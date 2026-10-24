# -*- coding: utf-8 -*-
"""
Facteur — surveillant de dossiers et commandes a distance signees du Projet Padawan.

But : surveiller des dossiers (boite aux lettres = Telechargements, obtenu par
l'API Windows FOLDERID_Downloads) et appliquer des regles ordonnees aux fichiers
qui y arrivent. Une page web ne peut deposer un fichier que dans Telechargements ;
Facteur y lit des commandes a distance SIGNEES (.padawan, HMAC-SHA256), limitees a
une liste blanche d'actions. Les commandes CMD/PowerShell libres n'existent que dans
les regles locales creees par Marc dans l'application, jamais dans un .padawan.

Theme Norton bleu/cyan/jaune Consolas + Sombre/Clair, interface francaise, instance
unique (mutex), liens cliquables, infobulles, F1, options --smoke / --check.

Donnees : C:\\web\\FTP_HOME\\FACTEUR si FTP_HOME existe, sinon
%USERPROFILE%\\Documents\\Padawan\\Facteur (variable FACTEUR_DATA). La cle secrete
n'est PAS dans FTP_HOME en clair : protegee par Windows DPAPI.
"""
from __future__ import annotations

import argparse
import base64
import ctypes
import datetime as dt
import fnmatch
import hashlib
import hmac
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
import uuid
import zipfile
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog
    import tkinter.font as tkfont
except Exception:
    tk = None  # type: ignore
    ttk = messagebox = filedialog = tkfont = None  # type: ignore

IS_WIN = sys.platform.startswith("win")
if IS_WIN:
    from ctypes import wintypes  # noqa: F401

try:
    from watchdog.observers import Observer  # type: ignore
    from watchdog.events import FileSystemEventHandler  # type: ignore
    WATCHDOG = True
except Exception:
    Observer = None  # type: ignore
    FileSystemEventHandler = object  # type: ignore
    WATCHDOG = False

APP_NAME = "Facteur"
APP_TITLE = "Facteur"
APP_FILE_VER = 1
IS_WIN = sys.platform.startswith("win")
CREATE_NO_WINDOW = 0x08000000

BASE = os.path.dirname(os.path.abspath(__file__))
FTP_HOME = r"C:\web\FTP_HOME"
PADAWAN_DIR_DEFAULT = r"C:\web\FTP_HOME\SECTION PYTHON\Projet Padawan"
_MUTEX_NAME = "Local\\Facteur_SingleInstance"
SIG_VERSION = 1
DEFAULT_EXPIRE_SEC = 600  # fenetre anti-rejeu : 10 minutes
SEEN_KEEP = 4000

logger = logging.getLogger("facteur")

try:
    import facteur_boite as boite_sql  # type: ignore
except ImportError:
    boite_sql = None  # type: ignore


def _portable_data_dir(app: str, ftp_sub: str) -> str:
    env = os.environ.get(app.upper() + "_DATA", "").strip()
    if env:
        return env
    root = os.environ.get("PADAWAN_DATA", "").strip()
    if root:
        return os.path.join(root, app)
    if os.path.isdir(FTP_HOME):
        return os.path.join(FTP_HOME, ftp_sub)
    return os.path.join(os.path.expanduser("~"), "Documents", "Padawan", app)


DEFAULT_DATA_DIR = _portable_data_dir("Facteur", "FACTEUR")


class Paths:
    data = DEFAULT_DATA_DIR

    @classmethod
    def set(cls, d: str) -> None:
        cls.data = os.path.abspath(d)

    @classmethod
    def config(cls) -> str:
        return os.path.join(cls.data, "facteur_config.json")

    @classmethod
    def log(cls) -> str:
        return os.path.join(cls.data, "facteur.log")

    @classmethod
    def traites(cls) -> str:
        return os.path.join(cls.data, "_Traités")

    @classmethod
    def quarantaine(cls) -> str:
        return os.path.join(cls.data, "_Quarantaine")

    @classmethod
    def seen(cls) -> str:
        return os.path.join(cls.data, "seen_ids.json")

    @classmethod
    def keyfile(cls) -> str:
        """Cle protegee DPAPI : %LOCALAPPDATA%\\Padawan\\Facteur (hors FTP_HOME) pour les donnees normales,
        dans le dossier de donnees seulement pour un dossier de test (--data)."""
        if os.path.abspath(cls.data) == os.path.abspath(DEFAULT_DATA_DIR) and os.environ.get("LOCALAPPDATA"):
            return os.path.join(os.environ["LOCALAPPDATA"], "Padawan", "Facteur", "facteur_cle.dpapi")
        return os.path.join(cls.data, "facteur_cle.dpapi")

    @classmethod
    def state(cls) -> str:
        return os.path.join(cls.data, "facteur_etat.json")

    @classmethod
    def signal(cls) -> str:
        return os.path.join(cls.data, "_signal")

    @classmethod
    def creds_boites(cls) -> str:
        if boite_sql is None:
            return os.path.join(cls.data, "boites_sql_creds.dpapi")
        return boite_sql.creds_path(cls.data, DEFAULT_DATA_DIR)


# ================================================================ journal
class Journal:
    """facteur.log (rotation) + memoire pour la vue filtrable de l'application."""

    def __init__(self) -> None:
        self.items: List[Dict[str, str]] = []
        self.lock = threading.Lock()
        self.listeners: List[Callable[[Dict[str, str]], None]] = []

    def setup(self) -> None:
        if logger.handlers:
            return
        logger.setLevel(logging.INFO)
        try:
            os.makedirs(Paths.data, exist_ok=True)
            h = logging.handlers.RotatingFileHandler(Paths.log(), maxBytes=2_000_000, backupCount=5, encoding="utf-8")
            h.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", "%Y-%m-%d %H:%M:%S"))
            logger.addHandler(h)
        except OSError:
            logger.addHandler(logging.NullHandler())
        self._load_tail()

    def _load_tail(self) -> None:
        try:
            with open(Paths.log(), "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()[-1500:]
        except OSError:
            return
        for ln in lines:
            parts = [x.strip() for x in ln.rstrip("\n").split(" | ")]
            if len(parts) >= 4:
                self.items.append({"ts": parts[0], "niveau": parts[1], "cat": parts[2],
                                   "msg": " | ".join(parts[3:])})

    def add(self, niveau: str, cat: str, msg: str) -> None:
        msg = msg.replace("\n", " ⏎ ")
        e = {"ts": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "niveau": niveau, "cat": cat, "msg": msg}
        lvl = {"INFO": logging.INFO, "OK": logging.INFO, "ALERTE": logging.WARNING, "REFUS": logging.WARNING,
               "ERREUR": logging.ERROR}.get(niveau, logging.INFO)
        logger.log(lvl, "%s | %s", cat, msg)
        with self.lock:
            self.items.append(e)
            if len(self.items) > 5000:
                del self.items[:1000]
        for fn in list(self.listeners):
            try:
                fn(e)
            except Exception:
                pass


JOURNAL = Journal()


def jlog(niveau: str, cat: str, msg: str) -> None:
    JOURNAL.add(niveau, cat, msg)


# ================================================================ utilitaires
def now_ts() -> int:
    return int(time.time())


def stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def sha256_file(p: str) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def unique_path(p: str) -> str:
    if not os.path.exists(p):
        return p
    b, e = os.path.splitext(p)
    for i in range(2, 10000):
        c = f"{b} ({i}){e}"
        if not os.path.exists(c):
            return c
    return f"{b}_{uuid.uuid4().hex[:6]}{e}"


def safe_name(s: str) -> str:
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", s or "").strip(" .")
    return s[:180] or "fichier"


def open_path(p: str) -> bool:
    if not p:
        return False
    try:
        if re.match(r"(?i)^(https?|mailto|file):", p):
            import webbrowser
            webbrowser.open(p)
        elif IS_WIN:
            os.startfile(p)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", p], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception as ex:
        jlog("ERREUR", "ui", f"ouverture {p} : {ex}")
        return False


def reveal(p: str) -> None:
    if IS_WIN and os.path.exists(p):
        try:
            subprocess.Popen(["explorer", "/select,", os.path.normpath(p)], creationflags=CREATE_NO_WINDOW)
            return
        except Exception:
            pass
    open_path(os.path.dirname(p) if os.path.isfile(p) else p)


def find_pythonw() -> str:
    cands = [os.path.join(os.environ.get("LOCALAPPDATA", ""), "Python", "pythoncore-3.14-64", "pythonw.exe")]
    exe = sys.executable or ""
    if exe:
        cands.insert(0, os.path.join(os.path.dirname(exe), "pythonw.exe"))
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
    c = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Python", "pythoncore-3.14-64", "python.exe")
    if os.path.isfile(c):
        return c
    return exe or shutil.which("python") or "python"


def padawan_dir() -> str:
    for d in (BASE, PADAWAN_DIR_DEFAULT):
        if os.path.isfile(os.path.join(d, "grimoire1.py")) or os.path.isfile(os.path.join(d, "padawan39.py")):
            return d
    return BASE


def find_script(*names: str) -> str:
    for d in (BASE, padawan_dir(), PADAWAN_DIR_DEFAULT):
        for n in names:
            p = os.path.join(d, n)
            if os.path.isfile(p):
                return p
    return ""


def module_ok(name: str) -> bool:
    try:
        __import__(name)
        return True
    except Exception:
        return False


IDLE_PRIORITY = 0x00000040
BELOW_NORMAL = 0x00004000


def run_hidden(args: Any, timeout: float = 120, low: bool = True, **kw) -> subprocess.CompletedProcess:
    kw.setdefault("stdin", subprocess.DEVNULL)
    kw.setdefault("stdout", subprocess.PIPE)
    kw.setdefault("stderr", subprocess.STDOUT)
    if IS_WIN:
        kw["creationflags"] = kw.get("creationflags", 0) | CREATE_NO_WINDOW | (BELOW_NORMAL if low else 0)
    return subprocess.run(args, timeout=timeout, **kw)


def popen_detached(args: Any, low: bool = True, visible: bool = False, **kw) -> subprocess.Popen:
    kw.setdefault("stdin", subprocess.DEVNULL)
    kw.setdefault("stdout", subprocess.DEVNULL)
    kw.setdefault("stderr", subprocess.DEVNULL)
    if IS_WIN:
        fl = (BELOW_NORMAL if low else 0)
        fl |= 0x00000010 if visible else CREATE_NO_WINDOW   # CREATE_NEW_CONSOLE ou cachee
        kw["creationflags"] = kw.get("creationflags", 0) | fl
    return subprocess.Popen(args, **kw)


def decode_bytes(b: bytes) -> str:
    for enc in ("utf-8", "cp850", "cp1252"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return b.decode("utf-8", errors="replace")


# ================================================================ Windows : dossier Telechargements (FOLDERID_Downloads)
def known_folder_downloads() -> str:
    """Chemin reel de Telechargements via SHGetKnownFolderPath(FOLDERID_Downloads) :
    marche en francais comme en anglais, et si le dossier a ete deplace (D:, OneDrive...)."""
    if IS_WIN:
        try:
            class GUID(ctypes.Structure):
                _fields_ = [("Data1", ctypes.c_uint32), ("Data2", ctypes.c_uint16), ("Data3", ctypes.c_uint16),
                            ("Data4", ctypes.c_ubyte * 8)]
            g = GUID(0x374DE290, 0x123F, 0x4565, (ctypes.c_ubyte * 8)(0x91, 0x64, 0x39, 0xC4, 0x92, 0x5E, 0x46, 0x7B))
            p = ctypes.c_wchar_p()
            shell32 = ctypes.windll.shell32
            shell32.SHGetKnownFolderPath.argtypes = [ctypes.POINTER(GUID), ctypes.c_uint32, ctypes.c_void_p,
                                                     ctypes.POINTER(ctypes.c_wchar_p)]
            if shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(p)) == 0:
                val = p.value
                ctypes.windll.ole32.CoTaskMemFree(p)
                if val:
                    return val
        except Exception:
            pass
    return os.path.join(os.path.expanduser("~"), "Downloads")


# ================================================================ Windows DPAPI (protection de la cle secrete)
_ENTROPY = b"Facteur-Padawan-v1"


def _dpapi(data: bytes, protect: bool) -> bytes:
    if not IS_WIN:
        raise RuntimeError("DPAPI indisponible hors Windows")
    try:
        import win32crypt  # type: ignore
        if protect:
            return win32crypt.CryptProtectData(data, "Facteur", _ENTROPY, None, None, 0x01)
        return win32crypt.CryptUnprotectData(data, _ENTROPY, None, None, 0x01)[1]
    except ImportError:
        pass

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def mk(b: bytes) -> Tuple[BLOB, Any]:
        buf = ctypes.create_string_buffer(b, len(b))
        return BLOB(len(b), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf

    crypt32 = ctypes.windll.crypt32
    k32 = ctypes.windll.kernel32
    k32.LocalFree.argtypes = [ctypes.c_void_p]
    bin_, _k1 = mk(data)
    ent, _k2 = mk(_ENTROPY)
    out = BLOB()
    if protect:
        ok = crypt32.CryptProtectData(ctypes.byref(bin_), "Facteur", ctypes.byref(ent), None, None, 0x01, ctypes.byref(out))
    else:
        ok = crypt32.CryptUnprotectData(ctypes.byref(bin_), None, ctypes.byref(ent), None, None, 0x01, ctypes.byref(out))
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        k32.LocalFree(ctypes.cast(out.pbData, ctypes.c_void_p))


class KeyStore:
    """Cle HMAC de 32 octets, protegee par DPAPI (liee au compte Windows de Marc).
    Affichable UNE seule fois apres sa creation (ou apres regeneration)."""

    def __init__(self) -> None:
        self.path = Paths.keyfile()
        self.meta_path = self.path + ".json"
        self._cache: Optional[bytes] = None

    def exists(self) -> bool:
        return os.path.isfile(self.path)

    def meta(self) -> Dict[str, Any]:
        try:
            with open(self.meta_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_meta(self, m: Dict[str, Any]) -> None:
        with open(self.meta_path, "w", encoding="utf-8") as f:
            json.dump(m, f, ensure_ascii=False, indent=1)

    def create(self) -> bytes:
        key = os.urandom(32)
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        if IS_WIN:
            blob = b"DPAPI1" + _dpapi(key, True)
        else:  # tests hors Windows seulement
            blob = b"PLAIN1" + key
        tmp = self.path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(blob)
        os.replace(tmp, self.path)
        self._save_meta({"cree": dt.datetime.now().isoformat(timespec="seconds"), "montree": False,
                         "empreinte": hashlib.sha256(key).hexdigest()[:12], "protection": blob[:6].decode()})
        self._cache = key
        jlog("ALERTE", "cle", f"nouvelle cle secrete creee (empreinte {hashlib.sha256(key).hexdigest()[:12]})")
        return key

    def load(self) -> bytes:
        if self._cache:
            return self._cache
        if not self.exists():
            raise RuntimeError("aucune cl\u00e9 de connexion (Options > Mode avanc\u00e9 > Cr\u00e9er ma cl\u00e9)")
        with open(self.path, "rb") as f:
            blob = f.read()
        if blob.startswith(b"DPAPI1"):
            key = _dpapi(blob[6:], False)
        elif blob.startswith(b"PLAIN1") and not IS_WIN:
            key = blob[6:]
        else:
            raise RuntimeError("fichier de cle illisible")
        self._cache = key
        return key

    def fingerprint(self) -> str:
        if not self.exists():
            return "aucune cl\u00e9 (rien \u00e0 faire si tu n'utilises pas le mode avanc\u00e9)"
        try:
            return hashlib.sha256(self.load()).hexdigest()[:12]
        except Exception as ex:
            return f"(erreur : {ex})"

    def reveal_once(self) -> Optional[str]:
        m = self.meta()
        key = self.load()
        m = self.meta()
        if m.get("montree"):
            return None
        m["montree"] = True
        m["montree_le"] = dt.datetime.now().isoformat(timespec="seconds")
        self._save_meta(m)
        jlog("ALERTE", "cle", "cle secrete affichee (une seule fois)")
        return key.hex()

    def regenerate(self) -> None:
        self._cache = None
        self.create()


# ================================================================ signature des commandes .padawan
SIGNED_FIELDS = ("v", "id", "ts", "expire", "action", "params")


def canonical(cmd: Dict[str, Any]) -> bytes:
    """Contenu canonique signe : JSON trie, sans espaces, UTF-8 (identique a PHP :
    ksort recursif + json_encode(JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES|JSON_UNESCAPED_LINE_TERMINATORS))."""
    body = {k: cmd.get(k) for k in SIGNED_FIELDS}
    if not body.get("params"):
        body["params"] = {}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sign_command(cmd: Dict[str, Any], key: bytes) -> str:
    return hmac.new(key, canonical(cmd), hashlib.sha256).hexdigest()


def make_command(action: str, params: Dict[str, Any], key: bytes, expire_sec: int = DEFAULT_EXPIRE_SEC,
                 ts: Optional[int] = None, cid: str = "") -> Dict[str, Any]:
    t = int(ts if ts is not None else now_ts())
    cmd = {"v": SIG_VERSION, "id": cid or uuid.uuid4().hex, "ts": t, "expire": t + int(expire_sec),
           "action": action, "params": params or {}}
    cmd["sig"] = sign_command(cmd, key)
    return cmd


ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,80}$")


# ================================================================ configuration et modele
DEFAULT_INTERVAL = 30          # secondes par defaut d'une verification par sondage
STABLE_WAIT = 4                # secondes : le fichier doit garder sa taille
IGNORE_EXT = (".crdownload", ".part", ".tmp", ".partial", ".!ut", ".download", ".opdownload")

ACTION_TYPES = ["deplacer", "copier", "renommer", "grimoire", "archiveur", "executer",
                "decompresser", "supprimer", "notifier"]
ACTION_LABELS = {
    "deplacer": "Déplacer vers…", "copier": "Copier (double) vers…", "renommer": "Renommer (modèle)",
    "grimoire": "Envoyer au Grimoire", "archiveur": "Envoyer à l'Archiveur", "executer": "Exécuter une commande",
    "decompresser": "Décompresser (zip)", "supprimer": "Supprimer (corbeille)", "notifier": "Notifier",
}

# liste blanche des actions acceptees dans un .padawan (commandes a distance)
REMOTE_ACTIONS = ["grimoire_ajouter", "archiver_lien", "lancer_raccourci_arsenal",
                  "lancer_programme_autorise", "copier_vers", "notifier"]
REMOTE_LABELS = {
    "grimoire_ajouter": "Ajouter au Grimoire (lien ou texte + sujet)",
    "archiver_lien": "Archiver un lien (Archiveur)",
    "lancer_raccourci_arsenal": "Lancer un raccourci d'Arsenal (par id)",
    "lancer_programme_autorise": "Lancer un programme autorisé (par alias)",
    "copier_vers": "Copier vers une destination pré-autorisée (par nom)",
    "notifier": "Notification Windows",
}


DEFAULT_PREFIXE_LANCEMENT = "::run "


def default_config() -> Dict[str, Any]:
    dl = known_folder_downloads()
    cmd_dir = os.path.join(Paths.data, "commandes")
    return {
        "version": 1,
        "theme": "norton",
        "font_delta": 0,
        "pause_globale": False,
        "notifications": True,
        "mode_avance": False,   # commandes a distance + boites SQL (cache par defaut)
        "limites": {
            "max_par_passe": 50,
            "priorite_basse": True,
            "pause_batterie_faible": False,
            "seuil_batterie": 20,
            "pause_cpu_occupe": False,
            "seuil_cpu": 85,
        },
        "remote": {
            "actif": False,
            "lire_voix_haute": False,
            "voix": "auto",
            "expire_sec": DEFAULT_EXPIRE_SEC,
            "dossier_commandes": cmd_dir,
            "programmes_autorises": {
                "paint": {"target": "mspaint.exe", "args": "", "cwd": ""},
                "notepad": {"target": "notepad.exe", "args": "", "cwd": ""},
                "calc": {"target": "calc.exe", "args": "", "cwd": ""},
                "pbrush": {"target": "mspaint.exe", "args": "", "cwd": ""},
                "pbrush.exe": {"target": "mspaint.exe", "args": "", "cwd": ""},
                "mspaint": {"target": "mspaint.exe", "args": "", "cwd": ""},
            },
            # ADMIN SEULEMENT : message signe avec params.admin=true (mot de passe web OK)
            # alias -> {"type": "exe"|"cmd"|"ps1", "target": "...", "args": "", "cwd": ""}
            "commandes_nommees": {
                # Chemins relatifs au dossier de donnees Facteur (scripts/ copie a l'install).
                # Adapter apres installation si XAMPP / backup sont ailleurs.
                "apache": {"type": "cmd", "target": os.path.join(Paths.data, "scripts", "restart_xampp.cmd"),
                           "args": "", "cwd": r"C:\xampp", "libelle": "Redemarrer Apache/MySQL"},
                "backup": {"type": "cmd", "target": os.path.join(Paths.data, "scripts", "backup_web.exemple.cmd"),
                           "args": "", "cwd": Paths.data, "libelle": "Backup web (a configurer)"},
                "verrouiller": {"type": "exe", "target": "rundll32.exe",
                                "args": "user32.dll,LockWorkStation", "cwd": "", "libelle": "Verrouiller le PC"},
                "site": {"type": "exe", "target": "https://marcsevigny.ca",
                         "args": "", "cwd": "", "libelle": "Ouvrir le site"},
            },
            "prefixe_lancement": DEFAULT_PREFIXE_LANCEMENT,
            "destinations_autorisees": {},   # nom  -> dossier
            "confirmer": [],                 # actions distantes qui demandent confirmation a l'ecran
            "actions_permises": list(REMOTE_ACTIONS),
        },
        "dossiers": [
            {"id": uuid.uuid4().hex[:8], "chemin": dl, "recursif": False, "actif": True,
             "intervalle": 15, "evenementiel": True, "note": "Téléchargements (boîte aux lettres)"},
        ],
        "boites_sql": [],  # sources pont PHP (aucun mot de passe MySQL sur le PC)
        "regles": default_rules(dl, cmd_dir),
    }


def _rule(nom: str, actif: bool, **kw) -> Dict[str, Any]:
    r = {
        "id": uuid.uuid4().hex[:8], "nom": nom, "actif": actif,
        "dossiers": [],            # ids de dossiers surveilles ; vide = tous
        "recursif": None,          # None = suit le dossier
        "masque": "*",             # glob sur le nom
        "extensions": [],          # ex. ["pdf","jpg"] (sans point)
        "regex": "",               # regex sur le nom
        "taille_min": 0, "taille_max": 0,       # octets ; 0 = pas de limite
        "age_min": 0, "age_max": 0,             # secondes ; 0 = pas de limite
        "intervalle": 0,           # secondes ; 0 = suit le dossier
        "evenementiel": True,
        "horaire": {"actif": False, "debut": "08:00", "fin": "22:00", "jours": [0, 1, 2, 3, 4, 5, 6]},
        "max_par_passe": 0,        # 0 = suit la limite globale
        "actions": [],
        "confirmer": False,
        "note": "",
    }
    r.update(kw)
    return r


def default_rules(dl: str, cmd_dir: str) -> List[Dict[str, Any]]:
    rules: List[Dict[str, Any]] = []
    # 1) commandes signees : la SEULE active par defaut
    rules.append(_rule(
        "Commandes à distance signées (.padawan)", False,
        masque="*.padawan", evenementiel=True, intervalle=10,
        actions=[{"type": "commande_signee"}],
        note="Vérifie la signature HMAC, l'expiration et l'anti-rejeu, puis exécute seulement "
             "les actions de la liste blanche. Les fichiers refusés vont en quarantaine.",
    ))
    # 2) exemples desactives
    rules.append(_rule(
        "PDF de Téléchargements → dossier choisi (copie)", False,
        extensions=["pdf"], intervalle=60,
        actions=[{"type": "copier", "dest": os.path.join(os.path.expanduser("~"), "Documents", "PDF")}],
        note="Exemple : garde une copie des PDF téléchargés.",
    ))
    rules.append(_rule(
        "Vidéos → Archiveur", False,
        extensions=["mp4", "mkv", "webm", "mov"], intervalle=120,
        actions=[{"type": "archiveur"}],
        note="Exemple : envoie les vidéos déposées à l'Archiveur.",
    ))
    rules.append(_rule(
        "Trier Téléchargements par type", False,
        masque="*", intervalle=300,
        actions=[{"type": "deplacer", "dest": "", "par_type": True}],
        note="Modèle : range chaque fichier dans un sous-dossier selon son type (désactivé).",
    ))
    return rules


# modeles de regles prets (bibliotheque) — toujours desactives a l'insertion
def rule_templates() -> List[Dict[str, Any]]:
    docs = os.path.join(os.path.expanduser("~"), "Documents")
    return [
        _rule("Trier Téléchargements par type", False, masque="*", intervalle=300,
              actions=[{"type": "deplacer", "dest": "", "par_type": True}],
              note="Range chaque fichier dans un sous-dossier (Images, Documents, Vidéos, Archives…)."),
        _rule("Archiver les vieux fichiers (> 30 jours)", False, masque="*", age_min=30 * 86400, intervalle=3600,
              actions=[{"type": "deplacer", "dest": os.path.join(docs, "Vieux")}],
              note="Déplace les fichiers âgés vers un dossier d'archive."),
        _rule("Copier les créations vers FTP_HOME", False, extensions=["html", "php", "py", "md"], intervalle=60,
              actions=[{"type": "copier", "dest": os.path.join(FTP_HOME, "DESCRIPTION")}],
              note="Double des fichiers d'éditeur aux bons endroits de FTP_HOME."),
        _rule("Lancer un .bat déposé puis le ranger", False, extensions=["bat"], intervalle=30,
              actions=[{"type": "executer", "shell": "cmd", "ligne": '"{fichier}"', "admin": False,
                        "visible": True, "timeout": 120, "capturer": True}],
              confirmer=True,
              note="Exécute un .bat déposé (confirmation), puis le fichier part dans _Traités."),
        _rule("Convertir des vidéos avec ffmpeg", False, extensions=["mkv", "avi", "mov"], intervalle=300,
              actions=[{"type": "executer", "shell": "cmd",
                        "ligne": 'ffmpeg -y -i "{fichier}" "{dossier}\\{nom}.mp4"', "admin": False,
                        "visible": False, "timeout": 1800, "capturer": True}],
              note="Convertit en MP4 H.264 (ffmpeg requis dans le PATH)."),
    ]


class Config:
    def __init__(self) -> None:
        self.data: Dict[str, Any] = {}

    def load(self) -> "Config":
        os.makedirs(Paths.data, exist_ok=True)
        try:
            with open(Paths.config(), "r", encoding="utf-8") as f:
                self.data = json.load(f)
            self._merge_defaults()
        except FileNotFoundError:
            self.data = default_config()
            self.save()
            jlog("INFO", "config", f"config créée : {Paths.config()}")
        except Exception as ex:
            bad = Paths.config() + f".illisible_{stamp()}"
            try:
                os.replace(Paths.config(), bad)
            except OSError:
                pass
            self.data = default_config()
            self.save()
            jlog("ERREUR", "config", f"config illisible ({ex}), copie gardée, défauts rechargés")
        return self

    def _merge_defaults(self) -> None:
        d = default_config()
        for k, v in d.items():
            if k not in self.data:
                self.data[k] = v
        for k, v in d["limites"].items():
            self.data["limites"].setdefault(k, v)
        for k, v in d["remote"].items():
            self.data["remote"].setdefault(k, v)
        if not self.data["remote"].get("programmes_autorises"):
            self.data["remote"]["programmes_autorises"] = dict(d["remote"]["programmes_autorises"])
        _pa = self.data["remote"]["programmes_autorises"]
        for _k in ("pbrush", "pbrush.exe", "mspaint"):
            if _k not in _pa:
                _pa[_k] = {"target": "mspaint.exe", "args": "", "cwd": ""}
        if not isinstance(self.data["remote"].get("commandes_nommees"), dict):
            self.data["remote"]["commandes_nommees"] = {}
        _defs = (d.get("remote") or {}).get("commandes_nommees") or {}
        _noms = self.data["remote"]["commandes_nommees"]
        for _k, _v in _defs.items():
            if _k not in _noms:
                _noms[_k] = dict(_v)

    def save(self) -> None:
        os.makedirs(Paths.data, exist_ok=True)
        tmp = Paths.config() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, Paths.config())

    # raccourcis
    def folders(self) -> List[Dict[str, Any]]:
        return self.data["dossiers"]

    def rules(self) -> List[Dict[str, Any]]:
        return self.data["regles"]

    def folder_by_id(self, fid: str) -> Optional[Dict[str, Any]]:
        return next((f for f in self.folders() if f["id"] == fid), None)

    def boites(self) -> List[Dict[str, Any]]:
        self.data.setdefault("boites_sql", [])
        return self.data["boites_sql"]

    def boite_by_id(self, bid: str) -> Optional[Dict[str, Any]]:
        return next((b for b in self.boites() if b["id"] == bid), None)


# ================================================================ anti-rejeu / deja-vu
class SeenStore:
    def __init__(self) -> None:
        self.ids: Dict[str, int] = {}       # id de commande -> ts
        self.hashes: Dict[str, int] = {}    # empreinte de fichier -> ts
        self.lock = threading.Lock()

    def load(self) -> "SeenStore":
        try:
            with open(Paths.seen(), "r", encoding="utf-8") as f:
                d = json.load(f)
            self.ids = d.get("ids", {})
            self.hashes = d.get("hashes", {})
        except Exception:
            pass
        return self

    def save(self) -> None:
        with self.lock:
            for store in (self.ids, self.hashes):
                if len(store) > SEEN_KEEP:
                    for k in sorted(store, key=lambda k: store[k])[:len(store) - SEEN_KEEP]:
                        store.pop(k, None)
            d = {"ids": self.ids, "hashes": self.hashes}
        try:
            tmp = Paths.seen() + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(d, f)
            os.replace(tmp, Paths.seen())
        except OSError:
            pass

    def seen_id(self, cid: str) -> bool:
        with self.lock:
            return cid in self.ids

    def mark_id(self, cid: str) -> None:
        with self.lock:
            self.ids[cid] = now_ts()
        self.save()

    def seen_hash(self, h: str) -> bool:
        with self.lock:
            return h in self.hashes

    def mark_hash(self, h: str) -> None:
        with self.lock:
            self.hashes[h] = now_ts()
        self.save()


SEEN = SeenStore()


# ================================================================ corbeille (suppression sure)
def to_recycle_bin(path: str) -> bool:
    if not IS_WIN:
        try:
            os.remove(path)
            return True
        except OSError:
            return False
    try:
        import ctypes.wintypes as wt  # noqa

        class SHFILEOPSTRUCTW(ctypes.Structure):
            _fields_ = [("hwnd", ctypes.c_void_p), ("wFunc", ctypes.c_uint),
                        ("pFrom", ctypes.c_wchar_p), ("pTo", ctypes.c_wchar_p),
                        ("fFlags", ctypes.c_uint16), ("fAnyOperationsAborted", ctypes.c_int),
                        ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", ctypes.c_wchar_p)]
        FO_DELETE = 3
        FOF_ALLOWUNDO = 0x40
        FOF_NOCONFIRMATION = 0x10
        FOF_SILENT = 0x04
        op = SHFILEOPSTRUCTW()
        op.wFunc = FO_DELETE
        op.pFrom = os.path.abspath(path) + "\x00\x00"
        op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT
        return ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op)) == 0
    except Exception as ex:
        jlog("ERREUR", "regle", f"corbeille {path} : {ex}")
        return False


# ================================================================ notifications Windows
def notify(title: str, msg: str, cfg: Optional[Config] = None) -> None:
    if cfg is not None and not cfg.data.get("notifications", True):
        return
    try:
        from plyer import notification  # type: ignore
        notification.notify(title=title, message=msg, app_name="Facteur", timeout=6)
        return
    except Exception:
        pass
    # repli : notification via l'icone tray de Facteur si presente (sinon silencieux)
    try:
        ico = getattr(notify, "_tray_icon", None)
        if ico is not None:
            ico.notify(msg, title)
    except Exception:
        pass


# ================================================================ expansion des variables de commande locale
VAR_RE = re.compile(r"\{(fichier|nom|ext|dossier|date|nom_ext)\}", re.IGNORECASE)


def expand_vars(text: str, path: str) -> str:
    d = os.path.dirname(path)
    base = os.path.basename(path)
    nom, ext = os.path.splitext(base)
    vals = {"fichier": path, "nom": nom, "ext": ext.lstrip("."), "dossier": d,
            "nom_ext": base, "date": dt.date.today().isoformat()}
    return VAR_RE.sub(lambda m: vals.get(m.group(1).lower(), m.group(0)), text or "")


# ================================================================ charge systeme (batterie / CPU)
def battery_percent() -> Optional[Tuple[int, bool]]:
    """(pourcentage, sur_secteur) ou None si pas de batterie."""
    if not IS_WIN:
        return None
    try:
        class SPS(ctypes.Structure):
            _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte),
                        ("BatteryLifePercent", ctypes.c_ubyte), ("SystemStatusFlag", ctypes.c_ubyte),
                        ("BatteryLifeTime", ctypes.c_ulong), ("BatteryFullLifeTime", ctypes.c_ulong)]
        s = SPS()
        if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(s)):
            return None
        if s.BatteryFlag == 128 or s.BatteryLifePercent == 255:
            return None
        return int(s.BatteryLifePercent), s.ACLineStatus == 1
    except Exception:
        return None


class CpuMeter:
    def __init__(self) -> None:
        self.prev: Optional[Tuple[int, int, int]] = None
        self.value = 0.0

    def sample(self) -> float:
        if not IS_WIN:
            return 0.0
        try:
            FT = ctypes.c_ulonglong
            idle, kern, user = FT(), FT(), FT()
            ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kern), ctypes.byref(user))
            cur = (idle.value, kern.value, user.value)
            if self.prev:
                di = cur[0] - self.prev[0]
                tot = (cur[1] - self.prev[1]) + (cur[2] - self.prev[2])
                if tot > 0:
                    self.value = max(0.0, min(100.0, 100.0 * (tot - di) / tot))
            self.prev = cur
        except Exception:
            pass
        return self.value


# ================================================================ regles : correspondance
TYPE_FOLDERS = {
    "Images": ["jpg", "jpeg", "png", "gif", "webp", "bmp", "svg", "heic", "ico", "tif", "tiff"],
    "Vidéos": ["mp4", "mkv", "webm", "mov", "avi", "wmv", "flv", "m4v"],
    "Audio": ["mp3", "wav", "flac", "ogg", "m4a", "aac", "opus"],
    "Documents": ["pdf", "doc", "docx", "odt", "rtf", "txt", "md", "xls", "xlsx", "ods", "csv", "ppt", "pptx", "epub"],
    "Archives": ["zip", "7z", "rar", "tar", "gz", "bz2", "xz"],
    "Programmes": ["exe", "msi", "bat", "cmd", "ps1", "py", "jar"],
    "Web": ["html", "htm", "php", "js", "css", "json", "xml"],
}


def type_folder(ext: str) -> str:
    e = ext.lower().lstrip(".")
    for k, v in TYPE_FOLDERS.items():
        if e in v:
            return k
    return "Autres"


def norm_exts(v: Any) -> List[str]:
    if isinstance(v, str):
        v = re.split(r"[,;\s]+", v)
    return [x.strip().lower().lstrip(".") for x in (v or []) if x and x.strip()]


def schedule_ok(rule: Dict[str, Any], now: Optional[dt.datetime] = None) -> bool:
    h = rule.get("horaire") or {}
    if not h.get("actif"):
        return True
    now = now or dt.datetime.now()
    jours = h.get("jours", list(range(7)))
    if jours and now.weekday() not in jours:
        return False
    try:
        a = dt.datetime.strptime(h.get("debut", "00:00"), "%H:%M").time()
        b = dt.datetime.strptime(h.get("fin", "23:59"), "%H:%M").time()
    except ValueError:
        return True
    t = now.time()
    return (a <= t <= b) if a <= b else (t >= a or t <= b)   # plage qui passe minuit


def match_rule(rule: Dict[str, Any], path: str, folder_id: str = "", st: Optional[os.stat_result] = None
               ) -> Tuple[bool, List[str]]:
    """Retourne (correspond, explications) pour le bouton Tester."""
    why: List[str] = []
    ok = True
    name = os.path.basename(path)
    if rule.get("dossiers") and folder_id and folder_id not in rule["dossiers"]:
        why.append("✗ dossier source non retenu par la règle")
        ok = False
    masks = [m.strip() for m in re.split(r"[;|]", rule.get("masque") or "*") if m.strip()] or ["*"]
    if any(fnmatch.fnmatch(name.lower(), m.lower()) for m in masks):
        why.append(f"✓ masque {';'.join(masks)}")
    else:
        why.append(f"✗ masque {';'.join(masks)}")
        ok = False
    exts = norm_exts(rule.get("extensions"))
    ext = os.path.splitext(name)[1].lower().lstrip(".")
    if exts:
        if ext in exts:
            why.append(f"✓ extension .{ext}")
        else:
            why.append(f"✗ extension .{ext} (attendu : {', '.join(exts)})")
            ok = False
    rx = rule.get("regex") or ""
    if rx:
        try:
            if re.search(rx, name, re.IGNORECASE):
                why.append(f"✓ regex {rx}")
            else:
                why.append(f"✗ regex {rx}")
                ok = False
        except re.error as ex:
            why.append(f"✗ regex invalide : {ex}")
            ok = False
    try:
        st = st or os.stat(path)
    except OSError:
        return False, why + ["✗ fichier introuvable"]
    size = st.st_size
    if rule.get("taille_min") and size < int(rule["taille_min"]):
        why.append(f"✗ taille {size} o < min {rule['taille_min']}")
        ok = False
    if rule.get("taille_max") and size > int(rule["taille_max"]):
        why.append(f"✗ taille {size} o > max {rule['taille_max']}")
        ok = False
    age = time.time() - st.st_mtime
    if rule.get("age_min") and age < int(rule["age_min"]):
        why.append(f"✗ âge {int(age)} s < min {rule['age_min']} s")
        ok = False
    if rule.get("age_max") and age > int(rule["age_max"]):
        why.append(f"✗ âge {int(age)} s > max {rule['age_max']} s")
        ok = False
    if ok:
        why.append(f"✓ taille {size} o, âge {int(age)} s")
    return ok, why


# ================================================================ actions
class ActionError(Exception):
    pass


_ARSENAL_MOD = None


def arsenal_module():
    """Charge arsenal1.py comme module (pour lire arsenal.json et calculer le lancement exactement comme Arsenal)."""
    global _ARSENAL_MOD
    if _ARSENAL_MOD is None:
        p = find_script("arsenal1.py")
        if not p:
            raise ActionError("arsenal1.py introuvable")
        import importlib.util
        spec = importlib.util.spec_from_file_location("arsenal1_facteur", p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore
        _ARSENAL_MOD = mod
    return _ARSENAL_MOD


def arsenal_entries() -> List[Dict[str, Any]]:
    p = os.path.join(os.path.dirname(find_script("arsenal1.py") or BASE), "arsenal.json")
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f).get("entries", [])
    except Exception:
        return []


def shell_execute(file: str, params: str = "", cwd: str = "", verb: str = "open", show: int = 1) -> None:
    if not IS_WIN:
        subprocess.Popen([file] + ([params] if params else []), cwd=cwd or None)
        return
    r = ctypes.windll.shell32.ShellExecuteW(None, verb, file, params or None, cwd or None, show)
    if int(r) <= 32:
        raise ActionError(f"ShellExecute a échoué (code {int(r)})")


def py_cli(script: str, args: List[str], timeout: float = 180) -> Tuple[int, str]:
    p = run_hidden([find_python(), script] + args, timeout=timeout, cwd=os.path.dirname(script))
    return p.returncode, decode_bytes(p.stdout or b"").strip()


def grimoire_add(contenu: str, sujet: str = "", titre: str = "", note: str = "") -> str:
    g = find_script("grimoire1.py")
    if not g:
        raise ActionError("grimoire1.py introuvable")
    args = ["--ajouter", contenu]
    if sujet:
        args += ["--sujet", sujet]
    if titre:
        args += ["--titre", titre]
    if note:
        args += ["--note", note]
    code, out = py_cli(g, args)
    if code != 0:
        raise ActionError(f"Grimoire code {code} : {out[-400:]}")
    return out[-400:] or "ajouté"


def archiveur_url(url: str) -> str:
    a = find_script("archiveur5.py", "archiveur4.py", "archiveur3.py")
    if not a:
        raise ActionError("archiveur introuvable")
    popen_detached([find_python(), a, "--url", url], cwd=os.path.dirname(a))
    return f"Archiveur lancé pour {url}"


def unzip_safe(src: str, dest: str) -> int:
    n = 0
    dest_abs = os.path.abspath(dest)
    with zipfile.ZipFile(src) as z:
        for info in z.infolist():
            target = os.path.abspath(os.path.join(dest_abs, info.filename))
            if not (target == dest_abs or target.startswith(dest_abs + os.sep)):
                raise ActionError(f"chemin dangereux dans l'archive : {info.filename}")
            if info.is_dir():
                os.makedirs(target, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with z.open(info) as s, open(target, "wb") as d:
                shutil.copyfileobj(s, d)
            n += 1
    return n


CMD_UNSAFE = re.compile(r'[%^&|<>!"]')


def run_local_command(a: Dict[str, Any], path: str, low: bool) -> str:
    """Commande CMD/PowerShell ecrite par Marc dans une regle LOCALE (jamais depuis un .padawan)."""
    shell = (a.get("shell") or "cmd").lower()
    line = a.get("ligne") or ""
    if not line.strip():
        raise ActionError("ligne de commande vide")
    timeout = max(1, int(a.get("timeout") or 300))
    env = dict(os.environ)
    d = os.path.dirname(path)
    base = os.path.basename(path)
    nom, ext = os.path.splitext(base)
    vals = {"FICHIER": path, "NOM": nom, "EXT": ext.lstrip("."), "DOSSIER": d, "NOM_EXT": base,
            "DATE": dt.date.today().isoformat()}
    for k, v in vals.items():
        env["FACTEUR_" + k] = v
    if shell == "powershell":
        # variables passees par l'environnement : aucun nom de fichier n'est interprete par PowerShell
        expanded = VAR_RE.sub(lambda m: "$env:FACTEUR_" + m.group(1).upper(), line)
        argv = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", expanded]
        disp = expanded
    else:
        for k, v in vals.items():
            if CMD_UNSAFE.search(v):
                raise ActionError(f"nom de fichier avec caractères spéciaux refusé pour cmd : {v}")
        expanded = expand_vars(line, path)
        argv = ["cmd.exe", "/d", "/s", "/c", expanded]
        disp = expanded
    if a.get("admin"):
        if shell == "powershell":
            params = "-NoProfile -ExecutionPolicy Bypass -Command " + subprocess.list2cmdline([expanded])
            shell_execute("powershell.exe", params, d, "runas", 1 if a.get("visible") else 0)
        else:
            shell_execute("cmd.exe", f'/d /s /c "{expanded}"', d, "runas", 1 if a.get("visible") else 0)
        return f"lancé en admin (UAC) : {disp}"
    if a.get("visible"):
        if shell == "powershell":
            argv = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-NoExit", "-Command", expanded]
        else:
            argv = ["cmd.exe", "/d", "/s", "/k", expanded]
        popen_detached(argv, low=low, visible=True, cwd=d, env=env)
        return f"lancé (fenêtre visible) : {disp}"
    try:
        p = run_hidden(argv, timeout=timeout, low=low, cwd=d, env=env)
    except subprocess.TimeoutExpired:
        raise ActionError(f"délai dépassé ({timeout} s) : {disp}")
    out = decode_bytes(p.stdout or b"").strip()
    if a.get("capturer", True) and out:
        jlog("INFO", "sortie", out[-2000:])
    if p.returncode != 0:
        raise ActionError(f"code {p.returncode} : {disp}")
    return f"OK (code 0) : {disp}"



def apply_action(a: Dict[str, Any], path: str, cfg: Config, dry: bool = False) -> Tuple[str, Optional[str]]:
    """Applique une action locale. Retourne (message, nouveau_chemin_si_deplace)."""
    typ = a.get("type") or ""
    if typ == "commande_signee":
        return handle_signed_command(path, cfg, dry=dry), None
    if typ == "notifier":
        msg = expand_vars(a.get("message") or "Fichier traité : {nom_ext}", path)
        if dry:
            return f"[simulé] notifier « {msg} »", None
        notify("Facteur", msg, cfg)
        return f"notifié : {msg}", None
    if typ == "renommer":
        modele = a.get("modele") or "{nom}_{date}.{ext}"
        new_name = safe_name(expand_vars(modele, path))
        dest = unique_path(os.path.join(os.path.dirname(path), new_name))
        if dry:
            return f"[simulé] renommer → {dest}", dest
        os.rename(path, dest)
        return f"renommé → {dest}", dest
    if typ in ("deplacer", "copier"):
        dest_dir = a.get("dest") or ""
        if a.get("par_type"):
            dest_dir = os.path.join(dest_dir or os.path.dirname(path),
                                    type_folder(os.path.splitext(path)[1]))
        if not dest_dir:
            raise ActionError("destination manquante")
        dest_dir = expand_vars(dest_dir, path)
        dest = unique_path(os.path.join(dest_dir, os.path.basename(path)))
        if dry:
            return f"[simulé] {typ} → {dest}", (dest if typ == "deplacer" else None)
        os.makedirs(dest_dir, exist_ok=True)
        if typ == "deplacer":
            shutil.move(path, dest)
            return f"déplacé → {dest}", dest
        shutil.copy2(path, dest)
        return f"copié → {dest}", None
    if typ == "grimoire":
        sujet = a.get("sujet") or ""
        titre = a.get("titre") or ""
        note = a.get("note") or ""
        if dry:
            return f"[simulé] Grimoire ← {path} (sujet={sujet or 'À classer'})", None
        out = grimoire_add(path, sujet=sujet, titre=titre, note=note)
        return f"Grimoire : {out}", None
    if typ == "archiveur":
        url = a.get("url") or ""
        if not url and path.lower().endswith((".url", ".txt", ".padawan")):
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    for ln in f:
                        if ln.strip().startswith("http"):
                            url = ln.strip(); break
            except OSError:
                pass
        if not url:
            # fichier video local : on ouvre l'Archiveur avec le fichier (pas d'URL)
            if dry:
                return f"[simulé] Archiveur ← {path}", None
            ar = find_script("archiveur5.py", "archiveur4.py")
            if not ar:
                raise ActionError("archiveur introuvable")
            popen_detached([find_pythonw(), ar], cwd=os.path.dirname(ar))
            return "Archiveur ouvert (dépose manuelle du fichier)", None
        if dry:
            return f"[simulé] Archiveur ← {url}", None
        return archiveur_url(url), None
    if typ == "decompresser":
        dest = a.get("dest") or os.path.join(os.path.dirname(path), os.path.splitext(os.path.basename(path))[0])
        dest = expand_vars(dest, path)
        if dry:
            return f"[simulé] décompresser → {dest}", None
        os.makedirs(dest, exist_ok=True)
        n = unzip_safe(path, dest)
        return f"décompressé {n} fichier(s) → {dest}", None
    if typ == "supprimer":
        if dry:
            return f"[simulé] corbeille ← {path}", None
        if not to_recycle_bin(path):
            raise ActionError("échec corbeille")
        return "envoyé à la corbeille", None
    if typ == "executer":
        if dry:
            return f"[simulé] exécuter ({a.get('shell','cmd')}) : {expand_vars(a.get('ligne') or '', path)}", None
        return run_local_command(a, path, low=cfg.data["limites"].get("priorite_basse", True)), None
    if typ == "executer_programme":
        # alias local (pas distant)
        alias = a.get("alias") or ""
        prog = (cfg.data.get("remote") or {}).get("programmes_autorises", {}).get(alias)
        if not prog:
            raise ActionError(f"programme autorisé inconnu : {alias}")
        if dry:
            return f"[simulé] lancer_programme_autorise {alias}", None
        return launch_authorized(prog, low=cfg.data["limites"].get("priorite_basse", True)), None
    raise ActionError(f"action inconnue : {typ}")


def launch_authorized(prog: Dict[str, Any], low: bool = True) -> str:
    target = os.path.expandvars(prog.get("target") or "")
    args = prog.get("args") or ""
    cwd = os.path.expandvars(prog.get("cwd") or "")
    if not target:
        raise ActionError("programme autorisé sans target")
    # jamais une commande shell libre : target = chemin ou exe connu, args = chaine d'arguments
    # construction propre
    if args:
        # ShellExecute pour respecter les guillemets deja presents
        if IS_WIN:
            shell_execute(target, args, cwd, "open", 1)
            return f"lancé (alias) : {target} {args}"
        argv = [target] + shlex_split(args)
    else:
        argv = [target]
        if IS_WIN:
            shell_execute(target, "", cwd, "open", 1)
            return f"lancé (alias) : {target}"
    popen_detached(argv, low=low, cwd=cwd or None)
    return f"lancé (alias) : {target}"


def shlex_split(s: str) -> List[str]:
    import shlex
    try:
        return shlex.split(s, posix=not IS_WIN)
    except ValueError:
        return [s]


# ================================================================ commandes a distance signees
def quarantine(path: str, reason: str) -> str:
    os.makedirs(Paths.quarantaine(), exist_ok=True)
    dest = unique_path(os.path.join(Paths.quarantaine(), f"{stamp()}_{safe_name(os.path.basename(path))}"))
    try:
        shutil.move(path, dest)
    except OSError:
        try:
            shutil.copy2(path, dest)
            os.remove(path)
        except OSError as ex:
            jlog("ERREUR", "quarantaine", f"{path} : {ex}")
            return ""
    meta = dest + ".raison.txt"
    try:
        with open(meta, "w", encoding="utf-8") as f:
            f.write(reason + "\n")
    except OSError:
        pass
    jlog("REFUS", "commande", f"{os.path.basename(path)} → quarantaine ({reason})")
    notify("Facteur — commande refusée", reason[:200])
    return dest


def verify_command(cmd: Dict[str, Any], key: bytes, expire_sec: int) -> Tuple[bool, str]:
    if not isinstance(cmd, dict):
        return False, "JSON invalide"
    if cmd.get("v") != SIG_VERSION:
        return False, f"version non supportée ({cmd.get('v')})"
    cid = str(cmd.get("id") or "")
    if not ID_RE.match(cid):
        return False, "id invalide"
    if SEEN.seen_id(cid):
        return False, "commande déjà vue (anti-rejeu)"
    for f in ("ts", "expire", "action", "sig"):
        if f not in cmd:
            return False, f"champ manquant : {f}"
    try:
        ts, exp = int(cmd["ts"]), int(cmd["expire"])
    except (TypeError, ValueError):
        return False, "ts/expire non numériques"
    now = now_ts()
    if exp < now:
        return False, f"expirée (expire={exp}, maintenant={now})"
    if ts > now + 120:
        return False, "horodatage dans le futur"
    if exp - ts > max(expire_sec, DEFAULT_EXPIRE_SEC) + 60:
        return False, "fenêtre d'expiration trop large"
    if not isinstance(cmd.get("params"), dict):
        return False, "params doit être un objet"
    sig = str(cmd.get("sig") or "").lower()
    if not re.fullmatch(r"[0-9a-f]{64}", sig):
        return False, "signature absente ou mal formée"
    expect = sign_command(cmd, key)
    if not hmac.compare_digest(sig, expect):
        return False, "signature invalide"
    return True, "ok"


def handle_signed_command(path: str, cfg: Config, dry: bool = False) -> str:
    rem = cfg.data.get("remote") or {}
    if not rem.get("actif", True):
        quarantine(path, "commandes à distance désactivées")
        return "refusé : commandes à distance désactivées"
    try:
        with open(path, "r", encoding="utf-8") as f:
            cmd = json.load(f)
    except Exception as ex:
        quarantine(path, f"JSON illisible : {ex}")
        return f"refusé : JSON illisible ({ex})"
    try:
        key = KeyStore().load()
    except Exception as ex:
        quarantine(path, f"clé inaccessible : {ex}")
        return f"refusé : clé inaccessible"
    ok, why = verify_command(cmd, key, int(rem.get("expire_sec") or DEFAULT_EXPIRE_SEC))
    if not ok:
        quarantine(path, why)
        return f"refusé : {why}"
    action = str(cmd.get("action") or "")
    if action not in rem.get("actions_permises", REMOTE_ACTIONS):
        quarantine(path, f"action hors liste blanche : {action}")
        return f"refusé : action hors liste blanche ({action})"
    if dry:
        return f"[simulé] commande {action} id={cmd.get('id')} params={cmd.get('params')}"
    # confirmation optionnelle
    if action in (rem.get("confirmer") or []):
        if not ask_confirm_action(action, cmd.get("params") or {}):
            quarantine(path, "refusée par confirmation utilisateur")
            return "refusé par confirmation"
    try:
        msg = execute_remote(action, cmd.get("params") or {}, cfg)
    except Exception as ex:
        quarantine(path, f"échec d'exécution : {ex}")
        return f"échec : {ex}"
    SEEN.mark_id(str(cmd["id"]))
    jlog("OK", "commande", f"{action} id={cmd['id']} — {msg}")
    notify("Facteur — commande OK", f"{action} : {msg}"[:200], cfg)
    return f"OK {action} — {msg}"


_confirm_cb: Optional[Callable[[str, Dict[str, Any]], bool]] = None


def ask_confirm_action(action: str, params: Dict[str, Any]) -> bool:
    if _confirm_cb:
        try:
            return bool(_confirm_cb(action, params))
        except Exception:
            return False
    # sans interface : on refuse les actions qui demandent confirmation
    return False


def run_named_command(c: Dict[str, Any], low: bool = True) -> str:
    """Commande nommee (admin) : cible precise definie LOCALEMENT, jamais de texte venant du web."""
    typ = str(c.get("type") or "exe").lower()
    target = os.path.expandvars(str(c.get("target") or ""))
    args = str(c.get("args") or "")
    cwd = os.path.expandvars(str(c.get("cwd") or "")) or None
    if cwd and not os.path.isdir(cwd):
        cwd = None  # dossier absent sur ce PC (ex. pas de XAMPP) : on lance sans dossier de travail
    if not target:
        raise ActionError("commande nommee sans target")
    if (os.path.isabs(target) or os.sep in target) and not os.path.exists(target):
        raise ActionError(f"introuvable sur ce PC : {target} (a configurer dans Commandes)")
    if typ == "exe":
        return launch_authorized({"target": target, "args": args, "cwd": cwd or ""}, low=low)
    if typ == "cmd":
        popen_detached(["cmd.exe", "/c", target + ((" " + args) if args else "")], low=low, cwd=cwd)
        return f"commande lancee (cmd) : {target}"
    if typ == "ps1":
        argv = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
                "-File", target] + (shlex_split(args) if args else [])
        popen_detached(argv, low=low, cwd=cwd)
        return f"script lance (ps1) : {target}"
    raise ActionError(f"type de commande nommee inconnu : {typ}")


# ================================================================ voix (TTS)
# WinRT / OneCore (fr-CA Caroline, Claude, …) en priorité ; System.Speech en secours.
_TTS_PS1 = r"""param([string]$TextFile, [string]$Voice = 'auto', [string]$Culture = '')
$ErrorActionPreference = 'Stop'
$t = [System.IO.File]::ReadAllText($TextFile, [System.Text.Encoding]::UTF8)
if ([string]::IsNullOrWhiteSpace($t)) { return }

function Pick-WinRT($all, $Voice, $Culture) {
  if ($Voice -and $Voice -ne 'auto') {
    $x = $all | Where-Object { $_.DisplayName -eq $Voice } | Select-Object -First 1
    if (-not $x) { $x = $all | Where-Object { $_.DisplayName -like ('*' + $Voice + '*') } | Select-Object -First 1 }
    if ($x) { return $x }
  }
  $c = ('' + $Culture).ToLowerInvariant()
  if ($c -eq 'fr' -or $c -eq 'fr-ca' -or $c -eq 'fr-fr' -or (-not $c -and ($Voice -eq 'auto' -or -not $Voice))) {
    $x = $all | Where-Object { $_.Language -eq 'fr-CA' } | Select-Object -First 1
    if ($x) { return $x }
    $x = $all | Where-Object { $_.Language -like 'fr*' } | Select-Object -First 1
    if ($x) { return $x }
    if ($c) { return $null }
  }
  if ($c -eq 'en' -or $c.StartsWith('en')) {
    $x = $all | Where-Object { $_.Language -like 'en*' } | Select-Object -First 1
    if ($x) { return $x }
  }
  if ($c) {
    $x = $all | Where-Object { $_.Language -eq $c -or $_.Language -like ($c + '*') } | Select-Object -First 1
    if ($x) { return $x }
  }
  return $null
}

function Speak-WinRT([string]$text, [string]$Voice, [string]$Culture) {
  Add-Type -AssemblyName System.Runtime.WindowsRuntime
  $null = [Windows.Media.SpeechSynthesis.SpeechSynthesizer,Windows.Media.SpeechSynthesis,ContentType=WindowsRuntime]
  $asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
      $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.ReturnType.Name -eq 'Task`1'
    } | Select-Object -First 1)
  function Await($WinRtTask, $ResultType) {
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    $netTask.Result
  }
  $s = [Windows.Media.SpeechSynthesis.SpeechSynthesizer]::new()
  try {
    $all = @([Windows.Media.SpeechSynthesis.SpeechSynthesizer]::AllVoices)
    $pick = Pick-WinRT $all $Voice $Culture
    if ($pick) { $s.Voice = $pick }
    $stream = Await ($s.SynthesizeTextToStreamAsync($text)) ([Windows.Media.SpeechSynthesis.SpeechSynthesisStream])
    $tmp = Join-Path $env:TEMP ('facteur_tts_' + [guid]::NewGuid().ToString() + '.wav')
    try {
      $net = [System.IO.WindowsRuntimeStreamExtensions]::AsStreamForRead($stream)
      $fs = [IO.File]::Create($tmp)
      try { $net.CopyTo($fs) } finally { $fs.Close(); if ($net) { $net.Close() } }
      Add-Type -AssemblyName System.Windows.Forms
      $p = New-Object System.Media.SoundPlayer $tmp
      $p.PlaySync()
    } finally {
      Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
    }
  } finally { $s.Dispose() }
}

function Speak-SAPI([string]$text, [string]$Voice, [string]$Culture) {
  Add-Type -AssemblyName System.Speech
  $s = New-Object System.Speech.Synthesis.SpeechSynthesizer
  try {
    $voices = @($s.GetInstalledVoices() | Where-Object { $_.Enabled })
    $pick = $null
    if ($Voice -and $Voice -ne 'auto') {
      $pick = $voices | Where-Object { $_.VoiceInfo.Name -eq $Voice } | Select-Object -First 1
      if (-not $pick) { $pick = $voices | Where-Object { $_.VoiceInfo.Name -like ('*' + $Voice + '*') } | Select-Object -First 1 }
    }
    $c = ('' + $Culture).ToLowerInvariant()
    if (-not $pick -and ($c -eq 'fr' -or $c.StartsWith('fr') -or (-not $c -and ($Voice -eq 'auto' -or -not $Voice)))) {
      $pick = $voices | Where-Object { $_.VoiceInfo.Culture.Name -eq 'fr-CA' } | Select-Object -First 1
      if (-not $pick) { $pick = $voices | Where-Object { $_.VoiceInfo.Culture.Name -like 'fr*' } | Select-Object -First 1 }
    }
    if (-not $pick -and ($c -eq 'en' -or $c.StartsWith('en'))) {
      $pick = $voices | Where-Object { $_.VoiceInfo.Culture.Name -like 'en*' } | Select-Object -First 1
    }
    if ($pick) { $s.SelectVoice($pick.VoiceInfo.Name) }
    $s.Speak($text)
  } finally { $s.Dispose() }
}

$done = $false
try { Speak-WinRT $t $Voice $Culture; $done = $true } catch { }
if (-not $done) { Speak-SAPI $t $Voice $Culture }
"""

_TTS_LIST_PS1 = r"""$ErrorActionPreference = 'SilentlyContinue'
$out = @()
try {
  Add-Type -AssemblyName System.Runtime.WindowsRuntime
  $null = [Windows.Media.SpeechSynthesis.SpeechSynthesizer,Windows.Media.SpeechSynthesis,ContentType=WindowsRuntime]
  foreach ($v in [Windows.Media.SpeechSynthesis.SpeechSynthesizer]::AllVoices) {
    $out += [pscustomobject]@{ name = [string]$v.DisplayName; lang = [string]$v.Language; engine = 'onecore' }
  }
} catch {}
try {
  Add-Type -AssemblyName System.Speech
  $s = New-Object System.Speech.Synthesis.SpeechSynthesizer
  foreach ($v in $s.GetInstalledVoices()) {
    if (-not $v.Enabled) { continue }
    $n = [string]$v.VoiceInfo.Name
    if ($out | Where-Object { $_.name -eq $n -or ($_.name + ' Desktop') -eq $n -or $_.name -eq ($n -replace ' Desktop$','') }) { continue }
    $out += [pscustomobject]@{ name = $n; lang = [string]$v.VoiceInfo.Culture.Name; engine = 'sapi' }
  }
  $s.Dispose()
} catch {}
$out | ConvertTo-Json -Compress
"""

_TTS_MAX = 300
_tts_q = None
_tts_lock = threading.Lock()
_tts_voices_cache: Optional[List[Dict[str, str]]] = None


def list_tts_voices(force: bool = False) -> List[Dict[str, str]]:
    """Voix installées (OneCore/WinRT + System.Speech). [{name, lang, engine}, ...]"""
    global _tts_voices_cache
    if _tts_voices_cache is not None and not force:
        return _tts_voices_cache
    rows: List[Dict[str, str]] = []
    if not IS_WIN:
        _tts_voices_cache = rows
        return rows
    import tempfile
    d = tempfile.mkdtemp(prefix="facteur_tts_list_")
    try:
        ps1 = os.path.join(d, "list.ps1")
        with open(ps1, "w", encoding="utf-8-sig") as fh:
            fh.write(_TTS_LIST_PS1)
        flags = 0x08000000
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", ps1],
            capture_output=True, timeout=30, creationflags=flags,
        )
        raw = (r.stdout or b"").decode("utf-8", errors="replace").strip()
        if raw:
            data = json.loads(raw)
            if isinstance(data, dict):
                data = [data]
            for it in data or []:
                n = str(it.get("name") or "").strip()
                if not n:
                    continue
                rows.append({
                    "name": n,
                    "lang": str(it.get("lang") or ""),
                    "engine": str(it.get("engine") or ""),
                })
    except Exception as ex:
        try:
            jlog("ERREUR", "voix", f"liste: {ex}")
        except Exception:
            pass
    finally:
        shutil.rmtree(d, ignore_errors=True)
    # fr-CA d'abord, puis fr-*, puis le reste
    def _key(v: Dict[str, str]):
        lang = (v.get("lang") or "").lower()
        if lang == "fr-ca":
            pri = 0
        elif lang.startswith("fr"):
            pri = 1
        else:
            pri = 2
        return (pri, lang, v.get("name") or "")
    rows.sort(key=_key)
    _tts_voices_cache = rows
    return rows


def _cfg_voix() -> str:
    try:
        p = Paths.config()
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as fh:
                return str((json.load(fh).get("remote") or {}).get("voix") or "auto")
    except Exception:
        pass
    return "auto"


def _tts_worker(q):
    import tempfile
    while True:
        item = q.get()
        try:
            if isinstance(item, tuple):
                txt = item[0]
                culture = item[1] if len(item) > 1 else ""
                voice = item[2] if len(item) > 2 else "auto"
            else:
                txt, culture, voice = item, "", "auto"
            culture = (culture or "").strip().lower()
            voice = (voice or "auto").strip() or "auto"
            d = tempfile.mkdtemp(prefix="facteur_tts_")
            ps1 = os.path.join(d, "dire.ps1"); tf = os.path.join(d, "texte.txt")
            with open(ps1, "w", encoding="utf-8-sig") as fh:
                fh.write(_TTS_PS1)
            with open(tf, "w", encoding="utf-8") as fh:
                fh.write(txt)
            flags = 0x08000000 if IS_WIN else 0
            subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                 "-File", ps1, "-TextFile", tf, "-Voice", voice, "-Culture", culture or ""],
                creationflags=flags, timeout=120,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception as ex:
            try:
                jlog("ERREUR", "voix", str(ex))
            except Exception:
                pass
        finally:
            try:
                shutil.rmtree(d, ignore_errors=True)
            except Exception:
                pass


def speak(texte: str, culture: Optional[str] = None, voice: Optional[str] = None) -> bool:
    """Lit le texte à voix haute. Auto = fr-CA puis fr-* puis défaut. File unique."""
    global _tts_q
    t = " ".join(str(texte or "").split())[:_TTS_MAX]
    if not t or not IS_WIN:
        return False
    v = (voice if voice is not None else _cfg_voix()) or "auto"
    c = (culture or "").strip().lower()
    import queue as _queue
    with _tts_lock:
        if _tts_q is None:
            _tts_q = _queue.Queue(maxsize=20)
            threading.Thread(target=_tts_worker, args=(_tts_q,), daemon=True, name="facteur-tts").start()
    try:
        _tts_q.put_nowait((t, c, v))
        return True
    except Exception:
        return False


    import queue as _queue
    with _tts_lock:
        if _tts_q is None:
            _tts_q = _queue.Queue(maxsize=20)
            threading.Thread(target=_tts_worker, args=(_tts_q,), daemon=True, name="facteur-tts").start()
    try:
        _tts_q.put_nowait(t)
        return True
    except Exception:
        return False


def _prefixe_lancer(message: str, cfg: Config, admin: bool = False) -> Optional[str]:
    """Prefixe discret : si le message commence par le prefixe configure,
    on lance UNIQUEMENT un alias de la liste blanche locale (programmes_autorises).
    Jamais de shell/CMD/PowerShell libre. Retourne le message de resultat si
    un programme est lance, sinon None (le message est traite comme une notif normale)."""
    rem = cfg.data.get("remote") or {}
    pref = str(rem.get("prefixe_lancement") or "")
    msg_n = message.replace("\u00a0", " ").strip()
    pref_n = pref.strip()
    if not pref_n or not msg_n.lower().startswith(pref_n.lower()):
        return None
    reste = msg_n[len(pref_n):].strip()
    if not reste:
        return None
    token = reste.split()[0]
    if not re.fullmatch(r"[A-Za-z0-9_.\-:]{1,40}", token):
        return None
    m_dire = re.fullmatch(r"(?i)dire(?::([a-z]{2}))?", token)
    if m_dire:
        texte = reste[len(token):].strip()
        if not texte:
            return None
        cult = (m_dire.group(1) or "").lower() or None
        if speak(texte, culture=cult):
            tag = f"dire:{cult}" if cult else "dire"
            jlog("OK", "voix", f"{tag} ({min(len(texte), _TTS_MAX)} car.)")
            return "dit"
        return None
    progs = rem.get("programmes_autorises") or {}
    prog = progs.get(token)
    if prog is None:
        for k, v in progs.items():
            if k.lower() == token.lower():
                prog = v
                break
    low = cfg.data.get("limites", {}).get("priorite_basse", True)
    if not prog:
        noms = rem.get("commandes_nommees") or {}
        c = noms.get(token) or next((v for k, v in noms.items() if k.lower() == token.lower()), None)
        if not c:
            return None
        if not admin:
            jlog("REFUS", "prefixe", f"commande nommee '{token}' sans admin -> simple notif")
            return None
        try:
            r = run_named_command(c, low=low)
            jlog("OK", "admin", f"{token} - {r}")
            return r
        except Exception as ex:
            jlog("ERREUR", "admin", f"{token} : {ex}")
            return None
    try:
        return launch_authorized(prog, low=low)
    except Exception as ex:
        jlog("ERREUR", "prefixe", str(ex))
        return None


def execute_remote(action: str, params: Dict[str, Any], cfg: Config) -> str:
    if not cfg.data.get("mode_avance"):
        return "ignor\u00e9 : mode avanc\u00e9 d\u00e9sactiv\u00e9"
    rem = cfg.data.get("remote") or {}
    if action == "notifier":
        _msg = str(params.get("message") or "Notification distante")
        # params.admin est couvert par la signature HMAC (verify_command deja passe)
        _adm = params.get("admin") in (True, 1, "1", "true")
        _lc = _prefixe_lancer(_msg, cfg, admin=_adm)
        if _lc is not None:
            notify("Facteur", "lancé", cfg)
            return _lc
        notify("Facteur", _msg, cfg)
        if rem.get("lire_voix_haute"):
            speak(_msg)
        return "notifié"
    if action == "grimoire_ajouter":
        contenu = str(params.get("contenu") or params.get("lien") or params.get("texte") or "").strip()
        if not contenu:
            raise ActionError("contenu/lien/texte manquant")
        if len(contenu) > 4000:
            raise ActionError("contenu trop long")
        sujet = str(params.get("sujet") or "")[:200]
        titre = str(params.get("titre") or "")[:200]
        note = str(params.get("note") or "")[:1000]
        return grimoire_add(contenu, sujet=sujet, titre=titre, note=note)
    if action == "archiver_lien":
        url = str(params.get("url") or params.get("lien") or "").strip()
        if not re.match(r"(?i)^https?://", url):
            raise ActionError("URL http(s) requise")
        return archiveur_url(url)
    if action == "lancer_raccourci_arsenal":
        eid = str(params.get("id") or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{6,40}", eid):
            raise ActionError("id Arsenal invalide")
        mod = arsenal_module()
        st = mod.Store().load()
        e = st.by_id(eid)
        if not e:
            raise ActionError(f"entrée Arsenal introuvable : {eid}")
        if e.get("danger") or e.get("admin"):
            raise ActionError("entrée admin/dangereuse refusée à distance")
        spec = mod.build_launch(e)
        if spec.get("kind") in ("copy", "builtin"):
            raise ActionError("type d'entrée non lançable à distance")
        if IS_WIN:
            shell_execute(spec["file"], spec.get("params") or "", spec.get("cwd") or "",
                          "open", 0)
        else:
            popen_detached([spec["file"]] + shlex_split(spec.get("params") or ""))
        return f"Arsenal « {e.get('name')} » lancé"
    if action == "lancer_programme_autorise":
        alias = str(params.get("alias") or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_]{2,40}", alias):
            raise ActionError("alias invalide")
        prog = rem.get("programmes_autorises", {}).get(alias)
        if not prog:
            raise ActionError(f"alias inconnu : {alias}")
        return launch_authorized(prog, low=cfg.data["limites"].get("priorite_basse", True))
    if action == "copier_vers":
        nom = str(params.get("destination") or params.get("dest") or "").strip()
        src = str(params.get("source") or params.get("fichier") or "").strip()
        if not nom or nom not in rem.get("destinations_autorisees", {}):
            raise ActionError(f"destination non autorisée : {nom}")
        dest_dir = rem["destinations_autorisees"][nom]
        if not src or not os.path.isfile(src):
            raise ActionError("fichier source introuvable")
        # le fichier source doit etre dans un dossier surveille (pas d'acces arbitraire)
        watched = [os.path.abspath(f["chemin"]) for f in cfg.folders()]
        src_abs = os.path.abspath(src)
        if not any(src_abs == w or src_abs.startswith(w + os.sep) for w in watched):
            raise ActionError("source hors dossiers surveillés")
        os.makedirs(dest_dir, exist_ok=True)
        dest = unique_path(os.path.join(dest_dir, os.path.basename(src_abs)))
        shutil.copy2(src_abs, dest)
        return f"copié → {dest}"
    raise ActionError(f"action inconnue : {action}")


# ================================================================ moteur
class _WDHandler(FileSystemEventHandler):  # type: ignore[misc]
    def __init__(self, engine: "Engine", fid: str) -> None:
        super().__init__()
        self.engine, self.fid = engine, fid

    def on_created(self, event):
        self._go(event)

    def on_moved(self, event):
        self._go(event)

    def on_modified(self, event):
        self._go(event)

    def _go(self, event) -> None:
        try:
            if getattr(event, "is_directory", False):
                return
            p = getattr(event, "dest_path", None) or getattr(event, "src_path", None)
            if p:
                self.engine.candidate(p, self.fid)
        except Exception:
            pass


class Engine:
    """Surveillance + ordonnancement des regles. Tourne dans un fil a part."""

    def __init__(self, cfg: Config, keys: KeyStore) -> None:
        self.cfg = cfg
        self.keys = keys
        self.lock = threading.RLock()
        self.pending: Dict[str, Dict[str, Any]] = {}
        self.known: Dict[str, Dict[str, Tuple[int, float]]] = {}
        self.next_folder: Dict[str, float] = {}
        self.next_boite: Dict[str, float] = {}
        self.next_rule: Dict[str, float] = {}
        self.last_rule: Dict[str, float] = {}
        self.stats = {"traites": 0, "refuses": 0, "erreurs": 0, "ignores": 0}
        self.recent: List[Dict[str, str]] = []
        self.stop_ev = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self.observer = None
        self.cpu = CpuMeter()
        self.ui_cb: Optional[Callable[[], None]] = None
        self._bootstrapped = False

    # ---- cycle de vie -------------------------------------------------
    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.stop_ev.clear()
        self._setup_watchers()
        self.thread = threading.Thread(target=self._loop, name="FacteurEngine", daemon=True)
        self.thread.start()
        jlog("INFO", "moteur", "démarré" + (" (watchdog)" if self.observer else " (sondage)"))

    def stop(self) -> None:
        self.stop_ev.set()
        try:
            if self.observer:
                self.observer.stop()
                self.observer.join(timeout=3)
        except Exception:
            pass
        self.observer = None
        if self.thread:
            self.thread.join(timeout=5)
        jlog("INFO", "moteur", "arrêté")

    def reload(self) -> None:
        """Reconfigure les watchers apres un changement de dossiers."""
        try:
            if self.observer:
                self.observer.stop()
                self.observer.join(timeout=2)
        except Exception:
            pass
        self.observer = None
        self._setup_watchers()

    def _setup_watchers(self) -> None:
        if not WATCHDOG:
            return
        try:
            obs = Observer()
            n = 0
            for f in self.cfg.folders():
                if not f.get("actif") or not f.get("evenementiel", True):
                    continue
                p = f.get("chemin") or ""
                if not os.path.isdir(p):
                    continue
                try:
                    obs.schedule(_WDHandler(self, f["id"]), p, recursive=bool(f.get("recursif")))
                    n += 1
                except Exception as ex:
                    jlog("ERREUR", "moteur", f"watchdog {p} : {ex}")
            if n:
                obs.start()
                self.observer = obs
        except Exception as ex:
            jlog("ERREUR", "moteur", f"watchdog indisponible : {ex}")
            self.observer = None

    # ---- boucle -------------------------------------------------------
    def _loop(self) -> None:
        while not self.stop_ev.is_set():
            try:
                self.tick()
            except Exception:
                jlog("ERREUR", "moteur", traceback.format_exc()[-800:])
            self.stop_ev.wait(1.0)

    def tick(self) -> None:
        if self.cfg.data.get("pause_globale"):
            return
        if self._load_paused():
            return
        now = time.time()
        # 1) sondage des dossiers dus
        for f in self.cfg.folders():
            if not f.get("actif"):
                continue
            iv = max(2, int(f.get("intervalle") or DEFAULT_INTERVAL))
            # en mode evenementiel, le sondage reste un filet de securite plus lent
            if f.get("evenementiel", True) and self.observer is not None:
                iv = max(iv, 120)
            if now >= self.next_folder.get(f["id"], 0):
                self.next_folder[f["id"]] = now + iv
                self._scan_folder(f)
        # 1b) boîtes SQL (pont PHP)
        self._poll_boites_sql()
        # 2) stabilite
        ready: List[Tuple[str, str]] = []
        with self.lock:
            for p, info in list(self.pending.items()):
                try:
                    s = os.stat(p)
                except OSError:
                    self.pending.pop(p, None)
                    continue
                sig = (s.st_size, s.st_mtime)
                if (info["size"], info["mtime"]) != sig:
                    info["size"], info["mtime"], info["since"] = sig[0], sig[1], now
                    continue
                if now - info["since"] >= STABLE_WAIT:
                    ready.append((p, info["fid"]))
                    self.pending.pop(p, None)
        # 3) appliquer les regles (ordonnees)
        for path, fid in ready:
            self._process(path, fid)

    def _load_paused(self) -> bool:
        lim = self.cfg.data.get("limites") or {}
        if lim.get("pause_batterie_faible"):
            bat = battery_percent()
            if bat and not bat[1] and bat[0] <= int(lim.get("seuil_batterie") or 20):
                return True
        if lim.get("pause_cpu_occupe"):
            cpu = self.cpu.sample()
            if cpu >= float(lim.get("seuil_cpu") or 85):
                return True
        else:
            self.cpu.sample()
        return False

    def candidate(self, path: str, fid: str) -> None:
        path = os.path.abspath(path)
        name = os.path.basename(path)
        if name.startswith(".") or name.startswith("~"):
            return
        ext = os.path.splitext(name)[1].lower()
        if ext in IGNORE_EXT:
            return
        # ignorer nos propres dossiers
        for skip in (Paths.traites(), Paths.quarantaine()):
            if path.startswith(os.path.abspath(skip) + os.sep):
                return
        try:
            s = os.stat(path)
            if not os.path.isfile(path):
                return
        except OSError:
            return
        with self.lock:
            self.pending[path] = {"fid": fid, "size": s.st_size, "mtime": s.st_mtime, "since": time.time()}

    def _scan_folder(self, f: Dict[str, Any]) -> None:
        root = f.get("chemin") or ""
        if not os.path.isdir(root):
            return
        known = self.known.setdefault(f["id"], {})
        seen_now: Dict[str, Tuple[int, float]] = {}
        try:
            if f.get("recursif"):
                walker = os.walk(root)
            else:
                walker = [(root, [], os.listdir(root))]
            for dirpath, _dirs, files in walker:
                # ne pas descendre dans _Traites/_Quarantaine
                if os.path.basename(dirpath) in ("_Traités", "_Traites", "_Quarantaine"):
                    continue
                for name in files:
                    p = os.path.join(dirpath, name)
                    try:
                        s = os.stat(p)
                    except OSError:
                        continue
                    sig = (s.st_size, s.st_mtime)
                    seen_now[p] = sig
                    if not self._bootstrapped:
                        continue  # premier passage : on note sans traiter
                    if known.get(p) != sig:
                        self.candidate(p, f["id"])
        except OSError as ex:
            jlog("ERREUR", "moteur", f"scan {root} : {ex}")
        self.known[f["id"]] = seen_now
        if not self._bootstrapped:
            # apres le premier scan de tous les dossiers actifs, on active
            actifs = [x["id"] for x in self.cfg.folders() if x.get("actif")]
            if all(i in self.known for i in actifs):
                self._bootstrapped = True
                jlog("INFO", "moteur", f"état initial capturé ({sum(len(v) for v in self.known.values())} fichiers)")

    def _process(self, path: str, fid: str) -> None:
        if not os.path.isfile(path):
            return
        try:
            h = sha256_file(path)
        except OSError:
            return
        if SEEN.seen_hash(h) and not path.lower().endswith(".padawan"):
            self.stats["ignores"] += 1
            jlog("INFO", "moteur", f"déjà vu (empreinte) : {os.path.basename(path)}")
            return
        # regles actives dans l'ordre
        matched = False
        avance = bool(self.cfg.data.get("mode_avance"))
        for rule in self.cfg.rules():
            if not rule.get("actif"):
                continue
            if not avance and any(a.get("type") == "commande_signee" for a in rule.get("actions") or []):
                continue
            if not schedule_ok(rule):
                continue
            # intervalle propre a la regle
            iv = int(rule.get("intervalle") or 0)
            if iv > 0:
                nxt = self.next_rule.get(rule["id"], 0)
                if time.time() < nxt and not (rule.get("evenementiel") and path.lower().endswith(".padawan")):
                    continue
            ok, _why = match_rule(rule, path, fid)
            if not ok:
                continue
            matched = True
            self.next_rule[rule["id"]] = time.time() + max(0, iv)
            self.last_rule[rule["id"]] = time.time()
            self._run_rule(rule, path)
            break
        if not matched and path.lower().endswith(".padawan") and avance:
            # .padawan sans regle active : toujours verifier (securite)
            for rule in self.cfg.rules():
                if any(a.get("type") == "commande_signee" for a in rule.get("actions") or []):
                    if rule.get("actif"):
                        self._run_rule(rule, path)
                        return
            quarantine(path, "aucune règle active pour .padawan")
            self.stats["refuses"] += 1

    def _run_rule(self, rule: Dict[str, Any], path: str) -> None:
        if rule.get("confirmer") and not ask_confirm_action("regle:" + rule.get("nom", ""), {"fichier": path}):
            jlog("ALERTE", "regle", f"« {rule.get('nom')} » annulée (confirmation)")
            return
        original = path
        cur = path
        msgs: List[str] = []
        relocated = False  # deplacer / supprimer / quarantaine : plus rien a ranger
        try:
            for a in rule.get("actions") or []:
                if not os.path.exists(cur) and a.get("type") not in ("notifier",):
                    break
                msg, newp = apply_action(a, cur, self.cfg, dry=False)
                msgs.append(msg)
                if "refusé" in msg.lower() or msg.startswith("refus"):
                    self.stats["refuses"] += 1
                    self._remember(rule, path, "REFUS", "; ".join(msgs))
                    return
                typ = a.get("type")
                if typ == "deplacer" and newp:
                    cur = newp
                    relocated = True
                elif typ == "supprimer":
                    relocated = True
                elif typ == "commande_signee" and not os.path.isfile(original):
                    relocated = True  # deja en quarantaine
                elif newp:
                    cur = newp
            # ranger l'ORIGINAL dans _Traites s'il est encore la (copie, exec, commande OK…)
            # ne pas toucher a la destination d'un deplacer
            if not relocated and os.path.isfile(original):
                self._to_traites(original)
            try:
                target = original if os.path.isfile(original) else (cur if os.path.isfile(cur) else "")
                if target:
                    SEEN.mark_hash(sha256_file(target))
            except Exception:
                pass
            self.stats["traites"] += 1
            self._remember(rule, path, "OK", "; ".join(msgs))
            jlog("OK", "regle", f"« {rule.get('nom')} » : {os.path.basename(path)} — {'; '.join(msgs)}")
        except Exception as ex:
            self.stats["erreurs"] += 1
            self._remember(rule, path, "ERREUR", str(ex))
            jlog("ERREUR", "regle", f"« {rule.get('nom')} » sur {path} : {ex}")

    def _to_traites(self, path: str) -> str:
        day = dt.date.today().isoformat()
        dest_dir = os.path.join(Paths.traites(), day)
        os.makedirs(dest_dir, exist_ok=True)
        dest = unique_path(os.path.join(dest_dir, os.path.basename(path)))
        try:
            shutil.move(path, dest)
            return dest
        except OSError as ex:
            jlog("ERREUR", "moteur", f"_Traités : {ex}")
            return path

    def _remember(self, rule: Dict[str, Any], path: str, status: str, msg: str) -> None:
        e = {"ts": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "regle": rule.get("nom", ""),
             "fichier": os.path.basename(path), "status": status, "msg": msg[:500]}
        with self.lock:
            self.recent.append(e)
            if len(self.recent) > 300:
                del self.recent[:100]
        if self.ui_cb:
            try:
                self.ui_cb()
            except Exception:
                pass


    def _poll_boites_sql(self) -> None:
        """Lit les boîtes SQL (pont PHP uniquement côté Marc) et exécute les commandes signées."""
        if boite_sql is None or not self.cfg.data.get("mode_avance"):
            return
        now = time.time()
        for b in self.cfg.boites():
            if not b.get("actif"):
                continue
            if not schedule_ok(b):
                continue
            iv = max(5, int(b.get("intervalle") or 30))
            if now < self.next_boite.get(b["id"], 0):
                continue
            self.next_boite[b["id"]] = now + iv
            try:
                self._process_boite(b)
            except Exception as ex:
                jlog("ERREUR", "boite", f"« {b.get('nom')} » : {ex}")
                self.stats["erreurs"] += 1

    def _process_boite(self, b: Dict[str, Any]) -> None:
        key = self.keys.load()
        mode = b.get("mode") or "pont"
        creds: Dict[str, Any] = {}
        if mode == "mysql":
            # réservé aux tests locaux ; l'UI Marc n'expose que le pont
            store = boite_sql.CredsStore(Paths.creds_boites(), lambda d: _dpapi(d, True),
                                         lambda d: _dpapi(d, False), IS_WIN)
            creds = store.get(b["id"])
            if not creds.get("password"):
                raise RuntimeError("mode mysql sans identifiants (tests seulement)")
        pending = boite_sql.fetch_pending(b, creds, key)
        for cmd in pending:
            self._run_sql_command(b, creds, key, cmd)

    def _run_sql_command(self, b: Dict[str, Any], creds: Dict[str, Any], key: bytes,
                         cmd: Dict[str, Any]) -> None:
        rem = self.cfg.data.get("remote") or {}
        expire = int(rem.get("expire_sec") or DEFAULT_EXPIRE_SEC)
        ok, why = verify_command(cmd, key, expire)
        if not ok:
            try:
                boite_sql.finish_command(b, creds, key, cmd, "refuse", why)
            except Exception as ex:
                jlog("ERREUR", "boite", f"finish refuse : {ex}")
            self.stats["refuses"] += 1
            jlog("REFUS", "boite", f"{cmd.get('action')} id={cmd.get('id')} — {why}")
            notify("Facteur — commande SQL refusée", why[:200], self.cfg)
            return
        action = str(cmd.get("action") or "")
        if action not in rem.get("actions_permises", REMOTE_ACTIONS):
            msg = f"action hors liste blanche : {action}"
            boite_sql.finish_command(b, creds, key, cmd, "refuse", msg)
            self.stats["refuses"] += 1
            return
        try:
            if action in (rem.get("confirmer") or []):
                if not ask_confirm_action(action, cmd.get("params") or {}):
                    boite_sql.finish_command(b, creds, key, cmd, "refuse", "refus confirmation")
                    self.stats["refuses"] += 1
                    return
            result = execute_remote(action, cmd.get("params") or {}, self.cfg)
            if action == "notifier":
                # ramener la fenêtre Facteur si une UI est branchée
                cb = getattr(self, "show_ui_cb", None)
                if cb:
                    try:
                        cb()
                    except Exception:
                        pass
            boite_sql.finish_command(b, creds, key, cmd, "traite", result)
            SEEN.mark_id(str(cmd["id"]))
            self.stats["traites"] += 1
            self._remember({"nom": f"Boîte SQL « {b.get('nom')} »"}, str(cmd.get("id")), "OK",
                           f"{action} — {result}")
            jlog("OK", "boite", f"{action} id={cmd['id']} — {result}")
            if action == "notifier" and str(result).startswith("lancé"):
                pass  # lancement discret deja notifie, on n'affiche pas le texte brut
            else:
                _disp = result if action != "notifier" else str((cmd.get("params") or {}).get("message") or result)
                notify("Facteur - message reçu", _disp[:200], self.cfg)
        except Exception as ex:
            try:
                boite_sql.finish_command(b, creds, key, cmd, "refuse", str(ex))
            except Exception:
                pass
            self.stats["erreurs"] += 1
            jlog("ERREUR", "boite", f"{action} : {ex}")

    # ---- infos tableau de bord ----------------------------------------
    def next_checks(self) -> List[Dict[str, Any]]:
        now = time.time()
        out: List[Dict[str, Any]] = []
        for f in self.cfg.folders():
            if not f.get("actif"):
                continue
            nxt = self.next_folder.get(f["id"], now)
            out.append({"kind": "dossier", "nom": f.get("note") or f.get("chemin"),
                        "dans": max(0, int(nxt - now)), "mode": "événementiel" if f.get("evenementiel") and self.observer else "sondage",
                        "intervalle": int(f.get("intervalle") or DEFAULT_INTERVAL)})
        for b in self.cfg.boites():
            if not b.get("actif"):
                continue
            iv = max(5, int(b.get("intervalle") or 30))
            nxt = self.next_boite.get(b["id"], now)
            out.append({"kind": "boîte SQL", "nom": b.get("nom"),
                        "dans": max(0, int(nxt - now)),
                        "mode": "pont PHP" if (b.get("mode") or "pont") == "pont" else "mysql",
                        "intervalle": iv})
        for r in self.cfg.rules():
            if not r.get("actif"):
                continue
            iv = int(r.get("intervalle") or 0)
            nxt = self.next_rule.get(r["id"], now)
            out.append({"kind": "règle", "nom": r.get("nom"), "dans": max(0, int(nxt - now)) if iv else 0,
                        "mode": "événementiel" if r.get("evenementiel") else f"toutes les {iv}s",
                        "intervalle": iv})
        return out

    # ---- test manuel --------------------------------------------------
    def test_rule(self, rule: Dict[str, Any], path: str, execute: bool = False) -> List[str]:
        lines: List[str] = []
        ok, why = match_rule(rule, path)
        lines.extend(why)
        if not schedule_ok(rule):
            lines.append("⚠ hors plage horaire actuellement")
        if not ok:
            return lines
        cur = path
        for a in rule.get("actions") or []:
            try:
                msg, newp = apply_action(a, cur, self.cfg, dry=not execute)
                lines.append("→ " + msg)
                if newp and execute:
                    cur = newp
            except Exception as ex:
                lines.append(f"✗ {ex}")
                break
        return lines


# ================================================================ themes (famille Padawan)
THEMES: Dict[str, Dict[str, str]] = {
    "norton": {
        "BG": "#0000AA", "PANEL": "#000088", "CARD": "#000066", "FG": "#55FFFF", "HI": "#FFFF55",
        "BTN": "#0000AA", "BTN_FG": "#FFFFFF", "ENTRY_BG": "#000055", "ENTRY_FG": "#FFFFFF",
        "SEL": "#AAAA00", "DIM": "#88AACC", "OK": "#55FF55", "ERR": "#FF5555", "TEXT": "#FFFFFF",
        "ON_HI": "#000000", "ON_SEL": "#000000", "LINE": "#3355AA", "IMG_BG": "#000033",
        "HI_ACT": "#FFFF88", "DISABLED": "#6677AA", "TIP_BG": "#FFFFCC", "TIP_FG": "#000000",
        "SASH": "#55FFFF", "WARN": "#FFAA33", "HOVER": "#0A0A99", "LINK": "#7FD4FF",
    },
    "sombre": {
        "BG": "#1E1E1E", "PANEL": "#252526", "CARD": "#2D2D30", "FG": "#D4D4D4", "HI": "#FFC83D",
        "BTN": "#3A3D41", "BTN_FG": "#FFFFFF", "ENTRY_BG": "#141414", "ENTRY_FG": "#F0F0F0",
        "SEL": "#C9A227", "DIM": "#8C8C8C", "OK": "#6CCB5F", "ERR": "#F1707B", "TEXT": "#F0F0F0",
        "ON_HI": "#000000", "ON_SEL": "#000000", "LINE": "#45454D", "IMG_BG": "#000000",
        "HI_ACT": "#FFD866", "DISABLED": "#6B6B6B", "TIP_BG": "#FFFFCC", "TIP_FG": "#000000",
        "SASH": "#5A5A5A", "WARN": "#FFAA33", "HOVER": "#38383C", "LINK": "#4FC1FF",
    },
    "clair": {
        "BG": "#F3F3F3", "PANEL": "#E4E7EB", "CARD": "#FFFFFF", "FG": "#1F3A5F", "HI": "#0B5CAD",
        "BTN": "#DADDE2", "BTN_FG": "#111111", "ENTRY_BG": "#FFFFFF", "ENTRY_FG": "#000000",
        "SEL": "#9CC3EE", "DIM": "#5F6B7A", "OK": "#1E7B34", "ERR": "#C62828", "TEXT": "#111111",
        "ON_HI": "#FFFFFF", "ON_SEL": "#000000", "LINE": "#B8C0CC", "IMG_BG": "#202428",
        "HI_ACT": "#3D8BDA", "DISABLED": "#A0A6AE", "TIP_BG": "#FFFFE0", "TIP_FG": "#000000",
        "SASH": "#9AA4B0", "WARN": "#B85C00", "HOVER": "#EEF3FA", "LINK": "#0645AD",
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
    "GHead": ("Consolas", 10, "bold", "roman"),
    "GMono": ("Consolas", 10, "normal", "roman"),
}
_FONT_OBJS: Dict[str, Any] = {}


def init_fonts(root, delta: int = 0) -> None:
    delta = max(-3, min(8, int(delta or 0)))
    try:
        fams = {f.lower() for f in tkfont.families(root)}
    except Exception:
        fams = set()
    for name, (fam, size, weight, slant) in FONT_SPECS.items():
        if fams and fam.lower() not in fams:
            fam = "DejaVu Sans Mono"
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
    st.configure("TCombobox", fieldbackground=C["ENTRY_BG"], background=C["BTN"], foreground=C["ENTRY_FG"],
                 arrowcolor=C["FG"], selectbackground=C["ENTRY_BG"], selectforeground=C["ENTRY_FG"], padding=2)
    st.map("TCombobox", fieldbackground=[("readonly", C["ENTRY_BG"])], foreground=[("readonly", C["ENTRY_FG"])])
    root.option_add("*TCombobox*Listbox.background", C["ENTRY_BG"])
    root.option_add("*TCombobox*Listbox.foreground", C["ENTRY_FG"])
    root.option_add("*TCombobox*Listbox.selectBackground", C["SEL"])
    root.option_add("*TCombobox*Listbox.selectForeground", C["ON_SEL"])
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


class Tooltip:
    def __init__(self, widget, text: Any, delay: int = 500):
        self.w, self.text, self.delay = widget, text, delay
        self.tip = self.job = None
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
        tw = tk.Toplevel(self.w)
        tw.wm_overrideredirect(True)
        try:
            tw.attributes("-topmost", True)
        except tk.TclError:
            pass
        tk.Label(tw, text=txt, bg=C["TIP_BG"], fg=C["TIP_FG"], font=fnt("GSM"), justify="left",
                 relief="solid", bd=1, padx=6, pady=3, wraplength=520).pack()
        tw.update_idletasks()
        x = min(self.w.winfo_pointerx() + 14, self.w.winfo_screenwidth() - tw.winfo_reqwidth() - 4)
        y = self.w.winfo_pointery() + 18
        tw.wm_geometry(f"+{max(0, x)}+{max(0, y)}")
        self.tip = tw

    def _hide(self, _e=None):
        self._cancel()
        if self.tip is not None:
            try:
                self.tip.destroy()
            except Exception:
                pass
            self.tip = None


def mk_button(parent, text, cmd, kind="", width=0, tip=""):
    bg, fg, abg, afg = C["BTN"], C["BTN_FG"], C["HI"], C["ON_HI"]
    if kind == "accent":
        bg, fg, abg, afg = C["HI"], C["ON_HI"], C["HI_ACT"], C["ON_HI"]
    elif kind == "danger":
        bg, fg = C["BTN"], C["ERR"]
    elif kind == "ghost":
        bg = parent.cget("bg") if "bg" in parent.keys() else C["BG"]
    b = tk.Button(parent, text=text, command=cmd, bg=bg, fg=fg, activebackground=abg, activeforeground=afg,
                  relief="flat", bd=0, highlightthickness=1, highlightbackground=C["LINE"], padx=9, pady=3,
                  font=fnt("GUIB" if kind == "accent" else "GUI"), cursor="hand2", disabledforeground=C["DISABLED"])
    if width:
        b.configure(width=width)
    b._colors = (bg, fg, abg, afg)  # type: ignore
    b.bind("<Enter>", lambda _e: b.configure(bg=b._colors[2], fg=b._colors[3]) if str(b["state"]) != "disabled" else None)
    b.bind("<Leave>", lambda _e: b.configure(bg=b._colors[0], fg=b._colors[1]))
    if tip:
        Tooltip(b, tip)
    return b


def mk_entry(parent, var=None, width=30):
    return tk.Entry(parent, textvariable=var, width=width, bg=C["ENTRY_BG"], fg=C["ENTRY_FG"],
                    insertbackground=C["HI"], relief="flat", highlightthickness=1, highlightbackground=C["LINE"],
                    highlightcolor=C["HI"], font=fnt("GUI"), selectbackground=C["SEL"], selectforeground=C["ON_SEL"])


def mk_label(parent, text="", key="FG", font_name="GUI", bg="", **kw):
    return tk.Label(parent, text=text, fg=C[key], bg=bg or parent.cget("bg"), font=fnt(font_name), **kw)


def mk_check(parent, text, var, bg="", cmd=None):
    b = bg or parent.cget("bg")
    return tk.Checkbutton(parent, text=text, variable=var, bg=b, fg=C["TEXT"], selectcolor=C["ENTRY_BG"],
                          activebackground=b, activeforeground=C["HI"], font=fnt("GUI"), anchor="w",
                          highlightthickness=0, bd=0, command=cmd)


def mk_link(parent, text, target, bg="", cmd=None):
    try:
        uf = tkfont.Font(font=fnt("GUI")); uf.configure(underline=True)
    except Exception:
        uf = fnt("GUI")
    lab = tk.Label(parent, text=text, fg=C["LINK"], bg=bg or parent.cget("bg"), font=uf, cursor="hand2",
                   justify="left", anchor="w")
    lab.bind("<Button-1>", lambda _e: cmd() if cmd else open_path(target))
    Tooltip(lab, target if not cmd else "")
    return lab


def style_menu(m) -> None:
    m.configure(bg=C["PANEL"], fg=C["TEXT"], activebackground=C["SEL"], activeforeground=C["ON_SEL"],
                font=fnt("GUI"), tearoff=0, relief="flat", bd=1, selectcolor=C["HI"],
                disabledforeground=C["DISABLED"])


def new_menu(parent):
    m = tk.Menu(parent, tearoff=0)
    style_menu(m)
    return m


class ScrollFrame(tk.Frame):
    def __init__(self, parent, bg=""):
        bg = bg or C["BG"]
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self.win = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.vsb.pack(side="right", fill="y")
        self.inner.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.win, width=e.width))
        self.bind("<Enter>", lambda _e: self.bind_all("<MouseWheel>", self._wheel), add="+")
        self.bind("<Leave>", lambda _e: self.unbind_all("<MouseWheel>"), add="+")

    def _wheel(self, e):
        d = int(getattr(e, "delta", 0) or 0)
        if d:
            self.canvas.yview_scroll(-1 if d > 0 else 1, "units")


# ================================================================ icones
def generate_app_icons(out_dir: str, force: bool = False) -> Tuple[str, str]:
    """facteur1.ico / .png / _256.png : lettre jaune sur bleu Norton avec une petite enveloppe."""
    ico = os.path.join(out_dir, "facteur1.ico")
    png = os.path.join(out_dir, "facteur1.png")
    big = os.path.join(out_dir, "facteur1_256.png")
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
    # enveloppe
    d.rounded_rectangle([48, 70, 208, 190], radius=12, fill=yellow, outline=dark, width=6)
    d.polygon([(48, 70), (128, 140), (208, 70)], outline=dark)
    d.line([(48, 70), (128, 140), (208, 70)], fill=dark, width=6)
    try:
        os.makedirs(out_dir, exist_ok=True)
        img.save(big)
        img.resize((64, 64), Image.Resampling.LANCZOS).save(png)
        img.save(ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    except OSError:
        return "", ""
    return ico, png


# ================================================================ dialogs
class Modal(tk.Toplevel):
    def __init__(self, parent, title: str, w: int = 720, h: int = 520):
        super().__init__(parent)
        self.title(title)
        self.configure(bg=C["BG"])
        self.transient(parent)
        self.result = None
        self.resizable(True, True)
        try:
            self.grab_set()
        except tk.TclError:
            pass
        self.update_idletasks()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        x = px + max(20, (pw - w) // 2)
        y = py + max(20, (ph - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.bind("<Escape>", lambda _e: self.cancel())

    def cancel(self):
        self.result = None
        self.destroy()

    def ok(self, value=True):
        self.result = value
        self.destroy()


class FolderDialog(Modal):
    def __init__(self, parent, folder: Optional[Dict[str, Any]] = None):
        super().__init__(parent, "Dossier surveillé", 640, 360)
        f = dict(folder or {})
        self.v_chemin = tk.StringVar(value=f.get("chemin") or known_folder_downloads())
        self.v_note = tk.StringVar(value=f.get("note") or "")
        self.v_rec = tk.BooleanVar(value=bool(f.get("recursif")))
        self.v_actif = tk.BooleanVar(value=f.get("actif", True))
        self.v_evt = tk.BooleanVar(value=f.get("evenementiel", True))
        self.v_iv = tk.StringVar(value=str(f.get("intervalle") or DEFAULT_INTERVAL))
        body = tk.Frame(self, bg=C["BG"], padx=14, pady=10)
        body.pack(fill="both", expand=True)
        mk_label(body, "Chemin", "HI", "GUIB").pack(anchor="w")
        row = tk.Frame(body, bg=C["BG"]); row.pack(fill="x", pady=2)
        mk_entry(row, self.v_chemin, 50).pack(side="left", fill="x", expand=True)
        mk_button(row, "…", self._browse, tip="Choisir un dossier").pack(side="left", padx=4)
        mk_button(row, "Téléchargements", lambda: self.v_chemin.set(known_folder_downloads()),
                  tip="Dossier connu Windows (FOLDERID_Downloads)").pack(side="left")
        mk_label(body, "Note (optionnelle)", "DIM", "GSM").pack(anchor="w", pady=(8, 0))
        mk_entry(body, self.v_note, 50).pack(fill="x")
        mk_check(body, "Actif", self.v_actif).pack(anchor="w", pady=(8, 0))
        mk_check(body, "Récursif (sous-dossiers)", self.v_rec).pack(anchor="w")
        mk_check(body, "Mode événementiel (watchdog, sans sondage fréquent)", self.v_evt).pack(anchor="w")
        r2 = tk.Frame(body, bg=C["BG"]); r2.pack(fill="x", pady=6)
        mk_label(r2, "Intervalle de vérification (secondes) :").pack(side="left")
        mk_entry(r2, self.v_iv, 8).pack(side="left", padx=6)
        mk_label(r2, "ex. 10, 60, 900, 3600", "DIM", "GSM").pack(side="left")
        bot = tk.Frame(self, bg=C["PANEL"], padx=10, pady=8); bot.pack(fill="x", side="bottom")
        mk_button(bot, "Annuler", self.cancel).pack(side="right", padx=4)
        mk_button(bot, "Enregistrer", self._save, "accent").pack(side="right")

    def _browse(self):
        d = filedialog.askdirectory(parent=self, initialdir=self.v_chemin.get() or os.path.expanduser("~"))
        if d:
            self.v_chemin.set(d)

    def _save(self):
        p = self.v_chemin.get().strip()
        if not p or not os.path.isdir(p):
            messagebox.showwarning(APP_NAME, "Dossier invalide.", parent=self)
            return
        try:
            iv = max(2, int(self.v_iv.get()))
        except ValueError:
            messagebox.showwarning(APP_NAME, "Intervalle invalide.", parent=self)
            return
        self.ok({"chemin": os.path.abspath(p), "note": self.v_note.get().strip(), "recursif": self.v_rec.get(),
                 "actif": self.v_actif.get(), "evenementiel": self.v_evt.get(), "intervalle": iv})


class ActionEditor(tk.Frame):
    """Une ligne d'action editable (type + champs selon le type)."""

    def __init__(self, parent, action: Dict[str, Any], on_del: Callable):
        super().__init__(parent, bg=C["CARD"], highlightthickness=1, highlightbackground=C["LINE"], padx=6, pady=4)
        self.action = dict(action)
        self.on_del = on_del
        self.vars: Dict[str, Any] = {}
        top = tk.Frame(self, bg=C["CARD"]); top.pack(fill="x")
        mk_label(top, "Action", "HI", "GSMB").pack(side="left")
        self.v_type = tk.StringVar(value=self.action.get("type") or "notifier")
        cb = ttk.Combobox(top, textvariable=self.v_type, values=list(ACTION_TYPES), state="readonly", width=18)
        cb.pack(side="left", padx=6)
        cb.bind("<<ComboboxSelected>>", lambda _e: self._rebuild())
        mk_button(top, "✕", self.on_del, "danger", tip="Retirer cette action").pack(side="right")
        self.body = tk.Frame(self, bg=C["CARD"]); self.body.pack(fill="x", pady=4)
        self._rebuild()

    def _rebuild(self):
        for w in self.body.winfo_children():
            w.destroy()
        self.vars.clear()
        t = self.v_type.get()
        a = self.action
        if t in ("deplacer", "copier"):
            self._path("dest", a.get("dest") or "", "Destination")
            self.vars["par_type"] = tk.BooleanVar(value=bool(a.get("par_type")))
            mk_check(self.body, "Sous-dossier selon le type (Images, PDF…)", self.vars["par_type"]).pack(anchor="w")
        elif t == "renommer":
            self._str("modele", a.get("modele") or "{nom}_{date}.{ext}", "Modèle ({nom} {ext} {date} {dossier})")
        elif t == "grimoire":
            self._str("sujet", a.get("sujet") or "", "Sujet (ex. Santé/Protocoles)")
            self._str("titre", a.get("titre") or "", "Titre (optionnel)")
            self._str("note", a.get("note") or "", "Note")
        elif t == "archiveur":
            self._str("url", a.get("url") or "", "URL (vide = ouvrir l'Archiveur)")
        elif t == "executer":
            self.vars["shell"] = tk.StringVar(value=a.get("shell") or "cmd")
            r = tk.Frame(self.body, bg=C["CARD"]); r.pack(fill="x")
            mk_label(r, "Shell").pack(side="left")
            ttk.Combobox(r, textvariable=self.vars["shell"], values=["cmd", "powershell"], state="readonly",
                         width=12).pack(side="left", padx=6)
            self._str("ligne", a.get("ligne") or 'echo Traite {fichier}',
                      "Ligne ({fichier} {nom} {ext} {dossier} {date})")
            self.vars["admin"] = tk.BooleanVar(value=bool(a.get("admin")))
            self.vars["visible"] = tk.BooleanVar(value=bool(a.get("visible")))
            self.vars["capturer"] = tk.BooleanVar(value=a.get("capturer", True))
            self.vars["timeout"] = tk.StringVar(value=str(a.get("timeout") or 300))
            mk_check(self.body, "En admin (invite UAC)", self.vars["admin"]).pack(anchor="w")
            mk_check(self.body, "Fenêtre visible", self.vars["visible"]).pack(anchor="w")
            mk_check(self.body, "Capturer la sortie dans le journal", self.vars["capturer"]).pack(anchor="w")
            r2 = tk.Frame(self.body, bg=C["CARD"]); r2.pack(fill="x")
            mk_label(r2, "Délai (s)").pack(side="left")
            mk_entry(r2, self.vars["timeout"], 8).pack(side="left", padx=6)
            mk_label(self.body, "⚠ Commande libre : seulement dans une règle LOCALE, jamais depuis un .padawan.",
                     "WARN", "GSM").pack(anchor="w", pady=2)
        elif t == "decompresser":
            self._path("dest", a.get("dest") or "", "Destination (vide = sous-dossier du même nom)")
        elif t == "notifier":
            self._str("message", a.get("message") or "Fichier traité : {nom_ext}", "Message")
        elif t == "supprimer":
            mk_label(self.body, "Envoie le fichier à la corbeille Windows (récupérable).", "DIM", "GSM").pack(anchor="w")

    def _str(self, key, val, label):
        mk_label(self.body, label, "DIM", "GSM").pack(anchor="w")
        self.vars[key] = tk.StringVar(value=val)
        mk_entry(self.body, self.vars[key], 60).pack(fill="x", pady=1)

    def _path(self, key, val, label):
        mk_label(self.body, label, "DIM", "GSM").pack(anchor="w")
        self.vars[key] = tk.StringVar(value=val)
        r = tk.Frame(self.body, bg=C["CARD"]); r.pack(fill="x")
        mk_entry(r, self.vars[key], 50).pack(side="left", fill="x", expand=True)
        mk_button(r, "…", lambda: self._browse(key)).pack(side="left", padx=4)

    def _browse(self, key):
        d = filedialog.askdirectory(parent=self)
        if d:
            self.vars[key].set(d)

    def get(self) -> Dict[str, Any]:
        t = self.v_type.get()
        out: Dict[str, Any] = {"type": t}
        for k, v in self.vars.items():
            if isinstance(v, tk.BooleanVar):
                out[k] = v.get()
            elif k == "timeout":
                try:
                    out[k] = max(1, int(v.get()))
                except ValueError:
                    out[k] = 300
            else:
                out[k] = v.get().strip()
        return out


class RuleDialog(Modal):
    """Editeur complet : QUOI / QUAND / QUOI FAIRE."""

    def __init__(self, parent, app: "FacteurApp", rule: Optional[Dict[str, Any]] = None):
        super().__init__(parent, "Éditeur de règle", 860, 640)
        self.app = app
        self.rule = dict(rule or _rule("Nouvelle règle", True))
        self.action_widgets: List[ActionEditor] = []
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=8)
        self.tab_quoi = tk.Frame(nb, bg=C["BG"], padx=10, pady=8)
        self.tab_quand = tk.Frame(nb, bg=C["BG"], padx=10, pady=8)
        self.tab_faire = tk.Frame(nb, bg=C["BG"], padx=10, pady=8)
        nb.add(self.tab_quoi, text="  Quoi  ")
        nb.add(self.tab_quand, text="  Quand  ")
        nb.add(self.tab_faire, text="  Quoi faire  ")
        self._build_quoi()
        self._build_quand()
        self._build_faire()
        bot = tk.Frame(self, bg=C["PANEL"], padx=10, pady=8); bot.pack(fill="x", side="bottom")
        mk_button(bot, "Tester…", self._test, tip="Simulation puis exécution réelle optionnelle").pack(side="left")
        mk_button(bot, "Annuler", self.cancel).pack(side="right", padx=4)
        mk_button(bot, "Enregistrer", self._save, "accent").pack(side="right")

    def _build_quoi(self):
        t = self.tab_quoi
        self.v_nom = tk.StringVar(value=self.rule.get("nom") or "")
        self.v_actif = tk.BooleanVar(value=bool(self.rule.get("actif")))
        self.v_confirmer = tk.BooleanVar(value=bool(self.rule.get("confirmer")))
        self.v_note = tk.StringVar(value=self.rule.get("note") or "")
        self.v_masque = tk.StringVar(value=self.rule.get("masque") or "*")
        self.v_ext = tk.StringVar(value=",".join(norm_exts(self.rule.get("extensions"))))
        self.v_regex = tk.StringVar(value=self.rule.get("regex") or "")
        self.v_tmin = tk.StringVar(value=str(self.rule.get("taille_min") or 0))
        self.v_tmax = tk.StringVar(value=str(self.rule.get("taille_max") or 0))
        self.v_amin = tk.StringVar(value=str((self.rule.get("age_min") or 0) // 60))
        self.v_amax = tk.StringVar(value=str((self.rule.get("age_max") or 0) // 60))
        mk_label(t, "Nom de la règle", "HI", "GUIB").pack(anchor="w")
        mk_entry(t, self.v_nom, 50).pack(fill="x", pady=2)
        mk_check(t, "Règle active", self.v_actif).pack(anchor="w")
        mk_check(t, "Demander confirmation avant d'agir", self.v_confirmer).pack(anchor="w")
        mk_label(t, "Note", "DIM", "GSM").pack(anchor="w", pady=(6, 0))
        mk_entry(t, self.v_note, 60).pack(fill="x")
        mk_label(t, "Dossiers concernés (vide = tous)", "HI", "GUIB").pack(anchor="w", pady=(10, 2))
        self.folder_vars: Dict[str, tk.BooleanVar] = {}
        for f in self.app.cfg.folders():
            bv = tk.BooleanVar(value=f["id"] in (self.rule.get("dossiers") or []) or not self.rule.get("dossiers"))
            # si dossiers vide a l'origine, on ne coche pas tout "comme selection" - on laisse vide = tous
            if not self.rule.get("dossiers"):
                bv.set(False)
            self.folder_vars[f["id"]] = bv
            mk_check(t, f"{f.get('note') or f.get('chemin')}", bv).pack(anchor="w")
        mk_label(t, "(aucun coché = tous les dossiers)", "DIM", "GSM").pack(anchor="w")
        mk_label(t, "Masque de nom (glob, ; pour plusieurs)", "HI", "GUIB").pack(anchor="w", pady=(10, 0))
        mk_entry(t, self.v_masque, 50).pack(fill="x")
        mk_label(t, "Extensions (sans point, séparées par virgule)", "DIM", "GSM").pack(anchor="w", pady=(6, 0))
        mk_entry(t, self.v_ext, 50).pack(fill="x")
        mk_label(t, "Regex sur le nom (optionnel)", "DIM", "GSM").pack(anchor="w", pady=(6, 0))
        mk_entry(t, self.v_regex, 50).pack(fill="x")
        r = tk.Frame(t, bg=C["BG"]); r.pack(fill="x", pady=8)
        mk_label(r, "Taille min (o)").pack(side="left"); mk_entry(r, self.v_tmin, 10).pack(side="left", padx=4)
        mk_label(r, "max").pack(side="left"); mk_entry(r, self.v_tmax, 10).pack(side="left", padx=4)
        mk_label(r, "  Âge min (min)").pack(side="left"); mk_entry(r, self.v_amin, 8).pack(side="left", padx=4)
        mk_label(r, "max").pack(side="left"); mk_entry(r, self.v_amax, 8).pack(side="left", padx=4)

    def _build_quand(self):
        t = self.tab_quand
        self.v_iv = tk.StringVar(value=str(self.rule.get("intervalle") or 0))
        self.v_evt = tk.BooleanVar(value=bool(self.rule.get("evenementiel", True)))
        self.v_maxp = tk.StringVar(value=str(self.rule.get("max_par_passe") or 0))
        h = self.rule.get("horaire") or {}
        self.v_hactif = tk.BooleanVar(value=bool(h.get("actif")))
        self.v_debut = tk.StringVar(value=h.get("debut") or "08:00")
        self.v_fin = tk.StringVar(value=h.get("fin") or "22:00")
        self.day_vars = [tk.BooleanVar(value=i in (h.get("jours") or list(range(7)))) for i in range(7)]
        mk_label(t, "Intervalle de cette règle (secondes, 0 = suit le dossier)", "HI", "GUIB").pack(anchor="w")
        r = tk.Frame(t, bg=C["BG"]); r.pack(fill="x", pady=4)
        mk_entry(r, self.v_iv, 10).pack(side="left")
        for lab, val in (("10 s", "10"), ("1 min", "60"), ("15 min", "900"), ("1 h", "3600")):
            mk_button(r, lab, lambda v=val: self.v_iv.set(v), "ghost").pack(side="left", padx=3)
        mk_check(t, "Mode événementiel (réagit tout de suite si watchdog disponible)", self.v_evt).pack(anchor="w", pady=6)
        mk_label(t, "Max fichiers par passe (0 = limite globale)", "DIM", "GSM").pack(anchor="w")
        mk_entry(t, self.v_maxp, 8).pack(anchor="w")
        mk_label(t, "Plage horaire (optionnelle)", "HI", "GUIB").pack(anchor="w", pady=(12, 2))
        mk_check(t, "Activer la plage horaire", self.v_hactif).pack(anchor="w")
        r2 = tk.Frame(t, bg=C["BG"]); r2.pack(fill="x", pady=4)
        mk_label(r2, "De").pack(side="left"); mk_entry(r2, self.v_debut, 8).pack(side="left", padx=4)
        mk_label(r2, "à").pack(side="left"); mk_entry(r2, self.v_fin, 8).pack(side="left", padx=4)
        mk_label(r2, "(HH:MM)", "DIM", "GSM").pack(side="left")
        r3 = tk.Frame(t, bg=C["BG"]); r3.pack(fill="x", pady=6)
        for i, lab in enumerate(("Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim")):
            mk_check(r3, lab, self.day_vars[i]).pack(side="left", padx=4)

    def _build_faire(self):
        t = self.tab_faire
        top = tk.Frame(t, bg=C["BG"]); top.pack(fill="x")
        mk_label(top, "Actions enchaînées (dans l'ordre)", "HI", "GUIB").pack(side="left")
        mk_button(top, "+ Ajouter", self._add_action, "accent").pack(side="right")
        self.sf = ScrollFrame(t, C["BG"]); self.sf.pack(fill="both", expand=True, pady=6)
        for a in self.rule.get("actions") or []:
            if a.get("type") == "commande_signee":
                # action speciale : non editable ici
                fr = tk.Frame(self.sf.inner, bg=C["CARD"], highlightthickness=1, highlightbackground=C["LINE"], padx=8, pady=6)
                fr.pack(fill="x", pady=3)
                mk_label(fr, "⚙ Commande signée (.padawan) — gérée par le moteur sécurisé", "HI", "GUIB").pack(anchor="w")
                self.action_widgets.append(fr)  # type: ignore
                fr._is_signed = True  # type: ignore
                fr.get = lambda: {"type": "commande_signee"}  # type: ignore
            else:
                self._add_action(a)

    def _add_action(self, a: Optional[Dict[str, Any]] = None):
        if a is None:
            a = {"type": "notifier", "message": "Fichier traité : {nom_ext}"}
        def _del(w=None):
            pass
        w = ActionEditor(self.sf.inner, a, on_del=lambda: None)
        w.pack(fill="x", pady=3)
        def do_del(ww=w):
            try:
                self.action_widgets.remove(ww)
                ww.destroy()
            except Exception:
                pass
        w.on_del = do_del
        # rebind bouton
        for child in w.winfo_children():
            if isinstance(child, tk.Frame):
                for b in child.winfo_children():
                    if isinstance(b, tk.Button) and b.cget("text") == "✕":
                        b.configure(command=do_del)
        self.action_widgets.append(w)

    def _collect(self) -> Optional[Dict[str, Any]]:
        nom = self.v_nom.get().strip()
        if not nom:
            messagebox.showwarning(APP_NAME, "Donne un nom à la règle.", parent=self)
            return None
        try:
            iv = max(0, int(self.v_iv.get() or 0))
            tmin = max(0, int(self.v_tmin.get() or 0))
            tmax = max(0, int(self.v_tmax.get() or 0))
            amin = max(0, int(self.v_amin.get() or 0)) * 60
            amax = max(0, int(self.v_amax.get() or 0)) * 60
            maxp = max(0, int(self.v_maxp.get() or 0))
        except ValueError:
            messagebox.showwarning(APP_NAME, "Nombre invalide.", parent=self)
            return None
        dossiers = [fid for fid, v in self.folder_vars.items() if v.get()]
        actions = []
        for w in self.action_widgets:
            try:
                actions.append(w.get())
            except Exception:
                pass
        if not actions:
            messagebox.showwarning(APP_NAME, "Ajoute au moins une action.", parent=self)
            return None
        r = dict(self.rule)
        r.update({
            "nom": nom, "actif": self.v_actif.get(), "confirmer": self.v_confirmer.get(),
            "note": self.v_note.get().strip(), "dossiers": dossiers,
            "masque": self.v_masque.get().strip() or "*",
            "extensions": norm_exts(self.v_ext.get()),
            "regex": self.v_regex.get().strip(),
            "taille_min": tmin, "taille_max": tmax, "age_min": amin, "age_max": amax,
            "intervalle": iv, "evenementiel": self.v_evt.get(), "max_par_passe": maxp,
            "horaire": {"actif": self.v_hactif.get(), "debut": self.v_debut.get().strip() or "08:00",
                        "fin": self.v_fin.get().strip() or "22:00",
                        "jours": [i for i, v in enumerate(self.day_vars) if v.get()]},
            "actions": actions,
        })
        if "id" not in r or not r["id"]:
            r["id"] = uuid.uuid4().hex[:8]
        return r

    def _save(self):
        r = self._collect()
        if r:
            self.ok(r)

    def _test(self):
        r = self._collect()
        if not r:
            return
        path = filedialog.askopenfilename(parent=self, title="Fichier à tester")
        if not path:
            return
        lines = self.app.engine.test_rule(r, path, execute=False)
        msg = "Simulation :\n\n" + "\n".join(lines)
        if messagebox.askyesno(APP_NAME, msg + "\n\nExécuter pour de vrai sur ce fichier ?", parent=self):
            lines2 = self.app.engine.test_rule(r, path, execute=True)
            messagebox.showinfo(APP_NAME, "Exécution :\n\n" + "\n".join(lines2), parent=self)


# ================================================================ application principale
class FacteurApp(tk.Tk):
    def __init__(self, args):
        super().__init__()
        self.withdraw()
        self.args = args
        self.title(APP_TITLE)
        self.cfg = Config().load()
        self.keys = KeyStore()   # aucune cle creee automatiquement (mode avance seulement, sur demande)
        SEEN.load()
        C.clear(); C.update(THEMES.get(self.cfg.data.get("theme", "norton"), THEMES["norton"]))
        init_fonts(self, self.cfg.data.get("font_delta", 0))
        self.engine = Engine(self.cfg, self.keys)
        self.engine.ui_cb = lambda: self.after(0, self.refresh_dash)
        self.engine.show_ui_cb = lambda: self.after(0, self._show_from_notify)
        global _confirm_cb
        _confirm_cb = self._confirm_ui
        self._build()
        try:
            ico = os.path.join(BASE, "facteur1.ico")
            if os.path.isfile(ico):
                self.iconbitmap(default=ico)
        except tk.TclError:
            pass
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.bind("<F1>", lambda _e: self.show_help())
        self.deiconify()
        if getattr(args, "geometry", ""):
            self.geometry(args.geometry)
        else:
            try:
                self.state("zoomed")
            except tk.TclError:
                self.geometry(f"{self.winfo_screenwidth()}x{self.winfo_screenheight() - 60}+0+0")
        if getattr(args, "cache", False):
            self.after(200, self.withdraw)
        self.engine.start()
        self.after(800, self.refresh_all)
        self.after(2000, self._tick)
        JOURNAL.listeners.append(lambda e: self.after(0, self._on_log, e))
        self.readonly_test = bool(getattr(args, "smoke", False) or getattr(args, "shot", ""))
        # aucune cle affichee automatiquement ; assistant si aucune regle
        if (not self.readonly_test and not getattr(args, "cache", False) and not self.cfg.rules()):
            self.after(900, self.first_rule_wizard)

    # ---- confirmation UI (actions distantes / regles) -----------------
    def _confirm_ui(self, action: str, params: Dict[str, Any]) -> bool:
        ev = threading.Event()
        box: List[bool] = [False]
        def ask():
            box[0] = messagebox.askyesno(APP_NAME, f"Autoriser l'action ?\n\n{action}\n{params}", parent=self)
            ev.set()
        self.after(0, ask)
        ev.wait(120)
        return box[0]

    # ---- construction -------------------------------------------------
    def _build(self):
        apply_styles(self)
        self.configure(bg=C["BG"])
        self._menu()
        top = tk.Frame(self, bg=C["PANEL"], padx=10, pady=6); top.pack(fill="x")
        mk_label(top, "📬 Facteur", "HI", "GTitle").pack(side="left")
        self.lbl_status = mk_label(top, "", "FG", "GUI"); self.lbl_status.pack(side="left", padx=16)
        self.v_pause = tk.BooleanVar(value=bool(self.cfg.data.get("pause_globale")))
        mk_check(top, "Pause globale", self.v_pause, C["PANEL"], cmd=self.toggle_pause).pack(side="right", padx=8)
        mk_button(top, "Aide (F1)", self.show_help, "ghost").pack(side="right", padx=4)
        self.nb = ttk.Notebook(self); self.nb.pack(fill="both", expand=True, padx=6, pady=6)
        self.tab_dash = tk.Frame(self.nb, bg=C["BG"]); self.nb.add(self.tab_dash, text="  Tableau de bord  ")
        self.tab_rules = tk.Frame(self.nb, bg=C["BG"]); self.nb.add(self.tab_rules, text="  Règles  ")
        self.tab_folders = tk.Frame(self.nb, bg=C["BG"]); self.nb.add(self.tab_folders, text="  Dossiers  ")
        self.tab_log = tk.Frame(self.nb, bg=C["BG"]); self.nb.add(self.tab_log, text="  Journal  ")
        self.tab_remote = tk.Frame(self.nb, bg=C["BG"]); self.nb.add(self.tab_remote, text="  Commandes à distance  ")
        self.tab_boites = tk.Frame(self.nb, bg=C["BG"]); self.nb.add(self.tab_boites, text="  Boîtes SQL  ")
        self.tab_opts = tk.Frame(self.nb, bg=C["BG"]); self.nb.add(self.tab_opts, text="  Options  ")
        self._build_dash(); self._build_rules(); self._build_folders()
        self._build_log(); self._build_remote(); self._build_boites(); self._build_opts()
        self._apply_advanced_tabs()
        bot = tk.Frame(self, bg=C["PANEL"], padx=8, pady=4); bot.pack(fill="x", side="bottom")
        self.lbl_foot = mk_label(bot, "", "DIM", "GSM"); self.lbl_foot.pack(side="left")
        mk_link(bot, "Ouvrir les données", Paths.data, C["PANEL"]).pack(side="right", padx=8)

    def _menu(self):
        m = tk.Menu(self); self.config(menu=m)
        f = new_menu(m); m.add_cascade(label="Fichier", menu=f)
        f.add_command(label="Enregistrer la config", command=self.save_cfg)
        f.add_command(label="Exporter les règles…", command=self.export_rules)
        f.add_command(label="Importer un paquet de r\u00e8gles\u2026", command=self.import_rules)
        f.add_separator()
        self.v_autostart = tk.BooleanVar(value=autostart_enabled())
        f.add_checkbutton(label="Démarrer avec Windows (en arrière-plan)", variable=self.v_autostart,
                          command=lambda: (set_autostart(self.v_autostart.get()),
                                           self.v_autostart.set(autostart_enabled())))
        f.add_separator()
        f.add_command(label="Masquer (reste en arrière-plan)", command=self.withdraw)
        f.add_command(label="Quitter Facteur", command=self.quit_app)
        r = new_menu(m); m.add_cascade(label="Règles", menu=r)
        r.add_command(label="Nouvelle règle…", command=self.new_rule)
        r.add_command(label="\u2728 Ma premi\u00e8re r\u00e8gle (assistant)\u2026", command=self.first_rule_wizard)
        r.add_command(label="Bibliothèque de modèles…", command=self.templates)
        t = new_menu(m); m.add_cascade(label="Thème", menu=t)
        self.v_theme = tk.StringVar(value=self.cfg.data.get("theme", "norton"))
        for k, lab in THEME_LABELS.items():
            t.add_radiobutton(label=lab, variable=self.v_theme, value=k, command=self.change_theme)
        a = new_menu(m); m.add_cascade(label="Aide", menu=a)
        a.add_command(label="Aide (F1)", command=self.show_help)
        a.add_command(label="À propos", command=lambda: messagebox.showinfo(APP_NAME,
            f"{APP_NAME}\nSurveillant de dossiers et commandes signées\nProjet Padawan\n\nDonnées : {Paths.data}",
            parent=self))

    def _build_dash(self):
        t = self.tab_dash
        hb = tk.Frame(t, bg=C["BG"]); hb.pack(fill="x", padx=10, pady=(10, 0))
        mk_button(hb, "\u2728 Ma premi\u00e8re r\u00e8gle (assistant 3 \u00e9tapes)", self.first_rule_wizard, "accent").pack(side="left")
        mk_label(hb, "  Facteur range tes fichiers tout seul : choisis un dossier, un genre de fichiers, et quoi en faire.",
                 "DIM", "GSM").pack(side="left")
        cards = tk.Frame(t, bg=C["BG"]); cards.pack(fill="x", padx=10, pady=10)
        self.stat_labs: Dict[str, tk.Label] = {}
        for key, lab, col in (("traites", "Traités", "OK"), ("refuses", "Refusés", "ERR"),
                              ("erreurs", "Erreurs", "WARN"), ("ignores", "Ignorés", "DIM"),
                              ("attente", "En attente", "FG")):
            fr = tk.Frame(cards, bg=C["CARD"], padx=14, pady=10, highlightthickness=1, highlightbackground=C["LINE"])
            fr.pack(side="left", padx=6)
            mk_label(fr, lab, "DIM", "GSM").pack()
            self.stat_labs[key] = mk_label(fr, "0", col, "GTitle"); self.stat_labs[key].pack()
        mk_label(t, "Prochaines vérifications", "HI", "GUIB").pack(anchor="w", padx=12)
        self.tree_next = ttk.Treeview(t, columns=("kind", "nom", "dans", "mode"), show="headings", height=8)
        for c, lab, w in (("kind", "Type", 80), ("nom", "Nom", 360), ("dans", "Dans", 80), ("mode", "Mode", 160)):
            self.tree_next.heading(c, text=lab); self.tree_next.column(c, width=w, anchor="w")
        self.tree_next.pack(fill="x", padx=10, pady=4)
        mk_label(t, "Derniers traitements", "HI", "GUIB").pack(anchor="w", padx=12, pady=(8, 0))
        self.tree_recent = ttk.Treeview(t, columns=("ts", "regle", "fichier", "status", "msg"), show="headings", height=10)
        for c, lab, w in (("ts", "Quand", 140), ("regle", "Règle", 200), ("fichier", "Fichier", 180),
                          ("status", "État", 70), ("msg", "Détail", 400)):
            self.tree_recent.heading(c, text=lab); self.tree_recent.column(c, width=w, anchor="w")
        self.tree_recent.pack(fill="both", expand=True, padx=10, pady=4)

    def _build_rules(self):
        t = self.tab_rules
        bar = tk.Frame(t, bg=C["PANEL"], padx=6, pady=4); bar.pack(fill="x")
        for lab, cmd in (("Nouvelle…", self.new_rule), ("Modifier…", self.edit_rule),
                         ("Dupliquer", self.dup_rule), ("Activer/Désactiver", self.toggle_rule),
                         ("Haut", lambda: self.move_rule(-1)), ("Bas", lambda: self.move_rule(1)),
                         ("Supprimer", self.del_rule), ("Modèles…", self.templates)):
            mk_button(bar, lab, cmd).pack(side="left", padx=2)
        self.tree_rules = ttk.Treeview(t, columns=("actif", "nom", "iv", "actions", "note"), show="headings", height=18)
        for c, lab, w in (("actif", "On", 40), ("nom", "Nom", 280), ("iv", "Intervalle", 90),
                          ("actions", "Actions", 220), ("note", "Note", 300)):
            self.tree_rules.heading(c, text=lab); self.tree_rules.column(c, width=w, anchor="w")
        self.tree_rules.pack(fill="both", expand=True, padx=6, pady=6)
        self.tree_rules.bind("<Double-1>", lambda _e: self.edit_rule())

    def _build_folders(self):
        t = self.tab_folders
        bar = tk.Frame(t, bg=C["PANEL"], padx=6, pady=4); bar.pack(fill="x")
        for lab, cmd in (("Ajouter…", self.add_folder), ("Modifier…", self.edit_folder),
                         ("Activer/Pause", self.toggle_folder), ("Retirer", self.del_folder)):
            mk_button(bar, lab, cmd).pack(side="left", padx=2)
        self.tree_folders = ttk.Treeview(t, columns=("actif", "chemin", "iv", "evt", "note"), show="headings", height=14)
        for c, lab, w in (("actif", "On", 40), ("chemin", "Chemin", 420), ("iv", "Intervalle", 90),
                          ("evt", "Événementiel", 100), ("note", "Note", 220)):
            self.tree_folders.heading(c, text=lab); self.tree_folders.column(c, width=w, anchor="w")
        self.tree_folders.pack(fill="both", expand=True, padx=6, pady=6)
        self.tree_folders.bind("<Double-1>", lambda _e: self.edit_folder())

    def _build_log(self):
        t = self.tab_log
        bar = tk.Frame(t, bg=C["PANEL"], padx=6, pady=4); bar.pack(fill="x")
        self.v_log_filter = tk.StringVar(value="")
        mk_label(bar, "Filtrer", "DIM").pack(side="left")
        e = mk_entry(bar, self.v_log_filter, 30); e.pack(side="left", padx=6)
        e.bind("<KeyRelease>", lambda _e: self.refresh_log())
        mk_button(bar, "Rafraîchir", self.refresh_log).pack(side="left")
        mk_button(bar, "Ouvrir facteur.log", lambda: open_path(Paths.log())).pack(side="right")
        self.txt_log = tk.Text(t, bg=C["ENTRY_BG"], fg=C["ENTRY_FG"], insertbackground=C["HI"],
                               font=fnt("GMono"), wrap="word", relief="flat", highlightthickness=1,
                               highlightbackground=C["LINE"])
        vsb = ttk.Scrollbar(t, orient="vertical", command=self.txt_log.yview)
        self.txt_log.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y"); self.txt_log.pack(fill="both", expand=True, padx=6, pady=6)
        self.txt_log.tag_configure("OK", foreground=C["OK"])
        self.txt_log.tag_configure("REFUS", foreground=C["ERR"])
        self.txt_log.tag_configure("ERREUR", foreground=C["ERR"])
        self.txt_log.tag_configure("ALERTE", foreground=C["WARN"])
        self.txt_log.tag_configure("INFO", foreground=C["DIM"])

    def _build_remote(self):
        t = self.tab_remote
        sf = ScrollFrame(t); sf.pack(fill="both", expand=True)
        b = sf.inner
        mk_label(b, "Sécurité des commandes à distance", "HI", "GTitle").pack(anchor="w", padx=10, pady=8)
        mk_label(b, "Un fichier .padawan (JSON signé HMAC-SHA256) déposé dans un dossier surveillé "
                    "n'est exécuté que s'il est correctement signé, non expiré et jamais vu. "
                    "Les actions possibles sont limitées à une liste blanche. Aucune commande shell "
                    "arbitraire ne vient d'un .padawan.", "TEXT", "GUI",
                 wraplength=900, justify="left").pack(anchor="w", padx=10)
        rem = self.cfg.data["remote"]
        self.v_remote = tk.BooleanVar(value=bool(rem.get("actif", True)))
        mk_check(b, "Accepter les commandes à distance signées", self.v_remote,
                 cmd=self._save_remote_flags).pack(anchor="w", padx=10, pady=6)
        self.v_voix = tk.BooleanVar(value=bool(rem.get("lire_voix_haute", False)))
        mk_check(b, "Lire les messages à voix haute", self.v_voix,
                 cmd=self._save_remote_flags).pack(anchor="w", padx=10, pady=2)
        rowv = tk.Frame(b, bg=C["BG"]); rowv.pack(fill="x", padx=10, pady=2)
        mk_label(rowv, "Voix").pack(side="left")
        _voices = list_tts_voices()
        self._voix_vals = ["auto"] + [v["name"] for v in _voices]
        self._voix_labs = ["Auto (français en priorité)"] + [
            f'{v["name"]} ({v["lang"]})' for v in _voices
        ]
        _cur = str(rem.get("voix") or "auto")
        if _cur not in self._voix_vals:
            self._voix_vals.append(_cur)
            self._voix_labs.append(_cur)
        _idx = self._voix_vals.index(_cur) if _cur in self._voix_vals else 0
        self.v_voix_lab = tk.StringVar(value=self._voix_labs[_idx])
        self.cb_voix = ttk.Combobox(rowv, textvariable=self.v_voix_lab, values=self._voix_labs,
                                    state="readonly", width=36)
        self.cb_voix.pack(side="left", padx=6)
        self.cb_voix.bind("<<ComboboxSelected>>", lambda _e: self._save_remote_flags())
        mk_button(rowv, "Tester", self._test_voix).pack(side="left", padx=4)
        r = tk.Frame(b, bg=C["BG"]); r.pack(fill="x", padx=10, pady=4)
        mk_label(r, "Fenêtre d'expiration (secondes)").pack(side="left")
        self.v_expire = tk.StringVar(value=str(rem.get("expire_sec") or DEFAULT_EXPIRE_SEC))
        mk_entry(r, self.v_expire, 8).pack(side="left", padx=6)
        mk_button(r, "Appliquer", self._save_remote_flags).pack(side="left")
        mk_label(b, f"Empreinte de la clé : {self.keys.fingerprint()}", "DIM", "GSM").pack(anchor="w", padx=10, pady=4)
        mk_label(b, f"Fichier protégé DPAPI : {Paths.keyfile()}", "DIM", "GSM").pack(anchor="w", padx=10)
        br = tk.Frame(b, bg=C["BG"]); br.pack(fill="x", padx=10, pady=8)
        mk_button(br, "Cr\u00e9er / afficher ma cl\u00e9 de connexion", self.show_key_once, "accent",
                  tip="Après affichage, la clé ne sera plus révélable (régénération nécessaire)").pack(side="left", padx=2)
        mk_button(br, "Régénérer la clé…", self.regen_key, "danger").pack(side="left", padx=2)
        mk_button(br, "Créer une commande de test…", self.make_test_cmd).pack(side="left", padx=2)
        mk_label(b, "Actions de la liste blanche", "HI", "GUIB").pack(anchor="w", padx=10, pady=(12, 2))
        for a in REMOTE_ACTIONS:
            mk_label(b, f"• {a} — {REMOTE_LABELS.get(a, '')}", "TEXT", "GSM").pack(anchor="w", padx=20)
        mk_label(b, "Alias locaux (alias vers programme)", "HI", "GUIB").pack(anchor="w", padx=10, pady=(12, 2))
        self.txt_progs = tk.Text(b, height=5, bg=C["ENTRY_BG"], fg=C["ENTRY_FG"], font=fnt("GMono"),
                                 relief="flat", highlightthickness=1, highlightbackground=C["LINE"])
        self.txt_progs.pack(fill="x", padx=10)
        self.txt_progs.insert("1.0", json.dumps(rem.get("programmes_autorises") or {}, ensure_ascii=False, indent=1))
        mk_label(b, 'Format : {"backup": {"target": "C:\\\\...\\\\backup.bat", "args": "", "cwd": "C:\\\\..."}}',
                 "DIM", "GSM").pack(anchor="w", padx=10)
        mk_label(b, "Commandes nommées (ADMIN seulement : message admin signé)", "HI", "GUIB").pack(anchor="w", padx=10, pady=(12, 2))
        self.txt_noms = tk.Text(b, height=5, bg=C["ENTRY_BG"], fg=C["ENTRY_FG"], font=fnt("GMono"),
                                relief="flat", highlightthickness=1, highlightbackground=C["LINE"])
        self.txt_noms.pack(fill="x", padx=10)
        self.txt_noms.insert("1.0", json.dumps(rem.get("commandes_nommees") or {}, ensure_ascii=False, indent=1))
        mk_label(b, 'Format : {"backup": {"type": "cmd|ps1|exe", "target": "C:\\\\...\\\\backup.bat", "args": "", "cwd": ""}}',
                 "DIM", "GSM").pack(anchor="w", padx=10)
        mk_label(b, "Destinations pré-autorisées (nom → dossier)", "HI", "GUIB").pack(anchor="w", padx=10, pady=(12, 2))
        self.txt_dests = tk.Text(b, height=4, bg=C["ENTRY_BG"], fg=C["ENTRY_FG"], font=fnt("GMono"),
                                 relief="flat", highlightthickness=1, highlightbackground=C["LINE"])
        self.txt_dests.pack(fill="x", padx=10)
        self.txt_dests.insert("1.0", json.dumps(rem.get("destinations_autorisees") or {}, ensure_ascii=False, indent=1))
        mk_button(b, "Enregistrer alias / destinations", self._save_remote_maps, "accent").pack(anchor="w", padx=10, pady=8)
        mk_link(b, "Exemple PHP (à configurer sur ton serveur)", os.path.join(BASE, "facteur_commande_exemple.php"),
                ).pack(anchor="w", padx=10, pady=4)


    def _show_from_notify(self):
        try:
            self.deiconify()
            self.lift()
            try:
                self.state("normal")
            except tk.TclError:
                pass
            try:
                self.attributes("-topmost", True)
                self.after(800, lambda: self.attributes("-topmost", False))
            except tk.TclError:
                pass
            self.focus_force()
        except Exception:
            pass

    def _build_boites(self):
        t = self.tab_boites
        mk_label(t, "Boîtes SQL — pont PHP (aucun mot de passe MySQL sur ce PC)", "HI", "GTitle").pack(
            anchor="w", padx=12, pady=8)
        mk_label(t, "Facteur appelle ton facteur_boite.php en HTTPS. Les identifiants MySQL restent sur le serveur. "
                    "Exporte les pages web (clé HMAC incluse), dépose-les chez ton hébergeur, colle l'URL du pont ici.",
                 "TEXT", "GSM", wraplength=900, justify="left").pack(anchor="w", padx=12)
        bar = tk.Frame(t, bg=C["PANEL"], padx=6, pady=4)
        bar.pack(fill="x", padx=8, pady=6)
        for lab, cmd in (("Ajouter…", self.add_boite), ("Modifier…", self.edit_boite),
                         ("Activer/Pause", self.toggle_boite), ("Retirer", self.del_boite),
                         ("Tester le pont", self.test_boite), ("Créer les tables", self.schema_boite),
                         ("Exporter les pages web…", self.export_boite_web)):
            mk_button(bar, lab, cmd).pack(side="left", padx=2)
        self.tree_boites = ttk.Treeview(t, columns=("actif", "nom", "mode", "url", "iv"), show="headings", height=8)
        for c, lab, w in (("actif", "On", 40), ("nom", "Nom", 160), ("mode", "Mode", 70),
                          ("url", "URL du pont", 420), ("iv", "Intervalle", 80)):
            self.tree_boites.heading(c, text=lab)
            self.tree_boites.column(c, width=w, anchor="w")
        self.tree_boites.pack(fill="x", padx=8, pady=4)
        self.tree_boites.bind("<Double-1>", lambda _e: self.edit_boite())
        mk_label(t, "Commandes récentes (via le pont)", "HI", "GUIB").pack(anchor="w", padx=12, pady=(8, 0))
        self.txt_boites = tk.Text(t, height=12, bg=C["ENTRY_BG"], fg=C["ENTRY_FG"], font=fnt("GMono"),
                                  relief="flat", highlightthickness=1, highlightbackground=C["LINE"])
        self.txt_boites.pack(fill="both", expand=True, padx=8, pady=6)
        mk_button(t, "Rafraîchir la liste", self.refresh_boite_lists).pack(anchor="w", padx=12, pady=4)

    def refresh_boites(self):
        if not hasattr(self, "tree_boites"):
            return
        self.tree_boites.delete(*self.tree_boites.get_children())
        for b in self.cfg.boites():
            self.tree_boites.insert("", "end", iid=b["id"], values=(
                "✓" if b.get("actif") else "·", b.get("nom"), b.get("mode") or "pont",
                (b.get("pont_url") or "")[:80], b.get("intervalle")))

    def _sel_boite(self):
        sel = self.tree_boites.selection()
        if not sel:
            return None
        return self.cfg.boite_by_id(sel[0])

    def add_boite(self):
        self._edit_boite_dialog(None)

    def edit_boite(self):
        b = self._sel_boite()
        if b:
            self._edit_boite_dialog(b)

    def _edit_boite_dialog(self, boite):
        if boite_sql is None:
            messagebox.showwarning(APP_NAME, "Module facteur_boite.py introuvable.", parent=self)
            return
        d = Modal(self, "Boîte SQL (pont PHP)", 640, 360)
        b = dict(boite or boite_sql.default_boite())
        v_nom = tk.StringVar(value=b.get("nom") or "Boîte SQL")
        v_url = tk.StringVar(value=b.get("pont_url") or "")
        v_iv = tk.StringVar(value=str(b.get("intervalle") or 30))
        v_actif = tk.BooleanVar(value=bool(b.get("actif")))
        body = tk.Frame(d, bg=C["BG"], padx=12, pady=10)
        body.pack(fill="both", expand=True)
        mk_label(body, "Nom", "HI", "GUIB").pack(anchor="w")
        mk_entry(body, v_nom, 40).pack(fill="x")
        mk_label(body, "URL HTTPS du pont (facteur_boite.php)", "HI", "GUIB").pack(anchor="w", pady=(8, 0))
        mk_entry(body, v_url, 60).pack(fill="x")
        mk_label(body, "Aucun mot de passe MySQL ici — il reste dans facteur_boite_config.php sur le serveur.",
                 "DIM", "GSM").pack(anchor="w", pady=4)
        r = tk.Frame(body, bg=C["BG"])
        r.pack(fill="x", pady=6)
        mk_label(r, "Intervalle (s)").pack(side="left")
        mk_entry(r, v_iv, 8).pack(side="left", padx=6)
        mk_check(body, "Active", v_actif).pack(anchor="w")

        def save():
            try:
                iv = max(5, int(v_iv.get()))
            except ValueError:
                messagebox.showwarning(APP_NAME, "Intervalle invalide.", parent=d)
                return
            url = v_url.get().strip()
            if url and not url.lower().startswith("https://") and "localhost" not in url and "127.0.0.1" not in url:
                if not messagebox.askyesno(APP_NAME, "L'URL n'est pas en HTTPS. Continuer quand même ?", parent=d):
                    return
            b.update({"nom": v_nom.get().strip() or "Boîte SQL", "pont_url": url, "intervalle": iv,
                      "actif": v_actif.get(), "mode": "pont"})
            if not boite:
                b["id"] = uuid.uuid4().hex[:8]
                self.cfg.boites().append(b)
            else:
                for i, x in enumerate(self.cfg.boites()):
                    if x["id"] == b["id"]:
                        self.cfg.boites()[i] = b
                        break
            self.cfg.save()
            self.engine.next_boite[b["id"]] = 0
            self.refresh_boites()
            d.ok(True)

        bot = tk.Frame(d, bg=C["PANEL"], padx=8, pady=6)
        bot.pack(fill="x", side="bottom")
        mk_button(bot, "Annuler", d.cancel).pack(side="right", padx=4)
        mk_button(bot, "Enregistrer", save, "accent").pack(side="right")
        self.wait_window(d)

    def toggle_boite(self):
        b = self._sel_boite()
        if not b:
            return
        b["actif"] = not b.get("actif")
        self.cfg.save()
        self.refresh_boites()

    def del_boite(self):
        b = self._sel_boite()
        if not b:
            return
        if not messagebox.askyesno(APP_NAME, f"Retirer « {b.get('nom')} » ?", parent=self):
            return
        self.cfg.data["boites_sql"] = [x for x in self.cfg.boites() if x["id"] != b["id"]]
        self.cfg.save()
        self.refresh_boites()

    def test_boite(self):
        b = self._sel_boite()
        if not b or not b.get("pont_url"):
            messagebox.showinfo(APP_NAME, "Choisis une boîte avec une URL de pont.", parent=self)
            return
        try:
            msg = boite_sql.bridge_test(b["pont_url"], self.keys.load())
            messagebox.showinfo(APP_NAME, msg, parent=self)
        except Exception as ex:
            messagebox.showerror(APP_NAME, str(ex), parent=self)

    def schema_boite(self):
        b = self._sel_boite()
        if not b or not b.get("pont_url"):
            messagebox.showinfo(APP_NAME, "Choisis une boîte avec une URL de pont.", parent=self)
            return
        try:
            msg = boite_sql.bridge_create_schema(b["pont_url"], self.keys.load())
            messagebox.showinfo(APP_NAME, msg, parent=self)
        except Exception as ex:
            messagebox.showerror(APP_NAME, str(ex), parent=self)

    def export_boite_web(self):
        if boite_sql is None:
            messagebox.showwarning(APP_NAME, "Module facteur_boite.py introuvable.", parent=self)
            return
        default = os.path.join(os.path.dirname(BASE), "Facteur", "web")
        dest = filedialog.askdirectory(parent=self, title="Dossier d'export des pages web Facteur",
                                       initialdir=default if os.path.isdir(os.path.dirname(default)) else BASE)
        if not dest:
            return
        try:
            written = boite_sql.export_web_pack(self.keys.load(), dest)
            messagebox.showinfo(
                APP_NAME,
                f"Pages exportées dans :\n{dest}\n\n"
                f"Page TEST : {written.get('_test_page')}\n"
                f"Pont : facteur_boite.php\n"
                f"Clé : facteur_cle.php\n\n"
                "Remplis seulement $LOCAL_DB_PASS dans facteur_boite_config.php, "
                "dépose le dossier en HTTPS, puis colle l'URL du pont ici.",
                parent=self)
            jlog("OK", "boite", f"export web → {dest} ({written.get('_test_page')})")
        except Exception as ex:
            messagebox.showerror(APP_NAME, str(ex), parent=self)

    def refresh_boite_lists(self):
        b = self._sel_boite()
        self.txt_boites.configure(state="normal")
        self.txt_boites.delete("1.0", "end")
        if not b or not b.get("pont_url"):
            self.txt_boites.insert("end", "Sélectionne une boîte active avec URL de pont.\n")
            self.txt_boites.configure(state="disabled")
            return
        try:
            r = boite_sql.bridge_call(b["pont_url"], self.keys.load(), "list_recent", {"limit": 25})
            self.txt_boites.insert("end", "=== incoming ===\n")
            for row in r.get("incoming") or []:
                self.txt_boites.insert(
                    "end",
                    f"{row.get('id')} {row.get('statut')} {row.get('action')} "
                    f"{str(row.get('uuid',''))[:8]}… {row.get('created_at')}\n")
            self.txt_boites.insert("end", "\n=== traites ===\n")
            for row in r.get("traites") or []:
                self.txt_boites.insert(
                    "end",
                    f"{row.get('statut')} {row.get('action')} {row.get('traite_at')} {row.get('resultat')}\n")
        except Exception as ex:
            self.txt_boites.insert("end", f"Erreur : {ex}\n")
        self.txt_boites.configure(state="disabled")


    def _build_opts(self):
        t = self.tab_opts
        lim = self.cfg.data["limites"]
        mk_label(t, "Limites de charge (ne pas saturer le PC)", "HI", "GTitle").pack(anchor="w", padx=12, pady=10)
        self.v_maxp = tk.StringVar(value=str(lim.get("max_par_passe") or 50))
        self.v_low = tk.BooleanVar(value=bool(lim.get("priorite_basse", True)))
        self.v_bat = tk.BooleanVar(value=bool(lim.get("pause_batterie_faible")))
        self.v_seuil_bat = tk.StringVar(value=str(lim.get("seuil_batterie") or 20))
        self.v_cpu = tk.BooleanVar(value=bool(lim.get("pause_cpu_occupe")))
        self.v_seuil_cpu = tk.StringVar(value=str(lim.get("seuil_cpu") or 85))
        self.v_notif = tk.BooleanVar(value=bool(self.cfg.data.get("notifications", True)))
        r = tk.Frame(t, bg=C["BG"]); r.pack(fill="x", padx=12, pady=4)
        mk_label(r, "Max fichiers par passe globale").pack(side="left")
        mk_entry(r, self.v_maxp, 8).pack(side="left", padx=6)
        mk_check(t, "Priorité basse pour les processus lancés", self.v_low).pack(anchor="w", padx=12)
        mk_check(t, "Pause automatique si batterie faible", self.v_bat).pack(anchor="w", padx=12)
        r2 = tk.Frame(t, bg=C["BG"]); r2.pack(fill="x", padx=28, pady=2)
        mk_label(r2, "Seuil batterie (%)").pack(side="left"); mk_entry(r2, self.v_seuil_bat, 6).pack(side="left", padx=4)
        mk_check(t, "Pause automatique si CPU occupé", self.v_cpu).pack(anchor="w", padx=12)
        r3 = tk.Frame(t, bg=C["BG"]); r3.pack(fill="x", padx=28, pady=2)
        mk_label(r3, "Seuil CPU (%)").pack(side="left"); mk_entry(r3, self.v_seuil_cpu, 6).pack(side="left", padx=4)
        mk_check(t, "Notifications Windows", self.v_notif).pack(anchor="w", padx=12, pady=6)
        mk_button(t, "Enregistrer les options", self._save_opts, "accent").pack(anchor="w", padx=12, pady=10)
        adv = tk.Frame(t, bg=C["CARD"], padx=12, pady=10, highlightthickness=1, highlightbackground=C["LINE"])
        adv.pack(fill="x", padx=12, pady=(4, 10))
        self.v_avance = tk.BooleanVar(value=bool(self.cfg.data.get("mode_avance")))
        mk_check(adv, "Mode avanc\u00e9 (commandes \u00e0 distance et bo\u00eetes SQL)", self.v_avance, C["CARD"],
                 cmd=self._toggle_advanced).pack(anchor="w")
        mk_label(adv, "Tu n'en as pas besoin pour ranger tes fichiers : laisse d\u00e9coch\u00e9 et Facteur reste simple. "
                      "Ce mode sert seulement \u00e0 piloter ce PC depuis ton site web. Tu peux l'activer ou le "
                      "d\u00e9sactiver quand tu veux, rien n'est perdu.", "DIM", "GSM", bg=C["CARD"],
                 wraplength=760, justify="left").pack(anchor="w", pady=(4, 0))
        mk_label(t, f"Watchdog : {'disponible' if WATCHDOG else 'absent (sondage uniquement — pip install watchdog)'}",
                 "DIM" if WATCHDOG else "WARN", "GSM").pack(anchor="w", padx=12)
        mk_label(t, f"Données : {Paths.data}", "DIM", "GSM").pack(anchor="w", padx=12)

    # ---- rafraichissement ---------------------------------------------
    def _tick(self):
        self.refresh_dash()
        self.after(2000, self._tick)

    def refresh_all(self):
        self.refresh_rules(); self.refresh_folders(); self.refresh_log(); self.refresh_boites(); self.refresh_dash()

    def refresh_dash(self):
        s = self.engine.stats
        for k in ("traites", "refuses", "erreurs", "ignores"):
            if k in self.stat_labs:
                self.stat_labs[k].configure(text=str(s.get(k, 0)))
        with self.engine.lock:
            n_att = len(self.engine.pending)
            recent = list(self.engine.recent[-40:])
        self.stat_labs["attente"].configure(text=str(n_att))
        pause = "⏸ PAUSE" if self.cfg.data.get("pause_globale") else "▶ Actif"
        wd = "watchdog" if self.engine.observer else "sondage"
        self.lbl_status.configure(text=f"{pause}  ·  {wd}  ·  {len(self.cfg.folders())} dossier(s)  ·  "
                                       f"{sum(1 for r in self.cfg.rules() if r.get('actif'))} règle(s) active(s)")
        self.lbl_foot.configure(text=f"Données {Paths.data}  ·  journal {Paths.log()}")
        self.tree_next.delete(*self.tree_next.get_children())
        for e in self.engine.next_checks():
            self.tree_next.insert("", "end", values=(e["kind"], e["nom"], f"{e['dans']} s", e["mode"]))
        self.tree_recent.delete(*self.tree_recent.get_children())
        for e in reversed(recent):
            self.tree_recent.insert("", "end", values=(e["ts"], e["regle"], e["fichier"], e["status"], e["msg"]))

    def refresh_rules(self):
        self.tree_rules.delete(*self.tree_rules.get_children())
        for r in self.cfg.rules():
            acts = ", ".join(a.get("type", "?") for a in r.get("actions") or [])
            iv = r.get("intervalle") or "—"
            self.tree_rules.insert("", "end", iid=r["id"],
                                   values=("✓" if r.get("actif") else "·", r.get("nom"), iv, acts, (r.get("note") or "")[:80]))

    def refresh_folders(self):
        self.tree_folders.delete(*self.tree_folders.get_children())
        for f in self.cfg.folders():
            self.tree_folders.insert("", "end", iid=f["id"],
                                     values=("✓" if f.get("actif") else "·", f.get("chemin"), f.get("intervalle"),
                                             "oui" if f.get("evenementiel") else "non", f.get("note") or ""))

    def refresh_log(self):
        filt = (self.v_log_filter.get() or "").lower()
        self.txt_log.configure(state="normal")
        self.txt_log.delete("1.0", "end")
        with JOURNAL.lock:
            items = list(JOURNAL.items[-800:])
        for e in items:
            line = f"{e['ts']} | {e['niveau']} | {e['cat']} | {e['msg']}\n"
            if filt and filt not in line.lower():
                continue
            self.txt_log.insert("end", line, e["niveau"] if e["niveau"] in ("OK", "REFUS", "ERREUR", "ALERTE", "INFO") else "INFO")
        self.txt_log.see("end")
        self.txt_log.configure(state="disabled")

    def _on_log(self, _e):
        if self.nb.index(self.nb.select()) == self.nb.tabs().index(str(self.tab_log)):
            self.refresh_log()

    # ---- actions UI ---------------------------------------------------
    def save_cfg(self):
        self.cfg.save()
        jlog("OK", "config", "configuration enregistrée")

    def toggle_pause(self):
        self.cfg.data["pause_globale"] = self.v_pause.get()
        self.cfg.save()
        jlog("ALERTE", "moteur", "PAUSE" if self.v_pause.get() else "reprise")

    def change_theme(self):
        k = self.v_theme.get()
        if k not in THEMES:
            return
        self.cfg.data["theme"] = k
        self.cfg.save()
        C.clear(); C.update(THEMES[k])
        for w in list(self.winfo_children()):
            w.destroy()
        self._build()
        self.refresh_all()

    def _sel_rule(self) -> Optional[Dict[str, Any]]:
        sel = self.tree_rules.selection()
        if not sel:
            return None
        return next((r for r in self.cfg.rules() if r["id"] == sel[0]), None)

    def _sel_folder(self) -> Optional[Dict[str, Any]]:
        sel = self.tree_folders.selection()
        if not sel:
            return None
        return self.cfg.folder_by_id(sel[0])

    def new_rule(self):
        d = RuleDialog(self, self, None)
        self.wait_window(d)
        if d.result:
            self.cfg.rules().append(d.result)
            self.cfg.save(); self.refresh_rules(); jlog("OK", "regle", f"créée : {d.result['nom']}")

    def edit_rule(self):
        r = self._sel_rule()
        if not r:
            return
        d = RuleDialog(self, self, r)
        self.wait_window(d)
        if d.result:
            for i, x in enumerate(self.cfg.rules()):
                if x["id"] == r["id"]:
                    self.cfg.rules()[i] = d.result
                    break
            self.cfg.save(); self.refresh_rules()

    def dup_rule(self):
        r = self._sel_rule()
        if not r:
            return
        c = json.loads(json.dumps(r))
        c["id"] = uuid.uuid4().hex[:8]
        c["nom"] = r["nom"] + " (copie)"
        c["actif"] = False
        self.cfg.rules().append(c)
        self.cfg.save(); self.refresh_rules()

    def toggle_rule(self):
        r = self._sel_rule()
        if not r:
            return
        r["actif"] = not r.get("actif")
        self.cfg.save(); self.refresh_rules()

    def move_rule(self, delta: int):
        r = self._sel_rule()
        if not r:
            return
        lst = self.cfg.rules()
        i = next(i for i, x in enumerate(lst) if x["id"] == r["id"])
        j = i + delta
        if 0 <= j < len(lst):
            lst[i], lst[j] = lst[j], lst[i]
            self.cfg.save(); self.refresh_rules()
            self.tree_rules.selection_set(r["id"])

    def del_rule(self):
        r = self._sel_rule()
        if not r:
            return
        if any(a.get("type") == "commande_signee" for a in r.get("actions") or []):
            if not messagebox.askyesno(APP_NAME, "C'est la règle des commandes signées. Supprimer quand même ?", parent=self):
                return
        elif not messagebox.askyesno(APP_NAME, f"Supprimer « {r['nom']} » ?", parent=self):
            return
        self.cfg.data["regles"] = [x for x in self.cfg.rules() if x["id"] != r["id"]]
        self.cfg.save(); self.refresh_rules()

    def templates(self):
        d = Modal(self, "Bibliothèque de modèles", 640, 420)
        lb = tk.Listbox(d, bg=C["ENTRY_BG"], fg=C["ENTRY_FG"], font=fnt("GUI"), selectbackground=C["SEL"],
                        selectforeground=C["ON_SEL"], activestyle="none")
        lb.pack(fill="both", expand=True, padx=10, pady=10)
        tpls = rule_templates()
        for t in tpls:
            lb.insert("end", f"{t['nom']} — {t.get('note', '')[:60]}")
        def add():
            i = lb.curselection()
            if not i:
                return
            r = json.loads(json.dumps(tpls[i[0]]))
            r["id"] = uuid.uuid4().hex[:8]
            r["actif"] = False
            self.cfg.rules().append(r)
            self.cfg.save(); self.refresh_rules()
            d.ok(True)
            messagebox.showinfo(APP_NAME, f"Modèle « {r['nom']} » ajouté (désactivé). Active-le quand tu veux.", parent=self)
        bot = tk.Frame(d, bg=C["PANEL"], padx=8, pady=6); bot.pack(fill="x", side="bottom")
        mk_button(bot, "Fermer", d.cancel).pack(side="right", padx=4)
        mk_button(bot, "Ajouter (désactivé)", add, "accent").pack(side="right")
        self.wait_window(d)

    def add_folder(self):
        d = FolderDialog(self); self.wait_window(d)
        if d.result:
            f = d.result; f["id"] = uuid.uuid4().hex[:8]
            self.cfg.folders().append(f)
            self.cfg.save(); self.engine.reload(); self.refresh_folders()

    def edit_folder(self):
        f = self._sel_folder()
        if not f:
            return
        d = FolderDialog(self, f); self.wait_window(d)
        if d.result:
            f.update(d.result)
            self.cfg.save(); self.engine.reload(); self.refresh_folders()

    def toggle_folder(self):
        f = self._sel_folder()
        if not f:
            return
        f["actif"] = not f.get("actif")
        self.cfg.save(); self.engine.reload(); self.refresh_folders()

    def del_folder(self):
        f = self._sel_folder()
        if not f:
            return
        if len(self.cfg.folders()) <= 1:
            messagebox.showwarning(APP_NAME, "Il faut au moins un dossier.", parent=self); return
        if not messagebox.askyesno(APP_NAME, f"Retirer la surveillance de\n{f['chemin']} ?", parent=self):
            return
        self.cfg.data["dossiers"] = [x for x in self.cfg.folders() if x["id"] != f["id"]]
        self.cfg.save(); self.engine.reload(); self.refresh_folders()

    def export_rules(self):
        p = filedialog.asksaveasfilename(parent=self, defaultextension=".json",
                                         initialfile="facteur_regles.json", filetypes=[("JSON", "*.json")])
        if not p:
            return
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"paquet": {"nom": os.path.splitext(os.path.basename(p))[0], "auteur": os.environ.get("USERNAME", ""), "version": 1},
                       "regles": [r for r in self.cfg.rules() if not any(isinstance(a, dict) and a.get("type") == "commande_signee" for a in r.get("actions", []))]},
                      f, ensure_ascii=False, indent=1)
        messagebox.showinfo(APP_NAME, f"Exporté : {p}", parent=self)

    def import_rules(self):
        """Paquet de regles (.json) : apercu, regles DESACTIVEES, jamais de commande a distance, rien n'est execute."""
        pk = os.path.join(os.path.dirname(os.path.abspath(__file__)), "paquets")
        p = filedialog.askopenfilename(parent=self, title="Importer un paquet de r\u00e8gles",
                                       initialdir=pk if os.path.isdir(pk) else None,
                                       filetypes=[("Paquet Facteur", "*.json")])
        if not p:
            return
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            rules = data.get("regles") if isinstance(data, dict) else data
            if not isinstance(rules, list):
                raise ValueError("aucune liste de r\u00e8gles dans ce fichier")
            meta = data.get("paquet", {}) if isinstance(data, dict) else {}
            ok, refus, risque = [], [], []
            for r in rules:
                if not isinstance(r, dict) or not isinstance(r.get("actions", []), list):
                    continue
                types = [str((a or {}).get("type", "")) for a in r.get("actions", []) if isinstance(a, dict)]
                if "commande_signee" in types or r.get("masque") == "*.padawan":
                    refus.append(str(r.get("nom", "?"))); continue
                if "executer" in types:
                    risque.append(str(r.get("nom", "?")))
                ok.append(r)
            if not ok:
                messagebox.showinfo(APP_NAME, "Aucune r\u00e8gle importable dans ce paquet.", parent=self); return
            txt = (f"Paquet : {meta.get('nom') or os.path.basename(p)}\n" + (f"{meta.get('description')}\n" if meta.get("description") else "")
                   + "\n" + "\n".join("  \u2022 " + str(r.get("nom", "?")) for r in ok[:25])
                   + (f"\n\n\u2139 Lancent une commande : {', '.join(risque)}" if risque else "")
                   + (f"\nLaiss\u00e9es de c\u00f4t\u00e9 (commandes \u00e0 distance) : {', '.join(refus)}" if refus else "")
                   + "\n\nLes r\u00e8gles arrivent en pause : tu les actives quand tu veux. Importer ?")
            if not messagebox.askyesno(APP_NAME, txt, parent=self):
                return
            tag = meta.get("nom") or os.path.splitext(os.path.basename(p))[0]
            for r in ok:
                base = _rule(str(r.get("nom") or "R\u00e8gle import\u00e9e"), False)
                base.update({k: v for k, v in r.items() if k in base and k not in ("id", "actif", "dossiers")})
                for a in base.get("actions", []):
                    if isinstance(a, dict) and isinstance(a.get("dest"), str):
                        a["dest"] = os.path.expandvars(a["dest"])
                base["id"] = uuid.uuid4().hex[:8]; base["actif"] = False
                base["note"] = (f"[paquet : {tag}] " + str(base.get("note") or "")).strip()
                self.cfg.rules().append(base)
            self.cfg.save(); self.refresh_rules()
            jlog("INFO", "import", f"paquet {p} : {len(ok)} r\u00e8gle(s) (d\u00e9sactiv\u00e9es), {len(refus)} refus\u00e9e(s)")
            messagebox.showinfo(APP_NAME, f"{len(ok)} r\u00e8gle(s) import\u00e9e(s), en pause.\nJette un \u0153il puis coche \u00ab active \u00bb.", parent=self)
        except Exception as ex:
            messagebox.showerror(APP_NAME, str(ex), parent=self)

    def _save_opts(self):
        try:
            self.cfg.data["limites"].update({
                "max_par_passe": max(1, int(self.v_maxp.get())),
                "priorite_basse": self.v_low.get(),
                "pause_batterie_faible": self.v_bat.get(),
                "seuil_batterie": max(1, int(self.v_seuil_bat.get())),
                "pause_cpu_occupe": self.v_cpu.get(),
                "seuil_cpu": max(1, min(100, int(self.v_seuil_cpu.get()))),
            })
            self.cfg.data["notifications"] = self.v_notif.get()
            self.cfg.save()
            messagebox.showinfo(APP_NAME, "Options enregistrées.", parent=self)
        except ValueError:
            messagebox.showwarning(APP_NAME, "Nombre invalide.", parent=self)

    def _save_remote_flags(self):
        try:
            self.cfg.data["remote"]["actif"] = self.v_remote.get()
            self.cfg.data["remote"]["lire_voix_haute"] = bool(self.v_voix.get())
            try:
                lab = self.v_voix_lab.get()
                if hasattr(self, "_voix_labs") and lab in self._voix_labs:
                    self.cfg.data["remote"]["voix"] = self._voix_vals[self._voix_labs.index(lab)]
                else:
                    self.cfg.data["remote"]["voix"] = "auto"
            except Exception:
                self.cfg.data["remote"].setdefault("voix", "auto")
            self.cfg.data["remote"]["expire_sec"] = max(60, int(self.v_expire.get()))
            self.cfg.save()
        except ValueError:
            messagebox.showwarning(APP_NAME, "Expiration invalide.", parent=self)

    def _test_voix(self):
        try:
            self._save_remote_flags()
        except Exception:
            pass
        v = str((self.cfg.data.get("remote") or {}).get("voix") or "auto")
        if speak("Bonjour Marc", voice=v):
            try:
                notify("Facteur", "Voix testée", self.cfg)
            except Exception:
                pass
        else:
            messagebox.showwarning(APP_NAME, "Impossible de lire le message test.", parent=self)

    def _save_remote_maps(self):
        try:
            self.cfg.data["remote"]["programmes_autorises"] = json.loads(self.txt_progs.get("1.0", "end"))
            self.cfg.data["remote"]["destinations_autorisees"] = json.loads(self.txt_dests.get("1.0", "end"))
            self.cfg.data["remote"]["commandes_nommees"] = json.loads(self.txt_noms.get("1.0", "end"))
            self.cfg.save()
            messagebox.showinfo(APP_NAME, "Alias et destinations enregistrés.", parent=self)
        except Exception as ex:
            messagebox.showerror(APP_NAME, f"JSON invalide : {ex}", parent=self)

    def _apply_advanced_tabs(self):
        on = bool(self.cfg.data.get("mode_avance"))
        for tab in (self.tab_remote, self.tab_boites):
            try:
                if on:
                    self.nb.add(tab)
                else:
                    self.nb.hide(tab)
            except tk.TclError:
                pass
        if on:  # garder l'ordre : avant Options
            try:
                self.nb.insert(self.tab_opts, self.tab_remote); self.nb.insert(self.tab_opts, self.tab_boites)
            except tk.TclError:
                pass

    def _toggle_advanced(self):
        on = bool(self.v_avance.get())
        self.cfg.data["mode_avance"] = on
        self.cfg.save()
        self._apply_advanced_tabs()
        jlog("INFO", "options", "mode avanc\u00e9 " + ("activ\u00e9" if on else "d\u00e9sactiv\u00e9"))
        if on:
            messagebox.showinfo(APP_NAME, "Mode avanc\u00e9 activ\u00e9 : les onglets \u00ab Commandes \u00e0 distance \u00bb "
                                "et \u00ab Bo\u00eetes SQL \u00bb sont visibles.\n\nRien ne change tant que tu ne cr\u00e9es pas "
                                "ta cl\u00e9 de connexion (bouton dans l'onglet Commandes \u00e0 distance).", parent=self)

    # ---- assistant « Ma premiere regle » -----------------------------
    WIZ_FILES = [("pdf", "\U0001f4c4 Les PDF", {"extensions": ["pdf"]}),
                 ("img", "\U0001f5bc Les images (jpg, png\u2026)", {"extensions": ["jpg", "jpeg", "png", "gif", "webp", "bmp", "heic"]}),
                 ("vid", "\U0001f3ac Les vid\u00e9os", {"extensions": ["mp4", "mkv", "webm", "mov", "avi", "m4v"]}),
                 ("old", "\U0001f570 Les vieux fichiers (plus de 30 jours)", {"masque": "*", "age_min": 30 * 86400}),
                 ("all", "\U0001f4e6 Tous les fichiers", {"masque": "*"})]

    def _wiz_rule(self, folder, files_key, action_key, dest, days):
        kw = dict(next(k for c, _l, k in self.WIZ_FILES if c == files_key))
        if action_key == "ranger":
            acts = [{"type": "deplacer", "dest": dest, "par_type": False}]
            verb = "ranger dans " + (os.path.basename(dest.rstrip("\\/")) or dest)
        elif action_key == "grimoire":
            acts = [{"type": "grimoire", "sujet": "\u00c0 classer"}]; verb = "envoyer au Grimoire"
        elif action_key == "archiveur":
            acts = [{"type": "archiveur"}]; verb = "envoyer \u00e0 l'Archiveur"
        else:
            kw["age_min"] = max(1, int(days)) * 86400
            acts = [{"type": "notifier", "message": "Rang\u00e9 dans _Trait\u00e9s : {nom_ext}"}]
            verb = f"mettre de c\u00f4t\u00e9 (_Trait\u00e9s) apr\u00e8s {int(days)} jours"
        lab = next(l for c, l, _k in self.WIZ_FILES if c == files_key).split(" ", 1)[1]
        r = _rule(f"{lab} \u2192 {verb}", False, actions=acts, intervalle=120,
                  note="Cr\u00e9\u00e9e avec l'assistant \u00ab Ma premi\u00e8re r\u00e8gle \u00bb.", **kw)
        if folder:
            r["dossiers"] = [folder["id"]]
        return r

    def _wiz_preview(self, rule, folder, limit=40):
        out = []
        base = (folder or {}).get("chemin") or ""
        if not os.path.isdir(base):
            return out
        try:
            names = sorted(os.listdir(base))[:2000]
        except OSError:
            return out
        for n in names:
            p = os.path.join(base, n)
            if not os.path.isfile(p):
                continue
            try:
                ok, _w = match_rule(rule, p, (folder or {}).get("id", ""))
            except Exception:
                ok = False
            if ok:
                out.append(n)
                if len(out) >= limit:
                    break
        return out

    def first_rule_wizard(self):
        folders = [f for f in self.cfg.folders() if f.get("chemin")]
        d = Modal(self, "Ma premi\u00e8re r\u00e8gle \u2014 3 petites \u00e9tapes", 760, 600)
        body = tk.Frame(d, bg=C["BG"], padx=16, pady=10); body.pack(fill="both", expand=True)
        v_folder = tk.StringVar(value=(folders[0]["id"] if folders else ""))
        v_files = tk.StringVar(value="pdf"); v_act = tk.StringVar(value="ranger")
        v_dest = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "Documents", "Rang\u00e9 par Facteur"))
        v_days = tk.StringVar(value="30")
        step = [0]

        def clear():
            for w in body.winfo_children():
                w.destroy()

        def title(txt, sub):
            mk_label(body, txt, "HI", "GTitle").pack(anchor="w")
            mk_label(body, sub, "DIM", "GUI", wraplength=700, justify="left").pack(anchor="w", pady=(2, 10))

        def radio(var, val, text):
            tk.Radiobutton(body, text=text, variable=var, value=val, bg=C["BG"], fg=C["FG"], selectcolor=C["ENTRY_BG"],
                           activebackground=C["BG"], activeforeground=C["HI"], font=fnt("GUI"), anchor="w"
                           ).pack(anchor="w", pady=2)

        def show():
            clear()
            if step[0] == 0:
                title("1/3 \u00b7 Quel dossier surveiller ?", "Facteur regarde ce dossier et s'occupe des nouveaux fichiers. "
                      "T\u00e9l\u00e9chargements est le bon choix pour commencer.")
                for f in folders:
                    radio(v_folder, f["id"], f"\U0001f4c1 {f.get('note') or os.path.basename(f['chemin'])}  \u2014  {f['chemin']}")
                if not folders:
                    mk_label(body, "Aucun dossier surveill\u00e9 : ajoute-en un dans l'onglet Dossiers.", "WARN").pack(anchor="w")
            elif step[0] == 1:
                title("2/3 \u00b7 Quels fichiers ?", "Choisis le genre de fichiers dont Facteur doit s'occuper.")
                for c, l, _k in self.WIZ_FILES:
                    radio(v_files, c, l)
            elif step[0] == 2:
                title("3/3 \u00b7 Qu'est-ce que je fais avec ?", "Rien n'est effac\u00e9 : au pire, un fichier est mis de c\u00f4t\u00e9 dans _Trait\u00e9s.")
                radio(v_act, "ranger", "\U0001f4c2 Les ranger dans un dossier")
                r = tk.Frame(body, bg=C["BG"]); r.pack(fill="x", padx=26)
                mk_entry(r, v_dest, 60).pack(side="left", fill="x", expand=True)
                mk_button(r, "Choisir\u2026", lambda: v_dest.set(filedialog.askdirectory(parent=d) or v_dest.get())).pack(side="left", padx=4)
                radio(v_act, "grimoire", "\U0001f4d6 Les envoyer au Grimoire (sujet \u00ab \u00c0 classer \u00bb)")
                radio(v_act, "archiveur", "\U0001f3ac Les envoyer \u00e0 l'Archiveur")
                radio(v_act, "traites", "\U0001f9f9 Les mettre de c\u00f4t\u00e9 (_Trait\u00e9s) apr\u00e8s quelques jours")
                r2 = tk.Frame(body, bg=C["BG"]); r2.pack(fill="x", padx=26)
                mk_label(r2, "apr\u00e8s").pack(side="left"); mk_entry(r2, v_days, 5).pack(side="left", padx=4); mk_label(r2, "jours").pack(side="left")
            else:
                rule = build()
                folder = next((f for f in folders if f["id"] == v_folder.get()), None)
                files = self._wiz_preview(rule, folder)
                title("Aper\u00e7u \u2014 voici ce qui se passerait", f"R\u00e8gle : {rule['nom']}")
                txt = tk.Text(body, height=14, bg=C["ENTRY_BG"], fg=C["FG"], relief="flat", font=fnt("GUI"))
                txt.pack(fill="both", expand=True)
                if files:
                    txt.insert("end", f"{len(files)} fichier(s) d\u00e9j\u00e0 l\u00e0 correspondent (aper\u00e7u, rien n'est touch\u00e9) :\n\n")
                    for n in files:
                        txt.insert("end", "  \u2022 " + n + "\n")
                else:
                    txt.insert("end", "Aucun fichier actuel ne correspond. Les prochains qui arriveront seront trait\u00e9s.\n")
                txt.insert("end", "\nFacteur s'occupe des NOUVEAUX fichiers d\u00e8s que la r\u00e8gle est active.")
                txt.configure(state="disabled")
            nav()

        def build():
            folder = next((f for f in folders if f["id"] == v_folder.get()), None)
            try:
                days = int(v_days.get() or 30)
            except ValueError:
                days = 30
            return self._wiz_rule(folder, v_files.get(), v_act.get(), v_dest.get().strip(), days)

        def finish(activate):
            rule = build(); rule["actif"] = bool(activate)
            self.cfg.rules().append(rule); self.cfg.save(); self.refresh_rules()
            jlog("INFO", "assistant", f"r\u00e8gle cr\u00e9\u00e9e : {rule['nom']} ({'active' if activate else 'en pause'})")
            d.ok(rule)
            messagebox.showinfo(APP_NAME, ("C'est parti ! " if activate else "R\u00e8gle enregistr\u00e9e en pause. ")
                                + f"\u00ab {rule['nom']} \u00bb\nTu peux la modifier dans l'onglet R\u00e8gles.", parent=self)

        bar = tk.Frame(d, bg=C["PANEL"], padx=10, pady=8); bar.pack(fill="x", side="bottom")

        def nav():
            for w in bar.winfo_children():
                w.destroy()
            mk_button(bar, "Annuler", d.cancel, "ghost").pack(side="left")
            if step[0] < 3:
                mk_button(bar, "Suivant \u2192" if step[0] < 2 else "Voir l'aper\u00e7u \u2192", lambda: go(1), "accent").pack(side="right", padx=4)
            else:
                mk_button(bar, "\u2714 Cr\u00e9er et activer", lambda: finish(True), "accent").pack(side="right", padx=4)
                mk_button(bar, "Cr\u00e9er en pause", lambda: finish(False)).pack(side="right", padx=4)
            if step[0] > 0:
                mk_button(bar, "\u2190 Retour", lambda: go(-1)).pack(side="right", padx=4)

        def go(k):
            step[0] = max(0, min(3, step[0] + k)); show()
        self._wiz = {"dialog": d, "go": go, "finish": finish, "vars": (v_folder, v_files, v_act, v_dest, v_days)}
        show()
        if not getattr(self, "readonly_test", False) and not getattr(self, "_wiz_nowait", False):
            self.wait_window(d)

    def show_key_once(self):
        if not self.keys.exists():
            if not messagebox.askyesno(APP_NAME, "Cr\u00e9er ta cl\u00e9 de connexion ?\n\nElle permet \u00e0 ton site web "
                                       "d'envoyer des commandes \u00e0 ce PC. Tu la colles une fois dans ta page web, "
                                       "c'est tout.", parent=self):
                return
            self.keys.create()
        hexkey = self.keys.reveal_once()
        if hexkey is None:
            messagebox.showinfo(APP_NAME,
                "La clé a déjà été affichée.\n\n"
                "Empreinte : " + self.keys.fingerprint() + "\n"
                "Fichier : " + Paths.keyfile() + "\n\n"
                "Pour en obtenir une nouvelle (invalide l'ancienne sur ton site), "
                "utilise « Régénérer la clé ».", parent=self)
            return
        d = Modal(self, "Ta cl\u00e9 de connexion Facteur", 700, 320)
        mk_label(d, "Copie cette cl\u00e9 dans ta page web (c\u00f4t\u00e9 serveur). Facteur ne la r\u00e9affiche pas ensuite ; "
                    "si tu la perds, tu pourras simplement en cr\u00e9er une nouvelle.", "FG", "GUIB",
                 wraplength=660, justify="left").pack(anchor="w", padx=12, pady=8)
        txt = tk.Text(d, height=4, bg=C["ENTRY_BG"], fg=C["HI"], font=fnt("GMono"), relief="flat",
                      highlightthickness=1, highlightbackground=C["LINE"])
        txt.pack(fill="x", padx=12); txt.insert("1.0", hexkey); txt.configure(state="disabled")
        def copy():
            self.clipboard_clear(); self.clipboard_append(hexkey)
            messagebox.showinfo(APP_NAME, "Clé copiée dans le presse-papiers.", parent=d)
        bot = tk.Frame(d, bg=C["PANEL"], padx=8, pady=6); bot.pack(fill="x", side="bottom")
        mk_button(bot, "Fermer", d.cancel).pack(side="right", padx=4)
        mk_button(bot, "Copier", copy, "accent").pack(side="right")
        self.wait_window(d)

    def regen_key(self):
        if not messagebox.askyesno(APP_NAME,
                "Régénérer la clé ?\n\nL'ancienne ne marchera plus : tu devras mettre "
                "la nouvelle dans ta page PHP.", parent=self):
            return
        self.keys.regenerate()
        messagebox.showinfo(APP_NAME, "Nouvelle cl\u00e9 cr\u00e9\u00e9e. La voici pour ta page web.", parent=self)
        self.show_key_once()

    def make_test_cmd(self):
        d = Modal(self, "Créer une commande de test", 640, 420)
        v_act = tk.StringVar(value="notifier")
        mk_label(d, "Action", "HI", "GUIB").pack(anchor="w", padx=12, pady=6)
        ttk.Combobox(d, textvariable=v_act, values=REMOTE_ACTIONS, state="readonly", width=40).pack(anchor="w", padx=12)
        mk_label(d, "Params (JSON)", "DIM", "GSM").pack(anchor="w", padx=12, pady=(8, 0))
        txt = tk.Text(d, height=8, bg=C["ENTRY_BG"], fg=C["ENTRY_FG"], font=fnt("GMono"), relief="flat",
                      highlightthickness=1, highlightbackground=C["LINE"])
        txt.pack(fill="both", expand=True, padx=12, pady=4)
        txt.insert("1.0", '{\n  "message": "Test Facteur OK"\n}')
        def go():
            try:
                params = json.loads(txt.get("1.0", "end"))
            except Exception as ex:
                messagebox.showerror(APP_NAME, f"JSON : {ex}", parent=d); return
            cmd = make_command(v_act.get(), params, self.keys.load())
            dest = filedialog.asksaveasfilename(parent=d, defaultextension=".padawan",
                                                initialfile=f"test_{cmd['id'][:8]}.padawan",
                                                initialdir=known_folder_downloads(),
                                                filetypes=[("Commande Facteur", "*.padawan")])
            if not dest:
                return
            with open(dest, "w", encoding="utf-8") as f:
                json.dump(cmd, f, ensure_ascii=False, indent=1)
            messagebox.showinfo(APP_NAME, f"Commande écrite :\n{dest}\n\n"
                                "Dépose-la dans un dossier surveillé (ou elle y est déjà).", parent=d)
            d.ok(True)
        bot = tk.Frame(d, bg=C["PANEL"], padx=8, pady=6); bot.pack(fill="x", side="bottom")
        mk_button(bot, "Annuler", d.cancel).pack(side="right", padx=4)
        mk_button(bot, "Générer…", go, "accent").pack(side="right")
        self.wait_window(d)

    def show_help(self, _section: str = ""):
        d = Modal(self, "Aide — Facteur", 780, 560)
        t = tk.Text(d, bg=C["ENTRY_BG"], fg=C["ENTRY_FG"], font=fnt("GUI"), wrap="word", relief="flat",
                    highlightthickness=1, highlightbackground=C["LINE"], padx=8, pady=8)
        t.pack(fill="both", expand=True, padx=8, pady=8)
        t.insert("1.0", HELP_TEXT)
        t.configure(state="disabled")
        # liens cliquables simples
        def open_data():
            open_path(Paths.data)
        bot = tk.Frame(d, bg=C["PANEL"], padx=8, pady=6); bot.pack(fill="x", side="bottom")
        mk_link(bot, "Ouvrir le dossier de données", Paths.data, C["PANEL"]).pack(side="left", padx=6)
        mk_button(bot, "Fermer", d.cancel).pack(side="right")
        self.wait_window(d)

    def on_close(self):
        # masquer dans le tray (le moteur continue) — Quitter via menu pour arreter
        if getattr(self, "readonly_test", False):
            self.quit_app(); return
        self.withdraw()
        notify("Facteur", "Toujours actif en arrière-plan. Quitter via le menu Fichier ou le tray Padawan.", self.cfg)

    def quit_app(self):
        try:
            self.engine.stop()
        except Exception:
            pass
        self.cfg.save()
        self.destroy()


HELP_TEXT = """Facteur - ton assistant de rangement (Projet Padawan)

EN DEUX MOTS
 Facteur surveille un dossier (Téléchargements, au départ) et s'occupe
 tout seul des nouveaux fichiers : il les range, les envoie au Grimoire
 ou à l'Archiveur, ou les met de côté. Rien n'est effacé pour de vrai :
 au pire, un fichier va dans le dossier _Traités, d'où tu peux le reprendre.

POUR COMMENCER (2 minutes)
 1. Tableau de bord > « Ma première règle » : un assistant en 3 étapes.
    Quel dossier ? Quels fichiers (PDF, images, vidéos, vieux fichiers) ?
    Quoi en faire (ranger, Grimoire, Archiveur, mettre de côté) ?
 2. Regarde l'aperçu : il montre ce qui serait fait, sans rien toucher.
 3. Clique « Créer et activer ». C'est tout !

LES RÈGLES, EN PLUS DÉTAILLÉ
 Onglet Règles : chaque règle dit QUOI (genre de fichiers), QUAND
 (toutes les X minutes, à certaines heures) et QUOI FAIRE.
 Règles > Bibliothèque de modèles : des règles toutes prêtes.
 Fichier > Importer un paquet de règles : les règles reçues arrivent
 en pause ; tu les actives quand tu veux.
 Un même fichier n'est jamais traité deux fois.

DOUCEUR POUR TON PC
 Options : nombre de fichiers par passe, priorité basse, pause si la
 batterie est faible ou si le PC est occupé. « Pause globale » en haut
 arrête tout d'un clic.

MODE AVANCÉ (facultatif - la plupart des gens n'en ont pas besoin)
 Options > « Mode avancé » affiche deux onglets de plus :
  - Commandes à distance : piloter ce PC depuis ton site web.
  - Boîtes SQL : lire des messages déposés sur ton serveur.
 Tant que ce mode est éteint, Facteur ne reçoit aucune commande de
 l'extérieur. Rien n'est perdu quand tu l'éteins ou le rallumes.
 La clé de connexion n'est créée que si tu cliques « Créer ma clé ».

OÙ SONT MES DONNÉES ?
 C:\\web\\FTP_HOME\\FACTEUR\\ (ou Documents\\Padawan\\Facteur) :
 facteur_config.json (réglages), facteur.log (journal), _Traités.

RACCOURCIS
 F1 : cette aide. Fichier > Masquer : Facteur continue en arrière-plan.
 L'icône Padawan (près de l'horloge) permet de mettre Facteur en pause.
"""


# ================================================================ demarrage Windows (HKCU Run "Facteur")
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _autostart_flag() -> str:
    la = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(la, "Padawan", "Facteur", "demarrage_desactive.flag")


def autostart_enabled() -> bool:
    if not IS_WIN:
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
            winreg.QueryValueEx(k, "Facteur")
            return True
    except Exception:
        return False


def set_autostart(enable: bool) -> bool:
    if not IS_WIN:
        return False
    try:
        import winreg
        pyw = sys.executable
        if pyw.lower().endswith("python.exe"):
            cand = pyw[:-10] + "pythonw.exe"
            if os.path.isfile(cand):
                pyw = cand
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if enable:
                winreg.SetValueEx(k, "Facteur", 0, winreg.REG_SZ,
                                  f'"{pyw}" "{os.path.abspath(__file__)}" --cache')
            else:
                try:
                    winreg.DeleteValue(k, "Facteur")
                except FileNotFoundError:
                    pass
        flag = _autostart_flag()
        if enable:
            if os.path.isfile(flag):
                os.remove(flag)
        else:
            os.makedirs(os.path.dirname(flag), exist_ok=True)
            with open(flag, "w") as fh:
                fh.write("Facteur au demarrage desactive manuellement\n")
        return True
    except Exception as e:
        logger.warning("autostart: %s", e)
        return False


# ================================================================ instance unique / captures / tests
def _focus_existing() -> bool:
    if not IS_WIN:
        return False
    try:
        u32 = ctypes.windll.user32
        hwnd = u32.FindWindowW("TkTopLevel", APP_TITLE)
        if hwnd:
            cmd = 9 if u32.IsIconic(hwnd) else (3 if u32.IsZoomed(hwnd) else 5)
            u32.ShowWindow(hwnd, cmd)
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


def take_shot(app: "FacteurApp", path: str) -> bool:
    try:
        from PIL import ImageGrab  # type: ignore
    except ImportError:
        return False
    try:
        app.attributes("-topmost", True); app.lift(); app.update(); time.sleep(0.4); app.update()
        full = ImageGrab.grab()
        app.attributes("-topmost", False)
    except Exception:
        return False
    f = full.width / max(1, app.winfo_screenwidth())
    x, y, w, h = app.winfo_rootx(), app.winfo_rooty(), app.winfo_width(), app.winfo_height()
    img = full.crop((int(x * f), int(y * f), int((x + w) * f), int((y + h) * f)))
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    img.save(path)
    return True


def run_smoke(app: "FacteurApp") -> int:
    errors: List[str] = []
    try:
        app.update(); app.refresh_all(); app.update()
        for theme in ("clair", "sombre", "norton"):
            app.v_theme.set(theme); app.change_theme(); app.update()
        # onglets
        for i in range(len(app.nb.tabs())):
            app.nb.select(i); app.update()
        if app.keys.exists() is False and not app.cfg.data.get("mode_avance"):
            print("SMOKE cle : aucune cle creee en mode normal (OK)")
        # assistant : creation d'une regle (sans fenetre bloquante)
        n0 = len(app.cfg.rules()); app._wiz_nowait = True
        app.first_rule_wizard(); w = app._wiz
        for _ in range(3):
            w["go"](1); app.update()
        rule = app._wiz_rule(app.cfg.folders()[0] if app.cfg.folders() else None, "pdf", "traites", "", 7)
        if rule["actif"] or rule.get("age_min") != 7 * 86400:
            errors.append("assistant regle")
        try:
            w["dialog"].destroy()
        except Exception:
            pass
        if os.path.abspath(Paths.data) == os.path.abspath(DEFAULT_DATA_DIR):
            print("SMOKE : donnees reelles, tests de signature sautes (aucune cle creee)")
            raise StopIteration
        if not app.keys.exists():
            app.keys.create()
        # generation commande de test (sans deposer)
        cmd = make_command("notifier", {"message": "smoke"}, app.keys.load())
        if not cmd.get("sig") or len(cmd["sig"]) != 64:
            errors.append("signature smoke")
        ok, why = verify_command(cmd, app.keys.load(), DEFAULT_EXPIRE_SEC)
        if not ok:
            errors.append("verify : " + why)
        # anti-rejeu
        SEEN.mark_id(cmd["id"])
        ok2, why2 = verify_command(cmd, app.keys.load(), DEFAULT_EXPIRE_SEC)
        if ok2:
            errors.append("anti-rejeu a laisse passer")
        # signature fausse
        bad = dict(cmd); bad["id"] = uuid.uuid4().hex; bad["sig"] = "0" * 64
        ok3, _ = verify_command(bad, app.keys.load(), DEFAULT_EXPIRE_SEC)
        if ok3:
            errors.append("fausse signature acceptee")
        # expiree
        old = make_command("notifier", {"message": "x"}, app.keys.load(), expire_sec=1, ts=now_ts() - 100)
        ok4, _ = verify_command(old, app.keys.load(), DEFAULT_EXPIRE_SEC)
        if ok4:
            errors.append("expiree acceptee")
    except StopIteration:
        pass
    except Exception:
        errors.append(traceback.format_exc())
    try:
        app.engine.stop()
    except Exception:
        pass
    print(f"SMOKE {'OK' if not errors else 'ERREURS'} : {len(app.cfg.rules())} règles, données {Paths.data}")
    for e in errors:
        print("ERREUR:", e)
    return 0 if not errors else 1


def cli_check(_args) -> int:
    lines = [
        f"Facteur v{APP_FILE_VER}",
        f"Données : {Paths.data}",
        f"Config  : {Paths.config()} ({'OK' if os.path.isfile(Paths.config()) else 'absente'})",
        f"Clé     : {Paths.keyfile()} ({'OK' if os.path.isfile(Paths.keyfile()) else 'à créer'})",
        f"Watchdog: {'OK' if WATCHDOG else 'ABSENT'}",
        f"plyer   : {'OK' if module_ok('plyer') else 'absent (notifications limitées)'}",
        f"pywin32 : {'OK' if module_ok('win32crypt') else 'absent (DPAPI via ctypes)'}",
        f"Téléchargements : {known_folder_downloads()}",
        f"Grimoire : {find_script('grimoire1.py') or 'ABSENT'}",
        f"Archiveur: {find_script('archiveur5.py','archiveur4.py') or 'ABSENT'}",
        f"Arsenal  : {find_script('arsenal1.py') or 'ABSENT'}",
    ]
    if os.path.isfile(Paths.config()):
        cfg = Config().load()
        lines.append(f"Dossiers : {len(cfg.folders())}  Règles : {len(cfg.rules())} "
                     f"({sum(1 for r in cfg.rules() if r.get('actif'))} actives)")
        lines.append(f"Pause globale : {cfg.data.get('pause_globale')}")
        lines.append(f"Remote actif  : {cfg.data.get('remote',{}).get('actif')}")
        n_b = len(cfg.data.get("boites_sql") or [])
        lines.append(f"Boîtes SQL   : {n_b} (module {'OK' if boite_sql else 'ABSENT'})")
    print("\n".join(lines))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Facteur - surveillant de dossiers (Projet Padawan)")
    ap.add_argument("--smoke", action="store_true", help="test automatique de l'interface puis sortie")
    ap.add_argument("--check", action="store_true", help="vérification config / modules")
    ap.add_argument("--shot", default="", help="capture PNG puis sortie")
    ap.add_argument("--geometry", default="", help="ex. 1280x720+0+0")
    ap.add_argument("--data", default="", help="autre dossier de données (tests)")
    ap.add_argument("--cache", action="store_true", help="démarrer masqué (lancé par le tray Padawan)")
    ap.add_argument("--make-icons", action="store_true", help="génère facteur1.ico/.png puis sortie")
    ap.add_argument("--montrer", action="store_true", help="ramène la fenêtre si déjà ouvert")
    args = ap.parse_args(argv)
    if args.data:
        Paths.set(args.data)
    os.makedirs(Paths.data, exist_ok=True)
    os.makedirs(Paths.traites(), exist_ok=True)
    os.makedirs(Paths.quarantaine(), exist_ok=True)
    JOURNAL.setup()
    if IS_WIN:
        for s in (sys.stdout, sys.stderr):
            try:
                s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
            except Exception:
                pass
    if args.make_icons:
        print(generate_app_icons(BASE, force=True)); return 0
    if args.check:
        return cli_check(args)
    if tk is None:
        print("tkinter requis"); return 1
    special = args.smoke or bool(args.shot)
    mutex = None
    if not special:
        ok, mutex = _single_instance()
        if not ok:
            if not args.cache:  # --cache (cle Run / tray) : deja actif -> sortie silencieuse
                _focus_existing()
            return 0
        if IS_WIN and not os.path.isfile(_autostart_flag()) and not autostart_enabled():
            set_autostart(True)  # defaut ON tant que Marc ne l'a pas desactive
    try:
        generate_app_icons(BASE)
    except Exception:
        pass
    try:
        app = FacteurApp(args)
    except Exception:
        jlog("ERREUR", "ui", traceback.format_exc())
        raise
    if args.smoke:
        code = run_smoke(app)
        app.quit_app(); return code
    if args.shot:
        app.update(); time.sleep(0.5)
        take_shot(app, args.shot)
        app.quit_app(); return 0
    app.mainloop()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        sys.exit(1)
