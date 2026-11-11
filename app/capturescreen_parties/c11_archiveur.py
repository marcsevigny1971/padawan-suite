# -*- coding: utf-8 -*-
"""CaptureScreen - c11 : lien avec l'Archiveur.
L'Archiveur lance  capturescreen1.py --enregistrer --mode ecran|fenetre|zone --titre ... --root ... --dossier ...
(si CaptureScreen est deja ouvert, la demande passe par un petit fichier lu par l'instance ouverte).
Quand la video est prete, on depose un « bon de livraison » dans <PRIV>\\pour_archiveur\\ : l'Archiveur
(ouvert maintenant ou plus tard) range la video dans la fiche et affiche « Video ajoutee a la fiche ».
Aucun contournement de protection : on enregistre l'ecran tel que Windows l'affiche."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import tkinter as tk
import uuid
import webbrowser
from datetime import datetime

from .c01_config import HERE, PRIV, logger, save_cfg
from .c02_win32 import IS_WIN, exclude_from_capture

REQ_FILE = os.path.join(PRIV, "demande_archiveur.json")
RESULTS = os.path.join(PRIV, "pour_archiveur")


def request_from_args(a) -> dict:
    return {"id": uuid.uuid4().hex[:12], "titre": (a.titre or "").strip(), "mode": a.mode or "ecran",
            "root": a.root or "", "dossier": a.dossier or "", "url": a.url or "", "ouvrir_site": bool(a.ouvrir_site),
            "son": a.son, "micro": a.micro, "webcam": a.webcam, "touches": a.touches, "clics": a.clics,
            "auto_stop": float(a.auto_stop or 0), "sans_compte": bool(a.sans_compte), "test": bool(a.test_handoff),
            "at": time.time()}


def write_request(req: dict) -> None:
    tmp = REQ_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(req, f, ensure_ascii=False)
    os.replace(tmp, REQ_FILE)


def take_request():
    """Demande en attente (deposee par une 2e instance), retiree une seule fois."""
    if not os.path.isfile(REQ_FILE):
        return None
    claim = REQ_FILE + f".{os.getpid()}"
    try:
        os.replace(REQ_FILE, claim)
        with open(claim, encoding="utf-8") as f:
            req = json.load(f)
        os.remove(claim)
    except Exception:
        return None
    if time.time() - float(req.get("at") or 0) > 120:  # vieille demande oubliee
        return None
    return req


def video_name(title: str) -> str:
    t = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", title or "").strip().rstrip(".")[:70] or "Enregistrement"
    return f"{t} - {datetime.now():%Y-%m-%d %Hh%M}"


def write_result(req: dict, out: str, duration=None) -> str:
    os.makedirs(RESULTS, exist_ok=True)
    srt = os.path.splitext(out)[0] + ".srt"
    data = {"id": req.get("id") or uuid.uuid4().hex[:12], "root": req.get("root") or archiveur_root(),
            "dossier": req.get("dossier") or "", "titre": req.get("titre") or "", "url": req.get("url") or "",
            "fichier": out, "srt": srt if os.path.isfile(srt) else "", "duree": duration,
            "cree": datetime.now().isoformat(timespec="seconds")}
    try:  # reperes (chapitres) et fiche resume, pour l'Archiveur
        from .c12_extras import read_card
        card = read_card(out)
        data["reperes"] = card.get("reperes") or []
        data["son_seulement"] = bool(card.get("son_seulement"))
    except Exception:
        pass
    p = os.path.join(RESULTS, f"{datetime.now():%Y%m%d_%H%M%S}_{data['id']}.json")
    with open(p + ".tmp", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(p + ".tmp", p)
    return p


def archiveur_root() -> str:
    sys.path.insert(0, HERE)
    try:
        import padawan_commun as pc
        return pc.archiveur_root()
    except Exception:
        return r"C:\web\FTP_HOME\ARCHIVEUR"


def archiveur_running() -> bool:
    if not IS_WIN:
        return False
    try:
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenMutexW(0x00100000, False, "Local\\ArchiveurPadawanUnique")
        if h:
            k.CloseHandle(h)
            return True
    except Exception:
        pass
    return False


def launch_archiveur() -> None:
    arch = os.path.join(HERE, "archiveur5.py")
    exe = sys.executable
    d, n = os.path.split(exe)
    if n.lower() == "python.exe" and os.path.isfile(os.path.join(d, "pythonw.exe")):
        exe = os.path.join(d, "pythonw.exe")
    if os.path.isfile(arch):
        subprocess.Popen([exe, arch], cwd=HERE, close_fds=True)


class ArchiveurLink:
    """Melange pour App : demandes venues de l'Archiveur → enregistrement → video livree a la fiche."""

    handoff = None        # demande en cours (dict) ou None
    handoff_fresh = False  # True : CaptureScreen a ete ouvert juste pour ca (on se referme a la fin)

    def _poll_requests(self):
        try:
            req = take_request()
            if req:
                self.handle_request(req, fresh=False)
        except Exception:
            logger.exception("demande archiveur")
        self.root.after(700, self._poll_requests)

    def handle_request(self, req: dict, fresh: bool):
        if self.rec is not None or getattr(self, "_starting", False):
            self.status("\u26a0 Un enregistrement est déjà en cours : arrête-le d'abord (Ctrl+Maj+R).")
            self._finishing_toast("\u26a0 Un enregistrement est déjà en cours — arrête-le d'abord (Ctrl+Maj+R)", 4000)
            if self.bar is not None:
                try:
                    self.bar.win.lift()
                except Exception:
                    pass
            return
        self.handoff, self.handoff_fresh = req, fresh
        m = req.get("mode") if req.get("mode") in ("ecran", "fenetre", "zone", "son") else "ecran"
        self.cfg["source"] = m
        for k_req, k_cfg in (("son", "sys_audio"), ("micro", "mic"), ("webcam", "webcam"),
                             ("touches", "keys"), ("clics", "clicks")):
            if req.get(k_req) is not None:
                self.cfg[k_cfg] = bool(int(req[k_req]))
        self._test_mode = bool(req.get("test"))
        if req.get("sans_compte"):
            self._saved_countdown = self.cfg.get("countdown")
            self.cfg["countdown"] = 0
        if not req.get("test"):
            save_cfg(self.cfg)
        for k, v in self.vars.items():
            if k in self.cfg and isinstance(v, tk.BooleanVar):
                try:
                    v.set(bool(self.cfg[k]))
                except Exception:
                    pass
        try:
            if "source" in self.vars:
                self.vars["source"].set(m)
            self._source_changed()
        except Exception:
            pass
        if not fresh:
            self.root.withdraw()
        what = f"« {req.get('titre')[:60]} »" if req.get("titre") else "une nouvelle fiche"
        self.status(f"\U0001f3a5 Demande de l'Archiveur : vidéo pour {what}")
        if req.get("url") and req.get("ouvrir_site"):
            try:
                webbrowser.open(req["url"])
            except Exception:
                logger.exception("ouvrir site")
            self.root.after(1200, self._ready_prompt)
        else:
            self.root.after(150, self._handoff_pick)

    def _ready_prompt(self):
        """Petite fenetre au premier plan (invisible dans la video) : prepare la page, puis ⏺ Commencer."""
        p = self.pal
        t = tk.Toplevel(self.root)
        t.title("CaptureScreen — prêt ?")
        t.configure(bg=p["PANEL"])
        t.attributes("-topmost", True)
        t.resizable(False, False)
        tk.Label(t, text="\U0001f310 Le site s'ouvre dans ton navigateur.", bg=p["PANEL"], fg=p["TEXT"],
                 font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=16, pady=(12, 2))
        tk.Label(t, text="Prépare la page comme tu veux (connexion, plein écran, début de la vidéo…),\n"
                         "puis clique « \u23fa Commencer » : 3-2-1 et ça enregistre.\n"
                         "Les vidéos protégées (Netflix, Tubi…) peuvent apparaître en noir : c'est voulu par le site.",
                 bg=p["PANEL"], fg=p["DIM"], font=("Segoe UI", 10), justify="left").pack(anchor="w", padx=16)
        row = tk.Frame(t, bg=p["PANEL"])
        row.pack(fill="x", padx=16, pady=12)

        def go():
            t.destroy()
            self.root.after(200, self._handoff_pick)

        def cancel():
            t.destroy()
            self._handoff_cancel()
        b = tk.Button(row, text="\u23fa  Commencer", command=go, bg=p["REC"], fg="white", font=("Segoe UI", 13, "bold"),
                      bd=0, padx=18, pady=6, cursor="hand2", activebackground=p["REC"])
        b.pack(side="left")
        tk.Button(row, text="Annuler", command=cancel, bg=p["BTN"], fg=p["TEXT"], font=("Segoe UI", 10), bd=0,
                  padx=12, pady=6).pack(side="right")
        t.bind("<Return>", lambda e: go())
        t.bind("<Escape>", lambda e: cancel())
        t.protocol("WM_DELETE_WINDOW", cancel)
        t.update_idletasks()
        sw = t.winfo_screenwidth()
        t.geometry(f"+{sw - t.winfo_reqwidth() - 30}+{40}")
        exclude_from_capture(t)
        self._ready_win = t
        if self.handoff and self.handoff.get("test"):  # test automatique : on « clique » Commencer
            t.after(1500, go)

    def _handoff_pick(self):
        from .c05_overlays import pick_window, select_region
        src = self.cfg.get("source")
        if src == "fenetre":
            self.win_hwnd = None

            def done(res):
                if not res:
                    return self._handoff_cancel()
                self.win_hwnd, title = res
                self.cfg["window_title"] = title[:120]
                self._source_changed()
                self.start_recording()
            pick_window(self.root, self.pal, done)
        elif src == "zone":
            def done(r):
                if not r:
                    return self._handoff_cancel()
                if r == "ecran":
                    self.cfg["source"] = "ecran"
                else:
                    self.cfg["region"] = list(r)
                self._source_changed()
                self.start_recording()
            select_region(self.root, done)
        else:
            self.start_recording()

    def _handoff_cancel(self):
        self.status("Enregistrement annulé.")
        self._handoff_end(cancelled=True)

    def _handoff_end(self, cancelled=False):
        fresh = self.handoff_fresh
        if getattr(self, "_saved_countdown", None) is not None:
            self.cfg["countdown"] = self._saved_countdown
            self._saved_countdown = None
        self.handoff, self.handoff_fresh = None, False
        if fresh:
            self.root.after(300 if cancelled else 2500, self.quit_quiet)
        else:
            self._restore_normal()

    def handoff_saved(self, req: dict, out: str, duration=None):
        try:
            write_result(req, out, duration)
        except Exception:
            logger.exception("bon de livraison")
            self.status("\u26a0 La vidéo est prête mais n'a pas pu être envoyée à l'Archiveur : " + os.path.basename(out))
            return
        self.status(f"\U0001f4e6 Vidéo envoyée à l'Archiveur : {os.path.basename(out)}")
        if not req.get("test") and not archiveur_running():
            try:
                launch_archiveur()
            except Exception:
                logger.exception("ouvrir l'Archiveur")
        self._finishing_toast(f"\u2705 Vidéo prête — elle s'ajoute à la fiche dans l'Archiveur")

    def _finishing_toast(self, text, ms=2400):
        try:
            p = self.pal
            t = tk.Toplevel(self.root)
            t.overrideredirect(True)
            t.attributes("-topmost", True)
            tk.Label(t, text=text, bg=p["CARD"], fg=p["TEXT"], font=("Segoe UI", 12, "bold"), padx=18, pady=10).pack()
            t.update_idletasks()
            sw, sh = t.winfo_screenwidth(), t.winfo_screenheight()
            t.geometry(f"+{sw - t.winfo_reqwidth() - 30}+{sh - t.winfo_reqheight() - 90}")
            t.after(ms, t.destroy)
        except Exception:
            pass

    def quit_quiet(self):
        try:
            self.hk.stop()
        except Exception:
            pass
        if not getattr(self, "_test_mode", False):
            save_cfg(self.cfg)
        try:  # plus de minuteries en attente (evite « invalid command name » a la fermeture)
            for j in self.root.tk.splitlist(self.root.tk.call("after", "info")):
                self.root.after_cancel(j)
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass
