# -*- coding: utf-8 -*-
# Partie de grimoire1.py (découpage v1.2.2, comportement inchangé).
# Chargée par grimoire1.py dans un espace de noms commun : ne pas lancer seule.
from __future__ import annotations



class Store:
    """Grimoire : SQLite (grimoire.db) + medias/<sujet_id>/ ; acces protege par un verrou (threads)."""

    def __init__(self, data_dir: Optional[str] = None):
        if data_dir:
            Paths.set(data_dir)
        self.lock = threading.RLock()
        self.conn: Optional[sqlite3.Connection] = None
        self.fts_ok = True
        self._subj_cache: Optional[Dict[int, Dict[str, Any]]] = None
        self.version = 0          # change a chaque modification (rafraichissement de l'interface)
        self.last_error = ""

    # ------------------------------------------------------------ ouverture
    def open(self) -> "Store":
        os.makedirs(Paths.data, exist_ok=True)
        os.makedirs(Paths.media(), exist_ok=True)
        if not os.path.exists(Paths.db()) and os.path.isfile(SEED_DB):
            try:   # premier lancement : base de depart (n'ecrase jamais une base existante)
                shutil.copyfile(SEED_DB, Paths.db())
                logger.info("base de départ copiée : %s", SEED_DB)
            except OSError as ex:
                logger.warning("base de départ non copiée : %s", ex)
        self.conn = sqlite3.connect(Paths.db(), check_same_thread=False, timeout=15)
        self.conn.row_factory = sqlite3.Row
        c = self.conn
        c.execute("PRAGMA foreign_keys=OFF")
        c.execute("PRAGMA synchronous=NORMAL")
        c.executescript(SCHEMA)
        c.executescript(GX_ARCHIVES_SQL)   # 1.5 : liens rendus permanents (ajout, rien n'est modifie)
        try:
            c.execute(FTS_SQL)
        except sqlite3.OperationalError as ex:
            self.fts_ok = False
            logger.warning("FTS5 indisponible : %s (recherche simple)", ex)
        v = c.execute("PRAGMA user_version").fetchone()[0]
        if v < SCHEMA_VERSION:
            c.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        c.commit()
        return self

    def close(self) -> None:
        with self.lock:
            if self.conn:
                try:
                    self.conn.commit()
                    self.conn.close()
                except Exception:
                    pass
                self.conn = None

    def _touch(self) -> None:
        self.version += 1
        self._subj_cache = None

    def q(self, sql: str, args: Iterable[Any] = ()) -> List[sqlite3.Row]:
        with self.lock:
            return self.conn.execute(sql, tuple(args)).fetchall()

    def x(self, sql: str, args: Iterable[Any] = (), commit: bool = True) -> sqlite3.Cursor:
        with self.lock:
            cur = self.conn.execute(sql, tuple(args))
            if commit:
                self.conn.commit()
            return cur

    # ------------------------------------------------------------ reglages
    def get(self, key: str, default: Any = None) -> Any:
        r = self.q("SELECT value FROM settings WHERE key=?", (key,))
        if not r:
            return default
        try:
            return json.loads(r[0]["value"])
        except (ValueError, TypeError):
            return default

    def set(self, key: str, value: Any) -> None:
        self.x("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (key, json.dumps(value, ensure_ascii=False)))

    # ------------------------------------------------------------ sujets
    def subjects(self) -> Dict[int, Dict[str, Any]]:
        with self.lock:
            if self._subj_cache is None:
                rows = self.q("SELECT * FROM subjects WHERE deleted IS NULL")
                self._subj_cache = {r["id"]: dict(r) for r in rows}
            return self._subj_cache

    def subject(self, sid: Any) -> Optional[Dict[str, Any]]:
        try:
            return self.subjects().get(int(sid))
        except (TypeError, ValueError):
            return None

    def children(self, sid: Optional[int]) -> List[Dict[str, Any]]:
        subs = [s for s in self.subjects().values() if (s["parent_id"] or None) == (sid or None)]
        return sorted(subs, key=lambda s: (-int(s["pinned"] or 0), float(s["sort"] or 0), norm(s["name"])))

    def descendants(self, sid: int) -> List[int]:
        out, stack = [], [sid]
        allsubs = list(self.subjects().values())
        while stack:
            cur = stack.pop()
            for s in allsubs:
                if s["parent_id"] == cur:
                    out.append(s["id"])
                    stack.append(s["id"])
        return out

    def subject_path(self, sid: Any, sep: str = " › ") -> str:
        names, seen = [], set()
        s = self.subject(sid)
        while s and s["id"] not in seen:
            seen.add(s["id"])
            names.append(s["name"])
            s = self.subject(s["parent_id"]) if s["parent_id"] else None
        return sep.join(reversed(names)) if names else "(sujet supprimé)"

    def subject_label(self, sid: Any) -> str:
        s = self.subject(sid)
        return f"{s['icon'] or '📁'} {self.subject_path(sid)}" if s else "(sujet supprimé)"

    def add_subject(self, name: str, parent_id: Optional[int] = None, icon: str = "📁", color: str = "",
                    description: str = "", pinned: bool = False) -> int:
        with self.lock:
            mx = self.q("SELECT COALESCE(MAX(sort),0) m FROM subjects WHERE COALESCE(parent_id,0)=?", (parent_id or 0,))[0]["m"]
            cur = self.x("INSERT INTO subjects(parent_id,name,icon,color,pinned,sort,description,created,updated) "
                         "VALUES(?,?,?,?,?,?,?,?,?)",
                         (parent_id or None, name.strip() or "Sans nom", icon or "📁", color, int(pinned), mx + 1,
                          description, now_iso(), now_iso()))
            self._touch()
            return int(cur.lastrowid)

    def update_subject(self, sid: int, **kw) -> None:
        kw = {k: v for k, v in kw.items() if k in SUBJECT_FIELDS}
        if not kw:
            return
        kw["updated"] = now_iso()
        cols = ", ".join(f"{k}=?" for k in kw)
        self.x(f"UPDATE subjects SET {cols} WHERE id=?", list(kw.values()) + [sid])
        self._touch()

    def find_subject(self, name: str) -> Optional[int]:
        """Par nom (sans accents) ou chemin « Santé/Protocoles » ou « Santé › Protocoles »."""
        name = (name or "").strip()
        if not name:
            return None
        exact = [s for s in self.subjects().values() if norm(s["name"]) == norm(name)]
        if exact:
            exact.sort(key=lambda s: (s["parent_id"] is not None, s["id"]))
            return exact[0]["id"]
        parts = split_subject_path(name)
        if len(parts) > 1:
            parent = None
            for p in parts:
                hit = next((s for s in self.children(parent) if norm(s["name"]) == norm(p)), None)
                if not hit:
                    return None
                parent = hit["id"]
            return parent
        hits = [s for s in self.subjects().values() if norm(s["name"]) == norm(name)]
        if hits:
            hits.sort(key=lambda s: (s["parent_id"] is not None, s["id"]))
            return hits[0]["id"]
        return None

    def ensure_subject(self, name: str, icon: str = "📁") -> int:
        sid = self.find_subject(name)
        if sid:
            return sid
        parts = split_subject_path(name) or ["Sans nom"]
        parent = None
        for p in parts:
            hit = next((s for s in self.children(parent) if norm(s["name"]) == norm(p)), None)
            parent = hit["id"] if hit else self.add_subject(p, parent, icon)
        return int(parent)

    def inbox_subject(self) -> int:
        return self.ensure_subject(INBOX_SUBJECT, "📥")

    def counts(self) -> Dict[int, int]:
        rows = self.q("SELECT subject_id, COUNT(*) n FROM items WHERE deleted IS NULL GROUP BY subject_id")
        return {r["subject_id"]: r["n"] for r in rows}

    def total_counts(self) -> Dict[int, int]:
        direct = self.counts()
        tot: Dict[int, int] = {}

        def walk(sid: int) -> int:
            if sid in tot:
                return tot[sid]
            n = direct.get(sid, 0) + sum(walk(c["id"]) for c in self.children(sid))
            tot[sid] = n
            return n
        for sid in self.subjects():
            walk(sid)
        return tot

    def move_subject(self, sid: int, new_parent: Optional[int]) -> bool:
        if new_parent == sid or (new_parent and new_parent in self.descendants(sid)):
            return False
        mx = self.q("SELECT COALESCE(MAX(sort),0) m FROM subjects WHERE COALESCE(parent_id,0)=?", (new_parent or 0,))[0]["m"]
        self.update_subject(sid, parent_id=new_parent or None, sort=mx + 1)
        return True

    def reorder_subject(self, sid: int, delta: int) -> None:
        s = self.subject(sid)
        if not s:
            return
        sib = self.children(s["parent_id"])
        ids = [x["id"] for x in sib]
        i = ids.index(sid)
        j = max(0, min(len(ids) - 1, i + delta))
        if i == j:
            return
        ids.insert(j, ids.pop(i))
        with self.lock:
            for k, x in enumerate(ids):
                self.conn.execute("UPDATE subjects SET sort=? WHERE id=?", (k + 1, x))
            self.conn.commit()
        self._touch()

    def place_subject_before(self, sid: int, target: int) -> None:
        t = self.subject(target)
        if not t or sid == target or target in self.descendants(sid):
            return
        sib = [x["id"] for x in self.children(t["parent_id"]) if x["id"] != sid]
        sib.insert(sib.index(target), sid)
        with self.lock:
            self.conn.execute("UPDATE subjects SET parent_id=? WHERE id=?", (t["parent_id"], sid))
            for k, x in enumerate(sib):
                self.conn.execute("UPDATE subjects SET sort=? WHERE id=?", (k + 1, x))
            self.conn.commit()
        self._touch()

    # ------------------------------------------------------------ items
    def item(self, iid: Any) -> Optional[Dict[str, Any]]:
        try:
            r = self.q("SELECT * FROM items WHERE id=?", (int(iid),))
        except (TypeError, ValueError):
            return None
        return dict(r[0]) if r else None

    def _index(self, iid: int, d: Optional[Dict[str, Any]] = None) -> None:
        if not self.fts_ok:
            return
        d = d or self.item(iid)
        with self.lock:
            self.conn.execute("DELETE FROM fts WHERE rowid=?", (iid,))
            if d and not d.get("deleted"):
                meta = {}
                try:
                    meta = json.loads(d.get("meta") or "{}")
                except ValueError:
                    pass
                extra = " ".join(str(meta.get(k, "")) for k in ("description", "site", "filename"))
                self.conn.execute("INSERT INTO fts(rowid,title,body,extracted,tags,source,url) VALUES(?,?,?,?,?,?,?)",
                                  (iid, d.get("title") or "", d.get("body_text") or "",
                                   (d.get("extracted") or "") + " " + extra, d.get("tags") or "",
                                   ((d.get("source") or "") + " " + (d.get("author") or "")).strip(), d.get("url") or ""))

    def add_item(self, subject_id: int, type_: str, **kw) -> int:
        d = {k: v for k, v in kw.items() if k in ITEM_FIELDS}
        d["subject_id"] = subject_id
        d["type"] = type_ if type_ in TYPES else "file"
        d.setdefault("created", now_iso())
        d.setdefault("updated", d["created"])
        if "tags" in d:
            d["tags"] = norm_tags(d["tags"])
        if "body" in d and "body_text" not in d:
            d["body_text"] = runs_plain(runs_from_any(d["body"]))
        if isinstance(d.get("meta"), dict):
            d["meta"] = json.dumps(d["meta"], ensure_ascii=False)
        with self.lock:
            if "sort" not in d:
                d["sort"] = self.q("SELECT COALESCE(MAX(sort),0) m FROM items WHERE subject_id=?", (subject_id,))[0]["m"] + 1
            cols = ", ".join(d.keys())
            cur = self.conn.execute(f"INSERT INTO items({cols}) VALUES({', '.join('?' * len(d))})", list(d.values()))
            iid = int(cur.lastrowid)
            self._index(iid)
            self.conn.commit()
        self._touch()
        return iid

    def update_item(self, iid: int, touch: bool = True, **kw) -> None:
        kw = {k: v for k, v in kw.items() if k in ITEM_FIELDS}
        if not kw:
            return
        if "tags" in kw:
            kw["tags"] = norm_tags(kw["tags"])
        if "body" in kw and "body_text" not in kw:
            kw["body_text"] = runs_plain(runs_from_any(kw["body"]))
        if isinstance(kw.get("meta"), dict):
            kw["meta"] = json.dumps(kw["meta"], ensure_ascii=False)
        if touch:
            kw.setdefault("updated", now_iso())
        cols = ", ".join(f"{k}=?" for k in kw)
        with self.lock:
            self.conn.execute(f"UPDATE items SET {cols} WHERE id=?", list(kw.values()) + [iid])
            if FTS_FIELDS & set(kw) or "deleted" in kw:
                self._index(iid)
            self.conn.commit()
        self._touch()

    def meta(self, it: Dict[str, Any]) -> Dict[str, Any]:
        try:
            m = json.loads(it.get("meta") or "{}")
            return m if isinstance(m, dict) else {}
        except ValueError:
            return {}

    def set_meta(self, iid: int, **kw) -> None:
        it = self.item(iid)
        if not it:
            return
        m = self.meta(it)
        m.update(kw)
        self.update_item(iid, touch=False, meta=m)

    def items_in(self, sids: List[int], deleted: bool = False) -> List[Dict[str, Any]]:
        if not sids:
            return []
        marks = ",".join("?" * len(sids))
        cond = "deleted IS NOT NULL" if deleted else "deleted IS NULL"
        return [dict(r) for r in self.q(f"SELECT * FROM items WHERE subject_id IN ({marks}) AND {cond}", sids)]

    def items_where(self, where: str, args: Iterable[Any] = (), limit: int = 5000, order: str = "") -> List[Dict[str, Any]]:
        parts = re.split(r"\s+ORDER\s+BY\s+", where, maxsplit=1, flags=re.I)
        where = parts[0]
        order = order or (parts[1] if len(parts) > 1 else "")
        sql = f"SELECT * FROM items WHERE deleted IS NULL AND ({where})" + (f" ORDER BY {order}" if order else "")
        return [dict(r) for r in self.q(sql + f" LIMIT {int(limit)}", args)]

    def all_tags(self) -> List[Tuple[str, int]]:
        cnt: Dict[str, Tuple[str, int]] = {}
        for r in self.q("SELECT tags FROM items WHERE deleted IS NULL AND tags<>''"):
            for t in tag_list(r["tags"]):
                k = norm(t)
                cnt[k] = (cnt.get(k, (t, 0))[0], cnt.get(k, (t, 0))[1] + 1)
        return sorted(cnt.values(), key=lambda x: (-x[1], norm(x[0])))

    # ------------------------------------------------------------ corbeille
    def trash_items(self, ids: List[int], batch: Optional[str] = None) -> str:
        batch = batch or uuid.uuid4().hex[:10]
        ts = now_iso()
        with self.lock:
            for i in ids:
                self.conn.execute("UPDATE items SET deleted=?, del_batch=? WHERE id=? AND deleted IS NULL", (ts, batch, i))
                if self.fts_ok:
                    self.conn.execute("DELETE FROM fts WHERE rowid=?", (i,))
            self.conn.commit()
        self._touch()
        return batch

    def trash_subject(self, sid: int) -> str:
        batch = uuid.uuid4().hex[:10]
        ts = now_iso()
        allids = [sid] + self.descendants(sid)
        with self.lock:
            for s in allids:
                self.conn.execute("UPDATE subjects SET deleted=?, del_batch=? WHERE id=?", (ts, batch, s))
                for r in self.conn.execute("SELECT id FROM items WHERE subject_id=? AND deleted IS NULL", (s,)).fetchall():
                    self.conn.execute("UPDATE items SET deleted=?, del_batch=? WHERE id=?", (ts, batch, r["id"]))
                    if self.fts_ok:
                        self.conn.execute("DELETE FROM fts WHERE rowid=?", (r["id"],))
            self.conn.commit()
        self._touch()
        return batch

    def restore_batch(self, batch: str) -> int:
        with self.lock:
            n = self.conn.execute("UPDATE subjects SET deleted=NULL, del_batch=NULL WHERE del_batch=?", (batch,)).rowcount
            ids = [r["id"] for r in self.conn.execute("SELECT id FROM items WHERE del_batch=?", (batch,)).fetchall()]
            self.conn.execute("UPDATE items SET deleted=NULL, del_batch=NULL WHERE del_batch=?", (batch,))
            self.conn.commit()
            self._subj_cache = None
            subs = self.subjects()
            for i in ids:
                it = self.item(i)
                if it and it["subject_id"] not in subs:   # sujet parti : l'item revient dans « À classer »
                    self.conn.execute("UPDATE items SET subject_id=? WHERE id=?", (self.inbox_subject(), i))
                self._index(i)
            # sujet restaure dont le parent est encore a la corbeille : il revient a la racine
            for s in self.q("SELECT id,parent_id FROM subjects WHERE deleted IS NULL AND parent_id IS NOT NULL"):
                if s["parent_id"] not in self.subjects() and not self.q(
                        "SELECT 1 FROM subjects WHERE id=? AND deleted IS NULL", (s["parent_id"],)):
                    self.conn.execute("UPDATE subjects SET parent_id=NULL WHERE id=?", (s["id"],))
            self.conn.commit()
        self._touch()
        return n + len(ids)

    def restore_items(self, ids: List[int]) -> int:
        subs = self.subjects()
        n = 0
        for i in ids:
            it = self.item(i)
            if not it:
                continue
            sid = it["subject_id"] if it["subject_id"] in subs else self.inbox_subject()
            self.x("UPDATE items SET deleted=NULL, del_batch=NULL, subject_id=? WHERE id=?", (sid, i))
            with self.lock:
                self._index(i)
                self.conn.commit()
            n += 1
        self._touch()
        return n

    def trash_list(self) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        subs = [dict(r) for r in self.q("SELECT * FROM subjects WHERE deleted IS NOT NULL ORDER BY deleted DESC")]
        its = [dict(r) for r in self.q("SELECT * FROM items WHERE deleted IS NOT NULL ORDER BY deleted DESC")]
        return subs, its

    def purge_items(self, ids: List[int]) -> int:
        n = 0
        for i in ids:
            it = self.item(i)
            if not it:
                continue
            for rel in (it.get("file"), it.get("thumb")) + tuple(self.meta(it).get("extra_files", [])):
                p = Paths.abs(rel) if rel else ""
                if p and os.path.isfile(p) and os.path.abspath(p).startswith(os.path.abspath(Paths.media())):
                    if not self.q("SELECT 1 FROM items WHERE id<>? AND (file=? OR thumb=?)", (i, rel, rel)):
                        try:
                            os.remove(p)
                        except OSError:
                            pass
            self.x("DELETE FROM items WHERE id=?", (i,), commit=False)
            if self.fts_ok:
                self.x("DELETE FROM fts WHERE rowid=?", (i,), commit=False)
            n += 1
        with self.lock:
            self.conn.commit()
        self._touch()
        return n

    def empty_trash(self, batch: Optional[str] = None) -> int:
        cond, args = ("del_batch=?", (batch,)) if batch else ("deleted IS NOT NULL", ())
        ids = [r["id"] for r in self.q(f"SELECT id FROM items WHERE {cond}", args)]
        n = self.purge_items(ids)
        self.x(f"DELETE FROM subjects WHERE {cond}", args)
        self._touch()
        return n

    # ------------------------------------------------------------ fichiers
    def subject_media_dir(self, sid: int) -> str:
        d = os.path.join(Paths.media(), str(sid))
        os.makedirs(d, exist_ok=True)
        return d

    def unique_path(self, folder: str, name: str) -> str:
        return unique_path(folder, name)

    def import_file(self, src: str, sid: int, move: bool = False) -> str:
        dst = self.unique_path(self.subject_media_dir(sid), os.path.basename(src))
        if move:
            shutil.move(src, dst)
        else:
            shutil.copy2(src, dst)
        return Paths.rel(dst)

    def relocate_files(self, it: Dict[str, Any], new_sid: int) -> Dict[str, Any]:
        """Deplace les fichiers d'un item dans medias/<nouveau sujet>/ (retourne les champs a mettre a jour)."""
        upd: Dict[str, Any] = {}
        media_root = os.path.abspath(Paths.media())
        for key in ("file", "thumb"):
            rel = it.get(key) or ""
            p = Paths.abs(rel)
            if not rel or not os.path.isfile(p) or not os.path.abspath(p).startswith(media_root):
                continue
            if self.q("SELECT 1 FROM items WHERE id<>? AND (file=? OR thumb=?)", (it["id"], rel, rel)):
                continue
            sub = "_vignettes" if key == "thumb" else ""
            dest_dir = os.path.join(self.subject_media_dir(new_sid), sub) if sub else self.subject_media_dir(new_sid)
            os.makedirs(dest_dir, exist_ok=True)
            try:
                dst = self.unique_path(dest_dir, os.path.basename(p))
                shutil.move(p, dst)
                upd[key] = Paths.rel(dst)
            except OSError as ex:
                logger.warning("déplacement fichier %s : %s", p, ex)
        m = self.meta(it)
        if m.get("extra_files"):
            new_extra = []
            for rel in m["extra_files"]:
                p = Paths.abs(rel)
                if os.path.isfile(p) and os.path.abspath(p).startswith(media_root):
                    try:
                        dst = self.unique_path(self.subject_media_dir(new_sid), os.path.basename(p))
                        shutil.move(p, dst)
                        rel = Paths.rel(dst)
                    except OSError:
                        pass
                new_extra.append(rel)
            m["extra_files"] = new_extra
            upd["meta"] = m
        return upd

    def move_items(self, ids: List[int], sid: int) -> List[Tuple[int, int]]:
        old = []
        for i in ids:
            it = self.item(i)
            if not it or it["subject_id"] == sid:
                continue
            old.append((i, it["subject_id"]))
            upd = self.relocate_files(it, sid)
            mx = self.q("SELECT COALESCE(MAX(sort),0) m FROM items WHERE subject_id=?", (sid,))[0]["m"]
            self.update_item(i, touch=False, subject_id=sid, sort=mx + 1, **upd)
        return old

    def copy_items(self, ids: List[int], sid: int) -> List[int]:
        new = []
        for i in ids:
            it = self.item(i)
            if not it:
                continue
            d = {k: it[k] for k in ITEM_FIELDS if k in it and k not in ("subject_id", "type", "deleted", "del_batch", "sort")}
            for key in ("file", "thumb"):
                p = Paths.abs(it.get(key) or "")
                if p and os.path.isfile(p):
                    try:
                        dest_dir = self.subject_media_dir(sid)
                        if key == "thumb":
                            dest_dir = os.path.join(dest_dir, "_vignettes")
                            os.makedirs(dest_dir, exist_ok=True)
                        dst = self.unique_path(dest_dir, os.path.basename(p))
                        shutil.copy2(p, dst)
                        d[key] = Paths.rel(dst)
                    except OSError:
                        pass
            d["created"] = now_iso()
            d["updated"] = d["created"]
            new.append(self.add_item(sid, it["type"], **d))
        return new

    def merge_subjects(self, src: int, dst: int) -> Dict[str, Any]:
        """Fusionne src dans dst : items et sous-sujets passent dans dst, puis src va a la corbeille."""
        moved = self.move_items([r["id"] for r in self.items_in([src])], dst)
        kids = [c["id"] for c in self.children(src)]
        for k in kids:
            self.update_subject(k, parent_id=dst)
        batch = self.trash_subject(src)
        return {"moved": moved, "kids": kids, "batch": batch, "src": src}

    # ------------------------------------------------------------ recherche
    @staticmethod
    def fts_query(text: str) -> str:
        toks = re.findall(r"[\w'-]+", text, re.UNICODE)
        parts = []
        for t in toks:
            t = t.replace('"', "").strip("'-")
            if not t:
                continue
            parts.append(f'"{t}"*' if len(t) >= 2 else f'"{t}"')
        return " AND ".join(parts)

    def search(self, text: str, types: Optional[List[str]] = None, sids: Optional[List[int]] = None,
               tag: str = "", since: str = "", fav_only: bool = False, limit: int = 400) -> List[Dict[str, Any]]:
        text = (text or "").strip()
        conds, args = ["i.deleted IS NULL"], []
        if types:
            conds.append(f"i.type IN ({','.join('?' * len(types))})")
            args += types
        if sids:
            conds.append(f"i.subject_id IN ({','.join('?' * len(sids))})")
            args += sids
        if since:
            conds.append("COALESCE(NULLIF(i.event_date,''), i.created) >= ?")
            args.append(since)
        if fav_only:
            conds.append("i.fav=1")
        res: List[Dict[str, Any]] = []
        fq = self.fts_query(text) if text else ""
        if fq and self.fts_ok:
            try:
                sql = ("SELECT i.*, snippet(fts, 1, char(1), char(2), '…', 18) AS s_body, "
                       "snippet(fts, 2, char(1), char(2), '…', 18) AS s_ext, bm25(fts, 8.0, 2.0, 1.0, 4.0, 2.0, 1.0) AS rk "
                       "FROM fts JOIN items i ON i.id = fts.rowid WHERE fts MATCH ? AND " + " AND ".join(conds) +
                       f" ORDER BY i.pinned DESC, rk LIMIT {int(limit)}")
                res = [dict(r) for r in self.q(sql, [fq] + args)]
                for r in res:
                    sb, se = r.pop("s_body", "") or "", r.pop("s_ext", "") or ""
                    r["snip"] = sb if "\x01" in sb else (se if "\x01" in se else "")
            except sqlite3.OperationalError as ex:
                logger.info("recherche FTS : %s (repli LIKE)", ex)
                res = []
                fq = ""
        if text and (not self.fts_ok or not fq):
            like = f"%{text}%"
            sql = ("SELECT i.*, '' AS snip FROM items i WHERE (i.title LIKE ? OR i.body_text LIKE ? OR i.extracted LIKE ? "
                   "OR i.tags LIKE ? OR i.url LIKE ? OR i.source LIKE ?) AND " + " AND ".join(conds) +
                   f" ORDER BY i.updated DESC LIMIT {int(limit)}")
            res = [dict(r) for r in self.q(sql, [like] * 6 + args)]
        elif not text:
            sql = ("SELECT i.*, '' AS snip FROM items i WHERE " + " AND ".join(conds) +
                   f" ORDER BY COALESCE(NULLIF(i.event_date,''), i.created) DESC LIMIT {int(limit)}")
            res = [dict(r) for r in self.q(sql, args)]
        if tag:
            res = [r for r in res if norm(tag) in [norm(t) for t in tag_list(r.get("tags") or "")]]
        # les noms de sujets comptent aussi : « recettes » trouve les items du sujet Recettes
        if text and not tag:
            hit_sids = [s["id"] for s in self.subjects().values() if all(norm(t) in norm(s["name"]) for t in text.split())]
            if hit_sids:
                have = {r["id"] for r in res}
                extra = [r for r in self.items_in(hit_sids) if r["id"] not in have]
                extra = [r for r in extra if (not types or r["type"] in types) and (not sids or r["subject_id"] in sids)
                         and (not fav_only or r["fav"])]
                for r in extra[:200]:
                    r["snip"] = ""
                res += extra
        return res

    def find_by_title(self, title: str) -> Optional[Dict[str, Any]]:
        t = norm(title)
        for r in self.q("SELECT * FROM items WHERE deleted IS NULL AND title<>'' ORDER BY updated DESC"):
            if norm(r["title"]) == t:
                return dict(r)
        return None

    def backlinks(self, it: Dict[str, Any]) -> List[Dict[str, Any]]:
        title = (it.get("title") or "").strip()
        if not title:
            return []
        out = []
        cand = self.items_where("body_text LIKE ?", (f"%[[%",))
        for r in cand:
            if r["id"] == it["id"]:
                continue
            for m in REF_RE.finditer(r.get("body_text") or ""):
                if norm(m.group(1)) == norm(title):
                    out.append(r)
                    break
        return out

    def rebuild_fts(self) -> int:
        if not self.fts_ok:
            return 0
        with self.lock:
            self.conn.execute("DELETE FROM fts")
            ids = [r["id"] for r in self.conn.execute("SELECT id FROM items WHERE deleted IS NULL").fetchall()]
            for i in ids:
                self._index(i)
            self.conn.commit()
        return len(ids)

    # ------------------------------------------------------------ sauvegardes
    def backup(self, force: bool = False, tag: str = "") -> Optional[str]:
        os.makedirs(Paths.backups(), exist_ok=True)
        last = float(self.get("last_backup_ts", 0) or 0)
        if not force and time.time() - last < BACKUP_MIN_INTERVAL:
            return None
        if not os.path.isfile(Paths.db()):
            return None
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        dst = os.path.join(Paths.backups(), f"grimoire_{stamp}{('_' + tag) if tag else ''}.db")
        try:
            with self.lock:
                self.conn.commit()
                b = sqlite3.connect(dst)
                self.conn.backup(b)
                b.close()
            self.set("last_backup_ts", time.time())
            files = sorted(glob.glob(os.path.join(Paths.backups(), "grimoire_*.db")))
            for old in files[:-BACKUP_KEEP]:
                try:
                    os.remove(old)
                except OSError:
                    pass
            logger.info("sauvegarde %s", dst)
            return dst
        except Exception as ex:
            logger.error("sauvegarde : %s", ex)
            self.last_error = str(ex)
            return None

    def integrity(self) -> str:
        try:
            return str(self.q("PRAGMA integrity_check")[0][0])
        except Exception as ex:
            return str(ex)

    def stats(self) -> Dict[str, Any]:
        st: Dict[str, Any] = {}
        st["subjects"] = len(self.subjects())
        st["items"] = self.q("SELECT COUNT(*) n FROM items WHERE deleted IS NULL")[0]["n"]
        st["trash"] = self.q("SELECT COUNT(*) n FROM items WHERE deleted IS NOT NULL")[0]["n"]
        st["by_type"] = {r["type"]: r["n"] for r in self.q("SELECT type, COUNT(*) n FROM items WHERE deleted IS NULL GROUP BY type")}
        st["favs"] = self.q("SELECT COUNT(*) n FROM items WHERE deleted IS NULL AND fav=1")[0]["n"]
        st["pinned"] = self.q("SELECT COUNT(*) n FROM items WHERE deleted IS NULL AND pinned=1")[0]["n"]
        st["months"] = [(r["m"], r["n"]) for r in self.q(
            "SELECT substr(created,1,7) m, COUNT(*) n FROM items WHERE deleted IS NULL GROUP BY m ORDER BY m DESC LIMIT 12")]
        st["words"] = sum(len((r["body_text"] or "").split()) for r in self.q("SELECT body_text FROM items WHERE deleted IS NULL"))
        size = 0
        nfiles = 0
        for root, _d, files in os.walk(Paths.media()):
            for f in files:
                try:
                    size += os.path.getsize(os.path.join(root, f))
                    nfiles += 1
                except OSError:
                    pass
        st["media_size"], st["media_files"] = size, nfiles
        try:
            st["db_size"] = os.path.getsize(Paths.db())
        except OSError:
            st["db_size"] = 0
        st["tags"] = self.all_tags()[:20]
        tot = self.total_counts()
        st["top_subjects"] = sorted(((self.subject_label(k), v) for k, v in tot.items() if v), key=lambda x: -x[1])[:10]
        st["backups"] = len(glob.glob(os.path.join(Paths.backups(), "grimoire_*.db")))
        lb = float(self.get("last_backup_ts", 0) or 0)
        st["last_backup"] = dt.datetime.fromtimestamp(lb).strftime("%Y-%m-%d %H:%M") if lb else "jamais"
        return st


def unique_path(folder: str, name: str) -> str:
    base, ext = os.path.splitext(safe_name(name, 120))
    p = os.path.join(folder, base + ext)
    n = 2
    while os.path.exists(p):
        p = os.path.join(folder, f"{base}_{n}{ext}")
        n += 1
    return p
