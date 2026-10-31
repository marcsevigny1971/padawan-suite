# -*- coding: utf-8 -*-
"""
Archiveur — conserver localement posts X / Facebook / YouTube (média + texte).
APP_FILE_VER = 5 ; titre fenêtre « Archiveur » sans numéro.
v5: LECTEUR INTÉGRÉ dans l'aperçu (ffmpeg → images + ffplay pour le son, synchro sur l'horloge
    audio ; lecture/pause, ±10 s, barre de position, volume, plein écran ffplay), TRANSCRIPTION
    horodatée cliquable (sous-titres yt-dlp FR/EN, option faster-whisper locale), OUTILS MÉDIA
    (capture, extrait mp4 sans ré-encodage, mp3, GIF → dossier extraits/), PAGES WEB complètes
    (HTML autonome + images, version lecture, texte, liens, capture PNG + PDF pleine page via
    Edge/Chrome headless), posts X (texte, photos, vidéo, fil parent via fxtwitter), FAVORIS et
    COLLECTIONS (filtres app + index global), EXPORT ZIP / CSV / JSON, résumé copiable,
    VÉRIFICATION d'intégrité + réparation, statut EN LIGNE du lien original (🟢/🔴/🟠),
    thèmes Norton/Sombre/Clair + taille de police (Ctrl+molette), multi-sélection et actions
    en lot, statistiques, aide F1, mise à jour yt-dlp, glisser-déposer (tkinterdnd2 optionnel),
    sauvegarde automatique de l'index (rotation), instance unique.
v4.1 (retouches, même fichier v4) : vidéos MP4 compatibles Windows (H.264 + AAC
    préférés à l'archivage, conversion ffmpeg auto si AV1/VP9/Opus, « Convertir en
    MP4 compatible » + « Réparer codecs » + CLI --fix-codecs), lecteur au choix
    (Windows / VLC / mpv détectés), mise en page responsive (barres qui passent à
    la ligne, historique adaptatif, actions sur 2 lignes), file d'attente repliable,
    bandeau codec, infobulles, états des boutons, Ctrl+V global, tests --geometry/--shot.
v4: APERÇU convivial et défilant (barre verticale + molette) : grande miniature
    redimensionnée (clic = lire), storyboard ffmpeg (6 images), carte d'infos
    (plateforme, auteur, dates, durée, taille, résolution, URL cliquable), texte
    du post défilant/copiable, galerie, fichiers (icônes, taille, clic droit),
    barre d'actions (Lire, Original, Page archive, Dossier, Renommer, Copier
    lien, Supprimer), tags + notes perso. Historique : recherche, filtre
    plateforme, tri, compteur, vignettes. File d'attente visible (% yt-dlp,
    annuler), lot « Plusieurs liens », surveillance presse-papiers (option),
    doublons, qualité (Meilleure/720p/480p/Audio mp3), sous-titres FR/EN,
    notifications plyer, paramètres persistants, index global en cartes,
    journal archiveur.log, mises à jour Tk thread-safe (file + after()).
v3: aperçu résultat, renommer (F2), historique clic droit, Coller et archiver
    garde l'URL visible, Ouvrir dossier fiable, titres auto améliorés.
v2: bouton Coller et archiver, Ctrl+V / Shift+Insert / Entrée auto-archivage,
    menu clic droit FR sur le champ URL.
"""
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



# ---------------------------------------------------------------- Grimoire : ecriture directe dans grimoire.db (5.x)
GR_MUTEX = "Local\\Grimoire_SingleInstance"
GR_ARCHIVES_SQL = """CREATE TABLE IF NOT EXISTS archives(
  url TEXT PRIMARY KEY, item_id INTEGER, status TEXT DEFAULT '', root TEXT DEFAULT '', folder TEXT DEFAULT '',
  info TEXT DEFAULT '{}', created TEXT, updated TEXT);"""


def gr_data_dir() -> str:
    env = os.environ.get("GRIMOIRE_DATA", "").strip()
    if env:
        return env
    root = os.environ.get("PADAWAN_DATA", "").strip()
    if root:
        return os.path.join(root, "Grimoire")
    if os.path.isdir(r"C:\web\FTP_HOME"):
        return os.path.join(r"C:\web\FTP_HOME", "GRIMOIRE")
    return os.path.join(os.path.expanduser("~"), "Documents", "Padawan", "Grimoire")


def gr_db_path() -> str:
    return os.path.join(gr_data_dir(), "grimoire.db")


def gr_connect():
    import sqlite3
    c = sqlite3.connect(gr_db_path(), timeout=20)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA busy_timeout=20000")
    c.execute(GR_ARCHIVES_SQL)
    c.commit()
    return c


def gr_now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def gr_norm(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", str(s or "").lower())
    return "".join(ch for ch in s if not unicodedata.combining(ch))


def gr_subjects(c) -> List[Dict[str, Any]]:
    return [dict(r) for r in c.execute("SELECT id,parent_id,name,icon,color,sort FROM subjects WHERE deleted IS NULL "
                                       "ORDER BY pinned DESC, sort, name")]


def gr_path(subs: List[Dict[str, Any]], sid: int) -> str:
    by = {s["id"]: s for s in subs}
    out, cur, n = [], by.get(sid), 0
    while cur and n < 20:
        out.append(cur["name"])
        cur = by.get(cur.get("parent_id"))
        n += 1
    return " › ".join(reversed(out))


def gr_suggest(subs: List[Dict[str, Any]], text: str) -> Optional[int]:
    """sujet du Grimoire le plus proche (mots du titre, description, collections et tags de l'archive)."""
    words = set(w for w in re.findall(r"[a-z0-9]{4,}", gr_norm(text)))
    best, score = None, 0.0
    for s in subs:
        sw = [w for w in re.findall(r"[a-z0-9]{4,}", gr_norm(s["name"]))]
        if not sw:
            continue
        hit = 0.0
        for w in sw:
            if w in words:
                hit += 2
            elif any(x.startswith(w[:5]) or w.startswith(x[:5]) for x in words if len(x) >= 5 and len(w) >= 5):
                hit += 1
        sc = hit / len(sw) + (0.2 if s.get("parent_id") else 0)
        if hit and sc > score:
            best, score = s["id"], sc
    return best


def gr_find_url(c, url: str) -> Optional[Dict[str, Any]]:
    if not url:
        return None
    r = c.execute("SELECT id,title,subject_id FROM items WHERE deleted IS NULL AND url=? ORDER BY id LIMIT 1", (url,)).fetchone()
    return dict(r) if r else None


def gr_folder_info(folder: str) -> Dict[str, Any]:
    files = os.listdir(folder) if os.path.isdir(folder) else []
    ext = (".mp4", ".webm", ".mkv", ".mov", ".m4v", ".mp3", ".m4a", ".opus")
    vids = sorted([f for f in files if f.lower().endswith(ext)], key=lambda f: -os.path.getsize(os.path.join(folder, f)))
    imgs = [f for f in files if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp")) and not f.startswith("sb_")]
    imgs.sort(key=lambda f: (0 if ("thumb" in f.lower() or "capture" in f.lower()) else 1, f))
    return {"main": vids[0] if vids else ("lecture.html" if "lecture.html" in files else
                                          ("page.html" if "page.html" in files else ("index.html" if "index.html" in files else ""))),
            "video": bool(vids and not vids[0].lower().endswith((".mp3", ".m4a", ".opus"))),
            "index": "index.html" if "index.html" in files else "", "capture": imgs[0] if imgs else "",
            "nfiles": len(files)}


def gr_add_subject(c, name: str, parent_id: Optional[int]) -> int:
    par = c.execute("SELECT icon,color FROM subjects WHERE id=?", (parent_id,)).fetchone() if parent_id else None
    srt = c.execute("SELECT COALESCE(MAX(sort),0)+1 FROM subjects WHERE parent_id IS ?", (parent_id,)).fetchone()[0]
    now = gr_now()
    cur = c.execute("INSERT INTO subjects(parent_id,name,icon,color,sort,created,updated) VALUES(?,?,?,?,?,?,?)",
                    (parent_id, name.strip()[:120], "📁", (par["color"] if par else "") or "", srt, now, now))
    c.commit()
    return int(cur.lastrowid)


def gr_add_fiche(c, sid: int, root: str, entry: Dict[str, Any], info: Dict[str, Any]) -> int:
    """cree une fiche dans le Grimoire (transaction courte) + lien « permanent » vers la copie locale."""
    folder_name = str(entry.get("folder") or "")
    folder = os.path.join(root, folder_name)
    url = str(info.get("url") or info.get("webpage_url") or entry.get("url") or "")
    fi = gr_folder_info(folder)
    title = str(info.get("title") or folder_name)[:300]
    desc = str(info.get("description") or info.get("text") or "")[:20000]
    typ = "video" if fi["video"] else "link"
    site = str(info.get("platform") or info.get("extractor_key") or "")
    try:
        site = platform_label(info.get("platform")) or site
    except Exception:
        pass
    tags = ", ".join(str(t) for t in (info.get("tags") or []) if isinstance(t, str))[:400]
    note = f"Archive locale : {folder}"
    if info.get("notes"):
        note += "\nNotes de l'Archiveur : " + str(info.get("notes"))
    body = json.dumps({"v": 1, "runs": [[note, []]]}, ensure_ascii=False, separators=(",", ":"))
    meta = {"description": desc[:1500], "site": site, "pending": False, "fetched": gr_now(), "auto_title": False,
            "source_archiveur": folder_name}
    now = gr_now()
    c.execute("BEGIN IMMEDIATE")
    try:
        srt = c.execute("SELECT COALESCE(MAX(sort),0)+1 FROM items WHERE subject_id=?", (sid,)).fetchone()[0]
        cur = c.execute("INSERT INTO items(subject_id,type,title,body,body_text,url,source,author,tags,extracted,meta,sort,created,updated) "
                        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (sid, typ, title, body, note, url, "Archiveur", str(info.get("uploader") or "")[:200], tags, desc,
                         json.dumps(meta, ensure_ascii=False), srt, now, now))
        iid = int(cur.lastrowid)
        thumb = ""
        if fi["capture"]:
            try:
                d = os.path.join(gr_data_dir(), "medias", str(sid), "_vignettes")
                os.makedirs(d, exist_ok=True)
                dest = os.path.join(d, f"v{iid}.png")
                try:
                    from PIL import Image  # type: ignore
                    with Image.open(os.path.join(folder, fi["capture"])) as im:
                        im = im.convert("RGB")
                        im.thumbnail((480, 320))
                        im.save(dest, "PNG")
                except Exception:
                    dest = os.path.join(d, f"v{iid}" + os.path.splitext(fi["capture"])[1].lower())
                    shutil.copyfile(os.path.join(folder, fi["capture"]), dest)
                thumb = f"medias/{sid}/_vignettes/{os.path.basename(dest)}"
                c.execute("UPDATE items SET thumb=? WHERE id=?", (thumb, iid))
            except Exception:
                thumb = ""
        try:
            c.execute("INSERT INTO fts(rowid,title,body,extracted,tags,source,url) VALUES(?,?,?,?,?,?,?)",
                      (iid, title, note, desc + " " + meta["description"] + " " + site, tags, "Archiveur", url))
        except Exception:
            pass   # pas de recherche plein texte : le Grimoire reconstruit l'index au besoin
        if url:
            fi.update({"source": "archiveur", "copie_le": now, "title": title})
            c.execute("INSERT OR REPLACE INTO archives(url,item_id,status,root,folder,info,created,updated) VALUES(?,?,?,?,?,?,?,?)",
                      (url, iid, "permanent", root, folder_name, json.dumps(fi, ensure_ascii=False), now, now))
        c.commit()
    except Exception:
        c.rollback()
        raise
    return iid


def gr_running() -> bool:
    if not sys.platform.startswith("win"):
        return False
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.windll.kernel32
        k32.OpenMutexW.restype = wintypes.HANDLE
        h = k32.OpenMutexW(0x00100000, False, GR_MUTEX)
        if h:
            k32.CloseHandle(h)
            return True
    except Exception:
        pass
    return False


def gr_open_item(iid: int, script: str) -> None:
    """ouvre la fiche dans le Grimoire (ouvert : message dans _inbox ; ferme : on le lance)."""
    d = os.path.join(gr_data_dir(), "_inbox")
    os.makedirs(d, exist_ok=True)
    fp = os.path.join(d, f"ouvrir_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.json")
    with open(fp + ".tmp", "w", encoding="utf-8") as f:
        json.dump({"action": "ouvrir", "id": int(iid)}, f)
    os.replace(fp + ".tmp", fp)
    if not gr_running() and os.path.isfile(script):
        py = sys.executable or "pythonw"
        if py.lower().endswith("python.exe") and os.path.isfile(py[:-10] + "pythonw.exe"):
            py = py[:-10] + "pythonw.exe"
        kw: Dict[str, Any] = {"cwd": os.path.dirname(script)}
        if sys.platform.startswith("win"):
            kw["creationflags"] = CREATE_NO_WINDOW
        subprocess.Popen([py, script], **kw)


class GrimoireSendDialog(tk.Toplevel if tk is not None else object):  # type: ignore[misc]
    """« 📚 Envoyer au Grimoire » : choisir un sujet (suggestion automatique), creer un sous-sujet au besoin."""

    def __init__(self, app, entries: List[Dict[str, Any]], infos: List[Dict[str, Any]]):
        super().__init__(app)
        self.app, self.entries, self.infos = app, entries, infos
        self.result: Optional[int] = None
        self.title("📚 Envoyer au Grimoire")
        self.configure(bg=NC_BG)
        self.transient(app)
        self.c = gr_connect()
        self.subs = gr_subjects(self.c)
        n = len(entries)
        hdr = (f"« {str(infos[0].get('title') or entries[0].get('folder'))[:90]} »" if n == 1 else f"{n} archives sélectionnées")
        tk.Label(self, text="📚 Dans quel sujet du Grimoire ?", bg=NC_BG, fg=NC_HI, font=FONT_TITLE).pack(anchor="w", padx=12, pady=(10, 0))
        tk.Label(self, text=hdr, bg=NC_BG, fg=NC_FG, font=FONT_UI, wraplength=560, justify="left").pack(anchor="w", padx=12)
        text = " ".join(str(i.get("title") or "") + " " + str(i.get("description") or "")[:600] + " " +
                        " ".join(str(x) for x in (i.get("tags") or [])) + " " + " ".join(str(x) for x in (e.get("collections") or []))
                        for e, i in zip(entries, infos))
        self.sug = gr_suggest(self.subs, text)
        if self.sug:
            tk.Label(self, text=f"✨ Suggestion : {gr_path(self.subs, self.sug)}", bg=NC_BG, fg=NC_OK, font=FONT_SM).pack(anchor="w", padx=12, pady=(4, 0))
        fr = tk.Frame(self, bg=NC_BG)
        fr.pack(fill="both", expand=True, padx=12, pady=6)
        self.tv = ttk.Treeview(fr, show="tree", selectmode="browse", height=16)
        sb = ttk.Scrollbar(fr, orient="vertical", command=self.tv.yview)
        self.tv.configure(yscrollcommand=sb.set)
        self.tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.fill()
        self.tv.bind("<Double-Button-1>", lambda _e: self.ok())
        self.tv.bind("<Return>", lambda _e: self.ok())
        bar = tk.Frame(self, bg=NC_BG)
        bar.pack(fill="x", padx=12, pady=(0, 10))
        b = app._btn(bar, "📁 Nouveau sous-sujet…", self.new_sub)
        b.pack(side="left")
        Tooltip(b, "Créer un sous-sujet dans le sujet choisi (ou un sujet principal si rien n'est choisi)")
        b = app._btn(bar, "✖ Annuler", self.destroy)
        b.pack(side="right", padx=(6, 0))
        Tooltip(b, "Fermer sans rien envoyer (Échap)")
        b = app._btn(bar, "📚 Envoyer", self.ok, hi=True)
        b.pack(side="right")
        Tooltip(b, "Crée la fiche dans le Grimoire : titre, texte, image, lien d'origine et copie locale (✔ Permanent)")
        self.bind("<Escape>", lambda _e: self.destroy())
        self.geometry("600x560")
        try:
            self.update_idletasks()
            self.geometry(f"+{app.winfo_rootx() + 80}+{app.winfo_rooty() + 60}")
        except Exception:
            pass
        self.tv.focus_set()
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def fill(self, sel: Optional[int] = None):
        self.tv.delete(*self.tv.get_children())
        kids: Dict[Any, List[Dict[str, Any]]] = {}
        for s in self.subs:
            kids.setdefault(s.get("parent_id"), []).append(s)

        def walk(pid, node):
            for s in kids.get(pid, []):
                self.tv.insert(node, "end", iid=str(s["id"]), text=f"{s.get('icon') or '📁'}  {s['name']}", open=True)
                walk(s["id"], str(s["id"]))
        walk(None, "")
        target = sel or self.sug or next((s["id"] for s in self.subs if s["name"] == "À classer"), None)
        if target and self.tv.exists(str(target)):
            self.tv.selection_set(str(target))
            self.tv.focus(str(target))
            self.tv.see(str(target))

    def new_sub(self):
        from tkinter import simpledialog
        sel = self.tv.selection()
        pid = int(sel[0]) if sel else None
        where = f" dans « {gr_path(self.subs, pid)} »" if pid else " (sujet principal)"
        name = simpledialog.askstring("Nouveau sous-sujet", "Nom du nouveau sujet" + where + " :", parent=self)
        if not name or not name.strip():
            return
        sid = gr_add_subject(self.c, name, pid)
        self.subs = gr_subjects(self.c)
        self.fill(sid)

    def ok(self):
        sel = self.tv.selection()
        if not sel:
            messagebox.showinfo("Grimoire", "Choisis un sujet dans la liste.", parent=self)
            return
        self.result = int(sel[0])
        self.destroy()

    def destroy(self):
        try:
            self.c.close()
        except Exception:
            pass
        super().destroy()

class ArchiveCancelled(Exception):
    """Archivage annulé par l'utilisateur."""


def friendly_error(exc: BaseException) -> str:
    """Message FR clair pour une erreur d'archivage."""
    s = str(exc) or exc.__class__.__name__
    low = s.lower()
    if isinstance(exc, ArchiveCancelled):
        return "Archivage annulé."
    if "private" in low or "login" in low or "sign in" in low or "authentication" in low:
        return "Contenu privé ou connexion requise — cochez « Cookies navigateur » et réessayez."
    if "unsupported url" in low:
        return "Site non pris en charge par yt-dlp — archivage page HTML tenté."
    if "http error 404" in low or "not found" in low:
        return "Page introuvable (404) — lien supprimé ou incorrect."
    if "http error 429" in low or "too many requests" in low:
        return "Trop de requêtes (429) — patientez quelques minutes."
    if "getaddrinfo" in low or "urlopen error" in low or "timed out" in low or "connection" in low:
        return "Problème réseau — vérifiez la connexion Internet."
    if "ffmpeg" in low:
        return "ffmpeg requis pour ce format — il sera installé automatiquement au prochain démarrage."
    if "permission" in low or "winerror 32" in low or "being used" in low:
        return "Fichier verrouillé (ouvert dans un lecteur ?) — fermez-le et réessayez."
    first = s.strip().splitlines()[0] if s.strip() else s
    return first[:300]


def _hidden_kwargs() -> Dict[str, Any]:
    kw: Dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "close_fds": True,
    }
    if sys.platform.startswith("win"):
        kw["creationflags"] = CREATE_NO_WINDOW
        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 0
            kw["startupinfo"] = si
        except Exception:
            pass
    return kw


DEFAULT_CFG: Dict[str, Any] = {
    "archive_root": DEFAULT_ROOT,
    "cookies_from_browser": False,
    "cookies_browser": "chrome",
    "ask_ytdlp_install": True,
    "ask_ffmpeg_install": False,
    "quality": "best",
    "subtitles": True,
    "storyboard": True,
    "clipboard_watch": False,
    "clipboard_auto": False,
    "notifications": True,
    "sort": "date_desc",
    "player": "windows",
    "auto_convert": True,
    "theme": "norton",
    "font_delta": 0,
    "integrated_player": True,
    "volume": 80,
    "web_capture": True,
    "x_fxtwitter": True,
    "whisper_model": "base",
    "collection_filter": "",
    "online_workers": 4,
}


def load_cfg() -> Dict[str, Any]:
    cfg = dict(DEFAULT_CFG)
    try:
        if os.path.isfile(CFG_FILE):
            with open(CFG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                cfg.update(data)
    except Exception:
        logger.exception("lecture config")
    if cfg.get("quality") not in LABEL_BY_QUALITY:
        cfg["quality"] = "best"
    if cfg.get("sort") not in LABEL_BY_SORT:
        cfg["sort"] = "date_desc"
    return cfg


_CFG_READONLY = False  # modes test (--smoke, --shot, --root) : ne jamais toucher aux réglages de l'utilisateur


def save_cfg(cfg: Dict[str, Any]) -> None:
    if _CFG_READONLY:
        return
    try:
        tmp = CFG_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        os.replace(tmp, CFG_FILE)
    except Exception:
        logger.exception("écriture config")


def _write_json_atomic(path: str, data: Any) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

def slugify(text: str, max_len: int = 60) -> str:
    """Nom de dossier/fichier Windows-safe (minuscules, tirets)."""
    text = (text or "").strip()
    # caractères interdits Windows + contrôles
    text = re.sub(r'[<>:"/\\|?*]', "", text)
    text = "".join(ch for ch in text if ord(ch) >= 32)
    text = (
        text.replace("’", "'")
        .replace("‘", "'")
        .replace("“", '"')
        .replace("”", '"')
    )
    text = text.lower()
    text = re.sub(r"[^\w\s\-]+", "", text, flags=re.UNICODE)
    text = re.sub(r"[\s_]+", "-", text).strip("-")
    text = re.sub(r"-{2,}", "-", text)
    if not text:
        text = "sans-titre"
    return text[:max_len].rstrip("-")


_GENERIC_TITLES = {
    "status", "statuses", "post", "posts", "tweet", "tweets", "video", "videos",
    "watch", "share", "photo", "photos", "image", "images", "media", "story",
    "reel", "reels", "sans-titre", "untitled", "null", "none", "n-a", "na",
}


def is_generic_title(title: str) -> bool:
    t = (title or "").strip()
    if not t:
        return True
    low = t.lower().strip()
    if low in _GENERIC_TITLES:
        return True
    # id numérique pur ou très court
    if re.fullmatch(r"\d{6,}", low):
        return True
    if len(low) <= 2:
        return True
    # "status 123456" / "Tweet by X"
    if re.fullmatch(r"(status|post|tweet|video|photo)[\s_-]*\d*", low):
        return True
    return False


def pick_archive_title(info: Dict[str, Any]) -> str:
    """Titre pertinent: yt-dlp/og title, sinon début du texte/description."""
    title = (info.get("title") or "").strip()
    desc = (info.get("description") or info.get("text") or "").strip()
    if not is_generic_title(title):
        return title
    # début du texte du post (1re ligne non vide, nettoyée)
    for line in desc.splitlines():
        line = line.strip()
        if not line:
            continue
        # ignorer URLs seules
        if re.match(r"^https?://\S+$", line, re.I):
            continue
        # tronquer raisonnablement
        line = re.sub(r"\s+", " ", line)
        if len(line) > 120:
            line = line[:117].rstrip() + "..."
        if not is_generic_title(line):
            return line
    uploader = (info.get("uploader") or info.get("creator") or info.get("channel") or "").strip()
    vid = str(info.get("id") or "").strip()
    if uploader and vid:
        return f"{uploader} - {vid}"
    if uploader:
        return uploader
    if vid:
        return vid
    return title or "sans-titre"


def open_path_explorer(path: str) -> Tuple[bool, str]:
    """Ouvre un dossier/fichier Windows (os.startfile puis explorer.exe)."""
    path = os.path.abspath(path)
    if not os.path.exists(path):
        return False, f"Introuvable:\n{path}"
    if sys.platform.startswith("win"):
        try:
            os.startfile(path)  # type: ignore[attr-defined]
            return True, ""
        except Exception as e1:
            try:
                kwargs = _hidden_kwargs()
                # explorer needs visible window — drop DEVNULL stdout ok
                kwargs.pop("stdout", None)
                kwargs.pop("stderr", None)
                subprocess.Popen(["explorer.exe", path], **{
                    "stdin": subprocess.DEVNULL,
                    "close_fds": True,
                    "creationflags": CREATE_NO_WINDOW,
                })
                return True, ""
            except Exception as e2:
                return False, f"Impossible d'ouvrir:\n{path}\n\n{e1}\n{e2}"
    try:
        webbrowser.open(path if path.startswith("file:") else "file://" + path)
        return True, ""
    except Exception as e:
        return False, str(e)



# ---------------------------------------------------------------- formats
def human_size(n: Any) -> str:
    try:
        n = float(n or 0)
    except Exception:
        return "—"
    if n <= 0:
        return "—"
    for unit in ("o", "Ko", "Mo", "Go", "To"):
        if n < 1024 or unit == "To":
            return f"{n:.0f} {unit}" if unit == "o" else f"{n:.1f} {unit}".replace(".", ",")
        n /= 1024.0
    return "—"


def human_duration(sec: Any) -> str:
    try:
        s = int(round(float(sec)))
    except Exception:
        return "—"
    if s <= 0:
        return "—"
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fmt_upload_date(d: Any) -> str:
    d = str(d or "").strip()
    if re.fullmatch(r"\d{8}", d):
        return f"{d[:4]}-{d[4:6]}-{d[6:]}"
    return d or "—"


def fmt_iso(d: Any) -> str:
    d = str(d or "").strip()
    if not d:
        return "—"
    return d.replace("T", " ")[:16]


def platform_label(p: Any) -> str:
    p = str(p or "web")
    return PLATFORM_LABELS.get(p, "🌐 " + p.capitalize())


FILE_ICONS = [
    (VIDEO_EXTS, "🎬"),
    (AUDIO_EXTS, "🎵"),
    (IMAGE_EXTS, "🖼"),
    ((".vtt", ".srt"), "💬"),
    ((".json",), "🧾"),
    ((".html", ".htm"), "🌐"),
    ((".pdf",), "📕"),
    ((".txt", ".description"), "📝"),
]


def file_icon(name: str) -> str:
    low = name.lower()
    for exts, ico in FILE_ICONS:
        if low.endswith(exts):
            return ico
    return "📄"


def file_kind(name: str) -> str:
    low = name.lower()
    if low.endswith(VIDEO_EXTS):
        return "Vidéo"
    if low.endswith(AUDIO_EXTS):
        return "Audio"
    if low.endswith(IMAGE_EXTS):
        return "Image"
    if low.endswith((".vtt", ".srt")):
        return "Sous-titres"
    if low.endswith(".json"):
        return "Métadonnées"
    if low.endswith((".html", ".htm")):
        return "Page HTML"
    if low.endswith((".txt", ".description")):
        return "Texte"
    if low.endswith(".pdf"):
        return "PDF"
    return "Fichier"


URL_RE = re.compile(r"""(?:https?://|www\.)[^\s<>"'\]\[{}|\\^`]+""", re.I)


def _trim_url(u: str) -> str:
    while u and u[-1] in ".,;:!?)»”’'\"":
        if u[-1] == ")" and u.count("(") >= u.count(")"):
            break
        u = u[:-1]
    return u


def find_urls_spans(text: str) -> List[Tuple[int, int, str]]:
    """[(start, end, url)] pour rendre les liens cliquables."""
    out = []
    for m in URL_RE.finditer(text or ""):
        u = _trim_url(m.group(0))
        if len(u) < 8:
            continue
        out.append((m.start(), m.start() + len(u), u))
    return out


def extract_urls(text: str) -> List[str]:
    """URLs http(s) d'un texte libre (un par ligne ou mélangé), sans doublon."""
    seen = set()
    out = []
    for _s, _e, u in find_urls_spans(text):
        if u.lower().startswith("www."):
            u = "https://" + u
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def linkify_html(text: str) -> str:
    """Échappe le texte et transforme les URLs en <a target=_blank>."""
    text = text or ""
    parts = []
    pos = 0
    for s, e, u in find_urls_spans(text):
        parts.append(html.escape(text[pos:s]))
        href = u if not u.lower().startswith("www.") else "https://" + u
        parts.append(
            f'<a href="{html.escape(href, quote=True)}" target="_blank" rel="noopener">{html.escape(u)}</a>'
        )
        pos = e
    parts.append(html.escape(text[pos:]))
    return "".join(parts)


# ---------------------------------------------------------------- doublons
def normalize_url(url: str) -> str:
    """Clé canonique d'une URL (YouTube id, X status id, sinon hôte+chemin)."""
    url = (url or "").strip()
    if not url:
        return ""
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    try:
        p = urlparse(url)
    except Exception:
        return url.lower()
    host = (p.hostname or "").lower()
    for pre in ("www.", "m.", "mobile.", "music."):
        if host.startswith(pre):
            host = host[len(pre):]
    path = p.path or "/"
    if host in ("youtube.com", "youtu.be", "youtube-nocookie.com"):
        vid = ""
        if host == "youtu.be":
            vid = path.strip("/").split("/")[0]
        else:
            q = parse_qs(p.query)
            if q.get("v"):
                vid = q["v"][0]
            else:
                m = re.match(r"^/(?:shorts|embed|live|v)/([^/?#]+)", path)
                if m:
                    vid = m.group(1)
        if vid:
            return f"youtube:{vid}"
    if host in ("x.com", "twitter.com", "fxtwitter.com", "vxtwitter.com"):
        m = re.search(r"/status(?:es)?/(\d+)", path)
        if m:
            return f"x:{m.group(1)}"
    if host == "fb.watch":
        return f"facebook:{path.strip('/')}"
    if host.endswith("facebook.com"):
        q = parse_qs(p.query)
        for k in ("v", "story_fbid", "fbid"):
            if q.get(k):
                return f"facebook:{q[k][0]}"
    if host.endswith("tiktok.com"):
        m = re.search(r"/video/(\d+)", path)
        if m:
            return f"tiktok:{m.group(1)}"
    if host.endswith("instagram.com"):
        m = re.match(r"^/(?:p|reel|reels|tv)/([^/]+)", path)
        if m:
            return f"instagram:{m.group(1)}"
    return f"{host}{path.rstrip('/')}".lower()


def find_duplicates(entries: List[Dict[str, Any]], url: str) -> List[Dict[str, Any]]:
    key = normalize_url(url)
    if not key:
        return []
    out = []
    for e in entries:
        for cand in (e.get("url"), e.get("source_url")):
            if cand and normalize_url(str(cand)) == key:
                out.append(e)
                break
    out.sort(key=lambda x: x.get("archived_at") or "", reverse=True)
    return out


# ---------------------------------------------------------------- tags / recherche
def parse_tags(raw: Any) -> List[str]:
    if isinstance(raw, list):
        items = [str(x) for x in raw]
    else:
        items = re.split(r"[,;\n]+", str(raw or ""))
    out: List[str] = []
    seen = set()
    for t in items:
        t = t.strip().lstrip("#").strip()
        t = re.sub(r"\s+", " ", t)
        if not t:
            continue
        k = t.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(t[:40])
    return out


_HAY_CACHE: Dict[Tuple[Any, ...], str] = {}


def entry_haystack(e: Dict[str, Any], full: bool = True) -> str:
    st = str(e.get("search_text") or "")
    key = (e.get("folder"), e.get("archived_at"), e.get("title"), e.get("notes"), tuple(e.get("tags") or []),
           tuple(e.get("collections") or []), len(st), full)
    hit = _HAY_CACHE.get(key)
    if hit is not None:
        return hit
    if len(_HAY_CACHE) > 20000:
        _HAY_CACHE.clear()
    hay = _entry_haystack_raw(e) + " " + " ".join(e.get("collections") or []).lower() + " " + \
        (st if full else st[:3000]).lower()
    _HAY_CACHE[key] = hay
    return hay


def _entry_haystack_raw(e: Dict[str, Any]) -> str:
    return " ".join([
        str(e.get("title") or ""),
        str(e.get("platform") or ""),
        str(e.get("uploader") or ""),
        str(e.get("text_snippet") or ""),
        " ".join(e.get("tags") or []),
        str(e.get("notes") or ""),
        str(e.get("url") or ""),
        str(e.get("folder") or ""),
    ]).lower()


COLL_FAV = "__fav__"
COLL_OFFLINE = "__offline__"
COLL_TRANSCRIPT = "__transcript__"
COLL_NONE = "__none__"


def entry_in_collection(e: Dict[str, Any], collection: Optional[str]) -> bool:
    if not collection:
        return True
    if collection == COLL_FAV:
        return bool(e.get("favorite"))
    if collection == COLL_OFFLINE:
        return e.get("online_status") in ("offline", "restricted")
    if collection == COLL_TRANSCRIPT:
        return bool(e.get("has_transcript"))
    if collection == COLL_NONE:
        return not e.get("collections")
    return collection.lower() in {c.lower() for c in (e.get("collections") or [])}


def search_entries(
    entries: List[Dict[str, Any]],
    query: str = "",
    platform: Optional[str] = None,
    sort: str = "date_desc",
    collection: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Filtre (tous les mots : titre, texte, transcription, auteur, tags, notes, collections)
    + plateforme + collection/favoris + tri."""
    words = [w for w in (query or "").lower().split() if w]
    out = []
    for e in entries:
        if platform and platform not in ("", "all") and (e.get("platform") or "web") != platform:
            continue
        if not entry_in_collection(e, collection):
            continue
        if words:
            hay = entry_haystack(e)
            if not all(w.lstrip("#") in hay for w in words):
                continue
        out.append(e)
    if sort.startswith("name"):
        out.sort(key=lambda x: str(x.get("title") or x.get("folder") or "").lower(),
                 reverse=sort.endswith("desc"))
    elif sort.startswith("size"):
        out.sort(key=lambda x: int(x.get("size") or 0), reverse=sort.endswith("desc"))
    else:
        out.sort(key=lambda x: x.get("archived_at") or "", reverse=not sort.endswith("asc"))
    return out


# ---------------------------------------------------------------- dossier
def folder_size(path: str) -> int:
    total = 0
    for root, _d, files in os.walk(path):
        for n in files:
            try:
                total += os.path.getsize(os.path.join(root, n))
            except OSError:
                pass
    return total


def list_folder_files(folder: str) -> List[str]:
    """Tous les fichiers de 1er niveau (pour l'onglet Fichiers)."""
    try:
        names = [n for n in os.listdir(folder)
                 if os.path.isfile(os.path.join(folder, n)) and not n.endswith(".tmp")]
    except OSError:
        return []
    order = {"Vidéo": 0, "Audio": 1, "Image": 2, "Texte": 3, "Page HTML": 4, "Sous-titres": 5}
    names.sort(key=lambda n: (order.get(file_kind(n), 9), n.lower()))
    return names


def list_folder_media(folder: str) -> List[str]:
    """Fichiers média + texte utiles d'un dossier d'archive."""
    if not os.path.isdir(folder):
        return []
    out: List[str] = []
    prefer_ext = MEDIA_EXTS + (".txt", ".vtt", ".srt", ".json", ".html")
    skip = {"info.json", "archive_index.json"}
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return []
    for name in names:
        if name in skip or name.startswith("."):
            continue
        if name.lower().endswith(prefer_ext):
            out.append(name)
    return out


def find_main_media(folder: str) -> Optional[str]:
    """Plus gros fichier vidéo, sinon audio."""
    best = None
    best_rank = (9, 0)
    try:
        names = os.listdir(folder)
    except OSError:
        return None
    for n in names:
        low = n.lower()
        if low.endswith(VIDEO_EXTS):
            rank = 0
        elif low.endswith(AUDIO_EXTS):
            rank = 1
        else:
            continue
        p = os.path.join(folder, n)
        try:
            sz = os.path.getsize(p)
        except OSError:
            sz = 0
        key = (rank, -sz)
        if best is None or key < best_rank:
            best, best_rank = p, key
    return best


def list_images(folder: str) -> List[str]:
    """Images de 1er niveau, sans doublons exacts (ex.: image.jpg = twimage.jpg)."""
    out = []
    seen = set()
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return []
    for n in names:
        if not n.lower().endswith(IMAGE_EXTS):
            continue
        p = os.path.join(folder, n)
        try:
            sz = os.path.getsize(p)
            with open(p, "rb") as f:
                h = hashlib.md5(f.read(65536)).hexdigest()
        except OSError:
            continue
        k = (sz, h)
        if k in seen:
            continue
        seen.add(k)
        out.append(p)
    return out


def list_page_images(folder: str, min_bytes: int = 12000, limit: int = 60) -> List[str]:
    """Images d'une page web archivée (page_files/), sans icônes minuscules."""
    d = os.path.join(folder, "page_files")
    out = []
    try:
        for n in sorted(os.listdir(d)):
            p = os.path.join(d, n)
            if n.lower().endswith(IMAGE_EXTS) and os.path.getsize(p) >= min_bytes:
                out.append(p)
                if len(out) >= limit:
                    break
    except OSError:
        pass
    return out


def find_thumbnail(folder: str, info: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """Chemin miniature locale (webp/jpg/png) si présente."""
    if not folder or not os.path.isdir(folder):
        return None
    prefer = []
    try:
        for name in os.listdir(folder):
            low = name.lower()
            if low.endswith((".webp", ".jpg", ".jpeg", ".png")):
                prefer.append((0 if "thumb" in low or "image" in low else 1, low, os.path.join(folder, name)))
    except OSError:
        return None
    if not prefer:  # post X sans image : avatar de l'auteur
        adir = os.path.join(folder, "auteur")
        try:
            for name in sorted(os.listdir(adir)) if os.path.isdir(adir) else []:
                if name.lower().endswith((".webp", ".jpg", ".jpeg", ".png")):
                    prefer.append((2, name.lower(), os.path.join(adir, name)))
        except OSError:
            pass
    prefer.sort()
    if prefer:
        # une capture de page (très haute) seulement si rien d'autre
        good = [p for p in prefer if not os.path.basename(p[2]).lower().startswith("capture_page")]
        return (good or prefer)[0][2]
    sb = list_storyboard(folder)
    if sb:
        return sb[0]
    ex = [p for p in list_extracts(folder) if p.lower().endswith((".jpg", ".png"))]
    return ex[0] if ex else None


def list_storyboard(folder: str) -> List[str]:
    d = os.path.join(folder, STORYBOARD_DIR)
    try:
        return [os.path.join(d, n) for n in sorted(os.listdir(d)) if n.lower().endswith(".jpg")]
    except OSError:
        return []


def load_info(folder_path: str) -> Dict[str, Any]:
    p = os.path.join(folder_path, "info.json")
    try:
        if os.path.isfile(p):
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        logger.exception("lecture info.json %s", p)
    return {}


def entry_from_info(info: Dict[str, Any], folder_path: str) -> Dict[str, Any]:
    """Entrée d'index enrichie (taille, miniature, tags, notes…)."""
    thumb = find_thumbnail(folder_path, info) if folder_path else None
    rel_thumb = os.path.relpath(thumb, folder_path).replace("\\", "/") if thumb else ""
    text = info.get("description") or info.get("text") or ""
    try:
        tr = transcript_text(folder_path) if folder_path and os.path.isdir(folder_path) else ""
    except Exception:
        logger.exception("transcript index")
        tr = ""
    return {
        "folder": os.path.basename(folder_path) if folder_path else info.get("folder"),
        "title": info.get("title"),
        "platform": info.get("platform"),
        "url": info.get("webpage_url") or info.get("url"),
        "source_url": info.get("url"),
        "uploader": info.get("uploader") or "",
        "upload_date": info.get("upload_date") or "",
        "duration": info.get("duration"),
        "archived_at": info.get("archived_at"),
        "text_snippet": text[:300],
        "method": info.get("method"),
        "tags": parse_tags(info.get("tags") or []),
        "notes": info.get("notes") or "",
        "size": folder_size(folder_path) if folder_path and os.path.isdir(folder_path) else 0,
        "thumb": rel_thumb,
        "quality": info.get("quality") or "",
        "favorite": bool(info.get("favorite")),
        "collections": [c for c in (info.get("collections") or []) if isinstance(c, str)],
        "online_status": info.get("online_status") or "",
        "online_checked": info.get("online_checked") or "",
        "has_transcript": bool(tr),
        "search_text": (str(text)[300:60000] + " " + tr)[:60000].strip(),
    }


# ---------------------------------------------------------------- index
def load_archive_index(root: str) -> List[Dict[str, Any]]:
    path = os.path.join(root, INDEX_JSON)
    try:
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return [e for e in data if isinstance(e, dict)]
    except Exception:
        logger.exception("lecture %s", path)
    return []


def save_archive_index(root: str, entries: List[Dict[str, Any]]) -> None:
    os.makedirs(root, exist_ok=True)
    backup_index(root)
    _write_json_atomic(os.path.join(root, INDEX_JSON), entries)
    write_global_index_html(root, entries)


def register_archive(root: str, info: Dict[str, Any]) -> Dict[str, Any]:
    """Ajoute/remplace l'archive dans archive_index.json + index global."""
    folder_path = os.path.join(root, str(info.get("folder")))
    entry = entry_from_info(info, folder_path)
    entries = load_archive_index(root)
    entries = [e for e in entries if e.get("folder") != entry["folder"]]
    entries.append(entry)
    save_archive_index(root, entries)
    return entry


def sync_index_with_disk(root: str, log: Optional[Callable[[str], None]] = None) -> List[Dict[str, Any]]:
    """Relit l'index, ajoute les dossiers inconnus, retire les absents, complète les champs."""
    entries = load_archive_index(root)
    changed = False
    if not os.path.isdir(root):
        return entries
    kept = []
    for e in entries:
        fp = os.path.join(root, str(e.get("folder") or ""))
        if not e.get("folder") or not os.path.isdir(fp):
            changed = True
            if log:
                log(f"Index: dossier absent retiré ({e.get('folder')})")
            continue
        if ("size" not in e or "thumb" not in e or "tags" not in e or "uploader" not in e
                or "favorite" not in e or "search_text" not in e):
            info = load_info(fp)
            if info:
                fresh = entry_from_info(info, fp)
                fresh["title"] = e.get("title") or fresh.get("title")
                e = {**fresh, **{k: v for k, v in e.items() if v not in (None, "")}}
                for k in ("favorite", "collections", "online_status", "online_checked",
                          "has_transcript", "search_text"):
                    e[k] = fresh[k]
                e["size"] = fresh["size"]
                e["thumb"] = fresh["thumb"]
                e.setdefault("tags", fresh["tags"])
                changed = True
        kept.append(e)
    known = {e.get("folder") for e in kept}
    for name in os.listdir(root):
        if name in known or name.startswith("_") or name in (INDEX_JSON, INDEX_HTML):
            continue
        fp = os.path.join(root, name)
        if os.path.isdir(fp) and os.path.isfile(os.path.join(fp, "info.json")):
            info = load_info(fp)
            if info:
                kept.append(entry_from_info(info, fp))
                changed = True
    if changed or not os.path.isfile(os.path.join(root, INDEX_HTML)):
        save_archive_index(root, kept)
    return kept


def update_tags_notes(root: str, folder: str, tags: Any, notes: str) -> Dict[str, Any]:
    """Sauve tags + notes dans info.json, archive_index.json, index.html (local + global)."""
    fp = os.path.join(root, folder)
    if not os.path.isdir(fp):
        raise FileNotFoundError(f"Dossier introuvable: {fp}")
    info = load_info(fp)
    info["tags"] = parse_tags(tags)
    info["notes"] = (notes or "").strip()
    info.setdefault("folder", folder)
    _write_json_atomic(os.path.join(fp, "info.json"), info)
    write_post_txt(os.path.join(fp, "post.txt"), info)
    write_local_index(fp, info)
    entries = load_archive_index(root)
    found = False
    for e in entries:
        if e.get("folder") == folder:
            e["tags"] = info["tags"]
            e["notes"] = info["notes"]
            found = True
    if not found:
        entries.append(entry_from_info(info, fp))
    save_archive_index(root, entries)
    return info


# ---------------------------------------------------------------- storyboard
def probe_duration(video: str) -> Optional[float]:
    ff = find_ffmpeg()
    if not ff:
        return None
    try:
        r = subprocess.run([ff, "-hide_banner", "-i", video], **_hidden_kwargs(), timeout=30)
        err = (r.stderr or b"").decode("utf-8", errors="replace")
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", err)
        if m:
            return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    except Exception:
        logger.exception("probe_duration")
    return None


def probe_resolution(video: str) -> str:
    """« LxH » de la 1re piste vidéo (ffmpeg -i), sinon ''."""
    ff = find_ffmpeg()
    if not ff:
        return ""
    try:
        r = subprocess.run([ff, "-hide_banner", "-i", video], **_hidden_kwargs(), timeout=30)
        err = (r.stderr or b"").decode("utf-8", errors="replace")
        m = re.search(r"Stream #.*?Video:.*?(\d{2,5})x(\d{2,5})", err)
        if m:
            return f"{m.group(1)}x{m.group(2)}"
    except Exception:
        logger.exception("probe_resolution")
    return ""


SB_FRAMES = 16           # images du storyboard automatique
SB_TIMES_JSON = "storyboard.json"
_SB_LOCK = threading.Lock()  # un seul storyboard à la fois (léger pour le PC)
_LOW_PRIO = 0x00004000       # BELOW_NORMAL_PRIORITY_CLASS (Windows)


def _lowprio_kwargs() -> Dict[str, Any]:
    kw = _hidden_kwargs()
    if sys.platform.startswith("win"):
        kw["creationflags"] = kw.get("creationflags", 0) | _LOW_PRIO
    return kw


def storyboard_times(folder: str, frames: Optional[List[str]] = None,
                     duration: Optional[float] = None) -> List[float]:
    """Moment (s) de chaque image du storyboard : storyboard.json, sinon calculé (anciens storyboards)."""
    frames = frames if frames is not None else list_storyboard(folder)
    if not frames:
        return []
    try:
        with open(os.path.join(folder, STORYBOARD_DIR, SB_TIMES_JSON), "r", encoding="utf-8") as f:
            data = json.load(f)
        by_name = data.get("frames") or {}
        out = []
        for fp in frames:
            t = by_name.get(os.path.basename(fp))
            out.append(float(t) if t is not None else -1.0)
        if all(t >= 0 for t in out):
            return out
    except Exception:
        pass
    dur = duration
    if not dur:
        try:
            dur = float(load_info(folder).get("duration") or 0) or None
        except (TypeError, ValueError):
            dur = None
    if not dur:
        return [0.0 for _ in frames]
    n = len(frames)
    return [dur * (i + 0.5) / n for i in range(n)]


def generate_storyboard(folder: str, n: int = SB_FRAMES, duration: Optional[float] = None,
                        force: bool = False, progress: Optional[Callable[[int, int], None]] = None) -> List[str]:
    """Extrait n petites images régulièrement espacées de la vidéo principale (ffmpeg, recherche rapide
    -ss avant -i, priorité basse) dans storyboard/ + storyboard.json (moment de chaque image)."""
    existing = list_storyboard(folder)
    if existing and not force:
        return existing
    video = find_main_media(folder)
    if not video or not video.lower().endswith(VIDEO_EXTS):
        return []
    ff = find_ffmpeg()
    if not ff:
        return []
    dur = duration or probe_duration(video)
    if not dur or dur <= 0:
        dur = 10.0
    n = max(1, min(int(n), max(1, int(dur // 2) or 1), 40))  # vidéo très courte : moins d'images
    out_dir = os.path.join(folder, STORYBOARD_DIR)
    tmp_dir = out_dir + ".tmp"
    shutil.rmtree(tmp_dir, ignore_errors=True)
    os.makedirs(tmp_dir, exist_ok=True)
    times: Dict[str, float] = {}
    for i in range(n):
        t = dur * (i + 0.5) / n
        name = f"frame_{i + 1:02d}.jpg"
        out = os.path.join(tmp_dir, name)
        try:
            subprocess.run(
                [ff, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{t:.2f}", "-i", video,
                 "-an", "-sn", "-frames:v", "1", "-vf", "scale=320:-2", "-q:v", "5", out],
                **_lowprio_kwargs(), timeout=45,
            )
        except Exception:
            logger.exception("storyboard frame %s", i)
        if os.path.isfile(out) and os.path.getsize(out) > 0:
            times[name] = round(t, 2)
        if progress:
            try:
                progress(i + 1, n)
            except Exception:
                pass
    if not times:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return []
    try:
        with open(os.path.join(tmp_dir, SB_TIMES_JSON), "w", encoding="utf-8") as f:
            json.dump({"duration": dur, "frames": times}, f, ensure_ascii=False, indent=1)
    except Exception:
        logger.exception("storyboard.json")
    # remplacement en une fois : jamais de storyboard à moitié fait
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir, ignore_errors=True)
    try:
        os.replace(tmp_dir, out_dir)
    except OSError:
        shutil.copytree(tmp_dir, out_dir, dirs_exist_ok=True)
        shutil.rmtree(tmp_dir, ignore_errors=True)
    return list_storyboard(folder)


def notify_desktop(title: str, message: str) -> None:
    """Notification discrète (plyer) dans un thread ; silencieux si indisponible."""
    def _go():
        try:
            from plyer import notification  # type: ignore
            ico = os.path.join(BASE, "archiveur.ico")
            kw: Dict[str, Any] = dict(title=title[:63], message=message[:250],
                                      app_name=APP_NAME, timeout=6)
            if os.path.isfile(ico):
                kw["app_icon"] = ico
            notification.notify(**kw)
        except Exception as e:
            logger.info("notification indisponible: %s", e)
    threading.Thread(target=_go, daemon=True).start()
_FFMPEG_DIR_CACHE = None  # type: Optional[str]
_FFMPEG_MUTEX_HANDLE = None


def _registry_path_entries():
    """Relit PATH depuis le registre (session souvent pas a jour apres winget)."""
    entries = []
    if sys.platform != "win32":
        return entries
    try:
        import winreg
        for hive, sub in (
            (winreg.HKEY_CURRENT_USER, r"Environment"),
            (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
        ):
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


def _prepend_path(directory):
    if not directory:
        return
    directory = os.path.abspath(directory)
    cur = os.environ.get("PATH", "")
    parts = [p for p in cur.split(os.pathsep) if p]
    if directory not in parts:
        os.environ["PATH"] = directory + os.pathsep + cur


def find_ffmpeg():
    """Retourne le chemin absolu de ffmpeg.exe, ou None."""
    global _FFMPEG_DIR_CACHE
    which = shutil.which("ffmpeg")
    if which and os.path.isfile(which):
        ab = os.path.abspath(which)
        _FFMPEG_DIR_CACHE = os.path.dirname(ab)
        _prepend_path(_FFMPEG_DIR_CACHE)
        return ab

    candidates = []
    for entry in _registry_path_entries():
        expanded = os.path.expandvars(entry)
        candidates.append(os.path.join(expanded, "ffmpeg.exe"))
        candidates.append(os.path.join(expanded, "bin", "ffmpeg.exe"))

    local = os.environ.get("LOCALAPPDATA", "")
    if local:
        candidates.append(os.path.join(local, r"Microsoft\WinGet\Links\ffmpeg.exe"))
        pkg_root = os.path.join(local, r"Microsoft\WinGet\Packages")
        if os.path.isdir(pkg_root):
            try:
                import glob
                pattern = os.path.join(pkg_root, "Gyan.FFmpeg*", "**", "bin", "ffmpeg.exe")
                for hit in glob.glob(pattern, recursive=True):
                    candidates.append(hit)
            except Exception:
                pass
        candidates.append(os.path.join(local, r"Archiveur\ffmpeg\bin\ffmpeg.exe"))
        candidates.append(os.path.join(local, r"Archiveur\ffmpeg\ffmpeg.exe"))

    for base in (
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\ffmpeg\ffmpeg.exe",
        os.path.expandvars(r"%ProgramFiles%\ffmpeg\bin\ffmpeg.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\ffmpeg\bin\ffmpeg.exe"),
        os.path.expandvars(r"%ProgramFiles%\Gyan\FFmpeg\bin\ffmpeg.exe"),
    ):
        candidates.append(base)

    seen = set()
    for cand in candidates:
        if not cand:
            continue
        cand = os.path.abspath(os.path.expandvars(cand))
        if cand in seen:
            continue
        seen.add(cand)
        if os.path.isfile(cand):
            _FFMPEG_DIR_CACHE = os.path.dirname(cand)
            _prepend_path(_FFMPEG_DIR_CACHE)
            return cand
    return None


def ffmpeg_available():
    return find_ffmpeg() is not None


def ffmpeg_location():
    """Dossier contenant ffmpeg.exe pour yt-dlp ffmpeg_location."""
    exe = find_ffmpeg()
    if exe:
        return os.path.dirname(exe)
    return _FFMPEG_DIR_CACHE


def _download_ffmpeg_zip(log):
    """Telecharge le zip essentials gyan.dev vers %LOCALAPPDATA%\\Archiveur\\ffmpeg\\."""
    import zipfile
    import tempfile

    local = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    dest_root = os.path.join(local, "Archiveur", "ffmpeg")
    os.makedirs(dest_root, exist_ok=True)
    url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    log("Telechargement ffmpeg essentials (gyan.dev)...")
    try:
        req = Request(url, headers={"User-Agent": USER_AGENT})
        with urlopen(req, timeout=120) as resp:
            data = resp.read()
        zip_path = os.path.join(tempfile.gettempdir(), "ffmpeg-release-essentials.zip")
        with open(zip_path, "wb") as f:
            f.write(data)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(dest_root)
        # find bin/ffmpeg.exe under dest_root
        for root, _dirs, files in os.walk(dest_root):
            if "ffmpeg.exe" in files and root.lower().endswith("bin"):
                _prepend_path(root)
                exe = os.path.join(root, "ffmpeg.exe")
                log(f"ffmpeg extrait: {exe}")
                return exe
        # maybe ffmpeg.exe at top of extracted folder
        for root, _dirs, files in os.walk(dest_root):
            if "ffmpeg.exe" in files:
                _prepend_path(root)
                exe = os.path.join(root, "ffmpeg.exe")
                log(f"ffmpeg extrait: {exe}")
                return exe
        log("ffmpeg: zip extrait mais ffmpeg.exe introuvable.")
    except Exception as e:
        log(f"ffmpeg zip erreur: {e}")
    return None


def ensure_ffmpeg(log, ask_install=False, parent=None, status_cb=None):
    """Detecte ffmpeg; si absent, installe auto (winget puis zip). Sans demander."""
    def _status(msg):
        log(msg)
        if status_cb:
            try:
                status_cb(msg)
            except Exception:
                pass

    path = find_ffmpeg()
    if path:
        _status(f"ffmpeg: present ({path})")
        return True

    _status("ffmpeg: absent — installation automatique...")

    # 1) winget silencieux
    winget = shutil.which("winget")
    if winget:
        _status("Installation ffmpeg via winget (Gyan.FFmpeg)...")
        try:
            r = subprocess.run(
                [
                    winget, "install", "-e", "--id", "Gyan.FFmpeg",
                    "--silent", "--accept-package-agreements", "--accept-source-agreements",
                ],
                **_hidden_kwargs(),
                timeout=600,
            )
            out = (r.stdout or b"").decode("utf-8", errors="replace")
            err = (r.stderr or b"").decode("utf-8", errors="replace")
            path = find_ffmpeg()
            if path:
                _status(f"ffmpeg installe via winget: {path}")
                return True
            _status(f"winget ffmpeg: code={r.returncode} {err or out}")
        except Exception as e:
            _status(f"winget ffmpeg erreur: {e}")
    else:
        _status("winget absent — bascule telechargement zip.")

    # 2) zip essentials
    path = _download_ffmpeg_zip(_status)
    if path and os.path.isfile(path):
        _status(f"ffmpeg pret (zip): {path}")
        return True

    _status("ffmpeg toujours absent — Archiveur utilisera des formats deja combines.")
    return False


def generate_icons(out_dir: str) -> Tuple[str, str]:
    """Génère archiveur.ico / .png (boîte archive teal/or). Retourne (ico, png)."""
    ico = os.path.join(out_dir, "archiveur.ico")
    png = os.path.join(out_dir, "archiveur.png")
    png256 = os.path.join(out_dir, "archiveur_256.png")
    try:
        from PIL import Image, ImageDraw

        def draw(size: int):
            img = Image.new("RGBA", (size, size), (10, 24, 40, 255))
            dr = ImageDraw.Draw(img)
            m = max(2, size // 10)
            teal = (32, 178, 170, 255)
            gold = (228, 192, 122, 255)
            dark = (8, 20, 36, 255)
            # box
            dr.rounded_rectangle([m, m + size // 8, size - m, size - m], radius=max(2, size // 12), fill=teal)
            # lid
            lid_h = size // 5
            dr.rounded_rectangle([m - 1, m, size - m + 1, m + lid_h], radius=max(2, size // 14), fill=gold)
            # fold line
            mid = m + lid_h // 2
            dr.line([m + 2, mid, size - m - 2, mid], fill=dark, width=max(1, size // 32))
            # play triangle
            cx, cy = size // 2, size // 2 + size // 10
            t = size // 6
            dr.polygon([(cx - t // 2, cy - t), (cx - t // 2, cy + t), (cx + t, cy)], fill=gold)
            return img

        img64 = draw(64)
        img256 = draw(256)
        img64.save(png)
        img256.save(png256)
        # multi-size ico
        imgs = [draw(s) for s in (16, 32, 48, 64, 128, 256)]
        imgs[0].save(ico, format="ICO", sizes=[(im.width, im.height) for im in imgs], append_images=imgs[1:])
    except Exception:
        # minimal fallback without Pillow
        pass
    return ico, png


def http_get(url: str, timeout: int = 30) -> bytes:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read()


def extract_og(html_text: str) -> Dict[str, str]:
    meta: Dict[str, str] = {}
    for prop in ("og:title", "og:description", "og:image", "og:video", "og:video:url", "og:url", "twitter:title", "twitter:description", "twitter:image"):
        m = re.search(
            rf'<meta[^>]+(?:property|name)=["\']{re.escape(prop)}["\'][^>]+content=["\']([^"\']+)["\']',
            html_text,
            re.I,
        )
        if not m:
            m = re.search(
                rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']{re.escape(prop)}["\']',
                html_text,
                re.I,
            )
        if m:
            meta[prop] = html.unescape(m.group(1))
    if "og:title" not in meta:
        tm = re.search(r"<title[^>]*>([^<]+)</title>", html_text, re.I)
        if tm:
            meta["og:title"] = html.unescape(tm.group(1).strip())
    return meta

def detect_platform(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if "youtube.com" in host or "youtu.be" in host:
        return "youtube"
    if "twitter.com" in host or "x.com" in host:
        return "x"
    if "facebook.com" in host or "fb.watch" in host or "fb.com" in host:
        return "facebook"
    if "instagram.com" in host:
        return "instagram"
    if "tiktok.com" in host:
        return "tiktok"
    if "vimeo.com" in host:
        return "vimeo"
    return "web"


def ensure_ytdlp(log: Callable[[str], None], ask_install: bool = True, parent=None) -> bool:
    try:
        import yt_dlp  # noqa: F401
        return True
    except ImportError:
        pass
    if not ask_install:
        log("yt-dlp manquant — installation refusée / reportée.")
        return False
    if parent is not None:
        ok = messagebox.askyesno(
            APP_NAME,
            "Le module yt-dlp est requis pour archiver YouTube / X / Facebook.\n\n"
            "L'installer maintenant via pip ?",
            parent=parent,
        )
        if not ok:
            return False
    log("Installation de yt-dlp…")
    py = sys.executable
    if py.lower().endswith("pythonw.exe"):
        cand = py[:-len("pythonw.exe")] + "python.exe"
        if os.path.isfile(cand):
            py = cand
    try:
        r = subprocess.run(
            [py, "-m", "pip", "install", "yt-dlp"],
            **_hidden_kwargs(),
            timeout=300,
        )
        out = (r.stdout or b"").decode("utf-8", errors="replace")
        err = (r.stderr or b"").decode("utf-8", errors="replace")
        if r.returncode != 0:
            log(f"pip yt-dlp échec: {err or out}")
            return False
        import yt_dlp  # noqa: F401
        log("yt-dlp installé.")
        return True
    except Exception as e:
        log(f"pip yt-dlp erreur: {e}")
        return False



def reveal_in_explorer(path: str) -> Tuple[bool, str]:
    """Ouvre l'Explorateur avec le fichier sélectionné."""
    path = os.path.abspath(path)
    if not os.path.exists(path):
        return False, f"Introuvable:\n{path}"
    if sys.platform.startswith("win"):
        try:
            subprocess.Popen(f'explorer.exe /select,"{path}"', close_fds=True)
            return True, ""
        except Exception as e:
            return False, str(e)
    return open_path_explorer(os.path.dirname(path))


def rename_archive(
    root: str,
    old_folder: str,
    new_display_name: str,
    log: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """
    Renomme le dossier d'archive + fichier média principal, met à jour info.json,
    post.txt, index.html local, archive_index.json + index global (tags/notes gardés).
    """
    def _log(m: str) -> None:
        if log:
            log(m)

    root = os.path.abspath(root)
    old_folder = os.path.basename(old_folder)
    old_path = os.path.join(root, old_folder)
    if not os.path.isdir(old_path):
        raise FileNotFoundError(f"Dossier introuvable: {old_path}")
    new_display_name = (new_display_name or "").strip()
    if not new_display_name:
        raise ValueError("Le nom ne peut pas être vide.")

    info = load_info(old_path)
    slug = slugify(new_display_name, 50)
    m = re.match(r"^(\d{4}-\d{2}-\d{2}_[a-z0-9]+_)(.+)$", old_folder, re.I)
    if m:
        prefix, rest = m.group(1), m.group(2)
        # v4: le slug ne contient jamais « _ » → tout ce qui suit le 1er « _ » est l'id (+ _n)
        suffix = "_" + rest.split("_", 1)[1] if "_" in rest else ""
        if not suffix and info.get("id"):
            suffix = "_" + slugify(str(info.get("id")), 20)  # v4: id perdu par v3 → restauré
        suffix = re.sub(r"_\d{1,2}$", "", suffix) if suffix.count("_") > 1 else suffix
        new_folder = f"{prefix}{slug}{suffix}"
    else:
        new_folder = f"{datetime.now().strftime('%Y-%m-%d')}_{slug}"
    if new_folder != old_folder:
        cand, n = new_folder, 2
        while os.path.exists(os.path.join(root, cand)):
            cand = f"{new_folder}_{n}"
            n += 1
        new_folder = cand
    new_path = os.path.join(root, new_folder)

    info["title"] = new_display_name
    info["folder"] = new_folder
    files = list(os.listdir(old_path))
    main = find_main_media(old_path)
    if main:
        name = os.path.basename(main)
        target = f"{slug}{os.path.splitext(name)[1]}"
        if target != name and target not in files:
            try:
                os.rename(main, os.path.join(old_path, target))
                _log(f"Fichier: {name} -> {target}")
            except OSError as e:
                raise OSError(
                    f"Fichier verrouillé ou inaccessible:\n{name}\n{e}\n"
                    "Fermez le lecteur multimédia et réessayez."
                ) from e
    info["media_files"] = [n for n in list_folder_media(old_path) if n.lower().endswith(MEDIA_EXTS)]
    _write_json_atomic(os.path.join(old_path, "info.json"), info)
    write_post_txt(os.path.join(old_path, "post.txt"), info)
    write_local_index(old_path, info)

    if new_folder != old_folder:
        try:
            os.rename(old_path, new_path)
        except OSError as e:
            raise OSError(
                f"Impossible de renommer le dossier (ouvert ailleurs?):\n"
                f"{old_folder}\n-> {new_folder}\n{e}"
            ) from e
        _log(f"Dossier: {old_folder} -> {new_folder}")
    else:
        new_path = old_path

    fresh = entry_from_info(info, new_path)
    entries = load_archive_index(root)
    out = []
    replaced = False
    for e in entries:
        if e.get("folder") == old_folder:
            merged = dict(e)
            merged.update({k: fresh[k] for k in ("folder", "title", "size", "thumb")})
            out.append(merged)
            fresh = merged
            replaced = True
        else:
            out.append(e)
    if not replaced:
        out.append(fresh)
    save_archive_index(root, out)
    fresh = dict(fresh)
    fresh["path"] = new_path
    return fresh


def write_post_txt(path: str, info: Dict[str, Any]) -> None:
    lines = [
        f"Titre: {info.get('title') or ''}",
        f"Auteur: {info.get('uploader') or info.get('creator') or ''}",
        f"Date: {fmt_upload_date(info.get('upload_date') or info.get('date') or '')}",
        f"Plateforme: {info.get('platform') or ''}",
        f"URL source: {info.get('webpage_url') or info.get('url') or ''}",
        f"Archivé le: {fmt_iso(info.get('archived_at'))}",
        f"Tags: {', '.join(parse_tags(info.get('tags') or []))}",
    ]
    if info.get("notes"):
        lines += ["", "--- Notes perso ---", "", str(info.get("notes"))]
    lines += ["", "--- Texte / description ---", "", info.get("description") or info.get("text") or ""]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


_HTML_CSS = """
body{font-family:Consolas,monospace;background:#000088;color:#55ffff;margin:0;padding:1.2rem}
a{color:#ffff55} h1{color:#ffff55;font-size:1.4rem;margin:.2rem 0 .8rem}
.box{background:#0000aa;padding:1rem 1.2rem;border:2px solid #55ffff;max-width:1100px;margin:auto}
.meta{display:grid;grid-template-columns:max-content 1fr;gap:.25rem 1rem;color:#aaffff;font-size:.92rem;margin-bottom:1rem}
.meta b{color:#ffff55;font-weight:normal}
.tags span,.tag{display:inline-block;background:#ffff55;color:#000;border-radius:3px;padding:0 .4rem;margin:0 .3rem .3rem 0;font-size:.85rem;cursor:pointer}
.notes{background:#000055;border-left:4px solid #ffff55;padding:.6rem .8rem;white-space:pre-wrap;margin:.8rem 0;color:#fff}
.desc{white-space:pre-wrap;line-height:1.45;margin-top:1rem;color:#fff;font-family:Segoe UI,Arial,sans-serif}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:.5rem;margin:.6rem 0}
.grid img{width:100%;border:1px solid #55ffff;display:block}
video,audio{max-width:100%;background:#000;display:block;margin:.4rem 0}
h2{color:#ffff55;font-size:1.05rem;margin:1.2rem 0 .4rem;border-bottom:1px solid #3355aa}
ul.files{columns:2;font-size:.85rem}
.btns{display:flex;flex-wrap:wrap;gap:.5rem}.btn{background:#ffff55;color:#000;padding:.3rem .7rem;text-decoration:none;border-radius:3px}
.tr{max-height:420px;overflow:auto;background:#000055;padding:.5rem .8rem;line-height:1.5;color:#fff;font-family:Segoe UI,Arial,sans-serif}
.ts{color:#ffff55;font-family:Consolas,monospace;margin-right:.4rem;text-decoration:none}
a.ex{display:block;padding:.5rem;border:1px solid #55ffff;text-decoration:none}
ul.links{font-size:.85rem;columns:2}
"""


def _qhref(name: str) -> str:
    return quote(name.replace("\\", "/"))


def write_local_index(folder: str, info: Dict[str, Any], media_files: Optional[List[str]] = None) -> None:
    """index.html de l'archive : média, storyboard, galerie, tags, notes, texte (liens cliquables)."""
    e = html.escape
    title = e(str(info.get("title") or "Archive"))
    src_raw = str(info.get("webpage_url") or info.get("url") or "")
    src = e(src_raw, quote=True)
    author = str(info.get("uploader") or info.get("creator") or "")
    author_url = str(info.get("uploader_url") or info.get("channel_url") or "")
    author_html = (f'<a href="{e(author_url, quote=True)}" target="_blank" rel="noopener">{e(author)}</a>'
                   if author_url and author else e(author or "—"))
    tags = parse_tags(info.get("tags") or [])
    notes = str(info.get("notes") or "")
    names = list_folder_files(folder)
    parts: List[str] = []
    main = find_main_media(folder)
    if main:
        mn = _qhref(os.path.basename(main))
        if main.lower().endswith(VIDEO_EXTS):
            poster = find_thumbnail(folder)
            pa = f' poster="{_qhref(os.path.relpath(poster, folder))}"' if poster else ""
            parts.append(f'<video controls preload="metadata"{pa} src="{mn}"></video>')
        else:
            parts.append(f'<audio controls src="{mn}"></audio>')
    sb = list_storyboard(folder)
    if sb:
        parts.append("<h2>Storyboard</h2><div class='grid'>" + "".join(
            f'<a href="{_qhref(os.path.relpath(p, folder))}" target="_blank"><img loading="lazy" alt="image" src="{_qhref(os.path.relpath(p, folder))}"></a>'
            for p in sb) + "</div>")
    imgs = list_images(folder)
    if imgs:
        parts.append(f"<h2>Images ({len(imgs)})</h2><div class='grid'>" + "".join(
            f'<a href="{_qhref(os.path.basename(p))}" target="_blank"><img loading="lazy" alt="image" src="{_qhref(os.path.basename(p))}"></a>'
            for p in imgs) + "</div>")
    web_links = []
    for fname, lab in (("lecture.html", "📰 Version lecture"), ("page.html", "🌐 Page complète (hors ligne)"),
                       (info.get("page_pdf") or "page_complete.pdf", "📕 PDF pleine page"),
                       (info.get("page_capture") or "capture_page.png", "🖼 Capture de la page")):
        if fname and os.path.isfile(os.path.join(folder, fname)):
            web_links.append(f'<a class="btn" href="{_qhref(fname)}" target="_blank">{lab}</a>')
    if web_links:
        parts.insert(0, "<p class='btns'>" + " ".join(web_links) + "</p>")
    top_sizes = set()
    for p in imgs:
        try:
            top_sizes.add(os.path.getsize(p))
        except OSError:
            pass
    pimgs = [p for p in list_page_images(folder) if os.path.getsize(p) not in top_sizes]
    if pimgs:
        parts.append(f"<h2>Images de la page ({len(pimgs)})</h2><div class='grid'>" + "".join(
            f'<a href="{_qhref(os.path.relpath(p, folder))}" target="_blank"><img loading="lazy" alt="image" '
            f'src="{_qhref(os.path.relpath(p, folder))}"></a>' for p in pimgs[:40]) + "</div>")
    exs = list_extracts(folder)
    if exs:
        items = []
        for p in exs:
            rel = _qhref(os.path.relpath(p, folder))
            n = os.path.basename(p)
            if n.lower().endswith((".jpg", ".png", ".gif", ".webp")):
                items.append(f'<a href="{rel}" target="_blank"><img loading="lazy" alt="{e(n)}" src="{rel}"></a>')
            else:
                items.append(f'<a class="ex" href="{rel}" target="_blank">{file_icon(n)} {e(n)}</a>')
        parts.append(f"<h2>Extraits et captures ({len(exs)})</h2><div class='grid'>" + "".join(items) + "</div>")
    if not main and not imgs and not web_links:
        parts.append("<p><em>Aucun fichier média téléchargé (login/DRM ou page texte seule).</em></p>")
    tr = load_transcript(folder) if os.path.isdir(folder) else {}
    tr_html = ""
    if tr.get("cues"):
        vid_js = _qhref(os.path.basename(main)) if main else ""
        rows = "".join(
            f'<div><a class="ts" href="#" onclick="return seek({t:.2f})">{fmt_ts(t)}</a> {linkify_html(x)}</div>'
            for t, x in tr["cues"][:5000])
        tr_html = (f"<h2>Transcription ({e(str(tr.get('source') or ''))}, {e(str(tr.get('lang') or '?'))})</h2>"
                   f"<div class='tr'>{rows}</div>"
                   f"<script>function seek(t){{var v=document.querySelector('video,audio');"
                   f"if(v){{v.currentTime=t;v.play();v.scrollIntoView({{behavior:'smooth'}});}}return false;}}</script>")
    links = [l for l in (info.get("links") or []) if isinstance(l, (list, tuple)) and len(l) == 2][:200]
    links_html = ""
    if links:
        links_html = "<h2>Liens (" + str(len(links)) + ")</h2><ul class='links'>" + "".join(
            f'<li><a href="{e(str(h), quote=True)}" target="_blank" rel="noopener">{e(str(t) or str(h))}</a></li>'
            for t, h in links) + "</ul>"
    tags_html = "".join(f"<span>#{e(t)}</span>" for t in tags) or "—"
    notes_html = f'<div class="notes">{linkify_html(notes)}</div>' if notes else ""
    desc = linkify_html(str(info.get("description") or info.get("text") or ""))
    files_html = "".join(
        f'<li>{file_icon(n)} <a href="{_qhref(n)}" target="_blank">{e(n)}</a></li>' for n in names)
    res = info.get("resolution") or ""
    body = f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>{_HTML_CSS}</style></head><body><div class="box">
<p><a href="../{INDEX_HTML}">← Toutes les archives</a></p>
<h1>{title}</h1>
<div class="meta">
<b>Plateforme</b><span>{e(platform_label(info.get('platform')))}</span>
<b>Auteur</b><span>{author_html}</span>
<b>Publié</b><span>{e(fmt_upload_date(info.get('upload_date') or info.get('date')))}</span>
<b>Archivé</b><span>{e(fmt_iso(info.get('archived_at')))}</span>
<b>Durée</b><span>{e(human_duration(info.get('duration')))}</span>
<b>Résolution</b><span>{e(str(res) or '—')}</span>
<b>Source</b><span><a href="{src}" target="_blank" rel="noopener">{e(src_raw)}</a></span>
<b>Tags</b><span class="tags">{tags_html}</span>
<b>Collections</b><span>{e(", ".join(c for c in (info.get("collections") or []) if isinstance(c, str)) or "—")}{" · ★ favori" if info.get("favorite") else ""}</span>
<b>En ligne</b><span>{e(ONLINE_LABELS.get(str(info.get("online_status") or ""), "jamais vérifié"))}{(" (vérifié le " + e(fmt_iso(info.get("online_checked"))) + ")") if info.get("online_checked") else ""}</span>
</div>
{notes_html}
{''.join(parts)}
{tr_html}
<h2>Texte du post</h2>
<div class="desc">{desc or '<em>(aucun texte)</em>'}</div>
{links_html}
<h2>Fichiers</h2><ul class="files">{files_html}</ul>
</div></body></html>
"""
    with open(os.path.join(folder, "index.html"), "w", encoding="utf-8") as f:
        f.write(body)


def write_global_index_html(root: str, entries: List[Dict[str, Any]]) -> None:
    """Index global joli : cartes avec miniature, recherche JS, filtres, tags cliquables."""
    page = build_global_index_html(entries, root)
    with open(os.path.join(root, INDEX_HTML), "w", encoding="utf-8") as f:
        f.write(page)


def build_global_index_html(entries: List[Dict[str, Any]], root: str = "") -> str:
    e = html.escape
    cards = []
    plats = set()
    colls = set()
    for x in sorted(entries, key=lambda v: v.get("archived_at") or "", reverse=True):
        folder = str(x.get("folder") or "")
        title = str(x.get("title") or folder)
        plat = str(x.get("platform") or "web")
        plats.add(plat)
        tags = parse_tags(x.get("tags") or [])
        src = str(x.get("url") or "")
        thumb = str(x.get("thumb") or "")
        hay = entry_haystack(x, full=False)
        xcols = [c for c in (x.get("collections") or []) if isinstance(c, str)]
        colls.update(xcols)
        fav = bool(x.get("favorite"))
        ost = str(x.get("online_status") or "")
        badge = (f'<span class="on" title="{e(ONLINE_LABELS.get(ost, ""), quote=True)}">{ONLINE_ICONS.get(ost, "")}</span>'
                 if ost else "")
        img = (f'<a href="{_qhref(folder)}/index.html"><img loading="lazy" alt="miniature" '
               f'src="{_qhref(folder)}/{_qhref(thumb)}"></a>' if thumb
               else f'<a class="noimg" href="{_qhref(folder)}/index.html">{e(platform_label(plat))}</a>')
        tag_html = "".join(f'<span class="tag" data-tag="{e(t.lower(), quote=True)}">#{e(t)}</span>' for t in tags)
        notes = str(x.get("notes") or "")
        cards.append(
            f'<div class="card" data-q="{e(hay, quote=True)}" data-plat="{e(plat, quote=True)}" '
            f'data-tags="{e("|".join(t.lower() for t in tags), quote=True)}" '
            f'data-date="{e(str(x.get("archived_at") or ""), quote=True)}" '
            f'data-title="{e(title.lower(), quote=True)}" data-size="{int(x.get("size") or 0)}" '
            f'data-coll="{e("|".join(c.lower() for c in xcols), quote=True)}" data-fav="{1 if fav else 0}" '
            f'data-on="{e(ost, quote=True)}">'
            f'{img}<div class="body">'
            f'<div class="t">{"<span class=fav>★</span> " if fav else ""}{badge}'
            f'<a href="{_qhref(folder)}/index.html">{e(title)}</a></div>'
            + (f'<div class="m">📚 {e(", ".join(xcols))}</div>' if xcols else "") +
            f'<div class="m">{e(platform_label(plat))} · {e(str(x.get("uploader") or ""))}</div>'
            f'<div class="m">Archivé {e(fmt_iso(x.get("archived_at")))} · {e(human_duration(x.get("duration")))} · {e(human_size(x.get("size")))}</div>'
            f'<div class="tags">{tag_html}</div>'
            + (f'<div class="notes">{linkify_html(notes[:200])}</div>' if notes else "")
            + f'<div class="s">{linkify_html(str(x.get("text_snippet") or "")[:220])}</div>'
            f'<div class="l"><a href="{e(src, quote=True)}" target="_blank" rel="noopener">🌐 original</a> · '
            f'<a href="{_qhref(folder)}/">📁 dossier</a></div>'
            f'</div></div>'
        )
    opts = "".join(f'<option value="{e(p, quote=True)}">{e(platform_label(p))}</option>' for p in sorted(plats))
    copts = "".join(f'<option value="{e(c.lower(), quote=True)}">📚 {e(c)}</option>'
                    for c in sorted(colls | set(load_collections(root) if root else []), key=str.lower))
    page = f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Archiveur — archives locales</title>
<style>
body{{font-family:Consolas,monospace;background:#000088;color:#55ffff;margin:0;padding:1rem}}
h1{{color:#ffff55;margin:.2rem 0 .8rem}} a{{color:#ffff55}}
.bar{{display:flex;flex-wrap:wrap;gap:.5rem;align-items:center;position:sticky;top:0;background:#000088;padding:.5rem 0;z-index:2}}
input,select{{padding:.4rem;background:#000055;color:#fff;border:1px solid #55ffff;font-family:inherit}}
input{{flex:1;min-width:240px;max-width:520px}}
#n{{color:#fff}} #tagf{{color:#000;background:#ffff55;padding:0 .4rem;border-radius:3px;cursor:pointer;display:none}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:.9rem;margin-top:.6rem}}
.card{{background:#0000aa;border:1px solid #55ffff;display:flex;flex-direction:column}}
.card img{{width:100%;aspect-ratio:16/9;object-fit:cover;display:block;background:#000}}
.noimg{{display:flex;align-items:center;justify-content:center;aspect-ratio:16/9;background:#000055;text-decoration:none;font-size:1.3rem}}
.body{{padding:.6rem .7rem;display:flex;flex-direction:column;gap:.25rem}}
.t{{font-size:1.05rem;font-weight:bold}} .m{{color:#aaffff;font-size:.82rem}}
.s{{color:#ddd;font-size:.82rem;white-space:pre-wrap;max-height:5.5em;overflow:hidden;font-family:Segoe UI,Arial,sans-serif}}
.notes{{color:#fff;border-left:3px solid #ffff55;padding-left:.4rem;font-size:.82rem;white-space:pre-wrap}}
.tag{{display:inline-block;background:#ffff55;color:#000;border-radius:3px;padding:0 .4rem;margin:0 .3rem .2rem 0;font-size:.8rem;cursor:pointer}}
.l{{font-size:.85rem;margin-top:.2rem}} .hidden{{display:none}} .fav{{color:#ffff55}} .on{{margin-right:.3rem}}
</style></head><body>
<h1>📦 Archiveur — archives locales</h1>
<div class="bar">
<input id="q" placeholder="🔎 titre, texte, auteur, tags, notes…" oninput="apply()">
<select id="p" onchange="apply()"><option value="">Toutes plateformes</option>{opts}</select>
<select id="s" onchange="apply()"><option value="date_desc">Date ↓</option><option value="date_asc">Date ↑</option>
<option value="name_asc">Nom A→Z</option><option value="name_desc">Nom Z→A</option>
<option value="size_desc">Taille ↓</option><option value="size_asc">Taille ↑</option></select>
<select id="c" onchange="apply()"><option value="">Toutes collections</option><option value="__fav__">★ Favoris</option>
<option value="__off__">🔴 Supprimées en ligne</option>{copts}</select>
<span id="tagf" title="Retirer le filtre" onclick="tag='';apply()"></span>
<span id="n"></span>
</div>
<div class="grid" id="g">
{''.join(cards) if cards else '<p>Aucune archive.</p>'}
</div>
<script>
var tag='';
document.addEventListener('click',function(ev){{var t=ev.target;if(t.classList&&t.classList.contains('tag')){{tag=t.getAttribute('data-tag');apply();}}}});
function apply(){{
  var q=(document.getElementById('q').value||'').toLowerCase().split(/\\s+/).filter(Boolean);
  var p=document.getElementById('p').value, s=document.getElementById('s').value;
  var g=document.getElementById('g'), cards=[].slice.call(g.querySelectorAll('.card')), n=0;
  cards.forEach(function(c){{
    var hay=c.getAttribute('data-q')||'', ok=true;
    for(var i=0;i<q.length;i++){{if(hay.indexOf(q[i].replace(/^#/,''))<0){{ok=false;break;}}}}
    if(p&&c.getAttribute('data-plat')!==p)ok=false;
    if(tag&&('|'+c.getAttribute('data-tags')+'|').indexOf('|'+tag+'|')<0)ok=false;
    var cv=document.getElementById('c').value;
    if(cv==='__fav__'){{if(c.getAttribute('data-fav')!=='1')ok=false;}}
    else if(cv==='__off__'){{var o=c.getAttribute('data-on');if(o!=='offline'&&o!=='restricted')ok=false;}}
    else if(cv&&('|'+c.getAttribute('data-coll')+'|').indexOf('|'+cv+'|')<0)ok=false;
    c.classList.toggle('hidden',!ok); if(ok)n++;
  }});
  cards.sort(function(a,b){{
    var k=s.split('_')[0], d=s.endsWith('desc')?-1:1, x, y;
    if(k==='size'){{x=+a.getAttribute('data-size');y=+b.getAttribute('data-size');}}
    else if(k==='name'){{x=a.getAttribute('data-title');y=b.getAttribute('data-title');}}
    else {{x=a.getAttribute('data-date');y=b.getAttribute('data-date');}}
    return x<y?-d:(x>y?d:0);
  }}).forEach(function(c){{g.appendChild(c);}});
  var tf=document.getElementById('tagf'); tf.style.display=tag?'inline-block':'none'; tf.textContent=tag?('#'+tag+' ✖'):'';
  document.getElementById('n').textContent=n+' / '+cards.length+' archive(s)';
}}
apply();
</script>
</body></html>
"""
    return page
_YTDLP_NOISE = re.compile(
    r"(Video Thumbnail \d+ does not exist|Downloading video thumbnail \d+|^\[download\]\s+\d+(\.\d+)?%)", re.I)


class YTDLPLogger:
    def __init__(self, log: Callable[[str], None]):
        self._log = log

    def debug(self, msg):
        if msg and not str(msg).startswith("[debug]") and not _YTDLP_NOISE.search(str(msg)):
            self._log(str(msg))

    def info(self, msg):
        if msg and not _YTDLP_NOISE.search(str(msg)):
            self._log(str(msg))

    def warning(self, msg):
        if msg:
            self._log(f"! {msg}")

    def error(self, msg):
        if msg:
            self._log(f"X {msg}")



# Tri yt-dlp : H.264 (avc1) + AAC (m4a) en MP4 d'abord → lisible par le lecteur Windows
# sans codec AV1/VP9 ; ensuite la meilleure résolution parmi ceux-là.
FORMAT_SORT_COMPAT = ["vcodec:h264", "acodec:aac", "res", "ext:mp4:m4a"]


def build_format_candidates(quality: str, has_ff: bool) -> List[str]:
    h = {"720": 720, "480": 480}.get(str(quality))
    if quality == "audio":
        return ["ba/b"] if has_ff else ["ba[ext=m4a]/ba/b"]
    if has_ff:
        if h:
            return [f"bv*[height<={h}]+ba/b[height<={h}]/bv*+ba/b"]
        return ["bv*+ba/b"]
    if h:
        return [
            f"b[height<={h}][acodec!=none][vcodec!=none][ext=mp4]/b[height<={h}][acodec!=none][vcodec!=none]/b[acodec!=none][vcodec!=none]",
            "18/best",
        ]
    return [
        "b*[acodec!=none][vcodec!=none][ext=mp4]/b[acodec!=none][vcodec!=none]/best[acodec!=none][vcodec!=none]",
        "18/22/best[height<=720][ext=mp4]/worst[ext=mp4]/best",
    ]


def _check_cancel(cancel_event: Optional[threading.Event]) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise ArchiveCancelled("Archivage annulé par l'utilisateur.")


def archive_with_ytdlp(
    url: str,
    root: str,
    log: Callable[[str], None],
    *,
    cookies_browser: Optional[str] = None,
    progress_hook: Optional[Callable[[Dict[str, Any]], None]] = None,
    quality: str = "best",
    subtitles: bool = True,
    storyboard: bool = True,
    cancel_event: Optional[threading.Event] = None,
    auto_convert: bool = True,
) -> Dict[str, Any]:
    import yt_dlp

    platform = detect_platform(url)
    ff_exe = find_ffmpeg()
    has_ff = ff_exe is not None
    ff_dir = os.path.dirname(ff_exe) if ff_exe else ffmpeg_location()
    if ff_dir:
        _prepend_path(ff_dir)
    if not has_ff:
        log("Sans ffmpeg: formats déjà combinés uniquement (pas de fusion).")
    format_candidates = build_format_candidates(quality, has_ff)

    def _hook(d: Dict[str, Any]) -> None:
        _check_cancel(cancel_event)
        if progress_hook:
            progress_hook(d)

    stamp = datetime.now().strftime("%Y-%m-%d")
    tmp_name = f"_tmp_{stamp}_{os.getpid()}_{threading.get_ident()}"
    out_tmp = os.path.join(root, tmp_name)
    os.makedirs(out_tmp, exist_ok=True)
    outtmpl = os.path.join(out_tmp, "%(title).80B [%(id)s].%(ext)s")

    info: Dict[str, Any] = {}
    last_err: Optional[BaseException] = None
    attempts = list(format_candidates)
    subs_on = bool(subtitles)
    ai = 0
    while ai < len(attempts):
        fmt = attempts[ai]
        ai += 1
        opts: Dict[str, Any] = {
            "outtmpl": outtmpl,
            "format": fmt,
            "writesubtitles": subs_on,
            "writeautomaticsub": subs_on,
            "subtitleslangs": ["fr", "fr-FR", "fr-CA", "en", "en-US"],
            "subtitlesformat": "vtt/srt/best",
            "writethumbnail": True,
            "writeinfojson": True,
            "writedescription": True,
            "noplaylist": True,
            "ignoreerrors": False,
            "quiet": True,
            "no_warnings": False,
            "noprogress": True,
            "logger": YTDLPLogger(log),
            "progress_hooks": [_hook],
            "http_headers": {"User-Agent": USER_AGENT},
        }
        if quality != "audio":
            opts["format_sort"] = list(FORMAT_SORT_COMPAT)
        if has_ff:
            if quality == "audio":
                opts["postprocessors"] = [{
                    "key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192",
                }]
            else:
                opts["merge_output_format"] = "mp4"
            if ff_dir:
                opts["ffmpeg_location"] = ff_dir
        if cookies_browser:
            opts["cookiesfrombrowser"] = (cookies_browser,)
        try:
            _check_cancel(cancel_event)
            log(f"yt-dlp format: {fmt}  (qualité: {LABEL_BY_QUALITY.get(quality, quality)})")
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True) or {}
                if "entries" in info and info["entries"]:
                    info = info["entries"][0] or info
            last_err = None
            break
        except BaseException as e:  # noqa: B902 — inclut ArchiveCancelled levé dans le hook
            if isinstance(e, (KeyboardInterrupt, SystemExit)):
                raise
            if isinstance(e, ArchiveCancelled) or (cancel_event is not None and cancel_event.is_set()):
                shutil.rmtree(out_tmp, ignore_errors=True)
                raise ArchiveCancelled("Archivage annulé par l'utilisateur.") from None
            last_err = e
            if subs_on and "subtitle" in str(e).lower():
                log("! Sous-titres refusés par le site (souvent 429) — nouvel essai sans sous-titres.")
                subs_on = False
                ai -= 1
            else:
                log(f"yt-dlp essai format échoué: {e}")
            try:
                for name in list(os.listdir(out_tmp)):
                    try:
                        os.remove(os.path.join(out_tmp, name))
                    except OSError:
                        pass
            except OSError:
                pass
    if last_err is not None or not info:
        err = str(last_err or "aucune info")
        log(f"yt-dlp: {err}")
        shutil.rmtree(out_tmp, ignore_errors=True)
        raise last_err if last_err else RuntimeError(err)

    raw_title = info.get("title") or info.get("id") or "sans-titre"
    title = pick_archive_title({
        "title": raw_title,
        "description": info.get("description") or "",
        "text": info.get("description") or "",
        "uploader": info.get("uploader") or info.get("creator") or info.get("channel"),
        "id": info.get("id") or "id",
    })
    vid = info.get("id") or "id"
    folder_name = f"{stamp}_{platform}_{slugify(title)}_{slugify(str(vid), 20)}"
    final_dir = os.path.join(root, folder_name)
    n = 2
    while os.path.exists(final_dir):
        final_dir = os.path.join(root, f"{folder_name}_{n}")
        n += 1
    os.rename(out_tmp, final_dir)

    vcodec_out, acodec_out = info.get("vcodec"), info.get("acodec")
    converted_at = ""
    if quality != "audio" and has_ff:
        main_v = find_main_media(final_dir)
        if main_v and main_v.lower().endswith(VIDEO_EXTS):
            try:
                c = probe_codecs(main_v)
                if c.get("vcodec"):
                    vcodec_out, acodec_out = c.get("vcodec"), c.get("acodec") or acodec_out
                if auto_convert and c.get("vcodec") and not is_compatible(main_v, c):
                    log(f"🎬 Vidéo {codec_label(c)} → conversion MP4 compatible (H.264/AAC)…")

                    def _cstats(s):
                        if progress_hook:
                            try:
                                progress_hook({"status": "converting", **s})
                            except Exception:
                                pass
                    r = convert_to_compatible(main_v, log, cancel_event=cancel_event, stats=_cstats)
                    if r.get("ok"):
                        vcodec_out, acodec_out = r.get("vcodec"), r.get("acodec")
                        converted_at = datetime.now().isoformat(timespec="seconds")
            except Exception as ce:
                logger.exception("conversion")
                log(f"! Conversion MP4 impossible ({ce}) — fichier original gardé.")

    media_files = [n for n in os.listdir(final_dir) if n.lower().endswith(MEDIA_EXTS)]
    w, h = info.get("width"), info.get("height")
    resolution = f"{w}x{h}" if w and h else (info.get("resolution") or "")
    if quality == "audio":
        resolution = "audio"
    info_out = {
        "title": title,
        "id": vid,
        "uploader": info.get("uploader") or info.get("creator") or info.get("channel"),
        "uploader_url": info.get("uploader_url") or info.get("channel_url") or "",
        "channel": info.get("channel") or "",
        "channel_url": info.get("channel_url") or "",
        "upload_date": info.get("upload_date") or "",
        "description": info.get("description") or "",
        "webpage_url": info.get("webpage_url") or url,
        "url": url,
        "platform": platform,
        "extractor": info.get("extractor"),
        "duration": info.get("duration"),
        "resolution": resolution,
        "fps": info.get("fps"),
        "vcodec": vcodec_out,
        "acodec": acodec_out,
        "converted_h264": converted_at,
        "view_count": info.get("view_count"),
        "like_count": info.get("like_count"),
        "source_tags": (info.get("tags") or [])[:30],
        "tags": [],
        "notes": "",
        "quality": quality,
        "archived_at": datetime.now().isoformat(timespec="seconds"),
        "folder": os.path.basename(final_dir),
        "media_files": media_files,
        "method": "yt-dlp",
    }
    if storyboard and quality != "audio":
        try:
            frames = generate_storyboard(final_dir, SB_FRAMES, duration=info.get("duration"))
            if frames:
                log(f"Storyboard: {len(frames)} images")
        except Exception:
            logger.exception("storyboard")
    try:
        tr = build_transcript(final_dir, force=True)
        if tr and tr.get("cues"):
            info_out["transcript_lang"] = tr.get("lang") or ""
            info_out["transcript_source"] = "sous-titres"
            log(f"🗣 Transcription : {len(tr['cues'])} lignes ({tr.get('lang') or '?'})")
    except Exception:
        logger.exception("transcription sous-titres")
    _write_json_atomic(os.path.join(final_dir, "info.json"), info_out)
    write_post_txt(os.path.join(final_dir, "post.txt"), info_out)
    write_local_index(final_dir, info_out)
    return info_out


def archive_fallback_html(
    url: str,
    root: str,
    log: Callable[[str], None],
    cancel_event: Optional[threading.Event] = None,
) -> Dict[str, Any]:
    platform = detect_platform(url)
    log(f"Fallback HTML pour {platform}: {url}")
    _check_cancel(cancel_event)
    raw = http_get(url)
    try:
        text = raw.decode("utf-8")
    except Exception:
        text = raw.decode("latin-1", errors="replace")
    og = extract_og(text)
    raw_title = og.get("og:title") or og.get("twitter:title") or "sans-titre"
    desc = og.get("og:description") or og.get("twitter:description") or ""
    title = pick_archive_title({"title": raw_title, "description": desc, "text": desc})
    stamp = datetime.now().strftime("%Y-%m-%d")
    folder_name = f"{stamp}_{platform}_{slugify(title)}_html"
    final_dir = os.path.join(root, folder_name)
    n = 2
    while os.path.exists(final_dir):
        final_dir = os.path.join(root, f"{folder_name}_{n}")
        n += 1
    os.makedirs(final_dir, exist_ok=True)
    with open(os.path.join(final_dir, "page.html"), "w", encoding="utf-8") as f:
        f.write(text)
    media_files: List[str] = []
    seen_urls = set()
    for key, prefix in (("og:image", "image"), ("twitter:image", "twimage"), ("og:video", "video"), ("og:video:url", "video2")):
        media_url = og.get(key)
        if not media_url or media_url in seen_urls:
            continue
        seen_urls.add(media_url)
        try:
            _check_cancel(cancel_event)
            data = http_get(media_url)
            ext = os.path.splitext(urlparse(media_url).path)[1] or (".mp4" if "video" in key else ".jpg")
            if len(ext) > 5:
                ext = ".bin"
            fname = f"{prefix}{ext}"
            with open(os.path.join(final_dir, fname), "wb") as f:
                f.write(data)
            media_files.append(fname)
            log(f"Média sauvé: {fname}")
        except ArchiveCancelled:
            shutil.rmtree(final_dir, ignore_errors=True)
            raise
        except Exception as e:
            log(f"Échec média {key}: {e}")
    info_out = {
        "title": title,
        "id": "",
        "uploader": "",
        "upload_date": "",
        "description": desc,
        "text": desc,
        "webpage_url": og.get("og:url") or url,
        "url": url,
        "platform": platform,
        "tags": [],
        "notes": "",
        "archived_at": datetime.now().isoformat(timespec="seconds"),
        "folder": os.path.basename(final_dir),
        "media_files": media_files,
        "method": "html-fallback",
        "links": [[u, u] for u in extract_urls(desc)],
        "note": "Archivage best-effort (métadonnées Open Graph). Login/DRM peuvent bloquer le média.",
    }
    _write_json_atomic(os.path.join(final_dir, "info.json"), info_out)
    write_post_txt(os.path.join(final_dir, "post.txt"), info_out)
    write_local_index(final_dir, info_out)
    return info_out


def archive_url(
    url: str,
    root: str,
    log: Callable[[str], None],
    *,
    cookies_browser: Optional[str] = None,
    progress_hook: Optional[Callable[[Dict[str, Any]], None]] = None,
    quality: str = "best",
    subtitles: bool = True,
    storyboard: bool = True,
    cancel_event: Optional[threading.Event] = None,
    tags: Any = None,
    notes: str = "",
    auto_convert: bool = True,
    web_capture: bool = True,
    use_fx: bool = True,
    page_mode: bool = False,
) -> Dict[str, Any]:
    url = (url or "").strip()
    if not url:
        raise ValueError("URL vide")
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    os.makedirs(root, exist_ok=True)
    platform = detect_platform(url)
    log(f"> Archivage ({platform}): {url}")
    if page_mode:
        info = archive_webpage(url, root, log, cancel_event=cancel_event, capture=web_capture)
        if tags or notes:
            info = update_tags_notes(root, str(info["folder"]), tags or [], notes or "")
        return info
    try:
        info = archive_with_ytdlp(
            url, root, log, cookies_browser=cookies_browser, progress_hook=progress_hook,
            quality=quality, subtitles=subtitles, storyboard=storyboard, cancel_event=cancel_event,
            auto_convert=auto_convert,
        )
    except ArchiveCancelled:
        raise
    except Exception as e1:
        log(f"yt-dlp a échoué ({e1})")
        info = None
        if platform == "x" and use_fx:
            log("Post X sans vidéo (ou bloqué) → texte, photos et fil via fxtwitter…")
            try:
                info = archive_x_fx(url, root, log, cancel_event=cancel_event)
            except ArchiveCancelled:
                raise
            except Exception as ex:
                log(f"fxtwitter : {ex}")
        if info is None and platform == "web":
            try:
                info = archive_webpage(url, root, log, cancel_event=cancel_event, capture=web_capture)
            except ArchiveCancelled:
                raise
            except Exception as ex:
                logger.exception("page web")
                log(f"Page web complète impossible ({friendly_error(ex)}) — repli métadonnées.")
        if info is None and platform in ("x", "facebook", "instagram", "web"):
            log("Tentative fallback HTML (limites login/DRM possibles)…")
            try:
                info = archive_fallback_html(url, root, log, cancel_event=cancel_event)
            except ArchiveCancelled:
                raise
            except Exception as e2:
                raise RuntimeError(
                    f"Échec yt-dlp et fallback HTML.\n"
                    f"yt-dlp: {e1}\nfallback: {e2}\n"
                    "Pour X/Facebook privés: cochez cookies navigateur, ou la page exige un login/DRM."
                ) from e2
        elif info is None:
            raise
    else:
        if platform == "x" and use_fx:
            enrich_x_thread(os.path.join(root, str(info.get("folder"))), url, log)
            info = load_info(os.path.join(root, str(info.get("folder")))) or info
    if tags or notes:
        info = update_tags_notes(root, str(info["folder"]), tags or [], notes or "")
    return info



# ================================================================= codecs / lecteurs
COMPAT_VCODECS = {"h264"}
COMPAT_ACODECS = {"aac", "mp3", ""}
COMPAT_PIXFMT = {"yuv420p", "yuvj420p", ""}


def find_ffprobe() -> Optional[str]:
    ff = find_ffmpeg()
    if ff:
        cand = os.path.join(os.path.dirname(ff), "ffprobe.exe" if sys.platform.startswith("win") else "ffprobe")
        if os.path.isfile(cand):
            return cand
    w = shutil.which("ffprobe")
    return os.path.abspath(w) if w else None


def probe_codecs(video: str) -> Dict[str, Any]:
    """{'vcodec','acodec','pix_fmt','duration','width','height'} via ffprobe (repli ffmpeg -i)."""
    out: Dict[str, Any] = {"vcodec": "", "acodec": "", "pix_fmt": "", "duration": None, "width": None, "height": None}
    fp = find_ffprobe()
    try:
        if fp:
            r = subprocess.run([fp, "-v", "error", "-show_entries",
                                "stream=codec_type,codec_name,pix_fmt,width,height:format=duration",
                                "-of", "json", video], **_hidden_kwargs(), timeout=30)
            data = json.loads((r.stdout or b"{}").decode("utf-8", errors="replace") or "{}")
            for st in data.get("streams") or []:
                if st.get("codec_type") == "video" and not out["vcodec"] and st.get("codec_name") not in ("mjpeg", "png", "webp"):
                    out["vcodec"] = str(st.get("codec_name") or "")
                    out["pix_fmt"] = str(st.get("pix_fmt") or "")
                    out["width"], out["height"] = st.get("width"), st.get("height")
                elif st.get("codec_type") == "audio" and not out["acodec"]:
                    out["acodec"] = str(st.get("codec_name") or "")
            try:
                out["duration"] = float((data.get("format") or {}).get("duration") or 0) or None
            except (TypeError, ValueError):
                pass
            return out
        ff = find_ffmpeg()
        if ff:
            r = subprocess.run([ff, "-hide_banner", "-i", video], **_hidden_kwargs(), timeout=30)
            err = (r.stderr or b"").decode("utf-8", errors="replace")
            m = re.search(r"Video:\s*([a-z0-9_]+)[^,\n]*(?:,\s*([a-z0-9_]+))?", err)
            if m:
                out["vcodec"], out["pix_fmt"] = m.group(1), (m.group(2) or "")
            m = re.search(r"Audio:\s*([a-z0-9_]+)", err)
            if m:
                out["acodec"] = m.group(1)
            out["duration"] = probe_duration(video)
    except Exception:
        logger.exception("probe_codecs %s", video)
    return out


def is_compatible(video: str, c: Optional[Dict[str, Any]] = None) -> bool:
    """True si lisible par le lecteur Windows sans extension : MP4 + H.264 (yuv420p) + AAC/MP3."""
    c = c if c is not None else probe_codecs(video)
    if not c.get("vcodec"):
        return True  # inconnu / pas de vidéo : on ne touche pas
    ext = os.path.splitext(video)[1].lower()
    return (ext in (".mp4", ".m4v", ".mov") and c.get("vcodec") in COMPAT_VCODECS
            and (c.get("acodec") or "") in COMPAT_ACODECS and (c.get("pix_fmt") or "") in COMPAT_PIXFMT)


def codec_label(c: Dict[str, Any]) -> str:
    v = {"av1": "AV1", "vp9": "VP9", "vp8": "VP8", "hevc": "HEVC (H.265)", "h264": "H.264"}.get(
        str(c.get("vcodec") or ""), str(c.get("vcodec") or "?").upper())
    a = str(c.get("acodec") or "")
    return f"{v} + {a.upper()}" if a else v


# ---------------------------------------------------------------- conversion rapide (oct. 2026)
# Encodeur matériel détecté une fois (test réel de 1 s), mis en cache dans archiveur_encodeur.json.
# Ordre : NVIDIA NVENC > Intel QSV > AMD AMF > Media Foundation (matériel Windows) > libx264 veryfast.
# Réglage optionnel dans archiveur_config.json : "video_encoder": "auto" (défaut) | "x264" | "h264_nvenc"…
ENC_CACHE_FILE = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "Archiveur",
                              "encodeur.json")  # cache hors du dossier web
ENC_CACHE_TTL = 7 * 86400
HW_ENCODERS = ["h264_nvenc", "h264_qsv", "h264_amf", "h264_mf"]
ENCODER_LABELS = {"h264_nvenc": "NVIDIA NVENC", "h264_qsv": "Intel Quick Sync", "h264_amf": "AMD AMF",
                  "h264_mf": "Media Foundation (GPU)", "libx264": "libx264 (processeur)"}
_ENC_LOCK = threading.Lock()
_ENC_MEM: Dict[str, Any] = {}


def _encoder_video_args(enc: str) -> List[str]:
    """Arguments vidéo par encodeur — qualité visuelle ~ libx264 crf 23."""
    if enc == "h264_nvenc":
        return ["-c:v", "h264_nvenc", "-preset", "p4", "-tune", "hq", "-rc", "vbr", "-cq", "23", "-b:v", "0",
                "-profile:v", "high", "-pix_fmt", "yuv420p"]
    if enc == "h264_qsv":
        return ["-c:v", "h264_qsv", "-preset", "faster", "-global_quality", "23", "-look_ahead", "0",
                "-pix_fmt", "nv12"]
    if enc == "h264_amf":
        return ["-c:v", "h264_amf", "-quality", "balanced", "-rc", "cqp", "-qp_i", "21", "-qp_p", "23",
                "-pix_fmt", "yuv420p"]
    if enc == "h264_mf":
        return ["-c:v", "h264_mf", "-hw_encoding", "1", "-rate_control", "quality", "-quality", "70",
                "-scenario", "archive", "-pix_fmt", "nv12"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-threads", "0", "-pix_fmt", "yuv420p"]


def _test_encoder(ff: str, enc: str) -> bool:
    """Encode 1 s d'une mire synthétique : vrai si l'encodeur fonctionne réellement sur ce PC."""
    try:
        r = subprocess.run([ff, "-hide_banner", "-nostdin", "-loglevel", "error", "-f", "lavfi",
                            "-i", "testsrc2=size=1280x720:rate=30", "-t", "1", *_encoder_video_args(enc),
                            "-f", "null", "-"], **_hidden_kwargs(), timeout=25)
        return r.returncode == 0
    except Exception:
        return False


def _encoder_pref() -> str:
    try:
        with open(CFG_FILE, "r", encoding="utf-8") as f:
            v = str((json.load(f) or {}).get("video_encoder") or "auto").strip().lower()
    except Exception:
        v = "auto"
    if v in ("x264", "libx264", "cpu", "logiciel"):
        return "libx264"
    return v if v in HW_ENCODERS else "auto"


def pick_video_encoder(log: Optional[Callable[[str], None]] = None, force: bool = False,
                       exclude: Optional[List[str]] = None) -> str:
    """Encodeur H.264 à utiliser (cache mémoire + fichier, re-test après 7 jours ou si ffmpeg change)."""
    ff = find_ffmpeg()
    if not ff:
        return "libx264"
    pref = _encoder_pref()
    if pref == "libx264":
        return "libx264"
    try:
        st = os.stat(ff)
        key = f"{os.path.abspath(ff)}|{int(st.st_mtime)}|{st.st_size}"
    except OSError:
        key = ff
    excl = set(exclude or [])
    with _ENC_LOCK:
        if not force and not excl:
            if _ENC_MEM.get("key") == key and _ENC_MEM.get("encoder"):
                enc = _ENC_MEM["encoder"]
                return pref if pref != "auto" and pref in (_ENC_MEM.get("ok") or []) else enc
            try:
                with open(ENC_CACHE_FILE, "r", encoding="utf-8") as f:
                    d = json.load(f)
                if (isinstance(d, dict) and d.get("key") == key and d.get("encoder")
                        and time.time() - float(d.get("time") or 0) < ENC_CACHE_TTL):
                    _ENC_MEM.clear()
                    _ENC_MEM.update(d)
                    enc = str(d["encoder"])
                    return pref if pref != "auto" and pref in (d.get("ok") or []) else enc
            except Exception:
                pass
        ok: List[str] = []
        order = ([pref] if pref != "auto" else []) + [e for e in HW_ENCODERS if e != pref]
        for enc in order:
            if enc in excl:
                continue
            if _test_encoder(ff, enc):
                ok.append(enc)
                if pref == "auto" or enc == pref:
                    break
        enc = ok[0] if ok else "libx264"
        d = {"key": key, "encoder": enc, "ok": ok, "excluded": sorted(excl), "time": time.time(),
             "date": datetime.now().isoformat(timespec="seconds")}
        _ENC_MEM.clear()
        _ENC_MEM.update(d)
        try:
            os.makedirs(os.path.dirname(ENC_CACHE_FILE), exist_ok=True)
            _write_json_atomic(ENC_CACHE_FILE, d)
        except Exception:
            pass
        if log:
            log(f"⚙ Encodeur vidéo détecté : {ENCODER_LABELS.get(enc, enc)}")
        return enc


def fmt_speed(x: Optional[float]) -> str:
    if not x or x <= 0:
        return ""
    return (f"{x:.1f}" if x < 10 else f"{x:.0f}").replace(".", ",") + "×"


def convert_to_compatible(video: str, log: Callable[[str], None],
                          progress: Optional[Callable[[float], None]] = None,
                          cancel_event: Optional[threading.Event] = None,
                          stats: Optional[Callable[[Dict[str, Any]], None]] = None) -> Dict[str, Any]:
    """MP4 H.264 + AAC compatible, le plus vite possible :
    - vidéo déjà H.264 (yuv420p) → copie (remux instantané) ; audio AAC/MP3 → copie, sinon AAC seul ;
    - sinon ré-encodage avec l'encodeur matériel détecté (repli automatique sur libx264 veryfast).
    Remplace le fichier (même nom, extension .mp4). Retourne {'ok', 'path', 'vcodec', 'acodec', 'before', ...}.
    stats(dict) reçoit pct, speed (×), eta (s), mode ('remux'|'audio'|'encode'), encoder, elapsed."""
    ff = find_ffmpeg()
    if not ff:
        raise RuntimeError("ffmpeg introuvable — conversion impossible.")
    c = probe_codecs(video)
    base = os.path.splitext(video)[0]
    final = base + ".mp4"
    tmp = base + ".h264.tmp"
    v_ok = c.get("vcodec") == "h264" and (c.get("pix_fmt") or "") in COMPAT_PIXFMT
    if not c.get("acodec"):
        aargs: List[str] = []
        a_ok = True
    elif c.get("acodec") in ("aac", "mp3"):
        aargs = ["-c:a", "copy"]
        a_ok = True
    else:
        aargs = ["-c:a", "aac", "-b:a", "160k"]
        a_ok = False
    mode = ("remux" if a_ok else "audio") if v_ok else "encode"
    enc = "copy" if v_ok else pick_video_encoder(log)
    dur = c.get("duration") or probe_duration(video) or 0
    t0 = time.time()

    def _emit(pct: float, speed: Optional[float] = None, done: bool = False) -> None:
        if not stats:
            return
        el = time.time() - t0
        eta = None
        if 0.5 < pct < 100 and el > 1.5:
            eta = el * (100.0 - pct) / pct
        try:
            stats({"pct": pct, "speed": speed, "eta": eta, "mode": mode, "encoder": enc,
                   "elapsed": el, "done": done})
        except Exception:
            pass

    def _cmd(e: str) -> List[str]:
        vargs = ["-c:v", "copy"] if e == "copy" else [*_encoder_video_args(e),
                                                       "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2"]
        return [ff, "-hide_banner", "-nostdin", "-y", "-i", video, "-map", "0:v:0", "-map", "0:a:0?",
                *vargs, *aargs, "-movflags", "+faststart", "-f", "mp4",
                "-progress", "pipe:1", "-nostats", "-loglevel", "error", tmp]

    def _run(e: str) -> Tuple[int, List[str], bool]:
        kw = _hidden_kwargs()
        kw["stderr"] = subprocess.STDOUT
        proc = subprocess.Popen(_cmd(e), **kw)
        errs: List[str] = []
        last = -1.0
        last_t = 0.0
        speed: Optional[float] = None
        cancelled = False
        try:
            for raw in iter(proc.stdout.readline, b""):  # type: ignore[union-attr]
                if cancel_event is not None and cancel_event.is_set():
                    cancelled = True
                    proc.kill()
                    break
                line = raw.decode("utf-8", errors="replace").strip()
                if line.startswith("speed="):
                    m = re.search(r"([\d.]+)\s*x", line)
                    if m:
                        try:
                            speed = float(m.group(1))
                        except ValueError:
                            pass
                elif line.startswith("out_time_us=") or line.startswith("out_time_ms="):
                    try:
                        us = int(line.split("=", 1)[1])
                    except ValueError:
                        continue
                    if dur:
                        pct = max(0.0, min(99.0, us / 1e6 / dur * 100.0))
                        now = time.time()
                        if progress and pct - last >= 1.0:
                            last = pct
                            progress(pct)
                        if now - last_t >= 0.4:
                            last_t = now
                            _emit(pct, speed)
                elif "=" not in line and line:
                    errs.append(line)
            proc.wait(timeout=60)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
            raise
        return proc.returncode, errs, cancelled

    what = {"remux": "remux instantané (copie)", "audio": "vidéo copiée, audio → AAC",
            "encode": f"ré-encodage {ENCODER_LABELS.get(enc, enc)}"}[mode]
    log(f"🎬 Conversion {os.path.basename(video)} ({codec_label(c)} → H.264 + AAC) — {what}…")
    _emit(0.0)
    rc, errs, cancelled = _run(enc)
    if (not cancelled and enc in HW_ENCODERS
            and (rc != 0 or not os.path.isfile(tmp) or os.path.getsize(tmp) == 0)):
        log(f"! Encodeur {ENCODER_LABELS.get(enc, enc)} en échec — repli sur libx264.")
        try:
            os.remove(tmp)
        except OSError:
            pass
        enc = pick_video_encoder(log, exclude=[enc])
        if enc != "libx264":
            enc = "libx264"  # sécurité : on ne retente pas un 2e matériel au milieu d'une conversion
        _emit(0.0)
        rc, errs, cancelled = _run(enc)
    if cancelled:
        try:
            os.remove(tmp)
        except OSError:
            pass
        log("⛔ Conversion annulée — fichier original gardé.")
        return {"ok": False, "cancelled": True, "path": video, "before": c}
    if rc != 0 or not os.path.isfile(tmp) or os.path.getsize(tmp) == 0:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise RuntimeError("ffmpeg a échoué : " + (" | ".join(errs[-3:]) or f"code {rc}"))
    try:
        os.replace(tmp, final)
        if os.path.abspath(final) != os.path.abspath(video) and os.path.exists(video):
            os.remove(video)
    except OSError as e:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise OSError(f"Fichier verrouillé (ouvert dans un lecteur ?) — fermez-le et réessayez.\n{e}") from e
    after = probe_codecs(final)
    if progress:
        progress(100.0)
    el = time.time() - t0
    _emit(100.0, (dur / el) if dur and el > 0 else None, done=True)
    log(f"✅ MP4 compatible : {os.path.basename(final)} ({codec_label(after)}) en {el:.0f} s"
        + (f" — {fmt_speed(dur / el)}" if dur and el > 0 else "")
        + ("" if enc == "copy" else f" · {ENCODER_LABELS.get(enc, enc)}"))
    return {"ok": True, "path": final, "vcodec": after.get("vcodec"), "acodec": after.get("acodec"),
            "before": c, "mode": mode, "encoder": enc, "seconds": el}


def _refresh_index_entry(root: str, folder: str) -> None:
    fp = os.path.join(root, folder)
    info = load_info(fp)
    entries = load_archive_index(root)
    for e in entries:
        if e.get("folder") == folder:
            fresh = entry_from_info(info, fp) if info else {}
            e["size"] = fresh.get("size", folder_size(fp))
            e["thumb"] = fresh.get("thumb", e.get("thumb", ""))
    save_archive_index(root, entries)


def fix_folder_codecs(folder_path: str, log: Callable[[str], None],
                      progress: Optional[Callable[[float], None]] = None,
                      cancel_event: Optional[threading.Event] = None,
                      update_index: bool = True,
                      stats: Optional[Callable[[Dict[str, Any]], None]] = None) -> str:
    """'ok' (converti), 'skip' (déjà compatible / pas de vidéo), 'cancel'. Lève en cas d'échec."""
    main = find_main_media(folder_path)
    if not main or not main.lower().endswith(VIDEO_EXTS):
        return "skip"
    c = probe_codecs(main)
    if is_compatible(main, c):
        return "skip"
    r = convert_to_compatible(main, log, progress=progress, cancel_event=cancel_event, stats=stats)
    if not r.get("ok"):
        return "cancel"
    info = load_info(folder_path)
    if info:
        info["vcodec"], info["acodec"] = r.get("vcodec"), r.get("acodec")
        info["converted_h264"] = datetime.now().isoformat(timespec="seconds")
        info["media_files"] = [n for n in os.listdir(folder_path) if n.lower().endswith(MEDIA_EXTS)]
        _write_json_atomic(os.path.join(folder_path, "info.json"), info)
        write_local_index(folder_path, info)
    if update_index:
        root, folder = os.path.split(os.path.abspath(folder_path))
        try:
            _refresh_index_entry(root, folder)
        except Exception:
            logger.exception("index après conversion")
    return "ok"


def scan_incompatible(root: str) -> List[Tuple[str, str]]:
    """[(folder, 'AV1 + OPUS'), …] des archives dont la vidéo n'est pas MP4 H.264/AAC."""
    out = []
    for e in sync_index_with_disk(root):
        fp = os.path.join(root, str(e.get("folder") or ""))
        main = find_main_media(fp)
        if main and main.lower().endswith(VIDEO_EXTS):
            c = probe_codecs(main)
            if not is_compatible(main, c):
                out.append((str(e.get("folder")), codec_label(c)))
    return out


def fix_codecs_all(root: str, log: Callable[[str], None],
                   cancel_event: Optional[threading.Event] = None) -> Dict[str, int]:
    stats = {"ok": 0, "skip": 0, "fail": 0}
    todo = scan_incompatible(root)
    log(f"Réparation codecs : {len(todo)} vidéo(s) à convertir.")
    for folder, lab in todo:
        if cancel_event is not None and cancel_event.is_set():
            break
        try:
            r = fix_folder_codecs(os.path.join(root, folder), log, cancel_event=cancel_event, update_index=False)
            stats["ok" if r == "ok" else "skip"] += 1
        except Exception as ex:
            logger.exception("fix codecs %s", folder)
            log(f"❌ {folder} : {friendly_error(ex)}")
            stats["fail"] += 1
    entries = sync_index_with_disk(root)
    for e in entries:
        fp = os.path.join(root, str(e.get("folder")))
        if os.path.isdir(fp):
            e["size"] = folder_size(fp)
    save_archive_index(root, entries)
    return stats


PLAYER_LABELS = {"windows": "Windows (défaut)", "vlc": "VLC", "mpv": "mpv"}


def detect_players() -> Dict[str, str]:
    """{'vlc': exe, 'mpv': exe} selon les chemins usuels."""
    found: Dict[str, str] = {}
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    pfx = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    la = os.environ.get("LOCALAPPDATA", "")
    home = os.path.expanduser("~")
    cands = {
        "vlc": [os.path.join(pf, "VideoLAN", "VLC", "vlc.exe"), os.path.join(pfx, "VideoLAN", "VLC", "vlc.exe"),
                os.path.join(la, "Programs", "VideoLAN", "VLC", "vlc.exe"), shutil.which("vlc") or ""],
        "mpv": [shutil.which("mpv") or "", os.path.join(la, "Programs", "mpv", "mpv.exe"),
                os.path.join(pf, "mpv", "mpv.exe"), os.path.join(home, "scoop", "shims", "mpv.exe"),
                os.path.join(la, "Microsoft", "WinGet", "Links", "mpv.exe"), r"C:\mpv\mpv.exe"],
    }
    for name, paths in cands.items():
        for p in paths:
            if p and os.path.isfile(p):
                found[name] = os.path.abspath(p)
                break
    return found


def open_media(path: str, player: str = "windows") -> Tuple[bool, str]:
    """Ouvre un média avec le lecteur choisi (VLC/mpv si installé), sinon le lecteur Windows."""
    if player in ("vlc", "mpv") and path.lower().endswith(VIDEO_EXTS + AUDIO_EXTS):
        exe = detect_players().get(player)
        if exe:
            try:
                kw: Dict[str, Any] = {"close_fds": True, "stdin": subprocess.DEVNULL,
                                      "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
                if sys.platform.startswith("win"):
                    kw["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0) | CREATE_NO_WINDOW
                subprocess.Popen([exe, os.path.abspath(path)], **kw)
                return True, ""
            except Exception as e:
                logger.exception("lecteur %s", player)
                return open_path_explorer(path) if os.path.exists(path) else (False, str(e))
    return open_path_explorer(path)


# ================================================================= v5 : utilitaires communs
def _python_console_exe() -> str:
    """python.exe (pas pythonw) pour pip / sous-process, sans console grâce à CREATE_NO_WINDOW."""
    py = sys.executable or "python"
    if py.lower().endswith("pythonw.exe"):
        cand = py[:-len("pythonw.exe")] + "python.exe"
        if os.path.isfile(cand):
            return cand
    return py


def fmt_ts(sec: Any) -> str:
    """Horodatage court : m:ss ou h:mm:ss."""
    try:
        s = max(0, int(float(sec)))
    except Exception:
        return "0:00"
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def parse_timecode(text: Any) -> Optional[float]:
    """« 1:23 », « 01:02:03.5 », « 83 », « 83,5 », « 1m23s » → secondes (None si invalide)."""
    s = str(text or "").strip().lower().replace(",", ".")
    if not s:
        return None
    m = re.fullmatch(r"(?:(\d+)h)?\s*(?:(\d+)m(?:in)?)?\s*(?:(\d+(?:\.\d+)?)s?)?", s)
    if m and any(m.groups()) and not re.fullmatch(r"\d+(?:\.\d+)?", s):
        h, mi, se = m.groups()
        return int(h or 0) * 3600 + int(mi or 0) * 60 + float(se or 0)
    parts = s.split(":")
    try:
        nums = [float(p) for p in parts]
    except ValueError:
        return None
    if len(nums) > 3 or any(n < 0 for n in nums):
        return None
    total = 0.0
    for n in nums:
        total = total * 60 + n
    return total


def _ff_label(sec: float) -> str:
    """Horodatage pour nom de fichier : 01m05s / 1h02m03s."""
    s = max(0, int(round(sec)))
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h{m:02d}m{s:02d}s" if h else f"{m:02d}m{s:02d}s"


def _unique_path(path: str) -> str:
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    n = 2
    while os.path.exists(f"{base}_{n}{ext}"):
        n += 1
    return f"{base}_{n}{ext}"


def find_ffplay() -> Optional[str]:
    ff = find_ffmpeg()
    if ff:
        cand = os.path.join(os.path.dirname(ff), "ffplay.exe" if sys.platform.startswith("win") else "ffplay")
        if os.path.isfile(cand):
            return cand
    w = shutil.which("ffplay")
    return os.path.abspath(w) if w else None


def find_browser() -> Optional[str]:
    """Edge / Chrome / Chromium (mode headless) pour capture et PDF pleine page."""
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    pfx = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    la = os.environ.get("LOCALAPPDATA", "")
    cands = [
        os.path.join(pfx, "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(pf, "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(pf, "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(pfx, "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(la, "Google", "Chrome", "Application", "chrome.exe") if la else "",
    ]
    for name in ("msedge", "google-chrome", "chromium", "chromium-browser", "chrome"):
        w = shutil.which(name)
        if w:
            cands.append(w)
    for c in cands:
        if c and os.path.isfile(c):
            return os.path.abspath(c)
    return None


def module_available(name: str) -> bool:
    try:
        import importlib.util
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def whisper_available() -> bool:
    return module_available("faster_whisper")


def ytdlp_version() -> str:
    try:
        import yt_dlp  # type: ignore
        return str(yt_dlp.version.__version__)
    except Exception:
        return ""


def update_ytdlp(log: Callable[[str], None]) -> Tuple[bool, str, str]:
    """pip install -U yt-dlp (sans console). Retourne (ok, ancienne, nouvelle version)."""
    old = ytdlp_version()
    py = _python_console_exe()
    log(f"Mise à jour de yt-dlp (actuelle : {old or 'absente'})…")
    try:
        r = subprocess.run([py, "-m", "pip", "install", "-U", "--disable-pip-version-check", "yt-dlp"],
                           **_hidden_kwargs(), timeout=600)
        out = (r.stdout or b"").decode("utf-8", errors="replace")
        err = (r.stderr or b"").decode("utf-8", errors="replace")
        if r.returncode != 0:
            log(f"pip yt-dlp échec : {(err or out).strip()[-400:]}")
            return False, old, old
        r2 = subprocess.run([py, "-c", "import yt_dlp;print(yt_dlp.version.__version__)"],
                            **_hidden_kwargs(), timeout=60)
        new = (r2.stdout or b"").decode("utf-8", errors="replace").strip() or old
        log(f"yt-dlp : {old or '—'} → {new}")
        return True, old, new
    except Exception as e:
        log(f"Mise à jour yt-dlp impossible : {e}")
        return False, old, old


# ---------------------------------------------------------------- instance unique (Windows)
_INSTANCE_MUTEX = None
_MUTEX_NAME = "Local\\ArchiveurPadawanUnique"


def acquire_single_instance(wait: float = 0.0) -> bool:
    """True si cette instance est la seule (mutex nommé). Non-Windows : toujours True."""
    global _INSTANCE_MUTEX
    if not sys.platform.startswith("win"):
        return True
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        k32.CreateMutexW.restype = ctypes.c_void_p
        deadline = time.time() + max(0.0, wait)
        while True:
            h = k32.CreateMutexW(None, False, _MUTEX_NAME)
            if h and k32.GetLastError() != 183:  # ERROR_ALREADY_EXISTS
                _INSTANCE_MUTEX = h
                return True
            if h:
                k32.CloseHandle(ctypes.c_void_p(h))
            if time.time() >= deadline:
                return False
            time.sleep(0.25)
    except Exception:
        logger.exception("mutex instance")
        return True


def release_single_instance() -> None:
    global _INSTANCE_MUTEX
    if _INSTANCE_MUTEX and sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(_INSTANCE_MUTEX))
        except Exception:
            pass
    _INSTANCE_MUTEX = None


def focus_existing_window() -> bool:
    """Ramène au premier plan la fenêtre « Archiveur » déjà ouverte."""
    if not sys.platform.startswith("win"):
        return False
    try:
        import ctypes
        u32 = ctypes.windll.user32
        h = u32.FindWindowW("TkTopLevel", APP_NAME)
        if not h:
            return False
        if u32.IsIconic(h):
            u32.ShowWindow(h, 9)  # SW_RESTORE
        u32.SetForegroundWindow(h)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- sauvegarde de l'index (rotation)
BACKUP_DIR = "_sauvegardes"


def backup_index(root: str, keep: int = 15, min_interval: float = 1800.0) -> Optional[str]:
    """Copie archive_index.json dans _sauvegardes/ (au plus toutes les 30 min, garde les 15 dernières)."""
    src = os.path.join(root, INDEX_JSON)
    if not os.path.isfile(src):
        return None
    d = os.path.join(root, BACKUP_DIR)
    try:
        os.makedirs(d, exist_ok=True)
        olds = sorted(n for n in os.listdir(d) if n.startswith("archive_index_") and n.endswith(".json"))
        if olds:
            last = os.path.join(d, olds[-1])
            if time.time() - os.path.getmtime(last) < min_interval:
                return None
        dst = os.path.join(d, f"archive_index_{datetime.now().strftime('%Y%m%d-%H%M%S')}.json")
        shutil.copy2(src, dst)
        olds.append(os.path.basename(dst))
        for n in olds[:-keep]:
            try:
                os.remove(os.path.join(d, n))
            except OSError:
                pass
        return dst
    except Exception:
        logger.exception("sauvegarde index")
        return None


def list_index_backups(root: str) -> List[str]:
    d = os.path.join(root, BACKUP_DIR)
    try:
        return [os.path.join(d, n) for n in sorted(os.listdir(d), reverse=True)
                if n.startswith("archive_index_") and n.endswith(".json")]
    except OSError:
        return []


# ---------------------------------------------------------------- champs info.json → index
def update_info_fields(root: str, folder: str, save_index: bool = True, **fields: Any) -> Dict[str, Any]:
    """Met à jour des champs d'info.json (favori, collections, statut en ligne…) + page locale + index."""
    fp = os.path.join(root, folder)
    if not os.path.isdir(fp):
        raise FileNotFoundError(f"Dossier introuvable: {fp}")
    info = load_info(fp)
    info.setdefault("folder", folder)
    info.update(fields)
    _write_json_atomic(os.path.join(fp, "info.json"), info)
    try:
        write_local_index(fp, info)
    except Exception:
        logger.exception("index local %s", folder)
    if save_index:
        entries = load_archive_index(root)
        _merge_entry(entries, entry_from_info(info, fp))
        save_archive_index(root, entries)
    return info


def _merge_entry(entries: List[Dict[str, Any]], fresh: Dict[str, Any]) -> None:
    for i, e in enumerate(entries):
        if e.get("folder") == fresh.get("folder"):
            entries[i] = fresh
            return
    entries.append(fresh)


def refresh_entries(root: str, folders: List[str]) -> List[Dict[str, Any]]:
    """Reconstruit les entrées d'index des dossiers donnés depuis leur info.json (une seule écriture)."""
    entries = load_archive_index(root)
    for f in folders:
        fp = os.path.join(root, f)
        info = load_info(fp)
        if info:
            _merge_entry(entries, entry_from_info(info, fp))
    save_archive_index(root, entries)
    return entries


# ---------------------------------------------------------------- favoris / collections
COLLECTIONS_FILE = "collections.json"


def load_collections(root: str, entries: Optional[List[Dict[str, Any]]] = None) -> List[str]:
    names: List[str] = []
    try:
        p = os.path.join(root, COLLECTIONS_FILE)
        if os.path.isfile(p):
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                names = [str(x) for x in data if str(x).strip()]
    except Exception:
        logger.exception("collections.json")
    for e in entries or []:
        for c in e.get("collections") or []:
            if c not in names:
                names.append(c)
    seen = set()
    out = []
    for n in names:
        k = n.lower()
        if k not in seen:
            seen.add(k)
            out.append(n)
    return sorted(out, key=str.lower)


def save_collections(root: str, names: List[str]) -> None:
    os.makedirs(root, exist_ok=True)
    clean = sorted({re.sub(r"\s+", " ", n).strip()[:40] for n in names if n and n.strip()}, key=str.lower)
    _write_json_atomic(os.path.join(root, COLLECTIONS_FILE), clean)


def set_collections(root: str, folders: List[str], add: Optional[str] = None,
                    remove: Optional[str] = None) -> int:
    n = 0
    for f in folders:
        fp = os.path.join(root, f)
        info = load_info(fp)
        if not info:
            continue
        cols = [c for c in (info.get("collections") or []) if isinstance(c, str)]
        if add and add.lower() not in {c.lower() for c in cols}:
            cols.append(add)
        if remove:
            cols = [c for c in cols if c.lower() != remove.lower()]
        update_info_fields(root, f, save_index=False, collections=cols)
        n += 1
    refresh_entries(root, folders)
    return n


def set_favorite(root: str, folders: List[str], value: bool) -> int:
    n = 0
    for f in folders:
        if os.path.isdir(os.path.join(root, f)):
            update_info_fields(root, f, save_index=False, favorite=bool(value))
            n += 1
    refresh_entries(root, folders)
    return n


def add_tags_many(root: str, folders: List[str], tags: Any) -> int:
    new = parse_tags(tags)
    n = 0
    for f in folders:
        fp = os.path.join(root, f)
        info = load_info(fp)
        if not info:
            continue
        info_tags = parse_tags((info.get("tags") or []) + new)
        update_info_fields(root, f, save_index=False, tags=info_tags)
        try:
            write_post_txt(os.path.join(fp, "post.txt"), load_info(fp))
        except Exception:
            pass
        n += 1
    refresh_entries(root, folders)
    return n


def delete_archives(root: str, folders: List[str]) -> int:
    n = 0
    for f in folders:
        fp = os.path.join(root, f)
        if f and f == os.path.basename(f) and not f.startswith(".") and os.path.isdir(fp):
            shutil.rmtree(fp)
            n += 1
    entries = [e for e in load_archive_index(root) if e.get("folder") not in set(folders)]
    save_archive_index(root, entries)
    return n


# ---------------------------------------------------------------- classement simple (suggestions)
import unicodedata as _ud

COLL_SUGGEST_OFF = "collection_suggest_off"  # info.json : suggestion refusée (« Non merci »)

# familles de mots-clés -> collection proposée (mots sans accents, minuscules ; « * » = début de mot)
COLL_FAMILIES: List[Tuple[str, List[str]]] = [
    ("Santé & Nutrition", ["sante", "nutrition", "health", "healthy", "medecine", "medicine", "medical",
                           "medecin", "docteur", "doctor", "vaccin*", "pharma*", "vitamin*", "baking soda",
                           "bicarbonate", "cancer", "diet*", "regime", "guerir", "remede*", "remedy",
                           "immunit*", "maladie*", "disease", "jeune", "fasting", "sucre", "sugar",
                           "cholesterol", "diabet*", "nutritionniste", "naturopath*", "supplement*"]),
    ("Musique", ["music", "musique", "song", "songs", "chanson*", "official video", "clip officiel",
                 "concert", "album", "lyrics", "paroles", "remix", "guitar*", "guitare", "piano", "dj",
                 "official audio", "live session", "cover", "band", "orchestre", "orchestra"]),
    ("Films & séries", ["trailer", "bande annonce", "bande-annonce", "movie", "movies", "movieclips", "film",
                        "films", "serie", "series", "episode*", "saison", "season", "netflix", "warner",
                        "justwatch", "imdb", "anime", "cinema", "teaser", "court metrage", "short film"]),
    ("Documentaires", ["documentary", "documentaire*", "history", "histoire", "historique", "mystery",
                       "mystere*", "ancient", "chronology", "chronologie", "enquete", "civilisation*",
                       "civilization*", "archeolog*", "nobody talks about", "hidden", "secret*",
                       "the truth", "la verite", "explained", "explique"]),
    ("Tech & science", ["tech", "technologie", "technology", "ai", "ia", "intelligence artificielle",
                        "musk", "tesla", "spacex", "starlink", "grok", "chatgpt", "computer", "ordinateur",
                        "python", "logiciel", "software", "science", "scientifique", "physique", "physics",
                        "gravity", "gravite", "nasa", "robot*", "nvidia", "gpu", "quantum", "quantique",
                        "space", "espace", "astronom*", "invention"]),
    ("Nature", ["nature", "animal", "animaux", "animals", "wildlife", "forest", "foret", "ocean", "oiseau*",
                "bird*", "plante*", "plant", "jardin*", "garden*", "cat", "cats", "chat", "chats", "dog",
                "dogs", "chien*", "lion", "bear", "ours", "geolog*", "volcan*", "montagne*", "riviere",
                "lac", "canadian shield", "bouclier canadien"]),
    ("Spiritualité", ["jesus", "dieu", "god", "bible", "spiritual*", "spirituel*", "spiritualite", "priere",
                      "prayer", "meditation", "foi", "faith", "conscience", "consciousness", "ame", "soul",
                      "angel*", "ange", "anges", "eglise", "church"]),
    ("Actualités & politique", ["news", "nouvelles", "actualite*", "politique", "politics", "political",
                                "election*", "gouvernement", "government", "president", "ministre",
                                "parlement", "parliament", "tribunal", "court", "proces", "charges",
                                "senat*", "senate", "loi", "law", "guerre", "war"]),
    ("Humour", ["funny", "drole", "humour", "humor", "lol", "blague*", "meme", "memes", "comedy",
                "comedie", "parodie", "parody", "prank"]),
    ("Cuisine", ["recette*", "recipe*", "cuisine", "cooking", "chef", "patisserie", "baking", "gateau",
                 "souper", "dinner", "bbq"]),
]


def _fold(text: Any) -> str:
    """minuscules sans accents, ponctuation -> espaces."""
    t = _ud.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode("ascii").lower()
    return " " + re.sub(r"[^a-z0-9]+", " ", t).strip() + " "


_FAM_RX: List[Tuple[str, List[Tuple[str, "re.Pattern[str]"]]]] = []


def _family_patterns():
    if not _FAM_RX:
        for name, words in COLL_FAMILIES:
            pats = []
            for w in words:
                stem = w.rstrip("*")
                body = re.escape(_fold(stem).strip()).replace(r"\ ", " ")
                rx = re.compile(r" " + body + (r"[a-z0-9]*" if w.endswith("*") else "") + r" ")
                pats.append((stem, rx))
            _FAM_RX.append((name, pats))
    return _FAM_RX


_SERIES_SPLIT = re.compile(r"\s+[-–—|:]\s+|\s*[|(\[]|\s+-\s*")
_STOP_SERIES = {"", "the", "le", "la", "les", "un", "une", "a", "video", "vidéo", "live", "new", "official"}


def _title_wo_author(e: Dict[str, Any]) -> str:
    """Titre sans le « Auteur - » ajouté devant les posts X/Facebook."""
    t = str(e.get("title") or "").strip()
    up = str(e.get("uploader") or "").strip()
    if up and t.lower().startswith(up.lower()):
        rest = t[len(up):].lstrip(" -–—:|")
        if rest:
            return rest
    return t


def series_key(e: Dict[str, Any]) -> Tuple[str, str]:
    """(clé, nom joli) de la « série » d'un titre : partie avant « - », « | », « ( », « : ».
    Ex. « The Animatrix - Trailer » -> ('animatrix', 'Animatrix'). ('', '') si rien d'utile."""
    t = _title_wo_author(e)
    head = _SERIES_SPLIT.split(t, maxsplit=1)[0].strip(" -–—|:.\"'«»")
    if not head or len(head) > 48:
        return "", ""
    words = head.split()
    if len(words) > 5:
        return "", ""
    pretty_words = list(words)
    while pretty_words and _fold(pretty_words[0]).strip() in ("the", "le", "la", "les", "l"):
        pretty_words = pretty_words[1:]
    pretty = " ".join(pretty_words).strip()
    if pretty.lower().startswith("l'"):
        pretty = pretty[2:]
    key = _fold(pretty).strip()
    if not key or key in _STOP_SERIES or len(key) < 3 or key.isdigit():
        return "", ""
    up = _fold(e.get("uploader")).strip()
    if up and key == up:  # « Auteur - texte » : l'auteur n'est pas une série
        return "", ""
    return key, pretty[:40]


def _match_existing(name: str, existing: List[str]) -> str:
    k = _fold(name).strip()
    for c in existing:
        if _fold(c).strip() == k:
            return c
    return name


def suggest_collection(e: Dict[str, Any], entries: List[Dict[str, Any]],
                       existing: Optional[List[str]] = None,
                       info: Optional[Dict[str, Any]] = None) -> Optional[Tuple[str, str]]:
    """Propose UNE collection pour une archive : (nom, raison) ou None si aucune idée sûre.
    Ordre : nom d'une collection existante dans le titre > même série que d'autres archives >
    famille de mots-clés (Santé & Nutrition, Musique, Films & séries…)."""
    existing = list(existing or [])
    info = info or {}
    title = _fold(e.get("title"))
    # 1) une collection existante citée dans le titre (ou tags)
    tagtxt = _fold(" ".join(e.get("tags") or []))
    for c in sorted(existing, key=len, reverse=True):
        k = _fold(c).strip()
        if len(k) >= 3 and (f" {k} " in title or f" {k} " in tagtxt):
            return c, "le titre mentionne cette collection"
    # 2) même série (titres qui commencent pareil)
    key, pretty = series_key(e)
    if key:
        same = [x for x in entries if x is not e and x.get("folder") != e.get("folder")
                and series_key(x)[0] == key]
        if same:
            # si les autres sont déjà rangés quelque part : même endroit
            votes: Dict[str, int] = {}
            for x in same:
                for c in x.get("collections") or []:
                    votes[c] = votes.get(c, 0) + 1
            if votes:
                best = max(votes.items(), key=lambda kv: kv[1])[0]
                return best, f"comme {len(same)} autre(s) archive(s) « {pretty} »"
            return _match_existing(pretty, existing), f"même série que {len(same)} autre(s) archive(s)"
    # 3) familles de mots-clés
    parts = [
        (title, 3),
        (_fold(e.get("uploader")), 2),
        (tagtxt, 2),
        (_fold(" ".join(str(t) for t in (info.get("source_tags") or [])[:20])), 1),
        (_fold(str(e.get("text_snippet") or info.get("description") or "")[:600]), 1),
    ]
    best_name, best_score, best_words = "", 0, []
    for name, pats in _family_patterns():
        score, words = 0, []
        for txt, w in parts:
            if not txt.strip():
                continue
            for stem, rx in pats:
                if rx.search(txt):
                    score += w
                    if stem not in words:
                        words.append(stem)
        if score > best_score:
            best_name, best_score, best_words = name, score, words
    if best_score >= 3:
        shown = ", ".join(best_words[:3])
        return _match_existing(best_name, existing), f"mots repérés : {shown}"
    return None


def plan_auto_collections(entries: List[Dict[str, Any]], existing: Optional[List[str]] = None,
                          root: str = "") -> List[Tuple[str, str, str]]:
    """Plan « Ranger tout » : [(dossier, collection, raison)] pour les archives NON classées seulement."""
    plan = []
    for e in entries:
        if e.get("collections") or not e.get("folder"):
            continue
        info = load_info(os.path.join(root, str(e.get("folder")))) if root else {}
        if info.get(COLL_SUGGEST_OFF):
            continue
        sug = suggest_collection(e, entries, existing, info)
        if sug:
            plan.append((str(e.get("folder")), sug[0], sug[1]))
    return plan


def move_to_collection(root: str, folders: List[str], target: Optional[str]) -> int:
    """Déplace : l'archive n'est plus que dans « target » (None = Non classée)."""
    n = 0
    for f in folders:
        fp = os.path.join(root, f)
        if not load_info(fp):
            continue
        update_info_fields(root, f, save_index=False, collections=[target] if target else [])
        n += 1
    refresh_entries(root, folders)
    return n


# ================================================================= v5 : transcription
TRANSCRIPT_JSON = "transcript.json"
TRANSCRIPT_TXT = "transcript.txt"
SUB_EXTS = (".vtt", ".srt")
_TS_RE = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})")


def _ts_to_sec(s: str) -> Optional[float]:
    m = _TS_RE.search(s or "")
    if not m:
        return None
    h, mi, se, ms = m.groups()
    return int(h or 0) * 3600 + int(mi) * 60 + int(se) + int(ms.ljust(3, "0")) / 1000.0


def parse_subtitles(path: str) -> List[Tuple[float, str]]:
    """Lit un .vtt/.srt → [(début_s, texte)] ; enlève les doublons des sous-titres auto YouTube."""
    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
            raw = f.read()
    except OSError:
        return []
    blocks = re.split(r"\r?\n\s*\r?\n", raw.replace("\r\n", "\n"))
    cues: List[Tuple[float, float, List[str]]] = []
    for b in blocks:
        lines = [ln for ln in b.split("\n")]
        idx = next((i for i, ln in enumerate(lines) if "-->" in ln), -1)
        if idx < 0:
            continue
        left, _, right = lines[idx].partition("-->")
        st, en = _ts_to_sec(left), _ts_to_sec(right)
        if st is None:
            continue
        texts = []
        for ln in lines[idx + 1:]:
            t = re.sub(r"<[^>]+>", "", ln)
            t = html.unescape(t).replace("\u200b", "").strip()
            if t:
                texts.append(t)
        if texts:
            cues.append((st, en if en is not None else st, texts))
    out: List[Tuple[float, str]] = []
    last_lines: List[str] = []
    for st, en, texts in cues:
        if en - st < 0.05 and len(cues) > 3:  # transitions YouTube de 10 ms
            continue
        new = [t for t in texts if t not in last_lines]
        last_lines = texts
        line = " ".join(new).strip()
        if not line or (out and out[-1][1] == line):
            continue
        out.append((round(st, 2), line))
    # fusionne les fragments (sous-titres auto découpés au milieu des phrases)
    merged: List[Tuple[float, str]] = []
    for st, line in out:
        if merged:
            pst, pl = merged[-1]
            if (st - pst < 6 and len(pl) + len(line) < 110
                    and (st - pst < 1.0 or not re.search(r"[.!?…»\"')\]]$", pl))):
                merged[-1] = (pst, pl + " " + line)
                continue
        merged.append((st, line))
    return merged


def _sub_lang(name: str) -> str:
    m = re.search(r"\.([a-zA-Z]{2,3}(?:[-_][A-Za-z0-9]+)*)\.(?:vtt|srt)$", name)
    return m.group(1) if m else ""


def pick_subtitle_file(folder: str) -> Optional[str]:
    """Meilleur fichier de sous-titres : FR, puis EN, puis autre."""
    try:
        names = [n for n in os.listdir(folder) if n.lower().endswith(SUB_EXTS)]
    except OSError:
        return None
    if not names:
        return None

    def rank(n: str) -> Tuple[int, int, str]:
        lang = _sub_lang(n).lower()
        if lang.startswith("fr"):
            r = 0
        elif lang.startswith("en"):
            r = 1
        else:
            r = 2
        return (r, 1 if "orig" in lang or "-" in lang else 0, n)
    names.sort(key=rank)
    return os.path.join(folder, names[0])


def save_transcript(folder: str, cues: List[Tuple[float, str]], lang: str, source: str) -> Dict[str, Any]:
    data = {"lang": lang, "source": source, "created": datetime.now().isoformat(timespec="seconds"),
            "cues": [[float(t), str(x)] for t, x in cues]}
    _write_json_atomic(os.path.join(folder, TRANSCRIPT_JSON), data)
    with open(os.path.join(folder, TRANSCRIPT_TXT), "w", encoding="utf-8") as f:
        f.write(f"Transcription ({source}, langue : {lang or '?'})\n\n")
        for t, x in cues:
            f.write(f"[{fmt_ts(t)}] {x}\n")
    return data


def load_transcript(folder: str) -> Dict[str, Any]:
    """{'lang','source','cues':[(t, texte)]} ; construit depuis les sous-titres si besoin."""
    p = os.path.join(folder, TRANSCRIPT_JSON)
    try:
        if os.path.isfile(p):
            with open(p, "r", encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict) and isinstance(d.get("cues"), list):
                d["cues"] = [(float(c[0]), str(c[1])) for c in d["cues"] if isinstance(c, (list, tuple)) and len(c) >= 2]
                return d
    except Exception:
        logger.exception("lecture transcript %s", p)
    return build_transcript(folder) or {}


def build_transcript(folder: str, force: bool = False) -> Optional[Dict[str, Any]]:
    """Transcription horodatée à partir des sous-titres yt-dlp (.vtt/.srt)."""
    if not force and os.path.isfile(os.path.join(folder, TRANSCRIPT_JSON)):
        return None
    sub = pick_subtitle_file(folder)
    if not sub:
        return None
    cues = parse_subtitles(sub)
    if not cues:
        return None
    try:
        d = save_transcript(folder, cues, _sub_lang(os.path.basename(sub)), "sous-titres")
        d["cues"] = [(float(t), x) for t, x in d["cues"]]
        return d
    except OSError:
        logger.exception("écriture transcript")
        return None


def transcript_text(folder: str, limit: int = 60000) -> str:
    d = load_transcript(folder) if os.path.isdir(folder) else {}
    txt = " ".join(x for _t, x in d.get("cues") or [])
    return txt[:limit]


def transcribe_whisper(folder: str, log: Callable[[str], None], model_size: str = "base",
                       progress: Optional[Callable[[float], None]] = None,
                       cancel_event: Optional[threading.Event] = None) -> Dict[str, Any]:
    """Transcription locale (faster-whisper, CPU int8). Le modèle est téléchargé au 1er usage."""
    from faster_whisper import WhisperModel  # type: ignore
    media = find_main_media(folder)
    if not media:
        raise RuntimeError("Aucun média audio/vidéo dans cette archive.")
    log(f"🎙 Chargement du modèle Whisper « {model_size} » (1er usage : téléchargement)…")
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, tinfo = model.transcribe(media, vad_filter=True, beam_size=1)
    dur = float(getattr(tinfo, "duration", 0) or 0) or (probe_duration(media) or 0)
    lang = str(getattr(tinfo, "language", "") or "")
    log(f"🎙 Langue détectée : {lang or '?'} — transcription…")
    cues: List[Tuple[float, str]] = []
    for seg in segments:
        if cancel_event is not None and cancel_event.is_set():
            raise ArchiveCancelled("Transcription annulée.")
        t = (seg.text or "").strip()
        if t:
            cues.append((round(float(seg.start), 2), t))
        if progress and dur:
            progress(min(99.0, float(seg.end) / dur * 100.0))
    if not cues:
        raise RuntimeError("Aucune parole détectée.")
    d = save_transcript(folder, cues, lang, f"whisper-{model_size}")
    with open(os.path.join(folder, f"transcript_whisper.{lang or 'xx'}.srt"), "w", encoding="utf-8") as f:
        for i, (t, x) in enumerate(cues, 1):
            nxt = cues[i][0] if i < len(cues) else t + 4

            def srt(v: float) -> str:
                ms = int(round(v * 1000))
                h, ms = divmod(ms, 3600000)
                m, ms = divmod(ms, 60000)
                s, ms = divmod(ms, 1000)
                return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
            f.write(f"{i}\n{srt(t)} --> {srt(max(t + 0.5, nxt))}\n{x}\n\n")
    info = load_info(folder)
    if info:
        info["transcript_lang"] = lang
        info["transcript_source"] = d["source"]
        _write_json_atomic(os.path.join(folder, "info.json"), info)
    return d


# ================================================================= v5 : outils média (ffmpeg)
EXTRACTS_DIR = "extraits"


def _run_ff(args: List[str], timeout: int = 600) -> Tuple[bool, str]:
    ff = find_ffmpeg()
    if not ff:
        return False, "ffmpeg introuvable"
    try:
        r = subprocess.run([ff, "-hide_banner", "-nostdin", "-loglevel", "error", "-y", *args],
                           **_hidden_kwargs(), timeout=timeout)
        err = (r.stderr or b"").decode("utf-8", errors="replace").strip()
        return r.returncode == 0, err
    except subprocess.TimeoutExpired:
        return False, "délai dépassé"
    except Exception as e:
        return False, str(e)


def _extract_dir(folder: str) -> str:
    d = os.path.join(folder, EXTRACTS_DIR)
    os.makedirs(d, exist_ok=True)
    return d


def _check_range(start: float, end: Optional[float], duration: Optional[float]) -> Tuple[float, float]:
    start = max(0.0, float(start or 0))
    if duration and start >= duration:
        raise ValueError(f"Le début ({fmt_ts(start)}) dépasse la durée ({fmt_ts(duration)}).")
    if end is None or end <= 0:
        end = duration or (start + 10)
    if duration:
        end = min(end, duration)
    if end <= start:
        raise ValueError("La fin doit être après le début.")
    return start, end


def media_capture(video: str, t: float, folder: str) -> str:
    dur = probe_duration(video)
    t = max(0.0, min(float(t or 0), max(0.0, (dur or t + 1) - 0.05)))
    out = _unique_path(os.path.join(_extract_dir(folder), f"capture_{_ff_label(t)}.jpg"))
    ok, err = _run_ff(["-ss", f"{t:.3f}", "-i", video, "-frames:v", "1", "-q:v", "2", out], 120)
    if not ok or not os.path.isfile(out):
        raise RuntimeError(f"Capture impossible : {err or 'ffmpeg'}")
    return out


def media_clip(video: str, start: float, end: Optional[float], folder: str, precise: bool = False) -> str:
    dur = probe_duration(video)
    start, end = _check_range(start, end, dur)
    is_audio = video.lower().endswith(AUDIO_EXTS)
    ext = os.path.splitext(video)[1].lower() if is_audio else ".mp4"
    name = f"extrait_{_ff_label(start)}_a_{_ff_label(end)}{ext}"
    out = _unique_path(os.path.join(_extract_dir(folder), name))
    length = end - start
    if is_audio:
        args = ["-ss", f"{start:.3f}", "-i", video, "-t", f"{length:.3f}", "-c", "copy", out]
    elif precise:
        args = ["-ss", f"{start:.3f}", "-i", video, "-t", f"{length:.3f}", "-map", "0:v:0", "-map", "0:a:0?",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out]
    else:
        args = ["-ss", f"{start:.3f}", "-i", video, "-t", f"{length:.3f}", "-map", "0:v:0", "-map", "0:a:0?",
                "-c", "copy", "-avoid_negative_ts", "make_zero", "-movflags", "+faststart", out]
    ok, err = _run_ff(args, 1800)
    if not ok or not os.path.isfile(out) or os.path.getsize(out) == 0:
        try:
            os.remove(out)
        except OSError:
            pass
        raise RuntimeError(f"Extrait impossible : {err or 'ffmpeg'}")
    return out


def media_audio(video: str, folder: str, start: Optional[float] = None, end: Optional[float] = None) -> str:
    dur = probe_duration(video)
    args: List[str] = []
    if start is not None or end is not None:
        s, e = _check_range(start or 0, end, dur)
        name = f"audio_{_ff_label(s)}_a_{_ff_label(e)}.mp3"
        args += ["-ss", f"{s:.3f}", "-i", video, "-t", f"{e - s:.3f}"]
    else:
        name = "audio_complet.mp3"
        args += ["-i", video]
    out = _unique_path(os.path.join(_extract_dir(folder), name))
    ok, err = _run_ff(args + ["-vn", "-c:a", "libmp3lame", "-q:a", "2", out], 1800)
    if not ok or not os.path.isfile(out) or os.path.getsize(out) == 0:
        try:
            os.remove(out)
        except OSError:
            pass
        raise RuntimeError(f"Extraction audio impossible : {err or 'ffmpeg (piste audio absente ?)'}")
    return out


GIF_MAX_SECONDS = 20


def media_gif(video: str, start: float, end: Optional[float], folder: str, width: int = 480, fps: int = 12) -> str:
    dur = probe_duration(video)
    start, end = _check_range(start, end if end else (start or 0) + 5, dur)
    if end - start > GIF_MAX_SECONDS:
        end = start + GIF_MAX_SECONDS
    out = _unique_path(os.path.join(_extract_dir(folder), f"gif_{_ff_label(start)}_a_{_ff_label(end)}.gif"))
    vf = (f"fps={int(fps)},scale='min({int(width)},iw)':-2:flags=lanczos,split[s0][s1];"
          f"[s0]palettegen=max_colors=128:stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle")
    ok, err = _run_ff(["-ss", f"{start:.3f}", "-t", f"{end - start:.3f}", "-i", video, "-vf", vf,
                       "-loop", "0", out], 900)
    if not ok or not os.path.isfile(out) or os.path.getsize(out) == 0:
        try:
            os.remove(out)
        except OSError:
            pass
        raise RuntimeError(f"GIF impossible : {err or 'ffmpeg'}")
    return out


def list_extracts(folder: str) -> List[str]:
    d = os.path.join(folder, EXTRACTS_DIR)
    try:
        return [os.path.join(d, n) for n in sorted(os.listdir(d)) if os.path.isfile(os.path.join(d, n))]
    except OSError:
        return []


# ================================================================= v5 : pages web complètes
WEB_ASSETS_DIR = "page_files"
WEB_MAX_IMAGES = 80
WEB_MAX_IMAGE_BYTES = 8 * 1024 * 1024
WEB_MAX_TOTAL_BYTES = 80 * 1024 * 1024
WEB_MAX_CSS = 15


def http_fetch(url: str, timeout: int = 30, max_bytes: int = 40 * 1024 * 1024) -> Tuple[bytes, str, str]:
    """GET robuste → (contenu, url finale, content-type). Repli curl_cffi (empreinte Chrome) si 403/429/503."""
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "fr-CA,fr;q=0.9,en;q=0.8",
               "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/*,*/*;q=0.8"}
    try:
        req = Request(url, headers=headers)
        with urlopen(req, timeout=timeout) as resp:
            data = resp.read(max_bytes + 1)
            if len(data) > max_bytes:
                raise RuntimeError("fichier trop volumineux")
            return data, resp.geturl(), str(resp.headers.get("Content-Type") or "")
    except Exception as e:
        code = getattr(e, "code", None)
        if code in (403, 429, 503) and module_available("curl_cffi"):
            from curl_cffi import requests as creq  # type: ignore
            r = creq.get(url, impersonate="chrome", timeout=timeout, headers={"Accept-Language": headers["Accept-Language"]})
            if r.status_code >= 400:
                raise RuntimeError(f"HTTP Error {r.status_code}") from e
            return r.content[:max_bytes], str(r.url), str(r.headers.get("content-type") or "")
        raise


def _decode_html(raw: bytes, ctype: str) -> str:
    m = re.search(r"charset=([\w-]+)", ctype or "", re.I)
    cands = [m.group(1)] if m else []
    m2 = re.search(rb"<meta[^>]+charset=[\"']?([\w-]+)", raw[:4096], re.I)
    if m2:
        cands.append(m2.group(1).decode("ascii", "ignore"))
    cands += ["utf-8", "cp1252"]
    for c in cands:
        try:
            return raw.decode(c)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", errors="replace")


def _soup(text: str):
    from bs4 import BeautifulSoup  # type: ignore
    for parser in ("lxml", "html.parser"):
        try:
            return BeautifulSoup(text, parser)
        except Exception:
            continue
    return BeautifulSoup(text, "html.parser")


def _meta(soup, *names: str) -> str:
    for n in names:
        tag = soup.find("meta", attrs={"property": n}) or soup.find("meta", attrs={"name": n})
        if tag and tag.get("content"):
            return html.unescape(str(tag.get("content"))).strip()
    return ""


def _best_src(img, base: str) -> str:
    from urllib.parse import urljoin
    cands = []
    for attr in ("srcset", "data-srcset"):
        ss = img.get(attr)
        if ss:
            for part in str(ss).split(","):
                bits = part.strip().split()
                if not bits:
                    continue
                w = 0
                if len(bits) > 1:
                    m = re.match(r"(\d+(?:\.\d+)?)([wx])", bits[1])
                    if m:
                        w = float(m.group(1)) * (1000 if m.group(2) == "x" else 1)
                cands.append((w, bits[0]))
    if cands:
        cands.sort(key=lambda x: x[0])
        # éviter les très grandes images (4K) : la plus grande ≤ 1600 px, sinon la plus petite
        ok = [c for c in cands if c[0] <= 1600] or cands[:1]
        src = ok[-1][1]
    else:
        src = img.get("data-src") or img.get("data-lazy-src") or img.get("data-original") or img.get("src") or ""
    src = str(src).strip()
    if not src or src.startswith("data:"):
        return ""
    return urljoin(base, src)


_READABLE_SELECTORS = ("article", "main", "[role=main]", "#mw-content-text", "#content", "#main",
                       ".post-content", ".entry-content", ".article-body", ".article-content", ".post", ".story")
_JUNK_TAGS = ("script", "style", "noscript", "iframe", "form", "nav", "footer", "aside", "svg", "button",
              "input", "select", "textarea", "template", "dialog")


def _readable_root(soup):
    best, best_len = None, 0
    for sel in _READABLE_SELECTORS:
        try:
            for node in soup.select(sel):
                ln = sum(len(p.get_text(" ", strip=True)) for p in node.find_all("p"))
                if ln > best_len:
                    best, best_len = node, ln
        except Exception:
            continue
    if best is None or best_len < 200:
        body = soup.body or soup
        cands = [body] + body.find_all(["div", "section"], limit=400)
        for node in cands:
            ln = sum(len(p.get_text(" ", strip=True)) for p in node.find_all("p", recursive=False))
            if ln > best_len:
                best, best_len = node, ln
    node = best or soup.body or soup

    def plen(n) -> int:
        return sum(len(p.get_text(" ", strip=True)) for p in n.find_all("p"))
    cur = plen(node)
    for _ in range(12):  # descendre vers le bloc le plus serré qui garde l'essentiel du texte
        kids = node.find_all(["div", "section", "article", "main"], recursive=False)
        if not kids or cur <= 0:
            break
        best_kid = max(kids, key=plen)
        if plen(best_kid) >= 0.85 * cur:
            node = best_kid
        else:
            break
    return node


def readable_text(node) -> str:
    """Texte lisible (titres, paragraphes, listes, citations) depuis un nœud bs4."""
    out: List[str] = []
    for el in node.find_all(["h1", "h2", "h3", "h4", "p", "li", "blockquote", "pre", "figcaption", "dd", "dt"]):
        if el.find_parent(["li", "blockquote"]) and el.name in ("p",):
            continue
        t = re.sub(r"\s+", " ", el.get_text()).strip()
        t = re.sub(r"\s+([,.;:!?)»])", r"\1", t) if el.name != "pre" else t
        if not t or len(t) < 2:
            continue
        if el.name in ("h1", "h2", "h3", "h4"):
            t = ("#" * int(el.name[1])) + " " + t
        elif el.name == "li":
            t = "• " + t
        elif el.name == "blockquote":
            t = "« " + t + " »"
        if out and out[-1] == t:
            continue
        out.append(t)
    return "\n\n".join(out)


def _download_assets(urls: List[str], dest_dir: str, log: Callable[[str], None],
                     cancel_event: Optional[threading.Event]) -> Dict[str, str]:
    """Télécharge les images (limites de taille/nombre) → {url: nom_local}."""
    os.makedirs(dest_dir, exist_ok=True)
    out: Dict[str, str] = {}
    total = 0
    for i, u in enumerate(urls[:WEB_MAX_IMAGES]):
        _check_cancel(cancel_event)
        if u in out:
            continue
        try:
            data, final, ctype = http_fetch(u, timeout=20, max_bytes=WEB_MAX_IMAGE_BYTES)
        except Exception:
            continue
        if not data or (ctype and not ctype.lower().startswith("image/")):
            continue
        ext = os.path.splitext(urlparse(final).path)[1].lower()
        if ext not in IMAGE_EXTS + (".svg", ".avif", ".bmp"):
            ext = {"image/png": ".png", "image/gif": ".gif", "image/webp": ".webp", "image/svg+xml": ".svg",
                   "image/avif": ".avif"}.get(ctype.split(";")[0].lower(), ".jpg")
        name = f"img_{i + 1:03d}{ext}"
        with open(os.path.join(dest_dir, name), "wb") as f:
            f.write(data)
        out[u] = name
        total += len(data)
        if total > WEB_MAX_TOTAL_BYTES:
            log("Limite de 80 Mo d'images atteinte — reste de la page non téléchargé.")
            break
    return out


def browser_capture(url: str, folder: str, log: Callable[[str], None], timeout: int = 75) -> Dict[str, str]:
    """Capture PNG (haut de page) + PDF pleine page via Edge/Chrome headless (sans fenêtre)."""
    exe = find_browser()
    if not exe:
        log("Capture : Edge/Chrome introuvable — page HTML autonome seulement.")
        return {}
    import tempfile
    res: Dict[str, str] = {}
    prof = tempfile.mkdtemp(prefix="archiveur_nav_")
    common = [exe, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--mute-audio", "--no-first-run",
              "--no-default-browser-check", "--disable-extensions", "--disable-notifications",
              f"--user-data-dir={prof}", "--virtual-time-budget=9000", "--lang=fr-CA"]
    if not sys.platform.startswith("win"):
        common.insert(2, "--no-sandbox")
    jobs = [("capture_page.png", ["--window-size=1280,2400", "--screenshot={out}"]),
            ("page_complete.pdf", ["--no-pdf-header-footer", "--print-to-pdf={out}"])]
    try:
        for name, extra in jobs:
            out = os.path.join(folder, name)
            args = common + [a.replace("{out}", out) for a in extra] + [url]
            try:
                kw = _hidden_kwargs()
                p = subprocess.Popen(args, **kw)
                try:
                    p.communicate(timeout=timeout)
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.communicate(timeout=10)
                    log(f"Capture {name} : délai dépassé.")
            except Exception as e:
                log(f"Capture {name} impossible : {e}")
            if os.path.isfile(out) and os.path.getsize(out) > 1000:
                res[name] = out
                log(f"📸 {name} ({human_size(os.path.getsize(out))})")
        if "capture_page.png" in res and HAS_PIL_BACKEND:
            try:
                from PIL import Image as _Im
                im = _Im.open(res["capture_page.png"])
                im.load()
                # rogner le bas uni (page plus courte que 2400 px)
                gray = im.convert("L")
                w, h = gray.size
                px = gray.load()
                bottom = h
                ref = px[w // 2, h - 1]
                while bottom > 400:
                    row = [px[x, bottom - 1] for x in range(0, w, 16)]
                    if max(abs(v - ref) for v in row) > 8:
                        break
                    bottom -= 8
                if bottom < h - 40:
                    im.crop((0, 0, w, min(h, bottom + 24))).save(res["capture_page.png"])
            except Exception:
                logger.exception("rognage capture")
    finally:
        for _ in range(5):
            shutil.rmtree(prof, ignore_errors=True)
            if not os.path.isdir(prof):
                break
            time.sleep(0.6)
    return res


try:
    import PIL  # noqa: F401
    HAS_PIL_BACKEND = True
except Exception:
    HAS_PIL_BACKEND = False

_LECTURE_CSS = """
body{font-family:Georgia,'Segoe UI',serif;background:#f6f3ea;color:#222;margin:0;padding:0}
.wrap{max-width:780px;margin:auto;padding:1.5rem 1.2rem 4rem;line-height:1.65;font-size:1.08rem}
.top{font-family:Consolas,monospace;font-size:.85rem;background:#0000aa;color:#55ffff;padding:.6rem 1rem}
.top a{color:#ffff55} h1{line-height:1.25} img{max-width:100%;height:auto} figure{margin:1rem 0}
figcaption{font-size:.85rem;color:#555} pre{white-space:pre-wrap;background:#eee;padding:.6rem}
table{border-collapse:collapse;max-width:100%;display:block;overflow:auto} td,th{border:1px solid #ccc;padding:.2rem .4rem}
blockquote{border-left:4px solid #bbb;margin-left:0;padding-left:1rem;color:#444} a{color:#0b5cad}
"""


def archive_webpage(url: str, root: str, log: Callable[[str], None],
                    cancel_event: Optional[threading.Event] = None, capture: bool = True) -> Dict[str, Any]:
    """Page web complète : HTML autonome (images locales, CSS intégrée, sans scripts), version lecture,
    texte lisible (article.txt), liens, + capture PNG / PDF pleine page (Edge/Chrome headless si présent)."""
    from urllib.parse import urljoin
    if not module_available("bs4"):
        raise RuntimeError("Module beautifulsoup4 absent — archivage page complète indisponible.")
    _check_cancel(cancel_event)
    log(f"🌐 Archivage page web complète : {url}")
    raw, final_url, ctype = http_fetch(url)
    platform = detect_platform(final_url or url)
    stamp = datetime.now().strftime("%Y-%m-%d")
    host = (urlparse(final_url or url).hostname or "site").lower()
    if host.startswith("www."):
        host = host[4:]
    low_ct = ctype.lower()
    if low_ct and "html" not in low_ct and "xml" not in low_ct:
        # document direct (PDF, image…) : on garde le fichier tel quel
        name = os.path.basename(urlparse(final_url).path) or "document"
        title = pick_archive_title({"title": os.path.splitext(name)[0]})
        final_dir = _new_archive_dir(root, f"{stamp}_{platform}_{slugify(title)}_{slugify(host.replace('.', '-'), 24)}")
        with open(os.path.join(final_dir, slugify(os.path.splitext(name)[0], 60) + (os.path.splitext(name)[1] or ".bin")), "wb") as f:
            f.write(raw)
        info_out = {"title": title, "id": host, "uploader": host, "upload_date": "", "description": "",
                    "webpage_url": final_url or url, "url": url, "platform": platform, "tags": [], "notes": "",
                    "archived_at": datetime.now().isoformat(timespec="seconds"), "folder": os.path.basename(final_dir),
                    "media_files": [], "method": "web-document", "content_type": ctype}
        _write_json_atomic(os.path.join(final_dir, "info.json"), info_out)
        write_post_txt(os.path.join(final_dir, "post.txt"), info_out)
        write_local_index(final_dir, info_out)
        return info_out
    text = _decode_html(raw, ctype)
    soup = _soup(text)
    base = final_url or url
    btag = soup.find("base", href=True)
    if btag:
        base = urljoin(base, str(btag.get("href")))
    raw_title = (_meta(soup, "og:title", "twitter:title") or
                 (soup.title.get_text(" ", strip=True) if soup.title else "") or host)
    desc_meta = _meta(soup, "og:description", "description", "twitter:description")
    author = _meta(soup, "author", "article:author", "twitter:creator", "parsely-author")
    site = _meta(soup, "og:site_name", "application-name") or host
    published = _meta(soup, "article:published_time", "datePublished", "date", "dc.date", "pubdate")
    if not published:
        art = soup.find("article")
        t = art.find("time", attrs={"datetime": True}) if art else None
        if t and re.match(r"\d{4}-\d{2}-\d{2}", str(t.get("datetime"))):
            published = str(t.get("datetime"))
    og_image = _meta(soup, "og:image", "twitter:image")

    node = _readable_root(soup)
    article = readable_text(node)
    title = pick_archive_title({"title": raw_title, "description": article or desc_meta})
    final_dir = _new_archive_dir(root, f"{stamp}_{platform}_{slugify(title)}_{slugify(host.replace('.', '-'), 24)}")
    try:
        with open(os.path.join(final_dir, "page_original.html"), "wb") as f:
            f.write(raw)
        # liens de l'article
        links: List[List[str]] = []
        seen_links = set()
        for a in node.find_all("a", href=True):
            href = urljoin(base, str(a.get("href")))
            if not href.startswith(("http://", "https://")) or href in seen_links:
                continue
            seen_links.add(href)
            links.append([re.sub(r"\s+", " ", a.get_text(" ", strip=True))[:120], href])
            if len(links) >= 400:
                break
        # images : celles de l'article d'abord, puis le reste de la page
        img_urls: List[str] = []
        if og_image:
            img_urls.append(urljoin(base, og_image))
        for scope in (node, soup):
            for img in scope.find_all("img"):
                u = _best_src(img, base)
                if u and u not in img_urls:
                    img_urls.append(u)
        _check_cancel(cancel_event)
        log(f"Images détectées : {len(img_urls)} (max {WEB_MAX_IMAGES})")
        assets = _download_assets(img_urls, os.path.join(final_dir, WEB_ASSETS_DIR), log, cancel_event)
        if og_image and urljoin(base, og_image) in assets:
            src = os.path.join(final_dir, WEB_ASSETS_DIR, assets[urljoin(base, og_image)])
            ext = os.path.splitext(src)[1]
            if ext in IMAGE_EXTS:
                shutil.copy2(src, os.path.join(final_dir, "image" + ext))

        def rewrite(scope, prefix: str, junk: Tuple[str, ...] = ("script",)) -> None:
            for tag in scope.find_all(list(junk)):
                tag.decompose()
            for mt in scope.find_all("meta", attrs={"http-equiv": True}):
                mt.decompose()
            for tag in scope.find_all(True):
                for attr in list(tag.attrs):
                    if attr.lower().startswith("on"):
                        del tag[attr]
            for img in scope.find_all("img"):
                u = _best_src(img, base)
                if u in assets:
                    img["src"] = prefix + assets[u]
                elif u:
                    img["src"] = u
                for attr in ("srcset", "data-srcset", "data-src", "loading", "sizes", "data-lazy-src"):
                    if attr in img.attrs:
                        del img[attr]
            for src in scope.find_all("source"):
                src.decompose()
            for a in scope.find_all("a", href=True):
                href = str(a.get("href"))
                if not href.startswith("#"):
                    a["href"] = urljoin(base, href)
                    a["target"] = "_blank"
                    a["rel"] = "noopener"

        # --- page complète autonome (CSS intégrée, scripts retirés)
        full = _soup(text)
        css_parts: List[str] = []
        for i, link in enumerate(full.find_all("link", href=True)):
            rel = " ".join(link.get("rel") or []).lower()
            if "stylesheet" not in rel:
                if "preload" in rel or "modulepreload" in rel:
                    link.decompose()
                continue
            if i >= 60 or len(css_parts) >= WEB_MAX_CSS:
                link.decompose()
                continue
            href = urljoin(base, str(link.get("href")))
            try:
                css_raw, css_final, _ct = http_fetch(href, timeout=20, max_bytes=3 * 1024 * 1024)
                css = css_raw.decode("utf-8", errors="replace")
                css = re.sub(r"url\(\s*(['\"]?)(?!data:)([^)'\"]+)\1\s*\)",
                             lambda m: f"url('{urljoin(css_final, m.group(2).strip())}')", css)
                css_parts.append(f"/* {href} */\n{css}")
            except Exception:
                pass
            link.decompose()
        for b in full.find_all("base"):
            b.decompose()
        for ns in full.find_all("noscript"):
            ns.unwrap()
        rewrite(full, WEB_ASSETS_DIR + "/")
        head = full.head or full
        if css_parts:
            st = full.new_tag("style")
            st.string = "\n".join(css_parts)
            head.append(st)
        banner = _soup(
            f'<div style="font:13px Consolas,monospace;background:#0000aa;color:#55ffff;padding:6px 10px;'
            f'position:relative;z-index:99999">📦 Archivé par Archiveur le {html.escape(datetime.now().strftime("%Y-%m-%d %H:%M"))} — '
            f'<a style="color:#ffff55" href="{html.escape(final_url or url, quote=True)}" target="_blank">'
            f'{html.escape(final_url or url)}</a> · <a style="color:#ffff55" href="lecture.html">version lecture</a></div>'
        )
        if full.body and banner.div:
            full.body.insert(0, banner.div)
        with open(os.path.join(final_dir, "page.html"), "w", encoding="utf-8") as f:
            f.write(str(full))

        # --- version lecture (article seul, propre)
        node_copy = _soup(str(node))
        rewrite(node_copy, WEB_ASSETS_DIR + "/", _JUNK_TAGS)
        inner = node_copy.body.decode_contents() if node_copy.body else str(node_copy)
        e = html.escape
        lecture = (f'<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">'
                   f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(title)}</title>'
                   f'<style>{_LECTURE_CSS}</style></head><body>'
                   f'<div class="top">📦 Archiveur — {e(site)} · archivé le {e(datetime.now().strftime("%Y-%m-%d %H:%M"))} · '
                   f'<a href="{e(final_url or url, quote=True)}" target="_blank">original</a> · '
                   f'<a href="page.html">page complète</a> · <a href="index.html">fiche</a></div>'
                   f'<div class="wrap"><h1>{e(raw_title)}</h1>'
                   f'<p><em>{e(author or site)}{" · " + e(published[:10]) if published else ""}</em></p>{inner}</div></body></html>')
        with open(os.path.join(final_dir, "lecture.html"), "w", encoding="utf-8") as f:
            f.write(lecture)
        with open(os.path.join(final_dir, "article.txt"), "w", encoding="utf-8") as f:
            f.write(f"{raw_title}\n{final_url or url}\n\n{article}\n")

        shots: Dict[str, str] = {}
        if capture:
            _check_cancel(cancel_event)
            shots = browser_capture(final_url or url, final_dir, log)
    except ArchiveCancelled:
        shutil.rmtree(final_dir, ignore_errors=True)
        raise
    except Exception:
        shutil.rmtree(final_dir, ignore_errors=True)
        raise
    upload = ""
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", published or "")
    if m:
        upload = "".join(m.groups())
    info_out = {
        "title": title,
        "id": host,
        "uploader": author or site,
        "uploader_url": f"https://{host}/",
        "site_name": site,
        "upload_date": upload,
        "description": article[:300000] or desc_meta,
        "summary": desc_meta,
        "webpage_url": final_url or url,
        "url": url,
        "platform": platform,
        "tags": [],
        "notes": "",
        "archived_at": datetime.now().isoformat(timespec="seconds"),
        "folder": os.path.basename(final_dir),
        "media_files": [n for n in os.listdir(final_dir) if n.lower().endswith(MEDIA_EXTS)],
        "method": "web-page",
        "links": links,
        "page_images": len(assets),
        "page_capture": "capture_page.png" if "capture_page.png" in shots else "",
        "page_pdf": "page_complete.pdf" if "page_complete.pdf" in shots else "",
        "words": len(article.split()),
    }
    _write_json_atomic(os.path.join(final_dir, "info.json"), info_out)
    write_post_txt(os.path.join(final_dir, "post.txt"), info_out)
    write_local_index(final_dir, info_out)
    log(f"✅ Page archivée : {len(article.split())} mots, {len(assets)} image(s), "
        f"{'capture + PDF' if shots else 'sans capture'}")
    return info_out


def _new_archive_dir(root: str, folder_name: str) -> str:
    final_dir = os.path.join(root, folder_name)
    n = 2
    while os.path.exists(final_dir):
        final_dir = os.path.join(root, f"{folder_name}_{n}")
        n += 1
    os.makedirs(final_dir, exist_ok=True)
    return final_dir


# ================================================================= v5 : X / Twitter (texte, médias, fil parent)
def _x_status_id(url: str) -> str:
    k = normalize_url(url)
    return k[2:] if k.startswith("x:") else ""


def fetch_fxtwitter(url_or_id: str, user: str = "i", timeout: int = 20) -> Optional[Dict[str, Any]]:
    """API publique fxtwitter (sans connexion) → dict « tweet » ou None."""
    sid = url_or_id if re.fullmatch(r"\d+", url_or_id or "") else _x_status_id(url_or_id)
    if not sid:
        return None
    if user == "i":
        m = re.search(r"(?:x|twitter)\.com/([A-Za-z0-9_]{1,15})/status", url_or_id or "")
        if m:
            user = m.group(1)
    try:
        data, _f, _c = http_fetch(f"https://api.fxtwitter.com/{user}/status/{sid}", timeout=timeout, max_bytes=4_000_000)
        d = json.loads(data.decode("utf-8", errors="replace"))
        tw = d.get("tweet") if isinstance(d, dict) else None
        return tw if isinstance(tw, dict) else None
    except Exception as e:
        logger.info("fxtwitter %s : %s", sid, e)
        return None


def _fx_line(tw: Dict[str, Any]) -> str:
    a = tw.get("author") or {}
    when = ""
    try:
        when = datetime.fromtimestamp(int(tw.get("created_timestamp"))).strftime("%Y-%m-%d %H:%M")
    except Exception:
        when = str(tw.get("created_at") or "")
    head = f"{a.get('name') or ''} (@{a.get('screen_name') or '?'}) — {when}"
    txt = str(tw.get("text") or "")
    q = tw.get("quote")
    if isinstance(q, dict):
        qa = q.get("author") or {}
        txt += f"\n\n↪ Citation de @{qa.get('screen_name') or '?'} : {q.get('text') or ''}\n{q.get('url') or ''}"
    stats = []
    for k, lab in (("replies", "réponses"), ("retweets", "reposts"), ("likes", "j'aime"), ("views", "vues")):
        if tw.get(k) is not None:
            stats.append(f"{tw.get(k)} {lab}")
    return f"{head}\n{txt}\n{tw.get('url') or ''}" + (f"\n[{', '.join(stats)}]" if stats else "")


def fetch_x_thread(url: str, max_parents: int = 8) -> List[Dict[str, Any]]:
    """Post + messages parents (remontée du fil). Les réponses sous le post exigent une connexion."""
    tw = fetch_fxtwitter(url)
    if not tw:
        return []
    chain = [tw]
    cur = tw
    for _ in range(max_parents):
        pid = cur.get("replying_to_status")
        if not pid:
            break
        parent = fetch_fxtwitter(str(pid), str(cur.get("replying_to") or "i"))
        if not parent:
            break
        chain.insert(0, parent)
        cur = parent
    return chain


def x_thread_text(chain: List[Dict[str, Any]], main_id: str = "") -> str:
    parts = []
    for i, tw in enumerate(chain, 1):
        mark = "▶ " if str(tw.get("id")) == main_id else ""
        parts.append(f"{mark}[{i}/{len(chain)}] {_fx_line(tw)}")
    return "\n\n────────\n\n".join(parts)


def archive_x_fx(url: str, root: str, log: Callable[[str], None],
                 cancel_event: Optional[threading.Event] = None) -> Dict[str, Any]:
    """Post X sans vidéo (ou yt-dlp en échec) : texte complet, photos, vidéo directe, fil parent, liens."""
    chain = fetch_x_thread(url)
    if not chain:
        raise RuntimeError("fxtwitter : post introuvable (supprimé, privé ou service indisponible).")
    main = chain[-1]
    sid = str(main.get("id") or _x_status_id(url))
    a = main.get("author") or {}
    text_main = str(main.get("text") or "")
    title = pick_archive_title({"title": "status", "description": text_main,
                                "uploader": a.get("name") or a.get("screen_name"), "id": sid})
    stamp = datetime.now().strftime("%Y-%m-%d")
    final_dir = _new_archive_dir(root, f"{stamp}_x_{slugify(title)}_{slugify(sid, 20)}")
    media_files: List[str] = []
    try:
        n = 0
        for ti, tw in enumerate(chain):
            med = tw.get("media") or {}
            for ph in (med.get("photos") or [])[:8]:
                _check_cancel(cancel_event)
                u = str(ph.get("url") or "")
                if not u:
                    continue
                try:
                    data, final, _ct = http_fetch(u + ("?name=orig" if "pbs.twimg.com" in u and "?" not in u else ""),
                                                  timeout=30, max_bytes=20 * 1024 * 1024)
                    n += 1
                    ext = os.path.splitext(urlparse(final).path)[1] or ".jpg"
                    fname = f"photo_{n:02d}{'' if tw is main else '_fil'}{ext}"
                    with open(os.path.join(final_dir, fname), "wb") as f:
                        f.write(data)
                    media_files.append(fname)
                except ArchiveCancelled:
                    raise
                except Exception as e:
                    log(f"Photo non téléchargée : {e}")
            if tw is main:
                for vi, vd in enumerate((med.get("videos") or [])[:4]):
                    _check_cancel(cancel_event)
                    u = str(vd.get("url") or "")
                    if not u:
                        continue
                    try:
                        data, _f, _ct = http_fetch(u, timeout=120, max_bytes=500 * 1024 * 1024)
                        fname = f"video_{vi + 1:02d}.mp4"
                        with open(os.path.join(final_dir, fname), "wb") as f:
                            f.write(data)
                        media_files.append(fname)
                        log(f"Vidéo sauvée : {fname} ({human_size(len(data))})")
                    except Exception as e:
                        log(f"Vidéo non téléchargée : {e}")
                    th = str(vd.get("thumbnail_url") or "")
                    if th and not os.path.exists(os.path.join(final_dir, "thumbnail.jpg")):
                        try:
                            data, _f, _ct = http_fetch(th, timeout=30, max_bytes=10 * 1024 * 1024)
                            with open(os.path.join(final_dir, "thumbnail.jpg"), "wb") as f:
                                f.write(data)
                        except Exception:
                            pass
        av = str(a.get("avatar_url") or "")
        if av:
            try:
                data, _f, _ct = http_fetch(av, timeout=20, max_bytes=2 * 1024 * 1024)
                os.makedirs(os.path.join(final_dir, "auteur"), exist_ok=True)
                with open(os.path.join(final_dir, "auteur", "avatar.jpg"), "wb") as f:
                    f.write(data)
            except Exception:
                pass
    except ArchiveCancelled:
        shutil.rmtree(final_dir, ignore_errors=True)
        raise
    desc = x_thread_text(chain, sid) if len(chain) > 1 else _fx_line(main)
    up = ""
    try:
        up = datetime.fromtimestamp(int(main.get("created_timestamp"))).strftime("%Y%m%d")
    except Exception:
        pass
    links = [[u, u] for u in extract_urls(desc)]
    info_out = {
        "title": title, "id": sid,
        "uploader": f"{a.get('name') or ''} (@{a.get('screen_name') or ''})".strip(),
        "uploader_url": f"https://x.com/{a.get('screen_name')}" if a.get("screen_name") else "",
        "upload_date": up, "description": desc, "text": text_main,
        "webpage_url": str(main.get("url") or url), "url": url, "platform": "x",
        "like_count": main.get("likes"), "repost_count": main.get("retweets"), "view_count": main.get("views"),
        "tags": [], "notes": "", "archived_at": datetime.now().isoformat(timespec="seconds"),
        "folder": os.path.basename(final_dir),
        "media_files": [m for m in os.listdir(final_dir) if m.lower().endswith(MEDIA_EXTS)],
        "method": "x-fxtwitter", "thread_count": len(chain), "links": links,
        "note": "Texte + médias via fxtwitter (public). Fil : messages parents seulement ; "
                "les réponses sous le post exigent une connexion à X.",
    }
    if any(m.lower().endswith(VIDEO_EXTS) for m in info_out["media_files"]):
        try:
            generate_storyboard(final_dir, SB_FRAMES)
        except Exception:
            logger.exception("storyboard x")
    _write_json_atomic(os.path.join(final_dir, "info.json"), info_out)
    write_post_txt(os.path.join(final_dir, "post.txt"), info_out)
    write_local_index(final_dir, info_out)
    log(f"✖ Post X archivé (fxtwitter) : {len(chain)} message(s) du fil, {len(media_files)} média(s).")
    return info_out


def enrich_x_thread(folder: str, url: str, log: Callable[[str], None]) -> None:
    """Après yt-dlp sur X : ajoute le fil parent et les liens (non bloquant)."""
    try:
        chain = fetch_x_thread(url)
        if len(chain) < 2:
            return
        info = load_info(folder)
        if not info:
            return
        info["thread_text"] = x_thread_text(chain, _x_status_id(url))
        info["thread_count"] = len(chain)
        info["description"] = (info.get("description") or "") + "\n\n──── Fil (messages parents) ────\n\n" + info["thread_text"]
        _write_json_atomic(os.path.join(folder, "info.json"), info)
        write_post_txt(os.path.join(folder, "post.txt"), info)
        write_local_index(folder, info)
        log(f"Fil X : {len(chain)} message(s) ajoutés au texte.")
    except Exception:
        logger.exception("enrich x")


# ================================================================= v5 : lien original encore en ligne ?
ONLINE_LABELS = {"online": "🟢 en ligne", "offline": "🔴 supprimé / introuvable",
                 "restricted": "🟠 privé / restreint", "unknown": "⚪ non vérifiable"}
ONLINE_ICONS = {"online": "🟢", "offline": "🔴", "restricted": "🟠", "unknown": "⚪"}


def _http_status(url: str, timeout: int = 15) -> Tuple[int, str]:
    try:
        req = Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "fr,en;q=0.8"})
        with urlopen(req, timeout=timeout) as r:
            r.read(2048)
            return int(r.status), r.geturl()
    except Exception as e:
        code = getattr(e, "code", None)
        if code:
            return int(code), url
        return 0, str(e)


def check_online(url: str, timeout: int = 15) -> Tuple[str, str]:
    """('online'|'offline'|'restricted'|'unknown', détail) — oEmbed officiels quand possible."""
    url = (url or "").strip()
    if not url:
        return "unknown", "pas d'URL"
    key = normalize_url(url)
    oembed = None
    if key.startswith("youtube:"):
        vid = key.split(":", 1)[1]
        oembed = "https://www.youtube.com/oembed?format=json&url=" + quote(f"https://www.youtube.com/watch?v={vid}", safe="")
    elif key.startswith("x:"):
        oembed = "https://publish.twitter.com/oembed?omit_script=1&url=" + quote(f"https://twitter.com/i/status/{key[2:]}", safe="")
    elif "vimeo.com" in key:
        oembed = "https://vimeo.com/api/oembed.json?url=" + quote(url, safe="")
    elif key.startswith("tiktok:"):
        oembed = "https://www.tiktok.com/oembed?url=" + quote(url, safe="")
    if oembed:
        code, _ = _http_status(oembed, timeout)
        if code == 200:
            return "online", "oEmbed 200"
        if code in (404, 400, 410):
            return "offline", f"oEmbed {code}"
        if code in (401, 403):
            return "restricted", f"oEmbed {code} (privé, restreint ou intégration interdite)"
        if code == 0:
            return "unknown", "réseau"
    plat = detect_platform(url)
    code, final = _http_status(url, timeout)
    if plat in ("facebook", "instagram") and code in (200, 302, 400, 403):
        return "unknown", f"HTTP {code} — vérification impossible sans connexion"
    if 200 <= code < 400:
        return "online", f"HTTP {code}"
    if code in (404, 410, 451):
        return "offline", f"HTTP {code}"
    if code in (401, 403):
        return "restricted", f"HTTP {code}"
    return "unknown", f"HTTP {code}" if code else "réseau"


def check_online_many(root: str, folders: List[str], progress: Optional[Callable[[int, int, str, str], None]] = None,
                      cancel_event: Optional[threading.Event] = None, workers: int = 4) -> Dict[str, int]:
    from concurrent.futures import ThreadPoolExecutor
    entries = {e.get("folder"): e for e in load_archive_index(root)}
    todo = [f for f in folders if f in entries]
    counts = {"online": 0, "offline": 0, "restricted": 0, "unknown": 0}
    results: Dict[str, Tuple[str, str]] = {}

    def one(f):
        if cancel_event is not None and cancel_event.is_set():
            return f, ("", "")
        e = entries[f]
        return f, check_online(str(e.get("url") or e.get("source_url") or ""))
    done = 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        for f, (st, det) in ex.map(one, todo):
            done += 1
            if not st:
                continue
            results[f] = (st, det)
            counts[st] = counts.get(st, 0) + 1
            if progress:
                progress(done, len(todo), f, st)
    now = datetime.now().isoformat(timespec="seconds")
    for f, (st, det) in results.items():
        try:
            update_info_fields(root, f, save_index=False, online_status=st, online_detail=det, online_checked=now)
        except Exception:
            logger.exception("online %s", f)
    if results:
        refresh_entries(root, list(results))
    return counts


# ================================================================= v5 : vérification d'intégrité
VERIFY_KINDS = {
    "orphan_entry": ("Entrée orpheline (dossier absent)", "Retirer de l'index"),
    "unindexed": ("Dossier non indexé", "Réindexer"),
    "no_info": ("Dossier sans info.json", "Créer une fiche minimale et indexer"),
    "tmp_left": ("Dossier temporaire abandonné", "Supprimer"),
    "missing_files": ("Fichiers listés mais absents", "Mettre la fiche à jour"),
    "no_local_index": ("Page index.html manquante", "Régénérer la page"),
    "thumb_missing": ("Miniature introuvable", "Mettre l'index à jour"),
    "media_unreadable": ("Média illisible / corrompu", "Re-archiver depuis l'original"),
    "no_media": ("Aucun média alors qu'une vidéo était attendue", "Re-archiver depuis l'original"),
    "incompatible": ("Vidéo non lisible par le lecteur Windows", "Convertir en MP4 H.264"),
    "bad_json": ("info.json illisible", "Restaurer depuis l'index"),
}
AUTO_FIX_KINDS = {"orphan_entry", "unindexed", "no_info", "tmp_left", "missing_files", "no_local_index",
                  "thumb_missing", "bad_json"}


def probe_readable(path: str) -> Tuple[bool, str]:
    """Média lisible ? (ffprobe : erreurs de flux, durée nulle) ; images via Pillow."""
    low = path.lower()
    if low.endswith(IMAGE_EXTS):
        try:
            from PIL import Image as _Im
            with _Im.open(path) as im:
                im.verify()
            return True, ""
        except Exception as e:
            return False, f"image illisible ({e.__class__.__name__})"
    fp = find_ffprobe()
    if not fp:
        return True, "ffprobe absent"
    try:
        r = subprocess.run([fp, "-v", "error", "-show_entries", "format=duration:stream=codec_type",
                            "-of", "json", path], **_hidden_kwargs(), timeout=60)
        err = (r.stderr or b"").decode("utf-8", errors="replace").strip()
        data = json.loads((r.stdout or b"{}").decode("utf-8", errors="replace") or "{}")
        streams = data.get("streams") or []
        dur = float((data.get("format") or {}).get("duration") or 0)
        if r.returncode != 0 or not streams:
            return False, (err.splitlines()[0][:160] if err else "aucun flux lisible")
        if dur <= 0 and not low.endswith(".gif"):
            return False, "durée nulle"
        return True, ""
    except Exception as e:
        return False, str(e)[:160]


def verify_archives(root: str, check_media: bool = True,
                    progress: Optional[Callable[[int, int, str], None]] = None,
                    cancel_event: Optional[threading.Event] = None) -> Dict[str, Any]:
    """Rapport : [{folder, title, kind, detail, fix, auto}] + compteurs. Ne modifie rien."""
    issues: List[Dict[str, Any]] = []
    entries = load_archive_index(root)
    by_folder = {str(e.get("folder")): e for e in entries if e.get("folder")}

    def add(folder: str, kind: str, detail: str = "", title: str = ""):
        lab, fix = VERIFY_KINDS[kind]
        issues.append({"folder": folder, "title": title or str((by_folder.get(folder) or {}).get("title") or folder),
                       "kind": kind, "label": lab, "detail": detail, "fix": fix, "auto": kind in AUTO_FIX_KINDS})
    try:
        names = sorted(os.listdir(root)) if os.path.isdir(root) else []
    except OSError:
        names = []
    dirs = [n for n in names if os.path.isdir(os.path.join(root, n))]
    for f in by_folder:
        if f not in dirs:
            add(f, "orphan_entry")
    checked = 0
    total = len(dirs)
    for i, name in enumerate(dirs):
        if cancel_event is not None and cancel_event.is_set():
            break
        if progress:
            progress(i + 1, total, name)
        fp = os.path.join(root, name)
        if name.startswith("_tmp_"):
            add(name, "tmp_left", human_size(folder_size(fp)), name)
            continue
        if name.startswith("_") or name.startswith("."):
            continue
        info_p = os.path.join(fp, "info.json")
        if not os.path.isfile(info_p):
            add(name, "no_info", f"{len(list_folder_files(fp))} fichier(s)", name)
            continue
        try:
            with open(info_p, "r", encoding="utf-8") as fh:
                info = json.load(fh)
            if not isinstance(info, dict):
                raise ValueError("pas un objet")
        except Exception as e:
            add(name, "bad_json", str(e)[:120])
            continue
        checked += 1
        if name not in by_folder:
            add(name, "unindexed", "", str(info.get("title") or name))
        missing = [m for m in (info.get("media_files") or []) if isinstance(m, str)
                   and not os.path.exists(os.path.join(fp, m))]
        if missing:
            add(name, "missing_files", ", ".join(missing[:4]) + (" …" if len(missing) > 4 else ""))
        if not os.path.isfile(os.path.join(fp, "index.html")):
            add(name, "no_local_index")
        e = by_folder.get(name)
        if e and e.get("thumb") and not os.path.isfile(os.path.join(fp, str(e.get("thumb")))):
            add(name, "thumb_missing", str(e.get("thumb")))
        main = find_main_media(fp)
        if info.get("method") == "yt-dlp" and not main and not list_images(fp):
            add(name, "no_media")
        if check_media:
            for n in list_folder_files(fp):
                if n.lower().endswith(VIDEO_EXTS + AUDIO_EXTS):
                    ok, det = probe_readable(os.path.join(fp, n))
                    if not ok:
                        add(name, "media_unreadable", f"{n} : {det}")
            if main and main.lower().endswith(VIDEO_EXTS):
                try:
                    c = probe_codecs(main)
                    if c.get("vcodec") and not is_compatible(main, c):
                        add(name, "incompatible", codec_label(c))
                except Exception:
                    pass
    bad = {x["folder"] for x in issues}
    return {"issues": issues, "checked": checked, "folders": total, "entries": len(entries),
            "ok": max(0, checked - len(bad & set(dirs))), "date": datetime.now().isoformat(timespec="seconds")}


def repair_archives(root: str, issues: List[Dict[str, Any]], log: Callable[[str], None]) -> Dict[str, int]:
    """Applique les réparations automatiques sûres (pas de re-archivage ni conversion ici)."""
    st = {"ok": 0, "skip": 0, "fail": 0}
    entries = load_archive_index(root)
    by_folder = {str(e.get("folder")): e for e in entries}
    touched: List[str] = []
    drop: set = set()
    for it in issues:
        kind, f = it.get("kind"), str(it.get("folder") or "")
        fp = os.path.join(root, f)
        try:
            if kind == "orphan_entry":
                drop.add(f)
            elif kind == "tmp_left":
                if f.startswith("_tmp_") and os.path.isdir(fp):
                    shutil.rmtree(fp)
            elif kind == "no_info":
                files = list_folder_files(fp)
                m = re.match(r"^(\d{4}-\d{2}-\d{2})_([a-z0-9]+)_(.+)$", f)
                info = {"title": (m.group(3) if m else f).replace("-", " "), "platform": m.group(2) if m else "web",
                        "url": "", "webpage_url": "", "description": "",
                        "archived_at": (m.group(1) + "T00:00:00") if m else datetime.now().isoformat(timespec="seconds"),
                        "folder": f, "media_files": [n for n in files if n.lower().endswith(MEDIA_EXTS)],
                        "method": "réindexé", "tags": [], "notes": ""}
                _write_json_atomic(os.path.join(fp, "info.json"), info)
                write_local_index(fp, info)
                touched.append(f)
            elif kind == "bad_json":
                e = by_folder.get(f)
                if not e:
                    st["skip"] += 1
                    continue
                os.replace(os.path.join(fp, "info.json"), os.path.join(fp, "info.json.corrompu"))
                info = {"title": e.get("title"), "platform": e.get("platform"), "url": e.get("source_url") or e.get("url"),
                        "webpage_url": e.get("url"), "uploader": e.get("uploader"), "description": e.get("text_snippet") or "",
                        "archived_at": e.get("archived_at"), "folder": f, "tags": e.get("tags") or [],
                        "notes": e.get("notes") or "", "method": e.get("method") or "restauré",
                        "media_files": [n for n in list_folder_files(fp) if n.lower().endswith(MEDIA_EXTS)]}
                _write_json_atomic(os.path.join(fp, "info.json"), info)
                write_local_index(fp, info)
                touched.append(f)
            elif kind == "missing_files":
                info = load_info(fp)
                info["media_files"] = [n for n in list_folder_files(fp) if n.lower().endswith(MEDIA_EXTS)]
                _write_json_atomic(os.path.join(fp, "info.json"), info)
                write_local_index(fp, info)
                touched.append(f)
            elif kind == "no_local_index":
                write_local_index(fp, load_info(fp))
            elif kind in ("unindexed", "thumb_missing"):
                touched.append(f)
            else:
                st["skip"] += 1
                continue
            st["ok"] += 1
            log(f"🔧 {f} : {VERIFY_KINDS.get(kind, (kind, ''))[1]}")
        except Exception as ex:
            logger.exception("réparation %s %s", kind, f)
            log(f"❌ {f} : {friendly_error(ex)}")
            st["fail"] += 1
    entries = [e for e in entries if str(e.get("folder")) not in drop]
    for f in touched:
        fp = os.path.join(root, f)
        info = load_info(fp)
        if info:
            _merge_entry(entries, entry_from_info(info, fp))
    save_archive_index(root, entries)
    return st


# ================================================================= v5 : export / partage / statistiques
_STORED_EXTS = VIDEO_EXTS + AUDIO_EXTS + IMAGE_EXTS + (".zip", ".pdf", ".avif")


def build_catalog_rows(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = []
    for e in entries:
        rows.append({
            "titre": e.get("title") or "", "plateforme": e.get("platform") or "", "url": e.get("url") or "",
            "auteur": e.get("uploader") or "", "publie": fmt_upload_date(e.get("upload_date")),
            "archive_le": fmt_iso(e.get("archived_at")), "duree": human_duration(e.get("duration")),
            "taille_octets": int(e.get("size") or 0), "tags": ", ".join(e.get("tags") or []),
            "collections": ", ".join(e.get("collections") or []), "favori": "oui" if e.get("favorite") else "",
            "en_ligne": ONLINE_LABELS.get(str(e.get("online_status") or ""), ""), "notes": e.get("notes") or "",
            "dossier": e.get("folder") or "",
        })
    return rows


def export_catalog(entries: List[Dict[str, Any]], dest: str) -> int:
    """CSV (séparateur ; UTF-8 BOM pour Excel FR) ou JSON selon l'extension."""
    rows = build_catalog_rows(entries)
    if dest.lower().endswith(".json"):
        _write_json_atomic(dest, rows)
    else:
        import csv
        with open(dest, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["titre"], delimiter=";")
            w.writeheader()
            for r in rows:
                w.writerow(r)
    return len(rows)


def export_zip(root: str, folders: List[str], dest: str,
               progress: Optional[Callable[[int, int, str], None]] = None,
               cancel_event: Optional[threading.Event] = None) -> Tuple[int, int]:
    """ZIP des archives choisies + index.html (cartes) + catalogue.csv. Retourne (fichiers, octets)."""
    import zipfile
    entries = [e for e in load_archive_index(root) if e.get("folder") in set(folders)]
    files: List[Tuple[str, str]] = []
    for f in folders:
        fp = os.path.join(root, f)
        for dp, _dn, fn in os.walk(fp):
            for n in fn:
                if n.endswith(".tmp"):
                    continue
                full = os.path.join(dp, n)
                files.append((full, os.path.relpath(full, root).replace("\\", "/")))
    tmp = dest + ".partiel"
    total = 0
    try:
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as z:
            for i, (full, arc) in enumerate(files):
                if cancel_event is not None and cancel_event.is_set():
                    raise ArchiveCancelled("Export annulé.")
                ct = zipfile.ZIP_STORED if arc.lower().endswith(_STORED_EXTS) else zipfile.ZIP_DEFLATED
                z.write(full, arc, compress_type=ct)
                total += os.path.getsize(full)
                if progress and (i % 5 == 0 or i == len(files) - 1):
                    progress(i + 1, len(files), arc)
            z.writestr("index.html", build_global_index_html(entries, root))
            import csv
            import io
            buf = io.StringIO()
            rows = build_catalog_rows(entries)
            if rows:
                w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()), delimiter=";")
                w.writeheader()
                for r in rows:
                    w.writerow(r)
            z.writestr("catalogue.csv", "\ufeff" + buf.getvalue())
        os.replace(tmp, dest)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    return len(files), total


def entry_summary(e: Dict[str, Any]) -> str:
    lines = [str(e.get("title") or e.get("folder") or ""), str(e.get("url") or e.get("webpage_url") or "")]
    meta = [platform_label(e.get("platform"))]
    if e.get("uploader"):
        meta.append(str(e.get("uploader")))
    if e.get("upload_date"):
        meta.append(fmt_upload_date(e.get("upload_date")))
    lines.append(" · ".join(meta))
    if e.get("tags"):
        lines.append("Tags : " + ", ".join("#" + t for t in e.get("tags") or []))
    if e.get("notes"):
        lines.append("Notes : " + str(e.get("notes")))
    return "\n".join(x for x in lines if x.strip())


def compute_stats(entries: List[Dict[str, Any]], root: str) -> Dict[str, Any]:
    from collections import Counter
    by_plat: Dict[str, List[int]] = {}
    tags: Counter = Counter()
    months: Counter = Counter()
    cols: Counter = Counter()
    online: Counter = Counter()
    dur = 0.0
    for e in entries:
        p = str(e.get("platform") or "web")
        by_plat.setdefault(p, [0, 0])
        by_plat[p][0] += 1
        by_plat[p][1] += int(e.get("size") or 0)
        for t in e.get("tags") or []:
            tags[t.lower()] += 1
        for c in e.get("collections") or []:
            cols[c] += 1
        months[str(e.get("archived_at") or "")[:7] or "?"] += 1
        online[str(e.get("online_status") or "jamais vérifié")] += 1
        try:
            dur += float(e.get("duration") or 0)
        except (TypeError, ValueError):
            pass
    free = None
    try:
        free = shutil.disk_usage(root).free
    except Exception:
        pass
    return {"count": len(entries), "size": sum(v[1] for v in by_plat.values()), "by_platform": by_plat,
            "favorites": sum(1 for e in entries if e.get("favorite")), "tags": tags.most_common(15),
            "months": sorted(months.items())[-12:], "collections": cols.most_common(), "online": dict(online),
            "duration": dur, "free": free,
            "with_transcript": sum(1 for e in entries if e.get("has_transcript"))}


# ================================================================= GUI
try:
    from PIL import Image, ImageDraw, ImageTk  # type: ignore
    HAS_PIL = True
except Exception:  # pragma: no cover
    HAS_PIL = False

JOB_LABELS = {
    "attente": "⏳ En attente",
    "cours": "⬇ En cours",
    "ok": "✅ Terminé",
    "echec": "❌ Échec",
    "annule": "⛔ Annulé",
}

_TkBase = tk.Tk if tk is not None else object


class ScrollFrame(tk.Frame if tk is not None else object):  # type: ignore[misc]
    """Canvas + Frame intérieur + barre verticale ; la largeur suit la fenêtre."""

    def __init__(self, master, bg=NC_BG, **kw):
        super().__init__(master, bg=bg, **kw)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0, yscrollincrement=24)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", self._on_inner)
        self.canvas.bind("<Configure>", self._on_canvas)

    def _on_inner(self, _e=None):
        bbox = self.canvas.bbox(self._win)
        if bbox:
            h = max(bbox[3], self.canvas.winfo_height())
            self.canvas.configure(scrollregion=(0, 0, bbox[2], h))

    def _on_canvas(self, e):
        self.canvas.itemconfigure(self._win, width=e.width)
        self._on_inner()

    def scroll_units(self, n: int) -> None:
        first, last = self.canvas.yview()
        if n < 0 and first <= 0.0:
            return
        if n > 0 and last >= 1.0:
            return
        self.canvas.yview_scroll(n, "units")

    def to_top(self) -> None:
        self.canvas.yview_moveto(0.0)

    def contains(self, widget) -> bool:
        try:
            return str(widget).startswith(str(self.inner)) or str(widget) == str(self.canvas)
        except Exception:
            return False


CONV_CHEERS = [
    (5, ["🚀 Ça décolle !", "🔧 Moteurs allumés…"]),
    (25, ["🛰 En orbite, tout roule", "💪 Ça avance bien"]),
    (45, ["🌠 Belle vitesse de croisière", "🎞 Les images défilent…"]),
    (60, ["🌗 À mi-chemin, capitaine", "☕ Le temps d'un café…"]),
    (80, ["🔥 Plus que la ligne droite", "🧭 Cap maintenu, ça file !"]),
    (100, ["🏁 Presque arrivé…", "✨ Les dernières images…"]),
]


def conv_cheer(pct: float, mode: str = "encode", done: bool = False) -> str:
    if done:
        return "Mission accomplie ✨"
    if mode == "remux":
        return "⚡ Déjà au bon format : rangement éclair"
    if mode == "audio":
        return "⚡ Vidéo déjà bonne : seul le son est converti"
    flip = int(time.time() // 6) % 2
    for lim, msgs in CONV_CHEERS:
        if pct < lim:
            return msgs[flip % len(msgs)]
    return CONV_CHEERS[-1][1][0]


def conv_detail(s: Dict[str, Any]) -> str:
    """Texte vivant : message encourageant · % · vitesse · temps restant."""
    pct = float(s.get("pct") or 0)
    parts = [conv_cheer(pct, str(s.get("mode") or "encode"), bool(s.get("done")))]
    parts.append(f"{pct:.0f} %")
    sp = fmt_speed(s.get("speed")) if (s.get("mode") == "encode" or s.get("done")) else ""
    if sp:
        parts.append(sp)
    if s.get("eta") and not s.get("done"):
        parts.append(f"reste ≈ {human_duration(s['eta']) if s['eta'] >= 1 else '0:01'}")
    enc = str(s.get("encoder") or "")
    if s.get("mode") == "encode" and enc in HW_ENCODERS:
        parts.append("GPU")
    return " · ".join(parts)


class FunBar(tk.Canvas if tk is not None else object):  # type: ignore[misc]
    """Barre de progression animée (rayures jaune/cyan qui défilent sur fond bleu foncé).
    Compatible avec l'API utilisée de ttk.Progressbar : configure(value=…)."""

    def __init__(self, master, width: int = 170, height: int = 16, **kw):
        super().__init__(master, width=width, height=height, highlightthickness=0, bd=0,
                         bg=NC_ENTRY_BG, **kw)
        self._value = 0.0
        self._mood = "normal"
        self._off = 0
        self._anim = None
        self._flash = 0
        self.bind("<Configure>", lambda e: self._draw())

    def set_mood(self, mood: str) -> None:
        if mood != self._mood:
            self._mood = mood
            self._draw()

    def configure(self, cnf=None, **kw):  # type: ignore[override]
        if isinstance(cnf, dict):
            kw = {**cnf, **kw}
            cnf = None
        val = kw.pop("value", None)
        for k in ("mode", "maximum", "orient", "length", "style"):
            kw.pop(k, None)
        r = super().configure(**kw) if kw else None
        if val is not None:
            try:
                v = max(0.0, min(100.0, float(val)))
            except (TypeError, ValueError):
                v = 0.0
            if v >= 100.0 and self._value < 100.0:
                self._flash = 12
            if v <= 0.0:
                self._mood = "normal"
            self._value = v
            self._draw()
            self._ensure_anim()
        return r

    config = configure  # type: ignore[assignment]

    def _ensure_anim(self):
        active = 0.0 < self._value < 100.0 or self._flash > 0
        if active and self._anim is None:
            self._anim = self.after(70, self._tick)

    def _tick(self):
        self._anim = None
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return
        self._off = (self._off + 2) % 14
        if self._flash > 0:
            self._flash -= 1
        self._draw()
        self._ensure_anim()

    def _draw(self):
        try:
            w = max(10, int(self.winfo_width()))
            h = max(6, int(self.winfo_height()))
        except Exception:
            return
        if w <= 10:
            w = int(self.cget("width") or 170)
            h = int(self.cget("height") or 16)
        self.delete("all")
        if str(tk.Canvas.cget(self, "bg")) != NC_ENTRY_BG:
            tk.Canvas.configure(self, bg=NC_ENTRY_BG)
        fw = int(w * self._value / 100.0)
        remux = self._mood == "remux"
        base, stripe = (NC_FG, NC_HI) if remux else (NC_HI, NC_FG)
        if self._flash > 0 and self._flash % 4 < 2:
            base, stripe = NC_OK, NC_HI
        if fw > 0:
            self.create_rectangle(0, 0, fw, h, fill=base, width=0)
            if 0 < self._value < 100:
                x = -h - 14 + self._off
                while x < fw:
                    pts = [max(0, min(fw, x)), h, max(0, min(fw, x + 6)), h,
                           max(0, min(fw, x + 6 + h)), 0, max(0, min(fw, x + h)), 0]
                    self.create_polygon(*pts, fill=stripe, width=0)
                    x += 14
                # petit éclat lumineux au bout de la barre
                self.create_rectangle(max(0, fw - 3), 0, fw, h, fill="#FFFFFF", width=0)
        self.create_rectangle(0, 0, w - 1, h - 1, outline=NC_FG, width=1)
        if self._value > 0:
            txt = f"{self._value:.0f} %"
            self.create_text(w // 2 + 1, h // 2 + 1, text=txt, fill="#000000", font=("Consolas", 8, "bold"))
            self.create_text(w // 2, h // 2, text=txt, fill="#FFFFFF", font=("Consolas", 8, "bold"))


class Tooltip:
    """Infobulle simple (survol 450 ms)."""

    def __init__(self, widget, text: str):
        self.widget, self.text = widget, text
        self._job = None
        self._tip = None
        widget.bind("<Enter>", self._enter, add="+")
        widget.bind("<Leave>", self._leave, add="+")
        widget.bind("<ButtonPress>", self._leave, add="+")

    def _enter(self, _e=None):
        self._cancel()
        self._job = self.widget.after(450, self._show)

    def _cancel(self):
        if self._job:
            try:
                self.widget.after_cancel(self._job)
            except Exception:
                pass
            self._job = None

    def _show(self):
        self._job = None
        if self._tip or not self.text:
            return
        try:
            x = self.widget.winfo_rootx() + 8
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
            tw = tk.Toplevel(self.widget)
            tw.wm_overrideredirect(True)
            try:
                tw.attributes("-topmost", True)
            except Exception:
                pass
            tk.Label(tw, text=self.text, bg=NC_TIP_BG, fg=NC_TIP_FG, font=FONT_SM, justify="left",
                     relief="solid", bd=1, padx=6, pady=3, wraplength=420).pack()
            tw.update_idletasks()
            sw = self.widget.winfo_screenwidth()
            if x + tw.winfo_reqwidth() > sw:
                x = max(0, sw - tw.winfo_reqwidth() - 4)
            tw.wm_geometry(f"+{x}+{y}")
            self._tip = tw
        except Exception:
            self._tip = None

    def _leave(self, _e=None):
        self._cancel()
        if self._tip:
            try:
                self._tip.destroy()
            except Exception:
                pass
            self._tip = None


class FlowFrame(tk.Frame if tk is not None else object):  # type: ignore[misc]
    """Cadre « à la ligne » : les enfants (ajoutés via add) passent à la ligne suivante
    quand la largeur manque — aucun libellé tronqué sur petit écran."""

    def __init__(self, master, bg=NC_BG, padx=4, pady=3, **kw):
        super().__init__(master, bg=bg, height=1, **kw)
        self._items: List[Any] = []
        self._padx, self._pady = padx, pady
        self._lastw = None
        self.bind("<Configure>", self._on_conf)

    def add(self, w, tip: str = ""):
        self._items.append(w)
        if tip:
            Tooltip(w, tip)
        self.after_idle(self.relayout)
        return w

    def set_visible(self, w, visible: bool):
        w._flow_hidden = not visible  # type: ignore[attr-defined]
        if not visible:
            w.place_forget()
        self.relayout()

    def _on_conf(self, e):
        if e.width != self._lastw:
            self._lastw = e.width
            self.relayout()

    def relayout(self):
        W = self.winfo_width()
        if W <= 1:
            W = max(400, self.winfo_toplevel().winfo_width() - 40)
        x = y = rowh = 0
        for w in self._items:
            if getattr(w, "_flow_hidden", False):
                continue
            rw, rh = w.winfo_reqwidth(), w.winfo_reqheight()
            if x > 0 and x + rw > W:
                x = 0
                y += rowh + self._pady
                rowh = 0
            w.place(x=x, y=y)
            x += rw + self._padx
            rowh = max(rowh, rh)
        h = max(1, y + rowh)
        try:
            if int(float(self.cget("height"))) != h:
                self.configure(height=h)
        except Exception:
            pass


class LightPlayer:
    """Lecteur intégré léger, sans installation : ffmpeg décode les images (rgb24 → Tk) et
    ffplay (fourni avec ffmpeg, sans fenêtre : -nodisp) joue le son. La vidéo se cale sur
    l'horloge audio lue dans la ligne d'état de ffplay → synchro stable. Pause / reprise /
    déplacement = relance des deux processus à la position voulue (seek précis via atrim)."""

    FPS_MAX = 25.0

    def __init__(self, app, surface, on_update: Callable[[float, float, str], None]):
        self.app = app
        self.surface = surface          # tk.Label qui affiche les images
        self.on_update = on_update      # (position, durée, état)
        self.path = ""
        self.duration = 0.0
        self.has_video = False
        self.src_w, self.src_h, self.src_fps = 0, 0, 25.0
        self.pos = 0.0
        self.state = "stop"             # stop | play | pause | end
        self.volume = 80
        self.muted = False
        self._pv = None
        self._pa = None
        self._q: "queue.Queue[Optional[bytes]]" = queue.Queue(maxsize=6)
        self._stop_evt = threading.Event()
        self._gen = 0
        self._t0 = 0.0
        self._aclock: Optional[Tuple[float, float]] = None
        self._size = (0, 0)
        self._frame_idx = 0
        self._photo = None
        self._tick_job = None
        self._reader_done = False
        self.last_error = ""

    # ---------------------------------------------------------------- chargement
    def load(self, path: str, info: Optional[Dict[str, Any]] = None) -> bool:
        self.stop()
        self.path = path
        self.pos = 0.0
        self.state = "stop"
        self.last_error = ""
        c = probe_codecs(path)
        self.duration = float(c.get("duration") or (info or {}).get("duration") or 0)
        self.has_video = bool(c.get("vcodec")) and path.lower().endswith(VIDEO_EXTS)
        self.src_w, self.src_h = int(c.get("width") or 0), int(c.get("height") or 0)
        self.src_fps = self._probe_fps(path) or 25.0
        return bool(self.duration)

    @staticmethod
    def _probe_fps(path: str) -> float:
        fp = find_ffprobe()
        if not fp:
            return 0.0
        try:
            r = subprocess.run([fp, "-v", "error", "-select_streams", "v:0", "-show_entries",
                                "stream=avg_frame_rate", "-of", "default=nw=1:nk=1", path],
                               **_hidden_kwargs(), timeout=20)
            txt = (r.stdout or b"").decode("ascii", "ignore").strip()
            if "/" in txt:
                a, b = txt.split("/", 1)
                return float(a) / float(b) if float(b) else 0.0
            return float(txt or 0)
        except Exception:
            return 0.0

    # ---------------------------------------------------------------- géométrie
    def _target_size(self, max_w: int, max_h: int) -> Tuple[int, int]:
        sw, sh = self.src_w or 640, self.src_h or 360
        scale = min(max_w / sw, max_h / sh, 2.0)
        w = max(160, int(sw * scale)) // 2 * 2
        h = max(90, int(sh * scale)) // 2 * 2
        if w * h > 960 * 540:  # limite CPU : ~qHD
            f = (960 * 540 / float(w * h)) ** 0.5
            w, h = int(w * f) // 2 * 2, int(h * f) // 2 * 2
        return w, h

    # ---------------------------------------------------------------- contrôle
    def current(self) -> float:
        if self.state != "play":
            return self.pos
        now = time.monotonic()
        if self._aclock and now - self._aclock[1] < 0.6:
            return min(self.duration or 1e9, self._aclock[0] + (now - self._aclock[1]))
        return min(self.duration or 1e9, self.pos + (now - self._t0))

    def play(self, max_w: int, max_h: int, at: Optional[float] = None) -> None:
        if not self.path:
            return
        if at is not None:
            self.pos = max(0.0, min(float(at), max(0.0, self.duration - 0.2) if self.duration else float(at)))
        elif self.state == "end":
            self.pos = 0.0
        self._kill()
        self._gen += 1
        gen = self._gen
        self._stop_evt = threading.Event()
        self._q = queue.Queue(maxsize=6)
        self._aclock = None
        self._frame_idx = 0
        self._reader_done = not self.has_video
        ff = find_ffmpeg()
        fps = min(self.FPS_MAX, self.src_fps or 25.0)
        self._fps = fps
        if self.has_video and ff:
            w, h = self._target_size(max_w, max_h)
            self._size = (w, h)
            cmd = [ff, "-hide_banner", "-nostdin", "-loglevel", "error", "-ss", f"{self.pos:.3f}", "-i", self.path,
                   "-an", "-sn", "-vf", f"fps={fps:.3f},scale={w}:{h}:flags=bilinear",
                   "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"]
            kw = _hidden_kwargs()
            kw["stderr"] = subprocess.DEVNULL
            kw["bufsize"] = w * h * 3 * 2
            try:
                self._pv = subprocess.Popen(cmd, **kw)
                threading.Thread(target=self._reader, args=(self._pv, w * h * 3, self._q, self._stop_evt),
                                 daemon=True).start()
            except Exception as e:
                self.last_error = f"vidéo : {e}"
                self._reader_done = True
        self._start_audio(gen)
        self._t0 = time.monotonic()
        self.state = "play"
        self._schedule()

    def _start_audio(self, gen: int) -> None:
        fpl = find_ffplay()
        if not fpl or self.muted or self.volume <= 0:
            self._pa = None
            return
        cmd = [fpl, "-hide_banner", "-nodisp", "-vn", "-sn", "-autoexit", "-loglevel", "error", "-stats",
               "-volume", str(int(self.volume))]
        if self.pos > 0.05:
            cmd += ["-ss", f"{self.pos:.3f}", "-af", f"atrim=start={self.pos:.3f}"]
        cmd.append(self.path)
        kw = _hidden_kwargs()
        kw["stdout"] = subprocess.DEVNULL
        try:
            self._pa = subprocess.Popen(cmd, **kw)
            threading.Thread(target=self._audio_clock, args=(self._pa, gen), daemon=True).start()
        except Exception as e:
            self._pa = None
            self.last_error = f"son : {e}"

    def _audio_clock(self, proc, gen: int) -> None:
        buf = b""
        rx = re.compile(rb"^\s*(-?\d+\.\d+)\s+M-A")
        try:
            while True:
                ch = proc.stderr.read(64)
                if not ch:
                    break
                buf += ch
                parts = re.split(rb"[\r\n]", buf)
                buf = parts[-1]
                for ln in parts[:-1]:
                    m = rx.match(ln)
                    if m and gen == self._gen:
                        v = float(m.group(1))
                        if v >= 0:
                            self._aclock = (v, time.monotonic())
        except Exception:
            pass

    @staticmethod
    def _reader(proc, nbytes: int, q, stop_evt) -> None:
        try:
            while not stop_evt.is_set():
                data = proc.stdout.read(nbytes)
                if not data or len(data) < nbytes:
                    break
                while not stop_evt.is_set():
                    try:
                        q.put(data, timeout=0.2)
                        break
                    except queue.Full:
                        continue
        except Exception:
            pass
        finally:
            try:
                q.put(None, timeout=1)
            except Exception:
                pass

    def _schedule(self) -> None:
        if self._tick_job is None:
            self._tick_job = self.app.after(15, self._tick)

    def _tick(self) -> None:
        self._tick_job = None
        if self.state != "play":
            return
        cur = self.current()
        if self.has_video and not self._reader_done:
            target = int((cur - self.pos) * self._fps)
            frame = None
            while self._frame_idx <= target:
                try:
                    item = self._q.get_nowait()
                except queue.Empty:
                    break
                if item is None:
                    self._reader_done = True
                    break
                frame = item
                self._frame_idx += 1
            if frame is not None:
                self._show_frame(frame)
        ended = self.duration and cur >= self.duration - 0.05
        audio_dead = self._pa is None or self._pa.poll() is not None
        if ended or (self._reader_done and audio_dead and (not self.has_video or cur >= self.duration - 0.5)):
            self.pos = self.duration if self.duration else cur
            self._kill()
            self.state = "end"
            self.on_update(self.pos, self.duration, self.state)
            return
        self.on_update(cur, self.duration, self.state)
        self._tick_job = self.app.after(15, self._tick)

    def _show_frame(self, data: bytes) -> None:
        if not HAS_PIL:
            return
        w, h = self._size
        try:
            im = Image.frombuffer("RGB", (w, h), data, "raw", "RGB", 0, 1)
            if self._photo is None or (self._photo.width(), self._photo.height()) != (w, h):
                self._photo = ImageTk.PhotoImage(im)
                self.surface.configure(image=self._photo, text="", height=h)
            else:
                self._photo.paste(im)
        except Exception:
            logger.exception("image lecteur")

    def show_still(self, max_w: int, max_h: int, at: float) -> None:
        """Affiche l'image à la position donnée (pause / déplacement)."""
        ff = find_ffmpeg()
        if not (self.has_video and ff and HAS_PIL):
            return
        w, h = self._target_size(max_w, max_h)
        try:
            r = subprocess.run([ff, "-hide_banner", "-nostdin", "-loglevel", "error", "-ss", f"{max(0.0, at):.3f}",
                                "-i", self.path, "-frames:v", "1", "-an", "-sn", "-vf", f"scale={w}:{h}",
                                "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"], **_hidden_kwargs(), timeout=20)
            data = r.stdout or b""
            if len(data) >= w * h * 3:
                self._size = (w, h)
                self._show_frame(data[:w * h * 3])
        except Exception:
            logger.exception("image fixe")

    def pause(self) -> None:
        if self.state == "play":
            self.pos = self.current()
            self._kill()
            self.state = "pause"
            self.on_update(self.pos, self.duration, self.state)

    def seek(self, t: float, max_w: int, max_h: int) -> None:
        t = max(0.0, min(float(t), self.duration or float(t)))
        if self.state == "play":
            self.play(max_w, max_h, at=t)
        else:
            self.pos = t
            if self.state == "end":
                self.state = "pause"
            if self.state == "stop":
                self.state = "pause"
            self.show_still(max_w, max_h, t)
            self.on_update(self.pos, self.duration, self.state)

    def set_volume(self, vol: int, muted: Optional[bool] = None) -> None:
        self.volume = max(0, min(100, int(vol)))
        if muted is not None:
            self.muted = bool(muted)
        if self.state == "play":
            cur = self.current()
            if self._pa is not None:
                try:
                    self._pa.kill()
                except Exception:
                    pass
            self._pa = None
            self._aclock = None
            # recaler l'horloge locale sur la position actuelle avant de relancer le son
            self._frame_idx = int((cur - self.pos) * self._fps)
            self._t0 = time.monotonic() - (cur - self.pos)
            saved = self.pos
            self.pos = cur
            self._gen += 0
            self._start_audio(self._gen)
            self.pos = saved

    def stop(self) -> None:
        self._kill()
        self.state = "stop"
        self.pos = 0.0
        self._photo = None

    def _kill(self) -> None:
        if self._tick_job is not None:
            try:
                self.app.after_cancel(self._tick_job)
            except Exception:
                pass
            self._tick_job = None
        self._stop_evt.set()
        for p in (self._pv, self._pa):
            if p is not None:
                try:
                    p.kill()
                except Exception:
                    pass
                try:
                    p.wait(timeout=2)
                except Exception:
                    pass
        self._pv = self._pa = None
        self._aclock = None


COLL_ALL_LABEL = "Toutes collections"
PLAT_ALL_LABEL = "Toutes plateformes"
GUI_ONLINE = {"online": ("●", "en ligne"), "offline": ("✖", "supprimé / introuvable"),
              "restricted": ("⚠", "accès restreint (privé, connexion…)"), "unknown": ("?", "inconnu (non vérifiable)")}


def online_color(st: str) -> str:
    return {"online": NC_OK, "offline": NC_ERR, "restricted": NC_WARN}.get(st, NC_DIM)


def wrap_name(name: str, width: int = 22, lines: int = 2) -> str:
    """Nom de fichier sur 2 lignes max (coupure après _ - . ou espace), sans rien cacher d'important."""
    if len(name) <= width:
        return name
    out, rest = [], name
    while rest and len(out) < lines:
        if len(rest) <= width or len(out) == lines - 1:
            if len(rest) > width:
                base, ext = os.path.splitext(rest)
                keep = width - len(ext) - 1
                rest = base[:max(4, keep)] + "…" + ext
            out.append(rest)
            break
        cut = max(rest.rfind(c, 0, width) for c in "_- .")
        cut = cut + 1 if cut >= width // 2 else width
        out.append(rest[:cut])
        rest = rest[cut:]
    return "\n".join(out)


HELP_TEXT: List[Tuple[str, str]] = [
    ("h", "📋 Archiver"),
    ("p", "Copie un lien (X, Facebook, YouTube, TikTok, Instagram, article de presse, n'importe quelle page web) "
          "puis clique « 📋 Coller et archiver » ou fais Ctrl+V n'importe où dans la fenêtre. Tu peux aussi "
          "glisser-déposer un lien (ou un fichier .txt de liens) sur la fenêtre."),
    ("p", "Les vidéos sont enregistrées en MP4 lisible partout, avec texte du post, miniature, sous-titres, "
          "transcription et storyboard. Les pages web sont archivées en « lecture » (texte propre), copie "
          "complète hors ligne, capture d'écran et PDF. Pour X, le fil (messages précédents) est aussi gardé."),
    ("h", "▶ Lecteur intégré"),
    ("p", "▶ Lire (ou clic sur l'image) lit la vidéo directement dans l'aperçu : barre de position, ±10 s, volume. "
          "« ⛶ Grande fenêtre » (ou double-clic sur l'image) l'ouvre dans une fenêtre séparée. "
          "« ↗ Externe » utilise le lecteur Windows / VLC / mpv."),
    ("h", "🗣 Transcription"),
    ("p", "Les sous-titres (YouTube…) deviennent une transcription horodatée : clic sur [m:ss] = lecture à cet "
          "endroit, champ 🔎 pour chercher, et la recherche de l'historique fouille aussi dedans. "
          "Sans sous-titres : « 🎙 Transcrire (local) » si Whisper est installé (rien n'est envoyé en ligne)."),
    ("h", "✂ Outils média"),
    ("p", "Capture d'image, extrait vidéo, MP3, GIF animé à partir de n'importe quelle archive vidéo. "
          "Mets la vidéo en pause au bon endroit puis « = position du lecteur ». Résultat dans extraits/."),
    ("h", "🗂 Comment ranger ?"),
    ("p", "À gauche, la barre « 📚 Collections » : clic sur une collection = tu ne vois qu'elle ; « 🗂 Toutes » = tout. "
          "« 📥 Non classées » montre ce qui reste à ranger."),
    ("p", "Pour ranger une archive : clique « ✔ Oui » sur le bandeau jaune « Ranger dans … ? » au-dessus de l'aperçu "
          "(ou « Autre… » pour choisir), ou clic droit → 📂 Déplacer vers la collection… (marche aussi sur plusieurs "
          "archives choisies avec Ctrl+clic). « ✨ Ranger tout automatiquement » range d'un coup les non classées : "
          "tu vois la liste avant, et « ↩ Annuler le rangement » remet tout comme avant."),
    ("h", "🎞 Storyboard"),
    ("p", "Une rangée de petites images tirées de la vidéo (une à intervalles réguliers). Il se prépare tout seul en "
          "quelques secondes. Clique sur une image : la vidéo part à ce moment-là."),
    ("h", "★ Favoris et 📚 collections"),
    ("p", "Ctrl+D ou « ☆ Favori ». Clic droit sur une ou plusieurs archives → 📚 Collections pour les classer "
          "(Recettes, Politique…). Le menu « Collection » au-dessus de l'historique filtre la liste. "
          "Ctrl+clic / Maj+clic = sélection multiple ; Ctrl+A = tout sélectionner."),
    ("h", "🧰 Outils"),
    ("p", "Vérifier les archives (fichiers manquants ou corrompus, réparation en un clic) · vérifier si les "
          "originaux sont encore en ligne (✖ supprimé : ton archive est alors la seule copie) · statistiques · "
          "export ZIP à partager (avec une page index.html) · catalogue CSV pour Excel · mise à jour de yt-dlp."),
    ("h", "⌨ Raccourcis clavier"),
    ("k", "Ctrl+V|coller et archiver (hors champs texte)"),
    ("k", "Entrée|archiver le(s) lien(s) du champ"),
    ("k", "Ctrl+Espace|lecture / pause du lecteur intégré"),
    ("k", "Ctrl+← / Ctrl+→|reculer / avancer de 10 s"),
    ("k", "Ctrl+F|chercher dans l'historique"),
    ("k", "Ctrl+D|favori oui / non"),
    ("k", "Ctrl+E|exporter la sélection en ZIP"),
    ("k", "Ctrl+A|tout sélectionner (historique)"),
    ("k", "Ctrl+S|enregistrer tags et notes"),
    ("k", "F2|renommer l'archive"),
    ("k", "F5|relire le dossier des archives"),
    ("k", "Suppr|supprimer (confirmation)"),
    ("k", "Ctrl+molette, Ctrl +/−/0|taille du texte"),
    ("k", "Échap|replier la file d'attente / fermer une fenêtre"),
    ("k", "F1|cette aide"),
    ("h", "🔒 Confidentialité"),
    ("p", "Tout est stocké sur ce PC. Seuls les sites d'origine sont contactés (et api.fxtwitter.com pour X si "
          "l'option est active). La vérification « en ligne » interroge uniquement l'adresse d'origine."),
]


class ArchiveurApp(_TkBase):  # type: ignore[misc]
    def __init__(self, smoke: float = 0.0, geometry: str = "", shot: str = "", force_scaling: float = 0.0,
                 root_override: str = "", font_delta: Optional[int] = None, shot_action: str = ""):
        super().__init__()
        if force_scaling:
            try:
                self.tk.call("tk", "scaling", force_scaling)
            except Exception:
                pass
        _fd = font_delta if font_delta is not None else int(_EARLY_CFG.get("font_delta") or 0)
        init_fonts(self, _fd)
        self._shot_action = shot_action
        self._root_override = root_override
        self._save_cfg_job = None
        self._online_busy = False
        self._export_busy = False
        self._dnd_ok = False
        self._modal_win = None
        self.title(APP_NAME)
        self._test_geometry = geometry
        self._shot = shot
        self._players = detect_players()
        self._codec_cache: Dict[Tuple[str, float], Dict[str, Any]] = {}
        self._bottom_view = "queue"
        self._bottom_open = False
        self._bottom_auto = False
        self.cfg = load_cfg()
        if font_delta is not None:
            self.cfg["font_delta"] = font_delta
        if root_override:
            self.cfg["archive_root"] = root_override
        self.archive_root = self.cfg.get("archive_root") or DEFAULT_ROOT
        self._smoke = smoke
        self._errors: List[str] = []
        self._uiq: "queue.Queue[Callable[[], None]]" = queue.Queue()
        self.jobs: List[Dict[str, Any]] = []
        self._job_seq = 0
        self._jobs_lock = threading.Lock()
        self._worker_running = False
        self._cancel_event = threading.Event()
        self._run_stats = {"ok": 0, "echec": 0, "annule": 0, "last_title": ""}
        self.entries: List[Dict[str, Any]] = []
        self._visible: List[Dict[str, Any]] = []
        self._iid_entry: Dict[str, Dict[str, Any]] = {}
        self.last_folder: Optional[str] = None
        self._preview_entry: Optional[Dict[str, Any]] = None
        self._preview_info: Dict[str, Any] = {}
        self._preview_path = ""
        self._loaded_tn = ("", "")
        self._thumb_src = None
        self._thumb_base = None
        self._thumb_is_video = False
        self._thumb_photo = None
        self._sb_photos: List[Any] = []
        self._gal_photos: List[Any] = []
        self._list_thumbs: Dict[Tuple[str, float], Any] = {}
        self._sb_busy: set = set()
        self._sb_failed: set = set()
        self._sb_imcache: Dict[Tuple[str, float, int], Any] = {}
        self._auto_undo: Optional[Dict[str, Any]] = None
        self._sug: Optional[Tuple[str, str]] = None
        self._coll_side_lock = False
        self._clip_last: Optional[str] = None
        self._clip_seen: set = set()
        self._clip_job = None
        self._clip_pending: List[str] = []
        self._resize_job = None
        self._link_target: Tuple[str, str] = ("url", "")
        self._link_seq = 0
        self.report_callback_exception = self._tk_error
        self._build_ui()
        self._build_ui_rest()
        self.after(40, self._drain_ui)
        self.after(150, self._post_init)

    # ------------------------------------------------------------ thread-safe UI
    def ui(self, fn: Callable[[], None]) -> None:
        """Planifie fn dans le thread Tk (file + after())."""
        self._uiq.put(fn)

    def _drain_ui(self):
        for _ in range(300):
            try:
                fn = self._uiq.get_nowait()
            except queue.Empty:
                break
            try:
                fn()
            except Exception as e:
                self._tk_error(type(e), e, e.__traceback__)
        try:
            self.after(40, self._drain_ui)
        except Exception:
            pass

    def _tk_error(self, exc, val, tb):
        msg = "".join(traceback.format_exception(exc, val, tb))
        logger.error("Erreur interface:\n%s", msg)
        self._errors.append(f"{exc.__name__}: {val}")
        try:
            print(msg, file=sys.stderr, flush=True)
        except Exception:
            pass
        try:
            self.status.set(f"⚠ Erreur interne : {val} — détails dans archiveur.log")
        except Exception:
            pass

    # ------------------------------------------------------------ helpers UI
    def _btn(self, parent, text, cmd, hi=False, font=FONT_SM, **kw):
        return tk.Button(
            parent, text=text, command=cmd,
            bg=NC_HI if hi else NC_BTN, fg=NC_ON_HI if hi else NC_BTN_FG,
            activebackground=NC_HI_ACT if hi else NC_HI, activeforeground=NC_ON_HI,
            font=font, relief="raised", bd=1, padx=6, cursor="hand2",
            disabledforeground=NC_DISABLED, **kw,
        )

    def _scrolled_text(self, parent, height=8, **kw):
        fr = tk.Frame(parent, bg=NC_BG)
        txt = tk.Text(fr, height=height, bg=kw.pop("bg", NC_PANEL), fg=kw.pop("fg", NC_FG),
                      insertbackground=NC_FG, wrap=kw.pop("wrap", "word"), bd=1, relief="sunken",
                      selectbackground=NC_SEL, selectforeground=NC_ON_SEL, **kw)
        sb = ttk.Scrollbar(fr, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        txt.pack(side="left", fill="both", expand=True)
        return fr, txt

    def _section(self, parent, text):
        lab = tk.Label(parent, text=text, bg=NC_BG, fg=NC_HI, font=FONT_UI, anchor="w")
        lab.pack(fill="x", padx=8, pady=(12, 2))
        line = tk.Frame(parent, bg=NC_LINE, height=1)
        line.pack(fill="x", padx=8, pady=(0, 4))
        lab._line = line  # type: ignore[attr-defined]
        return lab

    # ------------------------------------------------------------ construction
    def _build_ui(self):
        self.configure(bg=NC_BG)
        if self._test_geometry:
            self.geometry(f"{self._test_geometry}+0+0")
            try:
                self.attributes("-topmost", True)
            except Exception:
                pass
        else:
            self._zoom()
        self.minsize(900, 520)

    def _zoom(self):
        try:
            self.state("zoomed")
        except Exception:
            try:
                self.attributes("-zoomed", True)
            except Exception:
                pass
            self.geometry(f"{self.winfo_screenwidth()}x{self.winfo_screenheight()}+0+0")

    def _build_ui_rest(self):
        ico, png = generate_icons(BASE)
        try:
            if os.path.isfile(ico) and sys.platform.startswith("win"):
                self.iconbitmap(ico)
        except Exception:
            pass
        try:
            if os.path.isfile(png):
                self._icon_img = tk.PhotoImage(file=png)
                self.iconphoto(True, self._icon_img)
        except Exception:
            pass

        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TFrame", background=NC_BG)
        style.configure("TLabel", background=NC_BG, foreground=NC_FG, font=FONT_UI)
        style.configure("TCheckbutton", background=NC_BG, foreground=NC_FG, font=FONT_SM)
        style.map("TCheckbutton", background=[("active", NC_PANEL)], foreground=[("active", NC_HI)])
        style.configure("TButton", font=FONT_UI)
        style.configure("TLabelframe", background=NC_BG, foreground=NC_HI, bordercolor=NC_FG)
        style.configure("TLabelframe.Label", background=NC_BG, foreground=NC_HI, font=FONT_UI)
        style.configure("TCombobox", fieldbackground=NC_ENTRY_BG, background=NC_BTN, foreground=NC_ENTRY_FG,
                        arrowcolor=NC_HI, selectbackground=NC_ENTRY_BG, selectforeground=NC_ENTRY_FG)
        style.map("TCombobox", fieldbackground=[("readonly", NC_ENTRY_BG)], foreground=[("readonly", NC_ENTRY_FG)])
        self.option_add("*TCombobox*Listbox.background", NC_PANEL)
        self.option_add("*TCombobox*Listbox.foreground", NC_FG)
        self.option_add("*TCombobox*Listbox.selectBackground", NC_SEL)
        self.option_add("*TCombobox*Listbox.selectForeground", NC_ON_SEL)
        style.configure("Vertical.TScrollbar", background=NC_BTN, troughcolor=NC_PANEL,
                        arrowcolor=NC_HI, bordercolor=NC_FG, lightcolor=NC_BTN, darkcolor=NC_BTN)
        style.map("Vertical.TScrollbar", background=[("active", NC_SEL)])
        for name, rh in (("Arch.Treeview", 52), ("Files.Treeview", 24), ("Queue.Treeview", 24)):
            style.configure(name, background=NC_PANEL, fieldbackground=NC_PANEL, foreground=NC_FG,
                            rowheight=rh, font=FONT_SM, bordercolor=NC_LINE, indent=4)
            style.map(name, background=[("selected", NC_SEL)], foreground=[("selected", NC_ON_SEL)])
            style.configure(name + ".Heading", background=NC_BG, foreground=NC_HI, font=FONT_SM, relief="raised")
            style.map(name + ".Heading", background=[("active", NC_PANEL)])
        style.configure("Coll.Treeview", background=NC_PANEL, fieldbackground=NC_PANEL, foreground=NC_TEXT,
                        rowheight=30, font=FONT_UI, bordercolor=NC_LINE, indent=2)
        style.map("Coll.Treeview", background=[("selected", NC_HI)], foreground=[("selected", NC_ON_HI)])
        style.configure("TNotebook", background=NC_BG, bordercolor=NC_FG)
        style.configure("TNotebook.Tab", background=NC_PANEL, foreground=NC_FG, font=FONT_SM, padding=(10, 3))
        style.map("TNotebook.Tab", background=[("selected", NC_HI)], foreground=[("selected", NC_ON_HI)])
        style.configure("Arch.Horizontal.TProgressbar", troughcolor=NC_PANEL, background=NC_HI,
                        bordercolor=NC_FG, lightcolor=NC_HI, darkcolor=NC_SEL)
        style.configure("Arch.Horizontal.TScale", background=NC_HI, troughcolor=NC_ENTRY_BG, bordercolor=NC_LINE,
                        lightcolor=NC_HI, darkcolor=NC_SEL, sliderlength=18)
        style.map("Arch.Horizontal.TScale", background=[("active", NC_HI_ACT)])
        style.configure("TCheckbutton", background=NC_BG, foreground=NC_FG, font=FONT_SM)
        style.configure("TCombobox", arrowsize=max(12, font_px(self, FONT_SM) - 2))
        self._apply_row_heights()
        self._build_top()
        # barre d'état (tout en bas) puis panneau file/journal repliable, puis contenu
        self.status = tk.StringVar(value="Prêt.")
        sbar = tk.Frame(self, bg=NC_PANEL)
        sbar.pack(fill="x", side="bottom")
        keys = tk.Label(sbar, text="⌨ Raccourcis", bg=NC_PANEL, fg=NC_DIM, font=FONT_SM, cursor="question_arrow")
        keys.pack(side="right", padx=8)
        Tooltip(keys, "F1 = aide complète\nCtrl+V = coller + archiver (partout hors champs texte)\n"
                      "Ctrl+Espace = lecture / pause · Ctrl+←/→ = ±10 s\nCtrl+F = chercher dans l'historique\n"
                      "Ctrl+D = favori · Ctrl+E = export ZIP · Ctrl+A = tout sélectionner\n"
                      "Ctrl+S = enregistrer tags/notes · F2 = renommer · F5 = rafraîchir\n"
                      "Ctrl+molette ou Ctrl +/−/0 = taille du texte\nSuppr = supprimer · Échap = replier la file")
        keys.bind("<Button-1>", lambda e: self.open_help())
        tk.Label(sbar, textvariable=self.status, bg=NC_PANEL, fg=NC_HI, font=FONT_SM, anchor="w").pack(
            side="left", fill="x", expand=True, padx=8, pady=2)
        bottom = tk.Frame(self, bg=NC_BG)
        bottom.pack(fill="x", side="bottom", padx=8, pady=(2, 0))
        self._build_bottom(bottom)

        self.hpane = tk.PanedWindow(self, orient="horizontal", bg=NC_SASH, sashwidth=7,
                                    sashrelief="raised", bd=0, opaqueresize=True)
        self.hpane.pack(fill="both", expand=True, padx=8, pady=(2, 0))
        left = tk.Frame(self.hpane, bg=NC_BG)
        right = tk.Frame(self.hpane, bg=NC_BG)
        self.hpane.add(left, minsize=300, stretch="always")
        self.hpane.add(right, minsize=400, stretch="always")
        self._build_history(left)
        self._build_preview(right)

        self._link_menu = self._menu()
        self._link_menu.add_command(label="🌐 Ouvrir le lien", command=self._link_open)
        self._link_menu.add_command(label="📋 Copier le lien", command=self._link_copy)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<F2>", lambda e: self.rename_selected())
        self.bind("<Control-f>", lambda e: (self.search_entry.focus_set(), "break")[1])
        self.bind("<Control-F>", lambda e: (self.search_entry.focus_set(), "break")[1])
        self.bind("<Control-s>", lambda e: (self.save_tags_notes(), "break")[1])
        self.bind("<Control-S>", lambda e: (self.save_tags_notes(), "break")[1])
        self.bind_all("<MouseWheel>", self._on_wheel, add="+")
        self.bind_all("<Button-4>", self._on_wheel, add="+")
        self.bind_all("<Button-5>", self._on_wheel, add="+")
        self.bind("<Control-v>", self._global_paste)
        self.bind("<Control-V>", self._global_paste)
        self.bind("<Escape>", lambda e: self._collapse_bottom() if self._bottom_open else None)
        self._bind_v5_keys()
        self.after(300, self._init_sashes)
        self.after(600, self._init_sashes)

    def _menu(self):
        return tk.Menu(self, tearoff=0, bg=NC_PANEL, fg=NC_FG, activebackground=NC_SEL,
                       activeforeground=NC_ON_SEL, font=FONT_SM)

    def _init_sashes(self):
        try:
            self.update_idletasks()
            w = self.hpane.winfo_width()
            if w > 100 and not getattr(self, "_sash_user", False):
                self.hpane.sash_place(0, max(300, min(int(w * 0.42), w - 420)), 0)
        except Exception:
            logger.exception("sash")

    def _global_paste(self, event=None):
        """Ctrl+V hors champ texte = coller + archiver."""
        try:
            cls = event.widget.winfo_class() if event is not None else ""
        except Exception:
            cls = ""
        if cls in ("Entry", "Text", "TEntry", "TCombobox", "Spinbox"):
            return None
        self.paste_and_archive()
        return "break"

    def _build_top(self):
        top = tk.Frame(self, bg=NC_BG)
        top.pack(fill="x", padx=8, pady=(6, 2))
        url_row = tk.Frame(top, bg=NC_BG)
        url_row.pack(fill="x", pady=(0, 3))
        url_row.columnconfigure(0, weight=1)
        fr, self.url_text = self._scrolled_text(url_row, height=2, bg=NC_ENTRY_BG, fg=NC_ENTRY_FG, font=FONT_UI)
        fr.grid(row=0, column=0, sticky="nsew")
        paste_btn = tk.Button(
            url_row, text="📋 Coller et\narchiver", command=self.paste_and_archive,
            bg=NC_HI, fg=NC_ON_HI, font=FONT_PASTE, activebackground=NC_HI_ACT,
            activeforeground=NC_ON_HI, justify="center", cursor="hand2", padx=10,
        )
        paste_btn.grid(row=0, column=1, sticky="ns", padx=(6, 0))
        Tooltip(paste_btn, "Colle le lien copié (presse-papiers), l'affiche dans le champ et lance l'archivage.\nRaccourci : Ctrl+V")
        side = tk.Frame(url_row, bg=NC_BG)
        side.grid(row=0, column=2, sticky="ns", padx=(6, 0))
        b = self._btn(side, "▶ Archiver", self.enqueue_from_text, font=FONT_UI)
        b.pack(fill="x", pady=(0, 3))
        Tooltip(b, "Archive le(s) lien(s) écrit(s) dans le champ (Entrée)")
        b = self._btn(side, "📝 Plusieurs liens…", self.open_batch_dialog)
        b.pack(fill="x")
        Tooltip(b, "Coller une liste de liens à archiver en lot")
        t = self.url_text
        self._url_ph = False
        t.tag_configure("ph", foreground=NC_DIM)
        self._url_placeholder()
        t.bind("<Key>", self._url_key, add="+")
        t.bind("<FocusOut>", lambda e: self._url_placeholder(), add="+")
        t.bind("<Control-v>", self._on_paste_archive)
        t.bind("<Control-V>", self._on_paste_archive)
        t.bind("<Shift-Insert>", self._on_paste_archive)
        t.bind("<Control-a>", self._on_select_all)
        t.bind("<Control-A>", self._on_select_all)
        t.bind("<Return>", self._on_enter_archive)
        t.bind("<Control-Return>", self._on_enter_archive)
        t.bind("<Button-3>", self._show_url_menu)
        self._url_menu = self._menu()
        self._url_menu.add_command(label="📋 Coller et archiver", command=self.paste_and_archive)
        self._url_menu.add_command(label="📰 Archiver comme page web (lecture + capture + PDF)",
                                   command=self.archive_text_as_page)
        self._url_menu.add_command(label="Coller", command=self._ctx_paste)
        self._url_menu.add_command(label="Copier", command=self._ctx_copy)
        self._url_menu.add_command(label="Couper", command=self._ctx_cut)
        self._url_menu.add_separator()
        self._url_menu.add_command(label="Tout sélectionner", command=lambda: self._on_select_all())
        self._url_menu.add_command(label="Effacer", command=self._ctx_clear)

        # bannière presse-papiers (cachée par défaut)
        self.clip_banner = tk.Frame(top, bg=NC_HI)
        self.clip_msg = tk.Label(self.clip_banner, text="", bg=NC_HI, fg=NC_ON_HI, font=FONT_UI, anchor="w")
        self.clip_msg.pack(side="left", fill="x", expand=True, padx=6, pady=3)
        self.clip_btns = tk.Frame(self.clip_banner, bg=NC_HI)
        self.clip_btns.pack(side="right", padx=4)
        self._clip_anchor = tk.Frame(top, bg=NC_BG, height=0)
        self._clip_anchor.pack(fill="x")

        self.subs_var = tk.BooleanVar(value=bool(self.cfg.get("subtitles", True)))
        self.sb_var = tk.BooleanVar(value=bool(self.cfg.get("storyboard", True)))
        self.cookies_var = tk.BooleanVar(value=bool(self.cfg.get("cookies_from_browser")))
        self.browser_var = tk.StringVar(value=str(self.cfg.get("cookies_browser") or "chrome"))
        self.clip_var = tk.BooleanVar(value=bool(self.cfg.get("clipboard_watch", False)))
        self.clip_auto_var = tk.BooleanVar(value=bool(self.cfg.get("clipboard_auto", False)))
        self.notif_var = tk.BooleanVar(value=bool(self.cfg.get("notifications", True)))
        self.conv_var = tk.BooleanVar(value=bool(self.cfg.get("auto_convert", True)))
        self.quality_var = tk.StringVar(value=LABEL_BY_QUALITY.get(self.cfg.get("quality"), "Meilleure"))
        self.root_var = tk.StringVar(value=self.archive_root)

        flow = FlowFrame(top)
        flow.pack(fill="x", pady=(2, 0))
        self.opts_flow = flow

        def group(*_a):
            return tk.Frame(flow, bg=NC_BG)

        g = group()
        tk.Label(g, text="Qualité:", bg=NC_BG, fg=NC_FG, font=FONT_SM).pack(side="left")
        cb = ttk.Combobox(g, textvariable=self.quality_var, values=[lab for _k, lab in QUALITY_LABELS],
                          width=11, state="readonly", font=FONT_SM)
        cb.pack(side="left", padx=(3, 0))
        cb.bind("<<ComboboxSelected>>", lambda e: self._persist_opts())
        flow.add(g, "Vidéo : H.264/AAC en MP4 (lisible partout) à la meilleure résolution disponible.")

        def chk(text, var, cmd, tip):
            w = ttk.Checkbutton(flow, text=text, variable=var, command=cmd)
            flow.add(w, tip)
            return w
        chk("Sous-titres", self.subs_var, self._persist_opts, "Télécharge aussi les sous-titres FR/EN (.vtt)")
        g = group()
        ttk.Checkbutton(g, text="Cookies", variable=self.cookies_var, command=self._persist_opts).pack(side="left")
        bcb = ttk.Combobox(g, textvariable=self.browser_var, values=("chrome", "edge", "firefox"),
                           width=7, state="readonly", font=FONT_SM)
        bcb.pack(side="left", padx=(2, 0))
        bcb.bind("<<ComboboxSelected>>", lambda e: self._persist_opts())
        flow.add(g, "Utiliser les cookies du navigateur (posts X/Facebook qui exigent une connexion)")
        chk("📋 Surveiller", self.clip_var, self._toggle_clip_watch,
            "Surveiller le presse-papiers : propose d'archiver chaque lien que tu copies")
        chk("lancer auto", self.clip_auto_var, self._persist_opts,
            "Avec la surveillance : archiver tout de suite sans demander")

        vals = [PLAYER_LABELS["windows"]] + [PLAYER_LABELS[k] for k in ("vlc", "mpv") if k in self._players]
        cur = self.cfg.get("player") or "windows"
        if cur not in self._players:
            cur = "windows"
        self.player_var = tk.StringVar(value=PLAYER_LABELS.get(cur, PLAYER_LABELS["windows"]))

        for txt, cmd, tip, hi in (
            ("🌐 Index", self.open_global_index, "Page HTML de toutes les archives (cartes, recherche, favoris)", False),
        ):
            flow.add(self._btn(flow, txt, cmd, hi=hi), tip)
        self._tools_btn = flow.add(self._btn(flow, "🧰 Outils ▾", lambda: self._post_menu(self._tools_btn, self._build_tools_menu())),
                                   "Vérifier les archives, vérifier si les originaux sont en ligne, statistiques,\n"
                                   "export ZIP / catalogue, régénérer l'index, réparer les codecs, mise à jour de yt-dlp")
        flow.add(self._btn(flow, "⚙ Réglages", self.open_settings),
                 "Thème, taille du texte, lecteur intégré, capture des pages web, X (fxtwitter), Whisper")
        flow.add(self._btn(flow, "❓ Aide", self.open_help), "Mode d'emploi et raccourcis clavier (F1)")
        flow.add(self._btn(flow, "📂 Ouvrir le dossier", self.open_last_or_selected_folder, hi=True),
                 "Ouvre le dossier de l'archive sélectionnée (sinon la dernière, sinon la racine)")

    # ------------------------------------------------------------ champ URL : texte d'aide
    _URL_HINT = "Colle un lien ici (Ctrl+V = coller + archiver) — ou plusieurs, un par ligne"

    def _url_placeholder(self):
        t = self.url_text
        if not t.get("1.0", "end-1c").strip():
            t.delete("1.0", "end")
            t.insert("1.0", self._URL_HINT, ("ph",))
            self._url_ph = True

    def _url_clear_ph(self):
        if self._url_ph:
            self.url_text.delete("1.0", "end")
            self._url_ph = False

    def _url_key(self, event):
        if event.keysym in ("Control_L", "Control_R", "Shift_L", "Shift_R", "Alt_L", "Alt_R", "Tab"):
            return None
        if self._url_ph and not (event.state & 0x4):
            self._url_clear_ph()
        return None

    def _url_content(self) -> str:
        return "" if self._url_ph else self.url_text.get("1.0", "end")

    # ------------------------------------------------------------ historique
    def _build_history(self, left):
        # barre des collections (à gauche) : clic = n'afficher que cette collection
        side = tk.Frame(left, bg=NC_PANEL, highlightbackground=NC_LINE, highlightthickness=1)
        self._coll_side = side
        main = tk.Frame(left, bg=NC_BG)
        self._hist_main = main
        side.pack(side="left", fill="y", padx=(0, 6), pady=(2, 4))
        main.pack(side="left", fill="both", expand=True)
        tk.Label(side, text="📚 Collections", bg=NC_PANEL, fg=NC_HI, font=FONT_UI, anchor="w").pack(
            fill="x", padx=6, pady=(6, 2))
        self.coll_tree = ttk.Treeview(side, style="Coll.Treeview", show="tree", selectmode="browse", height=10)
        try:
            cw = max(150, tkfont.nametofont(FONT_UI, root=self).measure("Santé & Nutrition (99)") + 12)
        except Exception:
            cw = 180
        self.coll_tree.column("#0", width=min(cw, 210), stretch=True)
        self.coll_tree.tag_configure("dim", foreground=NC_DIM)
        self.coll_tree.pack(fill="both", expand=True, padx=4)
        self.coll_tree.bind("<<TreeviewSelect>>", self._on_coll_side)
        self.coll_tree.bind("<Button-3>", self._coll_side_menu)
        Tooltip(self.coll_tree, "Clic = afficher seulement cette collection.\n"
                                "Pour ranger : clic droit sur une archive → 📂 Déplacer vers la collection…\n"
                                "(Ctrl+clic / Maj+clic pour en choisir plusieurs)")
        b = self._btn(side, "✨ Ranger tout\nautomatiquement", self.auto_classify, hi=True, font=FONT_SM,
                      justify="center")
        b.pack(fill="x", padx=4, pady=(6, 2))
        Tooltip(b, "Propose une collection pour chaque archive NON classée (même série, santé, musique…).\n"
                   "Tu vois la liste avant, et tu peux tout annuler après.")
        b = self._btn(side, "➕ Nouvelle collection", self.new_collection)
        b.pack(fill="x", padx=4, pady=(0, 2))
        Tooltip(b, "Créer une collection (les archives sélectionnées y sont ajoutées)")
        self.undo_btn = self._btn(side, "↩ Annuler le rangement", self.undo_auto_classify)
        Tooltip(self.undo_btn, "Remet les archives rangées automatiquement dans « Non classées »")
        self._undo_anchor = tk.Frame(side, bg=NC_PANEL, height=4)
        self._undo_anchor.pack(fill="x")
        left = main
        head = tk.Frame(left, bg=NC_BG)
        head.pack(fill="x", pady=(2, 2))
        self._side_toggle = self._btn(head, "◀", self._toggle_coll_side)
        self._side_toggle.pack(side="left", padx=(0, 4))
        Tooltip(self._side_toggle, "Cacher / afficher la barre des collections")
        tk.Label(head, text="🗂 Historique", bg=NC_BG, fg=NC_HI, font=FONT_UI).pack(side="left")
        self.count_var = tk.StringVar(value="0 archive")
        tk.Label(head, textvariable=self.count_var, bg=NC_BG, fg=NC_FG, font=FONT_SM).pack(side="right", padx=4)
        srow = tk.Frame(left, bg=NC_BG)
        srow.pack(fill="x")
        tk.Label(srow, text="🔎", bg=NC_BG, fg=NC_FG, font=FONT_UI).pack(side="left")
        self.search_var = tk.StringVar()
        self.search_entry = tk.Entry(srow, textvariable=self.search_var, bg=NC_ENTRY_BG, fg=NC_ENTRY_FG,
                                     insertbackground=NC_FG, font=FONT_UI)
        self.search_entry.pack(side="left", fill="x", expand=True, padx=4)
        _x = self._btn(srow, "✖", lambda: self.search_var.set(""))
        _x.pack(side="left")
        Tooltip(_x, "Effacer la recherche")
        self.search_var.trace_add("write", lambda *_: self._schedule_filter())
        Tooltip(self.search_entry, "Cherche dans titre, texte, auteur, tags et notes (Ctrl+F)")
        frow = FlowFrame(left)
        frow.pack(fill="x", pady=3)
        self.plat_var = tk.StringVar(value=PLAT_ALL_LABEL)
        self.plat_cb = ttk.Combobox(frow, textvariable=self.plat_var, values=[PLAT_ALL_LABEL], width=19,
                                    state="readonly", font=FONT_SM)
        self.plat_cb.bind("<<ComboboxSelected>>", lambda e: self.apply_filter())
        frow.add(self.plat_cb, "Filtrer l'historique par plateforme")
        self.coll_var = tk.StringVar(value=COLL_ALL_LABEL)
        self._coll_map: Dict[str, str] = {COLL_ALL_LABEL: ""}
        self.coll_cb = ttk.Combobox(frow, textvariable=self.coll_var, values=[COLL_ALL_LABEL], width=21,
                                    state="readonly", font=FONT_SM)
        self.coll_cb.bind("<<ComboboxSelected>>", lambda e: self._on_coll_filter())
        frow.add(self.coll_cb, "Collections : ★ favoris, 🗣 avec transcription, ⚠ originaux plus en ligne,\n"
                               "ou une de tes collections (clic droit sur une archive → 📚 Collections)")
        self.sort_var = tk.StringVar(value=LABEL_BY_SORT.get(self.cfg.get("sort"), SORT_CHOICES[0][1]))
        scb = ttk.Combobox(frow, textvariable=self.sort_var, values=[lab for _k, lab in SORT_CHOICES],
                           width=15, state="readonly", font=FONT_SM)
        scb.bind("<<ComboboxSelected>>", lambda e: (self._persist_opts(), self.apply_filter()))
        frow.add(scb, "Ordre de l'historique (clic sur un en-tête de colonne aussi)")

        tfr = tk.Frame(left, bg=NC_BG)
        self._hist_tfr = tfr
        self.tree = ttk.Treeview(tfr, style="Arch.Treeview", columns=("date", "plat", "titre", "taille"),
                                 show="tree headings", selectmode="extended")
        vsb = ttk.Scrollbar(tfr, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.heading("#0", text="")
        self.tree.column("#0", width=96, minwidth=96, stretch=False)
        for col, txt, w, st in (("date", "Archivé", 120, False), ("plat", "Plateforme", 110, False),
                                ("titre", "Titre", 200, True), ("taille", "Taille", 72, False)):
            self.tree.heading(col, text=txt, command=lambda c=col: self._sort_by_heading(c))
            self.tree.column(col, width=w, minwidth=50, stretch=st, anchor="e" if col == "taille" else "w")
        self.tree.bind("<Configure>", self._tree_columns, add="+")
        self.tree.bind("<<TreeviewSelect>>", self._on_select_history)
        self.tree.bind("<Double-Button-1>", lambda e: self.play_selected())
        self.tree.bind("<Button-3>", self._show_hist_menu)
        self.tree.bind("<Return>", lambda e: self.play_selected())
        self.tree.bind("<Delete>", lambda e: self.delete_selected())
        self.tree.bind("<Control-a>", self._tree_select_all)
        self.tree.bind("<Control-A>", self._tree_select_all)
        self.tree.bind("<Motion>", self._tree_hover, add="+")
        self.tree.bind("<space>", lambda e: (self.player_toggle(), "break")[1])

        self._hist_menu = self._menu()  # rempli à l'ouverture (selon la sélection)

        btns = FlowFrame(left)
        btns.pack(fill="x", pady=(2, 4), side="bottom")
        self._hist_btns = []
        tfr.pack(fill="both", expand=True, pady=2)
        for txt, cmd, tip, needs in (
            ("📁 Dossier", self.open_last_or_selected_folder, "Ouvrir le dossier de l'archive", False),
            ("🗑 Supprimer", self.delete_selected, "Supprimer l'archive — ou toutes celles sélectionnées (confirmation)", True),
            ("🔄", self.refresh_list, "Rafraîchir : relire le dossier des archives (F5)", False),
        ):
            b = btns.add(self._btn(btns, txt, cmd), tip)
            if needs:
                self._hist_btns.append(b)

    # ------------------------------------------------------------ aperçu
    def _build_preview(self, right):
        prev = tk.LabelFrame(right, text=" APERÇU ", bg=NC_BG, fg=NC_HI, font=FONT_UI, bd=2, relief="groove")
        prev.pack(fill="both", expand=True, padx=(6, 0))
        # en-tête fixe : titre éditable + barre d'actions
        name_row = tk.Frame(prev, bg=NC_BG)
        name_row.pack(fill="x", padx=6, pady=(4, 2))
        self.name_var = tk.StringVar()
        self.name_entry = tk.Entry(name_row, textvariable=self.name_var, bg=NC_ENTRY_BG, fg=NC_HI,
                                   insertbackground=NC_FG, font=FONT_BIG, relief="flat")
        _rb = self._btn(name_row, "✏ Renommer", self.rename_selected)
        _rb.pack(side="right", fill="y")
        self._act_btns_extra = [_rb]
        Tooltip(_rb, "Renommer l'archive (dossier + titre) avec le nom écrit à gauche — Entrée ou F2")
        self.name_entry.pack(side="left", fill="x", expand=True, padx=(0, 4), ipady=3)
        self.name_entry.bind("<Return>", lambda e: self.rename_selected())
        self.name_entry.bind("<F2>", lambda e: (self.rename_selected(), "break")[1])
        Tooltip(self.name_entry, "Nom de l'archive — modifie-le puis Entrée / F2 / ✏ Renommer")
        act = FlowFrame(prev)
        act.pack(fill="x", padx=6, pady=(0, 4))
        self._act_btns: Dict[str, Any] = {}
        for key, txt, cmd, hi, tip in (
            ("play", "▶ Lire", self.play_selected, True,
             "Lire ici, dans l'aperçu (lecteur intégré) — Ctrl+Espace = lecture/pause.\n"
             "Désactivable dans ⚙ Réglages : ▶ ouvre alors le lecteur externe."),
            ("ext", "↗ Externe", self.open_selected_media, False, "Ouvrir le média dans le lecteur externe (Windows, VLC ou mpv)"),
            ("fav", "☆ Favori", self.toggle_favorite, False, "Ajouter aux favoris / retirer (Ctrl+D)"),
            ("coll", "📚 Collections ▾", lambda: self._post_menu(self._act_btns["coll"], self._build_coll_menu()), False,
             "Classer l'archive dans une ou plusieurs collections"),
            ("orig", "🌐 Original", self.open_original, False, "Ouvrir la page d'origine dans le navigateur"),
            ("page", "📄 Page", self.open_selected_index, False, "Page archive locale (index.html) dans le navigateur"),
            ("folder", "📁 Dossier", self.open_selected_folder, False, "Ouvrir le dossier de l'archive"),
            ("grim", "📚 Envoyer au Grimoire", self.send_to_grimoire, False,
             "Crée une fiche dans le Grimoire (choix du sujet) : titre, texte, image, lien et copie locale ✔ Permanent"),
            ("media", "✂ Outils média", self.open_media_tools, False,
             "Capture d'image, extrait vidéo, audio MP3, GIF animé (dossier extraits/)"),
            ("more", "⋯ Plus ▾", lambda: self._post_menu(self._act_btns["more"], self._build_more_menu()), False,
             "Copier le lien / le résumé, vérifier en ligne, exporter en ZIP, convertir en MP4, transcrire…"),
        ):
            self._act_btns[key] = act.add(self._btn(act, txt, cmd, hi=hi), tip)
        self._act_flow = act

        # bandeau « Ranger dans X ? » (suggestion, rien n'est forcé)
        self.sug_banner = tk.Frame(prev, bg=NC_CARD, highlightbackground=NC_HI, highlightthickness=1)
        self.sug_msg = tk.Label(self.sug_banner, text="", bg=NC_CARD, fg=NC_TEXT, font=FONT_UI,
                                anchor="w", justify="left")
        self.sug_msg.pack(side="left", fill="x", expand=True, padx=8, pady=4)
        _sb = tk.Frame(self.sug_banner, bg=NC_CARD)
        _sb.pack(side="right", padx=4, pady=3)
        self._btn(_sb, "✔ Oui", self._sug_accept, hi=True, font=FONT_UI).pack(side="left", padx=2)
        self._sug_other = self._btn(_sb, "Autre…", lambda: self._post_menu(self._sug_other, self._build_move_menu()))
        self._sug_other.pack(side="left", padx=2)
        Tooltip(self._sug_other, "Choisir une autre collection (ou en créer une)")
        _no = self._btn(_sb, "✖", self._sug_dismiss)
        _no.pack(side="left", padx=2)
        Tooltip(_no, "Non merci : ne plus proposer pour cette archive")

        self.pscroll = ScrollFrame(prev)
        self.pscroll.pack(fill="both", expand=True, padx=2, pady=2)
        body = self.pscroll.inner

        # bandeau codec (vidéo non lisible par le lecteur Windows)
        self.codec_banner = tk.Frame(body, bg=NC_HI)
        self.codec_msg = tk.Label(self.codec_banner, text="", bg=NC_HI, fg=NC_ON_HI, font=FONT_SM,
                                  anchor="w", justify="left")
        self.codec_msg.pack(side="left", fill="x", expand=True, padx=6, pady=3)
        self._btn(self.codec_banner, "🎬 Convertir en MP4 compatible", self.convert_selected).pack(
            side="right", padx=4, pady=2)
        self._codec_anchor = tk.Frame(body, bg=NC_BG, height=0)
        self._codec_anchor.pack(fill="x")

        # grande miniature (sert aussi d'écran au lecteur intégré)
        self.thumb_label = tk.Label(body, bg=NC_IMG_BG, fg=NC_DIM, font=FONT_UI, cursor="hand2",
                                    text="Aucune archive sélectionnée.\nColle un lien pour commencer.",
                                    height=12)
        self.thumb_label.pack(fill="x", padx=8, pady=(6, 0))
        self.thumb_label.bind("<Button-1>", lambda e: self._on_thumb_click())
        self.thumb_label.bind("<Double-Button-1>", lambda e: self.player_bigwin())
        self._build_player_bar(body)
        self.thumb_hint = tk.Label(body, text="", bg=NC_BG, fg=NC_DIM, font=FONT_SM)
        self.thumb_hint.pack(fill="x", padx=8)
        # documents d'une page web archivée
        self._doc_anchor = tk.Frame(body, bg=NC_BG, height=0)
        self._doc_anchor.pack(fill="x")
        self.doc_box = tk.Frame(body, bg=NC_BG)
        self.doc_flow = FlowFrame(self.doc_box)
        self.doc_flow.pack(fill="x", padx=8, pady=(6, 0))

        # storyboard
        self._sb_anchor = tk.Frame(body, bg=NC_BG, height=0)
        self._sb_anchor.pack(fill="x")
        self.sb_title = self._section(body, "🎞 Storyboard")
        self.sb_row = tk.Frame(body, bg=NC_BG)
        self.sb_row.pack(fill="x", padx=8)
        self.sb_msg = tk.Label(body, text="", bg=NC_BG, fg=NC_DIM, font=FONT_SM, anchor="w")
        self.sb_msg.pack(fill="x", padx=8)

        # carte d'infos
        self._section(body, "ℹ Informations")
        self.card = tk.Frame(body, bg=NC_CARD, bd=1, relief="solid", highlightbackground=NC_FG)
        self.card.pack(fill="x", padx=8, pady=2)
        self.card.columnconfigure(1, weight=1)
        self._card_vals: Dict[str, tk.Label] = {}
        self._card_targets: Dict[str, Tuple[str, str]] = {}
        rows = [
            ("platform", "Plateforme"), ("author", "👤 Auteur"), ("published", "📅 Publié"),
            ("archived", "🗄 Archivé"), ("duration", "⏱ Durée"), ("size", "💾 Taille"),
            ("resolution", "🎞 Résolution"), ("method", "⚙ Méthode"), ("url", "🔗 Original"),
            ("folder", "📁 Dossier"), ("main", "▶ Média"), ("online", "📡 En ligne"),
            ("collections", "📚 Collections"),
        ]
        for i, (key, lab) in enumerate(rows):
            tk.Label(self.card, text=lab, bg=NC_CARD, fg=NC_FG, font=FONT_CARD_K, anchor="nw").grid(
                row=i, column=0, sticky="nw", padx=(8, 10), pady=2)
            v = tk.Label(self.card, text="—", bg=NC_CARD, fg=NC_TEXT, font=FONT_CARD_V,
                         anchor="w", justify="left")
            v.grid(row=i, column=1, sticky="w", padx=(0, 8), pady=2)
            v.bind("<Button-1>", lambda e, k=key: self._card_click(k))
            v.bind("<Button-3>", lambda e, k=key: self._card_menu(e, k))
            self._card_vals[key] = v

        # tags + notes
        self._section(body, "🏷 Tags et notes perso")
        trow = tk.Frame(body, bg=NC_BG)
        trow.pack(fill="x", padx=8)
        tk.Label(trow, text="Tags (virgules):", bg=NC_BG, fg=NC_FG, font=FONT_SM).pack(side="left")
        self.tags_var = tk.StringVar()
        self.tags_entry = tk.Entry(trow, textvariable=self.tags_var, bg=NC_ENTRY_BG, fg=NC_HI,
                                   insertbackground=NC_FG, font=FONT_UI)
        self.tags_entry.pack(side="left", fill="x", expand=True, padx=4)
        self.tags_entry.bind("<Return>", lambda e: self.save_tags_notes())
        self.tag_chips = tk.Frame(body, bg=NC_BG)
        self.tag_chips.pack(fill="x", padx=8, pady=(2, 0))
        tk.Label(body, text="Notes:", bg=NC_BG, fg=NC_FG, font=FONT_SM, anchor="w").pack(fill="x", padx=8)
        nfr, self.notes_text = self._scrolled_text(body, height=4, bg=NC_ENTRY_BG, fg=NC_ENTRY_FG,
                                                   font=FONT_TEXT)
        nfr.pack(fill="x", padx=8)
        srow = tk.Frame(body, bg=NC_BG)
        srow.pack(fill="x", padx=8, pady=3)
        self._btn(srow, "💾 Enregistrer tags/notes (Ctrl+S)", self.save_tags_notes, hi=True).pack(side="left")
        self.tn_state = tk.Label(srow, text="", bg=NC_BG, fg=NC_OK, font=FONT_SM)
        self.tn_state.pack(side="left", padx=8)

        # texte du post
        self.text_title = self._section(body, "📝 Texte du post")
        tfr, self.desc_text = self._scrolled_text(body, height=12, bg=NC_PANEL, fg=NC_TEXT, font=FONT_TEXT)
        tfr.pack(fill="x", padx=8)
        self.desc_text.configure(state="disabled", cursor="xterm", padx=8, pady=6, spacing1=1, spacing3=3)
        self.desc_text.tag_configure("link", foreground=NC_HI, underline=True)
        self.desc_text.tag_bind("link", "<Enter>", lambda e: self.desc_text.configure(cursor="hand2"))
        self.desc_text.tag_bind("link", "<Leave>", lambda e: self.desc_text.configure(cursor="xterm"))
        self.desc_text.bind("<Button-1>", lambda e: self.desc_text.focus_set())
        self.desc_text.bind("<Button-3>", self._desc_menu_popup)
        self._desc_menu = self._menu()
        self._desc_menu.add_command(label="Copier la sélection", command=self._desc_copy_sel)
        self._desc_menu.add_command(label="Copier tout le texte", command=self._desc_copy_all)
        self._desc_menu.add_command(label="Tout sélectionner", command=lambda: self.desc_text.tag_add("sel", "1.0", "end-1c"))

        # transcription (v5)
        self._tr_anchor = tk.Frame(body, bg=NC_BG, height=0)
        self._tr_anchor.pack(fill="x")
        self._build_transcript_box(body)
        # extraits et captures (v5)
        self._ex_anchor = tk.Frame(body, bg=NC_BG, height=0)
        self._ex_anchor.pack(fill="x")
        self._build_extracts_box(body)

        # galerie
        self.gal_title = self._section(body, "🖼 Galerie")
        self.gal_frame = tk.Frame(body, bg=NC_BG)
        self.gal_frame.pack(fill="x", padx=8)
        self._gal_paths: List[str] = []

        # fichiers
        self.files_title = self._section(body, "📂 Fichiers")
        ffr = tk.Frame(body, bg=NC_BG)
        ffr.pack(fill="x", padx=8, pady=(0, 12))
        self.files_tree = ttk.Treeview(ffr, style="Files.Treeview", columns=("kind", "size", "mod"),
                                       show="tree headings", height=8, selectmode="browse")
        fsb = ttk.Scrollbar(ffr, orient="vertical", command=self.files_tree.yview)
        self.files_tree.configure(yscrollcommand=fsb.set)
        fsb.pack(side="right", fill="y")
        self.files_tree.pack(side="left", fill="x", expand=True)
        self.files_tree.heading("#0", text="Nom")
        self.files_tree.column("#0", width=380, stretch=True)
        for col, txt, w in (("kind", "Type", 100), ("size", "Taille", 90), ("mod", "Modifié", 130)):
            self.files_tree.heading(col, text=txt)
            self.files_tree.column(col, width=w, stretch=False, anchor="e" if col == "size" else "w")
        self.files_tree.bind("<Double-Button-1>", lambda e: self.open_preview_file())
        self.files_tree.bind("<Return>", lambda e: self.open_preview_file())
        self.files_tree.bind("<Button-3>", self._files_menu_popup)
        self._files_menu = self._menu()
        self._files_menu.add_command(label="Ouvrir", command=self.open_preview_file)
        self._files_menu.add_command(label="Afficher dans le dossier", command=self.reveal_preview_file)
        self._files_menu.add_command(label="Copier le chemin", command=self.copy_preview_file_path)
        self._files_menu.add_command(label="Copier le nom", command=self.copy_preview_file_name)

        self.pscroll.canvas.bind("<Configure>", self._on_preview_resize, add="+")

    # ------------------------------------------------------------ bas: file + journal
    def _build_bottom(self, bottom):
        """Barre compacte (toujours visible) + panneau File/Journal repliable."""
        hdr = tk.Frame(bottom, bg=NC_PANEL)
        hdr.pack(fill="x")
        self.q_toggle = self._btn(hdr, "▲ ⏳ File d'attente", lambda: self._toggle_bottom("queue"))
        self.q_toggle.pack(side="left", padx=(2, 2), pady=2)
        Tooltip(self.q_toggle, "Afficher / replier la file d'attente (Échap = replier)")
        self.l_toggle = self._btn(hdr, "📜 Journal", lambda: self._toggle_bottom("log"))
        self.l_toggle.pack(side="left", padx=2, pady=2)
        Tooltip(self.l_toggle, "Afficher / replier le journal détaillé")
        self.cancel_btn = self._btn(hdr, "⛔ Annuler", self.cancel_current)
        self.cancel_btn.pack(side="right", padx=4, pady=2)
        Tooltip(self.cancel_btn, "Annuler l'archivage / la conversion en cours")
        self.prog = FunBar(hdr, width=170, height=16)
        self.prog.pack(side="left", padx=(10, 6), pady=4)
        self.prog_var = tk.StringVar(value="Aucun archivage en cours.")
        tk.Label(hdr, textvariable=self.prog_var, bg=NC_PANEL, fg=NC_FG, font=FONT_SM, anchor="w").pack(
            side="left", fill="x", expand=True)

        self.bottom_body = tk.Frame(bottom, bg=NC_BG, height=170)
        self.bottom_body.pack_propagate(False)
        # file d'attente
        self.qframe = tk.Frame(self.bottom_body, bg=NC_BG)
        side = tk.Frame(self.qframe, bg=NC_BG)
        side.pack(side="right", fill="y", padx=(6, 2), pady=2)
        self.q_retire = self._btn(side, "✖ Retirer", self.remove_selected_job)
        self.q_retire.pack(fill="x", pady=1)
        Tooltip(self.q_retire, "Retirer le lien sélectionné de la file (Suppr)")
        self.q_retry = self._btn(side, "🔁 Réessayer", self.retry_selected_job)
        self.q_retry.pack(fill="x", pady=1)
        Tooltip(self.q_retry, "Relancer un lien en échec ou annulé")
        self.q_clear = self._btn(side, "🧹 Nettoyer terminés", self.clear_done_jobs)
        self.q_clear.pack(fill="x", pady=1)
        Tooltip(self.q_clear, "Enlever de la liste les liens terminés / en échec / annulés")
        qfr = tk.Frame(self.qframe, bg=NC_BG)
        qfr.pack(side="left", fill="both", expand=True, pady=2)
        self.qtree = ttk.Treeview(qfr, style="Queue.Treeview", columns=("etat", "pct", "titre"),
                                  show="headings", height=4, selectmode="browse")
        qsb = ttk.Scrollbar(qfr, orient="vertical", command=self.qtree.yview)
        self.qtree.configure(yscrollcommand=qsb.set)
        qsb.pack(side="right", fill="y")
        self.qtree.pack(side="left", fill="both", expand=True)
        for col, txt, w, st in (("etat", "État", 110, False), ("pct", "%", 50, False), ("titre", "Lien / titre", 500, True)):
            self.qtree.heading(col, text=txt)
            self.qtree.column(col, width=w, stretch=st, anchor="e" if col == "pct" else "w")
        self.qtree.bind("<Double-Button-1>", self._on_job_double)
        self.qtree.bind("<Delete>", lambda e: self.remove_selected_job())
        self.qtree.bind("<<TreeviewSelect>>", lambda e: self._update_states(), add="+")
        self.q_empty = tk.Label(qfr, text="File vide — colle un lien pour commencer.", bg=NC_PANEL,
                                fg=NC_DIM, font=FONT_SM)
        # journal
        self.lframe = tk.Frame(self.bottom_body, bg=NC_BG)
        lfr, self.log_box = self._scrolled_text(self.lframe, height=6, font=FONT_SM)
        lfr.pack(fill="both", expand=True, pady=2)

    def _toggle_bottom(self, view: str):
        if self._bottom_open and self._bottom_view == view:
            self._collapse_bottom()
        else:
            self._show_bottom(view)

    def _show_bottom(self, view: str, auto: bool = False):
        self._bottom_auto = auto and not self._bottom_open
        self._bottom_view = view
        (self.qframe if view == "queue" else self.lframe).pack(fill="both", expand=True)
        (self.lframe if view == "queue" else self.qframe).pack_forget()
        h = max(120, min(230, int(self.winfo_height() * 0.24))) if self.winfo_height() > 100 else 160
        self.bottom_body.configure(height=h)
        if not self._bottom_open:
            self.bottom_body.pack(fill="x")
            self._bottom_open = True
        if view == "log":
            self.log_box.see("end")
        self._refresh_bottom_labels()

    def _collapse_bottom(self):
        if self._bottom_open:
            self.bottom_body.pack_forget()
            self._bottom_open = False
            self._bottom_auto = False
        self._refresh_bottom_labels()

    def _refresh_bottom_labels(self):
        pending = sum(1 for j in self.jobs if j["status"] == "attente")
        running = any(j["status"] == "cours" for j in self.jobs)
        n = pending + (1 if running else 0)
        q_open = self._bottom_open and self._bottom_view == "queue"
        l_open = self._bottom_open and self._bottom_view == "log"
        self.q_toggle.configure(text=("▼ " if q_open else "▲ ") + "⏳ File d'attente" + (f" ({n})" if n else ""),
                                bg=NC_SEL if q_open else NC_BTN, fg=NC_ON_SEL if q_open else NC_BTN_FG)
        self.l_toggle.configure(text=("▼ " if l_open else "▲ ") + "📜 Journal",
                                bg=NC_SEL if l_open else NC_BTN, fg=NC_ON_SEL if l_open else NC_BTN_FG)
        if self.jobs:
            self.q_empty.place_forget()
        else:
            self.q_empty.place(relx=0.5, rely=0.55, anchor="center")

    # ------------------------------------------------------------ colonnes historique adaptatives
    def _tree_columns(self, event=None):
        w = event.width if event is not None else self.tree.winfo_width()
        if w <= 1:
            return
        if w >= 640:
            disp = ("date", "plat", "titre", "taille")
        elif w >= 470:
            disp = ("date", "titre", "taille")
        else:
            disp = ("titre", "taille")
        if tuple(self.tree.cget("displaycolumns")) != disp and self.tree.cget("displaycolumns") != disp:
            self.tree.configure(displaycolumns=disp)
        fixed = 96 + 72 + (120 if "date" in disp else 0) + (110 if "plat" in disp else 0) + 4
        self.tree.column("titre", width=max(120, w - fixed))

    # ------------------------------------------------------------ états des boutons
    def _update_states(self):
        try:
            has = bool(self._preview_entry and self._preview_path and os.path.isdir(self._preview_path))
            main = find_main_media(self._preview_path) if has else None
            is_vid = bool(main and main.lower().endswith(VIDEO_EXTS))
            can_play = bool(main) or bool(has and list_images(self._preview_path))
            for key, b in self._act_btns.items():
                ok = has
                if key == "play":
                    ok = can_play
                elif key == "ext":
                    ok = bool(main)
                elif key in ("orig", "copy"):
                    ok = has and bool(self._entry_url())
                elif key == "conv":
                    ok = is_vid and bool(find_ffmpeg())
                elif key == "media":
                    ok = bool(main) and bool(find_ffmpeg())
                b.configure(state="normal" if ok else "disabled")
            self._update_fav_button()
            nsel = len(self.tree.selection())
            for b in getattr(self, "_hist_btns", []):
                b.configure(state="normal" if (has or nsel) else "disabled")
            running = any(j["status"] == "cours" for j in self.jobs)
            self.cancel_btn.configure(state="normal" if running else "disabled")
            j = self._selected_job()
            self.q_retire.configure(state="normal" if j else "disabled")
            self.q_retry.configure(state="normal" if j and j["status"] in ("echec", "annule") else "disabled")
            self.q_clear.configure(state="normal" if any(x["status"] in ("ok", "echec", "annule")
                                                        for x in self.jobs) else "disabled")
        except Exception:
            logger.exception("update_states")

    # ------------------------------------------------------------ molette
    def _on_wheel(self, event):
        try:
            w = self.winfo_containing(event.x_root, event.y_root)
        except Exception:
            w = None
        if w is None:
            return
        if getattr(event, "state", 0) & 0x4:  # Ctrl + molette = taille du texte
            up = getattr(event, "num", None) == 4 or int(getattr(event, "delta", 0) or 0) > 0
            self._font_step(1 if up else -1)
            return "break"
        if getattr(event, "num", None) == 4:
            step = -3
        elif getattr(event, "num", None) == 5:
            step = 3
        else:
            d = int(getattr(event, "delta", 0) or 0)
            if d == 0:
                return
            step = -max(1, abs(d) // 40) if d > 0 else max(1, abs(d) // 40)
        try:
            cls = w.winfo_class()
        except Exception:
            return
        if cls in ("Text", "Treeview", "Listbox", "TCombobox", "Canvas") and w is not self.pscroll.canvas:
            try:
                first, last = w.yview()
                can_scroll = not (first <= 0.0 and last >= 1.0)
            except Exception:
                can_scroll = True
            if can_scroll:
                return  # la classe du widget gère sa propre molette
        if self.pscroll.contains(w):
            self.pscroll.scroll_units(step)
            return "break"

    # ------------------------------------------------------------ démarrage
    def _post_init(self):
        try:
            os.makedirs(self.archive_root_path(), exist_ok=True)
        except Exception as e:
            self.log(f"Racine inaccessible: {e}")
        self.log(f"Archiveur v{APP_FILE_VER} — racine: {self.archive_root_path()}")
        ff = find_ffmpeg()
        self.log(f"ffmpeg: {ff if ff else 'non trouvé'}")
        if not self._smoke:
            ensure_ytdlp(self.log, ask_install=bool(self.cfg.get("ask_ytdlp_install", True)), parent=self)

        def _ff_job():
            ok = ensure_ffmpeg(self.log, ask_install=False, parent=None,
                               status_cb=lambda m: self.ui(lambda mm=m: self.status.set(mm[:140])))
            self.cfg["ask_ffmpeg_install"] = False
            save_cfg(self.cfg)
            if not ok:
                self.log("ffmpeg manquant après tentative d'installation.")

        if not ff and not self._smoke:
            threading.Thread(target=_ff_job, daemon=True).start()
        if not find_ffplay():
            self.log("ffplay introuvable : lecteur intégré sans le son (relance setup_padawan.bat).", "warning")
        self._setup_dnd()
        self.refresh_list()
        if self._visible:
            self.select_folder(self._visible[0].get("folder"))
        else:
            self.clear_preview()
        if self.clip_var.get():
            self._toggle_clip_watch()
        self._refresh_bottom_labels()
        self._update_states()
        if self._players:
            self.log("Lecteurs détectés : " + ", ".join(f"{PLAYER_LABELS[k]} ({v})" for k, v in self._players.items()))
        self.after(200, lambda: self.url_text.focus_set())
        if self._shot:
            if self._shot_action:
                self.after(1500, self._do_shot_action)
            self.after(5000 if self._shot_action else 3500, self._take_shot)
        elif self._smoke:
            self.after(400, self._smoke_run)

    def _take_shot(self):
        """Mode test : capture de la fenêtre (PIL ImageGrab) → --shot fichier.png puis ferme."""
        try:
            self.update()
            from PIL import ImageGrab  # type: ignore
            full = ImageGrab.grab()
            sc = full.width / float(self.winfo_screenwidth())
            x0, y0 = self.winfo_rootx(), self.winfo_rooty()
            x1, y1 = x0 + self.winfo_width(), y0 + self.winfo_height()
            img = full.crop((int(x0 * sc), int(y0 * sc), int(x1 * sc), int(y1 * sc)))
            img.save(self._shot)
            print(f"SHOT {self._shot} {img.width}x{img.height} win={self.winfo_width()}x{self.winfo_height()} "
                  f"scale={sc:.2f} errors={len(self._errors)}", flush=True)
            for er in self._errors:
                print("SHOT_ERROR", er, flush=True)
        except Exception as ex:
            print("SHOT_FAIL", ex, flush=True)
            self._errors.append(str(ex))
        self._smoke_code = 1 if self._errors else 0
        self.destroy()

    def log(self, msg: str, level: str = "info"):
        line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
        try:
            getattr(logger, level if level in ("info", "warning", "error") else "info")(msg)
        except Exception:
            pass

        def _ui():
            try:
                self.log_box.insert("end", line + "\n")
                if int(self.log_box.index("end-1c").split(".")[0]) > 3000:
                    self.log_box.delete("1.0", "500.0")
                self.log_box.see("end")
                self.status.set(msg[:160])
            except Exception:
                pass
        self.ui(_ui)
        try:
            print(line, flush=True)
        except Exception:
            try:
                print(line.encode("ascii", "replace").decode("ascii"), flush=True)
            except Exception:
                pass

    def _persist_opts(self):
        self.cfg["quality"] = QUALITY_BY_LABEL.get(self.quality_var.get(), "best")
        self.cfg["subtitles"] = bool(self.subs_var.get())
        self.cfg["storyboard"] = bool(self.sb_var.get())
        self.cfg["cookies_from_browser"] = bool(self.cookies_var.get())
        self.cfg["cookies_browser"] = self.browser_var.get() or "chrome"
        self.cfg["clipboard_watch"] = bool(self.clip_var.get())
        self.cfg["clipboard_auto"] = bool(self.clip_auto_var.get())
        self.cfg["notifications"] = bool(self.notif_var.get())
        self.cfg["sort"] = SORT_BY_LABEL.get(self.sort_var.get(), "date_desc")
        self.cfg["auto_convert"] = bool(self.conv_var.get())
        inv = {v: k for k, v in PLAYER_LABELS.items()}
        self.cfg["player"] = inv.get(self.player_var.get(), "windows")
        self.cfg["archive_root"] = self.root_var.get().strip() or DEFAULT_ROOT
        self.archive_root = self.cfg["archive_root"]
        save_cfg(self.cfg)

    def _job_opts(self) -> Dict[str, Any]:
        self._persist_opts()
        return {
            "root": self.archive_root_path(),
            "quality": self.cfg["quality"],
            "subtitles": self.cfg["subtitles"],
            "storyboard": self.cfg["storyboard"],
            "cookies": (self.cfg["cookies_browser"] if self.cfg["cookies_from_browser"] else None),
            "auto_convert": bool(self.cfg.get("auto_convert", True)),
            "web_capture": bool(self.cfg.get("web_capture", True)),
            "use_fx": bool(self.cfg.get("x_fxtwitter", True)),
        }

    def choose_root(self):
        d = filedialog.askdirectory(initialdir=self.archive_root, title="Racine des archives", parent=self)
        if d:
            self.root_var.set(os.path.normpath(d))
            self._persist_opts()
            self.refresh_list()

    def archive_root_path(self) -> str:
        return self.root_var.get().strip() or self.archive_root

    def open_root(self):
        path = self.archive_root_path()
        os.makedirs(path, exist_ok=True)
        self.open_path_safe(path, "dossier")

    def open_global_index(self):
        root = self.archive_root_path()
        path = os.path.join(root, INDEX_HTML)
        if not os.path.isfile(path):
            write_global_index_html(root, load_archive_index(root))
        self._open_url(path)

    def regenerate_index(self):
        root = self.archive_root_path()
        try:
            entries = sync_index_with_disk(root, self.log)
            n = 0
            for e in entries:
                fp = os.path.join(root, str(e.get("folder")))
                info = load_info(fp)
                if info:
                    write_local_index(fp, info)
                    fresh = entry_from_info(info, fp)
                    e["size"], e["thumb"] = fresh["size"], fresh["thumb"]
                    n += 1
            save_archive_index(root, entries)
            self.log(f"♻ Index régénéré ({n} archive(s), pages locales + index global).")
            self.refresh_list()
        except Exception as ex:
            logger.exception("regenerate_index")
            messagebox.showerror(APP_NAME, f"Régénération impossible:\n{friendly_error(ex)}", parent=self)

    # ------------------------------------------------------------ liste
    def refresh_list(self):
        root = self.archive_root_path()
        try:
            self.entries = sync_index_with_disk(root, self.log)
        except Exception as e:
            logger.exception("refresh_list")
            self.log(f"Lecture de l'index impossible: {friendly_error(e)}", "error")
            self.entries = load_archive_index(root)
        self._refresh_filter_values()
        self.apply_filter()
        if self._preview_entry:
            self._refresh_preview_meta()

    def _schedule_filter(self):
        if getattr(self, "_filter_job", None):
            try:
                self.after_cancel(self._filter_job)
            except Exception:
                pass
        self._filter_job = self.after(150, self.apply_filter)

    def _sort_by_heading(self, col):
        cur = SORT_BY_LABEL.get(self.sort_var.get(), "date_desc")
        base = {"date": "date", "titre": "name", "taille": "size", "plat": "name"}.get(col, "date")
        if cur.startswith(base):
            new = base + ("_asc" if cur.endswith("desc") else "_desc")
        else:
            new = base + ("_desc" if base in ("date", "size") else "_asc")
        self.sort_var.set(LABEL_BY_SORT[new])
        self._persist_opts()
        self.apply_filter()

    def _list_thumb(self, entry):
        if not HAS_PIL:
            return ""
        thumb = entry.get("thumb")
        if not thumb:
            return ""
        p = os.path.join(self.archive_root_path(), str(entry.get("folder")), str(thumb))
        try:
            key = (p, os.path.getmtime(p))
        except OSError:
            return ""
        if key in self._list_thumbs:
            return self._list_thumbs[key]
        try:
            im = Image.open(p)
            im.thumbnail((84, 47))
            bg = Image.new("RGB", (84, 47), NC_IMG_BG)
            bg.paste(im.convert("RGB"), ((84 - im.width) // 2, (47 - im.height) // 2))
            ph = ImageTk.PhotoImage(bg)
        except Exception:
            logger.exception("vignette %s", p)
            ph = ""
        self._list_thumbs[key] = ph
        return ph

    def apply_filter(self):
        self._filter_job = None
        plat = getattr(self, "_plat_map", {}).get(self.plat_var.get(), "")
        sort = SORT_BY_LABEL.get(self.sort_var.get(), "date_desc")
        coll = self._coll_key()
        self._visible = search_entries(self.entries, self.search_var.get(), plat, sort, collection=coll)
        keep = self._preview_entry.get("folder") if self._preview_entry else None
        keep_sel = {self._iid_entry[i].get("folder") for i in self.tree.selection() if i in self._iid_entry}
        if keep:
            keep_sel.add(keep)
        self.tree.delete(*self.tree.get_children())
        self._iid_entry = {}
        sel_iids = []
        focus_iid = None
        for i, e in enumerate(self._visible):
            iid = f"e{i}"
            self._iid_entry[iid] = e
            title = str(e.get("title") or e.get("folder") or "")
            pre = ""
            if e.get("favorite"):
                pre += "★ "
            st = e.get("online_status")
            if st in ("offline", "restricted"):
                pre += GUI_ONLINE[st][0] + " "
            title = pre + title
            cols = [c for c in (e.get("collections") or []) if c.lower() != str(coll or "").lower()]
            if cols:
                title += "   📚 " + ", ".join(cols[:2])
            if e.get("tags"):
                title += "   " + " ".join("#" + t for t in e.get("tags")[:4])
            self.tree.insert("", "end", iid=iid, image=self._list_thumb(e), values=(
                fmt_iso(e.get("archived_at")), platform_label(e.get("platform")), title, human_size(e.get("size"))))
            if e.get("folder") in keep_sel:
                sel_iids.append(iid)
            if keep and e.get("folder") == keep:
                focus_iid = iid
        n, tot = len(self._visible), len(self.entries)
        self.count_var.set(f"{n} / {tot} archive(s)" if n != tot else f"{tot} archive(s)")
        if sel_iids:
            self._suppress_select = True
            self.tree.selection_set(sel_iids)
            if focus_iid:
                self.tree.focus(focus_iid)
                self.tree.see(focus_iid)
            self.after(10, lambda: setattr(self, "_suppress_select", False))

    def select_folder(self, folder: Optional[str]) -> bool:
        if not folder:
            return False
        for iid, e in self._iid_entry.items():
            if e.get("folder") == folder:
                self.tree.selection_set(iid)
                self.tree.see(iid)
                self.show_preview(e)
                return True
        # pas visible (filtre) → effacer filtres
        if self.search_var.get() or self._plat_map.get(self.plat_var.get()) or self._coll_key():
            self.search_var.set("")
            self.plat_var.set(PLAT_ALL_LABEL)
            self.coll_var.set(COLL_ALL_LABEL)
            self.apply_filter()
            for iid, e in self._iid_entry.items():
                if e.get("folder") == folder:
                    self.tree.selection_set(iid)
                    self.tree.see(iid)
                    self.show_preview(e)
                    return True
        return False

    def _selected_entry(self) -> Optional[Dict[str, Any]]:
        sel = self.tree.selection()
        if sel and sel[0] in self._iid_entry:
            return self._iid_entry[sel[0]]
        return self._preview_entry

    def _folder_path(self, entry: Optional[Dict[str, Any]] = None) -> Optional[str]:
        e = entry or self._selected_entry()
        if e and e.get("folder"):
            return os.path.join(self.archive_root_path(), str(e.get("folder")))
        if self.last_folder:
            p = os.path.join(self.archive_root_path(), self.last_folder)
            if os.path.isdir(p):
                return p
        return None

    def _on_select_history(self, _evt=None):
        if getattr(self, "_suppress_select", False):
            return
        sel = self.tree.selection()
        if not sel:
            return
        foc = self.tree.focus()
        iid = foc if foc in sel else sel[0]
        if iid in self._iid_entry:
            e = self._iid_entry[iid]
            if not self._preview_entry or e.get("folder") != self._preview_entry.get("folder"):
                self.show_preview(e)
        if len(sel) > 1:
            self.status.set(f"{len(sel)} archives sélectionnées — clic droit pour les actions groupées "
                            "(favoris, collections, tags, ZIP, vérifier en ligne, supprimer).")
            self._update_states()

    # ------------------------------------------------------------ aperçu: rendu
    def clear_preview(self):
        try:
            self.player.stop()
        except Exception:
            pass
        self._player_media = ""
        self.pbar.pack_forget()
        self.doc_box.pack_forget()
        self.tr_box.pack_forget()
        self.ex_box.pack_forget()
        self._sb_show(False)
        self._preview_entry = None
        self._preview_info = {}
        self._preview_path = ""
        self._loaded_tn = ("", "")
        self.name_var.set("")
        self._thumb_src = self._thumb_base = None
        self._thumb_photo = None
        self.thumb_label.configure(image="", height=12,
                                   text="Aucune archive sélectionnée.\nColle un lien (📋 Coller et archiver) pour commencer.")
        self.thumb_hint.configure(text="")
        for w in self.sb_row.winfo_children():
            w.destroy()
        self.sb_msg.configure(text="")
        for k in self._card_vals:
            self._set_card(k, "—")
        self.tags_var.set("")
        self.notes_text.delete("1.0", "end")
        self._render_tag_chips([])
        self._set_desc("")
        for w in self.gal_frame.winfo_children():
            w.destroy()
        self.files_tree.delete(*self.files_tree.get_children())
        self.tn_state.configure(text="")
        self.codec_banner.pack_forget()
        self._hide_suggest_banner()
        self._update_states()

    def _tn_current(self) -> Tuple[str, str]:
        return (", ".join(parse_tags(self.tags_var.get())), self.notes_text.get("1.0", "end-1c").strip())

    def _autosave_tn(self):
        if self._preview_entry and self._preview_path and os.path.isdir(self._preview_path):
            if self._tn_current() != self._loaded_tn:
                try:
                    self.save_tags_notes(quiet=True)
                    self.log("Tags/notes enregistrés automatiquement.")
                except Exception:
                    logger.exception("autosave tags")

    def show_preview(self, entry: Dict[str, Any]):
        if self._preview_entry and entry.get("folder") != self._preview_entry.get("folder"):
            self._autosave_tn()
        try:
            if self.player.state != "stop":
                self.player.stop()
        except Exception:
            logger.exception("arrêt lecteur")
        self._preview_entry = entry
        folder = str(entry.get("folder") or "")
        path = os.path.join(self.archive_root_path(), folder) if folder else ""
        self._preview_path = path
        info: Dict[str, Any] = dict(entry)
        if path:
            info.update(load_info(path))
        self._preview_info = info
        self.name_var.set(str(info.get("title") or folder))
        self.pscroll.to_top()

        # carte
        plat = info.get("platform")
        self._set_card("platform", platform_label(plat))
        author = str(info.get("uploader") or info.get("creator") or info.get("channel") or "")
        aurl = str(info.get("uploader_url") or info.get("channel_url") or "")
        self._set_card("author", author or "—", ("url", aurl) if aurl and author else None)
        self._set_card("published", fmt_upload_date(info.get("upload_date") or info.get("date")))
        self._set_card("archived", fmt_iso(info.get("archived_at")))
        self._set_card("duration", human_duration(info.get("duration")))
        size = folder_size(path) if path and os.path.isdir(path) else 0
        self._set_card("size", human_size(size))
        res = str(info.get("resolution") or "")
        if not res:
            res = "—"
            mm = find_main_media(path) if path else None
            if mm and mm.lower().endswith(VIDEO_EXTS) and find_ffmpeg():
                res = "… (analyse)"
                self._probe_res_async(path, mm)
        self._set_card("resolution", res)
        meth = str(info.get("method") or "—")
        q = info.get("quality")
        if q:
            meth += f" · {LABEL_BY_QUALITY.get(q, q)}"
        self._set_card("method", meth)
        url = str(info.get("webpage_url") or info.get("url") or "")
        self._set_card("url", url or "—", ("url", url) if url else None)
        self._set_card("folder", path or "—", ("path", path) if path and os.path.isdir(path) else None)
        main = find_main_media(path) if path else None
        self._set_card("main", os.path.basename(main) if main else "(aucun média vidéo/audio)",
                       ("path", main) if main else None)
        self._set_card("online", self._online_text(info), ("action", "online"))
        self._set_card("collections", self._collections_text(info), ("action", "collections"))

        # tags / notes
        tags = parse_tags(info.get("tags") or [])
        self.tags_var.set(", ".join(tags))
        self.notes_text.delete("1.0", "end")
        self.notes_text.insert("1.0", str(info.get("notes") or ""))
        self._loaded_tn = self._tn_current()
        self._render_tag_chips(tags, info.get("source_tags") or [])
        self.tn_state.configure(text="")

        # texte
        desc = str(info.get("description") or info.get("text") or "")
        self._set_desc(desc)
        self.text_title.configure(text=f"📝 Texte du post ({len(desc)} car.)" if desc else "📝 Texte du post")

        # miniature
        self._thumb_is_video = bool(main and main.lower().endswith(VIDEO_EXTS))
        thumb = find_thumbnail(path, info) if path else None
        self._load_main_image(thumb)
        if main and self._integrated_ok(main):
            self.thumb_hint.configure(text="Clic sur l'image = ▶ lecture / pause ici · double-clic = grande fenêtre")
        elif main:
            self.thumb_hint.configure(text=f"Clic sur l'image = ▶ lire le média ({PLAYER_LABELS.get(self._player())})")
        elif thumb:
            self.thumb_hint.configure(text="Clic sur l'image = ouvrir l'image")
        else:
            self.thumb_hint.configure(text="")

        self.codec_banner.pack_forget()
        if main and main.lower().endswith(VIDEO_EXTS) and find_ffmpeg():
            self._check_codec_async(path, main)
        self._setup_player(main, info)
        self._render_docs(path, info)
        self._sb_show(bool(main and main.lower().endswith(VIDEO_EXTS)) or bool(list_storyboard(path) if path else []))
        self._render_storyboard()
        self._render_transcript(path, main)
        self._render_extracts(path, main)
        self._render_gallery()
        self._render_files()
        self._update_suggest_banner()
        self._update_states()
        self.after_idle(self._render_thumb)

    def _probe_res_async(self, path: str, video: str):
        def _job():
            res = probe_resolution(video)
            if res:
                try:
                    info = load_info(path)
                    if info and not info.get("resolution"):
                        info["resolution"] = res
                        _write_json_atomic(os.path.join(path, "info.json"), info)
                except Exception:
                    logger.exception("save resolution")

            def _ui():
                if self._preview_path == path:
                    self._preview_info["resolution"] = res
                    self._set_card("resolution", res or "—")
            self.ui(_ui)
        threading.Thread(target=_job, daemon=True).start()

    def _set_card(self, key: str, text: str, target: Optional[Tuple[str, str]] = None):
        lab = self._card_vals[key]
        if target and target[1]:
            self._card_targets[key] = target
            fg = NC_HI
            if key == "online":
                fg = {"●": NC_OK, "✖": NC_ERR, "⚠": NC_WARN}.get(text[:1], NC_HI)
            lab.configure(text=text, fg=fg, cursor="hand2", font=FONT_CARD_VU)
        else:
            self._card_targets.pop(key, None)
            lab.configure(text=text, fg=NC_TEXT, cursor="", font=FONT_CARD_V)

    def _card_click(self, key: str):
        t = self._card_targets.get(key)
        if not t:
            return
        kind, target = t
        if kind == "action":
            if target == "online":
                self.check_online_selected(False)
            elif target == "collections":
                self._post_menu(self._card_vals["collections"], self._build_coll_menu())
            return
        if kind == "url":
            self._open_url(target)
        elif key == "main":
            self.play_selected()
        else:
            self.open_path_safe(target, "élément")

    def _card_menu(self, event, key: str):
        t = self._card_targets.get(key)
        if not t or t[0] == "action":
            return
        self._show_link_menu(event, t[0], t[1])

    def _show_link_menu(self, event, kind: str, target: str):
        self._link_target = (kind, target)
        self._link_menu.entryconfigure(0, label="🌐 Ouvrir le lien" if kind == "url" else "📂 Ouvrir")
        self._link_menu.entryconfigure(1, label="📋 Copier le lien" if kind == "url" else "📋 Copier le chemin")
        try:
            self._link_menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                self._link_menu.grab_release()
            except Exception:
                pass
        return "break"

    def _link_open(self):
        kind, target = self._link_target
        if kind == "url":
            self._open_url(target)
        elif target:
            self.open_path_safe(target, "élément")

    def _link_copy(self):
        self._copy_to_clipboard(self._link_target[1])

    def _copy_to_clipboard(self, text: str):
        if not text:
            return
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            self._clip_last = text  # la surveillance ne le reproposera pas
            self.status.set(f"📋 Copié : {text[:120]}")
        except Exception:
            logger.exception("clipboard")

    def _open_url(self, url: str):
        if not url:
            return
        if url.lower().startswith("www."):
            url = "https://" + url
        try:
            if os.path.exists(url) and sys.platform.startswith("win"):
                os.startfile(url)  # type: ignore[attr-defined]
            else:
                webbrowser.open(url)
            self.status.set(f"🌐 Ouverture : {url[:120]}")
        except Exception as e:
            logger.exception("open url")
            messagebox.showerror(APP_NAME, f"Impossible d'ouvrir le lien:\n{url}\n\n{e}", parent=self)

    def _render_tag_chips(self, tags: List[str], source_tags: Optional[List[str]] = None):
        for w in self.tag_chips.winfo_children():
            w.destroy()
        self.tag_chips.configure(height=1)
        for t in tags:
            lab = tk.Label(self.tag_chips, text=f"#{t}", bg=NC_HI, fg=NC_ON_HI, font=FONT_SM, padx=4, cursor="hand2")
            lab.pack(side="left", padx=(0, 4), pady=1)
            lab.bind("<Button-1>", lambda e, tt=t: self.search_var.set(tt))
        if source_tags:
            sug = [t for t in source_tags[:8] if t.lower() not in {x.lower() for x in tags}]
            if sug:
                tk.Label(self.tag_chips, text="  suggestions:", bg=NC_BG, fg=NC_DIM, font=FONT_SM).pack(side="left")
                for t in sug:
                    lab = tk.Label(self.tag_chips, text=f"+{t}", bg=NC_PANEL, fg=NC_FG, font=FONT_SM,
                                   padx=3, cursor="hand2")
                    lab.pack(side="left", padx=(2, 2))
                    lab.bind("<Button-1>", lambda e, tt=t: self._add_tag(tt))

    def _add_tag(self, tag: str):
        tags = parse_tags(self.tags_var.get()) + [tag]
        self.tags_var.set(", ".join(parse_tags(tags)))
        self.tn_state.configure(text="● modifié — Ctrl+S pour enregistrer", fg=NC_HI)

    def _set_desc(self, desc: str):
        t = self.desc_text
        t.configure(state="normal")
        t.delete("1.0", "end")
        for tag in t.tag_names():
            if tag.startswith("lk_"):
                t.tag_delete(tag)
        if not desc:
            t.insert("1.0", "(aucun texte pour ce post)")
        else:
            pos = 0
            for s, e, u in find_urls_spans(desc):
                t.insert("end", desc[pos:s])
                self._link_seq += 1
                tg = f"lk_{self._link_seq}"
                href = u if not u.lower().startswith("www.") else "https://" + u
                t.insert("end", u, ("link", tg))
                t.tag_bind(tg, "<Button-1>", lambda ev, h=href: (self._open_url(h), "break")[1])
                t.tag_bind(tg, "<Button-3>", lambda ev, h=href: self._show_link_menu(ev, "url", h))
                pos = e
            t.insert("end", desc[pos:])
        t.configure(state="disabled")
        lines = int(t.index("end-1c").split(".")[0])
        t.configure(height=max(4, min(18, lines + 1)))

    def _desc_menu_popup(self, event):
        if "link" in self.desc_text.tag_names(f"@{event.x},{event.y}"):
            return  # le menu du lien prend la main
        try:
            self._desc_menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                self._desc_menu.grab_release()
            except Exception:
                pass
        return "break"

    def _desc_copy_sel(self):
        try:
            self._copy_to_clipboard(self.desc_text.get("sel.first", "sel.last"))
        except tk.TclError:
            pass

    def _desc_copy_all(self):
        self._copy_to_clipboard(self.desc_text.get("1.0", "end-1c"))

    # ------------------------------------------------------------ images
    def _load_main_image(self, path: Optional[str]):
        self._thumb_base = None
        cands = [path] if path else []
        if self._preview_path:
            cands += list_images(self._preview_path) + list_storyboard(self._preview_path)
            cands += list_extracts(self._preview_path)
            adir = os.path.join(self._preview_path, "auteur")
            if os.path.isdir(adir):
                cands += [os.path.join(adir, n) for n in sorted(os.listdir(adir)) if n.lower().endswith(IMAGE_EXTS)]
        for cand in cands:
            if not cand or not HAS_PIL or not os.path.isfile(cand):
                continue
            try:
                im = Image.open(cand)
                im.load()
                self._thumb_base = im.convert("RGB")
                path = cand
                break
            except Exception:
                logger.warning("miniature illisible: %s", cand)
        self._thumb_src = self._thumb_base
        self._thumb_src_path = path
        self._shown_path = None

    def _preview_width(self) -> int:
        w = self.pscroll.canvas.winfo_width()
        return max(200, w - 20)

    def _render_thumb(self):
        if self.player.state in ("play", "pause"):
            return  # l'écran affiche la vidéo
        if self._thumb_src is None:
            self._thumb_photo = None
            if self._preview_entry:
                self.thumb_label.configure(image="", height=8, text="(pas de miniature)\n\nClic = ▶ lire / ouvrir le média")
            return
        avail_w, max_h = self._thumb_box()
        im = self._thumb_src
        scale = min(avail_w / im.width, max_h / im.height, 4.0)
        nw, nh = max(1, int(im.width * scale)), max(1, int(im.height * scale))
        try:
            res = im.resize((nw, nh), Image.LANCZOS).convert("RGBA")
            if self._thumb_is_video:
                ov = Image.new("RGBA", res.size, (0, 0, 0, 0))
                d = ImageDraw.Draw(ov)
                r = max(18, min(nw, nh) // 9)
                cx, cy = nw // 2, nh // 2
                d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(0, 0, 0, 150), outline=(255, 255, 85, 230), width=3)
                t = int(r * 0.55)
                d.polygon([(cx - t // 2, cy - t), (cx - t // 2, cy + t), (cx + t, cy)], fill=(255, 255, 85, 235))
                res = Image.alpha_composite(res, ov)
            self._thumb_photo = ImageTk.PhotoImage(res.convert("RGB"))
            self.thumb_label.configure(image=self._thumb_photo, text="", height=nh)
        except Exception:
            logger.exception("render thumb")

    def _on_preview_resize(self, _e=None):
        if self._resize_job:
            try:
                self.after_cancel(self._resize_job)
            except Exception:
                pass
        self._resize_job = self.after(120, self._do_resize)

    def _do_resize(self):
        self._resize_job = None
        w = self._preview_width()
        if getattr(self, "_last_pw", None) == (w, self.pscroll.canvas.winfo_height()):
            return
        self._last_pw = (w, self.pscroll.canvas.winfo_height())
        if self.player.state == "pause":
            mw, mh = self._thumb_box()
            self.player.show_still(mw, mh, self.player.pos)
        self._render_thumb()
        self._render_storyboard(reuse=True)
        self._layout_gallery()
        try:
            kf = tkfont.nametofont(FONT_CARD_K, root=self)
            keyw = max(kf.measure(t) for t in ("🎞 Résolution", "📚 Collections", "📡 En ligne")) + 40
        except Exception:
            keyw = 170
        for lab in self._card_vals.values():
            lab.configure(wraplength=max(200, w - keyw - 20))
        self.codec_msg.configure(wraplength=max(200, w - 300))
        self.sug_msg.configure(wraplength=max(200, w - 260))
        self.tr_msg.configure(wraplength=max(200, w - 20))
        self.ex_msg.configure(wraplength=max(200, w - 20))
        self.pl_note.configure(wraplength=max(200, w - 30))

    def _render_storyboard(self, reuse: bool = False):
        for w in self.sb_row.winfo_children():
            w.destroy()
        self.sb_row.configure(height=1)  # Tk: un cadre vidé garde sa taille sinon
        self._sb_photos = []
        path = self._preview_path
        if not path or not os.path.isdir(path):
            self.sb_msg.configure(text="")
            return
        frames = list_storyboard(path)
        main = find_main_media(path)
        is_video = bool(main and main.lower().endswith(VIDEO_EXTS))
        if not frames:
            if not is_video:
                self.sb_msg.configure(text="(pas de vidéo dans cette archive)")
            elif not find_ffmpeg():
                self.sb_msg.configure(text="(ffmpeg requis pour le storyboard)")
            elif path in self._sb_busy:
                self.sb_msg.configure(text="⏳ Storyboard en préparation… (quelques secondes)")
            elif path in self._sb_failed:
                self.sb_msg.configure(text="(storyboard impossible pour cette vidéo — clic droit : 🎞 Refaire le storyboard)")
            elif self._folder_converting(path):
                self.sb_msg.configure(text="⏳ Storyboard après la conversion en cours…")
            else:
                self._start_storyboard(path)
            return
        dur = None
        try:
            dur = float(self._preview_info.get("duration") or 0) or None
        except (TypeError, ValueError):
            dur = None
        times = storyboard_times(path, frames, dur)
        can_seek = bool(main) and self._integrated_ok(main)
        if can_seek:
            self.sb_msg.configure(text="👆 Clique sur une image pour sauter à ce moment de la vidéo")
        else:
            self.sb_msg.configure(text="Clic = agrandir l'image · double-clic = ▶ lire la vidéo")
        if not HAS_PIL:
            return
        items = [(fmt_ts(times[i]) if i < len(times) else f"{i + 1}", p, times[i] if i < len(times) else 0.0)
                 for i, p in enumerate(frames)]
        avail = self._preview_width() - 8
        n_items = max(1, len(items))
        tile_w = max(96, min(200, avail // n_items - 10))
        cols = max(1, min(n_items, avail // (tile_w + 10)))
        if cols < n_items:  # répartir sur des rangées égales
            rows = -(-n_items // cols)
            cols = -(-n_items // rows)
            tile_w = max(90, min(200, avail // cols - 10))
        for idx, (lab_txt, p, t) in enumerate(items):
            try:
                key = (p, os.path.getmtime(p), tile_w)
                ph = self._sb_imcache.get(key)
                if ph is None:
                    im = Image.open(p)
                    im.thumbnail((tile_w, int(tile_w * 0.75)))
                    ph = ImageTk.PhotoImage(im.convert("RGB"))
                    if len(self._sb_imcache) > 400:
                        self._sb_imcache.clear()
                    self._sb_imcache[key] = ph
            except Exception:
                continue
            self._sb_photos.append(ph)
            cell = tk.Frame(self.sb_row, bg=NC_BG)
            cell.grid(row=idx // cols, column=idx % cols, padx=3, pady=2, sticky="n")
            lb = tk.Label(cell, image=ph, bg=NC_HI if p == self._thumb_src_path_shown() else NC_BG,
                          bd=0, padx=2, pady=2, cursor="hand2")
            lb.pack()
            tk.Label(cell, text=lab_txt, bg=NC_BG, fg=NC_DIM, font=FONT_SM).pack()
            if can_seek:
                lb.bind("<Button-1>", lambda e, tt=t: self._sb_jump(tt))
                Tooltip(lb, f"▶ Lire à partir de {lab_txt}")
            else:
                lb.bind("<Button-1>", lambda e, pp=p: self._show_big(pp))
                lb.bind("<Double-Button-1>", lambda e: self.open_selected_media())

    def _sb_jump(self, t: float):
        """Clic sur une image du storyboard : la vidéo part à ce moment-là."""
        try:
            self.player_seek_to(max(0.0, float(t)), play=True)
            self.status.set(f"▶ Lecture à {fmt_ts(t)}")
        except Exception:
            logger.exception("storyboard jump")

    def _folder_converting(self, path: str) -> bool:
        folder = os.path.basename(path)
        return any(j.get("kind") == "convert" and j.get("folder") == folder and j.get("status") in ("cours", "attente")
                   for j in self.jobs)

    def _thumb_src_path_shown(self):
        return getattr(self, "_shown_path", None) or getattr(self, "_thumb_src_path", None)

    def _show_big(self, p: str):
        if self.player.state != "stop":
            self.player_stop()
        try:
            im = Image.open(p)
            im.load()
            self._thumb_src = im.convert("RGB")
            self._shown_path = p
            self._render_thumb()
            self._render_storyboard(reuse=True)
        except Exception:
            logger.exception("show big")

    def _start_storyboard(self, path: str, force: bool = False):
        """Storyboard en arrière-plan (fil séparé, ffmpeg en priorité basse, un à la fois) : l'interface reste libre."""
        if path in self._sb_busy:
            return
        self._sb_busy.add(path)
        self._sb_failed.discard(path)
        if self._preview_path == path:
            self.sb_msg.configure(text="⏳ Storyboard en préparation… (quelques secondes)")
        dur = self._preview_info.get("duration") if self._preview_path == path else None
        if not dur:
            try:
                dur = load_info(path).get("duration")
            except Exception:
                dur = None
        try:
            dur = float(dur) if dur else None
        except (TypeError, ValueError):
            dur = None

        def _prog(i, n):
            def _ui():
                if self._preview_path == path and path in self._sb_busy and not list_storyboard(path):
                    self.sb_msg.configure(text=f"⏳ Storyboard en préparation… {i}/{n}")
            self.ui(_ui)

        def _job():
            frames = []
            try:
                with _SB_LOCK:
                    frames = generate_storyboard(path, SB_FRAMES, duration=dur, force=force, progress=_prog)
            except Exception:
                logger.exception("storyboard")
            self._sb_busy.discard(path)
            if not frames:
                self._sb_failed.add(path)

            def _done():
                if self._preview_path == path:
                    self._render_storyboard()
                    self._render_files()
                if frames:
                    self.log(f"🎞 Storyboard prêt ({len(frames)} images) : {os.path.basename(path)}")
            self.ui(_done)
        threading.Thread(target=_job, daemon=True, name="storyboard").start()

    def regen_storyboard(self):
        path = self._folder_path()
        if not path or not os.path.isdir(path):
            return
        self._sb_failed.discard(path)
        if not find_ffmpeg():
            messagebox.showinfo(APP_NAME, "ffmpeg est requis pour le storyboard.", parent=self)
            return
        self._start_storyboard(path, force=True)

    def _render_gallery(self):
        self._gal_paths = list_images(self._preview_path) if self._preview_path else []
        self._gal_more = 0
        if self._preview_path:
            page_imgs = [p for p in list_page_images(self._preview_path) if p not in self._gal_paths]
            self._gal_more = max(0, len(page_imgs) - 24)
            self._gal_paths += page_imgs[:24]
        self._gal_photos = []
        self._gal_cells = []
        for w in self.gal_frame.winfo_children():
            w.destroy()
        self.gal_frame.configure(height=1)
        n = len(self._gal_paths)
        more = getattr(self, "_gal_more", 0)
        self.gal_title.configure(text=f"🖼 Galerie ({n + more} image{'s' if n + more > 1 else ''})"
                                      + (f" — {n} affichées" if more else "") + " — clic = ouvrir")
        if not n:
            tk.Label(self.gal_frame, text="(aucune image)", bg=NC_BG, fg=NC_DIM, font=FONT_SM).grid(row=0, column=0)
            return
        if not HAS_PIL:
            return
        for p in self._gal_paths:
            try:
                im = Image.open(p)
                im.thumbnail((180, 135))
                ph = ImageTk.PhotoImage(im.convert("RGB"))
            except Exception:
                continue
            self._gal_photos.append(ph)
            cell = tk.Frame(self.gal_frame, bg=NC_PANEL, bd=1, relief="solid")
            lb = tk.Label(cell, image=ph, bg=NC_PANEL, cursor="hand2")
            lb.pack(padx=3, pady=3)
            name = os.path.basename(p)
            tk.Label(cell, text=wrap_name(name, 24), bg=NC_PANEL, fg=NC_FG, font=FONT_SM, justify="center").pack()
            for wdg in (lb, cell):
                wdg.bind("<Button-1>", lambda e, pp=p: self.open_path_safe(pp, "image"))
                wdg.bind("<Button-3>", lambda e, pp=p: self._show_link_menu(e, "path", pp))
            self._gal_cells.append(cell)
        self._layout_gallery()

    def _layout_gallery(self):
        cells = getattr(self, "_gal_cells", [])
        if not cells:
            return
        cols = max(1, self._preview_width() // 196)
        for i, c in enumerate(cells):
            c.grid(row=i // cols, column=i % cols, padx=4, pady=4, sticky="n")

    def _render_files(self):
        self.files_tree.delete(*self.files_tree.get_children())
        path = self._preview_path
        names = list_folder_files(path) if path and os.path.isdir(path) else []
        sb = list_storyboard(path) if path else []
        self.files_title.configure(text=f"📂 Fichiers ({len(names)}) — double-clic = ouvrir, clic droit = options")
        for n in names:
            p = os.path.join(path, n)
            try:
                st = os.stat(p)
                size, mod = human_size(st.st_size), datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
            except OSError:
                size, mod = "—", ""
            self.files_tree.insert("", "end", iid="f::" + n, text=f" {file_icon(n)}  {n}",
                                   values=(file_kind(n), size, mod))
        extra = 0
        if sb:
            self.files_tree.insert("", "end", iid="f::" + STORYBOARD_DIR, text=f" 🎞  {STORYBOARD_DIR}\\  ({len(sb)} images)",
                                   values=("Dossier", human_size(sum(os.path.getsize(x) for x in sb)), ""))
            extra += 1
        for sub, icon in ((EXTRACTS_DIR, "✂"), (WEB_ASSETS_DIR, "🗂"), ("auteur", "👤")):
            d = os.path.join(path, sub) if path else ""
            if d and os.path.isdir(d):
                fl = [os.path.join(d, x) for x in os.listdir(d) if os.path.isfile(os.path.join(d, x))]
                if fl:
                    self.files_tree.insert("", "end", iid="f::" + sub, text=f" {icon}  {sub}\\  ({len(fl)} fichiers)",
                                           values=("Dossier", human_size(sum(os.path.getsize(x) for x in fl)), ""))
                    extra += 1
        self.files_tree.configure(height=max(3, min(12, len(names) + extra)))

    def _selected_file_path(self) -> Optional[str]:
        sel = self.files_tree.selection()
        if not sel or not self._preview_path:
            return None
        return os.path.join(self._preview_path, sel[0][3:])

    def open_preview_file(self):
        fp = self._selected_file_path()
        if fp and os.path.exists(fp):
            self._open_media(fp, "fichier")

    def reveal_preview_file(self):
        fp = self._selected_file_path()
        if fp:
            ok, err = reveal_in_explorer(fp)
            if not ok:
                messagebox.showerror(APP_NAME, err, parent=self)

    def copy_preview_file_path(self):
        fp = self._selected_file_path()
        if fp:
            self._copy_to_clipboard(fp)

    def copy_preview_file_name(self):
        fp = self._selected_file_path()
        if fp:
            self._copy_to_clipboard(os.path.basename(fp))

    def _files_menu_popup(self, event):
        iid = self.files_tree.identify_row(event.y)
        if iid:
            self.files_tree.selection_set(iid)
        else:
            return "break"
        try:
            self._files_menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                self._files_menu.grab_release()
            except Exception:
                pass
        return "break"

    # ------------------------------------------------------------ actions
    def open_path_safe(self, path: str, kind: str = "élément"):
        ok, err = open_path_explorer(path)
        if not ok:
            messagebox.showerror(APP_NAME, err or f"Impossible d'ouvrir le {kind}.", parent=self)
        return ok

    def open_selected_folder(self):
        path = self._folder_path()
        if not path or not os.path.isdir(path):
            root = self.archive_root_path()
            os.makedirs(root, exist_ok=True)
            self.status.set("Aucune archive sélectionnée — ouverture du dossier racine.")
            self.open_path_safe(root, "dossier")
            return
        self.open_path_safe(path, "dossier")

    def open_last_or_selected_folder(self):
        """Sélection → dernier archivage → racine ARCHIVEUR."""
        e = self._selected_entry()
        path = None
        if e and e.get("folder"):
            path = os.path.join(self.archive_root_path(), str(e["folder"]))
        if (not path or not os.path.isdir(path)) and self.last_folder:
            path = os.path.join(self.archive_root_path(), self.last_folder)
        if not path or not os.path.isdir(path):
            path = self.archive_root_path()
            os.makedirs(path, exist_ok=True)
        self.log(f"Ouverture dossier: {path}")
        self.open_path_safe(path, "dossier")

    def open_selected_index(self):
        path = self._folder_path()
        if not path:
            messagebox.showinfo(APP_NAME, "Sélectionnez une archive dans l'historique.", parent=self)
            return
        idx = os.path.join(path, "index.html")
        if not os.path.isfile(idx):
            try:
                write_local_index(path, load_info(path))
            except Exception:
                logger.exception("index local")
        if os.path.isfile(idx):
            self._open_url(idx)
        else:
            messagebox.showwarning(APP_NAME, f"index.html introuvable:\n{idx}", parent=self)

    def open_selected_media(self):
        path = self._folder_path()
        if not path or not os.path.isdir(path):
            messagebox.showinfo(APP_NAME, "Sélectionnez une archive.", parent=self)
            return
        main = find_main_media(path)
        if main and self.player.state == "play":
            self.player.pause()
        if main:
            if main.lower().endswith(VIDEO_EXTS) and self._player() == "windows" and find_ffmpeg():
                c = self._codec_for(main)
                if c.get("vcodec") and not is_compatible(main, c):
                    r = messagebox.askyesnocancel(
                        APP_NAME,
                        f"Cette vidéo est en {codec_label(c)}.\nLe lecteur Windows risque de demander un codec "
                        "(« Extension vidéo AV1 »).\n\nOui = la convertir en MP4 compatible (H.264) maintenant\n"
                        "Non = l'ouvrir quand même\nAnnuler = ne rien faire", parent=self)
                    if r is None:
                        return
                    if r:
                        self.convert_selected_path(path)
                        return
            self._open_media(main, "média")
            return
        imgs = list_images(path)
        if imgs:
            self.open_path_safe(imgs[0], "image")
            return
        messagebox.showinfo(APP_NAME, "Aucun fichier média trouvé dans ce dossier.", parent=self)

    def convert_selected_path(self, path: str):
        folder = os.path.basename(path)
        title = next((str(e.get("title") or "") for e in self.entries if e.get("folder") == folder), folder)
        if self._enqueue_convert([(folder, title)]):
            self.status.set("🎬 Conversion lancée — la vidéo sera lisible dans le lecteur Windows ensuite.")

    def _entry_url(self) -> str:
        e = self._selected_entry()
        if not e:
            return ""
        info = self._preview_info if self._preview_entry is e else e
        return str(info.get("webpage_url") or info.get("url") or e.get("url") or "")

    def open_original(self):
        u = self._entry_url()
        if u:
            self._open_url(u)
        else:
            messagebox.showinfo(APP_NAME, "Aucune URL d'origine pour cette archive.", parent=self)

    def copy_link(self):
        u = self._entry_url()
        if u:
            self._copy_to_clipboard(u)

    def copy_folder_path(self):
        p = self._folder_path()
        if p:
            self._copy_to_clipboard(p)

    def save_tags_notes(self, quiet: bool = False):
        e = self._preview_entry
        if not e or not e.get("folder"):
            if not quiet:
                self.status.set("Sélectionnez une archive pour enregistrer tags/notes.")
            return
        tags, notes = self._tn_current()
        try:
            info = update_tags_notes(self.archive_root_path(), str(e["folder"]), tags, notes)
        except Exception as ex:
            logger.exception("tags/notes")
            if not quiet:
                messagebox.showerror(APP_NAME, f"Enregistrement impossible:\n{friendly_error(ex)}", parent=self)
            return
        e["tags"] = info.get("tags") or []
        e["notes"] = info.get("notes") or ""
        for x in self.entries:
            if x.get("folder") == e.get("folder"):
                x["tags"], x["notes"] = e["tags"], e["notes"]
        if self._preview_entry is e:
            self._preview_info.update({"tags": e["tags"], "notes": e["notes"]})
            self._loaded_tn = self._tn_current()
            self.tags_var.set(", ".join(e["tags"]))
            self._loaded_tn = self._tn_current()
            self._render_tag_chips(e["tags"], self._preview_info.get("source_tags") or [])
            self.tn_state.configure(text=f"✅ Enregistré ({datetime.now().strftime('%H:%M:%S')})", fg=NC_OK)
        if not quiet:
            self.log(f"🏷 Tags/notes enregistrés : {', '.join(e['tags']) or '(aucun tag)'}")
            self.apply_filter()

    def rename_selected(self):
        e = self._selected_entry()
        if not e or not e.get("folder"):
            messagebox.showinfo(APP_NAME, "Sélectionnez une archive à renommer.", parent=self)
            return
        new_name = (self.name_var.get() or "").strip()
        if not new_name:
            messagebox.showwarning(APP_NAME, "Le nom ne peut pas être vide.", parent=self)
            return
        if self._preview_entry is e:
            self._autosave_tn()
        try:
            updated = rename_archive(self.archive_root_path(), str(e.get("folder")), new_name, log=self.log)
        except Exception as ex:
            logger.exception("rename")
            messagebox.showerror(APP_NAME, f"Renommage impossible:\n\n{ex}", parent=self)
            return
        self.last_folder = updated.get("folder")
        self._preview_entry = None
        self.refresh_list()
        self.select_folder(updated.get("folder"))
        self.log(f"✏ Renommé → {updated.get('folder')}")

    def delete_selected(self):
        ents = self._selected_entries()
        if len(ents) > 1:
            folders = [str(x.get("folder")) for x in ents if x.get("folder")]
            listing = "\n".join(f"• {str(x.get('title') or x.get('folder'))[:70]}" for x in ents[:10])
            more = f"\n… et {len(ents) - 10} autre(s)" if len(ents) > 10 else ""
            if not messagebox.askyesno(APP_NAME, f"Supprimer définitivement ces {len(folders)} archives ?\n\n"
                                       f"{listing}{more}\n\nLes dossiers et leurs fichiers seront effacés.",
                                       parent=self, icon="warning"):
                return
            try:
                self.player.stop()
                n = delete_archives(self.archive_root_path(), folders)
                self.log(f"🗑 {n} archive(s) supprimée(s).")
            except Exception as ex:
                logger.exception("delete many")
                messagebox.showerror(APP_NAME, f"Suppression impossible:\n{friendly_error(ex)}", parent=self)
            self._preview_entry = None
            self.refresh_list()
            if self._visible:
                self.select_folder(self._visible[0].get("folder"))
            else:
                self.clear_preview()
            return
        e = self._selected_entry()
        if not e or not e.get("folder"):
            return
        folder = str(e["folder"])
        path = os.path.join(self.archive_root_path(), folder)
        if not messagebox.askyesno(
            APP_NAME,
            f"Supprimer définitivement cette archive ?\n\n{e.get('title') or folder}\n{folder}\n\n"
            "Le dossier et ses fichiers seront effacés.",
            parent=self, icon="warning",
        ):
            return
        try:
            self.player.stop()
            if os.path.isdir(path):
                shutil.rmtree(path)
            entries = [x for x in load_archive_index(self.archive_root_path()) if x.get("folder") != folder]
            save_archive_index(self.archive_root_path(), entries)
            if self.last_folder == folder:
                self.last_folder = None
            self._preview_entry = None
            self.log(f"🗑 Supprimé: {folder}")
            self.refresh_list()
            if self._visible:
                self.select_folder(self._visible[0].get("folder"))
            else:
                self.clear_preview()
        except Exception as ex:
            logger.exception("delete")
            messagebox.showerror(APP_NAME, f"Suppression impossible:\n{friendly_error(ex)}", parent=self)

    # ------------------------------------------------------------ champ URL
    def paste_and_archive(self):
        """Lit le presse-papiers, affiche le lien, valide http(s), lance l'archivage."""
        try:
            clip = self.clipboard_get()
        except tk.TclError:
            messagebox.showinfo(APP_NAME, "Le presse-papiers est vide ou illisible.", parent=self)
            return
        clip = (clip or "").strip()
        urls = extract_urls(clip)
        if not urls:
            preview = clip if len(clip) <= 200 else clip[:200] + "…"
            messagebox.showwarning(
                APP_NAME,
                "Le presse-papiers ne contient pas de lien http:// ou https:// valide.\n\n"
                f"Contenu:\n{preview or '(vide)'}",
                parent=self,
            )
            return
        self._url_ph = False
        self.url_text.delete("1.0", "end")
        self.url_text.insert("1.0", "\n".join(urls))
        self.url_text.see("1.0")
        self._clip_last = clip
        self.enqueue_urls(urls)

    def _on_paste_archive(self, _evt=None):
        self.paste_and_archive()
        return "break"

    def _on_select_all(self, _evt=None):
        if self._url_ph:
            return "break"
        self.url_text.tag_add("sel", "1.0", "end-1c")
        self.url_text.mark_set("insert", "1.0")
        return "break"

    def _ctx_paste(self):
        try:
            clip = self.clipboard_get()
        except tk.TclError:
            return
        self._url_clear_ph()
        try:
            self.url_text.delete("sel.first", "sel.last")
        except tk.TclError:
            pass
        self.url_text.insert("insert", clip or "")

    def _ctx_copy(self):
        if self._url_ph:
            return
        try:
            self._copy_to_clipboard(self.url_text.get("sel.first", "sel.last"))
        except tk.TclError:
            pass

    def _ctx_cut(self):
        self._ctx_copy()
        try:
            self.url_text.delete("sel.first", "sel.last")
        except tk.TclError:
            pass

    def _ctx_clear(self):
        self._url_ph = False
        self.url_text.delete("1.0", "end")
        self.url_text.focus_set()

    def _show_url_menu(self, event):
        try:
            self._url_menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                self._url_menu.grab_release()
            except Exception:
                pass
        return "break"

    def _on_enter_archive(self, _evt=None):
        self.enqueue_from_text()
        return "break"

    def enqueue_from_text(self, clear_field: bool = False):
        urls = extract_urls(self._url_content())
        if not urls:
            messagebox.showinfo(APP_NAME, "Collez au moins un lien http(s) dans le champ\n"
                                "(ou cliquez « 📋 Coller et archiver »).", parent=self)
            return
        self.enqueue_urls(urls)
        if clear_field:
            self.url_text.delete("1.0", "end")

    # ------------------------------------------------------------ lot
    def open_batch_dialog(self):
        win = tk.Toplevel(self)
        win.title(f"{APP_NAME} — plusieurs liens")
        win.configure(bg=NC_BG)
        win.geometry("900x560")
        win.transient(self)
        try:
            win.iconphoto(False, self._icon_img)
        except Exception:
            pass
        tk.Label(win, text="📝 Colle une liste de liens (un par ligne, ou du texte contenant des liens)",
                 bg=NC_BG, fg=NC_HI, font=FONT_UI).pack(anchor="w", padx=10, pady=(10, 4))
        fr, txt = self._scrolled_text(win, height=18, bg=NC_ENTRY_BG, fg=NC_ENTRY_FG, font=FONT_UI, wrap="none")
        fr.pack(fill="both", expand=True, padx=10)
        cnt = tk.StringVar(value="0 lien détecté")
        row = tk.Frame(win, bg=NC_BG)
        row.pack(fill="x", padx=10, pady=8)
        tk.Label(row, textvariable=cnt, bg=NC_BG, fg=NC_FG, font=FONT_SM).pack(side="left")

        def _count(*_):
            n = len(extract_urls(txt.get("1.0", "end")))
            cnt.set(f"{n} lien{'s' if n > 1 else ''} détecté{'s' if n > 1 else ''}")

        def _paste():
            try:
                txt.insert("insert", self.clipboard_get())
            except tk.TclError:
                pass
            _count()

        def _go():
            urls = extract_urls(txt.get("1.0", "end"))
            if not urls:
                messagebox.showinfo(APP_NAME, "Aucun lien http(s) détecté.", parent=win)
                return
            win.destroy()
            n = self.enqueue_urls(urls)
            if n:
                self._show_bottom("queue")

        txt.bind("<KeyRelease>", _count)
        txt.bind("<<Paste>>", lambda e: self.after(10, _count))
        self._btn(row, "📥 Archiver tout", _go, hi=True, font=FONT_UI).pack(side="right", padx=4)
        self._btn(row, "Annuler", win.destroy).pack(side="right", padx=4)
        self._btn(row, "📋 Coller", _paste).pack(side="right", padx=4)
        txt.focus_set()
        self._batch_win = win
        return win

    # ------------------------------------------------------------ file d'attente
    def _active_keys(self) -> set:
        return {j.get("key") or normalize_url(j["url"]) for j in self.jobs if j["status"] in ("attente", "cours")}

    def archive_text_as_page(self):
        urls = extract_urls(self._url_content())
        if not urls:
            try:
                urls = extract_urls(self.clipboard_get())
            except tk.TclError:
                urls = []
        if not urls:
            messagebox.showinfo(APP_NAME, "Colle d'abord un lien dans le champ.", parent=self)
            return
        self.enqueue_urls(urls, extra={"page_mode": True})

    def enqueue_urls(self, urls: List[str], ask_dups: bool = True, extra: Optional[Dict[str, Any]] = None) -> int:
        clean: List[str] = []
        seen = set()
        active = self._active_keys()
        for u in urls:
            u = u.strip()
            if not u:
                continue
            if not re.match(r"^https?://", u, re.I):
                u = "https://" + u
            k = normalize_url(u)
            self._clip_seen.add(k)
            if k in seen:
                continue
            seen.add(k)
            if k in active:
                self.log(f"Déjà dans la file : {u}")
                continue
            clean.append(u)
        if not clean:
            return 0
        dups = {u: find_duplicates(self.entries, u) for u in clean}
        dups = {u: d for u, d in dups.items() if d}
        if dups and ask_dups:
            if len(clean) == 1:
                d = dups[clean[0]][0]
                r = messagebox.askyesnocancel(
                    APP_NAME,
                    "Ce lien est déjà archivé :\n\n"
                    f"« {d.get('title') or d.get('folder')} »\n"
                    f"archivé le {fmt_iso(d.get('archived_at'))}"
                    + (f"  ({len(dups[clean[0]])} copies)" if len(dups[clean[0]]) > 1 else "") + "\n\n"
                    "Oui = ouvrir l'archive existante\n"
                    "Non = re-archiver quand même\n"
                    "Annuler = ne rien faire",
                    parent=self,
                )
                if r is None:
                    return 0
                if r:
                    self.select_folder(d.get("folder"))
                    self.status.set("Archive existante affichée dans l'aperçu.")
                    return 0
            else:
                listing = "\n".join(f"• {(d[0].get('title') or d[0].get('folder'))[:70]}" for d in list(dups.values())[:8])
                more = f"\n… et {len(dups) - 8} autre(s)" if len(dups) > 8 else ""
                r = messagebox.askyesnocancel(
                    APP_NAME,
                    f"{len(dups)} lien(s) sur {len(clean)} sont déjà archivés :\n\n{listing}{more}\n\n"
                    "Oui = ignorer les doublons (archiver seulement les nouveaux)\n"
                    "Non = tout archiver quand même\n"
                    "Annuler = ne rien faire",
                    parent=self,
                )
                if r is None:
                    return 0
                if r:
                    clean = [u for u in clean if u not in dups]
                    if not clean:
                        self.status.set("Tous les liens étaient déjà archivés.")
                        return 0
        opts = self._job_opts()
        if extra:
            opts.update(extra)
        start = False
        with self._jobs_lock:
            for u in clean:
                self._job_seq += 1
                self.jobs.append({"id": self._job_seq, "url": u, "status": "attente", "pct": 0.0,
                                  "title": "", "folder": "", "error": "", "detail": "", "opts": dict(opts)})
            if not self._worker_running:
                self._worker_running = True
                start = True
        for u in clean:
            self.log(f"En file: {u}")
        self._refresh_queue_view()
        self._show_bottom("queue", auto=True)
        if start:
            threading.Thread(target=self._worker, daemon=True).start()
        else:
            self.status.set(f"{len(clean)} lien(s) ajouté(s) à la file (archivage en cours).")
        return len(clean)

    def _job_values(self, j):
        pct = f"{j['pct']:.0f}%" if j["status"] in ("cours", "ok") else ""
        label = j["title"] or j["url"]
        if j["status"] == "echec" and j.get("error"):
            label = f"{label} — {j['error']}"
        elif j["status"] == "cours" and j.get("detail"):
            label = f"{label} — {j['detail']}"
        return (JOB_LABELS.get(j["status"], j["status"]), pct, label)

    def _refresh_queue_view(self):
        sel = self.qtree.selection()
        self.qtree.delete(*self.qtree.get_children())
        for j in self.jobs:
            self.qtree.insert("", "end", iid=f"j{j['id']}", values=self._job_values(j))
        for s in sel:
            if self.qtree.exists(s):
                self.qtree.selection_set(s)
        self._refresh_bottom_labels()
        self._update_states()

    def _job_changed(self, j):
        iid = f"j{j['id']}"
        if self.qtree.exists(iid):
            self.qtree.item(iid, values=self._job_values(j))
        else:
            self._refresh_queue_view()
        if j["status"] == "cours":
            try:
                self.prog.set_mood("remux" if j.get("conv_mode") in ("remux", "audio") else "normal")
            except Exception:
                pass
            self.prog.configure(value=j["pct"])
            name = (j["title"] or j["url"])[:70]
            if j.get("conv_mode"):
                self.prog_var.set(f"{j.get('detail') or '🎬 Conversion…'} — {name.lstrip('🎬 ')}")
            else:
                self.prog_var.set(f"⬇ {name} — {j.get('detail') or 'Préparation…'}")
            self.cancel_btn.configure(state="normal")
        else:
            self._refresh_queue_view()

    def _make_hook(self, job):
        state = {"t": 0.0, "q": -1}

        def hook(d):
            st = d.get("status")
            if st == "downloading":
                tot = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                done = d.get("downloaded_bytes") or 0
                pct = None
                if tot:
                    pct = min(100.0, done * 100.0 / tot)
                elif d.get("fragment_count"):
                    pct = min(100.0, (d.get("fragment_index") or 0) * 100.0 / max(1, d["fragment_count"]))
                now = time.time()
                if now - state["t"] < 0.25 and (pct or 0) < 99.9:
                    return
                state["t"] = now
                if pct is not None:
                    job["pct"] = pct
                parts = []
                if pct is not None:
                    parts.append(f"{pct:.0f} %")
                if tot:
                    parts.append(f"{human_size(done)} / {human_size(tot)}")
                if d.get("speed"):
                    parts.append(f"{human_size(d['speed'])}/s")
                if d.get("eta") is not None:
                    parts.append(f"reste {human_duration(d['eta']) if d['eta'] else '0:00'}")
                job["detail"] = " · ".join(parts) or "Téléchargement…"
                info = d.get("info_dict") or {}
                if info.get("title") and not job["title"]:
                    job["title"] = str(info.get("title"))
                if pct is not None and int(pct // 25) > state["q"]:
                    state["q"] = int(pct // 25)
                    self.log(f"Téléchargement {pct:.0f} %")
                self.ui(lambda: self._job_changed(job))
            elif st == "converting":
                job["pct"] = float(d.get("pct") or 0)
                job["conv_mode"] = str(d.get("mode") or "encode")
                job["detail"] = "🎬 " + conv_detail(d)
                self.ui(lambda: self._job_changed(job))
            elif st == "finished":
                state["q"] = -1
                job["detail"] = "Traitement (fusion, miniature, storyboard)…"
                self.log(f"Fichier: {os.path.basename(d.get('filename') or '')}")
                self.ui(lambda: self._job_changed(job))
        return hook

    def _worker(self):
        while True:
            with self._jobs_lock:
                job = next((j for j in self.jobs if j["status"] == "attente"), None)
                if job is None:
                    self._worker_running = False
                    break
                job["status"] = "cours"
                job["pct"] = 0.0
                job["detail"] = "Analyse du lien…"
            self._cancel_event.clear()
            self.ui(lambda j=job: self._job_changed(j))
            o = job["opts"]
            if job.get("kind") == "convert":
                self._run_convert_job(job)
                self.ui(lambda j=job: self._job_changed(j))
                continue
            if job.get("kind") == "whisper":
                self._run_whisper_job(job)
                self.ui(lambda j=job: self._job_changed(j))
                continue
            try:
                info = archive_url(
                    job["url"], o["root"], self.log, cookies_browser=o.get("cookies"),
                    progress_hook=self._make_hook(job), quality=o.get("quality", "best"),
                    subtitles=o.get("subtitles", True), storyboard=o.get("storyboard", True),
                    cancel_event=self._cancel_event, auto_convert=o.get("auto_convert", True),
                    web_capture=o.get("web_capture", True), use_fx=o.get("use_fx", True),
                    page_mode=bool(o.get("page_mode")),
                )
                entry = register_archive(o["root"], info)
                job.update(status="ok", pct=100.0, title=str(entry.get("title") or ""),
                           folder=str(entry.get("folder") or ""), detail="")
                self.last_folder = entry.get("folder")
                self._run_stats["ok"] += 1
                self._run_stats["last_title"] = job["title"]
                self.log(f"✅ Archivé: {entry['folder']}")
                self.ui(lambda e=entry: self._on_job_ok(e))
            except ArchiveCancelled:
                job.update(status="annule", detail="")
                self._run_stats["annule"] += 1
                self.log("⛔ Archivage annulé.")
            except Exception as e:
                logger.exception("archivage %s", job["url"])
                job.update(status="echec", error=friendly_error(e), detail="")
                self._run_stats["echec"] += 1
                self.log(f"❌ Échec: {friendly_error(e)}", "error")
            self.ui(lambda j=job: self._job_changed(j))
        self.ui(self._on_queue_done)

    def _run_convert_job(self, job):
        """Exécuté dans le thread worker : conversion MP4 compatible d'une archive."""
        o = job["opts"]
        fp = os.path.join(o["root"], job["folder"])

        def stats(s):
            job["pct"] = float(s.get("pct") or 0)
            job["conv_mode"] = str(s.get("mode") or "encode")
            job["detail"] = "🎬 " + conv_detail(s)
            self.ui(lambda: self._job_changed(job))
        try:
            r = fix_folder_codecs(fp, self.log, cancel_event=self._cancel_event, stats=stats)
            if r == "cancel":
                job.update(status="annule", detail="")
                self._run_stats["annule"] += 1
                return
            job.update(status="ok", pct=100.0, detail="déjà compatible" if r == "skip" else "")
            self._run_stats["ok"] += 1
            self._run_stats["last_title"] = job["title"]
            if r == "skip":
                self.log(f"Déjà compatible : {job['folder']}")
            self._codec_cache.clear()
            self.ui(lambda f=job["folder"]: self._after_convert(f))
        except Exception as e:
            logger.exception("conversion %s", job["folder"])
            job.update(status="echec", error=friendly_error(e), detail="")
            self._run_stats["echec"] += 1
            self.log(f"❌ Conversion : {friendly_error(e)}", "error")

    def _after_convert(self, folder):
        cur = self._preview_entry.get("folder") if self._preview_entry else None
        self._preview_entry = None
        self.refresh_list()
        if cur:
            self.select_folder(cur)
        elif folder:
            self.select_folder(folder)

    def _enqueue_convert(self, items: List[Tuple[str, str]]) -> int:
        """items = [(folder, titre)] → tâches « convert » dans la file (une à la fois, annulables)."""
        active = self._active_keys()
        opts = self._job_opts()
        added = 0
        start = False
        with self._jobs_lock:
            for folder, title in items:
                if "conv:" + folder in active:
                    continue
                self._job_seq += 1
                self.jobs.append({"id": self._job_seq, "kind": "convert", "key": "conv:" + folder,
                                  "url": f"🎬 MP4 compatible : {folder}", "status": "attente", "pct": 0.0,
                                  "title": f"🎬 {title or folder}", "folder": folder, "error": "",
                                  "detail": "", "opts": dict(opts)})
                added += 1
            if added and not self._worker_running:
                self._worker_running = True
                start = True
        if added:
            self._refresh_queue_view()
            self._show_bottom("queue", auto=True)
        if start:
            threading.Thread(target=self._worker, daemon=True).start()
        return added

    def convert_selected(self):
        e = self._selected_entry()
        path = self._folder_path(e)
        if not e or not path or not os.path.isdir(path):
            messagebox.showinfo(APP_NAME, "Sélectionnez une archive vidéo.", parent=self)
            return
        if not find_ffmpeg():
            messagebox.showwarning(APP_NAME, "ffmpeg est requis pour la conversion.", parent=self)
            return
        main = find_main_media(path)
        if not main or not main.lower().endswith(VIDEO_EXTS):
            messagebox.showinfo(APP_NAME, "Cette archive ne contient pas de vidéo.", parent=self)
            return
        c = self._codec_for(main)
        if is_compatible(main, c):
            if not messagebox.askyesno(APP_NAME, f"La vidéo est déjà compatible ({codec_label(c)}, MP4).\n\n"
                                       "La vérifier / reconvertir quand même ?", parent=self):
                return
        n = self._enqueue_convert([(str(e.get("folder")), str(e.get("title") or ""))])
        if n:
            self.status.set("🎬 Conversion ajoutée à la file — ferme le lecteur vidéo s'il lit ce fichier.")

    def fix_all_codecs(self):
        if not find_ffmpeg():
            messagebox.showwarning(APP_NAME, "ffmpeg est requis pour la conversion.", parent=self)
            return
        root = self.archive_root_path()
        self.status.set("🔎 Analyse des codecs des archives…")

        def scan():
            try:
                todo = scan_incompatible(root)
            except Exception as ex:
                logger.exception("scan codecs")
                msg = friendly_error(ex)
                self.ui(lambda: messagebox.showerror(APP_NAME, f"Analyse impossible:\n{msg}", parent=self))
                return

            def ask():
                if not todo:
                    messagebox.showinfo(APP_NAME, "✅ Toutes les vidéos archivées sont déjà en MP4 H.264 compatible.",
                                        parent=self)
                    self.status.set("✅ Toutes les vidéos sont compatibles.")
                    return
                titles = {str(e.get("folder")): str(e.get("title") or "") for e in self.entries}
                listing = "\n".join(f"• {titles.get(f, f)[:60]}  ({lab})" for f, lab in todo[:10])
                more = f"\n… et {len(todo) - 10} autre(s)" if len(todo) > 10 else ""
                if messagebox.askyesno(APP_NAME, f"{len(todo)} vidéo(s) ne sont pas lisibles par le lecteur Windows :\n\n"
                                       f"{listing}{more}\n\nLes convertir en MP4 H.264 + AAC maintenant ?\n"
                                       "(le fichier est remplacé ; ferme le lecteur vidéo avant)", parent=self):
                    self._enqueue_convert([(f, titles.get(f, f)) for f, _l in todo])
            self.ui(ask)
        threading.Thread(target=scan, daemon=True).start()

    def _codec_for(self, video: str) -> Dict[str, Any]:
        try:
            key = (video, os.path.getmtime(video))
        except OSError:
            return {}
        if key not in self._codec_cache:
            self._codec_cache[key] = probe_codecs(video)
        return self._codec_cache[key]

    def _check_codec_async(self, path: str, video: str):
        try:
            key = (video, os.path.getmtime(video))
        except OSError:
            return
        if key in self._codec_cache:
            self._show_codec_banner(path, video, self._codec_cache[key])
            return

        def job():
            c = probe_codecs(video)
            self._codec_cache[key] = c
            self.ui(lambda: self._show_codec_banner(path, video, c))
        threading.Thread(target=job, daemon=True).start()

    def _show_codec_banner(self, path: str, video: str, c: Dict[str, Any]):
        if self._preview_path != path:
            return
        if c.get("vcodec") and not is_compatible(video, c):
            self.codec_msg.configure(text=f"⚠ Vidéo {codec_label(c)} : le lecteur Windows peut demander un codec "
                                          f"(« Extension vidéo AV1 »). Convertis-la en MP4 H.264.",
                                     wraplength=max(200, self._preview_width() - 300))
            self.codec_banner.pack(fill="x", padx=8, pady=(6, 0), after=self._codec_anchor)
        else:
            self.codec_banner.pack_forget()
        if c.get("vcodec"):
            res = self._preview_info.get("resolution") or ""
            if c.get("width") and c.get("height") and not res:
                res = f"{c['width']}x{c['height']}"
            self._set_card("resolution", f"{res or '—'} · {codec_label(c)}")

    def _player(self) -> str:
        p = self.cfg.get("player") or "windows"
        return p if p in self._players else "windows"

    def _open_media(self, path: str, kind: str = "média") -> bool:
        if path.lower().endswith(VIDEO_EXTS + AUDIO_EXTS):
            ok, err = open_media(path, self._player())
            if not ok:
                messagebox.showerror(APP_NAME, err or f"Impossible d'ouvrir le {kind}.", parent=self)
            else:
                self.status.set(f"▶ Lecture : {os.path.basename(path)} ({PLAYER_LABELS.get(self._player())})")
            return ok
        return self.open_path_safe(path, kind)

    def _on_job_ok(self, entry):
        self._preview_entry = None
        self.refresh_list()
        if not self.select_folder(entry.get("folder")):
            self.show_preview(entry)
        # storyboard tout de suite après l'archivage (arrière-plan), même si une autre archive est affichée
        try:
            path = os.path.join(self.archive_root_path(), str(entry.get("folder") or ""))
            main = find_main_media(path) if entry.get("folder") else None
            if main and main.lower().endswith(VIDEO_EXTS) and not list_storyboard(path) and find_ffmpeg() \
                    and not self._folder_converting(path):
                self._start_storyboard(path)
        except Exception:
            logger.exception("storyboard après archivage")

    def _on_queue_done(self):
        s = self._run_stats
        total = s["ok"] + s["echec"] + s["annule"]
        self.prog.configure(value=0)
        if total == 0:
            return
        if total == 1 and s["ok"] == 1:
            msg = f"Archivé : {s['last_title']}"
        else:
            msg = f"Terminé : {s['ok']} OK" + (f", {s['echec']} échec(s)" if s["echec"] else "") + \
                  (f", {s['annule']} annulé(s)" if s["annule"] else "")
        self.prog_var.set("✅ " + msg if not s["echec"] else "⚠ " + msg)
        self.status.set(("✅ " if not s["echec"] else "⚠ ") + msg)
        self.log("File terminée — " + msg)
        if self.notif_var.get():
            notify_desktop(APP_NAME, msg)
        failed = bool(s["echec"])
        self._run_stats = {"ok": 0, "echec": 0, "annule": 0, "last_title": ""}
        self._refresh_queue_view()
        if self._bottom_auto and not failed:
            self.after(6000, lambda: (self._collapse_bottom()
                                      if self._bottom_auto and not self._worker_running else None))

    def cancel_current(self):
        if any(j["status"] == "cours" for j in self.jobs):
            self._cancel_event.set()
            self.status.set("⛔ Annulation demandée…")
        else:
            self.status.set("Aucun archivage en cours.")

    def _selected_job(self):
        sel = self.qtree.selection()
        if not sel:
            return None
        jid = int(sel[0][1:])
        return next((j for j in self.jobs if j["id"] == jid), None)

    def remove_selected_job(self):
        j = self._selected_job()
        if not j:
            return
        if j["status"] == "cours":
            self.cancel_current()
            return
        with self._jobs_lock:
            self.jobs = [x for x in self.jobs if x is not j]
        self._refresh_queue_view()

    def retry_selected_job(self):
        j = self._selected_job()
        if not j or j["status"] not in ("echec", "annule"):
            self.status.set("Sélectionnez un lien en échec ou annulé pour réessayer.")
            return
        with self._jobs_lock:
            j.update(status="attente", pct=0.0, error="", detail="", opts=self._job_opts())
            start = not self._worker_running
            if start:
                self._worker_running = True
        self._refresh_queue_view()
        if start:
            threading.Thread(target=self._worker, daemon=True).start()

    def clear_done_jobs(self):
        with self._jobs_lock:
            self.jobs = [j for j in self.jobs if j["status"] in ("attente", "cours")]
        self._refresh_queue_view()

    def _on_job_double(self, _e=None):
        j = self._selected_job()
        if j and j.get("folder"):
            self.select_folder(j["folder"])
        elif j and j["status"] == "echec":
            messagebox.showinfo(APP_NAME, f"{j['url']}\n\n{j.get('error')}\n\nDétails : archiveur.log", parent=self)

    # ------------------------------------------------------------ presse-papiers
    def _toggle_clip_watch(self):
        self._persist_opts()
        if self.clip_var.get():
            try:
                self._clip_last = self.clipboard_get()
            except Exception:
                self._clip_last = ""
            if not self._clip_job:
                self._clip_job = self.after(1000, self._clip_poll)
            self.status.set("📋 Surveillance du presse-papiers activée — copie un lien pour l'archiver.")
        else:
            if self._clip_job:
                try:
                    self.after_cancel(self._clip_job)
                except Exception:
                    pass
            self._clip_job = None
            self._hide_clip_banner()
            self.status.set("Surveillance du presse-papiers désactivée.")

    def _clip_poll(self):
        self._clip_job = None
        if not self.clip_var.get():
            return
        try:
            txt = self.clipboard_get()
        except Exception:
            txt = ""
        if txt != self._clip_last:
            self._clip_last = txt
            if txt and len(txt) < 20000 and re.match(r"^\s*(https?://|www\.)", txt, re.I):
                try:
                    self._on_clip_urls(extract_urls(txt))
                except Exception:
                    logger.exception("clip")
        self._clip_job = self.after(1000, self._clip_poll)

    def _on_clip_urls(self, urls: List[str]):
        active = self._active_keys()
        fresh = []
        for u in urls:
            k = normalize_url(u)
            if k in self._clip_seen or k in active:
                continue
            self._clip_seen.add(k)
            fresh.append(u)
        if not fresh:
            return
        dups = find_duplicates(self.entries, fresh[0]) if len(fresh) == 1 else []
        if self.clip_auto_var.get() and not dups:
            self.log(f"📋 Lien copié détecté → archivage auto ({len(fresh)})")
            self.enqueue_urls(fresh, ask_dups=False)
            return
        self._clip_pending = fresh
        for w in self.clip_btns.winfo_children():
            w.destroy()
        if dups:
            d = dups[0]
            self.clip_msg.configure(text=f"📋 Lien copié déjà archivé : « {(d.get('title') or '')[:80]} »")
            self._btn(self.clip_btns, "📂 Ouvrir l'existante",
                      lambda f=d.get("folder"): (self._hide_clip_banner(), self.select_folder(f))).pack(side="left", padx=2)
            self._btn(self.clip_btns, "🔁 Re-archiver",
                      lambda: (self._hide_clip_banner(), self.enqueue_urls(self._clip_pending, ask_dups=False))).pack(side="left", padx=2)
        else:
            shown = fresh[0] if len(fresh) == 1 else f"{len(fresh)} liens"
            self.clip_msg.configure(text=f"📋 Lien copié détecté : {shown[:110]}")
            self._btn(self.clip_btns, "📥 Archiver", lambda: (self._hide_clip_banner(),
                      self.enqueue_urls(self._clip_pending)), hi=False).pack(side="left", padx=2)
        self._btn(self.clip_btns, "Ignorer", self._hide_clip_banner).pack(side="left", padx=2)
        self.clip_banner.pack(fill="x", pady=2, after=self._clip_anchor)
        try:
            self.bell()
        except Exception:
            pass

    def _hide_clip_banner(self):
        try:
            self.clip_banner.pack_forget()
        except Exception:
            pass

    # ------------------------------------------------------------ v5 : lecteur intégré (UI)
    def _build_player_bar(self, body):
        self._pbar_anchor = tk.Frame(body, bg=NC_BG, height=0)
        self._pbar_anchor.pack(fill="x")
        self.pbar = tk.Frame(body, bg=NC_PANEL, bd=0)
        self.pos_var = tk.DoubleVar(value=0.0)
        self.pos_scale = ttk.Scale(self.pbar, from_=0, to=1, variable=self.pos_var, orient="horizontal",
                                   style="Arch.Horizontal.TScale")
        self.pos_scale.pack(fill="x", padx=10, pady=(6, 1))
        self.pos_scale.bind("<ButtonPress-1>", self._seek_press)
        self.pos_scale.bind("<B1-Motion>", self._seek_motion)
        self.pos_scale.bind("<ButtonRelease-1>", self._seek_release)
        Tooltip(self.pos_scale, "Clique ou glisse pour te déplacer dans la vidéo")
        row = FlowFrame(self.pbar, bg=NC_PANEL, padx=3, pady=2)
        row.pack(fill="x", padx=6, pady=(0, 5))
        self._pl_row = row
        self.pl_play = row.add(self._btn(row, "▶ Lecture", self.player_toggle, hi=True, font=FONT_UI),
                               "Lecture / pause (Ctrl+Espace, ou clic sur l'image)")
        self.pl_stop = row.add(self._btn(row, "⏹", self.player_stop, font=FONT_UI), "Arrêter et revenir au début")
        self.pl_back = row.add(self._btn(row, "⏪ 10 s", lambda: self.player_skip(-10), font=FONT_SM),
                               "Reculer de 10 secondes (Ctrl+←)")
        self.pl_fwd = row.add(self._btn(row, "10 s ⏩", lambda: self.player_skip(10), font=FONT_SM),
                              "Avancer de 10 secondes (Ctrl+→)")
        self.pl_time = tk.Label(row, text="0:00 / 0:00", bg=NC_PANEL, fg=NC_HI, font=FONT_MONO, padx=6)
        row.add(self.pl_time, "Position / durée")
        self.pl_mute = row.add(self._btn(row, "🔊", self.player_mute, font=FONT_SM), "Couper / remettre le son")
        self.vol_var = tk.DoubleVar(value=float(self.cfg.get("volume", 80) or 0))
        self.vol_scale = ttk.Scale(row, from_=0, to=100, variable=self.vol_var, orient="horizontal", length=96,
                                   style="Arch.Horizontal.TScale", command=lambda v: self._vol_label())
        self.vol_scale.bind("<ButtonRelease-1>", lambda e: self._apply_volume())
        row.add(self.vol_scale, "Volume")
        self.pl_vol = tk.Label(row, text="", bg=NC_PANEL, fg=NC_FG, font=FONT_SM, width=4, anchor="w")
        row.add(self.pl_vol)
        self.pl_big = row.add(self._btn(row, "⛶ Grande fenêtre", self.player_bigwin, font=FONT_SM),
                              "Ouvrir la vidéo dans une fenêtre séparée, redimensionnable, à la position actuelle\n"
                              "(ffplay : F = plein écran, Espace = pause, ←/→ = ±10 s, Échap = fermer).\n"
                              "Double-clic sur l'image = pareil.")
        self.pl_note = tk.Label(self.pbar, text="", bg=NC_PANEL, fg=NC_DIM, font=FONT_SM, anchor="w", justify="left")
        self._seek_drag = False
        self._muted = False
        self._vol_label()
        self.player = LightPlayer(self, self.thumb_label, self._on_player_update)
        self.player.volume = int(self.vol_var.get())
        self._player_media = ""
        self._player_loaded = ""
        self._tr_cur = -1

    def _vol_label(self):
        try:
            v = int(float(self.vol_var.get()))
            self.pl_vol.configure(text=f"{v}%")
            self.pl_mute.configure(text="🔇" if (self._muted or v == 0) else "🔊")
        except Exception:
            pass

    def _apply_volume(self):
        v = int(float(self.vol_var.get()))
        self.cfg["volume"] = v
        save_cfg(self.cfg)
        if v > 0 and self._muted:
            self._muted = False
        self.player.set_volume(v, self._muted)
        self._vol_label()

    def player_mute(self):
        self._muted = not self._muted
        self.player.set_volume(int(float(self.vol_var.get())), self._muted)
        self._vol_label()
        self.status.set("🔇 Son coupé" if self._muted else "🔊 Son rétabli")

    def _integrated_ok(self, main: Optional[str] = None) -> bool:
        main = main if main is not None else self._player_media
        if not main or not bool(self.cfg.get("integrated_player", True)):
            return False
        if not find_ffmpeg():
            return False
        if main.lower().endswith(VIDEO_EXTS):
            return HAS_PIL
        return bool(find_ffplay())  # audio seul : il faut ffplay

    def _thumb_box(self) -> Tuple[int, int]:
        avail_w = self._preview_width()
        vis_h = self.pscroll.canvas.winfo_height()
        max_h = max(150, min(int(vis_h * 0.62), vis_h - 130)) if vis_h > 50 else 420
        return avail_w, max_h

    def _setup_player(self, main: Optional[str], info: Dict[str, Any]):
        """Prépare la barre du lecteur pour l'archive affichée (chargement réel au 1er ▶)."""
        try:
            self.player.stop()
        except Exception:
            logger.exception("arrêt lecteur")
        self._player_media = main or ""
        self._player_loaded = ""
        self._tr_cur = -1
        if not self._integrated_ok(main):
            self.pbar.pack_forget()
            return
        dur = 0.0
        try:
            dur = float(info.get("duration") or 0)
        except (TypeError, ValueError):
            dur = 0.0
        self.pos_scale.configure(to=max(1.0, dur))
        self.pos_var.set(0.0)
        self.pl_time.configure(text=f"{fmt_ts(0)} / {fmt_ts(dur) if dur else '—'}")
        self.pl_play.configure(text="▶ Lecture")
        is_vid = main.lower().endswith(VIDEO_EXTS)
        self._pl_row.set_visible(self.pl_big, is_vid)
        note = ""
        if not find_ffplay():
            note = "Son indisponible (ffplay introuvable) — la vidéo est lue sans le son."
        elif not is_vid:
            note = "🎵 Audio seul — lecture du son dans l'aperçu."
        self.pl_note.configure(text=note)
        if note:
            self.pl_note.pack(fill="x", padx=10, pady=(0, 4))
        else:
            self.pl_note.pack_forget()
        self.pbar.pack(fill="x", padx=8, pady=(0, 0), after=self._pbar_anchor)

    def _ensure_loaded(self) -> bool:
        if self._player_loaded == self._player_media and self.player.path:
            return True
        if not self._player_media or not os.path.isfile(self._player_media):
            return False
        self.status.set("⏳ Préparation de la lecture…")
        self.update_idletasks()
        ok = self.player.load(self._player_media, self._preview_info)
        self._player_loaded = self._player_media
        self.player.volume = int(float(self.vol_var.get()))
        self.player.muted = self._muted
        if self.player.duration:
            self.pos_scale.configure(to=max(1.0, self.player.duration))
        return ok or bool(self.player.duration)

    def play_selected(self):
        """▶ Lire : lecteur intégré si possible, sinon lecteur externe."""
        main = find_main_media(self._preview_path) if self._preview_path else None
        if main and main != self._player_media:
            self._setup_player(main, self._preview_info)
        if main and self._integrated_ok(main):
            self.player_toggle()
        else:
            self.open_selected_media()

    def player_toggle(self):
        if not self._integrated_ok():
            if self._preview_entry:
                self.open_selected_media()
            return
        st = self.player.state
        if st == "play":
            self.player.pause()
            return
        if not self._ensure_loaded():
            self.status.set("Lecture impossible : média illisible (voir 🧰 Outils → Vérifier les archives).")
            return
        w, h = self._thumb_box()
        at = float(self.pos_var.get()) if st in ("stop", "pause", "end") else None
        if st == "end" or (self.player.duration and at is not None and at >= self.player.duration - 0.3):
            at = 0.0
        self.player.play(w, h, at=at)
        if self.player.last_error:
            self.log(f"Lecteur : {self.player.last_error}", "warning")
        self.status.set(f"▶ Lecture intégrée : {os.path.basename(self._player_media)}")

    def player_stop(self):
        if self.player.state != "stop":
            self.player.stop()
        self.pos_var.set(0.0)
        self._on_player_update(0.0, self.player.duration or float(self.pos_scale.cget("to") or 0), "stop")
        self._render_thumb()

    def player_skip(self, delta: float):
        if not self._integrated_ok():
            return
        if not self._ensure_loaded():
            return
        cur = self.player.current() if self.player.state == "play" else float(self.pos_var.get())
        w, h = self._thumb_box()
        self.player.seek(max(0.0, cur + delta), w, h)

    def player_seek_to(self, t: float, play: bool = True):
        """Utilisé par la transcription (clic sur un horodatage)."""
        if not self._integrated_ok():
            self.status.set(f"Horodatage {fmt_ts(t)} — lecteur intégré indisponible.")
            return
        if not self._ensure_loaded():
            return
        w, h = self._thumb_box()
        self.pscroll.to_top()
        if play:
            self.player.play(w, h, at=t)
        else:
            self.player.seek(t, w, h)

    def _scale_value_at(self, x: int) -> float:
        wpx = max(1, self.pos_scale.winfo_width() - 16)
        frac = min(1.0, max(0.0, (x - 8) / float(wpx)))
        return frac * float(self.pos_scale.cget("to") or 1)

    def _seek_press(self, e):
        if not self._integrated_ok():
            return "break"
        self._seek_drag = True
        self.pos_var.set(self._scale_value_at(e.x))
        self._show_time(float(self.pos_var.get()))
        return "break"

    def _seek_motion(self, e):
        if self._seek_drag:
            self.pos_var.set(self._scale_value_at(e.x))
            self._show_time(float(self.pos_var.get()))
        return "break"

    def _seek_release(self, e):
        if not self._seek_drag:
            return "break"
        self._seek_drag = False
        t = self._scale_value_at(e.x)
        if self._ensure_loaded():
            w, h = self._thumb_box()
            self.player.seek(t, w, h)
        return "break"

    def _show_time(self, pos: float):
        dur = self.player.duration or float(self.pos_scale.cget("to") or 0)
        self.pl_time.configure(text=f"{fmt_ts(pos)} / {fmt_ts(dur) if dur else '—'}")

    def _on_player_update(self, pos: float, dur: float, state: str):
        if not self._seek_drag:
            self.pos_var.set(pos)
            self._show_time(pos)
        self.pl_play.configure(text="⏸ Pause" if state == "play" else "▶ Lecture")
        self._tr_follow(pos)

    def player_bigwin(self):
        """Grande fenêtre ffplay (redimensionnable) à la position courante."""
        main = self._player_media or (find_main_media(self._preview_path) if self._preview_path else None)
        if not main or not main.lower().endswith(VIDEO_EXTS):
            return
        fpl = find_ffplay()
        if not fpl:
            self.open_selected_media()
            return
        pos = self.player.current() if self.player.state == "play" else float(self.pos_var.get() or 0)
        if self.player.state == "play":
            self.player.pause()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w = min(1280, int(sw * 0.7))
        h = int(w * 9 / 16)
        title = f"{APP_NAME} — {str(self._preview_info.get('title') or os.path.basename(main))[:80]}"
        cmd = [fpl, "-hide_banner", "-loglevel", "error", "-autoexit", "-window_title", title,
               "-x", str(w), "-y", str(h), "-volume", str(0 if self._muted else int(float(self.vol_var.get())))]
        if pos > 0.5:
            cmd += ["-ss", f"{pos:.2f}"]
        cmd.append(main)
        try:
            kw: Dict[str, Any] = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
                                  "stderr": subprocess.DEVNULL, "close_fds": True}
            if sys.platform.startswith("win"):
                kw["creationflags"] = CREATE_NO_WINDOW  # pas de console ; la fenêtre vidéo reste visible
            subprocess.Popen(cmd, **kw)
            self.status.set("⛶ Grande fenêtre ouverte (F = plein écran, Espace = pause, Échap = fermer).")
        except Exception as ex:
            logger.exception("ffplay fenêtre")
            messagebox.showerror(APP_NAME, f"Impossible d'ouvrir la fenêtre vidéo :\n{ex}", parent=self)

    def _on_thumb_click(self):
        if not self._preview_entry:
            return
        if self._player_media and self._integrated_ok():
            self.player_toggle()
        else:
            self.open_selected_media()

    # ------------------------------------------------------------ v5 : transcription
    def _build_transcript_box(self, body):
        box = tk.Frame(body, bg=NC_BG)
        self.tr_box = box
        self.tr_title = self._section(box, "🗣 Transcription")
        bar = FlowFrame(box)
        bar.pack(fill="x", padx=8)
        self.tr_bar = bar
        g = tk.Frame(bar, bg=NC_BG)
        tk.Label(g, text="🔎", bg=NC_BG, fg=NC_FG, font=FONT_SM).pack(side="left")
        self.tr_search = tk.StringVar()
        ent = tk.Entry(g, textvariable=self.tr_search, width=24, bg=NC_ENTRY_BG, fg=NC_ENTRY_FG,
                       insertbackground=NC_FG, font=FONT_SM)
        ent.pack(side="left", padx=3)
        ent.bind("<Return>", lambda e: (self._tr_find_next(), "break")[1])
        self.tr_entry = ent
        self.tr_search.trace_add("write", lambda *_: self._tr_schedule_hl())
        bar.add(g, "Chercher dans la transcription (Entrée = occurrence suivante)")
        self.tr_count = tk.Label(bar, text="", bg=NC_BG, fg=NC_DIM, font=FONT_SM)
        bar.add(self.tr_count)
        self._tr_btns: Dict[str, Any] = {}
        for key, txt, cmd, tip in (
            ("next", "⬇ Suivant", self._tr_find_next, "Occurrence suivante"),
            ("copy", "📋 Copier", self._tr_copy, "Copier toute la transcription (avec horodatages)"),
            ("open", "📄 transcript.txt", self._tr_open, "Ouvrir le fichier texte de la transcription"),
        ):
            self._tr_btns[key] = bar.add(self._btn(bar, txt, cmd), tip)
        self._tr_btns["whisper"] = bar.add(self._btn(bar, "🎙 Transcrire (local)", self.transcribe_selected))
        self._whisper_tip = Tooltip(self._tr_btns["whisper"], "")
        trf, self.tr_text = self._scrolled_text(box, height=8, bg=NC_PANEL, fg=NC_TEXT, font=FONT_TEXT)
        trf.pack(fill="x", padx=8, pady=(3, 0))
        self.tr_frame = trf
        t = self.tr_text
        t.configure(state="disabled", cursor="xterm", padx=8, pady=6, spacing1=1, spacing3=2)
        t.tag_configure("ts", foreground=NC_HI, underline=True)
        t.tag_configure("cur", background=NC_CARD)
        t.tag_configure("hit", background=NC_SEL, foreground=NC_ON_SEL)
        t.tag_configure("hitcur", background=NC_HI, foreground=NC_ON_HI)
        t.tag_raise("hit")
        t.tag_raise("hitcur")
        t.tag_bind("ts", "<Enter>", lambda e: t.configure(cursor="hand2"))
        t.tag_bind("ts", "<Leave>", lambda e: t.configure(cursor="xterm"))
        t.bind("<Button-1>", lambda e: t.focus_set())
        t.bind("<Button-3>", self._tr_menu_popup)
        self._tr_menu = self._menu()
        self._tr_menu.add_command(label="Copier la sélection", command=lambda: self._text_copy_sel(self.tr_text))
        self._tr_menu.add_command(label="Copier toute la transcription", command=self._tr_copy)
        self.tr_msg = tk.Label(box, text="", bg=NC_BG, fg=NC_DIM, font=FONT_SM, anchor="w", justify="left")
        self.tr_msg.pack(fill="x", padx=8)
        self._tr_cues: List[Tuple[float, str]] = []
        self._tr_starts: List[float] = []
        self._tr_hits: List[str] = []
        self._tr_hit_i = -1
        self._tr_hl_job = None

    def _text_copy_sel(self, w):
        try:
            self._copy_to_clipboard(w.get("sel.first", "sel.last"))
        except tk.TclError:
            pass

    def _tr_menu_popup(self, event):
        try:
            self._tr_menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                self._tr_menu.grab_release()
            except Exception:
                pass
        return "break"

    def _render_transcript(self, path: str, main: Optional[str]):
        self._tr_cues, self._tr_starts, self._tr_hits, self._tr_hit_i, self._tr_cur = [], [], [], -1, -1
        d: Dict[str, Any] = {}
        if path and os.path.isdir(path):
            try:
                d = load_transcript(path)
            except Exception:
                logger.exception("transcription")
                d = {}
        cues = list(d.get("cues") or [])
        if not cues and not main:
            self.tr_box.pack_forget()
            return
        self.tr_box.pack(fill="x", after=self._tr_anchor)
        self._tr_cues = cues
        self._tr_starts = [c[0] for c in cues]
        if cues and self._preview_entry is not None and not self._preview_entry.get("has_transcript"):
            self._preview_entry["has_transcript"] = True
        t = self.tr_text
        t.configure(state="normal")
        t.delete("1.0", "end")
        for tag in t.tag_names():
            if tag.startswith("tsc_"):
                t.tag_delete(tag)
        wbtn = self._tr_btns["whisper"]
        has_w = whisper_available()
        if cues:
            src = str(d.get("source") or "sous-titres")
            lang = str(d.get("lang") or "?")
            self.tr_title.configure(text=f"🗣 Transcription ({len(cues)} passages · {src} · langue : {lang})")
            for i, (ts, txt) in enumerate(cues):
                tg = f"tsc_{i}"
                t.insert("end", f"[{fmt_ts(ts)}]", ("ts", tg))
                t.insert("end", f"  {txt}\n", (f"line_{i}",))
                t.tag_bind(tg, "<Button-1>", lambda e, s=ts: (self.player_seek_to(s), "break")[1])
            self.tr_msg.configure(text="Clic sur un horodatage [m:ss] = lire la vidéo à cet endroit · "
                                       "le passage en cours est surligné pendant la lecture")
            t.configure(height=max(4, min(14, len(cues) + 1)))
            self.tr_frame.pack(fill="x", padx=8, pady=(3, 0), before=self.tr_msg)
        else:
            self.tr_title.configure(text="🗣 Transcription")
            self.tr_frame.pack_forget()
            if has_w:
                msg = ("Aucune transcription (pas de sous-titres pour ce média). "
                       "« 🎙 Transcrire (local) » la crée sur ce PC avec Whisper, sans envoyer le son en ligne.")
            else:
                msg = ("Aucune transcription : ce média n'a pas de sous-titres. Les vidéos avec sous-titres "
                       "(YouTube…) sont transcrites automatiquement. Pour transcrire les autres, installer "
                       "faster-whisper (setup_padawan.bat, option Whisper).")
            self.tr_msg.configure(text=msg)
        t.configure(state="disabled")
        for k in ("next", "copy", "open"):
            self.tr_bar.set_visible(self._tr_btns[k], bool(cues))
        self.tr_bar.set_visible(self.tr_entry.master, bool(cues))
        self.tr_bar.set_visible(self.tr_count, bool(cues))
        self.tr_bar.set_visible(wbtn, bool(main))
        busy = any(j.get("kind") == "whisper" and j.get("folder") == os.path.basename(path)
                   and j["status"] in ("attente", "cours") for j in self.jobs)
        if not has_w:
            wbtn.configure(state="disabled", text="🎙 Transcrire (local)")
            self._whisper_tip.text = ("Transcription locale avec Whisper — module faster-whisper non installé.\n"
                                      "Lance setup_padawan.bat et réponds O à « Whisper » (≈ 200 Mo), puis relance.")
        elif busy:
            wbtn.configure(state="disabled", text="🎙 Transcription en cours…")
            self._whisper_tip.text = "Transcription dans la file d'attente."
        else:
            wbtn.configure(state="normal", text="🎙 Retranscrire (local)" if cues else "🎙 Transcrire (local)")
            self._whisper_tip.text = (f"Transcrire le son sur ce PC (Whisper « {self.cfg.get('whisper_model', 'base')} », "
                                      "aucun envoi en ligne). Peut prendre plusieurs minutes ; annulable dans la file.")
        if self.tr_search.get():
            self._tr_highlight()
        else:
            self.tr_count.configure(text="")

    def _tr_schedule_hl(self):
        if self._tr_hl_job:
            try:
                self.after_cancel(self._tr_hl_job)
            except Exception:
                pass
        self._tr_hl_job = self.after(180, self._tr_highlight)

    def _tr_highlight(self):
        self._tr_hl_job = None
        t = self.tr_text
        t.tag_remove("hit", "1.0", "end")
        t.tag_remove("hitcur", "1.0", "end")
        q = self.tr_search.get().strip()
        self._tr_hits, self._tr_hit_i = [], -1
        if not q or not self._tr_cues:
            self.tr_count.configure(text="")
            return
        idx = "1.0"
        n = 0
        while n < 2000:
            pos = t.search(q, idx, nocase=True, stopindex="end")
            if not pos:
                break
            end = f"{pos}+{len(q)}c"
            t.tag_add("hit", pos, end)
            self._tr_hits.append(pos)
            idx = end
            n += 1
        self.tr_count.configure(text=f"{n} résultat{'s' if n > 1 else ''}" if n else "aucun résultat",
                                fg=NC_FG if n else NC_ERR)
        if n:
            self._tr_find_next()

    def _tr_find_next(self):
        if not self._tr_hits:
            return
        t = self.tr_text
        self._tr_hit_i = (self._tr_hit_i + 1) % len(self._tr_hits)
        pos = self._tr_hits[self._tr_hit_i]
        t.tag_remove("hitcur", "1.0", "end")
        t.tag_add("hitcur", pos, f"{pos}+{len(self.tr_search.get().strip())}c")
        t.see(pos)
        self.tr_count.configure(text=f"{self._tr_hit_i + 1} / {len(self._tr_hits)}")

    def _tr_follow(self, pos: float):
        if not self._tr_starts:
            return
        import bisect
        i = bisect.bisect_right(self._tr_starts, pos + 0.05) - 1
        if i == self._tr_cur:
            return
        t = self.tr_text
        t.tag_remove("cur", "1.0", "end")
        self._tr_cur = i
        if i >= 0:
            t.tag_add("cur", f"{i + 1}.0", f"{i + 1}.end")
            t.see(f"{i + 1}.0")

    def _tr_copy(self):
        if self._tr_cues:
            self._copy_to_clipboard("\n".join(f"[{fmt_ts(ts)}] {x}" for ts, x in self._tr_cues))

    def _tr_open(self):
        p = os.path.join(self._preview_path, TRANSCRIPT_TXT) if self._preview_path else ""
        if p and os.path.isfile(p):
            self.open_path_safe(p, "fichier")

    def transcribe_selected(self):
        e = self._preview_entry
        path = self._preview_path
        if not e or not path or not find_main_media(path):
            return
        if not whisper_available():
            messagebox.showinfo(APP_NAME, "La transcription locale utilise Whisper (module faster-whisper), "
                                "qui n'est pas installé.\n\nLance setup_padawan.bat et réponds O à la question "
                                "« Whisper », puis relance l'Archiveur.", parent=self)
            return
        if load_transcript(path).get("cues") and not messagebox.askyesno(
                APP_NAME, "Cette archive a déjà une transcription.\nLa refaire avec Whisper (remplace l'actuelle) ?",
                parent=self):
            return
        folder = str(e.get("folder"))
        self._enqueue_task("whisper", folder, f"🎙 Transcription : {e.get('title') or folder}")
        self._render_transcript(path, find_main_media(path))

    def _enqueue_task(self, kind: str, folder: str, title: str) -> bool:
        key = f"{kind}:{folder}"
        if key in self._active_keys():
            self.status.set("Déjà dans la file d'attente.")
            return False
        opts = self._job_opts()
        start = False
        with self._jobs_lock:
            self._job_seq += 1
            self.jobs.append({"id": self._job_seq, "kind": kind, "key": key, "url": title, "status": "attente",
                              "pct": 0.0, "title": title, "folder": folder, "error": "", "detail": "",
                              "opts": dict(opts)})
            if not self._worker_running:
                self._worker_running = True
                start = True
        self._refresh_queue_view()
        self._show_bottom("queue", auto=True)
        if start:
            threading.Thread(target=self._worker, daemon=True).start()
        return True

    def _run_whisper_job(self, job):
        o = job["opts"]
        fp = os.path.join(o["root"], job["folder"])

        def prog(p):
            job["pct"] = p
            job["detail"] = f"🎙 {p:.0f} %"
            self.ui(lambda: self._job_changed(job))
        try:
            job["detail"] = "Chargement du modèle Whisper…"
            self.ui(lambda: self._job_changed(job))
            d = transcribe_whisper(fp, self.log, model_size=str(self.cfg.get("whisper_model") or "base"),
                                   progress=prog, cancel_event=self._cancel_event)
            refresh_entries(o["root"], [job["folder"]])
            job.update(status="ok", pct=100.0, detail=f"{len(d.get('cues') or [])} passages")
            self._run_stats["ok"] += 1
            self._run_stats["last_title"] = job["title"]
            self.log(f"🎙 Transcription terminée : {len(d.get('cues') or [])} passages ({d.get('lang') or '?'}).")
            self.ui(lambda f=job["folder"]: self._after_task(f))
        except ArchiveCancelled:
            job.update(status="annule", detail="")
            self._run_stats["annule"] += 1
        except Exception as e:
            logger.exception("whisper %s", job["folder"])
            job.update(status="echec", error=friendly_error(e), detail="")
            self._run_stats["echec"] += 1
            self.log(f"❌ Transcription : {friendly_error(e)}", "error")

    def _after_task(self, folder: str):
        self.entries = load_archive_index(self.archive_root_path())
        self.apply_filter()
        if self._preview_entry and self._preview_entry.get("folder") == folder:
            self._preview_entry = next((x for x in self.entries if x.get("folder") == folder), self._preview_entry)
            main = find_main_media(self._preview_path)
            self._render_transcript(self._preview_path, main)
            self._render_extracts(self._preview_path, main)
            self._render_files()

    # ------------------------------------------------------------ v5 : extraits et captures
    def _build_extracts_box(self, body):
        box = tk.Frame(body, bg=NC_BG)
        self.ex_box = box
        self.ex_title = self._section(box, "✂ Extraits et captures")
        bar = FlowFrame(box)
        bar.pack(fill="x", padx=8)
        bar.add(self._btn(bar, "✂ Outils média…", self.open_media_tools, hi=True),
                "Créer une capture d'image, un extrait vidéo, un MP3 ou un GIF à partir de cette archive")
        self.ex_open = bar.add(self._btn(bar, "📁 Dossier extraits", self._open_extracts_dir),
                               "Ouvrir le sous-dossier extraits/ de l'archive")
        self.ex_bar = bar
        self.ex_flow = FlowFrame(box, padx=6, pady=6)
        self.ex_flow.pack(fill="x", padx=8, pady=(4, 0))
        self.ex_msg = tk.Label(box, text="", bg=NC_BG, fg=NC_DIM, font=FONT_SM, anchor="w", justify="left")
        self.ex_msg.pack(fill="x", padx=8)
        self._ex_photos: List[Any] = []

    def _open_extracts_dir(self):
        d = os.path.join(self._preview_path, EXTRACTS_DIR) if self._preview_path else ""
        if d and os.path.isdir(d):
            self.open_path_safe(d, "dossier")

    def _render_extracts(self, path: str, main: Optional[str]):
        for w in list(self.ex_flow._items):
            try:
                w.destroy()
            except Exception:
                pass
        self.ex_flow._items = []
        self.ex_flow.configure(height=1)
        self._ex_photos = []
        files = list_extracts(path) if path and os.path.isdir(path) else []
        if not main and not files:
            self.ex_box.pack_forget()
            return
        self.ex_box.pack(fill="x", after=self._ex_anchor)
        n = len(files)
        self.ex_title.configure(text=f"✂ Extraits et captures ({n})" if n else "✂ Extraits et captures")
        self.ex_bar.set_visible(self.ex_open, bool(n))
        if not n:
            self.ex_msg.configure(text="Aucun extrait pour l'instant. Astuce : mets la vidéo en pause à l'endroit "
                                       "voulu, puis « ✂ Outils média » → « = position du lecteur ».")
        else:
            self.ex_msg.configure(text="Clic = ouvrir · clic droit = copier le chemin / afficher dans le dossier")
        for p in files[:40]:
            name = os.path.basename(p)
            cell = tk.Frame(self.ex_flow, bg=NC_PANEL, bd=1, relief="solid", cursor="hand2")
            low = name.lower()
            ph = None
            if HAS_PIL and low.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
                try:
                    im = Image.open(p)
                    im.thumbnail((150, 100))
                    ph = ImageTk.PhotoImage(im.convert("RGB"))
                except Exception:
                    ph = None
            if ph is not None:
                self._ex_photos.append(ph)
                tk.Label(cell, image=ph, bg=NC_PANEL).pack(padx=3, pady=(3, 0))
            else:
                tk.Label(cell, text=file_icon(name), bg=NC_PANEL, fg=NC_HI, font=FONT_BIG, width=4).pack(padx=3, pady=(6, 0))
            short = wrap_name(name, 24)
            try:
                sz = human_size(os.path.getsize(p))
            except OSError:
                sz = ""
            tk.Label(cell, text=f"{short}\n{sz}", bg=NC_PANEL, fg=NC_FG, font=FONT_SM, justify="center").pack(padx=4, pady=(0, 3))
            for wdg in [cell] + list(cell.winfo_children()):
                wdg.bind("<Button-1>", lambda e, pp=p: self._open_media(pp, "fichier"))
                wdg.bind("<Button-3>", lambda e, pp=p: self._show_link_menu(e, "path", pp))
            self.ex_flow.add(cell, name)
        self.ex_flow.after_idle(self.ex_flow.relayout)

    # ------------------------------------------------------------ v5 : documents d'une page web
    def _render_docs(self, path: str, info: Dict[str, Any]):
        for w in list(self.doc_flow._items):
            try:
                w.destroy()
            except Exception:
                pass
        self.doc_flow._items = []
        docs = []
        if path and os.path.isdir(path):
            for fname, label, tip in (
                ("lecture.html", "📖 Lecture", "Texte de l'article, mise en page lisible (hors ligne)"),
                ("page.html", "🌐 Page complète", "Copie autonome de la page (images locales, sans scripts)"),
                (str(info.get("page_pdf") or "page_complete.pdf"), "📑 PDF", "Page imprimée en PDF (Edge/Chrome)"),
                (str(info.get("page_capture") or "capture_page.png"), "🖼 Capture", "Capture d'écran de la page entière"),
                ("article.txt", "📝 Texte brut", "Texte de l'article (.txt)"),
            ):
                fp = os.path.join(path, fname)
                if fname and os.path.isfile(fp):
                    docs.append((fp, label, tip))
        if not docs:
            self.doc_box.pack_forget()
            return
        words = info.get("words")
        try:
            wtxt = f" ({int(words):,} mots)".replace(",", "\u202f") if words else ""
        except (TypeError, ValueError):
            wtxt = ""
        lab = tk.Label(self.doc_flow, text=f"📰 Page web archivée{wtxt} :", bg=NC_BG, fg=NC_HI, font=FONT_SM)
        self.doc_flow.add(lab)
        for fp, label, tip in docs:
            self.doc_flow.add(self._btn(self.doc_flow, label, lambda p=fp: self._open_doc(p)), tip)
        self.doc_box.pack(fill="x", after=self._doc_anchor)
        self.doc_flow.after_idle(self.doc_flow.relayout)

    def _open_doc(self, p: str):
        if p.lower().endswith((".html", ".htm")):
            self._open_url(p)
        else:
            self.open_path_safe(p, "fichier")

    def _online_text(self, info: Dict[str, Any]) -> str:
        st = str(info.get("online_status") or "")
        if not st:
            return "jamais vérifié — clic pour vérifier"
        ic, lab = GUI_ONLINE.get(st, ("?", st))
        txt = f"{ic} {lab}"
        det = str(info.get("online_detail") or "")
        when = fmt_iso(info.get("online_checked")) if info.get("online_checked") else ""
        if det:
            txt += f" ({det})"
        if when:
            txt += f" · vérifié le {when}"
        return txt

    def _sb_show(self, show: bool):
        parts = (self.sb_title, self.sb_title._line, self.sb_row, self.sb_msg)
        if show:
            if not self.sb_title.winfo_manager():
                prev = self._sb_anchor
                for w, kw in zip(parts, (dict(padx=8, pady=(12, 2)), dict(padx=8, pady=(0, 4)),
                                         dict(padx=8), dict(padx=8))):
                    w.pack(fill="x", after=prev, **kw)
                    prev = w
        else:
            for w in parts:
                w.pack_forget()

    def _collections_text(self, info: Dict[str, Any]) -> str:
        parts = []
        if info.get("favorite"):
            parts.append("★ Favori")
        cols = [c for c in (info.get("collections") or []) if isinstance(c, str)]
        if cols:
            parts.append(", ".join(cols))
        return " · ".join(parts) if parts else "— (clic pour classer)"

    def _refresh_preview_meta(self):
        """Met à jour favori / collections / en ligne de l'aperçu sans tout redessiner."""
        e = self._preview_entry
        if not e or not self._preview_path:
            return
        folder = e.get("folder")
        fresh = next((x for x in self.entries if x.get("folder") == folder), None)
        if fresh is not None:
            self._preview_entry = fresh
        info = load_info(self._preview_path)
        for k in ("favorite", "collections", "online_status", "online_detail", "online_checked", "tags"):
            self._preview_info[k] = info.get(k)
        self._set_card("online", self._online_text(self._preview_info), ("action", "online"))
        self._set_card("collections", self._collections_text(self._preview_info), ("action", "collections"))
        self._preview_info[COLL_SUGGEST_OFF] = info.get(COLL_SUGGEST_OFF)
        self._update_fav_button()
        self._update_suggest_banner()

    def _update_fav_button(self):
        b = self._act_btns.get("fav")
        if not b:
            return
        fav = bool(self._preview_info.get("favorite")) if self._preview_entry else False
        b.configure(text="★ Favori" if fav else "☆ Favori",
                    bg=NC_SEL if fav else NC_BTN, fg=NC_ON_SEL if fav else NC_BTN_FG)

    # ------------------------------------------------------------ v5 : sélection multiple / menus
    def _post_menu(self, widget, menu):
        try:
            x, y = widget.winfo_rootx(), widget.winfo_rooty() + widget.winfo_height()
            menu.tk_popup(x, y)
        finally:
            try:
                menu.grab_release()
            except Exception:
                pass

    def _tree_hover(self, event):
        iid = self.tree.identify_row(event.y)
        if iid and iid != getattr(self, "_hover_iid", None):
            self._hover_iid = iid
            e = self._iid_entry.get(iid)
            if e:
                self.status.set(f"{platform_label(e.get('platform'))} · {e.get('title') or e.get('folder')}"[:220])

    def _selected_entries(self) -> List[Dict[str, Any]]:
        out = [self._iid_entry[i] for i in self.tree.selection() if i in self._iid_entry]
        if not out and self._preview_entry:
            out = [self._preview_entry]
        return out

    def _selected_folders(self) -> List[str]:
        return [str(e.get("folder")) for e in self._selected_entries() if e.get("folder")]

    def _tree_select_all(self, _e=None):
        items = self.tree.get_children()
        if items:
            self._suppress_select = True
            self.tree.selection_set(items)
            self.after(10, lambda: setattr(self, "_suppress_select", False))
            self.status.set(f"{len(items)} archives sélectionnées — clic droit pour les actions groupées.")
            self._update_states()
        return "break"

    def _refresh_filter_values(self):
        plats = sorted({str(e.get("platform") or "web") for e in self.entries})
        self._plat_map = {PLAT_ALL_LABEL: ""}
        for p in plats:
            n = sum(1 for e in self.entries if str(e.get("platform") or "web") == p)
            self._plat_map[f"{platform_label(p)} ({n})"] = p
        cur = getattr(self, "_plat_map_prev", {}).get(self.plat_var.get(), "")
        self.plat_cb.configure(values=list(self._plat_map.keys()))
        self.plat_var.set(next((k for k, v in self._plat_map.items() if v == cur), PLAT_ALL_LABEL))
        self._plat_map_prev = dict(self._plat_map)
        cmap: Dict[str, str] = {COLL_ALL_LABEL: ""}
        nfav = sum(1 for e in self.entries if e.get("favorite"))
        ntr = sum(1 for e in self.entries if e.get("has_transcript"))
        noff = sum(1 for e in self.entries if e.get("online_status") in ("offline", "restricted"))
        nnone = sum(1 for e in self.entries if not e.get("collections"))
        for lab, key, n in (("★ Favoris", COLL_FAV, nfav), ("🗣 Avec transcription", COLL_TRANSCRIPT, ntr),
                            ("⚠ Plus en ligne", COLL_OFFLINE, noff), ("📥 Non classées", COLL_NONE, nnone)):
            cmap[f"{lab} ({n})"] = key
        counts: Dict[str, int] = {}
        for e in self.entries:
            for c in e.get("collections") or []:
                counts[c.lower()] = counts.get(c.lower(), 0) + 1
        for c in load_collections(self.archive_root_path(), self.entries):
            cmap[f"📚 {c} ({counts.get(c.lower(), 0)})"] = c
        cur_key = self._coll_map.get(self.coll_var.get(), self.cfg.get("collection_filter") or "")
        self._coll_map = cmap
        self.coll_cb.configure(values=list(cmap.keys()))
        lab = next((k for k, v in cmap.items() if v == cur_key), COLL_ALL_LABEL)
        self.coll_var.set(lab)
        self._fill_coll_side(counts, nnone, nfav)

    def _coll_key(self) -> str:
        return self._coll_map.get(self.coll_var.get(), "")

    def _on_coll_filter(self):
        self.cfg["collection_filter"] = self._coll_key()
        save_cfg(self.cfg)
        self._sync_coll_side()
        self.apply_filter()

    # ---------------------------------------------------------------- barre des collections (classement simple)
    def _fill_coll_side(self, counts: Dict[str, int], nnone: int, nfav: int):
        t = getattr(self, "coll_tree", None)
        if t is None:
            return
        self._coll_side_lock = True
        try:
            t.delete(*t.get_children())
            t.insert("", "end", iid="c::", text=f" 🗂 Toutes ({len(self.entries)})")
            t.insert("", "end", iid="c::" + COLL_NONE, text=f" 📥 Non classées ({nnone})",
                     tags=() if nnone else ("dim",))
            t.insert("", "end", iid="c::" + COLL_FAV, text=f" ★ Favoris ({nfav})", tags=() if nfav else ("dim",))
            for c in load_collections(self.archive_root_path(), self.entries):
                n = counts.get(c.lower(), 0)
                t.insert("", "end", iid="c::" + c, text=f" 📚 {c} ({n})", tags=() if n else ("dim",))
        except Exception:
            logger.exception("barre collections")
        finally:
            self._coll_side_lock = False
        self._sync_coll_side()

    def _sync_coll_side(self):
        t = getattr(self, "coll_tree", None)
        if t is None:
            return
        iid = "c::" + self._coll_key()
        self._coll_side_lock = True
        try:
            if t.exists(iid):
                if t.selection() != (iid,):
                    t.selection_set(iid)
                t.see(iid)
            else:
                t.selection_remove(*t.selection())
        except Exception:
            pass
        finally:
            self.after(10, lambda: setattr(self, "_coll_side_lock", False))

    def _on_coll_side(self, _e=None):
        if self._coll_side_lock:
            return
        sel = self.coll_tree.selection()
        if not sel:
            return
        key = sel[0][3:]
        lab = next((k for k, v in self._coll_map.items() if v == key), None)
        if lab is None or self.coll_var.get() == lab:
            return
        self.coll_var.set(lab)
        self._on_coll_filter()

    def _coll_side_menu(self, event):
        iid = self.coll_tree.identify_row(event.y)
        name = iid[3:] if iid and iid.startswith("c::") else ""
        m = self._menu()
        m.add_command(label="➕ Nouvelle collection…", command=self.new_collection)
        m.add_command(label="✨ Ranger tout automatiquement…", command=self.auto_classify)
        if self._auto_undo:
            m.add_command(label="↩ Annuler le dernier rangement automatique", command=self.undo_auto_classify)
        if name and not name.startswith("__"):
            m.add_separator()
            m.add_command(label=f"✏ Renommer « {name} »…", command=lambda: self.rename_collection(name))
            m.add_command(label=f"🗑 Supprimer « {name} » (les archives restent)",
                          command=lambda: self.delete_collection(name))
        try:
            m.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                m.grab_release()
            except Exception:
                pass
        return "break"

    def _toggle_coll_side(self):
        if self._coll_side.winfo_manager():
            self._coll_side.pack_forget()
            self._side_toggle.configure(text="▶ 📚")
        else:
            self._coll_side.pack(side="left", fill="y", padx=(0, 6), pady=(2, 4), before=self._hist_main)
            self._side_toggle.configure(text="◀")

    def rename_collection(self, name: str):
        new = self._ask_string(f"Nouveau nom pour la collection « {name} » :", initial=name, parent=self)
        new = re.sub(r"\s+", " ", (new or "")).strip()[:40]
        if not new or new == name:
            return
        root = self.archive_root_path()
        members = [str(e.get("folder")) for e in self.entries
                   if name.lower() in {c.lower() for c in (e.get("collections") or [])}]
        try:
            backup_index(root, min_interval=0)
            names = [n for n in load_collections(root, self.entries) if n.lower() != name.lower()]
            if new.lower() not in {n.lower() for n in names}:
                names.append(new)
            save_collections(root, names)
            for f in members:
                info = load_info(os.path.join(root, f))
                cols = [c for c in (info.get("collections") or []) if isinstance(c, str) and c.lower() != name.lower()]
                if new.lower() not in {c.lower() for c in cols}:
                    cols.append(new)
                update_info_fields(root, f, save_index=False, collections=cols)
            refresh_entries(root, members)
        except Exception as ex:
            logger.exception("renommer collection")
            messagebox.showerror(APP_NAME, f"Renommage impossible :\n{friendly_error(ex)}", parent=self)
        if self._coll_key().lower() == name.lower():
            self.cfg["collection_filter"] = new
        self.log(f"✏ Collection « {name} » → « {new} » ({len(members)} archive(s))")
        self._reload_entries()
        if self.cfg.get("collection_filter") == new:
            lab = next((k for k, v in self._coll_map.items() if v == new), COLL_ALL_LABEL)
            self.coll_var.set(lab)
            self._on_coll_filter()

    def _build_move_menu(self, parent=None):
        """Menu « Déplacer vers » : l'archive (ou la sélection) va dans UNE collection."""
        m = tk.Menu(parent or self, tearoff=0, bg=NC_PANEL, fg=NC_FG, activebackground=NC_SEL,
                    activeforeground=NC_ON_SEL, font=FONT_UI)
        names = load_collections(self.archive_root_path(), self.entries)
        sug = self._sug[1] if self._sug and len(self._selected_folders()) <= 1 else ""
        if sug and sug.lower() not in {n.lower() for n in names}:
            m.add_command(label=f"✨ {sug} (nouvelle, proposée)", command=lambda: self.move_selected_to(sug))
        for c in names:
            m.add_command(label=f"📚 {c}", command=lambda cc=c: self.move_selected_to(cc))
        if names or sug:
            m.add_separator()
        m.add_command(label="➕ Nouvelle collection…", command=self._move_to_new)
        m.add_command(label="📥 Non classée (retirer des collections)", command=lambda: self.move_selected_to(None))
        return m

    def _move_to_new(self):
        name = self._ask_string("Nom de la nouvelle collection :\n(ex. Animatrix, Santé, Musique, À revoir)",
                                parent=self)
        name = re.sub(r"\s+", " ", (name or "")).strip()[:40]
        if name:
            self.move_selected_to(name)

    def move_selected_to(self, name: Optional[str], folders: Optional[List[str]] = None):
        folders = folders or self._selected_folders()
        if not folders:
            return
        root = self.archive_root_path()
        try:
            if name:
                names = load_collections(root, self.entries)
                hit = next((n for n in names if n.lower() == name.lower()), None)
                if hit:
                    name = hit
                else:
                    save_collections(root, names + [name])
            n = move_to_collection(root, folders, name)
        except Exception as ex:
            logger.exception("déplacer collection")
            messagebox.showerror(APP_NAME, f"Classement impossible :\n{friendly_error(ex)}", parent=self)
            return
        msg = (f"📚 Rangé dans « {name} »" if name else "📥 Remis dans « Non classées »") + (f" ({n} archives)" if n > 1 else "")
        self.status.set(msg)
        self.log(msg)
        self._reload_entries()

    # ---------------------------------------------------------------- suggestion « Ranger dans X ? »
    def _hide_suggest_banner(self):
        self._sug = None
        try:
            self.sug_banner.pack_forget()
        except Exception:
            pass

    def _update_suggest_banner(self):
        e = self._preview_entry
        info = self._preview_info or {}
        if not e or not e.get("folder") or info.get("collections") or info.get(COLL_SUGGEST_OFF):
            self._hide_suggest_banner()
            return
        try:
            names = load_collections(self.archive_root_path(), self.entries)
            sug = suggest_collection(e, self.entries, names, info)
        except Exception:
            logger.exception("suggestion collection")
            sug = None
        if not sug:
            self._hide_suggest_banner()
            return
        self._sug = (str(e.get("folder")), sug[0])
        self.sug_msg.configure(text=f"📚 Ranger dans « {sug[0]} » ?   ({sug[1]})",
                               wraplength=max(200, self._preview_width() - 260))
        if not self.sug_banner.winfo_manager():
            self.sug_banner.pack(fill="x", padx=6, pady=(0, 4), before=self.pscroll)

    def _sug_accept(self):
        if not self._sug:
            return
        folder, name = self._sug
        self.move_selected_to(name, folders=[folder])

    def _sug_dismiss(self):
        if not self._sug:
            return
        folder, name = self._sug
        try:
            update_info_fields(self.archive_root_path(), folder, save_index=False, **{COLL_SUGGEST_OFF: name})
            self._preview_info[COLL_SUGGEST_OFF] = name
        except Exception:
            logger.exception("suggestion refusée")
        self._hide_suggest_banner()
        self.status.set("D'accord — je ne propose plus de collection pour cette archive.")

    # ---------------------------------------------------------------- « Ranger tout automatiquement »
    def auto_classify(self):
        root = self.archive_root_path()
        names = load_collections(root, self.entries)
        self.status.set("✨ Je regarde les archives non classées…")
        self.update_idletasks()
        try:
            plan = plan_auto_collections(self.entries, names, root)
        except Exception as ex:
            logger.exception("plan rangement")
            messagebox.showerror(APP_NAME, f"Rangement impossible :\n{friendly_error(ex)}", parent=self)
            return
        nonclass = sum(1 for e in self.entries if not e.get("collections"))
        if not plan:
            self.status.set("Rien à ranger automatiquement.")
            messagebox.showinfo(APP_NAME, ("Toutes tes archives sont déjà classées. 👍" if not nonclass else
                                           f"{nonclass} archive(s) non classée(s), mais je n'ai pas d'idée sûre "
                                           "pour elles.\n\nClic droit sur une archive → 📂 Déplacer vers la "
                                           "collection… pour la ranger toi-même."), parent=self)
            return
        title_of = {str(e.get("folder")): str(e.get("title") or e.get("folder")) for e in self.entries}
        groups: Dict[str, List[str]] = {}
        for f, n, _r in plan:
            groups.setdefault(n, []).append(f)
        win = self._dialog("ranger automatiquement", 760, 560, modal=True)
        self._auto_win = win
        rest = nonclass - len(plan)
        head = (f"Je propose de ranger {len(plan)} archive(s) non classée(s) dans {len(groups)} collection(s) :"
                + (f"\n{rest} archive(s) resteront dans « 📥 Non classées » (pas d'idée sûre)." if rest > 0 else "")
                + "\nTes archives déjà classées ne bougent pas. Tu pourras tout annuler d'un clic (↩).")
        tk.Label(win, text=head, bg=NC_BG, fg=NC_TEXT, font=FONT_UI, justify="left", anchor="w",
                 wraplength=720).pack(fill="x", padx=12, pady=(10, 6))
        fr, txt = self._scrolled_text(win, height=16, bg=NC_PANEL, fg=NC_TEXT, font=FONT_TEXT)
        fr.pack(fill="both", expand=True, padx=12, pady=4)
        txt.tag_configure("h", foreground=NC_HI, font=FONT_UI, spacing1=8)
        new_lower = {n.lower() for n in names}
        for n in sorted(groups, key=lambda k: (-len(groups[k]), k.lower())):
            mark = "" if n.lower() in new_lower else "  (nouvelle)"
            txt.insert("end", f"📚 {n} — {len(groups[n])}{mark}\n", ("h",))
            for f in groups[n]:
                txt.insert("end", f"     • {title_of.get(f, f)[:110]}\n")
        txt.configure(state="disabled")
        row = tk.Frame(win, bg=NC_BG)
        row.pack(fill="x", padx=12, pady=(4, 10))

        def go():
            win.destroy()
            self._apply_auto_plan(plan, names)
        self._btn(row, "✔ Ranger", go, hi=True, font=FONT_UI).pack(side="right", padx=(6, 0))
        self._btn(row, "Annuler", win.destroy, font=FONT_UI).pack(side="right")
        self.status.set("✨ Vérifie la proposition puis « ✔ Ranger ».")
        return win

    def _apply_auto_plan(self, plan: List[Tuple[str, str, str]], names: List[str]):
        root = self.archive_root_path()
        self.status.set("✨ Rangement en cours…")
        try:
            self.configure(cursor="watch")
            self.update_idletasks()
        except Exception:
            pass
        done: List[Tuple[str, str]] = []
        created: List[str] = []
        try:
            backup_index(root, min_interval=0)
            low = {n.lower() for n in names}
            for _f, n, _r in plan:
                if n.lower() not in low:
                    created.append(n)
                    low.add(n.lower())
            if created:
                save_collections(root, names + created)
            groups: Dict[str, List[str]] = {}
            for f, n, _r in plan:
                groups.setdefault(n, []).append(f)
            for n, fl in groups.items():
                set_collections(root, fl, add=n)
                done += [(f, n) for f in fl]
        except Exception as ex:
            logger.exception("rangement auto")
            messagebox.showerror(APP_NAME, f"Rangement interrompu :\n{friendly_error(ex)}\n\n"
                                 "Ce qui est déjà rangé peut être annulé (↩).", parent=self)
        finally:
            try:
                self.configure(cursor="")
            except Exception:
                pass
        self._auto_undo = {"done": done, "created": created}
        if done:
            self.undo_btn.pack(fill="x", padx=4, pady=(0, 4), after=self._undo_anchor)
        ncol = len({n for _f, n in done})
        msg = f"✅ {len(done)} archive(s) rangée(s) dans {ncol} collection(s) — « ↩ Annuler le rangement » si ça ne te plaît pas."
        self.status.set(msg)
        self.log(msg)
        self._reload_entries()

    def undo_auto_classify(self):
        u = self._auto_undo
        if not u:
            return
        root = self.archive_root_path()
        try:
            groups: Dict[str, List[str]] = {}
            for f, n in u.get("done") or []:
                groups.setdefault(n, []).append(f)
            for n, fl in groups.items():
                set_collections(root, [f for f in fl if os.path.isdir(os.path.join(root, f))], remove=n)
            ents = load_archive_index(root)
            used = {c.lower() for e in ents for c in (e.get("collections") or [])}
            drop = {c.lower() for c in u.get("created") or [] if c.lower() not in used}
            if drop:
                save_collections(root, [n for n in load_collections(root) if n.lower() not in drop])
        except Exception as ex:
            logger.exception("annuler rangement")
            messagebox.showerror(APP_NAME, f"Annulation impossible :\n{friendly_error(ex)}", parent=self)
            return
        self._auto_undo = None
        self.undo_btn.pack_forget()
        if self._coll_key() and not self._coll_key().startswith("__"):
            self.coll_var.set(COLL_ALL_LABEL)
            self.cfg["collection_filter"] = ""
        msg = "↩ Rangement annulé : les archives sont revenues dans « Non classées »."
        self.status.set(msg)
        self.log(msg)
        self._reload_entries()

    def _reload_entries(self):
        """Relit l'index (après une action groupée) sans rebalayer le disque."""
        self.entries = load_archive_index(self.archive_root_path())
        self._refresh_filter_values()
        self.apply_filter()
        self._refresh_preview_meta()

    def _show_hist_menu(self, event):
        iid = self.tree.identify_row(event.y)
        if iid and iid not in self.tree.selection():
            self.tree.selection_set(iid)
            self.tree.focus(iid)
            e = self._iid_entry.get(iid)
            if e:
                self.show_preview(e)
        ents = self._selected_entries()
        if not ents:
            return "break"
        m = self._hist_menu
        m.delete(0, "end")
        n = len(ents)
        allfav = all(e.get("favorite") for e in ents)
        if n == 1:
            e = ents[0]
            path = os.path.join(self.archive_root_path(), str(e.get("folder")))
            main = find_main_media(path)
            m.add_command(label="▶ Lire dans l'aperçu", command=self.play_selected,
                          state="normal" if (main or list_images(path)) else "disabled")
            m.add_command(label="↗ Ouvrir dans le lecteur externe", command=self.open_selected_media,
                          state="normal" if main else "disabled")
            m.add_command(label="📄 Page archive (index.html)", command=self.open_selected_index)
            m.add_command(label="📁 Ouvrir le dossier", command=self.open_selected_folder)
            m.add_command(label="🌐 Ouvrir l'original", command=self.open_original)
            m.add_separator()
        else:
            m.add_command(label=f"{n} archives sélectionnées", state="disabled")
            m.add_separator()
        m.add_command(label="☆ Retirer des favoris" if allfav else "★ Ajouter aux favoris  (Ctrl+D)",
                      command=self.toggle_favorite)
        m.add_cascade(label="📂 Déplacer vers la collection…" + ("" if n == 1 else f" ({n})"),
                      menu=self._build_move_menu(parent=m))
        m.add_cascade(label="📚 Collections (cocher plusieurs)", menu=self._build_coll_menu(parent=m))
        m.add_command(label="🏷 Ajouter des tags…", command=self.add_tags_selected)
        m.add_separator()
        if n == 1:
            m.add_command(label="📋 Copier le lien", command=self.copy_link)
            m.add_command(label="📋 Copier le résumé (titre, lien, auteur, tags)", command=self.copy_summary)
            m.add_command(label="📋 Copier le chemin du dossier", command=self.copy_folder_path)
        else:
            m.add_command(label=f"📋 Copier les {n} liens", command=self.copy_links_selected)
            m.add_command(label=f"📋 Copier les {n} résumés", command=self.copy_summary)
        m.add_command(label="📚 Envoyer au Grimoire…" + ("" if n == 1 else f" ({n})"),
                      command=self.send_to_grimoire)
        m.add_separator()
        m.add_command(label="📡 Vérifier si l'original est en ligne" if n == 1 else f"📡 Vérifier en ligne ({n})",
                      command=lambda: self.check_online_selected(False))
        m.add_command(label="📦 Exporter en ZIP…  (Ctrl+E)", command=lambda: self.export_zip_dialog("selection"))
        if n == 1:
            m.add_command(label="✂ Outils média (capture, extrait, MP3, GIF)…", command=self.open_media_tools)
            m.add_command(label="🎞 Refaire le storyboard", command=self.regen_storyboard)
        m.add_command(label="🎬 Convertir en MP4 compatible (H.264)" + ("" if n == 1 else f" ({n})"),
                      command=self.convert_selected_many)
        m.add_separator()
        if n == 1:
            m.add_command(label="✏ Renommer (F2)", command=self.rename_selected)
        m.add_command(label="🗑 Supprimer…" if n == 1 else f"🗑 Supprimer les {n} archives…", command=self.delete_selected)
        try:
            m.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                m.grab_release()
            except Exception:
                pass
        return "break"

    # ---------------------------------------------------------------- Grimoire (carnet de recherche)
    def _grimoire_script(self) -> str:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "grimoire1.py")

    def send_to_grimoire(self):
        """📚 Envoyer au Grimoire : choisir le sujet, puis creer la fiche directement dans grimoire.db
        (titre, texte, image, lien d'origine, copie locale « ✔ Permanent »). Marche Grimoire ouvert ou ferme."""
        ents = self._selected_entries()
        if not ents:
            messagebox.showinfo(APP_NAME, "Choisis d'abord une archive (ou plusieurs) dans la liste.", parent=self)
            return
        if not os.path.isfile(gr_db_path()):
            messagebox.showwarning(APP_NAME, f"Grimoire introuvable :\n{gr_db_path()}\n\nOuvre le Grimoire une première fois.", parent=self)
            return
        root = self.archive_root_path()
        infos = []
        for e in ents:
            info = dict(e)
            try:
                info.update(load_info(os.path.join(root, str(e.get("folder")))))
            except Exception:
                pass
            infos.append(info)
        # doublons : lien deja dans une fiche ?
        try:
            c = gr_connect()
            dups = []
            for e, i in zip(list(ents), list(infos)):
                d = gr_find_url(c, str(i.get("url") or i.get("webpage_url") or ""))
                if d:
                    dups.append((e, i, d))
            c.close()
        except Exception as ex:
            messagebox.showerror(APP_NAME, f"Lecture du Grimoire impossible : {ex}", parent=self)
            return
        if dups:
            if len(ents) == 1:
                d = dups[0][2]
                if messagebox.askyesno(APP_NAME, f"Ce lien est déjà dans le Grimoire :\n« {d['title']} »\n\nL'ouvrir dans le Grimoire ?",
                                       parent=self):
                    gr_open_item(d["id"], self._grimoire_script())
                return
            keep = [(e, i) for e, i in zip(ents, infos) if not any(e is x[0] for x in dups)]
            messagebox.showinfo(APP_NAME, f"{len(dups)} archive(s) déjà dans le Grimoire : elles sont ignorées.", parent=self)
            if not keep:
                return
            ents, infos = [k[0] for k in keep], [k[1] for k in keep]
        dlg = GrimoireSendDialog(self, ents, infos)
        self.wait_window(dlg)
        sid = dlg.result
        if not sid:
            return
        ids, err = [], ""
        try:
            c = gr_connect()
            subs = gr_subjects(c)
            for e, i in zip(ents, infos):
                try:
                    ids.append(gr_add_fiche(c, sid, root, e, i))
                except Exception as ex:
                    err = str(ex)
            name = gr_path(subs, sid)
            c.close()
        except Exception as ex:
            err, name = str(ex), "?"
        if ids:
            msg = f"✔ Ajouté au Grimoire « {name} »" + ("" if len(ids) == 1 else f" ({len(ids)} fiches)")
            self.status.set(msg)
            try:
                self.log(msg, "info")
            except Exception:
                pass
            self._grimoire_toast(msg, ids[0])
        if err:
            messagebox.showerror(APP_NAME, f"Envoi au Grimoire incomplet : {err}", parent=self)

    def _grimoire_toast(self, msg: str, iid: int):
        try:
            t = tk.Toplevel(self)
            t.overrideredirect(True)
            t.configure(bg=NC_HI)
            tk.Label(t, text=msg, bg=NC_HI, fg=NC_ON_HI, font=FONT_UI, padx=12, pady=8).pack(side="left")
            b = tk.Button(t, text="📖 Ouvrir dans le Grimoire", command=lambda: (gr_open_item(iid, self._grimoire_script()), t.destroy()),
                          bg=NC_BTN, fg=NC_BTN_FG, font=FONT_SM, relief="raised", bd=1, cursor="hand2")
            b.pack(side="left", padx=6, pady=6)
            Tooltip(b, "Montre la nouvelle fiche dans le Grimoire (le lance s'il est fermé)")
            x = tk.Button(t, text="✖", command=t.destroy, bg=NC_HI, fg=NC_ON_HI, relief="flat", font=FONT_SM, cursor="hand2")
            x.pack(side="left", padx=(0, 6))
            t.update_idletasks()
            t.geometry(f"+{self.winfo_rootx() + (self.winfo_width() - t.winfo_reqwidth()) // 2}+"
                       f"{self.winfo_rooty() + self.winfo_height() - t.winfo_reqheight() - 70}")
            t.attributes("-topmost", True)
            self.after(9000, lambda: t.winfo_exists() and t.destroy())
        except Exception:
            pass

    def _build_coll_menu(self, parent=None):
        """Menu des collections : coche = l'archive (toutes celles sélectionnées) en fait partie."""
        m = tk.Menu(parent or self, tearoff=0, bg=NC_PANEL, fg=NC_FG, activebackground=NC_SEL,
                    activeforeground=NC_ON_SEL, font=FONT_SM)
        folders = self._selected_folders()
        ents = self._selected_entries()
        names = load_collections(self.archive_root_path(), self.entries)
        m.add_command(label="➕ Nouvelle collection…", command=self.new_collection,
                      state="normal" if folders else "disabled")
        if names:
            m.add_separator()
        for c in names:
            inside = bool(ents) and all(c.lower() in {x.lower() for x in (e.get("collections") or [])} for e in ents)
            m.add_command(label=("☑ " if inside else "☐ ") + c,
                          command=lambda cc=c, ins=inside: self._toggle_collection(cc, ins),
                          state="normal" if folders else "disabled")
        if names:
            m.add_separator()
            sub = tk.Menu(m, tearoff=0, bg=NC_PANEL, fg=NC_FG, activebackground=NC_SEL,
                          activeforeground=NC_ON_SEL, font=FONT_SM)
            for c in names:
                sub.add_command(label=c, command=lambda cc=c: self.delete_collection(cc))
            m.add_cascade(label="🗑 Supprimer une collection", menu=sub)
        return m

    def _toggle_collection(self, name: str, inside: bool):
        folders = self._selected_folders()
        if not folders:
            return
        root = self.archive_root_path()
        try:
            if inside:
                set_collections(root, folders, remove=name)
                self.log(f"📚 Retiré de « {name} » : {len(folders)} archive(s)")
            else:
                set_collections(root, folders, add=name)
                self.log(f"📚 Ajouté à « {name} » : {len(folders)} archive(s)")
        except Exception as ex:
            logger.exception("collections")
            messagebox.showerror(APP_NAME, f"Collection : {friendly_error(ex)}", parent=self)
        self._reload_entries()

    def new_collection(self):
        folders = self._selected_folders()
        name = self._ask_string("Nom de la nouvelle collection :\n(ex. Recettes, Politique, À revoir)",
                                      parent=self)
        name = re.sub(r"\s+", " ", (name or "")).strip()[:40]
        if not name:
            return
        root = self.archive_root_path()
        names = load_collections(root, self.entries)
        if name.lower() not in {n.lower() for n in names}:
            save_collections(root, names + [name])
        else:
            name = next(n for n in names if n.lower() == name.lower())
        if folders:
            set_collections(root, folders, add=name)
            self.log(f"📚 Collection « {name} » : {len(folders)} archive(s)")
        self._reload_entries()

    def delete_collection(self, name: str):
        root = self.archive_root_path()
        members = [str(e.get("folder")) for e in self.entries
                   if name.lower() in {c.lower() for c in (e.get("collections") or [])}]
        if not messagebox.askyesno(APP_NAME, f"Supprimer la collection « {name} » ?\n\n"
                                   f"Les {len(members)} archive(s) qu'elle contient sont conservées ; "
                                   "elles sont seulement retirées de la collection.", parent=self):
            return
        if members:
            set_collections(root, members, remove=name)
        save_collections(root, [n for n in load_collections(root) if n.lower() != name.lower()])
        if self._coll_key().lower() == name.lower():
            self.coll_var.set(COLL_ALL_LABEL)
            self.cfg["collection_filter"] = ""
            save_cfg(self.cfg)
        self.log(f"🗑 Collection « {name} » supprimée.")
        self._reload_entries()

    def toggle_favorite(self):
        ents = self._selected_entries()
        if not ents:
            return
        value = not all(e.get("favorite") for e in ents)
        n = set_favorite(self.archive_root_path(), [str(e.get("folder")) for e in ents], value)
        self.status.set(("★ Ajouté aux favoris" if value else "☆ Retiré des favoris") + (f" ({n})" if n > 1 else ""))
        self._reload_entries()

    def add_tags_selected(self):
        folders = self._selected_folders()
        if not folders:
            return
        txt = self._ask_string(f"Tags à ajouter à {len(folders)} archive(s) (séparés par des virgules) :",
                                     parent=self)
        tags = parse_tags(txt or "")
        if not tags:
            return
        self._autosave_tn()
        n = add_tags_many(self.archive_root_path(), folders, tags)
        self.log(f"🏷 Tags {', '.join('#' + t for t in tags)} ajoutés à {n} archive(s).")
        self._reload_entries()
        if self._preview_entry and self._preview_entry.get("folder") in folders:
            info = load_info(self._preview_path)
            self.tags_var.set(", ".join(parse_tags(info.get("tags") or [])))
            self._loaded_tn = self._tn_current()
            self._render_tag_chips(parse_tags(info.get("tags") or []), info.get("source_tags") or [])

    def copy_summary(self):
        ents = self._selected_entries()
        if ents:
            full = []
            for e in ents:
                p = os.path.join(self.archive_root_path(), str(e.get("folder")))
                info = dict(e)
                info.update(load_info(p))
                full.append(entry_summary(info))
            self._copy_to_clipboard("\n\n".join(full))
            self.status.set(f"📋 Résumé copié ({len(ents)} archive{'s' if len(ents) > 1 else ''}).")

    def copy_links_selected(self):
        urls = [str(e.get("url") or e.get("webpage_url") or "") for e in self._selected_entries()]
        urls = [u for u in urls if u]
        if urls:
            self._copy_to_clipboard("\n".join(urls))
            self.status.set(f"📋 {len(urls)} lien(s) copié(s).")

    def convert_selected_many(self):
        ents = self._selected_entries()
        if len(ents) <= 1:
            self.convert_selected()
            return
        if not find_ffmpeg():
            messagebox.showwarning(APP_NAME, "ffmpeg est requis pour la conversion.", parent=self)
            return
        items = []
        for e in ents:
            m = find_main_media(os.path.join(self.archive_root_path(), str(e.get("folder"))))
            if m and m.lower().endswith(VIDEO_EXTS):
                items.append((str(e.get("folder")), str(e.get("title") or "")))
        if not items:
            messagebox.showinfo(APP_NAME, "Aucune vidéo dans la sélection.", parent=self)
            return
        n = self._enqueue_convert(items)
        self.status.set(f"🎬 {n} conversion(s) ajoutée(s) — les vidéos déjà compatibles sont ignorées.")

    # ------------------------------------------------------------ v5 : en ligne ?
    def check_online_selected(self, all_visible: bool = False):
        if getattr(self, "_online_busy", False):
            self.status.set("📡 Vérification déjà en cours…")
            return
        ents = list(self._visible) if all_visible else self._selected_entries()
        folders = [str(e.get("folder")) for e in ents if e.get("folder")]
        if not folders:
            return
        self._online_busy = True
        root = self.archive_root_path()
        self.status.set(f"📡 Vérification en ligne de {len(folders)} archive(s)…")
        self.log(f"📡 Vérification en ligne : {len(folders)} archive(s)")
        self.prog.configure(value=0)

        def prog(done, total, f, st):
            def _u():
                self.prog.configure(value=done * 100.0 / max(1, total))
                self.prog_var.set(f"📡 {done}/{total} · {GUI_ONLINE.get(st, ('?',))[0]} {f[:60]}")
            self.ui(_u)

        def job():
            counts: Dict[str, int] = {}
            err = ""
            try:
                counts = check_online_many(root, folders, progress=prog,
                                           workers=int(self.cfg.get("online_workers") or 4))
            except Exception as ex:
                logger.exception("check online")
                err = friendly_error(ex)
            self.ui(lambda: self._online_done(counts, err, len(folders)))
        threading.Thread(target=job, daemon=True).start()

    def _online_done(self, counts: Dict[str, int], err: str, n: int):
        self._online_busy = False
        self.prog.configure(value=0)
        if err:
            self.prog_var.set("Aucun archivage en cours.")
            messagebox.showerror(APP_NAME, f"Vérification impossible :\n{err}", parent=self)
            return
        parts = [f"{GUI_ONLINE[k][0]} {GUI_ONLINE[k][1]} : {v}" for k, v in counts.items() if v and k in GUI_ONLINE]
        msg = " · ".join(parts) or "aucun résultat"
        self.prog_var.set(f"📡 Vérifié ({n}) — {msg}")
        self.log(f"📡 Résultat : {msg}")
        self.status.set(f"📡 Vérification terminée — {msg}")
        self._reload_entries()
        if self._smoke:
            return
        off = counts.get("offline", 0) + counts.get("restricted", 0)
        if n > 1:
            if off and messagebox.askyesno(APP_NAME, f"Vérification terminée ({n} archives) :\n\n" + "\n".join(parts) +
                                           f"\n\nAfficher les {off} archive(s) dont l'original n'est plus disponible ?",
                                           parent=self):
                lab = next((k for k, v in self._coll_map.items() if v == COLL_OFFLINE), COLL_ALL_LABEL)
                self.coll_var.set(lab)
                self._on_coll_filter()
            elif not off:
                messagebox.showinfo(APP_NAME, f"Vérification terminée ({n} archives) :\n\n" + "\n".join(parts), parent=self)

    # ------------------------------------------------------------ v5 : export
    def _docs_dir(self) -> str:
        d = os.path.join(os.path.expanduser("~"), "Documents")
        return d if os.path.isdir(d) else os.path.expanduser("~")

    def export_zip_dialog(self, scope: str = "selection"):
        if getattr(self, "_export_busy", False):
            self.status.set("📦 Export déjà en cours…")
            return
        ents = self._selected_entries() if scope == "selection" else list(self._visible)
        folders = [str(e.get("folder")) for e in ents if e.get("folder")]
        if not folders:
            messagebox.showinfo(APP_NAME, "Aucune archive à exporter.", parent=self)
            return
        root = self.archive_root_path()
        total = sum(folder_size(os.path.join(root, f)) for f in folders)
        base = slugify(str(ents[0].get("title") or "archive"))[:40] if len(ents) == 1 else f"archives_{len(ents)}"
        name = f"Archiveur_{base}_{datetime.now().strftime('%Y-%m-%d')}.zip"
        dest = filedialog.asksaveasfilename(parent=self, title=f"Exporter {len(folders)} archive(s) en ZIP ({human_size(total)})",
                                            initialdir=self._docs_dir(), initialfile=name, defaultextension=".zip",
                                            filetypes=[("Archive ZIP", "*.zip")])
        if not dest:
            return
        try:
            free = shutil.disk_usage(os.path.dirname(dest) or ".").free
            if free < total + 50 * 1024 * 1024:
                messagebox.showerror(APP_NAME, f"Espace insuffisant : il faut ≈ {human_size(total)}, "
                                     f"disponible {human_size(free)}.", parent=self)
                return
        except Exception:
            pass
        self._export_busy = True
        self.log(f"📦 Export ZIP : {len(folders)} archive(s) → {dest}")

        def prog(i, n, f):
            self.ui(lambda: (self.prog.configure(value=i * 100.0 / max(1, n)),
                             self.prog_var.set(f"📦 Export ZIP {i}/{n} : {f[:60]}")))

        def job():
            err = ""
            res = (0, 0)
            try:
                res = export_zip(root, folders, dest, progress=prog)
            except Exception as ex:
                logger.exception("export zip")
                err = friendly_error(ex)
            self.ui(lambda: self._export_done(dest, res, err))
        threading.Thread(target=job, daemon=True).start()

    def _export_done(self, dest: str, res: Tuple[int, int], err: str):
        self._export_busy = False
        self.prog.configure(value=0)
        if err:
            self.prog_var.set("Export ZIP échoué.")
            messagebox.showerror(APP_NAME, f"Export impossible :\n{err}", parent=self)
            return
        self.prog_var.set(f"📦 ZIP créé : {os.path.basename(dest)} ({human_size(res[1])})")
        self.log(f"📦 ZIP créé : {dest} — {res[0]} fichiers, {human_size(res[1])}")
        if messagebox.askyesno(APP_NAME, f"ZIP créé ✅\n\n{dest}\n{res[0]} fichiers · {human_size(res[1])}\n\n"
                               "Il contient une page index.html (à ouvrir après décompression) et catalogue.csv.\n\n"
                               "Afficher le fichier dans l'Explorateur ?", parent=self):
            ok, e2 = reveal_in_explorer(dest)
            if not ok:
                self.open_path_safe(os.path.dirname(dest), "dossier")

    def export_catalog_dialog(self):
        ents = list(self._visible)
        if not ents:
            messagebox.showinfo(APP_NAME, "Aucune archive dans la liste.", parent=self)
            return
        dest = filedialog.asksaveasfilename(
            parent=self, title=f"Exporter le catalogue ({len(ents)} archives affichées)", initialdir=self._docs_dir(),
            initialfile=f"Archiveur_catalogue_{datetime.now().strftime('%Y-%m-%d')}.csv", defaultextension=".csv",
            filetypes=[("CSV (Excel)", "*.csv"), ("JSON", "*.json")])
        if not dest:
            return
        try:
            n = export_catalog(ents, dest)
        except Exception as ex:
            logger.exception("catalogue")
            messagebox.showerror(APP_NAME, f"Export impossible :\n{friendly_error(ex)}", parent=self)
            return
        self.log(f"📑 Catalogue exporté : {n} lignes → {dest}")
        if messagebox.askyesno(APP_NAME, f"Catalogue exporté ✅ ({n} archives)\n\n{dest}\n\nL'ouvrir maintenant ?", parent=self):
            self.open_path_safe(dest, "fichier")

    # ------------------------------------------------------------ v5 : dialogues
    def _dialog(self, title: str, w: int, h: int, modal: bool = False):
        win = tk.Toplevel(self)
        win.title(f"{APP_NAME} — {title}")
        win.configure(bg=NC_BG)
        sw = max(400, self.winfo_width() if self.winfo_width() > 200 else self.winfo_screenwidth())
        sh = max(300, self.winfo_height() if self.winfo_height() > 200 else self.winfo_screenheight())
        w, h = min(w, sw - 40), min(h, sh - 40)
        x = self.winfo_rootx() + max(0, (sw - w) // 2)
        y = self.winfo_rooty() + max(0, (sh - h) // 2)
        win.geometry(f"{w}x{h}+{x}+{y}")
        win.transient(self)
        try:
            win.iconphoto(False, self._icon_img)
        except Exception:
            pass
        win.bind("<Escape>", lambda e: win.destroy())
        if modal:
            try:
                win.grab_set()
            except Exception:
                pass
        return win

    def _ask_string(self, prompt: str, initial: str = "", parent=None) -> Optional[str]:
        win = self._dialog("saisie", 520, 190, modal=True)
        res: Dict[str, Optional[str]] = {"v": None}
        tk.Label(win, text=prompt, bg=NC_BG, fg=NC_FG, font=FONT_UI, justify="left", anchor="w",
                 wraplength=480).pack(fill="x", padx=14, pady=(14, 6))
        var = tk.StringVar(value=initial)
        ent = tk.Entry(win, textvariable=var, bg=NC_ENTRY_BG, fg=NC_ENTRY_FG, insertbackground=NC_FG, font=FONT_UI)
        ent.pack(fill="x", padx=14, ipady=3)
        row = tk.Frame(win, bg=NC_BG)
        row.pack(fill="x", padx=14, pady=12, side="bottom")

        def ok(_e=None):
            res["v"] = var.get()
            win.destroy()
        self._btn(row, "OK", ok, hi=True, font=FONT_UI).pack(side="right", padx=4)
        self._btn(row, "Annuler", win.destroy, font=FONT_UI).pack(side="right", padx=4)
        ent.bind("<Return>", ok)
        ent.focus_set()
        ent.select_range(0, "end")
        self._modal_win = win
        if not self._smoke:
            self.wait_window(win)
        return res["v"]

    def _build_tools_menu(self):
        m = self._menu()
        m.add_command(label="✔ Vérifier les archives (intégrité)…", command=self.verify_dialog)
        m.add_command(label="📡 Vérifier si les originaux sont encore en ligne (liste affichée)",
                      command=lambda: self.check_online_selected(True))
        m.add_command(label="📊 Statistiques…", command=self.open_stats)
        m.add_separator()
        m.add_command(label="📦 Exporter la sélection en ZIP…  (Ctrl+E)", command=lambda: self.export_zip_dialog("selection"))
        m.add_command(label="📦 Exporter la liste affichée en ZIP…", command=lambda: self.export_zip_dialog("visible"))
        m.add_command(label="📑 Exporter le catalogue (CSV pour Excel, ou JSON)…", command=self.export_catalog_dialog)
        m.add_separator()
        m.add_command(label="♻ Régénérer l'index (pages HTML)", command=self.regenerate_index)
        m.add_command(label="🎬 Réparer les codecs (toutes les vidéos)", command=self.fix_all_codecs)
        m.add_command(label="📁 Ouvrir le dossier racine des archives", command=self.open_root)
        m.add_command(label="🗂 Ouvrir les sauvegardes de l'index", command=self.open_backups)
        m.add_separator()
        m.add_command(label=f"⬆ Mettre à jour yt-dlp (version {ytdlp_version() or '?'})", command=self.update_ytdlp_ui)
        return m

    def _build_more_menu(self):
        m = self._menu()
        has = bool(self._preview_entry)
        st = "normal" if has else "disabled"
        main = find_main_media(self._preview_path) if has and self._preview_path else None
        m.add_command(label="📋 Copier le lien", command=self.copy_link, state=st)
        m.add_command(label="📋 Copier le résumé (titre, lien, auteur, tags)", command=self.copy_summary, state=st)
        m.add_command(label="📋 Copier le chemin du dossier", command=self.copy_folder_path, state=st)
        m.add_separator()
        m.add_command(label="📡 Vérifier si l'original est en ligne", command=lambda: self.check_online_selected(False), state=st)
        m.add_command(label="📦 Exporter en ZIP…", command=lambda: self.export_zip_dialog("selection"), state=st)
        m.add_command(label="🏷 Ajouter des tags…", command=self.add_tags_selected, state=st)
        m.add_separator()
        m.add_command(label="🎙 Transcrire le son (Whisper, local)", command=self.transcribe_selected,
                      state="normal" if (main and whisper_available()) else "disabled")
        m.add_command(label="🎬 Convertir en MP4 compatible (H.264)", command=self.convert_selected,
                      state="normal" if (main and main.lower().endswith(VIDEO_EXTS)) else "disabled")
        m.add_command(label="🎞 Refaire le storyboard", command=self.regen_storyboard,
                      state="normal" if (main and main.lower().endswith(VIDEO_EXTS)) else "disabled")
        url = self._entry_url() if has else ""
        m.add_command(label="🔁 Ré-archiver depuis l'original", command=lambda: self.enqueue_urls([url], ask_dups=False),
                      state="normal" if url else "disabled")
        m.add_command(label="📰 Ré-archiver comme page web (lecture + capture + PDF)",
                      command=lambda: self.enqueue_urls([url], ask_dups=False, extra={"page_mode": True}),
                      state="normal" if url else "disabled")
        m.add_separator()
        m.add_command(label="✏ Renommer (F2)", command=self.rename_selected, state=st)
        m.add_command(label="🗑 Supprimer l'archive…  (Suppr)", command=self.delete_selected, state=st)
        return m

    def open_backups(self):
        d = os.path.join(self.archive_root_path(), BACKUP_DIR)
        if not os.path.isdir(d):
            backup_index(self.archive_root_path(), min_interval=0)
        if os.path.isdir(d):
            self.open_path_safe(d, "dossier")
        else:
            messagebox.showinfo(APP_NAME, "Aucune sauvegarde pour l'instant (l'index est vide).", parent=self)

    # ---------------------------------------------------------------- réglages
    def open_settings(self):
        win = self._dialog("réglages", 640, 600)
        self._settings_win = win
        sf = ScrollFrame(win)
        sf.pack(fill="both", expand=True)
        body = sf.inner
        cfg = self.cfg

        def section(t):
            return self._section(body, t)

        section("🎨 Apparence")
        theme_var = tk.StringVar(value=THEME)
        row = tk.Frame(body, bg=NC_BG)
        row.pack(fill="x", padx=14)
        tk.Label(row, text="Thème :", bg=NC_BG, fg=NC_FG, font=FONT_UI).pack(side="left")
        for k, lab in THEME_LABELS.items():
            tk.Radiobutton(row, text=lab, value=k, variable=theme_var, bg=NC_BG, fg=NC_FG, selectcolor=NC_ENTRY_BG,
                           activebackground=NC_BG, activeforeground=NC_HI, font=FONT_SM, highlightthickness=0,
                           command=lambda: self._theme_changed(theme_var.get())).pack(side="left", padx=6)
        tk.Label(body, text="Changer de thème relance l'Archiveur (quelques secondes).", bg=NC_BG, fg=NC_DIM,
                 font=FONT_SM, anchor="w").pack(fill="x", padx=14)
        row = tk.Frame(body, bg=NC_BG)
        row.pack(fill="x", padx=14, pady=(8, 0))
        tk.Label(row, text="Taille du texte :", bg=NC_BG, fg=NC_FG, font=FONT_UI).pack(side="left")
        self._fs_lab = tk.Label(row, text="", bg=NC_BG, fg=NC_HI, font=FONT_UI, width=8)
        self._btn(row, "A−", lambda: self._font_step(-1), font=FONT_UI).pack(side="left", padx=(8, 2))
        self._fs_lab.pack(side="left")
        self._btn(row, "A+", lambda: self._font_step(1), font=FONT_UI).pack(side="left", padx=2)
        self._btn(row, "Normal", lambda: self._font_step(0, reset=True)).pack(side="left", padx=8)
        self._fs_update()
        tk.Label(body, text="Raccourcis : Ctrl + molette, Ctrl + / Ctrl − / Ctrl 0", bg=NC_BG, fg=NC_DIM,
                 font=FONT_SM, anchor="w").pack(fill="x", padx=14)

        def chk(text, key, tip="", default=True, cmd=None):
            var = tk.BooleanVar(value=bool(cfg.get(key, default)))

            def _set():
                cfg[key] = bool(var.get())
                save_cfg(cfg)
                if cmd:
                    cmd()
            cb = tk.Checkbutton(body, text=text, variable=var, command=_set, bg=NC_BG, fg=NC_FG, selectcolor=NC_ENTRY_BG,
                                activebackground=NC_BG, activeforeground=NC_HI, font=FONT_UI, anchor="w",
                                highlightthickness=0)
            cb.pack(fill="x", padx=14, pady=(4, 0))
            if tip:
                tk.Label(body, text=tip, bg=NC_BG, fg=NC_DIM, font=FONT_SM, anchor="w", justify="left",
                         wraplength=560).pack(fill="x", padx=38)
            return var

        section("▶ Lecture")
        ff_ok = bool(find_ffmpeg()) and bool(find_ffplay())
        chk("Lecteur intégré dans l'aperçu", "integrated_player",
            "▶ Lire joue la vidéo directement dans l'Archiveur (ffmpeg + ffplay, rien à installer). "
            "Décoché : ▶ ouvre le lecteur externe choisi ci-dessous."
            + ("" if ff_ok else "\n⚠ ffplay introuvable : relance setup_padawan.bat pour l'installer avec ffmpeg."),
            cmd=lambda: self._preview_entry and self.show_preview(self._preview_entry))
        row = tk.Frame(body, bg=NC_BG)
        row.pack(fill="x", padx=14, pady=(8, 0))
        tk.Label(row, text="Lecteur externe (↗) :", bg=NC_BG, fg=NC_FG, font=FONT_UI).pack(side="left")
        pvals = [PLAYER_LABELS["windows"]] + [PLAYER_LABELS[k] for k in ("vlc", "mpv") if k in self._players]
        pcb = ttk.Combobox(row, textvariable=self.player_var, values=pvals, width=22, state="readonly", font=FONT_SM)
        pcb.pack(side="left", padx=6)
        pcb.bind("<<ComboboxSelected>>", lambda e: self._persist_opts())
        if len(pvals) == 1:
            pcb.configure(state="disabled")
        tk.Label(body, text=("Détectés : " + ", ".join(PLAYER_LABELS[k] for k in self._players)) if self._players else
                 "VLC / mpv non détectés : le lecteur Windows est utilisé (winget install VideoLAN.VLC pour VLC).",
                 bg=NC_BG, fg=NC_DIM, font=FONT_SM, anchor="w", justify="left", wraplength=560).pack(fill="x", padx=38)
        section("🌐 Archivage")
        row = tk.Frame(body, bg=NC_BG)
        row.pack(fill="x", padx=14, pady=(4, 0))
        tk.Label(row, text="Dossier des archives :", bg=NC_BG, fg=NC_FG, font=FONT_UI).pack(side="left")
        ent = tk.Entry(row, textvariable=self.root_var, bg=NC_ENTRY_BG, fg=NC_ENTRY_FG, insertbackground=NC_FG,
                       font=FONT_SM)
        ent.pack(side="left", fill="x", expand=True, padx=6)
        ent.bind("<Return>", lambda e: (self._persist_opts(), self.refresh_list()))
        ent.bind("<FocusOut>", lambda e: self._persist_opts())
        self._btn(row, "Choisir…", self.choose_root).pack(side="left")

        def vchk(text, var, tip):
            tk.Checkbutton(body, text=text, variable=var, command=self._persist_opts, bg=NC_BG, fg=NC_FG,
                           selectcolor=NC_ENTRY_BG, activebackground=NC_BG, activeforeground=NC_HI, font=FONT_UI,
                           anchor="w", highlightthickness=0).pack(fill="x", padx=14, pady=(4, 0))
            tk.Label(body, text=tip, bg=NC_BG, fg=NC_DIM, font=FONT_SM, anchor="w", justify="left",
                     wraplength=560).pack(fill="x", padx=38)
        vchk("🎞 Storyboard aussi pendant l'archivage", self.sb_var,
             "Sinon il se prépare tout seul en arrière-plan juste après (ou à l'affichage) — clic sur une image = lecture à ce moment.")
        vchk("🎬 MP4 compatible automatique", self.conv_var,
             "Si la vidéo reçue est en AV1/VP9/Opus, la convertir en MP4 H.264 + AAC (lisible partout, à vie).")
        vchk("🔔 Notification Windows à la fin de l'archivage", self.notif_var, "Petite bulle en bas à droite de l'écran.")
        chk("Pages web : capture d'écran + PDF de la page entière", "web_capture",
            "Utilise Edge (ou Chrome) en arrière-plan, sans fenêtre. Ajoute ≈ 10-30 s par page.")
        chk("X / Twitter : service fxtwitter en secours", "x_fxtwitter",
            "Si yt-dlp échoue (post sans vidéo, compte protégé…), récupère le texte, les photos, la vidéo et le fil "
            "(messages précédents) via api.fxtwitter.com, un service public tiers. Seule l'adresse du post lui est envoyée.")
        section("🎙 Transcription (Whisper)")
        has_w = whisper_available()
        tk.Label(body, text=("✅ faster-whisper installé." if has_w else
                             "faster-whisper n'est pas installé : les vidéos avec sous-titres sont quand même transcrites. "
                             "Pour transcrire les autres : setup_padawan.bat → répondre O à « Whisper » (≈ 200 Mo)."),
                 bg=NC_BG, fg=NC_OK if has_w else NC_DIM, font=FONT_SM, anchor="w", justify="left",
                 wraplength=560).pack(fill="x", padx=14, pady=(2, 4))
        row = tk.Frame(body, bg=NC_BG)
        row.pack(fill="x", padx=14)
        tk.Label(row, text="Modèle :", bg=NC_BG, fg=NC_FG, font=FONT_UI).pack(side="left")
        models = [("tiny", "tiny — très rapide, approximatif"), ("base", "base — bon compromis (défaut)"),
                  ("small", "small — plus précis, ≈ 3× plus lent"), ("medium", "medium — précis, lent")]
        wlab = {k: v for k, v in models}
        wvar = tk.StringVar(value=wlab.get(str(cfg.get("whisper_model") or "base"), wlab["base"]))
        wcb = ttk.Combobox(row, textvariable=wvar, values=[v for _k, v in models], width=34, state="readonly", font=FONT_SM)
        wcb.pack(side="left", padx=6)

        def _wset(_e=None):
            inv = {v: k for k, v in models}
            cfg["whisper_model"] = inv.get(wvar.get(), "base")
            save_cfg(cfg)
        wcb.bind("<<ComboboxSelected>>", _wset)
        section("ℹ Informations")
        info_lines = [
            f"Archiveur v{APP_FILE_VER} · Python {sys.version.split()[0]} · Tk {self.tk.call('info', 'patchlevel')}",
            f"yt-dlp : {ytdlp_version() or 'non installé'}",
            f"ffmpeg : {find_ffmpeg() or 'introuvable'}",
            f"ffplay : {find_ffplay() or 'introuvable'}",
            f"Navigateur pour captures : {find_browser() or 'introuvable'}",
            f"Glisser-déposer : {'actif' if getattr(self, '_dnd_ok', False) else 'indisponible (module tkinterdnd2)'}",
            f"Réglages : {CFG_FILE}",
            f"Journal : {LOG_FILE}",
        ]
        tk.Label(body, text="\n".join(info_lines), bg=NC_BG, fg=NC_FG, font=FONT_SM, anchor="w", justify="left",
                 wraplength=580).pack(fill="x", padx=14, pady=(2, 10))
        row = tk.Frame(win, bg=NC_PANEL)
        row.pack(fill="x", side="bottom")
        self._btn(row, "Fermer", win.destroy, hi=True, font=FONT_UI).pack(side="right", padx=10, pady=6)
        self._auto_wrap(sf)
        return win

    def _auto_wrap(self, sf):
        """Les textes longs d'un ScrollFrame suivent la largeur (aucun texte coupé)."""
        labs: List[Any] = []

        def walk(w):
            for c in w.winfo_children():
                if isinstance(c, tk.Label) and (int(float(c.cget("wraplength") or 0)) > 0
                                                or len(str(c.cget("text") or "")) > 40):
                    if not int(float(c.cget("wraplength") or 0)):
                        c.configure(justify="left")
                    labs.append(c)
                walk(c)
        walk(sf.inner)

        def conf(_e=None):
            try:
                width = sf.canvas.winfo_width()
                base = sf.inner.winfo_rootx()
            except Exception:
                return
            if width < 50:
                return
            for lab in labs:
                try:
                    x = (lab.winfo_rootx() - base) if lab.winfo_ismapped() else 40
                    lab.configure(wraplength=max(160, width - 2 * x - 12))  # marges gauche = droite
                except Exception:
                    pass
        sf.canvas.bind("<Configure>", lambda e: sf.canvas.after_idle(conf), add="+")
        sf.canvas.after(150, conf)
        sf.canvas.after(600, conf)

    def _theme_changed(self, theme: str):
        if theme == THEME:
            return
        self.cfg["theme"] = theme
        save_cfg(self.cfg)
        if self._smoke:
            self.cfg["theme"] = THEME
            return
        busy = any(j["status"] in ("cours", "attente") for j in self.jobs)
        if busy:
            messagebox.showinfo(APP_NAME, "Le nouveau thème sera appliqué au prochain démarrage\n"
                                "(un archivage est en cours).", parent=self)
            return
        if messagebox.askyesno(APP_NAME, f"Thème « {THEME_LABELS.get(theme, theme)} » enregistré.\n\n"
                               "Relancer l'Archiveur maintenant pour l'appliquer ?", parent=self):
            self._relaunch()

    def _relaunch(self):
        try:
            self._autosave_tn()
        except Exception:
            pass
        try:
            self.player.stop()
        except Exception:
            pass
        release_single_instance()
        exe = sys.executable
        if sys.platform.startswith("win") and exe.lower().endswith("python.exe"):
            cand = exe[:-10] + "pythonw.exe"
            if os.path.isfile(cand):
                exe = cand
        try:
            kw: Dict[str, Any] = {"close_fds": True}
            if sys.platform.startswith("win"):
                kw["creationflags"] = CREATE_NO_WINDOW
            subprocess.Popen([exe, os.path.abspath(__file__), "--wait-lock"], **kw)
        except Exception as ex:
            logger.exception("relance")
            messagebox.showerror(APP_NAME, f"Relance impossible : {ex}\nRelance l'Archiveur à la main.", parent=self)
            return
        self.destroy()

    # ---------------------------------------------------------------- taille du texte
    def _fs_update(self):
        d = int(self.cfg.get("font_delta") or 0)
        try:
            self._fs_lab.configure(text=("normal" if d == 0 else f"{d:+d}"))
        except Exception:
            pass

    def _font_step(self, step: int, reset: bool = False):
        cur = int(self.cfg.get("font_delta") or 0)
        new = 0 if reset else max(FONT_DELTA_MIN, min(FONT_DELTA_MAX, cur + step))
        if new == cur and not reset:
            self.status.set("🔠 Taille du texte : limite atteinte.")
            return
        self.cfg["font_delta"] = new
        init_fonts(self, new)
        self._apply_row_heights()
        self._relayout_flows(self)
        self._last_pw = None
        self._do_resize()
        self._fs_update()
        if self._save_cfg_job:
            try:
                self.after_cancel(self._save_cfg_job)
            except Exception:
                pass
        self._save_cfg_job = self.after(600, lambda: save_cfg(self.cfg))
        self.status.set(f"🔠 Taille du texte : {'normale' if new == 0 else f'{new:+d}'}  (Ctrl+0 = normale)")

    def _relayout_flows(self, w):
        try:
            for c in w.winfo_children():
                if isinstance(c, FlowFrame):
                    c.relayout()
                self._relayout_flows(c)
        except Exception:
            pass

    def _apply_row_heights(self):
        style = ttk.Style(self)
        ls = font_px(self, FONT_SM)
        style.configure("Arch.Treeview", rowheight=max(52, ls + 10))
        style.configure("Files.Treeview", rowheight=max(22, ls + 8))
        style.configure("Queue.Treeview", rowheight=max(22, ls + 8))
        style.configure("Coll.Treeview", rowheight=max(28, font_px(self, FONT_UI) + 12))

    # ---------------------------------------------------------------- aide
    def open_help(self):
        win = self._dialog("aide", 860, 680)
        self._help_win = win
        fr, txt = self._scrolled_text(win, height=30, bg=NC_PANEL, fg=NC_TEXT, font=FONT_TEXT)
        fr.pack(fill="both", expand=True, padx=10, pady=(10, 4))
        txt.configure(padx=14, pady=10, spacing1=2, spacing3=2)
        txt.tag_configure("h", foreground=NC_HI, font=FONT_TITLE, spacing1=10)
        txt.tag_configure("k", foreground=NC_HI, font=FONT_MONO)
        for kind, line in HELP_TEXT:
            if kind == "h":
                txt.insert("end", line + "\n", ("h",))
            elif kind == "k":
                k, d = line.split("|", 1)
                txt.insert("end", f"  {k:<22}", ("k",))
                txt.insert("end", d + "\n")
            else:
                txt.insert("end", line + "\n")
        txt.configure(state="disabled")
        row = tk.Frame(win, bg=NC_BG)
        row.pack(fill="x", padx=10, pady=(0, 8))
        self._btn(row, "Fermer", win.destroy, hi=True, font=FONT_UI).pack(side="right")
        self._btn(row, "📜 Ouvrir le journal (archiveur.log)", lambda: self.open_path_safe(LOG_FILE, "fichier")).pack(side="left")
        return win

    # ---------------------------------------------------------------- statistiques
    def open_stats(self):
        st = compute_stats(self.entries, self.archive_root_path())
        win = self._dialog("statistiques", 780, 640)
        self._stats_win = win
        fr, txt = self._scrolled_text(win, height=30, bg=NC_PANEL, fg=NC_TEXT, font=FONT_UI)
        fr.pack(fill="both", expand=True, padx=10, pady=(10, 4))
        txt.configure(padx=12, pady=10)
        f = tkfont.nametofont(FONT_UI, root=self)
        keys = ["Espace libre sur le disque", "Durée totale des médias"] + \
            [platform_label(p) for p in st["by_platform"]] + [c for c, _n in st["collections"]] + \
            [f"{GUI_ONLINE.get(k, ('?', k))[0]}  {GUI_ONLINE.get(k, ('?', k))[1]}" for k in st["online"]]
        c1 = 16 + max(f.measure(k) for k in keys) + 24
        c2 = c1 + f.measure("00000") + f.measure("000,0 Mo") + 28
        c3 = c2 + 24
        txt.configure(tabs=(c1, "left", c2, "right", c3, "left"))
        txt.tag_configure("h", foreground=NC_HI, font=FONT_TITLE, spacing1=10, spacing3=2)
        txt.tag_configure("bar", foreground=NC_OK)
        txt.tag_configure("v", foreground=NC_HI)
        for k in ("online", "offline", "restricted", "unknown"):
            txt.tag_configure("on_" + k, foreground=online_color(k))

        def h(t):
            txt.insert("end", t + "\n", ("h",))

        def line(k, v, tag=""):
            txt.insert("end", f"  {k}", (tag,) if tag else ())
            txt.insert("end", f"\t{v}\n", ("v",))
        h("📊 Vue d'ensemble")
        line("Archives", str(st["count"]))
        line("Espace utilisé", human_size(st["size"]))
        if st.get("free") is not None:
            line("Espace libre sur le disque", human_size(st["free"]))
        line("Durée totale des médias", human_duration(st["duration"]) if st["duration"] else "—")
        line("Favoris", str(st["favorites"]))
        line("Avec transcription", str(st["with_transcript"]))
        h("📺 Par plateforme")
        mx = max([v[0] for v in st["by_platform"].values()] or [1])
        for p, (n, size) in sorted(st["by_platform"].items(), key=lambda kv: -kv[1][0]):
            txt.insert("end", f"  {platform_label(p)}\t{n}\t{human_size(size)}\t")
            txt.insert("end", "█" * max(1, int(20 * n / mx)) + "\n", ("bar",))
        h("📅 Archivées par mois (12 derniers)")
        mm = max([n for _m, n in st["months"]] or [1])
        for m, n in st["months"]:
            txt.insert("end", f"  {m}\t{n}\t\t")
            txt.insert("end", "█" * max(1, int(20 * n / mm)) + "\n", ("bar",))
        h("📡 Originaux en ligne")
        for k, n in sorted(st["online"].items(), key=lambda kv: -kv[1]):
            if k in GUI_ONLINE:
                line(f"{GUI_ONLINE[k][0]}  {GUI_ONLINE[k][1]}", str(n), "on_" + k)
            else:
                line(str(k), str(n))
        if st["collections"]:
            h("📚 Collections")
            for c, n in st["collections"]:
                line(c, str(n))
        if st["tags"]:
            h("🏷 Tags les plus utilisés")
            txt.insert("end", "  " + "   ".join(f"#{t} ({n})" for t, n in st["tags"]) + "\n")
        txt.configure(state="disabled")
        row = tk.Frame(win, bg=NC_BG)
        row.pack(fill="x", padx=10, pady=(0, 8))
        self._btn(row, "Fermer", win.destroy, hi=True, font=FONT_UI).pack(side="right")
        self._btn(row, "📋 Copier", lambda: self._copy_to_clipboard(txt.get("1.0", "end-1c"))).pack(side="left")
        return win

    # ---------------------------------------------------------------- vérification
    def verify_dialog(self):
        win = self._dialog("vérifier les archives", 1000, 600)
        self._verify_win = win
        tk.Label(win, text="✔ Vérification de l'intégrité des archives — rien n'est modifié sans ton accord",
                 bg=NC_BG, fg=NC_HI, font=FONT_UI, anchor="w").pack(fill="x", padx=12, pady=(10, 2))
        top = tk.Frame(win, bg=NC_BG)
        top.pack(fill="x", padx=12)
        media_var = tk.BooleanVar(value=True)
        tk.Checkbutton(top, text="Analyser aussi chaque fichier vidéo/audio (plus long)", variable=media_var,
                       bg=NC_BG, fg=NC_FG, selectcolor=NC_ENTRY_BG, activebackground=NC_BG, activeforeground=NC_HI,
                       font=FONT_SM, highlightthickness=0).pack(side="left")
        state = {"issues": [], "cancel": threading.Event(), "running": False}
        prog_var = tk.StringVar(value="Clique « Lancer » pour vérifier.")
        bar = ttk.Progressbar(win, style="Arch.Horizontal.TProgressbar", maximum=100)
        bar.pack(fill="x", padx=12, pady=(6, 2))
        tk.Label(win, textvariable=prog_var, bg=NC_BG, fg=NC_FG, font=FONT_SM, anchor="w").pack(fill="x", padx=12)
        tfr = tk.Frame(win, bg=NC_BG)
        tfr.pack(fill="both", expand=True, padx=12, pady=6)
        tv = ttk.Treeview(tfr, style="Files.Treeview", columns=("prob", "detail", "action"), show="tree headings",
                          selectmode="extended")
        sb = ttk.Scrollbar(tfr, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        tv.pack(side="left", fill="both", expand=True)
        tv.heading("#0", text="Archive")
        tv.column("#0", width=300, stretch=True)
        for c, t, w in (("prob", "Problème", 230), ("detail", "Détail", 200), ("action", "Correction proposée", 220)):
            tv.heading(c, text=t)
            tv.column(c, width=w, stretch=True)
        row = tk.Frame(win, bg=NC_BG)
        row.pack(fill="x", padx=12, pady=(0, 10))
        b_run = self._btn(row, "▶ Lancer la vérification", lambda: run(), hi=True, font=FONT_UI)
        b_run.pack(side="left")
        b_fix = self._btn(row, "🔧 Réparer automatiquement", lambda: fix(), font=FONT_UI, state="disabled")
        b_fix.pack(side="left", padx=6)
        b_redo = self._btn(row, "🔁 Re-archiver / 🎬 convertir la sélection", lambda: redo(), font=FONT_UI, state="disabled")
        b_redo.pack(side="left", padx=6)
        self._btn(row, "Fermer", lambda: close(), font=FONT_UI).pack(side="right")
        Tooltip(b_fix, "Corrige sans risque : index, fiches, pages HTML, dossiers temporaires.\n"
                       "Ne supprime jamais une archive.")
        Tooltip(b_redo, "Médias illisibles / manquants : re-télécharge depuis l'original.\n"
                        "Vidéos non compatibles : conversion MP4 H.264. (via la file d'attente)")

        def close():
            state["cancel"].set()
            win.destroy()
        win.protocol("WM_DELETE_WINDOW", close)

        def fill(rep):
            tv.delete(*tv.get_children())
            issues = rep.get("issues") or []
            state["issues"] = issues
            for i, it in enumerate(issues):
                tv.insert("", "end", iid=f"v{i}", text=f" {it.get('title') or it.get('folder')}"[:80],
                          values=(it.get("label"), it.get("detail") or "", it.get("fix")))
            n_auto = sum(1 for it in issues if it.get("auto"))
            n_redo = sum(1 for it in issues if it.get("kind") in ("media_unreadable", "no_media", "incompatible"))
            b_fix.configure(state="normal" if n_auto else "disabled", text=f"🔧 Réparer automatiquement ({n_auto})")
            b_redo.configure(state="normal" if n_redo else "disabled")
            if not issues:
                prog_var.set(f"✅ Aucun problème — {rep.get('checked', 0)} archive(s) vérifiée(s).")
            else:
                prog_var.set(f"⚠ {len(issues)} problème(s) sur {rep.get('checked', 0)} archive(s) vérifiée(s) "
                             f"— {n_auto} réparable(s) automatiquement.")
            bar.configure(value=100)

        def run():
            if state["running"]:
                return
            state["running"] = True
            state["cancel"] = threading.Event()
            b_run.configure(state="disabled")
            root = self.archive_root_path()

            def p(i, n, name):
                self.ui(lambda: (bar.configure(value=i * 100.0 / max(1, n)), prog_var.set(f"{i}/{n} · {name[:80]}"))
                        if win.winfo_exists() else None)

            def job():
                rep: Dict[str, Any] = {}
                try:
                    rep = verify_archives(root, check_media=bool(media_var.get()), progress=p,
                                          cancel_event=state["cancel"])
                except Exception as ex:
                    logger.exception("vérification")
                    rep = {"issues": [], "error": friendly_error(ex)}

                def done():
                    state["running"] = False
                    if not win.winfo_exists():
                        return
                    b_run.configure(state="normal", text="🔄 Relancer")
                    if rep.get("error"):
                        prog_var.set(f"❌ {rep['error']}")
                        return
                    fill(rep)
                    self.log(f"✔ Vérification : {len(rep.get('issues') or [])} problème(s).")
                self.ui(done)
            threading.Thread(target=job, daemon=True).start()
        self._verify_run = run

        def fix():
            todo = [it for it in state["issues"] if it.get("auto")]
            if not todo:
                return
            st = repair_archives(self.archive_root_path(), todo, self.log)
            messagebox.showinfo(APP_NAME, f"Réparation : {st['ok']} corrigé(s), {st['fail']} échec(s).", parent=win)
            self.refresh_list()
            run()

        def redo():
            sel = [state["issues"][int(i[1:])] for i in tv.selection()] or state["issues"]
            conv, urls = [], []
            for it in sel:
                f = str(it.get("folder"))
                if it.get("kind") == "incompatible":
                    conv.append((f, str(it.get("title") or f)))
                elif it.get("kind") in ("media_unreadable", "no_media"):
                    info = load_info(os.path.join(self.archive_root_path(), f))
                    u = str(info.get("webpage_url") or info.get("url") or "")
                    if u:
                        urls.append(u)
            if conv:
                self._enqueue_convert(conv)
            if urls:
                self.enqueue_urls(urls, ask_dups=False)
            prog_var.set(f"Ajouté à la file : {len(conv)} conversion(s), {len(urls)} re-archivage(s).")

        def dbl(_e=None):
            sel = tv.selection()
            if sel:
                self.select_folder(state["issues"][int(sel[0][1:])].get("folder"))
        tv.bind("<Double-Button-1>", dbl)
        return win

    # ---------------------------------------------------------------- outils média
    def open_media_tools(self):
        path = self._preview_path
        main = find_main_media(path) if path else None
        if not main:
            messagebox.showinfo(APP_NAME, "Cette archive ne contient ni vidéo ni audio.", parent=self)
            return
        if not find_ffmpeg():
            messagebox.showwarning(APP_NAME, "ffmpeg est requis pour les outils média.", parent=self)
            return
        is_vid = main.lower().endswith(VIDEO_EXTS)
        dur = 0.0
        try:
            dur = float(self._preview_info.get("duration") or 0) or float(probe_duration(main) or 0)
        except Exception:
            dur = 0.0
        win = self._dialog("outils média", 740, 500)
        self._media_win = win
        title = str(self._preview_info.get("title") or os.path.basename(path))
        tk.Label(win, text="✂ Outils média", bg=NC_BG, fg=NC_HI, font=FONT_TITLE, anchor="w").pack(fill="x", padx=14, pady=(12, 0))
        wrap_labs: List[Any] = []
        head = tk.Label(win, text=f"{title[:120]}\n{os.path.basename(main)} · durée {fmt_ts(dur) if dur else '?'}",
                        bg=NC_BG, fg=NC_FG, font=FONT_SM, anchor="w", justify="left", wraplength=680)
        head.pack(fill="x", padx=14)
        wrap_labs.append((head, 40))
        grid = tk.Frame(win, bg=NC_BG)
        grid.pack(fill="x", padx=14, pady=10)
        cur = self.player.current() if self.player.state == "play" else float(self.pos_var.get() or 0)
        start_var = tk.StringVar(value=fmt_ts(cur) if cur > 0.5 else "0:00")
        end_var = tk.StringVar(value="")
        for r, (lab, var, tip) in enumerate((("Début :", start_var, "ex. 1:23 ou 83 ou 1m23s"),
                                             ("Fin :", end_var, "vide = jusqu'à la fin (GIF : 20 s max)"))):
            tk.Label(grid, text=lab, bg=NC_BG, fg=NC_FG, font=FONT_UI).grid(row=r, column=0, sticky="w", pady=3)
            ent = tk.Entry(grid, textvariable=var, width=12, bg=NC_ENTRY_BG, fg=NC_ENTRY_FG, insertbackground=NC_FG,
                           font=FONT_UI)
            ent.grid(row=r, column=1, sticky="w", padx=6)
            b = self._btn(grid, "= position du lecteur",
                          lambda v=var: v.set(fmt_ts(self.player.current() if self.player.state == "play"
                                                     else float(self.pos_var.get() or 0))))
            b.grid(row=r, column=2, sticky="w", padx=4)
            tk.Label(grid, text=tip, bg=NC_BG, fg=NC_DIM, font=FONT_SM, justify="left",
                     wraplength=240).grid(row=r, column=3, sticky="w", padx=6)
        precise_var = tk.BooleanVar(value=False)
        tk.Checkbutton(win, text="Coupe précise à l'image près (ré-encodage, plus lent)", variable=precise_var,
                       bg=NC_BG, fg=NC_FG, selectcolor=NC_ENTRY_BG, activebackground=NC_BG, activeforeground=NC_HI,
                       font=FONT_SM, highlightthickness=0, state="normal" if is_vid else "disabled").pack(anchor="w", padx=14)
        hint = tk.Label(win, text="Sans coupe précise, l'extrait commence à l'image clé la plus proche (instantané, sans perte).",
                        bg=NC_BG, fg=NC_DIM, font=FONT_SM, anchor="w", justify="left", wraplength=640)
        hint.pack(fill="x", padx=38)
        wrap_labs.append((hint, 90))
        acts = FlowFrame(win)
        acts.pack(fill="x", padx=14, pady=(12, 4))
        status = tk.Label(win, text="Les fichiers sont créés dans le sous-dossier extraits/ de l'archive.",
                          bg=NC_BG, fg=NC_FG, font=FONT_SM, anchor="w", justify="left", wraplength=600)
        status.pack(fill="x", padx=14, pady=(8, 0))
        wrap_labs.append((status, 40))

        def _wrap(e):
            if e.widget is not win:
                return
            for lab, m in wrap_labs:
                try:
                    lab.configure(wraplength=max(200, e.width - m))
                except Exception:
                    pass
        win.bind("<Configure>", _wrap, add="+")
        btns: List[Any] = []
        open_btn = self._btn(win, "📂 Ouvrir le résultat", lambda: None)

        def parse() -> Optional[Tuple[float, Optional[float]]]:
            s = parse_timecode(start_var.get() or "0")
            e_txt = end_var.get().strip()
            e = parse_timecode(e_txt) if e_txt else None
            if s is None or (e_txt and e is None):
                status.configure(text="⚠ Temps invalide — écris par exemple 1:23, 83 ou 1m23s.", fg=NC_ERR)
                return None
            return s, e

        def run(kind: str):
            rng = parse()
            if rng is None:
                return
            s, e = rng
            for b in btns:
                b.configure(state="disabled")
            status.configure(text="⏳ Traitement ffmpeg en cours…", fg=NC_HI)
            precise = bool(precise_var.get())

            def job():
                out, err = "", ""
                try:
                    if kind == "capture":
                        out = media_capture(main, s, path)
                    elif kind == "clip":
                        out = media_clip(main, s, e, path, precise=precise)
                    elif kind == "audio":
                        full = (s <= 0.01 and e is None)
                        out = media_audio(main, path, None if full else s, None if full else e)
                    elif kind == "gif":
                        out = media_gif(main, s, e if e is not None else s + 6, path)
                except Exception as ex:
                    logger.warning("outil média %s : %s", kind, ex)
                    err = friendly_error(ex)

                def done():
                    if not win.winfo_exists():
                        return
                    for b in btns:
                        b.configure(state="normal" if (is_vid or b is btns[2]) else "disabled")
                    if err:
                        status.configure(text=f"❌ {err}", fg=NC_ERR)
                        return
                    try:
                        sz = human_size(os.path.getsize(out))
                    except OSError:
                        sz = ""
                    status.configure(text=f"✅ Créé : {EXTRACTS_DIR}/{os.path.basename(out)} ({sz})", fg=NC_OK)
                    open_btn.configure(command=lambda: self._open_media(out, "fichier"))
                    open_btn.pack(anchor="w", padx=14, pady=6)
                    self.log(f"✂ {os.path.basename(out)} créé ({sz}).")
                    if self._preview_path == path:
                        self._render_extracts(path, main)
                        self._render_files()
                self.ui(done)
            threading.Thread(target=job, daemon=True).start()

        for key, txt, tip in (("capture", "📸 Capture image", "Image JPEG à la position « Début »"),
                              ("clip", "✂ Extrait vidéo", "Vidéo MP4 de « Début » à « Fin »"),
                              ("audio", "🎵 Audio MP3", "Son en MP3 (toute la durée si Début = 0 et Fin vide)"),
                              ("gif", "🎞 GIF animé", "GIF de « Début » à « Fin » (6 s si Fin vide, 20 s max)")):
            b = acts.add(self._btn(acts, txt, lambda k=key: run(k), hi=(key == "clip"), font=FONT_UI), tip)
            btns.append(b)
            if not is_vid and key != "audio":
                b.configure(state="disabled")
        row = tk.Frame(win, bg=NC_PANEL)
        row.pack(fill="x", side="bottom")
        self._btn(row, "Fermer", win.destroy, font=FONT_UI).pack(side="right", padx=10, pady=6)
        self._media_run = run
        return win

    # ---------------------------------------------------------------- yt-dlp
    def update_ytdlp_ui(self):
        if getattr(self, "_ytdlp_busy", False):
            return
        self._ytdlp_busy = True
        self.status.set("⬆ Mise à jour de yt-dlp…")

        def job():
            try:
                ok, old, new = update_ytdlp(self.log)
            except Exception as ex:
                logger.exception("maj yt-dlp")
                ok, old, new = False, "", friendly_error(ex)

            def done():
                self._ytdlp_busy = False
                if ok and old != new:
                    messagebox.showinfo(APP_NAME, f"yt-dlp mis à jour : {old} → {new}\n\n"
                                        "Relance l'Archiveur pour utiliser la nouvelle version.", parent=self)
                elif ok:
                    messagebox.showinfo(APP_NAME, f"yt-dlp est déjà à jour ({new}).", parent=self)
                else:
                    messagebox.showerror(APP_NAME, "Mise à jour de yt-dlp impossible (pas de connexion ?).\n"
                                         "Détails dans le journal (📜 Journal en bas).", parent=self)
            self.ui(done)
        threading.Thread(target=job, daemon=True).start()

    # ------------------------------------------------------------ v5 : raccourcis / glisser-déposer
    def _in_text_field(self, event) -> bool:
        try:
            return event.widget.winfo_class() in ("Entry", "Text", "TEntry", "TCombobox", "Spinbox")
        except Exception:
            return False

    def _bind_v5_keys(self):
        self.bind("<F1>", lambda e: (self.open_help(), "break")[1])
        self.bind("<F5>", lambda e: (self.refresh_list(), "break")[1])
        for seq in ("<Control-d>", "<Control-D>"):
            self.bind(seq, lambda e: (self.toggle_favorite(), "break")[1])
        for seq in ("<Control-e>", "<Control-E>"):
            self.bind(seq, lambda e: (self.export_zip_dialog("selection"), "break")[1])
        self.bind("<Control-space>", lambda e: (self.player_toggle(), "break")[1])
        self.bind("<Control-Left>", lambda e: None if self._in_text_field(e) else (self.player_skip(-10), "break")[1])
        self.bind("<Control-Right>", lambda e: None if self._in_text_field(e) else (self.player_skip(10), "break")[1])
        for seq in ("<Control-plus>", "<Control-equal>", "<Control-KP_Add>"):
            self.bind(seq, lambda e: (self._font_step(1), "break")[1])
        for seq in ("<Control-minus>", "<Control-KP_Subtract>"):
            self.bind(seq, lambda e: (self._font_step(-1), "break")[1])
        for seq in ("<Control-0>", "<Control-KP_0>", "<Control-KP_Insert>"):
            self.bind(seq, lambda e: (self._font_step(0, reset=True), "break")[1])

    def _setup_dnd(self):
        """Glisser-déposer (module optionnel tkinterdnd2) : liens, texte, fichiers .txt/.url."""
        self._dnd_ok = False
        try:
            import tkinterdnd2  # type: ignore
            from tkinterdnd2 import DND_FILES, DND_TEXT  # type: ignore
            req = getattr(tkinterdnd2.TkinterDnD, "_require", None) or getattr(tkinterdnd2.TkinterDnD, "require", None)
            req(self)
            for w in (self.url_text, self.tree, self.thumb_label, self.pscroll.canvas, self.hpane):
                w.drop_target_register(DND_FILES, DND_TEXT)
                w.dnd_bind("<<Drop>>", self._on_drop)
            self._dnd_ok = True
            self.log("Glisser-déposer actif : dépose un lien ou un fichier .txt de liens sur la fenêtre.")
        except ImportError:
            pass
        except Exception as ex:
            logger.warning("glisser-déposer indisponible : %s", ex)

    def _on_drop(self, event):
        data = getattr(event, "data", "") or ""
        urls: List[str] = []
        try:
            items = list(self.tk.splitlist(data))
        except Exception:
            items = [data]
        for it in items:
            if os.path.isfile(it):
                if it.lower().endswith((".txt", ".url", ".html", ".htm", ".csv", ".md", ".json", ".webloc")):
                    try:
                        with open(it, "r", encoding="utf-8", errors="replace") as f:
                            urls += extract_urls(f.read(2_000_000))
                    except OSError:
                        pass
            else:
                urls += extract_urls(it)
        if not urls:
            urls = extract_urls(data)
        if not urls:
            self.status.set("Glisser-déposer : aucun lien http(s) trouvé.")
            return getattr(event, "action", "copy")
        self._url_ph = False
        self.url_text.delete("1.0", "end")
        self.url_text.insert("1.0", "\n".join(urls))
        self.log(f"🖱 Déposé : {len(urls)} lien(s)")
        self.after(50, lambda: self.enqueue_urls(urls))
        return getattr(event, "action", "copy")

    # ------------------------------------------------------------ v5 : tests automatiques (--smoke / --shot)
    def _first_entry(self, pred) -> Optional[Dict[str, Any]]:
        for e in self._visible:
            p = os.path.join(self.archive_root_path(), str(e.get("folder")))
            try:
                if pred(e, p):
                    return e
            except Exception:
                continue
        return None

    def _scroll_to_widget(self, w):
        try:
            self.update_idletasks()
            inner_h = max(1, self.pscroll.inner.winfo_height())
            self.pscroll.canvas.yview_moveto(max(0.0, (w.winfo_y() - 10) / float(inner_h)))
        except Exception:
            logger.exception("scroll")

    def _do_shot_action(self):
        action, _, sub = (self._shot_action or "").partition("@")
        try:
            if sub:
                e = self._first_entry(lambda e, p: sub.lower() in str(e.get("folder")).lower())
                if e:
                    self.select_folder(e.get("folder"))
                    self.update()
            if action == "play":
                if not self._player_media:
                    e = self._first_entry(lambda e, p: bool(find_main_media(p)))
                    if e:
                        self.select_folder(e.get("folder"))
                self.player_toggle()
            elif action == "settings":
                self.open_settings()
            elif action == "help":
                self.open_help()
            elif action == "stats":
                self.open_stats()
            elif action == "verify":
                self.verify_dialog()
                self._verify_run()
            elif action == "media":
                self.open_media_tools()
            elif action == "multi":
                self._tree_select_all()
            elif action == "transcript":
                self._scroll_to_widget(self.tr_box)
            elif action == "extracts":
                self._scroll_to_widget(self.ex_box)
            elif action == "storyboard":
                self._scroll_to_widget(self.sb_title)
            elif action == "card":
                self._scroll_to_widget(self.card)
            elif action == "queue":
                self._show_bottom("log")
        except Exception as ex:
            self._tk_error(type(ex), ex, ex.__traceback__)

    def _smoke_v5_steps(self) -> List[Any]:
        safe = bool(self._root_override)
        st: List[Any] = []
        st.append(self._refresh_filter_values)
        st += [lambda: self.coll_tree.selection_set("c::" + COLL_NONE), 300,
               lambda: self.coll_tree.selection_set("c::"), 300,
               lambda: self._build_move_menu().destroy(), lambda: self._update_suggest_banner(),
               lambda: print(f"SMOKE_SUGGEST {self._sug}", flush=True),
               lambda: self._toggle_coll_side(), 200, lambda: self._toggle_coll_side()]
        if safe:
            st += [lambda: self.auto_classify(), 600,
                   lambda: getattr(self, "_auto_win", None) and self._auto_win.destroy(),
                   lambda: self._apply_auto_plan(plan_auto_collections(self.entries, load_collections(
                       self.archive_root_path(), self.entries), self.archive_root_path()),
                       load_collections(self.archive_root_path(), self.entries)), 500,
                   lambda: print("SMOKE_CLASSES " + str(sorted(self._coll_map.keys())), flush=True),
                   lambda: self.undo_auto_classify(), 500,
                   lambda: print("SMOKE_UNDO " + str(sorted(self._coll_map.keys())), flush=True)]
        for lab in list(self._coll_map.keys()) + [COLL_ALL_LABEL]:
            st.append(lambda l=lab: (self.coll_var.set(l), self.apply_filter()))
        st.append(lambda: self.search_var.set("zoo"))
        st.append(400)
        st.append(lambda: self.search_var.set(""))
        st.append(400)
        vid = self._first_entry(lambda e, p: bool(find_main_media(p)) and find_main_media(p).lower().endswith(VIDEO_EXTS))
        if vid:
            st += [lambda: self.select_folder(vid.get("folder")), self.player_toggle, 2500,
                   lambda: print(f"SMOKE_PLAYER state={self.player.state} pos={self.player.current():.2f} "
                                 f"frames={self.player._frame_idx} audio={'oui' if self.player._aclock else 'non'}",
                                 flush=True),
                   self.player_toggle, 300, lambda: self.player_skip(10), 600, lambda: self.player_skip(-5), 600,
                   self.player_toggle, 1500, self.player_mute, 400, self.player_mute, 600,
                   lambda: self.player_seek_to(1.0), 800, self.player_stop, 300,
                   lambda: self.tr_search.set("the"), 400, self._tr_find_next, self._tr_copy,
                   lambda: self.tr_search.set(""),
                   lambda: (self.open_media_tools(), None)[1], 300]
            if safe:
                st += [lambda: self._media_run("capture"), 3000]
            st += [lambda: self._media_win.destroy(), self._build_more_menu, lambda: self._build_more_menu().destroy()]
        web = self._first_entry(lambda e, p: os.path.isfile(os.path.join(p, "lecture.html")))
        if web:
            st += [lambda: self.select_folder(web.get("folder")), 300, lambda: self.pscroll.scroll_units(30)]
        st += [lambda: self.open_settings(), 400, lambda: self._settings_win.destroy(),
               lambda: self.open_help(), 300, lambda: self._help_win.destroy(),
               lambda: self.open_stats(), 300, lambda: self._stats_win.destroy(),
               lambda: self._build_tools_menu().destroy(), lambda: self._build_coll_menu().destroy(),
               lambda: self.verify_dialog(), lambda: self._verify_run(), 4000, lambda: self._verify_win.destroy(),
               lambda: self._font_step(2), 300, lambda: self._font_step(-2), 300, lambda: self._font_step(0, reset=True),
               lambda: self._tree_select_all(), 200, lambda: self._update_states(),
               lambda: self._on_drop(type("E", (), {"data": "pas de lien ici", "action": "copy"})()),
               lambda: self.check_online_selected(False), 4000]
        if safe:
            st += [self.toggle_favorite, 300, self.toggle_favorite, 300,
                   lambda: export_catalog(self._visible, os.path.join(self.archive_root_path(), "_smoke_catalogue.csv"))]
        st += [lambda: self._visible and self.select_folder(self._visible[0].get("folder")), 300]
        return st

    # ------------------------------------------------------------ fermeture / test
    def _on_close(self):
        if any(j["status"] in ("cours", "attente") for j in self.jobs) and not self._smoke:
            if not messagebox.askyesno(APP_NAME, "Un archivage est en cours.\nQuitter quand même ?", parent=self):
                return
            self._cancel_event.set()
        try:
            self._autosave_tn()
        except Exception:
            pass
        try:
            self.player.stop()
        except Exception:
            pass
        if self._save_cfg_job:
            save_cfg(self.cfg)
        release_single_instance()
        self.destroy()

    def _smoke_run(self):
        """--smoke N : parcourt les aperçus, filtres, tri, lot, puis ferme."""
        steps: List[Callable[[], None]] = []
        for e in list(self._visible):
            steps.append(lambda e=e: self.select_folder(e.get("folder")))
            steps.append(lambda: self.pscroll.scroll_units(10))
        steps += [
            lambda: self.search_var.set("zoo"),
            lambda: self.apply_filter(),
            lambda: self.search_var.set(""),
            lambda: self.sort_var.set(LABEL_BY_SORT["size_desc"]),
            lambda: self.apply_filter(),
            lambda: self.sort_var.set(LABEL_BY_SORT["date_desc"]),
            lambda: self.apply_filter(),
            lambda: self.open_batch_dialog(),
            lambda: self._batch_win.destroy(),
            lambda: self._on_clip_urls(["https://www.youtube.com/watch?v=jNQXAC9IVRw"]),
            lambda: self._hide_clip_banner(),
            lambda: self._refresh_queue_view(),
            lambda: self._do_resize(),
            lambda: self._show_bottom("queue"),
            lambda: self._show_bottom("log"),
            lambda: self._collapse_bottom(),
            lambda: self._tree_columns(),
            lambda: self.opts_flow.relayout(),
            lambda: self._update_states(),
            lambda: self._url_placeholder(),
        ]
        steps += self._smoke_v5_steps()

        def run(i=0):
            if i < len(steps):
                delay = 150
                if isinstance(steps[i], int):
                    delay = steps[i]
                else:
                    try:
                        steps[i]()
                    except Exception as ex:
                        self._tk_error(type(ex), ex, ex.__traceback__)
                self.after(delay, lambda: run(i + 1))
            else:
                self.after(int(self._smoke * 1000), self._smoke_end)
        run()

    def _smoke_end(self):
        print(f"SMOKE_RESULT errors={len(self._errors)} entries={len(self.entries)} visible={len(self._visible)}", flush=True)
        for er in self._errors:
            print("SMOKE_ERROR", er, flush=True)
        self._smoke_code = 1 if self._errors else 0
        self.destroy()


# ================================================================= CLI
def _cli_log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    logger.info(msg)
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("ascii", "replace").decode("ascii"), flush=True)


def _cli_ensure_ytdlp() -> bool:
    if ensure_ytdlp(_cli_log, ask_install=True, parent=None):
        return True
    try:
        import yt_dlp  # noqa: F401
        return True
    except ImportError:
        _cli_log("Impossible d'importer yt_dlp")
        return False


def run_cli(urls: List[str], root: Optional[str] = None, cookies_browser: Optional[str] = None,
            quality: Optional[str] = None, subtitles: Optional[bool] = None, storyboard: bool = True,
            tags: str = "", notes: str = "", force: bool = False, page_mode: bool = False) -> int:
    cfg = load_cfg()
    archive_root = root or cfg.get("archive_root") or DEFAULT_ROOT
    os.makedirs(archive_root, exist_ok=True)
    quality = quality or cfg.get("quality") or "best"
    subtitles = cfg.get("subtitles", True) if subtitles is None else subtitles
    if not _cli_ensure_ytdlp():
        return 2
    _cli_log(f"ffmpeg: {find_ffmpeg() or 'non'}")
    entries = sync_index_with_disk(archive_root)
    rc = 0
    for url in urls:
        dups = find_duplicates(entries, url)
        if dups and not force:
            _cli_log(f"DOUBLON: déjà archivé ({len(dups)}x) -> {dups[0].get('folder')} — ajoutez --force pour re-archiver")
            print(json.dumps({"duplicate": True, "folder": dups[0].get("folder")}, ensure_ascii=False))
            continue
        try:
            info = archive_url(url, archive_root, _cli_log, cookies_browser=cookies_browser,
                               quality=quality, subtitles=bool(subtitles), storyboard=storyboard,
                               tags=parse_tags(tags), notes=notes, page_mode=page_mode,
                               web_capture=bool(cfg.get("web_capture", True)),
                               use_fx=bool(cfg.get("x_fxtwitter", True)),
                               auto_convert=bool(cfg.get("auto_convert", True)))
            entry = register_archive(archive_root, info)
            entries = load_archive_index(archive_root)
            _cli_log(f"OK folder={entry['folder']} method={entry.get('method')}")
            print(json.dumps(entry, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.exception("CLI %s", url)
            _cli_log(f"FAIL: {friendly_error(e)}")
            traceback.print_exc()
            rc = 1
    return rc


def _run_v5_cli(args, root: str) -> Optional[int]:
    """Commandes v5 en ligne de commande. None = rien à faire ici (suite normale)."""
    if args.verify:
        rep = verify_archives(root, check_media=not args.no_media_check,
                              progress=lambda i, n, f: None)
        issues = rep["issues"]
        _cli_log(f"Vérification : {rep['checked']} archive(s) vérifiée(s), {len(issues)} problème(s).")
        for it in issues:
            print(f"  [{it['kind']}] {it['folder']} — {it['label']}" + (f" : {it['detail']}" if it.get("detail") else "")
                  + f"  → {it['fix']}" + (" (auto)" if it.get("auto") else ""), flush=True)
        if args.repair and issues:
            st = repair_archives(root, [x for x in issues if x.get("auto")], _cli_log)
            _cli_log(f"Réparation : {st['ok']} corrigé(s), {st['skip']} ignoré(s), {st['fail']} échec(s).")
            rep2 = verify_archives(root, check_media=False)
            _cli_log(f"Après réparation : {len(rep2['issues'])} problème(s) restant(s) (hors médias).")
        return 0 if not issues or args.repair else 1
    if args.check_online:
        entries = sync_index_with_disk(root)
        folders = args.folders or [str(e.get("folder")) for e in entries]
        counts = check_online_many(root, folders, progress=lambda d, n, f, s: _cli_log(f"{d}/{n} {ONLINE_ICONS.get(s, '')} {s:<10} {f}"))
        _cli_log("Résultat : " + ", ".join(f"{k}={v}" for k, v in counts.items()))
        return 0
    if args.export_zip:
        entries = sync_index_with_disk(root)
        folders = args.folders or [str(e.get("folder")) for e in entries]
        n, size = export_zip(root, folders, args.export_zip, progress=lambda i, t, f: _cli_log(f"{i}/{t} {f}"))
        _cli_log(f"ZIP : {args.export_zip} — {n} fichiers, {human_size(size)}")
        return 0
    if args.export_catalog:
        entries = sync_index_with_disk(root)
        n = export_catalog(entries, args.export_catalog)
        _cli_log(f"Catalogue : {n} ligne(s) → {args.export_catalog}")
        return 0
    if args.stats:
        st = compute_stats(sync_index_with_disk(root), root)
        print(json.dumps(st, ensure_ascii=False, indent=2, default=str))
        return 0
    if args.transcript or args.whisper or args.media_test:
        target = args.transcript or args.whisper or args.media_test
        fp = target if os.path.isabs(target) else os.path.join(root, target)
        if not os.path.isdir(fp):
            _cli_log(f"Dossier introuvable : {fp}")
            return 2
        if args.transcript:
            d = build_transcript(fp, force=True)
            if not d:
                _cli_log("Aucun sous-titre exploitable dans ce dossier.")
                return 1
            refresh_entries(root, [os.path.basename(fp)])
            _cli_log(f"Transcription : {len(d['cues'])} passages ({d.get('lang')}) → {TRANSCRIPT_TXT}")
            for t, x in d["cues"][:5]:
                print(f"  [{fmt_ts(t)}] {x}", flush=True)
            return 0
        if args.whisper:
            if not whisper_available():
                _cli_log("faster-whisper n'est pas installé (setup_padawan.bat → option Whisper).")
                return 2
            d = transcribe_whisper(fp, _cli_log, model_size=str(load_cfg().get("whisper_model") or "base"))
            refresh_entries(root, [os.path.basename(fp)])
            _cli_log(f"Whisper : {len(d['cues'])} passages ({d.get('lang')})")
            return 0
        main = find_main_media(fp)
        if not main or not main.lower().endswith(VIDEO_EXTS):
            _cli_log("Pas de vidéo dans ce dossier.")
            return 2
        dur = probe_duration(main) or 10
        a, b = min(1.0, dur / 4), min(dur, 1.0 + min(4.0, dur / 2))
        ok = True
        for label, fn in (("capture", lambda: media_capture(main, a, fp)),
                          ("extrait (copie)", lambda: media_clip(main, a, b, fp)),
                          ("extrait (précis)", lambda: media_clip(main, a, b, fp, precise=True)),
                          ("audio mp3", lambda: media_audio(main, fp)),
                          ("gif", lambda: media_gif(main, a, b, fp))):
            try:
                out = fn()
                rd, det = probe_readable(out) if not out.lower().endswith(".jpg") else (os.path.getsize(out) > 1000, "")
                _cli_log(f"{'OK ' if rd else 'KO '} {label:<18} {os.path.basename(out)} ({human_size(os.path.getsize(out))}) {det}")
                ok = ok and rd
            except Exception as ex:
                ok = False
                _cli_log(f"KO  {label:<18} {friendly_error(ex)}")
        return 0 if ok else 1
    return None


def main():
    setup_logging()
    parser = argparse.ArgumentParser(description="Archiveur 5 — posts X/FB/YouTube et pages web, archivés en local")
    parser.add_argument("--url", action="append", help="Mode CLI: archiver une URL (répétable)")
    parser.add_argument("--urls-file", help="Fichier texte de liens (un par ligne)")
    parser.add_argument("--root", help="Racine des archives")
    parser.add_argument("--cookies-browser", help="chrome|edge|firefox")
    parser.add_argument("--quality", choices=[k for k, _ in QUALITY_LABELS], help="best|720|480|audio")
    parser.add_argument("--subs", dest="subs", action="store_true", default=None, help="sous-titres FR/EN")
    parser.add_argument("--no-subs", dest="subs", action="store_false")
    parser.add_argument("--no-storyboard", action="store_true")
    parser.add_argument("--tags", default="", help="tags séparés par virgules")
    parser.add_argument("--notes", default="", help="notes perso")
    parser.add_argument("--force", action="store_true", help="re-archiver même si doublon")
    parser.add_argument("--reindex", action="store_true", help="régénérer index.html global + pages")
    parser.add_argument("--search", help="chercher dans l'historique (titre/texte/auteur/tags)")
    parser.add_argument("--platform", help="filtre plateforme pour --search")
    parser.add_argument("--sort", default="date_desc", choices=[k for k, _ in SORT_CHOICES])
    parser.add_argument("--smoke", type=float, default=0.0, help="test UI: ouvre, parcourt, ferme après N s")
    parser.add_argument("--fix-codecs", action="store_true",
                        help="convertir en MP4 H.264/AAC toutes les vidéos archivées non compatibles")
    parser.add_argument("--folder", help="avec --fix-codecs : un seul dossier d'archive")
    parser.add_argument("--geometry", default="", help="test UI : taille forcée, ex. 1024x576")
    parser.add_argument("--shot", default="", help="test UI : capture PNG de la fenêtre puis ferme")
    parser.add_argument("--dpi-aware", action="store_true", help="test UI : pixels physiques, échelle 100 %%")
    # v5
    parser.add_argument("--page", action="append", help="archiver une URL comme page web (lecture + capture + PDF)")
    parser.add_argument("--verify", action="store_true", help="vérifier l'intégrité des archives")
    parser.add_argument("--repair", action="store_true", help="avec --verify : appliquer les réparations sûres")
    parser.add_argument("--no-media-check", action="store_true", help="avec --verify : ne pas analyser les médias")
    parser.add_argument("--check-online", action="store_true", help="vérifier si les originaux sont en ligne")
    parser.add_argument("--export-zip", metavar="DEST", help="exporter en ZIP (toutes, ou --folder répétable)")
    parser.add_argument("--export-catalog", metavar="DEST", help="exporter le catalogue (.csv ou .json)")
    parser.add_argument("--transcript", metavar="FOLDER", help="(re)construire la transcription depuis les sous-titres")
    parser.add_argument("--whisper", metavar="FOLDER", help="transcrire localement avec Whisper (faster-whisper)")
    parser.add_argument("--media-test", metavar="FOLDER", help="tester les outils média sur une archive vidéo")
    parser.add_argument("--stats", action="store_true", help="statistiques des archives")
    parser.add_argument("--folders", action="append", help="dossier(s) d'archive pour --check-online / --export-zip")
    parser.add_argument("--wait-lock", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--font-delta", type=int, default=None, help="test UI : taille du texte (-3 à 8)")
    parser.add_argument("--shot-action", default="", help="test UI : play|settings|help|stats|verify|media|multi|transcript[@dossier]")
    args = parser.parse_args()
    root = args.root or load_cfg().get("archive_root") or DEFAULT_ROOT
    rc = _run_v5_cli(args, root)
    if rc is not None:
        raise SystemExit(rc)
    if args.fix_codecs:
        if not find_ffmpeg():
            _cli_log("ffmpeg introuvable.")
            raise SystemExit(2)
        if args.folder:
            fp = args.folder if os.path.isabs(args.folder) else os.path.join(root, args.folder)
            try:
                r = fix_folder_codecs(fp, _cli_log)
                _cli_log(f"{os.path.basename(fp)} : {r}")
                raise SystemExit(0)
            except SystemExit:
                raise
            except Exception as ex:
                _cli_log(f"ÉCHEC : {friendly_error(ex)}")
                raise SystemExit(1)
        st = fix_codecs_all(root, _cli_log)
        _cli_log(f"Réparation codecs terminée : {st['ok']} converti(s), {st['skip']} ignoré(s), {st['fail']} échec(s).")
        for e in load_archive_index(root):
            fp = os.path.join(root, str(e.get("folder")))
            m = find_main_media(fp)
            if m and m.lower().endswith(VIDEO_EXTS):
                c = probe_codecs(m)
                print(f"  {'OK ' if is_compatible(m, c) else 'NON'} {codec_label(c):<14} {e.get('folder')}", flush=True)
        raise SystemExit(1 if st["fail"] else 0)
    if args.reindex:
        entries = sync_index_with_disk(root, _cli_log)
        for e in entries:
            fp = os.path.join(root, str(e.get("folder")))
            info = load_info(fp)
            if info:
                write_local_index(fp, info)
                fresh = entry_from_info(info, fp)
                e["size"], e["thumb"] = fresh["size"], fresh["thumb"]
        save_archive_index(root, entries)
        _cli_log(f"Index régénéré: {len(entries)} archive(s) -> {os.path.join(root, INDEX_HTML)}")
        if not args.url and not args.search:
            raise SystemExit(0)
    if args.search is not None:
        res = search_entries(sync_index_with_disk(root), args.search, args.platform, args.sort)
        for e in res:
            print(f"{fmt_iso(e.get('archived_at'))} | {e.get('platform')} | {e.get('title')} | tags={e.get('tags')} | {e.get('folder')}")
        print(f"{len(res)} résultat(s)")
        if not args.url:
            raise SystemExit(0)
    if args.page:
        raise SystemExit(run_cli(args.page, root=args.root, cookies_browser=args.cookies_browser,
                                 quality=args.quality, subtitles=args.subs, storyboard=not args.no_storyboard,
                                 tags=args.tags, notes=args.notes, force=True, page_mode=True))
    urls = list(args.url or [])
    if args.urls_file:
        with open(args.urls_file, "r", encoding="utf-8") as f:
            urls += extract_urls(f.read())
    if urls:
        raise SystemExit(run_cli(urls, root=args.root, cookies_browser=args.cookies_browser,
                                 quality=args.quality, subtitles=args.subs,
                                 storyboard=not args.no_storyboard, tags=args.tags, notes=args.notes,
                                 force=args.force))
    if tk is None:
        print("Tkinter indisponible.", file=sys.stderr)
        raise SystemExit(2)
    test_mode = bool(args.smoke or args.shot)
    global _CFG_READONLY
    if test_mode or args.root or args.font_delta is not None:
        _CFG_READONLY = True
    if not test_mode:
        # une seule fenêtre : si l'Archiveur est déjà ouvert, on le ramène au premier plan
        if not acquire_single_instance(wait=15.0 if args.wait_lock else 0.0):
            focus_existing_window()
            logger.info("Déjà ouvert : fenêtre existante ramenée au premier plan.")
            raise SystemExit(0)
    generate_icons(BASE)
    scaling = 0.0
    if args.dpi_aware and sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
            scaling = 96 / 72.0
        except Exception:
            pass
    app = ArchiveurApp(smoke=args.smoke, geometry=args.geometry, shot=args.shot, force_scaling=scaling,
                       root_override=args.root or "", font_delta=args.font_delta, shot_action=args.shot_action)
    app.mainloop()
    if args.smoke or args.shot:
        raise SystemExit(getattr(app, "_smoke_code", 1))


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        setup_logging()
        logger.exception("Erreur fatale")
        try:
            if tk is not None:
                r = tk.Tk()
                r.withdraw()
                messagebox.showerror(APP_NAME, "Erreur au démarrage — détails dans archiveur.log\n\n"
                                     + traceback.format_exc()[-800:])
                r.destroy()
        except Exception:
            pass
        raise
