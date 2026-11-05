# -*- coding: utf-8 -*-
# Partie de grimoire1.py (découpage v1.2.2, comportement inchangé).
# Chargée par grimoire1.py dans un espace de noms commun : ne pas lancer seule.
from __future__ import annotations

class _GrimoireAppPartie3:
    """Méthodes de GrimoireApp (partie 3/3)."""


    def _enriched(self, iid: int):
        self.refresh_item_view(iid)
        it = self.store.item(iid)
        if it and it.get("thumb") and self._effective_mode() == "cards":
            self.img_cache = {k: v for k, v in self.img_cache.items() if k[0] != Paths.abs(it["thumb"])}

    def new_note(self, text: str = "", template: Optional[str] = None):
        sid = self.current_sid()
        title, body, auto = "Nouvelle note", "", True
        if template:
            tp = self.all_templates().get(template)
            if not tp:
                return
            body = runs_to_json(md_runs(tp[1]))
            title, auto = f"{template}", True
        elif text:
            body = runs_to_json(runs_from_any(text))
            first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
            title = first[:80] or title
        iid = self.store.add_item(sid, "note", title=title, body=body, meta={"auto_title": auto, "template": template or ""})
        self._after_add([iid], sid, enrich=False, msg=f"📝 Nouvelle note dans « {self.store.subject_path(sid)} » : écris, "
                                                     "c'est enregistré automatiquement.")
        self.nb.select(self.tab_body)
        self.editor.t.focus_set()
        if template:
            idx = self.editor.t.search(": ", "1.0", "2.0")
            self.editor.t.mark_set("insert", f"{idx}+2c" if idx else "1.end")
        else:
            self.editor.t.mark_set("insert", "end-1c")

    def add_link_dialog(self, url: str = ""):
        if not url:
            try:
                clip = self.clipboard_get().strip()
                if is_url(clip) and len(clip.split()) == 1:
                    url = clip
            except tk.TclError:
                pass
        r = LinkDialog(self, self, url).wait()
        if not r:
            return
        sid = self.current_sid()
        iid = add_url(self.store, sid, r["url"], r["title"], r["note"], r["tags"])
        self._after_add([iid], sid)
        if r.get("capture"):
            self.capture_item(iid)

    def add_urls(self, urls: List[str], sid: Optional[int] = None):
        sid = sid or self.current_sid()
        ids = [add_url(self.store, sid, u) for u in dict.fromkeys(urls)]
        self._after_add(ids, sid)

    def add_quote_dialog(self, text: str = ""):
        r = QuoteDialog(self, text).wait()
        if not r:
            return
        sid = self.current_sid()
        d = self._parse_date(r["date"]) if r.get("date") else ""
        iid = add_quote(self.store, sid, r["text"], r["author"], r["source"], r["url"], r["page"], r["tags"], d or "")
        self._after_add([iid], sid, enrich=False, msg="❝ Citation ajoutée.")

    def add_text_note(self, text: str, sid: Optional[int] = None):
        sid = sid or self.current_sid()
        ids = add_text(self.store, sid, text)
        self._after_add(ids, sid)

    def add_files_dialog(self, kind: Optional[str]):
        ft = {"image": [("Images", " ".join("*" + e for e in sorted(IMG_EXT)))],
              "document": [("Documents", " ".join("*" + e for e in sorted(DOC_EXT)))],
              "audio": [("Sons", " ".join("*" + e for e in sorted(AUDIO_EXT)))],
              "video": [("Vidéos", " ".join("*" + e for e in sorted(VIDEO_EXT)))]}.get(kind or "", []) + [("Tous les fichiers", "*.*")]
        paths = filedialog.askopenfilenames(parent=self, title="Ajouter au Grimoire", filetypes=ft,
                                            initialdir=self.store.get("last_dir", os.path.expanduser("~")))
        if paths:
            self.store.set("last_dir", os.path.dirname(paths[0]))
            self.add_paths(list(paths), None)

    def add_paths(self, paths: List[str], sid: Optional[int]):
        sid = sid or self.current_sid()
        files = [p for p in paths if os.path.isfile(p)]
        dirs = [p for p in paths if os.path.isdir(p)]
        big = sum(os.path.getsize(p) for p in files if os.path.isfile(p))
        if big > 500 * 1024 * 1024 and not messagebox.askyesno(
                APP_NAME, f"Copier {human_size(big)} de fichiers dans le Grimoire ?", parent=self):
            return
        ids: List[int] = []
        for p in files:
            try:
                ids.append(add_file(self.store, sid, p))
            except Exception as ex:
                logger.error("ajout %s : %s", p, ex)
                self.set_status(f"⚠ {os.path.basename(p)} : {ex}", "ERR")
        for d in dirs:
            if messagebox.askyesno(APP_NAME, f"Importer le dossier « {os.path.basename(d)} » et ses sous-dossiers ?\n"
                                             "(un sous-sujet est créé pour chaque dossier)", parent=self):
                got, _n = import_folder(self.store, sid, d)
                ids += got
        self._after_add(ids, sid)

    def import_folder_dialog(self, sid: Optional[int]):
        d = filedialog.askdirectory(parent=self, title="Importer un dossier dans le Grimoire",
                                    initialdir=self.store.get("last_dir", os.path.expanduser("~")))
        if not d:
            return
        sid = sid or self.current_sid()
        self.set_status("📂 Import en cours…", "WARN")
        self.update_idletasks()
        ids, n = import_folder(self.store, sid, d, progress=lambda m: (self.set_status(m, "WARN"), self.update_idletasks()))
        self._after_add(ids, sid, msg=f"📂 {len(ids)} fichier(s) importé(s) dans {n} sujet(s).")

    def record_memo(self):
        sid = self.current_sid()
        r = RecorderDialog(self, sid).wait()
        if not r:
            return
        try:
            iid = add_file(self.store, sid, r["path"], r["title"], move=True, typ="voice")
            self.store.set_meta(iid, duration=r["duration"])
        except Exception as ex:
            messagebox.showerror(APP_NAME, f"Mémo non enregistré : {ex}", parent=self)
            return
        self._after_add([iid], sid, msg=f"🎙 Mémo de {fmt_dur(r['duration'])} ajouté.",
                        transcribe_ids=[iid] if r.get("transcribe") else [])

    def smart_paste(self, plain: bool = False):
        sid = self.current_sid()
        if not plain:
            try:
                from PIL import ImageGrab  # type: ignore
                clip = ImageGrab.grabclipboard()
            except Exception:
                clip = None
            if isinstance(clip, list) and clip:
                paths = [p for p in clip if isinstance(p, str) and os.path.exists(p)]
                if paths:
                    self.add_paths(paths, sid)
                    return
            elif clip is not None and hasattr(clip, "save"):
                iid = add_image_pil(self.store, sid, clip)
                self._after_add([iid], sid, msg="🖼 Image collée.")
                return
        try:
            text = self.clipboard_get()
        except tk.TclError:
            text = ""
        if not text.strip():
            self.set_status("Le presse-papiers est vide (ou contient un format non reconnu).", "WARN")
            return
        if plain:
            first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "Note")
            iid = self.store.add_item(sid, "note", title=first[:80], body=runs_to_json([[text.strip(), []]]))
            self._after_add([iid], sid, enrich=False)
            return
        self.add_text_note(text, sid)

    # ------------------------------------------------------------ travaux de fond sur une fiche
    def refetch(self, iid: int):
        self.store.set_meta(iid, pending=True)
        self.refresh_item_view(iid)
        self.run_job(lambda: enrich_link(self.store, iid), lambda _r: self._enriched(iid), "récupération des infos")

    def reextract(self, iid: int):
        self.run_job(lambda: enrich_file(self.store, iid), lambda _r: (self._enriched(iid), self.set_status("Texte relu.", "OK")),
                     "extraction du texte")

    def ocr_item(self, iid: int):
        it = self.store.item(iid)
        if not it:
            return
        p = Paths.abs(it.get("file") or "")
        self.set_status("🔤 Lecture du texte de l'image (OCR)…", "WARN")

        def job():
            return ocr_image(p)

        def done(res):
            txt, err = res
            if txt:
                m = self.store.meta(self.store.item(iid) or {})
                m["ocr"] = now_iso()
                self.store.update_item(iid, touch=False, extracted=txt, meta=m)
                self.refresh_item_view(iid)
                self.set_status(f"🔤 {len(txt.split())} mot(s) lu(s) dans l'image : ils sont maintenant cherchables.", "OK")
            else:
                self.set_status("OCR : " + (err or "aucun texte trouvé."), "WARN")
                if err:
                    messagebox.showinfo(APP_NAME, "Lecture du texte impossible :\n" + err, parent=self)
        self.run_job(job, done, "OCR")

    def transcribe_item(self, iid: int, quiet: bool = False):
        it = self.store.item(iid)
        if not it:
            return
        if not whisper_available():
            if not quiet:
                if messagebox.askyesno(APP_NAME, WHISPER_HELP + "\n\nInstaller faster-whisper maintenant ?", parent=self):
                    self.install_whisper(confirm=False)
            return
        p = Paths.abs(it.get("file") or "")
        model = self.store.get("whisper_model", "small")
        self.set_status("📝 Transcription du mémo en cours (peut prendre un moment)…", "WARN")

        def job():
            return transcribe(p, model, progress=lambda m: self.post(lambda: self.set_status(m, "WARN")))

        def done(res):
            txt, err = res
            if txt:
                cur = self.store.item(iid) or {}
                m = self.store.meta(cur)
                m["transcribed"] = now_iso()
                m["whisper_model"] = model
                self.store.update_item(iid, touch=False, extracted=txt, meta=m)
                self.refresh_item_view(iid)
                self.set_status("📝 Transcription terminée : le texte est cherchable.", "OK")
            else:
                self.set_status("Transcription : " + (err or "aucun texte."), "WARN")
        self.run_job(job, done, "transcription")

    def capture_page_dialog(self):
        url = ""
        try:
            clip = self.clipboard_get().strip()
            if is_url(clip):
                url = clip
        except tk.TclError:
            pass
        u = ask_string(self, "Capturer une page web", "Adresse de la page à garder hors ligne (HTML + PDF + image pleine page) :", url)
        if not u or not u.strip():
            return
        sid = self.current_sid()
        iid = self.store.add_item(sid, "page", title=placeholder_title(fix_url(u.strip())), url=fix_url(u.strip()),
                                  source=domain_of(fix_url(u.strip())), meta={"pending": True, "auto_title": True})
        self._after_add([iid], sid, enrich=False, msg="🌐 Capture de la page en cours…")
        self.capture_item(iid, as_page=True)

    def capture_item(self, iid: int, as_page: bool = False):
        it = self.store.item(iid)
        if not it or not it.get("url"):
            return
        st = self.store
        url = it["url"]
        dest = os.path.join(st.subject_media_dir(it["subject_id"]), "_pages")
        self.set_status("🌐 Capture de la page (HTML, PDF, image)…", "WARN")

        def job():
            return capture_page(url, dest, it.get("title") if not st.meta(it).get("auto_title") else "",
                                progress=lambda m: self.post(lambda: self.set_status("🌐 " + m, "WARN")))

        def done(res):
            cur = st.item(iid)
            if not cur:
                return
            m = st.meta(cur)
            files = [Paths.rel(p) for p in res.get("files", [])]
            upd: Dict[str, Any] = {}
            if as_page or cur["type"] == "page":
                html_rel = Paths.rel(res["html"]) if res.get("html") else ""
                if html_rel:
                    upd["file"] = html_rel
                    files = [f for f in files if f != html_rel]
                if res.get("title") and m.get("auto_title"):
                    upd["title"] = res["title"][:300]
                if res.get("text"):
                    upd["extracted"] = res["text"]
                m["description"] = res.get("description", "") or m.get("description", "")
            else:
                if res.get("text"):
                    upd["extracted"] = ((cur.get("extracted") or "") + "\n\n" + res["text"]).strip()[:MAX_EXTRACT]
            m["extra_files"] = list(dict.fromkeys((m.get("extra_files") or []) + files))
            m["captured"] = now_iso()
            m["pending"] = False
            if res.get("png") and not cur.get("thumb"):
                try:
                    from PIL import Image  # type: ignore
                    with Image.open(res["png"]) as im:
                        crop = im.crop((0, 0, im.width, min(im.height, int(im.width * 0.66))))
                        tp = thumb_path(st, cur["subject_id"], iid)
                        if save_thumb_image(crop, tp):
                            upd["thumb"] = Paths.rel(tp)
                except Exception as ex:
                    logger.info("vignette capture : %s", ex)
            upd["meta"] = m
            st.update_item(iid, touch=False, **upd)
            self.refresh_item_view(iid)
            errs = res.get("errors") or []
            if res.get("files"):
                self.set_status(f"🌐 Page capturée ({len(res['files'])} fichier(s))" + (f" — {errs[0]}" if errs else "."),
                                "OK" if not errs else "WARN")
            else:
                self.set_status("⚠ Capture impossible : " + ("; ".join(errs) or "erreur inconnue"), "ERR")
        self.run_job(job, done, "capture de page")

    def send_to_archiveur(self, url: str):
        copy_to_clipboard(self, url)
        arch = os.path.join(padawan_dir(), "archiveur5.py")
        if not os.path.isfile(arch):
            arch = os.path.join(BASE, "archiveur5.py")
        if not os.path.isfile(arch):
            messagebox.showinfo(APP_NAME, "Lien copié. archiveur5.py est introuvable dans le dossier Padawan.", parent=self)
            return
        try:
            popen_hidden([find_pythonw(), arch], cwd=os.path.dirname(arch))
            self.set_status("📦 Lien copié et Archiveur 5 lancé : colle le lien (Ctrl+V) dans l'Archiveur.", "OK")
        except Exception as ex:
            messagebox.showerror(APP_NAME, f"Lancement de l'Archiveur impossible : {ex}", parent=self)

    def copy_citation(self, iid: int):
        it = self.store.item(iid)
        if not it:
            return
        m = self.store.meta(it)
        parts = []
        if it["type"] == "quote":
            parts.append(f"« {(it.get('body_text') or '').strip()} »")
            src = ", ".join(x for x in (it.get("author"), it.get("source"), m.get("page") and f"p. {m['page']}",
                                        it.get("event_date")) if x)
            if src:
                parts.append("— " + src)
        else:
            parts.append(", ".join(x for x in (it.get("author"), f"« {it.get('title') or ''} »", it.get("source") or m.get("site"),
                                               it.get("event_date")) if x and x != "«  »"))
        if it.get("url"):
            parts.append(f"{it['url']} (consulté le {fmt_date(today(), False)})")
        txt = "\n".join(parts)
        copy_to_clipboard(self, txt)
        self.set_status("📋 Citation copiée : " + txt.replace("\n", " ")[:120], "OK")

    # ------------------------------------------------------------ ouvrir
    def open_item(self, iid: int):
        it = self.store.item(iid)
        if not it:
            return
        typ = it["type"]
        fpath = Paths.abs(it.get("file") or "")
        if typ == "note" or typ == "quote":
            self.select_ids([iid])
            self.after(60, lambda: (self.nb.select(self.tab_body), self.editor.t.focus_set()))
        elif typ == "image" and fpath and os.path.isfile(fpath):
            self.view_image(iid)
        elif typ in ("audio", "voice") and fpath:
            self.select_ids([iid])
            self.after(60, lambda: self.play_toggle(iid))
        elif fpath and os.path.isfile(fpath):
            open_path(fpath)
        elif it.get("url"):
            open_url(it["url"])
        self.store.update_item(iid, touch=False, opened=now_iso())

    def view_image(self, iid: int):
        imgs = [r for r in (self.results if self.cur_view == "search" else self.visible)
                if r["type"] == "image" and r.get("file") and os.path.isfile(Paths.abs(r["file"]))]
        if not any(r["id"] == iid for r in imgs):
            it = self.store.item(iid)
            imgs = [it] if it else []
        if not imgs:
            return
        idx = next((k for k, r in enumerate(imgs) if r["id"] == iid), 0)
        ImageViewer(self, [(Paths.abs(r["file"]), r.get("title") or "") for r in imgs], idx)

    def open_reader(self):
        pool = self.results if self.cur_view == "search" else self.visible
        if not pool:
            self.set_status("Rien à lire dans cette vue.", "WARN")
            return
        ids = [r["id"] for r in pool]
        if len(self.selected) > 1:
            ids = [i for i in ids if i in self.selected]
            idx = 0
        else:
            idx = ids.index(self.cur_item) if self.cur_item in ids else 0
        self._commit_pending()
        ReaderWindow(self, ids, idx, self.terms if self.cur_view == "search" else None)

    def goto_item(self, iid: int):
        it = self.store.item(iid)
        if not it:
            return
        if it.get("deleted"):
            self.open_view("v:trash")
            return
        pool = {r["id"] for r in (self.results if self.cur_view == "search" else self.visible)}
        if iid not in pool:
            self.open_view(f"s:{it['subject_id']}")
            if iid not in {r["id"] for r in self.visible}:
                self.cb_type.current(0)
                self.cb_tag.current(0)
                self.refresh_items()
        self.select_ids([iid], see=True)
        self.lift()

    def follow_ref(self, title: str):
        title = title.strip()
        it = self.store.find_by_title(title)
        if it:
            self.goto_item(it["id"])
            return
        sid = self.store.find_subject(title)
        if sid:
            self.open_view(f"s:{sid}")
            return
        if messagebox.askyesno(APP_NAME, f"Aucune fiche ni sujet « {title} ».\n\nCréer une note avec ce titre ?", parent=self):
            sid = self.current_sid()
            iid = self.store.add_item(sid, "note", title=title, body="", meta={"auto_title": False})
            self._after_add([iid], sid, enrich=False)
            self.nb.select(self.tab_body)
            self.editor.t.focus_set()

    def choose_reference(self) -> Optional[str]:
        got: List[Tuple[str, int, str]] = []
        p = Palette(self, "ref", on_pick=lambda pick: got.append(pick))
        self.wait_window(p)
        for _ in range(30):
            if got:
                break
            self.update()
            time.sleep(0.01)
        if not got:
            return None
        kind, ident, label = got[0]
        if kind == "s":
            s = self.store.subject(ident)
            return s["name"] if s else None
        if kind == "i":
            it = self.store.item(ident)
            return (it.get("title") or "").strip() if it else None
        return label

    def open_palette(self):
        def pick(p):
            kind, ident, _lab = p
            if kind == "s":
                self.open_view(f"s:{ident}")
            elif kind == "i":
                self.goto_item(ident)
        Palette(self, "goto", on_pick=pick)

    # ================================================================ modifier les fiches
    def _sel_items(self) -> List[int]:
        if self.cur_view == "v:trash":
            return []
        return list(self.selected)

    def rename_any(self):
        if self.focus_get() is self.tree:
            self.rename_subject()
        else:
            self.rename_item()

    def rename_item(self):
        if not self.cur_item:
            if self.cur_view.startswith("s:"):
                self.rename_subject()
            return
        self.e_title.focus_set()
        self.e_title.select_range(0, "end")
        self.e_title.icursor("end")

    def toggle_fav(self):
        ids = self._sel_items()
        if not ids:
            return
        its = [self.store.item(i) for i in ids]
        val = 0 if all(it and it.get("fav") for it in its) else 1
        for i in ids:
            self.store.update_item(i, touch=False, fav=val)
        self.refresh_tree()
        self.refresh_items(keep=ids)
        self.set_status(("★ Ajouté aux favoris" if val else "☆ Retiré des favoris") + f" ({len(ids)}).", "OK")

    def toggle_pin(self):
        ids = self._sel_items()
        if not ids:
            return
        its = [self.store.item(i) for i in ids]
        val = 0 if all(it and it.get("pinned") for it in its) else 1
        for i in ids:
            self.store.update_item(i, touch=False, pinned=val)
        self.refresh_tree()
        self.refresh_items(keep=ids)
        self.set_status(("📌 Épinglé en haut" if val else "Désépinglé") + f" ({len(ids)}).", "OK")

    def edit_tags(self):
        ids = self._sel_items()
        if not ids:
            return
        if len(ids) == 1:
            self.e_tags.focus_set()
            self.e_tags.icursor("end")
            return
        r = ask_string(self, "Étiquettes", f"Ajouter ces étiquettes aux {len(ids)} fiches (séparées par des virgules ; "
                                           "« -mot » pour en retirer une) :")
        if not r:
            return
        add = [t for t in tag_list(r) if not t.startswith("-")]
        rem = [norm(t[1:]) for t in tag_list(r) if t.startswith("-")]
        for i in ids:
            it = self.store.item(i)
            cur = [t for t in tag_list(it.get("tags") or "") if norm(t) not in rem]
            self.store.update_item(i, tags=", ".join(cur + add))
        self.refresh_tree()
        self.refresh_items(keep=ids)

    def move_selected(self, copy: bool = False, target: Optional[int] = None):
        ids = self._sel_items()
        if not ids:
            self.set_status("Choisis d'abord une ou plusieurs fiches.", "WARN")
            return
        self._commit_pending()
        if target is None:
            target = SubjectChooser(self, self, "Copier vers" if copy else "Déplacer vers",
                                    f"{'Copier' if copy else 'Déplacer'} {len(ids)} fiche(s) dans quel sujet ?").wait()
        if not target:
            return
        name = self.store.subject_path(target)
        if copy:
            new = self.store.copy_items(ids, target)
            self.push_undo(f"copie de {len(new)} fiche(s)", lambda: self.store.trash_items(new))
            self.refresh_tree()
            self.refresh_items(keep=ids)
            self.reveal_subject(target)
            self.set_status(f"⧉ {len(new)} fiche(s) copiée(s) dans « {name} ».  (Ctrl+Z pour annuler)", "OK")
        else:
            old = self.store.move_items(ids, target)

            def undo(old=old):
                for i, sid in old:
                    self.store.move_items([i], sid)
            self.push_undo(f"déplacement de {len(old)} fiche(s)", undo)
            self.refresh_tree()
            self.refresh_items(keep=ids)
            self.reveal_subject(target)
            self.set_status(f"📁 {len(old)} fiche(s) déplacée(s) dans « {name} ».  (Ctrl+Z pour annuler)", "OK")

    def move_item_step(self, d: int):
        if not self.cur_view.startswith("s:") or len(self.selected) != 1:
            self.set_status("Monter/descendre : ouvre un sujet, choisis une fiche (tri « Ordre manuel »).", "WARN")
            return
        if self.sort != "manual":
            self.sort = "manual"
            self.cb_sort.current(0)
            self.store.set("sort", "manual")
        iid = self.selected[0]
        it = self.store.item(iid)
        sibs = sorted([r for r in self.store.items_in([it["subject_id"]])], key=lambda r: (-int(r.get("pinned") or 0),
                                                                                         float(r.get("sort") or 0)))
        ids = [r["id"] for r in sibs]
        i = ids.index(iid)
        j = max(0, min(len(ids) - 1, i + d))
        if i == j:
            return
        ids.insert(j, ids.pop(i))
        with self.store.lock:
            for k, x in enumerate(ids):
                self.store.conn.execute("UPDATE items SET sort=? WHERE id=?", (k + 1, x))
            self.store.conn.commit()
        self.store._touch()
        self.refresh_items(keep=[iid])

    def delete_selected(self):
        if self.cur_view == "v:trash":
            self.trash_purge()
            return
        ids = self._sel_items()
        if not ids:
            return
        self._commit_pending()
        self.player.stop()
        pool = [r["id"] for r in (self.results if self.cur_view == "search" else self.visible)]
        nxt = None
        for i in pool[pool.index(ids[-1]) + 1:] if ids[-1] in pool else []:
            if i not in ids:
                nxt = i
                break
        if nxt is None:
            for i in reversed(pool[:pool.index(ids[0])] if ids[0] in pool else []):
                if i not in ids:
                    nxt = i
                    break
        batch = self.store.trash_items(ids)
        self.push_undo(f"suppression de {len(ids)} fiche(s)", lambda: self.store.restore_batch(batch))
        self.editor_item = None
        self.selected = []
        self.refresh_tree()
        self.refresh_items(keep=[nxt] if nxt else None)
        self.set_status(f"🗑 {len(ids)} fiche(s) mise(s) à la corbeille.  Ctrl+Z pour annuler.", "OK")

    def push_undo(self, label: str, fn: Callable[[], Any]):
        self.undo_stack.append((label, fn))
        self.undo_stack = self.undo_stack[-50:]

    def do_undo(self):
        if not self.undo_stack:
            self.set_status("Rien à annuler.", "DIM")
            return
        label, fn = self.undo_stack.pop()
        try:
            fn()
        except Exception as ex:
            logger.error("annulation : %s", traceback.format_exc())
            self.set_status(f"Annulation impossible : {ex}", "ERR")
            return
        if self.cur_view != "search" and not self._view_valid(self.cur_view):
            self.cur_view = "v:all"
        self.refresh_tree()
        self.refresh_items(keep=list(self.selected))
        self.set_status(f"↩ Annulé : {label}.", "OK")

    # ================================================================ sujets
    def _tree_sid(self) -> Optional[int]:
        sel = self.tree.selection()
        if sel and sel[0].startswith("s:"):
            return int(sel[0][2:])
        return self.current_sid(strict=True)

    def new_subject(self, parent: Optional[int] = None):
        r = SubjectDialog(self, self, "Nouveau sous-sujet" if parent else "Nouveau sujet", None, parent).wait()
        if not r:
            return
        sid = self.store.add_subject(r["name"], r["parent_id"], r["icon"], r["color"], r["description"], bool(r["pinned"]))
        if r["parent_id"]:
            self.store.update_subject(r["parent_id"], expanded=1)
        self.refresh_tree()
        self.open_view(f"s:{sid}")
        self.reveal_subject(sid)
        self.set_status(f"📁 Sujet « {r['name']} » créé. Ajoute-y des notes, liens, images…", "OK")

    def edit_subject(self, sid: Optional[int] = None):
        sid = sid or self._tree_sid()
        s = self.store.subject(sid) if sid else None
        if not s:
            return
        r = SubjectDialog(self, self, "Modifier le sujet", s).wait()
        if not r:
            return
        par = r["parent_id"]
        if par != s["parent_id"] and not self.store.move_subject(sid, par):
            messagebox.showwarning(APP_NAME, "Un sujet ne peut pas aller dans lui-même ou un de ses sous-sujets.", parent=self)
            par = s["parent_id"]
        self.store.update_subject(sid, name=r["name"], icon=r["icon"], color=r["color"], description=r["description"],
                                  pinned=r["pinned"])
        self.refresh_tree()
        self.reveal_subject(sid)
        self.refresh_items(keep=list(self.selected))

    def rename_subject(self):
        sid = self._tree_sid()
        s = self.store.subject(sid) if sid else None
        if not s:
            return
        r = ask_string(self, "Renommer le sujet", "Nouveau nom :", s["name"])
        if r and r.strip() and r.strip() != s["name"]:
            self.store.update_subject(sid, name=r.strip())
            self.refresh_tree()
            self._header()

    def delete_subject(self, sid: Optional[int] = None):
        sid = sid or self._tree_sid()
        s = self.store.subject(sid) if sid else None
        if not s:
            return
        n = len(self.store.items_in([sid] + self.store.descendants(sid)))
        k = len(self.store.descendants(sid))
        msg = f"Mettre le sujet « {s['name']} » à la corbeille ?"
        if n or k:
            msg += f"\n\nIl contient {n} fiche(s)" + (f" et {k} sous-sujet(s)" if k else "") + " qui iront aussi à la corbeille."
        msg += "\n\nTu pourras le restaurer depuis la Corbeille (ou Ctrl+Z)."
        if not messagebox.askyesno(APP_NAME, msg, parent=self):
            return
        self._commit_pending()
        batch = self.store.trash_subject(sid)
        self.push_undo(f"suppression du sujet « {s['name']} »", lambda: self.store.restore_batch(batch))
        if self.cur_view == f"s:{sid}" or not self._view_valid(self.cur_view):
            self.cur_view = f"s:{s['parent_id']}" if s["parent_id"] else "v:all"
        self.refresh_tree()
        self.open_view(self.cur_view)
        self.set_status(f"🗑 Sujet « {s['name']} » mis à la corbeille.  Ctrl+Z pour annuler.", "OK")

    def reorder_subject(self, d: int, sid: Optional[int] = None):
        sid = sid or self._tree_sid()
        if sid:
            self.store.reorder_subject(sid, d)
            self.refresh_tree()
            self.reveal_subject(sid, flash=False)

    def promote_subject(self, sid: Optional[int] = None):
        sid = sid or self._tree_sid()
        if sid and self.store.move_subject(sid, None):
            self.refresh_tree()
            self.reveal_subject(sid)

    def rename_subject_id(self, sid: int):
        s = self.store.subject(sid)
        r = ask_string(self, "Renommer le sujet", "Nouveau nom :", s["name"]) if s else None
        if r and r.strip() and r.strip() != s["name"]:
            self.store.update_subject(sid, name=r.strip())
            self.refresh_tree()
            self._header()

    def manage_subjects(self):
        SubjectManager(self, self)

    def _subjects_menu(self, mb):
        m = new_menu(mb)
        cur = lambda: self._tree_sid()
        def need(fn):
            def run():
                sid = cur()
                if not sid:
                    messagebox.showinfo(APP_NAME, "Choisis d'abord un sujet dans l'arbre de gauche.", parent=self)
                    return
                fn(sid)
            return run
        m.add_command(label="🗂 Gérer les sujets…", accelerator="Ctrl+Maj+G", command=self.manage_subjects)
        m.add_separator()
        m.add_command(label="📁 Nouveau sujet principal…", accelerator="Ctrl+Maj+N", command=lambda: self.new_subject(None))
        m.add_command(label="📂 Nouveau sous-sujet du sujet choisi…", accelerator="Inser", command=need(self.new_subject))
        m.add_separator()
        m.add_command(label="✏ Renommer", accelerator="F2", command=need(self.rename_subject_id))
        m.add_command(label="⚙ Modifier (icône, couleur, parent, description)…", command=need(self.edit_subject))
        m.add_command(label="😀 Changer l'icône…", command=need(self.set_subject_icon))
        m.add_command(label="🎨 Changer la couleur…", command=need(lambda s: self.set_subject_color(s)))
        m.add_separator()
        m.add_command(label="⬆ Monter", accelerator="Alt+Haut", command=need(lambda s: self.reorder_subject(-1, s)))
        m.add_command(label="⬇ Descendre", accelerator="Alt+Bas", command=need(lambda s: self.reorder_subject(1, s)))
        m.add_command(label="📁 Déplacer / ranger dans un autre sujet…", command=need(self._subject_into))
        m.add_command(label="⤴ Rendre sujet principal", command=need(self.promote_subject))
        m.add_command(label="🔀 Fusionner dans…", command=need(self.merge_subject))
        m.add_separator()
        m.add_command(label="🗑 Supprimer (corbeille)", command=need(self.delete_subject))
        m.add_separator()
        m.add_command(label="Astuce : glisse un sujet sur un autre pour en faire un sous-sujet ; dans le vide = principal",
                      state="disabled")
        return m

    def merge_subject(self, sid: int):
        s = self.store.subject(sid)
        if not s:
            return
        dst = SubjectChooser(self, self, "Fusionner", f"Fusionner « {s['name']} » dans quel sujet ?\n"
                                                    "Ses fiches et sous-sujets y passent, puis il va à la corbeille.",
                             exclude=[sid] + self.store.descendants(sid)).wait()
        if not dst:
            return
        res = self.store.merge_subjects(sid, dst)

        def undo(res=res):
            self.store.restore_batch(res["batch"])
            for k in res["kids"]:
                self.store.update_subject(k, parent_id=res["src"])
            for i, old in res["moved"]:
                self.store.move_items([i], old)
        self.push_undo(f"fusion de « {s['name']} »", undo)
        self.refresh_tree()
        self.open_view(f"s:{dst}")
        self.set_status(f"🔀 « {s['name']} » fusionné ({len(res['moved'])} fiche(s)).  Ctrl+Z pour annuler.", "OK")

    def set_subject_icon(self, sid: int):
        s = self.store.subject(sid)
        r = EmojiPicker(self, s["icon"]).wait()
        if r is not None:
            self.store.update_subject(sid, icon=r or "📁")
            self.refresh_tree()
            self._header()

    def set_subject_color(self, sid: int, color: Optional[str] = None):
        if color is None:
            from tkinter import colorchooser
            r = colorchooser.askcolor(self.store.subject(sid)["color"] or "#FFFF55", parent=self, title="Couleur du sujet")
            if not r or not r[1]:
                return
            color = r[1]
        self.store.update_subject(sid, color=color)
        self.swatches.pop(color, None)
        self.refresh_tree()
        self._header()
        if self._effective_mode() == "cards":
            self.fill_cards()

    def _tree_menu(self, e):
        row = self.tree.identify_row(e.y)
        m = new_menu(self)
        if row.startswith("s:"):
            sid = int(row[2:])
            s = self.store.subject(sid)
            if row not in self.tree.selection():
                self.tree.selection_set(row)
            m.add_command(label=f"{s['icon']} {s['name']}", state="disabled")
            m.add_separator()
            m.add_command(label="📂 Nouveau sous-sujet…", accelerator="Inser", command=lambda: self.new_subject(sid))
            m.add_command(label="📝 Nouvelle note ici", command=self.new_note)
            m.add_command(label="📋 Coller ici", command=self.smart_paste)
            m.add_separator()
            m.add_command(label="✏ Renommer", accelerator="F2", command=self.rename_subject)
            m.add_command(label="⚙ Modifier (icône, couleur, description)…", command=lambda: self.edit_subject(sid))
            m.add_command(label="😀 Icône…", command=lambda: self.set_subject_icon(sid))
            cm = new_menu(m)
            for col in SUBJECT_COLORS:
                cm.add_command(label="■■■  " + col, foreground=col, activeforeground=col,
                               command=lambda c=col: self.set_subject_color(sid, c))
            cm.add_command(label="Autre couleur…", command=lambda: self.set_subject_color(sid))
            m.add_cascade(label="🎨 Couleur", menu=cm)
            m.add_command(label=("📌 Désépingler" if s["pinned"] else "📌 Épingler en haut"),
                          command=lambda: (self.store.update_subject(sid, pinned=0 if s["pinned"] else 1), self.refresh_tree()))
            m.add_command(label="⬆ Monter", accelerator="Alt+Haut", command=lambda: self.reorder_subject(-1))
            m.add_command(label="⬇ Descendre", accelerator="Alt+Bas", command=lambda: self.reorder_subject(1))
            if s["parent_id"]:
                m.add_command(label="⤴ Rendre sujet principal",
                              command=lambda: self.promote_subject(sid))
            m.add_command(label="📁 Ranger dans…", command=lambda: self._subject_into(sid))
            m.add_command(label="🔀 Fusionner dans…", command=lambda: self.merge_subject(sid))
            m.add_separator()
            m.add_command(label="🌐 Exporter en HTML…", command=lambda: self.export_dialog(sid, False))
            m.add_command(label="📦 Exporter en ZIP…", command=lambda: self.export_dialog(sid, True))
            m.add_command(label="📥 Importer un dossier ici…", command=lambda: self.import_folder_dialog(sid))
            m.add_command(label="🗂 Ouvrir son dossier de fichiers", command=lambda: open_path(self.store.subject_media_dir(sid)))
            m.add_separator()
            m.add_command(label="🗑 Supprimer (corbeille)", accelerator="Suppr", command=lambda: self.delete_subject(sid))
        elif row.startswith("t:"):
            tg = row[2:]
            m.add_command(label=f"✏ Renommer l'étiquette #{tg}…", command=lambda: self.rename_tag(tg))
            m.add_command(label=f"✖ Retirer #{tg} de toutes les fiches", command=lambda: self.remove_tag(tg))
        elif row == "v:trash":
            m.add_command(label="🧹 Vider la corbeille", command=self.trash_empty)
        else:
            m.add_command(label="📁 Nouveau sujet…", command=lambda: self.new_subject(None))
            m.add_command(label="📥 Importer un dossier…", command=lambda: self.import_folder_dialog(None))
        popup(m, e)

    def _subject_into(self, sid: int):
        dst = SubjectChooser(self, self, "Ranger le sujet", "Ranger ce sujet dans :", allow_root=True,
                             exclude=[sid] + self.store.descendants(sid)).wait()
        if dst is None:
            return
        if self.store.move_subject(sid, dst or None):
            if dst:
                self.store.update_subject(dst, expanded=1)
            self.refresh_tree()
            self.reveal_subject(sid)

    def rename_tag(self, tg: str):
        r = ask_string(self, "Renommer l'étiquette", f"Nouveau nom pour #{tg} :", tg)
        if not r or not r.strip():
            return
        n = 0
        for it in self.store.items_where("tags<>''"):
            tl = tag_list(it["tags"])
            if any(norm(t) == norm(tg) for t in tl):
                self.store.update_item(it["id"], touch=False, tags=", ".join(r.strip() if norm(t) == norm(tg) else t for t in tl))
                n += 1
        if self.cur_view == f"t:{tg}":
            self.cur_view = f"t:{norm_tags(r)}"
        self.refresh_all()
        self.set_status(f"🏷 Étiquette renommée sur {n} fiche(s).", "OK")

    def remove_tag(self, tg: str):
        if not messagebox.askyesno(APP_NAME, f"Retirer l'étiquette #{tg} de toutes les fiches ?", parent=self):
            return
        for it in self.store.items_where("tags<>''"):
            tl = tag_list(it["tags"])
            if any(norm(t) == norm(tg) for t in tl):
                self.store.update_item(it["id"], touch=False, tags=", ".join(t for t in tl if norm(t) != norm(tg)))
        if self.cur_view == f"t:{tg}":
            self.cur_view = "v:tags"
        self.refresh_all()

    # ================================================================ menus contextuels
    def item_menu(self, e):
        ids = self._sel_items()
        if not ids:
            return
        m = self._build_item_menu(ids)
        popup(m, e)

    def _item_more(self):
        ids = self._sel_items()
        if not ids:
            return
        m = self._build_item_menu(ids)
        b = self.b_more
        try:
            m.tk_popup(b.winfo_rootx(), b.winfo_rooty() + b.winfo_height())
        finally:
            m.grab_release()

    def _build_item_menu(self, ids: List[int]):
        m = new_menu(self)
        it = self.store.item(ids[0]) if len(ids) == 1 else None
        if it:
            fpath = Paths.abs(it.get("file") or "")
            m.add_command(label="↗ Ouvrir", accelerator="Entrée", command=lambda: self.open_item(it["id"]))
            m.add_command(label="📖 Mode lecture", accelerator="F11", command=self.open_reader)
            if it.get("url"):
                m.add_command(label="🌐 Ouvrir le lien dans le navigateur", command=lambda: open_url(it["url"]))
                m.add_command(label="📋 Copier le lien", command=lambda: copy_to_clipboard(self, it["url"]))
            if fpath and os.path.isfile(fpath):
                m.add_command(label="🗂 Montrer le fichier dans l'Explorateur", command=lambda: reveal_in_explorer(fpath))
            m.add_command(label="📋 Copier la citation (auteur, source, lien)", command=lambda: self.copy_citation(it["id"]))
            m.add_separator()
            m.add_command(label="✏ Renommer", accelerator="F2", command=self.rename_item)
        m.add_command(label="★ Favori oui/non", accelerator="Ctrl+D", command=self.toggle_fav)
        m.add_command(label="📌 Épingler oui/non", accelerator="Ctrl+P", command=self.toggle_pin)
        m.add_command(label="🏷 Étiquettes…", accelerator="Ctrl+T", command=self.edit_tags)
        m.add_separator()
        m.add_command(label="📁 Déplacer vers…", accelerator="Ctrl+M", command=lambda: self.move_selected(False))
        m.add_command(label="⧉ Copier vers…", command=lambda: self.move_selected(True))
        if self.cur_view.startswith("s:"):
            m.add_command(label="⬆ Monter", accelerator="Alt+Haut", command=lambda: self.move_item_step(-1))
            m.add_command(label="⬇ Descendre", accelerator="Alt+Bas", command=lambda: self.move_item_step(1))
        if it:
            tools = new_menu(m)
            if it["type"] in ("link", "video") and it.get("url"):
                tools.add_command(label="↻ Récupérer à nouveau titre et miniature", command=lambda: self.refetch(it["id"]))
                tools.add_command(label="🌐 Capturer la page complète", command=lambda: self.capture_item(it["id"]))
            if it["type"] == "video" and it.get("url"):
                tools.add_command(label="📦 Envoyer à l'Archiveur", command=lambda: self.send_to_archiveur(it["url"]))
            if it["type"] == "image":
                tools.add_command(label="🔤 Lire le texte de l'image (OCR)", command=lambda: self.ocr_item(it["id"]))
            if it["type"] in ("voice", "audio"):
                tools.add_command(label="📝 Transcrire en texte", command=lambda: self.transcribe_item(it["id"]))
            if it["type"] == "document":
                tools.add_command(label="↻ Extraire le texte", command=lambda: self.reextract(it["id"]))
            if it["type"] == "note":
                tools.add_command(label="💾 Enregistrer comme modèle de fiche…", command=self.save_as_template)
            tools.add_command(label="🌐 Exporter cette fiche en HTML…", command=lambda: self.export_selection([it["id"]]))
            m.add_cascade(label="🛠 Outils", menu=tools)
        else:
            m.add_command(label="🌐 Exporter la sélection en HTML…", command=self.export_selection)
            m.add_command(label="📖 Lire la sélection", command=self.open_reader)
        m.add_separator()
        m.add_command(label=f"🗑 Mettre à la corbeille ({len(ids)})", accelerator="Suppr", command=self.delete_selected)
        return m

    def view_menu(self, e):
        m = new_menu(self)
        m.add_command(label="📝 Nouvelle note", accelerator="Ctrl+N", command=self.new_note)
        m.add_command(label="🔗 Lien web…", accelerator="Ctrl+L", command=self.add_link_dialog)
        m.add_command(label="❝ Citation…", command=self.add_quote_dialog)
        m.add_command(label="📎 Fichier(s)…", accelerator="Ctrl+O", command=lambda: self.add_files_dialog(None))
        m.add_command(label="📋 Coller", accelerator="Ctrl+V", command=self.smart_paste)
        m.add_separator()
        m.add_command(label="☰ Liste", command=lambda: self.set_view_mode("list"))
        m.add_command(label="▦ Cartes", command=lambda: self.set_view_mode("cards"))
        m.add_command(label="🕘 Chronologie", command=lambda: self.set_view_mode("chrono"))
        m.add_separator()
        m.add_command(label="Tout sélectionner", accelerator="Ctrl+A", command=self.select_all)
        popup(m, e)

    # ================================================================ glisser-deposer interne
    def _tree_press(self, e):
        row = self.tree.identify_row(e.y)
        self.press = {"x": e.x_root, "y": e.y_root, "sid": int(row[2:]), "src": "subject"} if row.startswith("s:") else None

    def _drag_motion(self, e):
        p = self.press
        if not p:
            return None
        if self.drag is None:
            if abs(e.x_root - p["x"]) + abs(e.y_root - p["y"]) < 8:
                return None
            if p["src"] == "items":
                ids = p.get("ids") or list(self.selected)
                if not ids:
                    return None
                txt = f"📝 {len(ids)} fiche(s)" if len(ids) > 1 else "📝 " + ((self.store.item(ids[0]) or {}).get("title") or "")[:40]
                self.drag = {"src": "items", "ids": ids}
            else:
                s = self.store.subject(p["sid"])
                if not s:
                    return None
                txt = f"{s['icon']} {s['name']}"
                self.drag = {"src": "subject", "sid": p["sid"]}
            tw = tk.Toplevel(self)
            tw.overrideredirect(True)
            try:
                tw.attributes("-topmost", True)
                tw.attributes("-alpha", 0.9)
            except tk.TclError:
                pass
            tk.Label(tw, text=txt, bg=C["HI"], fg=C["ON_HI"], font=fnt("GUIB"), padx=8, pady=3).pack()
            self.drag["win"] = tw
            self.drag["hint"] = ""
        tw = self.drag["win"]
        tw.geometry(f"+{e.x_root + 14}+{e.y_root + 10}")
        tgt, desc = self._drop_target(e.x_root, e.y_root, e.state)
        self._drop_highlight(tgt)
        self.set_status(desc or "Lâche sur un sujet de la colonne de gauche (Ctrl = copier, Échap = annuler).", "WARN")
        return "break"

    def _drop_target(self, x: int, y: int, state: int) -> Tuple[Optional[str], str]:
        w = self.winfo_containing(x, y)
        if w is not self.tree or not self.drag:
            return None, ""
        row = self.tree.identify_row(y - self.tree.winfo_rooty())
        if self.drag["src"] == "items":
            if row.startswith("s:"):
                s = self.store.subject(row[2:])
                return row, f"{'Copier' if state & 0x4 else 'Déplacer'} dans « {s['name']} »"
            if row == "v:fav":
                return row, "Marquer comme favoris ★"
            if row == "v:pin":
                return row, "Épingler 📌"
            if row == "v:trash":
                return row, "Mettre à la corbeille"
            return None, ""
        sid = self.drag["sid"]
        if row.startswith("s:"):
            t = int(row[2:])
            if t == sid or t in self.store.descendants(sid):
                return None, "Impossible : un sujet ne va pas dans lui-même."
            s = self.store.subject(t)
            return row, (f"Placer avant « {s['name']} »" if state & 0x1 else f"Ranger dans « {s['name']} »  (Maj = placer avant)")
        if row == "v:trash":
            return row, "Mettre le sujet à la corbeille"
        if not row:
            return "root", "Mettre au niveau principal"
        return None, ""

    def _drop_highlight(self, tgt: Optional[str]):
        old = getattr(self, "_drop_row", None)
        if old and old != tgt and self.tree.exists(old):
            tags = [t for t in self.tree.item(old, "tags") if t != "drop"]
            self.tree.item(old, tags=tags)
        if tgt and tgt != "root" and self.tree.exists(tgt):
            tags = list(self.tree.item(tgt, "tags"))
            if "drop" not in tags:
                self.tree.item(tgt, tags=tags + ["drop"])
        self._drop_row = tgt

    def _drag_release(self, e):
        d = self.drag
        p = self.press
        self.press = None
        if d is None:
            if p and p.get("src") == "items" and p.get("ids") and len(p["ids"]) > 1 and not (e.state & 0x5) \
                    and e.widget in (self.lst, self.chr):
                row = e.widget.identify_row(e.y)
                if row.startswith("i:"):
                    self.select_ids([int(row[2:])])
            return None
        self.drag = None
        try:
            d["win"].destroy()
        except Exception:
            pass
        tgt, _desc = self._drop_target(e.x_root, e.y_root, e.state)
        self._drop_highlight(None)
        self.set_status("", "DIM")
        if not tgt:
            return "break"
        if d["src"] == "items":
            ids = d["ids"]
            self.select_ids(ids)
            if tgt.startswith("s:"):
                self.move_selected(copy=bool(e.state & 0x4), target=int(tgt[2:]))
            elif tgt == "v:fav":
                for i in ids:
                    self.store.update_item(i, touch=False, fav=1)
                self.refresh_tree()
                self.refresh_items(keep=ids)
            elif tgt == "v:pin":
                for i in ids:
                    self.store.update_item(i, touch=False, pinned=1)
                self.refresh_tree()
                self.refresh_items(keep=ids)
            elif tgt == "v:trash":
                self.delete_selected()
        else:
            sid = d["sid"]
            if tgt == "v:trash":
                self.delete_subject(sid)
            elif tgt == "root":
                self.store.move_subject(sid, None)
            elif e.state & 0x1:
                self.store.place_subject_before(sid, int(tgt[2:]))
            else:
                t = int(tgt[2:])
                if self.store.move_subject(sid, t):
                    self.store.update_subject(t, expanded=1)
            self.refresh_tree()
            self._header()
        return "break"

    # ================================================================ modeles de fiches
    def all_templates(self) -> Dict[str, Tuple[str, str]]:
        d = dict(TEMPLATES)
        for name, val in (self.store.get("templates_user", {}) or {}).items():
            if isinstance(val, (list, tuple)) and len(val) == 2:
                d[name] = (val[0], val[1])
        return d

    def _runs_to_md(self, runs: List[List[Any]]) -> str:
        out = []
        for text, tags in runs:
            pre = ""
            if "h1" in tags:
                pre = "# "
            elif "h2" in tags:
                pre = "## "
            elif "h3" in tags:
                pre = "### "
            elif "quote" in tags:
                pre = "> "
            t = text
            if "b" in tags and t.strip():
                t = f"**{t}**"
            elif "i" in tags and t.strip():
                t = f"*{t}*"
            if pre:
                t = "\n".join((pre + ln) if ln.strip() else ln for ln in t.split("\n"))
            out.append(t)
        return "".join(out).replace("☐ ", "[ ] ").replace("☑ ", "[ ] ")

    def save_as_template(self):
        it = self.store.item(self.cur_item) if self.cur_item else None
        if not it or it["type"] != "note":
            messagebox.showinfo(APP_NAME, "Ouvre d'abord une note : sa structure deviendra un modèle réutilisable.", parent=self)
            return
        self._commit_pending()
        it = self.store.item(it["id"])
        name = ask_string(self, "Nouveau modèle de fiche", "Nom du modèle :", it.get("title") or "")
        if not name or not name.strip():
            return
        user = self.store.get("templates_user", {}) or {}
        user[name.strip()] = ["📋", self._runs_to_md(runs_from_any(it.get("body") or ""))]
        self.store.set("templates_user", user)
        self._rebuild_add_menu()
        self.set_status(f"📋 Modèle « {name.strip()} » enregistré : menu Ajouter → Fiche à partir d'un modèle.", "OK")

    def manage_templates(self):
        user = self.store.get("templates_user", {}) or {}
        lines = ["# Modèles de fiches", "", "## Modèles fournis"]
        lines += [f"  {ic} {n}" for n, (ic, _m) in TEMPLATES.items()]
        lines += ["", "## Mes modèles"]
        lines += [f"  {v[0]} {n}" for n, v in user.items()] or ["  (aucun pour l'instant)"]
        lines += ["", "Pour créer un modèle : écris une note structurée, puis clic droit → Outils → "
                      "« Enregistrer comme modèle de fiche ».",
                  "Pour supprimer un de tes modèles : donne son nom ci-dessous (bouton Supprimer un modèle)."]
        TextDialog(self, "Modèles de fiches", "\n".join(lines), 700, 560)
        if user:
            n = ask_string(self, "Supprimer un modèle", "Nom exact du modèle à supprimer (laisser vide pour ne rien faire) :")
            if n and n.strip() in user:
                user.pop(n.strip())
                self.store.set("templates_user", user)
                self._rebuild_add_menu()
                self.set_status(f"Modèle « {n.strip()} » supprimé.", "OK")

    def _rebuild_add_menu(self):
        try:
            idx = self.menubar.index("Ajouter")
            self.menu_add = self._make_add_menu(self.menubar)
            self.menubar.entryconfigure(idx, menu=self.menu_add)
        except Exception:
            logger.error("menu Ajouter : %s", traceback.format_exc())

    # ================================================================ export / import / sauvegardes
    def export_dialog(self, sid: Optional[int], as_zip: bool):
        sid = sid or self.current_sid(strict=True)
        if not sid:
            messagebox.showinfo(APP_NAME, "Ouvre d'abord un sujet (colonne de gauche) à exporter.", parent=self)
            return
        self._commit_pending()
        s = self.store.subject(sid)
        os.makedirs(Paths.exports(), exist_ok=True)
        base = f"Grimoire_{safe_name(s['name'], 50)}_{dt.date.today().isoformat()}"
        out = filedialog.asksaveasfilename(parent=self, title="Exporter le sujet", initialdir=Paths.exports(),
                                           initialfile=base + (".zip" if as_zip else ".html"),
                                           defaultextension=".zip" if as_zip else ".html",
                                           filetypes=[("Archive ZIP", "*.zip")] if as_zip else [("Page web", "*.html")])
        if not out:
            return
        inc = True
        if self.store.descendants(sid):
            inc = messagebox.askyesno(APP_NAME, "Inclure aussi les sous-sujets ?", parent=self)
        self.set_status("Export en cours…", "WARN")

        def job():
            return export_subject_zip(self.store, sid, out, inc) if as_zip else export_subject(self.store, sid, out, inc)

        def done(n):
            if n is None:
                self.set_status("⚠ Export impossible (voir grimoire.log).", "ERR")
                return
            self.set_status(f"✔ {n} fiche(s) exportée(s) : {out}", "OK")
            if messagebox.askyesno(APP_NAME, f"{n} fiche(s) exportée(s) dans :\n{out}\n\nOuvrir maintenant ?", parent=self):
                open_path(out) if not as_zip else reveal_in_explorer(out)
        self.run_job(job, done, "export")

    def export_selection(self, ids: Optional[List[int]] = None):
        ids = ids or self._sel_items()
        if not ids:
            self.set_status("Choisis d'abord des fiches à exporter.", "WARN")
            return
        self._commit_pending()
        os.makedirs(Paths.exports(), exist_ok=True)
        it = self.store.item(ids[0])
        base = safe_name(it["title"], 50) if len(ids) == 1 and it else f"Selection_{len(ids)}_fiches"
        out = filedialog.asksaveasfilename(parent=self, title="Exporter en HTML", initialdir=Paths.exports(),
                                           initialfile=f"Grimoire_{base}.html", defaultextension=".html",
                                           filetypes=[("Page web", "*.html")])
        if not out:
            return
        n = export_subject(self.store, 0, out, item_ids=ids)
        self.set_status(f"✔ {n} fiche(s) exportée(s) : {out}", "OK")
        open_path(out)

    def backup_now(self):
        self._commit_pending()
        p = self.store.backup(force=True, tag="manuel")
        if p:
            self.set_status(f"💾 Sauvegarde : {p}   (tout est déjà enregistré automatiquement)", "OK")
        else:
            self.set_status("⚠ Sauvegarde impossible : " + self.store.last_error, "ERR")

    def restore_backup(self):
        p = filedialog.askopenfilename(parent=self, title="Restaurer une sauvegarde du Grimoire", initialdir=Paths.backups(),
                                       filetypes=[("Sauvegarde Grimoire", "grimoire_*.db"), ("Base SQLite", "*.db")])
        if not p:
            return
        try:
            c = sqlite3.connect(p)
            n = c.execute("SELECT COUNT(*) FROM items WHERE deleted IS NULL").fetchone()[0]
            c.close()
        except Exception as ex:
            messagebox.showerror(APP_NAME, f"Ce fichier n'est pas une sauvegarde valide : {ex}", parent=self)
            return
        if not messagebox.askyesno(APP_NAME, f"Remplacer le Grimoire actuel par cette sauvegarde ({n} fiche(s)) ?\n\n"
                                             "L'état actuel est d'abord sauvegardé (grimoire_..._avant_restauration.db).",
                                   parent=self, icon="warning"):
            return
        self._commit_pending()
        self.store.backup(force=True, tag="avant_restauration")
        try:
            src = sqlite3.connect(p)
            with self.store.lock:
                src.backup(self.store.conn)
            src.close()
            self.store._touch()
            if self.store.fts_ok:
                self.store.rebuild_fts()
        except Exception as ex:
            messagebox.showerror(APP_NAME, f"Restauration impossible : {ex}", parent=self)
            return
        self.undo_stack.clear()
        self.cur_view = "v:all"
        self.refresh_all()
        self.set_status(f"↩ Sauvegarde restaurée ({n} fiche(s)).", "OK")

    # ================================================================ outils
    def show_stats(self):
        st = self.store
        s = st.stats()
        L = ["# 📊 Statistiques du Grimoire", ""]
        L.append(f"  Fiches : {s['items']}")
        L.append(f"  Sujets : {s['subjects']}")
        L.append(f"  Favoris : {s['favs']}")
        L.append(f"  Épinglées : {s['pinned']}")
        L.append(f"  Mots écrits : {s['words']:,}".replace(",", " "))
        L.append(f"  Fichiers : {s['media_files']} ({human_size(s['media_size'])})")
        L.append(f"  Base de données : {human_size(s['db_size'])}")
        L.append(f"  Corbeille : {s['trash']} fiche(s)")
        L.append(f"  Dossier : {Paths.data}")
        L += ["", "## Par type"]
        mx = max([1] + list(s["by_type"].values()))
        for k in TYPE_ORDER:
            n = s["by_type"].get(k, 0)
            if n:
                L.append(f"{TYPES[k]['icon']} {TYPES[k]['plural']:<16} {'█' * max(1, int(28 * n / mx))} {n}")
        L += ["", "## Sujets les plus remplis"]
        tot = st.total_counts()
        top = sorted(((n, sid) for sid, n in tot.items() if n), reverse=True)[:12]
        mx = max([1] + [n for n, _s in top])
        for n, sid in top:
            subj = st.subject(sid)
            L.append(f"{subj['icon']} {subj['name'][:24]:<24} {'█' * max(1, int(24 * n / mx))} {n}")
        if not top:
            L.append("(tous les sujets sont encore vides)")
        L += ["", "## Ajouts par mois"]
        mx = max([1] + [n for _m, n in s["months"]])
        for m, n in reversed(s["months"]):
            L.append(f"{month_label(m + '-01'):<16} {'█' * max(1, int(28 * n / mx))} {n}")
        if s["tags"]:
            L += ["", "## Étiquettes les plus utilisées"]
            L.append("   ".join(f"#{t} ({n})" for t, n in s["tags"]))
        L += ["", "## Modules optionnels"]
        L.append(f"  Micro (sounddevice) : {'oui' if module_ok('sounddevice') else 'non installé'}")
        L.append(f"  Transcription (faster-whisper) : {'oui' if whisper_available() else 'non installé (menu Outils)'}")
        L.append(f"  Lecture PDF (pypdf) : {'oui' if module_ok('pypdf') else 'non installé'}")
        L.append(f"  Glisser-déposer (tkinterdnd2) : {'oui' if getattr(self, '_dnd_ok', False) else 'non disponible'}")
        L.append(f"  Lecteur audio (ffplay) : {'oui' if find_ff_tool('ffplay') else 'introuvable'}")
        L.append(f"  Capture de page (Edge) : {'oui' if find_browser() else 'introuvable'}")
        TextDialog(self, "Statistiques du Grimoire", "\n".join(L), 820, 680)

    def check_dialog(self):
        self.set_status("🔎 Vérification…", "WARN")
        self.update_idletasks()
        TextDialog(self, "Vérification du Grimoire", check_report(self.store), 860, 620)
        self.set_status("Vérification terminée.", "OK")

    def rebuild_index(self):
        n = self.store.rebuild_fts()
        self.set_status(f"🔄 Index de recherche reconstruit ({n} fiche(s)).", "OK")

    def install_whisper(self, confirm: bool = True):
        if whisper_available():
            messagebox.showinfo(APP_NAME, "faster-whisper est déjà installé : la transcription est disponible.", parent=self)
            return
        if confirm and not messagebox.askyesno(APP_NAME, WHISPER_HELP + "\n\nLancer l'installation maintenant ? "
                                               "(pip --user, quelques minutes, Internet requis)", parent=self):
            return
        py = find_python()
        self.set_status("⬇ Installation de faster-whisper en cours (quelques minutes)…", "WARN")

        def job():
            r = run_hidden([py, "-m", "pip", "install", "--user", "--upgrade", "faster-whisper"], 1800)
            return r.returncode, (r.stdout or "")[-2000:] + (r.stderr or "")[-2000:]

        def done(res):
            code, out = res if res else (1, "erreur inconnue")
            import importlib
            importlib.invalidate_caches()
            if code == 0:
                site_dirs = []
                try:
                    import site
                    site_dirs = [site.getusersitepackages()]
                except Exception:
                    pass
                for d in site_dirs:
                    if d not in sys.path and os.path.isdir(d):
                        sys.path.append(d)
                self.set_status("✔ faster-whisper installé : la transcription des mémos est disponible.", "OK")
                messagebox.showinfo(APP_NAME, "faster-whisper est installé.\nLe modèle sera téléchargé à la première "
                                              "transcription (une seule fois).", parent=self)
            else:
                self.set_status("⚠ Installation de faster-whisper échouée (voir le journal).", "ERR")
                logger.error("pip faster-whisper : %s", out)
                TextDialog(self, "Installation échouée", "# Installation de faster-whisper échouée\n\n" + out, 820, 520)
        self.run_job(job, done, "installation faster-whisper")

    def show_log(self):
        try:
            with open(Paths.log(), "r", encoding="utf-8", errors="replace") as f:
                txt = f.read()[-60000:]
        except OSError as ex:
            txt = str(ex)
        TextDialog(self, "Journal du Grimoire", "# grimoire.log\n" + Paths.log() + "\n\n" + txt, 1000, 640)

    def show_help(self, section: str = ""):
        d = TextDialog(self, "Aide du Grimoire", HELP_TEXT, 920, 680)
        if section:
            idx = d.t.search("Raccourcis clavier", "1.0", "end")
            if idx:
                d.t.see(idx)
                d.t.yview(idx)

    def about(self):
        s = self.store.stats()
        messagebox.showinfo(APP_NAME, f"📖 Grimoire\nCarnet de recherche du Projet Padawan\n\n"
                                      f"{s['items']} fiches · {s['subjects']} sujets\nDonnées : {Paths.data}\n"
                                      f"Python {sys.version.split()[0]} · Tk {self.tk.call('info', 'patchlevel')}", parent=self)

    # ================================================================ apparence
    def zoom(self, d: int):
        cur = int(self.store.get("font_delta", 0) or 0)
        new = 0 if d == 0 else max(FONT_DELTA_MIN, min(FONT_DELTA_MAX, cur + d))
        if new == cur and d != 0:
            return
        self.store.set("font_delta", new)
        init_fonts(self, new)
        apply_styles(self)
        self.img_cache.clear()
        self.after_idle(self._after_zoom)
        self.set_status(f"Taille du texte : {'+' if new > 0 else ''}{new}", "DIM")

    def _after_zoom(self):
        keep = list(self.selected)
        self._detail_mode_reset()
        self.refresh_items(keep=keep)

    def _detail_mode_reset(self):
        self._commit_pending()
        self._shown_ver = None
        self.editor_item_reload = True

    def change_theme(self):
        k = self.v_theme.get()
        if k not in THEMES:
            return
        self._commit_pending()
        self.store.set("theme", k)
        C.clear()
        C.update(THEMES[k])
        self.rebuild()

    def rebuild(self):
        keep = list(self.selected)
        view = self.cur_view
        q = self.v_search.get()
        for w in list(self.winfo_children()):
            if isinstance(w, tk.Toplevel):
                try:
                    w.destroy()
                except Exception:
                    pass
                continue
            w.destroy()
        self._detail_mode = ""
        self.editor_item = None
        self._build()
        self.cur_view = view if self._view_valid(view) or view == "search" else "v:all"
        self.refresh_tree()
        if view == "search" and q:
            self._search_lock = True
            self.v_search.set(q)
            self._search_lock = False
            self._update_placeholder()
            self.cur_view = self.view_before_search
            self.do_search(keep=keep)
        else:
            self._show_view_widget()
            self.refresh_items(keep=keep)

    # ================================================================ boite de reception (--ajouter)
    def _poll_inbox(self):
        try:
            d = Paths.inbox()
            files = sorted(glob.glob(os.path.join(d, "*.json"))) if os.path.isdir(d) else []
            all_ids: List[int] = []
            for fp in files:
                try:
                    with open(fp, "r", encoding="utf-8") as f:
                        payload = json.load(f)
                    os.remove(fp)
                except (OSError, ValueError) as ex:
                    logger.warning("inbox %s : %s", fp, ex)
                    try:
                        os.replace(fp, fp + ".erreur")
                    except OSError:
                        pass
                    continue
                if payload.get("action") == "montrer":
                    self._bring_front()
                    continue
                if payload.get("action") == "ouvrir":
                    self.store._touch()
                    self.refresh_all()
                    try:
                        self.goto_item(int(payload.get("id")))
                    except (TypeError, ValueError):
                        pass
                    self._bring_front()
                    continue
                if payload.get("action") == "lot":
                    with open(payload["fichier"], "r", encoding="utf-8") as f:
                        rep = import_lot(self.store, json.load(f))
                    all_ids += rep["ajoutees"]
                    continue
                ids = process_payload(self.store, payload)
                all_ids += ids
                logger.info("inbox : %d fiche(s) ajoutée(s)", len(ids))
            if all_ids:
                self._after_add(all_ids, None, msg=f"📥 {len(all_ids)} fiche(s) reçue(s) (envoi externe).")
                self._bring_front()
            self._gx_external_changes()
        except Exception:
            logger.error("inbox : %s", traceback.format_exc())
        self.after(1500, self._poll_inbox)

    def _bring_front(self):
        try:
            if self.state() == "iconic":
                self.state("zoomed")
            self.lift()
            self.attributes("-topmost", True)
            self.after(300, lambda: self.attributes("-topmost", False))
            self.focus_force()
        except tk.TclError:
            pass

    # ================================================================ fermeture
    def on_close(self):
        try:
            self._commit_pending()
        except Exception:
            logger.error("fermeture (enregistrement) : %s", traceback.format_exc())
        try:
            self.player.stop()
            if not self.readonly_test:
                try:
                    lw = self.pw.sash_coord(0)[0]
                    rw = self.pw.winfo_width() - self.pw.sash_coord(1)[0]
                    if not getattr(self.args, "geometry", ""):
                        self.store.set("left_w", lw)
                        self.store.set("right_w", rw)
                        self.store.set("panes_v", PANES_V)
                except Exception:
                    pass
                self.store.backup()
            self.store.close()
        except Exception:
            logger.error("fermeture : %s", traceback.format_exc())
        logger.info("Grimoire fermé")
        self.destroy()
