# -*- coding: utf-8 -*-
"""
Padawan commun 1.0 - chemins des donnees de la suite et lancement des programmes.
Utilise par Premiers pas, Recherche Padawan et Coffre Padawan.
Meme logique que les modules : variable <APP>_DATA / PADAWAN_DATA, sinon C:\\web\\FTP_HOME\\<SOUS>
(PC de Marc), sinon Documents\\Padawan\\<App>. Reglages perso : %APPDATA%\\Padawan (jamais FTP_HOME).
"""
import os, sys, json, subprocess, unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
FTP_HOME = r"C:\web\FTP_HOME"
IS_WIN = os.name == "nt"
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0) if IS_WIN else 0


def data_dir(app, ftp_sub):
    env = os.environ.get(app.upper() + "_DATA", "").strip()
    if env:
        return env
    root = os.environ.get("PADAWAN_DATA", "").strip()
    if root:
        return os.path.join(root, app)
    if os.path.isdir(FTP_HOME):
        return os.path.join(FTP_HOME, ftp_sub)
    return os.path.join(os.path.expanduser("~"), "Documents", "Padawan", app)


def settings_dir():
    d = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "Padawan")
    os.makedirs(d, exist_ok=True)
    return d


def load_settings(name, default):
    p = os.path.join(settings_dir(), name)
    try:
        with open(p, encoding="utf-8-sig") as f:
            d = json.load(f)
        if isinstance(default, dict) and isinstance(d, dict):
            out = dict(default); out.update(d); return out
        return d
    except Exception:
        return default


def save_settings(name, data):
    p = os.path.join(settings_dir(), name)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return default


def grimoire_db():
    return os.path.join(data_dir("Grimoire", "GRIMOIRE"), "grimoire.db")


def archiveur_root():
    cfg = read_json(os.path.join(HERE, "archiveur_config.json"), {}) or {}
    return cfg.get("archive_root") or data_dir("Archiveur", "ARCHIVEUR")


def arsenal_json():
    return os.path.join(HERE, "arsenal.json")


def facteur_dir():
    return data_dir("Facteur", "FACTEUR")


def retro_dir():
    p = r"C:\web_private\retro"
    if os.path.isdir(p):
        return p
    return os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "Padawan", "Retro")


def norm(s):
    """minuscules sans accents (recherche tolerante)."""
    s = unicodedata.normalize("NFKD", str(s or "").lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def pythonw():
    exe = sys.executable or "pythonw"
    if IS_WIN and exe.lower().endswith("python.exe"):
        w = exe[:-10] + "pythonw.exe"
        if os.path.isfile(w):
            return w
    return exe


# Ressources en ligne de la suite (page publique GitHub)
GITHUB_URL = "https://github.com/marcsevigny1971/padawan-suite"
GITHUB_RELEASES = GITHUB_URL + "/releases/latest"
GITHUB_ISSUES = GITHUB_URL + "/issues"
PRESENTATION_URL = "https://marcsevigny1971.github.io/padawan-suite/"
RESSOURCES = [  # (libelle, url, description)
    ("\U0001f3e0 Page du projet", GITHUB_URL, "Le code, le guide et les nouveaut\u00e9s."),
    ("\u2b06 Mises \u00e0 jour", GITHUB_RELEASES, "La derni\u00e8re version de l'installateur."),
    ("\U0001f4a1 Id\u00e9es et suggestions", GITHUB_ISSUES, "Une id\u00e9e, une question, un petit souci ?"),
    ("\u2728 Pr\u00e9sentation compl\u00e8te", PRESENTATION_URL, "Tous les outils, en d\u00e9tail."),
]


def open_url(url):
    """Ouvre un lien dans le navigateur par defaut. Retourne True si ok."""
    try:
        import webbrowser
        return bool(webbrowser.open(url, new=2))
    except Exception:
        return open_path(url)


PROGRAMMES = {  # cle : (fichier, nom)
    "padawan": ("padawan39.py", "Padawan IA"),
    "tableau": ("tableau_bord.py", "Tableau de bord"),
    "archiveur": ("archiveur5.py", "Archiveur"),
    "grimoire": ("grimoire1.py", "Grimoire"),
    "arsenal": ("arsenal1.py", "Arsenal"),
    "facteur": ("facteur1.py", "Facteur"),
    "gestionnaire": ("gestionnaire_fichiers5.py", "Gestionnaire de fichiers"),
    "messager": ("messager2.py", "Messager"),
    "chantier": ("chantier1.py", "Chantier"),
    "retro": ("retro1.py", "R\u00e9tro"),
    "recherche": ("recherche_padawan.py", "Recherche Padawan"),
    "coffre": ("coffre_padawan.py", "Coffre Padawan"),
    "premiers": ("premiers_pas.py", "Premiers pas"),
}


def launch(key_or_script, *args):
    """Lance un programme de la suite sans console. Retourne True si lance."""
    script = PROGRAMMES.get(key_or_script, (key_or_script, ""))[0]
    path = os.path.join(HERE, script)
    if not os.path.isfile(path):
        return False
    subprocess.Popen([pythonw(), path] + [str(a) for a in args], cwd=HERE, creationflags=NOWIN)
    return True


def open_path(p):
    try:
        if IS_WIN:
            os.startfile(p)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", p])
        return True
    except Exception:
        return False


def reveal(p):
    if IS_WIN and os.path.exists(p):
        subprocess.Popen(["explorer", "/select,", os.path.normpath(p)])
        return True
    return open_path(os.path.dirname(p) or p)


# couleurs communes (theme sombre de la suite)
C = {"BG": "#0f1724", "PANEL": "#16213a", "CARD": "#1c2a48", "TEXT": "#e8eefc", "DIM": "#9fb0d0",
     "ACC": "#3ad1c2", "ACC2": "#ffcc55", "ENTRY": "#0b1220", "BTN": "#24406e", "BTNH": "#2f5596"}
