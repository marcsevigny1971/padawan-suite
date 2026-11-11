# -*- coding: utf-8 -*-
"""CaptureScreen - c06 : dessiner a l'ecran (visible dans la video) et tableau blanc / noir / vert.
Couches : [tableau] < surligneur (translucide) < encre < capteur souris (invisible, hors video) < palette (hors video).
Raccourcis (palette ou dessin actif) : P crayon, H surligneur, A fleche, R rectangle, E ellipse, T texte, G gomme,
1-6 couleurs, +/- epaisseur, Ctrl+Z annuler, Suppr tout effacer, Echap souris libre, Ctrl+Maj+D afficher/cacher."""
from __future__ import annotations

import math
import tkinter as tk

from .c02_win32 import click_through, exclude_from_capture
from .c05_overlays import KEY, overlay

COLORS = [("Rouge", "#ff3b30"), ("Jaune", "#ffd400"), ("Vert", "#34c759"), ("Bleu", "#0a84ff"),
          ("Blanc", "#ffffff"), ("Noir", "#111111")]
BOARDS = {"blanc": "#fbfbf8", "noir": "#15181c", "vert": "#1f4d3a"}
TOOLS = [("pen", "\u270f", "Crayon (P)", "p"), ("hl", "\U0001f58d", "Surligneur translucide (H)", "h"),
         ("arrow", "\u279c", "Flèche (A)", "a"), ("rect", "\u25ad", "Rectangle (R)", "r"),
         ("oval", "\u25ef", "Ellipse (E)", "e"), ("text", "T", "Texte (T) : clique puis écris, Entrée", "t"),
         ("eraser", "\U0001f9fd", "Gomme (G) : glisse sur un trait", "g")]


class Annotator:
    def __init__(self, root, rect, pal, board=None, tip=None, on_close=None):
        self.root, self.rect, self.pal, self.tip, self.on_close = root, rect, pal, tip, on_close
        self.tool, self.color, self.width = "pen", "#ff3b30", 5
        self.undo = []
        self.board_name = None
        self.board_win = None
        self.drawing = True
        self.visible = True
        x, y, w, h = rect
        self.hl = overlay(root, x, y, w, h, transparent=True, alpha=0.42)
        self.ch = tk.Canvas(self.hl, width=w, height=h, bg=KEY, highlightthickness=0); self.ch.pack()
        click_through(self.hl)
        self.ink = overlay(root, x, y, w, h, transparent=True)
        self.ci = tk.Canvas(self.ink, width=w, height=h, bg=KEY, highlightthickness=0); self.ci.pack()
        click_through(self.ink)
        self.catch = overlay(root, x, y, w, h, transparent=False, alpha=0.01, bg="black")
        exclude_from_capture(self.catch)
        self.catch.configure(cursor="pencil")
        self._bind(self.catch)
        self._palette()
        if board:
            self.set_board(board)
        self._restack()

    # ---------------------------------------------------------- fenetres
    def _restack(self):
        for w in (self.board_win, self.hl, self.ink, self.catch if self.drawing else None, self.pw):
            if w is not None:
                try:
                    w.lift(); w.attributes("-topmost", True)
                except Exception:
                    pass
        if self.drawing:
            self.catch.focus_force()

    def set_board(self, name):
        """name : blanc | noir | vert | None (transparent)."""
        if self.board_win is not None:
            self.board_win.destroy(); self.board_win = None
        self.board_name = name if name in BOARDS else None
        if self.board_name:
            x, y, w, h = self.rect
            self.board_win = overlay(self.root, x, y, w, h, transparent=False, bg=BOARDS[self.board_name])
            click_through(self.board_win)
            if self.board_name != "blanc" and self.color == "#111111":
                self.set_color("#ffffff")
            elif self.board_name == "blanc" and self.color == "#ffffff":
                self.set_color("#111111")
        self._restack()
        self._refresh_palette()

    def set_drawing(self, on):
        self.drawing = on
        if on:
            self.catch.deiconify()
        else:
            self.catch.withdraw()
        self._restack(); self._refresh_palette()

    def toggle_visible(self):
        self.visible = not self.visible
        for w in (self.board_win, self.hl, self.ink, self.pw):
            if w is not None:
                (w.deiconify if self.visible else w.withdraw)()
        if self.visible and self.drawing:
            self.catch.deiconify()
        else:
            self.catch.withdraw()
        if self.visible:
            self._restack()

    def close(self):
        for w in (self.board_win, self.hl, self.ink, self.catch, self.pw):
            try:
                if w is not None:
                    w.destroy()
            except Exception:
                pass
        self.board_win = None
        if self.on_close:
            self.on_close()

    # ---------------------------------------------------------- palette
    def _palette(self):
        p = self.pal
        x, y, w, h = self.rect
        self.pw = pw = tk.Toplevel(self.root)
        pw.overrideredirect(True); pw.attributes("-topmost", True); pw.configure(bg=p["PANEL"])
        exclude_from_capture(pw)
        head = tk.Label(pw, text="\u2630 Dessin", bg=p["ACC"], fg=p.get("ONACC", "#000"), font=("Segoe UI", 10, "bold"),
                        cursor="fleur", pady=3)
        head.pack(fill="x")
        head.bind("<ButtonPress-1>", lambda e: setattr(self, "_d", (e.x_root - pw.winfo_x(), e.y_root - pw.winfo_y())))
        head.bind("<B1-Motion>", lambda e: pw.geometry(f"+{e.x_root - self._d[0]}+{e.y_root - self._d[1]}"))
        body = tk.Frame(pw, bg=p["PANEL"]); body.pack(padx=4, pady=4)
        self.tbtn = {}

        def btn(par, txt, cmd, tip, wdt=3, **kw):
            b = tk.Button(par, text=txt, command=cmd, width=wdt, relief="flat", bg=kw.get("bg", p["BTN"]),
                          fg=kw.get("fg", p["TEXT"]), font=("Segoe UI Emoji", 15, "bold"), cursor="hand2",
                          activebackground=p["BTNH"])
            if self.tip:
                self.tip(b, tip)
            return b
        r = 0
        for key, ic, tip, _k in TOOLS:
            b = btn(body, ic, lambda k=key: self.set_tool(k), tip); b.grid(row=r // 2, column=r % 2, padx=2, pady=2)
            self.tbtn[key] = b; r += 1
        r = (r + 1) // 2 * 2
        self.cbtn = {}
        for i, (name, col) in enumerate(COLORS):
            b = btn(body, "\u25cf", lambda c=col: self.set_color(c), f"{name} ({i + 1})", bg=p["BTN"], fg=col)
            b.grid(row=r // 2, column=r % 2, padx=2, pady=2); self.cbtn[col] = b; r += 1
        btn(body, "\u2796", lambda: self.set_width(-2), "Plus fin (-)").grid(row=r // 2, column=0, padx=2, pady=2)
        btn(body, "\u2795", lambda: self.set_width(2), "Plus épais (+)").grid(row=r // 2, column=1, padx=2, pady=2); r += 2
        self.wlab = tk.Label(body, text="", bg=p["PANEL"], fg=p["DIM"], font=("Segoe UI", 9))
        self.wlab.grid(row=r // 2, column=0, columnspan=2); r += 2
        btn(body, "\u21b6", self.do_undo, "Annuler le dernier trait (Ctrl+Z)").grid(row=r // 2, column=0, padx=2, pady=2)
        btn(body, "\U0001f5d1", self.clear, "Tout effacer (Suppr)").grid(row=r // 2, column=1, padx=2, pady=2); r += 2
        self.bbtn = {}
        for i, (name, ic, tip) in enumerate((("blanc", "\u2b1c", "Tableau blanc"), ("noir", "\u2b1b", "Tableau noir"),
                                              ("vert", "\U0001f7e9", "Tableau vert (ardoise)"),
                                              (None, "\U0001fa9f", "Transparent : dessiner par-dessus l'écran"))):
            b = btn(body, ic, lambda n=name: self.set_board(n), tip)
            b.grid(row=r // 2, column=r % 2, padx=2, pady=2); self.bbtn[name] = b; r += 1
        self.mbtn = btn(body, "\U0001f5b1", lambda: self.set_drawing(not self.drawing),
                        "Souris libre / dessiner (Échap) : les traits restent affichés", wdt=7)
        self.mbtn.grid(row=r // 2 + 1, column=0, columnspan=2, padx=2, pady=2)
        btn(body, "\u2716 Fermer", self.close, "Fermer le dessin (Ctrl+Maj+D pour cacher/montrer)", wdt=7,
            bg=p.get("REC", "#c62828")).grid(row=r // 2 + 2, column=0, columnspan=2, padx=2, pady=(6, 2))
        pw.update_idletasks()
        pw.geometry(f"+{x + 12}+{y + max(60, (h - pw.winfo_reqheight()) // 2)}")
        self._bind(pw)
        self._refresh_palette()

    def _refresh_palette(self):
        p = self.pal
        try:
            for k, b in self.tbtn.items():
                b.configure(bg=p["ACC"] if k == self.tool else p["BTN"])
            for c, b in self.cbtn.items():
                b.configure(bg=p["SEL"] if c == self.color else p["BTN"])
            for n, b in self.bbtn.items():
                b.configure(bg=p["ACC"] if n == self.board_name else p["BTN"])
            self.mbtn.configure(text=("\U0001f5b1 Souris libre" if self.drawing else "\u270f Dessiner"))
            self.wlab.configure(text=f"Épaisseur : {self.width}")
        except Exception:
            pass

    # ---------------------------------------------------------- reglages
    def set_tool(self, k):
        self.tool = k
        if not self.drawing:
            self.set_drawing(True)
        self.catch.configure(cursor={"eraser": "dotbox", "text": "xterm"}.get(k, "pencil"))
        self._refresh_palette()

    def set_color(self, c):
        self.color = c; self._refresh_palette()

    def set_width(self, d):
        self.width = max(1, min(40, self.width + d)); self._refresh_palette()

    # ---------------------------------------------------------- clavier / souris
    def _bind(self, w):
        for _key, _ic, _tip, k in TOOLS:
            w.bind(f"<KeyPress-{k}>", lambda e, kk=_key: self.set_tool(kk))
            w.bind(f"<KeyPress-{k.upper()}>", lambda e, kk=_key: self.set_tool(kk))
        for i, (_n, col) in enumerate(COLORS):
            w.bind(f"<KeyPress-{i + 1}>", lambda e, c=col: self.set_color(c))
        w.bind("<plus>", lambda e: self.set_width(2)); w.bind("<KP_Add>", lambda e: self.set_width(2))
        w.bind("<minus>", lambda e: self.set_width(-2)); w.bind("<KP_Subtract>", lambda e: self.set_width(-2))
        w.bind("<Control-z>", lambda e: self.do_undo()); w.bind("<Control-Z>", lambda e: self.do_undo())
        w.bind("<Delete>", lambda e: self.clear())
        w.bind("<Escape>", lambda e: self.set_drawing(False))
        if w is self.catch:
            w.bind("<ButtonPress-1>", self._down); w.bind("<B1-Motion>", self._move); w.bind("<ButtonRelease-1>", self._up)
            w.bind("<ButtonPress-3>", lambda e: self.set_drawing(False))

    def _canvas(self):
        return self.ch if self.tool == "hl" else self.ci

    def _down(self, e):
        self.x0, self.y0 = e.x, e.y
        self.cur = None
        c, col, wd = self._canvas(), self.color, self.width
        if self.tool == "pen":
            self.pts = [e.x, e.y, e.x + 0.1, e.y + 0.1]
            self.cur = c.create_line(*self.pts, fill=col, width=wd, capstyle="round", joinstyle="round", smooth=True)
        elif self.tool == "hl":
            self.pts = [e.x, e.y, e.x + 0.1, e.y + 0.1]
            self.cur = c.create_line(*self.pts, fill=col, width=wd * 4, capstyle="round", joinstyle="round")
        elif self.tool == "arrow":
            s = max(12, wd * 3)
            self.cur = c.create_line(e.x, e.y, e.x, e.y, fill=col, width=wd, arrow="last", arrowshape=(s, s * 1.2, s / 2.2),
                                     capstyle="round")
        elif self.tool == "rect":
            self.cur = c.create_rectangle(e.x, e.y, e.x, e.y, outline=col, width=wd)
        elif self.tool == "oval":
            self.cur = c.create_oval(e.x, e.y, e.x, e.y, outline=col, width=wd)
        elif self.tool == "text":
            self._text_at(e.x, e.y)
        elif self.tool == "eraser":
            self._erase(e.x, e.y)

    def _move(self, e):
        c = self._canvas()
        if self.tool in ("pen", "hl") and self.cur:
            if math.hypot(e.x - self.pts[-2], e.y - self.pts[-1]) >= 2:
                self.pts += [e.x, e.y]; c.coords(self.cur, *self.pts)
        elif self.tool in ("arrow", "rect", "oval") and self.cur:
            x1, y1 = e.x, e.y
            if self.tool != "arrow" and (e.state & 0x1):  # Maj = carre / cercle
                d = max(abs(x1 - self.x0), abs(y1 - self.y0))
                x1 = self.x0 + (d if x1 >= self.x0 else -d); y1 = self.y0 + (d if y1 >= self.y0 else -d)
            c.coords(self.cur, self.x0, self.y0, x1, y1)
        elif self.tool == "eraser":
            self._erase(e.x, e.y)

    def _up(self, e):
        if self.cur:
            self.undo.append((self._canvas(), self.cur))
            self.cur = None

    def _erase(self, x, y):
        r = max(10, self.width * 2)
        for c in (self.ci, self.ch):
            for it in c.find_overlapping(x - r, y - r, x + r, y + r):
                c.delete(it)

    def _text_at(self, x, y):
        size = max(14, self.width * 4)
        t = tk.Toplevel(self.root); t.overrideredirect(True); t.attributes("-topmost", True)
        exclude_from_capture(t)
        t.geometry(f"+{self.rect[0] + x}+{self.rect[1] + y - size}")
        v = tk.StringVar()
        en = tk.Entry(t, textvariable=v, font=("Segoe UI", size, "bold"), fg=self.color, bg="#202020", width=24,
                      insertbackground="white", relief="solid", bd=2)
        en.pack()

        def ok(e=None):
            s = v.get().strip()
            if s:
                it = self.ci.create_text(x, y, text=s, fill=self.color, anchor="sw", font=("Segoe UI", size, "bold"))
                self.undo.append((self.ci, it))
            t.destroy(); self.catch.focus_force()
        en.bind("<Return>", ok); en.bind("<Escape>", lambda e: (t.destroy(), self.catch.focus_force()))
        en.bind("<FocusOut>", ok)
        t.after(30, en.focus_force)

    def do_undo(self):
        while self.undo:
            c, it = self.undo.pop()
            if c.type(it):
                c.delete(it); return

    def clear(self):
        self.ci.delete("all"); self.ch.delete("all"); self.undo.clear()
