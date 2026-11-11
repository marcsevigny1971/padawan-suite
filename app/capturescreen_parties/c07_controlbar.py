# -*- coding: utf-8 -*-
"""CaptureScreen - c07 : barre flottante pendant l'enregistrement (toujours devant, deplacable,
cachee de la video si l'option est cochee) : temps, taille, niveaux du son, Pause, Arreter, outils."""
from __future__ import annotations

import tkinter as tk

from .c01_config import hms, human_size
from .c02_win32 import exclude_from_capture, virtual_screen


class ControlBar:
    def __init__(self, app, hide_in_video=True):
        self.app = app
        p = app.pal
        root = app.root
        self.win = w = tk.Toplevel(root)
        w.overrideredirect(True); w.attributes("-topmost", True); w.configure(bg=p["DEEP"])
        w.attributes("-alpha", 0.95)
        if hide_in_video:
            self.hidden_ok = exclude_from_capture(w)
        else:
            self.hidden_ok = False
        fr = tk.Frame(w, bg=p["DEEP"], padx=6, pady=4); fr.pack()
        grip = tk.Label(fr, text="\u2807", bg=p["DEEP"], fg=p["DIM"], font=("Segoe UI", 16), cursor="fleur")
        grip.pack(side="left", padx=(0, 4))
        grip.bind("<ButtonPress-1>", self._press); grip.bind("<B1-Motion>", self._drag)
        self.dot = tk.Label(fr, text="\u25cf", bg=p["DEEP"], fg=p["REC"], font=("Segoe UI", 16, "bold"))
        self.dot.pack(side="left")
        self.time = tk.Label(fr, text="00:00", bg=p["DEEP"], fg=p["TEXT"], font=("Consolas", 18, "bold"), width=7)
        self.time.pack(side="left")
        self.size = tk.Label(fr, text="", bg=p["DEEP"], fg=p["DIM"], font=("Segoe UI", 10), width=9)
        self.size.pack(side="left")
        self.meters = {}
        mf = tk.Frame(fr, bg=p["DEEP"]); mf.pack(side="left", padx=4)
        for kind, ic in (("systeme", "\U0001f50a"), ("micro", "\U0001f3a4")):
            if kind in app.rec.levels():
                row = tk.Frame(mf, bg=p["DEEP"]); row.pack(anchor="w")
                tk.Label(row, text=ic, bg=p["DEEP"], fg=p["TEXT"], font=("Segoe UI Emoji", 9)).pack(side="left")
                c = tk.Canvas(row, width=70, height=8, bg=p["ENTRY"], highlightthickness=0); c.pack(side="left", padx=2)
                self.meters[kind] = (c, c.create_rectangle(0, 0, 0, 8, fill=p["OK"], width=0))
        mods = app.hk_label
        self.bpause = self._btn(fr, "\u23f8", app.toggle_pause, f"Pause / Reprendre ({mods}+P)")
        self._btn(fr, "\u23f9", app.stop_recording, f"Arrêter et enregistrer le MP4 ({mods}+R)", bg=p["REC"])
        self._btn(fr, "\U0001f516", app.marker_prompt, f"Repère (chapitre) avec un nom — {mods}+K = repère rapide sans nom")
        self._btn(fr, "\u270f", app.toggle_draw, f"Dessiner à l'écran ({mods}+D)")
        self._btn(fr, "\U0001f526", app.toggle_spot, f"Projecteur : assombrit autour de la souris ({mods}+L)")
        self._btn(fr, "\U0001f50d", app.toggle_zoom, f"Loupe qui suit la souris ({mods}+Z)")
        self._btn(fr, "\u2b1c", app.toggle_board, f"Tableau blanc / noir ({mods}+B)")
        self._btn(fr, "\u23f1", app.toggle_timer, f"Minuteur à l'écran ({mods}+M)")
        self._btn(fr, "\U0001f4f7", app.screenshot_now, f"Capture d'écran PNG ({mods}+S)")
        self._btn(fr, "\u2716", app.cancel_recording, "Annuler : jeter cet enregistrement")
        w.update_idletasks()
        vx, vy, vw, _vh = virtual_screen()
        w.geometry(f"+{vx + (vw - w.winfo_reqwidth()) // 2}+{vy + 6}")
        self._blink = True
        self._tick()

    def _btn(self, par, txt, cmd, tip, bg=None):
        p = self.app.pal
        b = tk.Button(par, text=txt, command=cmd, bg=bg or p["BTN"], fg=p["TEXT"], activebackground=p["BTNH"],
                      relief="flat", font=("Segoe UI Emoji", 14, "bold"), width=3, cursor="hand2")
        b.pack(side="left", padx=2)
        self.app.tip(b, tip)
        return b

    def _press(self, e):
        self._dx, self._dy = e.x_root - self.win.winfo_x(), e.y_root - self.win.winfo_y()

    def _drag(self, e):
        self.win.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")

    def _tick(self):
        if not self.win:
            return
        rec = self.app.rec
        if rec is None:
            return
        p = self.app.pal
        paused = rec.state == "pause"
        self._blink = not self._blink
        self.dot.configure(text="\u23f8" if paused else "\u25cf",
                           fg=p["ACC2"] if paused else (p["REC"] if self._blink else p["DEEP"]))
        self.time.configure(text=hms(rec.elapsed()))
        self.size.configure(text=human_size(rec.size()))
        self.bpause.configure(text="\u25b6" if paused else "\u23f8", bg=p["ACC2"] if paused else p["BTN"])
        lv = rec.levels()
        for k, (c, r) in self.meters.items():
            v = lv.get(k, 0)
            c.coords(r, 0, 0, int(70 * v), 8)
            c.itemconfigure(r, fill=p["REC"] if v > 0.9 else p["OK"])
        self.win.after(500 if paused else 250, self._tick)

    def destroy(self):
        try:
            self.win.destroy()
        except Exception:
            pass
        self.win = None
