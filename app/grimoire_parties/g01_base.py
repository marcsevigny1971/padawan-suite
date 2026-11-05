# -*- coding: utf-8 -*-
# Partie de grimoire1.py (découpage v1.2.2, comportement inchangé).
# Chargée par grimoire1.py dans un espace de noms commun : ne pas lancer seule.
from __future__ import annotations

from __future__ import annotations

import argparse
import base64
import ctypes
import datetime as dt
import glob
import hashlib
import html
import io
import json
import logging
import logging.handlers
import math
import mimetypes
import os
import queue
import random
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import unicodedata
import urllib.parse
import urllib.request
import uuid
import zipfile
from html.parser import HTMLParser
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

try:
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog
    from tkinter import font as tkfont
except ImportError:  # pragma: no cover
    tk = None  # type: ignore
    ttk = messagebox = filedialog = tkfont = None  # type: ignore

if sys.platform.startswith("win"):
    from ctypes import wintypes  # noqa: F401

APP_NAME = "Grimoire"
APP_TITLE = "Grimoire"            # titre de fenetre sans numero (FindWindow / instance unique)
APP_FILE_VER = 1
SCHEMA_VERSION = 1
SEED_VERSION = 1
IS_WIN = sys.platform.startswith("win")

BASE = os.path.dirname(os.path.abspath(__file__))
FTP_HOME = r"C:\web\FTP_HOME"


def _portable_data_dir(app: str, ftp_sub: str) -> str:
    """Dossier de donnees : variable GRIMOIRE_DATA / PADAWAN_DATA, sinon C:\\web\\FTP_HOME\\<ftp_sub> (PC de Marc),
    sinon %USERPROFILE%\\Documents\\Padawan\\<app> (autre PC)."""
    env = os.environ.get(app.upper() + "_DATA", "").strip()
    if env:
        return env
    root = os.environ.get("PADAWAN_DATA", "").strip()
    if root:
        return os.path.join(root, app)
    if os.path.isdir(FTP_HOME):
        return os.path.join(FTP_HOME, ftp_sub)
    return os.path.join(os.path.expanduser("~"), "Documents", "Padawan", app)


DEFAULT_DATA_DIR = _portable_data_dir("Grimoire", "GRIMOIRE")
SEED_DB = os.path.join(BASE, "grimoire_depart.db")   # base de depart (copiee si aucune grimoire.db)
PADAWAN_DIR_DEFAULT = r"C:\web\FTP_HOME\SECTION PYTHON\Projet Padawan"
_MUTEX_NAME = "Local\\Grimoire_SingleInstance"
CREATE_NO_WINDOW = 0x08000000
BACKUP_KEEP = 30
BACKUP_MIN_INTERVAL = 6 * 3600
INBOX_SUBJECT = "À classer"

logger = logging.getLogger("grimoire")


class Paths:
    """Emplacements des donnees (modifiables avec --data pour les tests)."""
    data = DEFAULT_DATA_DIR

    @classmethod
    def set(cls, d: str) -> None:
        cls.data = os.path.abspath(d)

    @classmethod
    def db(cls) -> str:
        return os.path.join(cls.data, "grimoire.db")

    @classmethod
    def media(cls) -> str:
        return os.path.join(cls.data, "medias")

    @classmethod
    def backups(cls) -> str:
        return os.path.join(cls.data, "_sauvegardes")

    @classmethod
    def inbox(cls) -> str:
        return os.path.join(cls.data, "_inbox")

    @classmethod
    def log(cls) -> str:
        return os.path.join(cls.data, "grimoire.log")

    @classmethod
    def exports(cls) -> str:
        return os.path.join(cls.data, "exports")

    @classmethod
    def abs(cls, rel: str) -> str:
        if not rel:
            return ""
        if os.path.isabs(rel):
            return rel
        return os.path.normpath(os.path.join(cls.data, rel))

    @classmethod
    def rel(cls, p: str) -> str:
        try:
            r = os.path.relpath(os.path.abspath(p), cls.data)
        except ValueError:
            return os.path.abspath(p)
        return r.replace("\\", "/") if not r.startswith("..") else os.path.abspath(p)


def setup_logging() -> None:
    if logger.handlers:
        return
    logger.setLevel(logging.INFO)
    try:
        os.makedirs(Paths.data, exist_ok=True)
        h = logging.handlers.RotatingFileHandler(Paths.log(), maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S"))
        logger.addHandler(h)
    except OSError:
        logger.addHandler(logging.NullHandler())


# ---------------------------------------------------------------- themes (famille Archiveur / Arsenal)
THEMES: Dict[str, Dict[str, str]] = {
    "norton": {
        "BG": "#0000AA", "PANEL": "#000088", "CARD": "#000066", "FG": "#55FFFF", "HI": "#FFFF55",
        "BTN": "#0000AA", "BTN_FG": "#FFFFFF", "ENTRY_BG": "#000055", "ENTRY_FG": "#FFFFFF",
        "SEL": "#AAAA00", "DIM": "#88AACC", "OK": "#55FF55", "ERR": "#FF5555", "TEXT": "#FFFFFF",
        "ON_HI": "#000000", "ON_SEL": "#000000", "LINE": "#3355AA", "IMG_BG": "#000033",
        "HI_ACT": "#FFFF88", "DISABLED": "#6677AA", "TIP_BG": "#FFFFCC", "TIP_FG": "#000000",
        "SASH": "#55FFFF", "WARN": "#FFAA33", "HOVER": "#0A0A99", "CARD_FAV": "#1A1A70",
        "LINK": "#7FD4FF", "REF": "#FF99FF", "MARK": "#806000", "CODE_BG": "#00003A", "QUOTE": "#AACCFF",
    },
    "sombre": {
        "BG": "#1E1E1E", "PANEL": "#252526", "CARD": "#2D2D30", "FG": "#D4D4D4", "HI": "#FFC83D",
        "BTN": "#3A3D41", "BTN_FG": "#FFFFFF", "ENTRY_BG": "#141414", "ENTRY_FG": "#F0F0F0",
        "SEL": "#C9A227", "DIM": "#8C8C8C", "OK": "#6CCB5F", "ERR": "#F1707B", "TEXT": "#F0F0F0",
        "ON_HI": "#000000", "ON_SEL": "#000000", "LINE": "#45454D", "IMG_BG": "#000000",
        "HI_ACT": "#FFD866", "DISABLED": "#6B6B6B", "TIP_BG": "#FFFFCC", "TIP_FG": "#000000",
        "SASH": "#5A5A5A", "WARN": "#FFAA33", "HOVER": "#38383C", "CARD_FAV": "#33302A",
        "LINK": "#4FC1FF", "REF": "#E59CFF", "MARK": "#6B5300", "CODE_BG": "#101010", "QUOTE": "#B0B8C8",
    },
    "clair": {
        "BG": "#F3F3F3", "PANEL": "#E4E7EB", "CARD": "#FFFFFF", "FG": "#1F3A5F", "HI": "#0B5CAD",
        "BTN": "#DADDE2", "BTN_FG": "#111111", "ENTRY_BG": "#FFFFFF", "ENTRY_FG": "#000000",
        "SEL": "#9CC3EE", "DIM": "#5F6B7A", "OK": "#1E7B34", "ERR": "#C62828", "TEXT": "#111111",
        "ON_HI": "#FFFFFF", "ON_SEL": "#000000", "LINE": "#B8C0CC", "IMG_BG": "#202428",
        "HI_ACT": "#3D8BDA", "DISABLED": "#A0A6AE", "TIP_BG": "#FFFFE0", "TIP_FG": "#000000",
        "SASH": "#9AA4B0", "WARN": "#B85C00", "HOVER": "#EEF3FA", "CARD_FAV": "#FFF8DC",
        "LINK": "#0645AD", "REF": "#8B1FA9", "MARK": "#FFF176", "CODE_BG": "#EEF0F3", "QUOTE": "#445566",
    },
}
THEME_LABELS = {"norton": "Norton (bleu, défaut)", "sombre": "Sombre", "clair": "Clair"}
C: Dict[str, str] = dict(THEMES["norton"])

FONT_SPECS: Dict[str, Tuple[str, int, str, str]] = {
    "GUI": ("Consolas", 11, "normal", "roman"),
    "GUIB": ("Consolas", 11, "bold", "roman"),
    "GSM": ("Consolas", 9, "normal", "roman"),
    "GSMB": ("Consolas", 9, "bold", "roman"),
    "GTitle": ("Consolas", 14, "bold", "roman"),
    "GBig": ("Consolas", 17, "bold", "roman"),
    "GHead": ("Consolas", 10, "bold", "roman"),
    "GMono": ("Consolas", 10, "normal", "roman"),
    "GCard": ("Consolas", 10, "bold", "roman"),
    "GCardD": ("Consolas", 9, "normal", "roman"),
    # editeur de notes
    "ENorm": ("Consolas", 11, "normal", "roman"),
    "EB": ("Consolas", 11, "bold", "roman"),
    "EI": ("Consolas", 11, "normal", "italic"),
    "EBI": ("Consolas", 11, "bold", "italic"),
    "EH1": ("Consolas", 18, "bold", "roman"),
    "EH2": ("Consolas", 15, "bold", "roman"),
    "EH3": ("Consolas", 13, "bold", "roman"),
    "ECode": ("Consolas", 10, "normal", "roman"),
    # mode lecture
    "RNorm": ("Georgia", 14, "normal", "roman"),
    "RB": ("Georgia", 14, "bold", "roman"),
    "RI": ("Georgia", 14, "normal", "italic"),
    "RBI": ("Georgia", 14, "bold", "italic"),
    "RH1": ("Georgia", 24, "bold", "roman"),
    "RH2": ("Georgia", 19, "bold", "roman"),
    "RH3": ("Georgia", 16, "bold", "roman"),
    "RCode": ("Consolas", 12, "normal", "roman"),
    "Emoji": ("Segoe UI Emoji", 18, "normal", "roman"),
    "EmojiBig": ("Segoe UI Emoji", 30, "normal", "roman"),
    "EmojiSM": ("Segoe UI Emoji", 12, "normal", "roman"),
}
FONT_DELTA_MIN, FONT_DELTA_MAX = -3, 8
_FONT_OBJS: Dict[str, Any] = {}


def init_fonts(root, delta: int = 0) -> None:
    delta = max(FONT_DELTA_MIN, min(FONT_DELTA_MAX, int(delta or 0)))
    try:
        fams = {f.lower() for f in tkfont.families(root)}
    except Exception:
        fams = set()
    for name, (fam, size, weight, slant) in FONT_SPECS.items():
        if fams and fam.lower() not in fams:
            fam = {"Consolas": "DejaVu Sans Mono", "Georgia": "DejaVu Serif",
                   "Segoe UI Emoji": "DejaVu Sans"}.get(fam, "DejaVu Sans")
        kw = dict(family=fam, size=max(6, size + delta), weight=weight, slant=slant)
        obj = _FONT_OBJS.get(name)
        if obj is not None:
            try:
                obj.configure(**kw)
                continue
            except Exception:
                pass
        try:
            obj = tkfont.Font(root=root, name=name, exists=False, **kw)
        except Exception:
            obj = tkfont.Font(root=root, name=name, exists=True)
            obj.configure(**kw)
        _FONT_OBJS[name] = obj


def fnt(name: str):
    return _FONT_OBJS.get(name) or name


# ---------------------------------------------------------------- utilitaires
def now_iso() -> str:
    return dt.datetime.now().replace(microsecond=0).isoformat(sep=" ")


def today() -> str:
    return dt.date.today().isoformat()


def norm(s: str) -> str:
    """Minuscules sans accents (comparaisons, recherche)."""
    s = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(ch for ch in s if not unicodedata.combining(ch)).lower().strip()


def safe_name(s: str, maxlen: int = 80) -> str:
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", str(s or "")).strip(" .")
    return (s or "sans_nom")[:maxlen]


def human_size(n: Any) -> str:
    try:
        n = float(n or 0)
    except (TypeError, ValueError):
        return ""
    for u in ("o", "Ko", "Mo", "Go"):
        if n < 1024 or u == "Go":
            return f"{n:.0f} {u}" if u == "o" else f"{n:.1f} {u}".replace(".", ",")
        n /= 1024
    return ""


def fmt_dur(sec: Any) -> str:
    try:
        s = int(float(sec or 0))
    except (TypeError, ValueError):
        return ""
    h, r = divmod(s, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
        "novembre", "décembre"]
MOIS_ABR = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]


def fmt_date(iso: str, with_time: bool = True) -> str:
    """2026-10-06 14:22:00 -> 6 oct. 2026 14:22 (aujourd'hui / hier en clair)."""
    if not iso:
        return ""
    try:
        d = dt.datetime.fromisoformat(iso[:19])
    except ValueError:
        return iso
    t = d.strftime("%H:%M") if with_time and len(iso) > 10 else ""
    dd = d.date()
    td = dt.date.today()
    if dd == td:
        day = "aujourd'hui"
    elif dd == td - dt.timedelta(days=1):
        day = "hier"
    else:
        day = f"{dd.day} {MOIS_ABR[dd.month - 1]} {dd.year}"
    return (day + " " + t).strip()


def month_label(iso: str) -> str:
    try:
        d = dt.date.fromisoformat(iso[:10])
        return f"{MOIS[d.month - 1].capitalize()} {d.year}"
    except ValueError:
        return "Sans date"


URL_RE = re.compile(r"""(?i)\b((?:https?://|www\.)[^\s<>"'«»\[\]{}]+[^\s<>"'«»\[\]{}.,;:!?)])""")
REF_RE = re.compile(r"\[\[([^\[\]\n]{1,120})\]\]")


def find_urls(text: str) -> List[str]:
    return [m.group(1) for m in URL_RE.finditer(text or "")]


def is_url(s: str) -> bool:
    s = (s or "").strip()
    return bool(re.match(r"(?i)^(https?://|www\.)\S+$", s)) and " " not in s


def fix_url(u: str) -> str:
    u = (u or "").strip()
    if u.lower().startswith("www."):
        u = "https://" + u
    return u


VIDEO_HOSTS = ("youtube.com", "youtu.be", "vimeo.com", "tiktok.com", "dailymotion.com", "rumble.com", "odysee.com",
               "twitch.tv", "bitchute.com", "x.com", "twitter.com", "facebook.com/watch", "fb.watch", "instagram.com/reel",
               "instagram.com/p/", "facebook.com/reel", "/videos/", "brighteon.com", "peertube")


def is_video_url(u: str) -> bool:
    lu = (u or "").lower()
    if re.search(r"\.(mp4|webm|mkv|mov|m4v)(\?|$)", lu):
        return True
    if ("x.com/" in lu or "twitter.com/" in lu) and "/status/" not in lu:
        return False
    return any(h in lu for h in VIDEO_HOSTS)


def youtube_id(u: str) -> str:
    m = re.search(r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|embed/|live/)|youtu\.be/)([\w-]{11})", u or "")
    return m.group(1) if m else ""


def domain_of(u: str) -> str:
    try:
        d = urllib.parse.urlparse(fix_url(u)).netloc.lower()
        return d[4:] if d.startswith("www.") else d
    except Exception:
        return ""


def open_path(p: str) -> bool:
    """Ouvre un fichier, dossier ou lien avec l'application par defaut."""
    if not p:
        return False
    try:
        if re.match(r"(?i)^(https?|mailto|file):", p):
            import webbrowser
            webbrowser.open(p)
            return True
        if IS_WIN:
            os.startfile(p)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", p])
        else:
            subprocess.Popen(["xdg-open", p], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception as ex:
        logger.warning("ouverture %s : %s", p, ex)
        return False


def open_url(u: str) -> None:
    u = fix_url(u)
    if not re.match(r"(?i)^[a-z][a-z0-9+.-]*:", u):
        u = "https://" + u
    open_path(u)


def reveal_in_explorer(p: str) -> None:
    if not p:
        return
    if IS_WIN and os.path.exists(p):
        try:
            subprocess.Popen(["explorer", "/select,", os.path.normpath(p)], creationflags=CREATE_NO_WINDOW)
            return
        except Exception:
            pass
    open_path(os.path.dirname(p) if os.path.isfile(p) else p)


def popen_hidden(args: List[str], **kw) -> subprocess.Popen:
    kw.setdefault("stdin", subprocess.DEVNULL)
    kw.setdefault("stdout", subprocess.DEVNULL)
    kw.setdefault("stderr", subprocess.DEVNULL)
    if IS_WIN:
        kw["creationflags"] = kw.get("creationflags", 0) | CREATE_NO_WINDOW
    return subprocess.Popen(args, **kw)


def run_hidden(args: List[str], timeout: float = 120, **kw) -> subprocess.CompletedProcess:
    kw.setdefault("stdin", subprocess.DEVNULL)
    kw.setdefault("stdout", subprocess.PIPE)
    kw.setdefault("stderr", subprocess.PIPE)
    if IS_WIN:
        kw["creationflags"] = kw.get("creationflags", 0) | CREATE_NO_WINDOW
    return subprocess.run(args, timeout=timeout, **kw)


def module_ok(name: str) -> bool:
    try:
        __import__(name)
        return True
    except Exception:
        return False


def find_pythonw() -> str:
    cands = [os.path.join(os.environ.get("LOCALAPPDATA", ""), "Python", "pythoncore-3.14-64", "pythonw.exe")]
    exe = sys.executable or ""
    if exe:
        d = os.path.dirname(exe)
        cands.insert(0, os.path.join(d, "pythonw.exe"))
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return shutil.which("pythonw") or exe or "pythonw"


def find_python() -> str:
    exe = sys.executable or ""
    if exe.lower().endswith("pythonw.exe"):
        c = exe[:-len("pythonw.exe")] + "python.exe"
        if os.path.isfile(c):
            return c
    return exe or shutil.which("python") or "python"


def padawan_dir() -> str:
    for d in (BASE, PADAWAN_DIR_DEFAULT):
        if os.path.isfile(os.path.join(d, "padawan39.py")) or os.path.isfile(os.path.join(d, "archiveur5.py")):
            return d
    return BASE


# ---------------------------------------------------------------- ffmpeg / ffplay (repris de l'Archiveur 5)
_FF_CACHE: Dict[str, Optional[str]] = {}


def _registry_path_entries() -> List[str]:
    entries: List[str] = []
    if not IS_WIN:
        return entries
    try:
        import winreg
        for hive, sub in ((winreg.HKEY_CURRENT_USER, r"Environment"),
                          (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment")):
            try:
                key = winreg.OpenKey(hive, sub, 0, winreg.KEY_READ)
                try:
                    val, _ = winreg.QueryValueEx(key, "Path")
                except FileNotFoundError:
                    val = ""
                winreg.CloseKey(key)
                if val:
                    entries.extend([p.strip() for p in str(val).split(";") if p.strip()])
            except OSError:
                pass
    except Exception:
        pass
    return entries


def find_ffmpeg() -> Optional[str]:
    if "ffmpeg" in _FF_CACHE:
        return _FF_CACHE["ffmpeg"]
    res = None
    w = shutil.which("ffmpeg")
    if w and os.path.isfile(w):
        res = os.path.abspath(w)
    else:
        cands = []
        for entry in _registry_path_entries():
            e = os.path.expandvars(entry)
            cands += [os.path.join(e, "ffmpeg.exe"), os.path.join(e, "bin", "ffmpeg.exe")]
        local = os.environ.get("LOCALAPPDATA", "")
        if local:
            cands.append(os.path.join(local, r"Microsoft\WinGet\Links\ffmpeg.exe"))
            cands += glob.glob(os.path.join(local, r"Microsoft\WinGet\Packages", "Gyan.FFmpeg*", "**", "bin", "ffmpeg.exe"),
                               recursive=True)
            cands += [os.path.join(local, r"Archiveur\ffmpeg\bin\ffmpeg.exe"), os.path.join(local, r"Archiveur\ffmpeg\ffmpeg.exe")]
        cands += [r"C:\ffmpeg\bin\ffmpeg.exe", os.path.expandvars(r"%ProgramFiles%\ffmpeg\bin\ffmpeg.exe")]
        for c in cands:
            if c and os.path.isfile(c):
                res = os.path.abspath(c)
                break
    _FF_CACHE["ffmpeg"] = res
    return res


def find_ff_tool(name: str) -> Optional[str]:
    if name in _FF_CACHE:
        return _FF_CACHE[name]
    res = None
    ff = find_ffmpeg()
    if ff:
        c = os.path.join(os.path.dirname(ff), name + (".exe" if IS_WIN else ""))
        if os.path.isfile(c):
            res = c
    if not res:
        w = shutil.which(name)
        res = os.path.abspath(w) if w else None
    _FF_CACHE[name] = res
    return res


def find_browser() -> Optional[str]:
    """Edge / Chrome (headless) pour la capture complete des pages web."""
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    pfx = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    la = os.environ.get("LOCALAPPDATA", "")
    cands = [os.path.join(pfx, "Microsoft", "Edge", "Application", "msedge.exe"),
             os.path.join(pf, "Microsoft", "Edge", "Application", "msedge.exe"),
             os.path.join(pf, "Google", "Chrome", "Application", "chrome.exe"),
             os.path.join(pfx, "Google", "Chrome", "Application", "chrome.exe"),
             os.path.join(la, "Google", "Chrome", "Application", "chrome.exe") if la else ""]
    for n in ("msedge", "google-chrome", "chromium", "chromium-browser", "chrome"):
        w = shutil.which(n)
        if w:
            cands.append(w)
    for c in cands:
        if c and os.path.isfile(c):
            return os.path.abspath(c)
    return None


def media_duration(path: str) -> float:
    try:
        import soundfile as sf  # type: ignore
        return float(sf.info(path).duration)
    except Exception:
        pass
    fp = find_ff_tool("ffprobe")
    if fp:
        try:
            r = run_hidden([fp, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", path], 20)
            return float(r.stdout.decode("utf-8", "ignore").strip() or 0)
        except Exception:
            pass
    return 0.0


# ---------------------------------------------------------------- types d'items
TYPES: Dict[str, Dict[str, str]] = {
    "note": {"label": "Note", "icon": "📝", "plural": "Notes"},
    "link": {"label": "Lien web", "icon": "🔗", "plural": "Liens"},
    "video": {"label": "Vidéo / embed", "icon": "🎬", "plural": "Vidéos"},
    "quote": {"label": "Citation", "icon": "❝", "plural": "Citations"},
    "page": {"label": "Page web capturée", "icon": "🌐", "plural": "Pages capturées"},
    "image": {"label": "Image", "icon": "🖼", "plural": "Images"},
    "document": {"label": "Document", "icon": "📄", "plural": "Documents"},
    "audio": {"label": "Son", "icon": "🔊", "plural": "Sons"},
    "voice": {"label": "Mémo vocal", "icon": "🎙", "plural": "Mémos vocaux"},
    "file": {"label": "Fichier", "icon": "📎", "plural": "Fichiers"},
}
TYPE_ORDER = ["note", "link", "video", "quote", "page", "image", "document", "audio", "voice", "file"]
IMG_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff", ".ico", ".jfif", ".heic", ".avif"}
DOC_EXT = {".pdf", ".doc", ".docx", ".odt", ".rtf", ".txt", ".md", ".csv", ".xls", ".xlsx", ".ods", ".ppt", ".pptx",
           ".odp", ".html", ".htm", ".epub", ".json", ".xml", ".log", ".ini", ".py", ".ino", ".js", ".php", ".css",
           ".bat", ".ps1", ".c", ".cpp", ".h", ".sql", ".yaml", ".yml"}
AUDIO_EXT = {".mp3", ".wav", ".flac", ".ogg", ".oga", ".opus", ".m4a", ".aac", ".wma", ".aiff", ".aif", ".amr", ".mid", ".midi"}
VIDEO_EXT = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v", ".wmv", ".mpg", ".mpeg", ".flv", ".3gp", ".ts"}
TEXT_EXT = {".txt", ".md", ".csv", ".json", ".xml", ".log", ".ini", ".py", ".ino", ".js", ".php", ".css", ".bat", ".ps1",
            ".c", ".cpp", ".h", ".sql", ".yaml", ".yml"}


def type_for_file(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in IMG_EXT:
        return "image"
    if ext in AUDIO_EXT:
        return "audio"
    if ext in VIDEO_EXT:
        return "video"
    if ext in DOC_EXT:
        return "document"
    return "file"


SUBJECT_COLORS = ["#FFFF55", "#55FFFF", "#55FF55", "#FF77FF", "#FFAA33", "#FF5555", "#7FB2FF", "#C0C0C0",
                  "#B388FF", "#FFD27F", "#66E0B0", "#FF9EB5", "#A8E05F", "#F5F5F5", "#40C4FF", "#E0A060"]

EMOJI_SETS = [
    ("Savoir", "📚📖📜📝📒📓📔📕📗📘📙🗂🗃🗄📁📂🧾📋📌📎🔖🏷"),
    ("Sciences", "🔬🔭🧪🧬⚗🧲💡⚡🔋🔌🌡🧮📐📏🛰📡⚛🧠"),
    ("Nature", "🌿🌱🌳🌲🍃🍀🌸🌻🌼🍄🌾🌍🌎🌏🏔🌊☀🌙⭐❄🔥💧🐝🦋🐦"),
    ("Santé", "❤🫀🩺💊🩹🌿🍵🧘🥗🍎🥕🧄🫚🍯💪😴"),
    ("Maison", "🏠🔨🛠🔧🪛🪚🧰🏕⛺🪵🧱🚿🔦🕯🧯🚜"),
    ("Cuisine", "🍲🥘🍞🥖🧀🥚🍳🥩🍗🍝🍜🥧🍰☕🍷🧂🫙"),
    ("Tech", "💻🖥⌨🖱🖨💾💿📱🤖🐍🌐🔗🪟🧑‍💻📶🔐"),
    ("Monde", "🌍🗺🧭🏛⚖🗳📰🗞🎖🏳🛡⚔🕊💰💵📈📉🏦"),
    ("Médias", "🎬🎞📺📻🎵🎶🎤🎙🎧📷📸🖼🎨▶🔊"),
    ("Idées", "💡🚀✨🌟⭐🎯🧩🔑🗝💎🏆🎁❓❗✅☑📅⏰"),
]


# ---------------------------------------------------------------- icone de l'application
def generate_app_icons(out_dir: str, force: bool = False) -> Tuple[str, str]:
    """grimoire1.ico / grimoire1.png / grimoire1_256.png : livre ancien jaune sur bleu Norton."""
    ico = os.path.join(out_dir, "grimoire1.ico")
    png = os.path.join(out_dir, "grimoire1.png")
    big = os.path.join(out_dir, "grimoire1_256.png")
    if not force and os.path.isfile(ico) and os.path.isfile(png) and os.path.isfile(big):
        return ico, png
    try:
        from PIL import Image, ImageDraw  # type: ignore
    except ImportError:
        return "", ""
    S = 256
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cyan, yellow, blue, dark = (85, 255, 255, 255), (255, 255, 85, 255), (0, 0, 170, 255), (0, 0, 70, 255)
    d.rounded_rectangle([6, 6, S - 7, S - 7], radius=44, fill=blue, outline=cyan, width=10)
    # tranche des pages (derriere la couverture)
    d.rounded_rectangle([62, 52, 206, 214], radius=10, fill=(235, 235, 210, 255), outline=dark, width=4)
    for yy in range(70, 206, 14):
        d.line([(196, yy), (204, yy)], fill=(160, 160, 140, 255), width=2)
    # couverture
    d.rounded_rectangle([46, 40, 192, 204], radius=12, fill=yellow, outline=dark, width=6)
    # dos
    d.rectangle([46, 40, 74, 204], fill=(220, 190, 40, 255))
    d.line([(74, 42), (74, 202)], fill=dark, width=5)
    for yy in (70, 172):
        d.line([(50, yy), (70, yy)], fill=dark, width=5)
    # cadre et embleme (etoile) de la couverture
    d.rounded_rectangle([90, 62, 176, 182], radius=8, outline=dark, width=4)
    cx, cy, r1, r2 = 133, 116, 30, 12
    import math
    pts = []
    for k in range(10):
        a = -math.pi / 2 + k * math.pi / 5
        r = r1 if k % 2 == 0 else r2
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    d.polygon(pts, fill=blue, outline=dark)
    d.rectangle([104, 156, 162, 162], fill=dark)
    # signet cyan
    d.polygon([(150, 196), (150, 236), (162, 224), (174, 236), (174, 196)], fill=cyan, outline=dark)
    # fermoir
    d.rounded_rectangle([180, 104, 204, 128], radius=5, fill=cyan, outline=dark, width=3)
    try:
        os.makedirs(out_dir, exist_ok=True)
        img.save(big)
        img.resize((64, 64), Image.Resampling.LANCZOS).save(png)
        img.save(ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    except OSError:
        return "", ""
    return ico, png


# ================================================================ texte riche : « runs »
# Une note = liste de segments [texte, [etiquettes]] ; etiquettes : b i u s h1 h2 h3 quote code mark a=<url>
RICH_TAGS = ("b", "i", "u", "s", "h1", "h2", "h3", "quote", "code", "mark")
LINE_TAGS = ("h1", "h2", "h3", "quote")


def runs_from_any(body: Any) -> List[List[Any]]:
    if not body:
        return []
    if isinstance(body, list):
        return body
    s = str(body)
    if s.startswith("{") and '"runs"' in s[:40]:
        try:
            d = json.loads(s)
            out = []
            for r in d.get("runs", []):
                if isinstance(r, list) and r and isinstance(r[0], str):
                    out.append([r[0], [t for t in (r[1] if len(r) > 1 else []) if isinstance(t, str)]])
            return out
        except (ValueError, AttributeError):
            pass
    return [[s, []]]


def runs_to_json(runs: List[List[Any]]) -> str:
    return json.dumps({"v": 1, "runs": runs}, ensure_ascii=False, separators=(",", ":"))


def runs_plain(runs: List[List[Any]]) -> str:
    return "".join(r[0] for r in runs)


def merge_runs(runs: List[List[Any]]) -> List[List[Any]]:
    out: List[List[Any]] = []
    for t, tags in runs:
        if not t:
            continue
        tags = sorted(set(tags))
        if out and out[-1][1] == tags:
            out[-1][0] += t
        else:
            out.append([t, tags])
    return out


def md_runs(text: str) -> List[List[Any]]:
    """Mini-markdown -> runs : # titres, - puces, > citation, [ ] cases, **gras**, *italique*, `code`, [lien](url)."""
    runs: List[List[Any]] = []
    lines = text.split("\n")
    for n, line in enumerate(lines):
        base: List[str] = []
        m = re.match(r"^(#{1,3}) (.*)$", line)
        if m:
            base = ["h%d" % len(m.group(1))]
            line = m.group(2)
        elif line.startswith("> "):
            base = ["quote"]
            line = line[2:]
        elif re.match(r"^\s*[-*] ", line):
            ind = len(line) - len(line.lstrip())
            line = " " * ind + "• " + line.lstrip()[2:]
        elif line.startswith("[ ] "):
            line = "☐ " + line[4:]
        elif line.startswith("[x] "):
            line = "☑ " + line[4:]
        pos = 0
        for mm in re.finditer(r"\[([^\[\]\n]+)\]\((https?://[^\s()]+(?:\([^\s()]*\)[^\s()]*)*)\)|\*\*(.+?)\*\*|\*(.+?)\*|`(.+?)`", line):
            if mm.start() > pos:
                runs.append([line[pos:mm.start()], list(base)])
            if mm.group(1) is not None:          # [texte](https://...) : lien cliquable
                inner = mm.group(1)
                extra = ["b"] if inner.startswith("**") and inner.endswith("**") and len(inner) > 4 else []
                runs.append([inner.strip("*") if extra else inner, base + extra + ["a=" + mm.group(2)]])
            elif mm.group(3) is not None:
                runs.append([mm.group(3), base + ["b"]])
            elif mm.group(4) is not None:
                runs.append([mm.group(4), base + ["i"]])
            else:
                runs.append([mm.group(5), base + ["code"]])
            pos = mm.end()
        if pos < len(line):
            runs.append([line[pos:], list(base)])
        if n < len(lines) - 1:
            runs.append(["\n", list(base)])
    return merge_runs(runs)


def _linkify_html(text: str) -> str:
    """Echappe le texte et rend cliquables les URL et les references [[...]]."""
    out = []
    pos = 0
    for m in URL_RE.finditer(text):
        out.append(html.escape(text[pos:m.start()]))
        u = m.group(1)
        out.append(f'<a href="{html.escape(fix_url(u), quote=True)}" target="_blank">{html.escape(u)}</a>')
        pos = m.end()
    out.append(html.escape(text[pos:]))
    s = "".join(out)
    return REF_RE.sub(lambda mm: f'<span class="ref">[[{mm.group(1)}]]</span>', s)


def runs_to_html(runs: List[List[Any]]) -> str:
    parts = []
    for text, tags in runs:
        h = _linkify_html(text).replace("\n", "<br>\n")
        href = next((t[2:] for t in tags if t.startswith("a=")), "")
        for t in ("code", "mark", "s", "u", "i", "b"):
            if t in tags:
                tag = {"b": "strong", "i": "em", "u": "u", "s": "s", "mark": "mark", "code": "code"}[t]
                h = f"<{tag}>{h}</{tag}>"
        if href:
            h = f'<a href="{html.escape(href, quote=True)}" target="_blank">{h}</a>'
        cls = [t for t in tags if t in LINE_TAGS]
        if cls:
            h = f'<span class="{" ".join(cls)}">{h}</span>'
        parts.append(h)
    return "".join(parts)


# ================================================================ base de donnees
SCHEMA = """
CREATE TABLE IF NOT EXISTS subjects(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  parent_id INTEGER,
  name TEXT NOT NULL,
  icon TEXT DEFAULT '📁',
  color TEXT DEFAULT '',
  pinned INTEGER DEFAULT 0,
  sort REAL DEFAULT 0,
  description TEXT DEFAULT '',
  expanded INTEGER DEFAULT 1,
  created TEXT, updated TEXT, deleted TEXT, del_batch TEXT
);
CREATE TABLE IF NOT EXISTS items(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  subject_id INTEGER NOT NULL,
  type TEXT NOT NULL,
  title TEXT DEFAULT '',
  body TEXT DEFAULT '',
  body_text TEXT DEFAULT '',
  url TEXT DEFAULT '',
  file TEXT DEFAULT '',
  thumb TEXT DEFAULT '',
  source TEXT DEFAULT '',
  author TEXT DEFAULT '',
  tags TEXT DEFAULT '',
  fav INTEGER DEFAULT 0,
  pinned INTEGER DEFAULT 0,
  event_date TEXT DEFAULT '',
  extracted TEXT DEFAULT '',
  meta TEXT DEFAULT '{}',
  sort REAL DEFAULT 0,
  created TEXT, updated TEXT, opened TEXT, deleted TEXT, del_batch TEXT
);
CREATE INDEX IF NOT EXISTS ix_items_subject ON items(subject_id);
CREATE INDEX IF NOT EXISTS ix_items_deleted ON items(deleted);
CREATE INDEX IF NOT EXISTS ix_subjects_parent ON subjects(parent_id);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
"""
FTS_SQL = ("CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(title, body, extracted, tags, source, url, "
           "tokenize=\"unicode61 remove_diacritics 2\", prefix='2 3')")
ITEM_FIELDS = ("subject_id", "type", "title", "body", "body_text", "url", "file", "thumb", "source", "author", "tags",
               "fav", "pinned", "event_date", "extracted", "meta", "sort", "created", "updated", "opened", "deleted",
               "del_batch")
FTS_FIELDS = {"title", "body", "body_text", "extracted", "tags", "source", "url", "author"}
SUBJECT_FIELDS = ("parent_id", "name", "icon", "color", "pinned", "sort", "description", "expanded", "created",
                  "updated", "deleted", "del_batch")


def norm_tags(s: Any) -> str:
    if isinstance(s, (list, tuple)):
        parts = list(s)
    else:
        parts = re.split(r"[,;#\n]+", str(s or ""))
    seen, out = set(), []
    for p in parts:
        p = re.sub(r"\s+", " ", str(p)).strip().lstrip("#").strip()
        if p and norm(p) not in seen:
            seen.add(norm(p))
            out.append(p)
    return ", ".join(out)


def split_subject_path(name: str) -> List[str]:
    """« Santé/Protocoles » ou « Santé › Protocoles » ; « Autonomie / Survie » (barre entouree d'espaces) reste un nom."""
    return [p.strip() for p in re.split(r"\s*(?:›|>|\\)\s*|(?<! )/(?! )", name or "") if p and p.strip()]


def tag_list(s: str) -> List[str]:
    return [t for t in (x.strip() for x in (s or "").split(",")) if t]
