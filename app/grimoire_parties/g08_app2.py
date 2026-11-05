# -*- coding: utf-8 -*-
# Partie de grimoire1.py (découpage v1.2.2, comportement inchangé).
# Chargée par grimoire1.py dans un espace de noms commun : ne pas lancer seule.
from __future__ import annotations

class _GrimoireAppPartie2:
    """Méthodes de GrimoireApp (partie 2/3)."""


    def _card_motion(self, e):
        iid = self._card_at(e.x, e.y)
        old = getattr(self, "_card_hover", None)
        if iid == old:
            return
        cv = self.cv
        for i, on in ((old, False), (iid, True)):
            if i is None:
                continue
            rid = next((o for o in cv.find_withtag(f"c{i}") if "card" in cv.gettags(o)), None)
            if rid:
                sel = i in self.selected
                cv.itemconfigure(rid, fill=gx_mix(C["CARD"], C["HI"], 0.10) if on else C["CARD"],
                                 outline=C["HI"] if sel else (C["FG"] if on else C["LINE"]), width=3 if sel else (2 if on else 1))
        self._card_hover = iid
        cv.configure(cursor="hand2" if iid else "")

    def _card_star_click(self, e) -> bool:
        cx, cy = self.cv.canvasx(e.x), self.cv.canvasy(e.y)
        for o in self.cv.find_overlapping(cx - 2, cy - 2, cx + 2, cy + 2):
            tags = self.cv.gettags(o)
            if "star" in tags:
                iid = int(next(t for t in tags if t.startswith("st"))[2:])
                it = self.store.item(iid)
                if it:
                    self.store.update_item(iid, touch=False, fav=0 if it.get("fav") else 1)
                    self.set_status("★ Ajoutée aux favoris." if not it.get("fav") else "☆ Retirée des favoris.", "OK")
                    self.refresh_items(keep=[iid])
                return True
        return False

    def _gx_open_pulse(self, iid: int):
        """petite pulsation de la carte a l'ouverture d'une fiche."""
        if not self.store.get("animations", True) or self._effective_mode() != "cards":
            return
        cv = self.cv
        rid = next((o for o in cv.find_withtag(f"c{iid}") if "card" in cv.gettags(o)), None)
        if not rid:
            return
        seq = [0.35, 0.6, 0.35, 0.15, 0.0]

        def go(k):
            if k >= len(seq) or not cv.winfo_exists():
                return
            try:
                cv.itemconfigure(rid, fill=gx_mix(C["CARD"], C["HI"], seq[k]))
            except tk.TclError:
                return
            self.after(45, lambda: go(k + 1))
        go(0)

    def toggle_animations(self):
        on = bool(self.v_anim.get())
        self.store.set("animations", on)
        self.set_status("✨ Animations activées." if on else "Animations désactivées (tout s'affiche d'un coup).", "OK")

    def open_mindmap(self):
        mm = getattr(self, "_mindmap", None)
        if mm is not None:
            try:
                if mm.winfo_exists():
                    mm.lift()
                    mm.focus_force()
                    return
            except tk.TclError:
                pass
        self._mindmap = MindMap(self)

    # ================================================================ 1.5 : apercus de liens + Archiveur
    def gx_link_section(self, f, it: Dict[str, Any], W: int):
        urls = gx_item_urls(it)
        if not urls:
            return
        self._section(f, "🔗 LIENS DE LA FICHE" if len(urls) > 1 else "🔗 LIEN DE LA FICHE")
        self._gx_link_rows = getattr(self, "_gx_link_rows", {})
        self._gx_link_rows = {}
        for u in urls:
            box = tk.Frame(f, bg=C["CARD"], highlightthickness=1, highlightbackground=C["LINE"])
            box.pack(fill="x", padx=12, pady=4)
            self._gx_link_rows[u] = (box, it["id"], W)
            self._gx_fill_link(u)
            pv = gx_preview_cached(u)
            if not pv or (not pv.get("ok") and time.time() - float(pv.get("t") or 0) > 3600):
                self.run_job(lambda uu=u: gx_fetch_preview(uu), lambda _r, uu=u: self._gx_fill_link(uu), "")

    def _gx_fill_link(self, url: str):
        rows = getattr(self, "_gx_link_rows", {})
        if url not in rows:
            return
        box, iid, W = rows[url]
        try:
            if not box.winfo_exists():
                return
        except tk.TclError:
            return
        for w in box.winfo_children():
            w.destroy()
        pv = gx_preview_cached(url) or {}
        a = gx_archive_get(self.store, url)
        folder = gx_archive_folder(a)
        bg = C["CARD"]
        top = tk.Frame(box, bg=bg)
        top.pack(fill="x", padx=6, pady=6)
        img = None
        ip = gx_preview_image(url)
        if not ip and folder and (a or {}).get("info", {}).get("capture"):
            ip = os.path.join(folder, a["info"]["capture"])
        if ip:
            img = self.photo(ip, 150, 96)
        if img is not None:
            lab = tk.Label(top, image=img, bg=bg, cursor="hand2", bd=0)
            lab.pack(side="left", padx=(0, 8))
            self._prev_imgs.append(img)
            lab.bind("<Button-1>", lambda _e: self._gx_watch(url) if folder else open_url(url))
            Tooltip(lab, "Clic : regarder la copie permanente" if folder else "Clic : ouvrir dans le navigateur")
        txt = tk.Frame(top, bg=bg)
        txt.pack(side="left", fill="x", expand=True)
        site = pv.get("site") or domain_of(url)
        mk_label(txt, ("🎬 " if pv.get("video") or is_video_url(url) else "🌐 ") + str(site), "DIM", "GSM", bg=bg).pack(anchor="w")
        title = pv.get("title") or (a or {}).get("info", {}).get("title") or url
        mk_link(txt, self.fit_text(title, "GUIB", max(120, W - 200), 2), url, bg=bg, font_name="GUIB", wrap=max(120, W - 190)).pack(anchor="w")
        if pv.get("desc"):
            mk_label(txt, self.fit_text(pv["desc"], "GSM", max(120, W - 200), 3), "TEXT", "GSM", bg=bg, justify="left",
                     wraplength=max(120, W - 190)).pack(anchor="w")
        if not pv:
            mk_label(txt, "⏳ Aperçu en préparation…", "DIM", "GSM", bg=bg).pack(anchor="w")
        bar = tk.Frame(box, bg=bg)
        bar.pack(fill="x", padx=6, pady=(0, 6))
        prog = getattr(self, "_gx_prog", {}).get(url)
        if prog is not None:
            self._gx_progress_bar(bar, url)
        elif folder:
            tk.Label(bar, text=f"✔ Permanent · dans l'Archiveur · {str((a or {}).get('updated') or '')[:10]}", bg="#2E9E5B",
                     fg="#FFFFFF", font=fnt("GSM"), padx=6).pack(anchor="w", pady=(0, 3))
            bar = tk.Frame(bar, bg=bg)
            bar.pack(fill="x")
            mk_button(bar, "▶ Regarder", lambda: self._gx_watch(url), "accent",
                      tip="Regarder la copie gardée sur ton PC (marche même si le lien original disparaît)").pack(side="left", padx=(0, 4))
            mk_button(bar, "💾 Copie locale", lambda: self._gx_local(url),
                      tip="Ouvrir la page de l'archive (index.html) dans le navigateur").pack(side="left", padx=2)
            mk_button(bar, "🗂 Dossier", lambda: reveal_in_explorer(folder), tip="Le dossier de la copie (Archiveur, collection « Grimoire »)").pack(
                side="left", padx=2)
        else:
            err = (a or {}).get("status") == "erreur"
            ok = bool(gx_archiveur_dir())
            b = mk_button(bar, "↻ Réessayer" if err else "📦 Rendre permanent", lambda: self.gx_make_permanent(url, iid), "accent",
                          tip=("Envoie le lien à l'Archiveur : une copie reste sur ton PC, même si le lien disparaît" if ok else
                               "L'Archiveur (archiveur5.py) est introuvable : bouton indisponible"))
            b.pack(side="left")
            if not ok:
                b.configure(state="disabled")
            if err:
                mk_label(bar, "⚠ La copie n'a pas marché (connexion ?) — tu peux réessayer.", "WARN", "GSM", bg=bg).pack(side="left", padx=6)
            mk_button(bar, "🌐 Ouvrir", lambda: open_url(url), tip="Ouvrir le lien dans le navigateur").pack(side="left", padx=4)
            mk_button(bar, "📋 Copier", lambda: (copy_to_clipboard(self, url), self.set_status("Lien copié.", "OK")),
                      tip="Copier le lien").pack(side="left", padx=2)

    def _gx_progress_bar(self, bar, url: str):
        bg = C["CARD"]
        cv = tk.Canvas(bar, height=16, bg=C["PANEL"], highlightthickness=0, bd=0)
        cv.pack(fill="x", pady=(2, 2))
        lab = mk_label(bar, "", "FG", "GSM", bg=bg)
        lab.pack(anchor="w")
        state = {"ph": 0.0}

        def tick():
            try:
                if not cv.winfo_exists():
                    return
            except tk.TclError:
                return
            p = getattr(self, "_gx_prog", {}).get(url)
            if p is None:
                return
            w = max(50, cv.winfo_width())
            cv.delete("all")
            pct = p.get("pct")
            if pct is None:   # barre vivante (indeterminee)
                state["ph"] = (state["ph"] + 7) % (w + 120)
                x = state["ph"] - 120
                cv.create_rectangle(max(0, x), 2, min(w, x + 120), 14, fill=C["HI"], width=0)
            else:
                cv.create_rectangle(0, 2, w * min(100, pct) / 100, 14, fill=C["HI"], width=0)
                state["ph"] = (state["ph"] + 9) % 40
                for xx in range(int(-40 + state["ph"]), int(w * min(100, pct) / 100), 40):
                    cv.create_line(xx, 14, xx + 12, 2, fill=gx_mix(C["HI"], "#FFFFFF", 0.5), width=4)
            lab.configure(text=gx_cheer(pct, p.get("log", "")))
            self.after(60 if self.store.get("animations", True) else 400, tick)
        tick()

    def gx_make_permanent(self, url: str, iid: Optional[int]):
        self._gx_prog = getattr(self, "_gx_prog", {})
        if url in self._gx_prog:
            return
        if not gx_archiveur_dir():
            messagebox.showinfo(APP_NAME, "L'Archiveur (archiveur5.py) est introuvable dans le dossier Padawan.\n"
                                          "Astuce : « 🌐 Capturer la page » garde quand même une copie hors ligne.", parent=self)
            return
        prog = self._gx_prog[url] = {"pct": None, "log": ""}
        gx_archive_set(self.store, url, iid, "copie")
        self._gx_fill_link(url)
        self.set_status("📦 Envoi à l'Archiveur… tu peux continuer à travailler.", "FG")

        def ev(k, v):
            prog[k] = v

        def work():
            r = gx_archive_via_archiveur(url, ev)
            folder = os.path.join(r["root"], r["folder"])
            fi = gx_folder_info(folder)
            if not fi["nfiles"]:
                raise RuntimeError("dossier d'archive introuvable")
            fi.update({"source": "grimoire", "dup": r.get("dup"), "copie_le": now_iso()})
            return r, fi

        def finish(res):
            self._gx_prog.pop(url, None)
            if isinstance(res, Exception) or not res:
                gx_archive_set(self.store, url, iid, "erreur")
                logger.warning("rendre permanent %s : %s", url, res)
                self.set_status("⚠ Copie impossible pour l'instant (connexion ?). Le lien reste dans la fiche ; tu pourras réessayer.", "WARN")
            else:
                r, fi = res
                gx_archive_set(self.store, url, iid, "permanent", r["root"], r["folder"], fi)
                self.set_status("✔ Lien rendu permanent : la copie est sur ton PC (Archiveur, collection « Grimoire »).", "OK")
                self._gx_toast("✔ Permanent ! Même si le lien disparaît, ta copie reste dans ton Grimoire.")
            self._gx_fill_link(url)
            if self._effective_mode() == "cards":
                self.fill_cards()
                if self.selected:
                    self.select_ids(self.selected)

        def job():
            try:
                out = work()
            except Exception as ex:
                logger.error("Archiveur : %s", traceback.format_exc())
                out = ex
            self.post(lambda: finish(out))
        threading.Thread(target=job, daemon=True).start()

    def _gx_watch(self, url: str):
        a = gx_archive_get(self.store, url)
        folder = gx_archive_folder(a)
        if not folder:
            open_url(url)
            return
        info = (a or {}).get("info") or {}
        main = info.get("main") or gx_folder_info(folder)["main"]
        p = os.path.join(folder, main) if main else folder
        open_path(p if os.path.exists(p) else folder)

    def _gx_local(self, url: str):
        a = gx_archive_get(self.store, url)
        folder = gx_archive_folder(a)
        if folder:
            p = os.path.join(folder, "index.html")
            open_path(p if os.path.isfile(p) else folder)

    def _gx_toast(self, msg: str, seconds: float = 3.5):
        try:
            t = tk.Toplevel(self)
            t.overrideredirect(True)
            t.configure(bg=C["HI"])
            tk.Label(t, text=msg, bg=C["HI"], fg=C["ON_HI"], font=fnt("GUIB"), padx=16, pady=8).pack()
            t.update_idletasks()
            x = self.winfo_rootx() + (self.winfo_width() - t.winfo_reqwidth()) // 2
            y = self.winfo_rooty() + self.winfo_height() - t.winfo_reqheight() - 60
            t.geometry(f"+{x}+{y}")
            t.attributes("-topmost", True)
            if self.store.get("animations", True):
                for k in range(6):
                    self.after(k * 30, lambda a=(k + 1) / 6: t.winfo_exists() and t.attributes("-alpha", a))
            self.after(int(seconds * 1000), t.destroy)
        except tk.TclError:
            pass

    def _gx_external_changes(self):
        """une autre application (ex. l'Archiveur) a ecrit dans grimoire.db : on rafraichit."""
        try:
            v = self.store.q("PRAGMA data_version")[0][0]
        except Exception:
            return
        old = getattr(self, "_gx_dv", None)
        self._gx_dv = v
        if old is not None and v != old:
            self.store._touch()
            self.refresh_all()

    def _card_at(self, x: int, y: int) -> Optional[int]:
        cx, cy = self.cv.canvasx(x), self.cv.canvasy(y)
        for x0, y0, x1, y1, iid in self.card_boxes:
            if x0 <= cx <= x1 and y0 <= cy <= y1:
                return iid
        return None

    def _card_press(self, e):
        self.cv.focus_set()
        if self._card_star_click(e):
            return
        iid = self._card_at(e.x, e.y)
        if iid is None:
            self.select_ids([])
            return
        ids = [r["id"] for r in self.visible]
        if e.state & 0x1 and self.anchor in ids:
            a, b = ids.index(self.anchor), ids.index(iid)
            self.select_ids(ids[min(a, b):max(a, b) + 1], anchor=False)
        elif e.state & 0x4:
            cur = list(self.selected)
            if iid in cur:
                cur.remove(iid)
            else:
                cur.append(iid)
            self.select_ids(cur, anchor=False)
        else:
            if iid not in self.selected or len(self.selected) == 1:
                self.select_ids([iid])
        self.press = {"x": e.x_root, "y": e.y_root, "ids": list(self.selected), "src": "items"}

    def _card_double(self, e):
        iid = self._card_at(e.x, e.y)
        if iid:
            self._gx_open_pulse(iid)
            self.open_item(iid)

    def _card_menu(self, e):
        iid = self._card_at(e.x, e.y)
        if iid and iid not in self.selected:
            self.select_ids([iid])
        if iid:
            self.item_menu(e)
        else:
            self.view_menu(e)

    def _card_key(self, key: str):
        ids = [r["id"] for r in self.visible[:400]]
        if not ids:
            return "break"
        cols = self._card_dims()[0]
        cur = ids.index(self.selected[0]) if self.selected and self.selected[0] in ids else -1
        step = {"Left": -1, "Right": 1, "Up": -cols, "Down": cols}.get(key, 0)
        if key == "Home":
            n = 0
        elif key == "End":
            n = len(ids) - 1
        else:
            n = max(0, min(len(ids) - 1, cur + step)) if cur >= 0 else 0
        self.select_ids([ids[n]], see=True)
        return "break"

    def _card_see(self, iid: int):
        for x0, y0, x1, y1, i in self.card_boxes:
            if i == iid:
                total = float(self.cv.cget("scrollregion").split()[3]) if self.cv.cget("scrollregion") else 1
                top, bot = self.cv.canvasy(0), self.cv.canvasy(self.cv.winfo_height())
                if y0 < top:
                    self.cv.yview_moveto(max(0, (y0 - 8) / total))
                elif y1 > bot:
                    self.cv.yview_moveto(max(0, (y1 + 8 - self.cv.winfo_height()) / total))
                return

    # ================================================================ selection
    def select_ids(self, ids: List[int], see: bool = False, anchor: bool = True):
        self.selected = list(dict.fromkeys(ids))
        if anchor:
            self.anchor = self.selected[0] if self.selected else None
        mode = self._effective_mode()
        self._sel_lock = True
        try:
            if mode in ("list", "chrono"):
                tv = self.lst if mode == "list" else self.chr
                iids = [f"i:{i}" for i in self.selected if tv.exists(f"i:{i}")]
                tv.selection_set(iids)
                if iids:
                    tv.focus(iids[0])
                    if see:
                        tv.see(iids[0])
            elif mode == "cards":
                for x0, y0, x1, y1, i in self.card_boxes:
                    on = i in self.selected
                    for it in self.cv.find_withtag("card"):
                        pass
                    rid = next((o for o in self.cv.find_withtag(f"c{i}") if "card" in self.cv.gettags(o)), None)
                    if rid:
                        self.cv.itemconfigure(rid, outline=C["HI"] if on else C["LINE"], width=3 if on else 1)
                if see and self.selected:
                    self._card_see(self.selected[0])
            elif mode == "results":
                self._results_mark()
        finally:
            self.after_idle(lambda: setattr(self, "_sel_lock", False))
        self.cur_item = self.selected[0] if len(self.selected) == 1 else None
        self._schedule_detail()

    def _tv_selected(self, e):
        if getattr(self, "_sel_lock", False):
            return
        tv = e.widget
        ids = [int(i[2:]) for i in tv.selection() if i.startswith("i:")]
        if ids != self.selected:
            self.selected = ids
            if len(ids) == 1:
                self.anchor = ids[0]
            self.cur_item = ids[0] if len(ids) == 1 else None
            self._schedule_detail()

    def _schedule_detail(self):
        if self.detail_job:
            self.after_cancel(self.detail_job)
        self.detail_job = self.after(40, self.update_detail)

    def select_all(self):
        if self.cur_view == "v:trash":
            self.trv.selection_set(self.trv.get_children(""))
            return
        self.select_ids([r["id"] for r in (self.results if self.cur_view == "search" else self.visible)])

    def _tv_press(self, e):
        tv = e.widget
        row = tv.identify_row(e.y)
        if not row.startswith("i:"):
            self.press = None
            return
        iid = int(row[2:])
        if iid in self.selected and not (e.state & 0x5):
            self.press = {"x": e.x_root, "y": e.y_root, "ids": list(self.selected), "src": "items"}
            if len(self.selected) > 1:
                return "break"
        else:
            self.press = {"x": e.x_root, "y": e.y_root, "ids": None, "src": "items"}

    def _tv_double(self, e):
        row = e.widget.identify_row(e.y)
        if row.startswith("i:"):
            self.open_item(int(row[2:]))
            return "break"

    def _tv_menu(self, e):
        tv = e.widget
        row = tv.identify_row(e.y)
        if row.startswith("i:"):
            iid = int(row[2:])
            if iid not in self.selected:
                self.select_ids([iid])
            self.item_menu(e)
        else:
            self.view_menu(e)

    def open_selected(self):
        if self.cur_item:
            self.open_item(self.cur_item)
        elif self.selected:
            self.open_reader()

    # ================================================================ recherche
    def _update_placeholder(self):
        if self.v_search.get():
            self.l_ph.place_forget()
        else:
            self.l_ph.place(in_=self.e_search, x=2, rely=0.5, anchor="w")

    def _search_changed(self):
        self._update_placeholder()
        if getattr(self, "_search_lock", False):
            return
        if self.search_job:
            self.after_cancel(self.search_job)
        self.search_job = self.after(220, self.do_search)

    def focus_search(self):
        self.e_search.focus_set()
        self.e_search.select_range(0, "end")

    def search_for(self, txt: str):
        self.v_search.set(txt.strip())
        self.focus_search()

    def clear_search(self):
        if self.v_search.get():
            self.v_search.set("")
        if self.cur_view == "search":
            self.open_view(self.view_before_search if self._view_valid(self.view_before_search) else "v:all")
        self._focus_items()

    def do_search(self, keep: Optional[List[int]] = None):
        self.search_job = None
        q = self.v_search.get().strip()
        if not q:
            if self.cur_view == "search":
                self.open_view(self.view_before_search if self._view_valid(self.view_before_search) else "v:all")
            return
        if self.cur_view != "search":
            self._commit_pending()
            self.view_before_search = self.cur_view
            self.cur_view = "search"
            self._tree_lock = True
            self.tree.selection_remove(self.tree.selection())
            self._tree_lock = False
            sc = self.view_before_search.startswith("s:")
            self.cb_scope.configure(values=["Partout"] + ([f"Dans « {self.store.subject(self.view_before_search[2:])['name']} »"] if sc else []))
            self.cb_scope.current(0)
            self._show_view_widget()
        sids = None
        if self.cb_scope.current() == 1 and self.view_before_search.startswith("s:"):
            sid = int(self.view_before_search[2:])
            sids = [sid] + self.store.descendants(sid)
        typ = self._filter_type()
        t0 = time.time()
        self.results = self.store.search(q, [typ] if typ else None, sids, self._filter_tag(), self._period_since())
        self.terms = [t for t in re.findall(r"[\w'-]+", q, re.UNICODE) if len(t) >= 2] or [q]
        self.visible = self.results
        self._header()
        self.fill_results()
        self.set_status(f"{len(self.results)} résultat(s) pour « {q} » en {int((time.time() - t0) * 1000)} ms"
                        "   ·   Entrée ou ↓ pour parcourir, double-clic pour ouvrir, Échap pour quitter la recherche.", "DIM")
        ids = {r["id"] for r in self.results}
        keep = [i for i in (keep or []) if i in ids]
        if keep:
            self.select_ids(keep, see=True)
        else:
            self.selected = []
            self.cur_item = None
            self.update_detail()

    def _hl_insert(self, t: tk.Text, text: str, base_tags: Tuple[str, ...]):
        """Insere text en surlignant les termes de recherche (sans accents)."""
        if not text:
            return
        nt = norm(text)
        spans: List[Tuple[int, int]] = []
        if len(nt) == len(text):
            for term in self.terms:
                nterm = norm(term)
                if not nterm:
                    continue
                start = 0
                while True:
                    k = nt.find(nterm, start)
                    if k < 0:
                        break
                    spans.append((k, k + len(nterm)))
                    start = k + len(nterm)
        spans.sort()
        pos = 0
        for a, b in spans:
            if a < pos:
                continue
            t.insert("end", text[pos:a], base_tags)
            t.insert("end", text[a:b], base_tags + ("hl",))
            pos = b
        t.insert("end", text[pos:], base_tags)

    def fill_results(self):
        t = self.rt
        t.configure(state="normal")
        t.delete("1.0", "end")
        for tg in t.tag_names():
            if tg.startswith("r:"):
                t.tag_delete(tg)
        if not self.results:
            t.insert("end", "\nAucun résultat.\n\nEssaie un autre mot, moins de mots, ou enlève les filtres.\n"
                            "La recherche ignore les accents et les majuscules ; « plant » trouve aussi « plantes ».", "rnone")
        for r in self.results:
            tg = f"r:{r['id']}"
            ty = TYPES.get(r["type"], TYPES["file"])
            pre = ("📌" if r.get("pinned") else "") + ("★ " if r.get("fav") else "")
            self._hl_insert(t, f"{pre}{ty['icon']}  {r.get('title') or '(sans titre)'}", ("rtitle", tg))
            t.insert("end", "   " + self.store.subject_path(r["subject_id"]) + "\n", ("rsub", tg))
            snip = r.get("snip") or ""
            if snip and "\x01" in snip:
                parts = re.split(r"(\x01[^\x02]*\x02)", snip.replace("\n", " "))
                for p in parts:
                    if p.startswith("\x01"):
                        t.insert("end", p.strip("\x01\x02"), ("rsnip", tg, "hl"))
                    else:
                        t.insert("end", p, ("rsnip", tg))
                t.insert("end", "\n", ("rsnip", tg))
            else:
                txt = (r.get("body_text") or self.store.meta(r).get("description") or r.get("extracted") or r.get("url") or "")
                txt = re.sub(r"\s+", " ", txt).strip()
                if txt:
                    k = -1
                    nt = norm(txt)
                    for term in self.terms:
                        k = nt.find(norm(term))
                        if k >= 0:
                            break
                    a = max(0, k - 60) if k > 0 else 0
                    frag = ("…" if a else "") + txt[a:a + 220] + ("…" if len(txt) > a + 220 else "")
                    self._hl_insert(t, frag, ("rsnip", tg))
                    t.insert("end", "\n", ("rsnip", tg))
            meta = f"{ty['label']} · {self._row_date(r)}"
            if r.get("tags"):
                meta += "  ·  " + "  ".join("#" + x for x in tag_list(r["tags"]))
            t.insert("end", meta + "\n", ("rmeta", tg))
        t.configure(state="disabled")
        t.yview_moveto(0)

    def _result_at(self, e) -> Optional[int]:
        idx = self.rt.index(f"@{e.x},{e.y}")
        for tg in self.rt.tag_names(idx):
            if tg.startswith("r:"):
                return int(tg[2:])
        return None

    def _results_mark(self):
        t = self.rt
        t.tag_remove("rsel", "1.0", "end")
        for i in self.selected:
            r = t.tag_ranges(f"r:{i}")
            if r:
                t.tag_add("rsel", r[0], r[-1])
        if self.selected:
            r = t.tag_ranges(f"r:{self.selected[0]}")
            if r:
                t.see(r[0])
                t.see(r[-1])
                t.see(r[0])

    def _result_click(self, e):
        self.rt.focus_set()
        iid = self._result_at(e)
        if iid:
            if e.state & 0x4:
                cur = list(self.selected)
                cur.remove(iid) if iid in cur else cur.append(iid)
                self.select_ids(cur, anchor=False)
            else:
                self.select_ids([iid])
            self.press = {"x": e.x_root, "y": e.y_root, "ids": list(self.selected), "src": "items"}
        return "break"

    def _result_double(self, e):
        iid = self._result_at(e)
        if iid:
            self.open_item(iid)
        return "break"

    def _result_menu(self, e):
        iid = self._result_at(e)
        if iid:
            if iid not in self.selected:
                self.select_ids([iid])
            self.item_menu(e)
        return "break"

    def _result_key(self, e):
        ks = e.keysym
        ids = [r["id"] for r in self.results]
        if ks in ("Up", "Down") and ids:
            cur = ids.index(self.selected[0]) if self.selected and self.selected[0] in ids else -1
            n = max(0, min(len(ids) - 1, cur + (1 if ks == "Down" else -1)))
            if ks == "Up" and cur <= 0:
                self.e_search.focus_set()
                return "break"
            self.select_ids([ids[n]])
            return "break"
        if ks in ("Prior", "Next", "Home", "End"):
            return None
        if ks == "Return" and self.selected:
            self.open_item(self.selected[0])
            return "break"
        if ks == "Escape":
            self.clear_search()
            return "break"
        if ks == "Delete":
            self.delete_selected()
            return "break"
        if e.state & 0x4:
            return None
        if e.char and e.char.isprintable() and len(e.char) == 1:
            return self._type_to_search(e)
        return "break"

    # ================================================================ corbeille (vue)
    def fill_trash(self):
        tv = self.trv
        tv.delete(*tv.get_children(""))
        subs, its = self.store.trash_list()
        batch_subj = {s["del_batch"]: s for s in subs if s.get("del_batch")}
        n = 0
        for s in subs:
            par = self.store.subject(s["parent_id"]) if s["parent_id"] else None
            nits = sum(1 for r in its if r.get("del_batch") == s["del_batch"])
            tv.insert("", "end", iid=f"ts:{s['id']}", text=f"{s['icon'] or '📁'}  {s['name']}",
                      values=(f"Sujet ({nits} fiche{'s' if nits > 1 else ''})", fmt_date(s["deleted"]),
                              self.store.subject_path(par["id"]) if par else "(racine)"))
            n += 1
        for r in its:
            if r.get("del_batch") in batch_subj:
                continue
            ty = TYPES.get(r["type"], TYPES["file"])
            tv.insert("", "end", iid=f"ti:{r['id']}", text=f"{ty['icon']}  {r.get('title') or '(sans titre)'}",
                      values=(ty["label"], fmt_date(r["deleted"]), self.store.subject_path(r["subject_id"])))
            n += 1
        self._trash_count = n
        self._empty_hint(tv, n == 0)
        if n == 0:
            tv._hint.configure(text="La corbeille est vide.")

    _trash_count = 0

    def _trash_sel(self) -> Tuple[List[Dict[str, Any]], List[int]]:
        subs, items = [], []
        for i in self.trv.selection():
            if i.startswith("ts:"):
                r = self.store.q("SELECT * FROM subjects WHERE id=?", (int(i[3:]),))
                if r:
                    subs.append(dict(r[0]))
            elif i.startswith("ti:"):
                items.append(int(i[3:]))
        return subs, items

    def trash_restore(self):
        subs, items = self._trash_sel()
        if not subs and not items:
            self.set_status("Choisis d'abord un élément de la corbeille.", "WARN")
            return
        n = 0
        for s in subs:
            n += self.store.restore_batch(s["del_batch"])
        n += self.store.restore_items(items)
        self.refresh_tree()
        self.refresh_items()
        self.set_status(f"♻ {n} élément(s) restauré(s).", "OK")

    def trash_purge(self):
        subs, items = self._trash_sel()
        if not subs and not items:
            return
        if not messagebox.askyesno(APP_NAME, f"Supprimer définitivement {len(subs) + len(items)} élément(s) ?\n"
                                             "Les fichiers copiés dans le Grimoire seront effacés.\nCette action est irréversible.",
                                   parent=self, icon="warning"):
            return
        n = self.store.purge_items(items)
        for s in subs:
            n += self.store.empty_trash(s["del_batch"])
        self.refresh_tree()
        self.refresh_items()
        self.set_status(f"✖ {n} élément(s) supprimé(s) définitivement.", "OK")

    def trash_empty(self):
        if not self._trash_count:
            return
        if not messagebox.askyesno(APP_NAME, f"Vider la corbeille ({self._trash_count} élément(s)) ?\n"
                                             "Cette action est irréversible (une sauvegarde est faite avant).",
                                   parent=self, icon="warning"):
            return
        self.store.backup(force=True, tag="avant_vidage")
        n = self.store.empty_trash()
        self.undo_stack = [u for u in self.undo_stack if not u[0].startswith("suppression")]
        self.refresh_tree()
        self.refresh_items()
        self.set_status(f"🧹 Corbeille vidée ({n} fiche(s)).", "OK")

    # ================================================================ panneau de droite
    def _commit_pending(self):
        try:
            self.editor.flush()
        except Exception:
            pass
        if self._detail_mode == "item" and getattr(self, "editor_item", None):
            self._title_commit()
            self._tags_commit()
            self._info_commit()

    def update_detail(self):
        self.detail_job = None
        if self.cur_view == "v:trash":
            self._show_home_trash()
            return
        if len(self.selected) == 1:
            it = self.store.item(self.selected[0])
            if it and not it.get("deleted"):
                self.show_item(it)
                return
        if len(self.selected) > 1:
            self.show_multi()
            return
        self.show_home()

    def _right_mode(self, mode: str):
        if mode == self._detail_mode:
            return
        if self._detail_mode == "item":
            self._commit_pending()
        self.f_item.pack_forget()
        self.f_home.pack_forget()
        if mode == "item":
            self.f_item.pack(fill="both", expand=True)
        else:
            self.f_home.pack(fill="both", expand=True)
            self.editor_item = None
        self._detail_mode = mode

    def _panel_w(self) -> int:
        w = self.f_right.winfo_width()
        return max(300, w if w > 50 else 420)

    # ------------------------------------------------------------ accueil d'un sujet / d'une vue
    def show_home(self):
        self._right_mode("home")
        sf = self.f_home
        sf.clear()
        f = sf.inner
        st = self.store
        W = self._panel_w() - 40
        v = self.cur_view if self.cur_view != "search" else self.view_before_search
        if self.cur_view == "search":
            mk_label(f, "🔍 Recherche", "HI", "GTitle").pack(anchor="w", padx=14, pady=(14, 4))
            mk_label(f, f"{len(self.results)} résultat(s). Choisis une fiche pour la voir ici.\n\n"
                        "Astuces :\n• plusieurs mots = toutes les fiches qui contiennent tous ces mots\n"
                        "• les accents et majuscules sont ignorés\n• le texte des PDF, des pages capturées, des images (OCR) "
                        "et des mémos transcrits est aussi cherché\n• filtre par type, étiquette ou période au-dessus de la liste",
                     "TEXT", "GUI", wraplength=W, justify="left").pack(anchor="w", padx=14)
            return
        if v.startswith("s:") and st.subject(v[2:]):
            s = st.subject(v[2:])
            sid = s["id"]
            hd = tk.Frame(f, bg=C["PANEL"])
            hd.pack(fill="x", padx=12, pady=(12, 2))
            tk.Label(hd, text=s["icon"] or "📁", bg=C["PANEL"], fg=C["HI"], font=fnt("EmojiBig")).pack(side="left")
            tk.Label(hd, text=self.fit_text(s["name"], "GBig", W - 70, 2), bg=C["PANEL"], fg=s["color"] or C["HI"],
                     font=fnt("GBig"), justify="left").pack(side="left", padx=8)
            path = st.subject_path(sid)
            if " › " in path:
                mk_label(f, "dans " + path.rsplit(" › ", 1)[0], "DIM", "GSM", wraplength=W, justify="left").pack(anchor="w", padx=14)
            if s.get("description"):
                mk_label(f, s["description"], "TEXT", "GUI", wraplength=W, justify="left").pack(anchor="w", padx=14, pady=(6, 2))
            sids = [sid] + st.descendants(sid)
            items = st.items_in(sids)
            by: Dict[str, int] = {}
            for r in items:
                by[r["type"]] = by.get(r["type"], 0) + 1
            line = "  ".join(f"{TYPES[k]['icon']} {by[k]}" for k in TYPE_ORDER if by.get(k))
            mk_label(f, f"{len(items)} fiche(s)" + (f"  ·  {len(sids) - 1} sous-sujet(s)" if len(sids) > 1 else ""), "FG", "GUIB").pack(
                anchor="w", padx=14, pady=(10, 0))
            if line:
                mk_label(f, line, "TEXT", "GUI", wraplength=W, justify="left").pack(anchor="w", padx=14)
            mk_label(f, "AJOUTER ICI", "HI", "GHead").pack(anchor="w", padx=14, pady=(14, 4))
            g = tk.Frame(f, bg=C["PANEL"])
            g.pack(fill="x", padx=12)
            acts = [("📝 Note", self.new_note), ("🔗 Lien", self.add_link_dialog), ("❝ Citation", self.add_quote_dialog),
                    ("🖼 Image", lambda: self.add_files_dialog("image")), ("📄 Document", lambda: self.add_files_dialog("document")),
                    ("🎙 Mémo", self.record_memo), ("📎 Fichier", lambda: self.add_files_dialog(None)),
                    ("📋 Coller", self.smart_paste)]
            ncol = 2 if W < 420 else 4
            for k, (txt, cmd) in enumerate(acts):
                b = mk_button(g, txt, cmd)
                b.grid(row=k // ncol, column=k % ncol, sticky="we", padx=2, pady=2)
            for c in range(ncol):
                g.columnconfigure(c, weight=1)
            tf = tk.Frame(f, bg=C["PANEL"])
            tf.pack(fill="x", padx=12, pady=(6, 0))
            mk_label(tf, "📋 Fiche modèle :", "FG", "GUI").pack(side="left")
            names = list(self.all_templates())
            cb = ttk.Combobox(tf, values=names, state="readonly", font=fnt("GUI"), width=22)
            cb.pack(side="left", padx=6, fill="x", expand=True)
            cb.set("choisir…")
            cb.bind("<<ComboboxSelected>>", lambda _e: self.new_note(template=cb.get()))
            Tooltip(cb, "Créer une fiche déjà structurée : source, protocole, plante, recette, livre, journal de recherche…")
            mk_label(f, "SUJET", "HI", "GHead").pack(anchor="w", padx=14, pady=(14, 4))
            g2 = tk.Frame(f, bg=C["PANEL"])
            g2.pack(fill="x", padx=12)
            acts2 = [("✏ Modifier…", lambda: self.edit_subject(sid)), ("📂 Sous-sujet…", lambda: self.new_subject(sid)),
                     ("🌐 Exporter…", lambda: self.export_dialog(sid, False)), ("📖 Lire tout", self.open_reader)]
            for k, (txt, cmd) in enumerate(acts2):
                mk_button(g2, txt, cmd).grid(row=k // 2, column=k % 2, sticky="we", padx=2, pady=2)
            g2.columnconfigure(0, weight=1)
            g2.columnconfigure(1, weight=1)
            kids = st.children(sid)
            if kids:
                mk_label(f, "SOUS-SUJETS", "HI", "GHead").pack(anchor="w", padx=14, pady=(14, 2))
                tot = st.total_counts()
                for k in kids:
                    mk_link(f, f"{k['icon'] or '📁'} {k['name']}  ({tot.get(k['id'], 0)})", "", bg=C["PANEL"],
                            cmd=lambda i=k["id"]: self.open_view(f"s:{i}")).pack(anchor="w", padx=18, pady=1)
            recent = sorted(items, key=lambda r: r.get("updated") or "", reverse=True)[:6]
            if recent:
                mk_label(f, "MODIFIÉ RÉCEMMENT", "HI", "GHead").pack(anchor="w", padx=14, pady=(14, 2))
                for r in recent:
                    mk_link(f, self.fit_text(f"{TYPES.get(r['type'], TYPES['file'])['icon']} {r['title'] or '(sans titre)'}",
                                             "GUI", W - 20), "", bg=C["PANEL"],
                            cmd=lambda i=r["id"]: self.goto_item(i)).pack(anchor="w", padx=18, pady=1)
            mk_label(f, "Astuce : glisse des fiches sur un sujet de la colonne de gauche pour les déplacer "
                        "(Ctrl en lâchant = copier). Glisse un sujet sur un autre pour le ranger dedans.",
                     "DIM", "GSM", wraplength=W, justify="left").pack(anchor="w", padx=14, pady=(16, 10))
            return
        # vues speciales
        key = v
        title = next((f"{ic}  {lab}" for k, ic, lab in SPECIAL_VIEWS if k == key), "")
        if key.startswith("t:"):
            title = f"🏷  #{key[2:]}"
        mk_label(f, title or "Grimoire", "HI", "GTitle").pack(anchor="w", padx=14, pady=(14, 4))
        expl = {"v:all": "Toutes les fiches de tous les sujets.", "v:fav": "Les fiches marquées ★ (Ctrl+D).",
                "v:pin": "Les fiches épinglées 📌 (Ctrl+P) restent en haut de leur sujet.",
                "v:recent": "Les fiches ouvertes ou modifiées récemment.",
                "v:tags": "Toutes les fiches qui ont au moins une étiquette. Déplie « Étiquettes » à gauche pour en choisir une."}
        mk_label(f, expl.get(key, f"{len(self.visible)} fiche(s) avec cette étiquette."), "TEXT", "GUI", wraplength=W,
                 justify="left").pack(anchor="w", padx=14)
        s = st.stats()
        mk_label(f, f"\n{s['items']} fiches · {s['subjects']} sujets · {s['favs']} favoris · {human_size(s['media_size'])} de fichiers",
                 "FG", "GUI", wraplength=W, justify="left").pack(anchor="w", padx=14)
        if key == "v:tags" or key.startswith("t:"):
            tags = st.all_tags()[:60]
            if tags:
                mk_label(f, "ÉTIQUETTES", "HI", "GHead").pack(anchor="w", padx=14, pady=(14, 4))
                fl = tk.Text(f, bg=C["PANEL"], relief="flat", height=8, wrap="word", highlightthickness=0, cursor="arrow",
                             font=fnt("GUI"), padx=4)
                fl.pack(fill="x", padx=12)
                fl.tag_configure("tg", foreground=C["LINK"], underline=True)
                for t, c in tags:
                    tagn = f"tag_{len(fl.tag_names())}"
                    fl.insert("end", f"#{t} ({c})", ("tg", tagn))
                    fl.tag_bind(tagn, "<Button-1>", lambda _e, tt=t: self.open_view(f"t:{tt}"))
                    fl.tag_bind(tagn, "<Enter>", lambda _e, w=fl: w.configure(cursor="hand2"))
                    fl.tag_bind(tagn, "<Leave>", lambda _e, w=fl: w.configure(cursor="arrow"))
                    fl.insert("end", "   ")
                fl.configure(state="disabled", height=min(10, max(2, int(fl.index("end-1c").split(".")[0]) + len(tags) // 4)))
        mk_label(f, "\nChoisis une fiche pour la voir ici. Double-clic ou Entrée : ouvrir. F11 : mode lecture.",
                 "DIM", "GSM", wraplength=W, justify="left").pack(anchor="w", padx=14)

    def _show_home_trash(self):
        self._right_mode("home")
        sf = self.f_home
        sf.clear()
        f = sf.inner
        W = self._panel_w() - 40
        mk_label(f, "🗑  Corbeille", "HI", "GTitle").pack(anchor="w", padx=14, pady=(14, 4))
        mk_label(f, "Les sujets et fiches supprimés restent ici jusqu'à ce que tu vides la corbeille. "
                    "« Restaurer » les remet à leur place (dans « À classer » si leur sujet n'existe plus).\n\n"
                    "Ctrl+Z annule aussi la dernière suppression.", "TEXT", "GUI", wraplength=W, justify="left").pack(anchor="w", padx=14)
        sel = self.trv.selection()
        if len(sel) == 1 and sel[0].startswith("ti:"):
            it = self.store.item(int(sel[0][3:]))
            if it:
                mk_label(f, "\n" + (it.get("title") or ""), "HI", "GUIB", wraplength=W, justify="left").pack(anchor="w", padx=14)
                txt = (it.get("body_text") or it.get("url") or self.store.meta(it).get("filename") or "")[:1200]
                mk_label(f, txt, "TEXT", "GUI", wraplength=W, justify="left").pack(anchor="w", padx=14)

    # ------------------------------------------------------------ plusieurs fiches
    def show_multi(self):
        self._right_mode("home")
        sf = self.f_home
        sf.clear()
        f = sf.inner
        W = self._panel_w() - 40
        n = len(self.selected)
        mk_label(f, f"☑  {n} fiches choisies", "HI", "GTitle").pack(anchor="w", padx=14, pady=(14, 8))
        acts = [("📁 Déplacer vers…", lambda: self.move_selected(False)), ("⧉ Copier vers…", lambda: self.move_selected(True)),
                ("🏷 Ajouter des étiquettes…", self.edit_tags), ("★ Favoris oui/non", self.toggle_fav),
                ("📌 Épingler oui/non", self.toggle_pin), ("📖 Lire en mode lecture", self.open_reader),
                ("🌐 Exporter en HTML…", self.export_selection), ("🗑 Mettre à la corbeille", self.delete_selected)]
        for txt, cmd in acts:
            mk_button(f, txt, cmd, "danger" if "corbeille" in txt else "").pack(fill="x", padx=14, pady=2)
        mk_label(f, "", "DIM").pack()
        for i in self.selected[:40]:
            it = self.store.item(i)
            if it:
                mk_label(f, self.fit_text(f"{TYPES.get(it['type'], TYPES['file'])['icon']} {it['title'] or '(sans titre)'}", "GUI", W),
                         "TEXT", "GUI").pack(anchor="w", padx=16)
        if n > 40:
            mk_label(f, f"… et {n - 40} autre(s)", "DIM", "GSM").pack(anchor="w", padx=16)

    # ------------------------------------------------------------ une fiche
    def show_item(self, it: Dict[str, Any]):
        if self._detail_mode == "item" and getattr(self, "editor_item", None) == it["id"] and getattr(self, "_shown_ver", -1) == self._item_ver(it):
            return
        if self._detail_mode == "item" and getattr(self, "editor_item", None) not in (None, it["id"]):
            self._commit_pending()
            it = self.store.item(it["id"]) or it
        self._right_mode("item")
        st = self.store
        iid = it["id"]
        same = getattr(self, "editor_item", None) == iid
        self.editor_item = iid
        self._shown_ver = self._item_ver(it)
        ty = TYPES.get(it["type"], TYPES["file"])
        self.l_icon.configure(text=ty["icon"])
        self._loaded_title = it.get("title") or ""
        if self.focus_get() is not self.e_title or not same:
            self.v_title.set(self._loaded_title)
        self._loaded_tags = ", ".join(tag_list(it.get("tags") or ""))
        if self.focus_get() is not self.e_tags or not same:
            self.v_tags.set(self._loaded_tags)
        self.b_fav.configure(text="★" if it.get("fav") else "☆", fg=C["HI"] if it.get("fav") else C["BTN_FG"])
        self.b_fav._colors = (C["BTN"], C["HI"] if it.get("fav") else C["BTN_FG"], C["HI"], C["ON_HI"])
        self.b_pin.configure(fg=C["HI"] if it.get("pinned") else C["DIM"])
        self.b_pin._colors = (C["BTN"], C["HI"] if it.get("pinned") else C["DIM"], C["HI"], C["ON_HI"])
        m = st.meta(it)
        bits = [ty["label"], st.subject_path(it["subject_id"])]
        if it.get("event_date"):
            bits.append("📅 " + fmt_date(it["event_date"], False))
        bits.append("ajouté " + fmt_date(it.get("created") or ""))
        if m.get("pending"):
            bits.append("⏳ récupération en cours…")
        self.l_meta.configure(text="  ·  ".join(bits))
        # onglets
        typ = it["type"]
        note_like = typ == "note"
        self.nb.tab(self.tab_prev, state="hidden" if note_like else "normal")
        self.nb.tab(self.tab_body, text="❝ Citation" if typ == "quote" else ("📝 Note" if note_like else "📝 Notes"))
        if not same or self.editor.is_empty() and it.get("body"):
            self.editor.load(it.get("body") or "", self.terms if self.cur_view == "search" else None)
        self.fill_preview(it)
        self.fill_info(it)
        if not same:
            if note_like or (typ == "quote" and False):
                self.nb.select(self.tab_body)
            else:
                self.nb.select(self.tab_prev)
            if not it.get("opened") or (it.get("opened") or "")[:10] != today():
                st.update_item(iid, touch=False, opened=now_iso())

    def _item_ver(self, it: Dict[str, Any]) -> str:
        return f"{it.get('updated')}|{it.get('meta')}|{it.get('thumb')}|{it.get('fav')}|{it.get('pinned')}|{it.get('subject_id')}|{len(it.get('extracted') or '')}"

    def refresh_item_view(self, iid: int):
        """Une fiche a change (enrichissement, OCR…) : met a jour sa ligne et le panneau si elle est affichee."""
        it = self.store.item(iid)
        if not it:
            return
        for k, r in enumerate(self.visible):
            if r["id"] == iid:
                self.visible[k] = it
                break
        mode = self._effective_mode()
        if mode == "list" and self.lst.exists(f"i:{iid}"):
            s = self.store.subject(it["subject_id"])
            self.lst.item(f"i:{iid}", values=(self._row_title(it), s["name"] if s else "", self._row_date(it),
                                              ", ".join(tag_list(it.get("tags") or ""))), tags=("fav",) if it.get("fav") else ())
        elif mode == "chrono" and self.chr.exists(f"i:{iid}"):
            self.chr.item(f"i:{iid}", text=self._row_title(it))
        elif mode == "cards":
            if getattr(self, "_cards_job", None):
                self.after_cancel(self._cards_job)
            self._cards_job = self.after(150, lambda: (self.fill_cards(), self.select_ids(self.selected) if self.selected else None))
        if self._detail_mode == "item" and getattr(self, "editor_item", None) == iid:
            self.show_item(it)

    def _tab_changed(self):
        try:
            cur = self.nb.select()
        except tk.TclError:
            return
        if cur == str(self.tab_body):
            pass

    def _section(self, f, text: str):
        mk_label(f, text, "HI", "GHead", bg=C["PANEL"]).pack(anchor="w", padx=12, pady=(12, 3))

    def _btn_row(self, f, acts: List[Tuple[str, Callable, str]]):
        W = self._panel_w() - 30
        row = tk.Frame(f, bg=C["PANEL"])
        row.pack(fill="x", padx=10, pady=2)
        used = 0
        for txt, cmd, tip in acts:
            b = mk_button(row, txt, cmd, tip=tip)
            need = b.winfo_reqwidth() + 4
            if used + need > W and used:
                row = tk.Frame(f, bg=C["PANEL"])
                row.pack(fill="x", padx=10, pady=2)
                used = 0
                b.destroy()
                b = mk_button(row, txt, cmd, tip=tip)
            b.pack(side="left", padx=2)
            used += need
        return row

    def fill_preview(self, it: Dict[str, Any]):
        sf = self.tab_prev
        y = sf.canvas.yview()[0] if getattr(self, "_prev_item", None) == it["id"] else 0
        self._prev_item = it["id"]
        sf.clear()
        f = sf.inner
        st = self.store
        m = st.meta(it)
        W = self._panel_w() - 40
        typ = it["type"]
        url = it.get("url") or ""
        fpath = Paths.abs(it.get("file") or "")
        self._prev_imgs: List[Any] = []
        if typ == "quote":
            txt = it.get("body_text") or ""
            q = tk.Frame(f, bg=C["PANEL"])
            q.pack(fill="x", padx=12, pady=(12, 4))
            tk.Frame(q, bg=C["QUOTE"], width=4).pack(side="left", fill="y")
            tk.Label(q, text=f"« {txt.strip()} »", bg=C["PANEL"], fg=C["TEXT"], font=fnt("RI"), wraplength=W - 30,
                     justify="left").pack(side="left", padx=10, pady=4)
            src = " — " + ", ".join(x for x in (it.get("author"), it.get("source"), m.get("page") and f"p. {m.get('page')}",
                                                it.get("event_date")) if x)
            if src.strip(" —"):
                mk_label(f, src, "FG", "GUI", bg=C["PANEL"], wraplength=W, justify="left").pack(anchor="w", padx=14)
            if url:
                mk_link(f, url, url, bg=C["PANEL"], wrap=W).pack(anchor="w", padx=14, pady=2)
            self._btn_row(f, [("📋 Copier avec la source", lambda: self.copy_citation(it["id"]), "Texte + auteur + source, prêt à coller"),
                              ("✏ Modifier", lambda: self.nb.select(self.tab_body), "Modifier le texte de la citation")])
            return
        img_src = it.get("thumb") or ""
        if typ == "image" and fpath and os.path.isfile(fpath):
            img_src = it.get("file")
        if img_src:
            ph = self.photo(img_src, W, 340 if typ == "image" else 240)
            if ph is not None:
                lab = tk.Label(f, image=ph, bg=C["PANEL"], cursor="hand2", bd=0)
                lab.pack(anchor="w", padx=12, pady=(10, 4))
                self._prev_imgs.append(ph)
                if typ == "image":
                    lab.bind("<Button-1>", lambda _e: self.view_image(it["id"]))
                    Tooltip(lab, "Clic : visionneuse (zoom, rotation, plein écran)")
                elif url:
                    lab.bind("<Button-1>", lambda _e: open_url(url))
                    Tooltip(lab, "Clic : ouvrir dans le navigateur")
        elif typ not in ("link", "video") or not url:
            tk.Label(f, text=TYPES.get(typ, TYPES["file"])["icon"], bg=C["PANEL"], fg=C["FG"], font=fnt("EmojiBig")).pack(
                anchor="w", padx=14, pady=(12, 0))
        if url:
            mk_link(f, url, url, bg=C["PANEL"], wrap=W, font_name="GSM").pack(anchor="w", padx=14, pady=(4, 2))
            if m.get("site") or it.get("author"):
                mk_label(f, " · ".join(x for x in (m.get("site"), it.get("author")) if x), "DIM", "GSM", bg=C["PANEL"],
                         wraplength=W, justify="left").pack(anchor="w", padx=14)
        desc = m.get("description") or ""
        if desc:
            mk_label(f, desc[:1500], "TEXT", "GUI", bg=C["PANEL"], wraplength=W, justify="left").pack(anchor="w", padx=14, pady=(6, 2))
        if m.get("fetch_error") and typ in ("link", "video"):
            mk_label(f, "⚠ Infos non récupérées : " + str(m["fetch_error"])[:200], "WARN", "GSM", bg=C["PANEL"], wraplength=W,
                     justify="left").pack(anchor="w", padx=14, pady=2)
        if fpath:
            exists = os.path.isfile(fpath)
            name = m.get("filename") or os.path.basename(fpath)
            info = [name]
            if m.get("size"):
                info.append(human_size(m["size"]))
            if m.get("pages"):
                info.append(f"{m['pages']} page(s)")
            if m.get("width"):
                info.append(f"{m['width']}×{m['height']} px")
            if m.get("duration"):
                info.append(fmt_dur(m["duration"]))
            if exists:
                mk_link(f, "  ·  ".join(info), fpath, bg=C["PANEL"], wrap=W).pack(anchor="w", padx=14, pady=(6, 2))
            else:
                mk_label(f, "⚠ Fichier introuvable : " + fpath, "ERR", "GSM", bg=C["PANEL"], wraplength=W, justify="left").pack(
                    anchor="w", padx=14, pady=(6, 2))
        # boutons
        acts: List[Tuple[str, Callable, str]] = []
        if typ in ("audio", "voice") or (typ == "video" and fpath and os.path.splitext(fpath)[1].lower() in AUDIO_EXT):
            self._player_row(f, it)
        if url:
            acts.append(("🌐 Ouvrir", lambda: open_url(url), "Ouvrir dans le navigateur"))
            acts.append(("📋 Copier le lien", lambda: (copy_to_clipboard(self, url), self.set_status("Lien copié.", "OK")), ""))
        if fpath and os.path.isfile(fpath):
            if typ == "image":
                acts.append(("🔍 Visionneuse", lambda: self.view_image(it["id"]), "Zoom, rotation, image suivante"))
            acts.append(("📂 Ouvrir", lambda: open_path(fpath), "Ouvrir avec le programme de Windows"))
            acts.append(("🗂 Dossier", lambda: reveal_in_explorer(fpath), "Montrer le fichier dans l'Explorateur"))
        if typ in ("link", "video") and url:
            acts.append(("↻ Infos", lambda: self.refetch(it["id"]), "Récupérer à nouveau titre, description et miniature"))
            acts.append(("🌐 Capturer la page", lambda: self.capture_item(it["id"]), "Copie complète hors ligne : HTML + PDF + image"))
        if typ == "video" and url:
            acts.append(("📦 Envoyer à l'Archiveur", lambda: self.send_to_archiveur(url), "Copie le lien et ouvre l'Archiveur 5"))
        if typ == "image" and fpath:
            acts.append(("🔤 Lire le texte (OCR)", lambda: self.ocr_item(it["id"]), "Reconnaissance de texte Windows"))
        if typ in ("voice", "audio") and fpath:
            acts.append(("📝 Transcrire", lambda: self.transcribe_item(it["id"]), "Transcription locale (faster-whisper)"))
        if typ == "document" and fpath:
            acts.append(("↻ Extraire le texte", lambda: self.reextract(it["id"]), "Relire le texte du document"))
        if acts:
            self._btn_row(f, acts)
        extra = m.get("extra_files") or []
        if extra:
            self._section(f, "COPIE DE LA PAGE")
            for rel in extra:
                p = Paths.abs(rel)
                lab = {".html": "🌐 Page hors ligne (HTML)", ".pdf": "📄 PDF de la page", ".png": "🖼 Image de la page"}.get(
                    os.path.splitext(p)[1].lower(), "📎 " + os.path.basename(p))
                if os.path.isfile(p):
                    mk_link(f, lab, p, bg=C["PANEL"]).pack(anchor="w", padx=18, pady=1)
        ext = it.get("extracted") or ""
        if ext and not (typ in ("link", "video") and ext.strip() == desc.strip()):
            title = {"image": "TEXTE LU DANS L'IMAGE (OCR)", "voice": "TRANSCRIPTION", "audio": "TRANSCRIPTION",
                     "page": "TEXTE DE LA PAGE"}.get(typ, "TEXTE DU DOCUMENT")
            self._section(f, f"{title}  ({len(ext.split())} mots)")
            box = tk.Frame(f, bg=C["PANEL"])
            box.pack(fill="x", padx=12, pady=(0, 8))
            t = tk.Text(box, bg=C["ENTRY_BG"], fg=C["ENTRY_FG"], font=fnt("GUI"), wrap="word", relief="flat", height=14,
                        padx=8, pady=6, highlightthickness=1, highlightbackground=C["LINE"], selectbackground=C["SEL"],
                        selectforeground=C["ON_SEL"])
            sb = ttk.Scrollbar(box, orient="vertical", command=t.yview)
            t.configure(yscrollcommand=sb.set)
            t.pack(side="left", fill="x", expand=True)
            sb.pack(side="right", fill="y")
            t.insert("1.0", ext[:300000])
            configure_rich_tags(t)
            relink(t, self.terms if self.cur_view == "search" else None)
            t.configure(state="disabled")
            t.bind("<1>", lambda _e, w=t: w.focus_set())
            if self.cur_view == "search":
                r = t.tag_nextrange("search", "1.0")
                if r:
                    t.see(r[0])
        try:
            self.gx_link_section(f, it, W)
        except Exception:
            logger.error("aperçus de liens : %s", traceback.format_exc())
        self.after_idle(lambda: sf.canvas.yview_moveto(y))

    def _player_row(self, f, it: Dict[str, Any]):
        fpath = Paths.abs(it.get("file") or "")
        m = self.store.meta(it)
        row = tk.Frame(f, bg=C["PANEL"])
        row.pack(fill="x", padx=10, pady=(8, 2))
        playing_this = self.player_item == it["id"] and self.player.playing()
        self.b_play = mk_button(row, "⏸ Pause" if playing_this else "▶ Écouter", lambda: self.play_toggle(it["id"]), "accent",
                                tip="Lecture sans fenêtre (ffplay)")
        self.b_play.pack(side="left", padx=2)
        mk_button(row, "⏪ 10 s", lambda: self.play_seek(it["id"], -10)).pack(side="left", padx=2)
        mk_button(row, "10 s ⏩", lambda: self.play_seek(it["id"], 10)).pack(side="left", padx=2)
        mk_button(row, "■", self.play_stop, tip="Arrêter").pack(side="left", padx=2)
        self.l_play = mk_label(row, "", "HI", "GUIB", bg=C["PANEL"])
        self.l_play.pack(side="left", padx=8)
        self._play_total = float(m.get("duration") or 0)
        self._update_play_label()

    def _update_play_label(self):
        try:
            if not self.l_play.winfo_exists():
                return
        except Exception:
            return
        pos = self.player.position() if self.player_item == getattr(self, "editor_item", None) else 0
        tot = getattr(self, "_play_total", 0)
        self.l_play.configure(text=f"{fmt_dur(pos)} / {fmt_dur(tot)}" if tot else fmt_dur(pos))

    def _tick_player(self):
        try:
            if self.player_item and not self.player.playing() and getattr(self, "_was_playing", False):
                self._was_playing = False
                if hasattr(self, "b_play") and self.b_play.winfo_exists():
                    self.b_play.configure(text="▶ Écouter")
            if self.player.playing():
                self._was_playing = True
            if hasattr(self, "l_play"):
                self._update_play_label()
        except Exception:
            pass
        self.after(250, self._tick_player)

    def play_toggle(self, iid: int):
        it = self.store.item(iid)
        if not it:
            return
        p = Paths.abs(it.get("file") or "")
        if self.player_item == iid and self.player.playing():
            self.player.pause()
            self.b_play.configure(text="▶ Reprendre")
            return
        start = self.player.paused_at if self.player_item == iid else 0.0
        err = self.player.play(p, start)
        if err:
            if messagebox.askyesno(APP_NAME, f"Lecture intégrée impossible : {err}\n\nOuvrir avec le lecteur de Windows ?", parent=self):
                open_path(p)
            return
        self.player_item = iid
        self.b_play.configure(text="⏸ Pause")

    def play_seek(self, iid: int, d: float):
        if self.player_item != iid:
            return self.play_toggle(iid)
        pos = max(0.0, self.player.position() + d)
        it = self.store.item(iid)
        if it:
            self.player.play(Paths.abs(it.get("file") or ""), pos)
            self.b_play.configure(text="⏸ Pause")

    def play_stop(self):
        self.player.stop()
        try:
            self.b_play.configure(text="▶ Écouter")
        except Exception:
            pass

    # ------------------------------------------------------------ onglet Fiche
    def fill_info(self, it: Dict[str, Any]):
        sf = self.tab_info
        sf.clear()
        f = sf.inner
        st = self.store
        W = self._panel_w() - 40
        m = st.meta(it)
        g = tk.Frame(f, bg=C["PANEL"])
        g.pack(fill="x", padx=8, pady=(10, 4))
        g.columnconfigure(1, weight=1)
        self.info_vars: Dict[str, tk.StringVar] = {}
        rows = [("source", "Source", "Livre, site, émission, personne…"), ("author", "Auteur", ""),
                ("event_date", "Date de l'info", "AAAA-MM-JJ : sert à la chronologie"), ("url", "Lien", "")]
        r = 0
        for key, lab, hint in rows:
            mk_label(g, lab, "HI", "GSMB", bg=C["PANEL"]).grid(row=r, column=0, sticky="w", padx=(4, 8), pady=3)
            v = tk.StringVar(value=it.get(key) or "")
            e = mk_entry(g, v, 20, "GSM")
            e.grid(row=r, column=1, sticky="we", pady=3, ipady=2)
            e.bind("<FocusOut>", lambda _e: self._info_commit())
            e.bind("<Return>", lambda _e: self._info_commit())
            e.bind("<Control-KeyPress>", self._entry_ctrl)
            if hint:
                Tooltip(e, hint)
            self.info_vars[key] = v
            r += 1
        if it["type"] == "quote":
            mk_label(g, "Page", "HI", "GSMB", bg=C["PANEL"]).grid(row=r, column=0, sticky="w", padx=(4, 8), pady=3)
            v = tk.StringVar(value=str(m.get("page") or ""))
            e = mk_entry(g, v, 20, "GSM")
            e.grid(row=r, column=1, sticky="we", pady=3, ipady=2)
            e.bind("<FocusOut>", lambda _e: self._info_commit())
            self.info_vars["page"] = v
            r += 1
        self._info_item = it["id"]
        self._section(f, "RANGEMENT")
        sp = tk.Frame(f, bg=C["PANEL"])
        sp.pack(fill="x", padx=12)
        mk_link(sp, st.subject_label(it["subject_id"]), "", bg=C["PANEL"], wrap=W - 120,
                cmd=lambda: self.open_view(f"s:{it['subject_id']}")).pack(side="left")
        mk_button(sp, "Déplacer…", lambda: self.move_selected(False), font_name="GSM").pack(side="right")
        self._section(f, "DATES")
        for lab, key in (("Ajouté", "created"), ("Modifié", "updated"), ("Ouvert", "opened")):
            if it.get(key):
                mk_label(f, f"  {lab} : {fmt_date(it[key])}", "TEXT", "GSM", bg=C["PANEL"]).pack(anchor="w", padx=12)
        fpath = Paths.abs(it.get("file") or "")
        if fpath:
            self._section(f, "FICHIER")
            mk_link(f, fpath, fpath, bg=C["PANEL"], wrap=W, font_name="GSM").pack(anchor="w", padx=14)
            if m.get("original") and m["original"] != fpath:
                mk_label(f, "Copié depuis : " + m["original"], "DIM", "GSM", bg=C["PANEL"], wraplength=W, justify="left").pack(
                    anchor="w", padx=14)
        refs = list(dict.fromkeys(x.group(1).strip() for x in REF_RE.finditer(it.get("body_text") or "")))
        self._section(f, "RÉFÉRENCES [[…]]")
        if refs:
            for t in refs[:50]:
                tgt = st.find_by_title(t)
                sid = st.find_subject(t) if not tgt else None
                mark = "" if (tgt or sid) else "  (à créer)"
                mk_link(f, f"→ {t}{mark}", "", bg=C["PANEL"], cmd=lambda tt=t: self.follow_ref(tt)).pack(anchor="w", padx=16)
        else:
            mk_label(f, "Aucune. Dans la note, [[ ]] (ou tape [[titre]]) relie une autre fiche ou un sujet.", "DIM", "GSM",
                     bg=C["PANEL"], wraplength=W, justify="left").pack(anchor="w", padx=14)
        back = st.backlinks(it)
        self._section(f, f"CITÉE DANS ({len(back)})")
        if back:
            for b in back[:50]:
                mk_link(f, f"← {b['title'] or '(sans titre)'}", "", bg=C["PANEL"], cmd=lambda i=b["id"]: self.goto_item(i)).pack(
                    anchor="w", padx=16)
        else:
            mk_label(f, "Aucune fiche ne fait référence à celle-ci.", "DIM", "GSM", bg=C["PANEL"]).pack(anchor="w", padx=14)
        self._btn_row(f, [("📋 Copier la citation", lambda: self.copy_citation(it["id"]), "Titre, auteur, source, lien et date"),
                          ("🌐 Exporter", lambda: self.export_selection([it["id"]]), "Cette fiche en page HTML autonome")])

    def _info_commit(self):
        iid = getattr(self, "_info_item", None)
        if not iid or not getattr(self, "info_vars", None):
            return
        it = self.store.item(iid)
        if not it:
            return
        upd: Dict[str, Any] = {}
        for k in ("source", "author", "event_date", "url"):
            if k in self.info_vars:
                try:
                    val = self.info_vars[k].get().strip()
                except tk.TclError:
                    return
                if k == "event_date" and val:
                    val = self._parse_date(val)
                    if val is None:
                        self.set_status("Date non comprise : écris AAAA-MM-JJ (ou AAAA, ou AAAA-MM).", "WARN")
                        continue
                if k == "url" and val:
                    val = fix_url(val)
                if val != (it.get(k) or ""):
                    upd[k] = val
        if "page" in self.info_vars:
            try:
                pg = self.info_vars["page"].get().strip()
            except tk.TclError:
                pg = None
            m = self.store.meta(it)
            if pg is not None and pg != str(m.get("page") or ""):
                m["page"] = pg
                upd["meta"] = m
        if upd:
            self.store.update_item(iid, **upd)
            self.refresh_item_view(iid)

    @staticmethod
    def _parse_date(s: str) -> Optional[str]:
        s = s.strip()
        mm = re.match(r"^(\d{4})(?:[-/.](\d{1,2})(?:[-/.](\d{1,2}))?)?$", s)
        if mm:
            y, mo, d = mm.group(1), mm.group(2), mm.group(3)
            try:
                dt.date(int(y), int(mo or 1), int(d or 1))
            except ValueError:
                return None
            return y + (f"-{int(mo):02d}" if mo else "") + (f"-{int(d):02d}" if d else "")
        mm = re.match(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})$", s)
        if mm:
            try:
                return dt.date(int(mm.group(3)), int(mm.group(2)), int(mm.group(1))).isoformat()
            except ValueError:
                return None
        return None

    # ------------------------------------------------------------ titre, etiquettes, texte
    def _title_commit(self):
        iid = getattr(self, "editor_item", None)
        if not iid:
            return
        try:
            t = self.v_title.get().strip()
        except tk.TclError:
            return
        if t == self._loaded_title or not t:
            if not t:
                self.v_title.set(self._loaded_title)
            return
        it = self.store.item(iid)
        if not it:
            return
        m = self.store.meta(it)
        m["auto_title"] = False
        self.store.update_item(iid, title=t[:300], meta=m)
        self._loaded_title = t[:300]
        self.refresh_item_view(iid)

    def _tags_commit(self):
        iid = getattr(self, "editor_item", None)
        if not iid:
            return
        try:
            t = norm_tags(self.v_tags.get())
        except tk.TclError:
            return
        if t == norm_tags(self._loaded_tags):
            return
        self.store.update_item(iid, tags=t)
        self._loaded_tags = ", ".join(tag_list(t))
        self.refresh_item_view(iid)
        self.refresh_tree()

    def _tags_autocomplete(self, e):
        if e.keysym in ("BackSpace", "Delete", "Left", "Right", "Tab", "Return", "comma", "space", "Shift_L", "Shift_R"):
            return
        txt = self.v_tags.get()
        if self.e_tags.index("insert") != len(txt):
            return
        cur = txt.split(",")[-1].strip()
        if len(cur) < 2:
            return
        for t, _c in self.store.all_tags():
            if norm(t).startswith(norm(cur)) and norm(t) != norm(cur):
                pos = len(txt)
                self.v_tags.set(txt + t[len(cur):])
                self.e_tags.icursor(pos)
                self.e_tags.select_range(pos, "end")
                break

    def _tags_tab(self, _e):
        if self.e_tags.selection_present():
            self.e_tags.selection_clear()
            self.v_tags.set(self.v_tags.get() + ", ")
            self.e_tags.icursor("end")
            return "break"
        return None

    def _editor_changed(self):
        iid = getattr(self, "editor_item", None)
        if not iid:
            return
        it = self.store.item(iid)
        if not it or it.get("deleted"):
            return
        body = self.editor.body()
        if body == (it.get("body") or "") or (not it.get("body") and self.editor.is_empty()):
            return
        upd: Dict[str, Any] = {"body": body}
        m = self.store.meta(it)
        if it["type"] == "note" and m.get("auto_title"):
            first = next((ln.strip(" #•☐☑>-") for ln in self.editor.plain().splitlines() if ln.strip(" #•☐☑>-")), "")
            if first:
                upd["title"] = first[:80]
                self._loaded_title = upd["title"]
                if self.focus_get() is not self.e_title:
                    self.v_title.set(upd["title"])
        if it["type"] == "quote" and m.get("auto_title") is not False and not it.get("author"):
            words = re.sub(r"\s+", " ", self.editor.plain()).strip()
            upd["title"] = words[:60] + ("…" if len(words) > 60 else "")
        self.store.update_item(iid, **upd)
        self._shown_ver = self._item_ver(self.store.item(iid) or it)
        self.refresh_item_view(iid)
        self.set_status("✔ Enregistré automatiquement.", "DIM")

    # ================================================================ ajouter
    def _after_add(self, ids: List[int], sid: Optional[int] = None, enrich: bool = True, msg: str = "",
                   transcribe_ids: Iterable[int] = ()):
        ids = [i for i in ids if i]
        if not ids:
            return
        st = self.store
        sid = sid or (st.item(ids[0]) or {}).get("subject_id")
        self.refresh_tree()
        shown = {r["id"] for r in self.collect_items()} if self.cur_view not in ("search", "v:trash") else set()
        if not set(ids) & shown:
            self.open_view(f"s:{sid}")
        else:
            self.refresh_items(keep=ids)
        self.select_ids(ids, see=True)
        if self.detail_job:
            self.after_cancel(self.detail_job)
        self.update_detail()
        self.set_status(msg or f"＋ {len(ids)} fiche(s) ajoutée(s) dans « {st.subject_path(sid)} ».", "OK")
        if enrich:
            ocr = bool(self.store.get("auto_ocr", False))
            for iid in ids:
                it = st.item(iid)
                if not it:
                    continue
                if it["type"] in ("link", "video") and not self.store.get("auto_fetch", True):
                    st.set_meta(iid, pending=False)
                    continue
                if it["type"] in ("link", "video") or it.get("file"):
                    self.run_job(lambda i=iid: enrich_any(st, i, ocr=ocr), lambda _r, i=iid: self._enriched(i),
                                 "récupération des infos")
        for iid in transcribe_ids:
            self.transcribe_item(iid, quiet=True)
