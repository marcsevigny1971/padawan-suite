# -*- coding: utf-8 -*-
# Partie de archiveur5.py : embeds (aperçus oEmbed/OpenGraph + lecteur officiel en ligne).
# Chargée par archiveur5.py dans un espace de noms commun : ne pas lancer seule.
# Le travail est fait par padawan_embeds.py (module commun de la suite, sans Tk).
from __future__ import annotations

try:
    import padawan_embeds as _PE
except Exception:  # module absent : l'Archiveur marche comme avant, sans embeds
    _PE = None

if _PE is not None:
    for _k, _lab in _PE.LABELS.items():
        PLATFORM_LABELS.setdefault(_k, _lab)
    PLATFORM_LABELS.setdefault("peertube", "🐙 PeerTube")
    PLATFORM_LABELS.setdefault("mastodon", "🐘 Mastodon")

EMBED_KEEP = ("platform", "label", "kind", "protected", "embed", "title", "author", "author_url", "thumbnail",
              "provider", "duration", "description", "source", "oembed_html", "fetched_at")


def embed_detect(url: str) -> Dict[str, Any]:
    if _PE is None:
        return {"key": detect_platform(url), "label": "", "kind": "web", "protected": False, "embed": ""}
    try:
        return _PE.detect(url)
    except Exception:
        return {"key": detect_platform(url), "label": "", "kind": "web", "protected": False, "embed": ""}


def embed_attach(root: str, info: Dict[str, Any], url: str, log: Callable[[str], None]) -> Dict[str, Any]:
    """Ajoute l'aperçu (oEmbed/OpenGraph) et le lecteur officiel à info.json. Ne change aucun média."""
    if _PE is None or not info or not info.get("folder"):
        return info
    try:
        meta = _PE.fetch_preview(url)
    except Exception as e:
        log(f"Aperçu embed : {e}")
        return info
    fields: Dict[str, Any] = {"embed": {k: meta.get(k) for k in EMBED_KEEP if meta.get(k) not in (None, "")}}
    key = str(meta.get("platform") or "web")
    if str(info.get("platform") or "web") == "web" and key != "web":
        fields["platform"] = key
    if meta.get("protected"):
        fields["protected"] = True
        fields["favorite"] = True  # lien favori : on le retrouve facilement pour le regarder sur le site
    for src, dst in (("author", "uploader"), ("duration", "duration")):
        if meta.get(src) and not info.get(dst):
            fields[dst] = meta[src]
    if meta.get("description") and not info.get("summary"):
        fields["summary"] = str(meta["description"])[:2000]
    fp = os.path.join(root, str(info["folder"]))
    thumb = str(meta.get("thumbnail") or "")
    try:
        has_img = any(n.lower().endswith((".jpg", ".jpeg", ".png", ".webp")) and not n.lower().startswith("capture_page")
                      for n in os.listdir(fp))
    except OSError:
        has_img = True
    if thumb.startswith("http") and not has_img:
        try:
            data, _u, ct = http_fetch(thumb, timeout=20, max_bytes=8 * 1024 * 1024)
            ext = ".png" if "png" in ct else ".webp" if "webp" in ct else ".jpg"
            with open(os.path.join(fp, "embed_thumb" + ext), "wb") as fh:
                fh.write(data)
        except Exception as e:
            log(f"Miniature de l'aperçu : {e}")
    try:
        info = update_info_fields(root, str(info["folder"]), save_index=False, **fields)
    except Exception:
        logger.exception("embed info.json")
        info.update(fields)
    lab = meta.get("label") or platform_label(key)
    if meta.get("protected"):
        log(f"🔒 {lab} : {_PE.PROTECTED_MSG} (rangé dans ★ Favoris)")
    elif _PE.can_play(meta):
        log(f"▶ {lab} : lecteur officiel en ligne disponible (bouton « ▶ Lecteur en ligne », Ctrl+L).")
    return info


class _ArchiveurAppEmbeds:
    """Bouton « ▶ Lecteur en ligne » + bandeau d'info dans l'aperçu."""

    def _embed_meta(self, info: Dict[str, Any], url: str) -> Dict[str, Any]:
        m = dict(info.get("embed") or {})
        if not m and _PE is not None and url:
            d = _PE.detect(url)
            m = {"platform": d["key"], "label": d["label"], "kind": d["kind"], "protected": d["protected"],
                 "embed": d["embed"]}
        if m and url:
            m["url"] = url
        if m and not m.get("title"):
            m["title"] = str(info.get("title") or "")
        return m

    def _embed_preview_update(self, info: Dict[str, Any]):
        b = self._act_btns.get("online") if hasattr(self, "_act_btns") else None
        note = getattr(self, "_emb_note", None)
        if note is None:
            note = tk.Label(self._act_flow.master, text="", bg=NC_CARD, fg=NC_TEXT, font=FONT_UI, anchor="w",
                            justify="left", padx=8, pady=4, highlightthickness=1, highlightbackground=NC_HI,
                            wraplength=560, cursor="hand2")
            note.bind("<Button-1>", lambda e: self.embed_play())
            Tooltip(note, "Clic = ouvrir (lecteur officiel ou site officiel)")
            self._emb_note = note
        url = str(info.get("webpage_url") or info.get("url") or "")
        m = self._embed_meta(info, url) if url else {}
        txt = ""
        if b is not None:
            if m.get("protected") or info.get("protected"):
                b.configure(text="🔒 Regarder sur le site")
            else:
                b.configure(text="▶ Lecteur en ligne")
            try:  # le libellé change de longueur : replacer les boutons (sinon ils se chevauchent)
                self._act_flow.after_idle(self._act_flow.relayout)
            except Exception:
                pass
        if m.get("protected") or info.get("protected"):
            txt = f"{m.get('label') or ''}  🔒 Contenu protégé : aperçu + lien gardés — regarde-le sur le site officiel (Ctrl+L)."
        elif m and _PE is not None and _PE.can_play(m) and not find_main_media(self._preview_path or ""):
            txt = f"{m.get('label') or ''}  ▶ Lecteur officiel en ligne disponible : bouton « ▶ Lecteur en ligne » ou Ctrl+L."
        if txt:
            note.configure(text=txt.strip())
            if not note.winfo_ismapped():
                note.pack(fill="x", padx=6, pady=(0, 4), after=self._act_flow)
        elif note.winfo_ismapped():
            note.pack_forget()

    # ── v5.1 🧩 code embed ──
    def _build_embed_menu(self):
        m = self._menu()
        has = bool(self._preview_entry)
        url = self._entry_url() if has else ""
        vid = youtube_id(url) if url else ""
        main = find_main_media(self._preview_path) if has and self._preview_path else None
        m.add_command(label="📋 Copier le code embed YouTube (iframe)", command=lambda: self.copy_embed_code("youtube"),
                      state="normal" if vid else "disabled")
        m.add_command(label="🎬 Créer le lecteur local (lecteur.html) + copier son code",
                      command=lambda: self.copy_embed_code("local"),
                      state="normal" if (main and main.lower().endswith(VIDEO_EXTS + AUDIO_EXTS)) else "disabled")
        return m

    def copy_embed_code(self, kind: str = "youtube") -> str:
        if not self._preview_entry:
            return ""
        title = html.escape(str((self._preview_info or {}).get("title") or "Vidéo"), quote=True)
        if kind == "youtube":
            vid = youtube_id(self._entry_url())
            if not vid:
                messagebox.showinfo(APP_NAME, "Pas une vidéo YouTube : utilise le lecteur local.", parent=self)
                return ""
            code = (f'<iframe width="560" height="315" src="https://www.youtube-nocookie.com/embed/{vid}" '
                    f'title="{title}" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; '
                    f'gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>')
            msg = f"🧩 Code embed YouTube copié ({vid}) — colle-le dans ta page HTML."
        else:
            folder = self._preview_path or ""
            main = find_main_media(folder) if folder else None
            if not main:
                messagebox.showinfo(APP_NAME, "Aucune vidéo archivée dans ce dossier.", parent=self)
                return ""
            name = os.path.basename(main)
            poster = next((f for f in os.listdir(folder) if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))
                           and not f.startswith("capture")), "")
            tag = "audio" if main.lower().endswith((".mp3", ".m4a", ".ogg", ".wav", ".flac", ".opus")) else "video"
            src = quote(name)
            pst = (f' poster="{quote(poster)}"' if poster and tag == "video" else "")
            page = ("<!doctype html><html lang=\"fr\"><head><meta charset=\"utf-8\"><title>" + title + "</title>"
                    "<style>html,body{margin:0;background:#000;height:100%}" + tag + "{width:100%;height:100%;object-fit:contain}</style>"
                    "</head><body><" + tag + " controls preload=\"metadata\" src=\"" + src + "\"" + pst + "></" + tag + "></body></html>\n")
            with open(os.path.join(folder, "lecteur.html"), "w", encoding="utf-8") as fh:
                fh.write(page)
            root = self.archive_root_path()
            rel = os.path.relpath(os.path.join(folder, "lecteur.html"), os.path.dirname(root)).replace("\\", "/")
            code = (f'<iframe src="{rel}" width="640" height="360" title="{title}" frameborder="0" allowfullscreen></iframe>')
            msg = f"🎬 lecteur.html créé dans l'archive + code iframe copié (chemin relatif à {os.path.dirname(root)})."
        self.clipboard_clear()
        self.clipboard_append(code)
        self.status.set(msg)
        self.log(msg)
        return code

    def embed_play(self):
        """▶ Lecteur en ligne : lecteur officiel de la plateforme (rien n'est téléchargé)."""
        if not self._preview_entry:
            return
        url = self._entry_url()
        if not url:
            messagebox.showinfo(APP_NAME, "Aucune URL d'origine pour cette archive.", parent=self)
            return
        info = dict(self._preview_info or {})
        m = self._embed_meta(info, url)
        if _PE is None:
            self._open_url(url)
            return
        if m.get("protected") or info.get("protected"):
            self.status.set(_PE.PROTECTED_MSG)
            self._open_url(url)
            return
        colors = {"bg": NC_BG, "panel": NC_PANEL, "fg": NC_FG, "dim": NC_DIM, "acc": NC_HI}
        self.status.set(f"▶ Ouverture du lecteur officiel {m.get('label') or ''}…")

        def work():
            meta = m
            if not _PE.can_play(meta):  # pas d'URL connue : on demande à la page (oEmbed / OpenGraph)
                try:
                    meta = dict(_PE.fetch_preview(url), title=m.get("title") or "")
                except Exception:
                    meta = m
            try:
                if _PE.can_play(meta):
                    _PE.open_player(url, meta, colors)
                    msg = f"▶ Lecteur officiel ouvert ({meta.get('label') or 'en ligne'}) — F = plein écran, Alt+F4 = fermer."
                else:
                    webbrowser.open(url)
                    msg = "🌐 Pas de lecteur intégrable pour ce site : page officielle ouverte dans le navigateur."
            except Exception as ex:
                logger.exception("lecteur en ligne")
                msg = f"Lecteur en ligne impossible : {ex}"
            self.ui(lambda: self.status.set(msg))

        threading.Thread(target=work, daemon=True).start()
