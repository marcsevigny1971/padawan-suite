# -*- coding: utf-8 -*-
"""
padawan_themes - themes communs de la suite Padawan (v1.2.3).

Reprend les themes du Journal de bord (Cosmos, Papier, Nuit douce, Foret) et les offre
a tous les programmes, plus « Original » (le look propre de chaque programme, par defaut).

- Reglage partage : %APPDATA%\\Padawan\\themes.json  {"suite": "", "apps": {"grimoire": "nuit", ...}}
  (le choix d'un programme passe avant le choix « toute la suite »).
- Changement en direct : les couleurs des fenetres ouvertes sont remplacees couleur par couleur
  (widgets Tk, items de Canvas, styles de texte). Ce qui ne peut pas changer en direct (ex. certains
  elements ttk) suit au prochain lancement : un message le dit.
- Dans chaque programme : menu ou bouton « 🎨 Thème » + raccourci Ctrl+Maj+T.
- Test : PADAWAN_THEME_TEST="cle|capture.png|delai_ms" applique le theme, capture la fenetre et ferme.
"""
from __future__ import annotations

import json
import os
import sys

THEME_ORDER = ["original", "cosmos", "papier", "nuit", "foret"]
LABELS = {
    "original": "\u2728 Original (le look de ce programme)",
    "cosmos": "\U0001f30c Cosmos (classique)",
    "papier": "\U0001f4dc Papier (clair, doux pour les yeux)",
    "nuit": "\U0001f319 Nuit douce (sombre, chaleureux)",
    "foret": "\U0001f332 For\u00eat (nature, apaisant)",
}
# memes couleurs que journal_bord.py (Cosmos = couleurs communes padawan_commun.C + ajouts du Journal)
PALETTES = {
    "cosmos": {"BG": "#0f1724", "PANEL": "#16213a", "CARD": "#1c2a48", "TEXT": "#e8eefc", "DIM": "#9fb0d0",
               "ACC": "#3ad1c2", "ACC2": "#ffcc55", "ENTRY": "#0b1220", "BTN": "#24406e", "BTNH": "#2f5596",
               "DEEP": "#070b16", "REC": "#ff4d6d", "OK": "#55ff99", "WAX": "#b3263a", "WAX2": "#e0485c",
               "LINE": "#2a3b63", "ONACC": "#06121f", "SEL": "#2f5597"},
    "papier": {"BG": "#f7f1e3", "PANEL": "#efe6d2", "CARD": "#fffaf0", "TEXT": "#2b2419", "DIM": "#7a6a55",
               "ACC": "#9a5b1e", "ACC2": "#b2452e", "ENTRY": "#fffdf7", "BTN": "#e6d9bf", "BTNH": "#d8c39b",
               "LINE": "#cdbb98", "DEEP": "#3a2f22", "OK": "#2e7d32", "REC": "#c62828", "WAX": "#a3263a",
               "WAX2": "#cf4a5c", "ONACC": "#fffef9", "SEL": "#f0d9a8"},
    "nuit": {"BG": "#1e1b24", "PANEL": "#26222e", "CARD": "#2f2a39", "TEXT": "#ece6f2", "DIM": "#a99fb8",
             "ACC": "#c9a7ff", "ACC2": "#ffb38a", "ENTRY": "#17151c", "BTN": "#3a3347", "BTNH": "#4b4160",
             "LINE": "#3d3550", "DEEP": "#0d0b12", "OK": "#8fe3a8", "REC": "#ff6b81", "WAX": "#a8243a",
             "WAX2": "#d9475b", "ONACC": "#1a1424", "SEL": "#5a4a78"},
    "foret": {"BG": "#14201a", "PANEL": "#1a2a21", "CARD": "#22362b", "TEXT": "#e9f2e6", "DIM": "#a7bfa9",
              "ACC": "#7fd18b", "ACC2": "#f2c46d", "ENTRY": "#0f1914", "BTN": "#2b4535", "BTNH": "#3a5c46",
              "LINE": "#30503c", "DEEP": "#08110c", "OK": "#b6f5bd", "REC": "#ff7a6b", "WAX": "#8c2f2f",
              "WAX2": "#c0504d", "ONACC": "#0c1a10", "SEL": "#3f6b4f"},
}

# role commun pour les noms de couleurs utilises dans la suite (insensible a la casse)
ROLES = {
    "bg": "BG", "bg2": "BG", "fond": "BG", "panel": "PANEL", "panel2": "PANEL", "panel3": "CARD",
    "card": "CARD", "card2": "CARD", "card_fav": "BTN", "row": "PANEL", "row_alt": "CARD", "them": "CARD",
    "text": "TEXT", "ink": "TEXT", "fg_text": "TEXT", "btn_fg": "TEXT", "btnfg": "TEXT", "entry_fg": "TEXT",
    "on_sel": "TEXT", "cursor": "TEXT", "logfg": "TEXT", "fg": "ACC",
    "dim": "DIM", "mut": "DIM", "disabled": "DIM", "quote": "DIM", "skel": "DIM",
    "acc": "ACC", "teal": "ACC", "cyan": "ACC", "link": "ACC", "hi_act": "ACC", "flash": "BTNH",
    "acc2": "ACC2", "hi": "ACC2", "gold": "ACC2", "accent": "ACC2", "warn": "ACC2", "ref": "ACC2", "priv": "ACC2",
    "on_hi": "ONACC", "onacc": "ONACC",
    "entry": "ENTRY", "entry_bg": "ENTRY", "input": "ENTRY", "code_bg": "ENTRY", "logbg": "DEEP",
    "btn": "BTN", "me": "BTN", "btnh": "BTNH", "hover": "BTNH",
    "sel": "SEL", "sel_bg": "SEL", "cursor_bg": "SEL", "cursor_sel_bg": "SEL", "mark": "SEL",
    "line": "LINE", "sash": "LINE",
    "ok": "OK", "pub": "OK", "err": "REC", "bad": "REC", "rec": "REC",
    "img_bg": "DEEP", "deep": "DEEP", "wax": "WAX", "wax2": "WAX2",
}
COLOR_OPTS = ("background", "foreground", "activebackground", "activeforeground", "highlightbackground",
              "highlightcolor", "insertbackground", "selectbackground", "selectforeground", "troughcolor",
              "disabledforeground", "readonlybackground", "selectcolor", "disabledbackground", "inactiveselectbackground")
ITEM_OPTS = ("fill", "outline", "activefill", "activeoutline", "disabledfill")
TAG_OPTS = ("background", "foreground", "selectbackground", "selectforeground", "underlinefg", "overstrikefg")


def settings_path() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "Padawan", "themes.json")


def load() -> dict:
    try:
        with open(settings_path(), encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict):
            d.setdefault("suite", ""); d.setdefault("apps", {})
            return d
    except Exception:
        pass
    return {"suite": "", "apps": {}}


def save(d: dict) -> bool:
    p = settings_path()
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
        os.replace(tmp, p)
        return True
    except Exception:
        return False


def chosen(app: str) -> str:
    d = load()
    k = d.get("apps", {}).get(app) or d.get("suite") or "original"
    return k if k in THEME_ORDER else "original"


def set_choice(app: str, key: str) -> None:
    d = load(); d.setdefault("apps", {})[app] = key; save(d)


def set_suite(key: str) -> None:
    """Toute la suite : efface les choix par programme et applique aussi au Journal de bord."""
    d = load(); d["suite"] = "" if key == "original" else key; d["apps"] = {}; save(d)
    try:  # le Journal garde son propre reglage (journal.json) : on le met d'accord
        jp = os.path.join(os.path.dirname(settings_path()), "journal.json")
        js = {}
        if os.path.isfile(jp):
            with open(jp, encoding="utf-8") as f:
                js = json.load(f)
        js["theme"] = "cosmos" if key == "original" else key
        tmp = jp + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(js, f, ensure_ascii=False, indent=1)
        os.replace(tmp, jp)
    except Exception:
        pass


def _norm(c) -> str:
    c = str(c or "").strip().lower()
    if len(c) == 4 and c.startswith("#"):
        c = "#" + "".join(ch * 2 for ch in c[1:])
    return c


def _lum(c):
    try:
        c = _norm(c)
        r, g, b = (int(c[i:i + 2], 16) / 255 for i in (1, 3, 5))
    except Exception:
        return None
    f = lambda x: x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def _contrast(a, b):
    la, lb = _lum(a), _lum(b)
    if la is None or lb is None:
        return 99
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _mix(c1, c2, t):
    a = [int(_norm(c1)[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(_norm(c2)[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{int(a[k] + (b[k] - a[k]) * t):02x}" for k in range(3))


def readable(fg, bg, text):
    """Garde la teinte mais rapproche du texte du theme si illisible sur le fond (ex. jaune sur papier)."""
    if _contrast(fg, bg) >= 2.6:
        return fg
    for t in (0.35, 0.55, 0.75, 1.0):
        c = _mix(fg, text, t)
        if _contrast(c, bg) >= 3.0:
            return c
    return text


def map_palette(base: dict, key: str, roles: dict = None) -> dict:
    """Couleurs du programme -> theme commun (les cles sans role connu gardent leur couleur)."""
    if key not in PALETTES:
        return dict(base)
    pal = PALETTES[key]; r = dict(ROLES); r.update({k.lower(): v for k, v in (roles or {}).items()})
    out = {}
    for k, v in base.items():
        role = r.get(str(k).lower())
        out[k] = pal[role] if (role and isinstance(v, str) and v.startswith("#")) else v
    return out


class Themer:
    """Applique un theme commun a une fenetre Tk (et a ses fenetres filles), en direct."""

    def __init__(self, root, app: str, palette, roles=None, store=None, on_change=None):
        self.root, self.app = root, app
        self.base = {k: v for k, v in dict(palette).items() if isinstance(v, str) and v.startswith("#")}
        self.palette = palette if isinstance(palette, dict) else None
        self.roles, self.store, self.on_change = roles or {}, store, on_change
        self.key = "original"
        self.var = None
        self._orig = {}            # chemin widget -> {option: couleur d'origine}
        self.cur_map = {}          # couleur courante -> couleur d'origine (pour les widgets crees apres)
        self._styles = set()
        self._prev = {}

    # ---- couleurs
    def _target(self, key) -> dict:
        """couleur d'origine -> couleur du theme"""
        if key == "original":
            return {}
        new = map_palette(self.base, key, self.roles)
        m = {}
        for k, v in self.base.items():
            m.setdefault(_norm(v), new[k])
        return m

    def recolor(self, key):
        tmap = self._target(key)
        self._text = (PALETTES.get(key) or PALETTES["cosmos"])["TEXT"]
        seen = 0
        stack = [self.root]
        while stack:
            w = stack.pop()
            try:
                stack.extend(w.winfo_children())
            except Exception:
                pass
            path = str(w)
            try:
                if w.winfo_class().startswith("T") or w.winfo_class() in ("Treeview",):
                    self._styles.add(str(w.cget("style")) or w.winfo_class())
            except Exception:
                try:
                    self._styles.add(w.winfo_class())
                except Exception:
                    pass
            rec = self._orig.setdefault(path, {})
            for opt in COLOR_OPTS:
                try:
                    cur = w.cget(opt)
                except Exception:
                    continue
                if not isinstance(cur, str) or not cur.startswith("#"):
                    continue
                orig = rec.get(opt)
                if orig is None or _norm(cur) != rec.get("~" + opt):
                    orig = self.cur_map.get(_norm(cur), _norm(cur))   # widget nouveau (ou recree au meme chemin)
                rec[opt] = orig
                new = tmap.get(orig, orig) if tmap else orig
                rec["~" + opt] = _norm(new)
                if _norm(new) != _norm(cur):
                    try:
                        w.configure(**{opt: new}); seen += 1
                    except Exception:
                        pass
            if tmap:
                try:
                    bgc, fgc = w.cget("background"), w.cget("foreground")
                    if str(bgc).startswith("#") and str(fgc).startswith("#"):
                        nf = readable(fgc, bgc, self._text)
                        if _norm(nf) != _norm(fgc):
                            w.configure(foreground=nf); rec["~foreground"] = _norm(nf)
                except Exception:
                    pass
            cls = ""
            try:
                cls = w.winfo_class()
            except Exception:
                pass
            if cls == "Listbox":
                try:
                    for i in range(int(w.size())):
                        irec = rec.setdefault(f"#row{i}", {})
                        for opt in ("background", "foreground", "selectbackground", "selectforeground"):
                            cur = w.itemcget(i, opt)
                            if not cur or not str(cur).startswith("#"):
                                continue
                            orig = irec.get(opt) or self.cur_map.get(_norm(cur), _norm(cur)); irec[opt] = orig
                            new = tmap.get(orig, orig) if tmap else orig
                            if _norm(new) != _norm(cur):
                                w.itemconfigure(i, **{opt: new})
                        if tmap:
                            ib = w.itemcget(i, "background") or w.cget("background")
                            fg_ = w.itemcget(i, "foreground") or w.cget("foreground")
                            if str(ib).startswith("#") and str(fg_).startswith("#"):
                                nf = readable(fg_, ib, self._text)
                                if _norm(nf) != _norm(fg_):
                                    w.itemconfigure(i, foreground=nf)
                except Exception:
                    pass
            if cls == "Treeview":
                try:
                    tags, todo = set(), list(w.get_children(""))
                    while todo:
                        it = todo.pop()
                        tags.update(w.item(it, "tags") or ())
                        todo.extend(w.get_children(it))
                    for tg in tags:
                        trec = rec.setdefault(f"#tvtag{tg}", {})
                        for opt in ("background", "foreground"):
                            cur = w.tag_configure(tg, opt)
                            if not cur or not str(cur).startswith("#"):
                                continue
                            orig = trec.get(opt) or self.cur_map.get(_norm(cur), _norm(cur)); trec[opt] = orig
                            new = tmap.get(orig, orig) if tmap else orig
                            if tmap and opt == "foreground":
                                tb = w.tag_configure(tg, "background") or (self.palette or {}).get("PANEL") or "#ffffff"
                                if str(tb).startswith("#"):
                                    new = readable(new, tb, self._text)
                            if _norm(new) != _norm(cur):
                                w.tag_configure(tg, **{opt: new})
                except Exception:
                    pass
            if cls == "Canvas":
                try:
                    for it in w.find_all():
                        irec = rec.setdefault(f"#item{it}", {})
                        for opt in ITEM_OPTS:
                            try:
                                cur = w.itemcget(it, opt)
                            except Exception:
                                continue
                            if not cur or not str(cur).startswith("#"):
                                continue
                            orig = irec.get(opt) or self.cur_map.get(_norm(cur), _norm(cur)); irec[opt] = orig
                            new = tmap.get(orig, orig) if tmap else orig
                            if _norm(new) != _norm(cur):
                                w.itemconfigure(it, **{opt: new})
                except Exception:
                    pass
            elif cls == "Text":
                try:
                    for tg in w.tag_names():
                        trec = rec.setdefault(f"#tag{tg}", {})
                        for opt in TAG_OPTS:
                            try:
                                cur = w.tag_cget(tg, opt)
                            except Exception:
                                continue
                            if not cur or not str(cur).startswith("#"):
                                continue
                            orig = trec.get(opt) or self.cur_map.get(_norm(cur), _norm(cur)); trec[opt] = orig
                            new = tmap.get(orig, orig) if tmap else orig
                            if tmap and opt == "foreground":
                                tb = w.tag_cget(tg, "background") or w.cget("background")
                                if str(tb).startswith("#"):
                                    new = readable(new, tb if _norm(tb) not in tmap else tmap[_norm(tb)], self._text)
                            if _norm(new) != _norm(cur):
                                w.tag_configure(tg, **{opt: new})
                except Exception:
                    pass
        self._ttk(tmap)
        # palette du programme : les fenetres ouvertes ensuite prennent le theme
        newpal = map_palette(self.base, key, self.roles) if key != "original" else dict(self.base)
        if self.palette is not None:
            try:
                self.palette.update(newpal)
            except Exception:
                pass
        if self.store:
            try:
                self.store(newpal)
            except Exception:
                pass
        self.cur_map = {_norm(v): o for o, v in tmap.items()} if tmap else {}
        self._prev = dict(tmap)
        return seen

    def _ttk(self, tmap):
        try:
            from tkinter import ttk
            st = ttk.Style(self.root)
            if not hasattr(self, "_ttk_orig"):
                self._ttk_orig = {}
            names = set(self._styles)
            for name in names | {".", "TFrame", "TLabel", "TButton", "TEntry", "TCombobox", "Treeview", "Treeview.Heading",
                         "TNotebook", "TNotebook.Tab", "TCheckbutton", "TRadiobutton", "Vertical.TScrollbar",
                         "Horizontal.TScrollbar", "TProgressbar", "Horizontal.TProgressbar", "TPanedwindow", "TSpinbox"}:
                for opt in ("background", "foreground", "fieldbackground", "troughcolor", "bordercolor",
                            "lightcolor", "darkcolor", "arrowcolor", "selectbackground", "selectforeground"):
                    try:
                        cur = st.lookup(name, opt)
                    except Exception:
                        continue
                    if not cur or not str(cur).startswith("#"):
                        continue
                    k = (name, opt)
                    orig = self._ttk_orig.get(k) or self.cur_map.get(_norm(cur), _norm(cur)); self._ttk_orig[k] = orig
                    new = tmap.get(orig, orig) if tmap else orig
                    if _norm(new) != _norm(cur):
                        try:
                            st.configure(name, **{opt: new})
                        except Exception:
                            pass
                try:
                    mp = st.map(name)
                except Exception:
                    mp = {}
                for opt, specs in (mp or {}).items():
                    k = (name, "map", opt)
                    if k not in self._ttk_orig:
                        self._ttk_orig[k] = [tuple(x) for x in specs]
                    out, changed = [], False
                    for spec in self._ttk_orig[k]:
                        spec = list(spec); val = spec[-1]
                        if isinstance(val, str) and val.startswith("#"):
                            o = _norm(val); nv = tmap.get(o, o) if tmap else o
                            changed = changed or nv != o; spec[-1] = nv
                        out.append(tuple(spec))
                    try:
                        st.map(name, **{opt: out})
                    except Exception:
                        pass
        except Exception:
            pass

    def apply(self, key, save_choice=True, announce=False):
        if key not in THEME_ORDER:
            key = "original"
        ok = True
        try:
            self.recolor(key)
        except Exception:
            ok = False
        self.key = key
        if self.var is not None:
            try:
                self.var.set(key)
            except Exception:
                pass
        if save_choice:
            set_choice(self.app, key)
        if self.on_change and save_choice:
            try:
                self.on_change(key)
            except Exception:
                pass
        if announce:
            self.toast(("\U0001f3a8 Th\u00e8me : " + LABELS[key].split(" (")[0]) +
                       ("" if ok else " \u2014 il s'appliquera au complet au prochain lancement."))

    def toast(self, msg):
        try:
            import tkinter as tk
            pal = PALETTES.get(self.key) or PALETTES["cosmos"]
            t = tk.Toplevel(self.root); t.overrideredirect(True)
            try:
                t.attributes("-topmost", True)
            except Exception:
                pass
            tk.Label(t, text=msg + "\n(certains d\u00e9tails suivent au prochain lancement)", bg=pal["ACC"], fg=pal["ONACC"],
                     font=("Segoe UI", 11, "bold"), padx=14, pady=8, justify="left").pack()
            self.root.update_idletasks()
            x = self.root.winfo_rootx() + max(20, self.root.winfo_width() // 2 - 180)
            y = self.root.winfo_rooty() + 60
            t.geometry(f"+{x}+{y}")
            t.after(2600, t.destroy)
        except Exception:
            pass

    # ---- interface
    def build_menu(self, parent):
        import tkinter as tk
        m = tk.Menu(parent, tearoff=0)
        if self.var is None:
            self.var = tk.StringVar(master=self.root, value=self.key)
        for k in THEME_ORDER:
            m.add_radiobutton(label=LABELS[k], variable=self.var, value=k,
                              command=lambda k=k: self.apply(k, announce=True))
        m.add_separator()
        m.add_command(label="Th\u00e8me suivant (Ctrl+Maj+T)", command=self.cycle)
        m.add_command(label="Appliquer ce th\u00e8me \u00e0 toute la suite", command=self.apply_suite)
        return m

    def cycle(self, event=None):
        i = THEME_ORDER.index(self.key) if self.key in THEME_ORDER else 0
        self.apply(THEME_ORDER[(i + 1) % len(THEME_ORDER)], announce=True)
        return "break"

    def popup(self, event=None):
        try:
            m = self.build_menu(self.root)
            x, y = self.root.winfo_pointerx(), self.root.winfo_pointery()
            m.tk_popup(x, y)
        except Exception:
            pass
        return "break"

    def apply_suite(self):
        set_suite(self.key)
        set_choice(self.app, self.key) if self.key != "original" else None
        self.toast("\u2705 Toute la suite : " + LABELS[self.key].split(" (")[0] +
                   "\nLes programmes d\u00e9j\u00e0 ouverts le prennent au prochain lancement.")


def install(root, app: str, palette, roles=None, store=None, menubar=None, button_parent=None,
            on_change=None, shortcut=True):
    """A appeler une fois l'interface construite (avant mainloop). Ne plante jamais le programme."""
    try:
        th = Themer(root, app, palette, roles, store, on_change)
        import tkinter as tk
        th.var = tk.StringVar(master=root, value="original")
        mb = menubar
        if mb is None:
            try:
                name = root.cget("menu")
                mb = root.nametowidget(name) if name else None
            except Exception:
                mb = None
        if mb is None and button_parent is None:
            try:  # pas de barre de menus : on en ajoute une toute simple (ne cache aucun bouton)
                mb = tk.Menu(root)
                root.configure(menu=mb)
            except Exception:
                mb = None
        if mb is not None:
            try:
                mb.add_cascade(label="\U0001f3a8 Th\u00e8me", menu=th.build_menu(mb))
            except Exception:
                mb = None
        if mb is None:
            par = button_parent or root
            pal = th.base
            bg = pal.get("BTN") or pal.get("btn") or pal.get("ACC") or "#24406e"
            fg = pal.get("BTN_FG") or pal.get("TEXT") or pal.get("fg") or "#ffffff"
            b = tk.Button(par, text="\U0001f3a8 Th\u00e8me", command=th.popup, bg=bg, fg=fg, relief="flat", bd=0,
                          padx=10, pady=4, cursor="hand2", font=("Segoe UI Emoji", 10, "bold"))
            if button_parent is None:
                b.place(relx=1.0, x=-6, y=4, anchor="ne")
            else:
                b.pack(side="right", padx=4, pady=2)
            th.button = b
            _tip(b, "Changer les couleurs de ce programme (Ctrl+Maj+T = th\u00e8me suivant)")
        if shortcut:
            for seq in ("<Control-Shift-T>", "<Control-Shift-t>"):
                try:
                    root.bind_all(seq, th.cycle, add="+")
                except Exception:
                    pass
        key = chosen(app)
        test = os.environ.get("PADAWAN_THEME_TEST", "")
        if test:
            key = test.split("|")[0] or key
        if key != "original":
            root.after(250, lambda: th.apply(key, save_choice=False))
        else:
            th.key = "original"
        if test:
            parts = test.split("|")
            shot = parts[1] if len(parts) > 1 else ""
            delay = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 2500
            root.after(delay, lambda: _shot_and_quit(root, shot))
        root._padawan_themer = th
        return th
    except Exception:
        return None


def _tip(w, text):
    import tkinter as tk
    state = {"t": None}

    def show(e=None):
        if state["t"]:
            return
        t = tk.Toplevel(w); t.overrideredirect(True)
        tk.Label(t, text=text, bg="#ffffe0", fg="#000000", font=("Segoe UI", 10), relief="solid", bd=1, padx=6, pady=3).pack()
        t.geometry(f"+{w.winfo_rootx() - 220}+{w.winfo_rooty() + w.winfo_height() + 4}")
        state["t"] = t

    def hide(e=None):
        if state["t"]:
            state["t"].destroy(); state["t"] = None
    w.bind("<Enter>", show, add="+"); w.bind("<Leave>", hide, add="+"); w.bind("<ButtonPress>", hide, add="+")


def _shot_and_quit(root, path):
    try:
        root.update()
        if path:
            from PIL import ImageGrab
            x, y = root.winfo_rootx(), root.winfo_rooty()
            w, h = root.winfo_width(), root.winfo_height()
            ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True).save(path)
    except Exception as e:
        print("capture impossible :", e, file=sys.stderr)
    try:
        root.destroy()
    except Exception:
        pass
    os._exit(0)
