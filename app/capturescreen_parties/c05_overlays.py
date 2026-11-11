# -*- coding: utf-8 -*-
"""CaptureScreen - c05 : superpositions a l'ecran (visibles dans la video, la souris les traverse) :
halo des clics, bulle des raccourcis, projecteur, loupe, minuteur, compte a rebours, choix de zone / fenetre,
cadre de la zone enregistree. La bulle clavier ne garde rien : elle affiche puis oublie."""
from __future__ import annotations

import ctypes
import time
import tkinter as tk

from .c02_win32 import (IS_WIN, MODS, SPECIAL, click_through, cursor_pos, exclude_from_capture, keys_down,
                        mouse_buttons, no_activate, virtual_screen, vk_name, window_rect, windows_list)

KEY = "#ff00fe"   # couleur rendue transparente
UI = ("Segoe UI", 11)


def overlay(root, x, y, w, h, transparent=True, alpha=None, bg=None):
    t = tk.Toplevel(root)
    t.withdraw()
    t.overrideredirect(True)
    t.geometry(f"{int(w)}x{int(h)}+{int(x)}+{int(y)}")
    t.attributes("-topmost", True)
    t.configure(bg=bg or (KEY if transparent else "black"))
    if transparent:
        t.attributes("-transparentcolor", KEY)
    if alpha is not None:
        t.attributes("-alpha", alpha)
    t.deiconify()
    return t


# ------------------------------------------------------------------ halo des clics
class ClickHalo:
    COLORS = ("#ffd400", "#ff4d6d", "#3ad1c2")  # gauche, droit, milieu

    def __init__(self, root):
        self.root, self.on, self._prev = root, False, (False, False, False)

    def start(self):
        if not self.on:
            self.on = True; self._tick()

    def stop(self):
        self.on = False

    def _tick(self):
        if not self.on:
            return
        b = mouse_buttons()
        for i in range(3):
            if b[i] and not self._prev[i]:
                self._ring(self.COLORS[i])
        self._prev = b
        self.root.after(15, self._tick)

    def _ring(self, color):
        x, y = cursor_pos()
        S = 120
        try:
            t = overlay(self.root, x - S // 2, y - S // 2, S, S)
            c = tk.Canvas(t, width=S, height=S, bg=KEY, highlightthickness=0)
            c.pack()
            click_through(t)
        except Exception:
            return
        steps = 12

        def anim(i=0):
            try:
                c.delete("all")
                r = 8 + (S // 2 - 12) * i / steps
                c.create_oval(S / 2 - r, S / 2 - r, S / 2 + r, S / 2 + r, outline=color, width=max(2, 6 - i // 3))
                if i < 4:
                    c.create_oval(S / 2 - 7, S / 2 - 7, S / 2 + 7, S / 2 + 7, fill=color, outline=color)
                if i >= steps:
                    t.destroy(); return
                t.after(25, anim, i + 1)
            except Exception:
                pass
        anim()


# ------------------------------------------------------------------ bulle des raccourcis clavier
class KeyBubble:
    """Montre les touches pressees (Ctrl + Maj + S) quelques secondes. Rien n'est ecrit sur disque.
    shortcuts_only : n'affiche pas les lettres tapees seules (protege les mots de passe a l'ecran)."""

    def __init__(self, root, get_rect, shortcuts_only=True):
        self.root, self.get_rect, self.shortcuts_only = root, get_rect, shortcuts_only
        self.on, self._prev, self.win, self._hide_job, self._last, self._count = False, set(), None, None, "", 1

    def start(self):
        if not self.on:
            self.on = True; self._prev = keys_down(); self._tick()

    def stop(self):
        self.on = False
        self._hide()

    def _tick(self):
        if not self.on:
            return
        now = keys_down()
        new = [vk for vk in now - self._prev if vk not in MODS and vk not in (0x10, 0x11, 0x12)]
        self._prev = now
        if new:
            mods = []
            if 0x11 in now: mods.append("Ctrl")
            if 0x12 in now: mods.append("Alt")
            if 0x10 in now: mods.append("Maj")
            if 0x5B in now or 0x5C in now: mods.append("Win")
            for vk in new:
                special = vk in SPECIAL or 0x70 <= vk <= 0x87
                strong = any(m in mods for m in ("Ctrl", "Alt", "Win"))
                if self.shortcuts_only and not (strong or special):
                    continue
                name = vk_name(vk)
                if name:
                    self._show(" + ".join(mods + [name]))
        self.root.after(30, self._tick)

    def _show(self, txt):
        if txt == self._last and self.win is not None:
            self._count += 1
            label = f"{txt}   ×{self._count}"
        else:
            self._count, label = 1, txt
        self._last = txt
        try:
            if self.win is None:
                self.win = overlay(self.root, 0, 0, 10, 10, transparent=False, alpha=0.92, bg="#101822")
                self.lbl = tk.Label(self.win, bg="#101822", fg="#ffffff", font=("Segoe UI", 22, "bold"), padx=26, pady=10)
                self.lbl.pack()
                click_through(self.win)
            self.lbl.configure(text="\u2328  " + label)
            self.win.update_idletasks()
            x, y, w, h = self.get_rect()
            bw, bh = self.win.winfo_reqwidth(), self.win.winfo_reqheight()
            self.win.geometry(f"+{int(x + (w - bw) / 2)}+{int(y + h - bh - max(40, h // 12))}")
            self.win.lift()
        except Exception:
            return
        if self._hide_job:
            self.root.after_cancel(self._hide_job)
        self._hide_job = self.root.after(1600, self._hide)

    def _hide(self):
        self._hide_job = None
        if self.win is not None:
            try:
                self.win.destroy()
            except Exception:
                pass
            self.win = None


# ------------------------------------------------------------------ projecteur
class Spotlight:
    """Assombrit tout sauf un cercle autour de la souris."""

    def __init__(self, root, rect, radius=150, dim=0.6):
        self.root, self.rect, self.radius, self.dim = root, rect, radius, dim
        self.win = None

    @property
    def active(self):
        return self.win is not None

    def toggle(self):
        self.stop() if self.win else self.start()

    def start(self):
        x, y, w, h = self.rect
        self.win = overlay(self.root, x, y, w, h, transparent=True, alpha=self.dim, bg="black")
        self.win.attributes("-transparentcolor", KEY)
        self.c = tk.Canvas(self.win, width=w, height=h, bg="black", highlightthickness=0)
        self.c.pack()
        self.hole = self.c.create_oval(0, 0, 0, 0, fill=KEY, outline=KEY)
        click_through(self.win)
        self._tick()

    def _tick(self):
        if not self.win:
            return
        cx, cy = cursor_pos()
        x, y, _w, _h = self.rect
        r = self.radius
        self.c.coords(self.hole, cx - x - r, cy - y - r, cx - x + r, cy - y + r)
        self.win.after(16, self._tick)

    def stop(self):
        if self.win:
            self.win.destroy(); self.win = None


# ------------------------------------------------------------------ loupe
class Magnifier:
    """Loupe qui suit la souris (a cote du pointeur, jamais par-dessus la zone grossie)."""
    W, H = 440, 290

    def __init__(self, root, zoom=2.0, color="#3ad1c2"):
        self.root, self.zoom, self.color, self.win = root, zoom, color, None

    @property
    def active(self):
        return self.win is not None

    def toggle(self):
        self.stop() if self.win else self.start()

    def start(self):
        self.win = overlay(self.root, 0, 0, self.W, self.H, transparent=False, bg=self.color)
        self.lbl = tk.Label(self.win, bd=0, bg="black")
        self.lbl.place(x=3, y=3, width=self.W - 6, height=self.H - 6)
        click_through(self.win)
        self._tick()

    def _tick(self):
        if not self.win:
            return
        try:
            from PIL import ImageGrab, ImageTk, Image
            cx, cy = cursor_pos()
            gw, gh = int((self.W - 6) / self.zoom), int((self.H - 6) / self.zoom)
            img = ImageGrab.grab(bbox=(cx - gw // 2, cy - gh // 2, cx - gw // 2 + gw, cy - gh // 2 + gh), all_screens=True)
            img = img.resize((self.W - 6, self.H - 6), Image.LANCZOS)
            self._ph = ImageTk.PhotoImage(img)
            self.lbl.configure(image=self._ph)
            vx, vy, vw, vh = virtual_screen()
            gap = gw // 2 + 24
            nx = cx + gap if cx + gap + self.W < vx + vw else cx - gap - self.W
            ny = min(max(vy, cy - self.H // 2), vy + vh - self.H)
            self.win.geometry(f"+{nx}+{ny}")
        except Exception:
            pass
        self.win.after(40, self._tick)

    def stop(self):
        if self.win:
            self.win.destroy(); self.win = None


# ------------------------------------------------------------------ minuteur a l'ecran
class ScreenTimer:
    """Chronometre ou compte a rebours, gros chiffres, deplacable. Visible dans la video."""

    def __init__(self, root, minutes=5, pal=None):
        self.root, self.minutes = root, minutes
        self.pal = pal or {"BG": "#0f1724", "TEXT": "#e8eefc", "ACC": "#3ad1c2", "REC": "#ff4d6d", "BTN": "#24406e"}
        self.win = None

    @property
    def active(self):
        return self.win is not None

    def toggle(self):
        self.stop() if self.win else self.start()

    def start(self):
        p = self.pal
        sx, sy, sw, sh = virtual_screen()
        self.win = t = overlay(self.root, sx + sw - 360, sy + 90, 330, 150, transparent=False, bg=p["BG"])
        t.attributes("-alpha", 0.93)
        self.mode, self.running, self.t_acc, self.t_run = "compte", True, 0.0, time.time()
        self.lbl = tk.Label(t, text="", font=("Consolas", 42, "bold"), bg=p["BG"], fg=p["ACC"])
        self.lbl.pack(fill="x", pady=(6, 0))
        bar = tk.Frame(t, bg=p["BG"]); bar.pack()
        for txt, cmd in (("\u23ef", self.toggle_run), ("\u21ba", self.reset), ("+1", lambda: self.add(60)),
                         ("-1", lambda: self.add(-60)), ("\u23f1", self.switch), ("\u2716", self.stop)):
            tk.Button(bar, text=txt, command=cmd, bg=p["BTN"], fg=p["TEXT"], relief="flat", font=("Segoe UI Emoji", 12, "bold"),
                      width=3, cursor="hand2").pack(side="left", padx=2, pady=4)
        for w in (t, self.lbl):
            w.bind("<ButtonPress-1>", self._press); w.bind("<B1-Motion>", self._drag)
        self._tick()

    def _press(self, e):
        self._dx, self._dy = e.x_root - self.win.winfo_x(), e.y_root - self.win.winfo_y()

    def _drag(self, e):
        self.win.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")

    def _elapsed(self):
        return self.t_acc + ((time.time() - self.t_run) if self.running else 0)

    def toggle_run(self):
        if self.running:
            self.t_acc = self._elapsed(); self.running = False
        else:
            self.t_run, self.running = time.time(), True

    def reset(self):
        self.t_acc, self.t_run = 0.0, time.time()

    def add(self, s):
        self.minutes = max(1, self.minutes + s // 60) if self.mode == "compte" else self.minutes
        if self.mode == "chrono":
            self.t_acc = max(0, self.t_acc - s)

    def switch(self):
        self.mode = "chrono" if self.mode == "compte" else "compte"; self.reset()

    def _tick(self):
        if not self.win:
            return
        e = self._elapsed()
        if self.mode == "compte":
            left = self.minutes * 60 - e
            if left <= 0:
                txt, col = "\u23f0 0:00", (self.pal["REC"] if int(e * 2) % 2 else self.pal["TEXT"])
            else:
                txt, col = f"\u23f3 {int(left) // 60}:{int(left) % 60:02d}", (self.pal["REC"] if left < 60 else self.pal["ACC"])
        else:
            txt, col = f"\u23f1 {int(e) // 60}:{int(e) % 60:02d}", self.pal["ACC"]
        self.lbl.configure(text=txt, fg=col)
        self.win.after(250, self._tick)

    def stop(self):
        if self.win:
            self.win.destroy(); self.win = None


# ------------------------------------------------------------------ compte a rebours 3-2-1
def countdown(root, rect, n, done, cancel_flag=None):
    if n <= 0:
        done(); return
    x, y, w, h = rect
    S = 260
    t = overlay(root, x + (w - S) // 2, y + (h - S) // 2, S, S)
    exclude_from_capture(t)
    c = tk.Canvas(t, width=S, height=S, bg=KEY, highlightthickness=0); c.pack()
    click_through(t)

    def step(k):
        if cancel_flag and cancel_flag.get("stop"):
            t.destroy(); return
        if k <= 0:
            t.destroy(); root.after(120, done); return
        c.delete("all")
        c.create_oval(10, 10, S - 10, S - 10, fill="#101822", outline="#ff4d6d", width=8)
        c.create_text(S / 2, S / 2 - 8, text=str(k), fill="white", font=("Segoe UI", 110, "bold"))
        c.create_text(S / 2, S - 50, text="Échap = annuler", fill="#9fb0d0", font=("Segoe UI", 11))
        t.after(1000, step, k - 1)
    step(n)


# ------------------------------------------------------------------ choix d'une zone
def select_region(root, done):
    """Plein ecran assombri : glisser pour tracer la zone. done((x, y, w, h)) ou done(None)."""
    vx, vy, vw, vh = virtual_screen()
    t = overlay(root, vx, vy, vw, vh, transparent=False, alpha=0.35, bg="black")
    t.configure(cursor="crosshair")
    c = tk.Canvas(t, width=vw, height=vh, bg="black", highlightthickness=0, cursor="crosshair"); c.pack()
    c.create_text(vw // 2 - vx + vx, 60, text="Glisse la souris pour choisir la zone  ·  Entrée = écran entier  ·  Échap = annuler",
                  fill="white", font=("Segoe UI", 18, "bold"))
    st = {"x0": None, "r": None, "lab": None}

    def press(e):
        st["x0"] = (e.x, e.y)
        for k in ("r", "lab"):
            if st[k]:
                c.delete(st[k])
        st["r"] = c.create_rectangle(e.x, e.y, e.x, e.y, outline="#ff4d6d", width=3, fill="white", stipple="gray12")
        st["lab"] = c.create_text(e.x, e.y - 18, text="", fill="white", font=("Segoe UI", 14, "bold"))

    def move(e):
        if st["x0"]:
            x0, y0 = st["x0"]
            c.coords(st["r"], x0, y0, e.x, e.y)
            c.coords(st["lab"], min(x0, e.x) + 70, min(y0, e.y) - 18)
            c.itemconfigure(st["lab"], text=f"{abs(e.x - x0)} × {abs(e.y - y0)}")

    def release(e):
        if not st["x0"]:
            return
        x0, y0 = st["x0"]
        x, y, w, h = min(x0, e.x) + vx, min(y0, e.y) + vy, abs(e.x - x0), abs(e.y - y0)
        t.destroy()
        done((x, y, w, h) if w >= 40 and h >= 40 else None)

    def esc(e=None):
        t.destroy(); done(None)

    def full(e=None):
        t.destroy(); done("ecran")
    c.bind("<ButtonPress-1>", press); c.bind("<B1-Motion>", move); c.bind("<ButtonRelease-1>", release)
    t.bind("<Escape>", esc); t.bind("<Return>", full)
    t.focus_force()


# ------------------------------------------------------------------ choix d'une fenetre
def pick_window(root, pal, done):
    """Liste des fenetres (double-clic / Entree) ou « Cliquer sur la fenetre »."""
    import os
    p = pal
    d = tk.Toplevel(root); d.title("Choisir la fenêtre à enregistrer"); d.configure(bg=p["BG"])
    d.geometry("760x520")
    if root.winfo_viewable():
        d.transient(root)
    else:  # fenetre principale cachee (lance depuis l'Archiveur) : la liste reste visible au premier plan
        d.attributes("-topmost", True)
    d.grab_set()
    tk.Label(d, text="\U0001fa9f Quelle fenêtre veux-tu enregistrer ?", bg=p["BG"], fg=p["TEXT"],
             font=("Segoe UI", 15, "bold")).pack(anchor="w", padx=14, pady=(12, 6))
    fr = tk.Frame(d, bg=p["BG"]); fr.pack(fill="both", expand=True, padx=14)
    sb = tk.Scrollbar(fr); sb.pack(side="right", fill="y")
    lb = tk.Listbox(fr, font=("Segoe UI", 13), bg=p["ENTRY"], fg=p["TEXT"], selectbackground=p["ACC"],
                    selectforeground=p.get("ONACC", "#000"), activestyle="none", yscrollcommand=sb.set, bd=0)
    lb.pack(fill="both", expand=True); sb.configure(command=lb.yview)
    wins = windows_list(skip_pid=os.getpid())
    for _h, title, (x, y, w, h) in wins:
        lb.insert("end", f"  {title}   ({w}×{h})")
    if wins:
        lb.selection_set(0)

    def ok(e=None):
        sel = lb.curselection()
        if not sel:
            return
        hwnd, title, _r = wins[sel[0]]
        d.destroy(); done((hwnd, title))

    def by_click():
        d.withdraw()
        tip = overlay(root, 0, 0, 10, 10, transparent=False, bg="#101822")
        tk.Label(tip, text="\U0001f5b1 Clique sur la fenêtre à enregistrer (Échap = annuler)", bg="#101822", fg="white",
                 font=("Segoe UI", 16, "bold"), padx=20, pady=12).pack()
        tip.update_idletasks()
        vx, vy, vw, _vh = virtual_screen()
        tip.geometry(f"+{vx + (vw - tip.winfo_reqwidth()) // 2}+{vy + 30}")
        click_through(tip); exclude_from_capture(tip)
        st = {"down": False, "t0": time.time()}

        def wait():
            l, _r, _m = mouse_buttons()
            if IS_WIN and ctypes.windll.user32.GetAsyncKeyState(0x1B) & 0x8000:
                tip.destroy(); d.destroy(); done(None); return
            if l:
                st["down"] = True
            elif st["down"]:
                from ctypes import wintypes
                x, y = cursor_pos()
                u = ctypes.windll.user32
                h = u.WindowFromPoint(wintypes.POINT(x, y))
                h = u.GetAncestor(h, 2) if h else 0
                tip.destroy()
                if h:
                    n = u.GetWindowTextLengthW(h)
                    buf = ctypes.create_unicode_buffer(n + 1); u.GetWindowTextW(h, buf, n + 1)
                    d.destroy(); done((int(h), buf.value or "Fenêtre"))
                else:
                    d.destroy(); done(None)
                return
            if time.time() - st["t0"] > 60:
                tip.destroy(); d.destroy(); done(None); return
            root.after(30, wait)
        root.after(300, wait)

    bar = tk.Frame(d, bg=p["BG"]); bar.pack(fill="x", padx=14, pady=10)
    for txt, cmd, tipt in (("\u2714 Choisir (Entrée)", ok, "Enregistrer la fenêtre sélectionnée"),
                           ("\U0001f5b1 Cliquer sur la fenêtre", by_click, "Clique directement sur la fenêtre voulue"),
                           ("\u2716 Annuler (Échap)", lambda: (d.destroy(), done(None)), "Fermer sans choisir")):
        b = tk.Button(bar, text=txt, command=cmd, bg=p["BTN"], fg=p["TEXT"], relief="flat", font=("Segoe UI", 12, "bold"),
                      padx=14, pady=8, cursor="hand2")
        b.pack(side="left", padx=4)
    lb.bind("<Double-Button-1>", ok); d.bind("<Return>", ok); d.bind("<Escape>", lambda e: (d.destroy(), done(None)))
    lb.focus_set()


# ------------------------------------------------------------------ cadre autour de la zone enregistree
class RegionBorder:
    """4 traits rouges juste a l'exterieur de la zone (hors video)."""

    def __init__(self, root, rect, color="#ff4d6d", th=3):
        self.wins = []
        x, y, w, h = rect
        for gx, gy, gw, gh in ((x - th, y - th, w + 2 * th, th), (x - th, y + h, w + 2 * th, th),
                               (x - th, y, th, h), (x + w, y, th, h)):
            t = overlay(root, gx, gy, gw, gh, transparent=False, bg=color)
            click_through(t); exclude_from_capture(t)
            self.wins.append(t)

    def destroy(self):
        for t in self.wins:
            try:
                t.destroy()
            except Exception:
                pass
        self.wins = []
