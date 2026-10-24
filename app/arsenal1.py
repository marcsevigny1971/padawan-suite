# -*- coding: utf-8 -*-
"""
Arsenal 1 - lanceur / catalogue de favoris, raccourcis et commandes (Projet Padawan).

Un tiroir a outils plein ecran (theme Norton bleu/cyan/jaune, Consolas) :
- liens web, programmes, raccourcis .lnk, dossiers, scripts .bat/.cmd/.ps1/.py,
  commandes CMD et PowerShell, aide-memoire (copier seulement), shell:/ms-settings:/CLSID ;
- admin (UAC), console ouverte/cachee/resultat dans Arsenal, confirmation, questions au lancement ;
- categories, favoris, recents, plus utilises, recherche instantanee, palette Ctrl+Espace
  (raccourci global Ctrl+Alt+Espace optionnel), glisser-deposer (fichiers, liens, reorganiser),
  multi-selection, annuler/retablir, entrees masquees, import/export (JSON, Favoris.php,
  signets Chrome/Edge, HTML), sauvegardes automatiques avec rotation, journal arsenal.log.

Donnees : arsenal.json a cote de ce fichier (dans Projet Padawan, donc pris par backup.bat).
Sauvegardes : _sauvegardes_arsenal\\ (rotation 25). Icones extraites : _icones_arsenal\\.
Tests : --smoke, --shot fichier.png --geometry 1280x720 --shot-view main|editeur|securite|aide|palette|ip,
        --list (commandes calculees), --run-capture ID (entree non dangereuse, sortie console).
"""
from __future__ import annotations

import argparse
import base64
import copy
import ctypes
import datetime as dt
import html
import json
import logging
import logging.handlers
import os
import queue
import re
import shutil
import socket
import string
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import unicodedata
import urllib.request
import uuid
from html.parser import HTMLParser
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog
    from tkinter import font as tkfont
except ImportError:  # pragma: no cover
    tk = None  # type: ignore
    ttk = messagebox = filedialog = tkfont = None  # type: ignore

APP_NAME = "Arsenal"
APP_FILE_VER = 1
APP_TITLE = "Arsenal"          # titre de fenetre sans numero (FindWindow)
SEED_VERSION = 2               # contenu initial : les nouvelles entrees futures s'ajoutent sans ecraser
IS_WIN = sys.platform.startswith("win")

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE, "arsenal.json")
LOG_FILE = os.path.join(BASE, "arsenal.log")
BACKUP_DIR = os.path.join(BASE, "_sauvegardes_arsenal")
ICON_DIR = os.path.join(BASE, "_icones_arsenal")
BACKUP_KEEP = 25
BACKUP_MIN_INTERVAL = 1800.0
PADAWAN_DIR_DEFAULT = r"C:\web\FTP_HOME\SECTION PYTHON\Projet Padawan"
FAVORIS_BACKUP_DIR = r"C:\web\favoris_backups"
FAVORIS_URL = "https://marcsevigny.ca/Favoris.php"
_MUTEX_NAME = "Local\\ArsenalPadawanUnique"

CREATE_NO_WINDOW = 0x08000000
CONSOLE_COLORS = [True]       # consoles CMD/PowerShell aux couleurs Norton (reglage)

logger = logging.getLogger("arsenal")


def setup_logging() -> None:
    if logger.handlers:
        return
    logger.setLevel(logging.INFO)
    try:
        h = logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S"))
        logger.addHandler(h)
    except OSError:
        logger.addHandler(logging.NullHandler())


# ---------------------------------------------------------------- themes (repris de l'Archiveur 5)
THEMES: Dict[str, Dict[str, str]] = {
    "norton": {
        "BG": "#0000AA", "PANEL": "#000088", "CARD": "#000066", "FG": "#55FFFF", "HI": "#FFFF55",
        "BTN": "#0000AA", "BTN_FG": "#FFFFFF", "ENTRY_BG": "#000055", "ENTRY_FG": "#FFFFFF",
        "SEL": "#AAAA00", "DIM": "#88AACC", "OK": "#55FF55", "ERR": "#FF5555", "TEXT": "#FFFFFF",
        "ON_HI": "#000000", "ON_SEL": "#000000", "LINE": "#3355AA", "IMG_BG": "#000033",
        "HI_ACT": "#FFFF88", "DISABLED": "#6677AA", "TIP_BG": "#FFFFCC", "TIP_FG": "#000000",
        "SASH": "#55FFFF", "WARN": "#FFAA33", "HOVER": "#0A0A99", "CARD_FAV": "#1A1A70",
    },
    "sombre": {
        "BG": "#1E1E1E", "PANEL": "#252526", "CARD": "#2D2D30", "FG": "#D4D4D4", "HI": "#FFC83D",
        "BTN": "#3A3D41", "BTN_FG": "#FFFFFF", "ENTRY_BG": "#141414", "ENTRY_FG": "#F0F0F0",
        "SEL": "#C9A227", "DIM": "#8C8C8C", "OK": "#6CCB5F", "ERR": "#F1707B", "TEXT": "#F0F0F0",
        "ON_HI": "#000000", "ON_SEL": "#000000", "LINE": "#45454D", "IMG_BG": "#000000",
        "HI_ACT": "#FFD866", "DISABLED": "#6B6B6B", "TIP_BG": "#FFFFCC", "TIP_FG": "#000000",
        "SASH": "#5A5A5A", "WARN": "#FFAA33", "HOVER": "#38383C", "CARD_FAV": "#33302A",
    },
    "clair": {
        "BG": "#F3F3F3", "PANEL": "#E4E7EB", "CARD": "#FFFFFF", "FG": "#1F3A5F", "HI": "#0B5CAD",
        "BTN": "#DADDE2", "BTN_FG": "#111111", "ENTRY_BG": "#FFFFFF", "ENTRY_FG": "#000000",
        "SEL": "#9CC3EE", "DIM": "#5F6B7A", "OK": "#1E7B34", "ERR": "#C62828", "TEXT": "#111111",
        "ON_HI": "#FFFFFF", "ON_SEL": "#000000", "LINE": "#B8C0CC", "IMG_BG": "#202428",
        "HI_ACT": "#3D8BDA", "DISABLED": "#A0A6AE", "TIP_BG": "#FFFFE0", "TIP_FG": "#000000",
        "SASH": "#9AA4B0", "WARN": "#B85C00", "HOVER": "#EEF3FA", "CARD_FAV": "#FFF8DC",
    },
}
THEME_LABELS = {"norton": "Norton (bleu, défaut)", "sombre": "Sombre", "clair": "Clair"}
C: Dict[str, str] = dict(THEMES["norton"])

FONT_SPECS: Dict[str, Tuple[str, int, str]] = {
    "ArsUI": ("Consolas", 11, "normal"),
    "ArsUIB": ("Consolas", 11, "bold"),
    "ArsSM": ("Consolas", 9, "normal"),
    "ArsTitle": ("Consolas", 14, "bold"),
    "ArsBig": ("Consolas", 17, "bold"),
    "ArsTile": ("Consolas", 10, "bold"),
    "ArsTileD": ("Consolas", 9, "normal"),
    "ArsMono": ("Consolas", 10, "normal"),
    "ArsHead": ("Consolas", 10, "bold"),
    "ArsEmoji": ("Segoe UI Emoji", 18, "normal"),
    "ArsEmojiBig": ("Segoe UI Emoji", 30, "normal"),
    "ArsEmojiSM": ("Segoe UI Emoji", 12, "normal"),
}
FONT_DELTA_MIN, FONT_DELTA_MAX = -3, 8
_FONT_OBJS: Dict[str, Any] = {}


def init_fonts(root, delta: int = 0) -> None:
    delta = max(FONT_DELTA_MIN, min(FONT_DELTA_MAX, int(delta or 0)))
    try:
        fams = {f.lower() for f in tkfont.families(root)}
    except Exception:
        fams = set()
    for name, (fam, size, weight) in FONT_SPECS.items():
        if fams and fam.lower() not in fams:
            fam = {"Consolas": "DejaVu Sans Mono", "Segoe UI Emoji": "DejaVu Sans"}.get(fam, "DejaVu Sans")
        kw = dict(family=fam, size=max(6, size + delta), weight=weight)
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


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def norm(s: str) -> str:
    """Minuscules sans accents (recherche)."""
    s = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(ch for ch in s if not unicodedata.combining(ch)).lower()


def ver_key(s: str) -> Tuple[int, ...]:
    return tuple(int(x) if x.isdigit() else 0 for x in re.split(r"[.\-]", s))


def find_mpcmdrun() -> str:
    """MpCmdRun.exe le plus recent (Platform) sinon %ProgramFiles%\\Windows Defender."""
    cands: List[Tuple[Tuple[int, ...], str]] = []
    plat = os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), "Microsoft", "Windows Defender", "Platform")
    try:
        for d in os.listdir(plat):
            p = os.path.join(plat, d, "MpCmdRun.exe")
            if os.path.isfile(p):
                cands.append((ver_key(d), p))
    except OSError:
        pass
    if cands:
        return max(cands)[1]
    return os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Windows Defender", "MpCmdRun.exe")


def find_pythonw() -> str:
    if IS_WIN:
        for root in (os.environ.get("LOCALAPPDATA", ""), os.environ.get("USERPROFILE", "")):
            if root:
                cand = os.path.join(root, "Python", "pythoncore-3.14-64", "pythonw.exe")
                if os.path.isfile(cand):
                    return cand
        exe = sys.executable or ""
        d, n = os.path.split(exe)
        if n.lower() == "pythonw.exe":
            return exe
        if n.lower() == "python.exe" and os.path.isfile(os.path.join(d, "pythonw.exe")):
            return os.path.join(d, "pythonw.exe")
        w = shutil.which("pythonw.exe")
        if w and "windowsapps" not in w.lower():
            return w
    return sys.executable or "pythonw"


def find_python() -> str:
    pw = find_pythonw()
    d, n = os.path.split(pw)
    if n.lower() == "pythonw.exe" and os.path.isfile(os.path.join(d, "python.exe")):
        return os.path.join(d, "python.exe")
    return sys.executable or "python"


def padawan_dir() -> str:
    if os.path.isfile(os.path.join(BASE, "padawan39.py")) or os.path.isfile(os.path.join(BASE, "padawan_tray.py")):
        return BASE
    if os.path.isdir(PADAWAN_DIR_DEFAULT):
        return PADAWAN_DIR_DEFAULT
    return BASE


def powershell_exe() -> str:
    p = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    return p if os.path.isfile(p) or not IS_WIN else "powershell.exe"


def cmd_exe() -> str:
    return os.environ.get("ComSpec") or os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "cmd.exe")


def refresh_path_from_registry() -> int:
    """Complete le PATH du processus avec celui du Registre (outils installes apres le demarrage de la session,
    ex. ffmpeg via winget) : Arsenal trouve ffmpeg/ollama meme s'il a ete lance par un programme plus ancien."""
    if not IS_WIN:
        return 0
    try:
        import winreg
    except ImportError:
        return 0
    found: List[str] = []
    for hive, key in ((winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
                      (winreg.HKEY_CURRENT_USER, r"Environment")):
        try:
            with winreg.OpenKey(hive, key) as k:
                val, _t = winreg.QueryValueEx(k, "Path")
            found += [os.path.expandvars(p.strip()) for p in str(val).split(";") if p.strip()]
        except OSError:
            continue
    cur = os.environ.get("PATH", "")
    have = {p.strip().rstrip("\\").lower() for p in cur.split(";") if p.strip()}
    extra = [p for p in found if p.rstrip("\\").lower() not in have]
    if extra:
        os.environ["PATH"] = cur.rstrip(";") + ";" + ";".join(dict.fromkeys(extra))
    return len(extra)


_BUILTIN_CACHE: Dict[str, str] = {}


def builtin_vars() -> Dict[str, str]:
    if not _BUILTIN_CACHE:
        _BUILTIN_CACHE.update({
            "MPCMDRUN": find_mpcmdrun(),
            "PROJET": padawan_dir(),
            "ARSENAL": BASE,
            "PYTHONW": find_pythonw(),
            "PYTHON": find_python(),
            "WEB": r"C:\web" if os.path.isdir(r"C:\web") else os.path.expanduser("~"),
            "POWERSHELL": powershell_exe(),
        })
    return _BUILTIN_CACHE


PLACEHOLDER_RE = re.compile(r"\{([A-Z][A-Z0-9_]{1,30})\}")


def placeholders_in(*texts: str) -> List[str]:
    out: List[str] = []
    bv = builtin_vars()
    for t in texts:
        for m in PLACEHOLDER_RE.finditer(t or ""):
            k = m.group(1)
            if k not in bv and k not in out:
                out.append(k)
    return out


def expand(text: str, values: Optional[Dict[str, str]] = None) -> str:
    vals = dict(builtin_vars())
    if values:
        vals.update({k: str(v) for k, v in values.items()})

    def rep(m):
        k = m.group(1)
        return vals.get(k, m.group(0))
    return PLACEHOLDER_RE.sub(rep, text or "")


def expand_path(text: str, values: Optional[Dict[str, str]] = None) -> str:
    return os.path.expandvars(os.path.expanduser(expand(text, values))).strip().strip('"')


def safe_title(s: str) -> str:
    return re.sub(r'[&|<>^%"!()]', "", s or "")[:60]


def decode_bytes(b: bytes) -> str:
    for enc in ("utf-8", "cp850", "cp1252"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return b.decode("utf-8", errors="replace")


def which_or_path(p: str) -> bool:
    """True si l'exe/chemin requis existe (chemin absolu ou dans le PATH)."""
    p = expand_path(p)
    if not p:
        return True
    if os.path.isabs(p) or "\\" in p:
        return os.path.exists(p)
    return shutil.which(p) is not None or os.path.exists(os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", p))


# ---------------------------------------------------------------- types d'entrees
TYPES: Dict[str, Dict[str, str]] = {
    "url": {"label": "Lien web", "icon": "🌐", "target": "Adresse (URL)",
            "help": "Une page Internet ou locale : https://..., http://localhost/..."},
    "file": {"label": "Programme / fichier / raccourci", "icon": "📄", "target": "Chemin du programme ou du fichier",
             "help": "Un .exe, un raccourci .lnk, un document, une console .msc..."},
    "folder": {"label": "Dossier", "icon": "📁", "target": "Chemin du dossier",
               "help": "Ouvre un dossier dans l'Explorateur (variables %APPDATA% acceptées)."},
    "script": {"label": "Script (.bat .cmd .ps1 .py)", "icon": "📜", "target": "Chemin du script",
               "help": "Un fichier batch, PowerShell ou Python, avec console au choix."},
    "cmd": {"label": "Commande CMD", "icon": "⌨", "target": "Commande CMD",
            "help": "Une ligne de commande (ipconfig, sfc...). Plusieurs commandes : séparer par &"},
    "ps": {"label": "Commande PowerShell", "icon": "🔷", "target": "Commande PowerShell",
           "help": "Une ou plusieurs lignes PowerShell (Get-..., Test-NetConnection...)."},
    "copy": {"label": "Aide-mémoire (copier)", "icon": "📋", "target": "Texte à copier",
             "help": "Ne lance rien : Entrée copie le texte dans le presse-papiers."},
    "shell": {"label": "Raccourci Windows (shell:, ms-settings:)", "icon": "🪟", "target": "Adresse Windows",
              "help": "shell:startup, ms-settings:display, shell:::{CLSID} (GodMode)..."},
    "builtin": {"label": "Outil intégré", "icon": "✨", "target": "Outil",
                "help": "Fonction intégrée à Arsenal (ex. Mon IP)."},
}
TYPE_ORDER = ["url", "file", "folder", "script", "cmd", "ps", "copy", "shell"]
CONSOLE_MODES = [
    ("keep", "Rester ouverte"),
    ("pause", "Pause puis fermer"),
    ("close", "Fermer à la fin"),
    ("capture", "Résultat dans Arsenal (cachée)"),
    ("hidden", "Cachée, sans résultat"),
]
CONSOLE_LABEL = dict(CONSOLE_MODES)
ASK_KINDS = [("text", "Texte"), ("folder", "Dossier"), ("file", "Fichier"), ("drive", "Lettre de disque")]
ASK_LABEL = dict(ASK_KINDS)
SHELL_SUGGESTIONS = [
    "shell:startup", "shell:common startup", "shell:AppData", "shell:Local AppData", "shell:sendto",
    "shell:recent", "shell:fonts", "shell:downloads", "shell:Desktop", "shell:AppsFolder",
    "shell:RecycleBinFolder", "shell:MyComputerFolder", "shell:::{ED7BA470-8E54-465E-825C-99712043E01C}",
    "ms-settings:", "ms-settings:display", "ms-settings:sound", "ms-settings:windowsupdate",
    "ms-settings:appsfeatures", "ms-settings:startupapps", "ms-settings:network-status",
    "ms-settings:bluetooth", "ms-settings:storagesense", "windowsdefender:",
]


def default_entry() -> Dict[str, Any]:
    return {
        "id": new_id(), "seed": "", "name": "", "type": "url", "target": "", "args": "", "cwd": "",
        "category": "", "group": "", "desc": "", "icon": "", "icon_file": "", "tags": [],
        "admin": False, "console": "keep", "confirm": False, "danger": False, "fav": False,
        "hidden": False, "uses": 0, "last_used": "", "created": now_iso(), "order": 0.0,
        "ask": [], "requires": "",
    }


def fix_entry(e: Dict[str, Any]) -> Dict[str, Any]:
    base = default_entry()
    base.update({k: v for k, v in e.items() if v is not None})
    if not isinstance(base.get("tags"), list):
        base["tags"] = [t.strip() for t in str(base.get("tags") or "").split(",") if t.strip()]
    if base["type"] not in TYPES:
        base["type"] = "url"
    if base["console"] not in CONSOLE_LABEL:
        base["console"] = "keep"
    if not isinstance(base.get("ask"), list):
        base["ask"] = []
    for k in ("admin", "confirm", "danger", "fav", "hidden"):
        base[k] = bool(base.get(k))
    try:
        base["uses"] = int(base.get("uses") or 0)
    except (TypeError, ValueError):
        base["uses"] = 0
    try:
        base["order"] = float(base.get("order") or 0)
    except (TypeError, ValueError):
        base["order"] = 0.0
    return base


# ---------------------------------------------------------------- construction de la commande
def ps_encode(script: str) -> str:
    return base64.b64encode(script.encode("utf-16-le")).decode("ascii")


def build_launch(e: Dict[str, Any], values: Optional[Dict[str, str]] = None, admin: Optional[bool] = None,
                 console: Optional[str] = None) -> Dict[str, Any]:
    """Calcule comment lancer une entree.

    Retour : {kind: shell|capture|copy|builtin, file, params, cwd, verb, show, display, copy, capture_cmd}
    - display : la commande exacte lisible (montree avant un lancement admin)
    - copy    : texte copie par « Copier la commande »
    """
    t = e.get("type", "url")
    adm = bool(e.get("admin")) if admin is None else bool(admin)
    mode = console or e.get("console") or "keep"
    name = e.get("name", "")
    target = expand(e.get("target", ""), values)
    args = expand(e.get("args", ""), values)
    cwd = expand_path(e.get("cwd", ""), values) if e.get("cwd") else ""
    verb = "runas" if adm else "open"
    res: Dict[str, Any] = {"kind": "shell", "file": "", "params": "", "cwd": cwd, "verb": verb, "show": 1,
                           "display": "", "copy": target, "mode": mode, "admin": adm}
    if t == "copy":
        res.update(kind="copy", display=target, copy=target)
        return res
    if t == "builtin":
        res.update(kind="builtin", display=f"(outil intégré : {target})", copy=target)
        return res
    if t == "url":
        res.update(file=target.strip(), params="", verb="open", display=target.strip(), copy=target.strip(), admin=False)
        return res
    if t == "shell":
        tg = target.strip()
        if tg.lower().startswith("shell:"):
            res.update(file="explorer.exe", params=tg, display=f"explorer.exe {tg}", copy=f"explorer.exe {tg}")
        else:
            res.update(file=tg, params=args, display=(tg + (" " + args if args else "")), copy=tg)
        return res
    if t in ("file", "folder"):
        path = expand_path(e.get("target", ""), values)
        if t == "folder":
            res.update(file=path, params="", display=f'explorer.exe "{path}"', copy=path)
            return res
        disp = f'"{path}"' + (f" {args}" if args else "")
        res.update(file=path, params=args, display=disp, copy=disp)
        if not cwd:
            res["cwd"] = os.path.dirname(path) if os.path.isabs(path) else ""
        return res
    line = ""
    script = ""
    if t == "script":
        path = expand_path(e.get("target", ""), values)
        ext = os.path.splitext(path)[1].lower()
        if not cwd and os.path.isabs(path):
            res["cwd"] = os.path.dirname(path)
        if ext in (".bat", ".cmd"):
            line = f'"{path}"' + (f" {args}" if args else "")
            t = "cmd"
        elif ext == ".ps1":
            script = f"& '{path}'" + (f" {args}" if args else "")
            t = "ps"
        elif ext in (".py", ".pyw"):
            py = builtin_vars()["PYTHONW"] if ext == ".pyw" or mode in ("hidden",) else builtin_vars()["PYTHON"]
            line = f'"{py}" "{path}"' + (f" {args}" if args else "")
            t = "cmd"
        else:
            disp = f'"{path}"' + (f" {args}" if args else "")
            res.update(file=path, params=args, display=disp, copy=disp)
            return res
        res["copy"] = f'"{path}"' + (f" {args}" if args else "")
    elif t == "cmd":
        line = target.replace("\r\n", "\n").strip()
        line = " & ".join(x.strip() for x in line.split("\n") if x.strip())
        res["copy"] = line
    elif t == "ps":
        script = target.replace("\r\n", "\n").strip()
        res["copy"] = script
    if t == "cmd":
        title = f"title Arsenal - {safe_title(name)} & " if name else ""
        color = "color 1F & " if CONSOLE_COLORS[0] else ""
        if mode == "keep":
            params = f'/d /s /k "{title}{color}{line}"'
        elif mode == "pause":
            params = f'/d /s /c "{title}{color}{line} & echo. & pause"'
        elif mode == "close":
            params = f'/d /s /c "{title}{line}"'
        else:
            params = f'/d /s /c "chcp 65001 >nul & {line}"'
        res.update(file=cmd_exe(), params=params, display=line if mode in ("capture", "hidden") else f"cmd.exe {params}")
        if mode in ("capture", "hidden"):
            res["kind"] = "capture" if mode == "capture" else "shell"
            res["show"] = 0
            res["capture_cmd"] = f'"{cmd_exe()}" {params}'
            res["capture_line"] = line
            res["display"] = f'cmd.exe /c {line}'
        return res
    if t == "ps":
        ttl = name.replace("'", "") if name else "PowerShell"
        pre = ""
        if mode in ("keep", "pause", "close"):
            pre = f"$Host.UI.RawUI.WindowTitle='Arsenal - {ttl}';"
            if CONSOLE_COLORS[0]:
                pre += "try{$Host.UI.RawUI.BackgroundColor='DarkBlue';$Host.UI.RawUI.ForegroundColor='White';Clear-Host}catch{};"
        body = script
        if mode == "pause":
            body = script + "\nWrite-Host ''; Read-Host 'Appuyez sur Entrée pour fermer' | Out-Null"
        exe = powershell_exe()
        if mode in ("capture", "hidden"):
            full = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8;$OutputEncoding=[Text.Encoding]::UTF8;"
                    "$ProgressPreference='SilentlyContinue';\n& {\n" + body + "\n} *>&1 | Out-String -Stream -Width 220")
            params = f"-NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand {ps_encode(full)}"
            res.update(file=exe, params=params, show=0, kind="capture" if mode == "capture" else "shell",
                       capture_cmd=f'"{exe}" {params}', ps_script=body)
        else:
            noexit = "-NoExit " if mode == "keep" else ""
            params = f"-NoProfile -ExecutionPolicy Bypass {noexit}-EncodedCommand {ps_encode(pre + body)}"
            res.update(file=exe, params=params, ps_script=body)
        flag = "-NoExit " if mode == "keep" else ""
        res["display"] = f"powershell.exe -NoProfile -ExecutionPolicy Bypass {flag}-Command {{\n{body}\n}}"
        return res
    return res


# ---------------------------------------------------------------- execution Windows
if IS_WIN:
    from ctypes import wintypes

    class SHELLEXECUTEINFOW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD), ("fMask", ctypes.c_ulong), ("hwnd", wintypes.HWND),
            ("lpVerb", wintypes.LPCWSTR), ("lpFile", wintypes.LPCWSTR), ("lpParameters", wintypes.LPCWSTR),
            ("lpDirectory", wintypes.LPCWSTR), ("nShow", ctypes.c_int), ("hInstApp", wintypes.HINSTANCE),
            ("lpIDList", ctypes.c_void_p), ("lpClass", wintypes.LPCWSTR), ("hkeyClass", wintypes.HKEY),
            ("dwHotKey", wintypes.DWORD), ("hIconOrMonitor", wintypes.HANDLE), ("hProcess", wintypes.HANDLE),
        ]


def shell_execute(file: str, params: str = "", cwd: str = "", verb: str = "open", show: int = 1,
                  want_handle: bool = False) -> Tuple[bool, str, Any]:
    """ShellExecuteExW (verb runas = UAC). Retour (ok, message, hProcess)."""
    if not IS_WIN:
        return False, "Windows requis", None
    try:
        sei = SHELLEXECUTEINFOW()
        sei.cbSize = ctypes.sizeof(SHELLEXECUTEINFOW)
        sei.fMask = 0x00000100 | (0x00000040 if want_handle else 0)  # NOASYNC | NOCLOSEPROCESS
        sei.hwnd = None
        sei.lpVerb = verb or "open"
        sei.lpFile = file
        sei.lpParameters = params or None
        sei.lpDirectory = cwd if cwd and os.path.isdir(cwd) else None
        sei.nShow = show
        ok = ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(sei))
        if not ok:
            err = ctypes.GetLastError()
            if err == 1223:
                return False, "Annulé (UAC refusé)", None
            return False, f"Erreur Windows {err} : {ctypes.FormatError(err).strip()}", None
        return True, "", sei.hProcess if want_handle else None
    except Exception as ex:
        return False, str(ex), None


def wait_process(h, timeout_ms: int = 500) -> Optional[int]:
    """None si encore en cours, sinon code de sortie."""
    k32 = ctypes.windll.kernel32
    r = k32.WaitForSingleObject(h, timeout_ms)
    if r == 0x102:  # WAIT_TIMEOUT
        return None
    code = wintypes.DWORD()
    k32.GetExitCodeProcess(h, ctypes.byref(code))
    k32.CloseHandle(h)
    return int(code.value)


def admin_capture_command(spec: Dict[str, Any], outfile: str) -> Tuple[str, str]:
    """(file, params) pour executer en admin, cache, avec la sortie dans outfile."""
    if spec.get("ps_script") is not None:
        body = spec["ps_script"]
        full = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8;$ProgressPreference='SilentlyContinue';\n& {\n"
                + body + "\n} *>&1 | Out-String -Stream -Width 220 | Out-File -FilePath '"
                + outfile.replace("'", "''") + "' -Encoding utf8")
        return powershell_exe(), f"-NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand {ps_encode(full)}"
    line = spec.get("capture_line") or ""
    return cmd_exe(), f'/d /s /c "chcp 65001 >nul & ( {line} ) > "{outfile}" 2>&1"'


def kill_tree(pid: int) -> None:
    try:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW if IS_WIN else 0, timeout=10)
    except Exception:
        pass


def copy_to_clipboard(root, text: str) -> None:
    try:
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update_idletasks()
    except Exception:
        pass


# ---------------------------------------------------------------- IP locale / publique
def local_ips() -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1)
        s.connect(("8.8.8.8", 80))
        out.append(("IPv4 principale", s.getsockname()[0]))
        s.close()
    except OSError:
        pass
    try:
        host = socket.gethostname()
        seen = {ip for _, ip in out}
        for fam, _, _, _, sa in socket.getaddrinfo(host, None):
            ip = sa[0]
            if ip in seen or ip.startswith("127.") or ip == "::1":
                continue
            seen.add(ip)
            if fam == socket.AF_INET:
                out.append(("IPv4", ip))
            elif not ip.lower().startswith("fe80"):
                out.append(("IPv6", ip.split("%")[0]))
    except OSError:
        pass
    return out


def public_ip(v6: bool = False) -> str:
    urls = (["https://api64.ipify.org"] if v6 else
            ["https://api.ipify.org", "https://ipv4.icanhazip.com", "https://ifconfig.me/ip"])
    for u in urls:
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "Arsenal/1"})
            with urllib.request.urlopen(req, timeout=6) as r:
                ip = r.read(100).decode("ascii", "ignore").strip()
            if re.fullmatch(r"[0-9a-fA-F:.]{3,45}", ip):
                return ip
        except Exception:
            continue
    return ""


# ---------------------------------------------------------------- icones extraites des programmes
def extract_icon_png(path: str, size: int = 32) -> str:
    """Extrait l'icone Windows d'un fichier/dossier/.lnk (SHGetFileInfoW) vers _icones_arsenal\\*.png."""
    if not IS_WIN or not path:
        return ""
    try:
        from PIL import Image, ImageChops  # type: ignore
    except ImportError:
        return ""
    import hashlib
    path = expand_path(path)
    if not os.path.exists(path):
        return ""
    key = hashlib.sha1(path.lower().encode("utf-8")).hexdigest()[:16] + ".png"
    out = os.path.join(ICON_DIR, key)
    if os.path.isfile(out):
        return key

    class SHFILEINFOW(ctypes.Structure):
        _fields_ = [("hIcon", wintypes.HICON), ("iIcon", ctypes.c_int), ("dwAttributes", wintypes.DWORD),
                    ("szDisplayName", wintypes.WCHAR * 260), ("szTypeName", wintypes.WCHAR * 80)]

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
                    ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                    ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]

    shell32, user32, gdi32 = ctypes.windll.shell32, ctypes.windll.user32, ctypes.windll.gdi32
    shell32.SHGetFileInfoW.restype = ctypes.c_void_p
    gdi32.CreateDIBSection.restype = wintypes.HBITMAP
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    user32.GetDC.restype = wintypes.HDC
    gdi32.SelectObject.restype = wintypes.HGDIOBJ
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi32.DeleteDC.argtypes = [wintypes.HDC]
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user32.DrawIconEx.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.HICON, ctypes.c_int,
                                  ctypes.c_int, wintypes.UINT, wintypes.HBRUSH, wintypes.UINT]
    user32.DestroyIcon.argtypes = [wintypes.HICON]
    gdi32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.c_void_p, wintypes.UINT, ctypes.POINTER(ctypes.c_void_p),
                                       wintypes.HANDLE, wintypes.DWORD]
    sfi = SHFILEINFOW()
    r = shell32.SHGetFileInfoW(path, 0, ctypes.byref(sfi), ctypes.sizeof(sfi), 0x100 | 0x0)  # SHGFI_ICON|LARGE
    if not r or not sfi.hIcon:
        return ""
    hicon = sfi.hIcon
    imgs = []
    try:
        for bg in (0x00, 0xFF):
            hdc_s = user32.GetDC(None)
            hdc = gdi32.CreateCompatibleDC(hdc_s)
            bmi = BITMAPINFOHEADER()
            bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.biWidth, bmi.biHeight, bmi.biPlanes, bmi.biBitCount = size, -size, 1, 32
            bits = ctypes.c_void_p()
            hbmp = gdi32.CreateDIBSection(hdc, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
            old = gdi32.SelectObject(hdc, hbmp)
            ctypes.memset(bits, bg, size * size * 4)
            user32.DrawIconEx(hdc, 0, 0, hicon, size, size, 0, None, 3)
            buf = ctypes.string_at(bits, size * size * 4)
            imgs.append(Image.frombuffer("RGBA", (size, size), buf, "raw", "BGRA", 0, 1).convert("RGB"))
            gdi32.SelectObject(hdc, old)
            gdi32.DeleteObject(hbmp)
            gdi32.DeleteDC(hdc)
            user32.ReleaseDC(None, hdc_s)
    finally:
        user32.DestroyIcon(hicon)
    black, white = imgs
    diff = ImageChops.subtract(white, black).convert("L")
    alpha = diff.point(lambda v: 255 - v)
    img = black.copy().convert("RGBA")
    px_b = black.load()
    px_a = alpha.load()
    px = img.load()
    for y in range(size):
        for x in range(size):
            a = px_a[x, y]
            if a == 0:
                px[x, y] = (0, 0, 0, 0)
            else:
                r_, g_, b_ = px_b[x, y]
                px[x, y] = (min(255, r_ * 255 // a), min(255, g_ * 255 // a), min(255, b_ * 255 // a), a)
    if img.getbbox() is None:
        return ""
    os.makedirs(ICON_DIR, exist_ok=True)
    img.save(out)
    return key


def generate_app_icons(out_dir: str) -> Tuple[str, str]:
    """arsenal1.ico / arsenal1.png / arsenal1_256.png : boite a outils + eclair jaune sur bleu Norton."""
    ico = os.path.join(out_dir, "arsenal1.ico")
    png = os.path.join(out_dir, "arsenal1.png")
    big = os.path.join(out_dir, "arsenal1_256.png")
    if os.path.isfile(ico) and os.path.isfile(png) and os.path.isfile(big):
        return ico, png
    try:
        from PIL import Image, ImageDraw  # type: ignore
    except ImportError:
        return "", ""
    S = 256
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([6, 6, S - 7, S - 7], radius=44, fill=(0, 0, 170, 255), outline=(85, 255, 255, 255), width=10)
    # boite a outils
    d.rounded_rectangle([86, 70, 170, 104], radius=14, outline=(85, 255, 255, 255), width=12)
    d.rounded_rectangle([40, 96, 216, 206], radius=18, fill=(0, 0, 102, 255), outline=(85, 255, 255, 255), width=10)
    d.rectangle([40, 132, 216, 142], fill=(85, 255, 255, 255))
    # eclair
    bolt = [(146, 82), (96, 156), (128, 156), (106, 226), (170, 136), (136, 136), (160, 82)]
    d.polygon(bolt, fill=(255, 255, 85, 255), outline=(0, 0, 0, 255))
    try:
        os.makedirs(out_dir, exist_ok=True)
        img.save(big)
        img.resize((64, 64), Image.Resampling.LANCZOS).save(png)
        img.save(ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    except OSError:
        return "", ""
    return ico, png


# ---------------------------------------------------------------- stockage arsenal.json
class Store:
    """Donnees d'Arsenal : categories + entrees + reglages, sauvegarde atomique et rotation."""

    def __init__(self, path: str = DATA_FILE, readonly: bool = False):
        self.path = path
        self.readonly = readonly
        self.data: Dict[str, Any] = {}
        self.last_backup = 0.0
        self.dirty = False
        self.load_error = ""

    # -- chargement
    def load(self) -> None:
        d: Dict[str, Any] = {}
        seed = os.path.join(BASE, "arsenal_depart.json")
        if not self.readonly and not os.path.exists(self.path) and os.path.isfile(seed):
            try:   # premier lancement sur un autre PC : contenu de depart (jamais par-dessus un arsenal.json)
                shutil.copyfile(seed, self.path)
            except OSError as ex:
                logger.warning("arsenal_depart.json non copie : %s", ex)
        if not os.path.isfile(self.path) and self.readonly and os.path.isfile(seed):
            self.path = seed
        if os.path.isfile(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    d = json.load(f)
                if not isinstance(d, dict):
                    raise ValueError("format inattendu")
            except Exception as ex:
                self.load_error = f"arsenal.json illisible ({ex}) : copie gardée, contenu initial rechargé."
                logger.error(self.load_error)
                try:
                    shutil.copy2(self.path, self.path + ".illisible-" + time.strftime("%Y%m%d-%H%M%S"))
                except OSError:
                    pass
                d = {}
        if not d:
            d = {"app": APP_NAME, "format": 1, "seed_version": 0, "seed_deleted": [],
                 "categories": [], "entries": [], "settings": {}}
        d.setdefault("categories", [])
        d.setdefault("entries", [])
        d.setdefault("settings", {})
        d.setdefault("seed_deleted", [])
        d.setdefault("seed_version", 0)
        d["entries"] = [fix_entry(e) for e in d["entries"] if isinstance(e, dict)]
        cats = []
        for c in d["categories"]:
            if isinstance(c, dict) and c.get("id"):
                c.setdefault("name", c["id"])
                c.setdefault("icon", "📂")
                cats.append(c)
        d["categories"] = cats
        self.data = d
        if int(d.get("seed_version") or 0) < SEED_VERSION:
            added = self.merge_seeds()
            d["seed_version"] = SEED_VERSION
            logger.info("contenu initial : %d entrées ajoutées", added)
            self.dirty = True
        self.ensure_categories()
        if self.dirty:
            self.save(force_backup=False)

    def merge_seeds(self) -> int:
        cats, entries = seed_content()
        have_c = {c["id"] for c in self.data["categories"]}
        for c in cats:
            if c["id"] not in have_c:
                self.data["categories"].append(dict(c))
        have = {e.get("seed") for e in self.data["entries"] if e.get("seed")}
        deleted = set(self.data.get("seed_deleted") or [])
        n = 0
        for e in entries:
            if e["seed"] in have or e["seed"] in deleted:
                continue
            self.data["entries"].append(fix_entry(e))
            n += 1
        return n

    def restore_missing_seeds(self) -> int:
        self.data["seed_deleted"] = []
        n = self.merge_seeds()
        self.dirty = True
        return n

    def ensure_categories(self) -> None:
        ids = {c["id"] for c in self.data["categories"]}
        for e in self.data["entries"]:
            if not e.get("category") or e["category"] not in ids:
                cid = e.get("category") or "mes_ajouts"
                if cid not in ids:
                    self.data["categories"].append({"id": cid, "name": "Mes ajouts" if cid == "mes_ajouts" else cid,
                                                    "icon": "📌"})
                    ids.add(cid)
                e["category"] = cid

    # -- acces
    @property
    def entries(self) -> List[Dict[str, Any]]:
        return self.data["entries"]

    @property
    def categories(self) -> List[Dict[str, Any]]:
        return self.data["categories"]

    @property
    def settings(self) -> Dict[str, Any]:
        return self.data["settings"]

    def cat(self, cid: str) -> Optional[Dict[str, Any]]:
        for c in self.categories:
            if c["id"] == cid:
                return c
        return None

    def cat_name(self, cid: str, with_icon: bool = False) -> str:
        c = self.cat(cid)
        if not c:
            return cid
        return (c.get("icon", "") + " " + c["name"]).strip() if with_icon else c["name"]

    def by_id(self, eid: str) -> Optional[Dict[str, Any]]:
        for e in self.entries:
            if e["id"] == eid:
                return e
        return None

    def next_order(self, cid: str) -> float:
        orders = [e["order"] for e in self.entries if e["category"] == cid]
        return (max(orders) + 1.0) if orders else 1.0

    def add(self, e: Dict[str, Any]) -> Dict[str, Any]:
        e = fix_entry(e)
        if not e.get("category"):
            e["category"] = "mes_ajouts"
        if self.by_id(e["id"]):
            e["id"] = new_id()
        e["order"] = self.next_order(e["category"])
        self.entries.append(e)
        self.ensure_categories()
        self.dirty = True
        return e

    def delete(self, ids: List[str]) -> int:
        idset = set(ids)
        gone = [e for e in self.entries if e["id"] in idset]
        for e in gone:
            if e.get("seed"):
                self.data["seed_deleted"].append(e["seed"])
        self.data["entries"] = [e for e in self.entries if e["id"] not in idset]
        self.dirty = True
        return len(gone)

    def reorder(self, cid: str, ordered_ids: List[str]) -> None:
        pos = {eid: i for i, eid in enumerate(ordered_ids)}
        for e in self.entries:
            if e["category"] == cid and e["id"] in pos:
                e["order"] = float(pos[e["id"]] + 1)
        self.dirty = True

    def dedupe_key(self, e: Dict[str, Any]) -> Tuple[str, str]:
        t = e.get("type", "")
        tg = (e.get("target") or "").strip()
        if t == "url":
            tg = tg.lower().rstrip("/").replace("http://", "https://").replace("://www.", "://")
        else:
            tg = tg.lower()
        return (t, tg)

    def import_entries(self, items: List[Dict[str, Any]], cats: Optional[List[Dict[str, Any]]] = None) -> Tuple[int, int]:
        """Ajoute en evitant les doublons (type + cible). Retour (ajoutees, doublons)."""
        for c in cats or []:
            if c.get("id") and not self.cat(c["id"]):
                self.categories.append({"id": c["id"], "name": c.get("name") or c["id"], "icon": c.get("icon") or "📂"})
        have = {self.dedupe_key(e) for e in self.entries}
        added = dup = 0
        for it in items:
            k = self.dedupe_key(it)
            if k in have:
                dup += 1
                continue
            have.add(k)
            e = dict(it)
            e["id"] = new_id()
            e["seed"] = ""
            if str(e.get("type", "")) not in ("url", "copy", "folder", "shell", "builtin"):
                e["confirm"] = True   # paquet recu : une commande importee demande toujours confirmation
                e["admin"] = False    # et ne garde jamais les droits admin (a remettre soi-meme)
            self.add(e)
            added += 1
        self.dirty = True
        return added, dup

    # -- sauvegarde
    def snapshot(self) -> Dict[str, Any]:
        return copy.deepcopy({k: v for k, v in self.data.items() if k != "settings"})

    def restore(self, snap: Dict[str, Any]) -> None:
        st = self.data.get("settings", {})
        self.data = copy.deepcopy(snap)
        self.data["settings"] = st
        self.dirty = True

    def save(self, force_backup: bool = False) -> bool:
        if self.readonly:
            self.dirty = False
            return True
        self.data["app"] = APP_NAME
        self.data["format"] = 1
        self.data["saved_at"] = now_iso()
        self.data["saved_by"] = f"arsenal{APP_FILE_VER}.py"
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)
            self.dirty = False
        except OSError as ex:
            logger.error("sauvegarde arsenal.json : %s", ex)
            return False
        self.backup(force=force_backup)
        return True

    def backup(self, force: bool = False) -> Optional[str]:
        if self.readonly or not os.path.isfile(self.path):
            return None
        if not force and time.time() - self.last_backup < BACKUP_MIN_INTERVAL:
            return None
        try:
            os.makedirs(BACKUP_DIR, exist_ok=True)
            names = sorted(n for n in os.listdir(BACKUP_DIR) if n.startswith("arsenal-") and n.endswith(".json"))
            if not force and names:
                last = os.path.join(BACKUP_DIR, names[-1])
                if time.time() - os.path.getmtime(last) < BACKUP_MIN_INTERVAL:
                    self.last_backup = time.time()
                    return None
            dst = os.path.join(BACKUP_DIR, "arsenal-" + time.strftime("%Y%m%d-%H%M%S") + ".json")
            shutil.copy2(self.path, dst)
            self.last_backup = time.time()
            names = sorted(n for n in os.listdir(BACKUP_DIR) if n.startswith("arsenal-") and n.endswith(".json"))
            for old in names[:-BACKUP_KEEP]:
                try:
                    os.remove(os.path.join(BACKUP_DIR, old))
                except OSError:
                    pass
            return dst
        except OSError as ex:
            logger.warning("sauvegarde auto : %s", ex)
            return None


# ---------------------------------------------------------------- import / export
def _slug(s: str) -> str:
    s = norm(s)
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s[:40] or "cat"


def _clean_title(t: str, url: str) -> str:
    t = (t or "").strip()
    if t:
        return t[:120]
    m = re.match(r"https?://(?:www\.)?([^/]+)", url or "")
    return m.group(1) if m else (url or "Lien")[:80]


def url_entry(title: str, url: str, cat: str, group: str = "", icon: str = "", desc: str = "",
              tags: Optional[List[str]] = None) -> Dict[str, Any]:
    e = default_entry()
    e.update(type="url", name=_clean_title(title, url), target=url.strip(), category=cat, group=group,
             icon=(icon or "🔖")[:4], desc=desc, tags=tags or [])
    return e


class _FavHTMLParser(HTMLParser):
    """Lit Favoris.php (div.fav data-url/data-title/data-sym) et les fichiers de signets HTML (<A HREF>, <H3>)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.favs: List[Dict[str, str]] = []
        self.links: List[Dict[str, str]] = []
        self.groups: Dict[str, str] = {}
        self._folder: List[str] = []
        self._in_h3 = False
        self._h3 = ""
        self._a: Optional[Dict[str, str]] = None
        self._opt: Optional[str] = None
        self._depth_dl = 0
        self._pending_folder = ""

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "div" and "fav" in (a.get("class") or "").split() and a.get("data-url"):
            self.favs.append({"url": a.get("data-url", ""), "title": a.get("data-title", ""),
                              "sym": a.get("data-sym", ""), "gid": a.get("data-gid", "")})
        elif tag == "option" and a.get("value", "").isdigit():
            self._opt = a["value"]
        elif tag == "h3":
            self._in_h3, self._h3 = True, ""
        elif tag == "dl":
            if self._pending_folder:
                self._folder.append(self._pending_folder)
                self._pending_folder = ""
            else:
                self._folder.append("")
        elif tag == "a" and (a.get("href") or "").lower().startswith(("http://", "https://")):
            self._a = {"url": a["href"], "title": "", "folder": " / ".join(x for x in self._folder if x)}

    def handle_endtag(self, tag):
        if tag == "h3":
            self._in_h3 = False
            self._pending_folder = self._h3.strip()
        elif tag == "dl" and self._folder:
            self._folder.pop()
        elif tag == "a" and self._a is not None:
            self.links.append(self._a)
            self._a = None
        elif tag == "option":
            self._opt = None

    def handle_data(self, data):
        if self._in_h3:
            self._h3 += data
        if self._a is not None:
            self._a["title"] += data
        if self._opt is not None and data.strip():
            self.groups[self._opt] = data.strip()


def parse_favoris_html(text: str, cat: str = "favoris_web") -> List[Dict[str, Any]]:
    p = _FavHTMLParser()
    try:
        p.feed(text)
    except Exception:
        pass
    out: List[Dict[str, Any]] = []
    if p.favs:
        for f in p.favs:
            g = p.groups.get(f["gid"], "") if f["gid"] else ""
            out.append(url_entry(f["title"], f["url"], cat, g or "Favoris.php", f["sym"], tags=["favoris.php"]))
        return out
    for l in p.links:
        out.append(url_entry(l["title"], l["url"], cat, l.get("folder", ""), "🔖", tags=["signets"]))
    return out


def parse_favoris_json(d: Any, cat: str = "favoris_web") -> List[Dict[str, Any]]:
    """Sauvegarde Favoris (favoris_backups / FavorisRecup) : groupes + favoris ; les comptes sont ignores."""
    groups: Dict[str, str] = {}
    favs: List[Dict[str, Any]] = []

    def walk(o: Any, key: str = ""):
        if isinstance(o, dict):
            for k, v in o.items():
                if "user" in k.lower() or "token" in k.lower():
                    continue  # jamais de comptes / mots de passe
                walk(v, k)
        elif isinstance(o, list):
            for it in o:
                if isinstance(it, dict) and it.get("url"):
                    favs.append(it)
                elif isinstance(it, dict) and "name" in it and "id" in it and "group" in key.lower():
                    groups[str(it["id"])] = str(it["name"])
                else:
                    walk(it, key)
    walk(d)
    out = []
    for f in favs:
        g = groups.get(str(f.get("group_id") or ""), "") or "Sans groupe"
        sym = str(f.get("unicode_symbol") or f.get("sym") or "")
        out.append(url_entry(str(f.get("title") or ""), str(f.get("url")), cat, g, sym, tags=["favoris.php"]))
    return out


def parse_chrome_bookmarks(d: Dict[str, Any], cat: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    def walk(node: Dict[str, Any], path: List[str]):
        if node.get("type") == "url" and str(node.get("url", "")).lower().startswith(("http://", "https://")):
            out.append(url_entry(node.get("name", ""), node["url"], cat, " / ".join(path[-2:]), "🔖", tags=["signets"]))
        for ch in node.get("children", []) or []:
            walk(ch, path + ([node.get("name", "")] if node.get("type") == "folder" and node.get("name") else []))
    for k, root in (d.get("roots") or {}).items():
        if isinstance(root, dict):
            walk(root, [])
    return out


def browser_bookmark_files() -> List[Tuple[str, str]]:
    la = os.environ.get("LOCALAPPDATA", "")
    cands = [("Chrome", os.path.join(la, "Google", "Chrome", "User Data")),
             ("Edge", os.path.join(la, "Microsoft", "Edge", "User Data")),
             ("Brave", os.path.join(la, "BraveSoftware", "Brave-Browser", "User Data"))]
    out = []
    for name, root in cands:
        if not os.path.isdir(root):
            continue
        for prof in ["Default"] + sorted(p for p in os.listdir(root) if p.startswith("Profile ")):
            f = os.path.join(root, prof, "Bookmarks")
            if os.path.isfile(f):
                out.append((f"{name} ({prof})", f))
    return out


def latest_favoris_backup() -> str:
    try:
        names = sorted(n for n in os.listdir(FAVORIS_BACKUP_DIR) if n.lower().endswith(".json"))
        best = ""
        for n in reversed(names):
            p = os.path.join(FAVORIS_BACKUP_DIR, n)
            if os.path.getsize(p) > 1000:
                best = p
                break
        return best
    except OSError:
        return ""


def read_import_file(path: str, cat_hint: str = "") -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], str]:
    """Detecte le format : Arsenal JSON, signets Chrome/Edge, sauvegarde Favoris, HTML (Favoris.php / signets)."""
    with open(path, "rb") as f:
        raw = f.read(30_000_000)
    text = decode_bytes(raw)
    st = text.lstrip()
    if st.startswith("{") or st.startswith("["):
        d = json.loads(text)
        if isinstance(d, dict) and d.get("app") == APP_NAME and isinstance(d.get("entries"), list):
            return [fix_entry(e) for e in d["entries"]], d.get("categories") or [], "Arsenal"
        if isinstance(d, dict) and "roots" in d:
            cid = cat_hint or "signets_navigateur"
            return parse_chrome_bookmarks(d, cid), [{"id": cid, "name": "Signets navigateur", "icon": "🔖"}], "signets"
        cid = cat_hint or "favoris_web"
        return parse_favoris_json(d, cid), [{"id": cid, "name": "Mes favoris web", "icon": "⭐"}], "Favoris"
    cid = cat_hint or "favoris_web"
    items = parse_favoris_html(text, cid)
    return items, [{"id": cid, "name": "Mes favoris web", "icon": "⭐"}], "HTML"


def fetch_url_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 Arsenal/1"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return decode_bytes(r.read(10_000_000))


def export_json(store: Store, path: str, entries: Optional[List[Dict[str, Any]]] = None) -> int:
    ents = entries if entries is not None else store.entries
    cids = {e["category"] for e in ents}
    d = {"app": APP_NAME, "format": 1, "exported_at": now_iso(),
         "categories": [c for c in store.categories if c["id"] in cids],
         "entries": [{k: v for k, v in e.items() if k not in ("uses", "last_used")} for e in ents]}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    return len(ents)


def export_html(store: Store, path: str, entries: Optional[List[Dict[str, Any]]] = None) -> int:
    ents = entries if entries is not None else [e for e in store.entries if not e.get("hidden")]
    parts = ["<!doctype html><html lang='fr'><head><meta charset='utf-8'><title>Arsenal - catalogue</title>",
             "<style>body{background:#0000AA;color:#55FFFF;font-family:Consolas,monospace;margin:20px}"
             "h1{color:#FFFF55}h2{color:#FFFF55;border-bottom:2px solid #55FFFF;padding-top:14px}"
             "h3{color:#FFFFFF;margin:10px 0 4px}a{color:#FFFF55}"
             ".e{background:#000066;border:1px solid #3355AA;margin:6px 0;padding:6px 10px}"
             ".n{color:#fff;font-weight:bold}.d{color:#88AACC}code{display:block;white-space:pre-wrap;"
             "background:#000033;color:#fff;padding:4px 6px;margin-top:4px}.b{color:#FFAA33}</style></head><body>",
             f"<h1>⚡ Arsenal — {len(ents)} entrées</h1><p>Exporté le {html.escape(now_iso())}</p>"]
    for c in store.categories:
        ce = sorted([e for e in ents if e["category"] == c["id"]], key=lambda e: (e.get("group", ""), e["order"]))
        if not ce:
            continue
        parts.append(f"<h2>{html.escape(c.get('icon', ''))} {html.escape(c['name'])} ({len(ce)})</h2>")
        g_last = None
        for e in ce:
            if e.get("group") and e["group"] != g_last:
                parts.append(f"<h3>{html.escape(e['group'])}</h3>")
                g_last = e["group"]
            badges = (" <span class='b'>🛡 admin</span>" if e.get("admin") else "") + \
                     (" <span class='b'>⚠ dangereux</span>" if e.get("danger") else "")
            tgt = html.escape(e.get("target", ""))
            if e["type"] == "url":
                body = f"<a href='{tgt}'>{tgt}</a>"
            else:
                body = f"<code>{tgt}{(' ' + html.escape(e.get('args', ''))) if e.get('args') else ''}</code>"
            parts.append(f"<div class='e'><span class='n'>{html.escape(e.get('icon', ''))} {html.escape(e['name'])}</span>"
                         f"{badges}<div class='d'>{html.escape(e.get('desc', ''))}</div>{body}</div>")
    parts.append("</body></html>")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    return len(ents)


def search_score(e: Dict[str, Any], tokens: List[str], catname: str) -> int:
    """Pertinence : debut du nom > debut d'un mot du nom > mot-cle > debut de mot ailleurs.
    Les mots de 1-2 lettres ne correspondent qu'en debut de mot (« ip » ne trouve pas « périphérique »)."""
    if not tokens:
        return 1
    def alt(x: str) -> str:
        return x + " | " + x.replace("-", "").replace("'", "") if ("-" in x or "'" in x) else x
    name = alt(norm(e.get("name", "")))
    tags = alt(norm(" ".join(e.get("tags") or [])))
    other = alt(" ".join([norm(e.get("desc", "")), norm(e.get("target", "")), norm(catname), norm(e.get("group", "")),
                      norm(TYPES.get(e["type"], {}).get("label", ""))]))
    score = 0
    for t in tokens:
        wb = re.compile(r"(?:^|[^a-z0-9])" + re.escape(t))
        if name.startswith(t):
            score += 10
        elif wb.search(name):
            score += 7
        elif len(t) >= 3 and t in name:
            score += 4
        elif wb.search(tags):
            score += 4
        elif wb.search(other):
            score += 2
        elif len(t) >= 3 and (t in tags or t in other):
            score += 1
        else:
            return 0
    return score + min(5, int(e.get("uses") or 0))


# ---------------------------------------------------------------- contenu initial (tout gratuit, integre a Windows)
def A(var: str, label: str, kind: str = "text", default: str = "") -> Dict[str, str]:
    return {"var": var, "label": label, "kind": kind, "default": default}


SEED_CATEGORIES = [
    ("mes_outils", "Mes outils", "🧰"),
    ("favoris_web", "Mes favoris web", "⭐"),
    ("web", "Web pratique", "🌐"),
    ("securite", "Sécurité", "🛡"),
    ("reparation", "Réparation", "🔧"),
    ("nettoyage", "Nettoyage", "🧹"),
    ("reseau", "Réseau", "📡"),
    ("systeme", "Système", "💻"),
    ("processus", "Processus/services", "⚙"),
    ("comptes", "Comptes & session", "👤"),
    ("peripheriques", "Périphériques", "🖨"),
    ("disques", "Disques & fichiers", "💽"),
    ("windows", "Outils Windows", "🪟"),
    ("parametres", "Paramètres", "🎛"),
    ("consoles", "Consoles", "🖥"),
    ("dev", "Développement", "🐍"),
    ("ollama", "Ollama (IA locale)", "🤖"),
    ("media", "yt-dlp & ffmpeg", "🎬"),
    ("clavier", "Raccourcis clavier", "⌨"),
    ("memo", "Aide-mémoire", "📋"),
]


def seed_content() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    cats = [{"id": i, "name": n, "icon": ic} for i, n, ic in SEED_CATEGORIES]
    E: List[Dict[str, Any]] = []
    counts: Dict[str, int] = {}

    def add(cat, sid, name, typ, target, desc, icon="", group="", **kw):
        e = default_entry()
        counts[cat] = counts.get(cat, 0) + 1
        e.update(seed=f"{cat}.{sid}", name=name, type=typ, target=target, desc=desc,
                 icon=icon or TYPES[typ]["icon"], category=cat, group=group, order=float(counts[cat]),
                 created="2026-10-06 14:00:00")
        if typ in ("cmd", "ps") and "console" not in kw:
            kw["console"] = "capture"
        e.update(kw)
        E.append(e)

    # ============================================================ Mes outils
    c = "mes_outils"
    g = "Programmes Padawan"
    add(c, "padawan", "Padawan", "file", "{PYTHONW}", "Ton assistant Padawan (Ollama) avec son icône dans la barre système. "
        "Une seule instance : s'il tourne déjà, rien ne se duplique.", "🤖", g, args='"{PROJET}\\padawan39.py"', cwd="{PROJET}")
    add(c, "gestionnaire", "Gestionnaire de fichiers", "file", "{PYTHONW}", "Le Gestionnaire de fichiers Padawan.", "📁", g,
        args='"{PROJET}\\gestionnaire_fichiers5.py"', cwd="{PROJET}")
    add(c, "archiveur", "Archiveur", "file", "{PYTHONW}", "Archiveur 5 : archive vidéos, posts X/Facebook et pages web "
        "dans C:\\web\\FTP_HOME\\ARCHIVEUR.", "📦", g, args='"{PROJET}\\archiveur5.py"', cwd="{PROJET}")
    add(c, "arsenal", "Arsenal", "file", "{PYTHONW}", "Ce tiroir à outils (une seule fenêtre : la relancer la ramène devant).",
        "⚡", g, args='"{ARSENAL}\\arsenal1.py"', cwd="{ARSENAL}")
    add(c, "facteur", "Facteur", "file", "{PYTHONW}", "Surveillant de dossiers et commandes a distance signees (boite aux lettres Telechargements).", "📬", g, args='"{PROJET}\\facteur1.py"', cwd="{PROJET}")
    g = "Scripts"
    add(c, "backup", "backup.bat (E: et D:)", "script", r"C:\web\backup.bat", "Ton backup quotidien : copie C:\\web, "
        "les sketches Arduino et le Bureau vers la clé USB (E:) et D:. Console ouverte pour suivre la progression.",
        "💾", g, cwd=r"C:\web", console="keep", tags=["sauvegarde", "usb"])
    add(c, "backup_dry", "backup.bat — test (/dry)", "script", r"C:\web\backup.bat", "Simulation du backup sans rien "
        "copier (option /dry) : vérifie les disques et ce qui serait fait.", "🧪", g, args="/dry", cwd=r"C:\web",
        console="keep", tags=["sauvegarde"])
    add(c, "setup", "Setup Padawan (installation)", "script", "{PROJET}\\setup_padawan.bat", "Réinstalle / met à jour "
        "le kit : modules Python, ffmpeg, Ollama, PATH, raccourcis Bureau, démarrage auto.", "🛠", g,
        cwd="{PROJET}", console="keep", confirm=True)
    add(c, "maj_modules", "Mettre à jour les modules Padawan", "cmd",
        '"{PYTHON}" -m pip install --upgrade -r "{PROJET}\\requirements-padawan.txt"',
        "pip install --upgrade de tous les modules du kit (Pillow, pystray, yt-dlp...).", "⬆", g, console="keep")
    g = "Dossiers"
    add(c, "dir_projet", "Dossier Projet Padawan", "folder", "{PROJET}", "Les programmes Padawan, Archiveur, "
        "Gestionnaire et Arsenal (et arsenal.json).", "📂", g)
    add(c, "dir_web", "C:\\web", "folder", r"C:\web", "Racine du serveur web marcsevigny.ca (sauvegardée par backup.bat).", "🗂", g)
    add(c, "dir_archiveur", "ARCHIVEUR (archives)", "folder", r"C:\web\FTP_HOME\ARCHIVEUR", "Toutes les archives de "
        "l'Archiveur (vidéos, posts, pages).", "🗃", g)
    add(c, "dir_python", "SECTION PYTHON", "folder", r"C:\web\FTP_HOME\SECTION PYTHON", "Les projets Python publiés.", "🐍", g)
    add(c, "dir_arduino", "Sketches Arduino", "folder", r"%USERPROFILE%\OneDrive\Documents\Arduino",
        "Tes sketches Arduino (OneDrive\\Documents\\Arduino).", "🔌", g)
    add(c, "dir_bureau", "Bureau (OneDrive)", "folder", r"%USERPROFILE%\OneDrive\Desktop", "Ton Bureau.", "🖥", g)
    add(c, "dir_downloads", "Téléchargements", "shell", "shell:downloads", "Le dossier Téléchargements.", "⬇", g)
    g = "Serveur web"
    add(c, "site", "marcsevigny.ca", "url", "https://marcsevigny.ca/", "Ton site.", "🏠", g)
    add(c, "favoris_php", "Favoris.php", "url", "https://marcsevigny.ca/Favoris.php", "Ta bibliothèque de liens en ligne.", "⭐", g)
    add(c, "localhost", "localhost (serveur local)", "url", "http://localhost/", "Le serveur Apache local (XAMPP).", "🧪", g)
    add(c, "phpmyadmin", "phpMyAdmin", "url", "http://localhost/phpmyadmin/", "Base de données MySQL locale (XAMPP).", "🐬", g)
    add(c, "xampp", "XAMPP Control Panel", "file", r"C:\xampp\xampp-control.exe", "Démarrer/arrêter Apache et MySQL.",
        "🎛", g, requires=r"C:\xampp\xampp-control.exe")
    add(c, "apache_log", "Journal d'erreurs Apache", "file", r"C:\xampp\apache\logs\error.log", "error.log d'Apache "
        "(erreurs PHP, 404...).", "📜", g, requires=r"C:\xampp\apache\logs\error.log")
    g = "Arsenal"
    add(c, "monip", "Mon IP", "builtin", "myip", "Affiche ton IP publique et tes IP locales, copiables en un clic.", "🌍", g)
    add(c, "arsenal_json", "arsenal.json (données)", "file", "{ARSENAL}\\arsenal.json", "Le fichier de données "
        "d'Arsenal (lisible). Sauvegardes auto dans _sauvegardes_arsenal.", "🗄", g)
    add(c, "arsenal_log", "Journal Arsenal", "file", "{ARSENAL}\\arsenal.log", "Tout ce qui a été lancé et les erreurs.", "📒", g)

    # ============================================================ Mes favoris web (import Favoris.php)
    c = "favoris_web"
    favs = [
        ("FAVORIS", "UPLOADER AU SERVEUR A MARC", "https://www.marcsevigny.org/uploader3.php", "📡"),
        ("FAVORIS", "X (Twitter)", "https://x.com/home", "🐦"),
        ("FAVORIS", "SiteGround (connexion)", "https://login.siteground.com/?lang=fr", "🔖"),
        ("FAVORIS", "ChatGPT", "https://chatgpt.com/", "🤖"),
        ("FAVORIS", "Hackaday", "https://hackaday.com/", "🔖"),
        ("FAVORIS", "C64", "https://www.c64.com/", "🔖"),
        ("FAVORIS", "Msdos", "https://www.msdos.com/", "🔖"),
        ("FAVORIS", "Archive — Softwarelibrary Msdos Games", "https://archive.org/details/softwarelibrary_msdos_games", "🔖"),
        ("FAVORIS", "Archive — Lemmings (MS-DOS)", "https://archive.org/details/lemmings_original_ms-dos_201705", "🔖"),
        ("FAVORIS", "Crazygames — Rocketgoal IO", "https://www.crazygames.com/game/rocketgoal-io", "🔖"),
        ("FAVORIS", "Bbs.mythicalkingdom", "https://bbs.mythicalkingdom.com/files/2/bbsbbsdoors/index.html", "🧩"),
        ("FAVORIS", "Fnd.foundation — Entry 2", "https://fnd.foundation.game/pc/entry-2", "🔖"),
        ("FAVORIS", "Hacker News", "https://news.ycombinator.com/", "🔖"),
        ("OUTILS INTERNET", "Moltbook", "https://www.moltbook.com/", "🔖"),
        ("OUTILS INTERNET", "Threejs — Examples", "https://threejs.org/examples/#webgl_animation_keyframes", "🔖"),
        ("OUTILS INTERNET", "Dafont", "https://www.dafont.com/", "🔖"),
        ("OUTILS INTERNET", "Patorjk — Taag (texte ASCII)", "https://patorjk.com/software/taag/#p=display&f=Graffiti&t=Type+Something+&x=none&v=4&h=4&w", "🔖"),
        ("OUTILS INTERNET", "Kenney — New Platformer Pack", "https://www.kenney.nl/assets/new-platformer-pack", "🔖"),
        ("OUTILS INTERNET", "Falstad — Mathphysics", "https://www.falstad.com/mathphysics.html", "🧩"),
        ("OUTILS INTERNET", "Bellard — Jslinux", "https://bellard.org/jslinux/", "🔖"),
        ("OUTILS INTERNET", "Spriters Resource — Arcade", "https://www.spriters-resource.com/arcade/", "🔖"),
        ("OUTILS INTERNET", "Shaderfrog", "https://shaderfrog.com/", "🔖"),
        ("OUTILS INTERNET", "Orillusion — AddRemove", "https://www.orillusion.com/en/example/base/AddRemove.html", "🧩"),
        ("Sans groupe", "Tubitv", "https://tubitv.com/", "🔖"),
        ("Sans groupe", "Web.archive — Marcsevigny Org", "https://web.archive.org/web/20250201000000*/marcsevigny.org", "🔖"),
        ("Sans groupe", "Rumble", "https://rumble.com/", "🔖"),
        ("Sans groupe", "Odysee", "https://odysee.com/", "🔖"),
        ("Sans groupe", "Worldmonitor", "https://worldmonitor.app/?lat=20.0000&lon=-1.9887&zoom=1.00&view=global&timeRange=7d", "🔖"),
        ("Sans groupe", "Playground.babylonjs", "https://playground.babylonjs.com/", "🔖"),
        ("Sans groupe", "Itch", "https://itch.io/", "🔖"),
        ("Sans groupe", "Archive.org", "https://archive.org/", "🔖"),
        ("Sans groupe", "Asciiart — Ascii Spinning Shapes", "https://www.asciiart.eu/animations/ascii-spinning-shapes", "🔖"),
        ("Sans groupe", "Lexaloffle — Pico 8", "https://www.lexaloffle.com/pico-8.php", "🧩"),
        ("Sans groupe", "Jsnes", "https://jsnes.org/", "🔖"),
        ("Sans groupe", "WebGL Fluid Simulation", "https://paveldogreat.github.io/WebGL-Fluid-Simulation/", "🔖"),
    ]
    for i, (gr, t, u, ic) in enumerate(favs):
        add(c, f"fav{i:02d}", t, "url", u, "Importé de Favoris.php (" + gr + ").", ic, gr, tags=["favoris.php"])

    # ============================================================ Web pratique (URLs verifiees le 2026-10-06)
    c = "web"

    def W(gr, sid, name, url, desc, icon="🌐"):
        add(c, sid, name, "url", url, desc, icon, gr, tags=["web"])
    gr = "Padawan Suite (ressources)"
    W(gr, "padawan_github", "Padawan Suite sur GitHub", "https://github.com/marcsevigny1971/padawan-suite", "La page du projet : le code, le guide et les nouveautés.", "🏠")
    W(gr, "padawan_releases", "Padawan — mises à jour", "https://github.com/marcsevigny1971/padawan-suite/releases/latest", "La dernière version de l'installateur (réinstaller par-dessus garde tes données).", "⬆")
    W(gr, "padawan_issues", "Padawan — idées et suggestions", "https://github.com/marcsevigny1971/padawan-suite/issues", "Une idée, une question, un petit souci ? Écris-le ici.", "💡")
    W(gr, "padawan_presentation", "Padawan — présentation complète", "https://marcsevigny1971.github.io/padawan-suite/", "Tous les outils de la suite, en détail.", "✨")
    gr = "Sécurité & vérification"
    W(gr, "virustotal", "VirusTotal", "https://www.virustotal.com/gui/home/upload", "Analyse un fichier, un lien ou une empreinte avec 70 antivirus.", "🦠")
    W(gr, "hibp", "Have I Been Pwned", "https://haveibeenpwned.com/", "Ton courriel a-t-il fuité dans un piratage ?", "🔓")
    W(gr, "urlscan", "urlscan.io", "https://urlscan.io/", "Ouvre un lien douteux à ta place et montre ce qu'il contient.", "🔎")
    W(gr, "safebrowsing", "Google Safe Browsing", "https://transparencyreport.google.com/safe-browsing/search?hl=fr", "Un site est-il signalé dangereux ?", "🚦")
    W(gr, "hybrid", "Hybrid Analysis", "https://www.hybrid-analysis.com/", "Analyse de fichiers suspects en bac à sable (gratuit).", "🧫")
    W(gr, "bitwarden_gen", "Générateur de mots de passe", "https://bitwarden.com/password-generator/", "Mots de passe et phrases de passe solides.", "🔑")
    W(gr, "cyber_gc", "Centre canadien pour la cybersécurité", "https://www.cyber.gc.ca/fr", "Alertes et conseils officiels.", "🍁")
    W(gr, "pensez_cyber", "Pensez cybersécurité", "https://www.pensezcybersecurite.gc.ca/fr", "Guides simples (arnaques, mots de passe).", "🧠")
    W(gr, "shodan", "Shodan", "https://www.shodan.io/", "Ce qui est visible de ton IP sur Internet.", "🛰")
    W(gr, "whois", "Whois", "https://www.whois.com/whois/", "Propriétaire et dates d'un nom de domaine.", "📇")
    W(gr, "torcheck", "Tor check", "https://check.torproject.org/", "Vérifie si tu passes par Tor.", "🧅")
    gr = "Réseau & diagnostic"
    W(gr, "whatismyip", "WhatIsMyIP", "https://www.whatismyip.com/", "Ton adresse IP publique et ta localisation.", "🌍")
    W(gr, "ipinfo", "ipinfo.io", "https://ipinfo.io/", "IP publique, fournisseur, ville (version technique).", "📍")
    W(gr, "speedtest", "Speedtest", "https://www.speedtest.net/fr", "Test de vitesse Internet (Ookla).", "🚀")
    W(gr, "fast", "Fast.com", "https://fast.com/fr/", "Test de vitesse instantané (Netflix).", "⚡")
    W(gr, "downdetector", "Downdetector", "https://downdetector.ca/fr/", "Panne chez Bell, Vidéotron, Facebook... ?", "📉")
    W(gr, "isitdown", "Is It Down Right Now", "https://www.isitdownrightnow.com/", "Un site est-il en panne pour tout le monde ?", "❓")
    W(gr, "dnschecker", "DNS Checker", "https://dnschecker.org/", "Propagation DNS dans le monde.", "🗺")
    W(gr, "whatsmydns", "WhatsMyDNS", "https://www.whatsmydns.net/", "Propagation DNS (autre outil).", "🗺")
    W(gr, "mxtoolbox", "MXToolbox", "https://mxtoolbox.com/", "Courriel, DNS, listes noires, en-têtes.", "📬")
    W(gr, "ssllabs", "SSL Labs", "https://www.ssllabs.com/ssltest/", "Note du certificat HTTPS d'un site.", "🔐")
    W(gr, "pagespeed", "PageSpeed Insights", "https://pagespeed.web.dev/", "Vitesse et qualité d'une page web.", "🏎")
    W(gr, "browserleaks", "BrowserLeaks", "https://browserleaks.com/ip", "Ce que ton navigateur révèle (IP, WebRTC...).", "🕵")
    W(gr, "pingpe", "ping.pe", "https://ping.pe/", "Ping et traceroute depuis plusieurs pays.", "📶")
    W(gr, "cloudflare1111", "1.1.1.1 (DNS Cloudflare)", "https://one.one.one.one/fr-FR/", "DNS rapide et privé : réglages.", "🌐")
    gr = "Archives du web"
    W(gr, "wayback", "Wayback Machine", "https://web.archive.org/", "Anciennes versions de n'importe quel site.", "⏳")
    W(gr, "archivetoday", "archive.today", "https://archive.ph/", "Instantané permanent d'une page.", "📸")
    W(gr, "archiveorg", "Internet Archive", "https://archive.org/", "Livres, logiciels, films, musique libres.", "🏛")
    gr = "Commandes Windows & PowerShell"
    W(gr, "ss64nt", "SS64 — commandes CMD", "https://ss64.com/nt/", "Toutes les commandes CMD avec exemples.", "⌨")
    W(gr, "ss64ps", "SS64 — PowerShell", "https://ss64.com/ps/", "Toutes les commandes PowerShell.", "🔷")
    W(gr, "mslearn_ps", "Microsoft Learn — PowerShell", "https://learn.microsoft.com/fr-fr/powershell/", "Documentation officielle PowerShell.", "📘")
    W(gr, "mslearn_cmd", "Microsoft Learn — commandes Windows", "https://learn.microsoft.com/fr-fr/windows-server/administration/windows-commands/windows-commands", "Référence A à Z des commandes.", "📗")
    W(gr, "sysinternals", "Sysinternals", "https://learn.microsoft.com/fr-fr/sysinternals/", "Outils gratuits Microsoft (Autoruns, Process Explorer...).", "🔬")
    W(gr, "sysinternals_live", "Sysinternals Live", "https://live.sysinternals.com/", "Lancer les outils Sysinternals sans installer.", "🔬")
    W(gr, "ms_catalog", "Catalogue Microsoft Update", "https://www.catalog.update.microsoft.com/Home.aspx", "Télécharger une mise à jour Windows précise (KB).", "🧾")
    W(gr, "ms_support", "Support Windows", "https://support.microsoft.com/fr-fr/windows/", "Aide officielle Windows.", "🆘")
    W(gr, "elevenforum", "ElevenForum (tutoriels)", "https://www.elevenforum.com/", "Tutoriels Windows 11 très complets.", "💬")
    W(gr, "bleeping", "BleepingComputer", "https://www.bleepingcomputer.com/", "Actualités sécurité et guides de désinfection.", "📰")
    gr = "Logiciels gratuits"
    W(gr, "ninite", "Ninite", "https://ninite.com/", "Installe plusieurs logiciels gratuits d'un coup, sans pub.", "📦")
    W(gr, "wingetrun", "winget.run", "https://winget.run/", "Chercher un paquet winget (commande prête).", "📦")
    W(gr, "winstall", "winstall", "https://winstall.app/", "Créer un script winget d'installation.", "📦")
    W(gr, "powertoys", "PowerToys", "https://github.com/microsoft/PowerToys", "Outils Microsoft : FancyZones, PowerRename, sélecteur de couleur...", "🧸")
    W(gr, "sevenzip", "7-Zip", "https://www.7-zip.org/", "Compression gratuite (zip, 7z, rar).", "🗜")
    W(gr, "vlc", "VLC", "https://www.videolan.org/vlc/index.fr.html", "Lit tous les formats vidéo/audio.", "🎦")
    W(gr, "npp", "Notepad++", "https://notepad-plus-plus.org/", "Éditeur de texte/code léger.", "📝")
    W(gr, "everything", "Everything (voidtools)", "https://www.voidtools.com/", "Recherche de fichiers instantanée.", "🔍")
    W(gr, "wiztree", "WizTree", "https://wiztree.com/", "Ce qui remplit ton disque, en secondes.", "🌳")
    W(gr, "rufus", "Rufus", "https://rufus.ie/fr/", "Créer une clé USB amorçable Windows/Linux.", "💿")
    W(gr, "ventoy", "Ventoy", "https://www.ventoy.net/", "Une clé USB, plusieurs ISO amorçables.", "💿")
    W(gr, "win11iso", "Windows 11 — ISO officiel", "https://www.microsoft.com/fr-ca/software-download/windows11", "Télécharger Windows 11 (outil Microsoft).", "🪟")
    W(gr, "hwinfo", "HWiNFO", "https://www.hwinfo.com/", "Températures, capteurs et infos matériel.", "🌡")
    W(gr, "cpuz", "CPU-Z", "https://www.cpuid.com/softwares/cpu-z.html", "Processeur, RAM, carte mère.", "🧮")
    W(gr, "crystaldisk", "CrystalDiskInfo", "https://crystalmark.info/en/software/crystaldiskinfo/", "Santé SMART des disques.", "💽")
    W(gr, "memtest", "MemTest86", "https://www.memtest86.com/", "Tester la mémoire vive (clé USB).", "🧠")
    W(gr, "nirsoft", "NirSoft", "https://www.nirsoft.net/", "Des centaines de petits utilitaires gratuits.", "🧰")
    W(gr, "malwarebytes", "Malwarebytes (gratuit)", "https://www.malwarebytes.com/fr/", "Second avis anti-malware (version gratuite).", "🛡")
    W(gr, "alternativeto", "AlternativeTo", "https://alternativeto.net/", "Trouver une alternative gratuite à un logiciel.", "🔁")
    W(gr, "obs", "OBS Studio", "https://obsproject.com/fr", "Enregistrer / diffuser l'écran.", "🎥")
    W(gr, "audacity", "Audacity", "https://www.audacityteam.org/", "Montage audio.", "🎙")
    W(gr, "gimp", "GIMP", "https://www.gimp.org/", "Retouche photo.", "🖌")
    W(gr, "libreoffice", "LibreOffice", "https://www.libreoffice.org/", "Suite bureautique gratuite.", "📄")
    W(gr, "handbrake", "HandBrake", "https://handbrake.fr/", "Convertir/compresser des vidéos.", "🎞")
    W(gr, "keepass", "KeePass", "https://keepass.info/", "Coffre de mots de passe local.", "🔐")
    gr = "Développement"
    W(gr, "github", "GitHub", "https://github.com/", "Code source et projets.", "🐙")
    W(gr, "python_docs", "Documentation Python (FR)", "https://docs.python.org/fr/3/", "Référence officielle Python.", "🐍")
    W(gr, "pypi", "PyPI", "https://pypi.org/", "Les modules pip.", "📦")
    W(gr, "regex101", "regex101", "https://regex101.com/", "Tester et comprendre une expression régulière.", "🔣")
    W(gr, "caniuse", "Can I Use", "https://caniuse.com/", "Compatibilité HTML/CSS/JS des navigateurs.", "✅")
    W(gr, "mdn", "MDN Web Docs", "https://developer.mozilla.org/fr/", "Référence HTML, CSS, JavaScript.", "📚")
    W(gr, "php_manual", "Manuel PHP (FR)", "https://www.php.net/manual/fr/", "Référence PHP.", "🐘")
    W(gr, "devdocs", "DevDocs", "https://devdocs.io/", "Toutes les docs de dev au même endroit.", "📖")
    W(gr, "git_doc", "Documentation Git", "https://git-scm.com/doc", "Git : livre Pro Git et référence.", "🌿")
    W(gr, "jsonformatter", "JSON Formatter", "https://jsonformatter.org/", "Formater/valider du JSON.", "🧾")
    W(gr, "diffchecker", "Diffchecker", "https://www.diffchecker.com/", "Comparer deux textes.", "↔")
    W(gr, "codepen", "CodePen", "https://codepen.io/", "Bac à sable HTML/CSS/JS.", "✏")
    W(gr, "base64", "Base64 decode", "https://www.base64decode.org/", "Encoder/décoder Base64.", "🔤")
    W(gr, "diagrams", "draw.io (diagrams.net)", "https://app.diagrams.net/", "Schémas et organigrammes.", "📐")
    W(gr, "excalidraw", "Excalidraw", "https://excalidraw.com/", "Croquis style main levée.", "✍")
    gr = "Arduino & électronique"
    W(gr, "arduino_docs", "Arduino Docs", "https://docs.arduino.cc/", "Documentation officielle Arduino.", "🔌")
    W(gr, "arduino_ref", "Arduino — référence du langage", "https://docs.arduino.cc/language-reference/", "Toutes les fonctions Arduino.", "📘")
    W(gr, "esp8266", "ESP8266 Arduino core", "https://arduino-esp8266.readthedocs.io/en/latest/", "Docs ESP8266 (NodeMCU, Wemos) sous Arduino.", "📶")
    W(gr, "nodemcu", "NodeMCU docs", "https://nodemcu.readthedocs.io/en/release/", "Firmware NodeMCU (Lua).", "📶")
    W(gr, "rnt", "Random Nerd Tutorials", "https://randomnerdtutorials.com/", "Tutoriels ESP32/ESP8266/Arduino.", "🤓")
    W(gr, "wokwi", "Wokwi", "https://wokwi.com/", "Simulateur Arduino/ESP32 en ligne.", "🧪")
    W(gr, "falstad", "Falstad Circuit", "https://www.falstad.com/circuit/", "Simulateur de circuits électroniques.", "⚡")
    W(gr, "tinkercad", "Tinkercad", "https://www.tinkercad.com/", "3D et circuits Arduino simulés.", "🧊")
    W(gr, "easyeda", "EasyEDA", "https://easyeda.com/", "Schémas et circuits imprimés.", "🟩")
    W(gr, "alldatasheet", "AllDatasheet", "https://www.alldatasheet.com/", "Fiches techniques de composants.", "📑")
    W(gr, "digikey", "Digi-Key Canada", "https://www.digikey.ca/fr", "Composants électroniques.", "🛒")
    W(gr, "thingiverse", "Thingiverse", "https://www.thingiverse.com/", "Modèles 3D à imprimer.", "🖨")
    gr = "IA & médias"
    W(gr, "ollama_lib", "Ollama — bibliothèque", "https://ollama.com/library", "Modèles à installer avec ollama pull.", "🦙")
    W(gr, "huggingface", "Hugging Face", "https://huggingface.co/", "Modèles et démos d'IA.", "🤗")
    W(gr, "grok", "Grok", "https://grok.com/", "Assistant IA.", "✨")
    W(gr, "ytdlp_gh", "yt-dlp (GitHub)", "https://github.com/yt-dlp/yt-dlp", "Le moteur de téléchargement de l'Archiveur.", "📥")
    W(gr, "ytdlp_sites", "yt-dlp — sites supportés", "https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md", "Liste des sites compatibles.", "📃")
    W(gr, "ffmpeg_docs", "Documentation ffmpeg", "https://ffmpeg.org/documentation.html", "Toutes les options ffmpeg.", "🎬")
    W(gr, "ffmpeg_builds", "ffmpeg pour Windows (gyan.dev)", "https://www.gyan.dev/ffmpeg/builds/", "Versions Windows de ffmpeg.", "🎬")
    W(gr, "cobalt", "cobalt", "https://cobalt.tools/", "Télécharger une vidéo/un son sans pub.", "🐟")
    W(gr, "vocalremover", "Vocal Remover", "https://vocalremover.org/fr/", "Séparer voix et musique.", "🎤")
    W(gr, "freesound", "Freesound", "https://freesound.org/", "Sons libres.", "🔊")
    W(gr, "emojipedia", "Emojipedia", "https://emojipedia.org/", "Trouver et copier un emoji.", "😀")
    W(gr, "symbl", "Table Unicode (symbl.cc)", "https://symbl.cc/fr/", "Tous les caractères spéciaux.", "Ω")
    gr = "Images, PDF & conversion"
    W(gr, "photopea", "Photopea", "https://www.photopea.com/", "Photoshop gratuit dans le navigateur (PSD).", "🖼")
    W(gr, "removebg", "remove.bg", "https://www.remove.bg/fr", "Enlever l'arrière-plan d'une photo.", "✂")
    W(gr, "tinypng", "TinyPNG", "https://tinypng.com/", "Compresser PNG/JPG/WebP.", "🐼")
    W(gr, "squoosh", "Squoosh", "https://squoosh.app/", "Compresser/convertir une image (local).", "🍊")
    W(gr, "ezgif", "ezgif", "https://ezgif.com/", "Créer/éditer des GIF animés.", "🎞")
    W(gr, "cloudconvert", "CloudConvert", "https://cloudconvert.com/", "Convertir presque tout (vidéo, doc, image).", "🔄")
    W(gr, "convertio", "Convertio", "https://convertio.co/fr/", "Conversion de fichiers.", "🔄")
    W(gr, "ilovepdf", "iLovePDF", "https://www.ilovepdf.com/fr", "Fusionner, couper, compresser des PDF.", "📕")
    W(gr, "smallpdf", "Smallpdf", "https://smallpdf.com/fr", "Outils PDF.", "📕")
    W(gr, "pdf24", "PDF24 Tools", "https://tools.pdf24.org/fr/", "Outils PDF gratuits, sans limite.", "📕")
    W(gr, "iloveimg", "iLoveIMG", "https://www.iloveimg.com/fr", "Redimensionner, recadrer, convertir des images.", "🖼")
    W(gr, "onlineocr", "OnlineOCR", "https://www.onlineocr.net/fr/", "Texte d'une image/PDF scanné.", "🔠")
    W(gr, "favicon", "RealFaviconGenerator", "https://realfavicongenerator.net/", "Favicons pour ton site.", "⭐")
    W(gr, "coolors", "Coolors", "https://coolors.co/", "Palettes de couleurs.", "🎨")
    W(gr, "googlefonts", "Google Fonts", "https://fonts.google.com/", "Polices libres.", "🔤")
    W(gr, "pixabay", "Pixabay", "https://pixabay.com/fr/", "Images et vidéos libres.", "📷")
    W(gr, "fontawesome", "Font Awesome (icônes)", "https://fontawesome.com/icons", "Icônes pour le web.", "🏳")
    gr = "Traduction & français"
    W(gr, "deepl", "DeepL", "https://www.deepl.com/fr/translator", "Le meilleur traducteur automatique.", "🈳")
    W(gr, "gtrad", "Google Traduction", "https://translate.google.com/?sl=auto&tl=fr", "Traduction vers le français.", "🈯")
    W(gr, "bonpatron", "BonPatron", "https://bonpatron.com/", "Correcteur de français gratuit.", "✔")
    W(gr, "larousse", "Larousse (dictionnaire)", "https://www.larousse.fr/dictionnaires/francais", "Définitions et conjugaison.", "📕")
    W(gr, "oqlf", "Vitrine linguistique (OQLF)", "https://vitrinelinguistique.oqlf.gouv.qc.ca/", "Grand dictionnaire terminologique, Banque de dépannage.", "⚜")
    W(gr, "wordref", "WordReference", "https://www.wordreference.com/fren/", "Dictionnaire français-anglais.", "📗")
    gr = "Météo & cartes"
    W(gr, "meteomedia", "MétéoMédia — Sherbrooke", "https://www.meteomedia.com/fr/ville/ca/quebec/sherbrooke/actuelle", "Météo actuelle et horaire à Sherbrooke.", "⛅")
    W(gr, "meteomedia14", "MétéoMédia — 14 jours", "https://www.meteomedia.com/fr/ville/ca/quebec/sherbrooke/14-jours", "Tendance 14 jours, Sherbrooke.", "📅")
    W(gr, "envcan", "Environnement Canada — Sherbrooke", "https://meteo.gc.ca/fr/location/index.html?coords=45.403,-71.901", "Prévisions officielles 7 jours.", "🍁")
    W(gr, "envcan_h", "Environnement Canada — horaire", "https://meteo.gc.ca/fr/forecast/hourly/index.html?coords=45.403,-71.901", "Prévision heure par heure.", "🕐")
    W(gr, "envcan_alertes", "Alertes météo — Sherbrooke", "https://meteo.gc.ca/warnings/report_f.html?qcrm55=", "Avertissements en vigueur.", "⚠")
    W(gr, "windy", "Windy", "https://www.windy.com/", "Cartes animées vent, pluie, radar.", "🌬")
    W(gr, "ventusky", "Ventusky", "https://www.ventusky.com/", "Météo animée mondiale.", "🌀")
    W(gr, "lightning", "LightningMaps (éclairs)", "https://www.lightningmaps.org/", "Orages et éclairs en direct.", "🌩")
    W(gr, "gmaps", "Google Maps", "https://www.google.com/maps", "Cartes et itinéraires.", "🗺")
    W(gr, "osm", "OpenStreetMap", "https://www.openstreetmap.org/", "Carte libre.", "🗺")
    W(gr, "gearth", "Google Earth", "https://earth.google.com/web/", "La Terre en 3D.", "🌎")
    W(gr, "flightradar", "Flightradar24", "https://www.flightradar24.com/", "Avions en vol en direct.", "✈")
    gr = "Québec & services"
    W(gr, "hq_pannes", "Hydro-Québec — Info-pannes", "https://infopannes.solutions.hydroquebec.com/", "Carte des pannes d'électricité en direct.", "🔌")
    W(gr, "hq", "Hydro-Québec", "https://www.hydroquebec.com/", "Ton espace client Hydro-Québec.", "⚡")
    W(gr, "q511", "Québec 511", "https://www.quebec511.info/fr/", "État des routes, travaux, caméras.", "🚗")
    W(gr, "quebecca", "Québec.ca", "https://www.quebec.ca/", "Portail du gouvernement du Québec.", "⚜")
    W(gr, "revenuqc", "Revenu Québec", "https://www.revenuquebec.ca/fr/", "Impôts du Québec, Mon dossier.", "🧾")
    W(gr, "clicsante", "Clic Santé", "https://portal3.clicsante.ca/", "Rendez-vous santé (vaccins, prises de sang).", "💉")
    W(gr, "cnesst", "CNESST", "https://www.cnesst.gouv.qc.ca/fr", "Normes du travail, santé-sécurité.", "👷")
    W(gr, "sherbrooke", "Ville de Sherbrooke", "https://www.sherbrooke.ca/fr", "Services municipaux, collectes.", "🏙")
    W(gr, "postes", "Postes Canada — suivi", "https://www.canadapost-postescanada.ca/track-reperage/fr", "Suivre un colis.", "📮")
    W(gr, "donneesqc", "Données Québec", "https://www.donneesquebec.ca/", "Données ouvertes du Québec.", "📊")
    gr = "Utiles du quotidien"
    W(gr, "wolfram", "WolframAlpha", "https://www.wolframalpha.com/", "Calculs, conversions, maths, faits.", "🧮")
    W(gr, "desmos", "Desmos (calculatrice)", "https://www.desmos.com/calculator?lang=fr", "Calculatrice graphique.", "📈")
    W(gr, "timeanddate", "Heure dans le monde", "https://www.timeanddate.com/worldclock/", "Fuseaux horaires et horloges.", "🕰")
    W(gr, "wetransfer", "WeTransfer", "https://wetransfer.com/", "Envoyer de gros fichiers.", "📤")
    W(gr, "swisstransfer", "SwissTransfer", "https://www.swisstransfer.com/fr", "Gros fichiers jusqu'à 50 Go, gratuit.", "📤")
    W(gr, "tempmail", "Temp Mail", "https://temp-mail.org/fr/", "Courriel jetable contre le spam.", "📧")
    W(gr, "privnote", "Privnote", "https://privnote.com/", "Note qui s'autodétruit après lecture.", "🔥")
    W(gr, "ifixit", "iFixit", "https://fr.ifixit.com/", "Guides de réparation.", "🔧")
    W(gr, "wikipedia", "Wikipédia", "https://fr.wikipedia.org/", "L'encyclopédie.", "📚")
    W(gr, "ddg", "DuckDuckGo", "https://duckduckgo.com/", "Recherche sans pistage.", "🦆")
    W(gr, "testufo", "TestUFO (écran)", "https://testufo.com/", "Tester fluidité et taux de rafraîchissement.", "🛸")
    W(gr, "keyboardtester", "Testeur de clavier", "https://www.keyboardtester.com/", "Vérifier chaque touche.", "⌨")
    W(gr, "mictest", "Test de micro", "https://www.onlinemictest.com/fr/", "Ton micro fonctionne-t-il ?", "🎙")
    W(gr, "webcamtest", "Test de webcam", "https://webcamtests.com/", "Ta webcam fonctionne-t-elle ?", "📷")
    W(gr, "pcpartpicker", "PCPartPicker Canada", "https://ca.pcpartpicker.com/", "Monter un PC, prix et compatibilité.", "🖥")
    W(gr, "protondb", "ProtonDB", "https://www.protondb.com/", "Jeux Windows sous Linux.", "🎮")

    # ============================================================ Sécurité
    c = "securite"
    g = "Antivirus Defender"
    add(c, "def_update", "Defender — mettre à jour les signatures", "cmd", '"{MPCMDRUN}" -SignatureUpdate',
        "Télécharge les dernières définitions de virus de Microsoft Defender (MpCmdRun).", "🔄", g, admin=True, console="keep")
    add(c, "def_quick", "Defender — scan rapide", "cmd", '"{MPCMDRUN}" -Scan -ScanType 1',
        "Analyse rapide (zones à risque, mémoire, démarrage) : quelques minutes.", "⚡", g, admin=True, console="keep")
    add(c, "def_full", "Defender — scan complet", "cmd", '"{MPCMDRUN}" -Scan -ScanType 2',
        "Analyse de tous les disques : peut durer plus d'une heure.", "🔍", g, admin=True, console="keep", confirm=True)
    add(c, "def_folder", "Defender — scanner un dossier", "cmd", '"{MPCMDRUN}" -Scan -ScanType 3 -File "{DOSSIER}"',
        "Analyse un dossier ou une clé USB précise (le chemin est demandé).", "📁", g, admin=True, console="keep",
        ask=[A("DOSSIER", "Dossier ou lecteur à analyser", "folder", "E:\\")])
    add(c, "def_offline", "Defender — scan hors ligne (redémarre)", "ps", "Start-MpWDOScan",
        "Redémarre le PC dans Microsoft Defender hors ligne pour déloger les virus tenaces (environ 15 min). "
        "Enregistre ton travail avant !", "🔁", g, admin=True, console="keep", danger=True)
    add(c, "def_status", "Defender — état", "ps",
        "Get-MpComputerStatus | Format-List AMServiceEnabled,AntivirusEnabled,RealTimeProtectionEnabled,"
        "IoavProtectionEnabled,BehaviorMonitorEnabled,AntivirusSignatureVersion,AntivirusSignatureLastUpdated,"
        "QuickScanEndTime,FullScanEndTime,AMProductVersion",
        "Protection en temps réel active ? Signatures à jour ? Date des derniers scans.", "📊", g)
    add(c, "def_threats", "Defender — historique des menaces", "ps",
        "$d = Get-MpThreatDetection | Sort-Object InitialDetectionTime -Descending\n"
        "if (-not $d) { 'Aucune menace détectée dans l''historique.' } else {\n"
        "  $t = @{}; Get-MpThreat | ForEach-Object { $t[$_.ThreatID] = $_.ThreatName }\n"
        "  $d | Select-Object InitialDetectionTime,@{n='Menace';e={$t[$_.ThreatID]}},ActionSuccess,"
        "@{n='Fichiers';e={$_.Resources -join ' | '}} | Format-List }",
        "Ce que Defender a trouvé et ce qu'il en a fait (Get-MpThreatDetection).", "🦠", g, admin=True)
    add(c, "def_prefs", "Defender — exclusions", "ps",
        "$p = Get-MpPreference\n'Dossiers exclus :'; $p.ExclusionPath\n''; 'Extensions exclues :'; $p.ExclusionExtension\n"
        "''; 'Processus exclus :'; $p.ExclusionProcess",
        "Liste des exclusions de l'antivirus (un virus aime s'y cacher).", "🚫", g, admin=True)
    add(c, "def_app", "Sécurité Windows", "shell", "windowsdefender:", "Ouvre l'application Sécurité Windows.", "🛡", g)
    add(c, "mrt", "MRT — outil de suppression de malwares", "file", "mrt.exe",
        "Outil Microsoft de suppression de logiciels malveillants (assistant, scan rapide ou complet).", "🧽", g,
        admin=True, requires=r"C:\Windows\System32\MRT.exe")
    g = "Pare-feu & ports"
    add(c, "fw_state", "Pare-feu — état", "cmd", "netsh advfirewall show allprofiles state",
        "Le pare-feu Windows est-il actif pour chaque profil (domaine, privé, public) ?", "🧱", g)
    add(c, "fw_wf", "Pare-feu — fonctions avancées", "file", "wf.msc", "Règles entrantes/sortantes détaillées.", "🧱", g)
    add(c, "fw_rules", "Pare-feu — règles entrantes actives", "ps",
        "Get-NetFirewallRule -Direction Inbound -Enabled True -Action Allow | Sort-Object DisplayName | "
        "Format-Table DisplayName,Profile -AutoSize",
        "Tout ce qui a le droit d'entrer sur ton PC.", "📥", g)
    add(c, "ports_listen", "Ports en écoute (avec programme)", "ps",
        "Get-NetTCPConnection -State Listen | Sort-Object LocalPort | Select-Object LocalAddress,LocalPort,OwningProcess,"
        "@{n='Programme';e={(Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue).ProcessName}} | Format-Table -AutoSize",
        "Quels programmes attendent des connexions (serveurs, ports ouverts).", "👂", g)
    g = "Vérifications"
    add(c, "vt_hash", "Vérifier un fichier sur VirusTotal", "ps",
        "$h = (Get-FileHash -Algorithm SHA256 -LiteralPath \"{FICHIER}\").Hash\n\"SHA256 : $h\"\n"
        "Start-Process \"https://www.virustotal.com/gui/file/$h\"",
        "Calcule l'empreinte SHA256 et ouvre le rapport VirusTotal (le fichier n'est pas envoyé).", "🧬", g,
        ask=[A("FICHIER", "Fichier à vérifier", "file")])
    add(c, "signature", "Signature numérique d'un fichier", "ps",
        "Get-AuthenticodeSignature -LiteralPath \"{FICHIER}\" | Format-List Status,StatusMessage,"
        "@{n='Signataire';e={$_.SignerCertificate.Subject}},@{n='Expire';e={$_.SignerCertificate.NotAfter}}",
        "Un .exe est-il signé par un éditeur légitime ?", "✍", g, ask=[A("FICHIER", "Fichier (.exe, .dll, .msi)", "file")])
    add(c, "tasks_nonms", "Tâches planifiées non Microsoft", "ps",
        "Get-ScheduledTask | Where-Object { $_.TaskPath -notlike '\\Microsoft\\*' } | Sort-Object TaskPath,TaskName | "
        "Format-Table TaskName,TaskPath,State -AutoSize",
        "Les tâches ajoutées par des logiciels (endroit favori des indésirables).", "⏰", g)
    add(c, "uac", "Réglages du contrôle de compte (UAC)", "file", "UserAccountControlSettings.exe",
        "Niveau des alertes « Voulez-vous autoriser... ».", "🛂", g)

    # ============================================================ Réparation
    c = "reparation"
    g = "Fichiers système"
    add(c, "sfc", "SFC — réparer les fichiers système", "cmd", "sfc /scannow",
        "Vérifie et répare les fichiers protégés de Windows (10-20 min). À lancer après DISM RestoreHealth.",
        "🩺", g, admin=True, console="keep", confirm=True)
    add(c, "sfc_verify", "SFC — vérifier seulement", "cmd", "sfc /verifyonly",
        "Vérifie l'intégrité sans rien réparer.", "🔎", g, admin=True, console="keep")
    add(c, "dism_check", "DISM — CheckHealth (rapide)", "cmd", "DISM /Online /Cleanup-Image /CheckHealth",
        "L'image de Windows est-elle marquée corrompue ? (quelques secondes)", "✅", g, admin=True, console="keep")
    add(c, "dism_scan", "DISM — ScanHealth", "cmd", "DISM /Online /Cleanup-Image /ScanHealth",
        "Analyse approfondie du magasin de composants (5-15 min).", "🔍", g, admin=True, console="keep")
    add(c, "dism_restore", "DISM — RestoreHealth (réparer)", "cmd", "DISM /Online /Cleanup-Image /RestoreHealth",
        "Répare l'image de Windows via Windows Update (10-30 min). Ensuite : sfc /scannow.", "🛠", g,
        admin=True, console="keep", confirm=True)
    add(c, "cbs_log", "Journal SFC (lignes [SR])", "ps",
        "Select-String -Path \"$env:windir\\Logs\\CBS\\CBS.log\" -Pattern '\\[SR\\]' | Select-Object -Last 60 | ForEach-Object { $_.Line }",
        "Les dernières lignes de SFC dans CBS.log : ce qui a été réparé ou non.", "📜", g, admin=True)
    g = "Disque"
    add(c, "chkdsk_ro", "CHKDSK — vérifier (lecture seule)", "cmd", "chkdsk {LETTRE}:",
        "Vérifie le système de fichiers sans rien modifier.", "💽", g, admin=True, console="keep",
        ask=[A("LETTRE", "Lettre du disque", "drive", "C")])
    add(c, "chkdsk_scan", "CHKDSK — analyse en ligne (/scan)", "cmd", "chkdsk {LETTRE}: /scan",
        "Analyse NTFS en ligne, sans démonter le disque.", "💽", g, admin=True, console="keep",
        ask=[A("LETTRE", "Lettre du disque", "drive", "C")])
    add(c, "chkdsk_f", "CHKDSK — réparer (/f)", "cmd", "chkdsk {LETTRE}: /f",
        "Corrige les erreurs du disque. Pour C: la réparation se fait au prochain redémarrage ; "
        "pour une clé USB, ferme tout ce qui l'utilise.", "🧰", g, admin=True, console="keep", danger=True,
        ask=[A("LETTRE", "Lettre du disque à réparer", "drive", "E")])
    g = "Windows Update"
    add(c, "wu_reset", "Réinitialiser Windows Update", "ps",
        "$s = 'wuauserv','bits','cryptsvc'\nStop-Service -Name $s -Force -ErrorAction SilentlyContinue\n"
        "$t = Get-Date -Format yyyyMMdd-HHmmss\n"
        "Rename-Item \"$env:SystemRoot\\SoftwareDistribution\" \"SoftwareDistribution.old-$t\" -ErrorAction Continue\n"
        "Rename-Item \"$env:SystemRoot\\System32\\catroot2\" \"catroot2.old-$t\" -ErrorAction Continue\n"
        "Start-Service -Name $s -ErrorAction Continue\n'Windows Update réinitialisé (anciens dossiers renommés .old).'",
        "Quand les mises à jour bloquent : arrête les services, renomme SoftwareDistribution et catroot2, relance.",
        "♻", g, admin=True, console="keep", danger=True)
    add(c, "wu_settings", "Windows Update", "shell", "ms-settings:windowsupdate", "Rechercher les mises à jour.", "⬆", g)
    add(c, "hotfix", "Mises à jour installées", "ps",
        "Get-HotFix | Sort-Object InstalledOn -Descending | Format-Table HotFixID,Description,InstalledOn -AutoSize",
        "La liste des KB installés, le plus récent en premier.", "🧾", g)
    g = "Restauration"
    add(c, "restore_point", "Créer un point de restauration", "ps",
        "Checkpoint-Computer -Description \"{NOM}\" -RestorePointType MODIFY_SETTINGS\n'Point de restauration demandé : {NOM}'\n"
        "Get-ComputerRestorePoint | Select-Object -Last 3 SequenceNumber,Description,"
        "@{n='Date';e={$_.ConvertToDateTime($_.CreationTime)}} | Format-Table -AutoSize",
        "Filet de sécurité avant une modification. Windows n'en crée qu'un par 24 h ; la protection du système doit être active sur C:.",
        "📍", g, admin=True, ask=[A("NOM", "Nom du point de restauration", "text", "Avant modification (Arsenal)")])
    add(c, "restore_list", "Points de restauration existants", "ps",
        "$r = Get-ComputerRestorePoint\nif (-not $r) { 'Aucun point de restauration (protection du système désactivée ?)' } else {\n"
        "$r | Select-Object SequenceNumber,@{n='Date';e={$_.ConvertToDateTime($_.CreationTime)}},Description | Format-Table -AutoSize }",
        "Liste des points disponibles.", "📋", g, admin=True)
    add(c, "rstrui", "Restauration du système", "file", "rstrui.exe", "Revenir à un point de restauration.", "⏪", g)
    add(c, "sysprot", "Protection du système", "file", "SystemPropertiesProtection.exe",
        "Activer la protection de C: et régler l'espace des points de restauration.", "🛡", g)
    g = "Dépannage"
    add(c, "troubleshoot", "Résolution des problèmes", "shell", "ms-settings:troubleshoot", "Utilitaires de dépannage Windows.", "🧩", g)
    add(c, "recovery", "Récupération (réinitialiser le PC)", "shell", "ms-settings:recovery",
        "Réinitialiser Windows, démarrage avancé.", "🚑", g)
    add(c, "winre", "Redémarrer en démarrage avancé", "cmd", "shutdown /r /o /t 0",
        "Redémarre immédiatement vers les options de récupération (mode sans échec, restauration...).", "🔁", g,
        danger=True, console="hidden")
    add(c, "bios", "Redémarrer dans le BIOS/UEFI", "cmd", "shutdown /r /fw /t 0",
        "Redémarre directement dans les réglages du micrologiciel (PC UEFI).", "🧬", g, admin=True, danger=True,
        console="hidden")
    add(c, "mdsched", "Diagnostic de la mémoire", "file", "mdsched.exe",
        "Teste la RAM au prochain redémarrage.", "🧠", g, confirm=True)
    add(c, "reliability", "Moniteur de fiabilité", "file", "perfmon.exe", "Historique des plantages et erreurs, jour par jour.",
        "📈", g, args="/rel")
    add(c, "wsreset", "Réparer le Microsoft Store (wsreset)", "file", "wsreset.exe", "Vide le cache du Store.", "🛍", g)

    # ============================================================ Nettoyage
    c = "nettoyage"
    g = "Nettoyage de disque"
    add(c, "cleanmgr", "Nettoyage de disque", "file", "cleanmgr.exe", "L'outil classique de nettoyage.", "🧹", g)
    add(c, "cleanmgr_sys", "Nettoyage des fichiers système", "file", "cleanmgr.exe",
        "Nettoyage de disque avec les fichiers système (mises à jour, anciens Windows).", "🧹", g, args="/d C", admin=True)
    add(c, "sageset", "Configurer le nettoyage automatique (sageset)", "file", "cleanmgr.exe",
        "Choisis une fois ce qu'il faut nettoyer (profil 64).", "⚙", g, args="/sageset:64", admin=True)
    add(c, "sagerun", "Lancer le nettoyage configuré (sagerun)", "file", "cleanmgr.exe",
        "Nettoie selon le profil 64 sans poser de question.", "▶", g, args="/sagerun:64", admin=True, confirm=True)
    add(c, "storagesense", "Assistant de stockage", "shell", "ms-settings:storagesense", "Nettoyage automatique de Windows.", "🗄", g)
    g = "Fichiers temporaires"
    add(c, "temp_user", "Vider %TEMP%", "ps",
        "$before = (Get-ChildItem $env:TEMP -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum\n"
        "Get-ChildItem $env:TEMP -Force -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue\n"
        "$after = (Get-ChildItem $env:TEMP -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum\n"
        "'Libéré : {0:N0} Mo (les fichiers en cours d''utilisation restent).' -f (($before - $after) / 1MB)",
        "Supprime tes fichiers temporaires.", "🗑", g, confirm=True)
    add(c, "temp_win", "Vider C:\\Windows\\Temp", "ps",
        "Get-ChildItem \"$env:SystemRoot\\Temp\" -Force -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue\n"
        "'C:\\Windows\\Temp vidé (fichiers verrouillés ignorés).'",
        "Temporaires du système.", "🗑", g, admin=True, confirm=True)
    add(c, "wu_cache", "Vider le cache Windows Update", "ps",
        "Stop-Service wuauserv,bits -Force -ErrorAction SilentlyContinue\n"
        "Remove-Item \"$env:SystemRoot\\SoftwareDistribution\\Download\\*\" -Recurse -Force -ErrorAction SilentlyContinue\n"
        "Start-Service wuauserv,bits -ErrorAction SilentlyContinue\n'Cache des téléchargements Windows Update vidé.'",
        "Libère les mises à jour déjà téléchargées.", "🧺", g, admin=True, confirm=True)
    add(c, "recycle", "Vider la corbeille", "ps", "Clear-RecycleBin -Force -ErrorAction SilentlyContinue\n'Corbeille vidée.'",
        "Vide la corbeille de tous les disques (définitif).", "♻", g, danger=True)
    add(c, "dism_cleanup", "DISM — nettoyer les composants", "cmd", "DISM /Online /Cleanup-Image /StartComponentCleanup",
        "Supprime les anciennes versions des composants Windows (WinSxS).", "🧽", g, admin=True, console="keep", confirm=True)
    add(c, "dism_analyze", "DISM — taille de WinSxS", "cmd", "DISM /Online /Cleanup-Image /AnalyzeComponentStore",
        "Combien le magasin de composants prend et s'il faut le nettoyer.", "📏", g, admin=True, console="keep")
    add(c, "clipclear", "Vider le presse-papiers", "cmd", "echo off | clip", "Efface le contenu du presse-papiers.", "📋", g,
        console="hidden")
    g = "Espace disque"
    add(c, "foldersize", "Taille des sous-dossiers", "ps",
        "Get-ChildItem -LiteralPath \"{DOSSIER}\" -Directory -Force -ErrorAction SilentlyContinue | ForEach-Object {\n"
        "  $s = (Get-ChildItem -LiteralPath $_.FullName -Recurse -File -Force -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum\n"
        "  [pscustomobject]@{ 'Taille (Mo)' = [math]::Round($s / 1MB, 1); Dossier = $_.Name }\n"
        "} | Sort-Object 'Taille (Mo)' -Descending | Format-Table -AutoSize",
        "Ce qui prend de la place dans un dossier, du plus gros au plus petit.", "📊", g,
        ask=[A("DOSSIER", "Dossier à mesurer", "folder", "C:\\Users")])
    add(c, "bigfiles", "30 plus gros fichiers d'un dossier", "ps",
        "Get-ChildItem -LiteralPath \"{DOSSIER}\" -Recurse -File -Force -ErrorAction SilentlyContinue | "
        "Sort-Object Length -Descending | Select-Object -First 30 @{n='Mo';e={[math]::Round($_.Length/1MB,1)}},FullName | "
        "Format-Table -AutoSize",
        "Trouver les fichiers géants (vidéos oubliées, ISO...).", "🐘", g, ask=[A("DOSSIER", "Dossier à fouiller", "folder", "C:\\")])
    add(c, "hiber_off", "Désactiver la mise en veille prolongée", "cmd", "powercfg /hibernate off",
        "Supprime hiberfil.sys (libère plusieurs Go) ; désactive aussi le démarrage rapide.", "💤", g, admin=True, confirm=True)
    add(c, "hiber_on", "Réactiver la mise en veille prolongée", "cmd", "powercfg /hibernate on",
        "Recrée hiberfil.sys (démarrage rapide de nouveau possible).", "⏰", g, admin=True)

    # ============================================================ Réseau
    c = "reseau"
    g = "Adresses & état"
    add(c, "myip", "Mon IP (publique et locale)", "builtin", "myip", "IP publique et IP locales, copiables.", "🌍", g)
    add(c, "ipconfig", "ipconfig /all", "cmd", "ipconfig /all", "Toutes les cartes réseau : IP, passerelle, DNS, MAC.", "🧾", g)
    add(c, "pubip_ps", "IP publique (ligne de commande)", "ps", "Invoke-RestMethod -Uri 'https://api.ipify.org'",
        "Ton IP publique vue d'Internet.", "🌐", g)
    add(c, "dns_servers", "Serveurs DNS utilisés", "ps",
        "Get-DnsClientServerAddress -AddressFamily IPv4 | Where-Object ServerAddresses | Format-Table InterfaceAlias,ServerAddresses -AutoSize",
        "Quels DNS chaque carte utilise.", "📖", g)
    add(c, "wifi_if", "Wi-Fi — signal et connexion", "cmd", "netsh wlan show interfaces",
        "Réseau connecté, signal en %, vitesse.", "📶", g)
    add(c, "netstat", "Connexions actives (netstat -ano)", "cmd", "netstat -ano", "Toutes les connexions avec leur PID.", "🔗", g)
    add(c, "conns_proc", "Connexions établies (avec programme)", "ps",
        "Get-NetTCPConnection -State Established | Select-Object RemoteAddress,RemotePort,"
        "@{n='Programme';e={(Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue).ProcessName}},OwningProcess | "
        "Sort-Object Programme | Format-Table -AutoSize",
        "Qui parle à Internet en ce moment.", "🕸", g)
    add(c, "arp", "Appareils vus sur le réseau (ARP)", "cmd", "arp -a", "Adresses IP/MAC récemment vues sur le réseau local.", "🏘", g)
    add(c, "getmac", "Adresses MAC", "cmd", "getmac /v /fo list", "Adresse physique de chaque carte.", "🏷", g)
    add(c, "route", "Table de routage", "cmd", "route print -4", "Routes IPv4 et passerelle par défaut.", "🛣", g)
    g = "Diagnostic"
    add(c, "ping_google", "Ping continu 8.8.8.8", "cmd", "ping 8.8.8.8 -t",
        "Surveille la connexion en continu (Ctrl+C pour arrêter).", "📡", g, console="keep")
    add(c, "ping_host", "Ping d'un hôte", "cmd", "ping {HOTE}", "4 pings vers un site ou une IP.", "🏓", g,
        ask=[A("HOTE", "Site ou IP", "text", "google.com")])
    add(c, "tracert", "Tracert (chemin réseau)", "cmd", "tracert -d {HOTE}", "Par où passent les paquets jusqu'au site.", "🧭", g,
        ask=[A("HOTE", "Site ou IP", "text", "google.com")])
    add(c, "nslookup", "nslookup (résolution DNS)", "cmd", "nslookup {HOTE}", "Quelle IP correspond à un nom.", "🔤", g,
        ask=[A("HOTE", "Nom de domaine", "text", "marcsevigny.ca")])
    add(c, "testport", "Tester un port (Test-NetConnection)", "ps",
        "Test-NetConnection -ComputerName \"{HOTE}\" -Port {PORT} -WarningAction SilentlyContinue | "
        "Format-List ComputerName,RemoteAddress,RemotePort,TcpTestSucceeded",
        "Un port est-il ouvert sur une machine (ex. 80, 443, 3389) ?", "🚪", g,
        ask=[A("HOTE", "Hôte", "text", "marcsevigny.ca"), A("PORT", "Port", "text", "443")])
    add(c, "wifi_keys", "Clés Wi-Fi enregistrées", "ps",
        "$names = netsh wlan show profiles | Select-String '(?:Profil Tous les utilisateurs|All User Profile)\\s*:\\s*(.+)$' | "
        "ForEach-Object { $_.Matches[0].Groups[1].Value.Trim() }\n"
        "if (-not $names) { 'Aucun profil Wi-Fi enregistré sur ce PC.' }\n"
        "foreach ($n in $names) { $k = netsh wlan show profile name=\"$n\" key=clear | "
        "Select-String '(?:Contenu de la cl.|Key Content)\\s*:\\s*(.+)$' | ForEach-Object { $_.Matches[0].Groups[1].Value.Trim() }\n"
        "  [pscustomobject]@{ Reseau = $n; Cle = $k } }",
        "Retrouve la clé de tes réseaux Wi-Fi déjà utilisés (netsh wlan show profile key=clear).", "🔑", g, admin=True)
    add(c, "wlanreport", "Rapport Wi-Fi (HTML)", "cmd",
        'netsh wlan show wlanreport && start "" "C:\\ProgramData\\Microsoft\\Windows\\WlanReport\\wlan-report-latest.html"',
        "Historique des déconnexions Wi-Fi des 3 derniers jours.", "📈", g, admin=True, console="pause")
    g = "Réparer la connexion"
    add(c, "flushdns", "Vider le cache DNS", "cmd", "ipconfig /flushdns", "Quand un site a changé d'adresse ou ne répond plus.", "🚿", g)
    add(c, "renew", "Renouveler l'IP (release/renew)", "cmd", "ipconfig /release & ipconfig /renew",
        "Redemande une adresse au routeur (coupe Internet quelques secondes).", "🔄", g, console="keep", confirm=True)
    add(c, "netreset", "Réinitialiser Winsock et TCP/IP", "cmd", "netsh winsock reset & netsh int ip reset",
        "Répare une pile réseau corrompue. Redémarrage nécessaire ensuite.", "🧯", g, admin=True, console="keep", danger=True)
    add(c, "ncpa", "Connexions réseau (cartes)", "file", "ncpa.cpl", "Activer/désactiver une carte, propriétés IPv4.", "🔌", g)
    add(c, "netstatus", "Paramètres réseau", "shell", "ms-settings:network-status", "État et réinitialisation du réseau.", "⚙", g)
    add(c, "netshare", "Partages de ce PC", "cmd", "net share", "Dossiers partagés sur le réseau.", "🤝", g)
    add(c, "netuse", "Lecteurs réseau connectés", "cmd", "net use", "Lecteurs réseau mappés.", "🗄", g)

    # ============================================================ Système
    c = "systeme"
    g = "Infos"
    add(c, "systeminfo", "systeminfo", "cmd", "systeminfo", "Résumé complet : Windows, mémoire, mises à jour, réseau (environ 10 s).", "🧾", g)
    add(c, "osinfo", "Version de Windows", "ps",
        "Get-CimInstance Win32_OperatingSystem | Format-List Caption,Version,BuildNumber,OSArchitecture,InstallDate,LastBootUpTime",
        "Édition, build, date d'installation.", "🪟", g)
    add(c, "winver", "À propos de Windows (winver)", "file", "winver.exe", "Version exacte de Windows.", "ℹ", g)
    add(c, "uptime", "Depuis quand le PC tourne", "ps",
        "$b = (Get-CimInstance Win32_OperatingSystem).LastBootUpTime\n$u = (Get-Date) - $b\n"
        "\"Démarré le : $b\"\n'En marche depuis : {0} j {1} h {2} min' -f $u.Days, $u.Hours, $u.Minutes",
        "Dernier démarrage et durée.", "⏱", g)
    add(c, "hardware", "Matériel (CPU, RAM, carte graphique)", "ps",
        "Get-CimInstance Win32_Processor | Format-List Name,NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed\n"
        "Get-CimInstance Win32_PhysicalMemory | Format-Table Manufacturer,PartNumber,@{n='Go';e={$_.Capacity/1GB}},Speed -AutoSize\n"
        "Get-CimInstance Win32_VideoController | Format-List Name,DriverVersion,VideoModeDescription\n"
        "Get-CimInstance Win32_BaseBoard | Format-List Manufacturer,Product",
        "Processeur, barrettes de mémoire, GPU, carte mère.", "🧮", g)
    add(c, "bios", "BIOS et modèle", "ps",
        "Get-CimInstance Win32_BIOS | Format-List Manufacturer,SMBIOSBIOSVersion,SerialNumber,ReleaseDate\n"
        "Get-CimInstance Win32_ComputerSystem | Format-List Manufacturer,Model,SystemType",
        "Fabricant, modèle, version du BIOS, numéro de série.", "🔢", g)
    add(c, "productkey", "Clé de produit Windows (OEM)", "ps",
        "$k = (Get-CimInstance SoftwareLicensingService).OA3xOriginalProductKey\n"
        "if ($k) { \"Clé OEM : $k\" } else { 'Aucune clé OEM dans le BIOS (licence numérique ou clé saisie).' }",
        "La clé gravée dans le BIOS par le fabricant.", "🔑", g)
    add(c, "activation", "État de l'activation", "cmd", "cscript //nologo %windir%\\system32\\slmgr.vbs /dli",
        "Licence et activation de Windows.", "✅", g)
    add(c, "msinfo", "Informations système (msinfo32)", "file", "msinfo32.exe", "Tout le détail matériel et logiciel.", "📇", g)
    add(c, "dxdiag", "DirectX (dxdiag)", "file", "dxdiag.exe", "Carte graphique, son, pilotes DirectX.", "🎮", g)
    add(c, "winsat", "Score WinSAT", "ps",
        "Get-CimInstance Win32_WinSAT | Format-List CPUScore,MemoryScore,D3DScore,GraphicsScore,DiskScore,WinSPRLevel",
        "Indice de performance (dernière évaluation).", "🏁", g)
    add(c, "envpath", "Contenu du PATH", "ps", "$env:Path -split ';' | Where-Object { $_ }", "Chaque dossier du PATH sur une ligne.", "🛤", g)
    g = "Logiciels & pilotes"
    add(c, "installed", "Logiciels installés", "ps",
        "Get-ItemProperty HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*,"
        "HKLM:\\Software\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*,"
        "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\* -ErrorAction SilentlyContinue | "
        "Where-Object DisplayName | Sort-Object DisplayName -Unique | Format-Table DisplayName,DisplayVersion,Publisher -AutoSize",
        "Tous les programmes installés avec leur version.", "📦", g)
    add(c, "startup", "Programmes au démarrage", "ps",
        "Get-CimInstance Win32_StartupCommand | Sort-Object Name | Format-Table Name,Command,Location -AutoSize -Wrap",
        "Ce qui se lance avec Windows (Run, dossier Démarrage).", "🚀", g)
    add(c, "startupapps", "Applications au démarrage (réglages)", "shell", "ms-settings:startupapps", "Activer/désactiver.", "🚀", g)
    add(c, "winget_list", "winget — mises à jour disponibles", "cmd", "winget upgrade",
        "Liste les logiciels qui ont une mise à jour.", "📋", g, console="keep")
    add(c, "winget_all", "winget — tout mettre à jour", "cmd",
        "winget upgrade --all --accept-package-agreements --accept-source-agreements",
        "Met à jour tous les logiciels connus de winget (peut redémarrer certains programmes).", "⬆", g,
        console="keep", confirm=True)
    add(c, "winget_search", "winget — chercher un logiciel", "cmd", 'winget search "{NOM}"', "Trouver l'identifiant d'un logiciel.",
        "🔎", g, console="keep", ask=[A("NOM", "Nom du logiciel", "text", "7zip")])
    add(c, "drivers", "Liste des pilotes", "ps",
        "Get-CimInstance Win32_PnPSignedDriver | Where-Object DeviceName | Sort-Object DeviceName | "
        "Format-Table DeviceName,DriverVersion,Manufacturer -AutoSize",
        "Tous les pilotes avec leur version.", "🧩", g)
    add(c, "drivers_backup", "Sauvegarder tous les pilotes", "cmd", 'dism /online /export-driver /destination:"{DOSSIER}"',
        "Copie les pilotes tiers dans un dossier (utile avant une réinstallation).", "💾", g, admin=True, console="keep",
        ask=[A("DOSSIER", "Dossier de destination (vide)", "folder", "D:\\Pilotes")])
    g = "Journaux"
    add(c, "sys_errors", "Erreurs système récentes", "ps",
        "Get-WinEvent -FilterHashtable @{LogName='System'; Level=1,2} -MaxEvents 30 -ErrorAction SilentlyContinue | "
        "Format-Table TimeCreated,ProviderName,Id,Message -AutoSize -Wrap",
        "Les 30 dernières erreurs critiques du journal Système.", "🚨", g)
    add(c, "crashes", "Plantages et redémarrages inattendus", "ps",
        "$e = Get-WinEvent -FilterHashtable @{LogName='System'; Id=41,1001,6008} -MaxEvents 20 -ErrorAction SilentlyContinue\n"
        "if (-not $e) { 'Aucun plantage ni arrêt inattendu enregistré.' } else { $e | Format-Table TimeCreated,Id,ProviderName,Message -AutoSize -Wrap }",
        "Écrans bleus (1001), coupures (41), arrêts inattendus (6008).", "💥", g)
    add(c, "shutdowns", "Historique des arrêts/démarrages", "ps",
        "Get-WinEvent -FilterHashtable @{LogName='System'; Id=1074,6005,6006,6008} -MaxEvents 25 -ErrorAction SilentlyContinue | "
        "Format-Table TimeCreated,Id,Message -AutoSize -Wrap",
        "Qui a éteint ou redémarré le PC et quand.", "🕰", g)
    g = "Alimentation"
    add(c, "battery", "Rapport de batterie", "cmd",
        'powercfg /batteryreport /output "%TEMP%\\battery-report.html" && start "" "%TEMP%\\battery-report.html"',
        "Usure et autonomie de la batterie (portables seulement).", "🔋", g)
    add(c, "energy", "Rapport énergie (60 s)", "cmd",
        'powercfg /energy /output "%TEMP%\\energy-report.html" & start "" "%TEMP%\\energy-report.html"',
        "Analyse 60 secondes ce qui gaspille l'énergie ou empêche la veille.", "⚡", g, admin=True, console="keep")
    add(c, "powerplans", "Modes d'alimentation", "cmd", "powercfg /list", "Les plans et celui qui est actif (*).", "🔌", g)
    add(c, "powerreq", "Ce qui empêche la mise en veille", "cmd", "powercfg /requests",
        "Programmes ou pilotes qui gardent le PC éveillé.", "☕", g, admin=True)
    add(c, "powercpl", "Options d'alimentation", "file", "powercfg.cpl", "Panneau des modes d'alimentation.", "🔋", g)
    add(c, "sleep", "Mettre en veille", "ps",
        "Add-Type -AssemblyName System.Windows.Forms\n[System.Windows.Forms.Application]::SetSuspendState('Suspend', $false, $false) | Out-Null",
        "Met le PC en veille maintenant.", "🌙", g, console="hidden", confirm=True)
    add(c, "restart", "Redémarrer", "cmd", "shutdown /r /t 0", "Redémarre immédiatement.", "🔁", g, console="hidden", danger=True)
    add(c, "poweroff", "Éteindre", "cmd", "shutdown /s /t 0", "Éteint immédiatement.", "⏻", g, console="hidden", danger=True)
    add(c, "poweroff_timer", "Éteindre dans X minutes", "ps",
        "$m = [int]'{MINUTES}'\nshutdown /s /t ($m * 60)\n\"Arrêt programmé dans $m minutes (annuler : shutdown /a).\"",
        "Programme l'arrêt (minuterie).", "⏲", g, confirm=True, ask=[A("MINUTES", "Dans combien de minutes ?", "text", "60")])
    add(c, "poweroff_abort", "Annuler un arrêt programmé", "cmd", "shutdown /a", "Annule la minuterie d'arrêt.", "✋", g)

    # ============================================================ Processus & services
    c = "processus"
    g = "Processus"
    add(c, "top_mem", "Top 20 — mémoire", "ps",
        "Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 20 Name,Id,"
        "@{n='Mémoire (Mo)';e={[math]::Round($_.WorkingSet64/1MB)}},@{n='CPU (s)';e={[math]::Round($_.CPU,1)}} | Format-Table -AutoSize",
        "Les programmes qui prennent le plus de mémoire.", "🐘", g)
    add(c, "top_cpu", "Top 20 — processeur", "ps",
        "Get-Process | Sort-Object CPU -Descending | Select-Object -First 20 Name,Id,@{n='CPU (s)';e={[math]::Round($_.CPU,1)}},"
        "@{n='Mémoire (Mo)';e={[math]::Round($_.WorkingSet64/1MB)}} | Format-Table -AutoSize",
        "Temps processeur cumulé.", "🔥", g)
    add(c, "tasklist", "Liste des processus (tasklist)", "cmd", "tasklist", "Tous les processus avec PID et mémoire.", "📃", g)
    add(c, "tasklist_svc", "Services par processus", "cmd", "tasklist /svc", "Quels services tournent dans chaque svchost.", "🧵", g)
    add(c, "proc_path", "Où se trouve ce programme", "ps",
        "Get-Process -Name \"{NOM}\" -ErrorAction SilentlyContinue | Select-Object Id,StartTime,Path | Format-Table -AutoSize -Wrap",
        "Chemin de l'exécutable d'un processus (sans .exe).", "📍", g, ask=[A("NOM", "Nom du processus (sans .exe)", "text", "pythonw")])
    add(c, "notresp", "Applications qui ne répondent pas", "ps",
        "$p = Get-Process | Where-Object { $_.MainWindowHandle -ne 0 -and -not $_.Responding }\n"
        "if ($p) { $p | Format-Table Name,Id -AutoSize } else { 'Toutes les applications répondent.' }",
        "Repérer les fenêtres gelées.", "🧊", g)
    add(c, "kill_notresp", "Fermer les applications gelées", "cmd", 'taskkill /f /fi "status eq not responding"',
        "Force la fermeture de tout ce qui ne répond plus.", "💀", g, confirm=True)
    add(c, "kill_name", "Arrêter un processus (nom)", "cmd", 'taskkill /f /im "{NOM}"', "Ferme de force un programme par son nom.",
        "🔪", g, danger=True, ask=[A("NOM", "Nom de l'exécutable", "text", "notepad.exe")])
    add(c, "kill_pid", "Arrêter un processus (PID)", "cmd", "taskkill /f /pid {PID}", "Ferme de force un processus par son numéro.",
        "🔪", g, danger=True, ask=[A("PID", "Numéro du processus (PID)", "text")])
    add(c, "explorer_restart", "Redémarrer l'Explorateur", "cmd", "taskkill /f /im explorer.exe & start explorer.exe",
        "Quand la barre des tâches ou le Bureau sont gelés.", "🔄", g, confirm=True, console="hidden")
    g = "Services"
    add(c, "svc_running", "Services en cours", "ps",
        "Get-Service | Where-Object Status -eq 'Running' | Sort-Object DisplayName | Format-Table Name,DisplayName -AutoSize",
        "Tous les services démarrés.", "🟢", g)
    add(c, "svc_failed", "Services automatiques arrêtés", "ps",
        "Get-CimInstance Win32_Service -Filter \"StartMode='Auto' AND State<>'Running'\" | Sort-Object DisplayName | "
        "Format-Table Name,DisplayName,State,ExitCode -AutoSize",
        "Services censés tourner mais arrêtés (souvent normal, parfois une panne).", "🔴", g)
    add(c, "svc_restart", "Redémarrer un service", "ps", "Restart-Service -Name \"{NOM}\" -Force -PassThru | Format-Table Name,Status,DisplayName -AutoSize",
        "Relance un service par son nom court (ex. Spooler, Audiosrv, wuauserv).", "🔁", g, admin=True, confirm=True,
        ask=[A("NOM", "Nom du service", "text", "Spooler")])
    add(c, "who_port", "Qui utilise ce port", "ps",
        "$c = Get-NetTCPConnection -LocalPort {PORT} -ErrorAction SilentlyContinue\n"
        "if (-not $c) { 'Aucun programme sur ce port.' } else { $c | Select-Object LocalAddress,LocalPort,State,OwningProcess,"
        "@{n='Programme';e={(Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue).Path}} | Format-Table -AutoSize -Wrap }",
        "Le programme qui occupe un port (ex. 80 pour Apache).", "🚪", g, ask=[A("PORT", "Port", "text", "80")])
    add(c, "services_msc", "Services (console)", "file", "services.msc", "Gérer les services Windows.", "⚙", g)
    add(c, "taskschd", "Planificateur de tâches", "file", "taskschd.msc", "Tâches automatiques.", "⏰", g)

    # ============================================================ Comptes & session
    c = "comptes"
    g = "Comptes"
    add(c, "whoami", "Qui suis-je (whoami)", "cmd", "whoami & whoami /groups /fo table", "Ton compte et tes groupes (Administrateurs ?).", "🙋", g)
    add(c, "localusers", "Comptes locaux", "ps", "Get-LocalUser | Format-Table Name,Enabled,LastLogon,PasswordRequired,Description -AutoSize",
        "Tous les comptes de ce PC.", "👥", g)
    add(c, "admins", "Membres du groupe Administrateurs", "ps",
        "Get-LocalGroupMember -SID 'S-1-5-32-544' | Format-Table Name,ObjectClass,PrincipalSource -AutoSize",
        "Qui a les droits d'administrateur.", "👑", g)
    add(c, "netaccounts", "Stratégie de mot de passe", "cmd", "net accounts", "Durée, longueur minimale, verrouillage.", "🔐", g)
    add(c, "netplwiz", "Comptes d'utilisateurs (netplwiz)", "file", "netplwiz.exe", "Gérer les comptes, connexion automatique.", "👤", g)
    add(c, "lusrmgr", "Utilisateurs et groupes locaux", "file", "lusrmgr.msc", "Console avancée (Windows Pro/Entreprise).", "👥", g)
    add(c, "credman", "Gestionnaire d'identification", "file", "control.exe", "Identifiants enregistrés par Windows (sites, réseau).",
        "🗝", g, args="/name Microsoft.CredentialManager")
    add(c, "yourinfo", "Tes infos (compte Microsoft)", "shell", "ms-settings:yourinfo", "Ton compte.", "🪪", g)
    add(c, "signin", "Options de connexion", "shell", "ms-settings:signinoptions", "PIN, mot de passe, Windows Hello.", "🔢", g)
    add(c, "otherusers", "Famille et autres utilisateurs", "shell", "ms-settings:otherusers", "Ajouter un compte.", "👪", g)
    g = "Session"
    add(c, "lock", "Verrouiller la session", "file", "rundll32.exe", "Comme Win+L.", "🔒", g, args="user32.dll,LockWorkStation")
    add(c, "logoff", "Se déconnecter", "cmd", "shutdown /l", "Ferme ta session (enregistre ton travail).", "🚪", g, console="hidden", danger=True)
    add(c, "sessions", "Sessions ouvertes", "ps",
        "Get-CimInstance Win32_LoggedOnUser | ForEach-Object { $_.Antecedent.Name } | Sort-Object -Unique",
        "Comptes ayant une session active.", "🪑", g)

    # ============================================================ Périphériques
    c = "peripheriques"
    g = "Impression"
    add(c, "spooler_reset", "Réinitialiser le spouleur d'impression", "cmd",
        'net stop spooler /y & del /q /f "%SystemRoot%\\System32\\spool\\PRINTERS\\*" & net start spooler',
        "Débloque une impression coincée : arrête le spouleur, vide la file, relance.", "🖨", g, admin=True,
        console="keep", confirm=True)
    add(c, "printers", "Imprimantes installées", "ps", "Get-Printer | Format-Table Name,DriverName,PortName,PrinterStatus -AutoSize",
        "Liste des imprimantes et leur état.", "🖨", g)
    add(c, "printjobs", "File d'attente d'impression", "ps",
        "$j = Get-Printer | ForEach-Object { Get-PrintJob -PrinterName $_.Name -ErrorAction SilentlyContinue }\n"
        "if ($j) { $j | Format-Table PrinterName,DocumentName,JobStatus,SubmittedTime -AutoSize } else { 'Aucun travail en attente.' }",
        "Ce qui attend d'être imprimé.", "📄", g)
    add(c, "printers_set", "Imprimantes et scanners", "shell", "ms-settings:printers", "Ajouter/gérer une imprimante.", "⚙", g)
    add(c, "printers_cpl", "Périphériques et imprimantes", "file", "control.exe", "Panneau classique.", "🖨", g, args="printers")
    g = "Son"
    add(c, "sound_set", "Paramètres de son", "shell", "ms-settings:sound", "Sortie, entrée, volume.", "🔊", g)
    add(c, "mmsys", "Panneau Son (classique)", "file", "control.exe", "Périphériques de lecture/enregistrement détaillés.", "🎚", g,
        args="mmsys.cpl")
    add(c, "sndvol", "Mélangeur de volume", "file", "sndvol.exe", "Volume par application.", "🎛", g)
    add(c, "audio_restart", "Redémarrer le service audio", "ps",
        "Restart-Service -Name Audiosrv,AudioEndpointBuilder -Force -PassThru | Format-Table Name,Status -AutoSize",
        "Quand le son disparaît sans raison.", "🔈", g, admin=True)
    add(c, "audio_devices", "Périphériques audio", "ps", "Get-CimInstance Win32_SoundDevice | Format-Table Name,Manufacturer,Status -AutoSize",
        "Cartes son détectées.", "🎧", g)
    add(c, "mic_privacy", "Confidentialité — microphone", "shell", "ms-settings:privacy-microphone", "Applications autorisées.", "🎙", g)
    g = "Écran"
    add(c, "display", "Paramètres d'affichage", "shell", "ms-settings:display", "Résolution, échelle, écrans multiples.", "🖥", g)
    add(c, "nightlight", "Éclairage nocturne", "shell", "ms-settings:nightlight", "Lumière chaude le soir.", "🌙", g)
    add(c, "dccw", "Étalonner les couleurs", "file", "dccw.exe", "Assistant de calibration de l'écran.", "🎨", g)
    add(c, "displayswitch", "Projeter (Win+P)", "file", "displayswitch.exe", "Dupliquer/étendre vers un 2e écran.", "📽", g)
    add(c, "gpuinfo", "Résolution et carte graphique", "ps",
        "Get-CimInstance Win32_VideoController | Format-List Name,CurrentHorizontalResolution,CurrentVerticalResolution,"
        "CurrentRefreshRate,DriverVersion",
        "Résolution actuelle, fréquence, version du pilote.", "📺", g)
    add(c, "graphics", "Paramètres graphiques (GPU par appli)", "shell", "ms-settings:display-advancedgraphics", "Performances GPU par programme.", "🎮", g)
    g = "Bluetooth & USB"
    add(c, "bt_set", "Bluetooth et appareils", "shell", "ms-settings:bluetooth", "Jumeler un appareil.", "🔵", g)
    add(c, "bt_list", "Appareils Bluetooth", "ps", "Get-PnpDevice -Class Bluetooth | Sort-Object FriendlyName | Format-Table FriendlyName,Status -AutoSize",
        "Appareils Bluetooth connus et leur état.", "🔵", g)
    add(c, "bt_restart", "Redémarrer le service Bluetooth", "ps", "Restart-Service -Name bthserv -Force -PassThru | Format-Table Name,Status -AutoSize",
        "Quand un appareil Bluetooth refuse de se connecter.", "🔁", g, admin=True)
    add(c, "fsquirt", "Envoyer/recevoir par Bluetooth", "file", "fsquirt.exe", "Transfert de fichiers Bluetooth.", "📲", g)
    add(c, "usb_list", "Périphériques USB branchés", "ps",
        "Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -like 'USB*' } | Sort-Object Class | "
        "Format-Table FriendlyName,Class,Status -AutoSize",
        "Tout ce qui est branché en USB.", "🔌", g)
    add(c, "dev_errors", "Périphériques en erreur", "ps",
        "$d = Get-PnpDevice -PresentOnly | Where-Object Status -ne 'OK'\n"
        "if ($d) { $d | Format-Table FriendlyName,Class,Status -AutoSize } else { 'Tous les périphériques fonctionnent.' }",
        "Les points d'exclamation jaunes du Gestionnaire de périphériques.", "❗", g)
    add(c, "safe_remove", "Retirer un périphérique en toute sécurité", "file", "rundll32.exe", "Éjecter une clé ou un disque USB.",
        "⏏", g, args="shell32.dll,Control_RunDLL hotplug.dll")
    add(c, "devmgmt", "Gestionnaire de périphériques", "file", "devmgmt.msc", "Pilotes et matériel.", "🧩", g)
    g = "Clavier & souris"
    add(c, "mouse", "Souris (panneau classique)", "file", "control.exe", "Vitesse du pointeur, boutons, roulette.", "🖱", g, args="main.cpl")
    add(c, "mouse_set", "Paramètres souris", "shell", "ms-settings:mousetouchpad", "Souris et pavé tactile.", "🖱", g)
    add(c, "typing", "Saisie (clavier)", "shell", "ms-settings:typing", "Correction, suggestions.", "⌨", g)
    add(c, "osk", "Clavier visuel", "file", "osk.exe", "Clavier à l'écran.", "⌨", g)

    # ============================================================ Disques & fichiers
    c = "disques"
    g = "Disques"
    add(c, "freespace", "Espace libre des disques", "ps",
        "Get-PSDrive -PSProvider FileSystem | Where-Object Used -ne $null | Select-Object Name,"
        "@{n='Utilisé (Go)';e={[math]::Round($_.Used/1GB,1)}},@{n='Libre (Go)';e={[math]::Round($_.Free/1GB,1)}},"
        "@{n='% libre';e={if(($_.Used+$_.Free) -gt 0){[math]::Round(100*$_.Free/($_.Used+$_.Free))}}},Root | Format-Table -AutoSize",
        "Combien il reste sur C:, D:, E:...", "📊", g)
    add(c, "disk_health", "Santé des disques", "ps",
        "Get-PhysicalDisk | Format-Table FriendlyName,MediaType,BusType,HealthStatus,OperationalStatus,"
        "@{n='Taille (Go)';e={[math]::Round($_.Size/1GB)}} -AutoSize",
        "État de santé rapporté par chaque disque (Healthy = OK).", "❤", g)
    add(c, "disk_smart", "Compteurs de fiabilité (SMART)", "ps",
        "Get-PhysicalDisk | ForEach-Object { $r = $_ | Get-StorageReliabilityCounter -ErrorAction SilentlyContinue\n"
        "[pscustomobject]@{ Disque = $_.FriendlyName; 'Temp C' = $r.Temperature; 'Usure %' = $r.Wear; "
        "'Erreurs lecture' = $r.ReadErrorsTotal; 'Heures' = $r.PowerOnHours } } | Format-Table -AutoSize",
        "Température, usure (SSD), erreurs et heures de fonctionnement.", "🌡", g, admin=True)
    add(c, "volumes", "Volumes", "ps", "Get-Volume | Where-Object DriveLetter | Sort-Object DriveLetter | Format-Table DriveLetter,FileSystemLabel,"
        "FileSystem,DriveType,HealthStatus,@{n='Libre (Go)';e={[math]::Round($_.SizeRemaining/1GB,1)}},@{n='Taille (Go)';e={[math]::Round($_.Size/1GB,1)}} -AutoSize",
        "Lettres, étiquettes, systèmes de fichiers, état.", "🗂", g)
    add(c, "partitions", "Partitions", "ps", "Get-Partition | Format-Table DiskNumber,PartitionNumber,DriveLetter,"
        "@{n='Taille (Go)';e={[math]::Round($_.Size/1GB,1)}},Type -AutoSize", "Toutes les partitions de chaque disque.", "🧱", g)
    add(c, "bitlocker", "BitLocker — statut", "cmd", "manage-bde -status",
        "Chiffrement des disques (BitLocker / chiffrement de l'appareil).", "🔐", g, admin=True)
    add(c, "trim", "TRIM des SSD actif ?", "cmd", "fsutil behavior query DisableDeleteNotify",
        "DisableDeleteNotify = 0 veut dire que TRIM est actif (bon pour les SSD).", "✂", g, admin=True)
    add(c, "dfrgui", "Optimiser les lecteurs", "file", "dfrgui.exe", "Défragmentation (HDD) / TRIM (SSD) planifiés.", "🧩", g)
    add(c, "diskmgmt", "Gestion des disques", "file", "diskmgmt.msc", "Partitions, lettres, formatage.", "💽", g)
    g = "Fichiers"
    add(c, "hash", "Empreinte d'un fichier (SHA256)", "ps",
        "Get-FileHash -Algorithm SHA256 -LiteralPath \"{FICHIER}\" | Format-List Algorithm,Hash,Path",
        "Vérifier qu'un téléchargement est intact.", "🧬", g, ask=[A("FICHIER", "Fichier", "file")])
    add(c, "recent_files", "Fichiers modifiés depuis 7 jours", "ps",
        "Get-ChildItem -LiteralPath \"{DOSSIER}\" -Recurse -File -Force -ErrorAction SilentlyContinue | "
        "Where-Object LastWriteTime -gt (Get-Date).AddDays(-7) | Sort-Object LastWriteTime -Descending | "
        "Select-Object -First 50 LastWriteTime,@{n='Ko';e={[math]::Round($_.Length/1KB)}},FullName | Format-Table -AutoSize",
        "Ce qui a changé récemment dans un dossier.", "🆕", g, ask=[A("DOSSIER", "Dossier", "folder", "C:\\web")])
    add(c, "huge", "Fichiers de plus de 1 Go sur un disque", "ps",
        "Get-ChildItem -LiteralPath \"{LETTRE}:\\\" -Recurse -File -Force -ErrorAction SilentlyContinue | Where-Object Length -gt 1GB | "
        "Sort-Object Length -Descending | Select-Object -First 40 @{n='Go';e={[math]::Round($_.Length/1GB,2)}},FullName | Format-Table -AutoSize",
        "Liste les fichiers géants (prend quelques minutes).", "🐋", g, ask=[A("LETTRE", "Lettre du disque", "drive", "C")])
    add(c, "unhide_usb", "Récupérer les fichiers cachés d'une clé USB", "cmd", 'attrib -h -s -r /s /d "{LETTRE}:\\*"',
        "Après un virus de clé USB : rend visibles les fichiers masqués.", "👁", g, console="keep", confirm=True,
        ask=[A("LETTRE", "Lettre de la clé", "drive", "E")])
    add(c, "folder_options", "Options de l'Explorateur", "file", "control.exe", "Afficher les fichiers cachés et les extensions.", "🗂", g,
        args="folders")
    add(c, "tree", "Arborescence d'un dossier (tree)", "cmd", 'tree "{DOSSIER}" /a', "Structure des sous-dossiers.", "🌳", g,
        ask=[A("DOSSIER", "Dossier", "folder", "C:\\web\\FTP_HOME\\SECTION PYTHON")])

    # ============================================================ Outils Windows
    c = "windows"
    g = "Consoles d'administration"
    add(c, "godmode", "GodMode (tous les réglages)", "shell", "shell:::{ED7BA470-8E54-465E-825C-99712043E01C}",
        "Les 200+ réglages du Panneau de configuration dans une seule fenêtre.", "🌟", g)
    add(c, "control", "Panneau de configuration", "file", "control.exe", "Le panneau classique.", "🎛", g)
    add(c, "taskmgr", "Gestionnaire des tâches", "file", "taskmgr.exe", "Processus, performances, démarrage (Ctrl+Maj+Échap).", "📈", g)
    add(c, "services", "Services", "file", "services.msc", "Démarrer/arrêter les services.", "⚙", g)
    add(c, "devmgmt", "Gestionnaire de périphériques", "file", "devmgmt.msc", "Matériel et pilotes.", "🧩", g)
    add(c, "diskmgmt", "Gestion des disques", "file", "diskmgmt.msc", "Partitions et lettres de lecteur.", "💽", g)
    add(c, "compmgmt", "Gestion de l'ordinateur", "file", "compmgmt.msc", "Tout en un : disques, services, journaux.", "🖥", g)
    add(c, "eventvwr", "Observateur d'événements", "file", "eventvwr.msc", "Journaux Windows (erreurs, avertissements).", "📜", g)
    add(c, "regedit", "Éditeur du Registre", "file", "regedit.exe", "Attention : une erreur peut empêcher Windows de démarrer.", "🧬", g,
        confirm=True)
    add(c, "gpedit", "Stratégie de groupe locale", "file", "gpedit.msc", "Réglages avancés (Windows Pro/Entreprise seulement).", "📐", g,
        requires=r"C:\Windows\System32\gpedit.msc")
    add(c, "taskschd", "Planificateur de tâches", "file", "taskschd.msc", "Tâches automatiques.", "⏰", g)
    add(c, "resmon", "Moniteur de ressources", "file", "resmon.exe", "Disque, réseau, mémoire en détail par processus.", "📊", g)
    add(c, "perfmon", "Analyseur de performances", "file", "perfmon.exe", "Compteurs et rapports de performance.", "📉", g)
    add(c, "msconfig", "Configuration du système", "file", "msconfig.exe", "Démarrage sélectif, mode sans échec au prochain démarrage.", "🧰", g)
    add(c, "wintools", "Outils d'administration Windows", "shell", "shell:::{D20EA4E1-3957-11D2-A40B-0C5020524153}",
        "Le dossier de tous les outils d'administration.", "🗄", g)
    add(c, "optionalfeatures", "Fonctionnalités Windows", "file", "optionalfeatures.exe", "Activer .NET 3.5, WSL, Hyper-V, SMB1...", "🧱", g)
    add(c, "appwiz", "Programmes et fonctionnalités", "file", "appwiz.cpl", "Désinstaller un programme (panneau classique).", "🗑", g)
    add(c, "envvars", "Variables d'environnement", "file", "rundll32.exe", "Modifier le PATH et les variables utilisateur.", "🛤", g,
        args="sysdm.cpl,EditEnvironmentVariables")
    add(c, "sysadv", "Propriétés système avancées", "file", "SystemPropertiesAdvanced.exe", "Mémoire virtuelle, performances, démarrage.", "🖥", g)
    add(c, "hosts", "Fichier hosts (Bloc-notes admin)", "file", "notepad.exe", "Bloquer ou rediriger des sites (C:\\Windows\\System32\\drivers\\etc\\hosts).",
        "📝", g, args=r'"%SystemRoot%\System32\drivers\etc\hosts"', admin=True, confirm=True)
    g = "Dossiers spéciaux"
    add(c, "startup_dir", "Dossier Démarrage", "shell", "shell:startup", "Ce qui démarre avec ta session.", "🚀", g)
    add(c, "startup_common", "Démarrage (tous les utilisateurs)", "shell", "shell:common startup", "Démarrage commun.", "🚀", g)
    add(c, "appdata", "AppData (Roaming)", "folder", "%APPDATA%", "Réglages des programmes.", "📂", g)
    add(c, "localappdata", "AppData\\Local", "folder", "%LOCALAPPDATA%", "Données locales des programmes.", "📂", g)
    add(c, "temp", "Dossier Temp", "folder", "%TEMP%", "Fichiers temporaires.", "🗑", g)
    add(c, "sendto", "Envoyer vers", "shell", "shell:sendto", "Ajouter des raccourcis au menu Envoyer vers.", "📨", g)
    add(c, "recent", "Éléments récents", "shell", "shell:recent", "Fichiers ouverts récemment.", "🕘", g)
    add(c, "fonts", "Polices", "shell", "shell:fonts", "Polices installées.", "🔤", g)
    add(c, "appsfolder", "Toutes les applications", "shell", "shell:AppsFolder", "Toutes les applis (y compris Store) dans une fenêtre.", "🔳", g)
    add(c, "recyclebin", "Corbeille", "shell", "shell:RecycleBinFolder", "Ouvrir la corbeille.", "♻", g)
    add(c, "thispc", "Ce PC", "shell", "shell:MyComputerFolder", "Les disques.", "💻", g)
    add(c, "programs_dir", "Menu Démarrer (raccourcis)", "shell", "shell:programs", "Les raccourcis du menu Démarrer.", "📁", g)
    g = "Accessoires"
    add(c, "notepad", "Bloc-notes", "file", "notepad.exe", "Éditeur de texte.", "📝", g)
    add(c, "calc", "Calculatrice", "file", "calc.exe", "Calculatrice (mode programmeur : Alt+5).", "🧮", g)
    add(c, "mspaint", "Paint", "file", "mspaint.exe", "Dessin simple.", "🎨", g)
    add(c, "snip", "Outil Capture", "file", "SnippingTool.exe", "Capture d'écran (ou Win+Maj+S).", "✂", g)
    add(c, "charmap", "Table des caractères", "file", "charmap.exe", "Symboles et caractères spéciaux.", "Ω", g)
    add(c, "magnify", "Loupe", "file", "magnify.exe", "Agrandir l'écran (Win+ +).", "🔍", g)
    add(c, "mstsc", "Bureau à distance", "file", "mstsc.exe", "Se connecter à un autre PC.", "🖧", g)
    add(c, "quickassist", "Assistance rapide", "file", "quickassist.exe", "Aider quelqu'un à distance (ou se faire aider).", "🤝", g)
    add(c, "psr", "Enregistreur d'actions", "file", "psr.exe", "Enregistre tes clics en captures pour expliquer un problème.", "🎬", g,
        requires=r"C:\Windows\System32\psr.exe")

    # ============================================================ Paramètres (ms-settings:)
    c = "parametres"

    def P(gr, sid, name, uri, desc, icon="⚙"):
        add(c, sid, name, "shell", uri, desc, icon, gr)
    gr = "Système"
    P(gr, "home", "Paramètres (accueil)", "ms-settings:", "Ouvre les Paramètres.", "⚙")
    P(gr, "about", "Informations système", "ms-settings:about", "Nom du PC, processeur, mémoire, édition.", "ℹ")
    P(gr, "display", "Affichage", "ms-settings:display", "Résolution, échelle.", "🖥")
    P(gr, "sound", "Son", "ms-settings:sound", "Sorties/entrées audio.", "🔊")
    P(gr, "notifications", "Notifications", "ms-settings:notifications", "Quelles applis peuvent notifier.", "🔔")
    P(gr, "power", "Alimentation et mise en veille", "ms-settings:powersleep", "Délais d'écran et de veille.", "🔋")
    P(gr, "storage", "Stockage", "ms-settings:storagesense", "Espace et nettoyage.", "🗄")
    P(gr, "multitasking", "Multitâche", "ms-settings:multitasking", "Ancrage des fenêtres, bureaux virtuels.", "🪟")
    P(gr, "clipboard", "Presse-papiers (historique)", "ms-settings:clipboard", "Activer Win+V.", "📋")
    P(gr, "remote", "Bureau à distance", "ms-settings:remotedesktop", "Autoriser les connexions à distance (Pro).", "🖧")
    P(gr, "recovery", "Récupération", "ms-settings:recovery", "Réinitialiser, démarrage avancé.", "🚑")
    P(gr, "activation", "Activation", "ms-settings:activation", "Licence Windows.", "✅")
    gr = "Personnalisation"
    P(gr, "background", "Arrière-plan", "ms-settings:personalization-background", "Fond d'écran.", "🖼")
    P(gr, "colors", "Couleurs (mode sombre)", "ms-settings:colors", "Thème clair/sombre, couleur d'accentuation.", "🎨")
    P(gr, "lockscreen", "Écran de verrouillage", "ms-settings:lockscreen", "Image et infos.", "🔒")
    P(gr, "taskbar", "Barre des tâches", "ms-settings:taskbar", "Icônes, position, zone de notification.", "▭")
    P(gr, "start", "Menu Démarrer", "ms-settings:personalization-start", "Contenu du menu Démarrer.", "🟦")
    P(gr, "fonts_set", "Polices", "ms-settings:fonts", "Polices installées.", "🔤")
    gr = "Applications"
    P(gr, "apps", "Applications installées", "ms-settings:appsfeatures", "Désinstaller, réparer.", "📦")
    P(gr, "defaultapps", "Applications par défaut", "ms-settings:defaultapps", "Navigateur, lecteur vidéo par défaut.", "⭐")
    P(gr, "optional", "Fonctionnalités facultatives", "ms-settings:optionalfeatures", "Ajouter des composants Windows.", "🧱")
    P(gr, "startupapps", "Démarrage", "ms-settings:startupapps", "Applications lancées avec Windows.", "🚀")
    gr = "Réseau & appareils"
    P(gr, "network", "État du réseau", "ms-settings:network-status", "Connexion, réinitialisation réseau.", "📡")
    P(gr, "wifi", "Wi-Fi", "ms-settings:network-wifi", "Réseaux sans fil.", "📶")
    P(gr, "proxy", "Proxy", "ms-settings:network-proxy", "Proxy et script de config.", "🧭")
    P(gr, "bluetooth", "Bluetooth et appareils", "ms-settings:bluetooth", "Jumelage.", "🔵")
    P(gr, "printers", "Imprimantes et scanners", "ms-settings:printers", "Gérer les imprimantes.", "🖨")
    P(gr, "mouse", "Souris", "ms-settings:mousetouchpad", "Vitesse, roulette.", "🖱")
    P(gr, "autoplay", "Exécution automatique", "ms-settings:autoplay", "Que faire quand on branche une clé.", "▶")
    P(gr, "usb", "USB", "ms-settings:usb", "Notifications USB.", "🔌")
    gr = "Comptes, heure & langue"
    P(gr, "signin", "Options de connexion", "ms-settings:signinoptions", "PIN, Windows Hello.", "🔢")
    P(gr, "datetime", "Date et heure", "ms-settings:dateandtime", "Fuseau, synchronisation.", "🕐")
    P(gr, "region", "Langue et région", "ms-settings:regionlanguage", "Langues, clavier.", "🌐")
    P(gr, "speech", "Voix", "ms-settings:speech", "Reconnaissance vocale.", "🗣")
    gr = "Confidentialité & sécurité"
    P(gr, "privacy", "Confidentialité", "ms-settings:privacy", "Autorisations Windows.", "🕶")
    P(gr, "webcam", "Caméra (autorisations)", "ms-settings:privacy-webcam", "Applis qui peuvent utiliser la caméra.", "📷")
    P(gr, "micro", "Microphone (autorisations)", "ms-settings:privacy-microphone", "Applis qui peuvent écouter.", "🎙")
    P(gr, "location", "Localisation", "ms-settings:privacy-location", "Applis qui savent où tu es.", "📍")
    P(gr, "defender", "Sécurité Windows", "ms-settings:windowsdefender", "Antivirus, pare-feu.", "🛡")
    P(gr, "update", "Windows Update", "ms-settings:windowsupdate", "Mises à jour.", "⬆")
    P(gr, "update_history", "Historique des mises à jour", "ms-settings:windowsupdate-history", "Mises à jour installées/échouées.", "🧾")
    P(gr, "developers", "Espace développeurs", "ms-settings:developers", "Mode développeur, options de l'Explorateur.", "🧑")
    P(gr, "gamebar", "Game Bar", "ms-settings:gaming-gamebar", "Enregistrement d'écran Win+G.", "🎮")
    P(gr, "easeofaccess", "Accessibilité (affichage)", "ms-settings:easeofaccess-display", "Taille du texte, contrastes.", "♿")

    # ============================================================ Consoles
    c = "consoles"
    g = "Consoles"
    add(c, "cmd", "Invite de commandes (CMD)", "file", "cmd.exe", "Console CMD dans ton dossier personnel.", "⬛", g, cwd="%USERPROFILE%")
    add(c, "cmd_admin", "CMD administrateur", "file", "cmd.exe", "Console CMD avec droits d'administrateur.", "🟥", g, admin=True,
        cwd="%USERPROFILE%")
    add(c, "ps", "PowerShell", "file", "{POWERSHELL}", "Console PowerShell.", "🔷", g, args="-NoLogo", cwd="%USERPROFILE%")
    add(c, "ps_admin", "PowerShell administrateur", "file", "{POWERSHELL}", "PowerShell avec droits d'administrateur.", "🟦", g,
        args="-NoLogo", admin=True, cwd="%USERPROFILE%")
    add(c, "wt", "Windows Terminal", "file", "wt.exe", "Terminal moderne à onglets (s'il est installé).", "🖥", g, requires="wt.exe")
    add(c, "ise", "PowerShell ISE", "file", r"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell_ise.exe",
        "Éditeur de scripts PowerShell avec console.", "📘", g, requires=r"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell_ise.exe")
    add(c, "cmd_web", "CMD dans C:\\web", "file", "cmd.exe", "Console ouverte directement dans C:\\web.", "⬛", g, cwd=r"C:\web")
    add(c, "cmd_projet", "CMD dans Projet Padawan", "file", "cmd.exe", "Console dans le dossier des programmes Padawan.", "⬛", g,
        cwd="{PROJET}")
    add(c, "ps_here", "PowerShell dans un dossier", "ps", "Set-Location -LiteralPath \"{DOSSIER}\"; Get-Location",
        "Ouvre PowerShell dans le dossier choisi.", "📂", g, console="keep", ask=[A("DOSSIER", "Dossier", "folder", "C:\\web")])
    add(c, "python", "Python (console interactive)", "file", "{PYTHON}", "Interpréteur Python 3.14.", "🐍", g, cwd="%USERPROFILE%")
    add(c, "wsl", "WSL (Linux)", "file", "wsl.exe", "Sous-système Linux (si une distribution est installée).", "🐧", g, requires="wsl.exe")

    # ============================================================ Développement
    c = "dev"
    g = "Python & pip"
    add(c, "py_ver", "Versions Python et pip", "cmd", '"{PYTHON}" --version & "{PYTHON}" -m pip --version', "Version installée.", "🐍", g)
    add(c, "pip_list", "Modules installés (pip list)", "cmd", '"{PYTHON}" -m pip list', "Tous les modules Python.", "📃", g)
    add(c, "pip_outdated", "Modules à mettre à jour", "cmd", '"{PYTHON}" -m pip list --outdated', "Modules qui ont une nouvelle version.", "⬆", g)
    add(c, "pip_upgrade_pip", "Mettre pip à jour", "cmd", '"{PYTHON}" -m pip install --upgrade pip', "Dernière version de pip.", "⬆", g,
        console="keep")
    add(c, "pip_install", "Installer un module (pip)", "cmd", '"{PYTHON}" -m pip install --upgrade {NOM}', "pip install d'un module.", "📥", g,
        console="keep", ask=[A("NOM", "Nom du module", "text", "requests")])
    add(c, "pip_show", "Infos d'un module (pip show)", "cmd", '"{PYTHON}" -m pip show {NOM}', "Version, dossier, dépendances.", "🔎", g,
        ask=[A("NOM", "Nom du module", "text", "yt-dlp")])
    add(c, "idle", "IDLE (éditeur Python)", "file", "{PYTHONW}", "L'éditeur fourni avec Python.", "✏", g, args="-m idlelib")
    add(c, "http_server", "Serveur web Python (port 8000)", "cmd", '"{PYTHON}" -m http.server 8000 --directory "{DOSSIER}"',
        "Sert un dossier sur http://localhost:8000 (Ctrl+C pour arrêter).", "🌐", g, console="keep",
        ask=[A("DOSSIER", "Dossier à servir", "folder", "C:\\web")])
    add(c, "venv", "Créer un environnement virtuel", "cmd", '"{PYTHON}" -m venv "{DOSSIER}\\.venv"', "Crée .venv dans le dossier choisi.",
        "📦", g, ask=[A("DOSSIER", "Dossier du projet", "folder")])
    add(c, "site_packages", "Dossier des modules (site-packages)", "cmd",
        '"{PYTHON}" -c "import site, sys; print(sys.executable); print(*site.getsitepackages(), sep=chr(10))"',
        "Où pip installe les modules.", "📂", g)
    add(c, "py_compile", "Vérifier un script Python (compilation)", "cmd", '"{PYTHON}" -m py_compile "{FICHIER}" && echo Aucune erreur de syntaxe.',
        "Détecte les erreurs de syntaxe sans exécuter.", "✔", g, ask=[A("FICHIER", "Script .py", "file")])
    g = "Git"
    add(c, "git_status", "git status d'un dossier", "cmd", 'git -C "{DOSSIER}" status', "État d'un dépôt Git.", "🌿", g,
        requires="git.exe", ask=[A("DOSSIER", "Dépôt", "folder")])
    add(c, "git_log", "git log (20 derniers)", "cmd", 'git -C "{DOSSIER}" log --oneline --graph -20', "Historique récent.", "🌿", g,
        requires="git.exe", ask=[A("DOSSIER", "Dépôt", "folder")])
    add(c, "git_install", "Installer Git (winget)", "cmd", "winget install -e --id Git.Git --accept-package-agreements --accept-source-agreements",
        "Git n'est pas installé sur ce PC : l'installer gratuitement.", "📥", g, console="keep", confirm=True)
    g = "Arduino"
    add(c, "arduino_ide", "Arduino IDE", "file", r"C:\Program Files\Arduino IDE\Arduino IDE.exe", "Programmer tes cartes.", "🔌", g,
        requires=r"C:\Program Files\Arduino IDE\Arduino IDE.exe")
    add(c, "com_ports", "Ports COM (cartes branchées)", "ps",
        "$p = Get-PnpDevice -Class Ports -PresentOnly -ErrorAction SilentlyContinue\n"
        "if ($p) { $p | Format-Table FriendlyName,Status -AutoSize } else { 'Aucun port COM : la carte est-elle branchée (câble de données) ?' }",
        "Sur quel COM est ton Arduino / ESP8266.", "🔍", g)
    add(c, "arduino_dir", "Sketches Arduino", "folder", r"%USERPROFILE%\OneDrive\Documents\Arduino", "Tes sketches.", "📂", g)
    add(c, "arduino_libs", "Bibliothèques Arduino", "folder", r"%USERPROFILE%\OneDrive\Documents\Arduino\libraries", "Librairies installées.", "📚", g)
    add(c, "arduino15", "Cartes et cores (Arduino15)", "folder", r"%LOCALAPPDATA%\Arduino15", "Cores ESP8266/ESP32 installés.", "🧩", g)
    g = "Web local"
    add(c, "php_ini", "php.ini (XAMPP)", "file", "notepad.exe", "Réglages PHP.", "🐘", g, args=r'"C:\xampp\php\php.ini"',
        requires=r"C:\xampp\php\php.ini")
    add(c, "httpd_conf", "httpd.conf (Apache)", "file", "notepad.exe", "Configuration Apache.", "🪶", g,
        args=r'"C:\xampp\apache\conf\httpd.conf"', requires=r"C:\xampp\apache\conf\httpd.conf")

    # ============================================================ Ollama
    c = "ollama"
    g = "Modèles"
    add(c, "list", "Modèles installés (ollama list)", "cmd", "ollama list", "Les modèles sur ce PC et leur taille.", "📚", g)
    add(c, "ps", "Modèles chargés (ollama ps)", "cmd", "ollama ps", "Ce qui occupe la mémoire en ce moment.", "🧠", g)
    add(c, "pull_dolphin", "Télécharger dolphin3:8b", "cmd", "ollama pull dolphin3:8b", "Le modèle de Padawan.", "🐬", g, console="keep")
    add(c, "run_dolphin", "Discuter avec dolphin3:8b", "cmd", "ollama run dolphin3:8b", "Conversation dans la console (/bye pour quitter).",
        "💬", g, console="keep")
    add(c, "pull", "Télécharger un modèle", "cmd", "ollama pull {MODELE}", "Installe un modèle de la bibliothèque Ollama.", "📥", g,
        console="keep", ask=[A("MODELE", "Modèle (ex. llama3.2:3b, qwen2.5:7b)", "text", "llama3.2:3b")])
    add(c, "run", "Discuter avec un modèle", "cmd", "ollama run {MODELE}", "Conversation dans la console.", "💬", g, console="keep",
        ask=[A("MODELE", "Modèle", "text", "dolphin3:8b")])
    add(c, "show", "Infos d'un modèle", "cmd", "ollama show {MODELE}", "Paramètres, contexte, licence.", "ℹ", g,
        ask=[A("MODELE", "Modèle", "text", "dolphin3:8b")])
    add(c, "rm", "Supprimer un modèle", "cmd", "ollama rm {MODELE}", "Libère l'espace d'un modèle.", "🗑", g, danger=True,
        ask=[A("MODELE", "Modèle à supprimer", "text")])
    add(c, "stop", "Décharger un modèle (ollama stop)", "cmd", "ollama stop {MODELE}", "Libère la mémoire sans supprimer.", "⏏", g,
        ask=[A("MODELE", "Modèle", "text", "dolphin3:8b")])
    g = "Service"
    add(c, "version", "Version d'Ollama", "cmd", "ollama --version", "Version installée.", "🏷", g)
    add(c, "api", "Ollama répond-il ? (API)", "ps", "try { Invoke-RestMethod -Uri 'http://localhost:11434/api/version' -TimeoutSec 5 } "
        "catch { 'Ollama ne répond pas sur le port 11434 : lance l''application Ollama.' }", "Vérifie le serveur local (port 11434).", "🩺", g)
    add(c, "restart", "Redémarrer Ollama", "ps",
        "Get-Process -Name 'ollama*' -ErrorAction SilentlyContinue | Stop-Process -Force\nStart-Sleep -Seconds 2\n"
        "Start-Process \"$env:LOCALAPPDATA\\Programs\\Ollama\\ollama app.exe\"\n'Ollama relancé.'",
        "Arrête et relance Ollama (quand il ne répond plus).", "🔁", g, confirm=True,
        requires=r"%LOCALAPPDATA%\Programs\Ollama\ollama app.exe")
    add(c, "models_dir", "Dossier des modèles", "folder", r"%USERPROFILE%\.ollama\models", "Où sont stockés les modèles.", "📂", g)
    add(c, "logs", "Journaux d'Ollama", "folder", r"%LOCALAPPDATA%\Ollama", "server.log et app.log.", "📜", g)
    add(c, "library", "Bibliothèque de modèles (web)", "url", "https://ollama.com/library", "Choisir un modèle.", "🦙", g)

    # ============================================================ yt-dlp & ffmpeg
    c = "media"
    g = "yt-dlp"
    add(c, "ytdlp_ver", "Version de yt-dlp", "cmd", '"{PYTHON}" -m yt_dlp --version', "Version installée.", "🏷", g)
    add(c, "ytdlp_up", "Mettre yt-dlp à jour", "cmd", '"{PYTHON}" -m pip install --upgrade yt-dlp',
        "À faire quand YouTube ou X ne téléchargent plus.", "⬆", g, console="keep")
    add(c, "ytdlp_mp4", "Télécharger une vidéo (MP4 lisible partout)", "cmd",
        '"{PYTHON}" -m yt_dlp -f "bv*[vcodec^=avc1]+ba[ext=m4a]/b[ext=mp4]/b" --merge-output-format mp4 -P "{DOSSIER}" "{URL}"',
        "MP4 H.264 + AAC, lisible par le lecteur Windows.", "📥", g, console="keep",
        ask=[A("URL", "Lien de la vidéo", "text"), A("DOSSIER", "Dossier de destination", "folder", "%USERPROFILE%\\Videos")])
    add(c, "ytdlp_mp3", "Télécharger l'audio en MP3", "cmd",
        '"{PYTHON}" -m yt_dlp -x --audio-format mp3 --audio-quality 0 -P "{DOSSIER}" "{URL}"',
        "Extrait la bande-son en MP3 (ffmpeg requis).", "🎵", g, console="keep",
        ask=[A("URL", "Lien", "text"), A("DOSSIER", "Dossier de destination", "folder", "%USERPROFILE%\\Music")])
    add(c, "ytdlp_subs", "Vidéo + sous-titres FR/EN", "cmd",
        '"{PYTHON}" -m yt_dlp -f "bv*[vcodec^=avc1]+ba[ext=m4a]/b" --merge-output-format mp4 --write-subs --write-auto-subs '
        '--sub-langs "fr.*,en.*" --convert-subs srt -P "{DOSSIER}" "{URL}"',
        "Télécharge la vidéo et ses sous-titres .srt.", "💬", g, console="keep",
        ask=[A("URL", "Lien", "text"), A("DOSSIER", "Dossier", "folder", "%USERPROFILE%\\Videos")])
    add(c, "ytdlp_formats", "Lister les formats disponibles", "cmd", '"{PYTHON}" -m yt_dlp -F "{URL}"', "Toutes les qualités proposées.",
        "📋", g, ask=[A("URL", "Lien", "text")])
    add(c, "ytdlp_playlist", "Playlist entière en MP3", "cmd",
        '"{PYTHON}" -m yt_dlp -x --audio-format mp3 --yes-playlist -P "{DOSSIER}" "{URL}"', "Toute une playlist en audio.", "📻", g,
        console="keep", ask=[A("URL", "Lien de la playlist", "text"), A("DOSSIER", "Dossier", "folder", "%USERPROFILE%\\Music")])
    g = "ffmpeg"
    add(c, "ff_ver", "Version de ffmpeg", "cmd", "ffmpeg -hide_banner -version", "Version et options de compilation.", "🏷", g)
    add(c, "ff_probe", "Infos d'un fichier média (ffprobe)", "cmd", 'ffprobe -hide_banner "{FICHIER}"',
        "Codec, durée, résolution, pistes audio.", "🔎", g, ask=[A("FICHIER", "Fichier vidéo ou audio", "file")])
    add(c, "ff_h264", "Convertir en MP4 H.264", "cmd",
        'ffmpeg -hide_banner -i "{FICHIER}" -c:v libx264 -crf 20 -preset medium -c:a aac -b:a 192k "{FICHIER}.h264.mp4"',
        "Rend une vidéo (AV1, MKV, WebM...) lisible partout.", "🎞", g, console="keep", ask=[A("FICHIER", "Vidéo", "file")])
    add(c, "ff_mp3", "Extraire l'audio en MP3", "cmd", 'ffmpeg -hide_banner -i "{FICHIER}" -vn -q:a 2 "{FICHIER}.mp3"',
        "Garde seulement le son.", "🎵", g, console="keep", ask=[A("FICHIER", "Vidéo", "file")])
    add(c, "ff_cut", "Couper un extrait (sans réencoder)", "cmd",
        'ffmpeg -hide_banner -ss {DEBUT} -i "{FICHIER}" -t {DUREE} -c copy "{FICHIER}.extrait.mp4"',
        "Extrait rapide à partir d'un temps (hh:mm:ss) et d'une durée en secondes.", "✂", g, console="keep",
        ask=[A("FICHIER", "Vidéo", "file"), A("DEBUT", "Début (hh:mm:ss)", "text", "00:00:10"), A("DUREE", "Durée (secondes)", "text", "30")])
    add(c, "ff_720", "Réduire en 720p", "cmd",
        'ffmpeg -hide_banner -i "{FICHIER}" -vf scale=-2:720 -c:v libx264 -crf 24 -preset medium -c:a aac -b:a 128k "{FICHIER}.720p.mp4"',
        "Fichier plus léger pour partager.", "📉", g, console="keep", ask=[A("FICHIER", "Vidéo", "file")])
    add(c, "ff_gif", "Vidéo vers GIF animé", "cmd",
        'ffmpeg -hide_banner -i "{FICHIER}" -vf "fps=12,scale=480:-1:flags=lanczos" "{FICHIER}.gif"', "GIF de 480 px de large.", "🎞", g,
        console="keep", ask=[A("FICHIER", "Vidéo (courte)", "file")])
    add(c, "ff_frame", "Capture d'image à 5 s", "cmd", 'ffmpeg -hide_banner -ss 5 -i "{FICHIER}" -frames:v 1 "{FICHIER}.jpg"',
        "Une image JPG tirée de la vidéo.", "📸", g, ask=[A("FICHIER", "Vidéo", "file")])
    add(c, "ff_screen", "Enregistrer l'écran (q pour arrêter)", "cmd",
        'ffmpeg -hide_banner -f gdigrab -framerate 30 -i desktop -c:v libx264 -preset ultrafast -pix_fmt yuv420p "%USERPROFILE%\\Videos\\ecran_%RANDOM%.mp4"',
        "Enregistre tout l'écran dans Vidéos (appuie sur q dans la console pour arrêter).", "🎥", g, console="keep")
    add(c, "ffplay", "Lire avec ffplay", "cmd", 'ffplay -hide_banner -autoexit "{FICHIER}"', "Lecteur minimal de ffmpeg.", "▶", g,
        console="hidden", ask=[A("FICHIER", "Fichier", "file")])
    add(c, "archives", "Dossier ARCHIVEUR", "folder", r"C:\web\FTP_HOME\ARCHIVEUR", "Tes archives.", "🗃", g)

    # ============================================================ Raccourcis clavier (aide-mémoire)
    c = "clavier"
    keys = [
        ("Fenêtres", "Win+D", "Afficher le Bureau / revenir"),
        ("Fenêtres", "Win+E", "Ouvrir l'Explorateur"),
        ("Fenêtres", "Win+Flèches", "Ancrer la fenêtre à gauche/droite, agrandir, réduire"),
        ("Fenêtres", "Win+Maj+Gauche/Droite", "Envoyer la fenêtre sur l'autre écran"),
        ("Fenêtres", "Win+M", "Réduire toutes les fenêtres (Win+Maj+M pour restaurer)"),
        ("Fenêtres", "Alt+Tab", "Passer d'une fenêtre à l'autre"),
        ("Fenêtres", "Win+Tab", "Vue des tâches et bureaux virtuels"),
        ("Fenêtres", "Win+Ctrl+D", "Nouveau bureau virtuel"),
        ("Fenêtres", "Win+Ctrl+Gauche/Droite", "Changer de bureau virtuel"),
        ("Fenêtres", "Win+Ctrl+F4", "Fermer le bureau virtuel actuel"),
        ("Fenêtres", "Alt+F4", "Fermer la fenêtre (sur le Bureau : menu Arrêter)"),
        ("Fenêtres", "Win+1..9", "Lancer/afficher l'appli épinglée n° 1 à 9 de la barre des tâches"),
        ("Système", "Ctrl+Maj+Échap", "Gestionnaire des tâches directement"),
        ("Système", "Win+L", "Verrouiller la session"),
        ("Système", "Win+X", "Menu rapide (Gestionnaire de périphériques, PowerShell admin...)"),
        ("Système", "Win+R", "Exécuter (taper une commande)"),
        ("Système", "Win+I", "Paramètres"),
        ("Système", "Win+Pause", "Informations système"),
        ("Système", "Win+Ctrl+Maj+B", "Redémarrer le pilote graphique (écran noir ou figé)"),
        ("Système", "Win+P", "Projeter : dupliquer/étendre l'écran"),
        ("Système", "Win+A", "Centre de notifications / paramètres rapides"),
        ("Captures & presse-papiers", "Win+Maj+S", "Capture d'une zone de l'écran"),
        ("Captures & presse-papiers", "Win+ImprÉcran", "Capture plein écran enregistrée dans Images\\Captures d'écran"),
        ("Captures & presse-papiers", "Alt+ImprÉcran", "Capture de la fenêtre active dans le presse-papiers"),
        ("Captures & presse-papiers", "Win+V", "Historique du presse-papiers (à activer une fois)"),
        ("Captures & presse-papiers", "Win+Alt+R", "Enregistrer une vidéo de l'appli (Game Bar)"),
        ("Captures & presse-papiers", "Win+G", "Game Bar (enregistrement, performances)"),
        ("Saisie", "Win+.", "Emojis et symboles"),
        ("Saisie", "Win+H", "Dictée vocale"),
        ("Saisie", "Win+Espace", "Changer de langue de clavier"),
        ("Saisie", "Ctrl+Maj+V", "Coller sans mise en forme (dans beaucoup d'applis)"),
        ("Explorateur", "F2", "Renommer"),
        ("Explorateur", "Alt+Entrée", "Propriétés"),
        ("Explorateur", "Ctrl+Maj+N", "Nouveau dossier"),
        ("Explorateur", "Alt+Haut", "Dossier parent"),
        ("Explorateur", "Ctrl+L", "Aller à la barre d'adresse (taper cmd pour une console ici)"),
        ("Explorateur", "Maj+Suppr", "Supprimer définitivement (sans corbeille) ⚠"),
        ("Explorateur", "Maj+clic droit", "Menu étendu : « Copier en tant que chemin d'accès », PowerShell ici"),
        ("Navigateur", "Ctrl+Maj+T", "Rouvrir l'onglet fermé"),
        ("Navigateur", "Ctrl+L", "Sélectionner l'adresse"),
        ("Navigateur", "Ctrl+Maj+Suppr", "Effacer l'historique et le cache"),
        ("Navigateur", "Ctrl+F5", "Recharger sans le cache"),
        ("Navigateur", "Ctrl+Molette", "Zoom de la page (Ctrl+0 : 100 %)"),
        ("Accessibilité", "Win+ +", "Loupe (Win+Échap pour quitter)"),
        ("Accessibilité", "Win+Ctrl+Entrée", "Narrateur"),
        ("Accessibilité", "Win+Ctrl+C", "Filtres de couleur"),
        ("Arsenal", "Ctrl+Espace", "Palette de lancement rapide (Ctrl+Alt+Espace partout si activé)"),
        ("Arsenal", "Ctrl+F", "Rechercher (ou tape directement)"),
        ("Arsenal", "Entrée / Ctrl+Entrée", "Lancer / lancer en administrateur"),
        ("Arsenal", "F2 / Ctrl+E", "Renommer / modifier l'entrée"),
        ("Arsenal", "Ctrl+Z / Ctrl+Y", "Annuler / rétablir"),
    ]
    for i, (gr, k, d) in enumerate(keys):
        add(c, f"k{i:02d}", k, "copy", k, d, "⌨", gr, tags=["clavier"])

    # ============================================================ Aide-mémoire (copier seulement)
    c = "memo"
    memo = [
        ("Copie & fichiers", "robocopy — copie avec reprise", 'robocopy "C:\\source" "D:\\dest" /E /Z /R:2 /W:2 /MT:8 /LOG:"%USERPROFILE%\\robocopy.log" /TEE',
         "Copie un dossier complet, reprend après coupure, journal. /MT:8 = 8 fichiers à la fois."),
        ("Copie & fichiers", "robocopy — miroir ⚠", 'robocopy "C:\\source" "D:\\dest" /MIR /R:2 /W:2',
         "Rend la destination identique : SUPPRIME ce qui n'est plus dans la source. Teste d'abord avec /L."),
        ("Copie & fichiers", "robocopy — simulation (/L)", 'robocopy "C:\\source" "D:\\dest" /MIR /L', "Montre ce qui serait copié/supprimé, sans rien faire."),
        ("Copie & fichiers", "xcopy — copier un arbre", 'xcopy "C:\\source" "D:\\dest\\" /E /H /C /I /Y', "Copie simple avec fichiers cachés."),
        ("Copie & fichiers", "Lister tous les fichiers d'un type", 'dir /s /b "C:\\dossier\\*.mp4"', "Chemins complets, sous-dossiers compris."),
        ("Copie & fichiers", "Chercher du texte dans des fichiers", 'findstr /s /i /n "mot" "C:\\dossier\\*.txt"', "Comme grep : fichier, ligne, texte."),
        ("Copie & fichiers", "Chercher du texte (PowerShell)", 'Get-ChildItem C:\\dossier -Recurse -Include *.py,*.php | Select-String "mot"', "Recherche récursive avec numéros de ligne."),
        ("Copie & fichiers", "Comparer deux fichiers", 'fc /b "fichier1" "fichier2"', "Comparaison binaire (fc /n pour du texte)."),
        ("Copie & fichiers", "Effacer les fichiers de plus de 30 jours ⚠", 'forfiles /p "C:\\dossier" /s /d -30 /c "cmd /c del @path"', "Nettoyage par date (vérifier le dossier !)."),
        ("Copie & fichiers", "Lien symbolique de dossier", 'mklink /D "C:\\lien" "D:\\vrai_dossier"', "Un dossier qui pointe ailleurs (admin)."),
        ("Copie & fichiers", "Jonction de dossier", 'mklink /J "C:\\lien" "D:\\vrai_dossier"', "Comme un lien, sans admin."),
        ("Copie & fichiers", "Compresser en ZIP (PowerShell)", 'Compress-Archive -Path "C:\\dossier\\*" -DestinationPath "C:\\archive.zip"', "Créer un ZIP."),
        ("Copie & fichiers", "Décompresser un ZIP", 'Expand-Archive -Path "C:\\archive.zip" -DestinationPath "C:\\dest"', "Extraire un ZIP."),
        ("Copie & fichiers", "ZIP avec tar (CMD)", 'tar -a -c -f archive.zip dossier', "tar est inclus dans Windows 10/11."),
        ("Copie & fichiers", "Suivre un journal en direct (tail -f)", 'Get-Content "C:\\xampp\\apache\\logs\\error.log" -Wait -Tail 50', "Affiche les nouvelles lignes au fil de l'eau."),
        ("Droits & attributs", "attrib — rendre visibles les fichiers", 'attrib -h -s -r /s /d "E:\\*"', "Clé USB « vide » après un virus."),
        ("Droits & attributs", "takeown — devenir propriétaire", 'takeown /f "C:\\dossier" /r /d o', "Reprendre un dossier « accès refusé » (admin ; /d o en français)."),
        ("Droits & attributs", "icacls — donner le contrôle total", 'icacls "C:\\dossier" /grant "%USERNAME%":F /t /c', "Après takeown."),
        ("Droits & attributs", "icacls — réinitialiser les droits", 'icacls "C:\\dossier" /reset /t /c /q', "Remet les autorisations héritées par défaut."),
        ("Droits & attributs", "Débloquer des scripts téléchargés", 'Get-ChildItem "C:\\dossier" -Recurse | Unblock-File', "Enlève la marque « provenant d'Internet »."),
        ("Droits & attributs", "Autoriser les scripts PowerShell", 'Set-ExecutionPolicy -Scope CurrentUser RemoteSigned', "Permet tes propres .ps1."),
        ("Processus & services", "tasklist filtré", 'tasklist /fi "imagename eq pythonw.exe"', "Les processus d'un programme."),
        ("Processus & services", "taskkill par nom", 'taskkill /f /im notepad.exe', "Fermer de force."),
        ("Processus & services", "taskkill arbre complet", 'taskkill /f /t /pid 1234', "Ferme un processus et ses enfants."),
        ("Processus & services", "sc — état d'un service", 'sc query Spooler', "État d'un service."),
        ("Processus & services", "sc — désactiver un service ⚠", 'sc config NomService start= disabled', "L'espace après start= est obligatoire."),
        ("Processus & services", "Tâches planifiées détaillées", 'schtasks /query /fo LIST /v', "Toutes les tâches avec leurs commandes."),
        ("wmic vers PowerShell", "wmic bios get serialnumber", 'Get-CimInstance Win32_BIOS | Select-Object SerialNumber', "wmic est retiré de Windows 11 : équivalent PowerShell."),
        ("wmic vers PowerShell", "wmic cpu get name", 'Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores', "Processeur."),
        ("wmic vers PowerShell", "wmic diskdrive get status", 'Get-CimInstance Win32_DiskDrive | Select-Object Model,Status,Size', "Disques."),
        ("wmic vers PowerShell", "wmic product get name", 'Get-Package | Select-Object Name,Version', "Logiciels (plus rapide que Win32_Product)."),
        ("wmic vers PowerShell", "wmic process list brief", 'Get-CimInstance Win32_Process | Select-Object ProcessId,Name,CommandLine', "Processus avec leur ligne de commande."),
        ("wmic vers PowerShell", "wmic os get lastbootuptime", '(Get-CimInstance Win32_OperatingSystem).LastBootUpTime', "Dernier démarrage."),
        ("Empreintes", "Get-FileHash (SHA256)", 'Get-FileHash "C:\\fichier.iso" -Algorithm SHA256', "Comparer avec l'empreinte du site."),
        ("Empreintes", "certutil (MD5/SHA1/SHA256)", 'certutil -hashfile "C:\\fichier.iso" SHA256', "Même chose en CMD."),
        ("Réseau", "Afficher le cache DNS", 'ipconfig /displaydns', "Noms déjà résolus."),
        ("Réseau", "Tester un port", 'Test-NetConnection marcsevigny.ca -Port 443', "TcpTestSucceeded : True = ouvert."),
        ("Réseau", "Télécharger un fichier (curl)", 'curl -L -o fichier.zip "https://exemple.com/fichier.zip"', "curl est inclus dans Windows 10/11."),
        ("Réseau", "Mapper un lecteur réseau", 'net use Z: "\\\\serveur\\partage" /persistent:yes', "Lecteur réseau permanent."),
        ("Réseau", "SSH vers un serveur", 'ssh utilisateur@serveur', "Client OpenSSH intégré."),
        ("Réseau", "Copier par SSH (scp)", 'scp "C:\\fichier.txt" utilisateur@serveur:/home/utilisateur/', "Transfert sécurisé."),
        ("Système", "BIOS/UEFI directement", 'shutdown /r /fw /t 0', "Redémarre dans le micrologiciel (admin)."),
        ("Système", "Démarrage avancé", 'shutdown /r /o /t 0', "Options de récupération."),
        ("Système", "Menu de démarrage", 'bcdedit /enum', "Entrées de démarrage (admin)."),
        ("Système", "Journal système (texte)", 'wevtutil qe System /c:20 /f:text /rd:true', "20 derniers événements."),
        ("Système", "Exporter la liste de logiciels (winget)", 'winget export -o "%USERPROFILE%\\apps.json"', "Pour réinstaller tout d'un coup."),
        ("Système", "Réinstaller depuis la liste (winget)", 'winget import -i "%USERPROFILE%\\apps.json"', "Après une réinstallation de Windows."),
        ("Système", "Installer WSL (Linux)", 'wsl --install', "Ubuntu par défaut (admin, redémarrage)."),
        ("Système", "setx — attention ⚠", 'setx NOM "valeur"', "Ne pas utiliser pour le PATH : setx tronque à 1024 caractères ! Utiliser Variables d'environnement."),
        ("Console", "Couleurs Norton dans CMD", 'color 1E', "Fond bleu, texte jaune (color 1F : blanc)."),
        ("Console", "Console en UTF-8", 'chcp 65001', "Accents corrects dans CMD."),
        ("Console", "Historique des commandes", 'doskey /history', "Commandes tapées dans cette console (F7 : liste)."),
        ("Console", "Où est un programme", 'where python', "Chemin de chaque exécutable trouvé dans le PATH."),
        ("Console", "Mesurer la durée d'une commande", 'Measure-Command { Get-ChildItem C:\\web -Recurse }', "Temps d'exécution."),
        ("Console", "Aide en ligne d'une commande PowerShell", 'Get-Help Get-ChildItem -Online', "Ouvre la doc Microsoft."),
        ("Console", "Ouvrir l'Explorateur ici", 'start .', "Depuis CMD : ouvre le dossier courant."),
        ("Python", "Installer/mettre à jour un module", 'python -m pip install --upgrade nom_module', "Toujours passer par python -m pip."),
        ("Python", "Geler les dépendances", 'python -m pip freeze > requirements.txt', "Liste exacte des modules."),
        ("Python", "Installer depuis requirements", 'python -m pip install -r requirements.txt', "Réinstaller les dépendances."),
    ]
    for i, (gr, n, cmd, d) in enumerate(memo):
        add(c, f"m{i:02d}", n, "copy", cmd, d, "📋", gr, tags=["aide-mémoire"])

    return cats, E


# ================================================================ interface : utilitaires
EMOJI_SETS = [
    ("Outils", "⚡🧰🔧🔨🛠⚙🔩🧲🔌🔋💡🧪🧬🔬🔭📡🛰"),
    ("Sécurité", "🛡🔒🔓🔑🗝🚨⚠⛔🚫✅❌❎☑🔐👁🕵🦠🧯"),
    ("Fichiers", "📁📂🗂🗃🗄📄📃📜📝📋📌📎🖇💾💿📀🗑♻📦🗜"),
    ("Ordinateur", "💻🖥⌨🖱🖨🖲💽📱☎📞📟📠🔊🔈🔇🎧🎙📷🎥"),
    ("Web", "🌐🌍🌎🌏🔗📧✉📨📩📬📰🗞🛒💳🏦🏠🏛🗺🧭"),
    ("Médias", "🎬🎞📺📻🎵🎶🎤🎮🕹🖼🎨📸🎥▶⏸⏹⏺⏭🔁"),
    ("Symboles", "⭐🌟✨🔥💥💧❄☀🌙⚪🔴🟠🟡🟢🔵🟣⚫⬛🟦"),
    ("Divers", "🤖🐍🦙🐬🧠💬🗨📚📖🎓🧾🧮📈📉📊⏰⏱🕘📅🚀"),
]


def ui_color(key: str) -> str:
    return C.get(key, "#000000")


def apply_styles(root) -> None:
    st = ttk.Style(root)
    try:
        st.theme_use("clam")
    except tk.TclError:
        pass
    lh = tkfont.Font(font=fnt("ArsUI")).metrics("linespace")
    st.configure(".", background=C["BG"], foreground=C["FG"], fieldbackground=C["ENTRY_BG"], font=fnt("ArsUI"),
                 bordercolor=C["LINE"], lightcolor=C["PANEL"], darkcolor=C["PANEL"], troughcolor=C["PANEL"],
                 selectbackground=C["SEL"], selectforeground=C["ON_SEL"], insertcolor=C["ENTRY_FG"])
    st.configure("TFrame", background=C["BG"])
    st.configure("Panel.TFrame", background=C["PANEL"])
    st.configure("TLabel", background=C["BG"], foreground=C["FG"])
    st.configure("Treeview", background=C["CARD"], fieldbackground=C["CARD"], foreground=C["TEXT"],
                 rowheight=lh + 8, font=fnt("ArsUI"), borderwidth=0)
    st.map("Treeview", background=[("selected", C["SEL"])], foreground=[("selected", C["ON_SEL"])])
    st.configure("Treeview.Heading", background=C["PANEL"], foreground=C["HI"], font=fnt("ArsHead"), relief="flat")
    st.map("Treeview.Heading", background=[("active", C["HOVER"])])
    st.configure("Cat.Treeview", background=C["PANEL"], fieldbackground=C["PANEL"], foreground=C["FG"], rowheight=lh + 10)
    st.configure("TCombobox", fieldbackground=C["ENTRY_BG"], background=C["BTN"], foreground=C["ENTRY_FG"],
                 arrowcolor=C["FG"], selectbackground=C["ENTRY_BG"], selectforeground=C["ENTRY_FG"])
    st.map("TCombobox", fieldbackground=[("readonly", C["ENTRY_BG"])], foreground=[("readonly", C["ENTRY_FG"])],
           selectbackground=[("readonly", C["ENTRY_BG"])], selectforeground=[("readonly", C["ENTRY_FG"])])
    root.option_add("*TCombobox*Listbox.background", C["ENTRY_BG"])
    root.option_add("*TCombobox*Listbox.foreground", C["ENTRY_FG"])
    root.option_add("*TCombobox*Listbox.selectBackground", C["SEL"])
    root.option_add("*TCombobox*Listbox.selectForeground", C["ON_SEL"])
    root.option_add("*TCombobox*Listbox.font", fnt("ArsUI"))
    for orient in ("Vertical", "Horizontal"):
        st.configure(f"{orient}.TScrollbar", background=C["BTN"], troughcolor=C["PANEL"], arrowcolor=C["FG"],
                     bordercolor=C["LINE"], gripcount=0, arrowsize=16)
        st.map(f"{orient}.TScrollbar", background=[("active", C["HOVER"])])
    st.configure("TCheckbutton", background=C["BG"], foreground=C["TEXT"], indicatorbackground=C["ENTRY_BG"],
                 indicatorforeground=C["HI"])
    st.map("TCheckbutton", background=[("active", C["BG"])], foreground=[("active", C["HI"])])


def mk_button(parent, text: str, cmd: Callable, kind: str = "", width: int = 0, tip: str = "", font_name: str = "ArsUI"):
    """Bouton plat aux couleurs du theme. kind : '' | 'accent' | 'danger' | 'ghost'."""
    bg, fg, abg, afg = C["BTN"], C["BTN_FG"], C["HI"], C["ON_HI"]
    if kind == "accent":
        bg, fg, abg, afg = C["HI"], C["ON_HI"], C["HI_ACT"], C["ON_HI"]
    elif kind == "danger":
        bg, fg = C["BTN"], C["ERR"]
    elif kind == "ghost":
        bg = parent.cget("bg") if "bg" in parent.keys() else C["BG"]
    b = tk.Button(parent, text=text, command=cmd, bg=bg, fg=fg, activebackground=abg, activeforeground=afg,
                  relief="flat", bd=0, highlightthickness=1, highlightbackground=C["LINE"], padx=10, pady=3,
                  font=fnt(font_name if kind != "accent" else "ArsUIB"), cursor="hand2", disabledforeground=C["DISABLED"])
    if width:
        b.configure(width=width)
    b.bind("<Enter>", lambda _e: b.configure(bg=abg, fg=afg) if str(b["state"]) != "disabled" else None)
    b.bind("<Leave>", lambda _e: b.configure(bg=bg, fg=fg))
    if tip:
        Tooltip(b, tip)
    return b


def mk_entry(parent, var=None, width: int = 30, font_name: str = "ArsUI"):
    return tk.Entry(parent, textvariable=var, width=width, bg=C["ENTRY_BG"], fg=C["ENTRY_FG"], insertbackground=C["HI"],
                    relief="flat", highlightthickness=1, highlightbackground=C["LINE"], highlightcolor=C["HI"],
                    font=fnt(font_name), selectbackground=C["SEL"], selectforeground=C["ON_SEL"],
                    disabledbackground=C["PANEL"], readonlybackground=C["ENTRY_BG"])


def mk_text(parent, height: int = 4, width: int = 40, font_name: str = "ArsMono", wrap: str = "word"):
    return tk.Text(parent, height=height, width=width, bg=C["ENTRY_BG"], fg=C["ENTRY_FG"], insertbackground=C["HI"],
                   relief="flat", highlightthickness=1, highlightbackground=C["LINE"], highlightcolor=C["HI"],
                   font=fnt(font_name), wrap=wrap, selectbackground=C["SEL"], selectforeground=C["ON_SEL"], undo=True)


def mk_label(parent, text: str = "", key: str = "FG", font_name: str = "ArsUI", bg: str = "", **kw):
    return tk.Label(parent, text=text, fg=C[key], bg=bg or parent.cget("bg"), font=fnt(font_name), **kw)


def mk_check(parent, text: str, var, bg: str = ""):
    b = bg or parent.cget("bg")
    return tk.Checkbutton(parent, text=text, variable=var, bg=b, fg=C["TEXT"], selectcolor=C["ENTRY_BG"],
                          activebackground=b, activeforeground=C["HI"], font=fnt("ArsUI"), anchor="w",
                          highlightthickness=0, bd=0)


def style_menu(m) -> None:
    m.configure(bg=C["PANEL"], fg=C["TEXT"], activebackground=C["SEL"], activeforeground=C["ON_SEL"],
                font=fnt("ArsUI"), tearoff=0, relief="flat", bd=1, selectcolor=C["HI"],
                disabledforeground=C["DISABLED"])


def new_menu(parent):
    m = tk.Menu(parent, tearoff=0)
    style_menu(m)
    return m


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
        x = self.w.winfo_pointerx() + 14
        y = self.w.winfo_pointery() + 18
        self.tip = show_tip(self.w, txt, x, y)

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
    lab = tk.Label(tw, text=txt, bg=C["TIP_BG"], fg=C["TIP_FG"], font=fnt("ArsSM"), justify="left",
                   relief="solid", bd=1, padx=6, pady=3, wraplength=520)
    lab.pack()
    tw.update_idletasks()
    sw, sh = widget.winfo_screenwidth(), widget.winfo_screenheight()
    w, h = tw.winfo_reqwidth(), tw.winfo_reqheight()
    x = min(x, sw - w - 4)
    if y + h > sh - 4:
        y = y - h - 30
    tw.wm_geometry(f"+{max(0, x)}+{max(0, y)}")
    return tw


class ScrollFrame(tk.Frame):
    """Cadre defilant vertical (formulaires longs : l'editeur tient en 1024x576)."""

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
        self.bind_all_wheel(self.canvas)

    def bind_all_wheel(self, w):
        w.bind("<Enter>", lambda _e: w.bind_all("<MouseWheel>", self._wheel), add="+")
        w.bind("<Leave>", lambda _e: w.unbind_all("<MouseWheel>"), add="+")

    def _wheel(self, e):
        if self.inner.winfo_reqheight() > self.canvas.winfo_height():
            self.canvas.yview_scroll(int(-e.delta / 120) * 3, "units")


def work_area(widget) -> Tuple[int, int, int, int]:
    """Zone de travail (ecran moins la barre des taches) en pixels Tk."""
    if IS_WIN:
        try:
            r = wintypes.RECT()
            if ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(r), 0):
                return r.left, r.top, r.right - r.left, r.bottom - r.top
        except Exception:
            pass
    return 0, 0, widget.winfo_screenwidth(), widget.winfo_screenheight()


class Dialog(tk.Toplevel):
    """Fenetre modale centree sur le parent, aux couleurs du theme, taille bornee a l'ecran."""

    def __init__(self, parent, title: str, w: int = 640, h: int = 420, resizable: bool = True, modal: bool = True):
        super().__init__(parent)
        self.parent = parent
        self.result = None
        self.withdraw()
        self.title(title)
        self.configure(bg=C["BG"])
        try:
            ico = os.path.join(BASE, "arsenal1.ico")
            if os.path.isfile(ico):
                self.iconbitmap(ico)
        except tk.TclError:
            pass
        top = parent.winfo_toplevel()
        pw, ph = top.winfo_width(), top.winfo_height()
        if pw < 200:
            pw, ph = top.winfo_screenwidth(), top.winfo_screenheight()
        wx, wy, ww, wh = work_area(self)
        w = min(w, pw - 30, ww - 30)
        h = min(h, ph - 40, wh - 50)
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
        (focus or self).focus_set()
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


# ================================================================ boites de dialogue
class EmojiPicker(Dialog):
    def __init__(self, parent, current: str = ""):
        super().__init__(parent, "Choisir un emoji", 600, 470)
        self.var = tk.StringVar(value=current)
        top = tk.Frame(self, bg=C["BG"])
        top.pack(fill="x", padx=10, pady=(10, 4))
        mk_label(top, "Emoji :", "HI", "ArsUIB").pack(side="left")
        e = mk_entry(top, self.var, 6, "ArsEmojiSM")
        e.pack(side="left", padx=6)
        mk_label(top, "Clique un symbole, ou Win+. pour tous les emojis.", "DIM", "ArsSM").pack(side="left", padx=8)
        self.button_bar([("Aucun", self._none, ""), ("Annuler", self.cancel, ""), ("OK", self._ok, "accent")])
        sf = ScrollFrame(self)
        sf.pack(fill="both", expand=True, padx=10, pady=4)
        for gname, chars in EMOJI_SETS:
            mk_label(sf.inner, gname, "HI", "ArsHead").pack(anchor="w", pady=(6, 0))
            row = tk.Frame(sf.inner, bg=C["BG"])
            row.pack(anchor="w")
            items = [ch for ch in self._split(chars)]
            for i, ch in enumerate(items):
                b = tk.Button(row, text=ch, font=fnt("ArsEmojiSM"), width=2, relief="flat", bg=C["CARD"], fg=C["TEXT"],
                              activebackground=C["SEL"], cursor="hand2", command=lambda c=ch: self._pick(c))
                b.grid(row=i // 12, column=i % 12, padx=1, pady=1)
        self.bind("<Return>", lambda _e: self._ok())
        self.show(e)

    @staticmethod
    def _split(s: str) -> List[str]:
        out: List[str] = []
        for ch in s:
            if ch in "\ufe0f\u200d" and out:
                out[-1] += ch
            else:
                out.append(ch)
        return out

    def _pick(self, ch):
        self.result = ch
        self.destroy()

    def _none(self):
        self.result = ""
        self.destroy()

    def _ok(self):
        self.result = self.var.get().strip()
        self.destroy()

    def cancel(self):
        self.result = None
        self.destroy()


class CategoryDialog(Dialog):
    def __init__(self, parent, title: str, name: str = "", icon: str = "📂"):
        super().__init__(parent, title, 560, 230, resizable=False)
        f = tk.Frame(self, bg=C["BG"])
        f.pack(fill="both", expand=True, padx=14, pady=12)
        self.v_name = tk.StringVar(value=name)
        self.v_icon = tk.StringVar(value=icon)
        mk_label(f, "Nom de la catégorie :", "HI", "ArsUIB").grid(row=0, column=0, sticky="w", pady=4)
        en = mk_entry(f, self.v_name, 30)
        en.grid(row=0, column=1, columnspan=2, sticky="we", padx=6)
        mk_label(f, "Emoji :", "HI", "ArsUIB").grid(row=1, column=0, sticky="w", pady=4)
        mk_entry(f, self.v_icon, 5, "ArsEmojiSM").grid(row=1, column=1, sticky="w", padx=6)
        mk_button(f, "Choisir…", self._pick).grid(row=1, column=2, sticky="w")
        f.columnconfigure(1, weight=1)
        self.button_bar([("Annuler", self.cancel, ""), ("OK", self._ok, "accent")])
        self.bind("<Return>", lambda _e: self._ok())
        self.show(en)
        en.select_range(0, "end")

    def _pick(self):
        r = EmojiPicker(self, self.v_icon.get()).wait()
        if r is not None:
            self.v_icon.set(r or "📂")

    def _ok(self):
        n = self.v_name.get().strip()
        if not n:
            messagebox.showwarning(APP_NAME, "Donne un nom à la catégorie.", parent=self)
            return
        self.result = (n, self.v_icon.get().strip() or "📂")
        self.destroy()


class ChoiceDialog(Dialog):
    """Choisir une categorie (deplacer) ou une option dans une liste."""

    def __init__(self, parent, title: str, prompt: str, choices: List[Tuple[str, str]], current: str = ""):
        super().__init__(parent, title, 520, 480)
        mk_label(self, prompt, "HI", "ArsUIB", wraplength=480, justify="left").pack(anchor="w", padx=12, pady=(10, 4))
        self.button_bar([("Annuler", self.cancel, ""), ("OK", self._ok, "accent")])
        fr = tk.Frame(self, bg=C["BG"])
        fr.pack(fill="both", expand=True, padx=12, pady=4)
        self.lb = tk.Listbox(fr, bg=C["CARD"], fg=C["TEXT"], selectbackground=C["SEL"], selectforeground=C["ON_SEL"],
                             font=fnt("ArsUI"), activestyle="none", relief="flat", highlightthickness=1,
                             highlightbackground=C["LINE"])
        sb = ttk.Scrollbar(fr, orient="vertical", command=self.lb.yview)
        self.lb.configure(yscrollcommand=sb.set)
        self.lb.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.keys = [k for k, _ in choices]
        for i, (k, lab) in enumerate(choices):
            self.lb.insert("end", lab)
            if k == current:
                self.lb.selection_set(i)
                self.lb.see(i)
        self.lb.bind("<Double-Button-1>", lambda _e: self._ok())
        self.bind("<Return>", lambda _e: self._ok())
        self.show(self.lb)

    def _ok(self):
        s = self.lb.curselection()
        if s:
            self.result = self.keys[s[0]]
            self.destroy()


class AskDialog(Dialog):
    """Valeurs a fournir au lancement ({DOSSIER}, {HOTE}...)."""

    def __init__(self, parent, entry: Dict[str, Any], asks: List[Dict[str, str]], last: Dict[str, str]):
        super().__init__(parent, f"{entry.get('name', '')} — paramètres", 680, 160 + 62 * len(asks))
        mk_label(self, f"{entry.get('icon', '')} {entry.get('name', '')}", "HI", "ArsTitle").pack(anchor="w", padx=12, pady=(10, 2))
        mk_label(self, "Ces valeurs sont insérées dans la commande avant le lancement.", "DIM", "ArsSM").pack(anchor="w", padx=12)
        self.button_bar([("Annuler", self.cancel, ""), ("▶ Lancer", self._ok, "accent")])
        f = tk.Frame(self, bg=C["BG"])
        f.pack(fill="both", expand=True, padx=12, pady=8)
        self.vars: Dict[str, tk.StringVar] = {}
        self.asks = asks
        first = None
        for i, a in enumerate(asks):
            var = a["var"]
            default = last.get(var) or os.path.expandvars(a.get("default") or "")
            v = tk.StringVar(value=default)
            self.vars[var] = v
            mk_label(f, (a.get("label") or var) + " :", "TEXT", "ArsUIB").grid(row=i * 2, column=0, columnspan=2, sticky="w")
            en = mk_entry(f, v, 50)
            en.grid(row=i * 2 + 1, column=0, sticky="we", pady=(0, 6))
            first = first or en
            kind = a.get("kind") or "text"
            if kind in ("folder", "file"):
                mk_button(f, "Parcourir…", lambda vv=v, k=kind: self._browse(vv, k)).grid(row=i * 2 + 1, column=1, padx=6,
                                                                                         pady=(0, 6))
            elif kind == "drive":
                drives = [d for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")] if IS_WIN else ["C"]
                cb = ttk.Combobox(f, values=drives, width=4, state="readonly", textvariable=v)
                cb.grid(row=i * 2 + 1, column=1, padx=6, pady=(0, 6))
        f.columnconfigure(0, weight=1)
        self.bind("<Return>", lambda _e: self._ok())
        self.show(first)

    def _browse(self, v, kind):
        init = v.get() if os.path.isdir(v.get()) else (os.path.dirname(v.get()) if v.get() else "")
        if kind == "folder":
            p = filedialog.askdirectory(parent=self, initialdir=init or None)
        else:
            p = filedialog.askopenfilename(parent=self, initialdir=init or None)
        if p:
            v.set(os.path.normpath(p))

    def _ok(self):
        vals = {k: v.get().strip() for k, v in self.vars.items()}
        missing = [a.get("label") or a["var"] for a in self.asks if not vals.get(a["var"])]
        if missing:
            messagebox.showwarning(APP_NAME, "Valeur manquante : " + ", ".join(missing), parent=self)
            return
        for a in self.asks:
            if a.get("kind") == "drive":
                vals[a["var"]] = vals[a["var"]].rstrip(":\\/")[:1].upper()
        self.result = vals
        self.destroy()


class ConfirmDialog(Dialog):
    """Montre la commande EXACTE avant un lancement admin / dangereux."""

    def __init__(self, parent, entry: Dict[str, Any], spec: Dict[str, Any], can_skip: bool):
        danger = bool(entry.get("danger"))
        super().__init__(parent, "Confirmer le lancement", 780, 470)
        self.skip = tk.BooleanVar(value=False)
        head = tk.Frame(self, bg=C["ERR"] if danger else C["PANEL"])
        head.pack(fill="x")
        txt = "⚠  ACTION POTENTIELLEMENT DESTRUCTRICE — lis bien avant de continuer" if danger else \
            ("🛡  Lancement en ADMINISTRATEUR (fenêtre UAC)" if spec.get("admin") else "Confirmer le lancement")
        tk.Label(head, text=txt, bg=head.cget("bg"), fg="#FFFFFF" if danger else C["HI"], font=fnt("ArsUIB"),
                 anchor="w", padx=10, pady=8, wraplength=740, justify="left").pack(fill="x")
        mk_label(self, f"{entry.get('icon', '')} {entry.get('name', '')}", "HI", "ArsTitle").pack(anchor="w", padx=12, pady=(8, 0))
        if entry.get("desc"):
            mk_label(self, entry["desc"], "TEXT", "ArsUI", wraplength=740, justify="left").pack(anchor="w", padx=12)
        info = []
        if spec.get("admin"):
            info.append("Droits administrateur : oui")
        info.append("Console : " + CONSOLE_LABEL.get(spec.get("mode", ""), "-") if entry.get("type") in ("cmd", "ps", "script")
                    else "Type : " + TYPES.get(entry.get("type", ""), {}).get("label", ""))
        if spec.get("cwd"):
            info.append("Dossier : " + spec["cwd"])
        mk_label(self, "   ·   ".join(info), "DIM", "ArsSM", wraplength=740, justify="left").pack(anchor="w", padx=12, pady=(4, 2))
        mk_label(self, "Commande exacte :", "HI", "ArsUIB").pack(anchor="w", padx=12, pady=(6, 0))
        bar = self.button_bar([("Annuler", self.cancel, ""),
                               ("⚠ Lancer quand même" if danger else "▶ Lancer", self._ok, "danger" if danger else "accent")])
        if can_skip and not danger:
            mk_check(bar, "Ne plus demander pour les lancements admin non dangereux", self.skip).pack(side="left", padx=10)
        t = mk_text(self, 8, 80)
        t.pack(fill="both", expand=True, padx=12, pady=(2, 8))
        t.insert("1.0", spec.get("display", ""))
        t.configure(state="disabled")
        self.bind("<Return>", lambda _e: self._ok() if not danger else None)
        self.show()

    def _ok(self):
        self.result = {"ok": True, "skip": self.skip.get()}
        self.destroy()


class TextDialog(Dialog):
    """Texte long en lecture (aide, journal, rapport)."""

    def __init__(self, parent, title: str, content: str, w: int = 900, h: int = 640, tags: Optional[List[Tuple[str, str]]] = None):
        super().__init__(parent, title, w, h, modal=False)
        self.button_bar([("Copier", lambda: copy_to_clipboard(self, content), ""), ("Fermer", self.cancel, "accent")])
        fr = tk.Frame(self, bg=C["BG"])
        fr.pack(fill="both", expand=True, padx=8, pady=8)
        self.t = tk.Text(fr, bg=C["CARD"], fg=C["TEXT"], font=fnt("ArsUI"), wrap="word", relief="flat", padx=12, pady=8,
                         highlightthickness=0, selectbackground=C["SEL"], selectforeground=C["ON_SEL"], spacing1=1, spacing3=2)
        sb = ttk.Scrollbar(fr, orient="vertical", command=self.t.yview)
        self.t.configure(yscrollcommand=sb.set)
        self.t.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.t.tag_configure("h1", foreground=C["HI"], font=fnt("ArsTitle"), spacing1=8, spacing3=4)
        self.t.tag_configure("h2", foreground=C["HI"], font=fnt("ArsUIB"), spacing1=8, spacing3=2)
        self.t.tag_configure("k", foreground=C["FG"], font=fnt("ArsUIB"))
        self.t.tag_configure("dim", foreground=C["DIM"])
        for line in content.split("\n"):
            if line.startswith("# "):
                self.t.insert("end", line[2:] + "\n", "h1")
            elif line.startswith("## "):
                self.t.insert("end", line[3:] + "\n", "h2")
            elif line.startswith("  ") and " : " in line:
                k, v = line.split(" : ", 1)
                self.t.insert("end", k + " : ", "k")
                self.t.insert("end", v + "\n")
            else:
                self.t.insert("end", line + "\n")
        self.t.configure(state="disabled")
        self.t.bind("<MouseWheel>", lambda e: self.t.yview_scroll(int(-e.delta / 120) * 3, "units"))
        self.show(self.t)


class IPDialog(Dialog):
    """Mon IP : publique (v4/v6) et locales, copiables, actualisables."""

    def __init__(self, parent, app):
        super().__init__(parent, "Mon IP", 720, 470, modal=False)
        self.app = app
        mk_label(self, "🌍 Mon IP", "HI", "ArsTitle").pack(anchor="w", padx=14, pady=(10, 0))
        mk_label(self, f"Ordinateur : {socket.gethostname()}", "DIM", "ArsSM").pack(anchor="w", padx=14)
        self.button_bar([("⟳ Actualiser", self.refresh, ""), ("Tout copier", self.copy_all, ""),
                         ("Fermer", self.cancel, "accent")])
        self.body = tk.Frame(self, bg=C["BG"])
        self.body.pack(fill="both", expand=True, padx=14, pady=8)
        self.rows: List[Tuple[str, str]] = []
        self.refresh()
        self.show()

    def _render(self, rows: List[Tuple[str, str]], busy: bool = False):
        for w in self.body.winfo_children():
            w.destroy()
        self.rows = rows
        for i, (lab, val) in enumerate(rows):
            mk_label(self.body, lab, "FG", "ArsUIB", anchor="w").grid(row=i, column=0, sticky="w", pady=4)
            v = tk.StringVar(value=val)
            e = mk_entry(self.body, v, 40, "ArsUIB")
            e.configure(state="readonly", fg=C["HI"], readonlybackground=C["ENTRY_BG"])
            e.grid(row=i, column=1, sticky="we", padx=8)
            if val and not val.startswith("…") and not val.startswith("("):
                mk_button(self.body, "📋 Copier", lambda t=val: self._copy(t)).grid(row=i, column=2)
        self.body.columnconfigure(1, weight=1)
        if busy:
            mk_label(self.body, "Recherche de l'IP publique…", "DIM", "ArsSM").grid(row=len(rows), column=0, columnspan=3,
                                                                                  sticky="w", pady=6)

    def _copy(self, t):
        copy_to_clipboard(self, t)
        self.app.set_status(f"Copié : {t}")

    def copy_all(self):
        copy_to_clipboard(self, "\n".join(f"{a} : {b}" for a, b in self.rows))
        self.app.set_status("IP copiées dans le presse-papiers")

    def refresh(self):
        loc = local_ips()
        rows = [("IP publique (IPv4)", "…"), ("IP publique (IPv6)", "…")] + [(f"Locale {a}", b) for a, b in loc]
        self._render(rows, busy=True)

        def work():
            v4 = public_ip(False)
            v6 = public_ip(True)
            if v6 == v4 or ":" not in v6:
                v6 = "(pas d'IPv6 publique)"
            self.app.post(lambda: self._done(v4 or "(introuvable : pas d'Internet ?)", v6, loc))
        threading.Thread(target=work, daemon=True).start()

    def _done(self, v4, v6, loc):
        if not self.winfo_exists():
            return
        self.app.ip_cache = {"public": v4, "local": loc[0][1] if loc else ""}
        self.app.refresh_items(keep=True)
        self._render([("IP publique (IPv4)", v4), ("IP publique (IPv6)", v6)] + [(f"Locale {a}", b) for a, b in loc])


# ================================================================ editeur / assistant
def guess_type(text: str) -> str:
    t = (text or "").strip().strip('"')
    lo = t.lower()
    if re.match(r"^(https?|ftp)://", lo) or lo.startswith("www."):
        return "url"
    if lo.startswith(("shell:", "ms-settings:", "windowsdefender:", "::{")):
        return "shell"
    p = os.path.expandvars(t)
    if p and os.path.isdir(p):
        return "folder"
    ext = os.path.splitext(p)[1].lower()
    if p and os.path.isfile(p):
        return "script" if ext in (".bat", ".cmd", ".ps1", ".py", ".pyw") else "file"
    if re.match(r"^[a-zA-Z]:\\", p) or p.startswith("\\\\"):
        return "script" if ext in (".bat", ".cmd", ".ps1", ".py", ".pyw") else ("file" if ext else "folder")
    if re.match(r"^(\$|get-|set-|new-|remove-|start-|stop-|test-|invoke-|import-|export-|add-|enable-|disable-)", lo):
        return "ps"
    return "cmd"


def guess_name(typ: str, target: str) -> str:
    t = (target or "").strip().strip('"')
    if typ == "url":
        m = re.match(r"^[a-z]+://(?:www\.)?([^/:?#]+)", t, re.I)
        return m.group(1) if m else t[:40]
    if typ in ("file", "script", "folder"):
        base = os.path.basename(t.rstrip("\\/")) or t
        return os.path.splitext(base)[0] if typ != "folder" else base
    return t.split("\n")[0][:40]


ASK_GUESS = {"DOSSIER": "folder", "FICHIER": "file", "LETTRE": "drive", "SCRIPT": "file"}


class EditorDialog(Dialog):
    """Assistant : 1) choisir le type  2) champs adaptes, Parcourir, Tester, Enregistrer."""

    def __init__(self, parent, app, entry: Optional[Dict[str, Any]] = None, default_cat: str = "",
                 prefill: Optional[Dict[str, Any]] = None):
        self.app = app
        self.store: Store = app.store
        self.is_new = entry is None
        title = "Nouvelle entrée" if self.is_new else f"Modifier — {entry.get('name', '')}"
        super().__init__(parent, title, 900, 700)
        e = default_entry() if entry is None else copy.deepcopy(entry)
        if prefill:
            e.update(prefill)
        if not e.get("category"):
            e["category"] = default_cat or "mes_ajouts"
        self.e = e
        self.cat_ids: List[str] = []
        self.body = tk.Frame(self, bg=C["BG"])
        self.body.pack(fill="both", expand=True)
        self.bind("<Control-s>", lambda _e: self.save())
        if self.is_new and not prefill:
            self.step1()
        else:
            self.step2()
        self.show()

    # ------------------------------------------------------------ etape 1 : type
    def step1(self):
        for w in self.body.winfo_children():
            w.destroy()
        self.unbind("<Return>")
        f = self.body
        mk_label(f, "＋ Ajouter — étape 1 : que veux-tu ajouter ?", "HI", "ArsTitle").pack(anchor="w", padx=14, pady=(12, 4))
        q = tk.Frame(f, bg=C["PANEL"])
        q.pack(fill="x", padx=14, pady=(2, 8))
        mk_label(q, "Colle un lien, un chemin ou une commande :", "TEXT", "ArsUI").pack(side="left", padx=8, pady=8)
        self.v_quick = tk.StringVar()
        en = mk_entry(q, self.v_quick, 34)
        en.pack(side="left", fill="x", expand=True, padx=4, pady=8)
        mk_button(q, "Détecter ▶", self._quick).pack(side="left", padx=8)
        en.bind("<Return>", lambda _e: self._quick())
        sf = ScrollFrame(f)
        sf.pack(fill="both", expand=True, padx=14, pady=4)
        g = sf.inner
        for i, t in enumerate(TYPE_ORDER):
            info = TYPES[t]
            card = tk.Frame(g, bg=C["CARD"], highlightthickness=1, highlightbackground=C["LINE"], cursor="hand2")
            card.grid(row=i // 2, column=i % 2, sticky="nsew", padx=4, pady=4)
            ic = tk.Label(card, text=info["icon"], bg=C["CARD"], fg=C["HI"], font=fnt("ArsEmoji"), width=2)
            ic.pack(side="left", padx=(8, 4), pady=6)
            tx = tk.Frame(card, bg=C["CARD"])
            tx.pack(side="left", fill="both", expand=True, pady=4)
            l1 = tk.Label(tx, text=info["label"], bg=C["CARD"], fg=C["TEXT"], font=fnt("ArsUIB"), anchor="w", justify="left")
            l1.pack(anchor="w")
            l2 = tk.Label(tx, text=info["help"], bg=C["CARD"], fg=C["DIM"], font=fnt("ArsSM"), anchor="w", justify="left",
                          wraplength=330)
            l2.pack(anchor="w", fill="x")
            for w in (card, ic, tx, l1, l2):
                w.bind("<Button-1>", lambda _e, tt=t: self._choose(tt))
                w.bind("<Enter>", lambda _e, c=card: self._hover(c, True))
                w.bind("<Leave>", lambda _e, c=card: self._hover(c, False))
            tx.bind("<Configure>", lambda e, lab=l2: lab.configure(wraplength=max(150, e.width - 10)))
        g.columnconfigure(0, weight=1, uniform="c")
        g.columnconfigure(1, weight=1, uniform="c")
        bar = tk.Frame(f, bg=C["PANEL"])
        bar.pack(side="bottom", fill="x")
        mk_button(bar, "Annuler", self.cancel).pack(side="right", padx=8, pady=8)
        mk_label(bar, "Astuce : tu peux aussi glisser un fichier, un dossier ou un lien sur la fenêtre d'Arsenal.",
                 "DIM", "ArsSM", bg=C["PANEL"]).pack(side="left", padx=10)
        en.focus_set()

    def _hover(self, card, on):
        col = C["HOVER"] if on else C["CARD"]
        card.configure(bg=col, highlightbackground=C["HI"] if on else C["LINE"])
        for w in card.winfo_children():
            try:
                w.configure(bg=col)
                for ww in w.winfo_children():
                    ww.configure(bg=col)
            except tk.TclError:
                pass

    def _choose(self, t):
        self.e["type"] = t
        if t in ("cmd", "ps"):
            self.e["console"] = "capture"
        self.step2()

    def _quick(self):
        txt = self.v_quick.get().strip()
        if not txt:
            return
        t = guess_type(txt)
        self.e.update(type=t, target=txt.strip('"') if t not in ("cmd", "ps") else txt, name=guess_name(t, txt))
        if t in ("cmd", "ps"):
            self.e["console"] = "capture"
        self.step2()

    # ------------------------------------------------------------ etape 2 : formulaire
    def _row(self, label: str, r: int, hint: str = ""):
        mk_label(self.form, label, "HI", "ArsUIB", anchor="w").grid(row=r, column=0, sticky="nw", padx=(4, 8), pady=5)
        if hint:
            mk_label(self.form, hint, "DIM", "ArsSM", anchor="w", justify="left", wraplength=560).grid(
                row=r + 1, column=1, columnspan=3, sticky="w", pady=(0, 4))

    def step2(self):
        for w in self.body.winfo_children():
            w.destroy()
        e = self.e
        t = e["type"]
        info = TYPES.get(t, TYPES["url"])
        bar = tk.Frame(self.body, bg=C["PANEL"])
        bar.pack(side="bottom", fill="x")
        if self.is_new:
            mk_button(bar, "◀ Type", self._back).pack(side="left", padx=8, pady=8)
        mk_button(bar, "▶ Tester", self.test, tip="Lance avec les valeurs du formulaire, sans enregistrer").pack(
            side="left", padx=4, pady=8)
        mk_button(bar, "Enregistrer", self.save, "accent").pack(side="right", padx=8, pady=8)
        mk_button(bar, "Annuler", self.cancel).pack(side="right", padx=4, pady=8)
        head = tk.Frame(self.body, bg=C["BG"])
        head.pack(fill="x", padx=14, pady=(10, 0))
        mk_label(head, f"{info['icon']}  {info['label']}", "HI", "ArsTitle").pack(side="left")
        sf = ScrollFrame(self.body)
        sf.pack(fill="both", expand=True, padx=10, pady=6)
        self.form = f = sf.inner
        f.columnconfigure(1, weight=1)
        r = 0
        # type
        self.v_type = tk.StringVar(value=info["label"])
        self._row("Type", r)
        labels = [TYPES[k]["label"] for k in TYPE_ORDER + (["builtin"] if t == "builtin" else [])]
        cb = ttk.Combobox(f, values=labels, textvariable=self.v_type, state="readonly", width=40)
        cb.grid(row=r, column=1, columnspan=2, sticky="w", pady=5)
        cb.bind("<<ComboboxSelected>>", lambda _e: self._change_type())
        r += 1
        # nom
        self.v_name = tk.StringVar(value=e.get("name", ""))
        self._row("Nom *", r)
        en_name = mk_entry(f, self.v_name, 50)
        en_name.grid(row=r, column=1, columnspan=3, sticky="we", pady=5)
        r += 1
        # cible
        self._row(info["target"] + " *", r, info["help"] + ("   Variables : {DOSSIER}, {FICHIER}… seront demandées au "
                                                           "lancement ; {PROJET} {PYTHON} {MPCMDRUN} sont automatiques."
                                                           if t in ("cmd", "ps", "file", "script") else ""))
        self.t_target = None
        self.v_target = tk.StringVar(value=e.get("target", ""))
        if t in ("cmd", "ps", "copy"):
            self.t_target = mk_text(f, 5, 60)
            self.t_target.grid(row=r, column=1, columnspan=3, sticky="we", pady=5)
            self.t_target.insert("1.0", e.get("target", ""))
            self.t_target.bind("<FocusOut>", lambda _e: self._refresh_asks())
        elif t == "shell":
            cbt = ttk.Combobox(f, values=SHELL_SUGGESTIONS, textvariable=self.v_target, width=56)
            cbt.grid(row=r, column=1, columnspan=2, sticky="we", pady=5)
        else:
            et = mk_entry(f, self.v_target, 50)
            et.grid(row=r, column=1, columnspan=2, sticky="we", pady=5)
            et.bind("<FocusOut>", lambda _e: self._auto_name())
            if t in ("file", "folder", "script"):
                mk_button(f, "Parcourir…", lambda: self._browse(self.v_target, "folder" if t == "folder" else "file")).grid(
                    row=r, column=3, sticky="w", padx=6)
        r += 2
        # arguments / dossier / console
        self.v_args = tk.StringVar(value=e.get("args", ""))
        self.v_cwd = tk.StringVar(value=e.get("cwd", ""))
        self.v_console = tk.StringVar(value=CONSOLE_LABEL.get(e.get("console", "keep"), CONSOLE_LABEL["keep"]))
        if t in ("file", "script", "shell"):
            self._row("Arguments", r)
            mk_entry(f, self.v_args, 50).grid(row=r, column=1, columnspan=3, sticky="we", pady=5)
            r += 1
        if t in ("file", "script", "cmd", "ps"):
            self._row("Dossier de travail", r)
            mk_entry(f, self.v_cwd, 50).grid(row=r, column=1, columnspan=2, sticky="we", pady=5)
            mk_button(f, "Parcourir…", lambda: self._browse(self.v_cwd, "folder")).grid(row=r, column=3, sticky="w", padx=6)
            r += 1
        if t in ("script", "cmd", "ps"):
            self._row("Console", r, "« Résultat dans Arsenal » : la sortie s'affiche dans le panneau Résultat (copiable).")
            ttk.Combobox(f, values=[lab for _, lab in CONSOLE_MODES], textvariable=self.v_console, state="readonly",
                         width=34).grid(row=r, column=1, sticky="w", pady=5)
            r += 2
        # categorie / groupe
        self._row("Catégorie", r)
        self.v_cat = tk.StringVar()
        self.cb_cat = ttk.Combobox(f, state="readonly", textvariable=self.v_cat, width=34)
        self.cb_cat.grid(row=r, column=1, sticky="w", pady=5)
        self.cb_cat.bind("<<ComboboxSelected>>", lambda _e: self._cat_changed())
        self._fill_cats(e.get("category", ""))
        mk_label(f, "Groupe", "HI", "ArsUIB").grid(row=r, column=2, sticky="e", padx=6)
        self.v_group = tk.StringVar(value=e.get("group", ""))
        self.cb_group = ttk.Combobox(f, textvariable=self.v_group, width=22)
        self.cb_group.grid(row=r, column=3, sticky="w", pady=5)
        self._fill_groups()
        r += 1
        # description
        self._row("Description", r)
        self.t_desc = mk_text(f, 3, 60, "ArsUI")
        self.t_desc.grid(row=r, column=1, columnspan=3, sticky="we", pady=5)
        self.t_desc.insert("1.0", e.get("desc", ""))
        r += 1
        # icone
        self._row("Icône", r)
        ic = tk.Frame(f, bg=C["BG"])
        ic.grid(row=r, column=1, columnspan=3, sticky="w", pady=5)
        self.v_icon = tk.StringVar(value=e.get("icon", ""))
        self.icon_file = e.get("icon_file", "")
        self.l_icon = tk.Label(ic, bg=C["CARD"], fg=C["HI"], font=fnt("ArsEmoji"), width=3, height=1)
        self.l_icon.pack(side="left", padx=(0, 8))
        mk_entry(ic, self.v_icon, 5, "ArsEmojiSM").pack(side="left")
        mk_button(ic, "Choisir un emoji…", self._pick_emoji).pack(side="left", padx=6)
        if t in ("file", "script", "folder"):
            mk_button(ic, "Icône du programme", self._extract_icon,
                      tip="Extrait l'icône Windows du fichier choisi").pack(side="left", padx=2)
        mk_button(ic, "Par défaut", self._icon_default).pack(side="left", padx=6)
        self.v_icon.trace_add("write", lambda *_a: self._icon_preview())
        self._icon_preview()
        r += 1
        # tags
        self.v_tags = tk.StringVar(value=", ".join(e.get("tags") or []))
        self._row("Mots-clés", r, "Séparés par des virgules : aident la recherche.")
        mk_entry(f, self.v_tags, 50).grid(row=r, column=1, columnspan=3, sticky="we", pady=5)
        r += 2
        # options
        self._row("Options", r)
        op = tk.Frame(f, bg=C["BG"])
        op.grid(row=r, column=1, columnspan=3, sticky="w", pady=5)
        self.v_admin = tk.BooleanVar(value=e.get("admin", False))
        self.v_confirm = tk.BooleanVar(value=e.get("confirm", False))
        self.v_danger = tk.BooleanVar(value=e.get("danger", False))
        self.v_fav = tk.BooleanVar(value=e.get("fav", False))
        self.v_hidden = tk.BooleanVar(value=e.get("hidden", False))
        opts = [("🛡 Administrateur (UAC)", self.v_admin), ("❓ Demander confirmation", self.v_confirm),
                ("⚠ Action dangereuse", self.v_danger), ("⭐ Favori", self.v_fav), ("👁 Masquée", self.v_hidden)]
        opts = [o for o in opts if not (o[0].startswith("🛡") and t in ("url", "folder", "copy", "builtin"))]
        for i, (lab, var) in enumerate(opts):
            mk_check(op, lab, var).grid(row=i // 2, column=i % 2, sticky="w", padx=(0, 24), pady=1)
        r += 1
        # requis
        self.v_requires = tk.StringVar(value=e.get("requires", ""))
        if t not in ("url", "copy", "builtin"):
            self._row("Requiert", r, "Programme ou chemin nécessaire (ex. git.exe) : sinon Arsenal l'indique au lieu d'échouer.")
            mk_entry(f, self.v_requires, 50).grid(row=r, column=1, columnspan=3, sticky="we", pady=5)
            r += 2
        # questions
        self.asks = [dict(a) for a in e.get("ask") or []]
        self.ask_row = r
        self.ask_frame = tk.Frame(f, bg=C["BG"])
        self.ask_frame.grid(row=r + 1, column=0, columnspan=4, sticky="we")
        self._refresh_asks()
        en_name.focus_set()
        if not self.v_name.get():
            self._auto_name()

    def _back(self):
        self._collect()
        self.step1()

    def _change_type(self):
        lab = self.v_type.get()
        self._collect()
        for k, v in TYPES.items():
            if v["label"] == lab:
                if k in ("cmd", "ps") and self.e["type"] not in ("cmd", "ps"):
                    self.e["console"] = "capture"
                self.e["type"] = k
        self.step2()

    def _fill_cats(self, cid: str):
        cats = self.store.categories
        self.cat_ids = [c["id"] for c in cats]
        names = [self.store.cat_name(c["id"], True) for c in cats] + ["＋ Nouvelle catégorie…"]
        self.cb_cat.configure(values=names, height=min(22, len(names)))
        if cid in self.cat_ids:
            self.cb_cat.current(self.cat_ids.index(cid))
        elif self.cat_ids:
            self.cb_cat.current(0)

    def _cur_cat(self) -> str:
        i = self.cb_cat.current()
        return self.cat_ids[i] if 0 <= i < len(self.cat_ids) else "mes_ajouts"

    def _cat_changed(self):
        if self.cb_cat.current() == len(self.cat_ids):
            r = CategoryDialog(self, "Nouvelle catégorie").wait()
            if r:
                cid = self.app.create_category(r[0], r[1])
                self._fill_cats(cid)
            else:
                self._fill_cats(self.e.get("category", ""))
        self._fill_groups()

    def _fill_groups(self):
        cid = self._cur_cat()
        groups = sorted({x.get("group", "") for x in self.store.entries if x["category"] == cid and x.get("group")})
        self.cb_group.configure(values=groups)

    def _browse(self, var, kind):
        cur = os.path.expandvars(expand(var.get()))
        init = cur if os.path.isdir(cur) else os.path.dirname(cur) if cur else ""
        if kind == "folder":
            p = filedialog.askdirectory(parent=self, initialdir=init or None)
        else:
            p = filedialog.askopenfilename(parent=self, initialdir=init or None,
                                           filetypes=[("Tous les fichiers", "*.*"), ("Programmes", "*.exe;*.lnk;*.msc;*.cpl"),
                                                      ("Scripts", "*.bat;*.cmd;*.ps1;*.py;*.pyw")])
        if p:
            var.set(os.path.normpath(p))
            if var is self.v_target:
                self._auto_name(force=not self.v_name.get())

    def _auto_name(self, force: bool = False):
        if force or not self.v_name.get().strip():
            tg = self.v_target.get() if self.t_target is None else self.t_target.get("1.0", "end").strip()
            if tg:
                self.v_name.set(guess_name(self.e["type"], tg))

    def _pick_emoji(self):
        r = EmojiPicker(self, self.v_icon.get()).wait()
        if r is not None:
            self.icon_file = ""
            self.v_icon.set(r)

    def _icon_default(self):
        self.icon_file = ""
        self.v_icon.set(TYPES[self.e["type"]]["icon"])

    def _extract_icon(self):
        tg = self.v_target.get()
        if self.e["type"] == "file" and os.path.basename(expand_path(tg)).lower() in ("pythonw.exe", "python.exe") \
                and self.v_args.get():
            tg = self.v_args.get().strip().split('" ')[0].strip('"')
        name = extract_icon_png(tg)
        if not name:
            messagebox.showinfo(APP_NAME, "Impossible d'extraire une icône de ce chemin (fichier introuvable "
                                "ou Pillow absent). Choisis un emoji à la place.", parent=self)
            return
        self.icon_file = name
        self._icon_preview()

    def _icon_preview(self):
        img = self.app.icon_image(self.icon_file, 32) if self.icon_file else None
        if img is not None:
            self.l_icon.configure(image=img, text="", width=40, height=34)
            self.l_icon.image = img
        else:
            self.l_icon.configure(image="", text=self.v_icon.get() or TYPES[self.e["type"]]["icon"], width=3, height=1)

    def _target_text(self) -> str:
        if self.t_target is not None:
            return self.t_target.get("1.0", "end").rstrip("\n")
        return self.v_target.get().strip()

    def _refresh_asks(self):
        for w in self.ask_frame.winfo_children():
            w.destroy()
        txt = self._target_text() + " " + self.v_args.get() + " " + self.v_cwd.get()
        found = placeholders_in(txt)
        old = {a["var"]: a for a in self.asks}
        self.asks = [old.get(v) or {"var": v, "label": v.capitalize(), "kind": ASK_GUESS.get(v, "text"), "default": ""}
                     for v in found]
        self.ask_vars = []
        if not found:
            return
        mk_label(self.ask_frame, "Questions au lancement (variables {…} détectées)", "HI", "ArsUIB").grid(
            row=0, column=0, columnspan=4, sticky="w", padx=4, pady=(8, 2))
        for i, a in enumerate(self.asks, start=1):
            mk_label(self.ask_frame, "{" + a["var"] + "}", "FG", "ArsUIB").grid(row=i, column=0, sticky="w", padx=4)
            vl, vk, vd = tk.StringVar(value=a.get("label", "")), tk.StringVar(value=ASK_LABEL.get(a.get("kind", "text"))), \
                tk.StringVar(value=a.get("default", ""))
            mk_entry(self.ask_frame, vl, 26).grid(row=i, column=1, padx=4, pady=2, sticky="we")
            ttk.Combobox(self.ask_frame, values=[x for _, x in ASK_KINDS], textvariable=vk, state="readonly",
                         width=16).grid(row=i, column=2, padx=4)
            mk_entry(self.ask_frame, vd, 20).grid(row=i, column=3, padx=4, sticky="we")
            self.ask_vars.append((a["var"], vl, vk, vd))
        mk_label(self.ask_frame, "Libellé · type de valeur · valeur par défaut", "DIM", "ArsSM").grid(
            row=len(self.asks) + 1, column=1, columnspan=3, sticky="w", padx=4)
        self.ask_frame.columnconfigure(1, weight=1)

    def _collect(self) -> Dict[str, Any]:
        e = self.e
        if not hasattr(self, "v_name"):
            return e
        e["name"] = self.v_name.get().strip()
        e["target"] = self._target_text()
        e["args"] = self.v_args.get().strip()
        e["cwd"] = self.v_cwd.get().strip()
        lab = self.v_console.get()
        e["console"] = next((k for k, v in CONSOLE_MODES if v == lab), e.get("console", "keep"))
        e["category"] = self._cur_cat()
        e["group"] = self.v_group.get().strip()
        e["desc"] = self.t_desc.get("1.0", "end").strip()
        e["icon"] = self.v_icon.get().strip()
        e["icon_file"] = self.icon_file
        e["tags"] = [x.strip() for x in self.v_tags.get().split(",") if x.strip()]
        e["admin"] = self.v_admin.get() and e["type"] not in ("url", "folder", "copy", "builtin")
        e["confirm"] = self.v_confirm.get()
        e["danger"] = self.v_danger.get()
        e["fav"] = self.v_fav.get()
        e["hidden"] = self.v_hidden.get()
        e["requires"] = self.v_requires.get().strip()
        self._refresh_asks_values()
        e["ask"] = [dict(a) for a in self.asks]
        return e

    def _refresh_asks_values(self):
        vals = {v: (vl.get().strip(), vk.get(), vd.get()) for v, vl, vk, vd in getattr(self, "ask_vars", [])}
        txt = self._target_text() + " " + self.v_args.get() + " " + self.v_cwd.get()
        found = placeholders_in(txt)
        out = []
        old = {a["var"]: a for a in self.asks}
        for v in found:
            a = dict(old.get(v) or {"var": v, "label": v.capitalize(), "kind": ASK_GUESS.get(v, "text"), "default": ""})
            if v in vals:
                lab, kl, d = vals[v]
                a["label"] = lab or v.capitalize()
                a["kind"] = next((k for k, x in ASK_KINDS if x == kl), "text")
                a["default"] = d
            out.append(a)
        self.asks = out

    def _validate(self) -> bool:
        e = self._collect()
        if not e["name"]:
            messagebox.showwarning(APP_NAME, "Donne un nom à l'entrée.", parent=self)
            return False
        if not e["target"].strip():
            messagebox.showwarning(APP_NAME, "Le champ « " + TYPES[e["type"]]["target"] + " » est vide.", parent=self)
            return False
        if not e["icon"] and not e["icon_file"]:
            e["icon"] = TYPES[e["type"]]["icon"]
        return True

    def test(self):
        if self._validate():
            self.app.launch(copy.deepcopy(self.e), test=True, parent=self)

    def save(self):
        if self._validate():
            self.result = self.e
            self.destroy()


# ================================================================ application
SPECIAL_VIEWS = [
    ("@fav", "⭐", "Favoris"),
    ("@recent", "🕘", "Récents"),
    ("@top", "🔥", "Plus utilisés"),
    ("@all", "📚", "Tout"),
    ("@hidden", "👁", "Masquées"),
]


PANES_V = 3  # version du format des largeurs de panneaux enregistrees


class ArsenalApp(tk.Tk):
    def __init__(self, args):
        super().__init__()
        self.withdraw()
        self.args = args
        self.title(APP_TITLE)
        self.q: "queue.Queue[Callable]" = queue.Queue()
        self.cap_q: "queue.Queue[str]" = queue.Queue()
        self.hk_q: "queue.Queue[int]" = queue.Queue()
        ro = bool(getattr(args, "smoke", False) or getattr(args, "shot", ""))
        self.store = Store(getattr(args, "data", "") or DATA_FILE, readonly=ro)
        self.store.load()
        s = self.store.settings
        theme = s.get("theme", "norton")
        C.clear()
        C.update(THEMES.get(theme, THEMES["norton"]))
        CONSOLE_COLORS[0] = bool(s.get("console_colors", True))
        init_fonts(self, s.get("font_delta", 0))
        self.view_mode = s.get("view", "tiles")
        self.cur_view = s.get("last_view", "@fav")
        if self.cur_view.startswith("c:") and not self.store.cat(self.cur_view[2:]):
            self.cur_view = "@fav"
        self.selected: List[str] = []
        self.anchor: Optional[str] = None
        self.visible: List[Dict[str, Any]] = []
        self.rows: List[Tuple[str, Any]] = []
        self.tiles: List[Tuple[int, int, int, int, str]] = []
        self.undo: List[Tuple[str, Dict[str, Any]]] = []
        self.redo: List[Tuple[str, Dict[str, Any]]] = []
        self.ip_cache: Dict[str, str] = {}
        self.icon_cache: Dict[Tuple[str, int], Any] = {}
        self.fit_cache: Dict[Tuple[str, str, int, int], str] = {}
        self.last_values: Dict[str, Dict[str, str]] = {}
        self.capture: Optional[Dict[str, Any]] = None
        self.drag: Optional[Dict[str, Any]] = None
        self.press: Optional[Dict[str, Any]] = None
        self.hover_eid: Optional[str] = None
        self.tip_win = None
        self.tip_job = None
        self.save_job = None
        self.search_job = None
        self.rename_entry = None
        self.hk_thread_id = 0
        self.result_shown = False
        self.palette = None
        self._build()
        try:
            ico = os.path.join(BASE, "arsenal1.ico")
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
        self.after(60, self._poll)
        self.after(150, lambda: self.refresh_all(first=True))
        if not ro:
            self.after(120, self._ensure_shown)
            self.after(700, self._ensure_shown)
        if self.store.load_error:
            self.after(800, lambda: messagebox.showwarning(APP_NAME, self.store.load_error, parent=self))
        if not ro:
            threading.Thread(target=self._bg_ip, daemon=True).start()
            if s.get("global_hotkey", True):
                self.start_hotkey()
        logger.info("Arsenal démarré : %d entrées, %d catégories", len(self.store.entries), len(self.store.categories))

    def _ensure_shown(self):
        """Si le lanceur a demande SW_HIDE (STARTUPINFO), Windows l'applique au premier
        ShowWindow de Tk : la fenetre existe mais reste invisible. On la remontre."""
        if not IS_WIN:
            return
        try:
            u32 = ctypes.windll.user32
            hwnd = int(self.wm_frame(), 16)
            if not u32.IsWindowVisible(hwnd):
                zoomed = self.state() == "zoomed" or bool(u32.IsZoomed(hwnd))
                u32.ShowWindow(hwnd, 3 if zoomed else 5)
                logger.info("fenêtre remontrée (lancée masquée)")
            self.lift()
            self.focus_force()
        except Exception:
            pass

    # ------------------------------------------------------------ outils
    def post(self, fn: Callable) -> None:
        self.q.put(fn)

    def _poll(self):
        try:
            for _ in range(200):
                fn = self.q.get_nowait()
                try:
                    fn()
                except Exception:
                    logger.error("tâche UI : %s", traceback.format_exc())
        except queue.Empty:
            pass
        chunks = []
        try:
            while True:
                chunks.append(self.cap_q.get_nowait())
        except queue.Empty:
            pass
        if chunks:
            self._result_append("".join(chunks))
        try:
            while True:
                self.hk_q.get_nowait()
                self.from_hotkey()
        except queue.Empty:
            pass
        self.after(80, self._poll)

    def _bg_ip(self):
        loc = local_ips()
        pub = public_ip(False)
        self.post(lambda: self._ip_ready(pub, loc[0][1] if loc else ""))

    def _ip_ready(self, pub, loc):
        self.ip_cache = {"public": pub, "local": loc}
        self.refresh_items(keep=True)

    def set_status(self, msg: str, key: str = "FG") -> None:
        try:
            self.l_status.configure(text=msg, fg=C.get(key, C["FG"]))
        except Exception:
            pass

    def icon_image(self, name: str, size: int = 32):
        if not name:
            return None
        k = (name, size)
        if k in self.icon_cache:
            return self.icon_cache[k]
        img = None
        p = os.path.join(ICON_DIR, name)
        if os.path.isfile(p):
            try:
                img = tk.PhotoImage(file=p, master=self)
            except tk.TclError:
                img = None
        self.icon_cache[k] = img
        return img

    def fit(self, text: str, font_name: str, width: int, lines: int = 1) -> str:
        """Coupe proprement en `lines` lignes de `width` px max (… si trop long)."""
        k = (text, font_name, width, lines)
        if k in self.fit_cache:
            return self.fit_cache[k]
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
            if not cur:  # mot trop long : on le coupe
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
        if rest or cur:
            last = out[-1] if out else ""
            while last and meas(last + "…") > width:
                last = last[:-1]
            if out:
                out[-1] = last.rstrip() + "…"
        res = "\n".join(out)
        self.fit_cache[k] = res
        return res

    # ------------------------------------------------------------ construction
    def _build(self):
        apply_styles(self)
        self.configure(bg=C["BG"])
        self.fit_cache.clear()
        self._build_menu()
        self._build_toolbar()
        sb = tk.Frame(self, bg=C["PANEL"])
        sb.pack(side="bottom", fill="x")
        self.l_status = tk.Label(sb, text="Prêt.", bg=C["PANEL"], fg=C["FG"], font=fnt("ArsSM"), anchor="w")
        self.l_status.pack(side="left", fill="x", expand=True, padx=8, pady=3)
        self.l_count = tk.Label(sb, text="", bg=C["PANEL"], fg=C["DIM"], font=fnt("ArsSM"), anchor="e")
        self.l_count.pack(side="right", padx=8)
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
        st = self.store.settings
        saved = not getattr(self.args, "geometry", "") and st.get("panes_v") == PANES_V
        left_w = int((saved and st.get("left_w")) or (215 if sw <= 1100 else 260))
        right_w = int((saved and st.get("right_w")) or (290 if sw <= 1100 else 350))
        # la colonne des categories s'elargit au besoin : aucun nom tronque
        left_w = max(170, min(int(sw * 0.34), max(left_w, self._left_needed())))
        right_w = max(240, min(int(sw * 0.36), right_w))
        self.pw.add(self.f_left, minsize=170, width=left_w, stretch="never")
        self.pw.add(self.f_center, minsize=300, stretch="always")
        self.pw.add(self.f_right, minsize=240, width=right_w, stretch="never")
        self._bind_keys()
        self._setup_dnd()

    def _left_needed(self) -> int:
        """Largeur minimale de la colonne Categories pour afficher le plus long nom en entier."""
        try:
            f = fnt("ArsUI")
            if isinstance(f, str):
                f = tkfont.nametofont(f)
            names = [f" {ic}  {lab}" for _, ic, lab in SPECIAL_VIEWS]
            names += [f" {c.get('icon', '📂')}  {c['name']}" for c in self.store.categories]
            # + compteur (46) + retrait de l'arbre + barre de defilement + marge
            return max(f.measure(t) for t in names) + 46 + 22 + 24 + 16
        except Exception:
            return 260

    def _build_menu(self):
        mb = tk.Menu(self)
        style_menu(mb)
        m = new_menu(mb)
        m.add_command(label="＋ Ajouter une entrée…", accelerator="Ctrl+N", command=self.add_entry)
        m.add_command(label="Nouvelle catégorie…", command=self.new_category)
        m.add_separator()
        imp = new_menu(m)
        imp.add_command(label="Fichier Arsenal / Favoris / signets (.json, .html)…", command=self.import_file)
        imp.add_command(label="Paquet d'exemple / paquet re\u00e7u\u2026", command=self.import_pack)
        imp.add_command(label="Favoris.php : dernière sauvegarde locale", command=self.import_favoris_backup)
        imp.add_command(label="Favoris.php : page en ligne (marcsevigny.ca)", command=self.import_favoris_url)
        imp.add_command(label="Signets Chrome / Edge / Brave…", command=self.import_browser)
        m.add_cascade(label="Importer", menu=imp)
        exp = new_menu(m)
        exp.add_command(label="Tout en JSON (sauvegarde partageable)…", command=lambda: self.export_json(False))
        exp.add_command(label="Sélection en JSON…", command=lambda: self.export_json(True))
        exp.add_command(label="Catalogue HTML (page imprimable)…", command=self.export_html)
        m.add_cascade(label="Exporter", menu=exp)
        m.add_separator()
        m.add_command(label="Sauvegarder maintenant (copie datée)", command=self.backup_now)
        m.add_command(label="Ouvrir le dossier des sauvegardes", command=lambda: self.open_path(BACKUP_DIR))
        m.add_command(label="Restaurer les entrées d'origine supprimées", command=self.restore_seeds)
        m.add_separator()
        m.add_command(label="Quitter", accelerator="Alt+F4", command=self.on_close)
        mb.add_cascade(label="Fichier", menu=m)
        m = new_menu(mb)
        m.add_command(label="Annuler", accelerator="Ctrl+Z", command=self.do_undo)
        m.add_command(label="Rétablir", accelerator="Ctrl+Y", command=self.do_redo)
        m.add_separator()
        m.add_command(label="Modifier…", accelerator="Ctrl+E", command=lambda: self.edit_entry())
        m.add_command(label="Renommer", accelerator="F2", command=self.start_rename)
        m.add_command(label="Dupliquer", accelerator="Ctrl+D", command=self.duplicate)
        m.add_command(label="Déplacer vers…", accelerator="Ctrl+M", command=self.move_dialog)
        m.add_command(label="Favori oui/non", accelerator="Ctrl+B", command=self.toggle_fav)
        m.add_command(label="Masquer / afficher", accelerator="Ctrl+H", command=self.toggle_hidden)
        m.add_command(label="Monter", accelerator="Alt+Haut", command=lambda: self.move_step(-1))
        m.add_command(label="Descendre", accelerator="Alt+Bas", command=lambda: self.move_step(1))
        m.add_separator()
        m.add_command(label="Tout sélectionner", accelerator="Ctrl+A", command=self.select_all)
        m.add_command(label="Supprimer", accelerator="Suppr", command=self.delete_selected)
        mb.add_cascade(label="Édition", menu=m)
        m = new_menu(mb)
        self.v_view = tk.StringVar(value=self.view_mode)
        m.add_radiobutton(label="Tuiles", variable=self.v_view, value="tiles", command=self.set_view_mode)
        m.add_radiobutton(label="Liste", variable=self.v_view, value="list", command=self.set_view_mode)
        self.v_showhidden = tk.BooleanVar(value=bool(self.store.settings.get("show_hidden", False)))
        m.add_checkbutton(label="Montrer les entrées masquées", variable=self.v_showhidden, command=self.toggle_show_hidden)
        m.add_separator()
        m.add_command(label="Texte plus grand", accelerator="Ctrl++", command=lambda: self.zoom(1))
        m.add_command(label="Texte plus petit", accelerator="Ctrl+-", command=lambda: self.zoom(-1))
        m.add_command(label="Taille normale", accelerator="Ctrl+0", command=lambda: self.zoom(0))
        th = new_menu(m)
        self.v_theme = tk.StringVar(value=self.store.settings.get("theme", "norton"))
        for k, lab in THEME_LABELS.items():
            th.add_radiobutton(label=lab, variable=self.v_theme, value=k, command=self.change_theme)
        m.add_cascade(label="Thème", menu=th)
        self.v_ccolors = tk.BooleanVar(value=CONSOLE_COLORS[0])
        m.add_checkbutton(label="Consoles aux couleurs Norton", variable=self.v_ccolors, command=self.toggle_console_colors)
        mb.add_cascade(label="Affichage", menu=m)
        m = new_menu(mb)
        m.add_command(label="Palette de lancement rapide", accelerator="Ctrl+Espace", command=self.open_palette)
        m.add_command(label="Mon IP", command=self.show_ip)
        self.v_hotkey = tk.BooleanVar(value=bool(self.store.settings.get("global_hotkey", True)))
        m.add_checkbutton(label="Raccourci global Ctrl+Alt+Espace (même si Arsenal est caché)", variable=self.v_hotkey,
                          command=self.toggle_hotkey)
        self.v_confadmin = tk.BooleanVar(value=bool(self.store.settings.get("confirm_admin", True)))
        m.add_checkbutton(label="Montrer la commande avant chaque lancement admin", variable=self.v_confadmin,
                          command=self._save_confadmin)
        m.add_separator()
        m.add_command(label="Ouvrir arsenal.json", command=lambda: self.open_path(self.store.path, select=True))
        m.add_command(label="Voir le journal (arsenal.log)", command=self.show_log)
        m.add_command(label="Vérifier les entrées (programmes requis)", command=self.check_entries)
        mb.add_cascade(label="Outils", menu=m)
        m = new_menu(mb)
        m.add_command(label="Aide", accelerator="F1", command=self.show_help)
        m.add_command(label="À propos d'Arsenal", command=self.about)
        mb.add_cascade(label="Aide", menu=m)
        self.config(menu=mb)
        self.menubar = mb

    def _build_toolbar(self):
        tb = tk.Frame(self, bg=C["PANEL"])
        tb.pack(side="top", fill="x")
        self.f_toolbar = tb
        tk.Label(tb, text="⚡ ARSENAL", bg=C["PANEL"], fg=C["HI"], font=fnt("ArsTitle")).pack(side="left", padx=(10, 12), pady=6)
        sbox = tk.Frame(tb, bg=C["ENTRY_BG"], highlightthickness=1, highlightbackground=C["LINE"], highlightcolor=C["HI"])
        sbox.pack(side="left", pady=6)
        tk.Label(sbox, text="🔍", bg=C["ENTRY_BG"], fg=C["FG"], font=fnt("ArsUI")).pack(side="left", padx=(6, 0))
        self.v_search = tk.StringVar()
        self.e_search = tk.Entry(sbox, textvariable=self.v_search, width=30, bg=C["ENTRY_BG"], fg=C["ENTRY_FG"],
                                 insertbackground=C["HI"], relief="flat", font=fnt("ArsUI"), highlightthickness=0,
                                 selectbackground=C["SEL"], selectforeground=C["ON_SEL"])
        self.e_search.pack(side="left", padx=4, pady=3)
        self.l_ph = tk.Label(sbox, text="Rechercher… (Ctrl+F)", bg=C["ENTRY_BG"], fg=C["DIM"], font=fnt("ArsUI"), cursor="xterm")
        self.l_ph.place(in_=self.e_search, x=2, rely=0.5, anchor="w")
        self.l_ph.bind("<Button-1>", lambda _e: self.e_search.focus_set())
        b = tk.Button(sbox, text="✕", command=self.clear_search, bg=C["ENTRY_BG"], fg=C["DIM"], relief="flat", bd=0,
                      activebackground=C["SEL"], font=fnt("ArsUI"), cursor="hand2")
        b.pack(side="left", padx=(0, 4))
        Tooltip(b, "Effacer la recherche (Échap)")
        self.v_search.trace_add("write", lambda *_a: self._search_changed())
        self.e_search.bind("<Return>", lambda _e: self.launch_first())
        self.e_search.bind("<Down>", lambda _e: self._focus_items())
        self.e_search.bind("<Escape>", lambda _e: self.clear_search())
        mk_button(tb, "＋ Ajouter", self.add_entry, "accent", tip="Ajouter un lien, un programme, une commande… (Ctrl+N)").pack(
            side="left", padx=(12, 4), pady=6)
        right = tk.Frame(tb, bg=C["PANEL"])
        right.pack(side="right", padx=6)
        mk_button(right, "?", self.show_help, tip="Aide (F1)").pack(side="right", padx=3, pady=6)
        mk_button(right, "⌘ Palette", self.open_palette, tip="Lancement rapide au clavier (Ctrl+Espace)").pack(
            side="right", padx=3, pady=6)
        mk_button(right, "🌍 Mon IP", self.show_ip, tip="IP publique et locale, copiables").pack(side="right", padx=3, pady=6)
        self.b_view = mk_button(right, "", self.toggle_view_mode, tip="Changer d'affichage : tuiles ou liste")
        self.b_view.pack(side="right", padx=3, pady=6)
        self._update_view_button()

    def _update_view_button(self):
        self.b_view.configure(text="☰ Liste" if self.view_mode == "tiles" else "▦ Tuiles")

    def _build_left(self):
        f = tk.Frame(self.pw, bg=C["PANEL"])
        self.f_left = f
        h = tk.Frame(f, bg=C["PANEL"])
        h.pack(fill="x")
        tk.Label(h, text="CATÉGORIES", bg=C["PANEL"], fg=C["HI"], font=fnt("ArsHead")).pack(side="left", padx=8, pady=(6, 4))
        b = tk.Button(h, text="＋", command=self.new_category, bg=C["PANEL"], fg=C["HI"], relief="flat", bd=0,
                      activebackground=C["SEL"], font=fnt("ArsUIB"), cursor="hand2")
        b.pack(side="right", padx=6)
        Tooltip(b, "Nouvelle catégorie")
        fr = tk.Frame(f, bg=C["PANEL"])
        fr.pack(fill="both", expand=True)
        self.cat_tree = ttk.Treeview(fr, style="Cat.Treeview", show="tree", columns=("n",), selectmode="browse")
        self.cat_tree.column("#0", width=180, stretch=True)
        self.cat_tree.column("n", width=46, anchor="e", stretch=False)
        vsb = ttk.Scrollbar(fr, orient="vertical", command=self.cat_tree.yview)
        self.cat_tree.configure(yscrollcommand=vsb.set)
        self.cat_tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.cat_tree.tag_configure("special", foreground=C["HI"])
        self.cat_tree.tag_configure("cat", foreground=C["TEXT"])
        self.cat_tree.tag_configure("empty", foreground=C["DIM"])
        self.cat_tree.tag_configure("sep", foreground=C["LINE"])
        self.cat_tree.tag_configure("drop", background=C["HI"], foreground=C["ON_HI"])
        self.cat_tree.bind("<<TreeviewSelect>>", self._cat_selected)
        self.cat_tree.bind("<Button-3>", self._cat_menu)
        self.cat_tree.bind("<ButtonPress-1>", self._cat_press, add="+")
        self.cat_tree.bind("<B1-Motion>", self._cat_motion, add="+")
        self.cat_tree.bind("<ButtonRelease-1>", self._cat_release, add="+")
        self.cat_tree.bind("<F2>", lambda _e: self.rename_category())
        self.cat_tree.bind("<Alt-Up>", lambda _e: (self.move_category(-1), "break")[1])
        self.cat_tree.bind("<Alt-Down>", lambda _e: (self.move_category(1), "break")[1])
        self.cat_tree.bind("<Right>", lambda _e: (self._focus_items(), "break")[1])

    def _build_center(self):
        f = tk.Frame(self.pw, bg=C["BG"])
        self.f_center = f
        self.vpw = tk.PanedWindow(f, orient="vertical", bg=C["LINE"], sashwidth=5, bd=0, sashrelief="flat", opaqueresize=True)
        self.vpw.pack(fill="both", expand=True)
        top = tk.Frame(self.vpw, bg=C["BG"])
        self.f_items = top
        hd = tk.Frame(top, bg=C["BG"])
        hd.pack(fill="x")
        self.l_view = tk.Label(hd, text="", bg=C["BG"], fg=C["HI"], font=fnt("ArsTitle"), anchor="w")
        self.l_view.pack(side="left", padx=10, pady=(6, 2))
        self.l_hint = tk.Label(hd, text="", bg=C["BG"], fg=C["DIM"], font=fnt("ArsSM"), anchor="e")
        self.l_hint.pack(side="right", padx=10)
        self.f_view = tk.Frame(top, bg=C["BG"])
        self.f_view.pack(fill="both", expand=True)
        # tuiles
        self.f_tiles = tk.Frame(self.f_view, bg=C["BG"])
        self.canvas = tk.Canvas(self.f_tiles, bg=C["BG"], highlightthickness=0, bd=0, takefocus=1)
        self.c_vsb = ttk.Scrollbar(self.f_tiles, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.c_vsb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.c_vsb.pack(side="right", fill="y")
        cv = self.canvas
        cv.bind("<Configure>", self._canvas_configure)
        cv.bind("<ButtonPress-1>", self._tile_press)
        cv.bind("<B1-Motion>", self._drag_motion)
        cv.bind("<ButtonRelease-1>", self._drag_release)
        cv.bind("<Double-Button-1>", self._tile_double)
        cv.bind("<Button-3>", self._tile_menu)
        cv.bind("<Motion>", self._tile_hover)
        cv.bind("<Leave>", lambda _e: self._hover_set(None))
        cv.bind("<MouseWheel>", lambda e: (self.canvas.yview_scroll(int(-e.delta / 120) * 3, "units"), self._hide_tip()))
        # liste
        self.f_list = tk.Frame(self.f_view, bg=C["BG"])
        cols = ("name", "cat", "type", "desc")
        self.lst = ttk.Treeview(self.f_list, columns=cols, show="headings", selectmode="extended")
        for cid, lab, w, st in (("name", "Nom", 300, True), ("cat", "Catégorie", 210, False), ("type", "Type", 130, False),
                                ("desc", "Description", 420, False)):
            self.lst.heading(cid, text=lab, anchor="w")
            self.lst.column(cid, width=w, stretch=st, anchor="w")
        lv = ttk.Scrollbar(self.f_list, orient="vertical", command=self.lst.yview)
        lh = ttk.Scrollbar(self.f_list, orient="horizontal", command=self.lst.xview)
        self.lst.configure(yscrollcommand=lv.set, xscrollcommand=lh.set)
        self.lst.grid(row=0, column=0, sticky="nsew")
        lv.grid(row=0, column=1, sticky="ns")
        lh.grid(row=1, column=0, sticky="ew")
        self.f_list.rowconfigure(0, weight=1)
        self.f_list.columnconfigure(0, weight=1)
        self.lst.tag_configure("hidden", foreground=C["DISABLED"])
        self.lst.tag_configure("fav", foreground=C["HI"])
        self.lst.tag_configure("danger", foreground=C["WARN"])
        self.lst.tag_configure("drop", background=C["HI"], foreground=C["ON_HI"])
        self.lst.bind("<<TreeviewSelect>>", self._list_select)
        self.lst.bind("<Double-Button-1>", self._list_double)
        self.lst.bind("<Button-3>", self._list_menu)
        self.lst.bind("<ButtonPress-1>", self._list_press, add="+")
        self.lst.bind("<B1-Motion>", self._drag_motion, add="+")
        self.lst.bind("<ButtonRelease-1>", self._drag_release, add="+")
        self.vpw.add(top, stretch="always", minsize=160)
        self._build_result()
        self._show_view_widget()

    def _build_result(self):
        r = tk.Frame(self.vpw, bg=C["PANEL"])
        self.f_result = r
        hd = tk.Frame(r, bg=C["PANEL"])
        hd.pack(fill="x")
        for text, cmd, tip in (("▾", self.hide_result, "Fermer le panneau Résultat"),
                               ("🧹", self.clear_result, "Effacer le résultat"),
                               ("💾", self.save_result, "Enregistrer le résultat dans un fichier .txt"),
                               ("📋 Copier", self.copy_result, "Copier tout le résultat"),
                               ("■ Arrêter", self.stop_capture, "Arrêter la commande en cours")):
            b = mk_button(hd, text, cmd, tip=tip, font_name="ArsSM")
            b.configure(pady=1, padx=6)
            b.pack(side="right", padx=2, pady=2)
            if text.startswith("■"):
                self.b_stop = b
        self.l_result = tk.Label(hd, text="Résultat", bg=C["PANEL"], fg=C["HI"], font=fnt("ArsUIB"), anchor="w")
        self.l_result.pack(side="left", padx=8, pady=3, fill="x", expand=True)
        fr = tk.Frame(r, bg=C["PANEL"])
        fr.pack(fill="both", expand=True)
        self.t_result = tk.Text(fr, bg=C["IMG_BG"], fg=C["TEXT"], font=fnt("ArsMono"), wrap="none", relief="flat",
                                highlightthickness=0, insertbackground=C["HI"], selectbackground=C["SEL"],
                                selectforeground=C["ON_SEL"], padx=8, pady=4)
        vs = ttk.Scrollbar(fr, orient="vertical", command=self.t_result.yview)
        hs = ttk.Scrollbar(fr, orient="horizontal", command=self.t_result.xview)
        self.t_result.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        self.t_result.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")
        hs.grid(row=1, column=0, sticky="ew")
        fr.rowconfigure(0, weight=1)
        fr.columnconfigure(0, weight=1)
        self.t_result.tag_configure("cmd", foreground=C["HI"])
        self.t_result.tag_configure("ok", foreground=C["OK"])
        self.t_result.tag_configure("err", foreground=C["ERR"])
        self.t_result.bind("<Key>", lambda e: None if (e.state & 0x4 and e.keysym.lower() in ("c", "a")) or
                           e.keysym in ("Left", "Right", "Up", "Down", "Prior", "Next", "Home", "End") else "break")
        self.result_shown = False

    def _build_right(self):
        f = tk.Frame(self.pw, bg=C["PANEL"])
        self.f_right = f
        self.detail = ScrollFrame(f, bg=C["PANEL"])
        self.detail.pack(fill="both", expand=True)

    def _show_view_widget(self):
        if self.view_mode == "list":
            self.f_tiles.pack_forget()
            self.f_list.pack(fill="both", expand=True)
        else:
            self.f_list.pack_forget()
            self.f_tiles.pack(fill="both", expand=True)

    def _bind_keys(self):
        b = self.bind
        b("<Control-f>", lambda _e: self.focus_search())
        b("<Control-F>", lambda _e: self.focus_search())
        b("<Control-space>", lambda _e: (self.open_palette(), "break")[1])
        b("<F1>", lambda _e: self.show_help())
        b("<Control-n>", lambda _e: self.add_entry())
        b("<Control-z>", lambda _e: self._unless_entry(self.do_undo))
        b("<Control-y>", lambda _e: self._unless_entry(self.do_redo))
        b("<F5>", lambda _e: self.refresh_all())
        b("<Control-plus>", lambda _e: self.zoom(1))
        b("<Control-equal>", lambda _e: self.zoom(1))
        b("<Control-KP_Add>", lambda _e: self.zoom(1))
        b("<Control-minus>", lambda _e: self.zoom(-1))
        b("<Control-KP_Subtract>", lambda _e: self.zoom(-1))
        b("<Control-0>", lambda _e: self.zoom(0))
        b("<Control-l>", lambda _e: self.toggle_view_mode())
        for w in (self.canvas, self.lst):
            w.bind("<Return>", lambda _e: self.launch_selected())
            w.bind("<Control-Return>", lambda _e: self.launch_selected(admin=True))
            w.bind("<Delete>", lambda _e: self.delete_selected())
            w.bind("<F2>", lambda _e: self.start_rename())
            w.bind("<Control-e>", lambda _e: self.edit_entry())
            w.bind("<Control-d>", lambda _e: self.duplicate())
            w.bind("<Control-m>", lambda _e: self.move_dialog())
            w.bind("<Control-b>", lambda _e: self.toggle_fav())
            w.bind("<Control-h>", lambda _e: self.toggle_hidden())
            w.bind("<Control-c>", lambda _e: self.copy_command())
            w.bind("<Control-a>", lambda _e: (self.select_all(), "break")[1])
            w.bind("<Alt-Up>", lambda _e: (self.move_step(-1), "break")[1])
            w.bind("<Alt-Down>", lambda _e: (self.move_step(1), "break")[1])
            w.bind("<Escape>", lambda _e: self.clear_search() if self.v_search.get() else self.select_ids([]))
            w.bind("<Key>", self._type_to_search, add="+")
        for k in ("Left", "Right", "Up", "Down", "Home", "End", "Prior", "Next"):
            self.canvas.bind(f"<{k}>", lambda *_a, kk=k: self._tile_key(kk, None))
            self.canvas.bind(f"<Shift-{k}>", lambda *_a, kk=k: self._tile_key(kk, None, shift=True))

    def _unless_entry(self, fn):
        w = self.focus_get()
        if isinstance(w, (tk.Entry, tk.Text, ttk.Entry)) and w is not self.t_result:
            return None
        fn()
        return "break"

    def _type_to_search(self, e):
        if e.state & 0x4 or e.state & 0x20000 or e.state & 0x8:
            return None
        ch = e.char
        if ch and ch.isprintable() and len(ch) == 1 and ch != " ":
            self.e_search.focus_set()
            self.e_search.insert("end", ch)
            return "break"
        if e.keysym == "BackSpace" and self.v_search.get():
            self.e_search.focus_set()
            self.v_search.set(self.v_search.get()[:-1])
            self.e_search.icursor("end")
            return "break"
        return None

    def _setup_dnd(self):
        try:
            import tkinterdnd2  # type: ignore
            from tkinterdnd2 import DND_FILES, DND_TEXT  # type: ignore
            if not getattr(self, "_dnd_ok", False):
                tkinterdnd2.TkinterDnD._require(self)
                self._dnd_ok = True
            for w in (self.canvas, self.lst, self.cat_tree):
                w.drop_target_register(DND_FILES, DND_TEXT)
                w.dnd_bind("<<Drop>>", self._on_drop)
        except Exception as ex:
            self._dnd_ok = False
            logger.info("glisser-déposer externe indisponible : %s", ex)

    # ------------------------------------------------------------ donnees visibles
    def _cat_order(self) -> Dict[str, int]:
        return {c["id"]: i for i, c in enumerate(self.store.categories)}

    def compute_visible(self) -> None:
        st = self.store
        show_h = self.v_showhidden.get()
        q = self.v_search.get().strip()
        cord = self._cat_order()
        rows: List[Tuple[str, Any]] = []
        ents = st.entries
        if q:
            toks = [norm(t) for t in q.split() if t.strip()]
            scored = []
            for e in ents:
                if e.get("hidden") and not show_h and self.cur_view != "@hidden":
                    continue
                sc = search_score(e, toks, st.cat_name(e["category"]))
                if sc:
                    scored.append((-sc, cord.get(e["category"], 99), e["order"], e))
            scored.sort(key=lambda x: x[:3])
            vis = [x[3] for x in scored]
            rows = [("e", e) for e in vis]
        else:
            v = self.cur_view
            if v == "@hidden":
                vis = [e for e in ents if e.get("hidden")]
            else:
                vis = [e for e in ents if show_h or not e.get("hidden")]
            if v == "@fav":
                vis = sorted([e for e in vis if e.get("fav")], key=lambda e: (cord.get(e["category"], 99), e["order"]))
            elif v == "@recent":
                vis = sorted([e for e in vis if e.get("last_used")], key=lambda e: e["last_used"], reverse=True)[:60]
            elif v == "@top":
                vis = sorted([e for e in vis if e.get("uses")], key=lambda e: (-e["uses"], e["name"]))[:60]
            elif v in ("@all", "@hidden"):
                vis = sorted(vis, key=lambda e: (cord.get(e["category"], 99), e["order"]))
            elif v.startswith("c:"):
                cid = v[2:]
                vis = sorted([e for e in vis if e["category"] == cid], key=lambda e: e["order"])
            if v in ("@fav", "@all", "@hidden"):
                last = None
                for e in vis:
                    if e["category"] != last:
                        rows.append(("h", st.cat_name(e["category"], True)))
                        last = e["category"]
                    rows.append(("e", e))
            elif v.startswith("c:"):
                last = None
                for e in vis:
                    g = e.get("group") or ""
                    if g != last:
                        if g or last is not None:
                            rows.append(("h", g or "Divers"))
                        last = g
                    rows.append(("e", e))
            else:
                rows = [("e", e) for e in vis]
        self.visible = vis
        self.rows = rows
        ids = {e["id"] for e in vis}
        self.selected = [i for i in self.selected if i in ids]

    def can_reorder(self) -> bool:
        return self.cur_view.startswith("c:") and not self.v_search.get().strip()

    def view_title(self) -> str:
        q = self.v_search.get().strip()
        n = len(self.visible)
        if q:
            return f"🔍 « {q} » — {n} résultat{'s' if n != 1 else ''}"
        v = self.cur_view
        for k, ic, lab in SPECIAL_VIEWS:
            if k == v:
                return f"{ic} {lab} — {n}"
        if v.startswith("c:"):
            return f"{self.store.cat_name(v[2:], True)} — {n}"
        return f"{n}"

    # ------------------------------------------------------------ rafraichissements
    def refresh_all(self, first: bool = False) -> None:
        self.refresh_cats()
        self.refresh_items()
        if first:
            if self.view_mode == "tiles":
                self.canvas.focus_set()
            else:
                self.lst.focus_set()
            if not any(e.get("fav") for e in self.store.entries) and self.cur_view == "@fav":
                self.select_view("c:mes_outils")

    def refresh_cats(self) -> None:
        t = self.cat_tree
        t.delete(*t.get_children())
        ents = self.store.entries
        show_h = self.v_showhidden.get()
        counts: Dict[str, int] = {}
        for e in ents:
            if e.get("hidden") and not show_h:
                continue
            counts[e["category"]] = counts.get(e["category"], 0) + 1
        sp = {"@fav": sum(1 for e in ents if e.get("fav") and (show_h or not e.get("hidden"))),
              "@recent": min(60, sum(1 for e in ents if e.get("last_used"))),
              "@top": min(60, sum(1 for e in ents if e.get("uses"))),
              "@all": sum(counts.values()),
              "@hidden": sum(1 for e in ents if e.get("hidden"))}
        for k, ic, lab in SPECIAL_VIEWS:
            t.insert("", "end", iid=k, text=f" {ic}  {lab}", values=(sp.get(k, 0),), tags=("special",))
        t.insert("", "end", iid="@sep", text=" ─────────────", values=("",), tags=("sep",))
        for c in self.store.categories:
            n = counts.get(c["id"], 0)
            t.insert("", "end", iid="c:" + c["id"], text=f" {c.get('icon', '📂')}  {c['name']}", values=(n,),
                     tags=("cat" if n else "empty",))
        if t.exists(self.cur_view):
            t.selection_set(self.cur_view)
            t.see(self.cur_view)
        total = len(ents)
        self.l_count.configure(text=f"{total} entrées · {len(self.store.categories)} catégories · Ctrl+Espace : palette · F1 : aide")

    def refresh_items(self, keep: bool = False) -> None:
        self.compute_visible()
        self.l_view.configure(text=self.view_title())
        self.l_hint.configure(text="Glisser : réordonner · F2 : renommer" if self.can_reorder()
                              else ("Entrée = lancer · Ctrl+Entrée = admin" if self.visible else ""))
        self.after_idle(self._fit_hint)
        if self.view_mode == "tiles":
            y = self.canvas.yview()[0] if keep else 0.0
            self.draw_tiles()
            self.canvas.yview_moveto(y)
        else:
            self.fill_list()
        self.update_detail()

    def _fit_hint(self):
        try:
            hd = self.l_view.master
            need = self.l_view.winfo_reqwidth() + self.l_hint.winfo_reqwidth() + 40
            if need > hd.winfo_width() or not self.l_hint.cget("text"):
                self.l_hint.pack_forget()
            elif not self.l_hint.winfo_ismapped():
                self.l_hint.pack(side="right", padx=10)
        except tk.TclError:
            pass

    def select_view(self, v: str) -> None:
        self.cur_view = v
        self.store.settings["last_view"] = v
        if self.v_search.get():
            self.v_search.set("")
        self.selected = []
        if self.cat_tree.exists(v):
            self.cat_tree.selection_set(v)
            self.cat_tree.see(v)
        self.refresh_items()

    def _cat_selected(self, _e=None):
        sel = self.cat_tree.selection()
        if not sel:
            return
        v = sel[0]
        if v == "@sep":
            self.cat_tree.selection_set(self.cur_view) if self.cat_tree.exists(self.cur_view) else None
            return
        if v != self.cur_view or self.v_search.get():
            self.select_view(v)

    # ------------------------------------------------------------ tuiles
    def tile_metrics(self) -> Tuple[int, int, int, int]:
        f1 = fnt("ArsTile")
        f2 = fnt("ArsTileD")
        lh1 = f1.metrics("linespace") if hasattr(f1, "metrics") else 16
        lh2 = f2.metrics("linespace") if hasattr(f2, "metrics") else 14
        cw = f1.measure("M") if hasattr(f1, "measure") else 8
        tw = max(200, cw * 22 + 60)
        th = lh1 * 2 + lh2 + 20
        return tw, th, 10, 8   # largeur min, hauteur, marge, ecart

    def draw_tiles(self) -> None:
        cv = self.canvas
        cv.delete("all")
        self.tiles = []
        self._hide_tip()
        W = max(cv.winfo_width(), 200)
        tw, th, pad, gap = self.tile_metrics()
        cols = max(1, (W - 2 * pad + gap) // (tw + gap))
        tw = min(int(tw * 1.7), (W - 2 * pad - (cols - 1) * gap) // cols)
        hh = fnt("ArsHead").metrics("linespace") + 14 if hasattr(fnt("ArsHead"), "metrics") else 26
        y = pad
        col = 0
        sel = set(self.selected)
        if not self.rows:
            msg = "Aucune entrée ici." if not self.v_search.get() else "Aucun résultat."
            sub = ("Clique « ＋ Ajouter », glisse un fichier ou un lien ici, ou choisis une autre catégorie."
                   if self.cur_view != "@fav" else
                   "Ajoute des favoris : clic droit sur une entrée → « Favori », ou Ctrl+B.")
            cv.create_text(W // 2, 60, text=msg, fill=C["HI"], font=fnt("ArsTitle"))
            cv.create_text(W // 2, 92, text=sub, fill=C["DIM"], font=fnt("ArsUI"), width=W - 40, justify="center")
            cv.configure(scrollregion=(0, 0, W, 140))
            return
        for kind, item in self.rows:
            if kind == "h":
                if col:
                    y += th + gap
                    col = 0
                cv.create_text(pad + 2, y + 4, text=item, anchor="nw", fill=C["HI"], font=fnt("ArsHead"))
                cv.create_line(pad, y + hh - 6, W - pad, y + hh - 6, fill=C["LINE"])
                y += hh
                continue
            x = pad + col * (tw + gap)
            self._draw_tile(item, x, y, tw, th, item["id"] in sel, len(self.tiles))
            self.tiles.append((x, y, x + tw, y + th, item["id"]))
            col += 1
            if col >= cols:
                col = 0
                y += th + gap
        if col:
            y += th + gap
        cv.configure(scrollregion=(0, 0, W, y + pad))
        self._tile_cols = cols

    def _tile_desc(self, e) -> str:
        if e["type"] == "builtin" and e["target"] == "myip" and self.ip_cache:
            pub = self.ip_cache.get("public") or "?"
            return f"Publique {pub} · Locale {self.ip_cache.get('local') or '?'}"
        return e.get("desc") or e.get("target", "")

    def _draw_tile(self, e, x, y, tw, th, selected, idx):
        cv = self.canvas
        hidden = e.get("hidden")
        fill = C["SEL"] if selected else (C["HOVER"] if e["id"] == self.hover_eid else
                                          (C["CARD_FAV"] if e.get("fav") else C["CARD"]))
        outline = C["HI"] if selected else C["LINE"]
        tg = f"T{idx}"
        cv.create_rectangle(x, y, x + tw, y + th, fill=fill, outline=outline, width=2 if selected else 1,
                            tags=("tile", tg, "R" + tg))
        fg = C["ON_SEL"] if selected else (C["DISABLED"] if hidden else C["TEXT"])
        dim = C["ON_SEL"] if selected else C["DIM"]
        img = self.icon_image(e.get("icon_file", ""), 32) if e.get("icon_file") else None
        if img is not None:
            cv.create_image(x + 26, y + th // 2, image=img, tags=("tile", tg))
        else:
            cv.create_text(x + 26, y + th // 2, text=e.get("icon") or TYPES[e["type"]]["icon"], font=fnt("ArsEmoji"),
                           fill=C["ON_SEL"] if selected else C["HI"], tags=("tile", tg))
        badges = ("★" if e.get("fav") else "") + ("🛡" if e.get("admin") else "") + ("⚠" if e.get("danger") else "") + \
                 ("👁" if hidden else "")
        bw = fnt("ArsSM").measure(badges) + 8 if badges and hasattr(fnt("ArsSM"), "measure") else 0
        if badges:
            cv.create_text(x + tw - 5, y + 4, text=badges, anchor="ne", font=fnt("ArsSM"),
                           fill=C["ON_SEL"] if selected else (C["WARN"] if e.get("danger") else C["HI"]), tags=("tile", tg))
        tx = x + 52
        avail = tw - 58
        name = self.fit(e.get("name", ""), "ArsTile", avail - bw, 1)
        if fnt("ArsTile").measure(e.get("name", "")) > avail - bw:
            name = self.fit(e.get("name", ""), "ArsTile", avail - bw, 2)
        cv.create_text(tx, y + 7, text=name, anchor="nw", font=fnt("ArsTile"), fill=fg, tags=("tile", tg))
        nlines = name.count("\n") + 1
        desc = self.fit(self._tile_desc(e), "ArsTileD", avail, 2 if nlines == 1 else 1)
        cv.create_text(tx, y + th - 6, text=desc, anchor="sw", font=fnt("ArsTileD"), fill=dim, tags=("tile", tg))

    def _canvas_configure(self, e):
        w = e.width
        if getattr(self, "_last_cw", 0) != w:
            self._last_cw = w
            if self.view_mode == "tiles":
                if getattr(self, "_cfg_job", None):
                    self.after_cancel(self._cfg_job)
                self._cfg_job = self.after(60, lambda: self.draw_tiles())

    def tile_at(self, x: int, y: int) -> Optional[Tuple[int, str]]:
        cx, cy = self.canvas.canvasx(x), self.canvas.canvasy(y)
        for i, (x0, y0, x1, y1, eid) in enumerate(self.tiles):
            if x0 <= cx <= x1 and y0 <= cy <= y1:
                return i, eid
        return None

    def _tile_press(self, e):
        self.canvas.focus_set()
        self._hide_tip()
        self._end_rename(commit=True)
        hit = self.tile_at(e.x, e.y)
        ctrl, shift = bool(e.state & 0x4), bool(e.state & 0x1)
        if not hit:
            if not ctrl:
                self.select_ids([])
            self.press = None
            return
        _, eid = hit
        self._press_select(eid, ctrl, shift)
        self.press = {"eid": eid, "x": e.x_root, "y": e.y_root, "ctrl": ctrl, "shift": shift, "src": "tiles"}

    def _press_select(self, eid, ctrl, shift):
        if ctrl:
            sel = list(self.selected)
            if eid in sel:
                sel.remove(eid)
            else:
                sel.append(eid)
            self.anchor = eid
            self.select_ids(sel, keep_anchor=True)
        elif shift and self.anchor:
            order = [x["id"] for x in self.visible]
            if self.anchor in order and eid in order:
                a, b = sorted((order.index(self.anchor), order.index(eid)))
                self.select_ids(order[a:b + 1], keep_anchor=True)
        elif eid not in self.selected:
            self.select_ids([eid])

    def _tile_double(self, e):
        hit = self.tile_at(e.x, e.y)
        if hit:
            ent = self.store.by_id(hit[1])
            if ent:
                self.launch(ent)

    def _tile_menu(self, e):
        hit = self.tile_at(e.x, e.y)
        if hit and hit[1] not in self.selected:
            self.select_ids([hit[1]])
        if not hit:
            self.select_ids([])
        self.context_menu(e.x_root, e.y_root)

    def _tile_hover(self, e):
        if self.drag:
            return
        hit = self.tile_at(e.x, e.y)
        self._hover_set(hit[1] if hit else None, e)

    def _hover_set(self, eid, ev=None):
        if eid == self.hover_eid:
            return
        old = self.hover_eid
        self.hover_eid = eid
        for i, t in enumerate(self.tiles):
            if t[4] in (old, eid) and t[4] not in self.selected:
                ent = self.store.by_id(t[4])
                if not ent:
                    continue
                col = C["HOVER"] if t[4] == eid else (C["CARD_FAV"] if ent.get("fav") else C["CARD"])
                self.canvas.itemconfigure(f"RT{i}", fill=col)
        self._hide_tip()
        if eid and ev is not None:
            xr, yr = ev.x_root, ev.y_root
            self.tip_job = self.after(750, lambda: self._show_tile_tip(eid, xr, yr))

    def _show_tile_tip(self, eid, xr, yr):
        e = self.store.by_id(eid)
        if not e or self.drag:
            return
        spec = build_launch(e)
        cmdline = spec.get("display", "")
        if len(cmdline) > 300:
            cmdline = cmdline[:300] + "…"
        txt = f"{e['name']}\n{self._tile_desc(e)}\n\n{cmdline}".strip()
        self._hide_tip()
        self.tip_win = show_tip(self, txt, xr + 16, yr + 20)

    def _hide_tip(self):
        if self.tip_job:
            try:
                self.after_cancel(self.tip_job)
            except Exception:
                pass
            self.tip_job = None
        if self.tip_win is not None:
            try:
                self.tip_win.destroy()
            except Exception:
                pass
            self.tip_win = None

    def _tile_key(self, k, e, shift=False):
        order = [x["id"] for x in self.visible]
        if not order:
            return "break"
        cur = self.selected[-1] if self.selected else None
        i = order.index(cur) if cur in order else -1
        cols = getattr(self, "_tile_cols", 1)
        if self.v_search.get() or not self.rows or any(k_ == "h" for k_, _ in self.rows):
            # avec des en-tetes, haut/bas se deplacent par rangee visuelle
            pass
        step = {"Left": -1, "Right": 1, "Up": -cols, "Down": cols, "Prior": -cols * 4, "Next": cols * 4}.get(k, 0)
        if k in ("Up", "Down") and self.tiles and i >= 0:
            x0, y0, x1, y1, _ = self.tiles[i]
            cx = (x0 + x1) / 2
            cands = [(j, t) for j, t in enumerate(self.tiles) if (t[1] > y0 if k == "Down" else t[1] < y0)]
            if cands:
                ty = min(t[1] for _, t in cands) if k == "Down" else max(t[1] for _, t in cands)
                row = [(abs((t[0] + t[2]) / 2 - cx), j) for j, t in cands if t[1] == ty]
                ni = min(row)[1]
            else:
                ni = i
        elif k == "Home":
            ni = 0
        elif k == "End":
            ni = len(order) - 1
        else:
            ni = max(0, min(len(order) - 1, (i if i >= 0 else 0) + step if i >= 0 else 0))
        nid = order[ni]
        if shift and self.anchor in order:
            a, b = sorted((order.index(self.anchor), ni))
            self.select_ids(order[a:b + 1], keep_anchor=True)
        else:
            self.select_ids([nid])
        self.see_tile(nid)
        return "break"

    def see_tile(self, eid):
        if self.view_mode != "tiles":
            if self.lst.exists(eid):
                self.lst.see(eid)
            return
        for x0, y0, x1, y1, i in self.tiles:
            if i == eid:
                sr = self.canvas.cget("scrollregion").split()
                total = float(sr[3]) if len(sr) == 4 else 1.0
                h = self.canvas.winfo_height()
                top = self.canvas.canvasy(0)
                if y0 < top + 4:
                    self.canvas.yview_moveto(max(0.0, (y0 - 30) / total))
                elif y1 > top + h - 4:
                    self.canvas.yview_moveto(max(0.0, (y1 - h + 10) / total))
                return

    # ------------------------------------------------------------ selection
    def select_ids(self, ids: List[str], keep_anchor: bool = False) -> None:
        self.selected = list(dict.fromkeys(ids))
        if not keep_anchor:
            self.anchor = self.selected[-1] if self.selected else None
        if self.view_mode == "tiles":
            self._redraw_selection()
        else:
            self._syncing = True
            try:
                exist = [i for i in self.selected if self.lst.exists(i)]
                self.lst.selection_set(exist)
                if exist:
                    self.lst.focus(exist[-1])
                    self.lst.see(exist[-1])
            finally:
                self.after_idle(lambda: setattr(self, "_syncing", False))
        self.update_detail()

    def _redraw_selection(self):
        y = self.canvas.yview()[0]
        self.draw_tiles()
        self.canvas.yview_moveto(y)

    def select_all(self):
        self.select_ids([e["id"] for e in self.visible])

    def sel_entries(self) -> List[Dict[str, Any]]:
        out = []
        for i in self.selected:
            e = self.store.by_id(i)
            if e:
                out.append(e)
        return out

    def _focus_items(self):
        if self.view_mode == "tiles":
            self.canvas.focus_set()
        else:
            self.lst.focus_set()
        if not self.selected and self.visible:
            self.select_ids([self.visible[0]["id"]])
        return "break"

    # ------------------------------------------------------------ liste
    def fill_list(self) -> None:
        t = self.lst
        t.delete(*t.get_children())
        for e in self.visible:
            tags = []
            if e.get("hidden"):
                tags.append("hidden")
            elif e.get("danger"):
                tags.append("danger")
            elif e.get("fav"):
                tags.append("fav")
            badge = (" ★" if e.get("fav") else "") + (" 🛡" if e.get("admin") else "") + (" ⚠" if e.get("danger") else "")
            grp = self.store.cat_name(e["category"]) + (f" › {e['group']}" if e.get("group") else "")
            t.insert("", "end", iid=e["id"], values=(f"{e.get('icon', '')}  {e['name']}{badge}", grp,
                                                     TYPES[e["type"]]["label"], self._tile_desc(e).replace("\n", " ")),
                     tags=tags)
        exist = [i for i in self.selected if t.exists(i)]
        if exist:
            self._syncing = True
            t.selection_set(exist)
            t.see(exist[-1])
            self.after_idle(lambda: setattr(self, "_syncing", False))

    def _list_select(self, _e=None):
        if getattr(self, "_syncing", False):
            return
        self.selected = list(self.lst.selection())
        self.anchor = self.selected[-1] if self.selected else None
        self.update_detail()

    def _list_double(self, e):
        iid = self.lst.identify_row(e.y)
        if iid and self.lst.identify_region(e.x, e.y) != "heading":
            ent = self.store.by_id(iid)
            if ent:
                self.launch(ent)
                return "break"
        return None

    def _list_menu(self, e):
        iid = self.lst.identify_row(e.y)
        if iid and iid not in self.lst.selection():
            self.lst.selection_set(iid)
            self._list_select()
        self.context_menu(e.x_root, e.y_root)

    def _list_press(self, e):
        self._end_rename(commit=True)
        iid = self.lst.identify_row(e.y)
        self.press = {"eid": iid, "x": e.x_root, "y": e.y_root, "src": "list"} if iid else None

    # ------------------------------------------------------------ glisser-deposer interne
    def _drag_motion(self, e):
        p = self.press
        if not p or not p.get("eid"):
            return
        if not self.drag:
            if abs(e.x_root - p["x"]) + abs(e.y_root - p["y"]) < 8:
                return
            ids = list(self.selected) if p["eid"] in self.selected else [p["eid"]]
            if p["src"] == "list":
                ids = list(self.lst.selection()) or [p["eid"]]
            first = self.store.by_id(ids[0])
            label = f"⇅ {first['name']}" if len(ids) == 1 and first else f"⇅ {len(ids)} entrées"
            tw = tk.Toplevel(self)
            tw.wm_overrideredirect(True)
            try:
                tw.attributes("-topmost", True)
                tw.attributes("-alpha", 0.9)
            except tk.TclError:
                pass
            tk.Label(tw, text=label, bg=C["HI"], fg=C["ON_HI"], font=fnt("ArsUIB"), padx=8, pady=3).pack()
            self.drag = {"ids": ids, "win": tw, "target": None}
            self._hide_tip()
        self.drag["win"].wm_geometry(f"+{e.x_root + 14}+{e.y_root + 10}")
        self._drag_feedback(e.x_root, e.y_root)
        return "break" if p["src"] == "list" else None

    def _drop_target(self, xr: int, yr: int):
        w = self.winfo_containing(xr, yr)
        if w is self.cat_tree:
            iid = self.cat_tree.identify_row(yr - self.cat_tree.winfo_rooty())
            if iid and iid != "@sep":
                return ("cat", iid)
            return None
        if w is self.canvas and self.can_reorder():
            x, y = xr - self.canvas.winfo_rootx(), yr - self.canvas.winfo_rooty()
            hit = self.tile_at(x, y)
            if hit:
                i, eid = hit
                x0, y0, x1, y1, _ = self.tiles[i]
                before = self.canvas.canvasx(x) < (x0 + x1) / 2
                return ("tile", eid, before, i)
            return None
        if w is self.lst and self.can_reorder():
            y = yr - self.lst.winfo_rooty()
            iid = self.lst.identify_row(y)
            if iid:
                bb = self.lst.bbox(iid)
                before = bool(bb) and y < bb[1] + bb[3] / 2
                return ("row", iid, before)
        return None

    def _drag_feedback(self, xr, yr):
        tgt = self._drop_target(xr, yr)
        old = self.drag.get("target")
        if old == tgt:
            return
        self._clear_drop_marks()
        self.drag["target"] = tgt
        if not tgt:
            return
        if tgt[0] == "cat":
            self.cat_tree.item(tgt[1], tags=("drop",))
        elif tgt[0] == "tile":
            x0, y0, x1, y1, _ = self.tiles[tgt[3]]
            xx = x0 - 5 if tgt[2] else x1 + 5
            self.canvas.create_line(xx, y0 - 2, xx, y1 + 2, fill=C["HI"], width=4, tags=("marker",))
        elif tgt[0] == "row":
            self.lst.item(tgt[1], tags=("drop",))

    def _clear_drop_marks(self):
        self.canvas.delete("marker")
        for iid in self.cat_tree.get_children():
            tags = self.cat_tree.item(iid, "tags")
            if "drop" in tags:
                n = self.cat_tree.set(iid, "n")
                self.cat_tree.item(iid, tags=("special",) if iid.startswith("@") else ("cat" if str(n) not in ("0", "") else "empty",))
        for iid in self.lst.tag_has("drop"):
            e = self.store.by_id(iid)
            self.lst.item(iid, tags=("hidden",) if e and e.get("hidden") else ())

    def _drag_release(self, e):
        d = self.drag
        p = self.press
        self.press = None
        if not d:
            if p and p.get("src") == "tiles" and not p.get("ctrl") and not p.get("shift") and len(self.selected) > 1:
                self.select_ids([p["eid"]])
            return None
        self.drag = None
        try:
            d["win"].destroy()
        except Exception:
            pass
        tgt = d.get("target")
        self._clear_drop_marks()
        if not tgt:
            return None
        ids = d["ids"]
        if tgt[0] == "cat":
            v = tgt[1]
            if v.startswith("c:"):
                self.move_to(ids, v[2:])
            elif v == "@fav":
                self.set_flag(ids, "fav", True, "Ajout aux favoris")
            elif v == "@hidden":
                self.set_flag(ids, "hidden", True, "Masquage")
            else:
                self.set_status("Dépose sur une catégorie, sur ⭐ Favoris ou sur 👁 Masquées.")
        elif tgt[0] in ("tile", "row"):
            self.reorder_drop(ids, tgt[1], tgt[2])
        return "break"

    def reorder_drop(self, ids: List[str], target_id: str, before: bool) -> None:
        if target_id in ids or not self.can_reorder():
            return
        cid = self.cur_view[2:]
        tgt = self.store.by_id(target_id)
        if not tgt:
            return
        self.mutate("Réorganisation")
        order = [e["id"] for e in sorted([e for e in self.store.entries if e["category"] == cid], key=lambda e: e["order"])]
        moving = [i for i in order if i in ids]
        rest = [i for i in order if i not in ids]
        pos = rest.index(target_id) + (0 if before else 1)
        new = rest[:pos] + moving + rest[pos:]
        for i in moving:
            e = self.store.by_id(i)
            if e:
                e["group"] = tgt.get("group", "")
        self.store.reorder(cid, new)
        self.save_soon()
        self.refresh_items(keep=True)
        self.set_status(f"{len(moving)} entrée(s) déplacée(s). Ctrl+Z pour annuler.")

    # ------------------------------------------------------------ categories (glisser pour reordonner)
    def _cat_press(self, e):
        iid = self.cat_tree.identify_row(e.y)
        self._cat_drag = {"iid": iid, "y": e.y_root, "on": False} if iid and iid.startswith("c:") else None

    def _cat_motion(self, e):
        d = getattr(self, "_cat_drag", None)
        if not d:
            return None
        if not d["on"] and abs(e.y_root - d["y"]) > 8:
            d["on"] = True
            self.cat_tree.configure(cursor="sb_v_double_arrow")
        if d["on"]:
            iid = self.cat_tree.identify_row(e.y)
            self._clear_drop_marks()
            if iid and iid.startswith("c:") and iid != d["iid"]:
                self.cat_tree.item(iid, tags=("drop",))
            return "break"
        return None

    def _cat_release(self, e):
        d = getattr(self, "_cat_drag", None)
        self._cat_drag = None
        self.cat_tree.configure(cursor="")
        if not d or not d["on"]:
            return None
        self._clear_drop_marks()
        iid = self.cat_tree.identify_row(e.y)
        if not iid or not iid.startswith("c:") or iid == d["iid"]:
            return "break"
        cats = self.store.categories
        src = next((c for c in cats if c["id"] == d["iid"][2:]), None)
        if not src:
            return "break"
        self.mutate("Ordre des catégories")
        cats.remove(src)
        idx = next(i for i, c in enumerate(cats) if c["id"] == iid[2:])
        bb = self.cat_tree.bbox(iid)
        if bb and e.y > bb[1] + bb[3] / 2:
            idx += 1
        cats.insert(idx, src)
        self.store.dirty = True
        self.save_soon()
        self.refresh_cats()
        self.set_status(f"Catégorie « {src['name']} » déplacée. Ctrl+Z pour annuler.")
        return "break"

    def _cat_menu(self, e):
        iid = self.cat_tree.identify_row(e.y)
        if iid and iid != "@sep":
            self.cat_tree.selection_set(iid)
        m = new_menu(self)
        is_cat = bool(iid and iid.startswith("c:"))
        m.add_command(label="＋ Ajouter une entrée ici…", command=self.add_entry)
        m.add_command(label="Nouvelle catégorie…", command=self.new_category)
        if is_cat:
            m.add_separator()
            m.add_command(label="Renommer / changer l'emoji…", accelerator="F2", command=self.rename_category)
            m.add_command(label="Monter", accelerator="Alt+Haut", command=lambda: self.move_category(-1))
            m.add_command(label="Descendre", accelerator="Alt+Bas", command=lambda: self.move_category(1))
            m.add_command(label="Exporter cette catégorie (JSON)…", command=lambda: self.export_category(iid[2:]))
            m.add_separator()
            m.add_command(label="Supprimer la catégorie…", command=self.delete_category)
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()

    def cur_cat_id(self) -> str:
        return self.cur_view[2:] if self.cur_view.startswith("c:") else ""

    def create_category(self, name: str, icon: str) -> str:
        base = _slug(name) or "categorie"
        cid = base
        n = 2
        while self.store.cat(cid):
            cid = f"{base}_{n}"
            n += 1
        self.mutate("Nouvelle catégorie")
        self.store.categories.append({"id": cid, "name": name, "icon": icon})
        self.store.dirty = True
        self.save_soon()
        self.refresh_cats()
        return cid

    def new_category(self):
        r = CategoryDialog(self, "Nouvelle catégorie").wait()
        if r:
            cid = self.create_category(*r)
            self.select_view("c:" + cid)
            self.set_status(f"Catégorie « {r[0]} » créée. Glisse des entrées dessus ou clique « ＋ Ajouter ».")

    def rename_category(self):
        cid = self.cur_cat_id()
        c = self.store.cat(cid) if cid else None
        if not c:
            self.set_status("Choisis d'abord une catégorie (à gauche).")
            return
        r = CategoryDialog(self, "Renommer la catégorie", c["name"], c.get("icon", "📂")).wait()
        if r:
            self.mutate("Renommage de catégorie")
            c["name"], c["icon"] = r
            self.store.dirty = True
            self.save_soon()
            self.refresh_all()

    def move_category(self, delta: int):
        cid = self.cur_cat_id()
        cats = self.store.categories
        idx = next((i for i, c in enumerate(cats) if c["id"] == cid), -1)
        j = idx + delta
        if idx < 0 or not 0 <= j < len(cats):
            return
        self.mutate("Ordre des catégories")
        cats[idx], cats[j] = cats[j], cats[idx]
        self.store.dirty = True
        self.save_soon()
        self.refresh_cats()

    def delete_category(self):
        cid = self.cur_cat_id()
        c = self.store.cat(cid) if cid else None
        if not c:
            return
        ents = [e for e in self.store.entries if e["category"] == cid]
        if ents:
            r = messagebox.askyesnocancel(
                APP_NAME, f"La catégorie « {c['name']} » contient {len(ents)} entrée(s).\n\n"
                          "Oui : supprimer la catégorie et déplacer ses entrées dans « Mes ajouts ».\n"
                          "Non : supprimer la catégorie ET ses entrées.\nAnnuler : ne rien faire.\n\n"
                          "(Ctrl+Z annule dans tous les cas.)", parent=self)
            if r is None:
                return
        else:
            if not messagebox.askyesno(APP_NAME, f"Supprimer la catégorie vide « {c['name']} » ?", parent=self):
                return
            r = True
        self.mutate("Suppression de catégorie")
        if ents:
            if r:
                for e in ents:
                    e["category"] = "mes_ajouts"
                    e["order"] = self.store.next_order("mes_ajouts")
            else:
                self.store.delete([e["id"] for e in ents])
        self.store.data["categories"] = [x for x in self.store.categories if x["id"] != cid]
        self.store.ensure_categories()
        self.store.dirty = True
        self.save_soon()
        self.cur_view = "@all"
        self.refresh_all()
        self.set_status(f"Catégorie « {c['name']} » supprimée. Ctrl+Z pour annuler.")

    # ------------------------------------------------------------ panneau detail
    def update_detail(self) -> None:
        f = self.detail.inner
        for w in f.winfo_children():
            w.destroy()
        bg = C["PANEL"]
        ents = self.sel_entries()
        wrap = max(180, self.f_right.winfo_width() - 40) if self.f_right.winfo_width() > 50 else 280
        if not ents:
            mk_label(f, "⚡", "HI", "ArsEmojiBig", bg=bg).pack(pady=(30, 6))
            mk_label(f, "Arsenal", "HI", "ArsTitle", bg=bg).pack()
            tips = ("Choisis une entrée pour voir sa commande.\n\nDouble-clic ou Entrée : lancer\nCtrl+Entrée : en admin\n"
                    "Clic droit : toutes les actions\nF2 : renommer · Ctrl+E : modifier\nCtrl+clic / Maj+clic : plusieurs\n"
                    "Glisser : réordonner ou déplacer\nCtrl+Z : annuler\n\nTape n'importe où pour chercher.")
            mk_label(f, tips, "DIM", "ArsSM", bg=bg, justify="left", wraplength=wrap).pack(padx=12, pady=10, anchor="w")
            return
        if len(ents) > 1:
            mk_label(f, f"{len(ents)} entrées sélectionnées", "HI", "ArsTitle", bg=bg, wraplength=wrap,
                     justify="left").pack(anchor="w", padx=12, pady=(14, 6))
            names = "\n".join("• " + e["name"] for e in ents[:12]) + ("\n…" if len(ents) > 12 else "")
            mk_label(f, names, "TEXT", "ArsSM", bg=bg, justify="left", wraplength=wrap).pack(anchor="w", padx=12)
            g = tk.Frame(f, bg=bg)
            g.pack(fill="x", padx=10, pady=12)
            acts = [("📁 Déplacer vers…", self.move_dialog, ""), ("⭐ Favoris oui/non", self.toggle_fav, ""),
                    ("👁 Masquer/afficher", self.toggle_hidden, ""), ("💾 Exporter…", lambda: self.export_json(True), ""),
                    ("🗑 Supprimer", self.delete_selected, "danger")]
            for i, (t, cmd, k) in enumerate(acts):
                mk_button(g, t, cmd, k).grid(row=i, column=0, sticky="we", pady=2)
            g.columnconfigure(0, weight=1)
            return
        e = ents[0]
        top = tk.Frame(f, bg=bg)
        top.pack(fill="x", padx=12, pady=(12, 4))
        img = self.icon_image(e.get("icon_file", ""), 32) if e.get("icon_file") else None
        if img is not None:
            tk.Label(top, image=img, bg=bg).pack(side="left", padx=(0, 10))
        else:
            mk_label(top, e.get("icon") or TYPES[e["type"]]["icon"], "HI", "ArsEmojiBig", bg=bg).pack(side="left", padx=(0, 8))
        mk_label(top, e["name"], "HI", "ArsTitle", bg=bg, wraplength=max(120, wrap - 60), justify="left",
                 anchor="w").pack(side="left", fill="x", expand=True)
        where = self.store.cat_name(e["category"], True) + (f" › {e['group']}" if e.get("group") else "")
        mk_label(f, where, "FG", "ArsSM", bg=bg, wraplength=wrap, justify="left").pack(anchor="w", padx=12)
        badges = [TYPES[e["type"]]["label"]]
        if e["type"] in ("cmd", "ps", "script"):
            badges.append("console : " + CONSOLE_LABEL.get(e.get("console", "keep"), ""))
        if e.get("admin"):
            badges.append("🛡 admin")
        if e.get("danger"):
            badges.append("⚠ dangereux")
        if e.get("hidden"):
            badges.append("👁 masquée")
        mk_label(f, " · ".join(badges), "WARN" if e.get("danger") else "DIM", "ArsSM", bg=bg, wraplength=wrap,
                 justify="left").pack(anchor="w", padx=12, pady=(2, 0))
        if e.get("requires") and not which_or_path(e["requires"]):
            mk_label(f, f"Introuvable sur ce PC : {e['requires']}", "ERR", "ArsSM", bg=bg, wraplength=wrap,
                     justify="left").pack(anchor="w", padx=12, pady=(2, 0))
        desc = self._tile_desc(e) if e["type"] == "builtin" else e.get("desc", "")
        if desc:
            mk_label(f, desc, "TEXT", "ArsUI", bg=bg, wraplength=wrap, justify="left").pack(anchor="w", padx=12, pady=(8, 2))
        spec = build_launch(e)
        hd = tk.Frame(f, bg=bg)
        hd.pack(fill="x", padx=12, pady=(8, 0))
        mk_label(hd, "Commande" if e["type"] not in ("url", "copy") else ("Adresse" if e["type"] == "url" else "Texte"),
                 "HI", "ArsUIB", bg=bg).pack(side="left")
        b = tk.Button(hd, text="📋", command=self.copy_command, bg=bg, fg=C["HI"], relief="flat", bd=0,
                      activebackground=C["SEL"], font=fnt("ArsUI"), cursor="hand2")
        b.pack(side="right")
        Tooltip(b, "Copier (Ctrl+C)")
        txt = spec.get("copy") if e["type"] in ("cmd", "ps", "copy", "url") else spec.get("display", "")
        lines = min(10, max(2, txt.count("\n") + 1 + len(txt) // 34))
        t = mk_text(f, lines, 30, "ArsMono", "char")
        t.configure(bg=C["IMG_BG"], fg=C["TEXT"])
        t.insert("1.0", txt)
        t.configure(state="disabled")
        t.pack(fill="x", padx=12, pady=(2, 4))
        if e.get("ask"):
            mk_label(f, "Demandé au lancement : " + ", ".join(a.get("label") or a["var"] for a in e["ask"]), "DIM", "ArsSM",
                     bg=bg, wraplength=wrap, justify="left").pack(anchor="w", padx=12)
        g = tk.Frame(f, bg=bg)
        g.pack(fill="x", padx=10, pady=8)
        run_lab = "📋 Copier" if e["type"] == "copy" else "▶ Lancer"
        acts = [(run_lab, lambda: self.launch(e), "accent")]
        if e["type"] not in ("url", "folder", "copy", "builtin"):
            acts.append(("🛡 En admin", lambda: self.launch(e, admin=True), ""))
        acts += [("✏ Modifier", lambda: self.edit_entry(e["id"]), ""),
                 ("⭐ Retirer favori" if e.get("fav") else "⭐ Favori", self.toggle_fav, ""),
                 ("⧉ Dupliquer", self.duplicate, ""),
                 ("👁 Afficher" if e.get("hidden") else "👁 Masquer", self.toggle_hidden, "")]
        if e["type"] in ("file", "folder", "script"):
            acts.append(("📂 Emplacement", lambda: self.open_location(e), ""))
        acts.append(("🗑 Supprimer", self.delete_selected, "danger"))
        two = wrap >= 250
        for i, (tx, cmd, k) in enumerate(acts):
            bt = mk_button(g, tx, cmd, k)
            if two and i > 0:
                bt.grid(row=1 + (i - 1) // 2, column=(i - 1) % 2, sticky="we", padx=2, pady=2)
            else:
                bt.grid(row=i if not two else 0, column=0, columnspan=2 if two else 1, sticky="we", padx=2, pady=2)
        g.columnconfigure(0, weight=1, uniform="b")
        if two:
            g.columnconfigure(1, weight=1, uniform="b")
        use = f"Utilisée {e.get('uses', 0)} fois" + (f" · dernière : {e['last_used'][:16]}" if e.get("last_used") else "")
        mk_label(f, use, "DIM", "ArsSM", bg=bg, wraplength=wrap, justify="left").pack(anchor="w", padx=12, pady=(2, 12))
        self.detail.canvas.yview_moveto(0)

    # ------------------------------------------------------------ menu contextuel
    def context_menu(self, xr: int, yr: int) -> None:
        ents = self.sel_entries()
        m = new_menu(self)
        if len(ents) == 1:
            e = ents[0]
            if e["type"] == "copy":
                m.add_command(label="📋 Copier le texte", accelerator="Entrée", command=lambda: self.launch(e))
            else:
                m.add_command(label="▶ Lancer", accelerator="Entrée", command=lambda: self.launch(e))
                if e["type"] not in ("url", "folder", "builtin"):
                    m.add_command(label="🛡 Lancer en administrateur", accelerator="Ctrl+Entrée",
                                  command=lambda: self.launch(e, admin=True))
                if e["type"] in ("cmd", "ps", "script"):
                    sub = new_menu(m)
                    for k, lab in CONSOLE_MODES:
                        sub.add_command(label=lab, command=lambda kk=k: self.launch(e, console=kk))
                    m.add_cascade(label="Lancer avec la console…", menu=sub)
                m.add_command(label="📋 Copier la commande", accelerator="Ctrl+C", command=self.copy_command)
            m.add_separator()
            m.add_command(label="✏ Modifier…", accelerator="Ctrl+E", command=lambda: self.edit_entry(e["id"]))
            m.add_command(label="Renommer", accelerator="F2", command=self.start_rename)
            m.add_command(label="⧉ Dupliquer", accelerator="Ctrl+D", command=self.duplicate)
            if e["type"] in ("file", "folder", "script"):
                m.add_command(label="📂 Ouvrir l'emplacement", command=lambda: self.open_location(e))
        if ents:
            if len(ents) > 1:
                m.add_command(label=f"{len(ents)} entrées sélectionnées", state="disabled")
                m.add_separator()
            m.add_command(label="⭐ Favori oui/non", accelerator="Ctrl+B", command=self.toggle_fav)
            m.add_command(label="👁 Masquer / afficher", accelerator="Ctrl+H", command=self.toggle_hidden)
            m.add_command(label="📁 Déplacer vers…", accelerator="Ctrl+M", command=self.move_dialog)
            if self.can_reorder():
                m.add_command(label="Monter", accelerator="Alt+Haut", command=lambda: self.move_step(-1))
                m.add_command(label="Descendre", accelerator="Alt+Bas", command=lambda: self.move_step(1))
            m.add_command(label="💾 Exporter la sélection…", command=lambda: self.export_json(True))
            m.add_separator()
            m.add_command(label="🗑 Supprimer", accelerator="Suppr", command=self.delete_selected)
        else:
            m.add_command(label="＋ Ajouter une entrée…", accelerator="Ctrl+N", command=self.add_entry)
            m.add_command(label="Coller un lien / chemin du presse-papiers", command=self.add_from_clipboard)
            m.add_command(label="Tout sélectionner", accelerator="Ctrl+A", command=self.select_all)
        try:
            m.tk_popup(xr, yr)
        finally:
            m.grab_release()

    # ------------------------------------------------------------ lancement
    def launch_selected(self, admin: Optional[bool] = None):
        ents = self.sel_entries()
        if len(ents) == 1:
            self.launch(ents[0], admin=admin)
        elif len(ents) > 1:
            self.set_status("Plusieurs entrées sélectionnées : choisis-en une seule pour la lancer.", "WARN")
        return "break"

    def launch_first(self):
        if self.visible:
            e = self.store.by_id(self.selected[-1]) if self.selected else self.visible[0]
            self.launch(e or self.visible[0])
        return "break"

    def launch(self, e: Dict[str, Any], admin: Optional[bool] = None, console: Optional[str] = None,
               test: bool = False, parent=None) -> bool:
        parent = parent or self
        name = e.get("name", "")
        try:
            if e.get("requires") and not which_or_path(e["requires"]):
                messagebox.showwarning(APP_NAME, f"« {name} » a besoin de :\n{expand_path(e['requires'])}\n\n"
                                       "Ce programme ou ce fichier est introuvable sur ce PC.", parent=parent)
                return False
            if e["type"] == "builtin":
                self.run_builtin(e["target"])
                self._count(e, test)
                return True
            if e["type"] == "copy":
                copy_to_clipboard(self, e["target"])
                self.set_status(f"📋 Copié : {e['target'][:90]}", "OK")
                self._count(e, test)
                return True
            asks = [dict(a) for a in e.get("ask") or []]
            have = {a["var"] for a in asks}
            for v in placeholders_in(e.get("target", ""), e.get("args", ""), e.get("cwd", "")):
                if v not in have:
                    asks.append({"var": v, "label": v.capitalize(), "kind": ASK_GUESS.get(v, "text"), "default": ""})
            values = None
            if asks:
                values = AskDialog(parent, e, asks, self.last_values.get(e.get("id", ""), {})).wait()
                if values is None:
                    return False
                self.last_values[e.get("id", "")] = values
            spec = build_launch(e, values, admin=admin, console=console)
            if e["type"] in ("file", "folder", "script") and spec.get("file") and os.path.isabs(spec["file"]) \
                    and not os.path.exists(spec["file"]):
                messagebox.showerror(APP_NAME, f"Introuvable :\n{spec['file']}", parent=parent)
                return False
            need = bool(e.get("danger") or e.get("confirm") or (spec.get("admin") and self.store.settings.get("confirm_admin", True)))
            if need:
                r = ConfirmDialog(parent, e, spec, can_skip=bool(spec.get("admin")) and not e.get("confirm")).wait()
                if not r:
                    logger.info("annulé par l'utilisateur : %s", name)
                    self.set_status("Lancement annulé.")
                    return False
                if r.get("skip"):
                    self.store.settings["confirm_admin"] = False
                    self.v_confadmin.set(False)
                    self.save_soon()
            logger.info("lancement%s : %s [%s] admin=%s mode=%s : %s", " (test)" if test else "", name,
                        e.get("seed") or e.get("id"), spec.get("admin"), spec.get("mode"),
                        spec.get("display", "").replace("\n", " ⏎ ")[:400])
            if spec["kind"] == "capture":
                self.run_capture(e, spec)
            else:
                self._shell_async(name, spec)
            self._count(e, test)
            return True
        except Exception as ex:
            logger.error("lancement %s : %s", name, traceback.format_exc())
            messagebox.showerror(APP_NAME, f"Erreur au lancement de « {name} » :\n{ex}", parent=parent)
            return False

    def _shell_async(self, name: str, spec: Dict[str, Any]) -> None:
        self.set_status(f"▶ {name}" + ("  (fenêtre UAC…)" if spec.get("admin") else ""), "OK")

        def work():
            if IS_WIN:
                try:
                    ctypes.windll.ole32.CoInitializeEx(None, 0x2 | 0x4)
                except Exception:
                    pass
            ok, msg, _h = shell_execute(spec["file"], spec.get("params", ""), spec.get("cwd", ""), spec.get("verb", "open"),
                                        spec.get("show", 1))
            if not ok:
                logger.warning("échec %s : %s", name, msg)
                if "UAC" in msg:
                    self.post(lambda: self.set_status(f"{name} : {msg}", "WARN"))
                else:
                    self.post(lambda: messagebox.showerror(APP_NAME, f"« {name} » n'a pas pu être lancé :\n{msg}", parent=self))
        threading.Thread(target=work, daemon=True).start()

    def _count(self, e: Dict[str, Any], test: bool) -> None:
        if test:
            return
        real = self.store.by_id(e.get("id", ""))
        if not real:
            return
        real["uses"] = int(real.get("uses") or 0) + 1
        real["last_used"] = now_iso()
        self.store.dirty = True
        self.save_soon()
        if self.cur_view in ("@recent", "@top"):
            self.refresh_items(keep=True)
        self.after(50, self.refresh_cats)
        if len(self.selected) == 1 and self.selected[0] == real["id"]:
            self.after(60, self.update_detail)

    def run_builtin(self, what: str) -> None:
        if what == "myip":
            self.show_ip()
        elif what == "palette":
            self.open_palette()
        elif what == "help":
            self.show_help()
        elif what == "add":
            self.add_entry()
        else:
            self.set_status(f"Outil intégré inconnu : {what}", "ERR")

    # ------------------------------------------------------------ capture (resultat dans Arsenal)
    def show_result(self):
        if not self.result_shown:
            h = max(160, int(self.f_center.winfo_height() * 0.42))
            self.vpw.add(self.f_result, minsize=90, height=h)
            self.result_shown = True

    def hide_result(self):
        if self.result_shown:
            self.vpw.forget(self.f_result)
            self.result_shown = False

    def clear_result(self):
        self.t_result.delete("1.0", "end")

    def copy_result(self):
        copy_to_clipboard(self, self.t_result.get("1.0", "end").rstrip())
        self.set_status("Résultat copié.", "OK")

    def save_result(self):
        p = filedialog.asksaveasfilename(parent=self, defaultextension=".txt", filetypes=[("Texte", "*.txt")],
                                         initialfile="arsenal_resultat_" + time.strftime("%Y%m%d_%H%M%S") + ".txt")
        if p:
            with open(p, "w", encoding="utf-8") as f:
                f.write(self.t_result.get("1.0", "end"))
            self.set_status(f"Enregistré : {p}", "OK")

    def _result_append(self, text: str, tag: str = "") -> None:
        t = self.t_result
        at_end = t.yview()[1] > 0.98
        t.insert("end", text, tag or ())
        n = int(t.index("end-1c").split(".")[0])
        if n > 20000:
            t.delete("1.0", f"{n - 20000}.0")
        if at_end:
            t.see("end")

    def run_capture(self, e: Dict[str, Any], spec: Dict[str, Any]) -> None:
        if self.capture and self.capture.get("running"):
            if not messagebox.askyesno(APP_NAME, "Une commande tourne déjà dans le panneau Résultat.\nL'arrêter et lancer "
                                                 "celle-ci ?", parent=self):
                return
            self.stop_capture()
        self.show_result()
        self.clear_result()
        name = e.get("name", "")
        self.l_result.configure(text=f"Résultat : {e.get('icon', '')} {name}" + ("  (admin)" if spec.get("admin") else ""))
        self._result_append(f"> {spec.get('display', '')}\n\n", "cmd")
        cap = {"running": True, "proc": None, "h": None, "name": name, "t0": time.time()}
        self.capture = cap
        self.set_status(f"▶ {name} : en cours…", "OK")
        if spec.get("admin"):
            fd, outfile = tempfile.mkstemp(prefix="arsenal_", suffix=".txt")
            os.close(fd)
            file, params = admin_capture_command(spec, outfile)
            threading.Thread(target=self._cap_admin, args=(cap, file, params, spec.get("cwd", ""), outfile),
                             daemon=True).start()
        else:
            threading.Thread(target=self._cap_normal, args=(cap, spec), daemon=True).start()

    def _cap_normal(self, cap, spec):
        code = -1
        try:
            si = None
            if IS_WIN:
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                si.wShowWindow = 0
            p = subprocess.Popen(spec["capture_cmd"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 stdin=subprocess.DEVNULL, cwd=spec.get("cwd") or None,
                                 creationflags=CREATE_NO_WINDOW if IS_WIN else 0, startupinfo=si)
            cap["proc"] = p
            assert p.stdout is not None
            for raw in iter(p.stdout.readline, b""):
                self.cap_q.put(decode_bytes(raw).replace("\r\n", "\n").replace("\r", "\n"))
            code = p.wait()
        except Exception as ex:
            self.cap_q.put(f"\n[erreur] {ex}\n")
        self.post(lambda: self._cap_done(cap, code))

    def _cap_admin(self, cap, file, params, cwd, outfile):
        code = -1
        try:
            if IS_WIN:
                try:
                    ctypes.windll.ole32.CoInitializeEx(None, 0x2 | 0x4)
                except Exception:
                    pass
            ok, msg, h = shell_execute(file, params, cwd, "runas", 0, want_handle=True)
            if not ok:
                self.cap_q.put(f"[{msg}]\n")
                self.post(lambda: self._cap_done(cap, None))
                return
            cap["h"] = h
            import codecs
            dec = codecs.getincrementaldecoder("utf-8")(errors="replace")
            pos = 0
            first = True
            while True:
                r = wait_process(h, 300) if h else 0
                try:
                    with open(outfile, "rb") as f:
                        f.seek(pos)
                        chunk = f.read()
                    pos += len(chunk)
                    if chunk:
                        s = dec.decode(chunk)
                        if first:
                            s = s.lstrip("\ufeff")
                            first = False
                        self.cap_q.put(s.replace("\r\n", "\n").replace("\r", "\n"))
                except OSError:
                    pass
                if r is not None:
                    code = r
                    break
                if not cap.get("running"):
                    break
        except Exception as ex:
            self.cap_q.put(f"\n[erreur] {ex}\n")
        finally:
            try:
                time.sleep(0.2)
                os.remove(outfile)
            except OSError:
                pass
        self.post(lambda: self._cap_done(cap, code))

    def _cap_done(self, cap, code):
        if self.capture is not cap:
            return
        cap["running"] = False
        self._poll_cap_now()
        dur = time.time() - cap["t0"]
        if code is None:
            self._result_append("\n[non lancé]\n", "err")
            self.set_status(f"{cap['name']} : non lancé.", "WARN")
            return
        tag = "ok" if code == 0 else "err"
        self._result_append(f"\n[terminé — code {code} — {dur:.1f} s]\n", tag)
        self.set_status(f"{cap['name']} : terminé (code {code}, {dur:.1f} s).", "OK" if code == 0 else "WARN")
        logger.info("résultat %s : code %s en %.1f s", cap["name"], code, dur)

    def _poll_cap_now(self):
        chunks = []
        try:
            while True:
                chunks.append(self.cap_q.get_nowait())
        except queue.Empty:
            pass
        if chunks:
            self._result_append("".join(chunks))

    def stop_capture(self):
        cap = self.capture
        if not cap or not cap.get("running"):
            self.set_status("Aucune commande en cours.")
            return
        cap["running"] = False
        p = cap.get("proc")
        if p is not None:
            kill_tree(p.pid)
        elif cap.get("h") and IS_WIN:
            try:
                ctypes.windll.kernel32.TerminateProcess(cap["h"], 1)
            except Exception:
                pass
        self._result_append("\n[arrêté]\n", "err")
        self.set_status(f"{cap['name']} : arrêté.", "WARN")

    # ------------------------------------------------------------ modifications + annuler
    def mutate(self, label: str) -> None:
        self.undo.append((label, self.store.snapshot()))
        del self.undo[:-60]
        self.redo.clear()

    def do_undo(self):
        if not self.undo:
            self.set_status("Rien à annuler.")
            return
        label, snap = self.undo.pop()
        self.redo.append((label, self.store.snapshot()))
        self.store.restore(snap)
        self.save_soon()
        self.refresh_all()
        self.set_status(f"↶ Annulé : {label}", "OK")

    def do_redo(self):
        if not self.redo:
            self.set_status("Rien à rétablir.")
            return
        label, snap = self.redo.pop()
        self.undo.append((label, self.store.snapshot()))
        self.store.restore(snap)
        self.save_soon()
        self.refresh_all()
        self.set_status(f"↷ Rétabli : {label}", "OK")

    def save_soon(self):
        if self.save_job:
            try:
                self.after_cancel(self.save_job)
            except Exception:
                pass
        self.save_job = self.after(700, self._save_now)

    def _save_now(self):
        self.save_job = None
        if not self.store.save():
            self.set_status("⚠ Impossible d'enregistrer arsenal.json (voir arsenal.log)", "ERR")

    def add_entry(self, prefill: Optional[Dict[str, Any]] = None):
        cid = self.cur_cat_id() or ("mes_ajouts" if not prefill or not prefill.get("category") else prefill["category"])
        r = EditorDialog(self, self, None, cid, prefill).wait()
        if r:
            self.mutate("Ajout")
            e = self.store.add(r)
            self.save_soon()
            if self.cur_view.startswith("c:") and self.cur_view[2:] != e["category"]:
                self.cur_view = "c:" + e["category"]
            self.refresh_all()
            self.select_ids([e["id"]])
            self.see_tile(e["id"])
            self.set_status(f"＋ « {e['name']} » ajouté dans {self.store.cat_name(e['category'], True)}.", "OK")

    def add_from_clipboard(self):
        try:
            txt = self.clipboard_get().strip()
        except tk.TclError:
            txt = ""
        if not txt:
            self.set_status("Le presse-papiers est vide.")
            return
        t = guess_type(txt)
        self.add_entry({"type": t, "target": txt.strip('"'), "name": guess_name(t, txt),
                        "console": "capture" if t in ("cmd", "ps") else "keep"})

    def edit_entry(self, eid: Optional[str] = None):
        if eid is None:
            ents = self.sel_entries()
            if len(ents) != 1:
                self.set_status("Choisis une entrée à modifier.")
                return
            eid = ents[0]["id"]
        e = self.store.by_id(eid)
        if not e:
            return
        r = EditorDialog(self, self, e).wait()
        if r:
            self.mutate("Modification")
            old_cat = e["category"]
            e.clear()
            e.update(fix_entry(r))
            if e["category"] != old_cat:
                e["order"] = self.store.next_order(e["category"])
            self.store.ensure_categories()
            self.store.dirty = True
            self.save_soon()
            self.refresh_all()
            self.select_ids([e["id"]])
            self.set_status(f"✏ « {e['name']} » modifié.", "OK")

    def duplicate(self):
        ents = self.sel_entries()
        if not ents:
            return
        self.mutate("Duplication")
        new_ids = []
        for e in ents:
            d = copy.deepcopy(e)
            d.update(id=new_id(), seed="", name=e["name"] + " (copie)", uses=0, last_used="", created=now_iso(),
                     order=e["order"] + 0.5)
            self.store.entries.append(d)
            new_ids.append(d["id"])
            cid = e["category"]
            order = [x["id"] for x in sorted([x for x in self.store.entries if x["category"] == cid], key=lambda x: x["order"])]
            self.store.reorder(cid, order)
        self.store.dirty = True
        self.save_soon()
        self.refresh_all()
        self.select_ids(new_ids)
        self.set_status(f"⧉ {len(new_ids)} copie(s) créée(s). F2 pour renommer.", "OK")

    def delete_selected(self):
        ents = self.sel_entries()
        if not ents:
            return
        what = f"« {ents[0]['name']} »" if len(ents) == 1 else f"ces {len(ents)} entrées"
        if not messagebox.askyesno(APP_NAME, f"Supprimer {what} ?\n\n(Ctrl+Z pour annuler, ou « Masquer » pour seulement "
                                             "les cacher.)", parent=self):
            return
        self.mutate("Suppression")
        n = self.store.delete([e["id"] for e in ents])
        self.selected = []
        self.save_soon()
        self.refresh_all()
        self.set_status(f"🗑 {n} entrée(s) supprimée(s) — Ctrl+Z pour annuler.", "WARN")

    def set_flag(self, ids: List[str], key: str, value: Optional[bool], label: str) -> None:
        ents = [self.store.by_id(i) for i in ids]
        ents = [e for e in ents if e]
        if not ents:
            return
        self.mutate(label)
        if value is None:
            value = not all(e.get(key) for e in ents)
        for e in ents:
            e[key] = value
        self.store.dirty = True
        self.save_soon()
        self.refresh_all()
        if key == "hidden" and value and not self.v_showhidden.get() and self.cur_view != "@hidden":
            msg = f"👁 {len(ents)} entrée(s) masquée(s) — visibles dans « Masquées » à gauche. Ctrl+Z pour annuler."
        else:
            msg = f"{label} : {len(ents)} entrée(s)."
        self.set_status(msg, "OK")

    def toggle_fav(self):
        self.set_flag(list(self.selected), "fav", None, "Favoris")

    def toggle_hidden(self):
        self.set_flag(list(self.selected), "hidden", None, "Masquer / afficher")

    def move_to(self, ids: List[str], cid: str) -> None:
        ents = [e for e in (self.store.by_id(i) for i in ids) if e and e["category"] != cid]
        if not ents:
            return
        self.mutate("Déplacement")
        groups = {x.get("group") for x in self.store.entries if x["category"] == cid}
        for e in ents:
            e["order"] = self.store.next_order(cid)
            e["category"] = cid
            if e.get("group") not in groups:
                e["group"] = ""
        self.store.dirty = True
        self.save_soon()
        self.refresh_all()
        self.set_status(f"📁 {len(ents)} entrée(s) déplacée(s) vers {self.store.cat_name(cid, True)}. Ctrl+Z pour annuler.", "OK")

    def move_dialog(self):
        ids = list(self.selected)
        if not ids:
            return
        choices = [(c["id"], self.store.cat_name(c["id"], True)) for c in self.store.categories] + \
                  [("__new__", "＋ Nouvelle catégorie…")]
        first = self.store.by_id(ids[0])
        r = ChoiceDialog(self, "Déplacer vers…", f"Déplacer {len(ids)} entrée(s) vers la catégorie :", choices,
                         first["category"] if first else "").wait()
        if r == "__new__":
            c = CategoryDialog(self, "Nouvelle catégorie").wait()
            if not c:
                return
            r = self.create_category(*c)
        if r:
            self.move_to(ids, r)

    def move_step(self, delta: int):
        if not self.can_reorder() or len(self.selected) != 1:
            self.set_status("Monter/descendre : ouvre une catégorie et choisis une entrée.")
            return
        cid = self.cur_view[2:]
        order = [e["id"] for e in sorted([e for e in self.store.entries if e["category"] == cid], key=lambda e: e["order"])]
        i = order.index(self.selected[0])
        j = i + delta
        if not 0 <= j < len(order):
            return
        self.mutate("Réorganisation")
        order[i], order[j] = order[j], order[i]
        a, b = self.store.by_id(order[i]), self.store.by_id(order[j])
        if a and b and a.get("group") != b.get("group"):
            b["group"] = a.get("group", "")
        self.store.reorder(cid, order)
        self.save_soon()
        self.refresh_items(keep=True)
        self.see_tile(self.selected[0])

    def copy_command(self):
        ents = self.sel_entries()
        if len(ents) != 1:
            return
        spec = build_launch(ents[0])
        txt = spec.get("copy") or spec.get("display", "")
        copy_to_clipboard(self, txt)
        self.set_status(f"📋 Copié : {txt[:90]}", "OK")

    def open_path(self, path: str, select: bool = False):
        if select and os.path.exists(path):
            subprocess.Popen(["explorer.exe", "/select,", os.path.normpath(path)], creationflags=CREATE_NO_WINDOW if IS_WIN else 0)
            return
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True) if path == BACKUP_DIR else None
        shell_execute(path)

    def open_location(self, e):
        p = expand_path(e.get("target", ""))
        if e["type"] == "file" and os.path.basename(p).lower() in ("pythonw.exe", "python.exe") and e.get("args"):
            m = re.match(r'\s*"([^"]+)"', expand(e["args"]))
            if m:
                p = m.group(1)
        if e["type"] == "folder":
            if os.path.isdir(p):
                shell_execute(p)
                return
        if os.path.exists(p):
            self.open_path(p, select=True)
        else:
            w = shutil.which(p)
            if w:
                self.open_path(w, select=True)
            else:
                self.set_status(f"Emplacement introuvable : {p}", "WARN")

    # ------------------------------------------------------------ renommage en place (F2)
    def start_rename(self):
        ents = self.sel_entries()
        if len(ents) != 1:
            return
        e = ents[0]
        self._end_rename(commit=False)
        v = tk.StringVar(value=e["name"])
        if self.view_mode == "tiles":
            box = next((t for t in self.tiles if t[4] == e["id"]), None)
            if not box:
                return
            self.see_tile(e["id"])
            x0, y0, x1, y1, _ = box
            ent = mk_entry(self.canvas, v, 10, "ArsTile")
            win = self.canvas.create_window(x0 + 50, y0 + 5, window=ent, anchor="nw", width=x1 - x0 - 56)
            self.rename_entry = (ent, win, e["id"], v)
        else:
            bb = self.lst.bbox(e["id"], "name")
            if not bb:
                return
            ent = mk_entry(self.lst, v, 10)
            ent.place(x=bb[0], y=bb[1], width=bb[2], height=bb[3])
            self.rename_entry = (ent, None, e["id"], v)
        ent.focus_set()
        ent.select_range(0, "end")
        ent.bind("<Return>", lambda _e: (self._end_rename(True), "break")[1])
        ent.bind("<Escape>", lambda _e: (self._end_rename(False), "break")[1])
        ent.bind("<FocusOut>", lambda _e: self._end_rename(True))

    def _end_rename(self, commit: bool):
        r = self.rename_entry
        if not r:
            return
        self.rename_entry = None
        ent, win, eid, v = r
        name = v.get().strip()
        try:
            if win is not None:
                self.canvas.delete(win)
            ent.destroy()
        except Exception:
            pass
        e = self.store.by_id(eid)
        if commit and e and name and name != e["name"]:
            self.mutate("Renommage")
            e["name"] = name
            self.store.dirty = True
            self.save_soon()
            self.fit_cache.clear()
            self.refresh_items(keep=True)
            self.set_status(f"Renommé : {name}", "OK")
        (self.canvas if self.view_mode == "tiles" else self.lst).focus_set()

    # ------------------------------------------------------------ recherche
    def _search_changed(self):
        q = self.v_search.get()
        if q:
            self.l_ph.place_forget()
        else:
            self.l_ph.place(in_=self.e_search, x=2, rely=0.5, anchor="w")
        if self.search_job:
            self.after_cancel(self.search_job)
        self.search_job = self.after(110, self._do_search)

    def _do_search(self):
        self.search_job = None
        self.selected = []
        self.refresh_items()
        if self.visible and self.v_search.get().strip():
            self.selected = [self.visible[0]["id"]]
            if self.view_mode == "tiles":
                self._redraw_selection()
            else:
                self.fill_list()
            self.update_detail()

    def focus_search(self):
        self.e_search.focus_set()
        self.e_search.select_range(0, "end")
        return "break"

    def clear_search(self):
        if self.v_search.get():
            self.v_search.set("")
        self._focus_items()
        return "break"

    # ------------------------------------------------------------ affichage / reglages
    def set_view_mode(self):
        self.view_mode = self.v_view.get()
        self.store.settings["view"] = self.view_mode
        self._update_view_button()
        self._show_view_widget()
        self.refresh_items()
        self._focus_items() if self.visible else None
        self.save_soon()

    def toggle_view_mode(self):
        self.v_view.set("list" if self.view_mode == "tiles" else "tiles")
        self.set_view_mode()
        return "break"

    def toggle_show_hidden(self):
        self.store.settings["show_hidden"] = self.v_showhidden.get()
        self.save_soon()
        self.refresh_all()

    def zoom(self, d: int):
        cur = int(self.store.settings.get("font_delta", 0))
        new = 0 if d == 0 else max(FONT_DELTA_MIN, min(FONT_DELTA_MAX, cur + d))
        self.store.settings["font_delta"] = new
        init_fonts(self, new)
        self.rebuild()
        self.set_status(f"Taille du texte : {'+' if new > 0 else ''}{new}")
        return "break"

    def change_theme(self):
        k = self.v_theme.get()
        self.store.settings["theme"] = k
        C.clear()
        C.update(THEMES.get(k, THEMES["norton"]))
        self.rebuild()
        self.set_status(f"Thème : {THEME_LABELS.get(k, k)}")

    def rebuild(self):
        self._save_panes()
        sel = list(self.selected)
        res = self.t_result.get("1.0", "end") if self.result_shown else ""
        for w in self.winfo_children():
            if not isinstance(w, tk.Toplevel):
                w.destroy()
        self.icon_cache.clear()
        self._build()
        self.selected = sel
        self.refresh_all()
        if res.strip():
            self.show_result()
            self._result_append(res)
        self.save_soon()

    def _save_panes(self):
        try:
            # rien a enregistrer si la fenetre n'a jamais ete affichee (largeurs factices)
            if not self.winfo_viewable() or self.pw.winfo_width() < 600:
                return
            lw = int(self.pw.sash_coord(0)[0])
            rw = int(self.pw.winfo_width() - self.pw.sash_coord(1)[0])
            if 150 <= lw <= 800 and 200 <= rw <= 900:
                self.store.settings.update(left_w=lw, right_w=rw, panes_v=PANES_V)
        except Exception:
            pass

    def toggle_console_colors(self):
        CONSOLE_COLORS[0] = self.v_ccolors.get()
        self.store.settings["console_colors"] = CONSOLE_COLORS[0]
        self.save_soon()
        self.update_detail()

    def _save_confadmin(self):
        self.store.settings["confirm_admin"] = self.v_confadmin.get()
        self.save_soon()

    # ------------------------------------------------------------ raccourci global (RegisterHotKey)
    def start_hotkey(self):
        if not IS_WIN or self.hk_thread_id:
            return

        def loop():
            u32 = ctypes.windll.user32
            k32 = ctypes.windll.kernel32
            self.hk_thread_id = k32.GetCurrentThreadId()
            ok = u32.RegisterHotKey(None, 0xA75E, 0x0002 | 0x0001 | 0x4000, 0x20)  # Ctrl+Alt+Espace
            if not ok:
                logger.warning("raccourci global Ctrl+Alt+Espace déjà utilisé par un autre programme")
                self.post(lambda: self.set_status("Raccourci global Ctrl+Alt+Espace indisponible (déjà pris).", "WARN"))
                self.hk_thread_id = 0
                return
            msg = wintypes.MSG()
            while u32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == 0x0312:
                    self.hk_q.put(1)
            u32.UnregisterHotKey(None, 0xA75E)
        threading.Thread(target=loop, daemon=True).start()

    def stop_hotkey(self):
        if IS_WIN and self.hk_thread_id:
            ctypes.windll.user32.PostThreadMessageW(self.hk_thread_id, 0x0012, 0, 0)
            self.hk_thread_id = 0

    def toggle_hotkey(self):
        on = self.v_hotkey.get()
        self.store.settings["global_hotkey"] = on
        self.save_soon()
        if on:
            self.start_hotkey()
            self.set_status("Raccourci global activé : Ctrl+Alt+Espace ouvre la palette d'Arsenal.", "OK")
        else:
            self.stop_hotkey()
            self.set_status("Raccourci global désactivé.")

    def from_hotkey(self):
        self.bring_front()
        self.open_palette()

    def bring_front(self):
        try:
            if self.state() == "iconic" or not self.winfo_viewable():
                self.deiconify()
            self.lift()
            self.attributes("-topmost", True)
            self.after(200, lambda: self.attributes("-topmost", False))
            self.focus_force()
        except tk.TclError:
            pass

    # ------------------------------------------------------------ palette Ctrl+Espace
    def open_palette(self):
        if self.palette is not None and self.palette.winfo_exists():
            self.palette.lift()
            self.palette.entry.focus_force()
            return "break"
        self.palette = Palette(self)
        return "break"

    # ------------------------------------------------------------ dialogues divers
    def show_ip(self):
        IPDialog(self, self)

    def show_help(self):
        TextDialog(self, "Aide — Arsenal", HELP_TEXT, 920, 680)
        return "break"

    def about(self):
        n = len(self.store.entries)
        messagebox.showinfo(APP_NAME, f"Arsenal {APP_FILE_VER} — tiroir à outils du Projet Padawan\n\n"
                                      f"{n} entrées · {len(self.store.categories)} catégories\n"
                                      f"Données : {self.store.path}\nJournal : {LOG_FILE}\n"
                                      f"Sauvegardes : {BACKUP_DIR}\n\nPython {sys.version.split()[0]} · Tk {tk.TkVersion}",
                            parent=self)

    def show_log(self):
        try:
            with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()[-400:]
        except OSError:
            lines = ["(journal vide)"]
        TextDialog(self, "Journal — arsenal.log (400 dernières lignes)", "".join(lines), 1000, 640)

    def check_entries(self):
        missing = []
        for e in self.store.entries:
            if e.get("requires") and not which_or_path(e["requires"]):
                missing.append(f"  {e['name']} : requiert {e['requires']}")
            elif e["type"] in ("file", "folder", "script"):
                p = expand_path(e["target"])
                if os.path.isabs(p) and not os.path.exists(p):
                    missing.append(f"  {e['name']} : introuvable {p}")
        txt = "# Vérification des entrées\n\n" + (f"{len(missing)} entrée(s) dont le programme ou le chemin est absent de ce PC "
                                                  "(elles restent disponibles, Arsenal le signale au lancement) :\n\n"
                                                  + "\n".join(missing) if missing else "Tout est présent sur ce PC. ✔")
        TextDialog(self, "Vérification", txt, 900, 560)

    # ------------------------------------------------------------ import / export
    def _do_import(self, items, cats, label, src):
        if not items:
            messagebox.showinfo(APP_NAME, f"Aucune entrée trouvée dans :\n{src}", parent=self)
            return
        if not messagebox.askyesno(APP_NAME, f"{len(items)} entrée(s) trouvée(s) ({label}).\n\nLes doublons (même adresse "
                                             "ou même commande) seront ignorés. Importer ?", parent=self):
            return
        self.mutate("Import")
        added, dup = self.store.import_entries(items, cats)
        self.save_soon()
        self.refresh_all()
        logger.info("import %s : %d ajoutées, %d doublons (%s)", label, added, dup, src)
        messagebox.showinfo(APP_NAME, f"Import terminé : {added} ajoutée(s), {dup} doublon(s) ignoré(s).\n(Ctrl+Z pour annuler.)",
                            parent=self)

    def import_pack(self):
        """Paquet Arsenal (.json) : apercu ; rien n'est lance a l'import, commandes en confirmation obligatoire."""
        pk = os.path.join(os.path.dirname(os.path.abspath(__file__)), "paquets")
        path = filedialog.askopenfilename(parent=self, title="Importer un paquet Arsenal",
                                          initialdir=pk if os.path.isdir(pk) else None,
                                          filetypes=[("Paquet Arsenal", "*.json"), ("Tous", "*.*")])
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                meta = (json.load(f) or {}).get("paquet") or {}
        except Exception:
            meta = {}
        if meta and not messagebox.askyesno(APP_NAME, f"Paquet : {meta.get('nom', '?')} (par {meta.get('auteur', '?')})\n\n"
                                            f"{meta.get('description', '')}\n\nRien n'est lanc\u00e9 \u00e0 l'import ; les commandes "
                                            "demanderont confirmation. Continuer ?", parent=self):
            return
        self.import_file(path)

    def import_file(self, path: str = "", cat_hint: str = ""):
        if not path:
            path = filedialog.askopenfilename(parent=self, title="Importer dans Arsenal",
                                              filetypes=[("Arsenal, Favoris, signets", "*.json;*.html;*.htm;Bookmarks"),
                                                         ("Tous", "*.*")])
        if not path:
            return
        try:
            items, cats, label = read_import_file(path, cat_hint)
        except Exception as ex:
            messagebox.showerror(APP_NAME, f"Fichier illisible :\n{ex}", parent=self)
            return
        self._do_import(items, cats, label, path)

    def import_favoris_backup(self):
        p = latest_favoris_backup()
        if not p:
            messagebox.showinfo(APP_NAME, f"Aucune sauvegarde de Favoris trouvée dans\n{FAVORIS_BACKUP_DIR}", parent=self)
            return
        self.import_file(p, "favoris_web")

    def import_favoris_url(self):
        self.set_status(f"Lecture de {FAVORIS_URL}…")

        def work():
            try:
                txt = fetch_url_text(FAVORIS_URL)
                items = parse_favoris_html(txt, "favoris_web")
                self.post(lambda: self._do_import(items, [{"id": "favoris_web", "name": "Mes favoris web", "icon": "⭐"}],
                                                  "Favoris.php en ligne", FAVORIS_URL))
            except Exception as ex:
                err = str(ex)
                self.post(lambda: messagebox.showerror(APP_NAME, f"Lecture impossible :\n{err}", parent=self))
        threading.Thread(target=work, daemon=True).start()

    def import_browser(self):
        files = browser_bookmark_files()
        if not files:
            messagebox.showinfo(APP_NAME, "Aucun fichier de signets Chrome, Edge ou Brave trouvé.", parent=self)
            return
        r = ChoiceDialog(self, "Signets du navigateur", "Quel navigateur / profil importer ?",
                         [(p, f"{n}   —   {p}") for n, p in files]).wait()
        if r:
            self.import_file(r, "signets_navigateur")

    def export_json(self, selection: bool):
        ents = self.sel_entries() if selection else None
        if selection and not ents:
            self.set_status("Sélectionne d'abord des entrées.")
            return
        p = filedialog.asksaveasfilename(parent=self, defaultextension=".json", filetypes=[("JSON", "*.json")],
                                         initialfile=("arsenal_selection_" if selection else "arsenal_export_")
                                         + time.strftime("%Y%m%d") + ".json")
        if p:
            n = export_json(self.store, p, ents)
            self.set_status(f"💾 {n} entrée(s) exportée(s) : {p}", "OK")

    def export_category(self, cid: str):
        ents = [e for e in self.store.entries if e["category"] == cid]
        p = filedialog.asksaveasfilename(parent=self, defaultextension=".json", filetypes=[("JSON", "*.json")],
                                         initialfile=f"arsenal_{cid}.json")
        if p:
            n = export_json(self.store, p, ents)
            self.set_status(f"💾 {n} entrée(s) exportée(s) : {p}", "OK")

    def export_html(self):
        p = filedialog.asksaveasfilename(parent=self, defaultextension=".html", filetypes=[("Page web", "*.html")],
                                         initialfile="arsenal_catalogue.html")
        if p:
            n = export_html(self.store, p)
            self.set_status(f"💾 Catalogue HTML : {n} entrées — {p}", "OK")
            shell_execute(p)

    def backup_now(self):
        self._save_now()
        d = self.store.backup(force=True)
        self.set_status(f"Sauvegarde : {d}" if d else "Sauvegarde impossible.", "OK" if d else "ERR")

    def restore_seeds(self):
        n_del = len(self.store.data.get("seed_deleted") or [])
        if not n_del:
            messagebox.showinfo(APP_NAME, "Aucune entrée d'origine n'a été supprimée.", parent=self)
            return
        if messagebox.askyesno(APP_NAME, f"Remettre les {n_del} entrée(s) d'origine supprimée(s) ?", parent=self):
            self.mutate("Restauration")
            n = self.store.restore_missing_seeds()
            self.save_soon()
            self.refresh_all()
            self.set_status(f"{n} entrée(s) d'origine restaurée(s).", "OK")

    # ------------------------------------------------------------ glisser-deposer depuis Windows
    def _on_drop(self, event):
        data = event.data or ""
        try:
            parts = list(self.tk.splitlist(data))
        except tk.TclError:
            parts = [data]
        parts = [p.strip() for p in parts if p and p.strip()]
        if not parts:
            return
        w = event.widget
        cid = self.cur_cat_id() or "mes_ajouts"
        if w is self.cat_tree:
            try:
                iid = self.cat_tree.identify_row(event.y_root - self.cat_tree.winfo_rooty())
                if iid and iid.startswith("c:"):
                    cid = iid[2:]
            except Exception:
                pass
        items = []
        for p in parts:
            p0 = p
            if p.lower().endswith(".url") and os.path.isfile(p):
                try:
                    with open(p, "r", encoding="utf-8", errors="ignore") as f:
                        m = re.search(r"^URL=(.+)$", f.read(), re.M)
                    if m:
                        items.append({"type": "url", "target": m.group(1).strip(),
                                      "name": os.path.splitext(os.path.basename(p))[0]})
                        continue
                except OSError:
                    pass
            t = guess_type(p0)
            if t in ("cmd", "ps") and "\n" not in p0 and len(parts) == 1 and re.match(r"^[a-z]+://", p0, re.I) is None:
                t = "copy" if len(p0) > 0 and " " in p0 else t
            items.append({"type": t, "target": p0, "name": guess_name(t, p0)})
        if len(items) == 1:
            pre = items[0]
            pre["category"] = cid
            if pre["type"] in ("file", "script"):
                ic = extract_icon_png(pre["target"])
                if ic:
                    pre["icon_file"] = ic
            self.add_entry(pre)
            return
        self.mutate("Ajout par glisser-déposer")
        n = 0
        for it in items:
            e = default_entry()
            e.update(it)
            e["category"] = cid
            e["icon"] = TYPES[e["type"]]["icon"]
            if e["type"] in ("file", "script"):
                e["icon_file"] = extract_icon_png(e["target"])
            self.store.add(e)
            n += 1
        self.save_soon()
        self.refresh_all()
        self.set_status(f"＋ {n} entrées ajoutées dans {self.store.cat_name(cid, True)} (Ctrl+Z pour annuler).", "OK")

    # ------------------------------------------------------------ fermeture
    def on_close(self):
        try:
            self._save_panes()
            self.store.settings["last_view"] = self.cur_view
            self.stop_hotkey()
            if self.capture and self.capture.get("running"):
                self.stop_capture()
            if self.save_job:
                self.after_cancel(self.save_job)
            self.store.save()
            logger.info("Arsenal fermé")
        except Exception:
            logger.error("fermeture : %s", traceback.format_exc())
        self.destroy()


# ================================================================ palette
class Palette(tk.Toplevel):
    """Lancement rapide : tape, flèches, Entrée (Ctrl+Entrée = admin), Échap."""

    def __init__(self, app: ArsenalApp):
        super().__init__(app)
        self.app = app
        self.overrideredirect(True)
        self.configure(bg=C["HI"])
        try:
            self.attributes("-topmost", True)
        except tk.TclError:
            pass
        top = app.winfo_toplevel()
        W = min(760, max(420, top.winfo_width() - 60))
        H = min(470, max(260, top.winfo_height() - 80))
        x = top.winfo_rootx() + (top.winfo_width() - W) // 2
        y = top.winfo_rooty() + max(20, top.winfo_height() // 7)
        self.geometry(f"{W}x{H}+{x}+{y}")
        inner = tk.Frame(self, bg=C["PANEL"])
        inner.pack(fill="both", expand=True, padx=2, pady=2)
        hd = tk.Frame(inner, bg=C["PANEL"])
        hd.pack(fill="x", padx=10, pady=(8, 4))
        tk.Label(hd, text="⚡", bg=C["PANEL"], fg=C["HI"], font=fnt("ArsTitle")).pack(side="left")
        self.v = tk.StringVar()
        self.entry = tk.Entry(hd, textvariable=self.v, bg=C["ENTRY_BG"], fg=C["ENTRY_FG"], insertbackground=C["HI"],
                              relief="flat", font=fnt("ArsBig"), highlightthickness=1, highlightbackground=C["LINE"],
                              highlightcolor=C["HI"])
        self.entry.pack(side="left", fill="x", expand=True, padx=8, ipady=3)
        self.lb = tk.Listbox(inner, bg=C["CARD"], fg=C["TEXT"], selectbackground=C["SEL"], selectforeground=C["ON_SEL"],
                             font=fnt("ArsUI"), activestyle="none", relief="flat", highlightthickness=0, bd=0)
        self.lb.pack(fill="both", expand=True, padx=10, pady=4)
        tk.Label(inner, text="Entrée : lancer · Ctrl+Entrée : admin · ↑↓ : choisir · Échap : fermer", bg=C["PANEL"],
                 fg=C["DIM"], font=fnt("ArsSM")).pack(anchor="w", padx=10, pady=(0, 6))
        self.items: List[Dict[str, Any]] = []
        self.v.trace_add("write", lambda *_a: self.fill())
        for w in (self.entry, self.lb):
            w.bind("<Return>", lambda _e: self.go(False))
            w.bind("<Control-Return>", lambda _e: self.go(True))
            w.bind("<Escape>", lambda _e: self.close())
        self.entry.bind("<Down>", lambda _e: self.move(1))
        self.entry.bind("<Up>", lambda _e: self.move(-1))
        self.entry.bind("<Next>", lambda _e: self.move(8))
        self.entry.bind("<Prior>", lambda _e: self.move(-8))
        self.lb.bind("<Double-Button-1>", lambda _e: self.go(False))
        self.bind("<FocusOut>", self._focus_out)
        self.fill()
        self.after(30, self.entry.focus_force)

    def _focus_out(self, _e):
        self.after(150, lambda: self.close() if self.winfo_exists() and self.focus_get() is None else None)

    def fill(self):
        q = self.v.get().strip()
        st = self.app.store
        if q:
            toks = [norm(t) for t in q.split()]
            sc = [(search_score(e, toks, st.cat_name(e["category"])), e) for e in st.entries if not e.get("hidden")]
            res = [e for s, e in sorted([x for x in sc if x[0]], key=lambda x: (-x[0], x[1]["name"]))][:40]
        else:
            used = sorted([e for e in st.entries if e.get("last_used") and not e.get("hidden")],
                          key=lambda e: e["last_used"], reverse=True)[:15]
            favs = [e for e in st.entries if e.get("fav") and not e.get("hidden") and e not in used]
            res = (used + favs)[:40] or [e for e in st.entries if e["category"] == "mes_outils"][:20]
        self.items = res
        self.lb.delete(0, "end")
        width_chars = max(30, int(self.lb.winfo_width() / max(7, fnt("ArsUI").measure("M"))) - 2) \
            if self.lb.winfo_width() > 50 else 80
        for e in res:
            cat = st.cat_name(e["category"])
            left = f" {e.get('icon', '')}  {e['name']}"
            pad = max(2, width_chars - len(left) - len(cat))
            self.lb.insert("end", left + " " * pad + cat)
        if res:
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

    def go(self, admin):
        cur = self.lb.curselection()
        if not cur or not self.items:
            return "break"
        e = self.items[cur[0]]
        self.close()
        self.app.after(30, lambda: self.app.launch(e, admin=True if admin else None))
        return "break"

    def close(self):
        try:
            self.destroy()
        except tk.TclError:
            pass
        self.app.palette = None


HELP_TEXT = """# ⚡ Arsenal — ton tiroir à outils
Un seul endroit pour tes favoris web, programmes, dossiers, commandes CMD/PowerShell, réglages Windows et aide-mémoire. Tout est gratuit et intégré à Windows. Les données sont dans arsenal.json (sauvegardes automatiques).

## Lancer
  Double-clic ou Entrée : lancer l'entrée choisie
  Ctrl+Entrée : lancer en administrateur (fenêtre UAC)
  Clic droit : Lancer, Lancer en admin, Copier la commande, Modifier, Dupliquer, Emplacement, Supprimer…
  Taper n'importe où : recherche instantanée (nom, description, commande, mots-clés, catégorie)
  Ctrl+F : aller dans la recherche · Échap : effacer
  Ctrl+Espace : palette de lancement rapide · Ctrl+Alt+Espace : palette même quand Arsenal est en arrière-plan

## Résultat dans Arsenal
Les commandes marquées « Résultat dans Arsenal » s'exécutent sans console : la sortie s'affiche dans le panneau Résultat (en bas), avec Arrêter, Copier, Enregistrer. Les autres ouvrent une console bleue qui reste ouverte.

## Ajouter et gérer
  ＋ Ajouter (Ctrl+N) : assistant — choisis le type, remplis les champs, « Parcourir… », « ▶ Tester », Enregistrer
  Glisser-déposer : un fichier, un dossier, un raccourci ou un lien depuis Windows ou le navigateur crée une entrée
  F2 : renommer sur place · Ctrl+E : tout modifier · Ctrl+D : dupliquer
  Glisser une tuile : réordonner dans sa catégorie, ou la déposer sur une catégorie à gauche pour la déplacer
  Alt+Haut / Alt+Bas : monter / descendre
  Ctrl+clic, Maj+clic, Ctrl+A : plusieurs entrées (déplacer, favoris, masquer, exporter, supprimer)
  Ctrl+B : favori (⭐) · Ctrl+H : masquer sans supprimer (vue « Masquées » à gauche)
  Ctrl+Z / Ctrl+Y : annuler / rétablir (suppression, modification, déplacement, import…)
  Catégories : bouton ＋ ou clic droit à gauche — créer, renommer, changer l'emoji, monter, descendre, supprimer. On peut aussi les glisser pour changer leur ordre.

## Variables dans les commandes
  {DOSSIER} {FICHIER} {HOTE} {NOM}… : demandées au lancement (avec « Parcourir… » pour les dossiers et fichiers)
  {PROJET} : le dossier du Projet Padawan · {ARSENAL} : le dossier d'Arsenal · {WEB} : C:\\web
  {PYTHON} / {PYTHONW} : Python 3.14 · {POWERSHELL} : Windows PowerShell
  {MPCMDRUN} : Microsoft Defender, chemin le plus récent trouvé automatiquement
  %APPDATA%, %USERPROFILE%… : variables Windows acceptées dans les chemins

## Sécurité
  ⚠ Entrées dangereuses : confirmation obligatoire, avec la commande exacte affichée
  🛡 Lancement administrateur : la commande exacte est montrée avant la fenêtre UAC (réglable dans Outils)
  Journal : chaque lancement est noté dans arsenal.log (Outils → Voir le journal)
  Programme absent : les entrées qui en dépendent (git, gpedit sur Windows Famille…) le disent au lieu d'échouer

## Importer / exporter
  Fichier → Importer : sauvegarde Arsenal (.json), sauvegarde de Favoris.php, page Favoris.php enregistrée (.html), signets Chrome / Edge / Brave, fichier de signets HTML. Les doublons sont ignorés.
  Fichier → Exporter : tout ou la sélection en JSON, ou un catalogue HTML imprimable.
  Fichier → Restaurer les entrées d'origine supprimées : remet le contenu fourni avec Arsenal.

## Affichage
  Ctrl+L ou bouton : tuiles / liste · Ctrl+ + / Ctrl+ - / Ctrl+0 : taille du texte
  Affichage → Thème : Norton (bleu), Sombre, Clair · F5 : rafraîchir · F1 : cette aide

## Fichiers
  arsenal1.py : le programme · arsenal.json : tes données · arsenal.log : le journal
  _sauvegardes_arsenal\\ : copies datées (25 dernières) · _icones_arsenal\\ : icônes extraites des programmes
"""


# ================================================================ lancement
def _focus_existing() -> bool:
    if not IS_WIN:
        return False
    try:
        u32 = ctypes.windll.user32
        hwnd = u32.FindWindowW("TkTopLevel", APP_TITLE)
        if hwnd:
            cmd = 9 if u32.IsIconic(hwnd) else (3 if u32.IsZoomed(hwnd) else 5)
            # deux appels : le premier ShowWindow d'un processus peut etre remplace
            # par le wShowWindow de son STARTUPINFO
            u32.ShowWindow(hwnd, cmd)
            u32.ShowWindow(hwnd, cmd)
            # Windows bloque SetForegroundWindow depuis un processus en arriere-plan :
            # un evenement souris nul (deplacement 0,0) leve ce verrou sans effet visible
            # (une frappe Alt activerait la barre de menus d'Arsenal).
            u32.mouse_event(0x0001, 0, 0, 0, 0)
            u32.BringWindowToTop(hwnd)
            u32.SetForegroundWindow(hwnd)
            return True
    except Exception:
        pass
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


def take_shot(app: ArsenalApp, path: str) -> bool:
    try:
        from PIL import ImageGrab  # type: ignore
    except ImportError:
        logger.error("capture : Pillow absent")
        return False
    # la capture prend l'ecran : on passe Arsenal (puis ses dialogues) au premier plan
    wins = [app] + [w for w in app.winfo_children() if isinstance(w, tk.Toplevel) and w.winfo_viewable()]
    for w in wins:
        try:
            w.attributes("-topmost", True)
            w.lift()
        except tk.TclError:
            pass
    app.update()
    time.sleep(0.3)
    app.update()
    full = ImageGrab.grab()
    for w in wins:
        try:
            w.attributes("-topmost", False)
        except tk.TclError:
            pass
    f = full.width / max(1, app.winfo_screenwidth())
    x, y = app.winfo_rootx(), app.winfo_rooty()
    w, h = app.winfo_width(), app.winfo_height()
    box = (int(x * f), int(y * f), int((x + w) * f), int((y + h) * f))
    img = full.crop(box)
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    img.save(path)
    logger.info("capture %s (%dx%d, facteur %.2f)", path, img.width, img.height, f)
    return True


def run_shot(app: ArsenalApp, path: str, view: str) -> None:
    st = app.store

    def first_of(cid):
        ents = sorted([e for e in st.entries if e["category"] == cid and not e.get("hidden")], key=lambda e: e["order"])
        return ents[0]["id"] if ents else None

    def step1():
        if view == "main":
            app.select_view("c:mes_outils")
            fid = first_of("mes_outils")
            if fid:
                app.select_ids([fid])
        elif view == "securite":
            app.select_view("c:securite")
            e = st.by_id(next((x["id"] for x in st.entries if x.get("seed") == "securite.mp_quick"), "")) or None
            app.select_ids([e["id"] if e else first_of("securite")])
        elif view == "liste":
            app.select_view("c:reseau")
            app.v_view.set("list")
            app.set_view_mode()
            fid = first_of("reseau")
            if fid:
                app.select_ids([fid])
        elif view == "web":
            app.select_view("c:web")
        elif view == "recherche":
            app.v_search.set("ip")
        elif view == "editeur":
            e = next((x for x in st.entries if x.get("seed") == "reseau.ping"), None) or st.entries[0]
            app.select_view("c:" + e["category"])
            EditorDialog(app, app, e)
        elif view == "editeur1":
            EditorDialog(app, app, None, "mes_ajouts")
        elif view == "aide":
            app.show_help()
        elif view == "palette":
            app.open_palette()
            app.palette.v.set("def")
        elif view == "ip":
            app.show_ip()
        elif view == "resultat":
            app.select_view("c:reseau")
            e = next((x for x in st.entries if x.get("seed") == "reseau.ipconfig"), None)
            if e:
                app.select_ids([e["id"]])
                app.run_capture(e, build_launch(e))
        elif view == "confirm":
            e = next((x for x in st.entries if x.get("danger")), None)
            if e:
                app.select_view("c:" + e["category"])
                ConfirmDialog(app, e, build_launch(e), True)
        delay = {"ip": 5000, "resultat": 6000}.get(view, 1500)
        app.after(delay, step2)

    def step2():
        take_shot(app, path)
        app.after(100, app.destroy)
    app.after(1500, step1)


def run_smoke(app: ArsenalApp) -> int:
    errors: List[str] = []
    st = app.store
    try:
        for e in st.entries:
            try:
                build_launch(e, {a["var"]: "X" for a in e.get("ask") or []})
            except Exception as ex:
                errors.append(f"build_launch {e.get('seed') or e['id']}: {ex}")
        app.update()
        for v in [k for k, _, _ in SPECIAL_VIEWS] + ["c:" + c["id"] for c in st.categories]:
            app.select_view(v)
            app.update()
            if app.visible:
                app.select_ids([app.visible[0]["id"]])
                app.update()
        app.v_view.set("list")
        app.set_view_mode()
        app.select_view("c:securite")
        app.update()
        app.v_view.set("tiles")
        app.set_view_mode()
        app.v_search.set("ipconfig")
        app._do_search()
        app.update()
        if not app.visible:
            errors.append("recherche ipconfig : aucun résultat")
        app.v_search.set("")
        for maker in (lambda: EditorDialog(app, app, None, "mes_ajouts"),
                      lambda: EditorDialog(app, app, st.entries[5]),
                      lambda: TextDialog(app, "Aide", HELP_TEXT),
                      lambda: CategoryDialog(app, "Test"),
                      lambda: EmojiPicker(app, "⚡"),
                      lambda: ConfirmDialog(app, st.entries[0], build_launch(st.entries[0]), True)):
            d = maker()
            app.update()
            d.destroy()
        ed = EditorDialog(app, app, None, "mes_ajouts")
        ed._choose("cmd")
        app.update()
        ed.t_target.insert("1.0", "ping {HOTE}")
        ed._refresh_asks()
        app.update()
        if not ed.asks or ed.asks[0]["var"] != "HOTE":
            errors.append("éditeur : variable {HOTE} non détectée")
        ed.destroy()
        app.open_palette()
        app.update()
        app.palette.v.set("dolphin")
        app.update()
        if not app.palette.items:
            errors.append("palette : aucun résultat pour dolphin")
        app.palette.close()
        snap_n = len(st.entries)
        app.mutate("test")
        st.delete([st.entries[0]["id"]])
        app.do_undo()
        if len(st.entries) != snap_n:
            errors.append("annuler : nombre d'entrées incorrect")
        app.zoom(1)
        app.update()
        app.zoom(0)
        app.update()
    except Exception:
        errors.append(traceback.format_exc())
    counts: Dict[str, int] = {}
    for e in st.entries:
        counts[e["category"]] = counts.get(e["category"], 0) + 1
    print(f"SMOKE {'OK' if not errors else 'ERREURS'} : {len(st.entries)} entrées, {len(st.categories)} catégories")
    for c in st.categories:
        print(f"  {c['name']}: {counts.get(c['id'], 0)}")
    for er in errors:
        print("ERREUR:", er)
    logger.info("smoke : %s (%d entrées)", "OK" if not errors else f"{len(errors)} erreur(s)", len(st.entries))
    return 0 if not errors else 1


def cli_list(store: Store) -> int:
    counts: Dict[str, int] = {}
    for e in store.entries:
        counts[e["category"]] = counts.get(e["category"], 0) + 1
    for c in store.categories:
        print(f"{c['id']}\t{c['name']}\t{counts.get(c['id'], 0)}")
    print(f"TOTAL\t{len(store.entries)}")
    return 0


def cli_check(store: Store) -> int:
    n = 0
    for e in store.entries:
        bad = ""
        if e.get("requires") and not which_or_path(e["requires"]):
            bad = f"requiert {e['requires']}"
        elif e["type"] in ("file", "folder", "script"):
            p = expand_path(e["target"])
            if os.path.isabs(p) and not os.path.exists(p):
                bad = f"introuvable {p}"
        if bad:
            n += 1
            print(f"{e.get('seed') or e['id']}\t{e['name']}\t{bad}")
    print(f"MANQUANTS\t{n}")
    return 0


def cli_run_capture(store: Store, seed: str, sets: List[str]) -> int:
    e = next((x for x in store.entries if x.get("seed") == seed or x["id"] == seed), None)
    if not e:
        print("entrée introuvable :", seed)
        return 2
    if e.get("danger") or e.get("admin"):
        print("refusé en ligne de commande : entrée admin ou dangereuse :", e["name"])
        return 3
    vals = dict(s.split("=", 1) for s in sets if "=" in s)
    spec = build_launch(e, vals, console="capture")
    if spec["kind"] != "capture":
        print("pas une commande capturable :", spec.get("display"))
        return 4
    print(">", spec.get("display"))
    p = subprocess.run(spec["capture_cmd"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                       cwd=spec.get("cwd") or None, creationflags=CREATE_NO_WINDOW if IS_WIN else 0, timeout=300)
    out = decode_bytes(p.stdout)
    sys.stdout.buffer.write(out.encode("utf-8", "replace"))
    print(f"\n[code {p.returncode}]")
    logger.info("run-capture %s : code %s", seed, p.returncode)
    return 0 if p.returncode == 0 else 5


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Arsenal - lanceur / catalogue (Projet Padawan)")
    ap.add_argument("--smoke", action="store_true", help="test automatique de l'interface puis sortie")
    ap.add_argument("--shot", default="", help="capture PNG de la fenetre puis sortie")
    ap.add_argument("--shot-view", default="main",
                    help="main|securite|liste|web|recherche|editeur|editeur1|aide|palette|ip|resultat|confirm")
    ap.add_argument("--geometry", default="", help="ex. 1280x720+0+0 (sinon plein ecran)")
    ap.add_argument("--data", default="", help="autre fichier arsenal.json")
    ap.add_argument("--list", action="store_true", help="nombre d'entrees par categorie")
    ap.add_argument("--check", action="store_true", help="programmes/chemins absents de ce PC")
    ap.add_argument("--run-capture", default="", help="execute une entree non admin (seed) et affiche sa sortie")
    ap.add_argument("--set", action="append", default=[], help="VAR=valeur pour --run-capture")
    ap.add_argument("--make-icons", action="store_true", help="genere arsenal1.ico/.png puis sortie")
    args = ap.parse_args(argv)
    setup_logging()
    try:
        n_path = refresh_path_from_registry()
        if n_path:
            logger.info("PATH complété avec %d dossier(s) du Registre", n_path)
    except Exception:
        pass
    if IS_WIN:
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
        except Exception:
            pass
    if args.make_icons:
        print(generate_app_icons(BASE))
        return 0
    if args.list or args.check or args.run_capture:
        st = Store(args.data or DATA_FILE, readonly=True)
        st.load()
        if args.list:
            return cli_list(st)
        if args.check:
            return cli_check(st)
        return cli_run_capture(st, args.run_capture, args.set)
    if tk is None:
        print("tkinter est requis")
        return 1
    special = args.smoke or bool(args.shot)
    mutex = None
    if not special:
        ok, mutex = _single_instance()
        if not ok:
            _focus_existing()
            return 0
    try:
        generate_app_icons(BASE)
    except Exception:
        pass
    try:
        app = ArsenalApp(args)
    except Exception:
        logger.error("démarrage : %s", traceback.format_exc())
        raise
    if args.smoke:
        app.update()
        code = run_smoke(app)
        app.destroy()
        return code
    if args.shot:
        run_shot(app, args.shot, args.shot_view)

    def report(*a):
        logger.error("erreur Tk : %s", "".join(traceback.format_exception(*a)))
    app.report_callback_exception = report
    app.mainloop()
    _ = mutex
    return 0


if __name__ == "__main__":
    sys.exit(main())
