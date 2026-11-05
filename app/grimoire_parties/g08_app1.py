# -*- coding: utf-8 -*-
# Partie de grimoire1.py (découpage v1.2.2, comportement inchangé).
# Chargée par grimoire1.py dans un espace de noms commun : ne pas lancer seule.
from __future__ import annotations



class _GrimoireAppPartie1:
    """Méthodes de GrimoireApp (partie 1/3)."""

    def __init__(self, args):
        super().__init__()
        global TK9
        self.withdraw()
        self.args = args
        self.title(APP_TITLE)
        try:
            TK9 = str(self.tk.call("info", "patchlevel")).startswith("9")
        except Exception:
            TK9 = False
        self.q: "queue.Queue[Callable]" = queue.Queue()
        self.jobs: "queue.Queue[Tuple[Callable, Optional[Callable], str]]" = queue.Queue()
        self.njobs = 0
        self.store = Store().open()
        try:
            seed_content(self.store, demo=bool(getattr(args, "demo", False)))
        except Exception:
            logger.error("contenu de départ : %s", traceback.format_exc())
        st = self.store
        C.clear()
        C.update(THEMES.get(st.get("theme", "norton"), THEMES["norton"]))
        init_fonts(self, st.get("font_delta", 0))
        if not st.get("gx_cards_default"):      # 1.5 : la vue Cartes devient la vue par defaut (une seule fois)
            st.set("view_mode", "cards")
            st.set("gx_cards_default", True)
        self.view_mode = st.get("view_mode", "cards")
        self._mindmap = None
        self.sort = st.get("sort", "manual")
        self.cur_view = st.get("last_view", "")
        if not self._view_valid(self.cur_view):
            self.cur_view = f"s:{st.find_subject('Bienvenue')}" if st.find_subject("Bienvenue") else "v:all"
        self.view_before_search = self.cur_view
        self.visible: List[Dict[str, Any]] = []
        self.selected: List[int] = []
        self.anchor: Optional[int] = None
        self.cur_item: Optional[int] = None
        self.undo_stack: List[Tuple[str, Callable[[], None]]] = []
        self.player = AudioPlayer()
        self.player_item: Optional[int] = None
        self.img_cache: Dict[Tuple[str, int, int], Any] = {}
        self.swatches: Dict[str, Any] = {}
        self.card_boxes: List[Tuple[int, int, int, int, int]] = []
        self.drag: Optional[Dict[str, Any]] = None
        self.press: Optional[Dict[str, Any]] = None
        self.search_job = None
        self.detail_job = None
        self.save_job = None
        self.results: List[Dict[str, Any]] = []
        self.terms: List[str] = []
        self.readonly_test = bool(getattr(args, "smoke", False) or getattr(args, "shot", ""))
        self.v_anim = tk.BooleanVar(master=self, value=bool(st.get("animations", True)))
        self._build()
        try:
            ico = os.path.join(BASE, "grimoire1.ico")
            if os.path.isfile(ico):
                self.iconbitmap(default=ico)
        except tk.TclError:
            pass
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.deiconify()
        if getattr(args, "geometry", ""):
            self.geometry(args.geometry)
        else:
            try:
                self.state("zoomed")
            except tk.TclError:
                self.geometry(f"{self.winfo_screenwidth()}x{self.winfo_screenheight() - 60}+0+0")
        for _ in range(2):
            threading.Thread(target=self._worker, daemon=True).start()
        self.after(60, self._poll)
        self.after(120, lambda: self.refresh_all(first=True))
        self.after(250, self._tick_player)
        if not self.readonly_test:
            self.after(150, self._ensure_shown)
            self.after(900, self._ensure_shown)
            self.after(1500, self._poll_inbox)
            self.run_job(lambda: self.store.backup(), None, "")
        logger.info("Grimoire démarré : %d sujets, %s fiches", len(st.subjects()), st.stats()["items"])

    # ------------------------------------------------------------ outils
    def _ensure_shown(self):
        if not IS_WIN:
            return
        try:
            u32 = ctypes.windll.user32
            hwnd = int(self.wm_frame(), 16)
            if not u32.IsWindowVisible(hwnd):
                u32.ShowWindow(hwnd, 3 if self.state() == "zoomed" else 5)
            self.lift()
        except Exception:
            pass

    def post(self, fn: Callable) -> None:
        self.q.put(fn)

    def _poll(self):
        try:
            for _ in range(100):
                fn = self.q.get_nowait()
                try:
                    fn()
                except Exception:
                    logger.error("tâche UI : %s", traceback.format_exc())
        except queue.Empty:
            pass
        self.after(70, self._poll)

    def _worker(self):
        while True:
            fn, done, label = self.jobs.get()
            res = None
            try:
                res = fn()
            except Exception:
                logger.error("tâche %s : %s", label, traceback.format_exc())
            self.njobs = max(0, self.njobs - 1)
            if done:
                self.post(lambda d=done, r=res: d(r))
            self.post(self._update_jobs)

    def run_job(self, fn: Callable, done: Optional[Callable] = None, label: str = "") -> None:
        self.njobs += 1
        self.jobs.put((fn, done, label))
        self._update_jobs(label)

    def _update_jobs(self, label: str = ""):
        try:
            self.l_jobs.configure(text=(f"⏳ {label or 'travail en cours'}… ({self.njobs})" if self.njobs else ""))
        except Exception:
            pass

    def set_status(self, msg: str, key: str = "FG") -> None:
        try:
            self.l_status.configure(text=msg, fg=C.get(key, C["FG"]))
        except Exception:
            pass

    def _view_valid(self, v: str) -> bool:
        if not v:
            return False
        if v.startswith("s:"):
            return bool(self.store.subject(v[2:]))
        if v.startswith("t:"):
            return True
        return v in [k for k, _i, _l in SPECIAL_VIEWS]

    def subject_order(self) -> List[int]:
        out: List[int] = []

        def walk(pid):
            for s in self.store.children(pid):
                out.append(s["id"])
                walk(s["id"])
        walk(None)
        return out

    def swatch(self, color: str):
        k = color or "none"
        if k not in self.swatches:
            self.swatches[k] = color_swatch(self, color or C["DIM"], 12)
        return self.swatches[k]

    def photo(self, rel_or_abs: str, w: int, h: int):
        """Vignette PhotoImage (cache) ; None si absente."""
        p = Paths.abs(rel_or_abs) if rel_or_abs else ""
        if not p or not os.path.isfile(p):
            return None
        key = (p, w, h)
        if key in self.img_cache:
            return self.img_cache[key]
        img = None
        try:
            from PIL import Image, ImageTk  # type: ignore
            with Image.open(p) as im:
                im = im.convert("RGBA") if im.mode not in ("RGB", "RGBA") else im.copy()
            im.thumbnail((w, h), Image.Resampling.LANCZOS)
            img = ImageTk.PhotoImage(im, master=self)
        except Exception:
            try:
                img = tk.PhotoImage(file=p, master=self)
            except Exception:
                img = None
        if len(self.img_cache) > 400:
            self.img_cache.clear()
        self.img_cache[key] = img
        return img

    def fit_text(self, text: str, font_name: str, width: int, lines: int = 1) -> str:
        f = fnt(font_name)
        meas = f.measure if hasattr(f, "measure") else (lambda s: len(s) * 8)
        words = (text or "").replace("\n", " ").split(" ")
        out: List[str] = []
        cur = ""
        i = 0
        while i < len(words):
            w = words[i]
            cand = (cur + " " + w).strip()
            if meas(cand) <= width:
                cur = cand
                i += 1
                continue
            if not cur:
                cut = len(w)
                while cut > 1 and meas(w[:cut]) > width:
                    cut -= 1
                cur, words[i] = w[:cut], w[cut:]
            out.append(cur)
            cur = ""
            if len(out) == lines:
                break
        if len(out) < lines and cur:
            out.append(cur)
            cur = ""
        rest = " ".join(words[i:]).strip() if len(out) == lines else ""
        if (rest or cur) and out:
            last = out[-1]
            while last and meas(last + "…") > width:
                last = last[:-1]
            out[-1] = last.rstrip() + "…"
        return "\n".join(out)

    # ------------------------------------------------------------ construction
    def _build(self):
        apply_styles(self)
        self.configure(bg=C["BG"])
        self.img_cache.clear()
        self.swatches.clear()
        self._build_menu()
        self._build_toolbar()
        sb = tk.Frame(self, bg=C["PANEL"])
        sb.pack(side="bottom", fill="x")
        self.l_count = tk.Label(sb, text="", bg=C["PANEL"], fg=C["DIM"], font=fnt("GSM"), anchor="e")
        self.l_count.pack(side="right", padx=8)
        self.l_jobs = tk.Label(sb, text="", bg=C["PANEL"], fg=C["WARN"], font=fnt("GSM"), anchor="e")
        self.l_jobs.pack(side="right", padx=8)
        self.l_status = tk.Label(sb, text="Prêt.", bg=C["PANEL"], fg=C["FG"], font=fnt("GSM"), anchor="w", width=1)
        self.l_status.pack(side="left", fill="x", expand=True, padx=8, pady=3)
        Tooltip(self.l_status, lambda: self.l_status.cget("text"))
        self.pw = tk.PanedWindow(self, orient="horizontal", bg=C["LINE"], sashwidth=5, bd=0, sashrelief="flat",
                                 opaqueresize=True)
        self.pw.pack(fill="both", expand=True)
        self._build_left()
        self._build_center()
        self._build_right()
        sw = self.winfo_screenwidth()
        g = getattr(self.args, "geometry", "")
        if g and re.match(r"^\d+x", g):
            sw = int(g.split("x")[0])
        elif self.winfo_width() > 400:
            sw = self.winfo_width()
        st = self.store
        saved = not g and st.get("panes_v") == PANES_V
        left_w = int((saved and st.get("left_w")) or (200 if sw <= 1100 else 245))
        right_w = int((saved and st.get("right_w")) or int(sw * (0.35 if sw <= 1100 else 0.36)))
        left_w = max(170, min(int(sw * (0.32 if sw <= 1100 else 0.30)), max(left_w, self._left_needed())))
        right_w = max(340, min(int(sw * 0.55), right_w))
        self.pw.add(self.f_left, minsize=170, width=left_w, stretch="never")
        self.pw.add(self.f_center, minsize=280, stretch="always")
        self.pw.add(self.f_right, minsize=320, width=right_w, stretch="never")
        self._bind_keys()
        self._setup_dnd()

    def _left_needed(self) -> int:
        try:
            f = fnt("GUI")
            if isinstance(f, str):
                f = tkfont.nametofont(f)
            names = [f" {ic}  {lab}" for _k, ic, lab in SPECIAL_VIEWS]
            for sid in self.subject_order():
                s = self.store.subject(sid)
                depth = len(self.store.subject_path(sid).split(" › ")) - 1
                names.append((depth, f"{s['icon'] or '📁'} {s['name']}"))
            need = 0
            for d in names:
                if isinstance(d, tuple):
                    need = max(need, d[0] * 20 + 20 + 16 + f.measure(d[1]))
                else:
                    need = max(need, 20 + f.measure(d))
            return need + 38 + 18 + 14
        except Exception:
            return 240

    def _build_menu(self):
        mb = tk.Menu(self)
        style_menu(mb)
        m = new_menu(mb)
        m.add_command(label="📝 Nouvelle note", accelerator="Ctrl+N", command=self.new_note)
        m.add_command(label="📁 Nouveau sujet…", accelerator="Ctrl+Maj+N", command=lambda: self.new_subject(None))
        m.add_command(label="📂 Nouveau sous-sujet…", command=lambda: self.new_subject(self.current_sid(strict=True)))
        m.add_separator()
        m.add_command(label="📥 Importer un dossier…", command=lambda: self.import_folder_dialog(None))
        m.add_command(label="🌐 Exporter le sujet en HTML…", accelerator="Ctrl+Maj+E", command=lambda: self.export_dialog(None, False))
        m.add_command(label="📦 Exporter le sujet en ZIP…", command=lambda: self.export_dialog(None, True))
        m.add_command(label="🌐 Exporter la sélection en HTML…", command=self.export_selection)
        m.add_separator()
        m.add_command(label="💾 Sauvegarder maintenant (copie datée)", accelerator="Ctrl+S", command=self.backup_now)
        m.add_command(label="📁 Ouvrir le dossier du Grimoire", command=lambda: open_path(Paths.data))
        m.add_command(label="↩ Restaurer une sauvegarde…", command=self.restore_backup)
        m.add_separator()
        m.add_command(label="Quitter", accelerator="Alt+F4", command=self.on_close)
        mb.add_cascade(label="Fichier", menu=m)
        m = new_menu(mb)
        m.add_command(label="Annuler la dernière suppression / le dernier déplacement", accelerator="Ctrl+Z", command=self.do_undo)
        m.add_separator()
        m.add_command(label="Coller intelligent (lien, texte, image, fichiers)", accelerator="Ctrl+V", command=self.smart_paste)
        m.add_command(label="Coller comme note texte", accelerator="Ctrl+Maj+V", command=lambda: self.smart_paste(plain=True))
        m.add_separator()
        m.add_command(label="Renommer", accelerator="F2", command=self.rename_any)
        m.add_command(label="★ Favori oui/non", accelerator="Ctrl+D", command=self.toggle_fav)
        m.add_command(label="📌 Épingler oui/non", accelerator="Ctrl+P", command=self.toggle_pin)
        m.add_command(label="🏷 Étiquettes…", accelerator="Ctrl+T", command=self.edit_tags)
        m.add_command(label="📁 Déplacer vers…", accelerator="Ctrl+M", command=lambda: self.move_selected(False))
        m.add_command(label="⧉ Copier vers…", command=lambda: self.move_selected(True))
        m.add_command(label="Monter / descendre", accelerator="Alt+Haut / Alt+Bas", command=lambda: self.move_item_step(-1))
        m.add_separator()
        m.add_command(label="Tout sélectionner", accelerator="Ctrl+A", command=self.select_all)
        m.add_command(label="🗑 Supprimer (corbeille)", accelerator="Suppr", command=self.delete_selected)
        mb.add_cascade(label="Édition", menu=m)
        mb.add_cascade(label="Sujets", menu=self._subjects_menu(mb))
        self.menu_add = self._make_add_menu(mb)
        mb.add_cascade(label="Ajouter", menu=self.menu_add)
        m = new_menu(mb)
        self.v_view = tk.StringVar(value=self.view_mode)
        m.add_radiobutton(label="☰ Liste", accelerator="Ctrl+1", variable=self.v_view, value="list", command=self._view_from_var)
        m.add_radiobutton(label="▦ Cartes", accelerator="Ctrl+2", variable=self.v_view, value="cards", command=self._view_from_var)
        m.add_radiobutton(label="🕘 Chronologie", accelerator="Ctrl+3", variable=self.v_view, value="chrono", command=self._view_from_var)
        m.add_separator()
        m.add_command(label="🗺 Carte des sujets", accelerator="F8", command=self.open_mindmap)
        m.add_checkbutton(label="✨ Animations", variable=self.v_anim, command=self.toggle_animations)
        m.add_command(label="📖 Mode lecture", accelerator="F11", command=self.open_reader)
        m.add_command(label="🧭 Aller à un sujet ou une fiche…", accelerator="Ctrl+G", command=self.open_palette)
        m.add_command(label="🔍 Rechercher partout", accelerator="Ctrl+F", command=self.focus_search)
        m.add_separator()
        m.add_command(label="Texte plus grand", accelerator="Ctrl++", command=lambda: self.zoom(1))
        m.add_command(label="Texte plus petit", accelerator="Ctrl+-", command=lambda: self.zoom(-1))
        m.add_command(label="Taille normale", accelerator="Ctrl+0", command=lambda: self.zoom(0))
        th = new_menu(m)
        self.v_theme = tk.StringVar(value=self.store.get("theme", "norton"))
        for k, lab in THEME_LABELS.items():
            th.add_radiobutton(label=lab, variable=self.v_theme, value=k, command=self.change_theme)
        m.add_cascade(label="Thème", menu=th)
        m.add_command(label="Rafraîchir", accelerator="F5", command=self.refresh_all)
        mb.add_cascade(label="Affichage", menu=m)
        m = new_menu(mb)
        m.add_command(label="📊 Statistiques", command=self.show_stats)
        m.add_command(label="🔎 Vérifier le Grimoire (fichiers, index)", command=self.check_dialog)
        m.add_command(label="🔄 Reconstruire l'index de recherche", command=self.rebuild_index)
        m.add_separator()
        self.v_fetch = tk.BooleanVar(value=bool(self.store.get("auto_fetch", True)))
        m.add_checkbutton(label="Récupérer titre, description et miniature des liens", variable=self.v_fetch,
                          command=lambda: self.store.set("auto_fetch", self.v_fetch.get()))
        self.v_ocr = tk.BooleanVar(value=bool(self.store.get("auto_ocr", False)))
        m.add_checkbutton(label="Lire le texte des images ajoutées (OCR Windows, automatique)", variable=self.v_ocr,
                          command=lambda: self.store.set("auto_ocr", self.v_ocr.get()))
        self.v_atr = tk.BooleanVar(value=bool(self.store.get("auto_transcribe", True)))
        m.add_checkbutton(label="Transcrire les mémos vocaux (si faster-whisper est installé)", variable=self.v_atr,
                          command=lambda: self.store.set("auto_transcribe", self.v_atr.get()))
        wm = new_menu(m)
        self.v_wmodel = tk.StringVar(value=self.store.get("whisper_model", "small"))
        for k, lab in (("tiny", "tiny (très rapide)"), ("base", "base (rapide)"), ("small", "small (bon, défaut)"),
                       ("medium", "medium (précis, lent)")):
            wm.add_radiobutton(label=lab, variable=self.v_wmodel, value=k,
                               command=lambda: self.store.set("whisper_model", self.v_wmodel.get()))
        m.add_cascade(label="Modèle de transcription", menu=wm)
        m.add_command(label="⬇ Installer la transcription (faster-whisper)…", command=self.install_whisper)
        m.add_separator()
        m.add_command(label="📋 Gérer mes modèles de fiches…", command=self.manage_templates)
        m.add_command(label="📒 Voir le journal (grimoire.log)", command=self.show_log)
        mb.add_cascade(label="Outils", menu=m)
        m = new_menu(mb)
        m.add_command(label="Aide", accelerator="F1", command=self.show_help)
        m.add_command(label="Raccourcis clavier", command=lambda: self.show_help("raccourcis"))
        m.add_command(label="À propos du Grimoire", command=self.about)
        mb.add_cascade(label="Aide", menu=m)
        self.config(menu=mb)
        self.menubar = mb

    def _make_add_menu(self, parent):
        m = new_menu(parent)
        m.add_command(label="📝 Note", accelerator="Ctrl+N", command=self.new_note)
        tm = new_menu(m)
        for name, (ic, _md) in self.all_templates().items():
            tm.add_command(label=f"{ic} {name}", command=lambda n=name: self.new_note(template=n))
        tm.add_separator()
        tm.add_command(label="💾 Enregistrer la note ouverte comme modèle…", command=self.save_as_template)
        m.add_cascade(label="📋 Fiche à partir d'un modèle", menu=tm)
        m.add_command(label="🔗 Lien web…", accelerator="Ctrl+L", command=self.add_link_dialog)
        m.add_command(label="❝ Citation…", accelerator="Ctrl+Maj+Q", command=self.add_quote_dialog)
        m.add_command(label="🌐 Capturer une page web complète…", command=self.capture_page_dialog)
        m.add_separator()
        m.add_command(label="🖼 Image(s)…", accelerator="Ctrl+Maj+I", command=lambda: self.add_files_dialog("image"))
        m.add_command(label="📄 Document(s) (PDF, Word, texte…)…", command=lambda: self.add_files_dialog("document"))
        m.add_command(label="🔊 Son(s)…", command=lambda: self.add_files_dialog("audio"))
        m.add_command(label="🎬 Vidéo(s) locale(s)…", command=lambda: self.add_files_dialog("video"))
        m.add_command(label="📎 Fichier(s) quelconque(s)…", accelerator="Ctrl+O", command=lambda: self.add_files_dialog(None))
        m.add_command(label="🎙 Mémo vocal (micro)", accelerator="Ctrl+R", command=self.record_memo)
        m.add_separator()
        m.add_command(label="📋 Coller (Ctrl+V)", command=self.smart_paste)
        m.add_command(label="📂 Importer un dossier…", command=lambda: self.import_folder_dialog(None))
        return m

    def _build_toolbar(self):
        tb = tk.Frame(self, bg=C["PANEL"])
        tb.pack(side="top", fill="x")
        self.f_toolbar = tb
        sw = self.winfo_screenwidth() if not getattr(self.args, "geometry", "") else int(self.args.geometry.split("x")[0])
        small = sw <= 1100
        right = tk.Frame(tb, bg=C["PANEL"])
        right.pack(side="right", padx=6)
        mk_button(right, "?", self.show_help, tip="Aide (F1)").pack(side="right", padx=3, pady=6)
        mk_button(right, "📊", self.show_stats, tip="Statistiques du Grimoire").pack(side="right", padx=3, pady=6)
        mk_button(right, "🗺" if small else "🗺 Carte", self.open_mindmap, tip="Carte des sujets : tes sujets en graphe animé (F8)").pack(
            side="right", padx=3, pady=6)
        mk_button(right, "🧭", self.open_palette, tip="Aller à un sujet ou une fiche (Ctrl+G)").pack(side="right", padx=3, pady=6)
        mk_button(right, "📖" if small else "📖 Lecture", self.open_reader, tip="Mode lecture plein écran (F11)").pack(
            side="right", padx=3, pady=6)
        tk.Label(tb, text="📖 GRIMOIRE", bg=C["PANEL"], fg=C["HI"], font=fnt("GTitle")).pack(side="left", padx=(10, 10), pady=6)
        sbox = tk.Frame(tb, bg=C["ENTRY_BG"], highlightthickness=1, highlightbackground=C["LINE"], highlightcolor=C["HI"])
        sbox.pack(side="left", pady=6)
        tk.Label(sbox, text="🔍", bg=C["ENTRY_BG"], fg=C["FG"], font=fnt("GUI")).pack(side="left", padx=(6, 0))
        self.v_search = tk.StringVar()
        self.e_search = tk.Entry(sbox, textvariable=self.v_search, width=22 if small else 30, bg=C["ENTRY_BG"],
                                 fg=C["ENTRY_FG"], insertbackground=C["HI"], relief="flat", font=fnt("GUI"),
                                 highlightthickness=0, selectbackground=C["SEL"], selectforeground=C["ON_SEL"])
        self.e_search.pack(side="left", padx=4, pady=3)
        self.l_ph = tk.Label(sbox, text="Rechercher… (Ctrl+F)", bg=C["ENTRY_BG"], fg=C["DIM"], font=fnt("GUI"), cursor="xterm")
        self.l_ph.place(in_=self.e_search, x=2, rely=0.5, anchor="w")
        self.l_ph.bind("<Button-1>", lambda _e: self.e_search.focus_set())
        b = tk.Button(sbox, text="✕", command=self.clear_search, bg=C["ENTRY_BG"], fg=C["DIM"], relief="flat", bd=0,
                      activebackground=C["SEL"], font=fnt("GUI"), cursor="hand2")
        b.pack(side="left", padx=(0, 4))
        Tooltip(b, "Effacer la recherche (Échap)")
        self.v_search.trace_add("write", lambda *_a: self._search_changed())
        self.e_search.bind("<Return>", lambda _e: self._focus_items())
        self.e_search.bind("<Down>", lambda _e: self._focus_items())
        self.e_search.bind("<Escape>", lambda _e: self.clear_search())
        self.e_search.bind("<Control-KeyPress>", self._entry_ctrl)
        self.b_add = mk_button(tb, "＋ Ajouter ▾", self._add_popup, "accent",
                               tip="Note, modèle de fiche, lien, citation, image, document, son, mémo vocal, page web…")
        self.b_add.pack(side="left", padx=(10, 4), pady=6)
        mk_button(tb, "📋 Coller", self.smart_paste, tip="Coller un lien, du texte, une image ou des fichiers dans le sujet ouvert (Ctrl+V)").pack(
            side="left", padx=3, pady=6)
        mk_button(tb, "🎙 Mémo", self.record_memo, tip="Enregistrer un mémo vocal au micro (Ctrl+R)").pack(side="left", padx=3, pady=6)

    def _add_popup(self):
        b = self.b_add
        try:
            self.menu_add.tk_popup(b.winfo_rootx(), b.winfo_rooty() + b.winfo_height())
        finally:
            try:
                self.menu_add.grab_release()
            except Exception:
                pass

    def _build_left(self):
        f = tk.Frame(self.pw, bg=C["PANEL"])
        self.f_left = f
        h = tk.Frame(f, bg=C["PANEL"])
        h.pack(fill="x")
        tk.Label(h, text="SUJETS", bg=C["PANEL"], fg=C["HI"], font=fnt("GHead")).pack(side="left", padx=8, pady=(6, 4))
        b = tk.Button(h, text="＋", command=lambda: self.new_subject(None), bg=C["PANEL"], fg=C["HI"], relief="flat", bd=0,
                      activebackground=C["SEL"], font=fnt("GUIB"), cursor="hand2")
        b.pack(side="right", padx=6)
        Tooltip(b, "Nouveau sujet (Ctrl+Maj+N) · clic droit sur un sujet : sous-sujet, icône, couleur…")
        fr = tk.Frame(f, bg=C["PANEL"])
        fr.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(fr, style="Subj.Treeview", show="tree", columns=("n",), selectmode="browse")
        self.tree.column("#0", width=180, stretch=True)
        self.tree.column("n", width=38, anchor="e", stretch=False)
        vsb = ttk.Scrollbar(fr, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.tag_configure("special", foreground=C["HI"])
        self.tree.tag_configure("subj", foreground=C["TEXT"])
        self.tree.tag_configure("pinned", foreground=C["HI"])
        self.tree.tag_configure("tag", foreground=C["FG"])
        self.tree.tag_configure("sep", foreground=C["LINE"])
        self.tree.tag_configure("drop", background=C["HI"], foreground=C["ON_HI"])
        self.tree.bind("<<TreeviewSelect>>", self._tree_selected)
        self.tree.bind("<<TreeviewOpen>>", lambda _e: self._tree_open(True))
        self.tree.bind("<<TreeviewClose>>", lambda _e: self._tree_open(False))
        self.tree.bind("<Button-3>", self._tree_menu)
        self.tree.bind("<ButtonPress-1>", self._tree_press, add="+")
        self.tree.bind("<B1-Motion>", self._drag_motion, add="+")
        self.tree.bind("<ButtonRelease-1>", self._drag_release, add="+")
        self.tree.bind("<F2>", lambda _e: self.rename_subject())
        self.bind_all("<Control-Shift-G>", lambda _e: self.manage_subjects())
        self.tree.bind("<Delete>", lambda _e: self.delete_subject())
        self.tree.bind("<Insert>", lambda _e: self.new_subject(self.current_sid(strict=True)))
        self.tree.bind("<Alt-Up>", lambda _e: (self.reorder_subject(-1), "break")[1])
        self.tree.bind("<Alt-Down>", lambda _e: (self.reorder_subject(1), "break")[1])
        self.tree.bind("<Return>", lambda _e: (self._focus_items(), "break")[1])

    def _build_center(self):
        f = tk.Frame(self.pw, bg=C["BG"])
        self.f_center = f
        self.colorbar = tk.Frame(f, bg=C["HI"], height=4)
        self.colorbar.pack(fill="x")
        hd = tk.Frame(f, bg=C["BG"])
        hd.pack(fill="x")
        self.l_view = tk.Label(hd, text="", bg=C["BG"], fg=C["HI"], font=fnt("GTitle"), anchor="w")
        self.l_view.pack(side="left", padx=10, pady=(4, 0), fill="x", expand=True)
        fb = FlowFrame(f, bg=C["BG"])
        fb.pack(fill="x", padx=8, pady=(2, 4))
        self.fbar = fb
        self.view_btns: Dict[str, Any] = {}
        for key, txt, tip in (("list", "☰", "Liste (Ctrl+1)"), ("cards", "▦", "Cartes avec vignettes (Ctrl+2)"),
                              ("chrono", "🕘", "Chronologie par mois (Ctrl+3)")):
            b = mk_button(fb, txt, lambda k=key: self.set_view_mode(k), tip=tip)
            b.configure(padx=7)
            fb.add(b, 1)
            self.view_btns[key] = b
        b = mk_button(fb, "🗺 Carte des sujets", self.open_mindmap, tip="Carte animée de tes sujets et de leurs fiches (F8)")
        fb.add(b, 6)
        ch_an = mk_check(fb, "✨ Animations", self.v_anim, bg=C["BG"], cmd=self.toggle_animations)
        ch_an.configure(font=fnt("GSM"))
        fb.add(ch_an, 4)
        Tooltip(ch_an, "Petites animations (apparition des cartes, carte des sujets, barre de progression)")
        self.cb_sort = ttk.Combobox(fb, values=[lab for _k, lab in SORTS], state="readonly", width=14, font=fnt("GSM"))
        fb.add(self.cb_sort, 6)
        self.cb_sort.current(max(0, [k for k, _l in SORTS].index(self.sort) if self.sort in [k for k, _l in SORTS] else 0))
        self.cb_sort.bind("<<ComboboxSelected>>", lambda _e: self._sort_changed())
        Tooltip(self.cb_sort, "Tri des fiches")
        self.cb_type = ttk.Combobox(fb, values=[lab for _k, lab in TYPE_FILTERS], state="readonly", width=16, font=fnt("GSM"))
        self.cb_type.current(0)
        fb.add(self.cb_type, 3)
        self.cb_type.bind("<<ComboboxSelected>>", lambda _e: self.refresh_items())
        Tooltip(self.cb_type, "Filtrer par type")
        self.cb_tag = ttk.Combobox(fb, values=["Toutes étiquettes"], state="readonly", width=17, font=fnt("GSM"))
        self.cb_tag.current(0)
        fb.add(self.cb_tag, 3)
        self.cb_tag.bind("<<ComboboxSelected>>", lambda _e: self.refresh_items())
        Tooltip(self.cb_tag, "Filtrer par étiquette")
        self.v_sub = tk.BooleanVar(value=bool(self.store.get("include_sub", True)))
        self.chk_sub = mk_check(fb, "＋sous-sujets", self.v_sub, bg=C["BG"], cmd=self._sub_changed)
        self.chk_sub.configure(font=fnt("GSM"))
        fb.add(self.chk_sub, 4)
        Tooltip(self.chk_sub, "Montrer aussi les fiches des sous-sujets")
        self.cb_scope = ttk.Combobox(fb, values=["Partout", "Dans ce sujet"], state="readonly", width=18, font=fnt("GSM"))
        self.cb_scope.current(0)
        self.cb_scope.bind("<<ComboboxSelected>>", lambda _e: self.do_search())
        fb.add(self.cb_scope, 3)
        Tooltip(self.cb_scope, "Où chercher")
        self.cb_period = ttk.Combobox(fb, values=[lab for _k, lab in PERIODS], state="readonly", width=17, font=fnt("GSM"))
        self.cb_period.current(0)
        self.cb_period.bind("<<ComboboxSelected>>", lambda _e: self.refresh_items())
        fb.add(self.cb_period, 3)
        Tooltip(self.cb_period, "Période (date de l'info, sinon date d'ajout)")
        self.l_vcount = tk.Label(fb, text="", bg=C["BG"], fg=C["DIM"], font=fnt("GSM"), anchor="w")
        fb.add(self.l_vcount, 8)
        self.f_view = tk.Frame(f, bg=C["BG"])
        self.f_view.pack(fill="both", expand=True)
        # liste
        self.f_list = tk.Frame(self.f_view, bg=C["BG"])
        cols = ("title", "subject", "date", "tags")
        self.lst = ttk.Treeview(self.f_list, columns=cols, show="headings", selectmode="extended")
        for cid, lab, w, stt in (("title", "Titre", 300, True), ("subject", "Sujet", 150, False), ("date", "Date", 110, False),
                                 ("tags", "Étiquettes", 130, False)):
            self.lst.heading(cid, text=lab, anchor="w", command=lambda c=cid: self._heading_sort(c))
            self.lst.column(cid, width=w, stretch=stt, anchor="w", minwidth=60)
        lv = ttk.Scrollbar(self.f_list, orient="vertical", command=self.lst.yview)
        self.lst.configure(yscrollcommand=lv.set)
        self.lst.pack(side="left", fill="both", expand=True)
        lv.pack(side="right", fill="y")
        self.lst.tag_configure("fav", foreground=C["HI"])
        self.lst.tag_configure("pending", foreground=C["DIM"])
        self.lst.tag_configure("drop", background=C["HI"], foreground=C["ON_HI"])
        self.lst.bind("<Configure>", lambda _e: self._list_columns())
        dw = tkfont.Font(font=fnt("GUI")).measure("15 sept. 2026") + 22
        self.lst.column("date", width=dw, minwidth=dw)
        self._row_tip(self.lst)
        # cartes
        self.f_cards = tk.Frame(self.f_view, bg=C["BG"])
        self.cv = tk.Canvas(self.f_cards, bg=C["BG"], highlightthickness=0, bd=0, takefocus=1)
        cvs = ttk.Scrollbar(self.f_cards, orient="vertical", command=self.cv.yview)
        self.cv.configure(yscrollcommand=cvs.set)
        self.cv.pack(side="left", fill="both", expand=True)
        cvs.pack(side="right", fill="y")
        self.cv.bind("<Configure>", lambda _e: self._cards_resized())
        self.cv.bind("<MouseWheel>", lambda e: self.cv.yview_scroll(wheel_steps(e) * 3, "units"))
        self.cv.bind("<Button-4>", lambda e: self.cv.yview_scroll(-3, "units"))
        self.cv.bind("<Button-5>", lambda e: self.cv.yview_scroll(3, "units"))
        self.cv.bind("<ButtonPress-1>", self._card_press)
        self.cv.bind("<B1-Motion>", self._drag_motion)
        self.cv.bind("<ButtonRelease-1>", self._drag_release)
        self.cv.bind("<Double-Button-1>", self._card_double)
        self.cv.bind("<Motion>", self._card_motion)
        self.cv.bind("<Leave>", lambda _e: self._card_motion(type("E", (), {"x": -9999, "y": -9999})()))
        self.cv.bind("<Button-3>", self._card_menu)
        for k in ("Left", "Right", "Up", "Down", "Home", "End"):
            self.cv.bind(f"<{k}>", lambda _e, kk=k: self._card_key(kk))
        # chronologie
        self.f_chrono = tk.Frame(self.f_view, bg=C["BG"])
        self.chr = ttk.Treeview(self.f_chrono, columns=("date", "subject"), show="tree headings", selectmode="extended")
        self.chr.heading("#0", text="Fiche", anchor="w")
        self.chr.heading("date", text="Date", anchor="w")
        self.chr.heading("subject", text="Sujet", anchor="w")
        self.chr.column("#0", width=320, stretch=True)
        self.chr.column("date", width=110, stretch=False)
        self.chr.column("subject", width=150, stretch=False)
        cs = ttk.Scrollbar(self.f_chrono, orient="vertical", command=self.chr.yview)
        self.chr.configure(yscrollcommand=cs.set)
        self.chr.pack(side="left", fill="both", expand=True)
        cs.pack(side="right", fill="y")
        self.chr.tag_configure("month", foreground=C["HI"], font=fnt("GUIB"))
        self.chr.tag_configure("fav", foreground=C["HI"])
        self.chr.tag_configure("drop", background=C["HI"], foreground=C["ON_HI"])
        self.chr.bind("<Configure>", lambda _e: self._list_columns())
        self.chr.column("date", width=dw, minwidth=dw)
        self._row_tip(self.chr)
        # resultats de recherche
        self.f_results = tk.Frame(self.f_view, bg=C["BG"])
        self.rt = tk.Text(self.f_results, bg=C["CARD"], fg=C["TEXT"], relief="flat", wrap="word", highlightthickness=0,
                          padx=10, pady=6, cursor="arrow", font=fnt("GUI"), spacing1=1, takefocus=1)
        rs = ttk.Scrollbar(self.f_results, orient="vertical", command=self.rt.yview)
        self.rt.configure(yscrollcommand=rs.set)
        self.rt.pack(side="left", fill="both", expand=True)
        rs.pack(side="right", fill="y")
        self.rt.tag_configure("rtitle", foreground=C["HI"], font=fnt("GUIB"))
        self.rt.tag_configure("rsub", foreground=C["DIM"], font=fnt("GSM"))
        self.rt.tag_configure("rmeta", foreground=C["DIM"], font=fnt("GSM"), spacing3=8)
        self.rt.tag_configure("rsnip", foreground=C["TEXT"], lmargin1=22, lmargin2=22)
        self.rt.tag_configure("hl", background=C["SEL"], foreground=C["ON_SEL"])
        self.rt.tag_configure("rsel", background=C["HOVER"])
        self.rt.tag_configure("rnone", foreground=C["DIM"], font=fnt("GUI"), justify="center", spacing1=30)
        self.rt.tag_raise("hl")
        self.rt.bind("<Button-1>", self._result_click)
        self.rt.bind("<Double-Button-1>", self._result_double)
        self.rt.bind("<Button-3>", self._result_menu)
        self.rt.bind("<Key>", self._result_key)
        self.rt.bind("<MouseWheel>", lambda e: (self.rt.yview_scroll(wheel_steps(e) * 3, "units"), "break")[1])
        # corbeille
        self.f_trash = tk.Frame(self.f_view, bg=C["BG"])
        tb = FlowFrame(self.f_trash, bg=C["BG"], gap=3)
        tb.pack(fill="x", padx=4, pady=(0, 4))
        tb.add(mk_button(tb, "♻ Restaurer", self.trash_restore, "accent", tip="Remettre la sélection à sa place (Entrée)"), 0)
        tb.add(mk_button(tb, "✖ Supprimer définitivement", self.trash_purge, "danger",
                         tip="Effacer pour de bon la sélection (Suppr)"), 4)
        tb.add(mk_button(tb, "🧹 Vider la corbeille", self.trash_empty, "danger", tip="Tout effacer pour de bon"), 4)
        self.trv = ttk.Treeview(self.f_trash, columns=("kind", "deleted", "origin"), show="tree headings", selectmode="extended")
        self.trv.heading("#0", text="Élément", anchor="w")
        self.trv.heading("kind", text="Type", anchor="w")
        self.trv.heading("deleted", text="Supprimé", anchor="w")
        self.trv.heading("origin", text="Venait de", anchor="w")
        self.trv.column("#0", width=280, stretch=True)
        self.trv.column("kind", width=110, stretch=False)
        self.trv.column("deleted", width=120, stretch=False)
        self.trv.column("origin", width=150, stretch=False)
        ts = ttk.Scrollbar(self.f_trash, orient="vertical", command=self.trv.yview)
        self.trv.configure(yscrollcommand=ts.set)
        self.trv.pack(side="left", fill="both", expand=True)
        ts.pack(side="right", fill="y")
        self.trv.bind("<Delete>", lambda _e: self.trash_purge())
        self.trv.bind("<Return>", lambda _e: self.trash_restore())
        self.trv.bind("<<TreeviewSelect>>", lambda _e: self.update_detail())
        self.trv.bind("<Configure>", lambda _e: self._fit_columns(), add="+")
        self.trv.column("deleted", width=tkfont.Font(font=fnt("GUI")).measure("15 sept. 2026 10:00") + 16)
        for w in (self.lst, self.chr):
            w.bind("<<TreeviewSelect>>", self._tv_selected)
            w.bind("<Double-Button-1>", self._tv_double)
            w.bind("<Button-3>", self._tv_menu)
            w.bind("<ButtonPress-1>", self._tv_press, add="+")
            w.bind("<B1-Motion>", self._drag_motion, add="+")
            w.bind("<ButtonRelease-1>", self._drag_release, add="+")
        for w in (self.lst, self.chr, self.cv, self.rt):
            w.bind("<Return>", lambda _e: (self.open_selected(), "break")[1])
            w.bind("<Delete>", lambda _e: self.delete_selected())
            w.bind("<F2>", lambda _e: self.rename_item())
            w.bind("<Control-a>", lambda _e: (self.select_all(), "break")[1])
            w.bind("<Alt-Up>", lambda _e: (self.move_item_step(-1), "break")[1])
            w.bind("<Alt-Down>", lambda _e: (self.move_item_step(1), "break")[1])
            w.bind("<Key>", self._type_to_search, add="+")
        self._show_view_widget()

    def _row_tip(self, tv):
        """Infobulle sur une ligne de liste : titre complet, sujet, etiquettes (utile si la colonne est coupee)."""
        state = {"row": "", "job": None, "tip": None}

        def hide(_e=None):
            if state["job"]:
                try:
                    tv.after_cancel(state["job"])
                except Exception:
                    pass
                state["job"] = None
            if state["tip"] is not None:
                try:
                    state["tip"].destroy()
                except Exception:
                    pass
                state["tip"] = None

        def show(row, x, y):
            state["job"] = None
            if not row.startswith("i:") or self.drag:
                return
            it = self.store.item(row[2:])
            if not it:
                return
            txt = (it.get("title") or "(sans titre)") + "\n" + self.store.subject_path(it["subject_id"])
            if it.get("tags"):
                txt += "\n" + "  ".join("#" + t for t in tag_list(it["tags"]))
            try:
                state["tip"] = show_tip(tv, txt, x + 16, y + 18)
            except tk.TclError:
                pass

        def motion(e):
            row = tv.identify_row(e.y)
            if row != state["row"]:
                state["row"] = row
                hide()
                if row:
                    state["job"] = tv.after(700, lambda r=row, x=e.x_root, y=e.y_root: show(r, x, y))
        tv.bind("<Motion>", motion, add="+")
        tv.bind("<Leave>", lambda _e: (hide(), state.update(row="")), add="+")
        tv.bind("<ButtonPress>", hide, add="+")

    def _build_right(self):
        f = tk.Frame(self.pw, bg=C["PANEL"])
        self.f_right = f
        # --- fiche
        self.f_item = tk.Frame(f, bg=C["PANEL"])
        hd = tk.Frame(self.f_item, bg=C["PANEL"])
        hd.pack(fill="x", padx=8, pady=(6, 0))
        self.l_icon = tk.Label(hd, text="📝", bg=C["PANEL"], fg=C["HI"], font=fnt("Emoji"))
        self.l_icon.pack(side="left", padx=(0, 4))
        self.v_title = tk.StringVar()
        self.e_title = tk.Entry(hd, textvariable=self.v_title, bg=C["PANEL"], fg=C["HI"], insertbackground=C["HI"],
                                relief="flat", font=fnt("GTitle"), highlightthickness=1, highlightbackground=C["PANEL"],
                                highlightcolor=C["HI"], selectbackground=C["SEL"], selectforeground=C["ON_SEL"])
        self.e_title.configure(width=1)
        self.e_title.bind("<Return>", lambda _e: (self._title_commit(), self.editor.t.focus_set()))
        self.e_title.bind("<FocusOut>", lambda _e: self._title_commit())
        self.e_title.bind("<Escape>", lambda _e: (self.v_title.set(self._loaded_title), self._focus_items()))
        self.e_title.bind("<Control-KeyPress>", self._entry_ctrl)
        Tooltip(self.e_title, "Titre de la fiche (F2) : Entrée pour valider")
        self.b_more = mk_button(hd, "⋯", self._item_more, tip="Toutes les actions")
        self.b_more.pack(side="right", padx=(2, 0))
        self.b_pin = mk_button(hd, "📌", self.toggle_pin, tip="Épingler en haut (Ctrl+P)")
        self.b_pin.pack(side="right", padx=2)
        self.b_fav = mk_button(hd, "☆", self.toggle_fav, tip="Favori (Ctrl+D)")
        self.b_fav.pack(side="right", padx=2)
        self.e_title.pack(side="left", fill="x", expand=True, ipady=2)
        self.l_meta = tk.Label(self.f_item, text="", bg=C["PANEL"], fg=C["DIM"], font=fnt("GSM"), anchor="w", justify="left")
        self.l_meta.pack(fill="x", padx=10)
        self.l_meta.bind("<Configure>", lambda e: self.l_meta.configure(wraplength=max(200, e.width - 4)))
        tg = tk.Frame(self.f_item, bg=C["PANEL"])
        tg.pack(fill="x", padx=8, pady=(2, 4))
        tk.Label(tg, text="🏷", bg=C["PANEL"], fg=C["FG"], font=fnt("GUI")).pack(side="left")
        self.v_tags = tk.StringVar()
        self.e_tags = mk_entry(tg, self.v_tags, 30, "GSM")
        self.e_tags.pack(side="left", fill="x", expand=True, padx=(4, 0), ipady=2)
        self.e_tags.bind("<Return>", lambda _e: self._tags_commit())
        self.e_tags.bind("<FocusOut>", lambda _e: self._tags_commit())
        self.e_tags.bind("<Control-KeyPress>", self._entry_ctrl)
        self.e_tags.bind("<KeyRelease>", self._tags_autocomplete, add="+")
        Tooltip(self.e_tags, "Étiquettes séparées par des virgules (Ctrl+T) ; Tab complète une étiquette existante")
        self.e_tags.bind("<Tab>", self._tags_tab)
        self.nb = ttk.Notebook(self.f_item)
        self.nb.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        self.tab_prev = ScrollFrame(self.nb, bg=C["PANEL"])
        self.tab_body = tk.Frame(self.nb, bg=C["PANEL"])
        self.tab_info = ScrollFrame(self.nb, bg=C["PANEL"])
        self.nb.add(self.tab_prev, text="👁 Aperçu")
        self.nb.add(self.tab_body, text="📝 Notes")
        self.nb.add(self.tab_info, text="🗂 Fiche")
        self.editor = RichEditor(self.tab_body, self, on_change=self._editor_changed)
        self.editor.pack(fill="both", expand=True)
        self.editor.t.bind("<Escape>", lambda _e: (self.editor.flush(), self._focus_items()))
        self.nb.bind("<<NotebookTabChanged>>", lambda _e: self._tab_changed())
        # --- accueil / selection multiple
        self.f_home = ScrollFrame(f, bg=C["PANEL"])
        self._loaded_title = ""
        self._loaded_tags = ""
        self._detail_mode = ""

    def _show_view_widget(self):
        for w in (self.f_list, self.f_cards, self.f_chrono, self.f_results, self.f_trash):
            w.pack_forget()
        mode = self._effective_mode()
        {"list": self.f_list, "cards": self.f_cards, "chrono": self.f_chrono, "results": self.f_results,
         "trash": self.f_trash}[mode].pack(fill="both", expand=True)
        for k, b in self.view_btns.items():
            on = (k == self.view_mode and mode not in ("results", "trash"))
            b._colors = (C["HI"], C["ON_HI"], C["HI_ACT"], C["ON_HI"]) if on else (C["BTN"], C["BTN_FG"], C["HI"], C["ON_HI"])
            b.configure(bg=b._colors[0], fg=b._colors[1])
        searching = self.cur_view == "search"
        trash = self.cur_view == "v:trash"
        fb = self.fbar
        fb.show(self.chk_sub, self.cur_view.startswith("s:"))
        fb.show(self.cb_scope, searching)
        fb.show(self.cb_period, not trash)
        for w in (self.cb_sort, self.cb_type, self.cb_tag):
            fb.show(w, not trash and not (searching and w is self.cb_sort))
        fb.reflow()

    def _effective_mode(self) -> str:
        if self.cur_view == "search":
            return "results"
        if self.cur_view == "v:trash":
            return "trash"
        return self.view_mode

    def _list_columns(self):
        try:
            self._fit_columns()
        except tk.TclError:
            pass
        try:
            w = self.lst.winfo_width()
            multi = self._multi_subject_view()
            if w < 430:
                cols = ("title", "date")
            elif w < 620:
                cols = ("title", "subject", "date") if multi else ("title", "date", "tags")
            else:
                cols = ("title", "subject", "date", "tags") if multi else ("title", "date", "tags")
            if tuple(self.lst["displaycolumns"]) != cols:
                self.lst["displaycolumns"] = cols
            cw = self.chr.winfo_width()
            ccols = ("date",) if cw < 480 else ("date", "subject")
            if tuple(self.chr["displaycolumns"]) != ccols:
                self.chr["displaycolumns"] = ccols
        except tk.TclError:
            pass

    def _fit_columns(self):
        """La colonne Titre prend la place restante : Date et Sujet ne sont jamais coupees a droite."""
        for tv, main in ((self.lst, "title"), (self.chr, "#0"), (self.trv, "#0")):
            W = tv.winfo_width()
            if W < 50:
                continue
            disp = list(tv["displaycolumns"])
            if disp == ["#all"]:
                disp = list(tv["columns"])
            fixed = sum(int(tv.column(c, "width")) for c in disp if c != main)
            want = max(120, W - fixed - 4)
            if abs(int(tv.column(main, "width")) - want) > 2:
                tv.column(main, width=want)

    def _multi_subject_view(self) -> bool:
        if self.cur_view.startswith("s:"):
            s = self.store.subject(self.cur_view[2:])
            return bool(self.v_sub.get() and s and self.store.children(s["id"]))
        return True

    # ------------------------------------------------------------ raccourcis
    def _bind_keys(self):
        b = self.bind
        b("<Control-KeyPress>", self.ctrl_key)
        b("<F1>", lambda _e: self.show_help())
        b("<F2>", lambda _e: self.rename_any())
        b("<F5>", lambda _e: self.refresh_all())
        b("<F11>", lambda _e: self.open_reader())
        b("<F8>", lambda _e: self.open_mindmap())
        b("<Escape>", lambda _e: self.clear_search() if self.v_search.get() else None)
        for seq in ("<Control-plus>", "<Control-equal>", "<Control-KP_Add>"):
            b(seq, lambda _e: self.zoom(1))
        for seq in ("<Control-minus>", "<Control-KP_Subtract>"):
            b(seq, lambda _e: self.zoom(-1))
        b("<Control-MouseWheel>", lambda e: self.zoom(1 if wheel_steps(e) < 0 else -1))

    def _focus_is_text(self) -> bool:
        w = self.focus_get()
        return isinstance(w, (tk.Entry, tk.Text, ttk.Entry, ttk.Combobox)) and w is not self.rt

    def ctrl_key(self, e):
        k = (e.keysym or "").lower()
        shift = bool(e.state & 0x1)
        txt = self._focus_is_text()
        if k == "0" and not txt:
            self.zoom(0)
            return "break"
        acts: Dict[Tuple[str, bool], Callable[[], Any]] = {
            ("n", False): self.new_note, ("n", True): lambda: self.new_subject(None),
            ("l", False): self.add_link_dialog, ("q", True): self.add_quote_dialog,
            ("r", False): self.record_memo, ("o", False): lambda: self.add_files_dialog(None),
            ("i", True): lambda: self.add_files_dialog("image"), ("f", False): self.focus_search,
            ("g", False): self.open_palette, ("1", False): lambda: self.set_view_mode("list"),
            ("2", False): lambda: self.set_view_mode("cards"), ("3", False): lambda: self.set_view_mode("chrono"),
            ("d", False): self.toggle_fav, ("p", False): self.toggle_pin, ("t", False): self.edit_tags,
            ("m", False): lambda: self.move_selected(False), ("e", True): lambda: self.export_dialog(None, False),
            ("s", False): self.backup_now, ("v", True): lambda: self.smart_paste(plain=True),
        }
        if (k, shift) in acts:
            acts[(k, shift)]()
            return "break"
        if k == "v" and not shift and not txt:
            self.smart_paste()
            return "break"
        if k == "z" and not txt:
            self.do_undo()
            return "break"
        if k == "a" and not txt:
            self.select_all()
            return "break"
        return None

    def _entry_ctrl(self, e):
        k = (e.keysym or "").lower()
        if k in ("v", "z", "y", "a", "x", "c", "plus", "minus", "equal") and not (e.state & 0x1 and k == "v"):
            return None
        if k in "ngrolfdpmtse123" or (e.state & 0x1 and k in ("q", "i", "v", "n", "e")):
            if e.widget is self.e_title:
                self._title_commit()
            elif e.widget is self.e_tags:
                self._tags_commit()
            return self.ctrl_key(e)
        return None

    def _type_to_search(self, e):
        if e.state & 0x4 or e.state & 0x20000 or e.state & 0x8:
            return None
        ch = e.char
        if ch and ch.isprintable() and len(ch) == 1 and ch not in " \t":
            self.e_search.focus_set()
            self.e_search.insert("end", ch)
            return "break"
        return None

    def _focus_items(self):
        mode = self._effective_mode()
        w = {"list": self.lst, "cards": self.cv, "chrono": self.chr, "results": self.rt, "trash": self.trv}[mode]
        w.focus_set()
        if mode == "list" and self.visible and not self.lst.selection():
            first = self.lst.get_children("")
            if first:
                self.lst.selection_set(first[0])
                self.lst.focus(first[0])
        elif mode == "results" and self.results and not self.selected:
            self.select_ids([self.results[0]["id"]])
        return "break"

    # ------------------------------------------------------------ glisser-deposer externe
    def _setup_dnd(self):
        try:
            import tkinterdnd2  # type: ignore
            from tkinterdnd2 import DND_FILES, DND_TEXT  # type: ignore
            if not getattr(self, "_dnd_ok", False):
                req = getattr(tkinterdnd2.TkinterDnD, "_require", None) or getattr(tkinterdnd2.TkinterDnD, "require", None)
                req(self)
                self._dnd_ok = True
            for w in (self.lst, self.cv, self.chr, self.rt, self.tree, self.f_home.canvas, self.tab_prev.canvas):
                w.drop_target_register(DND_FILES, DND_TEXT)
                w.dnd_bind("<<Drop>>", self._on_drop)
        except Exception as ex:
            self._dnd_ok = False
            logger.info("glisser-déposer externe indisponible : %s", ex)

    def _on_drop(self, event):
        data = event.data or ""
        try:
            parts = list(self.tk.splitlist(data))
        except tk.TclError:
            parts = [data]
        parts = [p.strip() for p in parts if p and p.strip()]
        if not parts:
            return
        sid = self.current_sid()
        if event.widget is self.tree:
            try:
                iid = self.tree.identify_row(event.y_root - self.tree.winfo_rooty())
                if iid and iid.startswith("s:"):
                    sid = int(iid[2:])
            except Exception:
                pass
        paths = [p for p in parts if os.path.exists(p)]
        if paths and len(paths) == len(parts):
            self.add_paths(paths, sid)
            return
        text = data if not paths else " ".join(p for p in parts if not os.path.exists(p))
        urls = find_urls(text)
        if urls and len(" ".join(urls)) >= len(text.strip()) * 0.8:
            self.add_urls(urls, sid)
        else:
            self.add_text_note(text, sid)
        if paths:
            self.add_paths(paths, sid)

    # ================================================================ arbre des sujets
    def refresh_tree(self):
        tv = self.tree
        st = self.store
        sel = self.cur_view if self.cur_view != "search" else ""
        y = tv.yview()[0] if tv.get_children("") else 0
        tv.delete(*tv.get_children(""))
        tot = st.total_counts()
        n_all = st.stats()["items"]
        counts = {"v:all": n_all,
                  "v:fav": st.q("SELECT COUNT(*) n FROM items WHERE deleted IS NULL AND fav=1")[0]["n"],
                  "v:pin": st.q("SELECT COUNT(*) n FROM items WHERE deleted IS NULL AND pinned=1")[0]["n"],
                  "v:trash": st.q("SELECT COUNT(*) n FROM items WHERE deleted IS NOT NULL")[0]["n"]
                  + st.q("SELECT COUNT(*) n FROM subjects WHERE deleted IS NOT NULL")[0]["n"]}
        tags = st.all_tags()
        for key, ic, lab in SPECIAL_VIEWS:
            n = counts.get(key, len(tags) if key == "v:tags" else "")
            tv.insert("", "end", iid=key, text=f" {ic}  {lab}", values=(n if n not in (0, "") else "",), tags=("special",),
                      open=bool(st.get("tags_open", False)) if key == "v:tags" else False)
            if key == "v:tags":
                for t, c in tags[:300]:
                    tv.insert(key, "end", iid=f"t:{t}", text=f" #{t}", values=(c,), tags=("tag",))
        tv.insert("", "end", iid="sep", text="", tags=("sep",))

        def add(parent_iid, pid):
            for s in st.children(pid):
                iid = f"s:{s['id']}"
                n = tot.get(s["id"], 0)
                tv.insert(parent_iid, "end", iid=iid, text=f"{s['icon'] or '📁'} {s['name']}", values=(n if n else "",),
                          image=self.swatch(s["color"]), open=bool(s["expanded"]),
                          tags=("pinned" if s["pinned"] else "subj",))
                add(iid, s["id"])
        add("", None)
        if sel and tv.exists(sel):
            self._tree_lock = True
            tv.selection_set(sel)
            tv.see(sel)
            self._tree_lock = False
        else:
            tv.selection_remove(tv.selection())
        tv.yview_moveto(y)
        vals = ["Toutes étiquettes"] + [f"#{t} ({c})" for t, c in tags[:200]]
        cur = self.cb_tag.get()
        self.cb_tag.configure(values=vals)
        self._tag_values = [""] + [t for t, _c in tags[:200]]
        if cur not in vals:
            self.cb_tag.current(0)

    def reveal_subject(self, sid: Optional[int], flash: bool = True):
        """Rend un sujet visible dans l'arbre : deplie ses parents, defile jusqu'a lui et le fait clignoter."""
        if not sid:
            return
        tv = self.tree
        iid = f"s:{sid}"
        s = self.store.subject(sid)
        while s and s["parent_id"]:
            if not self.store.subject(s["parent_id"])["expanded"]:
                self.store.update_subject(s["parent_id"], expanded=1)
            s = self.store.subject(s["parent_id"])
        if not tv.exists(iid):
            self.refresh_tree()
        if not tv.exists(iid):
            return
        p = tv.parent(iid)
        while p:
            tv.item(p, open=True)
            p = tv.parent(p)
        tv.see(iid)
        if flash:
            tags = [t for t in tv.item(iid, "tags") if t != "drop"]
            tv.item(iid, tags=tags + ["drop"])
            self.after(1600, lambda: tv.exists(iid) and tv.item(iid, tags=tags))

    def _tree_selected(self, _e=None):
        if getattr(self, "_tree_lock", False):
            return
        sel = self.tree.selection()
        if not sel or sel[0] == "sep" or sel[0] == self.cur_view:
            return
        self.open_view(sel[0])

    def _tree_open(self, state: bool):
        iid = self.tree.focus()
        if iid.startswith("s:"):
            self.store.update_subject(int(iid[2:]), expanded=int(state))
            self.store.version -= 0
        elif iid == "v:tags":
            self.store.set("tags_open", state)

    def open_view(self, key: str, keep_search: bool = False):
        self._commit_pending()
        if not keep_search and self.v_search.get():
            self._search_lock = True
            self.v_search.set("")
            self._search_lock = False
            self._update_placeholder()
        self.cur_view = key
        if key != "search":
            self.view_before_search = key
            self.store.set("last_view", key)
            if self.tree.exists(key) and key not in self.tree.selection():
                self._tree_lock = True
                self.tree.selection_set(key)
                self.tree.see(key)
                self._tree_lock = False
        self.selected = []
        self.cur_item = None
        self._show_view_widget()
        self.refresh_items()

    def current_sid(self, strict: bool = False) -> Optional[int]:
        """Sujet ou ajouter : sujet ouvert, sinon sujet de la fiche choisie, sinon « À classer »."""
        v = self.cur_view if self.cur_view != "search" else self.view_before_search
        if v.startswith("s:") and self.store.subject(v[2:]):
            return int(v[2:])
        if self.cur_item:
            it = self.store.item(self.cur_item)
            if it and self.store.subject(it["subject_id"]):
                return it["subject_id"]
        if strict:
            return None
        return self.store.inbox_subject()

    # ================================================================ fiches : collecte et tri
    def _period_since(self) -> str:
        k = PERIODS[max(0, self.cb_period.current())][0]
        if not k:
            return ""
        if k == "365":
            return f"{dt.date.today().year}-01-01"
        return (dt.date.today() - dt.timedelta(days=int(k))).isoformat()

    def _filter_type(self) -> str:
        return TYPE_FILTERS[max(0, self.cb_type.current())][0]

    def _filter_tag(self) -> str:
        i = self.cb_tag.current()
        vals = getattr(self, "_tag_values", [""])
        return vals[i] if 0 <= i < len(vals) else ""

    def collect_items(self) -> List[Dict[str, Any]]:
        st = self.store
        v = self.cur_view
        if v.startswith("s:"):
            sid = int(v[2:])
            sids = [sid] + (st.descendants(sid) if self.v_sub.get() else [])
            items = st.items_in(sids)
        elif v == "v:fav":
            items = st.items_where("fav=1")
        elif v == "v:pin":
            items = st.items_where("pinned=1")
        elif v == "v:recent":
            items = st.items_where("1=1 ORDER BY COALESCE(opened, updated, created) DESC", limit=150)
        elif v == "v:tags":
            items = st.items_where("tags<>''")
        elif v.startswith("t:"):
            tg = norm(v[2:])
            items = [r for r in st.items_where("tags<>''") if tg in [norm(t) for t in tag_list(r["tags"])]]
        else:
            items = st.items_where("1=1")
        typ = self._filter_type()
        if typ:
            items = [r for r in items if r["type"] == typ]
        tg = self._filter_tag()
        if tg:
            items = [r for r in items if norm(tg) in [norm(t) for t in tag_list(r.get("tags") or "")]]
        since = self._period_since()
        if since:
            items = [r for r in items if (r.get("event_date") or r.get("created") or "") >= since]
        return self.sort_items(items, "recentopen" if v == "v:recent" and self.sort == "manual" else self.sort)

    def sort_items(self, items: List[Dict[str, Any]], how: str) -> List[Dict[str, Any]]:
        def evd(r):
            return r.get("event_date") or r.get("created") or ""
        if how == "recent":
            items.sort(key=lambda r: r.get("created") or "", reverse=True)
        elif how == "old":
            items.sort(key=lambda r: r.get("created") or "")
        elif how == "title":
            items.sort(key=lambda r: norm(r.get("title") or ""))
        elif how == "type":
            items.sort(key=lambda r: (TYPE_ORDER.index(r["type"]) if r["type"] in TYPE_ORDER else 99, norm(r.get("title") or "")))
        elif how == "event":
            items.sort(key=evd, reverse=True)
        elif how == "subject":
            items.sort(key=lambda r: (norm(self.store.subject_path(r["subject_id"])), float(r.get("sort") or 0)))
        elif how == "recentopen":
            items.sort(key=lambda r: r.get("opened") or r.get("updated") or "", reverse=True)
        else:
            multi = self._multi_subject_view() and self.cur_view.startswith("s:")
            if multi:
                order = {sid: k for k, sid in enumerate(self.subject_order())}
                items.sort(key=lambda r: (order.get(r["subject_id"], 9999), float(r.get("sort") or 0)))
            elif self.cur_view.startswith("s:"):
                items.sort(key=lambda r: float(r.get("sort") or 0))
            else:
                items.sort(key=lambda r: r.get("updated") or "", reverse=True)
        items.sort(key=lambda r: -int(r.get("pinned") or 0))
        return items

    def _sort_changed(self):
        self.sort = SORTS[max(0, self.cb_sort.current())][0]
        self.store.set("sort", self.sort)
        self.refresh_items()

    def _heading_sort(self, col: str):
        nxt = {"title": "title", "subject": "subject", "date": "old" if self.sort == "recent" else "recent", "tags": "type"}[col]
        if col == "subject":
            self.sort = "subject"
        else:
            self.sort = nxt
            keys = [k for k, _l in SORTS]
            if nxt in keys:
                self.cb_sort.current(keys.index(nxt))
        self.refresh_items()

    def _sub_changed(self):
        self.store.set("include_sub", bool(self.v_sub.get()))
        self.refresh_items()

    def set_view_mode(self, mode: str):
        if mode not in ("list", "cards", "chrono"):
            return
        self.view_mode = mode
        self.v_view.set(mode)
        self.store.set("view_mode", mode)
        if self.cur_view in ("search", "v:trash"):
            self.open_view(self.view_before_search if self.view_before_search not in ("search", "v:trash") else "v:all")
            return
        keep = list(self.selected)
        self._show_view_widget()
        self.fill_view()
        if keep:
            self.select_ids(keep, see=True)

    def _view_from_var(self):
        self.set_view_mode(self.v_view.get())

    # ================================================================ rafraichissement
    def refresh_all(self, first: bool = False):
        self._commit_pending()
        keep = list(self.selected)
        self.refresh_tree()
        if not self._view_valid(self.cur_view) and self.cur_view != "search":
            self.cur_view = "v:all"
        self._show_view_widget()
        self.refresh_items(keep=keep)
        if first:
            if self.cur_view.startswith("s:") and not keep:
                its = self.visible
                pin = [r for r in its if r.get("pinned")]
                if pin and self.store.subject(self.cur_view[2:]) and self.store.subject(self.cur_view[2:])["name"] == "Bienvenue":
                    self.select_ids([pin[0]["id"]])
            self.set_status(f"Grimoire prêt : {self.store.stats()['items']} fiche(s) dans {len(self.store.subjects())} sujets.  "
                            f"Données : {Paths.data}", "DIM")

    def refresh_items(self, keep: Optional[List[int]] = None):
        if self.cur_view == "search":
            self.do_search(keep=keep)
            return
        if self.cur_view == "v:trash":
            self.fill_trash()
            self._header()
            self.update_detail()
            return
        self.visible = self.collect_items()
        self._header()
        self.fill_view()
        ids = {r["id"] for r in self.visible}
        keep = [i for i in (keep or []) if i in ids]
        if keep:
            self.select_ids(keep, see=True)
        else:
            self.selected = []
            self.update_detail()

    def _header(self):
        st = self.store
        v = self.cur_view
        color = C["HI"]
        if v.startswith("s:") and st.subject(v[2:]):
            s = st.subject(v[2:])
            title = f"{s['icon'] or '📁'}  {st.subject_path(s['id'])}"
            color = s["color"] or C["HI"]
        elif v == "search":
            title = f"🔍  Recherche : « {self.v_search.get().strip()} »"
        elif v.startswith("t:"):
            title = f"🏷  Étiquette #{v[2:]}"
        else:
            title = next((f"{ic}  {lab}" for k, ic, lab in SPECIAL_VIEWS if k == v), "Grimoire")
        self.colorbar.configure(bg=color)
        w = max(200, self.f_center.winfo_width() - 30)
        self.l_view.configure(text=self.fit_text(title, "GTitle", w, 2))
        n = len(self.results) if v == "search" else (len(self.visible) if v != "v:trash" else self._trash_count)
        self.l_vcount.configure(text=f"{n} fiche{'s' if n > 1 else ''}" if v != "v:trash" else f"{n} élément(s)")
        self.fbar.reflow()
        self.l_count.configure(text=f"{st.stats()['items']} fiches · {len(st.subjects())} sujets")

    def fill_view(self):
        mode = self._effective_mode()
        if mode == "list":
            self.fill_list()
        elif mode == "cards":
            self.fill_cards()
        elif mode == "chrono":
            self.fill_chrono()

    def _row_title(self, r: Dict[str, Any]) -> str:
        t = TYPES.get(r["type"], TYPES["file"])
        pre = ("📌" if r.get("pinned") else "") + ("★ " if r.get("fav") else "")
        m = self.store.meta(r)
        pend = " ⏳" if m.get("pending") else ""
        return f"{pre}{t['icon']}  {r.get('title') or '(sans titre)'}{pend}"

    def _row_date(self, r: Dict[str, Any]) -> str:
        if r.get("event_date"):
            return fmt_date(r["event_date"], False)
        return fmt_date(r.get("created") or "", False)

    def fill_list(self):
        lv = self.lst
        lv.delete(*lv.get_children(""))
        for r in self.visible:
            s = self.store.subject(r["subject_id"])
            lv.insert("", "end", iid=f"i:{r['id']}", values=(self._row_title(r), s["name"] if s else "", self._row_date(r),
                                                             ", ".join(tag_list(r.get("tags") or ""))),
                      tags=("fav",) if r.get("fav") else ())
        self._list_columns()
        self._empty_hint(lv, not self.visible)

    def _empty_hint(self, widget, empty: bool):
        lab = getattr(widget, "_hint", None)
        if lab is None:
            lab = tk.Label(widget, bg=C["CARD"], fg=C["DIM"], font=fnt("GUI"), justify="center")
            widget._hint = lab
        if empty:
            v = self.cur_view
            if v.startswith("s:"):
                msg = ("Ce sujet est vide.\n\n＋ Ajouter, Ctrl+V pour coller un lien, du texte ou une image,\n"
                       "ou glisse ici des fichiers, des liens ou du texte.")
            elif self._filter_type() or self._filter_tag() or self._period_since():
                msg = "Aucune fiche ne correspond aux filtres."
            else:
                msg = "Rien ici pour l'instant."
            lab.configure(text=msg, wraplength=max(200, widget.winfo_width() - 40))
            lab.place(relx=0.5, rely=0.3, anchor="center")
        else:
            lab.place_forget()

    def fill_chrono(self):
        tv = self.chr
        tv.delete(*tv.get_children(""))
        items = sorted(self.visible, key=lambda r: r.get("event_date") or r.get("created") or "", reverse=True)
        groups: Dict[str, List[Dict[str, Any]]] = {}
        order: List[str] = []
        for r in items:
            d = (r.get("event_date") or r.get("created") or "")[:7] or "????"
            if d not in groups:
                groups[d] = []
                order.append(d)
            groups[d].append(r)
        for m in order:
            lab = month_label(m + "-01") if m != "????" else "Sans date"
            tv.insert("", "end", iid=f"m:{m}", text=f"📅  {lab[:1].upper() + lab[1:]}",
                      values=(f"{len(groups[m])} fiche{'s' if len(groups[m]) > 1 else ''}", ""), open=True, tags=("month",))
            for r in groups[m]:
                s = self.store.subject(r["subject_id"])
                tv.insert(f"m:{m}", "end", iid=f"i:{r['id']}", text=self._row_title(r),
                          values=(self._row_date(r), s["name"] if s else ""), tags=("fav",) if r.get("fav") else ())
        self._list_columns()
        self._empty_hint(tv, not items)

    # ------------------------------------------------------------ cartes
    def _cards_resized(self):
        w = self.cv.winfo_width()
        if getattr(self, "_cards_w", 0) != w and self._effective_mode() == "cards":
            self._cards_w = w
            if getattr(self, "_cards_job", None):
                self.after_cancel(self._cards_job)
            self._cards_job = self.after(80, self.fill_cards)

    # ================================================================ 1.5 : cartes illustrees
    def _gx_thumb_src(self, r: Dict[str, Any]) -> str:
        """vignette d'une fiche : image/media de la fiche, sinon apercu de lien en cache, sinon ''."""
        if r.get("thumb"):
            return r["thumb"]
        if r["type"] == "image" and r.get("file"):
            return r["file"]
        for u in gx_item_urls(r)[:3]:
            p = gx_preview_image(u)
            if p:
                return p
            a = gx_archive_get(self.store, u)
            fo = gx_archive_folder(a)
            cap = (a or {}).get("info", {}).get("capture") if a else ""
            if fo and cap and os.path.isfile(os.path.join(fo, cap)):
                return os.path.join(fo, cap)
        return ""

    def _card_dims(self) -> Tuple[int, int, int, int]:
        W = max(200, self.cv.winfo_width())
        base = 210 + 10 * int(self.store.get("font_delta", 0) or 0)
        cols = max(1, (W - 12) // (base + 14))
        cw = (W - 12 - (cols - 1) * 14) // cols
        thumb_h = int(cw * 0.50)
        lh = tkfont.Font(font=fnt("GCard")).metrics("linespace")
        lh2 = tkfont.Font(font=fnt("GCardD")).metrics("linespace")
        ch = thumb_h + 2 * lh + 3 * lh2 + 34
        return cols, cw, ch, thumb_h

    def fill_cards(self):
        cv = self.cv
        cv.delete("all")
        self.card_boxes = []
        self._card_imgs: List[Any] = []
        self._card_hover = None
        items = self.visible[:600]
        cols, cw, ch, th = self._card_dims()
        lh = tkfont.Font(font=fnt("GCard")).metrics("linespace")
        lh2 = tkfont.Font(font=fnt("GCardD")).metrics("linespace")
        pending: List[Tuple[int, str, int, int, int, int]] = []
        for k, r in enumerate(items):
            col, row = k % cols, k // cols
            x0 = 6 + col * (cw + 14)
            y0 = 8 + row * (ch + 14)
            x1, y1 = x0 + cw, y0 + ch
            iid = r["id"]
            tg = (f"c{iid}", "cardall")
            sel = iid in self.selected
            s = self.store.subject(r["subject_id"])
            scol = (s["color"] if s else "") or C["HI"]
            cv.create_rectangle(x0 + 3, y0 + 3, x1 + 3, y1 + 3, fill=gx_mix(C["BG"], "#000000", 0.35), width=0, tags=tg + ("shadow",))
            cv.create_rectangle(x0, y0, x1, y1, fill=C["CARD"], outline=C["HI"] if sel else C["LINE"], width=3 if sel else 1,
                                tags=("card",) + tg)
            cv.create_rectangle(x0 + 1, y0 + 1, x1 - 1, y0 + 5, fill=scol, width=0, tags=tg)
            t = TYPES.get(r["type"], TYPES["file"])
            ty0 = y0 + 8
            # vignette (chargee en differe) ou tuile coloree
            cv.create_rectangle(x0 + 6, ty0, x1 - 6, ty0 + th, fill=gx_mix(C["PANEL"], scol, 0.22), width=0, tags=tg + (f"th{iid}",))
            cv.create_text((x0 + x1) // 2, ty0 + th // 2 - 6, text=(s["icon"] if s and s.get("icon") else t["icon"]),
                           font=fnt("EmojiBig"), fill=scol, tags=tg + (f"ic{iid}",))
            src = self._gx_thumb_src(r)
            if src:
                pending.append((iid, src, (x0 + x1) // 2, ty0 + th // 2, cw - 12, th))
            # badge de type + etoile
            badge = f" {t['icon']} {t['label']} "
            bt = cv.create_text(x0 + 12, ty0 + 6, text=badge, anchor="nw", fill=C["ON_HI"], font=fnt("GCardD"), tags=tg)
            bb = cv.bbox(bt)
            if bb:
                br = cv.create_rectangle(bb[0] - 2, bb[1] - 1, bb[2] + 2, bb[3] + 1, fill=scol, outline="", tags=tg)
                cv.tag_lower(br, bt)
            star = cv.create_text(x1 - 12, ty0 + 4, text="★" if r.get("fav") else "☆", anchor="ne",
                                  fill=C["HI"] if r.get("fav") else C["DIM"], font=("Segoe UI Symbol", 15), tags=tg + ("star", f"st{iid}"))
            _ = star
            if r.get("pinned"):
                cv.create_text(x1 - 34, ty0 + 6, text="📌", anchor="ne", font=fnt("GCardD"), tags=tg)
            perm = any(gx_archive_folder(gx_archive_get(self.store, u)) for u in gx_item_urls(r)[:4]) if (r.get("url") or "http" in (r.get("body_text") or "")) else False
            if perm:
                pt = cv.create_text(x0 + 12, ty0 + th - 6, text=" ✔ Permanent ", anchor="sw", fill="#FFFFFF", font=fnt("GCardD"), tags=tg)
                pb = cv.bbox(pt)
                if pb:
                    pr = cv.create_rectangle(pb[0] - 2, pb[1] - 1, pb[2] + 2, pb[3] + 1, fill="#2E9E5B", outline="", tags=tg)
                    cv.tag_lower(pr, pt)
            yt = ty0 + th + 6
            title = r.get("title") or "(sans titre)"
            cv.create_text(x0 + 8, yt, text=self.fit_text(title, "GCard", cw - 16, 2), anchor="nw",
                           fill=C["HI"] if r.get("fav") else C["TEXT"], font=fnt("GCard"), width=cw - 14, tags=tg)
            ym = yt + 2 * lh + 2
            meta = f"🗓 {self._row_date(r)}"
            if self._multi_subject_view() and s:
                meta += f"  ·  {s.get('icon') or ''} {s['name']}"
            cv.create_text(x0 + 8, ym, text=self.fit_text(meta, "GCardD", cw - 16), anchor="nw", fill=C["DIM"], font=fnt("GCardD"), tags=tg)
            desc = self.store.meta(r).get("description") or ""
            if not desc:
                desc = r.get("body_text") or r.get("extracted") or r.get("url") or ""
            if r["type"] == "quote" and desc:
                desc = "« " + desc.strip() + " »"
            if desc:
                cv.create_text(x0 + 8, ym + lh2 + 2, text=self.fit_text(desc, "GCardD", cw - 16, 2), anchor="nw",
                               fill=C["QUOTE"] if r["type"] == "quote" else C["TEXT"], font=fnt("GCardD"), tags=tg)
            self.card_boxes.append((x0, y0, x1, y1, iid))
        rows = (len(items) + cols - 1) // cols
        total_h = 8 + rows * (ch + 14)
        if len(self.visible) > len(items):
            cv.create_text(12, total_h + 4, anchor="nw", fill=C["WARN"], font=fnt("GSM"),
                           text=f"… {len(self.visible) - len(items)} fiche(s) de plus : utilise la vue Liste ou un filtre.")
            total_h += 30
        cv.configure(scrollregion=(0, 0, max(1, cv.winfo_width()), max(total_h, cv.winfo_height())))
        self._empty_hint(cv, not items)
        # vignettes en differe (les cartes visibles d'abord) : l'affichage reste instantane meme avec 150+ fiches
        top = cv.canvasy(0)
        pending.sort(key=lambda p: (0 if p[3] >= top - 50 and p[3] <= top + cv.winfo_height() + 200 else 1, p[3]))
        self._gx_thumb_gen = getattr(self, "_gx_thumb_gen", 0) + 1
        gen = self._gx_thumb_gen
        self.after(15, lambda: self._gx_load_thumbs(pending, gen))
        # apparition en douceur (seulement quand la liste change, pas a chaque clic)
        sig = (self.cur_view, tuple(r["id"] for r in items[:60]), cols)
        if self.store.get("animations", True) and sig != getattr(self, "_gx_card_sig", None) and items:
            self._gx_fade(rows_visible=max(1, int(cv.winfo_height() // (ch + 14)) + 1), cols=cols, ids=[r["id"] for r in items])
        self._gx_card_sig = sig

    def _gx_load_thumbs(self, pending, gen):
        if gen != getattr(self, "_gx_thumb_gen", 0) or self._effective_mode() != "cards":
            return
        t0 = time.time()
        while pending and time.time() - t0 < 0.03:
            iid, src, cx, cy, w, h = pending.pop(0)
            img = self.photo(src, w, h)
            if img is None:
                continue
            self._card_imgs.append(img)
            self.cv.delete(f"ic{iid}")
            o = self.cv.create_image(cx, cy, image=img, tags=(f"c{iid}", "cardall", f"im{iid}"))
            above = self.cv.find_withtag(f"th{iid}")
            if above:
                self.cv.tag_raise(o, above[0])
        if pending:
            self.after(10, lambda: self._gx_load_thumbs(pending, gen))

    def _gx_fade(self, rows_visible: int, cols: int, ids: List[int]):
        """les cartes du haut glissent et apparaissent rangee par rangee (~0,4 s)."""
        cv = self.cv
        n = min(len(ids), rows_visible * cols)
        first = ids[:n]
        for i in first:
            cv.itemconfigure(f"c{i}", state="hidden")
            cv.move(f"c{i}", 0, 14)

        def show(k: int, step: int):
            if not cv.winfo_exists():
                return
            row = first[k * cols:(k + 1) * cols]
            if not row:
                return
            for i in row:
                if step == 0:
                    cv.itemconfigure(f"c{i}", state="normal")
                cv.move(f"c{i}", 0, -3.5)
            if step < 3:
                self.after(22, lambda: show(k, step + 1))
            if step == 1:
                self.after(10, lambda: show(k + 1, 0))
        show(0, 0)
