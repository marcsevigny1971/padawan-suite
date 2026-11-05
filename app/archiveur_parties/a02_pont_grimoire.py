# -*- coding: utf-8 -*-
# Partie de archiveur5.py (découpage v1.2.2, comportement inchangé).
# Chargée par archiveur5.py dans un espace de noms commun : ne pas lancer seule.
from __future__ import annotations




# ---------------------------------------------------------------- Grimoire : ecriture directe dans grimoire.db (5.x)
GR_MUTEX = "Local\\Grimoire_SingleInstance"
GR_ARCHIVES_SQL = """CREATE TABLE IF NOT EXISTS archives(
  url TEXT PRIMARY KEY, item_id INTEGER, status TEXT DEFAULT '', root TEXT DEFAULT '', folder TEXT DEFAULT '',
  info TEXT DEFAULT '{}', created TEXT, updated TEXT);"""


def gr_data_dir() -> str:
    env = os.environ.get("GRIMOIRE_DATA", "").strip()
    if env:
        return env
    root = os.environ.get("PADAWAN_DATA", "").strip()
    if root:
        return os.path.join(root, "Grimoire")
    if os.path.isdir(r"C:\web\FTP_HOME"):
        return os.path.join(r"C:\web\FTP_HOME", "GRIMOIRE")
    return os.path.join(os.path.expanduser("~"), "Documents", "Padawan", "Grimoire")


def gr_db_path() -> str:
    return os.path.join(gr_data_dir(), "grimoire.db")


def gr_connect():
    import sqlite3
    c = sqlite3.connect(gr_db_path(), timeout=20)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA busy_timeout=20000")
    c.execute(GR_ARCHIVES_SQL)
    c.commit()
    return c


def gr_now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def gr_norm(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", str(s or "").lower())
    return "".join(ch for ch in s if not unicodedata.combining(ch))


def gr_subjects(c) -> List[Dict[str, Any]]:
    return [dict(r) for r in c.execute("SELECT id,parent_id,name,icon,color,sort FROM subjects WHERE deleted IS NULL "
                                       "ORDER BY pinned DESC, sort, name")]


def gr_path(subs: List[Dict[str, Any]], sid: int) -> str:
    by = {s["id"]: s for s in subs}
    out, cur, n = [], by.get(sid), 0
    while cur and n < 20:
        out.append(cur["name"])
        cur = by.get(cur.get("parent_id"))
        n += 1
    return " › ".join(reversed(out))


def gr_suggest(subs: List[Dict[str, Any]], text: str) -> Optional[int]:
    """sujet du Grimoire le plus proche (mots du titre, description, collections et tags de l'archive)."""
    words = set(w for w in re.findall(r"[a-z0-9]{4,}", gr_norm(text)))
    best, score = None, 0.0
    for s in subs:
        sw = [w for w in re.findall(r"[a-z0-9]{4,}", gr_norm(s["name"]))]
        if not sw:
            continue
        hit = 0.0
        for w in sw:
            if w in words:
                hit += 2
            elif any(x.startswith(w[:5]) or w.startswith(x[:5]) for x in words if len(x) >= 5 and len(w) >= 5):
                hit += 1
        sc = hit / len(sw) + (0.2 if s.get("parent_id") else 0)
        if hit and sc > score:
            best, score = s["id"], sc
    return best


def gr_find_url(c, url: str) -> Optional[Dict[str, Any]]:
    if not url:
        return None
    r = c.execute("SELECT id,title,subject_id FROM items WHERE deleted IS NULL AND url=? ORDER BY id LIMIT 1", (url,)).fetchone()
    return dict(r) if r else None


def gr_folder_info(folder: str) -> Dict[str, Any]:
    files = os.listdir(folder) if os.path.isdir(folder) else []
    ext = (".mp4", ".webm", ".mkv", ".mov", ".m4v", ".mp3", ".m4a", ".opus")
    vids = sorted([f for f in files if f.lower().endswith(ext)], key=lambda f: -os.path.getsize(os.path.join(folder, f)))
    imgs = [f for f in files if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp")) and not f.startswith("sb_")]
    imgs.sort(key=lambda f: (0 if ("thumb" in f.lower() or "capture" in f.lower()) else 1, f))
    return {"main": vids[0] if vids else ("lecture.html" if "lecture.html" in files else
                                          ("page.html" if "page.html" in files else ("index.html" if "index.html" in files else ""))),
            "video": bool(vids and not vids[0].lower().endswith((".mp3", ".m4a", ".opus"))),
            "index": "index.html" if "index.html" in files else "", "capture": imgs[0] if imgs else "",
            "nfiles": len(files)}


def gr_add_subject(c, name: str, parent_id: Optional[int]) -> int:
    par = c.execute("SELECT icon,color FROM subjects WHERE id=?", (parent_id,)).fetchone() if parent_id else None
    srt = c.execute("SELECT COALESCE(MAX(sort),0)+1 FROM subjects WHERE parent_id IS ?", (parent_id,)).fetchone()[0]
    now = gr_now()
    cur = c.execute("INSERT INTO subjects(parent_id,name,icon,color,sort,created,updated) VALUES(?,?,?,?,?,?,?)",
                    (parent_id, name.strip()[:120], "📁", (par["color"] if par else "") or "", srt, now, now))
    c.commit()
    return int(cur.lastrowid)


def gr_add_fiche(c, sid: int, root: str, entry: Dict[str, Any], info: Dict[str, Any]) -> int:
    """cree une fiche dans le Grimoire (transaction courte) + lien « permanent » vers la copie locale."""
    folder_name = str(entry.get("folder") or "")
    folder = os.path.join(root, folder_name)
    url = str(info.get("url") or info.get("webpage_url") or entry.get("url") or "")
    fi = gr_folder_info(folder)
    title = str(info.get("title") or folder_name)[:300]
    desc = str(info.get("description") or info.get("text") or "")[:20000]
    typ = "video" if fi["video"] else "link"
    site = str(info.get("platform") or info.get("extractor_key") or "")
    try:
        site = platform_label(info.get("platform")) or site
    except Exception:
        pass
    tags = ", ".join(str(t) for t in (info.get("tags") or []) if isinstance(t, str))[:400]
    note = f"Archive locale : {folder}"
    if info.get("notes"):
        note += "\nNotes de l'Archiveur : " + str(info.get("notes"))
    body = json.dumps({"v": 1, "runs": [[note, []]]}, ensure_ascii=False, separators=(",", ":"))
    meta = {"description": desc[:1500], "site": site, "pending": False, "fetched": gr_now(), "auto_title": False,
            "source_archiveur": folder_name}
    now = gr_now()
    c.execute("BEGIN IMMEDIATE")
    try:
        srt = c.execute("SELECT COALESCE(MAX(sort),0)+1 FROM items WHERE subject_id=?", (sid,)).fetchone()[0]
        cur = c.execute("INSERT INTO items(subject_id,type,title,body,body_text,url,source,author,tags,extracted,meta,sort,created,updated) "
                        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (sid, typ, title, body, note, url, "Archiveur", str(info.get("uploader") or "")[:200], tags, desc,
                         json.dumps(meta, ensure_ascii=False), srt, now, now))
        iid = int(cur.lastrowid)
        thumb = ""
        if fi["capture"]:
            try:
                d = os.path.join(gr_data_dir(), "medias", str(sid), "_vignettes")
                os.makedirs(d, exist_ok=True)
                dest = os.path.join(d, f"v{iid}.png")
                try:
                    from PIL import Image  # type: ignore
                    with Image.open(os.path.join(folder, fi["capture"])) as im:
                        im = im.convert("RGB")
                        im.thumbnail((480, 320))
                        im.save(dest, "PNG")
                except Exception:
                    dest = os.path.join(d, f"v{iid}" + os.path.splitext(fi["capture"])[1].lower())
                    shutil.copyfile(os.path.join(folder, fi["capture"]), dest)
                thumb = f"medias/{sid}/_vignettes/{os.path.basename(dest)}"
                c.execute("UPDATE items SET thumb=? WHERE id=?", (thumb, iid))
            except Exception:
                thumb = ""
        try:
            c.execute("INSERT INTO fts(rowid,title,body,extracted,tags,source,url) VALUES(?,?,?,?,?,?,?)",
                      (iid, title, note, desc + " " + meta["description"] + " " + site, tags, "Archiveur", url))
        except Exception:
            pass   # pas de recherche plein texte : le Grimoire reconstruit l'index au besoin
        if url:
            fi.update({"source": "archiveur", "copie_le": now, "title": title})
            c.execute("INSERT OR REPLACE INTO archives(url,item_id,status,root,folder,info,created,updated) VALUES(?,?,?,?,?,?,?,?)",
                      (url, iid, "permanent", root, folder_name, json.dumps(fi, ensure_ascii=False), now, now))
        c.commit()
    except Exception:
        c.rollback()
        raise
    return iid


def gr_running() -> bool:
    if not sys.platform.startswith("win"):
        return False
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.windll.kernel32
        k32.OpenMutexW.restype = wintypes.HANDLE
        h = k32.OpenMutexW(0x00100000, False, GR_MUTEX)
        if h:
            k32.CloseHandle(h)
            return True
    except Exception:
        pass
    return False


def gr_open_item(iid: int, script: str) -> None:
    """ouvre la fiche dans le Grimoire (ouvert : message dans _inbox ; ferme : on le lance)."""
    d = os.path.join(gr_data_dir(), "_inbox")
    os.makedirs(d, exist_ok=True)
    fp = os.path.join(d, f"ouvrir_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.json")
    with open(fp + ".tmp", "w", encoding="utf-8") as f:
        json.dump({"action": "ouvrir", "id": int(iid)}, f)
    os.replace(fp + ".tmp", fp)
    if not gr_running() and os.path.isfile(script):
        py = sys.executable or "pythonw"
        if py.lower().endswith("python.exe") and os.path.isfile(py[:-10] + "pythonw.exe"):
            py = py[:-10] + "pythonw.exe"
        kw: Dict[str, Any] = {"cwd": os.path.dirname(script)}
        if sys.platform.startswith("win"):
            kw["creationflags"] = CREATE_NO_WINDOW
        subprocess.Popen([py, script], **kw)


class GrimoireSendDialog(tk.Toplevel if tk is not None else object):  # type: ignore[misc]
    """« 📚 Envoyer au Grimoire » : choisir un sujet (suggestion automatique), creer un sous-sujet au besoin."""

    def __init__(self, app, entries: List[Dict[str, Any]], infos: List[Dict[str, Any]]):
        super().__init__(app)
        self.app, self.entries, self.infos = app, entries, infos
        self.result: Optional[int] = None
        self.title("📚 Envoyer au Grimoire")
        self.configure(bg=NC_BG)
        self.transient(app)
        self.c = gr_connect()
        self.subs = gr_subjects(self.c)
        n = len(entries)
        hdr = (f"« {str(infos[0].get('title') or entries[0].get('folder'))[:90]} »" if n == 1 else f"{n} archives sélectionnées")
        tk.Label(self, text="📚 Dans quel sujet du Grimoire ?", bg=NC_BG, fg=NC_HI, font=FONT_TITLE).pack(anchor="w", padx=12, pady=(10, 0))
        tk.Label(self, text=hdr, bg=NC_BG, fg=NC_FG, font=FONT_UI, wraplength=560, justify="left").pack(anchor="w", padx=12)
        text = " ".join(str(i.get("title") or "") + " " + str(i.get("description") or "")[:600] + " " +
                        " ".join(str(x) for x in (i.get("tags") or [])) + " " + " ".join(str(x) for x in (e.get("collections") or []))
                        for e, i in zip(entries, infos))
        self.sug = gr_suggest(self.subs, text)
        if self.sug:
            tk.Label(self, text=f"✨ Suggestion : {gr_path(self.subs, self.sug)}", bg=NC_BG, fg=NC_OK, font=FONT_SM).pack(anchor="w", padx=12, pady=(4, 0))
        fr = tk.Frame(self, bg=NC_BG)
        fr.pack(fill="both", expand=True, padx=12, pady=6)
        self.tv = ttk.Treeview(fr, show="tree", selectmode="browse", height=16)
        sb = ttk.Scrollbar(fr, orient="vertical", command=self.tv.yview)
        self.tv.configure(yscrollcommand=sb.set)
        self.tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.fill()
        self.tv.bind("<Double-Button-1>", lambda _e: self.ok())
        self.tv.bind("<Return>", lambda _e: self.ok())
        bar = tk.Frame(self, bg=NC_BG)
        bar.pack(fill="x", padx=12, pady=(0, 10))
        b = app._btn(bar, "📁 Nouveau sous-sujet…", self.new_sub)
        b.pack(side="left")
        Tooltip(b, "Créer un sous-sujet dans le sujet choisi (ou un sujet principal si rien n'est choisi)")
        b = app._btn(bar, "✖ Annuler", self.destroy)
        b.pack(side="right", padx=(6, 0))
        Tooltip(b, "Fermer sans rien envoyer (Échap)")
        b = app._btn(bar, "📚 Envoyer", self.ok, hi=True)
        b.pack(side="right")
        Tooltip(b, "Crée la fiche dans le Grimoire : titre, texte, image, lien d'origine et copie locale (✔ Permanent)")
        self.bind("<Escape>", lambda _e: self.destroy())
        self.geometry("600x560")
        try:
            self.update_idletasks()
            self.geometry(f"+{app.winfo_rootx() + 80}+{app.winfo_rooty() + 60}")
        except Exception:
            pass
        self.tv.focus_set()
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def fill(self, sel: Optional[int] = None):
        self.tv.delete(*self.tv.get_children())
        kids: Dict[Any, List[Dict[str, Any]]] = {}
        for s in self.subs:
            kids.setdefault(s.get("parent_id"), []).append(s)

        def walk(pid, node):
            for s in kids.get(pid, []):
                self.tv.insert(node, "end", iid=str(s["id"]), text=f"{s.get('icon') or '📁'}  {s['name']}", open=True)
                walk(s["id"], str(s["id"]))
        walk(None, "")
        target = sel or self.sug or next((s["id"] for s in self.subs if s["name"] == "À classer"), None)
        if target and self.tv.exists(str(target)):
            self.tv.selection_set(str(target))
            self.tv.focus(str(target))
            self.tv.see(str(target))

    def new_sub(self):
        from tkinter import simpledialog
        sel = self.tv.selection()
        pid = int(sel[0]) if sel else None
        where = f" dans « {gr_path(self.subs, pid)} »" if pid else " (sujet principal)"
        name = simpledialog.askstring("Nouveau sous-sujet", "Nom du nouveau sujet" + where + " :", parent=self)
        if not name or not name.strip():
            return
        sid = gr_add_subject(self.c, name, pid)
        self.subs = gr_subjects(self.c)
        self.fill(sid)

    def ok(self):
        sel = self.tv.selection()
        if not sel:
            messagebox.showinfo("Grimoire", "Choisis un sujet dans la liste.", parent=self)
            return
        self.result = int(sel[0])
        self.destroy()

    def destroy(self):
        try:
            self.c.close()
        except Exception:
            pass
        super().destroy()
