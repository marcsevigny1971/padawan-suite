# -*- coding: utf-8 -*-
# Partie de archiveur5.py : CaptureScreen intégré (🎥 Enregistrer l'écran → vidéo ajoutée à la fiche).
# Chargée par archiveur5.py dans un espace de noms commun : ne pas lancer seule.
# Aucun contournement de protection (DRM) : on enregistre l'écran tel que Windows le montre.
from __future__ import annotations

PLATFORM_LABELS.setdefault("capture", "🎥 Enregistrement")
PLATFORM_LABELS.setdefault("import", "📥 Importé")

CS_COLLECTION = "Mes enregistrements"
CS_MODES = (("ecran", "🖥", "Tout l'écran", "Tout ce qui est à l'écran"),
            ("fenetre", "🗔", "Une fenêtre", "Seulement une fenêtre (ex. : le navigateur)"),
            ("zone", "⛶", "Une zone", "Un rectangle que tu traces à la souris"),
            ("son", "🎤", "Son seulement", "Pas d'image : le son de l'ordi et/ou le micro (cours, balado)"))


def cs_private_dir() -> str:
    """Même dossier que CaptureScreen (C:\\web_private\\CaptureScreen) — jamais sous FTP_HOME."""
    env = os.environ.get("CAPTURESCREEN_CONFIG", "").strip()
    if env:
        d = env
    elif sys.platform.startswith("win") and os.path.isdir(r"C:\web_private"):
        d = r"C:\web_private\CaptureScreen"
    else:
        d = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "Padawan", "CaptureScreen")
    os.makedirs(d, exist_ok=True)
    return d


def cs_results_dir() -> str:
    d = os.path.join(cs_private_dir(), "pour_archiveur")
    os.makedirs(d, exist_ok=True)
    return d


def _cs_json(path: str, default: Any) -> Any:
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return default


def cs_choices() -> Dict[str, Any]:
    """Derniers choix (mode, son, micro…) : d'abord ceux de la fenêtre 🎥, sinon les réglages de CaptureScreen."""
    cs = _cs_json(os.path.join(cs_private_dir(), "config.json"), {})
    ch = {"mode": cs.get("source") if cs.get("source") in ("ecran", "fenetre", "zone", "son") else "ecran",
          "son": bool(cs.get("sys_audio", True)), "micro": bool(cs.get("mic", False)),
          "webcam": bool(cs.get("webcam", False)), "touches": bool(cs.get("keys", True)),
          "clics": bool(cs.get("clicks", True)), "ouvrir_site": True}
    saved = _cs_json(os.path.join(cs_private_dir(), "archiveur_choix.json"), {})
    if isinstance(saved, dict):
        ch.update({k: v for k, v in saved.items() if k in ch})
    return ch


def cs_save_choices(ch: Dict[str, Any]) -> None:
    try:
        _write_json_atomic(os.path.join(cs_private_dir(), "archiveur_choix.json"), ch)
    except Exception:
        logger.exception("choix CaptureScreen")


def cs_script() -> str:
    return os.path.join(BASE, "capturescreen1.py")


def cs_python(console: bool = False) -> str:
    exe = sys.executable or "python"
    d, n = os.path.split(exe)
    want = "python.exe" if console else "pythonw.exe"
    if n.lower() in ("python.exe", "pythonw.exe") and os.path.isfile(os.path.join(d, want)):
        return os.path.join(d, want)
    return exe


def cs_command(root: str, folder: str, title: str, url: str, ch: Dict[str, Any], extra: Optional[List[str]] = None,
               console: bool = False) -> List[str]:
    cmd = [cs_python(console), cs_script(), "--enregistrer", "--mode", ch.get("mode", "ecran"),
           "--titre", title or "Enregistrement", "--root", root, "--dossier", folder or ""]
    if url:
        cmd += ["--url", url]
        if ch.get("ouvrir_site"):
            cmd.append("--ouvrir-site")
    for k in ("son", "micro", "webcam", "touches", "clics"):
        cmd += ["--" + k, "1" if ch.get(k) else "0"]
    return cmd + list(extra or [])


def cs_launch(cmd: List[str]) -> None:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if cmd[0].lower().endswith("python.exe") else 0
    subprocess.Popen(cmd, cwd=BASE, creationflags=flags, close_fds=True)


def _cs_same_root(a: str, b: str) -> bool:
    try:
        return os.path.normcase(os.path.abspath(a or "")) == os.path.normcase(os.path.abspath(b or ""))
    except Exception:
        return False


def _cs_link_or_copy(src: str, dst: str) -> str:
    """Lien physique (même disque : aucune place en plus), sinon copie."""
    try:
        os.link(src, dst)
        return "lien"
    except Exception:
        shutil.copy2(src, dst)
        return "copie"


def _cs_unique(path: str) -> str:
    base, ext = os.path.splitext(path)
    i, p = 2, path
    while os.path.exists(p):
        p = f"{base} ({i}){ext}"
        i += 1
    return p


def _cs_thumb(video: str, dest: str) -> None:
    ff = find_ffmpeg()
    if not ff:
        return
    try:
        subprocess.run([ff, "-y", "-v", "error", "-ss", "1", "-i", video, "-frames:v", "1", "-vf", "scale=640:-2", dest],
                       timeout=60, capture_output=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:
        logger.exception("miniature capture")


def cs_ensure_collection(root: str) -> None:
    """La collection « 🎥 Mes enregistrements » existe toujours (et range les anciennes fiches CaptureScreen)."""
    try:
        names = load_collections(root)
        if CS_COLLECTION.lower() not in {n.lower() for n in names}:
            save_collections(root, names + [CS_COLLECTION])
        old = [e.get("folder") for e in load_archive_index(root)
               if (e.get("method") == "CaptureScreen" or e.get("platform") == "capture")
               and CS_COLLECTION not in (e.get("collections") or [])]
        if old:
            set_collections(root, [f for f in old if f], add=CS_COLLECTION)
    except Exception:
        logger.exception("collection Mes enregistrements")


def cs_new_fiche(root: str, title: str, platform: str = "capture", method: str = "CaptureScreen",
                 description: str = "Enregistrement d'écran fait avec CaptureScreen.", url: str = "") -> str:
    os.makedirs(root, exist_ok=True)
    folder = _cs_unique(os.path.join(root, f"{datetime.now():%Y-%m-%d}_{platform}_{slugify(title or 'video', 50)}"))
    os.makedirs(folder)
    info = {"title": title or "Vidéo", "platform": platform, "url": url, "webpage_url": url,
            "uploader": "Moi" + (" (CaptureScreen)" if method == "CaptureScreen" else ""), "description": description,
            "archived_at": datetime.now().isoformat(timespec="seconds"), "folder": os.path.basename(folder),
            "media_files": [], "method": method, "tags": [platform], "notes": "",
            "collections": [CS_COLLECTION] if method == "CaptureScreen" else []}
    _write_json_atomic(os.path.join(folder, "info.json"), info)
    return os.path.basename(folder)


def cs_attach_file(root: str, folder: str, video: str, title: str = "", from_capture: bool = True,
                   duration: Optional[float] = None, extra_files: Optional[List[str]] = None,
                   markers: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Ajoute une vidéo à une fiche (ou crée une fiche si folder est vide / introuvable). Retourne {folder, file, new}."""
    if not os.path.isfile(video):
        raise FileNotFoundError(video)
    new = False
    if not folder or folder != os.path.basename(folder) or not os.path.isdir(os.path.join(root, folder)):
        folder = cs_new_fiche(root, title or os.path.splitext(os.path.basename(video))[0],
                              *(() if from_capture else ("import", "import", "Vidéo importée depuis un fichier.")))
        new = True
    fp = os.path.join(root, folder)
    dst = _cs_unique(os.path.join(fp, os.path.basename(video)))
    how = _cs_link_or_copy(video, dst)
    for x in extra_files or []:
        if os.path.isfile(x):
            try:
                shutil.copy2(x, _cs_unique(os.path.join(fp, os.path.splitext(os.path.basename(dst))[0]
                                                         + os.path.splitext(x)[1])))
            except Exception:
                logger.exception("fichier joint")
    info = load_info(fp)
    media = [m for m in (info.get("media_files") or []) if isinstance(m, str)]
    if os.path.basename(dst) not in media:
        media.append(os.path.basename(dst))
    fields: Dict[str, Any] = {"media_files": media}
    if from_capture:
        caps = [c for c in (info.get("captures") or []) if isinstance(c, dict)]
        caps.append({"file": os.path.basename(dst), "at": datetime.now().isoformat(timespec="seconds"),
                     "duration": duration, "source": video,
                     "markers": [{"t": float(m.get("t") or 0), "label": str(m.get("label") or "")[:80]}
                                 for m in (markers or []) if isinstance(m, dict)]})
        cols = [c for c in (info.get("collections") or []) if isinstance(c, str)]
        if CS_COLLECTION.lower() not in {c.lower() for c in cols}:
            cols.append(CS_COLLECTION)
        fields.update(captures=caps, collections=cols)
    if new:
        fields["duration"] = duration
        if not find_thumbnail(fp):
            _cs_thumb(dst, os.path.join(fp, "thumb.jpg"))
    update_info_fields(root, folder, save_index=False, **fields)
    refresh_entries(root, [folder])
    if from_capture:
        cs_ensure_collection(root)
    logger.info("vidéo %s (%s) → %s", os.path.basename(dst), how, folder)
    return {"folder": folder, "file": os.path.basename(dst), "new": new, "how": how}


def cs_pending_results(root: str) -> List[Tuple[str, Dict[str, Any]]]:
    out = []
    try:
        names = sorted(os.listdir(cs_results_dir()))
    except OSError:
        return out
    for n in names:
        if not n.endswith(".json"):
            continue
        p = os.path.join(cs_results_dir(), n)
        r = _cs_json(p, None)
        if isinstance(r, dict) and _cs_same_root(r.get("root", ""), root):
            out.append((p, r))
    return out


def cs_process_results(root: str, log: Callable[[str], None] = lambda m: None) -> List[Dict[str, Any]]:
    """Range dans leurs fiches les vidéos terminées par CaptureScreen (une fois chacune)."""
    done = []
    for p, r in cs_pending_results(root):
        claim = p + ".encours"
        try:
            os.replace(p, claim)  # une seule instance la traite
        except OSError:
            continue
        try:
            res = cs_attach_file(root, r.get("dossier") or "", r.get("fichier") or "", r.get("titre") or "",
                                 True, r.get("duree"), [r["srt"]] if r.get("srt") else None, r.get("reperes") or [])
            res["titre"] = r.get("titre") or ""
            done.append(res)
            log(f"🎥 Vidéo ajoutée à la fiche : {res['folder']}")
            os.remove(claim)
        except FileNotFoundError:
            log(f"🎥 Vidéo introuvable (déplacée ou supprimée ?) : {r.get('fichier')}")
            os.replace(claim, p + ".introuvable")
        except Exception as e:
            logger.exception("ajout capture")
            log(f"🎥 Ajout impossible : {friendly_error(e)}")
            try:
                os.replace(claim, p)
            except OSError:
                pass
    return done


class _ArchiveurAppCapture:
    """🎥 Enregistrer l'écran (CaptureScreen) depuis l'aperçu + 📥 Importer une vidéo."""

    def _cs_start_polling(self):
        if getattr(self, "_cs_poll_on", False):
            return
        self._cs_poll_on = True
        threading.Thread(target=cs_ensure_collection, args=(self.archive_root_path(),), daemon=True).start()
        self.after(2500, self._cs_poll)

    def _cs_poll(self):
        try:
            root = self.archive_root_path()
            if cs_pending_results(root) and not getattr(self, "_cs_busy", False):
                self._cs_busy = True

                def work():
                    try:
                        res = cs_process_results(root, lambda m: self.ui(lambda mm=m: self.log(mm)))
                    finally:
                        self._cs_busy = False
                    if res:
                        self.ui(lambda: self._cs_done(res))
                threading.Thread(target=work, daemon=True).start()
        except Exception:
            logger.exception("poll captures")
        self.after(2000, self._cs_poll)

    def _cs_done(self, res: List[Dict[str, Any]]):
        self.refresh_list()
        self._refresh_filter_values()
        last = res[-1]
        self.select_folder(last["folder"])
        try:
            self.deiconify()
            self.lift()
            self.focus_force()
        except Exception:
            pass
        msg = ("Vidéo ajoutée à la fiche" if not last.get("new") else "Vidéo ajoutée à une nouvelle fiche") + \
              (f" « {last.get('titre')[:50]} »" if last.get("titre") else "")
        self.status.set("✅ " + msg + f" — dans {CS_COLLECTION}")
        self.cs_toast("✅ " + msg, f"Fichier : {last['file']}\nAussi dans la collection {CS_COLLECTION}.",
                      ("▶ Lire", self.play_selected))

    def cs_toast(self, title: str, sub: str = "", action: Optional[Tuple[str, Callable[[], None]]] = None, ms: int = 7000):
        try:
            t = tk.Toplevel(self)
            t.overrideredirect(True)
            t.attributes("-topmost", True)
            t.configure(bg=NC_HI)
            box = tk.Frame(t, bg=NC_CARD)
            box.pack(padx=2, pady=2)
            tk.Label(box, text=title, bg=NC_CARD, fg=NC_HI, font=FONT_BIG, anchor="w", justify="left").pack(
                fill="x", padx=12, pady=(8, 0))
            if sub:
                tk.Label(box, text=sub, bg=NC_CARD, fg=NC_TEXT, font=FONT_SM, anchor="w", justify="left").pack(
                    fill="x", padx=12)
            row = tk.Frame(box, bg=NC_CARD)
            row.pack(fill="x", padx=10, pady=8)
            if action:
                self._btn(row, action[0], lambda: (t.destroy(), action[1]()), hi=True).pack(side="left")
            self._btn(row, "✖", t.destroy).pack(side="right")
            t.update_idletasks()
            x = self.winfo_rootx() + self.winfo_width() - t.winfo_reqwidth() - 24
            y = self.winfo_rooty() + self.winfo_height() - t.winfo_reqheight() - 60
            t.geometry(f"+{max(0, x)}+{max(0, y)}")
            t.after(ms, lambda: t.winfo_exists() and t.destroy())
            self._cs_last_toast = t
        except Exception:
            logger.exception("toast")

    # ---------------------------------------------------------- 🎥 Enregistrer
    def record_screen(self):
        if not os.path.isfile(cs_script()):
            messagebox.showerror(APP_NAME, "CaptureScreen est introuvable (capturescreen1.py).\n"
                                 "Réinstalle Padawan pour l'avoir.", parent=self)
            return
        e = self._preview_entry if (self._preview_entry and self._preview_path
                                     and os.path.isdir(self._preview_path)) else None
        folder = (e or {}).get("folder") or ""
        title = (self.name_var.get().strip() or (e or {}).get("title") or "") if e else ""
        url = self._entry_url() if e else ""
        protected = False
        if e:
            try:
                protected = bool((self._preview_info.get("embed") or {}).get("protected"))
            except Exception:
                protected = False
        self._cs_dialog(folder, title, url, protected)

    def _cs_dialog(self, folder: str, title: str, url: str, protected: bool):
        old = getattr(self, "_cs_win", None)
        if old is not None and old.winfo_exists():
            old.lift()
            return
        ch = cs_choices()
        d = tk.Toplevel(self)
        self._cs_win = d
        d.title("🎥 Enregistrer l'écran")
        d.configure(bg=NC_BG)
        d.transient(self)
        d.resizable(False, False)
        pad = dict(padx=16)
        tk.Label(d, text="🎥 Enregistrer l'écran", bg=NC_BG, fg=NC_HI, font=FONT_TITLE, anchor="w").pack(
            fill="x", pady=(12, 0), **pad)
        dest = (f"La vidéo sera ajoutée à la fiche « {title[:60]} »." if folder
                else "Aucune fiche choisie : une nouvelle fiche sera créée.")
        tk.Label(d, text=dest, bg=NC_BG, fg=NC_DIM, font=FONT_UI, anchor="w").pack(fill="x", **pad)

        nm = tk.Frame(d, bg=NC_BG)
        nm.pack(fill="x", pady=(10, 0), **pad)
        tk.Label(nm, text="Nom de la vidéo :", bg=NC_BG, fg=NC_TEXT, font=FONT_UI).pack(side="left")
        name_v = tk.StringVar(value=title or f"Enregistrement {datetime.now():%Y-%m-%d}")
        ent = tk.Entry(nm, textvariable=name_v, bg=NC_ENTRY_BG, fg=NC_HI, insertbackground=NC_FG,
                       font=FONT_UI, relief="flat", width=46)
        ent.pack(side="left", fill="x", expand=True, padx=(8, 0), ipady=3)

        tk.Label(d, text="Qu'est-ce qu'on enregistre ?", bg=NC_BG, fg=NC_TEXT, font=FONT_UI, anchor="w").pack(
            fill="x", pady=(12, 4), **pad)
        tiles = tk.Frame(d, bg=NC_BG)
        tiles.pack(fill="x", **pad)
        mode_v = tk.StringVar(value=ch.get("mode", "ecran"))
        tbtn: Dict[str, tk.Button] = {}

        def paint():
            for k, b in tbtn.items():
                on = mode_v.get() == k
                b.configure(bg=NC_HI if on else NC_CARD, fg=NC_ON_HI if on else NC_TEXT,
                            relief="sunken" if on else "raised")
        for i, (k, ico, lab, tip) in enumerate(CS_MODES):
            b = tk.Button(tiles, text=f"{ico}\n{lab}", font=FONT_BIG, width=13, height=3, bd=2, cursor="hand2",
                          command=lambda kk=k: (mode_v.set(kk), paint()))
            b.grid(row=0, column=i, padx=4, sticky="ew")
            tiles.columnconfigure(i, weight=1)
            b.bind("<Double-Button-1>", lambda ev, kk=k: (mode_v.set(kk), go()))
            Tooltip(b, tip + f"  —  touche {i + 1}")
            tbtn[k] = b
        paint()

        opts = tk.Frame(d, bg=NC_BG)
        opts.pack(fill="x", pady=(10, 0), **pad)
        vars_: Dict[str, tk.BooleanVar] = {}
        for i, (k, lab, tip) in enumerate((
                ("son", "🔊 Son de l'ordi", "Enregistre ce que tu entends (vidéo, musique, appels…)"),
                ("micro", "🎤 Micro", "Enregistre ta voix (le micro par défaut de Windows)"),
                ("webcam", "📷 Webcam", "Ta webcam dans une petite bulle, dans un coin de la vidéo"),
                ("touches", "⌨ Afficher les touches", "Montre les raccourcis (Ctrl+C…) dans une bulle.\n"
                                                      "Les lettres tapées (mots de passe) ne sont jamais montrées."),
                ("clics", "🖱 Montrer les clics", "Un halo coloré apparaît à chaque clic"))):
            v = tk.BooleanVar(value=bool(ch.get(k)))
            vars_[k] = v
            cb = tk.Checkbutton(opts, text=lab, variable=v, bg=NC_BG, fg=NC_TEXT, selectcolor=NC_ENTRY_BG,
                                activebackground=NC_BG, activeforeground=NC_HI, font=FONT_UI, anchor="w")
            cb.grid(row=i // 3, column=i % 3, sticky="w", padx=(0, 14), pady=1)
            Tooltip(cb, tip)
        site_v = tk.BooleanVar(value=bool(ch.get("ouvrir_site", True)))
        if url:
            cb = tk.Checkbutton(d, text="🌐 Ouvrir le site d'abord (puis je te laisse préparer la page avant le 3-2-1)",
                                variable=site_v, bg=NC_BG, fg=NC_TEXT, selectcolor=NC_ENTRY_BG, activebackground=NC_BG,
                                activeforeground=NC_HI, font=FONT_UI, anchor="w")
            cb.pack(fill="x", pady=(8, 0), **pad)
            Tooltip(cb, f"Ouvre {url[:80]}\nQuand la page est prête, clique « ⏺ Commencer » : 3-2-1 et ça enregistre.")
            if protected:
                tk.Label(d, text="ℹ Les vidéos protégées (Netflix, Tubi…) apparaissent souvent en noir : c'est voulu par\n"
                                 "le site, et on ne contourne pas les protections.", bg=NC_BG, fg=NC_DIM, font=FONT_SM,
                         anchor="w", justify="left").pack(fill="x", **pad)

        tk.Label(d, text="Pendant l'enregistrement, une petite barre flottante (invisible dans la vidéo) te donne :\n"
                         "⏸ Pause · ⏹ Arrêter · ✏ Dessiner · 🔦 Projecteur · 🔍 Loupe · ⬜ Tableau blanc · ⏱ Minuteur · 📸 Photo.\n"
                         "Raccourcis partout : Ctrl+Maj+R arrêter · Ctrl+Maj+P pause · Ctrl+Maj+D dessiner · Ctrl+Maj+K 🔖 repère (chapitre).",
                 bg=NC_BG, fg=NC_DIM, font=FONT_SM, anchor="w", justify="left").pack(fill="x", pady=(10, 0), **pad)

        bot = tk.Frame(d, bg=NC_BG)
        bot.pack(fill="x", pady=14, **pad)

        def collect() -> Dict[str, Any]:
            c = {k: bool(v.get()) for k, v in vars_.items()}
            c["mode"] = mode_v.get()
            c["ouvrir_site"] = bool(site_v.get())
            cs_save_choices(c)
            return c

        def go(_e=None):
            c = collect()
            d.destroy()
            try:
                cs_launch(cs_command(self.archive_root_path(), folder, name_v.get().strip() or title, url, c))
                self.status.set("🎥 CaptureScreen se prépare… " + ("(le site s'ouvre d'abord)" if url and c["ouvrir_site"]
                                                                  else "3-2-1 et ça enregistre"))
                self._cs_start_polling()
            except Exception as ex:
                logger.exception("lancement CaptureScreen")
                messagebox.showerror(APP_NAME, f"CaptureScreen n'a pas pu démarrer :\n{friendly_error(ex)}", parent=self)

        def full():
            collect()
            d.destroy()
            try:
                cs_launch([cs_python(), cs_script()])
            except Exception as ex:
                messagebox.showerror(APP_NAME, f"CaptureScreen n'a pas pu démarrer :\n{friendly_error(ex)}", parent=self)

        start = tk.Button(bot, text="⏺  Commencer", command=go, font=FONT_BIG, bg="#d7263d", fg="white",
                          activebackground="#ff4d6d", activeforeground="white", bd=0, padx=22, pady=8, cursor="hand2")
        start.pack(side="left")
        Tooltip(start, "Entrée — CaptureScreen démarre (3-2-1), puis la vidéo revient toute seule dans cette fiche")
        b = self._btn(bot, "⚙ CaptureScreen complet…", full)
        b.pack(side="left", padx=10)
        Tooltip(b, "Ouvre CaptureScreen avec tous ses réglages (qualité, écran, préréglages, bibliothèque…)")
        self._btn(bot, "Annuler", d.destroy).pack(side="right")
        d.bind("<Return>", go)
        d.bind("<Escape>", lambda e: d.destroy())
        for i, (k, *_r) in enumerate(CS_MODES):
            d.bind(str(i + 1), lambda e, kk=k: None if e.widget is ent else (mode_v.set(kk), paint()))
        d.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - d.winfo_reqwidth()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - d.winfo_reqheight()) // 3
        d.geometry(f"+{max(0, x)}+{max(0, y)}")
        d.grab_set()
        start.focus_set()
        return d

    # ---------------------------------------------------------- 🔖 repères d'un enregistrement (clic = lire là)
    def _cs_markers_update(self, info: Dict[str, Any]):
        box = getattr(self, "_cs_mark_box", None)
        if box is None:
            box = tk.Frame(self._act_flow.master, bg=NC_BG)
            self._cs_mark_box = box
        for w in box.winfo_children():
            w.destroy()
        main = os.path.basename(find_main_media(self._preview_path) or "") if self._preview_path else ""
        marks: List[Dict[str, Any]] = []
        for c in info.get("captures") or []:
            if isinstance(c, dict) and c.get("file") == main:
                marks = [m for m in (c.get("markers") or []) if isinstance(m, dict)]
        if not marks:
            if box.winfo_ismapped():
                box.pack_forget()
            return
        tk.Label(box, text="🔖 Repères :", bg=NC_BG, fg=NC_HI, font=FONT_UI).pack(side="left", padx=(0, 4))
        for m in marks[:24]:
            t = float(m.get("t") or 0)
            b = self._btn(box, f"▶ {fmt_ts(t)} {str(m.get('label') or '')[:24]}",
                          lambda tt=t: (self.player_seek_to(tt, play=True), self.status.set(f"▶ Lecture à {fmt_ts(tt)}")))
            b.pack(side="left", padx=2)
            Tooltip(b, "Lire l'enregistrement à partir de ce repère")
        if not box.winfo_ismapped():
            box.pack(fill="x", padx=6, pady=(0, 4), after=self._act_flow)

    # ---------------------------------------------------------- 📥 Importer une vidéo
    def import_video_dialog(self):
        files = filedialog.askopenfilenames(
            parent=self, title="Importer une ou des vidéos dans l'Archiveur",
            filetypes=[("Vidéos et sons", " ".join("*" + x for x in VIDEO_EXTS + AUDIO_EXTS)), ("Tous les fichiers", "*.*")])
        if not files:
            return
        e = self._preview_entry if (self._preview_entry and self._preview_path
                                     and os.path.isdir(self._preview_path)) else None
        folder = ""
        if e:
            r = messagebox.askyesnocancel(
                APP_NAME, f"Ajouter {'cette vidéo' if len(files) == 1 else f'ces {len(files)} vidéos'} à la fiche\n"
                          f"« {(e.get('title') or e.get('folder'))[:70]} » ?\n\n"
                          "Oui = à cette fiche    Non = une nouvelle fiche par vidéo", parent=self)
            if r is None:
                return
            folder = e.get("folder") if r else ""
        root = self.archive_root_path()
        self.status.set(f"📥 Importation de {len(files)} fichier(s)…")

        def work():
            res = []
            for f in files:
                try:
                    res.append(cs_attach_file(root, folder, f, os.path.splitext(os.path.basename(f))[0],
                                              from_capture=False, duration=None))
                except Exception as ex:
                    logger.exception("import vidéo")
                    self.ui(lambda m=f"📥 Import impossible : {os.path.basename(f)} ({friendly_error(ex)})": self.log(m))

            def done():
                if not res:
                    self.status.set("📥 Rien n'a été importé.")
                    return
                self.refresh_list()
                self.select_folder(res[-1]["folder"])
                self.status.set(f"✅ {len(res)} vidéo(s) importée(s).")
                self.cs_toast(f"✅ {len(res)} vidéo(s) importée(s)", "Copiées dans l'archive (l'original reste en place).",
                              ("▶ Lire", self.play_selected))
            self.ui(done)
        threading.Thread(target=work, daemon=True).start()
