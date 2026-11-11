# -*- coding: utf-8 -*-
# Partie de archiveur5.py (découpage v1.2.2, comportement inchangé).
# Chargée par archiveur5.py dans un espace de noms commun : ne pas lancer seule.
from __future__ import annotations



class _ArchiveurAppPartie1:
    """Méthodes de ArchiveurApp (partie 1/3)."""

    def __init__(self, smoke: float = 0.0, geometry: str = "", shot: str = "", force_scaling: float = 0.0,
                 root_override: str = "", font_delta: Optional[int] = None, shot_action: str = ""):
        super().__init__()
        if force_scaling:
            try:
                self.tk.call("tk", "scaling", force_scaling)
            except Exception:
                pass
        _fd = font_delta if font_delta is not None else int(_EARLY_CFG.get("font_delta") or 0)
        init_fonts(self, _fd)
        self._shot_action = shot_action
        self._root_override = root_override
        self._save_cfg_job = None
        self._online_busy = False
        self._export_busy = False
        self._dnd_ok = False
        self._modal_win = None
        self.title(APP_NAME)
        self._test_geometry = geometry
        self._shot = shot
        self._players = detect_players()
        self._codec_cache: Dict[Tuple[str, float], Dict[str, Any]] = {}
        self._bottom_view = "queue"
        self._bottom_open = False
        self._bottom_auto = False
        self.cfg = load_cfg()
        if font_delta is not None:
            self.cfg["font_delta"] = font_delta
        if root_override:
            self.cfg["archive_root"] = root_override
        self.archive_root = self.cfg.get("archive_root") or DEFAULT_ROOT
        self._smoke = smoke
        self._errors: List[str] = []
        self._uiq: "queue.Queue[Callable[[], None]]" = queue.Queue()
        self.jobs: List[Dict[str, Any]] = []
        self._job_seq = 0
        self._jobs_lock = threading.Lock()
        self._worker_running = False
        self._cancel_event = threading.Event()
        self._run_stats = {"ok": 0, "echec": 0, "annule": 0, "last_title": ""}
        self.entries: List[Dict[str, Any]] = []
        self._visible: List[Dict[str, Any]] = []
        self._iid_entry: Dict[str, Dict[str, Any]] = {}
        self.last_folder: Optional[str] = None
        self._preview_entry: Optional[Dict[str, Any]] = None
        self._preview_info: Dict[str, Any] = {}
        self._preview_path = ""
        self._loaded_tn = ("", "")
        self._thumb_src = None
        self._thumb_base = None
        self._thumb_is_video = False
        self._thumb_photo = None
        self._sb_photos: List[Any] = []
        self._gal_photos: List[Any] = []
        self._list_thumbs: Dict[Tuple[str, float], Any] = {}
        self._sb_busy: set = set()
        self._sb_failed: set = set()
        self._sb_imcache: Dict[Tuple[str, float, int], Any] = {}
        self._auto_undo: Optional[Dict[str, Any]] = None
        self._sug: Optional[Tuple[str, str]] = None
        self._coll_side_lock = False
        self._clip_last: Optional[str] = None
        self._clip_seen: set = set()
        self._clip_job = None
        self._clip_pending: List[str] = []
        self._resize_job = None
        self._link_target: Tuple[str, str] = ("url", "")
        self._link_seq = 0
        self.report_callback_exception = self._tk_error
        self._build_ui()
        self._build_ui_rest()
        self.after(40, self._drain_ui)
        self.after(150, self._post_init)

    # ------------------------------------------------------------ thread-safe UI
    def ui(self, fn: Callable[[], None]) -> None:
        """Planifie fn dans le thread Tk (file + after())."""
        self._uiq.put(fn)

    def _drain_ui(self):
        for _ in range(300):
            try:
                fn = self._uiq.get_nowait()
            except queue.Empty:
                break
            try:
                fn()
            except Exception as e:
                self._tk_error(type(e), e, e.__traceback__)
        try:
            self.after(40, self._drain_ui)
        except Exception:
            pass

    def _tk_error(self, exc, val, tb):
        msg = "".join(traceback.format_exception(exc, val, tb))
        logger.error("Erreur interface:\n%s", msg)
        self._errors.append(f"{exc.__name__}: {val}")
        try:
            print(msg, file=sys.stderr, flush=True)
        except Exception:
            pass
        try:
            self.status.set(f"⚠ Erreur interne : {val} — détails dans archiveur.log")
        except Exception:
            pass

    # ------------------------------------------------------------ helpers UI
    def _btn(self, parent, text, cmd, hi=False, font=FONT_SM, **kw):
        return tk.Button(
            parent, text=text, command=cmd,
            bg=NC_HI if hi else NC_BTN, fg=NC_ON_HI if hi else NC_BTN_FG,
            activebackground=NC_HI_ACT if hi else NC_HI, activeforeground=NC_ON_HI,
            font=font, relief="raised", bd=1, padx=6, cursor="hand2",
            disabledforeground=NC_DISABLED, **kw,
        )

    def _scrolled_text(self, parent, height=8, **kw):
        fr = tk.Frame(parent, bg=NC_BG)
        txt = tk.Text(fr, height=height, bg=kw.pop("bg", NC_PANEL), fg=kw.pop("fg", NC_FG),
                      insertbackground=NC_FG, wrap=kw.pop("wrap", "word"), bd=1, relief="sunken",
                      selectbackground=NC_SEL, selectforeground=NC_ON_SEL, **kw)
        sb = ttk.Scrollbar(fr, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        txt.pack(side="left", fill="both", expand=True)
        return fr, txt

    def _section(self, parent, text):
        lab = tk.Label(parent, text=text, bg=NC_BG, fg=NC_HI, font=FONT_UI, anchor="w")
        lab.pack(fill="x", padx=8, pady=(12, 2))
        line = tk.Frame(parent, bg=NC_LINE, height=1)
        line.pack(fill="x", padx=8, pady=(0, 4))
        lab._line = line  # type: ignore[attr-defined]
        return lab

    # ------------------------------------------------------------ construction
    def _build_ui(self):
        self.configure(bg=NC_BG)
        if self._test_geometry:
            self.geometry(f"{self._test_geometry}+0+0")
            try:
                self.attributes("-topmost", True)
            except Exception:
                pass
        else:
            self._zoom()
        self.minsize(900, 520)

    def _zoom(self):
        try:
            self.state("zoomed")
        except Exception:
            try:
                self.attributes("-zoomed", True)
            except Exception:
                pass
            self.geometry(f"{self.winfo_screenwidth()}x{self.winfo_screenheight()}+0+0")

    def _build_ui_rest(self):
        ico, png = generate_icons(BASE)
        try:
            if os.path.isfile(ico) and sys.platform.startswith("win"):
                self.iconbitmap(ico)
        except Exception:
            pass
        try:
            if os.path.isfile(png):
                self._icon_img = tk.PhotoImage(file=png)
                self.iconphoto(True, self._icon_img)
        except Exception:
            pass

        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TFrame", background=NC_BG)
        style.configure("TLabel", background=NC_BG, foreground=NC_FG, font=FONT_UI)
        style.configure("TCheckbutton", background=NC_BG, foreground=NC_FG, font=FONT_SM)
        style.map("TCheckbutton", background=[("active", NC_PANEL)], foreground=[("active", NC_HI)])
        style.configure("TButton", font=FONT_UI)
        style.configure("TLabelframe", background=NC_BG, foreground=NC_HI, bordercolor=NC_FG)
        style.configure("TLabelframe.Label", background=NC_BG, foreground=NC_HI, font=FONT_UI)
        style.configure("TCombobox", fieldbackground=NC_ENTRY_BG, background=NC_BTN, foreground=NC_ENTRY_FG,
                        arrowcolor=NC_HI, selectbackground=NC_ENTRY_BG, selectforeground=NC_ENTRY_FG)
        style.map("TCombobox", fieldbackground=[("readonly", NC_ENTRY_BG)], foreground=[("readonly", NC_ENTRY_FG)])
        self.option_add("*TCombobox*Listbox.background", NC_PANEL)
        self.option_add("*TCombobox*Listbox.foreground", NC_FG)
        self.option_add("*TCombobox*Listbox.selectBackground", NC_SEL)
        self.option_add("*TCombobox*Listbox.selectForeground", NC_ON_SEL)
        style.configure("Vertical.TScrollbar", background=NC_BTN, troughcolor=NC_PANEL,
                        arrowcolor=NC_HI, bordercolor=NC_FG, lightcolor=NC_BTN, darkcolor=NC_BTN)
        style.map("Vertical.TScrollbar", background=[("active", NC_SEL)])
        for name, rh in (("Arch.Treeview", 52), ("Files.Treeview", 24), ("Queue.Treeview", 24)):
            style.configure(name, background=NC_PANEL, fieldbackground=NC_PANEL, foreground=NC_FG,
                            rowheight=rh, font=FONT_SM, bordercolor=NC_LINE, indent=4)
            style.map(name, background=[("selected", NC_SEL)], foreground=[("selected", NC_ON_SEL)])
            style.configure(name + ".Heading", background=NC_BG, foreground=NC_HI, font=FONT_SM, relief="raised")
            style.map(name + ".Heading", background=[("active", NC_PANEL)])
        style.configure("Coll.Treeview", background=NC_PANEL, fieldbackground=NC_PANEL, foreground=NC_TEXT,
                        rowheight=30, font=FONT_UI, bordercolor=NC_LINE, indent=2)
        style.map("Coll.Treeview", background=[("selected", NC_HI)], foreground=[("selected", NC_ON_HI)])
        style.configure("TNotebook", background=NC_BG, bordercolor=NC_FG)
        style.configure("TNotebook.Tab", background=NC_PANEL, foreground=NC_FG, font=FONT_SM, padding=(10, 3))
        style.map("TNotebook.Tab", background=[("selected", NC_HI)], foreground=[("selected", NC_ON_HI)])
        style.configure("Arch.Horizontal.TProgressbar", troughcolor=NC_PANEL, background=NC_HI,
                        bordercolor=NC_FG, lightcolor=NC_HI, darkcolor=NC_SEL)
        style.configure("Arch.Horizontal.TScale", background=NC_HI, troughcolor=NC_ENTRY_BG, bordercolor=NC_LINE,
                        lightcolor=NC_HI, darkcolor=NC_SEL, sliderlength=18)
        style.map("Arch.Horizontal.TScale", background=[("active", NC_HI_ACT)])
        style.configure("TCheckbutton", background=NC_BG, foreground=NC_FG, font=FONT_SM)
        style.configure("TCombobox", arrowsize=max(12, font_px(self, FONT_SM) - 2))
        self._apply_row_heights()
        self._build_top()
        # barre d'état (tout en bas) puis panneau file/journal repliable, puis contenu
        self.status = tk.StringVar(value="Prêt.")
        sbar = tk.Frame(self, bg=NC_PANEL)
        sbar.pack(fill="x", side="bottom")
        keys = tk.Label(sbar, text="⌨ Raccourcis", bg=NC_PANEL, fg=NC_DIM, font=FONT_SM, cursor="question_arrow")
        keys.pack(side="right", padx=8)
        Tooltip(keys, "F1 = aide complète\nCtrl+V = coller + archiver (partout hors champs texte)\n"
                      "Ctrl+Espace = lecture / pause · Ctrl+←/→ = ±10 s\nCtrl+F = chercher dans l'historique\n"
                      "Ctrl+D = favori · Ctrl+E = export ZIP · Ctrl+A = tout sélectionner\n"
                      "Ctrl+S = enregistrer tags/notes · F2 = renommer · F5 = rafraîchir\n"
                      "Ctrl+molette ou Ctrl +/−/0 = taille du texte\nSuppr = supprimer · Échap = replier la file")
        keys.bind("<Button-1>", lambda e: self.open_help())
        tk.Label(sbar, textvariable=self.status, bg=NC_PANEL, fg=NC_HI, font=FONT_SM, anchor="w").pack(
            side="left", fill="x", expand=True, padx=8, pady=2)
        bottom = tk.Frame(self, bg=NC_BG)
        bottom.pack(fill="x", side="bottom", padx=8, pady=(2, 0))
        self._build_bottom(bottom)

        self.hpane = tk.PanedWindow(self, orient="horizontal", bg=NC_SASH, sashwidth=7,
                                    sashrelief="raised", bd=0, opaqueresize=True)
        self.hpane.pack(fill="both", expand=True, padx=8, pady=(2, 0))
        left = tk.Frame(self.hpane, bg=NC_BG)
        right = tk.Frame(self.hpane, bg=NC_BG)
        self.hpane.add(left, minsize=300, stretch="always")
        self.hpane.add(right, minsize=400, stretch="always")
        self._build_history(left)
        self._build_preview(right)

        self._link_menu = self._menu()
        self._link_menu.add_command(label="🌐 Ouvrir le lien", command=self._link_open)
        self._link_menu.add_command(label="📋 Copier le lien", command=self._link_copy)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<F2>", lambda e: self.rename_selected())
        self.bind("<Control-f>", lambda e: (self.search_entry.focus_set(), "break")[1])
        self.bind("<Control-F>", lambda e: (self.search_entry.focus_set(), "break")[1])
        self.bind("<Control-s>", lambda e: (self.save_tags_notes(), "break")[1])
        self.bind("<Control-S>", lambda e: (self.save_tags_notes(), "break")[1])
        self.bind_all("<MouseWheel>", self._on_wheel, add="+")
        self.bind_all("<Button-4>", self._on_wheel, add="+")
        self.bind_all("<Button-5>", self._on_wheel, add="+")
        self.bind("<Control-v>", self._global_paste)
        self.bind("<Control-V>", self._global_paste)
        self.bind("<Escape>", lambda e: self._collapse_bottom() if self._bottom_open else None)
        self._bind_v5_keys()
        self.after(1500, self._cs_start_polling)  # vidéos CaptureScreen → fiches
        self.after(300, self._init_sashes)
        self.after(600, self._init_sashes)

    def _menu(self):
        return tk.Menu(self, tearoff=0, bg=NC_PANEL, fg=NC_FG, activebackground=NC_SEL,
                       activeforeground=NC_ON_SEL, font=FONT_SM)

    def _init_sashes(self):
        try:
            self.update_idletasks()
            w = self.hpane.winfo_width()
            if w > 100 and not getattr(self, "_sash_user", False):
                self.hpane.sash_place(0, max(300, min(int(w * 0.42), w - 420)), 0)
        except Exception:
            logger.exception("sash")

    def _global_paste(self, event=None):
        """Ctrl+V hors champ texte = coller + archiver."""
        try:
            cls = event.widget.winfo_class() if event is not None else ""
        except Exception:
            cls = ""
        if cls in ("Entry", "Text", "TEntry", "TCombobox", "Spinbox"):
            return None
        self.paste_and_archive()
        return "break"

    def _build_top(self):
        top = tk.Frame(self, bg=NC_BG)
        top.pack(fill="x", padx=8, pady=(6, 2))
        url_row = tk.Frame(top, bg=NC_BG)
        url_row.pack(fill="x", pady=(0, 3))
        url_row.columnconfigure(0, weight=1)
        fr, self.url_text = self._scrolled_text(url_row, height=2, bg=NC_ENTRY_BG, fg=NC_ENTRY_FG, font=FONT_UI)
        fr.grid(row=0, column=0, sticky="nsew")
        paste_btn = tk.Button(
            url_row, text="📋 Coller et\narchiver", command=self.paste_and_archive,
            bg=NC_HI, fg=NC_ON_HI, font=FONT_PASTE, activebackground=NC_HI_ACT,
            activeforeground=NC_ON_HI, justify="center", cursor="hand2", padx=10,
        )
        paste_btn.grid(row=0, column=1, sticky="ns", padx=(6, 0))
        Tooltip(paste_btn, "Colle le lien copié (presse-papiers), l'affiche dans le champ et lance l'archivage.\nRaccourci : Ctrl+V")
        side = tk.Frame(url_row, bg=NC_BG)
        side.grid(row=0, column=2, sticky="ns", padx=(6, 0))
        b = self._btn(side, "▶ Archiver", self.enqueue_from_text, font=FONT_UI)
        b.pack(fill="x", pady=(0, 3))
        Tooltip(b, "Archive le(s) lien(s) écrit(s) dans le champ (Entrée)")
        b = self._btn(side, "📝 Plusieurs liens…", self.open_batch_dialog)
        b.pack(fill="x")
        Tooltip(b, "Coller une liste de liens à archiver en lot")
        t = self.url_text
        self._url_ph = False
        t.tag_configure("ph", foreground=NC_DIM)
        self._url_placeholder()
        t.bind("<Key>", self._url_key, add="+")
        t.bind("<FocusOut>", lambda e: self._url_placeholder(), add="+")
        t.bind("<Control-v>", self._on_paste_archive)
        t.bind("<Control-V>", self._on_paste_archive)
        t.bind("<Shift-Insert>", self._on_paste_archive)
        t.bind("<Control-a>", self._on_select_all)
        t.bind("<Control-A>", self._on_select_all)
        t.bind("<Return>", self._on_enter_archive)
        t.bind("<Control-Return>", self._on_enter_archive)
        t.bind("<Button-3>", self._show_url_menu)
        self._url_menu = self._menu()
        self._url_menu.add_command(label="📋 Coller et archiver", command=self.paste_and_archive)
        self._url_menu.add_command(label="📰 Archiver comme page web (lecture + capture + PDF)",
                                   command=self.archive_text_as_page)
        self._url_menu.add_command(label="Coller", command=self._ctx_paste)
        self._url_menu.add_command(label="Copier", command=self._ctx_copy)
        self._url_menu.add_command(label="Couper", command=self._ctx_cut)
        self._url_menu.add_separator()
        self._url_menu.add_command(label="Tout sélectionner", command=lambda: self._on_select_all())
        self._url_menu.add_command(label="Effacer", command=self._ctx_clear)

        # bannière presse-papiers (cachée par défaut)
        self.clip_banner = tk.Frame(top, bg=NC_HI)
        self.clip_msg = tk.Label(self.clip_banner, text="", bg=NC_HI, fg=NC_ON_HI, font=FONT_UI, anchor="w")
        self.clip_msg.pack(side="left", fill="x", expand=True, padx=6, pady=3)
        self.clip_btns = tk.Frame(self.clip_banner, bg=NC_HI)
        self.clip_btns.pack(side="right", padx=4)
        self._clip_anchor = tk.Frame(top, bg=NC_BG, height=0)
        self._clip_anchor.pack(fill="x")

        self.subs_var = tk.BooleanVar(value=bool(self.cfg.get("subtitles", True)))
        self.sb_var = tk.BooleanVar(value=bool(self.cfg.get("storyboard", True)))
        self.cookies_var = tk.BooleanVar(value=bool(self.cfg.get("cookies_from_browser")))
        self.browser_var = tk.StringVar(value=str(self.cfg.get("cookies_browser") or "chrome"))
        self.clip_var = tk.BooleanVar(value=bool(self.cfg.get("clipboard_watch", False)))
        self.clip_auto_var = tk.BooleanVar(value=bool(self.cfg.get("clipboard_auto", False)))
        self.notif_var = tk.BooleanVar(value=bool(self.cfg.get("notifications", True)))
        self.conv_var = tk.BooleanVar(value=bool(self.cfg.get("auto_convert", True)))
        self.quality_var = tk.StringVar(value=LABEL_BY_QUALITY.get(self.cfg.get("quality"), "Meilleure"))
        self.root_var = tk.StringVar(value=self.archive_root)

        flow = FlowFrame(top)
        flow.pack(fill="x", pady=(2, 0))
        self.opts_flow = flow

        def group(*_a):
            return tk.Frame(flow, bg=NC_BG)

        g = group()
        tk.Label(g, text="Qualité:", bg=NC_BG, fg=NC_FG, font=FONT_SM).pack(side="left")
        cb = ttk.Combobox(g, textvariable=self.quality_var, values=[lab for _k, lab in QUALITY_LABELS],
                          width=11, state="readonly", font=FONT_SM)
        cb.pack(side="left", padx=(3, 0))
        cb.bind("<<ComboboxSelected>>", lambda e: self._persist_opts())
        flow.add(g, "Vidéo : H.264/AAC en MP4 (lisible partout) à la meilleure résolution disponible.")

        def chk(text, var, cmd, tip):
            w = ttk.Checkbutton(flow, text=text, variable=var, command=cmd)
            flow.add(w, tip)
            return w
        chk("Sous-titres", self.subs_var, self._persist_opts, "Télécharge aussi les sous-titres FR/EN (.vtt)")
        g = group()
        ttk.Checkbutton(g, text="Cookies", variable=self.cookies_var, command=self._persist_opts).pack(side="left")
        bcb = ttk.Combobox(g, textvariable=self.browser_var, values=("chrome", "edge", "firefox"),
                           width=7, state="readonly", font=FONT_SM)
        bcb.pack(side="left", padx=(2, 0))
        bcb.bind("<<ComboboxSelected>>", lambda e: self._persist_opts())
        flow.add(g, "Utiliser les cookies du navigateur (posts X/Facebook qui exigent une connexion)")
        chk("📋 Surveiller", self.clip_var, self._toggle_clip_watch,
            "Surveiller le presse-papiers : propose d'archiver chaque lien que tu copies")
        chk("lancer auto", self.clip_auto_var, self._persist_opts,
            "Avec la surveillance : archiver tout de suite sans demander")

        vals = [PLAYER_LABELS["windows"]] + [PLAYER_LABELS[k] for k in ("vlc", "mpv") if k in self._players]
        cur = self.cfg.get("player") or "windows"
        if cur not in self._players:
            cur = "windows"
        self.player_var = tk.StringVar(value=PLAYER_LABELS.get(cur, PLAYER_LABELS["windows"]))

        for txt, cmd, tip, hi in (
            ("🌐 Index", self.open_global_index, "Page HTML de toutes les archives (cartes, recherche, favoris)", False),
        ):
            flow.add(self._btn(flow, txt, cmd, hi=hi), tip)
        self._tools_btn = flow.add(self._btn(flow, "🧰 Outils ▾", lambda: self._post_menu(self._tools_btn, self._build_tools_menu())),
                                   "Vérifier les archives, vérifier si les originaux sont en ligne, statistiques,\n"
                                   "export ZIP / catalogue, régénérer l'index, réparer les codecs, mise à jour de yt-dlp")
        flow.add(self._btn(flow, "⚙ Réglages", self.open_settings),
                 "Thème, taille du texte, lecteur intégré, capture des pages web, X (fxtwitter), Whisper")
        flow.add(self._btn(flow, "❓ Aide", self.open_help), "Mode d'emploi et raccourcis clavier (F1)")
        flow.add(self._btn(flow, "📂 Ouvrir le dossier", self.open_last_or_selected_folder, hi=True),
                 "Ouvre le dossier de l'archive sélectionnée (sinon la dernière, sinon la racine)")

    # ------------------------------------------------------------ champ URL : texte d'aide
    _URL_HINT = "Colle un lien ici (Ctrl+V = coller + archiver) — ou plusieurs, un par ligne"

    def _url_placeholder(self):
        t = self.url_text
        if not t.get("1.0", "end-1c").strip():
            t.delete("1.0", "end")
            t.insert("1.0", self._URL_HINT, ("ph",))
            self._url_ph = True

    def _url_clear_ph(self):
        if self._url_ph:
            self.url_text.delete("1.0", "end")
            self._url_ph = False

    def _url_key(self, event):
        if event.keysym in ("Control_L", "Control_R", "Shift_L", "Shift_R", "Alt_L", "Alt_R", "Tab"):
            return None
        if self._url_ph and not (event.state & 0x4):
            self._url_clear_ph()
        return None

    def _url_content(self) -> str:
        return "" if self._url_ph else self.url_text.get("1.0", "end")

    # ------------------------------------------------------------ historique
    def _build_history(self, left):
        # barre des collections (à gauche) : clic = n'afficher que cette collection
        # v1.2.4 : barre redimensionnable (glisser la séparation ; double-clic = largeur auto), largeur mémorisée
        self._side_pane = tk.PanedWindow(left, orient="horizontal", bg=NC_SASH, sashwidth=6, sashrelief="raised",
                                         bd=0, opaqueresize=True)
        self._side_pane.pack(fill="both", expand=True)
        side = tk.Frame(self._side_pane, bg=NC_PANEL, highlightbackground=NC_LINE, highlightthickness=1)
        self._coll_side = side
        main = tk.Frame(self._side_pane, bg=NC_BG)
        self._hist_main = main
        self._side_w_saved = int(self.cfg.get("coll_side_w") or 0)
        self._side_pane.add(side, minsize=100, width=self._side_w_saved or 150, stretch="never")
        self._side_pane.add(main, minsize=260, stretch="always")
        self._side_pane.bind("<ButtonRelease-1>", self._side_sash_saved, add="+")
        self._side_pane.bind("<Double-Button-1>", lambda _e: self._side_autofit(force=True), add="+")
        Tooltip(self._side_pane, "Glisse la séparation pour élargir / rétrécir les collections.\n"
                                 "Double-clic sur la séparation = largeur automatique.")
        tk.Label(side, text="📚 Collections", bg=NC_PANEL, fg=NC_HI, font=FONT_UI, anchor="w").pack(
            fill="x", padx=4, pady=(4, 1))
        self.coll_tree = ttk.Treeview(side, style="Coll.Treeview", show="tree", selectmode="browse", height=10)
        try:
            cw = max(150, tkfont.nametofont(FONT_UI, root=self).measure("Santé & Nutrition (99)") + 12)
        except Exception:
            cw = 180
        self.coll_tree.column("#0", width=80, minwidth=60, stretch=True)   # suit la largeur de la barre
        self.coll_tree.tag_configure("dim", foreground=NC_DIM)
        self.coll_tree.pack(fill="both", expand=True, padx=2)
        self.coll_tree.bind("<<TreeviewSelect>>", self._on_coll_side)
        self.coll_tree.bind("<Button-3>", self._coll_side_menu)
        Tooltip(self.coll_tree, "Clic = afficher seulement cette collection.\n"
                                "Pour ranger : clic droit sur une archive → 📂 Déplacer vers la collection…\n"
                                "(Ctrl+clic / Maj+clic pour en choisir plusieurs)")
        b = self._btn(side, "✨ Ranger tout\nautomatiquement", self.auto_classify, hi=True, font=FONT_SM,
                      justify="center")
        b.pack(fill="x", padx=2, pady=(4, 2))
        Tooltip(b, "Propose une collection pour chaque archive NON classée (même série, santé, musique…).\n"
                   "Tu vois la liste avant, et tu peux tout annuler après.")
        b = self._btn(side, "➕ Nouvelle", self.new_collection)
        b.pack(fill="x", padx=2, pady=(0, 2))
        Tooltip(b, "Créer une collection (les archives sélectionnées y sont ajoutées)")
        self.undo_btn = self._btn(side, "↩ Annuler le rangement", self.undo_auto_classify)
        Tooltip(self.undo_btn, "Remet les archives rangées automatiquement dans « Non classées »")
        self._undo_anchor = tk.Frame(side, bg=NC_PANEL, height=4)
        self._undo_anchor.pack(fill="x")
        left = main
        head = tk.Frame(left, bg=NC_BG)
        head.pack(fill="x", pady=(2, 2))
        self._side_toggle = self._btn(head, "◀", self._toggle_coll_side)
        self._side_toggle.pack(side="left", padx=(0, 4))
        Tooltip(self._side_toggle, "Cacher / afficher la barre des collections")
        tk.Label(head, text="🗂 Historique", bg=NC_BG, fg=NC_HI, font=FONT_UI).pack(side="left")
        self.count_var = tk.StringVar(value="0 archive")
        tk.Label(head, textvariable=self.count_var, bg=NC_BG, fg=NC_FG, font=FONT_SM).pack(side="right", padx=4)
        srow = tk.Frame(left, bg=NC_BG)
        srow.pack(fill="x")
        tk.Label(srow, text="🔎", bg=NC_BG, fg=NC_FG, font=FONT_UI).pack(side="left")
        self.search_var = tk.StringVar()
        self.search_entry = tk.Entry(srow, textvariable=self.search_var, bg=NC_ENTRY_BG, fg=NC_ENTRY_FG,
                                     insertbackground=NC_FG, font=FONT_UI)
        self.search_entry.pack(side="left", fill="x", expand=True, padx=4)
        _x = self._btn(srow, "✖", lambda: self.search_var.set(""))
        _x.pack(side="left")
        Tooltip(_x, "Effacer la recherche")
        self.search_var.trace_add("write", lambda *_: self._schedule_filter())
        Tooltip(self.search_entry, "Cherche dans titre, texte, auteur, tags et notes (Ctrl+F)")
        frow = FlowFrame(left)
        frow.pack(fill="x", pady=3)
        self.plat_var = tk.StringVar(value=PLAT_ALL_LABEL)
        self.plat_cb = ttk.Combobox(frow, textvariable=self.plat_var, values=[PLAT_ALL_LABEL], width=19,
                                    state="readonly", font=FONT_SM)
        self.plat_cb.bind("<<ComboboxSelected>>", lambda e: self.apply_filter())
        frow.add(self.plat_cb, "Filtrer l'historique par plateforme")
        self.coll_var = tk.StringVar(value=COLL_ALL_LABEL)
        self._coll_map: Dict[str, str] = {COLL_ALL_LABEL: ""}
        self.coll_cb = ttk.Combobox(frow, textvariable=self.coll_var, values=[COLL_ALL_LABEL], width=21,
                                    state="readonly", font=FONT_SM)
        self.coll_cb.bind("<<ComboboxSelected>>", lambda e: self._on_coll_filter())
        frow.add(self.coll_cb, "Collections : ★ favoris, 🗣 avec transcription, ⚠ originaux plus en ligne,\n"
                               "ou une de tes collections (clic droit sur une archive → 📚 Collections)")
        self.sort_var = tk.StringVar(value=LABEL_BY_SORT.get(self.cfg.get("sort"), SORT_CHOICES[0][1]))
        scb = ttk.Combobox(frow, textvariable=self.sort_var, values=[lab for _k, lab in SORT_CHOICES],
                           width=15, state="readonly", font=FONT_SM)
        scb.bind("<<ComboboxSelected>>", lambda e: (self._persist_opts(), self.apply_filter()))
        frow.add(scb, "Ordre de l'historique (clic sur un en-tête de colonne aussi)")

        tfr = tk.Frame(left, bg=NC_BG)
        self._hist_tfr = tfr
        self.tree = ttk.Treeview(tfr, style="Arch.Treeview", columns=("date", "plat", "titre", "taille"),
                                 show="tree headings", selectmode="extended")
        vsb = ttk.Scrollbar(tfr, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.heading("#0", text="")
        self.tree.column("#0", width=96, minwidth=96, stretch=False)
        for col, txt, w, st in (("date", "Archivé", 120, False), ("plat", "Plateforme", 110, False),
                                ("titre", "Titre", 200, True), ("taille", "Taille", 72, False)):
            self.tree.heading(col, text=txt, command=lambda c=col: self._sort_by_heading(c))
            self.tree.column(col, width=w, minwidth=50, stretch=st, anchor="e" if col == "taille" else "w")
        self.tree.bind("<Configure>", self._tree_columns, add="+")
        self.tree.bind("<<TreeviewSelect>>", self._on_select_history)
        self.tree.bind("<Double-Button-1>", lambda e: self.play_selected())
        self.tree.bind("<Button-3>", self._show_hist_menu)
        self.tree.bind("<Return>", lambda e: self.play_selected())
        self.tree.bind("<Delete>", lambda e: self.delete_selected())
        self.tree.bind("<Control-a>", self._tree_select_all)
        self.tree.bind("<Control-A>", self._tree_select_all)
        self.tree.bind("<Motion>", self._tree_hover, add="+")
        self.tree.bind("<space>", lambda e: (self.player_toggle(), "break")[1])

        self._hist_menu = self._menu()  # rempli à l'ouverture (selon la sélection)

        btns = FlowFrame(left)
        btns.pack(fill="x", pady=(2, 4), side="bottom")
        self._hist_btns = []
        tfr.pack(fill="both", expand=True, pady=2)
        for txt, cmd, tip, needs in (
            ("📁 Dossier", self.open_last_or_selected_folder, "Ouvrir le dossier de l'archive", False),
            ("🗑 Supprimer", self.delete_selected, "Supprimer l'archive — ou toutes celles sélectionnées (confirmation)", True),
            ("🔄", self.refresh_list, "Rafraîchir : relire le dossier des archives (F5)", False),
        ):
            b = btns.add(self._btn(btns, txt, cmd), tip)
            if needs:
                self._hist_btns.append(b)

    # ------------------------------------------------------------ aperçu
    def _build_preview(self, right):
        prev = tk.LabelFrame(right, text=" APERÇU ", bg=NC_BG, fg=NC_HI, font=FONT_UI, bd=2, relief="groove")
        prev.pack(fill="both", expand=True, padx=(6, 0))
        # en-tête fixe : titre éditable + barre d'actions
        name_row = tk.Frame(prev, bg=NC_BG)
        name_row.pack(fill="x", padx=6, pady=(4, 2))
        self.name_var = tk.StringVar()
        self.name_entry = tk.Entry(name_row, textvariable=self.name_var, bg=NC_ENTRY_BG, fg=NC_HI,
                                   insertbackground=NC_FG, font=FONT_BIG, relief="flat")
        _rb = self._btn(name_row, "✏ Renommer", self.rename_selected)
        _rb.pack(side="right", fill="y")
        self._act_btns_extra = [_rb]
        Tooltip(_rb, "Renommer l'archive (dossier + titre) avec le nom écrit à gauche — Entrée ou F2")
        self.name_entry.pack(side="left", fill="x", expand=True, padx=(0, 4), ipady=3)
        self.name_entry.bind("<Return>", lambda e: self.rename_selected())
        self.name_entry.bind("<F2>", lambda e: (self.rename_selected(), "break")[1])
        Tooltip(self.name_entry, "Nom de l'archive — modifie-le puis Entrée / F2 / ✏ Renommer")
        act = FlowFrame(prev)
        act.pack(fill="x", padx=6, pady=(0, 4))
        self._act_btns: Dict[str, Any] = {}
        for key, txt, cmd, hi, tip in (
            ("play", "▶ Lire", self.play_selected, True,
             "Lire ici, dans l'aperçu (lecteur intégré) — Ctrl+Espace = lecture/pause.\n"
             "Désactivable dans ⚙ Réglages : ▶ ouvre alors le lecteur externe."),
            ("ext", "↗ Externe", self.open_selected_media, False, "Ouvrir le média dans le lecteur externe (Windows, VLC ou mpv)"),
            ("online", "▶ Lecteur en ligne", self.embed_play, False,
             "Lecteur OFFICIEL de la plateforme (YouTube, Vimeo, TikTok, Spotify, SoundCloud, Twitch…) dans une\n"
             "petite fenêtre propre — Ctrl+L. Contenu protégé (Tubi, Netflix…) : ouvre le site officiel."),
            ("rec", "🎥 Enregistrer", self.record_screen, True,
             "Enregistrer l'écran (CaptureScreen) — Ctrl+Maj+E.\n"
             "Tout l'écran, une fenêtre ou une zone, avec le son, le micro, la webcam, le dessin à l'écran…\n"
             "Quand tu arrêtes, la vidéo est ajoutée toute seule à cette fiche (ou à une nouvelle)."),
            ("fav", "☆ Favori", self.toggle_favorite, False, "Ajouter aux favoris / retirer (Ctrl+D)"),
            ("coll", "📚 Collections ▾", lambda: self._post_menu(self._act_btns["coll"], self._build_coll_menu()), False,
             "Classer l'archive dans une ou plusieurs collections"),
            ("orig", "🌐 Original", self.open_original, False, "Ouvrir la page d'origine dans le navigateur"),
            ("page", "📄 Page", self.open_selected_index, False, "Page archive locale (index.html) dans le navigateur"),
            ("folder", "📁 Dossier", self.open_selected_folder, False, "Ouvrir le dossier de l'archive"),
            ("grim", "📚 Envoyer au Grimoire", self.send_to_grimoire, False,
             "Crée une fiche dans le Grimoire (choix du sujet) : titre, texte, image, lien et copie locale ✔ Permanent"),
            ("media", "✂ Outils média", self.open_media_tools, False,
             "Capture d'image, extrait vidéo, audio MP3, GIF animé (dossier extraits/)"),
            ("more", "⋯ Plus ▾", lambda: self._post_menu(self._act_btns["more"], self._build_more_menu()), False,
             "Copier le lien / le résumé, vérifier en ligne, exporter en ZIP, convertir en MP4, transcrire…"),
        ):
            self._act_btns[key] = act.add(self._btn(act, txt, cmd, hi=hi), tip)
        try:  # 🎥 Enregistrer bien visible (rouge « REC »), meme taille que les autres boutons
            self._act_btns["rec"].configure(bg="#D7263D", fg="#FFFFFF", activebackground="#FF4D6D",
                                            activeforeground="#FFFFFF")
        except Exception:
            pass
        self._act_flow = act

        # bandeau « Ranger dans X ? » (suggestion, rien n'est forcé)
        self.sug_banner = tk.Frame(prev, bg=NC_CARD, highlightbackground=NC_HI, highlightthickness=1)
        self.sug_msg = tk.Label(self.sug_banner, text="", bg=NC_CARD, fg=NC_TEXT, font=FONT_UI,
                                anchor="w", justify="left")
        self.sug_msg.pack(side="left", fill="x", expand=True, padx=8, pady=4)
        _sb = tk.Frame(self.sug_banner, bg=NC_CARD)
        _sb.pack(side="right", padx=4, pady=3)
        self._btn(_sb, "✔ Oui", self._sug_accept, hi=True, font=FONT_UI).pack(side="left", padx=2)
        self._sug_other = self._btn(_sb, "Autre…", lambda: self._post_menu(self._sug_other, self._build_move_menu()))
        self._sug_other.pack(side="left", padx=2)
        Tooltip(self._sug_other, "Choisir une autre collection (ou en créer une)")
        _no = self._btn(_sb, "✖", self._sug_dismiss)
        _no.pack(side="left", padx=2)
        Tooltip(_no, "Non merci : ne plus proposer pour cette archive")

        self.pscroll = ScrollFrame(prev)
        self.pscroll.pack(fill="both", expand=True, padx=2, pady=2)
        body = self.pscroll.inner

        # bandeau codec (vidéo non lisible par le lecteur Windows)
        self.codec_banner = tk.Frame(body, bg=NC_HI)
        self.codec_msg = tk.Label(self.codec_banner, text="", bg=NC_HI, fg=NC_ON_HI, font=FONT_SM,
                                  anchor="w", justify="left")
        self.codec_msg.pack(side="left", fill="x", expand=True, padx=6, pady=3)
        self._btn(self.codec_banner, "🎬 Convertir en MP4 compatible", self.convert_selected).pack(
            side="right", padx=4, pady=2)
        self._codec_anchor = tk.Frame(body, bg=NC_BG, height=0)
        self._codec_anchor.pack(fill="x")

        # grande miniature (sert aussi d'écran au lecteur intégré)
        self.thumb_label = tk.Label(body, bg=NC_IMG_BG, fg=NC_DIM, font=FONT_UI, cursor="hand2",
                                    text="Aucune archive sélectionnée.\nColle un lien pour commencer.",
                                    height=12)
        self.thumb_label.pack(fill="x", padx=8, pady=(6, 0))
        self.thumb_label.bind("<Button-1>", lambda e: self._on_thumb_click())
        self.thumb_label.bind("<Double-Button-1>", lambda e: self.player_bigwin())
        self._build_player_bar(body)
        self.thumb_hint = tk.Label(body, text="", bg=NC_BG, fg=NC_DIM, font=FONT_SM)
        self.thumb_hint.pack(fill="x", padx=8)
        # documents d'une page web archivée
        self._doc_anchor = tk.Frame(body, bg=NC_BG, height=0)
        self._doc_anchor.pack(fill="x")
        self.doc_box = tk.Frame(body, bg=NC_BG)
        self.doc_flow = FlowFrame(self.doc_box)
        self.doc_flow.pack(fill="x", padx=8, pady=(6, 0))

        # storyboard
        self._sb_anchor = tk.Frame(body, bg=NC_BG, height=0)
        self._sb_anchor.pack(fill="x")
        self.sb_title = self._section(body, "🎞 Storyboard")
        self.sb_row = tk.Frame(body, bg=NC_BG)
        self.sb_row.pack(fill="x", padx=8)
        self.sb_msg = tk.Label(body, text="", bg=NC_BG, fg=NC_DIM, font=FONT_SM, anchor="w")
        self.sb_msg.pack(fill="x", padx=8)

        # carte d'infos
        self._section(body, "ℹ Informations")
        self.card = tk.Frame(body, bg=NC_CARD, bd=1, relief="solid", highlightbackground=NC_FG)
        self.card.pack(fill="x", padx=8, pady=2)
        self.card.columnconfigure(1, weight=1)
        self._card_vals: Dict[str, tk.Label] = {}
        self._card_targets: Dict[str, Tuple[str, str]] = {}
        rows = [
            ("platform", "Plateforme"), ("author", "👤 Auteur"), ("published", "📅 Publié"),
            ("archived", "🗄 Archivé"), ("duration", "⏱ Durée"), ("size", "💾 Taille"),
            ("resolution", "🎞 Résolution"), ("method", "⚙ Méthode"), ("url", "🔗 Original"),
            ("folder", "📁 Dossier"), ("main", "▶ Média"), ("online", "📡 En ligne"),
            ("collections", "📚 Collections"),
        ]
        for i, (key, lab) in enumerate(rows):
            tk.Label(self.card, text=lab, bg=NC_CARD, fg=NC_FG, font=FONT_CARD_K, anchor="nw").grid(
                row=i, column=0, sticky="nw", padx=(8, 10), pady=2)
            v = tk.Label(self.card, text="—", bg=NC_CARD, fg=NC_TEXT, font=FONT_CARD_V,
                         anchor="w", justify="left")
            v.grid(row=i, column=1, sticky="w", padx=(0, 8), pady=2)
            v.bind("<Button-1>", lambda e, k=key: self._card_click(k))
            v.bind("<Button-3>", lambda e, k=key: self._card_menu(e, k))
            self._card_vals[key] = v

        # tags + notes
        self._section(body, "🏷 Tags et notes perso")
        trow = tk.Frame(body, bg=NC_BG)
        trow.pack(fill="x", padx=8)
        tk.Label(trow, text="Tags (virgules):", bg=NC_BG, fg=NC_FG, font=FONT_SM).pack(side="left")
        self.tags_var = tk.StringVar()
        self.tags_entry = tk.Entry(trow, textvariable=self.tags_var, bg=NC_ENTRY_BG, fg=NC_HI,
                                   insertbackground=NC_FG, font=FONT_UI)
        self.tags_entry.pack(side="left", fill="x", expand=True, padx=4)
        self.tags_entry.bind("<Return>", lambda e: self.save_tags_notes())
        self.tag_chips = tk.Frame(body, bg=NC_BG)
        self.tag_chips.pack(fill="x", padx=8, pady=(2, 0))
        tk.Label(body, text="Notes:", bg=NC_BG, fg=NC_FG, font=FONT_SM, anchor="w").pack(fill="x", padx=8)
        nfr, self.notes_text = self._scrolled_text(body, height=4, bg=NC_ENTRY_BG, fg=NC_ENTRY_FG,
                                                   font=FONT_TEXT)
        nfr.pack(fill="x", padx=8)
        srow = tk.Frame(body, bg=NC_BG)
        srow.pack(fill="x", padx=8, pady=3)
        self._btn(srow, "💾 Enregistrer tags/notes (Ctrl+S)", self.save_tags_notes, hi=True).pack(side="left")
        self.tn_state = tk.Label(srow, text="", bg=NC_BG, fg=NC_OK, font=FONT_SM)
        self.tn_state.pack(side="left", padx=8)

        # texte du post
        self.text_title = self._section(body, "📝 Texte du post")
        tfr, self.desc_text = self._scrolled_text(body, height=12, bg=NC_PANEL, fg=NC_TEXT, font=FONT_TEXT)
        tfr.pack(fill="x", padx=8)
        self.desc_text.configure(state="disabled", cursor="xterm", padx=8, pady=6, spacing1=1, spacing3=3)
        self.desc_text.tag_configure("link", foreground=NC_HI, underline=True)
        self.desc_text.tag_bind("link", "<Enter>", lambda e: self.desc_text.configure(cursor="hand2"))
        self.desc_text.tag_bind("link", "<Leave>", lambda e: self.desc_text.configure(cursor="xterm"))
        self.desc_text.bind("<Button-1>", lambda e: self.desc_text.focus_set())
        self.desc_text.bind("<Button-3>", self._desc_menu_popup)
        self._desc_menu = self._menu()
        self._desc_menu.add_command(label="Copier la sélection", command=self._desc_copy_sel)
        self._desc_menu.add_command(label="Copier tout le texte", command=self._desc_copy_all)
        self._desc_menu.add_command(label="Tout sélectionner", command=lambda: self.desc_text.tag_add("sel", "1.0", "end-1c"))

        # transcription (v5)
        self._tr_anchor = tk.Frame(body, bg=NC_BG, height=0)
        self._tr_anchor.pack(fill="x")
        self._build_transcript_box(body)
        # extraits et captures (v5)
        self._ex_anchor = tk.Frame(body, bg=NC_BG, height=0)
        self._ex_anchor.pack(fill="x")
        self._build_extracts_box(body)

        # galerie
        self.gal_title = self._section(body, "🖼 Galerie")
        self.gal_frame = tk.Frame(body, bg=NC_BG)
        self.gal_frame.pack(fill="x", padx=8)
        self._gal_paths: List[str] = []

        # fichiers
        self.files_title = self._section(body, "📂 Fichiers")
        ffr = tk.Frame(body, bg=NC_BG)
        ffr.pack(fill="x", padx=8, pady=(0, 12))
        self.files_tree = ttk.Treeview(ffr, style="Files.Treeview", columns=("kind", "size", "mod"),
                                       show="tree headings", height=8, selectmode="browse")
        fsb = ttk.Scrollbar(ffr, orient="vertical", command=self.files_tree.yview)
        self.files_tree.configure(yscrollcommand=fsb.set)
        fsb.pack(side="right", fill="y")
        self.files_tree.pack(side="left", fill="x", expand=True)
        self.files_tree.heading("#0", text="Nom")
        self.files_tree.column("#0", width=380, stretch=True)
        for col, txt, w in (("kind", "Type", 100), ("size", "Taille", 90), ("mod", "Modifié", 130)):
            self.files_tree.heading(col, text=txt)
            self.files_tree.column(col, width=w, stretch=False, anchor="e" if col == "size" else "w")
        self.files_tree.bind("<Double-Button-1>", lambda e: self.open_preview_file())
        self.files_tree.bind("<Return>", lambda e: self.open_preview_file())
        self.files_tree.bind("<Button-3>", self._files_menu_popup)
        self._files_menu = self._menu()
        self._files_menu.add_command(label="Ouvrir", command=self.open_preview_file)
        self._files_menu.add_command(label="Afficher dans le dossier", command=self.reveal_preview_file)
        self._files_menu.add_command(label="Copier le chemin", command=self.copy_preview_file_path)
        self._files_menu.add_command(label="Copier le nom", command=self.copy_preview_file_name)

        self.pscroll.canvas.bind("<Configure>", self._on_preview_resize, add="+")

    # ------------------------------------------------------------ bas: file + journal
    def _build_bottom(self, bottom):
        """Barre compacte (toujours visible) + panneau File/Journal repliable."""
        hdr = tk.Frame(bottom, bg=NC_PANEL)
        hdr.pack(fill="x")
        self.q_toggle = self._btn(hdr, "▲ ⏳ File d'attente", lambda: self._toggle_bottom("queue"))
        self.q_toggle.pack(side="left", padx=(2, 2), pady=2)
        Tooltip(self.q_toggle, "Afficher / replier la file d'attente (Échap = replier)")
        self.l_toggle = self._btn(hdr, "📜 Journal", lambda: self._toggle_bottom("log"))
        self.l_toggle.pack(side="left", padx=2, pady=2)
        Tooltip(self.l_toggle, "Afficher / replier le journal détaillé")
        self.cancel_btn = self._btn(hdr, "⛔ Annuler", self.cancel_current)
        self.cancel_btn.pack(side="right", padx=4, pady=2)
        Tooltip(self.cancel_btn, "Annuler l'archivage / la conversion en cours")
        self.prog = FunBar(hdr, width=170, height=16)
        self.prog.pack(side="left", padx=(10, 6), pady=4)
        self.prog_var = tk.StringVar(value="Aucun archivage en cours.")
        tk.Label(hdr, textvariable=self.prog_var, bg=NC_PANEL, fg=NC_FG, font=FONT_SM, anchor="w").pack(
            side="left", fill="x", expand=True)

        self.bottom_body = tk.Frame(bottom, bg=NC_BG, height=170)
        self.bottom_body.pack_propagate(False)
        # file d'attente
        self.qframe = tk.Frame(self.bottom_body, bg=NC_BG)
        side = tk.Frame(self.qframe, bg=NC_BG)
        side.pack(side="right", fill="y", padx=(6, 2), pady=2)
        self.q_retire = self._btn(side, "✖ Retirer", self.remove_selected_job)
        self.q_retire.pack(fill="x", pady=1)
        Tooltip(self.q_retire, "Retirer le lien sélectionné de la file (Suppr)")
        self.q_retry = self._btn(side, "🔁 Réessayer", self.retry_selected_job)
        self.q_retry.pack(fill="x", pady=1)
        Tooltip(self.q_retry, "Relancer un lien en échec ou annulé")
        self.q_clear = self._btn(side, "🧹 Nettoyer terminés", self.clear_done_jobs)
        self.q_clear.pack(fill="x", pady=1)
        Tooltip(self.q_clear, "Enlever de la liste les liens terminés / en échec / annulés")
        qfr = tk.Frame(self.qframe, bg=NC_BG)
        qfr.pack(side="left", fill="both", expand=True, pady=2)
        self.qtree = ttk.Treeview(qfr, style="Queue.Treeview", columns=("etat", "pct", "titre"),
                                  show="headings", height=4, selectmode="browse")
        qsb = ttk.Scrollbar(qfr, orient="vertical", command=self.qtree.yview)
        self.qtree.configure(yscrollcommand=qsb.set)
        qsb.pack(side="right", fill="y")
        self.qtree.pack(side="left", fill="both", expand=True)
        for col, txt, w, st in (("etat", "État", 110, False), ("pct", "%", 50, False), ("titre", "Lien / titre", 500, True)):
            self.qtree.heading(col, text=txt)
            self.qtree.column(col, width=w, stretch=st, anchor="e" if col == "pct" else "w")
        self.qtree.bind("<Double-Button-1>", self._on_job_double)
        self.qtree.bind("<Delete>", lambda e: self.remove_selected_job())
        self.qtree.bind("<<TreeviewSelect>>", lambda e: self._update_states(), add="+")
        self.q_empty = tk.Label(qfr, text="File vide — colle un lien pour commencer.", bg=NC_PANEL,
                                fg=NC_DIM, font=FONT_SM)
        # journal
        self.lframe = tk.Frame(self.bottom_body, bg=NC_BG)
        lfr, self.log_box = self._scrolled_text(self.lframe, height=6, font=FONT_SM)
        lfr.pack(fill="both", expand=True, pady=2)

    def _toggle_bottom(self, view: str):
        if self._bottom_open and self._bottom_view == view:
            self._collapse_bottom()
        else:
            self._show_bottom(view)

    def _show_bottom(self, view: str, auto: bool = False):
        self._bottom_auto = auto and not self._bottom_open
        self._bottom_view = view
        (self.qframe if view == "queue" else self.lframe).pack(fill="both", expand=True)
        (self.lframe if view == "queue" else self.qframe).pack_forget()
        h = max(120, min(230, int(self.winfo_height() * 0.24))) if self.winfo_height() > 100 else 160
        self.bottom_body.configure(height=h)
        if not self._bottom_open:
            self.bottom_body.pack(fill="x")
            self._bottom_open = True
        if view == "log":
            self.log_box.see("end")
        self._refresh_bottom_labels()

    def _collapse_bottom(self):
        if self._bottom_open:
            self.bottom_body.pack_forget()
            self._bottom_open = False
            self._bottom_auto = False
        self._refresh_bottom_labels()

    def _refresh_bottom_labels(self):
        pending = sum(1 for j in self.jobs if j["status"] == "attente")
        running = any(j["status"] == "cours" for j in self.jobs)
        n = pending + (1 if running else 0)
        q_open = self._bottom_open and self._bottom_view == "queue"
        l_open = self._bottom_open and self._bottom_view == "log"
        self.q_toggle.configure(text=("▼ " if q_open else "▲ ") + "⏳ File d'attente" + (f" ({n})" if n else ""),
                                bg=NC_SEL if q_open else NC_BTN, fg=NC_ON_SEL if q_open else NC_BTN_FG)
        self.l_toggle.configure(text=("▼ " if l_open else "▲ ") + "📜 Journal",
                                bg=NC_SEL if l_open else NC_BTN, fg=NC_ON_SEL if l_open else NC_BTN_FG)
        if self.jobs:
            self.q_empty.place_forget()
        else:
            self.q_empty.place(relx=0.5, rely=0.55, anchor="center")

    # ------------------------------------------------------------ colonnes historique adaptatives
    def _tree_columns(self, event=None):
        w = event.width if event is not None else self.tree.winfo_width()
        if w <= 1:
            return
        if w >= 640:
            disp = ("date", "plat", "titre", "taille")
        elif w >= 470:
            disp = ("date", "titre", "taille")
        else:
            disp = ("titre", "taille")
        if tuple(self.tree.cget("displaycolumns")) != disp and self.tree.cget("displaycolumns") != disp:
            self.tree.configure(displaycolumns=disp)
        fixed = 96 + 72 + (120 if "date" in disp else 0) + (110 if "plat" in disp else 0) + 4
        self.tree.column("titre", width=max(120, w - fixed))

    # ------------------------------------------------------------ états des boutons
    def _update_states(self):
        try:
            has = bool(self._preview_entry and self._preview_path and os.path.isdir(self._preview_path))
            main = find_main_media(self._preview_path) if has else None
            is_vid = bool(main and main.lower().endswith(VIDEO_EXTS))
            can_play = bool(main) or bool(has and list_images(self._preview_path))
            for key, b in self._act_btns.items():
                ok = has
                if key == "rec":
                    ok = True
                elif key == "play":
                    ok = can_play
                elif key == "ext":
                    ok = bool(main)
                elif key in ("orig", "copy", "online"):
                    ok = has and bool(self._entry_url())
                elif key == "conv":
                    ok = is_vid and bool(find_ffmpeg())
                elif key == "media":
                    ok = bool(main) and bool(find_ffmpeg())
                b.configure(state="normal" if ok else "disabled")
            self._update_fav_button()
            nsel = len(self.tree.selection())
            for b in getattr(self, "_hist_btns", []):
                b.configure(state="normal" if (has or nsel) else "disabled")
            running = any(j["status"] == "cours" for j in self.jobs)
            self.cancel_btn.configure(state="normal" if running else "disabled")
            j = self._selected_job()
            self.q_retire.configure(state="normal" if j else "disabled")
            self.q_retry.configure(state="normal" if j and j["status"] in ("echec", "annule") else "disabled")
            self.q_clear.configure(state="normal" if any(x["status"] in ("ok", "echec", "annule")
                                                        for x in self.jobs) else "disabled")
        except Exception:
            logger.exception("update_states")

    # ------------------------------------------------------------ molette
    def _on_wheel(self, event):
        try:
            w = self.winfo_containing(event.x_root, event.y_root)
        except Exception:
            w = None
        if w is None:
            return
        if getattr(event, "state", 0) & 0x4:  # Ctrl + molette = taille du texte
            up = getattr(event, "num", None) == 4 or int(getattr(event, "delta", 0) or 0) > 0
            self._font_step(1 if up else -1)
            return "break"
        if getattr(event, "num", None) == 4:
            step = -3
        elif getattr(event, "num", None) == 5:
            step = 3
        else:
            d = int(getattr(event, "delta", 0) or 0)
            if d == 0:
                return
            step = -max(1, abs(d) // 40) if d > 0 else max(1, abs(d) // 40)
        try:
            cls = w.winfo_class()
        except Exception:
            return
        if cls in ("Text", "Treeview", "Listbox", "TCombobox", "Canvas") and w is not self.pscroll.canvas:
            try:
                first, last = w.yview()
                can_scroll = not (first <= 0.0 and last >= 1.0)
            except Exception:
                can_scroll = True
            if can_scroll:
                return  # la classe du widget gère sa propre molette
        if self.pscroll.contains(w):
            self.pscroll.scroll_units(step)
            return "break"

    # ------------------------------------------------------------ démarrage
    def _post_init(self):
        try:
            os.makedirs(self.archive_root_path(), exist_ok=True)
        except Exception as e:
            self.log(f"Racine inaccessible: {e}")
        self.log(f"Archiveur v{APP_FILE_VER} — racine: {self.archive_root_path()}")
        ff = find_ffmpeg()
        self.log(f"ffmpeg: {ff if ff else 'non trouvé'}")
        if not self._smoke:
            ensure_ytdlp(self.log, ask_install=bool(self.cfg.get("ask_ytdlp_install", True)), parent=self)

        def _ff_job():
            ok = ensure_ffmpeg(self.log, ask_install=False, parent=None,
                               status_cb=lambda m: self.ui(lambda mm=m: self.status.set(mm[:140])))
            self.cfg["ask_ffmpeg_install"] = False
            save_cfg(self.cfg)
            if not ok:
                self.log("ffmpeg manquant après tentative d'installation.")

        if not ff and not self._smoke:
            threading.Thread(target=_ff_job, daemon=True).start()
        if not find_ffplay():
            self.log("ffplay introuvable : lecteur intégré sans le son (relance setup_padawan.bat).", "warning")
        self._setup_dnd()
        self.refresh_list()
        if self._visible:
            self.select_folder(self._visible[0].get("folder"))
        else:
            self.clear_preview()
        if self.clip_var.get():
            self._toggle_clip_watch()
        self._refresh_bottom_labels()
        self._update_states()
        if self._players:
            self.log("Lecteurs détectés : " + ", ".join(f"{PLAYER_LABELS[k]} ({v})" for k, v in self._players.items()))
        self.after(200, lambda: self.url_text.focus_set())
        if self._shot:
            if self._shot_action:
                self.after(1500, self._do_shot_action)
            self.after(5000 if self._shot_action else 3500, self._take_shot)
        elif self._smoke:
            self.after(400, self._smoke_run)

    def _take_shot(self):
        """Mode test : capture de la fenêtre (PIL ImageGrab) → --shot fichier.png puis ferme."""
        try:
            self.update()
            from PIL import ImageGrab  # type: ignore
            full = ImageGrab.grab()
            sc = full.width / float(self.winfo_screenwidth())
            x0, y0 = self.winfo_rootx(), self.winfo_rooty()
            x1, y1 = x0 + self.winfo_width(), y0 + self.winfo_height()
            img = full.crop((int(x0 * sc), int(y0 * sc), int(x1 * sc), int(y1 * sc)))
            img.save(self._shot)
            print(f"SHOT {self._shot} {img.width}x{img.height} win={self.winfo_width()}x{self.winfo_height()} "
                  f"scale={sc:.2f} errors={len(self._errors)}", flush=True)
            for er in self._errors:
                print("SHOT_ERROR", er, flush=True)
        except Exception as ex:
            print("SHOT_FAIL", ex, flush=True)
            self._errors.append(str(ex))
        self._smoke_code = 1 if self._errors else 0
        self.destroy()

    def log(self, msg: str, level: str = "info"):
        line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
        try:
            getattr(logger, level if level in ("info", "warning", "error") else "info")(msg)
        except Exception:
            pass

        def _ui():
            try:
                self.log_box.insert("end", line + "\n")
                if int(self.log_box.index("end-1c").split(".")[0]) > 3000:
                    self.log_box.delete("1.0", "500.0")
                self.log_box.see("end")
                self.status.set(msg[:160])
            except Exception:
                pass
        self.ui(_ui)
        try:
            print(line, flush=True)
        except Exception:
            try:
                print(line.encode("ascii", "replace").decode("ascii"), flush=True)
            except Exception:
                pass

    def _persist_opts(self):
        self.cfg["quality"] = QUALITY_BY_LABEL.get(self.quality_var.get(), "best")
        self.cfg["subtitles"] = bool(self.subs_var.get())
        self.cfg["storyboard"] = bool(self.sb_var.get())
        self.cfg["cookies_from_browser"] = bool(self.cookies_var.get())
        self.cfg["cookies_browser"] = self.browser_var.get() or "chrome"
        self.cfg["clipboard_watch"] = bool(self.clip_var.get())
        self.cfg["clipboard_auto"] = bool(self.clip_auto_var.get())
        self.cfg["notifications"] = bool(self.notif_var.get())
        self.cfg["sort"] = SORT_BY_LABEL.get(self.sort_var.get(), "date_desc")
        self.cfg["auto_convert"] = bool(self.conv_var.get())
        inv = {v: k for k, v in PLAYER_LABELS.items()}
        self.cfg["player"] = inv.get(self.player_var.get(), "windows")
        self.cfg["archive_root"] = self.root_var.get().strip() or DEFAULT_ROOT
        self.archive_root = self.cfg["archive_root"]
        save_cfg(self.cfg)

    def _job_opts(self) -> Dict[str, Any]:
        self._persist_opts()
        return {
            "root": self.archive_root_path(),
            "quality": self.cfg["quality"],
            "subtitles": self.cfg["subtitles"],
            "storyboard": self.cfg["storyboard"],
            "cookies": (self.cfg["cookies_browser"] if self.cfg["cookies_from_browser"] else None),
            "auto_convert": bool(self.cfg.get("auto_convert", True)),
            "web_capture": bool(self.cfg.get("web_capture", True)),
            "use_fx": bool(self.cfg.get("x_fxtwitter", True)),
        }

    def choose_root(self):
        d = filedialog.askdirectory(initialdir=self.archive_root, title="Racine des archives", parent=self)
        if d:
            self.root_var.set(os.path.normpath(d))
            self._persist_opts()
            self.refresh_list()

    def archive_root_path(self) -> str:
        return self.root_var.get().strip() or self.archive_root

    def open_root(self):
        path = self.archive_root_path()
        os.makedirs(path, exist_ok=True)
        self.open_path_safe(path, "dossier")

    def open_global_index(self):
        root = self.archive_root_path()
        path = os.path.join(root, INDEX_HTML)
        if not os.path.isfile(path):
            write_global_index_html(root, load_archive_index(root))
        self._open_url(path)

    def regenerate_index(self):
        root = self.archive_root_path()
        try:
            entries = sync_index_with_disk(root, self.log)
            n = 0
            for e in entries:
                fp = os.path.join(root, str(e.get("folder")))
                info = load_info(fp)
                if info:
                    write_local_index(fp, info)
                    fresh = entry_from_info(info, fp)
                    e["size"], e["thumb"] = fresh["size"], fresh["thumb"]
                    n += 1
            save_archive_index(root, entries)
            self.log(f"♻ Index régénéré ({n} archive(s), pages locales + index global).")
            self.refresh_list()
        except Exception as ex:
            logger.exception("regenerate_index")
            messagebox.showerror(APP_NAME, f"Régénération impossible:\n{friendly_error(ex)}", parent=self)

    # ------------------------------------------------------------ liste
    def refresh_list(self):
        root = self.archive_root_path()
        try:
            self.entries = sync_index_with_disk(root, self.log)
        except Exception as e:
            logger.exception("refresh_list")
            self.log(f"Lecture de l'index impossible: {friendly_error(e)}", "error")
            self.entries = load_archive_index(root)
        self._refresh_filter_values()
        self.apply_filter()
        if self._preview_entry:
            self._refresh_preview_meta()

    def _schedule_filter(self):
        if getattr(self, "_filter_job", None):
            try:
                self.after_cancel(self._filter_job)
            except Exception:
                pass
        self._filter_job = self.after(150, self.apply_filter)

    def _sort_by_heading(self, col):
        cur = SORT_BY_LABEL.get(self.sort_var.get(), "date_desc")
        base = {"date": "date", "titre": "name", "taille": "size", "plat": "name"}.get(col, "date")
        if cur.startswith(base):
            new = base + ("_asc" if cur.endswith("desc") else "_desc")
        else:
            new = base + ("_desc" if base in ("date", "size") else "_asc")
        self.sort_var.set(LABEL_BY_SORT[new])
        self._persist_opts()
        self.apply_filter()

    def _list_thumb(self, entry):
        if not HAS_PIL:
            return ""
        thumb = entry.get("thumb")
        if not thumb:
            return ""
        p = os.path.join(self.archive_root_path(), str(entry.get("folder")), str(thumb))
        try:
            key = (p, os.path.getmtime(p))
        except OSError:
            return ""
        if key in self._list_thumbs:
            return self._list_thumbs[key]
        try:
            im = Image.open(p)
            im.thumbnail((84, 47))
            bg = Image.new("RGB", (84, 47), NC_IMG_BG)
            bg.paste(im.convert("RGB"), ((84 - im.width) // 2, (47 - im.height) // 2))
            ph = ImageTk.PhotoImage(bg)
        except Exception:
            logger.exception("vignette %s", p)
            ph = ""
        self._list_thumbs[key] = ph
        return ph

    def apply_filter(self):
        self._filter_job = None
        plat = getattr(self, "_plat_map", {}).get(self.plat_var.get(), "")
        sort = SORT_BY_LABEL.get(self.sort_var.get(), "date_desc")
        coll = self._coll_key()
        self._visible = search_entries(self.entries, self.search_var.get(), plat, sort, collection=coll)
        keep = self._preview_entry.get("folder") if self._preview_entry else None
        keep_sel = {self._iid_entry[i].get("folder") for i in self.tree.selection() if i in self._iid_entry}
        if keep:
            keep_sel.add(keep)
        self.tree.delete(*self.tree.get_children())
        self._iid_entry = {}
        sel_iids = []
        focus_iid = None
        for i, e in enumerate(self._visible):
            iid = f"e{i}"
            self._iid_entry[iid] = e
            title = str(e.get("title") or e.get("folder") or "")
            pre = ""
            if e.get("favorite"):
                pre += "★ "
            st = e.get("online_status")
            if st in ("offline", "restricted"):
                pre += GUI_ONLINE[st][0] + " "
            title = pre + title
            cols = [c for c in (e.get("collections") or []) if c.lower() != str(coll or "").lower()]
            if cols:
                title += "   📚 " + ", ".join(cols[:2])
            if e.get("tags"):
                title += "   " + " ".join("#" + t for t in e.get("tags")[:4])
            self.tree.insert("", "end", iid=iid, image=self._list_thumb(e), values=(
                fmt_iso(e.get("archived_at")), platform_label(e.get("platform")), title, human_size(e.get("size"))))
            if e.get("folder") in keep_sel:
                sel_iids.append(iid)
            if keep and e.get("folder") == keep:
                focus_iid = iid
        n, tot = len(self._visible), len(self.entries)
        self.count_var.set(f"{n} / {tot} archive(s)" if n != tot else f"{tot} archive(s)")
        if sel_iids:
            self._suppress_select = True
            self.tree.selection_set(sel_iids)
            if focus_iid:
                self.tree.focus(focus_iid)
                self.tree.see(focus_iid)
            self.after(10, lambda: setattr(self, "_suppress_select", False))

    def select_folder(self, folder: Optional[str]) -> bool:
        if not folder:
            return False
        for iid, e in self._iid_entry.items():
            if e.get("folder") == folder:
                self.tree.selection_set(iid)
                self.tree.see(iid)
                self.show_preview(e)
                return True
        # pas visible (filtre) → effacer filtres
        if self.search_var.get() or self._plat_map.get(self.plat_var.get()) or self._coll_key():
            self.search_var.set("")
            self.plat_var.set(PLAT_ALL_LABEL)
            self.coll_var.set(COLL_ALL_LABEL)
            self.apply_filter()
            for iid, e in self._iid_entry.items():
                if e.get("folder") == folder:
                    self.tree.selection_set(iid)
                    self.tree.see(iid)
                    self.show_preview(e)
                    return True
        return False

    def _selected_entry(self) -> Optional[Dict[str, Any]]:
        sel = self.tree.selection()
        if sel and sel[0] in self._iid_entry:
            return self._iid_entry[sel[0]]
        return self._preview_entry

    def _folder_path(self, entry: Optional[Dict[str, Any]] = None) -> Optional[str]:
        e = entry or self._selected_entry()
        if e and e.get("folder"):
            return os.path.join(self.archive_root_path(), str(e.get("folder")))
        if self.last_folder:
            p = os.path.join(self.archive_root_path(), self.last_folder)
            if os.path.isdir(p):
                return p
        return None

    def _on_select_history(self, _evt=None):
        if getattr(self, "_suppress_select", False):
            return
        sel = self.tree.selection()
        if not sel:
            return
        foc = self.tree.focus()
        iid = foc if foc in sel else sel[0]
        if iid in self._iid_entry:
            e = self._iid_entry[iid]
            if not self._preview_entry or e.get("folder") != self._preview_entry.get("folder"):
                self.show_preview(e)
        if len(sel) > 1:
            self.status.set(f"{len(sel)} archives sélectionnées — clic droit pour les actions groupées "
                            "(favoris, collections, tags, ZIP, vérifier en ligne, supprimer).")
            self._update_states()

    # ------------------------------------------------------------ aperçu: rendu
    def clear_preview(self):
        try:
            self.player.stop()
        except Exception:
            pass
        self._player_media = ""
        self.pbar.pack_forget()
        self.doc_box.pack_forget()
        self.tr_box.pack_forget()
        self.ex_box.pack_forget()
        self._sb_show(False)
        self._preview_entry = None
        self._preview_info = {}
        self._preview_path = ""
        self._loaded_tn = ("", "")
        self.name_var.set("")
        self._thumb_src = self._thumb_base = None
        self._thumb_photo = None
        self.thumb_label.configure(image="", height=12,
                                   text="Aucune archive sélectionnée.\nColle un lien (📋 Coller et archiver) pour commencer.")
        self.thumb_hint.configure(text="")
        for w in self.sb_row.winfo_children():
            w.destroy()
        self.sb_msg.configure(text="")
        for k in self._card_vals:
            self._set_card(k, "—")
        self.tags_var.set("")
        self.notes_text.delete("1.0", "end")
        self._render_tag_chips([])
        self._set_desc("")
        for w in self.gal_frame.winfo_children():
            w.destroy()
        self.files_tree.delete(*self.files_tree.get_children())
        self.tn_state.configure(text="")
        self.codec_banner.pack_forget()
        self._hide_suggest_banner()
        self._update_states()

    def _tn_current(self) -> Tuple[str, str]:
        return (", ".join(parse_tags(self.tags_var.get())), self.notes_text.get("1.0", "end-1c").strip())

    def _autosave_tn(self):
        if self._preview_entry and self._preview_path and os.path.isdir(self._preview_path):
            if self._tn_current() != self._loaded_tn:
                try:
                    self.save_tags_notes(quiet=True)
                    self.log("Tags/notes enregistrés automatiquement.")
                except Exception:
                    logger.exception("autosave tags")

    def show_preview(self, entry: Dict[str, Any]):
        if self._preview_entry and entry.get("folder") != self._preview_entry.get("folder"):
            self._autosave_tn()
        try:
            if self.player.state != "stop":
                self.player.stop()
        except Exception:
            logger.exception("arrêt lecteur")
        self._preview_entry = entry
        folder = str(entry.get("folder") or "")
        path = os.path.join(self.archive_root_path(), folder) if folder else ""
        self._preview_path = path
        info: Dict[str, Any] = dict(entry)
        if path:
            info.update(load_info(path))
        self._preview_info = info
        self.name_var.set(str(info.get("title") or folder))
        self.pscroll.to_top()

        # carte
        plat = info.get("platform")
        self._set_card("platform", platform_label(plat))
        author = str(info.get("uploader") or info.get("creator") or info.get("channel") or "")
        aurl = str(info.get("uploader_url") or info.get("channel_url") or "")
        self._set_card("author", author or "—", ("url", aurl) if aurl and author else None)
        self._set_card("published", fmt_upload_date(info.get("upload_date") or info.get("date")))
        self._set_card("archived", fmt_iso(info.get("archived_at")))
        self._set_card("duration", human_duration(info.get("duration")))
        size = folder_size(path) if path and os.path.isdir(path) else 0
        self._set_card("size", human_size(size))
        res = str(info.get("resolution") or "")
        if not res:
            res = "—"
            mm = find_main_media(path) if path else None
            if mm and mm.lower().endswith(VIDEO_EXTS) and find_ffmpeg():
                res = "… (analyse)"
                self._probe_res_async(path, mm)
        self._set_card("resolution", res)
        meth = str(info.get("method") or "—")
        q = info.get("quality")
        if q:
            meth += f" · {LABEL_BY_QUALITY.get(q, q)}"
        self._set_card("method", meth)
        url = str(info.get("webpage_url") or info.get("url") or "")
        self._set_card("url", url or "—", ("url", url) if url else None)
        self._set_card("folder", path or "—", ("path", path) if path and os.path.isdir(path) else None)
        main = find_main_media(path) if path else None
        self._set_card("main", os.path.basename(main) if main else "(aucun média vidéo/audio)",
                       ("path", main) if main else None)
        self._set_card("online", self._online_text(info), ("action", "online"))
        self._set_card("collections", self._collections_text(info), ("action", "collections"))
        try:  # embeds : bouton « ▶ Lecteur en ligne » / contenu protégé
            self._embed_preview_update(info)
        except Exception:
            logger.exception("aperçu embed")
        try:  # 🔖 repères des enregistrements CaptureScreen
            self._cs_markers_update(info)
        except Exception:
            logger.exception("repères capture")

        # tags / notes
        tags = parse_tags(info.get("tags") or [])
        self.tags_var.set(", ".join(tags))
        self.notes_text.delete("1.0", "end")
        self.notes_text.insert("1.0", str(info.get("notes") or ""))
        self._loaded_tn = self._tn_current()
        self._render_tag_chips(tags, info.get("source_tags") or [])
        self.tn_state.configure(text="")

        # texte
        desc = str(info.get("description") or info.get("text") or "")
        self._set_desc(desc)
        self.text_title.configure(text=f"📝 Texte du post ({len(desc)} car.)" if desc else "📝 Texte du post")

        # miniature
        self._thumb_is_video = bool(main and main.lower().endswith(VIDEO_EXTS))
        thumb = find_thumbnail(path, info) if path else None
        self._load_main_image(thumb)
        if main and self._integrated_ok(main):
            self.thumb_hint.configure(text="Clic sur l'image = ▶ lecture / pause ici · double-clic = grande fenêtre")
        elif main:
            self.thumb_hint.configure(text=f"Clic sur l'image = ▶ lire le média ({PLAYER_LABELS.get(self._player())})")
        elif thumb:
            self.thumb_hint.configure(text="Clic sur l'image = ouvrir l'image")
        else:
            self.thumb_hint.configure(text="")

        self.codec_banner.pack_forget()
        if main and main.lower().endswith(VIDEO_EXTS) and find_ffmpeg():
            self._check_codec_async(path, main)
        self._setup_player(main, info)
        self._render_docs(path, info)
        self._sb_show(bool(main and main.lower().endswith(VIDEO_EXTS)) or bool(list_storyboard(path) if path else []))
        self._render_storyboard()
        self._render_transcript(path, main)
        self._render_extracts(path, main)
        self._render_gallery()
        self._render_files()
        self._update_suggest_banner()
        self._update_states()
        self.after_idle(self._render_thumb)

    def _probe_res_async(self, path: str, video: str):
        def _job():
            res = probe_resolution(video)
            if res:
                try:
                    info = load_info(path)
                    if info and not info.get("resolution"):
                        info["resolution"] = res
                        _write_json_atomic(os.path.join(path, "info.json"), info)
                except Exception:
                    logger.exception("save resolution")

            def _ui():
                if self._preview_path == path:
                    self._preview_info["resolution"] = res
                    self._set_card("resolution", res or "—")
            self.ui(_ui)
        threading.Thread(target=_job, daemon=True).start()

    def _set_card(self, key: str, text: str, target: Optional[Tuple[str, str]] = None):
        lab = self._card_vals[key]
        if target and target[1]:
            self._card_targets[key] = target
            fg = NC_HI
            if key == "online":
                fg = {"●": NC_OK, "✖": NC_ERR, "⚠": NC_WARN}.get(text[:1], NC_HI)
            lab.configure(text=text, fg=fg, cursor="hand2", font=FONT_CARD_VU)
        else:
            self._card_targets.pop(key, None)
            lab.configure(text=text, fg=NC_TEXT, cursor="", font=FONT_CARD_V)

    def _card_click(self, key: str):
        t = self._card_targets.get(key)
        if not t:
            return
        kind, target = t
        if kind == "action":
            if target == "online":
                self.check_online_selected(False)
            elif target == "collections":
                self._post_menu(self._card_vals["collections"], self._build_coll_menu())
            return
        if kind == "url":
            self._open_url(target)
        elif key == "main":
            self.play_selected()
        else:
            self.open_path_safe(target, "élément")

    def _card_menu(self, event, key: str):
        t = self._card_targets.get(key)
        if not t or t[0] == "action":
            return
        self._show_link_menu(event, t[0], t[1])

    def _show_link_menu(self, event, kind: str, target: str):
        self._link_target = (kind, target)
        self._link_menu.entryconfigure(0, label="🌐 Ouvrir le lien" if kind == "url" else "📂 Ouvrir")
        self._link_menu.entryconfigure(1, label="📋 Copier le lien" if kind == "url" else "📋 Copier le chemin")
        try:
            self._link_menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                self._link_menu.grab_release()
            except Exception:
                pass
        return "break"

    def _link_open(self):
        kind, target = self._link_target
        if kind == "url":
            self._open_url(target)
        elif target:
            self.open_path_safe(target, "élément")

    def _link_copy(self):
        self._copy_to_clipboard(self._link_target[1])

    def _copy_to_clipboard(self, text: str):
        if not text:
            return
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            self._clip_last = text  # la surveillance ne le reproposera pas
            self.status.set(f"📋 Copié : {text[:120]}")
        except Exception:
            logger.exception("clipboard")

    def _open_url(self, url: str):
        if not url:
            return
        if url.lower().startswith("www."):
            url = "https://" + url
        try:
            if os.path.exists(url) and sys.platform.startswith("win"):
                os.startfile(url)  # type: ignore[attr-defined]
            else:
                webbrowser.open(url)
            self.status.set(f"🌐 Ouverture : {url[:120]}")
        except Exception as e:
            logger.exception("open url")
            messagebox.showerror(APP_NAME, f"Impossible d'ouvrir le lien:\n{url}\n\n{e}", parent=self)

    def _render_tag_chips(self, tags: List[str], source_tags: Optional[List[str]] = None):
        for w in self.tag_chips.winfo_children():
            w.destroy()
        self.tag_chips.configure(height=1)
        for t in tags:
            lab = tk.Label(self.tag_chips, text=f"#{t}", bg=NC_HI, fg=NC_ON_HI, font=FONT_SM, padx=4, cursor="hand2")
            lab.pack(side="left", padx=(0, 4), pady=1)
            lab.bind("<Button-1>", lambda e, tt=t: self.search_var.set(tt))
        if source_tags:
            sug = [t for t in source_tags[:8] if t.lower() not in {x.lower() for x in tags}]
            if sug:
                tk.Label(self.tag_chips, text="  suggestions:", bg=NC_BG, fg=NC_DIM, font=FONT_SM).pack(side="left")
                for t in sug:
                    lab = tk.Label(self.tag_chips, text=f"+{t}", bg=NC_PANEL, fg=NC_FG, font=FONT_SM,
                                   padx=3, cursor="hand2")
                    lab.pack(side="left", padx=(2, 2))
                    lab.bind("<Button-1>", lambda e, tt=t: self._add_tag(tt))

    def _add_tag(self, tag: str):
        tags = parse_tags(self.tags_var.get()) + [tag]
        self.tags_var.set(", ".join(parse_tags(tags)))
        self.tn_state.configure(text="● modifié — Ctrl+S pour enregistrer", fg=NC_HI)

    def _set_desc(self, desc: str):
        t = self.desc_text
        t.configure(state="normal")
        t.delete("1.0", "end")
        for tag in t.tag_names():
            if tag.startswith("lk_"):
                t.tag_delete(tag)
        if not desc:
            t.insert("1.0", "(aucun texte pour ce post)")
        else:
            pos = 0
            for s, e, u in find_urls_spans(desc):
                t.insert("end", desc[pos:s])
                self._link_seq += 1
                tg = f"lk_{self._link_seq}"
                href = u if not u.lower().startswith("www.") else "https://" + u
                t.insert("end", u, ("link", tg))
                t.tag_bind(tg, "<Button-1>", lambda ev, h=href: (self._open_url(h), "break")[1])
                t.tag_bind(tg, "<Button-3>", lambda ev, h=href: self._show_link_menu(ev, "url", h))
                pos = e
            t.insert("end", desc[pos:])
        t.configure(state="disabled")
        lines = int(t.index("end-1c").split(".")[0])
        t.configure(height=max(4, min(18, lines + 1)))

    def _desc_menu_popup(self, event):
        if "link" in self.desc_text.tag_names(f"@{event.x},{event.y}"):
            return  # le menu du lien prend la main
        try:
            self._desc_menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                self._desc_menu.grab_release()
            except Exception:
                pass
        return "break"

    def _desc_copy_sel(self):
        try:
            self._copy_to_clipboard(self.desc_text.get("sel.first", "sel.last"))
        except tk.TclError:
            pass

    def _desc_copy_all(self):
        self._copy_to_clipboard(self.desc_text.get("1.0", "end-1c"))

    # ------------------------------------------------------------ images
    def _load_main_image(self, path: Optional[str]):
        self._thumb_base = None
        cands = [path] if path else []
        if self._preview_path:
            cands += list_images(self._preview_path) + list_storyboard(self._preview_path)
            cands += list_extracts(self._preview_path)
            adir = os.path.join(self._preview_path, "auteur")
            if os.path.isdir(adir):
                cands += [os.path.join(adir, n) for n in sorted(os.listdir(adir)) if n.lower().endswith(IMAGE_EXTS)]
        for cand in cands:
            if not cand or not HAS_PIL or not os.path.isfile(cand):
                continue
            try:
                im = Image.open(cand)
                im.load()
                self._thumb_base = im.convert("RGB")
                path = cand
                break
            except Exception:
                logger.warning("miniature illisible: %s", cand)
        self._thumb_src = self._thumb_base
        self._thumb_src_path = path
        self._shown_path = None

    def _preview_width(self) -> int:
        w = self.pscroll.canvas.winfo_width()
        return max(200, w - 20)

    def _render_thumb(self):
        if self.player.state in ("play", "pause"):
            return  # l'écran affiche la vidéo
        if self._thumb_src is None:
            self._thumb_photo = None
            if self._preview_entry:
                self.thumb_label.configure(image="", height=8, text="(pas de miniature)\n\nClic = ▶ lire / ouvrir le média")
            return
        avail_w, max_h = self._thumb_box()
        im = self._thumb_src
        scale = min(avail_w / im.width, max_h / im.height, 4.0)
        nw, nh = max(1, int(im.width * scale)), max(1, int(im.height * scale))
        try:
            res = im.resize((nw, nh), Image.LANCZOS).convert("RGBA")
            if self._thumb_is_video:
                ov = Image.new("RGBA", res.size, (0, 0, 0, 0))
                d = ImageDraw.Draw(ov)
                r = max(18, min(nw, nh) // 9)
                cx, cy = nw // 2, nh // 2
                d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(0, 0, 0, 150), outline=(255, 255, 85, 230), width=3)
                t = int(r * 0.55)
                d.polygon([(cx - t // 2, cy - t), (cx - t // 2, cy + t), (cx + t, cy)], fill=(255, 255, 85, 235))
                res = Image.alpha_composite(res, ov)
            self._thumb_photo = ImageTk.PhotoImage(res.convert("RGB"))
            self.thumb_label.configure(image=self._thumb_photo, text="", height=nh)
        except Exception:
            logger.exception("render thumb")

    def _on_preview_resize(self, _e=None):
        if self._resize_job:
            try:
                self.after_cancel(self._resize_job)
            except Exception:
                pass
        self._resize_job = self.after(120, self._do_resize)

    def _do_resize(self):
        self._resize_job = None
        w = self._preview_width()
        if getattr(self, "_last_pw", None) == (w, self.pscroll.canvas.winfo_height()):
            return
        self._last_pw = (w, self.pscroll.canvas.winfo_height())
        if self.player.state == "pause":
            mw, mh = self._thumb_box()
            self.player.show_still(mw, mh, self.player.pos)
        self._render_thumb()
        self._render_storyboard(reuse=True)
        self._layout_gallery()
        try:
            kf = tkfont.nametofont(FONT_CARD_K, root=self)
            keyw = max(kf.measure(t) for t in ("🎞 Résolution", "📚 Collections", "📡 En ligne")) + 40
        except Exception:
            keyw = 170
        for lab in self._card_vals.values():
            lab.configure(wraplength=max(200, w - keyw - 20))
        self.codec_msg.configure(wraplength=max(200, w - 300))
        self.sug_msg.configure(wraplength=max(200, w - 260))
        self.tr_msg.configure(wraplength=max(200, w - 20))
        self.ex_msg.configure(wraplength=max(200, w - 20))
        self.pl_note.configure(wraplength=max(200, w - 30))

    def _render_storyboard(self, reuse: bool = False):
        for w in self.sb_row.winfo_children():
            w.destroy()
        self.sb_row.configure(height=1)  # Tk: un cadre vidé garde sa taille sinon
        self._sb_photos = []
        path = self._preview_path
        if not path or not os.path.isdir(path):
            self.sb_msg.configure(text="")
            return
        frames = list_storyboard(path)
        main = find_main_media(path)
        is_video = bool(main and main.lower().endswith(VIDEO_EXTS))
        if not frames:
            if not is_video:
                self.sb_msg.configure(text="(pas de vidéo dans cette archive)")
            elif not find_ffmpeg():
                self.sb_msg.configure(text="(ffmpeg requis pour le storyboard)")
            elif path in self._sb_busy:
                self.sb_msg.configure(text="⏳ Storyboard en préparation… (quelques secondes)")
            elif path in self._sb_failed:
                self.sb_msg.configure(text="(storyboard impossible pour cette vidéo — clic droit : 🎞 Refaire le storyboard)")
            elif self._folder_converting(path):
                self.sb_msg.configure(text="⏳ Storyboard après la conversion en cours…")
            else:
                self._start_storyboard(path)
            return
        dur = None
        try:
            dur = float(self._preview_info.get("duration") or 0) or None
        except (TypeError, ValueError):
            dur = None
        times = storyboard_times(path, frames, dur)
        can_seek = bool(main) and self._integrated_ok(main)
        if can_seek:
            self.sb_msg.configure(text="👆 Clique sur une image pour sauter à ce moment de la vidéo")
        else:
            self.sb_msg.configure(text="Clic = agrandir l'image · double-clic = ▶ lire la vidéo")
        if not HAS_PIL:
            return
        items = [(fmt_ts(times[i]) if i < len(times) else f"{i + 1}", p, times[i] if i < len(times) else 0.0)
                 for i, p in enumerate(frames)]
        avail = self._preview_width() - 8
        n_items = max(1, len(items))
        tile_w = max(96, min(200, avail // n_items - 10))
        cols = max(1, min(n_items, avail // (tile_w + 10)))
        if cols < n_items:  # répartir sur des rangées égales
            rows = -(-n_items // cols)
            cols = -(-n_items // rows)
            tile_w = max(90, min(200, avail // cols - 10))
        for idx, (lab_txt, p, t) in enumerate(items):
            try:
                key = (p, os.path.getmtime(p), tile_w)
                ph = self._sb_imcache.get(key)
                if ph is None:
                    im = Image.open(p)
                    im.thumbnail((tile_w, int(tile_w * 0.75)))
                    ph = ImageTk.PhotoImage(im.convert("RGB"))
                    if len(self._sb_imcache) > 400:
                        self._sb_imcache.clear()
                    self._sb_imcache[key] = ph
            except Exception:
                continue
            self._sb_photos.append(ph)
            cell = tk.Frame(self.sb_row, bg=NC_BG)
            cell.grid(row=idx // cols, column=idx % cols, padx=3, pady=2, sticky="n")
            lb = tk.Label(cell, image=ph, bg=NC_HI if p == self._thumb_src_path_shown() else NC_BG,
                          bd=0, padx=2, pady=2, cursor="hand2")
            lb.pack()
            tk.Label(cell, text=lab_txt, bg=NC_BG, fg=NC_DIM, font=FONT_SM).pack()
            if can_seek:
                lb.bind("<Button-1>", lambda e, tt=t: self._sb_jump(tt))
                Tooltip(lb, f"▶ Lire à partir de {lab_txt}")
            else:
                lb.bind("<Button-1>", lambda e, pp=p: self._show_big(pp))
                lb.bind("<Double-Button-1>", lambda e: self.open_selected_media())

    def _sb_jump(self, t: float):
        """Clic sur une image du storyboard : la vidéo part à ce moment-là."""
        try:
            self.player_seek_to(max(0.0, float(t)), play=True)
            self.status.set(f"▶ Lecture à {fmt_ts(t)}")
        except Exception:
            logger.exception("storyboard jump")

    def _folder_converting(self, path: str) -> bool:
        folder = os.path.basename(path)
        return any(j.get("kind") == "convert" and j.get("folder") == folder and j.get("status") in ("cours", "attente")
                   for j in self.jobs)

    def _thumb_src_path_shown(self):
        return getattr(self, "_shown_path", None) or getattr(self, "_thumb_src_path", None)

    def _show_big(self, p: str):
        if self.player.state != "stop":
            self.player_stop()
        try:
            im = Image.open(p)
            im.load()
            self._thumb_src = im.convert("RGB")
            self._shown_path = p
            self._render_thumb()
            self._render_storyboard(reuse=True)
        except Exception:
            logger.exception("show big")

    def _start_storyboard(self, path: str, force: bool = False):
        """Storyboard en arrière-plan (fil séparé, ffmpeg en priorité basse, un à la fois) : l'interface reste libre."""
        if path in self._sb_busy:
            return
        self._sb_busy.add(path)
        self._sb_failed.discard(path)
        if self._preview_path == path:
            self.sb_msg.configure(text="⏳ Storyboard en préparation… (quelques secondes)")
        dur = self._preview_info.get("duration") if self._preview_path == path else None
        if not dur:
            try:
                dur = load_info(path).get("duration")
            except Exception:
                dur = None
        try:
            dur = float(dur) if dur else None
        except (TypeError, ValueError):
            dur = None

        def _prog(i, n):
            def _ui():
                if self._preview_path == path and path in self._sb_busy and not list_storyboard(path):
                    self.sb_msg.configure(text=f"⏳ Storyboard en préparation… {i}/{n}")
            self.ui(_ui)

        def _job():
            frames = []
            try:
                with _SB_LOCK:
                    frames = generate_storyboard(path, SB_FRAMES, duration=dur, force=force, progress=_prog)
            except Exception:
                logger.exception("storyboard")
            self._sb_busy.discard(path)
            if not frames:
                self._sb_failed.add(path)

            def _done():
                if self._preview_path == path:
                    self._render_storyboard()
                    self._render_files()
                if frames:
                    self.log(f"🎞 Storyboard prêt ({len(frames)} images) : {os.path.basename(path)}")
            self.ui(_done)
        threading.Thread(target=_job, daemon=True, name="storyboard").start()

    def regen_storyboard(self):
        path = self._folder_path()
        if not path or not os.path.isdir(path):
            return
        self._sb_failed.discard(path)
        if not find_ffmpeg():
            messagebox.showinfo(APP_NAME, "ffmpeg est requis pour le storyboard.", parent=self)
            return
        self._start_storyboard(path, force=True)

    def _render_gallery(self):
        self._gal_paths = list_images(self._preview_path) if self._preview_path else []
        self._gal_more = 0
        if self._preview_path:
            page_imgs = [p for p in list_page_images(self._preview_path) if p not in self._gal_paths]
            self._gal_more = max(0, len(page_imgs) - 24)
            self._gal_paths += page_imgs[:24]
        self._gal_photos = []
        self._gal_cells = []
        for w in self.gal_frame.winfo_children():
            w.destroy()
        self.gal_frame.configure(height=1)
        n = len(self._gal_paths)
        more = getattr(self, "_gal_more", 0)
        self.gal_title.configure(text=f"🖼 Galerie ({n + more} image{'s' if n + more > 1 else ''})"
                                      + (f" — {n} affichées" if more else "") + " — clic = ouvrir")
        if not n:
            tk.Label(self.gal_frame, text="(aucune image)", bg=NC_BG, fg=NC_DIM, font=FONT_SM).grid(row=0, column=0)
            return
        if not HAS_PIL:
            return
        for p in self._gal_paths:
            try:
                im = Image.open(p)
                im.thumbnail((180, 135))
                ph = ImageTk.PhotoImage(im.convert("RGB"))
            except Exception:
                continue
            self._gal_photos.append(ph)
            cell = tk.Frame(self.gal_frame, bg=NC_PANEL, bd=1, relief="solid")
            lb = tk.Label(cell, image=ph, bg=NC_PANEL, cursor="hand2")
            lb.pack(padx=3, pady=3)
            name = os.path.basename(p)
            tk.Label(cell, text=wrap_name(name, 24), bg=NC_PANEL, fg=NC_FG, font=FONT_SM, justify="center").pack()
            for wdg in (lb, cell):
                wdg.bind("<Button-1>", lambda e, pp=p: self.open_path_safe(pp, "image"))
                wdg.bind("<Button-3>", lambda e, pp=p: self._show_link_menu(e, "path", pp))
            self._gal_cells.append(cell)
        self._layout_gallery()
