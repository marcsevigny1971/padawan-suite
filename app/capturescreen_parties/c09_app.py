# -*- coding: utf-8 -*-
"""CaptureScreen - c09 : fenetre principale (maximisee, sans intro) : gros boutons avec raccourcis et infobulles,
reglages defilants, bibliotheque, theme commun Padawan (🎨 Thème)."""
from __future__ import annotations

import os
import sys
import tkinter as tk
from tkinter import filedialog, ttk

from .c01_config import APP, PRESETS, QUALITY, VERSION, find_ffmpeg, load_cfg, logger, pick_encoder, save_cfg
from .c02_win32 import GlobalHotkeys, monitors
from .c03_audio import microphones, speakers
from .c05_overlays import ClickHalo, KeyBubble, Magnifier, ScreenTimer
from .c08_library import Library
from .c09b_actions import Actions
from .c11_archiveur import ArchiveurLink
from . import c14_tools_ui as tools_ui

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    import padawan_themes as themes
except Exception:  # pragma: no cover
    themes = None

PAL = {"BG": "#0f1724", "PANEL": "#16213a", "CARD": "#1c2a48", "TEXT": "#e8eefc", "DIM": "#9fb0d0", "ACC": "#3ad1c2",
       "ACC2": "#ffcc55", "ENTRY": "#0b1220", "BTN": "#24406e", "BTNH": "#2f5596", "DEEP": "#070b16", "REC": "#ff4d6d",
       "OK": "#55ff99", "LINE": "#2a3b63", "ONACC": "#06121f", "SEL": "#2f5597"}

HOTKEYS = [("rec", "R", "Enregistrer / Arrêter"), ("pause", "P", "Pause / Reprendre"), ("shot", "S", "Capture d'écran (zone)"),
           ("draw", "D", "Dessiner à l'écran"), ("spot", "L", "Projecteur"), ("zoom", "Z", "Loupe"),
           ("board", "B", "Tableau blanc / noir"), ("timer", "M", "Minuteur à l'écran"), ("mark", "K", "Repère (chapitre)")]


class App(Actions, ArchiveurLink):
    def __init__(self, root):
        self.root = root
        self.cfg = load_cfg()
        self.pal = dict(PAL)
        if themes:
            try:
                self.pal = themes.map_palette(PAL, themes.chosen("capturescreen"))
            except Exception:
                pass
        self.rec = self.bar = self.annot = self.border = None
        self.win_hwnd = None
        self.halo = ClickHalo(root)
        self.keyb = KeyBubble(root, self.rec_rect_or_screen, self.cfg.get("keys_shortcuts_only", True))
        self.mag = Magnifier(root, float(self.cfg.get("zoom") or 2.0))
        self.timer = ScreenTimer(root, int(self.cfg.get("timer_minutes") or 5), self.pal)
        self.spot = None
        self.hk = GlobalHotkeys()
        self.hk_label = "Ctrl+Maj" if self.cfg.get("hotkey_mods", "ctrl+shift") == "ctrl+shift" else "Ctrl+Alt+Maj"
        root.title(APP)
        root.configure(bg=self.pal["BG"])
        root.minsize(900, 560)
        try:
            if not getattr(root, "_cs_handoff", False):
                root.state("zoomed")
        except Exception:
            pass
        try:
            ico = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "capturescreen1.ico")
            if os.path.isfile(ico):
                root.iconbitmap(ico)
        except Exception:
            pass
        self._build()
        self._keys()
        self._start_hotkeys()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(50, self.lib.refresh)
        root.after(80, self._poll_hotkeys)
        root.after(300, self._check_ffmpeg)
        if not getattr(root, "_cs_handoff", False):
            root.after(900, self.check_leftovers)
        root.after(700, self._poll_requests)

    # ---------------------------------------------------------- petits outils d'interface
    def tip(self, w, text):
        st = {"t": None, "job": None}
        p = self.pal

        def show():
            st["job"] = None
            if st["t"] or not w.winfo_exists():
                return
            t = tk.Toplevel(w); t.overrideredirect(True); t.attributes("-topmost", True)
            tk.Label(t, text=text, bg="#ffffe0", fg="#000000", font=("Segoe UI", 10), relief="solid", bd=1, padx=6, pady=3,
                     justify="left", wraplength=420).pack()
            t.update_idletasks()
            x = min(w.winfo_rootx(), w.winfo_screenwidth() - t.winfo_reqwidth() - 8)
            t.geometry(f"+{max(0, x)}+{w.winfo_rooty() + w.winfo_height() + 4}")
            st["t"] = t

        def enter(e=None):
            if not st["job"]:
                st["job"] = w.after(450, show)

        def leave(e=None):
            if st["job"]:
                w.after_cancel(st["job"]); st["job"] = None
            if st["t"]:
                st["t"].destroy(); st["t"] = None
        w.bind("<Enter>", enter, add="+"); w.bind("<Leave>", leave, add="+"); w.bind("<ButtonPress>", leave, add="+")
        del p

    def button(self, parent, text, cmd, tip, side=None, small=False, big=False, bg=None, fg=None, grid=None):
        p = self.pal
        f = ("Segoe UI Emoji", 16 if big else (10 if small else 12), "bold")
        b = tk.Button(parent, text=text, command=cmd, bg=bg or p["BTN"], fg=fg or p["TEXT"], activebackground=p["BTNH"],
                      activeforeground=p["TEXT"], relief="flat", bd=0, font=f, cursor="hand2",
                      padx=14 if not small else 8, pady=(14 if big else (4 if small else 8)), anchor="w" if big else "center")
        if grid:
            b.grid(**grid)
        elif side:
            b.pack(side=side, padx=3)
        else:
            b.pack(side="left", padx=3)
        self.tip(b, tip)
        return b

    def section(self, parent, title):
        p = self.pal
        fr = tk.Frame(parent, bg=p["PANEL"], padx=12, pady=8)
        fr.pack(fill="x", pady=5, padx=(0, 6))
        tk.Label(fr, text=title, bg=p["PANEL"], fg=p["ACC"], font=("Segoe UI", 13, "bold")).pack(anchor="w", pady=(0, 4))
        return fr

    def check(self, parent, text, key, tip, cmd=None):
        p = self.pal
        v = tk.BooleanVar(value=bool(self.cfg.get(key)))

        def ch():
            self.cfg[key] = v.get(); save_cfg(self.cfg)
            if cmd:
                cmd()
        c = tk.Checkbutton(parent, text=text, variable=v, command=ch, bg=p["PANEL"], fg=p["TEXT"], selectcolor=p["ENTRY"],
                           activebackground=p["PANEL"], activeforeground=p["TEXT"], font=("Segoe UI", 11), anchor="w",
                           cursor="hand2")
        c.pack(fill="x")
        self.tip(c, tip)
        self.vars[key] = v
        return c

    def radios(self, parent, key, choices, tip, cmd=None):
        p = self.pal
        v = tk.StringVar(value=str(self.cfg.get(key)))
        row = tk.Frame(parent, bg=p["PANEL"]); row.pack(fill="x", pady=2)

        def ch():
            val = v.get()
            self.cfg[key] = int(val) if val.isdigit() else (float(val) if val.replace(".", "", 1).isdigit() else val)
            save_cfg(self.cfg)
            if cmd:
                cmd()
        for val, txt in choices:
            r = tk.Radiobutton(row, text=txt, value=str(val), variable=v, command=ch, indicatoron=False, bg=p["BTN"],
                               fg=p["TEXT"], selectcolor=p["SEL"], activebackground=p["BTNH"], relief="flat",
                               font=("Segoe UI", 11, "bold"), padx=10, pady=5, cursor="hand2")
            r.pack(side="left", padx=2)
            self.tip(r, tip)
        self.vars[key] = v
        return row

    def combo(self, parent, key, values, tip, width=34, empty="(par défaut)"):
        vals = [empty] + values
        v = tk.StringVar(value=self.cfg.get(key) or empty)
        cb = ttk.Combobox(parent, textvariable=v, values=vals, state="readonly", width=width, font=("Segoe UI", 10))
        cb.pack(anchor="w", padx=(26, 0), pady=(0, 4))

        def ch(e=None):
            self.cfg[key] = "" if v.get() == empty else v.get(); save_cfg(self.cfg)
        cb.bind("<<ComboboxSelected>>", ch)
        self.tip(cb, tip)
        return cb

    # ---------------------------------------------------------- construction
    def _build(self):
        p = self.pal
        self.vars = {}
        root = self.root
        head = tk.Frame(root, bg=p["DEEP"], padx=12, pady=8); head.pack(fill="x")
        tk.Label(head, text="\U0001f3a5 CaptureScreen", bg=p["DEEP"], fg=p["TEXT"], font=("Segoe UI", 20, "bold")).pack(side="left")
        tk.Label(head, text="  Enregistre ton écran pour enseigner : vidéo, son, souris, clavier, dessin.",
                 bg=p["DEEP"], fg=p["DIM"], font=("Segoe UI", 11)).pack(side="left")
        self.head = head
        self.button(head, "\u2753 Aide (F1)", self.show_help, "Mode d'emploi et tous les raccourcis", side="right")
        self.button(head, "\U0001f4c2 Dossier", lambda: os.startfile(self.cfg["out_dir"]) if os.path.isdir(self.cfg["out_dir"]) else None,
                    "Ouvrir le dossier des enregistrements", side="right")

        status = tk.Label(root, text="Prêt.", bg=p["DEEP"], fg=p["DIM"], font=("Segoe UI", 10), anchor="w", padx=10, pady=4)
        status.pack(side="bottom", fill="x")
        self._status = status

        body = tk.Frame(root, bg=p["BG"]); body.pack(fill="both", expand=True, padx=10, pady=8)
        # --- colonne de gauche (defilante)
        try:
            self.scale = max(1.0, float(root.winfo_fpixels("1i")) / 96.0)
        except Exception:
            self.scale = 1.0
        lw = int(min(600 * self.scale, root.winfo_screenwidth() * 0.48))
        left = tk.Frame(body, bg=p["BG"], width=lw); left.pack(side="left", fill="y")
        left.pack_propagate(False)
        cv = tk.Canvas(left, bg=p["BG"], highlightthickness=0, width=lw - 20)
        sb = tk.Scrollbar(left, command=cv.yview); sb.pack(side="right", fill="y")
        cv.configure(yscrollcommand=sb.set); cv.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(cv, bg=p["BG"]); wid = cv.create_window(0, 0, window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
        cv.bind("<Configure>", lambda e: cv.itemconfigure(wid, width=e.width))
        wheel = lambda e: cv.yview_scroll(int(-e.delta / 120) * 3, "units")
        for w in (cv, inner):
            w.bind("<Enter>", lambda e: cv.bind_all("<MouseWheel>", wheel))
            w.bind("<Leave>", lambda e: cv.unbind_all("<MouseWheel>"))
        self._build_left(inner)
        # --- bibliotheque
        right = tk.Frame(body, bg=p["BG"]); right.pack(side="left", fill="both", expand=True, padx=(10, 0))
        self.lib = Library(self, right)
        self.lib.frame.pack(fill="both", expand=True)
        if themes:
            try:
                themes.install(root, "capturescreen", PAL, button_parent=head, on_change=self._theme_changed)
            except Exception:
                logger.exception("themes")

    def _tile(self, parent, col, src, icon, title, sub, tip):
        p = self.pal
        fr = tk.Frame(parent, bg=p["CARD"], highlightthickness=3, highlightbackground=p["CARD"], cursor="hand2")
        fr.grid(row=0, column=col, sticky="nsew", padx=4, pady=4)
        a = tk.Label(fr, text=icon, bg=p["CARD"], fg=p["TEXT"], font=("Segoe UI Emoji", 30))
        b = tk.Label(fr, text=title, bg=p["CARD"], fg=p["TEXT"], font=("Segoe UI", 13, "bold"))
        c = tk.Label(fr, text=sub, bg=p["CARD"], fg=p["DIM"], font=("Segoe UI", 9), wraplength=150)
        a.pack(pady=(10, 0)); b.pack(); c.pack(pady=(0, 10), padx=6)
        for w in (fr, a, b, c):
            w.bind("<Button-1>", lambda e: self.set_source(src))
            self.tip(w, tip)
        self.tiles[src] = fr

    def _mark_tiles(self):
        cur = self.cfg.get("source")
        cur = "ecran" if cur == "moniteur" else cur
        for k, fr in getattr(self, "tiles", {}).items():
            fr.configure(highlightbackground=self.pal["ACC"] if k == cur else self.pal["CARD"])

    def _toggle(self, parent, text, key, tip, cmd=None):
        """Gros interrupteur simple (case a cocher en bouton)."""
        p = self.pal
        v = tk.BooleanVar(value=bool(self.cfg.get(key)))

        def ch():
            self.cfg[key] = v.get(); save_cfg(self.cfg); paint()
            if cmd:
                cmd()
        b = tk.Checkbutton(parent, text=text, variable=v, command=ch, indicatoron=False, relief="flat",
                           font=("Segoe UI Emoji", 12, "bold"), padx=12, pady=10, cursor="hand2", anchor="w",
                           bg=p["BTN"], fg=p["TEXT"], selectcolor=p["SEL"], activebackground=p["BTNH"])

        def paint():
            b.configure(text=("\u2705 " if v.get() else "\u2b1c ") + text)
        paint()
        self.tip(b, tip)
        self.vars[key] = v
        return b

    def _build_left(self, f):
        p, hk = self.pal, self.hk_label
        self.tiles = {}
        top = tk.Frame(f, bg=p["BG"]); top.pack(fill="x", padx=(0, 6))
        self.brec = self.button(top, f"\u25cf  Enregistrer\n{hk}+R", self.toggle_record,
                                "Démarre l'enregistrement : compte à rebours, puis la fenêtre se cache.\n"
                                f"{hk}+R (ou \u23f9 dans la petite barre) arrête et sauve la vidéo.", big=True,
                                bg=p["REC"], fg="#ffffff", grid=None)
        self.brec.configure(font=("Segoe UI", 20, "bold"), pady=12, anchor="center", justify="center")
        self.brec.pack_forget(); self.brec.pack(fill="x", pady=(0, 8))

        tk.Label(f, text="Quoi enregistrer ?", bg=p["BG"], fg=p["ACC"], font=("Segoe UI", 13, "bold")).pack(anchor="w")
        tl = tk.Frame(f, bg=p["BG"]); tl.pack(fill="x", padx=(0, 6))
        for i in range(4):
            tl.columnconfigure(i, weight=1)
        self._tile(tl, 0, "ecran", "\U0001f5a5", "Écran complet", "Tout ce que tu vois", "Tout l'écran où se trouve la souris")
        self._tile(tl, 1, "fenetre", "\U0001fa9f", "Fenêtre", "Un seul programme", "Choisis une fenêtre (liste ou clic dessus)")
        self._tile(tl, 2, "zone", "\u25ad", "Zone", "Un rectangle tracé", "Trace une zone à la souris")
        self._tile(tl, 3, "son", "\U0001f3a4", "Son seulement", "Cours, balado", "Pas d'image : seulement le son de l'ordi et/ou "
                   "le micro (fichier M4A ou MP3)")
        self.src_lab = tk.Label(f, text="", bg=p["BG"], fg=p["ACC2"], font=("Segoe UI", 10), anchor="w", justify="left",
                                wraplength=500)
        self.src_lab.pack(fill="x", pady=(0, 6))

        tk.Label(f, text="Avec :", bg=p["BG"], fg=p["ACC"], font=("Segoe UI", 13, "bold")).pack(anchor="w")
        tg = tk.Frame(f, bg=p["BG"]); tg.pack(fill="x", padx=(0, 6))
        tg.columnconfigure(0, weight=1); tg.columnconfigure(1, weight=1)
        for i, (txt, key, tp, cmd) in enumerate((
                ("\U0001f50a Son de l'ordi", "sys_audio", "Ce que tu entends : vidéos, musique, sons des programmes", None),
                ("\U0001f3a4 Micro", "mic", "Ta voix pour expliquer", None),
                ("\U0001f4f7 Webcam", "webcam", "Ta caméra en petite vignette dans le coin", None),
                ("\u2328 Afficher les touches", "keys", "Les raccourcis (Ctrl+C, Alt+Tab…) apparaissent dans une bulle.\n"
                 "Rien n'est jamais écrit sur le disque.", None))):
            self._toggle(tg, txt, key, tp, cmd).grid(row=i // 2, column=i % 2, sticky="ew", padx=3, pady=3)

        tk.Label(f, text="Outils à l'écran :", bg=p["BG"], fg=p["ACC"],
                 font=("Segoe UI", 13, "bold")).pack(anchor="w", pady=(10, 0))
        act = tk.Frame(f, bg=p["BG"]); act.pack(fill="x", padx=(0, 6))
        for i in range(3):
            act.columnconfigure(i, weight=1)
        tools = [("\U0001f4f7 Capture", "S", lambda: self.screenshot("zone"),
                  "Image PNG d'une zone (Entrée = écran entier), aussi copiée : colle avec Ctrl+V"),
                 ("\u270f Dessiner", "D", self.toggle_draw, "Crayon, surligneur, flèches, cadres, texte, gomme"),
                 ("\u2b1c Tableau", "B", self.toggle_board, "Tableau blanc / noir / vert plein écran pour écrire"),
                 ("\U0001f526 Projecteur", "L", self.toggle_spot, "Assombrit tout sauf autour de la souris"),
                 ("\U0001f50d Loupe", "Z", self.toggle_zoom, "Une loupe suit la souris"),
                 ("\u23f1 Minuteur", "M", self.toggle_timer, "Compte à rebours ou chrono à l'écran")]
        for i, (t, k, c, tp) in enumerate(tools):
            b = self.button(act, f"{t}\n{hk}+{k}", c, f"{tp}\nRaccourci : {hk}+{k}", small=True,
                            grid=dict(row=i // 3, column=i % 3, sticky="ew", padx=2, pady=2))
            b.configure(pady=6, justify="center")

        # ---- reglages avances (caches)
        self.adv_open = False
        self.adv_btn = self.button(f, "\u2699 Réglages avancés  \u25b8", self._toggle_adv,
                                   "Moniteur, haut-parleurs, micro, images/s, qualité, effets, dossier, raccourcis…", small=True)
        self.adv_btn.pack_forget(); self.adv_btn.pack(anchor="w", pady=(12, 4))
        self.adv = tk.Frame(f, bg=p["BG"])
        self._build_advanced(self.adv)
        self.adv_end = tk.Label(f, text=f"{APP} {VERSION} · Projet Padawan", bg=p["BG"], fg=p["DIM"], font=("Segoe UI", 9))
        self.adv_end.pack(pady=8)
        self._source_changed()

    def _toggle_adv(self):
        self.adv_open = not self.adv_open
        if self.adv_open:
            self.adv.pack(fill="x", before=self.adv_end)
        else:
            self.adv.pack_forget()
        self.adv_btn.configure(text="\u2699 Réglages avancés  " + ("\u25be" if self.adv_open else "\u25b8"))

    def _build_advanced(self, f):
        p = self.pal
        s = self.section(f, "\u2728 Préréglages")
        row = tk.Frame(s, bg=p["PANEL"]); row.pack(fill="x")
        for k, pr in PRESETS.items():
            self.button(row, pr["label"], lambda k=k: self.apply_preset(k), pr["tip"], small=True)

        s = self.section(f, "\U0001f3af Écran")
        self.radios(s, "source", [("ecran", "Écran de la souris"), ("moniteur", "Moniteur choisi :")],
                    "Avec plusieurs écrans : lequel enregistrer", cmd=self._source_changed)
        mons = monitors()
        self.mon_cb = ttk.Combobox(s, values=[m["label"] for m in mons], state="readonly", width=40, font=("Segoe UI", 10))
        self.mon_cb.current(min(int(self.cfg.get("monitor") or 0), len(mons) - 1))
        self.mon_cb.bind("<<ComboboxSelected>>", lambda e: (self.cfg.update(monitor=self.mon_cb.current()), save_cfg(self.cfg),
                                                            self._source_changed()))
        self.mon_cb.pack(anchor="w", pady=3)
        self.tip(self.mon_cb, "Le moniteur à enregistrer")
        self.check(s, "\U0001f5b1 Pointeur de souris visible", "cursor", "Dessine la flèche de la souris dans la vidéo")
        self.check(s, "\U0001f7e1 Halo de couleur sur les clics (gauche jaune, droit rouge)", "clicks", "Les élèves voient où tu cliques")
        self.check(s, "\U0001f512 Touches : seulement les raccourcis (jamais les lettres tapées)", "keys_shortcuts_only",
                   "Recommandé : tes mots de passe et textes tapés ne s'affichent pas",
                   cmd=lambda: setattr(self.keyb, "shortcuts_only", self.cfg["keys_shortcuts_only"]))
        self.check(s, "\U0001f648 Cacher la petite barre de contrôle dans la vidéo", "hide_bar",
                   "La barre reste visible pour toi mais pas dans la vidéo")
        tk.Label(s, text="Compte à rebours avant de commencer :", bg=p["PANEL"], fg=p["TEXT"], font=("Segoe UI", 11)).pack(anchor="w")
        self.radios(s, "countdown", [(0, "Aucun"), (3, "3 s"), (5, "5 s")], "Le temps de te préparer")

        s = self.section(f, "\U0001f50a Son et caméra")
        tk.Label(s, text="Haut-parleurs écoutés :", bg=p["PANEL"], fg=p["TEXT"], font=("Segoe UI", 11)).pack(anchor="w")
        self.combo(s, "speaker", speakers(), "Par défaut = ceux de Windows")
        mics = microphones()
        tk.Label(s, text="Micro :", bg=p["PANEL"], fg=p["TEXT"], font=("Segoe UI", 11)).pack(anchor="w")
        self.combo(s, "mic_name", mics, "Micro à utiliser", empty="(par défaut)" if mics else "(aucun micro détecté)")
        tk.Label(s, text="Caméra :", bg=p["PANEL"], fg=p["TEXT"], font=("Segoe UI", 11)).pack(anchor="w")
        self.cam_cb = self.combo(s, "webcam_name", [], "Caméra à utiliser", empty="(aucune caméra détectée)")
        self.root.after(1200, self._load_cams)
        row = tk.Frame(s, bg=p["PANEL"]); row.pack(fill="x", pady=3)
        self.button(row, "\U0001f508 Tester le son (2 s)", self.test_sound, "Vérifie que le son et le micro arrivent bien", small=True)
        self.snd_lab = tk.Label(s, text="", bg=p["PANEL"], fg=p["DIM"], font=("Segoe UI", 10), anchor="w", wraplength=480,
                                justify="left")
        self.snd_lab.pack(fill="x")

        s = self.section(f, "\U0001f3ac Vidéo")
        self.radios(s, "fps", [(15, "15 images/s"), (30, "30 images/s"), (60, "60 images/s")],
                    "30 pour un cours · 60 pour des mouvements rapides (jeux) · 15 pour de tout petits fichiers")
        self.radios(s, "quality", [(k, v[0].split(" (")[0]) for k, v in QUALITY.items()],
                    "Haute = très net, fichiers plus gros · Bonne = recommandé · Légère = petits fichiers")
        self.enc_lab = tk.Label(s, text="", bg=p["PANEL"], fg=p["DIM"], font=("Segoe UI", 9), anchor="w"); self.enc_lab.pack(fill="x")
        tk.Label(s, text="Sauvegarde de sécurité pendant l'enregistrement : un morceau toutes les",
                 bg=p["PANEL"], fg=p["TEXT"], font=("Segoe UI", 10), anchor="w").pack(fill="x")
        self.radios(s, "segment_minutes", [(2, "2 min"), (5, "5 min"), (10, "10 min")],
                    "Si le PC plante, tu perds au pire quelques secondes : les morceaux sont récupérés au prochain lancement")

        s = self.section(f, "\U0001f393 Outils")
        tk.Label(s, text="Loupe :", bg=p["PANEL"], fg=p["TEXT"], font=("Segoe UI", 11)).pack(anchor="w")
        self.radios(s, "zoom", [(1.5, "×1,5"), (2.0, "×2"), (3.0, "×3")], "Grossissement de la loupe",
                    cmd=lambda: setattr(self.mag, "zoom", float(self.cfg["zoom"])))
        tk.Label(s, text="Projecteur :", bg=p["PANEL"], fg=p["TEXT"], font=("Segoe UI", 11)).pack(anchor="w")
        self.radios(s, "spot_radius", [(100, "Petit"), (150, "Moyen"), (230, "Grand")], "Taille du cercle éclairé")
        tk.Label(s, text="Minuteur :", bg=p["PANEL"], fg=p["TEXT"], font=("Segoe UI", 11)).pack(anchor="w")
        self.radios(s, "timer_minutes", [(1, "1 min"), (5, "5 min"), (10, "10 min"), (15, "15 min")], "Durée du compte à rebours",
                    cmd=lambda: setattr(self.timer, "minutes", int(self.cfg["timer_minutes"])))
        tk.Label(s, text="Tableau :", bg=p["PANEL"], fg=p["TEXT"], font=("Segoe UI", 11)).pack(anchor="w")
        self.radios(s, "board_color", [("blanc", "\u2b1c Blanc"), ("noir", "\u2b1b Noir"), ("vert", "\U0001f7e9 Vert")],
                    "Couleur du tableau")

        s = self.section(f, "\u23f0 Programmer et durée")
        tk.Label(s, text="Arrêter tout seul après :", bg=p["PANEL"], fg=p["TEXT"], font=("Segoe UI", 11)).pack(anchor="w")
        self.radios(s, "auto_stop_min", [(0, "Jamais"), (15, "15 min"), (30, "30 min"), (60, "1 h"), (90, "1 h 30")],
                    "Pratique pour un cours d'une durée fixe (les pauses ne comptent pas)")
        row = tk.Frame(s, bg=p["PANEL"]); row.pack(fill="x", pady=3)
        self.button(row, "\u23f0 Programmer un enregistrement…", lambda: tools_ui.schedule_dialog(self),
                    "Démarrer tout seul à une heure (ex. : 14:00) et arrêter après une durée", small=True)
        self.sched_lab = tk.Label(s, text="", bg=p["PANEL"], fg=p["ACC2"], font=("Segoe UI", 10, "bold"), anchor="w")
        self.sched_lab.pack(fill="x")
        tk.Label(s, text="Son seulement, format :", bg=p["PANEL"], fg=p["TEXT"], font=("Segoe UI", 11)).pack(anchor="w")
        self.radios(s, "audio_fmt", [("m4a", "M4A (petit, recommandé)"), ("mp3", "MP3 (lu partout)")],
                    "Format du fichier quand tu choisis « Son seulement »", cmd=self._source_changed)
        tk.Label(s, text="Bulle webcam :", bg=p["PANEL"], fg=p["TEXT"], font=("Segoe UI", 11)).pack(anchor="w")
        self.radios(s, "cam_pos", [("bd", "\u2198 Bas droite"), ("bg", "\u2199 Bas gauche"), ("hd", "\u2197 Haut droite"),
                                   ("hg", "\u2196 Haut gauche")], "Coin de la vidéo où apparaît ta webcam")
        self.radios(s, "cam_size", [("petite", "Petite"), ("moyenne", "Moyenne"), ("grande", "Grande")], "Taille de la bulle webcam")

        s = self.section(f, "\U0001f4c1 Où ranger les vidéos")
        self.out_lab = tk.Label(s, text=self.cfg["out_dir"], bg=p["PANEL"], fg=p["TEXT"], font=("Segoe UI", 10), anchor="w",
                                wraplength=480, justify="left")
        self.out_lab.pack(fill="x")
        self.free_lab = tk.Label(s, text="", bg=p["PANEL"], fg=p["DIM"], font=("Segoe UI", 9), anchor="w")
        self.free_lab.pack(fill="x")
        row = tk.Frame(s, bg=p["PANEL"]); row.pack(fill="x", pady=3)
        self.button(row, "\U0001f4c1 Changer…", self.change_out, "Choisir un autre dossier", small=True)

        s = self.section(f, "\u2328 Raccourcis globaux (marchent même fenêtre cachée)")
        self.radios(s, "hotkey_mods", [("ctrl+shift", "Ctrl+Maj+lettre"), ("ctrl+alt+shift", "Ctrl+Alt+Maj+lettre")],
                    "Si un autre logiciel utilise déjà Ctrl+Maj+R/P/S…, prends Ctrl+Alt+Maj", cmd=self._restart_hotkeys)
        tk.Label(s, text="Quand je n'enregistre pas :", bg=p["PANEL"], fg=p["TEXT"], font=("Segoe UI", 10), anchor="w").pack(fill="x")
        self.radios(s, "hotkeys_idle", [("rec", "Seulement Enregistrer"), ("all", "Tous"), ("none", "Aucun")],
                    "Seulement Enregistrer (conseillé) : les autres touches (Ctrl+Maj+S, D, B…) restent aux autres logiciels\n"
                    "tant que tu n'enregistres pas. Aucun : Ctrl+Maj+R recharge la page du navigateur comme d'habitude\n"
                    "(tu démarres avec le gros bouton). Tous : pour enseigner en direct sans enregistrer.",
                    cmd=self.hotkeys_refresh)
        self.hk_lab = tk.Label(s, text="", bg=p["PANEL"], fg=p["DIM"], font=("Segoe UI", 9), anchor="w", justify="left",
                               wraplength=480)
        self.hk_lab.pack(fill="x")

    def _keys(self):
        r = self.root
        r.bind("<F1>", lambda e: self.show_help())
        r.bind("<F5>", lambda e: self.lib.refresh())
        r.bind("<F2>", lambda e: self.lib.key_rename())
        r.bind("<Delete>", lambda e: None if isinstance(e.widget, (tk.Entry, ttk.Entry)) else self.lib.key_delete())
        r.bind("<Return>", lambda e: None if isinstance(e.widget, (tk.Entry, ttk.Entry)) else self.lib.key_open())

    # ---------------------------------------------------------- raccourcis globaux
    def _hk_wanted(self):
        """Pendant un enregistrement : tous les raccourcis. Sinon (reglage) : seulement Enregistrer, tous ou aucun,
        pour ne pas voler Ctrl+Maj+S (Enregistrer sous), Ctrl+Maj+D, Ctrl+Maj+B… aux autres logiciels."""
        if self.rec is not None or getattr(self, "_starting", False):
            return list(HOTKEYS)
        mode = self.cfg.get("hotkeys_idle", "rec")
        return list(HOTKEYS) if mode == "all" else ([h for h in HOTKEYS if h[0] == "rec"] if mode == "rec" else [])

    def hotkeys_refresh(self):
        want = tuple(n for n, _k, _d in self._hk_wanted())
        if want == getattr(self, "_hk_set", None):
            return
        try:
            self.hk.stop()
        except Exception:
            pass
        self._start_hotkeys()

    def _start_hotkeys(self):
        mods = self.cfg.get("hotkey_mods", "ctrl+shift")
        self.hk_label = "Ctrl+Maj" if mods == "ctrl+shift" else "Ctrl+Alt+Maj"
        keys = self._hk_wanted()
        self._hk_set = tuple(n for n, _k, _d in keys)
        self.hk = GlobalHotkeys()
        self.hk.start([(n, mods, k) for n, k, _d in keys])
        txt = "  ·  ".join(f"{self.hk_label}+{k} {d}" for n, k, d in HOTKEYS)
        mode = self.cfg.get("hotkeys_idle", "rec")
        txt += "\n" + {"rec": f"Hors enregistrement, seul {self.hk_label}+R est pris (les autres restent aux autres logiciels).",
                       "none": "Hors enregistrement, aucune touche n'est prise : démarre avec le gros bouton.",
                       "all": "Tous les raccourcis sont actifs, même sans enregistrer."}.get(mode, "")
        if self.hk.failed:
            txt += "\n\u26a0 Déjà pris par un autre logiciel : " + ", ".join(
                f"{self.hk_label}+{k}" for n, k, _d in HOTKEYS if n in self.hk.failed) + " (les boutons marchent quand même)"
        try:
            self.hk_lab.configure(text=txt)
        except Exception:
            pass

    def _restart_hotkeys(self):
        self.hk.stop()
        self._hk_set = None
        self.root.after(50, self._start_hotkeys)
        self.status("\u2328 Raccourcis changés (les étiquettes des boutons suivent au prochain lancement).")

    def _poll_hotkeys(self):
        try:
            while True:
                name = self.hk.q.get_nowait()
                {"rec": self.toggle_record, "pause": self.toggle_pause, "shot": self.hotkey_shot, "draw": self.toggle_draw,
                 "spot": self.toggle_spot, "zoom": self.toggle_zoom, "board": self.toggle_board,
                 "timer": self.toggle_timer, "mark": self.hotkey_marker}.get(name, lambda: None)()
        except Exception:
            pass
        self.root.after(60, self._poll_hotkeys)

    # ---------------------------------------------------------- divers
    def status(self, msg):
        try:
            self._status.configure(text=msg)
        except Exception:
            pass
        logger.info("%s", msg)

    def _theme_changed(self, key):
        if themes:
            self.pal = themes.map_palette(PAL, key)
            self.timer.pal = self.pal
            self.lib.p = self.pal
            self.lib.refresh()

    def _check_ffmpeg(self):
        ff = find_ffmpeg()
        if not ff:
            self.status("\u26a0 L'outil vidéo n'est pas encore installé : ouvre l'Archiveur une fois (il s'installe tout seul) ou lance le Setup Padawan.")
            self.brec.configure(state="disabled")
            return
        import threading

        def go():
            enc = pick_encoder(ff, self.cfg.get("encoder", "auto"))
            lab = "par la carte graphique (rapide, léger pour le PC)" if enc == "h264_nvenc" else "par le processeur"
            import shutil as _sh
            try:
                fr = _sh.disk_usage(self.cfg["out_dir"] if os.path.isdir(self.cfg["out_dir"]) else "C:\\").free
            except Exception:
                fr = 0
            from .c01_config import human_size as _hs
            per_h = {"haute": 2.5, "bonne": 1.2, "legere": 0.6}.get(self.cfg.get("quality"), 1.2) * (self.cfg.get("fps", 30) / 30)
            def put():
                self.enc_lab.configure(text=f"Vidéo MP4 qui s'ouvre partout · encodée {lab}")
                self.free_lab.configure(text=f"Espace libre : {_hs(fr)} · environ 0,3 à {per_h:.1f} Go par heure "
                                             "(selon ce qui bouge à l'écran)".replace(".", ","))
            self.root.after(0, put)
        threading.Thread(target=go, daemon=True).start()

    def _load_cams(self):
        import threading
        from .c04_recorder import list_webcams

        def go():
            cams = list_webcams()
            def put():
                if cams:
                    self.cam_cb.configure(values=["(par défaut)"] + cams)
                    if not self.cfg.get("webcam_name"):
                        self.cam_cb.set(cams[0]); self.cfg["webcam_name"] = cams[0]
            self.root.after(0, put)
        threading.Thread(target=go, daemon=True).start()

    def change_out(self):
        d = filedialog.askdirectory(title="Dossier des enregistrements", initialdir=self.cfg["out_dir"], parent=self.root)
        if d:
            self.cfg["out_dir"] = os.path.normpath(d); save_cfg(self.cfg)
            self.out_lab.configure(text=self.cfg["out_dir"]); self.lib.refresh()


def _ui_test(app):
    """Test automatique des outils (sans souris) : dessin + tableau, projecteur, loupe, minuteur, bulle, halo,
    puis un vrai enregistrement de 4 s par l'interface (barre flottante comprise) dans un dossier test."""
    import time as _t
    from .c01_config import TMP_DIR
    r, steps = app.root, []
    test_dir = os.path.join(TMP_DIR, "_test_ui")
    app.cfg.update(out_dir=test_dir, countdown=0, source="ecran")

    def log(m):
        print("  UI:", m, flush=True)

    def s1():
        app.toggle_draw(); a = app.annot
        a.ci.create_line(100, 100, 600, 300, fill="#ff3b30", width=6); a.set_tool("arrow"); a.set_tool("hl")
        a.ch.create_line(100, 400, 700, 400, fill="#ffd400", width=24)
        a.set_board("blanc"); log("dessin + tableau blanc ouverts")
    def s2():
        try:
            from PIL import ImageGrab
            x, y, w, h = app.annot.rect
            ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True).resize((w // 3, h // 3)).save(
                os.path.join(os.environ.get("TEMP", "."), "cs_shot_board.png"))
        except Exception as e:
            log(f"capture tableau : {e}")
        app.annot.set_board("noir"); app.annot.do_undo(); app.annot.clear(); app.annot.close(); log("dessin fermé")
    def s3():
        app.toggle_spot(); log(f"projecteur actif={app.spot.active}")
    def s4():
        app.toggle_spot(); app.toggle_zoom(); log(f"loupe active={app.mag.active}")
    def s5():
        app.toggle_zoom(); app.toggle_timer(); app.keyb._show("Ctrl + Maj + S"); app.halo._ring("#ffd400")
        log(f"minuteur actif={app.timer.active}, bulle, halo")
    def s6():
        app.toggle_timer(); app.keyb._hide(); app.start_recording(); log("enregistrement par l'interface…")
    def s7():
        if app.rec is None:
            log("ÉCHEC : l'enregistrement n'a pas démarré"); return
        log(f"barre flottante={app.bar is not None and app.bar.win is not None}, cachée de la vidéo={app.bar.hidden_ok}, "
            f"temps={app.rec.elapsed():.1f}s, taille={app.rec.size()}")
        app.toggle_pause()
    def s8():
        log(f"état={app.rec.state if app.rec else '?'}"); app.toggle_pause()
    def s9():
        app.stop_recording(); log("arrêt demandé")
    def s10():
        vids = [f for f in os.listdir(test_dir)] if os.path.isdir(test_dir) else []
        log(f"fichiers produits : {vids}")
        from .c04_recorder import probe_duration
        for f in vids:
            log(f"  {f} : {probe_duration(os.path.join(test_dir, f)):.2f} s")
            os.remove(os.path.join(test_dir, f))
        try:
            os.rmdir(test_dir)
        except OSError:
            pass
        log("fini"); app.hk.stop(); r.destroy()
    t = 0
    for fn, wait in ((s1, 0), (s2, 1500), (s3, 1500), (s4, 1500), (s5, 1500), (s6, 1500), (s7, 5000), (s8, 1500),
                     (s9, 2500), (s10, 8000)):
        t += wait
        r.after(t, fn)


def run_app(smoke=0.0, shot="", shot_view="", request=None):
    root = tk.Tk()
    if request:
        root.withdraw()  # lance depuis l'Archiveur : pas de grande fenetre, juste l'enregistrement
        root._cs_handoff = True
    app = App(root)
    if request:
        root.withdraw()
        root.after(500, lambda: app.handle_request(request, fresh=True))
    if smoke or shot:
        def end():
            if shot:
                try:
                    from PIL import ImageGrab
                    root.update()
                    x, y, w, h = root.winfo_rootx(), root.winfo_rooty(), root.winfo_width(), root.winfo_height()
                    ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True).save(shot)
                except Exception as e:
                    print("capture impossible :", e)
            app.hk.stop()
            root.destroy()
        if shot_view == "avance":
            root.after(500, app._toggle_adv)
        if shot_view == "outils":
            root.after(600, lambda: _ui_test(app))
            smoke = max(smoke, 40)
        if shot_view == "aide":
            root.after(800, app.show_help)
        root.after(int((smoke or 3) * 1000), end)
    root.mainloop()
    return 0
