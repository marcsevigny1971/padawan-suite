# -*- coding: utf-8 -*-
# Partie de archiveur5.py (découpage v1.2.2, comportement inchangé).
# Chargée par archiveur5.py dans un espace de noms commun : ne pas lancer seule.
from __future__ import annotations

from __future__ import annotations

import argparse
import hashlib
import html
import json
import logging
import logging.handlers
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, quote, urlparse
from urllib.request import Request, urlopen

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    from tkinter import font as tkfont
except Exception:  # CLI sans Tk
    tk = None  # type: ignore

APP_NAME = "Archiveur"
APP_FILE_VER = 5
BASE = os.path.dirname(os.path.abspath(__file__))
CFG_FILE = os.path.join(BASE, "archiveur_config.json")
LOG_FILE = os.path.join(BASE, "archiveur.log")
_MARC_ROOT = r"C:\web\FTP_HOME\ARCHIVEUR"


def _portable_root() -> str:
    """Archives : ARCHIVEUR_DATA / PADAWAN_DATA, sinon C:\\web\\FTP_HOME\\ARCHIVEUR (PC de Marc),
    sinon %USERPROFILE%\\Documents\\Padawan\\Archiveur (autre PC). Modifiable dans les reglages."""
    env = os.environ.get("ARCHIVEUR_DATA", "").strip()
    if env:
        return env
    root = os.environ.get("PADAWAN_DATA", "").strip()
    if root:
        return os.path.join(root, "Archiveur")
    if os.path.isdir(os.path.dirname(_MARC_ROOT)):
        return _MARC_ROOT
    return os.path.join(os.path.expanduser("~"), "Documents", "Padawan", "Archiveur")


DEFAULT_ROOT = _portable_root()
INDEX_JSON = "archive_index.json"
INDEX_HTML = "index.html"
STORYBOARD_DIR = "storyboard"
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Norton Commander-ish theme
NC_BG = "#0000AA"
NC_PANEL = "#000088"
NC_CARD = "#000066"
NC_FG = "#55FFFF"
NC_HI = "#FFFF55"
NC_BTN = "#0000AA"
NC_BTN_FG = "#FFFFFF"
NC_ENTRY_BG = "#000055"
NC_ENTRY_FG = "#FFFFFF"
NC_SEL = "#AAAA00"
NC_DIM = "#88AACC"
NC_OK = "#55FF55"
NC_ERR = "#FF5555"
# ---------------------------------------------------------------- thèmes (v5)
# Couleurs appliquées au démarrage (config « theme ») ; changer de thème relance l'app.
THEMES: Dict[str, Dict[str, str]] = {
    "norton": {
        "BG": "#0000AA", "PANEL": "#000088", "CARD": "#000066", "FG": "#55FFFF", "HI": "#FFFF55",
        "BTN": "#0000AA", "BTN_FG": "#FFFFFF", "ENTRY_BG": "#000055", "ENTRY_FG": "#FFFFFF",
        "SEL": "#AAAA00", "DIM": "#88AACC", "OK": "#55FF55", "ERR": "#FF5555", "TEXT": "#FFFFFF",
        "ON_HI": "#000000", "ON_SEL": "#000000", "LINE": "#3355AA", "IMG_BG": "#000033",
        "HI_ACT": "#FFFF88", "DISABLED": "#6677AA", "TIP_BG": "#FFFFCC", "TIP_FG": "#000000",
        "SASH": "#55FFFF", "WARN": "#FFAA33",
    },
    "sombre": {
        "BG": "#1E1E1E", "PANEL": "#252526", "CARD": "#2D2D30", "FG": "#D4D4D4", "HI": "#FFC83D",
        "BTN": "#3A3D41", "BTN_FG": "#FFFFFF", "ENTRY_BG": "#141414", "ENTRY_FG": "#F0F0F0",
        "SEL": "#C9A227", "DIM": "#8C8C8C", "OK": "#6CCB5F", "ERR": "#F1707B", "TEXT": "#F0F0F0",
        "ON_HI": "#000000", "ON_SEL": "#000000", "LINE": "#45454D", "IMG_BG": "#000000",
        "HI_ACT": "#FFD866", "DISABLED": "#6B6B6B", "TIP_BG": "#FFFFCC", "TIP_FG": "#000000",
        "SASH": "#5A5A5A", "WARN": "#FFAA33",
    },
    "clair": {
        "BG": "#F3F3F3", "PANEL": "#E4E7EB", "CARD": "#FFFFFF", "FG": "#1F3A5F", "HI": "#0B5CAD",
        "BTN": "#DADDE2", "BTN_FG": "#111111", "ENTRY_BG": "#FFFFFF", "ENTRY_FG": "#000000",
        "SEL": "#9CC3EE", "DIM": "#5F6B7A", "OK": "#1E7B34", "ERR": "#C62828", "TEXT": "#111111",
        "ON_HI": "#FFFFFF", "ON_SEL": "#000000", "LINE": "#B8C0CC", "IMG_BG": "#202428",
        "HI_ACT": "#3D8BDA", "DISABLED": "#A0A6AE", "TIP_BG": "#FFFFE0", "TIP_FG": "#000000",
        "SASH": "#9AA4B0", "WARN": "#B85C00",
    },
}
THEME_LABELS = {"norton": "Norton (bleu, défaut)", "sombre": "Sombre", "clair": "Clair"}


def _early_cfg() -> Dict[str, Any]:
    try:
        with open(CFG_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


_EARLY_CFG = _early_cfg()
THEME = os.environ.get("ARCHIVEUR_THEME") or str(_EARLY_CFG.get("theme") or "norton")
if THEME not in THEMES:
    THEME = "norton"
for _k, _v in THEMES[THEME].items():
    globals()["NC_" + _k] = _v
del _k, _v

# Polices nommées (Tk) : la taille se règle en direct (Ctrl+molette, Ctrl +/-/0).
FONT_SPECS: Dict[str, Tuple[str, int, str, bool]] = {
    "ArchUI": ("Consolas", 11, "normal", False),
    "ArchSM": ("Consolas", 9, "normal", False),
    "ArchTitle": ("Consolas", 14, "bold", False),
    "ArchBig": ("Consolas", 17, "bold", False),
    "ArchCardK": ("Consolas", 10, "bold", False),
    "ArchCardV": ("Consolas", 10, "normal", False),
    "ArchCardVU": ("Consolas", 10, "normal", True),
    "ArchText": ("Segoe UI", 11, "normal", False),
    "ArchPaste": ("Consolas", 12, "bold", False),
    "ArchMono": ("Consolas", 10, "normal", False),
}
FONT_UI = "ArchUI"
FONT_SM = "ArchSM"
FONT_TITLE = "ArchTitle"
FONT_BIG = "ArchBig"
FONT_CARD_K = "ArchCardK"
FONT_CARD_V = "ArchCardV"
FONT_CARD_VU = "ArchCardVU"
FONT_TEXT = "ArchText"
FONT_PASTE = "ArchPaste"
FONT_MONO = "ArchMono"
FONT_DELTA_MIN, FONT_DELTA_MAX = -3, 8


_FONT_OBJS: Dict[str, Any] = {}


def init_fonts(root, delta: int = 0) -> None:
    """Crée (ou met à jour) les polices nommées pour la fenêtre racine."""
    from tkinter import font as tkfont
    delta = max(FONT_DELTA_MIN, min(FONT_DELTA_MAX, int(delta or 0)))
    families = set()
    try:
        families = {f.lower() for f in tkfont.families(root)}
    except Exception:
        pass
    for name, (fam, size, weight, underline) in FONT_SPECS.items():
        if families and fam.lower() not in families:
            fam = "DejaVu Sans Mono" if fam == "Consolas" else "DejaVu Sans"
        kw = dict(family=fam, size=max(6, size + delta), weight=weight, underline=1 if underline else 0)
        obj = _FONT_OBJS.get(name)
        if obj is not None:
            try:
                obj.configure(**kw)
                continue
            except Exception:
                pass
        try:
            obj = tkfont.Font(root=root, name=name, exists=False, **kw)
        except Exception:  # existe déjà côté Tk
            obj = tkfont.Font(root=root, name=name, exists=True)
            obj.configure(**kw)
        _FONT_OBJS[name] = obj  # garder la référence : sinon Tk supprime la police nommée


def font_px(root, name: str = FONT_SM) -> int:
    """Hauteur de ligne (px) d'une police nommée."""
    try:
        from tkinter import font as tkfont
        return int(tkfont.nametofont(name, root=root).metrics("linespace"))
    except Exception:
        return 16

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

VIDEO_EXTS = (".mp4", ".webm", ".mkv", ".mov", ".m4v")
AUDIO_EXTS = (".mp3", ".m4a", ".ogg", ".opus", ".wav")
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")
MEDIA_EXTS = VIDEO_EXTS + AUDIO_EXTS + IMAGE_EXTS

QUALITY_LABELS = [
    ("best", "Meilleure"),
    ("720", "720p"),
    ("480", "480p"),
    ("audio", "Audio (mp3)"),
]
QUALITY_BY_LABEL = {lab: key for key, lab in QUALITY_LABELS}
LABEL_BY_QUALITY = {key: lab for key, lab in QUALITY_LABELS}

PLATFORM_LABELS = {
    "youtube": "📺 YouTube",
    "x": "✖ X (Twitter)",
    "facebook": "📘 Facebook",
    "instagram": "📷 Instagram",
    "tiktok": "🎵 TikTok",
    "vimeo": "🎬 Vimeo",
    "web": "🌐 Web",
}

SORT_CHOICES = [
    ("date_desc", "Date ↓ (récent)"),
    ("date_asc", "Date ↑ (ancien)"),
    ("name_asc", "Nom A→Z"),
    ("name_desc", "Nom Z→A"),
    ("size_desc", "Taille ↓"),
    ("size_asc", "Taille ↑"),
]
SORT_BY_LABEL = {lab: key for key, lab in SORT_CHOICES}
LABEL_BY_SORT = {key: lab for key, lab in SORT_CHOICES}


# ---------------------------------------------------------------- journal
logger = logging.getLogger("archiveur")


def setup_logging() -> None:
    if logger.handlers:
        return
    logger.setLevel(logging.INFO)
    try:
        h = logging.handlers.RotatingFileHandler(
            LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(h)
    except Exception:
        logger.addHandler(logging.NullHandler())
