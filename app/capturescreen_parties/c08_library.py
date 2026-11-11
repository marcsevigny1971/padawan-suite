# -*- coding: utf-8 -*-
"""CaptureScreen - c08 : bibliotheque des enregistrements et captures (miniatures, ouvrir, dossier,
renommer, couper debut/fin, sous-titres, envoyer a l'Archiveur, Corbeille)."""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, simpledialog

from .c01_config import NOWIN, hms, human_size, logger
from .c02_win32 import open_path, recycle, reveal
from .c04_recorder import (IMAGE_EXT, VIDEO_EXT, frame_at, make_srt, probe_duration, send_to_archiveur, thumb, trim,
                           whisper_available)
from .c12_extras import AUDIO_EXT, CARD_SUFFIX, read_card
from . import c14_tools_ui as tools_ui

SORTS = [("recent", "\u2b07 Plus récents"), ("ancien", "\u2b06 Plus anciens"), ("nom", "\U0001f524 Nom"),
         ("long", "\u23f1 Plus longs"), ("gros", "\U0001f4be Plus gros")]

CARD_W, THUMB_W, THUMB_H = 300, 284, 160


class Library:
    def __init__(self, app, parent):
        self.app, self.p = app, app.pal
        p = self.p
        self.frame = tk.Frame(parent, bg=p["BG"])
        self.sel = None
        self.items = []
        self._dur = {}
        self._photos = {}
        self.filter = tk.StringVar(value="tout")
        self.query = tk.StringVar()
        top = tk.Frame(self.frame, bg=p["BG"]); top.pack(fill="x", pady=(0, 6))
        app.button(top, "\U0001f504 Actualiser", self.refresh, "Relire le dossier (F5)", side="right", small=True)
        tk.Label(top, text="\U0001f39e Mes enregistrements", bg=p["BG"], fg=p["TEXT"], font=("Segoe UI", 15, "bold")).pack(side="left")
        for val, txt in (("tout", "Tout"), ("video", "\U0001f3ac Vidéos"), ("son", "\U0001f3a4 Sons"), ("image", "\U0001f5bc Images")):
            rb = tk.Radiobutton(top, text=txt, value=val, variable=self.filter, command=self.refresh, indicatoron=False,
                                bg=p["BTN"], fg=p["TEXT"], selectcolor=p["ACC"], activebackground=p["BTNH"], relief="flat",
                                font=("Segoe UI", 11, "bold"), padx=10, pady=4, cursor="hand2")
            rb.pack(side="left", padx=(10 if val == "tout" else 2, 0))
        top2 = tk.Frame(self.frame, bg=p["BG"]); top2.pack(fill="x", pady=(0, 6))
        tk.Label(top2, text="\U0001f50e", bg=p["BG"], fg=p["DIM"], font=("Segoe UI Emoji", 12)).pack(side="left")
        en = tk.Entry(top2, textvariable=self.query, font=("Segoe UI", 12), bg=p["ENTRY"], fg=p["TEXT"],
                      insertbackground=p["TEXT"], relief="flat", width=14)
        en.pack(side="left", padx=(2, 10), ipady=4)
        app.tip(en, "Chercher par nom")
        self.query.trace_add("write", lambda *a: self.refresh())
        from tkinter import ttk
        self.sort = tk.StringVar(value=dict(SORTS).get(app.cfg.get("lib_sort", "recent"), SORTS[0][1]))
        sc = ttk.Combobox(top2, textvariable=self.sort, values=[s[1] for s in SORTS], state="readonly", width=14,
                          font=("Segoe UI", 10))
        sc.pack(side="left")
        sc.bind("<<ComboboxSelected>>", lambda e: self.refresh())
        app.tip(sc, "Trier : date, nom, durée, taille")
        app.button(top2, "\U0001f517 Joindre des vidéos…", lambda: tools_ui.join_dialog(app, self.sel),
                   "Mettre plusieurs vidéos bout à bout", side="right", small=True)
        self.stats_lab = tk.Label(self.frame, text="", bg=p["BG"], fg=p["ACC2"], font=("Segoe UI", 10, "bold"), anchor="w",
                                  justify="left")
        self.stats_lab.pack(fill="x", pady=(0, 4))
        app.tip(self.stats_lab, "Ton compteur : nombre d'enregistrements et temps enregistré (total, vidéos, sons, cette semaine)")
        self._stats_busy = False
        box = tk.Frame(self.frame, bg=p["BG"]); box.pack(fill="both", expand=True)
        self.cv = tk.Canvas(box, bg=p["BG"], highlightthickness=0)
        sb = tk.Scrollbar(box, command=self.cv.yview); sb.pack(side="right", fill="y")
        self.cv.configure(yscrollcommand=sb.set); self.cv.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.cv, bg=p["BG"])
        self.win_id = self.cv.create_window(0, 0, window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda e: self.cv.configure(scrollregion=self.cv.bbox("all")))
        self.cv.bind("<Configure>", self._relayout)
        for w in (self.cv, self.inner):
            w.bind("<Enter>", lambda e: self.cv.bind_all("<MouseWheel>", self._wheel))
            w.bind("<Leave>", lambda e: self.cv.unbind_all("<MouseWheel>"))
        self.empty = tk.Label(self.inner, bg=p["BG"], fg=p["DIM"], font=("Segoe UI", 13), justify="left",
                              text="Rien encore ! Clique sur \u23fa Enregistrer ou \U0001f4f7 Capture d'écran.\n"
                                   "Tes vidéos et images apparaîtront ici avec une miniature.")
        self._cols = 0

    def _wheel(self, e):
        self.cv.yview_scroll(int(-e.delta / 120) * 3, "units")

    # ---------------------------------------------------------- liste
    def scan(self):
        d = self.app.cfg["out_dir"]
        out = []
        try:
            for n in os.listdir(d):
                fp = os.path.join(d, n)
                if os.path.isfile(fp) and n.lower().endswith(VIDEO_EXT + IMAGE_EXT + AUDIO_EXT):
                    out.append(fp)
        except OSError:
            pass
        out.sort(key=lambda f: os.path.getmtime(f), reverse=True)
        return out

    def refresh(self, select=None):
        f, q = self.filter.get(), self.query.get().strip().lower()
        items = []
        for fp in self.scan():
            low = fp.lower()
            kind = "video" if low.endswith(VIDEO_EXT) else ("son" if low.endswith(AUDIO_EXT) else "image")
            if f != "tout" and f != kind:
                continue
            if q and q not in os.path.basename(fp).lower():
                continue
            items.append(fp)
        key = next((k for k, lab in SORTS if lab == self.sort.get()), "recent")
        if self.app.cfg.get("lib_sort") != key:
            self.app.cfg["lib_sort"] = key
        try:
            if key == "ancien":
                items.reverse()
            elif key == "nom":
                items.sort(key=lambda x: os.path.basename(x).lower())
            elif key == "long":
                items.sort(key=lambda x: -(self._dur.get(x) or (read_card(x).get("duree") or 0)))
            elif key == "gros":
                items.sort(key=lambda x: -os.path.getsize(x))
        except OSError:
            pass
        self.items = items
        if select:
            self.sel = select
        self._build()
        self._update_stats()

    def _update_stats(self):
        """Compteur en arriere-plan (fiches resume = instantane ; sinon ffprobe une fois, puis cache)."""
        if self._stats_busy:
            self._stats_again = True
            return
        self._stats_busy, self._stats_again = True, False
        files = self.scan()

        def go():
            try:
                from .c15_finish import compute_stats, stats_text
                txt = stats_text(compute_stats(files, self._dur))
            except Exception:
                logger.exception("compteur")
                txt = ""

            def put():
                self._stats_busy = False
                try:
                    self.stats_lab.configure(text=txt)
                except Exception:
                    pass
                if self._stats_again:
                    self._update_stats()
            self.app.root.after(0, put)
        threading.Thread(target=go, daemon=True).start()

    def _relayout(self, e=None):
        self.cv.itemconfigure(self.win_id, width=self.cv.winfo_width())
        cols = max(1, self.cv.winfo_width() // (CARD_W + 12))
        if cols != self._cols:
            self._cols = cols
            self._build()

    def _build(self):
        for w in self.inner.winfo_children():
            if w is not self.empty:
                w.destroy()
        self.cards = {}
        if not self.items:
            self.empty.grid(row=0, column=0, padx=20, pady=30, sticky="w")
            return
        self.empty.grid_forget()
        cols = max(1, self._cols or 3)
        for i, fp in enumerate(self.items[:300]):
            c = self._card(fp)
            c.grid(row=i // cols, column=i % cols, padx=6, pady=6, sticky="n")
            self.cards[fp] = c
        self._mark()
        threading.Thread(target=self._load_thumbs, args=(list(self.items[:300]),), daemon=True).start()

    def _card(self, fp):
        p, app = self.p, self.app
        isv = fp.lower().endswith(VIDEO_EXT)
        isa = fp.lower().endswith(AUDIO_EXT)
        c = tk.Frame(self.inner, bg=p["CARD"], highlightthickness=3, highlightbackground=p["CARD"], width=CARD_W)
        if not hasattr(self, "_blank"):
            self._blank = tk.PhotoImage(width=THUMB_W, height=THUMB_H)
        im = tk.Label(c, bg=p["DEEP"], image=self._blank, compound="center", text="\u23f3", fg=p["DIM"], cursor="hand2",
                      font=("Segoe UI Emoji", 24))
        im.pack(padx=6, pady=(6, 2))
        im.bind("<Double-Button-1>", lambda e: open_path(fp))
        name = os.path.splitext(os.path.basename(fp))[0]
        tk.Label(c, text=name[:40], bg=p["CARD"], fg=p["TEXT"], font=("Segoe UI", 11, "bold"), anchor="w").pack(fill="x", padx=8)
        info = tk.Label(c, text=self._info(fp), bg=p["CARD"], fg=p["DIM"], font=("Segoe UI", 9), anchor="w")
        info.pack(fill="x", padx=8)
        c._img, c._info = im, info
        bar = tk.Frame(c, bg=p["CARD"]); bar.pack(fill="x", padx=4, pady=(2, 6))
        acts = [("\u25b6", lambda: open_path(fp), "Ouvrir / lire (Entrée, double-clic)"),
                ("\U0001f4c2", lambda: reveal(fp), "Montrer dans le dossier"),
                ("\u270f", lambda: self.rename(fp), "Renommer (F2)")]
        if isv:
            acts += [("\u2702", lambda: self.trim_dialog(fp), "Couper le début / la fin (rapide, sans perte)"),
                     ("\U0001f4ac", lambda: self.subtitles(fp), "Sous-titres automatiques .srt (Whisper)"),
                     ("\U0001f4e6", lambda: self.to_archiveur(fp), "Envoyer une copie à l'Archiveur")]
        acts += [("\U0001f5d1", lambda: self.delete(fp), "Mettre à la Corbeille (Suppr)")]
        for txt, cmd, tip in acts:
            b = tk.Button(bar, text=txt, command=cmd, bg=p["BTN"], fg=p["TEXT"], activebackground=p["BTNH"], relief="flat",
                          font=("Segoe UI Emoji", 12), width=3, cursor="hand2")
            b.pack(side="left", padx=1)
            app.tip(b, tip)
        if isv or isa:  # 2e rangee : resume + outils de montage
            bar2 = tk.Frame(c, bg=p["CARD"]); bar2.pack(fill="x", padx=4, pady=(0, 6))
            for txt, cmd, tip in (("\u2139 Résumé", lambda: tools_ui.card_dialog(app, fp),
                                   "Durée, taille, date, repères cliquables (lire à partir de là), résumé à copier"),
                                  ("\U0001f6e0 Outils", lambda: tools_ui.tools_dialog(app, fp),
                                   "Version à partager, extrait / GIF, enlever un passage, joindre, son amélioré, MP3…")):
                b = tk.Button(bar2, text=txt, command=cmd, bg=p["BTN"], fg=p["TEXT"], activebackground=p["BTNH"],
                              relief="flat", font=("Segoe UI Emoji", 10, "bold"), cursor="hand2", padx=6)
                b.pack(side="left", padx=1, fill="x", expand=True)
                app.tip(b, tip)
        for w in (c, im, info):
            w.bind("<Button-1>", lambda e, f=fp: self.select(f), add="+")
        return c

    def _info(self, fp):
        try:
            st = os.stat(fp)
        except OSError:
            return ""
        d = self._dur.get(fp)
        bits = []
        if fp.lower().endswith(VIDEO_EXT + AUDIO_EXT):
            bits.append(hms(d) if d is not None else "…")
            if os.path.isfile(os.path.splitext(fp)[0] + ".srt"):
                bits.append("\U0001f4ac srt")
            nm = len(read_card(fp).get("reperes") or [])
            if nm:
                bits.append(f"\U0001f516 {nm}")
        bits += [human_size(st.st_size), datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")]
        return "  ·  ".join(bits)

    def _load_thumbs(self, items):
        for fp in items:
            try:
                if fp.lower().endswith(VIDEO_EXT + AUDIO_EXT) and fp not in self._dur:
                    self._dur[fp] = probe_duration(fp)
                t = thumb(fp, THUMB_W)
                self.app.root.after(0, self._set_thumb, fp, t)
            except Exception:
                logger.exception("miniature")

    def _set_thumb(self, fp, t):
        c = self.cards.get(fp)
        if not c or not c.winfo_exists():
            return
        c._info.configure(text=self._info(fp))
        if not t:
            c._img.configure(text="\U0001f3ac" if fp.lower().endswith(VIDEO_EXT) else
                             ("\U0001f3b5" if fp.lower().endswith(AUDIO_EXT) else "\U0001f5bc"))
            return
        try:
            from PIL import Image, ImageTk
            im = Image.open(t); im.thumbnail((THUMB_W, THUMB_H))
            ph = ImageTk.PhotoImage(im)
            self._photos[fp] = ph
            c._img.configure(image=ph, text="")
        except Exception:
            pass

    def select(self, fp):
        self.sel = fp; self._mark()

    def _mark(self):
        for fp, c in getattr(self, "cards", {}).items():
            c.configure(highlightbackground=self.p["ACC"] if fp == self.sel else self.p["CARD"])

    # ---------------------------------------------------------- actions clavier (fenetre principale)
    def key_open(self):
        if self.sel:
            open_path(self.sel)

    def key_rename(self):
        if self.sel:
            self.rename(self.sel)

    def key_delete(self):
        if self.sel:
            self.delete(self.sel)

    # ---------------------------------------------------------- actions
    def _siblings(self, fp):
        return [s for s in (os.path.splitext(fp)[0] + ".srt", os.path.splitext(fp)[0] + CARD_SUFFIX) if os.path.isfile(s)]

    def rename(self, fp):
        base, ext = os.path.splitext(fp)
        new = simpledialog.askstring("Renommer", "Nouveau nom :", initialvalue=os.path.basename(base), parent=self.app.root)
        if not new or not new.strip():
            return
        new = "".join(ch for ch in new.strip() if ch not in '\\/:*?"<>|')
        dst = os.path.join(os.path.dirname(fp), new + ext)
        if os.path.exists(dst):
            messagebox.showwarning("Renommer", "Ce nom existe déjà.", parent=self.app.root); return
        try:
            for s in self._siblings(fp):
                os.replace(s, os.path.join(os.path.dirname(fp), new + s[len(base):]))
            os.replace(fp, dst)
            self.app.status(f"\u270f Renommé : {new}{ext}")
            self.refresh(select=dst)
        except OSError as e:
            messagebox.showerror("Renommer", f"Impossible : {e}\n(Le fichier est peut-être ouvert dans un lecteur.)",
                                 parent=self.app.root)

    def delete(self, fp):
        if not messagebox.askyesno("Corbeille", f"Mettre à la Corbeille ?\n\n{os.path.basename(fp)}\n\n"
                                   "(Tu pourras le récupérer dans la Corbeille de Windows.)", parent=self.app.root):
            return
        ok = recycle(fp)
        for s in self._siblings(fp):
            recycle(s)
        self.app.status("\U0001f5d1 Mis à la Corbeille." if ok else "\u26a0 Impossible (fichier ouvert dans un lecteur ?)")
        self.sel = None
        self.refresh()

    def to_archiveur(self, fp):
        self.app.status("\U0001f4e6 Envoi à l'Archiveur…")

        def go():
            try:
                folder = send_to_archiveur(fp, log=lambda m: self.app.root.after(0, self.app.status, m))
                self.app.root.after(0, self.app.status, f"\U0001f4e6 Dans l'Archiveur : {os.path.basename(folder)} "
                                                         "(rouvre l'Archiveur ou F5 pour la voir)")
            except Exception as e:
                logger.exception("archiveur")
                self.app.root.after(0, self.app.status, f"\u26a0 Archiveur : {e}")
        threading.Thread(target=go, daemon=True).start()

    def subtitles(self, fp):
        if not whisper_available():
            if not messagebox.askyesno(
                    "Sous-titres automatiques",
                    "Les sous-titres utilisent Whisper (faster-whisper), le même outil que la transcription de l'Archiveur.\n\n"
                    "Il n'est pas encore installé. L'installer maintenant ? (environ 100 à 200 Mo, une seule fois ; "
                    "le modèle « base » se télécharge au premier usage)", parent=self.app.root):
                return
            self.app.status("\u2b07 Installation de faster-whisper… (quelques minutes)")

            def inst():
                exe = sys.executable
                if exe.lower().endswith("pythonw.exe") and os.path.isfile(exe[:-11] + "python.exe"):
                    exe = exe[:-11] + "python.exe"
                r = subprocess.run([exe, "-m", "pip", "install", "--disable-pip-version-check", "faster-whisper"],
                                   capture_output=True, creationflags=NOWIN)
                if r.returncode == 0:
                    self.app.root.after(0, self._srt_go, fp)
                else:
                    self.app.root.after(0, self.app.status, "\u26a0 Installation de faster-whisper impossible (voir le journal).")
                    logger.error("pip faster-whisper: %s", (r.stderr or b"").decode("utf-8", "replace")[-800:])
            threading.Thread(target=inst, daemon=True).start()
            return
        self._srt_go(fp)

    def _srt_go(self, fp):
        self.app.status("\U0001f4ac Sous-titres en cours… (environ le quart de la durée de la vidéo)")

        def go():
            try:
                out = make_srt(fp, log=lambda m: self.app.root.after(0, self.app.status, m))
                self.app.root.after(0, self.app.status, f"\U0001f4ac Sous-titres prêts : {os.path.basename(out)} "
                                                         "(les lecteurs les affichent automatiquement)")
                self.app.root.after(0, self.refresh)
            except Exception as e:
                logger.exception("srt")
                self.app.root.after(0, self.app.status, f"\u26a0 Sous-titres : {e}")
        threading.Thread(target=go, daemon=True).start()

    # ---------------------------------------------------------- coupe rapide
    def trim_dialog(self, fp):
        p, app = self.p, self.app
        dur = self._dur.get(fp) or probe_duration(fp)
        if dur <= 1:
            messagebox.showinfo("Couper", "Vidéo trop courte pour être coupée.", parent=app.root); return
        d = tk.Toplevel(app.root); d.title("\u2702 Couper le début et la fin"); d.configure(bg=p["BG"])
        d.transient(app.root); d.grab_set()
        tk.Label(d, text=os.path.basename(fp), bg=p["BG"], fg=p["TEXT"], font=("Segoe UI", 13, "bold")).pack(padx=14, pady=(12, 4))
        pv = tk.Label(d, bg=p["DEEP"], width=64, height=18); pv.pack(padx=14, pady=4)
        s_var, e_var = tk.DoubleVar(value=0.0), tk.DoubleVar(value=round(dur, 1))
        lab = tk.Label(d, bg=p["BG"], fg=p["ACC"], font=("Segoe UI", 12, "bold")); lab.pack()
        job = {"id": None, "ph": None}

        def show(t):
            def run():
                img = frame_at(fp, t)
                if img:
                    d.after(0, put, img)
            threading.Thread(target=run, daemon=True).start()

        def put(img):
            try:
                from PIL import Image, ImageTk
                im = Image.open(img); im.thumbnail((640, 360)); job["ph"] = ImageTk.PhotoImage(im)
                pv.configure(image=job["ph"], width=640, height=360)
            except Exception:
                pass

        def changed(which):
            s, e = s_var.get(), e_var.get()
            if e - s < 1:
                (s_var.set(max(0, e - 1)) if which == "s" else e_var.set(min(dur, s + 1)))
            lab.configure(text=f"Garder de {hms(s_var.get())} à {hms(e_var.get())}  →  {hms(e_var.get() - s_var.get())}")
            if job["id"]:
                d.after_cancel(job["id"])
            job["id"] = d.after(250, show, s_var.get() if which == "s" else max(0, e_var.get() - 0.5))
        for txt, var, w in (("Début", s_var, "s"), ("Fin", e_var, "e")):
            row = tk.Frame(d, bg=p["BG"]); row.pack(fill="x", padx=14)
            tk.Label(row, text=txt, width=6, bg=p["BG"], fg=p["TEXT"], font=("Segoe UI", 11, "bold")).pack(side="left")
            tk.Scale(row, from_=0, to=round(dur, 1), resolution=0.5, orient="horizontal", variable=var, showvalue=False,
                     length=560, bg=p["BG"], fg=p["TEXT"], troughcolor=p["ENTRY"], highlightthickness=0, sliderlength=26,
                     width=18, command=lambda v, ww=w: changed(ww)).pack(side="left", fill="x", expand=True)
        rep = tk.BooleanVar(value=False)
        tk.Checkbutton(d, text="Remplacer l'original (l'ancien va à la Corbeille)", variable=rep, bg=p["BG"], fg=p["TEXT"],
                       selectcolor=p["ENTRY"], activebackground=p["BG"], font=("Segoe UI", 11)).pack(anchor="w", padx=14, pady=4)
        tk.Label(d, text="Coupe rapide sans perte de qualité : précise à environ 1 seconde.", bg=p["BG"], fg=p["DIM"],
                 font=("Segoe UI", 9)).pack(anchor="w", padx=14)

        def go():
            s, e = s_var.get(), e_var.get()
            d.destroy()
            app.status("\u2702 Coupe en cours…")

            def run():
                try:
                    out = trim(fp, s, e, replace=rep.get())
                    app.root.after(0, app.status, f"\u2702 Coupé : {os.path.basename(out)}")
                    app.root.after(0, self.refresh, out)
                except Exception as ex:
                    app.root.after(0, app.status, f"\u26a0 Coupe : {ex}")
            threading.Thread(target=run, daemon=True).start()
        bar = tk.Frame(d, bg=p["BG"]); bar.pack(pady=10)
        app.button(bar, "\u2702 Couper (Entrée)", go, "Créer la version coupée")
        app.button(bar, "\u2716 Annuler (Échap)", d.destroy, "Fermer sans rien changer")
        d.bind("<Return>", lambda e: go()); d.bind("<Escape>", lambda e: d.destroy())
        changed("s")
