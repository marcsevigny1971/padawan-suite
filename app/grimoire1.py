# -*- coding: utf-8 -*-
"""
Grimoire 1 - carnet de recherche par sujets (Projet Padawan).

Le « dump de tout » de Marc, classe par sujets et sous-sujets :
- notes en texte riche (gras, italique, titres, listes, cases a cocher, citations, liens cliquables,
  references [[...]] entre fiches), modeles de fiches (source, protocole, plante, recette...) ;
- liens web (titre, description et miniature recuperes), videos/embeds (YouTube, X, TikTok...),
  citations avec source, captures de pages web completes (HTML hors ligne + PDF + image) ;
- images (vignettes, visionneuse zoom, OCR Windows optionnel), documents (PDF, Word, texte... :
  texte extrait pour la recherche), sons (lecture ffplay cachee), memos vocaux enregistres dans
  l'application (transcription faster-whisper optionnelle), fichiers quelconques ;
- recherche plein texte instantanee (SQLite FTS5, sans accents) avec filtres et surlignage,
  vues liste / cartes / chronologie, mode lecture, favoris, epingles, etiquettes, corbeille,
  Ctrl+Z, glisser-deposer, Ctrl+V intelligent, export HTML autonome / ZIP, import de dossier,
  statistiques, sauvegardes automatiques, ligne de commande --ajouter / --importer-lot pour la famille Padawan.

Donnees : C:\\web\\FTP_HOME\\GRIMOIRE\\ (grimoire.db, medias\\<sujet>\\, _sauvegardes\\, _inbox\\,
grimoire.log) : tout est pris par backup.bat.
Tests : --smoke, --check, --shot fichier.png --geometry 1280x720 --shot-view main|cartes|chrono|recherche|...
"""
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


class Store:
    """Grimoire : SQLite (grimoire.db) + medias/<sujet_id>/ ; acces protege par un verrou (threads)."""

    def __init__(self, data_dir: Optional[str] = None):
        if data_dir:
            Paths.set(data_dir)
        self.lock = threading.RLock()
        self.conn: Optional[sqlite3.Connection] = None
        self.fts_ok = True
        self._subj_cache: Optional[Dict[int, Dict[str, Any]]] = None
        self.version = 0          # change a chaque modification (rafraichissement de l'interface)
        self.last_error = ""

    # ------------------------------------------------------------ ouverture
    def open(self) -> "Store":
        os.makedirs(Paths.data, exist_ok=True)
        os.makedirs(Paths.media(), exist_ok=True)
        if not os.path.exists(Paths.db()) and os.path.isfile(SEED_DB):
            try:   # premier lancement : base de depart (n'ecrase jamais une base existante)
                shutil.copyfile(SEED_DB, Paths.db())
                logger.info("base de départ copiée : %s", SEED_DB)
            except OSError as ex:
                logger.warning("base de départ non copiée : %s", ex)
        self.conn = sqlite3.connect(Paths.db(), check_same_thread=False, timeout=15)
        self.conn.row_factory = sqlite3.Row
        c = self.conn
        c.execute("PRAGMA foreign_keys=OFF")
        c.execute("PRAGMA synchronous=NORMAL")
        c.executescript(SCHEMA)
        c.executescript(GX_ARCHIVES_SQL)   # 1.5 : liens rendus permanents (ajout, rien n'est modifie)
        try:
            c.execute(FTS_SQL)
        except sqlite3.OperationalError as ex:
            self.fts_ok = False
            logger.warning("FTS5 indisponible : %s (recherche simple)", ex)
        v = c.execute("PRAGMA user_version").fetchone()[0]
        if v < SCHEMA_VERSION:
            c.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        c.commit()
        return self

    def close(self) -> None:
        with self.lock:
            if self.conn:
                try:
                    self.conn.commit()
                    self.conn.close()
                except Exception:
                    pass
                self.conn = None

    def _touch(self) -> None:
        self.version += 1
        self._subj_cache = None

    def q(self, sql: str, args: Iterable[Any] = ()) -> List[sqlite3.Row]:
        with self.lock:
            return self.conn.execute(sql, tuple(args)).fetchall()

    def x(self, sql: str, args: Iterable[Any] = (), commit: bool = True) -> sqlite3.Cursor:
        with self.lock:
            cur = self.conn.execute(sql, tuple(args))
            if commit:
                self.conn.commit()
            return cur

    # ------------------------------------------------------------ reglages
    def get(self, key: str, default: Any = None) -> Any:
        r = self.q("SELECT value FROM settings WHERE key=?", (key,))
        if not r:
            return default
        try:
            return json.loads(r[0]["value"])
        except (ValueError, TypeError):
            return default

    def set(self, key: str, value: Any) -> None:
        self.x("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (key, json.dumps(value, ensure_ascii=False)))

    # ------------------------------------------------------------ sujets
    def subjects(self) -> Dict[int, Dict[str, Any]]:
        with self.lock:
            if self._subj_cache is None:
                rows = self.q("SELECT * FROM subjects WHERE deleted IS NULL")
                self._subj_cache = {r["id"]: dict(r) for r in rows}
            return self._subj_cache

    def subject(self, sid: Any) -> Optional[Dict[str, Any]]:
        try:
            return self.subjects().get(int(sid))
        except (TypeError, ValueError):
            return None

    def children(self, sid: Optional[int]) -> List[Dict[str, Any]]:
        subs = [s for s in self.subjects().values() if (s["parent_id"] or None) == (sid or None)]
        return sorted(subs, key=lambda s: (-int(s["pinned"] or 0), float(s["sort"] or 0), norm(s["name"])))

    def descendants(self, sid: int) -> List[int]:
        out, stack = [], [sid]
        allsubs = list(self.subjects().values())
        while stack:
            cur = stack.pop()
            for s in allsubs:
                if s["parent_id"] == cur:
                    out.append(s["id"])
                    stack.append(s["id"])
        return out

    def subject_path(self, sid: Any, sep: str = " › ") -> str:
        names, seen = [], set()
        s = self.subject(sid)
        while s and s["id"] not in seen:
            seen.add(s["id"])
            names.append(s["name"])
            s = self.subject(s["parent_id"]) if s["parent_id"] else None
        return sep.join(reversed(names)) if names else "(sujet supprimé)"

    def subject_label(self, sid: Any) -> str:
        s = self.subject(sid)
        return f"{s['icon'] or '📁'} {self.subject_path(sid)}" if s else "(sujet supprimé)"

    def add_subject(self, name: str, parent_id: Optional[int] = None, icon: str = "📁", color: str = "",
                    description: str = "", pinned: bool = False) -> int:
        with self.lock:
            mx = self.q("SELECT COALESCE(MAX(sort),0) m FROM subjects WHERE COALESCE(parent_id,0)=?", (parent_id or 0,))[0]["m"]
            cur = self.x("INSERT INTO subjects(parent_id,name,icon,color,pinned,sort,description,created,updated) "
                         "VALUES(?,?,?,?,?,?,?,?,?)",
                         (parent_id or None, name.strip() or "Sans nom", icon or "📁", color, int(pinned), mx + 1,
                          description, now_iso(), now_iso()))
            self._touch()
            return int(cur.lastrowid)

    def update_subject(self, sid: int, **kw) -> None:
        kw = {k: v for k, v in kw.items() if k in SUBJECT_FIELDS}
        if not kw:
            return
        kw["updated"] = now_iso()
        cols = ", ".join(f"{k}=?" for k in kw)
        self.x(f"UPDATE subjects SET {cols} WHERE id=?", list(kw.values()) + [sid])
        self._touch()

    def find_subject(self, name: str) -> Optional[int]:
        """Par nom (sans accents) ou chemin « Santé/Protocoles » ou « Santé › Protocoles »."""
        name = (name or "").strip()
        if not name:
            return None
        exact = [s for s in self.subjects().values() if norm(s["name"]) == norm(name)]
        if exact:
            exact.sort(key=lambda s: (s["parent_id"] is not None, s["id"]))
            return exact[0]["id"]
        parts = split_subject_path(name)
        if len(parts) > 1:
            parent = None
            for p in parts:
                hit = next((s for s in self.children(parent) if norm(s["name"]) == norm(p)), None)
                if not hit:
                    return None
                parent = hit["id"]
            return parent
        hits = [s for s in self.subjects().values() if norm(s["name"]) == norm(name)]
        if hits:
            hits.sort(key=lambda s: (s["parent_id"] is not None, s["id"]))
            return hits[0]["id"]
        return None

    def ensure_subject(self, name: str, icon: str = "📁") -> int:
        sid = self.find_subject(name)
        if sid:
            return sid
        parts = split_subject_path(name) or ["Sans nom"]
        parent = None
        for p in parts:
            hit = next((s for s in self.children(parent) if norm(s["name"]) == norm(p)), None)
            parent = hit["id"] if hit else self.add_subject(p, parent, icon)
        return int(parent)

    def inbox_subject(self) -> int:
        return self.ensure_subject(INBOX_SUBJECT, "📥")

    def counts(self) -> Dict[int, int]:
        rows = self.q("SELECT subject_id, COUNT(*) n FROM items WHERE deleted IS NULL GROUP BY subject_id")
        return {r["subject_id"]: r["n"] for r in rows}

    def total_counts(self) -> Dict[int, int]:
        direct = self.counts()
        tot: Dict[int, int] = {}

        def walk(sid: int) -> int:
            if sid in tot:
                return tot[sid]
            n = direct.get(sid, 0) + sum(walk(c["id"]) for c in self.children(sid))
            tot[sid] = n
            return n
        for sid in self.subjects():
            walk(sid)
        return tot

    def move_subject(self, sid: int, new_parent: Optional[int]) -> bool:
        if new_parent == sid or (new_parent and new_parent in self.descendants(sid)):
            return False
        mx = self.q("SELECT COALESCE(MAX(sort),0) m FROM subjects WHERE COALESCE(parent_id,0)=?", (new_parent or 0,))[0]["m"]
        self.update_subject(sid, parent_id=new_parent or None, sort=mx + 1)
        return True

    def reorder_subject(self, sid: int, delta: int) -> None:
        s = self.subject(sid)
        if not s:
            return
        sib = self.children(s["parent_id"])
        ids = [x["id"] for x in sib]
        i = ids.index(sid)
        j = max(0, min(len(ids) - 1, i + delta))
        if i == j:
            return
        ids.insert(j, ids.pop(i))
        with self.lock:
            for k, x in enumerate(ids):
                self.conn.execute("UPDATE subjects SET sort=? WHERE id=?", (k + 1, x))
            self.conn.commit()
        self._touch()

    def place_subject_before(self, sid: int, target: int) -> None:
        t = self.subject(target)
        if not t or sid == target or target in self.descendants(sid):
            return
        sib = [x["id"] for x in self.children(t["parent_id"]) if x["id"] != sid]
        sib.insert(sib.index(target), sid)
        with self.lock:
            self.conn.execute("UPDATE subjects SET parent_id=? WHERE id=?", (t["parent_id"], sid))
            for k, x in enumerate(sib):
                self.conn.execute("UPDATE subjects SET sort=? WHERE id=?", (k + 1, x))
            self.conn.commit()
        self._touch()

    # ------------------------------------------------------------ items
    def item(self, iid: Any) -> Optional[Dict[str, Any]]:
        try:
            r = self.q("SELECT * FROM items WHERE id=?", (int(iid),))
        except (TypeError, ValueError):
            return None
        return dict(r[0]) if r else None

    def _index(self, iid: int, d: Optional[Dict[str, Any]] = None) -> None:
        if not self.fts_ok:
            return
        d = d or self.item(iid)
        with self.lock:
            self.conn.execute("DELETE FROM fts WHERE rowid=?", (iid,))
            if d and not d.get("deleted"):
                meta = {}
                try:
                    meta = json.loads(d.get("meta") or "{}")
                except ValueError:
                    pass
                extra = " ".join(str(meta.get(k, "")) for k in ("description", "site", "filename"))
                self.conn.execute("INSERT INTO fts(rowid,title,body,extracted,tags,source,url) VALUES(?,?,?,?,?,?,?)",
                                  (iid, d.get("title") or "", d.get("body_text") or "",
                                   (d.get("extracted") or "") + " " + extra, d.get("tags") or "",
                                   ((d.get("source") or "") + " " + (d.get("author") or "")).strip(), d.get("url") or ""))

    def add_item(self, subject_id: int, type_: str, **kw) -> int:
        d = {k: v for k, v in kw.items() if k in ITEM_FIELDS}
        d["subject_id"] = subject_id
        d["type"] = type_ if type_ in TYPES else "file"
        d.setdefault("created", now_iso())
        d.setdefault("updated", d["created"])
        if "tags" in d:
            d["tags"] = norm_tags(d["tags"])
        if "body" in d and "body_text" not in d:
            d["body_text"] = runs_plain(runs_from_any(d["body"]))
        if isinstance(d.get("meta"), dict):
            d["meta"] = json.dumps(d["meta"], ensure_ascii=False)
        with self.lock:
            if "sort" not in d:
                d["sort"] = self.q("SELECT COALESCE(MAX(sort),0) m FROM items WHERE subject_id=?", (subject_id,))[0]["m"] + 1
            cols = ", ".join(d.keys())
            cur = self.conn.execute(f"INSERT INTO items({cols}) VALUES({', '.join('?' * len(d))})", list(d.values()))
            iid = int(cur.lastrowid)
            self._index(iid)
            self.conn.commit()
        self._touch()
        return iid

    def update_item(self, iid: int, touch: bool = True, **kw) -> None:
        kw = {k: v for k, v in kw.items() if k in ITEM_FIELDS}
        if not kw:
            return
        if "tags" in kw:
            kw["tags"] = norm_tags(kw["tags"])
        if "body" in kw and "body_text" not in kw:
            kw["body_text"] = runs_plain(runs_from_any(kw["body"]))
        if isinstance(kw.get("meta"), dict):
            kw["meta"] = json.dumps(kw["meta"], ensure_ascii=False)
        if touch:
            kw.setdefault("updated", now_iso())
        cols = ", ".join(f"{k}=?" for k in kw)
        with self.lock:
            self.conn.execute(f"UPDATE items SET {cols} WHERE id=?", list(kw.values()) + [iid])
            if FTS_FIELDS & set(kw) or "deleted" in kw:
                self._index(iid)
            self.conn.commit()
        self._touch()

    def meta(self, it: Dict[str, Any]) -> Dict[str, Any]:
        try:
            m = json.loads(it.get("meta") or "{}")
            return m if isinstance(m, dict) else {}
        except ValueError:
            return {}

    def set_meta(self, iid: int, **kw) -> None:
        it = self.item(iid)
        if not it:
            return
        m = self.meta(it)
        m.update(kw)
        self.update_item(iid, touch=False, meta=m)

    def items_in(self, sids: List[int], deleted: bool = False) -> List[Dict[str, Any]]:
        if not sids:
            return []
        marks = ",".join("?" * len(sids))
        cond = "deleted IS NOT NULL" if deleted else "deleted IS NULL"
        return [dict(r) for r in self.q(f"SELECT * FROM items WHERE subject_id IN ({marks}) AND {cond}", sids)]

    def items_where(self, where: str, args: Iterable[Any] = (), limit: int = 5000, order: str = "") -> List[Dict[str, Any]]:
        parts = re.split(r"\s+ORDER\s+BY\s+", where, maxsplit=1, flags=re.I)
        where = parts[0]
        order = order or (parts[1] if len(parts) > 1 else "")
        sql = f"SELECT * FROM items WHERE deleted IS NULL AND ({where})" + (f" ORDER BY {order}" if order else "")
        return [dict(r) for r in self.q(sql + f" LIMIT {int(limit)}", args)]

    def all_tags(self) -> List[Tuple[str, int]]:
        cnt: Dict[str, Tuple[str, int]] = {}
        for r in self.q("SELECT tags FROM items WHERE deleted IS NULL AND tags<>''"):
            for t in tag_list(r["tags"]):
                k = norm(t)
                cnt[k] = (cnt.get(k, (t, 0))[0], cnt.get(k, (t, 0))[1] + 1)
        return sorted(cnt.values(), key=lambda x: (-x[1], norm(x[0])))

    # ------------------------------------------------------------ corbeille
    def trash_items(self, ids: List[int], batch: Optional[str] = None) -> str:
        batch = batch or uuid.uuid4().hex[:10]
        ts = now_iso()
        with self.lock:
            for i in ids:
                self.conn.execute("UPDATE items SET deleted=?, del_batch=? WHERE id=? AND deleted IS NULL", (ts, batch, i))
                if self.fts_ok:
                    self.conn.execute("DELETE FROM fts WHERE rowid=?", (i,))
            self.conn.commit()
        self._touch()
        return batch

    def trash_subject(self, sid: int) -> str:
        batch = uuid.uuid4().hex[:10]
        ts = now_iso()
        allids = [sid] + self.descendants(sid)
        with self.lock:
            for s in allids:
                self.conn.execute("UPDATE subjects SET deleted=?, del_batch=? WHERE id=?", (ts, batch, s))
                for r in self.conn.execute("SELECT id FROM items WHERE subject_id=? AND deleted IS NULL", (s,)).fetchall():
                    self.conn.execute("UPDATE items SET deleted=?, del_batch=? WHERE id=?", (ts, batch, r["id"]))
                    if self.fts_ok:
                        self.conn.execute("DELETE FROM fts WHERE rowid=?", (r["id"],))
            self.conn.commit()
        self._touch()
        return batch

    def restore_batch(self, batch: str) -> int:
        with self.lock:
            n = self.conn.execute("UPDATE subjects SET deleted=NULL, del_batch=NULL WHERE del_batch=?", (batch,)).rowcount
            ids = [r["id"] for r in self.conn.execute("SELECT id FROM items WHERE del_batch=?", (batch,)).fetchall()]
            self.conn.execute("UPDATE items SET deleted=NULL, del_batch=NULL WHERE del_batch=?", (batch,))
            self.conn.commit()
            self._subj_cache = None
            subs = self.subjects()
            for i in ids:
                it = self.item(i)
                if it and it["subject_id"] not in subs:   # sujet parti : l'item revient dans « À classer »
                    self.conn.execute("UPDATE items SET subject_id=? WHERE id=?", (self.inbox_subject(), i))
                self._index(i)
            # sujet restaure dont le parent est encore a la corbeille : il revient a la racine
            for s in self.q("SELECT id,parent_id FROM subjects WHERE deleted IS NULL AND parent_id IS NOT NULL"):
                if s["parent_id"] not in self.subjects() and not self.q(
                        "SELECT 1 FROM subjects WHERE id=? AND deleted IS NULL", (s["parent_id"],)):
                    self.conn.execute("UPDATE subjects SET parent_id=NULL WHERE id=?", (s["id"],))
            self.conn.commit()
        self._touch()
        return n + len(ids)

    def restore_items(self, ids: List[int]) -> int:
        subs = self.subjects()
        n = 0
        for i in ids:
            it = self.item(i)
            if not it:
                continue
            sid = it["subject_id"] if it["subject_id"] in subs else self.inbox_subject()
            self.x("UPDATE items SET deleted=NULL, del_batch=NULL, subject_id=? WHERE id=?", (sid, i))
            with self.lock:
                self._index(i)
                self.conn.commit()
            n += 1
        self._touch()
        return n

    def trash_list(self) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        subs = [dict(r) for r in self.q("SELECT * FROM subjects WHERE deleted IS NOT NULL ORDER BY deleted DESC")]
        its = [dict(r) for r in self.q("SELECT * FROM items WHERE deleted IS NOT NULL ORDER BY deleted DESC")]
        return subs, its

    def purge_items(self, ids: List[int]) -> int:
        n = 0
        for i in ids:
            it = self.item(i)
            if not it:
                continue
            for rel in (it.get("file"), it.get("thumb")) + tuple(self.meta(it).get("extra_files", [])):
                p = Paths.abs(rel) if rel else ""
                if p and os.path.isfile(p) and os.path.abspath(p).startswith(os.path.abspath(Paths.media())):
                    if not self.q("SELECT 1 FROM items WHERE id<>? AND (file=? OR thumb=?)", (i, rel, rel)):
                        try:
                            os.remove(p)
                        except OSError:
                            pass
            self.x("DELETE FROM items WHERE id=?", (i,), commit=False)
            if self.fts_ok:
                self.x("DELETE FROM fts WHERE rowid=?", (i,), commit=False)
            n += 1
        with self.lock:
            self.conn.commit()
        self._touch()
        return n

    def empty_trash(self, batch: Optional[str] = None) -> int:
        cond, args = ("del_batch=?", (batch,)) if batch else ("deleted IS NOT NULL", ())
        ids = [r["id"] for r in self.q(f"SELECT id FROM items WHERE {cond}", args)]
        n = self.purge_items(ids)
        self.x(f"DELETE FROM subjects WHERE {cond}", args)
        self._touch()
        return n

    # ------------------------------------------------------------ fichiers
    def subject_media_dir(self, sid: int) -> str:
        d = os.path.join(Paths.media(), str(sid))
        os.makedirs(d, exist_ok=True)
        return d

    def unique_path(self, folder: str, name: str) -> str:
        return unique_path(folder, name)

    def import_file(self, src: str, sid: int, move: bool = False) -> str:
        dst = self.unique_path(self.subject_media_dir(sid), os.path.basename(src))
        if move:
            shutil.move(src, dst)
        else:
            shutil.copy2(src, dst)
        return Paths.rel(dst)

    def relocate_files(self, it: Dict[str, Any], new_sid: int) -> Dict[str, Any]:
        """Deplace les fichiers d'un item dans medias/<nouveau sujet>/ (retourne les champs a mettre a jour)."""
        upd: Dict[str, Any] = {}
        media_root = os.path.abspath(Paths.media())
        for key in ("file", "thumb"):
            rel = it.get(key) or ""
            p = Paths.abs(rel)
            if not rel or not os.path.isfile(p) or not os.path.abspath(p).startswith(media_root):
                continue
            if self.q("SELECT 1 FROM items WHERE id<>? AND (file=? OR thumb=?)", (it["id"], rel, rel)):
                continue
            sub = "_vignettes" if key == "thumb" else ""
            dest_dir = os.path.join(self.subject_media_dir(new_sid), sub) if sub else self.subject_media_dir(new_sid)
            os.makedirs(dest_dir, exist_ok=True)
            try:
                dst = self.unique_path(dest_dir, os.path.basename(p))
                shutil.move(p, dst)
                upd[key] = Paths.rel(dst)
            except OSError as ex:
                logger.warning("déplacement fichier %s : %s", p, ex)
        m = self.meta(it)
        if m.get("extra_files"):
            new_extra = []
            for rel in m["extra_files"]:
                p = Paths.abs(rel)
                if os.path.isfile(p) and os.path.abspath(p).startswith(media_root):
                    try:
                        dst = self.unique_path(self.subject_media_dir(new_sid), os.path.basename(p))
                        shutil.move(p, dst)
                        rel = Paths.rel(dst)
                    except OSError:
                        pass
                new_extra.append(rel)
            m["extra_files"] = new_extra
            upd["meta"] = m
        return upd

    def move_items(self, ids: List[int], sid: int) -> List[Tuple[int, int]]:
        old = []
        for i in ids:
            it = self.item(i)
            if not it or it["subject_id"] == sid:
                continue
            old.append((i, it["subject_id"]))
            upd = self.relocate_files(it, sid)
            mx = self.q("SELECT COALESCE(MAX(sort),0) m FROM items WHERE subject_id=?", (sid,))[0]["m"]
            self.update_item(i, touch=False, subject_id=sid, sort=mx + 1, **upd)
        return old

    def copy_items(self, ids: List[int], sid: int) -> List[int]:
        new = []
        for i in ids:
            it = self.item(i)
            if not it:
                continue
            d = {k: it[k] for k in ITEM_FIELDS if k in it and k not in ("subject_id", "type", "deleted", "del_batch", "sort")}
            for key in ("file", "thumb"):
                p = Paths.abs(it.get(key) or "")
                if p and os.path.isfile(p):
                    try:
                        dest_dir = self.subject_media_dir(sid)
                        if key == "thumb":
                            dest_dir = os.path.join(dest_dir, "_vignettes")
                            os.makedirs(dest_dir, exist_ok=True)
                        dst = self.unique_path(dest_dir, os.path.basename(p))
                        shutil.copy2(p, dst)
                        d[key] = Paths.rel(dst)
                    except OSError:
                        pass
            d["created"] = now_iso()
            d["updated"] = d["created"]
            new.append(self.add_item(sid, it["type"], **d))
        return new

    def merge_subjects(self, src: int, dst: int) -> Dict[str, Any]:
        """Fusionne src dans dst : items et sous-sujets passent dans dst, puis src va a la corbeille."""
        moved = self.move_items([r["id"] for r in self.items_in([src])], dst)
        kids = [c["id"] for c in self.children(src)]
        for k in kids:
            self.update_subject(k, parent_id=dst)
        batch = self.trash_subject(src)
        return {"moved": moved, "kids": kids, "batch": batch, "src": src}

    # ------------------------------------------------------------ recherche
    @staticmethod
    def fts_query(text: str) -> str:
        toks = re.findall(r"[\w'-]+", text, re.UNICODE)
        parts = []
        for t in toks:
            t = t.replace('"', "").strip("'-")
            if not t:
                continue
            parts.append(f'"{t}"*' if len(t) >= 2 else f'"{t}"')
        return " AND ".join(parts)

    def search(self, text: str, types: Optional[List[str]] = None, sids: Optional[List[int]] = None,
               tag: str = "", since: str = "", fav_only: bool = False, limit: int = 400) -> List[Dict[str, Any]]:
        text = (text or "").strip()
        conds, args = ["i.deleted IS NULL"], []
        if types:
            conds.append(f"i.type IN ({','.join('?' * len(types))})")
            args += types
        if sids:
            conds.append(f"i.subject_id IN ({','.join('?' * len(sids))})")
            args += sids
        if since:
            conds.append("COALESCE(NULLIF(i.event_date,''), i.created) >= ?")
            args.append(since)
        if fav_only:
            conds.append("i.fav=1")
        res: List[Dict[str, Any]] = []
        fq = self.fts_query(text) if text else ""
        if fq and self.fts_ok:
            try:
                sql = ("SELECT i.*, snippet(fts, 1, char(1), char(2), '…', 18) AS s_body, "
                       "snippet(fts, 2, char(1), char(2), '…', 18) AS s_ext, bm25(fts, 8.0, 2.0, 1.0, 4.0, 2.0, 1.0) AS rk "
                       "FROM fts JOIN items i ON i.id = fts.rowid WHERE fts MATCH ? AND " + " AND ".join(conds) +
                       f" ORDER BY i.pinned DESC, rk LIMIT {int(limit)}")
                res = [dict(r) for r in self.q(sql, [fq] + args)]
                for r in res:
                    sb, se = r.pop("s_body", "") or "", r.pop("s_ext", "") or ""
                    r["snip"] = sb if "\x01" in sb else (se if "\x01" in se else "")
            except sqlite3.OperationalError as ex:
                logger.info("recherche FTS : %s (repli LIKE)", ex)
                res = []
                fq = ""
        if text and (not self.fts_ok or not fq):
            like = f"%{text}%"
            sql = ("SELECT i.*, '' AS snip FROM items i WHERE (i.title LIKE ? OR i.body_text LIKE ? OR i.extracted LIKE ? "
                   "OR i.tags LIKE ? OR i.url LIKE ? OR i.source LIKE ?) AND " + " AND ".join(conds) +
                   f" ORDER BY i.updated DESC LIMIT {int(limit)}")
            res = [dict(r) for r in self.q(sql, [like] * 6 + args)]
        elif not text:
            sql = ("SELECT i.*, '' AS snip FROM items i WHERE " + " AND ".join(conds) +
                   f" ORDER BY COALESCE(NULLIF(i.event_date,''), i.created) DESC LIMIT {int(limit)}")
            res = [dict(r) for r in self.q(sql, args)]
        if tag:
            res = [r for r in res if norm(tag) in [norm(t) for t in tag_list(r.get("tags") or "")]]
        # les noms de sujets comptent aussi : « recettes » trouve les items du sujet Recettes
        if text and not tag:
            hit_sids = [s["id"] for s in self.subjects().values() if all(norm(t) in norm(s["name"]) for t in text.split())]
            if hit_sids:
                have = {r["id"] for r in res}
                extra = [r for r in self.items_in(hit_sids) if r["id"] not in have]
                extra = [r for r in extra if (not types or r["type"] in types) and (not sids or r["subject_id"] in sids)
                         and (not fav_only or r["fav"])]
                for r in extra[:200]:
                    r["snip"] = ""
                res += extra
        return res

    def find_by_title(self, title: str) -> Optional[Dict[str, Any]]:
        t = norm(title)
        for r in self.q("SELECT * FROM items WHERE deleted IS NULL AND title<>'' ORDER BY updated DESC"):
            if norm(r["title"]) == t:
                return dict(r)
        return None

    def backlinks(self, it: Dict[str, Any]) -> List[Dict[str, Any]]:
        title = (it.get("title") or "").strip()
        if not title:
            return []
        out = []
        cand = self.items_where("body_text LIKE ?", (f"%[[%",))
        for r in cand:
            if r["id"] == it["id"]:
                continue
            for m in REF_RE.finditer(r.get("body_text") or ""):
                if norm(m.group(1)) == norm(title):
                    out.append(r)
                    break
        return out

    def rebuild_fts(self) -> int:
        if not self.fts_ok:
            return 0
        with self.lock:
            self.conn.execute("DELETE FROM fts")
            ids = [r["id"] for r in self.conn.execute("SELECT id FROM items WHERE deleted IS NULL").fetchall()]
            for i in ids:
                self._index(i)
            self.conn.commit()
        return len(ids)

    # ------------------------------------------------------------ sauvegardes
    def backup(self, force: bool = False, tag: str = "") -> Optional[str]:
        os.makedirs(Paths.backups(), exist_ok=True)
        last = float(self.get("last_backup_ts", 0) or 0)
        if not force and time.time() - last < BACKUP_MIN_INTERVAL:
            return None
        if not os.path.isfile(Paths.db()):
            return None
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        dst = os.path.join(Paths.backups(), f"grimoire_{stamp}{('_' + tag) if tag else ''}.db")
        try:
            with self.lock:
                self.conn.commit()
                b = sqlite3.connect(dst)
                self.conn.backup(b)
                b.close()
            self.set("last_backup_ts", time.time())
            files = sorted(glob.glob(os.path.join(Paths.backups(), "grimoire_*.db")))
            for old in files[:-BACKUP_KEEP]:
                try:
                    os.remove(old)
                except OSError:
                    pass
            logger.info("sauvegarde %s", dst)
            return dst
        except Exception as ex:
            logger.error("sauvegarde : %s", ex)
            self.last_error = str(ex)
            return None

    def integrity(self) -> str:
        try:
            return str(self.q("PRAGMA integrity_check")[0][0])
        except Exception as ex:
            return str(ex)

    def stats(self) -> Dict[str, Any]:
        st: Dict[str, Any] = {}
        st["subjects"] = len(self.subjects())
        st["items"] = self.q("SELECT COUNT(*) n FROM items WHERE deleted IS NULL")[0]["n"]
        st["trash"] = self.q("SELECT COUNT(*) n FROM items WHERE deleted IS NOT NULL")[0]["n"]
        st["by_type"] = {r["type"]: r["n"] for r in self.q("SELECT type, COUNT(*) n FROM items WHERE deleted IS NULL GROUP BY type")}
        st["favs"] = self.q("SELECT COUNT(*) n FROM items WHERE deleted IS NULL AND fav=1")[0]["n"]
        st["pinned"] = self.q("SELECT COUNT(*) n FROM items WHERE deleted IS NULL AND pinned=1")[0]["n"]
        st["months"] = [(r["m"], r["n"]) for r in self.q(
            "SELECT substr(created,1,7) m, COUNT(*) n FROM items WHERE deleted IS NULL GROUP BY m ORDER BY m DESC LIMIT 12")]
        st["words"] = sum(len((r["body_text"] or "").split()) for r in self.q("SELECT body_text FROM items WHERE deleted IS NULL"))
        size = 0
        nfiles = 0
        for root, _d, files in os.walk(Paths.media()):
            for f in files:
                try:
                    size += os.path.getsize(os.path.join(root, f))
                    nfiles += 1
                except OSError:
                    pass
        st["media_size"], st["media_files"] = size, nfiles
        try:
            st["db_size"] = os.path.getsize(Paths.db())
        except OSError:
            st["db_size"] = 0
        st["tags"] = self.all_tags()[:20]
        tot = self.total_counts()
        st["top_subjects"] = sorted(((self.subject_label(k), v) for k, v in tot.items() if v), key=lambda x: -x[1])[:10]
        st["backups"] = len(glob.glob(os.path.join(Paths.backups(), "grimoire_*.db")))
        lb = float(self.get("last_backup_ts", 0) or 0)
        st["last_backup"] = dt.datetime.fromtimestamp(lb).strftime("%Y-%m-%d %H:%M") if lb else "jamais"
        return st


def unique_path(folder: str, name: str) -> str:
    base, ext = os.path.splitext(safe_name(name, 120))
    p = os.path.join(folder, base + ext)
    n = 2
    while os.path.exists(p):
        p = os.path.join(folder, f"{base}_{n}{ext}")
        n += 1
    return p


# ================================================================ web : titre, description, miniature
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/128.0 Safari/537.36 Edg/128.0")


def http_get(url: str, timeout: float = 12, maxbytes: int = 4_000_000) -> Tuple[bytes, str, str]:
    url = fix_url(url)
    hdr = {"User-Agent": UA, "Accept-Language": "fr-CA,fr;q=0.9,en;q=0.7",
           "Accept": "text/html,application/xhtml+xml,application/json,image/*;q=0.9,*/*;q=0.8"}
    try:
        import requests  # type: ignore
        r = requests.get(url, headers=hdr, timeout=timeout, stream=True, allow_redirects=True)
        chunks, n = [], 0
        for ch in r.iter_content(65536):
            chunks.append(ch)
            n += len(ch)
            if n >= maxbytes:
                break
        r.close()
        if r.status_code >= 400:
            raise IOError(f"HTTP {r.status_code}")
        return b"".join(chunks), r.url, r.headers.get("Content-Type", "")
    except ImportError:
        req = urllib.request.Request(url, headers=hdr)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read(maxbytes), resp.geturl(), resp.headers.get("Content-Type", "")


def decode_html(b: bytes, ctype: str = "") -> str:
    enc = ""
    m = re.search(r"charset=([\w-]+)", ctype or "", re.I)
    if m:
        enc = m.group(1)
    else:
        m = re.search(rb"<meta[^>]+charset=[\"']?([\w-]+)", b[:4000], re.I)
        if m:
            enc = m.group(1).decode("ascii", "ignore")
    for e in (enc, "utf-8", "cp1252", "latin-1"):
        if not e:
            continue
        try:
            return b.decode(e)
        except (LookupError, UnicodeDecodeError):
            continue
    return b.decode("utf-8", "replace")


class _MetaParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta: Dict[str, str] = {}
        self.title = ""
        self._in_title = False
        self.icon = ""

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            k = (a.get("property") or a.get("name") or a.get("itemprop") or "").lower()
            if k and a.get("content") and k not in self.meta:
                self.meta[k] = a["content"].strip()
        elif tag == "link" and "icon" in a.get("rel", "").lower() and not self.icon:
            self.icon = a.get("href", "")
        elif tag == "link" and a.get("rel", "").lower() == "canonical":
            self.meta.setdefault("canonical", a.get("href", ""))

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title and len(self.title) < 400:
            self.title += data


def _json_get(url: str, timeout: float = 10) -> Dict[str, Any]:
    b, _u, _c = http_get(url, timeout)
    return json.loads(b.decode("utf-8", "replace"))


def fetch_link_info(url: str) -> Dict[str, str]:
    """Titre, description, image, site, auteur, date de publication d'un lien (meilleur effort)."""
    url = fix_url(url)
    info: Dict[str, str] = {"title": "", "description": "", "image": "", "site": domain_of(url), "author": "",
                            "published": "", "html_text": ""}
    lu = url.lower()
    try:
        yid = youtube_id(url)
        if yid:
            try:
                j = _json_get("https://www.youtube.com/oembed?format=json&url=" + urllib.parse.quote(url, safe=""))
                info.update(title=j.get("title", ""), author=j.get("author_name", ""), site="YouTube")
            except Exception:
                pass
            info["image"] = f"https://i.ytimg.com/vi/{yid}/hqdefault.jpg"
        m = re.search(r"(?:x|twitter)\.com/([^/]+)/status/(\d+)", lu)
        if m:
            try:
                j = _json_get(f"https://api.fxtwitter.com/{m.group(1)}/status/{m.group(2)}")
                t = j.get("tweet") or {}
                au = t.get("author") or {}
                info.update(title=f"{au.get('name', '')} (@{au.get('screen_name', '')}) sur X", site="X",
                            description=t.get("text", ""), author=au.get("name", ""),
                            published=str(t.get("created_at", ""))[:40])
                media = (t.get("media") or {})
                pics = media.get("photos") or []
                vids = media.get("videos") or []
                if vids:
                    info["image"] = vids[0].get("thumbnail_url", "")
                elif pics:
                    info["image"] = pics[0].get("url", "")
            except Exception:
                try:
                    j = _json_get("https://publish.twitter.com/oembed?omit_script=1&url=" + urllib.parse.quote(url, safe=""))
                    txt = re.sub(r"<[^>]+>", " ", j.get("html", ""))
                    info.update(title=f"{j.get('author_name', '')} sur X", author=j.get("author_name", ""), site="X",
                                description=html.unescape(re.sub(r"\s+", " ", txt)).strip())
                except Exception:
                    pass
        for host, api in (("tiktok.com", "https://www.tiktok.com/oembed?url="),
                          ("vimeo.com", "https://vimeo.com/api/oembed.json?url=")):
            if host in lu and not info["title"]:
                try:
                    j = _json_get(api + urllib.parse.quote(url, safe=""))
                    info.update(title=j.get("title", ""), author=j.get("author_name", ""),
                                image=j.get("thumbnail_url", ""), site=j.get("provider_name", host))
                except Exception:
                    pass
        if not info["title"] or not info["image"] or not info["description"]:
            b, final, ctype = http_get(url, 12, 1_500_000)
            if "image/" in (ctype or ""):
                info["image"] = info["image"] or final
                info["title"] = info["title"] or os.path.basename(urllib.parse.urlparse(final).path)
                return info
            text = decode_html(b, ctype)
            p = _MetaParser()
            try:
                p.feed(text[:600_000])
            except Exception:
                pass
            mt = p.meta
            info["title"] = info["title"] or mt.get("og:title") or mt.get("twitter:title") or html.unescape(p.title.strip())
            info["description"] = info["description"] or mt.get("og:description") or mt.get("description") or \
                mt.get("twitter:description", "")
            img = info["image"] or mt.get("og:image") or mt.get("og:image:url") or mt.get("twitter:image") or \
                mt.get("twitter:image:src", "")
            if img:
                info["image"] = urllib.parse.urljoin(final, img)
            info["site"] = mt.get("og:site_name") or info["site"]
            info["author"] = info["author"] or mt.get("author") or mt.get("article:author", "")
            info["published"] = info["published"] or mt.get("article:published_time") or mt.get("date", "")
    except Exception as ex:
        info["error"] = str(ex)[:200]
    for k in ("title", "description", "author"):
        info[k] = re.sub(r"\s+", " ", html.unescape(info.get(k) or "")).strip()[:2000]
    return info


def save_thumb_bytes(data: bytes, dest: str, size: Tuple[int, int] = (480, 320)) -> bool:
    try:
        from PIL import Image  # type: ignore
        im = Image.open(io.BytesIO(data))
        im.load()
        return save_thumb_image(im, dest, size)
    except Exception as ex:
        logger.info("vignette : %s", ex)
        return False


def save_thumb_image(im: Any, dest: str, size: Tuple[int, int] = (480, 320)) -> bool:
    try:
        from PIL import Image, ImageOps  # type: ignore
        try:
            im = ImageOps.exif_transpose(im)
        except Exception:
            pass
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGBA" if "A" in im.mode or im.mode == "P" else "RGB")
        im.thumbnail(size, Image.Resampling.LANCZOS)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        im.save(dest, "PNG")
        return True
    except Exception as ex:
        logger.info("vignette : %s", ex)
        return False


def thumb_path(store: Store, sid: int, iid: int) -> str:
    d = os.path.join(store.subject_media_dir(sid), "_vignettes")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"v{iid}.png")


def thumb_from_file(path: str, dest: str) -> bool:
    ext = os.path.splitext(path)[1].lower()
    if ext in IMG_EXT:
        try:
            from PIL import Image  # type: ignore
            with Image.open(path) as im:
                im.load()
                return save_thumb_image(im.copy(), dest)
        except Exception as ex:
            logger.info("vignette image %s : %s", path, ex)
            return False
    if ext in VIDEO_EXT:
        ff = find_ffmpeg()
        if not ff:
            return False
        tmp = dest + ".tmp.png"
        for ss in ("3", "0"):
            try:
                run_hidden([ff, "-y", "-ss", ss, "-i", path, "-frames:v", "1", "-vf", "scale=480:-2", tmp], 40)
                if os.path.isfile(tmp) and os.path.getsize(tmp) > 0:
                    with open(tmp, "rb") as f:
                        ok = save_thumb_bytes(f.read(), dest)
                    os.remove(tmp)
                    return ok
            except Exception:
                pass
    return False


# ================================================================ extraction de texte
class _TextHTML(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "head", "nav", "footer", "form", "button", "iframe"}
    BLOCK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section", "article", "blockquote", "pre"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: List[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


def html_to_text(s: str) -> str:
    try:
        from bs4 import BeautifulSoup  # type: ignore
        soup = BeautifulSoup(s, "html.parser")
        for t in soup(["script", "style", "noscript", "svg", "nav", "footer", "form", "iframe", "header", "aside"]):
            t.decompose()
        root = soup.find("article") or soup.find("main") or soup.body or soup
        txt = root.get_text("\n")
    except Exception:
        p = _TextHTML()
        try:
            p.feed(s)
        except Exception:
            pass
        txt = "".join(p.out)
    lines = [re.sub(r"[ \t\xa0]+", " ", ln).strip() for ln in txt.splitlines()]
    out, blank = [], 0
    for ln in lines:
        if not ln:
            blank += 1
            if blank == 1:
                out.append("")
            continue
        blank = 0
        out.append(ln)
    return "\n".join(out).strip()


def _xml_text(data: bytes, para_tags: Tuple[str, ...] = ("</w:p>", "</text:p>", "</a:p>", "</p>", "</si>")) -> str:
    s = data.decode("utf-8", "ignore")
    for t in para_tags:
        s = s.replace(t, t + "\n")
    s = re.sub(r"<w:tab/>", "\t", s)
    s = re.sub(r"<[^>]+>", "", s)
    return html.unescape(s)


MAX_EXTRACT = 1_500_000


def extract_text(path: str) -> Tuple[str, Dict[str, Any]]:
    """Texte d'un document (pour la recherche) + infos (pages...)."""
    ext = os.path.splitext(path)[1].lower()
    info: Dict[str, Any] = {}
    txt = ""
    try:
        if ext == ".pdf":
            try:
                from pypdf import PdfReader  # type: ignore
            except ImportError:
                info["note"] = "pypdf absent : texte du PDF non extrait (pip install pypdf)"
                return "", info
            r = PdfReader(path)
            info["pages"] = len(r.pages)
            parts = []
            total = 0
            for i, pg in enumerate(r.pages):
                if i >= 400 or total > MAX_EXTRACT:
                    break
                try:
                    t = pg.extract_text() or ""
                except Exception:
                    t = ""
                parts.append(t)
                total += len(t)
            txt = "\n\n".join(parts)
            try:
                md = r.metadata
                if md and md.title:
                    info["doc_title"] = str(md.title)
                if md and md.author:
                    info["doc_author"] = str(md.author)
            except Exception:
                pass
        elif ext in (".docx", ".pptx", ".xlsx", ".odt", ".odp", ".ods", ".epub"):
            with zipfile.ZipFile(path) as z:
                names = z.namelist()
                if ext == ".docx":
                    txt = _xml_text(z.read("word/document.xml"))
                elif ext == ".pptx":
                    slides = sorted([n for n in names if re.match(r"ppt/slides/slide\d+\.xml$", n)],
                                    key=lambda n: int(re.findall(r"\d+", n)[-1]))
                    info["pages"] = len(slides)
                    txt = "\n\n".join(_xml_text(z.read(n)) for n in slides)
                elif ext == ".xlsx":
                    txt = _xml_text(z.read("xl/sharedStrings.xml")) if "xl/sharedStrings.xml" in names else ""
                elif ext in (".odt", ".odp", ".ods"):
                    txt = _xml_text(z.read("content.xml"))
                elif ext == ".epub":
                    parts = [n for n in names if n.lower().endswith((".xhtml", ".html", ".htm"))]
                    txt = "\n\n".join(html_to_text(z.read(n).decode("utf-8", "ignore")) for n in sorted(parts)[:400])
        elif ext in (".html", ".htm"):
            with open(path, "rb") as f:
                txt = html_to_text(decode_html(f.read(MAX_EXTRACT * 2)))
        elif ext == ".rtf":
            with open(path, "rb") as f:
                s = f.read(MAX_EXTRACT).decode("latin-1", "ignore")
            s = re.sub(r"\\'([0-9a-f]{2})", lambda m: bytes([int(m.group(1), 16)]).decode("cp1252", "ignore"), s)
            s = re.sub(r"\\par[d]?", "\n", s)
            s = re.sub(r"\{\\\*[^{}]*\}|\\[a-z]+-?\d* ?|[{}]", "", s)
            txt = s
        elif ext in TEXT_EXT or ext == "":
            with open(path, "rb") as f:
                b = f.read(MAX_EXTRACT)
            txt = decode_html(b)
    except Exception as ex:
        info["note"] = f"texte non extrait : {ex}"[:200]
    txt = re.sub(r"[ \t]+\n", "\n", txt or "")
    txt = re.sub(r"\n{3,}", "\n\n", txt).strip()
    return txt[:MAX_EXTRACT], info


# ================================================================ OCR (Windows integre, optionnel)
OCR_PS = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$path = $args[0]
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($WinRtTask, $ResultType) {
  $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
  $netTask = $asTask.Invoke($null, @($WinRtTask))
  $netTask.Wait(-1) | Out-Null
  $netTask.Result
}
$engine = $null
try { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new('fr')) } catch {}
if ($engine -eq $null) { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages() }
if ($engine -eq $null) { Write-Output '##NOENGINE##'; exit 3 }
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($path)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
foreach ($l in $result.Lines) { Write-Output $l.Text }
"""


def ocr_available() -> str:
    if IS_WIN:
        return "windows"
    if shutil.which("tesseract") and module_ok("pytesseract"):
        return "tesseract"
    return ""


def ocr_image(path: str) -> Tuple[str, str]:
    """(texte, erreur) - OCR Windows (Windows.Media.Ocr) sinon Tesseract si installe."""
    if not os.path.isfile(path):
        return "", "fichier introuvable"
    src = path
    tmp_png = ""
    try:
        from PIL import Image  # type: ignore
        with Image.open(path) as im:
            w, h = im.size
            if os.path.splitext(path)[1].lower() not in (".png", ".jpg", ".jpeg", ".bmp") or max(w, h) > 9000 or min(w, h) < 40:
                im2 = im.convert("RGB")
                if max(w, h) > 9000:
                    im2.thumbnail((9000, 9000))
                if min(w, h) < 40:
                    im2 = im2.resize((w * 3, h * 3))
                fd, tmp_png = tempfile.mkstemp(suffix=".png", prefix="grim_ocr_")
                os.close(fd)
                im2.save(tmp_png)
                src = tmp_png
    except Exception:
        pass
    try:
        if IS_WIN:
            fd, ps = tempfile.mkstemp(suffix=".ps1", prefix="grim_ocr_")
            with os.fdopen(fd, "w", encoding="utf-8-sig") as f:
                f.write(OCR_PS)
            try:
                r = run_hidden(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                                "-File", ps, os.path.abspath(src)], 90)
            finally:
                try:
                    os.remove(ps)
                except OSError:
                    pass
            out = r.stdout.decode("utf-8", "replace").strip()
            if "##NOENGINE##" in out:
                return "", "aucune langue OCR installée dans Windows (Paramètres → Langue → Français : reconnaissance optique)"
            if r.returncode != 0 and not out:
                return "", (r.stderr.decode("utf-8", "replace").strip().splitlines() or ["échec de l'OCR Windows"])[-1][:300]
            return out.replace("\r\n", "\n").replace("\r", "\n"), ""
        if shutil.which("tesseract") and module_ok("pytesseract"):
            import pytesseract  # type: ignore
            from PIL import Image  # type: ignore
            return pytesseract.image_to_string(Image.open(src), lang="fra+eng").strip(), ""
        return "", "OCR indisponible sur ce système"
    except Exception as ex:
        return "", str(ex)[:300]
    finally:
        if tmp_png:
            try:
                os.remove(tmp_png)
            except OSError:
                pass


# ================================================================ transcription (faster-whisper, optionnel)
WHISPER_HELP = ("La transcription des mémos vocaux se fait 100 % sur ce PC avec le module optionnel faster-whisper "
                "(environ 300 Mo + le modèle, téléchargé une seule fois).\n\nPour l'installer : menu Outils → "
                "« Installer la transcription (faster-whisper) », ou relancer setup_padawan.bat et répondre O.\n\n"
                "En attendant, tu peux écrire un résumé dans l'onglet Notes du mémo : il sera cherchable.")
_WHISPER_MODEL: Dict[str, Any] = {}


def whisper_available() -> bool:
    try:
        import importlib.util
        return importlib.util.find_spec("faster_whisper") is not None
    except Exception:
        return False


def transcribe(path: str, model_size: str = "small", progress: Optional[Callable[[str], None]] = None) -> Tuple[str, str]:
    """(texte horodate, erreur)."""
    if not whisper_available():
        return "", "faster-whisper n'est pas installé"
    try:
        from faster_whisper import WhisperModel  # type: ignore
        if model_size not in _WHISPER_MODEL:
            if progress:
                progress(f"Chargement du modèle Whisper « {model_size} » (la première fois, téléchargement)…")
            _WHISPER_MODEL[model_size] = WhisperModel(model_size, device="cpu", compute_type="int8")
        model = _WHISPER_MODEL[model_size]
        segs, info = model.transcribe(path, language="fr", vad_filter=True, beam_size=5)
        lines = []
        for s in segs:
            lines.append(f"[{fmt_dur(s.start)}] {s.text.strip()}")
            if progress and len(lines) % 5 == 0:
                progress(f"Transcription… {fmt_dur(s.end)}")
        return "\n".join(lines), ""
    except Exception as ex:
        logger.error("transcription : %s", traceback.format_exc())
        return "", str(ex)[:300]


# ================================================================ capture complete d'une page web
def capture_page(url: str, dest_dir: str, base: str, progress: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
    """HTML hors ligne (base href) + texte lisible + PDF et image pleine page (Edge/Chrome sans fenetre)."""
    url = fix_url(url)
    os.makedirs(dest_dir, exist_ok=True)
    res: Dict[str, Any] = {"files": [], "title": "", "text": "", "errors": []}
    base = safe_name(base or domain_of(url) or "page", 60)
    try:
        if progress:
            progress("Téléchargement de la page…")
        b, final, ctype = http_get(url, 25, 15_000_000)
        s = decode_html(b, ctype)
        p = _MetaParser()
        try:
            p.feed(s[:600_000])
        except Exception:
            pass
        res["title"] = (p.meta.get("og:title") or html.unescape(p.title)).strip()
        res["description"] = p.meta.get("og:description") or p.meta.get("description", "")
        res["image"] = urllib.parse.urljoin(final, p.meta.get("og:image", "")) if p.meta.get("og:image") else ""
        s2 = re.sub(r"<meta[^>]+charset[^>]*>", "", s, flags=re.I)
        tag = f'<meta charset="utf-8"><base href="{html.escape(final, quote=True)}">'
        if re.search(r"<head[^>]*>", s2, re.I):
            s2 = re.sub(r"(<head[^>]*>)", lambda m: m.group(1) + tag, s2, count=1, flags=re.I)
        else:
            s2 = tag + s2
        hp = os.path.join(dest_dir, base + ".html")
        hp = unique_path(dest_dir, os.path.basename(hp))
        with open(hp, "w", encoding="utf-8") as f:
            f.write(f"<!-- Capturé par Grimoire le {now_iso()} depuis {html.escape(final)} -->\n" + s2)
        res["html"] = hp
        res["files"].append(hp)
        res["text"] = html_to_text(s)[:MAX_EXTRACT]
        res["final_url"] = final
    except Exception as ex:
        res["errors"].append(f"page : {ex}")
    br = find_browser()
    if br:
        prof = tempfile.mkdtemp(prefix="grim_edge_")
        common = [br, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", "--hide-scrollbars",
                  "--mute-audio", f"--user-data-dir={prof}", "--virtual-time-budget=8000"]
        try:
            if progress:
                progress("PDF de la page (Edge sans fenêtre)…")
            pdf = unique_path(dest_dir, base + ".pdf")
            run_hidden(common + ["--no-pdf-header-footer", f"--print-to-pdf={pdf}", url], 90)
            if os.path.isfile(pdf) and os.path.getsize(pdf) > 1000:
                res["pdf"] = pdf
                res["files"].append(pdf)
            if progress:
                progress("Image pleine page…")
            png = unique_path(dest_dir, base + "_capture.png")
            run_hidden(common + ["--window-size=1280,3000", f"--screenshot={png}", url], 90)
            if os.path.isfile(png) and os.path.getsize(png) > 1000:
                res["png"] = png
                res["files"].append(png)
        except Exception as ex:
            res["errors"].append(f"navigateur : {ex}")
        finally:
            shutil.rmtree(prof, ignore_errors=True)
    else:
        res["errors"].append("Edge/Chrome introuvable : PDF et image non créés")
    return res


# ================================================================ lecture audio (ffplay cache)
class AudioPlayer:
    """Lecture d'un son avec ffplay sans fenetre ; pause = arret en memorisant la position."""

    def __init__(self):
        self.proc: Optional[subprocess.Popen] = None
        self.path = ""
        self.t0 = 0.0
        self.offset = 0.0
        self.paused_at = 0.0

    def play(self, path: str, start: float = 0.0) -> str:
        self.stop()
        ff = find_ff_tool("ffplay")
        if not ff:
            return "ffplay introuvable (installé avec ffmpeg par setup_padawan.bat)"
        try:
            self.proc = popen_hidden([ff, "-nodisp", "-autoexit", "-hide_banner", "-loglevel", "quiet",
                                      "-ss", f"{max(0.0, start):.2f}", path])
        except Exception as ex:
            return str(ex)
        self.path = path
        self.t0 = time.time()
        self.offset = max(0.0, start)
        self.paused_at = 0.0
        return ""

    def playing(self) -> bool:
        return bool(self.proc and self.proc.poll() is None)

    def position(self) -> float:
        if self.playing():
            return self.offset + time.time() - self.t0
        return self.paused_at

    def pause(self) -> None:
        if self.playing():
            pos = self.position()
            self.stop()
            self.paused_at = pos

    def stop(self) -> None:
        if self.proc:
            try:
                if self.proc.poll() is None:
                    self.proc.kill()
            except Exception:
                pass
        self.proc = None
        self.paused_at = 0.0


# ================================================================ enregistrement du micro
class Recorder:
    """Memo vocal : sounddevice (micro par defaut) -> FLAC via soundfile, niveau en direct."""

    def __init__(self):
        self.stream = None
        self.sf = None
        self.q: "queue.Queue[Any]" = queue.Queue()
        self.level = 0.0
        self.frames = 0
        self.sr = 44100
        self.path = ""
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.error = ""

    @staticmethod
    def devices() -> Tuple[List[Tuple[int, str]], Optional[int], str]:
        try:
            import sounddevice as sd  # type: ignore
        except Exception as ex:
            return [], None, f"module sounddevice absent ({ex.__class__.__name__}) : pip install sounddevice soundfile"
        try:
            sd._terminate()
            sd._initialize()
        except Exception:
            pass
        try:
            devs = sd.query_devices()
            apis = sd.query_hostapis()
        except Exception as ex:
            return [], None, f"audio indisponible : {ex}"
        out, seen = [], set()
        for i, d in enumerate(devs):
            if int(d.get("max_input_channels", 0)) <= 0:
                continue
            api = apis[d["hostapi"]]["name"] if d.get("hostapi") is not None else ""
            if "WDM-KS" in api:
                continue
            key = (d["name"][:28], api)
            if key in seen:
                continue
            seen.add(key)
            out.append((i, f"{d['name']}  ({api})"))
        try:
            dflt = sd.default.device[0]
            dflt = int(dflt) if dflt is not None and int(dflt) >= 0 else None
        except Exception:
            dflt = None
        if not out:
            return [], None, "Aucun micro détecté. Branche un micro (ou la webcam) puis clique « Actualiser »."
        if dflt is None or dflt not in [i for i, _ in out]:
            dflt = out[0][0]
        return out, dflt, ""

    def start(self, path: str, device: Optional[int] = None) -> str:
        try:
            import sounddevice as sd  # type: ignore
            import soundfile as sf  # type: ignore
        except Exception as ex:
            return f"modules audio absents : {ex}"
        try:
            info = sd.query_devices(device, "input")
            self.sr = int(info.get("default_samplerate") or 44100)
            fmt = "FLAC" if path.lower().endswith(".flac") else "WAV"
            self.sf = sf.SoundFile(path, "w", samplerate=self.sr, channels=1, format=fmt, subtype="PCM_16")
            self.path = path
            self.frames = 0
            self.level = 0.0

            def cb(indata, frames, _t, status):
                try:
                    self.q.put(indata.copy())
                    self.frames += frames
                    peak = float(abs(indata).max()) / 32768.0 if frames else 0.0
                    self.level = max(peak, self.level * 0.85)
                except Exception:
                    pass
            self.stream = sd.InputStream(device=device, channels=1, samplerate=self.sr, dtype="int16", callback=cb)
            self.running = True
            self.thread = threading.Thread(target=self._writer, daemon=True)
            self.thread.start()
            self.stream.start()
            return ""
        except Exception as ex:
            self.running = False
            try:
                if self.sf:
                    self.sf.close()
            except Exception:
                pass
            try:
                if path and os.path.isfile(path):
                    os.remove(path)
            except OSError:
                pass
            return f"impossible d'ouvrir le micro : {ex}"

    def _writer(self):
        while self.running or not self.q.empty():
            try:
                data = self.q.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                self.sf.write(data)
            except Exception as ex:
                self.error = str(ex)

    def duration(self) -> float:
        return self.frames / float(self.sr or 1)

    def stop(self) -> Tuple[str, float]:
        try:
            if self.stream:
                self.stream.stop()
                self.stream.close()
        except Exception:
            pass
        self.stream = None
        self.running = False
        if self.thread:
            self.thread.join(timeout=3)
        try:
            if self.sf:
                self.sf.close()
        except Exception:
            pass
        self.sf = None
        return self.path, self.duration()

    def cancel(self) -> None:
        p, _d = self.stop()
        try:
            if p and os.path.isfile(p):
                os.remove(p)
        except OSError:
            pass


# ================================================================ contenu de depart
SEED_SUBJECTS: List[Tuple[str, str, str, str, List[Tuple[str, str, str, str]]]] = [
    ("Bienvenue", "👋", "#FFFF55", "Le mode d'emploi du Grimoire (supprimable).", []),
    (INBOX_SUBJECT, "📥", "#C0C0C0", "Ce qui arrive de l'Archiveur, de Padawan, d'Arsenal ou de la ligne de commande.", []),
    ("Géopolitique", "🌍", "#7FB2FF", "", []),
    ("Recettes", "🍲", "#FFAA33", "", []),
    ("Santé", "❤", "#FF5555", "", [
        ("Santé naturelle", "🍵", "#66E0B0", ""),
        ("Plantes médicinales", "🌿", "#55FF55", ""),
        ("Protocoles", "📋", "#FFD27F", "")]),
    ("Technologies informatiques", "💻", "#55FFFF", "", [
        ("Python", "🐍", "#FFFF55", ""),
        ("Arduino / NodeMCU", "🔌", "#40C4FF", ""),
        ("Windows", "🪟", "#7FB2FF", ""),
        ("Web", "🌐", "#B388FF", "")]),
    ("Savoir-faire", "💡", "#FFD27F", "Trucs bons à savoir.", []),
    ("Nature et jardinage", "🌱", "#A8E05F", "", []),
    ("Autonomie / Survie", "🏕", "#E0A060", "", []),
    ("Énergie libre / HHO", "⚡", "#FFFF55", "", []),
    ("Sciences", "🔬", "#40C4FF", "", []),
    ("Histoire", "📜", "#E0A060", "", []),
    ("Finances", "💰", "#66E0B0", "", []),
    ("Bricolage et maison", "🔨", "#FFAA33", "", []),
    ("Lectures et vidéos à voir", "📚", "#FF9EB5", "", []),
    ("Idées et projets", "🚀", "#FF77FF", "", []),
]

WELCOME_MD = """# Bienvenue dans ton Grimoire 📖
Ton carnet de recherche : tout ce que tu trouves, classé par **sujets**, et retrouvable en un instant.

## Ajouter quelque chose
- **Ctrl+V** n'importe où : colle un lien, du texte, une image ou des fichiers copiés, ils vont dans le sujet ouvert
- **Glisser-déposer** des fichiers ou des liens depuis l'Explorateur ou le navigateur
- Bouton **＋ Ajouter** : note, modèle de fiche (source, protocole, plante, recette…), lien, citation, image, document, son, page web complète
- **Ctrl+R** : mémo vocal au micro (transcription optionnelle)
- Depuis l'Archiveur : clic droit sur une archive → « Envoyer au Grimoire »

## Retrouver
- **Ctrl+F** : recherche dans tout (titres, notes, texte des PDF, transcriptions, étiquettes), sans te soucier des accents
- Vues **Liste**, **Cartes** et **Chronologie** (Ctrl+1, Ctrl+2, Ctrl+3) · **F11** : mode lecture
- ★ favori (Ctrl+D) · 📌 épingler (Ctrl+P) · étiquettes (Ctrl+T) · **Ctrl+G** : aller à un sujet ou une fiche

## Organiser
- Les sujets et sous-sujets sont à gauche : clic droit pour créer, renommer (F2), changer l'icône et la couleur, épingler, fusionner, supprimer
- Glisse un sujet sur un autre pour le ranger dedans ; glisse des fiches sur un sujet pour les déplacer (avec Ctrl : copier)
- Supprimer envoie à la 🗑 Corbeille (restaurable) · **Ctrl+Z** annule

## Relier tes idées
Écris [[Recettes]] ou [[le titre d'une fiche]] dans une note : la référence devient cliquable. L'onglet Fiche montre aussi les rétroliens.
Les liens web sont toujours cliquables : https://marcsevigny.ca

## Tes données
Tout est dans `C:\\web\\FTP_HOME\\GRIMOIRE` (base grimoire.db + dossier medias), donc dans tes sauvegardes, avec des copies automatiques dans _sauvegardes.

[ ] Essayer Ctrl+V avec un lien YouTube
[ ] Créer ma première fiche « Plante médicinale » (＋ Ajouter → Modèle)
[ ] Supprimer ce sujet Bienvenue quand je suis à l'aise 😉"""

TEMPLATES: Dict[str, Tuple[str, str]] = {
    "Source / référence": ("📑", """# Source
**Titre :** 
**Auteur :** 
**Date :** 
**Lien :** 

## Résumé


## Citations clés
> 

## Fiabilité
[ ] Source primaire
[ ] Vérifiée par une autre source
Remarques : 
"""),
    "Protocole": ("📋", """# Protocole : 
**Objectif :** 
**Durée :** 

## Matériel / ingrédients
- 

## Posologie / étapes
1. 

## Précautions et contre-indications
- 

## Suivi
[ ] Jour 1 : 
[ ] Semaine 1 : 

## Sources
- 
"""),
    "Plante médicinale": ("🌿", """# Plante : 
**Nom latin :** 
**Famille :** 
**Parties utilisées :** 

## Propriétés
- 

## Usages
- 

## Préparation (tisane, teinture, cataplasme…)


## Posologie


## Précautions / interactions
- 

## Où la trouver / cueillette


## Sources
- 
"""),
    "Recette": ("🍲", """# Recette : 
**Portions :**  · **Préparation :**  · **Cuisson :** 

## Ingrédients
[ ] 

## Étapes
1. 

## Notes et variantes


**Source :** 
"""),
    "Livre / vidéo / article": ("📚", """# 
**Auteur :** 
**Lien :** 
**Vu / lu le :** 

## En bref


## À retenir
- 

## Citations
> 

## Ce que j'en pense

"""),
    "Journal de recherche": ("🔎", """# Recherche : 
**Question :** 

## Ce que je sais déjà
- 

## Pistes à explorer
[ ] 

## Trouvailles
- 

## Conclusion provisoire

"""),
    "Idée / projet": ("🚀", """# Projet : 
**Pourquoi :** 

## Matériel / budget
- 

## Étapes
[ ] 

## Prochaine action


## Liens utiles
- 
"""),
    "Expérience": ("🧪", """# Expérience : 
**Hypothèse :** 
**Date :** 

## Montage / matériel
- 

## Mesures
| Essai | Valeur | Remarque |

## Résultat


## Conclusion

"""),
    "Fait / événement": ("📅", """# Événement : 
**Date :** 
**Lieu :** 
**Acteurs :** 

## Ce qui s'est passé


## Contexte


## Sources
- 
"""),
    "Personne / contact": ("👤", """# 
**Rôle / domaine :** 
**Site / contact :** 

## Pourquoi c'est intéressant


## Œuvres, vidéos, publications
- 
"""),
}


def seed_content(store: Store, demo: bool = False) -> int:
    """Cree les sujets de depart une seule fois (renommables / supprimables ensuite)."""
    if int(store.get("seed_version", 0) or 0) >= SEED_VERSION:
        return 0
    n = 0
    welcome_sid = None
    for name, icon, color, desc, kids in SEED_SUBJECTS:
        sid = store.find_subject(name) if name == INBOX_SUBJECT else None
        if not sid:
            sid = store.add_subject(name, None, icon, color, desc, pinned=(name == "Bienvenue"))
            n += 1
        if name == "Bienvenue":
            welcome_sid = sid
        for kn, ki, kc, kd in kids:
            store.add_subject(kn, sid, ki, kc, kd)
            n += 1
    if welcome_sid:
        store.add_item(welcome_sid, "note", title="Comment utiliser le Grimoire", body=runs_to_json(md_runs(WELCOME_MD)),
                       pinned=1, fav=1, tags="aide, grimoire", source="Grimoire")
        store.add_item(welcome_sid, "quote", title="La curiosité",
                       body=runs_to_json([["La curiosité est le moteur de la recherche ; le carnet en est la mémoire.", []]]),
                       author="Grimoire", source="Exemple de citation (supprimable)", tags="exemple")
    store.set("seed_version", SEED_VERSION)
    store.set("created", now_iso())
    if demo:
        seed_demo(store)
    return n


def seed_demo(store: Store) -> None:
    """Contenu d'exemple pour les captures et --smoke (dossier de donnees de test seulement)."""
    p = store.find_subject("Plantes médicinales") or store.ensure_subject("Santé/Plantes médicinales")
    store.add_item(p, "note", title="Échinacée", tags="immunité, plante",
                   body=runs_to_json(md_runs(TEMPLATES["Plante médicinale"][1].replace("# Plante : ", "# Plante : Échinacée")
                                             .replace("**Nom latin :** ", "**Nom latin :** Echinacea purpurea")
                                             .replace("**Famille :** ", "**Famille :** Astéracées"))), fav=1)
    store.add_item(p, "link", title="Échinacée — Passeport Santé", url="https://www.passeportsante.net/fr/Solutions/PlantesSupplements/Fiche.aspx?doc=echinacee_ps",
                   tags="immunité", meta={"description": "Fiche complète : usages, posologie, précautions.", "site": "passeportsante.net"})
    store.add_item(p, "quote", title="Hippocrate", body=runs_to_json([["Que ton aliment soit ta seule médecine.", []]]),
                   author="Hippocrate", source="attribué", tags="citation")
    store.add_item(p, "video", title="Exemple de vidéo (Big Buck Bunny)", url="https://www.youtube.com/watch?v=aqz-KE-bpKQ",
                   tags="vidéo", meta={"site": "YouTube"})
    store.add_item(p, "note", title="Tisane du soir", event_date="2026-09-15",
                   body=runs_to_json(md_runs("Camomille + mélisse + tilleul.\n- 1 c. à thé de chaque\n- infuser **10 minutes**")))


# ================================================================ ajout d'items (interface, CLI, inbox)
def placeholder_title(url: str) -> str:
    yid = youtube_id(url)
    if yid:
        return "Vidéo YouTube"
    return domain_of(url) or url[:80]


def add_url(store: Store, sid: int, url: str, title: str = "", note: str = "", tags: str = "", source: str = "") -> int:
    url = fix_url(url)
    typ = "video" if is_video_url(url) else "link"
    auto = not title
    body = runs_to_json(md_runs(note)) if note else ""
    return store.add_item(sid, typ, title=title or placeholder_title(url), url=url, body=body, tags=tags,
                          source=source or domain_of(url), meta={"auto_title": auto, "pending": True})


def enrich_link(store: Store, iid: int) -> Dict[str, str]:
    it = store.item(iid)
    if not it or not it.get("url"):
        return {}
    info = fetch_link_info(it["url"])
    m = store.meta(it)
    upd: Dict[str, Any] = {}
    if info.get("title") and (m.get("auto_title") or not it.get("title")):
        upd["title"] = info["title"][:300]
    if info.get("author") and not it.get("author"):
        upd["author"] = info["author"][:200]
    if info.get("description"):
        upd["extracted"] = info["description"]
    pub = info.get("published", "")
    mm = re.match(r"(\d{4}-\d{2}-\d{2})", pub or "")
    if mm and not it.get("event_date"):
        upd["event_date"] = mm.group(1)
    if info.get("image"):
        try:
            b, _u, _c = http_get(info["image"], 12, 6_000_000)
            dest = thumb_path(store, it["subject_id"], iid)
            if save_thumb_bytes(b, dest):
                upd["thumb"] = Paths.rel(dest)
        except Exception as ex:
            logger.info("miniature %s : %s", info["image"], ex)
    m.update({"description": info.get("description", ""), "site": info.get("site", ""), "image_url": info.get("image", ""),
              "pending": False, "fetched": now_iso()})
    if info.get("error") and not info.get("title"):
        m["fetch_error"] = info["error"]
    else:
        m.pop("fetch_error", None)
    upd["meta"] = m
    store.update_item(iid, touch=False, **upd)
    return info


def add_file(store: Store, sid: int, path: str, title: str = "", move: bool = False, note: str = "", tags: str = "",
             typ: str = "") -> int:
    path = os.path.abspath(path)
    typ = typ or type_for_file(path)
    rel = store.import_file(path, sid, move=move)
    size = os.path.getsize(Paths.abs(rel)) if os.path.isfile(Paths.abs(rel)) else 0
    meta = {"filename": os.path.basename(path), "size": size, "original": path, "pending": True}
    body = runs_to_json(md_runs(note)) if note else ""
    return store.add_item(sid, typ, title=title or os.path.splitext(os.path.basename(path))[0], file=rel, body=body,
                          tags=tags, meta=meta)


def enrich_file(store: Store, iid: int, ocr: bool = False) -> None:
    it = store.item(iid)
    if not it:
        return
    p = Paths.abs(it.get("file") or "")
    if not p or not os.path.isfile(p):
        return
    m = store.meta(it)
    upd: Dict[str, Any] = {}
    ext = os.path.splitext(p)[1].lower()
    if it["type"] in ("image", "video") or ext in IMG_EXT | VIDEO_EXT:
        dest = thumb_path(store, it["subject_id"], iid)
        if thumb_from_file(p, dest):
            upd["thumb"] = Paths.rel(dest)
        if ext in IMG_EXT:
            try:
                from PIL import Image  # type: ignore
                with Image.open(p) as im:
                    m["width"], m["height"] = im.size
            except Exception:
                pass
    if it["type"] == "document" or ext in DOC_EXT:
        txt, info = extract_text(p)
        if txt:
            upd["extracted"] = txt
        m.update(info)
    if it["type"] in ("audio", "voice", "video") or ext in AUDIO_EXT | VIDEO_EXT:
        d = media_duration(p)
        if d:
            m["duration"] = d
    if ocr and ext in IMG_EXT:
        txt, err = ocr_image(p)
        if txt:
            upd["extracted"] = txt
            m["ocr"] = now_iso()
        elif err:
            m["ocr_error"] = err
    m["pending"] = False
    upd["meta"] = m
    store.update_item(iid, touch=False, **upd)


def add_text(store: Store, sid: int, text: str, title: str = "", note: str = "", tags: str = "",
             source: str = "") -> List[int]:
    """Texte quelconque : chemin existant -> fichier ; liens seuls -> liens ; sinon note."""
    t = (text or "").strip().strip('"')
    if not t:
        return []
    if len(t) < 600 and "\n" not in t and os.path.exists(t):
        if os.path.isdir(t):
            return import_folder(store, sid, t)[0]
        return [add_file(store, sid, t, title, note=note, tags=tags)]
    toks = t.split()
    if toks and all(is_url(x) for x in toks):
        return [add_url(store, sid, u, title if len(toks) == 1 else "", note, tags, source) for u in toks]
    first = next((ln.strip() for ln in t.splitlines() if ln.strip()), "Note")
    ttl = title or (first[:80] + ("…" if len(first) > 80 else ""))
    body = runs_from_any(t)
    if note:
        body += [["\n\n" + note, []]]
    return [store.add_item(sid, "note", title=ttl, body=runs_to_json(body), tags=tags, source=source)]


def add_quote(store: Store, sid: int, text: str, author: str = "", source: str = "", url: str = "", page: str = "",
              tags: str = "", date: str = "") -> int:
    words = re.sub(r"\s+", " ", text).strip()
    title = author or (words[:60] + ("…" if len(words) > 60 else ""))
    return store.add_item(sid, "quote", title=title, body=runs_to_json([[text.strip(), []]]), author=author, source=source,
                          url=fix_url(url) if url else "", tags=tags, event_date=date, meta={"page": page})


def add_image_pil(store: Store, sid: int, im: Any, title: str = "") -> int:
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = unique_path(store.subject_media_dir(sid), f"image_collee_{stamp}.png")
    im.save(dest, "PNG")
    meta = {"filename": os.path.basename(dest), "size": os.path.getsize(dest), "pending": True, "origin": "presse-papiers"}
    return store.add_item(sid, "image", title=title or f"Image collée {fmt_date(now_iso())}", file=Paths.rel(dest), meta=meta)


def import_folder(store: Store, sid: int, folder: str, recursive: bool = True,
                  progress: Optional[Callable[[str], None]] = None) -> Tuple[List[int], int]:
    """Cree un sous-sujet au nom du dossier (sous-dossiers = sous-sujets) et y copie les fichiers."""
    folder = os.path.abspath(folder)
    top = store.add_subject(os.path.basename(folder.rstrip("\\/")) or "Import", sid, "📂")
    ids: List[int] = []
    nsub = 1
    mapping = {folder: top}
    for root, dirs, files in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if not d.startswith((".", "_", "$"))) if recursive else []
        cur = mapping.get(root)
        if cur is None:
            parent = mapping.get(os.path.dirname(root), top)
            cur = store.add_subject(os.path.basename(root), parent, "📂")
            mapping[root] = cur
            nsub += 1
        for f in sorted(files):
            if f.lower() in ("desktop.ini", "thumbs.db") or f.startswith("~$"):
                continue
            fp = os.path.join(root, f)
            try:
                if f.lower().endswith(".url"):
                    with open(fp, "r", encoding="utf-8", errors="ignore") as fh:
                        mm = re.search(r"^URL=(.+)$", fh.read(), re.M)
                    if mm:
                        ids.append(add_url(store, cur, mm.group(1).strip(), os.path.splitext(f)[0]))
                        continue
                ids.append(add_file(store, cur, fp))
                if progress and len(ids) % 10 == 0:
                    progress(f"Import : {len(ids)} fichier(s)…")
            except Exception as ex:
                logger.warning("import %s : %s", fp, ex)
    return ids, nsub


def process_payload(store: Store, d: Dict[str, Any]) -> List[int]:
    """Ajout venant de --ajouter (direct ou par _inbox) ; retourne les ids crees (enrichis ensuite)."""
    val = str(d.get("ajouter") or "").strip()
    if not val:
        return []
    sid = store.ensure_subject(d["sujet"]) if d.get("sujet") else store.inbox_subject()
    kind = d.get("type", "")
    if kind == "citation":
        return [add_quote(store, sid, val, d.get("auteur", ""), d.get("source", ""), d.get("url", ""), tags=d.get("etiquettes", ""))]
    ids = add_text(store, sid, val, d.get("titre", ""), d.get("note", ""), d.get("etiquettes", ""), d.get("source", ""))
    return ids


LOT_TYPES = {"note": "note", "citation": "quote", "quote": "quote", "lien": "link", "link": "link", "video": "video"}


def import_lot(store: Store, data: Any, progress: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
    """Import en lot (--importer-lot fichier.json) : sujets + fiches riches (mini-markdown, liens, etiquettes,
    favoris, modeles, citations). Idempotent : une fiche deja presente (meme titre, meme sujet) est sautee.
    Format : {"lot": "nom", "sujets": [{"chemin": "Sante/Plantes", "icone": "🌿", "couleur": "#55FF55",
    "description": ""}], "fiches": [{"sujet": "...", "type": "note|citation|lien", "titre": "...", "md": "...",
    "etiquettes": "a, b", "favori": 0, "epingle": 0, "source": "", "auteur": "", "url": "", "page": "",
    "date": "AAAA-MM-JJ", "modele": "Plante médicinale"}]}"""
    if isinstance(data, list):
        data = {"fiches": data}
    lot = str(data.get("lot") or dt.datetime.now().strftime("lot_%Y%m%d_%H%M%S"))
    rep: Dict[str, Any] = {"lot": lot, "ajoutees": [], "sautees": [], "erreurs": [], "sujets_crees": 0}
    for sj in data.get("sujets", []) or []:
        try:
            path = str(sj.get("chemin") or "").strip()
            if not path:
                continue
            existed = store.find_subject(path)
            sid = store.ensure_subject(path, sj.get("icone") or "📁")
            if not existed:
                rep["sujets_crees"] += 1
                upd = {k2: sj[k1] for k1, k2 in (("couleur", "color"), ("description", "description"), ("icone", "icon"))
                       if sj.get(k1)}
                if upd:
                    store.update_subject(sid, **upd)
        except Exception as ex:
            rep["erreurs"].append(f"sujet {sj!r} : {ex}")
    for n, f in enumerate(data.get("fiches", []) or [], start=1):
        try:
            title = str(f.get("titre") or "").strip()
            sid = store.ensure_subject(f["sujet"]) if f.get("sujet") else store.inbox_subject()
            typ = LOT_TYPES.get(str(f.get("type") or "note").lower(), "note")
            if title and any(norm(r["title"]) == norm(title) for r in store.items_in([sid])):
                rep["sautees"].append(title)
                continue
            text = str(f.get("md") or f.get("texte") or "")
            meta: Dict[str, Any] = {"lot": lot, "auto_title": False}
            if f.get("modele"):
                meta["template"] = f["modele"]
            if f.get("page"):
                meta["page"] = str(f["page"])
            if f.get("description"):
                meta["description"] = str(f["description"])
            if typ == "quote":
                body = runs_to_json([[text.strip(), []]])
            else:
                body = runs_to_json(md_runs(text)) if text else ""
            url = fix_url(f["url"]) if f.get("url") else ""
            if typ == "link" and is_video_url(url):
                typ = "video"
            iid = store.add_item(sid, typ, title=title or (runs_plain(md_runs(text))[:80] or "Fiche"), body=body, url=url,
                                 tags=f.get("etiquettes") or "", source=f.get("source") or "", author=f.get("auteur") or "",
                                 fav=1 if f.get("favori") else 0, pinned=1 if f.get("epingle") else 0,
                                 event_date=f.get("date") or "", meta=meta)
            rep["ajoutees"].append(iid)
            if progress and n % 10 == 0:
                progress(f"Import en lot : {n} fiche(s)…")
        except Exception as ex:
            rep["erreurs"].append(f"fiche {f.get('titre')!r} : {ex}")
    logger.info("import en lot « %s » : %d ajoutée(s), %d sautée(s), %d erreur(s)", lot, len(rep["ajoutees"]),
                len(rep["sautees"]), len(rep["erreurs"]))
    return rep


def remove_lot(store: Store, lot: str) -> int:
    """Envoie a la corbeille (restaurable) toutes les fiches d'un lot importe."""
    ids = [r["id"] for r in store.items_where("meta LIKE ?", (f'%"lot": "{lot}"%',)) if store.meta(r).get("lot") == lot]
    if ids:
        store.trash_items(ids)
    return len(ids)


def enrich_any(store: Store, iid: int, ocr: bool = False) -> None:
    it = store.item(iid)
    if not it:
        return
    try:
        if it["type"] in ("link", "video") and it.get("url") and not it.get("file"):
            enrich_link(store, iid)
        elif it.get("file"):
            enrich_file(store, iid, ocr=ocr)
    except Exception:
        logger.error("enrichissement %s : %s", iid, traceback.format_exc())


# ================================================================ export HTML autonome / ZIP
EXPORT_CSS = """
body{font-family:Segoe UI,Arial,sans-serif;background:#f4f6fb;color:#1b2333;margin:0}
header{background:#0000AA;color:#FFFF55;padding:18px 28px;font-family:Consolas,monospace}
header h1{margin:0;font-size:26px} header p{margin:4px 0 0;color:#55FFFF}
#q{margin:10px 0 0;padding:7px 10px;width:340px;max-width:90%;border:1px solid #55FFFF;background:#000055;color:#fff;font-family:Consolas}
main{max-width:1000px;margin:0 auto;padding:18px}
nav{background:#fff;border:1px solid #d5dbe8;border-radius:8px;padding:10px 18px;margin-bottom:18px}
nav a{color:#0b3d91;text-decoration:none} nav li{margin:2px 0}
h2.subj{border-left:8px solid var(--c,#0000AA);padding:4px 12px;background:#e8ecf7;border-radius:4px;margin-top:34px}
.item{background:#fff;border:1px solid #d5dbe8;border-radius:10px;padding:14px 18px;margin:12px 0;box-shadow:0 1px 3px #0001}
.item h3{margin:0 0 4px;font-size:19px} .meta{color:#5a6478;font-size:13px;margin-bottom:8px}
.tag{display:inline-block;background:#fff6c2;border:1px solid #e6d36a;border-radius:10px;padding:0 8px;margin-right:4px;font-size:12px}
.body{line-height:1.55;font-size:15px} .body .h1{font-size:24px;font-weight:bold;color:#0b3d91}
.body .h2{font-size:20px;font-weight:bold;color:#0b3d91} .body .h3{font-size:17px;font-weight:bold}
.body .quote,blockquote{border-left:4px solid #9fb3d9;padding-left:10px;color:#3d4a66;font-style:italic;display:inline-block}
code{background:#eef0f3;padding:0 4px;border-radius:3px} mark{background:#fff176}
.ref{color:#8B1FA9;font-weight:bold} a{color:#0645AD}
img.thumb{max-width:100%;max-height:420px;border-radius:6px;border:1px solid #ccd;display:block;margin:8px 0}
details{margin-top:8px} details pre{white-space:pre-wrap;background:#f7f8fb;padding:10px;border-radius:6px;max-height:420px;overflow:auto}
.cite{font-size:18px;font-style:italic;border-left:5px solid #FFAA33;padding:6px 14px;background:#fffaf0}
footer{color:#7a8499;font-size:12px;text-align:center;padding:24px}
"""
EXPORT_JS = """
document.getElementById('q').addEventListener('input',function(){var t=this.value.toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g,'');
document.querySelectorAll('.item').forEach(function(e){var s=e.textContent.toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g,'');e.style.display=(!t||s.indexOf(t)>=0)?'':'none';});});
"""


def _data_uri(path: str, max_bytes: int = 4_000_000) -> str:
    try:
        if os.path.getsize(path) > max_bytes:
            return ""
        mt = mimetypes.guess_type(path)[0] or "application/octet-stream"
        with open(path, "rb") as f:
            return f"data:{mt};base64," + base64.b64encode(f.read()).decode("ascii")
    except OSError:
        return ""


def export_subject(store: Store, sid: int, out_html: str, include_sub: bool = True, zip_media: bool = False,
                   item_ids: Optional[List[int]] = None) -> int:
    """HTML autonome (images integrees) ; zip_media=True : medias copies a cote (dossier medias/) pour un ZIP."""
    out_dir = os.path.dirname(os.path.abspath(out_html))
    media_out = os.path.join(out_dir, "medias")
    sids = [sid] + (store.descendants(sid) if include_sub else []) if sid else []
    root_name = store.subject_path(sid) if sid else "Sélection"
    n = 0
    toc, body = [], []

    def media_ref(rel: str, inline_ok: bool) -> str:
        p = Paths.abs(rel)
        if not p or not os.path.isfile(p):
            return ""
        if zip_media:
            os.makedirs(media_out, exist_ok=True)
            dst = unique_path(media_out, os.path.basename(p))
            shutil.copy2(p, dst)
            return "medias/" + urllib.parse.quote(os.path.basename(dst))
        if inline_ok:
            u = _data_uri(p)
            if u:
                return u
        return "file:///" + urllib.parse.quote(p.replace("\\", "/"), safe="/:")

    def render(it: Dict[str, Any]) -> str:
        m = store.meta(it)
        ic = TYPES.get(it["type"], TYPES["file"])["icon"]
        h = [f'<div class="item" id="i{it["id"]}"><h3>{ic} {html.escape(it.get("title") or "(sans titre)")}'
             f'{" ★" if it.get("fav") else ""}{" 📌" if it.get("pinned") else ""}</h3>']
        meta = [TYPES.get(it["type"], TYPES["file"])["label"], fmt_date(it.get("event_date") or it.get("created") or "", False)]
        if it.get("author"):
            meta.append("par " + html.escape(it["author"]))
        if it.get("source"):
            meta.append("source : " + _linkify_html(it["source"]))
        h.append('<div class="meta">' + " · ".join(x for x in meta if x) + "</div>")
        if it.get("tags"):
            h.append("<div>" + "".join(f'<span class="tag">#{html.escape(t)}</span>' for t in tag_list(it["tags"])) + "</div>")
        if it.get("url"):
            h.append(f'<p>🔗 <a href="{html.escape(it["url"], quote=True)}" target="_blank">{html.escape(it["url"])}</a></p>')
        img_rel = it.get("file") if it["type"] == "image" else (it.get("thumb") or "")
        if img_rel:
            src = media_ref(img_rel, True)
            if src:
                link = it.get("url") or src
                h.append(f'<a href="{html.escape(link, quote=True)}" target="_blank"><img class="thumb" src="{src}" alt=""></a>')
        if it.get("file") and it["type"] != "image":
            src = media_ref(it["file"], it["type"] in ("audio", "voice") and (m.get("size") or 0) < 8_000_000)
            if src:
                if it["type"] in ("audio", "voice"):
                    h.append(f'<audio controls src="{src}"></audio>')
                h.append(f'<p>📎 <a href="{html.escape(src, quote=True) if not src.startswith("data:") else "#"}" '
                         f'target="_blank">{html.escape(m.get("filename") or os.path.basename(it["file"]))}</a> '
                         f'({human_size(m.get("size"))})</p>')
        if m.get("description"):
            h.append(f"<p><em>{_linkify_html(m['description'])}</em></p>")
        runs = runs_from_any(it.get("body"))
        if runs:
            cls = "body cite" if it["type"] == "quote" else "body"
            h.append(f'<div class="{cls}">{runs_to_html(runs)}</div>')
        if it.get("extracted") and it["type"] not in ("link", "video"):
            lab = {"voice": "Transcription", "audio": "Transcription", "image": "Texte reconnu (OCR)"}.get(it["type"], "Texte extrait")
            h.append(f"<details><summary>{lab}</summary><pre>{html.escape(it['extracted'][:200000])}</pre></details>")
        h.append("</div>")
        return "\n".join(h)

    if item_ids:
        its = [store.item(i) for i in item_ids]
        its = [i for i in its if i]
        body.append("".join(render(i) for i in its))
        n = len(its)
    for s in sids:
        subj = store.subject(s)
        if not subj:
            continue
        its = sorted(store.items_in([s]), key=lambda i: (-int(i["pinned"] or 0), float(i["sort"] or 0)))
        depth = len(store.subject_path(s).split(" › ")) - len(root_name.split(" › "))
        toc.append(f'<li style="margin-left:{depth * 18}px"><a href="#s{s}">{html.escape(subj["icon"] or "📁")} '
                   f'{html.escape(subj["name"])}</a> ({len(its)})</li>')
        body.append(f'<h2 class="subj" id="s{s}" style="--c:{html.escape(subj["color"] or "#0000AA")}">'
                    f'{html.escape(subj["icon"] or "📁")} {html.escape(store.subject_path(s))}</h2>')
        if subj.get("description"):
            body.append(f"<p>{_linkify_html(subj['description'])}</p>")
        for it in its:
            body.append(render(it))
            n += 1
    doc = f"""<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Grimoire — {html.escape(root_name)}</title>
<style>{EXPORT_CSS}</style></head><body>
<header><h1>📖 Grimoire — {html.escape(root_name)}</h1><p>{n} fiche(s) · exporté le {fmt_date(now_iso())}</p>
<input id="q" placeholder="Filtrer…" autocomplete="off"></header><main>
{('<nav><b>Sommaire</b><ul>' + ''.join(toc) + '</ul></nav>') if len(toc) > 1 else ''}
{''.join(body)}
</main><footer>Exporté depuis le Grimoire du Projet Padawan</footer><script>{EXPORT_JS}</script></body></html>"""
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(doc)
    return n


def export_subject_zip(store: Store, sid: int, out_zip: str, include_sub: bool = True) -> int:
    tmp = tempfile.mkdtemp(prefix="grim_zip_")
    try:
        n = export_subject(store, sid, os.path.join(tmp, "index.html"), include_sub, zip_media=True)
        with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
            for root, _d, files in os.walk(tmp):
                for f in files:
                    fp = os.path.join(root, f)
                    z.write(fp, os.path.relpath(fp, tmp))
        return n
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ================================================================ interface : utilitaires
TK9 = False


def tk_col(line: str, i: int) -> int:
    """Index Python -> colonne Tk (Tk 8.6 compte les emoji hors BMP comme 2 caracteres)."""
    if TK9:
        return i
    return len(line[:i].encode("utf-16-le")) // 2


def apply_styles(root) -> None:
    st = ttk.Style(root)
    try:
        st.theme_use("clam")
    except tk.TclError:
        pass
    lh = tkfont.Font(font=fnt("GUI")).metrics("linespace")
    st.configure(".", background=C["BG"], foreground=C["FG"], fieldbackground=C["ENTRY_BG"], font=fnt("GUI"),
                 bordercolor=C["LINE"], lightcolor=C["PANEL"], darkcolor=C["PANEL"], troughcolor=C["PANEL"],
                 selectbackground=C["SEL"], selectforeground=C["ON_SEL"], insertcolor=C["ENTRY_FG"])
    st.configure("TFrame", background=C["BG"])
    st.configure("TLabel", background=C["BG"], foreground=C["FG"])
    st.configure("Treeview", background=C["CARD"], fieldbackground=C["CARD"], foreground=C["TEXT"],
                 rowheight=lh + 8, font=fnt("GUI"), borderwidth=0)
    st.map("Treeview", background=[("selected", C["SEL"])], foreground=[("selected", C["ON_SEL"])])
    st.configure("Treeview.Heading", background=C["PANEL"], foreground=C["HI"], font=fnt("GHead"), relief="flat")
    st.map("Treeview.Heading", background=[("active", C["HOVER"])])
    st.configure("Subj.Treeview", background=C["PANEL"], fieldbackground=C["PANEL"], foreground=C["TEXT"], rowheight=lh + 9)
    st.configure("TCombobox", fieldbackground=C["ENTRY_BG"], background=C["BTN"], foreground=C["ENTRY_FG"],
                 arrowcolor=C["FG"], selectbackground=C["ENTRY_BG"], selectforeground=C["ENTRY_FG"], padding=2)
    st.map("TCombobox", fieldbackground=[("readonly", C["ENTRY_BG"])], foreground=[("readonly", C["ENTRY_FG"])],
           selectbackground=[("readonly", C["ENTRY_BG"])], selectforeground=[("readonly", C["ENTRY_FG"])])
    root.option_add("*TCombobox*Listbox.background", C["ENTRY_BG"])
    root.option_add("*TCombobox*Listbox.foreground", C["ENTRY_FG"])
    root.option_add("*TCombobox*Listbox.selectBackground", C["SEL"])
    root.option_add("*TCombobox*Listbox.selectForeground", C["ON_SEL"])
    root.option_add("*TCombobox*Listbox.font", fnt("GUI"))
    for orient in ("Vertical", "Horizontal"):
        st.configure(f"{orient}.TScrollbar", background=C["BTN"], troughcolor=C["PANEL"], arrowcolor=C["FG"],
                     bordercolor=C["LINE"], gripcount=0, arrowsize=16)
        st.map(f"{orient}.TScrollbar", background=[("active", C["HOVER"])])
    st.configure("TNotebook", background=C["PANEL"], borderwidth=0, tabmargins=(4, 4, 4, 0))
    st.configure("TNotebook.Tab", background=C["BTN"], foreground=C["TEXT"], padding=(10, 3), font=fnt("GUI"),
                 bordercolor=C["LINE"], lightcolor=C["PANEL"])
    st.map("TNotebook.Tab", background=[("selected", C["HI"]), ("active", C["HOVER"])],
           foreground=[("selected", C["ON_HI"])])
    st.configure("TCheckbutton", background=C["BG"], foreground=C["TEXT"], indicatorbackground=C["ENTRY_BG"])
    st.configure("Horizontal.TProgressbar", background=C["OK"], troughcolor=C["ENTRY_BG"], bordercolor=C["LINE"])


def mk_button(parent, text: str, cmd: Callable, kind: str = "", width: int = 0, tip: str = "", font_name: str = "GUI"):
    """Bouton plat aux couleurs du theme. kind : '' | 'accent' | 'danger' | 'ghost'."""
    bg, fg, abg, afg = C["BTN"], C["BTN_FG"], C["HI"], C["ON_HI"]
    if kind == "accent":
        bg, fg, abg, afg = C["HI"], C["ON_HI"], C["HI_ACT"], C["ON_HI"]
    elif kind == "danger":
        bg, fg = C["BTN"], C["ERR"]
    elif kind == "ghost":
        bg = parent.cget("bg") if "bg" in parent.keys() else C["BG"]
    elif kind == "rec":
        bg, fg, abg, afg = "#AA0000", "#FFFFFF", "#FF3333", "#FFFFFF"
    b = tk.Button(parent, text=text, command=cmd, bg=bg, fg=fg, activebackground=abg, activeforeground=afg,
                  relief="flat", bd=0, highlightthickness=1, highlightbackground=C["LINE"], padx=9, pady=3,
                  font=fnt(font_name if kind != "accent" else "GUIB"), cursor="hand2", disabledforeground=C["DISABLED"])
    if width:
        b.configure(width=width)
    b._colors = (bg, fg, abg, afg)  # type: ignore[attr-defined]
    b.bind("<Enter>", lambda _e: b.configure(bg=b._colors[2], fg=b._colors[3]) if str(b["state"]) != "disabled" else None)
    b.bind("<Leave>", lambda _e: b.configure(bg=b._colors[0], fg=b._colors[1]))
    if tip:
        Tooltip(b, tip)
    return b


def mk_entry(parent, var=None, width: int = 30, font_name: str = "GUI"):
    return tk.Entry(parent, textvariable=var, width=width, bg=C["ENTRY_BG"], fg=C["ENTRY_FG"], insertbackground=C["HI"],
                    relief="flat", highlightthickness=1, highlightbackground=C["LINE"], highlightcolor=C["HI"],
                    font=fnt(font_name), selectbackground=C["SEL"], selectforeground=C["ON_SEL"],
                    disabledbackground=C["PANEL"], readonlybackground=C["ENTRY_BG"])


def mk_text(parent, height: int = 4, width: int = 40, font_name: str = "GMono", wrap: str = "word"):
    return tk.Text(parent, height=height, width=width, bg=C["ENTRY_BG"], fg=C["ENTRY_FG"], insertbackground=C["HI"],
                   relief="flat", highlightthickness=1, highlightbackground=C["LINE"], highlightcolor=C["HI"],
                   font=fnt(font_name), wrap=wrap, selectbackground=C["SEL"], selectforeground=C["ON_SEL"], undo=True,
                   padx=6, pady=4)


def mk_label(parent, text: str = "", key: str = "FG", font_name: str = "GUI", bg: str = "", **kw):
    return tk.Label(parent, text=text, fg=C[key], bg=bg or parent.cget("bg"), font=fnt(font_name), **kw)


def mk_link(parent, text: str, target: str, bg: str = "", font_name: str = "GUI", wrap: int = 0, cmd: Optional[Callable] = None):
    """Libelle cliquable (souligne, curseur main) : ouvre un lien, un fichier ou appelle cmd."""
    f = fnt(font_name)
    try:
        uf = tkfont.Font(font=f)
        uf.configure(underline=True)
    except Exception:
        uf = f
    lab = tk.Label(parent, text=text, fg=C["LINK"], bg=bg or parent.cget("bg"), font=uf, cursor="hand2",
                   justify="left", anchor="w", wraplength=wrap or 0)
    lab._ufont = uf  # type: ignore[attr-defined]
    lab.bind("<Button-1>", lambda _e: cmd() if cmd else (open_url(target) if re.match(r"(?i)^(https?://|www\.)", target)
                                                          else open_path(target)))
    Tooltip(lab, target if not cmd else "")
    return lab


def mk_check(parent, text: str, var, bg: str = "", cmd: Optional[Callable] = None):
    b = bg or parent.cget("bg")
    return tk.Checkbutton(parent, text=text, variable=var, bg=b, fg=C["TEXT"], selectcolor=C["ENTRY_BG"],
                          activebackground=b, activeforeground=C["HI"], font=fnt("GUI"), anchor="w",
                          highlightthickness=0, bd=0, command=cmd)


def style_menu(m) -> None:
    m.configure(bg=C["PANEL"], fg=C["TEXT"], activebackground=C["SEL"], activeforeground=C["ON_SEL"],
                font=fnt("GUI"), tearoff=0, relief="flat", bd=1, selectcolor=C["HI"], disabledforeground=C["DISABLED"])


def new_menu(parent):
    m = tk.Menu(parent, tearoff=0)
    style_menu(m)
    return m


def popup(m, e) -> None:
    try:
        m.tk_popup(e.x_root, e.y_root)
    finally:
        try:
            m.grab_release()
        except Exception:
            pass


class Tooltip:
    """Infobulle simple (delai 500 ms)."""

    def __init__(self, widget, text: Any, delay: int = 500):
        self.w = widget
        self.text = text
        self.delay = delay
        self.tip = None
        self.job = None
        widget.bind("<Enter>", self._sched, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _sched(self, _e=None):
        self._cancel()
        self.job = self.w.after(self.delay, self._show)

    def _cancel(self):
        if self.job:
            try:
                self.w.after_cancel(self.job)
            except Exception:
                pass
            self.job = None

    def _show(self):
        txt = self.text() if callable(self.text) else self.text
        if not txt:
            return
        try:
            self.tip = show_tip(self.w, txt, self.w.winfo_pointerx() + 14, self.w.winfo_pointery() + 18)
        except tk.TclError:
            self.tip = None

    def _hide(self, _e=None):
        self._cancel()
        if self.tip is not None:
            try:
                self.tip.destroy()
            except Exception:
                pass
            self.tip = None


def show_tip(widget, txt: str, x: int, y: int):
    tw = tk.Toplevel(widget)
    tw.wm_overrideredirect(True)
    try:
        tw.attributes("-topmost", True)
    except tk.TclError:
        pass
    tk.Label(tw, text=txt, bg=C["TIP_BG"], fg=C["TIP_FG"], font=fnt("GSM"), justify="left", relief="solid", bd=1,
             padx=6, pady=3, wraplength=520).pack()
    tw.update_idletasks()
    sw, sh = widget.winfo_screenwidth(), widget.winfo_screenheight()
    w, h = tw.winfo_reqwidth(), tw.winfo_reqheight()
    x = min(x, sw - w - 4)
    if y + h > sh - 4:
        y = y - h - 30
    tw.wm_geometry(f"+{max(0, x)}+{max(0, y)}")
    return tw


def wheel_steps(e) -> int:
    if getattr(e, "num", None) == 4:
        return -1
    if getattr(e, "num", None) == 5:
        return 1
    d = int(getattr(e, "delta", 0) or 0)
    if d == 0:
        return 0
    return -max(1, abs(d) // 120) if d > 0 else max(1, abs(d) // 120)


class ScrollFrame(tk.Frame):
    """Cadre defilant vertical ; la molette fait defiler le Text survole s'il y en a un."""

    def __init__(self, parent, bg: str = "", **kw):
        bg = bg or C["BG"]
        super().__init__(parent, bg=bg, **kw)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self.win = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.vsb.pack(side="right", fill="y")
        self.inner.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.win, width=e.width))
        self.bind("<Enter>", self._on, add="+")
        self.bind("<Leave>", self._off, add="+")

    def _on(self, _e=None):
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.bind_all(seq, self._wheel)

    def _off(self, _e=None):
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.unbind_all(seq)

    def _wheel(self, e):
        n = wheel_steps(e)
        w = e.widget
        try:
            if isinstance(w, tk.Text):
                w.yview_scroll(n * 3, "units")
                return "break"
            if isinstance(w, (tk.Listbox, ttk.Treeview)):
                w.yview_scroll(n * 3, "units")
                return "break"
        except Exception:
            pass
        if self.inner.winfo_reqheight() > self.canvas.winfo_height():
            self.canvas.yview_scroll(n * 3, "units")
        return "break"

    def clear(self):
        for w in self.inner.winfo_children():
            w.destroy()
        self.canvas.yview_moveto(0)


class FlowFrame(tk.Frame):
    """Rangee de widgets qui passe a la ligne quand la place manque (rien n'est coupe a 1024 px)."""

    def __init__(self, parent, bg: str = "", gap: int = 2, **kw):
        super().__init__(parent, bg=bg or C["BG"], height=30, **kw)
        self.items: List[Tuple[Any, int]] = []
        self.hidden: set = set()
        self.gap = gap
        self.bind("<Configure>", lambda _e: self.reflow())

    def add(self, w, pad: int = 2) -> None:
        self.items.append((w, pad))

    def show(self, w, on: bool) -> None:
        if on:
            self.hidden.discard(str(w))
        else:
            self.hidden.add(str(w))

    def reflow(self) -> None:
        try:
            W = self.winfo_width()
        except tk.TclError:
            return
        if W < 50:
            W = max(300, self.master.winfo_width() - 16)
        x, y, rowh = 0, 0, 0
        for w, pad in self.items:
            if str(w) in self.hidden:
                w.place_forget()
                continue
            ww, hh = w.winfo_reqwidth(), w.winfo_reqheight()
            if x and x + pad + ww > W:
                x, y = 0, y + rowh + self.gap + 1
                rowh = 0
            px = x + (pad if x else 0)
            w.place(x=px, y=y)
            x = px + ww
            rowh = max(rowh, hh)
        h = y + rowh
        if int(self.cget("height") or 0) != h:
            self.configure(height=h)


def work_area(widget) -> Tuple[int, int, int, int]:
    if IS_WIN:
        try:
            r = wintypes.RECT()
            if ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(r), 0):
                return r.left, r.top, r.right - r.left, r.bottom - r.top
        except Exception:
            pass
    return 0, 0, widget.winfo_screenwidth(), widget.winfo_screenheight()


def copy_to_clipboard(root, text: str) -> None:
    try:
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update_idletasks()
    except tk.TclError:
        pass


def color_swatch(root, color: str, size: int = 12):
    img = tk.PhotoImage(master=root, width=size, height=size)
    try:
        img.put(C["LINE"], to=(0, 0, size, size))
        img.put(color or C["DIM"], to=(1, 1, size - 1, size - 1))
    except tk.TclError:
        pass
    return img


class Dialog(tk.Toplevel):
    """Fenetre modale centree, aux couleurs du theme, bornee a l'ecran."""

    def __init__(self, parent, title: str, w: int = 640, h: int = 420, resizable: bool = True, modal: bool = True):
        super().__init__(parent)
        self.parent = parent
        self.result = None
        self.withdraw()
        self.title(title)
        self.configure(bg=C["BG"])
        try:
            ico = os.path.join(BASE, "grimoire1.ico")
            if os.path.isfile(ico):
                self.iconbitmap(ico)
        except tk.TclError:
            pass
        top = parent.winfo_toplevel()
        pw, ph = top.winfo_width(), top.winfo_height()
        if pw < 200:
            pw, ph = top.winfo_screenwidth(), top.winfo_screenheight()
        wx, wy, ww, wh = work_area(self)
        w = min(w, max(300, pw - 30), ww - 30)
        h = min(h, max(240, ph - 40), wh - 50)
        x = top.winfo_rootx() + (pw - w) // 2
        y = top.winfo_rooty() + max(0, (ph - h) // 2 - 10)
        x = max(wx, min(x, wx + ww - w - 10))
        y = max(wy, min(y, wy + wh - h - 40))
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.resizable(resizable, resizable)
        self.transient(top)
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.bind("<Escape>", lambda _e: self.cancel())
        self._modal = modal

    def show(self, focus=None):
        self.deiconify()
        self.lift()
        if self._modal:
            try:
                self.grab_set()
            except tk.TclError:
                pass
        try:
            (focus or self).focus_set()
        except tk.TclError:
            pass
        return self

    def wait(self):
        self.wait_window(self)
        return self.result

    def cancel(self):
        self.result = None
        self.destroy()

    def button_bar(self, buttons: List[Tuple[str, Callable, str]]):
        bar = tk.Frame(self, bg=C["PANEL"])
        bar.pack(side="bottom", fill="x")
        for text, cmd, kind in reversed(buttons):
            mk_button(bar, text, cmd, kind).pack(side="right", padx=6, pady=8)
        return bar

    def row(self, parent, label: str, r: int, widget, hint: str = ""):
        mk_label(parent, label, "HI", "GUIB").grid(row=r, column=0, sticky="nw", padx=(10, 8), pady=4)
        widget.grid(row=r, column=1, sticky="we", padx=(0, 10), pady=4)
        if hint:
            mk_label(parent, hint, "DIM", "GSM", wraplength=420, justify="left").grid(row=r + 1, column=1, sticky="w", padx=(0, 10))


class TextDialog(Dialog):
    """Texte long en lecture (aide, statistiques, rapport) ; # titre, ## sous-titre, liens cliquables."""

    def __init__(self, parent, title: str, content: str, w: int = 900, h: int = 640):
        super().__init__(parent, title, w, h, modal=False)
        self.button_bar([("Copier", lambda: copy_to_clipboard(self, content), ""), ("Fermer", self.cancel, "accent")])
        fr = tk.Frame(self, bg=C["BG"])
        fr.pack(fill="both", expand=True, padx=8, pady=8)
        self.t = tk.Text(fr, bg=C["CARD"], fg=C["TEXT"], font=fnt("GUI"), wrap="word", relief="flat", padx=12, pady=8,
                         highlightthickness=0, selectbackground=C["SEL"], selectforeground=C["ON_SEL"], spacing1=1, spacing3=2)
        sb = ttk.Scrollbar(fr, orient="vertical", command=self.t.yview)
        self.t.configure(yscrollcommand=sb.set)
        self.t.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.t.tag_configure("h1", foreground=C["HI"], font=fnt("GTitle"), spacing1=8, spacing3=4)
        self.t.tag_configure("h2", foreground=C["HI"], font=fnt("GUIB"), spacing1=10, spacing3=2)
        self.t.tag_configure("k", foreground=C["FG"], font=fnt("GUIB"))
        self.t.tag_configure("bar", foreground=C["OK"])
        self.t.tag_configure("url", foreground=C["LINK"], underline=True)
        self.t.tag_bind("url", "<Enter>", lambda _e: self.t.configure(cursor="hand2"))
        self.t.tag_bind("url", "<Leave>", lambda _e: self.t.configure(cursor=""))
        self.t.tag_bind("url", "<Button-1>", self._click)
        for line in content.split("\n"):
            if line.startswith("# "):
                self.t.insert("end", line[2:] + "\n", "h1")
            elif line.startswith("## "):
                self.t.insert("end", line[3:] + "\n", "h2")
            elif line.startswith("  ") and " : " in line:
                k, v = line.split(" : ", 1)
                self.t.insert("end", k + " : ", "k")
                self._ins(v + "\n")
            else:
                self._ins(line + "\n")
        self.t.configure(state="disabled")
        self.show(self.t)

    def _ins(self, s: str):
        pos = 0
        for m in URL_RE.finditer(s):
            self.t.insert("end", s[pos:m.start()], "bar" if "█" in s[pos:m.start()] else ())
            self.t.insert("end", m.group(1), "url")
            pos = m.end()
        rest = s[pos:]
        if "█" in rest:
            i = rest.index("█")
            j = len(rest) - len(rest.lstrip("█")) if rest.startswith("█") else rest.rindex("█") + 1
            self.t.insert("end", rest[:i])
            self.t.insert("end", rest[i:j], "bar")
            self.t.insert("end", rest[j:])
        else:
            self.t.insert("end", rest)

    def _click(self, e):
        idx = self.t.index(f"@{e.x},{e.y}")
        r = self.t.tag_prevrange("url", idx + "+1c")
        if r:
            open_url(self.t.get(*r))


class AskDialog(Dialog):
    """Question simple : une ligne (ou plusieurs avec multiline)."""

    def __init__(self, parent, title: str, prompt: str, value: str = "", multiline: bool = False, w: int = 560):
        super().__init__(parent, title, w, 300 if multiline else 190, resizable=multiline)
        self.multiline = multiline
        self.button_bar([("Annuler", self.cancel, ""), ("OK", self._ok, "accent")])
        mk_label(self, prompt, "HI", "GUIB", wraplength=w - 40, justify="left").pack(anchor="w", padx=12, pady=(12, 6))
        if multiline:
            self.e = mk_text(self, 6, 40, "GUI")
            self.e.insert("1.0", value)
            self.e.pack(fill="both", expand=True, padx=12, pady=4)
        else:
            self.v = tk.StringVar(value=value)
            self.e = mk_entry(self, self.v, 50)
            self.e.pack(fill="x", padx=12, pady=4, ipady=3)
            self.e.select_range(0, "end")
            self.e.bind("<Return>", lambda _e: self._ok())
        self.show(self.e)

    def _ok(self):
        self.result = self.e.get("1.0", "end-1c") if self.multiline else self.v.get()
        self.destroy()


def ask_string(parent, title: str, prompt: str, value: str = "", multiline: bool = False) -> Optional[str]:
    return AskDialog(parent, title, prompt, value, multiline).wait()


class EmojiPicker(Dialog):
    def __init__(self, parent, current: str = ""):
        super().__init__(parent, "Choisir une icône", 640, 520)
        self.button_bar([("Aucune", self._none, ""), ("Annuler", self.cancel, ""), ("OK", self._ok, "accent")])
        top = tk.Frame(self, bg=C["BG"])
        top.pack(fill="x", padx=10, pady=(10, 4))
        mk_label(top, "Icône (emoji ou caractère) :", "HI", "GUIB").pack(side="left")
        self.v = tk.StringVar(value=current)
        e = mk_entry(top, self.v, 6, "EmojiSM")
        e.pack(side="left", padx=8)
        sf = ScrollFrame(self, bg=C["BG"])
        sf.pack(fill="both", expand=True, padx=8, pady=4)
        for name, chars in EMOJI_SETS:
            mk_label(sf.inner, name, "FG", "GHead").pack(anchor="w", padx=4, pady=(6, 0))
            g = tk.Frame(sf.inner, bg=C["BG"])
            g.pack(anchor="w")
            for i, ch in enumerate(self._split(chars)):
                b = tk.Button(g, text=ch, command=lambda c=ch: self._pick(c), bg=C["BG"], fg=C["TEXT"], relief="flat", bd=0,
                              activebackground=C["SEL"], font=fnt("EmojiSM"), cursor="hand2", width=2)
                b.grid(row=i // 13, column=i % 13, padx=1, pady=1)
        self.show(e)

    @staticmethod
    def _split(s: str) -> List[str]:
        out: List[str] = []
        for ch in s:
            if out and (ch in "\ufe0f\u200d" or unicodedata.category(ch) == "Mn" or (out[-1].endswith("\u200d"))):
                out[-1] += ch
            else:
                out.append(ch)
        return out

    def _pick(self, ch):
        self.v.set(ch)
        self._ok()

    def _none(self):
        self.result = ""
        self.destroy()

    def _ok(self):
        self.result = self.v.get().strip()
        self.destroy()

    def cancel(self):
        self.result = None
        self.destroy()


class SubjectDialog(Dialog):
    """Creer / modifier un sujet : nom, icone, couleur, parent, description, epingle."""

    def __init__(self, parent, app, title: str, subj: Optional[Dict[str, Any]] = None, parent_id: Optional[int] = None):
        super().__init__(parent, title, 680, 520)
        self.app = app
        st = app.store
        s = subj or {}
        self.sid = s.get("id")
        self.button_bar([("Annuler", self.cancel, ""), ("Enregistrer", self._ok, "accent")])
        f = tk.Frame(self, bg=C["BG"])
        f.pack(fill="both", expand=True, padx=6, pady=8)
        f.columnconfigure(1, weight=1)
        self.v_name = tk.StringVar(value=s.get("name", ""))
        e = mk_entry(f, self.v_name, 40, "GUIB")
        self.row(f, "Nom", 0, e)
        e.bind("<Return>", lambda _e: self._ok())
        ic = tk.Frame(f, bg=C["BG"])
        self.v_icon = tk.StringVar(value=s.get("icon") or "📁")
        mk_entry(ic, self.v_icon, 4, "EmojiSM").pack(side="left")
        mk_button(ic, "Choisir…", self._pick).pack(side="left", padx=6)
        self.row(f, "Icône", 1, ic)
        cf = tk.Frame(f, bg=C["BG"])
        self.v_color = tk.StringVar(value=s.get("color") or random.choice(SUBJECT_COLORS))
        self.color_btns = []
        for i, col in enumerate(SUBJECT_COLORS):
            b = tk.Button(cf, bg=col, activebackground=col, width=2, relief="flat", bd=0, highlightthickness=2,
                          cursor="hand2", command=lambda c=col: self._set_color(c))
            b.grid(row=i // 8, column=i % 8, padx=2, pady=2)
            self.color_btns.append((col, b))
        mk_button(cf, "Autre…", self._other_color, font_name="GSM").grid(row=0, column=8, rowspan=2, padx=6)
        self.row(f, "Couleur", 2, cf)
        self._set_color(self.v_color.get())
        self.parents = [(None, "(racine : sujet principal)")]
        excl = {self.sid} | set(st.descendants(self.sid)) if self.sid else set()
        for sid in app.subject_order():
            if sid not in excl:
                self.parents.append((sid, "   " * (len(st.subject_path(sid).split(" › ")) - 1) + st.subject_label(sid).split(" ", 1)[0]
                                     + " " + st.subject(sid)["name"]))
        self.cb_parent = ttk.Combobox(f, values=[p[1] for p in self.parents], state="readonly", font=fnt("GUI"))
        cur = s.get("parent_id") if subj else parent_id
        idx = next((i for i, p in enumerate(self.parents) if p[0] == cur), 0)
        self.cb_parent.current(idx)
        self.row(f, "Dans", 3, self.cb_parent)
        self.t_desc = mk_text(f, 4, 40, "GUI")
        self.t_desc.insert("1.0", s.get("description", ""))
        self.row(f, "Description", 4, self.t_desc)
        self.v_pin = tk.BooleanVar(value=bool(s.get("pinned")))
        self.row(f, "", 5, mk_check(f, "📌 Épinglé (toujours en haut)", self.v_pin))
        self.show(e)
        e.select_range(0, "end")

    def _pick(self):
        r = EmojiPicker(self, self.v_icon.get()).wait()
        if r is not None:
            self.v_icon.set(r or "📁")

    def _set_color(self, c):
        self.v_color.set(c)
        for col, b in self.color_btns:
            b.configure(highlightbackground=C["HI"] if col.lower() == c.lower() else C["BG"],
                        relief="solid" if col.lower() == c.lower() else "flat")

    def _other_color(self):
        from tkinter import colorchooser
        r = colorchooser.askcolor(self.v_color.get(), parent=self, title="Couleur du sujet")
        if r and r[1]:
            self._set_color(r[1])

    def _ok(self):
        name = self.v_name.get().strip()
        if not name:
            messagebox.showwarning(APP_NAME, "Donne un nom au sujet.", parent=self)
            return
        self.result = {"name": name, "icon": self.v_icon.get().strip() or "📁", "color": self.v_color.get(),
                       "parent_id": self.parents[self.cb_parent.current()][0],
                       "description": self.t_desc.get("1.0", "end-1c").strip(), "pinned": int(self.v_pin.get())}
        self.destroy()


class SubjectChooser(Dialog):
    """Choisir un sujet (deplacer, copier, fusionner) avec filtre."""

    def __init__(self, parent, app, title: str, prompt: str, allow_root: bool = False, exclude: Iterable[int] = ()):
        super().__init__(parent, title, 560, 560)
        self.app = app
        self.allow_root = allow_root
        self.exclude = set(exclude)
        self.button_bar([("Annuler", self.cancel, ""), ("＋ Nouveau sujet…", lambda: self._new(False), ""),
                         ("＋ Sous-sujet du sujet choisi…", lambda: self._new(True), ""), ("OK", self._ok, "accent")])
        mk_label(self, prompt, "HI", "GUIB", wraplength=520, justify="left").pack(anchor="w", padx=12, pady=(10, 4))
        self.v = tk.StringVar()
        e = mk_entry(self, self.v, 40)
        e.pack(fill="x", padx=12, pady=4, ipady=2)
        fr = tk.Frame(self, bg=C["BG"])
        fr.pack(fill="both", expand=True, padx=12, pady=4)
        self.tv = ttk.Treeview(fr, show="tree", selectmode="browse", style="Subj.Treeview")
        sb = ttk.Scrollbar(fr, orient="vertical", command=self.tv.yview)
        self.tv.configure(yscrollcommand=sb.set)
        self.tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.v.trace_add("write", lambda *_a: self.fill())
        e.bind("<Down>", lambda _e: (self.tv.focus_set(), self._first()))
        e.bind("<Return>", lambda _e: self._ok())
        self.tv.bind("<Double-Button-1>", lambda _e: self._ok())
        self.tv.bind("<Return>", lambda _e: self._ok())
        self.fill()
        self.show(e)

    def _first(self):
        ch = self.tv.get_children("")
        if ch:
            self.tv.selection_set(ch[0])
            self.tv.focus(ch[0])

    def fill(self):
        st = self.app.store
        self.tv.delete(*self.tv.get_children(""))
        q = norm(self.v.get())
        if self.allow_root and not q:
            self.tv.insert("", "end", iid="root", text="⬆ (racine : sujet principal)")
        if q:
            for sid in self.app.subject_order():
                if sid in self.exclude:
                    continue
                if all(t in norm(st.subject_path(sid)) for t in q.split()):
                    self.tv.insert("", "end", iid=f"s{sid}", text=st.subject_label(sid))
        else:
            def add(parent_iid, pid):
                for s in st.children(pid):
                    if s["id"] in self.exclude:
                        continue
                    self.tv.insert(parent_iid, "end", iid=f"s{s['id']}", text=f"{s['icon'] or '📁'} {s['name']}", open=True)
                    add(f"s{s['id']}", s["id"])
            add("", None)
        self._first()

    def _new(self, sub: bool = False):
        par = None
        if sub:
            sel = self.tv.selection()
            if not sel or sel[0] == "root":
                messagebox.showinfo(APP_NAME, "Choisis d'abord dans la liste le sujet qui recevra le sous-sujet.", parent=self)
                return
            par = int(sel[0][1:])
        r = SubjectDialog(self, self.app, "Nouveau sous-sujet" if par else "Nouveau sujet", None, par).wait()
        if r:
            sid = self.app.store.add_subject(r["name"], r["parent_id"], r["icon"], r["color"], r["description"], bool(r["pinned"]))
            if r["parent_id"]:
                self.app.store.update_subject(r["parent_id"], expanded=1)
            self.app.refresh_tree()
            self.app.reveal_subject(sid)
            self.result = sid
            self.destroy()

    def _ok(self):
        sel = self.tv.selection()
        if not sel:
            return
        self.result = 0 if sel[0] == "root" else int(sel[0][1:])
        self.destroy()


class SubjectManager(Dialog):
    """Fenetre « Gerer les sujets » : tous les sujets, sur tous les niveaux, avec leurs actions."""

    def __init__(self, parent, app):
        super().__init__(parent, "Gérer les sujets", 820, 620, modal=False)
        self.app = app
        mk_label(self, "Tous les sujets. Choisis-en un puis une action, ou glisse-le dans l'arbre principal. "
                       "Double-clic = modifier.", "HI", "GUIB", wraplength=780, justify="left").pack(anchor="w", padx=12, pady=(10, 4))
        body = tk.Frame(self, bg=C["BG"])
        body.pack(fill="both", expand=True, padx=12, pady=4)
        fr = tk.Frame(body, bg=C["BG"])
        fr.pack(side="left", fill="both", expand=True)
        self.tv = ttk.Treeview(fr, show="tree", columns=("n",), selectmode="browse", style="Subj.Treeview")
        self.tv.column("n", width=50, anchor="e", stretch=False)
        sb = ttk.Scrollbar(fr, orient="vertical", command=self.tv.yview)
        self.tv.configure(yscrollcommand=sb.set)
        self.tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        bx = tk.Frame(body, bg=C["BG"])
        bx.pack(side="right", fill="y", padx=(10, 0))
        acts = [("📁 Nouveau sujet principal", lambda s: self._do(lambda: app.new_subject(None)), False),
                ("📂 Nouveau sous-sujet", lambda s: self._do(lambda: app.new_subject(s)), True),
                ("✏ Renommer (F2)", lambda s: self._do(lambda: app.rename_subject_id(s)), True),
                ("⚙ Modifier…", lambda s: self._do(lambda: app.edit_subject(s)), True),
                ("😀 Icône…", lambda s: self._do(lambda: app.set_subject_icon(s)), True),
                ("🎨 Couleur…", lambda s: self._do(lambda: app.set_subject_color(s)), True),
                ("⬆ Monter", lambda s: self._do(lambda: app.store.reorder_subject(s, -1)), True),
                ("⬇ Descendre", lambda s: self._do(lambda: app.store.reorder_subject(s, 1)), True),
                ("📁 Ranger dans…", lambda s: self._do(lambda: app._subject_into(s)), True),
                ("⤴ Rendre principal", lambda s: self._do(lambda: app.promote_subject(s)), True),
                ("🔀 Fusionner dans…", lambda s: self._do(lambda: app.merge_subject(s)), True),
                ("🗑 Supprimer (corbeille)", lambda s: self._do(lambda: app.delete_subject(s)), True)]
        for lab, fn, need in acts:
            mk_button(bx, lab, lambda fn=fn, need=need: self._run(fn, need), font_name="GSM").pack(fill="x", pady=2)
        self.button_bar([("Fermer", self.cancel, "accent")])
        self.tv.bind("<Double-Button-1>", lambda _e: self._run(lambda s: self._do(lambda: app.edit_subject(s)), True))
        self.tv.bind("<F2>", lambda _e: self._run(lambda s: self._do(lambda: app.rename_subject_id(s)), True))
        self.fill()
        self.show(self.tv)

    def _sid(self) -> Optional[int]:
        sel = self.tv.selection()
        return int(sel[0][1:]) if sel else None

    def _run(self, fn, need: bool):
        sid = self._sid()
        if need and not sid:
            messagebox.showinfo(APP_NAME, "Choisis d'abord un sujet dans la liste.", parent=self)
            return
        fn(sid)

    def _do(self, fn):
        sid = self._sid()
        fn()
        self.app.refresh_tree()
        self.fill(sid)
        if sid and self.app.store.subject(sid):
            self.app.reveal_subject(sid, flash=False)

    def fill(self, keep: Optional[int] = None):
        st = self.app.store
        tot = st.total_counts()
        self.tv.delete(*self.tv.get_children(""))

        def add(piid, pid):
            for s in st.children(pid):
                iid = f"s{s['id']}"
                self.tv.insert(piid, "end", iid=iid, text=f"{s['icon'] or '📁'} {s['name']}",
                               values=(tot.get(s["id"], 0) or "",), image=self.app.swatch(s["color"]), open=True)
                add(iid, s["id"])
        add("", None)
        if keep and self.tv.exists(f"s{keep}"):
            self.tv.selection_set(f"s{keep}")
            self.tv.see(f"s{keep}")


class LinkDialog(Dialog):
    def __init__(self, parent, app, url: str = ""):
        super().__init__(parent, "Ajouter un lien web", 700, 480)
        self.button_bar([("Annuler", self.cancel, ""), ("Ajouter", self._ok, "accent")])
        f = tk.Frame(self, bg=C["BG"])
        f.pack(fill="both", expand=True, padx=6, pady=8)
        f.columnconfigure(1, weight=1)
        self.v_url = tk.StringVar(value=url)
        e = mk_entry(f, self.v_url, 50)
        self.row(f, "Lien", 0, e, "Le titre, la description et la miniature sont récupérés automatiquement.")
        self.v_title = tk.StringVar()
        self.row(f, "Titre", 2, mk_entry(f, self.v_title, 50), "Laisser vide : titre de la page.")
        self.v_tags = tk.StringVar()
        self.row(f, "Étiquettes", 4, mk_entry(f, self.v_tags, 50), "Séparées par des virgules.")
        self.t_note = mk_text(f, 4, 40, "GUI")
        self.row(f, "Note", 6, self.t_note)
        f.rowconfigure(6, weight=1)
        self.v_cap = tk.BooleanVar(value=False)
        self.row(f, "", 7, mk_check(f, "🌐 Capturer aussi la page complète (HTML hors ligne + PDF + image)", self.v_cap))
        e.bind("<Return>", lambda _e: self._ok())
        self.show(e)
        e.select_range(0, "end")

    def _ok(self):
        u = self.v_url.get().strip()
        if not u:
            return
        if not re.match(r"(?i)^[a-z][a-z0-9+.-]*:", u) and not u.lower().startswith("www."):
            u = "https://" + u
        self.result = {"url": u, "title": self.v_title.get().strip(), "tags": self.v_tags.get(),
                       "note": self.t_note.get("1.0", "end-1c").strip(), "capture": self.v_cap.get()}
        self.destroy()


class QuoteDialog(Dialog):
    def __init__(self, parent, text: str = ""):
        super().__init__(parent, "Ajouter une citation", 720, 540)
        self.button_bar([("Annuler", self.cancel, ""), ("Ajouter", self._ok, "accent")])
        f = tk.Frame(self, bg=C["BG"])
        f.pack(fill="both", expand=True, padx=6, pady=8)
        f.columnconfigure(1, weight=1)
        self.t = mk_text(f, 6, 40, "GUI")
        self.t.insert("1.0", text)
        self.row(f, "Citation", 0, self.t)
        f.rowconfigure(0, weight=1)
        self.vs = {k: tk.StringVar() for k in ("author", "source", "url", "page", "tags", "date")}
        for i, (k, lab, hint) in enumerate((("author", "Auteur", ""), ("source", "Source", "Livre, article, vidéo, site…"),
                                            ("url", "Lien", ""), ("page", "Page / minute", ""),
                                            ("date", "Date", "AAAA-MM-JJ (facultatif)"), ("tags", "Étiquettes", ""))):
            self.row(f, lab, 1 + i, mk_entry(f, self.vs[k], 40))
        self.show(self.t)

    def _ok(self):
        txt = self.t.get("1.0", "end-1c").strip()
        if not txt:
            return
        self.result = {"text": txt, **{k: v.get().strip() for k, v in self.vs.items()}}
        self.destroy()


# ================================================================ editeur de texte riche
EDITOR_APP_KEYS = set("dgnlmoprstfe")


def configure_rich_tags(t: tk.Text, reading: bool = False) -> None:
    pre = "R" if reading else "E"
    norm_f = fnt(pre + "Norm")
    t.configure(font=norm_f)
    t.tag_configure("b", font=fnt(pre + "B"))
    t.tag_configure("i", font=fnt(pre + "I"))
    t.tag_configure("bi", font=fnt(pre + "BI"))
    t.tag_configure("u", underline=True)
    t.tag_configure("s", overstrike=True)
    t.tag_configure("h1", font=fnt(pre + "H1"), foreground=C["HI"], spacing1=8, spacing3=4)
    t.tag_configure("h2", font=fnt(pre + "H2"), foreground=C["HI"], spacing1=6, spacing3=3)
    t.tag_configure("h3", font=fnt(pre + "H3"), foreground=C["FG"], spacing1=4, spacing3=2)
    t.tag_configure("quote", font=fnt(pre + "I"), foreground=C["QUOTE"], lmargin1=22, lmargin2=22, rmargin=10)
    t.tag_configure("code", font=fnt(pre + "Code" if not reading else "RCode"), background=C["CODE_BG"], foreground=C["OK"])
    t.tag_configure("mark", background=C["MARK"])
    t.tag_configure("url", foreground=C["LINK"], underline=True)
    t.tag_configure("ref", foreground=C["REF"], underline=True)
    t.tag_configure("href", foreground=C["LINK"], underline=True)
    t.tag_configure("chk", foreground=C["HI"])
    t.tag_configure("search", background=C["SEL"], foreground=C["ON_SEL"])
    for tg in ("h3", "h2", "h1", "url", "ref", "href", "search"):
        t.tag_raise(tg)
    try:
        t.tag_raise("sel")
    except tk.TclError:
        pass


def insert_runs(t: tk.Text, runs: List[List[Any]], hrefs: Dict[str, str]) -> None:
    """Insere des runs ; les liens « a=url » deviennent des etiquettes href_N (dict hrefs : etiquette -> url)."""
    rev = {v: k for k, v in hrefs.items()}
    for text, tags in runs:
        tk_tags = []
        for tg in tags:
            if tg.startswith("a="):
                url = tg[2:]
                name = rev.get(url)
                if not name:
                    name = f"href_{len(hrefs) + 1}"
                    hrefs[name] = url
                    rev[url] = name
                tk_tags += [name, "href"]
            elif tg in RICH_TAGS:
                tk_tags.append(tg)
        t.insert("end", text, tuple(tk_tags))


def refresh_combo(t: tk.Text) -> None:
    """Gras + italique ensemble : etiquette derivee « bi »."""
    t.tag_remove("bi", "1.0", "end")
    br = t.tag_ranges("b")
    ir = t.tag_ranges("i")
    if not br or not ir:
        return
    ib = [(ir[k], ir[k + 1]) for k in range(0, len(ir), 2)]
    for k in range(0, len(br), 2):
        a, b = br[k], br[k + 1]
        for c, d in ib:
            s = a if t.compare(a, ">", c) else c
            e = b if t.compare(b, "<", d) else d
            if t.compare(s, "<", e):
                t.tag_add("bi", s, e)


def relink(t: tk.Text, terms: Optional[List[str]] = None) -> None:
    """Liens web, references [[...]], cases a cocher et surlignage de recherche."""
    for tg in ("url", "ref", "chk", "search"):
        t.tag_remove(tg, "1.0", "end")
    content = t.get("1.0", "end-1c")
    nterms = [norm(x) for x in (terms or []) if len(norm(x)) >= 2]
    for ln, line in enumerate(content.split("\n"), start=1):
        if not line:
            continue
        for m in URL_RE.finditer(line):
            t.tag_add("url", f"{ln}.{tk_col(line, m.start(1))}", f"{ln}.{tk_col(line, m.end(1))}")
        for m in REF_RE.finditer(line):
            t.tag_add("ref", f"{ln}.{tk_col(line, m.start())}", f"{ln}.{tk_col(line, m.end())}")
        for m in re.finditer("[☐☑]", line):
            t.tag_add("chk", f"{ln}.{tk_col(line, m.start())}", f"{ln}.{tk_col(line, m.end())}")
        if nterms:
            nl = norm(line)
            if len(nl) == len(line):
                for term in nterms:
                    for m in re.finditer(re.escape(term), nl):
                        t.tag_add("search", f"{ln}.{tk_col(line, m.start())}", f"{ln}.{tk_col(line, m.end())}")


class RichEditor(tk.Frame):
    """Editeur de notes : gras, italique, souligne, barre, titres, listes, cases, citation, code, surligneur,
    liens (auto et sur selection), references [[...]] ; sauvegarde automatique via on_change."""

    def __init__(self, parent, app, on_change: Optional[Callable[[], None]] = None, bg: str = ""):
        super().__init__(parent, bg=bg or C["PANEL"])
        self.app = app
        self.on_change = on_change
        self.hrefs: Dict[str, str] = {}
        self.loading = False
        self.pending: set = set()
        self.terms: List[str] = []
        self.job = None
        tb = tk.Frame(self, bg=C["PANEL"])
        tb.pack(fill="x", pady=(2, 2))
        self.tb = tb
        specs = [("G", lambda: self.toggle("b"), "Gras (Ctrl+B)", "GUIB"),
                 ("I", lambda: self.toggle("i"), "Italique (Ctrl+I)", "EI"),
                 ("S̲", lambda: self.toggle("u"), "Souligné (Ctrl+U)", "GUI"),
                 ("B̶", lambda: self.toggle("s"), "Barré (Ctrl+Maj+X)", "GUI"),
                 ("|", None, "", ""),
                 ("T1", lambda: self.heading("h1"), "Grand titre (Ctrl+1)", "GSMB"),
                 ("T2", lambda: self.heading("h2"), "Titre (Ctrl+2)", "GSMB"),
                 ("T3", lambda: self.heading("h3"), "Sous-titre (Ctrl+3)", "GSMB"),
                 ("¶", lambda: self.heading(None), "Texte normal (Ctrl+0)", "GUI"),
                 ("|", None, "", ""),
                 ("•", lambda: self.list_prefix("• "), "Liste à puces (Ctrl+Maj+8)", "GUIB"),
                 ("1.", lambda: self.list_prefix("1. "), "Liste numérotée", "GSMB"),
                 ("☐", lambda: self.list_prefix("☐ "), "Case à cocher (clic sur ☐ pour cocher)", "GUI"),
                 ("❝", lambda: self.heading("quote"), "Citation (bloc)", "GUI"),
                 ("</>", lambda: self.toggle("code"), "Code / commande", "GSM"),
                 ("🖍", lambda: self.toggle("mark"), "Surligner", "EmojiSM"),
                 ("|", None, "", ""),
                 ("🔗", self.make_link, "Lien sur la sélection, ou insérer un lien (Ctrl+K)", "EmojiSM"),
                 ("[[ ]]", self.insert_ref, "Référence vers un sujet ou une fiche ([[titre]])", "GSM"),
                 ("📅", self.insert_date, "Insérer la date du jour", "EmojiSM"),
                 ("🧹", self.clear_format, "Effacer la mise en forme de la sélection", "EmojiSM")]
        self.tb_buttons = []
        for text, cmd, tip, f in specs:
            if cmd is None:
                sep = tk.Frame(tb, bg=C["LINE"], width=1, height=18)
                sep._flow_pad = 4  # type: ignore[attr-defined]
                continue
            b = tk.Button(tb, text=text, command=cmd, bg=C["BTN"], fg=C["TEXT"], relief="flat", bd=0, padx=5, pady=0,
                          activebackground=C["HI"], activeforeground=C["ON_HI"], font=fnt(f), cursor="hand2",
                          highlightthickness=0, takefocus=0)
            b._flow_pad = 1  # type: ignore[attr-defined]
            Tooltip(b, tip)
            self.tb_buttons.append(b)
        tb.bind("<Configure>", lambda _e: self._flow())
        self.after_idle(self._flow)
        fr = tk.Frame(self, bg=C["PANEL"])
        fr.pack(fill="both", expand=True)
        self.t = tk.Text(fr, bg=C["ENTRY_BG"], fg=C["ENTRY_FG"], insertbackground=C["HI"], relief="flat", wrap="word",
                         undo=True, autoseparators=True, maxundo=-1, padx=10, pady=8, spacing1=1, spacing3=1,
                         highlightthickness=1, highlightbackground=C["LINE"], highlightcolor=C["HI"],
                         selectbackground=C["SEL"], selectforeground=C["ON_SEL"], height=8, width=30)
        vsb = ttk.Scrollbar(fr, orient="vertical", command=self.t.yview)
        self.t.configure(yscrollcommand=vsb.set)
        self.t.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        configure_rich_tags(self.t)
        t = self.t
        for tg in ("url", "ref", "href", "chk"):
            t.tag_bind(tg, "<Enter>", lambda _e: t.configure(cursor="hand2"))
            t.tag_bind(tg, "<Leave>", lambda _e: t.configure(cursor="xterm"))
        t.tag_bind("url", "<Button-1>", lambda e: self._click(e, "url"))
        t.tag_bind("ref", "<Button-1>", lambda e: self._click(e, "ref"))
        t.tag_bind("href", "<Button-1>", lambda e: self._click(e, "href"))
        t.tag_bind("chk", "<Button-1>", lambda e: self._click(e, "chk"))
        t.bind("<<Modified>>", self._modified)
        t.bind("<Control-KeyPress>", self._ctrl)
        t.bind("<Return>", self._return)
        t.bind("<KeyPress>", self._key, add="+")
        t.bind("<ButtonPress-1>", lambda _e: self.pending.clear(), add="+")
        t.bind("<Button-3>", self._menu)
        t.bind("<FocusOut>", lambda _e: self.flush(), add="+")
        t.bind("<MouseWheel>", lambda e: (t.yview_scroll(wheel_steps(e) * 3, "units"), "break")[1])

    def _flow(self):
        """Barre d'outils sur plusieurs lignes si le panneau est etroit (aucun bouton cache)."""
        tb = self.tb
        try:
            W = tb.winfo_width()
        except tk.TclError:
            return
        if W < 50:
            W = 400
        x, y, rowh = 2, 2, 0
        for w in tb.winfo_children():
            pad = getattr(w, "_flow_pad", 1)
            ww, hh = w.winfo_reqwidth(), w.winfo_reqheight()
            if x + ww + pad > W and x > 2:
                x, y = 2, y + rowh + 2
                rowh = 0
            w.place(x=x + pad, y=y + (0 if pad == 1 else 3))
            x += ww + 2 * pad
            rowh = max(rowh, hh if pad == 1 else 0)
        h = y + rowh + 2
        if int(tb.cget("height") or 0) != h:
            tb.configure(height=h)

    # ------------------------------------------------------------ contenu
    def load(self, body: Any, terms: Optional[List[str]] = None, readonly: bool = False) -> None:
        self.loading = True
        self.terms = list(terms or [])
        t = self.t
        t.configure(state="normal")
        t.delete("1.0", "end")
        for name in list(self.hrefs):
            try:
                t.tag_delete(name)
            except tk.TclError:
                pass
        self.hrefs = {}
        insert_runs(t, runs_from_any(body), self.hrefs)
        refresh_combo(t)
        relink(t, self.terms)
        t.edit_reset()
        t.edit_modified(False)
        t.mark_set("insert", "1.0")
        t.see("1.0")
        if readonly:
            t.configure(state="disabled")
        self.loading = False
        if self.terms:
            r = t.tag_nextrange("search", "1.0")
            if r:
                t.see(r[0])

    def runs(self) -> List[List[Any]]:
        out: List[List[Any]] = []
        active: List[str] = []
        for key, val, _idx in self.t.dump("1.0", "end-1c", tag=True, text=True):
            if key == "tagon":
                active.append(val)
            elif key == "tagoff":
                if val in active:
                    active.remove(val)
            elif key == "text":
                tags = []
                for tg in active:
                    if tg in RICH_TAGS:
                        tags.append(tg)
                    elif tg.startswith("href_") and tg in self.hrefs:
                        tags.append("a=" + self.hrefs[tg])
                out.append([val, tags])
        return merge_runs(out)

    def body(self) -> str:
        return runs_to_json(self.runs())

    def plain(self) -> str:
        return self.t.get("1.0", "end-1c")

    def is_empty(self) -> bool:
        return not self.plain().strip()

    # ------------------------------------------------------------ evenements
    def _modified(self, _e=None):
        if not self.t.edit_modified():
            return
        self.t.edit_modified(False)
        if self.loading:
            return
        if self.job:
            self.after_cancel(self.job)
        self.job = self.after(700, self._changed)

    def _changed(self):
        self.job = None
        try:
            refresh_combo(self.t)
            relink(self.t, self.terms)
        except tk.TclError:
            return
        if self.on_change:
            self.on_change()

    def flush(self):
        try:
            dirty = (not self.loading) and bool(self.t.edit_modified())
        except tk.TclError:
            dirty = False
        if self.job or dirty:
            if self.job:
                try:
                    self.after_cancel(self.job)
                except Exception:
                    pass
            try:
                self.t.edit_modified(False)
            except tk.TclError:
                pass
            self._changed()

    def _ctrl(self, e):
        k = (e.keysym or "").lower()
        shift = bool(e.state & 0x1)
        acts = {"b": lambda: self.toggle("b"), "i": lambda: self.toggle("i"), "u": lambda: self.toggle("u"),
                "1": lambda: self.heading("h1"), "2": lambda: self.heading("h2"), "3": lambda: self.heading("h3"),
                "0": lambda: self.heading(None), "k": self.make_link}
        if k == "x" and shift:
            self.toggle("s")
            return "break"
        if k in ("8", "asterisk") and shift:
            self.list_prefix("• ")
            return "break"
        if k in acts and not (shift and k in "123"):
            acts[k]()
            return "break"
        if k in ("plus", "equal", "minus", "kp_add", "kp_subtract") or (k == "0" and shift):
            return None
        if k in EDITOR_APP_KEYS or (shift and k in ("q", "i", "v", "n")):
            self.flush()
            return self.app.ctrl_key(e)
        return None

    def _key(self, e):
        if self.pending and e.char and e.char.isprintable() and not (e.state & 0x4):
            ctx = [tg for tg in self.t.tag_names("insert-1c") if tg in RICH_TAGS]
            tags = (set(ctx) | {p for p in self.pending if not p.startswith("-")}) - {p[1:] for p in self.pending if p.startswith("-")}
            if self.t.tag_ranges("sel"):
                self.t.delete("sel.first", "sel.last")
            self.t.insert("insert", e.char, tuple(tags))
            self.t.see("insert")
            return "break"
        if e.keysym in ("Left", "Right", "Up", "Down", "Home", "End", "Prior", "Next"):
            self.pending.clear()
        return None

    def _return(self, _e=None):
        line = self.t.get("insert linestart", "insert")
        m = re.match(r"^(\s*)(• |(\d+)\. |☐ |☑ )(.*)$", line)
        if not m:
            return None
        ind, pre, num, rest = m.group(1), m.group(2), m.group(3), m.group(4)
        if not rest.strip() and self.t.compare("insert", "==", "insert lineend"):
            self.t.delete("insert linestart", "insert")
            return "break"
        nxt = f"{int(num) + 1}. " if num else ("☐ " if pre in ("☐ ", "☑ ") else pre)
        self.t.insert("insert", "\n" + ind + nxt)
        self.t.see("insert")
        return "break"

    def _click(self, e, kind):
        idx = self.t.index(f"@{e.x},{e.y}")
        if kind == "href":
            name = next((tg for tg in self.t.tag_names(idx) if tg.startswith("href_")), "")
            if name in self.hrefs:
                open_url(self.hrefs[name])
            return "break"
        r = self.t.tag_prevrange(kind, idx + "+1c")
        if not r:
            return None
        txt = self.t.get(*r)
        if kind == "url":
            open_url(txt)
        elif kind == "ref":
            self.app.follow_ref(txt.strip("[]"))
        elif kind == "chk":
            st = self.t.cget("state")
            self.t.configure(state="normal")
            self.t.delete(r[0], r[1])
            self.t.insert(r[0], "☑" if txt == "☐" else "☐", tuple(tg for tg in self.t.tag_names(r[0]) if tg in RICH_TAGS))
            self.t.configure(state=st)
            relink(self.t, self.terms)
            self._modified_force()
        return "break"

    def _modified_force(self):
        if self.on_change and not self.loading:
            if self.job:
                self.after_cancel(self.job)
            self.job = self.after(300, self._changed)

    # ------------------------------------------------------------ mise en forme
    def _sel(self) -> Optional[Tuple[str, str]]:
        try:
            return self.t.index("sel.first"), self.t.index("sel.last")
        except tk.TclError:
            return None

    def _covered(self, tag: str, a: str, b: str) -> bool:
        r = self.t.tag_ranges(tag)
        for k in range(0, len(r), 2):
            if self.t.compare(r[k], "<=", a) and self.t.compare(r[k + 1], ">=", b):
                return True
        return False

    def toggle(self, tag: str):
        if str(self.t.cget("state")) == "disabled":
            return
        s = self._sel()
        if not s:
            # sans selection : style en attente pour les prochains caracteres tapes
            if tag in self.t.tag_names("insert-1c") and "-" + tag not in self.pending:
                self.pending.discard(tag)
                self.pending.add("-" + tag)
            elif tag in self.pending or "-" + tag in self.pending:
                self.pending.discard(tag)
                self.pending.discard("-" + tag)
            else:
                self.pending.add(tag)
            self.app.set_status(f"Style « {tag} » : " + ("activé pour la suite de la frappe" if tag in self.pending else "désactivé"))
            self.t.focus_set()
            return
        a, b = s
        self.t.edit_separator()
        if self._covered(tag, a, b):
            self.t.tag_remove(tag, a, b)
        else:
            self.t.tag_add(tag, a, b)
        refresh_combo(self.t)
        self._modified_force()
        self.t.focus_set()

    def heading(self, tag: Optional[str]):
        if str(self.t.cget("state")) == "disabled":
            return
        s = self._sel()
        a, b = (s if s else (self.t.index("insert"), self.t.index("insert")))
        a, b = self.t.index(f"{a} linestart"), self.t.index(f"{b} lineend")
        had = tag and self._covered(tag, a, b) if tag else False
        for tg in LINE_TAGS:
            self.t.tag_remove(tg, a, b + "+1c")
        if tag and not had:
            self.t.tag_add(tag, a, b + "+1c")
        self._modified_force()
        self.t.focus_set()

    def list_prefix(self, pre: str):
        if str(self.t.cget("state")) == "disabled":
            return
        s = self._sel()
        a, b = (s if s else (self.t.index("insert"), self.t.index("insert")))
        first, last = int(a.split(".")[0]), int(b.split(".")[0])
        if s and b.endswith(".0") and last > first:
            last -= 1
        self.t.edit_separator()
        n = 1
        for ln in range(first, last + 1):
            line = self.t.get(f"{ln}.0", f"{ln}.end")
            m = re.match(r"^(\s*)(• |\d+\. |☐ |☑ )", line)
            if m:
                self.t.delete(f"{ln}.{len(m.group(1))}", f"{ln}.{len(m.group(0))}")
                if (pre == "1. " and m.group(2)[0].isdigit()) or m.group(2) == pre or (pre == "☐ " and m.group(2) in ("☐ ", "☑ ")):
                    continue
            ind = len(line) - len(line.lstrip(" "))
            self.t.insert(f"{ln}.{ind}", f"{n}. " if pre == "1. " else pre)
            n += 1
        relink(self.t, self.terms)
        self._modified_force()
        self.t.focus_set()

    def make_link(self):
        if str(self.t.cget("state")) == "disabled":
            return
        s = self._sel()
        clip = ""
        try:
            clip = self.clipboard_get().strip()
        except tk.TclError:
            pass
        url = ask_string(self, "Lien", "Adresse du lien (https://…) :" if s else "Lien à insérer (https://…) :",
                         clip if is_url(clip) else "https://")
        if not url or url.strip() in ("https://", "http://"):
            return
        url = fix_url(url.strip())
        if s:
            name = f"href_{len(self.hrefs) + 1}"
            while name in self.hrefs:
                name += "x"
            self.hrefs[name] = url
            self.t.tag_configure(name)
            self.t.tag_add(name, *s)
            self.t.tag_add("href", *s)
        else:
            self.t.insert("insert", url + " ")
        self._modified_force()
        self.t.focus_set()

    def insert_ref(self):
        if str(self.t.cget("state")) == "disabled":
            return
        title = self.app.choose_reference()
        if title:
            self.t.insert("insert", f"[[{title}]]")
            relink(self.t, self.terms)
            self._modified_force()
        self.t.focus_set()

    def insert_date(self):
        if str(self.t.cget("state")) != "disabled":
            self.t.insert("insert", today())
            self.t.focus_set()

    def clear_format(self):
        s = self._sel()
        a, b = s if s else (self.t.index("insert linestart"), self.t.index("insert lineend"))
        for tg in RICH_TAGS + ("bi", "href") + tuple(self.hrefs):
            self.t.tag_remove(tg, a, b)
        self._modified_force()

    def insert_text(self, txt: str):
        self.t.insert("insert", txt)
        relink(self.t, self.terms)
        self._modified_force()

    def _menu(self, e):
        m = new_menu(self)
        st = "normal" if str(self.t.cget("state")) != "disabled" else "disabled"
        m.add_command(label="Couper", accelerator="Ctrl+X", command=lambda: self.t.event_generate("<<Cut>>"), state=st)
        m.add_command(label="Copier", accelerator="Ctrl+C", command=lambda: self.t.event_generate("<<Copy>>"))
        m.add_command(label="Coller", accelerator="Ctrl+V", command=lambda: self.t.event_generate("<<Paste>>"), state=st)
        m.add_command(label="Tout sélectionner", command=lambda: self.t.tag_add("sel", "1.0", "end-1c"))
        m.add_separator()
        f = new_menu(m)
        for lab, cmd in (("Gras", lambda: self.toggle("b")), ("Italique", lambda: self.toggle("i")),
                         ("Souligné", lambda: self.toggle("u")), ("Barré", lambda: self.toggle("s")),
                         ("Surligner", lambda: self.toggle("mark")), ("Code", lambda: self.toggle("code")),
                         ("Grand titre", lambda: self.heading("h1")), ("Titre", lambda: self.heading("h2")),
                         ("Sous-titre", lambda: self.heading("h3")), ("Citation", lambda: self.heading("quote")),
                         ("Texte normal", lambda: self.heading(None)), ("Effacer la mise en forme", self.clear_format)):
            f.add_command(label=lab, command=cmd, state=st)
        m.add_cascade(label="Mise en forme", menu=f)
        m.add_command(label="🔗 Lien…", accelerator="Ctrl+K", command=self.make_link, state=st)
        m.add_command(label="[[ ]] Référence vers une fiche…", command=self.insert_ref, state=st)
        idx = self.t.index(f"@{e.x},{e.y}")
        r = self.t.tag_prevrange("url", idx + "+1c")
        if r and self.t.compare(r[1], ">=", idx):
            u = self.t.get(*r)
            m.add_separator()
            m.add_command(label="🌐 Ouvrir le lien", command=lambda: open_url(u))
            m.add_command(label="📋 Copier le lien", command=lambda: copy_to_clipboard(self, fix_url(u)))
            m.add_command(label="＋ Ajouter ce lien comme fiche", command=lambda: self.app.add_urls([u]))
        sel = self._sel()
        if sel:
            txt = self.t.get(*sel)
            m.add_separator()
            m.add_command(label="❝ Faire une citation de la sélection", command=lambda: self.app.add_quote_dialog(txt))
            m.add_command(label="📝 Nouvelle note avec la sélection", command=lambda: self.app.new_note(text=txt))
            m.add_command(label="🔍 Chercher la sélection", command=lambda: self.app.search_for(txt[:80]))
        popup(m, e)
        return "break"


# ================================================================ visionneuse d'images
class ImageViewer(tk.Toplevel):
    """Zoom molette, glisser pour deplacer, F ajuster, 1 = 100 %, R rotation, ←/→ image precedente/suivante."""

    def __init__(self, app, paths: List[Tuple[str, str]], index: int = 0):
        super().__init__(app)
        self.app = app
        self.paths = paths
        self.index = index
        self.configure(bg=C["IMG_BG"])
        self.title("Grimoire — image")
        try:
            ico = os.path.join(BASE, "grimoire1.ico")
            if os.path.isfile(ico):
                self.iconbitmap(ico)
        except tk.TclError:
            pass
        x, y, w, h = work_area(self)
        self.geometry(f"{max(600, w - 80)}x{max(400, h - 80)}+{x + 40}+{y + 30}")
        bar = tk.Frame(self, bg=C["PANEL"])
        bar.pack(fill="x")
        self.l_title = tk.Label(bar, text="", bg=C["PANEL"], fg=C["HI"], font=fnt("GUIB"), anchor="w")
        self.l_title.pack(side="left", fill="x", expand=True, padx=8)
        for text, cmd, tip in (("✕", self.destroy, "Fermer (Échap)"), ("📂", self.open_ext, "Ouvrir avec l'application par défaut"),
                               ("⟳", lambda: self.rotate(-90), "Tourner (R)"), ("1:1", lambda: self.set_zoom(1.0), "Taille réelle (1)"),
                               ("⤢", self.fit, "Ajuster à la fenêtre (F)"), ("＋", lambda: self.zoom_by(1.25), "Zoom avant (+ ou molette)"),
                               ("－", lambda: self.zoom_by(0.8), "Zoom arrière (-)"), ("▶", lambda: self.go(1), "Image suivante (→)"),
                               ("◀", lambda: self.go(-1), "Image précédente (←)")):
            mk_button(bar, text, cmd, tip=tip).pack(side="right", padx=2, pady=3)
        self.l_info = tk.Label(bar, text="", bg=C["PANEL"], fg=C["DIM"], font=fnt("GSM"))
        self.l_info.pack(side="right", padx=8)
        self.cv = tk.Canvas(self, bg=C["IMG_BG"], highlightthickness=0, cursor="fleur")
        self.cv.pack(fill="both", expand=True)
        self.im = None
        self.tkimg = None
        self.zoom = 1.0
        self.rot = 0
        self.ox = self.oy = 0.0
        self.drag = None
        self.cv.bind("<Configure>", lambda _e: self.redraw())
        self.cv.bind("<MouseWheel>", lambda e: self.zoom_by(1.2 if wheel_steps(e) < 0 else 1 / 1.2, e.x, e.y))
        self.cv.bind("<Button-4>", lambda e: self.zoom_by(1.2, e.x, e.y))
        self.cv.bind("<Button-5>", lambda e: self.zoom_by(1 / 1.2, e.x, e.y))
        self.cv.bind("<ButtonPress-1>", lambda e: setattr(self, "drag", (e.x, e.y, self.ox, self.oy)))
        self.cv.bind("<B1-Motion>", self._move)
        self.cv.bind("<Double-Button-1>", lambda _e: self.fit())
        for k, f in (("<Escape>", lambda _e: self.destroy()), ("<Left>", lambda _e: self.go(-1)), ("<Right>", lambda _e: self.go(1)),
                     ("f", lambda _e: self.fit()), ("1", lambda _e: self.set_zoom(1.0)), ("r", lambda _e: self.rotate(-90)),
                     ("<plus>", lambda _e: self.zoom_by(1.25)), ("<minus>", lambda _e: self.zoom_by(0.8)),
                     ("<KP_Add>", lambda _e: self.zoom_by(1.25)), ("<KP_Subtract>", lambda _e: self.zoom_by(0.8))):
            self.bind(k, f)
        self.load()
        self.focus_force()

    def load(self):
        p, title = self.paths[self.index]
        self.l_title.configure(text=f"🖼 {title}   ({self.index + 1}/{len(self.paths)})")
        try:
            from PIL import Image, ImageOps  # type: ignore
            im = Image.open(p)
            try:
                im = ImageOps.exif_transpose(im)
            except Exception:
                pass
            if im.mode not in ("RGB", "RGBA"):
                im = im.convert("RGBA")
            self.im = im
            self.l_info.configure(text=f"{im.width}×{im.height} · {human_size(os.path.getsize(p))}")
        except Exception as ex:
            self.im = None
            self.l_info.configure(text=f"illisible : {ex}")
        self.rot = 0
        self.after(30, self.fit)

    def _src(self):
        if self.im is None:
            return None
        return self.im.rotate(self.rot, expand=True) if self.rot else self.im

    def fit(self):
        src = self._src()
        if src is None:
            return
        cw, ch = max(50, self.cv.winfo_width()), max(50, self.cv.winfo_height())
        self.zoom = min(cw / src.width, ch / src.height, 1.0 if max(src.width, src.height) < 200 else 99)
        self.ox = self.oy = 0
        self.redraw()

    def set_zoom(self, z: float):
        self.zoom = z
        self.redraw()

    def zoom_by(self, f: float, x: Optional[int] = None, y: Optional[int] = None):
        old = self.zoom
        self.zoom = max(0.02, min(20.0, self.zoom * f))
        if x is not None:
            cw, ch = self.cv.winfo_width(), self.cv.winfo_height()
            k = self.zoom / old
            self.ox = (self.ox - (x - cw / 2)) * k + (x - cw / 2)
            self.oy = (self.oy - (y - ch / 2)) * k + (y - ch / 2)
        self.redraw()

    def rotate(self, d: int):
        self.rot = (self.rot + d) % 360
        self.fit()

    def _move(self, e):
        if self.drag:
            x0, y0, ox, oy = self.drag
            self.ox, self.oy = ox + e.x - x0, oy + e.y - y0
            self.redraw()

    def redraw(self):
        self.cv.delete("all")
        src = self._src()
        if src is None:
            self.cv.create_text(self.cv.winfo_width() // 2, self.cv.winfo_height() // 2, text="Image illisible",
                                fill=C["ERR"], font=fnt("GTitle"))
            return
        try:
            from PIL import Image, ImageTk  # type: ignore
            w, h = max(1, int(src.width * self.zoom)), max(1, int(src.height * self.zoom))
            cw, ch = self.cv.winfo_width(), self.cv.winfo_height()
            # on ne redimensionne que la partie visible quand le zoom est fort
            if w * h > 25_000_000:
                x0 = max(0, int((w / 2 - cw / 2 - self.ox) / self.zoom))
                y0 = max(0, int((h / 2 - ch / 2 - self.oy) / self.zoom))
                x1 = min(src.width, int(x0 + cw / self.zoom) + 2)
                y1 = min(src.height, int(y0 + ch / self.zoom) + 2)
                crop = src.crop((x0, y0, x1, y1)).resize((max(1, int((x1 - x0) * self.zoom)), max(1, int((y1 - y0) * self.zoom))))
                self.tkimg = ImageTk.PhotoImage(crop, master=self)
                self.cv.create_image(cw / 2 + self.ox - w / 2 + x0 * self.zoom, ch / 2 + self.oy - h / 2 + y0 * self.zoom,
                                     image=self.tkimg, anchor="nw")
            else:
                rs = Image.Resampling.LANCZOS if self.zoom < 1 else Image.Resampling.NEAREST if self.zoom > 3 else Image.Resampling.BILINEAR
                self.tkimg = ImageTk.PhotoImage(src.resize((w, h), rs), master=self)
                self.cv.create_image(cw / 2 + self.ox, ch / 2 + self.oy, image=self.tkimg)
            self.cv.create_text(10, ch - 10, anchor="sw", text=f"{self.zoom * 100:.0f} %", fill=C["DIM"], font=fnt("GSM"))
        except Exception as ex:
            logger.warning("visionneuse : %s", ex)

    def go(self, d: int):
        if len(self.paths) > 1:
            self.index = (self.index + d) % len(self.paths)
            self.load()

    def open_ext(self):
        open_path(self.paths[self.index][0])


# ================================================================ mode lecture
class ReaderWindow(tk.Toplevel):
    """Lecture confortable plein ecran, une fiche a la fois (←/→), A-/A+, Echap pour fermer."""

    def __init__(self, app, ids: List[int], index: int = 0, terms: Optional[List[str]] = None):
        super().__init__(app)
        self.app = app
        self.ids = ids
        self.index = max(0, min(index, len(ids) - 1))
        self.terms = terms or []
        self.imgs: List[Any] = []
        self.hrefs: Dict[str, str] = {}
        self.title("Grimoire — lecture")
        self.configure(bg=C["CARD"])
        try:
            ico = os.path.join(BASE, "grimoire1.ico")
            if os.path.isfile(ico):
                self.iconbitmap(ico)
        except tk.TclError:
            pass
        x, y, w, h = work_area(self)
        self.geometry(f"{w}x{h - 30}+{x}+{y}")
        try:
            self.state("zoomed")
        except tk.TclError:
            pass
        bar = tk.Frame(self, bg=C["PANEL"])
        bar.pack(fill="x")
        mk_label(bar, "📖 Mode lecture", "HI", "GUIB").pack(side="left", padx=10, pady=4)
        self.l_pos = mk_label(bar, "", "DIM", "GSM")
        self.l_pos.pack(side="left", padx=10)
        for text, cmd, tip in (("✕ Fermer", self.destroy, "Échap"), ("A+", lambda: self.font(1), "Texte plus grand (Ctrl++)"),
                               ("A−", lambda: self.font(-1), "Texte plus petit (Ctrl+-)"), ("✏ Modifier", self.edit, "Revenir à la fiche pour la modifier"),
                               ("Suivante ▶", lambda: self.go(1), "→ ou Page suivante"), ("◀ Précédente", lambda: self.go(-1), "← ou Page précédente")):
            mk_button(bar, text, cmd, tip=tip).pack(side="right", padx=3, pady=3)
        fr = tk.Frame(self, bg=C["CARD"])
        fr.pack(fill="both", expand=True)
        self.t = tk.Text(fr, bg=C["CARD"], fg=C["TEXT"], relief="flat", wrap="word", highlightthickness=0, spacing1=3,
                         spacing2=2, spacing3=3, selectbackground=C["SEL"], selectforeground=C["ON_SEL"], cursor="arrow")
        sb = ttk.Scrollbar(fr, orient="vertical", command=self.t.yview)
        self.t.configure(yscrollcommand=sb.set)
        self.t.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        configure_rich_tags(self.t, reading=True)
        self.t.tag_configure("meta", font=fnt("GUI"), foreground=C["DIM"], spacing3=10)
        self.t.tag_configure("rtitle", font=fnt("RH1"), foreground=C["HI"], spacing1=10, spacing3=6)
        self.t.tag_configure("sect", font=fnt("RH3"), foreground=C["FG"], spacing1=16, spacing3=4)
        self.t.tag_configure("cite", font=fnt("RI"), foreground=C["TEXT"], lmargin1=30, lmargin2=30)
        self.t.tag_configure("center", justify="center")
        for tg in ("url", "ref", "href"):
            self.t.tag_bind(tg, "<Enter>", lambda _e: self.t.configure(cursor="hand2"))
            self.t.tag_bind(tg, "<Leave>", lambda _e: self.t.configure(cursor="arrow"))
        self.t.tag_bind("url", "<Button-1>", self._click_url)
        self.t.tag_bind("href", "<Button-1>", self._click_href)
        self.t.tag_bind("ref", "<Button-1>", self._click_ref)
        self.t.bind("<Configure>", lambda _e: self._margins())
        self.t.bind("<Key>", lambda e: None if (e.state & 0x4 and e.keysym.lower() in ("c", "a")) else "break")
        for k, f in (("<Escape>", lambda _e: self.destroy()), ("<Left>", lambda _e: self.go(-1)), ("<Right>", lambda _e: self.go(1)),
                     ("<Prior>", lambda _e: self.go(-1)), ("<Next>", lambda _e: self.go(1)),
                     ("<Control-plus>", lambda _e: self.font(1)), ("<Control-equal>", lambda _e: self.font(1)),
                     ("<Control-minus>", lambda _e: self.font(-1)), ("<Up>", lambda _e: self.t.yview_scroll(-3, "units")),
                     ("<Down>", lambda _e: self.t.yview_scroll(3, "units")), ("<space>", lambda _e: self.t.yview_scroll(1, "pages"))):
            self.bind(k, f)
        self.t.bind("<MouseWheel>", lambda e: (self.t.yview_scroll(wheel_steps(e) * 3, "units"), "break")[1])
        self.render()
        self.focus_force()

    def _margins(self):
        w = self.t.winfo_width()
        m = max(20, (w - 900) // 2)
        self.t.configure(padx=m)

    def font(self, d: int):
        self.app.zoom(d)
        configure_rich_tags(self.t, reading=True)
        self.render()

    def go(self, d: int):
        n = self.index + d
        if 0 <= n < len(self.ids):
            self.index = n
            self.render()

    def edit(self):
        iid = self.ids[self.index]
        self.destroy()
        self.app.goto_item(iid)

    def render(self):
        st = self.app.store
        t = self.t
        t.configure(state="normal")
        t.delete("1.0", "end")
        self.imgs.clear()
        for name in list(self.hrefs):
            try:
                t.tag_delete(name)
            except tk.TclError:
                pass
        self.hrefs = {}
        it = st.item(self.ids[self.index]) if self.ids else None
        self.l_pos.configure(text=f"{self.index + 1} / {len(self.ids)}")
        if not it:
            t.insert("end", "Rien à lire.", "rtitle")
            t.configure(state="disabled")
            return
        m = st.meta(it)
        ic = TYPES.get(it["type"], TYPES["file"])["icon"]
        t.insert("end", f"{ic} {it.get('title') or '(sans titre)'}\n", "rtitle")
        bits = [st.subject_label(it["subject_id"]), TYPES.get(it["type"], TYPES["file"])["label"],
                fmt_date(it.get("event_date") or it.get("created") or "", False)]
        if it.get("author"):
            bits.append("par " + it["author"])
        if it.get("tags"):
            bits.append(" ".join("#" + x for x in tag_list(it["tags"])))
        t.insert("end", "   ·   ".join(b for b in bits if b) + "\n", "meta")
        img_rel = it.get("file") if it["type"] == "image" else it.get("thumb")
        if img_rel and os.path.isfile(Paths.abs(img_rel)):
            try:
                from PIL import Image, ImageTk  # type: ignore
                with Image.open(Paths.abs(img_rel)) as im:
                    im = im.convert("RGBA") if im.mode not in ("RGB", "RGBA") else im.copy()
                maxw = min(860, max(300, self.t.winfo_width() - 120))
                im.thumbnail((maxw, 640))
                ph = ImageTk.PhotoImage(im, master=self)
                self.imgs.append(ph)
                t.image_create("end", image=ph, padx=4, pady=6)
                t.insert("end", "\n")
            except Exception:
                pass
        if it.get("url"):
            t.insert("end", "🔗 ")
            t.insert("end", it["url"], "url")
            t.insert("end", "\n")
        if m.get("description"):
            t.insert("end", m["description"] + "\n", "i")
        runs = runs_from_any(it.get("body"))
        if runs:
            if it["type"] == "quote":
                t.insert("end", "\n« ", "cite")
                insert_runs(t, [[r[0], r[1] + ["i"]] for r in runs], self.hrefs)
                t.insert("end", " »\n", "cite")
                src = " — " + ", ".join(x for x in (it.get("author"), it.get("source"), m.get("page")) if x)
                t.insert("end", src + "\n", "meta")
            else:
                if it["type"] not in ("note",):
                    t.insert("end", "\nNotes\n", "sect")
                insert_runs(t, runs, self.hrefs)
                t.insert("end", "\n")
        if it.get("extracted") and it["type"] not in ("link", "video"):
            lab = {"voice": "Transcription", "audio": "Transcription", "image": "Texte reconnu (OCR)"}.get(it["type"], "Texte du document")
            t.insert("end", f"\n{lab}\n", "sect")
            t.insert("end", it["extracted"][:60000] + ("\n…" if len(it["extracted"]) > 60000 else "") + "\n")
        for tg in self.hrefs:
            t.tag_configure(tg)
        refresh_combo(t)
        relink(t, self.terms)
        t.configure(state="disabled")
        t.yview_moveto(0)
        self._margins()

    def _click_url(self, e):
        idx = self.t.index(f"@{e.x},{e.y}")
        r = self.t.tag_prevrange("url", idx + "+1c")
        if r:
            open_url(self.t.get(*r))

    def _click_href(self, e):
        idx = self.t.index(f"@{e.x},{e.y}")
        name = next((tg for tg in self.t.tag_names(idx) if tg.startswith("href_")), "")
        if name in self.hrefs:
            open_url(self.hrefs[name])

    def _click_ref(self, e):
        idx = self.t.index(f"@{e.x},{e.y}")
        r = self.t.tag_prevrange("ref", idx + "+1c")
        if r:
            title = self.t.get(*r).strip("[]")
            it = self.app.store.find_by_title(title)
            if it:
                if it["id"] in self.ids:
                    self.index = self.ids.index(it["id"])
                else:
                    self.ids.insert(self.index + 1, it["id"])
                    self.index += 1
                self.render()
            else:
                self.destroy()
                self.app.follow_ref(title)


# ================================================================ palette « Aller a » (Ctrl+G)
class Palette(tk.Toplevel):
    """Aller a un sujet ou une fiche au clavier ; en mode reference, retourne un titre pour [[...]]."""

    def __init__(self, app, mode: str = "goto", on_pick: Optional[Callable[[Tuple[str, int, str]], None]] = None):
        super().__init__(app)
        self.app = app
        self.mode = mode
        self.on_pick = on_pick
        self.overrideredirect(True)
        self.configure(bg=C["HI"])
        try:
            self.attributes("-topmost", True)
        except tk.TclError:
            pass
        top = app.winfo_toplevel()
        W = min(780, max(420, top.winfo_width() - 60))
        H = min(470, max(260, top.winfo_height() - 80))
        x = top.winfo_rootx() + (top.winfo_width() - W) // 2
        y = top.winfo_rooty() + max(20, top.winfo_height() // 8)
        self.geometry(f"{W}x{H}+{x}+{y}")
        inner = tk.Frame(self, bg=C["PANEL"])
        inner.pack(fill="both", expand=True, padx=2, pady=2)
        hd = tk.Frame(inner, bg=C["PANEL"])
        hd.pack(fill="x", padx=10, pady=(8, 4))
        tk.Label(hd, text="🧭" if mode == "goto" else "[[", bg=C["PANEL"], fg=C["HI"], font=fnt("GTitle")).pack(side="left")
        self.v = tk.StringVar()
        self.entry = tk.Entry(hd, textvariable=self.v, bg=C["ENTRY_BG"], fg=C["ENTRY_FG"], insertbackground=C["HI"],
                              relief="flat", font=fnt("GBig"), highlightthickness=1, highlightbackground=C["LINE"],
                              highlightcolor=C["HI"])
        self.entry.pack(side="left", fill="x", expand=True, padx=8, ipady=3)
        lf = tk.Frame(inner, bg=C["CARD"])
        lf.pack(fill="both", expand=True, padx=10, pady=4)
        self.lb = tk.Listbox(lf, bg=C["CARD"], fg=C["TEXT"], selectbackground=C["SEL"], selectforeground=C["ON_SEL"],
                             font=fnt("GUI"), activestyle="none", relief="flat", highlightthickness=0, bd=0)
        sb = ttk.Scrollbar(lf, orient="vertical", command=self.lb.yview)
        self.lb.configure(yscrollcommand=sb.set)
        self.lb.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        hint = ("Entrée : aller · ↑↓ : choisir · Échap : fermer" if mode == "goto"
                else "Entrée : insérer la référence · si rien ne correspond, le texte tapé est utilisé")
        tk.Label(inner, text=hint, bg=C["PANEL"], fg=C["DIM"], font=fnt("GSM")).pack(anchor="w", padx=10, pady=(0, 6))
        self.items: List[Tuple[str, int, str]] = []
        self.v.trace_add("write", lambda *_a: self.fill())
        for w in (self.entry, self.lb):
            w.bind("<Return>", lambda _e: self.go())
            w.bind("<Escape>", lambda _e: self.close())
        self.entry.bind("<Down>", lambda _e: self.move(1))
        self.entry.bind("<Up>", lambda _e: self.move(-1))
        self.lb.bind("<Double-Button-1>", lambda _e: self.go())
        self.bind("<FocusOut>", lambda _e: self.after(200, lambda: self.close() if self.winfo_exists() and self.focus_get() is None else None))
        self.fill()
        self.after(30, self.entry.focus_force)

    def fill(self):
        st = self.app.store
        q = self.v.get().strip()
        res: List[Tuple[str, int, str]] = []
        nq = norm(q)
        for sid in self.app.subject_order():
            path = st.subject_path(sid)
            if not nq or all(t in norm(path) for t in nq.split()):
                s = st.subject(sid)
                res.append(("s", sid, f"{s['icon'] or '📁'}  {path}"))
        if q:
            for it in st.search(q, limit=60):
                res.append(("i", it["id"], f"{TYPES.get(it['type'], TYPES['file'])['icon']}  {it['title'] or '(sans titre)'}"
                                          f"    — {st.subject_path(it['subject_id'])}"))
        else:
            for it in st.items_where("1=1 ORDER BY COALESCE(opened, updated) DESC", limit=15):
                res.append(("i", it["id"], f"{TYPES.get(it['type'], TYPES['file'])['icon']}  {it['title'] or '(sans titre)'}"
                                          f"    — {st.subject_path(it['subject_id'])}"))
        if not q:
            res = res[:40] + [r for r in res[40:] if r[0] == "i"]
        self.items = res[:120]
        self.lb.delete(0, "end")
        for _k, _i, lab in self.items:
            self.lb.insert("end", " " + lab)
        if self.items:
            self.lb.selection_set(0)

    def move(self, d):
        if not self.items:
            return "break"
        cur = self.lb.curselection()
        i = max(0, min(len(self.items) - 1, (cur[0] if cur else -1) + d))
        self.lb.selection_clear(0, "end")
        self.lb.selection_set(i)
        self.lb.see(i)
        return "break"

    def go(self):
        cur = self.lb.curselection()
        pick: Optional[Tuple[str, int, str]] = self.items[cur[0]] if cur and self.items else None
        if pick is None and self.mode == "ref" and self.v.get().strip():
            pick = ("t", 0, self.v.get().strip())
        self.close()
        if pick and self.on_pick:
            self.app.after(20, lambda: self.on_pick(pick))
        return "break"

    def close(self):
        try:
            self.destroy()
        except tk.TclError:
            pass


# ================================================================ enregistreur de memo vocal
class RecorderDialog(Dialog):
    def __init__(self, app, sid: int):
        super().__init__(app, "Mémo vocal", 620, 430, resizable=False)
        self.app = app
        self.sid = sid
        self.rec = Recorder()
        self.path = ""
        self.state_ = "idle"
        self.job = None
        self.button_bar([("Annuler", self.cancel, ""), ("✔ Enregistrer le mémo", self.save, "accent")])
        self.b_save = self.winfo_children()[-1].winfo_children()[0]
        f = tk.Frame(self, bg=C["BG"])
        f.pack(fill="both", expand=True, padx=14, pady=10)
        mk_label(f, f"🎙 Nouveau mémo dans : {app.store.subject_label(sid)}", "HI", "GUIB", wraplength=560,
                 justify="left").pack(anchor="w")
        df = tk.Frame(f, bg=C["BG"])
        df.pack(fill="x", pady=(10, 4))
        mk_label(df, "Micro :", "FG", "GUI").pack(side="left")
        self.cb = ttk.Combobox(df, state="readonly", font=fnt("GUI"), width=40)
        self.cb.pack(side="left", padx=6, fill="x", expand=True)
        mk_button(df, "↻ Actualiser", self.load_devices, font_name="GSM", tip="Relire la liste des micros").pack(side="left")
        mid = tk.Frame(f, bg=C["BG"])
        mid.pack(fill="x", pady=12)
        self.b_rec = mk_button(mid, "●  Enregistrer", self.toggle, "rec", font_name="GTitle")
        self.b_rec.pack(side="left", padx=(0, 16), ipady=6)
        self.l_time = mk_label(mid, "0:00", "HI", "GBig")
        self.l_time.pack(side="left")
        self.vu = tk.Canvas(f, height=18, bg=C["ENTRY_BG"], highlightthickness=1, highlightbackground=C["LINE"])
        self.vu.pack(fill="x", pady=4)
        self.v_title = tk.StringVar(value=f"Mémo du {fmt_date(now_iso())}")
        tf = tk.Frame(f, bg=C["BG"])
        tf.pack(fill="x", pady=(8, 2))
        mk_label(tf, "Titre :", "FG", "GUI").pack(side="left")
        mk_entry(tf, self.v_title, 40).pack(side="left", fill="x", expand=True, padx=6, ipady=2)
        self.v_tr = tk.BooleanVar(value=whisper_available() and bool(app.store.get("auto_transcribe", True)))
        self.chk = mk_check(f, "📝 Transcrire en texte ensuite (faster-whisper, local)", self.v_tr)
        self.chk.pack(anchor="w", pady=(6, 0))
        if not whisper_available():
            self.chk.configure(state="disabled")
            mk_label(f, "Transcription : module faster-whisper non installé (optionnel, menu Outils). "
                        "Le son est quand même gardé et tu peux écrire un résumé dans les notes.",
                     "DIM", "GSM", wraplength=570, justify="left").pack(anchor="w")
        self.l_msg = mk_label(f, "", "WARN", "GSM", wraplength=570, justify="left")
        self.l_msg.pack(anchor="w", pady=(6, 0))
        self.bind("<space>", lambda _e: (self.toggle(), "break")[1])
        self.load_devices()
        self.show(self.b_rec)

    def load_devices(self):
        devs, dflt, err = Recorder.devices()
        self.devs = devs
        self.cb.configure(values=[lab for _i, lab in devs])
        if devs:
            idx = next((k for k, (i, _l) in enumerate(devs) if i == dflt), 0)
            self.cb.current(idx)
            self.b_rec.configure(state="normal")
            self.l_msg.configure(text="Espace ou ● pour commencer, puis ■ pour arrêter.", fg=C["DIM"])
        else:
            self.cb.set("(aucun micro)")
            self.b_rec.configure(state="disabled")
            self.l_msg.configure(text="⚠ " + (err or "Aucun micro détecté."), fg=C["WARN"])
        self._update_save()

    def _update_save(self):
        try:
            self.b_save.configure(state="normal" if self.state_ == "done" else "disabled")
        except Exception:
            pass

    def toggle(self):
        if self.state_ == "rec":
            self.stop()
        elif self.devs:
            self.start()

    def start(self):
        if self.path and os.path.isfile(self.path):
            try:
                os.remove(self.path)
            except OSError:
                pass
        dev = self.devs[self.cb.current()][0] if self.cb.current() >= 0 else None
        d = os.path.join(Paths.data, "_temp")
        os.makedirs(d, exist_ok=True)
        self.path = os.path.join(d, f"memo_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.flac")
        err = self.rec.start(self.path, dev)
        if err:
            self.l_msg.configure(text="⚠ " + err, fg=C["ERR"])
            return
        self.state_ = "rec"
        self.b_rec.configure(text="■  Arrêter")
        self.l_msg.configure(text="Enregistrement… (Espace pour arrêter)", fg=C["OK"])
        self._update_save()
        self._tick()

    def _tick(self):
        if self.state_ != "rec":
            return
        self.l_time.configure(text=fmt_dur(self.rec.duration()))
        w = self.vu.winfo_width()
        lv = min(1.0, self.rec.level * 1.6)
        self.vu.delete("all")
        col = C["OK"] if lv < 0.7 else (C["WARN"] if lv < 0.92 else C["ERR"])
        self.vu.create_rectangle(0, 0, int(w * lv), 20, fill=col, width=0)
        self.job = self.after(80, self._tick)

    def stop(self):
        p, d = self.rec.stop()
        self.state_ = "done" if d > 0.3 else "idle"
        self.b_rec.configure(text="●  Recommencer")
        self.l_time.configure(text=fmt_dur(d))
        self.vu.delete("all")
        self.l_msg.configure(text=(f"Mémo de {fmt_dur(d)} prêt : « Enregistrer le mémo » pour le garder." if d > 0.3
                                   else "Trop court, recommence."), fg=C["OK"] if d > 0.3 else C["WARN"])
        self._update_save()

    def save(self):
        if self.state_ == "rec":
            self.stop()
        if self.state_ != "done" or not os.path.isfile(self.path):
            return
        self.result = {"path": self.path, "title": self.v_title.get().strip() or "Mémo vocal",
                       "duration": self.rec.duration(), "transcribe": bool(self.v_tr.get())}
        self.destroy()

    def cancel(self):
        if self.job:
            try:
                self.after_cancel(self.job)
            except Exception:
                pass
        if self.state_ == "rec":
            self.rec.cancel()
        elif self.path and os.path.isfile(self.path):
            try:
                os.remove(self.path)
            except OSError:
                pass
        self.result = None
        self.destroy()


# ================================================================ application
# ======================================================================== 1.5 : cartes, carte des sujets, liens permanents
GX_ARCHIVES_SQL = """
CREATE TABLE IF NOT EXISTS archives(
  url TEXT PRIMARY KEY,
  item_id INTEGER,
  status TEXT DEFAULT '',
  root TEXT DEFAULT '',
  folder TEXT DEFAULT '',
  info TEXT DEFAULT '{}',
  created TEXT, updated TEXT
);
"""
GX_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
GX_MEDIA_EXT = (".mp4", ".webm", ".mkv", ".mov", ".m4v", ".mp3", ".m4a", ".opus")


def gx_mix(c1: str, c2: str, t: float) -> str:
    """melange de deux couleurs #RRGGBB (t=0 -> c1, t=1 -> c2)."""
    try:
        a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
        b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
        return "#%02X%02X%02X" % tuple(int(x + (y - x) * t) for x, y in zip(a, b))
    except Exception:
        return c2


def gx_http(url: str, timeout: float = 12, limit: int = 3_000_000, headers: Optional[Dict[str, str]] = None):
    h = {"User-Agent": GX_UA, "Accept-Language": "fr-CA,fr;q=0.9,en;q=0.8"}
    h.update(headers or {})
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(limit), r.headers.get("Content-Type", ""), r.geturl()


def gx_http_json(url: str, timeout: float = 12) -> Dict[str, Any]:
    raw, _c, _u = gx_http(url, timeout, headers={"Accept": "application/json"})
    return json.loads(raw.decode("utf-8", "replace"))


def gx_og(raw_html: str, *names: str) -> str:
    for n in names:
        mo = re.search(r'(?is)<meta[^>]+(?:property|name)=["\']' + re.escape(n) + r'["\'][^>]*content=["\']([^"\']*)', raw_html) or \
            re.search(r'(?is)<meta[^>]+content=["\']([^"\']*)["\'][^>]*(?:property|name)=["\']' + re.escape(n) + r'["\']', raw_html)
        if mo and mo.group(1).strip():
            return html.unescape(re.sub(r"\s+", " ", mo.group(1))).strip()
    return ""


def gx_preview_dir() -> str:
    d = os.path.join(Paths.data, "apercus")
    os.makedirs(d, exist_ok=True)
    return d


def gx_key(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


def gx_preview_cached(url: str) -> Optional[Dict[str, Any]]:
    p = os.path.join(gx_preview_dir(), gx_key(url) + ".json")
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def gx_preview_image(url: str) -> str:
    """chemin de la miniature d'apercu en cache (ou '')."""
    d = gx_preview_cached(url)
    if d and d.get("image"):
        p = os.path.join(gx_preview_dir(), d["image"])
        if os.path.isfile(p):
            return p
    return ""


def gx_fetch_preview(url: str) -> Dict[str, Any]:
    """apercu d'un lien (titre, site, description, miniature : OpenGraph / oEmbed) ; garde une copie dans apercus\\
    pour que ca marche hors ligne. Meme logique que le Journal de bord 1.4."""
    key = gx_key(url)
    d = gx_preview_dir()
    jp = os.path.join(d, key + ".json")
    old = gx_preview_cached(url)
    if old and (old.get("ok") or time.time() - float(old.get("t") or 0) < 3600):
        return old
    host = (urllib.parse.urlparse(url).hostname or "").lower().replace("www.", "")
    res: Dict[str, Any] = {"url": url, "title": "", "site": host, "desc": "", "image": "", "author": "", "ok": False,
                           "t": time.time()}
    img_url = ""
    q = urllib.parse.quote(url, safe="")
    try:
        if host in ("youtube.com", "m.youtube.com", "youtu.be", "music.youtube.com"):
            o = gx_http_json("https://www.youtube.com/oembed?format=json&url=" + q)
            res.update(title=o.get("title", ""), author=o.get("author_name", ""), site="YouTube", video=True)
            img_url = o.get("thumbnail_url", "")
        elif host.endswith("vimeo.com"):
            o = gx_http_json("https://vimeo.com/api/oembed.json?url=" + q)
            res.update(title=o.get("title", ""), author=o.get("author_name", ""), site="Vimeo",
                       desc=str(o.get("description") or "")[:300], video=True)
            img_url = o.get("thumbnail_url", "")
        elif host.endswith("tiktok.com"):
            o = gx_http_json("https://www.tiktok.com/oembed?url=" + q)
            res.update(title=o.get("title", ""), author=o.get("author_name", ""), site="TikTok", video=True)
            img_url = o.get("thumbnail_url", "")
        elif host in ("x.com", "twitter.com", "mobile.twitter.com", "fxtwitter.com", "vxtwitter.com") and "/status/" in url:
            mo = re.search(r"/([A-Za-z0-9_]{1,15})/status(?:es)?/(\d+)", url)
            o = gx_http_json(f"https://api.fxtwitter.com/{mo.group(1)}/status/{mo.group(2)}")["tweet"]
            a = o.get("author") or {}
            res.update(title=(a.get("name") or "") + (f" (@{a.get('screen_name')})" if a.get("screen_name") else ""),
                       author=a.get("name") or "", site="X", desc=str(o.get("text") or "")[:400])
            med = o.get("media") or {}
            if med.get("photos"):
                img_url = med["photos"][0].get("url", "")
            elif med.get("videos"):
                img_url = med["videos"][0].get("thumbnail_url", "")
                res["video"] = True
            else:
                img_url = a.get("avatar_url", "")
        if not res["title"]:
            raw, ctype, final = gx_http(url, 12, 1_500_000)
            if "html" in ctype.lower() or not ctype:
                t = raw.decode("utf-8", "replace")
                res["title"] = gx_og(t, "og:title", "twitter:title") or html.unescape(
                    re.sub(r"\s+", " ", (re.search(r"(?is)<title[^>]*>(.*?)</title>", t) or [None, ""])[1])).strip()
                res["desc"] = res["desc"] or gx_og(t, "og:description", "twitter:description", "description")[:400]
                res["site"] = gx_og(t, "og:site_name") or res["site"]
                img_url = img_url or gx_og(t, "og:image", "og:image:url", "twitter:image", "twitter:image:src")
                if img_url:
                    img_url = urllib.parse.urljoin(final, img_url)
            else:
                res["title"] = os.path.basename(urllib.parse.urlparse(url).path) or url
                res["desc"] = ctype
        res["title"] = str(res["title"])[:200]
        res["ok"] = bool(res["title"] or res["desc"])
        if img_url:
            try:
                raw, _c, _u = gx_http(img_url, 15, 8_000_000)
                from PIL import Image  # type: ignore
                im = Image.open(io.BytesIO(raw)).convert("RGB")
                im.thumbnail((480, 300))
                im.save(os.path.join(d, key + ".jpg"), "JPEG", quality=85)
                res["image"] = key + ".jpg"
            except Exception:
                pass
    except Exception as ex:
        res["erreur"] = str(ex)[:200]
    try:
        tmp = jp + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False)
        os.replace(tmp, jp)
    except OSError:
        pass
    return res


GX_ARCH_SCRIPT = r"""
import sys, os, json
sys.path.insert(0, sys.argv[1]); url = sys.argv[2]
import archiveur5 as a
a.setup_logging()
def hook(d):
    try:
        if d.get("status") == "downloading":
            t = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            if t:
                print("@@P@@%.1f" % (100.0 * (d.get("downloaded_bytes") or 0) / t), flush=True)
        elif d.get("status") == "finished":
            print("@@P@@100", flush=True)
    except Exception:
        pass
cfg = a.load_cfg()
root = cfg.get("archive_root") or a.DEFAULT_ROOT
os.makedirs(root, exist_ok=True)
if not a._cli_ensure_ytdlp():
    print("@@E@@yt-dlp introuvable", flush=True); sys.exit(2)
entries = a.sync_index_with_disk(root)
d = a.find_duplicates(entries, url)
if d:
    folder, dup = d[0].get("folder"), True
else:
    info = a.archive_url(url, root, a._cli_log, progress_hook=hook, quality=cfg.get("quality") or "best",
                         subtitles=bool(cfg.get("subtitles", True)), storyboard=True, tags=["Grimoire"],
                         notes="Depuis le Grimoire", web_capture=bool(cfg.get("web_capture", True)),
                         use_fx=bool(cfg.get("x_fxtwitter", True)), auto_convert=bool(cfg.get("auto_convert", True)))
    folder, dup = a.register_archive(root, info)["folder"], False
try:
    a.set_collections(root, [folder], add="Grimoire")
except Exception:
    pass
print("@@R@@" + json.dumps({"root": root, "folder": folder, "dup": dup}), flush=True)
"""


def gx_archiveur_dir() -> str:
    for d in (padawan_dir(), BASE):
        if d and os.path.isfile(os.path.join(d, "archiveur5.py")):
            return d
    return ""


def gx_console_python() -> str:
    exe = sys.executable or "python"
    if os.path.basename(exe).lower() == "pythonw.exe":
        c = os.path.join(os.path.dirname(exe), "python.exe")
        if os.path.isfile(c):
            return c
    return exe


def gx_archive_via_archiveur(url: str, on_event: Callable[[str, Any], None] = lambda k, v: None,
                             timeout: float = 3600) -> Dict[str, Any]:
    here = gx_archiveur_dir()
    if not here:
        raise RuntimeError("archiveur5.py introuvable")
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    kw: Dict[str, Any] = {}
    if IS_WIN:
        kw["creationflags"] = CREATE_NO_WINDOW
    p = subprocess.Popen([gx_console_python(), "-c", GX_ARCH_SCRIPT, here, url], cwd=here, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, text=True, encoding="utf-8",
                         errors="replace", env=env, **kw)
    res, tail, t0 = None, [], time.time()
    assert p.stdout is not None
    for line in p.stdout:
        line = line.rstrip()
        if line.startswith("@@P@@"):
            try:
                on_event("pct", float(line[5:]))
            except ValueError:
                pass
        elif line.startswith("@@R@@"):
            res = json.loads(line[5:])
        elif line.startswith("@@E@@"):
            tail.append(line[5:])
        elif line.strip():
            tail = (tail + [line])[-8:]
            on_event("log", line)
        if time.time() - t0 > timeout:
            p.kill()
            break
    p.wait()
    if not res:
        fails = [x for x in tail if "FAIL" in x or "rror" in x]
        raise RuntimeError((fails or tail or ["l'Archiveur n'a rien gardé"])[-1][-240:])
    return res


def gx_folder_info(folder: str) -> Dict[str, Any]:
    """fichiers utiles d'un dossier d'archive (video principale, page, capture...)."""
    files = os.listdir(folder) if os.path.isdir(folder) else []
    vids = sorted([f for f in files if f.lower().endswith(GX_MEDIA_EXT)], key=lambda f: -os.path.getsize(os.path.join(folder, f)))
    imgs = [f for f in files if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp")) and not f.startswith("sb_")]
    imgs.sort(key=lambda f: (0 if ("thumb" in f.lower() or "capture" in f.lower()) else 1, f))
    info: Dict[str, Any] = {}
    try:
        with open(os.path.join(folder, "info.json"), "r", encoding="utf-8") as f:
            info = json.load(f) or {}
    except (OSError, ValueError):
        info = {}
    return {"main": vids[0] if vids else ("lecture.html" if "lecture.html" in files else
                                          ("page.html" if "page.html" in files else ("index.html" if "index.html" in files else ""))),
            "video": bool(vids and not vids[0].lower().endswith((".mp3", ".m4a", ".opus"))),
            "index": "index.html" if "index.html" in files else "",
            "capture": imgs[0] if imgs else "",
            "title": str(info.get("title") or "")[:300],
            "texte": str(info.get("description") or info.get("text") or "")[:20000],
            "nfiles": len(files)}


def gx_archive_get(store: "Store", url: str) -> Optional[Dict[str, Any]]:
    try:
        r = store.q("SELECT * FROM archives WHERE url=?", (url,))
    except sqlite3.Error:
        return None
    if not r:
        return None
    d = dict(r[0])
    try:
        d["info"] = json.loads(d.get("info") or "{}")
    except ValueError:
        d["info"] = {}
    return d


def gx_archive_set(store: "Store", url: str, item_id: Optional[int], status: str, root: str = "", folder: str = "",
                   info: Optional[Dict[str, Any]] = None) -> None:
    now = now_iso()
    old = gx_archive_get(store, url)
    if old:
        store.x("UPDATE archives SET item_id=COALESCE(?,item_id), status=?, root=?, folder=?, info=?, updated=? WHERE url=?",
                (item_id, status, root or old.get("root") or "", folder or old.get("folder") or "",
                 json.dumps(info if info is not None else old.get("info") or {}, ensure_ascii=False), now, url))
    else:
        store.x("INSERT INTO archives(url,item_id,status,root,folder,info,created,updated) VALUES(?,?,?,?,?,?,?,?)",
                (url, item_id, status, root, folder, json.dumps(info or {}, ensure_ascii=False), now, now))


def gx_archive_folder(a: Optional[Dict[str, Any]]) -> str:
    if not a or a.get("status") != "permanent":
        return ""
    p = os.path.join(a.get("root") or "", a.get("folder") or "")
    return p if a.get("folder") and os.path.isdir(p) else ""


def gx_cheer(pct: Optional[float], log: str = "") -> str:
    if pct is None:
        if re.search(r"(?i)ffmpeg|convert|encod|remux|storyboard", log or ""):
            return "🎞 L'Archiveur peaufine la copie… presque fini !"
        return "🛰 L'Archiveur met ce lien à l'abri… tu peux continuer à lire."
    p = int(pct)
    if p < 5:
        return "🚀 C'est parti, on va chercher ça…"
    if p < 40:
        return f"📥 {p} % — ça avance bien !"
    if p < 80:
        return f"✨ {p} % — plus de la moitié !"
    if p < 100:
        return f"🏁 {p} % — dernière ligne droite !"
    return "🎞 Téléchargé ! L'Archiveur range la copie…"


def gx_item_urls(it: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    for u in [it.get("url") or ""] + find_urls(it.get("body_text") or "") + find_urls(it.get("extracted") or "")[:5]:
        u = (u or "").strip().rstrip(".,;:)»\"'")
        if u.startswith(("http://", "https://")) and u not in out:
            out.append(u)
    return out[:12]


class MindMap(tk.Toplevel):
    """« Carte des sujets » : graphe anime et interactif (Canvas Tk pur) : sujets, sous-sujets, fiches, liens."""

    def __init__(self, app: "GrimoireApp"):
        super().__init__(app)
        self.app = app
        st = app.store
        self.title("🗺 Carte des sujets — Grimoire")
        self.configure(bg=C["BG"])
        try:
            self.state("zoomed")
        except tk.TclError:
            self.geometry(f"{self.winfo_screenwidth()}x{self.winfo_screenheight() - 60}+0+0")
        self.anim = bool(app.store.get("animations", True))
        self.show_items = tk.BooleanVar(value=bool(st.get("map_items", True)))
        self.show_links = tk.BooleanVar(value=bool(st.get("map_links", False)))
        bar = tk.Frame(self, bg=C["PANEL"])
        bar.pack(fill="x")
        tk.Label(bar, text="🗺 CARTE DES SUJETS", bg=C["PANEL"], fg=C["HI"], font=fnt("GTitle")).pack(side="left", padx=10, pady=6)
        for txt, cmd, tip in (("➕ Zoom", lambda: self.zoom_at(1.2), "Agrandir (molette vers le haut, ou +)"),
                              ("➖ Zoom", lambda: self.zoom_at(1 / 1.2), "Réduire (molette vers le bas, ou -)"),
                              ("🎯 Recentrer", self.fit, "Tout voir d'un coup d'œil (touche 0)"),
                              ("✨ Réorganiser", self.shake, "Relancer l'animation de placement (touche R)")):
            mk_button(bar, txt, cmd, tip=tip).pack(side="left", padx=3, pady=6)
        c1 = mk_check(bar, "Montrer les fiches", self.show_items, bg=C["PANEL"], cmd=self.rebuild)
        c1.pack(side="left", padx=8)
        Tooltip(c1, "Petits points autour de chaque sujet : un point = une fiche")
        c2 = mk_check(bar, "Liens entre fiches", self.show_links, bg=C["PANEL"], cmd=lambda: (self.app.store.set("map_links", bool(self.show_links.get())), self.redraw()))
        c2.pack(side="left", padx=4)
        Tooltip(c2, "Traits pointillés : fiches qui se citent ([[…]]) ou partagent une étiquette")
        mk_button(bar, "✖ Fermer", self.destroy, tip="Fermer la carte (Échap)").pack(side="right", padx=6, pady=6)
        self.l_info = tk.Label(self, text="Molette : zoom · glisser : déplacer · clic sur un sujet : l'ouvrir · double-clic sur une "
                                          "fiche : l'ouvrir · survol : nom et nombre de fiches", bg=C["BG"], fg=C["DIM"],
                               font=fnt("GSM"), anchor="w")
        self.l_info.pack(fill="x", padx=10)
        self.cv = tk.Canvas(self, bg=C["CARD"], highlightthickness=0, bd=0, takefocus=1)
        self.cv.pack(fill="both", expand=True)
        self.scale, self.ox, self.oy = 1.0, 0.0, 0.0
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.edges: List[Tuple[str, str, str]] = []
        self.hover: Optional[str] = None
        self.drag: Optional[Tuple[int, int, float, float, bool]] = None
        self.ticks = 0
        self.job = None
        cv = self.cv
        cv.bind("<MouseWheel>", lambda e: self.zoom_at(1.15 if wheel_steps(e) < 0 else 1 / 1.15, e.x, e.y))
        cv.bind("<Button-4>", lambda e: self.zoom_at(1.15, e.x, e.y))
        cv.bind("<Button-5>", lambda e: self.zoom_at(1 / 1.15, e.x, e.y))
        cv.bind("<ButtonPress-1>", self._press)
        cv.bind("<B1-Motion>", self._motion_drag)
        cv.bind("<ButtonRelease-1>", self._release)
        cv.bind("<Double-Button-1>", self._double)
        cv.bind("<Motion>", self._motion)
        cv.bind("<Button-3>", self._menu)
        cv.bind("<Configure>", lambda _e: self.redraw())
        self.bind("<Escape>", lambda _e: self.destroy())
        for k, f in (("plus", 1.2), ("equal", 1.2), ("KP_Add", 1.2), ("minus", 1 / 1.2), ("KP_Subtract", 1 / 1.2)):
            self.bind(f"<{k}>", lambda _e, ff=f: self.zoom_at(ff))
        self.bind("0", lambda _e: self.fit())
        self.bind("r", lambda _e: self.shake())
        self.bind("R", lambda _e: self.shake())
        self.rebuild(first=True)
        self.after(50, lambda: (cv.focus_set(), self.fit(), self.start()))

    # ------------------------------------------------------------ modele
    def rebuild(self, first: bool = False):
        st = self.app.store
        st.set("map_items", bool(self.show_items.get()))
        subs = st.subjects()
        tc = st.total_counts()
        cnt = st.counts()
        old = self.nodes
        self.nodes, self.edges = {}, []
        roots = [s for s in st.children(None)]
        n = max(1, len(roots))
        R0 = 340.0
        for k, s in enumerate(roots):
            a = 2 * math.pi * k / n
            self._add_subject(s, math.cos(a) * R0, math.sin(a) * R0, subs, tc, 0, old)
        for sid, s in subs.items():
            if s.get("parent_id") and f"s{s['parent_id']}" in self.nodes and f"s{sid}" in self.nodes:
                self.edges.append((f"s{s['parent_id']}", f"s{sid}", "tree"))
        if self.show_items.get():
            items = st.items_where("1=1", limit=3000)
            by_title: Dict[str, str] = {}
            tags: Dict[str, List[str]] = {}
            for r in items:
                p = self.nodes.get(f"s{r['subject_id']}")
                if not p:
                    continue
                key = f"i{r['id']}"
                ang = random.random() * 2 * math.pi
                o = old.get(key)
                self.nodes[key] = {"kind": "item", "id": r["id"], "label": r.get("title") or "(sans titre)",
                                   "x": o["x"] if o else p["x"] + math.cos(ang) * 60, "y": o["y"] if o else p["y"] + math.sin(ang) * 60,
                                   "vx": 0.0, "vy": 0.0, "r": 4.5, "color": p["color"], "type": r["type"], "fav": r.get("fav")}
                self.edges.append((p["key"], key, "item"))
                by_title[norm(r.get("title") or "")] = key
                for tg in tag_list(r.get("tags") or ""):
                    tags.setdefault(tg.lower(), []).append(key)
            seen = set()
            for r in items:
                a = f"i{r['id']}"
                if a not in self.nodes:
                    continue
                for ref in re.findall(r"\[\[([^\]]+)\]\]", r.get("body_text") or ""):
                    b = by_title.get(norm(ref))
                    if b and b != a and (a, b) not in seen:
                        seen.add((a, b))
                        self.edges.append((a, b, "ref"))
            for tg, keys in tags.items():
                if 2 <= len(keys) <= 12:
                    for i in range(len(keys) - 1):
                        pair = (keys[i], keys[i + 1])
                        if pair not in seen:
                            seen.add(pair)
                            self.edges.append((keys[i], keys[i + 1], "tag"))
        _ = cnt
        if not first:
            self.start()

    def _add_subject(self, s, x, y, subs, tc, depth, old):
        key = f"s{s['id']}"
        o = old.get(key)
        n = tc.get(s["id"], 0)
        r = (26 if depth == 0 else 16) + 5 * math.sqrt(n)
        col = s.get("color") or (self.nodes.get(f"s{s.get('parent_id')}", {}).get("color")) or C["HI"]
        self.nodes[key] = {"kind": "subject", "id": s["id"], "key": key, "label": s["name"], "icon": s.get("icon") or "📁",
                           "count": n, "x": o["x"] if o else x, "y": o["y"] if o else y, "vx": 0.0, "vy": 0.0,
                           "r": min(r, 70), "color": col, "depth": depth}
        kids = self.app.store.children(s["id"])
        for k, c in enumerate(kids):
            a = math.atan2(y, x) + (k - (len(kids) - 1) / 2) * 0.55
            self._add_subject(c, x + math.cos(a) * 170, y + math.sin(a) * 170, subs, tc, depth + 1, old)

    # ------------------------------------------------------------ animation (forces douces)
    def start(self):
        self.ticks = 160 if self.anim else 0
        if not self.anim:
            for _ in range(140):
                self.step(fast=True)
            self.redraw()
            return
        if self.job is None:
            self.job = self.after(16, self._tick)

    def shake(self):
        for n in self.nodes.values():
            n["vx"] += random.uniform(-8, 8)
            n["vy"] += random.uniform(-8, 8)
        self.start()

    def _tick(self):
        self.job = None
        if not self.winfo_exists():
            return
        self.step()
        self.redraw()
        self.ticks -= 1
        if self.ticks > 0:
            self.job = self.after(20, self._tick)

    def step(self, fast: bool = False):
        ns = list(self.nodes.values())
        subj = [n for n in ns if n["kind"] == "subject"]
        for i, a in enumerate(subj):           # repulsion entre sujets
            for b in subj[i + 1:]:
                dx, dy = a["x"] - b["x"], a["y"] - b["y"]
                d2 = dx * dx + dy * dy + 0.01
                d = math.sqrt(d2)
                mind = a["r"] + b["r"] + 60
                f = 9000.0 / d2 + (max(0.0, mind - d) * 0.5)
                fx, fy = dx / d * f, dy / d * f
                a["vx"] += fx; a["vy"] += fy
                b["vx"] -= fx; b["vy"] -= fy
        for a_k, b_k, kind in self.edges:       # ressorts
            a, b = self.nodes.get(a_k), self.nodes.get(b_k)
            if not a or not b:
                continue
            dx, dy = b["x"] - a["x"], b["y"] - a["y"]
            d = math.sqrt(dx * dx + dy * dy) + 0.01
            rest = {"tree": a["r"] + b["r"] + 90, "item": a["r"] + 22 + (abs(hash(b_k)) % 30), "ref": 120, "tag": 140}[kind]
            k = {"tree": 0.02, "item": 0.08, "ref": 0.004, "tag": 0.002}[kind]
            f = (d - rest) * k
            fx, fy = dx / d * f, dy / d * f
            if a["kind"] == "item" or kind != "item":
                a["vx"] += fx; a["vy"] += fy
            b["vx"] -= fx; b["vy"] -= fy
        for n in ns:                              # gravite vers le centre + amortissement
            g = 0.004 if n["kind"] == "subject" else 0.0
            n["vx"] = (n["vx"] - n["x"] * g) * 0.78
            n["vy"] = (n["vy"] - n["y"] * g) * 0.78
            if self.drag and self.drag[4] and self.drag_key == n.get("key", f"i{n['id']}"):
                continue
            n["x"] += max(-30, min(30, n["vx"]))
            n["y"] += max(-30, min(30, n["vy"]))

    # ------------------------------------------------------------ dessin
    def sx(self, x: float) -> float:
        return self.cv.winfo_width() / 2 + (x + self.ox) * self.scale

    def sy(self, y: float) -> float:
        return self.cv.winfo_height() / 2 + (y + self.oy) * self.scale

    def redraw(self):
        cv = self.cv
        if not cv.winfo_exists():
            return
        cv.delete("all")
        s = self.scale
        links = self.show_links.get()
        for a_k, b_k, kind in self.edges:
            if kind in ("ref", "tag") and not links:
                continue
            a, b = self.nodes.get(a_k), self.nodes.get(b_k)
            if not a or not b:
                continue
            hot = self.hover in (a_k, b_k)
            if kind == "tree":
                cv.create_line(self.sx(a["x"]), self.sy(a["y"]), self.sx(b["x"]), self.sy(b["y"]), fill=gx_mix(C["CARD"], b["color"], 0.8),
                               width=max(1, 3 * s))
            elif kind == "item":
                cv.create_line(self.sx(a["x"]), self.sy(a["y"]), self.sx(b["x"]), self.sy(b["y"]),
                               fill=gx_mix(C["CARD"], a["color"], 0.6 if hot else 0.28), width=1)
            else:
                cv.create_line(self.sx(a["x"]), self.sy(a["y"]), self.sx(b["x"]), self.sy(b["y"]),
                               fill=C["HI"] if hot else gx_mix(C["CARD"], C["FG"] if kind == "ref" else C["DIM"], 0.55),
                               dash=(4, 3), width=2 if hot else 1)
        for key, n in self.nodes.items():
            if n["kind"] != "item":
                continue
            r = max(2.0, n["r"] * min(1.6, s))
            x, y = self.sx(n["x"]), self.sy(n["y"])
            hot = key == self.hover
            cv.create_oval(x - r, y - r, x + r, y + r, fill=C["HI"] if (hot or n.get("fav")) else gx_mix(C["CARD"], n["color"], 0.75),
                           outline=C["HI"] if hot else "", tags=("node", key))
        subs = sorted([kv for kv in self.nodes.items() if kv[1]["kind"] == "subject"], key=lambda kv: -kv[1]["depth"])
        for key, n in subs:
            r = n["r"] * s
            x, y = self.sx(n["x"]), self.sy(n["y"])
            hot = key == self.hover
            if hot:
                cv.create_oval(x - r - 6, y - r - 6, x + r + 6, y + r + 6, outline=n["color"], width=2, tags=("node", key))
            cv.create_oval(x - r, y - r, x + r, y + r, fill=gx_mix(C["CARD"], n["color"], 0.30 if not hot else 0.45),
                           outline=n["color"], width=3 if n["depth"] == 0 else 2, tags=("node", key))
            if r > 9:
                cv.create_text(x, y - (r * 0.12), text=n["icon"], font=("Segoe UI Emoji", max(8, int(min(28, r * 0.55)))),
                               fill=C["TEXT"], tags=("node", key))
            if s > 0.35 or n["depth"] == 0:
                fz = max(7, int((11 if n["depth"] == 0 else 9) * min(1.5, max(0.8, s))))
                cv.create_text(x, y + r + 4, text=f"{n['label']}  ({n['count']})", anchor="n", fill=C["TEXT"] if not hot else C["HI"],
                               font=(fnt("GUIB").actual("family") if hasattr(fnt("GUIB"), "actual") else "Segoe UI", fz, "bold"),
                               tags=("node", key))
        if self.hover and self.hover in self.nodes:
            n = self.nodes[self.hover]
            txt = (f"{n['icon']} {self.app.store.subject_path(n['id'])} — {n['count']} fiche(s) · clic : ouvrir ce sujet"
                   if n["kind"] == "subject" else f"{TYPES.get(n['type'], TYPES['file'])['icon']} {n['label']} · double-clic : ouvrir la fiche")
            x, y = self.sx(n["x"]), self.sy(n["y"]) - n["r"] * s - 16
            t = cv.create_text(x, y, text=txt, anchor="s", fill=C["ON_HI"], font=fnt("GUI"))
            bb = cv.bbox(t)
            if bb:
                rr = cv.create_rectangle(bb[0] - 6, bb[1] - 3, bb[2] + 6, bb[3] + 3, fill=C["HI"], outline="")
                cv.tag_lower(rr, t)

    def fit(self):
        if not self.nodes:
            return
        xs = [n["x"] for n in self.nodes.values()]
        ys = [n["y"] for n in self.nodes.values()]
        w, h = max(200, self.cv.winfo_width()), max(200, self.cv.winfo_height())
        bw, bh = max(xs) - min(xs) + 200, max(ys) - min(ys) + 200
        self.scale = max(0.15, min(2.0, min(w / bw, h / bh)))
        self.ox, self.oy = -(max(xs) + min(xs)) / 2, -(max(ys) + min(ys)) / 2
        self.redraw()

    def zoom_at(self, f: float, x: Optional[int] = None, y: Optional[int] = None):
        w, h = self.cv.winfo_width(), self.cv.winfo_height()
        x = w / 2 if x is None else x
        y = h / 2 if y is None else y
        wx = (x - w / 2) / self.scale - self.ox
        wy = (y - h / 2) / self.scale - self.oy
        self.scale = max(0.1, min(5.0, self.scale * f))
        self.ox = (x - w / 2) / self.scale - wx
        self.oy = (y - h / 2) / self.scale - wy
        self.redraw()

    # ------------------------------------------------------------ souris
    def node_at(self, x: int, y: int) -> Optional[str]:
        best, bd = None, 1e9
        for key, n in self.nodes.items():
            d = math.hypot(self.sx(n["x"]) - x, self.sy(n["y"]) - y)
            r = max(6, n["r"] * self.scale) + 3
            if d <= r and (n["kind"] == "item" or d < bd):
                if n["kind"] == "item" or best is None or self.nodes[best]["kind"] != "item":
                    best, bd = key, d
        return best

    def _motion(self, e):
        k = self.node_at(e.x, e.y)
        if k != self.hover:
            self.hover = k
            self.cv.configure(cursor="hand2" if k else "fleur")
            self.redraw()

    def _press(self, e):
        self.cv.focus_set()
        k = self.node_at(e.x, e.y)
        self.drag_key = k
        self.drag = (e.x, e.y, self.ox, self.oy, bool(k))
        self.moved = False

    def _motion_drag(self, e):
        if not self.drag:
            return
        x0, y0, ox, oy, on_node = self.drag
        if abs(e.x - x0) + abs(e.y - y0) > 4:
            self.moved = True
        if on_node and self.drag_key in self.nodes:
            n = self.nodes[self.drag_key]
            n["x"] = (e.x - self.cv.winfo_width() / 2) / self.scale - self.ox
            n["y"] = (e.y - self.cv.winfo_height() / 2) / self.scale - self.oy
            n["vx"] = n["vy"] = 0.0
            if self.anim and self.job is None:
                self.ticks = 40
                self.job = self.after(16, self._tick)
        else:
            self.ox = ox + (e.x - x0) / self.scale
            self.oy = oy + (e.y - y0) / self.scale
        self.redraw()

    def _release(self, e):
        k = self.drag_key if self.drag else None
        moved = getattr(self, "moved", False)
        self.drag = None
        if k and not moved and self.nodes.get(k, {}).get("kind") == "subject":
            self.open_node(k)

    def _double(self, e):
        k = self.node_at(e.x, e.y)
        if k:
            self.open_node(k)

    def open_node(self, k: str):
        n = self.nodes.get(k)
        if not n:
            return
        if n["kind"] == "subject":
            self.app.open_view(f"s:{n['id']}")
            self.app.reveal_subject(n["id"])
            self.app.set_status(f"🗺 Sujet ouvert : {n['label']} ({n['count']} fiche(s)).", "OK")
        else:
            self.app.goto_item(n["id"])
        self.app.lift()

    def _menu(self, e):
        k = self.node_at(e.x, e.y)
        m = new_menu(self)
        if k:
            n = self.nodes[k]
            m.add_command(label=("📂 Ouvrir ce sujet" if n["kind"] == "subject" else "📄 Ouvrir cette fiche"),
                          command=lambda: self.open_node(k))
            m.add_separator()
        m.add_command(label="🎯 Recentrer", command=self.fit)
        m.add_command(label="✨ Réorganiser", command=self.shake)
        m.add_command(label="✖ Fermer la carte", command=self.destroy)
        popup(m, e)

    def destroy(self):
        if self.job:
            try:
                self.after_cancel(self.job)
            except tk.TclError:
                pass
            self.job = None
        try:
            self.app._mindmap = None
        except Exception:
            pass
        super().destroy()


SPECIAL_VIEWS = [("v:all", "🗂", "Tout"), ("v:fav", "★", "Favoris"), ("v:pin", "📌", "Épinglés"),
                 ("v:recent", "🕘", "Récents"), ("v:tags", "🏷", "Étiquettes"), ("v:trash", "🗑", "Corbeille")]
SORTS = [("manual", "Ordre manuel"), ("recent", "Plus récents"), ("old", "Plus anciens"), ("title", "Titre A→Z"),
         ("type", "Par type"), ("event", "Date de l'info")]
PERIODS = [("", "Toutes les dates"), ("7", "7 derniers jours"), ("30", "30 derniers jours"), ("365", "Cette année")]
PANES_V = 1
TYPE_FILTERS = [("", "Tous les types")] + [(k, f"{TYPES[k]['icon']} {TYPES[k]['plural']}") for k in TYPE_ORDER]


class GrimoireApp(tk.Tk):
    def __init__(self, args):
        super().__init__()
        global TK9
        self.withdraw()
        self.args = args
        self.title(APP_TITLE)
        try:
            TK9 = str(self.tk.call("info", "patchlevel")).startswith("9")
        except Exception:
            TK9 = False
        self.q: "queue.Queue[Callable]" = queue.Queue()
        self.jobs: "queue.Queue[Tuple[Callable, Optional[Callable], str]]" = queue.Queue()
        self.njobs = 0
        self.store = Store().open()
        try:
            seed_content(self.store, demo=bool(getattr(args, "demo", False)))
        except Exception:
            logger.error("contenu de départ : %s", traceback.format_exc())
        st = self.store
        C.clear()
        C.update(THEMES.get(st.get("theme", "norton"), THEMES["norton"]))
        init_fonts(self, st.get("font_delta", 0))
        if not st.get("gx_cards_default"):      # 1.5 : la vue Cartes devient la vue par defaut (une seule fois)
            st.set("view_mode", "cards")
            st.set("gx_cards_default", True)
        self.view_mode = st.get("view_mode", "cards")
        self._mindmap = None
        self.sort = st.get("sort", "manual")
        self.cur_view = st.get("last_view", "")
        if not self._view_valid(self.cur_view):
            self.cur_view = f"s:{st.find_subject('Bienvenue')}" if st.find_subject("Bienvenue") else "v:all"
        self.view_before_search = self.cur_view
        self.visible: List[Dict[str, Any]] = []
        self.selected: List[int] = []
        self.anchor: Optional[int] = None
        self.cur_item: Optional[int] = None
        self.undo_stack: List[Tuple[str, Callable[[], None]]] = []
        self.player = AudioPlayer()
        self.player_item: Optional[int] = None
        self.img_cache: Dict[Tuple[str, int, int], Any] = {}
        self.swatches: Dict[str, Any] = {}
        self.card_boxes: List[Tuple[int, int, int, int, int]] = []
        self.drag: Optional[Dict[str, Any]] = None
        self.press: Optional[Dict[str, Any]] = None
        self.search_job = None
        self.detail_job = None
        self.save_job = None
        self.results: List[Dict[str, Any]] = []
        self.terms: List[str] = []
        self.readonly_test = bool(getattr(args, "smoke", False) or getattr(args, "shot", ""))
        self.v_anim = tk.BooleanVar(master=self, value=bool(st.get("animations", True)))
        self._build()
        try:
            ico = os.path.join(BASE, "grimoire1.ico")
            if os.path.isfile(ico):
                self.iconbitmap(default=ico)
        except tk.TclError:
            pass
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.deiconify()
        if getattr(args, "geometry", ""):
            self.geometry(args.geometry)
        else:
            try:
                self.state("zoomed")
            except tk.TclError:
                self.geometry(f"{self.winfo_screenwidth()}x{self.winfo_screenheight() - 60}+0+0")
        for _ in range(2):
            threading.Thread(target=self._worker, daemon=True).start()
        self.after(60, self._poll)
        self.after(120, lambda: self.refresh_all(first=True))
        self.after(250, self._tick_player)
        if not self.readonly_test:
            self.after(150, self._ensure_shown)
            self.after(900, self._ensure_shown)
            self.after(1500, self._poll_inbox)
            self.run_job(lambda: self.store.backup(), None, "")
        logger.info("Grimoire démarré : %d sujets, %s fiches", len(st.subjects()), st.stats()["items"])

    # ------------------------------------------------------------ outils
    def _ensure_shown(self):
        if not IS_WIN:
            return
        try:
            u32 = ctypes.windll.user32
            hwnd = int(self.wm_frame(), 16)
            if not u32.IsWindowVisible(hwnd):
                u32.ShowWindow(hwnd, 3 if self.state() == "zoomed" else 5)
            self.lift()
        except Exception:
            pass

    def post(self, fn: Callable) -> None:
        self.q.put(fn)

    def _poll(self):
        try:
            for _ in range(100):
                fn = self.q.get_nowait()
                try:
                    fn()
                except Exception:
                    logger.error("tâche UI : %s", traceback.format_exc())
        except queue.Empty:
            pass
        self.after(70, self._poll)

    def _worker(self):
        while True:
            fn, done, label = self.jobs.get()
            res = None
            try:
                res = fn()
            except Exception:
                logger.error("tâche %s : %s", label, traceback.format_exc())
            self.njobs = max(0, self.njobs - 1)
            if done:
                self.post(lambda d=done, r=res: d(r))
            self.post(self._update_jobs)

    def run_job(self, fn: Callable, done: Optional[Callable] = None, label: str = "") -> None:
        self.njobs += 1
        self.jobs.put((fn, done, label))
        self._update_jobs(label)

    def _update_jobs(self, label: str = ""):
        try:
            self.l_jobs.configure(text=(f"⏳ {label or 'travail en cours'}… ({self.njobs})" if self.njobs else ""))
        except Exception:
            pass

    def set_status(self, msg: str, key: str = "FG") -> None:
        try:
            self.l_status.configure(text=msg, fg=C.get(key, C["FG"]))
        except Exception:
            pass

    def _view_valid(self, v: str) -> bool:
        if not v:
            return False
        if v.startswith("s:"):
            return bool(self.store.subject(v[2:]))
        if v.startswith("t:"):
            return True
        return v in [k for k, _i, _l in SPECIAL_VIEWS]

    def subject_order(self) -> List[int]:
        out: List[int] = []

        def walk(pid):
            for s in self.store.children(pid):
                out.append(s["id"])
                walk(s["id"])
        walk(None)
        return out

    def swatch(self, color: str):
        k = color or "none"
        if k not in self.swatches:
            self.swatches[k] = color_swatch(self, color or C["DIM"], 12)
        return self.swatches[k]

    def photo(self, rel_or_abs: str, w: int, h: int):
        """Vignette PhotoImage (cache) ; None si absente."""
        p = Paths.abs(rel_or_abs) if rel_or_abs else ""
        if not p or not os.path.isfile(p):
            return None
        key = (p, w, h)
        if key in self.img_cache:
            return self.img_cache[key]
        img = None
        try:
            from PIL import Image, ImageTk  # type: ignore
            with Image.open(p) as im:
                im = im.convert("RGBA") if im.mode not in ("RGB", "RGBA") else im.copy()
            im.thumbnail((w, h), Image.Resampling.LANCZOS)
            img = ImageTk.PhotoImage(im, master=self)
        except Exception:
            try:
                img = tk.PhotoImage(file=p, master=self)
            except Exception:
                img = None
        if len(self.img_cache) > 400:
            self.img_cache.clear()
        self.img_cache[key] = img
        return img

    def fit_text(self, text: str, font_name: str, width: int, lines: int = 1) -> str:
        f = fnt(font_name)
        meas = f.measure if hasattr(f, "measure") else (lambda s: len(s) * 8)
        words = (text or "").replace("\n", " ").split(" ")
        out: List[str] = []
        cur = ""
        i = 0
        while i < len(words):
            w = words[i]
            cand = (cur + " " + w).strip()
            if meas(cand) <= width:
                cur = cand
                i += 1
                continue
            if not cur:
                cut = len(w)
                while cut > 1 and meas(w[:cut]) > width:
                    cut -= 1
                cur, words[i] = w[:cut], w[cut:]
            out.append(cur)
            cur = ""
            if len(out) == lines:
                break
        if len(out) < lines and cur:
            out.append(cur)
            cur = ""
        rest = " ".join(words[i:]).strip() if len(out) == lines else ""
        if (rest or cur) and out:
            last = out[-1]
            while last and meas(last + "…") > width:
                last = last[:-1]
            out[-1] = last.rstrip() + "…"
        return "\n".join(out)

    # ------------------------------------------------------------ construction
    def _build(self):
        apply_styles(self)
        self.configure(bg=C["BG"])
        self.img_cache.clear()
        self.swatches.clear()
        self._build_menu()
        self._build_toolbar()
        sb = tk.Frame(self, bg=C["PANEL"])
        sb.pack(side="bottom", fill="x")
        self.l_count = tk.Label(sb, text="", bg=C["PANEL"], fg=C["DIM"], font=fnt("GSM"), anchor="e")
        self.l_count.pack(side="right", padx=8)
        self.l_jobs = tk.Label(sb, text="", bg=C["PANEL"], fg=C["WARN"], font=fnt("GSM"), anchor="e")
        self.l_jobs.pack(side="right", padx=8)
        self.l_status = tk.Label(sb, text="Prêt.", bg=C["PANEL"], fg=C["FG"], font=fnt("GSM"), anchor="w", width=1)
        self.l_status.pack(side="left", fill="x", expand=True, padx=8, pady=3)
        Tooltip(self.l_status, lambda: self.l_status.cget("text"))
        self.pw = tk.PanedWindow(self, orient="horizontal", bg=C["LINE"], sashwidth=5, bd=0, sashrelief="flat",
                                 opaqueresize=True)
        self.pw.pack(fill="both", expand=True)
        self._build_left()
        self._build_center()
        self._build_right()
        sw = self.winfo_screenwidth()
        g = getattr(self.args, "geometry", "")
        if g and re.match(r"^\d+x", g):
            sw = int(g.split("x")[0])
        elif self.winfo_width() > 400:
            sw = self.winfo_width()
        st = self.store
        saved = not g and st.get("panes_v") == PANES_V
        left_w = int((saved and st.get("left_w")) or (200 if sw <= 1100 else 245))
        right_w = int((saved and st.get("right_w")) or int(sw * (0.35 if sw <= 1100 else 0.36)))
        left_w = max(170, min(int(sw * (0.32 if sw <= 1100 else 0.30)), max(left_w, self._left_needed())))
        right_w = max(340, min(int(sw * 0.55), right_w))
        self.pw.add(self.f_left, minsize=170, width=left_w, stretch="never")
        self.pw.add(self.f_center, minsize=280, stretch="always")
        self.pw.add(self.f_right, minsize=320, width=right_w, stretch="never")
        self._bind_keys()
        self._setup_dnd()

    def _left_needed(self) -> int:
        try:
            f = fnt("GUI")
            if isinstance(f, str):
                f = tkfont.nametofont(f)
            names = [f" {ic}  {lab}" for _k, ic, lab in SPECIAL_VIEWS]
            for sid in self.subject_order():
                s = self.store.subject(sid)
                depth = len(self.store.subject_path(sid).split(" › ")) - 1
                names.append((depth, f"{s['icon'] or '📁'} {s['name']}"))
            need = 0
            for d in names:
                if isinstance(d, tuple):
                    need = max(need, d[0] * 20 + 20 + 16 + f.measure(d[1]))
                else:
                    need = max(need, 20 + f.measure(d))
            return need + 38 + 18 + 14
        except Exception:
            return 240

    def _build_menu(self):
        mb = tk.Menu(self)
        style_menu(mb)
        m = new_menu(mb)
        m.add_command(label="📝 Nouvelle note", accelerator="Ctrl+N", command=self.new_note)
        m.add_command(label="📁 Nouveau sujet…", accelerator="Ctrl+Maj+N", command=lambda: self.new_subject(None))
        m.add_command(label="📂 Nouveau sous-sujet…", command=lambda: self.new_subject(self.current_sid(strict=True)))
        m.add_separator()
        m.add_command(label="📥 Importer un dossier…", command=lambda: self.import_folder_dialog(None))
        m.add_command(label="🌐 Exporter le sujet en HTML…", accelerator="Ctrl+Maj+E", command=lambda: self.export_dialog(None, False))
        m.add_command(label="📦 Exporter le sujet en ZIP…", command=lambda: self.export_dialog(None, True))
        m.add_command(label="🌐 Exporter la sélection en HTML…", command=self.export_selection)
        m.add_separator()
        m.add_command(label="💾 Sauvegarder maintenant (copie datée)", accelerator="Ctrl+S", command=self.backup_now)
        m.add_command(label="📁 Ouvrir le dossier du Grimoire", command=lambda: open_path(Paths.data))
        m.add_command(label="↩ Restaurer une sauvegarde…", command=self.restore_backup)
        m.add_separator()
        m.add_command(label="Quitter", accelerator="Alt+F4", command=self.on_close)
        mb.add_cascade(label="Fichier", menu=m)
        m = new_menu(mb)
        m.add_command(label="Annuler la dernière suppression / le dernier déplacement", accelerator="Ctrl+Z", command=self.do_undo)
        m.add_separator()
        m.add_command(label="Coller intelligent (lien, texte, image, fichiers)", accelerator="Ctrl+V", command=self.smart_paste)
        m.add_command(label="Coller comme note texte", accelerator="Ctrl+Maj+V", command=lambda: self.smart_paste(plain=True))
        m.add_separator()
        m.add_command(label="Renommer", accelerator="F2", command=self.rename_any)
        m.add_command(label="★ Favori oui/non", accelerator="Ctrl+D", command=self.toggle_fav)
        m.add_command(label="📌 Épingler oui/non", accelerator="Ctrl+P", command=self.toggle_pin)
        m.add_command(label="🏷 Étiquettes…", accelerator="Ctrl+T", command=self.edit_tags)
        m.add_command(label="📁 Déplacer vers…", accelerator="Ctrl+M", command=lambda: self.move_selected(False))
        m.add_command(label="⧉ Copier vers…", command=lambda: self.move_selected(True))
        m.add_command(label="Monter / descendre", accelerator="Alt+Haut / Alt+Bas", command=lambda: self.move_item_step(-1))
        m.add_separator()
        m.add_command(label="Tout sélectionner", accelerator="Ctrl+A", command=self.select_all)
        m.add_command(label="🗑 Supprimer (corbeille)", accelerator="Suppr", command=self.delete_selected)
        mb.add_cascade(label="Édition", menu=m)
        mb.add_cascade(label="Sujets", menu=self._subjects_menu(mb))
        self.menu_add = self._make_add_menu(mb)
        mb.add_cascade(label="Ajouter", menu=self.menu_add)
        m = new_menu(mb)
        self.v_view = tk.StringVar(value=self.view_mode)
        m.add_radiobutton(label="☰ Liste", accelerator="Ctrl+1", variable=self.v_view, value="list", command=self._view_from_var)
        m.add_radiobutton(label="▦ Cartes", accelerator="Ctrl+2", variable=self.v_view, value="cards", command=self._view_from_var)
        m.add_radiobutton(label="🕘 Chronologie", accelerator="Ctrl+3", variable=self.v_view, value="chrono", command=self._view_from_var)
        m.add_separator()
        m.add_command(label="🗺 Carte des sujets", accelerator="F8", command=self.open_mindmap)
        m.add_checkbutton(label="✨ Animations", variable=self.v_anim, command=self.toggle_animations)
        m.add_command(label="📖 Mode lecture", accelerator="F11", command=self.open_reader)
        m.add_command(label="🧭 Aller à un sujet ou une fiche…", accelerator="Ctrl+G", command=self.open_palette)
        m.add_command(label="🔍 Rechercher partout", accelerator="Ctrl+F", command=self.focus_search)
        m.add_separator()
        m.add_command(label="Texte plus grand", accelerator="Ctrl++", command=lambda: self.zoom(1))
        m.add_command(label="Texte plus petit", accelerator="Ctrl+-", command=lambda: self.zoom(-1))
        m.add_command(label="Taille normale", accelerator="Ctrl+0", command=lambda: self.zoom(0))
        th = new_menu(m)
        self.v_theme = tk.StringVar(value=self.store.get("theme", "norton"))
        for k, lab in THEME_LABELS.items():
            th.add_radiobutton(label=lab, variable=self.v_theme, value=k, command=self.change_theme)
        m.add_cascade(label="Thème", menu=th)
        m.add_command(label="Rafraîchir", accelerator="F5", command=self.refresh_all)
        mb.add_cascade(label="Affichage", menu=m)
        m = new_menu(mb)
        m.add_command(label="📊 Statistiques", command=self.show_stats)
        m.add_command(label="🔎 Vérifier le Grimoire (fichiers, index)", command=self.check_dialog)
        m.add_command(label="🔄 Reconstruire l'index de recherche", command=self.rebuild_index)
        m.add_separator()
        self.v_fetch = tk.BooleanVar(value=bool(self.store.get("auto_fetch", True)))
        m.add_checkbutton(label="Récupérer titre, description et miniature des liens", variable=self.v_fetch,
                          command=lambda: self.store.set("auto_fetch", self.v_fetch.get()))
        self.v_ocr = tk.BooleanVar(value=bool(self.store.get("auto_ocr", False)))
        m.add_checkbutton(label="Lire le texte des images ajoutées (OCR Windows, automatique)", variable=self.v_ocr,
                          command=lambda: self.store.set("auto_ocr", self.v_ocr.get()))
        self.v_atr = tk.BooleanVar(value=bool(self.store.get("auto_transcribe", True)))
        m.add_checkbutton(label="Transcrire les mémos vocaux (si faster-whisper est installé)", variable=self.v_atr,
                          command=lambda: self.store.set("auto_transcribe", self.v_atr.get()))
        wm = new_menu(m)
        self.v_wmodel = tk.StringVar(value=self.store.get("whisper_model", "small"))
        for k, lab in (("tiny", "tiny (très rapide)"), ("base", "base (rapide)"), ("small", "small (bon, défaut)"),
                       ("medium", "medium (précis, lent)")):
            wm.add_radiobutton(label=lab, variable=self.v_wmodel, value=k,
                               command=lambda: self.store.set("whisper_model", self.v_wmodel.get()))
        m.add_cascade(label="Modèle de transcription", menu=wm)
        m.add_command(label="⬇ Installer la transcription (faster-whisper)…", command=self.install_whisper)
        m.add_separator()
        m.add_command(label="📋 Gérer mes modèles de fiches…", command=self.manage_templates)
        m.add_command(label="📒 Voir le journal (grimoire.log)", command=self.show_log)
        mb.add_cascade(label="Outils", menu=m)
        m = new_menu(mb)
        m.add_command(label="Aide", accelerator="F1", command=self.show_help)
        m.add_command(label="Raccourcis clavier", command=lambda: self.show_help("raccourcis"))
        m.add_command(label="À propos du Grimoire", command=self.about)
        mb.add_cascade(label="Aide", menu=m)
        self.config(menu=mb)
        self.menubar = mb

    def _make_add_menu(self, parent):
        m = new_menu(parent)
        m.add_command(label="📝 Note", accelerator="Ctrl+N", command=self.new_note)
        tm = new_menu(m)
        for name, (ic, _md) in self.all_templates().items():
            tm.add_command(label=f"{ic} {name}", command=lambda n=name: self.new_note(template=n))
        tm.add_separator()
        tm.add_command(label="💾 Enregistrer la note ouverte comme modèle…", command=self.save_as_template)
        m.add_cascade(label="📋 Fiche à partir d'un modèle", menu=tm)
        m.add_command(label="🔗 Lien web…", accelerator="Ctrl+L", command=self.add_link_dialog)
        m.add_command(label="❝ Citation…", accelerator="Ctrl+Maj+Q", command=self.add_quote_dialog)
        m.add_command(label="🌐 Capturer une page web complète…", command=self.capture_page_dialog)
        m.add_separator()
        m.add_command(label="🖼 Image(s)…", accelerator="Ctrl+Maj+I", command=lambda: self.add_files_dialog("image"))
        m.add_command(label="📄 Document(s) (PDF, Word, texte…)…", command=lambda: self.add_files_dialog("document"))
        m.add_command(label="🔊 Son(s)…", command=lambda: self.add_files_dialog("audio"))
        m.add_command(label="🎬 Vidéo(s) locale(s)…", command=lambda: self.add_files_dialog("video"))
        m.add_command(label="📎 Fichier(s) quelconque(s)…", accelerator="Ctrl+O", command=lambda: self.add_files_dialog(None))
        m.add_command(label="🎙 Mémo vocal (micro)", accelerator="Ctrl+R", command=self.record_memo)
        m.add_separator()
        m.add_command(label="📋 Coller (Ctrl+V)", command=self.smart_paste)
        m.add_command(label="📂 Importer un dossier…", command=lambda: self.import_folder_dialog(None))
        return m

    def _build_toolbar(self):
        tb = tk.Frame(self, bg=C["PANEL"])
        tb.pack(side="top", fill="x")
        self.f_toolbar = tb
        sw = self.winfo_screenwidth() if not getattr(self.args, "geometry", "") else int(self.args.geometry.split("x")[0])
        small = sw <= 1100
        right = tk.Frame(tb, bg=C["PANEL"])
        right.pack(side="right", padx=6)
        mk_button(right, "?", self.show_help, tip="Aide (F1)").pack(side="right", padx=3, pady=6)
        mk_button(right, "📊", self.show_stats, tip="Statistiques du Grimoire").pack(side="right", padx=3, pady=6)
        mk_button(right, "🗺" if small else "🗺 Carte", self.open_mindmap, tip="Carte des sujets : tes sujets en graphe animé (F8)").pack(
            side="right", padx=3, pady=6)
        mk_button(right, "🧭", self.open_palette, tip="Aller à un sujet ou une fiche (Ctrl+G)").pack(side="right", padx=3, pady=6)
        mk_button(right, "📖" if small else "📖 Lecture", self.open_reader, tip="Mode lecture plein écran (F11)").pack(
            side="right", padx=3, pady=6)
        tk.Label(tb, text="📖 GRIMOIRE", bg=C["PANEL"], fg=C["HI"], font=fnt("GTitle")).pack(side="left", padx=(10, 10), pady=6)
        sbox = tk.Frame(tb, bg=C["ENTRY_BG"], highlightthickness=1, highlightbackground=C["LINE"], highlightcolor=C["HI"])
        sbox.pack(side="left", pady=6)
        tk.Label(sbox, text="🔍", bg=C["ENTRY_BG"], fg=C["FG"], font=fnt("GUI")).pack(side="left", padx=(6, 0))
        self.v_search = tk.StringVar()
        self.e_search = tk.Entry(sbox, textvariable=self.v_search, width=22 if small else 30, bg=C["ENTRY_BG"],
                                 fg=C["ENTRY_FG"], insertbackground=C["HI"], relief="flat", font=fnt("GUI"),
                                 highlightthickness=0, selectbackground=C["SEL"], selectforeground=C["ON_SEL"])
        self.e_search.pack(side="left", padx=4, pady=3)
        self.l_ph = tk.Label(sbox, text="Rechercher… (Ctrl+F)", bg=C["ENTRY_BG"], fg=C["DIM"], font=fnt("GUI"), cursor="xterm")
        self.l_ph.place(in_=self.e_search, x=2, rely=0.5, anchor="w")
        self.l_ph.bind("<Button-1>", lambda _e: self.e_search.focus_set())
        b = tk.Button(sbox, text="✕", command=self.clear_search, bg=C["ENTRY_BG"], fg=C["DIM"], relief="flat", bd=0,
                      activebackground=C["SEL"], font=fnt("GUI"), cursor="hand2")
        b.pack(side="left", padx=(0, 4))
        Tooltip(b, "Effacer la recherche (Échap)")
        self.v_search.trace_add("write", lambda *_a: self._search_changed())
        self.e_search.bind("<Return>", lambda _e: self._focus_items())
        self.e_search.bind("<Down>", lambda _e: self._focus_items())
        self.e_search.bind("<Escape>", lambda _e: self.clear_search())
        self.e_search.bind("<Control-KeyPress>", self._entry_ctrl)
        self.b_add = mk_button(tb, "＋ Ajouter ▾", self._add_popup, "accent",
                               tip="Note, modèle de fiche, lien, citation, image, document, son, mémo vocal, page web…")
        self.b_add.pack(side="left", padx=(10, 4), pady=6)
        mk_button(tb, "📋 Coller", self.smart_paste, tip="Coller un lien, du texte, une image ou des fichiers dans le sujet ouvert (Ctrl+V)").pack(
            side="left", padx=3, pady=6)
        mk_button(tb, "🎙 Mémo", self.record_memo, tip="Enregistrer un mémo vocal au micro (Ctrl+R)").pack(side="left", padx=3, pady=6)

    def _add_popup(self):
        b = self.b_add
        try:
            self.menu_add.tk_popup(b.winfo_rootx(), b.winfo_rooty() + b.winfo_height())
        finally:
            try:
                self.menu_add.grab_release()
            except Exception:
                pass

    def _build_left(self):
        f = tk.Frame(self.pw, bg=C["PANEL"])
        self.f_left = f
        h = tk.Frame(f, bg=C["PANEL"])
        h.pack(fill="x")
        tk.Label(h, text="SUJETS", bg=C["PANEL"], fg=C["HI"], font=fnt("GHead")).pack(side="left", padx=8, pady=(6, 4))
        b = tk.Button(h, text="＋", command=lambda: self.new_subject(None), bg=C["PANEL"], fg=C["HI"], relief="flat", bd=0,
                      activebackground=C["SEL"], font=fnt("GUIB"), cursor="hand2")
        b.pack(side="right", padx=6)
        Tooltip(b, "Nouveau sujet (Ctrl+Maj+N) · clic droit sur un sujet : sous-sujet, icône, couleur…")
        fr = tk.Frame(f, bg=C["PANEL"])
        fr.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(fr, style="Subj.Treeview", show="tree", columns=("n",), selectmode="browse")
        self.tree.column("#0", width=180, stretch=True)
        self.tree.column("n", width=38, anchor="e", stretch=False)
        vsb = ttk.Scrollbar(fr, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.tag_configure("special", foreground=C["HI"])
        self.tree.tag_configure("subj", foreground=C["TEXT"])
        self.tree.tag_configure("pinned", foreground=C["HI"])
        self.tree.tag_configure("tag", foreground=C["FG"])
        self.tree.tag_configure("sep", foreground=C["LINE"])
        self.tree.tag_configure("drop", background=C["HI"], foreground=C["ON_HI"])
        self.tree.bind("<<TreeviewSelect>>", self._tree_selected)
        self.tree.bind("<<TreeviewOpen>>", lambda _e: self._tree_open(True))
        self.tree.bind("<<TreeviewClose>>", lambda _e: self._tree_open(False))
        self.tree.bind("<Button-3>", self._tree_menu)
        self.tree.bind("<ButtonPress-1>", self._tree_press, add="+")
        self.tree.bind("<B1-Motion>", self._drag_motion, add="+")
        self.tree.bind("<ButtonRelease-1>", self._drag_release, add="+")
        self.tree.bind("<F2>", lambda _e: self.rename_subject())
        self.bind_all("<Control-Shift-G>", lambda _e: self.manage_subjects())
        self.tree.bind("<Delete>", lambda _e: self.delete_subject())
        self.tree.bind("<Insert>", lambda _e: self.new_subject(self.current_sid(strict=True)))
        self.tree.bind("<Alt-Up>", lambda _e: (self.reorder_subject(-1), "break")[1])
        self.tree.bind("<Alt-Down>", lambda _e: (self.reorder_subject(1), "break")[1])
        self.tree.bind("<Return>", lambda _e: (self._focus_items(), "break")[1])

    def _build_center(self):
        f = tk.Frame(self.pw, bg=C["BG"])
        self.f_center = f
        self.colorbar = tk.Frame(f, bg=C["HI"], height=4)
        self.colorbar.pack(fill="x")
        hd = tk.Frame(f, bg=C["BG"])
        hd.pack(fill="x")
        self.l_view = tk.Label(hd, text="", bg=C["BG"], fg=C["HI"], font=fnt("GTitle"), anchor="w")
        self.l_view.pack(side="left", padx=10, pady=(4, 0), fill="x", expand=True)
        fb = FlowFrame(f, bg=C["BG"])
        fb.pack(fill="x", padx=8, pady=(2, 4))
        self.fbar = fb
        self.view_btns: Dict[str, Any] = {}
        for key, txt, tip in (("list", "☰", "Liste (Ctrl+1)"), ("cards", "▦", "Cartes avec vignettes (Ctrl+2)"),
                              ("chrono", "🕘", "Chronologie par mois (Ctrl+3)")):
            b = mk_button(fb, txt, lambda k=key: self.set_view_mode(k), tip=tip)
            b.configure(padx=7)
            fb.add(b, 1)
            self.view_btns[key] = b
        b = mk_button(fb, "🗺 Carte des sujets", self.open_mindmap, tip="Carte animée de tes sujets et de leurs fiches (F8)")
        fb.add(b, 6)
        ch_an = mk_check(fb, "✨ Animations", self.v_anim, bg=C["BG"], cmd=self.toggle_animations)
        ch_an.configure(font=fnt("GSM"))
        fb.add(ch_an, 4)
        Tooltip(ch_an, "Petites animations (apparition des cartes, carte des sujets, barre de progression)")
        self.cb_sort = ttk.Combobox(fb, values=[lab for _k, lab in SORTS], state="readonly", width=14, font=fnt("GSM"))
        fb.add(self.cb_sort, 6)
        self.cb_sort.current(max(0, [k for k, _l in SORTS].index(self.sort) if self.sort in [k for k, _l in SORTS] else 0))
        self.cb_sort.bind("<<ComboboxSelected>>", lambda _e: self._sort_changed())
        Tooltip(self.cb_sort, "Tri des fiches")
        self.cb_type = ttk.Combobox(fb, values=[lab for _k, lab in TYPE_FILTERS], state="readonly", width=16, font=fnt("GSM"))
        self.cb_type.current(0)
        fb.add(self.cb_type, 3)
        self.cb_type.bind("<<ComboboxSelected>>", lambda _e: self.refresh_items())
        Tooltip(self.cb_type, "Filtrer par type")
        self.cb_tag = ttk.Combobox(fb, values=["Toutes étiquettes"], state="readonly", width=17, font=fnt("GSM"))
        self.cb_tag.current(0)
        fb.add(self.cb_tag, 3)
        self.cb_tag.bind("<<ComboboxSelected>>", lambda _e: self.refresh_items())
        Tooltip(self.cb_tag, "Filtrer par étiquette")
        self.v_sub = tk.BooleanVar(value=bool(self.store.get("include_sub", True)))
        self.chk_sub = mk_check(fb, "＋sous-sujets", self.v_sub, bg=C["BG"], cmd=self._sub_changed)
        self.chk_sub.configure(font=fnt("GSM"))
        fb.add(self.chk_sub, 4)
        Tooltip(self.chk_sub, "Montrer aussi les fiches des sous-sujets")
        self.cb_scope = ttk.Combobox(fb, values=["Partout", "Dans ce sujet"], state="readonly", width=18, font=fnt("GSM"))
        self.cb_scope.current(0)
        self.cb_scope.bind("<<ComboboxSelected>>", lambda _e: self.do_search())
        fb.add(self.cb_scope, 3)
        Tooltip(self.cb_scope, "Où chercher")
        self.cb_period = ttk.Combobox(fb, values=[lab for _k, lab in PERIODS], state="readonly", width=17, font=fnt("GSM"))
        self.cb_period.current(0)
        self.cb_period.bind("<<ComboboxSelected>>", lambda _e: self.refresh_items())
        fb.add(self.cb_period, 3)
        Tooltip(self.cb_period, "Période (date de l'info, sinon date d'ajout)")
        self.l_vcount = tk.Label(fb, text="", bg=C["BG"], fg=C["DIM"], font=fnt("GSM"), anchor="w")
        fb.add(self.l_vcount, 8)
        self.f_view = tk.Frame(f, bg=C["BG"])
        self.f_view.pack(fill="both", expand=True)
        # liste
        self.f_list = tk.Frame(self.f_view, bg=C["BG"])
        cols = ("title", "subject", "date", "tags")
        self.lst = ttk.Treeview(self.f_list, columns=cols, show="headings", selectmode="extended")
        for cid, lab, w, stt in (("title", "Titre", 300, True), ("subject", "Sujet", 150, False), ("date", "Date", 110, False),
                                 ("tags", "Étiquettes", 130, False)):
            self.lst.heading(cid, text=lab, anchor="w", command=lambda c=cid: self._heading_sort(c))
            self.lst.column(cid, width=w, stretch=stt, anchor="w", minwidth=60)
        lv = ttk.Scrollbar(self.f_list, orient="vertical", command=self.lst.yview)
        self.lst.configure(yscrollcommand=lv.set)
        self.lst.pack(side="left", fill="both", expand=True)
        lv.pack(side="right", fill="y")
        self.lst.tag_configure("fav", foreground=C["HI"])
        self.lst.tag_configure("pending", foreground=C["DIM"])
        self.lst.tag_configure("drop", background=C["HI"], foreground=C["ON_HI"])
        self.lst.bind("<Configure>", lambda _e: self._list_columns())
        dw = tkfont.Font(font=fnt("GUI")).measure("15 sept. 2026") + 22
        self.lst.column("date", width=dw, minwidth=dw)
        self._row_tip(self.lst)
        # cartes
        self.f_cards = tk.Frame(self.f_view, bg=C["BG"])
        self.cv = tk.Canvas(self.f_cards, bg=C["BG"], highlightthickness=0, bd=0, takefocus=1)
        cvs = ttk.Scrollbar(self.f_cards, orient="vertical", command=self.cv.yview)
        self.cv.configure(yscrollcommand=cvs.set)
        self.cv.pack(side="left", fill="both", expand=True)
        cvs.pack(side="right", fill="y")
        self.cv.bind("<Configure>", lambda _e: self._cards_resized())
        self.cv.bind("<MouseWheel>", lambda e: self.cv.yview_scroll(wheel_steps(e) * 3, "units"))
        self.cv.bind("<Button-4>", lambda e: self.cv.yview_scroll(-3, "units"))
        self.cv.bind("<Button-5>", lambda e: self.cv.yview_scroll(3, "units"))
        self.cv.bind("<ButtonPress-1>", self._card_press)
        self.cv.bind("<B1-Motion>", self._drag_motion)
        self.cv.bind("<ButtonRelease-1>", self._drag_release)
        self.cv.bind("<Double-Button-1>", self._card_double)
        self.cv.bind("<Motion>", self._card_motion)
        self.cv.bind("<Leave>", lambda _e: self._card_motion(type("E", (), {"x": -9999, "y": -9999})()))
        self.cv.bind("<Button-3>", self._card_menu)
        for k in ("Left", "Right", "Up", "Down", "Home", "End"):
            self.cv.bind(f"<{k}>", lambda _e, kk=k: self._card_key(kk))
        # chronologie
        self.f_chrono = tk.Frame(self.f_view, bg=C["BG"])
        self.chr = ttk.Treeview(self.f_chrono, columns=("date", "subject"), show="tree headings", selectmode="extended")
        self.chr.heading("#0", text="Fiche", anchor="w")
        self.chr.heading("date", text="Date", anchor="w")
        self.chr.heading("subject", text="Sujet", anchor="w")
        self.chr.column("#0", width=320, stretch=True)
        self.chr.column("date", width=110, stretch=False)
        self.chr.column("subject", width=150, stretch=False)
        cs = ttk.Scrollbar(self.f_chrono, orient="vertical", command=self.chr.yview)
        self.chr.configure(yscrollcommand=cs.set)
        self.chr.pack(side="left", fill="both", expand=True)
        cs.pack(side="right", fill="y")
        self.chr.tag_configure("month", foreground=C["HI"], font=fnt("GUIB"))
        self.chr.tag_configure("fav", foreground=C["HI"])
        self.chr.tag_configure("drop", background=C["HI"], foreground=C["ON_HI"])
        self.chr.bind("<Configure>", lambda _e: self._list_columns())
        self.chr.column("date", width=dw, minwidth=dw)
        self._row_tip(self.chr)
        # resultats de recherche
        self.f_results = tk.Frame(self.f_view, bg=C["BG"])
        self.rt = tk.Text(self.f_results, bg=C["CARD"], fg=C["TEXT"], relief="flat", wrap="word", highlightthickness=0,
                          padx=10, pady=6, cursor="arrow", font=fnt("GUI"), spacing1=1, takefocus=1)
        rs = ttk.Scrollbar(self.f_results, orient="vertical", command=self.rt.yview)
        self.rt.configure(yscrollcommand=rs.set)
        self.rt.pack(side="left", fill="both", expand=True)
        rs.pack(side="right", fill="y")
        self.rt.tag_configure("rtitle", foreground=C["HI"], font=fnt("GUIB"))
        self.rt.tag_configure("rsub", foreground=C["DIM"], font=fnt("GSM"))
        self.rt.tag_configure("rmeta", foreground=C["DIM"], font=fnt("GSM"), spacing3=8)
        self.rt.tag_configure("rsnip", foreground=C["TEXT"], lmargin1=22, lmargin2=22)
        self.rt.tag_configure("hl", background=C["SEL"], foreground=C["ON_SEL"])
        self.rt.tag_configure("rsel", background=C["HOVER"])
        self.rt.tag_configure("rnone", foreground=C["DIM"], font=fnt("GUI"), justify="center", spacing1=30)
        self.rt.tag_raise("hl")
        self.rt.bind("<Button-1>", self._result_click)
        self.rt.bind("<Double-Button-1>", self._result_double)
        self.rt.bind("<Button-3>", self._result_menu)
        self.rt.bind("<Key>", self._result_key)
        self.rt.bind("<MouseWheel>", lambda e: (self.rt.yview_scroll(wheel_steps(e) * 3, "units"), "break")[1])
        # corbeille
        self.f_trash = tk.Frame(self.f_view, bg=C["BG"])
        tb = FlowFrame(self.f_trash, bg=C["BG"], gap=3)
        tb.pack(fill="x", padx=4, pady=(0, 4))
        tb.add(mk_button(tb, "♻ Restaurer", self.trash_restore, "accent", tip="Remettre la sélection à sa place (Entrée)"), 0)
        tb.add(mk_button(tb, "✖ Supprimer définitivement", self.trash_purge, "danger",
                         tip="Effacer pour de bon la sélection (Suppr)"), 4)
        tb.add(mk_button(tb, "🧹 Vider la corbeille", self.trash_empty, "danger", tip="Tout effacer pour de bon"), 4)
        self.trv = ttk.Treeview(self.f_trash, columns=("kind", "deleted", "origin"), show="tree headings", selectmode="extended")
        self.trv.heading("#0", text="Élément", anchor="w")
        self.trv.heading("kind", text="Type", anchor="w")
        self.trv.heading("deleted", text="Supprimé", anchor="w")
        self.trv.heading("origin", text="Venait de", anchor="w")
        self.trv.column("#0", width=280, stretch=True)
        self.trv.column("kind", width=110, stretch=False)
        self.trv.column("deleted", width=120, stretch=False)
        self.trv.column("origin", width=150, stretch=False)
        ts = ttk.Scrollbar(self.f_trash, orient="vertical", command=self.trv.yview)
        self.trv.configure(yscrollcommand=ts.set)
        self.trv.pack(side="left", fill="both", expand=True)
        ts.pack(side="right", fill="y")
        self.trv.bind("<Delete>", lambda _e: self.trash_purge())
        self.trv.bind("<Return>", lambda _e: self.trash_restore())
        self.trv.bind("<<TreeviewSelect>>", lambda _e: self.update_detail())
        self.trv.bind("<Configure>", lambda _e: self._fit_columns(), add="+")
        self.trv.column("deleted", width=tkfont.Font(font=fnt("GUI")).measure("15 sept. 2026 10:00") + 16)
        for w in (self.lst, self.chr):
            w.bind("<<TreeviewSelect>>", self._tv_selected)
            w.bind("<Double-Button-1>", self._tv_double)
            w.bind("<Button-3>", self._tv_menu)
            w.bind("<ButtonPress-1>", self._tv_press, add="+")
            w.bind("<B1-Motion>", self._drag_motion, add="+")
            w.bind("<ButtonRelease-1>", self._drag_release, add="+")
        for w in (self.lst, self.chr, self.cv, self.rt):
            w.bind("<Return>", lambda _e: (self.open_selected(), "break")[1])
            w.bind("<Delete>", lambda _e: self.delete_selected())
            w.bind("<F2>", lambda _e: self.rename_item())
            w.bind("<Control-a>", lambda _e: (self.select_all(), "break")[1])
            w.bind("<Alt-Up>", lambda _e: (self.move_item_step(-1), "break")[1])
            w.bind("<Alt-Down>", lambda _e: (self.move_item_step(1), "break")[1])
            w.bind("<Key>", self._type_to_search, add="+")
        self._show_view_widget()

    def _row_tip(self, tv):
        """Infobulle sur une ligne de liste : titre complet, sujet, etiquettes (utile si la colonne est coupee)."""
        state = {"row": "", "job": None, "tip": None}

        def hide(_e=None):
            if state["job"]:
                try:
                    tv.after_cancel(state["job"])
                except Exception:
                    pass
                state["job"] = None
            if state["tip"] is not None:
                try:
                    state["tip"].destroy()
                except Exception:
                    pass
                state["tip"] = None

        def show(row, x, y):
            state["job"] = None
            if not row.startswith("i:") or self.drag:
                return
            it = self.store.item(row[2:])
            if not it:
                return
            txt = (it.get("title") or "(sans titre)") + "\n" + self.store.subject_path(it["subject_id"])
            if it.get("tags"):
                txt += "\n" + "  ".join("#" + t for t in tag_list(it["tags"]))
            try:
                state["tip"] = show_tip(tv, txt, x + 16, y + 18)
            except tk.TclError:
                pass

        def motion(e):
            row = tv.identify_row(e.y)
            if row != state["row"]:
                state["row"] = row
                hide()
                if row:
                    state["job"] = tv.after(700, lambda r=row, x=e.x_root, y=e.y_root: show(r, x, y))
        tv.bind("<Motion>", motion, add="+")
        tv.bind("<Leave>", lambda _e: (hide(), state.update(row="")), add="+")
        tv.bind("<ButtonPress>", hide, add="+")

    def _build_right(self):
        f = tk.Frame(self.pw, bg=C["PANEL"])
        self.f_right = f
        # --- fiche
        self.f_item = tk.Frame(f, bg=C["PANEL"])
        hd = tk.Frame(self.f_item, bg=C["PANEL"])
        hd.pack(fill="x", padx=8, pady=(6, 0))
        self.l_icon = tk.Label(hd, text="📝", bg=C["PANEL"], fg=C["HI"], font=fnt("Emoji"))
        self.l_icon.pack(side="left", padx=(0, 4))
        self.v_title = tk.StringVar()
        self.e_title = tk.Entry(hd, textvariable=self.v_title, bg=C["PANEL"], fg=C["HI"], insertbackground=C["HI"],
                                relief="flat", font=fnt("GTitle"), highlightthickness=1, highlightbackground=C["PANEL"],
                                highlightcolor=C["HI"], selectbackground=C["SEL"], selectforeground=C["ON_SEL"])
        self.e_title.configure(width=1)
        self.e_title.bind("<Return>", lambda _e: (self._title_commit(), self.editor.t.focus_set()))
        self.e_title.bind("<FocusOut>", lambda _e: self._title_commit())
        self.e_title.bind("<Escape>", lambda _e: (self.v_title.set(self._loaded_title), self._focus_items()))
        self.e_title.bind("<Control-KeyPress>", self._entry_ctrl)
        Tooltip(self.e_title, "Titre de la fiche (F2) : Entrée pour valider")
        self.b_more = mk_button(hd, "⋯", self._item_more, tip="Toutes les actions")
        self.b_more.pack(side="right", padx=(2, 0))
        self.b_pin = mk_button(hd, "📌", self.toggle_pin, tip="Épingler en haut (Ctrl+P)")
        self.b_pin.pack(side="right", padx=2)
        self.b_fav = mk_button(hd, "☆", self.toggle_fav, tip="Favori (Ctrl+D)")
        self.b_fav.pack(side="right", padx=2)
        self.e_title.pack(side="left", fill="x", expand=True, ipady=2)
        self.l_meta = tk.Label(self.f_item, text="", bg=C["PANEL"], fg=C["DIM"], font=fnt("GSM"), anchor="w", justify="left")
        self.l_meta.pack(fill="x", padx=10)
        self.l_meta.bind("<Configure>", lambda e: self.l_meta.configure(wraplength=max(200, e.width - 4)))
        tg = tk.Frame(self.f_item, bg=C["PANEL"])
        tg.pack(fill="x", padx=8, pady=(2, 4))
        tk.Label(tg, text="🏷", bg=C["PANEL"], fg=C["FG"], font=fnt("GUI")).pack(side="left")
        self.v_tags = tk.StringVar()
        self.e_tags = mk_entry(tg, self.v_tags, 30, "GSM")
        self.e_tags.pack(side="left", fill="x", expand=True, padx=(4, 0), ipady=2)
        self.e_tags.bind("<Return>", lambda _e: self._tags_commit())
        self.e_tags.bind("<FocusOut>", lambda _e: self._tags_commit())
        self.e_tags.bind("<Control-KeyPress>", self._entry_ctrl)
        self.e_tags.bind("<KeyRelease>", self._tags_autocomplete, add="+")
        Tooltip(self.e_tags, "Étiquettes séparées par des virgules (Ctrl+T) ; Tab complète une étiquette existante")
        self.e_tags.bind("<Tab>", self._tags_tab)
        self.nb = ttk.Notebook(self.f_item)
        self.nb.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        self.tab_prev = ScrollFrame(self.nb, bg=C["PANEL"])
        self.tab_body = tk.Frame(self.nb, bg=C["PANEL"])
        self.tab_info = ScrollFrame(self.nb, bg=C["PANEL"])
        self.nb.add(self.tab_prev, text="👁 Aperçu")
        self.nb.add(self.tab_body, text="📝 Notes")
        self.nb.add(self.tab_info, text="🗂 Fiche")
        self.editor = RichEditor(self.tab_body, self, on_change=self._editor_changed)
        self.editor.pack(fill="both", expand=True)
        self.editor.t.bind("<Escape>", lambda _e: (self.editor.flush(), self._focus_items()))
        self.nb.bind("<<NotebookTabChanged>>", lambda _e: self._tab_changed())
        # --- accueil / selection multiple
        self.f_home = ScrollFrame(f, bg=C["PANEL"])
        self._loaded_title = ""
        self._loaded_tags = ""
        self._detail_mode = ""

    def _show_view_widget(self):
        for w in (self.f_list, self.f_cards, self.f_chrono, self.f_results, self.f_trash):
            w.pack_forget()
        mode = self._effective_mode()
        {"list": self.f_list, "cards": self.f_cards, "chrono": self.f_chrono, "results": self.f_results,
         "trash": self.f_trash}[mode].pack(fill="both", expand=True)
        for k, b in self.view_btns.items():
            on = (k == self.view_mode and mode not in ("results", "trash"))
            b._colors = (C["HI"], C["ON_HI"], C["HI_ACT"], C["ON_HI"]) if on else (C["BTN"], C["BTN_FG"], C["HI"], C["ON_HI"])
            b.configure(bg=b._colors[0], fg=b._colors[1])
        searching = self.cur_view == "search"
        trash = self.cur_view == "v:trash"
        fb = self.fbar
        fb.show(self.chk_sub, self.cur_view.startswith("s:"))
        fb.show(self.cb_scope, searching)
        fb.show(self.cb_period, not trash)
        for w in (self.cb_sort, self.cb_type, self.cb_tag):
            fb.show(w, not trash and not (searching and w is self.cb_sort))
        fb.reflow()

    def _effective_mode(self) -> str:
        if self.cur_view == "search":
            return "results"
        if self.cur_view == "v:trash":
            return "trash"
        return self.view_mode

    def _list_columns(self):
        try:
            self._fit_columns()
        except tk.TclError:
            pass
        try:
            w = self.lst.winfo_width()
            multi = self._multi_subject_view()
            if w < 430:
                cols = ("title", "date")
            elif w < 620:
                cols = ("title", "subject", "date") if multi else ("title", "date", "tags")
            else:
                cols = ("title", "subject", "date", "tags") if multi else ("title", "date", "tags")
            if tuple(self.lst["displaycolumns"]) != cols:
                self.lst["displaycolumns"] = cols
            cw = self.chr.winfo_width()
            ccols = ("date",) if cw < 480 else ("date", "subject")
            if tuple(self.chr["displaycolumns"]) != ccols:
                self.chr["displaycolumns"] = ccols
        except tk.TclError:
            pass

    def _fit_columns(self):
        """La colonne Titre prend la place restante : Date et Sujet ne sont jamais coupees a droite."""
        for tv, main in ((self.lst, "title"), (self.chr, "#0"), (self.trv, "#0")):
            W = tv.winfo_width()
            if W < 50:
                continue
            disp = list(tv["displaycolumns"])
            if disp == ["#all"]:
                disp = list(tv["columns"])
            fixed = sum(int(tv.column(c, "width")) for c in disp if c != main)
            want = max(120, W - fixed - 4)
            if abs(int(tv.column(main, "width")) - want) > 2:
                tv.column(main, width=want)

    def _multi_subject_view(self) -> bool:
        if self.cur_view.startswith("s:"):
            s = self.store.subject(self.cur_view[2:])
            return bool(self.v_sub.get() and s and self.store.children(s["id"]))
        return True

    # ------------------------------------------------------------ raccourcis
    def _bind_keys(self):
        b = self.bind
        b("<Control-KeyPress>", self.ctrl_key)
        b("<F1>", lambda _e: self.show_help())
        b("<F2>", lambda _e: self.rename_any())
        b("<F5>", lambda _e: self.refresh_all())
        b("<F11>", lambda _e: self.open_reader())
        b("<F8>", lambda _e: self.open_mindmap())
        b("<Escape>", lambda _e: self.clear_search() if self.v_search.get() else None)
        for seq in ("<Control-plus>", "<Control-equal>", "<Control-KP_Add>"):
            b(seq, lambda _e: self.zoom(1))
        for seq in ("<Control-minus>", "<Control-KP_Subtract>"):
            b(seq, lambda _e: self.zoom(-1))
        b("<Control-MouseWheel>", lambda e: self.zoom(1 if wheel_steps(e) < 0 else -1))

    def _focus_is_text(self) -> bool:
        w = self.focus_get()
        return isinstance(w, (tk.Entry, tk.Text, ttk.Entry, ttk.Combobox)) and w is not self.rt

    def ctrl_key(self, e):
        k = (e.keysym or "").lower()
        shift = bool(e.state & 0x1)
        txt = self._focus_is_text()
        if k == "0" and not txt:
            self.zoom(0)
            return "break"
        acts: Dict[Tuple[str, bool], Callable[[], Any]] = {
            ("n", False): self.new_note, ("n", True): lambda: self.new_subject(None),
            ("l", False): self.add_link_dialog, ("q", True): self.add_quote_dialog,
            ("r", False): self.record_memo, ("o", False): lambda: self.add_files_dialog(None),
            ("i", True): lambda: self.add_files_dialog("image"), ("f", False): self.focus_search,
            ("g", False): self.open_palette, ("1", False): lambda: self.set_view_mode("list"),
            ("2", False): lambda: self.set_view_mode("cards"), ("3", False): lambda: self.set_view_mode("chrono"),
            ("d", False): self.toggle_fav, ("p", False): self.toggle_pin, ("t", False): self.edit_tags,
            ("m", False): lambda: self.move_selected(False), ("e", True): lambda: self.export_dialog(None, False),
            ("s", False): self.backup_now, ("v", True): lambda: self.smart_paste(plain=True),
        }
        if (k, shift) in acts:
            acts[(k, shift)]()
            return "break"
        if k == "v" and not shift and not txt:
            self.smart_paste()
            return "break"
        if k == "z" and not txt:
            self.do_undo()
            return "break"
        if k == "a" and not txt:
            self.select_all()
            return "break"
        return None

    def _entry_ctrl(self, e):
        k = (e.keysym or "").lower()
        if k in ("v", "z", "y", "a", "x", "c", "plus", "minus", "equal") and not (e.state & 0x1 and k == "v"):
            return None
        if k in "ngrolfdpmtse123" or (e.state & 0x1 and k in ("q", "i", "v", "n", "e")):
            if e.widget is self.e_title:
                self._title_commit()
            elif e.widget is self.e_tags:
                self._tags_commit()
            return self.ctrl_key(e)
        return None

    def _type_to_search(self, e):
        if e.state & 0x4 or e.state & 0x20000 or e.state & 0x8:
            return None
        ch = e.char
        if ch and ch.isprintable() and len(ch) == 1 and ch not in " \t":
            self.e_search.focus_set()
            self.e_search.insert("end", ch)
            return "break"
        return None

    def _focus_items(self):
        mode = self._effective_mode()
        w = {"list": self.lst, "cards": self.cv, "chrono": self.chr, "results": self.rt, "trash": self.trv}[mode]
        w.focus_set()
        if mode == "list" and self.visible and not self.lst.selection():
            first = self.lst.get_children("")
            if first:
                self.lst.selection_set(first[0])
                self.lst.focus(first[0])
        elif mode == "results" and self.results and not self.selected:
            self.select_ids([self.results[0]["id"]])
        return "break"

    # ------------------------------------------------------------ glisser-deposer externe
    def _setup_dnd(self):
        try:
            import tkinterdnd2  # type: ignore
            from tkinterdnd2 import DND_FILES, DND_TEXT  # type: ignore
            if not getattr(self, "_dnd_ok", False):
                req = getattr(tkinterdnd2.TkinterDnD, "_require", None) or getattr(tkinterdnd2.TkinterDnD, "require", None)
                req(self)
                self._dnd_ok = True
            for w in (self.lst, self.cv, self.chr, self.rt, self.tree, self.f_home.canvas, self.tab_prev.canvas):
                w.drop_target_register(DND_FILES, DND_TEXT)
                w.dnd_bind("<<Drop>>", self._on_drop)
        except Exception as ex:
            self._dnd_ok = False
            logger.info("glisser-déposer externe indisponible : %s", ex)

    def _on_drop(self, event):
        data = event.data or ""
        try:
            parts = list(self.tk.splitlist(data))
        except tk.TclError:
            parts = [data]
        parts = [p.strip() for p in parts if p and p.strip()]
        if not parts:
            return
        sid = self.current_sid()
        if event.widget is self.tree:
            try:
                iid = self.tree.identify_row(event.y_root - self.tree.winfo_rooty())
                if iid and iid.startswith("s:"):
                    sid = int(iid[2:])
            except Exception:
                pass
        paths = [p for p in parts if os.path.exists(p)]
        if paths and len(paths) == len(parts):
            self.add_paths(paths, sid)
            return
        text = data if not paths else " ".join(p for p in parts if not os.path.exists(p))
        urls = find_urls(text)
        if urls and len(" ".join(urls)) >= len(text.strip()) * 0.8:
            self.add_urls(urls, sid)
        else:
            self.add_text_note(text, sid)
        if paths:
            self.add_paths(paths, sid)

    # ================================================================ arbre des sujets
    def refresh_tree(self):
        tv = self.tree
        st = self.store
        sel = self.cur_view if self.cur_view != "search" else ""
        y = tv.yview()[0] if tv.get_children("") else 0
        tv.delete(*tv.get_children(""))
        tot = st.total_counts()
        n_all = st.stats()["items"]
        counts = {"v:all": n_all,
                  "v:fav": st.q("SELECT COUNT(*) n FROM items WHERE deleted IS NULL AND fav=1")[0]["n"],
                  "v:pin": st.q("SELECT COUNT(*) n FROM items WHERE deleted IS NULL AND pinned=1")[0]["n"],
                  "v:trash": st.q("SELECT COUNT(*) n FROM items WHERE deleted IS NOT NULL")[0]["n"]
                  + st.q("SELECT COUNT(*) n FROM subjects WHERE deleted IS NOT NULL")[0]["n"]}
        tags = st.all_tags()
        for key, ic, lab in SPECIAL_VIEWS:
            n = counts.get(key, len(tags) if key == "v:tags" else "")
            tv.insert("", "end", iid=key, text=f" {ic}  {lab}", values=(n if n not in (0, "") else "",), tags=("special",),
                      open=bool(st.get("tags_open", False)) if key == "v:tags" else False)
            if key == "v:tags":
                for t, c in tags[:300]:
                    tv.insert(key, "end", iid=f"t:{t}", text=f" #{t}", values=(c,), tags=("tag",))
        tv.insert("", "end", iid="sep", text="", tags=("sep",))

        def add(parent_iid, pid):
            for s in st.children(pid):
                iid = f"s:{s['id']}"
                n = tot.get(s["id"], 0)
                tv.insert(parent_iid, "end", iid=iid, text=f"{s['icon'] or '📁'} {s['name']}", values=(n if n else "",),
                          image=self.swatch(s["color"]), open=bool(s["expanded"]),
                          tags=("pinned" if s["pinned"] else "subj",))
                add(iid, s["id"])
        add("", None)
        if sel and tv.exists(sel):
            self._tree_lock = True
            tv.selection_set(sel)
            tv.see(sel)
            self._tree_lock = False
        else:
            tv.selection_remove(tv.selection())
        tv.yview_moveto(y)
        vals = ["Toutes étiquettes"] + [f"#{t} ({c})" for t, c in tags[:200]]
        cur = self.cb_tag.get()
        self.cb_tag.configure(values=vals)
        self._tag_values = [""] + [t for t, _c in tags[:200]]
        if cur not in vals:
            self.cb_tag.current(0)

    def reveal_subject(self, sid: Optional[int], flash: bool = True):
        """Rend un sujet visible dans l'arbre : deplie ses parents, defile jusqu'a lui et le fait clignoter."""
        if not sid:
            return
        tv = self.tree
        iid = f"s:{sid}"
        s = self.store.subject(sid)
        while s and s["parent_id"]:
            if not self.store.subject(s["parent_id"])["expanded"]:
                self.store.update_subject(s["parent_id"], expanded=1)
            s = self.store.subject(s["parent_id"])
        if not tv.exists(iid):
            self.refresh_tree()
        if not tv.exists(iid):
            return
        p = tv.parent(iid)
        while p:
            tv.item(p, open=True)
            p = tv.parent(p)
        tv.see(iid)
        if flash:
            tags = [t for t in tv.item(iid, "tags") if t != "drop"]
            tv.item(iid, tags=tags + ["drop"])
            self.after(1600, lambda: tv.exists(iid) and tv.item(iid, tags=tags))

    def _tree_selected(self, _e=None):
        if getattr(self, "_tree_lock", False):
            return
        sel = self.tree.selection()
        if not sel or sel[0] == "sep" or sel[0] == self.cur_view:
            return
        self.open_view(sel[0])

    def _tree_open(self, state: bool):
        iid = self.tree.focus()
        if iid.startswith("s:"):
            self.store.update_subject(int(iid[2:]), expanded=int(state))
            self.store.version -= 0
        elif iid == "v:tags":
            self.store.set("tags_open", state)

    def open_view(self, key: str, keep_search: bool = False):
        self._commit_pending()
        if not keep_search and self.v_search.get():
            self._search_lock = True
            self.v_search.set("")
            self._search_lock = False
            self._update_placeholder()
        self.cur_view = key
        if key != "search":
            self.view_before_search = key
            self.store.set("last_view", key)
            if self.tree.exists(key) and key not in self.tree.selection():
                self._tree_lock = True
                self.tree.selection_set(key)
                self.tree.see(key)
                self._tree_lock = False
        self.selected = []
        self.cur_item = None
        self._show_view_widget()
        self.refresh_items()

    def current_sid(self, strict: bool = False) -> Optional[int]:
        """Sujet ou ajouter : sujet ouvert, sinon sujet de la fiche choisie, sinon « À classer »."""
        v = self.cur_view if self.cur_view != "search" else self.view_before_search
        if v.startswith("s:") and self.store.subject(v[2:]):
            return int(v[2:])
        if self.cur_item:
            it = self.store.item(self.cur_item)
            if it and self.store.subject(it["subject_id"]):
                return it["subject_id"]
        if strict:
            return None
        return self.store.inbox_subject()

    # ================================================================ fiches : collecte et tri
    def _period_since(self) -> str:
        k = PERIODS[max(0, self.cb_period.current())][0]
        if not k:
            return ""
        if k == "365":
            return f"{dt.date.today().year}-01-01"
        return (dt.date.today() - dt.timedelta(days=int(k))).isoformat()

    def _filter_type(self) -> str:
        return TYPE_FILTERS[max(0, self.cb_type.current())][0]

    def _filter_tag(self) -> str:
        i = self.cb_tag.current()
        vals = getattr(self, "_tag_values", [""])
        return vals[i] if 0 <= i < len(vals) else ""

    def collect_items(self) -> List[Dict[str, Any]]:
        st = self.store
        v = self.cur_view
        if v.startswith("s:"):
            sid = int(v[2:])
            sids = [sid] + (st.descendants(sid) if self.v_sub.get() else [])
            items = st.items_in(sids)
        elif v == "v:fav":
            items = st.items_where("fav=1")
        elif v == "v:pin":
            items = st.items_where("pinned=1")
        elif v == "v:recent":
            items = st.items_where("1=1 ORDER BY COALESCE(opened, updated, created) DESC", limit=150)
        elif v == "v:tags":
            items = st.items_where("tags<>''")
        elif v.startswith("t:"):
            tg = norm(v[2:])
            items = [r for r in st.items_where("tags<>''") if tg in [norm(t) for t in tag_list(r["tags"])]]
        else:
            items = st.items_where("1=1")
        typ = self._filter_type()
        if typ:
            items = [r for r in items if r["type"] == typ]
        tg = self._filter_tag()
        if tg:
            items = [r for r in items if norm(tg) in [norm(t) for t in tag_list(r.get("tags") or "")]]
        since = self._period_since()
        if since:
            items = [r for r in items if (r.get("event_date") or r.get("created") or "") >= since]
        return self.sort_items(items, "recentopen" if v == "v:recent" and self.sort == "manual" else self.sort)

    def sort_items(self, items: List[Dict[str, Any]], how: str) -> List[Dict[str, Any]]:
        def evd(r):
            return r.get("event_date") or r.get("created") or ""
        if how == "recent":
            items.sort(key=lambda r: r.get("created") or "", reverse=True)
        elif how == "old":
            items.sort(key=lambda r: r.get("created") or "")
        elif how == "title":
            items.sort(key=lambda r: norm(r.get("title") or ""))
        elif how == "type":
            items.sort(key=lambda r: (TYPE_ORDER.index(r["type"]) if r["type"] in TYPE_ORDER else 99, norm(r.get("title") or "")))
        elif how == "event":
            items.sort(key=evd, reverse=True)
        elif how == "subject":
            items.sort(key=lambda r: (norm(self.store.subject_path(r["subject_id"])), float(r.get("sort") or 0)))
        elif how == "recentopen":
            items.sort(key=lambda r: r.get("opened") or r.get("updated") or "", reverse=True)
        else:
            multi = self._multi_subject_view() and self.cur_view.startswith("s:")
            if multi:
                order = {sid: k for k, sid in enumerate(self.subject_order())}
                items.sort(key=lambda r: (order.get(r["subject_id"], 9999), float(r.get("sort") or 0)))
            elif self.cur_view.startswith("s:"):
                items.sort(key=lambda r: float(r.get("sort") or 0))
            else:
                items.sort(key=lambda r: r.get("updated") or "", reverse=True)
        items.sort(key=lambda r: -int(r.get("pinned") or 0))
        return items

    def _sort_changed(self):
        self.sort = SORTS[max(0, self.cb_sort.current())][0]
        self.store.set("sort", self.sort)
        self.refresh_items()

    def _heading_sort(self, col: str):
        nxt = {"title": "title", "subject": "subject", "date": "old" if self.sort == "recent" else "recent", "tags": "type"}[col]
        if col == "subject":
            self.sort = "subject"
        else:
            self.sort = nxt
            keys = [k for k, _l in SORTS]
            if nxt in keys:
                self.cb_sort.current(keys.index(nxt))
        self.refresh_items()

    def _sub_changed(self):
        self.store.set("include_sub", bool(self.v_sub.get()))
        self.refresh_items()

    def set_view_mode(self, mode: str):
        if mode not in ("list", "cards", "chrono"):
            return
        self.view_mode = mode
        self.v_view.set(mode)
        self.store.set("view_mode", mode)
        if self.cur_view in ("search", "v:trash"):
            self.open_view(self.view_before_search if self.view_before_search not in ("search", "v:trash") else "v:all")
            return
        keep = list(self.selected)
        self._show_view_widget()
        self.fill_view()
        if keep:
            self.select_ids(keep, see=True)

    def _view_from_var(self):
        self.set_view_mode(self.v_view.get())

    # ================================================================ rafraichissement
    def refresh_all(self, first: bool = False):
        self._commit_pending()
        keep = list(self.selected)
        self.refresh_tree()
        if not self._view_valid(self.cur_view) and self.cur_view != "search":
            self.cur_view = "v:all"
        self._show_view_widget()
        self.refresh_items(keep=keep)
        if first:
            if self.cur_view.startswith("s:") and not keep:
                its = self.visible
                pin = [r for r in its if r.get("pinned")]
                if pin and self.store.subject(self.cur_view[2:]) and self.store.subject(self.cur_view[2:])["name"] == "Bienvenue":
                    self.select_ids([pin[0]["id"]])
            self.set_status(f"Grimoire prêt : {self.store.stats()['items']} fiche(s) dans {len(self.store.subjects())} sujets.  "
                            f"Données : {Paths.data}", "DIM")

    def refresh_items(self, keep: Optional[List[int]] = None):
        if self.cur_view == "search":
            self.do_search(keep=keep)
            return
        if self.cur_view == "v:trash":
            self.fill_trash()
            self._header()
            self.update_detail()
            return
        self.visible = self.collect_items()
        self._header()
        self.fill_view()
        ids = {r["id"] for r in self.visible}
        keep = [i for i in (keep or []) if i in ids]
        if keep:
            self.select_ids(keep, see=True)
        else:
            self.selected = []
            self.update_detail()

    def _header(self):
        st = self.store
        v = self.cur_view
        color = C["HI"]
        if v.startswith("s:") and st.subject(v[2:]):
            s = st.subject(v[2:])
            title = f"{s['icon'] or '📁'}  {st.subject_path(s['id'])}"
            color = s["color"] or C["HI"]
        elif v == "search":
            title = f"🔍  Recherche : « {self.v_search.get().strip()} »"
        elif v.startswith("t:"):
            title = f"🏷  Étiquette #{v[2:]}"
        else:
            title = next((f"{ic}  {lab}" for k, ic, lab in SPECIAL_VIEWS if k == v), "Grimoire")
        self.colorbar.configure(bg=color)
        w = max(200, self.f_center.winfo_width() - 30)
        self.l_view.configure(text=self.fit_text(title, "GTitle", w, 2))
        n = len(self.results) if v == "search" else (len(self.visible) if v != "v:trash" else self._trash_count)
        self.l_vcount.configure(text=f"{n} fiche{'s' if n > 1 else ''}" if v != "v:trash" else f"{n} élément(s)")
        self.fbar.reflow()
        self.l_count.configure(text=f"{st.stats()['items']} fiches · {len(st.subjects())} sujets")

    def fill_view(self):
        mode = self._effective_mode()
        if mode == "list":
            self.fill_list()
        elif mode == "cards":
            self.fill_cards()
        elif mode == "chrono":
            self.fill_chrono()

    def _row_title(self, r: Dict[str, Any]) -> str:
        t = TYPES.get(r["type"], TYPES["file"])
        pre = ("📌" if r.get("pinned") else "") + ("★ " if r.get("fav") else "")
        m = self.store.meta(r)
        pend = " ⏳" if m.get("pending") else ""
        return f"{pre}{t['icon']}  {r.get('title') or '(sans titre)'}{pend}"

    def _row_date(self, r: Dict[str, Any]) -> str:
        if r.get("event_date"):
            return fmt_date(r["event_date"], False)
        return fmt_date(r.get("created") or "", False)

    def fill_list(self):
        lv = self.lst
        lv.delete(*lv.get_children(""))
        for r in self.visible:
            s = self.store.subject(r["subject_id"])
            lv.insert("", "end", iid=f"i:{r['id']}", values=(self._row_title(r), s["name"] if s else "", self._row_date(r),
                                                             ", ".join(tag_list(r.get("tags") or ""))),
                      tags=("fav",) if r.get("fav") else ())
        self._list_columns()
        self._empty_hint(lv, not self.visible)

    def _empty_hint(self, widget, empty: bool):
        lab = getattr(widget, "_hint", None)
        if lab is None:
            lab = tk.Label(widget, bg=C["CARD"], fg=C["DIM"], font=fnt("GUI"), justify="center")
            widget._hint = lab
        if empty:
            v = self.cur_view
            if v.startswith("s:"):
                msg = ("Ce sujet est vide.\n\n＋ Ajouter, Ctrl+V pour coller un lien, du texte ou une image,\n"
                       "ou glisse ici des fichiers, des liens ou du texte.")
            elif self._filter_type() or self._filter_tag() or self._period_since():
                msg = "Aucune fiche ne correspond aux filtres."
            else:
                msg = "Rien ici pour l'instant."
            lab.configure(text=msg, wraplength=max(200, widget.winfo_width() - 40))
            lab.place(relx=0.5, rely=0.3, anchor="center")
        else:
            lab.place_forget()

    def fill_chrono(self):
        tv = self.chr
        tv.delete(*tv.get_children(""))
        items = sorted(self.visible, key=lambda r: r.get("event_date") or r.get("created") or "", reverse=True)
        groups: Dict[str, List[Dict[str, Any]]] = {}
        order: List[str] = []
        for r in items:
            d = (r.get("event_date") or r.get("created") or "")[:7] or "????"
            if d not in groups:
                groups[d] = []
                order.append(d)
            groups[d].append(r)
        for m in order:
            lab = month_label(m + "-01") if m != "????" else "Sans date"
            tv.insert("", "end", iid=f"m:{m}", text=f"📅  {lab[:1].upper() + lab[1:]}",
                      values=(f"{len(groups[m])} fiche{'s' if len(groups[m]) > 1 else ''}", ""), open=True, tags=("month",))
            for r in groups[m]:
                s = self.store.subject(r["subject_id"])
                tv.insert(f"m:{m}", "end", iid=f"i:{r['id']}", text=self._row_title(r),
                          values=(self._row_date(r), s["name"] if s else ""), tags=("fav",) if r.get("fav") else ())
        self._list_columns()
        self._empty_hint(tv, not items)

    # ------------------------------------------------------------ cartes
    def _cards_resized(self):
        w = self.cv.winfo_width()
        if getattr(self, "_cards_w", 0) != w and self._effective_mode() == "cards":
            self._cards_w = w
            if getattr(self, "_cards_job", None):
                self.after_cancel(self._cards_job)
            self._cards_job = self.after(80, self.fill_cards)

    # ================================================================ 1.5 : cartes illustrees
    def _gx_thumb_src(self, r: Dict[str, Any]) -> str:
        """vignette d'une fiche : image/media de la fiche, sinon apercu de lien en cache, sinon ''."""
        if r.get("thumb"):
            return r["thumb"]
        if r["type"] == "image" and r.get("file"):
            return r["file"]
        for u in gx_item_urls(r)[:3]:
            p = gx_preview_image(u)
            if p:
                return p
            a = gx_archive_get(self.store, u)
            fo = gx_archive_folder(a)
            cap = (a or {}).get("info", {}).get("capture") if a else ""
            if fo and cap and os.path.isfile(os.path.join(fo, cap)):
                return os.path.join(fo, cap)
        return ""

    def _card_dims(self) -> Tuple[int, int, int, int]:
        W = max(200, self.cv.winfo_width())
        base = 210 + 10 * int(self.store.get("font_delta", 0) or 0)
        cols = max(1, (W - 12) // (base + 14))
        cw = (W - 12 - (cols - 1) * 14) // cols
        thumb_h = int(cw * 0.50)
        lh = tkfont.Font(font=fnt("GCard")).metrics("linespace")
        lh2 = tkfont.Font(font=fnt("GCardD")).metrics("linespace")
        ch = thumb_h + 2 * lh + 3 * lh2 + 34
        return cols, cw, ch, thumb_h

    def fill_cards(self):
        cv = self.cv
        cv.delete("all")
        self.card_boxes = []
        self._card_imgs: List[Any] = []
        self._card_hover = None
        items = self.visible[:600]
        cols, cw, ch, th = self._card_dims()
        lh = tkfont.Font(font=fnt("GCard")).metrics("linespace")
        lh2 = tkfont.Font(font=fnt("GCardD")).metrics("linespace")
        pending: List[Tuple[int, str, int, int, int, int]] = []
        for k, r in enumerate(items):
            col, row = k % cols, k // cols
            x0 = 6 + col * (cw + 14)
            y0 = 8 + row * (ch + 14)
            x1, y1 = x0 + cw, y0 + ch
            iid = r["id"]
            tg = (f"c{iid}", "cardall")
            sel = iid in self.selected
            s = self.store.subject(r["subject_id"])
            scol = (s["color"] if s else "") or C["HI"]
            cv.create_rectangle(x0 + 3, y0 + 3, x1 + 3, y1 + 3, fill=gx_mix(C["BG"], "#000000", 0.35), width=0, tags=tg + ("shadow",))
            cv.create_rectangle(x0, y0, x1, y1, fill=C["CARD"], outline=C["HI"] if sel else C["LINE"], width=3 if sel else 1,
                                tags=("card",) + tg)
            cv.create_rectangle(x0 + 1, y0 + 1, x1 - 1, y0 + 5, fill=scol, width=0, tags=tg)
            t = TYPES.get(r["type"], TYPES["file"])
            ty0 = y0 + 8
            # vignette (chargee en differe) ou tuile coloree
            cv.create_rectangle(x0 + 6, ty0, x1 - 6, ty0 + th, fill=gx_mix(C["PANEL"], scol, 0.22), width=0, tags=tg + (f"th{iid}",))
            cv.create_text((x0 + x1) // 2, ty0 + th // 2 - 6, text=(s["icon"] if s and s.get("icon") else t["icon"]),
                           font=fnt("EmojiBig"), fill=scol, tags=tg + (f"ic{iid}",))
            src = self._gx_thumb_src(r)
            if src:
                pending.append((iid, src, (x0 + x1) // 2, ty0 + th // 2, cw - 12, th))
            # badge de type + etoile
            badge = f" {t['icon']} {t['label']} "
            bt = cv.create_text(x0 + 12, ty0 + 6, text=badge, anchor="nw", fill=C["ON_HI"], font=fnt("GCardD"), tags=tg)
            bb = cv.bbox(bt)
            if bb:
                br = cv.create_rectangle(bb[0] - 2, bb[1] - 1, bb[2] + 2, bb[3] + 1, fill=scol, outline="", tags=tg)
                cv.tag_lower(br, bt)
            star = cv.create_text(x1 - 12, ty0 + 4, text="★" if r.get("fav") else "☆", anchor="ne",
                                  fill=C["HI"] if r.get("fav") else C["DIM"], font=("Segoe UI Symbol", 15), tags=tg + ("star", f"st{iid}"))
            _ = star
            if r.get("pinned"):
                cv.create_text(x1 - 34, ty0 + 6, text="📌", anchor="ne", font=fnt("GCardD"), tags=tg)
            perm = any(gx_archive_folder(gx_archive_get(self.store, u)) for u in gx_item_urls(r)[:4]) if (r.get("url") or "http" in (r.get("body_text") or "")) else False
            if perm:
                pt = cv.create_text(x0 + 12, ty0 + th - 6, text=" ✔ Permanent ", anchor="sw", fill="#FFFFFF", font=fnt("GCardD"), tags=tg)
                pb = cv.bbox(pt)
                if pb:
                    pr = cv.create_rectangle(pb[0] - 2, pb[1] - 1, pb[2] + 2, pb[3] + 1, fill="#2E9E5B", outline="", tags=tg)
                    cv.tag_lower(pr, pt)
            yt = ty0 + th + 6
            title = r.get("title") or "(sans titre)"
            cv.create_text(x0 + 8, yt, text=self.fit_text(title, "GCard", cw - 16, 2), anchor="nw",
                           fill=C["HI"] if r.get("fav") else C["TEXT"], font=fnt("GCard"), width=cw - 14, tags=tg)
            ym = yt + 2 * lh + 2
            meta = f"🗓 {self._row_date(r)}"
            if self._multi_subject_view() and s:
                meta += f"  ·  {s.get('icon') or ''} {s['name']}"
            cv.create_text(x0 + 8, ym, text=self.fit_text(meta, "GCardD", cw - 16), anchor="nw", fill=C["DIM"], font=fnt("GCardD"), tags=tg)
            desc = self.store.meta(r).get("description") or ""
            if not desc:
                desc = r.get("body_text") or r.get("extracted") or r.get("url") or ""
            if r["type"] == "quote" and desc:
                desc = "« " + desc.strip() + " »"
            if desc:
                cv.create_text(x0 + 8, ym + lh2 + 2, text=self.fit_text(desc, "GCardD", cw - 16, 2), anchor="nw",
                               fill=C["QUOTE"] if r["type"] == "quote" else C["TEXT"], font=fnt("GCardD"), tags=tg)
            self.card_boxes.append((x0, y0, x1, y1, iid))
        rows = (len(items) + cols - 1) // cols
        total_h = 8 + rows * (ch + 14)
        if len(self.visible) > len(items):
            cv.create_text(12, total_h + 4, anchor="nw", fill=C["WARN"], font=fnt("GSM"),
                           text=f"… {len(self.visible) - len(items)} fiche(s) de plus : utilise la vue Liste ou un filtre.")
            total_h += 30
        cv.configure(scrollregion=(0, 0, max(1, cv.winfo_width()), max(total_h, cv.winfo_height())))
        self._empty_hint(cv, not items)
        # vignettes en differe (les cartes visibles d'abord) : l'affichage reste instantane meme avec 150+ fiches
        top = cv.canvasy(0)
        pending.sort(key=lambda p: (0 if p[3] >= top - 50 and p[3] <= top + cv.winfo_height() + 200 else 1, p[3]))
        self._gx_thumb_gen = getattr(self, "_gx_thumb_gen", 0) + 1
        gen = self._gx_thumb_gen
        self.after(15, lambda: self._gx_load_thumbs(pending, gen))
        # apparition en douceur (seulement quand la liste change, pas a chaque clic)
        sig = (self.cur_view, tuple(r["id"] for r in items[:60]), cols)
        if self.store.get("animations", True) and sig != getattr(self, "_gx_card_sig", None) and items:
            self._gx_fade(rows_visible=max(1, int(cv.winfo_height() // (ch + 14)) + 1), cols=cols, ids=[r["id"] for r in items])
        self._gx_card_sig = sig

    def _gx_load_thumbs(self, pending, gen):
        if gen != getattr(self, "_gx_thumb_gen", 0) or self._effective_mode() != "cards":
            return
        t0 = time.time()
        while pending and time.time() - t0 < 0.03:
            iid, src, cx, cy, w, h = pending.pop(0)
            img = self.photo(src, w, h)
            if img is None:
                continue
            self._card_imgs.append(img)
            self.cv.delete(f"ic{iid}")
            o = self.cv.create_image(cx, cy, image=img, tags=(f"c{iid}", "cardall", f"im{iid}"))
            above = self.cv.find_withtag(f"th{iid}")
            if above:
                self.cv.tag_raise(o, above[0])
        if pending:
            self.after(10, lambda: self._gx_load_thumbs(pending, gen))

    def _gx_fade(self, rows_visible: int, cols: int, ids: List[int]):
        """les cartes du haut glissent et apparaissent rangee par rangee (~0,4 s)."""
        cv = self.cv
        n = min(len(ids), rows_visible * cols)
        first = ids[:n]
        for i in first:
            cv.itemconfigure(f"c{i}", state="hidden")
            cv.move(f"c{i}", 0, 14)

        def show(k: int, step: int):
            if not cv.winfo_exists():
                return
            row = first[k * cols:(k + 1) * cols]
            if not row:
                return
            for i in row:
                if step == 0:
                    cv.itemconfigure(f"c{i}", state="normal")
                cv.move(f"c{i}", 0, -3.5)
            if step < 3:
                self.after(22, lambda: show(k, step + 1))
            if step == 1:
                self.after(10, lambda: show(k + 1, 0))
        show(0, 0)

    def _card_motion(self, e):
        iid = self._card_at(e.x, e.y)
        old = getattr(self, "_card_hover", None)
        if iid == old:
            return
        cv = self.cv
        for i, on in ((old, False), (iid, True)):
            if i is None:
                continue
            rid = next((o for o in cv.find_withtag(f"c{i}") if "card" in cv.gettags(o)), None)
            if rid:
                sel = i in self.selected
                cv.itemconfigure(rid, fill=gx_mix(C["CARD"], C["HI"], 0.10) if on else C["CARD"],
                                 outline=C["HI"] if sel else (C["FG"] if on else C["LINE"]), width=3 if sel else (2 if on else 1))
        self._card_hover = iid
        cv.configure(cursor="hand2" if iid else "")

    def _card_star_click(self, e) -> bool:
        cx, cy = self.cv.canvasx(e.x), self.cv.canvasy(e.y)
        for o in self.cv.find_overlapping(cx - 2, cy - 2, cx + 2, cy + 2):
            tags = self.cv.gettags(o)
            if "star" in tags:
                iid = int(next(t for t in tags if t.startswith("st"))[2:])
                it = self.store.item(iid)
                if it:
                    self.store.update_item(iid, touch=False, fav=0 if it.get("fav") else 1)
                    self.set_status("★ Ajoutée aux favoris." if not it.get("fav") else "☆ Retirée des favoris.", "OK")
                    self.refresh_items(keep=[iid])
                return True
        return False

    def _gx_open_pulse(self, iid: int):
        """petite pulsation de la carte a l'ouverture d'une fiche."""
        if not self.store.get("animations", True) or self._effective_mode() != "cards":
            return
        cv = self.cv
        rid = next((o for o in cv.find_withtag(f"c{iid}") if "card" in cv.gettags(o)), None)
        if not rid:
            return
        seq = [0.35, 0.6, 0.35, 0.15, 0.0]

        def go(k):
            if k >= len(seq) or not cv.winfo_exists():
                return
            try:
                cv.itemconfigure(rid, fill=gx_mix(C["CARD"], C["HI"], seq[k]))
            except tk.TclError:
                return
            self.after(45, lambda: go(k + 1))
        go(0)

    def toggle_animations(self):
        on = bool(self.v_anim.get())
        self.store.set("animations", on)
        self.set_status("✨ Animations activées." if on else "Animations désactivées (tout s'affiche d'un coup).", "OK")

    def open_mindmap(self):
        mm = getattr(self, "_mindmap", None)
        if mm is not None:
            try:
                if mm.winfo_exists():
                    mm.lift()
                    mm.focus_force()
                    return
            except tk.TclError:
                pass
        self._mindmap = MindMap(self)

    # ================================================================ 1.5 : apercus de liens + Archiveur
    def gx_link_section(self, f, it: Dict[str, Any], W: int):
        urls = gx_item_urls(it)
        if not urls:
            return
        self._section(f, "🔗 LIENS DE LA FICHE" if len(urls) > 1 else "🔗 LIEN DE LA FICHE")
        self._gx_link_rows = getattr(self, "_gx_link_rows", {})
        self._gx_link_rows = {}
        for u in urls:
            box = tk.Frame(f, bg=C["CARD"], highlightthickness=1, highlightbackground=C["LINE"])
            box.pack(fill="x", padx=12, pady=4)
            self._gx_link_rows[u] = (box, it["id"], W)
            self._gx_fill_link(u)
            pv = gx_preview_cached(u)
            if not pv or (not pv.get("ok") and time.time() - float(pv.get("t") or 0) > 3600):
                self.run_job(lambda uu=u: gx_fetch_preview(uu), lambda _r, uu=u: self._gx_fill_link(uu), "")

    def _gx_fill_link(self, url: str):
        rows = getattr(self, "_gx_link_rows", {})
        if url not in rows:
            return
        box, iid, W = rows[url]
        try:
            if not box.winfo_exists():
                return
        except tk.TclError:
            return
        for w in box.winfo_children():
            w.destroy()
        pv = gx_preview_cached(url) or {}
        a = gx_archive_get(self.store, url)
        folder = gx_archive_folder(a)
        bg = C["CARD"]
        top = tk.Frame(box, bg=bg)
        top.pack(fill="x", padx=6, pady=6)
        img = None
        ip = gx_preview_image(url)
        if not ip and folder and (a or {}).get("info", {}).get("capture"):
            ip = os.path.join(folder, a["info"]["capture"])
        if ip:
            img = self.photo(ip, 150, 96)
        if img is not None:
            lab = tk.Label(top, image=img, bg=bg, cursor="hand2", bd=0)
            lab.pack(side="left", padx=(0, 8))
            self._prev_imgs.append(img)
            lab.bind("<Button-1>", lambda _e: self._gx_watch(url) if folder else open_url(url))
            Tooltip(lab, "Clic : regarder la copie permanente" if folder else "Clic : ouvrir dans le navigateur")
        txt = tk.Frame(top, bg=bg)
        txt.pack(side="left", fill="x", expand=True)
        site = pv.get("site") or domain_of(url)
        mk_label(txt, ("🎬 " if pv.get("video") or is_video_url(url) else "🌐 ") + str(site), "DIM", "GSM", bg=bg).pack(anchor="w")
        title = pv.get("title") or (a or {}).get("info", {}).get("title") or url
        mk_link(txt, self.fit_text(title, "GUIB", max(120, W - 200), 2), url, bg=bg, font_name="GUIB", wrap=max(120, W - 190)).pack(anchor="w")
        if pv.get("desc"):
            mk_label(txt, self.fit_text(pv["desc"], "GSM", max(120, W - 200), 3), "TEXT", "GSM", bg=bg, justify="left",
                     wraplength=max(120, W - 190)).pack(anchor="w")
        if not pv:
            mk_label(txt, "⏳ Aperçu en préparation…", "DIM", "GSM", bg=bg).pack(anchor="w")
        bar = tk.Frame(box, bg=bg)
        bar.pack(fill="x", padx=6, pady=(0, 6))
        prog = getattr(self, "_gx_prog", {}).get(url)
        if prog is not None:
            self._gx_progress_bar(bar, url)
        elif folder:
            tk.Label(bar, text=f"✔ Permanent · dans l'Archiveur · {str((a or {}).get('updated') or '')[:10]}", bg="#2E9E5B",
                     fg="#FFFFFF", font=fnt("GSM"), padx=6).pack(anchor="w", pady=(0, 3))
            bar = tk.Frame(bar, bg=bg)
            bar.pack(fill="x")
            mk_button(bar, "▶ Regarder", lambda: self._gx_watch(url), "accent",
                      tip="Regarder la copie gardée sur ton PC (marche même si le lien original disparaît)").pack(side="left", padx=(0, 4))
            mk_button(bar, "💾 Copie locale", lambda: self._gx_local(url),
                      tip="Ouvrir la page de l'archive (index.html) dans le navigateur").pack(side="left", padx=2)
            mk_button(bar, "🗂 Dossier", lambda: reveal_in_explorer(folder), tip="Le dossier de la copie (Archiveur, collection « Grimoire »)").pack(
                side="left", padx=2)
        else:
            err = (a or {}).get("status") == "erreur"
            ok = bool(gx_archiveur_dir())
            b = mk_button(bar, "↻ Réessayer" if err else "📦 Rendre permanent", lambda: self.gx_make_permanent(url, iid), "accent",
                          tip=("Envoie le lien à l'Archiveur : une copie reste sur ton PC, même si le lien disparaît" if ok else
                               "L'Archiveur (archiveur5.py) est introuvable : bouton indisponible"))
            b.pack(side="left")
            if not ok:
                b.configure(state="disabled")
            if err:
                mk_label(bar, "⚠ La copie n'a pas marché (connexion ?) — tu peux réessayer.", "WARN", "GSM", bg=bg).pack(side="left", padx=6)
            mk_button(bar, "🌐 Ouvrir", lambda: open_url(url), tip="Ouvrir le lien dans le navigateur").pack(side="left", padx=4)
            mk_button(bar, "📋 Copier", lambda: (copy_to_clipboard(self, url), self.set_status("Lien copié.", "OK")),
                      tip="Copier le lien").pack(side="left", padx=2)

    def _gx_progress_bar(self, bar, url: str):
        bg = C["CARD"]
        cv = tk.Canvas(bar, height=16, bg=C["PANEL"], highlightthickness=0, bd=0)
        cv.pack(fill="x", pady=(2, 2))
        lab = mk_label(bar, "", "FG", "GSM", bg=bg)
        lab.pack(anchor="w")
        state = {"ph": 0.0}

        def tick():
            try:
                if not cv.winfo_exists():
                    return
            except tk.TclError:
                return
            p = getattr(self, "_gx_prog", {}).get(url)
            if p is None:
                return
            w = max(50, cv.winfo_width())
            cv.delete("all")
            pct = p.get("pct")
            if pct is None:   # barre vivante (indeterminee)
                state["ph"] = (state["ph"] + 7) % (w + 120)
                x = state["ph"] - 120
                cv.create_rectangle(max(0, x), 2, min(w, x + 120), 14, fill=C["HI"], width=0)
            else:
                cv.create_rectangle(0, 2, w * min(100, pct) / 100, 14, fill=C["HI"], width=0)
                state["ph"] = (state["ph"] + 9) % 40
                for xx in range(int(-40 + state["ph"]), int(w * min(100, pct) / 100), 40):
                    cv.create_line(xx, 14, xx + 12, 2, fill=gx_mix(C["HI"], "#FFFFFF", 0.5), width=4)
            lab.configure(text=gx_cheer(pct, p.get("log", "")))
            self.after(60 if self.store.get("animations", True) else 400, tick)
        tick()

    def gx_make_permanent(self, url: str, iid: Optional[int]):
        self._gx_prog = getattr(self, "_gx_prog", {})
        if url in self._gx_prog:
            return
        if not gx_archiveur_dir():
            messagebox.showinfo(APP_NAME, "L'Archiveur (archiveur5.py) est introuvable dans le dossier Padawan.\n"
                                          "Astuce : « 🌐 Capturer la page » garde quand même une copie hors ligne.", parent=self)
            return
        prog = self._gx_prog[url] = {"pct": None, "log": ""}
        gx_archive_set(self.store, url, iid, "copie")
        self._gx_fill_link(url)
        self.set_status("📦 Envoi à l'Archiveur… tu peux continuer à travailler.", "FG")

        def ev(k, v):
            prog[k] = v

        def work():
            r = gx_archive_via_archiveur(url, ev)
            folder = os.path.join(r["root"], r["folder"])
            fi = gx_folder_info(folder)
            if not fi["nfiles"]:
                raise RuntimeError("dossier d'archive introuvable")
            fi.update({"source": "grimoire", "dup": r.get("dup"), "copie_le": now_iso()})
            return r, fi

        def finish(res):
            self._gx_prog.pop(url, None)
            if isinstance(res, Exception) or not res:
                gx_archive_set(self.store, url, iid, "erreur")
                logger.warning("rendre permanent %s : %s", url, res)
                self.set_status("⚠ Copie impossible pour l'instant (connexion ?). Le lien reste dans la fiche ; tu pourras réessayer.", "WARN")
            else:
                r, fi = res
                gx_archive_set(self.store, url, iid, "permanent", r["root"], r["folder"], fi)
                self.set_status("✔ Lien rendu permanent : la copie est sur ton PC (Archiveur, collection « Grimoire »).", "OK")
                self._gx_toast("✔ Permanent ! Même si le lien disparaît, ta copie reste dans ton Grimoire.")
            self._gx_fill_link(url)
            if self._effective_mode() == "cards":
                self.fill_cards()
                if self.selected:
                    self.select_ids(self.selected)

        def job():
            try:
                out = work()
            except Exception as ex:
                logger.error("Archiveur : %s", traceback.format_exc())
                out = ex
            self.post(lambda: finish(out))
        threading.Thread(target=job, daemon=True).start()

    def _gx_watch(self, url: str):
        a = gx_archive_get(self.store, url)
        folder = gx_archive_folder(a)
        if not folder:
            open_url(url)
            return
        info = (a or {}).get("info") or {}
        main = info.get("main") or gx_folder_info(folder)["main"]
        p = os.path.join(folder, main) if main else folder
        open_path(p if os.path.exists(p) else folder)

    def _gx_local(self, url: str):
        a = gx_archive_get(self.store, url)
        folder = gx_archive_folder(a)
        if folder:
            p = os.path.join(folder, "index.html")
            open_path(p if os.path.isfile(p) else folder)

    def _gx_toast(self, msg: str, seconds: float = 3.5):
        try:
            t = tk.Toplevel(self)
            t.overrideredirect(True)
            t.configure(bg=C["HI"])
            tk.Label(t, text=msg, bg=C["HI"], fg=C["ON_HI"], font=fnt("GUIB"), padx=16, pady=8).pack()
            t.update_idletasks()
            x = self.winfo_rootx() + (self.winfo_width() - t.winfo_reqwidth()) // 2
            y = self.winfo_rooty() + self.winfo_height() - t.winfo_reqheight() - 60
            t.geometry(f"+{x}+{y}")
            t.attributes("-topmost", True)
            if self.store.get("animations", True):
                for k in range(6):
                    self.after(k * 30, lambda a=(k + 1) / 6: t.winfo_exists() and t.attributes("-alpha", a))
            self.after(int(seconds * 1000), t.destroy)
        except tk.TclError:
            pass

    def _gx_external_changes(self):
        """une autre application (ex. l'Archiveur) a ecrit dans grimoire.db : on rafraichit."""
        try:
            v = self.store.q("PRAGMA data_version")[0][0]
        except Exception:
            return
        old = getattr(self, "_gx_dv", None)
        self._gx_dv = v
        if old is not None and v != old:
            self.store._touch()
            self.refresh_all()

    def _card_at(self, x: int, y: int) -> Optional[int]:
        cx, cy = self.cv.canvasx(x), self.cv.canvasy(y)
        for x0, y0, x1, y1, iid in self.card_boxes:
            if x0 <= cx <= x1 and y0 <= cy <= y1:
                return iid
        return None

    def _card_press(self, e):
        self.cv.focus_set()
        if self._card_star_click(e):
            return
        iid = self._card_at(e.x, e.y)
        if iid is None:
            self.select_ids([])
            return
        ids = [r["id"] for r in self.visible]
        if e.state & 0x1 and self.anchor in ids:
            a, b = ids.index(self.anchor), ids.index(iid)
            self.select_ids(ids[min(a, b):max(a, b) + 1], anchor=False)
        elif e.state & 0x4:
            cur = list(self.selected)
            if iid in cur:
                cur.remove(iid)
            else:
                cur.append(iid)
            self.select_ids(cur, anchor=False)
        else:
            if iid not in self.selected or len(self.selected) == 1:
                self.select_ids([iid])
        self.press = {"x": e.x_root, "y": e.y_root, "ids": list(self.selected), "src": "items"}

    def _card_double(self, e):
        iid = self._card_at(e.x, e.y)
        if iid:
            self._gx_open_pulse(iid)
            self.open_item(iid)

    def _card_menu(self, e):
        iid = self._card_at(e.x, e.y)
        if iid and iid not in self.selected:
            self.select_ids([iid])
        if iid:
            self.item_menu(e)
        else:
            self.view_menu(e)

    def _card_key(self, key: str):
        ids = [r["id"] for r in self.visible[:400]]
        if not ids:
            return "break"
        cols = self._card_dims()[0]
        cur = ids.index(self.selected[0]) if self.selected and self.selected[0] in ids else -1
        step = {"Left": -1, "Right": 1, "Up": -cols, "Down": cols}.get(key, 0)
        if key == "Home":
            n = 0
        elif key == "End":
            n = len(ids) - 1
        else:
            n = max(0, min(len(ids) - 1, cur + step)) if cur >= 0 else 0
        self.select_ids([ids[n]], see=True)
        return "break"

    def _card_see(self, iid: int):
        for x0, y0, x1, y1, i in self.card_boxes:
            if i == iid:
                total = float(self.cv.cget("scrollregion").split()[3]) if self.cv.cget("scrollregion") else 1
                top, bot = self.cv.canvasy(0), self.cv.canvasy(self.cv.winfo_height())
                if y0 < top:
                    self.cv.yview_moveto(max(0, (y0 - 8) / total))
                elif y1 > bot:
                    self.cv.yview_moveto(max(0, (y1 + 8 - self.cv.winfo_height()) / total))
                return

    # ================================================================ selection
    def select_ids(self, ids: List[int], see: bool = False, anchor: bool = True):
        self.selected = list(dict.fromkeys(ids))
        if anchor:
            self.anchor = self.selected[0] if self.selected else None
        mode = self._effective_mode()
        self._sel_lock = True
        try:
            if mode in ("list", "chrono"):
                tv = self.lst if mode == "list" else self.chr
                iids = [f"i:{i}" for i in self.selected if tv.exists(f"i:{i}")]
                tv.selection_set(iids)
                if iids:
                    tv.focus(iids[0])
                    if see:
                        tv.see(iids[0])
            elif mode == "cards":
                for x0, y0, x1, y1, i in self.card_boxes:
                    on = i in self.selected
                    for it in self.cv.find_withtag("card"):
                        pass
                    rid = next((o for o in self.cv.find_withtag(f"c{i}") if "card" in self.cv.gettags(o)), None)
                    if rid:
                        self.cv.itemconfigure(rid, outline=C["HI"] if on else C["LINE"], width=3 if on else 1)
                if see and self.selected:
                    self._card_see(self.selected[0])
            elif mode == "results":
                self._results_mark()
        finally:
            self.after_idle(lambda: setattr(self, "_sel_lock", False))
        self.cur_item = self.selected[0] if len(self.selected) == 1 else None
        self._schedule_detail()

    def _tv_selected(self, e):
        if getattr(self, "_sel_lock", False):
            return
        tv = e.widget
        ids = [int(i[2:]) for i in tv.selection() if i.startswith("i:")]
        if ids != self.selected:
            self.selected = ids
            if len(ids) == 1:
                self.anchor = ids[0]
            self.cur_item = ids[0] if len(ids) == 1 else None
            self._schedule_detail()

    def _schedule_detail(self):
        if self.detail_job:
            self.after_cancel(self.detail_job)
        self.detail_job = self.after(40, self.update_detail)

    def select_all(self):
        if self.cur_view == "v:trash":
            self.trv.selection_set(self.trv.get_children(""))
            return
        self.select_ids([r["id"] for r in (self.results if self.cur_view == "search" else self.visible)])

    def _tv_press(self, e):
        tv = e.widget
        row = tv.identify_row(e.y)
        if not row.startswith("i:"):
            self.press = None
            return
        iid = int(row[2:])
        if iid in self.selected and not (e.state & 0x5):
            self.press = {"x": e.x_root, "y": e.y_root, "ids": list(self.selected), "src": "items"}
            if len(self.selected) > 1:
                return "break"
        else:
            self.press = {"x": e.x_root, "y": e.y_root, "ids": None, "src": "items"}

    def _tv_double(self, e):
        row = e.widget.identify_row(e.y)
        if row.startswith("i:"):
            self.open_item(int(row[2:]))
            return "break"

    def _tv_menu(self, e):
        tv = e.widget
        row = tv.identify_row(e.y)
        if row.startswith("i:"):
            iid = int(row[2:])
            if iid not in self.selected:
                self.select_ids([iid])
            self.item_menu(e)
        else:
            self.view_menu(e)

    def open_selected(self):
        if self.cur_item:
            self.open_item(self.cur_item)
        elif self.selected:
            self.open_reader()

    # ================================================================ recherche
    def _update_placeholder(self):
        if self.v_search.get():
            self.l_ph.place_forget()
        else:
            self.l_ph.place(in_=self.e_search, x=2, rely=0.5, anchor="w")

    def _search_changed(self):
        self._update_placeholder()
        if getattr(self, "_search_lock", False):
            return
        if self.search_job:
            self.after_cancel(self.search_job)
        self.search_job = self.after(220, self.do_search)

    def focus_search(self):
        self.e_search.focus_set()
        self.e_search.select_range(0, "end")

    def search_for(self, txt: str):
        self.v_search.set(txt.strip())
        self.focus_search()

    def clear_search(self):
        if self.v_search.get():
            self.v_search.set("")
        if self.cur_view == "search":
            self.open_view(self.view_before_search if self._view_valid(self.view_before_search) else "v:all")
        self._focus_items()

    def do_search(self, keep: Optional[List[int]] = None):
        self.search_job = None
        q = self.v_search.get().strip()
        if not q:
            if self.cur_view == "search":
                self.open_view(self.view_before_search if self._view_valid(self.view_before_search) else "v:all")
            return
        if self.cur_view != "search":
            self._commit_pending()
            self.view_before_search = self.cur_view
            self.cur_view = "search"
            self._tree_lock = True
            self.tree.selection_remove(self.tree.selection())
            self._tree_lock = False
            sc = self.view_before_search.startswith("s:")
            self.cb_scope.configure(values=["Partout"] + ([f"Dans « {self.store.subject(self.view_before_search[2:])['name']} »"] if sc else []))
            self.cb_scope.current(0)
            self._show_view_widget()
        sids = None
        if self.cb_scope.current() == 1 and self.view_before_search.startswith("s:"):
            sid = int(self.view_before_search[2:])
            sids = [sid] + self.store.descendants(sid)
        typ = self._filter_type()
        t0 = time.time()
        self.results = self.store.search(q, [typ] if typ else None, sids, self._filter_tag(), self._period_since())
        self.terms = [t for t in re.findall(r"[\w'-]+", q, re.UNICODE) if len(t) >= 2] or [q]
        self.visible = self.results
        self._header()
        self.fill_results()
        self.set_status(f"{len(self.results)} résultat(s) pour « {q} » en {int((time.time() - t0) * 1000)} ms"
                        "   ·   Entrée ou ↓ pour parcourir, double-clic pour ouvrir, Échap pour quitter la recherche.", "DIM")
        ids = {r["id"] for r in self.results}
        keep = [i for i in (keep or []) if i in ids]
        if keep:
            self.select_ids(keep, see=True)
        else:
            self.selected = []
            self.cur_item = None
            self.update_detail()

    def _hl_insert(self, t: tk.Text, text: str, base_tags: Tuple[str, ...]):
        """Insere text en surlignant les termes de recherche (sans accents)."""
        if not text:
            return
        nt = norm(text)
        spans: List[Tuple[int, int]] = []
        if len(nt) == len(text):
            for term in self.terms:
                nterm = norm(term)
                if not nterm:
                    continue
                start = 0
                while True:
                    k = nt.find(nterm, start)
                    if k < 0:
                        break
                    spans.append((k, k + len(nterm)))
                    start = k + len(nterm)
        spans.sort()
        pos = 0
        for a, b in spans:
            if a < pos:
                continue
            t.insert("end", text[pos:a], base_tags)
            t.insert("end", text[a:b], base_tags + ("hl",))
            pos = b
        t.insert("end", text[pos:], base_tags)

    def fill_results(self):
        t = self.rt
        t.configure(state="normal")
        t.delete("1.0", "end")
        for tg in t.tag_names():
            if tg.startswith("r:"):
                t.tag_delete(tg)
        if not self.results:
            t.insert("end", "\nAucun résultat.\n\nEssaie un autre mot, moins de mots, ou enlève les filtres.\n"
                            "La recherche ignore les accents et les majuscules ; « plant » trouve aussi « plantes ».", "rnone")
        for r in self.results:
            tg = f"r:{r['id']}"
            ty = TYPES.get(r["type"], TYPES["file"])
            pre = ("📌" if r.get("pinned") else "") + ("★ " if r.get("fav") else "")
            self._hl_insert(t, f"{pre}{ty['icon']}  {r.get('title') or '(sans titre)'}", ("rtitle", tg))
            t.insert("end", "   " + self.store.subject_path(r["subject_id"]) + "\n", ("rsub", tg))
            snip = r.get("snip") or ""
            if snip and "\x01" in snip:
                parts = re.split(r"(\x01[^\x02]*\x02)", snip.replace("\n", " "))
                for p in parts:
                    if p.startswith("\x01"):
                        t.insert("end", p.strip("\x01\x02"), ("rsnip", tg, "hl"))
                    else:
                        t.insert("end", p, ("rsnip", tg))
                t.insert("end", "\n", ("rsnip", tg))
            else:
                txt = (r.get("body_text") or self.store.meta(r).get("description") or r.get("extracted") or r.get("url") or "")
                txt = re.sub(r"\s+", " ", txt).strip()
                if txt:
                    k = -1
                    nt = norm(txt)
                    for term in self.terms:
                        k = nt.find(norm(term))
                        if k >= 0:
                            break
                    a = max(0, k - 60) if k > 0 else 0
                    frag = ("…" if a else "") + txt[a:a + 220] + ("…" if len(txt) > a + 220 else "")
                    self._hl_insert(t, frag, ("rsnip", tg))
                    t.insert("end", "\n", ("rsnip", tg))
            meta = f"{ty['label']} · {self._row_date(r)}"
            if r.get("tags"):
                meta += "  ·  " + "  ".join("#" + x for x in tag_list(r["tags"]))
            t.insert("end", meta + "\n", ("rmeta", tg))
        t.configure(state="disabled")
        t.yview_moveto(0)

    def _result_at(self, e) -> Optional[int]:
        idx = self.rt.index(f"@{e.x},{e.y}")
        for tg in self.rt.tag_names(idx):
            if tg.startswith("r:"):
                return int(tg[2:])
        return None

    def _results_mark(self):
        t = self.rt
        t.tag_remove("rsel", "1.0", "end")
        for i in self.selected:
            r = t.tag_ranges(f"r:{i}")
            if r:
                t.tag_add("rsel", r[0], r[-1])
        if self.selected:
            r = t.tag_ranges(f"r:{self.selected[0]}")
            if r:
                t.see(r[0])
                t.see(r[-1])
                t.see(r[0])

    def _result_click(self, e):
        self.rt.focus_set()
        iid = self._result_at(e)
        if iid:
            if e.state & 0x4:
                cur = list(self.selected)
                cur.remove(iid) if iid in cur else cur.append(iid)
                self.select_ids(cur, anchor=False)
            else:
                self.select_ids([iid])
            self.press = {"x": e.x_root, "y": e.y_root, "ids": list(self.selected), "src": "items"}
        return "break"

    def _result_double(self, e):
        iid = self._result_at(e)
        if iid:
            self.open_item(iid)
        return "break"

    def _result_menu(self, e):
        iid = self._result_at(e)
        if iid:
            if iid not in self.selected:
                self.select_ids([iid])
            self.item_menu(e)
        return "break"

    def _result_key(self, e):
        ks = e.keysym
        ids = [r["id"] for r in self.results]
        if ks in ("Up", "Down") and ids:
            cur = ids.index(self.selected[0]) if self.selected and self.selected[0] in ids else -1
            n = max(0, min(len(ids) - 1, cur + (1 if ks == "Down" else -1)))
            if ks == "Up" and cur <= 0:
                self.e_search.focus_set()
                return "break"
            self.select_ids([ids[n]])
            return "break"
        if ks in ("Prior", "Next", "Home", "End"):
            return None
        if ks == "Return" and self.selected:
            self.open_item(self.selected[0])
            return "break"
        if ks == "Escape":
            self.clear_search()
            return "break"
        if ks == "Delete":
            self.delete_selected()
            return "break"
        if e.state & 0x4:
            return None
        if e.char and e.char.isprintable() and len(e.char) == 1:
            return self._type_to_search(e)
        return "break"

    # ================================================================ corbeille (vue)
    def fill_trash(self):
        tv = self.trv
        tv.delete(*tv.get_children(""))
        subs, its = self.store.trash_list()
        batch_subj = {s["del_batch"]: s for s in subs if s.get("del_batch")}
        n = 0
        for s in subs:
            par = self.store.subject(s["parent_id"]) if s["parent_id"] else None
            nits = sum(1 for r in its if r.get("del_batch") == s["del_batch"])
            tv.insert("", "end", iid=f"ts:{s['id']}", text=f"{s['icon'] or '📁'}  {s['name']}",
                      values=(f"Sujet ({nits} fiche{'s' if nits > 1 else ''})", fmt_date(s["deleted"]),
                              self.store.subject_path(par["id"]) if par else "(racine)"))
            n += 1
        for r in its:
            if r.get("del_batch") in batch_subj:
                continue
            ty = TYPES.get(r["type"], TYPES["file"])
            tv.insert("", "end", iid=f"ti:{r['id']}", text=f"{ty['icon']}  {r.get('title') or '(sans titre)'}",
                      values=(ty["label"], fmt_date(r["deleted"]), self.store.subject_path(r["subject_id"])))
            n += 1
        self._trash_count = n
        self._empty_hint(tv, n == 0)
        if n == 0:
            tv._hint.configure(text="La corbeille est vide.")

    _trash_count = 0

    def _trash_sel(self) -> Tuple[List[Dict[str, Any]], List[int]]:
        subs, items = [], []
        for i in self.trv.selection():
            if i.startswith("ts:"):
                r = self.store.q("SELECT * FROM subjects WHERE id=?", (int(i[3:]),))
                if r:
                    subs.append(dict(r[0]))
            elif i.startswith("ti:"):
                items.append(int(i[3:]))
        return subs, items

    def trash_restore(self):
        subs, items = self._trash_sel()
        if not subs and not items:
            self.set_status("Choisis d'abord un élément de la corbeille.", "WARN")
            return
        n = 0
        for s in subs:
            n += self.store.restore_batch(s["del_batch"])
        n += self.store.restore_items(items)
        self.refresh_tree()
        self.refresh_items()
        self.set_status(f"♻ {n} élément(s) restauré(s).", "OK")

    def trash_purge(self):
        subs, items = self._trash_sel()
        if not subs and not items:
            return
        if not messagebox.askyesno(APP_NAME, f"Supprimer définitivement {len(subs) + len(items)} élément(s) ?\n"
                                             "Les fichiers copiés dans le Grimoire seront effacés.\nCette action est irréversible.",
                                   parent=self, icon="warning"):
            return
        n = self.store.purge_items(items)
        for s in subs:
            n += self.store.empty_trash(s["del_batch"])
        self.refresh_tree()
        self.refresh_items()
        self.set_status(f"✖ {n} élément(s) supprimé(s) définitivement.", "OK")

    def trash_empty(self):
        if not self._trash_count:
            return
        if not messagebox.askyesno(APP_NAME, f"Vider la corbeille ({self._trash_count} élément(s)) ?\n"
                                             "Cette action est irréversible (une sauvegarde est faite avant).",
                                   parent=self, icon="warning"):
            return
        self.store.backup(force=True, tag="avant_vidage")
        n = self.store.empty_trash()
        self.undo_stack = [u for u in self.undo_stack if not u[0].startswith("suppression")]
        self.refresh_tree()
        self.refresh_items()
        self.set_status(f"🧹 Corbeille vidée ({n} fiche(s)).", "OK")

    # ================================================================ panneau de droite
    def _commit_pending(self):
        try:
            self.editor.flush()
        except Exception:
            pass
        if self._detail_mode == "item" and getattr(self, "editor_item", None):
            self._title_commit()
            self._tags_commit()
            self._info_commit()

    def update_detail(self):
        self.detail_job = None
        if self.cur_view == "v:trash":
            self._show_home_trash()
            return
        if len(self.selected) == 1:
            it = self.store.item(self.selected[0])
            if it and not it.get("deleted"):
                self.show_item(it)
                return
        if len(self.selected) > 1:
            self.show_multi()
            return
        self.show_home()

    def _right_mode(self, mode: str):
        if mode == self._detail_mode:
            return
        if self._detail_mode == "item":
            self._commit_pending()
        self.f_item.pack_forget()
        self.f_home.pack_forget()
        if mode == "item":
            self.f_item.pack(fill="both", expand=True)
        else:
            self.f_home.pack(fill="both", expand=True)
            self.editor_item = None
        self._detail_mode = mode

    def _panel_w(self) -> int:
        w = self.f_right.winfo_width()
        return max(300, w if w > 50 else 420)

    # ------------------------------------------------------------ accueil d'un sujet / d'une vue
    def show_home(self):
        self._right_mode("home")
        sf = self.f_home
        sf.clear()
        f = sf.inner
        st = self.store
        W = self._panel_w() - 40
        v = self.cur_view if self.cur_view != "search" else self.view_before_search
        if self.cur_view == "search":
            mk_label(f, "🔍 Recherche", "HI", "GTitle").pack(anchor="w", padx=14, pady=(14, 4))
            mk_label(f, f"{len(self.results)} résultat(s). Choisis une fiche pour la voir ici.\n\n"
                        "Astuces :\n• plusieurs mots = toutes les fiches qui contiennent tous ces mots\n"
                        "• les accents et majuscules sont ignorés\n• le texte des PDF, des pages capturées, des images (OCR) "
                        "et des mémos transcrits est aussi cherché\n• filtre par type, étiquette ou période au-dessus de la liste",
                     "TEXT", "GUI", wraplength=W, justify="left").pack(anchor="w", padx=14)
            return
        if v.startswith("s:") and st.subject(v[2:]):
            s = st.subject(v[2:])
            sid = s["id"]
            hd = tk.Frame(f, bg=C["PANEL"])
            hd.pack(fill="x", padx=12, pady=(12, 2))
            tk.Label(hd, text=s["icon"] or "📁", bg=C["PANEL"], fg=C["HI"], font=fnt("EmojiBig")).pack(side="left")
            tk.Label(hd, text=self.fit_text(s["name"], "GBig", W - 70, 2), bg=C["PANEL"], fg=s["color"] or C["HI"],
                     font=fnt("GBig"), justify="left").pack(side="left", padx=8)
            path = st.subject_path(sid)
            if " › " in path:
                mk_label(f, "dans " + path.rsplit(" › ", 1)[0], "DIM", "GSM", wraplength=W, justify="left").pack(anchor="w", padx=14)
            if s.get("description"):
                mk_label(f, s["description"], "TEXT", "GUI", wraplength=W, justify="left").pack(anchor="w", padx=14, pady=(6, 2))
            sids = [sid] + st.descendants(sid)
            items = st.items_in(sids)
            by: Dict[str, int] = {}
            for r in items:
                by[r["type"]] = by.get(r["type"], 0) + 1
            line = "  ".join(f"{TYPES[k]['icon']} {by[k]}" for k in TYPE_ORDER if by.get(k))
            mk_label(f, f"{len(items)} fiche(s)" + (f"  ·  {len(sids) - 1} sous-sujet(s)" if len(sids) > 1 else ""), "FG", "GUIB").pack(
                anchor="w", padx=14, pady=(10, 0))
            if line:
                mk_label(f, line, "TEXT", "GUI", wraplength=W, justify="left").pack(anchor="w", padx=14)
            mk_label(f, "AJOUTER ICI", "HI", "GHead").pack(anchor="w", padx=14, pady=(14, 4))
            g = tk.Frame(f, bg=C["PANEL"])
            g.pack(fill="x", padx=12)
            acts = [("📝 Note", self.new_note), ("🔗 Lien", self.add_link_dialog), ("❝ Citation", self.add_quote_dialog),
                    ("🖼 Image", lambda: self.add_files_dialog("image")), ("📄 Document", lambda: self.add_files_dialog("document")),
                    ("🎙 Mémo", self.record_memo), ("📎 Fichier", lambda: self.add_files_dialog(None)),
                    ("📋 Coller", self.smart_paste)]
            ncol = 2 if W < 420 else 4
            for k, (txt, cmd) in enumerate(acts):
                b = mk_button(g, txt, cmd)
                b.grid(row=k // ncol, column=k % ncol, sticky="we", padx=2, pady=2)
            for c in range(ncol):
                g.columnconfigure(c, weight=1)
            tf = tk.Frame(f, bg=C["PANEL"])
            tf.pack(fill="x", padx=12, pady=(6, 0))
            mk_label(tf, "📋 Fiche modèle :", "FG", "GUI").pack(side="left")
            names = list(self.all_templates())
            cb = ttk.Combobox(tf, values=names, state="readonly", font=fnt("GUI"), width=22)
            cb.pack(side="left", padx=6, fill="x", expand=True)
            cb.set("choisir…")
            cb.bind("<<ComboboxSelected>>", lambda _e: self.new_note(template=cb.get()))
            Tooltip(cb, "Créer une fiche déjà structurée : source, protocole, plante, recette, livre, journal de recherche…")
            mk_label(f, "SUJET", "HI", "GHead").pack(anchor="w", padx=14, pady=(14, 4))
            g2 = tk.Frame(f, bg=C["PANEL"])
            g2.pack(fill="x", padx=12)
            acts2 = [("✏ Modifier…", lambda: self.edit_subject(sid)), ("📂 Sous-sujet…", lambda: self.new_subject(sid)),
                     ("🌐 Exporter…", lambda: self.export_dialog(sid, False)), ("📖 Lire tout", self.open_reader)]
            for k, (txt, cmd) in enumerate(acts2):
                mk_button(g2, txt, cmd).grid(row=k // 2, column=k % 2, sticky="we", padx=2, pady=2)
            g2.columnconfigure(0, weight=1)
            g2.columnconfigure(1, weight=1)
            kids = st.children(sid)
            if kids:
                mk_label(f, "SOUS-SUJETS", "HI", "GHead").pack(anchor="w", padx=14, pady=(14, 2))
                tot = st.total_counts()
                for k in kids:
                    mk_link(f, f"{k['icon'] or '📁'} {k['name']}  ({tot.get(k['id'], 0)})", "", bg=C["PANEL"],
                            cmd=lambda i=k["id"]: self.open_view(f"s:{i}")).pack(anchor="w", padx=18, pady=1)
            recent = sorted(items, key=lambda r: r.get("updated") or "", reverse=True)[:6]
            if recent:
                mk_label(f, "MODIFIÉ RÉCEMMENT", "HI", "GHead").pack(anchor="w", padx=14, pady=(14, 2))
                for r in recent:
                    mk_link(f, self.fit_text(f"{TYPES.get(r['type'], TYPES['file'])['icon']} {r['title'] or '(sans titre)'}",
                                             "GUI", W - 20), "", bg=C["PANEL"],
                            cmd=lambda i=r["id"]: self.goto_item(i)).pack(anchor="w", padx=18, pady=1)
            mk_label(f, "Astuce : glisse des fiches sur un sujet de la colonne de gauche pour les déplacer "
                        "(Ctrl en lâchant = copier). Glisse un sujet sur un autre pour le ranger dedans.",
                     "DIM", "GSM", wraplength=W, justify="left").pack(anchor="w", padx=14, pady=(16, 10))
            return
        # vues speciales
        key = v
        title = next((f"{ic}  {lab}" for k, ic, lab in SPECIAL_VIEWS if k == key), "")
        if key.startswith("t:"):
            title = f"🏷  #{key[2:]}"
        mk_label(f, title or "Grimoire", "HI", "GTitle").pack(anchor="w", padx=14, pady=(14, 4))
        expl = {"v:all": "Toutes les fiches de tous les sujets.", "v:fav": "Les fiches marquées ★ (Ctrl+D).",
                "v:pin": "Les fiches épinglées 📌 (Ctrl+P) restent en haut de leur sujet.",
                "v:recent": "Les fiches ouvertes ou modifiées récemment.",
                "v:tags": "Toutes les fiches qui ont au moins une étiquette. Déplie « Étiquettes » à gauche pour en choisir une."}
        mk_label(f, expl.get(key, f"{len(self.visible)} fiche(s) avec cette étiquette."), "TEXT", "GUI", wraplength=W,
                 justify="left").pack(anchor="w", padx=14)
        s = st.stats()
        mk_label(f, f"\n{s['items']} fiches · {s['subjects']} sujets · {s['favs']} favoris · {human_size(s['media_size'])} de fichiers",
                 "FG", "GUI", wraplength=W, justify="left").pack(anchor="w", padx=14)
        if key == "v:tags" or key.startswith("t:"):
            tags = st.all_tags()[:60]
            if tags:
                mk_label(f, "ÉTIQUETTES", "HI", "GHead").pack(anchor="w", padx=14, pady=(14, 4))
                fl = tk.Text(f, bg=C["PANEL"], relief="flat", height=8, wrap="word", highlightthickness=0, cursor="arrow",
                             font=fnt("GUI"), padx=4)
                fl.pack(fill="x", padx=12)
                fl.tag_configure("tg", foreground=C["LINK"], underline=True)
                for t, c in tags:
                    tagn = f"tag_{len(fl.tag_names())}"
                    fl.insert("end", f"#{t} ({c})", ("tg", tagn))
                    fl.tag_bind(tagn, "<Button-1>", lambda _e, tt=t: self.open_view(f"t:{tt}"))
                    fl.tag_bind(tagn, "<Enter>", lambda _e, w=fl: w.configure(cursor="hand2"))
                    fl.tag_bind(tagn, "<Leave>", lambda _e, w=fl: w.configure(cursor="arrow"))
                    fl.insert("end", "   ")
                fl.configure(state="disabled", height=min(10, max(2, int(fl.index("end-1c").split(".")[0]) + len(tags) // 4)))
        mk_label(f, "\nChoisis une fiche pour la voir ici. Double-clic ou Entrée : ouvrir. F11 : mode lecture.",
                 "DIM", "GSM", wraplength=W, justify="left").pack(anchor="w", padx=14)

    def _show_home_trash(self):
        self._right_mode("home")
        sf = self.f_home
        sf.clear()
        f = sf.inner
        W = self._panel_w() - 40
        mk_label(f, "🗑  Corbeille", "HI", "GTitle").pack(anchor="w", padx=14, pady=(14, 4))
        mk_label(f, "Les sujets et fiches supprimés restent ici jusqu'à ce que tu vides la corbeille. "
                    "« Restaurer » les remet à leur place (dans « À classer » si leur sujet n'existe plus).\n\n"
                    "Ctrl+Z annule aussi la dernière suppression.", "TEXT", "GUI", wraplength=W, justify="left").pack(anchor="w", padx=14)
        sel = self.trv.selection()
        if len(sel) == 1 and sel[0].startswith("ti:"):
            it = self.store.item(int(sel[0][3:]))
            if it:
                mk_label(f, "\n" + (it.get("title") or ""), "HI", "GUIB", wraplength=W, justify="left").pack(anchor="w", padx=14)
                txt = (it.get("body_text") or it.get("url") or self.store.meta(it).get("filename") or "")[:1200]
                mk_label(f, txt, "TEXT", "GUI", wraplength=W, justify="left").pack(anchor="w", padx=14)

    # ------------------------------------------------------------ plusieurs fiches
    def show_multi(self):
        self._right_mode("home")
        sf = self.f_home
        sf.clear()
        f = sf.inner
        W = self._panel_w() - 40
        n = len(self.selected)
        mk_label(f, f"☑  {n} fiches choisies", "HI", "GTitle").pack(anchor="w", padx=14, pady=(14, 8))
        acts = [("📁 Déplacer vers…", lambda: self.move_selected(False)), ("⧉ Copier vers…", lambda: self.move_selected(True)),
                ("🏷 Ajouter des étiquettes…", self.edit_tags), ("★ Favoris oui/non", self.toggle_fav),
                ("📌 Épingler oui/non", self.toggle_pin), ("📖 Lire en mode lecture", self.open_reader),
                ("🌐 Exporter en HTML…", self.export_selection), ("🗑 Mettre à la corbeille", self.delete_selected)]
        for txt, cmd in acts:
            mk_button(f, txt, cmd, "danger" if "corbeille" in txt else "").pack(fill="x", padx=14, pady=2)
        mk_label(f, "", "DIM").pack()
        for i in self.selected[:40]:
            it = self.store.item(i)
            if it:
                mk_label(f, self.fit_text(f"{TYPES.get(it['type'], TYPES['file'])['icon']} {it['title'] or '(sans titre)'}", "GUI", W),
                         "TEXT", "GUI").pack(anchor="w", padx=16)
        if n > 40:
            mk_label(f, f"… et {n - 40} autre(s)", "DIM", "GSM").pack(anchor="w", padx=16)

    # ------------------------------------------------------------ une fiche
    def show_item(self, it: Dict[str, Any]):
        if self._detail_mode == "item" and getattr(self, "editor_item", None) == it["id"] and getattr(self, "_shown_ver", -1) == self._item_ver(it):
            return
        if self._detail_mode == "item" and getattr(self, "editor_item", None) not in (None, it["id"]):
            self._commit_pending()
            it = self.store.item(it["id"]) or it
        self._right_mode("item")
        st = self.store
        iid = it["id"]
        same = getattr(self, "editor_item", None) == iid
        self.editor_item = iid
        self._shown_ver = self._item_ver(it)
        ty = TYPES.get(it["type"], TYPES["file"])
        self.l_icon.configure(text=ty["icon"])
        self._loaded_title = it.get("title") or ""
        if self.focus_get() is not self.e_title or not same:
            self.v_title.set(self._loaded_title)
        self._loaded_tags = ", ".join(tag_list(it.get("tags") or ""))
        if self.focus_get() is not self.e_tags or not same:
            self.v_tags.set(self._loaded_tags)
        self.b_fav.configure(text="★" if it.get("fav") else "☆", fg=C["HI"] if it.get("fav") else C["BTN_FG"])
        self.b_fav._colors = (C["BTN"], C["HI"] if it.get("fav") else C["BTN_FG"], C["HI"], C["ON_HI"])
        self.b_pin.configure(fg=C["HI"] if it.get("pinned") else C["DIM"])
        self.b_pin._colors = (C["BTN"], C["HI"] if it.get("pinned") else C["DIM"], C["HI"], C["ON_HI"])
        m = st.meta(it)
        bits = [ty["label"], st.subject_path(it["subject_id"])]
        if it.get("event_date"):
            bits.append("📅 " + fmt_date(it["event_date"], False))
        bits.append("ajouté " + fmt_date(it.get("created") or ""))
        if m.get("pending"):
            bits.append("⏳ récupération en cours…")
        self.l_meta.configure(text="  ·  ".join(bits))
        # onglets
        typ = it["type"]
        note_like = typ == "note"
        self.nb.tab(self.tab_prev, state="hidden" if note_like else "normal")
        self.nb.tab(self.tab_body, text="❝ Citation" if typ == "quote" else ("📝 Note" if note_like else "📝 Notes"))
        if not same or self.editor.is_empty() and it.get("body"):
            self.editor.load(it.get("body") or "", self.terms if self.cur_view == "search" else None)
        self.fill_preview(it)
        self.fill_info(it)
        if not same:
            if note_like or (typ == "quote" and False):
                self.nb.select(self.tab_body)
            else:
                self.nb.select(self.tab_prev)
            if not it.get("opened") or (it.get("opened") or "")[:10] != today():
                st.update_item(iid, touch=False, opened=now_iso())

    def _item_ver(self, it: Dict[str, Any]) -> str:
        return f"{it.get('updated')}|{it.get('meta')}|{it.get('thumb')}|{it.get('fav')}|{it.get('pinned')}|{it.get('subject_id')}|{len(it.get('extracted') or '')}"

    def refresh_item_view(self, iid: int):
        """Une fiche a change (enrichissement, OCR…) : met a jour sa ligne et le panneau si elle est affichee."""
        it = self.store.item(iid)
        if not it:
            return
        for k, r in enumerate(self.visible):
            if r["id"] == iid:
                self.visible[k] = it
                break
        mode = self._effective_mode()
        if mode == "list" and self.lst.exists(f"i:{iid}"):
            s = self.store.subject(it["subject_id"])
            self.lst.item(f"i:{iid}", values=(self._row_title(it), s["name"] if s else "", self._row_date(it),
                                              ", ".join(tag_list(it.get("tags") or ""))), tags=("fav",) if it.get("fav") else ())
        elif mode == "chrono" and self.chr.exists(f"i:{iid}"):
            self.chr.item(f"i:{iid}", text=self._row_title(it))
        elif mode == "cards":
            if getattr(self, "_cards_job", None):
                self.after_cancel(self._cards_job)
            self._cards_job = self.after(150, lambda: (self.fill_cards(), self.select_ids(self.selected) if self.selected else None))
        if self._detail_mode == "item" and getattr(self, "editor_item", None) == iid:
            self.show_item(it)

    def _tab_changed(self):
        try:
            cur = self.nb.select()
        except tk.TclError:
            return
        if cur == str(self.tab_body):
            pass

    def _section(self, f, text: str):
        mk_label(f, text, "HI", "GHead", bg=C["PANEL"]).pack(anchor="w", padx=12, pady=(12, 3))

    def _btn_row(self, f, acts: List[Tuple[str, Callable, str]]):
        W = self._panel_w() - 30
        row = tk.Frame(f, bg=C["PANEL"])
        row.pack(fill="x", padx=10, pady=2)
        used = 0
        for txt, cmd, tip in acts:
            b = mk_button(row, txt, cmd, tip=tip)
            need = b.winfo_reqwidth() + 4
            if used + need > W and used:
                row = tk.Frame(f, bg=C["PANEL"])
                row.pack(fill="x", padx=10, pady=2)
                used = 0
                b.destroy()
                b = mk_button(row, txt, cmd, tip=tip)
            b.pack(side="left", padx=2)
            used += need
        return row

    def fill_preview(self, it: Dict[str, Any]):
        sf = self.tab_prev
        y = sf.canvas.yview()[0] if getattr(self, "_prev_item", None) == it["id"] else 0
        self._prev_item = it["id"]
        sf.clear()
        f = sf.inner
        st = self.store
        m = st.meta(it)
        W = self._panel_w() - 40
        typ = it["type"]
        url = it.get("url") or ""
        fpath = Paths.abs(it.get("file") or "")
        self._prev_imgs: List[Any] = []
        if typ == "quote":
            txt = it.get("body_text") or ""
            q = tk.Frame(f, bg=C["PANEL"])
            q.pack(fill="x", padx=12, pady=(12, 4))
            tk.Frame(q, bg=C["QUOTE"], width=4).pack(side="left", fill="y")
            tk.Label(q, text=f"« {txt.strip()} »", bg=C["PANEL"], fg=C["TEXT"], font=fnt("RI"), wraplength=W - 30,
                     justify="left").pack(side="left", padx=10, pady=4)
            src = " — " + ", ".join(x for x in (it.get("author"), it.get("source"), m.get("page") and f"p. {m.get('page')}",
                                                it.get("event_date")) if x)
            if src.strip(" —"):
                mk_label(f, src, "FG", "GUI", bg=C["PANEL"], wraplength=W, justify="left").pack(anchor="w", padx=14)
            if url:
                mk_link(f, url, url, bg=C["PANEL"], wrap=W).pack(anchor="w", padx=14, pady=2)
            self._btn_row(f, [("📋 Copier avec la source", lambda: self.copy_citation(it["id"]), "Texte + auteur + source, prêt à coller"),
                              ("✏ Modifier", lambda: self.nb.select(self.tab_body), "Modifier le texte de la citation")])
            return
        img_src = it.get("thumb") or ""
        if typ == "image" and fpath and os.path.isfile(fpath):
            img_src = it.get("file")
        if img_src:
            ph = self.photo(img_src, W, 340 if typ == "image" else 240)
            if ph is not None:
                lab = tk.Label(f, image=ph, bg=C["PANEL"], cursor="hand2", bd=0)
                lab.pack(anchor="w", padx=12, pady=(10, 4))
                self._prev_imgs.append(ph)
                if typ == "image":
                    lab.bind("<Button-1>", lambda _e: self.view_image(it["id"]))
                    Tooltip(lab, "Clic : visionneuse (zoom, rotation, plein écran)")
                elif url:
                    lab.bind("<Button-1>", lambda _e: open_url(url))
                    Tooltip(lab, "Clic : ouvrir dans le navigateur")
        elif typ not in ("link", "video") or not url:
            tk.Label(f, text=TYPES.get(typ, TYPES["file"])["icon"], bg=C["PANEL"], fg=C["FG"], font=fnt("EmojiBig")).pack(
                anchor="w", padx=14, pady=(12, 0))
        if url:
            mk_link(f, url, url, bg=C["PANEL"], wrap=W, font_name="GSM").pack(anchor="w", padx=14, pady=(4, 2))
            if m.get("site") or it.get("author"):
                mk_label(f, " · ".join(x for x in (m.get("site"), it.get("author")) if x), "DIM", "GSM", bg=C["PANEL"],
                         wraplength=W, justify="left").pack(anchor="w", padx=14)
        desc = m.get("description") or ""
        if desc:
            mk_label(f, desc[:1500], "TEXT", "GUI", bg=C["PANEL"], wraplength=W, justify="left").pack(anchor="w", padx=14, pady=(6, 2))
        if m.get("fetch_error") and typ in ("link", "video"):
            mk_label(f, "⚠ Infos non récupérées : " + str(m["fetch_error"])[:200], "WARN", "GSM", bg=C["PANEL"], wraplength=W,
                     justify="left").pack(anchor="w", padx=14, pady=2)
        if fpath:
            exists = os.path.isfile(fpath)
            name = m.get("filename") or os.path.basename(fpath)
            info = [name]
            if m.get("size"):
                info.append(human_size(m["size"]))
            if m.get("pages"):
                info.append(f"{m['pages']} page(s)")
            if m.get("width"):
                info.append(f"{m['width']}×{m['height']} px")
            if m.get("duration"):
                info.append(fmt_dur(m["duration"]))
            if exists:
                mk_link(f, "  ·  ".join(info), fpath, bg=C["PANEL"], wrap=W).pack(anchor="w", padx=14, pady=(6, 2))
            else:
                mk_label(f, "⚠ Fichier introuvable : " + fpath, "ERR", "GSM", bg=C["PANEL"], wraplength=W, justify="left").pack(
                    anchor="w", padx=14, pady=(6, 2))
        # boutons
        acts: List[Tuple[str, Callable, str]] = []
        if typ in ("audio", "voice") or (typ == "video" and fpath and os.path.splitext(fpath)[1].lower() in AUDIO_EXT):
            self._player_row(f, it)
        if url:
            acts.append(("🌐 Ouvrir", lambda: open_url(url), "Ouvrir dans le navigateur"))
            acts.append(("📋 Copier le lien", lambda: (copy_to_clipboard(self, url), self.set_status("Lien copié.", "OK")), ""))
        if fpath and os.path.isfile(fpath):
            if typ == "image":
                acts.append(("🔍 Visionneuse", lambda: self.view_image(it["id"]), "Zoom, rotation, image suivante"))
            acts.append(("📂 Ouvrir", lambda: open_path(fpath), "Ouvrir avec le programme de Windows"))
            acts.append(("🗂 Dossier", lambda: reveal_in_explorer(fpath), "Montrer le fichier dans l'Explorateur"))
        if typ in ("link", "video") and url:
            acts.append(("↻ Infos", lambda: self.refetch(it["id"]), "Récupérer à nouveau titre, description et miniature"))
            acts.append(("🌐 Capturer la page", lambda: self.capture_item(it["id"]), "Copie complète hors ligne : HTML + PDF + image"))
        if typ == "video" and url:
            acts.append(("📦 Envoyer à l'Archiveur", lambda: self.send_to_archiveur(url), "Copie le lien et ouvre l'Archiveur 5"))
        if typ == "image" and fpath:
            acts.append(("🔤 Lire le texte (OCR)", lambda: self.ocr_item(it["id"]), "Reconnaissance de texte Windows"))
        if typ in ("voice", "audio") and fpath:
            acts.append(("📝 Transcrire", lambda: self.transcribe_item(it["id"]), "Transcription locale (faster-whisper)"))
        if typ == "document" and fpath:
            acts.append(("↻ Extraire le texte", lambda: self.reextract(it["id"]), "Relire le texte du document"))
        if acts:
            self._btn_row(f, acts)
        extra = m.get("extra_files") or []
        if extra:
            self._section(f, "COPIE DE LA PAGE")
            for rel in extra:
                p = Paths.abs(rel)
                lab = {".html": "🌐 Page hors ligne (HTML)", ".pdf": "📄 PDF de la page", ".png": "🖼 Image de la page"}.get(
                    os.path.splitext(p)[1].lower(), "📎 " + os.path.basename(p))
                if os.path.isfile(p):
                    mk_link(f, lab, p, bg=C["PANEL"]).pack(anchor="w", padx=18, pady=1)
        ext = it.get("extracted") or ""
        if ext and not (typ in ("link", "video") and ext.strip() == desc.strip()):
            title = {"image": "TEXTE LU DANS L'IMAGE (OCR)", "voice": "TRANSCRIPTION", "audio": "TRANSCRIPTION",
                     "page": "TEXTE DE LA PAGE"}.get(typ, "TEXTE DU DOCUMENT")
            self._section(f, f"{title}  ({len(ext.split())} mots)")
            box = tk.Frame(f, bg=C["PANEL"])
            box.pack(fill="x", padx=12, pady=(0, 8))
            t = tk.Text(box, bg=C["ENTRY_BG"], fg=C["ENTRY_FG"], font=fnt("GUI"), wrap="word", relief="flat", height=14,
                        padx=8, pady=6, highlightthickness=1, highlightbackground=C["LINE"], selectbackground=C["SEL"],
                        selectforeground=C["ON_SEL"])
            sb = ttk.Scrollbar(box, orient="vertical", command=t.yview)
            t.configure(yscrollcommand=sb.set)
            t.pack(side="left", fill="x", expand=True)
            sb.pack(side="right", fill="y")
            t.insert("1.0", ext[:300000])
            configure_rich_tags(t)
            relink(t, self.terms if self.cur_view == "search" else None)
            t.configure(state="disabled")
            t.bind("<1>", lambda _e, w=t: w.focus_set())
            if self.cur_view == "search":
                r = t.tag_nextrange("search", "1.0")
                if r:
                    t.see(r[0])
        try:
            self.gx_link_section(f, it, W)
        except Exception:
            logger.error("aperçus de liens : %s", traceback.format_exc())
        self.after_idle(lambda: sf.canvas.yview_moveto(y))

    def _player_row(self, f, it: Dict[str, Any]):
        fpath = Paths.abs(it.get("file") or "")
        m = self.store.meta(it)
        row = tk.Frame(f, bg=C["PANEL"])
        row.pack(fill="x", padx=10, pady=(8, 2))
        playing_this = self.player_item == it["id"] and self.player.playing()
        self.b_play = mk_button(row, "⏸ Pause" if playing_this else "▶ Écouter", lambda: self.play_toggle(it["id"]), "accent",
                                tip="Lecture sans fenêtre (ffplay)")
        self.b_play.pack(side="left", padx=2)
        mk_button(row, "⏪ 10 s", lambda: self.play_seek(it["id"], -10)).pack(side="left", padx=2)
        mk_button(row, "10 s ⏩", lambda: self.play_seek(it["id"], 10)).pack(side="left", padx=2)
        mk_button(row, "■", self.play_stop, tip="Arrêter").pack(side="left", padx=2)
        self.l_play = mk_label(row, "", "HI", "GUIB", bg=C["PANEL"])
        self.l_play.pack(side="left", padx=8)
        self._play_total = float(m.get("duration") or 0)
        self._update_play_label()

    def _update_play_label(self):
        try:
            if not self.l_play.winfo_exists():
                return
        except Exception:
            return
        pos = self.player.position() if self.player_item == getattr(self, "editor_item", None) else 0
        tot = getattr(self, "_play_total", 0)
        self.l_play.configure(text=f"{fmt_dur(pos)} / {fmt_dur(tot)}" if tot else fmt_dur(pos))

    def _tick_player(self):
        try:
            if self.player_item and not self.player.playing() and getattr(self, "_was_playing", False):
                self._was_playing = False
                if hasattr(self, "b_play") and self.b_play.winfo_exists():
                    self.b_play.configure(text="▶ Écouter")
            if self.player.playing():
                self._was_playing = True
            if hasattr(self, "l_play"):
                self._update_play_label()
        except Exception:
            pass
        self.after(250, self._tick_player)

    def play_toggle(self, iid: int):
        it = self.store.item(iid)
        if not it:
            return
        p = Paths.abs(it.get("file") or "")
        if self.player_item == iid and self.player.playing():
            self.player.pause()
            self.b_play.configure(text="▶ Reprendre")
            return
        start = self.player.paused_at if self.player_item == iid else 0.0
        err = self.player.play(p, start)
        if err:
            if messagebox.askyesno(APP_NAME, f"Lecture intégrée impossible : {err}\n\nOuvrir avec le lecteur de Windows ?", parent=self):
                open_path(p)
            return
        self.player_item = iid
        self.b_play.configure(text="⏸ Pause")

    def play_seek(self, iid: int, d: float):
        if self.player_item != iid:
            return self.play_toggle(iid)
        pos = max(0.0, self.player.position() + d)
        it = self.store.item(iid)
        if it:
            self.player.play(Paths.abs(it.get("file") or ""), pos)
            self.b_play.configure(text="⏸ Pause")

    def play_stop(self):
        self.player.stop()
        try:
            self.b_play.configure(text="▶ Écouter")
        except Exception:
            pass

    # ------------------------------------------------------------ onglet Fiche
    def fill_info(self, it: Dict[str, Any]):
        sf = self.tab_info
        sf.clear()
        f = sf.inner
        st = self.store
        W = self._panel_w() - 40
        m = st.meta(it)
        g = tk.Frame(f, bg=C["PANEL"])
        g.pack(fill="x", padx=8, pady=(10, 4))
        g.columnconfigure(1, weight=1)
        self.info_vars: Dict[str, tk.StringVar] = {}
        rows = [("source", "Source", "Livre, site, émission, personne…"), ("author", "Auteur", ""),
                ("event_date", "Date de l'info", "AAAA-MM-JJ : sert à la chronologie"), ("url", "Lien", "")]
        r = 0
        for key, lab, hint in rows:
            mk_label(g, lab, "HI", "GSMB", bg=C["PANEL"]).grid(row=r, column=0, sticky="w", padx=(4, 8), pady=3)
            v = tk.StringVar(value=it.get(key) or "")
            e = mk_entry(g, v, 20, "GSM")
            e.grid(row=r, column=1, sticky="we", pady=3, ipady=2)
            e.bind("<FocusOut>", lambda _e: self._info_commit())
            e.bind("<Return>", lambda _e: self._info_commit())
            e.bind("<Control-KeyPress>", self._entry_ctrl)
            if hint:
                Tooltip(e, hint)
            self.info_vars[key] = v
            r += 1
        if it["type"] == "quote":
            mk_label(g, "Page", "HI", "GSMB", bg=C["PANEL"]).grid(row=r, column=0, sticky="w", padx=(4, 8), pady=3)
            v = tk.StringVar(value=str(m.get("page") or ""))
            e = mk_entry(g, v, 20, "GSM")
            e.grid(row=r, column=1, sticky="we", pady=3, ipady=2)
            e.bind("<FocusOut>", lambda _e: self._info_commit())
            self.info_vars["page"] = v
            r += 1
        self._info_item = it["id"]
        self._section(f, "RANGEMENT")
        sp = tk.Frame(f, bg=C["PANEL"])
        sp.pack(fill="x", padx=12)
        mk_link(sp, st.subject_label(it["subject_id"]), "", bg=C["PANEL"], wrap=W - 120,
                cmd=lambda: self.open_view(f"s:{it['subject_id']}")).pack(side="left")
        mk_button(sp, "Déplacer…", lambda: self.move_selected(False), font_name="GSM").pack(side="right")
        self._section(f, "DATES")
        for lab, key in (("Ajouté", "created"), ("Modifié", "updated"), ("Ouvert", "opened")):
            if it.get(key):
                mk_label(f, f"  {lab} : {fmt_date(it[key])}", "TEXT", "GSM", bg=C["PANEL"]).pack(anchor="w", padx=12)
        fpath = Paths.abs(it.get("file") or "")
        if fpath:
            self._section(f, "FICHIER")
            mk_link(f, fpath, fpath, bg=C["PANEL"], wrap=W, font_name="GSM").pack(anchor="w", padx=14)
            if m.get("original") and m["original"] != fpath:
                mk_label(f, "Copié depuis : " + m["original"], "DIM", "GSM", bg=C["PANEL"], wraplength=W, justify="left").pack(
                    anchor="w", padx=14)
        refs = list(dict.fromkeys(x.group(1).strip() for x in REF_RE.finditer(it.get("body_text") or "")))
        self._section(f, "RÉFÉRENCES [[…]]")
        if refs:
            for t in refs[:50]:
                tgt = st.find_by_title(t)
                sid = st.find_subject(t) if not tgt else None
                mark = "" if (tgt or sid) else "  (à créer)"
                mk_link(f, f"→ {t}{mark}", "", bg=C["PANEL"], cmd=lambda tt=t: self.follow_ref(tt)).pack(anchor="w", padx=16)
        else:
            mk_label(f, "Aucune. Dans la note, [[ ]] (ou tape [[titre]]) relie une autre fiche ou un sujet.", "DIM", "GSM",
                     bg=C["PANEL"], wraplength=W, justify="left").pack(anchor="w", padx=14)
        back = st.backlinks(it)
        self._section(f, f"CITÉE DANS ({len(back)})")
        if back:
            for b in back[:50]:
                mk_link(f, f"← {b['title'] or '(sans titre)'}", "", bg=C["PANEL"], cmd=lambda i=b["id"]: self.goto_item(i)).pack(
                    anchor="w", padx=16)
        else:
            mk_label(f, "Aucune fiche ne fait référence à celle-ci.", "DIM", "GSM", bg=C["PANEL"]).pack(anchor="w", padx=14)
        self._btn_row(f, [("📋 Copier la citation", lambda: self.copy_citation(it["id"]), "Titre, auteur, source, lien et date"),
                          ("🌐 Exporter", lambda: self.export_selection([it["id"]]), "Cette fiche en page HTML autonome")])

    def _info_commit(self):
        iid = getattr(self, "_info_item", None)
        if not iid or not getattr(self, "info_vars", None):
            return
        it = self.store.item(iid)
        if not it:
            return
        upd: Dict[str, Any] = {}
        for k in ("source", "author", "event_date", "url"):
            if k in self.info_vars:
                try:
                    val = self.info_vars[k].get().strip()
                except tk.TclError:
                    return
                if k == "event_date" and val:
                    val = self._parse_date(val)
                    if val is None:
                        self.set_status("Date non comprise : écris AAAA-MM-JJ (ou AAAA, ou AAAA-MM).", "WARN")
                        continue
                if k == "url" and val:
                    val = fix_url(val)
                if val != (it.get(k) or ""):
                    upd[k] = val
        if "page" in self.info_vars:
            try:
                pg = self.info_vars["page"].get().strip()
            except tk.TclError:
                pg = None
            m = self.store.meta(it)
            if pg is not None and pg != str(m.get("page") or ""):
                m["page"] = pg
                upd["meta"] = m
        if upd:
            self.store.update_item(iid, **upd)
            self.refresh_item_view(iid)

    @staticmethod
    def _parse_date(s: str) -> Optional[str]:
        s = s.strip()
        mm = re.match(r"^(\d{4})(?:[-/.](\d{1,2})(?:[-/.](\d{1,2}))?)?$", s)
        if mm:
            y, mo, d = mm.group(1), mm.group(2), mm.group(3)
            try:
                dt.date(int(y), int(mo or 1), int(d or 1))
            except ValueError:
                return None
            return y + (f"-{int(mo):02d}" if mo else "") + (f"-{int(d):02d}" if d else "")
        mm = re.match(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})$", s)
        if mm:
            try:
                return dt.date(int(mm.group(3)), int(mm.group(2)), int(mm.group(1))).isoformat()
            except ValueError:
                return None
        return None

    # ------------------------------------------------------------ titre, etiquettes, texte
    def _title_commit(self):
        iid = getattr(self, "editor_item", None)
        if not iid:
            return
        try:
            t = self.v_title.get().strip()
        except tk.TclError:
            return
        if t == self._loaded_title or not t:
            if not t:
                self.v_title.set(self._loaded_title)
            return
        it = self.store.item(iid)
        if not it:
            return
        m = self.store.meta(it)
        m["auto_title"] = False
        self.store.update_item(iid, title=t[:300], meta=m)
        self._loaded_title = t[:300]
        self.refresh_item_view(iid)

    def _tags_commit(self):
        iid = getattr(self, "editor_item", None)
        if not iid:
            return
        try:
            t = norm_tags(self.v_tags.get())
        except tk.TclError:
            return
        if t == norm_tags(self._loaded_tags):
            return
        self.store.update_item(iid, tags=t)
        self._loaded_tags = ", ".join(tag_list(t))
        self.refresh_item_view(iid)
        self.refresh_tree()

    def _tags_autocomplete(self, e):
        if e.keysym in ("BackSpace", "Delete", "Left", "Right", "Tab", "Return", "comma", "space", "Shift_L", "Shift_R"):
            return
        txt = self.v_tags.get()
        if self.e_tags.index("insert") != len(txt):
            return
        cur = txt.split(",")[-1].strip()
        if len(cur) < 2:
            return
        for t, _c in self.store.all_tags():
            if norm(t).startswith(norm(cur)) and norm(t) != norm(cur):
                pos = len(txt)
                self.v_tags.set(txt + t[len(cur):])
                self.e_tags.icursor(pos)
                self.e_tags.select_range(pos, "end")
                break

    def _tags_tab(self, _e):
        if self.e_tags.selection_present():
            self.e_tags.selection_clear()
            self.v_tags.set(self.v_tags.get() + ", ")
            self.e_tags.icursor("end")
            return "break"
        return None

    def _editor_changed(self):
        iid = getattr(self, "editor_item", None)
        if not iid:
            return
        it = self.store.item(iid)
        if not it or it.get("deleted"):
            return
        body = self.editor.body()
        if body == (it.get("body") or "") or (not it.get("body") and self.editor.is_empty()):
            return
        upd: Dict[str, Any] = {"body": body}
        m = self.store.meta(it)
        if it["type"] == "note" and m.get("auto_title"):
            first = next((ln.strip(" #•☐☑>-") for ln in self.editor.plain().splitlines() if ln.strip(" #•☐☑>-")), "")
            if first:
                upd["title"] = first[:80]
                self._loaded_title = upd["title"]
                if self.focus_get() is not self.e_title:
                    self.v_title.set(upd["title"])
        if it["type"] == "quote" and m.get("auto_title") is not False and not it.get("author"):
            words = re.sub(r"\s+", " ", self.editor.plain()).strip()
            upd["title"] = words[:60] + ("…" if len(words) > 60 else "")
        self.store.update_item(iid, **upd)
        self._shown_ver = self._item_ver(self.store.item(iid) or it)
        self.refresh_item_view(iid)
        self.set_status("✔ Enregistré automatiquement.", "DIM")

    # ================================================================ ajouter
    def _after_add(self, ids: List[int], sid: Optional[int] = None, enrich: bool = True, msg: str = "",
                   transcribe_ids: Iterable[int] = ()):
        ids = [i for i in ids if i]
        if not ids:
            return
        st = self.store
        sid = sid or (st.item(ids[0]) or {}).get("subject_id")
        self.refresh_tree()
        shown = {r["id"] for r in self.collect_items()} if self.cur_view not in ("search", "v:trash") else set()
        if not set(ids) & shown:
            self.open_view(f"s:{sid}")
        else:
            self.refresh_items(keep=ids)
        self.select_ids(ids, see=True)
        if self.detail_job:
            self.after_cancel(self.detail_job)
        self.update_detail()
        self.set_status(msg or f"＋ {len(ids)} fiche(s) ajoutée(s) dans « {st.subject_path(sid)} ».", "OK")
        if enrich:
            ocr = bool(self.store.get("auto_ocr", False))
            for iid in ids:
                it = st.item(iid)
                if not it:
                    continue
                if it["type"] in ("link", "video") and not self.store.get("auto_fetch", True):
                    st.set_meta(iid, pending=False)
                    continue
                if it["type"] in ("link", "video") or it.get("file"):
                    self.run_job(lambda i=iid: enrich_any(st, i, ocr=ocr), lambda _r, i=iid: self._enriched(i),
                                 "récupération des infos")
        for iid in transcribe_ids:
            self.transcribe_item(iid, quiet=True)

    def _enriched(self, iid: int):
        self.refresh_item_view(iid)
        it = self.store.item(iid)
        if it and it.get("thumb") and self._effective_mode() == "cards":
            self.img_cache = {k: v for k, v in self.img_cache.items() if k[0] != Paths.abs(it["thumb"])}

    def new_note(self, text: str = "", template: Optional[str] = None):
        sid = self.current_sid()
        title, body, auto = "Nouvelle note", "", True
        if template:
            tp = self.all_templates().get(template)
            if not tp:
                return
            body = runs_to_json(md_runs(tp[1]))
            title, auto = f"{template}", True
        elif text:
            body = runs_to_json(runs_from_any(text))
            first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
            title = first[:80] or title
        iid = self.store.add_item(sid, "note", title=title, body=body, meta={"auto_title": auto, "template": template or ""})
        self._after_add([iid], sid, enrich=False, msg=f"📝 Nouvelle note dans « {self.store.subject_path(sid)} » : écris, "
                                                     "c'est enregistré automatiquement.")
        self.nb.select(self.tab_body)
        self.editor.t.focus_set()
        if template:
            idx = self.editor.t.search(": ", "1.0", "2.0")
            self.editor.t.mark_set("insert", f"{idx}+2c" if idx else "1.end")
        else:
            self.editor.t.mark_set("insert", "end-1c")

    def add_link_dialog(self, url: str = ""):
        if not url:
            try:
                clip = self.clipboard_get().strip()
                if is_url(clip) and len(clip.split()) == 1:
                    url = clip
            except tk.TclError:
                pass
        r = LinkDialog(self, self, url).wait()
        if not r:
            return
        sid = self.current_sid()
        iid = add_url(self.store, sid, r["url"], r["title"], r["note"], r["tags"])
        self._after_add([iid], sid)
        if r.get("capture"):
            self.capture_item(iid)

    def add_urls(self, urls: List[str], sid: Optional[int] = None):
        sid = sid or self.current_sid()
        ids = [add_url(self.store, sid, u) for u in dict.fromkeys(urls)]
        self._after_add(ids, sid)

    def add_quote_dialog(self, text: str = ""):
        r = QuoteDialog(self, text).wait()
        if not r:
            return
        sid = self.current_sid()
        d = self._parse_date(r["date"]) if r.get("date") else ""
        iid = add_quote(self.store, sid, r["text"], r["author"], r["source"], r["url"], r["page"], r["tags"], d or "")
        self._after_add([iid], sid, enrich=False, msg="❝ Citation ajoutée.")

    def add_text_note(self, text: str, sid: Optional[int] = None):
        sid = sid or self.current_sid()
        ids = add_text(self.store, sid, text)
        self._after_add(ids, sid)

    def add_files_dialog(self, kind: Optional[str]):
        ft = {"image": [("Images", " ".join("*" + e for e in sorted(IMG_EXT)))],
              "document": [("Documents", " ".join("*" + e for e in sorted(DOC_EXT)))],
              "audio": [("Sons", " ".join("*" + e for e in sorted(AUDIO_EXT)))],
              "video": [("Vidéos", " ".join("*" + e for e in sorted(VIDEO_EXT)))]}.get(kind or "", []) + [("Tous les fichiers", "*.*")]
        paths = filedialog.askopenfilenames(parent=self, title="Ajouter au Grimoire", filetypes=ft,
                                            initialdir=self.store.get("last_dir", os.path.expanduser("~")))
        if paths:
            self.store.set("last_dir", os.path.dirname(paths[0]))
            self.add_paths(list(paths), None)

    def add_paths(self, paths: List[str], sid: Optional[int]):
        sid = sid or self.current_sid()
        files = [p for p in paths if os.path.isfile(p)]
        dirs = [p for p in paths if os.path.isdir(p)]
        big = sum(os.path.getsize(p) for p in files if os.path.isfile(p))
        if big > 500 * 1024 * 1024 and not messagebox.askyesno(
                APP_NAME, f"Copier {human_size(big)} de fichiers dans le Grimoire ?", parent=self):
            return
        ids: List[int] = []
        for p in files:
            try:
                ids.append(add_file(self.store, sid, p))
            except Exception as ex:
                logger.error("ajout %s : %s", p, ex)
                self.set_status(f"⚠ {os.path.basename(p)} : {ex}", "ERR")
        for d in dirs:
            if messagebox.askyesno(APP_NAME, f"Importer le dossier « {os.path.basename(d)} » et ses sous-dossiers ?\n"
                                             "(un sous-sujet est créé pour chaque dossier)", parent=self):
                got, _n = import_folder(self.store, sid, d)
                ids += got
        self._after_add(ids, sid)

    def import_folder_dialog(self, sid: Optional[int]):
        d = filedialog.askdirectory(parent=self, title="Importer un dossier dans le Grimoire",
                                    initialdir=self.store.get("last_dir", os.path.expanduser("~")))
        if not d:
            return
        sid = sid or self.current_sid()
        self.set_status("📂 Import en cours…", "WARN")
        self.update_idletasks()
        ids, n = import_folder(self.store, sid, d, progress=lambda m: (self.set_status(m, "WARN"), self.update_idletasks()))
        self._after_add(ids, sid, msg=f"📂 {len(ids)} fichier(s) importé(s) dans {n} sujet(s).")

    def record_memo(self):
        sid = self.current_sid()
        r = RecorderDialog(self, sid).wait()
        if not r:
            return
        try:
            iid = add_file(self.store, sid, r["path"], r["title"], move=True, typ="voice")
            self.store.set_meta(iid, duration=r["duration"])
        except Exception as ex:
            messagebox.showerror(APP_NAME, f"Mémo non enregistré : {ex}", parent=self)
            return
        self._after_add([iid], sid, msg=f"🎙 Mémo de {fmt_dur(r['duration'])} ajouté.",
                        transcribe_ids=[iid] if r.get("transcribe") else [])

    def smart_paste(self, plain: bool = False):
        sid = self.current_sid()
        if not plain:
            try:
                from PIL import ImageGrab  # type: ignore
                clip = ImageGrab.grabclipboard()
            except Exception:
                clip = None
            if isinstance(clip, list) and clip:
                paths = [p for p in clip if isinstance(p, str) and os.path.exists(p)]
                if paths:
                    self.add_paths(paths, sid)
                    return
            elif clip is not None and hasattr(clip, "save"):
                iid = add_image_pil(self.store, sid, clip)
                self._after_add([iid], sid, msg="🖼 Image collée.")
                return
        try:
            text = self.clipboard_get()
        except tk.TclError:
            text = ""
        if not text.strip():
            self.set_status("Le presse-papiers est vide (ou contient un format non reconnu).", "WARN")
            return
        if plain:
            first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "Note")
            iid = self.store.add_item(sid, "note", title=first[:80], body=runs_to_json([[text.strip(), []]]))
            self._after_add([iid], sid, enrich=False)
            return
        self.add_text_note(text, sid)

    # ------------------------------------------------------------ travaux de fond sur une fiche
    def refetch(self, iid: int):
        self.store.set_meta(iid, pending=True)
        self.refresh_item_view(iid)
        self.run_job(lambda: enrich_link(self.store, iid), lambda _r: self._enriched(iid), "récupération des infos")

    def reextract(self, iid: int):
        self.run_job(lambda: enrich_file(self.store, iid), lambda _r: (self._enriched(iid), self.set_status("Texte relu.", "OK")),
                     "extraction du texte")

    def ocr_item(self, iid: int):
        it = self.store.item(iid)
        if not it:
            return
        p = Paths.abs(it.get("file") or "")
        self.set_status("🔤 Lecture du texte de l'image (OCR)…", "WARN")

        def job():
            return ocr_image(p)

        def done(res):
            txt, err = res
            if txt:
                m = self.store.meta(self.store.item(iid) or {})
                m["ocr"] = now_iso()
                self.store.update_item(iid, touch=False, extracted=txt, meta=m)
                self.refresh_item_view(iid)
                self.set_status(f"🔤 {len(txt.split())} mot(s) lu(s) dans l'image : ils sont maintenant cherchables.", "OK")
            else:
                self.set_status("OCR : " + (err or "aucun texte trouvé."), "WARN")
                if err:
                    messagebox.showinfo(APP_NAME, "Lecture du texte impossible :\n" + err, parent=self)
        self.run_job(job, done, "OCR")

    def transcribe_item(self, iid: int, quiet: bool = False):
        it = self.store.item(iid)
        if not it:
            return
        if not whisper_available():
            if not quiet:
                if messagebox.askyesno(APP_NAME, WHISPER_HELP + "\n\nInstaller faster-whisper maintenant ?", parent=self):
                    self.install_whisper(confirm=False)
            return
        p = Paths.abs(it.get("file") or "")
        model = self.store.get("whisper_model", "small")
        self.set_status("📝 Transcription du mémo en cours (peut prendre un moment)…", "WARN")

        def job():
            return transcribe(p, model, progress=lambda m: self.post(lambda: self.set_status(m, "WARN")))

        def done(res):
            txt, err = res
            if txt:
                cur = self.store.item(iid) or {}
                m = self.store.meta(cur)
                m["transcribed"] = now_iso()
                m["whisper_model"] = model
                self.store.update_item(iid, touch=False, extracted=txt, meta=m)
                self.refresh_item_view(iid)
                self.set_status("📝 Transcription terminée : le texte est cherchable.", "OK")
            else:
                self.set_status("Transcription : " + (err or "aucun texte."), "WARN")
        self.run_job(job, done, "transcription")

    def capture_page_dialog(self):
        url = ""
        try:
            clip = self.clipboard_get().strip()
            if is_url(clip):
                url = clip
        except tk.TclError:
            pass
        u = ask_string(self, "Capturer une page web", "Adresse de la page à garder hors ligne (HTML + PDF + image pleine page) :", url)
        if not u or not u.strip():
            return
        sid = self.current_sid()
        iid = self.store.add_item(sid, "page", title=placeholder_title(fix_url(u.strip())), url=fix_url(u.strip()),
                                  source=domain_of(fix_url(u.strip())), meta={"pending": True, "auto_title": True})
        self._after_add([iid], sid, enrich=False, msg="🌐 Capture de la page en cours…")
        self.capture_item(iid, as_page=True)

    def capture_item(self, iid: int, as_page: bool = False):
        it = self.store.item(iid)
        if not it or not it.get("url"):
            return
        st = self.store
        url = it["url"]
        dest = os.path.join(st.subject_media_dir(it["subject_id"]), "_pages")
        self.set_status("🌐 Capture de la page (HTML, PDF, image)…", "WARN")

        def job():
            return capture_page(url, dest, it.get("title") if not st.meta(it).get("auto_title") else "",
                                progress=lambda m: self.post(lambda: self.set_status("🌐 " + m, "WARN")))

        def done(res):
            cur = st.item(iid)
            if not cur:
                return
            m = st.meta(cur)
            files = [Paths.rel(p) for p in res.get("files", [])]
            upd: Dict[str, Any] = {}
            if as_page or cur["type"] == "page":
                html_rel = Paths.rel(res["html"]) if res.get("html") else ""
                if html_rel:
                    upd["file"] = html_rel
                    files = [f for f in files if f != html_rel]
                if res.get("title") and m.get("auto_title"):
                    upd["title"] = res["title"][:300]
                if res.get("text"):
                    upd["extracted"] = res["text"]
                m["description"] = res.get("description", "") or m.get("description", "")
            else:
                if res.get("text"):
                    upd["extracted"] = ((cur.get("extracted") or "") + "\n\n" + res["text"]).strip()[:MAX_EXTRACT]
            m["extra_files"] = list(dict.fromkeys((m.get("extra_files") or []) + files))
            m["captured"] = now_iso()
            m["pending"] = False
            if res.get("png") and not cur.get("thumb"):
                try:
                    from PIL import Image  # type: ignore
                    with Image.open(res["png"]) as im:
                        crop = im.crop((0, 0, im.width, min(im.height, int(im.width * 0.66))))
                        tp = thumb_path(st, cur["subject_id"], iid)
                        if save_thumb_image(crop, tp):
                            upd["thumb"] = Paths.rel(tp)
                except Exception as ex:
                    logger.info("vignette capture : %s", ex)
            upd["meta"] = m
            st.update_item(iid, touch=False, **upd)
            self.refresh_item_view(iid)
            errs = res.get("errors") or []
            if res.get("files"):
                self.set_status(f"🌐 Page capturée ({len(res['files'])} fichier(s))" + (f" — {errs[0]}" if errs else "."),
                                "OK" if not errs else "WARN")
            else:
                self.set_status("⚠ Capture impossible : " + ("; ".join(errs) or "erreur inconnue"), "ERR")
        self.run_job(job, done, "capture de page")

    def send_to_archiveur(self, url: str):
        copy_to_clipboard(self, url)
        arch = os.path.join(padawan_dir(), "archiveur5.py")
        if not os.path.isfile(arch):
            arch = os.path.join(BASE, "archiveur5.py")
        if not os.path.isfile(arch):
            messagebox.showinfo(APP_NAME, "Lien copié. archiveur5.py est introuvable dans le dossier Padawan.", parent=self)
            return
        try:
            popen_hidden([find_pythonw(), arch], cwd=os.path.dirname(arch))
            self.set_status("📦 Lien copié et Archiveur 5 lancé : colle le lien (Ctrl+V) dans l'Archiveur.", "OK")
        except Exception as ex:
            messagebox.showerror(APP_NAME, f"Lancement de l'Archiveur impossible : {ex}", parent=self)

    def copy_citation(self, iid: int):
        it = self.store.item(iid)
        if not it:
            return
        m = self.store.meta(it)
        parts = []
        if it["type"] == "quote":
            parts.append(f"« {(it.get('body_text') or '').strip()} »")
            src = ", ".join(x for x in (it.get("author"), it.get("source"), m.get("page") and f"p. {m['page']}",
                                        it.get("event_date")) if x)
            if src:
                parts.append("— " + src)
        else:
            parts.append(", ".join(x for x in (it.get("author"), f"« {it.get('title') or ''} »", it.get("source") or m.get("site"),
                                               it.get("event_date")) if x and x != "«  »"))
        if it.get("url"):
            parts.append(f"{it['url']} (consulté le {fmt_date(today(), False)})")
        txt = "\n".join(parts)
        copy_to_clipboard(self, txt)
        self.set_status("📋 Citation copiée : " + txt.replace("\n", " ")[:120], "OK")

    # ------------------------------------------------------------ ouvrir
    def open_item(self, iid: int):
        it = self.store.item(iid)
        if not it:
            return
        typ = it["type"]
        fpath = Paths.abs(it.get("file") or "")
        if typ == "note" or typ == "quote":
            self.select_ids([iid])
            self.after(60, lambda: (self.nb.select(self.tab_body), self.editor.t.focus_set()))
        elif typ == "image" and fpath and os.path.isfile(fpath):
            self.view_image(iid)
        elif typ in ("audio", "voice") and fpath:
            self.select_ids([iid])
            self.after(60, lambda: self.play_toggle(iid))
        elif fpath and os.path.isfile(fpath):
            open_path(fpath)
        elif it.get("url"):
            open_url(it["url"])
        self.store.update_item(iid, touch=False, opened=now_iso())

    def view_image(self, iid: int):
        imgs = [r for r in (self.results if self.cur_view == "search" else self.visible)
                if r["type"] == "image" and r.get("file") and os.path.isfile(Paths.abs(r["file"]))]
        if not any(r["id"] == iid for r in imgs):
            it = self.store.item(iid)
            imgs = [it] if it else []
        if not imgs:
            return
        idx = next((k for k, r in enumerate(imgs) if r["id"] == iid), 0)
        ImageViewer(self, [(Paths.abs(r["file"]), r.get("title") or "") for r in imgs], idx)

    def open_reader(self):
        pool = self.results if self.cur_view == "search" else self.visible
        if not pool:
            self.set_status("Rien à lire dans cette vue.", "WARN")
            return
        ids = [r["id"] for r in pool]
        if len(self.selected) > 1:
            ids = [i for i in ids if i in self.selected]
            idx = 0
        else:
            idx = ids.index(self.cur_item) if self.cur_item in ids else 0
        self._commit_pending()
        ReaderWindow(self, ids, idx, self.terms if self.cur_view == "search" else None)

    def goto_item(self, iid: int):
        it = self.store.item(iid)
        if not it:
            return
        if it.get("deleted"):
            self.open_view("v:trash")
            return
        pool = {r["id"] for r in (self.results if self.cur_view == "search" else self.visible)}
        if iid not in pool:
            self.open_view(f"s:{it['subject_id']}")
            if iid not in {r["id"] for r in self.visible}:
                self.cb_type.current(0)
                self.cb_tag.current(0)
                self.refresh_items()
        self.select_ids([iid], see=True)
        self.lift()

    def follow_ref(self, title: str):
        title = title.strip()
        it = self.store.find_by_title(title)
        if it:
            self.goto_item(it["id"])
            return
        sid = self.store.find_subject(title)
        if sid:
            self.open_view(f"s:{sid}")
            return
        if messagebox.askyesno(APP_NAME, f"Aucune fiche ni sujet « {title} ».\n\nCréer une note avec ce titre ?", parent=self):
            sid = self.current_sid()
            iid = self.store.add_item(sid, "note", title=title, body="", meta={"auto_title": False})
            self._after_add([iid], sid, enrich=False)
            self.nb.select(self.tab_body)
            self.editor.t.focus_set()

    def choose_reference(self) -> Optional[str]:
        got: List[Tuple[str, int, str]] = []
        p = Palette(self, "ref", on_pick=lambda pick: got.append(pick))
        self.wait_window(p)
        for _ in range(30):
            if got:
                break
            self.update()
            time.sleep(0.01)
        if not got:
            return None
        kind, ident, label = got[0]
        if kind == "s":
            s = self.store.subject(ident)
            return s["name"] if s else None
        if kind == "i":
            it = self.store.item(ident)
            return (it.get("title") or "").strip() if it else None
        return label

    def open_palette(self):
        def pick(p):
            kind, ident, _lab = p
            if kind == "s":
                self.open_view(f"s:{ident}")
            elif kind == "i":
                self.goto_item(ident)
        Palette(self, "goto", on_pick=pick)

    # ================================================================ modifier les fiches
    def _sel_items(self) -> List[int]:
        if self.cur_view == "v:trash":
            return []
        return list(self.selected)

    def rename_any(self):
        if self.focus_get() is self.tree:
            self.rename_subject()
        else:
            self.rename_item()

    def rename_item(self):
        if not self.cur_item:
            if self.cur_view.startswith("s:"):
                self.rename_subject()
            return
        self.e_title.focus_set()
        self.e_title.select_range(0, "end")
        self.e_title.icursor("end")

    def toggle_fav(self):
        ids = self._sel_items()
        if not ids:
            return
        its = [self.store.item(i) for i in ids]
        val = 0 if all(it and it.get("fav") for it in its) else 1
        for i in ids:
            self.store.update_item(i, touch=False, fav=val)
        self.refresh_tree()
        self.refresh_items(keep=ids)
        self.set_status(("★ Ajouté aux favoris" if val else "☆ Retiré des favoris") + f" ({len(ids)}).", "OK")

    def toggle_pin(self):
        ids = self._sel_items()
        if not ids:
            return
        its = [self.store.item(i) for i in ids]
        val = 0 if all(it and it.get("pinned") for it in its) else 1
        for i in ids:
            self.store.update_item(i, touch=False, pinned=val)
        self.refresh_tree()
        self.refresh_items(keep=ids)
        self.set_status(("📌 Épinglé en haut" if val else "Désépinglé") + f" ({len(ids)}).", "OK")

    def edit_tags(self):
        ids = self._sel_items()
        if not ids:
            return
        if len(ids) == 1:
            self.e_tags.focus_set()
            self.e_tags.icursor("end")
            return
        r = ask_string(self, "Étiquettes", f"Ajouter ces étiquettes aux {len(ids)} fiches (séparées par des virgules ; "
                                           "« -mot » pour en retirer une) :")
        if not r:
            return
        add = [t for t in tag_list(r) if not t.startswith("-")]
        rem = [norm(t[1:]) for t in tag_list(r) if t.startswith("-")]
        for i in ids:
            it = self.store.item(i)
            cur = [t for t in tag_list(it.get("tags") or "") if norm(t) not in rem]
            self.store.update_item(i, tags=", ".join(cur + add))
        self.refresh_tree()
        self.refresh_items(keep=ids)

    def move_selected(self, copy: bool = False, target: Optional[int] = None):
        ids = self._sel_items()
        if not ids:
            self.set_status("Choisis d'abord une ou plusieurs fiches.", "WARN")
            return
        self._commit_pending()
        if target is None:
            target = SubjectChooser(self, self, "Copier vers" if copy else "Déplacer vers",
                                    f"{'Copier' if copy else 'Déplacer'} {len(ids)} fiche(s) dans quel sujet ?").wait()
        if not target:
            return
        name = self.store.subject_path(target)
        if copy:
            new = self.store.copy_items(ids, target)
            self.push_undo(f"copie de {len(new)} fiche(s)", lambda: self.store.trash_items(new))
            self.refresh_tree()
            self.refresh_items(keep=ids)
            self.reveal_subject(target)
            self.set_status(f"⧉ {len(new)} fiche(s) copiée(s) dans « {name} ».  (Ctrl+Z pour annuler)", "OK")
        else:
            old = self.store.move_items(ids, target)

            def undo(old=old):
                for i, sid in old:
                    self.store.move_items([i], sid)
            self.push_undo(f"déplacement de {len(old)} fiche(s)", undo)
            self.refresh_tree()
            self.refresh_items(keep=ids)
            self.reveal_subject(target)
            self.set_status(f"📁 {len(old)} fiche(s) déplacée(s) dans « {name} ».  (Ctrl+Z pour annuler)", "OK")

    def move_item_step(self, d: int):
        if not self.cur_view.startswith("s:") or len(self.selected) != 1:
            self.set_status("Monter/descendre : ouvre un sujet, choisis une fiche (tri « Ordre manuel »).", "WARN")
            return
        if self.sort != "manual":
            self.sort = "manual"
            self.cb_sort.current(0)
            self.store.set("sort", "manual")
        iid = self.selected[0]
        it = self.store.item(iid)
        sibs = sorted([r for r in self.store.items_in([it["subject_id"]])], key=lambda r: (-int(r.get("pinned") or 0),
                                                                                         float(r.get("sort") or 0)))
        ids = [r["id"] for r in sibs]
        i = ids.index(iid)
        j = max(0, min(len(ids) - 1, i + d))
        if i == j:
            return
        ids.insert(j, ids.pop(i))
        with self.store.lock:
            for k, x in enumerate(ids):
                self.store.conn.execute("UPDATE items SET sort=? WHERE id=?", (k + 1, x))
            self.store.conn.commit()
        self.store._touch()
        self.refresh_items(keep=[iid])

    def delete_selected(self):
        if self.cur_view == "v:trash":
            self.trash_purge()
            return
        ids = self._sel_items()
        if not ids:
            return
        self._commit_pending()
        self.player.stop()
        pool = [r["id"] for r in (self.results if self.cur_view == "search" else self.visible)]
        nxt = None
        for i in pool[pool.index(ids[-1]) + 1:] if ids[-1] in pool else []:
            if i not in ids:
                nxt = i
                break
        if nxt is None:
            for i in reversed(pool[:pool.index(ids[0])] if ids[0] in pool else []):
                if i not in ids:
                    nxt = i
                    break
        batch = self.store.trash_items(ids)
        self.push_undo(f"suppression de {len(ids)} fiche(s)", lambda: self.store.restore_batch(batch))
        self.editor_item = None
        self.selected = []
        self.refresh_tree()
        self.refresh_items(keep=[nxt] if nxt else None)
        self.set_status(f"🗑 {len(ids)} fiche(s) mise(s) à la corbeille.  Ctrl+Z pour annuler.", "OK")

    def push_undo(self, label: str, fn: Callable[[], Any]):
        self.undo_stack.append((label, fn))
        self.undo_stack = self.undo_stack[-50:]

    def do_undo(self):
        if not self.undo_stack:
            self.set_status("Rien à annuler.", "DIM")
            return
        label, fn = self.undo_stack.pop()
        try:
            fn()
        except Exception as ex:
            logger.error("annulation : %s", traceback.format_exc())
            self.set_status(f"Annulation impossible : {ex}", "ERR")
            return
        if self.cur_view != "search" and not self._view_valid(self.cur_view):
            self.cur_view = "v:all"
        self.refresh_tree()
        self.refresh_items(keep=list(self.selected))
        self.set_status(f"↩ Annulé : {label}.", "OK")

    # ================================================================ sujets
    def _tree_sid(self) -> Optional[int]:
        sel = self.tree.selection()
        if sel and sel[0].startswith("s:"):
            return int(sel[0][2:])
        return self.current_sid(strict=True)

    def new_subject(self, parent: Optional[int] = None):
        r = SubjectDialog(self, self, "Nouveau sous-sujet" if parent else "Nouveau sujet", None, parent).wait()
        if not r:
            return
        sid = self.store.add_subject(r["name"], r["parent_id"], r["icon"], r["color"], r["description"], bool(r["pinned"]))
        if r["parent_id"]:
            self.store.update_subject(r["parent_id"], expanded=1)
        self.refresh_tree()
        self.open_view(f"s:{sid}")
        self.reveal_subject(sid)
        self.set_status(f"📁 Sujet « {r['name']} » créé. Ajoute-y des notes, liens, images…", "OK")

    def edit_subject(self, sid: Optional[int] = None):
        sid = sid or self._tree_sid()
        s = self.store.subject(sid) if sid else None
        if not s:
            return
        r = SubjectDialog(self, self, "Modifier le sujet", s).wait()
        if not r:
            return
        par = r["parent_id"]
        if par != s["parent_id"] and not self.store.move_subject(sid, par):
            messagebox.showwarning(APP_NAME, "Un sujet ne peut pas aller dans lui-même ou un de ses sous-sujets.", parent=self)
            par = s["parent_id"]
        self.store.update_subject(sid, name=r["name"], icon=r["icon"], color=r["color"], description=r["description"],
                                  pinned=r["pinned"])
        self.refresh_tree()
        self.reveal_subject(sid)
        self.refresh_items(keep=list(self.selected))

    def rename_subject(self):
        sid = self._tree_sid()
        s = self.store.subject(sid) if sid else None
        if not s:
            return
        r = ask_string(self, "Renommer le sujet", "Nouveau nom :", s["name"])
        if r and r.strip() and r.strip() != s["name"]:
            self.store.update_subject(sid, name=r.strip())
            self.refresh_tree()
            self._header()

    def delete_subject(self, sid: Optional[int] = None):
        sid = sid or self._tree_sid()
        s = self.store.subject(sid) if sid else None
        if not s:
            return
        n = len(self.store.items_in([sid] + self.store.descendants(sid)))
        k = len(self.store.descendants(sid))
        msg = f"Mettre le sujet « {s['name']} » à la corbeille ?"
        if n or k:
            msg += f"\n\nIl contient {n} fiche(s)" + (f" et {k} sous-sujet(s)" if k else "") + " qui iront aussi à la corbeille."
        msg += "\n\nTu pourras le restaurer depuis la Corbeille (ou Ctrl+Z)."
        if not messagebox.askyesno(APP_NAME, msg, parent=self):
            return
        self._commit_pending()
        batch = self.store.trash_subject(sid)
        self.push_undo(f"suppression du sujet « {s['name']} »", lambda: self.store.restore_batch(batch))
        if self.cur_view == f"s:{sid}" or not self._view_valid(self.cur_view):
            self.cur_view = f"s:{s['parent_id']}" if s["parent_id"] else "v:all"
        self.refresh_tree()
        self.open_view(self.cur_view)
        self.set_status(f"🗑 Sujet « {s['name']} » mis à la corbeille.  Ctrl+Z pour annuler.", "OK")

    def reorder_subject(self, d: int, sid: Optional[int] = None):
        sid = sid or self._tree_sid()
        if sid:
            self.store.reorder_subject(sid, d)
            self.refresh_tree()
            self.reveal_subject(sid, flash=False)

    def promote_subject(self, sid: Optional[int] = None):
        sid = sid or self._tree_sid()
        if sid and self.store.move_subject(sid, None):
            self.refresh_tree()
            self.reveal_subject(sid)

    def rename_subject_id(self, sid: int):
        s = self.store.subject(sid)
        r = ask_string(self, "Renommer le sujet", "Nouveau nom :", s["name"]) if s else None
        if r and r.strip() and r.strip() != s["name"]:
            self.store.update_subject(sid, name=r.strip())
            self.refresh_tree()
            self._header()

    def manage_subjects(self):
        SubjectManager(self, self)

    def _subjects_menu(self, mb):
        m = new_menu(mb)
        cur = lambda: self._tree_sid()
        def need(fn):
            def run():
                sid = cur()
                if not sid:
                    messagebox.showinfo(APP_NAME, "Choisis d'abord un sujet dans l'arbre de gauche.", parent=self)
                    return
                fn(sid)
            return run
        m.add_command(label="🗂 Gérer les sujets…", accelerator="Ctrl+Maj+G", command=self.manage_subjects)
        m.add_separator()
        m.add_command(label="📁 Nouveau sujet principal…", accelerator="Ctrl+Maj+N", command=lambda: self.new_subject(None))
        m.add_command(label="📂 Nouveau sous-sujet du sujet choisi…", accelerator="Inser", command=need(self.new_subject))
        m.add_separator()
        m.add_command(label="✏ Renommer", accelerator="F2", command=need(self.rename_subject_id))
        m.add_command(label="⚙ Modifier (icône, couleur, parent, description)…", command=need(self.edit_subject))
        m.add_command(label="😀 Changer l'icône…", command=need(self.set_subject_icon))
        m.add_command(label="🎨 Changer la couleur…", command=need(lambda s: self.set_subject_color(s)))
        m.add_separator()
        m.add_command(label="⬆ Monter", accelerator="Alt+Haut", command=need(lambda s: self.reorder_subject(-1, s)))
        m.add_command(label="⬇ Descendre", accelerator="Alt+Bas", command=need(lambda s: self.reorder_subject(1, s)))
        m.add_command(label="📁 Déplacer / ranger dans un autre sujet…", command=need(self._subject_into))
        m.add_command(label="⤴ Rendre sujet principal", command=need(self.promote_subject))
        m.add_command(label="🔀 Fusionner dans…", command=need(self.merge_subject))
        m.add_separator()
        m.add_command(label="🗑 Supprimer (corbeille)", command=need(self.delete_subject))
        m.add_separator()
        m.add_command(label="Astuce : glisse un sujet sur un autre pour en faire un sous-sujet ; dans le vide = principal",
                      state="disabled")
        return m

    def merge_subject(self, sid: int):
        s = self.store.subject(sid)
        if not s:
            return
        dst = SubjectChooser(self, self, "Fusionner", f"Fusionner « {s['name']} » dans quel sujet ?\n"
                                                    "Ses fiches et sous-sujets y passent, puis il va à la corbeille.",
                             exclude=[sid] + self.store.descendants(sid)).wait()
        if not dst:
            return
        res = self.store.merge_subjects(sid, dst)

        def undo(res=res):
            self.store.restore_batch(res["batch"])
            for k in res["kids"]:
                self.store.update_subject(k, parent_id=res["src"])
            for i, old in res["moved"]:
                self.store.move_items([i], old)
        self.push_undo(f"fusion de « {s['name']} »", undo)
        self.refresh_tree()
        self.open_view(f"s:{dst}")
        self.set_status(f"🔀 « {s['name']} » fusionné ({len(res['moved'])} fiche(s)).  Ctrl+Z pour annuler.", "OK")

    def set_subject_icon(self, sid: int):
        s = self.store.subject(sid)
        r = EmojiPicker(self, s["icon"]).wait()
        if r is not None:
            self.store.update_subject(sid, icon=r or "📁")
            self.refresh_tree()
            self._header()

    def set_subject_color(self, sid: int, color: Optional[str] = None):
        if color is None:
            from tkinter import colorchooser
            r = colorchooser.askcolor(self.store.subject(sid)["color"] or "#FFFF55", parent=self, title="Couleur du sujet")
            if not r or not r[1]:
                return
            color = r[1]
        self.store.update_subject(sid, color=color)
        self.swatches.pop(color, None)
        self.refresh_tree()
        self._header()
        if self._effective_mode() == "cards":
            self.fill_cards()

    def _tree_menu(self, e):
        row = self.tree.identify_row(e.y)
        m = new_menu(self)
        if row.startswith("s:"):
            sid = int(row[2:])
            s = self.store.subject(sid)
            if row not in self.tree.selection():
                self.tree.selection_set(row)
            m.add_command(label=f"{s['icon']} {s['name']}", state="disabled")
            m.add_separator()
            m.add_command(label="📂 Nouveau sous-sujet…", accelerator="Inser", command=lambda: self.new_subject(sid))
            m.add_command(label="📝 Nouvelle note ici", command=self.new_note)
            m.add_command(label="📋 Coller ici", command=self.smart_paste)
            m.add_separator()
            m.add_command(label="✏ Renommer", accelerator="F2", command=self.rename_subject)
            m.add_command(label="⚙ Modifier (icône, couleur, description)…", command=lambda: self.edit_subject(sid))
            m.add_command(label="😀 Icône…", command=lambda: self.set_subject_icon(sid))
            cm = new_menu(m)
            for col in SUBJECT_COLORS:
                cm.add_command(label="■■■  " + col, foreground=col, activeforeground=col,
                               command=lambda c=col: self.set_subject_color(sid, c))
            cm.add_command(label="Autre couleur…", command=lambda: self.set_subject_color(sid))
            m.add_cascade(label="🎨 Couleur", menu=cm)
            m.add_command(label=("📌 Désépingler" if s["pinned"] else "📌 Épingler en haut"),
                          command=lambda: (self.store.update_subject(sid, pinned=0 if s["pinned"] else 1), self.refresh_tree()))
            m.add_command(label="⬆ Monter", accelerator="Alt+Haut", command=lambda: self.reorder_subject(-1))
            m.add_command(label="⬇ Descendre", accelerator="Alt+Bas", command=lambda: self.reorder_subject(1))
            if s["parent_id"]:
                m.add_command(label="⤴ Rendre sujet principal",
                              command=lambda: self.promote_subject(sid))
            m.add_command(label="📁 Ranger dans…", command=lambda: self._subject_into(sid))
            m.add_command(label="🔀 Fusionner dans…", command=lambda: self.merge_subject(sid))
            m.add_separator()
            m.add_command(label="🌐 Exporter en HTML…", command=lambda: self.export_dialog(sid, False))
            m.add_command(label="📦 Exporter en ZIP…", command=lambda: self.export_dialog(sid, True))
            m.add_command(label="📥 Importer un dossier ici…", command=lambda: self.import_folder_dialog(sid))
            m.add_command(label="🗂 Ouvrir son dossier de fichiers", command=lambda: open_path(self.store.subject_media_dir(sid)))
            m.add_separator()
            m.add_command(label="🗑 Supprimer (corbeille)", accelerator="Suppr", command=lambda: self.delete_subject(sid))
        elif row.startswith("t:"):
            tg = row[2:]
            m.add_command(label=f"✏ Renommer l'étiquette #{tg}…", command=lambda: self.rename_tag(tg))
            m.add_command(label=f"✖ Retirer #{tg} de toutes les fiches", command=lambda: self.remove_tag(tg))
        elif row == "v:trash":
            m.add_command(label="🧹 Vider la corbeille", command=self.trash_empty)
        else:
            m.add_command(label="📁 Nouveau sujet…", command=lambda: self.new_subject(None))
            m.add_command(label="📥 Importer un dossier…", command=lambda: self.import_folder_dialog(None))
        popup(m, e)

    def _subject_into(self, sid: int):
        dst = SubjectChooser(self, self, "Ranger le sujet", "Ranger ce sujet dans :", allow_root=True,
                             exclude=[sid] + self.store.descendants(sid)).wait()
        if dst is None:
            return
        if self.store.move_subject(sid, dst or None):
            if dst:
                self.store.update_subject(dst, expanded=1)
            self.refresh_tree()
            self.reveal_subject(sid)

    def rename_tag(self, tg: str):
        r = ask_string(self, "Renommer l'étiquette", f"Nouveau nom pour #{tg} :", tg)
        if not r or not r.strip():
            return
        n = 0
        for it in self.store.items_where("tags<>''"):
            tl = tag_list(it["tags"])
            if any(norm(t) == norm(tg) for t in tl):
                self.store.update_item(it["id"], touch=False, tags=", ".join(r.strip() if norm(t) == norm(tg) else t for t in tl))
                n += 1
        if self.cur_view == f"t:{tg}":
            self.cur_view = f"t:{norm_tags(r)}"
        self.refresh_all()
        self.set_status(f"🏷 Étiquette renommée sur {n} fiche(s).", "OK")

    def remove_tag(self, tg: str):
        if not messagebox.askyesno(APP_NAME, f"Retirer l'étiquette #{tg} de toutes les fiches ?", parent=self):
            return
        for it in self.store.items_where("tags<>''"):
            tl = tag_list(it["tags"])
            if any(norm(t) == norm(tg) for t in tl):
                self.store.update_item(it["id"], touch=False, tags=", ".join(t for t in tl if norm(t) != norm(tg)))
        if self.cur_view == f"t:{tg}":
            self.cur_view = "v:tags"
        self.refresh_all()

    # ================================================================ menus contextuels
    def item_menu(self, e):
        ids = self._sel_items()
        if not ids:
            return
        m = self._build_item_menu(ids)
        popup(m, e)

    def _item_more(self):
        ids = self._sel_items()
        if not ids:
            return
        m = self._build_item_menu(ids)
        b = self.b_more
        try:
            m.tk_popup(b.winfo_rootx(), b.winfo_rooty() + b.winfo_height())
        finally:
            m.grab_release()

    def _build_item_menu(self, ids: List[int]):
        m = new_menu(self)
        it = self.store.item(ids[0]) if len(ids) == 1 else None
        if it:
            fpath = Paths.abs(it.get("file") or "")
            m.add_command(label="↗ Ouvrir", accelerator="Entrée", command=lambda: self.open_item(it["id"]))
            m.add_command(label="📖 Mode lecture", accelerator="F11", command=self.open_reader)
            if it.get("url"):
                m.add_command(label="🌐 Ouvrir le lien dans le navigateur", command=lambda: open_url(it["url"]))
                m.add_command(label="📋 Copier le lien", command=lambda: copy_to_clipboard(self, it["url"]))
            if fpath and os.path.isfile(fpath):
                m.add_command(label="🗂 Montrer le fichier dans l'Explorateur", command=lambda: reveal_in_explorer(fpath))
            m.add_command(label="📋 Copier la citation (auteur, source, lien)", command=lambda: self.copy_citation(it["id"]))
            m.add_separator()
            m.add_command(label="✏ Renommer", accelerator="F2", command=self.rename_item)
        m.add_command(label="★ Favori oui/non", accelerator="Ctrl+D", command=self.toggle_fav)
        m.add_command(label="📌 Épingler oui/non", accelerator="Ctrl+P", command=self.toggle_pin)
        m.add_command(label="🏷 Étiquettes…", accelerator="Ctrl+T", command=self.edit_tags)
        m.add_separator()
        m.add_command(label="📁 Déplacer vers…", accelerator="Ctrl+M", command=lambda: self.move_selected(False))
        m.add_command(label="⧉ Copier vers…", command=lambda: self.move_selected(True))
        if self.cur_view.startswith("s:"):
            m.add_command(label="⬆ Monter", accelerator="Alt+Haut", command=lambda: self.move_item_step(-1))
            m.add_command(label="⬇ Descendre", accelerator="Alt+Bas", command=lambda: self.move_item_step(1))
        if it:
            tools = new_menu(m)
            if it["type"] in ("link", "video") and it.get("url"):
                tools.add_command(label="↻ Récupérer à nouveau titre et miniature", command=lambda: self.refetch(it["id"]))
                tools.add_command(label="🌐 Capturer la page complète", command=lambda: self.capture_item(it["id"]))
            if it["type"] == "video" and it.get("url"):
                tools.add_command(label="📦 Envoyer à l'Archiveur", command=lambda: self.send_to_archiveur(it["url"]))
            if it["type"] == "image":
                tools.add_command(label="🔤 Lire le texte de l'image (OCR)", command=lambda: self.ocr_item(it["id"]))
            if it["type"] in ("voice", "audio"):
                tools.add_command(label="📝 Transcrire en texte", command=lambda: self.transcribe_item(it["id"]))
            if it["type"] == "document":
                tools.add_command(label="↻ Extraire le texte", command=lambda: self.reextract(it["id"]))
            if it["type"] == "note":
                tools.add_command(label="💾 Enregistrer comme modèle de fiche…", command=self.save_as_template)
            tools.add_command(label="🌐 Exporter cette fiche en HTML…", command=lambda: self.export_selection([it["id"]]))
            m.add_cascade(label="🛠 Outils", menu=tools)
        else:
            m.add_command(label="🌐 Exporter la sélection en HTML…", command=self.export_selection)
            m.add_command(label="📖 Lire la sélection", command=self.open_reader)
        m.add_separator()
        m.add_command(label=f"🗑 Mettre à la corbeille ({len(ids)})", accelerator="Suppr", command=self.delete_selected)
        return m

    def view_menu(self, e):
        m = new_menu(self)
        m.add_command(label="📝 Nouvelle note", accelerator="Ctrl+N", command=self.new_note)
        m.add_command(label="🔗 Lien web…", accelerator="Ctrl+L", command=self.add_link_dialog)
        m.add_command(label="❝ Citation…", command=self.add_quote_dialog)
        m.add_command(label="📎 Fichier(s)…", accelerator="Ctrl+O", command=lambda: self.add_files_dialog(None))
        m.add_command(label="📋 Coller", accelerator="Ctrl+V", command=self.smart_paste)
        m.add_separator()
        m.add_command(label="☰ Liste", command=lambda: self.set_view_mode("list"))
        m.add_command(label="▦ Cartes", command=lambda: self.set_view_mode("cards"))
        m.add_command(label="🕘 Chronologie", command=lambda: self.set_view_mode("chrono"))
        m.add_separator()
        m.add_command(label="Tout sélectionner", accelerator="Ctrl+A", command=self.select_all)
        popup(m, e)

    # ================================================================ glisser-deposer interne
    def _tree_press(self, e):
        row = self.tree.identify_row(e.y)
        self.press = {"x": e.x_root, "y": e.y_root, "sid": int(row[2:]), "src": "subject"} if row.startswith("s:") else None

    def _drag_motion(self, e):
        p = self.press
        if not p:
            return None
        if self.drag is None:
            if abs(e.x_root - p["x"]) + abs(e.y_root - p["y"]) < 8:
                return None
            if p["src"] == "items":
                ids = p.get("ids") or list(self.selected)
                if not ids:
                    return None
                txt = f"📝 {len(ids)} fiche(s)" if len(ids) > 1 else "📝 " + ((self.store.item(ids[0]) or {}).get("title") or "")[:40]
                self.drag = {"src": "items", "ids": ids}
            else:
                s = self.store.subject(p["sid"])
                if not s:
                    return None
                txt = f"{s['icon']} {s['name']}"
                self.drag = {"src": "subject", "sid": p["sid"]}
            tw = tk.Toplevel(self)
            tw.overrideredirect(True)
            try:
                tw.attributes("-topmost", True)
                tw.attributes("-alpha", 0.9)
            except tk.TclError:
                pass
            tk.Label(tw, text=txt, bg=C["HI"], fg=C["ON_HI"], font=fnt("GUIB"), padx=8, pady=3).pack()
            self.drag["win"] = tw
            self.drag["hint"] = ""
        tw = self.drag["win"]
        tw.geometry(f"+{e.x_root + 14}+{e.y_root + 10}")
        tgt, desc = self._drop_target(e.x_root, e.y_root, e.state)
        self._drop_highlight(tgt)
        self.set_status(desc or "Lâche sur un sujet de la colonne de gauche (Ctrl = copier, Échap = annuler).", "WARN")
        return "break"

    def _drop_target(self, x: int, y: int, state: int) -> Tuple[Optional[str], str]:
        w = self.winfo_containing(x, y)
        if w is not self.tree or not self.drag:
            return None, ""
        row = self.tree.identify_row(y - self.tree.winfo_rooty())
        if self.drag["src"] == "items":
            if row.startswith("s:"):
                s = self.store.subject(row[2:])
                return row, f"{'Copier' if state & 0x4 else 'Déplacer'} dans « {s['name']} »"
            if row == "v:fav":
                return row, "Marquer comme favoris ★"
            if row == "v:pin":
                return row, "Épingler 📌"
            if row == "v:trash":
                return row, "Mettre à la corbeille"
            return None, ""
        sid = self.drag["sid"]
        if row.startswith("s:"):
            t = int(row[2:])
            if t == sid or t in self.store.descendants(sid):
                return None, "Impossible : un sujet ne va pas dans lui-même."
            s = self.store.subject(t)
            return row, (f"Placer avant « {s['name']} »" if state & 0x1 else f"Ranger dans « {s['name']} »  (Maj = placer avant)")
        if row == "v:trash":
            return row, "Mettre le sujet à la corbeille"
        if not row:
            return "root", "Mettre au niveau principal"
        return None, ""

    def _drop_highlight(self, tgt: Optional[str]):
        old = getattr(self, "_drop_row", None)
        if old and old != tgt and self.tree.exists(old):
            tags = [t for t in self.tree.item(old, "tags") if t != "drop"]
            self.tree.item(old, tags=tags)
        if tgt and tgt != "root" and self.tree.exists(tgt):
            tags = list(self.tree.item(tgt, "tags"))
            if "drop" not in tags:
                self.tree.item(tgt, tags=tags + ["drop"])
        self._drop_row = tgt

    def _drag_release(self, e):
        d = self.drag
        p = self.press
        self.press = None
        if d is None:
            if p and p.get("src") == "items" and p.get("ids") and len(p["ids"]) > 1 and not (e.state & 0x5) \
                    and e.widget in (self.lst, self.chr):
                row = e.widget.identify_row(e.y)
                if row.startswith("i:"):
                    self.select_ids([int(row[2:])])
            return None
        self.drag = None
        try:
            d["win"].destroy()
        except Exception:
            pass
        tgt, _desc = self._drop_target(e.x_root, e.y_root, e.state)
        self._drop_highlight(None)
        self.set_status("", "DIM")
        if not tgt:
            return "break"
        if d["src"] == "items":
            ids = d["ids"]
            self.select_ids(ids)
            if tgt.startswith("s:"):
                self.move_selected(copy=bool(e.state & 0x4), target=int(tgt[2:]))
            elif tgt == "v:fav":
                for i in ids:
                    self.store.update_item(i, touch=False, fav=1)
                self.refresh_tree()
                self.refresh_items(keep=ids)
            elif tgt == "v:pin":
                for i in ids:
                    self.store.update_item(i, touch=False, pinned=1)
                self.refresh_tree()
                self.refresh_items(keep=ids)
            elif tgt == "v:trash":
                self.delete_selected()
        else:
            sid = d["sid"]
            if tgt == "v:trash":
                self.delete_subject(sid)
            elif tgt == "root":
                self.store.move_subject(sid, None)
            elif e.state & 0x1:
                self.store.place_subject_before(sid, int(tgt[2:]))
            else:
                t = int(tgt[2:])
                if self.store.move_subject(sid, t):
                    self.store.update_subject(t, expanded=1)
            self.refresh_tree()
            self._header()
        return "break"

    # ================================================================ modeles de fiches
    def all_templates(self) -> Dict[str, Tuple[str, str]]:
        d = dict(TEMPLATES)
        for name, val in (self.store.get("templates_user", {}) or {}).items():
            if isinstance(val, (list, tuple)) and len(val) == 2:
                d[name] = (val[0], val[1])
        return d

    def _runs_to_md(self, runs: List[List[Any]]) -> str:
        out = []
        for text, tags in runs:
            pre = ""
            if "h1" in tags:
                pre = "# "
            elif "h2" in tags:
                pre = "## "
            elif "h3" in tags:
                pre = "### "
            elif "quote" in tags:
                pre = "> "
            t = text
            if "b" in tags and t.strip():
                t = f"**{t}**"
            elif "i" in tags and t.strip():
                t = f"*{t}*"
            if pre:
                t = "\n".join((pre + ln) if ln.strip() else ln for ln in t.split("\n"))
            out.append(t)
        return "".join(out).replace("☐ ", "[ ] ").replace("☑ ", "[ ] ")

    def save_as_template(self):
        it = self.store.item(self.cur_item) if self.cur_item else None
        if not it or it["type"] != "note":
            messagebox.showinfo(APP_NAME, "Ouvre d'abord une note : sa structure deviendra un modèle réutilisable.", parent=self)
            return
        self._commit_pending()
        it = self.store.item(it["id"])
        name = ask_string(self, "Nouveau modèle de fiche", "Nom du modèle :", it.get("title") or "")
        if not name or not name.strip():
            return
        user = self.store.get("templates_user", {}) or {}
        user[name.strip()] = ["📋", self._runs_to_md(runs_from_any(it.get("body") or ""))]
        self.store.set("templates_user", user)
        self._rebuild_add_menu()
        self.set_status(f"📋 Modèle « {name.strip()} » enregistré : menu Ajouter → Fiche à partir d'un modèle.", "OK")

    def manage_templates(self):
        user = self.store.get("templates_user", {}) or {}
        lines = ["# Modèles de fiches", "", "## Modèles fournis"]
        lines += [f"  {ic} {n}" for n, (ic, _m) in TEMPLATES.items()]
        lines += ["", "## Mes modèles"]
        lines += [f"  {v[0]} {n}" for n, v in user.items()] or ["  (aucun pour l'instant)"]
        lines += ["", "Pour créer un modèle : écris une note structurée, puis clic droit → Outils → "
                      "« Enregistrer comme modèle de fiche ».",
                  "Pour supprimer un de tes modèles : donne son nom ci-dessous (bouton Supprimer un modèle)."]
        TextDialog(self, "Modèles de fiches", "\n".join(lines), 700, 560)
        if user:
            n = ask_string(self, "Supprimer un modèle", "Nom exact du modèle à supprimer (laisser vide pour ne rien faire) :")
            if n and n.strip() in user:
                user.pop(n.strip())
                self.store.set("templates_user", user)
                self._rebuild_add_menu()
                self.set_status(f"Modèle « {n.strip()} » supprimé.", "OK")

    def _rebuild_add_menu(self):
        try:
            idx = self.menubar.index("Ajouter")
            self.menu_add = self._make_add_menu(self.menubar)
            self.menubar.entryconfigure(idx, menu=self.menu_add)
        except Exception:
            logger.error("menu Ajouter : %s", traceback.format_exc())

    # ================================================================ export / import / sauvegardes
    def export_dialog(self, sid: Optional[int], as_zip: bool):
        sid = sid or self.current_sid(strict=True)
        if not sid:
            messagebox.showinfo(APP_NAME, "Ouvre d'abord un sujet (colonne de gauche) à exporter.", parent=self)
            return
        self._commit_pending()
        s = self.store.subject(sid)
        os.makedirs(Paths.exports(), exist_ok=True)
        base = f"Grimoire_{safe_name(s['name'], 50)}_{dt.date.today().isoformat()}"
        out = filedialog.asksaveasfilename(parent=self, title="Exporter le sujet", initialdir=Paths.exports(),
                                           initialfile=base + (".zip" if as_zip else ".html"),
                                           defaultextension=".zip" if as_zip else ".html",
                                           filetypes=[("Archive ZIP", "*.zip")] if as_zip else [("Page web", "*.html")])
        if not out:
            return
        inc = True
        if self.store.descendants(sid):
            inc = messagebox.askyesno(APP_NAME, "Inclure aussi les sous-sujets ?", parent=self)
        self.set_status("Export en cours…", "WARN")

        def job():
            return export_subject_zip(self.store, sid, out, inc) if as_zip else export_subject(self.store, sid, out, inc)

        def done(n):
            if n is None:
                self.set_status("⚠ Export impossible (voir grimoire.log).", "ERR")
                return
            self.set_status(f"✔ {n} fiche(s) exportée(s) : {out}", "OK")
            if messagebox.askyesno(APP_NAME, f"{n} fiche(s) exportée(s) dans :\n{out}\n\nOuvrir maintenant ?", parent=self):
                open_path(out) if not as_zip else reveal_in_explorer(out)
        self.run_job(job, done, "export")

    def export_selection(self, ids: Optional[List[int]] = None):
        ids = ids or self._sel_items()
        if not ids:
            self.set_status("Choisis d'abord des fiches à exporter.", "WARN")
            return
        self._commit_pending()
        os.makedirs(Paths.exports(), exist_ok=True)
        it = self.store.item(ids[0])
        base = safe_name(it["title"], 50) if len(ids) == 1 and it else f"Selection_{len(ids)}_fiches"
        out = filedialog.asksaveasfilename(parent=self, title="Exporter en HTML", initialdir=Paths.exports(),
                                           initialfile=f"Grimoire_{base}.html", defaultextension=".html",
                                           filetypes=[("Page web", "*.html")])
        if not out:
            return
        n = export_subject(self.store, 0, out, item_ids=ids)
        self.set_status(f"✔ {n} fiche(s) exportée(s) : {out}", "OK")
        open_path(out)

    def backup_now(self):
        self._commit_pending()
        p = self.store.backup(force=True, tag="manuel")
        if p:
            self.set_status(f"💾 Sauvegarde : {p}   (tout est déjà enregistré automatiquement)", "OK")
        else:
            self.set_status("⚠ Sauvegarde impossible : " + self.store.last_error, "ERR")

    def restore_backup(self):
        p = filedialog.askopenfilename(parent=self, title="Restaurer une sauvegarde du Grimoire", initialdir=Paths.backups(),
                                       filetypes=[("Sauvegarde Grimoire", "grimoire_*.db"), ("Base SQLite", "*.db")])
        if not p:
            return
        try:
            c = sqlite3.connect(p)
            n = c.execute("SELECT COUNT(*) FROM items WHERE deleted IS NULL").fetchone()[0]
            c.close()
        except Exception as ex:
            messagebox.showerror(APP_NAME, f"Ce fichier n'est pas une sauvegarde valide : {ex}", parent=self)
            return
        if not messagebox.askyesno(APP_NAME, f"Remplacer le Grimoire actuel par cette sauvegarde ({n} fiche(s)) ?\n\n"
                                             "L'état actuel est d'abord sauvegardé (grimoire_..._avant_restauration.db).",
                                   parent=self, icon="warning"):
            return
        self._commit_pending()
        self.store.backup(force=True, tag="avant_restauration")
        try:
            src = sqlite3.connect(p)
            with self.store.lock:
                src.backup(self.store.conn)
            src.close()
            self.store._touch()
            if self.store.fts_ok:
                self.store.rebuild_fts()
        except Exception as ex:
            messagebox.showerror(APP_NAME, f"Restauration impossible : {ex}", parent=self)
            return
        self.undo_stack.clear()
        self.cur_view = "v:all"
        self.refresh_all()
        self.set_status(f"↩ Sauvegarde restaurée ({n} fiche(s)).", "OK")

    # ================================================================ outils
    def show_stats(self):
        st = self.store
        s = st.stats()
        L = ["# 📊 Statistiques du Grimoire", ""]
        L.append(f"  Fiches : {s['items']}")
        L.append(f"  Sujets : {s['subjects']}")
        L.append(f"  Favoris : {s['favs']}")
        L.append(f"  Épinglées : {s['pinned']}")
        L.append(f"  Mots écrits : {s['words']:,}".replace(",", " "))
        L.append(f"  Fichiers : {s['media_files']} ({human_size(s['media_size'])})")
        L.append(f"  Base de données : {human_size(s['db_size'])}")
        L.append(f"  Corbeille : {s['trash']} fiche(s)")
        L.append(f"  Dossier : {Paths.data}")
        L += ["", "## Par type"]
        mx = max([1] + list(s["by_type"].values()))
        for k in TYPE_ORDER:
            n = s["by_type"].get(k, 0)
            if n:
                L.append(f"{TYPES[k]['icon']} {TYPES[k]['plural']:<16} {'█' * max(1, int(28 * n / mx))} {n}")
        L += ["", "## Sujets les plus remplis"]
        tot = st.total_counts()
        top = sorted(((n, sid) for sid, n in tot.items() if n), reverse=True)[:12]
        mx = max([1] + [n for n, _s in top])
        for n, sid in top:
            subj = st.subject(sid)
            L.append(f"{subj['icon']} {subj['name'][:24]:<24} {'█' * max(1, int(24 * n / mx))} {n}")
        if not top:
            L.append("(tous les sujets sont encore vides)")
        L += ["", "## Ajouts par mois"]
        mx = max([1] + [n for _m, n in s["months"]])
        for m, n in reversed(s["months"]):
            L.append(f"{month_label(m + '-01'):<16} {'█' * max(1, int(28 * n / mx))} {n}")
        if s["tags"]:
            L += ["", "## Étiquettes les plus utilisées"]
            L.append("   ".join(f"#{t} ({n})" for t, n in s["tags"]))
        L += ["", "## Modules optionnels"]
        L.append(f"  Micro (sounddevice) : {'oui' if module_ok('sounddevice') else 'non installé'}")
        L.append(f"  Transcription (faster-whisper) : {'oui' if whisper_available() else 'non installé (menu Outils)'}")
        L.append(f"  Lecture PDF (pypdf) : {'oui' if module_ok('pypdf') else 'non installé'}")
        L.append(f"  Glisser-déposer (tkinterdnd2) : {'oui' if getattr(self, '_dnd_ok', False) else 'non disponible'}")
        L.append(f"  Lecteur audio (ffplay) : {'oui' if find_ff_tool('ffplay') else 'introuvable'}")
        L.append(f"  Capture de page (Edge) : {'oui' if find_browser() else 'introuvable'}")
        TextDialog(self, "Statistiques du Grimoire", "\n".join(L), 820, 680)

    def check_dialog(self):
        self.set_status("🔎 Vérification…", "WARN")
        self.update_idletasks()
        TextDialog(self, "Vérification du Grimoire", check_report(self.store), 860, 620)
        self.set_status("Vérification terminée.", "OK")

    def rebuild_index(self):
        n = self.store.rebuild_fts()
        self.set_status(f"🔄 Index de recherche reconstruit ({n} fiche(s)).", "OK")

    def install_whisper(self, confirm: bool = True):
        if whisper_available():
            messagebox.showinfo(APP_NAME, "faster-whisper est déjà installé : la transcription est disponible.", parent=self)
            return
        if confirm and not messagebox.askyesno(APP_NAME, WHISPER_HELP + "\n\nLancer l'installation maintenant ? "
                                               "(pip --user, quelques minutes, Internet requis)", parent=self):
            return
        py = find_python()
        self.set_status("⬇ Installation de faster-whisper en cours (quelques minutes)…", "WARN")

        def job():
            r = run_hidden([py, "-m", "pip", "install", "--user", "--upgrade", "faster-whisper"], 1800)
            return r.returncode, (r.stdout or "")[-2000:] + (r.stderr or "")[-2000:]

        def done(res):
            code, out = res if res else (1, "erreur inconnue")
            import importlib
            importlib.invalidate_caches()
            if code == 0:
                site_dirs = []
                try:
                    import site
                    site_dirs = [site.getusersitepackages()]
                except Exception:
                    pass
                for d in site_dirs:
                    if d not in sys.path and os.path.isdir(d):
                        sys.path.append(d)
                self.set_status("✔ faster-whisper installé : la transcription des mémos est disponible.", "OK")
                messagebox.showinfo(APP_NAME, "faster-whisper est installé.\nLe modèle sera téléchargé à la première "
                                              "transcription (une seule fois).", parent=self)
            else:
                self.set_status("⚠ Installation de faster-whisper échouée (voir le journal).", "ERR")
                logger.error("pip faster-whisper : %s", out)
                TextDialog(self, "Installation échouée", "# Installation de faster-whisper échouée\n\n" + out, 820, 520)
        self.run_job(job, done, "installation faster-whisper")

    def show_log(self):
        try:
            with open(Paths.log(), "r", encoding="utf-8", errors="replace") as f:
                txt = f.read()[-60000:]
        except OSError as ex:
            txt = str(ex)
        TextDialog(self, "Journal du Grimoire", "# grimoire.log\n" + Paths.log() + "\n\n" + txt, 1000, 640)

    def show_help(self, section: str = ""):
        d = TextDialog(self, "Aide du Grimoire", HELP_TEXT, 920, 680)
        if section:
            idx = d.t.search("Raccourcis clavier", "1.0", "end")
            if idx:
                d.t.see(idx)
                d.t.yview(idx)

    def about(self):
        s = self.store.stats()
        messagebox.showinfo(APP_NAME, f"📖 Grimoire\nCarnet de recherche du Projet Padawan\n\n"
                                      f"{s['items']} fiches · {s['subjects']} sujets\nDonnées : {Paths.data}\n"
                                      f"Python {sys.version.split()[0]} · Tk {self.tk.call('info', 'patchlevel')}", parent=self)

    # ================================================================ apparence
    def zoom(self, d: int):
        cur = int(self.store.get("font_delta", 0) or 0)
        new = 0 if d == 0 else max(FONT_DELTA_MIN, min(FONT_DELTA_MAX, cur + d))
        if new == cur and d != 0:
            return
        self.store.set("font_delta", new)
        init_fonts(self, new)
        apply_styles(self)
        self.img_cache.clear()
        self.after_idle(self._after_zoom)
        self.set_status(f"Taille du texte : {'+' if new > 0 else ''}{new}", "DIM")

    def _after_zoom(self):
        keep = list(self.selected)
        self._detail_mode_reset()
        self.refresh_items(keep=keep)

    def _detail_mode_reset(self):
        self._commit_pending()
        self._shown_ver = None
        self.editor_item_reload = True

    def change_theme(self):
        k = self.v_theme.get()
        if k not in THEMES:
            return
        self._commit_pending()
        self.store.set("theme", k)
        C.clear()
        C.update(THEMES[k])
        self.rebuild()

    def rebuild(self):
        keep = list(self.selected)
        view = self.cur_view
        q = self.v_search.get()
        for w in list(self.winfo_children()):
            if isinstance(w, tk.Toplevel):
                try:
                    w.destroy()
                except Exception:
                    pass
                continue
            w.destroy()
        self._detail_mode = ""
        self.editor_item = None
        self._build()
        self.cur_view = view if self._view_valid(view) or view == "search" else "v:all"
        self.refresh_tree()
        if view == "search" and q:
            self._search_lock = True
            self.v_search.set(q)
            self._search_lock = False
            self._update_placeholder()
            self.cur_view = self.view_before_search
            self.do_search(keep=keep)
        else:
            self._show_view_widget()
            self.refresh_items(keep=keep)

    # ================================================================ boite de reception (--ajouter)
    def _poll_inbox(self):
        try:
            d = Paths.inbox()
            files = sorted(glob.glob(os.path.join(d, "*.json"))) if os.path.isdir(d) else []
            all_ids: List[int] = []
            for fp in files:
                try:
                    with open(fp, "r", encoding="utf-8") as f:
                        payload = json.load(f)
                    os.remove(fp)
                except (OSError, ValueError) as ex:
                    logger.warning("inbox %s : %s", fp, ex)
                    try:
                        os.replace(fp, fp + ".erreur")
                    except OSError:
                        pass
                    continue
                if payload.get("action") == "montrer":
                    self._bring_front()
                    continue
                if payload.get("action") == "ouvrir":
                    self.store._touch()
                    self.refresh_all()
                    try:
                        self.goto_item(int(payload.get("id")))
                    except (TypeError, ValueError):
                        pass
                    self._bring_front()
                    continue
                if payload.get("action") == "lot":
                    with open(payload["fichier"], "r", encoding="utf-8") as f:
                        rep = import_lot(self.store, json.load(f))
                    all_ids += rep["ajoutees"]
                    continue
                ids = process_payload(self.store, payload)
                all_ids += ids
                logger.info("inbox : %d fiche(s) ajoutée(s)", len(ids))
            if all_ids:
                self._after_add(all_ids, None, msg=f"📥 {len(all_ids)} fiche(s) reçue(s) (envoi externe).")
                self._bring_front()
            self._gx_external_changes()
        except Exception:
            logger.error("inbox : %s", traceback.format_exc())
        self.after(1500, self._poll_inbox)

    def _bring_front(self):
        try:
            if self.state() == "iconic":
                self.state("zoomed")
            self.lift()
            self.attributes("-topmost", True)
            self.after(300, lambda: self.attributes("-topmost", False))
            self.focus_force()
        except tk.TclError:
            pass

    # ================================================================ fermeture
    def on_close(self):
        try:
            self._commit_pending()
        except Exception:
            logger.error("fermeture (enregistrement) : %s", traceback.format_exc())
        try:
            self.player.stop()
            if not self.readonly_test:
                try:
                    lw = self.pw.sash_coord(0)[0]
                    rw = self.pw.winfo_width() - self.pw.sash_coord(1)[0]
                    if not getattr(self.args, "geometry", ""):
                        self.store.set("left_w", lw)
                        self.store.set("right_w", rw)
                        self.store.set("panes_v", PANES_V)
                except Exception:
                    pass
                self.store.backup()
            self.store.close()
        except Exception:
            logger.error("fermeture : %s", traceback.format_exc())
        logger.info("Grimoire fermé")
        self.destroy()


# ================================================================ aide
HELP_TEXT = """# 📖 Grimoire : ton carnet de recherche

Le Grimoire garde TOUT ce que tu trouves, classé par sujets : notes, liens, vidéos, citations, pages web, images, documents, sons, mémos vocaux et fichiers. Tout est enregistré automatiquement, rien à sauvegarder à la main.

## Les trois colonnes
  Gauche : les sujets (et sous-sujets) + les vues spéciales : Tout, Favoris, Épinglés, Récents, Étiquettes, Corbeille.
  Centre : les fiches du sujet choisi, en Liste ☰, en Cartes ▦ (vignettes) ou en Chronologie 🕘 (par mois).
  Droite : la fiche choisie : Aperçu (miniature, lien, lecteur, texte extrait), Notes (texte riche), Fiche (source, dates, références).

## Ajouter quelque chose
  ＋ Ajouter : note, fiche à partir d'un modèle, lien, citation, image, document, son, vidéo, fichier, mémo vocal, page web.
  Ctrl+V (hors zone de texte) : colle intelligemment un lien (titre et miniature récupérés), du texte (note),
     une image copiée (capture d'écran) ou des fichiers copiés dans l'Explorateur.
  Glisser-déposer : des fichiers, des liens ou du texte depuis l'Explorateur ou le navigateur, sur la liste ou sur un sujet.
  Ce qui est ajouté va dans le sujet ouvert (sinon dans « À classer »).

## Les sujets
  Clic droit sur un sujet : sous-sujet, renommer (F2), icône, couleur, épingler, monter/descendre, ranger dans, fusionner,
     exporter, importer un dossier, supprimer (corbeille).
  Glisse un sujet sur un autre pour le ranger dedans ; Maj en lâchant = le placer avant ; dans le vide = niveau principal.
  Glisse des fiches sur un sujet pour les déplacer (Ctrl en lâchant = copier), sur ★ Favoris, 📌 Épinglés ou 🗑 Corbeille.
  Tous les sujets de départ sont renommables et supprimables.

## Les notes
  Barre d'outils : G gras, I italique, S̲ souligné, B̶ barré, T1/T2/T3 titres, ¶ normal, • puces, 1. numéros, ☐ cases à cocher
     (clic pour cocher), ❝ bloc citation, </> code, 🖍 surligner, 🔗 lien, [[ ]] référence, 📅 date du jour, 🧹 effacer le style.
  Les liens tapés deviennent cliquables tout seuls. [[Titre d'une fiche]] ou [[Nom d'un sujet]] crée un lien interne cliquable.
  L'onglet Fiche montre les références sortantes et les fiches qui citent celle-ci (rétroliens).
  Modèles : Source, Protocole, Plante médicinale, Recette, Livre/vidéo/article, Journal de recherche, Idée/projet,
     Expérience, Fait/événement, Personne. Tu peux enregistrer tes propres modèles (clic droit → Outils).

## Rechercher
  Ctrl+F : recherche instantanée dans tout : titres, notes, étiquettes, sources, liens, texte des PDF et documents,
     texte des pages capturées, texte lu dans les images (OCR) et mémos transcrits. Accents et majuscules ignorés.
  Plusieurs mots = fiches qui contiennent tous les mots ; « plant » trouve aussi « plantes ».
  Filtres : type, étiquette, période, « Partout » ou « Dans ce sujet ». Les mots trouvés sont surlignés.
  Ctrl+G : aller directement à un sujet ou une fiche en tapant quelques lettres.

## Outils de chercheur
  Citation ❝ : texte + auteur + source + page + lien + date ; « Copier avec la source » la met en forme.
  Capturer une page 🌐 : copie hors ligne complète (HTML + PDF + image pleine page) : la page reste même si le site disparaît.
  OCR 🔤 : lit le texte des images (moteur de Windows) pour le rendre cherchable (automatique au choix, menu Outils).
  Mémo vocal 🎙 : enregistre au micro ; transcription locale avec faster-whisper si installé (menu Outils).
  Date de l'info (onglet Fiche) : la date de l'événement ou de la publication, utilisée par la Chronologie.
  Mode lecture 📖 (F11) : grand texte confortable, fiche après fiche (◀ ▶).
  Statistiques 📊 : nombre de fiches par type, par sujet, par mois, étiquettes.
  Exporter : un sujet en page HTML autonome (images intégrées, filtre) ou en ZIP avec tous les fichiers.
  Envoyer à l'Archiveur 📦 : pour les vidéos, copie le lien et ouvre l'Archiveur 5 pour la télécharger.

## Raccourcis clavier
  Ctrl+N : nouvelle note            Ctrl+Maj+N : nouveau sujet          Ctrl+L : lien web
  Ctrl+Maj+Q : citation             Ctrl+R : mémo vocal                 Ctrl+O : fichier(s)
  Ctrl+Maj+I : image(s)             Ctrl+V : coller intelligent         Ctrl+Maj+V : coller comme note
  Ctrl+F : rechercher               Ctrl+G : aller à…                   Échap : quitter la recherche
  Ctrl+1 / 2 / 3 : liste / cartes / chronologie                         F11 : mode lecture
  Ctrl+D : favori ★                 Ctrl+P : épingler 📌                Ctrl+T : étiquettes
  Ctrl+M : déplacer vers…           Alt+Haut / Alt+Bas : monter / descendre (fiche ou sujet)
  F2 : renommer                     Suppr : corbeille                   Ctrl+Z : annuler suppression / déplacement
  Ctrl+A : tout sélectionner        Ctrl+clic / Maj+clic : sélection multiple
  Ctrl+Maj+E : exporter le sujet    Ctrl+S : copie de sauvegarde datée  F5 : rafraîchir
  Ctrl++ / Ctrl+- / Ctrl+0 : taille du texte (aussi Ctrl+molette)       F1 : cette aide
  Dans une note : Ctrl+B gras, Ctrl+I italique, Ctrl+U souligné, Ctrl+1/2/3 titres, Ctrl+0 normal, Ctrl+K lien,
     Ctrl+Maj+X barré, Ctrl+Maj+8 puces, Entrée continue la liste, Échap revient à la liste.
  Dans la liste : tape une lettre pour lancer la recherche, Entrée pour ouvrir.

## Données et sécurité
  Tout est dans C:\\web\\FTP_HOME\\GRIMOIRE\\ : grimoire.db (la base), medias\\ (les fichiers copiés, un dossier par sujet),
     _sauvegardes\\ (copies automatiques de la base : au démarrage, toutes les 6 h et à la fermeture, 30 gardées),
     exports\\ et grimoire.log (journal).
  Les fichiers ajoutés sont COPIÉS dans le Grimoire : l'original peut être déplacé ou effacé sans rien perdre.
  Corbeille : rien n'est effacé tant que tu ne vides pas la corbeille. Fichier → Restaurer une sauvegarde au besoin.

## Ligne de commande (pour les autres programmes Padawan)
  grimoire1.py --ajouter "https://..." --sujet "Santé/Protocoles" --titre "..." --note "..." --etiquettes "a, b"
  grimoire1.py --ajouter "C:\\chemin\\fichier.pdf"      grimoire1.py --ajouter "Une idée" --type citation --auteur "X"
  Si le Grimoire est ouvert, l'ajout arrive tout de suite dedans ; sinon il est enregistré directement.
  --check : vérification complète    --smoke : test automatique    --montrer : ramener la fenêtre
  --importer-lot fichier.json : import de fiches riches en lot    --retirer-lot NOM : retire un lot (corbeille)
"""


# ================================================================ verification
def check_report(store: Store) -> str:
    L = ["# 🔎 Vérification du Grimoire", ""]
    L.append(f"  Dossier : {Paths.data}")
    L.append(f"  Intégrité SQLite : {store.integrity()}")
    st = store.stats()
    L.append(f"  Fiches : {st['items']}  ·  sujets : {st['subjects']}  ·  corbeille : {st['trash']}")
    if store.fts_ok:
        nf = store.q("SELECT COUNT(*) n FROM fts")[0]["n"]
        L.append(f"  Index de recherche : {nf} entrée(s) pour {st['items']} fiche(s)"
                 + ("" if nf == st["items"] else "  ⚠ écart (menu Outils → Reconstruire l'index)"))
    else:
        L.append("  Index de recherche : FTS5 indisponible (recherche simple)")
    missing = []
    for r in store.q("SELECT id,title,file,thumb FROM items WHERE deleted IS NULL AND (file<>'' OR thumb<>'')"):
        for k in ("file", "thumb"):
            if r[k] and not os.path.isfile(Paths.abs(r[k])):
                missing.append(f"    #{r['id']} {r['title'][:50]} : {k} {r[k]}")
    L.append(f"  Fichiers manquants : {len(missing)}")
    L += missing[:30]
    orphans = store.q("SELECT COUNT(*) n FROM items WHERE deleted IS NULL AND subject_id NOT IN "
                      "(SELECT id FROM subjects WHERE deleted IS NULL)")[0]["n"]
    L.append(f"  Fiches sans sujet : {orphans}" + ("  ⚠ (Ctrl+Z / restaurer, ou elles apparaissent dans Tout)" if orphans else ""))
    bk = sorted(glob.glob(os.path.join(Paths.backups(), "grimoire_*.db")))
    L.append(f"  Sauvegardes : {len(bk)}" + (f"  (dernière : {os.path.basename(bk[-1])})" if bk else ""))
    L += ["", "## Modules et outils"]
    for mod, why in (("PIL", "images, vignettes, Ctrl+V d'images"), ("requests", "liens web"), ("pypdf", "texte des PDF"),
                     ("tkinterdnd2", "glisser-déposer depuis l'Explorateur"), ("sounddevice", "micro (mémos vocaux)"),
                     ("soundfile", "enregistrement FLAC"), ("bs4", "texte des pages web (facultatif)"),
                     ("faster_whisper", "transcription des mémos (facultatif)")):
        L.append(f"  {mod:<15} {'OK' if module_ok(mod) else 'absent'}   ({why})")
    try:
        devs, _d, err = Recorder.devices()
        L.append(f"  Micro            {len(devs)} entrée(s) audio" + (f"  ({err})" if err and not devs else ""))
    except Exception as ex:
        L.append(f"  Micro            erreur : {ex}")
    L.append(f"  ffplay           {find_ff_tool('ffplay') or 'introuvable (lecture audio par Windows)'}")
    L.append(f"  ffmpeg           {find_ffmpeg() or 'introuvable (pas de vignettes de vidéos locales)'}")
    L.append(f"  Navigateur       {find_browser() or 'introuvable (pas de PDF/image des pages capturées)'}")
    try:
        o = ocr_available()
        L.append(f"  OCR Windows      {o or 'indisponible'}")
    except Exception as ex:
        L.append(f"  OCR Windows      erreur : {ex}")
    L.append(f"  Python           {sys.version.split()[0]}  ({sys.executable})")
    return "\n".join(L)


# ================================================================ instance unique, captures, tests
def _focus_existing() -> bool:
    if not IS_WIN:
        return False
    try:
        u32 = ctypes.windll.user32
        hwnd = u32.FindWindowW("TkTopLevel", APP_TITLE)
        if hwnd:
            cmd = 9 if u32.IsIconic(hwnd) else (3 if u32.IsZoomed(hwnd) else 5)
            u32.ShowWindow(hwnd, cmd)
            u32.ShowWindow(hwnd, cmd)
            u32.mouse_event(0x0001, 0, 0, 0, 0)
            u32.BringWindowToTop(hwnd)
            u32.SetForegroundWindow(hwnd)
            return True
    except Exception:
        pass
    return False


def _mutex_exists() -> bool:
    if not IS_WIN:
        return False
    k32 = ctypes.windll.kernel32
    k32.OpenMutexW.restype = wintypes.HANDLE
    h = k32.OpenMutexW(0x00100000, False, _MUTEX_NAME)   # SYNCHRONIZE
    if h:
        k32.CloseHandle(h)
        return True
    return False


def _single_instance():
    if not IS_WIN:
        return True, None
    k32 = ctypes.windll.kernel32
    k32.CreateMutexW.restype = wintypes.HANDLE
    h = k32.CreateMutexW(None, False, _MUTEX_NAME)
    if ctypes.GetLastError() == 183:
        return False, h
    return True, h


def take_shot(app: "GrimoireApp", path: str) -> bool:
    try:
        from PIL import ImageGrab  # type: ignore
    except ImportError:
        logger.error("capture : Pillow absent")
        return False
    wins = [app] + [w for w in app.winfo_children() if isinstance(w, tk.Toplevel) and w.winfo_viewable()]
    for w in wins:
        try:
            w.attributes("-topmost", True)
            w.lift()
        except tk.TclError:
            pass
    app.update()
    time.sleep(0.4)
    app.update()
    try:
        full = ImageGrab.grab()
    except Exception as ex:
        logger.error("capture : %s", ex)
        return False
    for w in wins:
        try:
            w.attributes("-topmost", False)
        except tk.TclError:
            pass
    f = full.width / max(1, app.winfo_screenwidth())
    x, y = app.winfo_rootx(), app.winfo_rooty()
    w, h = app.winfo_width(), app.winfo_height()
    img = full.crop((int(x * f), int(y * f), int((x + w) * f), int((y + h) * f)))
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    img.save(path)
    logger.info("capture %s (%dx%d, facteur %.2f)", path, img.width, img.height, f)
    return True


def _first_item(app: "GrimoireApp", name: str, typ: str = "") -> Optional[int]:
    for r in app.store.items_where("1=1"):
        if (not name or norm(r["title"]) == norm(name)) and (not typ or r["type"] == typ):
            return r["id"]
    return None


def run_shot(app: "GrimoireApp", path: str, view: str) -> None:
    st = app.store

    def subj(name):
        return st.find_subject(name)

    def step1():
        try:
            pm = subj("Plantes médicinales")
            if view in ("cartes", "lien"):
                for r in st.items_where("type IN ('link','video')"):
                    if st.meta(r).get("pending", True) and not st.meta(r).get("fetched"):
                        enrich_any(st, r["id"])
            if view in ("main", "cartes", "chrono", "lien", "image", "citation"):
                app.open_view(f"s:{pm}" if pm else "v:all")
                app.set_view_mode({"cartes": "cards", "chrono": "chrono"}.get(view, "list"))
                target = {"main": _first_item(app, "Échinacée", "note"), "lien": _first_item(app, "", "link"),
                          "citation": _first_item(app, "", "quote"), "cartes": _first_item(app, "", "video"),
                          "chrono": _first_item(app, "Tisane du soir"), "image": _first_item(app, "", "image")}.get(view)
                if target:
                    app.select_ids([target], see=True)
            elif view == "accueil":
                app.set_view_mode("list")
                b = subj("Bienvenue")
                app.open_view(f"s:{b}")
                it = _first_item(app, "Comment utiliser le Grimoire")
                if it:
                    app.select_ids([it])
            elif view == "sujet":
                app.set_view_mode("list")
                app.open_view(f"s:{subj('Santé')}")
            elif view == "recherche":
                app.set_view_mode("list")
                app.v_search.set("echinacee")
                app.do_search()
                if app.results:
                    app.select_ids([app.results[0]["id"]])
            elif view == "lecture":
                app.open_view(f"s:{pm}")
                it = _first_item(app, "Échinacée", "note")
                if it:
                    app.select_ids([it])
                app.open_reader()
            elif view == "memo":
                app.open_view(f"s:{pm}")
                RecorderDialog(app, pm)
            elif view == "aide":
                app.show_help()
            elif view == "stats":
                app.show_stats()
            elif view == "corbeille":
                app.open_view("v:trash")
            elif view == "palette":
                Palette(app, "goto")
            elif view == "sujetdlg":
                SubjectDialog(app, app, "Nouveau sujet", None, subj("Santé"))
            elif view == "citationdlg":
                QuoteDialog(app, "")
            elif view == "liendlg":
                LinkDialog(app, app, "https://www.youtube.com/watch?v=aqz-KE-bpKQ")
            elif view == "verif":
                app.check_dialog()
            elif view == "carte":
                app.open_mindmap()
            elif view == "cartes2":
                app.open_view("v:all")
                app.set_view_mode("cards")
            elif view == "liens":
                app.open_view("v:all")
                app.set_view_mode("cards")
                tgt = os.environ.get("GX_SHOT_ITEM")
                if tgt:
                    app.select_ids([int(tgt)], see=True)
        except Exception:
            logger.error("capture %s : %s", view, traceback.format_exc())
        app.after(1800 if view != "verif" else 4000, step2)

    def step2():
        take_shot(app, path)
        app.after(150, app.destroy)
    app.after(1600, step1)


def run_smoke(app: "GrimoireApp") -> int:
    errors: List[str] = []
    st = app.store
    try:
        app.update()
        for key, _i, _l in SPECIAL_VIEWS:
            app.open_view(key)
            app.update()
        for sid in app.subject_order():
            app.open_view(f"s:{sid}")
            app.update()
            if app.visible:
                app.select_ids([app.visible[0]["id"]])
                app.update()
        for mode in ("cards", "chrono", "list"):
            app.set_view_mode(mode)
            app.update()
        pm = st.find_subject("Plantes médicinales")
        app.open_view(f"s:{pm}")
        app.update()
        # note
        app.new_note(template="Recette")
        app.update()
        iid = app.cur_item
        app.editor.t.insert("end", "\nzorglub magique [[Échinacée]] https://exemple.org")
        app.editor.flush()
        app.update()
        it = st.item(iid)
        if not it or "zorglub" not in (it.get("body_text") or ""):
            errors.append("note : texte non enregistré")
        app.v_tags.set("test, smoke")
        app._tags_commit()
        if "smoke" not in (st.item(iid) or {}).get("tags", ""):
            errors.append("étiquettes non enregistrées")
        # recherche
        app.v_search.set("zorglub")
        app.do_search()
        app.update()
        if not any(r["id"] == iid for r in app.results):
            errors.append("recherche : note zorglub introuvable")
        app.v_search.set("echinacee")
        app.do_search()
        app.update()
        if not app.results:
            errors.append("recherche sans accent : échinacée introuvable")
        app.clear_search()
        app.update()
        # citation, lien hors ligne
        q = add_quote(st, pm, "Le savoir est une arme.", "Anonyme", "Test")
        app._after_add([q], pm, enrich=False)
        app.update()
        app.copy_citation(q)
        # corbeille + annuler
        n0 = st.stats()["items"]
        app.select_ids([iid, q])
        app.delete_selected()
        app.update()
        if st.stats()["items"] != n0 - 2:
            errors.append("corbeille : suppression incorrecte")
        app.do_undo()
        app.update()
        if st.stats()["items"] != n0:
            errors.append("annuler : restauration incorrecte")
        # deplacer + annuler
        other = st.find_subject("Recettes")
        app.select_ids([iid])
        app.move_selected(False, other)
        if (st.item(iid) or {}).get("subject_id") != other:
            errors.append("déplacement incorrect")
        app.do_undo()
        if (st.item(iid) or {}).get("subject_id") != pm:
            errors.append("annuler le déplacement incorrect")
        # sujets
        sid = st.add_subject("Sujet smoke", pm, "🧪", "#55FF55")
        app.refresh_tree()
        app.open_view(f"s:{sid}")
        app.update()
        b = st.trash_subject(sid)
        st.restore_batch(b)
        st.trash_subject(sid)
        app.refresh_all()
        app.open_view("v:trash")
        app.update()
        # dialogues
        for maker in (lambda: TextDialog(app, "Aide", HELP_TEXT), lambda: SubjectDialog(app, app, "Test"),
                      lambda: LinkDialog(app, app, "https://exemple.org"), lambda: QuoteDialog(app, "x"),
                      lambda: EmojiPicker(app, "📖"), lambda: SubjectChooser(app, app, "Test", "Choisir"),
                      lambda: RecorderDialog(app, pm), lambda: Palette(app, "goto")):
            d = maker()
            app.update()
            d.destroy()
        app.show_stats()
        app.update()
        ReaderWindow(app, [iid, q], 0).destroy()
        # export
        out = os.path.join(Paths.exports(), "smoke_export.html")
        os.makedirs(Paths.exports(), exist_ok=True)
        n = export_subject(st, pm, out)
        if n < 1 or not os.path.isfile(out):
            errors.append("export HTML vide")
        app.zoom(1)
        app.update()
        app.zoom(0)
        app.update()
        app.v_theme.set("clair")
        app.change_theme()
        app.update()
        app.v_theme.set("norton")
        app.change_theme()
        app.update()
        app.open_view(f"s:{pm}")
        app.set_view_mode("cards")
        app.update()
        app.set_view_mode("list")
        if st.integrity() != "ok":
            errors.append("intégrité : " + st.integrity())
    except Exception:
        errors.append(traceback.format_exc())
    s = st.stats()
    print(f"SMOKE {'OK' if not errors else 'ERREURS'} : {s['items']} fiches, {s['subjects']} sujets, données {Paths.data}")
    for er in errors:
        print("ERREUR:", er)
    logger.info("smoke : %s", "OK" if not errors else f"{len(errors)} erreur(s)")
    return 0 if not errors else 1


# ================================================================ ligne de commande
def cli_add(args) -> int:
    payload = {"ajouter": args.ajouter, "sujet": args.sujet, "titre": args.titre, "note": args.note,
               "etiquettes": args.etiquettes, "source": args.source, "type": args.type, "auteur": args.auteur,
               "url": args.url}
    payload = {k: v for k, v in payload.items() if v}
    val = payload["ajouter"].strip().strip('"')
    if len(val) < 600 and os.path.exists(val):
        payload["ajouter"] = os.path.abspath(val)
    if _mutex_exists():
        os.makedirs(Paths.inbox(), exist_ok=True)
        fp = os.path.join(Paths.inbox(), f"{dt.datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{uuid.uuid4().hex[:6]}.json")
        tmp = fp + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        os.replace(tmp, fp)
        print(f"Envoyé au Grimoire ouvert : {fp}")
        logger.info("--ajouter → inbox %s", fp)
        return 0
    st = Store().open()
    try:
        seed_content(st)
        ids = process_payload(st, payload)
        for iid in ids:
            enrich_any(st, iid)
        for iid in ids:
            it = st.item(iid)
            print(f"Ajouté #{iid} [{it['type']}] « {it['title']} » dans {st.subject_path(it['subject_id'])}")
        logger.info("--ajouter direct : %d fiche(s)", len(ids))
        return 0 if ids else 2
    finally:
        st.close()


def cli_lot(args) -> int:
    fp = os.path.abspath(args.importer_lot)
    with open(fp, "r", encoding="utf-8") as f:
        data = json.load(f)
    if _mutex_exists():
        os.makedirs(Paths.inbox(), exist_ok=True)
        dst = os.path.join(Paths.inbox(), f"lot_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}.json")
        with open(dst + ".tmp", "w", encoding="utf-8") as f:
            json.dump({"action": "lot", "fichier": fp}, f, ensure_ascii=False)
        os.replace(dst + ".tmp", dst)
        print(f"Grimoire ouvert : lot envoyé par la boîte de réception ({dst})")
        return 0
    st = Store().open()
    try:
        seed_content(st)
        st.backup(force=True, tag="avant_lot")
        rep = import_lot(st, data, progress=print)
        print(f"Lot « {rep['lot']} » : {len(rep['ajoutees'])} fiche(s) ajoutée(s), {len(rep['sautees'])} déjà présente(s), "
              f"{rep['sujets_crees']} sujet(s) créé(s), {len(rep['erreurs'])} erreur(s)")
        for e in rep["erreurs"]:
            print("ERREUR:", e)
        return 0 if not rep["erreurs"] else 1
    finally:
        st.close()


def cli_remove_lot(args) -> int:
    if _mutex_exists():
        print("Ferme d'abord le Grimoire (ou utilise la corbeille dans l'interface).")
        return 2
    st = Store().open()
    try:
        st.backup(force=True, tag="avant_retrait_lot")
        n = remove_lot(st, args.retirer_lot)
        print(f"{n} fiche(s) du lot « {args.retirer_lot} » envoyée(s) à la corbeille (restaurables).")
        return 0
    finally:
        st.close()


def cli_check(_args) -> int:
    st = Store().open()
    try:
        print(check_report(st))
        return 0 if st.integrity() == "ok" else 1
    finally:
        st.close()


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Grimoire - carnet de recherche par sujets (Projet Padawan)")
    ap.add_argument("--smoke", action="store_true", help="test automatique de l'interface puis sortie")
    ap.add_argument("--check", action="store_true", help="vérification de la base, des fichiers et des modules")
    ap.add_argument("--shot", default="", help="capture PNG de la fenêtre puis sortie")
    ap.add_argument("--shot-view", default="main", help="main|cartes|chrono|recherche|lecture|memo|sujet|aide|stats|accueil|"
                                                         "lien|citation|corbeille|palette|sujetdlg|citationdlg|liendlg|verif")
    ap.add_argument("--geometry", default="", help="ex. 1280x720+0+0 (sinon plein écran)")
    ap.add_argument("--data", default="", help="autre dossier de données (tests)")
    ap.add_argument("--demo", action="store_true", help="ajoute des fiches d'exemple (dossier de test seulement)")
    ap.add_argument("--ajouter", default="", help="texte, lien ou fichier à ajouter")
    ap.add_argument("--sujet", default="", help="sujet de destination (« Santé/Protocoles »), sinon « À classer »")
    ap.add_argument("--titre", default="")
    ap.add_argument("--note", default="")
    ap.add_argument("--etiquettes", default="")
    ap.add_argument("--source", default="")
    ap.add_argument("--auteur", default="")
    ap.add_argument("--url", default="", help="lien de la source (citation)")
    ap.add_argument("--type", default="", help="citation : ajoute le texte comme citation")
    ap.add_argument("--montrer", action="store_true", help="ramène la fenêtre du Grimoire")
    ap.add_argument("--make-icons", action="store_true", help="génère grimoire1.ico/.png puis sortie")
    ap.add_argument("--importer-lot", default="", help="importe un lot de fiches (JSON : sujets, fiches riches, étiquettes)")
    ap.add_argument("--retirer-lot", default="", help="envoie à la corbeille les fiches d'un lot importé (par son nom)")
    args = ap.parse_args(argv)
    if args.data:
        Paths.set(args.data)
    setup_logging()
    if IS_WIN:
        for s in (sys.stdout, sys.stderr):
            try:
                s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
            except Exception:
                pass
    if args.make_icons:
        print(generate_app_icons(BASE, force=True))
        return 0
    if args.check:
        return cli_check(args)
    if args.importer_lot:
        try:
            return cli_lot(args)
        except Exception:
            logger.error("--importer-lot : %s", traceback.format_exc())
            print(traceback.format_exc())
            return 1
    if args.retirer_lot:
        return cli_remove_lot(args)
    if args.ajouter:
        try:
            return cli_add(args)
        except Exception:
            logger.error("--ajouter : %s", traceback.format_exc())
            print(traceback.format_exc())
            return 1
    if tk is None:
        print("tkinter est requis")
        return 1
    special = args.smoke or bool(args.shot)
    mutex = None
    if not special:
        ok, mutex = _single_instance()
        if not ok:
            if not _focus_existing():
                try:
                    os.makedirs(Paths.inbox(), exist_ok=True)
                    with open(os.path.join(Paths.inbox(), f"montrer_{uuid.uuid4().hex[:6]}.json"), "w", encoding="utf-8") as f:
                        json.dump({"action": "montrer"}, f)
                except OSError:
                    pass
            return 0
    elif args.montrer:
        return 0
    try:
        generate_app_icons(BASE)
    except Exception:
        logger.info("icônes : %s", traceback.format_exc())
    try:
        app = GrimoireApp(args)
    except Exception:
        logger.error("démarrage : %s", traceback.format_exc())
        if not special and tk is not None:
            try:
                r = tk.Tk()
                r.withdraw()
                messagebox.showerror(APP_NAME, "Le Grimoire n'a pas pu démarrer :\n\n" + traceback.format_exc()[-1500:]
                                     + f"\n\nJournal : {Paths.log()}")
                r.destroy()
            except Exception:
                pass
        raise

    def report(*a):
        logger.error("erreur Tk : %s", "".join(traceback.format_exception(*a)))
        try:
            app.set_status("⚠ Une erreur s'est produite (détails dans grimoire.log) : " + str(a[1])[:120], "ERR")
        except Exception:
            pass
    app.report_callback_exception = report
    if args.smoke:
        app.update()
        code = run_smoke(app)
        try:
            app.store.close()
        except Exception:
            pass
        app.destroy()
        return code
    if args.shot:
        run_shot(app, args.shot, args.shot_view)
    app.mainloop()
    _ = mutex
    return 0


if __name__ == "__main__":
    sys.exit(main())
