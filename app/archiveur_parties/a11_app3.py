# -*- coding: utf-8 -*-
# Partie de archiveur5.py (découpage v1.2.2, comportement inchangé).
# Chargée par archiveur5.py dans un espace de noms commun : ne pas lancer seule.
from __future__ import annotations

class _ArchiveurAppPartie3:
    """Méthodes de ArchiveurApp (partie 3/3)."""


    def _coll_key(self) -> str:
        return self._coll_map.get(self.coll_var.get(), "")

    def _on_coll_filter(self):
        self.cfg["collection_filter"] = self._coll_key()
        save_cfg(self.cfg)
        self._sync_coll_side()
        self.apply_filter()

    # ---------------------------------------------------------------- barre des collections (classement simple)
    def _fill_coll_side(self, counts: Dict[str, int], nnone: int, nfav: int):
        t = getattr(self, "coll_tree", None)
        if t is None:
            return
        self._coll_side_lock = True
        try:
            t.delete(*t.get_children())
            t.insert("", "end", iid="c::", text=f" 🗂 Toutes ({len(self.entries)})")
            t.insert("", "end", iid="c::" + COLL_NONE, text=f" 📥 Non classées ({nnone})",
                     tags=() if nnone else ("dim",))
            t.insert("", "end", iid="c::" + COLL_FAV, text=f" ★ Favoris ({nfav})", tags=() if nfav else ("dim",))
            for c in load_collections(self.archive_root_path(), self.entries):
                n = counts.get(c.lower(), 0)
                t.insert("", "end", iid="c::" + c, text=f" 📚 {c} ({n})", tags=() if n else ("dim",))
        except Exception:
            logger.exception("barre collections")
        finally:
            self._coll_side_lock = False
        self._sync_coll_side()
        self._side_autofit()

    def _side_autofit(self, force: bool = False):
        """Largeur juste assez pour les noms des collections (sauf si Marc a choisi une largeur)."""
        try:
            if getattr(self, "_side_w_saved", 0) and not force:
                return
            if not self._coll_side.winfo_manager():
                return
            f = tkfont.nametofont(FONT_UI, root=self)
            t = self.coll_tree
            texts = [t.item(i, "text") for i in t.get_children()] + ["📚 Collections"]
            w = max(f.measure(x) for x in texts) + 34
            w = max(120, min(w, int(self.winfo_width() * 0.22) or 260, 280))
            self._side_pane.paneconfigure(self._coll_side, width=w)
            if force:
                self._side_w_saved = 0
                self.cfg["coll_side_w"] = 0
                save_cfg(self.cfg)
        except Exception:
            logger.debug("largeur collections", exc_info=True)

    def _side_sash_saved(self, _e=None):
        try:
            if self._coll_side.winfo_manager():
                w = int(self._coll_side.winfo_width())
                if w > 50 and abs(w - (self._side_w_saved or 0)) > 3:
                    self._side_w_saved = w
                    self.cfg["coll_side_w"] = w
                    save_cfg(self.cfg)
        except Exception:
            pass

    def _sync_coll_side(self):
        t = getattr(self, "coll_tree", None)
        if t is None:
            return
        iid = "c::" + self._coll_key()
        self._coll_side_lock = True
        try:
            if t.exists(iid):
                if t.selection() != (iid,):
                    t.selection_set(iid)
                t.see(iid)
            else:
                t.selection_remove(*t.selection())
        except Exception:
            pass
        finally:
            self.after(10, lambda: setattr(self, "_coll_side_lock", False))

    def _on_coll_side(self, _e=None):
        if self._coll_side_lock:
            return
        sel = self.coll_tree.selection()
        if not sel:
            return
        key = sel[0][3:]
        lab = next((k for k, v in self._coll_map.items() if v == key), None)
        if lab is None or self.coll_var.get() == lab:
            return
        self.coll_var.set(lab)
        self._on_coll_filter()

    def _coll_side_menu(self, event):
        iid = self.coll_tree.identify_row(event.y)
        name = iid[3:] if iid and iid.startswith("c::") else ""
        m = self._menu()
        m.add_command(label="➕ Nouvelle collection…", command=self.new_collection)
        m.add_command(label="✨ Ranger tout automatiquement…", command=self.auto_classify)
        if self._auto_undo:
            m.add_command(label="↩ Annuler le dernier rangement automatique", command=self.undo_auto_classify)
        if name and not name.startswith("__"):
            m.add_separator()
            m.add_command(label=f"✏ Renommer « {name} »…", command=lambda: self.rename_collection(name))
            m.add_command(label=f"🗑 Supprimer « {name} » (les archives restent)",
                          command=lambda: self.delete_collection(name))
        try:
            m.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                m.grab_release()
            except Exception:
                pass
        return "break"

    def _toggle_coll_side(self):
        if self._coll_side.winfo_manager():
            self._side_pane.forget(self._coll_side)
            self._side_toggle.configure(text="▶ 📚")
        else:
            self._side_pane.add(self._coll_side, before=self._hist_main, minsize=100,
                                width=self._side_w_saved or 150, stretch="never")
            self._side_toggle.configure(text="◀")
            self.after(50, self._side_autofit)

    def rename_collection(self, name: str):
        new = self._ask_string(f"Nouveau nom pour la collection « {name} » :", initial=name, parent=self)
        new = re.sub(r"\s+", " ", (new or "")).strip()[:40]
        if not new or new == name:
            return
        root = self.archive_root_path()
        members = [str(e.get("folder")) for e in self.entries
                   if name.lower() in {c.lower() for c in (e.get("collections") or [])}]
        try:
            backup_index(root, min_interval=0)
            names = [n for n in load_collections(root, self.entries) if n.lower() != name.lower()]
            if new.lower() not in {n.lower() for n in names}:
                names.append(new)
            save_collections(root, names)
            for f in members:
                info = load_info(os.path.join(root, f))
                cols = [c for c in (info.get("collections") or []) if isinstance(c, str) and c.lower() != name.lower()]
                if new.lower() not in {c.lower() for c in cols}:
                    cols.append(new)
                update_info_fields(root, f, save_index=False, collections=cols)
            refresh_entries(root, members)
        except Exception as ex:
            logger.exception("renommer collection")
            messagebox.showerror(APP_NAME, f"Renommage impossible :\n{friendly_error(ex)}", parent=self)
        if self._coll_key().lower() == name.lower():
            self.cfg["collection_filter"] = new
        self.log(f"✏ Collection « {name} » → « {new} » ({len(members)} archive(s))")
        self._reload_entries()
        if self.cfg.get("collection_filter") == new:
            lab = next((k for k, v in self._coll_map.items() if v == new), COLL_ALL_LABEL)
            self.coll_var.set(lab)
            self._on_coll_filter()

    def _build_move_menu(self, parent=None):
        """Menu « Déplacer vers » : l'archive (ou la sélection) va dans UNE collection."""
        m = tk.Menu(parent or self, tearoff=0, bg=NC_PANEL, fg=NC_FG, activebackground=NC_SEL,
                    activeforeground=NC_ON_SEL, font=FONT_UI)
        names = load_collections(self.archive_root_path(), self.entries)
        sug = self._sug[1] if self._sug and len(self._selected_folders()) <= 1 else ""
        if sug and sug.lower() not in {n.lower() for n in names}:
            m.add_command(label=f"✨ {sug} (nouvelle, proposée)", command=lambda: self.move_selected_to(sug))
        for c in names:
            m.add_command(label=f"📚 {c}", command=lambda cc=c: self.move_selected_to(cc))
        if names or sug:
            m.add_separator()
        m.add_command(label="➕ Nouvelle collection…", command=self._move_to_new)
        m.add_command(label="📥 Non classée (retirer des collections)", command=lambda: self.move_selected_to(None))
        return m

    def _move_to_new(self):
        name = self._ask_string("Nom de la nouvelle collection :\n(ex. Animatrix, Santé, Musique, À revoir)",
                                parent=self)
        name = re.sub(r"\s+", " ", (name or "")).strip()[:40]
        if name:
            self.move_selected_to(name)

    def move_selected_to(self, name: Optional[str], folders: Optional[List[str]] = None):
        folders = folders or self._selected_folders()
        if not folders:
            return
        root = self.archive_root_path()
        try:
            if name:
                names = load_collections(root, self.entries)
                hit = next((n for n in names if n.lower() == name.lower()), None)
                if hit:
                    name = hit
                else:
                    save_collections(root, names + [name])
            n = move_to_collection(root, folders, name)
        except Exception as ex:
            logger.exception("déplacer collection")
            messagebox.showerror(APP_NAME, f"Classement impossible :\n{friendly_error(ex)}", parent=self)
            return
        msg = (f"📚 Rangé dans « {name} »" if name else "📥 Remis dans « Non classées »") + (f" ({n} archives)" if n > 1 else "")
        self.status.set(msg)
        self.log(msg)
        self._reload_entries()

    # ---------------------------------------------------------------- suggestion « Ranger dans X ? »
    def _hide_suggest_banner(self):
        self._sug = None
        try:
            self.sug_banner.pack_forget()
        except Exception:
            pass

    def _update_suggest_banner(self):
        e = self._preview_entry
        info = self._preview_info or {}
        if not e or not e.get("folder") or info.get("collections") or info.get(COLL_SUGGEST_OFF):
            self._hide_suggest_banner()
            return
        try:
            names = load_collections(self.archive_root_path(), self.entries)
            sug = suggest_collection(e, self.entries, names, info)
        except Exception:
            logger.exception("suggestion collection")
            sug = None
        if not sug:
            self._hide_suggest_banner()
            return
        self._sug = (str(e.get("folder")), sug[0])
        self.sug_msg.configure(text=f"📚 Ranger dans « {sug[0]} » ?   ({sug[1]})",
                               wraplength=max(200, self._preview_width() - 260))
        if not self.sug_banner.winfo_manager():
            self.sug_banner.pack(fill="x", padx=6, pady=(0, 4), before=self.pscroll)

    def _sug_accept(self):
        if not self._sug:
            return
        folder, name = self._sug
        self.move_selected_to(name, folders=[folder])

    def _sug_dismiss(self):
        if not self._sug:
            return
        folder, name = self._sug
        try:
            update_info_fields(self.archive_root_path(), folder, save_index=False, **{COLL_SUGGEST_OFF: name})
            self._preview_info[COLL_SUGGEST_OFF] = name
        except Exception:
            logger.exception("suggestion refusée")
        self._hide_suggest_banner()
        self.status.set("D'accord — je ne propose plus de collection pour cette archive.")

    # ---------------------------------------------------------------- « Ranger tout automatiquement »
    def auto_classify(self):
        root = self.archive_root_path()
        names = load_collections(root, self.entries)
        self.status.set("✨ Je regarde les archives non classées…")
        self.update_idletasks()
        try:
            plan = plan_auto_collections(self.entries, names, root)
        except Exception as ex:
            logger.exception("plan rangement")
            messagebox.showerror(APP_NAME, f"Rangement impossible :\n{friendly_error(ex)}", parent=self)
            return
        nonclass = sum(1 for e in self.entries if not e.get("collections"))
        if not plan:
            self.status.set("Rien à ranger automatiquement.")
            messagebox.showinfo(APP_NAME, ("Toutes tes archives sont déjà classées. 👍" if not nonclass else
                                           f"{nonclass} archive(s) non classée(s), mais je n'ai pas d'idée sûre "
                                           "pour elles.\n\nClic droit sur une archive → 📂 Déplacer vers la "
                                           "collection… pour la ranger toi-même."), parent=self)
            return
        title_of = {str(e.get("folder")): str(e.get("title") or e.get("folder")) for e in self.entries}
        groups: Dict[str, List[str]] = {}
        for f, n, _r in plan:
            groups.setdefault(n, []).append(f)
        win = self._dialog("ranger automatiquement", 760, 560, modal=True)
        self._auto_win = win
        rest = nonclass - len(plan)
        head = (f"Je propose de ranger {len(plan)} archive(s) non classée(s) dans {len(groups)} collection(s) :"
                + (f"\n{rest} archive(s) resteront dans « 📥 Non classées » (pas d'idée sûre)." if rest > 0 else "")
                + "\nTes archives déjà classées ne bougent pas. Tu pourras tout annuler d'un clic (↩).")
        tk.Label(win, text=head, bg=NC_BG, fg=NC_TEXT, font=FONT_UI, justify="left", anchor="w",
                 wraplength=720).pack(fill="x", padx=12, pady=(10, 6))
        fr, txt = self._scrolled_text(win, height=16, bg=NC_PANEL, fg=NC_TEXT, font=FONT_TEXT)
        fr.pack(fill="both", expand=True, padx=12, pady=4)
        txt.tag_configure("h", foreground=NC_HI, font=FONT_UI, spacing1=8)
        new_lower = {n.lower() for n in names}
        for n in sorted(groups, key=lambda k: (-len(groups[k]), k.lower())):
            mark = "" if n.lower() in new_lower else "  (nouvelle)"
            txt.insert("end", f"📚 {n} — {len(groups[n])}{mark}\n", ("h",))
            for f in groups[n]:
                txt.insert("end", f"     • {title_of.get(f, f)[:110]}\n")
        txt.configure(state="disabled")
        row = tk.Frame(win, bg=NC_BG)
        row.pack(fill="x", padx=12, pady=(4, 10))

        def go():
            win.destroy()
            self._apply_auto_plan(plan, names)
        self._btn(row, "✔ Ranger", go, hi=True, font=FONT_UI).pack(side="right", padx=(6, 0))
        self._btn(row, "Annuler", win.destroy, font=FONT_UI).pack(side="right")
        self.status.set("✨ Vérifie la proposition puis « ✔ Ranger ».")
        return win

    def _apply_auto_plan(self, plan: List[Tuple[str, str, str]], names: List[str]):
        root = self.archive_root_path()
        self.status.set("✨ Rangement en cours…")
        try:
            self.configure(cursor="watch")
            self.update_idletasks()
        except Exception:
            pass
        done: List[Tuple[str, str]] = []
        created: List[str] = []
        try:
            backup_index(root, min_interval=0)
            low = {n.lower() for n in names}
            for _f, n, _r in plan:
                if n.lower() not in low:
                    created.append(n)
                    low.add(n.lower())
            if created:
                save_collections(root, names + created)
            groups: Dict[str, List[str]] = {}
            for f, n, _r in plan:
                groups.setdefault(n, []).append(f)
            for n, fl in groups.items():
                set_collections(root, fl, add=n)
                done += [(f, n) for f in fl]
        except Exception as ex:
            logger.exception("rangement auto")
            messagebox.showerror(APP_NAME, f"Rangement interrompu :\n{friendly_error(ex)}\n\n"
                                 "Ce qui est déjà rangé peut être annulé (↩).", parent=self)
        finally:
            try:
                self.configure(cursor="")
            except Exception:
                pass
        self._auto_undo = {"done": done, "created": created}
        if done:
            self.undo_btn.pack(fill="x", padx=4, pady=(0, 4), after=self._undo_anchor)
        ncol = len({n for _f, n in done})
        msg = f"✅ {len(done)} archive(s) rangée(s) dans {ncol} collection(s) — « ↩ Annuler le rangement » si ça ne te plaît pas."
        self.status.set(msg)
        self.log(msg)
        self._reload_entries()

    def undo_auto_classify(self):
        u = self._auto_undo
        if not u:
            return
        root = self.archive_root_path()
        try:
            groups: Dict[str, List[str]] = {}
            for f, n in u.get("done") or []:
                groups.setdefault(n, []).append(f)
            for n, fl in groups.items():
                set_collections(root, [f for f in fl if os.path.isdir(os.path.join(root, f))], remove=n)
            ents = load_archive_index(root)
            used = {c.lower() for e in ents for c in (e.get("collections") or [])}
            drop = {c.lower() for c in u.get("created") or [] if c.lower() not in used}
            if drop:
                save_collections(root, [n for n in load_collections(root) if n.lower() not in drop])
        except Exception as ex:
            logger.exception("annuler rangement")
            messagebox.showerror(APP_NAME, f"Annulation impossible :\n{friendly_error(ex)}", parent=self)
            return
        self._auto_undo = None
        self.undo_btn.pack_forget()
        if self._coll_key() and not self._coll_key().startswith("__"):
            self.coll_var.set(COLL_ALL_LABEL)
            self.cfg["collection_filter"] = ""
        msg = "↩ Rangement annulé : les archives sont revenues dans « Non classées »."
        self.status.set(msg)
        self.log(msg)
        self._reload_entries()

    def _reload_entries(self):
        """Relit l'index (après une action groupée) sans rebalayer le disque."""
        self.entries = load_archive_index(self.archive_root_path())
        self._refresh_filter_values()
        self.apply_filter()
        self._refresh_preview_meta()

    def _show_hist_menu(self, event):
        iid = self.tree.identify_row(event.y)
        if iid and iid not in self.tree.selection():
            self.tree.selection_set(iid)
            self.tree.focus(iid)
            e = self._iid_entry.get(iid)
            if e:
                self.show_preview(e)
        ents = self._selected_entries()
        if not ents:
            return "break"
        m = self._hist_menu
        m.delete(0, "end")
        n = len(ents)
        allfav = all(e.get("favorite") for e in ents)
        if n == 1:
            e = ents[0]
            path = os.path.join(self.archive_root_path(), str(e.get("folder")))
            main = find_main_media(path)
            m.add_command(label="▶ Lire dans l'aperçu", command=self.play_selected,
                          state="normal" if (main or list_images(path)) else "disabled")
            m.add_command(label="↗ Ouvrir dans le lecteur externe", command=self.open_selected_media,
                          state="normal" if main else "disabled")
            m.add_command(label="📄 Page archive (index.html)", command=self.open_selected_index)
            m.add_command(label="📁 Ouvrir le dossier", command=self.open_selected_folder)
            m.add_command(label="🌐 Ouvrir l'original", command=self.open_original)
            m.add_separator()
        else:
            m.add_command(label=f"{n} archives sélectionnées", state="disabled")
            m.add_separator()
        m.add_command(label="☆ Retirer des favoris" if allfav else "★ Ajouter aux favoris  (Ctrl+D)",
                      command=self.toggle_favorite)
        m.add_cascade(label="📂 Déplacer vers la collection…" + ("" if n == 1 else f" ({n})"),
                      menu=self._build_move_menu(parent=m))
        m.add_cascade(label="📚 Collections (cocher plusieurs)", menu=self._build_coll_menu(parent=m))
        m.add_command(label="🏷 Ajouter des tags…", command=self.add_tags_selected)
        m.add_separator()
        if n == 1:
            m.add_command(label="📋 Copier le lien", command=self.copy_link)
            m.add_command(label="📋 Copier le résumé (titre, lien, auteur, tags)", command=self.copy_summary)
            m.add_command(label="📋 Copier le chemin du dossier", command=self.copy_folder_path)
        else:
            m.add_command(label=f"📋 Copier les {n} liens", command=self.copy_links_selected)
            m.add_command(label=f"📋 Copier les {n} résumés", command=self.copy_summary)
        m.add_command(label="📚 Envoyer au Grimoire…" + ("" if n == 1 else f" ({n})"),
                      command=self.send_to_grimoire)
        m.add_separator()
        m.add_command(label="📡 Vérifier si l'original est en ligne" if n == 1 else f"📡 Vérifier en ligne ({n})",
                      command=lambda: self.check_online_selected(False))
        m.add_command(label="📦 Exporter en ZIP…  (Ctrl+E)", command=lambda: self.export_zip_dialog("selection"))
        if n == 1:
            m.add_command(label="✂ Outils média (capture, extrait, MP3, GIF)…", command=self.open_media_tools)
            m.add_command(label="🎞 Refaire le storyboard", command=self.regen_storyboard)
        m.add_command(label="🎬 Convertir en MP4 compatible (H.264)" + ("" if n == 1 else f" ({n})"),
                      command=self.convert_selected_many)
        m.add_separator()
        if n == 1:
            m.add_command(label="✏ Renommer (F2)", command=self.rename_selected)
        m.add_command(label="🗑 Supprimer…" if n == 1 else f"🗑 Supprimer les {n} archives…", command=self.delete_selected)
        try:
            m.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                m.grab_release()
            except Exception:
                pass
        return "break"

    # ---------------------------------------------------------------- Grimoire (carnet de recherche)
    def _grimoire_script(self) -> str:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "grimoire1.py")

    def send_to_grimoire(self):
        """📚 Envoyer au Grimoire : choisir le sujet, puis creer la fiche directement dans grimoire.db
        (titre, texte, image, lien d'origine, copie locale « ✔ Permanent »). Marche Grimoire ouvert ou ferme."""
        ents = self._selected_entries()
        if not ents:
            messagebox.showinfo(APP_NAME, "Choisis d'abord une archive (ou plusieurs) dans la liste.", parent=self)
            return
        if not os.path.isfile(gr_db_path()):
            messagebox.showwarning(APP_NAME, f"Grimoire introuvable :\n{gr_db_path()}\n\nOuvre le Grimoire une première fois.", parent=self)
            return
        root = self.archive_root_path()
        infos = []
        for e in ents:
            info = dict(e)
            try:
                info.update(load_info(os.path.join(root, str(e.get("folder")))))
            except Exception:
                pass
            infos.append(info)
        # doublons : lien deja dans une fiche ?
        try:
            c = gr_connect()
            dups = []
            for e, i in zip(list(ents), list(infos)):
                d = gr_find_url(c, str(i.get("url") or i.get("webpage_url") or ""))
                if d:
                    dups.append((e, i, d))
            c.close()
        except Exception as ex:
            messagebox.showerror(APP_NAME, f"Lecture du Grimoire impossible : {ex}", parent=self)
            return
        if dups:
            if len(ents) == 1:
                d = dups[0][2]
                if messagebox.askyesno(APP_NAME, f"Ce lien est déjà dans le Grimoire :\n« {d['title']} »\n\nL'ouvrir dans le Grimoire ?",
                                       parent=self):
                    gr_open_item(d["id"], self._grimoire_script())
                return
            keep = [(e, i) for e, i in zip(ents, infos) if not any(e is x[0] for x in dups)]
            messagebox.showinfo(APP_NAME, f"{len(dups)} archive(s) déjà dans le Grimoire : elles sont ignorées.", parent=self)
            if not keep:
                return
            ents, infos = [k[0] for k in keep], [k[1] for k in keep]
        dlg = GrimoireSendDialog(self, ents, infos)
        self.wait_window(dlg)
        sid = dlg.result
        if not sid:
            return
        ids, err = [], ""
        try:
            c = gr_connect()
            subs = gr_subjects(c)
            for e, i in zip(ents, infos):
                try:
                    ids.append(gr_add_fiche(c, sid, root, e, i))
                except Exception as ex:
                    err = str(ex)
            name = gr_path(subs, sid)
            c.close()
        except Exception as ex:
            err, name = str(ex), "?"
        if ids:
            msg = f"✔ Ajouté au Grimoire « {name} »" + ("" if len(ids) == 1 else f" ({len(ids)} fiches)")
            self.status.set(msg)
            try:
                self.log(msg, "info")
            except Exception:
                pass
            self._grimoire_toast(msg, ids[0])
        if err:
            messagebox.showerror(APP_NAME, f"Envoi au Grimoire incomplet : {err}", parent=self)

    def _grimoire_toast(self, msg: str, iid: int):
        try:
            t = tk.Toplevel(self)
            t.overrideredirect(True)
            t.configure(bg=NC_HI)
            tk.Label(t, text=msg, bg=NC_HI, fg=NC_ON_HI, font=FONT_UI, padx=12, pady=8).pack(side="left")
            b = tk.Button(t, text="📖 Ouvrir dans le Grimoire", command=lambda: (gr_open_item(iid, self._grimoire_script()), t.destroy()),
                          bg=NC_BTN, fg=NC_BTN_FG, font=FONT_SM, relief="raised", bd=1, cursor="hand2")
            b.pack(side="left", padx=6, pady=6)
            Tooltip(b, "Montre la nouvelle fiche dans le Grimoire (le lance s'il est fermé)")
            x = tk.Button(t, text="✖", command=t.destroy, bg=NC_HI, fg=NC_ON_HI, relief="flat", font=FONT_SM, cursor="hand2")
            x.pack(side="left", padx=(0, 6))
            t.update_idletasks()
            t.geometry(f"+{self.winfo_rootx() + (self.winfo_width() - t.winfo_reqwidth()) // 2}+"
                       f"{self.winfo_rooty() + self.winfo_height() - t.winfo_reqheight() - 70}")
            t.attributes("-topmost", True)
            self.after(9000, lambda: t.winfo_exists() and t.destroy())
        except Exception:
            pass

    def _build_coll_menu(self, parent=None):
        """Menu des collections : coche = l'archive (toutes celles sélectionnées) en fait partie."""
        m = tk.Menu(parent or self, tearoff=0, bg=NC_PANEL, fg=NC_FG, activebackground=NC_SEL,
                    activeforeground=NC_ON_SEL, font=FONT_SM)
        folders = self._selected_folders()
        ents = self._selected_entries()
        names = load_collections(self.archive_root_path(), self.entries)
        m.add_command(label="➕ Nouvelle collection…", command=self.new_collection,
                      state="normal" if folders else "disabled")
        if names:
            m.add_separator()
        for c in names:
            inside = bool(ents) and all(c.lower() in {x.lower() for x in (e.get("collections") or [])} for e in ents)
            m.add_command(label=("☑ " if inside else "☐ ") + c,
                          command=lambda cc=c, ins=inside: self._toggle_collection(cc, ins),
                          state="normal" if folders else "disabled")
        if names:
            m.add_separator()
            sub = tk.Menu(m, tearoff=0, bg=NC_PANEL, fg=NC_FG, activebackground=NC_SEL,
                          activeforeground=NC_ON_SEL, font=FONT_SM)
            for c in names:
                sub.add_command(label=c, command=lambda cc=c: self.delete_collection(cc))
            m.add_cascade(label="🗑 Supprimer une collection", menu=sub)
        return m

    def _toggle_collection(self, name: str, inside: bool):
        folders = self._selected_folders()
        if not folders:
            return
        root = self.archive_root_path()
        try:
            if inside:
                set_collections(root, folders, remove=name)
                self.log(f"📚 Retiré de « {name} » : {len(folders)} archive(s)")
            else:
                set_collections(root, folders, add=name)
                self.log(f"📚 Ajouté à « {name} » : {len(folders)} archive(s)")
        except Exception as ex:
            logger.exception("collections")
            messagebox.showerror(APP_NAME, f"Collection : {friendly_error(ex)}", parent=self)
        self._reload_entries()

    def new_collection(self):
        folders = self._selected_folders()
        name = self._ask_string("Nom de la nouvelle collection :\n(ex. Recettes, Politique, À revoir)",
                                      parent=self)
        name = re.sub(r"\s+", " ", (name or "")).strip()[:40]
        if not name:
            return
        root = self.archive_root_path()
        names = load_collections(root, self.entries)
        if name.lower() not in {n.lower() for n in names}:
            save_collections(root, names + [name])
        else:
            name = next(n for n in names if n.lower() == name.lower())
        if folders:
            set_collections(root, folders, add=name)
            self.log(f"📚 Collection « {name} » : {len(folders)} archive(s)")
        self._reload_entries()

    def delete_collection(self, name: str):
        root = self.archive_root_path()
        members = [str(e.get("folder")) for e in self.entries
                   if name.lower() in {c.lower() for c in (e.get("collections") or [])}]
        if not messagebox.askyesno(APP_NAME, f"Supprimer la collection « {name} » ?\n\n"
                                   f"Les {len(members)} archive(s) qu'elle contient sont conservées ; "
                                   "elles sont seulement retirées de la collection.", parent=self):
            return
        if members:
            set_collections(root, members, remove=name)
        save_collections(root, [n for n in load_collections(root) if n.lower() != name.lower()])
        if self._coll_key().lower() == name.lower():
            self.coll_var.set(COLL_ALL_LABEL)
            self.cfg["collection_filter"] = ""
            save_cfg(self.cfg)
        self.log(f"🗑 Collection « {name} » supprimée.")
        self._reload_entries()

    def toggle_favorite(self):
        ents = self._selected_entries()
        if not ents:
            return
        value = not all(e.get("favorite") for e in ents)
        n = set_favorite(self.archive_root_path(), [str(e.get("folder")) for e in ents], value)
        self.status.set(("★ Ajouté aux favoris" if value else "☆ Retiré des favoris") + (f" ({n})" if n > 1 else ""))
        self._reload_entries()

    def add_tags_selected(self):
        folders = self._selected_folders()
        if not folders:
            return
        txt = self._ask_string(f"Tags à ajouter à {len(folders)} archive(s) (séparés par des virgules) :",
                                     parent=self)
        tags = parse_tags(txt or "")
        if not tags:
            return
        self._autosave_tn()
        n = add_tags_many(self.archive_root_path(), folders, tags)
        self.log(f"🏷 Tags {', '.join('#' + t for t in tags)} ajoutés à {n} archive(s).")
        self._reload_entries()
        if self._preview_entry and self._preview_entry.get("folder") in folders:
            info = load_info(self._preview_path)
            self.tags_var.set(", ".join(parse_tags(info.get("tags") or [])))
            self._loaded_tn = self._tn_current()
            self._render_tag_chips(parse_tags(info.get("tags") or []), info.get("source_tags") or [])

    def copy_summary(self):
        ents = self._selected_entries()
        if ents:
            full = []
            for e in ents:
                p = os.path.join(self.archive_root_path(), str(e.get("folder")))
                info = dict(e)
                info.update(load_info(p))
                full.append(entry_summary(info))
            self._copy_to_clipboard("\n\n".join(full))
            self.status.set(f"📋 Résumé copié ({len(ents)} archive{'s' if len(ents) > 1 else ''}).")

    def copy_links_selected(self):
        urls = [str(e.get("url") or e.get("webpage_url") or "") for e in self._selected_entries()]
        urls = [u for u in urls if u]
        if urls:
            self._copy_to_clipboard("\n".join(urls))
            self.status.set(f"📋 {len(urls)} lien(s) copié(s).")

    def convert_selected_many(self):
        ents = self._selected_entries()
        if len(ents) <= 1:
            self.convert_selected()
            return
        if not find_ffmpeg():
            messagebox.showwarning(APP_NAME, "ffmpeg est requis pour la conversion.", parent=self)
            return
        items = []
        for e in ents:
            m = find_main_media(os.path.join(self.archive_root_path(), str(e.get("folder"))))
            if m and m.lower().endswith(VIDEO_EXTS):
                items.append((str(e.get("folder")), str(e.get("title") or "")))
        if not items:
            messagebox.showinfo(APP_NAME, "Aucune vidéo dans la sélection.", parent=self)
            return
        n = self._enqueue_convert(items)
        self.status.set(f"🎬 {n} conversion(s) ajoutée(s) — les vidéos déjà compatibles sont ignorées.")

    # ------------------------------------------------------------ v5 : en ligne ?
    def check_online_selected(self, all_visible: bool = False):
        if getattr(self, "_online_busy", False):
            self.status.set("📡 Vérification déjà en cours…")
            return
        ents = list(self._visible) if all_visible else self._selected_entries()
        folders = [str(e.get("folder")) for e in ents if e.get("folder")]
        if not folders:
            return
        self._online_busy = True
        root = self.archive_root_path()
        self.status.set(f"📡 Vérification en ligne de {len(folders)} archive(s)…")
        self.log(f"📡 Vérification en ligne : {len(folders)} archive(s)")
        self.prog.configure(value=0)

        def prog(done, total, f, st):
            def _u():
                self.prog.configure(value=done * 100.0 / max(1, total))
                self.prog_var.set(f"📡 {done}/{total} · {GUI_ONLINE.get(st, ('?',))[0]} {f[:60]}")
            self.ui(_u)

        def job():
            counts: Dict[str, int] = {}
            err = ""
            try:
                counts = check_online_many(root, folders, progress=prog,
                                           workers=int(self.cfg.get("online_workers") or 4))
            except Exception as ex:
                logger.exception("check online")
                err = friendly_error(ex)
            self.ui(lambda: self._online_done(counts, err, len(folders)))
        threading.Thread(target=job, daemon=True).start()

    def _online_done(self, counts: Dict[str, int], err: str, n: int):
        self._online_busy = False
        self.prog.configure(value=0)
        if err:
            self.prog_var.set("Aucun archivage en cours.")
            messagebox.showerror(APP_NAME, f"Vérification impossible :\n{err}", parent=self)
            return
        parts = [f"{GUI_ONLINE[k][0]} {GUI_ONLINE[k][1]} : {v}" for k, v in counts.items() if v and k in GUI_ONLINE]
        msg = " · ".join(parts) or "aucun résultat"
        self.prog_var.set(f"📡 Vérifié ({n}) — {msg}")
        self.log(f"📡 Résultat : {msg}")
        self.status.set(f"📡 Vérification terminée — {msg}")
        self._reload_entries()
        if self._smoke:
            return
        off = counts.get("offline", 0) + counts.get("restricted", 0)
        if n > 1:
            if off and messagebox.askyesno(APP_NAME, f"Vérification terminée ({n} archives) :\n\n" + "\n".join(parts) +
                                           f"\n\nAfficher les {off} archive(s) dont l'original n'est plus disponible ?",
                                           parent=self):
                lab = next((k for k, v in self._coll_map.items() if v == COLL_OFFLINE), COLL_ALL_LABEL)
                self.coll_var.set(lab)
                self._on_coll_filter()
            elif not off:
                messagebox.showinfo(APP_NAME, f"Vérification terminée ({n} archives) :\n\n" + "\n".join(parts), parent=self)

    # ------------------------------------------------------------ v5 : export
    def _docs_dir(self) -> str:
        d = os.path.join(os.path.expanduser("~"), "Documents")
        return d if os.path.isdir(d) else os.path.expanduser("~")

    def export_zip_dialog(self, scope: str = "selection"):
        if getattr(self, "_export_busy", False):
            self.status.set("📦 Export déjà en cours…")
            return
        ents = self._selected_entries() if scope == "selection" else list(self._visible)
        folders = [str(e.get("folder")) for e in ents if e.get("folder")]
        if not folders:
            messagebox.showinfo(APP_NAME, "Aucune archive à exporter.", parent=self)
            return
        root = self.archive_root_path()
        total = sum(folder_size(os.path.join(root, f)) for f in folders)
        base = slugify(str(ents[0].get("title") or "archive"))[:40] if len(ents) == 1 else f"archives_{len(ents)}"
        name = f"Archiveur_{base}_{datetime.now().strftime('%Y-%m-%d')}.zip"
        dest = filedialog.asksaveasfilename(parent=self, title=f"Exporter {len(folders)} archive(s) en ZIP ({human_size(total)})",
                                            initialdir=self._docs_dir(), initialfile=name, defaultextension=".zip",
                                            filetypes=[("Archive ZIP", "*.zip")])
        if not dest:
            return
        try:
            free = shutil.disk_usage(os.path.dirname(dest) or ".").free
            if free < total + 50 * 1024 * 1024:
                messagebox.showerror(APP_NAME, f"Espace insuffisant : il faut ≈ {human_size(total)}, "
                                     f"disponible {human_size(free)}.", parent=self)
                return
        except Exception:
            pass
        self._export_busy = True
        self.log(f"📦 Export ZIP : {len(folders)} archive(s) → {dest}")

        def prog(i, n, f):
            self.ui(lambda: (self.prog.configure(value=i * 100.0 / max(1, n)),
                             self.prog_var.set(f"📦 Export ZIP {i}/{n} : {f[:60]}")))

        def job():
            err = ""
            res = (0, 0)
            try:
                res = export_zip(root, folders, dest, progress=prog)
            except Exception as ex:
                logger.exception("export zip")
                err = friendly_error(ex)
            self.ui(lambda: self._export_done(dest, res, err))
        threading.Thread(target=job, daemon=True).start()

    def _export_done(self, dest: str, res: Tuple[int, int], err: str):
        self._export_busy = False
        self.prog.configure(value=0)
        if err:
            self.prog_var.set("Export ZIP échoué.")
            messagebox.showerror(APP_NAME, f"Export impossible :\n{err}", parent=self)
            return
        self.prog_var.set(f"📦 ZIP créé : {os.path.basename(dest)} ({human_size(res[1])})")
        self.log(f"📦 ZIP créé : {dest} — {res[0]} fichiers, {human_size(res[1])}")
        if messagebox.askyesno(APP_NAME, f"ZIP créé ✅\n\n{dest}\n{res[0]} fichiers · {human_size(res[1])}\n\n"
                               "Il contient une page index.html (à ouvrir après décompression) et catalogue.csv.\n\n"
                               "Afficher le fichier dans l'Explorateur ?", parent=self):
            ok, e2 = reveal_in_explorer(dest)
            if not ok:
                self.open_path_safe(os.path.dirname(dest), "dossier")

    def export_catalog_dialog(self):
        ents = list(self._visible)
        if not ents:
            messagebox.showinfo(APP_NAME, "Aucune archive dans la liste.", parent=self)
            return
        dest = filedialog.asksaveasfilename(
            parent=self, title=f"Exporter le catalogue ({len(ents)} archives affichées)", initialdir=self._docs_dir(),
            initialfile=f"Archiveur_catalogue_{datetime.now().strftime('%Y-%m-%d')}.csv", defaultextension=".csv",
            filetypes=[("CSV (Excel)", "*.csv"), ("JSON", "*.json")])
        if not dest:
            return
        try:
            n = export_catalog(ents, dest)
        except Exception as ex:
            logger.exception("catalogue")
            messagebox.showerror(APP_NAME, f"Export impossible :\n{friendly_error(ex)}", parent=self)
            return
        self.log(f"📑 Catalogue exporté : {n} lignes → {dest}")
        if messagebox.askyesno(APP_NAME, f"Catalogue exporté ✅ ({n} archives)\n\n{dest}\n\nL'ouvrir maintenant ?", parent=self):
            self.open_path_safe(dest, "fichier")

    # ------------------------------------------------------------ v5 : dialogues
    def _dialog(self, title: str, w: int, h: int, modal: bool = False):
        win = tk.Toplevel(self)
        win.title(f"{APP_NAME} — {title}")
        win.configure(bg=NC_BG)
        sw = max(400, self.winfo_width() if self.winfo_width() > 200 else self.winfo_screenwidth())
        sh = max(300, self.winfo_height() if self.winfo_height() > 200 else self.winfo_screenheight())
        w, h = min(w, sw - 40), min(h, sh - 40)
        x = self.winfo_rootx() + max(0, (sw - w) // 2)
        y = self.winfo_rooty() + max(0, (sh - h) // 2)
        win.geometry(f"{w}x{h}+{x}+{y}")
        win.transient(self)
        try:
            win.iconphoto(False, self._icon_img)
        except Exception:
            pass
        win.bind("<Escape>", lambda e: win.destroy())
        if modal:
            try:
                win.grab_set()
            except Exception:
                pass
        return win

    def _ask_string(self, prompt: str, initial: str = "", parent=None) -> Optional[str]:
        win = self._dialog("saisie", 520, 190, modal=True)
        res: Dict[str, Optional[str]] = {"v": None}
        tk.Label(win, text=prompt, bg=NC_BG, fg=NC_FG, font=FONT_UI, justify="left", anchor="w",
                 wraplength=480).pack(fill="x", padx=14, pady=(14, 6))
        var = tk.StringVar(value=initial)
        ent = tk.Entry(win, textvariable=var, bg=NC_ENTRY_BG, fg=NC_ENTRY_FG, insertbackground=NC_FG, font=FONT_UI)
        ent.pack(fill="x", padx=14, ipady=3)
        row = tk.Frame(win, bg=NC_BG)
        row.pack(fill="x", padx=14, pady=12, side="bottom")

        def ok(_e=None):
            res["v"] = var.get()
            win.destroy()
        self._btn(row, "OK", ok, hi=True, font=FONT_UI).pack(side="right", padx=4)
        self._btn(row, "Annuler", win.destroy, font=FONT_UI).pack(side="right", padx=4)
        ent.bind("<Return>", ok)
        ent.focus_set()
        ent.select_range(0, "end")
        self._modal_win = win
        if not self._smoke:
            self.wait_window(win)
        return res["v"]

    def _build_tools_menu(self):
        m = self._menu()
        m.add_command(label="✔ Vérifier les archives (intégrité)…", command=self.verify_dialog)
        m.add_command(label="📡 Vérifier si les originaux sont encore en ligne (liste affichée)",
                      command=lambda: self.check_online_selected(True))
        m.add_command(label="📊 Statistiques…", command=self.open_stats)
        m.add_separator()
        m.add_command(label="📦 Exporter la sélection en ZIP…  (Ctrl+E)", command=lambda: self.export_zip_dialog("selection"))
        m.add_command(label="📦 Exporter la liste affichée en ZIP…", command=lambda: self.export_zip_dialog("visible"))
        m.add_command(label="📑 Exporter le catalogue (CSV pour Excel, ou JSON)…", command=self.export_catalog_dialog)
        m.add_separator()
        m.add_command(label="♻ Régénérer l'index (pages HTML)", command=self.regenerate_index)
        m.add_command(label="🎬 Réparer les codecs (toutes les vidéos)", command=self.fix_all_codecs)
        m.add_command(label="📁 Ouvrir le dossier racine des archives", command=self.open_root)
        m.add_command(label="🗂 Ouvrir les sauvegardes de l'index", command=self.open_backups)
        m.add_separator()
        m.add_command(label=f"⬆ Mettre à jour yt-dlp (version {ytdlp_version() or '?'})", command=self.update_ytdlp_ui)
        return m

    def _build_more_menu(self):
        m = self._menu()
        has = bool(self._preview_entry)
        st = "normal" if has else "disabled"
        main = find_main_media(self._preview_path) if has and self._preview_path else None
        m.add_command(label="📋 Copier le lien", command=self.copy_link, state=st)
        m.add_command(label="📋 Copier le résumé (titre, lien, auteur, tags)", command=self.copy_summary, state=st)
        m.add_command(label="📋 Copier le chemin du dossier", command=self.copy_folder_path, state=st)
        m.add_separator()
        m.add_command(label="📡 Vérifier si l'original est en ligne", command=lambda: self.check_online_selected(False), state=st)
        m.add_command(label="📦 Exporter en ZIP…", command=lambda: self.export_zip_dialog("selection"), state=st)
        m.add_command(label="🏷 Ajouter des tags…", command=self.add_tags_selected, state=st)
        m.add_separator()
        m.add_command(label="🎙 Transcrire le son (Whisper, local)", command=self.transcribe_selected,
                      state="normal" if (main and whisper_available()) else "disabled")
        m.add_command(label="🎬 Convertir en MP4 compatible (H.264)", command=self.convert_selected,
                      state="normal" if (main and main.lower().endswith(VIDEO_EXTS)) else "disabled")
        m.add_command(label="🎞 Refaire le storyboard", command=self.regen_storyboard,
                      state="normal" if (main and main.lower().endswith(VIDEO_EXTS)) else "disabled")
        url = self._entry_url() if has else ""
        m.add_command(label="🔁 Ré-archiver depuis l'original", command=lambda: self.enqueue_urls([url], ask_dups=False),
                      state="normal" if url else "disabled")
        m.add_command(label="📰 Ré-archiver comme page web (lecture + capture + PDF)",
                      command=lambda: self.enqueue_urls([url], ask_dups=False, extra={"page_mode": True}),
                      state="normal" if url else "disabled")
        m.add_separator()
        m.add_command(label="✏ Renommer (F2)", command=self.rename_selected, state=st)
        m.add_command(label="🗑 Supprimer l'archive…  (Suppr)", command=self.delete_selected, state=st)
        return m

    def open_backups(self):
        d = os.path.join(self.archive_root_path(), BACKUP_DIR)
        if not os.path.isdir(d):
            backup_index(self.archive_root_path(), min_interval=0)
        if os.path.isdir(d):
            self.open_path_safe(d, "dossier")
        else:
            messagebox.showinfo(APP_NAME, "Aucune sauvegarde pour l'instant (l'index est vide).", parent=self)

    # ---------------------------------------------------------------- réglages
    def open_settings(self):
        win = self._dialog("réglages", 640, 600)
        self._settings_win = win
        sf = ScrollFrame(win)
        sf.pack(fill="both", expand=True)
        body = sf.inner
        cfg = self.cfg

        def section(t):
            return self._section(body, t)

        section("🎨 Apparence")
        theme_var = tk.StringVar(value=THEME)
        row = tk.Frame(body, bg=NC_BG)
        row.pack(fill="x", padx=14)
        tk.Label(row, text="Thème :", bg=NC_BG, fg=NC_FG, font=FONT_UI).pack(side="left")
        for k, lab in THEME_LABELS.items():
            tk.Radiobutton(row, text=lab, value=k, variable=theme_var, bg=NC_BG, fg=NC_FG, selectcolor=NC_ENTRY_BG,
                           activebackground=NC_BG, activeforeground=NC_HI, font=FONT_SM, highlightthickness=0,
                           command=lambda: self._theme_changed(theme_var.get())).pack(side="left", padx=6)
        tk.Label(body, text="Changer de thème relance l'Archiveur (quelques secondes).", bg=NC_BG, fg=NC_DIM,
                 font=FONT_SM, anchor="w").pack(fill="x", padx=14)
        row = tk.Frame(body, bg=NC_BG)
        row.pack(fill="x", padx=14, pady=(8, 0))
        tk.Label(row, text="Taille du texte :", bg=NC_BG, fg=NC_FG, font=FONT_UI).pack(side="left")
        self._fs_lab = tk.Label(row, text="", bg=NC_BG, fg=NC_HI, font=FONT_UI, width=8)
        self._btn(row, "A−", lambda: self._font_step(-1), font=FONT_UI).pack(side="left", padx=(8, 2))
        self._fs_lab.pack(side="left")
        self._btn(row, "A+", lambda: self._font_step(1), font=FONT_UI).pack(side="left", padx=2)
        self._btn(row, "Normal", lambda: self._font_step(0, reset=True)).pack(side="left", padx=8)
        self._fs_update()
        tk.Label(body, text="Raccourcis : Ctrl + molette, Ctrl + / Ctrl − / Ctrl 0", bg=NC_BG, fg=NC_DIM,
                 font=FONT_SM, anchor="w").pack(fill="x", padx=14)

        def chk(text, key, tip="", default=True, cmd=None):
            var = tk.BooleanVar(value=bool(cfg.get(key, default)))

            def _set():
                cfg[key] = bool(var.get())
                save_cfg(cfg)
                if cmd:
                    cmd()
            cb = tk.Checkbutton(body, text=text, variable=var, command=_set, bg=NC_BG, fg=NC_FG, selectcolor=NC_ENTRY_BG,
                                activebackground=NC_BG, activeforeground=NC_HI, font=FONT_UI, anchor="w",
                                highlightthickness=0)
            cb.pack(fill="x", padx=14, pady=(4, 0))
            if tip:
                tk.Label(body, text=tip, bg=NC_BG, fg=NC_DIM, font=FONT_SM, anchor="w", justify="left",
                         wraplength=560).pack(fill="x", padx=38)
            return var

        section("▶ Lecture")
        ff_ok = bool(find_ffmpeg()) and bool(find_ffplay())
        chk("Lecteur intégré dans l'aperçu", "integrated_player",
            "▶ Lire joue la vidéo directement dans l'Archiveur (ffmpeg + ffplay, rien à installer). "
            "Décoché : ▶ ouvre le lecteur externe choisi ci-dessous."
            + ("" if ff_ok else "\n⚠ ffplay introuvable : relance setup_padawan.bat pour l'installer avec ffmpeg."),
            cmd=lambda: self._preview_entry and self.show_preview(self._preview_entry))
        row = tk.Frame(body, bg=NC_BG)
        row.pack(fill="x", padx=14, pady=(8, 0))
        tk.Label(row, text="Lecteur externe (↗) :", bg=NC_BG, fg=NC_FG, font=FONT_UI).pack(side="left")
        pvals = [PLAYER_LABELS["windows"]] + [PLAYER_LABELS[k] for k in ("vlc", "mpv") if k in self._players]
        pcb = ttk.Combobox(row, textvariable=self.player_var, values=pvals, width=22, state="readonly", font=FONT_SM)
        pcb.pack(side="left", padx=6)
        pcb.bind("<<ComboboxSelected>>", lambda e: self._persist_opts())
        if len(pvals) == 1:
            pcb.configure(state="disabled")
        tk.Label(body, text=("Détectés : " + ", ".join(PLAYER_LABELS[k] for k in self._players)) if self._players else
                 "VLC / mpv non détectés : le lecteur Windows est utilisé (winget install VideoLAN.VLC pour VLC).",
                 bg=NC_BG, fg=NC_DIM, font=FONT_SM, anchor="w", justify="left", wraplength=560).pack(fill="x", padx=38)
        section("🌐 Archivage")
        row = tk.Frame(body, bg=NC_BG)
        row.pack(fill="x", padx=14, pady=(4, 0))
        tk.Label(row, text="Dossier des archives :", bg=NC_BG, fg=NC_FG, font=FONT_UI).pack(side="left")
        ent = tk.Entry(row, textvariable=self.root_var, bg=NC_ENTRY_BG, fg=NC_ENTRY_FG, insertbackground=NC_FG,
                       font=FONT_SM)
        ent.pack(side="left", fill="x", expand=True, padx=6)
        ent.bind("<Return>", lambda e: (self._persist_opts(), self.refresh_list()))
        ent.bind("<FocusOut>", lambda e: self._persist_opts())
        self._btn(row, "Choisir…", self.choose_root).pack(side="left")

        def vchk(text, var, tip):
            tk.Checkbutton(body, text=text, variable=var, command=self._persist_opts, bg=NC_BG, fg=NC_FG,
                           selectcolor=NC_ENTRY_BG, activebackground=NC_BG, activeforeground=NC_HI, font=FONT_UI,
                           anchor="w", highlightthickness=0).pack(fill="x", padx=14, pady=(4, 0))
            tk.Label(body, text=tip, bg=NC_BG, fg=NC_DIM, font=FONT_SM, anchor="w", justify="left",
                     wraplength=560).pack(fill="x", padx=38)
        vchk("🎞 Storyboard aussi pendant l'archivage", self.sb_var,
             "Sinon il se prépare tout seul en arrière-plan juste après (ou à l'affichage) — clic sur une image = lecture à ce moment.")
        vchk("🎬 MP4 compatible automatique", self.conv_var,
             "Si la vidéo reçue est en AV1/VP9/Opus, la convertir en MP4 H.264 + AAC (lisible partout, à vie).")
        vchk("🔔 Notification Windows à la fin de l'archivage", self.notif_var, "Petite bulle en bas à droite de l'écran.")
        chk("Pages web : capture d'écran + PDF de la page entière", "web_capture",
            "Utilise Edge (ou Chrome) en arrière-plan, sans fenêtre. Ajoute ≈ 10-30 s par page.")
        chk("X / Twitter : service fxtwitter en secours", "x_fxtwitter",
            "Si yt-dlp échoue (post sans vidéo, compte protégé…), récupère le texte, les photos, la vidéo et le fil "
            "(messages précédents) via api.fxtwitter.com, un service public tiers. Seule l'adresse du post lui est envoyée.")
        section("🎙 Transcription (Whisper)")
        has_w = whisper_available()
        tk.Label(body, text=("✅ faster-whisper installé." if has_w else
                             "faster-whisper n'est pas installé : les vidéos avec sous-titres sont quand même transcrites. "
                             "Pour transcrire les autres : setup_padawan.bat → répondre O à « Whisper » (≈ 200 Mo)."),
                 bg=NC_BG, fg=NC_OK if has_w else NC_DIM, font=FONT_SM, anchor="w", justify="left",
                 wraplength=560).pack(fill="x", padx=14, pady=(2, 4))
        row = tk.Frame(body, bg=NC_BG)
        row.pack(fill="x", padx=14)
        tk.Label(row, text="Modèle :", bg=NC_BG, fg=NC_FG, font=FONT_UI).pack(side="left")
        models = [("tiny", "tiny — très rapide, approximatif"), ("base", "base — bon compromis (défaut)"),
                  ("small", "small — plus précis, ≈ 3× plus lent"), ("medium", "medium — précis, lent")]
        wlab = {k: v for k, v in models}
        wvar = tk.StringVar(value=wlab.get(str(cfg.get("whisper_model") or "base"), wlab["base"]))
        wcb = ttk.Combobox(row, textvariable=wvar, values=[v for _k, v in models], width=34, state="readonly", font=FONT_SM)
        wcb.pack(side="left", padx=6)

        def _wset(_e=None):
            inv = {v: k for k, v in models}
            cfg["whisper_model"] = inv.get(wvar.get(), "base")
            save_cfg(cfg)
        wcb.bind("<<ComboboxSelected>>", _wset)
        section("ℹ Informations")
        info_lines = [
            f"Archiveur v{APP_FILE_VER} · Python {sys.version.split()[0]} · Tk {self.tk.call('info', 'patchlevel')}",
            f"yt-dlp : {ytdlp_version() or 'non installé'}",
            f"ffmpeg : {find_ffmpeg() or 'introuvable'}",
            f"ffplay : {find_ffplay() or 'introuvable'}",
            f"Navigateur pour captures : {find_browser() or 'introuvable'}",
            f"Glisser-déposer : {'actif' if getattr(self, '_dnd_ok', False) else 'indisponible (module tkinterdnd2)'}",
            f"Réglages : {CFG_FILE}",
            f"Journal : {LOG_FILE}",
        ]
        tk.Label(body, text="\n".join(info_lines), bg=NC_BG, fg=NC_FG, font=FONT_SM, anchor="w", justify="left",
                 wraplength=580).pack(fill="x", padx=14, pady=(2, 10))
        row = tk.Frame(win, bg=NC_PANEL)
        row.pack(fill="x", side="bottom")
        self._btn(row, "Fermer", win.destroy, hi=True, font=FONT_UI).pack(side="right", padx=10, pady=6)
        self._auto_wrap(sf)
        return win

    def _auto_wrap(self, sf):
        """Les textes longs d'un ScrollFrame suivent la largeur (aucun texte coupé)."""
        labs: List[Any] = []

        def walk(w):
            for c in w.winfo_children():
                if isinstance(c, tk.Label) and (int(float(c.cget("wraplength") or 0)) > 0
                                                or len(str(c.cget("text") or "")) > 40):
                    if not int(float(c.cget("wraplength") or 0)):
                        c.configure(justify="left")
                    labs.append(c)
                walk(c)
        walk(sf.inner)

        def conf(_e=None):
            try:
                width = sf.canvas.winfo_width()
                base = sf.inner.winfo_rootx()
            except Exception:
                return
            if width < 50:
                return
            for lab in labs:
                try:
                    x = (lab.winfo_rootx() - base) if lab.winfo_ismapped() else 40
                    lab.configure(wraplength=max(160, width - 2 * x - 12))  # marges gauche = droite
                except Exception:
                    pass
        sf.canvas.bind("<Configure>", lambda e: sf.canvas.after_idle(conf), add="+")
        sf.canvas.after(150, conf)
        sf.canvas.after(600, conf)

    def _theme_changed(self, theme: str):
        if theme == THEME:
            return
        self.cfg["theme"] = theme
        save_cfg(self.cfg)
        if self._smoke:
            self.cfg["theme"] = THEME
            return
        busy = any(j["status"] in ("cours", "attente") for j in self.jobs)
        if busy:
            messagebox.showinfo(APP_NAME, "Le nouveau thème sera appliqué au prochain démarrage\n"
                                "(un archivage est en cours).", parent=self)
            return
        if messagebox.askyesno(APP_NAME, f"Thème « {THEME_LABELS.get(theme, theme)} » enregistré.\n\n"
                               "Relancer l'Archiveur maintenant pour l'appliquer ?", parent=self):
            self._relaunch()

    def _relaunch(self):
        try:
            self._autosave_tn()
        except Exception:
            pass
        try:
            self.player.stop()
        except Exception:
            pass
        release_single_instance()
        exe = sys.executable
        if sys.platform.startswith("win") and exe.lower().endswith("python.exe"):
            cand = exe[:-10] + "pythonw.exe"
            if os.path.isfile(cand):
                exe = cand
        try:
            kw: Dict[str, Any] = {"close_fds": True}
            if sys.platform.startswith("win"):
                kw["creationflags"] = CREATE_NO_WINDOW
            subprocess.Popen([exe, os.path.abspath(__file__), "--wait-lock"], **kw)
        except Exception as ex:
            logger.exception("relance")
            messagebox.showerror(APP_NAME, f"Relance impossible : {ex}\nRelance l'Archiveur à la main.", parent=self)
            return
        self.destroy()

    # ---------------------------------------------------------------- taille du texte
    def _fs_update(self):
        d = int(self.cfg.get("font_delta") or 0)
        try:
            self._fs_lab.configure(text=("normal" if d == 0 else f"{d:+d}"))
        except Exception:
            pass

    def _font_step(self, step: int, reset: bool = False):
        cur = int(self.cfg.get("font_delta") or 0)
        new = 0 if reset else max(FONT_DELTA_MIN, min(FONT_DELTA_MAX, cur + step))
        if new == cur and not reset:
            self.status.set("🔠 Taille du texte : limite atteinte.")
            return
        self.cfg["font_delta"] = new
        init_fonts(self, new)
        self._apply_row_heights()
        self._relayout_flows(self)
        self._last_pw = None
        self._do_resize()
        self._fs_update()
        if self._save_cfg_job:
            try:
                self.after_cancel(self._save_cfg_job)
            except Exception:
                pass
        self._save_cfg_job = self.after(600, lambda: save_cfg(self.cfg))
        self.status.set(f"🔠 Taille du texte : {'normale' if new == 0 else f'{new:+d}'}  (Ctrl+0 = normale)")

    def _relayout_flows(self, w):
        try:
            for c in w.winfo_children():
                if isinstance(c, FlowFrame):
                    c.relayout()
                self._relayout_flows(c)
        except Exception:
            pass

    def _apply_row_heights(self):
        style = ttk.Style(self)
        ls = font_px(self, FONT_SM)
        style.configure("Arch.Treeview", rowheight=max(52, ls + 10))
        style.configure("Files.Treeview", rowheight=max(22, ls + 8))
        style.configure("Queue.Treeview", rowheight=max(22, ls + 8))
        style.configure("Coll.Treeview", rowheight=max(28, font_px(self, FONT_UI) + 12))

    # ---------------------------------------------------------------- aide
    def open_help(self):
        win = self._dialog("aide", 860, 680)
        self._help_win = win
        fr, txt = self._scrolled_text(win, height=30, bg=NC_PANEL, fg=NC_TEXT, font=FONT_TEXT)
        fr.pack(fill="both", expand=True, padx=10, pady=(10, 4))
        txt.configure(padx=14, pady=10, spacing1=2, spacing3=2)
        txt.tag_configure("h", foreground=NC_HI, font=FONT_TITLE, spacing1=10)
        txt.tag_configure("k", foreground=NC_HI, font=FONT_MONO)
        for kind, line in HELP_TEXT:
            if kind == "h":
                txt.insert("end", line + "\n", ("h",))
            elif kind == "k":
                k, d = line.split("|", 1)
                txt.insert("end", f"  {k:<22}", ("k",))
                txt.insert("end", d + "\n")
            else:
                txt.insert("end", line + "\n")
        txt.configure(state="disabled")
        row = tk.Frame(win, bg=NC_BG)
        row.pack(fill="x", padx=10, pady=(0, 8))
        self._btn(row, "Fermer", win.destroy, hi=True, font=FONT_UI).pack(side="right")
        self._btn(row, "📜 Ouvrir le journal (archiveur.log)", lambda: self.open_path_safe(LOG_FILE, "fichier")).pack(side="left")
        return win

    # ---------------------------------------------------------------- statistiques
    def open_stats(self):
        st = compute_stats(self.entries, self.archive_root_path())
        win = self._dialog("statistiques", 780, 640)
        self._stats_win = win
        fr, txt = self._scrolled_text(win, height=30, bg=NC_PANEL, fg=NC_TEXT, font=FONT_UI)
        fr.pack(fill="both", expand=True, padx=10, pady=(10, 4))
        txt.configure(padx=12, pady=10)
        f = tkfont.nametofont(FONT_UI, root=self)
        keys = ["Espace libre sur le disque", "Durée totale des médias"] + \
            [platform_label(p) for p in st["by_platform"]] + [c for c, _n in st["collections"]] + \
            [f"{GUI_ONLINE.get(k, ('?', k))[0]}  {GUI_ONLINE.get(k, ('?', k))[1]}" for k in st["online"]]
        c1 = 16 + max(f.measure(k) for k in keys) + 24
        c2 = c1 + f.measure("00000") + f.measure("000,0 Mo") + 28
        c3 = c2 + 24
        txt.configure(tabs=(c1, "left", c2, "right", c3, "left"))
        txt.tag_configure("h", foreground=NC_HI, font=FONT_TITLE, spacing1=10, spacing3=2)
        txt.tag_configure("bar", foreground=NC_OK)
        txt.tag_configure("v", foreground=NC_HI)
        for k in ("online", "offline", "restricted", "unknown"):
            txt.tag_configure("on_" + k, foreground=online_color(k))

        def h(t):
            txt.insert("end", t + "\n", ("h",))

        def line(k, v, tag=""):
            txt.insert("end", f"  {k}", (tag,) if tag else ())
            txt.insert("end", f"\t{v}\n", ("v",))
        h("📊 Vue d'ensemble")
        line("Archives", str(st["count"]))
        line("Espace utilisé", human_size(st["size"]))
        if st.get("free") is not None:
            line("Espace libre sur le disque", human_size(st["free"]))
        line("Durée totale des médias", human_duration(st["duration"]) if st["duration"] else "—")
        line("Favoris", str(st["favorites"]))
        line("Avec transcription", str(st["with_transcript"]))
        h("📺 Par plateforme")
        mx = max([v[0] for v in st["by_platform"].values()] or [1])
        for p, (n, size) in sorted(st["by_platform"].items(), key=lambda kv: -kv[1][0]):
            txt.insert("end", f"  {platform_label(p)}\t{n}\t{human_size(size)}\t")
            txt.insert("end", "█" * max(1, int(20 * n / mx)) + "\n", ("bar",))
        h("📅 Archivées par mois (12 derniers)")
        mm = max([n for _m, n in st["months"]] or [1])
        for m, n in st["months"]:
            txt.insert("end", f"  {m}\t{n}\t\t")
            txt.insert("end", "█" * max(1, int(20 * n / mm)) + "\n", ("bar",))
        h("📡 Originaux en ligne")
        for k, n in sorted(st["online"].items(), key=lambda kv: -kv[1]):
            if k in GUI_ONLINE:
                line(f"{GUI_ONLINE[k][0]}  {GUI_ONLINE[k][1]}", str(n), "on_" + k)
            else:
                line(str(k), str(n))
        if st["collections"]:
            h("📚 Collections")
            for c, n in st["collections"]:
                line(c, str(n))
        if st["tags"]:
            h("🏷 Tags les plus utilisés")
            txt.insert("end", "  " + "   ".join(f"#{t} ({n})" for t, n in st["tags"]) + "\n")
        txt.configure(state="disabled")
        row = tk.Frame(win, bg=NC_BG)
        row.pack(fill="x", padx=10, pady=(0, 8))
        self._btn(row, "Fermer", win.destroy, hi=True, font=FONT_UI).pack(side="right")
        self._btn(row, "📋 Copier", lambda: self._copy_to_clipboard(txt.get("1.0", "end-1c"))).pack(side="left")
        return win

    # ---------------------------------------------------------------- vérification
    def verify_dialog(self):
        win = self._dialog("vérifier les archives", 1000, 600)
        self._verify_win = win
        tk.Label(win, text="✔ Vérification de l'intégrité des archives — rien n'est modifié sans ton accord",
                 bg=NC_BG, fg=NC_HI, font=FONT_UI, anchor="w").pack(fill="x", padx=12, pady=(10, 2))
        top = tk.Frame(win, bg=NC_BG)
        top.pack(fill="x", padx=12)
        media_var = tk.BooleanVar(value=True)
        tk.Checkbutton(top, text="Analyser aussi chaque fichier vidéo/audio (plus long)", variable=media_var,
                       bg=NC_BG, fg=NC_FG, selectcolor=NC_ENTRY_BG, activebackground=NC_BG, activeforeground=NC_HI,
                       font=FONT_SM, highlightthickness=0).pack(side="left")
        state = {"issues": [], "cancel": threading.Event(), "running": False}
        prog_var = tk.StringVar(value="Clique « Lancer » pour vérifier.")
        bar = ttk.Progressbar(win, style="Arch.Horizontal.TProgressbar", maximum=100)
        bar.pack(fill="x", padx=12, pady=(6, 2))
        tk.Label(win, textvariable=prog_var, bg=NC_BG, fg=NC_FG, font=FONT_SM, anchor="w").pack(fill="x", padx=12)
        tfr = tk.Frame(win, bg=NC_BG)
        tfr.pack(fill="both", expand=True, padx=12, pady=6)
        tv = ttk.Treeview(tfr, style="Files.Treeview", columns=("prob", "detail", "action"), show="tree headings",
                          selectmode="extended")
        sb = ttk.Scrollbar(tfr, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        tv.pack(side="left", fill="both", expand=True)
        tv.heading("#0", text="Archive")
        tv.column("#0", width=300, stretch=True)
        for c, t, w in (("prob", "Problème", 230), ("detail", "Détail", 200), ("action", "Correction proposée", 220)):
            tv.heading(c, text=t)
            tv.column(c, width=w, stretch=True)
        row = tk.Frame(win, bg=NC_BG)
        row.pack(fill="x", padx=12, pady=(0, 10))
        b_run = self._btn(row, "▶ Lancer la vérification", lambda: run(), hi=True, font=FONT_UI)
        b_run.pack(side="left")
        b_fix = self._btn(row, "🔧 Réparer automatiquement", lambda: fix(), font=FONT_UI, state="disabled")
        b_fix.pack(side="left", padx=6)
        b_redo = self._btn(row, "🔁 Re-archiver / 🎬 convertir la sélection", lambda: redo(), font=FONT_UI, state="disabled")
        b_redo.pack(side="left", padx=6)
        self._btn(row, "Fermer", lambda: close(), font=FONT_UI).pack(side="right")
        Tooltip(b_fix, "Corrige sans risque : index, fiches, pages HTML, dossiers temporaires.\n"
                       "Ne supprime jamais une archive.")
        Tooltip(b_redo, "Médias illisibles / manquants : re-télécharge depuis l'original.\n"
                        "Vidéos non compatibles : conversion MP4 H.264. (via la file d'attente)")

        def close():
            state["cancel"].set()
            win.destroy()
        win.protocol("WM_DELETE_WINDOW", close)

        def fill(rep):
            tv.delete(*tv.get_children())
            issues = rep.get("issues") or []
            state["issues"] = issues
            for i, it in enumerate(issues):
                tv.insert("", "end", iid=f"v{i}", text=f" {it.get('title') or it.get('folder')}"[:80],
                          values=(it.get("label"), it.get("detail") or "", it.get("fix")))
            n_auto = sum(1 for it in issues if it.get("auto"))
            n_redo = sum(1 for it in issues if it.get("kind") in ("media_unreadable", "no_media", "incompatible"))
            b_fix.configure(state="normal" if n_auto else "disabled", text=f"🔧 Réparer automatiquement ({n_auto})")
            b_redo.configure(state="normal" if n_redo else "disabled")
            if not issues:
                prog_var.set(f"✅ Aucun problème — {rep.get('checked', 0)} archive(s) vérifiée(s).")
            else:
                prog_var.set(f"⚠ {len(issues)} problème(s) sur {rep.get('checked', 0)} archive(s) vérifiée(s) "
                             f"— {n_auto} réparable(s) automatiquement.")
            bar.configure(value=100)

        def run():
            if state["running"]:
                return
            state["running"] = True
            state["cancel"] = threading.Event()
            b_run.configure(state="disabled")
            root = self.archive_root_path()

            def p(i, n, name):
                self.ui(lambda: (bar.configure(value=i * 100.0 / max(1, n)), prog_var.set(f"{i}/{n} · {name[:80]}"))
                        if win.winfo_exists() else None)

            def job():
                rep: Dict[str, Any] = {}
                try:
                    rep = verify_archives(root, check_media=bool(media_var.get()), progress=p,
                                          cancel_event=state["cancel"])
                except Exception as ex:
                    logger.exception("vérification")
                    rep = {"issues": [], "error": friendly_error(ex)}

                def done():
                    state["running"] = False
                    if not win.winfo_exists():
                        return
                    b_run.configure(state="normal", text="🔄 Relancer")
                    if rep.get("error"):
                        prog_var.set(f"❌ {rep['error']}")
                        return
                    fill(rep)
                    self.log(f"✔ Vérification : {len(rep.get('issues') or [])} problème(s).")
                self.ui(done)
            threading.Thread(target=job, daemon=True).start()
        self._verify_run = run

        def fix():
            todo = [it for it in state["issues"] if it.get("auto")]
            if not todo:
                return
            st = repair_archives(self.archive_root_path(), todo, self.log)
            messagebox.showinfo(APP_NAME, f"Réparation : {st['ok']} corrigé(s), {st['fail']} échec(s).", parent=win)
            self.refresh_list()
            run()

        def redo():
            sel = [state["issues"][int(i[1:])] for i in tv.selection()] or state["issues"]
            conv, urls = [], []
            for it in sel:
                f = str(it.get("folder"))
                if it.get("kind") == "incompatible":
                    conv.append((f, str(it.get("title") or f)))
                elif it.get("kind") in ("media_unreadable", "no_media"):
                    info = load_info(os.path.join(self.archive_root_path(), f))
                    u = str(info.get("webpage_url") or info.get("url") or "")
                    if u:
                        urls.append(u)
            if conv:
                self._enqueue_convert(conv)
            if urls:
                self.enqueue_urls(urls, ask_dups=False)
            prog_var.set(f"Ajouté à la file : {len(conv)} conversion(s), {len(urls)} re-archivage(s).")

        def dbl(_e=None):
            sel = tv.selection()
            if sel:
                self.select_folder(state["issues"][int(sel[0][1:])].get("folder"))
        tv.bind("<Double-Button-1>", dbl)
        return win

    # ---------------------------------------------------------------- outils média
    def open_media_tools(self):
        path = self._preview_path
        main = find_main_media(path) if path else None
        if not main:
            messagebox.showinfo(APP_NAME, "Cette archive ne contient ni vidéo ni audio.", parent=self)
            return
        if not find_ffmpeg():
            messagebox.showwarning(APP_NAME, "ffmpeg est requis pour les outils média.", parent=self)
            return
        is_vid = main.lower().endswith(VIDEO_EXTS)
        dur = 0.0
        try:
            dur = float(self._preview_info.get("duration") or 0) or float(probe_duration(main) or 0)
        except Exception:
            dur = 0.0
        win = self._dialog("outils média", 740, 500)
        self._media_win = win
        title = str(self._preview_info.get("title") or os.path.basename(path))
        tk.Label(win, text="✂ Outils média", bg=NC_BG, fg=NC_HI, font=FONT_TITLE, anchor="w").pack(fill="x", padx=14, pady=(12, 0))
        wrap_labs: List[Any] = []
        head = tk.Label(win, text=f"{title[:120]}\n{os.path.basename(main)} · durée {fmt_ts(dur) if dur else '?'}",
                        bg=NC_BG, fg=NC_FG, font=FONT_SM, anchor="w", justify="left", wraplength=680)
        head.pack(fill="x", padx=14)
        wrap_labs.append((head, 40))
        grid = tk.Frame(win, bg=NC_BG)
        grid.pack(fill="x", padx=14, pady=10)
        cur = self.player.current() if self.player.state == "play" else float(self.pos_var.get() or 0)
        start_var = tk.StringVar(value=fmt_ts(cur) if cur > 0.5 else "0:00")
        end_var = tk.StringVar(value="")
        for r, (lab, var, tip) in enumerate((("Début :", start_var, "ex. 1:23 ou 83 ou 1m23s"),
                                             ("Fin :", end_var, "vide = jusqu'à la fin (GIF : 20 s max)"))):
            tk.Label(grid, text=lab, bg=NC_BG, fg=NC_FG, font=FONT_UI).grid(row=r, column=0, sticky="w", pady=3)
            ent = tk.Entry(grid, textvariable=var, width=12, bg=NC_ENTRY_BG, fg=NC_ENTRY_FG, insertbackground=NC_FG,
                           font=FONT_UI)
            ent.grid(row=r, column=1, sticky="w", padx=6)
            b = self._btn(grid, "= position du lecteur",
                          lambda v=var: v.set(fmt_ts(self.player.current() if self.player.state == "play"
                                                     else float(self.pos_var.get() or 0))))
            b.grid(row=r, column=2, sticky="w", padx=4)
            tk.Label(grid, text=tip, bg=NC_BG, fg=NC_DIM, font=FONT_SM, justify="left",
                     wraplength=240).grid(row=r, column=3, sticky="w", padx=6)
        precise_var = tk.BooleanVar(value=False)
        tk.Checkbutton(win, text="Coupe précise à l'image près (ré-encodage, plus lent)", variable=precise_var,
                       bg=NC_BG, fg=NC_FG, selectcolor=NC_ENTRY_BG, activebackground=NC_BG, activeforeground=NC_HI,
                       font=FONT_SM, highlightthickness=0, state="normal" if is_vid else "disabled").pack(anchor="w", padx=14)
        hint = tk.Label(win, text="Sans coupe précise, l'extrait commence à l'image clé la plus proche (instantané, sans perte).",
                        bg=NC_BG, fg=NC_DIM, font=FONT_SM, anchor="w", justify="left", wraplength=640)
        hint.pack(fill="x", padx=38)
        wrap_labs.append((hint, 90))
        acts = FlowFrame(win)
        acts.pack(fill="x", padx=14, pady=(12, 4))
        status = tk.Label(win, text="Les fichiers sont créés dans le sous-dossier extraits/ de l'archive.",
                          bg=NC_BG, fg=NC_FG, font=FONT_SM, anchor="w", justify="left", wraplength=600)
        status.pack(fill="x", padx=14, pady=(8, 0))
        wrap_labs.append((status, 40))

        def _wrap(e):
            if e.widget is not win:
                return
            for lab, m in wrap_labs:
                try:
                    lab.configure(wraplength=max(200, e.width - m))
                except Exception:
                    pass
        win.bind("<Configure>", _wrap, add="+")
        btns: List[Any] = []
        open_btn = self._btn(win, "📂 Ouvrir le résultat", lambda: None)

        def parse() -> Optional[Tuple[float, Optional[float]]]:
            s = parse_timecode(start_var.get() or "0")
            e_txt = end_var.get().strip()
            e = parse_timecode(e_txt) if e_txt else None
            if s is None or (e_txt and e is None):
                status.configure(text="⚠ Temps invalide — écris par exemple 1:23, 83 ou 1m23s.", fg=NC_ERR)
                return None
            return s, e

        def run(kind: str):
            rng = parse()
            if rng is None:
                return
            s, e = rng
            for b in btns:
                b.configure(state="disabled")
            status.configure(text="⏳ Traitement ffmpeg en cours…", fg=NC_HI)
            precise = bool(precise_var.get())

            def job():
                out, err = "", ""
                try:
                    if kind == "capture":
                        out = media_capture(main, s, path)
                    elif kind == "clip":
                        out = media_clip(main, s, e, path, precise=precise)
                    elif kind == "audio":
                        full = (s <= 0.01 and e is None)
                        out = media_audio(main, path, None if full else s, None if full else e)
                    elif kind == "gif":
                        out = media_gif(main, s, e if e is not None else s + 6, path)
                except Exception as ex:
                    logger.warning("outil média %s : %s", kind, ex)
                    err = friendly_error(ex)

                def done():
                    if not win.winfo_exists():
                        return
                    for b in btns:
                        b.configure(state="normal" if (is_vid or b is btns[2]) else "disabled")
                    if err:
                        status.configure(text=f"❌ {err}", fg=NC_ERR)
                        return
                    try:
                        sz = human_size(os.path.getsize(out))
                    except OSError:
                        sz = ""
                    status.configure(text=f"✅ Créé : {EXTRACTS_DIR}/{os.path.basename(out)} ({sz})", fg=NC_OK)
                    open_btn.configure(command=lambda: self._open_media(out, "fichier"))
                    open_btn.pack(anchor="w", padx=14, pady=6)
                    self.log(f"✂ {os.path.basename(out)} créé ({sz}).")
                    if self._preview_path == path:
                        self._render_extracts(path, main)
                        self._render_files()
                self.ui(done)
            threading.Thread(target=job, daemon=True).start()

        for key, txt, tip in (("capture", "📸 Capture image", "Image JPEG à la position « Début »"),
                              ("clip", "✂ Extrait vidéo", "Vidéo MP4 de « Début » à « Fin »"),
                              ("audio", "🎵 Audio MP3", "Son en MP3 (toute la durée si Début = 0 et Fin vide)"),
                              ("gif", "🎞 GIF animé", "GIF de « Début » à « Fin » (6 s si Fin vide, 20 s max)")):
            b = acts.add(self._btn(acts, txt, lambda k=key: run(k), hi=(key == "clip"), font=FONT_UI), tip)
            btns.append(b)
            if not is_vid and key != "audio":
                b.configure(state="disabled")
        row = tk.Frame(win, bg=NC_PANEL)
        row.pack(fill="x", side="bottom")
        self._btn(row, "Fermer", win.destroy, font=FONT_UI).pack(side="right", padx=10, pady=6)
        self._media_run = run
        return win

    # ---------------------------------------------------------------- yt-dlp
    def update_ytdlp_ui(self):
        if getattr(self, "_ytdlp_busy", False):
            return
        self._ytdlp_busy = True
        self.status.set("⬆ Mise à jour de yt-dlp…")

        def job():
            try:
                ok, old, new = update_ytdlp(self.log)
            except Exception as ex:
                logger.exception("maj yt-dlp")
                ok, old, new = False, "", friendly_error(ex)

            def done():
                self._ytdlp_busy = False
                if ok and old != new:
                    messagebox.showinfo(APP_NAME, f"yt-dlp mis à jour : {old} → {new}\n\n"
                                        "Relance l'Archiveur pour utiliser la nouvelle version.", parent=self)
                elif ok:
                    messagebox.showinfo(APP_NAME, f"yt-dlp est déjà à jour ({new}).", parent=self)
                else:
                    messagebox.showerror(APP_NAME, "Mise à jour de yt-dlp impossible (pas de connexion ?).\n"
                                         "Détails dans le journal (📜 Journal en bas).", parent=self)
            self.ui(done)
        threading.Thread(target=job, daemon=True).start()

    # ------------------------------------------------------------ v5 : raccourcis / glisser-déposer
    def _in_text_field(self, event) -> bool:
        try:
            return event.widget.winfo_class() in ("Entry", "Text", "TEntry", "TCombobox", "Spinbox")
        except Exception:
            return False

    def _bind_v5_keys(self):
        self.bind("<F1>", lambda e: (self.open_help(), "break")[1])
        self.bind("<F5>", lambda e: (self.refresh_list(), "break")[1])
        for seq in ("<Control-d>", "<Control-D>"):
            self.bind(seq, lambda e: (self.toggle_favorite(), "break")[1])
        for seq in ("<Control-e>", "<Control-E>"):
            self.bind(seq, lambda e: (self.export_zip_dialog("selection"), "break")[1])
        self.bind("<Control-space>", lambda e: (self.player_toggle(), "break")[1])
        self.bind("<Control-Left>", lambda e: None if self._in_text_field(e) else (self.player_skip(-10), "break")[1])
        self.bind("<Control-Right>", lambda e: None if self._in_text_field(e) else (self.player_skip(10), "break")[1])
        for seq in ("<Control-plus>", "<Control-equal>", "<Control-KP_Add>"):
            self.bind(seq, lambda e: (self._font_step(1), "break")[1])
        for seq in ("<Control-minus>", "<Control-KP_Subtract>"):
            self.bind(seq, lambda e: (self._font_step(-1), "break")[1])
        for seq in ("<Control-0>", "<Control-KP_0>", "<Control-KP_Insert>"):
            self.bind(seq, lambda e: (self._font_step(0, reset=True), "break")[1])

    def _setup_dnd(self):
        """Glisser-déposer (module optionnel tkinterdnd2) : liens, texte, fichiers .txt/.url."""
        self._dnd_ok = False
        try:
            import tkinterdnd2  # type: ignore
            from tkinterdnd2 import DND_FILES, DND_TEXT  # type: ignore
            req = getattr(tkinterdnd2.TkinterDnD, "_require", None) or getattr(tkinterdnd2.TkinterDnD, "require", None)
            req(self)
            for w in (self.url_text, self.tree, self.thumb_label, self.pscroll.canvas, self.hpane):
                w.drop_target_register(DND_FILES, DND_TEXT)
                w.dnd_bind("<<Drop>>", self._on_drop)
            self._dnd_ok = True
            self.log("Glisser-déposer actif : dépose un lien ou un fichier .txt de liens sur la fenêtre.")
        except ImportError:
            pass
        except Exception as ex:
            logger.warning("glisser-déposer indisponible : %s", ex)

    def _on_drop(self, event):
        data = getattr(event, "data", "") or ""
        urls: List[str] = []
        try:
            items = list(self.tk.splitlist(data))
        except Exception:
            items = [data]
        for it in items:
            if os.path.isfile(it):
                if it.lower().endswith((".txt", ".url", ".html", ".htm", ".csv", ".md", ".json", ".webloc")):
                    try:
                        with open(it, "r", encoding="utf-8", errors="replace") as f:
                            urls += extract_urls(f.read(2_000_000))
                    except OSError:
                        pass
            else:
                urls += extract_urls(it)
        if not urls:
            urls = extract_urls(data)
        if not urls:
            self.status.set("Glisser-déposer : aucun lien http(s) trouvé.")
            return getattr(event, "action", "copy")
        self._url_ph = False
        self.url_text.delete("1.0", "end")
        self.url_text.insert("1.0", "\n".join(urls))
        self.log(f"🖱 Déposé : {len(urls)} lien(s)")
        self.after(50, lambda: self.enqueue_urls(urls))
        return getattr(event, "action", "copy")

    # ------------------------------------------------------------ v5 : tests automatiques (--smoke / --shot)
    def _first_entry(self, pred) -> Optional[Dict[str, Any]]:
        for e in self._visible:
            p = os.path.join(self.archive_root_path(), str(e.get("folder")))
            try:
                if pred(e, p):
                    return e
            except Exception:
                continue
        return None

    def _scroll_to_widget(self, w):
        try:
            self.update_idletasks()
            inner_h = max(1, self.pscroll.inner.winfo_height())
            self.pscroll.canvas.yview_moveto(max(0.0, (w.winfo_y() - 10) / float(inner_h)))
        except Exception:
            logger.exception("scroll")

    def _do_shot_action(self):
        action, _, sub = (self._shot_action or "").partition("@")
        try:
            if sub:
                e = self._first_entry(lambda e, p: sub.lower() in str(e.get("folder")).lower())
                if e:
                    self.select_folder(e.get("folder"))
                    self.update()
            if action == "play":
                if not self._player_media:
                    e = self._first_entry(lambda e, p: bool(find_main_media(p)))
                    if e:
                        self.select_folder(e.get("folder"))
                self.player_toggle()
            elif action == "settings":
                self.open_settings()
            elif action == "help":
                self.open_help()
            elif action == "stats":
                self.open_stats()
            elif action == "verify":
                self.verify_dialog()
                self._verify_run()
            elif action == "media":
                self.open_media_tools()
            elif action == "multi":
                self._tree_select_all()
            elif action == "transcript":
                self._scroll_to_widget(self.tr_box)
            elif action == "extracts":
                self._scroll_to_widget(self.ex_box)
            elif action == "storyboard":
                self._scroll_to_widget(self.sb_title)
            elif action == "card":
                self._scroll_to_widget(self.card)
            elif action == "queue":
                self._show_bottom("log")
        except Exception as ex:
            self._tk_error(type(ex), ex, ex.__traceback__)

    def _smoke_v5_steps(self) -> List[Any]:
        safe = bool(self._root_override)
        st: List[Any] = []
        st.append(self._refresh_filter_values)
        st += [lambda: self.coll_tree.selection_set("c::" + COLL_NONE), 300,
               lambda: self.coll_tree.selection_set("c::"), 300,
               lambda: self._build_move_menu().destroy(), lambda: self._update_suggest_banner(),
               lambda: print(f"SMOKE_SUGGEST {self._sug}", flush=True),
               lambda: self._toggle_coll_side(), 200, lambda: self._toggle_coll_side()]
        if safe:
            st += [lambda: self.auto_classify(), 600,
                   lambda: getattr(self, "_auto_win", None) and self._auto_win.destroy(),
                   lambda: self._apply_auto_plan(plan_auto_collections(self.entries, load_collections(
                       self.archive_root_path(), self.entries), self.archive_root_path()),
                       load_collections(self.archive_root_path(), self.entries)), 500,
                   lambda: print("SMOKE_CLASSES " + str(sorted(self._coll_map.keys())), flush=True),
                   lambda: self.undo_auto_classify(), 500,
                   lambda: print("SMOKE_UNDO " + str(sorted(self._coll_map.keys())), flush=True)]
        for lab in list(self._coll_map.keys()) + [COLL_ALL_LABEL]:
            st.append(lambda l=lab: (self.coll_var.set(l), self.apply_filter()))
        st.append(lambda: self.search_var.set("zoo"))
        st.append(400)
        st.append(lambda: self.search_var.set(""))
        st.append(400)
        vid = self._first_entry(lambda e, p: bool(find_main_media(p)) and find_main_media(p).lower().endswith(VIDEO_EXTS))
        if vid:
            st += [lambda: self.select_folder(vid.get("folder")), self.player_toggle, 2500,
                   lambda: print(f"SMOKE_PLAYER state={self.player.state} pos={self.player.current():.2f} "
                                 f"frames={self.player._frame_idx} audio={'oui' if self.player._aclock else 'non'}",
                                 flush=True),
                   self.player_toggle, 300, lambda: self.player_skip(10), 600, lambda: self.player_skip(-5), 600,
                   self.player_toggle, 1500, self.player_mute, 400, self.player_mute, 600,
                   lambda: self.player_seek_to(1.0), 800, self.player_stop, 300,
                   lambda: self.tr_search.set("the"), 400, self._tr_find_next, self._tr_copy,
                   lambda: self.tr_search.set(""),
                   lambda: (self.open_media_tools(), None)[1], 300]
            if safe:
                st += [lambda: self._media_run("capture"), 3000]
            st += [lambda: self._media_win.destroy(), self._build_more_menu, lambda: self._build_more_menu().destroy()]
        web = self._first_entry(lambda e, p: os.path.isfile(os.path.join(p, "lecture.html")))
        if web:
            st += [lambda: self.select_folder(web.get("folder")), 300, lambda: self.pscroll.scroll_units(30)]
        st += [lambda: self.open_settings(), 400, lambda: self._settings_win.destroy(),
               lambda: self.open_help(), 300, lambda: self._help_win.destroy(),
               lambda: self.open_stats(), 300, lambda: self._stats_win.destroy(),
               lambda: self._build_tools_menu().destroy(), lambda: self._build_coll_menu().destroy(),
               lambda: self.verify_dialog(), lambda: self._verify_run(), 4000, lambda: self._verify_win.destroy(),
               lambda: self._font_step(2), 300, lambda: self._font_step(-2), 300, lambda: self._font_step(0, reset=True),
               lambda: self._tree_select_all(), 200, lambda: self._update_states(),
               lambda: self._on_drop(type("E", (), {"data": "pas de lien ici", "action": "copy"})()),
               lambda: self.check_online_selected(False), 4000]
        if safe:
            st += [self.toggle_favorite, 300, self.toggle_favorite, 300,
                   lambda: export_catalog(self._visible, os.path.join(self.archive_root_path(), "_smoke_catalogue.csv"))]
        st += [lambda: self._visible and self.select_folder(self._visible[0].get("folder")), 300]
        return st

    # ------------------------------------------------------------ fermeture / test
    def _on_close(self):
        if any(j["status"] in ("cours", "attente") for j in self.jobs) and not self._smoke:
            if not messagebox.askyesno(APP_NAME, "Un archivage est en cours.\nQuitter quand même ?", parent=self):
                return
            self._cancel_event.set()
        try:
            self._autosave_tn()
        except Exception:
            pass
        try:
            self.player.stop()
        except Exception:
            pass
        if self._save_cfg_job:
            save_cfg(self.cfg)
        release_single_instance()
        self.destroy()

    def _smoke_run(self):
        """--smoke N : parcourt les aperçus, filtres, tri, lot, puis ferme."""
        steps: List[Callable[[], None]] = []
        for e in list(self._visible):
            steps.append(lambda e=e: self.select_folder(e.get("folder")))
            steps.append(lambda: self.pscroll.scroll_units(10))
        steps += [
            lambda: self.search_var.set("zoo"),
            lambda: self.apply_filter(),
            lambda: self.search_var.set(""),
            lambda: self.sort_var.set(LABEL_BY_SORT["size_desc"]),
            lambda: self.apply_filter(),
            lambda: self.sort_var.set(LABEL_BY_SORT["date_desc"]),
            lambda: self.apply_filter(),
            lambda: self.open_batch_dialog(),
            lambda: self._batch_win.destroy(),
            lambda: self._on_clip_urls(["https://www.youtube.com/watch?v=jNQXAC9IVRw"]),
            lambda: self._hide_clip_banner(),
            lambda: self._refresh_queue_view(),
            lambda: self._do_resize(),
            lambda: self._show_bottom("queue"),
            lambda: self._show_bottom("log"),
            lambda: self._collapse_bottom(),
            lambda: self._tree_columns(),
            lambda: self.opts_flow.relayout(),
            lambda: self._update_states(),
            lambda: self._url_placeholder(),
        ]
        steps += self._smoke_v5_steps()

        def run(i=0):
            if i < len(steps):
                delay = 150
                if isinstance(steps[i], int):
                    delay = steps[i]
                else:
                    try:
                        steps[i]()
                    except Exception as ex:
                        self._tk_error(type(ex), ex, ex.__traceback__)
                self.after(delay, lambda: run(i + 1))
            else:
                self.after(int(self._smoke * 1000), self._smoke_end)
        run()

    def _smoke_end(self):
        print(f"SMOKE_RESULT errors={len(self._errors)} entries={len(self.entries)} visible={len(self._visible)}", flush=True)
        for er in self._errors:
            print("SMOKE_ERROR", er, flush=True)
        self._smoke_code = 1 if self._errors else 0
        self.destroy()
