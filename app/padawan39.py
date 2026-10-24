# -*- coding: utf-8 -*-
"""
Padawan build 39 — tray + Archiveur (archiveur4.py, repli v3/v2/v1) via padawan_tray.
Cousin local de Grok pour Marc (Québec). Ollama only.
Anti-freeze + multi-chasse + pouvoirs + mission + notifs plyer (v23–v28).
Version fichier seulement (APP_FILE_VER); UI affiche APP_NAME sans numéro.
Indicateur modèle: /api/ps + warm /api/generate; voyant checking/loading/ready/down.
Status FR successifs: vérification → démarrage/install/téléchargement → serveur OK → modèle.
Auto: ping Ollama → serve si down → install+pull dolphin3:8b si absent (consentement Tk).
Rail: header fixe + zone scroll (nav+VEILLE) + bas fixe (mission/status + phase Ollama).
Sources: web / quebec / tech / news / arduino / nature. Profondeur N + Creuser top 3.
v29: chrome chasse 2 rangées max, rail plus étroit, cartes sources compactes.
v30: backends yahoo/bing/auto d'abord; retry sans bias si 0 hits; erreur réelle vs Filet vide.
v31: brief chasse isolé (pas last_a/chat/parked/ADN); filter hors-sujet; session_hunt_id.
v32: conclusion En bref/À retenir/Sources+URLs; dédup phrases; inject sources; liens cliquables.
v33: UNCENSORED_MODELS (Dolphin/uncensored); menu locaux+(à télécharger); pull thread + warm;
     system prompts directs — pas de refus moralisateur / « je ne peux pas ».
v34: auto-scroll intelligent (sticky-bottom); ancre chasse sur query/En bref; bouton ↓ Bas.
v35: pystray tray (Ouvrir/Masquer/Quitter); X=hide; zoomed au load (cfg fullscreen);
     auto-start shell:Startup ou HKCU Run (cfg start_with_windows).
v36: tray option « Gestionnaire de fichiers » → lance gestionnaire_fichiers5.py (pythonw).
v38: tray module padawan_tray.py (assets .ico/.png teal) + alias systemtray.py;
     menu sans default=True.
v39: tray option « Archiveur… » → lance archiveur4.py (repli archiveur3/2/1, pythonw); padawan_tray.launch_archiveur.
v37: tray sans default=True — clic gauche ouvre le menu; choix Padawan OU Gestionnaire.
"""
from __future__ import annotations

import html
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
import webbrowser
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

try:
    import requests
except ImportError:
    requests = None
try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None
try:
    from ddgs import DDGS
except ImportError:
    DDGS = None
try:
    from plyer import notification as plyer_notification
except ImportError:
    plyer_notification = None
# Tray / auto-start / gestionnaire : module visible padawan_tray (+ alias systemtray)
import padawan_tray
from padawan_tray import (
    TRAY_AVAILABLE,
    ensure_windows_startup,
    acquire_single_instance,
    is_windows_startup_enabled,
    hide_to_tray as _tray_hide,
    launch_archiveur as _tray_launch_archiveur,
    launch_file_manager as _tray_launch_fm,
    make_tray_image,  # noqa: F401 — disponible / assets
    setup_tray,
    show_from_tray as _tray_show,
    stop_tray,
)

BASE = os.path.dirname(os.path.abspath(__file__))
MEM_FILE, CFG_FILE = os.path.join(BASE, "memory.json"), os.path.join(BASE, "config.json")
CACHE_FILE, LOG_FILE = os.path.join(BASE, "search_cache.json"), os.path.join(BASE, "errors.log")
TASKS_FILE = os.path.join(BASE, "tasks.json")
OLLAMA, MODEL, TIMEOUT = "http://127.0.0.1:11434", "dolphin3:8b", 240
MODEL_FALLBACK = "huihui_ai/qwen2.5-abliterate:7b"
# Catalogue Ollama NON CENSURÉS (famille Dolphin / uncensored explicites).
# Évite Llama Guard / modèles « aligned » comme défaut. 70b = gros, optionnel.
UNCENSORED_MODELS = (
    "dolphin3:8b",                       # défaut v39g (2026-10-24, choix de Marc) - plus vivant, meilleures précautions
    "huihui_ai/qwen2.5-abliterate:7b",   # ancien défaut v39h - Qwen2.5 7B (4,7 Go)
    "dolphin-mistral:latest",
    "dolphin-phi:latest",                # petit Dolphin uncensored
    "wizard-vicuna-uncensored:latest",   # classic uncensored
    "dolphin-llama3:70b",                # gros (~40 Go), optionnel
    "qwen2.5:7b",                        # 4,7 Go - recommandé: français riche, structure
    "mistral-nemo:12b",                  # 7,1 Go - plus profond, un peu plus lent
)
MODEL_DL_MARK = " (à télécharger)"
APP_NAME = "Padawan"
APP_FILE_VER = 39  # version fichier seulement — jamais affichée comme titre produit
ROLE_HIST_CAP = 80
CACHE_TTL = 3 * 3600
SESSION_CACHE_TTL = 10 * 60  # anti-doublon session ~10 min
HUNT_N = 8
HUNT_N_MAX = 15
CLICK_DEBOUNCE_MS = 300
HTTP_CONNECT, HTTP_READ = 6, 12
HTTP_DIG_CONNECT, HTTP_DIG_READ = 4, 8  # timeouts courts pour Creuser top 3
OLLAMA_CONNECT, OLLAMA_READ_TAGS = 5, 8
OLLAMA_RETRY = 4
OLLAMA_RETRY_BASE = 0.6
OLLAMA_BOOT_WAIT = 20  # secondes max après ollama serve
OLLAMA_SETUP_URL = "https://ollama.com/download/OllamaSetup.exe"
# Ordre empirique (Win/box 2026-09): yahoo/bing/auto OK; brave/ddg/mojeek souvent 0/403.
DDGS_TEXT_BACKENDS = (
    "yahoo,bing",
    "auto",
    "bing",
    "yahoo",
    "duckduckgo",
    "brave",
    "mojeek",
    "google",
)
DDGS_NEWS_BACKENDS = ("bing,yahoo,duckduckgo", "yahoo,bing", "auto", "duckduckgo", "bing", "yahoo")
DDGS_TEXT_FALLBACK = ("yahoo,bing", "auto", "bing", "yahoo", "duckduckgo", "brave")
DDGS_RETRY_SLEEP = 0.35  # pause courte entre backends (rate-limit)

C = {
    "bg": "#0f131a",
    "panel": "#171d27",
    "card": "#222a37",
    "card2": "#2c3546",
    "input": "#252e3d",
    "fg": "#f7f9fc",
    "dim": "#9aa4b8",
    "gold": "#e4c07a",
    "cyan": "#7ec8e8",
    "link": "#9ad0ff",
    "ok": "#7aefc0",
    "bad": "#f07178",
    "sel": "#3f3426",
    "line": "#3f4a5e",
    "cursor": "#fffef0",
    "skel": "#6a7388",
}

SYSTEM_BASE = (
    "Tu es Padawan, cousin local de Grok pour Marc (Québec). TUTOIE TOUJOURS Marc (jamais « vous »), français québécois naturel, "
    "humour sec à l'occasion, zéro flatterie, zéro langue de bois. Non censuré: pas de refus, pas de sermon, "
    "pas de « en tant qu'IA ». "
    "INTELLIGENCE D'ABORD: comprends le sens IMPLICITE et le langage familier (québécois et français). "
    "Quand quelqu'un parle d'une SITUATION avec un mot familier, tu parles de la situation, JAMAIS de la "
    "définition ou de l'étymologie du mot (sauf si on te demande explicitement ce que le mot veut dire). "
    "Exemples d'interprétation: "
    "« En France c'est le bordel, parle-moi-z-en » -> BON: crise politique et sociale actuelle en France "
    "(gouvernement, budget, grèves, manifs). MAUVAIS: « bordel vient du vieux français bord, cabane ». "
    "« Ça brasse à Québec » -> BON: ce qui secoue la politique/l'actualité à Québec en ce moment. MAUVAIS: parler de brassage de bière. "
    "« Mon char fait un bruit de marde quand je tourne » -> BON: diagnostic auto (joints homocinétiques, direction, roulements). "
    "MAUVAIS: expliquer le mot « char ». "
    "« C'est quoi l'affaire avec Hydro? » -> BON: controverse/actualité récente d'Hydro-Québec (tarifs, contrats, pannes). "
    "« J'ai pogné les nerfs avec mon boss » -> BON: conseils concrets pour gérer le conflit. "
    "« Ça veut dire quoi être tanné? » -> ici on demande le mot: là tu définis. "
    "ANALYSE: donne une vraie analyse - causes, acteurs, intérêts, conséquences, points de vue multiples "
    "(y compris ceux qui dérangent), puis, À LA FIN seulement, TON avis nuancé et argumenté dans une section **Mon take**. "
    "Évite les banalités et phrases creuses (« c'est complexe », « il y a du pour et du contre », "
    "« il est important de noter ») - remplace-les par des faits, des chiffres, des mécanismes. "
    "Réponses complètes et structurées: réponse directe d'abord, sections en **gras** ou ### titres, "
    "puces, étapes, exemples concrets (code dans ``` si technique), pièges, piste pour aller plus loin. "
    "Adapte au contexte de Marc (Windows, Python, Arduino/NodeMCU, serveurs maison, rétro) quand pertinent. "
    "En technique, va à la VRAIE cause probable d'abord (ex. NodeMCU qui reboot au relais = chute de tension/brownout ou pic inductif: alim séparée 5 V, diode de roue libre, module relais optocouplé, condensateur 470-1000 µF), pose ensuite une question pour préciser. "
    "HONNÊTETÉ: n'invente aucun fait/date/montant/lien; si tu n'es pas sûr, dis-le. Une allégation reste une allégation. "
    "Dis franchement quand une source est faible (page d'accueil, archive, blogue, titre sans contenu, source partisane). "
    "AUCUNE URL de mémoire: nomme la ressource au lieu d'un lien; une URL seulement si elle vient des SOURCES fournies."
)

DEAD_HOSTS = (
    "msn.com", "www.msn.com", "bing.com", "www.bing.com", "news.bing.com",
    "news.google.com", "news.yahoo.com", "apple.news", "news.yahoo.fr",
)
HUB_PATHS = ("/monde", "/international", "/geopolitique", "/topics/", "/home", "/accueil")
NOISE = ("newsletter", "s'abonner", "mentions legales", "politique de confidentialite")
URL_RE = re.compile(r"https?://[^\s\)\]\>\"'\<\>]+")
WATCH_DEFAULT = ["détroit d'Ormuz", "Taïwan", "IA open source", "Canada / Québec"]
NEWS_BACKENDS = "bing,yahoo,duckduckgo"

HUNT_MODES = ("rapide", "multi", "profond")
HUNT_MODE_LABELS = {
    "rapide": "Rapide",
    "multi": "Multi-moteurs",
    "profond": "Profond",
}

# Sources ciblées (remplacent actus/web/wiki comme filet de chasse)
SEARCH_SOURCES = ("web", "quebec", "tech", "news", "arduino", "nature")
SEARCH_SOURCE_LABELS = {
    "web": "Web",
    "quebec": "Québec",
    "tech": "Tech",
    "news": "News",
    "arduino": "Arduino",
    "nature": "Nature",
}
# Bias site: operator ajouté à la requête (None = large / news DDGS)
SEARCH_SOURCE_BIAS = {
    "web": None,
    "quebec": (
        "(site:radio-canada.ca OR site:lapresse.ca OR site:ledevoir.com "
        "OR site:quebec.ca OR site:gouv.qc.ca OR radio-canada OR ici.radio-canada)"
    ),
    "tech": (
        "(site:github.com OR site:stackoverflow.com OR site:docs.python.org "
        "OR site:developer.mozilla.org OR site:readthedocs.io)"
    ),
    "news": None,  # DDGS news + fallback after:/sites
    "arduino": (
        "(site:arduino.cc OR site:github.com) "
        "(arduino OR esp8266 OR nodemcu OR mqtt)"
    ),
    "nature": (
        "(site:passeportsante.net OR site:aujardin.info OR site:jardinage.ooreka.fr "
        "OR site:quebec.ca OR site:canada.ca OR site:protegez-vous.ca) "
        "(plante OR nature OR santé OR remède OR jardin)"
    ),
}
NEWS_FALLBACK_SITES = (
    "site:radio-canada.ca OR site:lapresse.ca OR site:ledevoir.com "
    "OR site:bbc.com OR site:reuters.com OR site:theguardian.com"
)

# Cache session en mémoire (query+source -> {t, items})
_SESSION_SEARCH_CACHE: Dict[str, Dict[str, Any]] = {}
_SESSION_CACHE_LOCK = threading.Lock()

MODE_TO_ROLE = {"parler": "compagnon", "chercher": "chercheur", "contredire": "contrarian"}
ROLE_TO_MODE = {v: k for k, v in MODE_TO_ROLE.items()}

MISSION_STEPS = ("formuler", "moteurs", "filtrer", "enrichir", "brief")
MISSION_LABELS = {
    "formuler": "Formuler",
    "moteurs": "Moteurs",
    "filtrer": "Filtrer",
    "enrichir": "Enrichir",
    "brief": "Brief",
}

_http: Optional["requests.Session"] = None


def http() -> "requests.Session":
    global _http
    if _http is None:
        if not requests:
            raise RuntimeError("pip install requests")
        s = requests.Session()
        s.trust_env = False
        s.headers.update({
            "User-Agent": f"Mozilla/5.0 {APP_NAME}",
            "Accept-Language": "fr-FR,fr;q=0.9",
        })
        _http = s
    return _http


# ── helpers ──────────────────────────────────────────────────────────────────


def _is_conn_err(exc: BaseException) -> bool:
    if requests and isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
        return True
    msg = str(exc).lower()
    return any(x in msg for x in (
        "connection refused", "actively refused", "failed to establish",
        "max retries exceeded", "timed out", "timeout", "10061", "winerror 10061",
        "name or service not known", "nodename nor servname",
    ))


def _is_timeout(exc: BaseException) -> bool:
    if requests and isinstance(exc, requests.exceptions.Timeout):
        return True
    return "timeout" in str(exc).lower() or "timed out" in str(exc).lower()


def ollama_err_fr(exc: BaseException, *, context: str = "") -> str:
    """Messages d'erreur Ollama clairs en français."""
    if _is_conn_err(exc) and not _is_timeout(exc):
        return "Ollama down — daemon injoignable (127.0.0.1:11434)"
    if _is_timeout(exc):
        return "timeout Ollama — le modèle met trop longtemps à répondre"
    msg = str(exc)
    low = msg.lower()
    if "404" in low or "not found" in low or "model" in low and ("not found" in low or "pull" in low):
        return f"modèle pas chargé / introuvable — tire {MODEL}"
    if context:
        return f"{context}: {msg[:100]}"
    return msg[:120] or "erreur Ollama"


def ollama_request(
    method: str,
    path: str,
    *,
    json_body: Any = None,
    timeout: Any = None,
    stream: bool = False,
    retries: int = OLLAMA_RETRY,
    cancel: Optional[threading.Event] = None,
) -> "requests.Response":
    """GET/POST Ollama avec retry + backoff exponentiel."""
    if not requests:
        raise RuntimeError("pip install requests")
    url = f"{OLLAMA}{path}"
    to = timeout if timeout is not None else (OLLAMA_CONNECT, OLLAMA_READ_TAGS)
    last: Optional[BaseException] = None
    for attempt in range(max(1, retries)):
        if cancel and cancel.is_set():
            raise RuntimeError("annulé")
        try:
            fn = http().post if method.upper() == "POST" else http().get
            kw: Dict[str, Any] = {"timeout": to, "stream": stream}
            if json_body is not None:
                kw["json"] = json_body
            r = fn(url, **kw)
            r.raise_for_status()
            return r
        except Exception as e:
            last = e
            # 4xx (sauf retryables) : pas de retry inutile
            if requests and isinstance(e, requests.exceptions.HTTPError):
                code = getattr(getattr(e, "response", None), "status_code", 0) or 0
                if 400 <= code < 500 and code not in (408, 429):
                    raise
            if attempt + 1 >= retries:
                break
            delay = OLLAMA_RETRY_BASE * (2 ** attempt)
            log(f"ollama retry {attempt+1}/{retries} {path}: {e} (sleep {delay:.1f}s)")
            time.sleep(delay)
    assert last is not None
    raise last


def ollama_up() -> bool:
    """True si le daemon Ollama répond (GET /api/tags)."""
    if not requests:
        return False
    try:
        ollama_request("GET", "/api/tags", timeout=(OLLAMA_CONNECT, OLLAMA_READ_TAGS), retries=2)
        return True
    except Exception:
        return False


def find_ollama_exe() -> Optional[str]:
    """Cherche ollama.exe (Windows) / ollama (PATH)."""
    candidates: List[str] = []
    if sys.platform.startswith("win"):
        local = os.environ.get("LOCALAPPDATA") or ""
        pf = os.environ.get("ProgramFiles") or r"C:\Program Files"
        pf86 = os.environ.get("ProgramFiles(x86)") or r"C:\Program Files (x86)"
        user = os.environ.get("USERPROFILE") or ""
        candidates.extend([
            os.path.join(local, "Programs", "Ollama", "ollama.exe"),
            os.path.join(pf, "Ollama", "ollama.exe"),
            os.path.join(pf86, "Ollama", "ollama.exe"),
            os.path.join(user, "AppData", "Local", "Programs", "Ollama", "ollama.exe"),
        ])
        which = shutil.which("ollama.exe") or shutil.which("ollama")
    else:
        which = shutil.which("ollama")
    if which:
        candidates.insert(0, which)
    seen = set()
    for c in candidates:
        if not c or c in seen:
            continue
        seen.add(c)
        if os.path.isfile(c):
            return c
    return None


def _win_no_window_kwargs() -> Dict[str, Any]:
    if not sys.platform.startswith("win"):
        return {}
    kw: Dict[str, Any] = {}
    # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
    flags = 0x00000008 | 0x00000200 | 0x08000000
    kw["creationflags"] = flags
    try:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0
        kw["startupinfo"] = si
    except Exception:
        pass
    return kw


def start_ollama_serve(exe: Optional[str] = None) -> Tuple[bool, str]:
    """Lance `ollama serve` détaché. Retourne (ok_lancé, détail)."""
    exe = exe or find_ollama_exe()
    if not exe:
        return False, "ollama.exe introuvable"
    try:
        kwargs = dict(
            args=[exe, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            close_fds=True,
        )
        kwargs.update(_win_no_window_kwargs())
        subprocess.Popen(**kwargs)
        log(f"ollama serve lancé via {exe}")
        return True, f"serveur lancé · {exe}"
    except Exception as e:
        log(f"start_ollama_serve: {e}")
        return False, f"échec lancement: {e}"[:120]


def wait_ollama_up(
    seconds: float = OLLAMA_BOOT_WAIT,
    cancel: Optional[threading.Event] = None,
    on_tick: Optional[Callable[[str], None]] = None,
) -> bool:
    """Attend que /api/tags réponde (poll ~0.8s)."""
    deadline = time.time() + max(1.0, seconds)
    n = 0
    while time.time() < deadline:
        if cancel and cancel.is_set():
            return False
        if ollama_up():
            return True
        n += 1
        if on_tick:
            try:
                on_tick(f"Ollama : absent → démarrage… ({n})")
            except Exception:
                pass
        time.sleep(0.8)
    return ollama_up()


def model_in_tags(name: str) -> bool:
    """True si le modèle est listé dans /api/tags (installé localement)."""
    if not requests or not name:
        return False
    try:
        r = ollama_request("GET", "/api/tags", timeout=(OLLAMA_CONNECT, OLLAMA_READ_TAGS), retries=2)
        names = [
            (m.get("name") or "").strip().lower()
            for m in (r.json() or {}).get("models", [])
            if m.get("name")
        ]
        want = name.strip().lower()
        want_base = want.split(":")[0]
        for n in names:
            if n == want or n.startswith(want + ":") or (want_base and n.startswith(want_base + ":")):
                return True
        return False
    except Exception:
        return False


def pull_model(
    name: str,
    cancel: Optional[threading.Event] = None,
    on_progress: Optional[Callable[[str], None]] = None,
) -> Tuple[bool, str]:
    """`ollama pull <name>` (subprocess) avec status progress."""
    exe = find_ollama_exe()
    if not exe:
        return False, "ollama.exe introuvable pour pull"
    if on_progress:
        try:
            on_progress(f"Téléchargement {name}…")
        except Exception:
            pass
    try:
        kwargs: Dict[str, Any] = dict(
            args=[exe, "pull", name],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        kwargs.update(_win_no_window_kwargs())
        proc = subprocess.Popen(**kwargs)
        assert proc.stdout is not None
        last_line = ""
        for line in proc.stdout:
            if cancel and cancel.is_set():
                try:
                    proc.terminate()
                except Exception:
                    pass
                return False, "annulé"
            last_line = (line or "").strip()
            if last_line and on_progress:
                short = last_line[:60]
                try:
                    on_progress(f"Téléchargement {name}… {short}")
                except Exception:
                    pass
        rc = proc.wait(timeout=3600)
        if rc == 0 or model_in_tags(name):
            return True, "modèle téléchargé"
        return False, f"pull échoué (code {rc}) · {last_line[:80]}"
    except Exception as e:
        log(f"pull_model: {e}")
        return False, f"échec pull: {e}"[:120]


def install_ollama_windows(
    cancel: Optional[threading.Event] = None,
    on_progress: Optional[Callable[[str], None]] = None,
) -> Tuple[bool, str]:
    """Installe Ollama via winget, sinon OllamaSetup.exe silencieux."""
    if not sys.platform.startswith("win"):
        return False, "install auto supportée sur Windows seulement"

    def prog(msg: str):
        if on_progress:
            try:
                on_progress(msg)
            except Exception:
                pass

    # 1) winget
    winget = shutil.which("winget")
    if winget:
        prog("Ollama : installation…")
        try:
            kwargs: Dict[str, Any] = dict(
                args=[
                    winget, "install", "-e", "--id", "Ollama.Ollama",
                    "--accept-package-agreements", "--accept-source-agreements",
                    "--disable-interactivity",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            kwargs.update(_win_no_window_kwargs())
            proc = subprocess.Popen(**kwargs)
            assert proc.stdout is not None
            for line in proc.stdout:
                if cancel and cancel.is_set():
                    try:
                        proc.terminate()
                    except Exception:
                        pass
                    return False, "annulé"
                t = (line or "").strip()
                if t:
                    prog(f"winget: {t[:50]}")
            rc = proc.wait(timeout=900)
            exe = find_ollama_exe()
            if exe:
                return True, f"installé via winget · {exe}"
            if rc != 0:
                log(f"winget ollama rc={rc}")
        except Exception as e:
            log(f"winget install: {e}")

    # 2) Setup.exe officiel
    if not requests:
        return False, "requests manquant pour télécharger OllamaSetup.exe"
    prog("Ollama : installation…")
    setup = os.path.join(os.environ.get("TEMP") or os.environ.get("TMP") or ".", "OllamaSetup.exe")
    try:
        with http().get(OLLAMA_SETUP_URL, stream=True, timeout=(15, 300)) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length") or 0)
            done = 0
            with open(setup, "wb") as f:
                for chunk in r.iter_content(chunk_size=256 * 1024):
                    if cancel and cancel.is_set():
                        return False, "annulé"
                    if not chunk:
                        continue
                    f.write(chunk)
                    done += len(chunk)
                    if total and on_progress:
                        pct = int(100 * done / total)
                        prog(f"Ollama : installation… {pct}%")
        prog("Ollama : installation…")
        # Inno Setup style flags courants
        for flags in (["/VERYSILENT", "/NORESTART"], ["/SILENT", "/NORESTART"], ["/S"]):
            try:
                kwargs = dict(
                    args=[setup] + flags,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                )
                kwargs.update(_win_no_window_kwargs())
                proc = subprocess.Popen(**kwargs)
                try:
                    proc.wait(timeout=600)
                except subprocess.TimeoutExpired:
                    pass
                # laisser le temps aux fichiers
                for _ in range(20):
                    if cancel and cancel.is_set():
                        return False, "annulé"
                    exe = find_ollama_exe()
                    if exe:
                        return True, f"installé via setup · {exe}"
                    time.sleep(1.0)
            except Exception as e:
                log(f"setup {flags}: {e}")
        exe = find_ollama_exe()
        if exe:
            return True, f"installé · {exe}"
        return False, "install terminée mais ollama.exe introuvable (droits admin?)"
    except Exception as e:
        log(f"install_ollama: {e}")
        if _is_conn_err(e):
            return False, "échec réseau — impossible de télécharger Ollama"
        return False, f"échec install: {e}"[:120]


def ensure_ollama_running(
    cancel: Optional[threading.Event] = None,
    on_status: Optional[Callable[[str], None]] = None,
    allow_install: bool = False,
    ask_install: Optional[Callable[[], bool]] = None,
) -> Tuple[bool, str]:
    """
    Garantit Ollama joignable:
    - déjà up → ok
    - exe présent → serve + wait
    - exe absent + allow_install → install (consentement) puis serve
    """
    def status(msg: str):
        if on_status:
            try:
                on_status(msg)
            except Exception:
                pass

    if ollama_up():
        status("Ollama : serveur OK")
        return True, "Ollama : serveur OK"

    exe = find_ollama_exe()
    if not exe:
        if not allow_install:
            return False, "Impossible de démarrer Ollama (installe-le?)"
        consent = True
        if ask_install is not None:
            try:
                consent = bool(ask_install())
            except Exception:
                consent = False
        if not consent:
            return False, "Installation Ollama refusée"
        status("Ollama : installation…")
        ok, detail = install_ollama_windows(cancel=cancel, on_progress=status)
        if not ok:
            return False, detail or "Impossible de démarrer Ollama (installe-le?)"
        exe = find_ollama_exe()
        if not exe:
            return False, "Impossible de démarrer Ollama (installe-le?)"

    status("Ollama : absent → démarrage…")
    started, sdetail = start_ollama_serve(exe)
    if not started:
        # peut déjà tourner sans répondre encore — on attend quand même
        log(f"serve note: {sdetail}")
    if wait_ollama_up(OLLAMA_BOOT_WAIT, cancel=cancel, on_tick=status):
        status("Ollama : serveur OK")
        return True, "Ollama : serveur OK"
    return False, "Impossible de démarrer Ollama (installe-le?)"


def ensure_model_present(
    name: str,
    cancel: Optional[threading.Event] = None,
    on_status: Optional[Callable[[str], None]] = None,
) -> Tuple[bool, str]:
    """Si le modèle n'est pas dans /api/tags → ollama pull."""
    if model_in_tags(name):
        return True, "modèle présent"
    def status(msg: str):
        if on_status:
            try:
                on_status(msg)
            except Exception:
                pass
    status(f"Téléchargement {name}…")
    return pull_model(name, cancel=cancel, on_progress=status)


def model_loaded(name: str) -> bool:
    """True si le modèle est déjà en mémoire (GET /api/ps)."""
    if not requests or not name:
        return False
    try:
        r = ollama_request("GET", "/api/ps", timeout=(OLLAMA_CONNECT, OLLAMA_READ_TAGS), retries=2)
        models = (r.json() or {}).get("models") or []
        want = name.strip().lower()
        want_base = want.split(":")[0]
        for m in models:
            n = (m.get("name") or m.get("model") or "").strip().lower()
            if not n:
                continue
            if n == want or n.startswith(want + ":") or n.startswith(want + "-"):
                return True
            if want_base and (n == want_base or n.startswith(want_base + ":")):
                return True
        return False
    except Exception:
        return False


def ensure_model(name: str, cancel: Optional[threading.Event] = None) -> Tuple[bool, str]:
    """Force le load du modèle via /api/generate si pas déjà en VRAM."""
    if not requests:
        return False, "requests manquant"
    if not name:
        return False, "modèle vide"
    if model_loaded(name):
        return True, "prêt"
    if cancel and cancel.is_set():
        return False, "annulé"
    try:
        ollama_request(
            "POST",
            "/api/generate",
            json_body={
                "model": name,
                "prompt": " ",
                "stream": False,
                "keep_alive": "30m",
            },
            timeout=(OLLAMA_CONNECT, 300),
            retries=3,
            cancel=cancel,
        )
        if cancel and cancel.is_set():
            return False, "annulé"
        if model_loaded(name):
            return True, "prêt"
        return True, "prêt"
    except Exception as e:
        return False, ollama_err_fr(e, context="chargement modèle")


def log(msg: str) -> None:
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")
    except Exception:
        pass


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def clock() -> str:
    return datetime.now().strftime("%H:%M")


def notify_toast(title: str, message: str, timeout: int = 5) -> None:
    """Toast Windows via plyer; no-op si lib absente ou échec."""
    if plyer_notification is None:
        return
    try:
        plyer_notification.notify(
            title=title[:64],
            message=(message or "")[:180],
            app_name="Padawan",
            timeout=timeout,
        )
    except Exception:
        pass


def clean(text: str) -> str:
    if not text:
        return ""
    text = html.unescape(text)
    if "Ã" in text or "Â" in text:
        try:
            text = text.encode("latin-1").decode("utf-8")
        except Exception:
            pass
    return text.rstrip(").,;]")


def _norm_for_dedup(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^\w\sàâäéèêëïîôùûüç]", "", s, flags=re.IGNORECASE)
    return s.strip()


def dedup_near_sentences(text: str) -> str:
    """Écarte phrases / lignes quasi-identiques (garde la 1re occurrence)."""
    if not text:
        return ""
    out_lines: List[str] = []
    seen: List[str] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            out_lines.append(line)
            continue
        # Garder en-têtes markdown / labels de section
        if re.match(r"^(?:\*\*|#+)?\s*(?:En bref|À retenir|A retenir|Sources)\b", stripped, re.I):
            out_lines.append(line)
            continue
        if re.match(r"^#{1,3}\s", stripped) or (stripped.startswith("**") and stripped.endswith("**")):
            out_lines.append(line)
            continue
        bullet_m = re.match(r"^([-*•]\s+)", stripped)
        content = stripped[bullet_m.end():] if bullet_m else stripped
        chunks = re.split(r"(?<=[.!?…])\s+", content) if len(content) > 48 else [content]
        kept: List[str] = []
        for ch in chunks:
            ch = ch.strip()
            if not ch:
                continue
            norm = _norm_for_dedup(ch)
            if len(norm) < 14:
                kept.append(ch)
                continue
            dup = False
            for prev in seen:
                if norm == prev:
                    dup = True
                    break
                shorter, longer = (norm, prev) if len(norm) <= len(prev) else (prev, norm)
                if shorter in longer and len(shorter) >= 0.82 * len(longer):
                    dup = True
                    break
            if dup:
                continue
            seen.append(norm)
            kept.append(ch)
        if not kept:
            continue
        indent = line[: len(line) - len(line.lstrip())]
        prefix = bullet_m.group(1) if bullet_m else ""
        out_lines.append(indent + prefix + " ".join(kept))
    return "\n".join(out_lines)


def _strip_empty_legacy_sections(text: str) -> str:
    """Retire en-têtes Flou / Ça change / Prochaine coupe sans substance."""
    if not text:
        return ""
    lines = text.split("\n")
    out: List[str] = []
    i = 0
    hdr_re = re.compile(
        r"^(?:\*\*)?(?:Flou|Ça change|Ca change|Prochaine coupe)(?:\*\*)?\s*:?\s*$",
        re.I,
    )
    while i < len(lines):
        if hdr_re.match(lines[i].strip()):
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            # section vide ou une seule ligne générique → drop header (+ vide)
            if j >= len(lines) or hdr_re.match(lines[j].strip()) or re.match(
                r"^(?:\*\*)?(?:En bref|À retenir|A retenir|Sources|Ce qu.?.?on tient)\b",
                lines[j].strip(),
                re.I,
            ):
                i = j
                continue
            # garder le contenu utile, drop seulement l'en-tête legacy
            i += 1
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out)


def _strip_sources_section(text: str) -> str:
    """Retire une section Sources existante (sera réinjectée avec URLs complètes)."""
    if not text:
        return ""
    lines = text.split("\n")
    out: List[str] = []
    i = 0
    src_re = re.compile(r"^(?:\*\*)?Sources(?:\*\*)?\s*:?\s*$", re.I)
    other_re = re.compile(
        r"^(?:\*\*)?(?:En bref|À retenir|A retenir|Flou|Ça change|Ca change|Prochaine coupe|Ce qu|Mon take|Pour aller plus loin|💡|#)",
        re.I,
    )
    while i < len(lines):
        if src_re.match(lines[i].strip()):
            i += 1
            while i < len(lines):
                s = lines[i].strip()
                if other_re.match(s) and not src_re.match(s):
                    break
                # fin naturelle si double blank + autre chose — continuer jusqu'à fin ou autre section
                i += 1
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out).rstrip()


def _strip_query_echo(text: str, query: str) -> str:
    """Écarte lignes qui ne font que reformuler / répéter la query."""
    q = (query or "").strip()
    if not text or len(q) < 8:
        return text
    qn = _norm_for_dedup(q)
    if len(qn) < 8:
        return text
    out: List[str] = []
    seen_lines = 0  # v39g: anti-écho seulement en ouverture
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            out.append(line)
            continue
        if re.match(r"^(?:\*\*|#+)?\s*(?:En bref|À retenir|A retenir|Sources)\b", stripped, re.I):
            out.append(line)
            continue
        seen_lines += 1
        if seen_lines > 3:
            out.append(line)
            continue
        content = re.sub(r"^[-*•]\s+", "", stripped)
        # « Query: ... » / « Sujet: ... »
        content = re.sub(r"^(?:query|sujet|recherche|question)\s*[:：]\s*", "", content, flags=re.I)
        ln = _norm_for_dedup(content)
        if ln == qn:
            continue
        if qn in ln:
            extra = ln.replace(qn, "").strip()
            if len(extra) < 18:
                continue
        out.append(line)
    return "\n".join(out)


def format_hunt_sources_block(hits: List[Dict[str, str]]) -> str:
    """Bloc **Sources** titre + URL complète (cliquable via _insert_linked / say_links)."""
    if not hits:
        return ""
    lines = ["**Sources**"]
    for i, it in enumerate(hits, 1):
        title = clean((it.get("title") or "sans titre").strip()) or "sans titre"
        url = (it.get("url") or "").strip()
        lines.append(f"{i}. {title}")
        if url:
            lines.append(url)
    return "\n".join(lines)


def postprocess_hunt_brief(ans: str, hits: Optional[List[Dict[str, str]]] = None, query: str = "") -> str:
    """Dédup + anti-écho query + injecte toujours les URLs des hits retenus."""
    text = clean(ans or "").strip()
    text = _strip_query_echo(text, query)
    text = dedup_near_sentences(text)
    text = _strip_empty_legacy_sections(text)
    hits = hits or []
    sources_block = format_hunt_sources_block(hits)
    if sources_block:
        text = _strip_sources_section(text)
        text = (text.rstrip() + "\n\n" + sources_block).strip()
    return text.strip()


def host_of(url: str) -> str:
    try:
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return ""


def loadj(path, default):
    if not os.path.isfile(path):
        savej(path, default)
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, type(default)) else default
    except Exception as e:
        log(f"load {path}: {e}")
        return default


def savej(path, data) -> None:
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception as e:
        log(f"save {path}: {e}")


def load_cfg():
    d = {
        "model": MODEL, "watch": WATCH_DEFAULT, "role": "chercheur",
        "tip_seen": False, "hunt_mode": "multi",
        "notify_on_done": True,
        "search_source": "web",
        "hunt_n": HUNT_N,
        "dig_top3": False,
        "fullscreen": True,          # v35: maximisé (zoomed) au load
        "start_with_windows": True,  # v35: entrée Startup / HKCU Run
    }
    g = loadj(CFG_FILE, d)
    for k, v in d.items():
        g.setdefault(k, v)
    if g.get("hunt_mode") not in HUNT_MODES:
        g["hunt_mode"] = "multi"
    # migration anciens kind actus/web/wiki → sources v26
    legacy = {"actus": "news", "wiki": "web", "web": "web"}
    ss = g.get("search_source") or legacy.get(g.get("hunt_kind", ""), "web")
    if ss not in SEARCH_SOURCES:
        ss = legacy.get(ss, "web") if ss in legacy else "web"
    g["search_source"] = ss if ss in SEARCH_SOURCES else "web"
    try:
        hn = int(g.get("hunt_n", HUNT_N))
    except (TypeError, ValueError):
        hn = HUNT_N
    g["hunt_n"] = max(3, min(HUNT_N_MAX, hn))
    g["dig_top3"] = bool(g.get("dig_top3", False))
    g["fullscreen"] = bool(g.get("fullscreen", True))
    g["start_with_windows"] = bool(g.get("start_with_windows", True))
    return g


def _empty_roles() -> Dict[str, Any]:
    return {
        rid: {"history": []}
        for rid in ("capitaine", "chercheur", "contrarian", "compagnon")
    }


def load_mem():
    d = {"inbox": [], "searches": [], "sessions": [], "roles": _empty_roles()}
    g = loadj(MEM_FILE, d)
    for k, v in d.items():
        if k not in g or not isinstance(g[k], type(v)):
            g[k] = v
    if "roles" not in g or not isinstance(g["roles"], dict):
        g["roles"] = _empty_roles()
    else:
        for rid, empty in _empty_roles().items():
            slot = g["roles"].setdefault(rid, empty)
            if not isinstance(slot, dict):
                g["roles"][rid] = empty
            else:
                slot.setdefault("history", [])
                if not isinstance(slot["history"], list):
                    slot["history"] = []
    return g


def is_dead(url: str) -> bool:
    h = host_of(url).lower()
    return any(h == d or h.endswith("." + d) for d in DEAD_HOSTS)


def is_hub(url: str) -> bool:
    if is_dead(url):
        return True
    try:
        p = urlparse(url)
    except Exception:
        return True
    path = (p.path or "/").rstrip("/").lower() or "/"
    if path in ("", "/"):
        return True
    return any(h in path for h in HUB_PATHS) and path.count("/") <= 2


def model_id_from_label(label: str) -> str:
    """Enlève le marqueur « (à télécharger) » du libellé UI → id Ollama."""
    s = (label or "").strip()
    if s.endswith(MODEL_DL_MARK):
        s = s[: -len(MODEL_DL_MARK)].strip()
    return s


def model_menu_label(name: str, installed: bool) -> str:
    return name if installed else f"{name}{MODEL_DL_MARK}"


def local_model_names() -> List[str]:
    """Noms bruts présents dans /api/tags (vide si Ollama down)."""
    if not requests:
        return []
    try:
        return [
            m.get("name")
            for m in ollama_request(
                "GET", "/api/tags", timeout=(OLLAMA_CONNECT, OLLAMA_READ_TAGS), retries=3
            ).json().get("models", [])
            if m.get("name")
        ]
    except Exception as e:
        log(ollama_err_fr(e, context="tags"))
        return []


def _name_installed(want: str, local_names: List[str]) -> bool:
    """Match souple tags/aliases (ex. dolphin3:8b ↔ dolphin3:latest)."""
    w = (want or "").strip().lower()
    if not w:
        return False
    base = w.split(":")[0]
    for n in local_names:
        nl = (n or "").strip().lower()
        if not nl:
            continue
        if nl == w or nl.startswith(w + ":") or nl.startswith(w + "-"):
            return True
        if base and (nl == base or nl.startswith(base + ":")):
            # si on demande :tag précis et local a un autre tag → encore "présent"
            # pour catalogue: considérer la famille installée comme OK
            return True
    return False


def models() -> List[str]:
    """
    Menu modèles: locaux + manquants du catalogue UNCENSORED_MODELS
    marqués « (à télécharger) ». Dolphin / uncensor en tête; MODEL défaut.
    """
    local = local_model_names()
    local_l = [(n or "").strip() for n in local if n]
    # ids locaux (sans marqueur) pour lookup
    installed_set = {n.lower() for n in local_l}

    def is_in(name: str) -> bool:
        return _name_installed(name, local_l) or name.lower() in installed_set

    labels: List[str] = []
    seen_ids: set = set()

    # 1) catalogue uncensored d'abord (défaut en tête)
    cat = list(UNCENSORED_MODELS)
    if MODEL in cat:
        cat = [MODEL] + [n for n in cat if n != MODEL]
    elif MODEL not in cat:
        cat = [MODEL] + cat

    for name in cat:
        nid = name.strip()
        if not nid or nid.lower() in seen_ids:
            continue
        seen_ids.add(nid.lower())
        labels.append(model_menu_label(nid, is_in(nid)))

    # 2) autres locaux (hors catalogue) — dolphin* avant le reste
    extras = [n for n in local_l if n.lower() not in seen_ids]
    dolphins = [n for n in extras if "dolphin" in n.lower() or "uncensor" in n.lower()]
    others = [n for n in extras if n not in dolphins]
    # skip aligned/guard comme suggestion prioritaire (on les garde s'ils sont locaux)
    for n in dolphins + others:
        nid = n.strip()
        key = nid.lower()
        if key in seen_ids:
            continue
        seen_ids.add(key)
        labels.append(nid)  # déjà local → pas de marqueur

    if not labels:
        return [model_menu_label(MODEL, False)]
    return labels


def needs_web(q: str) -> bool:
    x = q.lower()
    return any(k in x for k in (
        "actu", "nouvelle", "aujourd", "2024", "2025", "2026", "qui est",
        "guerre", "geopolit", "trump", "election", "prix", "wiki", "c'est quoi",
        "ormuz", "taiwan", "taïwan", "hugging", "nvidia", "carney",
    ))


# ── ADN léger : tasks.json ───────────────────────────────────────────────────

def load_tasks() -> list:
    data = loadj(TASKS_FILE, [])
    return data if isinstance(data, list) else []


def save_tasks(tasks: list) -> None:
    savej(TASKS_FILE, tasks)


def tool_get_task_list() -> List[Dict[str, Any]]:
    return load_tasks()


def tool_add_task(description: str, priority: str = "normal") -> Dict[str, Any]:
    tasks = load_tasks()
    item = {
        "id": uuid.uuid4().hex[:8],
        "description": (description or "").strip(),
        "status": "open",
        "priority": priority or "normal",
        "result": "",
    }
    if not item["description"]:
        raise ValueError("description vide")
    tasks.append(item)
    save_tasks(tasks)
    return item


def tool_update_task(
    task_id: str,
    status: Optional[str] = None,
    description: Optional[str] = None,
    priority: Optional[str] = None,
    result: Optional[str] = None,
) -> Dict[str, Any]:
    tasks = load_tasks()
    for t in tasks:
        if t.get("id") == task_id:
            if status is not None:
                t["status"] = status
            if description is not None:
                t["description"] = description
            if priority is not None:
                t["priority"] = priority
            if result is not None:
                t["result"] = result
            save_tasks(tasks)
            return t
    raise KeyError(f"tâche inconnue: {task_id}")


# ── tools (registry) ─────────────────────────────────────────────────────────

def tool_web_search(query: str, kind: str = "web", n: int = HUNT_N) -> List[Dict[str, str]]:
    return search_web(query, n=n, kind=kind)


def tool_read_page(url: str, limit: int = 8000) -> str:
    return read_page(url, limit=limit)


def tool_send_email(*_a, **_k) -> str:
    return "pas encore branché"


def tool_send_sms(*_a, **_k) -> str:
    return "pas encore branché"


TOOLS: Dict[str, Callable] = {
    "web_search": tool_web_search,
    "read_page": tool_read_page,
    "send_email": tool_send_email,
    "send_sms": tool_send_sms,
    "get_task_list": tool_get_task_list,
    "add_task": tool_add_task,
    "update_task": tool_update_task,
}


def _session_cache_key(query: str, source: str) -> str:
    return f"{source}::{query.lower().strip()}"


def session_cache_get(query: str, source: str) -> Optional[List[Dict[str, str]]]:
    key = _session_cache_key(query, source)
    with _SESSION_CACHE_LOCK:
        hit = _SESSION_SEARCH_CACHE.get(key)
        if not hit:
            return None
        if time.time() - hit.get("t", 0) > SESSION_CACHE_TTL:
            _SESSION_SEARCH_CACHE.pop(key, None)
            return None
        return list(hit.get("items") or [])


def session_cache_put(query: str, source: str, items: List[Dict[str, str]]) -> None:
    key = _session_cache_key(query, source)
    with _SESSION_CACHE_LOCK:
        cutoff = time.time() - SESSION_CACHE_TTL
        dead = [k for k, v in _SESSION_SEARCH_CACHE.items() if v.get("t", 0) < cutoff]
        for k in dead:
            _SESSION_SEARCH_CACHE.pop(k, None)
        _SESSION_SEARCH_CACHE[key] = {"t": time.time(), "items": list(items or [])}


def session_cache_recent(topic: str) -> bool:
    """True si un sujet VEILLE a été chassé récemment (n'importe quelle source)."""
    tlow = (topic or "").lower().strip()
    if not tlow:
        return False
    now_t = time.time()
    with _SESSION_CACHE_LOCK:
        for key, hit in _SESSION_SEARCH_CACHE.items():
            if now_t - hit.get("t", 0) > SESSION_CACHE_TTL:
                continue
            # key = source::query
            qpart = key.split("::", 1)[-1]
            if tlow == qpart or tlow in qpart or qpart in tlow:
                return True
    return False


def _looks_french(text: str) -> bool:
    t = text.lower()
    if re.search(r"[àâäéèêëïîôùûüçœæ]", t):
        return True
    fr_tokens = (
        " le ", " la ", " les ", " des ", " une ", " un ", " du ", " de ",
        " québec", " quebec", " canada", " comment ", " pourquoi ", " quoi ",
    )
    padded = f" {t} "
    return sum(1 for w in fr_tokens if w in padded) >= 2


def _short_synonym(query: str) -> Optional[str]:
    """Synonyme / reformulation courte heuristique (sans LLM)."""
    q = query.strip()
    low = q.lower()
    swaps = [
        ("actualité", "news"), ("nouvelles", "news"), ("guide", "tutoriel"),
        ("comment", "how to"), ("pourquoi", "why"), ("meilleur", "best"),
        ("problème", "issue"), ("erreur", "error"), ("santé", "health"),
        ("plante", "plant"), ("jardin", "gardening"),
    ]
    for a, b in swaps:
        if a in low:
            return re.sub(re.escape(a), b, q, count=1, flags=re.I).strip()
    # trim stopwords FR/EN for a shorter alt
    words = [w for w in re.split(r"\s+", q) if w.lower() not in {
        "le", "la", "les", "de", "des", "du", "un", "une", "et", "ou", "à", "a", "the", "of", "for",
    }]
    if 2 <= len(words) < len(q.split()) and len(words) >= 2:
        return " ".join(words[:6])
    return None


def build_source_query(query: str, source: str) -> str:
    """Applique le bias site:/région selon la source ciblée."""
    q = query.strip()
    src = source if source in SEARCH_SOURCES else "web"
    bias = SEARCH_SOURCE_BIAS.get(src)
    if src == "news":
        # news: query brute; fallback sites ajouté ailleurs si news DDGS vide
        return q
    if bias:
        return f"{q} {bias}"
    return q


def multi_query_variants(query: str) -> List[str]:
    """2-3 reformulations: original + anglais si FR + synonyme court."""
    q = query.strip()
    out: List[str] = []
    seen = set()

    def add(v: str):
        k = v.lower().strip()
        if k and k not in seen:
            seen.add(k)
            out.append(v.strip())

    add(q)
    if _looks_french(q):
        # variante « anglaise » légère: synonyme swaps + strip accents heuristique
        en = q
        for a, b in (
            ("actualité", "news"), ("nouvelles", "latest news"), ("québec", "Quebec"),
            ("quebec", "Quebec"), ("comment", "how to"), ("pourquoi", "why"),
            ("santé", "health"), ("plante", "plant"), ("jardin", "garden"),
            ("erreur", "error"), ("tutoriel", "tutorial"), ("meilleur", "best"),
        ):
            if a in en.lower():
                en = re.sub(re.escape(a), b, en, count=1, flags=re.I)
        add(en)
    syn = _short_synonym(q)
    if syn:
        add(syn)
    if len(out) < 2:
        add(f"{q} overview")
    return out[:3]


def _norm_row(row: dict) -> Optional[Dict[str, str]]:
    url = row.get("href") or row.get("url") or ""
    if not url.startswith("http"):
        return None
    if any(x in url.lower() for x in ("signup", "login", "privacy")):
        return None
    return {
        "url": url,
        "title": clean(row.get("title") or url),
        "snippet": clean(row.get("body") or "")[:240],
    }


def _short_exc(e: BaseException, limit: int = 120) -> str:
    msg = str(e).strip() or type(e).__name__
    # DDGS: "No results found." / ConnectError / 403 / ratelimit
    low = msg.lower()
    if "no results" in low:
        return "0 résultats"
    if "403" in low or "forbidden" in low:
        return "403"
    if "ratelimit" in low or "rate limit" in low or "too many" in low:
        return "rate-limit"
    if _is_timeout(e) or "timed out" in low or "timeout" in low:
        return "timeout"
    if "tls" in low or "handshake" in low or "eof" in low:
        return "TLS/réseau"
    if "requesterror" in low or "httpstatus" in low:
        return f"requête ({type(e).__name__})"
    if _is_conn_err(e) or "connecterror" in low or "connect" in low:
        return "connexion"
    return f"{type(e).__name__}: {msg[:max(40, limit - 20)]}"


def _engine_text(
    eng, query: str, n: int, backend: str,
    errors: Optional[List[str]] = None, **kw
) -> List[Dict[str, str]]:
    try:
        raw = list(eng.text(query, max_results=n, region="fr-fr", backend=backend, **kw) or [])
    except Exception as e:
        kind = "timeout" if _is_timeout(e) else ("connexion" if _is_conn_err(e) else "err")
        brief = _short_exc(e)
        log(f"text/{backend} [{kind}] {e}")
        if errors is not None:
            errors.append(f"text/{backend}: {brief}")
        return []
    out, seen = [], set()
    for row in raw:
        it = _norm_row(row)
        if not it or it["url"] in seen:
            continue
        seen.add(it["url"])
        out.append(it)
    if not out and errors is not None:
        errors.append(f"text/{backend}: 0 résultats")
    return out


def _engine_news(
    eng, query: str, n: int, backend: str,
    errors: Optional[List[str]] = None,
) -> List[Dict[str, str]]:
    try:
        raw = list(eng.news(query, max_results=n, region="fr-fr", backend=backend) or [])
    except Exception as e:
        kind = "timeout" if _is_timeout(e) else ("connexion" if _is_conn_err(e) else "err")
        brief = _short_exc(e)
        log(f"news/{backend} [{kind}] {e}")
        if errors is not None:
            errors.append(f"news/{backend}: {brief}")
        return []
    out, seen = [], set()
    for row in raw:
        it = _norm_row(row)
        if not it or it["url"] in seen:
            continue
        seen.add(it["url"])
        out.append(it)
    if not out and errors is not None:
        errors.append(f"news/{backend}: 0 résultats")
    return out


def _ddgs_try_text(
    eng, query: str, n: int,
    backends: Tuple[str, ...] = DDGS_TEXT_BACKENDS,
    errors: Optional[List[str]] = None,
    cancel: Optional[threading.Event] = None,
    **kw,
) -> List[Dict[str, str]]:
    """Essaie plusieurs backends DDGS text; pause courte entre échecs (rate-limit)."""
    last: List[Dict[str, str]] = []
    for i, tb in enumerate(backends):
        if cancel and cancel.is_set():
            break
        last = _engine_text(eng, query, n, tb, errors=errors, **kw)
        if last:
            return last
        if i + 1 < len(backends) and DDGS_RETRY_SLEEP > 0:
            time.sleep(DDGS_RETRY_SLEEP)
    return last


def _ddgs_try_news(
    eng, query: str, n: int,
    backends: Tuple[str, ...] = DDGS_NEWS_BACKENDS,
    errors: Optional[List[str]] = None,
    cancel: Optional[threading.Event] = None,
) -> List[Dict[str, str]]:
    last: List[Dict[str, str]] = []
    for i, nb in enumerate(backends):
        if cancel and cancel.is_set():
            break
        last = _engine_news(eng, query, n, nb, errors=errors)
        if last:
            return last
        if i + 1 < len(backends) and DDGS_RETRY_SLEEP > 0:
            time.sleep(DDGS_RETRY_SLEEP)
    return last


def _summarize_ddgs_errors(errors: List[str], limit: int = 4) -> str:
    if not errors:
        return "aucun détail moteur"
    # dédup en gardant l'ordre
    seen, uniq = set(), []
    for e in errors:
        if e in seen:
            continue
        seen.add(e)
        uniq.append(e)
    head = uniq[:limit]
    extra = len(uniq) - len(head)
    s = " · ".join(head)
    if extra > 0:
        s += f" · +{extra}"
    return s


def _heuristic_variants(query: str) -> List[str]:
    """Variantes locales sans LLM — délègue à multi_query_variants (FR→EN + synonyme)."""
    return multi_query_variants(query)


def query_variants(query: str, use_ollama: bool = False, model: str = MODEL,
                   cancel: Optional[threading.Event] = None) -> List[str]:
    """formuler : variantes heuristiques (+ option ollama minuscule)."""
    base = _heuristic_variants(query)
    if not use_ollama or not requests or (cancel and cancel.is_set()):
        return base
    try:
        r = ollama_request(
            "POST",
            "/api/chat",
            json_body={
                "model": model,
                "stream": False,
                "options": {"temperature": 0.2},
                "messages": [
                    {
                        "role": "system",
                        "content": "Tu reformules. Réponds UNIQUEMENT avec 1 variante de requête web, 4-10 mots, rien d'autre.",
                    },
                    {"role": "user", "content": f"Requête: {query}"},
                ],
            },
            timeout=(OLLAMA_CONNECT, 20),
            retries=2,
            cancel=cancel,
        )
        alt = ((r.json().get("message") or {}).get("content") or "").strip()
        alt = re.sub(r'[\n"«»]', " ", alt).strip()[:80]
        if alt and alt.lower() not in {x.lower() for x in base}:
            base.append(alt)
    except Exception as e:
        log(f"variants ollama: {e}")
    return base[:3]


ProgressCb = Callable[[str, str, Optional[str]], None]


def dig_top_pages(
    items: List[Dict[str, str]],
    n: int = 3,
    model: str = MODEL,
    cancel: Optional[threading.Event] = None,
    on_progress: Optional[ProgressCb] = None,
) -> List[Dict[str, str]]:
    """Fetch HTML des N premiers URLs, extrait texte, résumé Ollama court. Ignore échecs."""
    if not items or not (requests and BeautifulSoup):
        return items
    to_read = [i for i in items[:n] if i.get("url") and not is_dead(i["url"])]
    enriched_urls: List[str] = []

    def _prog(detail: str):
        if on_progress:
            try:
                on_progress("enrichir", "running", detail)
            except Exception:
                pass

    for i, it in enumerate(to_read, 1):
        if cancel and cancel.is_set():
            break
        url = it["url"]
        _prog(f"creuser {i}/{len(to_read)} · {host_of(url)}")
        body = ""
        try:
            r = http().get(url, timeout=(HTTP_DIG_CONNECT, HTTP_DIG_READ))
            r.raise_for_status()
            if not r.encoding or r.encoding.lower() in ("iso-8859-1", "ascii"):
                r.encoding = r.apparent_encoding or "utf-8"
            soup = BeautifulSoup(r.text, "html.parser")
            for t in soup(["nav", "footer", "header", "script", "style", "aside", "form", "noscript"]):
                t.decompose()
            node = soup.find("article") or soup.find("main") or soup
            text = clean(" ".join(
                p.get_text(" ", strip=True)
                for p in node.find_all("p")
                if len(p.get_text(strip=True)) > 40
            ))
            if len(text) < 80:
                og = soup.find("meta", attrs={"property": "og:description"}) or soup.find(
                    "meta", attrs={"name": "description"}
                )
                text = clean((og or {}).get("content") or "") if og else text
            body = text[:3500] if len(text) >= 80 else ""
        except Exception as e:
            log(f"dig_top {url}: {e}")
            body = ""
        if not body:
            continue
        summary = ""
        if requests and not (cancel and cancel.is_set()):
            try:
                rr = ollama_request(
                    "POST",
                    "/api/chat",
                    json_body={
                        "model": model,
                        "stream": False,
                        "options": {"temperature": 0.2},
                        "messages": [
                            {
                                "role": "system",
                                "content": (
                                    "Résume en 4-6 phrases max, français, faits seulement. "
                                    "Pas de liens, pas de moraline."
                                ),
                            },
                            {
                                "role": "user",
                                "content": f"Titre: {it.get('title', '')}\n\n{body[:2800]}",
                            },
                        ],
                    },
                    timeout=(OLLAMA_CONNECT, 30),
                    retries=2,
                    cancel=cancel,
                )
                summary = ((rr.json().get("message") or {}).get("content") or "").strip()
            except Exception as e:
                log(f"dig_top summarize: {ollama_err_fr(e)}")
                summary = ""
        it2 = dict(it)
        it2["body"] = body[:4000]
        if summary:
            it2["dig_summary"] = summary[:1200]
        for j, p in enumerate(items):
            if p.get("url") == url:
                items[j] = it2
                break
        enriched_urls.append(url)
    return items



def _query_tokens(query: str) -> List[str]:
    """Tokens utiles pour score de pertinence (FR/EN, ignore stopwords courts)."""
    stop = {
        "a", "à", "au", "aux", "de", "des", "du", "d", "le", "la", "les", "un", "une",
        "et", "ou", "en", "pour", "par", "sur", "dans", "avec", "sans", "the", "of",
        "and", "or", "to", "in", "on", "for", "with", "from", "vs", "versus", "quoi",
        "comment", "pourquoi", "quel", "quelle", "quels", "quelles", "est", "ce", "se",
        "qui", "que", "ne", "pas", "plus", "moins", "très", "tres", "comme", "entre",
    }
    raw = re.findall(r"[a-zA-Zàâäéèêëïîôùûüçœæ0-9]{3,}", (query or "").lower())
    out = []
    seen = set()
    for w in raw:
        if w in stop or w in seen:
            continue
        seen.add(w)
        out.append(w)
    return out


def relevance_score(query: str, title: str, snippet: str = "") -> float:
    """Score simple titre/snippet vs query (0 = hors-sujet)."""
    toks = _query_tokens(query)
    if not toks:
        return 1.0
    blob = f"{title or ''} {snippet or ''}".lower()
    if not blob.strip():
        return 0.0
    hits = sum(1 for w in toks if w in blob)
    # bonus racine courte (ex: parasit → antiparasitaires)
    stems = 0
    for w in toks:
        if len(w) >= 5:
            stem = w[: max(4, len(w) - 2)]
            if stem in blob:
                stems += 1
    return hits + 0.35 * stems


def filter_relevant_hits(
    query: str,
    items: List[Dict[str, str]],
    *,
    min_score: float = 0.75,
    keep_min: int = 3,
) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    """Écarte titres trop éloignés de la query avant synthèse.
    Retourne (kept, dropped). Si trop peu passent le seuil, garde les meilleurs.
    """
    if not items:
        return [], []
    scored = []
    for it in items:
        sc = relevance_score(query, it.get("title") or "", it.get("snippet") or "")
        scored.append((sc, it))
    scored.sort(key=lambda x: -x[0])
    kept = [it for sc, it in scored if sc >= min_score]
    dropped = [it for sc, it in scored if sc < min_score]
    if len(kept) < keep_min:
        # garder quand même les meilleurs pour ne pas vider le filet
        need = keep_min - len(kept)
        extra = [it for sc, it in scored if sc < min_score][:need]
        kept = kept + extra
        dropped = [it for it in dropped if it not in extra]
    return kept, dropped



def md_to_html(md: str, title: str = "Padawan") -> str:
    out, in_code, in_ul = [], False, False
    def inline(t: str) -> str:
        t = html.escape(t)
        t = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', t)
        t = re.sub(r"(?<![\"'>])(https?://[^\s<]+)", r'<a href="\1">\1</a>', t)
        t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
        t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
        t = re.sub(r"(?<![\w*])\*(?!\s)([^*]+?)\*", r"<i>\1</i>", t)
        return t
    for line in md.split("\n"):
        st = line.strip()
        if st.startswith("```"):
            out.append("</pre>" if in_code else "<pre>"); in_code = not in_code; continue
        if in_code:
            out.append(html.escape(line)); continue
        mb = re.match(r"^\s*[-*+•]\s+(.*)$", line)
        if mb:
            if not in_ul:
                out.append("<ul>"); in_ul = True
            out.append(f"<li>{inline(mb.group(1))}</li>"); continue
        if in_ul:
            out.append("</ul>"); in_ul = False
        mh = re.match(r"^(#{1,6})\s+(.*)$", st)
        if mh:
            lv = len(mh.group(1)); out.append(f"<h{lv}>{inline(mh.group(2))}</h{lv}>")
        elif st:
            out.append(f"<p>{inline(st)}</p>")
    if in_ul:
        out.append("</ul>")
    body = "\n".join(out)
    return ("<!doctype html><html lang='fr'><meta charset='utf-8'><title>" + html.escape(title) + "</title>"
            "<style>body{font:16px/1.6 Segoe UI,sans-serif;max-width:860px;margin:2em auto;padding:0 1em;"
            "background:#0f131a;color:#f7f9fc}a{color:#9ad0ff}h1,h2{color:#e4c07a}h3{color:#7ec8e8}"
            "code,pre{background:#222a37;color:#7aefc0;padding:2px 4px}pre{padding:10px;overflow:auto}</style>"
            f"<body>{body}</body></html>")


def md_to_speech(md: str) -> str:
    t = re.sub(r"```.*?```", " (bloc de code) ", md, flags=re.S)
    t = re.split(r"\n\*\*Sources\*\*|\n#+\s*Sources", t)[0]
    t = re.sub(r"https?://\S+", "", t)
    t = re.sub(r"\[(\d{1,2})\]", "", t)
    t = re.sub(r"[#*_`>•]", "", t)
    return re.sub(r"\s+\n", "\n", t).strip()[:6000]


_TTS_PS = r"""
$ErrorActionPreference='Stop'
$txt = [IO.File]::ReadAllText($args[0], [Text.Encoding]::UTF8)
try {
  Add-Type -AssemblyName System.Runtime.WindowsRuntime
  $null = [Windows.Media.SpeechSynthesis.SpeechSynthesizer,Windows.Media,ContentType=WindowsRuntime]
  $null = [Windows.Storage.Streams.DataReader,Windows.Storage.Streams,ContentType=WindowsRuntime]
  $synth = New-Object Windows.Media.SpeechSynthesis.SpeechSynthesizer
  $v = [Windows.Media.SpeechSynthesis.SpeechSynthesizer]::AllVoices | Where-Object { $_.Language -eq 'fr-CA' } | Select-Object -First 1
  if (-not $v) { $v = [Windows.Media.SpeechSynthesis.SpeechSynthesizer]::AllVoices | Where-Object { $_.Language -like 'fr*' } | Select-Object -First 1 }
  if ($v) { $synth.Voice = $v }
  $asT = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
  $op = $synth.SynthesizeTextToStreamAsync($txt)
  $stream = $asT.MakeGenericMethod([Windows.Media.SpeechSynthesis.SpeechSynthesisStream]).Invoke($null, @($op)).Result
  $wav = [IO.Path]::Combine($env:TEMP, 'padawan_tts.wav')
  $rd = New-Object Windows.Storage.Streams.DataReader($stream.GetInputStreamAt(0))
  $ld = $asT.MakeGenericMethod([UInt32]).Invoke($null, @($rd.LoadAsync([UInt32]$stream.Size))).Result
  $bytes = New-Object byte[] $stream.Size; $rd.ReadBytes($bytes)
  [IO.File]::WriteAllBytes($wav, $bytes)
  (New-Object Media.SoundPlayer $wav).PlaySync()
} catch {
  Add-Type -AssemblyName System.Speech
  $s = New-Object System.Speech.Synthesis.SpeechSynthesizer
  $s.Speak($txt)
}
"""


def speak_fr(text: str):
    """Lecture à voix haute (voix fr-CA Windows si dispo). Retourne le Popen (kill = stop)."""
    if not text.strip() or os.name != "nt":
        return None
    tmp = os.environ.get("TEMP") or "."
    ps1, txt = os.path.join(tmp, "padawan_tts.ps1"), os.path.join(tmp, "padawan_tts.txt")
    with open(ps1, "w", encoding="utf-8-sig") as fh:
        fh.write(_TTS_PS)
    with open(txt, "w", encoding="utf-8") as fh:
        fh.write(text)
    return subprocess.Popen(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps1, txt],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def suggest_followups(model: str, q: str, answer: str) -> List[str]:
    """3 questions de suivi courtes (JSON). Jamais d'exception."""
    if not requests:
        return []
    try:
        r = ollama_request(
            "POST", "/api/chat",
            json_body={
                "model": model, "stream": False, "format": "json",
                "options": {"temperature": 0.5, "num_predict": 160},
                "messages": [
                    {"role": "system", "content": (
                        "Propose 3 questions de suivi courtes (max 9 mots), pertinentes et intelligentes, "
                        "que Marc pourrait poser ensuite, en français québécois naturel, à la 1re personne. "
                        "JSON uniquement: {\"questions\": [\"...\", \"...\", \"...\"]}")},
                    {"role": "user", "content": f"Question: {q}\n\nRéponse:\n{answer[:2500]}"},
                ],
            },
            timeout=(OLLAMA_CONNECT, 45), retries=1,
        )
        raw = ((r.json().get("message") or {}).get("content") or "")
        data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1]) if "{" in raw else {}
        qs = [str(x).strip().strip('"') for x in (data.get("questions") or [])]
        return [x for x in qs if 4 <= len(x) <= 90][:3]
    except Exception as e:
        log(f"followups: {e}")
        return []


# ── Intention de recherche (v39h) ─────────────────────────────────────────────
MOIS_FR = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
           "septembre", "octobre", "novembre", "décembre")
DICT_HOSTS = (
    "wiktionary.org", "linguee.fr", "linguee.com", "reverso.net", "larousse.fr", "lerobert.com",
    "cnrtl.fr", "wordreference.com", "dictionnaire.reverso.net", "le-dictionnaire.com",
    "usito.usherbrooke.ca", "dictionary.cambridge.org", "merriam-webster.com", "deepl.com",
    "translate.google.com", "glosbe.com", "context.reverso.net", "bab.la", "linternaute.fr",
    "dictionnaire.lerobert.com", "expressio.fr", "lesexpressions.fr", "hinative.com", "frenchlearner.com", "reelang.com", "lawlessfrench.com", "french.stackexchange.com", "collinsdictionary.com", "wordhippo.com", "urbandictionary.com", "dictionnaire-academie.fr", "synonymo.fr",
)
NEWS_HOSTS = (
    "radio-canada.ca", "lapresse.ca", "ledevoir.com", "journaldemontreal.com", "tvanouvelles.ca",
    "lemonde.fr", "lefigaro.fr", "liberation.fr", "francetvinfo.fr", "franceinfo.fr", "20minutes.fr",
    "leparisien.fr", "bfmtv.com", "rfi.fr", "france24.com", "tf1info.fr", "ouest-france.fr",
    "lexpress.fr", "lepoint.fr", "nouvelobs.com", "mediapart.fr", "huffingtonpost.fr", "europe1.fr",
    "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk", "theguardian.com", "cbc.ca", "ctvnews.ca",
    "lesoleil.com", "ledroit.com", "noovo.info", "lactualite.com", "politico.eu", "euronews.com",
    "afp.com", "nytimes.com", "lesechos.fr", "la-croix.com", "cnn.com",
)
_NEWS_WORDS = (
    "actualité", "actualite", "nouvelles", "news", "en ce moment", "présentement", "presentement",
    "situation", "bordel", "chaos", "crise", "élection", "election", "gouvernement", "premier ministre",
    "président", "president", "grève", "greve", "manif", "guerre", "aujourd'hui", "cette semaine",
    "ce mois", "récemment", "dernières", "derniers", "qu'est-ce qui se passe", "ça va mal", "ca va mal",
    "tarifs", "budget", "assemblée", "ministre", "politique",
)
_WORD_PAT = re.compile(
    r"(que veut dire|ça veut dire quoi|ca veut dire quoi|signification|définition|definition|étymologie|"
    r"etymologie|origine du mot|traduction|traduire|synonyme|comment on dit|orthographe|le mot\b)", re.I)


def _host_in(url: str, hosts) -> bool:
    h = host_of(url).lower()
    return any(h == d or h.endswith("." + d) for d in hosts)


def _today_fr() -> Tuple[str, str]:
    t = time.localtime()
    return f"{t.tm_mday} {MOIS_FR[t.tm_mon - 1]} {t.tm_year}", f"{MOIS_FR[t.tm_mon - 1]} {t.tm_year}"


def _heuristic_intent(query: str) -> str:
    low = query.lower()
    if _WORD_PAT.search(low):
        return "mot"
    if any(w in low for w in _NEWS_WORDS):
        return "actualite"
    return "general"


def understand_query(query: str, model: str = MODEL,
                     cancel: Optional[threading.Event] = None) -> Dict[str, Any]:
    """Comprend l'intention AVANT de chercher: LLM -> 2-4 requêtes web pertinentes.
    Jamais d'exception: sans Ollama -> heuristique locale."""
    day, month = _today_fr()
    intent = _heuristic_intent(query)
    res: Dict[str, Any] = {"intent": intent, "queries": [], "topic": "", "llm": False}
    if requests and not (cancel and cancel.is_set()):
        try:
            sysm = (
                "Tu transformes une question de Marc (Québécois, langage familier) en requêtes de moteur de recherche. "
                f"Date du jour: {day}. "
                "Comprends l'INTENTION réelle, pas les mots au pied de la lettre: "
                "« c'est le bordel en France » = la situation politique/sociale actuelle en France, "
                "pas le mot « bordel ». Expressions québécoises: « ça brasse », « c'est la marde », "
                "« c'est quoi l'affaire avec <organisation/personne/lieu> » = actualite (controverse récente), même si c'est une entreprise comme Hydro-Québec. "
                "intent = \"actualite\" (événements, politique, social, économie récents), "
                "\"mot\" (sens, origine, traduction d'un mot), \"technique\" (informatique, électronique, code, comment faire), "
                "ou \"general\". "
                f"Pour actualite: ajoute « {month} » et/ou « actualité » dans les requêtes, nomme les acteurs/sujets probables. "
                "Écris 2 à 4 requêtes courtes (3-9 mots), en français (une peut être en anglais si utile), "
                "sans guillemets ni opérateurs. N'utilise JAMAIS un mot familier comme mot-clé sauf si intent=mot. "
                "Réponds UNIQUEMENT en JSON: {\"intent\": \"...\", \"sujet\": \"...\", \"requetes\": [\"...\", \"...\"]}"
            )
            r = ollama_request(
                "POST", "/api/chat",
                json_body={
                    "model": model, "stream": False, "format": "json",
                    "options": {"temperature": 0.1, "num_predict": 200},
                    "messages": [{"role": "system", "content": sysm},
                                 {"role": "user", "content": query}],
                },
                timeout=(OLLAMA_CONNECT, 60), retries=1, cancel=cancel,
            )
            raw = ((r.json().get("message") or {}).get("content") or "").strip()
            data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1]) if "{" in raw else {}
            qs = [re.sub(r'["«»]', "", str(x)).strip()[:100] for x in (data.get("requetes") or data.get("queries") or [])]
            qs = [x for x in qs if len(x) >= 3][:4]
            it = str(data.get("intent") or "").lower().strip()
            if it in ("actualite", "actualité", "mot", "technique", "general", "général"):
                res["intent"] = {"actualité": "actualite", "général": "general"}.get(it, it)
            if intent == "mot":
                res["intent"] = "mot"  # demande explicite sur un mot: prioritaire
            if qs:
                res["queries"], res["llm"] = qs, True
            res["topic"] = str(data.get("sujet") or "")[:120]
        except Exception as e:
            log(f"understand_query: {ollama_err_fr(e)}")
    if not res["queries"]:
        base = multi_query_variants(query)
        if res["intent"] == "actualite":
            base = [f"{base[0]} actualité {month}"] + base
        res["queries"] = base[:3]
    if res["intent"] == "actualite" and not any(month.split()[0] in q.lower() or "actualit" in q.lower()
                                                for q in res["queries"]):
        res["queries"][0] = f"{res['queries'][0]} {month}"
    # dédup
    seen, out = set(), []
    for q in res["queries"]:
        if q.lower() not in seen:
            seen.add(q.lower()); out.append(q)
    res["queries"] = out[:4]
    return res


def rank_by_intent(items: List[Dict[str, str]], intent: str) -> List[Dict[str, str]]:
    """Exclut dictionnaires/traducteurs (sauf intent=mot); actualité -> sources de nouvelles d'abord."""
    if intent != "mot":
        items = [i for i in items if not _host_in(i.get("url", ""), DICT_HOSTS)]
    if intent == "actualite":
        def k(i):
            news = _host_in(i.get("url", ""), NEWS_HOSTS) or i.get("_news")
            wiki = "wikipedia.org" in host_of(i.get("url", ""))
            u = i.get("url", "")
            try:
                segs = [x for x in urlparse(u).path.split("/") if x]
            except Exception:
                segs = []
            hubby = len(segs) <= 1 or "archives" in u.lower() or is_hub(u)
            return (1 if hubby else 0, 0 if news else (2 if wiki else 1), 0 if i.get("date") else 1)
        items = sorted(items, key=k)
    return items


def hunt_pipeline(
    query: str,
    kind: str = "web",
    n: int = HUNT_N,
    mode: str = "multi",
    on_progress: Optional[ProgressCb] = None,
    cancel: Optional[threading.Event] = None,
    model: str = MODEL,
    source: Optional[str] = None,
    dig_top3: bool = False,
    use_session_cache: bool = True,
) -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
    """Pipeline multi-étape + sources ciblées + multi-requêtes parallèles + cache session."""

    def prog(step: str, state: str, detail: Optional[str] = None):
        if on_progress:
            try:
                on_progress(step, state, detail)
            except Exception as e:
                log(f"progress cb: {e}")

    def cancelled() -> bool:
        return bool(cancel and cancel.is_set())

    # source ciblée (v26); kind reste alias / legacy
    legacy_map = {"actus": "news", "wiki": "web", "web": "web"}
    src = source or kind
    if src not in SEARCH_SOURCES:
        src = legacy_map.get(src, "web")
    n = max(3, min(HUNT_N_MAX, int(n or HUNT_N)))

    meta: Dict[str, Any] = {
        "variants": [],
        "engine_hits": {},
        "enriched": [],
        "mode": mode,
        "kind": kind,
        "source": src,
        "from_cache": False,
        "dig_top3": dig_top3,
        "ddgs_errors": [],
        "widened": False,
        "attempts": [],
    }
    if not DDGS:
        raise RuntimeError("Lance padawanlibinstall.bat (ddgs manquant)")

    # Cache session (anti-doublon ~10 min)
    if use_session_cache:
        cached = session_cache_get(query, src)
        if cached:
            prog("formuler", "done", "cache")
            prog("moteurs", "done", "cache")
            prog("filtrer", "done", f"cache → {len(cached)} uniques")
            prog("enrichir", "done", "cache")
            meta["from_cache"] = True
            return cached[:n], meta

    # Cache disque rapide (comportement v25)
    if mode == "rapide":
        cache, key = loadj(CACHE_FILE, {}), f"{src}::{query.lower().strip()}"
        hit = cache.get(key)
        if hit and time.time() - hit.get("t", 0) < CACHE_TTL:
            items = hit.get("items", [])
            prog("formuler", "done", "cache disque")
            prog("moteurs", "done", "cache")
            prog("filtrer", "done", f"Fusion → {len(items)} uniques")
            prog("enrichir", "done", "skip")
            session_cache_put(query, src, items)
            return items, {**meta, "from_cache": True}

    # 1. formuler — 2-3 reformulations
    prog("formuler", "running", "variantes…")
    if cancelled():
        prog("formuler", "fail", "annulé")
        return [], meta
    prog("formuler", "running", "comprendre l'intention.")
    und = understand_query(query, model=model, cancel=cancel)
    intent = und["intent"]
    meta["intent"], meta["topic"], meta["llm_queries"] = intent, und.get("topic", ""), und.get("llm")
    variants = und["queries"] or multi_query_variants(query)
    # appliquer bias source sur chaque variante
    biased = [build_source_query(v, src) for v in variants]
    meta["variants"] = variants
    meta["biased"] = biased
    prog("formuler", "done", f"{intent} · {len(variants)} requête(s) · {src}")

    # 2. moteurs — parallèle sur variantes (backends robustes yahoo/bing/auto…)
    prog("moteurs", "running", "lancement parallèle…")
    if cancelled():
        prog("moteurs", "fail", "annulé")
        return [], meta

    buckets: Dict[str, List[Dict[str, str]]] = {}
    lock = threading.Lock()
    err_sink: List[str] = meta["ddgs_errors"]

    def _note(name: str, items: list):
        with lock:
            buckets[name] = items
            meta["engine_hits"][name] = len(items)
            meta["attempts"].append(f"{name}→{len(items)}")
        prog("moteurs", "running", f"{name} → {len(items)}")

    def _run_one(name: str, qtext: str, use_news: bool = False):
        if cancelled():
            return
        local_err: List[str] = []
        try:
            eng = DDGS()
            if use_news or src == "news":
                items = _ddgs_try_news(
                    eng, qtext, n + 4, backends=DDGS_NEWS_BACKENDS,
                    errors=local_err, cancel=cancel,
                )
                if not items:
                    # fallback: text + sites news
                    fb = f"{qtext} {NEWS_FALLBACK_SITES}"
                    items = _ddgs_try_text(
                        eng, fb, n + 2, backends=DDGS_TEXT_FALLBACK,
                        errors=local_err, cancel=cancel, timelimit="w",
                    )
                    if not items:
                        items = _ddgs_try_text(
                            eng, fb, n + 2, backends=DDGS_TEXT_FALLBACK,
                            errors=local_err, cancel=cancel,
                        )
                for _it in items:
                    _it["_news"] = True
                _note(name, items)
            elif mode == "rapide":
                multi = _ddgs_try_text(
                    eng, qtext, n + 4, backends=DDGS_TEXT_BACKENDS,
                    errors=local_err, cancel=cancel,
                )
                _note(name, multi)
            else:
                items = _ddgs_try_text(
                    eng, qtext, n + 2, backends=DDGS_TEXT_FALLBACK,
                    errors=local_err, cancel=cancel,
                )
                _note(name, items)
                if mode in ("multi", "profond") and not cancelled() and items:
                    # 2e passe: autre combo pour diversité
                    extra = _ddgs_try_text(
                        eng, qtext, max(3, n // 2),
                        backends=("bing,yahoo", "auto", "mojeek"),
                        errors=local_err, cancel=cancel,
                    )
                    if extra:
                        _note(name + "-extra", extra)
        except Exception as e:
            brief = _short_exc(e)
            log(f"engine {name}: chasse DDGS échouée — {e}")
            local_err.append(f"{name}: {brief}")
            _note(name, [])
        if local_err:
            with lock:
                err_sink.extend(local_err)

    # parallèle: chaque variante dans un thread
    jobs = []
    for i, bq in enumerate(biased):
        jobs.append((f"v{i+1}", bq, src == "news"))
    # mode multi/profond: aussi news secondaire si source web large
    if intent == "actualite":
        for i, v in enumerate(variants[:3]):
            jobs.append((f"news{i+1}", v, True))
    elif src == "web" and mode in ("multi", "profond"):
        jobs.append(("news-web", variants[0], True))

    max_workers = min(6, max(1, len(jobs)))
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futs = [pool.submit(_run_one, name, qtext, use_news) for name, qtext, use_news in jobs]
        for fut in as_completed(futs):
            if cancelled():
                break
            try:
                fut.result()
            except Exception as e:
                log(f"parallel hunt: {e}")
                err_sink.append(f"parallel: {_short_exc(e)}")

    if cancelled():
        prog("moteurs", "fail", "annulé")
        return [], meta

    # fallback chaîne si trop peu: backends restants + requête sans bias
    total_so_far = sum(len(v) for v in buckets.values())
    had_bias = bool(SEARCH_SOURCE_BIAS.get(src)) and src != "news"
    if total_so_far < 3 and not cancelled():
        prog("moteurs", "running", "fallback moteurs…")
        try:
            eng = DDGS()
            # 1) même requête biasée, backends complets
            fb = _ddgs_try_text(
                eng, biased[0], n + 4, backends=DDGS_TEXT_BACKENDS,
                errors=err_sink, cancel=cancel,
            )
            _note("fallback", fb)
            total_so_far = sum(len(v) for v in buckets.values())
            # 2) si bias source → retry SANS bias (élargi au web)
            if total_so_far < 3 and had_bias and variants:
                prog("moteurs", "running", "élargi au web (sans bias)…")
                plain = _ddgs_try_text(
                    eng, variants[0], n + 4, backends=DDGS_TEXT_BACKENDS,
                    errors=err_sink, cancel=cancel,
                )
                if plain:
                    _note("web-élargie", plain)
                    meta["widened"] = True
                    meta["widen_note"] = "élargi au web"
                total_so_far = sum(len(v) for v in buckets.values())
            # 3) dernière chance: 2e variante brute
            if total_so_far < 3 and len(variants) > 1:
                plain2 = _ddgs_try_text(
                    eng, variants[1], n + 4, backends=DDGS_TEXT_FALLBACK,
                    errors=err_sink, cancel=cancel,
                )
                if plain2:
                    _note("fallback-v2", plain2)
                    if had_bias:
                        meta["widened"] = True
                        meta["widen_note"] = "élargi au web"
        except Exception as e:
            log(f"ddgs fallback: {e}")
            err_sink.append(f"fallback: {_short_exc(e)}")

    hits_summary = ", ".join(f"{k}→{v}" for k, v in meta["engine_hits"].items())
    total_hits = sum(meta["engine_hits"].values()) if meta["engine_hits"] else 0
    err_summary = _summarize_ddgs_errors(err_sink)
    if total_hits == 0:
        meta["ddgs_error"] = err_summary
        detail = f"0 hits · {err_summary}"
        if meta.get("widened"):
            detail += " · élargi au web"
        prog("moteurs", "fail", detail[:80])
    else:
        done_detail = hits_summary or "0"
        if meta.get("widened"):
            done_detail = f"élargi au web · {done_detail}"
        prog("moteurs", "done", done_detail[:80])
        if meta.get("widened"):
            meta["search_note"] = "élargi au web (bias source sans hits)"

    # 3. filtrer / dédoublonner par URL
    prog("filtrer", "running", "dédupe…")
    if cancelled():
        prog("filtrer", "fail", "annulé")
        return [], meta
    merged, seen = [], set()
    for src_items in buckets.values():
        for it in src_items:
            u = it["url"]
            if u in seen:
                continue
            seen.add(u)
            merged.append(it)
    alive = [i for i in merged if not is_dead(i["url"])]
    n_dict = len(alive)
    ranked = sorted(
        alive,
        key=lambda i: (0 if not is_hub(i["url"]) else 1, -len(i.get("snippet") or "")),
    )
    ranked = rank_by_intent(ranked, intent)
    meta["dict_dropped"] = n_dict - len(ranked)
    non_hub = [i for i in ranked if not is_hub(i["url"])]
    picked = (non_hub or ranked)[: max(n, HUNT_N_MAX)]
    # Filtre hors-sujet (titres trop éloignés de la query) avant synthèse
    before_rel = len(picked)
    rel_q = " ".join([query] + list(variants)) if intent != "mot" else query
    kept_rel, dropped_rel = filter_relevant_hits(rel_q, picked, keep_min=min(3, n))
    kept_rel = rank_by_intent(kept_rel, intent)
    meta["relevance_dropped"] = [
        {"title": (d.get("title") or "")[:120], "url": d.get("url", "")}
        for d in dropped_rel[:12]
    ]
    picked = kept_rel[:n]
    drop_n = before_rel - len(picked)
    detail_f = f"Fusion → {len(picked)} uniques (sur {len(merged)})"
    if drop_n > 0:
        detail_f += f" · −{drop_n} hors-sujet"
    prog("filtrer", "done", detail_f)

    if mode == "rapide":
        cache, key = loadj(CACHE_FILE, {}), f"{src}::{query.lower().strip()}"
        cutoff = time.time() - CACHE_TTL
        cache = {k: v for k, v in cache.items() if isinstance(v, dict) and v.get("t", 0) >= cutoff}
        cache[key] = {"t": time.time(), "items": picked}
        savej(CACHE_FILE, cache)

    # 4. enrichir — profond (2 pages) et/ou Creuser top 3
    do_dig = dig_top3 or mode == "profond"
    if do_dig and picked:
        prog("enrichir", "running", "lecture pages…")
        if cancelled():
            prog("enrichir", "fail", "annulé")
            session_cache_put(query, src, picked)
            return picked, meta
        if dig_top3:
            picked = dig_top_pages(
                picked, n=3, model=model, cancel=cancel, on_progress=on_progress,
            )
            meta["enriched"] = [i["url"] for i in picked if i.get("body") or i.get("dig_summary")]
            # résumés dig déjà dans items
        elif mode == "profond":
            to_read = [i for i in picked[:(3 if intent == "actualite" else 2)] if not is_dead(i["url"])]
            for i, it in enumerate(to_read, 1):
                if cancelled():
                    prog("enrichir", "fail", "annulé")
                    session_cache_put(query, src, picked)
                    return picked, meta
                prog("enrichir", "running", f"page {i}/{len(to_read)} · {host_of(it['url'])}")
                body = read_page(it["url"], limit=4000)
                if body:
                    it = dict(it)
                    it["body"] = body[:4000]
                    for j, p in enumerate(picked):
                        if p["url"] == it["url"]:
                            picked[j] = it
                            break
                    meta["enriched"].append(it["url"])
        prog("enrichir", "done", f"{len(meta['enriched'])} page(s)")
    else:
        prog("enrichir", "done", "skip")

    session_cache_put(query, src, picked)
    return picked, meta



def search_web(query: str, n: int = HUNT_N, kind: str = "web") -> List[Dict[str, str]]:
    """API outil / fallback rapide (sans UI progress)."""
    items, _meta = hunt_pipeline(query, kind=kind, n=n, mode="rapide", source=kind)
    return items


def read_page(url: str, limit: int = 8000) -> str:
    if not (requests and BeautifulSoup) or is_dead(url):
        return ""
    try:
        r = http().get(url, timeout=(HTTP_CONNECT, HTTP_READ))
        r.raise_for_status()
        if not r.encoding or r.encoding.lower() in ("iso-8859-1", "ascii"):
            r.encoding = r.apparent_encoding or "utf-8"
        soup = BeautifulSoup(r.text, "html.parser")
        for t in soup(["nav", "footer", "header", "script", "style", "aside", "form", "noscript"]):
            t.decompose()
        node = soup.find("article") or soup.find("div", {"class": "mw-parser-output"}) or soup
        text = clean(" ".join(
            p.get_text(" ", strip=True) for p in node.find_all("p") if len(p.get_text(strip=True)) > 40
        ))
        if len(text) < 80:
            og = soup.find("meta", attrs={"property": "og:description"}) or soup.find(
                "meta", attrs={"name": "description"}
            )
            text = clean((og or {}).get("content") or "") if og else text
        if sum(1 for w in NOISE if w in text.lower()) >= 2 or len(text) < 80:
            return ""
        return text[:limit]
    except Exception as e:
        log(f"read {url}: {e}")
        return ""


# ── RoleRouter ───────────────────────────────────────────────────────────────

class RoleRouter:
    """Métamorphe single-process : un rôle actif, historique par rôle, outils allowlistés."""

    ROLES: Dict[str, Dict[str, Any]] = {
        "capitaine": {
            "id": "capitaine",
            "label": "Capitaine",
            "system_prompt": (
                SYSTEM_BASE
                + " Rôle CAPITAINE: orchestrateur + gestionnaire de tâches. "
                "Réponses très courtes. Tu oriente (chercher / contredire / parler). "
                "Outils tâches: get_task_list, add_task, update_task. "
                "Pas de chasse web directe. Zéro invention. Zéro moraline."
            ),
            "tools": ["get_task_list", "add_task", "update_task"],
            "history_key": "capitaine",
        },
        "chercheur": {
            "id": "chercheur",
            "label": "Chercheur",
            "system_prompt": (
                SYSTEM_BASE
                + " Rôle CHERCHEUR: chasse web multi-moteurs + brief. "
                "Allégations = allégations. Liens UNIQUEMENT sous **Sources** (URLs des hits). "
                "Pas de sermon. Pas de « je ne peux pas ». Réponds utilement. "
                "Outils: web_search, read_page. "
                "Si les sources digressent, ignore-les. "
                "Réponds UNIQUEMENT à la query courante et aux snippets/results "
                "de CETTE chasse. INTERDIT d'évoquer anciens projets, ADN, "
                "mission non liée, idées garées, chat antérieur ou sujets hors query. "
                "N'écris PAS la query en ouverture. Zéro section vide générique."
            ),
            "tools": ["web_search", "read_page"],
            "history_key": "chercheur",
        },
        "contrarian": {
            "id": "contrarian",
            "label": "Contrarian",
            "system_prompt": (
                SYSTEM_BASE
                + " Rôle CONTRARIAN / MODE CONTREDIRE: "
                "thèse charitable, trous, contre-thèse. Sans moraliser. "
                "Outils: web_search, read_page."
            ),
            "tools": ["web_search", "read_page"],
            "history_key": "contrarian",
        },
        "compagnon": {
            "id": "compagnon",
            "label": "Compagnon",
            "system_prompt": (
                SYSTEM_BASE
                + " Rôle COMPAGNON: causerie locale, mode parler. "
                "Utile, généreux en explications et en analyse, humour québécois. Pas d'outils par défaut "
                "(le logiciel peut injecter du web si besoin)."
            ),
            "tools": [],
            "history_key": "compagnon",
        },
    }

    def __init__(self, mem: dict, active: str = "chercheur"):
        self.mem = mem
        self.active = active if active in self.ROLES else "chercheur"
        self._ensure_slots()

    def _ensure_slots(self) -> None:
        if "roles" not in self.mem or not isinstance(self.mem["roles"], dict):
            self.mem["roles"] = _empty_roles()
        for rid in self.ROLES:
            slot = self.mem["roles"].setdefault(rid, {"history": []})
            if not isinstance(slot, dict):
                self.mem["roles"][rid] = {"history": []}
            else:
                slot.setdefault("history", [])

    def set_active(self, role_id: str) -> None:
        if role_id in self.ROLES:
            self.active = role_id

    def current(self) -> Dict[str, Any]:
        return self.ROLES[self.active]

    def system_prompt(self, hunt_query: Optional[str] = None) -> str:
        base = self.current()["system_prompt"] + f" Date du jour: {_today_fr()[0]}."
        q = (hunt_query or "").strip()
        if q and self.active == "chercheur":
            return (
                base
                + f" Si les sources digressent, ignore-les. Reste sur: {q}."
            )
        return base

    def clear_history(self, role_id: Optional[str] = None) -> None:
        """Vide l'historique d'un rôle (ou tous) — isolation chasse / nouvelle page."""
        self._ensure_slots()
        ids = [role_id] if role_id in self.ROLES else list(self.ROLES)
        for rid in ids:
            self.mem["roles"][rid] = {"history": []}

    def allowlist(self) -> List[str]:
        return list(self.current()["tools"])

    def history(self) -> List[dict]:
        self._ensure_slots()
        return self.mem["roles"][self.active]["history"]

    def append_history(self, who: str, text: str) -> None:
        self._ensure_slots()
        h = self.mem["roles"][self.active]["history"]
        h.append({"who": who, "text": text, "t": now()})
        self.mem["roles"][self.active]["history"] = h[-ROLE_HIST_CAP:]

    def can(self, tool_name: str) -> bool:
        return tool_name in self.allowlist()

    def call_tool(self, name: str, **kwargs) -> Any:
        if not self.can(name):
            raise PermissionError(f"Outil '{name}' pas dans l'allowlist du rôle {self.active}")
        fn = TOOLS.get(name)
        if not fn:
            raise KeyError(f"Outil inconnu: {name}")
        return fn(**kwargs)

    def contexte(self, n: int = 8) -> str:
        return "\n".join(f"{x['who']}: {x['text'][:350]}" for x in self.history()[-n:])


# ── Longueur des réponses / options génération (v39f) ─────────────────────────
LENGTH_LEVELS = ("courte", "normale", "detaillee")
LENGTH_LABELS = {"courte": "Court", "normale": "Équilibré", "detaillee": "Développé"}
LENGTH_NUM_PREDICT = {"courte": 768, "normale": 1536, "detaillee": 3072}
LENGTH_HIST_TURNS = {"courte": 6, "normale": 10, "detaillee": 16}
# v39g "vivant": style chaleureux et développé + conclusion qui ouvre (demande de Marc 2026-10-24)
STYLE_VIVANT = (
    " STYLE VIVANT: tu es un guide passionné et chaleureux, pas un dictionnaire. "
    "Ouvre par une phrase d'accroche qui donne envie (un fait étonnant, une image, un lien avec le quotidien). "
    "Explique avec des exemples concrets, des anecdotes, des comparaisons parlantes et des astuces pratiques. "
    "Fais des liens avec les passions de Marc quand c'est naturel (nature et plantes du Québec, "
    "rétro-informatique, Arduino/électronique, santé alternative), sans forcer. "
    "Santé et plantes: donne les usages traditionnels ET les vraies précautions (toxicité, doses, "
    "interactions, grossesse) et dis quand consulter un pro. "
    "Termine TOUJOURS par une courte section **💡 Pour aller plus loin**: une idée connexe surprenante, "
    "une question à explorer ou une prochaine étape pratique (1 à 3 puces)."
)
LENGTH_INSTR = {
    "courte": (" LONGUEUR: réponse courte mais chaleureuse (4 à 8 phrases ou quelques puces), jamais sèche. "
               "Finis par une seule ligne **💡 Pour aller plus loin**."),
    "normale": (" LONGUEUR: réponse équilibrée (environ 300 à 500 mots): accroche, 2 ou 3 parties claires "
                "avec exemples et astuces, puis **💡 Pour aller plus loin**."),
    "detaillee": (" LONGUEUR: réponse DÉVELOPPÉE et généreuse (souvent 600 à 1000 mots si le sujet le mérite): "
                  "accroche, sections ### bien expliquées, exemples concrets, anecdotes, astuces et pièges, "
                  "puis **💡 Pour aller plus loin**. Question factuelle rapide (une date, un chiffre, une définition simple): "
                  "réponds d'abord directement en 1-2 phrases, ajoute un peu de contexte vivant et garde la conclusion. "
                  "Simple salutation: reste naturel et bref."),
}
GEN: Dict[str, Any] = {"level": "detaillee", "num_ctx": None, "temperature": 0.7}


def _detect_num_ctx() -> int:
    """num_ctx adapté: VRAM (nvidia-smi) / RAM. Sans GPU ni RAM -> 4096. Jamais d'exception."""
    vram = 0
    try:
        exe = shutil.which("nvidia-smi")
        if exe:
            out = subprocess.run([exe, "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                                 capture_output=True, text=True, timeout=5,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
            vram = max(int(float(x)) for x in out.split() if x.strip()) if out.strip() else 0
    except Exception:
        vram = 0
    ram = 0
    try:
        import ctypes

        class _MS(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("a", ctypes.c_ulonglong), ("b", ctypes.c_ulonglong), ("c", ctypes.c_ulonglong),
                        ("d", ctypes.c_ulonglong), ("e", ctypes.c_ulonglong)]
        ms = _MS(); ms.dwLength = ctypes.sizeof(_MS)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms)):
            ram = int(ms.ullTotalPhys / (1024 ** 2))
    except Exception:
        ram = 0
    if vram >= 12000 or ram >= 30000:
        return 16384
    if vram >= 7500 or ram >= 15000:
        return 8192
    return 4096


def gen_level() -> str:
    lv = str(GEN.get("level") or "detaillee")
    return lv if lv in LENGTH_LEVELS else "detaillee"


def gen_options(temperature: Optional[float] = None) -> Dict[str, Any]:
    if not GEN.get("num_ctx"):
        try:
            GEN["num_ctx"] = _detect_num_ctx()
        except Exception:
            GEN["num_ctx"] = 4096
    return {
        "temperature": GEN.get("temperature", 0.7) if temperature is None else temperature,
        "num_predict": LENGTH_NUM_PREDICT[gen_level()],
        "num_ctx": int(GEN["num_ctx"]),
        "repeat_penalty": 1.1,
    }


def _build_messages(sys_msg: str, user: str, history: Optional[List[Dict[str, str]]]) -> List[Dict[str, str]]:
    msgs = [{"role": "system", "content": sys_msg + STYLE_VIVANT + LENGTH_INSTR[gen_level()]
             + " RAPPEL FINAL: réponse vivante et généreuse qui finit par **💡 Pour aller plus loin**; tutoie Marc (« tu », « ton », « toi »), JAMAIS « vous »; pas de phrases creuses."}]
    for m in (history or []):
        if m.get("role") in ("user", "assistant") and (m.get("content") or "").strip():
            msgs.append({"role": m["role"], "content": m["content"]})
    msgs.append({"role": "user", "content": user})
    return msgs


def forme_vivante(q: str) -> str:
    """v39g: guide de forme ajouté à la question (les petits modèles le suivent mieux que le system)."""
    q = (q or "").strip()
    if len(q.split()) <= 3 and "?" not in q:
        return ""  # salutation / mot isolé: rester naturel
    lv = gen_level()
    if lv == "courte":
        return ("\n\n[Forme: 4 à 8 phrases chaleureuses en tutoyant Marc (jamais « vous »), "
                "puis une ligne **💡 Pour aller plus loin**.]")
    if lv == "normale":
        return ("\n\n[Forme: environ 300 à 450 mots, en tutoyant Marc (jamais « vous », même pas « saviez-vous »). "
                "Une accroche vivante, 2 ou 3 sections ### avec explications et exemples concrets, "
                "puis **💡 Pour aller plus loin** (1 ou 2 puces). Si tu n'es pas sûr d'un fait, dis-le au lieu d'inventer.]")
    return ("\n\n[Forme: réponse DÉVELOPPÉE d'environ 500 à 900 mots, en tutoyant Marc "
            "(jamais « vous », même pas « saviez-vous »). "
            "1) Une accroche vivante de 1-2 phrases. "
            "2) 3 à 5 sections ### qui expliquent vraiment: comment ça marche, histoire ou contexte, "
            "exemples concrets, chiffres sûrs, anecdotes. "
            "3) Une section ### Précautions si le sujet touche la santé, les plantes ou l'électricité (vrais risques, doses, interactions), sinon ### Astuces. "
            "4) Termine par **💡 Pour aller plus loin** avec 2 ou 3 puces: une idée connexe surprenante, "
            "une question à explorer, une prochaine étape pratique. "
            "Question factuelle simple: réponse directe d'abord, puis développe un peu moins. "
            "EXACTITUDE AVANT TOUT: n'ajoute jamais un chiffre, une date, un nom ou une composante dont tu n'es pas sûr; mieux vaut développer avec des explications et des exemples que remplir avec des faits douteux.]")


def chat(model: str, user: str, system: str | None = None, cancel: Optional[threading.Event] = None,
         history: Optional[List[Dict[str, str]]] = None) -> str:
    if not requests:
        raise RuntimeError("pip install requests")
    if cancel and cancel.is_set():
        return ""
    sys_msg = system if system is not None else SYSTEM_BASE
    try:
        r = ollama_request(
            "POST",
            "/api/chat",
            json_body={
                "model": model,
                "stream": False,
                "options": gen_options(),
                "messages": _build_messages(sys_msg, user, history),
            },
            timeout=(OLLAMA_CONNECT, TIMEOUT),
            retries=OLLAMA_RETRY,
            cancel=cancel,
        )
        return ((r.json().get("message") or {}).get("content") or "").strip() or "Silence radio."
    except Exception as e:
        raise RuntimeError(ollama_err_fr(e, context="chat")) from e


def chat_stream(
    model: str,
    user: str,
    system: str | None = None,
    on_token: Optional[Callable[[str], None]] = None,
    cancel: Optional[threading.Event] = None,
    history: Optional[List[Dict[str, str]]] = None,
) -> str:
    if not requests:
        raise RuntimeError("pip install requests")
    if cancel and cancel.is_set():
        return ""
    sys_msg = system if system is not None else SYSTEM_BASE
    try:
        r = ollama_request(
            "POST",
            "/api/chat",
            json_body={
                "model": model,
                "stream": True,
                "options": gen_options(),
                "messages": _build_messages(sys_msg, user, history),
            },
            timeout=(OLLAMA_CONNECT, TIMEOUT),
            stream=True,
            retries=OLLAMA_RETRY,
            cancel=cancel,
        )
        buf: List[str] = []
        for line in r.iter_lines(decode_unicode=True):
            if cancel and cancel.is_set():
                try:
                    r.close()
                except Exception:
                    pass
                break
            if not line:
                continue
            try:
                chunk = json.loads(line)
            except Exception:
                continue
            part = ((chunk.get("message") or {}).get("content") or "")
            if part:
                buf.append(part)
                if on_token:
                    on_token(part)
            if chunk.get("done"):
                break
        text = "".join(buf).strip()
        return text or ("(annulé)" if cancel and cancel.is_set() else "Silence radio.")
    except Exception as e:
        fr = ollama_err_fr(e, context="stream")
        log(f"stream fail, fallback: {fr}")
        try:
            return chat(model, user, system=system, cancel=cancel, history=history)
        except Exception as e2:
            return f"⚠ {ollama_err_fr(e2, context='chat')}"


# ── UI ───────────────────────────────────────────────────────────────────────



# Tray / startup / gestionnaire : voir padawan_tray.py (alias systemtray.py)
# Constantes et helpers importés ci-dessus depuis padawan_tray.


class Padawan(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} · multi-chasse")
        self.configure(bg=C["bg"])
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{min(1440, sw - 24)}x{min(900, sh - 40)}+12+12")
        self.minsize(980, 560)
        self.cfg, self.mem = load_cfg(), load_mem()
        savej(MEM_FILE, self.mem)
        if not os.path.isfile(TASKS_FILE):
            save_tasks([])
        self.mode = "chercher"
        self.hunt_kind = self.cfg.get("search_source", "web")  # alias source (compat)
        if self.hunt_kind not in SEARCH_SOURCES:
            self.hunt_kind = "web"
        self.search_source = self.hunt_kind
        self.hunt_mode = self.cfg.get("hunt_mode", "multi")
        if self.hunt_mode not in HUNT_MODES:
            self.hunt_mode = "multi"
        self.hunt_n = int(self.cfg.get("hunt_n", HUNT_N))
        self.hunt_n = max(3, min(HUNT_N_MAX, self.hunt_n))
        self.dig_top3 = bool(self.cfg.get("dig_top3", False))
        self.ready = self.busy = False
        self.model_ready = False
        self._model_check_gen = 0
        self._model_warming = False
        self.hits: List[Dict[str, str]] = []
        self.active_url = self.last_q = self.last_a = ""
        self.session_hunt_id = 0  # bump = nouveau contexte chasse isolé
        self._hunt_query = ""     # query de la chasse courante (isolation brief)
        self._chat_anchor = ""    # mark index début chasse / En bref (anti-jump Sources)
        self._chat_jump_visible = False
        self._tip_blink_id = None
        self._tip_on = True
        self._pulse_id = None
        self._mission_pulse_id = None
        self._mission_running_step: Optional[str] = None
        self._mission_t0 = 0.0
        self._mission_elapsed_id = None
        self._cancel = threading.Event()
        self._reader_job = 0
        self._last_url_click = 0.0
        self.mods = models()
        GEN["level"] = str(self.cfg.get("longueur") or "detaillee")
        if GEN["level"] not in LENGTH_LEVELS:
            GEN["level"] = "detaillee"
        try:
            if self.cfg.get("num_ctx"):
                GEN["num_ctx"] = int(self.cfg["num_ctx"])
        except Exception:
            pass
        cfg_m = model_id_from_label(str(self.cfg.get("model") or MODEL))
        pick = None
        for lab in self.mods:
            if model_id_from_label(lab) == cfg_m:
                pick = lab
                break
        if pick is None:
            pick = self.mods[0] if self.mods else model_menu_label(MODEL, False)
        self.model = model_id_from_label(pick)
        role0 = self.cfg.get("role", "chercheur")
        if role0 not in RoleRouter.ROLES:
            role0 = "chercheur"
        self.router = RoleRouter(self.mem, active=role0)
        if role0 in ROLE_TO_MODE:
            self.mode = ROLE_TO_MODE[role0]
        self.session = {"t": now(), "h": []}
        self.mem["sessions"].append({"start": self.session["t"], "history": self.session["h"]})
        self.bind("<Control-f>", lambda e: self.focus_hunt())
        self.bind("<Control-i>", lambda e: self.park())
        self.bind("<Control-l>", lambda e: self.clear_chat())
        self.bind("<F11>", lambda e: self.attributes("-fullscreen", not self.attributes("-fullscreen")))
        self.bind("<Escape>", lambda e: self.cancel_job())
        self._style()
        self.build()
        self.after(80, lambda: self.split.sash_place(0, 820, 0))
        self.set_pill("mode", self.mode)
        self.set_role(self.router.active, sync_mode=False)
        self.set_pill("hmode", self.hunt_mode)
        threading.Thread(target=self.warm_model, daemon=True).start()
        self.after(180, self._startup_focus)
        # v35: maximisé + tray + auto-start Windows
        self._tray_icon = None
        self._tray_thread = None
        self._quitting = False
        self.after(120, self._apply_startup_window)
        self.after(250, self._setup_tray)
        self.after(400, self._sync_windows_startup)

    def after0(self, fn: Callable, *a, **k):
        self.after(0, lambda: fn(*a, **k))

    def notify_done(self, title: str, message: str, *, force: bool = False) -> None:
        if not force and not self.cfg.get("notify_on_done", True):
            return
        # Notifie seulement si iconifiée / withdrawn (sauf force) — évite spam
        try:
            st = self.state()
            if not force and st not in ("iconic", "withdrawn"):
                return
        except Exception:
            pass
        notify_toast(title, message)

    def _startup_focus(self):
        tray_hint = " · X = tray" if TRAY_AVAILABLE else ""
        self.say(
            "sys",
            f"{APP_NAME} — {self.router.current()['label']}. "
            f"Source: {SEARCH_SOURCE_LABELS.get(self.search_source, self.search_source)} · "
            f"Pouvoir: {HUNT_MODE_LABELS.get(self.hunt_mode, self.hunt_mode)} · n={self.hunt_n}"
            f"{tray_hint}. "
            "Entrée = envoyer. Échap = annuler.",
        )
        self.ent.focus_set()
        if not self.cfg.get("tip_seen"):
            self._start_tip_blink()
            self.cfg["tip_seen"] = True
            savej(CFG_FILE, self.cfg)

    def _start_tip_blink(self):
        self._tip_blink_count = 0

        def tick():
            if not hasattr(self, "input_tip") or not self.input_tip.winfo_exists():
                return
            self._tip_on = not self._tip_on
            self.input_tip.config(fg=C["gold"] if self._tip_on else C["cyan"])
            self._tip_blink_count += 1
            if self._tip_blink_count < 8:
                self._tip_blink_id = self.after(400, tick)
            else:
                self.input_tip.config(fg=C["dim"])

        tick()

    def _style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("TNotebook", background=C["bg"], borderwidth=0)
        s.configure(
            "TNotebook.Tab", background=C["card"], foreground=C["fg"],
            padding=(10, 4), font=("Segoe UI", 9),
        )
        s.map("TNotebook.Tab", background=[("selected", C["gold"])], foreground=[("selected", "#1a1408")])
        s.configure(
            "TCombobox", fieldbackground=C["card"], background=C["card"],
            foreground=C["fg"], arrowcolor=C["gold"],
        )
        s.map("TCombobox", fieldbackground=[("readonly", C["card"])], foreground=[("readonly", C["fg"])])
        s.configure(
            "Gold.Vertical.TScrollbar",
            background=C["gold"], troughcolor=C["panel"], bordercolor=C["line"],
            arrowcolor="#1a1408", darkcolor=C["gold"], lightcolor=C["gold"],
            relief="flat", width=18,
        )
        s.map("Gold.Vertical.TScrollbar", background=[("active", "#e4c48a"), ("pressed", "#c9a45a")])

    def _make_entry(self, parent, textvariable, *, font_size=14) -> tk.Entry:
        e = tk.Entry(
            parent,
            textvariable=textvariable,
            bg=C["input"],
            fg=C["fg"],
            insertbackground=C["cursor"],
            insertwidth=3,
            relief="flat",
            font=("Segoe UI", font_size),
            highlightthickness=2,
            highlightcolor=C["gold"],
            highlightbackground=C["cyan"],
            disabledbackground=C["card"],
            disabledforeground=C["dim"],
        )
        return e

    def pill(self, parent, text, key, group: str, *, bold: bool = False):
        b = tk.Label(
            parent, text=text, bg=C["card"], fg=C["fg"],
            font=("Segoe UI", 9 if bold else 8, "bold" if bold else "normal"),
            padx=8 if bold else 6, pady=3 if bold else 2, cursor="hand2",
        )
        b.bind("<Button-1>", lambda e, k=key, g=group: self.set_pill(g, k))
        b.pack(side="left", padx=1)
        return b

    def set_pill(self, group: str, key: str):
        if group == "mode":
            self.mode, store = key, self.mode_pills
            mapped = MODE_TO_ROLE.get(key)
            if mapped and getattr(self, "router", None):
                self.router.set_active(mapped)
                self._paint_role_pills()
                self._update_role_indicator()
        elif group == "role":
            self.set_role(key, sync_mode=True)
            return
        elif group == "hmode":
            self.hunt_mode = key
            self.cfg["hunt_mode"] = key
            store = self.hmode_pills
        elif group == "source":
            self.search_source = key
            self.hunt_kind = key  # alias
            self.cfg["search_source"] = key
            savej(CFG_FILE, self.cfg)
            store = self.source_pills
        else:
            # legacy kind → source
            self.hunt_kind, store = key, getattr(self, "kind_pills", getattr(self, "source_pills", {}))
            if key in SEARCH_SOURCES:
                self.search_source = key
                self.cfg["search_source"] = key
        for k, lab in store.items():
            on = k == key
            lab.config(bg=C["gold"] if on else C["card"], fg="#1a1408" if on else C["fg"])

    def set_role(self, role_id: str, sync_mode: bool = True):
        if role_id not in RoleRouter.ROLES:
            return
        self.router.set_active(role_id)
        self.cfg["role"] = role_id
        self._paint_role_pills()
        self._update_role_indicator()
        if sync_mode and role_id in ROLE_TO_MODE:
            self.mode = ROLE_TO_MODE[role_id]
            for k, lab in self.mode_pills.items():
                on = k == self.mode
                lab.config(bg=C["gold"] if on else C["card"], fg="#1a1408" if on else C["fg"])

    def _paint_role_pills(self):
        if not hasattr(self, "role_pills"):
            return
        for k, lab in self.role_pills.items():
            on = k == self.router.active
            lab.config(bg=C["gold"] if on else C["card"], fg="#1a1408" if on else C["fg"])

    def _update_role_indicator(self):
        if hasattr(self, "role_ind"):
            r = self.router.current()
            tools = ", ".join(r["tools"]) if r["tools"] else "aucun"
            self.role_ind.config(text=f"{r['label']} · {tools}")

    def build(self):
        rail = tk.Frame(self, bg=C["bg"], width=164)
        rail.pack(side="left", fill="y", padx=(8, 0), pady=8)
        rail.pack_propagate(False)

        # --- Bas fixe d'abord (pack bottom) : status + mission ---
        bot = tk.Frame(rail, bg=C["bg"])
        bot.pack(side="bottom", fill="x", anchor="w")
        self.cancel_btn = tk.Button(
            bot, text="Annuler", command=self.cancel_job, bg=C["bad"], fg="#1a0808",
            relief="flat", font=("Segoe UI", 8, "bold"), padx=8, pady=3, cursor="hand2",
        )
        self.ollama_phase = tk.Label(
            bot, text="Ollama : vérification…", bg=C["bg"], fg=C["dim"],
            font=("Segoe UI", 8), wraplength=148, justify="left",
        )
        self.ollama_phase.pack(anchor="w", pady=(0, 1))
        self.status = tk.Label(
            bot, text="● Ollama : vérification…", bg=C["bg"], fg=C["dim"], font=("Segoe UI", 10, "bold"),
            wraplength=148, justify="left",
        )
        self.status.pack(anchor="w")
        self.retry_ollama_btn = tk.Button(
            bot, text="Relancer Ollama", command=self.retry_ollama,
            bg=C["card"], fg=C["gold"], relief="flat", font=("Segoe UI", 8, "bold"),
            padx=6, pady=2, cursor="hand2",
        )
        self.retry_ollama_btn.pack(anchor="w", pady=(4, 0))

        self._build_mission_panel(rail)

        # --- Header fixe en haut ---
        header = tk.Frame(rail, bg=C["bg"])
        header.pack(side="top", fill="x")
        tk.Label(
            header, text="PADAWAN", bg=C["bg"], fg=C["gold"], font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w")
        tk.Label(
            header, text="multi-chasse · local", bg=C["bg"], fg=C["dim"], font=("Segoe UI", 7),
        ).pack(anchor="w", pady=(0, 4))

        # --- Zone scrollable (nav + VEILLE) ---
        scroll_fr = tk.Frame(rail, bg=C["bg"])
        scroll_fr.pack(side="top", fill="both", expand=True)

        self.rail_canvas = tk.Canvas(scroll_fr, bg=C["bg"], highlightthickness=0, bd=0)
        self.rail_scroll = ttk.Scrollbar(
            scroll_fr, orient="vertical", command=self.rail_canvas.yview,
            style="Gold.Vertical.TScrollbar",
        )
        self.rail_inner = tk.Frame(self.rail_canvas, bg=C["bg"])
        self.rail_inner.bind(
            "<Configure>",
            lambda e: self.rail_canvas.configure(scrollregion=self.rail_canvas.bbox("all")),
        )
        self.rail_win = self.rail_canvas.create_window((0, 0), window=self.rail_inner, anchor="nw")
        self.rail_canvas.configure(yscrollcommand=self.rail_scroll.set)
        self.rail_canvas.pack(side="left", fill="both", expand=True)
        self.rail_scroll.pack(side="right", fill="y")
        self.rail_canvas.bind(
            "<Configure>",
            lambda e: self.rail_canvas.itemconfigure(self.rail_win, width=max(140, e.width - 2)),
        )
        self.rail_canvas.bind("<Enter>", lambda e: self._bind_rail_wheel())
        self.rail_canvas.bind("<Leave>", lambda e: self._unbind_rail_wheel())

        def nav(txt, cmd):
            b = tk.Button(
                self.rail_inner, text=txt, command=cmd, bg=C["card"], fg=C["fg"], relief="flat",
                anchor="w", font=("Segoe UI", 9), cursor="hand2", padx=8, pady=4,
                activebackground=C["gold"], activeforeground="#1a1408",
            )
            def _enter(e, btn=b):
                if str(btn.cget("state")) != "disabled":
                    btn.configure(bg=C["card2"], fg=C["gold"])
            def _leave(e, btn=b):
                if str(btn.cget("state")) != "disabled":
                    btn.configure(bg=C["card"], fg=C["fg"])
            b.bind("<Enter>", _enter)
            b.bind("<Leave>", _leave)
            return b

        nav("Gare l'idée  Ctrl+I", self.park).pack(fill="x", pady=1)
        self.btn_inbox = nav(self._inbox_label(), self.show_inbox)
        self.btn_inbox.pack(fill="x", pady=1)
        nav("Tâches", self.show_tasks).pack(fill="x", pady=1)
        nav("Creuser", self.dig).pack(fill="x", pady=1)
        nav("Copier", self.copy_last).pack(fill="x", pady=1)
        nav("Nouvelle page", self.clear_chat).pack(fill="x", pady=1)
        nav("Exporter", self.export).pack(fill="x", pady=1)

        tk.Label(
            self.rail_inner, text="VEILLE", bg=C["bg"], fg=C["dim"], font=("Segoe UI", 7, "bold"),
        ).pack(anchor="w", pady=(8, 2))
        tk.Label(
            self.rail_inner, text="clic = chasse · droit = retirer · ↻ = déjà chassé",
            bg=C["bg"], fg=C["dim"], font=("Segoe UI", 7),
        ).pack(anchor="w", pady=(0, 4))
        self.watch_box = tk.Frame(self.rail_inner, bg=C["bg"])
        self.watch_box.pack(fill="x")
        self.draw_watch()
        watch_btns = tk.Frame(self.rail_inner, bg=C["bg"])
        watch_btns.pack(fill="x", pady=4)
        tk.Button(
            watch_btns, text="+ sujet", command=self.add_watch, bg=C["bg"], fg=C["gold"],
            relief="flat", font=("Segoe UI", 9), cursor="hand2",
        ).pack(side="left")
        tk.Button(
            watch_btns, text="Tout chasser", command=self.hunt_first_watch,
            bg=C["bg"], fg=C["dim"], relief="flat", font=("Segoe UI", 8), cursor="hand2",
        ).pack(side="right")

        tk.Frame(self, bg=C["line"], width=1).pack(side="left", fill="y", padx=6, pady=8)

        self.split = tk.PanedWindow(
            self, orient="horizontal", bg=C["line"], sashwidth=6, sashrelief="flat", opaqueresize=True,
        )
        self.split.pack(side="left", fill="both", expand=True, padx=(0, 8), pady=8)

        mid = tk.Frame(self.split, bg=C["bg"])
        self.split.add(mid, stretch="always", minsize=480)

        bar_wrap = tk.Frame(mid, bg=C["bg"])
        bar_wrap.pack(side="bottom", fill="x", pady=(4, 0))

        self.input_tip = tk.Label(
            bar_wrap,
            text="Entrée = envoyer · Échap = annuler  ·  gris=check · or=load · vert=prêt · rouge=off",
            bg=C["bg"], fg=C["dim"], font=("Segoe UI", 8, "italic"),
            anchor="w",
        )
        self.input_tip.pack(fill="x", padx=2, pady=(0, 1))

        self.busy_lbl = tk.Label(
            bar_wrap, text="", bg=C["bg"], fg=C["gold"], font=("Segoe UI", 8, "bold"), anchor="w",
        )
        self.busy_lbl.pack(fill="x", padx=2)

        self.sugg_bar = tk.Frame(bar_wrap, bg=C["bg"])
        self.sugg_bar.pack(fill="x", pady=(0, 2))
        act = tk.Frame(bar_wrap, bg=C["bg"])
        act.pack(fill="x", pady=(0, 2))
        self.act_btns = {}
        for key, lab, cmd in (
            ("stop", "■ Stop", self.cancel_job),
            ("copy", "📋 Copier", self.copy_answer),
            ("regen", "🔄 Régénérer", self.regenerate),
            ("export", "💾 Exporter", self.export_answer),
            ("speak", "🔊 Lire", self.speak_answer),
        ):
            b = tk.Button(
                act, text=lab, command=cmd, bg=C["bad"] if key == "stop" else C["card"],
                fg="#1a0808" if key == "stop" else C["fg"], relief="flat",
                font=("Segoe UI", 8, "bold"), padx=8, pady=2, cursor="hand2",
                activebackground=C["gold"], activeforeground="#1a1408",
            )
            b.pack(side="left", padx=2)
            self.act_btns[key] = b
        self.act_btns["stop"].pack_forget()
        bar = tk.Frame(
            bar_wrap, bg=C["input"],
            highlightbackground=C["line"], highlightcolor=C["gold"], highlightthickness=1,
        )
        bar.pack(fill="x")
        self.var = tk.StringVar()
        self.ent = self._make_entry(bar, self.var, font_size=13)
        self.ent.pack(side="left", fill="x", expand=True, ipady=8, padx=(8, 4), pady=3)
        self.ent.bind("<Return>", lambda e: self.send())
        self.ent.bind("<Control-Return>", lambda e: self.send())
        tk.Button(
            bar, text="Envoyer", command=self.send, bg=C["gold"], fg="#1a1408", relief="flat",
            font=("Segoe UI", 10, "bold"), padx=14, pady=6, cursor="hand2",
            activebackground="#e4c48a", activeforeground="#1a1408",
        ).pack(side="right", padx=6, pady=4)

        chips = tk.Frame(mid, bg=C["bg"])
        chips.pack(side="bottom", fill="x", pady=(2, 0))
        for lab, cmd in (("Creuser", self.dig), ("Contredire ça", self.flip), ("Garer ça", self.park)):
            tk.Button(
                chips, text=lab, command=cmd, bg=C["card"], fg=C["fg"], relief="flat",
                font=("Segoe UI", 8), padx=8, pady=3, cursor="hand2",
                activebackground=C["gold"], activeforeground="#1a1408",
            ).pack(side="left", padx=2)

        hunt = tk.Frame(
            mid, bg=C["input"],
            highlightbackground=C["line"], highlightcolor=C["gold"], highlightthickness=1,
        )
        hunt.pack(fill="x", pady=(0, 3))
        tk.Label(
            hunt, text="CHASSE", bg=C["input"], fg=C["gold"], font=("Segoe UI", 8, "bold"),
        ).pack(side="left", padx=(8, 6))
        self.hunt = tk.StringVar()
        self.hunt_entry = self._make_entry(hunt, self.hunt, font_size=12)
        self.hunt_entry.configure(highlightthickness=0)
        self.hunt_entry.pack(side="left", fill="x", expand=True, ipady=6)
        self.hunt_entry.bind("<Return>", lambda e: self.go_hunt())
        tk.Button(
            hunt, text="Go", command=self.go_hunt, bg=C["gold"], fg="#1a1408", relief="flat",
            font=("Segoe UI", 9, "bold"), padx=12, pady=4, cursor="hand2",
        ).pack(side="right", padx=6, pady=3)

        # Chrome densifié: 2 rangées max (pouvoir/source/n + rôle/modèle/mode)
        chrome = tk.Frame(mid, bg=C["bg"])
        chrome.pack(fill="x", pady=(0, 2))

        row0 = tk.Frame(chrome, bg=C["bg"])
        row0.pack(fill="x", pady=0)
        tk.Label(row0, text="POUV", bg=C["bg"], fg=C["dim"], font=("Segoe UI", 7)).pack(side="left", padx=(0, 3))
        self.hmode_pills = {}
        for key in HUNT_MODES:
            self.hmode_pills[key] = self.pill(row0, HUNT_MODE_LABELS[key], key, "hmode", bold=True)
        self.set_pill("hmode", self.hunt_mode)
        tk.Label(row0, text="·", bg=C["bg"], fg=C["line"], font=("Segoe UI", 8)).pack(side="left", padx=4)
        tk.Label(row0, text="SRC", bg=C["bg"], fg=C["dim"], font=("Segoe UI", 7)).pack(side="left", padx=(0, 3))
        self.source_pills = {}
        self.kind_pills = self.source_pills  # alias compat
        for key in SEARCH_SOURCES:
            self.source_pills[key] = self.pill(row0, SEARCH_SOURCE_LABELS[key], key, "source")
        self.set_pill("source", self.search_source)
        tk.Label(row0, text="·", bg=C["bg"], fg=C["line"], font=("Segoe UI", 8)).pack(side="left", padx=4)
        tk.Label(row0, text="n", bg=C["bg"], fg=C["dim"], font=("Segoe UI", 7)).pack(side="left", padx=(0, 2))
        self.hunt_n_var = tk.IntVar(value=self.hunt_n)
        self.hunt_n_spin = tk.Spinbox(
            row0, from_=3, to=HUNT_N_MAX, width=2, textvariable=self.hunt_n_var,
            command=self._on_hunt_n_change,
            bg=C["input"], fg=C["fg"], buttonbackground=C["card"],
            highlightthickness=1, highlightbackground=C["line"], highlightcolor=C["gold"],
            font=("Segoe UI", 8), relief="flat",
        )
        self.hunt_n_spin.pack(side="left", padx=(0, 4))
        self.hunt_n_spin.bind("<FocusOut>", lambda e: self._on_hunt_n_change())
        self.hunt_n_spin.bind("<Return>", lambda e: self._on_hunt_n_change())
        self.dig_top3_var = tk.BooleanVar(value=self.dig_top3)
        self.dig_top3_chk = tk.Checkbutton(
            row0, text="Creuser×3", variable=self.dig_top3_var,
            command=self._on_dig_top3_change,
            bg=C["bg"], fg=C["fg"], selectcolor=C["card"],
            activebackground=C["bg"], activeforeground=C["gold"],
            font=("Segoe UI", 8), cursor="hand2",
        )
        self.dig_top3_chk.pack(side="left", padx=(0, 2))

        row2 = tk.Frame(chrome, bg=C["bg"])
        row2.pack(fill="x", pady=(2, 0))
        self.role_pills = {}
        for key, lab in (
            ("capitaine", "Cap."),
            ("chercheur", "Chercheur"),
            ("contrarian", "Contre"),
            ("compagnon", "Comp."),
        ):
            self.role_pills[key] = self.pill(row2, lab, key, "role")
        self.role_ind = tk.Label(row2, text="", bg=C["bg"], fg=C["dim"], font=("Segoe UI", 7))
        self.role_ind.pack(side="left", padx=(6, 8))
        _m0 = self.model
        _lab0 = next((lab for lab in self.mods if model_id_from_label(lab) == _m0), self.mods[0] if self.mods else _m0)
        self.mvar = tk.StringVar(value=_lab0)
        self.model_combo = ttk.Combobox(
            row2, textvariable=self.mvar, values=self.mods, state="readonly", width=28,
        )
        self.model_combo.pack(side="left", padx=(0, 4))
        self.model_combo.bind("<<ComboboxSelected>>", self.on_model_chosen)
        self.model_dot = tk.Label(
            row2, text="●", bg=C["bg"], fg=C["dim"], font=("Segoe UI", 10, "bold"),
        )
        self.model_dot.pack(side="left", padx=(0, 2))
        self.model_lbl = tk.Label(
            row2, text="vérif…", bg=C["bg"], fg=C["dim"], font=("Segoe UI", 7),
        )
        self.model_lbl.pack(side="left", padx=(0, 8))
        tk.Label(row2, text="Style", bg=C["bg"], fg=C["dim"], font=("Segoe UI", 7)).pack(side="left", padx=(0, 2))
        self.lenvar = tk.StringVar(value=LENGTH_LABELS[gen_level()])
        self.len_combo = ttk.Combobox(
            row2, textvariable=self.lenvar, values=[LENGTH_LABELS[k] for k in LENGTH_LEVELS],
            state="readonly", width=10,
        )
        self.len_combo.pack(side="left", padx=(0, 8))
        self.len_combo.bind("<<ComboboxSelected>>", self.on_length_chosen)
        self.mode_pills = {}
        for key, lab in (("parler", "Parler"), ("chercher", "Chercher"), ("contredire", "Contredire")):
            self.mode_pills[key] = self.pill(row2, lab, key, "mode", bold=True)
        self.set_pill("mode", "chercher")

        chat_wrap = tk.Frame(mid, bg=C["bg"])
        chat_wrap.pack(fill="both", expand=True)
        self._chat_wrap = chat_wrap
        self.chat = scrolledtext.ScrolledText(
            chat_wrap, wrap="word", state="disabled", bg=C["panel"], fg=C["fg"],
            font=("Segoe UI", 11), relief="flat", padx=12, pady=10, bd=0,
            insertbackground=C["cursor"], highlightthickness=1,
            highlightbackground=C["line"], highlightcolor=C["gold"],
        )
        self.chat.pack(fill="both", expand=True)
        self.chat.tag_configure("you", foreground=C["gold"], font=("Segoe UI", 11, "bold"))
        self.chat.tag_configure("sys", foreground=C["dim"], font=("Segoe UI", 9, "italic"))
        self.chat.tag_configure("ai", foreground=C["fg"], font=("Segoe UI", 11))
        self.chat.tag_configure("url", foreground=C["link"], underline=True, font=("Segoe UI", 10))
        self.chat.tag_configure("stream", foreground=C["fg"], font=("Segoe UI", 11))
        self.chat.tag_configure("pulse", foreground=C["gold"], font=("Segoe UI", 9, "italic"))
        self.chat.tag_configure("snip", foreground=C["dim"], font=("Segoe UI", 9))
        self.chat.tag_configure("hitn", foreground=C["cyan"], font=("Segoe UI", 9, "bold"))
        self.chat.tag_bind("url", "<Button-1>", self.click_url)
        self.chat.tag_bind("url", "<Button-3>", lambda e: self.open_browser(self.url_at(self.chat, e)))
        self.chat.tag_bind("url", "<Enter>", lambda e: self.chat.config(cursor="hand2"))
        self.chat.tag_bind("url", "<Leave>", lambda e: self.chat.config(cursor="arrow"))
        # Scroll intelligent: sticky-bottom + bouton ↓ Bas si pas en bas
        self.chat.configure(yscrollcommand=self._chat_on_yscroll)
        self.chat.bind("<MouseWheel>", lambda e: self.after(20, self._chat_update_jump_btn), add="+")
        self.chat.bind("<Button-4>", lambda e: self.after(20, self._chat_update_jump_btn), add="+")
        self.chat.bind("<Button-5>", lambda e: self.after(20, self._chat_update_jump_btn), add="+")
        self.chat.bind("<KeyRelease-Prior>", lambda e: self.after(20, self._chat_update_jump_btn), add="+")
        self.chat.bind("<KeyRelease-Next>", lambda e: self.after(20, self._chat_update_jump_btn), add="+")
        self.chat.bind("<KeyRelease-Home>", lambda e: self.after(20, self._chat_update_jump_btn), add="+")
        self.chat.bind("<KeyRelease-End>", lambda e: self.after(20, self._chat_update_jump_btn), add="+")
        self._jump_bot_btn = tk.Button(
            chat_wrap, text="↓ Bas", command=self._chat_jump_bottom,
            bg=C["card"], fg=C["gold"], relief="flat", font=("Segoe UI", 8, "bold"),
            padx=8, pady=2, cursor="hand2",
            activebackground=C["gold"], activeforeground="#1a1408",
            highlightthickness=1, highlightbackground=C["line"],
        )
        # caché tant que viewport déjà en bas
        self._jump_bot_btn.place_forget()

        right = tk.Frame(self.split, bg=C["bg"], width=400)
        self.split.add(right, stretch="always", minsize=300)
        self.nb = ttk.Notebook(right)
        self.nb.pack(fill="both", expand=True)
        self.tab_src, self.tab_read = tk.Frame(self.nb, bg=C["bg"]), tk.Frame(self.nb, bg=C["bg"])
        self.nb.add(self.tab_src, text=" Sources ")
        self.nb.add(self.tab_read, text=" Lecteur ")

        src_top = tk.Frame(self.tab_src, bg=C["bg"])
        src_top.pack(fill="x", padx=6, pady=(4, 0))
        self.read3_btn = tk.Button(
            src_top, text="Lire top 3", command=self.read_top3,
            bg=C["card2"], fg=C["fg"], relief="flat", font=("Segoe UI", 8, "bold"),
            padx=8, pady=3, cursor="hand2",
            activebackground=C["gold"], activeforeground="#1a1408",
        )
        self.read3_btn.pack(side="left")
        tk.Button(
            src_top, text="Creuser profond", command=self.dig_profond,
            bg=C["card"], fg=C["cyan"], relief="flat", font=("Segoe UI", 8, "bold"),
            padx=8, pady=3, cursor="hand2",
            activebackground=C["gold"], activeforeground="#1a1408",
        ).pack(side="left", padx=4)

        self.src_canvas = tk.Canvas(self.tab_src, bg=C["bg"], highlightthickness=0)
        self.src_scroll = ttk.Scrollbar(
            self.tab_src, orient="vertical", command=self.src_canvas.yview, style="Gold.Vertical.TScrollbar",
        )
        self.src_in = tk.Frame(self.src_canvas, bg=C["bg"])
        self.src_in.bind("<Configure>", lambda e: self.src_canvas.configure(scrollregion=self.src_canvas.bbox("all")))
        self.src_win = self.src_canvas.create_window((0, 0), window=self.src_in, anchor="nw")
        self.src_canvas.configure(yscrollcommand=self.src_scroll.set)
        self.src_canvas.pack(side="left", fill="both", expand=True, padx=(4, 0), pady=4)
        self.src_scroll.pack(side="right", fill="y", padx=(2, 6), pady=4)
        self.src_canvas.bind(
            "<Configure>",
            lambda e: self.src_canvas.itemconfigure(self.src_win, width=max(200, e.width - 4)),
        )
        self.src_canvas.bind("<Enter>", lambda e: self.src_canvas.bind_all("<MouseWheel>", self._wheel_src))
        self.src_canvas.bind("<Leave>", lambda e: self.src_canvas.unbind_all("<MouseWheel>"))

        head = tk.Frame(self.tab_read, bg=C["bg"])
        head.pack(fill="x", pady=(4, 2), padx=8)
        self.rtitle = tk.Label(
            head, text="Lecteur — clique une carte Sources.", bg=C["bg"], fg=C["dim"],
            wraplength=360, justify="left", font=("Segoe UI", 10, "bold"),
        )
        self.rtitle.pack(anchor="w")
        self.rhost = tk.Label(head, text="Esc = annuler · clic droit lien = navigateur", bg=C["bg"], fg=C["dim"], font=("Segoe UI", 7))
        self.rhost.pack(anchor="w")
        navr = tk.Frame(head, bg=C["bg"])
        navr.pack(anchor="w", pady=4)
        tk.Button(navr, text="◀", command=lambda: self.step(-1), bg=C["card"], fg=C["fg"], relief="flat", width=3,
                  font=("Segoe UI", 9)).pack(side="left")
        tk.Button(navr, text="▶", command=lambda: self.step(1), bg=C["card"], fg=C["fg"], relief="flat", width=3,
                  font=("Segoe UI", 9)).pack(side="left", padx=3)
        tk.Button(
            navr, text="Ouvrir", command=self.open_site, bg=C["gold"], fg="#1a1408",
            relief="flat", font=("Segoe UI", 8, "bold"), padx=8, pady=2,
        ).pack(side="left", padx=4)
        tk.Button(
            navr, text="Copier", command=self.copy_link, bg=C["card2"], fg=C["fg"],
            relief="flat", font=("Segoe UI", 8), padx=6, pady=2,
        ).pack(side="left")
        self.rbox = scrolledtext.ScrolledText(
            self.tab_read, wrap="word", bg=C["panel"], fg=C["fg"],
            font=("Segoe UI", 11), relief="flat", padx=10, pady=10,
            highlightthickness=1, highlightbackground=C["line"], highlightcolor=C["gold"],
        )
        self.rbox.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self.rbox.tag_configure("url", foreground=C["link"], underline=True)
        self.rbox.tag_configure("skel", foreground=C["skel"], font=("Segoe UI", 10, "italic"))
        self.rbox.tag_bind("url", "<Button-3>", lambda e: self.open_browser(self.url_at(self.rbox, e)))
        self.rbox.insert(
            "1.0",
            "Rien encore.\n\n"
            "1. Lance une chasse (barre CHASSE ou Entrée).\n"
            "2. Clique une carte Sources → le texte s'affiche ici.\n"
            "3. Clic droit sur un lien = navigateur.\n\n"
            "Astuce: « Lire top 3 » enchaîne les 3 premières sources.",
        )
        self.rbox.configure(state="disabled")
        self.draw_sources()

    # ── Mission panel ────────────────────────────────────────────────────────

    def _build_mission_panel(self, rail):
        wrap = tk.Frame(rail, bg=C["panel"], highlightbackground=C["line"], highlightthickness=1)
        wrap.pack(side="bottom", fill="x", pady=(6, 4))

        head = tk.Frame(wrap, bg=C["panel"])
        head.pack(fill="x", padx=6, pady=(6, 2))
        tk.Label(head, text="MISSION", bg=C["panel"], fg=C["gold"], font=("Segoe UI", 8, "bold")).pack(side="left")
        self.mission_elapsed = tk.Label(head, text="", bg=C["panel"], fg=C["dim"], font=("Segoe UI", 8))
        self.mission_elapsed.pack(side="right")

        self.mission_steps: Dict[str, tk.Label] = {}
        steps_fr = tk.Frame(wrap, bg=C["panel"])
        steps_fr.pack(fill="x", padx=6, pady=2)
        for sid in MISSION_STEPS:
            row = tk.Frame(steps_fr, bg=C["panel"])
            row.pack(fill="x", pady=1)
            lab = tk.Label(
                row, text=f"○ {MISSION_LABELS[sid]}", bg=C["panel"], fg=C["dim"],
                font=("Segoe UI", 8), anchor="w",
            )
            lab.pack(fill="x")
            self.mission_steps[sid] = lab

        self.mission_live = tk.Label(
            wrap, text="", bg=C["panel"], fg=C["cyan"], font=("Segoe UI", 8),
            wraplength=148, justify="left", anchor="w",
        )
        self.mission_live.pack(fill="x", padx=6, pady=(2, 6))
        self._mission_states = {s: "pending" for s in MISSION_STEPS}
        self._mission_pulse_on = False

    def mission_clear(self):
        self._stop_mission_pulse()
        self._stop_mission_elapsed()
        self._mission_states = {s: "pending" for s in MISSION_STEPS}
        self._mission_running_step = None
        for sid, lab in self.mission_steps.items():
            lab.config(text=f"○ {MISSION_LABELS[sid]}", fg=C["dim"])
        self.mission_live.config(text="")
        self.mission_elapsed.config(text="")

    def mission_start(self):
        self.mission_clear()
        self._mission_t0 = time.time()
        self._tick_mission_elapsed()

    def _tick_mission_elapsed(self):
        if self._mission_t0 <= 0:
            return
        sec = int(time.time() - self._mission_t0)
        self.mission_elapsed.config(text=f"{sec}s")
        self._mission_elapsed_id = self.after(500, self._tick_mission_elapsed)

    def _stop_mission_elapsed(self):
        if self._mission_elapsed_id:
            try:
                self.after_cancel(self._mission_elapsed_id)
            except Exception:
                pass
            self._mission_elapsed_id = None
        if self._mission_t0 > 0:
            sec = int(time.time() - self._mission_t0)
            self.mission_elapsed.config(text=f"{sec}s")
        self._mission_t0 = 0.0

    def mission_update(self, step: str, state: str, detail: Optional[str] = None):
        if step not in self.mission_steps:
            return
        self._mission_states[step] = state
        icon = {"pending": "○", "running": "◐", "done": "●", "fail": "✕"}.get(state, "○")
        color = {
            "pending": C["dim"],
            "running": C["gold"],
            "done": C["ok"],
            "fail": C["bad"],
        }.get(state, C["dim"])
        self.mission_steps[step].config(text=f"{icon} {MISSION_LABELS[step]}", fg=color)
        if detail:
            self.mission_live.config(text=detail)
        if state == "running":
            self._mission_running_step = step
            self._start_mission_pulse()
        elif self._mission_running_step == step:
            self._mission_running_step = None
            self._stop_mission_pulse()
            self.mission_steps[step].config(text=f"{icon} {MISSION_LABELS[step]}", fg=color)

    def _start_mission_pulse(self):
        self._stop_mission_pulse()
        self._mission_pulse_on = True

        def tick():
            if not self._mission_pulse_on or not self._mission_running_step:
                return
            sid = self._mission_running_step
            lab = self.mission_steps.get(sid)
            if lab:
                cur = lab.cget("text")
                if cur.startswith("◐"):
                    lab.config(text=f"◑ {MISSION_LABELS[sid]}", fg=C["gold"])
                else:
                    lab.config(text=f"◐ {MISSION_LABELS[sid]}", fg=C["cyan"])
            self._mission_pulse_id = self.after(380, tick)

        tick()

    def _stop_mission_pulse(self):
        self._mission_pulse_on = False
        if self._mission_pulse_id:
            try:
                self.after_cancel(self._mission_pulse_id)
            except Exception:
                pass
            self._mission_pulse_id = None

    def _wheel_src(self, e):
        self.src_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

    def _wheel_rail(self, e):
        """Roulette Windows (delta) + Linux (Button-4/5)."""
        if getattr(e, "num", None) == 4:
            self.rail_canvas.yview_scroll(-1, "units")
        elif getattr(e, "num", None) == 5:
            self.rail_canvas.yview_scroll(1, "units")
        else:
            delta = getattr(e, "delta", 0) or 0
            self.rail_canvas.yview_scroll(int(-1 * (delta / 120)), "units")

    def _bind_rail_wheel(self):
        self.rail_canvas.bind_all("<MouseWheel>", self._wheel_rail)
        self.rail_canvas.bind_all("<Button-4>", self._wheel_rail)
        self.rail_canvas.bind_all("<Button-5>", self._wheel_rail)

    def _unbind_rail_wheel(self):
        self.rail_canvas.unbind_all("<MouseWheel>")
        self.rail_canvas.unbind_all("<Button-4>")
        self.rail_canvas.unbind_all("<Button-5>")

    def _inbox_label(self) -> str:
        n = len(self.mem.get("inbox") or [])
        return f"Inbox ({n})" if n else "Inbox"

    def _refresh_inbox_badge(self):
        btn = getattr(self, "btn_inbox", None)
        if not btn:
            return
        try:
            btn.config(text=self._inbox_label())
        except Exception:
            pass

    def hunt_first_watch(self):
        """Place le 1er sujet VEILLE dans la barre chasse + focus (pas de spam multi-chasse)."""
        topics = self.cfg.get("watch", WATCH_DEFAULT) or []
        if not topics:
            return self.say("sys", "Aucun sujet VEILLE.")
        t = topics[0]
        self.hunt.set(t)
        self.focus_hunt()
        self.say("sys", f"Sujet prêt : {t}")

    def focus_hunt(self):
        self.hunt_entry.focus_set()
        self.hunt_entry.select_range(0, "end")

    def _on_hunt_n_change(self):
        try:
            n = int(self.hunt_n_var.get())
        except (TypeError, ValueError, tk.TclError):
            n = HUNT_N
        n = max(3, min(HUNT_N_MAX, n))
        self.hunt_n = n
        self.hunt_n_var.set(n)
        self.cfg["hunt_n"] = n
        savej(CFG_FILE, self.cfg)

    def _on_dig_top3_change(self):
        self.dig_top3 = bool(self.dig_top3_var.get())
        self.cfg["dig_top3"] = self.dig_top3
        savej(CFG_FILE, self.cfg)

    def go_hunt(self):
        q = self.hunt.get().strip()
        if q:
            self.set_pill("mode", "chercher")
            self.set_role("chercheur", sync_mode=True)
            self.run_search(q, self.search_source)

    def dig_profond(self):
        q = self.last_q or self.hunt.get().strip()
        if not q:
            self.say("sys", "Rien à creuser profond.")
            return
        self.set_pill("hmode", "profond")
        self.set_pill("mode", "chercher")
        self.set_role("chercheur", sync_mode=True)
        self.run_search(q, self.search_source)

    def draw_watch(self):
        for w in self.watch_box.winfo_children():
            w.destroy()
        for topic in self.cfg.get("watch", WATCH_DEFAULT)[:20]:
            recent = session_cache_recent(topic)
            label = f"↻ {topic}" if recent else topic
            b = tk.Button(
                self.watch_box, text=label,
                command=lambda t=topic: self.run_search(t, self.search_source),
                bg=C["card"], fg=C["dim"] if recent else C["fg"], relief="flat",
                font=("Segoe UI", 9),
                anchor="w", cursor="hand2", pady=3,
            )
            if recent:
                # tooltip-ish: déjà chassé récemment
                b.configure(text=f"↻ {topic}")
            b.pack(fill="x", pady=1)
            b.bind("<Button-3>", lambda e, t=topic: self.drop_watch(t))
        # refresh scrollregion après redraw
        try:
            self.rail_inner.update_idletasks()
            self.rail_canvas.configure(scrollregion=self.rail_canvas.bbox("all"))
        except Exception:
            pass

    def drop_watch(self, t):
        self.cfg["watch"] = [x for x in self.cfg.get("watch", []) if x != t]
        savej(CFG_FILE, self.cfg)
        self.draw_watch()

    def draw_sources(self):
        for w in self.src_in.winfo_children():
            w.destroy()
        if not self.hits:
            tk.Label(
                self.src_in,
                text="Lance une chasse.\nClic carte = Lecteur.",
                bg=C["bg"], fg=C["dim"], justify="left", font=("Segoe UI", 9),
            ).pack(anchor="w", padx=8, pady=10)
            return
        wrap = max(220, int(self.src_canvas.winfo_width() or 300) - 28)
        for i, it in enumerate(self.hits, 1):
            sel = it["url"] == self.active_url
            card = tk.Frame(
                self.src_in, bg=C["sel"] if sel else C["card"],
                highlightbackground=C["gold"] if sel else C["line"], highlightthickness=1,
                cursor="hand2",
            )
            card.pack(fill="x", padx=5, pady=2)
            inner = tk.Frame(card, bg=card["bg"], cursor="hand2")
            inner.pack(fill="x", padx=7, pady=5)
            badge = " · profond" if it.get("body") else ""
            tk.Label(
                inner, text=f"{i}  {host_of(it['url'])}{badge}", bg=card["bg"], fg=C["gold"],
                font=("Segoe UI", 7, "bold"),
            ).pack(anchor="w")
            tk.Label(
                inner, text=it["title"], bg=card["bg"], fg=C["fg"], wraplength=wrap,
                justify="left", font=("Segoe UI", 9, "bold"),
            ).pack(anchor="w", pady=(1, 1))
            if it.get("snippet"):
                snip = it["snippet"][:110] + ("…" if len(it.get("snippet", "")) > 110 else "")
                tk.Label(
                    inner, text=snip, bg=card["bg"], fg=C["dim"], wraplength=wrap,
                    justify="left", font=("Segoe UI", 8),
                ).pack(anchor="w", pady=(0, 3))
            row = tk.Frame(inner, bg=card["bg"])
            row.pack(anchor="w")
            tk.Button(
                row, text="Lire", command=lambda u=it["url"], t=it["title"]: self.reader(u, t),
                bg=C["gold"], fg="#1a1408", relief="flat", font=("Segoe UI", 7, "bold"), padx=7, pady=2,
            ).pack(side="left")
            tk.Button(
                row, text="Site", command=lambda u=it["url"]: self.open_browser(u),
                bg=C["card2"], fg=C["fg"], relief="flat", font=("Segoe UI", 7), padx=7, pady=2,
            ).pack(side="left", padx=4)

            def _bind_card(w, u=it["url"], t=it["title"]):
                w.bind("<Button-1>", lambda e, uu=u, tt=t: self.reader(uu, tt))

            def _hover_on(e, c=card, inn=inner):
                if it["url"] == self.active_url:
                    return
                c.configure(highlightbackground=C["cyan"], bg=C["card2"])
                inn.configure(bg=C["card2"])
                for ch in inn.winfo_children():
                    try:
                        ch.configure(bg=C["card2"])
                    except Exception:
                        pass
                    if isinstance(ch, tk.Frame):
                        for g in ch.winfo_children():
                            try:
                                g.configure(bg=C["card2"] if isinstance(g, tk.Label) else g.cget("bg"))
                            except Exception:
                                pass

            def _hover_off(e, c=card, inn=inner, selected=sel):
                bg = C["sel"] if (it["url"] == self.active_url) else C["card"]
                hl = C["gold"] if (it["url"] == self.active_url) else C["line"]
                c.configure(highlightbackground=hl, bg=bg)
                inn.configure(bg=bg)
                for ch in inn.winfo_children():
                    try:
                        ch.configure(bg=bg)
                    except Exception:
                        pass
                    if isinstance(ch, tk.Frame):
                        for g in ch.winfo_children():
                            try:
                                if isinstance(g, tk.Label):
                                    g.configure(bg=bg)
                            except Exception:
                                pass

            for w in (card, inner):
                _bind_card(w)
                w.bind("<Enter>", _hover_on)
                w.bind("<Leave>", _hover_off)
            for child in inner.winfo_children():
                if isinstance(child, tk.Label):
                    _bind_card(child)
                    child.bind("<Enter>", _hover_on)
                    child.bind("<Leave>", _hover_off)
        self.after(30, lambda: self.src_canvas.configure(scrollregion=self.src_canvas.bbox("all")))

    def _chat_near_bottom(self, threshold: float = 0.04) -> bool:
        """True si le viewport est déjà près du bas (suivre le flux)."""
        try:
            _first, last = self.chat.yview()
            return float(last) >= (1.0 - threshold)
        except Exception:
            return True

    def _chat_on_yscroll(self, first, last):
        try:
            self.chat.vbar.set(first, last)
        except Exception:
            pass
        self._chat_update_jump_btn()

    def _chat_update_jump_btn(self):
        """Affiche ↓ Bas seulement si l'utilisateur n'est pas en bas."""
        try:
            near = self._chat_near_bottom()
            if near:
                if self._chat_jump_visible:
                    self._jump_bot_btn.place_forget()
                    self._chat_jump_visible = False
            else:
                if not self._chat_jump_visible:
                    self._jump_bot_btn.place(relx=1.0, rely=1.0, x=-14, y=-14, anchor="se")
                    self._chat_jump_visible = True
        except Exception:
            pass

    def _chat_jump_bottom(self):
        """Bouton ↓ Bas: amène au bas du chat."""
        try:
            self.chat.see("end")
            self.chat.yview_moveto(1.0)
        except Exception:
            pass
        self._chat_update_jump_btn()

    def _chat_follow_end(self, force: bool = False):
        """Sticky-bottom: suit la fin seulement si déjà en bas (ou force)."""
        if force or self._chat_near_bottom():
            try:
                self.chat.see("end")
            except Exception:
                pass
        self._chat_update_jump_btn()

    def _chat_see_anchor(self, index: str = ""):
        """Ancre la vue sur un mark (query / début En bref), sans jumper aux URLs."""
        mark = (index or self._chat_anchor or "").strip()
        if not mark:
            self._chat_follow_end(force=True)
            return
        try:
            self.chat.see(mark)
        except Exception:
            try:
                self.chat.see("end")
            except Exception:
                pass
        self._chat_update_jump_btn()

    def say(self, tag: str, text: str, *, force_scroll: bool = False, anchor: bool = False):
        text = clean(text or "")
        self.chat.configure(state="normal")
        if anchor:
            # Capture avant insert: début du message query / En bref
            self._chat_anchor = self.chat.index("end-1c")
        who = {"you": "Toi", "sys": "·", "ai": "Padawan"}.get(tag, tag)
        self.chat.insert("end", f"{who}  {clock()}\n", tag)
        self._insert_linked(self.chat, text + "\n\n", tag)
        self.chat.configure(state="disabled")
        if anchor and self._chat_anchor:
            self._chat_see_anchor(self._chat_anchor)
        else:
            self._chat_follow_end(force=force_scroll)
        self.session["h"].append({"who": tag, "text": text, "t": now()})
        self.mem["sessions"][-1]["history"] = self.session["h"][-120:]
        self.mem["sessions"] = self.mem["sessions"][-30:]
        if tag in ("you", "ai"):
            self.router.append_history(tag, text)
        savej(MEM_FILE, self.mem)

    def say_links(self):
        """Filet sous le brief: titres + URLs cliquables (lecteur / clic droit = nav)."""
        if not self.hits:
            return
        # Ne pas forcer le bas: si user lit En bref, rester ancré
        stick = self._chat_near_bottom()
        self.chat.configure(state="normal")
        self.chat.insert(
            "end",
            f"·  {clock()}\nSources · filet {SEARCH_SOURCE_LABELS.get(self.search_source, self.search_source)} · {HUNT_MODE_LABELS.get(self.hunt_mode, self.hunt_mode)} · n={self.hunt_n}"
            " — clic = lecteur, clic droit = nav\n",
            "sys",
        )
        for i, it in enumerate(self.hits, 1):
            title = clean((it.get("title") or "").strip()) or "sans titre"
            url = (it.get("url") or "").strip()
            self.chat.insert("end", f"{i}. ", "hitn")
            self.chat.insert("end", f"{title}\n", "ai")
            snip = (it.get("snippet") or "").strip()
            if snip:
                short = snip[:140] + ("…" if len(snip) > 140 else "")
                self.chat.insert("end", f"   {short}\n", "snip")
            if url:
                self.chat.insert("end", url + "\n", "url")
        self.chat.insert("end", "\n", "ai")
        self.chat.configure(state="disabled")
        if stick:
            self._chat_follow_end(force=True)
        elif self._chat_anchor:
            self._chat_see_anchor(self._chat_anchor)
        else:
            self._chat_update_jump_btn()

    _MD_INLINE = re.compile(
        r"\[([^\]]+)\]\((https?://[^)\s]+)\)"          # 1,2 lien markdown
        r"|(https?://[^\s\)\]\>\"'\<\>]+)"               # 3 URL brute
        r"|\*\*(.+?)\*\*|__(.+?)__"                     # 4,5 gras
        r"|`([^`\n]+)`"                                  # 6 code
        r"|(?<![\w*])\*(?!\s)([^*\n]+?)\*(?![\w*])"      # 7 italique
        r"|\[(\d{1,2})\](?!\()"                              # 8 citation [n]
    )

    def _md_tags(self, widget):
        if getattr(widget, "_md_ready", False):
            return
        try:
            widget.tag_configure("md_b", font=("Segoe UI", 11, "bold"))
            widget.tag_configure("md_i", font=("Segoe UI", 11, "italic"))
            widget.tag_configure("md_code", font=("Consolas", 10), background=C["card"], foreground=C["ok"])
            widget.tag_configure("md_pre", font=("Consolas", 10), background=C["card"], foreground=C["ok"],
                                 lmargin1=14, lmargin2=14)
            widget.tag_configure("md_h1", font=("Segoe UI", 15, "bold"), foreground=C["gold"], spacing1=8, spacing3=3)
            widget.tag_configure("md_h2", font=("Segoe UI", 13, "bold"), foreground=C["gold"], spacing1=6, spacing3=2)
            widget.tag_configure("md_h3", font=("Segoe UI", 12, "bold"), foreground=C["cyan"], spacing1=4, spacing3=1)
            widget.tag_configure("md_li", lmargin1=12, lmargin2=30)
            widget.tag_configure("md_quote", foreground=C["dim"], lmargin1=16, lmargin2=16,
                                 font=("Segoe UI", 11, "italic"))
            for t in ("md_b", "md_i", "md_code"):
                widget.tag_raise(t)
            widget.tag_configure("cite", foreground=C["cyan"], font=("Segoe UI", 9, "bold"), offset=4)
            widget.tag_raise("url")
            widget.tag_raise("cite")
            widget.tag_bind("cite", "<Button-1>", lambda e, w=widget: self._click_cite(w, e))
            widget.tag_bind("cite", "<Enter>", lambda e, w=widget: w.config(cursor="hand2"))
            widget.tag_bind("cite", "<Leave>", lambda e, w=widget: w.config(cursor="arrow"))
        except Exception as e:
            log(f"md tags: {e}")
        widget._md_ready = True

    def _md_inline(self, widget, text: str, tags: tuple):
        pos = 0
        for m in self._MD_INLINE.finditer(text):
            widget.insert("end", text[pos:m.start()], tags)
            if m.group(1):
                widget.insert("end", m.group(1) + " ", tags + ("md_b",))
                widget.insert("end", m.group(2), tags + ("url",))
            elif m.group(3):
                widget.insert("end", m.group(3), tags + ("url",))
            elif m.group(4) or m.group(5):
                self._md_inline(widget, m.group(4) or m.group(5), tags + ("md_b",))
            elif m.group(6):
                widget.insert("end", m.group(6), tags + ("md_code",))
            elif m.group(7):
                widget.insert("end", m.group(7), tags + ("md_i",))
            elif m.group(8):
                widget.insert("end", f"[{m.group(8)}]", tags + ("cite",))
            pos = m.end()
        widget.insert("end", text[pos:], tags)

    def _insert_linked(self, widget, text: str, base: str):
        """Rendu markdown léger (titres, gras, italique, listes, code, liens cliquables)."""
        if base != "ai":
            pos, rx = 0, re.compile(r"(https?://[^\s\)\]\>\"'\<\>]+)")
            for m in rx.finditer(text):
                widget.insert("end", text[pos:m.start()], base)
                widget.insert("end", m.group(1), "url")
                pos = m.end()
            widget.insert("end", text[pos:], base)
            return
        self._md_tags(widget)
        in_code = False
        lines = text.split("\n")
        for k, line in enumerate(lines):
            nl = "\n" if k < len(lines) - 1 else ""
            st = line.strip()
            if st.startswith("```"):
                in_code = not in_code
                continue
            if in_code:
                widget.insert("end", line + nl, (base, "md_pre"))
                continue
            mh = re.match(r"^(#{1,6})\s+(.*)$", st)
            if mh:
                lvl = min(3, len(mh.group(1)))
                self._md_inline(widget, mh.group(2).strip().strip("*").strip(), (base, f"md_h{lvl}"))
                widget.insert("end", nl, base)
                continue
            if re.match(r"^(\*{3,}|-{3,}|_{3,})$", st):
                widget.insert("end", "─" * 30 + nl, (base, "md_quote"))
                continue
            mb = re.match(r"^(\s*)[-*+•]\s+(.*)$", line)
            if mb:
                ind = "    " * min(3, len(mb.group(1)) // 2)
                widget.insert("end", ind + "•  ", (base, "md_li"))
                self._md_inline(widget, mb.group(2), (base, "md_li"))
                widget.insert("end", nl, base)
                continue
            mn = re.match(r"^(\s*)(\d+)[.)]\s+(.*)$", line)
            if mn:
                widget.insert("end", f"{mn.group(2)}.  ", (base, "md_li", "md_b"))
                self._md_inline(widget, mn.group(3), (base, "md_li"))
                widget.insert("end", nl, base)
                continue
            if st.startswith(">"):
                self._md_inline(widget, st.lstrip("> "), (base, "md_quote"))
                widget.insert("end", nl, base)
                continue
            self._md_inline(widget, line, (base,))
            widget.insert("end", nl, base)

    def url_at(self, widget, e) -> str:
        idx = widget.index(f"@{e.x},{e.y}")
        rng = widget.tag_ranges("url")
        for i in range(0, len(rng), 2):
            a, b = str(rng[i]), str(rng[i + 1])
            if widget.compare(a, "<=", idx) and widget.compare(idx, "<", b):
                return widget.get(a, b).strip()
        f = URL_RE.findall(widget.get(f"{idx.split('.')[0]}.0", f"{idx.split('.')[0]}.end"))
        return f[0] if f else ""

    def click_url(self, e):
        """Clic gauche = Lecteur seulement (jamais webbrowser). Debounce 300 ms."""
        now_t = time.time()
        if (now_t - self._last_url_click) * 1000 < CLICK_DEBOUNCE_MS:
            return
        self._last_url_click = now_t
        u = self.url_at(self.chat, e)
        if u:
            self.reader(u, next((h["title"] for h in self.hits if h["url"] == u), ""))

    def open_browser(self, url: str):
        if not url:
            return

        def _open():
            try:
                webbrowser.open_new_tab(url)
            except Exception as ex:
                log(f"browser: {ex}")
                self.after0(self.status.config, text="nav bloquée", fg=C["bad"])

        threading.Thread(target=_open, daemon=True).start()

    def open_site(self):
        self.open_browser(self.active_url)

    def copy_link(self):
        if self.active_url:
            self.clipboard_clear()
            self.clipboard_append(self.active_url)
            self.status.config(text="lien copié", fg=C["ok"])

    def step(self, delta: int):
        if not self.hits:
            return
        urls = [h["url"] for h in self.hits]
        i = urls.index(self.active_url) if self.active_url in urls else -1
        it = self.hits[max(0, min(len(urls) - 1, i + delta))]
        self.reader(it["url"], it["title"])

    def _skel_text(self) -> str:
        return (
            "▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓\n"
            "▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ · · ·\n"
            "▓▓▓▓▓▓▓▓▓▓▓▓▓▓\n"
            "▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓\n"
            "\nChargement… (anti-freeze)"
        )

    def reader(self, url: str, title: str = ""):
        self.active_url = url
        self._reader_job += 1
        job_id = self._reader_job
        self.rtitle.config(text=title or url, fg=C["fg"])
        self.rhost.config(text=host_of(url))
        self.nb.select(self.tab_read)
        self.draw_sources()
        cached = next((h.get("body") for h in self.hits if h["url"] == url and h.get("body")), None)
        self.rbox.configure(state="normal")
        self.rbox.delete("1.0", "end")
        if cached:
            self.rbox.insert("end", cached + "\n\n")
            self.rbox.insert("end", url, "url")
            self.rbox.configure(state="disabled")
            if not self.busy:
                self.status.config(text="● prêt", fg=C["ok"])
            return
        self.rbox.insert("1.0", self._skel_text(), "skel")
        self.rbox.configure(state="disabled")
        self.status.config(text="Lecteur…", fg=C["gold"])

        def job():
            if self.router.can("read_page"):
                body = self.router.call_tool("read_page", url=url, limit=8000)
            else:
                body = read_page(url)

            def show():
                if job_id != self._reader_job:
                    return
                self.rbox.configure(state="normal")
                self.rbox.delete("1.0", "end")
                self.rbox.insert("end", body + "\n\n" if body else "Paywall / JS / timeout. Ouvre le site.\n\n")
                self.rbox.insert("end", url, "url")
                self.rbox.configure(state="disabled")
                if not self.busy:
                    self.status.config(text="● prêt", fg=C["ok"])

            self.after0(show)

        threading.Thread(target=job, daemon=True).start()

    def read_top3(self):
        if not self.hits:
            self.say("sys", "Aucune source.")
            return
        top = [h for h in self.hits[:3] if not is_dead(h["url"])]
        if not top:
            self.say("sys", "Rien de lisible dans le top 3.")
            return
        self._cancel.clear()
        self.lock(True, "Lecteur…")

        def job():
            parts = []
            for i, it in enumerate(top, 1):
                if self._cancel.is_set():
                    break
                self.after0(self.status.config, text=f"Lecteur… {i}/{len(top)}", fg=C["gold"])
                self.after0(self._preview_skel, it["url"], it["title"])
                if it.get("body"):
                    body = it["body"]
                elif self.router.can("read_page"):
                    body = self.router.call_tool("read_page", url=it["url"], limit=4000)
                else:
                    body = read_page(it["url"], 4000)
                parts.append(
                    f"── {i}. {it['title']}  ({host_of(it['url'])}) ──\n"
                    f"{body or '(vide / paywall)'}\n\n{it['url']}\n"
                )
            if self._cancel.is_set():
                self.after0(self.say, "sys", "Lecture top 3 annulée.")
            else:
                full = "\n".join(parts)

                def show():
                    self.active_url = top[0]["url"]
                    self.rtitle.config(text=f"Top {len(top)} sources", fg=C["fg"])
                    self.rhost.config(text="")
                    self.nb.select(self.tab_read)
                    self.rbox.configure(state="normal")
                    self.rbox.delete("1.0", "end")
                    self.rbox.insert("1.0", full)
                    self.rbox.configure(state="disabled")
                    self.draw_sources()

                self.after0(show)
            self.after0(self.lock, False, "● prêt")

        threading.Thread(target=job, daemon=True).start()

    def _preview_skel(self, url: str, title: str):
        self.active_url = url
        self.rtitle.config(text=title or url, fg=C["fg"])
        self.rhost.config(text=host_of(url))
        self.nb.select(self.tab_read)
        self.rbox.configure(state="normal")
        self.rbox.delete("1.0", "end")
        self.rbox.insert("1.0", self._skel_text(), "skel")
        self.rbox.configure(state="disabled")

    def cancel_job(self):
        if not self.busy:
            return
        self._cancel.set()
        self.status.config(text="Annulation…", fg=C["bad"])
        self.busy_lbl.config(text="annulation…")

    def lock(self, on: bool, label=""):
        self.busy = on
        if on:
            self._cancel.clear()
        self.ent.configure(state="disabled" if on else "normal")
        self.hunt_entry.configure(state="disabled" if on else "normal")
        st = label or ("occupe…" if on else "● prêt")
        self.status.config(text=st, fg=C["gold"] if on else C["ok"])
        if on:
            self.busy_lbl.config(text=f"{st}  ·  Échap / Annuler")
            self.input_tip.config(text="Padawan travaille… Échap pour annuler")
            try:
                self.cancel_btn.pack(anchor="w", pady=(0, 6), before=self.status)
            except Exception:
                self.cancel_btn.pack(anchor="w", pady=(0, 6))
            try:
                self.act_btns["stop"].pack(side="left", padx=2, before=self.act_btns["copy"])
                for w in self.sugg_bar.winfo_children():
                    w.destroy()
            except Exception:
                pass
            self._start_pulse()
        else:
            try:
                self.act_btns["stop"].pack_forget()
            except Exception:
                pass
            self.busy_lbl.config(text="")
            self.input_tip.config(
                text="Écris ici… Entrée = envoyer · Échap = annuler  ·  Voyant modèle: gris=check, or=load, vert=prêt, rouge=off",
                fg=C["dim"],
            )
            self.cancel_btn.pack_forget()
            self._stop_pulse()
            self._stop_mission_elapsed()
            self.ent.focus_set()

    def _start_pulse(self):
        self._stop_pulse()
        self._pulse_n = 0
        dots = ("réflexion", "réflexion·", "réflexion··", "réflexion···")

        def tick():
            if not self.busy:
                return
            self._pulse_n = (self._pulse_n + 1) % 4
            cur = self.status.cget("text")
            if not (cur.startswith("Chasse") or cur.startswith("Lecteur") or cur.startswith("Annul")
                    or cur.startswith("Mission")):
                self.busy_lbl.config(text=f"{dots[self._pulse_n]}  ·  Échap / Annuler")
            self._pulse_id = self.after(420, tick)

        tick()

    def _stop_pulse(self):
        if self._pulse_id:
            try:
                self.after_cancel(self._pulse_id)
            except Exception:
                pass
            self._pulse_id = None

    def set_model_status(self, state: str, detail: str = "") -> None:
        """Update model chip: checking|loading|ready|down|error — thread-safe via after0."""
        labels = {
            "checking": ("vérif…", C["dim"]),
            "loading": ("chargement…", C["gold"]),
            "ready": ("prêt", C["ok"]),
            "down": ("Ollama down", C["bad"]),
            "error": ("échec", C["bad"]),
        }
        text, color = labels.get(state, ("vérif…", C["dim"]))
        if detail and state in ("error", "loading"):
            short = (detail[:28] + "…") if len(detail) > 28 else detail
            if state == "error":
                text = f"échec · {short}" if short else text

        phase_map = {
            "checking": ("Ollama : vérification…", C["dim"]),
            "loading": ("Modèle : chargement…", C["gold"]),
            "ready": ("Modèle : prêt", C["ok"]),
            "down": ("Ollama : échec", C["bad"]),
            "error": ("Modèle : échec", C["bad"]),
        }
        phase_txt, phase_fg = phase_map.get(state, ("Ollama : vérification…", C["dim"]))
        if state == "down" and detail:
            phase_txt = f"Ollama : échec ({detail[:40]})"
        elif state == "error" and detail:
            phase_txt = f"Modèle : échec ({detail[:40]})"
        elif state == "loading" and detail and "télécharg" in detail.lower():
            phase_txt = (
                detail
                if (
                    detail.startswith("Ollama")
                    or detail.startswith("Téléchargement")
                    or detail.startswith("Modèle")
                )
                else f"Téléchargement…"
            )

        def apply():
            if hasattr(self, "model_dot"):
                self.model_dot.config(fg=color)
            if hasattr(self, "model_lbl"):
                self.model_lbl.config(text=text, fg=color)
            if hasattr(self, "ollama_phase"):
                self.ollama_phase.config(text=phase_txt, fg=phase_fg)
            if state == "ready":
                if not self.busy:
                    self.status.config(text="● Modèle : prêt", fg=C["ok"])
            elif state == "loading":
                if not self.busy:
                    self.status.config(text=f"● {phase_txt}", fg=C["gold"])
            elif state == "checking":
                if not self.busy:
                    self.status.config(text="● Ollama : vérification…", fg=C["dim"])
            elif state == "down":
                if not self.busy:
                    self.status.config(text=f"● {phase_txt}", fg=C["bad"])
            elif state == "error":
                if not self.busy:
                    self.status.config(text=f"● {phase_txt}", fg=C["bad"])

        self.after0(apply)

    def on_length_chosen(self, *_):
        """Réglage Style de réponse: Court / Équilibré / Développé (persisté)."""
        lab = self.lenvar.get()
        lv = next((k for k, v in LENGTH_LABELS.items() if v == lab), "detaillee")
        GEN["level"] = lv
        self.cfg["longueur"] = lv
        try:
            savej(CFG_FILE, self.cfg)
        except Exception as e:
            log(f"save longueur: {e}")
        self._ui_status(f"Style de réponse : {LENGTH_LABELS[lv]}", C["ok"])

    def on_model_chosen(self, *_):
        raw = self.mvar.get()
        name = model_id_from_label(raw)
        self.model = name
        self.cfg["model"] = name
        savej(CFG_FILE, self.cfg)
        self.model_ready = False
        # Remet le libellé propre (id seul) pendant le pull; refresh après warm
        try:
            self.mvar.set(name)
        except Exception:
            pass
        if MODEL_DL_MARK in (raw or ""):
            self._ui_status(f"Téléchargement {name}…", C["gold"])
            self.set_model_status("loading", f"Téléchargement {name}…")
        threading.Thread(target=self.warm_model, args=(name,), daemon=True).start()

    def _ui_status(self, text: str, fg: str | None = None):
        """Status bar + phase Ollama thread-safe via after()."""
        color = fg or C["gold"]
        clean = text[1:].lstrip() if text.startswith("●") else text

        def apply():
            try:
                self.status.config(text=text if text.startswith("●") else f"● {text}", fg=color)
                if hasattr(self, "ollama_phase") and (
                    clean.startswith("Ollama")
                    or clean.startswith("Modèle")
                    or clean.startswith("Téléchargement")
                ):
                    self.ollama_phase.config(text=clean, fg=color)
            except Exception:
                pass

        self.after0(apply)

    def _ask_install_ollama(self) -> bool:
        """Dialog Tk (thread principal via event) — consentement install Ollama + modèle."""
        # Si déjà consenti en config, OK
        if self.cfg.get("ollama_install_ok"):
            return True
        result = {"ok": False}
        done = threading.Event()

        def ask():
            try:
                ok = messagebox.askyesno(
                    "Installer Ollama ?",
                    "Ollama n'est pas installé sur ce PC.\n\n"
                    f"Padawan peut l'installer et télécharger le modèle {MODEL}.\n"
                    "Ça peut demander des droits admin et du réseau.\n\n"
                    "Installer Ollama + modèle ?",
                    parent=self,
                )
                result["ok"] = bool(ok)
                if ok:
                    self.cfg["ollama_install_ok"] = True
                    savej(CFG_FILE, self.cfg)
            except Exception as e:
                log(f"ask_install: {e}")
                result["ok"] = False
            finally:
                done.set()

        self.after0(ask)
        done.wait(timeout=300)
        return bool(result["ok"])

    def retry_ollama(self):
        """Bouton Relancer Ollama — thread, n'bloque pas l'UI."""
        if self._model_warming:
            self.say("sys", "Déjà en train de relancer Ollama…")
            return
        self.say("sys", "Relance Ollama…")
        threading.Thread(target=self.warm_model, kwargs={"force_boot": True}, daemon=True).start()

    def warm_model(self, name: str | None = None, force_boot: bool = False):
        name = model_id_from_label(name or self.mvar.get() or self.model or MODEL)
        self._model_check_gen += 1
        gen = self._model_check_gen
        self._model_warming = True
        self.set_model_status("checking")
        self._ui_status("Ollama : vérification…", C["dim"])

        def on_status(msg: str):
            if gen != self._model_check_gen:
                return
            m = msg or ""
            if (
                m.startswith("Ollama")
                or m.startswith("Modèle")
                or m.startswith("Téléchargement")
            ):
                self._ui_status(m, C["gold"])
            else:
                self._ui_status(f"Ollama : {m}", C["gold"])

        try:
            # 1) ping / auto-start / install
            on_status("Ollama : vérification…")
            if force_boot or not ollama_up():
                on_status("Ollama : absent → démarrage…")
                ok_boot, detail = ensure_ollama_running(
                    cancel=None,
                    on_status=on_status,
                    allow_install=True,
                    ask_install=self._ask_install_ollama,
                )
                if gen != self._model_check_gen:
                    return
                if not ok_boot:
                    self.ready = False
                    self.model_ready = False
                    fail = detail or "Impossible de démarrer Ollama (installe-le?)"
                    self.set_model_status("down", fail)
                    self._ui_status(f"Ollama : échec ({fail[:40]})", C["bad"])
                    self.after0(self.say, "sys", fail)
                    return

            if gen != self._model_check_gen:
                return
            self.ready = True
            self._ui_status("Ollama : serveur OK", C["ok"])

            # 2) modèle présent ? sinon pull
            if not model_in_tags(name):
                self.set_model_status("loading", f"Téléchargement {name}…")
                on_status(f"Téléchargement {name}…")
                ok_pull, pdetail = ensure_model_present(name, cancel=None, on_status=on_status)
                if gen != self._model_check_gen:
                    return
                if not ok_pull:
                    self.model_ready = False
                    fail = pdetail or "téléchargement échoué"
                    self.set_model_status("error", fail)
                    self._ui_status(f"Modèle : échec ({fail[:40]})", C["bad"])
                    return
                # refresh combobox models (locaux + catalogue manquants)
                try:
                    mods = models()
                    self.mods = mods
                    def _apply_mods():
                        try:
                            self.model_combo.config(values=mods)
                            # sélectionner l'id sans marqueur s'il est local maintenant
                            for lab in mods:
                                if model_id_from_label(lab) == name and MODEL_DL_MARK not in lab:
                                    self.mvar.set(lab)
                                    break
                            else:
                                self.mvar.set(name)
                        except Exception:
                            pass
                    self.after0(_apply_mods)
                except Exception:
                    pass

            if gen != self._model_check_gen:
                return
            if model_loaded(name):
                self.model_ready = True
                self.set_model_status("ready")
                self._ui_status("Modèle : prêt", C["ok"])
                return

            self.model_ready = False
            self.set_model_status("loading")
            self._ui_status("Modèle : chargement…", C["gold"])
            ok, detail = ensure_model(name, cancel=None)
            if gen != self._model_check_gen:
                return
            if ok:
                self.model_ready = True
                self.set_model_status("ready", detail)
                self._ui_status("Modèle : prêt", C["ok"])
            else:
                self.model_ready = False
                fail = detail or "chargement échoué"
                self.set_model_status("error", fail)
                self._ui_status(f"Modèle : échec ({fail[:40]})", C["bad"])
        finally:
            if gen == self._model_check_gen:
                self._model_warming = False

    def ping(self):
        """Check Ollama up (auto-start si besoin), then warm the current model."""
        threading.Thread(target=self.warm_model, kwargs={"force_boot": True}, daemon=True).start()

    def _ensure_model_ready_or_kick(self) -> bool:
        """Gate envoi: True si modèle prêt. Sinon kick warm + message sys."""
        if self.model_ready and self.ready:
            return True
        if self._model_warming:
            self.say("sys", "Ollama / modèle encore en train de démarrer… attends le voyant vert (ou Relancer).")
            return False
        self.say("sys", "Ollama pas prêt — démarrage auto… attends le voyant vert.")
        threading.Thread(target=self.warm_model, kwargs={"force_boot": True}, daemon=True).start()
        return False

    def _wait_model_ready(self, timeout: float = 300.0) -> bool:
        """Bloquant (thread worker): ensure ollama+model, attendre model_ready."""
        if self.model_ready and ollama_up():
            return True
        name = model_id_from_label(self.mvar.get() or self.model or MODEL)

        def on_status(msg: str):
            m = msg or ""
            if (
                m.startswith("Ollama")
                or m.startswith("Modèle")
                or m.startswith("Téléchargement")
            ):
                self._ui_status(m, C["gold"])
            else:
                self._ui_status(f"Ollama : {m}", C["gold"])

        self._ui_status("Ollama : vérification…", C["dim"])
        ok_boot, detail = ensure_ollama_running(
            cancel=self._cancel,
            on_status=on_status,
            allow_install=True,
            ask_install=self._ask_install_ollama,
        )
        if not ok_boot:
            self.model_ready = False
            self.ready = False
            fail = detail or "Impossible de démarrer Ollama (installe-le?)"
            self.after0(self.set_model_status, "down", fail)
            self._ui_status(f"Ollama : échec ({fail[:40]})", C["bad"])
            return False
        self.ready = True
        self._ui_status("Ollama : serveur OK", C["ok"])
        if not model_in_tags(name):
            on_status(f"Téléchargement {name}…")
            ok_pull, pdetail = ensure_model_present(name, cancel=self._cancel, on_status=on_status)
            if not ok_pull:
                self.model_ready = False
                fail = pdetail or "téléchargement échoué"
                self.after0(self.set_model_status, "error", fail)
                self._ui_status(f"Modèle : échec ({fail[:40]})", C["bad"])
                return False
        self.after0(self.set_model_status, "loading")
        self._ui_status("Modèle : chargement…", C["gold"])
        ok, _detail = ensure_model(name, cancel=self._cancel)
        if ok:
            self.model_ready = True
            self.ready = True
            self.after0(self.set_model_status, "ready")
            self._ui_status("Modèle : prêt", C["ok"])
            return True
        self.model_ready = False
        fail = _detail or "chargement échoué"
        self.after0(self.set_model_status, "error", fail)
        self._ui_status(f"Modèle : échec ({fail[:40]})", C["bad"])
        return False

    def _ollama(
        self,
        user: str,
        on_token=None,
        *,
        use_history: bool = True,
        hunt_query: Optional[str] = None,
    ) -> str:
        """Chat Ollama. use_history=False isole le brief de chasse (anti context-bleed)."""
        if self._cancel.is_set():
            return ""
        hist: List[Dict[str, str]] = []
        if use_history:
            # Mémoire de conversation: vrais tours user/assistant (pas de troncature à 350 car.)
            raw = list(self.router.history())
            # le dernier "you" = question courante (déjà dans user) -> on l'exclut
            if raw and raw[-1].get("who") == "you":
                raw = raw[:-1]
            n = LENGTH_HIST_TURNS[gen_level()]
            for x in raw[-n:]:
                role = {"you": "user", "ai": "assistant"}.get(x.get("who"))
                if role:
                    hist.append({"role": role, "content": str(x.get("text") or "")[:4000]})
        # Isolation stricte si use_history=False: pas de last_a / chat ancien / parked / ADN
        return chat_stream(
            model_id_from_label(self.mvar.get()), user,
            system=self.router.system_prompt(hunt_query=hunt_query),
            on_token=on_token,
            cancel=self._cancel,
            history=hist,
        )

    def _begin_stream(self) -> str:
        self.chat.configure(state="normal")
        # Ancre sur le début de la réponse (En bref), pas sur les Sources futures
        header_at = self.chat.index("end-1c")
        self.chat.insert("end", f"Padawan  {clock()}\n", "ai")
        mark = self.chat.index("end-1c")
        self.chat.insert("end", "", "stream")
        self.chat.configure(state="disabled")
        # Pendant une chasse: ancrer sur query/début brief; sinon sticky-bottom
        if getattr(self, "_hunt_query", ""):
            self._chat_anchor = header_at
            self._chat_see_anchor(header_at)
        else:
            self._chat_follow_end(force=True)
        return mark

    def _append_stream(self, mark: str, token: str, buf: list):
        buf.append(token)
        stick = self._chat_near_bottom()
        self.chat.configure(state="normal")
        self.chat.insert("end", token, "stream")
        self.chat.configure(state="disabled")
        # Sticky-bottom only: si user lit le début, ne pas forcer see/end
        if stick:
            self._chat_follow_end(force=True)
        else:
            self._chat_update_jump_btn()

    def _finish_stream(self, mark: str, full: str):
        full = clean(full or "")
        stick = self._chat_near_bottom()
        self.chat.configure(state="normal")
        # Remplace le flux brut par la version finale (URLs cliquables via _insert_linked)
        try:
            if mark:
                self.chat.delete(mark, "end")
        except Exception:
            pass
        self._insert_linked(self.chat, full + "\n\n", "ai")
        self.chat.configure(state="disabled")
        # Ne pas jumper aux Sources URLs si l'user lit En bref
        if stick:
            self._chat_follow_end(force=True)
        elif self._chat_anchor:
            self._chat_see_anchor(self._chat_anchor)
        else:
            self._chat_update_jump_btn()
        self.session["h"].append({"who": "ai", "text": full, "t": now()})
        self.mem["sessions"][-1]["history"] = self.session["h"][-120:]
        self.mem["sessions"] = self.mem["sessions"][-30:]
        self.router.append_history("ai", full)
        savej(MEM_FILE, self.mem)
        self.after(400, self._suggest_followups, full)

    # ── v39h: actions réponse ───────────────────────────────────────────────
    def _click_cite(self, widget, e):
        try:
            idx = widget.index(f"@{e.x},{e.y}")
            rng = widget.tag_prevrange("cite", idx + "+1c")
            txt = widget.get(rng[0], rng[1]) if rng else ""
            n = int(re.sub(r"\D", "", txt) or 0)
            if 1 <= n <= len(self.hits):
                h = self.hits[n - 1]
                self.reader(h["url"], h.get("title", ""))
        except Exception as ex:
            log(f"cite: {ex}")

    def copy_answer(self):
        if not self.last_a:
            self._ui_status("Rien à copier.", C["dim"]); return
        self.clipboard_clear()
        self.clipboard_append(self.last_a)
        self._ui_status("Réponse copiée.", C["ok"])

    def regenerate(self):
        if self.busy or not self.last_q:
            return
        q = self.last_q
        if getattr(self, "_last_kind", "chat") == "hunt":
            self._regen = True
            self.run_search(q, self.search_source)
        else:
            self.say("sys", "Régénération.")
            if not self.ready or not self.model_ready:
                if not self._ensure_model_ready_or_kick():
                    return
            self.lock(True, "réflexion.")
            threading.Thread(target=self.think, args=(q,), daemon=True).start()

    def export_answer(self):
        if not self.last_a:
            self._ui_status("Rien à exporter.", C["dim"]); return
        try:
            path = filedialog.asksaveasfilename(
                parent=self, title="Exporter la réponse", defaultextension=".md",
                initialfile=f"padawan_{time.strftime('%Y%m%d_%H%M')}",
                filetypes=[("Markdown", "*.md"), ("Page HTML", "*.html")],
            )
            if not path:
                return
            md_text = f"# {self.last_q}\n\n_{_today_fr()[0]}_\n\n{self.last_a}\n"
            if path.lower().endswith((".html", ".htm")):
                out = md_to_html(md_text, self.last_q)
            else:
                out = md_text
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(out)
            self._ui_status(f"Exporté: {os.path.basename(path)}", C["ok"])
        except Exception as ex:
            log(f"export: {ex}")
            self._ui_status(f"Export raté: {ex}", C["bad"])

    def speak_answer(self):
        p = getattr(self, "_tts_proc", None)
        if p and p.poll() is None:
            try:
                p.kill()
            except Exception:
                pass
            self._tts_proc = None
            self.act_btns["speak"].config(text="🔊 Lire")
            return
        if not self.last_a:
            return
        txt = md_to_speech(self.last_a)
        try:
            self._tts_proc = speak_fr(txt)
            if self._tts_proc:
                self.act_btns["speak"].config(text="🔇 Arrêter")

                def _watch():
                    try:
                        self._tts_proc.wait()
                    except Exception:
                        pass
                    self.after0(lambda: self.act_btns["speak"].config(text="🔊 Lire"))
                threading.Thread(target=_watch, daemon=True).start()
        except Exception as ex:
            log(f"tts: {ex}")
            self._ui_status("Voix indisponible.", C["bad"])

    def _suggest_followups(self, answer: str):
        q = self.last_q or ""
        if not q or self.busy or not self.model_ready:
            return
        gen = getattr(self, "_sugg_gen", 0) + 1
        self._sugg_gen = gen
        model = model_id_from_label(self.mvar.get())

        def job():
            qs = suggest_followups(model, q, answer)
            if qs and gen == self._sugg_gen and not self.busy:
                self.after0(self._draw_followups, qs)
        threading.Thread(target=job, daemon=True).start()

    def _draw_followups(self, qs: List[str]):
        if self.busy:
            return
        for w in self.sugg_bar.winfo_children():
            w.destroy()
        tk.Label(self.sugg_bar, text="Suivi :", bg=C["bg"], fg=C["dim"],
                 font=("Segoe UI", 8)).pack(side="left", padx=(2, 4))
        for sq in qs[:3]:
            tk.Button(
                self.sugg_bar, text=sq[:70], command=lambda x=sq: self._ask_followup(x),
                bg=C["card2"], fg=C["cyan"], relief="flat", font=("Segoe UI", 8),
                padx=6, pady=1, cursor="hand2", activebackground=C["gold"],
            ).pack(side="left", padx=2)

    def _ask_followup(self, q: str):
        if self.busy:
            return
        for w in self.sugg_bar.winfo_children():
            w.destroy()
        if getattr(self, "_last_kind", "chat") == "hunt":
            self.run_search(q, self.search_source)
        else:
            self.var.set(q)
            self.send()

    def send(self):
        if self.busy:
            return
        q = self.var.get().strip()
        if not q:
            return
        self.var.set("")
        self.last_q = q
        self._last_kind = "chat"
        self.say("you", q)

        if self.router.active == "capitaine":
            if not self.ready or not self.model_ready:
                if not self._ensure_model_ready_or_kick():
                    return
            self.lock(True, "réflexion…")
            threading.Thread(target=self.think_capitaine, args=(q,), daemon=True).start()
            return

        if self.mode == "chercher" or self.router.active == "chercheur":
            self.run_search(q, self.search_source)
            return
        if not self.ready or not self.model_ready:
            if not self._ensure_model_ready_or_kick():
                return
        self.lock(True, "réflexion…")
        threading.Thread(target=self.think, args=(q,), daemon=True).start()

    def think_capitaine(self, q: str):
        try:
            low = q.lower()
            if any(k in low for k in ("liste tâche", "liste tache", "mes tâches", "mes taches", "get_task")):
                tasks = tool_get_task_list()
                if not tasks:
                    self.after0(self.say, "ai", "Aucune tâche.")
                    self.after0(self.notify_done, "Padawan — chat", "Réponse prête")
                    return
                lines = [
                    f"[{t.get('status','?')}] {t.get('id')} · {t.get('description','')} (prio {t.get('priority','')})"
                    for t in tasks
                ]
                self.after0(self.say, "ai", "Tâches:\n" + "\n".join(lines))
                self.after0(self.notify_done, "Padawan — chat", "Réponse prête")
                return
            m_add = re.match(r"(?:ajoute|add)\s+(?:tâche|tache)\s*[:\-]?\s*(.+)", q, re.I)
            if m_add:
                item = tool_add_task(m_add.group(1).strip())
                self.after0(self.say, "ai", f"Tâche ajoutée · {item['id']} — {item['description']}")
                self.after0(self.notify_done, "Padawan — chat", "Réponse prête")
                return
            m_done = re.match(r"(?:termine|done|fini)\s+(?:tâche|tache)?\s*([a-f0-9]{6,})", q, re.I)
            if m_done:
                item = tool_update_task(m_done.group(1).strip(), status="done")
                self.after0(self.say, "ai", f"Marquée done · {item['id']}")
                self.after0(self.notify_done, "Padawan — chat", "Réponse prête")
                return

            mark_holder: list = []
            token_buf: list = []

            def ui_start():
                mark_holder.append(self._begin_stream())

            self.after0(ui_start)
            time.sleep(0.05)

            def on_tok(t: str):
                if mark_holder:
                    self.after0(self._append_stream, mark_holder[0], t, token_buf)

            ans = self._ollama(
                f"Marc demande: {q}\n"
                "Réponds en capitaine: oriente (chercher / contredire / parler), "
                "ou gère les tâches. 1-3 phrases, pas d'invention, pas de liens, pas de moraline.",
                on_token=on_tok,
            )
            if self._cancel.is_set():
                self.after0(self.say, "sys", "Annulé.")
                return
            self.last_a = ans
            if mark_holder:
                self.after0(self._finish_stream, mark_holder[0], ans)
            else:
                self.after0(self.say, "ai", ans)
            self.after0(self.notify_done, "Padawan — chat", "Réponse prête")
        except Exception as e:
            self.after0(self.say, "sys", str(e))
            self.after0(self.notify_done, "Padawan — chat", f"Échec · {e}", force=True)
        finally:
            self.after0(self.lock, False, "● prêt")

    def think(self, q: str):
        try:
            web = ""
            want_web = (
                self.mode == "contredire"
                or self.router.active == "contrarian"
                or (self.router.active == "compagnon" and needs_web(q))
            )
            if self._cancel.is_set():
                return
            if want_web:
                kind = "news" if (self.mode == "contredire" or self.router.active == "contrarian") else self.search_source
                self.after0(self.mission_start)
                mode = "rapide" if self.hunt_mode == "rapide" else "multi"
                n = max(3, min(HUNT_N_MAX, int(getattr(self, "hunt_n", HUNT_N))))

                def on_prog(step, state, detail):
                    self.after0(self.mission_update, step, state, detail)

                items, _meta = hunt_pipeline(
                    q, kind=kind, n=n, mode=mode, source=kind,
                    dig_top3=bool(getattr(self, "dig_top3", False)),
                    on_progress=on_prog, cancel=self._cancel, model=model_id_from_label(self.mvar.get()),
                )
                if self._cancel.is_set():
                    return
                self.hits = items
                self.after0(self.draw_sources)
                web = "SOURCES:\n" + "\n".join(
                    f"- {i['title']}\n  {i['url']}\n  {i['snippet']}" for i in items
                )
            extra = ""
            if self.mode == "contredire" or self.router.active == "contrarian":
                extra = "MODE CONTREDIRE: thèse charitable, trous, contre-thèse. Sans moraliser."

            mark_holder: list = []
            token_buf: list = []

            def ui_start():
                mark_holder.append(self._begin_stream())

            self.after0(ui_start)
            time.sleep(0.05)

            def on_tok(t: str):
                if mark_holder:
                    self.after0(self._append_stream, mark_holder[0], t, token_buf)

            if want_web:
                self.after0(self.mission_update, "brief", "running", "dolphin3…")
                # Isolation: pas d'historique rôle / last_a / parked dans le brief web
                ans = self._ollama(
                    f"{web}\n\n{extra}\n\n"
                    f"QUERY COURANTE: {q}\n"
                    f"Si les sources digressent, ignore-les. Reste sur: {q}\n"
                    "Réponds UNIQUEMENT à cette query avec les SOURCES ci-dessus. "
                    "INTERDIT de répéter la query. "
                    + ("Format: **En bref** (3-6 phrases) / **À retenir** (puces) / " if gen_level() == "courte" else
                       "Format: **En bref** (un vrai paragraphe de synthèse) / **En détail** (sections expliquées, "
                       "contexte, chiffres et nuances tirés des SOURCES) / **À retenir** (puces concrètes) / ")
                    + 
                    "**💡 Pour aller plus loin** (1-3 puces) / "
                    "**Sources** (titre + URL complète). "
                    "INTERDIT sections vides Flou/Ça change/Prochaine coupe. "
                    "Si les sources sont minces, dis-le puis complète avec tes connaissances générales (présentées comme telles). "
                    "INTERDIT anciens projets / ADN / idées garées / chat antérieur.",
                    on_token=on_tok,
                    use_history=False,
                    hunt_query=q,
                )
                ans = postprocess_hunt_brief(ans, getattr(self, "hits", []) or [], q)
            else:
                ans = self._ollama(f"{web}\n\n{extra}\n\nMarc: {q}" + forme_vivante(q), on_token=on_tok)
            if want_web:
                self.after0(self.mission_update, "brief", "done" if not self._cancel.is_set() else "fail", None)
            if self._cancel.is_set():
                self.after0(self.say, "sys", "Annulé.")
                return
            self.last_a = ans
            if mark_holder:
                self.after0(self._finish_stream, mark_holder[0], ans)
            else:
                self.after0(self.say, "ai", ans)
            if web:
                self.after0(self.say_links)
            self.after0(self.notify_done, "Padawan — chat", "Réponse prête")
        except Exception as e:
            self.after0(self.say, "sys", str(e))
            self.after0(self.notify_done, "Padawan — chat", f"Échec · {e}", force=True)
        finally:
            self.after0(self.lock, False, "● prêt")

    def run_search(self, q: str, kind: str = "web"):
        if self.busy:
            return
        # Nouveau hunt_id: isole brief (pas last_a / chat / parked / ADN)
        self.clear_hunt_context(wipe_role_hist=True, reason=f"début chasse · {q[:60]}")
        self.last_q = q
        self._hunt_query = q
        self.hunt.set(q)
        source = kind if kind in SEARCH_SOURCES else self.search_source
        if source not in SEARCH_SOURCES:
            source = "web"
        if self.session["h"] and self.session["h"][-1].get("text") != q:
            self.say("you", q, force_scroll=True, anchor=True)
        elif not self.session["h"]:
            self.say("you", q, force_scroll=True, anchor=True)
        if self.router.active not in ("chercheur", "contrarian"):
            self.set_role("chercheur", sync_mode=True)
        mode = self.hunt_mode if self.hunt_mode in HUNT_MODES else "multi"
        n = max(3, min(HUNT_N_MAX, int(getattr(self, "hunt_n", HUNT_N))))
        dig = bool(getattr(self, "dig_top3", False))
        src_lab = SEARCH_SOURCE_LABELS.get(source, source)
        self.lock(True, f"Mission… {src_lab} · {HUNT_MODE_LABELS.get(mode, mode)}")
        self.mission_start()

        def job():
            try:
                if self._cancel.is_set():
                    return
                # Auto-boot Ollama avant brief / enrich (DDGS seul marche offline)
                if not ollama_up():
                    self.after0(self._ui_status, "Ollama : absent → démarrage…", C["gold"])
                    ok_boot, detail = ensure_ollama_running(
                        cancel=self._cancel,
                        on_status=lambda m: self._ui_status(
                            m if (m or "").startswith(("Ollama", "Modèle")) else f"Ollama : {m}",
                            C["gold"]),
                        allow_install=True,
                        ask_install=self._ask_install_ollama,
                    )
                    if not ok_boot:
                        self.after0(self.say, "sys", detail or "Impossible de démarrer Ollama (installe-le?)")
                        # continue quand même la chasse web sans LLM brief si possible
                    else:
                        self.ready = True
                        self.after0(self._ui_status, "Ollama : serveur OK", C["ok"])

                def on_prog(step, state, detail):
                    self.after0(self.mission_update, step, state, detail)
                    if state == "running" and step == "moteurs":
                        self.after0(self.status.config, text="Mission… moteurs", fg=C["gold"])
                    elif state == "running" and step == "enrichir":
                        self.after0(self.status.config, text="Mission… enrichir", fg=C["gold"])
                    elif state == "done" and detail == "cache":
                        self.after0(self.status.config, text="Mission… cache", fg=C["cyan"])

                _nocache = bool(getattr(self, "_regen", False))
                self._regen = False
                self._last_kind = "hunt"
                items, meta = hunt_pipeline(
                    q, kind=source, n=n, mode=mode, source=source,
                    dig_top3=dig, use_session_cache=not _nocache,
                    on_progress=on_prog, cancel=self._cancel, model=model_id_from_label(self.mvar.get()),
                )
                self.after0(self.draw_watch)  # rafraîchir marqueurs VEILLE
                if meta.get("from_cache"):
                    self.after0(self.say, "sys", f"Cache session · {src_lab} · {q[:50]}")
                elif meta.get("widened"):
                    self.after0(
                        self.say, "sys",
                        f"Source {src_lab} sans hits → élargi au web · {q[:50]}",
                    )
                if self._cancel.is_set():
                    self.after0(self.say, "sys", "Chasse annulée.")
                    self.after0(self.mission_update, "brief", "fail", "annulé")
                    return
                if not items:
                    err = meta.get("ddgs_error") or _summarize_ddgs_errors(meta.get("ddgs_errors") or [])
                    attempts = ", ".join(meta.get("attempts") or []) or "aucune tentative"
                    widen = " · élargi au web" if meta.get("widened") else ""
                    # v39g: hors ligne / filet vide -> réponse locale vivante au lieu d'un échec
                    if self._answer_local_fallback(q, f"{err}{widen} - {attempts}"):
                        return
                    raise RuntimeError(
                        f"Filet vide — {err}{widen} · tentatives: {attempts}"
                    )
                self.hits = items
                self.after0(self.draw_sources)
                self.after0(self.nb.select, self.tab_src)

                pack = []
                for i, it in enumerate(items, 1):
                    block = f"{i}. {it['title']}\n{it['url']}\n{it['snippet']}"
                    if it.get("dig_summary"):
                        block += f"\n[résumé creusé]\n{it['dig_summary'][:900]}"
                    elif it.get("body"):
                        block += f"\n[extrait page]\n{it['body'][:1800]}"
                    pack.append(block)

                if self._cancel.is_set():
                    self.after0(self.say, "sys", "Chasse annulée.")
                    return

                if not self.model_ready:
                    self.after0(self.status.config, text="● Chargement modèle…", fg=C["gold"])
                    self.after0(self.mission_update, "brief", "running", "chargement modèle…")
                    if not self._wait_model_ready():
                        raise RuntimeError("Modèle pas chargé — voyant rouge.")

                self.after0(self.mission_update, "brief", "running", "brief dolphin3…")
                self.after0(self.status.config, text="Mission… brief", fg=C["gold"])

                mark_holder: list = []
                token_buf: list = []

                def ui_start():
                    mark_holder.append(self._begin_stream())

                self.after0(ui_start)
                time.sleep(0.05)

                def on_tok(t: str):
                    if mark_holder:
                        self.after0(self._append_stream, mark_holder[0], t, token_buf)

                engines = ", ".join(f"{k}:{v}" for k, v in (meta.get("engine_hits") or {}).items())
                dug = " et résumés creusés" if dig or mode == "profond" else " seulement"
                cache_note = " (cache)" if meta.get("from_cache") else ""
                dropped = meta.get("relevance_dropped") or []
                drop_note = ""
                if dropped:
                    drop_note = (
                        f"\n(Ignorés hors-sujet: {len(dropped)} source(s) — "
                        "ne les mentionne pas.)\n"
                    )
                ans = self._ollama(
                    f"QUERY COURANTE (seule question à traiter): {q}\n"
                    f"Date du jour: {_today_fr()[0]}. Intention comprise: {meta.get('intent', 'general')}"
                    + (f" - sujet réel: {meta.get('topic')}" if meta.get('topic') else "")
                    + (" (QUESTION D'ACTUALITÉ: parle de la situation RÉELLE et RÉCENTE décrite par les sources "
                       "- acteurs, événements, chiffres, dates - pas de définition ni d'étymologie d'un mot familier)"
                       if meta.get('intent') == 'actualite' else "")
                    + "\n"
                    f"Source: {src_lab} · pouvoir: {mode} · n={n}{cache_note}\n"
                    f"Moteurs: {engines}\n"
                    f"session_hunt_id={getattr(self, 'session_hunt_id', 0)}\n"
                    f"{drop_note}\n"
                    f"SNIPPETS / RESULTS DE CETTE CHASSE UNIQUEMENT:\n"
                    f"{chr(10).join(pack)}\n\n"
                    "CONSIGNES STRICTES:\n"
                    f"- Réponds UNIQUEMENT à la query courante, à partir des "
                    "snippets/results de CETTE chasse.\n"
                    "- INTERDIT de répéter / reformuler la query en ouverture.\n"
                    "- INTERDIT d'évoquer anciens projets, génératrices, HHO, ADN, "
                    "mission non liée, idées garées, chat antérieur ou tout sujet "
                    "non présent dans cette query / ces snippets.\n"
                    f"- Si les sources digressent, ignore-les. Reste sur: {q}\n"
                    + ("- Format OBLIGATOIRE (FR court):\n"
                       "  **En bref** - 3 à 6 phrases utiles, zéro répétition.\n" if gen_level() == "courte" else
                       "- Format OBLIGATOIRE (FR, complet et structuré, markdown):\n"
                       "  **En bref** - un paragraphe de synthèse clair.\n"
                       "  ### En détail - 2 à 4 sous-parties (### titre) qui expliquent le contexte, "
                       "les acteurs, les causes, les chiffres et dates tirés des results, et les nuances.\n")
                    + 
                    "  **À retenir** — puces concrètes (faits / chiffres / dates sourcés).\n"
                    "  **Sources** — pour chaque hit pertinent: titre puis URL complète "
                    "(ligne séparée, URL réelle des results).\n"
                    "- INTERDIT sections vides génériques « Flou / Ça change / Prochaine coupe ».\n"
                    "- Si les results sont minces: dis-le en une phrase, puis complète avec tes connaissances générales solides, "
                    "présentées clairement comme telles (sans inventer de faits précis ni d'URL).\n"
                    "- AUCUNE URL dans ton texte: les Sources sont ajoutées automatiquement.\n"
                    "- CITE tes sources avec leur numéro entre crochets, ex. [1] ou [2][4], juste après le fait.\n"
                    "- Ensuite **Mon take** - ton analyse nuancée (causes, enjeux, ce qui pourrait arriver) "
                    "et dis franchement si les sources sont faibles (rubriques, archives, titres sans contenu).\n"
                    "- FINIS par **💡 Pour aller plus loin** - 1 à 3 puces vivantes: idée connexe, "
                    "question à creuser ou prochaine étape pratique.\n"
                    "- Brief à partir des titres/snippets"
                    + dug
                    + ". "
                    "Allégations = allégations (pas des faits). Pas de moraline. "
                    "Si le snippet est mince, dis-le clairement.",
                    on_token=on_tok,
                    use_history=False,
                    hunt_query=q,
                )
                if self._cancel.is_set():
                    self.after0(self.mission_update, "brief", "fail", "annulé")
                    self.after0(self.say, "sys", "Chasse annulée.")
                    return
                # Post-traitement: dédup + injecte toujours les URLs des hits retenus
                ans = postprocess_hunt_brief(ans, items, q)
                self.after0(self.mission_update, "brief", "done", "ok")
                self.last_a = ans
                if mark_holder:
                    self.after0(self._finish_stream, mark_holder[0], ans)
                else:
                    self.after0(self.say, "ai", ans)
                self.after0(self.say_links)
                self.mem["searches"].append({
                    "q": q, "kind": source, "source": source, "mode": mode, "t": now(),
                    "n": n, "dig_top3": dig,
                    "engines": meta.get("engine_hits"),
                    "from_cache": meta.get("from_cache"),
                })
                self.mem["searches"] = self.mem["searches"][-80:]
                savej(MEM_FILE, self.mem)
                self.after0(self.notify_done, "Padawan — chasse", f"Brief prêt · {q[:60]}")
            except Exception as e:
                self.after0(self.mission_update, "brief", "fail", str(e)[:60])
                self.after0(self.say, "sys", f"Chasse ratée : {e}")
                self.after0(self.notify_done, "Padawan — chasse", f"Échec · {e}", force=True)
            finally:
                self.after0(self.lock, False, "● prêt")

        threading.Thread(target=job, daemon=True).start()

    def _answer_local_fallback(self, q: str, why: str = "") -> bool:
        """v39g: chasse vide (hors ligne?) -> réponse vivante avec les connaissances du modèle local."""
        try:
            log(f"chasse vide -> réponse locale: {why[:200]}")
            if self._cancel.is_set():
                return False
            if not self.model_ready and not self._wait_model_ready():
                return False
            self.after0(self.mission_update, "brief", "running", "réponse locale")
            self.after0(self.say, "sys", "🌲 Pas de résultats web (hors ligne ?) - je te réponds avec mes connaissances locales.")
            mark_holder: list = []
            token_buf: list = []
            self.after0(lambda: mark_holder.append(self._begin_stream()))
            time.sleep(0.05)

            def on_tok(t: str):
                if mark_holder:
                    self.after0(self._append_stream, mark_holder[0], t, token_buf)

            ans = self._ollama(
                "(Aucune source web disponible pour cette question. Exceptionnellement, oublie les consignes "
                "sur les SOURCES et snippets: réponds avec tes connaissances générales, sans URL, "
                "et signale franchement ce qui mériterait d'être vérifié.)\n\n"
                f"Marc: {q}" + forme_vivante(q),
                on_token=on_tok,
                use_history=False,
            )
            if self._cancel.is_set():
                self.after0(self.mission_update, "brief", "fail", "annulé")
                self.after0(self.say, "sys", "Chasse annulée.")
                return True
            self.last_a = ans
            if mark_holder:
                self.after0(self._finish_stream, mark_holder[0], ans)
            else:
                self.after0(self.say, "ai", ans)
            self.after0(self.mission_update, "brief", "done", "local")
            self.after0(self.notify_done, "Padawan - chasse", f"Réponse locale prête - {q[:60]}")
            return True
        except Exception as e:
            log(f"réponse locale: {e}")
            return False

    def dig(self):
        if not self.last_q:
            return self.say("sys", "Rien à creuser.")
        if self.busy:
            return
        if not self.ready or not self.model_ready:
            if not self._ensure_model_ready_or_kick():
                return
        self.lock(True, "réflexion…")

        def job():
            try:
                if self._cancel.is_set():
                    return
                q2 = self._ollama(
                    f"Q: {self.last_q}\nR:\n{self.last_a[:1000]}\n\n"
                    "Donne SEULEMENT la prochaine requête web, 6-12 mots."
                )
                if self._cancel.is_set():
                    self.after0(self.say, "sys", "Annulé.")
                    return
                q2 = re.sub(r'[\n"«»]', " ", q2).strip()[:80]

                def then():
                    self.lock(False, "● prêt")
                    self.run_search(q2, self.search_source)

                self.after0(then)
            except Exception as e:
                self.after0(self.say, "sys", str(e))
                self.after0(self.lock, False, "● prêt")

        threading.Thread(target=job, daemon=True).start()

    def flip(self):
        if not self.last_a:
            return
        self.set_pill("mode", "contredire")
        self.set_role("contrarian", sync_mode=True)
        self.var.set(self.last_q or "Contredis le dernier brief.")
        self.send()

    def park(self):
        txt = self.var.get().strip() or self.hunt.get().strip() or self.last_q
        if not txt:
            return self.say("sys", "Rien à garer.")
        self.mem["inbox"].insert(0, {"text": txt, "t": now(), "done": False})
        self.mem["inbox"] = self.mem["inbox"][:80]
        savej(MEM_FILE, self.mem)
        self._refresh_inbox_badge()
        self.say("sys", f"Garé. {len(self.mem['inbox'])} idée(s).")

    def show_inbox(self):
        pop = tk.Toplevel(self)
        pop.title("Inbox · Idées garées")
        pop.configure(bg=C["bg"])
        pop.geometry("600x480")
        tk.Label(
            pop, text="Idées garées — Relancer ou Supprimer.",
            bg=C["bg"], fg=C["gold"], font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w", padx=10, pady=(8, 4))

        wrap = tk.Frame(pop, bg=C["bg"])
        wrap.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        canvas = tk.Canvas(wrap, bg=C["bg"], highlightthickness=0)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=canvas.yview, style="Gold.Vertical.TScrollbar")
        inner = tk.Frame(canvas, bg=C["bg"])
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        win = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win, width=max(200, e.width - 4)))

        def _wheel(e):
            if getattr(e, "num", None) == 4:
                canvas.yview_scroll(-1, "units")
            elif getattr(e, "num", None) == 5:
                canvas.yview_scroll(1, "units")
            else:
                canvas.yview_scroll(int(-1 * ((e.delta or 0) / 120)), "units")

        canvas.bind("<Enter>", lambda e: (canvas.bind_all("<MouseWheel>", _wheel), canvas.bind_all("<Button-4>", _wheel), canvas.bind_all("<Button-5>", _wheel)))
        canvas.bind("<Leave>", lambda e: (canvas.unbind_all("<MouseWheel>"), canvas.unbind_all("<Button-4>"), canvas.unbind_all("<Button-5>")))

        def refresh():
            for w in inner.winfo_children():
                w.destroy()
            items = list(self.mem.get("inbox") or [])[:40]
            if not items:
                tk.Label(
                    inner, text="Inbox vide — Gare l'idée (Ctrl+I) pour y mettre une question.",
                    bg=C["bg"], fg=C["dim"], font=("Segoe UI", 10), wraplength=520, justify="left",
                ).pack(anchor="w", padx=8, pady=20)
                return
            for idx, it in enumerate(items):
                row = tk.Frame(inner, bg=C["card"], highlightbackground=C["line"], highlightthickness=1)
                row.pack(fill="x", padx=4, pady=2)
                stamp = (it.get("t") or "")[5:16]
                txt = (it.get("text") or "")[:100]
                tk.Label(
                    row, text=f"{stamp}  {txt}", bg=C["card"], fg=C["fg"],
                    font=("Segoe UI", 9), anchor="w", wraplength=380, justify="left",
                ).pack(side="left", fill="x", expand=True, padx=7, pady=4)

                def relancer(t=it.get("text", ""), p=pop):
                    self._from_inbox(t, p)

                def supprimer(i=idx):
                    try:
                        del self.mem["inbox"][i]
                    except Exception:
                        return
                    savej(MEM_FILE, self.mem)
                    self._refresh_inbox_badge()
                    refresh()

                tk.Button(
                    row, text="Relancer", command=relancer, bg=C["gold"], fg="#1a1408",
                    relief="flat", font=("Segoe UI", 8, "bold"), padx=7, pady=2, cursor="hand2",
                ).pack(side="right", padx=(2, 5), pady=3)
                tk.Button(
                    row, text="Suppr.", command=supprimer, bg=C["card2"], fg=C["bad"],
                    relief="flat", font=("Segoe UI", 8), padx=6, pady=2, cursor="hand2",
                ).pack(side="right", padx=2, pady=3)

        refresh()

    def _from_inbox(self, text, pop):
        try:
            pop.destroy()
        except Exception:
            pass
        self.hunt.set(text)
        self.var.set(text)
        self.ent.focus_set()

    def show_tasks(self):
        """Éditeur Tâches simple (ADN léger) — liste scrollable."""
        pop = tk.Toplevel(self)
        pop.title("Tâches · ADN")
        pop.configure(bg=C["bg"])
        pop.geometry("580x500")
        tk.Label(
            pop, text="Liste éditable · mark done.",
            bg=C["bg"], fg=C["gold"], font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w", padx=10, pady=(8, 4))

        wrap = tk.Frame(pop, bg=C["bg"])
        wrap.pack(fill="both", expand=True, padx=10)
        canvas = tk.Canvas(wrap, bg=C["bg"], highlightthickness=0)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=canvas.yview, style="Gold.Vertical.TScrollbar")
        list_fr = tk.Frame(canvas, bg=C["bg"])
        list_fr.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        win = canvas.create_window((0, 0), window=list_fr, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win, width=max(200, e.width - 4)))

        def _wheel(e):
            if getattr(e, "num", None) == 4:
                canvas.yview_scroll(-1, "units")
            elif getattr(e, "num", None) == 5:
                canvas.yview_scroll(1, "units")
            else:
                canvas.yview_scroll(int(-1 * ((e.delta or 0) / 120)), "units")

        canvas.bind("<Enter>", lambda e: (canvas.bind_all("<MouseWheel>", _wheel), canvas.bind_all("<Button-4>", _wheel), canvas.bind_all("<Button-5>", _wheel)))
        canvas.bind("<Leave>", lambda e: (canvas.unbind_all("<MouseWheel>"), canvas.unbind_all("<Button-4>"), canvas.unbind_all("<Button-5>")))

        def refresh():
            for w in list_fr.winfo_children():
                w.destroy()
            tasks = load_tasks()
            if not tasks:
                tk.Label(list_fr, text="Aucune tâche.", bg=C["bg"], fg=C["dim"]).pack(anchor="w", pady=12)
                return
            for t in tasks:
                row = tk.Frame(list_fr, bg=C["card"], highlightbackground=C["line"], highlightthickness=1)
                row.pack(fill="x", pady=2)
                st = t.get("status", "open")
                fg = C["ok"] if st == "done" else C["fg"]
                tk.Label(
                    row,
                    text=f"[{st}] {t.get('id')} · {t.get('description','')[:70]}  (prio {t.get('priority','')})",
                    bg=C["card"], fg=fg, font=("Segoe UI", 9), anchor="w",
                ).pack(side="left", fill="x", expand=True, padx=7, pady=4)

                def mark(tid=t.get("id")):
                    try:
                        tool_update_task(tid, status="done")
                        refresh()
                    except Exception as ex:
                        messagebox.showerror("Tâche", str(ex))

                def reopen(tid=t.get("id")):
                    try:
                        tool_update_task(tid, status="open")
                        refresh()
                    except Exception as ex:
                        messagebox.showerror("Tâche", str(ex))

                if st != "done":
                    tk.Button(
                        row, text="Done", command=mark, bg=C["gold"], fg="#1a1408",
                        relief="flat", font=("Segoe UI", 8, "bold"), padx=8,
                    ).pack(side="right", padx=4, pady=4)
                else:
                    tk.Button(
                        row, text="Réouvrir", command=reopen, bg=C["card2"], fg=C["fg"],
                        relief="flat", font=("Segoe UI", 8), padx=8,
                    ).pack(side="right", padx=4, pady=4)

        add_fr = tk.Frame(pop, bg=C["bg"])
        add_fr.pack(fill="x", padx=10, pady=10)
        v = tk.StringVar()
        if self.last_q:
            v.set(self.last_q[:120])
        e = self._make_entry(add_fr, v, font_size=11)
        e.pack(side="left", fill="x", expand=True, ipady=4)
        e.focus_set()

        def add(_=None):
            desc = v.get().strip()
            if not desc:
                return
            try:
                tool_add_task(desc)
                v.set("")
                refresh()
            except Exception as ex:
                messagebox.showerror("Tâche", str(ex))

        def from_idea():
            q = (self.last_q or "").strip()
            if not q:
                messagebox.showinfo("Tâche", "Pas de dernière idée (last_q vide).")
                return
            v.set(q[:120])
            e.focus_set()

        tk.Button(
            add_fr, text="Depuis idée", command=from_idea, bg=C["card2"], fg=C["fg"],
            relief="flat", font=("Segoe UI", 9), padx=8,
        ).pack(side="right", padx=(6, 0))
        tk.Button(
            add_fr, text="Ajouter", command=add, bg=C["gold"], fg="#1a1408",
            relief="flat", font=("Segoe UI", 10, "bold"), padx=12,
        ).pack(side="right", padx=(8, 0))
        pop.bind("<Return>", add)
        refresh()

    def add_watch(self):
        pop = tk.Toplevel(self)
        pop.configure(bg=C["bg"])
        pop.geometry("420x110")
        v = tk.StringVar()
        e = self._make_entry(pop, v, font_size=12)
        e.pack(fill="x", padx=12, pady=16, ipady=6)
        e.focus_set()

        def add(_=None):
            t = v.get().strip()
            if t and t not in self.cfg.get("watch", []):
                self.cfg["watch"] = self.cfg.get("watch", []) + [t]
                savej(CFG_FILE, self.cfg)
                self.draw_watch()
            pop.destroy()

        pop.bind("<Return>", add)
        tk.Button(pop, text="Ajouter", command=add, bg=C["gold"], fg="#1a1408", relief="flat").pack()

    def copy_last(self):
        txt = (self.last_a or "").strip()
        if not txt:
            try:
                sel = self.chat.get("sel.first", "sel.last")
                txt = (sel or "").strip()
            except Exception:
                txt = ""
        if not txt:
            txt = (self.last_q or "").strip()
        if not txt:
            return self.say("sys", "Rien à copier.")
        self.clipboard_clear()
        self.clipboard_append(txt)
        self.status.config(text="copié", fg=C["ok"])

    def clear_hunt_context(self, *, wipe_role_hist: bool = True, reason: str = "") -> None:
        """Nouvelle page / début chasse: isole le brief (pas de bleed HHO/ADN/chat)."""
        self.session_hunt_id = int(getattr(self, "session_hunt_id", 0) or 0) + 1
        self._hunt_query = ""
        self.hits = []
        # last_a hors chasse: ne pas réinjecter un vieux brief dans la suivante
        self.last_a = ""
        if wipe_role_hist:
            try:
                # chercheur surtout — évite bleed projets anciens dans le brief
                self.router.clear_history("chercheur")
            except Exception as e:
                log(f"clear_hunt_context: {e}")
        try:
            self.after0(self.draw_sources)
        except Exception:
            pass
        if reason:
            log(f"hunt ctx cleared id={self.session_hunt_id} · {reason}")

    def clear_chat(self):
        self.chat.configure(state="normal")
        self.chat.delete("1.0", "end")
        self.chat.configure(state="disabled")
        self.session = {"t": now(), "h": []}
        self.mem["sessions"].append({"start": self.session["t"], "history": self.session["h"]})
        savej(MEM_FILE, self.mem)
        self.mission_clear()
        self.clear_hunt_context(wipe_role_hist=True, reason="nouvelle page")
        self.say("sys", "Nouvelle page. Contexte chasse vidé. Tape en bas →")
        self.ent.focus_set()

    def export(self):
        default = f"padawan_export_{datetime.now().strftime('%Y%m%d')}.txt"
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Texte", "*.txt")],
            initialfile=default,
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            for x in self.session["h"]:
                f.write(f"{x['who']} ({x['t']})\n{x['text']}\n\n")
        self.status.config(text="exporté", fg=C["ok"])

    # ----- v35 window / tray / startup -----
    def _apply_startup_window(self):
        """Maximisé Windows (zoomed) si cfg fullscreen — pas exclusive F11."""
        if not self.cfg.get("fullscreen", True):
            return
        try:
            self.update_idletasks()
            self.state("zoomed")
        except Exception:
            try:
                self.attributes("-zoomed", True)
            except Exception:
                try:
                    sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
                    self.geometry(f"{sw}x{sh}+0+0")
                except Exception:
                    pass

    def _sync_windows_startup(self):
        """Applique cfg start_with_windows (HKCU Run seulement; purge Startup .bat) → shell:Startup + HKCU Run."""
        want = bool(self.cfg.get("start_with_windows", True))
        try:
            path = ensure_windows_startup(want, os.path.abspath(__file__))
            self.cfg["_startup_path"] = path
            savej(CFG_FILE, self.cfg)
            if want and path and path != "(retirée)":
                self.say("sys", f"Auto-start Windows: {path}")
        except Exception as e:
            log(f"sync startup: {e}")

    def set_start_with_windows(self, enable: bool):
        self.cfg["start_with_windows"] = bool(enable)
        path = ensure_windows_startup(bool(enable), os.path.abspath(__file__))
        self.cfg["_startup_path"] = path
        savej(CFG_FILE, self.cfg)
        self.say("sys", f"Démarrer avec Windows: {'oui' if enable else 'non'} → {path}")

    def _setup_tray(self):
        self._tray_log = log
        setup_tray(self, app_name=APP_NAME, log_fn=log)

    def launch_file_manager(self):
        """Lance gestionnaire_fichiers5.py via padawan_tray (pythonw)."""
        _tray_launch_fm(
            BASE,
            say=self.say,
            app_name=APP_NAME,
            parent=self,
            log_fn=log,
        )

    def launch_archiveur(self):
        """Lance archiveur4.py (repli archiveur3/2/1) via padawan_tray (pythonw)."""
        _tray_launch_archiveur(
            BASE,
            say=self.say,
            app_name=APP_NAME,
            parent=self,
            log_fn=log,
        )

    def show_from_tray(self):
        _tray_show(self)

    def hide_to_tray(self):
        _tray_hide(self, app_name=APP_NAME)

    def _persist_cfg(self, *, light: bool = False):
        try:
            self.cfg["model"] = model_id_from_label(self.mvar.get())
            self.cfg["role"] = self.router.active
            self.cfg["hunt_mode"] = self.hunt_mode
            self.cfg["search_source"] = getattr(self, "search_source", "web")
            self.cfg["hunt_n"] = max(3, min(HUNT_N_MAX, int(getattr(self, "hunt_n", HUNT_N))))
            self.cfg["dig_top3"] = bool(getattr(self, "dig_top3", False))
            self.cfg["fullscreen"] = bool(self.cfg.get("fullscreen", True))
            self.cfg["start_with_windows"] = bool(self.cfg.get("start_with_windows", True))
            savej(CFG_FILE, self.cfg)
            if not light:
                savej(MEM_FILE, self.mem)
        except Exception as e:
            log(f"persist: {e}")

    def on_close(self):
        """X = hide to tray (pas kill). Sans tray → quit réel."""
        if self._quitting:
            return
        if TRAY_AVAILABLE and self._tray_icon is not None:
            self.hide_to_tray()
            return
        self.quit_padawan()

    def quit_padawan(self):
        """Quitter vraiment (menu tray Quitter Padawan)."""
        if self._quitting:
            return
        self._quitting = True
        self._cancel.set()
        if self._tip_blink_id:
            try:
                self.after_cancel(self._tip_blink_id)
            except Exception:
                pass
        self._stop_pulse()
        self._stop_mission_pulse()
        self._stop_mission_elapsed()
        self._persist_cfg(light=False)
        stop_tray(self)
        try:
            self.destroy()
        except Exception:
            pass


if __name__ == "__main__":
    try:
        if not acquire_single_instance():
            raise SystemExit(0)
    except SystemExit:
        raise
    except Exception:
        pass
    # Purge legacy Startup bat (doublons); Run gere via cfg/_sync
    try:
        from padawan_tray import _remove_legacy_startup_files
        _remove_legacy_startup_files(lambda _m: None)
    except Exception:
        pass
    app = Padawan()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    try:
        app.mainloop()
    except Exception as e:
        print(e)
        log(str(e))
        input("entree...")
