# -*- coding: utf-8 -*-
"""CaptureScreen : ecran de fin (bravo !), notification Windows et compteur de temps enregistre."""
from __future__ import annotations

import os
import subprocess
import threading
import tkinter as tk
from datetime import datetime, timedelta

from .c01_config import NOWIN, hms, human_size, logger, save_cfg
from .c12_extras import AUDIO_EXT, read_card

VIDEO_EXTS = (".mp4", ".mkv", ".webm", ".mov", ".avi")


# ------------------------------------------------------------------ compteur (bibliotheque)
def media_duration(fp: str, cache: dict) -> float:
    """Duree d'un fichier : fiche resume si elle existe (instantane), sinon ffprobe (mise en cache)."""
    if fp in cache and cache[fp] is not None:
        return float(cache[fp] or 0)
    d = read_card(fp).get("duree")
    if not d:
        try:
            from .c04_recorder import probe_duration
            d = probe_duration(fp)
        except Exception:
            d = 0.0
    cache[fp] = float(d or 0)
    return cache[fp]


def compute_stats(files, cache: dict) -> dict:
    """Nombre et temps enregistre : total, par genre (videos / sons), cette semaine (depuis lundi)."""
    monday = (datetime.now() - timedelta(days=datetime.now().weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    st = {"video": [0, 0.0], "son": [0, 0.0], "semaine": [0, 0.0], "images": 0}
    for fp in files:
        low = fp.lower()
        if low.endswith(VIDEO_EXTS):
            kind = "video"
        elif low.endswith(AUDIO_EXT):
            kind = "son"
        else:
            st["images"] += 1
            continue
        d = media_duration(fp, cache)
        st[kind][0] += 1; st[kind][1] += d
        try:
            if datetime.fromtimestamp(os.path.getmtime(fp)) >= monday:
                st["semaine"][0] += 1; st["semaine"][1] += d
        except OSError:
            pass
    return st


def hours_text(sec: float) -> str:
    sec = int(sec or 0)
    h, m = divmod(sec // 60, 60)
    if h:
        return f"{h} h {m:02d}"
    return f"{m} min" if m else f"{sec} s"


def stats_text(st: dict) -> str:
    nv, tv = st["video"]; ns, ts = st["son"]; nw, tw = st["semaine"]
    n = nv + ns
    if not n:
        return "\U0001f4ca Ton premier enregistrement t'attend !"
    bits = [f"\U0001f4ca {n} enregistrement{'s' if n > 1 else ''} · {hours_text(tv + ts)} au total"]
    if nv and ns:
        bits.append(f"\U0001f3ac {nv} · {hours_text(tv)}   \U0001f3a4 {ns} · {hours_text(ts)}")
    bits.append(f"cette semaine : {nw} · {hours_text(tw)}" if nw else "rien encore cette semaine")
    return "   ·   ".join(bits)


# ------------------------------------------------------------------ notification Windows
def notify(title: str, message: str, icon: str = "") -> None:
    """Petite notification Windows (plyer si present, sinon bulle PowerShell). Jamais bloquant, silencieux si impossible."""
    def go():
        try:
            from plyer import notification  # type: ignore
            kw = dict(title=title[:63], message=message[:250], app_name="CaptureScreen", timeout=6)
            if icon and os.path.isfile(icon):
                kw["app_icon"] = icon
            notification.notify(**kw)
            return
        except Exception:
            pass
        if os.name != "nt":
            return
        try:
            t = title.replace("'", "''")[:63]
            m = message.replace("'", "''")[:200]
            ps = ("Add-Type -AssemblyName System.Windows.Forms;Add-Type -AssemblyName System.Drawing;"
                  "$n=New-Object System.Windows.Forms.NotifyIcon;$n.Icon=[System.Drawing.SystemIcons]::Information;"
                  f"$n.Visible=$true;$n.ShowBalloonTip(6000,'{t}','{m}','Info');Start-Sleep 7;$n.Dispose()")
            subprocess.Popen(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps], creationflags=NOWIN)
        except Exception:
            logger.info("notification impossible")
    threading.Thread(target=go, daemon=True).start()


# ------------------------------------------------------------------ ecran de fin
def finish_dialog(app, out: str):
    """« Bravo ! » : miniature, duree, taille, reperes et les gestes utiles en gros boutons."""
    p = app.pal
    d = tk.Toplevel(app.root)
    d.title("CaptureScreen — c'est enregistré !")
    d.configure(bg=p["PANEL"])
    d.transient(app.root)
    d.resizable(False, False)
    is_audio = out.lower().endswith(AUDIO_EXT)
    card = read_card(out)
    try:
        size = os.path.getsize(out)
    except OSError:
        size = 0
    dur = card.get("duree")
    tk.Label(d, text="\U0001f389 Bravo, c'est enregistré !", bg=p["PANEL"], fg=p["ACC"],
             font=("Segoe UI", 18, "bold")).pack(anchor="w", padx=18, pady=(14, 2))
    tk.Label(d, text=os.path.basename(out), bg=p["PANEL"], fg=p["TEXT"], font=("Segoe UI", 11, "bold"),
             wraplength=560, justify="left").pack(anchor="w", padx=18)
    mid = tk.Frame(d, bg=p["PANEL"]); mid.pack(fill="x", padx=18, pady=10)
    img = tk.Label(mid, text="\U0001f3b5" if is_audio else "\U0001f3ac", bg=p["DEEP"], fg=p["DIM"],
                   font=("Segoe UI Emoji", 40), width=8, height=3)
    img.pack(side="left")
    info = tk.Frame(mid, bg=p["PANEL"]); info.pack(side="left", fill="both", expand=True, padx=(14, 0))
    lab_dur = tk.Label(info, text=f"\u23f1 {hms(dur) if dur else '…'}", bg=p["PANEL"], fg=p["TEXT"],
                       font=("Segoe UI", 20, "bold"), anchor="w")
    lab_dur.pack(fill="x")
    lines = [f"\U0001f4be {human_size(size)}"]
    nm = len(card.get("reperes") or [])
    if nm:
        lines.append(f"\U0001f516 {nm} repère{'s' if nm > 1 else ''} (chapitres)")
    if card.get("pauses"):
        lines.append(f"\u23f8 {card['pauses']} pause{'s' if card['pauses'] > 1 else ''}")
    if card.get("reparations"):
        lines.append(f"\U0001f527 {card['reparations']} coupure(s) réparée(s) toute(s) seule(s)")
    tk.Label(info, text="\n".join(lines), bg=p["PANEL"], fg=p["DIM"], font=("Segoe UI", 11), anchor="w",
             justify="left").pack(fill="x")
    lab_stats = tk.Label(info, text="", bg=p["PANEL"], fg=p["ACC2"], font=("Segoe UI", 10, "bold"), anchor="w",
                         justify="left", wraplength=330)
    lab_stats.pack(fill="x", pady=(6, 0))

    def bg_work():
        t = None
        try:
            if not is_audio:
                from .c04_recorder import thumb
                t = thumb(out, 320)
            dd = dur
            if not dd:
                from .c04_recorder import probe_duration
                dd = probe_duration(out)
            lib = getattr(app, "lib", None)
            st = compute_stats(lib.scan() if lib else [out], getattr(lib, "_dur", {}) if lib else {})
        except Exception:
            logger.exception("ecran de fin")
            st, dd = None, dur
        app.root.after(0, lambda: fill(t, dd, st))

    def fill(t, dd, st):
        if not d.winfo_exists():
            return
        if dd:
            lab_dur.configure(text=f"\u23f1 {hms(dd)}")
        if st:
            n = st["video"][0] + st["son"][0]
            lab_stats.configure(text=f"\U0001f3c6 C'est ton enregistrement n° {n} — " +
                                f"{hours_text(st['video'][1] + st['son'][1])} enregistrées en tout !")
        if t:
            try:
                from PIL import Image, ImageTk
                im = Image.open(t); im.thumbnail((240, 135))
                ph = ImageTk.PhotoImage(im)
                img.configure(image=ph, text="", width=im.width, height=im.height); img._ph = ph
            except Exception:
                pass
    threading.Thread(target=bg_work, daemon=True).start()

    lib = getattr(app, "lib", None)
    acts = [("\u25b6 Regarder", lambda: _open(out), True),
            ("\U0001f4c1 Dossier", lambda: _reveal(out), False)]
    if lib is not None:
        acts.append(("\U0001f4e6 Archiveur", lambda: lib.to_archiveur(out), False))
        if not is_audio:
            acts.append(("\u2702 Couper", lambda: (close(), lib.trim_dialog(out)), False))
    acts.append(("\U0001f6e0 Outils", lambda: (close(), _tools(app, out)), False))
    row = tk.Frame(d, bg=p["PANEL"]); row.pack(fill="x", padx=14, pady=(0, 6))
    tips = {"\u25b6 Regarder": "Ouvrir la vidéo (Entrée)", "\U0001f4c1 Dossier": "Montrer le fichier dans l'Explorateur",
            "\U0001f4e6 Archiveur": "Ajouter à l'Archiveur (collection Mes enregistrements)",
            "\u2702 Couper": "Enlever le début ou la fin", "\U0001f6e0 Outils": "Version à partager, GIF, son amélioré…"}
    for i, (txt, cmd, hi) in enumerate(acts):
        b = tk.Button(row, text=txt, command=cmd, bg=p["ACC"] if hi else p["BTN"], fg=p["ONACC"] if hi else p["TEXT"],
                      activebackground=p["BTNH"], relief="flat", font=("Segoe UI Emoji", 12, "bold"), padx=10, pady=8,
                      cursor="hand2")
        b.grid(row=0, column=i, padx=3, sticky="ew")
        row.columnconfigure(i, weight=1)
        try:
            app.tip(b, tips.get(txt, ""))
        except Exception:
            pass
    bot = tk.Frame(d, bg=p["PANEL"]); bot.pack(fill="x", padx=18, pady=(4, 12))
    v = tk.BooleanVar(value=bool(app.cfg.get("end_screen", True)))

    def toggle():
        app.cfg["end_screen"] = bool(v.get())
        save_cfg(app.cfg)
    tk.Checkbutton(bot, text="Montrer cet écran après chaque enregistrement", variable=v, command=toggle,
                   bg=p["PANEL"], fg=p["DIM"], selectcolor=p["ENTRY"], activebackground=p["PANEL"],
                   font=("Segoe UI", 9)).pack(side="left")

    def close():
        try:
            d.destroy()
        except Exception:
            pass
    tk.Button(bot, text="Fermer (Échap)", command=close, bg=p["BTN"], fg=p["TEXT"], relief="flat",
              font=("Segoe UI", 10), padx=10, cursor="hand2").pack(side="right")
    d.bind("<Escape>", lambda e: close())
    d.bind("<Return>", lambda e: _open(out))
    d.update_idletasks()
    try:
        x = app.root.winfo_rootx() + (app.root.winfo_width() - d.winfo_reqwidth()) // 2
        y = app.root.winfo_rooty() + max(40, (app.root.winfo_height() - d.winfo_reqheight()) // 3)
        d.geometry(f"+{max(0, x)}+{max(0, y)}")
    except Exception:
        pass
    d.lift(); d.focus_force()
    app._finish_win = d
    return d


def _open(fp):
    from .c02_win32 import open_path
    open_path(fp)


def _reveal(fp):
    from .c02_win32 import reveal
    reveal(fp)


def _tools(app, fp):
    from .c14_tools_ui import tools_dialog
    tools_dialog(app, fp)
