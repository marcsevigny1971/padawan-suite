# -*- coding: utf-8 -*-
"""CaptureScreen - c01 : chemins, reglages, journal, detection ffmpeg (meme logique que l'Archiveur)."""
from __future__ import annotations

import glob
import json
import logging
import os
import shutil
import subprocess
import sys

APP = "CaptureScreen"
VERSION = "1.3.0"
APP_FILE_VER = 1
IS_WIN = os.name == "nt"
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0) if IS_WIN else 0
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # dossier du projet Padawan


def private_dir() -> str:
    """Reglages : C:\\web_private\\CaptureScreen (PC de Marc, jamais sous FTP_HOME), sinon %APPDATA%\\Padawan\\CaptureScreen."""
    env = os.environ.get("CAPTURESCREEN_CONFIG", "").strip()
    if env:
        d = env
    elif IS_WIN and os.path.isdir(r"C:\web_private"):
        d = r"C:\web_private\CaptureScreen"
    else:
        d = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "Padawan", "CaptureScreen")
    os.makedirs(d, exist_ok=True)
    return d


def default_out_dir() -> str:
    env = os.environ.get("CAPTURESCREEN_DATA", "").strip()
    if env:
        return env
    root = os.environ.get("PADAWAN_DATA", "").strip()
    if root:
        return os.path.join(root, "Captures")
    if IS_WIN and os.path.isdir(r"C:\web\FTP_HOME"):
        return r"C:\web\FTP_HOME\CAPTURES"
    v = os.path.join(os.path.expanduser("~"), "Videos")
    return os.path.join(v if os.path.isdir(v) else os.path.expanduser("~"), "CaptureScreen")


PRIV = private_dir()
CFG_FILE = os.path.join(PRIV, "config.json")
LOG_FILE = os.path.join(PRIV, "capturescreen.log")
THUMBS = os.path.join(PRIV, "miniatures")
TMP_DIR = os.path.join(PRIV, "_en_cours")

DEFAULTS = {
    "out_dir": "",
    "source": "ecran",          # ecran | moniteur | zone | fenetre
    "monitor": 0,
    "region": None,             # [x, y, w, h] pixels physiques
    "window_title": "",
    "fps": 30,
    "quality": "bonne",         # haute | bonne | legere
    "engine": "auto",           # auto (ddagrab puis gdigrab) | gdigrab
    "encoder": "auto",          # auto | nvenc | x264
    "sys_audio": True,
    "speaker": "",              # vide = haut-parleurs par defaut
    "mic": False,
    "mic_name": "",
    "clicks": True,
    "keys": True,
    "keys_shortcuts_only": True,  # n'affiche pas les lettres tapees (mots de passe) : seulement Ctrl/Alt/Win + touche, F1...
    "cursor": True,
    "webcam": False,
    "webcam_name": "",
    "countdown": 3,
    "hide_bar": True,           # la barre flottante n'apparait pas dans la video
    "hotkey_mods": "ctrl+shift",  # ctrl+shift | ctrl+alt+shift
    "hotkeys_idle": "rec",
    "end_screen": True,           # ecran « Bravo ! » apres chaque enregistrement
    "notify_done": True,          # notification Windows quand la video est prete        # hors enregistrement : rec (seulement Ctrl+Maj+R) | all | none
    "spot_radius": 150,
    "zoom": 2.0,
    "board_color": "blanc",
    "timer_minutes": 5,
    "last_preset": "",
    "cam_pos": "bd",            # bd | bg | hd | hg (coin de la bulle webcam)
    "cam_size": "moyenne",      # petite | moyenne | grande
    "auto_stop_min": 0,         # arreter tout seul apres N minutes (0 = jamais)
    "audio_fmt": "m4a",         # « son seulement » : m4a | mp3
    "share_clean_audio": True,
    "sched_minutes": 60,
    "segment_minutes": 5,       # sauvegarde de securite : un morceau MKV toutes les N minutes
}

QUALITY = {  # cle : (libelle, crf x264, cq nvenc)
    "haute": ("Haute (fichiers plus gros)", 18, 21),
    "bonne": ("Bonne (recommandée)", 23, 25),
    "legere": ("Légère (petits fichiers)", 28, 30),
}

PRESETS = {
    "cours": {"label": "\U0001f393 Cours plein écran", "tip": "Écran entier, 30 i/s, son de l'ordinateur + micro, clics et raccourcis affichés.",
              "set": {"source": "ecran", "fps": 30, "quality": "bonne", "sys_audio": True, "mic": True,
                      "clicks": True, "keys": True, "countdown": 3}},
    "tuto": {"label": "\U0001fa9f Tutoriel fenêtre", "tip": "Une seule fenêtre (à choisir), 30 i/s, micro, clics et raccourcis.",
             "set": {"source": "fenetre", "fps": 30, "quality": "bonne", "sys_audio": False, "mic": True,
                     "clicks": True, "keys": True, "countdown": 3}},
    "zone": {"label": "\u25ad Zone", "tip": "Une zone que tu traces à la souris, 30 i/s, son de l'ordinateur.",
             "set": {"source": "zone", "fps": 30, "quality": "bonne", "sys_audio": True, "mic": False,
                     "clicks": True, "keys": False, "countdown": 3}},
}

logger = logging.getLogger("capturescreen")


def setup_logging() -> None:
    if logger.handlers:
        return
    try:
        h = logging.FileHandler(LOG_FILE, encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(h)
        logger.setLevel(logging.INFO)
    except Exception:
        pass


def load_cfg() -> dict:
    cfg = dict(DEFAULTS)
    try:
        with open(CFG_FILE, encoding="utf-8-sig") as f:
            d = json.load(f)
        if isinstance(d, dict):
            cfg.update(d)
    except Exception:
        pass
    if not cfg.get("out_dir"):
        cfg["out_dir"] = default_out_dir()
    return cfg


def save_cfg(cfg: dict) -> None:
    try:
        tmp = CFG_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=1)
        os.replace(tmp, CFG_FILE)
    except Exception:
        logger.exception("save_cfg")


# ------------------------------------------------------------------ ffmpeg (copie de la detection de l'Archiveur)
def _registry_path_entries():
    out = []
    if not IS_WIN:
        return out
    try:
        import winreg
        for hive, sub in ((winreg.HKEY_CURRENT_USER, r"Environment"),
                          (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment")):
            try:
                with winreg.OpenKey(hive, sub) as k:
                    v, _ = winreg.QueryValueEx(k, "Path")
                    out.extend(p for p in str(v).split(";") if p.strip())
            except OSError:
                pass
    except Exception:
        pass
    return out


_FF_CACHE = {}


def find_ffmpeg(name: str = "ffmpeg"):
    """Chemin absolu de ffmpeg.exe (ou ffprobe/ffplay), ou None. Memes emplacements que l'Archiveur."""
    if name in _FF_CACHE and os.path.isfile(_FF_CACHE[name]):
        return _FF_CACHE[name]
    exe = name + (".exe" if IS_WIN else "")
    which = shutil.which(name)
    if which:
        _FF_CACHE[name] = which
        return which
    cands = []
    for p in _registry_path_entries():
        e = os.path.expandvars(p.strip())
        cands += [os.path.join(e, exe), os.path.join(e, "bin", exe)]
    local = os.environ.get("LOCALAPPDATA", "")
    if local:
        cands.append(os.path.join(local, r"Microsoft\WinGet\Links", exe))
        pkg = os.path.join(local, r"Microsoft\WinGet\Packages")
        if os.path.isdir(pkg):
            cands += glob.glob(os.path.join(pkg, "Gyan.FFmpeg*", "**", "bin", exe), recursive=True)
        cands += [os.path.join(local, r"Archiveur\ffmpeg\bin", exe), os.path.join(local, r"Archiveur\ffmpeg", exe)]
    cands += [os.path.join(r"C:\ffmpeg\bin", exe), os.path.join(r"C:\ffmpeg", exe),
              os.path.expandvars(os.path.join(r"%ProgramFiles%\ffmpeg\bin", exe))]
    if local:  # ffmpeg installe automatiquement par l'Archiveur (zip gyan.dev)
        cands += glob.glob(os.path.join(local, "Archiveur", "ffmpeg", "**", exe), recursive=True)
    for c in cands:
        if c and os.path.isfile(c):
            _FF_CACHE[name] = c
            return c
    return None


def run_hidden(args, timeout=60, **kw):
    return subprocess.run(args, capture_output=True, timeout=timeout, creationflags=NOWIN, **kw)


_ENC = {}


def pick_encoder(ff: str, pref: str = "auto") -> str:
    """'h264_nvenc' si la carte NVIDIA l'accepte vraiment (test 0,2 s), sinon 'libx264'."""
    if pref == "x264":
        return "libx264"
    if "v" in _ENC:
        return _ENC["v"]
    enc = "libx264"
    try:
        r = run_hidden([ff, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=black:s=320x240:r=30",
                        "-t", "0.2", "-c:v", "h264_nvenc", "-f", "null", "-"], timeout=20)
        if r.returncode == 0:
            enc = "h264_nvenc"
    except Exception:
        pass
    _ENC["v"] = enc
    return enc


def video_codec_args(enc: str, quality: str, fps: int):
    _l, crf, cq = QUALITY.get(quality, QUALITY["bonne"])
    g = str(max(1, int(fps)))  # une image cle par seconde : coupe rapide (-c copy) precise a 1 s
    if enc == "h264_nvenc":
        return ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", str(cq), "-b:v", "0",
                "-g", g, "-pix_fmt", "yuv420p"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf), "-g", g, "-pix_fmt", "yuv420p"]


def human_size(n) -> str:
    n = float(n or 0)
    for u in ("o", "Ko", "Mo", "Go"):
        if n < 1024 or u == "Go":
            return (f"{n:.0f} {u}" if u == "o" else f"{n:.1f} {u}").replace(".", ",")
        n /= 1024
    return f"{n:.1f} Go"


def hms(sec) -> str:
    sec = max(0, int(sec or 0))
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
