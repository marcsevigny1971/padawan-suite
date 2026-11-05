# -*- coding: utf-8 -*-
# Partie de archiveur5.py (découpage v1.2.2, comportement inchangé).
# Chargée par archiveur5.py dans un espace de noms commun : ne pas lancer seule.
from __future__ import annotations

class _ArchiveurAppPartie2:
    """Méthodes de ArchiveurApp (partie 2/3)."""


    def _layout_gallery(self):
        cells = getattr(self, "_gal_cells", [])
        if not cells:
            return
        cols = max(1, self._preview_width() // 196)
        for i, c in enumerate(cells):
            c.grid(row=i // cols, column=i % cols, padx=4, pady=4, sticky="n")

    def _render_files(self):
        self.files_tree.delete(*self.files_tree.get_children())
        path = self._preview_path
        names = list_folder_files(path) if path and os.path.isdir(path) else []
        sb = list_storyboard(path) if path else []
        self.files_title.configure(text=f"📂 Fichiers ({len(names)}) — double-clic = ouvrir, clic droit = options")
        for n in names:
            p = os.path.join(path, n)
            try:
                st = os.stat(p)
                size, mod = human_size(st.st_size), datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
            except OSError:
                size, mod = "—", ""
            self.files_tree.insert("", "end", iid="f::" + n, text=f" {file_icon(n)}  {n}",
                                   values=(file_kind(n), size, mod))
        extra = 0
        if sb:
            self.files_tree.insert("", "end", iid="f::" + STORYBOARD_DIR, text=f" 🎞  {STORYBOARD_DIR}\\  ({len(sb)} images)",
                                   values=("Dossier", human_size(sum(os.path.getsize(x) for x in sb)), ""))
            extra += 1
        for sub, icon in ((EXTRACTS_DIR, "✂"), (WEB_ASSETS_DIR, "🗂"), ("auteur", "👤")):
            d = os.path.join(path, sub) if path else ""
            if d and os.path.isdir(d):
                fl = [os.path.join(d, x) for x in os.listdir(d) if os.path.isfile(os.path.join(d, x))]
                if fl:
                    self.files_tree.insert("", "end", iid="f::" + sub, text=f" {icon}  {sub}\\  ({len(fl)} fichiers)",
                                           values=("Dossier", human_size(sum(os.path.getsize(x) for x in fl)), ""))
                    extra += 1
        self.files_tree.configure(height=max(3, min(12, len(names) + extra)))

    def _selected_file_path(self) -> Optional[str]:
        sel = self.files_tree.selection()
        if not sel or not self._preview_path:
            return None
        return os.path.join(self._preview_path, sel[0][3:])

    def open_preview_file(self):
        fp = self._selected_file_path()
        if fp and os.path.exists(fp):
            self._open_media(fp, "fichier")

    def reveal_preview_file(self):
        fp = self._selected_file_path()
        if fp:
            ok, err = reveal_in_explorer(fp)
            if not ok:
                messagebox.showerror(APP_NAME, err, parent=self)

    def copy_preview_file_path(self):
        fp = self._selected_file_path()
        if fp:
            self._copy_to_clipboard(fp)

    def copy_preview_file_name(self):
        fp = self._selected_file_path()
        if fp:
            self._copy_to_clipboard(os.path.basename(fp))

    def _files_menu_popup(self, event):
        iid = self.files_tree.identify_row(event.y)
        if iid:
            self.files_tree.selection_set(iid)
        else:
            return "break"
        try:
            self._files_menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                self._files_menu.grab_release()
            except Exception:
                pass
        return "break"

    # ------------------------------------------------------------ actions
    def open_path_safe(self, path: str, kind: str = "élément"):
        ok, err = open_path_explorer(path)
        if not ok:
            messagebox.showerror(APP_NAME, err or f"Impossible d'ouvrir le {kind}.", parent=self)
        return ok

    def open_selected_folder(self):
        path = self._folder_path()
        if not path or not os.path.isdir(path):
            root = self.archive_root_path()
            os.makedirs(root, exist_ok=True)
            self.status.set("Aucune archive sélectionnée — ouverture du dossier racine.")
            self.open_path_safe(root, "dossier")
            return
        self.open_path_safe(path, "dossier")

    def open_last_or_selected_folder(self):
        """Sélection → dernier archivage → racine ARCHIVEUR."""
        e = self._selected_entry()
        path = None
        if e and e.get("folder"):
            path = os.path.join(self.archive_root_path(), str(e["folder"]))
        if (not path or not os.path.isdir(path)) and self.last_folder:
            path = os.path.join(self.archive_root_path(), self.last_folder)
        if not path or not os.path.isdir(path):
            path = self.archive_root_path()
            os.makedirs(path, exist_ok=True)
        self.log(f"Ouverture dossier: {path}")
        self.open_path_safe(path, "dossier")

    def open_selected_index(self):
        path = self._folder_path()
        if not path:
            messagebox.showinfo(APP_NAME, "Sélectionnez une archive dans l'historique.", parent=self)
            return
        idx = os.path.join(path, "index.html")
        if not os.path.isfile(idx):
            try:
                write_local_index(path, load_info(path))
            except Exception:
                logger.exception("index local")
        if os.path.isfile(idx):
            self._open_url(idx)
        else:
            messagebox.showwarning(APP_NAME, f"index.html introuvable:\n{idx}", parent=self)

    def open_selected_media(self):
        path = self._folder_path()
        if not path or not os.path.isdir(path):
            messagebox.showinfo(APP_NAME, "Sélectionnez une archive.", parent=self)
            return
        main = find_main_media(path)
        if main and self.player.state == "play":
            self.player.pause()
        if main:
            if main.lower().endswith(VIDEO_EXTS) and self._player() == "windows" and find_ffmpeg():
                c = self._codec_for(main)
                if c.get("vcodec") and not is_compatible(main, c):
                    r = messagebox.askyesnocancel(
                        APP_NAME,
                        f"Cette vidéo est en {codec_label(c)}.\nLe lecteur Windows risque de demander un codec "
                        "(« Extension vidéo AV1 »).\n\nOui = la convertir en MP4 compatible (H.264) maintenant\n"
                        "Non = l'ouvrir quand même\nAnnuler = ne rien faire", parent=self)
                    if r is None:
                        return
                    if r:
                        self.convert_selected_path(path)
                        return
            self._open_media(main, "média")
            return
        imgs = list_images(path)
        if imgs:
            self.open_path_safe(imgs[0], "image")
            return
        messagebox.showinfo(APP_NAME, "Aucun fichier média trouvé dans ce dossier.", parent=self)

    def convert_selected_path(self, path: str):
        folder = os.path.basename(path)
        title = next((str(e.get("title") or "") for e in self.entries if e.get("folder") == folder), folder)
        if self._enqueue_convert([(folder, title)]):
            self.status.set("🎬 Conversion lancée — la vidéo sera lisible dans le lecteur Windows ensuite.")

    def _entry_url(self) -> str:
        e = self._selected_entry()
        if not e:
            return ""
        info = self._preview_info if self._preview_entry is e else e
        return str(info.get("webpage_url") or info.get("url") or e.get("url") or "")

    def open_original(self):
        u = self._entry_url()
        if u:
            self._open_url(u)
        else:
            messagebox.showinfo(APP_NAME, "Aucune URL d'origine pour cette archive.", parent=self)

    def copy_link(self):
        u = self._entry_url()
        if u:
            self._copy_to_clipboard(u)

    def copy_folder_path(self):
        p = self._folder_path()
        if p:
            self._copy_to_clipboard(p)

    def save_tags_notes(self, quiet: bool = False):
        e = self._preview_entry
        if not e or not e.get("folder"):
            if not quiet:
                self.status.set("Sélectionnez une archive pour enregistrer tags/notes.")
            return
        tags, notes = self._tn_current()
        try:
            info = update_tags_notes(self.archive_root_path(), str(e["folder"]), tags, notes)
        except Exception as ex:
            logger.exception("tags/notes")
            if not quiet:
                messagebox.showerror(APP_NAME, f"Enregistrement impossible:\n{friendly_error(ex)}", parent=self)
            return
        e["tags"] = info.get("tags") or []
        e["notes"] = info.get("notes") or ""
        for x in self.entries:
            if x.get("folder") == e.get("folder"):
                x["tags"], x["notes"] = e["tags"], e["notes"]
        if self._preview_entry is e:
            self._preview_info.update({"tags": e["tags"], "notes": e["notes"]})
            self._loaded_tn = self._tn_current()
            self.tags_var.set(", ".join(e["tags"]))
            self._loaded_tn = self._tn_current()
            self._render_tag_chips(e["tags"], self._preview_info.get("source_tags") or [])
            self.tn_state.configure(text=f"✅ Enregistré ({datetime.now().strftime('%H:%M:%S')})", fg=NC_OK)
        if not quiet:
            self.log(f"🏷 Tags/notes enregistrés : {', '.join(e['tags']) or '(aucun tag)'}")
            self.apply_filter()

    def rename_selected(self):
        e = self._selected_entry()
        if not e or not e.get("folder"):
            messagebox.showinfo(APP_NAME, "Sélectionnez une archive à renommer.", parent=self)
            return
        new_name = (self.name_var.get() or "").strip()
        if not new_name:
            messagebox.showwarning(APP_NAME, "Le nom ne peut pas être vide.", parent=self)
            return
        if self._preview_entry is e:
            self._autosave_tn()
        try:
            updated = rename_archive(self.archive_root_path(), str(e.get("folder")), new_name, log=self.log)
        except Exception as ex:
            logger.exception("rename")
            messagebox.showerror(APP_NAME, f"Renommage impossible:\n\n{ex}", parent=self)
            return
        self.last_folder = updated.get("folder")
        self._preview_entry = None
        self.refresh_list()
        self.select_folder(updated.get("folder"))
        self.log(f"✏ Renommé → {updated.get('folder')}")

    def delete_selected(self):
        ents = self._selected_entries()
        if len(ents) > 1:
            folders = [str(x.get("folder")) for x in ents if x.get("folder")]
            listing = "\n".join(f"• {str(x.get('title') or x.get('folder'))[:70]}" for x in ents[:10])
            more = f"\n… et {len(ents) - 10} autre(s)" if len(ents) > 10 else ""
            if not messagebox.askyesno(APP_NAME, f"Supprimer définitivement ces {len(folders)} archives ?\n\n"
                                       f"{listing}{more}\n\nLes dossiers et leurs fichiers seront effacés.",
                                       parent=self, icon="warning"):
                return
            try:
                self.player.stop()
                n = delete_archives(self.archive_root_path(), folders)
                self.log(f"🗑 {n} archive(s) supprimée(s).")
            except Exception as ex:
                logger.exception("delete many")
                messagebox.showerror(APP_NAME, f"Suppression impossible:\n{friendly_error(ex)}", parent=self)
            self._preview_entry = None
            self.refresh_list()
            if self._visible:
                self.select_folder(self._visible[0].get("folder"))
            else:
                self.clear_preview()
            return
        e = self._selected_entry()
        if not e or not e.get("folder"):
            return
        folder = str(e["folder"])
        path = os.path.join(self.archive_root_path(), folder)
        if not messagebox.askyesno(
            APP_NAME,
            f"Supprimer définitivement cette archive ?\n\n{e.get('title') or folder}\n{folder}\n\n"
            "Le dossier et ses fichiers seront effacés.",
            parent=self, icon="warning",
        ):
            return
        try:
            self.player.stop()
            if os.path.isdir(path):
                shutil.rmtree(path)
            entries = [x for x in load_archive_index(self.archive_root_path()) if x.get("folder") != folder]
            save_archive_index(self.archive_root_path(), entries)
            if self.last_folder == folder:
                self.last_folder = None
            self._preview_entry = None
            self.log(f"🗑 Supprimé: {folder}")
            self.refresh_list()
            if self._visible:
                self.select_folder(self._visible[0].get("folder"))
            else:
                self.clear_preview()
        except Exception as ex:
            logger.exception("delete")
            messagebox.showerror(APP_NAME, f"Suppression impossible:\n{friendly_error(ex)}", parent=self)

    # ------------------------------------------------------------ champ URL
    def paste_and_archive(self):
        """Lit le presse-papiers, affiche le lien, valide http(s), lance l'archivage."""
        try:
            clip = self.clipboard_get()
        except tk.TclError:
            messagebox.showinfo(APP_NAME, "Le presse-papiers est vide ou illisible.", parent=self)
            return
        clip = (clip or "").strip()
        urls = extract_urls(clip)
        if not urls:
            preview = clip if len(clip) <= 200 else clip[:200] + "…"
            messagebox.showwarning(
                APP_NAME,
                "Le presse-papiers ne contient pas de lien http:// ou https:// valide.\n\n"
                f"Contenu:\n{preview or '(vide)'}",
                parent=self,
            )
            return
        self._url_ph = False
        self.url_text.delete("1.0", "end")
        self.url_text.insert("1.0", "\n".join(urls))
        self.url_text.see("1.0")
        self._clip_last = clip
        self.enqueue_urls(urls)

    def _on_paste_archive(self, _evt=None):
        self.paste_and_archive()
        return "break"

    def _on_select_all(self, _evt=None):
        if self._url_ph:
            return "break"
        self.url_text.tag_add("sel", "1.0", "end-1c")
        self.url_text.mark_set("insert", "1.0")
        return "break"

    def _ctx_paste(self):
        try:
            clip = self.clipboard_get()
        except tk.TclError:
            return
        self._url_clear_ph()
        try:
            self.url_text.delete("sel.first", "sel.last")
        except tk.TclError:
            pass
        self.url_text.insert("insert", clip or "")

    def _ctx_copy(self):
        if self._url_ph:
            return
        try:
            self._copy_to_clipboard(self.url_text.get("sel.first", "sel.last"))
        except tk.TclError:
            pass

    def _ctx_cut(self):
        self._ctx_copy()
        try:
            self.url_text.delete("sel.first", "sel.last")
        except tk.TclError:
            pass

    def _ctx_clear(self):
        self._url_ph = False
        self.url_text.delete("1.0", "end")
        self.url_text.focus_set()

    def _show_url_menu(self, event):
        try:
            self._url_menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                self._url_menu.grab_release()
            except Exception:
                pass
        return "break"

    def _on_enter_archive(self, _evt=None):
        self.enqueue_from_text()
        return "break"

    def enqueue_from_text(self, clear_field: bool = False):
        urls = extract_urls(self._url_content())
        if not urls:
            messagebox.showinfo(APP_NAME, "Collez au moins un lien http(s) dans le champ\n"
                                "(ou cliquez « 📋 Coller et archiver »).", parent=self)
            return
        self.enqueue_urls(urls)
        if clear_field:
            self.url_text.delete("1.0", "end")

    # ------------------------------------------------------------ lot
    def open_batch_dialog(self):
        win = tk.Toplevel(self)
        win.title(f"{APP_NAME} — plusieurs liens")
        win.configure(bg=NC_BG)
        win.geometry("900x560")
        win.transient(self)
        try:
            win.iconphoto(False, self._icon_img)
        except Exception:
            pass
        tk.Label(win, text="📝 Colle une liste de liens (un par ligne, ou du texte contenant des liens)",
                 bg=NC_BG, fg=NC_HI, font=FONT_UI).pack(anchor="w", padx=10, pady=(10, 4))
        fr, txt = self._scrolled_text(win, height=18, bg=NC_ENTRY_BG, fg=NC_ENTRY_FG, font=FONT_UI, wrap="none")
        fr.pack(fill="both", expand=True, padx=10)
        cnt = tk.StringVar(value="0 lien détecté")
        row = tk.Frame(win, bg=NC_BG)
        row.pack(fill="x", padx=10, pady=8)
        tk.Label(row, textvariable=cnt, bg=NC_BG, fg=NC_FG, font=FONT_SM).pack(side="left")

        def _count(*_):
            n = len(extract_urls(txt.get("1.0", "end")))
            cnt.set(f"{n} lien{'s' if n > 1 else ''} détecté{'s' if n > 1 else ''}")

        def _paste():
            try:
                txt.insert("insert", self.clipboard_get())
            except tk.TclError:
                pass
            _count()

        def _go():
            urls = extract_urls(txt.get("1.0", "end"))
            if not urls:
                messagebox.showinfo(APP_NAME, "Aucun lien http(s) détecté.", parent=win)
                return
            win.destroy()
            n = self.enqueue_urls(urls)
            if n:
                self._show_bottom("queue")

        txt.bind("<KeyRelease>", _count)
        txt.bind("<<Paste>>", lambda e: self.after(10, _count))
        self._btn(row, "📥 Archiver tout", _go, hi=True, font=FONT_UI).pack(side="right", padx=4)
        self._btn(row, "Annuler", win.destroy).pack(side="right", padx=4)
        self._btn(row, "📋 Coller", _paste).pack(side="right", padx=4)
        txt.focus_set()
        self._batch_win = win
        return win

    # ------------------------------------------------------------ file d'attente
    def _active_keys(self) -> set:
        return {j.get("key") or normalize_url(j["url"]) for j in self.jobs if j["status"] in ("attente", "cours")}

    def archive_text_as_page(self):
        urls = extract_urls(self._url_content())
        if not urls:
            try:
                urls = extract_urls(self.clipboard_get())
            except tk.TclError:
                urls = []
        if not urls:
            messagebox.showinfo(APP_NAME, "Colle d'abord un lien dans le champ.", parent=self)
            return
        self.enqueue_urls(urls, extra={"page_mode": True})

    def enqueue_urls(self, urls: List[str], ask_dups: bool = True, extra: Optional[Dict[str, Any]] = None) -> int:
        clean: List[str] = []
        seen = set()
        active = self._active_keys()
        for u in urls:
            u = u.strip()
            if not u:
                continue
            if not re.match(r"^https?://", u, re.I):
                u = "https://" + u
            k = normalize_url(u)
            self._clip_seen.add(k)
            if k in seen:
                continue
            seen.add(k)
            if k in active:
                self.log(f"Déjà dans la file : {u}")
                continue
            clean.append(u)
        if not clean:
            return 0
        dups = {u: find_duplicates(self.entries, u) for u in clean}
        dups = {u: d for u, d in dups.items() if d}
        if dups and ask_dups:
            if len(clean) == 1:
                d = dups[clean[0]][0]
                r = messagebox.askyesnocancel(
                    APP_NAME,
                    "Ce lien est déjà archivé :\n\n"
                    f"« {d.get('title') or d.get('folder')} »\n"
                    f"archivé le {fmt_iso(d.get('archived_at'))}"
                    + (f"  ({len(dups[clean[0]])} copies)" if len(dups[clean[0]]) > 1 else "") + "\n\n"
                    "Oui = ouvrir l'archive existante\n"
                    "Non = re-archiver quand même\n"
                    "Annuler = ne rien faire",
                    parent=self,
                )
                if r is None:
                    return 0
                if r:
                    self.select_folder(d.get("folder"))
                    self.status.set("Archive existante affichée dans l'aperçu.")
                    return 0
            else:
                listing = "\n".join(f"• {(d[0].get('title') or d[0].get('folder'))[:70]}" for d in list(dups.values())[:8])
                more = f"\n… et {len(dups) - 8} autre(s)" if len(dups) > 8 else ""
                r = messagebox.askyesnocancel(
                    APP_NAME,
                    f"{len(dups)} lien(s) sur {len(clean)} sont déjà archivés :\n\n{listing}{more}\n\n"
                    "Oui = ignorer les doublons (archiver seulement les nouveaux)\n"
                    "Non = tout archiver quand même\n"
                    "Annuler = ne rien faire",
                    parent=self,
                )
                if r is None:
                    return 0
                if r:
                    clean = [u for u in clean if u not in dups]
                    if not clean:
                        self.status.set("Tous les liens étaient déjà archivés.")
                        return 0
        opts = self._job_opts()
        if extra:
            opts.update(extra)
        start = False
        with self._jobs_lock:
            for u in clean:
                self._job_seq += 1
                self.jobs.append({"id": self._job_seq, "url": u, "status": "attente", "pct": 0.0,
                                  "title": "", "folder": "", "error": "", "detail": "", "opts": dict(opts)})
            if not self._worker_running:
                self._worker_running = True
                start = True
        for u in clean:
            self.log(f"En file: {u}")
        self._refresh_queue_view()
        self._show_bottom("queue", auto=True)
        if start:
            threading.Thread(target=self._worker, daemon=True).start()
        else:
            self.status.set(f"{len(clean)} lien(s) ajouté(s) à la file (archivage en cours).")
        return len(clean)

    def _job_values(self, j):
        pct = f"{j['pct']:.0f}%" if j["status"] in ("cours", "ok") else ""
        label = j["title"] or j["url"]
        if j["status"] == "echec" and j.get("error"):
            label = f"{label} — {j['error']}"
        elif j["status"] == "cours" and j.get("detail"):
            label = f"{label} — {j['detail']}"
        return (JOB_LABELS.get(j["status"], j["status"]), pct, label)

    def _refresh_queue_view(self):
        sel = self.qtree.selection()
        self.qtree.delete(*self.qtree.get_children())
        for j in self.jobs:
            self.qtree.insert("", "end", iid=f"j{j['id']}", values=self._job_values(j))
        for s in sel:
            if self.qtree.exists(s):
                self.qtree.selection_set(s)
        self._refresh_bottom_labels()
        self._update_states()

    def _job_changed(self, j):
        iid = f"j{j['id']}"
        if self.qtree.exists(iid):
            self.qtree.item(iid, values=self._job_values(j))
        else:
            self._refresh_queue_view()
        if j["status"] == "cours":
            try:
                self.prog.set_mood("remux" if j.get("conv_mode") in ("remux", "audio") else "normal")
            except Exception:
                pass
            self.prog.configure(value=j["pct"])
            name = (j["title"] or j["url"])[:70]
            if j.get("conv_mode"):
                self.prog_var.set(f"{j.get('detail') or '🎬 Conversion…'} — {name.lstrip('🎬 ')}")
            else:
                self.prog_var.set(f"⬇ {name} — {j.get('detail') or 'Préparation…'}")
            self.cancel_btn.configure(state="normal")
        else:
            self._refresh_queue_view()

    def _make_hook(self, job):
        state = {"t": 0.0, "q": -1}

        def hook(d):
            st = d.get("status")
            if st == "downloading":
                tot = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                done = d.get("downloaded_bytes") or 0
                pct = None
                if tot:
                    pct = min(100.0, done * 100.0 / tot)
                elif d.get("fragment_count"):
                    pct = min(100.0, (d.get("fragment_index") or 0) * 100.0 / max(1, d["fragment_count"]))
                now = time.time()
                if now - state["t"] < 0.25 and (pct or 0) < 99.9:
                    return
                state["t"] = now
                if pct is not None:
                    job["pct"] = pct
                parts = []
                if pct is not None:
                    parts.append(f"{pct:.0f} %")
                if tot:
                    parts.append(f"{human_size(done)} / {human_size(tot)}")
                if d.get("speed"):
                    parts.append(f"{human_size(d['speed'])}/s")
                if d.get("eta") is not None:
                    parts.append(f"reste {human_duration(d['eta']) if d['eta'] else '0:00'}")
                job["detail"] = " · ".join(parts) or "Téléchargement…"
                info = d.get("info_dict") or {}
                if info.get("title") and not job["title"]:
                    job["title"] = str(info.get("title"))
                if pct is not None and int(pct // 25) > state["q"]:
                    state["q"] = int(pct // 25)
                    self.log(f"Téléchargement {pct:.0f} %")
                self.ui(lambda: self._job_changed(job))
            elif st == "converting":
                job["pct"] = float(d.get("pct") or 0)
                job["conv_mode"] = str(d.get("mode") or "encode")
                job["detail"] = "🎬 " + conv_detail(d)
                self.ui(lambda: self._job_changed(job))
            elif st == "finished":
                state["q"] = -1
                job["detail"] = "Traitement (fusion, miniature, storyboard)…"
                self.log(f"Fichier: {os.path.basename(d.get('filename') or '')}")
                self.ui(lambda: self._job_changed(job))
        return hook

    def _worker(self):
        while True:
            with self._jobs_lock:
                job = next((j for j in self.jobs if j["status"] == "attente"), None)
                if job is None:
                    self._worker_running = False
                    break
                job["status"] = "cours"
                job["pct"] = 0.0
                job["detail"] = "Analyse du lien…"
            self._cancel_event.clear()
            self.ui(lambda j=job: self._job_changed(j))
            o = job["opts"]
            if job.get("kind") == "convert":
                self._run_convert_job(job)
                self.ui(lambda j=job: self._job_changed(j))
                continue
            if job.get("kind") == "whisper":
                self._run_whisper_job(job)
                self.ui(lambda j=job: self._job_changed(j))
                continue
            try:
                info = archive_url(
                    job["url"], o["root"], self.log, cookies_browser=o.get("cookies"),
                    progress_hook=self._make_hook(job), quality=o.get("quality", "best"),
                    subtitles=o.get("subtitles", True), storyboard=o.get("storyboard", True),
                    cancel_event=self._cancel_event, auto_convert=o.get("auto_convert", True),
                    web_capture=o.get("web_capture", True), use_fx=o.get("use_fx", True),
                    page_mode=bool(o.get("page_mode")),
                )
                entry = register_archive(o["root"], info)
                job.update(status="ok", pct=100.0, title=str(entry.get("title") or ""),
                           folder=str(entry.get("folder") or ""), detail="")
                self.last_folder = entry.get("folder")
                self._run_stats["ok"] += 1
                self._run_stats["last_title"] = job["title"]
                self.log(f"✅ Archivé: {entry['folder']}")
                self.ui(lambda e=entry: self._on_job_ok(e))
            except ArchiveCancelled:
                job.update(status="annule", detail="")
                self._run_stats["annule"] += 1
                self.log("⛔ Archivage annulé.")
            except Exception as e:
                logger.exception("archivage %s", job["url"])
                job.update(status="echec", error=friendly_error(e), detail="")
                self._run_stats["echec"] += 1
                self.log(f"❌ Échec: {friendly_error(e)}", "error")
            self.ui(lambda j=job: self._job_changed(j))
        self.ui(self._on_queue_done)

    def _run_convert_job(self, job):
        """Exécuté dans le thread worker : conversion MP4 compatible d'une archive."""
        o = job["opts"]
        fp = os.path.join(o["root"], job["folder"])

        def stats(s):
            job["pct"] = float(s.get("pct") or 0)
            job["conv_mode"] = str(s.get("mode") or "encode")
            job["detail"] = "🎬 " + conv_detail(s)
            self.ui(lambda: self._job_changed(job))
        try:
            r = fix_folder_codecs(fp, self.log, cancel_event=self._cancel_event, stats=stats)
            if r == "cancel":
                job.update(status="annule", detail="")
                self._run_stats["annule"] += 1
                return
            job.update(status="ok", pct=100.0, detail="déjà compatible" if r == "skip" else "")
            self._run_stats["ok"] += 1
            self._run_stats["last_title"] = job["title"]
            if r == "skip":
                self.log(f"Déjà compatible : {job['folder']}")
            self._codec_cache.clear()
            self.ui(lambda f=job["folder"]: self._after_convert(f))
        except Exception as e:
            logger.exception("conversion %s", job["folder"])
            job.update(status="echec", error=friendly_error(e), detail="")
            self._run_stats["echec"] += 1
            self.log(f"❌ Conversion : {friendly_error(e)}", "error")

    def _after_convert(self, folder):
        cur = self._preview_entry.get("folder") if self._preview_entry else None
        self._preview_entry = None
        self.refresh_list()
        if cur:
            self.select_folder(cur)
        elif folder:
            self.select_folder(folder)

    def _enqueue_convert(self, items: List[Tuple[str, str]]) -> int:
        """items = [(folder, titre)] → tâches « convert » dans la file (une à la fois, annulables)."""
        active = self._active_keys()
        opts = self._job_opts()
        added = 0
        start = False
        with self._jobs_lock:
            for folder, title in items:
                if "conv:" + folder in active:
                    continue
                self._job_seq += 1
                self.jobs.append({"id": self._job_seq, "kind": "convert", "key": "conv:" + folder,
                                  "url": f"🎬 MP4 compatible : {folder}", "status": "attente", "pct": 0.0,
                                  "title": f"🎬 {title or folder}", "folder": folder, "error": "",
                                  "detail": "", "opts": dict(opts)})
                added += 1
            if added and not self._worker_running:
                self._worker_running = True
                start = True
        if added:
            self._refresh_queue_view()
            self._show_bottom("queue", auto=True)
        if start:
            threading.Thread(target=self._worker, daemon=True).start()
        return added

    def convert_selected(self):
        e = self._selected_entry()
        path = self._folder_path(e)
        if not e or not path or not os.path.isdir(path):
            messagebox.showinfo(APP_NAME, "Sélectionnez une archive vidéo.", parent=self)
            return
        if not find_ffmpeg():
            messagebox.showwarning(APP_NAME, "ffmpeg est requis pour la conversion.", parent=self)
            return
        main = find_main_media(path)
        if not main or not main.lower().endswith(VIDEO_EXTS):
            messagebox.showinfo(APP_NAME, "Cette archive ne contient pas de vidéo.", parent=self)
            return
        c = self._codec_for(main)
        if is_compatible(main, c):
            if not messagebox.askyesno(APP_NAME, f"La vidéo est déjà compatible ({codec_label(c)}, MP4).\n\n"
                                       "La vérifier / reconvertir quand même ?", parent=self):
                return
        n = self._enqueue_convert([(str(e.get("folder")), str(e.get("title") or ""))])
        if n:
            self.status.set("🎬 Conversion ajoutée à la file — ferme le lecteur vidéo s'il lit ce fichier.")

    def fix_all_codecs(self):
        if not find_ffmpeg():
            messagebox.showwarning(APP_NAME, "ffmpeg est requis pour la conversion.", parent=self)
            return
        root = self.archive_root_path()
        self.status.set("🔎 Analyse des codecs des archives…")

        def scan():
            try:
                todo = scan_incompatible(root)
            except Exception as ex:
                logger.exception("scan codecs")
                msg = friendly_error(ex)
                self.ui(lambda: messagebox.showerror(APP_NAME, f"Analyse impossible:\n{msg}", parent=self))
                return

            def ask():
                if not todo:
                    messagebox.showinfo(APP_NAME, "✅ Toutes les vidéos archivées sont déjà en MP4 H.264 compatible.",
                                        parent=self)
                    self.status.set("✅ Toutes les vidéos sont compatibles.")
                    return
                titles = {str(e.get("folder")): str(e.get("title") or "") for e in self.entries}
                listing = "\n".join(f"• {titles.get(f, f)[:60]}  ({lab})" for f, lab in todo[:10])
                more = f"\n… et {len(todo) - 10} autre(s)" if len(todo) > 10 else ""
                if messagebox.askyesno(APP_NAME, f"{len(todo)} vidéo(s) ne sont pas lisibles par le lecteur Windows :\n\n"
                                       f"{listing}{more}\n\nLes convertir en MP4 H.264 + AAC maintenant ?\n"
                                       "(le fichier est remplacé ; ferme le lecteur vidéo avant)", parent=self):
                    self._enqueue_convert([(f, titles.get(f, f)) for f, _l in todo])
            self.ui(ask)
        threading.Thread(target=scan, daemon=True).start()

    def _codec_for(self, video: str) -> Dict[str, Any]:
        try:
            key = (video, os.path.getmtime(video))
        except OSError:
            return {}
        if key not in self._codec_cache:
            self._codec_cache[key] = probe_codecs(video)
        return self._codec_cache[key]

    def _check_codec_async(self, path: str, video: str):
        try:
            key = (video, os.path.getmtime(video))
        except OSError:
            return
        if key in self._codec_cache:
            self._show_codec_banner(path, video, self._codec_cache[key])
            return

        def job():
            c = probe_codecs(video)
            self._codec_cache[key] = c
            self.ui(lambda: self._show_codec_banner(path, video, c))
        threading.Thread(target=job, daemon=True).start()

    def _show_codec_banner(self, path: str, video: str, c: Dict[str, Any]):
        if self._preview_path != path:
            return
        if c.get("vcodec") and not is_compatible(video, c):
            self.codec_msg.configure(text=f"⚠ Vidéo {codec_label(c)} : le lecteur Windows peut demander un codec "
                                          f"(« Extension vidéo AV1 »). Convertis-la en MP4 H.264.",
                                     wraplength=max(200, self._preview_width() - 300))
            self.codec_banner.pack(fill="x", padx=8, pady=(6, 0), after=self._codec_anchor)
        else:
            self.codec_banner.pack_forget()
        if c.get("vcodec"):
            res = self._preview_info.get("resolution") or ""
            if c.get("width") and c.get("height") and not res:
                res = f"{c['width']}x{c['height']}"
            self._set_card("resolution", f"{res or '—'} · {codec_label(c)}")

    def _player(self) -> str:
        p = self.cfg.get("player") or "windows"
        return p if p in self._players else "windows"

    def _open_media(self, path: str, kind: str = "média") -> bool:
        if path.lower().endswith(VIDEO_EXTS + AUDIO_EXTS):
            ok, err = open_media(path, self._player())
            if not ok:
                messagebox.showerror(APP_NAME, err or f"Impossible d'ouvrir le {kind}.", parent=self)
            else:
                self.status.set(f"▶ Lecture : {os.path.basename(path)} ({PLAYER_LABELS.get(self._player())})")
            return ok
        return self.open_path_safe(path, kind)

    def _on_job_ok(self, entry):
        self._preview_entry = None
        self.refresh_list()
        if not self.select_folder(entry.get("folder")):
            self.show_preview(entry)
        # storyboard tout de suite après l'archivage (arrière-plan), même si une autre archive est affichée
        try:
            path = os.path.join(self.archive_root_path(), str(entry.get("folder") or ""))
            main = find_main_media(path) if entry.get("folder") else None
            if main and main.lower().endswith(VIDEO_EXTS) and not list_storyboard(path) and find_ffmpeg() \
                    and not self._folder_converting(path):
                self._start_storyboard(path)
        except Exception:
            logger.exception("storyboard après archivage")

    def _on_queue_done(self):
        s = self._run_stats
        total = s["ok"] + s["echec"] + s["annule"]
        self.prog.configure(value=0)
        if total == 0:
            return
        if total == 1 and s["ok"] == 1:
            msg = f"Archivé : {s['last_title']}"
        else:
            msg = f"Terminé : {s['ok']} OK" + (f", {s['echec']} échec(s)" if s["echec"] else "") + \
                  (f", {s['annule']} annulé(s)" if s["annule"] else "")
        self.prog_var.set("✅ " + msg if not s["echec"] else "⚠ " + msg)
        self.status.set(("✅ " if not s["echec"] else "⚠ ") + msg)
        self.log("File terminée — " + msg)
        if self.notif_var.get():
            notify_desktop(APP_NAME, msg)
        failed = bool(s["echec"])
        self._run_stats = {"ok": 0, "echec": 0, "annule": 0, "last_title": ""}
        self._refresh_queue_view()
        if self._bottom_auto and not failed:
            self.after(6000, lambda: (self._collapse_bottom()
                                      if self._bottom_auto and not self._worker_running else None))

    def cancel_current(self):
        if any(j["status"] == "cours" for j in self.jobs):
            self._cancel_event.set()
            self.status.set("⛔ Annulation demandée…")
        else:
            self.status.set("Aucun archivage en cours.")

    def _selected_job(self):
        sel = self.qtree.selection()
        if not sel:
            return None
        jid = int(sel[0][1:])
        return next((j for j in self.jobs if j["id"] == jid), None)

    def remove_selected_job(self):
        j = self._selected_job()
        if not j:
            return
        if j["status"] == "cours":
            self.cancel_current()
            return
        with self._jobs_lock:
            self.jobs = [x for x in self.jobs if x is not j]
        self._refresh_queue_view()

    def retry_selected_job(self):
        j = self._selected_job()
        if not j or j["status"] not in ("echec", "annule"):
            self.status.set("Sélectionnez un lien en échec ou annulé pour réessayer.")
            return
        with self._jobs_lock:
            j.update(status="attente", pct=0.0, error="", detail="", opts=self._job_opts())
            start = not self._worker_running
            if start:
                self._worker_running = True
        self._refresh_queue_view()
        if start:
            threading.Thread(target=self._worker, daemon=True).start()

    def clear_done_jobs(self):
        with self._jobs_lock:
            self.jobs = [j for j in self.jobs if j["status"] in ("attente", "cours")]
        self._refresh_queue_view()

    def _on_job_double(self, _e=None):
        j = self._selected_job()
        if j and j.get("folder"):
            self.select_folder(j["folder"])
        elif j and j["status"] == "echec":
            messagebox.showinfo(APP_NAME, f"{j['url']}\n\n{j.get('error')}\n\nDétails : archiveur.log", parent=self)

    # ------------------------------------------------------------ presse-papiers
    def _toggle_clip_watch(self):
        self._persist_opts()
        if self.clip_var.get():
            try:
                self._clip_last = self.clipboard_get()
            except Exception:
                self._clip_last = ""
            if not self._clip_job:
                self._clip_job = self.after(1000, self._clip_poll)
            self.status.set("📋 Surveillance du presse-papiers activée — copie un lien pour l'archiver.")
        else:
            if self._clip_job:
                try:
                    self.after_cancel(self._clip_job)
                except Exception:
                    pass
            self._clip_job = None
            self._hide_clip_banner()
            self.status.set("Surveillance du presse-papiers désactivée.")

    def _clip_poll(self):
        self._clip_job = None
        if not self.clip_var.get():
            return
        try:
            txt = self.clipboard_get()
        except Exception:
            txt = ""
        if txt != self._clip_last:
            self._clip_last = txt
            if txt and len(txt) < 20000 and re.match(r"^\s*(https?://|www\.)", txt, re.I):
                try:
                    self._on_clip_urls(extract_urls(txt))
                except Exception:
                    logger.exception("clip")
        self._clip_job = self.after(1000, self._clip_poll)

    def _on_clip_urls(self, urls: List[str]):
        active = self._active_keys()
        fresh = []
        for u in urls:
            k = normalize_url(u)
            if k in self._clip_seen or k in active:
                continue
            self._clip_seen.add(k)
            fresh.append(u)
        if not fresh:
            return
        dups = find_duplicates(self.entries, fresh[0]) if len(fresh) == 1 else []
        if self.clip_auto_var.get() and not dups:
            self.log(f"📋 Lien copié détecté → archivage auto ({len(fresh)})")
            self.enqueue_urls(fresh, ask_dups=False)
            return
        self._clip_pending = fresh
        for w in self.clip_btns.winfo_children():
            w.destroy()
        if dups:
            d = dups[0]
            self.clip_msg.configure(text=f"📋 Lien copié déjà archivé : « {(d.get('title') or '')[:80]} »")
            self._btn(self.clip_btns, "📂 Ouvrir l'existante",
                      lambda f=d.get("folder"): (self._hide_clip_banner(), self.select_folder(f))).pack(side="left", padx=2)
            self._btn(self.clip_btns, "🔁 Re-archiver",
                      lambda: (self._hide_clip_banner(), self.enqueue_urls(self._clip_pending, ask_dups=False))).pack(side="left", padx=2)
        else:
            shown = fresh[0] if len(fresh) == 1 else f"{len(fresh)} liens"
            self.clip_msg.configure(text=f"📋 Lien copié détecté : {shown[:110]}")
            self._btn(self.clip_btns, "📥 Archiver", lambda: (self._hide_clip_banner(),
                      self.enqueue_urls(self._clip_pending)), hi=False).pack(side="left", padx=2)
        self._btn(self.clip_btns, "Ignorer", self._hide_clip_banner).pack(side="left", padx=2)
        self.clip_banner.pack(fill="x", pady=2, after=self._clip_anchor)
        try:
            self.bell()
        except Exception:
            pass

    def _hide_clip_banner(self):
        try:
            self.clip_banner.pack_forget()
        except Exception:
            pass

    # ------------------------------------------------------------ v5 : lecteur intégré (UI)
    def _build_player_bar(self, body):
        self._pbar_anchor = tk.Frame(body, bg=NC_BG, height=0)
        self._pbar_anchor.pack(fill="x")
        self.pbar = tk.Frame(body, bg=NC_PANEL, bd=0)
        self.pos_var = tk.DoubleVar(value=0.0)
        self.pos_scale = ttk.Scale(self.pbar, from_=0, to=1, variable=self.pos_var, orient="horizontal",
                                   style="Arch.Horizontal.TScale")
        self.pos_scale.pack(fill="x", padx=10, pady=(6, 1))
        self.pos_scale.bind("<ButtonPress-1>", self._seek_press)
        self.pos_scale.bind("<B1-Motion>", self._seek_motion)
        self.pos_scale.bind("<ButtonRelease-1>", self._seek_release)
        Tooltip(self.pos_scale, "Clique ou glisse pour te déplacer dans la vidéo")
        row = FlowFrame(self.pbar, bg=NC_PANEL, padx=3, pady=2)
        row.pack(fill="x", padx=6, pady=(0, 5))
        self._pl_row = row
        self.pl_play = row.add(self._btn(row, "▶ Lecture", self.player_toggle, hi=True, font=FONT_UI),
                               "Lecture / pause (Ctrl+Espace, ou clic sur l'image)")
        self.pl_stop = row.add(self._btn(row, "⏹", self.player_stop, font=FONT_UI), "Arrêter et revenir au début")
        self.pl_back = row.add(self._btn(row, "⏪ 10 s", lambda: self.player_skip(-10), font=FONT_SM),
                               "Reculer de 10 secondes (Ctrl+←)")
        self.pl_fwd = row.add(self._btn(row, "10 s ⏩", lambda: self.player_skip(10), font=FONT_SM),
                              "Avancer de 10 secondes (Ctrl+→)")
        self.pl_time = tk.Label(row, text="0:00 / 0:00", bg=NC_PANEL, fg=NC_HI, font=FONT_MONO, padx=6)
        row.add(self.pl_time, "Position / durée")
        self.pl_mute = row.add(self._btn(row, "🔊", self.player_mute, font=FONT_SM), "Couper / remettre le son")
        self.vol_var = tk.DoubleVar(value=float(self.cfg.get("volume", 80) or 0))
        self.vol_scale = ttk.Scale(row, from_=0, to=100, variable=self.vol_var, orient="horizontal", length=96,
                                   style="Arch.Horizontal.TScale", command=lambda v: self._vol_label())
        self.vol_scale.bind("<ButtonRelease-1>", lambda e: self._apply_volume())
        row.add(self.vol_scale, "Volume")
        self.pl_vol = tk.Label(row, text="", bg=NC_PANEL, fg=NC_FG, font=FONT_SM, width=4, anchor="w")
        row.add(self.pl_vol)
        self.pl_big = row.add(self._btn(row, "⛶ Grande fenêtre", self.player_bigwin, font=FONT_SM),
                              "Ouvrir la vidéo dans une grande fenêtre avec ses propres boutons, à la position actuelle\n"
                              "(Espace = pause, F = plein écran, ←/→ = ±5 s, ↑/↓ = volume, M = muet, Échap = fermer).\n"
                              "Double-clic sur l'image = pareil.")
        self.pl_note = tk.Label(self.pbar, text="", bg=NC_PANEL, fg=NC_DIM, font=FONT_SM, anchor="w", justify="left")
        self._seek_drag = False
        self._muted = False
        self._vol_label()
        self.player = LightPlayer(self, self.thumb_label, self._on_player_update)
        self.player.volume = int(self.vol_var.get())
        self._player_media = ""
        self._player_loaded = ""
        self._tr_cur = -1

    def _vol_label(self):
        try:
            v = int(float(self.vol_var.get()))
            self.pl_vol.configure(text=f"{v}%")
            self.pl_mute.configure(text="🔇" if (self._muted or v == 0) else "🔊")
        except Exception:
            pass

    def _apply_volume(self):
        v = int(float(self.vol_var.get()))
        self.cfg["volume"] = v
        save_cfg(self.cfg)
        if v > 0 and self._muted:
            self._muted = False
        self.player.set_volume(v, self._muted)
        self._vol_label()

    def player_mute(self):
        self._muted = not self._muted
        self.player.set_volume(int(float(self.vol_var.get())), self._muted)
        self._vol_label()
        self.status.set("🔇 Son coupé" if self._muted else "🔊 Son rétabli")

    def _integrated_ok(self, main: Optional[str] = None) -> bool:
        main = main if main is not None else self._player_media
        if not main or not bool(self.cfg.get("integrated_player", True)):
            return False
        if not find_ffmpeg():
            return False
        if main.lower().endswith(VIDEO_EXTS):
            return HAS_PIL
        return bool(find_ffplay())  # audio seul : il faut ffplay

    def _thumb_box(self) -> Tuple[int, int]:
        avail_w = self._preview_width()
        vis_h = self.pscroll.canvas.winfo_height()
        max_h = max(150, min(int(vis_h * 0.62), vis_h - 130)) if vis_h > 50 else 420
        return avail_w, max_h

    def _setup_player(self, main: Optional[str], info: Dict[str, Any]):
        """Prépare la barre du lecteur pour l'archive affichée (chargement réel au 1er ▶)."""
        try:
            self.player.stop()
        except Exception:
            logger.exception("arrêt lecteur")
        self._player_media = main or ""
        self._player_loaded = ""
        self._tr_cur = -1
        if not self._integrated_ok(main):
            self.pbar.pack_forget()
            return
        dur = 0.0
        try:
            dur = float(info.get("duration") or 0)
        except (TypeError, ValueError):
            dur = 0.0
        self.pos_scale.configure(to=max(1.0, dur))
        self.pos_var.set(0.0)
        self.pl_time.configure(text=f"{fmt_ts(0)} / {fmt_ts(dur) if dur else '—'}")
        self.pl_play.configure(text="▶ Lecture")
        is_vid = main.lower().endswith(VIDEO_EXTS)
        self._pl_row.set_visible(self.pl_big, is_vid)
        note = ""
        if not find_ffplay():
            note = "Son indisponible (ffplay introuvable) — la vidéo est lue sans le son."
        elif not is_vid:
            note = "🎵 Audio seul — lecture du son dans l'aperçu."
        self.pl_note.configure(text=note)
        if note:
            self.pl_note.pack(fill="x", padx=10, pady=(0, 4))
        else:
            self.pl_note.pack_forget()
        self.pbar.pack(fill="x", padx=8, pady=(0, 0), after=self._pbar_anchor)

    def _ensure_loaded(self) -> bool:
        if self._player_loaded == self._player_media and self.player.path:
            return True
        if not self._player_media or not os.path.isfile(self._player_media):
            return False
        self.status.set("⏳ Préparation de la lecture…")
        self.update_idletasks()
        ok = self.player.load(self._player_media, self._preview_info)
        self._player_loaded = self._player_media
        self.player.volume = int(float(self.vol_var.get()))
        self.player.muted = self._muted
        if self.player.duration:
            self.pos_scale.configure(to=max(1.0, self.player.duration))
        return ok or bool(self.player.duration)

    def play_selected(self):
        """▶ Lire : lecteur intégré si possible, sinon lecteur externe."""
        main = find_main_media(self._preview_path) if self._preview_path else None
        if main and main != self._player_media:
            self._setup_player(main, self._preview_info)
        if main and self._integrated_ok(main):
            self.player_toggle()
        else:
            self.open_selected_media()

    def player_toggle(self):
        if not self._integrated_ok():
            if self._preview_entry:
                self.open_selected_media()
            return
        st = self.player.state
        if st == "play":
            self.player.pause()
            return
        if not self._ensure_loaded():
            self.status.set("Lecture impossible : média illisible (voir 🧰 Outils → Vérifier les archives).")
            return
        w, h = self._thumb_box()
        at = float(self.pos_var.get()) if st in ("stop", "pause", "end") else None
        if st == "end" or (self.player.duration and at is not None and at >= self.player.duration - 0.3):
            at = 0.0
        self.player.play(w, h, at=at)
        if self.player.last_error:
            self.log(f"Lecteur : {self.player.last_error}", "warning")
        self.status.set(f"▶ Lecture intégrée : {os.path.basename(self._player_media)}")

    def player_stop(self):
        if self.player.state != "stop":
            self.player.stop()
        self.pos_var.set(0.0)
        self._on_player_update(0.0, self.player.duration or float(self.pos_scale.cget("to") or 0), "stop")
        self._render_thumb()

    def player_skip(self, delta: float):
        if not self._integrated_ok():
            return
        if not self._ensure_loaded():
            return
        cur = self.player.current() if self.player.state == "play" else float(self.pos_var.get())
        w, h = self._thumb_box()
        self.player.seek(max(0.0, cur + delta), w, h)

    def player_seek_to(self, t: float, play: bool = True):
        """Utilisé par la transcription (clic sur un horodatage)."""
        if not self._integrated_ok():
            self.status.set(f"Horodatage {fmt_ts(t)} — lecteur intégré indisponible.")
            return
        if not self._ensure_loaded():
            return
        w, h = self._thumb_box()
        self.pscroll.to_top()
        if play:
            self.player.play(w, h, at=t)
        else:
            self.player.seek(t, w, h)

    def _scale_value_at(self, x: int) -> float:
        wpx = max(1, self.pos_scale.winfo_width() - 16)
        frac = min(1.0, max(0.0, (x - 8) / float(wpx)))
        return frac * float(self.pos_scale.cget("to") or 1)

    def _seek_press(self, e):
        if not self._integrated_ok():
            return "break"
        self._seek_drag = True
        self.pos_var.set(self._scale_value_at(e.x))
        self._show_time(float(self.pos_var.get()))
        return "break"

    def _seek_motion(self, e):
        if self._seek_drag:
            self.pos_var.set(self._scale_value_at(e.x))
            self._show_time(float(self.pos_var.get()))
        return "break"

    def _seek_release(self, e):
        if not self._seek_drag:
            return "break"
        self._seek_drag = False
        t = self._scale_value_at(e.x)
        if self._ensure_loaded():
            w, h = self._thumb_box()
            self.player.seek(t, w, h)
        return "break"

    def _show_time(self, pos: float):
        dur = self.player.duration or float(self.pos_scale.cget("to") or 0)
        self.pl_time.configure(text=f"{fmt_ts(pos)} / {fmt_ts(dur) if dur else '—'}")

    def _on_player_update(self, pos: float, dur: float, state: str):
        if not self._seek_drag:
            self.pos_var.set(pos)
            self._show_time(pos)
        self.pl_play.configure(text="⏸ Pause" if state == "play" else "▶ Lecture")
        self._tr_follow(pos)

    def player_bigwin(self):
        """Grande fenêtre ffplay (redimensionnable) à la position courante."""
        main = self._player_media or (find_main_media(self._preview_path) if self._preview_path else None)
        if not main or not main.lower().endswith(VIDEO_EXTS):
            return
        pos = self.player.current() if self.player.state == "play" else float(self.pos_var.get() or 0)
        bw = getattr(self, "_bigwin", None)
        if bw is not None:
            try:
                if bw.winfo_exists():
                    bw.deiconify(); bw.lift(); bw.focus_force()
                    return
            except Exception:
                pass
        if HAS_PIL and find_ffmpeg() and bool(self.cfg.get("integrated_player", True)):
            # grande fenêtre Tk avec ses propres contrôles (play/pause, position, volume, plein écran)
            if self.player.state == "play":
                self.player.pause()
            title = f"{APP_NAME} — {str(self._preview_info.get('title') or os.path.basename(main))[:80]}"
            try:
                self._bigwin = BigPlayerWindow(self, main, self._preview_info or {}, pos, title)
                self.status.set("⛶ Grande fenêtre : Espace = pause, F = plein écran, ←/→ = ±5 s, ↑/↓ = volume, "
                                "M = muet, Échap = fermer.")
                return
            except Exception:
                logger.exception("grande fenêtre Tk")
                self._bigwin = None
        fpl = find_ffplay()
        if not fpl:
            self.open_selected_media()
            return
        if self.player.state == "play":
            self.player.pause()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w = min(1280, int(sw * 0.7))
        h = int(w * 9 / 16)
        title = f"{APP_NAME} — {str(self._preview_info.get('title') or os.path.basename(main))[:80]}"
        cmd = [fpl, "-hide_banner", "-loglevel", "error", "-autoexit", "-window_title", title,
               "-x", str(w), "-y", str(h), "-volume", str(0 if self._muted else int(float(self.vol_var.get())))]
        if pos > 0.5:
            cmd += ["-ss", f"{pos:.2f}"]
        cmd.append(main)
        try:
            kw: Dict[str, Any] = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
                                  "stderr": subprocess.DEVNULL, "close_fds": True}
            if sys.platform.startswith("win"):
                kw["creationflags"] = CREATE_NO_WINDOW  # pas de console ; la fenêtre vidéo reste visible
            subprocess.Popen(cmd, **kw)
            self.status.set("⛶ Grande fenêtre ouverte (F = plein écran, Espace = pause, Échap = fermer).")
        except Exception as ex:
            logger.exception("ffplay fenêtre")
            messagebox.showerror(APP_NAME, f"Impossible d'ouvrir la fenêtre vidéo :\n{ex}", parent=self)

    def _bigwin_closed(self, pos: float):
        """Retour de la grande fenêtre : la petite reprend à la même position (en pause)."""
        self._bigwin = None
        try:
            if self._player_media and self._integrated_ok() and pos > 0 and self._ensure_loaded():
                w, h = self._thumb_box()
                self.player.seek(pos, w, h)
            self.status.set(f"⛶ Grande fenêtre fermée à {fmt_ts(pos)}.")
        except Exception:
            logger.exception("retour position")

    def _on_thumb_click(self):
        if not self._preview_entry:
            return
        if self._player_media and self._integrated_ok():
            self.player_toggle()
        else:
            self.open_selected_media()

    # ------------------------------------------------------------ v5 : transcription
    def _build_transcript_box(self, body):
        box = tk.Frame(body, bg=NC_BG)
        self.tr_box = box
        self.tr_title = self._section(box, "🗣 Transcription")
        bar = FlowFrame(box)
        bar.pack(fill="x", padx=8)
        self.tr_bar = bar
        g = tk.Frame(bar, bg=NC_BG)
        tk.Label(g, text="🔎", bg=NC_BG, fg=NC_FG, font=FONT_SM).pack(side="left")
        self.tr_search = tk.StringVar()
        ent = tk.Entry(g, textvariable=self.tr_search, width=24, bg=NC_ENTRY_BG, fg=NC_ENTRY_FG,
                       insertbackground=NC_FG, font=FONT_SM)
        ent.pack(side="left", padx=3)
        ent.bind("<Return>", lambda e: (self._tr_find_next(), "break")[1])
        self.tr_entry = ent
        self.tr_search.trace_add("write", lambda *_: self._tr_schedule_hl())
        bar.add(g, "Chercher dans la transcription (Entrée = occurrence suivante)")
        self.tr_count = tk.Label(bar, text="", bg=NC_BG, fg=NC_DIM, font=FONT_SM)
        bar.add(self.tr_count)
        self._tr_btns: Dict[str, Any] = {}
        for key, txt, cmd, tip in (
            ("next", "⬇ Suivant", self._tr_find_next, "Occurrence suivante"),
            ("copy", "📋 Copier", self._tr_copy, "Copier toute la transcription (avec horodatages)"),
            ("open", "📄 transcript.txt", self._tr_open, "Ouvrir le fichier texte de la transcription"),
        ):
            self._tr_btns[key] = bar.add(self._btn(bar, txt, cmd), tip)
        self._tr_btns["whisper"] = bar.add(self._btn(bar, "🎙 Transcrire (local)", self.transcribe_selected))
        self._whisper_tip = Tooltip(self._tr_btns["whisper"], "")
        trf, self.tr_text = self._scrolled_text(box, height=8, bg=NC_PANEL, fg=NC_TEXT, font=FONT_TEXT)
        trf.pack(fill="x", padx=8, pady=(3, 0))
        self.tr_frame = trf
        t = self.tr_text
        t.configure(state="disabled", cursor="xterm", padx=8, pady=6, spacing1=1, spacing3=2)
        t.tag_configure("ts", foreground=NC_HI, underline=True)
        t.tag_configure("cur", background=NC_CARD)
        t.tag_configure("hit", background=NC_SEL, foreground=NC_ON_SEL)
        t.tag_configure("hitcur", background=NC_HI, foreground=NC_ON_HI)
        t.tag_raise("hit")
        t.tag_raise("hitcur")
        t.tag_bind("ts", "<Enter>", lambda e: t.configure(cursor="hand2"))
        t.tag_bind("ts", "<Leave>", lambda e: t.configure(cursor="xterm"))
        t.bind("<Button-1>", lambda e: t.focus_set())
        t.bind("<Button-3>", self._tr_menu_popup)
        self._tr_menu = self._menu()
        self._tr_menu.add_command(label="Copier la sélection", command=lambda: self._text_copy_sel(self.tr_text))
        self._tr_menu.add_command(label="Copier toute la transcription", command=self._tr_copy)
        self.tr_msg = tk.Label(box, text="", bg=NC_BG, fg=NC_DIM, font=FONT_SM, anchor="w", justify="left")
        self.tr_msg.pack(fill="x", padx=8)
        self._tr_cues: List[Tuple[float, str]] = []
        self._tr_starts: List[float] = []
        self._tr_hits: List[str] = []
        self._tr_hit_i = -1
        self._tr_hl_job = None

    def _text_copy_sel(self, w):
        try:
            self._copy_to_clipboard(w.get("sel.first", "sel.last"))
        except tk.TclError:
            pass

    def _tr_menu_popup(self, event):
        try:
            self._tr_menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                self._tr_menu.grab_release()
            except Exception:
                pass
        return "break"

    def _render_transcript(self, path: str, main: Optional[str]):
        self._tr_cues, self._tr_starts, self._tr_hits, self._tr_hit_i, self._tr_cur = [], [], [], -1, -1
        d: Dict[str, Any] = {}
        if path and os.path.isdir(path):
            try:
                d = load_transcript(path)
            except Exception:
                logger.exception("transcription")
                d = {}
        cues = list(d.get("cues") or [])
        if not cues and not main:
            self.tr_box.pack_forget()
            return
        self.tr_box.pack(fill="x", after=self._tr_anchor)
        self._tr_cues = cues
        self._tr_starts = [c[0] for c in cues]
        if cues and self._preview_entry is not None and not self._preview_entry.get("has_transcript"):
            self._preview_entry["has_transcript"] = True
        t = self.tr_text
        t.configure(state="normal")
        t.delete("1.0", "end")
        for tag in t.tag_names():
            if tag.startswith("tsc_"):
                t.tag_delete(tag)
        wbtn = self._tr_btns["whisper"]
        has_w = whisper_available()
        if cues:
            src = str(d.get("source") or "sous-titres")
            lang = str(d.get("lang") or "?")
            self.tr_title.configure(text=f"🗣 Transcription ({len(cues)} passages · {src} · langue : {lang})")
            for i, (ts, txt) in enumerate(cues):
                tg = f"tsc_{i}"
                t.insert("end", f"[{fmt_ts(ts)}]", ("ts", tg))
                t.insert("end", f"  {txt}\n", (f"line_{i}",))
                t.tag_bind(tg, "<Button-1>", lambda e, s=ts: (self.player_seek_to(s), "break")[1])
            self.tr_msg.configure(text="Clic sur un horodatage [m:ss] = lire la vidéo à cet endroit · "
                                       "le passage en cours est surligné pendant la lecture")
            t.configure(height=max(4, min(14, len(cues) + 1)))
            self.tr_frame.pack(fill="x", padx=8, pady=(3, 0), before=self.tr_msg)
        else:
            self.tr_title.configure(text="🗣 Transcription")
            self.tr_frame.pack_forget()
            if has_w:
                msg = ("Aucune transcription (pas de sous-titres pour ce média). "
                       "« 🎙 Transcrire (local) » la crée sur ce PC avec Whisper, sans envoyer le son en ligne.")
            else:
                msg = ("Aucune transcription : ce média n'a pas de sous-titres. Les vidéos avec sous-titres "
                       "(YouTube…) sont transcrites automatiquement. Pour transcrire les autres, installer "
                       "faster-whisper (setup_padawan.bat, option Whisper).")
            self.tr_msg.configure(text=msg)
        t.configure(state="disabled")
        for k in ("next", "copy", "open"):
            self.tr_bar.set_visible(self._tr_btns[k], bool(cues))
        self.tr_bar.set_visible(self.tr_entry.master, bool(cues))
        self.tr_bar.set_visible(self.tr_count, bool(cues))
        self.tr_bar.set_visible(wbtn, bool(main))
        busy = any(j.get("kind") == "whisper" and j.get("folder") == os.path.basename(path)
                   and j["status"] in ("attente", "cours") for j in self.jobs)
        if not has_w:
            wbtn.configure(state="disabled", text="🎙 Transcrire (local)")
            self._whisper_tip.text = ("Transcription locale avec Whisper — module faster-whisper non installé.\n"
                                      "Lance setup_padawan.bat et réponds O à « Whisper » (≈ 200 Mo), puis relance.")
        elif busy:
            wbtn.configure(state="disabled", text="🎙 Transcription en cours…")
            self._whisper_tip.text = "Transcription dans la file d'attente."
        else:
            wbtn.configure(state="normal", text="🎙 Retranscrire (local)" if cues else "🎙 Transcrire (local)")
            self._whisper_tip.text = (f"Transcrire le son sur ce PC (Whisper « {self.cfg.get('whisper_model', 'base')} », "
                                      "aucun envoi en ligne). Peut prendre plusieurs minutes ; annulable dans la file.")
        if self.tr_search.get():
            self._tr_highlight()
        else:
            self.tr_count.configure(text="")

    def _tr_schedule_hl(self):
        if self._tr_hl_job:
            try:
                self.after_cancel(self._tr_hl_job)
            except Exception:
                pass
        self._tr_hl_job = self.after(180, self._tr_highlight)

    def _tr_highlight(self):
        self._tr_hl_job = None
        t = self.tr_text
        t.tag_remove("hit", "1.0", "end")
        t.tag_remove("hitcur", "1.0", "end")
        q = self.tr_search.get().strip()
        self._tr_hits, self._tr_hit_i = [], -1
        if not q or not self._tr_cues:
            self.tr_count.configure(text="")
            return
        idx = "1.0"
        n = 0
        while n < 2000:
            pos = t.search(q, idx, nocase=True, stopindex="end")
            if not pos:
                break
            end = f"{pos}+{len(q)}c"
            t.tag_add("hit", pos, end)
            self._tr_hits.append(pos)
            idx = end
            n += 1
        self.tr_count.configure(text=f"{n} résultat{'s' if n > 1 else ''}" if n else "aucun résultat",
                                fg=NC_FG if n else NC_ERR)
        if n:
            self._tr_find_next()

    def _tr_find_next(self):
        if not self._tr_hits:
            return
        t = self.tr_text
        self._tr_hit_i = (self._tr_hit_i + 1) % len(self._tr_hits)
        pos = self._tr_hits[self._tr_hit_i]
        t.tag_remove("hitcur", "1.0", "end")
        t.tag_add("hitcur", pos, f"{pos}+{len(self.tr_search.get().strip())}c")
        t.see(pos)
        self.tr_count.configure(text=f"{self._tr_hit_i + 1} / {len(self._tr_hits)}")

    def _tr_follow(self, pos: float):
        if not self._tr_starts:
            return
        import bisect
        i = bisect.bisect_right(self._tr_starts, pos + 0.05) - 1
        if i == self._tr_cur:
            return
        t = self.tr_text
        t.tag_remove("cur", "1.0", "end")
        self._tr_cur = i
        if i >= 0:
            t.tag_add("cur", f"{i + 1}.0", f"{i + 1}.end")
            t.see(f"{i + 1}.0")

    def _tr_copy(self):
        if self._tr_cues:
            self._copy_to_clipboard("\n".join(f"[{fmt_ts(ts)}] {x}" for ts, x in self._tr_cues))

    def _tr_open(self):
        p = os.path.join(self._preview_path, TRANSCRIPT_TXT) if self._preview_path else ""
        if p and os.path.isfile(p):
            self.open_path_safe(p, "fichier")

    def transcribe_selected(self):
        e = self._preview_entry
        path = self._preview_path
        if not e or not path or not find_main_media(path):
            return
        if not whisper_available():
            messagebox.showinfo(APP_NAME, "La transcription locale utilise Whisper (module faster-whisper), "
                                "qui n'est pas installé.\n\nLance setup_padawan.bat et réponds O à la question "
                                "« Whisper », puis relance l'Archiveur.", parent=self)
            return
        if load_transcript(path).get("cues") and not messagebox.askyesno(
                APP_NAME, "Cette archive a déjà une transcription.\nLa refaire avec Whisper (remplace l'actuelle) ?",
                parent=self):
            return
        folder = str(e.get("folder"))
        self._enqueue_task("whisper", folder, f"🎙 Transcription : {e.get('title') or folder}")
        self._render_transcript(path, find_main_media(path))

    def _enqueue_task(self, kind: str, folder: str, title: str) -> bool:
        key = f"{kind}:{folder}"
        if key in self._active_keys():
            self.status.set("Déjà dans la file d'attente.")
            return False
        opts = self._job_opts()
        start = False
        with self._jobs_lock:
            self._job_seq += 1
            self.jobs.append({"id": self._job_seq, "kind": kind, "key": key, "url": title, "status": "attente",
                              "pct": 0.0, "title": title, "folder": folder, "error": "", "detail": "",
                              "opts": dict(opts)})
            if not self._worker_running:
                self._worker_running = True
                start = True
        self._refresh_queue_view()
        self._show_bottom("queue", auto=True)
        if start:
            threading.Thread(target=self._worker, daemon=True).start()
        return True

    def _run_whisper_job(self, job):
        o = job["opts"]
        fp = os.path.join(o["root"], job["folder"])

        def prog(p):
            job["pct"] = p
            job["detail"] = f"🎙 {p:.0f} %"
            self.ui(lambda: self._job_changed(job))
        try:
            job["detail"] = "Chargement du modèle Whisper…"
            self.ui(lambda: self._job_changed(job))
            d = transcribe_whisper(fp, self.log, model_size=str(self.cfg.get("whisper_model") or "base"),
                                   progress=prog, cancel_event=self._cancel_event)
            refresh_entries(o["root"], [job["folder"]])
            job.update(status="ok", pct=100.0, detail=f"{len(d.get('cues') or [])} passages")
            self._run_stats["ok"] += 1
            self._run_stats["last_title"] = job["title"]
            self.log(f"🎙 Transcription terminée : {len(d.get('cues') or [])} passages ({d.get('lang') or '?'}).")
            self.ui(lambda f=job["folder"]: self._after_task(f))
        except ArchiveCancelled:
            job.update(status="annule", detail="")
            self._run_stats["annule"] += 1
        except Exception as e:
            logger.exception("whisper %s", job["folder"])
            job.update(status="echec", error=friendly_error(e), detail="")
            self._run_stats["echec"] += 1
            self.log(f"❌ Transcription : {friendly_error(e)}", "error")

    def _after_task(self, folder: str):
        self.entries = load_archive_index(self.archive_root_path())
        self.apply_filter()
        if self._preview_entry and self._preview_entry.get("folder") == folder:
            self._preview_entry = next((x for x in self.entries if x.get("folder") == folder), self._preview_entry)
            main = find_main_media(self._preview_path)
            self._render_transcript(self._preview_path, main)
            self._render_extracts(self._preview_path, main)
            self._render_files()

    # ------------------------------------------------------------ v5 : extraits et captures
    def _build_extracts_box(self, body):
        box = tk.Frame(body, bg=NC_BG)
        self.ex_box = box
        self.ex_title = self._section(box, "✂ Extraits et captures")
        bar = FlowFrame(box)
        bar.pack(fill="x", padx=8)
        bar.add(self._btn(bar, "✂ Outils média…", self.open_media_tools, hi=True),
                "Créer une capture d'image, un extrait vidéo, un MP3 ou un GIF à partir de cette archive")
        self.ex_open = bar.add(self._btn(bar, "📁 Dossier extraits", self._open_extracts_dir),
                               "Ouvrir le sous-dossier extraits/ de l'archive")
        self.ex_bar = bar
        self.ex_flow = FlowFrame(box, padx=6, pady=6)
        self.ex_flow.pack(fill="x", padx=8, pady=(4, 0))
        self.ex_msg = tk.Label(box, text="", bg=NC_BG, fg=NC_DIM, font=FONT_SM, anchor="w", justify="left")
        self.ex_msg.pack(fill="x", padx=8)
        self._ex_photos: List[Any] = []

    def _open_extracts_dir(self):
        d = os.path.join(self._preview_path, EXTRACTS_DIR) if self._preview_path else ""
        if d and os.path.isdir(d):
            self.open_path_safe(d, "dossier")

    def _render_extracts(self, path: str, main: Optional[str]):
        for w in list(self.ex_flow._items):
            try:
                w.destroy()
            except Exception:
                pass
        self.ex_flow._items = []
        self.ex_flow.configure(height=1)
        self._ex_photos = []
        files = list_extracts(path) if path and os.path.isdir(path) else []
        if not main and not files:
            self.ex_box.pack_forget()
            return
        self.ex_box.pack(fill="x", after=self._ex_anchor)
        n = len(files)
        self.ex_title.configure(text=f"✂ Extraits et captures ({n})" if n else "✂ Extraits et captures")
        self.ex_bar.set_visible(self.ex_open, bool(n))
        if not n:
            self.ex_msg.configure(text="Aucun extrait pour l'instant. Astuce : mets la vidéo en pause à l'endroit "
                                       "voulu, puis « ✂ Outils média » → « = position du lecteur ».")
        else:
            self.ex_msg.configure(text="Clic = ouvrir · clic droit = copier le chemin / afficher dans le dossier")
        for p in files[:40]:
            name = os.path.basename(p)
            cell = tk.Frame(self.ex_flow, bg=NC_PANEL, bd=1, relief="solid", cursor="hand2")
            low = name.lower()
            ph = None
            if HAS_PIL and low.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
                try:
                    im = Image.open(p)
                    im.thumbnail((150, 100))
                    ph = ImageTk.PhotoImage(im.convert("RGB"))
                except Exception:
                    ph = None
            if ph is not None:
                self._ex_photos.append(ph)
                tk.Label(cell, image=ph, bg=NC_PANEL).pack(padx=3, pady=(3, 0))
            else:
                tk.Label(cell, text=file_icon(name), bg=NC_PANEL, fg=NC_HI, font=FONT_BIG, width=4).pack(padx=3, pady=(6, 0))
            short = wrap_name(name, 24)
            try:
                sz = human_size(os.path.getsize(p))
            except OSError:
                sz = ""
            tk.Label(cell, text=f"{short}\n{sz}", bg=NC_PANEL, fg=NC_FG, font=FONT_SM, justify="center").pack(padx=4, pady=(0, 3))
            for wdg in [cell] + list(cell.winfo_children()):
                wdg.bind("<Button-1>", lambda e, pp=p: self._open_media(pp, "fichier"))
                wdg.bind("<Button-3>", lambda e, pp=p: self._show_link_menu(e, "path", pp))
            self.ex_flow.add(cell, name)
        self.ex_flow.after_idle(self.ex_flow.relayout)

    # ------------------------------------------------------------ v5 : documents d'une page web
    def _render_docs(self, path: str, info: Dict[str, Any]):
        for w in list(self.doc_flow._items):
            try:
                w.destroy()
            except Exception:
                pass
        self.doc_flow._items = []
        docs = []
        if path and os.path.isdir(path):
            for fname, label, tip in (
                ("lecture.html", "📖 Lecture", "Texte de l'article, mise en page lisible (hors ligne)"),
                ("page.html", "🌐 Page complète", "Copie autonome de la page (images locales, sans scripts)"),
                (str(info.get("page_pdf") or "page_complete.pdf"), "📑 PDF", "Page imprimée en PDF (Edge/Chrome)"),
                (str(info.get("page_capture") or "capture_page.png"), "🖼 Capture", "Capture d'écran de la page entière"),
                ("article.txt", "📝 Texte brut", "Texte de l'article (.txt)"),
            ):
                fp = os.path.join(path, fname)
                if fname and os.path.isfile(fp):
                    docs.append((fp, label, tip))
        if not docs:
            self.doc_box.pack_forget()
            return
        words = info.get("words")
        try:
            wtxt = f" ({int(words):,} mots)".replace(",", "\u202f") if words else ""
        except (TypeError, ValueError):
            wtxt = ""
        lab = tk.Label(self.doc_flow, text=f"📰 Page web archivée{wtxt} :", bg=NC_BG, fg=NC_HI, font=FONT_SM)
        self.doc_flow.add(lab)
        for fp, label, tip in docs:
            self.doc_flow.add(self._btn(self.doc_flow, label, lambda p=fp: self._open_doc(p)), tip)
        self.doc_box.pack(fill="x", after=self._doc_anchor)
        self.doc_flow.after_idle(self.doc_flow.relayout)

    def _open_doc(self, p: str):
        if p.lower().endswith((".html", ".htm")):
            self._open_url(p)
        else:
            self.open_path_safe(p, "fichier")

    def _online_text(self, info: Dict[str, Any]) -> str:
        st = str(info.get("online_status") or "")
        if not st:
            return "jamais vérifié — clic pour vérifier"
        ic, lab = GUI_ONLINE.get(st, ("?", st))
        txt = f"{ic} {lab}"
        det = str(info.get("online_detail") or "")
        when = fmt_iso(info.get("online_checked")) if info.get("online_checked") else ""
        if det:
            txt += f" ({det})"
        if when:
            txt += f" · vérifié le {when}"
        return txt

    def _sb_show(self, show: bool):
        parts = (self.sb_title, self.sb_title._line, self.sb_row, self.sb_msg)
        if show:
            if not self.sb_title.winfo_manager():
                prev = self._sb_anchor
                for w, kw in zip(parts, (dict(padx=8, pady=(12, 2)), dict(padx=8, pady=(0, 4)),
                                         dict(padx=8), dict(padx=8))):
                    w.pack(fill="x", after=prev, **kw)
                    prev = w
        else:
            for w in parts:
                w.pack_forget()

    def _collections_text(self, info: Dict[str, Any]) -> str:
        parts = []
        if info.get("favorite"):
            parts.append("★ Favori")
        cols = [c for c in (info.get("collections") or []) if isinstance(c, str)]
        if cols:
            parts.append(", ".join(cols))
        return " · ".join(parts) if parts else "— (clic pour classer)"

    def _refresh_preview_meta(self):
        """Met à jour favori / collections / en ligne de l'aperçu sans tout redessiner."""
        e = self._preview_entry
        if not e or not self._preview_path:
            return
        folder = e.get("folder")
        fresh = next((x for x in self.entries if x.get("folder") == folder), None)
        if fresh is not None:
            self._preview_entry = fresh
        info = load_info(self._preview_path)
        for k in ("favorite", "collections", "online_status", "online_detail", "online_checked", "tags"):
            self._preview_info[k] = info.get(k)
        self._set_card("online", self._online_text(self._preview_info), ("action", "online"))
        self._set_card("collections", self._collections_text(self._preview_info), ("action", "collections"))
        self._preview_info[COLL_SUGGEST_OFF] = info.get(COLL_SUGGEST_OFF)
        self._update_fav_button()
        self._update_suggest_banner()

    def _update_fav_button(self):
        b = self._act_btns.get("fav")
        if not b:
            return
        fav = bool(self._preview_info.get("favorite")) if self._preview_entry else False
        b.configure(text="★ Favori" if fav else "☆ Favori",
                    bg=NC_SEL if fav else NC_BTN, fg=NC_ON_SEL if fav else NC_BTN_FG)

    # ------------------------------------------------------------ v5 : sélection multiple / menus
    def _post_menu(self, widget, menu):
        try:
            x, y = widget.winfo_rootx(), widget.winfo_rooty() + widget.winfo_height()
            menu.tk_popup(x, y)
        finally:
            try:
                menu.grab_release()
            except Exception:
                pass

    def _tree_hover(self, event):
        iid = self.tree.identify_row(event.y)
        if iid and iid != getattr(self, "_hover_iid", None):
            self._hover_iid = iid
            e = self._iid_entry.get(iid)
            if e:
                self.status.set(f"{platform_label(e.get('platform'))} · {e.get('title') or e.get('folder')}"[:220])

    def _selected_entries(self) -> List[Dict[str, Any]]:
        out = [self._iid_entry[i] for i in self.tree.selection() if i in self._iid_entry]
        if not out and self._preview_entry:
            out = [self._preview_entry]
        return out

    def _selected_folders(self) -> List[str]:
        return [str(e.get("folder")) for e in self._selected_entries() if e.get("folder")]

    def _tree_select_all(self, _e=None):
        items = self.tree.get_children()
        if items:
            self._suppress_select = True
            self.tree.selection_set(items)
            self.after(10, lambda: setattr(self, "_suppress_select", False))
            self.status.set(f"{len(items)} archives sélectionnées — clic droit pour les actions groupées.")
            self._update_states()
        return "break"

    def _refresh_filter_values(self):
        plats = sorted({str(e.get("platform") or "web") for e in self.entries})
        self._plat_map = {PLAT_ALL_LABEL: ""}
        for p in plats:
            n = sum(1 for e in self.entries if str(e.get("platform") or "web") == p)
            self._plat_map[f"{platform_label(p)} ({n})"] = p
        cur = getattr(self, "_plat_map_prev", {}).get(self.plat_var.get(), "")
        self.plat_cb.configure(values=list(self._plat_map.keys()))
        self.plat_var.set(next((k for k, v in self._plat_map.items() if v == cur), PLAT_ALL_LABEL))
        self._plat_map_prev = dict(self._plat_map)
        cmap: Dict[str, str] = {COLL_ALL_LABEL: ""}
        nfav = sum(1 for e in self.entries if e.get("favorite"))
        ntr = sum(1 for e in self.entries if e.get("has_transcript"))
        noff = sum(1 for e in self.entries if e.get("online_status") in ("offline", "restricted"))
        nnone = sum(1 for e in self.entries if not e.get("collections"))
        for lab, key, n in (("★ Favoris", COLL_FAV, nfav), ("🗣 Avec transcription", COLL_TRANSCRIPT, ntr),
                            ("⚠ Plus en ligne", COLL_OFFLINE, noff), ("📥 Non classées", COLL_NONE, nnone)):
            cmap[f"{lab} ({n})"] = key
        counts: Dict[str, int] = {}
        for e in self.entries:
            for c in e.get("collections") or []:
                counts[c.lower()] = counts.get(c.lower(), 0) + 1
        for c in load_collections(self.archive_root_path(), self.entries):
            cmap[f"📚 {c} ({counts.get(c.lower(), 0)})"] = c
        cur_key = self._coll_map.get(self.coll_var.get(), self.cfg.get("collection_filter") or "")
        self._coll_map = cmap
        self.coll_cb.configure(values=list(cmap.keys()))
        lab = next((k for k, v in cmap.items() if v == cur_key), COLL_ALL_LABEL)
        self.coll_var.set(lab)
        self._fill_coll_side(counts, nnone, nfav)
