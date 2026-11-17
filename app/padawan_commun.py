# -*- coding: utf-8 -*-
"""
Padawan commun 1.0 - chemins des donnees de la suite et lancement des programmes.
Utilise par Premiers pas, Recherche Padawan et Coffre Padawan.
Meme logique que les modules : variable <APP>_DATA / PADAWAN_DATA, sinon C:\\web\\FTP_HOME\\<SOUS>
(PC de Marc), sinon Documents\\Padawan\\<App>. Reglages perso : C:\\web_private\\<App> (PC de Marc)
ou %APPDATA%\\Padawan (jamais FTP_HOME) : private_dir(), migrate_private().
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
    cfg = read_json(archiveur_config(), {}) or {}
    return cfg.get("archive_root") or data_dir("Archiveur", "ARCHIVEUR")


def archiveur_config():
    p = private_file("Archiveur", "archiveur_config.json")
    old = os.path.join(HERE, "archiveur_config.json")
    return p if os.path.isfile(p) or not os.path.isfile(old) else old


def arsenal_json():
    p = private_file("Arsenal", "arsenal.json")
    old = os.path.join(HERE, "arsenal.json")
    return p if os.path.isfile(p) or not os.path.isfile(old) else old


def facteur_dir():
    return data_dir("Facteur", "FACTEUR")


def journal_dir():
    """Journal de bord : JOURNAL_DATA / PADAWAN_DATA\\Journal, sinon C:\\web_private\\journal (PC de Marc,
    hors de FTP_HOME qui est publie sur le web), sinon Documents\\Padawan\\Journal."""
    env = os.environ.get("JOURNAL_DATA", "").strip()
    if env:
        return env
    root = os.environ.get("PADAWAN_DATA", "").strip()
    if root:
        return os.path.join(root, "Journal")
    if IS_WIN and os.path.isdir(r"C:\web"):
        return r"C:\web_private\journal"
    return os.path.join(os.path.expanduser("~"), "Documents", "Padawan", "Journal")


def retro_dir():
    p = r"C:\web_private\retro"
    if os.path.isdir(p):
        return p
    return os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "Padawan", "Retro")


# ── Réglages et état privés (2026-11-17) ─────────────────────────────────────
# PC de Marc : C:\web_private\<App>  (jamais sous FTP_HOME, qui est publié sur le web)
# Autre PC   : %APPDATA%\Padawan (Padawan lui-même) ou %APPDATA%\Padawan\<App>
# Tests      : <APP>_PRIVATE (dossier d'une app) ou PADAWAN_PRIVATE_ROOT\<App> (toute la suite, bak compris).
WEB_PRIVATE = r"C:\web_private"


def _appdata_padawan():
    return os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "Padawan")


def has_web_private():
    return IS_WIN and os.path.isdir(WEB_PRIVATE)


def private_dir(app="Padawan", create=True):
    """Dossier privé d'une application de la suite (réglages, état, journaux, sauvegardes)."""
    env = os.environ.get(app.upper() + "_PRIVATE", "").strip()
    root = os.environ.get("PADAWAN_PRIVATE_ROOT", "").strip()
    if env:
        d = env
    elif root:
        d = os.path.join(root, app)
    elif has_web_private():
        d = os.path.join(WEB_PRIVATE, app)
    else:
        d = _appdata_padawan() if app.lower() == "padawan" else os.path.join(_appdata_padawan(), app)
    if create:
        try:
            os.makedirs(d, exist_ok=True)
        except OSError:
            pass
    return d


def private_file(app, name):
    return os.path.join(private_dir(app), name)


def bak_dir():
    """Racine des .bak : C:\\web_private\\bak (PC de Marc), sinon <privé>\\bak."""
    root = os.environ.get("PADAWAN_PRIVATE_ROOT", "").strip()
    if root:
        return os.path.join(root, "bak")
    if has_web_private():
        return os.path.join(WEB_PRIVATE, "bak")
    return os.path.join(_appdata_padawan(), "bak")


def _same(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def migrate_private(app, old_dir, names, new_dir=None, log=None):
    """Déménage old_dir\\<nom> vers le dossier privé de l'app (fichiers ou dossiers).
    - ancien présent et nouveau absent : copie (avec date) vers le nouveau ;
    - ensuite l'ancien est rangé dans bak\\config_move_<date>\\<App>\\ (jamais effacé, jamais laissé en place) ;
    - le nouveau n'est jamais écrasé. Retourne [(nom, action)]. Ne lève jamais d'exception."""
    import shutil, time
    out = []
    try:
        new_dir = new_dir or private_dir(app)
        if not old_dir or not os.path.isdir(old_dir) or _same(old_dir, new_dir):
            return out
        stamp = time.strftime("%Y%m%d")
        dest_bak = os.path.join(bak_dir(), "config_move_" + stamp, app)
        for name in names:
            old = os.path.join(old_dir, name)
            if not os.path.exists(old):
                continue
            new = os.path.join(new_dir, name)
            try:
                os.makedirs(new_dir, exist_ok=True)
                if os.path.isdir(old):
                    os.makedirs(new, exist_ok=True)
                    for r, _ds, fs in os.walk(old):
                        rel = os.path.relpath(r, old)
                        for f in fs:
                            t = os.path.normpath(os.path.join(new, rel, f))
                            if not os.path.exists(t):
                                os.makedirs(os.path.dirname(t), exist_ok=True)
                                shutil.copy2(os.path.join(r, f), t)
                    action = "copié"
                elif not os.path.exists(new):
                    tmp = new + ".migr_tmp"
                    shutil.copy2(old, tmp)
                    if os.path.getsize(tmp) != os.path.getsize(old):
                        raise OSError("copie incomplète")
                    os.replace(tmp, new)
                    action = "copié"
                else:
                    action = "déjà présent (ancien rangé)"
                os.makedirs(dest_bak, exist_ok=True)
                b = os.path.join(dest_bak, name)
                if os.path.exists(b):
                    b = os.path.join(dest_bak, name + "." + time.strftime("%H%M%S"))
                shutil.move(old, b)
                out.append((name, action + " → bak"))
            except Exception as ex:   # fichier verrouillé, etc. : on réessaiera au prochain démarrage
                out.append((name, "erreur : %s" % ex))
        if out:
            try:
                with open(os.path.join(dest_bak, "_migration.log"), "a", encoding="utf-8") as f:
                    for n, a in out:
                        f.write("%s  %s  %s -> %s : %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), app,
                                                           os.path.join(old_dir, n), os.path.join(new_dir, n), a))
            except Exception:
                pass
        if log:
            for n, a in out:
                try:
                    log("migration %s : %s %s" % (app, n, a))
                except Exception:
                    pass
    except Exception as ex:
        out.append(("*", "erreur : %s" % ex))
    return out


def padawan_file(name):
    """Fichier privé de Padawan (config.json, memory.json, tasks.json...)."""
    return private_file("Padawan", name)


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
    "capture": ("capturescreen1.py", "CaptureScreen"),
    "grimoire": ("grimoire1.py", "Grimoire"),
    "journal": ("journal_bord.py", "Journal de bord"),
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
