# -*- coding: utf-8 -*-
"""CaptureScreen - c14 : fenetres simples pour les nouveaux outils.
🛠 Outils d'une video · ℹ Resume + reperes cliquables · 🔖 repere avec nom · 🔗 joindre · ⏰ programmer."""
from __future__ import annotations

import os
import threading
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import messagebox

from .c01_config import hms, human_size, logger, save_cfg
from .c02_win32 import exclude_from_capture
from . import c13_edit as E
from .c12_extras import AUDIO_EXT, read_card, read_chapters, summary_text, write_card, write_chapters


def _font(sz=11, bold=False):
    return ("Segoe UI", sz, "bold" if bold else "normal")


def run_job(app, label, fn, *args, done=None):
    """Lance un traitement dans un fil ; la bibliotheque montre le resultat."""
    app.status(f"\u23f3 {label}… (l'original ne change pas)")

    def go():
        try:
            out = fn(*args)
            app.root.after(0, app.status, f"\u2705 {label} : {os.path.basename(out)}")
            app.root.after(0, app.lib.refresh, out)
            if done:
                app.root.after(0, done, out)
        except Exception as e:
            logger.exception(label)
            app.root.after(0, app.status, f"\u26a0 {label} : {e}")
    threading.Thread(target=go, daemon=True).start()


# ------------------------------------------------------------------ 🛠 outils d'une video
def tools_dialog(app, fp):
    p = app.pal
    isa = fp.lower().endswith(AUDIO_EXT)
    d = tk.Toplevel(app.root); d.title("\U0001f6e0 Outils"); d.configure(bg=p["BG"]); d.transient(app.root)
    tk.Label(d, text=os.path.basename(fp), bg=p["BG"], fg=p["TEXT"], font=_font(13, True)).pack(anchor="w", padx=14, pady=(12, 0))
    tk.Label(d, text="Chaque outil crée un NOUVEAU fichier à côté : l'original ne change jamais.", bg=p["BG"],
             fg=p["DIM"], font=_font(10)).pack(anchor="w", padx=14, pady=(0, 8))
    clean = tk.BooleanVar(value=bool(app.cfg.get("share_clean_audio", True)))
    srt = os.path.splitext(fp)[0] + ".srt"

    def close_then(f):
        def g():
            app.cfg["share_clean_audio"] = bool(clean.get()); save_cfg(app.cfg)
            d.destroy(); f()
        return g
    items = []
    if not isa:
        items += [("\U0001f4e8 Version à partager", "Petite vidéo 720p, facile à envoyer par courriel ou Teams",
                   lambda: run_job(app, "Version à partager", E.share_version, fp, 720, clean.get())),
                  ("\U0001f39e Extrait ou GIF", "Garder seulement un moment (MP4) ou en faire un GIF animé",
                   lambda: range_dialog(app, fp, "extrait")),
                  ("\u2702 Enlever un passage", "Supprimer un moment au milieu (une erreur, une pause…)",
                   lambda: range_dialog(app, fp, "enlever")),
                  ("\U0001f517 Joindre à d'autres", "Mettre plusieurs vidéos bout à bout", lambda: join_dialog(app, fp))]
    items += [("\u2728 Améliorer le son", "Moins de bruit de fond, volume plus régulier", lambda: run_job(
                  app, "Son amélioré", E.clean_audio, fp))]
    if not isa:
        items += [("\U0001f3b5 Garder seulement le son", "Un MP3 pour écouter le cours comme un balado",
                   lambda: run_job(app, "Son en MP3", E.audio_only, fp, clean.get())),
                  ("\U0001f524 Incruster les sous-titres", "Sous-titres dans l'image (visibles partout)" if os.path.isfile(srt)
                   else "Fais d'abord \U0001f4ac Sous-titres (bouton de la carte)",
                   (lambda: run_job(app, "Sous-titres incrustés", E.burn_subtitles, fp)) if os.path.isfile(srt) else None)]
    grid = tk.Frame(d, bg=p["BG"]); grid.pack(fill="x", padx=14)
    grid.columnconfigure(0, weight=1, uniform="t"); grid.columnconfigure(1, weight=1, uniform="t")
    for i, (t, sub, cmd) in enumerate(items):
        b = tk.Button(grid, text=f"{t}\n", command=close_then(cmd) if cmd else None, bg=p["BTN"], fg=p["TEXT"],
                      activebackground=p["BTNH"], relief="flat", font=_font(12, True), anchor="w", justify="left",
                      padx=12, pady=6, wraplength=int(330 * float(app.root.winfo_fpixels("1i")) / 96), cursor="hand2",
                      state="normal" if cmd else "disabled")
        b.configure(text=f"{t}\n{sub}")
        b.grid(row=i // 2, column=i % 2, sticky="ew", padx=3, pady=3)
        app.tip(b, sub)
    tk.Checkbutton(d, text="\u2728 Améliorer aussi le son dans la version à partager et le MP3", variable=clean,
                   bg=p["BG"], fg=p["TEXT"], selectcolor=p["ENTRY"], activebackground=p["BG"], font=_font(10)).pack(
        anchor="w", padx=14, pady=(8, 0))
    app.button(d, "Fermer (Échap)", d.destroy, "Fermer", small=True).pack(pady=10)
    d.bind("<Escape>", lambda e: d.destroy())
    return d


def range_dialog(app, fp, kind):
    """Choisir un moment (debut / fin) avec apercu : extrait (MP4 ou GIF) ou passage a enlever."""
    from .c04_recorder import frame_at
    p = app.pal
    dur = E.probe(fp)["duration"]
    if dur <= 1:
        messagebox.showinfo("Outils", "Vidéo trop courte.", parent=app.root); return
    d = tk.Toplevel(app.root); d.configure(bg=p["BG"]); d.transient(app.root); d.grab_set()
    d.title("\U0001f39e Extrait ou GIF" if kind == "extrait" else "\u2702 Enlever un passage")
    tk.Label(d, text=("Quel moment veux-tu garder ?" if kind == "extrait" else "Quel passage veux-tu enlever ?"),
             bg=p["BG"], fg=p["TEXT"], font=_font(13, True)).pack(padx=14, pady=(12, 4))
    pv = tk.Label(d, bg=p["DEEP"], width=64, height=18); pv.pack(padx=14, pady=4)
    a0, b0 = (0.0, min(dur, 10.0)) if kind == "extrait" else (dur * 0.4, dur * 0.6)
    s_var, e_var = tk.DoubleVar(value=round(a0, 1)), tk.DoubleVar(value=round(b0, 1))
    lab = tk.Label(d, bg=p["BG"], fg=p["ACC"], font=_font(12, True)); lab.pack()
    job = {"id": None, "ph": None}

    def put(img):
        try:
            from PIL import Image, ImageTk
            im = Image.open(img); im.thumbnail((640, 360)); job["ph"] = ImageTk.PhotoImage(im)
            pv.configure(image=job["ph"], width=640, height=360)
        except Exception:
            pass

    def show(t):
        threading.Thread(target=lambda: (lambda im: im and d.after(0, put, im))(frame_at(fp, t)), daemon=True).start()

    def changed(which):
        s, e = s_var.get(), e_var.get()
        if e - s < 0.5:
            (s_var.set(max(0, e - 0.5)) if which == "s" else e_var.set(min(dur, s + 0.5)))
        verb = "Garder" if kind == "extrait" else "Enlever"
        lab.configure(text=f"{verb} de {hms(s_var.get())} à {hms(e_var.get())}  →  {e_var.get() - s_var.get():.1f} s")
        if job["id"]:
            d.after_cancel(job["id"])
        job["id"] = d.after(250, show, s_var.get() if which == "s" else max(0, e_var.get() - 0.3))
    for txt, var, w in (("Début", s_var, "s"), ("Fin", e_var, "e")):
        row = tk.Frame(d, bg=p["BG"]); row.pack(fill="x", padx=14)
        tk.Label(row, text=txt, width=6, bg=p["BG"], fg=p["TEXT"], font=_font(11, True)).pack(side="left")
        tk.Scale(row, from_=0, to=round(dur, 1), resolution=0.1, orient="horizontal", variable=var, showvalue=False,
                 length=560, bg=p["BG"], fg=p["TEXT"], troughcolor=p["ENTRY"], highlightthickness=0, sliderlength=26,
                 width=18, command=lambda v, ww=w: changed(ww)).pack(side="left", fill="x", expand=True)
    gif = tk.BooleanVar(value=False)
    if kind == "extrait":
        tk.Checkbutton(d, text="\U0001f5bc En GIF animé (sans son, 30 s max, 640 px)", variable=gif, bg=p["BG"],
                       fg=p["TEXT"], selectcolor=p["ENTRY"], activebackground=p["BG"], font=_font(11)).pack(anchor="w", padx=14)

    def go():
        s, e = s_var.get(), e_var.get()
        d.destroy()
        if kind == "extrait":
            run_job(app, "GIF" if gif.get() else "Extrait", E.clip, fp, s, e, gif.get())
        else:
            run_job(app, "Passage enlevé", E.cut_middle, fp, s, e)
    bar = tk.Frame(d, bg=p["BG"]); bar.pack(pady=10)
    app.button(bar, "\u2714 Créer (Entrée)", go, "Créer le nouveau fichier")
    app.button(bar, "\u2716 Annuler (Échap)", d.destroy, "Fermer sans rien faire")
    d.bind("<Return>", lambda e: go()); d.bind("<Escape>", lambda e: d.destroy())
    changed("s")
    return d


def join_dialog(app, first=None):
    from .c04_recorder import VIDEO_EXT
    p = app.pal
    vids = [f for f in app.lib.scan() if f.lower().endswith(VIDEO_EXT)]
    if len(vids) < 2:
        messagebox.showinfo("Joindre", "Il faut au moins 2 vidéos dans la bibliothèque.", parent=app.root); return
    d = tk.Toplevel(app.root); d.title("\U0001f517 Joindre des vidéos"); d.configure(bg=p["BG"]); d.transient(app.root)
    tk.Label(d, text="Coche les vidéos à mettre bout à bout (dans l'ordre affiché, de haut en bas) :", bg=p["BG"],
             fg=p["TEXT"], font=_font(12, True)).pack(anchor="w", padx=14, pady=(12, 6))
    order = sorted(vids, key=lambda f: os.path.getmtime(f))  # plus ancienne d'abord = ordre naturel d'un cours
    box = tk.Frame(d, bg=p["BG"]); box.pack(fill="both", expand=True, padx=14)
    vs = []
    for f in order[-30:]:
        v = tk.BooleanVar(value=(f == first))
        tk.Checkbutton(box, text=os.path.basename(f), variable=v, bg=p["BG"], fg=p["TEXT"], selectcolor=p["ENTRY"],
                       activebackground=p["BG"], font=_font(11), anchor="w").pack(fill="x")
        vs.append((f, v))

    def go():
        sel = [f for f, v in vs if v.get()]
        if len(sel) < 2:
            messagebox.showinfo("Joindre", "Coche au moins 2 vidéos.", parent=d); return
        d.destroy()
        run_job(app, "Montage", E.join, sel)
    bar = tk.Frame(d, bg=p["BG"]); bar.pack(pady=10)
    app.button(bar, "\U0001f517 Joindre", go, "Créer « Montage … .mp4 »")
    app.button(bar, "\u2716 Annuler", d.destroy, "Fermer")
    d.bind("<Escape>", lambda e: d.destroy())
    return d


# ------------------------------------------------------------------ ℹ resume + reperes
def card_dialog(app, fp):
    p = app.pal
    c = read_card(fp)
    marks = list(c.get("reperes") or []) or read_chapters(fp)
    d = tk.Toplevel(app.root); d.title("\u2139 Résumé"); d.configure(bg=p["BG"]); d.transient(app.root)
    tk.Label(d, text=os.path.splitext(os.path.basename(fp))[0], bg=p["BG"], fg=p["TEXT"], font=_font(14, True)).pack(
        anchor="w", padx=14, pady=(12, 4))
    try:
        size = os.path.getsize(fp)
    except OSError:
        size = 0
    src = {"ecran": "\U0001f5a5 Écran complet", "moniteur": "\U0001f5a5 Moniteur", "fenetre": "\U0001fa9f Fenêtre",
           "zone": "\u25ad Zone", "son": "\U0001f3a4 Son seulement"}.get(c.get("source") or "", "—")
    rows = [("\u23f1 Durée", hms(c.get("duree") or E.probe(fp)["duration"])), ("\U0001f4be Taille", human_size(size)),
            ("\U0001f4c5 Date", str(c.get("cree") or datetime.fromtimestamp(os.path.getmtime(fp)).isoformat())[:16].replace("T", " à ")),
            ("\U0001f3af Quoi", src),
            ("\U0001f50a Son", ", ".join(x for x, k in (("ordi", "son_ordi"), ("micro", "micro")) if c.get(k)) or "—"),
            ("\u23f8 Pauses", str(c.get("pauses") or 0)), ("\U0001f516 Repères", str(len(marks)))]
    if c.get("archiveur"):
        rows.append(("\U0001f4e6 Archiveur", c["archiveur"]))
    g = tk.Frame(d, bg=p["PANEL"]); g.pack(fill="x", padx=14)
    for i, (k, v) in enumerate(rows):
        tk.Label(g, text=k, bg=p["PANEL"], fg=p["DIM"], font=_font(11), anchor="w").grid(row=i, column=0, sticky="w", padx=8)
        tk.Label(g, text=v, bg=p["PANEL"], fg=p["TEXT"], font=_font(11, True), anchor="w").grid(row=i, column=1, sticky="w")
    tk.Label(d, text="\U0001f516 Repères (clic = lire à partir de là)", bg=p["BG"], fg=p["ACC"], font=_font(12, True)).pack(
        anchor="w", padx=14, pady=(10, 2))
    lst = tk.Frame(d, bg=p["BG"]); lst.pack(fill="x", padx=14)
    if not marks:
        tk.Label(lst, text=f"Aucun. Pendant un enregistrement : {app.hk_label}+K ou le bouton \U0001f516 de la barre.",
                 bg=p["BG"], fg=p["DIM"], font=_font(10)).pack(anchor="w")
    for i, m in enumerate(marks):
        row = tk.Frame(lst, bg=p["BG"]); row.pack(fill="x", pady=1)
        tk.Button(row, text=f"\u25b6 {hms(m['t'])}", command=lambda t=m["t"]: E.play_at(fp, t), bg=p["BTN"], fg=p["TEXT"],
                  relief="flat", font=_font(10, True), width=9, cursor="hand2").pack(side="left")
        ent = tk.Entry(row, font=_font(11), bg=p["ENTRY"], fg=p["TEXT"], insertbackground=p["TEXT"], relief="flat", width=40)
        ent.insert(0, m.get("label") or "")
        ent.pack(side="left", padx=6, ipady=2)
        m["_ent"] = ent

    def save_labels():
        new = [{"t": m["t"], "label": m["_ent"].get().strip() or m.get("label")} for m in marks]
        c["reperes"] = new
        try:
            write_card(fp, c)
        except Exception:
            pass
        run_job(app, "Repères renommés", lambda: (write_chapters(fp, new, E.probe(fp)["duration"]) and fp) or fp)
        d.destroy()

    def copy():
        app.root.clipboard_clear(); app.root.clipboard_append(summary_text(fp))
        app.status("\U0001f4cb Résumé copié (avec les chapitres : colle-le dans la description YouTube, Teams…)")
    bar = tk.Frame(d, bg=p["BG"]); bar.pack(pady=10)
    if marks:
        app.button(bar, "\U0001f4be Garder les noms", save_labels, "Renomme les repères (et les chapitres de la vidéo)")
    app.button(bar, "\U0001f4cb Copier le résumé", copy, "Texte avec les chapitres, prêt à coller")
    app.button(bar, "Fermer", d.destroy, "Fermer")
    d.bind("<Escape>", lambda e: d.destroy())
    return d


# ------------------------------------------------------------------ 🔖 repere avec un nom (pendant l'enregistrement)
def marker_prompt(app):
    rec = app.rec
    if rec is None:
        return
    t_now = rec.elapsed()
    import time
    t_wall = time.time()
    p = app.pal
    w = tk.Toplevel(app.root); w.overrideredirect(True); w.attributes("-topmost", True); w.configure(bg=p["ACC"])
    exclude_from_capture(w)
    fr = tk.Frame(w, bg=p["DEEP"], padx=10, pady=8); fr.pack(padx=2, pady=2)
    tk.Label(fr, text=f"\U0001f516 Repère à {hms(t_now)} — nom (facultatif) :", bg=p["DEEP"], fg=p["TEXT"],
             font=_font(11, True)).pack(anchor="w")
    e = tk.Entry(fr, font=_font(12), width=34, bg=p["ENTRY"], fg=p["TEXT"], insertbackground=p["TEXT"], relief="flat")
    e.pack(fill="x", pady=4, ipady=3)
    tk.Label(fr, text="Entrée = ajouter · Échap = annuler", bg=p["DEEP"], fg=p["DIM"], font=_font(9)).pack(anchor="w")

    def ok(_e=None):
        lab = e.get()
        w.destroy()
        if app.rec is rec:
            rec.man["markers"] = rec.man.get("markers") or []
            n = len(rec.man["markers"]) + 1
            with rec._lock:
                rec.man["markers"].append({"t": round(t_now, 2), "label": lab.strip()[:80] or f"Repère {n}",
                                           "n": rec._attempt, "wall": t_wall})
            rec._save_man()
            app.marker_flash(f"\U0001f516 {lab.strip() or f'Repère {n}'} · {hms(t_now)}")
    e.bind("<Return>", ok); e.bind("<Escape>", lambda ev: w.destroy())
    w.update_idletasks()
    sw = w.winfo_screenwidth()
    w.geometry(f"+{(sw - w.winfo_reqwidth()) // 2}+{90}")
    w.focus_force(); e.focus_set()
    return w


# ------------------------------------------------------------------ ⏰ programmer
def schedule_dialog(app):
    p = app.pal
    d = tk.Toplevel(app.root); d.title("\u23f0 Programmer un enregistrement"); d.configure(bg=p["BG"]); d.transient(app.root)
    tk.Label(d, text="\u23f0 Programmer un enregistrement", bg=p["BG"], fg=p["TEXT"], font=_font(14, True)).pack(
        anchor="w", padx=14, pady=(12, 6))
    r1 = tk.Frame(d, bg=p["BG"]); r1.pack(fill="x", padx=14, pady=2)
    tk.Label(r1, text="Commencer à (HH:MM) :", bg=p["BG"], fg=p["TEXT"], font=_font(11)).pack(side="left")
    at = tk.Entry(r1, font=_font(12), width=7, bg=p["ENTRY"], fg=p["TEXT"], insertbackground=p["TEXT"], relief="flat")
    at.insert(0, (datetime.now() + timedelta(minutes=5)).strftime("%H:%M")); at.pack(side="left", padx=8, ipady=2)
    r2 = tk.Frame(d, bg=p["BG"]); r2.pack(fill="x", padx=14, pady=2)
    tk.Label(r2, text="Arrêter après (minutes, 0 = moi-même) :", bg=p["BG"], fg=p["TEXT"], font=_font(11)).pack(side="left")
    du = tk.Entry(r2, font=_font(12), width=6, bg=p["ENTRY"], fg=p["TEXT"], insertbackground=p["TEXT"], relief="flat")
    du.insert(0, str(app.cfg.get("sched_minutes") or 60)); du.pack(side="left", padx=8, ipady=2)
    tk.Label(d, text="Garde CaptureScreen ouvert (il peut être réduit). Les réglages actuels seront utilisés\n"
                     "(écran, fenêtre ou zone, son, micro…). Pas de compte à rebours à l'heure prévue.",
             bg=p["BG"], fg=p["DIM"], font=_font(9), justify="left").pack(anchor="w", padx=14, pady=4)

    def go():
        try:
            hh, mm = [int(x) for x in at.get().strip().replace("h", ":").split(":")[:2]]
            mins = max(0, int(float(du.get().strip() or 0)))
        except Exception:
            messagebox.showwarning("Programmer", "Écris l'heure comme 14:30 et une durée en minutes.", parent=d); return
        now = datetime.now()
        when = now.replace(hour=hh % 24, minute=mm % 60, second=0, microsecond=0)
        if when <= now:
            when += timedelta(days=1)
        app.cfg["sched_minutes"] = mins; save_cfg(app.cfg)
        d.destroy()
        app.schedule_recording(when, mins)
    bar = tk.Frame(d, bg=p["BG"]); bar.pack(pady=10)
    app.button(bar, "\u23f0 Programmer", go, "L'enregistrement démarrera tout seul")
    if getattr(app, "_sched", None):
        app.button(bar, "\U0001f6ab Annuler la programmation", lambda: (d.destroy(), app.cancel_schedule()), "Ne plus démarrer")
    app.button(bar, "Fermer", d.destroy, "Fermer")
    d.bind("<Escape>", lambda e: d.destroy())
    return d
