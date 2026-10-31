# -*- coding: utf-8 -*-
"""
Chantier 1 — Projet Padawan
Installateur de serveurs À LA DEMANDE (rien n'est installé par défaut) :
  • Web : Apache (Apache Lounge) ou Caddy  + PHP (windows.php.net)
  • SQL : MariaDB (zip portable officiel)
  • FTP : pyftpdlib (portable, Python) — ou FileZilla Server via winget
  • MQTT : Mosquitto (winget, sinon installateur officiel)
Structure : C:\\web (pages), C:\\web\\FTP_HOME (public), C:\\web_private\\chantier (binaires, config, mots de passe, journaux).
Sans C:\\web : Documents\\Padawan\\Chantier\\web et %LOCALAPPDATA%\\Padawan\\Chantier\\private.
Ne plante jamais sans Internet. Ne touche jamais aux ports déjà utilisés ni aux serveurs existants.
Options : --make-icons  --selftest  --test-gui MS
"""
import os, sys, re, json, time, math, shutil, socket, secrets, string, hashlib, zipfile, threading, queue, subprocess, webbrowser, traceback
import urllib.request, urllib.error

APP = "Chantier"
VERSION = "1.1"
HERE = os.path.dirname(os.path.abspath(__file__))
IS_WIN = os.name == "nt"
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0) if IS_WIN else 0
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chantier-Padawan/1.1"

# ---------------------------------------------------------------- chemins
def _paths():
    if os.path.isdir(r"C:\web"):
        www = r"C:\web"
        priv_root = r"C:\web_private"
    else:
        docs = os.path.join(os.path.expanduser("~"), "Documents")
        www = os.path.join(docs, "Padawan", "Chantier", "web")
        priv_root = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "Padawan", "Chantier", "private")
    priv = os.path.join(priv_root, "chantier")
    return {
        "www": www, "pub": os.path.join(www, "FTP_HOME"), "priv_root": priv_root, "priv": priv,
        "bin": os.path.join(priv, "bin"), "conf": os.path.join(priv, "conf"), "logs": os.path.join(priv, "logs"),
        "data": os.path.join(priv, "data"), "dl": os.path.join(priv, "telechargements"),
        "state": os.path.join(priv, "chantier_etat.json"), "secrets": os.path.join(priv, "secrets_chantier.json"),
    }
P = _paths()

def ensure_dir(d):
    try:
        os.makedirs(d, exist_ok=True); return True
    except Exception:
        return False

def fwd(p):  # chemins style config (slash)
    return p.replace("\\", "/")

# ---------------------------------------------------------------- secrets + journal masqué
_SECRETS_CACHE = {}
def load_secrets():
    global _SECRETS_CACHE
    try:
        with open(P["secrets"], "r", encoding="utf-8") as f:
            _SECRETS_CACHE = json.load(f)
    except Exception:
        _SECRETS_CACHE = {}
    return _SECRETS_CACHE

def save_secrets(d):
    ensure_dir(P["priv"])
    tmp = P["secrets"] + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2)
    os.replace(tmp, P["secrets"])
    if IS_WIN:  # restreindre l'accès à l'utilisateur courant (best effort)
        try:
            subprocess.run(["icacls", P["secrets"], "/inheritance:r", "/grant:r", f"{os.environ.get('USERNAME','')}:F"],
                           capture_output=True, creationflags=NOWIN, timeout=15)
        except Exception:
            pass

def gen_password(n=24):
    alpha = string.ascii_letters + string.digits + "-_"
    return "".join(secrets.choice(alpha) for _ in range(n))

def mask(text):
    s = str(text)
    for v in list(_SECRETS_CACHE.values()):
        if isinstance(v, str) and len(v) >= 6:
            s = s.replace(v, "••••••")
    return s

LOGQ = queue.Queue()
def log(svc, msg):
    line = time.strftime("%H:%M:%S") + f" [{svc}] " + mask(msg)
    LOGQ.put((svc, line))
    if ensure_dir(P["logs"]):
        try:
            with open(os.path.join(P["logs"], "chantier.log"), "a", encoding="utf-8") as f:
                f.write(time.strftime("%Y-%m-%d ") + line + "\n")
        except Exception:
            pass

# ---------------------------------------------------------------- état
def load_state():
    try:
        with open(P["state"], "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_state(st):
    if not ensure_dir(P["priv"]):
        return
    try:
        with open(P["state"], "w", encoding="utf-8") as f:
            json.dump(st, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

# ---------------------------------------------------------------- réseau / ports / process
def port_busy(port, host="127.0.0.1"):
    try:
        with socket.create_connection((host, int(port)), timeout=0.4):
            return True
    except Exception:
        pass
    try:  # bind test (quelque chose écoute sur 0.0.0.0 sans accepter ?)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("0.0.0.0", int(port))); s.close()
        return False
    except Exception:
        return True

def free_port(prefs):
    for p in prefs:
        if not port_busy(p):
            return p
    for p in range(prefs[-1] + 1, prefs[-1] + 200):
        if not port_busy(p):
            return p
    return prefs[0]

def internet_ok():
    try:
        with socket.create_connection(("1.1.1.1", 443), timeout=2.5):
            return True
    except Exception:
        return False

def http_get(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()

def http_json(url):
    return json.loads(http_get(url).decode("utf-8", "replace"))

def download(url, dest, svc, progress=None, sha256=None):
    ensure_dir(os.path.dirname(dest))
    log(svc, f"Téléchargement : {url}")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    h = hashlib.sha256()
    with urllib.request.urlopen(req, timeout=60) as r, open(dest + ".part", "wb") as f:
        total = int(r.headers.get("Content-Length") or 0); done = 0
        while True:
            b = r.read(256 * 1024)
            if not b:
                break
            f.write(b); h.update(b); done += len(b)
            if progress and total:
                progress(done / total)
    if sha256 and h.hexdigest().lower() != sha256.lower():
        os.remove(dest + ".part")
        raise RuntimeError("SHA256 invalide pour " + os.path.basename(dest))
    os.replace(dest + ".part", dest)
    log(svc, f"Reçu {os.path.basename(dest)} ({os.path.getsize(dest)//1024} Ko)" + (" — SHA256 vérifié" if sha256 else ""))
    return dest

def unzip(zp, dest, svc):
    log(svc, f"Extraction vers {dest}")
    ensure_dir(dest)
    with zipfile.ZipFile(zp) as z:
        z.extractall(dest)

def find_file(root, name):
    for dp, dn, fn in os.walk(root):
        for f in fn:
            if f.lower() == name.lower():
                return os.path.join(dp, f)
    return None

def pid_alive(pid):
    if not pid:
        return False
    if IS_WIN:
        try:
            out = subprocess.run(["tasklist", "/FI", f"PID eq {int(pid)}", "/FO", "CSV", "/NH"], capture_output=True,
                                 text=True, creationflags=NOWIN, timeout=8).stdout
            return str(int(pid)) in out
        except Exception:
            return False
    try:
        os.kill(int(pid), 0); return True
    except Exception:
        return False

def kill_tree(pid):
    if IS_WIN:
        subprocess.run(["taskkill", "/PID", str(int(pid)), "/T", "/F"], capture_output=True, creationflags=NOWIN, timeout=15)
    else:
        try:
            os.kill(int(pid), 15)
        except Exception:
            pass

def winget_ok():
    return bool(shutil.which("winget"))

def run_logged(cmd, svc, timeout=900, env=None, stdin_text=None, cwd=None):
    log(svc, "> " + " ".join(f'"{c}"' if " " in str(c) else str(c) for c in cmd))
    r = subprocess.run(cmd, capture_output=True, text=True, creationflags=NOWIN, timeout=timeout, env=env,
                       input=stdin_text, cwd=cwd, encoding="utf-8", errors="replace")
    for ln in ((r.stdout or "") + (r.stderr or "")).splitlines()[-25:]:
        if ln.strip():
            log(svc, "  " + ln.strip())
    return r.returncode


# ---------------------------------------------------------------- détection des serveurs DÉJÀ installés (lecture seule)
# Chantier ne désinstalle et n'arrête JAMAIS un serveur existant : il le montre, c'est tout.
EXIST_NAMES = {"apache": "Apache", "mariadb": "MySQL/MariaDB", "ftp": "FTP (FileZilla)", "mosquitto": "Mosquitto", "docker": "Docker Desktop"}
EXIST_PROCS = {"apache": ["httpd.exe"], "mariadb": ["mysqld.exe", "mariadbd.exe"],
               "ftp": ["filezilla-server.exe", "filezillaserver.exe", "filezilla server.exe"],
               "mosquitto": ["mosquitto.exe"], "docker": ["docker desktop.exe", "com.docker.backend.exe"]}
EXIST_SVC = {"apache": r"^(apache|httpd)", "mariadb": r"^(mysql|mariadb)", "ftp": r"^filezilla", "mosquitto": r"^mosquitto",
             "docker": r"^com\.docker"}
EXIST_PORTS = {"apache": [80, 443], "mariadb": [3306], "ftp": [21], "mosquitto": [1883], "docker": []}
EXIST_GLOBS = {
    "apache": [r"C:\xampp\apache\bin\httpd.exe", r"C:\Apache24\bin\httpd.exe", r"C:\wamp64\bin\apache\*\bin\httpd.exe",
               r"C:\wamp\bin\apache\*\bin\httpd.exe", r"C:\laragon\bin\apache\*\bin\httpd.exe",
               r"C:\Program Files\Apache Software Foundation\*\bin\httpd.exe"],
    "mariadb": [r"C:\xampp\mysql\bin\mysqld.exe", r"C:\wamp64\bin\mysql\*\bin\mysqld.exe", r"C:\wamp64\bin\mariadb\*\bin\mariadbd.exe",
                r"C:\laragon\bin\mysql\*\bin\mysqld.exe", r"C:\Program Files\MySQL\*\bin\mysqld.exe",
                r"C:\Program Files\MariaDB*\bin\mariadbd.exe", r"C:\Program Files\MariaDB*\bin\mysqld.exe"],
    "ftp": [r"C:\Program Files\FileZilla Server\filezilla-server.exe", r"C:\Program Files\FileZilla Server\FileZilla Server.exe",
            r"C:\xampp\FileZillaFTP\FileZillaServer.exe"],
    "mosquitto": [r"C:\Program Files\mosquitto\mosquitto.exe", r"C:\Program Files (x86)\mosquitto\mosquitto.exe"],
    "docker": [r"C:\Program Files\Docker\Docker\Docker Desktop.exe"],
}

def _ps_json(script, timeout=30):
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                        "[Console]::OutputEncoding=[Text.Encoding]::UTF8; " + script],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=NOWIN, timeout=timeout)
    out = (r.stdout or "").strip()
    if not out:
        return []
    d = json.loads(out)
    return d if isinstance(d, list) else [d]

def _ver(exe, args, pat):
    try:
        r = subprocess.run([exe] + args, capture_output=True, timeout=12, creationflags=NOWIN, stdin=subprocess.DEVNULL)
        txt = (r.stdout or b"").decode("utf-8", "replace") + (r.stderr or b"").decode("utf-8", "replace")
        m = re.search(pat, txt)
        return m.group(1) if m else ""
    except Exception:
        return ""

def _is_chantier(path):
    try:
        return os.path.normcase(os.path.abspath(path)).startswith(os.path.normcase(os.path.abspath(P["bin"])))
    except Exception:
        return False

def detect_existing():
    """Serveurs installés HORS Chantier : {clé: infos}. Lecture seule, ne plante jamais."""
    import glob
    res = {}
    if not IS_WIN:
        return res
    try:
        procs = _ps_json("Get-CimInstance Win32_Process | Where-Object { $_.Name -match "
                         "'^(httpd|mysqld|mariadbd|filezilla-server|filezillaserver|filezilla server|mosquitto|Docker Desktop|com\\.docker\\.backend)\\.exe$' }"
                         " | Select-Object Name,ProcessId,ExecutablePath | ConvertTo-Json -Compress")
    except Exception as e:
        procs = []; log("chantier", f"Détection des processus impossible : {e}")
    try:
        svcs = _ps_json("Get-CimInstance Win32_Service | Where-Object { $_.Name -match '^(apache|httpd|mysql|mariadb|filezilla|mosquitto|com\\.docker)' }"
                        " | Select-Object Name,DisplayName,State,PathName | ConvertTo-Json -Compress")
    except Exception as e:
        svcs = []; log("chantier", f"Détection des services impossible : {e}")
    for key, names in EXIST_PROCS.items():
        info = {"name": EXIST_NAMES[key], "running": False, "exe": "", "root": "", "winsvc": "", "svcstate": "",
                "version": "", "ports": [], "logs": "", "pids": [], "panel": ""}
        for p in procs:
            exe = p.get("ExecutablePath") or ""
            if (p.get("Name") or "").lower() in names and not _is_chantier(exe):
                info["running"] = True; info["pids"].append(p.get("ProcessId"))
                info["exe"] = info["exe"] or exe
        for sv in svcs:
            if re.match(EXIST_SVC[key], sv.get("Name") or "", re.I):
                m = re.match(r'\s*"?([^"]+?\.exe)', sv.get("PathName") or "", re.I)
                if m and _is_chantier(m.group(1)):
                    continue
                info["winsvc"] = sv.get("Name"); info["svcstate"] = sv.get("State") or ""
                if info["svcstate"] == "Running":
                    info["running"] = True
                if m and not info["exe"]:
                    info["exe"] = m.group(1)
        if not info["exe"]:
            for g in EXIST_GLOBS[key]:
                hits = [h for h in glob.glob(g) if not _is_chantier(h)]
                if hits:
                    info["exe"] = sorted(hits)[-1]; break
        if not (info["exe"] or info["running"] or info["winsvc"]):
            continue
        exe = info["exe"]
        if exe:
            d = os.path.dirname(exe)
            info["root"] = os.path.dirname(d) if os.path.basename(d).lower() == "bin" else d
            if key == "apache":
                info["version"] = _ver(exe, ["-v"], r"Apache/([\d.]+)")
                info["logs"] = os.path.join(info["root"], "logs")
            elif key == "mariadb":
                v = _ver(exe, ["--version"], r"Ver\s+([\w.\-]+)")
                if v:
                    info["name"] = "MariaDB" if ("mariadb" in v.lower() or "mariadbd" in exe.lower()) else "MySQL"
                    info["version"] = v.split("-")[0]
                info["logs"] = os.path.join(info["root"], "data")
            elif key == "mosquitto":
                info["version"] = _ver(exe, ["-h"], r"mosquitto version ([\d.]+)")
                info["logs"] = info["root"]
            else:
                info["logs"] = info["root"]
            low = exe.lower()
            if "\\xampp\\" in low and os.path.isfile(r"C:\xampp\xampp-control.exe"):
                info["panel"] = r"C:\xampp\xampp-control.exe"
                if key in ("apache", "mariadb"):
                    info["name"] += " (XAMPP)"
            elif "\\wamp" in low and os.path.isfile(r"C:\wamp64\wampmanager.exe"):
                info["panel"] = r"C:\wamp64\wampmanager.exe"
        info["ports"] = [p for p in EXIST_PORTS[key] if port_busy(p)]
        res[key] = info
    if "apache" in res:
        res["caddy"] = res["apache"]
    php = shutil.which("php")
    if not php:
        for g in (r"C:\xampp\php\php.exe", r"C:\wamp64\bin\php\*\php.exe", r"C:\laragon\bin\php\*\php.exe", r"C:\php\php.exe"):
            h = sorted(glob.glob(g))
            if h:
                php = h[-1]; break
    if php and not _is_chantier(php):
        res["_php"] = {"exe": php, "version": _ver(php, ["-v"], r"PHP ([\d.]+)")}
    try:
        r = subprocess.run(["wsl", "--status"], capture_output=True, timeout=12, creationflags=NOWIN, stdin=subprocess.DEVNULL)
        raw = (r.stdout or b"") + (r.stderr or b"")
        txt = raw.decode("utf-16-le", "replace") if b"\x00" in raw else raw.decode("utf-8", "replace")
        res["_wsl"] = {"ok": r.returncode == 0, "txt": txt.replace("\x00", "").strip()[:400]}
    except Exception:
        res["_wsl"] = {"ok": False, "txt": "wsl introuvable"}
    return res

def existing_summary(ex, managed=None):
    managed = managed or {}
    parts = []
    def one(lbl, k):
        i = ex.get(k)
        if managed.get(k):
            parts.append(f"{lbl} ✔ (Chantier)")
        elif i:
            parts.append(f"{i.get('name', lbl).split(' (')[0]} {i.get('version', '')}".strip() + (" ✔" if i.get("running") else " ✔ (arrêté)"))
        else:
            parts.append(f"{lbl} ✗")
    one("Apache", "apache"); one("MySQL", "mariadb")
    p = ex.get("_php"); parts.append(f"PHP {p['version']} ✔" if p else "PHP ✗")
    one("FTP", "ftp"); one("MQTT", "mosquitto"); one("Docker", "docker")
    w = ex.get("_wsl"); parts.append("WSL ✔" if w and w.get("ok") else "WSL ✗")
    return "Sur ce PC :  " + "   ·   ".join(parts)

# ---------------------------------------------------------------- services
class Service:
    key = ""; name = ""; desc = ""; ports = [0]; winget_id = None; color = "#4cc9f0"
    def __init__(self, app_state):
        self.st = app_state
    # état persistant
    @property
    def s(self):
        return self.st.setdefault(self.key, {})
    def bindir(self):
        return os.path.join(P["bin"], self.key)
    def installed(self):
        return bool(self.s.get("installed"))
    def port(self):
        return int(self.s.get("port") or self.ports[0])
    def running(self):
        pid = self.s.get("pid")
        return bool(pid) and pid_alive(pid)
    def listening(self):
        return self.running() and port_busy(self.port())
    def choose_port(self):
        if not self.s.get("port") or (not self.running() and port_busy(self.port())):
            self.s["port"] = free_port(self.ports)
        return self.port()
    def spawn(self, cmd, cwd=None, env=None, logname=None):
        ensure_dir(P["logs"])
        lf = open(os.path.join(P["logs"], (logname or self.key) + ".out.log"), "a", encoding="utf-8", errors="replace")
        lf.write(f"\n==== {time.ctime()} ====\n"); lf.flush()
        pr = subprocess.Popen(cmd, cwd=cwd or self.bindir(), stdout=lf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                              creationflags=NOWIN, env=env)
        return pr.pid
    # à surcharger
    def install(self, prog): raise NotImplementedError
    def start(self): raise NotImplementedError
    def stop(self):
        for k in ("pid", "pid2"):
            pid = self.s.get(k)
            if pid and pid_alive(pid):
                log(self.key, f"Arrêt du processus {pid} (lancé par Chantier)")
                kill_tree(pid)
            self.s.pop(k, None)
    def uninstall(self):
        self.stop()
        if self.s.get("via") == "winget" and self.winget_id and winget_ok():
            run_logged(["winget", "uninstall", "--id", self.winget_id, "-e", "--silent"], self.key)
        d = self.bindir()
        if os.path.isdir(d):
            shutil.rmtree(d, ignore_errors=True)
            log(self.key, f"Dossier supprimé : {d}")
        port = self.s.get("port")
        self.st[self.key] = {"port": port} if port else {}
        log(self.key, "Désinstallé.")

# ----- PHP (partagé par Apache/Caddy)
def php_dir():
    return os.path.join(P["bin"], "php")

def install_php(prog):
    if os.path.isfile(os.path.join(php_dir(), "php-cgi.exe")):
        log("php", "PHP déjà présent."); return
    rel = http_json("https://windows.php.net/downloads/releases/releases.json")
    best = None
    for ver, info in rel.items():
        for k, v in info.items():
            if isinstance(v, dict) and k.startswith("ts-") and k.endswith("-x64") and "zip" in v:
                key = tuple(int(x) for x in re.findall(r"\d+", info.get("version", ver))[:3])
                if not best or key > best[0]:
                    best = (key, v["zip"]["path"], v["zip"].get("sha256"))
    if not best:
        raise RuntimeError("Aucune version PHP TS x64 trouvée sur windows.php.net")
    zp = os.path.join(P["dl"], best[1])
    download("https://windows.php.net/downloads/releases/" + best[1], zp, "php", prog, best[2])
    unzip(zp, php_dir(), "php")
    write_php_ini()

def write_php_ini():
    d = php_dir()
    src = os.path.join(d, "php.ini-production")
    ini = open(src, encoding="utf-8", errors="replace").read() if os.path.isfile(src) else "[PHP]\n"
    ini = re.sub(r'(?m)^;?\s*extension_dir\s*=\s*"ext"', f'extension_dir = "{fwd(os.path.join(d, "ext"))}"', ini)
    for ext in ("curl", "fileinfo", "gd", "mbstring", "openssl", "pdo_mysql", "mysqli", "zip", "intl"):
        ini = re.sub(rf"(?m)^;\s*extension\s*=\s*{ext}\s*$", f"extension={ext}", ini)
    ini += ("\n; --- Chantier ---\nupload_max_filesize = 32M\npost_max_size = 40M\n"
            f'error_log = "{fwd(os.path.join(P["logs"], "php_errors.log"))}"\ndate.timezone = America/Toronto\n')
    if 'extension_dir = "' not in ini:
        ini += f'extension_dir = "{fwd(os.path.join(d, "ext"))}"\n'
    open(os.path.join(d, "php.ini"), "w", encoding="utf-8").write(ini)
    log("php", "php.ini écrit (pdo_mysql, mbstring, gd, curl, openssl activés).")

class Apache(Service):
    key = "apache"; name = "Apache + PHP"; desc = "Serveur web (Apache Lounge, officiel pour Windows) + PHP"; ports = [80, 8080, 8081, 8088]
    color = "#ff7b54"
    def httpd(self):
        return find_file(self.bindir(), "httpd.exe") if os.path.isdir(self.bindir()) else None
    def install(self, prog):
        html = http_get("https://www.apachelounge.com/download/").decode("utf-8", "replace")
        m = re.findall(r'href="([^"]*httpd-[\d.]+-\d+-[Ww]in64-VS\d+\.zip)"', html)
        if not m:
            raise RuntimeError("Lien Apache Lounge introuvable (page changée ?)")
        url = m[0] if m[0].startswith("http") else "https://www.apachelounge.com" + m[0]
        zp = os.path.join(P["dl"], url.rsplit("/", 1)[-1])
        download(url, zp, self.key, prog)
        unzip(zp, self.bindir(), self.key)
        log(self.key, "Note : Apache Lounge demande le « Visual C++ Redistributable » (installé via winget si absent).")
        if winget_ok():
            run_logged(["winget", "install", "--id", "Microsoft.VCRedist.2015+.x64", "-e", "--silent",
                        "--accept-package-agreements", "--accept-source-agreements"], self.key)
        install_php(prog)
        self.s.update(installed=True, via="zip")
    def write_conf(self):
        httpd = self.httpd(); root = os.path.dirname(os.path.dirname(httpd)); port = self.choose_port()
        mods = ["authz_core", "authz_host", "access_compat", "dir", "mime", "log_config", "alias", "rewrite", "headers",
                "setenvif", "env", "deflate", "expires", "autoindex", "actions"]
        lines = [f'ServerRoot "{fwd(root)}"', f"Listen {port}", f"ServerName localhost:{port}"]
        for m in mods:
            so = os.path.join(root, "modules", f"mod_{m}.so")
            if os.path.isfile(so):
                lines.append(f'LoadModule {m}_module modules/mod_{m}.so')
        phpdll = None
        for n in ("php8apache2_4.dll", "php7apache2_4.dll"):
            c = os.path.join(php_dir(), n)
            if os.path.isfile(c):
                phpdll = c
        if phpdll:
            lines += [f'LoadModule php_module "{fwd(phpdll)}"', f'PHPIniDir "{fwd(php_dir())}"',
                      '<FilesMatch "\\.php$">', "  SetHandler application/x-httpd-php", "</FilesMatch>"]
        lines += [f'DocumentRoot "{fwd(P["www"])}"', f'<Directory "{fwd(P["www"])}">', "  Options Indexes FollowSymLinks",
                  "  AllowOverride All", "  Require all granted", "</Directory>",
                  '<Files ".ht*">', "  Require all denied", "</Files>",
                  "DirectoryIndex index.php index.html index.htm", 'TypesConfig conf/mime.types',
                  f'ErrorLog "{fwd(os.path.join(P["logs"], "apache_error.log"))}"',
                  'LogFormat "%h %l %u %t \\"%r\\" %>s %b" common',
                  f'CustomLog "{fwd(os.path.join(P["logs"], "apache_access.log"))}" common',
                  f'PidFile "{fwd(os.path.join(P["logs"], "httpd.pid"))}"']
        ensure_dir(P["conf"])
        cf = os.path.join(P["conf"], "httpd-chantier.conf")
        open(cf, "w", encoding="utf-8").write("\n".join(lines) + "\n")
        return httpd, root, cf
    def start(self):
        httpd, root, cf = self.write_conf()
        if port_busy(self.port()):
            raise RuntimeError(f"Port {self.port()} déjà utilisé : choisis un autre port.")
        rc = run_logged([httpd, "-t", "-f", cf], self.key, timeout=60)
        if rc != 0:
            raise RuntimeError("Configuration Apache invalide (voir journal).")
        self.s["pid"] = self.spawn([httpd, "-f", cf], cwd=root)
        log(self.key, f"Apache démarré → http://localhost:{self.port()}/")

class Caddy(Service):
    key = "caddy"; name = "Caddy + PHP"; desc = "Serveur web moderne (HTTPS auto) + PHP en FastCGI"; ports = [80, 8080, 8081, 8088]
    winget_id = "CaddyServer.Caddy"; color = "#22d3ee"
    def exe(self):
        c = find_file(self.bindir(), "caddy.exe") if os.path.isdir(self.bindir()) else None
        return c or shutil.which("caddy")
    def install(self, prog):
        try:
            rel = http_json("https://api.github.com/repos/caddyserver/caddy/releases/latest")
            asset = next(a for a in rel["assets"] if re.search(r"windows_amd64\.zip$", a["name"]))
            zp = os.path.join(P["dl"], asset["name"])
            download(asset["browser_download_url"], zp, self.key, prog)
            unzip(zp, self.bindir(), self.key); self.s["via"] = "zip"
        except Exception as e:
            log(self.key, f"Zip GitHub indisponible ({e}) → winget")
            if not winget_ok() or run_logged(["winget", "install", "--id", self.winget_id, "-e", "--silent",
                                              "--accept-package-agreements", "--accept-source-agreements"], self.key) != 0:
                raise
            self.s["via"] = "winget"
        install_php(prog)
        self.s["installed"] = True
    def start(self):
        port = self.choose_port()
        if port_busy(port):
            raise RuntimeError(f"Port {port} déjà utilisé.")
        fport = free_port([9123, 9124, 9125])
        env = dict(os.environ, PHP_FCGI_MAX_REQUESTS="0", PHPRC=php_dir())
        self.s["pid2"] = self.spawn([os.path.join(php_dir(), "php-cgi.exe"), "-b", f"127.0.0.1:{fport}"], cwd=php_dir(), env=env,
                                    logname="php-cgi")
        cf = os.path.join(P["conf"], "Caddyfile"); ensure_dir(P["conf"])
        open(cf, "w", encoding="utf-8").write(
            f':{port} {{\n\troot * "{fwd(P["www"])}"\n\t@prive path */.ht* */*config*.php */*_lib.php\n\trespond @prive 403\n'
            f'\tphp_fastcgi 127.0.0.1:{fport}\n\tfile_server browse\n'
            f'\tlog {{\n\t\toutput file "{fwd(os.path.join(P["logs"], "caddy_access.log"))}"\n\t}}\n}}\n')
        exe = self.exe()
        if not exe:
            raise RuntimeError("caddy.exe introuvable.")
        self.s["pid"] = self.spawn([exe, "run", "--config", cf, "--adapter", "caddyfile"], cwd=P["conf"])
        log(self.key, f"Caddy démarré → http://localhost:{port}/  (PHP FastCGI sur {fport})")

class MariaDB(Service):
    key = "mariadb"; name = "MariaDB (SQL)"; desc = "Base de données compatible MySQL, zip portable officiel"; ports = [3306, 3307, 3308]
    color = "#c084fc"
    def tool(self, *names):
        for n in names:
            c = find_file(self.bindir(), n) if os.path.isdir(self.bindir()) else None
            if c:
                return c
        return None
    def datadir(self):
        return os.path.join(P["data"], "mariadb")
    def install(self, prog):
        found = None
        for series in ("11.8", "11.4", "10.11"):
            try:
                js = http_json(f"https://downloads.mariadb.org/rest-api/mariadb/{series}/latest/")
            except Exception as e:
                log(self.key, f"Série {series} : {e}"); continue
            stack = [js]
            while stack and not found:
                o = stack.pop()
                if isinstance(o, dict):
                    fn = o.get("file_name", "")
                    if fn.endswith("winx64.zip") and "debug" not in fn:
                        found = (fn, o.get("file_download_url"), (o.get("checksum") or {}).get("sha256sum"))
                    stack.extend(o.values())
                elif isinstance(o, list):
                    stack.extend(o)
            if found:
                break
        if not found:
            raise RuntimeError("Zip MariaDB introuvable sur downloads.mariadb.org")
        zp = os.path.join(P["dl"], found[0])
        download(found[1], zp, self.key, prog, found[2])
        unzip(zp, self.bindir(), self.key)
        port = self.choose_port()
        sec = load_secrets()
        sec.setdefault("mariadb_root", gen_password()); save_secrets(sec); load_secrets()
        init = self.tool("mariadb-install-db.exe", "mysql_install_db.exe")
        if os.path.isdir(self.datadir()) and os.listdir(self.datadir()):
            log(self.key, "Données existantes conservées : " + self.datadir())
        else:
            ensure_dir(os.path.dirname(self.datadir()))
            rc = run_logged([init, f"--datadir={self.datadir()}", f"--port={port}", f"--password={sec['mariadb_root']}"], self.key)
            if rc != 0:
                raise RuntimeError("Initialisation MariaDB échouée.")
        ini = os.path.join(self.datadir(), "my.ini")
        txt = open(ini, encoding="utf-8", errors="replace").read() if os.path.isfile(ini) else "[mysqld]\n"
        if "bind-address" not in txt:
            txt = txt.replace("[mysqld]", "[mysqld]\nbind-address=127.0.0.1", 1)
        txt = re.sub(r"(?m)^port=\d+", f"port={port}", txt)
        open(ini, "w", encoding="utf-8").write(txt)
        self.s.update(installed=True, via="zip")
    def start(self):
        port = self.choose_port()
        if port_busy(port):
            raise RuntimeError(f"Port {port} déjà utilisé (un autre MySQL/MariaDB ?).")
        ini = os.path.join(self.datadir(), "my.ini")
        txt = open(ini, encoding="utf-8", errors="replace").read()
        open(ini, "w", encoding="utf-8").write(re.sub(r"(?m)^port=\d+", f"port={port}", txt))
        exe = self.tool("mariadbd.exe", "mysqld.exe")
        self.s["pid"] = self.spawn([exe, f"--defaults-file={ini}", f"--port={port}"])
        log(self.key, f"MariaDB démarré sur 127.0.0.1:{port}")
    def stop(self):
        adm = self.tool("mariadb-admin.exe", "mysqladmin.exe"); sec = load_secrets()
        if adm and self.running() and sec.get("mariadb_root"):
            env = dict(os.environ, MYSQL_PWD=sec["mariadb_root"])
            try:
                run_logged([adm, "-uroot", "-h127.0.0.1", f"-P{self.port()}", "shutdown"], self.key, timeout=60, env=env)
                for _ in range(30):
                    if not self.running():
                        break
                    time.sleep(0.5)
            except Exception as e:
                log(self.key, f"shutdown : {e}")
        super().stop()
    def sql(self, statements):
        cli = self.tool("mariadb.exe", "mysql.exe"); sec = load_secrets()
        env = dict(os.environ, MYSQL_PWD=sec["mariadb_root"])
        return run_logged([cli, "-uroot", "-h127.0.0.1", f"-P{self.port()}"], self.key, env=env, stdin_text=statements, timeout=120)
    def create_app_db(self, db="padawan", user="padawan"):
        sec = load_secrets()
        if not sec.get("sql_user_pass"):
            sec["sql_user_pass"] = gen_password(); save_secrets(sec); load_secrets()
        pw = sec["sql_user_pass"].replace("'", "")
        stmts = (f"CREATE DATABASE IF NOT EXISTS `{db}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;\n"
                 f"CREATE USER IF NOT EXISTS '{user}'@'localhost' IDENTIFIED BY '{pw}';\n"
                 f"CREATE USER IF NOT EXISTS '{user}'@'127.0.0.1' IDENTIFIED BY '{pw}';\n"
                 f"ALTER USER '{user}'@'localhost' IDENTIFIED BY '{pw}';\nALTER USER '{user}'@'127.0.0.1' IDENTIFIED BY '{pw}';\n"
                 f"GRANT ALL PRIVILEGES ON `{db}`.* TO '{user}'@'localhost';\nGRANT ALL PRIVILEGES ON `{db}`.* TO '{user}'@'127.0.0.1';\n"
                 "FLUSH PRIVILEGES;\n")
        rc = self.sql(stmts)
        if rc != 0:
            raise RuntimeError("Création de la base échouée.")
        sec["sql_db"] = db; sec["sql_user"] = user; sec["sql_port"] = str(self.port()); save_secrets(sec)
        log(self.key, f"Base « {db} » et utilisateur « {user} » prêts (mot de passe dans {P['secrets']}).")
    def uninstall(self):
        super().uninstall()
        log(self.key, f"Les données SQL sont gardées : {self.datadir()} (supprime-les à la main si tu veux).")

FTP_SCRIPT = r'''# serveur FTP Chantier (pyftpdlib) — généré, ne pas éditer
import json, sys, logging
from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import FTPServer
cfg = json.load(open(sys.argv[1], encoding="utf-8")); sec = json.load(open(cfg["secrets"], encoding="utf-8"))
logging.basicConfig(level=logging.INFO)
a = DummyAuthorizer(); a.add_user(sec["ftp_user"], sec["ftp_pass"], cfg["root"], perm="elradfmwMT")
h = FTPHandler; h.authorizer = a; h.passive_ports = range(cfg["pasv"], cfg["pasv"] + 20); h.banner = "Chantier FTP pret."
FTPServer((cfg["host"], cfg["port"]), h).serve_forever()
'''

class FTP(Service):
    key = "ftp"; name = "Serveur FTP"; desc = "pyftpdlib portable (racine = FTP_HOME public)"; ports = [21, 2121, 2122]
    winget_id = "TimKosse.FileZilla.Server"; color = "#facc15"
    def install(self, prog):
        py = sys.executable.replace("pythonw.exe", "python.exe")
        try:
            import pyftpdlib  # noqa
            log(self.key, "pyftpdlib déjà présent.")
        except Exception:
            if run_logged([py, "-m", "pip", "install", "--user", "pyftpdlib"], self.key) != 0:
                raise RuntimeError("pip install pyftpdlib a échoué.")
        ensure_dir(self.bindir())
        open(os.path.join(self.bindir(), "ftp_chantier.py"), "w", encoding="utf-8").write(FTP_SCRIPT)
        sec = load_secrets(); sec.setdefault("ftp_user", "padawan"); sec.setdefault("ftp_pass", gen_password(16))
        save_secrets(sec); load_secrets()
        ensure_dir(P["pub"])
        self.choose_port(); self.s.update(installed=True, via="pip")
        log(self.key, f"FTP prêt : utilisateur « {sec['ftp_user']} », racine {P['pub']}")
    def install_filezilla(self):
        if not winget_ok():
            raise RuntimeError("winget absent.")
        rc = run_logged(["winget", "install", "--id", self.winget_id, "-e", "--accept-package-agreements",
                         "--accept-source-agreements"], self.key)
        log(self.key, "FileZilla Server : configure-le avec sa console d'administration (il tourne comme service Windows)."
            if rc == 0 else "FileZilla Server : installation non terminée.")
    def start(self):
        port = self.choose_port()
        if port_busy(port):
            raise RuntimeError(f"Port {port} déjà utilisé.")
        cfg = os.path.join(P["conf"], "ftp_chantier.json"); ensure_dir(P["conf"])
        json.dump({"secrets": P["secrets"], "root": P["pub"], "host": "0.0.0.0", "port": port, "pasv": 50100},
                  open(cfg, "w", encoding="utf-8"))
        py = sys.executable.replace("pythonw.exe", "python.exe")
        self.s["pid"] = self.spawn([py, os.path.join(self.bindir(), "ftp_chantier.py"), cfg])
        log(self.key, f"FTP démarré sur le port {port} (passif 50100-50119).")

class Mosquitto(Service):
    key = "mosquitto"; name = "Mosquitto (MQTT)"; desc = "Courtier MQTT pour NodeMCU / ESP / domotique"; ports = [1883, 1884, 1885]
    winget_id = "EclipseFoundation.Mosquitto"; color = "#4ade80"
    def exe(self):
        for d in (self.bindir(), os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "mosquitto")):
            c = os.path.join(d, "mosquitto.exe")
            if os.path.isfile(c):
                return c
        return None
    def install(self, prog):
        ok = False
        if winget_ok():
            rc = run_logged(["winget", "install", "--id", self.winget_id, "-e", "--silent",
                             "--accept-package-agreements", "--accept-source-agreements"], self.key)
            ok = rc == 0 or bool(self.exe())
            if ok:
                self.s["via"] = "winget"
        if not ok:
            html = http_get("https://mosquitto.org/download/").decode("utf-8", "replace")
            m = re.findall(r'href="([^"]*mosquitto-[\d.]+-install-windows-x64\.exe)"', html)
            if not m:
                raise RuntimeError("Installateur Mosquitto introuvable sur mosquitto.org")
            url = m[0] if m[0].startswith("http") else "https://mosquitto.org" + m[0]
            exe = os.path.join(P["dl"], url.rsplit("/", 1)[-1]); download(url, exe, self.key, prog)
            ensure_dir(self.bindir())
            run_logged([exe, "/S", "/D=" + self.bindir()], self.key)
            self.s["via"] = "installateur"
        if not self.exe():
            raise RuntimeError("mosquitto.exe introuvable après installation.")
        self.s["installed"] = True
    def start(self):
        port = self.choose_port()
        if port_busy(port):
            raise RuntimeError(f"Port {port} déjà utilisé.")
        cf = os.path.join(P["conf"], "mosquitto-chantier.conf"); ensure_dir(P["conf"])
        open(cf, "w", encoding="utf-8").write(
            f"listener {port} 0.0.0.0\nallow_anonymous true\npersistence true\npersistence_location {fwd(P['data'])}/\n"
            f"log_dest file {fwd(os.path.join(P['logs'], 'mosquitto.log'))}\n")
        ensure_dir(P["data"])
        self.s["pid"] = self.spawn([self.exe(), "-c", cf, "-v"], cwd=os.path.dirname(self.exe()))
        log(self.key, f"Mosquitto démarré sur le port {port} (anonyme, réseau local).")
    def uninstall(self):
        if self.s.get("via") == "installateur":
            un = os.path.join(self.bindir(), "Uninstall.exe")
            if os.path.isfile(un):
                run_logged([un, "/S"], self.key)
        super().uninstall()

class Docker(Service):
    key = "docker"; name = "WSL2 + Docker Desktop"; desc = "Conteneurs (wsl --install puis Docker Desktop officiel) — droits admin + redémarrage"
    ports = [0]; winget_id = "Docker.DockerDesktop"; color = "#2496ed"
    DD = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Docker", "Docker", "Docker Desktop.exe")
    def port(self):
        return 0
    def choose_port(self):
        return 0
    def installed(self):
        return os.path.isfile(self.DD) or bool(self.s.get("installed"))
    def wsl_ok(self):
        try:
            r = subprocess.run(["wsl", "--status"], capture_output=True, creationflags=NOWIN, timeout=20)
            return r.returncode == 0
        except Exception:
            return False
    def running(self):
        if not IS_WIN:
            return False
        try:
            out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Docker Desktop.exe", "/FO", "CSV", "/NH"], capture_output=True,
                                 text=True, creationflags=NOWIN, timeout=8).stdout
            return "Docker Desktop.exe" in out
        except Exception:
            return False
    def install(self, prog):
        if not self.wsl_ok():
            log(self.key, "Activation de WSL2 (fenêtre administrateur / UAC) : wsl --install --no-distribution")
            subprocess.run(["powershell", "-NoProfile", "-Command",
                            "Start-Process wsl -ArgumentList '--install','--no-distribution' -Verb RunAs -Wait"],
                           creationflags=NOWIN, timeout=1800)
            log(self.key, "WSL2 : un REDÉMARRAGE de Windows peut être nécessaire avant Docker.")
        else:
            log(self.key, "WSL2 déjà actif.")
        ok = False
        if winget_ok():
            ok = run_logged(["winget", "install", "--id", self.winget_id, "-e", "--accept-package-agreements",
                             "--accept-source-agreements"], self.key, timeout=3600) == 0 or os.path.isfile(self.DD)
            if ok:
                self.s["via"] = "winget"
        if not ok:
            exe = os.path.join(P["dl"], "DockerDesktopInstaller.exe")
            download("https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe", exe, self.key, prog)
            subprocess.run(["powershell", "-NoProfile", "-Command",
                            f"Start-Process '{exe}' -ArgumentList 'install','--quiet','--accept-license','--backend=wsl-2' -Verb RunAs -Wait"],
                           creationflags=NOWIN, timeout=3600)
            self.s["via"] = "installateur"
        if not os.path.isfile(self.DD):
            raise RuntimeError("Docker Desktop introuvable après installation (redémarre puis réessaie).")
        self.s["installed"] = True
        log(self.key, "Docker Desktop installé. Licence : gratuite pour usage perso / petites entreprises (voir docker.com).")
    def start(self):
        subprocess.Popen([self.DD], creationflags=NOWIN); self.s["pid"] = None
        log(self.key, "Docker Desktop démarre (le voyant passe au vert quand il tourne).")
    def stop(self):
        d = shutil.which("docker")
        if d:
            run_logged([d, "desktop", "stop"], self.key, timeout=120)
        if self.running():
            subprocess.run(["taskkill", "/IM", "Docker Desktop.exe", "/F"], capture_output=True, creationflags=NOWIN)
    def uninstall(self):
        self.stop()
        if winget_ok():
            run_logged(["winget", "uninstall", "--id", self.winget_id, "-e"], self.key, timeout=1800)
        self.st[self.key] = {}
        log(self.key, "Docker Desktop désinstallé (WSL2 reste actif : « wsl --uninstall » si tu veux l'enlever).")

# ---------------------------------------------------------------- outils web de la suite (génériques)
WEB_WHITELIST = {
    "messager": ["api.php", "media.php", "index.php", "messager_lib.php"],
    "facteur": ["facteur_boite.php", "facteur_boite_lib.php"],
}
def web_source_dirs():
    return [os.path.join(HERE, "web_sources"), os.path.join(HERE, "app", "web_sources")]

def _find_src(name):
    cands = []
    for d in web_source_dirs():
        cands += [os.path.join(d, name + ".txt"), os.path.join(d, "messager_" + name + ".txt")]
    for c in cands:
        if os.path.isfile(c):
            return c
    return None

def deploy_web_tools(sec, sql_port):
    """Copie les pages Messager/Facteur GÉNÉRIQUES (sans secrets ni page test) sous www, la config sous web_private."""
    host = "127.0.0.1" if int(sql_port) == 3306 else f"127.0.0.1;port={int(sql_port)}"
    priv_root = P["priv_root"]; done = []
    for app, files in WEB_WHITELIST.items():
        dst = os.path.join(P["www"], app); ensure_dir(dst)
        for f in files:
            src = _find_src(f)
            if not src:
                log("web", f"Source manquante : {f}.txt (dans web_sources)"); continue
            txt = open(src, encoding="utf-8", errors="replace").read()
            txt = txt.replace("C:/web_private/", fwd(priv_root) + "/").replace("C:\\\\web_private\\\\", fwd(priv_root) + "/")
            if "facteur_test" in f or "::run" in txt:
                log("web", f"Ignoré (privé) : {f}"); continue
            open(os.path.join(dst, f), "w", encoding="utf-8").write(txt); done.append(f"{app}/{f}")
        open(os.path.join(dst, ".htaccess"), "w", encoding="utf-8").write(
            "Options -Indexes\n<FilesMatch \"(_lib\\.php|config.*|\\.(bak|txt|json|log))$\">\n    Require all denied\n</FilesMatch>\n"
            "SetEnvIf Authorization \"(.*)\" HTTP_AUTHORIZATION=$1\n")
    pw = sec["sql_user_pass"].replace("'", "")
    common = (f"$LOCAL_DB_INCLUDE = '';\n$LOCAL_HOST    = '{host}';\n$LOCAL_DB_USER = '{sec['sql_user']}';\n"
              f"$LOCAL_DB_NAME = '{sec['sql_db']}';\n$LOCAL_DB_PASS = '{pw}';\n")
    md = os.path.join(priv_root, "messager"); ensure_dir(os.path.join(md, "media"))
    open(os.path.join(md, "messager_config.php"), "w", encoding="utf-8").write(
        "<?php\n// Généré par Chantier — HORS racine web.\ndeclare(strict_types=1);\n" + common +
        f"$MSG_MEDIA_DIR    = '{fwd(os.path.join(md, 'media'))}';\n$MSG_MAX_UPLOAD   = 15728640;\n$MSG_RATE_PER_MIN = 120;\n"
        "$MSG_PUBLIC_RETENTION_DAYS = 7;\n// $MSG_ADMIN_HASH = password_hash('...', PASSWORD_DEFAULT);  // bouton admin (optionnel)\n")
    fd = os.path.join(priv_root, "facteur"); ensure_dir(fd)
    open(os.path.join(fd, "facteur_boite_config.php"), "w", encoding="utf-8").write(
        "<?php\n// Généré par Chantier — HORS racine web.\ndeclare(strict_types=1);\n" + common + "$FACTEUR_EXPIRE_SEC = 600;\n")
    open(os.path.join(P["www"], "facteur", "facteur_boite_config.php"), "w", encoding="utf-8").write(
        f"<?php\n// renvoi vers la config privée\nrequire '{fwd(os.path.join(fd, 'facteur_boite_config.php'))}';\n")
    log("web", f"Déployé : {', '.join(done) or 'rien'}")
    log("web", "Facteur : exporte facteur_cle.php depuis Facteur (Boîtes SQL → Exporter) dans " + os.path.join(P["www"], "facteur"))
    log("web", "Messager : dans Messager, mets le serveur http://ton-pc:PORT/messager/ (Paramètres → Serveur privé).")
    return done

PREP_LINKS = [
    ("Rufus (créer la clé USB, version portable)", "https://rufus.ie/fr/"),
    ("Windows 11 — ISO officiel Microsoft", "https://www.microsoft.com/fr-ca/software-download/windows11"),
    ("Support ASUS — pilotes (Intel RST/VMD, Wi-Fi)", "https://www.asus.com/ca-fr/support/download-center/"),
]
PREP_GUIDE = """1. Sauvegarde tes fichiers (et ta clé BitLocker si le chiffrement est actif).
2. Rufus : choisis l'ISO Windows 11 (ou bouton Télécharger), GPT + UEFI (non CSM), clé USB de 8 Go+ (elle sera effacée).
3. DÉMARRER → coche « Supprimer l'exigence d'un compte Microsoft en ligne », compte local, pas de BitLocker auto.
4. Mets les pilotes Intel RST/VMD et Wi-Fi de ton modèle sur la clé (si l'installateur ne voit aucun disque).
5. ASUS : Échap au démarrage = menu de démarrage (F2 = BIOS, désactiver Fast Boot si la clé n'apparaît pas).
6. Sans Internet pendant l'installation : Maj+F10 puis « start ms-cxh:localonly ».
7. Après : installe la suite Padawan, puis Chantier pour les serveurs."""

# ---------------------------------------------------------------- icônes
def make_icons():
    from PIL import Image, ImageDraw
    def draw(sz):
        im = Image.new("RGBA", (sz, sz), (0, 0, 0, 0)); d = ImageDraw.Draw(im); s = sz / 64
        d.rounded_rectangle([2*s, 2*s, 62*s, 62*s], radius=12*s, fill=(14, 30, 60, 255), outline=(250, 204, 21, 255), width=max(1, int(3*s)))
        for i, c in enumerate([(74, 222, 128), (250, 204, 21), (248, 113, 113)]):
            y = (14 + i*14) * s
            d.rounded_rectangle([12*s, y, 52*s, y + 10*s], radius=3*s, fill=(40, 60, 100, 255))
            d.ellipse([44*s, y + 2*s, 50*s, y + 8*s], fill=c + (255,))
        return im
    big = draw(256)
    big.save(os.path.join(HERE, "chantier1_256.png")); draw(64).save(os.path.join(HERE, "chantier1.png"))
    big.save(os.path.join(HERE, "chantier1.ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

# ---------------------------------------------------------------- GUI
THEMES = {
    "moderne": dict(bg="#0b1220", panel="#111c33", card="#16233f", fg="#e6f0ff", dim="#8aa3c7", acc="#facc15", btn="#1e3a66",
                    btnfg="#e6f0ff", logbg="#060b16", logfg="#9fe8ff", font=("Segoe UI", 10), mono=("Consolas", 9), title=("Segoe UI Black", 20)),
    "norton": dict(bg="#0000aa", panel="#0000aa", card="#0000aa", fg="#55ffff", dim="#aaaaaa", acc="#ffff55", btn="#00aaaa",
                   btnfg="#000000", logbg="#000080", logfg="#ffffff", font=("Consolas", 10), mono=("Consolas", 9), title=("Consolas", 18, "bold")),
}
FKEYS = [("F1", "Aide"), ("F2", "Installer"), ("F3", "Démarrer"), ("F4", "Arrêter"), ("F5", "Rafraîch."),
         ("F6", "Ports"), ("F7", "Outils web"), ("F8", "Désinst."), ("F9", "Thème"), ("F10", "Quitter")]

def single_instance():
    if not IS_WIN:
        return True
    try:
        import ctypes
        h = ctypes.windll.kernel32.CreateMutexW(None, False, "Padawan_Chantier1_Mutex")
        globals()["_MUTEX"] = h
        return ctypes.windll.kernel32.GetLastError() != 183
    except Exception:
        return True

def run_gui(test_ms=0):
    import tkinter as tk
    from tkinter import ttk, messagebox
    st = load_state(); load_secrets()
    cfg = st.setdefault("_ui", {"theme": "moderne", "web": "apache"})
    services = {c.key: c(st) for c in (Apache, Caddy, MariaDB, FTP, Mosquitto, Docker)}
    busy = {}
    existing = {}; ex_time = [0.0]; UIQ = queue.Queue(); portbusy = {}

    root = tk.Tk(); root.title(f"Chantier {VERSION} — serveurs à la demande (Projet Padawan)")
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    W, H = min(1080, sw - 40), min(760, sh - 110)
    root.geometry(f"{W}x{H}+{max(0,(sw-W)//2)}+{max(0,min(10,(sh-H)//2))}"); root.minsize(820, 560)
    # Ouvre agrandi (maximise) comme le Gestionnaire de fichiers
    try:
        if os.name == "nt":
            root.state("zoomed")
    except Exception:
        pass
    try:
        root.iconbitmap(os.path.join(HERE, "chantier1.ico"))
    except Exception:
        pass
    T = dict(THEMES.get(cfg.get("theme"), THEMES["moderne"]))
    widgets = []  # (widget, role)

    def reg(w, role):
        widgets.append((w, role)); return w

    def paint():
        for w, role in widgets:
            try:
                if role == "bg": w.configure(bg=T["bg"])
                elif role == "panel": w.configure(bg=T["panel"])
                elif role == "card": w.configure(bg=T["card"], highlightbackground=T["acc"] if cfg["theme"] == "norton" else T["btn"])
                elif role == "lbl": w.configure(bg=T["card"], fg=T["fg"], font=T["font"])
                elif role == "dim": w.configure(bg=T["card"], fg=T["dim"], font=(T["font"][0], 9))
                elif role == "title": w.configure(bg=T["card"], fg=T["acc"], font=(T["font"][0], 12, "bold"))
                elif role == "btn": w.configure(bg=T["btn"], fg=T["btnfg"], activebackground=T["acc"], activeforeground="#000", font=(T["font"][0], 9, "bold"), relief="flat", bd=0, cursor="hand2")
                elif role == "log": w.configure(bg=T["logbg"], fg=T["logfg"], insertbackground=T["fg"], font=T["mono"])
                elif role == "entry": w.configure(bg=T["logbg"], fg=T["fg"], insertbackground=T["fg"], font=T["mono"], relief="flat")
                elif role == "fk": w.configure(bg="#000000" if cfg["theme"] == "norton" else T["panel"])
                elif role == "fknum": w.configure(bg="#000000" if cfg["theme"] == "norton" else T["panel"], fg="#ffffff", font=(T["mono"][0], 9, "bold"))
                elif role == "fktxt": w.configure(bg="#00aaaa" if cfg["theme"] == "norton" else T["btn"], fg="#000000" if cfg["theme"] == "norton" else T["fg"], font=(T["mono"][0], 9))
                elif role == "radio": w.configure(bg=T["card"], fg=T["fg"], selectcolor=T["logbg"], activebackground=T["card"], font=(T["font"][0], 9))
            except Exception:
                pass
        root.configure(bg=T["bg"]); hdr.configure(bg=T["bg"])

    # --- en-tête animé
    hdr = tk.Canvas(root, height=70, highlightthickness=0, bg=T["bg"]); hdr.pack(fill="x")
    phase = [0.0]
    def draw_header():
        hdr.delete("all"); w = hdr.winfo_width() or W; phase[0] += 0.05
        if cfg["theme"] == "norton":
            hdr.create_rectangle(0, 0, w, 70, fill="#0000aa", outline="")
            hdr.create_rectangle(4, 4, w - 4, 66, outline="#55ffff", width=2)
            hdr.create_text(w // 2, 24, text="═══ C H A N T I E R ═══", fill="#ffff55", font=("Consolas", 18, "bold"))
            hdr.create_text(w // 2, 50, text="Serveurs à la demande — rien n'est installé par défaut", fill="#55ffff", font=("Consolas", 10))
        else:
            for i in range(0, w, 24):  # bandes de chantier qui défilent
                x = (i + phase[0] * 40) % (w + 48) - 48
                hdr.create_polygon(x, 70, x + 12, 70, x + 24, 62, x + 12, 62, fill="#facc15", outline="")
            hdr.create_text(22, 26, anchor="w", text="🏗  CHANTIER", fill="#facc15", font=("Segoe UI Black", 20))
            hdr.create_text(24, 50, anchor="w", text="Web · SQL · FTP · MQTT à la demande — pour toi et tes collègues", fill=T["dim"], font=("Segoe UI", 10))
            net = "● Internet OK" if net_state[0] else ("○ Hors ligne" if net_state[0] is False else "… vérification")
            hdr.create_text(w - 20, 26, anchor="e", text=net, fill="#4ade80" if net_state[0] else "#f87171", font=("Segoe UI", 10, "bold"))
            hdr.create_text(w - 20, 48, anchor="e", text=P["www"] + "  |  " + P["priv"], fill=T["dim"], font=("Consolas", 8))
        root.after(60, draw_header)
    net_state = [None]
    threading.Thread(target=lambda: net_state.__setitem__(0, internet_ok()), daemon=True).start()
    summary_var = tk.StringVar(value="Sur ce PC :  détection des serveurs existants…")
    sumlbl = tk.Label(root, textvariable=summary_var, anchor="w", bg="#0b1220", fg="#a7f3d0", font=("Segoe UI", 10, "bold"), padx=12, pady=4)
    sumlbl.pack(fill="x")

    fk = reg(tk.Frame(root), "fk"); fk.pack(fill="x", side="bottom")
    body = reg(tk.Frame(root), "bg"); body.pack(fill="both", expand=True, padx=10, pady=(6, 0))
    left = reg(tk.Frame(body), "bg"); left.pack(side="left", fill="both", expand=True)
    right = reg(tk.Frame(body, width=380), "bg"); right.pack(side="right", fill="both", padx=(10, 0))

    cards = {}; selected = [None]
    def select(key):
        selected[0] = key
        for k, c in cards.items():
            c["frame"].configure(highlightthickness=3 if k == key else 1)

    def card_for(svc, extra=None):
        f = reg(tk.Frame(left, highlightthickness=1, bd=0, padx=10, pady=4), "card"); f.pack(fill="x", pady=3)
        led = tk.Canvas(f, width=26, height=26, highlightthickness=0); led.grid(row=0, column=0, rowspan=2, padx=(0, 10))
        reg(led, "card")
        t = reg(tk.Label(f, text=svc.name, anchor="w"), "title"); t.grid(row=0, column=1, sticky="w")
        d = reg(tk.Label(f, text=svc.desc, anchor="w"), "dim"); d.grid(row=1, column=1, sticky="w")
        d.base = svc.desc
        stl = reg(tk.Label(f, text="", anchor="e"), "dim"); stl.grid(row=0, column=1, sticky="e", padx=8)
        bf = reg(tk.Frame(f), "card"); bf.grid(row=0, column=2, rowspan=2, sticky="e")
        f.grid_columnconfigure(1, weight=1)
        reg(tk.Label(bf, text="Port"), "dim").pack(side="left")
        pv = tk.StringVar(value=str(svc.port()))
        pe = reg(tk.Entry(bf, textvariable=pv, width=6), "entry"); pe.pack(side="left", padx=(2, 8))
        btns = {}
        for lbl, act in (("Installer", "install"), ("▶", "start"), ("■", "stop"), ("🗑", "uninstall")):
            b = reg(tk.Button(bf, text=lbl, padx=8, pady=3, command=lambda a=act, k=svc.key: do(k, a)), "btn")
            b.pack(side="left", padx=2); btns[act] = b
        for w in (f, t, d, stl):
            w.bind("<Button-1>", lambda e, k=svc.key: select(k))
        cards[svc.key] = dict(frame=f, led=led, status=stl, port=pv, btns=btns, title=t, desc=d)
        if extra:
            extra(f)

    def web_extra(f):
        rf = reg(tk.Frame(f), "card"); rf.grid(row=2, column=1, sticky="w", pady=(2, 0))
        reg(tk.Label(rf, text="Moteur web :"), "dim").pack(side="left")
        for v, lbl in (("apache", "Apache"), ("caddy", "Caddy")):
            reg(tk.Radiobutton(rf, text=lbl, value=v, variable=webvar, command=switch_web), "radio").pack(side="left")

    webvar = tk.StringVar(value=cfg.get("web", "apache"))
    def web_svc():
        return services[webvar.get()]
    def switch_web():
        cfg["web"] = webvar.get(); save_state(st); rebuild_web_card()

    web_holder = reg(tk.Frame(left), "bg"); web_holder.pack(fill="x")
    def rebuild_web_card():
        for k in ("apache", "caddy"):
            if k in cards:
                cards[k]["frame"].destroy(); cards.pop(k)
        svc = web_svc()
        card_for(svc, web_extra)
        cards[svc.key]["frame"].pack_forget()
        cards[svc.key]["frame"].pack(in_=web_holder, fill="x", pady=4)
        root.after(10, lambda: (paint(), refresh()))
    for key in ("mariadb", "ftp", "mosquitto", "docker"):
        card_for(services[key])
    rebuild_web_card()

    # outils
    tools = reg(tk.Frame(left, highlightthickness=1, padx=10, pady=8), "card"); tools.pack(fill="x", pady=(8, 4))
    reg(tk.Label(tools, text="Outils web de la suite", anchor="w"), "title").grid(row=0, column=0, sticky="w", columnspan=4)
    reg(tk.Label(tools, text="Pages Messager + Boîte Facteur génériques (sans secret ni page de test), base SQL et utilisateur générés.",
                 anchor="w", wraplength=620, justify="left"), "dim").grid(row=1, column=0, sticky="w", columnspan=4)
    for i, (lbl, cmd) in enumerate((("Créer base + utilisateur SQL", lambda: do("mariadb", "db")),
                                     ("Déployer les outils web", lambda: do("web", "deploy")),
                                     ("Copier mot de passe SQL", lambda: copy_secret("sql_user_pass")),
                                     ("Copier mot de passe FTP", lambda: copy_secret("ftp_pass")))):
        reg(tk.Button(tools, text=lbl, padx=8, pady=4, command=cmd), "btn").grid(row=2, column=i, padx=3, pady=(6, 0), sticky="w")
    for i, (lbl, cmd) in enumerate((("Ouvrir le site", lambda: open_site()), ("Dossier web", lambda: open_dir(P["www"])),
                                     ("Dossier privé", lambda: open_dir(P["priv"])), ("FileZilla Server (winget)", lambda: do("ftp", "filezilla")),
                                     ("Préparer un PC", lambda: prep_pc()))):
        reg(tk.Button(tools, text=lbl, padx=8, pady=4, command=cmd), "btn").grid(row=3, column=i, padx=3, pady=(4, 0), sticky="w")

    # journaux
    reg(tk.Label(right, text="Journaux", anchor="w"), "title").pack(fill="x")
    reg(right, "bg")
    fl = reg(tk.Frame(right), "bg"); fl.pack(fill="x")
    filt = tk.StringVar(value="tout")
    cb = ttk.Combobox(fl, textvariable=filt, values=["tout", "apache", "caddy", "php", "mariadb", "ftp", "mosquitto", "docker", "web", "chantier"],
                      width=12, state="readonly"); cb.pack(side="left", pady=3)
    lines_all = []
    logw = reg(tk.Text(right, wrap="word", height=10, bd=0, padx=8, pady=6), "log"); logw.pack(fill="both", expand=True)
    def rerender(*_):
        logw.configure(state="normal"); logw.delete("1.0", "end")
        for svc, ln in lines_all[-800:]:
            if filt.get() in ("tout", svc):
                logw.insert("end", ln + "\n")
        logw.see("end"); logw.configure(state="disabled")
    cb.bind("<<ComboboxSelected>>", rerender)
    reg(tk.Button(fl, text="Fichier journal", padx=6, command=lambda: open_dir(P["logs"])), "btn").pack(side="right")
    prog = ttk.Progressbar(right, mode="determinate", maximum=1.0); prog.pack(fill="x", pady=(6, 0))

    # barre F1-F10
    for n, lbl in FKEYS:
        cell = reg(tk.Frame(fk), "fk"); cell.pack(side="left", expand=True, fill="x")
        a = reg(tk.Label(cell, text=n.replace("F", "") if cfg["theme"] == "norton" else n), "fknum"); a.pack(side="left")
        b = reg(tk.Label(cell, text=lbl, anchor="w"), "fktxt"); b.pack(side="left", fill="x", expand=True)
        for w in (a, b, cell):
            w.bind("<Button-1>", lambda e, k=n: fkey(k))

    # ---- actions
    def open_dir(d):
        ensure_dir(d)
        try:
            os.startfile(d)
        except Exception as e:
            log("chantier", f"Ouvrir {d} : {e}")
    def open_site():
        s = web_svc(); webbrowser.open(f"http://localhost:{s.port()}/")
    def copy_secret(k):
        v = load_secrets().get(k)
        if not v:
            messagebox.showinfo(APP, "Pas encore généré.", parent=root); return
        root.clipboard_clear(); root.clipboard_append(v)
        log("chantier", f"Mot de passe copié dans le presse-papiers (stocké dans {P['secrets']}).")

    def prep_pc():
        w = tk.Toplevel(root); w.title("Préparer un PC — liens officiels"); w.configure(bg=T["panel"]); w.transient(root)
        tk.Label(w, text="Préparer un PC (réinstaller Windows 11)", bg=T["panel"], fg=T["acc"], font=(T["font"][0], 12, "bold")).pack(anchor="w", padx=14, pady=(10, 4))
        for lbl, url in PREP_LINKS:
            l = tk.Label(w, text="→ " + lbl, bg=T["panel"], fg=T["fg"], cursor="hand2", font=(T["font"][0], 10, "underline"))
            l.pack(anchor="w", padx=18); l.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))
        tk.Label(w, text=PREP_GUIDE, bg=T["panel"], fg=T["fg"], justify="left", wraplength=640, font=(T["font"][0], 9)).pack(anchor="w", padx=14, pady=10)
        tk.Button(w, text="Fermer", command=w.destroy, bg=T["btn"], fg=T["btnfg"], relief="flat", padx=10).pack(pady=(0, 10))

    def set_prog(v):
        UIQ.put(lambda: prog.configure(value=v))  # jamais d'appel Tk hors du fil principal

    def ex_of(key):
        if key not in services or status_cache.get(key, (False,))[0]:
            return None
        return existing.get(key)

    def details(key):
        ex = existing.get(key) or {}
        w = tk.Toplevel(root); w.title(f"{ex.get('name', key)} - déjà installé sur ce PC"); w.configure(bg=T["panel"]); w.transient(root)
        tk.Label(w, text=f"✔ {ex.get('name', key)} {ex.get('version', '')} - déjà installé (existant)", bg=T["panel"], fg="#4ade80",
                 font=(T["font"][0], 12, "bold")).pack(anchor="w", padx=14, pady=(10, 4))
        rows = [("État", "● en marche" if ex.get("running") else "● arrêté"), ("Programme", ex.get("exe") or "-"),
                ("Dossier", ex.get("root") or "-"), ("Ports", ", ".join(map(str, ex.get("ports") or [])) or "-"),
                ("Service Windows", (ex.get("winsvc") + " (" + ex.get("svcstate", "") + ")") if ex.get("winsvc") else "non (lancé par un panneau ou à la main)"),
                ("Journaux", ex.get("logs") or "-")]
        if key in ("apache", "caddy") and existing.get("_php"):
            rows.append(("PHP", f"{existing['_php']['version']}  ({existing['_php']['exe']})"))
        for a, b2 in rows:
            tk.Label(w, text=f"{a:<16} {b2}", bg=T["panel"], fg=T["fg"], font=T["mono"], anchor="w", justify="left").pack(anchor="w", padx=18)
        tk.Label(w, text="Chantier ne désinstalle et n'arrête jamais un serveur existant.", bg=T["panel"], fg=T["dim"],
                 font=(T["font"][0], 9, "italic")).pack(anchor="w", padx=14, pady=(8, 2))
        bf = tk.Frame(w, bg=T["panel"]); bf.pack(pady=10, padx=12, fill="x")
        def b(lbl, cmd):
            tk.Button(bf, text=lbl, command=cmd, bg=T["btn"], fg=T["btnfg"], relief="flat", padx=10, pady=3).pack(side="left", padx=3)
        if ex.get("root"):
            b("Ouvrir le dossier", lambda: open_dir(ex["root"]))
        if key in ("apache", "caddy"):
            prt = 80 if 80 in (ex.get("ports") or []) else ((ex.get("ports") or [80])[0])
            b("Ouvrir http://localhost" + ("" if prt == 80 else f":{prt}"), lambda: webbrowser.open(f"http://localhost:{prt}/"))
        if ex.get("logs") and os.path.isdir(ex["logs"]):
            b("Journaux", lambda: open_dir(ex["logs"]))
        if ex.get("panel"):
            b("Panneau " + ("XAMPP" if "xampp" in ex["panel"].lower() else "WAMP"), lambda: os.startfile(ex["panel"]))
        b("Fermer", w.destroy)
        w.bind("<Escape>", lambda e: w.destroy())

    def existing_ctl(key, act):
        ex = existing.get(key) or {}
        verbe = "Démarrer" if act == "start" else "Arrêter"
        if not ex.get("winsvc"):
            msg = (f"{ex.get('name', key)} est déjà installé sur ce PC, hors Chantier.\n"
                   "Ce n'est pas un service Windows : Chantier n'y touche pas.")
            if ex.get("panel"):
                if messagebox.askyesno(APP, msg + "\n\nOuvrir son panneau de contrôle ?", parent=root):
                    os.startfile(ex["panel"])
            else:
                messagebox.showinfo(APP, msg, parent=root)
            return
        if not messagebox.askyesno(APP, f"{verbe} le service Windows existant « {ex['winsvc']} » ?\n\n"
                                        "Windows va demander l'autorisation administrateur.\nRien d'autre ne sera modifié.",
                                   icon="warning", parent=root):
            return
        try:
            import ctypes
            ctypes.windll.shell32.ShellExecuteW(None, "runas", "sc.exe", f'{"start" if act == "start" else "stop"} "{ex["winsvc"]}"', None, 0)
            log(key, f"{verbe} le service existant {ex['winsvc']} (confirmé par toi).")
        except Exception as e:
            log(key, f"✖ {e}")
        root.after(4000, lambda: refresh(True))

    def do(key, act):
        if busy.get(key):
            return
        if ex_of(key):
            if act == "install":
                details(key); return
            if act == "uninstall":
                messagebox.showinfo(APP, "Ce serveur existait déjà avant Chantier :\nChantier ne le désinstalle jamais.", parent=root); return
            if act in ("start", "stop"):
                existing_ctl(key, act); return
        if act in ("install", "uninstall") and key in services:
            svc = services[key]
            q = (f"Installer {svc.name} ?\n\nTéléchargement depuis la source officielle, installation dans\n{P['bin']}\n"
                 "Aucun port déjà utilisé ne sera touché.") if act == "install" else \
                f"Désinstaller {svc.name} ?\n(Les données SQL et tes pages web sont gardées.)"
            if not messagebox.askyesno(APP, q, parent=root):
                return
        if key in services:
            pv = cards.get(key, {}).get("port")
            if pv:
                try:
                    p = int(pv.get())
                    if p != services[key].port() and not services[key].running():
                        services[key].s["port"] = p
                except ValueError:
                    pass
        busy[key] = True; set_prog(0)
        def work():
            try:
                svc = services.get(key)
                if act == "install":
                    if not internet_ok():
                        raise RuntimeError("Pas d'Internet : installation impossible pour l'instant (rien n'a été modifié).")
                    ensure_dir(P["bin"]); ensure_dir(P["dl"]); svc.install(set_prog); svc.choose_port()
                    log(key, f"✔ Installé (port proposé : {svc.port()})")
                elif act == "start":
                    if not svc.installed():
                        raise RuntimeError("Pas encore installé.")
                    if svc.running():
                        log(key, "Déjà en marche."); return
                    svc.start()
                elif act == "stop":
                    svc.stop(); log(key, "Arrêté.")
                elif act == "uninstall":
                    svc.uninstall()
                elif act == "db":
                    if not svc.running():
                        raise RuntimeError("Démarre MariaDB d'abord.")
                    svc.create_app_db()
                elif act == "deploy":
                    sec = load_secrets()
                    if not sec.get("sql_user_pass"):
                        raise RuntimeError("Crée d'abord la base + l'utilisateur SQL (MariaDB).")
                    deploy_web_tools(sec, sec.get("sql_port") or 3306)
                elif act == "filezilla":
                    svc.install_filezilla()
                save_state(st)
            except Exception as e:
                log(key, f"✖ {e}")
                if os.environ.get("CHANTIER_DEBUG"):
                    log(key, traceback.format_exc())
            finally:
                busy[key] = False; set_prog(1.0); save_state(st)
                UIQ.put(refresh)
        threading.Thread(target=work, daemon=True).start()

    status_cache = {}
    probing = [False]
    def refresh(force=False):
        if probing[0]:
            return
        probing[0] = True
        def probe():
            try:
                if force or time.time() - ex_time[0] > 60:
                    try:
                        ex = detect_existing()
                        existing.clear(); existing.update(ex); ex_time[0] = time.time()
                    except Exception as e:
                        log("chantier", f"Détection : {e}")
                res = {}
                for k, sv in services.items():
                    try:
                        inst, run, port = sv.installed(), sv.running(), sv.port()
                        res[k] = (inst, run, port); portbusy[k] = bool(inst and not run and port and port_busy(port))
                    except Exception:
                        res[k] = (False, False, 0)
                status_cache.update(res)
            finally:
                probing[0] = False
                UIQ.put(apply_status)
        threading.Thread(target=probe, daemon=True).start()
    def apply_status():
        managed = {k: v[0] for k, v in status_cache.items()}
        managed["apache"] = managed.get("apache") or managed.get("caddy")
        summary_var.set(existing_summary(existing, managed) if ex_time[0] else "Sur ce PC :  détection des serveurs existants…")
        for k, c in cards.items():
            inst, run, port = status_cache.get(k, (False, False, 0))
            ex = None if inst else existing.get(k)
            if busy.get(k):
                txt = "⏳ travail en cours…"
            elif ex:
                txt = ("✔ Déjà installé" + (f" · v{ex['version']}" if ex.get("version") else "")
                       + (" · ● en marche" if ex.get("running") else " · ● arrêté"))
            else:
                txt = ("● EN MARCHE (géré par Chantier)" if run else ("■ arrêté (géré par Chantier)" if inst else "non installé")) + (f" - port {port}" if inst and port else "")
                if portbusy.get(k):
                    txt += "  ⚠ port occupé par un autre programme"
            c["status"].configure(text=txt)
            try:
                c["status"].configure(fg="#4ade80" if ((ex and ex.get("running")) or run) else ("#f87171" if ex else T["dim"]))
            except Exception:
                pass
            c["btns"]["install"].configure(text="Détails" if ex else "Installer")
            c["btns"]["uninstall"].configure(state="disabled" if ex else "normal")
            c["desc"].configure(text=(f"📁 {ex.get('root') or ex.get('exe') or ''}" + (f"  ·  port {', '.join(map(str, ex['ports']))}" if ex.get("ports") else "") + f"  ·  existant{' (XAMPP)' if 'xampp' in (ex.get('exe') or '').lower() else ''}, non géré par Chantier" if ex else c["desc"].base))
            if not run:
                c["port"].set(str(port) if port else "-")
    def auto_refresh():
        refresh(); root.after(5000, auto_refresh)

    def anim_leds():
        t = time.time()
        for k, c in cards.items():
            inst, run, _ = status_cache.get(k, (False, False, 0))
            ex = None if inst else existing.get(k)
            if ex:
                inst, run = True, bool(ex.get("running"))
            cv = c["led"]; cv.delete("all")
            if busy.get(k):
                a = (t * 4) % (2 * math.pi)
                cv.create_arc(3, 3, 23, 23, start=math.degrees(a), extent=270, style="arc", outline="#facc15", width=3)
                continue
            if run:
                g = int(160 + 95 * (0.5 + 0.5 * math.sin(t * 3)))
                col = f"#{30:02x}{g:02x}{80:02x}"
                cv.create_oval(1, 1, 25, 25, fill="", outline=col, width=2)
                cv.create_oval(6, 6, 20, 20, fill=col, outline="")
            elif inst:
                cv.create_oval(6, 6, 20, 20, fill="#dc2626", outline="#7f1d1d", width=2)
            else:
                cv.create_oval(6, 6, 20, 20, fill="", outline=T["dim"], width=2)
        root.after(80, anim_leds)

    def pump_logs():
        n = 0
        try:
            while n < 200:
                svc, ln = LOGQ.get_nowait(); lines_all.append((svc, ln)); n += 1
                if len(lines_all) > 5000:
                    del lines_all[:1000]
                if filt.get() in ("tout", svc):
                    logw.configure(state="normal"); logw.insert("end", ln + "\n"); logw.see("end"); logw.configure(state="disabled")
        except queue.Empty:
            pass
        try:
            while True:
                UIQ.get_nowait()()
        except queue.Empty:
            pass
        except Exception as e:
            log("chantier", f"UI : {e}")
        root.after(150, pump_logs)

    def toggle_theme():
        cfg["theme"] = "norton" if cfg["theme"] == "moderne" else "moderne"
        T.clear(); T.update(THEMES[cfg["theme"]]); save_state(st); paint()
        for w, role in widgets:
            if role == "fknum":
                try:
                    w.configure(text=w.cget("text").replace("F", "") if cfg["theme"] == "norton" else ("F" + w.cget("text").lstrip("F")))
                except Exception:
                    pass

    def ports_dialog():
        lines = []
        for p in (21, 80, 443, 1883, 2121, 3306, 3307, 8080, 9123):
            lines.append(f"{p:>5} : {'OCCUPÉ' if port_busy(p) else 'libre'}")
        messagebox.showinfo(APP + " — ports", "\n".join(lines) + "\n\nChantier ne touche jamais un port occupé :\nil choisit un port libre (ex. 8080, 3307).", parent=root)

    def help_dialog():
        messagebox.showinfo(APP + " — aide",
            "Rien n'est installé par défaut : choisis un service puis « Installer ».\n\n"
            "F1 Aide · F2 Installer · F3 Démarrer · F4 Arrêter · F5 Rafraîchir · F6 Ports\n"
            "F7 Déployer les outils web · F8 Désinstaller · F9 Thème Norton · F10 Quitter\n"
            "↑/↓ choisir le service.\n\n"
            f"Pages : {P['www']}\nPublic FTP : {P['pub']}\nPrivé (config, mots de passe, journaux) : {P['priv']}\n\n"
            "Voir LISEZMOI-CHANTIER.txt.", parent=root)

    def cur():
        return selected[0] or "mariadb"
    def fkey(k):
        acts = {"F1": help_dialog, "F2": lambda: do(cur(), "install"), "F3": lambda: do(cur(), "start"),
                "F4": lambda: do(cur(), "stop"), "F5": lambda: refresh(True), "F6": ports_dialog, "F7": lambda: do("web", "deploy"),
                "F8": lambda: do(cur(), "uninstall"), "F9": toggle_theme, "F10": root.destroy}
        acts[k]()
    for n, _ in FKEYS:
        root.bind(f"<{n}>", lambda e, k=n: (fkey(k), "break")[1])
    order = lambda: [webvar.get(), "mariadb", "ftp", "mosquitto", "docker"]
    def move(d):
        o = order(); i = o.index(cur()) if cur() in o else 0; select(o[(i + d) % len(o)])
    root.bind("<Down>", lambda e: move(1)); root.bind("<Up>", lambda e: move(-1))

    log("chantier", f"Chantier {VERSION} prêt. Rien n'est installé par défaut.")
    log("chantier", f"Web : {P['www']}  |  Privé : {P['priv']}")
    busy_ports = [str(p) for p in (80, 443, 3306, 21, 1883) if port_busy(p)]
    if busy_ports:
        log("chantier", "Ports déjà utilisés par d'autres serveurs (on n'y touche pas) : " + ", ".join(busy_ports))
    paint(); select(webvar.get()); draw_header(); anim_leds(); pump_logs(); auto_refresh()
    if test_ms:
        root.after(test_ms, root.destroy)
    root.mainloop()

def selftest():
    print("Chantier selftest")
    print("chemins:", json.dumps(P, indent=1))
    for p in (80, 443, 3306, 21, 1883, 8080):
        print("port", p, "occupé" if port_busy(p) else "libre")
    print("internet:", internet_ok(), "winget:", winget_ok())
    st = {}
    for c in (Apache, Caddy, MariaDB, FTP, Mosquitto, Docker):
        s = c(st); print(c.key, "installé:", s.installed(), "port proposé:", free_port(c.ports))
    _SECRETS_CACHE["t"] = "motdepasse-secret-xyz"
    assert "motdepasse-secret-xyz" not in mask("pw=motdepasse-secret-xyz"); print("masquage OK")
    ex = detect_existing()
    print(existing_summary(ex))
    for k, v in ex.items():
        print(" ", k, json.dumps(v, ensure_ascii=False))
    print("sources web:", [f for f in sum(WEB_WHITELIST.values(), []) if _find_src(f)])
    print("OK")

if __name__ == "__main__":
    a = sys.argv[1:]
    if "--make-icons" in a:
        make_icons(); sys.exit(0)
    if "--selftest" in a:
        selftest(); sys.exit(0)
    if not single_instance():
        sys.exit(0)
    ms = int(a[a.index("--test-gui") + 1]) if "--test-gui" in a else 0
    try:
        run_gui(ms)
    except Exception:
        try:
            ensure_dir(P["logs"])
            open(os.path.join(P["logs"], "chantier_crash.log"), "a", encoding="utf-8").write(traceback.format_exc())
        except Exception:
            pass
        raise
