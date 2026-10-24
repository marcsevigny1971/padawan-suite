#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Messager v2 — messagerie conviviale du Projet Padawan (style MSN Messenger).

v2 : Salon general public par defaut + messages prives (clic sur un usager),
     liste des gens en ligne, "X ecrit...", badges non lus, emojis, repondre,
     modifier/supprimer, glisser-deposer, coller une image, recherche,
     clignotement barre des taches / icone tray, theme, taille de fenetre memorisee.

- Identite sans mot de passe : jeton aleatoire genere localement, protege par DPAPI.
- Serveur par defaut : https://marcsevigny.ca/messager/ (API PHP). Modifiable.
- Statut : Disponible / Absent / Occupe / Invisible. Sondage 5 s a 5 min ou perso.
- Reactions, liens cliquables, apercus (YouTube, X, Facebook, Odysee, OpenGraph),
  images, videos, PDF, fichiers, messages vocaux (enregistrer / ecouter).
Aucune fonction de controle a distance.

Usage : pythonw messager2.py   [--profil NOM] [--cache] [--smoke-api] [--make-icons] [--check]
"""
from __future__ import annotations

import argparse
import base64
import ctypes
import datetime as dt
import hashlib
import io
import json
import mimetypes
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import uuid
import webbrowser
from typing import Any, Callable, Dict, List, Optional, Tuple

IS_WIN = os.name == "nt"
if IS_WIN:
    from ctypes import wintypes

try:
    import requests  # type: ignore
except ImportError:  # pragma: no cover
    requests = None  # type: ignore

try:
    from PIL import Image, ImageDraw, ImageTk  # type: ignore
except ImportError:  # pragma: no cover
    Image = ImageDraw = ImageTk = None  # type: ignore

APP_NAME = "Messager"
APP_TITLE = "Messager"
APP_FILE_VER = 2
DEFAULT_SERVER = "https://marcsevigny.ca/messager/"
_MUTEX_BASE = "Local\\Messager_SingleInstance"
_ENTROPY = b"Messager-Padawan-v1"

STATUTS = [("disponible", "Disponible"), ("absent", "Absent"), ("occupe", "Occupé"), ("invisible", "Invisible")]
STATUT_LABEL = dict(STATUTS)
STATUT_COULEUR = {"disponible": "#33CC55", "absent": "#FFAA33", "occupe": "#E04848", "invisible": "#888888"}
INTERVALLES = [("5 s", 5), ("15 s", 15), ("30 s", 30), ("1 min", 60), ("5 min", 300), ("Perso…", -1)]
REACTIONS = ["❤️", "👍", "😂", "😮", "😢", "🎉"]
URL_RE = re.compile(r"https?://[^\s<>\"']+", re.I)
MAX_UPLOAD = 15 * 1024 * 1024


# ================================================================ chemins / profil
def _base_data_dir() -> str:
    la = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.local/share")
    return os.path.join(la, "Padawan", "Messager")


class Paths:
    profil = "defaut"

    @classmethod
    def data(cls) -> str:
        d = _base_data_dir() if cls.profil == "defaut" else os.path.join(_base_data_dir(), "profils", cls.profil)
        os.makedirs(d, exist_ok=True)
        return d

    @classmethod
    def config(cls) -> str:
        return os.path.join(cls.data(), "messager_config.json")

    @classmethod
    def keyfile(cls) -> str:
        return os.path.join(cls.data(), "messager_cle.dpapi")

    @classmethod
    def cache(cls) -> str:
        d = os.path.join(cls.data(), "cache")
        os.makedirs(d, exist_ok=True)
        return d

    @classmethod
    def log(cls) -> str:
        return os.path.join(cls.data(), "messager.log")


def jlog(msg: str) -> None:
    try:
        with open(Paths.log(), "a", encoding="utf-8") as f:
            f.write(f"{dt.datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")
    except Exception:
        pass


# ================================================================ DPAPI (meme principe que Facteur)
def _dpapi(data: bytes, protect: bool) -> bytes:
    if not IS_WIN:
        raise RuntimeError("DPAPI indisponible hors Windows")
    try:
        import win32crypt  # type: ignore
        if protect:
            return win32crypt.CryptProtectData(data, "Messager", _ENTROPY, None, None, 0x01)
        return win32crypt.CryptUnprotectData(data, _ENTROPY, None, None, 0x01)[1]
    except ImportError:
        pass

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def mk(b: bytes):
        buf = ctypes.create_string_buffer(b, len(b))
        return BLOB(len(b), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf

    crypt32 = ctypes.windll.crypt32
    k32 = ctypes.windll.kernel32
    k32.LocalFree.argtypes = [ctypes.c_void_p]
    bin_, _k1 = mk(data)
    ent, _k2 = mk(_ENTROPY)
    out = BLOB()
    if protect:
        ok = crypt32.CryptProtectData(ctypes.byref(bin_), "Messager", ctypes.byref(ent), None, None, 0x01, ctypes.byref(out))
    else:
        ok = crypt32.CryptUnprotectData(ctypes.byref(bin_), None, ctypes.byref(ent), None, None, 0x01, ctypes.byref(out))
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        k32.LocalFree(ctypes.cast(out.pbData, ctypes.c_void_p))


class Identity:
    """Jeton 32 octets (64 hex) + install_id. Le jeton ne quitte le PC que vers l'API HTTPS."""

    def __init__(self) -> None:
        self._token: Optional[str] = None

    def token(self) -> str:
        if self._token:
            return self._token
        p = Paths.keyfile()
        if os.path.isfile(p):
            blob = open(p, "rb").read()
            if blob.startswith(b"DPAPI1"):
                raw = _dpapi(blob[6:], False)
            elif blob.startswith(b"PLAIN1") and not IS_WIN:
                raw = blob[6:]
            else:
                raise RuntimeError("fichier de cle Messager illisible")
        else:
            raw = os.urandom(32)
            blob = (b"DPAPI1" + _dpapi(raw, True)) if IS_WIN else (b"PLAIN1" + raw)
            tmp = p + ".tmp"
            with open(tmp, "wb") as f:
                f.write(blob)
            os.replace(tmp, p)
            jlog("nouvelle identite creee")
        self._token = raw.hex()
        return self._token

    def fingerprint(self) -> str:
        return hashlib.sha256(self.token().encode()).hexdigest()[:10]


# ================================================================ configuration
def default_config() -> Dict[str, Any]:
    return {
        "serveur": DEFAULT_SERVER,
        "install_id": str(uuid.uuid4()),
        "pseudo": "",
        "statut": "disponible",
        "intervalle": 15,
        "pause_si_indispo": True,
        "notifications": True,
        "son": True,
        "theme": "norton",
        "inscrit": False,
        "user_id": 0,
        "dernier_id": 0,
        "geometrie": "",
        "zoom": False,
        "notif_salon": True,
        "salon_vide_le": 0,
    }


class Config:
    def __init__(self) -> None:
        self.data = default_config()

    def load(self) -> "Config":
        try:
            with open(Paths.config(), "r", encoding="utf-8") as f:
                d = json.load(f)
            self.data.update(d)
        except FileNotFoundError:
            self.save()
        except Exception as e:
            jlog(f"config illisible: {e}")
        return self

    def save(self) -> None:
        tmp = Paths.config() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, Paths.config())

    def __getitem__(self, k):
        return self.data.get(k)

    def __setitem__(self, k, v):
        self.data[k] = v


# ================================================================ client API (avec reprises patientes)
class ApiError(Exception):
    pass


class Api:
    def __init__(self, cfg: Config, ident: Identity) -> None:
        self.cfg, self.ident = cfg, ident
        self.sess = requests.Session() if requests else None
        if self.sess:
            self.sess.headers["User-Agent"] = f"PadawanMessager/{APP_FILE_VER}"

    @property
    def base(self) -> str:
        s = (self.cfg["serveur"] or DEFAULT_SERVER).strip()
        return s if s.endswith("/") else s + "/"

    def call(self, action: str, retries: int = 3, timeout: float = 20, **params) -> Dict[str, Any]:
        if not self.sess:
            raise ApiError("module requests absent (pip install requests)")
        body = dict(params)
        body["action"] = action
        hdr = {"Content-Type": "application/json"}
        if action != "register":
            hdr["Authorization"] = "Bearer " + self.ident.token()
        last: Any = None
        for i in range(max(1, retries)):
            try:
                r = self.sess.post(self.base + "api.php", data=json.dumps(body), headers=hdr, timeout=timeout)
                try:
                    j = r.json()
                except ValueError:
                    raise ApiError(f"réponse non JSON (HTTP {r.status_code})")
                if not j.get("ok"):
                    if r.status_code in (429, 500, 502, 503, 504) and i < retries - 1:
                        last = ApiError(j.get("error") or f"HTTP {r.status_code}")
                        time.sleep(1.5 * (i + 1))
                        continue
                    raise ApiError(j.get("error") or f"HTTP {r.status_code}")
                return j
            except ApiError:
                raise
            except Exception as e:  # reseau
                last = e
                time.sleep(1.5 * (i + 1))
        raise ApiError(f"serveur injoignable : {last}")

    def register(self) -> Dict[str, Any]:
        j = self.call("register", pseudo=self.cfg["pseudo"], install_id=self.cfg["install_id"], token=self.ident.token())
        u = j.get("user") or {}
        self.cfg["inscrit"] = True
        self.cfg["user_id"] = int(u.get("id") or 0)
        self.cfg.save()
        return u

    def media_url(self, att_id: int) -> str:
        return f"{self.base}media.php?id={int(att_id)}"

    def download_media(self, att_id: int, filename: str = "") -> str:
        if not self.sess:
            raise ApiError("requests absent")
        safe = re.sub(r"[^\w.\- ()]", "_", filename or f"media_{att_id}")[:120]
        dest = os.path.join(Paths.cache(), f"{att_id}_{safe}")
        if os.path.isfile(dest) and os.path.getsize(dest) > 0:
            return dest
        last = None
        for i in range(3):
            try:
                r = self.sess.get(self.media_url(att_id), headers={"Authorization": "Bearer " + self.ident.token()}, timeout=60)
                if r.status_code != 200:
                    raise ApiError(f"média HTTP {r.status_code}")
                with open(dest + ".part", "wb") as f:
                    f.write(r.content)
                os.replace(dest + ".part", dest)
                return dest
            except Exception as e:
                last = e
                time.sleep(1.5 * (i + 1))
        raise ApiError(f"téléchargement média : {last}")

    def upload(self, path: str) -> Dict[str, Any]:
        size = os.path.getsize(path)
        if size > MAX_UPLOAD:
            raise ApiError(f"fichier trop gros ({size // 1024 // 1024} Mo, max 15 Mo)")
        mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        j = self.call("upload", timeout=120, filename=os.path.basename(path), mime=mime, data_base64=b64)
        return j["attachment"]


def kind_for_mime(mime: str) -> str:
    if mime.startswith("image/"):
        return "image"
    if mime.startswith("video/"):
        return "video"
    if mime.startswith("audio/"):
        return "audio"
    return "file"


# ================================================================ outils (suite Padawan)
def find_exe(name: str) -> str:
    p = shutil.which(name)
    if p:
        return p
    for cand in (os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Links", name + ".exe"),):
        if os.path.isfile(cand):
            return cand
    return ""


def popen_hidden(args: List[str]) -> Optional[subprocess.Popen]:
    kw: Dict[str, Any] = {}
    if IS_WIN:
        kw["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
    try:
        return subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kw)
    except Exception as e:
        jlog(f"popen {args[:1]}: {e}")
        return None


def open_path(p: str) -> None:
    try:
        if IS_WIN:
            os.startfile(p)  # type: ignore[attr-defined]
        else:
            webbrowser.open(p)
    except Exception as e:
        jlog(f"open {p}: {e}")


def play_stream_url(url: str) -> bool:
    """Lit YouTube / Odysee / X / Facebook sans leur appli : yt-dlp -> ffplay (deja dans la suite)."""
    ffplay = find_exe("ffplay")
    ytdlp = find_exe("yt-dlp")
    if ffplay and ytdlp:
        def _go():
            try:
                kw: Dict[str, Any] = {"creationflags": 0x08000000} if IS_WIN else {}
                r = subprocess.run([ytdlp, "-f", "best[height<=720]/best", "-g", url],
                                   capture_output=True, text=True, timeout=60, **kw)
                lines = [l for l in (r.stdout or "").splitlines() if l.startswith("http")]
                if lines:
                    popen_hidden([ffplay, "-autoexit", "-window_title", "Messager — lecture", lines[0]])
                    return
            except Exception as e:
                jlog(f"yt-dlp: {e}")
            webbrowser.open(url)
        threading.Thread(target=_go, daemon=True).start()
        return True
    try:
        import yt_dlp  # noqa: F401
    except Exception:
        pass
    webbrowser.open(url)
    return False


def notify(title: str, msg: str) -> None:
    try:
        from plyer import notification  # type: ignore
        notification.notify(title=title, message=msg[:200], app_name=APP_NAME, timeout=6)
        return
    except Exception:
        pass
    if IS_WIN:
        try:
            ctypes.windll.user32.FlashWindow(ctypes.windll.user32.GetForegroundWindow(), True)
        except Exception:
            pass


# ================================================================ vocal
class Recorder:
    def __init__(self) -> None:
        self.frames: List[Any] = []
        self.stream = None
        self.rate = 22050

    @staticmethod
    def available() -> bool:
        try:
            import sounddevice  # noqa: F401
            import soundfile  # noqa: F401
            import numpy  # noqa: F401
            return True
        except Exception:
            return False

    def start(self) -> None:
        import sounddevice as sd  # type: ignore
        self.frames = []

        def cb(indata, frames, t, status):
            self.frames.append(indata.copy())

        self.stream = sd.InputStream(samplerate=self.rate, channels=1, dtype="int16", callback=cb)
        self.stream.start()

    def stop(self, max_sec: int = 120) -> Optional[str]:
        import numpy as np  # type: ignore
        import soundfile as sf  # type: ignore
        if not self.stream:
            return None
        try:
            self.stream.stop()
            self.stream.close()
        finally:
            self.stream = None
        if not self.frames:
            return None
        data = np.concatenate(self.frames)[: self.rate * max_sec]
        path = os.path.join(Paths.cache(), f"vocal_{dt.datetime.now():%Y%m%d_%H%M%S}.ogg")
        try:
            sf.write(path, data, self.rate, format="OGG", subtype="VORBIS")
        except Exception:
            path = path[:-4] + ".wav"
            sf.write(path, data, self.rate)
        return path


def play_audio(path: str) -> None:
    ffplay = find_exe("ffplay")
    if ffplay:
        popen_hidden([ffplay, "-nodisp", "-autoexit", path])
        return
    try:
        import sounddevice as sd  # type: ignore
        import soundfile as sf  # type: ignore
        data, rate = sf.read(path)
        threading.Thread(target=lambda: (sd.play(data, rate), sd.wait()), daemon=True).start()
        return
    except Exception:
        pass
    open_path(path)


# ================================================================ icones
def make_icon_image(size: int = 256):
    if Image is None:
        return None
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size
    d.rounded_rectangle((s * .06, s * .10, s * .80, s * .66), radius=s * .14, fill=(0, 140, 210, 255))
    d.polygon([(s * .18, s * .62), (s * .30, s * .62), (s * .14, s * .80)], fill=(0, 140, 210, 255))
    d.rounded_rectangle((s * .30, s * .36, s * .94, s * .84), radius=s * .12, fill=(60, 200, 90, 255))
    d.polygon([(s * .78, s * .80), (s * .88, s * .80), (s * .90, s * .96)], fill=(60, 200, 90, 255))
    for i, x in enumerate((.20, .36, .52)):
        d.ellipse((s * x, s * .32, s * (x + .09), s * .41), fill=(255, 255, 255, 255))
    return img


def generate_app_icons(out_dir: str, force: bool = False) -> Tuple[str, str]:
    ico = os.path.join(out_dir, "messager2.ico")
    png = os.path.join(out_dir, "messager2.png")
    png256 = os.path.join(out_dir, "messager2_256.png")
    img = make_icon_image(256)
    if img is None:
        return "", ""
    if force or not os.path.isfile(png256):
        img.save(png256)
    if force or not os.path.isfile(png):
        img.resize((64, 64)).save(png)
    if force or not os.path.isfile(ico):
        img.save(ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return ico, png


# ================================================================ interface Tk
import tkinter as tk  # noqa: E402
from tkinter import filedialog, messagebox, simpledialog, ttk  # noqa: E402

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES  # type: ignore
    _TkBase = TkinterDnD.Tk
except Exception:  # pragma: no cover
    TkinterDnD = None  # type: ignore
    DND_FILES = None  # type: ignore
    _TkBase = tk.Tk

try:
    import pystray  # type: ignore
except Exception:  # pragma: no cover
    pystray = None  # type: ignore

THEMES: Dict[str, Dict[str, str]] = {
    "norton": {"BG": "#0000AA", "PANEL": "#000088", "CARD": "#000066", "FG": "#55FFFF", "HI": "#FFFF55",
               "BTN": "#1A1AC0", "BTN_FG": "#FFFFFF", "ENTRY_BG": "#000044", "ENTRY_FG": "#FFFFFF",
               "SEL": "#AAAA00", "DIM": "#88AACC", "TEXT": "#FFFFFF", "ME": "#004488", "THEM": "#1C1C70",
               "LINK": "#7FD4FF", "LINE": "#3355AA", "ERR": "#FF5555", "OK": "#55FF55", "PUB": "#33CC55", "PRIV": "#FFAA33",
               "QUOTE": "#A0B8E0", "FLASH": "#5555FF"},
    "sombre": {"BG": "#1E1E1E", "PANEL": "#252526", "CARD": "#2D2D30", "FG": "#D4D4D4", "HI": "#FFC83D",
               "BTN": "#3A3D41", "BTN_FG": "#FFFFFF", "ENTRY_BG": "#141414", "ENTRY_FG": "#F0F0F0",
               "SEL": "#C9A227", "DIM": "#8C8C8C", "TEXT": "#F0F0F0", "ME": "#264F78", "THEM": "#38383D",
               "LINK": "#4FC1FF", "LINE": "#45454D", "ERR": "#F1707B", "OK": "#6CCB5F", "PUB": "#6CCB5F", "PRIV": "#FFB454",
               "QUOTE": "#A0A0A0", "FLASH": "#505A70"},
    "clair": {"BG": "#F3F3F3", "PANEL": "#E4E7EB", "CARD": "#FFFFFF", "FG": "#1F3A5F", "HI": "#0B5CAD",
              "BTN": "#DADDE2", "BTN_FG": "#111111", "ENTRY_BG": "#FFFFFF", "ENTRY_FG": "#000000",
              "SEL": "#9CC3EE", "DIM": "#5F6B7A", "TEXT": "#111111", "ME": "#D6E9FF", "THEM": "#ECECEC",
              "LINK": "#0645AD", "LINE": "#B8C0CC", "ERR": "#C62828", "OK": "#1E7B34", "PUB": "#1E7B34", "PRIV": "#C25E00",
              "QUOTE": "#5F6B7A", "FLASH": "#FFF2A8"},
}
THEME_NOMS = {"norton": "Norton (bleu Padawan)", "sombre": "Sombre", "clair": "Clair"}
C: Dict[str, str] = dict(THEMES["norton"])

EMOJIS = ("😀 😁 😂 🤣 😊 😍 😘 😎 🤩 🥳 😉 🙂 🤔 😮 😢 😭 😡 😴 🤯 🥶 "
          "👍 👎 👏 🙌 🙏 💪 👋 🤝 ✌️ 👌 ❤️ 🧡 💛 💚 💙 💜 💔 🔥 ⭐ ✨ "
          "🎉 🎂 🎁 🍕 🍔 🍺 ☕ 🐶 🐱 🚗 ✈️ 🏠 💻 📱 🎮 🎵 📷 ✅ ❌ ❓").split()


def btn(parent, text, cmd, **kw):
    b = tk.Button(parent, text=text, command=cmd, bg=kw.pop("bg", C["BTN"]), fg=C["BTN_FG"],
                  activebackground=C["SEL"], activeforeground=C["BTN_FG"], relief="flat", bd=0,
                  padx=kw.pop("padx", 8), pady=kw.pop("pady", 3), font=kw.pop("font", ("Segoe UI Emoji", 10)),
                  cursor="hand2", **kw)
    base = b.cget("bg")
    b.bind("<Enter>", lambda e: b.configure(bg=C["SEL"]) if str(b["state"]) != "disabled" else None)
    b.bind("<Leave>", lambda e: b.configure(bg=getattr(b, "_bg", base)))
    return b


def _mix(c1: str, c2: str, t: float) -> str:
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{int(x + (y - x) * t):02x}" for x, y in zip(a, b))


def _parse_ts(s: Any) -> dt.datetime:
    try:
        return dt.datetime.strptime(str(s)[:19], "%Y-%m-%d %H:%M:%S")
    except Exception:
        return dt.datetime.now()


def _day_label(d: dt.date) -> str:
    today = dt.date.today()
    if d == today:
        return "Aujourd'hui"
    if d == today - dt.timedelta(days=1):
        return "Hier"
    mois = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
    return f"{d.day} {mois[d.month - 1]} {d.year}"


def flash_taskbar(hwnd: int, stop: bool = False) -> None:
    if not IS_WIN or not hwnd:
        return
    try:
        class FLASHWINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("hwnd", ctypes.c_void_p), ("dwFlags", ctypes.c_uint),
                        ("uCount", ctypes.c_uint), ("dwTimeout", ctypes.c_uint)]
        fi = FLASHWINFO(ctypes.sizeof(FLASHWINFO), hwnd, 0 if stop else (3 | 12), 0, 0)
        ctypes.windll.user32.FlashWindowEx(ctypes.byref(fi))
    except Exception as e:
        jlog(f"flash: {e}")


class MessagerApp(_TkBase):  # type: ignore[misc,valid-type]
    def __init__(self, cfg: Config, ident: Identity, start_hidden: bool = False, mutex: Any = None) -> None:
        super().__init__()
        self.cfg, self.ident, self._mutex = cfg, ident, mutex
        self.api = Api(cfg, ident)
        C.update(THEMES.get(cfg["theme"] or "norton", THEMES["norton"]))
        self.title(APP_TITLE if Paths.profil == "defaut" else f"{APP_TITLE} ({Paths.profil})")
        self._base_title = self.title()
        self.minsize(720, 480)
        self._restore_geometry()
        self.configure(bg=C["BG"])
        self.protocol("WM_DELETE_WINDOW", self.hide)
        here = os.path.dirname(os.path.abspath(__file__))
        self._ico = os.path.join(here, "messager2.ico")
        if not os.path.isfile(self._ico):
            self._ico = os.path.join(here, "messager1.ico")
        try:
            if os.path.isfile(self._ico):
                self.iconbitmap(self._ico)
        except Exception:
            pass
        self.q: "queue.Queue[Callable[[], None]]" = queue.Queue()
        self.users: Dict[int, Dict[str, Any]] = {}
        self.convs: Dict[int, Dict[str, Any]] = {}
        self.peer_conv: Dict[int, int] = {}
        self.conv_peer: Dict[int, int] = {}
        self.pub_id = 0
        self.cur_conv = 0
        self.msgs: Dict[int, List[Dict[str, Any]]] = {}
        self.unread: Dict[int, int] = {}
        self.typing: Dict[int, Tuple[float, List[str]]] = {}
        self._images: List[Any] = []
        self._previews: Dict[str, Dict[str, Any]] = {}
        self._items: List[Tuple[str, int]] = []
        self.recorder = Recorder()
        self.recording = False
        self.reply_to = 0
        self.editing = 0
        self._last_typing_sent = 0.0
        self._server_time = 0
        self._first_poll = True
        self._online = False
        self._fade_n = 0
        self._rerender_job = None
        self._geo_job = None
        self._new_below = 0
        self._dots = 0
        self._tray = None
        self._tray_imgs: List[Any] = []
        self._tray_blink = False
        self._poll_started = False
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._build()
        self._setup_tray()
        self.after(100, self._pump)
        self.after(700, self._check_show_request)
        self.after(450, self._anim_tick)
        if start_hidden:
            self.withdraw()
        elif self.cfg["zoom"]:
            try:
                self.state("zoomed")
            except Exception:
                pass
        self.bind("<FocusIn>", lambda e: self._on_focus())
        self.bind("<Configure>", self._on_configure)
        self.after(300, self._startup)

    # ------------------------------------------------------------ geometrie memorisee
    def _restore_geometry(self) -> None:
        g = str(self.cfg["geometrie"] or "")
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        m = re.match(r"^(\d+)x(\d+)\+(-?\d+)\+(-?\d+)$", g)
        if m:
            w, h, x, y = (int(m.group(i)) for i in range(1, 5))
            if 720 <= w <= sw + 20 and 480 <= h <= sh - 40 and -50 < x < sw - 100 and -10 <= y and y + h <= sh - 30:
                self.geometry(g)
                return
        # taille par defaut qui tient TOUJOURS dans l'ecran (barre des taches comprise)
        w, h = max(720, min(1040, sw - 80)), max(480, min(720, sh - 110))
        self.geometry(f"{w}x{h}+{max(0, (sw - w) // 2)}+{max(0, (sh - h) // 3)}")

    def _on_configure(self, e) -> None:
        if e.widget is not self:
            return
        if self._geo_job:
            self.after_cancel(self._geo_job)
        self._geo_job = self.after(800, self._save_geometry)

    def _save_geometry(self) -> None:
        self._geo_job = None
        try:
            st = self.state()
            if st == "zoomed":
                self.cfg["zoom"] = True
            elif st == "normal":
                self.cfg["zoom"] = False
                self.cfg["geometrie"] = self.geometry()
            self.cfg.save()
        except Exception:
            pass

    # ------------------------------------------------------------ UI (grid : la saisie reste TOUJOURS visible)
    def _build(self) -> None:
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TCombobox", fieldbackground=C["ENTRY_BG"], background=C["BTN"], foreground=C["ENTRY_FG"],
                        arrowcolor=C["BTN_FG"])
        style.map("TCombobox", fieldbackground=[("readonly", C["ENTRY_BG"])], foreground=[("readonly", C["ENTRY_FG"])])
        style.configure("Vertical.TScrollbar", background=C["BTN"], troughcolor=C["CARD"], arrowcolor=C["BTN_FG"])

        top = tk.Frame(self, bg=C["PANEL"])
        top.grid(row=0, column=0, sticky="ew")
        self.dot = tk.Canvas(top, width=18, height=18, bg=C["PANEL"], highlightthickness=0)
        self.dot.pack(side="left", padx=(10, 2))
        self.v_pseudo = tk.StringVar(value=self.cfg["pseudo"] or "(sans pseudo)")
        tk.Label(top, textvariable=self.v_pseudo, bg=C["PANEL"], fg=C["HI"], font=("Segoe UI", 12, "bold")).pack(side="left", padx=(2, 8), pady=6)
        self.v_statut = tk.StringVar(value=STATUT_LABEL.get(self.cfg["statut"], "Disponible"))
        cb = ttk.Combobox(top, textvariable=self.v_statut, values=[l for _, l in STATUTS], width=11, state="readonly")
        cb.pack(side="left", padx=4)
        cb.bind("<<ComboboxSelected>>", lambda e: self.set_status())
        tk.Label(top, text="Vérifier aux :", bg=C["PANEL"], fg=C["FG"]).pack(side="left", padx=(12, 2))
        self.v_int = tk.StringVar(value=self._int_label(int(self.cfg["intervalle"] or 15)))
        ci = ttk.Combobox(top, textvariable=self.v_int, values=[l for l, _ in INTERVALLES], width=7, state="readonly")
        ci.pack(side="left")
        ci.bind("<<ComboboxSelected>>", lambda e: self.set_interval())
        self.v_pause = tk.BooleanVar(value=bool(self.cfg["pause_si_indispo"]))
        tk.Checkbutton(top, text="Ralentir si pas dispo", variable=self.v_pause, command=self._save_opts,
                       bg=C["PANEL"], fg=C["FG"], selectcolor=C["ENTRY_BG"], activebackground=C["PANEL"],
                       activeforeground=C["FG"]).pack(side="left", padx=6)
        btn(top, "⚙", self.settings).pack(side="right", padx=(2, 8), pady=4)
        btn(top, "🎨", self.cycle_theme).pack(side="right", padx=2)
        self.b_son = btn(top, "🔔" if self.cfg["son"] else "🔕", self.toggle_sound)
        self.b_son.pack(side="right", padx=2)
        btn(top, "🔎 Chercher", self.search_dialog).pack(side="right", padx=2)
        btn(top, "⟳", self.refresh_now).pack(side="right", padx=2)

        body = tk.PanedWindow(self, orient="horizontal", bg=C["LINE"], sashwidth=4, bd=0)
        body.grid(row=1, column=0, sticky="nsew")
        left = tk.Frame(body, bg=C["BG"])
        body.add(left, width=230, minsize=170)
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)
        tk.Label(left, text="Conversations", bg=C["BG"], fg=C["HI"], font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w", padx=8, pady=(8, 2))
        self.lst = tk.Listbox(left, bg=C["CARD"], fg=C["TEXT"], selectbackground=C["SEL"], selectforeground=C["TEXT"],
                              font=("Segoe UI Emoji", 11), activestyle="none", bd=0, highlightthickness=0, exportselection=False)
        self.lst.grid(row=1, column=0, sticky="nsew", padx=6)
        self.lst.bind("<<ListboxSelect>>", lambda e: self.on_pick())
        self.lst.bind("<Motion>", self._lst_hover)
        tk.Label(left, text="Clique sur quelqu'un pour lui écrire en privé.", bg=C["BG"], fg=C["DIM"],
                 font=("Segoe UI", 8), wraplength=200, justify="left").grid(row=2, column=0, sticky="w", padx=8, pady=(4, 6))

        right = tk.Frame(body, bg=C["BG"])
        body.add(right, minsize=420)
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=1)

        head = tk.Frame(right, bg=C["BG"])
        head.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 2))
        self.v_head = tk.StringVar(value="📢 Salon général")
        self.l_head = tk.Label(head, textvariable=self.v_head, bg=C["BG"], fg=C["PUB"], font=("Segoe UI Emoji", 12, "bold"))
        self.l_head.pack(side="left")
        self.v_sub = tk.StringVar(value="")
        tk.Label(head, textvariable=self.v_sub, bg=C["BG"], fg=C["DIM"], font=("Segoe UI", 9)).pack(side="left", padx=8)
        self.b_back = btn(head, "⟵ Retour au Salon général", self.open_public)

        wrap = tk.Frame(right, bg=C["CARD"])
        wrap.grid(row=1, column=0, sticky="nsew", padx=6)
        wrap.grid_rowconfigure(0, weight=1)
        wrap.grid_columnconfigure(0, weight=1)
        self.txt = tk.Text(wrap, bg=C["CARD"], fg=C["TEXT"], wrap="word", state="disabled", bd=0, highlightthickness=0,
                           font=("Segoe UI Emoji", 11), padx=10, pady=8, cursor="arrow", spacing1=1, spacing3=1, height=5)
        sb = ttk.Scrollbar(wrap, command=self.txt.yview)
        self.txt.configure(yscrollcommand=lambda a, b: (sb.set(a, b), self._on_scroll()))
        self.txt.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        t = self.txt
        t.tag_configure("who_me", foreground=C["OK"], font=("Segoe UI", 9, "bold"))
        t.tag_configure("who_them", foreground=C["HI"], font=("Segoe UI", 9, "bold"))
        t.tag_configure("time", foreground=C["DIM"], font=("Segoe UI", 8))
        t.tag_configure("day", foreground=C["DIM"], justify="center", font=("Segoe UI", 9, "italic"), spacing1=6, spacing3=4)
        t.tag_configure("me", lmargin1=70, lmargin2=70, rmargin=8)
        t.tag_configure("them", lmargin1=6, lmargin2=6, rmargin=70)
        t.tag_configure("bub_me", background=C["ME"])
        t.tag_configure("bub_them", background=C["THEM"])
        t.tag_configure("quote", foreground=C["QUOTE"], font=("Segoe UI", 9, "italic"))
        t.tag_configure("deleted", foreground=C["DIM"], font=("Segoe UI", 9, "italic"))
        t.tag_configure("edited", foreground=C["DIM"], font=("Segoe UI", 8, "italic"))
        t.tag_configure("link", foreground=C["LINK"], underline=True)
        t.tag_configure("hl", background=C["FLASH"])
        t.tag_bind("link", "<Enter>", lambda e: t.config(cursor="hand2"))
        t.tag_bind("link", "<Leave>", lambda e: t.config(cursor="arrow"))
        self.pill = tk.Label(wrap, text="⬇ nouveaux messages", bg=C["SEL"], fg=C["BTN_FG"], cursor="hand2",
                             font=("Segoe UI", 9, "bold"), padx=10, pady=2)
        self.pill.bind("<Button-1>", lambda e: self._smooth_bottom())

        self.v_typing = tk.StringVar(value="")
        tk.Label(right, textvariable=self.v_typing, bg=C["BG"], fg=C["DIM"], anchor="w",
                 font=("Segoe UI", 9, "italic")).grid(row=2, column=0, sticky="ew", padx=10)

        self.rbar = tk.Frame(right, bg=C["PANEL"])
        self.v_rbar = tk.StringVar(value="")
        tk.Label(self.rbar, textvariable=self.v_rbar, bg=C["PANEL"], fg=C["QUOTE"], anchor="w",
                 font=("Segoe UI Emoji", 9, "italic")).pack(side="left", fill="x", expand=True, padx=8, pady=3)
        btn(self.rbar, "✕", self.cancel_reply_edit, bg=C["PANEL"]).pack(side="right", padx=4)

        bar = tk.Frame(right, bg=C["BG"])
        bar.grid(row=4, column=0, sticky="ew", padx=6, pady=(4, 0))
        for em in ("❤️", "👍", "😂"):
            btn(bar, em, lambda e=em: self.react_last(e), padx=5).pack(side="left", padx=1)
        self.b_emoji = btn(bar, "😀 Émojis", self.emoji_picker)
        self.b_emoji.pack(side="left", padx=(8, 1))
        btn(bar, "📎 Fichier", self.send_file).pack(side="right", padx=2)
        btn(bar, "🖼 Image", lambda: self.send_file(images=True)).pack(side="right", padx=2)
        self.b_rec = btn(bar, "🎤 Vocal", self.toggle_record)
        self.b_rec.pack(side="right", padx=2)
        if not Recorder.available():
            self.b_rec.configure(state="disabled", text="🎤 (micro indispo)")

        inp = tk.Frame(right, bg=C["BG"])
        inp.grid(row=5, column=0, sticky="ew", padx=6, pady=(4, 6))
        inp.grid_columnconfigure(1, weight=1)
        self.l_dest = tk.Label(inp, text="", bg=C["PUB"], fg="#000000", font=("Segoe UI", 9, "bold"), padx=8, pady=2)
        self.l_dest.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 3))
        self.ent_wrap = tk.Frame(inp, bg=C["PUB"], padx=2, pady=2)
        self.ent_wrap.grid(row=1, column=0, columnspan=2, sticky="ew")
        self.ent_wrap.grid_columnconfigure(0, weight=1)
        self.ent = tk.Text(self.ent_wrap, height=2, bg=C["ENTRY_BG"], fg=C["ENTRY_FG"], insertbackground=C["ENTRY_FG"],
                           font=("Segoe UI Emoji", 11), wrap="word", bd=0, highlightthickness=0, padx=6, pady=4, undo=True)
        self.ent.grid(row=0, column=0, sticky="ew")
        self.ent.bind("<Return>", self._on_enter)
        self.ent.bind("<KP_Enter>", self._on_enter)
        self.ent.bind("<Escape>", lambda e: self.cancel_reply_edit())
        self.ent.bind("<Up>", self._on_up)
        self.ent.bind("<KeyRelease>", self._on_key)
        self.ent.bind("<Control-v>", self._on_paste)
        self.ent.bind("<Control-V>", self._on_paste)
        self.b_send = btn(inp, "Envoyer ➤", self.send_text, font=("Segoe UI", 11, "bold"), padx=14)
        self.b_send.grid(row=1, column=2, sticky="ns", padx=(6, 0))
        tk.Label(inp, text="Entrée = envoyer · Maj+Entrée = nouvelle ligne · Ctrl+V = coller une image · ↑ = modifier",
                 bg=C["BG"], fg=C["DIM"], font=("Segoe UI", 8)).grid(row=2, column=0, columnspan=3, sticky="w", pady=(2, 0))

        self.v_bar = tk.StringVar(value="Prêt.")
        tk.Label(self, textvariable=self.v_bar, bg=C["PANEL"], fg=C["DIM"], anchor="w", padx=8).grid(row=2, column=0, sticky="ew")

        if DND_FILES:
            for w in (self.txt, self.ent):
                try:
                    w.drop_target_register(DND_FILES)
                    w.dnd_bind("<<Drop>>", self._on_drop)
                except Exception as e:
                    jlog(f"dnd: {e}")
        self._draw_dot()
        self._update_dest()
        self.after(50, self.ent.focus_set)

    def _int_label(self, sec: int) -> str:
        for l, s in INTERVALLES:
            if s == sec:
                return l
        return f"{sec} s"

    def _draw_dot(self) -> None:
        self.dot.delete("all")
        col = STATUT_COULEUR.get(self.cfg["statut"], "#888") if self._online else "#666666"
        self.dot.create_oval(3, 3, 15, 15, fill=col, outline="")

    def status(self, msg: str) -> None:
        self.v_bar.set(msg)

    def ui(self, fn: Callable[[], None]) -> None:
        self.q.put(fn)

    def _pump(self) -> None:
        try:
            while True:
                self.q.get_nowait()()
        except queue.Empty:
            pass
        except Exception:
            jlog(traceback.format_exc())
        self.after(80, self._pump)

    def bg(self, work: Callable[[], Any], done: Optional[Callable[[Any], None]] = None, err_prefix: str = "") -> None:
        def run():
            try:
                r = work()
                if done:
                    self.ui(lambda: done(r))
            except Exception as e:
                msg = f"{err_prefix}{e}"
                jlog(msg)
                self.ui(lambda: self.status("⚠ " + msg))
        threading.Thread(target=run, daemon=True).start()

    @property
    def me(self) -> int:
        return int(self.cfg["user_id"] or 0)

    # ------------------------------------------------------------ demarrage
    def _startup(self) -> None:
        if not self.cfg["pseudo"]:
            self.show()
            p = simpledialog.askstring(APP_TITLE, "Bienvenue dans Messager !\n\nChoisis ton pseudo (2 à 48 caractères) :", parent=self)
            if not p:
                self.status("Pas de pseudo : choisis-en un dans Réglages (⚙).")
                return
            self.cfg["pseudo"] = p.strip()
            self.cfg.save()
            self.v_pseudo.set(self.cfg["pseudo"])
        self.status("Connexion au serveur…")

        def run():
            try:
                u = self.api.register()
                self.api.call("set_status", status=self.cfg["statut"])
                pub = int(self.api.call("public_room")["conversation_id"])
                v = self.api.call("list_conversations")
                self.ui(lambda: done(u, pub, v))
            except Exception as e:
                jlog(f"startup: {e}")
                self.ui(lambda e=e: fail(e))

        def done(u, pub, v):
            self._online = True
            self._draw_dot()
            self.pub_id = pub
            self.status(f"Connecté à {self.api.base} comme {u.get('pseudo')}.")
            self.v_pseudo.set(u.get("pseudo") or self.cfg["pseudo"])
            self._set_convs(v.get("conversations") or [])
            self.open_public()
            if not self._poll_started:
                self._poll_started = True
                threading.Thread(target=self._poll_loop, daemon=True).start()

        def fail(e: Exception):
            self._online = False
            self._draw_dot()
            self.status(f"⚠ Serveur injoignable ({self.api.base}) : hors ligne, nouvel essai dans 20 s…" if "injoignable" in str(e) else f"⚠ Connexion impossible ({str(e)[:120]}). Nouvel essai dans 20 s…")
            self.after(20000, self._startup)
        threading.Thread(target=run, daemon=True).start()

    # ------------------------------------------------------------ sondage
    def _poll_loop(self) -> None:
        fails = 0
        while not self._stop.is_set():
            st = self.cfg["statut"]
            wait = max(3, int(self.cfg["intervalle"] or 15))
            if bool(self.cfg["pause_si_indispo"]) and st in ("occupe", "invisible", "absent"):
                wait = max(wait, 60)
            tcur = self.typing.get(self.cur_conv)
            if tcur and time.time() - tcur[0] < 30:
                wait = min(wait, 4)
            try:
                self._poll_once(wait)
                if fails:
                    self.ui(lambda: self.status("Reconnecté ✔"))
                fails = 0
                if not self._online:
                    self._online = True
                    self.ui(self._draw_dot)
            except Exception as e:
                fails += 1
                jlog(f"poll: {e}")
                self._online = False
                self.ui(self._draw_dot)
                self.ui(lambda e=e: self.status("⚠ Serveur injoignable : hors ligne, nouvel essai automatique…" if "injoignable" in str(e) else f"⚠ Réseau : {str(e)[:120]} - nouvel essai automatique"))
                wait = min(wait * (1 + fails), 120)
            self._wake.wait(wait)
            self._wake.clear()

    def _poll_once(self, wait: int) -> None:
        for _page in range(5):
            after = int(self.cfg["dernier_id"] or 0)
            j = self.api.call("poll", after_id=after, limit=200, retries=2, poll_sec=wait,
                              edits_since=self._server_time or 0)
            msgs = j.get("messages") or []
            new_conv = any(int(m["conversation_id"]) not in self.convs for m in msgs)
            cj = self.api.call("list_conversations", retries=2) if new_conv else None
            self._server_time = int(j.get("server_time") or 0)
            if msgs:
                self.cfg["dernier_id"] = max(after, max(int(m["id"]) for m in msgs))
            self.ui(lambda j=j, cj=cj: self._apply_poll(j, cj))
            if len(msgs) < 200:
                break

    def refresh_now(self) -> None:
        def work():
            return self.api.call("list_conversations"), self.api.call("presence")

        def done(r):
            v, p = r
            self._set_convs(v.get("conversations") or [])
            self._set_users(p.get("users") or [])
            self._wake.set()
            self.status("Actualisé.")
        self.bg(work, done, "Actualisation : ")

    def _set_convs(self, convs: List[Dict[str, Any]]) -> None:
        for c in convs:
            cid = int(c["id"])
            self.convs[cid] = c
            if c.get("kind") == "public":
                self.pub_id = cid
            if c.get("kind") == "dm":
                for p in c.get("peers") or []:
                    self.peer_conv[int(p["id"])] = cid
                    self.conv_peer[cid] = int(p["id"])
                    self.users.setdefault(int(p["id"]), dict(p, online=False))
        self._render_list()

    def _set_users(self, users: List[Dict[str, Any]]) -> None:
        for u in users:
            self.users[int(u["id"])] = u
        self._render_list()

    def _apply_poll(self, j: Dict[str, Any], cj: Optional[Dict[str, Any]]) -> None:
        if cj:
            self._set_convs(cj.get("conversations") or [])
        if j.get("public_id"):
            self.pub_id = int(j["public_id"])
        pf = int(j.get("public_flush") or 0)
        if pf and pf != int(self.cfg["salon_vide_le"] or 0):
            first = not self.cfg["salon_vide_le"]
            self.cfg["salon_vide_le"] = pf
            self.cfg.save()
            self.msgs[self.pub_id] = [m for m in self.msgs.get(self.pub_id, []) if _parse_ts(m.get("created_at")).timestamp() > pf]
            self.unread.pop(self.pub_id, None)
            if self.cur_conv == self.pub_id:
                self._render_conv()
            if not first:
                self.status("🧹 Le Salon général a été vidé par l'administrateur.")
        for u in j.get("presence") or []:
            self.users[int(u["id"])] = u
        msgs = j.get("messages") or []
        me = self.me
        notif: List[Dict[str, Any]] = []
        appended: List[Dict[str, Any]] = []
        focused = self._is_focused()
        for m in msgs:
            cid = int(m["conversation_id"])
            lst = self.msgs.setdefault(cid, [])
            if any(int(x["id"]) == int(m["id"]) for x in lst):
                continue
            lst.append(m)
            if cid == self.cur_conv:
                appended.append(m)
            if int(m["sender_id"]) != me and not self._first_poll:
                if cid != self.cur_conv or not focused:
                    self.unread[cid] = self.unread.get(cid, 0) + 1
                    notif.append(m)
        if msgs:
            self.cfg.save()
        changed = False
        for e in j.get("edits") or []:
            lst = self.msgs.get(int(e["conversation_id"])) or []
            for i, x in enumerate(lst):
                if int(x["id"]) == int(e["id"]):
                    if (x.get("body"), str(x.get("deleted")), x.get("edited_at"), str(x.get("reactions"))) != \
                            (e.get("body"), str(e.get("deleted")), e.get("edited_at"), str(e.get("reactions"))):
                        lst[i] = e
                        if int(e["conversation_id"]) == self.cur_conv:
                            changed = True
        now = time.time()
        by: Dict[int, List[str]] = {}
        for t in j.get("typing") or []:
            by.setdefault(int(t["conversation_id"]), []).append(t.get("pseudo") or "?")
        self.typing = {cid: (now, names) for cid, names in by.items()}
        self._update_typing()
        if changed:
            self._render_conv(keep_scroll=True)
        elif appended:
            self._append_msgs(appended)
        self._render_list()
        if notif:
            self._notify(notif)
        self._first_poll = False
        self._update_title()

    def _notify(self, notif: List[Dict[str, Any]]) -> None:
        if self.cfg["statut"] == "occupe":
            return
        priv = [m for m in notif if int(m["conversation_id"]) != self.pub_id]
        if not priv and not self.cfg["notif_salon"]:
            return
        if not self._is_focused():
            flash_taskbar(self._hwnd())
        self._tray_blink = True
        m = (priv or notif)[-1]
        who = m.get("sender_pseudo") or self._pseudo(int(m["sender_id"]))
        where = "" if int(m["conversation_id"]) != self.pub_id else " (Salon)"
        preview = m.get("body") or {"image": "🖼 image", "audio": "🎤 message vocal", "video": "🎬 vidéo"}.get(m.get("kind"), "📎 fichier")
        if self.cfg["notifications"] and (priv or not self._is_focused()):
            threading.Thread(target=notify, args=(f"Messager — {who}{where}", preview), daemon=True).start()
        if self.cfg["son"] and IS_WIN:
            try:
                import winsound
                winsound.MessageBeep(0x40 if priv else 0)
            except Exception:
                pass

    def _pseudo(self, uid: int) -> str:
        if uid == self.me:
            return self.cfg["pseudo"] or "Moi"
        u = self.users.get(uid)
        return (u.get("pseudo") if u else None) or f"#{uid}"

    def _is_focused(self) -> bool:
        try:
            return self.state() not in ("withdrawn", "iconic") and self.focus_displayof() is not None
        except Exception:
            return False

    def _hwnd(self) -> int:
        try:
            return int(self.wm_frame(), 16)
        except Exception:
            return 0

    def _on_focus(self) -> None:
        if self.cur_conv and self.unread.pop(self.cur_conv, None):
            self._render_list()
        if not sum(self.unread.values()):
            if self._tray_blink:
                flash_taskbar(self._hwnd(), stop=True)
            self._tray_blink = False
        self._update_title()

    def _update_title(self) -> None:
        n = sum(self.unread.values())
        self.title(f"({n}) {self._base_title}" if n else self._base_title)

    # ------------------------------------------------------------ liste a gauche
    def _render_list(self) -> None:
        lb = self.lst
        y = lb.yview()[0]
        lb.delete(0, "end")
        self._items = []

        def add(label: str, kind: str, ident: int, fg: str) -> None:
            lb.insert("end", label)
            lb.itemconfig("end", fg=fg, selectforeground="#000000" if kind != "hdr" else fg)
            self._items.append((kind, ident))

        n = self.unread.get(self.pub_id, 0)
        add(" 📢  Salon général" + (f"   ● {n}" if n else ""), "conv", self.pub_id, C["HI"] if n else C["PUB"])
        me = self.me
        users = [u for uid, u in self.users.items() if uid != me]
        online = sorted([u for u in users if u.get("online")], key=lambda u: (u.get("pseudo") or "").lower())
        offline = [u for u in users if not u.get("online")]
        offline.sort(key=lambda u: (0 if int(u["id"]) in self.peer_conv else 1, (u.get("pseudo") or "").lower()))
        add(f" ── En ligne ({len(online) + 1}) ──", "hdr", 0, C["DIM"])
        add(f"  ●  {self.cfg['pseudo'] or 'Moi'}  (moi)", "me", me,
            STATUT_COULEUR.get(self.cfg["statut"], C["DIM"]) if self.cfg["statut"] != "invisible" else C["DIM"])
        for u in online:
            self._add_user_line(add, u, True)
        if offline:
            add(f" ── Hors ligne ({len(offline)}) ──", "hdr", 0, C["DIM"])
            for u in offline[:150]:
                self._add_user_line(add, u, False)
        for i, (k, ident) in enumerate(self._items):
            if (k == "conv" and ident == self.cur_conv) or (k == "user" and self.cur_conv and self.peer_conv.get(ident) == self.cur_conv):
                lb.selection_set(i)
        lb.yview_moveto(y)

    @staticmethod
    def _status_dot(st: str, online: bool) -> str:
        return "●" if online else "○"

    def _add_user_line(self, add, u: Dict[str, Any], online: bool) -> None:
        uid = int(u["id"])
        cid = self.peer_conv.get(uid, 0)
        n = self.unread.get(cid, 0) if cid else 0
        st = u.get("status") or "disponible"
        extra = "" if st == "disponible" or not online else f"  · {STATUT_LABEL.get(st, st).lower()}"
        lab = f"  {self._status_dot(st, online)}  {u.get('pseudo')}{extra}" + (f"   ● {n}" if n else "")
        add(lab, "user", uid, C["HI"] if n else (STATUT_COULEUR.get(st, C["TEXT"]) if online else C["DIM"]))

    def _lst_hover(self, e) -> None:
        try:
            k = self._items[self.lst.nearest(e.y)][0]
            self.lst.configure(cursor="hand2" if k in ("conv", "user") else "arrow")
        except Exception:
            pass

    def on_pick(self) -> None:
        try:
            kind, ident = self._items[self.lst.curselection()[0]]
        except Exception:
            return
        if kind == "conv":
            self.open_public()
        elif kind == "user":
            self.open_dm(ident)
        else:
            self._render_list()

    def open_public(self) -> None:
        if self.pub_id:
            self._open_conv(self.pub_id)

    def open_dm(self, uid: int) -> None:
        if not uid or uid == self.me:
            return
        cid = self.peer_conv.get(uid)
        if cid:
            self._open_conv(cid)
            return

        def done(j):
            c = int(j["conversation_id"])
            self.peer_conv[uid] = c
            self.conv_peer[c] = uid
            self.convs.setdefault(c, {"id": c, "kind": "dm", "peers": [self.users.get(uid, {"id": uid})]})
            self._open_conv(c)
        self.bg(lambda: self.api.call("open_dm", user_id=uid), done, "Conversation : ")

    def _open_conv(self, cid: int, then: Optional[Callable[[], None]] = None) -> None:
        if cid != self.cur_conv:
            self.cancel_reply_edit()
            self._new_below = 0
            self.pill.place_forget()
        self.cur_conv = cid
        self.unread.pop(cid, None)
        self._update_dest()
        self._render_list()
        self._render_conv()
        self._update_typing()
        self._update_title()
        self.ent.focus_set()

        def done(j):
            self._set_history(cid, j.get("messages") or [])
            if then:
                then()
        self.bg(lambda: self.api.call("history", conversation_id=cid, limit=80), done, "Historique : ")

    def _update_dest(self) -> None:
        if not self.cur_conv or self.cur_conv == self.pub_id:
            self.v_head.set("📢 Salon général")
            self.v_sub.set("Public — tout le monde sur le serveur lit ces messages")
            self.l_head.configure(fg=C["PUB"])
            self.l_dest.configure(text="✍  Tu écris à : TOUT LE MONDE (Salon général)", bg=C["PUB"])
            self.ent_wrap.configure(bg=C["PUB"])
            self.b_back.pack_forget()
        else:
            who = self._pseudo(self.conv_peer.get(self.cur_conv, 0))
            self.v_head.set(f"🔒 Privé avec {who}")
            self.v_sub.set("Seuls vous deux voyez cette conversation")
            self.l_head.configure(fg=C["PRIV"])
            self.l_dest.configure(text=f"✍  Tu écris en PRIVÉ à : {who}", bg=C["PRIV"])
            self.ent_wrap.configure(bg=C["PRIV"])
            self.b_back.pack(side="right")

    def _set_history(self, cid: int, msgs: List[Dict[str, Any]]) -> None:
        have = {int(m["id"]): m for m in self.msgs.get(cid, [])}
        for m in msgs:
            have[int(m["id"])] = m
        self.msgs[cid] = sorted(have.values(), key=lambda m: int(m["id"]))
        if cid == self.cur_conv:
            self._render_conv()

    # ------------------------------------------------------------ rendu des messages
    def _find_msg(self, mid: int) -> Optional[Dict[str, Any]]:
        for lst in self.msgs.values():
            for m in lst:
                if int(m["id"]) == mid:
                    return m
        return None

    def _at_bottom(self) -> bool:
        try:
            return self.txt.yview()[1] >= 0.985
        except Exception:
            return True

    def _rerender_soon(self) -> None:
        if self._rerender_job:
            return

        def go():
            self._rerender_job = None
            self._render_conv(keep_scroll=True)
        self._rerender_job = self.after(200, go)

    def _render_conv(self, keep_scroll: bool = False) -> None:
        t = self.txt
        bottom = self._at_bottom()
        y = t.yview()[0]
        t.configure(state="normal")
        t.delete("1.0", "end")
        self._images.clear()
        prev = None
        lst = self.msgs.get(self.cur_conv, [])
        if not lst:
            msg = ("Bienvenue dans le Salon général 👋\nÉcris en bas : tout le monde connecté au serveur verra ton message.\n"
                   "Clique sur une personne à gauche pour lui écrire en privé.") if self.cur_conv == self.pub_id else \
                "Aucun message encore. Dis bonjour 👋"
            t.insert("end", "\n\n" + msg, ("day",))
        for m in lst:
            self._insert_msg(m, prev)
            prev = m
        t.configure(state="disabled")
        if keep_scroll and not bottom:
            t.yview_moveto(y)
        else:
            t.see("end")

    def _append_msgs(self, msgs: List[Dict[str, Any]]) -> None:
        t = self.txt
        bottom = self._at_bottom()
        lst = self.msgs.get(self.cur_conv, [])
        if len(lst) == len(msgs):  # premier message : enlever le mot de bienvenue
            self._render_conv()
            return
        t.configure(state="normal")
        for m in msgs:
            i = next((k for k, x in enumerate(lst) if int(x["id"]) == int(m["id"])), -1)
            prev = lst[i - 1] if i > 0 else None
            start = t.index("end-1c")
            self._insert_msg(m, prev)
            self._fade(start, t.index("end-1c"))
        t.configure(state="disabled")
        mine = all(int(m["sender_id"]) == self.me for m in msgs)
        if bottom or mine:
            self._smooth_bottom()
        else:
            self._new_below += len(msgs)
            n = self._new_below
            self.pill.configure(text=f"⬇ {n} nouveau{'x' if n > 1 else ''} message{'s' if n > 1 else ''}")
            self.pill.place(relx=0.5, rely=1.0, y=-10, anchor="s")

    def _insert_msg(self, m: Dict[str, Any], prev: Optional[Dict[str, Any]]) -> None:
        t = self.txt
        mid = int(m["id"])
        sid = int(m["sender_id"])
        mine = sid == self.me
        side = "me" if mine else "them"
        bub = "bub_me" if mine else "bub_them"
        tg = f"m{mid}"
        ts = _parse_ts(m.get("created_at"))
        pts = _parse_ts(prev.get("created_at")) if prev else None
        if pts is None or pts.date() != ts.date():
            t.insert("end", f"\n—  {_day_label(ts.date())}  —\n", ("day",))
        grouped = prev is not None and pts is not None and int(prev["sender_id"]) == sid and pts.date() == ts.date() \
            and (ts - pts).total_seconds() < 300
        if not grouped:
            name = m.get("sender_pseudo") or self._pseudo(sid)
            t.insert("end", "\n", (side,))
            t.insert("end", f"{'Moi' if mine else name}  ", ("who_me" if mine else "who_them", side, tg))
            t.insert("end", f"{ts:%H:%M}\n", ("time", side, tg))
        rid = int(m.get("reply_to") or 0)
        if rid:
            q = self._find_msg(rid)
            if q:
                qtxt = (q.get("body") or ("[supprimé]" if int(q.get("deleted") or 0) else "[pièce jointe]")).replace("\n", " ")
                qname = q.get("sender_pseudo") or self._pseudo(int(q["sender_id"]))
                t.insert("end", f"↪ {qname} : {qtxt[:90]}{'…' if len(qtxt) > 90 else ''}\n", ("quote", side, bub, tg))
            else:
                t.insert("end", "↪ (réponse à un ancien message)\n", ("quote", side, bub, tg))
        if int(m.get("deleted") or 0):
            t.insert("end", "🗑 message supprimé\n", ("deleted", side, bub, tg))
        else:
            body = m.get("body") or ""
            if body:
                self._insert_text_with_links(body, (side, bub, tg))
                if m.get("edited_at"):
                    t.insert("end", "  (modifié)", ("edited", side, bub, tg))
                t.insert("end", "\n", (side, bub, tg))
            if m.get("attachment_id"):
                self._insert_attachment(m, side)
            for url in URL_RE.findall(body)[:2]:
                self._insert_preview(url, side)
        reacts = m.get("reactions") or []
        if reacts:
            cnt: Dict[str, int] = {}
            minez = set()
            for r in reacts:
                cnt[r["emoji"]] = cnt.get(r["emoji"], 0) + 1
                if int(r["user_id"]) == self.me:
                    minez.add(r["emoji"])
            t.insert("end", " ", (side,))
            for e, n in cnt.items():
                lab = tk.Label(t, text=f"{e} {n}" if n > 1 else e, bg=C["SEL"] if e in minez else C["PANEL"],
                               fg=C["TEXT"], font=("Segoe UI Emoji", 9), padx=4, cursor="hand2")
                lab.bind("<Button-1>", lambda ev, x=e: self.react(mid, x))
                t.window_create("end", window=lab, padx=1)
            t.insert("end", "\n", (side,))
        t.tag_bind(tg, "<Button-3>", lambda e: self.msg_menu(e, mid))
        t.tag_bind(tg, "<Double-Button-1>", lambda e: self.react(mid, "❤️"))

    def _insert_text_with_links(self, body: str, tags: Tuple[str, ...]) -> None:
        pos = 0
        for mm in URL_RE.finditer(body):
            if mm.start() > pos:
                self.txt.insert("end", body[pos:mm.start()], tags)
            url = mm.group(0)
            self._fade_n += 1
            tag = f"url{self._fade_n}"
            self.txt.insert("end", url, ("link", tag) + tags)
            self.txt.tag_bind(tag, "<Button-1>", lambda e, u=url: webbrowser.open(u))
            pos = mm.end()
        self.txt.insert("end", body[pos:], tags)

    def _insert_attachment(self, m: Dict[str, Any], side: str) -> None:
        aid = int(m["attachment_id"])
        kind = m.get("kind") or "file"
        label = {"image": "🖼 Image", "video": "🎬 Vidéo — lire", "audio": "▶ Écouter le vocal"}.get(kind, "📎 Ouvrir le fichier")
        b = tk.Button(self.txt, text=label, bg=C["BTN"], fg=C["BTN_FG"], relief="flat", cursor="hand2",
                      font=("Segoe UI Emoji", 10), command=lambda: self.open_attachment(aid, kind))
        if kind == "image" and Image is not None:
            ph = self._thumb_for_attachment(aid)
            if ph is not None:
                b.configure(image=ph, compound="top", text="🖼 ouvrir")
        self.txt.window_create("end", window=b, padx=4, pady=2)
        self.txt.insert("end", "\n", (side,))

    def _thumb_for_attachment(self, aid: int):
        path = os.path.join(Paths.cache(), f"thumb_{aid}.png")
        if os.path.isfile(path):
            try:
                ph = ImageTk.PhotoImage(Image.open(path))
                self._images.append(ph)
                return ph
            except Exception:
                return None
        if os.path.isfile(path + ".fail"):
            return None

        def work():
            try:
                src = self.api.download_media(aid, f"img_{aid}")
                im = Image.open(src)
                im.thumbnail((280, 210))
                im.save(path)
            except Exception:
                open(path + ".fail", "w").close()
                raise
            return True
        self.bg(work, lambda r: self._rerender_soon(), "Miniature : ")
        return None

    def _insert_preview(self, url: str, side: str) -> None:
        p = self._previews.get(url)
        if p is None:
            self._previews[url] = {}
            self.bg(lambda: self.api.call("preview", url=url, retries=2).get("preview") or {},
                    lambda pv: (self._previews.__setitem__(url, pv), self._rerender_soon()), "Aperçu : ")
            return
        if not p:
            return
        card = tk.Frame(self.txt, bg=C["PANEL"], bd=0, highlightthickness=1, highlightbackground=C["LINE"])
        prov = p.get("provider") or "generic"
        stream = prov in ("youtube", "odysee", "x", "facebook")
        icon = {"youtube": "▶ YouTube", "x": "𝕏", "facebook": "Facebook", "odysee": "Odysee"}.get(prov, "🔗")
        tk.Label(card, text=f"{icon}  {p.get('site_name') or ''}", bg=C["PANEL"], fg=C["DIM"], anchor="w",
                 font=("Segoe UI Emoji", 8)).pack(fill="x", padx=6, pady=(4, 0))
        tk.Label(card, text=(p.get("title") or url)[:120], bg=C["PANEL"], fg=C["HI"], anchor="w", justify="left",
                 wraplength=380, font=("Segoe UI", 10, "bold")).pack(fill="x", padx=6)
        if p.get("description"):
            tk.Label(card, text=p["description"][:220], bg=C["PANEL"], fg=C["TEXT"], anchor="w", justify="left",
                     wraplength=380, font=("Segoe UI", 9)).pack(fill="x", padx=6)
        ph = self._thumb_for_url(p.get("image_url") or "")
        if ph is not None:
            il = tk.Label(card, image=ph, bg=C["PANEL"], cursor="hand2")
            il.pack(anchor="w", padx=6, pady=2)
            il.bind("<Button-1>", lambda e: play_stream_url(url) if stream else webbrowser.open(url))
        row = tk.Frame(card, bg=C["PANEL"])
        row.pack(fill="x", padx=6, pady=4)
        if stream:
            btn(row, "▶ Lire ici (sans l'appli)", lambda: play_stream_url(url)).pack(side="left")
        btn(row, "🌐 Ouvrir", lambda: webbrowser.open(url)).pack(side="left", padx=4)
        self.txt.window_create("end", window=card, padx=4, pady=2)
        self.txt.insert("end", "\n", (side,))

    def _thumb_for_url(self, img_url: str):
        if not img_url or Image is None or not img_url.startswith("http"):
            return None
        h = hashlib.sha1(img_url.encode()).hexdigest()[:16]
        path = os.path.join(Paths.cache(), f"og_{h}.png")
        if os.path.isfile(path):
            try:
                ph = ImageTk.PhotoImage(Image.open(path))
                self._images.append(ph)
                return ph
            except Exception:
                return None
        if os.path.isfile(path + ".fail"):
            return None

        def work():
            try:
                r = self.api.sess.get(img_url, timeout=15)
                im = Image.open(io.BytesIO(r.content)).convert("RGB")
                im.thumbnail((360, 200))
                im.save(path)
            except Exception:
                open(path + ".fail", "w").close()
                raise
            return True
        self.bg(work, lambda r: self._rerender_soon(), "Image aperçu : ")
        return None

    # ------------------------------------------------------------ animations
    def _fade(self, start: str, end: str) -> None:
        """Apparition en fondu d'un nouveau message."""
        self._fade_n += 1
        tag = f"fade{self._fade_n}"
        t = self.txt
        t.tag_add(tag, start, end)
        t.tag_raise(tag)
        steps = 10

        def step(i: int):
            try:
                if i > steps:
                    t.tag_delete(tag)
                    return
                t.tag_configure(tag, foreground=_mix(C["CARD"], C["TEXT"], i / steps))
                self.after(30, lambda: step(i + 1))
            except Exception:
                pass
        step(0)

    def _smooth_bottom(self) -> None:
        """Defilement doux jusqu'au dernier message."""
        self.pill.place_forget()
        self._new_below = 0
        t = self.txt
        y0 = t.yview()[0]
        t.yview_moveto(1.0)
        y1 = t.yview()[0]
        t.yview_moveto(y0)
        steps = 12

        def step(i: int):
            if i > steps:
                t.yview_moveto(1.0)
                return
            k = 1 - (1 - i / steps) ** 3
            t.yview_moveto(y0 + (y1 - y0) * k)
            self.after(16, lambda: step(i + 1))
        step(1)

    def _on_scroll(self) -> None:
        if self._new_below and self._at_bottom():
            self._new_below = 0
            self.pill.place_forget()

    def _anim_tick(self) -> None:
        self._dots = (self._dots + 1) % 4
        self._update_typing()
        if self._tray is not None and self._tray_imgs:
            try:
                want = self._tray_imgs[self._dots % 2] if (self._tray_blink and sum(self.unread.values())) else self._tray_imgs[0]
                if self._tray.icon is not want:
                    self._tray.icon = want
            except Exception:
                pass
        self.after(450, self._anim_tick)

    def _update_typing(self) -> None:
        tc = self.typing.get(self.cur_conv)
        if not tc or time.time() - tc[0] > 9:
            self.v_typing.set("")
            return
        names = tc[1]
        who = names[0] if len(names) == 1 else (", ".join(names[:-1]) + " et " + names[-1])
        verb = "écrit" if len(names) == 1 else "écrivent"
        self.v_typing.set(f"✏ {who} {verb}" + "." * self._dots)

    # ------------------------------------------------------------ saisie / envoi
    def _on_enter(self, e):
        if e.state & 0x0001:  # Maj+Entree = nouvelle ligne
            return None
        self.send_text()
        return "break"

    def _on_up(self, e):
        if self.ent.get("1.0", "end").strip():
            return None
        lst = self.msgs.get(self.cur_conv) or []
        mine = next((m for m in reversed(lst) if int(m["sender_id"]) == self.me and not int(m.get("deleted") or 0)
                     and m.get("body")), None)
        if mine:
            self.start_edit(int(mine["id"]))
            return "break"
        return None

    def _on_key(self, e) -> None:
        try:
            n = int(self.ent.count("1.0", "end", "displaylines")[0])
            self.ent.configure(height=max(2, min(6, n)))
        except Exception:
            pass
        if e.keysym in ("Return", "KP_Enter", "Escape", "Up", "Down", "Left", "Right",
                        "Shift_L", "Shift_R", "Control_L", "Control_R"):
            return
        if not self.cur_conv or self.editing or self.cfg["statut"] == "invisible":
            return
        if time.time() - self._last_typing_sent > 4 and self.ent.get("1.0", "end").strip():
            self._last_typing_sent = time.time()
            cid = self.cur_conv
            self.bg(lambda: self.api.call("typing", conversation_id=cid, retries=1, timeout=8))

    def send_text(self) -> None:
        txt = self.ent.get("1.0", "end").strip()
        if not txt:
            return
        if not self.cur_conv:
            self.status("Connexion en cours… réessaie dans un instant.")
            return
        if self.editing:
            mid = self.editing
            self.cancel_reply_edit()
            self.bg(lambda: self.api.call("edit", message_id=mid, body=txt),
                    lambda j: self._replace_msg(j.get("message")), "Modification : ")
            return
        cid = self.cur_conv
        rep = self.reply_to
        self.ent.delete("1.0", "end")
        self.ent.configure(height=2)
        self.cancel_reply_edit()
        self._last_typing_sent = 0
        self._pulse_send()
        params: Dict[str, Any] = {"conversation_id": cid, "body": txt}
        if rep:
            params["reply_to"] = rep

        def fail_restore():
            if not self.ent.get("1.0", "end").strip():
                self.ent.insert("1.0", txt)

        def run():
            try:
                j = self.api.call("send", **params)
                self.ui(lambda: (self._wake.set(), self._add_local(j.get("message"))))
            except Exception as e:
                jlog(f"envoi: {e}")
                self.ui(lambda e=e: (self.status(f"⚠ Envoi : {e} — ton texte est remis dans la zone."), fail_restore()))
        threading.Thread(target=run, daemon=True).start()

    def _pulse_send(self) -> None:
        b = self.b_send
        cols = [C["OK"], _mix(C["OK"], C["BTN"], .5), C["BTN"]]

        def step(i: int):
            if i < len(cols):
                b.configure(bg=cols[i])
                self.after(90, lambda: step(i + 1))
        step(0)

    def _add_local(self, m: Optional[Dict[str, Any]]) -> None:
        if not m:
            return
        m.setdefault("reactions", [])
        cid = int(m["conversation_id"])
        lst = self.msgs.setdefault(cid, [])
        if any(int(x["id"]) == int(m["id"]) for x in lst):
            return
        lst.append(m)
        lst.sort(key=lambda x: int(x["id"]))
        if cid == self.cur_conv:
            self._append_msgs([m])

    def _replace_msg(self, m: Optional[Dict[str, Any]]) -> None:
        if not m:
            return
        lst = self.msgs.get(int(m["conversation_id"])) or []
        for i, x in enumerate(lst):
            if int(x["id"]) == int(m["id"]):
                lst[i] = m
        if int(m["conversation_id"]) == self.cur_conv:
            self._render_conv(keep_scroll=True)
            self._flash_msg(int(m["id"]))

    def _flash_msg(self, mid: int) -> None:
        t = self.txt
        try:
            rng = t.tag_ranges(f"m{mid}")
            if not rng:
                return
            t.see(rng[0])
            t.tag_add("hl", rng[0], rng[-1])
            t.tag_raise("hl")
            self.after(1400, lambda: t.tag_remove("hl", "1.0", "end"))
        except Exception:
            pass

    def start_reply(self, mid: int) -> None:
        m = self._find_msg(mid)
        if not m:
            return
        if self.editing:
            self.cancel_reply_edit()
        self.reply_to = mid
        who = m.get("sender_pseudo") or self._pseudo(int(m["sender_id"]))
        ex = (m.get("body") or "[pièce jointe]").replace("\n", " ")[:80]
        self.v_rbar.set(f"↪ Réponse à {who} : {ex}")
        self.rbar.grid(row=3, column=0, sticky="ew", padx=6, pady=(2, 0))
        self.ent.focus_set()

    def start_edit(self, mid: int) -> None:
        m = self._find_msg(mid)
        if not m or int(m["sender_id"]) != self.me:
            return
        self.reply_to = 0
        self.editing = mid
        self.v_rbar.set("✏ Modification de ton message — Entrée pour enregistrer, Échap pour annuler")
        self.rbar.grid(row=3, column=0, sticky="ew", padx=6, pady=(2, 0))
        self.ent.delete("1.0", "end")
        self.ent.insert("1.0", m.get("body") or "")
        self.ent.focus_set()

    def cancel_reply_edit(self) -> None:
        if self.editing:
            self.ent.delete("1.0", "end")
        self.reply_to = 0
        self.editing = 0
        self.rbar.grid_remove()

    def delete_msg(self, mid: int) -> None:
        if not messagebox.askyesno(APP_TITLE, "Supprimer ce message pour tout le monde ?", parent=self):
            return
        self.bg(lambda: self.api.call("delete", message_id=mid), lambda j: self._replace_msg(j.get("message")), "Suppression : ")

    def msg_menu(self, e, mid: int) -> None:
        m = self._find_msg(mid)
        if not m:
            return
        menu = tk.Menu(self, tearoff=0, font=("Segoe UI Emoji", 10))
        menu.add_command(label="↪  Répondre", command=lambda: self.start_reply(mid))
        sub = tk.Menu(menu, tearoff=0, font=("Segoe UI Emoji", 12))
        for em in REACTIONS:
            sub.add_command(label=em, command=lambda x=em: self.react(mid, x))
        menu.add_cascade(label="☺  Réagir", menu=sub)
        if m.get("body"):
            menu.add_command(label="⧉  Copier le texte",
                             command=lambda: (self.clipboard_clear(), self.clipboard_append(m.get("body") or "")))
        sid = int(m["sender_id"])
        if sid != self.me and self.conv_peer.get(self.cur_conv) != sid:
            menu.add_command(label=f"🔒  Écrire en privé à {m.get('sender_pseudo') or self._pseudo(sid)}",
                             command=lambda: self.open_dm(sid))
        if sid == self.me and not int(m.get("deleted") or 0):
            menu.add_separator()
            if m.get("body"):
                menu.add_command(label="✏  Modifier", command=lambda: self.start_edit(mid))
            menu.add_command(label="🗑  Supprimer", command=lambda: self.delete_msg(mid))
        menu.tk_popup(e.x_root, e.y_root)

    def emoji_picker(self) -> None:
        w = tk.Toplevel(self)
        w.overrideredirect(True)
        w.configure(bg=C["LINE"])
        f = tk.Frame(w, bg=C["PANEL"])
        f.pack(padx=1, pady=1)

        def pick(x: str):
            self.ent.insert("insert", x)
            self.ent.focus_set()
            w.destroy()
        for i, em in enumerate(EMOJIS):
            b = tk.Label(f, text=em, bg=C["PANEL"], font=("Segoe UI Emoji", 15), cursor="hand2", padx=3)
            b.grid(row=i // 10, column=i % 10)
            b.bind("<Enter>", lambda e, b=b: b.configure(bg=C["SEL"]))
            b.bind("<Leave>", lambda e, b=b: b.configure(bg=C["PANEL"]))
            b.bind("<Button-1>", lambda e, x=em: pick(x))
        w.update_idletasks()
        x = self.b_emoji.winfo_rootx()
        y = self.b_emoji.winfo_rooty() - w.winfo_reqheight() - 4
        w.geometry(f"+{x}+{max(0, y)}")
        w.bind("<Escape>", lambda e: w.destroy())
        w.bind("<FocusOut>", lambda e: w.after(150, lambda: w.winfo_exists() and w.destroy()))
        w.focus_force()

    def send_file(self, images: bool = False, path: str = "") -> None:
        if not self.cur_conv:
            self.status("Connexion en cours… réessaie dans un instant.")
            return
        if not path:
            ft = [("Images", "*.png *.jpg *.jpeg *.gif *.webp *.bmp")] if images else []
            ft += [("Tous", "*.*"), ("Vidéos", "*.mp4 *.webm *.mkv *.mov"), ("PDF", "*.pdf"), ("Audio", "*.mp3 *.ogg *.wav *.m4a")]
            path = filedialog.askopenfilename(parent=self, title="Envoyer un fichier", filetypes=ft)
        if not path or not os.path.isfile(path):
            return
        cid = self.cur_conv
        self.status(f"Envoi de {os.path.basename(path)}…")

        def work():
            att = self.api.upload(path)
            return self.api.call("send", conversation_id=cid, kind=kind_for_mime(att["mime"]), attachment_id=att["id"], body="")
        self.bg(work, lambda j: (self.status("Envoyé ✔"), self._add_local(j.get("message"))), "Fichier : ")

    def _on_drop(self, e):
        try:
            files = [f for f in self.tk.splitlist(e.data) if os.path.isfile(f)]
        except Exception:
            files = []
        for f in files[:10]:
            self.send_file(path=f)
        return "copy"

    def _on_paste(self, e):
        try:
            from PIL import ImageGrab  # type: ignore
            data = ImageGrab.grabclipboard()
        except Exception:
            data = None
        if Image is not None and isinstance(data, Image.Image):
            if messagebox.askyesno(APP_TITLE, "Envoyer l'image du presse-papiers ?", parent=self):
                p = os.path.join(Paths.cache(), f"colle_{dt.datetime.now():%Y%m%d_%H%M%S}.png")
                data.save(p)
                self.send_file(path=p)
            return "break"
        if isinstance(data, list) and data and all(os.path.isfile(str(x)) for x in data):
            if messagebox.askyesno(APP_TITLE, f"Envoyer {len(data)} fichier(s) copié(s) ?", parent=self):
                for f in data[:10]:
                    self.send_file(path=str(f))
            return "break"
        return None

    def open_attachment(self, aid: int, kind: str) -> None:
        self.status("Téléchargement…")

        def done(path):
            self.status("Ouvert.")
            if kind == "audio":
                play_audio(path)
            elif kind == "video" and find_exe("ffplay"):
                popen_hidden([find_exe("ffplay"), "-autoexit", path])
            else:
                open_path(path)
        self.bg(lambda: self.api.download_media(aid, f"media_{aid}"), done, "Pièce jointe : ")

    def toggle_record(self) -> None:
        if not self.recording:
            if not self.cur_conv:
                return
            try:
                self.recorder.start()
            except Exception as e:
                self.status(f"⚠ Micro : {e}")
                return
            self.recording = True
            self._rec_t0 = time.time()
            self.b_rec._bg = C["ERR"]  # type: ignore[attr-defined]
            self.b_rec.configure(bg=C["ERR"])
            self._rec_tick()
        else:
            self.recording = False
            self.b_rec._bg = C["BTN"]  # type: ignore[attr-defined]
            self.b_rec.configure(text="🎤 Vocal", bg=C["BTN"])
            try:
                path = self.recorder.stop()
            except Exception as e:
                self.status(f"⚠ Vocal : {e}")
                return
            if path:
                self.send_file(path=path)

    def _rec_tick(self) -> None:
        if not self.recording:
            return
        s = int(time.time() - self._rec_t0)
        if s >= 120:
            self.toggle_record()
            return
        self.b_rec.configure(text=f"{'⏺' if s % 2 == 0 else '⚪'} {s // 60}:{s % 60:02d}  ⏹ Envoyer")
        self.status("🎤 Enregistrement… clique pour arrêter et envoyer (max 2 min)")
        self.after(500, self._rec_tick)

    def react_last(self, emoji: str) -> None:
        lst = self.msgs.get(self.cur_conv) or []
        target = next((m for m in reversed(lst) if int(m["sender_id"]) != self.me), lst[-1] if lst else None)
        if target:
            self.react(int(target["id"]), emoji)

    def react(self, mid: int, emoji: str) -> None:
        cur = self._find_msg(mid)
        remove = bool(cur and any(r["emoji"] == emoji and int(r["user_id"]) == self.me for r in cur.get("reactions") or []))

        def done(j):
            if cur is not None:
                cur["reactions"] = [{"user_id": int(r["user_id"]), "emoji": r["emoji"]} for r in j.get("reactions") or []]
            self._render_conv(keep_scroll=True)
        self.bg(lambda: self.api.call("react", message_id=mid, emoji=emoji, remove=remove), done, "Réaction : ")

    def search_dialog(self) -> None:
        w = tk.Toplevel(self)
        w.title("Chercher — Messager")
        w.configure(bg=C["BG"])
        w.transient(self)
        w.geometry("600x420")
        w.grid_columnconfigure(0, weight=1)
        w.grid_rowconfigure(1, weight=1)
        v = tk.StringVar()
        e = tk.Entry(w, textvariable=v, bg=C["ENTRY_BG"], fg=C["ENTRY_FG"], insertbackground=C["ENTRY_FG"], font=("Segoe UI", 11))
        e.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        lb = tk.Listbox(w, bg=C["CARD"], fg=C["TEXT"], selectbackground=C["SEL"], font=("Segoe UI Emoji", 10), bd=0)
        lb.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=8, pady=(0, 8))
        res: List[Dict[str, Any]] = []

        def go(*_):
            q = v.get().strip()
            if len(q) < 2:
                return

            def done(j):
                res.clear()
                res.extend(j.get("messages") or [])
                lb.delete(0, "end")
                for m in res:
                    cid = int(m["conversation_id"])
                    where = "Salon" if cid == self.pub_id else f"Privé {self._pseudo(self.conv_peer.get(cid, 0))}"
                    body = (m.get("body") or "").replace("\n", " ")[:90]
                    lb.insert("end", f"[{where}] {str(m.get('created_at'))[5:16]}  {m.get('sender_pseudo')} : {body}")
                if not res:
                    lb.insert("end", "(aucun résultat)")
            self.bg(lambda: self.api.call("search", q=q), done, "Recherche : ")

        def pick(*_):
            try:
                m = res[lb.curselection()[0]]
            except Exception:
                return
            cid, mid = int(m["conversation_id"]), int(m["id"])

            def after():
                if self.txt.tag_ranges(f"m{mid}"):
                    self._flash_msg(mid)
                else:
                    self.bg(lambda: self.api.call("history", conversation_id=cid, limit=200),
                            lambda j: (self._set_history(cid, j.get("messages") or []), self._flash_msg(mid)))
            self._open_conv(cid, then=after)
        btn(w, "Chercher", go).grid(row=0, column=1, padx=(0, 8))
        e.bind("<Return>", go)
        lb.bind("<Double-Button-1>", pick)
        lb.bind("<Return>", pick)
        e.focus_set()

    # ------------------------------------------------------------ reglages
    def set_status(self) -> None:
        lab = self.v_statut.get()
        code = next((c for c, l in STATUTS if l == lab), "disponible")
        self.cfg["statut"] = code
        self.cfg.save()
        self._draw_dot()
        self._render_list()
        self.bg(lambda: self.api.call("set_status", status=code), lambda j: self.status(f"Statut : {lab}"), "Statut : ")
        self._wake.set()

    def set_interval(self) -> None:
        lab = self.v_int.get()
        sec = dict(INTERVALLES).get(lab, 15)
        if sec == -1:
            v = simpledialog.askinteger(APP_TITLE, "Délai entre deux vérifications (secondes, 3 à 3600) :",
                                        parent=self, minvalue=3, maxvalue=3600, initialvalue=int(self.cfg["intervalle"] or 15))
            if not v:
                self.v_int.set(self._int_label(int(self.cfg["intervalle"] or 15)))
                return
            sec = v
            self.v_int.set(f"{sec} s")
        self.cfg["intervalle"] = int(sec)
        self.cfg.save()
        self.status(f"Vérification aux {self._int_label(int(sec))}.")
        self._wake.set()

    def _save_opts(self) -> None:
        self.cfg["pause_si_indispo"] = bool(self.v_pause.get())
        self.cfg.save()

    def toggle_sound(self) -> None:
        self.cfg["son"] = not bool(self.cfg["son"])
        self.cfg.save()
        self.b_son.configure(text="🔔" if self.cfg["son"] else "🔕")
        self.status("Son activé." if self.cfg["son"] else "Son coupé.")

    def cycle_theme(self) -> None:
        names = list(THEMES)
        cur = self.cfg["theme"] if self.cfg["theme"] in names else "norton"
        nxt = names[(names.index(cur) + 1) % len(names)]
        if messagebox.askyesno(APP_TITLE, f"Passer au thème « {THEME_NOMS[nxt]} » ?\nMessager va redémarrer.", parent=self):
            self.cfg["theme"] = nxt
            self.cfg.save()
            self.restart()

    def restart(self) -> None:
        self._save_geometry()
        try:
            if IS_WIN and self._mutex:
                ctypes.windll.kernel32.CloseHandle(self._mutex)
                self._mutex = None
        except Exception:
            pass
        args = [sys.executable, os.path.abspath(__file__)]
        if Paths.profil != "defaut":
            args += ["--profil", Paths.profil]
        popen_hidden(args)
        self.quit_app()

    def settings(self) -> None:
        w = tk.Toplevel(self)
        w.title("Réglages — Messager")
        w.configure(bg=C["BG"])
        w.transient(self)
        vars_: Dict[str, tk.StringVar] = {}
        for i, (lab, k) in enumerate([("Pseudo", "pseudo"), ("Serveur (URL de l'API)", "serveur")]):
            tk.Label(w, text=lab, bg=C["BG"], fg=C["FG"]).grid(row=i, column=0, sticky="w", padx=8, pady=4)
            v = tk.StringVar(value=str(self.cfg[k] or ""))
            tk.Entry(w, textvariable=v, width=48, bg=C["ENTRY_BG"], fg=C["ENTRY_FG"],
                     insertbackground=C["ENTRY_FG"]).grid(row=i, column=1, padx=8, pady=4)
            vars_[k] = v
        v_not = tk.BooleanVar(value=bool(self.cfg["notifications"]))
        v_son = tk.BooleanVar(value=bool(self.cfg["son"]))
        v_sal = tk.BooleanVar(value=bool(self.cfg["notif_salon"]))
        v_th = tk.StringVar(value=self.cfg["theme"] or "norton")
        for r, (t, v) in enumerate([("Notifications de nouveaux messages", v_not), ("Son", v_son),
                                    ("Notifier aussi pour le Salon général (pas seulement le privé)", v_sal)], start=2):
            tk.Checkbutton(w, text=t, variable=v, bg=C["BG"], fg=C["FG"], selectcolor=C["ENTRY_BG"],
                           activebackground=C["BG"], activeforeground=C["FG"]).grid(row=r, column=1, sticky="w", padx=8)
        tk.Label(w, text="Thème", bg=C["BG"], fg=C["FG"]).grid(row=5, column=0, sticky="w", padx=8)
        ttk.Combobox(w, textvariable=v_th, values=list(THEMES), state="readonly", width=10).grid(row=5, column=1, sticky="w", padx=8)
        tk.Label(w, text=f"Identité locale (sans mot de passe) : empreinte {self.ident.fingerprint()}\n"
                         f"Données : {Paths.data()}\n"
                         "Serveur privé : installe les pages PHP de Messager sur ton serveur et mets son URL ici.",
                 bg=C["BG"], fg=C["DIM"], justify="left").grid(row=6, column=0, columnspan=2, sticky="w", padx=8, pady=6)

        def ok():
            old_srv = self.cfg["serveur"]
            self.cfg["pseudo"] = vars_["pseudo"].get().strip()
            self.cfg["serveur"] = vars_["serveur"].get().strip() or DEFAULT_SERVER
            self.cfg["notifications"] = bool(v_not.get())
            self.cfg["son"] = bool(v_son.get())
            self.cfg["notif_salon"] = bool(v_sal.get())
            self.b_son.configure(text="🔔" if self.cfg["son"] else "🔕")
            theme_changed = v_th.get() != self.cfg["theme"]
            self.cfg["theme"] = v_th.get()
            srv_changed = old_srv != self.cfg["serveur"]
            if srv_changed:
                self.cfg["dernier_id"] = 0
                self.cfg["inscrit"] = False
            self.cfg.save()
            w.destroy()
            self.v_pseudo.set(self.cfg["pseudo"])
            if theme_changed or srv_changed:
                self.restart()
                return
            self.bg(self.api.register, lambda u: (self.status(f"Connecté à {self.api.base}."), self.refresh_now()), "Serveur : ")

        def test():
            url = vars_["serveur"].get().strip().rstrip("/") + "/api.php"
            self.bg(lambda: requests.post(url, json={"action": "ping"}, timeout=10).json(),
                    lambda j: messagebox.showinfo(APP_TITLE, f"Serveur OK ✔ (version {j.get('version')})" if j.get("ok") else f"Erreur : {j}", parent=w),
                    "Test : ")

        def suppr():
            if not messagebox.askyesno(APP_TITLE, "Supprimer pour de bon ton compte Messager sur ce serveur ?\n"
                                       "(tes messages, fichiers et conversations privées seront effacés)", parent=w):
                return

            def done(j):
                self.cfg["inscrit"] = False
                self.cfg["pseudo"] = ""
                self.cfg["dernier_id"] = 0
                self.cfg.save()
                messagebox.showinfo(APP_TITLE, "Compte supprimé. Messager va se fermer.", parent=self)
                self.quit_app()
            self.bg(lambda: self.api.call("delete_account", confirm=True), done, "Suppression du compte : ")

        f = tk.Frame(w, bg=C["BG"])
        f.grid(row=7, column=0, columnspan=2, pady=8)
        btn(f, "Serveur par défaut (marcsevigny.ca)", lambda: vars_["serveur"].set(DEFAULT_SERVER)).pack(side="left", padx=4)
        btn(f, "Tester", test).pack(side="left", padx=4)
        btn(f, "Enregistrer", ok).pack(side="left", padx=4)
        btn(f, "Supprimer mon compte…", suppr).pack(side="left", padx=(20, 4))
        btn(f, "🧹 Vider le Salon (admin)…", lambda: self.admin_flush(w)).pack(side="left", padx=4)

    def admin_flush(self, parent=None) -> None:
        parent = parent or self
        pw = simpledialog.askstring(APP_TITLE, "Mot de passe administrateur :", show="*", parent=parent)
        if not pw:
            return
        if not messagebox.askyesno(APP_TITLE, "Effacer TOUS les messages du Salon général pour tout le monde ?\n"
                                   "(messages, réactions et fichiers du Salon — irréversible)", parent=parent):
            return

        def done(j):
            self.msgs[self.pub_id] = []
            self.cfg["salon_vide_le"] = int(j.get("public_flush") or 0)
            self.cfg.save()
            if self.cur_conv == self.pub_id:
                self._render_conv()
            self.status(f"🧹 Salon vidé ({j.get('deleted', 0)} messages).")
        self.bg(lambda: self.api.call("admin_flush_public", password=pw, retries=1), done, "Vider le Salon : ")

    # ------------------------------------------------------------ fenetre / icone tray
    def _setup_tray(self) -> None:
        if pystray is None or Image is None:
            return
        try:
            base = make_icon_image(64)
            alt = base.copy()
            d = ImageDraw.Draw(alt)
            d.ellipse((34, 0, 63, 29), fill=(230, 40, 40, 255), outline=(255, 255, 255, 255), width=3)
            self._tray_imgs = [base, alt]

            def st(lab):
                return lambda i, it: self.ui(lambda: (self.v_statut.set(lab), self.set_status()))
            menu = pystray.Menu(
                pystray.MenuItem("Ouvrir Messager", lambda i, it: self.ui(self.show), default=True),
                pystray.MenuItem("Salon général", lambda i, it: self.ui(lambda: (self.show(), self.open_public()))),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Disponible", st("Disponible")),
                pystray.MenuItem("Absent", st("Absent")),
                pystray.MenuItem("Occupé", st("Occupé")),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quitter Messager", lambda i, it: self.ui(self.quit_app)),
            )
            self._tray = pystray.Icon("PadawanMessager", base, "Messager (Padawan)", menu)
            self._tray.run_detached()
        except Exception as e:
            jlog(f"tray: {e}")
            self._tray = None

    def _check_show_request(self) -> None:
        p = os.path.join(Paths.data(), "afficher.req")
        try:
            if os.path.isfile(p):
                os.remove(p)
                self.show()
        except Exception:
            pass
        self.after(700, self._check_show_request)

    def hide(self) -> None:
        self._save_geometry()
        if self._tray is not None:
            self.withdraw()
        else:
            self.iconify()

    def show(self) -> None:
        self.deiconify()
        if self.cfg["zoom"]:
            try:
                self.state("zoomed")
            except Exception:
                pass
        self.lift()
        try:
            self.attributes("-topmost", True)
            self.after(200, lambda: self.attributes("-topmost", False))
        except Exception:
            pass
        self.focus_force()
        self.ent.focus_set()
        self._on_focus()

    def quit_app(self) -> None:
        self._stop.set()
        self._wake.set()
        try:
            if self._tray is not None:
                self._tray.stop()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass


# ================================================================ instance unique
def _single_instance():
    if not IS_WIN:
        return True, None
    k32 = ctypes.windll.kernel32
    k32.CreateMutexW.restype = wintypes.HANDLE
    name = _MUTEX_BASE + ("" if Paths.profil == "defaut" else "_" + Paths.profil)
    h = k32.CreateMutexW(None, False, name)
    if ctypes.GetLastError() == 183:
        return False, h
    return True, h


def _focus_existing(title: str) -> bool:
    """Demande a l'instance ouverte de s'afficher (fonctionne meme si sa fenetre est cachee)."""
    try:
        with open(os.path.join(Paths.data(), "afficher.req"), "w") as f:
            f.write(str(time.time()))
    except Exception:
        pass
    if not IS_WIN:
        return False
    try:
        u32 = ctypes.windll.user32
        hwnd = u32.FindWindowW("TkTopLevel", title)
        if hwnd:
            u32.ShowWindow(hwnd, 9)
            u32.SetForegroundWindow(hwnd)
            return True
    except Exception:
        pass
    return False


# ================================================================ test API sans interface (2 identites jetables)
def smoke_api(server: str) -> int:
    """Salon public, prive, ecrit..., presence, modifier/supprimer, reponse, recherche, image, apercu.
    Les 2 comptes de test sont effaces du serveur a la fin."""
    errs: List[str] = []
    out: List[str] = []
    tag = uuid.uuid4().hex[:6]
    apis = []
    profils = []
    for nom in ("A", "B"):
        Paths.profil = f"smoke2{nom}_{tag}"
        profils.append(Paths.data())
        cfg = Config().load()
        cfg["serveur"] = server
        cfg["pseudo"] = f"Test{nom}2_{tag}"
        cfg.save()
        ident = Identity()
        api = Api(cfg, ident)
        try:
            u = api.register()
            out.append(f"inscrit {u.get('pseudo')} id={u.get('id')}")
        except Exception as e:
            errs.append(f"register {nom}: {e}")
            break
        apis.append((api, cfg, ident))

    def chk(cond: bool, ok: str, bad: str) -> None:
        if cond:
            out.append("OK  " + ok)
        else:
            errs.append(bad)

    if len(apis) == 2:
        (a, ca, _ia), (b, cb, _ib) = apis
        try:
            v = a.call("ping")
            chk(int(v.get("version") or 0) >= 2, f"serveur version {v.get('version')}", f"serveur pas en v2 : {v}")
            pub = int(a.call("public_room")["conversation_id"])
            out.append(f"Salon general = conversation {pub}")
            mp = a.call("send", conversation_id=pub, body=f"Bonjour tout le monde ({tag}) https://www.youtube.com/watch?v=dQw4w9WgXcQ")["message"]
            rb = b.call("poll", after_id=int(mp["id"]) - 1, poll_sec=5)
            got = [m for m in rb["messages"] if int(m["id"]) == int(mp["id"])]
            chk(bool(got) and got[0].get("sender_pseudo") == ca["pseudo"], "B lit le message PUBLIC de A (avec pseudo)", "B ne voit pas le message public")
            chk(int(rb.get("public_id") or 0) == pub, "poll renvoie public_id", "public_id absent")
            pres = {int(u["id"]): u for u in rb["presence"]}
            chk(bool(pres.get(int(ca["user_id"]), {}).get("online")), "presence : A en ligne vu par B", "A pas en ligne pour B")
            r = b.call("react", message_id=int(mp["id"]), emoji="❤️")
            chk(len(r["reactions"]) == 1, "reaction ❤️ sur message public", "reaction publique echouee")
            cid = int(a.call("open_dm", user_id=cb["user_id"])["conversation_id"])
            mq = a.call("send", conversation_id=cid, body=f"Psst, c'est privé ({tag})", reply_to=int(mp["id"]))["message"]
            rb = b.call("poll", after_id=int(mq["id"]) - 1)
            got = [m for m in rb["messages"] if int(m["id"]) == int(mq["id"])]
            chk(bool(got) and int(got[0].get("reply_to") or 0) == int(mp["id"]), "B recoit le message PRIVE (avec citation)", "prive non recu")
            b.call("typing", conversation_id=cid)
            ra = a.call("poll", after_id=10 ** 12)
            chk(any(int(t["user_id"]) == int(cb["user_id"]) and int(t["conversation_id"]) == cid for t in ra.get("typing") or []),
                "A voit « B écrit… »", "typing non vu")
            b.call("typing", conversation_id=cid, stop=True)
            t0 = int(ra["server_time"])
            time.sleep(1.1)
            a.call("edit", message_id=int(mp["id"]), body=f"Bonjour (modifié) {tag}")
            rb = b.call("poll", after_id=10 ** 12, edits_since=t0)
            ed = [m for m in rb.get("edits") or [] if int(m["id"]) == int(mp["id"])]
            chk(bool(ed) and "modifié" in (ed[0].get("body") or ""), "modification vue par B", "modification non vue")
            try:
                b.call("edit", message_id=int(mp["id"]), body="pirate", retries=1)
                errs.append("B a pu modifier le message de A !")
            except ApiError:
                out.append("OK  B ne peut pas modifier le message de A")
            a.call("delete", message_id=int(mq["id"]))
            h = b.call("history", conversation_id=cid, limit=5)
            dm = [m for m in h["messages"] if int(m["id"]) == int(mq["id"])]
            chk(bool(dm) and int(dm[0].get("deleted") or 0) == 1 and not dm[0].get("body"), "suppression vue par B", "suppression non vue")
            s = b.call("search", q=tag)
            chk(any(int(m["id"]) == int(mp["id"]) for m in s["messages"]), "recherche trouve le message public", "recherche vide")
            img_path = os.path.join(tempfile.gettempdir(), f"messager_smoke_{tag}.png")
            make_icon_image(96).save(img_path)
            att = b.upload(img_path)
            b.call("send", conversation_id=pub, kind="image", attachment_id=att["id"], body="")
            dl = a.download_media(int(att["id"]), f"smoke_{tag}.png")
            chk(os.path.getsize(dl) == os.path.getsize(img_path), "image du Salon telechargee par A", "image publique illisible")
            pv = a.call("preview", url="https://www.youtube.com/watch?v=dQw4w9WgXcQ")["preview"]
            out.append(f"apercu YouTube : titre={str(pv.get('title'))[:60]!r}")
            b.call("set_status", status="invisible")
            pa = a.call("presence")
            st = next((u for u in pa["users"] if int(u["id"]) == int(cb["user_id"])), {})
            chk(not st.get("online"), "invisible = hors ligne pour les autres", "invisible visible")
        except Exception:
            errs.append(traceback.format_exc())
    for api, cfg, _i in apis:
        try:
            api.call("delete_account", confirm=True)
            out.append(f"compte {cfg['pseudo']} supprime")
        except Exception as e:
            errs.append(f"delete_account {cfg['pseudo']}: {e}")
    for d in profils:
        shutil.rmtree(d, ignore_errors=True)

    def _safe(s):
        enc = sys.stdout.encoding or "utf-8"
        return s.encode(enc, errors="replace").decode(enc, errors="replace")
    print(_safe("\n".join(out)))
    print(_safe("SMOKE-API " + ("OK" if not errs else "ERREURS")))
    for e in errs:
        print(_safe("ERREUR: " + str(e)))
    return 0 if not errs else 1


def supprimer_compte_profil() -> int:
    """Efface du serveur le compte du profil courant (ex. anciens comptes de test), puis le profil local."""
    cfg = Config().load()
    api = Api(cfg, Identity())
    try:
        j = api.call("delete_account", confirm=True)
        print(f"{cfg['pseudo']}: {j.get('message')}")
    except Exception as e:
        print(f"{cfg['pseudo']}: {e}")
        return 1
    if Paths.profil != "defaut":
        shutil.rmtree(Paths.data(), ignore_errors=True)
    return 0


def cli_check() -> int:
    print(f"Messager v{APP_FILE_VER}")
    print(f"Données : {Paths.data()}")
    cfg = Config().load()
    print(f"Serveur : {cfg['serveur']}")
    print(f"Pseudo  : {cfg['pseudo'] or '(aucun)'}  inscrit={cfg['inscrit']}")
    print(f"requests: {'OK' if requests else 'ABSENT'}  Pillow: {'OK' if Image else 'ABSENT'}  "
          f"pystray: {'OK' if pystray else 'absent'}  glisser-deposer: {'OK' if DND_FILES else 'absent'}")
    print(f"Vocal   : {'OK' if Recorder.available() else 'sounddevice/soundfile absents'}")
    print(f"ffplay  : {find_exe('ffplay') or 'absent'}   yt-dlp : {find_exe('yt-dlp') or 'absent'}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Messager v2 - messagerie du Projet Padawan")
    ap.add_argument("--profil", default="defaut", help="profil local (pour tester 2 identites sur un PC)")
    ap.add_argument("--cache", action="store_true", help="demarre masque")
    ap.add_argument("--smoke-api", action="store_true", help="test 2 identites jetables contre le serveur puis sortie")
    ap.add_argument("--serveur", default="", help="URL serveur (smoke)")
    ap.add_argument("--make-icons", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--supprimer-compte", action="store_true", help="efface le compte du --profil sur le serveur")
    ap.add_argument("--screenshot", default="", help="(test) capture la fenetre apres 7 s puis quitte")
    ap.add_argument("--taille", default="", help="(test) force la taille, ex. 760x500")
    a = ap.parse_args(argv)
    Paths.profil = re.sub(r"[^\w-]", "_", a.profil)[:40] or "defaut"
    if a.make_icons:
        print(generate_app_icons(os.path.dirname(os.path.abspath(__file__)), force=True))
        return 0
    if a.check:
        return cli_check()
    if a.smoke_api:
        return smoke_api(a.serveur or DEFAULT_SERVER)
    if a.supprimer_compte:
        return supprimer_compte_profil()
    ok, h = _single_instance()
    title = APP_TITLE if Paths.profil == "defaut" else f"{APP_TITLE} ({Paths.profil})"
    if not ok:
        _focus_existing(title)
        return 0
    cfg = Config().load()
    app = MessagerApp(cfg, Identity(), start_hidden=a.cache, mutex=h)
    if a.taille:
        app.geometry(a.taille)
    if a.screenshot:
        def snap():
            try:
                from PIL import ImageGrab  # type: ignore
                app.update()
                x, y = app.winfo_rootx(), app.winfo_rooty()
                w, hh = app.winfo_width(), app.winfo_height()
                full = ImageGrab.grab(all_screens=False)
                k = full.size[0] / max(1, app.winfo_screenwidth())  # mise a l'echelle Windows (ex. 150 %)
                full.crop((int(x * k), int(y * k), int((x + w) * k), int((y + hh) * k))).save(a.screenshot)
                ey = app.ent.winfo_rooty() - y
                print(f"geom={app.geometry()} ent_visible={bool(app.ent.winfo_ismapped())} ent_y={ey} "
                      f"ent_h={app.ent.winfo_height()} envoyer_visible={bool(app.b_send.winfo_ismapped())} win_h={hh} "
                      f"dans_fenetre={ey + app.ent.winfo_height() <= hh}")
            except Exception as e:
                print(f"screenshot: {e}")
            app.quit_app()
        app.after(7000, snap)
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
