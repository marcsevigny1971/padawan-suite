# -*- coding: utf-8 -*-
"""padawan_atelier.py — 💻 Atelier de Padawan (v40.0)

Mode programmeur : chat à gauche, éditeur de code à droite (onglets, numéros de ligne,
coloration HTML/CSS/JS/Python/PHP/Arduino/JSON), aperçu (navigateur à rechargement auto,
Python exécuté dans un panneau), déploiement (dossier Python, dossier Web local, serveur
FTP/FTPS/SFTP), diff avant d'écraser + .bak, projets, modèles de départ, snippets, outils.

Tout est local. Réglages : <PRIVATE_DIR>/atelier.json · projets : atelier_projets.json ·
espace de travail : <PRIVATE_DIR>/atelier/<projet>/ · copies .bak : C:\\web_private\\bak\\atelier\\.
Module facultatif : Padawan fonctionne sans lui. À inclure dans _build_distribution.ps1.
"""
from __future__ import annotations

import base64
import difflib
import http.server
import json
import keyword
import os
import queue
import re
import shutil
import socketserver
import subprocess
import sys
import threading
import time
import webbrowser
import zipfile
from bisect import bisect_right
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, simpledialog, ttk

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

try:  # v40.1 🖼→ANSI (module facultatif : l'Atelier marche sans lui)
    import padawan_ansi as _ANSI
except Exception:  # pragma: no cover
    _ANSI = None

VERSION = "1.4"  # v41.4 : demande de modification dans le chat → vrai fichier modifié (SEARCH/REPLACE appliqué localement, garde-fou anti-fragment, 1 relance, aperçu)
# v41.3 : 📎 vraie fenêtre de choix (au premier plan), retour visible, tout fichier texte (php, ino…), gros fichier ouvert joint en partie
# v41.2 : 📎 Insérer un fichier (au curseur, joint au chat, ou ouvert dans un onglet ; Ctrl+I, glisser-déposer)
# v40.1 : 🖼→ANSI (convertisseur d'images en art ANSI/ASCII, module padawan_ansi.py)
IS_WIN = os.name == "nt"
NOWIN = 0x08000000 if IS_WIN else 0          # CREATE_NO_WINDOW
NEWCON = 0x00000010 if IS_WIN else 0         # CREATE_NEW_CONSOLE

# ─────────────────────────────────────────────────────────────── utilitaires ──

def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _loadj(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _savej(path: str, data) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def read_text(path: str) -> str:
    with open(path, "rb") as f:
        raw = f.read()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        try:
            return raw.decode("utf-16")
        except UnicodeDecodeError:
            pass
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


TEXT_EXT = {".php", ".phtml", ".html", ".htm", ".js", ".mjs", ".ts", ".css", ".scss", ".py", ".pyw", ".ino", ".c", ".h",
            ".cpp", ".hpp", ".cs", ".java", ".json", ".sql", ".txt", ".md", ".bat", ".cmd", ".ps1", ".psm1", ".sh", ".xml",
            ".ini", ".cfg", ".conf", ".csv", ".tsv", ".log", ".yml", ".yaml", ".toml", ".ans", ".asc", ".nfo", ".bas",
            ".pas", ".lua", ".rb", ".go", ".rs", ".vbs", ".reg", ".htaccess", ".env", ".svg", ".tex", ".rtf", ".iss"}
IMG_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".ico", ".tif", ".tiff"}
ATTACH_MAX = 20000      # caractères joints au chat par fichier
INSERT_MAX = 400_000    # caractères insérés dans l'éditeur


def file_kind(path: str) -> str:
    """v41.2 : 'image', 'text' ou 'binary' (octet NUL / trop de caractères de contrôle au début)."""
    ext = os.path.splitext(path)[1].lower() or os.path.basename(path).lower()
    if ext in IMG_EXT:
        return "image"
    if ext in TEXT_EXT:
        return "text"
    try:
        with open(path, "rb") as f:
            head = f.read(8192)
    except Exception:
        return "binary"
    if head[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return "text"
    if b"\x00" in head:
        return "binary"
    bad = sum(1 for c in head if c < 9 or 13 < c < 32)
    return "binary" if head and bad > len(head) * 0.05 else "text"


def clip_text(txt: str, limit: int) -> Tuple[str, bool]:
    if len(txt) <= limit:
        return txt, False
    return txt[:limit] + f"\n…[tronqué : {limit:,} sur {len(txt):,} caractères]".replace(",", " "), True


def write_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def slugify(name: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", s).strip("._-").lower()
    return s[:48] or "projet"


def safe_name(fn: str) -> str:
    fn = os.path.basename((fn or "").replace("\\", "/").strip().strip("`*\"' "))
    fn = re.sub(r'[<>:"|?*\x00-\x1f]', "_", fn)
    return fn[:80]


def find_python() -> str:
    """python.exe (console) de la même installation que Padawan (pythonw → python)."""
    exe = sys.executable or "python"
    d, b = os.path.split(exe)
    if b.lower() == "pythonw.exe":
        c = os.path.join(d, "python.exe")
        if os.path.isfile(c):
            return c
    return exe


def find_tool(name: str, extra: Tuple[str, ...] = ()) -> str:
    for p in extra:
        if p and os.path.isfile(p):
            return p
    return shutil.which(name) or ""


def find_php() -> str:
    return find_tool("php", (r"C:\xampp\php\php.exe", r"C:\php\php.exe"))


def find_git() -> str:
    return find_tool("git", (r"C:\Program Files\Git\cmd\git.exe",))


def apache_docroot() -> str:
    """DocumentRoot de XAMPP s'il existe (pour suggérer le dossier Web local)."""
    for conf in (r"C:\xampp\apache\conf\httpd.conf",):
        try:
            for line in read_text(conf).splitlines():
                m = re.match(r'\s*DocumentRoot\s+"?([^"]+)"?', line)
                if m:
                    return os.path.normpath(m.group(1))
        except Exception:
            pass
    return ""


def clean_env() -> Dict[str, str]:
    """Environnement propre pour les programmes lancés (aucune variable de test PADAWAN_*)."""
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("PADAWAN_")}
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONUTF8"] = "1"
    return env


# ─────────────────────────────────────────── mot de passe (DPAPI Windows) ──

def protect(secret: str) -> str:
    """Chiffre avec DPAPI (lié à TA session Windows). Hors Windows : simple encodage, signalé."""
    if not secret:
        return ""
    data = secret.encode("utf-8")
    if IS_WIN:
        try:
            import ctypes
            from ctypes import wintypes

            class BLOB(ctypes.Structure):
                _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]
            buf = ctypes.create_string_buffer(data, len(data))
            inp = BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
            out = BLOB()
            if ctypes.windll.crypt32.CryptProtectData(ctypes.byref(inp), "Padawan Atelier", None, None,
                                                      None, 0x01, ctypes.byref(out)):
                enc = ctypes.string_at(out.pbData, out.cbData)
                ctypes.windll.kernel32.LocalFree(out.pbData)
                return "dpapi:" + base64.b64encode(enc).decode()
        except Exception:
            pass
    return "b64:" + base64.b64encode(data).decode()


def unprotect(blob: str) -> str:
    if not blob:
        return ""
    try:
        kind, _, b = blob.partition(":")
        raw = base64.b64decode(b)
        if kind == "b64":
            return raw.decode("utf-8")
        if kind == "dpapi" and IS_WIN:
            import ctypes
            from ctypes import wintypes

            class BLOB(ctypes.Structure):
                _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]
            buf = ctypes.create_string_buffer(raw, len(raw))
            inp = BLOB(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
            out = BLOB()
            if ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(inp), None, None, None, None, 0x01,
                                                        ctypes.byref(out)):
                dec = ctypes.string_at(out.pbData, out.cbData)
                ctypes.windll.kernel32.LocalFree(out.pbData)
                return dec.decode("utf-8")
    except Exception:
        pass
    return ""


# ──────────────────────────────────────────────────────────────── langages ──

EXT_LANG = {
    ".py": "python", ".pyw": "python", ".html": "html", ".htm": "html", ".css": "css",
    ".js": "js", ".mjs": "js", ".json": "json", ".php": "php", ".ino": "arduino",
    ".cpp": "arduino", ".c": "arduino", ".h": "arduino", ".hpp": "arduino",
    ".bat": "bat", ".cmd": "bat", ".ps1": "ps", ".sql": "sql", ".md": "text", ".txt": "text",
    ".xml": "html", ".svg": "html",
}
LANG_LABEL = {"python": "Python", "html": "HTML", "css": "CSS", "js": "JavaScript", "json": "JSON",
              "php": "PHP", "arduino": "Arduino/C++", "bat": "Batch", "ps": "PowerShell", "sql": "SQL",
              "text": "Texte"}
FENCE_LANG = {"python": "python", "py": "python", "html": "html", "htm": "html", "xml": "html",
              "css": "css", "js": "js", "javascript": "js", "json": "json", "php": "php",
              "arduino": "arduino", "ino": "arduino", "cpp": "arduino", "c++": "arduino", "c": "arduino",
              "bat": "bat", "batch": "bat", "cmd": "bat", "powershell": "ps", "ps1": "ps", "sql": "sql",
              "text": "text", "txt": "text", "": "text"}
LANG_EXT = {"python": ".py", "html": ".html", "css": ".css", "js": ".js", "json": ".json", "php": ".php",
            "arduino": ".ino", "bat": ".bat", "ps": ".ps1", "sql": ".sql", "text": ".txt"}
DEFAULT_NAME = {"python": "script.py", "html": "index.html", "css": "style.css", "js": "app.js",
                "json": "data.json", "php": "index.php", "arduino": "sketch.ino", "bat": "lancer.bat",
                "ps": "script.ps1", "sql": "requete.sql", "text": "notes.txt"}
COMMENT = {"python": ("# ", ""), "html": ("<!-- ", " -->"), "css": ("/* ", " */"), "js": ("// ", ""),
           "php": ("// ", ""), "arduino": ("// ", ""), "json": ("", ""), "bat": ("REM ", ""),
           "ps": ("# ", ""), "sql": ("-- ", ""), "text": ("# ", "")}


def lang_of(name: str) -> str:
    return EXT_LANG.get(os.path.splitext(name or "")[1].lower(), "text")


def _kw(words: str) -> str:
    return r"\b(?:" + "|".join(sorted(set(words.split()), key=len, reverse=True)) + r")\b"


_C_KW = ("if else for while do switch case default break continue return void int long short char "
         "float double bool boolean unsigned signed const static struct class public private protected "
         "new delete true false null nullptr include define ifdef ifndef endif byte word String uint8_t "
         "uint16_t uint32_t int8_t int16_t int32_t size_t auto volatile sizeof typedef enum namespace using")
_ARD_FN = ("setup loop pinMode digitalWrite digitalRead analogRead analogWrite delay delayMicroseconds "
           "millis micros Serial begin print println available read write tone noTone map constrain "
           "attachInterrupt HIGH LOW INPUT OUTPUT INPUT_PULLUP LED_BUILTIN A0 A1 A2 A3 A4 A5")
_JS_KW = ("var let const function return if else for while do switch case default break continue new "
          "this class extends import export from async await try catch finally throw typeof instanceof "
          "true false null undefined of in delete yield")
_JS_FN = "document window console alert fetch setTimeout setInterval Math JSON Array Object Promise localStorage"
_PHP_KW = ("echo print if else elseif endif foreach endforeach for while function return class public "
           "private protected new null true false array isset empty require require_once include "
           "include_once try catch throw static global as die exit")
_PY_BI = ("print input len range open str int float list dict set tuple bool type isinstance enumerate "
          "zip map filter sorted min max sum abs round any all super object Exception ValueError "
          "KeyError TypeError ImportError ModuleNotFoundError self cls")

# (tag, regex, groupe) — l'ordre compte peu : les tags string/comment sont au-dessus à l'affichage.
RULES: Dict[str, List[Tuple[str, str, int]]] = {
    "python": [
        ("kw", _kw(" ".join(keyword.kwlist)), 0),
        ("bi", _kw(_PY_BI), 0),
        ("num", r"\b(?:0x[0-9a-fA-F]+|\d+\.?\d*(?:e[+-]?\d+)?)\b", 0),
        ("deco", r"^\s*@[\w.]+", 0),
        ("fn", r"\b(?:def|class)\s+(\w+)", 1),
        ("str", r"(?:[rbfuRBFU]{0,2})(?:\"\"\"[\s\S]*?(?:\"\"\"|$(?![\s\S]))|'''[\s\S]*?(?:'''|$(?![\s\S]))|\"(?:\\.|[^\"\\\n])*\"?|'(?:\\.|[^'\\\n])*'?)", 0),
        ("com", r"#[^\n]*", 0),
    ],
    "html": [
        ("tag", r"</?[A-Za-z][\w:-]*|/?>", 0),
        ("attr", r"\s([A-Za-z_:][\w:.-]*)(?==)", 1),
        ("str", r"\"[^\"\n]*\"|'[^'\n]*'", 0),
        ("ent", r"&[#\w]+;", 0),
        ("com", r"<!--[\s\S]*?(?:-->|$(?![\s\S]))", 0),
    ],
    "css": [
        ("tag", r"(?m)^[^{}\n/@]+(?=\{)", 0),
        ("attr", r"[\w-]+(?=\s*:[^;{}]*[;}])", 0),
        ("num", r"#[0-9a-fA-F]{3,8}\b|\b\d+\.?\d*(?:px|em|rem|%|vh|vw|s|ms|deg|pt)?\b", 0),
        ("kw", r"@[\w-]+|!important", 0),
        ("str", r"\"[^\"\n]*\"|'[^'\n]*'", 0),
        ("com", r"/\*[\s\S]*?(?:\*/|$(?![\s\S]))", 0),
    ],
    "js": [
        ("kw", _kw(_JS_KW), 0),
        ("bi", _kw(_JS_FN), 0),
        ("num", r"\b\d+\.?\d*\b", 0),
        ("fn", r"\bfunction\s+(\w+)", 1),
        ("str", r"`(?:\\.|[^`\\])*`?|\"(?:\\.|[^\"\\\n])*\"?|'(?:\\.|[^'\\\n])*'?", 0),
        ("com", r"//[^\n]*|/\*[\s\S]*?(?:\*/|$(?![\s\S]))", 0),
    ],
    "json": [
        ("attr", r"\"(?:\\.|[^\"\\\n])*\"(?=\s*:)", 0),
        ("str", r"(?<=:)\s*\"(?:\\.|[^\"\\\n])*\"|(?<=[\[,])\s*\"(?:\\.|[^\"\\\n])*\"", 0),
        ("num", r"-?\b\d+\.?\d*(?:[eE][+-]?\d+)?\b", 0),
        ("kw", r"\b(?:true|false|null)\b", 0),
    ],
    "php": [
        ("tag", r"</?[A-Za-z][\w:-]*|/?>", 0),
        ("deco", r"<\?php|\?>", 0),
        ("kw", _kw(_PHP_KW), 0),
        ("var", r"\$\w+", 0),
        ("num", r"\b\d+\.?\d*\b", 0),
        ("str", r"\"(?:\\.|[^\"\\\n])*\"?|'(?:\\.|[^'\\\n])*'?", 0),
        ("com", r"//[^\n]*|#[^\n]*|/\*[\s\S]*?(?:\*/|$(?![\s\S]))|<!--[\s\S]*?(?:-->|$(?![\s\S]))", 0),
    ],
    "arduino": [
        ("kw", _kw(_C_KW), 0),
        ("bi", _kw(_ARD_FN), 0),
        ("deco", r"(?m)^\s*#\s*\w+", 0),
        ("num", r"\b(?:0x[0-9a-fA-F]+|\d+\.?\d*[fFuUlL]?)\b", 0),
        ("str", r"\"(?:\\.|[^\"\\\n])*\"?|'(?:\\.|[^'\\\n])*'?", 0),
        ("com", r"//[^\n]*|/\*[\s\S]*?(?:\*/|$(?![\s\S]))", 0),
    ],
    "bat": [
        ("kw", r"(?i)\b(?:echo|set|if|else|goto|call|for|in|do|exit|pause|cls|rem|not|exist|setlocal|endlocal|start|cd|title|color)\b", 0),
        ("var", r"%[\w~]+%?|![\w]+!", 0),
        ("deco", r"(?m)^:\w+", 0),
        ("str", r"\"[^\"\n]*\"", 0),
        ("com", r"(?im)^\s*(?:rem\b|::)[^\n]*", 0),
    ],
    "ps": [
        ("kw", r"(?i)\b(?:function|param|if|else|elseif|foreach|for|while|return|try|catch|finally|switch|in)\b", 0),
        ("var", r"\$[\w:]+", 0),
        ("bi", r"\b[A-Z][a-z]+-[A-Z]\w+\b", 0),
        ("str", r"\"(?:`.|[^\"`])*\"|'[^'\n]*'", 0),
        ("com", r"#[^\n]*|<#[\s\S]*?#>", 0),
    ],
    "sql": [
        ("kw", r"(?i)\b(?:select|from|where|insert|into|values|update|set|delete|create|table|drop|alter|join|left|right|inner|on|and|or|not|null|primary|key|order|by|group|limit|as|int|varchar|text|auto_increment|default)\b", 0),
        ("num", r"\b\d+\b", 0),
        ("str", r"'(?:''|[^'])*'?", 0),
        ("com", r"--[^\n]*|/\*[\s\S]*?\*/", 0),
    ],
    "text": [],
}
_RX: Dict[str, List[Tuple[str, "re.Pattern", int]]] = {}


def rules_for(lang: str):
    if lang not in _RX:
        out = []
        for tag, rx, g in RULES.get(lang, []):
            fl = re.M
            try:
                out.append((tag, re.compile(rx, fl), g))
            except re.error:
                pass
        _RX[lang] = out
    return _RX[lang]


THEMES = {
    "padawan": {"bg": "#12161e", "fg": "#e8ecf4", "gut": "#0c0f15", "gutfg": "#5d6880", "cur": "#1b212c",
                "sel": "#2f4a6e", "caret": "#fffef0", "kw": "#c792ea", "bi": "#82aaff", "num": "#f78c6c",
                "str": "#c3e88d", "com": "#6b7891", "fn": "#ffcb6b", "deco": "#89ddff", "tag": "#f07178",
                "attr": "#ffcb6b", "ent": "#f78c6c", "var": "#89ddff", "brk": "#3b5a3b", "found": "#5a4a1a",
                "font": "Consolas"},
    "dos": {"bg": "#0000aa", "fg": "#ffffff", "gut": "#000080", "gutfg": "#55ffff", "cur": "#0000c8",
            "sel": "#00aaaa", "caret": "#ffff55", "kw": "#ffff55", "bi": "#55ffff", "num": "#ff55ff",
            "str": "#55ff55", "com": "#aaaaaa", "fn": "#ffffff", "deco": "#ff5555", "tag": "#ffff55",
            "attr": "#55ffff", "ent": "#ff55ff", "var": "#55ff55", "brk": "#aa5500", "found": "#aa00aa",
            "font": "Consolas"},
}


# ───────────────────────────────────────────── lecture des réponses du modèle ──

_FENCE_RX = re.compile(r"(?m)^[ \t]*(`{3,}|~{3,})[ \t]*([^\n`]*)\n")
_NAME_RX = re.compile(r"([\w][\w .()-]{0,60}\.(?:py|pyw|html?|css|js|mjs|json|php|ino|cpp|c|h|hpp|bat|cmd|ps1|sql|md|txt|xml|svg))\b",
                      re.I)


def extract_blocks(text: str) -> List[Dict[str, str]]:
    """Blocs de code d'une réponse : [{lang, name, code, before}] (bloc final non fermé accepté)."""
    out, pos = [], 0
    while True:
        m = _FENCE_RX.search(text, pos)
        if not m:
            break
        fence, info = m.group(1), m.group(2).strip()
        end_rx = re.compile(r"(?m)^[ \t]*" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}[ \t]*$")
        e = end_rx.search(text, m.end())
        code = text[m.end(): e.start() if e else len(text)]
        if code.endswith("\n"):
            code = code[:-1]
        before = text[max(0, m.start() - 240): m.start()]
        parts = info.split()
        lang_raw = (parts[0].lower() if parts else "")
        name = ""
        if _NAME_RX.fullmatch(lang_raw or "x"):
            name, lang_raw = lang_raw, ""
        for p in parts[1:]:
            mm = _NAME_RX.search(p.replace("title=", "").strip("\"'"))
            if mm:
                name = mm.group(1)
                break
        if not name:
            last = [ln for ln in before.strip().splitlines() if ln.strip()][-1:]
            if last:
                cand = _NAME_RX.findall(last[0])
                if cand and len(last[0]) < 140:
                    name = cand[-1]
        if not name:
            first = code.lstrip().split("\n", 1)[0][:120]
            mm = re.match(r"^(?:#|//|<!--|/\*|--|REM)\s*(?:fichier\s*:?|file\s*:?|nom\s*:?)?\s*"
                          r"([\w.-]+\.\w{1,5})\s*(?:-->|\*/)?\s*$", first, re.I)
            if mm and _NAME_RX.fullmatch(mm.group(1)):
                name = mm.group(1)
        lang = FENCE_LANG.get(lang_raw, "") if lang_raw else ""
        if name and (not lang or lang == "text"):
            lang = lang_of(name)
        if not lang:
            lang = guess_lang(code)
        name = safe_name(name) if name else ""
        if name and not os.path.splitext(name)[1]:
            name += LANG_EXT.get(lang, ".txt")
        if code.strip():
            out.append({"lang": lang, "name": name, "code": code, "before": before})
        pos = e.end() if e else len(text)
    return out


def guess_lang(code: str) -> str:
    c = code.lstrip()[:2000]
    if c.startswith("<?php") or "<?php" in c:
        return "php"
    if re.search(r"(?i)<!doctype html|<html|<body|<div\b", c):
        return "html"
    if re.search(r"\bvoid\s+setup\s*\(", c):
        return "arduino"
    if re.search(r"(?m)^\s*(def |import |from \w+ import|class \w+[:(]|print\()", c):
        return "python"
    if re.search(r"(?m)^[\s\w.#:,>-]+\{[^}]*:[^}]*\}", c) and "function" not in c:
        return "css"
    if re.search(r"\b(function|const|let|=>|document\.)", c):
        return "js"
    if c[:1] in "{[":
        try:
            json.loads(code)
            return "json"
        except Exception:
            pass
    return "text"


CODE_REQ_RX = re.compile(
    r"(?i)\b(code|script|programme|programmer|coder|fonction|python|html|css|javascript|\bjs\b|php|mysql|"
    r"arduino|sketch|page web|site web|menu ascii|bug|traceback|compile|regex|api|json|batch|powershell|"
    r"\.py\b|\.html?\b|\.php\b|\.ino\b)")
CODE_VERB_RX = re.compile(r"(?i)\b(écri[st]|ecri[st]|fai[st]|fais[- ]moi|crée|cree|créer|creer|génère|genere|"
                          r"code|programme|corrige|débogue|debug|modifie|ajoute|convertis|optimise|make|write)")


def looks_like_code_request(q: str) -> bool:
    """Heuristique pour la suggestion « 💻 Ouvrir dans l'Atelier » du Chercheur."""
    q = q or ""
    if "```" in q or re.search(r"(?m)^\s*(def |import |<\?php|<html|#include|void setup)", q):
        return True
    return bool(CODE_REQ_RX.search(q) and CODE_VERB_RX.search(q))


def diff_hunks(a: List[str], b: List[str]):
    """Opcodes non égaux de SequenceMatcher (lignes)."""
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    return sm.get_opcodes()


def apply_hunks(a: List[str], b: List[str], ops, accepted: Dict[int, bool]) -> List[str]:
    out: List[str] = []
    for k, (tag, i1, i2, j1, j2) in enumerate(ops):
        if tag == "equal":
            out.extend(a[i1:i2])
        elif accepted.get(k, True):
            out.extend(b[j1:j2])
        else:
            out.extend(a[i1:i2])
    return out


ANSI_RX = re.compile(r"\x1b\[([0-9;?]*)([A-Za-z])")
ANSI_COL = {30: "#000000", 31: "#cd3131", 32: "#0dbc79", 33: "#e5e510", 34: "#2472c8", 35: "#bc3fbc",
            36: "#11a8cd", 37: "#e5e5e5", 90: "#666666", 91: "#f14c4c", 92: "#23d18b", 93: "#f5f543",
            94: "#3b8eea", 95: "#d670d6", 96: "#29b8db", 97: "#ffffff"}

PIP_NAMES = {"cv2": "opencv-python", "PIL": "pillow", "yaml": "pyyaml", "bs4": "beautifulsoup4",
             "sklearn": "scikit-learn", "serial": "pyserial", "win32api": "pywin32", "win32con": "pywin32",
             "dateutil": "python-dateutil", "dotenv": "python-dotenv", "Crypto": "pycryptodome",
             "docx": "python-docx", "pptx": "python-pptx", "fitz": "pymupdf", "usb": "pyusb",
             "telegram": "python-telegram-bot", "magic": "python-magic", "OpenSSL": "pyopenssl"}


# ──────────────────────────────────────────────────────────────── l'éditeur ──

class CodeEditor(tk.Frame):
    """Text + numéros de ligne + coloration + mini-carte + aides de frappe."""

    BRACKETS = {"(": ")", "[": "]", "{": "}"}
    CLOSERS = {")": "(", "]": "[", "}": "{"}

    def __init__(self, master, *, path: str = "", name: str = "", text: str = "", theme: str = "padawan",
                 font_size: int = 11, on_change: Optional[Callable] = None, on_cursor: Optional[Callable] = None,
                 minimap: bool = True):
        super().__init__(master, bg=THEMES[theme]["bg"])
        self.path, self.name = path, name or os.path.basename(path) or "sans_titre.txt"
        self.lang = lang_of(self.name)
        self.theme, self.font_size = theme, font_size
        self.on_change, self.on_cursor = on_change, on_cursor
        self._hl_job = self._mm_job = None
        self.saved_text = text
        self.gutter = tk.Canvas(self, width=46, highlightthickness=0, bd=0)
        self.gutter.pack(side="left", fill="y")
        self.vsb = ttk.Scrollbar(self, orient="vertical")
        self.vsb.pack(side="right", fill="y")
        self.mm = tk.Canvas(self, width=70, highlightthickness=0, bd=0, cursor="hand2")
        if minimap:
            self.mm.pack(side="right", fill="y")
        self.hsb = ttk.Scrollbar(self, orient="horizontal")
        self.hsb.pack(side="bottom", fill="x")
        self.t = tk.Text(self, wrap="none", undo=True, maxundo=-1, autoseparators=True, relief="flat", bd=0,
                         padx=6, pady=4, tabs=("4c",), exportselection=True, insertwidth=2)
        self.t.pack(side="left", fill="both", expand=True)
        self.t.configure(yscrollcommand=self._yscroll, xscrollcommand=self.hsb.set)
        self.vsb.configure(command=self._yview)
        self.hsb.configure(command=self.t.xview)
        self.apply_theme(theme, font_size)
        self.t.insert("1.0", text)
        self.t.edit_reset()
        self.t.edit_modified(False)
        self.t.mark_set("insert", "1.0")
        b = self.t.bind
        b("<<Modified>>", self._modified)
        b("<KeyRelease>", self._cursor_moved, add="+")
        b("<ButtonRelease-1>", self._cursor_moved, add="+")
        b("<Return>", self._newline)
        b("<KP_Enter>", self._newline)
        b("<Tab>", self._tab)
        b("<Shift-Tab>", self._untab)
        b("<ISO_Left_Tab>", self._untab)
        b("<Control-slash>", self.toggle_comment)
        b("<Control-d>", self.dup_line)
        b("<Control-D>", self.dup_line)
        b("<Alt-Up>", lambda e: self.move_line(-1))
        b("<Alt-Down>", lambda e: self.move_line(1))
        b("<Control-y>", self._redo)
        b("<Control-Y>", self._redo)
        b("<Control-Shift-Z>", self._redo)
        b("<Control-z>", self._undo)
        b("<Control-Z>", self._undo)
        b("<Control-a>", self.select_all)
        b("<Control-A>", self.select_all)
        b("<BackSpace>", self._backspace)
        for ks, o, c in (("parenleft", "(", ")"), ("bracketleft", "[", "]"), ("braceleft", "{", "}")):
            b(f"<{ks}>", lambda e, o=o, c=c: self._auto_pair(o, c))
        b("<Control-MouseWheel>", self._zoom)
        b("<Configure>", lambda e: self._redraw(), add="+")
        self.gutter.bind("<Button-1>", self._gutter_click)
        self.mm.bind("<Button-1>", self._mm_click)
        self.mm.bind("<B1-Motion>", self._mm_click)
        self.mm.bind("<Configure>", lambda e: self._schedule_mm())
        self.mm.bind("<Map>", lambda e: self._schedule_mm())
        self.after_idle(self.highlight_all)
        self.after_idle(self._schedule_mm)

    # -- apparence
    def apply_theme(self, theme: str, font_size: Optional[int] = None):
        self.theme = theme if theme in THEMES else "padawan"
        if font_size:
            self.font_size = font_size
        T = THEMES[self.theme]
        f = (T["font"], self.font_size)
        self.configure(bg=T["bg"])
        self.t.configure(bg=T["bg"], fg=T["fg"], insertbackground=T["caret"], selectbackground=T["sel"],
                         selectforeground=T["fg"], font=f, inactiveselectbackground=T["sel"])
        self.gutter.configure(bg=T["gut"])
        self.mm.configure(bg=T["gut"])
        for tag in ("kw", "bi", "num", "str", "com", "fn", "deco", "tag", "attr", "ent", "var"):
            self.t.tag_configure(tag, foreground=T[tag])
        self.t.tag_configure("kw", font=(T["font"], self.font_size, "bold"))
        self.t.tag_configure("curline", background=T["cur"])
        self.t.tag_configure("brk", background=T["brk"])
        self.t.tag_configure("found", background=T["found"])
        self.t.tag_configure("errline", background="#5a1d22")
        self.t.tag_lower("curline")
        self.t.tag_raise("str")
        self.t.tag_raise("com")
        self.t.tag_raise("found")
        self.t.tag_raise("sel")
        try:
            import tkinter.font as tkf
            w = tkf.Font(font=f).measure("0")
            self.t.configure(tabs=(4 * w,))
        except Exception:
            pass
        self._redraw()
        self._schedule_mm()

    def _zoom(self, e):
        self.apply_theme(self.theme, max(7, min(28, self.font_size + (1 if e.delta > 0 else -1))))
        return "break"

    # -- défilement / gouttière
    def _yscroll(self, a, b):
        self.vsb.set(a, b)
        self._redraw()
        self._mm_view()

    def _yview(self, *a):
        self.t.yview(*a)
        self._redraw()

    def _redraw(self):
        g = self.gutter
        g.delete("all")
        T = THEMES[self.theme]
        try:
            total = int(self.t.index("end-1c").split(".")[0])
            width = max(3, len(str(total))) * (self.font_size - 2) + 14
            if int(g.cget("width")) != width:
                g.configure(width=width)
            cur = self.t.index("insert").split(".")[0]
            i = self.t.index("@0,0")
            while True:
                d = self.t.dlineinfo(i)
                if d is None:
                    break
                n = i.split(".")[0]
                g.create_text(width - 6, d[1] + d[3] // 2, anchor="e", text=n,
                              fill=T["caret"] if n == cur else T["gutfg"], font=(T["font"], self.font_size - 1))
                nxt = self.t.index(f"{i}+1line")
                if nxt == i:
                    break
                i = nxt
        except tk.TclError:
            pass

    def _gutter_click(self, e):
        i = self.t.index(f"@0,{e.y}")
        ln = i.split(".")[0]
        self.t.tag_remove("sel", "1.0", "end")
        self.t.tag_add("sel", f"{ln}.0", f"{ln}.0+1line")
        self.t.mark_set("insert", f"{ln}.0")
        self.t.focus_set()

    # -- mini-carte
    def _schedule_mm(self):
        if self._mm_job:
            try:
                self.after_cancel(self._mm_job)
            except Exception:
                pass
        self._mm_job = self.after(400, self._draw_mm)

    def _draw_mm(self):
        self._mm_job = None
        c = self.mm
        if not c.winfo_ismapped():
            return
        c.delete("all")
        T = THEMES[self.theme]
        lines = self.t.get("1.0", "end-1c").split("\n")
        h = max(1, c.winfo_height())
        n = max(1, len(lines))
        step = min(3.0, h / n)
        for k, ln in enumerate(lines[:4000]):
            s = ln.rstrip()
            if not s:
                continue
            ind = (len(ln) - len(ln.lstrip())) / 2
            w = min(64, len(s) / 2)
            st = s.lstrip()
            col = T["com"] if st.startswith(("#", "//", "<!--", "/*")) else (
                T["fn"] if re.match(r"(def |class |function |void |<h\d|@)", st) else T.get("mm", "#7d8aa3"))
            y = k * step
            c.create_rectangle(3 + ind, y, 3 + ind + max(2, w - ind), y + max(1, step - 0.5), fill=col, width=0)
        self._mm_view()

    def _mm_view(self):
        c = self.mm
        try:
            c.delete("view")
            a, b = self.t.yview()
            n = max(1, int(self.t.index("end-1c").split(".")[0]))
            h = max(1, c.winfo_height())
            used = min(h, n * min(3.0, h / n))
            c.create_rectangle(0, a * used, 69, max(a * used + 6, b * used), outline=THEMES[self.theme]["caret"],
                               tags="view")
        except tk.TclError:
            pass

    def _mm_click(self, e):
        n = max(1, int(self.t.index("end-1c").split(".")[0]))
        h = max(1, self.mm.winfo_height())
        step = min(3.0, h / n)
        ln = max(1, min(n, int(e.y / step) + 1))
        self.t.see(f"{ln}.0")
        self.t.mark_set("insert", f"{ln}.0")
        self._cursor_moved()

    # -- coloration
    def _modified(self, e=None):
        if not self.t.edit_modified():
            return
        self.t.edit_modified(False)
        if self._hl_job:
            try:
                self.after_cancel(self._hl_job)
            except Exception:
                pass
        self._hl_job = self.after(160, self.highlight_all)
        self._schedule_mm()
        self._redraw()
        if self.on_change:
            self.on_change(self)

    def highlight_all(self):
        self._hl_job = None
        t = self.t
        text = t.get("1.0", "end-1c")
        big = len(text) > 400_000
        tags = ("kw", "bi", "num", "str", "com", "fn", "deco", "tag", "attr", "ent", "var")
        for tg in tags:
            t.tag_remove(tg, "1.0", "end")
        if big:
            return
        starts = [0]
        for m in re.finditer("\n", text):
            starts.append(m.end())

        def idx(off):
            ln = bisect_right(starts, off) - 1
            return f"{ln + 1}.{off - starts[ln]}"
        for tag, rx, g in rules_for(self.lang):
            for m in rx.finditer(text):
                a, b = (m.start(g), m.end(g)) if g else (m.start(), m.end())
                if b > a:
                    t.tag_add(tag, idx(a), idx(b))
        if self.lang == "html":  # <style> et <script> intégrés
            for m in re.finditer(r"(?is)<style[^>]*>(.*?)</style>|<script[^>]*>(.*?)</script>", text):
                g, lg = (1, "css") if m.group(1) is not None else (2, "js")
                base = m.start(g)
                seg = m.group(g)
                for tg in tags:
                    t.tag_remove(tg, idx(base), idx(m.end(g)))
                for tag, rx, gg in rules_for(lg):
                    for mm in rx.finditer(seg):
                        a, b = (mm.start(gg), mm.end(gg)) if gg else (mm.start(), mm.end())
                        if b > a:
                            t.tag_add(tag, idx(base + a), idx(base + b))
        self._cursor_moved()

    def set_lang_from_name(self, name: str):
        self.name = name
        self.lang = lang_of(name)
        self.highlight_all()

    # -- curseur, accolades
    def _cursor_moved(self, e=None):
        t = self.t
        t.tag_remove("curline", "1.0", "end")
        t.tag_add("curline", "insert linestart", "insert lineend+1c")
        t.tag_remove("brk", "1.0", "end")
        for pos in ("insert", "insert-1c"):
            ch = t.get(pos)
            if ch in self.BRACKETS or ch in self.CLOSERS:
                m = self._match(pos, ch)
                if m:
                    t.tag_add("brk", pos)
                    t.tag_add("brk", m)
                break
        self._redraw()
        if self.on_cursor:
            self.on_cursor(self)

    def _match(self, pos: str, ch: str) -> Optional[str]:
        t = self.t
        fwd = ch in self.BRACKETS
        other = self.BRACKETS.get(ch) or self.CLOSERS.get(ch)
        if fwd:
            seg = t.get(pos, f"{pos}+20000c")
            depth = 0
            for k, c in enumerate(seg):
                if c == ch:
                    depth += 1
                elif c == other:
                    depth -= 1
                    if depth == 0:
                        return t.index(f"{pos}+{k}c")
        else:
            seg = t.get(f"{pos}-20000c", f"{pos}+1c")
            depth = 0
            for k in range(len(seg) - 1, -1, -1):
                c = seg[k]
                if c == ch:
                    depth += 1
                elif c == other:
                    depth -= 1
                    if depth == 0:
                        return t.index(f"{pos}+1c-{len(seg) - k}c")
        return None

    # -- frappe
    def _newline(self, e=None):
        t = self.t
        t.edit_separator()
        line = t.get("insert linestart", "insert")
        ind = re.match(r"[ \t]*", line).group(0)
        st = line.rstrip()
        extra = ""
        if (self.lang == "python" and st.endswith(":")) or st.endswith(("{", "(", "[")) or \
                (self.lang == "html" and re.search(r"<(?!/)(?!br|img|meta|link|input|hr)[a-zA-Z][^>]*>$", st)):
            extra = "    "
        nxt = t.get("insert")
        if t.tag_ranges("sel"):
            t.delete("sel.first", "sel.last")
        if extra and nxt in ")]}" and nxt and st.endswith(("{", "(", "[")):
            t.insert("insert", "\n" + ind + extra + "\n" + ind)
            t.mark_set("insert", "insert-1line lineend")
        else:
            t.insert("insert", "\n" + ind + extra)
        t.see("insert")
        return "break"

    def _sel_lines(self) -> Tuple[int, int]:
        t = self.t
        if t.tag_ranges("sel"):
            a = int(t.index("sel.first").split(".")[0])
            bi = t.index("sel.last")
            b = int(bi.split(".")[0])
            if bi.endswith(".0") and b > a:
                b -= 1
            return a, b
        n = int(t.index("insert").split(".")[0])
        return n, n

    def _tab(self, e=None):
        t = self.t
        if t.tag_ranges("sel") and t.index("sel.first").split(".")[0] != t.index("sel.last").split(".")[0]:
            a, b = self._sel_lines()
            self._begin()
            for ln in range(a, b + 1):
                t.insert(f"{ln}.0", "    ")
            self._end()
            t.tag_add("sel", f"{a}.0", f"{b}.end")
        else:
            t.insert("insert", "    ")
        return "break"

    def _untab(self, e=None):
        t = self.t
        a, b = self._sel_lines()
        self._begin()
        for ln in range(a, b + 1):
            s = t.get(f"{ln}.0", f"{ln}.4")
            k = len(s) - len(s.lstrip(" ")) if s.strip(" ") != "" or s else 0
            k = min(4, len(s) - len(s.lstrip(" ")))
            if s.startswith("\t"):
                k = 1
            if k:
                t.delete(f"{ln}.0", f"{ln}.{k}")
        self._end()
        return "break"

    def _backspace(self, e=None):
        t = self.t
        if t.tag_ranges("sel"):
            return None
        before = t.get("insert linestart", "insert")
        if before and before.strip(" ") == "" and len(before) >= 4:
            t.delete(f"insert-{len(before) % 4 or 4}c", "insert")
            return "break"
        pair = t.get("insert-1c", "insert+1c")
        if pair in ("()", "[]", "{}", '""', "''"):
            t.delete("insert-1c", "insert+1c")
            return "break"
        return None

    def _auto_pair(self, o, c):
        t = self.t
        if t.tag_ranges("sel"):
            s = t.get("sel.first", "sel.last")
            t.delete("sel.first", "sel.last")
            t.insert("insert", o + s + c)
            return "break"
        nxt = t.get("insert")
        if nxt in ("", "\n", " ", ")", "]", "}", ",", ";"):
            t.insert("insert", o + c)
            t.mark_set("insert", "insert-1c")
            return "break"
        return None

    def toggle_comment(self, e=None):
        t = self.t
        pre, post = COMMENT.get(self.lang, ("# ", ""))
        if not pre:
            return "break"
        a, b = self._sel_lines()
        lines = [t.get(f"{ln}.0", f"{ln}.end") for ln in range(a, b + 1)]
        body = [l for l in lines if l.strip()]
        on = all(l.lstrip().startswith(pre.strip()) for l in body) if body else False
        self._begin()
        for k, ln in enumerate(range(a, b + 1)):
            l = lines[k]
            if not l.strip():
                continue
            ind = len(l) - len(l.lstrip())
            if on:
                s = l[ind:]
                s = s[len(pre):] if s.startswith(pre) else s[len(pre.strip()):]
                if post and s.rstrip().endswith(post.strip()):
                    s = s.rstrip()
                    s = s[: -len(post)] if s.endswith(post) else s[: -len(post.strip())]
                new = l[:ind] + s
            else:
                new = l[:ind] + pre + l[ind:] + post
            t.delete(f"{ln}.0", f"{ln}.end")
            t.insert(f"{ln}.0", new)
        self._end()
        return "break"

    def dup_line(self, e=None):
        t = self.t
        if t.tag_ranges("sel"):
            s = t.get("sel.first", "sel.last")
            t.insert("sel.last", s)
        else:
            line = t.get("insert linestart", "insert lineend")
            t.insert("insert lineend", "\n" + line)
            t.mark_set("insert", "insert+1line")
        return "break"

    def move_line(self, d: int):
        t = self.t
        a, b = self._sel_lines()
        last = int(t.index("end-1c").split(".")[0])
        if (d < 0 and a == 1) or (d > 0 and b >= last):
            return "break"
        col = t.index("insert").split(".")[1]
        block = t.get(f"{a}.0", f"{b}.end")
        self._begin()
        if d < 0:
            other = t.get(f"{a - 1}.0", f"{a - 1}.end")
            t.delete(f"{a - 1}.0", f"{b}.end")
            t.insert(f"{a - 1}.0", block + "\n" + other)
            na = a - 1
        else:
            other = t.get(f"{b + 1}.0", f"{b + 1}.end")
            t.delete(f"{a}.0", f"{b + 1}.end")
            t.insert(f"{a}.0", other + "\n" + block)
            na = a + 1
        self._end()
        t.tag_remove("sel", "1.0", "end")
        if b > a:
            t.tag_add("sel", f"{na}.0", f"{na + b - a}.end")
        t.mark_set("insert", f"{na}.{col}")
        return "break"

    def _undo(self, e=None):
        try:
            self.t.edit_undo()
        except tk.TclError:
            pass
        return "break"

    def _redo(self, e=None):
        try:
            self.t.edit_redo()
        except tk.TclError:
            pass
        return "break"

    def select_all(self, e=None):
        self.t.tag_add("sel", "1.0", "end-1c")
        self.t.mark_set("insert", "end-1c")
        return "break"

    def _begin(self):
        self.t.configure(autoseparators=False)
        self.t.edit_separator()

    def _end(self):
        self.t.edit_separator()
        self.t.configure(autoseparators=True)

    # -- API
    def get(self) -> str:
        return self.t.get("1.0", "end-1c")

    def set(self, text: str, keep_undo: bool = True):
        """Remplace tout le contenu (annulable par Ctrl+Z si keep_undo)."""
        y = self.t.yview()[0]
        ins = self.t.index("insert")
        self._begin()
        self.t.delete("1.0", "end")
        self.t.insert("1.0", text)
        self._end()
        if not keep_undo:
            self.t.edit_reset()
        try:
            self.t.mark_set("insert", ins)
            self.t.yview_moveto(y)
        except tk.TclError:
            pass
        self.highlight_all()

    def selection(self) -> Tuple[str, str, str]:
        t = self.t
        if t.tag_ranges("sel"):
            a, b = t.index("sel.first"), t.index("sel.last")
            return t.get(a, b), a, b
        return "", "", ""

    def dirty(self) -> bool:
        return self.get() != self.saved_text

    def goto(self, line: int, col: int = 0):
        self.t.mark_set("insert", f"{line}.{col}")
        self.t.see("insert")
        self.t.focus_set()
        self._cursor_moved()

    def mark_error(self, line: int):
        self.t.tag_remove("errline", "1.0", "end")
        if line > 0:
            self.t.tag_add("errline", f"{line}.0", f"{line}.0+1line")
            self.goto(line)

    def stats(self) -> Dict[str, int]:
        s = self.get()
        lines = s.split("\n")
        code = [l for l in lines if l.strip()]
        pre = COMMENT.get(self.lang, ("#", ""))[0].strip() or "\x00"
        return {"lines": len(lines), "chars": len(s), "code": len(code),
                "comments": sum(1 for l in code if l.lstrip().startswith(pre)),
                "funcs": len(re.findall(r"(?m)^\s*(?:def |function |(?:void|int|bool|float|String)\s+\w+\s*\()", s)),
                "todo": len(re.findall(r"(?i)\b(?:TODO|FIXME|XXX)\b", s))}


# ───────────────────────────────────── aperçu web local (rechargement auto) ──

_LIVE_JS = ("<script>/* Padawan Atelier : rechargement auto (aperçu seulement, pas dans ton fichier) */"
            "(function(){var t=null;setInterval(function(){fetch('/__padawan_mtime',{cache:'no-store'})"
            ".then(function(r){return r.text()}).then(function(v){if(t===null)t=v;else if(v!==t)location.reload()})"
            ".catch(function(){})},800)})();</script>")


class PreviewServer:
    """Petit serveur http 127.0.0.1 (jamais exposé au réseau) qui sert le dossier du projet."""

    def __init__(self):
        self.root = ""
        self.httpd = None
        self.port = 0

    def _mtime(self) -> str:
        best, n = 0.0, 0
        for dp, dn, fn in os.walk(self.root):
            dn[:] = [d for d in dn if not d.startswith(".")]
            for f in fn:
                n += 1
                if n > 800:
                    break
                try:
                    best = max(best, os.path.getmtime(os.path.join(dp, f)))
                except OSError:
                    pass
        return f"{best:.3f}"

    def start(self, root: str) -> int:
        self.root = root
        if self.httpd:
            return self.port
        srv = self

        class H(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *a, **k):
                super().__init__(*a, directory=srv.root, **k)

            def log_message(self, *a):
                pass

            def end_headers(self):
                self.send_header("Cache-Control", "no-store")
                super().end_headers()

            def do_GET(self):
                if self.path.startswith("/__padawan_mtime"):
                    b = srv._mtime().encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain")
                    self.send_header("Content-Length", str(len(b)))
                    self.end_headers()
                    self.wfile.write(b)
                    return
                p = self.translate_path(self.path.split("?", 1)[0])
                if os.path.isdir(p):
                    for ix in ("index.html", "index.htm"):
                        if os.path.isfile(os.path.join(p, ix)):
                            p = os.path.join(p, ix)
                            break
                if p.lower().endswith((".html", ".htm")) and os.path.isfile(p):
                    try:
                        html = read_text(p)
                        low = html.lower()
                        k = low.rfind("</body>")
                        html = html[:k] + _LIVE_JS + html[k:] if k >= 0 else html + _LIVE_JS
                        b = html.encode("utf-8")
                        self.send_response(200)
                        self.send_header("Content-Type", "text/html; charset=utf-8")
                        self.send_header("Content-Length", str(len(b)))
                        self.end_headers()
                        self.wfile.write(b)
                        return
                    except Exception:
                        pass
                return super().do_GET()

        class S(socketserver.ThreadingMixIn, http.server.HTTPServer):
            daemon_threads = True
            allow_reuse_address = True

        self.httpd = S(("127.0.0.1", 0), H)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        return self.port

    def url(self, rel: str) -> str:
        from urllib.parse import quote
        return f"http://127.0.0.1:{self.port}/" + quote(rel.replace("\\", "/"))

    def stop(self):
        if self.httpd:
            try:
                self.httpd.shutdown()
                self.httpd.server_close()
            except Exception:
                pass
            self.httpd = None


# ────────────────────────────────────────────────── exécution de programmes ──

class Runner:
    """Lance un programme, renvoie sa sortie par morceaux (même sans fin de ligne), accepte une saisie."""

    def __init__(self, on_out: Callable[[str, str], None], on_exit: Callable[[int, float], None]):
        self.on_out, self.on_exit = on_out, on_exit
        self.p: Optional[subprocess.Popen] = None
        self.t0 = 0.0
        self.last = 0.0
        self.killed = ""

    def running(self) -> bool:
        return bool(self.p and self.p.poll() is None)

    def start(self, cmd: List[str], cwd: str, timeout: int = 60):
        self.stop()
        self.killed = ""
        self.t0 = self.last = time.time()
        self.p = subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, env=clean_env(), creationflags=NOWIN, bufsize=0)
        p = self.p
        for stream, name in ((p.stdout, "out"), (p.stderr, "err")):
            threading.Thread(target=self._pump, args=(p, stream, name), daemon=True).start()
        threading.Thread(target=self._watch, args=(p, timeout), daemon=True).start()

    def _pump(self, p, stream, name):
        import codecs
        dec = codecs.getincrementaldecoder("utf-8")("replace")
        fd = stream.fileno()
        while True:
            try:
                b = os.read(fd, 4096)
            except OSError:
                break
            if not b:
                break
            self.last = time.time()
            s = dec.decode(b)
            if s:
                self.on_out(s.replace("\r\n", "\n"), name)
        tail = dec.decode(b"", final=True)
        if tail:
            self.on_out(tail, name)

    def _watch(self, p, timeout):
        while p.poll() is None:
            time.sleep(0.2)
            if timeout and time.time() - self.last > timeout:
                self.killed = f"arrêté : rien ne s'est passé pendant {timeout} s (réglable dans ⚙)"
                self._kill(p)
        time.sleep(0.15)  # laisse finir les lectures
        self.on_exit(p.returncode if p.returncode is not None else -1, time.time() - self.t0)

    def write(self, s: str):
        if self.running():
            try:
                self.last = time.time()
                self.p.stdin.write(s.encode("utf-8"))
                self.p.stdin.flush()
            except Exception:
                pass

    def _kill(self, p):
        try:
            if IS_WIN:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True,
                               creationflags=NOWIN, timeout=10)
            else:
                p.kill()
        except Exception:
            try:
                p.kill()
            except Exception:
                pass

    def stop(self, why: str = ""):
        if self.running():
            self.killed = why or "arrêté (⏹ Stop)"
            self._kill(self.p)


# ──────────────────────────────────────────────────────────── déploiement ──

def plan_files(files: List[Tuple[str, str]], dest_dir: str) -> List[Dict[str, Any]]:
    out = []
    for name, text in files:
        path = os.path.join(dest_dir, name)
        st, old = "nouveau", ""
        if os.path.isfile(path):
            try:
                old = read_text(path)
            except Exception:
                old = ""
            st = "identique" if old == text else "modifié"
        out.append({"name": name, "path": path, "state": st, "old": old, "new": text})
    return out


def backup_file(path: str, bak_root: str, label: str) -> str:
    """Copie .bak horodatée : <bak_root>/<AAAAMMJJ>/<label>/<nom>.<heure>.bak"""
    if not os.path.isfile(path):
        return ""
    d = os.path.join(bak_root, datetime.now().strftime("%Y%m%d"), slugify(label))
    os.makedirs(d, exist_ok=True)
    dst = os.path.join(d, f"{os.path.basename(path)}.{datetime.now():%H%M%S}.bak")
    shutil.copy2(path, dst)
    return dst


def backup_bytes(data: bytes, name: str, bak_root: str, label: str) -> str:
    d = os.path.join(bak_root, datetime.now().strftime("%Y%m%d"), slugify(label))
    os.makedirs(d, exist_ok=True)
    dst = os.path.join(d, f"{os.path.basename(name)}.{datetime.now():%H%M%S}.bak")
    with open(dst, "wb") as f:
        f.write(data)
    return dst


class NewHostKey(Exception):
    def __init__(self, host, keytype, fp, key):
        super().__init__(f"clé inconnue {keytype} {fp}")
        self.host, self.keytype, self.fp, self.key = host, keytype, fp, key


class Remote:
    """FTP / FTPS (TLS explicite) / SFTP. Rien n'est écrit par test()."""

    def __init__(self, cfg: Dict[str, Any], password: str, known_hosts: str = ""):
        self.cfg, self.pw, self.known = cfg, password, known_hosts
        self.proto = (cfg.get("proto") or "sftp").lower()
        self.c = None
        self.sftp = None

    def connect(self, timeout: int = 15):
        host = (self.cfg.get("host") or "").strip()
        user = (self.cfg.get("user") or "").strip()
        port = int(self.cfg.get("port") or 0)
        if not host:
            raise ValueError("hôte vide (⚙ Réglages)")
        if self.proto in ("ftp", "ftps"):
            import ftplib
            f = ftplib.FTP_TLS(timeout=timeout) if self.proto == "ftps" else ftplib.FTP(timeout=timeout)
            f.connect(host, port or 21)
            f.login(user or "anonymous", self.pw or "")
            if self.proto == "ftps":
                f.prot_p()
            f.encoding = "utf-8"
            self.c = f
        else:
            import paramiko
            cl = paramiko.SSHClient()
            if self.known and os.path.isfile(self.known):
                cl.load_host_keys(self.known)
            outer = self

            class Tofu(paramiko.MissingHostKeyPolicy):
                def missing_host_key(self, client, hostname, key):
                    import hashlib
                    fp = "SHA256:" + base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip("=")
                    if outer.cfg.get("_trust_fp") == fp:
                        client.get_host_keys().add(hostname, key.get_name(), key)
                        if outer.known:
                            os.makedirs(os.path.dirname(outer.known), exist_ok=True)
                            client.save_host_keys(outer.known)
                        return
                    raise NewHostKey(hostname, key.get_name(), fp, key)
            cl.set_missing_host_key_policy(Tofu())
            cl.connect(host, port=port or 22, username=user, password=self.pw or None, timeout=timeout,
                       allow_agent=False, look_for_keys=False)
            self.c = cl
            self.sftp = cl.open_sftp()
        return self

    def _p(self, rel: str) -> str:
        base = (self.cfg.get("dir") or "/").replace("\\", "/")
        return (base.rstrip("/") + "/" + rel.lstrip("/")) if rel else base

    def listdir(self, rel: str = "") -> List[str]:
        if self.sftp:
            return sorted(self.sftp.listdir(self._p(rel)))
        return sorted(os.path.basename(x) for x in self.c.nlst(self._p(rel)))

    def get(self, rel: str) -> Optional[bytes]:
        p = self._p(rel)
        try:
            if self.sftp:
                with self.sftp.open(p, "rb") as f:
                    return f.read()
            chunks: List[bytes] = []
            self.c.retrbinary("RETR " + p, chunks.append)
            return b"".join(chunks)
        except Exception:
            return None

    def mkdirs(self, rel_dir: str):
        if not rel_dir:
            return
        cur = ""
        for part in rel_dir.replace("\\", "/").strip("/").split("/"):
            cur = cur + "/" + part if cur else part
            p = self._p(cur)
            try:
                if self.sftp:
                    try:
                        self.sftp.stat(p)
                    except IOError:
                        self.sftp.mkdir(p)
                else:
                    try:
                        self.c.mkd(p)
                    except Exception:
                        pass
            except Exception:
                pass

    def put(self, rel: str, data: bytes):
        import io
        p = self._p(rel)
        if self.sftp:
            with self.sftp.open(p, "wb") as f:
                f.write(data)
        else:
            self.c.storbinary("STOR " + p, io.BytesIO(data))

    def close(self):
        try:
            if self.sftp:
                self.sftp.close()
            if self.c:
                (self.c.quit if self.proto in ("ftp", "ftps") else self.c.close)()
        except Exception:
            pass

    def test(self) -> str:
        try:
            self.connect()
            names = self.listdir()
            return f"✅ Connexion OK ({self.proto.upper()}) · {len(names)} élément(s) dans {self._p('')}"
        finally:
            self.close()


# ─────────────────────────────────────────────── consignes, modèles de départ ──

SYSTEM_PROG = (
    "Tu es Padawan-Atelier, un programmeur senior qui code pour Marc (Québec). TUTOIE TOUJOURS Marc "
    "(« tu », « ton fichier », jamais « vous » ni « votre »), français québécois naturel, zéro flatterie, zéro sermon.\n"
    "RÈGLES DE SORTIE (obligatoires) :\n"
    "1. Quand on te demande du code, donne TOUJOURS le FICHIER COMPLET, prêt à exécuter, dans un bloc "
    "markdown avec le langage ET le nom du fichier sur la ligne d'ouverture, ex. ```python menu.py ou "
    "```html index.html. Jamais de « ... », jamais de « reste du code inchangé », jamais de morceaux à recoller.\n"
    "2. Plusieurs fichiers = plusieurs blocs, un par fichier, chacun avec son nom.\n"
    "3. Pas de blabla avant le code. APRÈS le code : au plus 5 puces brèves (comment lancer, quoi ajuster).\n"
    "4. Environnement de Marc : Windows 11, Python 3.14 (bibliothèque standard d'abord), chemins Windows, "
    "XAMPP local (Apache + PHP 8 + MySQL sur localhost), IDE Arduino. Console Windows : codes ANSI OK "
    "(appelle os.system('') au début pour les activer).\n"
    "5. Commentaires dans le code en français, noms de variables clairs, gestion d'erreurs raisonnable.\n"
    "6. Si la demande est floue, fais un choix sensé et dis-le en une ligne à la fin.\n"
    "7. Si on te montre un fichier et qu'on te demande une modification, renvoie le fichier COMPLET modifié "
    "avec le MÊME nom de fichier.\n"
)

SYSTEM_PATCH = (
    "Tu modifies le VRAI fichier de Marc. Réponds UNIQUEMENT avec un ou plusieurs blocs de remplacement, "
    "exactement dans ce format :\n"
    "<<<<<<< SEARCH\n(texte copié EXACTEMENT du fichier, caractère pour caractère, assez pour être unique)\n"
    "=======\n(le même texte, modifié)\n>>>>>>> REPLACE\n"
    "Règles : change SEULEMENT ce qui est demandé ; tout le reste reste identique. Jamais d'exemple générique, "
    "jamais de nouveau fichier, jamais de « ... ». Les couleurs se nomment librement : « bleu » peut être "
    "un bleu ou un violet/mauve (#6C5EB5, #352879, navy…) — repère les vraies valeurs dans le fichier. "
    "Après les blocs : une seule ligne en français qui dit ce que tu as changé."
)

EDIT_VERB_RX = re.compile(
    r"(?i)\b(change[zrs]?|chang[eé]|modifie[zrs]?|modifi[eé]|remplace[zrs]?|ajoute[zrs]?|enl[eè]ve[zrs]?|retire[zrs]?|"
    r"supprime[zrs]?|corrige[zrs]?|mets|met|mettre|rends|agrandis|r[eé]duis|renomme|traduis|centre|colore|"
    r"passe[zr]?|transforme|am[eé]liore|fix|change|replace|add|remove|make)\b")
EDIT_REF_RX = re.compile(r"(?i)\b(fichier|page|code|site|script|fond|background|couleur|texte|titre|bouton|menu|police|"
                         r"css|html|style|ligne|fonction|section|image|lien|couleurs?|bordure|marge)\b")
SHOW_RX = re.compile(r"(?i)\b(montre|affiche|r[eé]sultat|aper[cç]u|voir|preview)")


def is_edit_request(q: str, tab_name: str = "") -> bool:
    """v41.4 : « change le fond… », « ajoute un bouton… » sur le fichier ouvert (pas une question générale)."""
    t = (q or "").strip()
    if not t or len(t) > 1500 or re.match(r"(?i)^(comment|pourquoi|c'est quoi|qu'est|explique|est-ce)", t):
        return False
    if not EDIT_VERB_RX.search(t):
        return False
    base = os.path.splitext(tab_name or "")[0].lower()
    return bool(EDIT_REF_RX.search(t) or (base and base in t.lower()))


PATCH_RX = re.compile(r"<{5,9} ?SEARCH[^\n]*\n(.*?)\n?={5,9}[^\n]*\n(.*?)\n?>{5,9} ?REPLACE", re.S)


def parse_patches(text: str) -> List[Tuple[str, str]]:
    return [(a, b) for a, b in PATCH_RX.findall(text or "") if a.strip()]


def apply_patches(src: str, patches: List[Tuple[str, str]]) -> Tuple[str, int, int]:
    """Applique SEARCH/REPLACE : correspondance exacte, puis tolérante aux espaces. → (texte, réussis, ratés)."""
    ok = bad = 0
    for a, b in patches:
        if a in src:
            src = src.replace(a, b, 1)
            ok += 1
            continue
        a2 = a.strip()
        if a2 and a2 in src:
            src = src.replace(a2, b.strip(), 1)
            ok += 1
            continue
        toks = a2.split()
        m = re.search(r"\s*".join(re.escape(x) for x in toks), src) if toks else None
        if m:
            src = src[:m.start()] + b.strip() + src[m.end():]
            ok += 1
        else:
            bad += 1
    return src, ok, bad


SYSTEM_LINES = (
    "Tu es un outil d'édition de fichiers. Tu ne parles pas, tu n'expliques pas, tu ne donnes jamais d'exemple. "
    "On te donne un fichier avec ses lignes numérotées et une demande. Tu réponds UNIQUEMENT par les lignes "
    "modifiées, une par ligne, au format exact :\nL<numéro>: <nouveau contenu COMPLET de la ligne>\n"
    "Pour ajouter une ligne après la ligne N : L<N>+: <contenu>. Pour supprimer la ligne N : L<N>-\n"
    "Copie le reste de chaque ligne à l'identique, ne change que ce qui est demandé. "
    "Les couleurs : « bleu » peut être un bleu ou un violet/mauve (#6C5EB5, #352879, navy…) ; « rouge » = un rouge "
    "(#B22222, #8B0000, #ff0000…). Rien d'autre dans ta réponse."
)
LINE_EDIT_RX = re.compile(r"^\s*[`>*-]*\s*L(\d{1,5})\s*([+-]?)\s*[:|]?\s?(.*)$")


def number_lines(src: str) -> str:
    return "\n".join(f"L{i}: {ln}" for i, ln in enumerate(src.split("\n"), 1))


def parse_line_edits(text: str) -> List[Tuple[int, str, str]]:
    out = []
    for raw in (text or "").splitlines():
        m = LINE_EDIT_RX.match(raw)
        if m:
            out.append((int(m.group(1)), m.group(2), m.group(3).rstrip()))
    return out


def apply_line_edits(src: str, edits: List[Tuple[int, str, str]]) -> Tuple[str, int]:
    lines = src.split("\n")
    rep_, add, dele = {}, {}, set()
    for n, op, txt in edits:
        if not 1 <= n <= len(lines):
            continue
        if op == "+":
            add.setdefault(n, []).append(txt)
        elif op == "-":
            dele.add(n)
        elif txt.strip() or lines[n - 1].strip() == "":
            # v41.4 : un 7B se trompe parfois de numéro → on recale sur la ligne d'origine la plus ressemblante
            r0 = difflib.SequenceMatcher(None, lines[n - 1], txt).ratio() if lines[n - 1].strip() else 1.0
            if r0 < 0.55:
                best, br = 0, 0.0
                for j, ln in enumerate(lines, 1):
                    if j in rep_ or not ln.strip():
                        continue
                    r = difflib.SequenceMatcher(None, ln, txt).ratio()
                    if r > br:
                        best, br = j, r
                if br < 0.6:
                    continue
                n = best
            rep_[n] = txt
    out, k = [], 0
    for i, ln in enumerate(lines, 1):
        if i in dele:
            k += 1
        else:
            new = rep_.get(i, ln)
            if new != ln:
                # garde l'indentation d'origine si le modèle l'a perdue
                ind = ln[:len(ln) - len(ln.lstrip())]
                if ind and not new[:1].isspace():
                    new = ind + new
                k += 1
            out.append(new)
        for x in add.get(i, []):
            out.append(x)
            k += 1
    return "\n".join(out), k


def looks_fragment(old: str, new: str) -> str:
    """Raison (texte) si « new » n'est qu'un morceau qui écraserait « old », sinon ''."""
    lo, ln = len(old.splitlines()), len(new.splitlines())
    if lo >= 8 and ln < lo * 0.6:
        return f"il ne garde que {ln} lignes sur {lo}"
    low_o, low_n = old.lower(), new.lower()
    for tag in ("<html", "<body", "<?php", "<!doctype", "def ", "void setup"):
        if tag in low_o and tag not in low_n:
            return f"il n'a plus « {tag.strip()} »"
    return ""


def _hue_name(hx: str) -> str:
    import colorsys
    h = hx.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except ValueError:
        return ""
    hh, ll, ss = colorsys.rgb_to_hls(r, g, b)
    if ss < 0.15:
        return "noir" if ll < 0.15 else "blanc" if ll > 0.85 else "gris"
    d = hh * 360
    name = ("rouge" if d < 15 or d >= 345 else "orange" if d < 45 else "jaune" if d < 70 else "vert" if d < 165 else
            "cyan" if d < 195 else "bleu" if d < 240 else "bleu-violet (mauve)" if d < 280 else "violet" if d < 320 else "rose")
    return name + (" foncé" if ll < 0.35 else " clair" if ll > 0.7 else "")


def color_hints(src: str) -> str:
    """« #6C5EB5 = bleu-violet » pour les couleurs de fond : le modèle sait lesquelles sont « bleues »."""
    seen = []
    for m in re.finditer(r"(?i)background(?:-color)?\s*:[^;}]*", src):
        for hx in re.findall(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b", m.group(0)):
            if hx.upper() not in [x.upper() for x in seen]:
                seen.append(hx)
    return ", ".join(f"{h} = {_hue_name(h)}" for h in seen[:12])


def key_lines(src: str, q: str, limit: int = 14) -> str:
    """Lignes du fichier liées à la demande (couleurs / fond…) pour que le modèle copie les vraies valeurs."""
    words = ["background"] if re.search(r"(?i)fond|background|couleur|color", q) else []
    words += [w.lower() for w in re.findall(r"[A-Za-zÀ-ÿ#_-]{4,}", q)]
    out = []
    for i, ln in enumerate(src.splitlines(), 1):
        l2 = ln.lower()
        if any(w in l2 for w in words if w not in ("change", "fichier", "page", "montre", "resultat", "résultat")):
            out.append(f"ligne {i}: {ln.strip()[:220]}")
        if len(out) >= limit:
            break
    return "\n".join(out)


TEMPLATES: Dict[str, Dict[str, Any]] = {}

TEMPLATES["dos_menu"] = {
    "title": "🟦 Menu ASCII couleur style DOS (Python)",
    "files": {"menu_dos.py": r'''# -*- coding: utf-8 -*-
"""Menu ASCII en couleur, style DOS / BBS des années 90.
Lance-le dans une vraie console (bouton 🖥 Console de l'Atelier) pour les couleurs et les flèches."""
import os
import sys
import time
from datetime import datetime

os.system("")  # active les codes couleur ANSI dans la console Windows

ESC = "\x1b["
RESET = ESC + "0m"
BLEU, CYAN, JAUNE, BLANC, ROUGE, VERT, GRIS = (ESC + c for c in
    ("44;97m", "96m", "93;1m", "97;1m", "91;1m", "92;1m", "90m"))

LARGEUR = 60
OPTIONS = [
    ("1", "Afficher la date et l'heure"),
    ("2", "Petit calcul (addition)"),
    ("3", "Animation : barre de progression"),
    ("4", "Infos système"),
    ("Q", "Quitter"),
]


def effacer():
    print(ESC + "2J" + ESC + "H", end="")


def cadre(titre, lignes):
    """Dessine un cadre double en caractères DOS (╔═╗)."""
    print(BLEU + "╔" + "═" * (LARGEUR - 2) + "╗" + RESET)
    print(BLEU + "║" + JAUNE + "\x1b[44m" + titre.center(LARGEUR - 2) + BLEU + "║" + RESET)
    print(BLEU + "╠" + "═" * (LARGEUR - 2) + "╣" + RESET)
    for texte in lignes:
        print(BLEU + "║ " + texte.ljust(LARGEUR - 4) + " ║" + RESET)
    print(BLEU + "╚" + "═" * (LARGEUR - 2) + "╝" + RESET)


def menu():
    effacer()
    lignes = [""] + [f"  [{k}]  {libelle}" for k, libelle in OPTIONS] + [""]
    cadre("■ MENU PRINCIPAL ■", lignes)
    print(GRIS + "  " + datetime.now().strftime("%Y-%m-%d %H:%M") + "  ·  Padawan Atelier" + RESET)
    return input(CYAN + "\n  Ton choix ► " + RESET).strip().upper()


def pause():
    input(GRIS + "\n  (Entrée pour revenir au menu)" + RESET)


def action(choix):
    if choix == "1":
        print(VERT + "\n  Nous sommes le " + datetime.now().strftime("%A %d %B %Y, %H:%M:%S") + RESET)
    elif choix == "2":
        try:
            a = float(input("  Premier nombre : "))
            b = float(input("  Deuxième nombre : "))
            print(VERT + f"\n  {a:g} + {b:g} = {a + b:g}" + RESET)
        except ValueError:
            print(ROUGE + "\n  Ce n'est pas un nombre." + RESET)
    elif choix == "3":
        for i in range(31):
            barre = "█" * i + "░" * (30 - i)
            print(f"\r  {CYAN}[{barre}]{RESET} {i * 100 // 30:3d} %", end="", flush=True)
            time.sleep(0.04)
        print()
    elif choix == "4":
        print(VERT + f"\n  Python {sys.version.split()[0]} · {sys.platform} · dossier : {os.getcwd()}" + RESET)
    else:
        print(ROUGE + "\n  Choix inconnu." + RESET)
    pause()


def main():
    while True:
        choix = menu()
        if choix in ("Q", "QUITTER"):
            print(JAUNE + "\n  À la prochaine !" + RESET)
            break
        action(choix)


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print(RESET)
'''},
}

TEMPLATES["web_retro"] = {
    "title": "🌐 Page web rétro (HTML + CSS)",
    "files": {"index.html": '''<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Ma page rétro</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <div class="ecran">
    <h1>▓▒░ BIENVENUE ░▒▓</h1>
    <p class="clignote">&gt; Connexion établie à 2400 bauds_</p>
    <ul class="menu">
      <li><a href="#">[1] Nouvelles</a></li>
      <li><a href="#">[2] Fichiers</a></li>
      <li><a href="#">[3] Livre d'or</a></li>
    </ul>
    <p class="pied">Visiteur n° <span id="compteur">000042</span> · fait avec Padawan</p>
  </div>
  <script>
    // petit compteur rétro qui avance tout seul
    let n = 42;
    setInterval(() => {
      n += 1;
      document.getElementById("compteur").textContent = String(n).padStart(6, "0");
    }, 1500);
  </script>
</body>
</html>
''', "style.css": '''/* Style rétro : écran cathodique vert */
body {
  margin: 0;
  min-height: 100vh;
  display: grid;
  place-items: center;
  background: #020802;
  font-family: "Courier New", monospace;
}
.ecran {
  width: min(720px, 92vw);
  padding: 32px;
  border: 3px double #33ff66;
  color: #33ff66;
  background: #031a07;
  box-shadow: 0 0 24px #33ff6655, inset 0 0 40px #000;
  text-shadow: 0 0 6px #33ff66;
}
h1 { margin-top: 0; letter-spacing: 3px; }
.menu { list-style: none; padding: 0; }
.menu a { color: #ffff66; text-decoration: none; }
.menu a:hover { background: #33ff66; color: #031a07; }
.clignote { animation: clignote 1s steps(2) infinite; }
@keyframes clignote { 50% { opacity: 0.2; } }
.pied { font-size: 13px; opacity: 0.7; }
'''},
}

TEMPLATES["py_script"] = {
    "title": "🐍 Script Python (propre, avec arguments)",
    "files": {"script.py": '''# -*- coding: utf-8 -*-
"""Script Python de départ : arguments, journal, gestion d'erreurs."""
import argparse
import logging
import sys
from pathlib import Path

log = logging.getLogger("script")


def traiter(dossier: Path) -> int:
    """Exemple : compte les fichiers .py d'un dossier."""
    fichiers = sorted(dossier.glob("*.py"))
    for f in fichiers:
        log.info("trouvé : %s (%d octets)", f.name, f.stat().st_size)
    return len(fichiers)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Script de départ Padawan")
    p.add_argument("dossier", nargs="?", default=".", help="dossier à examiner")
    p.add_argument("-v", "--verbeux", action="store_true", help="plus de détails")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbeux else logging.INFO,
                        format="%(levelname)s · %(message)s")
    dossier = Path(args.dossier)
    if not dossier.is_dir():
        log.error("dossier introuvable : %s", dossier)
        return 1
    n = traiter(dossier)
    print(f"{n} fichier(s) Python dans {dossier.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''},
}

TEMPLATES["arduino"] = {
    "title": "🔌 Sketch Arduino (LED + bouton + Série)",
    "files": {"sketch.ino": '''// Sketch de départ : la LED clignote, le bouton (broche 2) change la vitesse.
const int LED = LED_BUILTIN;
const int BOUTON = 2;          // bouton entre la broche 2 et GND
unsigned long dernier = 0;
int intervalle = 500;          // ms
bool etat = false;

void setup() {
  pinMode(LED, OUTPUT);
  pinMode(BOUTON, INPUT_PULLUP);
  Serial.begin(9600);
  Serial.println("Padawan : sketch démarré");
}

void loop() {
  // bouton appuyé = LOW (pull-up interne)
  if (digitalRead(BOUTON) == LOW) {
    intervalle = (intervalle == 500) ? 100 : 500;
    Serial.print("Nouvel intervalle : ");
    Serial.println(intervalle);
    delay(250);                // anti-rebond simple
  }
  if (millis() - dernier >= (unsigned long)intervalle) {
    dernier = millis();
    etat = !etat;
    digitalWrite(LED, etat ? HIGH : LOW);
  }
}
'''},
}

TEMPLATES["php_mysql"] = {
    "title": "🐘 Page PHP + MySQL (XAMPP, PDO)",
    "files": {"index.php": '''<?php
// Page PHP + MySQL de départ (XAMPP : utilisateur root, mot de passe vide par défaut).
// Crée la base « padawan_demo » et une table « notes » au premier lancement.
$hote = "127.0.0.1";
$base = "padawan_demo";
$util = "root";
$mdp  = "";

$erreur = "";
$notes = [];
try {
    $pdo = new PDO("mysql:host=$hote;charset=utf8mb4", $util, $mdp,
                   [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]);
    $pdo->exec("CREATE DATABASE IF NOT EXISTS `$base` CHARACTER SET utf8mb4");
    $pdo->exec("USE `$base`");
    $pdo->exec("CREATE TABLE IF NOT EXISTS notes (
        id INT AUTO_INCREMENT PRIMARY KEY,
        texte VARCHAR(255) NOT NULL,
        cree TIMESTAMP DEFAULT CURRENT_TIMESTAMP)");
    if ($_SERVER["REQUEST_METHOD"] === "POST" && trim($_POST["texte"] ?? "") !== "") {
        $st = $pdo->prepare("INSERT INTO notes (texte) VALUES (?)");
        $st->execute([trim($_POST["texte"])]);
        header("Location: " . $_SERVER["PHP_SELF"]);
        exit;
    }
    $notes = $pdo->query("SELECT * FROM notes ORDER BY id DESC LIMIT 20")->fetchAll(PDO::FETCH_ASSOC);
} catch (PDOException $e) {
    $erreur = $e->getMessage();
}
?>
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <title>Notes PHP + MySQL</title>
  <style>
    body { font-family: Segoe UI, sans-serif; background: #10141c; color: #eee; max-width: 640px; margin: 40px auto; }
    input[type=text] { width: 70%; padding: 8px; } button { padding: 8px 14px; }
    li { padding: 4px 0; border-bottom: 1px solid #333; } .err { color: #f77; }
  </style>
</head>
<body>
  <h1>📝 Mes notes</h1>
  <?php if ($erreur): ?><p class="err">MySQL : <?= htmlspecialchars($erreur) ?></p><?php endif; ?>
  <form method="post">
    <input type="text" name="texte" placeholder="Nouvelle note…" autofocus>
    <button>Ajouter</button>
  </form>
  <ul>
    <?php foreach ($notes as $n): ?>
      <li><?= htmlspecialchars($n["texte"]) ?> <small>(<?= $n["cree"] ?>)</small></li>
    <?php endforeach; ?>
  </ul>
</body>
</html>
'''},
}

TEMPLATE_ORDER = ["web_retro", "py_script", "arduino", "php_mysql", "dos_menu"]

SNIPPETS: Dict[str, List[Tuple[str, str]]] = {
    "python": [
        ("if __name__ == '__main__'", 'def main():\n    pass\n\n\nif __name__ == "__main__":\n    main()\n'),
        ("Lire un fichier texte", 'with open("fichier.txt", "r", encoding="utf-8") as f:\n    contenu = f.read()\n'),
        ("Écrire un JSON", 'import json\n\nwith open("donnees.json", "w", encoding="utf-8") as f:\n    json.dump(donnees, f, ensure_ascii=False, indent=2)\n'),
        ("Boucle sur les fichiers d'un dossier", 'from pathlib import Path\n\nfor f in Path(".").glob("*.txt"):\n    print(f.name)\n'),
        ("try / except", 'try:\n    pass\nexcept Exception as e:\n    print(f"Erreur : {e}")\n'),
        ("Fenêtre Tkinter", 'import tkinter as tk\n\nroot = tk.Tk()\nroot.title("Ma fenêtre")\ntk.Label(root, text="Bonjour !", font=("Segoe UI", 14)).pack(padx=20, pady=20)\ntk.Button(root, text="Quitter", command=root.destroy).pack(pady=(0, 20))\nroot.mainloop()\n'),
        ("Requête web (urllib)", 'from urllib.request import urlopen\n\nwith urlopen("https://example.com", timeout=10) as r:\n    html = r.read().decode("utf-8", "replace")\nprint(html[:200])\n'),
        ("Couleurs ANSI console", 'import os\nos.system("")\nprint("\\x1b[93;1mJaune\\x1b[0m \\x1b[96mCyan\\x1b[0m")\n'),
        ("Classe avec dataclass", 'from dataclasses import dataclass\n\n\n@dataclass\nclass Item:\n    nom: str\n    prix: float = 0.0\n'),
    ],
    "html": [
        ("Squelette HTML5", '<!DOCTYPE html>\n<html lang="fr">\n<head>\n  <meta charset="utf-8">\n  <meta name="viewport" content="width=device-width, initial-scale=1">\n  <title>Titre</title>\n</head>\n<body>\n\n</body>\n</html>\n'),
        ("Lien CSS + JS", '<link rel="stylesheet" href="style.css">\n<script src="app.js" defer></script>\n'),
        ("Formulaire", '<form method="post" action="">\n  <label>Nom <input type="text" name="nom" required></label>\n  <button type="submit">Envoyer</button>\n</form>\n'),
        ("Tableau", '<table>\n  <thead><tr><th>Col 1</th><th>Col 2</th></tr></thead>\n  <tbody><tr><td>A</td><td>B</td></tr></tbody>\n</table>\n'),
        ("Image", '<img src="image.png" alt="description" width="320">\n'),
    ],
    "css": [
        ("Centrer (grid)", '.centre {\n  display: grid;\n  place-items: center;\n  min-height: 100vh;\n}\n'),
        ("Flex en rangée", '.rangee {\n  display: flex;\n  gap: 12px;\n  align-items: center;\n}\n'),
        ("Bouton rétro", '.bouton {\n  background: #0000aa;\n  color: #ffff55;\n  border: 2px outset #5555ff;\n  font-family: "Courier New", monospace;\n  padding: 6px 14px;\n}\n'),
        ("Media query mobile", '@media (max-width: 600px) {\n  body { font-size: 15px; }\n}\n'),
    ],
    "js": [
        ("Au chargement", 'document.addEventListener("DOMContentLoaded", () => {\n\n});\n'),
        ("Clic sur un bouton", 'document.querySelector("#bouton").addEventListener("click", () => {\n  alert("Clic !");\n});\n'),
        ("fetch JSON", 'fetch("donnees.json")\n  .then(r => r.json())\n  .then(data => console.log(data))\n  .catch(err => console.error(err));\n'),
    ],
    "php": [
        ("Connexion PDO MySQL", '$pdo = new PDO("mysql:host=127.0.0.1;dbname=ma_base;charset=utf8mb4", "root", "",\n               [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]);\n'),
        ("Requête préparée", '$st = $pdo->prepare("SELECT * FROM table WHERE id = ?");\n$st->execute([$id]);\n$ligne = $st->fetch(PDO::FETCH_ASSOC);\n'),
        ("Échapper du HTML", '<?= htmlspecialchars($texte, ENT_QUOTES, "UTF-8") ?>'),
        ("Formulaire POST", 'if ($_SERVER["REQUEST_METHOD"] === "POST") {\n    $nom = trim($_POST["nom"] ?? "");\n}\n'),
    ],
    "arduino": [
        ("setup / loop", 'void setup() {\n  Serial.begin(9600);\n}\n\nvoid loop() {\n\n}\n'),
        ("Clignoter sans delay", 'unsigned long avant = 0;\nif (millis() - avant >= 500) {\n  avant = millis();\n  digitalWrite(LED_BUILTIN, !digitalRead(LED_BUILTIN));\n}\n'),
        ("Lire un potentiomètre", 'int valeur = analogRead(A0);\nSerial.println(valeur);\n'),
        ("Servo", '#include <Servo.h>\nServo monServo;\n// setup : monServo.attach(9);\n// loop  : monServo.write(90);\n'),
    ],
}

QUICK_ACTIONS = [
    ("💬 Expliquer", "explain", "Explique clairement ce code (ce qu'il fait, étape par étape, pièges éventuels). "
                                "Ne renvoie PAS de code sauf si c'est indispensable."),
    ("📝 Commenter", "edit", "Ajoute des commentaires utiles en français à ce code, sans changer son comportement."),
    ("⚡ Optimiser", "edit", "Optimise ce code (lisibilité, performance, robustesse) sans changer ce qu'il fait."),
    ("🧪 Tests", "tests", "Écris des tests pour ce code (Python : unittest, fichier test_<nom>.py exécutable seul)."),
    ("🔁 Convertir…", "convert", ""),
]


# ───────────────────────────────────────────────────────────────── dialogues ──

class Tip:
    def __init__(self, w, text: str, C: Dict[str, str]):
        self.w, self.text, self.C, self.tw, self.job = w, text, C, None, None
        w.bind("<Enter>", self._sched, add="+")
        w.bind("<Leave>", self._hide, add="+")
        w.bind("<ButtonPress>", self._hide, add="+")

    def _sched(self, e=None):
        self.job = self.w.after(550, self._show)

    def _show(self):
        if self.tw or not self.text:
            return
        try:
            x = self.w.winfo_rootx() + 10
            y = self.w.winfo_rooty() + self.w.winfo_height() + 4
            self.tw = tk.Toplevel(self.w)
            self.tw.wm_overrideredirect(True)
            self.tw.wm_geometry(f"+{x}+{y}")
            tk.Label(self.tw, text=self.text, bg="#fff8dc", fg="#222", font=("Segoe UI", 9), justify="left",
                     relief="solid", bd=1, padx=6, pady=3).pack()
        except tk.TclError:
            self.tw = None

    def _hide(self, e=None):
        if self.job:
            try:
                self.w.after_cancel(self.job)
            except Exception:
                pass
            self.job = None
        if self.tw:
            try:
                self.tw.destroy()
            except Exception:
                pass
            self.tw = None


def _dlg(master, C, title: str, geo: str = "") -> tk.Toplevel:
    d = tk.Toplevel(master)
    d.title(title)
    d.configure(bg=C["bg"])
    d.transient(master.winfo_toplevel())
    if geo:
        d.geometry(geo)
    try:
        top = master.winfo_toplevel()
        d.update_idletasks()
        w, h = (int(x) for x in (geo.split("+")[0].split("x") if geo else (d.winfo_reqwidth(), d.winfo_reqheight())))
        sw, sh = d.winfo_screenwidth(), d.winfo_screenheight()
        x = max(0, min(sw - w, top.winfo_rootx() + (top.winfo_width() - w) // 2))
        y = max(0, min(sh - h - 40, top.winfo_rooty() + (top.winfo_height() - h) // 2))
        d.geometry(f"{w}x{h}+{x}+{y}")
    except Exception:
        pass
    d.bind("<Escape>", lambda e: d.destroy())
    return d


def _btn(parent, text, cmd, C, *, kind="norm", big=False, tip="", **kw):
    bg = {"norm": C["card"], "gold": C["gold"], "ok": "#1f5e43", "bad": "#6a2228", "cyan": "#1d4a5e"}[kind]
    fg = "#1a1408" if kind == "gold" else C["fg"]
    b = tk.Button(parent, text=text, command=cmd, bg=bg, fg=fg, relief="flat", cursor="hand2",
                  font=("Segoe UI", 10 if big else 9, "bold" if big else "normal"),
                  padx=10 if big else 5, pady=5 if big else 2, activebackground=C["gold"],
                  activeforeground="#1a1408", disabledforeground=C["dim"], **kw)
    if tip:
        Tip(b, tip, C)
    return b


class DiffDialog:
    """Différences ligne par ligne ; mode « pick » = case par changement (Accepter/Rejeter)."""

    def __init__(self, master, C, old: str, new: str, title: str, *, mode: str = "pick",
                 subtitle: str = "", ok_text: str = ""):
        self.result = None
        self.a, self.b = old.split("\n"), new.split("\n")
        self.ops = diff_hunks(self.a, self.b)
        self.hunks = [k for k, op in enumerate(self.ops) if op[0] != "equal"]
        self.vars: Dict[int, tk.BooleanVar] = {}
        sw = master.winfo_screenwidth()
        sh = master.winfo_screenheight()
        d = self.d = _dlg(master, C, title, f"{min(980, sw - 40)}x{min(640, sh - 90)}")
        top = tk.Frame(d, bg=C["bg"])
        top.pack(fill="x", padx=10, pady=(8, 4))
        add = sum(op[4] - op[3] for op in self.ops if op[0] in ("replace", "insert"))
        rem = sum(op[2] - op[1] for op in self.ops if op[0] in ("replace", "delete"))
        tk.Label(top, text=title, bg=C["bg"], fg=C["gold"], font=("Segoe UI", 12, "bold")).pack(side="left")
        tk.Label(top, text=f"   {len(self.hunks)} changement(s) ·  +{add}  −{rem} lignes  {subtitle}",
                 bg=C["bg"], fg=C["dim"], font=("Segoe UI", 9)).pack(side="left")
        bar = tk.Frame(d, bg=C["bg"])
        bar.pack(side="bottom", fill="x", padx=10, pady=8)
        body = tk.Frame(d, bg=C["bg"])
        body.pack(fill="both", expand=True, padx=10)
        t = self.t = tk.Text(body, wrap="none", bg="#11151c", fg=C["fg"], font=("Consolas", 10), relief="flat",
                             padx=6, pady=4)
        vs = ttk.Scrollbar(body, orient="vertical", command=t.yview)
        hs = ttk.Scrollbar(body, orient="horizontal", command=t.xview)
        t.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        vs.pack(side="right", fill="y")
        hs.pack(side="bottom", fill="x")
        t.pack(side="left", fill="both", expand=True)
        t.tag_configure("add", background="#173d26", foreground="#b8f5c8")
        t.tag_configure("del", background="#4a1c22", foreground="#ffc2c7")
        t.tag_configure("ctx", foreground="#8a93a6")
        t.tag_configure("gap", foreground="#6a7388", font=("Segoe UI", 9, "italic"))
        t.tag_configure("hdr", background="#232b3a", foreground=C["gold"], font=("Segoe UI", 9, "bold"))
        self._fill(C, pick=(mode == "pick"))
        t.configure(state="disabled")
        if mode == "pick":
            _btn(bar, "✔ Tout accepter", lambda: self._all(True), C).pack(side="left", padx=(0, 4))
            _btn(bar, "✖ Tout rejeter", lambda: self._all(False), C).pack(side="left")
            _btn(bar, "✖  Refuser", d.destroy, C, kind="bad", big=True, width=14).pack(side="right")
            okb = _btn(bar, ok_text or "✅  Appliquer", self._apply, C, kind="gold", big=True, width=16)
            okb.pack(side="right", padx=6)
            tk.Label(bar, text="Appliquer = garde les changements cochés", bg=C["bg"], fg=C["dim"],
                     font=("Segoe UI", 9)).pack(side="right", padx=8)
            d.bind("<Return>", lambda e: self._apply())
            d.bind("<Escape>", lambda e: d.destroy())
        else:
            _btn(bar, "Annuler", d.destroy, C, big=True).pack(side="right")
            _btn(bar, ok_text or "✅ Oui, écraser", self._yes, C, kind="gold", big=True).pack(side="right", padx=6)
        d.grab_set()
        d.focus_force()

    def _fill(self, C, pick: bool):
        t = self.t
        if not self.hunks:
            t.insert("end", "Aucune différence.\n", "gap")
            return
        n = 0
        for k, (tag, i1, i2, j1, j2) in enumerate(self.ops):
            if tag == "equal":
                seg = self.a[i1:i2]
                first, last = k == 0, k == len(self.ops) - 1
                if len(seg) > 6:
                    head = [] if first else seg[:3]
                    tail = [] if last else seg[-3:]
                    for ln in head:
                        t.insert("end", "  " + ln + "\n", "ctx")
                    t.insert("end", f"   ⋯ {len(seg) - len(head) - len(tail)} ligne(s) identique(s) ⋯\n", "gap")
                    for ln in tail:
                        t.insert("end", "  " + ln + "\n", "ctx")
                else:
                    for ln in seg:
                        t.insert("end", "  " + ln + "\n", "ctx")
                continue
            n += 1
            if pick:
                v = tk.BooleanVar(value=True)
                self.vars[k] = v
                cb = tk.Checkbutton(t, text=f" ✔ Garder ce changement ({n}, ligne {i1 + 1})", variable=v,
                                    bg="#232b3a", fg=C["gold"], selectcolor="#11151c", activebackground="#232b3a",
                                    activeforeground=C["gold"], font=("Segoe UI", 9, "bold"), cursor="hand2",
                                    bd=0, highlightthickness=0)
                t.window_create("end", window=cb)
                t.insert("end", "\n", "hdr")
            else:
                t.insert("end", f" ── changement {n} (ligne {i1 + 1}) ──\n", "hdr")
            for ln in self.a[i1:i2]:
                t.insert("end", "− " + ln + "\n", "del")
            for ln in self.b[j1:j2]:
                t.insert("end", "+ " + ln + "\n", "add")

    def _all(self, on: bool):
        for v in self.vars.values():
            v.set(on)

    def _apply(self):
        acc = {k: v.get() for k, v in self.vars.items()}
        self.result = "\n".join(apply_hunks(self.a, self.b, self.ops, acc))
        self.d.destroy()

    def _yes(self):
        self.result = True
        self.d.destroy()

    def show(self):
        self.d.wait_window()
        return self.result


def ask_text(master, C, title: str, prompt: str, initial: str = "", height: int = 5) -> Optional[str]:
    d = _dlg(master, C, title, "620x300")
    tk.Label(d, text=prompt, bg=C["bg"], fg=C["fg"], font=("Segoe UI", 10), wraplength=580,
             justify="left").pack(anchor="w", padx=12, pady=(10, 4))
    out: Dict[str, Optional[str]] = {"v": None}
    bar = tk.Frame(d, bg=C["bg"])
    bar.pack(side="bottom", fill="x", padx=12, pady=8)
    t = tk.Text(d, height=height, bg=C["input"], fg=C["fg"], insertbackground=C["fg"], font=("Segoe UI", 11),
                relief="flat", wrap="word", padx=6, pady=4)
    t.pack(fill="both", expand=True, padx=12)
    t.insert("1.0", initial)
    t.focus_set()

    def ok(e=None):
        out["v"] = t.get("1.0", "end-1c").strip()
        d.destroy()
        return "break"
    t.bind("<Return>", ok)
    t.bind("<Shift-Return>", lambda e: None)
    t.bind("<Control-Return>", ok)
    _btn(bar, "Annuler", d.destroy, C, big=True).pack(side="right")
    _btn(bar, "OK  (Entrée)", ok, C, kind="gold", big=True).pack(side="right", padx=6)
    tk.Label(bar, text="Maj+Entrée = nouvelle ligne", bg=C["bg"], fg=C["dim"], font=("Segoe UI", 8)).pack(side="left")
    d.grab_set()
    d.wait_window()
    return out["v"] or None


class RegexTester:
    def __init__(self, master, C, initial: str = ""):
        d = _dlg(master, C, "🧪 Testeur d'expressions régulières (Python re)", "760x520")
        f = tk.Frame(d, bg=C["bg"])
        f.pack(fill="x", padx=10, pady=8)
        tk.Label(f, text="Motif :", bg=C["bg"], fg=C["fg"]).pack(side="left")
        self.pat = tk.StringVar(value=r"(\w+)@(\w+)\.com")
        e = tk.Entry(f, textvariable=self.pat, font=("Consolas", 12), bg=C["input"], fg=C["fg"],
                     insertbackground=C["fg"], relief="flat")
        e.pack(side="left", fill="x", expand=True, padx=6, ipady=3)
        self.fl = {k: tk.BooleanVar(value=False) for k in ("I", "M", "S")}
        for k, lab in (("I", "ignorer casse"), ("M", "multiligne"), ("S", ". = tout")):
            tk.Checkbutton(f, text=lab, variable=self.fl[k], command=self.run, bg=C["bg"], fg=C["fg"],
                           selectcolor=C["card"], activebackground=C["bg"]).pack(side="left")
        tk.Label(d, text="Texte à tester :", bg=C["bg"], fg=C["dim"]).pack(anchor="w", padx=10)
        self.t = tk.Text(d, height=10, bg="#11151c", fg=C["fg"], font=("Consolas", 11), relief="flat",
                         insertbackground=C["fg"])
        self.t.pack(fill="both", expand=True, padx=10)
        self.t.insert("1.0", initial or "marc@exemple.com, padawan@local.com\npas un courriel\n")
        self.t.tag_configure("m", background="#5a4a1a")
        self.t.tag_configure("g", background="#1d4a5e")
        self.info = tk.Text(d, height=7, bg=C["panel"], fg=C["fg"], font=("Consolas", 10), relief="flat")
        self.info.pack(fill="x", padx=10, pady=8)
        self.pat.trace_add("write", lambda *a: self.run())
        self.t.bind("<KeyRelease>", lambda e: self.run())
        self.run()
        e.focus_set()

    def run(self):
        t, info = self.t, self.info
        t.tag_remove("m", "1.0", "end")
        t.tag_remove("g", "1.0", "end")
        info.delete("1.0", "end")
        fl = 0
        for k, v in self.fl.items():
            if v.get():
                fl |= getattr(re, k)
        try:
            rx = re.compile(self.pat.get(), fl)
        except re.error as ex:
            info.insert("end", f"❌ Motif invalide : {ex}")
            return
        txt = t.get("1.0", "end-1c")
        n = 0
        for m in rx.finditer(txt):
            n += 1
            if m.end() > m.start():
                t.tag_add("m", f"1.0+{m.start()}c", f"1.0+{m.end()}c")
            for gi in range(1, (rx.groups or 0) + 1):
                if m.start(gi) >= 0 and m.end(gi) > m.start(gi):
                    t.tag_add("g", f"1.0+{m.start(gi)}c", f"1.0+{m.end(gi)}c")
            if n <= 30:
                info.insert("end", f"#{n} « {m.group(0)} »  groupes={m.groups()}  {m.groupdict() or ''}\n")
            if n > 5000:
                break
        info.insert("1.0", f"✅ {n} correspondance(s)\n")


def json_tool(master, C, text: str) -> Tuple[bool, str]:
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as ex:
        return False, f"JSON invalide ligne {ex.lineno}, colonne {ex.colno} : {ex.msg}"
    return True, json.dumps(obj, ensure_ascii=False, indent=2)


# ──────────────────────────────────────────────────────────────── l'Atelier ──

CODE_MODELS = ("qwen2.5-coder:7b", "qwen2.5-coder:3b", "qwen2.5-coder:latest", "qwen2.5-coder:1.5b",
               "deepseek-coder:6.7b", "codegemma:7b", "codellama:7b", "starcoder2:7b", "deepseek-coder-v2:16b",
               "qwen2.5-coder:14b", "qwen2.5:7b", "dolphin3:8b", "llama3.1:8b")

DEFAULT_CFG: Dict[str, Any] = {
    "py_dir": "", "web_dir": "", "web_url": "",
    "remote": {"proto": "sftp", "host": "", "port": 0, "user": "", "password": "", "dir": "/", "url": ""},
    "theme": "padawan", "font_size": 11, "py_timeout": 60, "minimap": True, "attach_file": True,
    "model": "", "sash": 0,
}


class Tab:
    def __init__(self, ed: CodeEditor, path: str, external: bool):
        self.ed, self.path, self.external = ed, path, external

    @property
    def name(self):
        return self.ed.name


class Atelier(tk.Frame):
    """Écran complet posé par-dessus la fenêtre de Padawan (place) ; caché, il garde ses onglets."""

    def __init__(self, master, C: Dict[str, str], private_dir: str, *, base: str = "http://127.0.0.1:11434",
                 log: Callable[[str], None] = print, hooks: Optional[Dict[str, Callable]] = None):
        super().__init__(master, bg=C["bg"])
        self.C, self.priv, self.base, self.log = C, private_dir, base.rstrip("/"), log
        self.hooks = hooks or {}
        self.cfg_path = os.path.join(private_dir, "atelier.json")
        self.idx_path = os.path.join(private_dir, "atelier_projets.json")
        self.ws = os.path.join(private_dir, "atelier")
        self.after(60000, self._recovery_tick)  # v41.4 : onglets non enregistrés → atelier\\recup
        par = os.path.dirname(os.path.normpath(private_dir))
        self.bak_root = (os.path.join(par, "bak", "atelier") if os.path.basename(par).lower() == "web_private"
                         else os.path.join(private_dir, "bak", "atelier"))
        self.known_hosts = os.path.join(private_dir, "atelier_known_hosts")
        self.cfg = self._load_cfg()
        self.index = _loadj(self.idx_path, {"projects": [], "last": ""})
        self.project: Optional[Dict[str, Any]] = None
        self.tabs: List[Tab] = []
        self.history: List[Dict[str, str]] = []
        self.q: "queue.Queue" = queue.Queue()
        self.gen_cancel: Optional[threading.Event] = None
        self.gen_busy = False
        self.gen_t0 = 0.0
        self.gen_first = 0.0
        self.gen_tokens = 0
        self.gen_fallback_shown = False
        self.last_err = ""
        self.last_err_tab: Optional[Tab] = None
        self.preview = PreviewServer()
        self.php_runner: Optional[Runner] = None
        self.runner = Runner(lambda s, k: self.q.put(("out", s, k)), lambda c, dt: self.q.put(("exit", c, dt)))
        self.run_tab: Optional[Tab] = None
        self._ansi_tag = "o_n"
        self._build()
        self.after(50, self._poll)
        self._reopen_last()

    # ── réglages ─────────────────────────────────────────────────────────────
    def _load_cfg(self) -> Dict[str, Any]:
        cfg = json.loads(json.dumps(DEFAULT_CFG))
        disk = _loadj(self.cfg_path, None)
        if isinstance(disk, dict):
            for k, v in disk.items():
                if k == "remote" and isinstance(v, dict):
                    cfg["remote"].update(v)
                else:
                    cfg[k] = v
        first = not isinstance(disk, dict)
        if not cfg.get("py_dir"):
            cfg["py_dir"] = r"C:\py" if os.path.isdir(r"C:\py") else os.path.join(os.path.expanduser("~"), "py")
        if first and not cfg.get("web_dir"):
            root = apache_docroot()
            if root and os.path.isdir(root):
                cfg["web_dir"] = os.path.join(root, "atelier")
                cfg["web_url"] = "http://localhost/atelier/"
        if first:
            try:
                self._save_cfg(cfg)
            except Exception as e:
                self.log(f"atelier cfg: {e}")
        return cfg

    def _save_cfg(self, cfg: Optional[Dict[str, Any]] = None):
        _savej(self.cfg_path, cfg or self.cfg)

    def _save_index(self):
        try:
            _savej(self.idx_path, self.index)
        except Exception as e:
            self.log(f"atelier index: {e}")

    # ── construction ─────────────────────────────────────────────────────────
    def _keytags(self, w):
        """Pas de raccourcis de la fenêtre principale ici (Ctrl+L, Ctrl+I…) : nos raccourcis à nous."""
        tags = [t for t in w.bindtags() if t != str(w.winfo_toplevel())]
        tags.insert(1, "AtelierKeys")
        w.bindtags(tuple(tags))

    def _bind_keys(self):
        k = lambda seq, fn: self.bind_class("AtelierKeys", seq, lambda e: (fn(), "break")[1])
        for s in ("<Control-s>", "<Control-S>"):
            k(s, self.save_current)
        for s in ("<Control-f>", "<Control-F>"):
            k(s, lambda: self.find_show(False))
        for s in ("<Control-h>", "<Control-H>"):
            k(s, lambda: self.find_show(True))
        for s in ("<Control-g>", "<Control-G>"):
            k(s, self.goto_line)
        k("<F3>", lambda: self.find_next(1))
        k("<Shift-F3>", lambda: self.find_next(-1))
        k("<F5>", self.preview_current)
        k("<Control-F5>", self.console_current)
        k("<Control-e>", self.modify_current)
        k("<Control-E>", self.modify_current)
        k("<Control-n>", self.new_file)
        k("<Control-N>", self.new_file)
        k("<Control-w>", self.close_tab)
        k("<Control-W>", self.close_tab)
        k("<Control-Shift-C>", self.copy_file)
        k("<Control-k>", self.leave)
        k("<Control-K>", self.leave)
        k("<Control-i>", self.insert_file)  # v41.2 📎
        k("<Control-I>", self.insert_file)
        k("<Control-o>", self.open_file)
        k("<Control-O>", self.open_file)
        self.bind_class("AtelierKeys", "<Escape>", self._esc)

    def _build(self):
        C = self.C
        self._bind_keys()
        hdr = tk.Frame(self, bg=C["panel"])
        hdr.pack(side="top", fill="x")
        tk.Label(hdr, text="💻 ATELIER", bg=C["panel"], fg=C["gold"], font=("Segoe UI", 13, "bold"),
                 padx=10).pack(side="left")
        self.proj_lbl = tk.Label(hdr, text="", bg=C["panel"], fg=C["cyan"], font=("Segoe UI", 10, "bold"),
                                 cursor="hand2")
        self.proj_lbl.pack(side="left", padx=(0, 10))
        self.proj_lbl.bind("<Button-1>", lambda e: self.projects_dialog())
        Tip(self.proj_lbl, "Projet en cours · clic = 📁 Projets", C)
        self.back_btn = _btn(hdr, "⬅ Retour à Padawan", self.leave, C, kind="gold", big=True,
                             tip="Revenir au chat (Ctrl+K)\nL'Atelier garde tes onglets ouverts.")
        self.back_btn.pack(side="right", padx=6, pady=4)
        _btn(hdr, "⚙", self.settings_dialog, C, big=True,
             tip="Réglages : dossier Python, dossier Web local, serveur FTP/FTPS/SFTP,\n"
                 "délai d'exécution, thème, police").pack(side="right", pady=4)
        self.theme_btn = _btn(hdr, "🟦 DOS", self.toggle_theme, C, big=True,
                              tip="Thème de l'éditeur : Padawan sombre ↔ bleu DOS (Turbo Pascal)")
        self.theme_btn.pack(side="right", padx=4, pady=4)
        self.model_var = tk.StringVar()
        self.model_cb = tk.Menubutton(hdr, textvariable=self.model_var, bg=C["card"], fg=C["fg"], relief="flat",
                                      font=("Segoe UI", 9, "bold"), padx=8, pady=3, cursor="hand2", width=20,
                                      activebackground=C["gold"], activeforeground="#1a1408", anchor="w")
        self.model_cb.pack(side="right", padx=(2, 6), pady=6)
        self.model_menu = tk.Menu(self.model_cb, tearoff=0)
        self.model_cb.configure(menu=self.model_menu)
        Tip(self.model_cb, "🧠 Modèle de l'Atelier (clic pour changer)\nTemporaire : ton modèle par défaut revient quand tu sors", C)
        self.model_st = tk.Label(hdr, text="🧠", bg=C["panel"], fg=C["dim"], font=("Segoe UI", 9))
        self.model_st.pack(side="right")

        # barre d'actions (2 rangées pour tenir en 1024 px)
        tb = tk.Frame(self, bg=C["bg"])
        tb.pack(side="top", fill="x", padx=6, pady=(4, 0))
        r1 = tk.Frame(tb, bg=C["bg"])
        r1.pack(fill="x")
        r2 = tk.Frame(tb, bg=C["bg"])
        r2.pack(fill="x", pady=(3, 0))
        B = lambda p, t, c, tip, kind="norm": _btn(p, t, c, C, kind=kind, big=(p is r1), tip=tip)
        self.ins_btn = B(r1, "📎 Insérer un fichier", self.insert_file,
                         "Ctrl+I · choisis un fichier, puis :\n✍ insérer son contenu au curseur · 💬 le joindre à ta question au modèle\n"
                         "· 📂 l'ouvrir dans un onglet. Tu peux aussi le glisser sur l'éditeur ou sur la zone de chat.", "gold")
        self.ins_btn.pack(side="left", padx=2)
        B(r1, "📋 Copier", self.copy_file, "Copie TOUT le fichier dans le presse-papiers (Ctrl+Maj+C)").pack(side="left", padx=2)
        B(r1, "💾 Enregistrer", self.save_current, "Enregistre (Ctrl+S) · garde une version 🕘 à chaque fois").pack(side="left", padx=2)
        B(r1, "👁 Aperçu", self.preview_current, "F5 · HTML : navigateur, recharge tout seul à chaque 💾\n"
          "Python : exécuté en bas (sortie + saisie) · PHP : serveur php local", "cyan").pack(side="left", padx=2)
        B(r1, "🖥 Console", self.console_current, "Ctrl+F5 · lance dans une vraie console Windows\n(couleurs ANSI, input(), menus DOS)").pack(side="left", padx=2)
        B(r1, "🖼→ANSI", self.ansi_studio, "Image → art ANSI / ASCII (16 couleurs DOS, truecolor, Pip-Boy, ░▒▓█)\n"
          "Ouvrir, coller ou glisser une image · .ans, .txt, HTML, insérer dans l'onglet").pack(side="left", padx=2)
        B(r1, "🚀 Déployer", self.deploy_dialog, "Copie vers le dossier Python, le dossier Web local\nou ton serveur (FTP/FTPS/SFTP) — diff + .bak avant d'écraser", "gold").pack(side="left", padx=2)
        B(r1, "✏️ Modifier", self.modify_current, "Ctrl+E · décris le changement : le modèle réécrit le fichier,\n"
          "tu vois le diff et tu acceptes/rejettes chaque changement").pack(side="left", padx=2)
        self.fix_btn = B(r1, "🩺 Corriger", self.fix_error, "Envoie l'erreur + le fichier au modèle et propose un correctif (diff)", "bad")
        self.fix_btn.pack(side="left", padx=2)
        self.fix_btn.configure(state="disabled")
        B(r2, "✨ Nouveau", self.new_dialog, "Nouveau projet : page web rétro, script Python, Arduino,\nPHP+MySQL, menu ASCII DOS… ou vide").pack(side="left", padx=1)
        B(r2, "📁 Projets", self.projects_dialog, "Tes créations : rouvrir, renommer, ouvrir le dossier").pack(side="left", padx=1)
        B(r2, "📂 Ouvrir", self.open_file, "Ouvrir un fichier du disque (Ctrl+O), ex. C:\\py\\truc.py").pack(side="left", padx=1)
        B(r2, "📄+", self.new_file, "Nouveau fichier dans le projet (Ctrl+N)").pack(side="left", padx=1)
        self.snip_mb = tk.Menubutton(r2, text="🧩 Snippets", bg=C["card"], fg=C["fg"], relief="flat",
                                     font=("Segoe UI", 9), padx=7, pady=2, cursor="hand2",
                                     activebackground=C["gold"], activeforeground="#1a1408")
        self.snip_mb.pack(side="left", padx=1)
        self.snip_menu = tk.Menu(self.snip_mb, tearoff=0, postcommand=self._fill_snippets)
        self.snip_mb.configure(menu=self.snip_menu)
        Tip(self.snip_mb, "Bouts de code prêts à insérer au curseur (selon le langage du fichier)", C)
        self.tools_mb = tk.Menubutton(r2, text="🛠 Outils", bg=C["card"], fg=C["fg"], relief="flat",
                                      font=("Segoe UI", 9), padx=7, pady=2, cursor="hand2",
                                      activebackground=C["gold"], activeforeground="#1a1408")
        self.tools_mb.pack(side="left", padx=1)
        self.tools_menu = tk.Menu(self.tools_mb, tearoff=0, postcommand=self._fill_tools)
        self.tools_mb.configure(menu=self.tools_menu)
        Tip(self.tools_mb, "Rechercher/remplacer, aller à la ligne, regex, JSON, couleur,\nexport .zip, git, statistiques", C)
        B(r2, "🕘 Versions", self.versions_dialog, "Ligne du temps du fichier : chaque 💾 et chaque correctif accepté").pack(side="left", padx=1)
        tk.Label(r2, text="  Sélection ➜", bg=C["bg"], fg=C["dim"], font=("Segoe UI", 9)).pack(side="left")
        for lab, kind, _ in QUICK_ACTIONS:
            B(r2, lab, lambda k=kind, l=lab: self.quick_action(k, l),
              "Sur la sélection (ou tout le fichier s'il n'y a rien de sélectionné)").pack(side="left", padx=1)

        self.status = tk.Label(self, text="", bg=C["panel"], fg=C["dim"], font=("Segoe UI", 9), anchor="w", padx=8)
        self.status.pack(side="bottom", fill="x")

        self.pw = tk.PanedWindow(self, orient="horizontal", bg=C["line"], sashwidth=5, bd=0, sashrelief="flat")
        self.pw.pack(fill="both", expand=True, padx=6, pady=6)
        left = tk.Frame(self.pw, bg=C["bg"])
        right = tk.Frame(self.pw, bg=C["bg"])
        self.pw.add(left, minsize=260, width=380)
        self.pw.add(right, minsize=420)
        self._build_chat(left)
        self.vpw = tk.PanedWindow(right, orient="vertical", bg=C["line"], sashwidth=5, bd=0)
        self.vpw.pack(fill="both", expand=True)
        ed_area = tk.Frame(self.vpw, bg=C["bg"])
        out_area = tk.Frame(self.vpw, bg=C["bg"])
        self.vpw.add(ed_area, minsize=200, stretch="always")
        self.vpw.add(out_area, minsize=60, height=150, stretch="never")
        self._build_find(ed_area)
        st = ttk.Style(self)
        st.configure("Atl.TNotebook", background=C["bg"], borderwidth=0)
        st.configure("Atl.TNotebook.Tab", background=C["card"], foreground=C["fg"], padding=(10, 3),
                     font=("Segoe UI", 9))
        st.map("Atl.TNotebook.Tab", background=[("selected", C["gold"])], foreground=[("selected", "#1a1408")])
        st.configure("Atl.TCombobox", fieldbackground=C["card"], foreground=C["fg"], background=C["card"])
        st.map("Atl.TCombobox", fieldbackground=[("readonly", C["card"])], foreground=[("readonly", C["fg"])],
               selectbackground=[("readonly", C["card"])], selectforeground=[("readonly", C["fg"])])
        self.nb = ttk.Notebook(ed_area, style="Atl.TNotebook")
        self.nb.pack(fill="both", expand=True)
        self.after(400, lambda: self._setup_drop(ed_area))  # v41.2 glisser-déposer
        self.nb.bind("<<NotebookTabChanged>>", lambda e: self._tab_changed())
        self.nb.bind("<Button-2>", self._nb_middle)
        self.nb.bind("<Button-3>", self._nb_menu)
        self.empty = tk.Label(ed_area, text="✨ Nouveau projet, 📂 Ouvrir un fichier,\nou demande du code dans le chat à gauche "
                              "— il arrivera ici.", bg=C["bg"], fg=C["dim"], font=("Segoe UI", 12), justify="center")
        self._build_output(out_area)
        self._set_theme_btn()

    def _build_chat(self, f):
        C = self.C
        self.chat = tk.Text(f, wrap="word", bg=C["panel"], fg=C["fg"], font=("Segoe UI", 10), relief="flat",
                            padx=8, pady=6, state="disabled", cursor="arrow", highlightthickness=0)
        bottom = tk.Frame(f, bg=C["bg"])
        bottom.pack(side="bottom", fill="x", pady=(4, 0))
        sb = ttk.Scrollbar(f, orient="vertical", command=self.chat.yview)
        self.chat.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.chat.pack(fill="both", expand=True)
        for tag, kw in (("you", dict(foreground=C["gold"], font=("Segoe UI", 10, "bold"))),
                        ("youtxt", dict(foreground=C["fg"], lmargin1=8, lmargin2=8)),
                        ("ai", dict(foreground=C["cyan"], font=("Segoe UI", 10, "bold"))),
                        ("txt", dict(foreground=C["fg"])),
                        ("sys", dict(foreground=C["dim"], font=("Segoe UI", 9, "italic"))),
                        ("err", dict(foreground=C["bad"])),
                        ("code", dict(font=("Consolas", 9), background="#0d1117", foreground="#c3e88d",
                                      lmargin1=6, lmargin2=6)),
                        ("codehdr", dict(font=("Segoe UI", 9, "bold"), foreground=C["gold"], spacing1=4)),
                        ("stream", dict(foreground=C["fg"], font=("Consolas", 9))),
                        ("bold", dict(foreground=C["fg"], font=("Segoe UI", 10, "bold"))),
                        ("icode", dict(foreground="#c3e88d", font=("Consolas", 9), background="#0d1117"))):
            self.chat.tag_configure(tag, **kw)
        self._keytags(self.chat)
        self.chat.bind("<Button-1>", lambda e: self.chat.focus_set())
        row = tk.Frame(bottom, bg=C["input"], highlightthickness=1, highlightbackground=C["line"],
                       highlightcolor=C["gold"])
        row.pack(fill="x")
        self.inp = tk.Text(row, height=3, wrap="word", bg=C["input"], fg=C["fg"], insertbackground=C["cursor"] if "cursor" in C else C["fg"],
                           font=("Segoe UI", 11), relief="flat", padx=6, pady=4, undo=True)
        self.inp.pack(side="left", fill="both", expand=True)
        self._keytags(self.inp)
        self.inp.bind("<Return>", lambda e: (self.send(), "break")[1])
        self.inp.bind("<KP_Enter>", lambda e: (self.send(), "break")[1])
        self.inp.bind("<Shift-Return>", lambda e: None)
        bcol = tk.Frame(row, bg=C["input"])
        bcol.pack(side="right", fill="y")
        self.send_btn = _btn(bcol, "Envoyer", self.send, C, kind="gold", big=True, tip="Entrée · Maj+Entrée = nouvelle ligne")
        self.send_btn.pack(fill="x", padx=3, pady=(3, 1))
        self.stop_btn = _btn(bcol, "⏹ Stop", self.stop_gen, C, tip="Arrêter la réponse")
        self.stop_btn.pack(fill="x", padx=3, pady=(1, 3))
        self.stop_btn.configure(state="disabled")
        opt = tk.Frame(bottom, bg=C["bg"])
        opt.pack(fill="x")
        self.attach_var = tk.BooleanVar(value=bool(self.cfg.get("attach_file", True)))
        tk.Checkbutton(opt, text="📎 joindre le fichier ouvert", variable=self.attach_var, bg=C["bg"], fg=C["dim"],
                       selectcolor=C["card"], activebackground=C["bg"], font=("Segoe UI", 8),
                       command=self._attach_changed).pack(side="left")
        self.attached: List[Tuple[str, str]] = []  # v41.2 fichiers joints à la prochaine question
        self.att_lbl = tk.Label(opt, text="", bg=C["bg"], fg=C["gold"], font=("Segoe UI", 8, "bold"), cursor="hand2")
        self.att_lbl.pack(side="left", padx=6)
        self.att_lbl.bind("<Button-1>", lambda e: self._attach_clear())
        Tip(self.att_lbl, "Fichiers joints à ta prochaine question · clic = tout retirer", C)
        tk.Label(opt, text="Entrée = envoyer · Maj+Entrée = ligne", bg=C["bg"], fg=C["dim"],
                 font=("Segoe UI", 8)).pack(side="right")

    def _build_find(self, f):
        C = self.C
        self.findbar = tk.Frame(f, bg=C["card"])
        fb = self.findbar
        self.find_var, self.repl_var = tk.StringVar(), tk.StringVar()
        self.find_case, self.find_rx = tk.BooleanVar(value=False), tk.BooleanVar(value=False)
        tk.Label(fb, text="🔍", bg=C["card"], fg=C["fg"]).pack(side="left", padx=(6, 2))
        self.find_ent = tk.Entry(fb, textvariable=self.find_var, width=22, bg=C["input"], fg=C["fg"],
                                 insertbackground=C["fg"], relief="flat", font=("Consolas", 10))
        self.find_ent.pack(side="left", pady=3, ipady=2)
        _btn(fb, "▲", lambda: self.find_next(-1), C, tip="Précédent (Maj+F3)").pack(side="left", padx=1)
        _btn(fb, "▼", lambda: self.find_next(1), C, tip="Suivant (F3 / Entrée)").pack(side="left", padx=1)
        self.repl_frame = tk.Frame(fb, bg=C["card"])
        tk.Label(self.repl_frame, text="→", bg=C["card"], fg=C["fg"]).pack(side="left", padx=2)
        self.repl_ent = tk.Entry(self.repl_frame, textvariable=self.repl_var, width=18, bg=C["input"], fg=C["fg"],
                                 insertbackground=C["fg"], relief="flat", font=("Consolas", 10))
        self.repl_ent.pack(side="left", ipady=2)
        _btn(self.repl_frame, "Remplacer", self.replace_one, C).pack(side="left", padx=1)
        _btn(self.repl_frame, "Tout", self.replace_all, C).pack(side="left", padx=1)
        for txt, var in (("Aa", self.find_case), (".*", self.find_rx)):
            tk.Checkbutton(fb, text=txt, variable=var, bg=C["card"], fg=C["fg"], selectcolor=C["bg"],
                           activebackground=C["card"], command=self._find_mark).pack(side="left")
        self.find_info = tk.Label(fb, text="", bg=C["card"], fg=C["dim"], font=("Segoe UI", 8))
        self.find_info.pack(side="left", padx=4)
        _btn(fb, "✖", self.find_hide, C, tip="Fermer (Échap)").pack(side="right", padx=3)
        for w in (self.find_ent, self.repl_ent):
            self._keytags(w)
        self.find_ent.bind("<Return>", lambda e: (self.find_next(1), "break")[1])
        self.repl_ent.bind("<Return>", lambda e: (self.replace_one(), "break")[1])
        self.find_var.trace_add("write", lambda *a: self._find_mark())

    def _build_output(self, f):
        C = self.C
        top = tk.Frame(f, bg=C["panel"])
        top.pack(side="top", fill="x")
        self.out_lbl = tk.Label(top, text="▶ Sortie", bg=C["panel"], fg=C["dim"], font=("Segoe UI", 9, "bold"), padx=6)
        self.out_lbl.pack(side="left")
        _btn(top, "🧹", self.out_clear, C, tip="Effacer la sortie").pack(side="right", padx=2, pady=1)
        self.run_stop = _btn(top, "⏹ Stop", self.stop_run, C, kind="bad", tip="Arrêter le programme")
        self.run_stop.pack(side="right", padx=2, pady=1)
        self.run_stop.configure(state="disabled")
        self.pip_btn = _btn(top, "📦 pip install", self.pip_install, C, kind="cyan",
                            tip="Installe le module manquant (demande confirmation)")
        self.fix2_btn = _btn(top, "🩺 Corriger cette erreur", self.fix_error, C, kind="bad")
        row = tk.Frame(f, bg=C["panel"])
        row.pack(side="bottom", fill="x")
        tk.Label(row, text="⌨ saisie :", bg=C["panel"], fg=C["dim"], font=("Segoe UI", 8)).pack(side="left", padx=4)
        self.stdin_var = tk.StringVar()
        self.stdin_ent = tk.Entry(row, textvariable=self.stdin_var, bg=C["input"], fg=C["fg"],
                                  insertbackground=C["fg"], relief="flat", font=("Consolas", 10))
        self.stdin_ent.pack(side="left", fill="x", expand=True, pady=2, ipady=1)
        self._keytags(self.stdin_ent)
        self.stdin_ent.bind("<Return>", lambda e: (self._send_stdin(), "break")[1])
        Tip(self.stdin_ent, "Ce que tu tapes ici est envoyé au programme (input()) avec Entrée", C)
        self.out = tk.Text(f, wrap="char", bg="#0c0c0c", fg="#cccccc", font=("Consolas", 10), relief="flat",
                           padx=6, pady=3, state="disabled", height=6)
        osb = ttk.Scrollbar(f, orient="vertical", command=self.out.yview)
        self.out.configure(yscrollcommand=osb.set)
        osb.pack(side="right", fill="y")
        self.out.pack(fill="both", expand=True)
        self._keytags(self.out)
        self.out.bind("<Button-1>", lambda e: self.out.focus_set())
        self.out.tag_configure("o_err", foreground="#ff7b72")
        self.out.tag_configure("o_sys", foreground="#7ec8e8", font=("Segoe UI", 9, "italic"))
        self.out.tag_configure("o_link", foreground="#ffd479", underline=True)
        self.out.tag_bind("o_link", "<Button-1>", self._out_click)
        self.out.tag_bind("o_link", "<Enter>", lambda e: self.out.config(cursor="hand2"))
        self.out.tag_bind("o_link", "<Leave>", lambda e: self.out.config(cursor="xterm"))
        for code, col in ANSI_COL.items():
            self.out.tag_configure(f"fg{code}", foreground=col)
        for code in range(40, 48):
            self.out.tag_configure(f"bg{code}", background=ANSI_COL[code - 10])
        self.out.tag_configure("o_b", font=("Consolas", 10, "bold"))

    # ── entrée / sortie de l'écran ───────────────────────────────────────────
    def enter(self, prefill: str = "", autosend: bool = False):
        self.place(x=0, y=0, relwidth=1, relheight=1)
        self.lift()
        self._refresh_models()
        if not self.tabs:
            self._show_empty(True)
        if prefill:
            self.inp.delete("1.0", "end")
            self.inp.insert("1.0", prefill)
            if autosend:
                self.after(100, self.send)
        (self.inp if not self.tabs or prefill else self.cur().ed.t).focus_set()
        self._status()

    def leave(self):
        self.place_forget()
        cb = self.hooks.get("leave")
        if cb:
            cb()

    def save_recovery(self) -> List[str]:
        """v41.4 : copie des onglets NON enregistrés dans atelier\\recup (avant fermeture / toutes les 60 s)."""
        out = []
        try:
            d = os.path.join(self.ws, "recup")
            for t in list(self.tabs):
                txt = t.ed.get()
                if t.ed.dirty() and txt.strip():
                    os.makedirs(d, exist_ok=True)
                    p = os.path.join(d, f"{slugify(os.path.splitext(t.name)[0]) or 'onglet'}__recup{os.path.splitext(t.name)[1]}")
                    try:
                        if os.path.exists(p) and read_text(p) == txt:
                            out.append(p)
                            continue
                    except Exception:
                        pass
                    write_text(p, txt)
                    out.append(p)
        except Exception:
            pass
        return out

    def _recovery_tick(self):
        self.save_recovery()
        try:
            self.after(60000, self._recovery_tick)
        except Exception:
            pass

    def shutdown(self):
        self.save_recovery()
        try:
            self.runner.stop()
            if self.php_runner:
                self.php_runner.stop()
            self.preview.stop()
        except Exception:
            pass

    # ── modèle ───────────────────────────────────────────────────────────────
    def installed(self) -> List[str]:
        fn = self.hooks.get("models")
        try:
            return list(fn()) if fn else []
        except Exception:
            return []

    def pick_model(self, inst: Optional[List[str]] = None) -> str:
        inst = inst if inst is not None else self.installed()
        low = {m.lower(): m for m in inst}
        want = (self.cfg.get("model") or "").lower()
        if want and want in low:
            return low[want]
        for m in CODE_MODELS:
            if m in low:
                return low[m]
        for m in inst:
            if "coder" in m.lower() or "code" in m.lower():
                return m
        return self.current_model() or (inst[0] if inst else "")

    def current_model(self) -> str:
        fn = self.hooks.get("current")
        return fn() if fn else (self.cfg.get("model") or "qwen2.5-coder:7b")

    def _refresh_models(self):
        inst = self.installed()
        order = [m for m in CODE_MODELS if m in inst] + [m for m in inst if m not in CODE_MODELS]
        self.model_menu.delete(0, "end")
        for m in order:
            star = "⭐ " if ("coder" in m or "code" in m) else "    "
            self.model_menu.add_command(label=star + m, command=lambda n=m: self._model_picked(n))
        want = self.pick_model(inst)
        if want and want != self.current_model():
            sw = self.hooks.get("switch")
            if sw:
                sw(want)
        self.model_var.set("🧠 " + self.current_model())

    def _model_picked(self, name: str = ""):
        name = name or self.model_var.get()
        self.model_var.set("🧠 " + name)
        self.cfg["model"] = name
        self._save_cfg()
        sw = self.hooks.get("switch")
        if sw:
            sw(name)
        self.say_sys(f"🧠 L'Atelier utilisera {name} (gardé pour l'Atelier seulement).")

    def _fallback_model(self) -> str:
        cur = self.current_model()
        inst = self.installed()
        for m in ("qwen2.5-coder:3b", "qwen2.5-coder:1.5b", "dolphin3:8b", "qwen2.5:7b", "qwen2.5-coder:7b"):
            if m in inst and m != cur:
                return m
        return ""

    # ── chat ─────────────────────────────────────────────────────────────────
    def _chat_ins(self, text: str, tag: str = "txt"):
        self.chat.configure(state="normal")
        self.chat.insert("end", text, tag)
        self.chat.configure(state="disabled")
        self.chat.see("end")

    def say_sys(self, text: str):
        self._chat_ins(text + "\n\n", "sys")

    def _render_answer(self, text: str):
        """Texte + blocs de code (avec 📋 Copier et ➡ Éditeur)."""
        C = self.C
        ch = self.chat
        ch.configure(state="normal")
        pos = 0
        for m in re.finditer(r"(?ms)^[ \t]*(`{3,})[ \t]*([^\n`]*)\n(.*?)(?:^[ \t]*\1[ \t]*$|\Z)", text):
            self._md(text[pos:m.start()])
            code = m.group(3).rstrip("\n")
            blk = (extract_blocks(text[m.start():m.end()] + ("\n" if not m.group(0).endswith("\n") else "")) or
                   [{"lang": guess_lang(code), "name": "", "code": code}])[0]
            ch.insert("end", f"📄 {blk['name'] or LANG_LABEL.get(blk['lang'], 'code')}  ", "codehdr")
            b1 = tk.Button(ch, text="📋 Copier", font=("Segoe UI", 8), bg=C["card"], fg=C["fg"], relief="flat",
                           cursor="hand2", padx=4, pady=0, command=lambda c=code: self._clip(c, "Bloc copié"))
            b2 = tk.Button(ch, text="➡ Éditeur", font=("Segoe UI", 8), bg=C["card"], fg=C["gold"], relief="flat",
                           cursor="hand2", padx=4, pady=0, command=lambda b=blk: self._apply_block(b, None, ask=True))
            ch.window_create("end", window=b1, padx=2)
            ch.window_create("end", window=b2, padx=2)
            ch.insert("end", "\n", "codehdr")
            lines = code.split("\n")
            shown = "\n".join(lines[:14]) + (f"\n   ⋯ (+{len(lines) - 14} lignes, voir l'éditeur)" if len(lines) > 14 else "")
            ch.insert("end", shown + "\n", "code")
            pos = m.end()
        self._md(text[pos:] + "\n\n")
        ch.configure(state="disabled")
        ch.see("end")

    _MD_RX = re.compile(r"\*\*(.+?)\*\*|`([^`\n]+)`")

    def _md(self, text: str):
        """Markdown léger : # titres, **gras**, `code`."""
        ch = self.chat
        for line in text.split("\n"):
            mh = re.match(r"^\s*#{1,6}\s+(.*)$", line)
            if mh:
                ch.insert("end", mh.group(1).strip("* ") + "\n", "bold")
                continue
            mb = re.match(r"^(\s*)[-*]\s+(.*)$", line)
            if mb:
                ch.insert("end", mb.group(1) + "• ", "txt")
                line = mb.group(2)
            pos = 0
            for m in self._MD_RX.finditer(line):
                ch.insert("end", line[pos:m.start()], "txt")
                ch.insert("end", m.group(1) or m.group(2), "bold" if m.group(1) else "icode")
                pos = m.end()
            ch.insert("end", line[pos:] + "\n", "txt")
        ch.delete("end-2c", "end-1c")

    def _attach_changed(self):
        self.cfg["attach_file"] = bool(self.attach_var.get())
        self._save_cfg()

    def send(self):
        q = self.inp.get("1.0", "end-1c").strip()
        if not q or self.gen_busy:
            return
        self.inp.delete("1.0", "end")
        tab = self.cur()
        ctx = ""
        if tab and tab.ed.get().strip() and is_edit_request(q, tab.name):  # v41.4 : vraie modification du fichier
            att = list(getattr(self, "attached", []) or [])
            self._attach_clear(quiet=True)
            self._chat_ins("Toi\n", "you")
            self._chat_ins(q + f"\n✏️ modification de {tab.name}\n\n", "youtxt")
            return self.edit_request(q, tab, extra_ctx="".join(b + "\n\n" for _, b in att))
        cur_on = bool(tab and self.attach_var.get() and tab.ed.get().strip())
        if cur_on:  # v41.3 : un gros fichier est joint en partie (avant : ignoré sans rien dire)
            body, cut = clip_text(tab.ed.get(), 24000)
            ctx = (f"[Fichier ouvert dans l'éditeur : {tab.name}]\n```{tab.ed.lang} {tab.name}\n{body}\n```\n\n")
            if cut:
                self.say_sys(f"⚠ {tab.name} est gros : seuls les 24 000 premiers caractères partent au modèle "
                             "(sélectionne un passage + ✏️ Modifier pour une partie précise).")
        att = list(getattr(self, "attached", []) or [])
        for nm, body in att:
            ctx += body + "\n\n"
        self._chat_ins("Toi\n", "you")
        names = ([tab.name] if cur_on else []) + [n for n, _ in att]
        self._chat_ins(q + ("\n📎 " + ", ".join(names) if names else "") + "\n\n", "youtxt")
        if att:
            self._attach_clear(quiet=True)
        self._generate(ctx + q, q, purpose="chat", tab=tab)

    # ── v41.4 ✏️ modification réelle (SEARCH/REPLACE) ──────────────────────
    def edit_request(self, what: str, tab: Tab, retry: int = 0, extra_ctx: str = ""):
        src = tab.ed.get()
        if len(src.split("\n")) <= 900 and len(src) <= 60000:  # v41.4 : lignes numérotées (fiable même en 7B)
            keys = key_lines(src, what)
            strict = ("\nATTENTION : ta réponse précédente était inutilisable. Réponds SEULEMENT par des lignes « L<n>: … ».\n"
                      if retry else "")
            prompt = (f"{extra_ctx}FICHIER {tab.name} ({len(src.split(chr(10)))} lignes) :\n{number_lines(src)}\n\n"
                      + (f"Lignes probablement concernées :\n{keys}\n\n" if keys else "")
                      + (f"Couleurs de fond du fichier : {color_hints(src)}\n\n"
                         if re.search(r"(?i)fond|background|couleur|color", what) and color_hints(src) else "")
                      + f"DEMANDE : {what}\n{strict}\nModifie TOUTES les lignes nécessaires (ex. chaque fond de couleur visible : page, "
                         "boîtes, écran), pas seulement la première. Réponds uniquement par les lignes modifiées (format L<n>: …).")
            return self._generate(prompt, f"✏️ {what} ({tab.name})", purpose="patch", tab=tab,
                                  extra={"what": what, "retry": retry, "show": bool(SHOW_RX.search(what)),
                                         "system": SYSTEM_LINES})
        keys = key_lines(src, what)
        strict = ("\nATTENTION : ta réponse précédente était un exemple générique ou un fragment. Cette fois, copie "
                  "EXACTEMENT les lignes du fichier dans SEARCH et ne change que la demande.\n") if retry else ""
        prompt = (f"{extra_ctx}Voici le fichier COMPLET de Marc ({len(src.splitlines())} lignes) :\n"
                  f"```{tab.ed.lang} {tab.name}\n{src}\n```\n\n"
                  + (f"Lignes probablement concernées :\n{keys}\n\n" if keys else "")
                  + f"Demande de Marc : {what}\n{strict}\n"
                  "Réponds avec des blocs <<<<<<< SEARCH / ======= / >>>>>>> REPLACE (texte EXACT du fichier dans SEARCH).")
        self._generate(prompt, f"✏️ {what} ({tab.name})", purpose="patch", tab=tab,
                       extra={"what": what, "retry": retry, "show": bool(SHOW_RX.search(what)), "system": SYSTEM_PATCH})

    def _after_patch(self, full: str, ctx: Dict[str, Any]):
        tab, ex = ctx["tab"], ctx["extra"]
        if not tab or tab not in self.tabs:
            return
        old = tab.ed.get()
        pts = parse_patches(full)
        new, why = None, ""
        le = parse_line_edits(full) if not pts else []
        if le:
            cand, k = apply_line_edits(old, le)
            why = looks_fragment(old, cand) if k else "ses lignes ne changent rien"
            if k and not why and cand != old:
                new = cand
        elif pts:
            cand, ok, bad = apply_patches(old, pts)
            if ok and cand != old:
                new = cand
                if bad:
                    self.say_sys(f"⚠ {bad} bloc(s) introuvable(s) dans {tab.name} — seuls {ok} appliqué(s).")
            else:
                why = "ses blocs SEARCH ne correspondent pas au fichier"
        else:
            blocks = extract_blocks(full)
            b = next((x for x in blocks if x["name"] and x["name"].lower() == tab.name.lower()), None) or \
                next((x for x in blocks if x["lang"] == tab.ed.lang), None) or (blocks[0] if blocks else None)
            if b:
                why = looks_fragment(old, b["code"])
                if not why:
                    new = b["code"]
            else:
                why = "pas de changement dans la réponse"
        if new is None:
            if not ex.get("retry"):
                self.say_sys(f"↻ Réponse inutilisable ({why}) — je redemande au modèle, plus strictement…")
                return self.after(200, lambda: self.edit_request(ex["what"], tab, retry=1))
            self.say_sys(f"🛑 Je n'applique rien : {why}. Ton fichier {tab.name} est intact. "
                         "Reformule (ex. « change #6C5EB5 en rouge »), ou insère l'extrait proposé :")
            snip = (extract_blocks(full) or [{"code": full}])[0]["code"]
            self._offer_snippet(tab, snip)
            return
        self._propose(tab, new, "✏️ Modification proposée")
        if ex.get("show") and tab.ed.get() != old:
            self.after(300, self.preview_current)

    def _offer_snippet(self, tab: Tab, code: str):
        b = tk.Button(self.chat, text="➕ Insérer l'extrait au curseur", font=("Segoe UI", 8, "bold"), bg=self.C["card"],
                      fg=self.C["gold"], relief="flat", cursor="hand2",
                      command=lambda: self._ins_text(code, "➕ Extrait inséré au curseur (Ctrl+Z pour annuler)."))
        self.chat.configure(state="normal")
        self.chat.window_create("end", window=b)
        self.chat.insert("end", "\n\n")
        self.chat.configure(state="disabled")
        self.chat.see("end")

    # ── v41.2 📎 insérer un fichier ──────────────────────────────────────────
    def insert_file(self, path: str = "", how: str = ""):
        if not path:
            init = (self.project or {}).get("dir", "") or os.path.expanduser("~")
            path = filedialog.askopenfilename(parent=self, initialdir=init, title="📎 Insérer un fichier")
            if not path:
                return
        path = os.path.normpath(path)
        if not os.path.isfile(path):
            return self.say_sys(f"📎 Introuvable : {path}")
        if not how:  # v41.3 : vraie fenêtre (le menu tk_popup se refermait tout seul après la boîte « Ouvrir »)
            return self._insert_choice(path)
        try:
            r = self._insert_file_do(path, how)
        except Exception as e:
            r = "error"
            self.say_sys(f"📎 Erreur avec {os.path.basename(path)} : {e}")
        self._ins_feedback(path, how, r)
        return r

    def _ins_feedback(self, path: str, how: str, r: str):
        name = os.path.basename(path)
        msg = {"editor": f"📎 {name} inséré au curseur", "chat": f"📎 {name} joint à ta prochaine question",
               "open": f"📂 {name} ouvert dans un onglet", "refused": f"📎 {name} : non inséré (voir le chat)",
               "error": f"📎 {name} : erreur (voir le chat)"}.get(r, f"📎 {name}")
        col = self.C["ok"] if r in ("editor", "chat", "open") else self.C["bad"]

        def show():
            try:
                self.status.configure(text=msg, fg=col)
                self.after(5000, self._status)
            except Exception:
                pass
        self.after(120, show)  # après le rafraîchissement de la barre par le changement d'onglet

    def _insert_choice(self, path: str):
        C = self.C
        name = os.path.basename(path)
        try:
            size = os.path.getsize(path)
        except OSError:
            size = 0
        kind = file_kind(path)
        d = tk.Toplevel(self)
        self._ins_dlg = d
        d.title("📎 Insérer un fichier")
        d.configure(bg=C["panel"])
        d.transient(self.winfo_toplevel())
        d.resizable(False, False)
        tk.Label(d, text=f"📎 {name}", bg=C["panel"], fg=C["gold"], font=("Segoe UI", 13, "bold")).pack(padx=18, pady=(14, 0))
        info = {"text": "fichier texte / code", "image": "image (seul son chemin peut être inséré)",
                "binary": "fichier binaire — ne peut pas être inséré comme texte"}[kind]
        tk.Label(d, text=f"{size / 1024:.0f} Ko · {info}\n{path}", bg=C["panel"], fg=C["dim"], font=("Segoe UI", 9),
                 justify="center", wraplength=520).pack(padx=18, pady=(2, 10))
        def go(how):
            try:
                d.grab_release()
            except Exception:
                pass
            d.destroy()
            self.insert_file(path, how)
        opts = [("📂  Ouvrir dans un onglet", "open", "gold"), ("✍  Insérer le contenu au curseur", "editor", "norm"),
                ("💬  Joindre à ma question au modèle", "chat", "cyan")]
        btns = {}
        for lab, how, kd in opts:
            b = _btn(d, lab, lambda h=how: go(h), C, kind=kd, big=True, width=34)
            b.pack(padx=18, pady=3, fill="x")
            btns[how] = b
        _btn(d, "Annuler (Échap)", d.destroy, C).pack(pady=(6, 12))
        self._ins_btns = btns
        default = "editor" if kind == "image" else "open"
        btns[default].configure(relief="solid", bd=2)
        d.bind("<Return>", lambda e: go(default))
        d.bind("<Escape>", lambda e: d.destroy())
        d.update_idletasks()
        top = self.winfo_toplevel()
        x = top.winfo_rootx() + (top.winfo_width() - d.winfo_reqwidth()) // 2
        y = top.winfo_rooty() + (top.winfo_height() - d.winfo_reqheight()) // 3
        d.geometry(f"+{max(0, x)}+{max(0, y)}")
        d.attributes("-topmost", True)
        d.lift()
        d.focus_force()
        btns[default].focus_set()
        try:
            d.grab_set()
        except Exception:
            pass
        try:
            self.status.configure(text=f"📎 {name} : choisis quoi faire dans la fenêtre", fg=self.C["gold"])
        except Exception:
            pass
        return d

    def _insert_file_do(self, path: str, how: str) -> str:
        name = os.path.basename(path)
        kind = file_kind(path)
        if kind == "binary":
            self.say_sys(f"📎 « {name} » est un fichier binaire (exe, zip, pdf…) : je ne peux pas l'insérer comme texte.")
            return "refused"
        if how == "open":
            if kind == "image":
                self.say_sys(f"📎 « {name} » est une image : essaie 🖼→ANSI, ou ✍ pour insérer son chemin.")
                return "refused"
            return "open" if self.open_path(path) else "error"
        if kind == "image":
            ref = path.replace("\\", "/")
            if how == "editor":
                return self._ins_text(ref, f"📎 Chemin de l'image inséré : {name}")
            self._attach_add(name, f"[Image jointe : {name} — chemin {ref} (le modèle ne voit pas l'image, seulement son nom/chemin)]")
            return "chat"
        try:
            txt = read_text(path)
        except Exception as e:
            self.say_sys(f"📎 Lecture impossible : {e}")
            return "error"
        if how == "editor":
            body, cut = clip_text(txt, INSERT_MAX)
            return self._ins_text(body, f"📎 {name} inséré au curseur ({len(txt):,} car.)".replace(",", " ")
                                  + (" — ⚠ tronqué" if cut else "") + " · Ctrl+Z pour annuler")
        body, cut = clip_text(txt, ATTACH_MAX)
        lang = lang_of(name) or ""
        self._attach_add(name, f"[Fichier joint : {name}]\n```{lang} {name}\n{body}\n```")
        if cut:
            self.say_sys(f"⚠ {name} est gros : seuls les {ATTACH_MAX:,} premiers caractères sont joints.".replace(",", " "))
        return "chat"

    def _ins_text(self, text: str, msg: str) -> str:
        t = self.cur()
        if not t:
            t = self.add_tab("sans_titre.txt", "", dirty=True)
        ed = t.ed
        ed.t.edit_separator()
        ed.t.insert("insert", text)
        ed.t.edit_separator()
        try:
            ed.t.event_generate("<<Modified>>")
        except Exception:
            pass
        ed.t.focus_set()
        self.say_sys(msg)
        return "editor"

    def _attach_add(self, name: str, body: str):
        self.attached = [a for a in self.attached if a[0] != name] + [(name, body)]
        self._attach_lbl()
        self.say_sys(f"📎 {name} joint : il partira avec ta prochaine question.")
        self.inp.focus_set()

    def _attach_clear(self, quiet: bool = False):
        if self.attached and not quiet:
            self.say_sys("📎 Fichiers joints retirés.")
        self.attached = []
        self._attach_lbl()

    def _attach_lbl(self):
        n = len(self.attached)
        self.att_lbl.configure(text=(f"📎 {n} joint{'s' if n > 1 else ''} : " + ", ".join(a[0] for a in self.attached)[:60] + " ✖") if n else "")

    def _setup_drop(self, ed_area):
        if _ANSI is None or not hasattr(_ANSI, "enable_drop"):
            return
        def on(files, how):
            for f in files[:5]:
                if how == "editor" and len(files) == 1:
                    self.insert_file(f)  # menu : insérer / joindre / ouvrir
                else:
                    self._insert_file_do(f, "chat" if how == "chat" else "open")
        try:
            self._drop_ed = _ANSI.enable_drop(ed_area, lambda fs: on(fs, "editor"))
            self._drop_chat = _ANSI.enable_drop(self.inp, lambda fs: on(fs, "chat"))
        except Exception:
            pass

    def _generate(self, prompt: str, shown: str, *, purpose: str, tab: Optional[Tab] = None,
                  sel: Optional[Tuple[str, str]] = None, extra: Optional[Dict[str, Any]] = None):
        if self.gen_busy:
            self.say_sys("⏳ Une réponse est déjà en cours (⏹ Stop pour l'arrêter).")
            return
        if not requests:
            self.say_sys("❌ Module requests manquant.")
            return
        model = self.current_model()
        sysp = (extra or {}).get("system") or SYSTEM_PROG
        msgs = [{"role": "system", "content": sysp}]
        for h in (self.history[-6:] if purpose != "patch" else []):
            msgs.append({"role": h["role"], "content": h["content"][:6000]})
        msgs.append({"role": "user", "content": prompt})
        self.history.append({"role": "user", "content": shown})
        self.gen_busy = True
        self.gen_cancel = threading.Event()
        self.gen_t0, self.gen_first, self.gen_tokens = time.time(), 0.0, 0
        self.gen_fallback_shown = False
        self._gen_ctx = {"purpose": purpose, "tab": tab, "sel": sel, "extra": extra or {}, "model": model}
        self.send_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self._chat_ins(f"Padawan · {model}\n", "ai")
        self.chat.mark_set("streamstart", "end-1c")
        self.chat.mark_gravity("streamstart", "left")
        opts = {}
        fn = self.hooks.get("gen_opts")
        if fn:
            try:
                opts = dict(fn())
            except Exception:
                opts = {}
        opts["temperature"] = 0.2
        opts["num_predict"] = 6144
        opts.setdefault("repeat_penalty", 1.05)
        threading.Thread(target=self._gen_worker, args=(model, msgs, opts, self.gen_cancel), daemon=True).start()
        self.after(500, self._gen_tick)

    def _gen_worker(self, model, msgs, opts, cancel):
        full = []
        try:
            r = requests.post(self.base + "/api/chat", json={"model": model, "messages": msgs, "stream": True,
                                                            "keep_alive": "30m", "options": opts},
                              stream=True, timeout=(10, 600))
            if r.status_code != 200:
                raise RuntimeError(f"Ollama HTTP {r.status_code} : {r.text[:200]}")
            for line in r.iter_lines():
                if cancel.is_set():
                    r.close()
                    break
                if not line:
                    continue
                j = json.loads(line)
                if j.get("error"):
                    raise RuntimeError(j["error"])
                tok = (j.get("message") or {}).get("content", "")
                if tok:
                    full.append(tok)
                    self.q.put(("tok", tok))
                if j.get("done"):
                    break
            self.q.put(("done", "".join(full), cancel.is_set()))
        except Exception as e:
            self.q.put(("gerr", str(e), "".join(full)))

    def _gen_tick(self):
        if not self.gen_busy:
            return
        dt = time.time() - self.gen_t0
        if not self.gen_first:
            ready = self.hooks.get("ready")
            st = "chargement du modèle" if (ready and not ready()) else "réflexion"
            self.model_st.configure(text=f"⏳ {st} · {dt:.0f} s", fg=self.C["gold"])
            if dt > 75 and not self.gen_fallback_shown:
                self.gen_fallback_shown = True
                fb = self._fallback_model()
                self._chat_ins("\n⌛ Le modèle est long à démarrer (premier chargement en mémoire). ", "sys")
                if fb:
                    b = tk.Button(self.chat, text=f"⚡ Passer à {fb}", font=("Segoe UI", 8, "bold"),
                                  bg=self.C["gold"], fg="#1a1408", relief="flat", cursor="hand2",
                                  command=lambda: self._use_fallback(fb))
                    self.chat.configure(state="normal")
                    self.chat.window_create("end", window=b)
                    self.chat.configure(state="disabled")
                self._chat_ins("\n", "sys")
        else:
            tps = self.gen_tokens / max(0.1, time.time() - self.gen_first)
            self.model_st.configure(text=f"✍ {self.gen_tokens} jetons · {tps:.0f}/s · {dt:.0f} s", fg=self.C["ok"])
        self.after(500, self._gen_tick)

    def _use_fallback(self, name: str):
        self.stop_gen()
        sw = self.hooks.get("switch")
        if sw:
            sw(name)
        self.model_var.set("🧠 " + name)
        self.say_sys(f"⚡ Atelier → {name}. Renvoie ta demande (↑ elle est encore dans l'historique).")
        if self.history and self.history[-1]["role"] == "user":
            self.inp.delete("1.0", "end")
            self.inp.insert("1.0", self.history[-1]["content"])

    def stop_gen(self):
        if self.gen_cancel:
            self.gen_cancel.set()

    def _gen_end(self, full: str, err: str = "", cancelled: bool = False):
        self.gen_busy = False
        self.send_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        dt = time.time() - self.gen_t0
        self.chat.configure(state="normal")
        try:
            self.chat.delete("streamstart", "end")
        except tk.TclError:
            pass
        self.chat.configure(state="disabled")
        self._chat_ins("\n", "txt")
        if full.strip():
            self._render_answer(full)
            self.history.append({"role": "assistant", "content": full})
        if err:
            self._chat_ins(f"❌ {err}\n\n", "err")
        if cancelled:
            self.say_sys("⏹ Réponse arrêtée.")
        self.model_st.configure(text=f"🧠 prêt · dernière réponse {dt:.0f} s", fg=self.C["dim"])
        self._save_chat()
        if full.strip() and not cancelled:
            self._after_answer(full)

    def _after_answer(self, full: str):
        ctx = self._gen_ctx
        purpose, tab = ctx["purpose"], ctx["tab"]
        if purpose == "patch":
            return self._after_patch(full, ctx)
        blocks = extract_blocks(full)
        if purpose == "explain" or not blocks:
            if purpose in ("edit", "fix", "sel") and not blocks:
                self.say_sys("🤔 Pas de bloc de code dans la réponse : rien à appliquer.")
            return
        if purpose in ("edit", "fix") and tab and tab in self.tabs:
            b = next((x for x in blocks if x["name"] and x["name"].lower() == tab.name.lower()), None) or \
                next((x for x in blocks if x["lang"] == tab.ed.lang), None) or blocks[0]
            self._propose(tab, b["code"], "🩺 Correctif proposé" if purpose == "fix" else "✏️ Modification proposée")
            for x in blocks:
                if x is not b and x["name"]:
                    self._apply_block(x, None)
            return
        if purpose == "sel" and tab and tab in self.tabs and ctx.get("sel"):
            a, bb = ctx["sel"]
            full_old = tab.ed.get()
            try:
                pre = tab.ed.t.get("1.0", a)
                post = tab.ed.t.get(bb, "end-1c")
            except tk.TclError:
                return
            new = pre + blocks[0]["code"] + post
            self._propose(tab, new, ctx["extra"].get("title", "Changement proposé"), old=full_old)
            return
        if purpose in ("tests", "convert"):
            for x in blocks:
                if not x["name"]:
                    base = os.path.splitext(tab.name)[0] if tab else "code"
                    x["name"] = (f"test_{base}.py" if purpose == "tests" else base + LANG_EXT.get(x["lang"], ".txt"))
                self._apply_block(x, None)
            return
        for x in blocks:
            self._apply_block(x, tab)

    def _apply_block(self, blk: Dict[str, str], hint: Optional[Tab], ask: bool = False):
        name = blk.get("name") or ""
        target = None
        if name:
            target = next((t for t in self.tabs if t.name.lower() == name.lower()), None)
        elif hint and hint in self.tabs and hint.ed.lang == blk["lang"]:
            target = hint
        if not name and not target:
            name = DEFAULT_NAME.get(blk["lang"], "code.txt")
            target = next((t for t in self.tabs if t.name.lower() == name.lower()), None)
        if target:
            if target.ed.get() == blk["code"]:
                self.nb.select(target.ed)
                return
            if not target.ed.get().strip():
                target.ed.set(blk["code"])
                self.nb.select(target.ed)
                return
            self._propose(target, blk["code"], f"Nouvelle version de {target.name}")
            return
        t = self.add_tab(name, blk["code"], dirty=True)
        self.say_sys(f"➡ {name} ouvert dans l'éditeur (pas encore enregistré : 💾 Ctrl+S).")
        self.nb.select(t.ed)

    def _propose(self, tab: Tab, new: str, title: str, old: Optional[str] = None):
        guard = old is None
        old = tab.ed.get() if old is None else old
        why = looks_fragment(old, new) if guard else ""
        if why:  # v41.4 : un exemple/fragment ne remplace jamais le fichier entier
            self.say_sys(f"🛑 Ce code n'est qu'un morceau ({why}) : je ne remplace pas {tab.name}. "
                         "Pour modifier ton fichier, écris ta demande (ex. « change le fond en rouge ») ou ✏️ Modifier.")
            self._offer_snippet(tab, new)
            return
        if old == new:
            self.say_sys(f"= {tab.name} : aucune différence.")
            return
        self.nb.select(tab.ed)
        res = DiffDialog(self, self.C, old, new, f"{title} · {tab.name}",
                         subtitle="· coche ce que tu gardes").show()
        if res is None:
            self.say_sys(f"✖ Changement de {tab.name} refusé (rien n'a bougé).")
            return
        tab.ed.set(res)
        self._snapshot(tab, res, "ia")
        self.say_sys(f"✅ {tab.name} mis à jour (Ctrl+Z pour annuler · 🕘 Versions). Pense à 💾.")
        self._status()

    def _clip(self, text: str, msg: str = "Copié"):
        self.clipboard_clear()
        self.clipboard_append(text)
        self._flash(f"📋 {msg} ({len(text.splitlines())} lignes)")

    def _flash(self, msg: str):
        self.status.configure(text=msg, fg=self.C["ok"])
        self.after(2500, self._status)

    # ── boucle d'événements des fils ─────────────────────────────────────────
    def _poll(self):
        try:
            for _ in range(400):
                ev = self.q.get_nowait()
                kind = ev[0]
                if kind == "tok":
                    if not self.gen_first:
                        self.gen_first = time.time()
                    self.gen_tokens += 1
                    self.chat.configure(state="normal")
                    self.chat.insert("end", ev[1], "stream")
                    self.chat.configure(state="disabled")
                    self.chat.see("end")
                elif kind == "done":
                    self._gen_end(ev[1], cancelled=ev[2])
                elif kind == "gerr":
                    self._gen_end(ev[2], err=ev[1])
                elif kind == "out":
                    self._out_write(ev[1], "o_err" if ev[2] == "err" else None)
                elif kind == "exit":
                    self._run_exit(ev[1], ev[2])
                elif kind == "call":
                    ev[1](*ev[2:])
        except queue.Empty:
            pass
        except Exception as e:
            self.log(f"atelier poll: {e}")
        try:
            self.after(40, self._poll)
        except tk.TclError:
            pass

    # ── onglets et fichiers ──────────────────────────────────────────────────
    def cur(self) -> Optional[Tab]:
        try:
            w = self.nb.select()
        except tk.TclError:
            return None
        for t in self.tabs:
            if str(t.ed) == w:
                return t
        return None

    def _show_empty(self, on: bool):
        if on:
            self.empty.place(relx=0.5, rely=0.45, anchor="center")
        else:
            self.empty.place_forget()

    def add_tab(self, name: str, text: str = "", path: str = "", external: bool = False, dirty: bool = False) -> Tab:
        ed = CodeEditor(self.nb, path=path, name=name, text=text, theme=self.cfg.get("theme", "padawan"),
                        font_size=int(self.cfg.get("font_size") or 11), minimap=bool(self.cfg.get("minimap", True)),
                        on_change=lambda e: self._tab_title(e), on_cursor=lambda e: self._status())
        if dirty:
            ed.saved_text = ""
        self._keytags(ed.t)
        ed.t.bind("<Button-3>", self._ed_menu)
        tab = Tab(ed, path, external)
        self.tabs.append(tab)
        self.nb.add(ed, text=self._title_for(tab))
        self._show_empty(False)
        self.nb.select(ed)
        ed.t.focus_set()
        return tab

    def _title_for(self, tab: Tab) -> str:
        mark = " ●" if tab.ed.dirty() else ""
        return f"{'↗ ' if tab.external else ''}{tab.name}{mark}"

    def _tab_title(self, ed: CodeEditor):
        for t in self.tabs:
            if t.ed is ed:
                try:
                    self.nb.tab(ed, text=self._title_for(t))
                except tk.TclError:
                    pass
        self._status()

    def _tab_changed(self):
        self._status()
        self._find_mark()

    def _nb_middle(self, e):
        try:
            i = self.nb.index(f"@{e.x},{e.y}")
            self.nb.select(i)
            self.close_tab()
        except tk.TclError:
            pass

    def _nb_menu(self, e):
        try:
            i = self.nb.index(f"@{e.x},{e.y}")
            self.nb.select(i)
        except tk.TclError:
            return
        m = tk.Menu(self, tearoff=0)
        m.add_command(label="✏ Renommer…", command=self.rename_tab)
        m.add_command(label="📋 Copier tout le fichier", command=self.copy_file)
        m.add_command(label="📂 Ouvrir le dossier", command=self.open_folder)
        m.add_separator()
        m.add_command(label="✖ Fermer (Ctrl+W)", command=self.close_tab)
        m.tk_popup(e.x_root, e.y_root)

    def close_tab(self):
        t = self.cur()
        if not t:
            return
        if t.ed.dirty() and t.ed.get().strip():
            r = messagebox.askyesnocancel("Atelier", f"{t.name} n'est pas enregistré. L'enregistrer avant de fermer ?",
                                          parent=self)
            if r is None:
                return
            if r and not self.save_tab(t):
                return
        self.nb.forget(t.ed)
        t.ed.destroy()
        self.tabs.remove(t)
        if not self.tabs:
            self._show_empty(True)
        self._sync_project_files()
        self._status()

    def new_file(self):
        lang = self.cur().ed.lang if self.cur() else "python"
        name = simpledialog.askstring("Nouveau fichier", "Nom du fichier (avec l'extension : .py .html .css .js .php .ino …)",
                                      initialvalue=DEFAULT_NAME.get(lang, "script.py"), parent=self)
        name = safe_name(name or "")
        if not name:
            return
        if not os.path.splitext(name)[1]:
            name += ".py"
        if any(t.name.lower() == name.lower() for t in self.tabs):
            return self._flash("Un onglet porte déjà ce nom.")
        self.add_tab(name, "", dirty=True)

    def rename_tab(self):
        t = self.cur()
        if not t:
            return
        new = safe_name(simpledialog.askstring("Renommer", "Nouveau nom :", initialvalue=t.name, parent=self) or "")
        if not new or new == t.name:
            return
        if t.path and os.path.isfile(t.path) and not t.external:
            np_ = os.path.join(os.path.dirname(t.path), new)
            if os.path.exists(np_):
                return messagebox.showwarning("Atelier", "Ce nom existe déjà.", parent=self)
            os.replace(t.path, np_)
            t.path = t.ed.path = np_
        t.ed.set_lang_from_name(new)
        self._tab_title(t.ed)
        self._sync_project_files()

    def open_file(self):
        init = self.cfg.get("py_dir") or os.path.expanduser("~")
        p = filedialog.askopenfilename(parent=self, initialdir=init, title="Ouvrir un fichier dans l'Atelier",
                                       filetypes=[("Code", "*.py *.pyw *.html *.htm *.css *.js *.json *.php *.ino *.cpp *.h *.bat *.ps1 *.sql *.txt *.md"),
                                                  ("Tous", "*.*")])
        if p:
            self.open_path(p)

    def open_path(self, p: str):
        p = os.path.normpath(p)
        for t in self.tabs:
            if t.path and os.path.normcase(t.path) == os.path.normcase(p):
                self.nb.select(t.ed)
                return t
        try:
            if os.path.getsize(p) > 3_000_000:
                messagebox.showwarning("Atelier", "Fichier trop gros pour l'éditeur (> 3 Mo).", parent=self)
                return None
            txt = read_text(p)
        except Exception as e:
            messagebox.showerror("Atelier", f"Lecture impossible : {e}", parent=self)
            return None
        ext = not (self.project and os.path.normcase(os.path.dirname(p)) == os.path.normcase(self.project["dir"]))
        return self.add_tab(os.path.basename(p), txt, path=p, external=ext)

    def copy_file(self):
        t = self.cur()
        if t:
            self._clip(t.ed.get(), f"{t.name} copié en entier")

    def open_folder(self):
        t = self.cur()
        d = os.path.dirname(t.path) if t and t.path else (self.project or {}).get("dir", "")
        if d and os.path.isdir(d):
            try:
                os.startfile(d)  # type: ignore[attr-defined]
            except Exception:
                webbrowser.open("file:///" + d.replace("\\", "/"))

    # ── projets ──────────────────────────────────────────────────────────────
    def _proj_by_slug(self, slug: str) -> Optional[Dict[str, Any]]:
        return next((p for p in self.index.get("projects", []) if p.get("slug") == slug), None)

    def create_project(self, name: str) -> Dict[str, Any]:
        slug = base = slugify(name)
        n = 2
        while self._proj_by_slug(slug) or os.path.exists(os.path.join(self.ws, slug)):
            slug = f"{base}_{n}"
            n += 1
        d = os.path.join(self.ws, slug)
        os.makedirs(d, exist_ok=True)
        p = {"name": name.strip() or slug, "slug": slug, "dir": d, "files": [], "created": _now(), "updated": _now()}
        self.index.setdefault("projects", []).insert(0, p)
        self.index["last"] = slug
        self._save_index()
        self.project = p
        self.history = []
        self._proj_label()
        return p

    def _proj_label(self):
        p = self.project
        self.proj_lbl.configure(text=f"📁 {p['name']}" if p else "📁 (projet non nommé — 💾 pour le créer)")

    def _ensure_project(self) -> bool:
        if self.project:
            return True
        t = self.cur()
        sug = os.path.splitext(t.name)[0].replace("_", " ") if t else "Mon projet"
        name = simpledialog.askstring("Nouveau projet", "Nom de ce projet (pour le retrouver dans 📁 Projets) :",
                                      initialvalue=sug, parent=self)
        if not name or not name.strip():
            return False
        self.create_project(name.strip())
        return True

    def _sync_project_files(self):
        p = self.project
        if not p:
            return
        p["files"] = [t.name for t in self.tabs if not t.external and t.path]
        p["external"] = [t.path for t in self.tabs if t.external and t.path]
        c = self.cur()
        p["last_file"] = c.name if c else ""
        p["updated"] = _now()
        self.index["last"] = p["slug"]
        self._save_index()

    def open_project(self, p: Dict[str, Any]):
        for t in list(self.tabs):
            if t.ed.dirty() and t.ed.get().strip():
                self.nb.select(t.ed)
                r = messagebox.askyesnocancel("Atelier", f"Enregistrer {t.name} avant de changer de projet ?", parent=self)
                if r is None:
                    return
                if r:
                    self.save_tab(t)
        for t in list(self.tabs):
            self.nb.forget(t.ed)
            t.ed.destroy()
        self.tabs = []
        self.project = p
        self.index["last"] = p["slug"]
        self._save_index()
        d = p["dir"]
        names = p.get("files") or sorted(f for f in os.listdir(d) if os.path.isfile(os.path.join(d, f))) \
            if os.path.isdir(d) else []
        for n in names:
            fp = os.path.join(d, n)
            if os.path.isfile(fp):
                self.add_tab(n, read_text(fp), path=fp)
        for fp in p.get("external") or []:
            if os.path.isfile(fp):
                self.add_tab(os.path.basename(fp), read_text(fp), path=fp, external=True)
        last = p.get("last_file")
        for t in self.tabs:
            if t.name == last:
                self.nb.select(t.ed)
        self.history = []
        self._load_chat()
        self._proj_label()
        self._show_empty(not self.tabs)
        self._status()

    def _reopen_last(self):
        p = self._proj_by_slug(self.index.get("last", ""))
        self._proj_label()
        if p and os.path.isdir(p.get("dir", "")):
            try:
                self.open_project(p)
            except Exception as e:
                self.log(f"atelier reopen: {e}")
        else:
            self.say_sys("Bienvenue dans l'Atelier 💻 — demande du code (« fais-moi un menu ASCII en couleur »), "
                         "ou ✨ Nouveau pour partir d'un modèle. Le code arrive dans l'éditeur à droite.")

    def _chat_file(self) -> str:
        return os.path.join(self.project["dir"], ".atelier_chat.json") if self.project else ""

    def _save_chat(self):
        f = self._chat_file()
        if f:
            try:
                _savej(f, self.history[-30:])
            except Exception:
                pass

    def _load_chat(self):
        self.chat.configure(state="normal")
        self.chat.delete("1.0", "end")
        self.chat.configure(state="disabled")
        f = self._chat_file()
        h = _loadj(f, []) if f else []
        self.history = [x for x in h if isinstance(x, dict) and x.get("role") in ("user", "assistant")]
        if self.history:
            self.say_sys(f"📁 {self.project['name']} rouvert · {len(self.history)} message(s) précédents gardés en mémoire "
                         "(le modèle s'en souvient).")
            for x in self.history[-4:]:
                if x["role"] == "user":
                    self._chat_ins("Toi\n", "you")
                    self._chat_ins(x["content"][:600] + "\n\n", "youtxt")
                else:
                    self._chat_ins("Padawan\n", "ai")
                    self._render_answer(x["content"])
        else:
            self.say_sys(f"📁 {self.project['name']} ouvert.")

    def projects_dialog(self):
        C = self.C
        d = _dlg(self, C, "📁 Projets de l'Atelier", "760x460")
        cols = ("nom", "fichiers", "maj")
        tv = ttk.Treeview(d, columns=cols, show="headings", height=14)
        for c, lab, w in (("nom", "Projet", 260), ("fichiers", "Fichiers", 300), ("maj", "Modifié", 140)):
            tv.heading(c, text=lab)
            tv.column(c, width=w, anchor="w")
        bar = tk.Frame(d, bg=C["bg"])
        bar.pack(side="bottom", fill="x", padx=10, pady=8)
        tv.pack(fill="both", expand=True, padx=10, pady=(10, 0))
        projs = [p for p in self.index.get("projects", []) if os.path.isdir(p.get("dir", ""))]

        def fill():
            tv.delete(*tv.get_children())
            for p in sorted(projs, key=lambda x: x.get("updated", ""), reverse=True):
                tv.insert("", "end", iid=p["slug"], values=(p["name"], ", ".join(p.get("files") or [])[:80],
                                                            p.get("updated", "")[:16]))
        fill()

        def sel():
            s = tv.selection()
            return self._proj_by_slug(s[0]) if s else None

        def op(e=None):
            p = sel()
            if p:
                d.destroy()
                self.open_project(p)

        def ren():
            p = sel()
            if not p:
                return
            n = simpledialog.askstring("Renommer", "Nouveau nom du projet :", initialvalue=p["name"], parent=d)
            if n and n.strip():
                p["name"] = n.strip()
                self._save_index()
                fill()
                self._proj_label()

        def folder():
            p = sel()
            if p:
                try:
                    os.startfile(p["dir"])  # type: ignore[attr-defined]
                except Exception:
                    pass

        def forget():
            p = sel()
            if not p:
                return
            if not messagebox.askyesno("Atelier", f"Retirer « {p['name']} » de la liste ?\n"
                                       "Ses fichiers sont DÉPLACÉS dans le dossier bak (rien n'est effacé).", parent=d):
                return
            dst = os.path.join(self.bak_root, "projets_retires", f"{p['slug']}_{_stamp()}")
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            try:
                shutil.move(p["dir"], dst)
            except Exception as e:
                return messagebox.showerror("Atelier", str(e), parent=d)
            self.index["projects"] = [x for x in self.index["projects"] if x is not p]
            projs.remove(p)
            self._save_index()
            if self.project is p:
                self.project = None
                self._proj_label()
            fill()
        tv.bind("<Double-1>", op)
        _btn(bar, "📂 Ouvrir", op, C, kind="gold", big=True).pack(side="left")
        _btn(bar, "✏ Renommer", ren, C).pack(side="left", padx=4)
        _btn(bar, "🗂 Dossier", folder, C).pack(side="left")
        _btn(bar, "🗑 Retirer (→ bak)", forget, C, kind="bad").pack(side="left", padx=4)
        _btn(bar, "✨ Nouveau…", lambda: (d.destroy(), self.new_dialog()), C).pack(side="right")
        if not projs:
            tk.Label(d, text="Aucun projet pour l'instant — ✨ Nouveau.", bg=C["bg"], fg=C["dim"]).place(relx=.5, rely=.4,
                                                                                                         anchor="center")

    def new_dialog(self):
        C = self.C
        d = _dlg(self, C, "✨ Nouveau projet", "560x420")
        tk.Label(d, text="Nom du projet :", bg=C["bg"], fg=C["fg"], font=("Segoe UI", 10)).pack(anchor="w", padx=14, pady=(12, 2))
        nv = tk.StringVar(value="")
        e = tk.Entry(d, textvariable=nv, font=("Segoe UI", 12), bg=C["input"], fg=C["fg"], insertbackground=C["fg"],
                     relief="flat")
        e.pack(fill="x", padx=14, ipady=4)
        tk.Label(d, text="Partir de :", bg=C["bg"], fg=C["fg"], font=("Segoe UI", 10)).pack(anchor="w", padx=14, pady=(10, 2))
        choice = tk.StringVar(value="dos_menu")
        for key in TEMPLATE_ORDER + ["vide"]:
            lab = TEMPLATES[key]["title"] if key in TEMPLATES else "📄 Projet vide"
            tk.Radiobutton(d, text=lab, variable=choice, value=key, bg=C["bg"], fg=C["fg"], selectcolor=C["card"],
                           activebackground=C["bg"], activeforeground=C["gold"], font=("Segoe UI", 11),
                           anchor="w", command=lambda k=key: nv.set(nv.get() or TEMPLATES.get(k, {}).get("title", "Projet")
                                                                    .split(" ", 1)[-1].split(" (")[0])).pack(fill="x", padx=24)

        def go(e=None):
            key = choice.get()
            name = nv.get().strip() or (TEMPLATES[key]["title"].split(" ", 1)[-1].split(" (")[0] if key in TEMPLATES else "Projet")
            d.destroy()
            self.start_project(name, key)
        bar = tk.Frame(d, bg=C["bg"])
        bar.pack(side="bottom", fill="x", padx=14, pady=10)
        _btn(bar, "Annuler", d.destroy, C, big=True).pack(side="right")
        _btn(bar, "✨ Créer", go, C, kind="gold", big=True).pack(side="right", padx=6)
        e.bind("<Return>", go)
        e.focus_set()

    def start_project(self, name: str, template: str = "vide"):
        if self.project or self.tabs:
            for t in list(self.tabs):
                if t.ed.dirty() and t.ed.get().strip():
                    self.nb.select(t.ed)
                    r = messagebox.askyesnocancel("Atelier", f"Enregistrer {t.name} avant ?", parent=self)
                    if r is None:
                        return
                    if r:
                        self.save_tab(t)
            for t in list(self.tabs):
                self.nb.forget(t.ed)
                t.ed.destroy()
            self.tabs = []
        p = self.create_project(name)
        files = TEMPLATES.get(template, {}).get("files", {})
        for fn, txt in files.items():
            fp = os.path.join(p["dir"], fn)
            write_text(fp, txt)
            tab = self.add_tab(fn, txt, path=fp)
            self._snapshot(tab, txt, "modèle")
        self._sync_project_files()
        self._load_chat()
        if files:
            first = next(iter(files))
            self.say_sys(f"✨ « {name} » créé à partir de « {TEMPLATES[template]['title']} ». "
                         f"👁 Aperçu (F5) pour l'essayer" + (", 🖥 Console pour les couleurs." if first.endswith(".py") else "."))
        self._show_empty(not self.tabs)
        self._status()

    # ── enregistrement, versions ─────────────────────────────────────────────
    def save_current(self):
        t = self.cur()
        if t:
            self.save_tab(t)

    def save_tab(self, t: Tab) -> bool:
        text = t.ed.get()
        if not t.path:
            if not self._ensure_project():
                return False
            t.path = t.ed.path = os.path.join(self.project["dir"], t.name)
            if os.path.exists(t.path):
                old = read_text(t.path)
                if old != text:
                    ok = DiffDialog(self, self.C, old, text, f"{t.name} existe déjà dans le projet", mode="confirm").show()
                    if not ok:
                        t.path = t.ed.path = ""
                        return False
        try:
            if os.path.isfile(t.path):
                old = read_text(t.path)
                if old != text and t.external:
                    backup_file(t.path, self.bak_root, "fichiers_ouverts")
            write_text(t.path, text)
        except Exception as e:
            messagebox.showerror("Atelier", f"Enregistrement impossible : {e}", parent=self)
            return False
        t.ed.saved_text = text
        self._snapshot(t, text, "💾")
        self._tab_title(t.ed)
        self._sync_project_files()
        self._flash(f"💾 {t.name} enregistré · {t.path}")
        return True

    def _vdir(self, t: Tab) -> str:
        base = self.project["dir"] if self.project and not t.external else os.path.join(self.ws, "_fichiers_ouverts")
        key = t.name if not t.external else f"{slugify(os.path.dirname(t.path))}__{t.name}"
        return os.path.join(base, ".versions", key)

    def _snapshot(self, t: Tab, text: str, why: str):
        try:
            d = self._vdir(t)
            os.makedirs(d, exist_ok=True)
            vs = sorted(os.listdir(d))
            if vs:
                try:
                    if read_text(os.path.join(d, vs[-1])) == text:
                        return
                except Exception:
                    pass
            write_text(os.path.join(d, f"{_stamp()}_{slugify(why) or 'v'}.txt"), text)
            for old in vs[:-59]:
                try:
                    os.remove(os.path.join(d, old))
                except OSError:
                    pass
        except Exception as e:
            self.log(f"atelier snapshot: {e}")

    def versions_dialog(self):
        t = self.cur()
        if not t:
            return
        C = self.C
        d0 = self._vdir(t)
        vs = sorted(os.listdir(d0), reverse=True) if os.path.isdir(d0) else []
        d = _dlg(self, C, f"🕘 Versions de {t.name}", "860x520")
        if not vs:
            tk.Label(d, text="Pas encore de version : chaque 💾 et chaque correctif accepté en crée une.",
                     bg=C["bg"], fg=C["dim"], font=("Segoe UI", 10)).pack(pady=40)
            return
        lb = tk.Listbox(d, width=30, bg=C["panel"], fg=C["fg"], selectbackground=C["gold"], selectforeground="#1a1408",
                        font=("Consolas", 10), relief="flat", activestyle="none")
        lb.pack(side="left", fill="y", padx=(10, 4), pady=10)
        right = tk.Frame(d, bg=C["bg"])
        right.pack(side="left", fill="both", expand=True, padx=(0, 10), pady=10)
        info = tk.Label(right, text="", bg=C["bg"], fg=C["dim"], anchor="w")
        info.pack(fill="x")
        pv = tk.Text(right, wrap="none", bg="#11151c", fg=C["fg"], font=("Consolas", 9), relief="flat")
        pv.pack(fill="both", expand=True)
        pv.tag_configure("add", foreground="#9ff0b4")
        pv.tag_configure("del", foreground="#ff9aa2")
        for v in vs:
            ts, _, why = v[:-4].partition("_")
            try:
                lab = datetime.strptime(ts, "%Y%m%d-%H%M%S").strftime("%d/%m %H:%M:%S")
            except ValueError:
                lab = ts
            lb.insert("end", f"{lab}  {why}")

        def show(e=None):
            s = lb.curselection()
            if not s:
                return
            old = read_text(os.path.join(d0, vs[s[0]]))
            cur = t.ed.get()
            pv.delete("1.0", "end")
            diff = list(difflib.unified_diff(cur.split("\n"), old.split("\n"), "actuel", "version", lineterm="", n=2))
            info.configure(text=f"{len(old.splitlines())} lignes · différences avec le fichier actuel :"
                           if diff else "identique au fichier actuel")
            for ln in diff[2:]:
                pv.insert("end", ln + "\n", "add" if ln.startswith("+") else "del" if ln.startswith("-") else "")

        def restore():
            s = lb.curselection()
            if not s:
                return
            t.ed.set(read_text(os.path.join(d0, vs[s[0]])))
            self._flash("↩ Version restaurée dans l'éditeur (Ctrl+Z pour revenir, 💾 pour garder)")
            d.destroy()
        lb.bind("<<ListboxSelect>>", show)
        bar = tk.Frame(right, bg=C["bg"])
        bar.pack(fill="x", pady=(6, 0))
        _btn(bar, "↩ Restaurer cette version", restore, C, kind="gold", big=True).pack(side="right")
        lb.selection_set(0)
        show()

    # ── aperçu / exécution ───────────────────────────────────────────────────
    def _save_for_run(self, t: Tab) -> bool:
        if t.ed.dirty() or not t.path:
            return self.save_tab(t)
        return True

    def preview_current(self):
        t = self.cur()
        if not t:
            return
        if not self._save_for_run(t):
            return
        lang, d = t.ed.lang, os.path.dirname(t.path)
        if lang in ("html", "css", "js") and not (lang == "js" and not self._html_for(t)):
            target = t if lang == "html" else self._html_for(t)
            if not target:
                return self._flash("Pas de page .html dans ce dossier à afficher.")
            self.preview.start(d)
            self.preview.root = d
            url = self.preview.url(os.path.relpath(target.path if isinstance(target, Tab) else target, d))
            webbrowser.open(url)
            self._out_sys(f"👁 Aperçu : {url}  (se recharge tout seul à chaque 💾)")
            return
        if lang == "python":
            return self._run([find_python(), "-u", t.path], d, t, int(self.cfg.get("py_timeout") or 60))
        if lang == "js":
            node = find_tool("node")
            if node:
                return self._run([node, t.path], d, t, int(self.cfg.get("py_timeout") or 60))
        if lang == "php":
            php = find_php()
            if not php:
                return self._out_sys("PHP introuvable (XAMPP : C:\\xampp\\php\\php.exe). 🚀 Déployer vers le dossier Web local "
                                     "puis ouvre-le avec Apache.", err=True)
            if self.php_runner and self.php_runner.running():
                self.php_runner.stop()
            import socket
            s = socket.socket()
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
            s.close()
            self.php_runner = Runner(lambda x, k: self.q.put(("out", x, "out")), lambda c, dt: None)
            self.php_runner.start([php, "-S", f"127.0.0.1:{port}", "-t", d], d, timeout=0)
            url = f"http://127.0.0.1:{port}/" + os.path.relpath(t.path, d).replace("\\", "/")
            self.run_stop.configure(state="normal")
            self.after(700, lambda: webbrowser.open(url))
            self._out_sys(f"🐘 Serveur PHP local : {url}  (⏹ Stop pour l'arrêter · MySQL de XAMPP utilisable)")
            return
        if lang == "arduino":
            cli = find_tool("arduino-cli")
            if cli:
                return self._run([cli, "compile", "--fqbn", "arduino:avr:uno", d], d, t, 300)
            self._clip(t.ed.get(), "Sketch copié")
            return self._out_sys("🔌 Arduino : sketch copié — colle-le dans l'IDE Arduino (Ctrl+V) puis Téléverser. "
                                 "(arduino-cli non installé : pas de compilation ici.)")
        if lang in ("bat", "ps"):
            return self.console_current()
        if lang == "json":
            ok, msg = json_tool(self, self.C, t.ed.get())
            return self._out_sys("✅ JSON valide" if ok else "❌ " + msg, err=not ok)
        self._out_sys("Pas d'aperçu pour ce type de fichier.")

    def _html_for(self, t: Tab):
        d = os.path.dirname(t.path)
        for tt in self.tabs:
            if tt.ed.lang == "html" and tt.path and os.path.dirname(tt.path) == d:
                return tt
        for n in ("index.html", "index.htm"):
            if os.path.isfile(os.path.join(d, n)):
                return os.path.join(d, n)
        return None

    def console_current(self):
        t = self.cur()
        if not t or not self._save_for_run(t):
            return
        d = os.path.dirname(t.path)
        if t.ed.lang == "python":
            cmd = ["cmd", "/k", find_python(), t.path]
        elif t.ed.lang == "bat":
            cmd = ["cmd", "/k", t.path]
        elif t.ed.lang == "ps":
            cmd = ["powershell", "-NoExit", "-ExecutionPolicy", "Bypass", "-File", t.path]
        else:
            return self.preview_current()
        try:
            subprocess.Popen(cmd, cwd=d, env=clean_env(), creationflags=NEWCON)
            self._out_sys(f"🖥 Lancé dans une console : {t.name}")
        except Exception as e:
            self._out_sys(f"Console impossible : {e}", err=True)

    def _run(self, cmd: List[str], cwd: str, t: Tab, timeout: int):
        self.out_clear()
        self.run_tab = t
        self.last_err = ""
        self._stderr_buf = []
        self.fix_btn.configure(state="disabled")
        self.fix2_btn.pack_forget()
        self.pip_btn.pack_forget()
        t.ed.mark_error(0)
        self._out_sys(f"▶ {os.path.basename(cmd[-1])}   ({datetime.now():%H:%M:%S})")
        try:
            self.runner.start(cmd, cwd, timeout)
        except Exception as e:
            return self._out_sys(f"Lancement impossible : {e}", err=True)
        self.run_stop.configure(state="normal")
        self.out_lbl.configure(text=f"▶ {t.name} · en cours…", fg=self.C["gold"])
        self.stdin_ent.focus_set()

    def _send_stdin(self):
        s = self.stdin_var.get()
        self.stdin_var.set("")
        if self.runner.running():
            self._out_write(s + "\n", "o_sys")
            self.runner.write(s + "\n")

    def stop_run(self):
        self.runner.stop()
        if self.php_runner and self.php_runner.running():
            self.php_runner.stop()
            self._out_sys("⏹ Serveur PHP arrêté.")
            self.run_stop.configure(state="disabled")

    def _run_exit(self, code: int, dt: float):
        t = self.run_tab
        self.run_stop.configure(state="disabled")
        why = self.runner.killed
        err = "".join(getattr(self, "_stderr_buf", []))
        if why:
            self._out_sys(f"⏹ {why}", err=True)
        ok = code == 0 and not why
        self.out_lbl.configure(text=f"{'✔' if ok else '✖'} {t.name if t else ''} · code {code} · {dt:.1f} s",
                               fg=self.C["ok"] if ok else self.C["bad"])
        if not ok and (err.strip() or why) and t:
            self.last_err = (err.strip() or why)[-6000:]
            self.last_err_tab = t
            self.fix_btn.configure(state="normal")
            self.fix2_btn.pack(side="right", padx=2, pady=1)
            line = 0
            for m in re.finditer(r'File "([^"]+)", line (\d+)', err):
                if t.path and os.path.normcase(os.path.abspath(m.group(1))) == os.path.normcase(t.path):
                    line = int(m.group(2))
            if line:
                t.ed.mark_error(line)
            mm = re.search(r"ModuleNotFoundError: No module named '([\w.]+)'", err)
            if mm:
                mod = mm.group(1).split(".")[0]
                self._pip_mod = PIP_NAMES.get(mod, mod)
                self.pip_btn.configure(text=f"📦 pip install {self._pip_mod}")
                self.pip_btn.pack(side="right", padx=2, pady=1)

    def _out_write(self, s: str, tag: Optional[str] = None):
        o = self.out
        if tag == "o_err":
            self._stderr_buf = getattr(self, "_stderr_buf", [])
            self._stderr_buf.append(s)
        o.configure(state="normal")
        if tag:
            o.insert("end", s, tag)
            if tag == "o_err":
                for m in re.finditer(r'File "([^"]+)", line (\d+)', s):
                    pass
        else:
            self._ansi_insert(s)
        lines = int(o.index("end-1c").split(".")[0])
        if lines > 4000:
            o.delete("1.0", f"{lines - 3000}.0")
        o.configure(state="disabled")
        o.see("end")

    def _ansi_insert(self, s: str):
        o = self.out
        pos = 0
        tags = getattr(self, "_ansi_tags", ())
        for m in ANSI_RX.finditer(s):
            if m.start() > pos:
                o.insert("end", s[pos:m.start()], tags)
            pos = m.end()
            params, cmd = m.group(1), m.group(2)
            if cmd == "m":
                cur = list(tags)
                for p in (params.split(";") if params else ["0"]):
                    try:
                        n = int(p or 0)
                    except ValueError:
                        continue
                    if n == 0:
                        cur = []
                    elif n == 1:
                        cur.append("o_b")
                    elif n in ANSI_COL:
                        cur = [x for x in cur if not x.startswith("fg")] + [f"fg{n}"]
                    elif 40 <= n <= 47:
                        cur = [x for x in cur if not x.startswith("bg")] + [f"bg{n}"]
                    elif n == 39:
                        cur = [x for x in cur if not x.startswith("fg")]
                    elif n == 49:
                        cur = [x for x in cur if not x.startswith("bg")]
                tags = tuple(cur)
            elif cmd == "J" and params in ("2", "3"):
                o.delete("1.0", "end")
        if pos < len(s):
            o.insert("end", s[pos:], tags)
        self._ansi_tags = tags

    def _out_sys(self, msg: str, err: bool = False):
        self.out.configure(state="normal")
        self.out.insert("end", msg + "\n", "o_err" if err else "o_sys")
        self.out.configure(state="disabled")
        self.out.see("end")

    def out_clear(self):
        self.out.configure(state="normal")
        self.out.delete("1.0", "end")
        self.out.configure(state="disabled")
        self._ansi_tags = ()

    def _out_click(self, e):
        pass

    def pip_install(self):
        mod = getattr(self, "_pip_mod", "")
        if not mod:
            return
        if not messagebox.askyesno("📦 pip install", f"Installer le module « {mod} » pour Python\n{find_python()} ?\n\n"
                                   "(pip le télécharge depuis PyPI.)", parent=self):
            return
        self.pip_btn.pack_forget()
        t = self.run_tab or self.cur()
        self._run([find_python(), "-m", "pip", "install", mod], self.ws, t, 600)

    def fix_error(self):
        t = self.last_err_tab if self.last_err_tab in self.tabs else self.cur()
        if not t or not self.last_err:
            return self._flash("Pas d'erreur à corriger (lance d'abord 👁 Aperçu).")
        self.nb.select(t.ed)
        prompt = (f"Ce programme plante. Voici la sortie d'erreur :\n```text\n{self.last_err}\n```\n\n"
                  f"Voici le fichier complet :\n```{t.ed.lang} {t.name}\n{t.ed.get()}\n```\n\n"
                  "Trouve la cause, corrige-la et renvoie le fichier COMPLET corrigé (même nom de fichier). "
                  "Ensuite, en 2 puces : la cause, et ce que tu as changé.")
        self._chat_ins("Toi\n", "you")
        self._chat_ins(f"🩺 Corrige l'erreur de {t.name}\n{self.last_err.strip().splitlines()[-1][:200]}\n\n", "youtxt")
        self._generate(prompt, f"🩺 Corrige l'erreur de {t.name}", purpose="fix", tab=t)

    def modify_current(self):
        t = self.cur()
        if not t:
            return self._flash("Ouvre d'abord un fichier.")
        sel, a, b = t.ed.selection()
        what = ask_text(self, self.C, f"✏️ Modifier {t.name}",
                        "Décris le changement voulu (ex. « ajoute une option 5 qui affiche l'heure en gros », "
                        "« mets le fond en bleu DOS »)." + ("\n→ Seule la SÉLECTION sera modifiée." if sel else ""))
        if not what:
            return
        self._chat_ins("Toi\n", "you")
        self._chat_ins(f"✏️ {what}  ({t.name}{', sélection' if sel else ''})\n\n", "youtxt")
        if sel:
            prompt = (f"Voici le fichier {t.name} pour contexte :\n```{t.ed.lang} {t.name}\n{t.ed.get()}\n```\n\n"
                      f"Modifie UNIQUEMENT cet extrait :\n```{t.ed.lang}\n{sel}\n```\n\nChangement demandé : {what}\n\n"
                      "Renvoie SEULEMENT l'extrait modifié, complet, dans un seul bloc de code (pas le fichier entier).")
            self._generate(prompt, f"✏️ {what} (sélection de {t.name})", purpose="sel", tab=t, sel=(a, b),
                           extra={"title": "✏️ Modification de la sélection"})
        else:
            self.edit_request(what, t)  # v41.4 : SEARCH/REPLACE + garde-fou

    def quick_action(self, kind: str, label: str):
        t = self.cur()
        if not t:
            return self._flash("Ouvre d'abord un fichier.")
        sel, a, b = t.ed.selection()
        code = sel or t.ed.get()
        if not code.strip():
            return self._flash("Rien à traiter : le fichier est vide.")
        instr = next(i for l, k, i in QUICK_ACTIONS if l == label)
        scope = "cet extrait" if sel else f"le fichier {t.name}"
        if kind == "convert":
            to = simpledialog.askstring("🔁 Convertir", "Convertir en quel langage ? (ex. JavaScript, PHP, Python, Arduino C++)",
                                        parent=self)
            if not to:
                return
            instr = f"Convertis ce code en {to}, avec le même comportement. Donne le fichier complet avec un nom de fichier adapté."
            purpose = "convert"
        elif kind == "tests":
            purpose = "tests"
        elif kind == "explain":
            purpose = "explain"
        else:
            purpose = "sel" if sel else "edit"
        lang = t.ed.lang
        if purpose in ("edit",):
            prompt = f"{instr}\n\n```{lang} {t.name}\n{code}\n```\n\nRenvoie le fichier COMPLET (même nom)."
        elif purpose == "sel":
            prompt = (f"{instr}\n\nExtrait (tiré de {t.name}) :\n```{lang}\n{code}\n```\n\n"
                      "Renvoie SEULEMENT l'extrait modifié dans un seul bloc de code.")
        else:
            prompt = f"{instr}\n\n{scope.capitalize()} :\n```{lang} {t.name}\n{code}\n```"
        self._chat_ins("Toi\n", "you")
        self._chat_ins(f"{label} — {scope}\n\n", "youtxt")
        self._generate(prompt, f"{label} — {scope}", purpose=purpose, tab=t, sel=(a, b) if sel else None,
                       extra={"title": label})

    # ── déploiement ──────────────────────────────────────────────────────────
    def deploy_dialog(self):
        t = self.cur()
        if not t:
            return self._flash("Rien à déployer.")
        for tt in self.tabs:
            if tt.ed.dirty() and tt.ed.get().strip():
                if not self.save_tab(tt):
                    return
        C, cfg = self.C, self.cfg
        rem = cfg.get("remote", {})
        d = _dlg(self, C, "🚀 Déployer", "640x520")
        tk.Label(d, text="Où envoyer ?", bg=C["bg"], fg=C["gold"], font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=14, pady=(10, 4))
        dest = tk.StringVar(value="py" if t.ed.lang == "python" else "web")
        opts = [("py", f"🐍 Dossier Python : {cfg.get('py_dir') or '(à régler dans ⚙)'}"),
                ("web", f"🌐 Dossier Web local : {cfg.get('web_dir') or '(à régler dans ⚙)'}"),
                ("remote", f"🛰 Serveur {str(rem.get('proto', 'sftp')).upper()} : "
                           f"{(rem.get('user') + '@') if rem.get('user') else ''}{rem.get('host') or '(à régler dans ⚙)'}{rem.get('dir') or ''}")]
        sub = tk.StringVar()

        def dest_changed():
            k = dest.get()
            sub.set("" if k == "py" else (self.project or {}).get("slug", ""))
        for k, lab in opts:
            tk.Radiobutton(d, text=lab, variable=dest, value=k, command=dest_changed, bg=C["bg"], fg=C["fg"],
                           selectcolor=C["card"], activebackground=C["bg"], font=("Segoe UI", 10), anchor="w",
                           wraplength=600, justify="left").pack(fill="x", padx=24)
        dest_changed()
        r = tk.Frame(d, bg=C["bg"])
        r.pack(fill="x", padx=14, pady=(8, 2))
        tk.Label(r, text="Sous-dossier :", bg=C["bg"], fg=C["fg"]).pack(side="left")
        tk.Entry(r, textvariable=sub, bg=C["input"], fg=C["fg"], insertbackground=C["fg"], relief="flat",
                 font=("Consolas", 10), width=30).pack(side="left", padx=6, ipady=2)
        tk.Label(r, text="(vide = directement dans le dossier)", bg=C["bg"], fg=C["dim"], font=("Segoe UI", 8)).pack(side="left")
        tk.Label(d, text="Fichiers :", bg=C["bg"], fg=C["fg"]).pack(anchor="w", padx=14, pady=(8, 0))
        fv: Dict[str, tk.BooleanVar] = {}
        box = tk.Frame(d, bg=C["bg"])
        box.pack(fill="both", expand=True, padx=24)
        for tt in self.tabs:
            if tt.path:
                fv[tt.path] = tk.BooleanVar(value=(tt is t) or (t.ed.lang in ("html", "css", "js", "php")
                                                                and tt.ed.lang in ("html", "css", "js", "php", "json")))
                tk.Checkbutton(box, text=tt.name, variable=fv[tt.path], bg=C["bg"], fg=C["fg"], selectcolor=C["card"],
                               activebackground=C["bg"], anchor="w").pack(fill="x")
        bar = tk.Frame(d, bg=C["bg"])
        bar.pack(side="bottom", fill="x", padx=14, pady=10)

        def go():
            files = [(os.path.basename(p), read_text(p)) for p, v in fv.items() if v.get() and os.path.isfile(p)]
            if not files:
                return messagebox.showinfo("Atelier", "Coche au moins un fichier.", parent=d)
            k, s = dest.get(), sub.get().strip().strip("\\/")
            d.destroy()
            if k == "remote":
                self._deploy_remote(files, s)
            else:
                root = cfg.get("py_dir" if k == "py" else "web_dir") or ""
                if not root:
                    messagebox.showinfo("Atelier", "Règle d'abord ce dossier dans ⚙ Réglages.", parent=self)
                    return self.settings_dialog()
                self._deploy_local(files, os.path.join(root, s) if s else root, k)
        _btn(bar, "Annuler", d.destroy, C, big=True).pack(side="right")
        _btn(bar, "🚀 Vérifier et déployer", go, C, kind="gold", big=True).pack(side="right", padx=6)
        _btn(bar, "⚙ Réglages", lambda: (d.destroy(), self.settings_dialog()), C).pack(side="left")

    def _deploy_local(self, files, dest_dir: str, kind: str):
        plan = plan_files(files, dest_dir)
        changed = [x for x in plan if x["state"] == "modifié"]
        for x in changed:
            ok = DiffDialog(self, self.C, x["old"], x["new"], f"Écraser {x['path']} ?", mode="confirm",
                            subtitle="· une copie .bak sera gardée", ok_text="✅ Oui, écraser (copie .bak)").show()
            if not ok:
                x["state"] = "sauté"
        todo = [x for x in plan if x["state"] in ("nouveau", "modifié")]
        if not todo:
            return self._out_sys("🚀 Rien à copier (fichiers identiques ou sautés).")
        if kind == "web" and not messagebox.askyesno(
                "🚀 Dossier Web", f"Copier {len(todo)} fichier(s) dans\n{dest_dir} ?\n\n"
                "(Si ce dossier est servi par Apache, ce sera visible à son adresse.)", parent=self):
            return
        os.makedirs(dest_dir, exist_ok=True)
        for x in todo:
            b = backup_file(x["path"], self.bak_root, f"deploy_{kind}") if x["state"] == "modifié" else ""
            write_text(x["path"], x["new"])
            self._out_sys(f"🚀 {x['state']:>8} → {x['path']}" + (f"   (.bak : {b})" if b else ""))
        for x in plan:
            if x["state"] in ("identique", "sauté"):
                self._out_sys(f"   {x['state']:>8} · {x['name']}")
        url = self.cfg.get("web_url") or ""
        if kind == "web" and url:
            rel = os.path.relpath(dest_dir, self.cfg.get("web_dir") or dest_dir).replace("\\", "/")
            page = next((x["name"] for x in plan if x["name"].lower().endswith((".html", ".htm", ".php"))), "")
            full = url.rstrip("/") + "/" + ("" if rel == "." else rel + "/") + page
            self._out_sys(f"🌐 {full}")
            if page and messagebox.askyesno("Atelier", f"Ouvrir {full} ?", parent=self):
                webbrowser.open(full)
        self._flash(f"🚀 {len(todo)} fichier(s) déployé(s) → {dest_dir}")

    def _remote_password(self) -> str:
        return unprotect(self.cfg.get("remote", {}).get("password", ""))

    def _deploy_remote(self, files, sub: str):
        rem = dict(self.cfg.get("remote", {}))
        if not rem.get("host"):
            messagebox.showinfo("Atelier", "Règle d'abord le serveur dans ⚙ Réglages.", parent=self)
            return self.settings_dialog()
        where = f"{rem.get('proto', '').upper()} {rem.get('user')}@{rem.get('host')}:{(rem.get('dir') or '/').rstrip('/')}/{sub}"
        if not messagebox.askyesno("🛰 Déployer sur le serveur",
                                   f"Envoyer {len(files)} fichier(s) vers\n{where}\n\n" + "\n".join(f"• {n}" for n, _ in files) +
                                   "\n\nLes fichiers existants sont d'abord copiés en .bak sur ce PC.", parent=self):
            return
        self._out_sys(f"🛰 Connexion à {rem.get('host')}…")
        pw = self._remote_password()

        def work():
            r = Remote(rem, pw, self.known_hosts)
            try:
                r.connect()
                r.mkdirs(sub)
                for name, text in files:
                    rel = f"{sub}/{name}" if sub else name
                    old = r.get(rel)
                    data = text.encode("utf-8")
                    if old is not None and old == data:
                        self.q.put(("call", self._out_sys, f"   identique · {name}"))
                        continue
                    b = backup_bytes(old, name, self.bak_root, f"deploy_remote_{rem.get('host')}") if old is not None else ""
                    r.put(rel, data)
                    self.q.put(("call", self._out_sys, f"🛰 {'modifié' if old is not None else 'nouveau'} → {rel}"
                                + (f"   (.bak : {b})" if b else "")))
                self.q.put(("call", self._out_sys, "✅ Déploiement terminé."))
                url = rem.get("url") or ""
                if url:
                    self.q.put(("call", self._out_sys, "🌐 " + url.rstrip("/") + "/" + (sub + "/" if sub else "")))
            except NewHostKey as k:
                self.q.put(("call", self._out_sys, f"🔐 Serveur inconnu ({k.keytype} {k.fp}) : va dans ⚙ → 🔌 Tester "
                                                   "pour vérifier et accepter son empreinte.", True))
            except Exception as e:
                self.q.put(("call", self._out_sys, f"❌ Déploiement : {e}", True))
            finally:
                r.close()
        threading.Thread(target=work, daemon=True).start()

    # ── réglages ─────────────────────────────────────────────────────────────
    def settings_dialog(self):
        C, cfg = self.C, self.cfg
        rem = cfg.setdefault("remote", {})
        d = _dlg(self, C, "⚙ Réglages de l'Atelier", "700x620")
        bar = tk.Frame(d, bg=C["bg"])
        bar.pack(side="bottom", fill="x", padx=14, pady=8)
        f = tk.Frame(d, bg=C["bg"])
        f.pack(fill="both", expand=True, padx=14, pady=(6, 0))
        f.columnconfigure(1, weight=1)
        vars_: Dict[str, tk.Variable] = {}
        row = [0]

        def head(txt):
            tk.Label(f, text=txt, bg=C["bg"], fg=C["gold"], font=("Segoe UI", 10, "bold")).grid(
                row=row[0], column=0, columnspan=3, sticky="w", pady=(5, 1))
            row[0] += 1

        def field(key, label, val, browse=False, show="", note=""):
            tk.Label(f, text=label, bg=C["bg"], fg=C["fg"]).grid(row=row[0], column=0, sticky="w", padx=(8, 6))
            v = tk.StringVar(value=str(val if val is not None else ""))
            e = tk.Entry(f, textvariable=v, bg=C["input"], fg=C["fg"], insertbackground=C["fg"], relief="flat",
                         font=("Consolas", 10), show=show)
            e.grid(row=row[0], column=1, sticky="ew", ipady=2, pady=1)
            if browse:
                _btn(f, "…", lambda: v.set(filedialog.askdirectory(parent=d, initialdir=v.get() or "C:\\") or v.get()),
                     C).grid(row=row[0], column=2, padx=4)
            vars_[key] = v
            row[0] += 1
            if note:
                tk.Label(f, text=note, bg=C["bg"], fg=C["dim"], font=("Segoe UI", 8)).grid(row=row[0], column=1,
                                                                                          sticky="w")
                row[0] += 1
        head("🐍 Python")
        field("py_dir", "Dossier Python", cfg.get("py_dir"), True)
        field("py_timeout", "Arrêt si muet (s)", cfg.get("py_timeout", 60), note="arrête un programme sans sortie ni saisie depuis N s · 0 = jamais")
        head("🌐 Web local")
        field("web_dir", "Dossier Web", cfg.get("web_dir"), True,
              note="ex. C:\\web\\atelier (Apache XAMPP sert C:\\web) — attention : public si ton site l'est")
        field("web_url", "Adresse de ce dossier", cfg.get("web_url"))
        head("🛰 Serveur distant")
        tk.Label(f, text="Protocole", bg=C["bg"], fg=C["fg"]).grid(row=row[0], column=0, sticky="w", padx=(8, 6))
        pv = tk.StringVar(value=rem.get("proto", "sftp"))
        pr = tk.Frame(f, bg=C["bg"])
        pr.grid(row=row[0], column=1, sticky="w")
        for val, lab in (("sftp", "SFTP (SSH, conseillé)"), ("ftps", "FTPS (TLS)"), ("ftp", "FTP (non chiffré)")):
            tk.Radiobutton(pr, text=lab, variable=pv, value=val, bg=C["bg"], fg=C["fg"], selectcolor=C["card"],
                           activebackground=C["bg"], activeforeground=C["gold"]).pack(side="left", padx=(0, 8))
        vars_["proto"] = pv
        row[0] += 1
        field("host", "Hôte", rem.get("host"))
        field("port", "Port (0 = défaut)", rem.get("port", 0))
        field("user", "Utilisateur", rem.get("user"))
        has_pw = bool(rem.get("password"))
        field("password", "Mot de passe", "", show="•",
              note=("🔒 enregistré, chiffré Windows (DPAPI) — laisse vide pour le garder" if has_pw else
                    "🔒 sera chiffré avec ta session Windows (DPAPI), jamais en clair"))
        field("dir", "Dossier distant", rem.get("dir", "/"))
        field("url", "Adresse web du dossier", rem.get("url"))
        head("🎨 Éditeur")
        tk.Label(f, text="Taille de police", bg=C["bg"], fg=C["fg"]).grid(row=row[0], column=0, sticky="w", padx=(8, 6))
        er = tk.Frame(f, bg=C["bg"])
        er.grid(row=row[0], column=1, sticky="w")
        fsv = tk.StringVar(value=str(cfg.get("font_size", 11)))
        tk.Spinbox(er, from_=7, to=28, textvariable=fsv, width=4, bg=C["input"], fg=C["fg"], buttonbackground=C["card"],
                   relief="flat", font=("Consolas", 10)).pack(side="left")
        vars_["font_size"] = fsv
        mmv = tk.BooleanVar(value=bool(cfg.get("minimap", True)))
        tk.Checkbutton(er, text="Mini-carte à droite de l'éditeur", variable=mmv, bg=C["bg"], fg=C["fg"],
                       selectcolor=C["card"], activebackground=C["bg"]).pack(side="left", padx=12)
        row[0] += 1
        info = tk.Label(f, text=f"Réglages : {self.cfg_path}", bg=C["bg"], fg=C["dim"], font=("Segoe UI", 8),
                        wraplength=600, justify="left")
        info.grid(row=row[0], column=0, columnspan=3, sticky="w", pady=(6, 0))

        def collect() -> Tuple[Dict[str, Any], str]:
            r = dict(rem)
            r.update({"proto": pv.get(), "host": vars_["host"].get().strip(), "user": vars_["user"].get().strip(),
                      "dir": vars_["dir"].get().strip() or "/", "url": vars_["url"].get().strip()})
            try:
                r["port"] = int(vars_["port"].get() or 0)
            except ValueError:
                r["port"] = 0
            return r, vars_["password"].get()

        def test():
            r, pw = collect()
            pw = pw or unprotect(rem.get("password", ""))
            info.configure(text="🔌 Test en cours… (lecture seule : rien n'est écrit sur le serveur)", fg=C["gold"])

            def work():
                try:
                    msg = Remote(r, pw, self.known_hosts).test()
                    self.q.put(("call", info.configure, {"text": msg, "fg": C["ok"]}))
                except NewHostKey as k:
                    self.q.put(("call", self._trust_key, k, r, pw, info))
                except Exception as e:
                    self.q.put(("call", info.configure, {"text": f"❌ {e}", "fg": C["bad"]}))
            threading.Thread(target=work, daemon=True).start()

        def save():
            r, pw = collect()
            if pw:
                r["password"] = protect(pw)
            r.pop("_trust_fp", None)
            cfg["remote"] = r
            cfg["py_dir"] = vars_["py_dir"].get().strip()
            cfg["web_dir"] = vars_["web_dir"].get().strip()
            cfg["web_url"] = vars_["web_url"].get().strip()
            for k, lo, hi, dflt in (("py_timeout", 0, 3600, 60), ("font_size", 7, 28, 11)):
                try:
                    cfg[k] = max(lo, min(hi, int(vars_[k].get())))
                except ValueError:
                    cfg[k] = dflt
            cfg["minimap"] = bool(mmv.get())
            self._save_cfg()
            for t in self.tabs:
                t.ed.apply_theme(cfg.get("theme", "padawan"), cfg["font_size"])
                if cfg["minimap"] and not t.ed.mm.winfo_ismapped():
                    t.ed.mm.pack(side="right", fill="y", before=t.ed.t)
                elif not cfg["minimap"]:
                    t.ed.mm.pack_forget()
            d.destroy()
            self._flash("⚙ Réglages enregistrés")
        _btn(bar, "Annuler", d.destroy, C, big=True).pack(side="right")
        _btn(bar, "💾 Enregistrer", save, C, kind="gold", big=True).pack(side="right", padx=6)
        _btn(bar, "🔌 Tester la connexion", test, C, kind="cyan").pack(side="left")
        _btn(bar, "🗑 Oublier le mot de passe", lambda: (rem.__setitem__("password", ""), self._save_cfg(),
                                                       info.configure(text="Mot de passe effacé.")), C).pack(side="left", padx=4)

    def _trust_key(self, k: "NewHostKey", r: Dict[str, Any], pw: str, info):
        if messagebox.askyesno("🔐 Nouveau serveur SFTP",
                               f"Première connexion à {k.host}.\nEmpreinte {k.keytype} :\n{k.fp}\n\n"
                               "Si elle correspond à ton serveur, accepte-la (elle sera retenue).", parent=self):
            r = dict(r)
            r["_trust_fp"] = k.fp

            def work():
                try:
                    msg = Remote(r, pw, self.known_hosts).test()
                    self.q.put(("call", info.configure, {"text": msg + " · empreinte retenue", "fg": self.C["ok"]}))
                except Exception as e:
                    self.q.put(("call", info.configure, {"text": f"❌ {e}", "fg": self.C["bad"]}))
            threading.Thread(target=work, daemon=True).start()
        else:
            info.configure(text="Connexion refusée (empreinte non acceptée).", fg=self.C["bad"])

    # ── menus outils / snippets ──────────────────────────────────────────────
    def _fill_snippets(self):
        m = self.snip_menu
        m.delete(0, "end")
        t = self.cur()
        lang = t.ed.lang if t else "python"
        lang = {"ps": "python", "bat": "python", "json": "js", "text": "python", "sql": "php"}.get(lang, lang)
        m.add_command(label=f"— {LANG_LABEL.get(lang, lang)} —", state="disabled")
        for lab, code in SNIPPETS.get(lang, []):
            m.add_command(label=lab, command=lambda c=code: self.insert_snippet(c))
        m.add_separator()
        for lg, items in SNIPPETS.items():
            if lg == lang:
                continue
            sm = tk.Menu(m, tearoff=0)
            for lab, code in items:
                sm.add_command(label=lab, command=lambda c=code: self.insert_snippet(c))
            m.add_cascade(label=LANG_LABEL.get(lg, lg), menu=sm)

    def insert_snippet(self, code: str):
        t = self.cur()
        if not t:
            t = self.add_tab(DEFAULT_NAME.get(guess_lang(code), "script.py"), "", dirty=True)
        ed = t.ed
        ind = re.match(r"[ \t]*", ed.t.get("insert linestart", "insert")).group(0)
        if ind and ed.t.get("insert linestart", "insert").strip() == "":
            code = code.replace("\n", "\n" + ind)
        ed.t.edit_separator()
        ed.t.insert("insert", code)
        ed.t.edit_separator()
        ed.t.focus_set()

    def _fill_tools(self):
        m = self.tools_menu
        m.delete(0, "end")
        m.add_command(label="🔍 Rechercher            Ctrl+F", command=lambda: self.find_show(False))
        m.add_command(label="🔁 Rechercher / remplacer  Ctrl+H", command=lambda: self.find_show(True))
        m.add_command(label="➡ Aller à la ligne…       Ctrl+G", command=self.goto_line)
        m.add_command(label="💬 Commenter / décommenter  Ctrl+/", command=lambda: self.cur() and self.cur().ed.toggle_comment())
        m.add_separator()
        m.add_command(label="🧪 Testeur d'expressions régulières", command=self.regex_tool)
        m.add_command(label="🧾 JSON : valider et mettre en forme", command=self.json_format)
        m.add_command(label="🎨 Choisir une couleur (insère #rrggbb)", command=self.color_pick)
        m.add_command(label="🖼→ANSI : image en art ANSI / ASCII…", command=self.ansi_studio)
        m.add_command(label="📊 Statistiques du fichier", command=self.stats_dialog)
        m.add_separator()
        m.add_command(label="📦 Exporter le projet en .zip…", command=self.export_zip)
        git = find_git()
        if git:
            m.add_command(label="🔧 git init + commit du projet", command=self.git_commit)
        else:
            m.add_command(label="🔧 git (non installé sur ce PC)", state="disabled")
        m.add_command(label="🗂 Ouvrir le dossier du fichier", command=self.open_folder)
        m.add_separator()
        m.add_command(label="🟦 Thème DOS / Padawan", command=self.toggle_theme)
        m.add_command(label="A+  Police plus grande", command=lambda: self._font(1))
        m.add_command(label="A−  Police plus petite", command=lambda: self._font(-1))

    # ── v40.1 🖼→ANSI ────────────────────────────────────────────────────────
    def ansi_studio(self, path: str = ""):
        """Ouvre (ou ramène) la fenêtre 🖼→ANSI. Retourne l'objet AnsiStudio (ou None)."""
        if _ANSI is None:
            messagebox.showwarning("🖼→ANSI", "Module padawan_ansi.py introuvable à côté de Padawan.", parent=self)
            return None
        s = getattr(self, "_ansi_win", None)
        if s is not None and s.exists():
            try:
                s.d.deiconify()
                s.d.lift()
                s.d.focus_force()
            except Exception:
                pass
            if path:
                s.load_path(path)
            return s

        def cur_dir() -> str:
            t = self.cur()
            if t and t.path:
                return os.path.dirname(t.path)
            return self.ws

        hooks = {"pip": self._pip_module, "new_tab": lambda name, text: self.add_tab(name, text, dirty=True),
                 "insert": self._ansi_to_tab, "default_dir": cur_dir, "python": find_python, "env": clean_env,
                 "flash": self._flash, "log": self.log}
        try:
            self._ansi_win = _ANSI.AnsiStudio(self, self.C, cfg=self.cfg, save_cfg=self._save_cfg,
                                              workdir=os.path.join(self.ws, "_ansi"), hooks=hooks, path=path)
        except Exception as e:
            self.log(f"ansi: {e}")
            messagebox.showerror("🖼→ANSI", f"Ouverture impossible : {e}", parent=self)
            return None
        return self._ansi_win

    def _ansi_to_tab(self, art) -> str:
        t = self.cur()
        lang = t.ed.lang if t else ""
        if lang == "python":
            code, what = art.to_python(), "code Python (print en couleurs)"
        elif lang in ("html", "php"):
            code, what = art.to_html(fragment=True), "<pre> HTML coloré"
        else:
            code, what = art.to_text(), "texte"
        self.insert_snippet(code)
        t = self.cur()
        return what + (f" → {t.name}" if t else "")

    def _pip_module(self, mod: str):
        """pip install <mod> (même chemin que le bouton 📦 de l'Atelier, avec confirmation)."""
        self._pip_mod = mod
        if not (self.run_tab or self.cur()):
            self.add_tab(f"installer_{mod}.txt", f"Installation du module {mod} pour Python (pip)…\n"
                         "La sortie s'affiche en bas. Ensuite, rouvre l'outil.\n", dirty=False)
        self.pip_install()

    def _font(self, d: int):
        self.cfg["font_size"] = max(7, min(28, int(self.cfg.get("font_size") or 11) + d))
        self._save_cfg()
        for t in self.tabs:
            t.ed.apply_theme(self.cfg.get("theme", "padawan"), self.cfg["font_size"])

    def toggle_theme(self):
        self.cfg["theme"] = "padawan" if self.cfg.get("theme") == "dos" else "dos"
        self._save_cfg()
        for t in self.tabs:
            t.ed.apply_theme(self.cfg["theme"])
        if self.cfg["theme"] == "dos":
            self.out.configure(bg="#000000", fg="#aaaaaa")
        else:
            self.out.configure(bg="#0c0c0c", fg="#cccccc")
        self._set_theme_btn()

    def _set_theme_btn(self):
        self.theme_btn.configure(text="🎨 Padawan" if self.cfg.get("theme") == "dos" else "🟦 DOS")

    def regex_tool(self):
        t = self.cur()
        sel = t.ed.selection()[0] if t else ""
        RegexTester(self, self.C, sel)

    def json_format(self):
        t = self.cur()
        if not t:
            return
        sel, a, b = t.ed.selection()
        ok, res = json_tool(self, self.C, sel or t.ed.get())
        if not ok:
            m = re.search(r"ligne (\d+)", res)
            if m and not sel:
                t.ed.mark_error(int(m.group(1)))
            return messagebox.showwarning("JSON", res, parent=self)
        if sel:
            t.ed._begin()
            t.ed.t.delete(a, b)
            t.ed.t.insert(a, res)
            t.ed._end()
        else:
            t.ed.set(res)
        self._flash("🧾 JSON valide, mis en forme (Ctrl+Z pour annuler)")

    def color_pick(self):
        t = self.cur()
        rgb, hx = colorchooser.askcolor(parent=self, title="🎨 Couleur")
        if hx:
            if t:
                t.ed.t.insert("insert", hx)
            self._clip(hx, f"Couleur {hx}")

    def stats_dialog(self):
        t = self.cur()
        if not t:
            return
        s = t.ed.stats()
        size = len(t.ed.get().encode("utf-8"))
        messagebox.showinfo("📊 Statistiques", f"{t.name}  ({LANG_LABEL.get(t.ed.lang, t.ed.lang)})\n\n"
                            f"Lignes : {s['lines']}  (code : {s['code']}, commentaires : {s['comments']})\n"
                            f"Caractères : {s['chars']}  ·  {size / 1024:.1f} Ko\n"
                            f"Fonctions : {s['funcs']}  ·  TODO/FIXME : {s['todo']}", parent=self)

    def export_zip(self):
        if not self.project:
            return self._flash("Enregistre d'abord le projet (💾).")
        for tt in self.tabs:
            if tt.ed.dirty() and tt.ed.get().strip():
                self.save_tab(tt)
        dl = os.path.join(os.path.expanduser("~"), "Downloads")
        p = filedialog.asksaveasfilename(parent=self, initialdir=dl if os.path.isdir(dl) else None,
                                         initialfile=f"{self.project['slug']}_{datetime.now():%Y%m%d}.zip",
                                         defaultextension=".zip", filetypes=[("Zip", "*.zip")])
        if not p:
            return
        n = 0
        with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
            for dp, dn, fn in os.walk(self.project["dir"]):
                dn[:] = [x for x in dn if not x.startswith(".")]
                for f in fn:
                    if f.startswith(".atelier"):
                        continue
                    fp = os.path.join(dp, f)
                    z.write(fp, os.path.join(self.project["slug"], os.path.relpath(fp, self.project["dir"])))
                    n += 1
            for tt in self.tabs:
                if tt.external and tt.path and os.path.isfile(tt.path):
                    z.write(tt.path, os.path.join(self.project["slug"], "externes", tt.name))
                    n += 1
        self._out_sys(f"📦 {n} fichier(s) → {p}")

    def git_commit(self):
        git = find_git()
        if not git or not self.project:
            return
        msg = simpledialog.askstring("git commit", "Message du commit :", initialvalue=f"Atelier {datetime.now():%Y-%m-%d %H:%M}",
                                     parent=self)
        if not msg:
            return
        d = self.project["dir"]
        gi = os.path.join(d, ".gitignore")
        if not os.path.exists(gi):
            write_text(gi, ".versions/\n.atelier_chat.json\n__pycache__/\n")
        cmds = ([] if os.path.isdir(os.path.join(d, ".git")) else [[git, "init"]]) + \
            [[git, "add", "-A"], [git, "-c", "user.name=Marc", "-c", "user.email=marc@localhost", "commit", "-m", msg]]

        def work():
            for c in cmds:
                r = subprocess.run(c, cwd=d, capture_output=True, text=True, creationflags=NOWIN)
                self.q.put(("call", self._out_sys, f"$ {' '.join(c[1:2] + c[-2:] if 'commit' in c else c[1:])}\n"
                            + (r.stdout + r.stderr).strip(), r.returncode != 0))
        threading.Thread(target=work, daemon=True).start()

    # ── recherche ────────────────────────────────────────────────────────────
    def find_show(self, replace: bool):
        t = self.cur()
        if not getattr(self, "_find_on", False):
            self.findbar.pack(side="top", fill="x", before=self.nb)
        self._find_on = True
        if replace:
            self.repl_frame.pack(side="left", padx=4, after=self.find_ent.master.winfo_children()[3])
        else:
            self.repl_frame.pack_forget()
        if t:
            s = t.ed.selection()[0]
            if s and "\n" not in s:
                self.find_var.set(s)
        self.find_ent.focus_set()
        self.find_ent.select_range(0, "end")
        self._find_mark()

    def find_hide(self):
        self._find_on = False
        self.findbar.pack_forget()
        for t in self.tabs:
            t.ed.t.tag_remove("found", "1.0", "end")
        t = self.cur()
        if t:
            t.ed.t.focus_set()

    def _find_rx(self):
        pat = self.find_var.get()
        if not pat:
            return None
        fl = 0 if self.find_case.get() else re.I
        try:
            return re.compile(pat if self.find_rx.get() else re.escape(pat), fl | re.M)
        except re.error:
            return None

    def _find_mark(self):
        t = self.cur()
        if not t:
            return
        t.ed.t.tag_remove("found", "1.0", "end")
        if not getattr(self, "_find_on", False):
            return
        rx = self._find_rx()
        if not rx:
            self.find_info.configure(text="" if not self.find_var.get() else "motif invalide")
            return
        txt = t.ed.get()
        n = 0
        for m in rx.finditer(txt):
            if m.end() == m.start():
                continue
            n += 1
            if n <= 3000:
                t.ed.t.tag_add("found", f"1.0+{m.start()}c", f"1.0+{m.end()}c")
        self.find_info.configure(text=f"{n} trouvé(s)")

    def find_next(self, d: int = 1):
        t = self.cur()
        rx = self._find_rx()
        if not t or not rx:
            return
        txt = t.ed.get()
        ins = len(t.ed.t.get("1.0", "insert"))
        ms = [m for m in rx.finditer(txt) if m.end() > m.start()]
        if not ms:
            return
        if d > 0:
            m = next((x for x in ms if x.start() >= ins), ms[0])
        else:
            m = next((x for x in reversed(ms) if x.end() < ins), ms[-1])
        a, b = f"1.0+{m.start()}c", f"1.0+{m.end()}c"
        e = t.ed.t
        e.tag_remove("sel", "1.0", "end")
        e.tag_add("sel", a, b)
        e.mark_set("insert", b if d > 0 else a)
        e.see(a)
        t.ed._cursor_moved()

    def replace_one(self):
        t = self.cur()
        rx = self._find_rx()
        if not t or not rx:
            return
        s, a, b = t.ed.selection()
        if s and rx.fullmatch(s):
            rep = rx.sub(self.repl_var.get(), s, count=1) if self.find_rx.get() else self.repl_var.get()
            t.ed._begin()
            t.ed.t.delete(a, b)
            t.ed.t.insert(a, rep)
            t.ed._end()
        self.find_next(1)
        self._find_mark()

    def replace_all(self):
        t = self.cur()
        rx = self._find_rx()
        if not t or not rx:
            return
        txt = t.ed.get()
        rep = self.repl_var.get()
        new, n = (rx.subn(rep, txt) if self.find_rx.get() else rx.subn(lambda m: rep, txt))
        if n:
            t.ed.set(new)
        self.find_info.configure(text=f"{n} remplacé(s) · Ctrl+Z pour annuler")

    def goto_line(self):
        t = self.cur()
        if not t:
            return
        n = simpledialog.askinteger("Aller à la ligne", "Numéro de ligne :", parent=self, minvalue=1,
                                    maxvalue=max(1, t.ed.stats()["lines"]))
        if n:
            t.ed.goto(n)

    def _esc(self, e=None):
        if getattr(self, "_find_on", False):
            self.find_hide()
            return "break"
        return "break"

    # ── menu clic droit de l'éditeur ─────────────────────────────────────────
    def _ed_menu(self, e):
        t = self.cur()
        if not t:
            return
        w = t.ed.t
        m = tk.Menu(self, tearoff=0)
        m.add_command(label="Couper", accelerator="Ctrl+X", command=lambda: w.event_generate("<<Cut>>"))
        m.add_command(label="Copier", accelerator="Ctrl+C", command=lambda: w.event_generate("<<Copy>>"))
        m.add_command(label="Coller", accelerator="Ctrl+V", command=lambda: w.event_generate("<<Paste>>"))
        m.add_command(label="Tout sélectionner", accelerator="Ctrl+A", command=t.ed.select_all)
        m.add_separator()
        m.add_command(label="📋 Copier tout le fichier", command=self.copy_file)
        m.add_command(label="💬 Commenter / décommenter", accelerator="Ctrl+/", command=t.ed.toggle_comment)
        m.add_command(label="⧉ Dupliquer la ligne", accelerator="Ctrl+D", command=t.ed.dup_line)
        m.add_separator()
        for lab, kind, _ in QUICK_ACTIONS:
            m.add_command(label=lab + (" (sélection)" if w.tag_ranges("sel") else " (fichier)"),
                          command=lambda k=kind, l=lab: self.quick_action(k, l))
        m.add_command(label="✏️ Modifier avec l'IA…", accelerator="Ctrl+E", command=self.modify_current)
        m.tk_popup(e.x_root, e.y_root)
        return "break"

    # ── barre d'état ─────────────────────────────────────────────────────────
    def _status(self):
        t = self.cur()
        if not t:
            self.status.configure(text="Aucun fichier · ✨ Nouveau ou demande du code dans le chat", fg=self.C["dim"])
            return
        ln, col = t.ed.t.index("insert").split(".")
        n = int(t.ed.t.index("end-1c").split(".")[0])
        st = "● non enregistré" if t.ed.dirty() else "✔ enregistré"
        where = t.path or "(pas encore enregistré)"
        self.status.configure(text=f"Ln {ln}, Col {int(col) + 1}   ·   {n} lignes   ·   {LANG_LABEL.get(t.ed.lang, t.ed.lang)}"
                                   f"   ·   UTF-8   ·   {st}   ·   {where}", fg=self.C["dim"])
