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
import random
import unicodedata
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
try:  # v39.6 🧠 gestionnaire de modèles (facultatif : Padawan marche sans)
    import padawan_modeles as _PM
except Exception:  # pragma: no cover
    _PM = None
try:  # v40.0 💻 Atelier (facultatif aussi)
    import padawan_atelier as _PA
except Exception:  # pragma: no cover
    _PA = None
try:  # v41.0 🎨 Studio d'images (facultatif : sans lui, pas de Studio ni d'images générées dans les jeux)
    import padawan_studio as _PS
except Exception:
    _PS = None
try:  # v40.2 🖼 illustrations ANSI des jeux (facultatif : sans lui, les jeux gardent l'art ASCII)
    import padawan_ansi as _ANSI
except Exception:  # pragma: no cover
    _ANSI = None
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
# v39.5 : réglages et état privés hors de FTP_HOME -> C:\web_private\Padawan (PC de Marc),
# sinon %APPDATA%\Padawan. Migration auto au démarrage : l'ancien fichier du dossier du
# programme est copié puis rangé dans C:\web_private\bak\config_move_<date>\Padawan\.
try:
    import padawan_commun as _pc
    PRIVATE_DIR = _pc.private_dir("Padawan")
    _PRIVATE_MOVED = _pc.migrate_private("Padawan", BASE, (
        "config.json", "memory.json", "tasks.json", "search_cache.json",
        "errors.log", "errors.log.1"), PRIVATE_DIR)
except Exception:   # padawan_commun absent : ancien comportement
    _pc, PRIVATE_DIR, _PRIVATE_MOVED = None, BASE, []
MEM_FILE, CFG_FILE = os.path.join(PRIVATE_DIR, "memory.json"), os.path.join(PRIVATE_DIR, "config.json")
CACHE_FILE, LOG_FILE = os.path.join(PRIVATE_DIR, "search_cache.json"), os.path.join(PRIVATE_DIR, "errors.log")
TASKS_FILE = os.path.join(PRIVATE_DIR, "tasks.json")
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
PROMPT_MODEL_DEFAULT = "(modèle courant)"  # v39.6
MODEL_DL_MARK = " (à télécharger)"
APP_NAME = "Padawan"
APP_FILE_VER = 39  # v39.1: 🧹 Nouvelle conversation (Ctrl+L / Ctrl+Shift+N), Historique
APP_SUB_VER = "41.2"  # v41.2: 💻 Atelier / 🎨 Studio s'ouvrent aussi en plein jeu (le jeu est mis sur pause, modèle d'avant rétabli) ; Atelier : 📎 Insérer un fichier (Ctrl+I, glisser-déposer). v41.1: v41.1: jeux — jamais avec un modèle « coder » (bascule temporaire dolphin3:8b, retour en quittant, jamais sauvé) ; réponse sans choix ou coupée → relance auto « termine et propose des choix », sinon ▶ Continuer + choix de secours. v41.0: 🎨 Studio d'images (ComfyUI local + SD-Turbo, démarré à la demande sur 127.0.0.1 : idée FR → prompt EN par le modèle courant, 6 styles en un clic, graine, variations, image + art ANSI côte à côte, .png/.ans/.html, galerie, jonglage mémoire graphique avec Ollama, module padawan_studio.py) + jeux 🖼 Images : Banque / Générées / Fixes / NON (scène dessinée en arrière-plan, cache par scène, repli banque). v40.2: 🖼 illustrations ANSI originales dans les jeux (31 scènes : Fallout Pip-Boy vert, Donjon 16 couleurs DOS, Polar film noir ; détection de scène, effet CRT, clic = agrandir, bascule 🖼 Images, export HTML). v40.1: 🖼→ANSI dans l'Atelier (image → art ANSI/ASCII : 16 couleurs DOS ▀▄, truecolor, ASCII, Pip-Boy, ░▒▓█ ; .ans + SAUCE, .txt, HTML rétro, insérer dans l'onglet, vraie console ; module padawan_ansi.py, API image_to_ansi() pour les jeux). v40.0: 💻 Atelier (mode programmeur : chat + éditeur à onglets coloré, aperçu HTML auto-rechargé, Python exécuté, 🩺 corriger l'erreur, diff accepter/rejeter, déploiement Python/Web/FTP-SFTP avec .bak, projets, modèles, snippets) + copier/coller partout (📋 sur les blocs de code, clic droit, collage multiligne). v39.8: jeu — un clic n'est jamais perdu (file d'attente pendant le chargement du modèle, repli dolphin3), statut de chargement chronométré, Mission vidée en mode jeu. v39.7: 🧠 recommandés cliquables (⬇ Installer / ⭐ Activer) + bouton par ligne au catalogue. v39.6: 🧠 Modèles (diagnostic machine, catalogue, installation, banc d'essai) + modèle par prompt. v39.5: réglages privés -> C:\web_private\Padawan (migration auto). v39.4: 📰 Nouvelles (🌍 géopolitique 2077, 🔭 découvertes) + inventaire du jeu robuste + départ Chercheur
_APP_FILE_VER_OLD = 39  # version fichier seulement — jamais affichée comme titre produit
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
                # v39.8 : même contexte que les réponses → un seul chargement (avant : 4096 puis 8192 = 2 chargements)
                "options": {"num_ctx": int(GEN.get("num_ctx") or 0) or _detect_num_ctx()},
            },
            timeout=(OLLAMA_CONNECT, 300),
            retries=1,
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
    try:  # rotation : errors.log garde au plus ~2 Mo (+ errors.log.1), il ne grossit plus sans fin
        if os.path.getsize(LOG_FILE) > 2 * 1024 * 1024:
            os.replace(LOG_FILE, LOG_FILE + ".1")
    except OSError:
        pass
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


# ── v39.1: archive des conversations (données, hors FTP_HOME) ────────────────
CONV_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "Padawan", "conversations")


def conv_archive(roles: Dict[str, list], session_h: list, *, reason: str = "", role: str = "") -> Optional[str]:
    """Écrit un JSON horodaté si quelque chose a été dit. Rien n'est effacé ailleurs."""
    said = [x for x in (session_h or []) if x.get("who") in ("you", "ai")]
    if not said and not any(roles.values()):
        return None
    os.makedirs(CONV_DIR, exist_ok=True)
    first = next((x.get("text", "") for x in said if x.get("who") == "you"), "")
    if not first:
        for h in roles.values():
            first = next((x.get("text", "") for x in h if x.get("who") == "you"), "")
            if first: break
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = os.path.join(CONV_DIR, f"conv_{stamp}.json")
    n = 1
    while os.path.exists(path):
        n += 1; path = os.path.join(CONV_DIR, f"conv_{stamp}_{n}.json")
    data = {"date": stamp, "reason": reason, "role": role, "title": (first or "(sans titre)")[:80],
            "session": session_h or [], "roles": roles}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return path


def conv_list() -> List[Dict[str, str]]:
    out = []
    try:
        names = sorted((n for n in os.listdir(CONV_DIR) if n.endswith(".json")), reverse=True)
    except Exception:
        return out
    for n in names[:300]:
        p = os.path.join(CONV_DIR, n)
        try:
            with open(p, encoding="utf-8") as f: d = json.load(f)
            out.append({"path": p, "title": str(d.get("title") or ""),
                        "label": str(d.get("date") or n).replace("_", " ")})
        except Exception:
            continue
    return out


def conv_render(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f: d = json.load(f)
    except Exception as e:
        return f"Lecture impossible: {e}"
    who = {"you": "Toi", "ai": "Padawan", "sys": "·"}
    rows = [x for x in (d.get("session") or []) if x.get("who") in ("you", "ai")]
    if not rows:
        for h in (d.get("roles") or {}).values(): rows.extend(h)
    return "\n\n".join(f"{who.get(x.get('who'), x.get('who'))}  {x.get('t', '')}\n{x.get('text', '')}" for x in rows) or "(vide)"


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


# ── v39.2: 📜 Bibliothèque de prompts (favoris éditables, actif par rôle) ────────
# Données privées: C:\web_private\Padawan\prompts.json (jamais sous FTP_HOME).
# .bak: C:\web_private\bak\ (copie avant chaque écriture + instantané du jour).
# Sur un autre PC (installé par le setup) sans C:\web_private : %APPDATA%\Padawan.
_WEB_PRIVATE = r"C:\web_private"
_HAS_WEB_PRIVATE = os.name == "nt" and os.path.isdir(_WEB_PRIVATE)
PROMPTS_DIR = os.environ.get("PADAWAN_PROMPTS_DIR") or (
    PRIVATE_DIR if _pc is not None else
    os.path.join(_WEB_PRIVATE, "Padawan") if _HAS_WEB_PRIVATE
    else os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "Padawan")
)
PROMPTS_FILE = os.path.join(PROMPTS_DIR, "prompts.json")
PROMPTS_BAK_DIR = os.environ.get("PADAWAN_PROMPTS_BAK") or (
    _pc.bak_dir() if _pc is not None else
    os.path.join(_WEB_PRIVATE, "bak") if _HAS_WEB_PRIVATE else os.path.join(PROMPTS_DIR, "bak")
)
PROMPT_ROLES = ("tous", "chercheur", "capitaine", "contrarian", "compagnon")
PROMPT_ROLE_LABELS = {
    "tous": "Tous", "chercheur": "Chercheur", "capitaine": "Capitaine",
    "contrarian": "Contrarian", "compagnon": "Compagnon",
}
PROMPT_MODES = ("remplacer", "ajouter")
PROMPT_MODE_LABELS = {
    "remplacer": "Remplacer le prompt par défaut",
    "ajouter": "Ajouter au prompt par défaut",
}
PROMPT_VARS = ("{date}", "{question}", "{role}")
PROMPT_TEST_Q = "Présente-toi en 3 phrases : quel style de réponse vas-tu suivre avec ce prompt?"

PROMPT_SEEDS: List[Dict[str, Any]] = [
    {
        "name": "Explique-moi tout (exemple)",
        "role": "tous", "mode": "ajouter", "keep_base": True,
        "text": (
            "MODE « EXPLIQUE-MOI TOUT » : Marc veut comprendre à fond, pas un résumé.\n"
            "Pour {question}, couvre dans l'ordre, en sautant ce qui ne s'applique pas :\n"
            "1. **Réponse directe** en 2-3 phrases.\n"
            "2. **Origine / étymologie** (seulement si le mot ou le nom est éclairant).\n"
            "3. **Histoire** : d'où ça vient, dates clés, personnes clés.\n"
            "4. **Mécanismes** : comment ça marche concrètement, étape par étape, avec un exemple chiffré.\n"
            "5. **Ce que disent les études** : résultats principaux, taille des effets, niveau de preuve "
            "(solide / mitigé / faible). N'invente aucune étude : si tu n'es pas sûr, dis-le.\n"
            "6. **Débats et limites** : ce qui est contesté, les angles morts, les idées reçues.\n"
            "7. **Concrètement pour Marc** : applications, pièges, quoi essayer.\n"
            "8. **Pour aller plus loin** : mots-clés de recherche, livres ou sources sérieuses.\n"
            "Sois long et complet; titres ### et puces. Rôle actif : {role}. Date : {date}."
        ),
    },
    {
        "name": "Résumé express (exemple)",
        "role": "tous", "mode": "remplacer", "keep_base": True,
        "text": (
            "MODE « RÉSUMÉ EXPRESS » : Marc est pressé.\n"
            "- Commence par **En bref** : une phrase qui répond à {question}.\n"
            "- Puis 3 à 5 puces maximum, une idée par puce, chiffres si disponibles.\n"
            "- Termine par **Verdict** en une ligne.\n"
            "- 150 mots maximum au total. Pas d'introduction, pas de conclusion molle."
        ),
    },
    {
        "name": "Avocat du diable (exemple)",
        "role": "tous", "mode": "ajouter", "keep_base": True,
        "text": (
            "MODE « AVOCAT DU DIABLE » : après ta réponse, ajoute une section **Avocat du diable** :\n"
            "- la meilleure version de la position opposée (steelman), sans caricature;\n"
            "- les 3 objections les plus fortes contre ta propre réponse;\n"
            "- les angles morts et les intérêts de ceux qui poussent chaque version;\n"
            "- **Qu'est-ce qui me ferait changer d'avis?** : les faits ou données qui trancheraient."
        ),
    },
    {
        "name": "Prof patient, étape par étape (exemple)",
        "role": "compagnon", "mode": "ajouter", "keep_base": True,
        "text": (
            "MODE « PROF PATIENT » : explique {question} comme un bon prof à un élève curieux.\n"
            "- Pars de ce que Marc connaît déjà; une notion à la fois.\n"
            "- Une analogie de la vie courante pour chaque idée difficile.\n"
            "- Un exemple concret résolu étape par étape.\n"
            "- Termine par un mini-quiz de 3 questions (réponses cachées à la fin, sous **Réponses**)."
        ),
    },
]


def prompt_render(text: str, *, date: str = "", question: str = "", role: str = "") -> str:
    """Remplace {date} {question} {role} sans toucher aux autres accolades."""
    s = str(text or "")
    return (s.replace("{date}", date or "")
             .replace("{question}", question or "ta question")
             .replace("{role}", role or ""))


class PromptStore:
    """Favoris de prompts + prompt actif par rôle (persistant, écriture atomique + .bak)."""

    def __init__(self, path: str = "", bak_dir: str = ""):
        self.path = path or PROMPTS_FILE
        self.bak_dir = bak_dir or PROMPTS_BAK_DIR
        self.error = ""
        self.data: Dict[str, Any] = {"version": 1, "prompts": [], "active": {}, "seeded": False,
                                     "seed_v": 1, "game": ""}
        self.migrated_note = ""
        self.load()

    # ---- fichier
    @staticmethod
    def _new_id() -> str:
        return "p" + uuid.uuid4().hex[:10]

    def _norm_prompt(self, p: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(p, dict):
            return None
        text = str(p.get("text") or "")
        name = str(p.get("name") or "").strip() or "Sans nom"
        role = p.get("role") if p.get("role") in PROMPT_ROLES else "tous"
        mode = p.get("mode") if p.get("mode") in PROMPT_MODES else "remplacer"
        kind = "jeu" if p.get("kind") == "jeu" else "normal"
        if kind == "jeu":
            role = "tous"
        return {
            "id": str(p.get("id") or self._new_id()),
            "name": name[:120],
            "role": role,
            "mode": mode,
            "keep_base": bool(p.get("keep_base", True)),
            "text": text,
            "example": bool(p.get("example", False)),
            "kind": kind,
            "builtin": str(p.get("builtin") or "")[:40],
            "model": str(p.get("model") or "").strip()[:120],  # v39.6: modèle Ollama propre au prompt ("" = courant)
            "created": str(p.get("created") or now()),
            "updated": str(p.get("updated") or now()),
        }

    def load(self) -> None:
        raw = None
        if os.path.isfile(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
            except Exception as e:
                self.error = f"prompts.json illisible ({e}); copie gardée dans bak"
                log(f"prompts load: {e}")
                self.data["seeded"] = True  # ne pas ré-ensemencer par-dessus le fichier de Marc
                try:
                    os.makedirs(self.bak_dir, exist_ok=True)
                    shutil.copy2(self.path, os.path.join(
                        self.bak_dir, f"prompts.json.corrompu-{time.strftime('%Y%m%d-%H%M%S')}.bak"))
                except Exception:
                    pass
        if isinstance(raw, dict):
            prompts = [q for q in (self._norm_prompt(p) for p in (raw.get("prompts") or [])) if q]
            seen, uniq = set(), []
            for q in prompts:
                if q["id"] in seen:
                    q["id"] = self._new_id()
                seen.add(q["id"])
                uniq.append(q)
            act = raw.get("active") if isinstance(raw.get("active"), dict) else {}
            self.data = {
                "version": 1, "prompts": uniq,
                "active": {k: str(v) for k, v in act.items() if k in RoleRouter_ROLE_IDS and v},
                "seeded": bool(raw.get("seeded", True)),
                "seed_v": int(raw.get("seed_v") or 1) if str(raw.get("seed_v") or "1").isdigit() else 1,
                "game": str(raw.get("game") or ""),
            }
        if not self.data.get("seeded"):
            for s in PROMPT_SEEDS:
                q = self._norm_prompt(dict(s, example=True))
                if q:
                    self.data["prompts"].append(q)
            self.data["seeded"] = True
            self.save()
        if int(self.data.get("seed_v") or 1) < 2 and not self.error:
            self._seed_games()
            self.data["seed_v"] = 2
            self.save()
        if int(self.data.get("seed_v") or 1) < 3 and not self.error:
            self._seed_v394()
            self.data["seed_v"] = 3
            self.save()

    def _seed_v394(self) -> None:
        """v39.4 : 📰 favoris 🌍 / 🔭 (après les jeux) + jeux intégrés non modifiés mis à jour (inventaire robuste)."""
        pos = sum(1 for q in self.data["prompts"] if q.get("kind") == "jeu")
        for s in NEWS_SEEDS:
            nid = "n_" + s["builtin"]
            if not self.get(nid):
                q = self._norm_prompt(dict(s, id=nid, example=True))
                if q:
                    self.data["prompts"].insert(pos, q)
                    pos += 1
        new_txt = {s["builtin"]: s["text"] for s in GAME_SEEDS}
        for q in self.data["prompts"]:
            b = q.get("builtin") or ""
            if q.get("kind") == "jeu" and q.get("example") and b in new_txt and q.get("text") != new_txt[b]:
                q["text"] = new_txt[b]

    def _seed_games(self) -> None:
        """v39.3: ajoute les jeux intégrés (sans toucher aux prompts existants)."""
        for s in reversed(GAME_SEEDS):
            gid = "g_" + s["builtin"]
            if not self.get(gid):
                q = self._norm_prompt(dict(s, id=gid, example=True))
                if q:
                    self.data["prompts"].insert(0, q)
        # un ancien prompt « jeu » collé en prompt normal (actif partout) : on le désactive
        # (le prompt reste intact dans la liste) et on bascule sur le vrai Mode Jeu.
        moved = []
        for r, pid in list(self.data["active"].items()):
            p = self.get(pid)
            if p and p.get("kind") != "jeu" and re.search(
                    r"ma[iî]tre du jeu|jeu de r[ôo]le|fallout|QUE FAIS-TU", p.get("name", "") + " " + p.get("text", ""), re.I):
                del self.data["active"][r]
                moved.append(p["name"])
        if moved:
            self.data["game"] = "g_fallout_qc"
            self.migrated_note = (
                f"🎮 Ton prompt « {moved[0]} » était actif comme prompt normal (c'est pour ça que ça « jouait » mal : "
                "les règles du Chercheur et la chasse web passaient devant). Il est gardé intact dans 📜 Prompts; "
                "Padawan lance maintenant le vrai Mode Jeu « 🎮 Fallout — Terres désolées du Québec ».")

    def save(self) -> bool:
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            if os.path.isfile(self.path):
                try:
                    os.makedirs(self.bak_dir, exist_ok=True)
                    shutil.copy2(self.path, os.path.join(self.bak_dir, "prompts.json.bak"))
                    day = os.path.join(self.bak_dir, f"prompts.json.{time.strftime('%Y%m%d')}.bak")
                    if not os.path.isfile(day):
                        shutil.copy2(self.path, day)
                except Exception as e:
                    log(f"prompts bak: {e}")
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except Exception:
                    pass
            os.replace(tmp, self.path)
            self.error = ""
            return True
        except Exception as e:
            self.error = f"Écriture impossible : {e}"
            log(f"prompts save: {e}")
            return False

    # ---- accès
    def all(self) -> List[Dict[str, Any]]:
        return self.data["prompts"]

    def get(self, pid: str) -> Optional[Dict[str, Any]]:
        for p in self.data["prompts"]:
            if p["id"] == pid:
                return p
        return None

    def index_of(self, pid: str) -> int:
        for i, p in enumerate(self.data["prompts"]):
            if p["id"] == pid:
                return i
        return -1

    def for_role(self, role: str) -> List[Dict[str, Any]]:
        return [p for p in self.data["prompts"] if p["role"] in ("tous", role)]

    def active_id(self, role: str) -> str:
        return str(self.data["active"].get(role) or "")

    def active_for(self, role: str) -> Optional[Dict[str, Any]]:
        p = self.get(self.active_id(role))
        if p and p.get("kind") != "jeu" and p["role"] in ("tous", role) and (p.get("text") or "").strip():
            return p
        return None

    def active_roles(self, pid: str) -> List[str]:
        return [r for r, v in self.data["active"].items() if v == pid]

    # ---- modifs
    def upsert(self, p: Dict[str, Any]) -> Dict[str, Any]:
        q = self._norm_prompt(p) or {}
        q["updated"] = now()
        i = self.index_of(q["id"])
        if i >= 0:
            q["created"] = self.data["prompts"][i].get("created") or q["created"]
            self.data["prompts"][i] = q
        else:
            self.data["prompts"].insert(0, q)
        # un prompt devenu spécifique à un rôle ne reste pas actif ailleurs
        for r in list(self.data["active"]):
            if self.data["active"][r] == q["id"] and q["role"] not in ("tous", r):
                del self.data["active"][r]
        return q

    def delete(self, pid: str) -> None:
        self.data["prompts"] = [p for p in self.data["prompts"] if p["id"] != pid]
        for r in list(self.data["active"]):
            if self.data["active"][r] == pid:
                del self.data["active"][r]

    def move(self, pid: str, delta: int) -> bool:
        i = self.index_of(pid)
        j = i + delta
        if i < 0 or not (0 <= j < len(self.data["prompts"])):
            return False
        L = self.data["prompts"]
        L[i], L[j] = L[j], L[i]
        return True

    def move_to(self, pid: str, j: int) -> bool:
        i = self.index_of(pid)
        if i < 0:
            return False
        L = self.data["prompts"]
        j = max(0, min(len(L) - 1, j))
        if i == j:
            return False
        L.insert(j, L.pop(i))
        return True

    def activate(self, pid: str, role: Optional[str] = None) -> List[str]:
        """Active pid pour `role` (ou pour tous les rôles si le prompt est « Tous » et role=None)."""
        p = self.get(pid)
        if not p or p.get("kind") == "jeu":
            return []
        roles = [role] if role else (list(RoleRouter_ROLE_IDS) if p["role"] == "tous" else [p["role"]])
        roles = [r for r in roles if r in RoleRouter_ROLE_IDS and p["role"] in ("tous", r)]
        for r in roles:
            self.data["active"][r] = pid
        return roles

    def reset(self, role: Optional[str] = None) -> None:
        if role:
            self.data["active"].pop(role, None)
        else:
            self.data["active"] = {}


RoleRouter_ROLE_IDS = ("capitaine", "chercheur", "contrarian", "compagnon")


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

    def __init__(self, mem: dict, active: str = "chercheur", prompts: Optional["PromptStore"] = None):
        self.mem = mem
        self.active = active if active in self.ROLES else "chercheur"
        self.prompts = prompts  # v39.2: favoris de prompts (actif par rôle)
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

    @classmethod
    def default_role_text(cls, role_id: str) -> str:
        """Texte propre au rôle (sans SYSTEM_BASE) — sert au 🔒 Défaut dans 📜 Prompts."""
        sp = cls.ROLES[role_id]["system_prompt"]
        return sp[len(SYSTEM_BASE):].strip() if sp.startswith(SYSTEM_BASE) else sp

    def active_prompt(self, role_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        st = getattr(self, "prompts", None)
        if st is None:
            return None
        try:
            return st.active_for(role_id or self.active)
        except Exception:
            return None

    def system_prompt(
        self,
        hunt_query: Optional[str] = None,
        question: Optional[str] = None,
        override: Optional[Dict[str, Any]] = None,
        role_id: Optional[str] = None,
        use_default: bool = False,
    ) -> str:
        """Prompt système final. v39.2: favori actif (Remplacer / Ajouter) ou `override` (🧪 test).
        Toujours: date du jour + garde-fou de chasse du Chercheur."""
        rid = role_id if role_id in self.ROLES else self.active
        role = self.ROLES[rid]
        date = _today_fr()[0]
        core = role["system_prompt"]
        p = None
        if not use_default:
            p = override if override is not None else self.active_prompt(rid)
        if p and p.get("kind") == "jeu" and str(p.get("text") or "").strip():
            # v39.3: prompt de JEU = prompt système pur (pas de règles de rôle, pas de chasse, pas d'outils)
            mine = prompt_render(p.get("text", ""), date=date, question=(question or "").strip()[:500],
                                 role=role["label"]).strip()
            pre = GAME_ADN_LINE.strip() + "\n\n" if p.get("keep_base", True) else ""
            return pre + mine + f"\n\nDate du jour (monde réel) : {date}."
        if p and str(p.get("text") or "").strip():
            mine = prompt_render(
                p.get("text", ""), date=date,
                question=(question or hunt_query or "").strip()[:500], role=role["label"],
            ).strip()
            if p.get("mode") == "ajouter":
                core = core + "\n\n" + mine
            elif p.get("keep_base", True):
                core = SYSTEM_BASE + "\n\n" + mine
            else:
                core = mine
        base = core + f" Date du jour: {date}."
        q = (hunt_query or "").strip()
        if q and rid == "chercheur":
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


# ── v39.3: bibliothèque d'art ASCII (dessiné à la main, ≤ 40 colonnes) ─────────
# Les petits modèles (7-8B) dessinent mal : le maître du jeu choisit un mot-clé
# « SCÈNE: … » et Padawan affiche l'art correspondant.
GAME_ART: Dict[str, Dict[str, str]] = {
"fallout": {
"abri": r"""
      ___________________________
     /  _______________________  \
    |  /    .-----------.      \  |
    | |    /  .-------.  \     |  |
    | |   |  /  1 1 1  \  |    |  |
    | |   |  \  ABRI   /  |    |  |
    | |    \  '-------'  /     |  |
    |  \    '-----------'     /   |
     \___________________________/
   ===== VAULT-TEC · MONT-ROYAL =====""",
"ruines": r"""
        _      ___              _
   ___ | |    |   |  __   _    | |__
  |   || |_   | | | |  | | |_  |  __|
  | | ||   |__| | |_|  |_|   |_| |
  | |_||  _   | |  _    _   _    |
 _|   ||_| |__|_|_| |__| |_| |___|_
 ~~ . ~~ , ~~ . ~~~ , ~~ . ~~ , ~~
   MONTRÉAL · 210 ANS APRÈS LA BOMBE""",
"metro": r"""
   ________________________________
  |  (M)   STATION  BERRI-UQAM  (M) |
  |________________________________|
   ||    __________________    ||
   ||   |  []  []  []  []  |   ||
   ||   |__________________|   ||
  _||__(o)______________(o)____||_
  ~~~~~~~~ ~~~~~~~~~ ~~~~~~~~ ~~~~~
     L'EAU NOIRE MONTE TOUJOURS""",
"goule": r"""
             .-~~~-.
            /  _ _  \
           |  (o)(O) |
           |    ^    |
            \  ===  /
         ___/'-----'\___
        /  /|  STM  |\  \
       /__/ |_______| \__\
            |  | |  |
           _|__| |__|_
        « T'AS-TU TON TITRE ? »""",
"mutant": r"""
            ___________
           /  _     _  \
          |  (@)   (@)  |
          |      ^      |
          |   \_____/   |
       ____\___________/____
      /    |  |  |  |  |    \
     | [=] |  SUPER MUTANT  |  |
     |_____|________________|__|
           |___|     |___|
          GRRRR... PETIT HUMAIN""",
"pillard": r"""
          ,  ,  ,
         /|_/|_/|
        |  x   x |___
        |   __   |   \___
         \_\__/_/    ====>
        __/    \__
       /  |PILLARD| \
      /_/ |  ##  | \_\
          |__||__|
         _/  ||  \_
      « TES CAPS OU TA VIE ! »""",
"radio": r"""
         _____________________
        |  .---------------.  |
        |  | 88  92  98 104|  |
        |  |------^--------|  |
        |  '---------------'  |
        |   (O)  RADIO   (O)  |
        |   ABRI ·· TI-GUY    |
        |_____________________|
          ))  ))  ))  ))  ))
      « ICI TI-GUY LUMIÈRE ! »""",
"marche": r"""
                 /\
                /  \  STADE OLYMPIQUE
               /    \______
          ____/   ___      \_____
         /   /   /   \          \
        |   |   | MAR |  ARMES   |
        |___|___|_CHÉ_|__POUTINE_|
        [##] [$$] [::] [%%] [@@]
       ~ marchands · pillards · rats ~""",
"foret": r"""
          /\        /\     /\
         /  \  /\  /  \   /  \
        / /\ \/  \/ /\ \ / /\ \
       /_/  \_\  /_/  \_\_/  \_\
          ||   /\   ||    ||
          ||  /  \  ||    ||
     ,,,,,||,/____\,||,,,,||,,,,,
        LES LAURENTIDES · RAD 12/H""",
"orignal": r"""
     \\  //             \\  //
      \\//   _______     \\//
       ||___/       \____||
        \   o     o      /
         \      __      /
          \____(oo)____/
             | |    | |
             | |    | |
            /__\    /__\
       ORIGNAL DE LA BOMBE · 3 TONNES""",
"chateau": r"""
              |>>>       |>>>
              |          |
          _  _|_  _    _|_  _
         | |_| |_| |  | |_| |
         |  _   _  |__|  _  |
         | | | | | |  | | | |
     ____|_|_|_|_|_|__|_|_|_|____
    |  CHÂTEAU FRONTENAC · CONFRÉRIE |
    |________________________________|""",
"barrage": r"""
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    |##|##|##|##|##|##|##|##|##|##|
    |  |  |  |  |  |  |  |  |  |  |
    |  |  |  | HYDRO-QUÉBEC |  |  |
    |__|__|__|__|__|__|__|__|__|__|
     \\ \\ \\ \\ \\ \\ \\ \\ \\ \\
      \\ \\ \\ \\ \\ \\ \\ \\ \\
    LA CITÉ DU BARRAGE · BAIE-JAMES""",
"route": r"""
                      .
      _    __        /|\     _
     | |  |  |      / | \   | |
    _|_|__|__|_____/  |  \__|_|_
            \      |  |      /
             \     |  |     /
              \    |  |    /
    ___________\___|__|___/________
      ROUTE 117 · TERRES DÉSOLÉES""",
"campement": r"""
                 (  )
                (    )  )
                 )  (  (
           _______)__)______
          /  /\    ||   /\  \
         /  /  \   ||  /  \  \
        /__/____\__||_/____\__\
            ^^^ /\/\/\ ^^^
           ~~~ (  ) (  ) ~~~
         CAMPEMENT DES COUREURS""",
"nuka": r"""
                 ___
                |___|
                |   |
               /     \
              | NUKA- |
              | COLA  |
              |  ~~~  |
              |  RAD  |
               \_____/
     « LA SOIF APRÈS LA FIN DU MONDE »""",
"robot": r"""
               ___
              |_O_|
            ___|_|___
           |  _____  |
           | | O O | |
           | |_____| |
         __|_________|__
        |__| MISTER  |__|
           |  HANDY  |
          /_/       \_\
       « BONJOUR, MONSIEUR ! »""",
"combat": r"""
        \         .  *   .     /
          \   *  BOUM !  *   /
       .    \   .-''''-.   /    .
          *  ->|  ##  |<-  *
               '-____-'
        --==[  ]-----------[  ]==--
             |   VATS : 74%   |
             |   >> TIRER <<  |
             '----------------'""",
"coffre": r"""
           ________________
          /               /|
         /_______________/ |
        |  ___________  |  |
        | |  $  CAPS  | |  |
        | |___________| |  |
        |      [O]      | /
        |_______________|/
          BUTIN · CRÉDITS · BALLES""",
"pont": r"""
      _/\_       _/\_       _/\_
     /|  |\_____/|  |\_____/|  |\
    / |  |       |  |       |  | \
   /__|__|_______|__|_______|__|__\
   ===================================
     ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
   PONT JACQUES-CARTIER · PÉAGE 10 CAPS""",
},
"polar": {
"bureau": r"""
     _______________________________
    |  DÉTECTIVE PRIVÉ  ·  2e ÉTAGE |
    |   _____          ______       |
    |  | ___ |   ___  |  ||  |      |
    |  ||   || /   \ |  ||  |      |
    |  ||___||  \_/  |__||__|      |
    |  |_____| ____________ (_)    |
    |_________|__WHISKY___|________|
        LE BUREAU AU-DESSUS DU BARBIER""",
"ruelle": r"""
     |  |                    |  |
     |  |   ___         ___  |  |
     |  |  |___|  ( )  |___| |  |
     |  |          |         |  |
     |  |         /|\        |  |
     |  |         / \        |  |
     |__|__ . __ . __ . __ __|__|
       NEIGE SALE · RUELLE DE LA MAIN""",
"jazz": r"""
         * . RED LIGHT . *
      ___________________________
     |   ♪   CLUB  ST-MICHEL  ♪  |
     |___________________________|
        _       _       _
       ( )     ( )     ( )   o
       /|\_    /|\=-   /|\  /|
       / \     / \     / \  / \
     ~~~~ JAZZ · FUMÉE · ENNUIS ~~~~""",
"taverne": r"""
      _____________________________
     |  TAVERNE  ·  HOMMES SEULEMENT |
     |_____________________________|
        _   _   _   _   _   _
       |_| |_| |_| |_| |_| |_|
     =================================
       ( )    ( )    ( )    ( )
       /|\    /|\    /|\    /|\
        BIÈRE · 10 CENNES · RUMEURS""",
"telephone": r"""
              _________
             /  _____  \
            |  / 1 2 3 \ |
            | | 4 5 6 | |
            | | 7 8 9 | |
            |  \__0__/  |
          __|___________|__
         (_________________)
       « ALLÔ ? C'EST POUR VOUS. »""",
"voiture": r"""
              ______________
         ____/ |    |    |  \____
        /  _   |____|____|   _   \
       |__/ \______________/ \___|
          \_/              \_/
      ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
         FORD 1946 · PHARES ÉTEINTS""",
"police": r"""
            _____________
           |  POLICE  ·  |
           |  MONTRÉAL   |
           |_____________|
              .-----.
             | o   o |
             |   ^   |
              \ --- /
            __/'---'\__
         « T'AS RIEN VU, LE PRIVÉ. »""",
"cadavre": r"""
     . . . . . . . . . . . . . . .
     .                           .
     .    ___                    .
     .   (x_x)___________        .
     .     |____________/__      .
     .        ||     \\          .
     . . . . . . . . . . . . . . .
         SCÈNE DE CRIME · NE PAS ENTRER""",
"port": r"""
          |
         -+-        _||_
          |     ___|____|___
     ____/|\___|  CARGO 47  |____
     \_________________________/
      ~~~~~~~~~~~~~~~~~~~~~~~~~~~~
      ~~ ~~~ ~~ ~~~ ~~ ~~~ ~~ ~~~
         LE PORT · QUAI NO 12 · BRUME""",
},
"donjon": {
"connexion": r"""
   ╔══════════════════════════════════╗
   ║                                  ║
   ║  CONNECT 2400 ...                ║
   ║                                  ║
   ║   ____   ___   _  _       _      ║
   ║  |  _ \ / _ \ | \| |   _ | |     ║
   ║  | |_| | |_| || .` |  | || |     ║
   ║  |____/ \___/ |_|\_|   \__/      ║
   ║                                  ║
   ║  SysOp: Ti-Guy · Nœud 1 sur 1    ║
   ╚══════════════════════════════════╝""",
"couloir": r"""
       ##########################
       #........#.......M......#
       #..@.....+.......#......#
       #........#.......#..$...#
       ######+###.......####+###
            #...........#
            #####.#######
                 #  > escalier
       @ = toi   M = monstre   $ = or""",
"monstre": r"""
                 __        __
                /  \______/  \
               |  (O)    (O)  |
                \     /\     /
          /\_____\   /__\   /_____/\
         <  ____  \________/  ____  >
          \/    \__|  ||  |__/    \/
                   |__||__|
         UN DRAGON DE 640 Ko SURGIT !""",
"tresor": r"""
            _____________
           /  *    *    /|
          /_____*______/ |
         | $$$  $$$  $$ |  |
         | $$  DISQUETTE| /
         |   5¼  RARE   |/
         '--------------'
       + 120 OR   + 1 Ko D'XP""",
"porte": r"""
          _____________________
         |  _________________  |
         | |       ___       | |
         | |      |   |      | |
         | |      | o |      | |
         | |      |___|      | |
         | |_________________| |
         |_____________________|
       C:\DONJON> OUVRIR PORTE.EXE""",
"squelette": r"""
               .---.
              / x x \
              \  ^  /
               |===|
            .--'---'--.
           /|  |   |  |\
            |  |   |  |
            '--+---+--'
              |     |
             _|     |_
          SQUELETTE NIV 3 · 12 PV""",
"escalier": r"""
        ____
       |    |____
       |         |____
       |              |____
       |                   |____
       |  NIVEAU SUIVANT  >     |
       |________________________|
         C:\DONJON\NIVEAU2> _""",
"taverne": r"""
       _____________________________
      | AUBERGE DU MODEM QUI SIFFLE |
      |_____________________________|
        _[]_      ( )      _[]_
       |____|     /|\     |____|
      ===========================
        HP +10 · POTION 5 OR · RUMEURS""",
},
}

GAME_ART_FAMILY = {"fallout_qc": "fallout", "polar_1947": "polar", "donjon_bbs": "donjon"}

# Mots-clés de secours quand le modèle n'écrit pas de « SCÈNE: » valide
GAME_ART_HINTS: Dict[str, Dict[str, Tuple[str, ...]]] = {
"fallout": {
    "abri": ("abri", "vault", "porte de l'abri"), "metro": ("métro", "metro", "station", "quai", "tunnel"),
    "goule": ("goule",), "mutant": ("mutant",), "pillard": ("pillard", "raider"),
    "radio": ("radio", "ti-guy"), "marche": ("stade", "marché", "marchand"),
    "foret": ("forêt", "laurentide", "bois"), "orignal": ("orignal",),
    "chateau": ("château", "frontenac", "confrérie", "québec"), "barrage": ("barrage", "hydro", "baie-james"),
    "campement": ("campement", "feu de camp", "coureur"), "nuka": ("nuka",), "robot": ("robot", "handy", "protectron"),
    "combat": ("combat", "attaque", "tire", "vats"), "coffre": ("coffre", "butin", "caisse"),
    "pont": ("pont",), "route": ("route", "désert", "autoroute", "surface"), "ruines": ("ruine", "ville", "montréal"),
},
"polar": {
    "bureau": ("bureau",), "ruelle": ("ruelle",), "jazz": ("jazz", "club", "cabaret"), "taverne": ("taverne", "bar"),
    "telephone": ("téléphone", "appel"), "voiture": ("voiture", "auto", "ford"), "police": ("police", "flic", "poste"),
    "cadavre": ("cadavre", "corps", "mort", "crime"), "port": ("port", "quai", "cargo"),
},
"donjon": {
    "connexion": ("connexion", "bbs", "modem"), "monstre": ("dragon", "monstre", "troll", "orc"),
    "squelette": ("squelette", "zombie", "mort-vivant"), "tresor": ("trésor", "coffre", "or "),
    "porte": ("porte",), "escalier": ("escalier", "niveau"), "taverne": ("auberge", "taverne"),
    "couloir": ("couloir", "salle", "carte"),
},
}


def game_art_for(builtin: str, key: str = "", hint_text: str = "") -> Tuple[str, str]:
    """(clé, art) pour un jeu intégré, d'après le mot-clé « SCÈNE: » ou le texte. ("", "") si rien."""
    fam = GAME_ART_FAMILY.get(builtin or "")
    if not fam:
        return "", ""
    lib = GAME_ART.get(fam, {})
    k = _art_norm(key)
    if k in lib:
        return k, lib[k].strip("\n")
    k = _ART_ALIAS.get(k, k)
    if k in lib:
        return k, lib[k].strip("\n")
    for kk in lib:
        if len(k) >= 4 and (kk in k or k in kk or kk[:4] == k[:4]):
            return kk, lib[kk].strip("\n")
    low = (key + " " + (hint_text or "")).lower()
    for kk, words in GAME_ART_HINTS.get(fam, {}).items():
        if any(w in low for w in words):
            return kk, lib[kk].strip("\n")
    return "", ""


_ART_ALIAS = {"vault": "abri", "ruins": "ruines", "ruin": "ruines", "ville": "ruines", "city": "ruines",
              "subway": "metro", "ghoul": "goule", "raider": "pillard", "market": "marche", "stade": "marche",
              "forest": "foret", "bois": "foret", "moose": "orignal", "castle": "chateau", "dam": "barrage",
              "road": "route", "desert": "route", "camp": "campement", "fight": "combat", "chest": "coffre",
              "butin": "coffre", "bridge": "pont", "office": "bureau", "alley": "ruelle", "club": "jazz",
              "bar": "taverne", "phone": "telephone", "car": "voiture", "auto": "voiture", "corps": "cadavre",
              "quai": "port", "dragon": "monstre", "skeleton": "squelette", "treasure": "tresor",
              "door": "porte", "stairs": "escalier", "salle": "couloir", "auberge": "taverne", "bbs": "connexion",
              "lac": "barrage", "riviere": "barrage", "cabane": "foret", "sucre": "foret", "erabliere": "foret",
              "entree": "porte", "interrogatoire": "police", "chest_dj": "tresor"}


def _art_norm(s: str) -> str:
    s = (s or "").strip().lower()
    for a, b in (("é", "e"), ("è", "e"), ("ê", "e"), ("â", "a"), ("ç", "c"), ("ô", "o"), ("û", "u"), ("î", "i")):
        s = s.replace(a, b)
    return re.sub(r"[^a-z]", "", s)
# ── v39.3: 🎮 Mode Jeu (prompts de type « jeu ») ────────────────────────────────
GAME_PARTIES_DIR = os.path.join(PROMPTS_DIR, "parties")
GAME_ADN_LINE = (
    "Tu tutoies le joueur (un Québécois) et tu écris en français québécois naturel, avec un humour noir sec. "
    "La narration dit toujours « tu » : jamais le prénom du joueur à la 3e personne. "
)
FENCE = "`" * 3

_SCENE_EXTRA = {"fallout": ("lac", "cabane"), "donjon": ("coffre",), "polar": ()}  # v40.2 : scènes illustrées


def _scene_words(fam: str) -> str:
    keys = list(GAME_ART.get(fam, {}).keys())
    keys += [k for k in _SCENE_EXTRA.get(fam, ()) if k not in keys]
    return ", ".join(keys)


# ── v40.2 : 🖼 illustrations ANSI originales (banque padawan_jeux_images.json.gz, à côté de padawan39.py) ──
# Images originales (style rétro, aucune image de franchise) converties par padawan_ansi : Pip-Boy vert (Fallout),
# 16 couleurs DOS (Donjon), film noir gris + accents (Polar). Le choix de l'image : mot-clé SCÈNE:, titre,
# LIEU du Pip-Boy et mots de la narration (FR + un peu d'anglais). Pas de répétition tant que la scène ne change pas.
GAME_IMG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "padawan_jeux_images.json.gz")
GAME_IMG_ALIAS: Dict[str, Dict[str, str]] = {
    "fallout": {"vault": "abri", "bunker": "abri", "pillard": "combat", "raider": "combat", "fight": "combat",
                "radio": "ruines", "chateau": "ruines", "ville": "ruines", "city": "ruines", "ruins": "ruines",
                "ruin": "ruines", "orignal": "foret", "moose": "foret", "forest": "foret", "bois": "foret",
                "barrage": "lac", "dam": "lac", "pont": "lac", "bridge": "lac", "riviere": "lac", "river": "lac",
                "lake": "lac", "fleuve": "lac", "nuka": "marche", "market": "marche", "stade": "marche",
                "marchand": "marche", "caravane": "marche", "camp": "campement", "feu": "campement",
                "subway": "metro", "tunnel": "metro", "cave": "metro", "egout": "metro", "ghoul": "goule",
                "road": "route", "desert": "route", "autoroute": "route", "sucre": "cabane", "erabliere": "cabane",
                "coffre": "", "butin": "", "chest": ""},
    "polar": {"taverne": "jazz", "bar": "jazz", "club": "jazz", "cabaret": "jazz", "telephone": "bureau",
              "phone": "bureau", "office": "bureau", "alley": "ruelle", "car": "voiture", "auto": "voiture",
              "corps": "cadavre", "crime": "cadavre", "quai": "port", "docks": "port",
              "interrogatoire": "police", "poste": "police"},
    "donjon": {"connexion": "titre", "bbs": "titre", "modem": "titre", "entree": "porte", "door": "porte",
               "salle": "couloir", "dragon": "monstre", "skeleton": "squelette", "treasure": "tresor",
               "chest": "coffre", "stairs": "escalier", "auberge": "taverne"},
}
# (clé, motif) — appliqués sur un texte en minuscules SANS accents
GAME_IMG_RULES: Dict[str, Tuple[Tuple[str, str], ...]] = {
    "fallout": (
        ("abri", r"\babri\b|\bvault|porte (blindee|de l.abri|d.acier)|bunker|refuge souterrain"),
        ("cabane", r"cabane a sucre|erabl|sirop|tire sur la neige|sucrerie|maple"),
        ("goule", r"\bgoules?\b|ghoul|zombie|chair (pourrie|decomposee)"),
        ("mutant", r"super.?mutant|\bmutants?\b|\bbrutes?\b|colosse"),
        ("robot", r"\brobots?\b|androide|\bdroide|protectron|tourelle|automate"),
        ("marche", r"marchand|caravane|commer[cs]|\btroc|\bvend(eur|euse|re|s|u)?\b|boutique|\bmarche\b|trader|merchant"),
        ("campement", r"campement|feu de camp|bivouac|\bcamp\b|\btentes?\b|autour du feu"),
        ("metro", r"\bmetro|tunnel|egout|souterrain|\bcaves?\b|grotte|caverne|\bstation\b|subway|sewer"),
        ("combat", r"\bcombat|attaqu|\btir(e|es|ent|ez)?\b|coup de feu|degats|\bfrapp|esquiv|\bvats\b|"
                   r"ennemi|pillard|raider|ripost|\bballes?\b|\bfight|shoot|\bpv -|initiative"),
        ("lac", r"\blacs?\b|riviere|fleuve|saint-laurent|\brive\b|berge|canot|barrage|\bpont\b|lake|river"),
        ("foret", r"\bforet|\bbois\b|\barbres?\b|epinette|\bsapins?\b|laurentide|forest|\btrees?\b|orignal|moose"),
        ("ruines", r"\bruine|decombre|immeuble|centre-ville|downtown|gratte-ciel|eglise|clocher|\brue\b|"
                   r"sherbrooke|montreal|\bquebec\b|\bville\b|\bcity\b|ruins|quartier"),
        ("route", r"\broute|autoroute|desert|\bplaine|\bchemin\b|highway|\broad\b|wasteland|terres desolees|poussiere|"
                  r"\bdehors\b|exterieur|\bsurface\b|\bnature\b|horizon|\bsoleil\b"),
    ),
    "polar": (
        ("cadavre", r"cadavre|\bcorps\b|victime|meurtr|scene (du|de) crime|assassin|\bmorte?\b|body|murder"),
        ("police", r"\bpolice|\bflics?\b|poste de|interrogatoire|inspecteur|sergent|cellule|\bsuspect|\bcops?\b"),
        ("jazz", r"\bjazz|\bclub\b|cabaret|\bbar\b|taverne|chanteuse|saxo|barman|comptoir|nightclub"),
        ("voiture", r"voiture|\bauto\b|automobile|\bford\b|chevrolet|berline|\bphares\b|\bvolant\b|\btaxi|filature"),
        ("port", r"\bport\b|\bquais?\b|\bdocks?\b|cargo|navire|bateau|entrepot|\bsilos?\b|harbou?r"),
        ("bureau", r"\bbureau|agence|dossier|machine a ecrire|telephone|\bclient|\boffice\b|store venitien"),
        ("ruelle", r"ruelle|\bpluie|averse|trottoir|\brue\b|alley|\brain\b|lampadaire|escalier de secours"),
    ),
    "donjon": (
        ("monstre", r"dragon|monstre|\btrolls?\b|\borcs?\b|\bogres?\b|gobelin|araignee|\bbete|wyrm|monster|goblin"),
        ("squelette", r"squelette|mort.vivant|zombie|crypte|\btombe|ossement|liche|skeleton|undead|crypt"),
        ("tresor", r"tresor|pieces? d.or|\bor\b|gemme|joyau|couronne|treasure|\bgold\b|\bloot"),
        ("coffre", r"\bcoffre|serrure|cadenas|crochet|\bchest\b|\block"),
        ("taverne", r"taverne|auberge|aubergiste|biere|hydromel|tavern|\binn\b"),
        ("escalier", r"escalier|\bdescend|niveau inferieur|\bstairs"),
        ("porte", r"\bentree|\bportes?\b|portail|\bgrille|\bseuil|entrance|\bgate|\bdoor"),
        ("couloir", r"couloir|corridor|galerie|passage|\bsalle|labyrinthe|\bhall\b"),
    ),
}
# scènes « fortes » (créature, lieu très typé) : un seul mot de la narration suffit
GAME_IMG_STRONG = {"abri", "cabane", "goule", "mutant", "robot", "marche", "monstre", "squelette", "tresor", "coffre",
                   "taverne", "cadavre", "jazz", "police", "port"}
_IMG_RX: Dict[str, List[Tuple[str, Any]]] = {}


def _img_fold(t: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", (t or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c)).replace("’", "'")


def game_img_bank() -> Optional[Dict[str, Any]]:
    """La banque d'images (None si padawan_ansi ou le fichier manque)."""
    if _ANSI is None or not os.path.isfile(GAME_IMG_FILE):
        return None
    try:
        b = _ANSI.load_bank(GAME_IMG_FILE)
    except Exception as e:  # pragma: no cover
        log(f"game_img_bank: {e}")
        return None
    return b if b.get("games") else None


def game_img_family(builtin: str) -> str:
    fam = GAME_ART_FAMILY.get(builtin or "", "")
    b = game_img_bank()
    return fam if (b and fam in b["games"]) else ""


def game_img_pick(builtin: str, scene: str = "", title: str = "", text: str = "", lieu: str = "", prev: str = "") -> str:
    """Clé d'image pour une réponse du MJ ("" si rien de clair). Poids : SCÈNE: 6, titre 3, LIEU 3, narration 1-2.
    Les petits modèles répètent souvent le même mot SCÈNE: : s'il est identique à l'image précédente (prev),
    il ne pèse plus que 2 et la narration peut l'emporter."""
    fam = game_img_family(builtin)
    if not fam:
        return ""
    scenes = game_img_bank()["games"][fam].get("scenes", {})
    score: Dict[str, float] = {}
    k = _art_norm(scene)
    if k:
        k2 = k if k in scenes else GAME_IMG_ALIAS.get(fam, {}).get(k, "")
        if not k2 and len(k) >= 4:
            k2 = next((kk for kk in scenes if kk != "titre" and (kk in k or k in kk or kk[:4] == k[:4])), "")
        if k2 in scenes and k2 != "titre":
            score[k2] = 2.0 if (prev and k2 == prev) else 6.0
    rx = _IMG_RX.get(fam)
    if rx is None:
        rx = _IMG_RX[fam] = [(kk, re.compile(p)) for kk, p in GAME_IMG_RULES.get(fam, ()) if kk in scenes]
    body = _img_fold(re.sub(r"(?m)^\s*\d+\s*[.)].*$", " ", text or "")[:1400])  # sans les choix proposés
    t_title, t_lieu = _img_fold(title), _img_fold(lieu)
    for kk, r in rx:
        sc = (3.0 * len(r.findall(t_title)) + 3.0 * min(2, len(r.findall(t_lieu)))
              + (2.0 if kk in GAME_IMG_STRONG else 1.0) * min(4, len(r.findall(body))))
        if sc:
            score[kk] = score.get(kk, 0.0) + sc
    if not score:
        return ""
    best = max(score.items(), key=lambda kv: kv[1])
    return best[0] if best[1] >= 2 else ""


def game_img_plan(st: Dict[str, Any], cache: Optional[Dict[Any, str]] = None) -> Dict[int, str]:
    """{index du journal: clé d'image} — l'image change seulement quand la scène change (ou un nouveau LIEU
    après quelques tours). -1 = image-titre en tête quand la partie n'a pas d'écran d'intro."""
    bi = st.get("builtin", "")
    fam = game_img_family(bi)
    if not fam:
        return {}
    g = game_img_bank()["games"][fam]
    scenes, fb = g.get("scenes", {}), g.get("fallback", "")
    plan: Dict[int, str] = {}
    log_ = st.get("log") or []
    last, last_lieu, since = "", "", 0
    if not any(e.get("who") == "intro" for e in log_) and "titre" in scenes:
        plan[-1] = last = "titre"
    for i, e in enumerate(log_):
        who, text = e.get("who"), e.get("text", "") or ""
        if who == "intro":
            if "titre" in scenes:
                plan[i] = last = "titre"
            continue
        if who != "mj":
            continue
        ck = (bi, text, e.get("status", ""), last)
        k = cache.get(ck) if cache is not None else None
        lieu = ""
        try:
            lieu = game_fields(e.get("status", "") or text).get("LIEU", "") or game_fields(text).get("LIEU", "")
        except Exception:
            pass
        if k is None:
            gp = game_parse(text)
            k = game_img_pick(bi, gp.get("scene", ""), gp.get("title", ""), text, lieu, prev=last)
            if cache is not None:
                if len(cache) > 600:
                    cache.clear()
                cache[ck] = k
        since += 1
        if not k and last in ("", "titre") and fb in scenes:
            k = fb
        ln = _art_norm(lieu)[:40]
        if k and (k != last or (ln and last_lieu and ln != last_lieu and since >= 3)):
            plan[i], last, since = k, k, 0
        if ln:
            last_lieu = ln
    return plan


GAME_FALLOUT_TEXT = "\n".join([
    "Tu es le MAÎTRE DU JEU de « FALLOUT : TERRES DÉSOLÉES DU QUÉBEC », un jeu de rôle textuel post-apocalyptique.",
    "Ton : 100 % Fallout — cynisme rétro-futuriste Vault-Tec, humour noir québécois, pubs pré-guerre absurdes.",
    "",
    "UNIVERS",
    "- An 2287, 210 ans après la Grande Guerre. Le Québec est une Terre désolée.",
    "- Départ : l'Abri 111, creusé sous le Mont-Royal (la croix du Mont-Royal clignote encore, radioactive).",
    "- Lieux : Montréal en ruines (le Stade olympique est un marché de pillards, le métro inondé grouille de goules), "
    "Sherbrooke irradiée, la Cité du Barrage à la Baie-James, Québec fortifiée derrière ses murs, "
    "les Laurentides et leurs orignaux de la Bombe.",
    "- Factions : l'Enclave d'Hydro-Québec (contrôle l'électricité, arrogante), la Confrérie de l'Acier du Château Frontenac, "
    "les Coureurs des bois (caravaniers libres), les Pillards du pont Jacques-Cartier, les Goules du Vieux-Port, "
    "les Super Mutants de la Côte-Nord.",
    "- Culture pré-guerre : Nuka-Cola, poutine en canne « Poutine-O-Matic », sirop d'érable irradié, "
    "Radio Abri avec l'animateur Ti-Guy Lumière, Pip-Boy 3000, capsules (CAPS) comme monnaie.",
    "",
    "RÈGLES",
    "0. TUTOIE le joueur : « tu », « ton », « toi » — jamais « vous ».",
    "1. Tu restes TOUJOURS le maître du jeu : aucun méta-commentaire, aucune URL, jamais « en tant qu'IA ».",
    "2. L'histoire suit les choix du joueur, de façon cohérente et continue, avec de vraies conséquences "
    "(blessures, alliés, ennemis, butin). Tu ne reviens jamais en arrière.",
    "3. État cohérent d'un tour à l'autre : HP, RAD, CAPS, FAIM, SOIF, inventaire, lieu, quête. "
    "Un chiffre ne change que pour une raison racontée. Il y a toujours une QUÊTE précise. "
    "Le bloc ▓▓ est COMPLET à CHAQUE réponse, avec l'INVENTAIRE ENTIER et les quantités (ex. « 2 Stimpaks »).",
    "3b. Quand le joueur gagne, perd ou utilise un objet, écris-le clairement dans la narration "
    "(« Tu obtiens une clé rouillée. », « Tu utilises un Stimpak. ») ET mets l'INVENTAIRE à jour. "
    "Les dégâts et les gains s'écrivent en chiffres (« tu perds 8 HP », « +15 RAD », « tu trouves 12 capsules »). "
    "La faim et la soif montent avec le temps; manger ou boire les fait baisser.",
    "4. Tests de compétence : le message du joueur contient [JET d20 = N]. Utilise ce N : 1-5 échec grave, "
    "6-10 échec, 11-15 réussite, 16-19 belle réussite, 20 critique. Écris le test ainsi : "
    "[Perception 6 · d20 14 → réussi].",
    "5. Narration de 120 à 220 mots, au présent et à la 2e personne (« Tu avances… », jamais « Marc avance » "
    "ni le nom du personnage hors des dialogues), "
    "avec au moins un dialogue de PNJ entre « guillemets ».",
    "6. UNE SEULE scène par réponse : tu t'arrêtes juste après le dernier choix et tu attends le joueur.",
    "7. Ne dessine PAS d'art ASCII : écris seulement la ligne SCÈNE: avec UN mot de cette liste, "
    "Padawan affiche l'image : " + _scene_words("fallout") + ".",
    "",
    "FORMAT OBLIGATOIRE DE CHAQUE RÉPONSE (dans cet ordre, rien d'autre) :",
    "## Titre de la scène",
    "SCÈNE: (un mot de la liste)",
    "Narration et dialogues.",
    FENCE,
    "▓▓ PIP-BOY 3000 ▓▓",
    "NOM: (nom) | NIV: 1",
    "HP: 100/100 | RAD: 0 | CAPS: 25",
    "FAIM: 0/100 | SOIF: 0/100",
    "SPECIAL: F5 P5 E5 C5 I5 A5 L5",
    "LIEU: (lieu)",
    "QUÊTE: (quête active)",
    "INVENTAIRE: (objet), (objet), (objet)",
    FENCE,
    "QUE FAIS-TU ?",
    "1. (choix)",
    "2. (choix)",
    "3. (choix)",
    "4. (choix)",
    "",
    "Mets 3 à 5 choix : des ACTIONS courtes (12 mots max), sans jet de dé ni résultat. Rien après le dernier choix.",
    "",
    "DÉMARRAGE : le premier message du joueur donne son personnage (nom, archétype, SPECIAL, inventaire). "
    "Reprends-les EXACTEMENT dans le Pip-Boy, donne-lui une QUÊTE de départ, puis lance la première scène : "
    "le matin où la porte de l'Abri 111 s'ouvre pour la première fois, annoncé par Ti-Guy Lumière à Radio Abri.",
])

GAME_POLAR_TEXT = "\n".join([
    "Tu es le NARRATEUR d'un polar noir interactif : « MONTRÉAL 1947 — LA NUIT DU RED LIGHT ».",
    "Ambiance : Montréal d'après-guerre sous Duplessis, boîtes de jazz de la rue Saint-Antoine, Red Light, "
    "tavernes, police corrompue, pègre, fumée de cigarette, neige sale. Humour pince-sans-rire québécois, "
    "dialogues en joual d'époque (sans exagérer).",
    "Le joueur incarne un détective privé fauché, bureau au-dessus d'un barbier sur la Main.",
    "",
    "RÈGLES",
    "0. Tutoie le joueur dans la narration (« tu »).",
    "1. Tu restes TOUJOURS le narrateur : aucun méta-commentaire, aucune URL.",
    "2. Une vraie enquête : indices, fausses pistes, suspects avec des motifs, conséquences. Garde la solution cohérente.",
    "3. État cohérent d'un tour à l'autre : SANTÉ, NERFS, PIASTRES, indices, lieu, piste.",
    "4. Le message du joueur contient [JET d20 = N] : 1-5 échec grave, 6-10 échec, 11-15 réussite, 16-20 belle réussite. "
    "Écris : [Flair · d20 15 → réussi].",
    "5. Narration de 120 à 220 mots, au présent, à la 2e personne (« tu »). UNE SEULE scène par réponse.",
    "6. Ne dessine PAS d'art ASCII : écris seulement la ligne SCÈNE: avec UN mot de cette liste : "
    + _scene_words("polar") + ".",
    "",
    "FORMAT OBLIGATOIRE DE CHAQUE RÉPONSE (rien d'autre) :",
    "## Titre de la scène",
    "SCÈNE: (un mot de la liste)",
    "Narration et dialogues.",
    FENCE,
    "▓▓ CARNET DU DÉTECTIVE ▓▓",
    "NOM: (nom)",
    "SANTÉ: 100/100 | NERFS: 80/100 | PIASTRES: 12",
    "LIEU: (lieu)",
    "PISTE: (piste principale)",
    "INDICES: (indice), (indice)",
    FENCE,
    "QUE FAIS-TU ?",
    "1. (choix)",
    "2. (choix)",
    "3. (choix)",
    "",
    "Mets 3 à 5 choix numérotés (actions courtes, sans dé), un par ligne, rien après le dernier.",
    "DÉMARRAGE : le premier message du joueur donne son détective. Lance l'affaire : une cliente mystérieuse "
    "entre dans le bureau un soir de tempête de neige.",
])

GAME_DONJON_TEXT = "\n".join([
    "Tu es le SYSOP-MAÎTRE DU JEU d'un « door game » de BBS de 1991 : « LE DONJON DU 2400 BAUDS ».",
    "Ambiance : jeu d'aventure rétro DOS, écran 80 colonnes, humour geek québécois "
    "(modem qui siffle, disquettes 5¼, AUTOEXEC.BAT, « Tu as reçu 1 Ko de XP »).",
    "Le joueur explore un donjon de 5 niveaux sous le serveur du BBS, avec monstres, trésors, énigmes.",
    "",
    "RÈGLES",
    "0. Tutoie le joueur (« tu »).",
    "1. Tu restes TOUJOURS le maître du jeu : aucun méta-commentaire, aucune URL.",
    "2. Conséquences réelles, butin, combats au tour par tour. État cohérent : PV, MANA, OR, niveau, salle, objets.",
    "3. Le message du joueur contient [JET d20 = N] : 1-5 échec grave, 6-10 échec, 11-15 réussite, 16-20 coup critique. "
    "Écris : [Attaque · d20 17 → touché, 6 dégâts].",
    "4. Narration de 100 à 200 mots, style rétro, phrases courtes, à la 2e personne. UNE SEULE scène par réponse.",
    "5. Ne dessine PAS d'art ASCII : écris seulement la ligne SCÈNE: avec UN mot de cette liste : "
    + _scene_words("donjon") + ".",
    "",
    "FORMAT OBLIGATOIRE DE CHAQUE RÉPONSE (rien d'autre) :",
    "## NIVEAU x — Nom de la salle",
    "SCÈNE: (un mot de la liste)",
    "Narration.",
    FENCE,
    "▓▓ FICHE DU HÉROS ▓▓",
    "NOM: (nom) | CLASSE: (classe) | NIV: 1",
    "PV: 20/20 | MANA: 10/10 | OR: 0",
    "SALLE: (salle)",
    "QUÊTE: (objectif)",
    "INVENTAIRE: (objet), (objet)",
    FENCE,
    "QUE FAIS-TU ?",
    "1. (choix)",
    "2. (choix)",
    "3. (choix)",
    "",
    "Mets 3 à 5 choix numérotés (actions courtes, sans dé), un par ligne, rien après le dernier.",
    "DÉMARRAGE : le premier message du joueur donne son héros. Lance la partie au NIVEAU 1, à l'entrée du donjon.",
])

# Création du personnage faite par Padawan (fiable, même avec un petit modèle)
GAME_META: Dict[str, Dict[str, Any]] = {
    "fallout_qc": {
        "title": "FALLOUT — TERRES DÉSOLÉES DU QUÉBEC", "art": "abri",
        "intro": ("23 octobre 2287, 6 h 00. Les haut-parleurs de l'Abri 111 grésillent :\n"
                  "« Bon matin, les résidents ! Ici Ti-Guy Lumière, sur Radio Abri. Aujourd'hui, c'est LE grand jour : "
                  "après 210 ans, la porte s'ouvre. Il fait -12 dehors, 400 rads, pis y'a des orignaux. Bonne chance ! »\n\n"
                  "Le Pip-Boy à ton poignet clignote : CRÉATION DU PERSONNAGE."),
        "ask": "Qui es-tu ?",
        "archetypes": [
            {"label": "Le Résident de l'Abri", "desc": "intelligent, débrouillard, jamais vu le soleil",
             "special": "F4 P6 E5 C6 I8 A5 L6", "inv": "pistolet 10 mm, 2 Stimpaks, poutine en canne", "name": "Marc"},
            {"label": "La Coureuse des bois", "desc": "rapide, l'œil vif, connaît chaque sentier",
             "special": "F5 P7 E6 C4 I5 A8 L5", "inv": "carabine de chasse, couteau, sirop d'érable irradié", "name": "Mélanie"},
            {"label": "Le Mécano de la Baie-James", "desc": "costaud, répare tout avec du tape gris",
             "special": "F6 P5 E7 C4 I8 A4 L6", "inv": "clé à molette lourde, tape gris, Nuka-Cola tiède", "name": "Réjean"},
        ],
        "custom": "Créer mon propre personnage (nom + 40 points SPECIAL)",
        "start": "Commence la partie. Mon personnage : {name}, {label}. SPECIAL: {special}. Inventaire : {inv}. "
                 "HP 100/100, RAD 0, CAPS 25.",
        "status0": "▓▓ PIP-BOY 3000 ▓▓\nNOM: {name} | NIV: 1\nHP: 100/100 | RAD: 0 | CAPS: 25\n"
                   "FAIM: 0/100 | SOIF: 0/100\nSPECIAL: {special}\nLIEU: Abri 111\nINVENTAIRE: {inv}",
    },
    "polar_1947": {
        "title": "MONTRÉAL 1947 — LA NUIT DU RED LIGHT", "art": "bureau",
        "intro": ("Décembre 1947. La neige tombe sur la Main. Ton bureau sent le tabac froid et le whisky de contrebande. "
                  "Le loyer est dû depuis deux mois et le téléphone ne sonne plus.\n\nQui es-tu ?"),
        "ask": "Ton détective :",
        "archetypes": [
            {"label": "L'ex-flic écœuré", "desc": "connaît la police par cœur — et ses secrets",
             "special": "FLAIR 6 · POING 7 · BAGOU 4", "inv": "revolver .38, flasque, insigne périmé", "name": "Gérard Lacasse"},
            {"label": "La journaliste du Devoir", "desc": "curieuse, culottée, un carnet plein de noms",
             "special": "FLAIR 7 · POING 3 · BAGOU 7", "inv": "carnet, appareil photo, laissez-passer de presse", "name": "Simone Beaulieu"},
            {"label": "Le joueur de cartes du Red Light", "desc": "charmant, endetté, connaît tout le monde",
             "special": "FLAIR 5 · POING 4 · BAGOU 8", "inv": "jeu de cartes truqué, 12 piastres, briquet en or", "name": "Ti-Mé Desrosiers"},
        ],
        "custom": "Créer mon propre détective",
        "start": "Commence la partie. Mon détective : {name}, {label} ({special}). Sur moi : {inv}. "
                 "SANTÉ 100/100, NERFS 80/100, PIASTRES 12.",
        "status0": "▓▓ CARNET DU DÉTECTIVE ▓▓\nNOM: {name}\nSANTÉ: 100/100 | NERFS: 80/100 | PIASTRES: 12\n"
                   "LIEU: Bureau sur la Main\nINDICES: {inv}",
    },
    "donjon_bbs": {
        "title": "LE DONJON DU 2400 BAUDS", "art": "connexion",
        "intro": ("ATDT 555-2400... iiiiiiiiih-krrrrr-shhhhhh. CONNECT 2400.\n"
                  "« Bienvenue sur LE DONJON BBS. Tu es l'appelant #1337. Temps restant : 60 minutes. »\n\n"
                  "CHOISIS TA CLASSE :"),
        "ask": "Ta classe :",
        "archetypes": [
            {"label": "Guerrier du DOS", "desc": "frappe fort, lit les fichiers .BAT comme des parchemins",
             "special": "FOR 8 · INT 3 · DEX 5", "inv": "épée COMMAND.COM, bouclier de disquettes", "name": "Bozo"},
            {"label": "Mage du Turbo Pascal", "desc": "sorts compilés, peu de PV",
             "special": "FOR 3 · INT 9 · DEX 4", "inv": "bâton de RAM, grimoire BEGIN..END", "name": "Merlinux"},
            {"label": "Voleur de shareware", "desc": "furtif, ouvre toutes les serrures (après 30 jours)",
             "special": "FOR 4 · INT 5 · DEX 9", "inv": "dague, crochets, clé d'enregistrement volée", "name": "Ti-Pirate"},
        ],
        "custom": "Créer mon propre héros",
        "start": "Commence la partie. Mon héros : {name}, {label} ({special}). Inventaire : {inv}. "
                 "PV 20/20, MANA 10/10, OR 0.",
        "status0": "▓▓ FICHE DU HÉROS ▓▓\nNOM: {name} | CLASSE: {label} | NIV: 1\nPV: 20/20 | MANA: 10/10 | OR: 0\n"
                   "SALLE: Entrée du donjon\nINVENTAIRE: {inv}",
    },
}

GAME_SEEDS: List[Dict[str, Any]] = [
    {"name": "🎮 Fallout — Terres désolées du Québec", "role": "tous", "mode": "remplacer", "kind": "jeu",
     "keep_base": True, "text": GAME_FALLOUT_TEXT, "builtin": "fallout_qc"},
    {"name": "🕵️ Polar — Montréal 1947", "role": "tous", "mode": "remplacer", "kind": "jeu",
     "keep_base": True, "text": GAME_POLAR_TEXT, "builtin": "polar_1947"},
    {"name": "🧙 Donjon du BBS 2400 bauds (rétro DOS)", "role": "tous", "mode": "remplacer", "kind": "jeu",
     "keep_base": True, "text": GAME_DONJON_TEXT, "builtin": "donjon_bbs"},
]

GAME_TURN_REMINDER = (
    "\n\n(Rappel : tutoie-moi. Format : ## titre, NOUVEL art ASCII dans un bloc " + FENCE + ", narration, "
    "statut dans un bloc " + FENCE + " qui commence par ▓▓, puis « QUE FAIS-TU ? » et 3 à 5 choix numérotés "
    "« 1. », « 2. »… (actions courtes, sans dé). Rien après le dernier choix.)"
)


def game_reminder(builtin: str = "") -> str:
    fam = GAME_ART_FAMILY.get(builtin or "")
    if not fam:
        return GAME_TURN_REMINDER
    return ("\n\n(Rappel : tutoie-moi. Format : ## titre, puis la ligne SCÈNE: avec un mot parmi "
            + _scene_words(fam) + " (pas d'art ASCII), narration avec un dialogue, statut dans un bloc " + FENCE
            + " qui commence par ▓▓ et contient TOUTES les lignes (INVENTAIRE complet à jour), puis « QUE FAIS-TU ? » "
            "et 3 à 5 choix numérotés (actions courtes, sans dé). Objet gagné ou utilisé = écris « Tu obtiens X » / "
            "« Tu utilises X »; dégâts en chiffres. UNE seule scène, à la 2e personne (« tu », jamais mon prénom); "
            "arrête-toi après le dernier choix.)")


GAME_HIST_BUDGET = 9000  # caractères d'historique envoyés (le reste = résumé)

_CHOICE_RE = re.compile(r"^\s*(?:[-*•]\s*)?(?:\*\*)?\s*\[?(\d{1,2})\]?\s*[.)\-:–]\s+(.+?)\s*$")
_SCENE_RE = re.compile(r"^\s*[*_]*\s*SC[ÈEÉ]NE\s*[*_]*\s*:\s*[*_(«\"']*\s*([A-Za-zÀ-ÿ\-]+)", re.M | re.I)
_FENCE_RE = re.compile(r"^\s*" + FENCE)
_KV_RE = re.compile(r"([A-ZÀ-ÜÉÈ][A-ZÀ-ÜÉÈ0-9 ’'\-]{1,18})\s*:\s*([^|]+)")
_FRAC_RE = re.compile(r"(-?\d+)\s*/\s*(\d+)")
_ANSI_RE = re.compile("\x1b\\[([0-9;]*)m")
_BOXCH = set("█▓▒░┌┐└┘─│├┤┬┴┼═║╔╗╚╝╠╣╦╩╬▀▄▌▐■□▪▫●○◘◙☢☠⚠/\\_|#@*=+<>^~")


def _strip_md(s: str) -> str:
    return re.sub(r"\*\*|__", "", s or "").strip()


def game_split_blocks(text: str) -> List[Tuple[str, str]]:
    """Découpe une réponse en blocs [("fence", contenu) | ("text", contenu)]."""
    out: List[Tuple[str, str]] = []
    cur: List[str] = []
    in_f = False
    for line in (text or "").replace("\r\n", "\n").split("\n"):
        if _FENCE_RE.match(line):
            if in_f:
                out.append(("fence", "\n".join(cur)))
                cur = []
                in_f = False
            else:
                if cur:
                    out.append(("text", "\n".join(cur)))
                cur = []
                in_f = True
            continue
        cur.append(line)
    if cur:
        out.append(("fence" if in_f else "text", "\n".join(cur)))
    # le petit modèle met parfois TOUTE sa réponse dans un bloc ``` : un « bloc » qui contient un titre
    # ou « QUE FAIS-TU » est en fait du texte
    fixed: List[Tuple[str, str]] = []
    for kind, body in out:
        if kind == "fence" and (re.search(r"^\s*#{1,4}\s+\S", body, re.M) or re.search(r"QUE FAIS[- ]TU", body, re.I)):
            kind = "text"
        fixed.append((kind, body))
    return fixed


def game_is_status(block: str) -> bool:
    b = block or ""
    if "▓▓" in b.split("\n", 1)[0] or "PIP-BOY" in b.upper():
        return True
    return bool(re.search(r"\b(HP|PV|SANTÉ)\s*:", b)) and bool(re.search(r"\b(LIEU|SALLE|INVENTAIRE)\s*:", b))


def game_is_art_line(line: str) -> bool:
    s = (line or "").rstrip()
    if len(s.strip()) < 3:
        return False
    sym = sum(1 for ch in s if ch in _BOXCH)
    letters = sum(1 for ch in s if ch.isalpha())
    return sym >= 3 and sym >= letters


CODE_MODEL_RX = re.compile(r"coder|starcoder|codellama|codegemma|codestral|codeqwen|deepseek-coder|(^|[^a-z])code([^a-z]|$)", re.I)


def is_code_model(name: str) -> bool:
    """v41.1 : modèle spécialisé code (mauvais maître du jeu)."""
    return bool(CODE_MODEL_RX.search(name or ""))


GAME_END_RX = re.compile(r"[.!?…»\")\]*_~]\s*$")
GAME_FALLBACK_CHOICES = [(1, "▶ Continuer"), (2, "Regarder autour de moi"),
                         (3, "Fouiller les environs"), (4, "Parler à quelqu'un / chercher de l'aide")]
GAME_FOLLOWUP = ("(Hors-jeu : ta réponse s'est arrêtée ou n'a pas de choix.) Termine la scène en 1 à 3 phrases, "
                 "puis propose 3 à 4 choix numérotés (1. 2. 3. 4.) et finis par « QUE FAIS-TU ? ».")


def game_reply_incomplete(text: str, choices) -> bool:
    """v41.1 : pas de choix, ou texte coupé net (pas de ponctuation finale)."""
    if not choices:
        return True
    t = (text or "").rstrip()
    last = t.splitlines()[-1].strip() if t else ""
    if re.match(r"^\W*\d+\s*[.)\-–:]", last):
        return False
    return bool(t) and not GAME_END_RX.search(t)


def game_parse(text: str) -> Dict[str, Any]:
    """Analyse une réponse de jeu : titre, choix numérotés (dernière liste), bloc de statut."""
    blocks = game_split_blocks(text)
    status = ""
    for kind, body in blocks:
        if kind == "fence" and game_is_status(body):
            status = body
    if not status:  # statut écrit hors bloc ``` : ligne ▓▓ puis lignes CLÉ: valeur
        lines = (text or "").replace("\r\n", "\n").split("\n")
        for i, line in enumerate(lines):
            if "▓▓" in line and not game_is_art_line(line.replace("▓", "")):
                got = [line.strip()] + [x.rstrip() for x in lines[i + 1:game_status_span(lines, i)] if x.strip()]
                if len(got) >= 3:
                    status = "\n".join(got)
    if not status:  # statut sans ▓▓ ni bloc : 3 lignes CLÉ: valeur consécutives avec des clés connues
        known = ("HP", "PV", "SANTÉ", "RAD", "CAPS", "LIEU", "SALLE", "QUÊTE", "QUETE", "INVENTAIRE", "NOM",
                 "NIV", "FAIM", "SOIF", "SPECIAL", "PISTE", "INDICES", "OR", "MANA", "NERFS", "PIASTRES")
        lines = (text or "").replace("\r\n", "\n").split("\n")
        run: List[str] = []
        best: List[str] = []
        for line in lines + [""]:
            m0 = _KV_RE.match(line.strip()) if line.strip() and not _CHOICE_RE.match(line) else None
            if m0 and m0.group(1).strip().upper().split(" ")[0] in known:
                run.append(line.rstrip())
            else:
                if len(run) >= 3:
                    best = run
                run = []
        if best:
            status = "\n".join(best)
    title = ""
    m = re.search(r"^\s*#{1,4}\s*(.+)$", text or "", re.M)
    if m:
        title = _strip_md(m.group(1))[:90]
    # choix : dernière série de lignes numérotées (1, 2, 3…) hors blocs
    runs: List[List[Tuple[int, str]]] = []
    cur: Optional[List[Tuple[int, str]]] = None
    for kind, body in blocks:
        if kind != "text":
            if cur:
                runs.append(cur)
            cur = None
            continue
        for line in body.split("\n"):
            mm = _CHOICE_RE.match(line)
            if mm:
                n, lab = int(mm.group(1)), _strip_md(mm.group(2))
                if n == 1:
                    if cur:
                        runs.append(cur)
                    cur = [(1, lab)]
                elif cur and n == cur[-1][0] + 1:
                    cur.append((n, lab))
                elif cur:
                    runs.append(cur)
                    cur = None
            elif not line.strip():
                continue
            elif cur and line[:1] in (" ", "\t"):
                cur[-1] = (cur[-1][0], (cur[-1][1] + " " + _strip_md(line)).strip())
            elif cur:
                runs.append(cur)
                cur = None
    if cur:
        runs.append(cur)
    runs = [r for r in runs if len(r) >= 2]
    choices = runs[-1] if runs else []
    sc = _SCENE_RE.search(text or "")
    return {"title": title, "choices": choices[:9], "status": status,
            "scene": _art_norm(sc.group(1)) if sc else ""}


def game_parse_status(block: str) -> Dict[str, Any]:
    """Champs du bloc de statut : {'title', 'fields': [(clé, valeur)], 'bars': [(clé, val, max)]}."""
    lines = [l for l in (block or "").split("\n") if l.strip()]
    title = ""
    if lines and "▓▓" in lines[0]:
        title = lines[0].replace("▓", "").strip()
        lines = lines[1:]
    fields: List[Tuple[str, str]] = []
    bars: List[Tuple[str, int, int]] = []
    for line in lines:
        for part in re.split(r"\s\|\s|\s{3,}|\s·\s(?=[A-ZÀ-Ü][A-ZÀ-Ü ]{1,12}\s*:)", line):
            m = _KV_RE.search(part.strip())
            if not m:
                continue
            k, v = m.group(1).strip().upper(), m.group(2).strip()
            fields.append((k, v))
            f = _FRAC_RE.search(v)
            if f and int(f.group(2)) > 0:
                bars.append((k, max(0, int(f.group(1))), int(f.group(2))))
            elif k.startswith("RAD"):
                n = re.search(r"\d+", v)
                if n:
                    val = int(n.group(0))
                    bars.append((k, val, 1000 if val > 100 else 100))
    return {"title": title or "STATUT", "fields": fields, "bars": bars}


def ansi_segments(s: str) -> List[Tuple[str, Optional[str]]]:
    """Sous-ensemble ANSI sûr : couleurs 30-37 / 90-97 (+0 reset). Retourne [(texte, couleur|None)]."""
    pal = {30: "#4d4d4d", 31: "#ff5f56", 32: "#41ff6a", 33: "#ffcc4d", 34: "#5fa8ff", 35: "#ff79e1",
           36: "#5ff5ff", 37: "#e6e6e6", 90: "#7f7f7f", 91: "#ff8a80", 92: "#8cff9e", 93: "#fff176",
           94: "#90caf9", 95: "#f48fb1", 96: "#a7ffeb", 97: "#ffffff"}
    out: List[Tuple[str, Optional[str]]] = []
    col: Optional[str] = None
    pos = 0
    for m in _ANSI_RE.finditer(s or ""):
        if m.start() > pos:
            out.append((s[pos:m.start()], col))
        for c in (m.group(1) or "0").split(";"):
            try:
                c = int(c or 0)
            except ValueError:
                continue
            if c == 0 or c == 39:
                col = None
            elif c in pal:
                col = pal[c]
        pos = m.end()
    if pos < len(s or ""):
        out.append((s[pos:], col))
    return out


def game_clean_reply(text: str) -> str:
    """Retire ce que le petit modèle ajoute après le dernier choix (notes méta, « (Début de partie) »…)."""
    t = (text or "").replace("\r\n", "\n").rstrip()
    m = re.search(r"QUE FAIS[- ]TU", t, re.I)
    if m:  # le petit modèle enchaîne parfois une 2e scène : on garde la première
        h = re.search(r"\n\s*#{1,4}\s+\S", t[m.end():])
        if h:
            t = t[:m.end() + h.start()].rstrip()
    g = game_parse(t)
    if not g["choices"]:
        return t
    lines = t.split("\n")
    last_n = g["choices"][-1][0]
    idx = -1
    for i, line in enumerate(lines):
        m = _CHOICE_RE.match(line)
        if m and int(m.group(1)) == last_n:
            idx = i
    if idx < 0:
        return t
    j = idx + 1
    while j < len(lines) and lines[j][:1] in (" ", "\t") and lines[j].strip():
        j += 1
    tail = "\n".join(lines[j:]).strip()
    if tail and (FENCE in tail or "▓▓" in tail):
        return t  # contenu utile après les choix : on ne coupe pas
    return "\n".join(lines[:j]).rstrip()


class _GameStop:
    """« Annuler » combiné : Échap de Marc OU fin de scène détectée pendant le flux."""

    def __init__(self, main: Optional[threading.Event] = None):
        self.main = main
        self.stop = False

    def is_set(self) -> bool:
        return self.stop or bool(self.main is not None and self.main.is_set())


def game_turn_complete(text: str) -> bool:
    """Vrai quand la scène est finie (≥3 choix après « QUE FAIS-TU ? » puis autre chose) → on coupe le flux."""
    t = text or ""
    m = None
    for m in re.finditer(r"QUE FAIS[- ]TU", t, re.I):
        pass
    if not m:
        return False
    n = 0
    has_status = "▓▓" in t[:m.start()]
    lines = t[m.end():].split("\n")[1:]
    for line in lines[:-1]:  # la dernière ligne est peut-être incomplète
        if not has_status and (_FENCE_RE.match(line) or "▓▓" in line or (
                n >= 3 and _KV_RE.match(line.strip()) and not _CHOICE_RE.match(line))):
            return False  # statut écrit après les choix : on le laisse arriver
        if _CHOICE_RE.match(line):
            n += 1
        elif not line.strip() or line[:1] in (" ", "\t"):
            continue
        elif n >= 3:
            return True
        else:
            return False
    return False


# Nettoyage d'un prompt où Marc a collé l'aperçu complet (ADN + rôle + date + garde-fou de chasse)
def prompt_clean(text: str) -> Tuple[str, List[str]]:
    t = str(text or "")
    found: List[str] = []
    if SYSTEM_BASE in t:
        t = t.replace(SYSTEM_BASE, "")
        found.append("l'ADN Padawan")
    elif SYSTEM_BASE[:70] in t:
        i = t.index(SYSTEM_BASE[:70])
        j = t.find("\n\n", i)
        t = t[:i] + (t[j:] if j > 0 else "")
        found.append("l'ADN Padawan")
    for rid in RoleRouter_ROLE_IDS:
        rt = RoleRouter.default_role_text(rid)
        if rt and rt in t:
            t = t.replace(rt, "")
            found.append(f"le texte du rôle {RoleRouter.ROLES[rid]['label']}")
    t2 = re.sub(r"\s*Si les sources digressent, ignore-les\.\s*Reste sur:\s*[^\n]*", "", t)
    if t2 != t:
        found.append("le garde-fou de chasse « Reste sur: … »")
        t = t2
    t2 = re.sub(r"\s*Date du jour:\s*\d{1,2} [a-zéû]+ \d{4}\.", "", t)
    if t2 != t:
        found.append("la date figée")
        t = t2
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    return t, found



GAME_COLORS = {
    "bg": "#06120a", "panel": "#0a1a0f", "pip": "#020a04", "art": "#04140a", "fg": "#c9f7c9",
    "dim": "#5f8f68", "green": "#41ff6a", "amber": "#ffc857", "cyan": "#5ff5ff", "bad": "#ff6b5f",
    "line": "#1f4a2a", "btn": "#0f2e17", "btnh": "#1d5a2c",
}
GAME_INPUT_TIP = "🎮 Mode Jeu : clique un choix, tape 1–9, ou écris ton action ici puis Entrée · Échap = annuler"
GAME_GEN_OPTIONS = {"num_predict": 1400, "temperature": 0.85, "repeat_penalty": 1.08}


def game_trim_history(st: Dict[str, Any], budget: int = 0) -> Tuple[List[Dict[str, str]], str]:
    """Derniers tours qui tiennent dans le budget + mémoire (chronique + dernier statut) si on a coupé."""
    budget = budget or GAME_HIST_BUDGET
    msgs = [m for m in (st.get("msgs") or []) if m.get("role") in ("user", "assistant") and m.get("content")]
    keep: List[Dict[str, str]] = []
    total = 0
    i = len(msgs)
    while i >= 2:
        pair = msgs[i - 2:i]
        size = sum(len(m["content"]) for m in pair)
        if keep and total + size > budget:
            break
        keep = pair + keep
        total += size
        i -= 2
    memo = ""
    if i > 0:
        chron = "; ".join((st.get("chronicle") or [])[-25:])
        memo = "[MÉMOIRE DE LA PARTIE — tours précédents résumés] Choix du joueur : " + chron + ". "
        if st.get("quests"):
            memo += "Quêtes : " + " → ".join(st["quests"][-6:]) + ". "
        if st.get("status"):
            memo += "Dernier statut connu :\n" + FENCE + "\n" + st["status"] + "\n" + FENCE + "\n"
        memo += "Continue l'histoire de façon cohérente.\n\n"
    return keep, memo


def game_export_txt(st: Dict[str, Any]) -> str:
    out = [f"{st.get('name', 'Partie')} — exporté par Padawan le {time.strftime('%Y-%m-%d %H:%M')}", "=" * 60, ""]
    for e in st.get("log") or []:
        if e.get("who") == "you":
            out.append(f"▶ {e.get('text', '')}")
        elif e.get("who") == "mj":
            fam_art = game_art_for(st.get("builtin", ""), game_parse(e.get("text", ""))["scene"])[1]
            t = e.get("text", "")
            if fam_art:
                t = _SCENE_RE.sub(lambda m: fam_art, t, count=1)
            out.append(t)
        elif e.get("who") == "intro":
            meta = GAME_META.get(st.get("builtin", ""), {})
            out.append(meta.get("title", ""))
            out.append(meta.get("intro", ""))
        out.append("")
    return "\n".join(out)


def _game_cached_art(h: str):
    """v41.0 : art ANSI d'une scène générée (cache du Studio), sans démarrer quoi que ce soit."""
    if not h or _ANSI is None:
        return None
    try:
        p = os.path.join(PRIVATE_DIR, "studio", "cache", h + ".json")
        with open(p, "r", encoding="utf-8") as f:
            return _ANSI.art_from_dict(json.load(f)["art"])
    except Exception:
        return None


def game_export_html(st: Dict[str, Any], images: bool = True, generated: bool = False) -> str:
    import html as _h
    css = ("body{background:#06120a;color:#c9f7c9;font:17px/1.55 'Segoe UI',sans-serif;max-width:860px;margin:30px auto;padding:0 18px}"
           "h1{color:#ffc857;font-family:Consolas,monospace}h2{color:#ffc857;font-family:Consolas,monospace;margin-top:34px}"
           "pre{background:#04140a;color:#41ff6a;padding:12px 16px;border:1px solid #1f4a2a;border-radius:6px;"
           "font:14px/1.25 Consolas,'Cascadia Mono',monospace;overflow:auto}"
           ".you{color:#ffc857;font-weight:bold;font-family:Consolas,monospace;margin-top:22px}"
           ".ch{color:#41ff6a;font-weight:bold}.chk{color:#5ff5ff;font-family:Consolas,monospace}.sys{color:#5f8f68}"
           ".img{margin:14px 0}.img pre.ansi{display:inline-block;padding:6px;border:1px solid #1f4a2a;border-radius:6px;"
           "line-height:1!important;letter-spacing:0;overflow:visible}")
    body = [f"<h1>☢ {_h.escape(st.get('name', 'Partie'))}</h1>",
            f"<p class='sys'>Exporté par Padawan le {time.strftime('%Y-%m-%d %H:%M')} · {st.get('turn', 0)} tours</p>"]
    bi = st.get("builtin", "")
    # v40.2 : les illustrations ANSI (mêmes règles que l'écran : pas de répétition)
    img_fam = game_img_family(bi) if images else ""
    img_plan = game_img_plan(st) if img_fam else {}

    def img_html(key: str, ei: int = -1) -> str:
        try:
            a = _ANSI.bank_art(game_img_bank(), img_fam, key) if key else None
            if a is not None and generated and 0 <= ei < len(st.get("log") or []):
                a = _game_cached_art((st["log"][ei] or {}).get("img_gen", "")) or a
            return ("<div class='img'>" + a.to_html(fragment=True, font_px=11) + "</div>") if a else ""
        except Exception:
            return ""
    if -1 in img_plan:
        body.append(img_html(img_plan[-1]))

    def para(line: str) -> str:
        t = _h.escape(line)
        t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
        t = re.sub(r"(\[[^\]]{2,90}\])", r"<span class='chk'>\1</span>", t)
        return t

    for ei, e in enumerate(st.get("log") or []):
        who, text = e.get("who"), e.get("text", "")
        if who == "you":
            body.append(f"<p class='you'>▶ {_h.escape(text)}</p>")
        elif who == "intro":
            meta = GAME_META.get(bi, {})
            art = game_art_for(bi, meta.get("art", ""))[1]
            body.append(f"<h2>{_h.escape(meta.get('title', ''))}</h2>")
            if img_fam:
                body.append(img_html(img_plan.get(ei, "")))
            elif art:
                body.append(f"<pre>{_h.escape(art)}</pre>")
            body.append("".join(f"<p>{para(x)}</p>" for x in meta.get("intro", "").split("\n") if x.strip()))
        elif who == "mj":
            g = game_parse(text)
            art = game_art_for(bi, g["scene"], text[:600])[1] if bi else ""
            done = False
            if img_fam:  # v40.2 : image ANSI (ou rien si la scène n'a pas changé) à la place de l'art ASCII
                art = img_html(img_plan.get(ei, ""), ei) or " "
                pre_art = art if art.strip() else ""
            for kind, blk in game_split_blocks(text):
                if kind == "fence":
                    if game_is_status(blk) or not art:
                        body.append(f"<pre>{_h.escape(blk.strip(chr(10)))}</pre>")
                    elif not done:
                        body.append(pre_art if img_fam else f"<pre>{_h.escape(art)}</pre>")
                        done = True
                    continue
                for line in blk.split("\n"):
                    if not line.strip():
                        continue
                    m = re.match(r"^\s*#{1,4}\s*(.+)$", line)
                    if m:
                        body.append(f"<h2>{_h.escape(_strip_md(m.group(1)))}</h2>")
                        if art and not done:
                            body.append(pre_art if img_fam else f"<pre>{_h.escape(art)}</pre>")
                            done = True
                    elif _SCENE_RE.match(line):
                        if art and not done:
                            body.append(pre_art if img_fam else f"<pre>{_h.escape(art)}</pre>")
                            done = True
                    elif _CHOICE_RE.match(line):
                        body.append(f"<p class='ch'>{para(line.strip())}</p>")
                    elif img_fam and game_is_art_line(line) and not line.strip().startswith("["):
                        continue  # art ASCII dessiné par le modèle : remplacé par les images
                    else:
                        body.append(f"<p>{para(line)}</p>")
            if img_fam and pre_art and not done:
                body.append(pre_art)
    return ("<!doctype html><html lang='fr'><head><meta charset='utf-8'><title>"
            + _h.escape(st.get("name", "Partie")) + "</title><style>" + css + "</style></head><body>"
            + "\n".join(body) + "</body></html>")


GAME_GENERIC_FORMAT = "\n".join([
    "",
    "FORMAT OBLIGATOIRE DE CHAQUE RÉPONSE (dans cet ordre, rien d'autre) :",
    "## Titre de la scène",
    FENCE,
    "petit art ASCII (6 à 10 lignes, 40 colonnes maximum)",
    FENCE,
    "Narration et dialogues (120 à 220 mots, au présent, en tutoyant le joueur).",
    FENCE,
    "▓▓ STATUT ▓▓",
    "NOM: (nom) | NIV: 1",
    "PV: 20/20 | OR: 0",
    "LIEU: (lieu)",
    "QUÊTE: (quête active)",
    "INVENTAIRE: (objet), (objet)",
    FENCE,
    "QUE FAIS-TU ?",
    "1. (choix)",
    "2. (choix)",
    "3. (choix)",
    "",
    "Mets 3 à 5 choix numérotés (actions courtes, sans dé), un par ligne. Rien après le dernier choix.",
    "Le message du joueur contient [JET d20 = N] : 1-5 échec grave, 6-10 échec, 11-15 réussite, 16-20 belle réussite.",
    "DÉMARRAGE : quand le joueur dit « Commence la partie », présente le monde en quelques phrases, puis propose "
    "3 personnages en choix numérotés + « 4. Créer mon propre personnage ».",
])

GAME_GEN_SYSTEM = ("Tu es un concepteur de jeux de rôle textuels. Tu écris en français québécois naturel. "
                   "Tu réponds UNIQUEMENT avec le texte demandé, sans introduction ni commentaire.")
GAME_GEN_ASK = (
    "Écris le PROMPT SYSTÈME d'un jeu de rôle textuel interactif sur ce thème : « {idee} ».\n"
    "Le prompt s'adresse au modèle qui sera le MAÎTRE DU JEU. Il doit contenir, avec ces titres :\n"
    "1. Une phrase « Tu es le MAÎTRE DU JEU de « TITRE DU JEU » … » et le ton.\n"
    "2. UNIVERS : 5 à 8 puces (époque, lieux précis, factions ou personnages, objets, humour).\n"
    "3. RÈGLES : tu tutoies le joueur; tu restes toujours le maître du jeu (aucun méta-commentaire, aucune URL); "
    "conséquences réelles; état cohérent d'un tour à l'autre; tests avec [JET d20 = N].\n"
    "4. Les noms des jauges du statut adaptées au thème (ex. PV, MANA, OR, SANTÉ…), écrites comme « PV: 20/20 ».\n"
    "N'écris PAS de section FORMAT : Padawan l'ajoute lui-même. 250 à 450 mots."
)


def game_fix_generated(txt: str) -> str:
    """Nettoie un prompt de jeu généré et garantit le format attendu par Padawan."""
    t = (txt or "").strip()
    t = re.sub(r"^" + FENCE + r"[a-z]*\s*|\s*" + FENCE + r"$", "", t).strip()
    t = re.split(r"\n\s*#*\s*\**\s*FORMAT OBLIGATOIRE", t)[0].strip()
    return t + "\n" + GAME_GENERIC_FORMAT


def game_merge_status(old: str, new: str) -> str:
    """Statut partiel (ex. sans HP) : on garde les jauges du tour précédent pour le Pip-Boy."""
    if not old or not new:
        return new or old
    o, n = game_parse_status(old), game_parse_status(new)
    nd = dict(n["fields"])
    if any(k in nd for k in ("HP", "PV", "SANTÉ")) or len(nd) >= 6:
        return new
    out = [(k, nd.get(k, v)) for k, v in o["fields"]]
    seen = {k for k, _ in o["fields"]}
    out += [(k, v) for k, v in n["fields"] if k not in seen]
    title = n["title"] if n["title"] != "STATUT" else o["title"]
    return f"▓▓ {title} ▓▓\n" + "\n".join(f"{k}: {v}" for k, v in out)


# ── v39.4: moteur d'état du jeu (inventaire / jauges robustes, même si le modèle oublie le statut) ──
def _fold(s: str) -> str:
    """minuscules sans accents (comparaisons tolérantes)."""
    s = unicodedata.normalize("NFD", str(s or ""))
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn").lower()


_GKEY_ALIAS = {"INV": "INVENTAIRE", "INVENTAIRE": "INVENTAIRE", "INVENTORY": "INVENTAIRE", "SAC": "INVENTAIRE",
               "SAC A DOS": "INVENTAIRE", "OBJETS": "INVENTAIRE", "QUETE": "QUÊTE", "QUETES": "QUÊTE",
               "QUETE ACTIVE": "QUÊTE", "QUEST": "QUÊTE", "MISSION": "QUÊTE", "PV": "PV", "HP": "HP",
               "SANTE": "SANTÉ", "NIVEAU": "NIV", "CAPSULES": "CAPS"}
_GKEY_KNOWN = {"HP", "PV", "SANTÉ", "RAD", "RADS", "CAPS", "FAIM", "SOIF", "NOM", "NIV", "SPECIAL", "LIEU", "QUÊTE",
               "INVENTAIRE", "XP", "PISTE", "INDICES", "OR", "MANA", "NERFS", "PIASTRES", "SALLE", "ARME", "ARMURE",
               "ÉTAGE", "ETAGE", "CLASSE", "MUNITIONS", "KARMA", "HEURE", "JOUR", "ALLIÉS", "ALLIES"}
_HP_KEYS = ("HP", "PV", "SANTÉ")
_GKV_LINE = re.compile(r"^([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9 ’'\-]{0,18}?)\s*:\s*(.*)$")


def game_norm_key(k: str) -> str:
    raw = re.sub(r"[*_`▓]", "", str(k or "")).strip()
    f = _fold(raw).upper().strip()
    f = re.sub(r"\s+", " ", f)
    if f in _GKEY_ALIAS:
        return _GKEY_ALIAS[f]
    for key in _GKEY_KNOWN:
        if _fold(key).upper() == f:
            return key
    return raw.upper()


def _gline_clean(line: str) -> str:
    s = (line or "").strip()
    s = re.sub(r"^[>\-*•·▸▶►]+\s*", "", s)
    s = s.replace("**", "").replace("__", "").replace("`", "").strip()
    return s.strip("▓ ").strip() if s.startswith("▓") else s


def game_fields(text: str, extra_keys=()) -> Dict[str, str]:
    """Toutes les lignes CLÉ: valeur connues de la réponse (statut ``` ou non, lignes vides tolérées,
    puces, gras, « | »). Inventaire sur plusieurs lignes à puces accepté. La dernière occurrence gagne."""
    known = set(_GKEY_KNOWN) | {game_norm_key(k) for k in extra_keys}
    out: Dict[str, str] = {}
    lines = (text or "").replace("\r\n", "\n").split("\n")
    i = 0
    while i < len(lines):
        raw = lines[i]
        i += 1
        if _CHOICE_RE.match(raw) and ":" not in raw[:24]:
            continue
        s = _gline_clean(raw)
        if not s or ":" not in s:
            continue
        for part in re.split(r"\s*\|\s*|\s{3,}|\s·\s(?=[A-ZÀ-Ü][A-ZÀ-Ü ]{1,12}\s*:)", s):
            m = _GKV_LINE.match(part.strip())
            if not m:
                continue
            k = game_norm_key(m.group(1))
            if k not in known:
                continue
            v = m.group(2).strip().strip("*").strip()
            if k == "INVENTAIRE" and not v:  # liste à puces sur les lignes suivantes
                items = []
                while i < len(lines):
                    nx = lines[i].strip()
                    if not nx and not items:
                        i += 1
                        continue
                    if re.match(r"^[-*•·▸]\s*\S", nx) and not _GKV_LINE.match(_gline_clean(nx) or "x"):
                        items.append(re.sub(r"^[-*•·▸]\s*", "", nx).strip())
                        i += 1
                        continue
                    if re.match(r"^[-*•·▸]\s*\S", nx):
                        items.append(re.sub(r"^[-*•·▸]\s*", "", nx).strip())
                        i += 1
                        continue
                    break
                v = ", ".join(items)
            if v or k == "INVENTAIRE":
                out[k] = v
    return out


_ITEM_STOP = {"le", "la", "les", "un", "une", "des", "du", "de", "d", "l", "ton", "ta", "tes", "ce", "cet", "cette",
              "ces", "son", "sa", "ses", "a", "au", "aux", "en", "et", "x", "mon", "ma", "mes", "quelques", "petit",
              "petite", "vieux", "vieille", "vieil", "nouveau", "nouvelle", "deux", "trois", "quatre", "cinq"}
_NUMW = {"un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8,
         "dix": 10, "quelques": 2}


def _sing(w: str) -> str:
    if len(w) > 3 and w.endswith(("s", "x")) and not w.endswith(("ss", "us")):
        return w[:-1]
    return w


def game_item_words(name: str) -> List[str]:
    f = _fold(name)
    f = re.sub(r"\(.*?\)", " ", f)
    ws = [_sing(w) for w in re.findall(r"[a-z0-9]+", f)]
    return [w for w in ws if w not in _ITEM_STOP and not w.isdigit() and len(w) > 1]


def game_item_parse(s: str) -> Tuple[int, str]:
    t = (s or "").strip().strip(".").strip()
    m = re.match(r"^(\d{1,3})\s*[x×]?\s+(.+)$", t)
    if m:
        return int(m.group(1)), m.group(2).strip()
    m = re.match(r"^(.+?)\s*(?:[x×]\s*(\d{1,3})|\((\d{1,3})\))$", t)
    if m:
        return int(m.group(2) or m.group(3)), m.group(1).strip()
    m = re.match(r"^(un|une|deux|trois|quatre|cinq|six|sept|huit|dix|quelques)\s+(.+)$", t, re.I)
    if m:
        return _NUMW[m.group(1).lower()], m.group(2).strip()
    return 1, t


def game_item_fmt(q: int, name: str) -> str:
    return f"{q} {name}" if q > 1 else name


def game_inv_list(v: str) -> List[Tuple[int, str]]:
    out: List[Tuple[int, str]] = []
    if not v or _fold(v).strip(" .-") in ("aucun", "rien", "vide", "n/a", "neant", "(vide)"):
        return out
    v = re.sub(r"\(([^()]*)\)", lambda m: "(" + m.group(1).replace(",", "/") + ")", v.strip().rstrip("."))
    for part in re.split(r"\s*[,;•]\s*|\s+·\s+|\s+\+\s+", v):
        part = part.strip().rstrip(".").strip()
        if part.startswith("(") and part.endswith(")") or part.startswith("[") and part.endswith("]"):
            part = part[1:-1].strip()
        if part and len(part) <= 60 and not part.startswith(("+", "-", "−")):
            q, n = game_item_parse(part)
            if q > 0 and game_item_words(n):
                out.append((q, n))
    return out


def game_item_match(inv: List[Tuple[int, str]], phrase: str) -> int:
    """Index de l'objet d'inventaire nommé dans la phrase (tolérant : accents, pluriel, articles), sinon -1."""
    pw = set(game_item_words(phrase))
    if not pw:
        return -1
    best, score = -1, 0
    for i, (_q, name) in enumerate(inv):
        iw = game_item_words(name)
        if not iw:
            continue
        common = [w for w in iw if w in pw and len(w) >= 3]
        sc = len(common) * 10 + (5 if iw[0] in pw else 0)
        if common and sc > score:
            best, score = i, sc
    return best


_ITEM_LEX = ("stimpak", "stim", "nuka", "cola", "munition", "balle", "cartouche", "chargeur", "arme", "pistolet", "fusil",
             "revolver", "couteau", "machette", "batte", "hache", "masse", "cle", "carte", "plan", "holobande",
             "holodisque", "radaway", "radx", "med", "buffout", "mentat", "jet", "eau", "conserve", "poutine",
             "sirop", "grenade", "mine", "armure", "casque", "veste", "manteau", "batterie", "cellule", "fusible",
             "outil", "pince", "pied", "lampe", "corde", "bandage", "trousse", "medicament", "pilule", "seringue",
             "potion", "parchemin", "epee", "dague", "bouclier", "anneau", "amulette", "lettre", "photo", "dossier",
             "cigarette", "flasque", "whisky", "gin", "biere", "badge", "insigne", "boussole", "radio", "piece",
             "composant", "ferraille", "vis", "ruban", "colle", "tissu", "cuir", "viande", "ration", "nourriture",
             "bouteille", "canette", "boite", "sac", "kit", "detonateur", "dynamite", "molotov", "jambon", "pomme",
             "steak", "baie", "champignon", "talisman", "grimoire", "livre", "journal", "magazine", "disquette",
             "crochet", "epingle", "jumelle", "lunette", "masque", "filtre", "gant", "botte", "tuyau", "lance")
_CONSUMABLE = ("stimpak", "stim", "nuka", "cola", "eau", "conserve", "poutine", "sirop", "radaway", "radx", "med",
               "buffout", "mentat", "jet", "bandage", "pilule", "seringue", "potion", "cigarette", "flasque", "whisky",
               "gin", "biere", "ration", "nourriture", "viande", "bouteille", "canette", "grenade", "molotov",
               "dynamite", "jambon", "pomme", "steak", "baie", "champignon", "parchemin", "munition", "balle",
               "cartouche", "mine", "trousse", "medicament", "kit", "epingle", "crochet")
_FOOD = ("poutine", "conserve", "viande", "ration", "nourriture", "jambon", "pomme", "steak", "baie", "champignon",
         "sirop", "repas", "bouffe", "pain", "fromage", "orignal")
_DRINK = ("eau", "nuka", "cola", "biere", "whisky", "gin", "flasque", "bouteille", "canette", "cafe", "the")
_GAIN_BAD = {"fuite", "decision", "refuge", "courage", "temps", "conscience", "souffle", "chemin", "route", "direction",
             "place", "peur", "confiance", "force", "sens", "idee", "moyen", "plaisir", "parole", "note", "garde", "air",
             "vue", "position", "controle", "fin", "raison", "distance", "pause", "risque", "porte", "passage", "coup",
             "oeil", "main", "pied", "tete", "elan", "reponse", "information", "indice", "nouvelle", "piste", "aide",
             "conseil", "avance", "rendez", "corps", "cadavre", "trace", "odeur", "bruit", "silence", "lumiere",
             "ombre", "sortie", "entree", "escalier", "couloir", "piece", "salle", "abri", "temps", "envie", "gout",
             "chance", "occasion", "dessin", "cache", "vie", "point", "degat", "rad", "hp", "pv", "xp"}
_PH = r"((?:\d{1,3}\s+|un |une |des |du |de la |de l['’]|l['’]|le |la |les |ce |cet |cette |ces |quelques |deux |trois |ton |ta |tes )[^.,;:!?»«\"\n()]{2,60}?)(?=\s+(?:et|puis|mais|qui|que|qu['’]|dans|sur|pour|avec|avant|apr[èe]s|en|sous|vers|contre|d['’]un|d['’]une)\b|[.,;:!?»«\"\n()]|$)"
_GAIN_STRONG = re.compile(
    r"\b(?:tu\s+|t['’])(?:obtiens|ramasses|re[çc]ois|r[ée]cup[èe]res|empoches|voles|ach[èe]tes|d[ée]robes|chipes|"
    r"pognes|chopes|as\s+(?:obtenu|ramass[ée]|re[çc]u|r[ée]cup[ée]r[ée]|empoch[ée]|vol[ée]|achet[ée]|trouv[ée]|gagn[ée]))\s+"
    r"(?:aussi\s+|enfin\s+|alors\s+|finalement\s+)?" + _PH, re.I)
_GAIN_WEAK = re.compile(r"\b(?:tu\s+|t['’])(?:trouves|prends|gagnes|d[ée]couvres|d[ée]nich(?:es)|d[ée]terres|saisis|attrapes)\s+"
                        r"(?:aussi\s+|enfin\s+|alors\s+)?" + _PH, re.I)
_GAIN_GIVEN = re.compile(r"\b(?:te|t['’])\s*(?:donne|donnent|donna|donnèrent|tend|tendent|tendit|remet|remettent|remit|"
                         r"offre|offrent|offrit|confie|confient|confia|lance|lança|vend|vendent|vendit|glisse|glissa)\s+" + _PH, re.I)
_GAIN_BAG = re.compile(r"\b(?:tu\s+)?(?:glisses|ranges|mets|fourres|places|accroches)\s+" + _PH + r"\s+(?:dans|à|a|sur)\s+(?:ton|ta|tes)\s+"
                       r"(?:sac|inventaire|poche|pip-boy|ceinture|besace|holster|dos)", re.I)
_GAIN_TAG = re.compile(r"(?:\[\s*\+\s*|\(\s*\+\s*|\b(?:objet|item)s?\s+(?:obtenu|trouv[ée]|ajout[ée])s?\s*:\s*|"
                       r"\bnouvel?\s+objet\s*:\s*|\bajout[ée]s?\s+(?:à|a)\s+l['’]inventaire\s*:\s*|\b(?:butin|loot)\s*:\s*)"
                       r"([^\]\)\n.;]{2,60})", re.I)
_LOSS_ANY = re.compile(r"\b(?:tu\s+|t['’])(?:perds|donnes|vends|jettes|abandonnes|[ée]changes|laisses tomber|troques|"
                       r"c[èe]des|as\s+perdu|as\s+donn[ée]|as\s+vendu|te fais voler|te fais prendre)\s+" + _PH, re.I)
_LOSS_USE = re.compile(r"\b(?:tu\s+|t['’])(?:utilises|bois|avales|manges|consommes|injectes|t['’]injectes|lances|"
                       r"vides|engloutis|d[ée]vores|grignotes|sirotes|ouvres|appliques|as\s+(?:utilis[ée]|bu|mang[ée]|aval[ée]|"
                       r"consomm[ée]|lanc[ée]|inject[ée]))\s+" + _PH, re.I)
_LOSS_TAG = re.compile(r"(?:\[\s*[-−–]\s*|\(\s*[-−–]\s*|\bobjets?\s+(?:perdu|utilis[ée]|consomm[ée])s?\s*:\s*|"
                       r"\bretir[ée]s?\s+de\s+l['’]inventaire\s*:\s*)([^\]\)\n.;]{2,60})", re.I)
_STAT_SIGNED = re.compile(r"(?<![\w/])([+\-−–])\s?(\d{1,3})\s?(HP|PV|RADS?|CAPS|XP|SANT[ÉE]|NERFS|OR|MANA|PIASTRES|"
                          r"points? de vie|capsules?)\b", re.I)
_STAT_VERB = re.compile(r"\b(perds|encaisses|subis|prends|absorbes|r[ée]cup[èe]res|regagnes|gagnes|re[çc]ois|obtiens|"
                        r"trouves|empoches|ramasses|d[ée]penses|paies|payes|donnes|as\s+perdu|as\s+gagn[ée])\s+(\d{1,3})\s+"
                        r"(HP|PV|points? de vie|points? de sant[ée]|rads?|capsules?|caps|XP|points? d['’]exp[ée]rience|"
                        r"pi[èe]ces? d['’]or|piastres?|points? de d[ée]g[âa]ts|d[ée]g[âa]ts)", re.I)
_DMG = re.compile(r"\b(\d{1,3})\s+(?:points?\s+de\s+)?d[ée]g[âa]ts\b", re.I)
_QUEST_NARR = re.compile(r"(?:nouvelle\s+qu[êe]te|qu[êe]te\s+(?:mise\s+[àa]\s+jour|ajout[ée]e|active)|"
                         r"\[\s*qu[êe]te\s*\])\s*[:\-–]?\s*([^\n\]]{4,120})", re.I)
_WOUND = re.compile(r"\bte\s+(?:mord|frapp|griff|touch|br[ûu]l|cogn|bless|lac[èe]r|transperc|percut|plaqu|ent[ae]ill|mitraill|tire\s+dessus)|"
                    r"\bt['’](?:attaqu|atteint|[ée]gratign|[ée]corch|[ée]clabouss)|"
                    r"\btu\s+(?:es|te\s+fais)\s+(?:bless|touch|mordu|griff|frapp|projet)|\btu\s+saignes|\btu\s+tombes|"
                    r"\bdouleur|\bblessure|\bmorsure|\bton\s+sang|\bta\s+(?:jambe|main|t[êe]te|cheville)\s+(?:saigne|br[ûu]le)", re.I)


def _phrase_ok(ph: str, weak: bool = False) -> Optional[str]:
    ph = re.split(r"\s+(?:et|qui|que|qu['’]|dans|sur|pour|avant|apr[èe]s|pendant|avec\s+(?:un|une|le|la|les)\s+\w+\s+\w+|"
                  r"en\s+\w+ant|sous|vers|contre|parmi|derri[èe]re|devant|puis|mais|alors|car|quand|lorsque|si|comme)\b",
                  ph.strip(), maxsplit=1)[0].strip(" -–—'’")
    words = ph.split()
    if not words:
        return None
    ph = " ".join(words[:7])
    w = game_item_words(ph)
    if not w or w[0] in _GAIN_BAD or all(x in _GAIN_BAD for x in w):
        return None
    if weak and not any(x.startswith(lx) for x in w for lx in _ITEM_LEX):
        return None
    if re.match(r"^(?:l['’]|le |la |les |un |une )?(?:air|temps|fuite|parole|d[ée]cision)\b", _fold(ph)):
        return None
    return ph


def game_narrative(text: str) -> Dict[str, Any]:
    """Objets gagnés / perdus et variations de jauges racontés dans la narration."""
    lines = []
    for raw in (text or "").replace("\r\n", "\n").split("\n"):
        s = _gline_clean(raw)
        if not s or _CHOICE_RE.match(raw) or re.match(r"^\s*#", raw) or re.match(r"^\s*QUE FAIS", s, re.I):
            continue
        m = _GKV_LINE.match(s)
        if m and game_norm_key(m.group(1)) in _GKEY_KNOWN:
            continue
        lines.append(s)
    narr = "\n".join(lines)
    gains: List[str] = []
    losses: List[Tuple[str, bool]] = []  # (phrase, usage)
    for rx, weak in ((_GAIN_STRONG, False), (_GAIN_GIVEN, False), (_GAIN_BAG, False), (_GAIN_WEAK, True)):
        for m in rx.finditer(narr):
            ph = _phrase_ok(m.group(1), weak)
            if ph:
                gains.append(ph)
    for m in _GAIN_TAG.finditer(narr):
        ph = m.group(1).strip()
        if not re.match(r"^\d{1,3}\s*(HP|PV|RAD|CAPS|XP)\b", ph, re.I) and game_item_words(ph):
            gains.append(ph)
    for m in _LOSS_ANY.finditer(narr):
        losses.append((m.group(1).strip(), False))
    for m in _LOSS_USE.finditer(narr):
        losses.append((m.group(1).strip(), True))
    for m in _LOSS_TAG.finditer(narr):
        ph = m.group(1).strip()
        if not re.match(r"^\d{1,3}\s*(HP|PV|RAD|CAPS|XP)\b", ph, re.I):
            losses.append((ph, False))
    stats: Dict[str, int] = {}

    def add(k, d):
        stats[k] = stats.get(k, 0) + d

    def skey(u: str) -> str:
        f = _fold(u)
        if f.startswith(("hp", "pv", "point de vie", "points de vie", "sante", "point de sante", "points de sante")):
            return "HP"
        if f.startswith("rad"):
            return "RAD"
        if f.startswith(("cap",)):
            return "CAPS"
        if "or" == f or "piece" in f:
            return "OR"
        if "piastre" in f:
            return "PIASTRES"
        if "exp" in f or f == "xp":
            return "XP"
        if "degat" in f:
            return "DMG"
        return f.upper()

    for m in _STAT_SIGNED.finditer(narr):
        sign = -1 if m.group(1) in "-−–" else 1
        add(skey(m.group(3)), sign * int(m.group(2)))
    for m in _STAT_VERB.finditer(narr):
        verb, n, k = _fold(m.group(1)), int(m.group(2)), skey(m.group(3))
        if k == "DMG":
            add("HP", -n)
            continue
        neg = verb.startswith(("perds", "encaisses", "subis", "depenses", "paies", "payes", "donnes", "as perdu"))
        if k == "RAD" and verb.startswith(("prends", "absorbes", "subis", "encaisses", "recois")):
            neg = False
        if k == "HP" and verb.startswith("prends"):
            continue
        add(k, -n if neg else n)
    if "HP" not in stats:
        for m in _DMG.finditer(narr):
            add("HP", -int(m.group(1)))
    quest = ""
    mq = None
    for mq in _QUEST_NARR.finditer(narr):
        pass
    if mq:
        quest = mq.group(1).strip(" .*»«\"")
    return {"gains": gains, "losses": losses, "stats": stats, "quest": quest, "narr": narr}


def _num(v: str) -> Optional[Tuple[int, Optional[int]]]:
    m = _FRAC_RE.search(v or "")
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"-?\d+", v or "")
    return (int(m.group(0)), None) if m else None


def game_status_dict(status: str) -> Tuple[str, Dict[str, str]]:
    info = game_parse_status(status or "")
    d: Dict[str, str] = {}
    for k, v in info["fields"]:
        d[game_norm_key(k)] = v
    return info["title"] if info["title"] != "STATUT" else "", d


def game_status_text(title: str, d: Dict[str, str], template: str = "") -> str:
    """Rebâtit un bloc ▓▓ propre (le Pip-Boy le relit) en gardant la disposition du statut précédent."""
    rows: List[str] = []
    if template:
        used = set()
        for line in template.split("\n"):
            if not line.strip() or "▓▓" in line:
                continue
            parts = []
            for part in re.split(r"\s\|\s|\s{3,}|\s·\s(?=[A-ZÀ-Ü][A-ZÀ-Ü ]{1,12}\s*:)", line):
                m = _KV_RE.search(part.strip())
                if not m:
                    continue
                k = game_norm_key(m.group(1))
                if k in d and k not in used:
                    used.add(k)
                    parts.append(f"{k}: {d[k]}")
            if parts:
                rows.append(" | ".join(parts))
        rest = {k: v for k, v in d.items() if k not in used}
        if rest:
            extra = game_status_text("", rest).split("\n")[1:]
            rows += [x for x in extra if x.strip()]
        return f"▓▓ {title or 'STATUT'} ▓▓\n" + "\n".join(rows)
    short: List[str] = []
    long_keys = ("INVENTAIRE", "QUÊTE", "LIEU", "SPECIAL", "INDICES", "PISTE", "ALLIÉS")
    order = ["NOM", "NIV", "XP", "HP", "PV", "SANTÉ", "RAD", "CAPS", "OR", "PIASTRES", "MANA", "NERFS", "FAIM", "SOIF"]
    keys = [k for k in order if k in d] + [k for k in d if k not in order and k not in long_keys] + \
           [k for k in long_keys if k in d]
    for k in keys:
        v = (d.get(k) or "").strip()
        if k in long_keys:
            if short:
                rows.append(" | ".join(short))
                short = []
            rows.append(f"{k}: {v}")
        else:
            short.append(f"{k}: {v}")
            if len(short) == 3:
                rows.append(" | ".join(short))
                short = []
    if short:
        rows.append(" | ".join(short))
    return f"▓▓ {title or 'STATUT'} ▓▓\n" + "\n".join(rows)


def game_apply_turn(old_status: str, reply: str, dice: int = 0, tick: bool = True) -> Dict[str, Any]:
    """Applique un tour : statut du modèle (tolérant) + ce que raconte la narration + faim/soif/dés.
    Retourne {'status', 'gained', 'lost', 'stat_changes', 'quest', 'notes'}."""
    title, old = game_status_dict(old_status)
    g = game_parse(reply)
    model_title, _x = game_status_dict(g["status"]) if g["status"] else ("", {})
    fields = game_fields(reply, extra_keys=old.keys())
    new = dict(old)
    notes: List[str] = []
    # 1. champs fournis par le modèle (sauf l'inventaire, traité à part)
    heal = bool(re.search(r"soign|stimpak|repos|dors|dormi|gu[ée]ri|bandage|m[ée]dic|r[ée]cup[èe]re|regagne|potion|soin",
                          _fold(reply)))
    fed = bool(re.search(r"\btu\s+(?:manges|devores|grignotes|engloutis|avales\s+(?:un|une|ta|ton|tes|des|le|la|les)\s+(?!gorgee))"
                         r"|\bt['’]empiffres|\btu\s+as\s+mange", _fold(reply)))
    drunk = bool(re.search(r"\btu\s+(?:bois|sirotes|te\s+desalteres|avales\s+une\s+gorgee|vides\s+ta\s+(?:bouteille|canette|flasque))"
                           r"|\bt['’]abreuves|\btu\s+as\s+bu", _fold(reply)))
    for k, v in fields.items():
        if k == "INVENTAIRE" or v.strip(" .-?") == "":
            continue
        nv, ov = _num(v), _num(old.get(k, ""))
        if nv and ov and nv[0] < ov[0] and (k == "FAIM" and not fed or k == "SOIF" and not drunk):
            continue  # le modèle recopie un vieux chiffre : la faim / soif ne baisse pas sans manger / boire
        if nv and ov and nv[0] > ov[0] and k in _HP_KEYS and not heal:
            continue  # HP qui remonte sans soin raconté = statut recopié d'un ancien tour
        new[k] = v
    hp_key = next((k for k in _HP_KEYS if k in new), "HP")
    narr = game_narrative(reply)
    # 2. inventaire
    old_inv = game_inv_list(old.get("INVENTAIRE", ""))
    inv = list(old_inv)
    gained: List[str] = []
    lost: List[str] = []
    model_inv_raw = fields.get("INVENTAIRE")
    deltas_plus, deltas_minus = [], []
    if model_inv_raw is not None:
        for part in re.split(r"\s*[,;]\s*", model_inv_raw):
            p = part.strip()
            if p.startswith("+"):
                deltas_plus.append(p[1:].strip())
            elif p[:1] in ("-", "−", "–"):
                deltas_minus.append(p[1:].strip())
    model_inv = game_inv_list(model_inv_raw) if model_inv_raw is not None else None
    changed_by_model = False
    if model_inv is not None and (model_inv or not deltas_plus and not deltas_minus):
        okeys = sorted(" ".join(game_item_words(n)) + f"#{q}" for q, n in old_inv)
        nkeys = sorted(" ".join(game_item_words(n)) + f"#{q}" for q, n in model_inv)
        if not old_inv or okeys != nkeys:
            if model_inv or not old_inv or "INVENTAIRE" in fields:
                changed_by_model = bool(old_inv) and okeys != nkeys
                for q, n in model_inv:
                    j = game_item_match(old_inv, n)
                    if j < 0:
                        gained.append(n)
                    elif q > old_inv[j][0]:
                        gained.append(f"{q - old_inv[j][0]} {n}" if q - old_inv[j][0] > 1 else n)
                for q, n in old_inv:
                    j = game_item_match(model_inv, n)
                    if j < 0:
                        lost.append(n)
                inv = list(model_inv)
    for p in deltas_plus:
        q, n = game_item_parse(p)
        j = game_item_match(inv, n)
        if j >= 0:
            inv[j] = (inv[j][0] + q, inv[j][1])
        else:
            inv.append((q, n))
        gained.append(game_item_fmt(q, n))
    for p in deltas_minus:
        q, n = game_item_parse(p)
        j = game_item_match(inv, n)
        if j >= 0:
            lost.append(inv[j][1])
            if inv[j][0] > q:
                inv[j] = (inv[j][0] - q, inv[j][1])
            else:
                inv.pop(j)
    # narration : si le modèle n'a pas lui-même tenu l'inventaire à jour
    ate, drank = fed, drunk
    stim = rad_away = 0
    if not changed_by_model:
        for ph in narr["gains"]:
            q, n = game_item_parse(ph)
            n = re.sub(r"^(?:de la |de l['’]|du |des |de |le |la |les |l['’]|ce |cet |cette |ces |ton |ta |tes )", "", n, flags=re.I).strip()
            words = game_item_words(n)
            if not words:
                continue
            if words[0] in ("capsule", "cap") and q:
                k = "CAPS"
                if k in new:
                    nv = _num(new[k])
                    if nv:
                        new[k] = str(nv[0] + q)
                        notes.append(f"+{q} CAPS")
                continue
            j = game_item_match(inv, n)
            if j >= 0:
                if q > 1 or re.match(r"^\d", ph.strip()) or any(words[0].startswith(c) for c in _CONSUMABLE):
                    inv[j] = (inv[j][0] + q, inv[j][1])
                    gained.append(game_item_fmt(q, inv[j][1]))
                continue
            n = n[:1].upper() + n[1:]
            inv.append((q, n))
            gained.append(game_item_fmt(q, n))
    for ph, use in narr["losses"]:
        j = game_item_match(inv, ph)
        if j < 0:
            continue
        q0, n0 = inv[j]
        w0 = game_item_words(n0)
        cons = any(x.startswith(c) for x in w0 for c in _CONSUMABLE)
        if use and not cons:
            continue  # « tu utilises ta machette » : l'arme reste
        if changed_by_model and any(game_item_match([(1, n0)], x) == 0 for x in lost):
            continue
        qn = game_item_parse(ph)[0] if re.match(r"^\d", ph.strip()) else 1
        fn = _fold(n0)
        if any(x in fn for x in ("stimpak", "stim")):
            stim += 1
        if "radaway" in fn or "rad-away" in fn:
            rad_away += 1
        if any(x in fn for x in _FOOD):
            ate = True
        if any(x in fn for x in _DRINK):
            drank = True
        if q0 > qn:
            left = q0 - qn
            if left == 1:  # « 2 Stimpaks » → « Stimpak »
                w = n0.split(" ", 1)
                if len(w[0]) > 3 and w[0][-1:] in ("s", "x") and not w[0].endswith(("ss", "us")):
                    n0 = " ".join([w[0][:-1]] + w[1:])
            inv[j] = (left, n0)
        else:
            inv.pop(j)
        lost.append(n0)
    if inv or "INVENTAIRE" in old or model_inv_raw is not None:
        new["INVENTAIRE"] = ", ".join(game_item_fmt(q, n) for q, n in inv) if inv else "(vide)"
    # 3. jauges
    stat_changes: List[str] = []

    def bump(key: str, delta: int, why: str = ""):
        if key not in new or not delta:
            return
        nv = _num(new[key])
        if not nv:
            return
        v, mx = nv
        lim = mx if mx else (1000 if key.startswith("RAD") else 999999)
        v2 = max(0, min(lim, v + delta))
        if v2 == v:
            return
        new[key] = f"{v2}/{mx}" if mx else str(v2)
        stat_changes.append(f"{'+' if v2 > v else '−'}{abs(v2 - v)} {key}{(' (' + why + ')') if why else ''}")

    def model_moved(key: str) -> bool:
        return key in fields and new.get(key) == fields.get(key) and _num(fields.get(key, "")) is not None and \
            (_num(fields[key]) or (0,))[0] != (_num(old.get(key, "")) or (None,))[0]

    st = narr["stats"]
    for k, d in st.items():
        key = hp_key if k == "HP" else ("RAD" if k == "RAD" and "RAD" in new else ("RADS" if k == "RAD" else k))
        if key in new and not model_moved(key):
            bump(key, d)
    if stim and not model_moved(hp_key) and "HP" not in st:
        bump(hp_key, 25 * stim, "Stimpak")
    if rad_away and "RAD" in new and not model_moved("RAD"):
        bump("RAD", -50 * rad_away, "RadAway")
    if dice and dice <= 5 and hp_key in new and not model_moved(hp_key) and "HP" not in st and _WOUND.search(narr["narr"]):
        bump(hp_key, -(12 - dice), f"jet raté {dice}")
    if tick:
        for key, step, done, amount in (("FAIM", 3, ate, -30), ("SOIF", 4, drank, -35)):
            if key not in new:
                continue
            if done and not model_moved(key):
                bump(key, amount, "mange" if key == "FAIM" else "bu")
            elif not model_moved(key):
                nv = _num(new[key])
                if nv:
                    v, mx = nv
                    v2 = min(mx or 100, v + step)
                    new[key] = f"{v2}/{mx}" if mx else str(v2)
    hp = _num(new.get(hp_key, "")) if hp_key in new else None
    if hp and hp[0] <= 0:
        notes.append("☠ HP à zéro !")
    for key, warn in (("FAIM", "🍖 Tu as faim : mange quelque chose"), ("SOIF", "💧 Tu as soif : bois quelque chose")):
        nv = _num(new.get(key, "")) if key in new else None
        if nv and nv[0] >= 70:
            notes.append(warn)
    quest = (fields.get("QUÊTE") or narr["quest"] or "").strip()
    if narr["quest"] and not fields.get("QUÊTE"):
        new["QUÊTE"] = narr["quest"]
    status = game_status_text(model_title or title, new, old_status) if new else (g["status"] or old_status)
    # dédoublonnage des listes
    def uniq(xs):
        seen, out = set(), []
        for x in xs:
            k = " ".join(game_item_words(x))
            if k and k not in seen:
                seen.add(k)
                out.append(x)
        return out
    return {"status": status, "gained": uniq(gained), "lost": uniq(lost), "stat_changes": stat_changes,
            "quest": quest, "notes": notes}


def game_state_line(status: str) -> str:
    """Rappel compact de l'état réel, envoyé au maître du jeu à chaque tour (pas gardé dans l'historique)."""
    title, d = game_status_dict(status)
    if not d:
        return ""
    parts = [f"{k}: {v}" for k, v in d.items() if k not in ("SPECIAL",)]
    return ("\n\n[ÉTAT ACTUEL DU PIP-BOY (vérité du jeu) — " + " · ".join(parts)[:900]
            + ". Recopie ce statut dans ton bloc ▓▓ en le METTANT À JOUR selon ce qui arrive "
              "(INVENTAIRE complet : ajoute ce que je ramasse, retire ce que j'utilise; chiffres HP/RAD/CAPS/FAIM/SOIF changés si raconté).]")


def game_dice_hint(dice: int) -> str:
    if not dice:
        return ""
    if dice <= 5:
        h = "échec grave : si l'action est risquée, vraie conséquence chiffrée (ex. « tu perds 12 HP », un objet perdu)"
    elif dice <= 10:
        h = "échec : petit coût chiffré (ex. « tu perds 5 HP » ou du temps)"
    elif dice <= 15:
        h = "réussite"
    elif dice <= 19:
        h = "belle réussite : petit bonus (objet, info ou CAPS)"
    else:
        h = "CRITIQUE : récompense mémorable"
    return f" [JET d20 = {dice} → {h}]"


def _status_kv_known(line: str) -> bool:
    s = _gline_clean(line)
    m = _GKV_LINE.match(s.split("|")[0].strip()) if s else None
    return bool(m) and game_norm_key(m.group(1)) in _GKEY_KNOWN


def game_status_span(lines: List[str], i: int) -> int:
    """Fin (exclue) d'un statut ▓▓ hors bloc commençant à la ligne i : tolère les lignes vides
    si la suite est encore une clé connue (INVENTAIRE après une ligne vide, etc.)."""
    j = i + 1
    while j < len(lines):
        s = lines[j]
        if not s.strip():
            k = j + 1
            while k < len(lines) and not lines[k].strip():
                k += 1
            if k < len(lines) and _status_kv_known(lines[k]) and not _CHOICE_RE.match(lines[k]):
                j = k
                continue
            break
        if _CHOICE_RE.match(s) or not (_KV_RE.search(s) or _status_kv_known(s)):
            break
        j += 1
    return j


_TEMPLATE_LINES = re.compile(r"^\s*(?:\(?narration et dialogues\.?\)?|\(?un mot de la liste\)?|mets 3 [àa] 5 choix.*|"
                             r"rien apr[èe]s le dernier choix\.?|\*\*\s*[ée]tat mis [àa] jour\s*\*\*\s*:?)\s*$", re.I)


def game_strip_template(text: str) -> str:
    """Le petit modèle recopie parfois des bouts du gabarit (« Narration et dialogues. », « Mets 3 à 5 choix… »)."""
    return "\n".join(l for l in (text or "").split("\n") if not _TEMPLATE_LINES.match(l))


# ── v39.4: 📰 Nouvelles — briefings sourcés (vraie chasse web, sources datées) ─────
BRIEF_DIR = os.path.join(PROMPTS_DIR, "briefings")

NEWS_GEO_TEXT = "\n".join([
    "Tu es VESNA ORLOV-TREMBLAY, géopoliticologue de l'an 2077. Depuis le futur, tu relis notre présent comme une archive : "
    "tu sais quelles nouvelles comptaient vraiment et lesquelles n'étaient que du bruit. Tu tutoies Marc (Québec), "
    "en français québécois clair, ton posé, lucide, un brin ironique. Sujet demandé : {question}.",
    "",
    "MÉTHODE (non négociable)",
    "- Les FAITS viennent UNIQUEMENT des SOURCES de la chasse, cités avec leur numéro [n] et leur date. "
    "Aucun fait, chiffre, nom ou date inventé : pas de source = tu ne l'affirmes pas.",
    "- Tu sépares toujours 📌 les faits sourcés et 🔮 ta lecture du futur (interprétation clairement marquée).",
    "- Plusieurs angles : Occident, Russie et Chine, Sud global, acteurs locaux. Aucune propagande, d'aucun bord; "
    "si une source est un média d'État ou partisan, tu le dis.",
    "- Probabilités honnêtes, jamais de certitudes. Si les sources sont minces sur une région, dis-le en une ligne et passe.",
    "- Pas d'URL dans le texte (Padawan ajoute les sources datées à la fin).",
    "",
    "FORMAT (markdown, en français)",
    "## 🌍 Briefing géopolitique — (période) · vu de 2077",
    "Une phrase d'ouverture, en italique, écrite depuis 2077.",
    "### 🔥 Les 3 points chauds",
    "- une ligne par point chaud, avec [n]",
    "Puis 4 à 6 sujets, par région où il y a des sources (🇪🇺 Europe & Russie, 🕌 Moyen-Orient, 🌏 Asie-Pacifique, "
    "🌍 Afrique, 🌎 Amériques, 🍁 Canada & Québec) :",
    "### (emoji) Région — Sujet précis   (pour CHAQUE sujet, les 6 puces suivantes)",
    "- **📌 Faits** : 2 à 4 faits sourcés [n] (date)",
    "- **🎭 Acteurs & intérêts** : qui veut quoi, et pourquoi",
    "- **🙈 Ce que les grands médias disent peu** : angle mort, contexte oublié (🔮 interprétation)",
    "- **🎲 Scénarios** : probable (~ %), possible (~ %), cygne noir (~ %)",
    "- **📡 Signaux faibles** : 2 indices concrets à surveiller",
    "- **🎯 Confiance** : ●●●○○ (faible / moyenne / élevée) — pourquoi",
    "### 🧭 Le mot de 2077",
    "2 à 4 phrases : ce que l'histoire retiendra de cette période (🔮 interprétation assumée).",
])

NEWS_DISC_TEXT = "\n".join([
    "Tu es le CURATEUR DES DÉCOUVERTES de Padawan : un scientifique curieux et rigoureux qui raconte à Marc (Québec), "
    "en le tutoyant, les avancées qui font dire « wow », dans toutes les sphères. Français québécois clair, enthousiaste "
    "mais jamais crédule. Domaine ciblé : {question}.",
    "",
    "RÈGLES",
    "- Chaque découverte vient UNIQUEMENT des SOURCES de la chasse, citée avec son numéro [n] et sa date. Rien d'inventé : "
    "aucun chiffre, nom de revue, de chercheur ou d'entreprise absent des sources.",
    "- Niveau de preuve honnête : 🧪 préprint (pas encore révisé), 📄 étude publiée (revue révisée par les pairs), "
    "📣 annonce d'entreprise ou communiqué, 📰 reportage seulement. Si la source ne le dit pas : « preuve : non précisée ».",
    "- Prudence : souris ≠ humains, petit échantillon, pas encore reproduit, promesse marketing… dis-le.",
    "- Médecine & santé : inclus aussi la médecine régénératrice et les approches naturelles quand les sources en parlent, "
    "avec la même exigence de preuve.",
    "- Ne retiens QUE les sources qui annoncent vraiment une découverte ou une avancée (étude, mesure, fouille, "
    "observation, prototype, essai). IGNORE expositions, prix, partenariats, opinions, valorisations boursières.",
    "- Le « Quoi » reformule fidèlement le titre et l'extrait de la source, sans rien ajouter.",
    "- 6 à 10 découvertes, regroupées par domaine; saute un domaine sans source. Pas d'URL dans le texte.",
    "",
    "FORMAT (markdown, en français)",
    "## 🔭 Découvertes & avancées — (période)",
    "Une phrase d'accroche en italique.",
    "### 🏆 La plus wow",
    "**Nom de la découverte** — 2 phrases [n]",
    "Puis par domaine (🤖 Tech & IA, ⚛️ Science & physique, 🧬 Médecine & santé, 🏺 Archéologie & histoire, 🚀 Espace, "
    "🌿 Environnement & nature, ⚡ Énergie) :",
    "### (emoji) Domaine",
    "**Nom de la découverte**   (pour CHAQUE découverte, les 4 puces suivantes)",
    "- **Quoi** : ce qui a été trouvé ou construit [n] (date)",
    "- **Pourquoi ça compte** : l'impact concret",
    "- **Preuve** : 🧪 / 📄 / 📣 / 📰 + la prudence qui va avec",
    "- **Wow** : 🤯🤯🤯○○ (3/5) — en quelques mots, pourquoi cette note",
    "### 🔮 À surveiller",
    "2 ou 3 pistes qui pourraient avoir une suite.",
])

NEWS_SEEDS: List[Dict[str, Any]] = [
    {"name": "🌍 Géopoliticologue du futur", "role": "chercheur", "mode": "remplacer", "kind": "normal",
     "keep_base": False, "text": NEWS_GEO_TEXT, "builtin": "geo_futur"},
    {"name": "🔭 Découvertes & avancées", "role": "chercheur", "mode": "remplacer", "kind": "normal",
     "keep_base": False, "text": NEWS_DISC_TEXT, "builtin": "decouvertes"},
]

NEWS_KINDS: Dict[str, Dict[str, Any]] = {
    "geo_futur": {
        "label": "🌍 Briefing géopolitique", "default_q": "la géopolitique mondiale",
        "queries": [
            ("Ukraine Russie guerre", "fr-fr", "Europe & Russie"), ("Russia Ukraine war", "us-en", "Europe & Russie"),
            ("Israël Gaza Liban Iran", "fr-fr", "Moyen-Orient"), ("Middle East Iran Israel", "us-en", "Moyen-Orient"),
            ("Chine Taïwan États-Unis", "fr-fr", "Asie-Pacifique"), ("China Taiwan US", "us-en", "Asie-Pacifique"),
            ("Afrique Sahel Soudan conflit", "fr-fr", "Afrique"), ("Union européenne OTAN défense", "fr-fr", "Europe & Russie"),
            ("Amérique latine Venezuela Brésil", "fr-fr", "Amériques"), ("Inde Pakistan géopolitique", "fr-fr", "Asie-Pacifique"),
            ("sanctions tarifs commerce mondial", "fr-fr", "Économie mondiale"), ("Canada relations internationales", "fr-fr", "Canada & Québec"),
        ],
        "focus": [("{q} actualité", "fr-fr", "{q}"), ("{q} news", "us-en", "{q}"),
                  ("{q} analyse géopolitique", "fr-fr", "{q}"), ("{q} tensions", "us-en", "{q}")],
    },
    "decouvertes": {
        "label": "🔭 Découvertes & avancées", "default_q": "tous les domaines",
        "queries": [
            ("AI researchers new model breakthrough", "us-en", "Tech & IA"),
            ("chercheurs intelligence artificielle nouvelle méthode", "fr-fr", "Tech & IA"),
            ("physicists discover", "us-en", "Science & physique"),
            ("scientists discover study published", "us-en", "Science & physique"),
            ("new study treatment patients trial results", "us-en", "Médecine & santé"),
            ("regenerative medicine stem cell study", "us-en", "Médecine & santé"),
            ("chercheurs découvrent traitement étude", "fr-fr", "Médecine & santé"),
            ("natural compound plant study health benefits", "us-en", "Médecine & santé"),
            ("archaeologists discover", "us-en", "Archéologie & histoire"),
            ("archéologues ont découvert", "fr-fr", "Archéologie & histoire"),
            ("astronomers discover", "us-en", "Espace"), ("James Webb telescope discovery", "us-en", "Espace"),
            ("new species discovered scientists", "us-en", "Environnement & nature"),
            ("battery breakthrough researchers", "us-en", "Énergie"), ("fusion energy record", "us-en", "Énergie"),
        ],
        "focus": [("{q} découverte", "fr-fr", "{q}"), ("{q} breakthrough", "us-en", "{q}"),
                  ("{q} nouvelle étude", "fr-fr", "{q}"), ("{q} researchers new study", "us-en", "{q}")],
    },
}
NEWS_TITLE_JUNK = {
    "decouvertes": re.compile(r"exposition|partenariat|award|recogni[sz]ed|of the year|valorisation|stock|shares|bourse|"
                              r"webinar|promo|horoscope|soldes|black friday|concert|festival|recette|deal|market|marché|investment|"
                              r"investissement|free trade|officers|ceo\b|earnings|résultats financiers|climbs|slides|dips|notes\b|"
                              r"\breview\b|essai routier|rival tested", re.I),
}
NEWS_PERIODS = {"d": "dernières 24 h", "w": "cette semaine", "m": "ce mois-ci"}
NEWS_MAX_SOURCES = 15
NEWS_GEN_OPTIONS = {"num_predict": 2400, "temperature": 0.45, "repeat_penalty": 1.1}


def _news_date(s: str) -> str:
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(s or ""))
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""


def _news_date_fr(iso: str) -> str:
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", iso or "")
    if not m:
        return "date ?"
    return f"{int(m.group(3))} {MOIS_FR[int(m.group(2)) - 1]} {m.group(1)}"


_NEWS_JUNK = re.compile(r"wikipedia\.org|/tag/|/tags/|/topics?/|/live-?map|tracker|/category/|/rubrique/|/search|youtube\.com|"
                        r"facebook\.com|instagram\.com|tiktok\.com|x\.com/|twitter\.com", re.I)


def _url_date(url: str) -> str:
    m = re.search(r"(20\d\d)[/-](0[1-9]|1[0-2])[/-]([0-2]\d|3[01])(?!\d)", url or "")
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.search(r"(?<!\d)(20\d\d)(0[1-9]|1[0-2])([0-2]\d|3[01])(?!\d)", url or "")
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""


def _news_row(row: dict, timelimit: str = "", is_news: bool = True) -> Optional[Dict[str, str]]:
    it = _norm_row(row)
    if not it or _NEWS_JUNK.search(it["url"]):
        return None
    path = urlparse(it["url"]).path.strip("/")
    if not is_news and (path.count("/") < 1 and len(path) < 25):
        return None  # page d'accueil / rubrique, pas un article
    # date : celle de l'URL d'abord (fiable), sinon celle du moteur si elle tombe dans la fenêtre demandée,
    # sinon « ≤ 24 h / ≤ 7 jours » (le filtre de temps du moteur est appliqué côté serveur)
    ud, ed = _url_date(it["url"]), _news_date(row.get("date") or "")
    win = {"d": 2, "w": 8, "m": 32}.get(timelimit, 0)
    pd = ud
    if not pd and ed and win:
        try:
            age = (datetime.now() - datetime.strptime(ed, "%Y-%m-%d")).days
            pd = ed if -1 <= age <= win else ""
        except Exception:
            pd = ""
    elif not pd and ed and not win:
        pd = ed
    it["pubdate"] = pd
    it["pubhint"] = "" if pd else ({"d": "≤ 24 h", "w": "≤ 7 jours", "m": "≤ 1 mois"}.get(timelimit, "") if is_news else "")
    it["outlet"] = clean(str(row.get("source") or "") or host_of(it["url"]))[:60]
    it["snippet"] = clean(row.get("body") or "")[:230]
    it["_news"] = True
    return it


def news_fetch_one(qtext: str, region: str, timelimit: str, n: int = 6,
                   cancel: Optional[threading.Event] = None, errors: Optional[List[str]] = None) -> List[Dict[str, str]]:
    """Une requête DDGS news datée (repli : texte avec limite de temps)."""
    if not DDGS or (cancel and cancel.is_set()):
        return []
    out: List[Dict[str, str]] = []
    for be in ("bing", "auto", "duckduckgo"):
        if cancel and cancel.is_set():
            break
        try:
            raw = list(DDGS().news(qtext, region=region, timelimit=timelimit, max_results=n, backend=be) or [])
        except Exception as e:
            if errors is not None:
                errors.append(f"news/{be}: {_short_exc(e)}")
            continue
        out = [x for x in (_news_row(r, timelimit, True) for r in raw) if x]
        if out:
            break
    if not out:
        try:
            raw = list(DDGS().text(qtext, region=region, timelimit=timelimit, max_results=n, backend="auto") or [])
            out = [x for x in (_news_row(r, timelimit, False) for r in raw) if x]
        except Exception as e:
            if errors is not None:
                errors.append(f"text: {_short_exc(e)}")
    return out


def news_collect(kind: str, period: str = "d", question: str = "", cancel: Optional[threading.Event] = None,
                 on_progress: Optional[Callable[[str], None]] = None, per_query: int = 2,
                 max_sources: int = NEWS_MAX_SOURCES, read_top: int = 5) -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
    """Chasse multi-requêtes en parallèle (régions FR + EN), dédoublonnée, triée par date, top pages lues."""
    spec = NEWS_KINDS[kind]
    tl = period if period in NEWS_PERIODS else "d"
    q = (question or "").strip()
    if q:
        queries = [(a.format(q=q), r, t.format(q=q)) for a, r, t in spec["focus"]]
        per_query = max(per_query, 4)
    else:
        queries = list(spec["queries"])
    meta: Dict[str, Any] = {"queries": [a for a, _r, _t in queries], "errors": [], "period": tl, "widened": False}
    buckets: Dict[int, List[Dict[str, str]]] = {}

    def run(tl_now: str):
        with ThreadPoolExecutor(max_workers=6) as ex:
            futs = {ex.submit(news_fetch_one, a, r, tl_now, 6, cancel, meta["errors"]): i
                    for i, (a, r, _t) in enumerate(queries)}
            for f in as_completed(futs):
                try:
                    buckets[futs[f]] = f.result() or []
                except Exception as e:
                    meta["errors"].append(str(e)[:80])
                if on_progress:
                    on_progress(f"{len(buckets)}/{len(queries)} requêtes")

    run(tl)
    if sum(len(v) for v in buckets.values()) < 4 and tl == "d" and not (cancel and cancel.is_set()):
        meta["widened"] = True  # trop peu en 24 h : on élargit à la semaine
        buckets.clear()
        run("w")
    seen_u, seen_t, picked = set(), set(), []
    rounds = [sorted(buckets.get(i, []), key=lambda x: x.get("pubdate") or "", reverse=True) for i in range(len(queries))]
    for depth in range(per_query + 2):
        for qi, lst in enumerate(rounds):
            if depth >= len(lst):
                continue
            it = lst[depth]
            tk = re.sub(r"\W+", " ", _fold(it.get("title", ""))).strip()[:60]
            if it["url"] in seen_u or tk in seen_t:
                continue
            if depth >= per_query and len(picked) >= max_sources * 2 // 3:
                continue
            seen_u.add(it["url"])
            seen_t.add(tk)
            it["tag"] = queries[qi][2]
            picked.append(it)
        if len(picked) >= max_sources:
            break
    junk = NEWS_TITLE_JUNK.get(kind)
    if junk:
        picked = [x for x in picked if not junk.search(x.get("title", ""))]
    picked = picked[:max_sources]
    order = []
    for _a, _r, t in queries:
        if t not in order:
            order.append(t)
    picked.sort(key=lambda x: order.index(x.get("tag")) if x.get("tag") in order else 99)  # groupé par région / domaine
    # lire les premières pages (contexte réel, pas seulement les titres)
    if read_top and picked and not (cancel and cancel.is_set()):
        if on_progress:
            on_progress(f"lecture de {min(read_top, len(picked))} pages…")
        with ThreadPoolExecutor(max_workers=5) as ex:
            tgt, seen_tag = [], set()
            for it in picked:  # une page par région / domaine d'abord
                if it.get("tag") not in seen_tag:
                    seen_tag.add(it.get("tag"))
                    tgt.append(it)
            tgt = (tgt + [x for x in picked if x not in tgt])[:read_top]
            futs = {ex.submit(read_page, it["url"], 1800): it for it in tgt}
            for f in as_completed(futs):
                try:
                    body = f.result() or ""
                except Exception:
                    body = ""
                if len(body) > 120:
                    futs[f]["body"] = body[:520]
    meta["n"] = len(picked)
    return picked, meta


def news_item_date(it: Dict[str, str]) -> str:
    if it.get("pubdate"):
        return _news_date_fr(it["pubdate"])
    return it.get("pubhint") or "date non indiquée"


def news_format_part(text: str) -> str:
    """La partie FORMAT du prompt (rappelée à la fin du message : le petit modèle suit mieux)."""
    m = re.search(r"^FORMAT\b.*$", text or "", re.M)
    return (text or "")[m.start():].strip() if m else ""


def news_user_msg(kind: str, items: List[Dict[str, str]], period: str, question: str = "",
                  prev: Optional[Dict[str, Any]] = None, widened: bool = False, fmt: str = "") -> str:
    spec = NEWS_KINDS[kind]
    today = _today_fr()[0]
    per = NEWS_PERIODS.get(period, period)
    if widened:
        per += " (peu de nouvelles en 24 h : élargi à la semaine)"
    lines = [f"BRIEFING : {spec['label']} · période : {per} · date du jour : {today}.",
             f"Sujet : {question or spec['default_q']}.", ""]
    if prev and prev.get("text"):
        old = re.sub(r"\*\*Sources\*\*[\s\S]*$", "", prev["text"]).strip()
        heads = [l for l in old.split("\n") if l.startswith(("#", "- ", "**"))][:28]
        lines += [f"BRIEFING PRÉCÉDENT ({prev.get('date', '?')}) — résumé :", "\n".join(heads)[:1600], "",
                  "MODE « CE QUI A CHANGÉ » : commence par la section « ### 🔄 Ce qui a changé depuis le "
                  f"{prev.get('date', 'dernier briefing')} » avec 3 à 6 puces : 🆕 nouveau, 📈 ça s'aggrave ou avance, "
                  "📉 ça se calme ou recule, ✅ réglé. Appuie chaque puce sur les SOURCES ci-dessous [n]. Ensuite le format habituel, "
                  "plus court sur ce qui n'a pas bougé.", ""]
    lines.append("SOURCES DE CETTE CHASSE (les SEULES informations factuelles permises) :")
    for i, it in enumerate(items, 1):
        d = news_item_date(it)
        tag = f"{it['tag']} · " if it.get("tag") else ""
        lines.append(f"[{i}] ({tag}{d} · {it.get('outlet') or host_of(it.get('url', ''))}) {it.get('title', '')}")
        if it.get("snippet"):
            lines.append(f"    {it['snippet']}")
        if it.get("body"):
            lines.append(f"    [extrait] {it['body']}")
    lines += ["", "CONSIGNES : suis ton FORMAT. Cite [n] juste après chaque fait, avec la date. N'utilise QUE ces sources pour les "
              "faits; tes interprétations sont marquées 🔮. Si une source est vieille, floue ou partisane, dis-le. "
              "Aucune URL. N'écris PAS de section Sources : Padawan l'ajoute."]
    if fmt:
        lines += ["", "RAPPEL — suis ce " + fmt[:1800], "",
                  "Commence directement par le titre ##. Remplace « (période) » par : " + per + "."]
        if kind == "decouvertes":
            lines.append("Au moins 6 découvertes si les sources le permettent. Chaque découverte DOIT citer [n] et avoir ses 4 puces "
                         "(Quoi, Pourquoi ça compte, Preuve, Wow X/5). "
                         "La plus wow = la plus surprenante scientifiquement (pas une étude d'affaires).")
        else:
            lines.append("Chaque sujet DOIT avoir ses 6 puces (Faits, Acteurs, Ce que les médias disent peu, Scénarios, "
                         "Signaux faibles, Confiance). Classe chaque sujet dans la région indiquée par sa source.")
    return "\n".join(lines)


_NEWS_STOP = {"cette", "selon", "entre", "aussi", "comme", "leurs", "avoir", "était", "etait", "pourrait", "pourraient",
              "nouvelle", "nouveau", "nouvelles", "about", "their", "there", "which", "would", "could", "after", "before",
              "while", "these", "those", "being", "where", "first", "years", "année", "annee", "depuis", "toute", "toutes",
              "encore", "contre", "monde", "world", "people", "study", "étude", "etude", "researchers", "chercheurs",
              "scientists", "scientifiques", "découverte", "decouverte", "discover", "discovered", "novembre", "november"}


def _news_stems(text: str) -> set:
    f = _fold(text)
    out = set()
    for w in re.findall(r"[a-z0-9]{5,}", f):
        if w in _NEWS_STOP:
            continue
        out.add(w[:6])
    for nmb in re.findall(r"\d[\d.,]*\d|\d", f):
        if len(nmb) >= 2:
            out.add("#" + nmb.replace(",", "."))
    return out


def news_flag_unsupported(text: str, items: List[Dict[str, str]]) -> str:
    """Garde-fou anti-invention : un bloc (titre + puces) qui cite [n] mais ne partage presque aucun mot
    avec la source n reçoit « ⚠ à vérifier »."""
    src = {i: _news_stems(" ".join([it.get("title", ""), it.get("snippet", ""), it.get("body", "")]))
           for i, it in enumerate(items, 1)}
    lines = text.split("\n")
    blocks: List[List[int]] = []
    cur: List[int] = []
    for k, line in enumerate(lines):
        if re.match(r"^\s*(?:#{2,4}\s|\*\*[^*]+\*\*\s*(?:—|-|:|$))", line) and cur:
            blocks.append(cur)
            cur = []
        cur.append(k)
    if cur:
        blocks.append(cur)
    flagged = 0
    for b in blocks:
        body = "\n".join(lines[k] for k in b)
        nums = sorted({int(x) for x in re.findall(r"\[(\d{1,2})\]", body) if int(x) in src})
        mine = _news_stems(re.sub(r"\[\d+\]", " ", body))
        if not mine:
            continue
        if not nums:  # le modèle a oublié [n] : on rattache le bloc à la source qui lui ressemble le plus
            if not re.search(r"\*\*\s*(?:quoi|📌)", _fold(body)) and not re.match(r"^\s*\*\*[^*]+\*\*", lines[b[0]]):
                continue
            sc = sorted(((len(mine & st), i) for i, st in src.items()), reverse=True)
            if sc and sc[0][0] >= 3:
                h = b[0]
                lines[h] = lines[h].rstrip() + f" [{sc[0][1]}]"
            continue
        best = max(len(mine & src[x]) for x in nums)
        if best < 2:
            last = max(k for k in b if lines[k].strip())
            lines[last] = lines[last].rstrip() + "  ⚠ _à vérifier : la source citée ne semble pas dire ça_"
            flagged += 1
    return "\n".join(lines)


def news_postprocess(ans: str, items: List[Dict[str, str]]) -> Tuple[str, List[int]]:
    """Retire URLs et section Sources du modèle, enlève les [n] hors liste, ajoute les sources datées citées."""
    t = clean(ans or "").strip()
    t = _strip_sources_section(t)
    t = re.sub(r"\n\s*(?:#+\s*)?\**\s*Sources?\s*\**\s*:?\s*\n[\s\S]*$", "", t).rstrip()
    t = re.sub(r"\(?https?://\S+\)?", "", t)
    n = len(items)

    def fix(m):
        nums = [int(x) for x in re.findall(r"\d+", m.group(0))]
        keep = [x for x in nums if 1 <= x <= n]
        return "".join(f"[{x}]" for x in keep)
    t = re.sub(r"\[(\d{1,2})(?:\s*[,;\]\[]\s*\d{1,2})*\]", fix, t)
    t = news_flag_unsupported(t, items)
    cited = sorted({int(x) for x in re.findall(r"\[(\d{1,2})\]", t) if 1 <= int(x) <= n})
    show = cited if len(cited) >= 3 else list(range(1, n + 1))
    lines = ["**Sources** (chasse web du " + _today_fr()[0] + ")"]
    for i in show:
        it = items[i - 1]
        d = news_item_date(it)
        lines.append(f"{i}. {it.get('title', '')} — {it.get('outlet') or host_of(it.get('url', ''))} · {d}")
        lines.append(it.get("url", ""))
    return (t.rstrip() + "\n\n" + "\n".join(lines)).strip(), cited


def news_last_path(kind: str) -> str:
    return os.path.join(BRIEF_DIR, f"last_{kind}.json")


def news_save(kind: str, text: str, period: str, question: str = "") -> Tuple[str, str]:
    """Garde le briefing (.md + .html) dans briefings/ et mémorise le dernier pour « Ce qui a changé »."""
    os.makedirs(BRIEF_DIR, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M")
    slug = kind + (("_" + re.sub(r"[^a-z0-9]+", "-", _fold(question)).strip("-")[:30]) if question else "")
    base = os.path.join(BRIEF_DIR, f"{slug}_{stamp}")
    title = f"{NEWS_KINDS[kind]['label']} — {_today_fr()[0]}"
    md = f"# {title}\n\n_{NEWS_PERIODS.get(period, period)} · généré par Padawan le {_today_fr()[0]} à {time.strftime('%H:%M')}_\n\n{text}\n"
    with open(base + ".md", "w", encoding="utf-8") as fh:
        fh.write(md)
    with open(base + ".html", "w", encoding="utf-8") as fh:
        fh.write(md_to_html(md, title))
    if not question:
        savej(news_last_path(kind), {"date": f"{_today_fr()[0]} {time.strftime('%H:%M')}", "t": time.time(),
                                     "period": period, "text": text[:12000]})
    return base + ".md", base + ".html"


def news_last(kind: str) -> Optional[Dict[str, Any]]:
    p = news_last_path(kind)
    if not os.path.isfile(p):
        return None
    d = loadj(p, {})
    return d if d.get("text") else None


# ── v39.2: fenêtre 📜 Prompts (⭐ Mes prompts + 💡 Idées garées) ─────────────────
PROMPT_LOCK_BASE = "__base__"
PROMPT_LOCK_PREFIX = "__def_"


def _hex_shift(c: str, amt: float = 0.12) -> str:
    """Éclaircit (amt>0) ou assombrit (amt<0) une couleur #rrggbb — survol neutre au thème."""
    try:
        c = str(c)
        if not c.startswith("#") or len(c) != 7:
            return c
        r, g, b = int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)
        if amt >= 0:
            r, g, b = (int(v + (255 - v) * amt) for v in (r, g, b))
        else:
            r, g, b = (int(v * (1 + amt)) for v in (r, g, b))
        return f"#{r:02x}{g:02x}{b:02x}"
    except Exception:
        return c


def _fr_int(n: int) -> str:
    return f"{int(n):,}".replace(",", "\u00a0")


class PromptsWindow(tk.Toplevel):
    """Bibliothèque de prompts : liste filtrable/réordonnable + éditeur + aperçu en direct."""

    def __init__(self, app, tab: str = "prompts"):
        super().__init__(app)
        self.app = app
        self.store: PromptStore = app.prompts
        self.title("📜 Prompts · Padawan")
        self.configure(bg=C["bg"])
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w = min(sw, max(1000, int(sw * 0.84)))
        h = min(sh - 40, max(660, int(sh * 0.86)))
        self.geometry(f"{w}x{h}+{max(0, (sw - w) // 2)}+{max(0, (sh - h) // 2 - 20)}")
        self.minsize(920, 600)
        try:  # Marc aime les fenêtres maximisées (redimensionnable / restaurable)
            if os.name == "nt":
                self.state("zoomed")
        except Exception:
            pass
        try:
            ico = os.path.join(BASE, "padawan.ico")
            if os.path.isfile(ico):
                self.iconbitmap(ico)
        except Exception:
            pass
        self.cur_id = ""
        self.dirty = False
        self._loading = False
        self._prev_job = None
        self._drag = None
        self._view_ids: List[str] = []
        self._n_user_view = 0
        # petit écran (ex. portable 1366×768 à 125 %) : mise en page compacte
        self._compact = self.winfo_screenheight() < 860
        self._style()
        self._build()
        self._fill_list()
        first = self.store.active_id(app.router.active) if self.store.active_for(app.router.active) else ""
        if not first and self._view_ids:
            first = self._view_ids[0]
        if first:
            self._select_id(first)
        self.select_tab(tab)
        for seq, fn in (
            ("<Control-s>", self.save_current), ("<Control-S>", self.save_current),
            ("<Control-n>", self.new_prompt), ("<Control-N>", self.new_prompt),
            ("<Control-d>", self.duplicate), ("<Control-D>", self.duplicate),
            ("<Control-f>", self._focus_filter), ("<Control-F>", self._focus_filter),
            ("<F5>", self.test_prompt),
            ("<F6>", self._toggle_pane),
        ):
            self.bind(seq, lambda e, f=fn: (f(), "break")[1])
        self.bind("<Escape>", lambda e: self.close())
        self.protocol("WM_DELETE_WINDOW", self.close)
        self._refresh_header()
        if self.store.error:
            self._status(f"⚠ {self.store.error}", "bad")
        app._theme_fix(self)
        self.after(60, self._update_preview)
        self.after(220, self._place_sash)
        try:
            self.lift()
            self.focus_force()
        except Exception:
            pass

    # ── style / helpers ─────────────────────────────────────────────────────
    def _style(self):
        s = ttk.Style(self)
        s.configure("Prompts.TNotebook", background=C["bg"], borderwidth=0, tabmargins=(4, 6, 4, 0))
        s.configure(
            "Prompts.TNotebook.Tab", background=C["card"], foreground=C["fg"],
            padding=(16, 5) if self._compact else (22, 9),
            font=("Segoe UI", 11 if self._compact else 12, "bold"),
        )
        s.map(
            "Prompts.TNotebook.Tab",
            background=[("selected", C["gold"])], foreground=[("selected", "#1a1408")],
        )
        s.configure("Prompts.TCombobox", fieldbackground=C["card"], background=C["card"],
                    foreground=C["fg"], arrowcolor=C["gold"], padding=4)
        s.map("Prompts.TCombobox", fieldbackground=[("readonly", C["card"])],
              foreground=[("readonly", C["fg"])])
        try:
            self.option_add("*TCombobox*Listbox.font", ("Segoe UI", 11))
        except Exception:
            pass

    def _place_sash(self):
        """Partage éditeur / aperçu ~55/45 selon la hauteur réelle (aperçu toujours visible)."""
        try:
            self.update_idletasks()
            h = self.vp.winfo_height() if self.vp is not None else 0
            if self.vp is not None and h > 80:
                self.vp.sash_place(0, 1, max(120, int(h * 0.55)))
        except Exception:
            pass

    def _tip(self, w, text):
        try:
            self.app._tip(w, text)
        except Exception:
            pass

    def _btn(self, parent, text, cmd, tip="", kind="normal", size=11):
        pal = {
            "primary": (C["gold"], "#1a1408"),
            "ok": (C["ok"], "#06261a"),
            "danger": (C["card2"], C["bad"]),
            "normal": (C["card"], C["fg"]),
        }
        bg, fg = pal.get(kind, pal["normal"])
        b = tk.Button(
            parent, text=text, command=cmd, bg=bg, fg=fg, relief="flat", bd=0,
            font=("Segoe UI", size, "bold"), padx=14, pady=7, cursor="hand2",
            activebackground=C["gold"], activeforeground="#1a1408",
            disabledforeground=C["dim"], highlightthickness=0,
        )
        st = {}

        def _enter(e, btn=b):
            if str(btn.cget("state")) == "disabled":
                return
            st["bg"] = btn.cget("bg")
            btn.configure(bg=_hex_shift(st["bg"], 0.16))

        def _leave(e, btn=b):
            if "bg" in st:
                try:
                    btn.configure(bg=st.pop("bg"))
                except Exception:
                    pass

        b.bind("<Enter>", _enter)
        b.bind("<Leave>", _leave)
        if tip:
            self._tip(b, tip)
        return b

    def _lbl(self, parent, text, *, size=11, bold=True, fg=None, bg=None, **kw):
        return tk.Label(parent, text=text, bg=bg or C["bg"], fg=fg or C["fg"],
                        font=("Segoe UI", size, "bold" if bold else "normal"), **kw)

    def _status(self, msg: str, kind: str = "info"):
        col = {"ok": C["ok"], "bad": C["bad"], "warn": C["gold"]}.get(kind, C["dim"])
        try:
            self.status.config(text=msg, fg=col)
        except Exception:
            pass

    # ── construction ─────────────────────────────────────────────────────────
    def _build(self):
        # Barre d'état (bas, toujours visible)
        self.status = tk.Label(self, text="", bg=C["bg"], fg=C["dim"], font=("Segoe UI", 10),
                               anchor="w", justify="left")
        self.status.pack(side="bottom", fill="x", padx=14, pady=(0, 8))

        head = tk.Frame(self, bg=C["bg"])
        head.pack(side="top", fill="x", padx=14, pady=(6, 2) if self._compact else (12, 4))
        left = tk.Frame(head, bg=C["bg"])
        left.pack(side="left", fill="x", expand=True)
        self._lbl(left, "📜 Prompts", size=16 if self._compact else 22, fg=C["gold"]).pack(anchor="w")
        self._lbl(
            left,
            "Tes meilleurs prompts, prêts à resservir. ✅ Activer = Padawan suit ce prompt · "
            "↩ = retour au prompt d'origine · rien n'est perdu.",
            size=9 if self._compact else 10, bold=False, fg=C["dim"],
        ).pack(anchor="w")
        right = tk.Frame(head, bg=C["card"], highlightbackground=C["line"], highlightthickness=1)
        right.pack(side="right", padx=(10, 0))
        self.hdr_role = self._lbl(right, "", size=9, fg=C["dim"], bg=C["card"])
        self.hdr_role.pack(anchor="w", padx=12, pady=(6, 0))
        self.hdr_active = self._lbl(right, "", size=13, fg=C["gold"], bg=C["card"])
        self.hdr_active.pack(anchor="w", padx=12, pady=(0, 6))
        self._tip(right, "Prompt suivi par Padawan pour le rôle sélectionné dans la fenêtre principale.")

        self.nb = ttk.Notebook(self, style="Prompts.TNotebook")
        self.nb.pack(fill="both", expand=True, padx=10, pady=(4, 6))
        self.tab_p = tk.Frame(self.nb, bg=C["bg"])
        self.tab_i = tk.Frame(self.nb, bg=C["bg"])
        self.nb.add(self.tab_p, text="  ⭐ Mes prompts  ")
        self.nb.add(self.tab_i, text=self._ideas_tab_label())
        self._build_prompts_tab(self.tab_p)
        self._build_ideas_tab(self.tab_i)

    def _ideas_tab_label(self) -> str:
        n = len(self.app.mem.get("inbox") or [])
        return f"  💡 Idées garées ({n})  " if n else "  💡 Idées garées  "

    def select_tab(self, tab: str):
        try:
            self.nb.select(self.tab_i if tab in ("idees", "inbox") else self.tab_p)
        except Exception:
            pass

    def _build_prompts_tab(self, root):
        pw = tk.PanedWindow(root, orient="horizontal", bg=C["line"], sashwidth=6,
                            bd=0, sashrelief="flat")
        pw.pack(fill="both", expand=True, pady=(6, 0))

        # ---- gauche : liste
        L = tk.Frame(pw, bg=C["bg"])
        pw.add(L, minsize=260, width=320 if self._compact else 380)
        self._lbl(L, "MES PROMPTS", size=9, fg=C["dim"]).pack(anchor="w", padx=(4, 0), pady=(2, 3))
        frow = tk.Frame(L, bg=C["input"], highlightbackground=C["line"], highlightthickness=1)
        frow.pack(fill="x", padx=(2, 8))
        self._lbl(frow, "🔎", size=12, bold=False, bg=C["input"]).pack(side="left", padx=(8, 2))
        self.fvar = tk.StringVar()
        self.filter_ent = self.app._make_entry(frow, self.fvar, font_size=12)
        self.filter_ent.configure(highlightthickness=0)
        self.filter_ent.pack(side="left", fill="x", expand=True, ipady=5, padx=(0, 4))
        self._tip(self.filter_ent, "Filtrer par nom ou par texte (Ctrl+F)")
        clr = tk.Label(frow, text="✕", bg=C["input"], fg=C["dim"], font=("Segoe UI", 11, "bold"),
                       cursor="hand2", padx=6)
        clr.pack(side="right")
        clr.bind("<Button-1>", lambda e: (self.fvar.set(""), self.filter_ent.focus_set()))
        self._tip(clr, "Effacer le filtre")
        self.fvar.trace_add("write", lambda *a: self._fill_list(keep=True))

        rrow = tk.Frame(L, bg=C["bg"])
        rrow.pack(fill="x", padx=(2, 8), pady=(6, 4))
        self._lbl(rrow, "Rôle :", size=10, fg=C["dim"]).pack(side="left")
        self.rfilter = tk.StringVar(value="Tous les rôles")
        cb = ttk.Combobox(rrow, textvariable=self.rfilter, state="readonly", width=16,
                          style="Prompts.TCombobox", font=("Segoe UI", 11),
                          values=["Tous les rôles"] + [PROMPT_ROLE_LABELS[r] for r in PROMPT_ROLES[1:]])
        cb.pack(side="left", padx=6)
        cb.bind("<<ComboboxSelected>>", lambda e: self._fill_list(keep=True))
        self._tip(cb, "Montrer seulement les prompts utilisables par ce rôle")

        lwrap = tk.Frame(L, bg=C["panel"], highlightbackground=C["line"], highlightthickness=1)
        lwrap.pack(fill="both", expand=True, padx=(2, 8))
        self.lb = tk.Listbox(
            lwrap, bg=C["panel"], fg=C["fg"], selectbackground=C["gold"], selectforeground="#1a1408",
            font=("Segoe UI", 12), activestyle="none", relief="flat", bd=0, highlightthickness=0,
            exportselection=False, height=8,
        )
        lsb = ttk.Scrollbar(lwrap, orient="vertical", command=self.lb.yview, style="Gold.Vertical.TScrollbar")
        self.lb.configure(yscrollcommand=lsb.set)
        self.lb.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)
        lsb.pack(side="right", fill="y")
        self.lb.bind("<<ListboxSelect>>", self._on_select)
        self.lb.bind("<ButtonPress-1>", self._drag_start, add="+")
        self.lb.bind("<B1-Motion>", self._drag_motion)
        self.lb.bind("<ButtonRelease-1>", self._drag_end, add="+")
        self.lb.bind("<Double-Button-1>", lambda e: self.activate())
        self.lb.bind("<Delete>", lambda e: self.delete())
        self.lb.bind("<Control-Up>", lambda e: (self.move(-1), "break")[1])
        self.lb.bind("<Control-Down>", lambda e: (self.move(1), "break")[1])

        mrow = tk.Frame(L, bg=C["bg"])
        mrow.pack(fill="x", padx=(2, 8), pady=(6, 2))
        self._btn(mrow, "↑", lambda: self.move(-1), "Monter le prompt (Ctrl+↑) — ou glisse-le avec la souris",
                  size=12).pack(side="left")
        self._btn(mrow, "↓", lambda: self.move(1), "Descendre le prompt (Ctrl+↓)", size=12).pack(side="left", padx=4)
        self.count_lbl = self._lbl(mrow, "", size=9, bold=False, fg=C["dim"])
        self.count_lbl.pack(side="left", padx=8)
        self._btn(mrow, "➕ Nouveau", self.new_prompt, "Nouveau prompt vide (Ctrl+N)", kind="primary").pack(side="right")
        self._lbl(
            L, "⭐ actif   🔒 prompt d'origine (lecture seule)\nDouble-clic = activer · glisser = réordonner",
            size=9, bold=False, fg=C["dim"], justify="left",
        ).pack(anchor="w", padx=(4, 0), pady=(2, 4))

        # ---- droite : éditeur
        R = tk.Frame(pw, bg=C["bg"])
        pw.add(R, minsize=520 if self._compact else 560)

        # boutons (bas, toujours visibles)
        bgrid = tk.Frame(R, bg=C["bg"])
        bgrid.pack(side="bottom", fill="x", padx=(10, 4), pady=(4, 0) if self._compact else (6, 2))
        specs = [
            ("save", "💾 Enregistrer", self.save_current, "Enregistrer les changements (Ctrl+S)", "primary"),
            ("act", "✅ Activer", self.activate,
             "Padawan suit ce prompt dès la prochaine question.\n"
             "Rôle « Tous » = actif pour les 4 rôles; sinon pour son rôle seulement.", "ok"),
            ("test", "🧪 Tester", self.test_prompt,
             "Pose la question test dans le chat de Padawan avec CE texte (même pas enregistré) — F5", "normal"),
            ("new", "➕ Nouveau", self.new_prompt, "Nouveau prompt vide (Ctrl+N)", "normal"),
            ("dup", "📄 Dupliquer", self.duplicate,
             "Copie modifiable de ce prompt (Ctrl+D).\nSur un 🔒 défaut : pars du prompt d'origine.", "normal"),
            ("del", "🗑 Supprimer", self.delete, "Supprimer ce prompt (confirmation; copie gardée dans le .bak)", "danger"),
            ("reset", "↩ Revenir au défaut", self.reset_default,
             "Tous les rôles reprennent le prompt d'origine de Padawan.\n"
             "(Pour un seul rôle : bouton 📜 à côté des rôles, ou activer son 🔒 Défaut.)", "normal"),
            ("imp", "📥 Importer", self.import_prompts, "Importer un .txt (un prompt) ou un .json (plusieurs)", "normal"),
            ("exp", "📤 Exporter", self.export_prompts,
             "Exporter tous tes prompts (.json) ou le prompt affiché (.txt)", "normal"),
            ("gen", "✨ Générer un jeu", lambda: self.app.game_generate(self),
             "Padawan écrit un prompt de 🎮 jeu complet à partir d'une idée en une ligne", "normal"),
        ]
        self.btns = {}
        if self._compact:  # 2 rangées : actions principales / gestion
            order = {"save": (0, 0, 6), "act": (0, 6, 6), "test": (0, 12, 6), "reset": (0, 18, 6),
                     "new": (1, 0, 4), "dup": (1, 4, 4), "del": (1, 8, 4), "imp": (1, 12, 4), "exp": (1, 16, 4),
                     "gen": (1, 20, 4)}
            for key, text, cmd, tip, kind in specs:
                b = self._btn(bgrid, text, cmd, tip, kind=kind, size=10)
                b.configure(pady=4, padx=8)
                r_, c_, span = order[key]
                b.grid(row=r_, column=c_, columnspan=span, sticky="ew", padx=2, pady=2)
                self.btns[key] = b
            for c in range(24):
                bgrid.columnconfigure(c, weight=1, uniform="pbtn")
        else:
            for i, (key, text, cmd, tip, kind) in enumerate(specs):
                b = self._btn(bgrid, text, cmd, tip, kind=kind)
                b.grid(row=i // 3, column=i % 3, sticky="ew", padx=3, pady=3)
                self.btns[key] = b
            for c in range(3):
                bgrid.columnconfigure(c, weight=1, uniform="pbtn")

        trow = tk.Frame(R, bg=C["bg"])
        trow.pack(side="bottom", fill="x", padx=(10, 4), pady=(2, 0) if self._compact else (4, 0))
        self._lbl(trow, "🧪 Question test :", size=10, fg=C["dim"]).pack(side="left")
        self.qvar = tk.StringVar(value=PROMPT_TEST_Q)
        qe = self.app._make_entry(trow, self.qvar, font_size=11)
        qe.pack(side="left", fill="x", expand=True, padx=(6, 0), ipady=3)
        qe.bind("<Return>", lambda e: self.test_prompt())
        self.qvar.trace_add("write", lambda *a: self._schedule_preview())
        self._tip(qe, "Question utilisée par 🧪 Tester et pour {question} dans l'aperçu")

        top = tk.Frame(R, bg=C["bg"])
        top.pack(side="top", fill="x", padx=(10, 4))
        trow2 = tk.Frame(top, bg=C["bg"])
        trow2.pack(fill="x", pady=(0, 2) if self._compact else (2, 4))
        self.ed_title = self._lbl(trow2, "", size=13 if self._compact else 15, fg=C["fg"])
        self.ed_title.pack(side="left")
        self.dirty_lbl = self._lbl(trow2, "", size=10, fg=C["gold"])
        self.dirty_lbl.pack(side="left", padx=10)
        self.active_badge = self._lbl(trow2, "", size=10, fg=C["ok"])
        self.active_badge.pack(side="right")

        form = tk.Frame(top, bg=C["bg"])
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)
        self._lbl(form, "Nom", size=11).grid(row=0, column=0, sticky="w", pady=3)
        self.nvar = tk.StringVar()
        self.name_ent = self.app._make_entry(form, self.nvar, font_size=13)
        self.name_ent.grid(row=0, column=1, sticky="ew", padx=(10, 0), pady=2, ipady=2 if self._compact else 4)
        self.nvar.trace_add("write", lambda *a: self._changed())
        self._tip(self.name_ent, "Nom affiché dans la liste et dans le menu rapide 📜")
        kf = tk.Frame(form, bg=C["bg"])
        kf.grid(row=0, column=2, sticky="e", padx=(10, 0))
        self.kindvar = tk.StringVar(value="normal")
        self.kind_rbs = []
        for key, lab in (("normal", "💬 Normal"), ("jeu", "🎮 Jeu")):
            rb = tk.Radiobutton(
                kf, text=lab, value=key, variable=self.kindvar, command=self._changed,
                bg=C["bg"], fg=C["fg"], selectcolor=C["card"], activebackground=C["bg"],
                activeforeground=C["gold"], font=("Segoe UI", 11, "bold"), cursor="hand2",
            )
            rb.pack(side="left", padx=(0, 6))
            self.kind_rbs.append(rb)
        self._tip(self.kind_rbs[0], "💬 Normal : modifie la façon dont Padawan répond (avec ou sans le défaut du rôle).")
        self._tip(self.kind_rbs[1], "🎮 Jeu : prompt système PUR pour un jeu de rôle (pas de règles de Chercheur,\n"
                                    "pas de chasse web). Activer = lancer la partie avec choix cliquables et Pip-Boy.")
        # v39.6 : modèle propre à ce prompt (facultatif)
        tk.Label(kf, text="🧠", bg=C["bg"], fg=C["gold"], font=("Segoe UI", 12, "bold")).pack(side="left", padx=(8, 2))
        self.modelvar = tk.StringVar(value=PROMPT_MODEL_DEFAULT)
        self.model_cb = ttk.Combobox(kf, textvariable=self.modelvar, state="readonly", width=24,
                                     style="Prompts.TCombobox", font=("Segoe UI", 10),
                                     values=self._model_choices(), postcommand=self._model_cb_refresh)
        self.model_cb.pack(side="left")
        self.model_cb.bind("<<ComboboxSelected>>", lambda e: self._changed())
        self._tip(self.model_cb, "Modèle à utiliser avec ce prompt (facultatif).\n"
                                 "Activer le prompt ou lancer le jeu bascule sur ce modèle;\n"
                                 "↩ Quitter / revenir au défaut remet le modèle d'avant.\n"
                                 "« modèle courant » = ne rien changer. 🧠 Modèles (Ctrl+M) pour en installer.")

        self._lbl(form, "Rôle", size=11).grid(row=1, column=0, sticky="w", pady=3)
        rf = tk.Frame(form, bg=C["bg"])
        rf.grid(row=1, column=1, columnspan=2, sticky="ew", padx=(10, 0), pady=3)  # v39.6: place pour le 🧠 Modèle
        self.rvar = tk.StringVar(value="Tous")
        self.role_cb = ttk.Combobox(rf, textvariable=self.rvar, state="readonly", width=14,
                                    style="Prompts.TCombobox", font=("Segoe UI", 11),
                                    values=[PROMPT_ROLE_LABELS[r] for r in PROMPT_ROLES])
        self.role_cb.pack(side="left")
        self.role_cb.bind("<<ComboboxSelected>>", lambda e: self._changed())
        self._tip(self.role_cb, "Tous = utilisable avec n'importe quel rôle.\n"
                                "Un rôle précis = ce prompt ne s'applique qu'à ce rôle.")
        self.kvar = tk.BooleanVar(value=True)
        if self._compact:  # Mode sur la même rangée que Rôle
            self._lbl(rf, "Mode", size=11).pack(side="left", padx=(14, 6))
            mf = rf
        else:
            self._lbl(form, "Mode", size=11).grid(row=2, column=0, sticky="w", pady=3)
            mf = tk.Frame(form, bg=C["bg"])
            mf.grid(row=2, column=1, sticky="w", padx=(10, 0), pady=3)
        self.mvar = tk.StringVar(value="ajouter")
        self.mode_rbs = []
        short = {"remplacer": "Remplacer le défaut", "ajouter": "Ajouter au défaut"}
        for key in ("remplacer", "ajouter"):
            rb = tk.Radiobutton(
                mf, text=short[key] if self._compact else PROMPT_MODE_LABELS[key], value=key,
                variable=self.mvar, command=self._changed,
                bg=C["bg"], fg=C["fg"], selectcolor=C["card"], activebackground=C["bg"],
                activeforeground=C["gold"], font=("Segoe UI", 11), cursor="hand2",
            )
            rb.pack(side="left", padx=(0, 10 if self._compact else 18))
            self.mode_rbs.append(rb)
        self._tip(self.mode_rbs[0], PROMPT_MODE_LABELS["remplacer"] + " : ton texte prend la place des consignes du rôle.")
        self._tip(self.mode_rbs[1], PROMPT_MODE_LABELS["ajouter"] + " : ton texte s'ajoute APRÈS le prompt normal du rôle (le plus sûr).")
        self.keep_chk = tk.Checkbutton(
            rf, text="ADN Padawan" if self._compact else "Garder l'ADN Padawan (tutoiement, honnêteté, style québécois)",
            variable=self.kvar, command=self._changed,
            bg=C["bg"], fg=C["fg"], selectcolor=C["card"], activebackground=C["bg"],
            activeforeground=C["gold"], font=("Segoe UI", 10), cursor="hand2",
        )
        self.keep_chk.pack(side="left", padx=(6 if self._compact else 16, 0))
        self._tip(self.keep_chk, "Garder l'ADN Padawan (tutoiement, honnêteté, style québécois).\n"
                                 "Coché : en mode Remplacer, la base commune de Padawan reste devant ton texte;\n"
                                 "seul le texte du rôle est remplacé.\n"
                                 "Décoché : ton texte remplace TOUT (contrôle total). La date est toujours ajoutée.")

        vrow = tk.Frame(top, bg=C["bg"])
        vrow.pack(fill="x", pady=(2, 0) if self._compact else (6, 2))
        self._lbl(vrow, "Variables :", size=10, fg=C["dim"]).pack(side="left")
        for var, tip in (
            ("{date}", "Date du jour (ex. 16 novembre 2026)"),
            ("{question}", "La question que tu poses à Padawan"),
            ("{role}", "Le nom du rôle actif (Chercheur, Capitaine…)"),
        ):
            b = self._btn(vrow, var, lambda v=var: self._insert_var(v), f"Insérer {var} au curseur — {tip}", size=9)
            b.configure(padx=8, pady=2)
            b.pack(side="left", padx=3)
        self.count_txt = self._lbl(vrow, "", size=9, bold=False, fg=C["dim"])
        self.count_txt.pack(side="right")

        # éditeur + aperçu : empilés avec séparateur (grand écran) ou bascule ✏ / 👁 (petit écran)
        self._split = self.winfo_screenheight() >= 900
        self.vp = None
        if self._split:
            vp = self.vp = tk.PanedWindow(R, orient="vertical", bg=C["line"], sashwidth=6, bd=0,
                                          sashrelief="flat")
            vp.pack(side="top", fill="both", expand=True, padx=(10, 4), pady=(4, 2))
            ef = tk.Frame(vp, bg=C["input"], highlightbackground=C["line"], highlightthickness=1)
            pf = tk.Frame(vp, bg=C["bg"])
            vp.add(ef, minsize=120, height=260)
            vp.add(pf, minsize=100)
        else:
            seg = tk.Frame(R, bg=C["bg"])
            seg.pack(side="top", fill="x", padx=(10, 4), pady=(4, 0))
            self.seg_btns = {}
            for key, lab, tip in (
                ("edit", "✏ Texte du prompt", "Écrire / modifier ton texte (F6 = basculer)"),
                ("prev", "👁 Aperçu en direct", "Le prompt final exact que Padawan recevra (F6 = basculer)"),
            ):
                sb_ = tk.Label(seg, text=lab, font=("Segoe UI", 10, "bold"), padx=16, pady=4,
                               cursor="hand2", bg=C["card"], fg=C["fg"])
                sb_.pack(side="left", padx=(0, 4))
                sb_.bind("<Button-1>", lambda e, k=key: self._show_pane(k))
                self._tip(sb_, tip)
                self.seg_btns[key] = sb_
            holder = tk.Frame(R, bg=C["bg"])
            holder.pack(side="top", fill="both", expand=True, padx=(10, 4), pady=(2, 2))
            ef = tk.Frame(holder, bg=C["input"], highlightbackground=C["line"], highlightthickness=1)
            pf = tk.Frame(holder, bg=C["bg"])
            self._panes = {"edit": ef, "prev": pf}
            self._pane_cur = "edit"
        self.txt = tk.Text(
            ef, wrap="word", undo=True, maxundo=-1, bg=C["input"], fg=C["fg"], height=6,
            insertbackground=C["cursor"], insertwidth=3, relief="flat", bd=0,
            font=("Segoe UI", 12), padx=12, pady=10, selectbackground=C["sel"],
            highlightthickness=0, spacing1=2, spacing3=2,
        )
        esb = ttk.Scrollbar(ef, orient="vertical", command=self.txt.yview, style="Gold.Vertical.TScrollbar")
        self.txt.configure(yscrollcommand=esb.set)
        self.txt.pack(side="left", fill="both", expand=True)
        esb.pack(side="right", fill="y")
        self.txt.bind("<<Modified>>", self._on_text_modified)
        self.txt.bind("<Control-a>", lambda e: (self.txt.tag_add("sel", "1.0", "end-1c"), "break")[1])

        ph = tk.Frame(pf, bg=C["bg"])
        ph.pack(fill="x", pady=(4, 2))
        self.prev_title = self._lbl(ph, "👁 Aperçu en direct", size=10, fg=C["cyan"])
        self.prev_title.pack(side="left")
        self.prev_count = self._lbl(ph, "", size=9, bold=False, fg=C["dim"])
        self.prev_count.pack(side="right")
        pwrap = tk.Frame(pf, bg=C["panel"], highlightbackground=C["line"], highlightthickness=1)
        pwrap.pack(fill="both", expand=True)
        self.prev = tk.Text(
            pwrap, wrap="word", bg=C["panel"], fg=C["dim"], relief="flat", bd=0, height=6,
            font=("Consolas", 10), padx=10, pady=8, highlightthickness=0, cursor="arrow",
        )
        psb = ttk.Scrollbar(pwrap, orient="vertical", command=self.prev.yview, style="Gold.Vertical.TScrollbar")
        self.prev.configure(yscrollcommand=psb.set)
        self.prev.pack(side="left", fill="both", expand=True)
        psb.pack(side="right", fill="y")
        self.prev.tag_configure("mine", foreground=C["gold"])
        self.prev.tag_configure("note", foreground=C["cyan"], font=("Segoe UI", 10, "italic"))
        self.prev.configure(state="disabled")
        self._tip(self.prev_title, "Le prompt système exact que Padawan recevra (variables remplacées).\n"
                                   "En doré : ta partie. Le reste : base Padawan, date, garde-fous de chasse.")
        if not self._split:
            self._show_pane("edit")

    def _show_pane(self, key: str):
        if self._split or key not in getattr(self, "_panes", {}):
            return
        for k, fr in self._panes.items():
            fr.pack_forget()
        self._panes[key].pack(fill="both", expand=True)
        self._pane_cur = key
        for k, b in self.seg_btns.items():
            on = k == key
            b.configure(bg=C["gold"] if on else C["card"], fg="#1a1408" if on else C["fg"])
        if key == "prev":
            self._update_preview()
        else:
            try:
                self.txt.focus_set()
            except Exception:
                pass
        self.app._theme_fix(self.seg_btns[key].master)

    def _toggle_pane(self):
        if not self._split:
            self._show_pane("prev" if self._pane_cur == "edit" else "edit")

    def _build_ideas_tab(self, root):
        self._lbl(
            root,
            "Une question qui te passe par la tête pendant une chasse ? Ctrl+I la met de côté ; "
            "Relancer la remet dans la barre plus tard.",
            size=12, bold=False, fg=C["fg"], wraplength=1100, justify="left",
        ).pack(anchor="w", padx=12, pady=(12, 6))
        row = tk.Frame(root, bg=C["bg"])
        row.pack(fill="x", padx=10, pady=(0, 6))
        self._btn(row, "➕ Garer ce qui est dans la barre  (Ctrl+I)", self._park_from_win,
                  "Met de côté le texte de la barre (ou de la chasse) de Padawan", kind="primary").pack(side="left")
        self.ideas_count = self._lbl(row, "", size=10, bold=False, fg=C["dim"])
        self.ideas_count.pack(side="left", padx=12)

        wrap = tk.Frame(root, bg=C["bg"])
        wrap.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        canvas = tk.Canvas(wrap, bg=C["bg"], highlightthickness=0)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=canvas.yview, style="Gold.Vertical.TScrollbar")
        self.ideas_inner = tk.Frame(canvas, bg=C["bg"])
        self.ideas_inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        win = canvas.create_window((0, 0), window=self.ideas_inner, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win, width=max(300, e.width - 4)))

        def _wheel(e):
            if getattr(e, "num", None) == 4:
                canvas.yview_scroll(-1, "units")
            elif getattr(e, "num", None) == 5:
                canvas.yview_scroll(1, "units")
            else:
                canvas.yview_scroll(int(-1 * ((e.delta or 0) / 120)), "units")

        canvas.bind("<Enter>", lambda e: (canvas.bind_all("<MouseWheel>", _wheel),
                                          canvas.bind_all("<Button-4>", _wheel),
                                          canvas.bind_all("<Button-5>", _wheel)))
        canvas.bind("<Leave>", lambda e: (canvas.unbind_all("<MouseWheel>"),
                                          canvas.unbind_all("<Button-4>"),
                                          canvas.unbind_all("<Button-5>")))
        self._refresh_ideas()

    # ── idées garées ─────────────────────────────────────────────────────────
    def _park_from_win(self):
        self.app.park()
        self._refresh_ideas()

    def _refresh_ideas(self):
        try:
            self.nb.tab(self.tab_i, text=self._ideas_tab_label())
        except Exception:
            pass
        inner = getattr(self, "ideas_inner", None)
        if inner is None:
            return
        for w in inner.winfo_children():
            w.destroy()
        allitems = list(self.app.mem.get("inbox") or [])
        items = allitems[:80]
        self.ideas_count.config(text=f"{len(allitems)} idée(s) garée(s)" if allitems else "")
        if not items:
            self._lbl(inner, "Aucune idée garée pour l'instant — Ctrl+I dans Padawan pour en mettre une de côté.",
                      size=11, bold=False, fg=C["dim"]).pack(anchor="w", padx=8, pady=24)
            self.app._theme_fix(inner)
            return
        for idx, it in enumerate(items):
            row = tk.Frame(inner, bg=C["card"], highlightbackground=C["line"], highlightthickness=1)
            row.pack(fill="x", padx=4, pady=3)
            stamp = (it.get("t") or "")[5:16]
            txt = (it.get("text") or "")[:300]

            def relancer(t=it.get("text", "")):
                if not self._confirm_discard():
                    return
                self._destroy()
                try:
                    self.app.hunt.set(t)
                    self.app.var.set(t)
                    self.app.ent.focus_set()
                except Exception:
                    pass

            def supprimer(i=idx):
                try:
                    del self.app.mem["inbox"][i]
                except Exception:
                    return
                savej(MEM_FILE, self.app.mem)
                self.app._refresh_inbox_badge()

            self._btn(row, "▶ Relancer", relancer, "Remettre cette idée dans la barre de Padawan",
                      kind="primary", size=10).pack(side="right", padx=(3, 6), pady=5)
            self._btn(row, "🗑 Supprimer", supprimer, "Retirer cette idée", kind="danger",
                      size=10).pack(side="right", padx=3, pady=5)
            tk.Label(row, text=stamp, bg=C["card"], fg=C["dim"], font=("Segoe UI", 9)).pack(
                side="left", padx=(10, 4), pady=6)
            tk.Label(row, text=txt, bg=C["card"], fg=C["fg"], font=("Segoe UI", 11), anchor="w",
                     wraplength=900, justify="left").pack(side="left", fill="x", expand=True, padx=4, pady=6)
        self.app._theme_fix(inner)

    # ── liste ────────────────────────────────────────────────────────────────
    def _locked_items(self) -> List[Dict[str, Any]]:
        out = []
        for rid in RoleRouter_ROLE_IDS:
            out.append({
                "id": PROMPT_LOCK_PREFIX + rid, "name": f"Défaut — {RoleRouter.ROLES[rid]['label']}",
                "role": rid, "mode": "remplacer", "keep_base": True,
                "text": RoleRouter.default_role_text(rid), "locked": True,
            })
        out.append({
            "id": PROMPT_LOCK_BASE, "name": "ADN Padawan (base commune)", "role": "tous",
            "mode": "remplacer", "keep_base": False, "text": SYSTEM_BASE, "locked": True,
        })
        return out

    def _item(self, pid: str) -> Optional[Dict[str, Any]]:
        if pid.startswith("__"):
            for it in self._locked_items():
                if it["id"] == pid:
                    return it
            return None
        return self.store.get(pid)

    def _role_filter(self) -> str:
        lab = self.rfilter.get()
        for r, l in PROMPT_ROLE_LABELS.items():
            if l == lab and r != "tous":
                return r
        return ""

    def _match(self, p, q: str, rf: str) -> bool:
        if rf and p["role"] not in ("tous", rf):
            return False
        if q:
            hay = (p["name"] + "\n" + p.get("text", "")).lower()
            return all(w in hay for w in q.lower().split())
        return True

    def _fill_list(self, keep: bool = False):
        if not hasattr(self, "lb"):
            return
        q, rf = self.fvar.get().strip(), self._role_filter()
        top = self.lb.nearest(0) if keep else 0
        cur_role = self.app.router.active
        self.lb.delete(0, "end")
        self._view_ids = []
        users = [p for p in self.store.all() if self._match(p, q, rf)]
        locks = [p for p in self._locked_items() if self._match(p, q, rf)]
        self._n_user_view = len(users)
        game_id = (getattr(self.app, "game", None) or {}).get("pid", "")
        for p in users:
            act = self.store.active_roles(p["id"])
            if p.get("kind") == "jeu":
                act = list(RoleRouter_ROLE_IDS) if p["id"] == game_id else []
            star = "⭐" if act else "    "
            tag = "" if p["role"] == "tous" else f"   · {PROMPT_ROLE_LABELS[p['role']]}"
            if p.get("kind") == "jeu":
                tag = "   · Jeu" if not p["name"].startswith("🎮") else ""
            self.lb.insert("end", f" {star} {p['name']}{tag}")
            self._view_ids.append(p["id"])
            i = self.lb.size() - 1
            if cur_role in act:
                self.lb.itemconfigure(i, foreground=C["gold"])
            elif act:
                self.lb.itemconfigure(i, foreground=C["ok"])
        if not users:
            self.lb.insert("end", "   (aucun favori — ➕ Nouveau ou 📄 Dupliquer un 🔒)" if not q
                           else "   (aucun résultat)")
            self.lb.itemconfigure(self.lb.size() - 1, foreground=C["dim"])
            self._view_ids.append("")
        for p in locks:
            rid = p["role"]
            is_def_active = rid in RoleRouter_ROLE_IDS and not self.store.active_for(rid)
            star = "⭐" if is_def_active else "    "
            self.lb.insert("end", f" {star} 🔒 {p['name']}")
            self._view_ids.append(p["id"])
            self.lb.itemconfigure(self.lb.size() - 1, foreground=C["dim"])
        nu = len(self.store.all())
        self.count_lbl.config(text=f"{nu} favori(s)")
        if self.cur_id in self._view_ids:
            i = self._view_ids.index(self.cur_id)
            self.lb.selection_clear(0, "end")
            self.lb.selection_set(i)
        try:
            self.lb.yview(top)
        except Exception:
            pass
        self.app._theme_fix(self.lb)

    def _select_id(self, pid: str, *, force: bool = False):
        if pid not in self._view_ids:
            self.fvar.set("")
            self.rfilter.set("Tous les rôles")
            self._fill_list()
        if pid in self._view_ids:
            i = self._view_ids.index(pid)
            self.lb.selection_clear(0, "end")
            self.lb.selection_set(i)
            self.lb.see(i)
        self._load(pid)

    def _on_select(self, e=None):
        sel = self.lb.curselection()
        if not sel:
            return
        pid = self._view_ids[sel[0]] if sel[0] < len(self._view_ids) else ""
        if not pid or pid == self.cur_id:
            if not pid and self.cur_id in self._view_ids:
                self.lb.selection_clear(0, "end")
                self.lb.selection_set(self._view_ids.index(self.cur_id))
            return
        if not self._confirm_discard():
            if self.cur_id in self._view_ids:
                self.lb.selection_clear(0, "end")
                self.lb.selection_set(self._view_ids.index(self.cur_id))
            return
        self._load(pid)

    # glisser-déposer (liste complète seulement)
    def _drag_start(self, e):
        i = self.lb.nearest(e.y)
        can = (not self.fvar.get().strip() and not self._role_filter()
               and 0 <= i < self._n_user_view)
        self._drag = {"i": i, "moved": False} if can else None

    def _drag_motion(self, e):
        d = self._drag
        if not d:
            return
        j = self.lb.nearest(e.y)
        j = max(0, min(self._n_user_view - 1, j))
        if j == d["i"]:
            return "break"
        pid = self._view_ids[d["i"]]
        if self.store.move_to(pid, j):
            d["i"], d["moved"] = j, True
            self._fill_list(keep=True)
            self.lb.selection_clear(0, "end")
            self.lb.selection_set(j)
        return "break"

    def _drag_end(self, e):
        d, self._drag = self._drag, None
        if d and d.get("moved"):
            if self.store.save():
                self._status("↕ Ordre enregistré.", "ok")
                self.app._refresh_prompt_ui()
            else:
                self._status(f"⚠ {self.store.error}", "bad")

    def move(self, delta: int):
        if not self.cur_id or self.cur_id.startswith("__"):
            return self._status("Choisis un de tes favoris pour le déplacer (les 🔒 restent en bas).", "warn")
        if self.store.move(self.cur_id, delta):
            self.store.save()
            self._fill_list(keep=True)
            if self.cur_id in self._view_ids:
                self.lb.see(self._view_ids.index(self.cur_id))
            self.app._refresh_prompt_ui()

    def _focus_filter(self):
        self.select_tab("prompts")
        self.filter_ent.focus_set()
        self.filter_ent.select_range(0, "end")

    # ── v39.6 : modèle par prompt ────────────────────────────────────────────
    def _model_choices(self) -> List[str]:
        mods = [model_id_from_label(m) for m in (getattr(self.app, "mods", None) or []) if MODEL_DL_MARK not in m]
        cur = (self.modelvar.get() if hasattr(self, "modelvar") else "") or ""
        if cur and cur != PROMPT_MODEL_DEFAULT and cur not in mods:
            mods.append(cur)
        return [PROMPT_MODEL_DEFAULT] + mods

    def _model_cb_refresh(self):
        try:
            self.model_cb.configure(values=self._model_choices())
        except Exception:
            pass

    # ── éditeur ──────────────────────────────────────────────────────────────
    def _load(self, pid: str):
        p = self._item(pid)
        if not p:
            return
        self._loading = True
        try:
            self.cur_id = pid
            locked = bool(p.get("locked"))
            self.name_ent.configure(state="normal")
            self.nvar.set(p["name"])
            self.rvar.set(PROMPT_ROLE_LABELS.get(p["role"], "Tous"))
            self.mvar.set(p["mode"])
            self.kvar.set(bool(p.get("keep_base", True)))
            self.kindvar.set("jeu" if p.get("kind") == "jeu" else "normal")
            self.modelvar.set((p.get("model") or "").strip() or PROMPT_MODEL_DEFAULT)
            self.model_cb.configure(state="disabled" if locked else "readonly")
            self.txt.configure(state="normal")
            self.txt.delete("1.0", "end")
            self.txt.insert("1.0", p.get("text", ""))
            self.txt.edit_reset()
            self.txt.edit_modified(False)
            st = "disabled" if locked else "normal"
            self.txt.configure(state=st, fg=C["dim"] if locked else C["fg"])
            self.name_ent.configure(state="readonly" if locked else "normal")
            self.role_cb.configure(state="disabled" if locked else "readonly")
            for w in self.mode_rbs + [self.keep_chk] + self.kind_rbs:
                w.configure(state=st)
            for k in ("save", "del"):
                self.btns[k].configure(state="disabled" if locked else "normal")
            self.btns["act"].configure(state="disabled" if pid == PROMPT_LOCK_BASE else "normal")
            self.ed_title.config(text=("🔒 " if locked else "✏ ") + p["name"])
            self.dirty = False
            self.dirty_lbl.config(text="")
        finally:
            self._loading = False
        self._update_keep_state()
        self._refresh_badge()
        self._update_counts()
        self._update_preview()
        if locked:
            self._status("🔒 Prompt d'origine en lecture seule — 📄 Dupliquer pour en faire ta version.", "info")
        else:
            self._status("", "info")
        self.app._theme_fix(self)

    def _update_keep_state(self):
        p = self._item(self.cur_id) if self.cur_id else None
        if p and p.get("locked"):
            return
        jeu = self.kindvar.get() == "jeu"
        self.keep_chk.configure(state="normal" if (self.mvar.get() == "remplacer" or jeu) else "disabled")
        for w in self.mode_rbs:
            w.configure(state="disabled" if jeu else "normal")
        self.role_cb.configure(state="disabled" if jeu else "readonly")
        if jeu and self.rvar.get() != PROMPT_ROLE_LABELS["tous"]:
            self.rvar.set(PROMPT_ROLE_LABELS["tous"])
        try:
            self.btns["act"].configure(text="🎮 Jouer" if jeu else "✅ Activer")
        except Exception:
            pass

    def _refresh_badge(self):
        pid = self.cur_id
        if not pid:
            self.active_badge.config(text="")
            return
        if pid.startswith(PROMPT_LOCK_PREFIX):
            rid = pid[len(PROMPT_LOCK_PREFIX):]
            on = not self.store.active_for(rid)
            self.active_badge.config(text="⭐ ACTIF (aucun favori sur ce rôle)" if on else "")
            return
        roles = self.store.active_roles(pid)
        if roles:
            labs = ", ".join(RoleRouter.ROLES[r]["label"] for r in RoleRouter_ROLE_IDS if r in roles)
            self.active_badge.config(text=f"⭐ ACTIF : {labs}")
        else:
            self.active_badge.config(text="")

    def _changed(self):
        if self._loading:
            return
        self._update_keep_state()
        p = self._item(self.cur_id) if self.cur_id else None
        if p and not p.get("locked"):
            self.dirty = True
            self.dirty_lbl.config(text="● non enregistré  (Ctrl+S)")
        self._schedule_preview()

    def _on_text_modified(self, e=None):
        if self.txt.edit_modified():
            self.txt.edit_modified(False)
            if not self._loading:
                self._changed()
                self._update_counts()

    def _insert_var(self, v: str):
        if str(self.txt.cget("state")) == "disabled":
            return self._status("🔒 Lecture seule — 📄 Dupliquer d'abord.", "warn")
        self.txt.insert("insert", v)
        self.txt.focus_set()

    def _editor_prompt(self) -> Dict[str, Any]:
        role = "tous"
        for r, l in PROMPT_ROLE_LABELS.items():
            if l == self.rvar.get():
                role = r
        jeu = self.kindvar.get() == "jeu"
        old = self.store.get(self.cur_id) or {}
        return {
            "id": self.cur_id, "name": self.nvar.get().strip(), "role": "tous" if jeu else role,
            "mode": "remplacer" if jeu else self.mvar.get(),
            "keep_base": bool(self.kvar.get()), "text": self.txt.get("1.0", "end-1c"),
            "kind": "jeu" if jeu else "normal", "builtin": old.get("builtin", ""),
            "model": "" if self.modelvar.get() == PROMPT_MODEL_DEFAULT else model_id_from_label(self.modelvar.get()),
        }

    def _update_counts(self):
        t = self.txt.get("1.0", "end-1c")
        n, w = len(t), len(t.split())
        self.count_txt.config(text=f"{_fr_int(n)} caractères · {_fr_int(w)} mots · ≈ {_fr_int(max(0, n // 4))} jetons")

    def _schedule_preview(self):
        if self._prev_job:
            try:
                self.after_cancel(self._prev_job)
            except Exception:
                pass
        self._prev_job = self.after(220, self._update_preview)

    def _preview_role(self, p: Dict[str, Any]) -> str:
        return p["role"] if p["role"] in RoleRouter_ROLE_IDS else self.app.router.active

    def _update_preview(self):
        self._prev_job = None
        if not self.cur_id:
            return
        try:
            locked = self.cur_id.startswith("__")
            p = self._item(self.cur_id) if locked else self._editor_prompt()
            rid = self._preview_role(p)
            q = self.qvar.get().strip() or PROMPT_TEST_Q
            if self.cur_id.startswith(PROMPT_LOCK_PREFIX):
                full = self.app.router.system_prompt(role_id=rid, use_default=True)
                mine = ""
            else:
                full = self.app.router.system_prompt(question=q, override=p, role_id=rid)
                mine = prompt_render(p.get("text", ""), date=_today_fr()[0], question=q,
                                     role=RoleRouter.ROLES[rid]["label"]).strip()
            note = ""
            if not locked and not (p.get("text") or "").strip():
                note = "(Texte vide : c'est le prompt par défaut du rôle qui s'appliquera.)\n\n"
            if rid == "chercheur" and p.get("kind") != "jeu":
                full_show = full + " Si les sources digressent, ignore-les. Reste sur: <ta chasse>."
            else:
                full_show = full
            self.prev.configure(state="normal")
            self.prev.delete("1.0", "end")
            if note:
                self.prev.insert("end", note, "note")
            k = full_show.find(mine) if mine else -1
            if k >= 0:
                self.prev.insert("end", full_show[:k])
                self.prev.insert("end", mine, "mine")
                self.prev.insert("end", full_show[k + len(mine):])
            else:
                self.prev.insert("end", full_show)
            self.prev.configure(state="disabled")
            if k >= 0:
                try:  # montre directement TA partie (en doré)
                    self.prev.see("mine.first")
                except Exception:
                    pass
            lab = RoleRouter.ROLES[rid]["label"]
            extra = "" if p["role"] in RoleRouter_ROLE_IDS else " (rôle actuel de Padawan)"
            self.prev_title.config(text=f"👁 Aperçu en direct — prompt final, rôle : {lab}{extra}"
                                   if p.get("kind") != "jeu" else "👁 Aperçu — prompt système du 🎮 jeu (pur)")
            self.prev_count.config(text=f"{_fr_int(len(full_show))} caractères au total")
        except Exception as e:
            log(f"prompt preview: {e}")

    def _refresh_header(self):
        rid = self.app.router.active
        lab = RoleRouter.ROLES[rid]["label"]
        p = self.store.active_for(rid)
        self.hdr_role.config(text=f"RÔLE ACTUEL : {lab.upper()}")
        self.hdr_active.config(text=f"⭐ {p['name']}" if p else "Prompt : défaut",
                               fg=C["gold"] if p else C["dim"])

    def _refresh_from_app(self):
        """Appelé par Padawan quand le rôle ou le prompt actif change."""
        self._refresh_header()
        self._fill_list(keep=True)
        self._refresh_badge()
        self._schedule_preview()

    # ── actions ──────────────────────────────────────────────────────────────
    def _confirm_discard(self) -> bool:
        if not self.dirty:
            return True
        name = self.nvar.get().strip() or "ce prompt"
        r = messagebox.askyesnocancel(
            "📜 Prompts", f"Enregistrer les modifications de « {name} » ?", parent=self)
        if r is None:
            return False
        if r:
            return self.save_current()
        self.dirty = False
        self.dirty_lbl.config(text="")
        return True

    def save_current(self) -> bool:
        if not self.cur_id or self.cur_id.startswith("__"):
            self._status("🔒 Lecture seule — 📄 Dupliquer pour créer ta version.", "warn")
            return False
        p = self._editor_prompt()
        if not p["name"]:
            self._status("Donne un nom au prompt avant d'enregistrer.", "warn")
            self.name_ent.focus_set()
            return False
        old = self.store.get(self.cur_id) or {}
        cleaned, found = prompt_clean(p["text"])
        if found and cleaned and messagebox.askyesno(
                "📜 Nettoyer le prompt ?",
                "Ton texte contient " + ", ".join(found) + " — sûrement copié depuis l'👁 Aperçu.\n\n"
                "Padawan ajoute déjà ces morceaux lui-même : les garder les met en double (et la chasse\n"
                "« Reste sur: <ta chasse> » brouille les jeux).\n\nLes retirer automatiquement ?", parent=self):
            p["text"] = cleaned
            self._loading = True
            try:
                self.txt.delete("1.0", "end")
                self.txt.insert("1.0", cleaned)
            finally:
                self._loading = False
        p["example"] = bool(old.get("example")) and p["text"] == old.get("text") and p["name"] == old.get("name")
        self.store.upsert(p)
        if not self.store.save():
            self._status(f"⚠ {self.store.error}", "bad")
            return False
        self.dirty = False
        self.dirty_lbl.config(text="")
        self.ed_title.config(text="✏ " + p["name"])
        self._fill_list(keep=True)
        self._refresh_badge()
        self.app._refresh_prompt_ui()
        live = self.store.active_roles(self.cur_id)
        self._status("💾 Enregistré" + (" — déjà actif : effet dès la prochaine question." if live else "."), "ok")
        return True

    def _add_and_select(self, p: Dict[str, Any], after: str = ""):
        q = self.store.upsert(dict(p, id=PromptStore._new_id()))
        if after:
            j = self.store.index_of(after)
            if j >= 0:
                self.store.move_to(q["id"], j + 1)
        if not self.store.save():
            self._status(f"⚠ {self.store.error}", "bad")
        self.fvar.set("")
        self.rfilter.set("Tous les rôles")
        self._fill_list()
        self._select_id(q["id"])
        return q

    def new_prompt(self):
        if not self._confirm_discard():
            return
        self.select_tab("prompts")
        self._add_and_select({"name": "Nouveau prompt", "role": "tous", "mode": "ajouter",
                              "keep_base": True, "text": ""})
        self.name_ent.focus_set()
        self.name_ent.select_range(0, "end")
        self._status("➕ Nouveau prompt créé — donne-lui un nom, écris ton texte, puis 💾 et ✅.", "ok")

    def duplicate(self):
        if not self.cur_id:
            return
        if not self._confirm_discard():
            return
        p = dict(self._item(self.cur_id) or {})
        if not p:
            return
        if self.cur_id == PROMPT_LOCK_BASE:
            p.update(name="Mon ADN Padawan", role="tous", mode="remplacer", keep_base=False)
            after = ""
        elif self.cur_id.startswith(PROMPT_LOCK_PREFIX):
            p.update(name=f"Mon {RoleRouter.ROLES[p['role']]['label']}", mode="remplacer", keep_base=True)
            after = ""
        else:
            p["name"] = (p["name"].replace(" (exemple)", "") + " (copie)")[:120]
            after = self.cur_id
        p.pop("locked", None)
        p["example"] = False
        self._add_and_select(p, after=after)
        self.name_ent.focus_set()
        self.name_ent.select_range(0, "end")
        self._status("📄 Copie créée et enregistrée — modifie-la à ton goût.", "ok")

    def delete(self):
        if not self.cur_id or self.cur_id.startswith("__"):
            return self._status("🔒 Les prompts d'origine ne se suppriment pas.", "warn")
        p = self.store.get(self.cur_id)
        if not p:
            return
        if not messagebox.askyesno(
            "📜 Supprimer",
            f"Supprimer « {p['name']} » ?\n\nUne copie de sécurité reste dans\n"
            f"{os.path.join(self.store.bak_dir, 'prompts.json.bak')}",
            parent=self, icon="warning",
        ):
            return
        i = self._view_ids.index(self.cur_id) if self.cur_id in self._view_ids else 0
        self.store.delete(self.cur_id)
        if not self.store.save():
            self._status(f"⚠ {self.store.error}", "bad")
        self.dirty = False
        self.cur_id = ""
        self._fill_list()
        ids = [x for x in self._view_ids if x]
        if ids:
            self._select_id(ids[min(i, len(ids) - 1)])
        self.app._refresh_prompt_ui()
        self._status(f"🗑 « {p['name']} » supprimé.", "ok")

    def activate(self):
        if not self.cur_id:
            return
        if self.cur_id == PROMPT_LOCK_BASE:
            return self._status("L'ADN seul ne s'active pas : 📄 Dupliquer pour en faire ton prompt complet.", "warn")
        if self.cur_id.startswith(PROMPT_LOCK_PREFIX):
            rid = self.cur_id[len(PROMPT_LOCK_PREFIX):]
            self.app._prompt_set_active(None, rid)
            self._status(f"↩ {RoleRouter.ROLES[rid]['label']} : prompt d'origine rétabli.", "ok")
            return
        if self.dirty and not self.save_current():
            return
        p = self.store.get(self.cur_id)
        if not p:
            return
        if not (p.get("text") or "").strip():
            return self._status("Ce prompt est vide — écris ton texte avant de l'activer.", "warn")
        if p.get("kind") == "jeu":
            self.app.game_start(p["id"])
            self._status(f"🎮 « {p['name']} » lancé dans la fenêtre principale de Padawan.", "ok")
            self._fill_list(keep=True)
            return
        roles = self.app._prompt_set_active(p["id"], None)
        if roles:
            labs = ", ".join(RoleRouter.ROLES[r]["label"] for r in roles)
            self._status(f"✅ « {p['name']} » actif pour : {labs}.", "ok")

    def reset_default(self):
        self.app._prompt_set_active(None, None)
        self._status("↩ Tous les rôles reprennent le prompt d'origine de Padawan.", "ok")

    def test_prompt(self):
        if not self.cur_id:
            return
        locked = self.cur_id.startswith("__")
        p = dict(self._item(self.cur_id) or {}) if locked else self._editor_prompt()
        if not p:
            return
        rid = self._preview_role(p)
        q = self.qvar.get().strip() or PROMPT_TEST_Q
        if p.get("kind") == "jeu":
            self.app.game_start(p.get("id", ""), override=dict(p, id=p.get("id") or "test"))
            return self._status("🎮 Essai du jeu lancé dans Padawan (texte non enregistré utilisé tel quel).", "ok")
        override = None if self.cur_id.startswith(PROMPT_LOCK_PREFIX) else p
        if self.app._prompt_test(override, rid, q, name=p.get("name") or "prompt"):
            self._status(f"🧪 Test lancé ({RoleRouter.ROLES[rid]['label']}) — la réponse s'écrit dans le chat "
                         "de Padawan. Ton actif n'a pas changé.", "ok")
        else:
            self._status("🧪 Test impossible pour l'instant (Padawan occupé ou modèle pas prêt).", "warn")

    def import_prompts(self):
        path = filedialog.askopenfilename(
            parent=self, title="Importer des prompts",
            initialdir=os.path.join(os.path.expanduser("~"), "Documents"),
            filetypes=[("Prompts (.json, .txt)", "*.json *.txt"), ("JSON", "*.json"), ("Texte", "*.txt"),
                       ("Tous", "*.*")],
        )
        if not path:
            return
        try:
            raw = open(path, "rb").read()
            try:
                s = raw.decode("utf-8-sig")
            except UnicodeDecodeError:
                s = raw.decode("cp1252", errors="replace")
            items: List[Dict[str, Any]] = []
            if path.lower().endswith(".json"):
                d = json.loads(s)
                if isinstance(d, dict) and isinstance(d.get("prompts"), list):
                    items = d["prompts"]
                elif isinstance(d, list):
                    items = d
                elif isinstance(d, dict) and "text" in d:
                    items = [d]
            else:
                stem = os.path.splitext(os.path.basename(path))[0]
                items = [{"name": stem, "role": "tous", "mode": "ajouter", "keep_base": True, "text": s.strip()}]
            have = {(p["name"], p["text"]) for p in self.store.all()}
            added = []
            for it in items:
                q = self.store._norm_prompt(it)
                if not q or not q["text"].strip() or (q["name"], q["text"]) in have:
                    continue
                q["id"] = PromptStore._new_id()
                q["example"] = False
                self.store.data["prompts"].insert(len(added), q)
                have.add((q["name"], q["text"]))
                added.append(q["id"])
            if not added:
                return self._status("📥 Rien de nouveau à importer (vide ou déjà présent).", "warn")
            self.store.save()
            self.fvar.set("")
            self._fill_list()
            self._select_id(added[0])
            self._status(f"📥 {len(added)} prompt(s) importé(s) depuis {os.path.basename(path)}.", "ok")
        except Exception as e:
            self._status(f"⚠ Import impossible : {e}", "bad")

    def export_prompts(self):
        cur = self._item(self.cur_id) if self.cur_id else None
        base_name = re.sub(r"[^\w\- ]+", "", (cur or {}).get("name", "prompt")).strip() or "prompt"
        path = filedialog.asksaveasfilename(
            parent=self, title="Exporter",
            initialdir=os.path.join(os.path.expanduser("~"), "Documents"),
            initialfile="mes_prompts_padawan.json", defaultextension=".json",
            filetypes=[("Tous mes prompts (.json)", "*.json"), (f"Prompt affiché — {base_name} (.txt)", "*.txt")],
        )
        if not path:
            return
        try:
            if path.lower().endswith(".txt"):
                body = self.txt.get("1.0", "end-1c")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(body)
                self._status(f"📤 Prompt exporté : {path}", "ok")
            else:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump({"padawan_prompts": 1, "exported": now(), "prompts": self.store.all()},
                              f, ensure_ascii=False, indent=2)
                self._status(f"📤 {len(self.store.all())} prompt(s) exporté(s) : {path}", "ok")
        except Exception as e:
            self._status(f"⚠ Export impossible : {e}", "bad")

    def _destroy(self):
        try:
            self.unbind_all("<MouseWheel>")
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass
        if getattr(self.app, "_prompts_win", None) is self:
            self.app._prompts_win = None

    def close(self):
        if self._confirm_discard():
            self._destroy()


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


def _build_messages(sys_msg: str, user: str, history: Optional[List[Dict[str, str]]],
                    raw: bool = False) -> List[Dict[str, str]]:
    if raw:  # v39.3: prompt personnalisé / jeu = système tel quel (pas de style ni « Pour aller plus loin »)
        msgs = [{"role": "system", "content": sys_msg}]
        for m in (history or []):
            if m.get("role") in ("user", "assistant") and (m.get("content") or "").strip():
                msgs.append({"role": m["role"], "content": m["content"]})
        msgs.append({"role": "user", "content": user})
        return msgs
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
         history: Optional[List[Dict[str, str]]] = None, raw_system: bool = False,
         options: Optional[Dict[str, Any]] = None) -> str:
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
                "options": dict(gen_options(), **(options or {})),
                "messages": _build_messages(sys_msg, user, history, raw=raw_system),
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
    raw_system: bool = False,
    options: Optional[Dict[str, Any]] = None,
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
                "options": dict(gen_options(), **(options or {})),
                "messages": _build_messages(sys_msg, user, history, raw=raw_system),
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
            return chat(model, user, system=system, cancel=cancel, history=history,
                        raw_system=raw_system, options=options)
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
        if self.cfg.get("startup_chercheur", True):  # v39.4: on commence sérieux : Chercheur + prompt d'origine
            role0 = "chercheur"
        if role0 not in RoleRouter.ROLES:
            role0 = "chercheur"
        try:
            self.prompts = PromptStore()
        except Exception as e:  # jamais bloquant: favoris en mémoire seulement
            log(f"prompts init: {e}")
            self.prompts = PromptStore.__new__(PromptStore)
            self.prompts.path, self.prompts.bak_dir, self.prompts.error = PROMPTS_FILE, PROMPTS_BAK_DIR, str(e)
            self.prompts.data = {"version": 1, "prompts": [], "active": {}, "seeded": True}
        self._prompts_win = None
        self._startup_note = ""
        if self.cfg.get("startup_chercheur", True) and isinstance(self.prompts.data.get("active"), dict) \
                and self.prompts.data["active"]:
            names = [self.prompts.get(x)["name"] for x in self.prompts.data["active"].values() if self.prompts.get(x)]
            self.prompts.data["active"] = {}
            self.prompts.save()
            if names:
                self._startup_note = (f"🔎 Départ en mode Chercheur, prompt d'origine. Ton favori « {names[0]} » "
                                      "reste à un clic (carte 📜 PROMPT à gauche).")
        self.router = RoleRouter(self.mem, active=role0, prompts=self.prompts)
        if role0 in ROLE_TO_MODE:
            self.mode = ROLE_TO_MODE[role0]
        self.session = {"t": now(), "h": []}
        self.mem["sessions"].append({"start": self.session["t"], "history": self.session["h"]})
        self.bind("<Control-f>", lambda e: self.focus_hunt())
        self.bind("<Control-i>", lambda e: self.park())
        self.bind("<Control-m>", lambda e: (self.show_models(), "break")[1])  # v39.6 🧠 Modèles
        self.bind("<Control-M>", lambda e: (self.show_models(), "break")[1])
        self.bind("<Control-k>", lambda e: (self.show_atelier(), "break")[1])  # v40.0 💻 Atelier
        self.bind("<Control-K>", lambda e: (self.show_atelier(), "break")[1])
        self.bind("<Control-g>", lambda e: (self.show_studio(), "break")[1])  # v41.0 🎨 Studio
        self.bind("<Control-G>", lambda e: (self.show_studio(), "break")[1])
        self.bind("<Control-p>", lambda e: (self.show_prompts(), "break")[1])  # v39.2 📜 Prompts
        self.bind("<Control-P>", lambda e: (self.show_prompts(), "break")[1])
        self.bind("<Control-l>", lambda e: (self.new_conversation(), "break")[1])
        self.bind("<Control-L>", lambda e: (self.new_conversation(), "break")[1])
        self.bind("<Control-Shift-N>", lambda e: (self.new_conversation(), "break")[1])
        self.bind("<Control-Shift-n>", lambda e: (self.new_conversation(), "break")[1])
        self.bind("<Control-Shift-H>", lambda e: (self.show_conv_history(), "break")[1])
        self.bind("<Control-Shift-h>", lambda e: (self.show_conv_history(), "break")[1])
        # v39.1: chaque lancement = conversation neuve (l'ancienne est archivée, rien d'effacé)
        try:
            self._archive_role_histories(reason="lancement")
        except Exception as e:
            log(f"archive lancement: {e}")
        self.bind("<F11>", lambda e: self.attributes("-fullscreen", not self.attributes("-fullscreen")))
        self.bind("<Escape>", lambda e: self.cancel_job())
        self._style()
        self.build()
        try:
            self._install_clipboard()  # v40.0 copier/coller partout
        except Exception as e:
            log(f"clipboard: {e}")
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
        self.after(700, self._game_boot)  # v39.3: reprend la partie en cours / note de migration

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
        self._refresh_prompt_ui()

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

        # v39.2: prompt actif (clic = 📜 Prompts)
        pcard = tk.Frame(self.rail_inner, bg=C["card"], highlightbackground=C["line"],
                         highlightthickness=1, cursor="hand2")
        pcard.pack(fill="x", pady=(0, 6))
        self.prompt_ind_role = tk.Label(
            pcard, text="📜 PROMPT", bg=C["card"], fg=C["dim"], font=("Segoe UI", 7, "bold"),
            anchor="w", cursor="hand2",
        )
        self.prompt_ind_role.pack(fill="x", padx=8, pady=(4, 0))
        self.prompt_ind = tk.Label(
            pcard, text="Prompt : défaut", bg=C["card"], fg=C["dim"], font=("Segoe UI", 10, "bold"),
            anchor="w", justify="left", wraplength=136, cursor="hand2",
        )
        self.prompt_ind.pack(fill="x", padx=8, pady=(0, 5))
        for _w in (pcard, self.prompt_ind_role, self.prompt_ind):
            _w.bind("<Button-1>", self._prompt_quick_menu)
        self._tip(self.prompt_ind, "Prompt suivi par Padawan pour le rôle actif.\n"
                                   "Clic : menu de tes favoris (activer en 1 clic) · Ctrl+P = gérer")
        gplay = nav("🎮 Jouer", self._game_menu)
        gplay.configure(fg=C["gold"], font=("Segoe UI", 10, "bold"))
        gplay.bind("<Leave>", lambda e, b=gplay: b.configure(bg=C["card"], fg=C["gold"]), add="+")
        gplay.pack(fill="x", pady=(0, 4))
        self._tip(gplay, "Jeux de rôle textuels : Fallout québécois, polar Montréal 1947, donjon BBS…\n"
                         "Choix cliquables, Pip-Boy, sauvegardes · ✨ créer ton propre jeu")
        gnews = nav("📰 Nouvelles", self._news_menu)
        gnews.configure(fg=C["cyan"], font=("Segoe UI", 10, "bold"))
        gnews.bind("<Leave>", lambda e, b=gnews: b.configure(bg=C["card"], fg=C["cyan"]), add="+")
        gnews.pack(fill="x", pady=(0, 4), before=gplay)
        self._tip(gnews, "Briefings sourcés en un clic (vraie chasse web, sources datées) :\n"
                         "🌍 Géopoliticologue du futur · 🔭 Découvertes & avancées\n"
                         "24 h / semaine / ce qui a changé · gardés en .html dans briefings\\")

        gmods = nav("🧠 Modèles  Ctrl+M", self.show_models)  # v39.6
        gmods.configure(fg=C["ok"], font=("Segoe UI", 10, "bold"))
        gmods.bind("<Leave>", lambda e, b=gmods: b.configure(bg=C["card"], fg=C["ok"]), add="+")
        gmods.pack(fill="x", pady=(0, 4), after=gplay)
        self._tip(gmods, "🧠 Modèles (Ctrl+M) : ce que ton PC peut faire tourner,\n"
                         "tes modèles (activer / effacer), catalogue avec pastilles 🟢🟡🔴,\n"
                         "installation en un clic et banc d'essai côte à côte")
        gatl = nav("💻 Atelier  Ctrl+K", self.show_atelier)  # v40.0
        gatl.configure(fg=C["gold"], font=("Segoe UI", 10, "bold"))
        gatl.bind("<Leave>", lambda e, b=gatl: b.configure(bg=C["card"], fg=C["gold"]), add="+")
        gatl.pack(fill="x", pady=(0, 4), after=gmods)
        self._tip(gatl, "💻 Atelier (Ctrl+K) : mode programmeur avec qwen2.5-coder\n"
                         "chat à gauche, éditeur coloré à droite · 👁 aperçu · 🩺 corriger l'erreur\n"
                         "🚀 déployer (C:\\py, Web local, FTP/SFTP) · projets, modèles, snippets\n"
                         "🖼→ANSI : une image devient de l'art ANSI / ASCII (DOS, truecolor, Pip-Boy)")
        if _PS is not None:  # v41.0
            gstu = nav("🎨 Studio  Ctrl+G", self.show_studio)
            gstu.configure(fg=C["cyan"], font=("Segoe UI", 10, "bold"))
            gstu.bind("<Leave>", lambda e, b=gstu: b.configure(bg=C["card"], fg=C["cyan"]), add="+")
            gstu.pack(fill="x", pady=(0, 4), after=gatl)
            self._tip(gstu, "🎨 Studio d'images (Ctrl+G) : une idée en français → une image dessinée sur ton PC\n"
                            "(ComfyUI + SD-Turbo, sans internet) + sa version art ANSI côte à côte\n"
                            "styles en un clic · graine · variations · .png / .ans / .html · galerie")
        nav("Gare l'idée  Ctrl+I", self.park).pack(fill="x", pady=1)
        self.btn_inbox = nav(self._inbox_label(), self.show_prompts)
        self.btn_inbox.pack(fill="x", pady=1)
        self._tip(self.btn_inbox, "📜 Prompts (Ctrl+P) : tes prompts favoris à activer en un clic\n"
                                  "+ l'onglet 💡 Idées garées (ce que Ctrl+I met de côté)")
        nav("Tâches", self.show_tasks).pack(fill="x", pady=1)
        nav("Creuser", self.dig).pack(fill="x", pady=1)
        nav("Copier", self.copy_last).pack(fill="x", pady=1)
        nav("🧹 Nouvelle conversation  Ctrl+L", self.new_conversation).pack(fill="x", pady=1)
        nav("🕘 Historique  Ctrl+Shift+H", self.show_conv_history).pack(fill="x", pady=1)
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
        self._act_fr = act
        self.act_btns = {}
        nb = tk.Button(
            act, text="🧹 Nouvelle conversation", command=self.new_conversation,
            bg=C["gold"], fg="#1a1408", relief="flat", font=("Segoe UI", 9, "bold"),
            padx=12, pady=3, cursor="hand2", activebackground="#e4c48a", activeforeground="#1a1408",
        )
        nb.pack(side="right", padx=2)
        self._tip(nb, "Repart à neuf comme une nouvelle session (Ctrl+L ou Ctrl+Shift+N).\n"
                      "La conversation actuelle est archivée (🕘 Historique, Ctrl+Shift+H), rien n'est effacé.")
        self.act_btns["newconv"] = nb
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
        self._input_bar = bar
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
        self._chips_fr = chips
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
        self._hunt_fr = hunt
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
        self._chrome_fr = chrome

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
        # v39.2: changer de prompt en 2 clics
        self.prompt_quick = tk.Label(
            row2, text="📜 défaut ▾", bg=C["card"], fg=C["fg"], font=("Segoe UI", 9, "bold"),
            padx=10, pady=2, cursor="hand2", highlightthickness=1, highlightbackground=C["gold"],
        )
        self.prompt_quick.pack(side="left", padx=(0, 8))
        self.prompt_quick.bind("<Button-1>", self._prompt_quick_menu)
        self._tip(self.prompt_quick, "Activer un prompt favori en 1 clic (ou lancer un 🎮 jeu)\nCtrl+P = gérer mes prompts")
        _m0 = self.model
        _lab0 = next((lab for lab in self.mods if model_id_from_label(lab) == _m0), self.mods[0] if self.mods else _m0)
        self.mvar = tk.StringVar(value=_lab0)
        self.model_combo = ttk.Combobox(
            row2, textvariable=self.mvar, values=self.mods, state="readonly", width=24,
        )
        # v39.7 : 🧠 AVANT le sélecteur (avant il était coupé au bout de la rangée)
        _mb = tk.Label(row2, text="🧠", bg=C["bg"], fg=C["ok"], font=("Segoe UI", 11, "bold"), cursor="hand2")
        _mb.pack(side="left", padx=(0, 2))
        _mb.bind("<Button-1>", lambda e: self.show_models())
        self._tip(_mb, "🧠 Modèles (Ctrl+M) : diagnostic du PC, installer / comparer des modèles")
        if _PS is not None:  # v41.0
            _sb = tk.Label(row2, text="🎨", bg=C["bg"], fg=C["cyan"], font=("Segoe UI", 11, "bold"), cursor="hand2")
            _sb.pack(side="left", padx=(0, 2))
            _sb.bind("<Button-1>", lambda e: self.show_studio())
            self._tip(_sb, "🎨 Studio d'images (Ctrl+G)")
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
        self._build_game(mid)  # v39.3 🎮 (caché tant qu'aucun jeu n'est lancé)

        right = tk.Frame(self.split, bg=C["bg"], width=400)
        self.split.add(right, stretch="always", minsize=300)
        self._right_pane = right
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
            "2. Clique une carte Sources → les détails se déplient sur place ;\n"
            "   « Lire » → le texte complet s'affiche ici.\n"
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
        return f"📜 Prompts  Ctrl+P  · 💡{n}" if n else "📜 Prompts  Ctrl+P"

    def _refresh_inbox_badge(self):
        btn = getattr(self, "btn_inbox", None)
        if not btn:
            return
        try:
            btn.config(text=self._inbox_label())
        except Exception:
            pass
        win = getattr(self, "_prompts_win", None)
        try:
            if win is not None and win.winfo_exists():
                win._refresh_ideas()
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
        """Cartes Sources dépliables (padawan_cartes.py) ; l'ancien affichage sert de secours."""
        try:
            import padawan_cartes as _pc
            return _pc.draw_sources(self, globals())
        except Exception as e:
            log(f"cartes dépliables : {e}")
            return self._draw_sources_classic()

    def _draw_sources_classic(self):
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
        code_buf: List[str] = []
        code_lang = ""
        lines = text.split("\n")
        for k, line in enumerate(lines):
            nl = "\n" if k < len(lines) - 1 else ""
            st = line.strip()
            if st.startswith("```"):
                if not in_code:
                    code_buf, code_lang = [], st.strip("`").strip()
                else:
                    self._code_block_btns(widget, "\n".join(code_buf), code_lang)  # v40.0 📋
                in_code = not in_code
                continue
            if in_code:
                code_buf.append(line)
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
                text=GAME_INPUT_TIP if getattr(self, "game", None) else
                "Écris ici… Entrée = envoyer · Échap = annuler  ·  Voyant modèle: gris=check, or=load, vert=prêt, rouge=off",
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

        # v39.8 : mémorise l'état (file d'attente du jeu, chrono, repli)
        prev = getattr(self, "_model_state", "")
        self._model_state, self._model_detail = state, detail
        if state == "loading" and prev != "loading":
            self._model_load_t0 = time.time()
            self._model_slow_said = False
            self.after0(self._model_load_tick)
        elif state != "loading":
            self._model_load_t0 = 0.0

        def apply():
            if hasattr(self, "model_dot"):
                self.model_dot.config(fg=color)
            if hasattr(self, "model_lbl"):
                self.model_lbl.config(text=text, fg=color)
            if hasattr(self, "ollama_phase"):  # v39.8 : ligne fine = QUEL modèle (le gros libellé dit l'état)
                self.ollama_phase.config(text=self._phase_line(), fg=phase_fg)
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

    # ── v39.8 : chrono de chargement du modèle ──────────────────────────────
    MODEL_SLOW_S = 60  # au-delà : on propose le repli (dolphin3:8b)

    def _phase_line(self) -> str:
        name = self.current_model() if hasattr(self, "mvar") else (self.model or MODEL)
        st = getattr(self, "_model_state", "")
        t0 = getattr(self, "_model_load_t0", 0.0)
        if st == "loading" and t0:
            return f"🧠 {name} · {int(time.time() - t0)} s"
        if st == "error":
            return f"🧠 {name} · {(getattr(self, '_model_detail', '') or 'échec')[:40]}"
        if st == "down":
            return "Ollama arrêté"
        return f"🧠 {name}"

    def _model_load_tick(self):
        t0 = getattr(self, "_model_load_t0", 0.0)
        if not t0 or getattr(self, "_model_state", "") != "loading":
            return
        sec = int(time.time() - t0)
        try:
            self.ollama_phase.config(text=self._phase_line())
            detail = getattr(self, "_model_detail", "") or ""
            if not self.busy and "télécharg" not in detail.lower():
                self.status.config(text=f"● Modèle : chargement… {sec} s", fg=C["gold"])
        except Exception:
            pass
        if sec >= self.MODEL_SLOW_S and not getattr(self, "_model_slow_said", False):
            self._model_slow_said = True
            name = self.current_model()
            if not self.game and not self._same_model_id(name, MODEL):
                self.say("sys", f"⏳ {name} met plus de {self.MODEL_SLOW_S} s à se charger : il déborde sans doute de "
                                f"ta carte graphique (lent). Tu peux attendre, ou repasser à {MODEL} dans le sélecteur "
                                "(🧠 Modèles, Ctrl+M, pour comparer).")
        self.after(1000, self._model_load_tick)

    @staticmethod
    def _same_model_id(a: str, b: str) -> bool:
        f = lambda x: (x or "").strip().lower() if ":" in (x or "") else (x or "").strip().lower() + ":latest"
        return f(a) == f(b)

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
        self._model_before = None  # v39.6 : choix manuel = nouveau modèle par défaut
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
                ):  # v39.8 : la ligne fine dit QUEL modèle (avant : même texte en double)
                    self.ollama_phase.config(
                        text=clean if clean.startswith("Téléchargement") else self._phase_line(), fg=color)
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
        override: Optional[Dict[str, Any]] = None,
        question: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Chat Ollama. use_history=False isole le brief de chasse (anti context-bleed).
        v39.4: override = prompt ponctuel (📰 briefing) sans changer le favori actif."""
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
        # v39.3: un prompt perso actif a priorité (Remplacer = système tel quel, sans le style par défaut)
        ap = override or self.router.active_prompt()
        if ap and hunt_query and not override:
            user = (user + f"\n\n(PRIORITÉ : le prompt système personnalisé de Marc « {ap.get('name', '')} » "
                    "a priorité sur le format demandé ci-dessus.)")
        # Isolation stricte si use_history=False: pas de last_a / chat ancien / parked / ADN
        return chat_stream(
            model_id_from_label(self.mvar.get()), user,
            system=self.router.system_prompt(hunt_query=hunt_query,
                                             question=question or getattr(self, "last_q", "") or "",
                                             override=override),
            on_token=on_token,
            cancel=self._cancel,
            history=hist,
            raw_system=bool(ap and ap.get("mode") == "remplacer"),
            options=options,
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
        if getattr(self, "_last_kind", "chat") == "brief" and getattr(self, "_brief_ctx", None):
            return self.news_regenerate()
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
        if getattr(self, "game", None):  # v39.3 🎮 : la barre sert d'« Autre action… »
            self.var.set("")
            self._game_send(q)
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
            self._atelier_suggest(q)  # v40.0 : « 💻 Ouvrir dans l'Atelier » si ça ressemble à du code
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
                ans = self._ollama(f"{web}\n\n{extra}\n\nMarc: {q}"
                                   + ("" if self.router.active_prompt() else forme_vivante(q)), on_token=on_tok)
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
        """v39.2: l'Inbox vit maintenant dans 📜 Prompts → onglet 💡 Idées garées."""
        self.show_prompts(tab="idees")

    def _from_inbox(self, text, pop):
        try:
            pop.destroy()
        except Exception:
            pass
        self.hunt.set(text)
        self.var.set(text)
        self.ent.focus_set()

    # ── v39.2: 📜 Prompts (favoris, actif par rôle, menu rapide, test) ─────────
    def _theme_fix(self, w=None):
        """Applique le thème padawan_themes courant aux widgets créés après coup."""
        th = getattr(self, "_padawan_themer", None)
        if th is None or getattr(th, "key", "original") == "original":
            return
        old = th.root
        try:
            if w is not None:
                th.root = w
            th.recolor(th.key)
        except Exception:
            pass
        finally:
            th.root = old

    def show_prompts(self, tab: str = "prompts"):
        w = getattr(self, "_prompts_win", None)
        try:
            if w is not None and w.winfo_exists():
                w.deiconify()
                w.lift()
                w.focus_force()
                w.select_tab(tab)
                return
        except Exception:
            pass
        try:
            self._prompts_win = PromptsWindow(self, tab=tab)
        except Exception as e:
            log(f"prompts win: {e}")
            self.say("sys", f"📜 Prompts : ouverture impossible ({e})")

    # ── v40.0 💻 Atelier ─────────────────────────────────────────────────────
    def show_atelier(self, prefill: str = "", autosend: bool = False):
        if _PA is None:
            self.say("sys", "💻 Atelier : module padawan_atelier.py introuvable à côté de padawan39.py.")
            return
        if getattr(self, "game", None):  # v41.2 : avant, refus muet (message écrit dans le chat caché par le jeu)
            self._game_pause_for("💻 Atelier")
        a = getattr(self, "_atelier", None)
        try:
            if a is None or not a.winfo_exists():
                hooks = {"models": self._atelier_models, "current": self.current_model,
                         "switch": self._atelier_switch, "leave": self._atelier_left,
                         "gen_opts": self.gen_opts, "ready": lambda: bool(self.ready and self.model_ready)}
                a = self._atelier = _PA.Atelier(self, C, PRIVATE_DIR, base=OLLAMA, log=log, hooks=hooks)
            a.enter(prefill=prefill, autosend=autosend)
            self._ui_status("💻 Atelier", C["gold"])
        except Exception as e:
            log(f"atelier: {e}")
            self.say("sys", f"💻 Atelier : ouverture impossible ({e})")

    # ── v41.0 🎨 Studio d'images ─────────────────────────────────────────────
    def _studio_core(self):
        if _PS is None:
            return None
        core = getattr(self, "_studio", None)
        if core is None:
            core = self._studio = _PS.Studio(PRIVATE_DIR, ollama_base=OLLAMA, log=log)
            core.num_ctx = lambda: int(GEN.get("num_ctx") or 0) or _detect_num_ctx()
            self.after(60000, self._studio_idle_tick)
        return core

    def _studio_idle_tick(self):
        """Arrêt auto du moteur après N minutes sans image (réglable dans 🎨 Studio → ⚙ Moteur)."""
        core = getattr(self, "_studio", None)
        if core is None or self._quitting:
            return
        if not getattr(self, "_game_gen_busy", False):
            threading.Thread(target=core.engine.idle_check, daemon=True).start()
        self.after(60000, self._studio_idle_tick)

    def show_studio(self, idea: str = ""):
        if _PS is None:
            self.say("sys", "🎨 Studio : module padawan_studio.py introuvable à côté de padawan39.py.")
            return
        if getattr(self, "game", None):
            self._game_pause_for("🎨 Studio")
        try:
            v = getattr(self, "_studio_view", None)
            if v is None or not v.winfo_exists():
                hooks = {"current": self.current_model, "ready": lambda: bool(self.ready and self.model_ready),
                         "leave": self._studio_left, "atelier": self._studio_to_atelier}
                v = self._studio_view = _PS.StudioView(self, C, self._studio_core(), hooks=hooks)
            v.enter(idea=idea)
            self._ui_status("🎨 Studio", C["cyan"])
        except Exception as e:
            log(f"studio: {e}")
            self.say("sys", f"🎨 Studio : ouverture impossible ({e})")

    def _studio_left(self) -> None:
        """Retour du Studio : ComfyUI rend la carte graphique, puis le modèle de texte est rechargé d'avance."""
        core = getattr(self, "_studio", None)
        name = self.current_model()

        def work():
            try:
                if core is not None and core.engine.alive(timeout=0.5) and core.cfg.get("vram") != "jamais":
                    core.engine.free()
                    if not any(n == name or n.split(":")[0] == name.split(":")[0] for n, v in core.ollama.loaded() if v):
                        self.warm_model(name)
            except Exception as e:
                log(f"studio left: {e}")
        threading.Thread(target=work, daemon=True).start()
        try:
            self.ent.focus_set()
        except Exception:
            pass
        self._ui_status("Retour du Studio.", C["dim"])

    def _studio_to_atelier(self, path: str) -> None:
        self.show_atelier()
        a = getattr(self, "_atelier", None)
        if a is not None and a.winfo_exists() and not getattr(self, "game", None):
            a.ansi_studio(path)

    def _atelier_models(self) -> List[str]:
        out = []
        for lab in self.mods:
            if MODEL_DL_MARK in lab:
                continue
            out.append(model_id_from_label(lab))
        return out

    def _atelier_switch(self, name: str) -> None:
        """Bascule temporaire (jamais sauvée : _persist_cfg garde _model_before)."""
        try:
            name = self._model_local_id(name) or name
            cur = self.current_model()
            if not name or self._same_model_id(name, cur):
                return
            if getattr(self, "_model_before", None) is None:
                self._model_before = cur
            self._model_label_set(name)
            self.model, self.model_ready = name, False
            self._model_state = ""
            threading.Thread(target=self.warm_model, args=(name,), daemon=True).start()
        except Exception as e:
            log(f"atelier switch: {e}")

    def _atelier_left(self) -> None:
        self._model_sync_prompt()  # retour au modèle d'avant (ou à celui du prompt actif)
        try:
            self.ent.focus_set()
        except Exception:
            pass
        self._ui_status("Retour de l'Atelier.", C["dim"])

    def _atelier_suggest(self, q: str) -> None:
        if _PA is None:
            return
        try:
            if not _PA.looks_like_code_request(q):
                return
            self.chat.configure(state="normal")
            self.chat.insert("end", f"·  {clock()}\n💻 Ça ressemble à du code : l'Atelier (qwen2.5-coder, éditeur, aperçu) "
                                    "fait ça bien mieux que la chasse web.  ", "sys")
            b = tk.Button(self.chat, text="💻 Ouvrir dans l'Atelier avec cette demande", font=("Segoe UI", 9, "bold"),
                          bg=C["gold"], fg="#1a1408", relief="flat", cursor="hand2", padx=8,
                          command=lambda: (self.cancel_job() if self.busy else None,
                                           self.show_atelier(prefill=q, autosend=True)))
            self.chat.window_create("end", window=b)
            self.chat.insert("end", "\n\n", "sys")
            self.chat.configure(state="disabled")
        except Exception as e:
            log(f"atelier suggest: {e}")

    def _code_block_btns(self, widget, code: str, lang: str = "") -> None:
        """v40.0 : 📋 Copier (et 💻 Atelier) sous chaque bloc de code des réponses."""
        if not code.strip():
            return
        try:
            row = tk.Frame(widget, bg=C["panel"])
            tk.Button(row, text="📋 Copier le code", font=("Segoe UI", 8), bg=C["card"], fg=C["fg"], relief="flat",
                      cursor="hand2", padx=6, command=lambda: self._copy_text(code, "Code copié")).pack(side="left")
            if _PA is not None:
                tk.Button(row, text="💻 Ouvrir dans l'Atelier", font=("Segoe UI", 8), bg=C["card"], fg=C["gold"],
                          relief="flat", cursor="hand2", padx=6,
                          command=lambda: self._code_to_atelier(code, lang)).pack(side="left", padx=4)
            widget.window_create("end", window=row)
            widget.insert("end", "\n", "ai")
        except Exception as e:
            log(f"code btns: {e}")

    def _copy_text(self, text: str, msg: str = "Copié") -> None:
        self.clipboard_clear()
        self.clipboard_append(text)
        self._ui_status(f"📋 {msg} ({len(text.splitlines())} lignes)", C["ok"])

    def _code_to_atelier(self, code: str, lang: str = "") -> None:
        self.show_atelier()
        a = getattr(self, "_atelier", None)
        if a is not None and a.winfo_exists() and not getattr(self, "game", None):
            blk = (_PA.extract_blocks(f"```{lang}\n{code}\n```") or [{"lang": "text", "name": "", "code": code}])[0]
            a._apply_block(blk, None)

    # ── v40.0 copier / coller partout ────────────────────────────────────────
    def _install_clipboard(self) -> None:
        """Clic droit Couper/Copier/Coller/Tout sélectionner sur tous les Text/Entry, Ctrl+A,
        Ctrl+C sur une zone en lecture seule (chat), Maj-lock compris."""
        self._last_text_w = None

        def remember(e):
            self._last_text_w = e.widget
        for cls in ("Text", "Entry", "TEntry", "TCombobox"):
            self.bind_class(cls, "<Button-3>", self._ctx_menu, add="+")
        self.bind_class("Text", "<ButtonRelease-1>", remember, add="+")
        self.bind_class("Text", "<Control-a>", self._sel_all)
        self.bind_class("Text", "<Control-A>", self._sel_all)
        self.bind_class("Entry", "<Control-a>", self._sel_all)
        self.bind_class("Entry", "<Control-A>", self._sel_all)
        for cls in ("Text", "Entry"):
            self.bind_class(cls, "<Control-C>", lambda e: (e.widget.event_generate("<<Copy>>"), "break")[1])
            self.bind_class(cls, "<Control-X>", lambda e: (e.widget.event_generate("<<Cut>>"), "break")[1])
            self.bind_class(cls, "<Control-V>", lambda e: (e.widget.event_generate("<<Paste>>"), "break")[1])
        self.bind_all("<Control-c>", self._copy_fallback, add="+")
        try:
            self.ent.bind("<<Paste>>", self._ent_paste)
            self.ent.bind("<Shift-Return>", lambda e: (self._composer(self.var.get()), "break")[1])
        except Exception:
            pass

    def _sel_all(self, e):
        w = e.widget
        try:
            if isinstance(w, tk.Text):
                w.tag_add("sel", "1.0", "end-1c")
            else:
                w.select_range(0, "end")
                w.icursor("end")
        except Exception:
            pass
        return "break"

    def _copy_fallback(self, e):
        """Ctrl+C alors que le focus est ailleurs : copie la sélection de la dernière zone cliquée (chat)."""
        try:
            f = self.focus_get()
            if f is not None:
                try:
                    if isinstance(f, tk.Text) and f.tag_ranges("sel"):
                        return
                    if isinstance(f, tk.Entry) and f.selection_present():
                        return
                except Exception:
                    pass
            w = getattr(self, "_last_text_w", None)
            if w is not None and w.winfo_exists() and w.tag_ranges("sel"):
                self._copy_text(w.get("sel.first", "sel.last"), "Sélection copiée")
        except Exception:
            pass

    def _ctx_menu(self, e):
        w = e.widget
        try:
            if isinstance(w, tk.Text):
                idx = w.index(f"@{e.x},{e.y}")
                for tg in w.tag_names(idx):
                    if w.tag_bind(tg, "<Button-3>"):
                        return  # lien : son propre clic droit (ouvrir dans le navigateur)
            if str(w.bindtags()).find("AtelierKeys") >= 0 and isinstance(w, tk.Text) and w.bind("<Button-3>"):
                return
        except Exception:
            pass
        ro = False
        try:
            ro = str(w.cget("state")) in ("disabled", "readonly")
        except Exception:
            pass
        m = tk.Menu(self, tearoff=0)
        if not ro:
            m.add_command(label="Couper", accelerator="Ctrl+X", command=lambda: w.event_generate("<<Cut>>"))
        m.add_command(label="Copier", accelerator="Ctrl+C", command=lambda: self._ctx_copy(w))
        if not ro:
            m.add_command(label="Coller", accelerator="Ctrl+V", command=lambda: w.event_generate("<<Paste>>"))
        m.add_separator()
        m.add_command(label="Tout sélectionner", accelerator="Ctrl+A",
                      command=lambda: self._sel_all(type("E", (), {"widget": w})()))
        if isinstance(w, tk.Text):
            m.add_command(label="📋 Copier tout", command=lambda: self._copy_text(w.get("1.0", "end-1c"), "Tout copié"))
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()

    def _ctx_copy(self, w):
        try:
            if isinstance(w, tk.Text):
                if w.tag_ranges("sel"):
                    self._copy_text(w.get("sel.first", "sel.last"), "Sélection copiée")
            else:
                w.event_generate("<<Copy>>")
        except Exception:
            pass

    def _ent_paste(self, e):
        """Collage de plusieurs lignes dans la barre : ouvre l'éditeur multiligne (rien n'est envoyé)."""
        try:
            clip = self.clipboard_get()
        except Exception:
            return None
        if "\n" not in clip.strip("\r\n"):
            return None
        cur = self.var.get()
        try:
            if self.ent.selection_present():
                a, b = self.ent.index("sel.first"), self.ent.index("sel.last")
                cur = cur[:a] + cur[b:]
                pos = a
            else:
                pos = self.ent.index("insert")
        except Exception:
            pos = len(cur)
        self._composer(cur[:pos] + clip.replace("\r\n", "\n") + cur[pos:])
        return "break"

    def _composer(self, initial: str = "") -> None:
        """Zone de saisie multiligne : Entrée = envoyer, Maj+Entrée = nouvelle ligne."""
        d = tk.Toplevel(self)
        d.title("✍ Message sur plusieurs lignes")
        d.configure(bg=C["bg"])
        d.transient(self)
        w, h = 760, 380
        try:
            x = self.winfo_rootx() + (self.winfo_width() - w) // 2
            y = self.winfo_rooty() + self.winfo_height() - h - 80
            d.geometry(f"{w}x{h}+{max(0, x)}+{max(0, y)}")
        except Exception:
            d.geometry(f"{w}x{h}")
        bar = tk.Frame(d, bg=C["bg"])
        bar.pack(side="bottom", fill="x", padx=10, pady=8)
        t = tk.Text(d, wrap="word", bg=C["input"], fg=C["fg"], insertbackground=C["cursor"], font=("Segoe UI", 11),
                    relief="flat", padx=8, pady=6, undo=True)
        t.pack(fill="both", expand=True, padx=10, pady=(10, 0))
        t.insert("1.0", initial)
        t.focus_set()
        t.mark_set("insert", "end-1c")

        def go(e=None):
            txt = t.get("1.0", "end-1c").strip()
            d.destroy()
            if txt:
                self.var.set(txt)
                self.send()
            return "break"

        def keep():
            self.var.set(t.get("1.0", "end-1c").replace("\n", " ⏎ ").strip())
            d.destroy()
        t.bind("<Return>", go)
        t.bind("<KP_Enter>", go)
        t.bind("<Shift-Return>", lambda e: None)
        d.bind("<Escape>", lambda e: d.destroy())
        tk.Button(bar, text="Envoyer  (Entrée)", command=go, bg=C["gold"], fg="#1a1408", relief="flat",
                  font=("Segoe UI", 10, "bold"), padx=14, pady=4, cursor="hand2").pack(side="right")
        tk.Button(bar, text="Annuler", command=d.destroy, bg=C["card"], fg=C["fg"], relief="flat",
                  font=("Segoe UI", 10), padx=10, pady=4, cursor="hand2").pack(side="right", padx=6)
        if _PA is not None:
            tk.Button(bar, text="💻 Envoyer à l'Atelier", command=lambda: (d.destroy(), self.show_atelier(
                prefill=t.get("1.0", "end-1c").strip(), autosend=True)) if t.get("1.0", "end-1c").strip() else None,
                      bg=C["card"], fg=C["gold"], relief="flat", font=("Segoe UI", 10), padx=10, pady=4,
                      cursor="hand2").pack(side="left")
        tk.Label(bar, text="Maj+Entrée = nouvelle ligne · Échap = fermer", bg=C["bg"], fg=C["dim"],
                 font=("Segoe UI", 8)).pack(side="left", padx=8)

    # ── v39.6 🧠 Modèles ─────────────────────────────────────────────────────
    def show_models(self, tab: str = "machine"):
        if _PM is None:
            self.say("sys", "🧠 Modèles : module padawan_modeles.py introuvable.")
            return
        w = getattr(self, "_models_win", None)
        try:
            if w is not None and w.winfo_exists():
                w.deiconify()
                w.lift()
                w.focus_force()
                w.select_tab(tab)
                return
        except Exception:
            pass
        try:
            self._models_win = _PM.ModelsWindow(self, C, os.path.join(PRIVATE_DIR, "modeles.json"),
                                                tab=tab, base=OLLAMA, log=log)
        except Exception as e:
            log(f"models win: {e}")
            self.say("sys", f"🧠 Modèles : ouverture impossible ({e})")

    def current_model(self) -> str:
        try:
            return model_id_from_label(self.mvar.get())
        except Exception:
            return self.model

    def gen_opts(self) -> Dict[str, Any]:
        return gen_options()

    def _model_label_set(self, name: str) -> None:
        for lab in self.mods:
            if model_id_from_label(lab) == name and MODEL_DL_MARK not in lab:
                self.mvar.set(lab)
                return
        self.mods = [name] + [m for m in self.mods if model_id_from_label(m) != name]
        try:
            self.model_combo.config(values=self.mods)
        except Exception:
            pass
        self.mvar.set(name)

    def _model_local_id(self, name: str) -> str:
        """Id exact du sélecteur correspondant à name (« dolphin-mistral » ↔ « dolphin-mistral:latest »), "" si absent."""
        n = (name or "").strip().lower()
        n2 = n if ":" in n else n + ":latest"
        for lab in self.mods:
            if MODEL_DL_MARK in lab:
                continue
            i = model_id_from_label(lab)
            l = i.lower()
            if l in (n, n2) or (l if ":" in l else l + ":latest") == n2:
                return i
        return ""

    def _model_is_local(self, name: str) -> bool:
        return bool(self._model_local_id(name))

    def models_refresh_selector(self, select: Optional[str] = None) -> None:
        """Relit /api/tags (thread) et met à jour le sélecteur (+ éditeur de prompts)."""
        def work():
            mods = models()
            def apply():
                cur = self.current_model()
                self.mods = mods
                try:
                    self.model_combo.config(values=mods)
                except Exception:
                    pass
                target = select or cur
                for lab in mods:
                    if model_id_from_label(lab) == target:
                        self.mvar.set(lab)
                        break
                win = getattr(self, "_prompts_win", None)
                try:
                    if win is not None and win.winfo_exists():
                        win._model_cb_refresh()
                except Exception:
                    pass
            self.after0(apply)
        threading.Thread(target=work, daemon=True).start()

    def model_activate(self, name: str) -> None:
        """⭐ Activer (panneau 🧠) : devient le modèle par défaut (sauvé dans la config)."""
        self._model_label_set(name)
        self.on_model_chosen()

    def _model_target(self) -> str:
        """Modèle voulu par le jeu en cours ou le prompt actif du rôle ("" = aucun)."""
        try:
            if self.game:
                p = getattr(self, "_game_override", None) or self.prompts.get(self.game.get("pid", "")) or {}
                pm = (p.get("model") or "").strip()
                if pm:
                    return pm
                base = getattr(self, "_model_before", None) or self.current_model()
                if is_code_model(base):
                    return self._game_play_model()  # v41.1 : un « coder » ne fait pas un bon MJ
                return ""
            p = self.prompts.active_for(self.router.active)
            return ((p or {}).get("model") or "").strip()
        except Exception:
            return ""

    def _game_play_model(self) -> str:
        """v41.1 : dolphin3:8b si installé, sinon le meilleur modèle installé non-code (pas de 70b)."""
        best = self._model_local_id(MODEL)
        if best:
            return best
        ids = [model_id_from_label(m) for m in (getattr(self, "mods", None) or [])]
        ok = [i for i in ids if i and not is_code_model(i) and not re.search(r"\b(70|72|65|34|32)b", i)
              and "embed" not in i]
        for pref in ("dolphin", "qwen2.5:", "llama", "mistral", "gemma"):
            for i in ok:
                if pref in i:
                    return i
        return ok[0] if ok else ""

    def _model_sync_prompt(self) -> None:
        """v39.6 : bascule temporaire vers le modèle du prompt/jeu, ou retour au modèle d'avant.
        Jamais sauvé dans la config : au prochain lancement, Chercheur + modèle par défaut."""
        try:
            want = self._model_target()
            before = getattr(self, "_model_before", None)
            cur = self.current_model()
            if want:
                want = self._model_local_id(want) or model_id_from_label(want)
                if want == cur:
                    return
                if not self._model_is_local(want):
                    self.say("sys", f"🧠 Le modèle « {want} » de ce prompt n'est pas installé — je garde {cur}. "
                                    "Installe-le dans 🧠 Modèles (Ctrl+M).")
                    return
                if before is None:
                    self._model_before = cur
                self._model_label_set(want)
                self.model, self.model_ready = want, False
                threading.Thread(target=self.warm_model, args=(want,), daemon=True).start()
                if self.game:
                    self._game_sys_safe(f"🧠 Jeu → {want} (meilleur conteur ; {self._model_before} revient en quittant, "
                                        "rien n'est sauvé).")
                else:
                    self.say("sys", f"🧠 Modèle du prompt : {want} (retour à {self._model_before} en quittant).")
            elif before:
                self._model_before = None
                if before != cur:
                    self._model_label_set(before)
                    self.model, self.model_ready = before, False
                    threading.Thread(target=self.warm_model, args=(before,), daemon=True).start()
                    self.say("sys", f"🧠 Retour au modèle {before}.")
        except Exception as e:
            log(f"model sync: {e}")

    def _prompt_name_for(self, role: Optional[str] = None) -> str:
        role = role or self.router.active
        st = getattr(self, "prompts", None)
        p = st.active_for(role) if st else None
        return p["name"] if p else ""

    def _refresh_prompt_ui(self):
        try:
            role = self.router.active
            name = self._prompt_name_for(role)
            if getattr(self, "game", None):
                name = "🎮 " + str(self.game.get("name", "Jeu")).lstrip("🎮 ")
            lab = RoleRouter.ROLES[role]["label"]
            if hasattr(self, "prompt_ind"):
                self.prompt_ind_role.config(text=f"📜 PROMPT · {lab.upper()}")
                self.prompt_ind.config(text=(f"⭐ {name}" if name else "Prompt : défaut"),
                                       fg=C["gold"] if name else C["dim"])
                self._theme_fix(self.prompt_ind.master)
            if hasattr(self, "prompt_quick"):
                short = name if len(name) <= 24 else name[:23] + "…"
                self.prompt_quick.config(text=f"📜 {short or 'défaut'} ▾", fg=C["gold"] if name else C["fg"])
                self._theme_fix(self.prompt_quick)
            win = getattr(self, "_prompts_win", None)
            if win is not None and win.winfo_exists():
                win._refresh_from_app()
        except Exception as e:
            log(f"prompt ui: {e}")

    def _prompt_set_active(self, pid: Optional[str], role: Optional[str], *, switch_role: bool = False) -> List[str]:
        """pid=None → défaut (role=None: tous les rôles). Retourne les rôles touchés.
        v39.3: un prompt propre à un rôle bascule Padawan sur ce rôle (switch_role) + confirmation claire."""
        st = self.prompts
        if pid is not None:
            p = st.get(pid)
            if p and p.get("kind") == "jeu":
                self.game_start(pid)
                return []
            if p and p["role"] != "tous" and role not in (None, p["role"]):
                role = p["role"]
            if p and switch_role and p["role"] != "tous" and p["role"] != self.router.active:
                self.set_role(p["role"])
        if self.game and pid is not None:
            self.game_quit()
        if pid is None:
            st.reset(role)
            roles = [role] if role else list(RoleRouter_ROLE_IDS)
            who = RoleRouter.ROLES[role]["label"] if role else "tous les rôles"
            msg = f"📜 Prompt d'origine rétabli ({who})."
        else:
            roles = st.activate(pid, role)
            p = st.get(pid) or {"name": "?"}
            labs = ", ".join(RoleRouter.ROLES[r]["label"] for r in roles) or "aucun rôle"
            msg = f"📜 Prompt activé : « {p['name']} » (rôle : {labs})."
        ok = st.save()
        self._refresh_prompt_ui()
        self.say("sys", msg if ok else f"{msg} (⚠ {st.error})")
        self._model_sync_prompt()  # v39.6 : modèle propre au prompt (ou retour au modèle d'avant)
        return roles

    def _prompt_quick_menu(self, event=None):
        role = self.router.active
        lab = RoleRouter.ROLES[role]["label"]
        st = self.prompts
        cur = st.active_id(role) if st.active_for(role) else ""
        m = tk.Menu(self, tearoff=0, bg=C["card"], fg=C["fg"], activebackground=C["gold"],
                    activeforeground="#1a1408", font=("Segoe UI", 11), bd=0)
        games = self._game_prompts()
        gcur = (self.game or {}).get("pid", "")
        if games:
            m.add_command(label="🎮  JEUX — clic = jouer", state="disabled")
            for p in games:
                m.add_command(label=f"{'▶' if p['id'] == gcur else '    '}  {p['name']}",
                              command=lambda pid=p["id"]: self.game_start(pid))
            if self.game:
                m.add_command(label="     ↩ Quitter le jeu", command=self.game_quit)
            m.add_separator()
        m.add_command(label=f"💬  PROMPTS — rôle actuel : {lab}", state="disabled")
        m.add_command(label=f"{'⭐' if not cur and not self.game else '    '}  ↩ Défaut — {lab}",
                      command=lambda: self._prompt_set_active(None, role))
        normal = [p for p in st.all() if p.get("kind") != "jeu"]
        if not normal:
            m.add_command(label="     (aucun favori — Ctrl+P pour en créer)", state="disabled")
        for p in normal:
            star = "⭐" if p["id"] == cur else "    "
            if p["role"] in ("tous", role):
                tag = "" if p["role"] == "tous" else f"   · {PROMPT_ROLE_LABELS[p['role']]}"
                m.add_command(label=f"{star}  {p['name']}{tag}",
                              command=lambda pid=p["id"]: self._prompt_set_active(pid, role))
            else:
                m.add_command(label=f"{star}  {p['name']}   → passe en {PROMPT_ROLE_LABELS[p['role']]}",
                              command=lambda pid=p["id"], r=p["role"]: self._prompt_set_active(pid, r, switch_role=True))
        m.add_separator()
        m.add_command(label="     ↩ Tout remettre par défaut (4 rôles)",
                      command=lambda: self._prompt_set_active(None, None))
        m.add_command(label="     ✨ Créer un jeu avec Padawan…", command=self.game_generate)
        m.add_command(label="     📜 Gérer mes prompts…   Ctrl+P", command=self.show_prompts)
        self._theme_fix(m)
        if event is not None:
            x, y = event.x_root, event.y_root
        else:
            x, y = self.winfo_pointerx(), self.winfo_pointery()
        try:
            m.tk_popup(x, y)
        finally:
            m.grab_release()

    def _prompt_test(self, override, role_id: str, question: str, *, name: str = "prompt") -> bool:
        """🧪 Pose une question test avec un prompt (même non enregistré) sans toucher l'actif ni l'historique."""
        if self.busy:
            self.say("sys", "🧪 Padawan est occupé — réessaie dans un instant (Échap = annuler).")
            return False
        if not self.ready or not self.model_ready:
            if not self._ensure_model_ready_or_kick():
                return False
        q = (question or PROMPT_TEST_Q).strip()
        rid = role_id if role_id in RoleRouter.ROLES else self.router.active
        self.say("sys", f"🧪 Test du prompt « {name} » ({RoleRouter.ROLES[rid]['label']}) — question : {q}")
        self.lock(True, "🧪 test du prompt…")
        threading.Thread(target=self._prompt_test_worker, args=(override, rid, q), daemon=True).start()
        return True

    def _prompt_test_worker(self, override, rid: str, q: str):
        try:
            mark_holder: list = []
            buf: list = []
            self.after0(lambda: mark_holder.append(self._begin_stream()))
            time.sleep(0.05)

            def on_tok(t: str):
                if mark_holder:
                    self.after0(self._append_stream, mark_holder[0], t, buf)

            system = self.router.system_prompt(question=q, override=override, role_id=rid,
                                               use_default=override is None)
            ans = chat_stream(
                model_id_from_label(self.mvar.get()), q, system=system,
                on_token=on_tok, cancel=self._cancel, history=[],
            )
            if self._cancel.is_set():
                self.after0(self.say, "sys", "🧪 Test annulé.")
                return
            self.after0(self._prompt_test_finish, mark_holder[0] if mark_holder else "", ans)
        except Exception as e:
            self.after0(self.say, "sys", f"🧪 Test : {e}")
        finally:
            self.after0(self.lock, False, "● prêt")

    def _prompt_test_finish(self, mark: str, full: str):
        full = clean(full or "") or "(réponse vide)"
        self.chat.configure(state="normal")
        try:
            if mark:
                self.chat.delete(mark, "end")
        except Exception:
            pass
        self._insert_linked(self.chat, full + "\n\n", "ai")
        self.chat.configure(state="disabled")
        self._chat_follow_end(force=True)

    # ══ v39.3 : 🎮 MODE JEU ═══════════════════════════════════════════════════
    def _build_game(self, mid):
        G = GAME_COLORS
        self.game = None
        self._game_compact = self.winfo_screenheight() < 860
        self._game_dice = bool(self.cfg.get("game_dice", True))
        self._game_sound = bool(self.cfg.get("game_sound", False))
        self._game_images = bool(self.cfg.get("game_images", True))        # v40.2 🖼
        self._game_images_anim = bool(self.cfg.get("game_images_anim", True))
        self._game_images_gen = bool(self.cfg.get("game_images_gen", False))  # v41.0 🎨 images générées
        self._game_gen_q: List[Any] = []        # demandes en attente (la plus récente gagne)
        self._game_gen_busy = False
        self._game_gen_mem: Dict[str, Any] = {}  # hash de scène → Art (cache mémoire)
        self._game_img_ph: Dict[int, Any] = {}   # index du journal → (PhotoImage, taille, famille)
        self._game_gen_times: List[Dict[str, Any]] = []
        self._game_imgs: List[Any] = []          # PhotoImage vivantes (sinon Tk les efface)
        self._game_img_cache: Dict[Any, Any] = {}
        self._game_pick_cache: Dict[Any, str] = {}
        self._game_img_seq = 0
        self.game_wrap = tk.Frame(mid, bg=G["bg"], highlightbackground=G["line"], highlightthickness=1)
        hdr = tk.Frame(self.game_wrap, bg=G["bg"])
        hdr.pack(side="top", fill="x", padx=6, pady=(5, 3))
        self.game_title = tk.Label(hdr, text="🎮", bg=G["bg"], fg=G["amber"], font=("Consolas", 13, "bold"),
                                   anchor="w")
        self.game_title.pack(side="left", fill="x", expand=True)
        self.game_btns = {}

        def gbtn(key, text, cmd, tip):
            b = tk.Button(hdr, text=text, command=cmd, bg=G["btn"], fg=G["fg"], relief="flat",
                          font=("Segoe UI", 9, "bold"), padx=8, pady=3, cursor="hand2",
                          activebackground=G["green"], activeforeground="#021006", bd=0)
            b.bind("<Enter>", lambda e, w=b: w.configure(bg=G["btnh"]))
            b.bind("<Leave>", lambda e, w=b: w.configure(bg=G["btn"]))
            self._tip(b, tip)
            self.game_btns[key] = b
            return b

        for key, text, cmd, tip in (
            ("quit", "↩ Quitter", self.game_quit, "Quitter le jeu (la partie est sauvegardée automatiquement)\n"
                                                    "Padawan reprend son prompt et son rôle d'avant."),
            ("images", "", self._game_toggle_images, "🖼 Illustrations ANSI des scènes\n"
                                                       "BANQUE = images originales rétro, effet CRT · GÉNÉRÉES = la scène est dessinée\n"
                                                       "par le 🎨 Studio en arrière-plan (la banque s'affiche d'abord) · FIXES = banque sans\n"
                                                       "animation · NON = art ASCII. Réglage gardé par jeu. Clique une image pour l'agrandir."),
            ("sound", "", self._game_toggle_sound, "Petits bips façon Pip-Boy à chaque tour (désactivés par défaut)"),
            ("dice", "", self._game_toggle_dice, "Dés réels : Padawan lance un vrai d20 local à chaque tour\n"
                                                   "et l'envoie au maître du jeu ([JET d20 = N])."),
            ("export", "📜 Exporter", self.game_export, "Exporter l'aventure en .html (joli) ou .txt"),
            ("load", "📂 Charger", self.game_load, "Charger une partie sauvegardée"),
            ("save", "💾 Sauver", self.game_save, "Sauvegarder la partie dans un fichier"),
            ("new", "🆕 Nouvelle", self.game_new, "🆕 Nouvelle partie : recommencer à zéro (confirmation)"),
        ):
            gbtn(key, text, cmd, tip).pack(side="right", padx=2)
        self.game_title.configure(width=1)  # v40.2 : le titre (long) se coupe au lieu de cacher des boutons
        self._game_tb_full = {k: w.cget("text") for k, w in self.game_btns.items()
                              if k in ("quit", "export", "load", "save", "new")}
        self._game_tb_compact = 0
        hdr.bind("<Configure>", lambda e: self._game_paint_toggles(), add="+")
        self._game_paint_toggles()

        self.game_choices = tk.Frame(self.game_wrap, bg=G["bg"])
        self.game_choices.pack(side="bottom", fill="x", padx=6, pady=(2, 4))
        self.game_hint = tk.Label(
            self.game_wrap, text="", bg=G["bg"], fg=G["dim"], font=("Segoe UI", 9, "italic"), anchor="w")
        self.game_hint.pack(side="bottom", fill="x", padx=8)

        body = tk.Frame(self.game_wrap, bg=G["bg"])
        body.pack(side="top", fill="both", expand=True, padx=6)
        # ☢ Pip-Boy (panneau de droite)
        self.pip = tk.Frame(body, bg=G["pip"], width=280, highlightbackground=G["green"], highlightthickness=1)
        self.pip.pack(side="right", fill="y", padx=(6, 0))
        self.pip.pack_propagate(False)
        self.pip_title = tk.Label(self.pip, text="▓▓ PIP-BOY 3000 ▓▓", bg=G["pip"], fg=G["green"],
                                  font=("Consolas", 12, "bold"))
        self.pip_title.pack(fill="x", pady=(6, 2))
        self.pip_bars = tk.Canvas(self.pip, bg=G["pip"], highlightthickness=0, height=10)
        self.pip_bars.pack(fill="x", padx=8)
        self.pip_txt = tk.Text(self.pip, bg=G["pip"], fg=G["fg"], relief="flat", bd=0, wrap="word",
                               font=("Consolas", 9), padx=8, pady=4, highlightthickness=0, cursor="arrow",
                               state="disabled")
        self.pip_txt.pack(fill="both", expand=True)
        self.pip_txt.tag_configure("h", foreground=G["green"], font=("Consolas", 10, "bold"), spacing1=6)
        self.pip_txt.tag_configure("k", foreground=G["dim"])
        self.pip_txt.tag_configure("v", foreground=G["fg"])
        self.pip_txt.tag_configure("cur", foreground=G["amber"], font=("Consolas", 9, "bold"))
        self.pip_txt.tag_configure("old", foreground=G["dim"], overstrike=True)
        self.pip_bars.bind("<Configure>", lambda e: self._game_draw_bars())

        tw = tk.Frame(body, bg=G["panel"])
        tw.pack(side="left", fill="both", expand=True)
        self.game_txt = tk.Text(
            tw, wrap="word", bg=G["panel"], fg=G["fg"], relief="flat", bd=0, padx=14, pady=10,
            font=("Segoe UI", 12), highlightthickness=0, cursor="arrow", spacing1=1, spacing3=3,
            insertbackground=G["green"], selectbackground=G["btnh"],
        )
        gsb = ttk.Scrollbar(tw, orient="vertical", command=self.game_txt.yview)
        self.game_txt.configure(yscrollcommand=gsb.set, state="disabled")
        self.game_txt.pack(side="left", fill="both", expand=True)
        gsb.pack(side="right", fill="y")
        T = self.game_txt
        T.tag_configure("title", foreground=G["amber"], font=("Consolas", 16, "bold"), spacing1=10, spacing3=6)
        T.tag_configure("art", foreground=G["green"], background=G["art"], font=("Consolas", 11),
                        lmargin1=18, lmargin2=18, spacing1=0, spacing3=0, wrap="none")
        T.tag_configure("status", foreground=G["green"], background=G["pip"], font=("Consolas", 10),
                        lmargin1=18, lmargin2=18, spacing1=0, spacing3=0, wrap="none")
        T.tag_configure("narr", foreground=G["fg"], font=("Segoe UI", 12))
        T.tag_configure("gimgline", lmargin1=14, lmargin2=14, spacing1=2, spacing3=4, font=("Consolas", 2))
        T.tag_configure("bold", font=("Segoe UI", 12, "bold"), foreground="#ffffff")
        T.tag_configure("dlg", foreground=G["amber"])
        T.tag_configure("check", foreground=G["cyan"], font=("Consolas", 11, "bold"))
        T.tag_configure("ask", foreground=G["amber"], font=("Consolas", 12, "bold"), spacing1=8)
        T.tag_configure("choice", foreground=G["green"], font=("Segoe UI", 12, "bold"), lmargin1=12, lmargin2=34)
        T.tag_configure("choice_hot", background=G["btnh"])
        T.tag_configure("you", foreground=G["amber"], font=("Consolas", 11, "bold"), spacing1=10)
        T.tag_configure("sys", foreground=G["dim"], font=("Segoe UI", 9, "italic"))
        T.tag_configure("stream", foreground=G["dim"], font=("Consolas", 10))
        T.tag_bind("choice", "<Enter>", lambda e: T.configure(cursor="hand2"))
        T.tag_bind("choice", "<Leave>", lambda e: T.configure(cursor="arrow"))
        T.tag_bind("choice", "<Button-1>", self._game_click_choice)
        self.ent.bind("<KeyPress>", self._game_key_ent, add="+")
        self.bind("<KeyPress>", self._game_key_any, add="+")

    def _game_tb_texts(self, level: int) -> Dict[str, str]:
        """Textes de la barre du jeu : 0 = complets, 1 = abrégés, 2 = icônes (fenêtre très étroite)."""
        d, s_ = getattr(self, "_game_dice", True), getattr(self, "_game_sound", False)
        im, an = getattr(self, "_game_images", True), getattr(self, "_game_images_anim", True)
        gen = im and an and self._game_gen_on(check_engine=False)
        img_s = ("🖼 G" if gen else "🖼 B" if an else "🖼 F") if im else "🖼 NON"
        if level >= 2:
            return {"quit": "↩", "export": "📜", "load": "📂", "save": "💾", "new": "🆕",
                    "dice": "🎲 OUI" if d else "🎲 NON", "sound": "🔊" if s_ else "🔈", "images": img_s}
        if level == 1:
            return {"quit": "↩ Quitter", "export": "📜 Export", "load": "📂 Charger", "save": "💾 Sauver",
                    "new": "🆕 Nouv.", "dice": "🎲 Dés OUI" if d else "🎲 Dés NON",
                    "sound": "🔊 Sons OUI" if s_ else "🔈 Sons NON",
                    "images": ("🖼 Génér." if gen else "🖼 Banque" if an else "🖼 Fixes") if im else "🖼 Img NON"}
        t = dict(getattr(self, "_game_tb_full", {}))
        t["dice"] = "🎲 Dés : OUI" if d else "🎲 Dés : NON"
        t["sound"] = "🔊 Sons : OUI" if s_ else "🔈 Sons : NON"
        t["images"] = (("🖼 Images : GÉNÉRÉES" if gen else "🖼 Images : BANQUE") if an else "🖼 Images : FIXES") \
            if im else "🖼 Images : NON"
        return t

    def _game_paint_toggles(self):
        b = getattr(self, "game_btns", {})
        if b and "quit" in b and hasattr(self, "_game_tb_full"):  # v40.2 : textes complets / abrégés / icônes
            level = 0
            try:
                import tkinter.font as _tkf
                hw = self.game_title.master.winfo_width()
                if hw > 50:
                    f = _tkf.Font(font=b["quit"].cget("font"))
                    for level, room in ((0, 240), (1, 60), (2, 0)):
                        need = sum(f.measure(x) + 26 for x in self._game_tb_texts(level).values()) + room
                        if need <= hw:
                            break
            except Exception:
                level = 0
            self._game_tb_compact = level
            for k, x in self._game_tb_texts(level).items():
                if k in b and b[k].cget("text") != x:
                    b[k].configure(text=x)
            return
        if "dice" in b:
            b["dice"].configure(text="🎲 Dés : OUI" if self._game_dice else "🎲 Dés : NON")
        if "sound" in b:
            b["sound"].configure(text="🔊 Sons : OUI" if self._game_sound else "🔈 Sons : NON")
        if "images" in b:
            on = getattr(self, "_game_images", True)
            b["images"].configure(text=self._game_tb_texts(0).get("images", "🖼 Images"))

    def _game_img_mode(self) -> str:
        if not getattr(self, "_game_images", True):
            return "non"
        if not getattr(self, "_game_images_anim", True):
            return "fixes"
        return "gen" if getattr(self, "_game_images_gen", False) else "banque"

    def _game_set_img_mode(self, mode: str, save: bool = True) -> None:
        self._game_images = mode != "non"
        self._game_images_anim = mode in ("banque", "gen")
        self._game_images_gen = mode == "gen"
        if save:
            self.cfg["game_images"] = self._game_images
            self.cfg["game_images_anim"] = self._game_images_anim
            self.cfg["game_images_gen"] = self._game_images_gen
            fam = game_img_family((self.game or {}).get("builtin", ""))
            if fam:  # v41.0 : réglage gardé par jeu (et dernier choix = défaut des autres)
                per = dict(self.cfg.get("game_images_per") or {})
                per[fam] = mode
                self.cfg["game_images_per"] = per

    def _game_load_img_mode(self) -> None:
        fam = game_img_family((self.game or {}).get("builtin", ""))
        m = (self.cfg.get("game_images_per") or {}).get(fam) if fam else None
        if m in ("banque", "gen", "fixes", "non"):
            self._game_set_img_mode(m, save=False)

    def _game_gen_on(self, check_engine: bool = True) -> bool:
        if not getattr(self, "_game_images_gen", False) or _PS is None:
            return False
        if not check_engine:
            return True
        core = self._studio_core()
        return bool(core and core.engine.ready_to_run())

    def _game_toggle_images(self):
        """BANQUE (animé) → GÉNÉRÉES → FIXES → NON → BANQUE (GÉNÉRÉES sauté si le moteur n'est pas installé)."""
        order = ["banque", "gen", "fixes", "non"]
        cur = self._game_img_mode()
        nxt = order[(order.index(cur) + 1) % len(order)]
        if nxt == "gen":
            core = self._studio_core() if _PS is not None else None
            if not (core and core.engine.ready_to_run()):
                nxt = "fixes"
                self._game_flash("🎨 Images générées : installe d'abord le moteur (🎨 Studio, Ctrl+G hors jeu).")
            else:
                self._game_flash("🎨 Images générées : la scène est dessinée en arrière-plan (la banque d'abord, "
                                 "≈ 15-20 s), gardée en cache.")
        self._game_set_img_mode(nxt)
        self._game_paint_toggles()  # enregistré dans config.json à la sortie, comme 🎲 et 🔊
        if self.game and not self.busy:
            self._game_rerender()

    # ---- 🖼 v40.2 illustrations ANSI
    def _game_img_on(self) -> bool:
        st = self.game or {}
        return bool(getattr(self, "_game_images", False) and game_img_family(st.get("builtin", ""))
                    and _ANSI is not None and _ANSI.load_pil() and _ANSI.ImageTk is not None)

    def _game_gen_art(self, h: str):
        """Art ANSI d'une scène générée (cache disque C:\\web_private\\Padawan\\studio\\cache)."""
        if not h:
            return None
        a = self._game_gen_mem.get(h)
        if a is None and _PS is not None:
            core = self._studio_core()
            a = core.cache_get(h) if core else None
            if a is not None:
                if len(self._game_gen_mem) > 60:
                    self._game_gen_mem.clear()
                self._game_gen_mem[h] = a
        return a

    def _game_li_art(self, li: Optional[int]):
        """(art généré, hash) pour l'entrée li du journal en mode GÉNÉRÉES, sinon (None, "")."""
        if li is None or li < 0 or not self._game_gen_on(check_engine=False):
            return None, ""
        try:
            h = ((self.game or {}).get("log") or [])[li].get("img_gen", "")
        except Exception:
            return None, ""
        a = self._game_gen_art(h)
        return (a, h) if a is not None else (None, "")

    def _game_img_pil(self, fam: str, key: str, cw: int, art=None, tag: str = ""):
        ck = (fam, key, cw, tag)
        im = self._game_img_cache.get(ck)
        if im is None:
            a = art if art is not None else _ANSI.bank_art(game_img_bank(), fam, key)
            if a is None:
                return None
            im = _ANSI.render_image(a, cw).convert("RGB")
            # lignes de balayage CRT discrètes (1 ligne sur 3 un peu plus sombre)
            if cw >= 4:
                from PIL import ImageDraw as _D
                dr = _D.Draw(im, "RGBA")
                for y in range(2, im.size[1], 3):
                    dr.line([(0, y), (im.size[0], y)], fill=(0, 0, 0, 70))
            if len(self._game_img_cache) > 80:
                self._game_img_cache.clear()
            self._game_img_cache[ck] = im
        return im

    def _game_img_cw(self, art) -> int:
        T = self.game_txt
        w = T.winfo_width() if T.winfo_width() > 200 else 760
        h = T.winfo_height() if T.winfo_height() > 200 else 480
        cw = (w - 60) // max(1, art.cols)
        cw = min(cw, int(h * 0.52) // max(1, 2 * art.nrows))  # l'image laisse de la place au texte
        return max(3, min(9, cw))

    def _game_img(self, key: str, animate: bool = False, li: Optional[int] = None):
        """Insère l'illustration (clé) dans le fil du jeu, avec révélation CRT facultative.
        v41.0 : en mode GÉNÉRÉES, l'image dessinée pour cette scène (li) remplace celle de la banque."""
        st = self.game or {}
        fam = game_img_family(st.get("builtin", ""))
        b = game_img_bank()
        a = _ANSI.bank_art(b, fam, key) if (fam and key) else None
        if a is None:
            return
        ga, gh = self._game_li_art(li)
        if ga is not None and (ga.cols, ga.nrows) == (a.cols, a.nrows):
            a = ga
        else:
            gh = ""
        im = self._game_img_pil(fam, key, self._game_img_cw(a), art=a if gh else None, tag=gh)
        if im is None:
            return
        G = GAME_COLORS
        T = self.game_txt
        try:
            ph = _ANSI.ImageTk.PhotoImage(im, master=T)
        except Exception as e:
            log(f"game img: {e}")
            return
        self._game_img_seq += 1
        tg = f"gimg{self._game_img_seq}"
        T.tag_configure(tg)
        T.configure(state="normal")
        T.insert("end", " ", ("gimgline",))
        idx = T.index("end-1c")
        T.image_create("end", image=ph, padx=0, pady=4)
        T.tag_add(tg, idx)
        T.tag_add("gimgline", idx)
        T.insert("end", "\n", ("gimgline",))
        T.configure(state="disabled")
        T.tag_bind(tg, "<Button-1>", lambda e, f=fam, k=key, i=li: self._game_img_popup(f, k, i))
        T.tag_bind(tg, "<Enter>", lambda e: T.configure(cursor="hand2"))
        T.tag_bind(tg, "<Leave>", lambda e: T.configure(cursor="arrow"))
        self._game_imgs.append(ph)
        if li is not None:
            self._game_img_ph[li] = (ph, im.size, fam, key, gh)
        if animate and getattr(self, "_game_images_anim", True):
            self._game_img_reveal(ph, im, fam)

    # ---- 🎨 v41.0 images générées (Studio) : en arrière-plan, après la réponse du MJ, sans bloquer le jeu
    def _game_gen_request(self, st: Dict[str, Any], li: int, key: str, text: str) -> None:
        core = self._studio_core()
        fam = game_img_family(st.get("builtin", ""))
        if core is None or not fam:
            return
        lieu = ""
        try:
            e = st["log"][li]
            lieu = game_fields(e.get("status", "") or text).get("LIEU", "") or game_fields(text).get("LIEU", "")
        except Exception:
            pass
        h = core.cache_key(fam, key, lieu)
        if core.cache_get(h) is not None:  # déjà dessinée (même scène, même lieu) : tout de suite
            st["log"][li]["img_gen"] = h
            return
        g = game_parse(text)
        narr = " ".join(x for k, x in game_split_blocks(text) if k != "fence")
        narr = re.sub(r"(?m)^\s*(\d+[.)]|SCÈNE\s*:|QUE FAIS).*$", "", narr)
        scene = (g.get("title", "") + ". " + narr).strip()[:900]
        self._game_gen_q = [(st, li, key, fam, scene, lieu, h)]  # la plus récente seulement
        if not self._game_gen_busy:
            self._game_gen_busy = True
            threading.Thread(target=self._game_gen_worker, daemon=True).start()

    def _game_gen_worker(self) -> None:
        core = self._studio_core()
        while True:
            try:
                job = self._game_gen_q.pop(0)
            except IndexError:
                break
            st, li, key, fam, scene, lieu, h = job
            t0 = time.time()
            rec: Dict[str, Any] = {"li": li, "key": key}
            try:
                model = model_id_from_label(self.mvar.get())
                self.after0(self._game_gen_hint, st, "🎨 dessin de la scène en arrière-plan…")
                prompt, how = core.game_prompt(fam, scene, key, lieu, model=model)
                rec["prompt_s"] = round(time.time() - t0, 1)
                to = float(core.cfg.get("game_timeout") or 90)
                imgs, info = core.generate(prompt, size="paysage", steps=2, timeout=to, vram="jamais")
                ast = _PS.GAME_STYLE.get(fam, ("", "pipboy"))[1]
                bank = _ANSI.bank_art(game_img_bank(), fam, key)
                cols, rows = (bank.cols, bank.nrows) if bank is not None else (72, 20)
                art = _PS.to_ansi(imgs[0], ast, cols, rows, title=key, game=True)
                core.cache_put(h, art, info["png"][0], {"prompt": prompt, "how": how, "seed": info["seed"],
                                                       "fam": fam, "key": key, "lieu": lieu})
                self._game_gen_mem[h] = art
                rec.update(gen_s=info.get("total_s"), all_s=round(time.time() - t0, 1), ok=True, how=how)
                self.after0(self._game_gen_apply, st, li, h)
            except Exception as e:
                rec.update(ok=False, err=str(e)[:200], all_s=round(time.time() - t0, 1))
                log(f"game gen: {e}")
                self.after0(self._game_gen_hint, st, f"🖼 image de la banque (dessin indisponible : {str(e)[:80]})")
            self._game_gen_times.append(rec)
            self._game_gen_times = self._game_gen_times[-30:]
        self._game_gen_busy = False

    def _game_gen_hint(self, st, text: str) -> None:
        if st is self.game and not self.busy:
            try:
                self.game_hint.config(text=text)
            except Exception:
                pass

    def _game_gen_apply(self, st, li: int, h: str) -> None:
        """L'image dessinée est prête : on la glisse à la place de celle de la banque, avec le balayage CRT."""
        if st is not self.game:
            return
        try:
            st["log"][li]["img_gen"] = h
        except Exception:
            return
        self._game_autosave()
        self._game_gen_hint(st, "🎨 scène dessinée ✔ (clic sur l'image = agrandir)")
        cur = self._game_img_ph.get(li)
        if not cur or not self._game_gen_on(check_engine=False):
            return
        ph, size, fam, key, _old = cur
        a = self._game_gen_art(h)
        if a is None:
            return
        cw = max(1, size[0] // max(1, a.cols))
        im = self._game_img_pil(fam, key, cw, art=a, tag=h)
        if im is None or im.size != tuple(size):
            return self._game_rerender() if not self.busy else None
        try:
            ph.paste(im)
        except Exception:
            return
        self._game_img_ph[li] = (ph, size, fam, key, h)
        if getattr(self, "_game_images_anim", True):
            self._game_img_reveal(ph, im, fam)

    def _game_img_reveal(self, ph, im, fam: str, steps: int = 10, delay: int = 28):
        """Effet d'écran CRT : l'image se dessine de haut en bas derrière un trait lumineux (≈ 0,3 s)."""
        try:
            from PIL import Image as _I
        except Exception:
            return
        W, H = im.size
        beam = {"fallout": (150, 255, 170), "donjon": (120, 255, 255), "polar": (255, 255, 255)}.get(fam, (200, 255, 200))
        black = _I.new("RGB", (W, H), (0, 0, 0))
        try:
            ph.paste(black)
        except Exception:
            return

        def frame(k: int):
            try:
                y = int(H * k / steps)
                fr = black.copy()
                if y > 0:
                    fr.paste(im.crop((0, 0, W, y)), (0, 0))
                if k < steps:
                    fr.paste(_I.new("RGB", (W, 3), beam), (0, max(0, y - 1)))
                ph.paste(fr)
            except Exception:
                return  # fenêtre fermée / image effacée
            if k < steps:
                self.after(delay, frame, k + 1)
        self.after(15, frame, 1)

    def _game_img_popup(self, fam: str, key: str, li: Optional[int] = None):
        a = _ANSI.bank_art(game_img_bank(), fam, key) if _ANSI else None
        if a is None:
            return
        ga, gh = self._game_li_art(li)
        if ga is not None:
            a = ga
        G = GAME_COLORS
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        cw = max(6, min(18, int(sw * 0.82) // a.cols, int(sh * 0.70) // (2 * a.nrows)))
        im = self._game_img_pil(fam, key, cw, art=a if gh else None, tag=gh)
        top = tk.Toplevel(self)
        top.title(f"🖼 {key} — illustration ANSI")
        top.configure(bg=G["bg"])
        top.transient(self)
        ph = _ANSI.ImageTk.PhotoImage(im, master=top)
        top._ph = ph  # type: ignore[attr-defined]
        lb = tk.Label(top, image=ph, bg="#000000", bd=0, cursor="hand2")
        lb.pack(padx=10, pady=(10, 4))
        sty = {"pipboy": "Pip-Boy vert", "dos16": "16 couleurs DOS", "noir": "film noir"}.get(a.style, a.style)
        tk.Label(top, text=f"{key} · {a.cols}×{a.nrows} caractères · {sty} · "
                           + ("scène dessinée par le 🎨 Studio (SD-Turbo)  " if gh else "illustration originale Padawan  ")
                           + "(clic ou Échap pour fermer)",
                 bg=G["bg"], fg=G["dim"], font=("Segoe UI", 9)).pack(pady=(0, 8))
        for w in (top, lb):
            w.bind("<Button-1>", lambda e: top.destroy())
        top.bind("<Escape>", lambda e: top.destroy())
        top.update_idletasks()
        x = self.winfo_rootx() + max(0, (self.winfo_width() - top.winfo_width()) // 2)
        y = self.winfo_rooty() + max(0, (self.winfo_height() - top.winfo_height()) // 3)
        top.geometry(f"+{x}+{y}")
        top.focus_set()
        if getattr(self, "_game_images_anim", True):
            self._game_img_reveal(ph, im, fam, steps=14, delay=22)

    def _game_toggle_dice(self):
        self._game_dice = not self._game_dice
        self.cfg["game_dice"] = self._game_dice
        self._game_paint_toggles()

    def _game_toggle_sound(self):
        self._game_sound = not self._game_sound
        self.cfg["game_sound"] = self._game_sound
        self._game_paint_toggles()
        if self._game_sound:
            self._game_beep("on")

    def _game_beep(self, kind: str = "turn"):
        if not getattr(self, "_game_sound", False):
            return
        seq = {"turn": [(1200, 40), (1600, 40)], "on": [(900, 60), (1300, 60), (1700, 80)],
               "pick": [(1500, 25)]}.get(kind, [(1200, 40)])

        def run():
            try:
                import winsound
                for f, d in seq:
                    winsound.Beep(f, d)
            except Exception:
                pass
        threading.Thread(target=run, daemon=True).start()

    # ---- état / fichiers
    def _game_prompts(self) -> List[Dict[str, Any]]:
        return [p for p in self.prompts.all() if p.get("kind") == "jeu"]

    @staticmethod
    def _game_slug(st: Dict[str, Any]) -> str:
        base = st.get("builtin") or st.get("pid") or "partie"
        return re.sub(r"[^A-Za-z0-9_\-]+", "_", str(base))[:40] or "partie"

    def _game_auto_path(self, st: Dict[str, Any]) -> str:
        return os.path.join(GAME_PARTIES_DIR, f"_encours_{self._game_slug(st)}.json")

    def _game_write(self, st: Dict[str, Any], path: str) -> bool:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            st["updated"] = now()
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(st, f, ensure_ascii=False, indent=1)
            os.replace(tmp, path)
            return True
        except Exception as e:
            log(f"game write: {e}")
            return False

    def _game_autosave(self):
        st = getattr(self, "game", None)
        if st:
            self._game_write(st, self._game_auto_path(st))

    @staticmethod
    def _game_read(path: str) -> Optional[Dict[str, Any]]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                st = json.load(f)
            if not isinstance(st, dict) or not isinstance(st.get("log"), list):
                return None
            st.setdefault("msgs", [])
            st.setdefault("chronicle", [])
            st.setdefault("quests", [])
            st.setdefault("choices", [])
            st.setdefault("status", "")
            st.setdefault("turn", 0)
            st.setdefault("phase", "play")
            return st
        except Exception as e:
            log(f"game read: {e}")
            return None

    def _game_new_state(self, p: Dict[str, Any]) -> Dict[str, Any]:
        return {"v": 1, "pid": p["id"], "name": p["name"], "builtin": p.get("builtin", ""),
                "created": now(), "updated": now(), "turn": 0, "phase": "intro" if p.get("builtin") in GAME_META else "play",
                "msgs": [], "log": [], "status": "", "chronicle": [], "quests": [], "choices": []}

    # ---- entrée / sortie
    def _game_boot(self):
        note = getattr(self.prompts, "migrated_note", "")
        gid = self.prompts.data.get("game") or ""
        if note:
            self.say("sys", note)
        if getattr(self, "_startup_note", ""):
            self.say("sys", self._startup_note)
        # v39.4: Padawan démarre sérieux (Chercheur). La partie reste sauvegardée : 🎮 Jouer la reprend.
        if gid and self.prompts.get(gid) and self.cfg.get("game_resume_on_start", False):
            self.game_start(gid, ask=False)

    def game_start(self, pid: str, ask: bool = True, override: Optional[Dict[str, Any]] = None):
        p = override or self.prompts.get(pid)
        if not p or p.get("kind") != "jeu":
            return
        if self.busy:
            self.say("sys", "🎮 Padawan est occupé — réessaie dans un instant (Échap = annuler).")
            return
        if self.game:
            self._game_autosave()
        st = None
        auto = self._game_auto_path({"builtin": p.get("builtin", ""), "pid": p["id"]})
        if os.path.isfile(auto):
            old = self._game_read(auto)
            if old and old.get("log"):
                r = True
                if ask:
                    r = messagebox.askyesnocancel(
                        "🎮 " + p["name"],
                        f"Une partie est en cours ({old.get('turn', 0)} tour(s), {str(old.get('updated', ''))[:16]}).\n\n"
                        "Oui = la reprendre\nNon = nouvelle partie\nAnnuler = rien faire", parent=self)
                if r is None:
                    return
                if r:
                    st = old
        if st is None:
            st = self._game_new_state(p)
        st["pid"], st["name"] = p["id"], p["name"]
        st["builtin"] = p.get("builtin", "") or st.get("builtin", "")
        self._game_override = override
        self.game = st
        self._game_load_img_mode()  # v41.0 🖼 réglage par jeu
        self._game_gen_q = []
        self._model_sync_prompt()  # v39.6 : le jeu peut avoir son propre modèle
        if not override:
            self.prompts.data["game"] = p["id"]
            self.prompts.save()
        self._game_enter_ui()
        self._game_rerender()
        if not st["log"]:
            if st["phase"] == "intro":
                self._game_intro()
            else:
                st["phase"] = "play"
                self._game_send("Commence la partie.", display="▶ Commence la partie")
        self._game_beep("on")
        self.say("sys", f"🎮 Prompt activé : « {p['name']} » — mode Jeu (clique un choix ou tape 1 à 9).")
        self._refresh_prompt_ui()

    def _game_enter_ui(self):
        if getattr(self, "_game_ui_on", False):
            self._game_paint_header()
            return
        self._game_ui_on = True
        self._game_saved_pack = {}
        for key in ("_chips_fr", "_hunt_fr", "_chrome_fr", "_act_fr"):
            w = getattr(self, key, None)
            if w is not None and w.winfo_manager() == "pack":
                info = w.pack_info()
                info.pop("in", None)
                self._game_saved_pack[key] = info
                w.pack_forget()
        self._chat_wrap.pack_forget()
        self.game_wrap.pack(fill="both", expand=True)
        try:
            self._right_pane_on = str(self._right_pane) in [str(x) for x in self.split.panes()]
            if self._right_pane_on:
                self.split.forget(self._right_pane)
        except Exception as e:
            log(f"game panes: {e}")
        self._game_paint_header()
        self.input_tip.config(text=GAME_INPUT_TIP)
        try:  # v39.8 : pas d'étapes de chasse périmées pendant un jeu
            self.mission_clear()
            self.mission_live.config(text="🎮 Mode jeu : pas de chasse web")
        except Exception:
            pass
        self.ent.focus_set()

    def _game_exit_ui(self):
        if not getattr(self, "_game_ui_on", False):
            return
        self._game_ui_on = False
        self.game_wrap.pack_forget()
        try:
            self.mission_live.config(text="")
        except Exception:
            pass
        sp = getattr(self, "_game_saved_pack", {})
        if "_hunt_fr" in sp:
            self._hunt_fr.pack(**sp["_hunt_fr"])
        if "_chrome_fr" in sp:
            self._chrome_fr.pack(**sp["_chrome_fr"])
        self._chat_wrap.pack(fill="both", expand=True)
        if "_chips_fr" in sp:
            self._chips_fr.pack(before=self._hunt_fr, **sp["_chips_fr"])
        if "_act_fr" in sp:
            self._act_fr.pack(before=self._input_bar, **sp["_act_fr"])
        try:
            if getattr(self, "_right_pane_on", True):
                self.split.add(self._right_pane, stretch="always", minsize=300)
                self.after(60, lambda: self.split.sash_place(0, max(480, min(820, self.split.winfo_width() - 320)), 0))
        except Exception as e:
            log(f"game panes back: {e}")
        self.lock(self.busy, "")

    def _game_paint_header(self):
        st = self.game or {}
        meta = GAME_META.get(st.get("builtin", ""), {})
        t = meta.get("title") or str(st.get("name", "🎮")).lstrip("🎮🕵️🧙 ").upper()
        self.game_title.config(text=f"☢ {t}   ·   TOUR {st.get('turn', 0)}")

    def _game_pause_for(self, what: str) -> None:
        """v41.2 : met le jeu sur pause (sauvegarde auto + retour au modèle d'avant) avant d'ouvrir un autre mode."""
        try:
            self.game_quit()
        except Exception as e:
            log(f"pause jeu pour {what}: {e}")
            self.game = None
        self.say("sys", f"{what} : partie mise sur pause — 🎮 Jouer pour la reprendre.")

    def game_quit(self):
        if not self.game:
            return
        if self.busy:
            self.cancel_job()
        self._game_autosave()
        name = self.game.get("name", "")
        self._game_pending = None  # v39.8
        self.game = None
        self._game_override = None
        self.prompts.data["game"] = ""
        self.prompts.save()
        self._game_exit_ui()
        self._refresh_prompt_ui()
        self._model_sync_prompt()  # v39.6 : retour au modèle d'avant le jeu
        self.say("sys", f"🎮 « {name} » mis sur pause (sauvegarde auto). Padawan reprend son prompt et son rôle "
                        f"d'avant — rejoue quand tu veux : 🎮 Jouer.")

    def game_new(self):
        st = self.game
        if not st or self.busy:
            return
        if st.get("log") and not messagebox.askyesno(
                "🆕 Nouvelle partie", "Recommencer à zéro ?\n\nLa partie actuelle est perdue "
                                     "(sauf si tu l'as 💾 sauvegardée).", parent=self):
            return
        p = self._game_override or self.prompts.get(st["pid"]) or {"id": st["pid"], "name": st["name"],
                                                                  "builtin": st.get("builtin", "")}
        self.game = self._game_new_state(p)
        self._game_rerender()
        if self.game["phase"] == "intro":
            self._game_intro()
        else:
            self._game_send("Commence la partie.", display="▶ Commence la partie")
        self._game_autosave()

    def game_save(self):
        st = self.game
        if not st:
            return
        os.makedirs(GAME_PARTIES_DIR, exist_ok=True)
        path = filedialog.asksaveasfilename(
            parent=self, title="💾 Sauvegarder la partie", initialdir=GAME_PARTIES_DIR,
            initialfile=f"{self._game_slug(st)}_{time.strftime('%Y%m%d-%H%M')}.json",
            defaultextension=".json", filetypes=[("Partie Padawan", "*.json")])
        if not path:
            return
        ok = self._game_write(dict(st), path)
        self._game_sys(f"💾 Partie sauvegardée : {path}" if ok else "⚠ Sauvegarde impossible.")

    def game_load(self):
        if self.busy:
            return
        os.makedirs(GAME_PARTIES_DIR, exist_ok=True)
        path = filedialog.askopenfilename(parent=self, title="📂 Charger une partie", initialdir=GAME_PARTIES_DIR,
                                          filetypes=[("Partie Padawan", "*.json")])
        if not path:
            return
        st = self._game_read(path)
        if not st:
            messagebox.showwarning("📂 Charger", "Ce fichier n'est pas une partie Padawan lisible.", parent=self)
            return
        p = self.prompts.get(st.get("pid", ""))
        if not p and st.get("builtin"):
            p = next((q for q in self._game_prompts() if q.get("builtin") == st["builtin"]), None)
        if not p:
            messagebox.showwarning("📂 Charger", "Le prompt de jeu de cette partie n'existe plus dans 📜 Prompts.",
                                   parent=self)
            return
        st["pid"], st["name"] = p["id"], p["name"]
        self.game = st
        self._game_override = None
        self.prompts.data["game"] = p["id"]
        self.prompts.save()
        self._game_enter_ui()
        self._game_rerender()
        self._game_sys(f"📂 Partie chargée : {os.path.basename(path)}")
        self._game_autosave()

    def game_export(self):
        st = self.game
        if not st or not st.get("log"):
            return
        os.makedirs(GAME_PARTIES_DIR, exist_ok=True)
        path = filedialog.asksaveasfilename(
            parent=self, title="📜 Exporter l'aventure", initialdir=GAME_PARTIES_DIR,
            initialfile=f"{self._game_slug(st)}_{time.strftime('%Y%m%d-%H%M')}.html",
            defaultextension=".html", filetypes=[("Page web", "*.html"), ("Texte", "*.txt")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(game_export_html(st, images=bool(getattr(self, "_game_images", True)),
                                         generated=self._game_gen_on(check_engine=False))
                        if path.lower().endswith((".html", ".htm")) else game_export_txt(st))
            self._game_sys(f"📜 Aventure exportée : {path}")
        except Exception as e:
            self._game_sys(f"⚠ Export impossible : {e}")

    # ---- rendu
    def _game_w(self, text: str, *tags):
        T = self.game_txt
        T.configure(state="normal")
        T.insert("end", text, tags)
        T.configure(state="disabled")

    def _game_sys_safe(self, text: str):
        try:
            self._game_sys(text)
        except Exception:
            self.say("sys", text)

    def _game_sys(self, text: str):
        self._game_w(text + "\n", "sys")
        self.game_txt.see("end")

    def _game_block(self, body: str, tag: str):
        lines = (body or "").replace("\t", "    ").split("\n")
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        if not lines:
            return
        w = max(len(l) for l in lines)
        out = "\n".join(" " + l.ljust(w) + " " for l in [""] + lines + [""])
        self._game_w(out + "\n", tag)
        self._game_w("\n", "narr")

    def _game_inline(self, line: str, base: str = "narr"):
        for seg, col in ansi_segments(line):
            extra = ()
            if col:
                tg = "ansi_" + col[1:]
                self.game_txt.tag_configure(tg, foreground=col)
                extra = (tg,)
            pos = 0
            for m in re.finditer(r"\*\*(.+?)\*\*|(\[[^\]\n]{2,90}\])|(«[^»\n]{1,500}»|“[^”\n]{1,500}”)", seg):
                if m.start() > pos:
                    self._game_w(seg[pos:m.start()], base, *extra)
                if m.group(1):
                    self._game_w(m.group(1), base, "bold", *extra)
                elif m.group(2):
                    self._game_w(m.group(2), "check", *extra)
                else:
                    self._game_w(m.group(3), base, "dlg", *extra)
                pos = m.end()
            if pos < len(seg):
                self._game_w(seg[pos:], base, *extra)

    def _game_render_reply(self, text: str, status: str = "", img_key: str = "", animate: bool = False,
                           li: Optional[int] = None):
        st = self.game or {}
        bi = st.get("builtin", "")
        g = game_parse(text)
        ch_set = {(n, lab) for n, lab in g["choices"]}
        art_key, art = game_art_for(bi, g["scene"], (g["title"] + " " + text[:600])) if bi else ("", "")
        art_done = False
        use_img = self._game_img_on()  # v40.2 : illustration ANSI (ou rien si même scène) au lieu de l'art ASCII
        if use_img:
            art = "🖼"

        def put_art():
            nonlocal art_done
            if art_done:
                return
            art_done = True
            if use_img:
                if img_key:
                    self._game_img(img_key, animate, li)
            elif art:
                self._game_block(art, "art")
        blocks = game_split_blocks(text)
        fenced_status = any(k == "fence" and game_is_status(b) for k, b in blocks)
        for kind, body in blocks:
            if kind == "fence":
                if game_is_status(body):
                    if self._game_compact:  # petit écran : le statut complet est dans le Pip-Boy à droite
                        self._game_w(" ▓▓ statut mis à jour → Pip-Boy à droite ▓▓\n\n", "check")
                    else:
                        self._game_block(status or body, "status")
                elif art and not art_done:
                    put_art()
                elif not art:
                    self._game_block(body, "art")
                continue
            lines = body.split("\n")
            i = 0
            while i < len(lines):
                line = lines[i]
                s = line.strip()
                if "▓▓" in s and not fenced_status:
                    j = game_status_span(lines, i)
                    blk = [line] + [x for x in lines[i + 1:j] if x.strip()]
                    if len(blk) >= 3:
                        if self._game_compact:
                            self._game_w(" ▓▓ statut mis à jour → Pip-Boy à droite ▓▓\n\n", "check")
                        else:
                            self._game_block(status or "\n".join(blk), "status")
                        i = j
                        continue
                mt = re.match(r"^\s*#{1,4}\s*(.+)$", line)
                if mt:
                    self._game_w(_strip_md(mt.group(1)) + "\n", "title")
                    if art and not art_done:
                        put_art()
                    i += 1
                    continue
                if _SCENE_RE.match(line):
                    if art and not art_done:
                        put_art()
                    i += 1
                    continue
                if re.match(r"^\s*\**\s*QUE FAIS[- ]TU", s, re.I):
                    self._game_w(_strip_md(s) + "\n", "ask")
                    i += 1
                    continue
                mc = _CHOICE_RE.match(line)
                if mc and (int(mc.group(1)), _strip_md(mc.group(2))) in ch_set:
                    n = int(mc.group(1))
                    lab = dict(g["choices"]).get(n, _strip_md(mc.group(2)))
                    tg = f"ch{n}"
                    self.game_txt.tag_configure(tg)
                    self._game_w(f"  {n}.  {lab}\n", "choice", tg)
                    i += 1
                    while i < len(lines) and lines[i][:1] in (" ", "\t") and lines[i].strip() and not _CHOICE_RE.match(lines[i]):
                        i += 1  # suite déjà fusionnée dans le libellé
                    continue
                if game_is_art_line(line) and not s.startswith("["):
                    blk = [line]
                    j = i + 1
                    while j < len(lines) and game_is_art_line(lines[j]):
                        blk.append(lines[j])
                        j += 1
                    if len(blk) >= 3:
                        if not art_done:
                            if art:
                                put_art()
                            else:
                                self._game_block("\n".join(blk), "art")
                                art_done = True
                        i = j
                        continue
                self._game_inline(line)
                self._game_w("\n", "narr")
                i += 1
        if art and not art_done:  # pas de titre ni de SCÈNE: on montre quand même l'image
            put_art()
        self._game_w("\n", "narr")

    def _game_rerender(self, animate_last: bool = False):
        T = self.game_txt
        T.configure(state="normal")
        T.delete("1.0", "end")
        T.configure(state="disabled")
        self._game_imgs = []
        self._game_img_ph = {}
        st = self.game or {}
        plan = game_img_plan(st, self._game_pick_cache) if self._game_img_on() else {}
        last_i = max(plan) if plan else None
        if -1 in plan:
            self._game_img(plan[-1], animate=animate_last and last_i == -1)
        for ei, e in enumerate(st.get("log", [])):
            who, text = e.get("who"), e.get("text", "")
            if who == "you":
                self._game_w(f"▶ {text}\n", "you")
            elif who == "mj":
                self._game_render_reply(text, e.get("status", ""), img_key=plan.get(ei, ""),
                                        animate=animate_last and ei == last_i, li=ei)
            elif who == "fx":
                self._game_w(text + "\n\n", "check")
            elif who == "intro":
                self._game_render_intro(intro_only=True, img_key=plan.get(ei, ""),
                                        animate=animate_last and ei == last_i)
            else:
                self._game_w(text + "\n", "sys")
        r = T.tag_prevrange("you", "end")
        self._game_scroll_to(r[0] if r else "1.0")
        self._game_update_pip()
        self._game_set_choices(st.get("choices") or [])
        self._game_paint_header()

    def _game_scroll_to(self, idx: str):
        """Montre le début de la nouvelle scène (titre + image) plutôt que la fin."""
        def go():
            try:
                self.game_txt.see("end")
                self.game_txt.yview(idx)
            except Exception:
                pass
        self.after(30, go)

    def _game_click_choice(self, e):
        idx = self.game_txt.index(f"@{e.x},{e.y}")
        for tg in self.game_txt.tag_names(idx):
            if tg.startswith("ch") and tg[2:].isdigit():
                n = int(tg[2:])
                ch = dict((self.game or {}).get("choices") or [])
                # seul le dernier menu est jouable
                if n in ch and self._game_is_last_menu(idx):
                    self._game_pick(n)
                else:  # v39.8 : jamais de clic muet
                    self._game_flash("Ce choix n'est plus jouable (menu d'un tour passé) — utilise les boutons du bas.")
                return "break"

    def _game_is_last_menu(self, idx: str) -> bool:
        """Seul le dernier menu de choix est cliquable (pas ceux des tours passés)."""
        r = self.game_txt.tag_prevrange("you", "end")
        return not r or self.game_txt.compare(idx, ">", r[0])

    def _game_set_choices(self, choices):
        G = GAME_COLORS
        for w in self.game_choices.winfo_children():
            w.destroy()
        st = self.game or {}
        if not st:
            return
        width = max(300, self.game_choices.winfo_width(), self.game_wrap.winfo_width() - 16,
                    self.split.winfo_width() - 20 if not getattr(self, "_game_ui_on", False) else 0)
        grid = tk.Frame(self.game_choices, bg=G["bg"])
        grid.pack(fill="x")
        two = len(choices) >= 4 and width > 700
        for k, (n, lab) in enumerate(choices[:9]):
            b = tk.Button(
                grid, text=f" {n} ▸ {lab}", anchor="w", justify="left", command=lambda n=n: self._game_pick(n),
                bg=G["btn"], fg=G["fg"], activebackground=G["green"], activeforeground="#021006",
                relief="flat", bd=0, font=("Segoe UI", 11, "bold"), padx=10, pady=5, cursor="hand2",
                wraplength=(width // 2 - 40) if two else (width - 40), highlightthickness=1,
                highlightbackground=G["line"],
            )
            b.bind("<Enter>", lambda e, w=b: w.configure(bg=G["btnh"], fg="#ffffff"))
            b.bind("<Leave>", lambda e, w=b: w.configure(bg=G["btn"], fg=G["fg"]))
            if two:
                b.grid(row=k // 2, column=k % 2, sticky="ew", padx=2, pady=2)
            else:
                b.grid(row=k, column=0, sticky="ew", padx=2, pady=2)
        grid.columnconfigure(0, weight=1)
        if two:
            grid.columnconfigure(1, weight=1)
        if not choices and st.get("log") and not self.busy:
            tk.Button(grid, text="🔁 Le maître du jeu a oublié les choix — les redemander",
                      command=lambda: self._game_send(
                          "(Hors jeu : redonne-moi le statut et 3 à 5 choix numérotés pour cette scène, au bon format.)",
                          display="🔁 Choix demandés", count=False),
                      bg=G["btn"], fg=G["amber"], relief="flat", font=("Segoe UI", 10, "bold"), padx=10, pady=4,
                      cursor="hand2").grid(row=0, column=0, sticky="w", padx=2, pady=2)
        hint = ("✍ Autre action : écris-la dans la barre du bas puis Entrée  ·  touches 1–"
                f"{min(9, len(choices))} = choisir" if choices else "✍ Écris ton action dans la barre du bas puis Entrée")
        self.game_hint.config(text=hint)

    def _game_key_ent(self, e):
        if not self.game or self.var.get():
            return None
        return self._game_key(e)

    def _game_key_any(self, e):
        if not self.game:
            return None
        f = self.focus_get()
        if f is self.ent or isinstance(f, (tk.Entry, ttk.Entry, tk.Spinbox, ttk.Combobox)) or (
                isinstance(f, tk.Text) and f is not self.game_txt):
            return None
        return self._game_key(e)

    def _game_key(self, e):
        ch = e.char or ""
        if e.keysym.startswith("KP_") and e.keysym[3:].isdigit():
            ch = e.keysym[3:]
        if len(ch) == 1 and ch in "123456789" and not (e.state & 0x4):
            n = int(ch)
            if n in dict((self.game or {}).get("choices") or []):
                self._game_pick(n)
                return "break"
        return None

    def _game_flash(self, text: str, color: Optional[str] = None):
        """v39.8 : retour visible quand un clic/touche ne peut pas être joué tout de suite."""
        try:
            self.game_hint.config(text="⚠ " + text, fg=color or GAME_COLORS["amber"])
            self.after(6000, lambda: self.game_hint.config(fg=GAME_COLORS["dim"]))
        except Exception:
            pass

    def _game_pick(self, n: int):
        st = self.game
        if not st:
            return
        if getattr(self, "_game_pending", None):
            return self._game_flash("Un choix attend déjà le modèle — patiente ou « ✖ Annuler ce choix ».")
        if self.busy:
            return self._game_flash("Le maître du jeu écrit encore… attends la fin (Échap = annuler).")
        ch = dict(st.get("choices") or [])
        if n not in ch:
            self._game_set_choices(st.get("choices") or [])  # boutons périmés → on remet les bons
            return self._game_flash(f"Le choix {n} n'est pas disponible à ce tour.")
        self._game_beep("pick")
        if st.get("phase") == "intro":
            return self._game_intro_pick(n)
        self._game_send(f"Je choisis {n}. {ch[n]}", display=f"{n}. {ch[n]}")

    # ---- création du personnage (locale, fiable)
    def _game_render_intro(self, intro_only: bool = False, img_key: str = "", animate: bool = False):
        st = self.game or {}
        meta = GAME_META.get(st.get("builtin", ""), {})
        if not meta:
            return
        self._game_w(meta["title"] + "\n", "title")
        k, art = game_art_for(st.get("builtin", ""), meta.get("art", ""))
        if self._game_img_on():
            if img_key:
                self._game_img(img_key, animate)
        elif art:
            self._game_block(art, "art")
        for para in meta["intro"].split("\n"):
            self._game_inline(para)
            self._game_w("\n", "narr")
        self._game_w("\n" + meta.get("ask", "Qui es-tu ?").upper() + "\n", "ask")
        for i, a in enumerate(meta["archetypes"], 1):
            self.game_txt.tag_configure(f"ch{i}")
            self._game_w(f"  {i}.  {a['label']} — {a['desc']}\n", "choice", f"ch{i}")
            self._game_w(f"        {a['special']}  ·  {a['inv']}\n", "sys")
        n = len(meta["archetypes"]) + 1
        self.game_txt.tag_configure(f"ch{n}")
        self._game_w(f"  {n}.  {meta['custom']}\n\n", "choice", f"ch{n}")

    def _game_intro(self):
        st = self.game
        meta = GAME_META.get(st.get("builtin", ""), {})
        st["phase"] = "intro"
        st["log"].append({"who": "intro", "text": ""})
        st["choices"] = [(i, a["label"]) for i, a in enumerate(meta["archetypes"], 1)]
        st["choices"].append((len(meta["archetypes"]) + 1, meta["custom"]))
        self._game_rerender(animate_last=True)

    def _game_intro_pick(self, n: int, custom_text: str = ""):
        from tkinter import simpledialog
        st = self.game
        meta = GAME_META.get(st.get("builtin", ""), {})
        arch = meta.get("archetypes", [])
        if 1 <= n <= len(arch) and not custom_text:
            a = arch[n - 1]
            name = simpledialog.askstring("🎮 " + a["label"], f"Nom de ton personnage ({a['label']}) :",
                                          initialvalue=a["name"], parent=self)
            if name is None:
                return
            name = name.strip()[:40] or a["name"]
            msg = meta["start"].format(**dict(a, name=name))
            if meta.get("status0"):  # Pip-Boy rempli dès le départ (même si le modèle oublie le statut)
                st["status"] = meta["status0"].format(**dict(a, name=name))
                self._game_update_pip()
            disp = f"{n}. {a['label']} — {name}"
        else:
            desc = custom_text or simpledialog.askstring(
                "🎮 " + meta.get("custom", "Mon personnage"),
                "Décris ton personnage (nom, style, forces, faiblesses…) :", parent=self)
            if not desc or not desc.strip():
                return
            msg = ("Commence la partie. Je crée mon propre personnage : " + desc.strip()[:600]
                   + ". Déduis ses statistiques de départ de cette description (total équilibré).")
            disp = "✍ " + desc.strip()[:120]
        st["phase"] = "play"
        st["choices"] = []
        self._game_send(msg, display=disp)

    # ---- tours de jeu
    # ── v39.8 : file d'attente pendant le chargement du modèle ───────────────
    def _game_queue(self, text: str, display: Optional[str], count: bool):
        self._game_pending = (text, display, count, time.time())
        if not self._model_warming:
            threading.Thread(target=self.warm_model, kwargs={"force_boot": not self.ready}, daemon=True).start()
        self._game_wait_ui()
        self.after(800, self._game_pending_poll)

    def _game_wait_ui(self):
        pend = getattr(self, "_game_pending", None)
        if not pend or not self.game:
            return
        G = GAME_COLORS
        name = self.current_model()
        sec = int(time.time() - pend[3])
        state = getattr(self, "_model_state", "")
        fb = self._game_fallback_model()
        bad = state in ("error", "down")
        key = (name, bad, sec >= self.MODEL_SLOW_S, fb, pend[3])
        lbl = getattr(self, "_game_wait_lbl", None)
        if bad:
            msg = f"✖ Le modèle {name} n'a pas pu se charger : {(getattr(self, '_model_detail', '') or 'échec')[:80]}"
            col = G["bad"]
        else:
            msg = f"⏳ Le modèle {name} se charge… {sec} s — ton choix « {(pend[1] or pend[0])[:50]} » part dès qu'il est prêt."
            if sec >= self.MODEL_SLOW_S:
                msg += "  C'est long : ce modèle déborde sans doute de ta carte graphique."
            col = G["amber"]
        self.game_hint.config(text=f"⏳ En attente du modèle {name} ({sec} s)", fg=G["amber"])
        try:  # même disposition → on ne met à jour que le texte (pas de clignotement des boutons)
            if lbl is not None and lbl.winfo_exists() and getattr(self, "_game_wait_key", None) == key:
                lbl.config(text=msg, fg=col)
                return
        except Exception:
            pass
        self._game_wait_key = key
        for w in self.game_choices.winfo_children():
            w.destroy()
        bar = tk.Frame(self.game_choices, bg=G["bg"])
        bar.pack(fill="x")
        if state == "error" or (state == "down"):
            msg = f"✖ Le modèle {name} n'a pas pu se charger : {(getattr(self, '_model_detail', '') or 'échec')[:80]}"
            col = G["bad"]
        else:
            msg = f"⏳ Le modèle {name} se charge… {sec} s — ton choix « {(pend[1] or pend[0])[:50]} » part dès qu'il est prêt."
            if sec >= self.MODEL_SLOW_S:
                msg += "  C'est long : ce modèle déborde sans doute de ta carte graphique."
            col = G["amber"]
        self._game_wait_lbl = tk.Label(bar, text=msg, bg=G["bg"], fg=col, font=("Segoe UI", 11, "bold"), anchor="w",
                                       justify="left", wraplength=max(400, self.game_wrap.winfo_width() - 40))
        self._game_wait_lbl.pack(fill="x", padx=4, pady=(2, 4))
        row = tk.Frame(bar, bg=G["bg"])
        row.pack(fill="x")

        def gb(text, cmd, tip, fg=None):
            b = tk.Button(row, text=text, command=cmd, bg=G["btn"], fg=fg or G["fg"], activebackground=G["green"],
                          activeforeground="#021006", relief="flat", bd=0, font=("Segoe UI", 11, "bold"),
                          padx=12, pady=5, cursor="hand2", highlightthickness=1, highlightbackground=G["line"])
            b.bind("<Enter>", lambda e, w=b: w.configure(bg=G["btnh"]))
            b.bind("<Leave>", lambda e, w=b: w.configure(bg=G["btn"]))
            self._tip(b, tip)
            b.pack(side="left", padx=2, pady=2)
            return b

        if fb and (sec >= self.MODEL_SLOW_S or bad):
            gb(f"⚡ Jouer avec {fb} (rapide)", lambda: self._game_use_fallback(fb),
               f"Passer à {fb} pour ce jeu seulement — ton modèle par défaut revient en quittant le jeu.", G["green"])
        if bad:
            gb("🔁 Réessayer", lambda: threading.Thread(target=self.warm_model, kwargs={"force_boot": True},
                                                       daemon=True).start(), "Relancer le chargement du modèle")
        gb("✖ Annuler ce choix", self._game_cancel_pending, "Ne pas envoyer ce choix (tu pourras en refaire un)", G["amber"])

    def _game_pending_poll(self):
        pend = getattr(self, "_game_pending", None)
        if not pend:
            return
        if not self.game:
            self._game_pending = None
            return
        if self.ready and self.model_ready and not self.busy:
            self._game_pending = None
            self._game_wait_key = None
            self.game_hint.config(fg=GAME_COLORS["dim"])
            return self._game_send(pend[0], pend[1], pend[2])
        self._game_wait_ui()
        self.after(1000, self._game_pending_poll)

    def _game_cancel_pending(self):
        pend = getattr(self, "_game_pending", None)
        self._game_pending = None
        self._game_wait_key = None
        st = self.game
        if not st:
            return
        if not any(x.get("who") in ("you", "mj") for x in st.get("log") or []) and st.get("builtin") in GAME_META:
            # rien n'a encore été joué : retour au choix du personnage
            meta = GAME_META[st["builtin"]]
            st["phase"], st["status"] = "intro", ""
            st["choices"] = [(i, a["label"]) for i, a in enumerate(meta["archetypes"], 1)]
            st["choices"].append((len(meta["archetypes"]) + 1, meta["custom"]))
            self._game_update_pip()
        self._game_set_choices(st.get("choices") or [])
        self._game_flash("Choix annulé — rien n'a été envoyé.", GAME_COLORS["dim"])

    def _game_fallback_model(self) -> str:
        cur = self.current_model()
        if self._same_model_id(cur, MODEL):
            return ""
        return self._model_local_id(MODEL)

    def _game_use_fallback(self, name: str):
        """Repli pour CE jeu : bascule temporaire (le modèle par défaut revient en quittant le jeu)."""
        cur = self.current_model()
        if getattr(self, "_model_before", None) is None:
            self._model_before = cur
        self._model_label_set(name)
        self.model, self.model_ready = name, False
        self._model_state = ""
        threading.Thread(target=self.warm_model, args=(name,), daemon=True).start()
        self._game_sys(f"⚡ Ce jeu passe à {name} (rapide). {self._model_before} revient quand tu quittes le jeu.")
        self._game_wait_ui()

    def _game_send(self, text: str, display: Optional[str] = None, count: bool = True):
        st = self.game
        if not st:
            return
        if self.busy:
            return self._game_flash("Le maître du jeu écrit encore… attends la fin (Échap = annuler).")
        if st.get("phase") == "intro":
            return self._game_intro_pick(0, custom_text=text)
        if not self.ready or not self.model_ready:
            return self._game_queue(text, display, count)  # v39.8 : le choix part dès que le modèle est prêt
        dice = random.randint(1, 20) if self._game_dice else 0
        st["_dice"] = dice
        user_core = text + game_dice_hint(dice)
        st["log"].append({"who": "you", "text": display or text})
        self._game_w(f"▶ {display or text}\n", "you")
        if dice:
            self._game_w(f"🎲 d20 lancé par Padawan : {dice}\n", "sys")
        self._game_set_choices([])
        T = self.game_txt
        T.configure(state="normal")
        mark = T.index("end-1c")
        T.mark_set("game_stream", mark)
        T.mark_gravity("game_stream", "left")
        T.insert("end", "⌛ le maître du jeu écrit…\n", "sys")
        T.configure(state="disabled")
        T.see("end")
        self.game_hint.config(text="⌛ Le maître du jeu écrit… (Échap = annuler)")
        self.lock(True, "🎮 le maître du jeu écrit…")
        hist, memo = game_trim_history(st)
        user = (memo + user_core) + game_state_line(st.get("status", "")) + game_reminder(st.get("builtin", ""))
        threading.Thread(target=self._game_worker, args=(user, user_core, hist, display or text, count),
                         daemon=True).start()

    def _game_worker(self, user: str, user_core: str, hist, display: str, count: bool):
        st = self.game
        try:
            p = self._game_override or self.prompts.get(st["pid"]) or {}
            system = self.router.system_prompt(override=p) if p else GAME_ADN_LINE
            first = [True]
            acc: List[str] = []
            stop = _GameStop(self._cancel)

            def on_tok(t: str):
                acc.append(t)
                if not stop.stop and "\n" in t and game_turn_complete("".join(acc)):
                    stop.stop = True  # scène complète : on n'attend pas une 2e scène inventée
                def ui():
                    T = self.game_txt
                    T.configure(state="normal")
                    if first[0]:
                        T.delete("game_stream", "end-1c")
                        first[0] = False
                    T.insert("end", t, "stream")
                    T.configure(state="disabled")
                    T.see("end")
                self.after0(ui)

            ans = chat_stream(
                model_id_from_label(self.mvar.get()), user, system=system, on_token=on_tok,
                cancel=stop, history=hist, raw_system=True, options=dict(GAME_GEN_OPTIONS),
            )
            self.after0(self._game_finish, st, ans, user_core, display, count)
        except Exception as e:
            self.after0(self._game_fail, st, str(e))
        finally:
            self.after0(self.lock, False, "● prêt")

    def _game_fail(self, st, err: str):
        if st is not self.game:
            return
        T = self.game_txt
        T.configure(state="normal")
        try:
            T.delete("game_stream", "end-1c")
        except Exception:
            pass
        T.configure(state="disabled")
        if st["log"] and st["log"][-1].get("who") == "you":
            st["log"].pop()
        self._game_sys(f"⚠ {err}")
        self._game_set_choices(st.get("choices") or [])

    def _game_finish(self, st, ans: str, user_core: str, display: str, count: bool):
        if st is not self.game:
            return
        T = self.game_txt
        T.configure(state="normal")
        try:
            T.delete("game_stream", "end-1c")
        except Exception:
            pass
        T.configure(state="disabled")
        if self._cancel.is_set() or not (ans or "").strip() or ans.startswith("⚠") or ans == "(annulé)":
            if st["log"] and st["log"][-1].get("who") == "you":
                st["log"].pop()
            self._game_rerender()
            self._game_sys("Tour annulé." if self._cancel.is_set() or ans == "(annulé)" else f"{ans or '(réponse vide)'}")
            return
        ans = game_strip_template(game_clean_reply(clean(ans)))
        st["msgs"].append({"role": "user", "content": user_core})
        st["msgs"].append({"role": "assistant", "content": ans})
        st["log"].append({"who": "mj", "text": ans})
        if count:
            st["turn"] = int(st.get("turn", 0)) + 1
            st["chronicle"].append(f"T{st['turn']} · {display}"[:140])
            st["chronicle"] = st["chronicle"][-60:]
        g = game_parse(ans)
        # v39.4: moteur d'état — statut tolérant + inventaire / jauges déduits de la narration
        try:
            res = game_apply_turn(st.get("status", ""), ans, dice=int(st.pop("_dice", 0) or 0), tick=count)
        except Exception as e:
            log(f"game_apply_turn: {e}")
            res = {"status": game_merge_status(st.get("status", ""), g["status"]), "gained": [], "lost": [],
                   "stat_changes": [], "quest": "", "notes": []}
        if res["status"] and (st.get("status") or g["status"]):
            st["status"] = res["status"]
            st["log"][-1]["status"] = res["status"]
        st["inv_new"] = res["gained"]
        qv = (res.get("quest") or "").strip()
        if not qv:
            for k, v in game_parse_status(st.get("status", ""))["fields"]:
                if game_norm_key(k) in ("QUÊTE", "PISTE"):
                    qv = v.strip()
        if qv and qv.strip(" .-").lower() not in ("n/a", "aucune", "?"):
            if not st["quests"] or st["quests"][-1] != qv:
                st["quests"] = [q for q in st["quests"] if q != qv] + [qv]
                st["quests"] = st["quests"][-20:]
        fx = []
        if res["gained"]:
            fx.append("+" + ", +".join(res["gained"]))
        if res["lost"]:
            fx.append("−" + ", −".join(res["lost"]))
        fx += res["stat_changes"] + res["notes"]
        auto = False
        if game_reply_incomplete(ans, g["choices"]):  # v41.1 : réponse coupée ou sans choix
            if not st.get("_autocont"):
                st["_autocont"] = 1
                auto = True
            else:
                st["_autocont"] = 0
                if not g["choices"]:
                    g["choices"] = list(GAME_FALLBACK_CHOICES)
        else:
            st["_autocont"] = 0
        st["choices"] = g["choices"]
        start = self.game_txt.index("end-1c")
        ikey = ""
        if self._game_img_on():
            try:
                ikey = game_img_plan(st, self._game_pick_cache).get(len(st["log"]) - 1, "")
            except Exception as e:
                log(f"game_img_plan: {e}")
        li = len(st["log"]) - 1
        if ikey and self._game_gen_on():
            self._game_gen_request(st, li, ikey, ans)
        self._game_render_reply(ans, st["log"][-1].get("status", ""), img_key=ikey, animate=bool(ikey), li=li)
        if fx:
            line = "🎒 Pip-Boy : " + " · ".join(fx)
            st["log"].append({"who": "fx", "text": line})
            self._game_w(line + "\n\n", "check")
        self._game_scroll_to(start)
        self._game_update_pip()
        self._game_set_choices(g["choices"])
        self._game_paint_header()
        self._game_autosave()
        self._game_beep("turn")
        self.ent.focus_set()
        if auto:
            self._game_sys("↻ Réponse coupée ou sans choix — je demande la suite au maître du jeu…")
            self.after(250, lambda: self.game is st and not self.busy and
                       self._game_send(GAME_FOLLOWUP, display="(suite et choix demandés)", count=False))
        elif g["choices"] == GAME_FALLBACK_CHOICES:
            self._game_sys("▶ Pas de choix proposés : choix de secours (▶ Continuer = la suite).")

    # ---- ☢ Pip-Boy
    def _game_update_pip(self):
        st = self.game or {}
        info = game_parse_status(st.get("status", "")) if st.get("status") else {"title": "", "fields": [], "bars": []}
        self._pip_info = info
        self.pip_title.config(text=f"▓▓ {info['title'] or 'PIP-BOY 3000'} ▓▓"[:34])
        self._game_draw_bars()
        P = self.pip_txt
        P.configure(state="normal")
        P.delete("1.0", "end")
        barred = {b[0] for b in info["bars"]}
        if not info["fields"]:
            P.insert("end", "En attente du premier statut…\n", "k")
        for k, v in info["fields"]:
            if k in barred:
                continue
            if k.startswith("INVENTAIRE") or k.startswith("INDICES"):
                P.insert("end", f"\n{k}\n", "h")
                newk = {" ".join(game_item_words(x)) for x in (st.get("inv_new") or [])}
                for it in [x.strip() for x in re.split(r",|;", v) if x.strip()][:20]:
                    if " ".join(game_item_words(it)) in newk or any(
                            game_item_match([(1, it)], x) == 0 for x in (st.get("inv_new") or [])):
                        P.insert("end", f" ✚ {it}  NOUVEAU\n", "cur")
                    else:
                        P.insert("end", f" • {it}\n", "v")
                continue
            P.insert("end", f"{k}: ", "k")
            P.insert("end", f"{v}\n", "v")
        if st.get("quests"):
            P.insert("end", "\n📓 JOURNAL DE QUÊTES\n", "h")
            qs = st["quests"]
            for i, q in enumerate(qs[-8:]):
                last = i == len(qs[-8:]) - 1
                P.insert("end", (" ▶ " if last else " ✓ ") + q + "\n", "cur" if last else "old")
        if st.get("chronicle"):
            P.insert("end", "\n🧭 CHRONIQUE\n", "h")
            for c in st["chronicle"][-10:]:
                P.insert("end", f" {c}\n", "k")
        P.configure(state="disabled")

    def _game_draw_bars(self):
        G = GAME_COLORS
        cv = self.pip_bars
        cv.delete("all")
        bars = (getattr(self, "_pip_info", None) or {}).get("bars", [])
        w = max(120, cv.winfo_width() or 250)
        y = 4
        for k, v, mx in bars[:6]:
            r = max(0.0, min(1.0, v / mx if mx else 0))
            bad_high = k.startswith(("RAD", "FAIM", "SOIF"))
            danger = r if bad_high else 1 - r
            col = G["green"] if danger < 0.4 else (G["amber"] if danger < 0.7 else G["bad"])
            cv.create_text(2, y + 7, text=k[:6], anchor="w", fill=G["fg"], font=("Consolas", 9, "bold"))
            x0, x1 = 58, w - 64
            cv.create_rectangle(x0, y + 1, x1, y + 13, outline=G["line"], fill=G["art"])
            if r > 0:
                cv.create_rectangle(x0 + 1, y + 2, x0 + 1 + (x1 - x0 - 2) * r, y + 12, outline="", fill=col)
            cv.create_text(w - 2, y + 7, text=f"{v}/{mx}", anchor="e", fill=G["fg"], font=("Consolas", 9))
            y += 18
        cv.configure(height=max(6, y))

    # ---- ✨ Générer un jeu avec Padawan
    def game_generate(self, parent=None):
        from tkinter import simpledialog
        if self.busy:
            self.say("sys", "✨ Padawan est occupé — réessaie dans un instant.")
            return
        idea = simpledialog.askstring(
            "✨ Générer un jeu avec Padawan",
            "Ton idée en une ligne (ex. « survie dans une cabane à sucre hantée », « pirates du Saint-Laurent ») :",
            parent=parent or self)
        if not idea or not idea.strip():
            return
        if not self.ready or not self.model_ready:
            if not self._ensure_model_ready_or_kick():
                return
        self.say("sys", f"✨ Padawan écrit un prompt de jeu pour : {idea.strip()}…")
        self.lock(True, "✨ génération du prompt de jeu…")
        threading.Thread(target=self._game_generate_worker, args=(idea.strip(), parent), daemon=True).start()

    def _game_generate_worker(self, idea: str, parent):
        try:
            txt = chat(model_id_from_label(self.mvar.get()), GAME_GEN_ASK.replace("{idee}", idea),
                       system=GAME_GEN_SYSTEM, cancel=self._cancel, raw_system=True,
                       options={"num_predict": 1600, "temperature": 0.8})
            self.after0(self._game_generate_done, idea, txt, parent)
        except Exception as e:
            self.after0(self.say, "sys", f"✨ Génération impossible : {e}")
        finally:
            self.after0(self.lock, False, "● prêt")

    def _game_generate_done(self, idea: str, txt: str, parent):
        if self._cancel.is_set() or not (txt or "").strip() or txt.startswith("⚠"):
            self.say("sys", "✨ Génération annulée ou vide.")
            return
        text = game_fix_generated(txt)
        name = "🎮 " + (idea[:1].upper() + idea[1:])[:60]
        q = self.prompts.upsert({"id": PromptStore._new_id(), "name": name, "role": "tous", "mode": "remplacer",
                                 "kind": "jeu", "keep_base": True, "text": text})
        self.prompts.save()
        self._refresh_prompt_ui()
        win = getattr(self, "_prompts_win", None)
        if win is not None and win.winfo_exists():
            win._fill_list()
            win._select_id(q["id"])
        self.say("sys", f"✨ Nouveau jeu « {name} » créé dans 📜 Prompts ({len(text)} caractères).")
        if messagebox.askyesno("✨ " + name, "Le prompt de jeu est prêt.\n\nJouer tout de suite ?",
                               parent=parent if parent is not None and parent.winfo_exists() else self):
            self.game_start(q["id"], ask=False)

    def _game_toggle_resume(self):
        self.cfg["game_resume_on_start"] = bool(self._game_resume_var.get())
        savej(CFG_FILE, self.cfg)
        self.say("sys", "🎮 Au démarrage : " + ("Padawan rouvre ta dernière partie." if self.cfg["game_resume_on_start"]
                                                 else "Chercheur (sérieux d'abord). 🎮 Jouer reprend ta partie."))

    def _game_menu(self, event=None):
        m = tk.Menu(self, tearoff=0, bg=C["card"], fg=C["fg"], activebackground=C["gold"],
                    activeforeground="#1a1408", font=("Segoe UI", 11), bd=0)
        cur = (self.game or {}).get("pid", "")
        games = self._game_prompts()
        if not games:
            m.add_command(label="     (aucun jeu — ✨ en créer un)", state="disabled")
        for p in games:
            m.add_command(label=f"{'▶' if p['id'] == cur else '   '}  {p['name']}",
                          command=lambda pid=p["id"]: self.game_start(pid))
        m.add_separator()
        m.add_command(label="     ✨ Créer un jeu avec Padawan…", command=self.game_generate)
        self._game_resume_var = tk.BooleanVar(value=bool(self.cfg.get("game_resume_on_start", False)))
        m.add_checkbutton(label="     Rouvrir la dernière partie au démarrage", variable=self._game_resume_var,
                          command=self._game_toggle_resume)
        if self.game:
            m.add_command(label="     ↩ Quitter le jeu", command=self.game_quit)
        m.add_command(label="     📜 Gérer mes prompts…   Ctrl+P", command=self.show_prompts)
        self._theme_fix(m)
        x, y = (event.x_root, event.y_root) if event is not None else (self.winfo_pointerx(), self.winfo_pointery())
        try:
            m.tk_popup(x, y)
        finally:
            m.grab_release()

    # ── v39.4: 📰 Nouvelles (briefings sourcés, un clic) ─────────────────────────
    def _news_prompt(self, kind: str) -> Dict[str, Any]:
        p = self.prompts.get("n_" + kind) if getattr(self, "prompts", None) else None
        if not p:
            seed = next(s for s in NEWS_SEEDS if s["builtin"] == kind)
            p = dict(seed, id="n_" + kind)
        return p

    def _news_menu(self, event=None):
        m = tk.Menu(self, tearoff=0, bg=C["card"], fg=C["fg"], activebackground=C["gold"],
                    activeforeground="#1a1408", font=("Segoe UI", 11), bd=0)
        for kind, icon, lab in (("geo_futur", "🌍", "Géopolitique (vue de 2077)"), ("decouvertes", "🔭", "Découvertes & avancées")):
            m.add_command(label=f"{icon}  {lab} — dernières 24 h", command=lambda k=kind: self.news_brief(k, "d"))
            m.add_command(label=f"{icon}  {lab} — cette semaine", command=lambda k=kind: self.news_brief(k, "w"))
            last = news_last(kind)
            m.add_command(label=f"{icon}  Ce qui a changé depuis le dernier briefing"
                                + (f"  ({last['date']})" if last else "  (aucun encore)"),
                          command=lambda k=kind: self.news_brief(k, "auto", changes=True),
                          state="normal" if last else "disabled")
            m.add_command(label=f"{icon}  🎯 Cibler un sujet…", command=lambda k=kind: self._news_ask_focus(k))
            m.add_separator()
        m.add_command(label="🔁  Régénérer le dernier briefing", command=self.news_regenerate,
                      state="normal" if getattr(self, "_brief_ctx", None) else "disabled")
        m.add_command(label="📂  Ouvrir le dossier des briefings", command=self.news_open_dir)
        m.add_command(label="📜  Modifier ces prompts…   Ctrl+P", command=self.show_prompts)
        self._theme_fix(m)
        x, y = (event.x_root, event.y_root) if event is not None else (self.winfo_pointerx(), self.winfo_pointery())
        try:
            m.tk_popup(x, y)
        finally:
            m.grab_release()

    def _news_ask_focus(self, kind: str):
        from tkinter import simpledialog
        ex = "ex. Arctique, Iran, Taïwan, Sahel…" if kind == "geo_futur" else \
            "ex. médecine régénératrice, fusion, archéologie maya, IA…"
        q = simpledialog.askstring(NEWS_KINDS[kind]["label"], f"Quel sujet ou domaine ? ({ex})", parent=self)
        if q and q.strip():
            self.news_brief(kind, "w", question=q.strip()[:80])

    def news_open_dir(self):
        try:
            os.makedirs(BRIEF_DIR, exist_ok=True)
            os.startfile(BRIEF_DIR)  # type: ignore[attr-defined]
        except Exception as e:
            self.say("sys", f"Dossier des briefings : {BRIEF_DIR} ({e})")

    def news_regenerate(self):
        ctx = getattr(self, "_brief_ctx", None)
        if ctx:
            self.news_brief(*ctx, nocache=True)

    def news_brief(self, kind: str, period: str = "d", changes: bool = False, question: str = "",
                   nocache: bool = False):
        """Briefing sourcé en un clic : vraie chasse web (news datées, FR + EN) puis le prompt favori 🌍 / 🔭.
        N'active PAS le prompt : le Chercheur garde son prompt habituel ensuite."""
        if kind not in NEWS_KINDS:
            return
        if self.busy:
            self.say("sys", "📰 Padawan est occupé — réessaie dans un instant (Échap = annuler).")
            return
        if self.game:
            self.game_quit()
        prev = news_last(kind) if changes else None
        if changes and not prev:
            self.say("sys", "📰 Pas encore de briefing précédent : je fais celui de la semaine.")
            changes, period = False, "w"
        if period == "auto":
            age = time.time() - float((prev or {}).get("t") or 0)
            period = "d" if age < 36 * 3600 else ("w" if age < 8 * 86400 else "m")
        p = self._news_prompt(kind)
        spec = NEWS_KINDS[kind]
        label = f"{spec['label']} — {NEWS_PERIODS.get(period, period)}" + (f" · {question}" if question else "") + \
            (" · 🔄 ce qui a changé" if changes else "")
        self._brief_ctx = (kind, period if not changes else "auto", changes, question)
        self.clear_hunt_context(wipe_role_hist=True, reason=f"briefing · {kind}")
        self.last_q = label
        self._last_kind = "brief"
        if self.router.active != "chercheur":
            self.set_role("chercheur", sync_mode=True)
        self.say("you", "📰 " + label, force_scroll=True, anchor=True)
        self.lock(True, f"📰 {spec['label']}…")
        self.mission_start()
        threading.Thread(target=self._news_job, args=(kind, period, changes, question, p, prev, label),
                         daemon=True).start()

    def _news_job(self, kind, period, changes, question, p, prev, label):
        try:
            if not ollama_up():
                self.after0(self._ui_status, "Ollama : absent → démarrage…", C["gold"])
                ok_boot, detail = ensure_ollama_running(cancel=self._cancel, allow_install=False)
                if ok_boot:
                    self.ready = True
            self.after0(self.mission_update, "formuler", "done", f"{len(NEWS_KINDS[kind]['queries'])} requêtes FR + EN")
            self.after0(self.mission_update, "moteurs", "running", "actualités datées…")

            def prog(msg):
                self.after0(self.mission_update, "moteurs", "running", msg)
            t0 = time.time()
            items, meta = news_collect(kind, period, question, cancel=self._cancel, on_progress=prog)
            self.after0(self.mission_update, "moteurs", "done", f"{len(items)} sources · {int(time.time() - t0)} s")
            self.after0(self.mission_update, "filtrer", "done", "dédoublonné · trié par date")
            self.after0(self.mission_update, "enrichir", "done", "pages lues")
            if self._cancel.is_set():
                self.after0(self.say, "sys", "Briefing annulé.")
                return
            if not items:
                err = _summarize_ddgs_errors(meta.get("errors") or [])
                self.after0(self.mission_update, "brief", "fail", "aucune source")
                self.after0(self.say, "sys", f"📰 Aucune nouvelle trouvée (hors ligne ?) — {err}. "
                                             "Je n'invente rien : réessaie dans un moment.")
                return
            self.hits = items
            self.after0(self.draw_sources)
            if meta.get("widened"):
                self.after0(self.say, "sys", "📰 Peu de nouvelles en 24 h : élargi à la semaine.")
            if not self.model_ready and not self._wait_model_ready():
                raise RuntimeError("Modèle pas chargé — voyant rouge.")
            self.after0(self.mission_update, "brief", "running", f"briefing · {len(items)} sources")
            mark_holder: list = []
            token_buf: list = []
            self.after0(lambda: mark_holder.append(self._begin_stream()))
            time.sleep(0.05)

            def on_tok(t: str):
                if mark_holder:
                    self.after0(self._append_stream, mark_holder[0], t, token_buf)
            user = news_user_msg(kind, items, period, question, prev=prev, widened=bool(meta.get("widened")),
                                 fmt=news_format_part(p.get("text", "")))
            ans = self._ollama(user, on_token=on_tok, use_history=False, override=p,
                               question=question or NEWS_KINDS[kind]["default_q"], options=dict(NEWS_GEN_OPTIONS))
            if self._cancel.is_set():
                self.after0(self.mission_update, "brief", "fail", "annulé")
                self.after0(self.say, "sys", "Briefing annulé.")
                return
            ans, cited = news_postprocess(ans, items)
            self.last_a = ans
            if mark_holder:
                self.after0(self._finish_stream, mark_holder[0], ans)
            else:
                self.after0(self.say, "ai", ans)
            self.after0(self.say_links)
            self.after0(self.mission_update, "brief", "done", f"{len(cited)} sources citées")
            try:
                md, htm = news_save(kind, ans, period, question)
                self.after0(self.say, "sys", f"📰 Briefing gardé : {htm}  ·  🔁 Régénérer / 🔄 Ce qui a changé : menu 📰 Nouvelles")
            except Exception as e:
                log(f"news_save: {e}")
            self.after0(self.notify_done, "Padawan — 📰", f"{label} prêt")
        except Exception as e:
            self.after0(self.mission_update, "brief", "fail", str(e)[:60])
            self.after0(self.say, "sys", f"📰 Briefing raté : {e}")
        finally:
            self.after0(self.lock, False, "● prêt")


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

    # ── v39.1: Nouvelle conversation (contexte modèle propre) ───────────────
    def _tip(self, w, text):
        st = {"t": None}
        def show(e):
            try:
                t = tk.Toplevel(w); t.wm_overrideredirect(True)
                t.wm_geometry(f"+{e.x_root+12}+{e.y_root-48}")
                tk.Label(t, text=text, bg="#2a2418", fg="#f3e6c8", font=("Segoe UI", 8),
                         justify="left", padx=8, pady=4, relief="solid", bd=1).pack()
                st["t"] = t
            except Exception:
                pass
        def hide(e):
            if st["t"] is not None:
                try: st["t"].destroy()
                except Exception: pass
                st["t"] = None
        w.bind("<Enter>", show, add="+"); w.bind("<Leave>", hide, add="+"); w.bind("<ButtonPress>", hide, add="+")

    def _archive_role_histories(self, reason: str = "") -> Optional[str]:
        """Archive session + historiques des rôles dans CONV_DIR puis vide le contexte modèle."""
        self.router._ensure_slots()
        roles = {rid: list(self.mem["roles"][rid].get("history") or []) for rid in RoleRouter.ROLES}
        sess = list(self.session.get("h") or []) if hasattr(self, "session") else []
        path = conv_archive(roles, sess, reason=reason, role=self.router.active)
        self.router.clear_history()
        savej(MEM_FILE, self.mem)
        return path

    def new_conversation(self, _retry: int = 0):
        if self.busy:
            self.cancel_job()
            if _retry < 40:
                self.after(150, self.new_conversation, _retry + 1)
            return
        try:
            path = self._archive_role_histories(reason="nouvelle conversation")
        except Exception as e:
            log(f"new_conversation archive: {e}"); path = None
        self.chat.configure(state="normal")
        self.chat.delete("1.0", "end")
        self.chat.configure(state="disabled")
        self.session = {"t": now(), "h": []}
        self.mem["sessions"].append({"start": self.session["t"], "history": self.session["h"]})
        self.mem["sessions"] = self.mem["sessions"][-30:]
        self.last_q = self.last_a = ""
        try: self.mission_clear()
        except Exception: pass
        self.clear_hunt_context(wipe_role_hist=True, reason="nouvelle conversation")
        try:
            for w in self.sugg_bar.winfo_children(): w.destroy()
        except Exception: pass
        savej(MEM_FILE, self.mem)
        self.say("sys", "🧹 Nouvelle conversation — l'esprit clair ! "
                 + ("L'ancienne est dans 🕘 Historique (Ctrl+Shift+H). " if path else "")
                 + "Tape en bas →")
        self._conv_flash()
        self.ent.focus_set()

    def _conv_flash(self):
        """Petite animation: balayage doré sur le chat + toast."""
        try:
            self._ui_status("🧹 Conversation neuve", C["ok"])
        except Exception:
            pass
        cols = ["#5a4a24", "#7a6430", "#a5843c", "#d8b468", "#a5843c", "#7a6430", "#5a4a24"]
        try:
            orig = self.chat.cget("bg")
        except Exception:
            return
        def step(i=0):
            try:
                if i < len(cols):
                    self.chat.configure(bg=cols[i]); self.after(45, step, i + 1)
                else:
                    self.chat.configure(bg=orig)
            except Exception:
                pass
        step()
        try:
            t = tk.Toplevel(self); t.wm_overrideredirect(True); t.attributes("-topmost", True)
            tk.Label(t, text="🧹  Nouvelle conversation", bg=C["gold"], fg="#1a1408",
                     font=("Segoe UI", 14, "bold"), padx=22, pady=10).pack()
            self.update_idletasks()
            x = self.chat.winfo_rootx() + self.chat.winfo_width() // 2 - 140
            y0 = self.chat.winfo_rooty() + 30
            def fly(k=0):
                try:
                    if k <= 12:
                        t.wm_geometry(f"+{x}+{y0 + k * 3}")
                        try: t.attributes("-alpha", min(1.0, 0.25 + k * 0.08))
                        except Exception: pass
                        self.after(25, fly, k + 1)
                    else:
                        self.after(1100, t.destroy)
                except Exception:
                    pass
            fly()
        except Exception:
            pass

    def show_conv_history(self):
        items = conv_list()
        pop = tk.Toplevel(self); pop.title("🕘 Historique des conversations")
        pop.configure(bg=C["bg"]); pop.geometry("760x520"); pop.transient(self)
        tk.Label(pop, text="Double-clic ou Entrée = relire · rien n'est réinjecté dans le modèle",
                 bg=C["bg"], fg=C["dim"], font=("Segoe UI", 9)).pack(anchor="w", padx=10, pady=(8, 2))
        body = tk.PanedWindow(pop, orient="horizontal", bg=C["bg"], sashwidth=4)
        body.pack(fill="both", expand=True, padx=8, pady=6)
        lb = tk.Listbox(body, bg=C["card"], fg=C["fg"], font=("Segoe UI", 9), activestyle="none",
                        selectbackground=C["gold"], selectforeground="#1a1408", width=34)
        txt = tk.Text(body, bg=C["input"], fg=C["fg"], wrap="word", font=("Segoe UI", 10))
        body.add(lb); body.add(txt)
        for it in items:
            lb.insert("end", f"{it['label']}  ·  {it['title'][:40]}")
        def view(e=None):
            sel = lb.curselection()
            if not sel: return
            txt.configure(state="normal"); txt.delete("1.0", "end")
            txt.insert("end", conv_render(items[sel[0]]["path"]))
            txt.configure(state="disabled")
        lb.bind("<<ListboxSelect>>", view); lb.bind("<Return>", view); lb.bind("<Double-1>", view)
        bar = tk.Frame(pop, bg=C["bg"]); bar.pack(fill="x", padx=8, pady=(0, 8))
        tk.Button(bar, text="📂 Ouvrir le dossier", relief="flat", bg=C["card"], fg=C["fg"],
                  command=lambda: os.startfile(CONV_DIR) if hasattr(os, "startfile") else None).pack(side="left")
        tk.Button(bar, text="Fermer (Échap)", relief="flat", bg=C["card"], fg=C["fg"],
                  command=pop.destroy).pack(side="right")
        pop.bind("<Escape>", lambda e: pop.destroy())
        if items:
            lb.selection_set(0); view()
        else:
            txt.insert("end", "Aucune conversation archivée pour l'instant.")
        lb.focus_set()

    def clear_chat(self):
        return self.new_conversation()

    def _clear_chat_old(self):
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
            self.cfg["model"] = getattr(self, "_model_before", None) or model_id_from_label(self.mvar.get())
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
        try:  # v40.0 : arrête les programmes / serveurs d'aperçu lancés par l'Atelier
            if getattr(self, "_atelier", None) is not None:
                self._atelier.shutdown()
        except Exception:
            pass
        try:  # v41.0 : arrête le moteur d'images s'il a été démarré par Padawan
            if getattr(self, "_studio_view", None) is not None:
                self._studio_view.shutdown()
            if getattr(self, "_studio", None) is not None:
                self._studio.engine.stop()
        except Exception:
            pass
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
    try:  # v1.2.3 : themes communs de la suite (menu/bouton « 🎨 Thème », Ctrl+Maj+T)
        import padawan_themes as _pt
        _pt.install(app, "padawan", C, roles={"fg": "TEXT"})
    except Exception:
        pass
    try:  # v39.6 : entrée « 🧠 Modèles » dans la barre de menus
        _mn = app.cget("menu")
        _mb = app.nametowidget(_mn) if _mn else None
        if _mb is None:
            _mb = tk.Menu(app)
            app.config(menu=_mb)
        _mb.add_command(label="🧠 Modèles (Ctrl+M)", command=app.show_models)
        _mb.add_command(label="💻 Atelier (Ctrl+K)", command=app.show_atelier)  # v40.0
    except Exception as _e:
        log(f"menu modeles: {_e}")
    try:
        app.mainloop()
    except Exception as e:
        print(e)
        log(str(e))
        input("entree...")
