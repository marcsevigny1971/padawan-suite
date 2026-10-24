# -*- coding: utf-8 -*-
"""
Rétro 1 — Projet Padawan : le coin du vieux nostalgique.
Lanceur C64 (VICE), DOS (DOSBox-X) et Windows 98 (86Box), installés À LA DEMANDE depuis les sources officielles.
Bibliothèque (glisser-déposer .d64/.prg/.t64/.crt/.tap/.exe/.com/.bat/.img/.ima/.iso), pochettes, lancement en un clic,
écran « READY. » animé, thèmes C64 / DOS / Norton. Aucun ROM, jeu ni système protégé n'est inclus.
Options : --make-icons  --selftest  --test-gui MS
"""
import os, sys, re, json, time, math, shutil, socket, zipfile, threading, queue, subprocess, webbrowser, traceback, hashlib
import urllib.request

APP = "Rétro"; VERSION = "1.4"
HERE = os.path.dirname(os.path.abspath(__file__))
IS_WIN = os.name == "nt"
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0) if IS_WIN else 0
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Retro-Padawan/1.0"

def _base():
    if os.path.isdir(r"C:\web"):
        priv = r"C:\web_private\retro"
    else:
        priv = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "Padawan", "Retro")
    data = os.path.join(os.path.expanduser("~"), "Documents", "Padawan", "Retro")
    jeux = os.path.join(priv, "jeux") if os.path.isdir(r"C:\web") else os.path.join(data, "Mes jeux")
    return {"emu": os.path.join(priv, "emulateurs"), "dl": os.path.join(priv, "telechargements"), "logs": os.path.join(priv, "logs"),
            "data": data, "lib": os.path.join(data, "bibliotheque.json"), "covers": os.path.join(data, "pochettes"),
            "vms": os.path.join(data, "machines_win98"), "jeux": jeux, "pack": os.path.join(jeux, "pack_demarrage"),
            "saves": os.path.join(data, "sauvegardes"), "atelier": os.path.join(priv, "atelier"),
            "listings": os.path.join(priv, "listings"), "etats": os.path.join(priv, "sauvegardes_parties")}
P = _base()

def ensure_dir(d):
    try:
        os.makedirs(d, exist_ok=True); return True
    except Exception:
        return False

LOGQ = queue.Queue(); UIQ = queue.Queue()
def ui(fn):
    """Exécute fn dans le thread de l'interface (seul thread autorisé à toucher Tk)."""
    UIQ.put(fn)
def log(msg):
    line = time.strftime("%H:%M:%S ") + str(msg); LOGQ.put(line)
    if ensure_dir(P["logs"]):
        try:
            open(os.path.join(P["logs"], "retro.log"), "a", encoding="utf-8").write(time.strftime("%Y-%m-%d ") + line + "\n")
        except Exception:
            pass

def internet_ok():
    try:
        with socket.create_connection(("1.1.1.1", 443), timeout=2.5):
            return True
    except Exception:
        return False

def http_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode("utf-8", "replace"))

def download(url, dest, progress=None):
    ensure_dir(os.path.dirname(dest)); log(f"Téléchargement : {url}")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r, open(dest + ".part", "wb") as f:
        total = int(r.headers.get("Content-Length") or 0); done = 0
        while True:
            b = r.read(256 * 1024)
            if not b:
                break
            f.write(b); done += len(b)
            if progress and total:
                progress(done / total)
    os.replace(dest + ".part", dest); log(f"Reçu {os.path.basename(dest)} ({os.path.getsize(dest)//1024} Ko)")

def find_file(root, *names):
    if not os.path.isdir(root):
        return None
    low = [n.lower() for n in names]
    for n in low:
        hits = []
        for dp, dn, fn in os.walk(root):
            for f in fn:
                if f.lower() == n:
                    hits.append(os.path.join(dp, f))
        if hits:
            return sorted(hits, key=lambda h: (("sdl" in h.lower()) or ("arm" in h.lower()), h.count(os.sep), len(h)))[0]
    return None

# ---------------------------------------------------------------- émulateurs
EMUS = {
    "c64": dict(nom="Commodore 64", emu="VICE", repo="VICE-Team/svn-mirror", asset=r"GTK3VICE-.*-win64.*\.zip$",
                exe=("x64sc.exe", "x64.exe"), site="https://vice-emu.sourceforge.io/", col="#7869c4",
                ext=(".d64", ".d71", ".d81", ".g64", ".prg", ".t64", ".tap", ".crt", ".p00")),
    "dos": dict(nom="MS-DOS", emu="DOSBox-X", repo="joncampbell123/dosbox-x", asset=r"dosbox-x-vsbuild-win64-.*\.zip$",
                exe=("dosbox-x.exe",), site="https://dosbox-x.com/", col="#aaaaaa", winget="joncampbell123.DOSBox-X",
                ext=(".exe", ".com", ".bat", ".img", ".ima", ".vhd", ".iso", ".cue", ".zip", ".bas")),
    "win98": dict(nom="Windows 98", emu="86Box", repo="86Box/86Box", asset=r"86Box-Windows-64-.*\.zip$",
                  exe=("86Box.exe",), site="https://86box.net/", col="#008080",
                  roms="https://86box.readthedocs.io/en/latest/usage/roms.html", ext=(".86box", ".cfg")),
}
def emu_dir(k):
    return os.path.join(P["emu"], k)
CUSTOM_EXE = {}; _EXE_CACHE = {}
def emu_exe_reset():
    _EXE_CACHE.clear()
def emu_exe(k):
    if CUSTOM_EXE.get(k) and os.path.isfile(CUSTOM_EXE[k]):
        return CUSTOM_EXE[k]
    c = _EXE_CACHE.get(k)
    if c and os.path.isfile(c):
        return c
    c = _emu_exe_find(k)
    if c:
        _EXE_CACHE[k] = c
    return c
def _emu_exe_find(k):
    e = EMUS[k]; c = find_file(emu_dir(k), *e["exe"])
    if not c and k == "dos":
        for d in (os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "DOSBox-X"),
                  os.path.join(os.environ.get("LOCALAPPDATA", ""), "DOSBox-X")):
            c = find_file(d, *e["exe"])
            if c:
                break
    return c

def install_emu(k, progress=None):
    e = EMUS[k]
    if not internet_ok():
        raise RuntimeError("Pas d'Internet : installation reportée (rien n'a été modifié).")
    try:
        rel = http_json(f"https://api.github.com/repos/{e['repo']}/releases/latest")
        assets = [a for a in rel.get("assets", []) if re.search(e["asset"], a["name"], re.I)]
        if not assets and k == "c64":  # VICE : dernière release contenant le zip win64
            for r in http_json(f"https://api.github.com/repos/{e['repo']}/releases?per_page=10"):
                assets = [a for a in r.get("assets", []) if re.search(e["asset"], a["name"], re.I)]
                if assets:
                    break
        if not assets:
            raise RuntimeError("archive Windows introuvable dans la dernière version")
        a = sorted(assets, key=lambda a: ("sdl" in a["name"].lower(), a["name"]))[0]
        zp = os.path.join(P["dl"], a["name"]); download(a["browser_download_url"], zp, progress)
        log(f"Extraction de {e['emu']}…"); ensure_dir(emu_dir(k))
        with zipfile.ZipFile(zp) as z:
            z.extractall(emu_dir(k))
    except Exception as ex:
        if e.get("winget") and shutil.which("winget"):
            log(f"{e['emu']} : zip indisponible ({ex}) → winget")
            subprocess.run(["winget", "install", "--id", e["winget"], "-e", "--silent", "--accept-package-agreements",
                            "--accept-source-agreements"], creationflags=NOWIN, capture_output=True, timeout=900)
        else:
            raise RuntimeError(f"{ex}. Page officielle : {e['site']}")
    emu_exe_reset()
    if not emu_exe(k):
        raise RuntimeError(f"{e['emu']} : exécutable introuvable après installation.")
    log(f"✔ {e['emu']} installé : {emu_exe(k)}")
    if k == "win98":
        log("86Box a besoin de ROMs de BIOS que tu fournis toi-même : voir le lien « ROMs 86Box » (documentation officielle).")

def guess_system(path):
    if os.path.isdir(path):
        return "win98" if any(f.lower().endswith(".cfg") for f in os.listdir(path)) else "dos"
    ext = os.path.splitext(path)[1].lower()
    for k in ("c64", "dos", "win98"):
        if ext in EMUS[k]["ext"]:
            return k
    return None

OPTS = {"fullscreen": True, "crt": False, "pad": True}
def vice_cfg():
    """Config VICE de Rétro : la croix ferme sans confirmation, F12 = plein écran on/off (en plus d'Alt+D)."""
    try:
        x = emu_exe("c64")
        if not x: return None
        d = os.path.dirname(os.path.dirname(os.path.dirname(x))); v = os.path.join(d, "retro-hotkeys.vhk"); c = os.path.join(d, "retro-vice.ini")
        if not os.path.exists(v):
            open(v, "w").write("# Retro : touches VICE normales + F12 = plein ecran\n!include hotkeys.vhk\nfullscreen-toggle F12\n")
        if not os.path.exists(c):
            open(c, "w").write('[C64SC]\nHotkeyFile="%s"\nConfirmOnExit=0\n' % v.replace("\\", "\\\\"))
        return c
    except Exception:
        return None

# ---- émulateurs lancés par Rétro : une seule instance, fermeture propre (WM_CLOSE = comme la croix)
RUNNING = []   # [(Popen, sys, titre)]
def running():
    RUNNING[:] = [r for r in RUNNING if r[0].poll() is None]
    return RUNNING
def _wins(pid):
    import ctypes
    from ctypes import wintypes
    u = ctypes.windll.user32; out = []
    CB = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(h, l):
        q = wintypes.DWORD(); u.GetWindowThreadProcessId(h, ctypes.byref(q))
        if q.value == pid and u.IsWindowVisible(h): out.append(h)
        return True
    u.EnumWindows(CB(cb), 0)
    return out
def unpin(pid):
    """Enlève le « toujours au-dessus » sans prendre le focus."""
    try:
        import ctypes
        u = ctypes.windll.user32
        for h in _wins(pid):
            if u.GetWindowLongW(h, -20) & 0x8:   # WS_EX_TOPMOST
                u.SetWindowPos(h, -2, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)  # HWND_NOTOPMOST, NOSIZE|NOMOVE|NOACTIVATE
    except Exception:
        pass
def close_emus(timeout=10):
    """Ferme proprement (comme la croix) : VICE écrit la disquette, DOSBox-X ses fichiers. Renvoie les titres encore ouverts."""
    import ctypes
    lst = list(running())
    for pr, k, t in lst:
        for h in _wins(pr.pid):
            ctypes.windll.user32.PostMessageW(h, 0x10, 0, 0)   # WM_CLOSE
    end = time.time() + timeout
    while time.time() < end and any(pr.poll() is None for pr, k, t in lst):
        time.sleep(0.2)
    return [t for pr, k, t in lst if pr.poll() is None]
def kill_emus():
    for pr, k, t in running():
        try: pr.kill()
        except Exception: pass

def emu_opts(k):
    o = []
    if k == "c64":
        o += ["+confirmonexit"]
        vc = vice_cfg()
        if vc: o += ["-config", vc]
        if OPTS.get("fullscreen"): o += ["-VICIIfull"]
        if OPTS.get("crt"): o += ["-VICIIfilter", "1"]
        if OPTS.get("pad"): o += [f"-joydev{OPTS.get('joyport', 2)}", "4"]  # manette Xbox/USB sur le port 2 (ou 1)
    elif k == "dos":
        o += ["-set", "dosbox quit warning=false", "-set", f"dos keyboardlayout={OPTS.get('clavier') or 'cf'}"]  # 1.4 : clavier canadien français (la détection auto « ca » échouait)
        cap = os.path.join(os.path.expanduser("~"), "Pictures", "Retro captures"); ensure_dir(cap)
        o += ["-set", f"dosbox captures={cap}", "-set", "dos lfn=true"]  # noms longs : Free Pascal / DJGPP
        if OPTS.get("fullscreen"): o += ["-fullscreen"]
        if OPTS.get("crt"): o += ["-set", "render scaler=tv2x forced"]
        if OPTS.get("pad"): o += ["-set", "joystick joysticktype=auto", "-set", "joystick timed=false"]
    return o

def open_cmd(k):
    """Lance l'émulateur VIDE : C64 READY., invite DOS Z:\\>, gestionnaire de machines 86Box."""
    exe = emu_exe(k)
    if not exe:
        raise RuntimeError(f"{EMUS[k]['emu']} n'est pas installé.\nClique « Installer » à côté de {EMUS[k]['nom']} (source officielle : {EMUS[k]['site']}).")
    if k == "dos":
        return [exe, "-fastlaunch"] + emu_opts(k), os.path.dirname(exe)
    if k == "win98":
        return [exe], os.path.dirname(exe)  # gestionnaire de machines : fenêtre normale ; -F s'applique aux machines
    return [exe] + emu_opts(k), os.path.dirname(exe)

def launch_cmd(item):
    k = item["sys"]; exe = emu_exe(k); p = item["path"]
    if not exe:
        raise RuntimeError(f"{EMUS[k]['emu']} n'est pas installé.\nClique « Installer » à côté de {EMUS[k]['nom']}.")
    if not os.path.exists(p):
        raise RuntimeError(f"Fichier introuvable :\n{p}\n\nIl a été déplacé ou supprimé. Retire-le de la bibliothèque ou relance « Scanner Mes jeux ».")
    xa = item.get("args", "").split() if item.get("args") else []
    if k == "c64":
        return [exe] + emu_opts(k) + xa + ["-autostart", p], os.path.dirname(exe)
    if k == "dos":
        exe = [exe, "-fastlaunch"] + emu_opts(k) + xa
        p = dos_path(p); ext = os.path.splitext(p)[1].lower(); d = os.path.dirname(p)
        if ext in (".img", ".ima"):
            return exe + ["-c", f'imgmount a "{p}" -t floppy', "-c", f'mount c "{d}"', "-c", "a:", "-c", "dir"], d
        if ext in (".iso", ".cue"):
            return exe + ["-c", f'mount c "{d}"', "-c", f'imgmount d "{p}" -t iso', "-c", "d:", "-c", "dir"], d
        if ext == ".vhd":
            return exe + ["-c", f'imgmount c "{p}"', "-c", "boot c:"], d
        if ext == ".bas" and toolbox_ok():  # 1.4 : l'atelier DOS (RUNBAS/RUNGW + outils) lance le listing
            nm = os.path.splitext(os.path.basename(p))[0]
            gw = gw_ok() and (bas_tokenized(p) or (item.get("basic") or OPTS.get("basic", "gw")) == "gw")
            if gw:
                if os.path.normcase(d) == os.path.normcase(dos_path(os.path.join(P["listings"], "dos"))):
                    d = dos_path(gw_listing_dir())
                return exe + ["-c", f'mount c "{dos_path(dos_root())}"', "-c", f'mount d "{d}"', "-c", r"set PATH=C:\BATCH;C:\FDOS\BIN;C:\GWBASIC;%PATH%",
                              "-c", "D:", "-c", f"call C:\\BATCH\\RUNGW.BAT {nm}"], d
            return exe + ["-c", f'mount c "{dos_path(dos_root())}"', "-c", f'mount d "{d}"', "-c", r"set PATH=C:\BATCH;C:\FDOS\BIN;C:\FDOS\DEVEL\BWBASIC;%PATH%",
                          "-c", r"set DOSDIR=C:\FDOS", "-c", "D:", "-c", f"call C:\\BATCH\\RUNBAS.BAT {nm}"], d
        if ext == ".bas":
            bw = bwbasic_dir()
            if not bw:
                raise RuntimeError("Le BASIC DOS (bwBASIC) n'est pas encore installé.\nMenu Atelier → « Installer l'atelier ».")
            return exe + ["-c", f'mount c "{dos_path(d)}"', "-c", f'mount b "{dos_path(bw)}"', "-c", "c:", "-c", f"b:\\bwbasic.exe {os.path.basename(p)}"], d
        if os.path.isdir(p):
            return exe + ["-c", f'mount c "{p}"', "-c", "c:", "-c", "dir /w"], p
        if ext == ".zip":
            return exe + ["-c", f'mount c "{d}"', "-c", "c:", "-c", "dir /w"], d
        return exe + ["-c", f'mount c "{d}"', "-c", "c:", "-c", os.path.basename(p)], d  # .exe/.com/.bat : DOSBox-X monte le dossier et lance
    if k == "win98":
        vm = p if os.path.isdir(p) else os.path.dirname(p)
        return [exe, "-N"] + (["-F"] if OPTS.get("fullscreen") else []) + ["-P", vm], vm
    raise RuntimeError("Système inconnu")

# ---------------------------------------------------------------- bibliothèque
def load_lib():
    try:
        return json.load(open(P["lib"], encoding="utf-8"))
    except Exception:
        return []
def save_lib(lib):
    if ensure_dir(P["data"]):
        tmp = P["lib"] + ".tmp"; json.dump(lib, open(tmp, "w", encoding="utf-8"), indent=1, ensure_ascii=False); os.replace(tmp, P["lib"])

def make_cover(item, size=(150, 190)):
    """Pochette générée (style boîte de jeu rétro) si l'utilisateur n'en fournit pas."""
    from PIL import Image, ImageDraw, ImageFont
    k = item["sys"]; W, H = size
    base = {"c64": ((64, 49, 141), (120, 105, 196)), "dos": ((20, 20, 20), (85, 85, 85)), "win98": ((0, 96, 96), (0, 128, 128))}[k]
    im = Image.new("RGB", size, base[0]); d = ImageDraw.Draw(im)
    h = int(hashlib.md5(item["title"].encode()).hexdigest()[:6], 16)
    for i in range(0, H, 6):
        t = i / H; c = tuple(int(base[0][j] * (1 - t) + base[1][j] * t) for j in range(3)); d.rectangle([0, i, W, i + 6], fill=c)
    for i in range(5):  # bandes arc-en-ciel façon années 80
        col = [(255, 85, 85), (255, 170, 0), (255, 255, 85), (85, 255, 85), (85, 170, 255)][(i + h) % 5]
        y = 120 + i * 7; d.polygon([(0, y), (W, y - 30), (W, y - 25), (0, y + 5)], fill=col)
    try:
        f = ImageFont.truetype("consolab.ttf", 15); fs = ImageFont.truetype("consola.ttf", 11)
    except Exception:
        f = fs = ImageFont.load_default()
    words, lines, cur = item["title"].upper().split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > 14:
            lines.append(cur); cur = w
        else:
            cur = (cur + " " + w).strip()
    lines.append(cur)
    for i, ln in enumerate(lines[:4]):
        d.text((10, 14 + i * 19), ln, fill=(255, 255, 255), font=f)
    d.rectangle([0, H - 22, W, H], fill=(0, 0, 0)); d.text((8, H - 18), EMUS[k]["nom"], fill=(255, 255, 85), font=fs)
    d.rectangle([0, 0, W - 1, H - 1], outline=(255, 255, 255))
    ensure_dir(P["covers"]); out = os.path.join(P["covers"], f"auto_{item['id']}.png"); im.save(out); return out

# Pack de démarrage : uniquement freeware / shareware redistribuable / domaine public, URL vérifiées (archive.org).
PACK_CATS = [("demo", "Scène démo (C64 et DOS)"), ("homebrew", "Jeux C64 gratuits"), ("shareware", "Classiques DOS (shareware)"),
             ("pd", "Petits jeux DOS et domaine public")]
# Uniquement des fichiers librement redistribuables (démos, freeware, shareware, domaine public). URL vérifiées.
PACK = [
    dict(cat="demo", title="Second Reality (Future Crew, 1993)", sys="dos", url="https://files.scene.org/get/parties/1993/assembly93/demo/2nd_real.zip",
         main=("SECOND.EXE",), lic="Démo librement distribuée par Future Crew (scene.org)", src="https://files.scene.org/view/parties/1993/assembly93/demo/2nd_real.zip"),
    dict(cat="demo", title="Edge of Disgrace (Booze Design, 2008)", sys="c64", url="https://archive.org/download/Edge_of_Disgrace_2008_Booze_Design_Side_A/Edge_of_Disgrace_2008_Booze_Design_Side_A.d64",
         main=("edge_of_disgrace_A.d64",), lic="Démo de la scène, distribution libre (CSDb)", src="https://archive.org/details/Edge_of_Disgrace_2008_Booze_Design_Side_A",
         extra=[("https://archive.org/download/Edge_of_Disgrace_2008_Booze_Design_Side_A/Edge_of_Disgrace_2008_Booze_Design_Side_B.d64", "edge_of_disgrace_B.d64")]),
    dict(cat="homebrew", title="Basic Tetris (8-Bit Guy)", sys="c64", url="https://archive.org/download/8-bit-guy-freeware./basictetris%282%29.zip",
         main=("basictetris.prg",), lic="Freeware (The 8-Bit Guy, CC BY-NC-SA)", src="https://archive.org/details/8-bit-guy-freeware."),
    dict(cat="homebrew", title="64 Breakout", sys="c64", url="https://archive.org/download/64-breakout/64Breakout.zip",
         main=("64BREAK2.T64",), lic="Freeware", src="https://archive.org/details/64-breakout"),
    dict(cat="homebrew", title="Reiner's PD Nr. 01", sys="c64",
         url="https://archive.org/download/Reiners_PD_Nr._01_19xx_Reiner_Public_Domain_de/Reiner%27s%20PD%20Nr.%2001%20%2819xx%29%28Reiner%20Public%20Domain%29%28de%29%28Side%20A%29.d64",
         main=("reiners_pd_01_A.d64",), lic="Domaine public (disquette PD)", src="https://archive.org/details/Reiners_PD_Nr._01_19xx_Reiner_Public_Domain_de"),
    dict(cat="shareware", title="Commander Keen 1 - Marooned on Mars", sys="dos",
         url="https://archive.org/download/CommanderKeenInvasionOfTheVorticons/CommanderKeenInInvasionOfTheVorticons-EpisodeOne-MaroonedOnMarsV1.311991apogeeSoftwareLtd.action.zip",
         main=("KEEN1.EXE",), lic="Shareware Apogee, épisode 1 librement redistribuable", src="https://archive.org/details/CommanderKeenInvasionOfTheVorticons"),
    dict(cat="shareware", title="Commander Keen 4 (shareware)", sys="dos", url="https://archive.org/download/Keen4e-sw/keen4.zip",
         main=("KEEN4E.EXE",), lic="Shareware Apogee/id, librement redistribuable", src="https://archive.org/details/Keen4e-sw"),
    dict(cat="shareware", title="Wolfenstein 3D - épisode 1", sys="dos", url="https://archive.org/download/Wolf3d-sw1/wolf3d.zip",
         main=("WOLF3D.EXE",), lic="Shareware id Software (épisode 1), librement redistribuable", src="https://archive.org/details/Wolf3d-sw1"),
    dict(cat="shareware", title="DOOM - épisode 1 (shareware)", sys="dos", url="https://archive.org/download/DoomsharewareEpisode/DoomV1.666sw1994idSoftwareInc.action.zip",
         main=("DOOM.EXE",), lic="Shareware id Software (Knee-Deep in the Dead), librement redistribuable", src="https://archive.org/details/DoomsharewareEpisode"),
    dict(cat="shareware", title="Duke Nukem II (shareware)", sys="dos", url="https://archive.org/download/msdos_DUKE2_shareware/DUKE2.zip",
         main=("NUKEM2.EXE", "DUKE2.EXE"), lic="Shareware Apogee, librement redistribuable", src="https://archive.org/details/msdos_DUKE2_shareware"),
    dict(cat="pd", title="Light Cycle (VGA)", sys="dos", url="https://archive.org/download/msdos_VGALC_shareware/VGALC.zip",
         main=("LC.EXE",), lic="Shareware redistribuable (1991)", src="https://archive.org/details/msdos_VGALC_shareware"),
    dict(cat="pd", title="Tetrill", sys="dos", url="https://archive.org/download/msdos_TETRILL_shareware/TETRILL.zip",
         main=("TETRILL.EXE",), lic="Shareware redistribuable (1991)", src="https://archive.org/details/msdos_TETRILL_shareware"),
    dict(cat="pd", title="Hugo II", sys="dos", url="https://archive.org/download/msdos_HUGO2_shareware/HUGO2.zip",
         main=("HUGO.EXE",), lic="Shareware redistribuable (1991)", src="https://archive.org/details/msdos_HUGO2_shareware"),
]

def ascii_name(t):
    import unicodedata
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9\- ]", "_", t).strip()

def dos_path(p):
    """DOS ne comprend pas les accents : chemin court Windows (8.3) si besoin."""
    if not IS_WIN or all(ord(c) < 128 for c in p):
        return p
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(1024)
        if ctypes.windll.kernel32.GetShortPathNameW(p, buf, 1024):
            return buf.value
    except Exception:
        pass
    return p

def _pick_main(d, g):
    for m in g["main"]:
        f = find_file(d, m)
        if f:
            return f
    if g["sys"] == "dos":  # repli : premier .EXE qui n'est pas un installateur
        for dp, dn, fn in os.walk(d):
            for f in sorted(fn):
                if f.lower().endswith(".exe") and not f.lower().startswith(("install", "setup", "uninst", "patch")):
                    return os.path.join(dp, f)
    return None

def install_pack(progress=None, cats=None):
    if not internet_ok():
        raise RuntimeError("Pas d'Internet pour l'instant. Vérifie ta connexion, puis réessaie.")
    todo = [g for g in PACK if not cats or g["cat"] in cats]; out = []
    for n, g in enumerate(todo):
        d = os.path.join(P["pack"], ascii_name(g["title"])); ensure_dir(d)
        try:
            f = _pick_main(d, g)
            if not f:
                if g["url"].lower().endswith(".zip"):
                    zp = os.path.join(P["dl"], "pack_" + os.path.basename(d) + ".zip"); download(g["url"], zp)
                    with zipfile.ZipFile(zp) as z:
                        for m in z.namelist():
                            if not m.startswith("__MACOSX") and not m.endswith("/"):
                                z.extract(m, d)
                else:
                    download(g["url"], os.path.join(d, g["main"][0]))
                for u, nm in g.get("extra", []):
                    download(u, os.path.join(d, nm))
                f = _pick_main(d, g)
            if f:
                open(os.path.join(d, "SOURCE.txt"), "w", encoding="utf-8").write(
                    f"{g['title']}\nCatégorie : {dict(PACK_CATS)[g['cat']]}\nLicence : {g['lic']}\nSource : {g['src']}\nTéléchargé : {g['url']}\n")
                out.append(dict(g, path=f))
            else:
                log(f"✗ {g['title']} : programme introuvable dans l'archive.")
        except Exception as ex:
            log(f"✗ {g['title']} : téléchargement impossible ({ex}).")
        if progress:
            progress((n + 1) / max(1, len(todo)))
    return out

# ------------------------------------------------------------ Atelier + listings
LISTINGS_REPO = "https://raw.githubusercontent.com/coding-horror/basic-computer-games/main/"
LISTINGS = [  # Basic Computer Games (David Ahl, Creative Computing) - dépôt coding-horror sous licence Unlicense
    ("Super Star Trek", "84_Super_Star_Trek/superstartrek.bas"), ("Lunar Lander (LEM)", "59_Lunar_LEM_Rocket/lunar.bas"),
    ("Hammurabi", "43_Hammurabi/hammurabi.bas"), ("Le pendu (Hangman)", "44_Hangman/hangman.bas"), ("Devine le nombre (Guess)", "41_Guess/guess.bas"),
    ("Hi-Lo", "47_Hi-Lo/hi-lo.bas"), ("Bagels", "05_Bagels/bagels.bas"), ("Hurkle", "51_Hurkle/hurkle.bas"), ("Mugwump", "62_Mugwump/mugwump.bas"),
    ("Acey Ducey", "01_Acey_Ducey/aceyducey.bas"), ("Animal", "03_Animal/animal.bas"), ("Amazing (labyrinthe)", "02_Amazing/amazing.bas"),
    ("Tic-Tac-Toe", "89_Tic-Tac-Toe/tictactoe2.bas"), ("La Bourse (Stock Market)", "83_Stock_Market/stockmarket.bas"),
]
MAGAZINES = [("Compute!'s Gazette", "https://archive.org/details/computes-gazette"), ("Compute!", "https://archive.org/details/compute-magazine"),
             ("Commodore Magazine", "https://archive.org/details/commodore-magazine"), ("RUN Magazine", "https://archive.org/details/run-magazine"),
             ("Ahoy!", "https://archive.org/details/ahoymagazine"), ("Tous les périodiques Commodore", "https://archive.org/details/commodoremagazines")]
BWBASIC_URL = "https://archive.org/download/bwbasic_202408/BWBASIC.zip"  # Bywater BASIC pour DOS (GPL v2, fichier COPYING inclus)
C64_EXEMPLES = {
    "bonjour": '10 print chr$(147)"bonjour marc !"\n20 for i=1 to 10:print tab(i)"retro padawan":next\n30 print "ready pour programmer..."\n',
    "couleurs": '10 for c=0 to 15:poke 53280,c:poke 53281,15-c\n20 for t=1 to 300:next t,c\n30 poke 53280,14:poke 53281,6:print "fini !"\n',
    "devine": '10 n=int(rnd(0)*100)+1:e=0\n20 input "devine (1-100)";g:e=e+1\n30 if g<n then print "plus grand":goto 20\n'
              '40 if g>n then print "plus petit":goto 20\n50 print "bravo en";e;"essais !"\n',
}
DOS_EXEMPLES = {
    "BONJOUR.BAS": '10 PRINT "BONJOUR MARC ! (BWBASIC SUR DOS)"\n20 FOR I = 1 TO 5: PRINT TAB(I); "RETRO PADAWAN": NEXT I\n',
    "CARNET.BAS": '10 REM ECRIT UNE NOTE DANS CARNET.TXT (TEST DE SAUVEGARDE)\n20 INPUT "TA NOTE"; N$\n30 OPEN "A", #1, "CARNET.TXT"\n'
                  '40 PRINT #1, N$\n50 CLOSE #1\n60 PRINT "ENREGISTRE DANS C:\\CARNET.TXT"\n70 SYSTEM\n',
    "DEVINE.BAS": '10 RANDOMIZE TIMER: N = INT(RND * 100) + 1\n20 INPUT "DEVINE (1-100)"; G\n30 IF G < N THEN PRINT "PLUS GRAND": GOTO 20\n'
                  '40 IF G > N THEN PRINT "PLUS PETIT": GOTO 20\n50 PRINT "BRAVO !"\n',
}

def bw_fix(txt):
    """bwBASIC lit mal le code « collé » des années 70 (ex. FORI=1TOS1) : ajoute des espaces autour de TO/STEP/THEN hors des chaînes."""
    out = []
    for ln in txt.split("\n"):
        parts = ln.split('"')
        for i in range(0, len(parts), 2):
            q = parts[i]
            q = re.sub(r"(?<=[0-9A-Z)])TO(?=[A-Z0-9(.-])", " TO ", q)
            q = re.sub(r"(?<=[0-9A-Z)])STEP(?=[A-Z0-9(.-])", " STEP ", q)
            q = re.sub(r"(?<=[0-9A-Z)])THEN(?=[A-Z0-9])", " THEN ", q)
            parts[i] = q.replace("GO TO ", "GOTO ").replace("G TO ", "GOTO ").replace("S TO P", "STOP")  # 1.4 : STOP n'est plus coupé
        out.append('"'.join(parts))
    return "\n".join(out)

def up_inputs(txt):
    """1.4 : les jeux de 1978 attendent des MAJUSCULES. Après chaque INPUT d'une variable texte, on ajoute V$=UCASE$(V$)."""
    out = []
    for ln in txt.split("\n"):
        m = re.match(r"(\s*\d+\s*)(.*)$", ln)
        if not m or "INPUT" not in ln.upper():
            out.append(ln); continue
        body = m.group(2); segs = []; cur = ""; q = False
        for ch in body:
            if ch == '"':
                q = not q
            if ch == ":" and not q:
                segs.append(cur); cur = ""
            else:
                cur += ch
        segs.append(cur); new = []
        for sg in segs:
            new.append(sg)
            u = sg.upper()
            if re.search(r"\bREM\b", u.split('"')[0]) or u.lstrip().startswith("REM"):
                continue
            k = u.rfind("INPUT")
            if k < 0 or u.count('"', 0, k) % 2:
                continue
            tail = re.sub(r'"[^"]*"\s*[;,]?', "", sg[k + 5:])
            vs = [v.strip() for v in tail.split(",") if re.fullmatch(r"\s*[A-Za-z][A-Za-z0-9]?\$\s*", v)]
            new += [f"{v.upper()}=UCASE$({v.upper()})" for v in vs]
        out.append(m.group(1) + ":".join(new))
    return "\n".join(out)

def vice_tool(name):
    x = emu_exe("c64")
    t = os.path.join(os.path.dirname(x), name) if x else None
    return t if t and os.path.isfile(t) else None

def petcat_prg(txt, out):
    """Texte BASIC (listing de magazine accepté) -> .prg C64 via petcat."""
    pc = vice_tool("petcat.exe")
    if not pc:
        raise RuntimeError("VICE n'est pas installé (il fournit petcat).")
    lines = []
    for ln in txt.replace("\r", "").split("\n"):
        ln = re.sub(r":?\s*rem\s*\*?\s*\d{1,3}\s*$", "", ln.rstrip(), flags=re.I)  # sommes de contrôle Compute! / RUN
        ln = re.sub(r"^\s*\[?[A-Z]{2}\]?\s+(?=\d)", "", ln)                       # codes Ahoy! en début de ligne
        if not re.match(r"^\s*\d+", ln):
            continue
        out_ln, i = "", 0
        for part in re.split(r"(\{[^}]*\})", ln):  # garde les codes {CLR} {DOWN} en minuscules pour petcat
            out_ln += part.lower()
        lines.append(out_ln.strip())
    if not lines:
        raise RuntimeError("Aucune ligne BASIC trouvée (chaque ligne doit commencer par un numéro).")
    src = os.path.join(P["dl"], "petcat_" + os.path.basename(out) + ".txt"); ensure_dir(P["dl"])
    open(src, "w", encoding="ascii", errors="replace", newline="\n").write("\n".join(lines) + "\n")
    r = subprocess.run([pc, "-w2", "-o", out, "--", src], capture_output=True, text=True, creationflags=NOWIN, timeout=30)
    if not os.path.isfile(out) or os.path.getsize(out) < 3:
        raise RuntimeError("Conversion impossible : " + (r.stderr or r.stdout)[-300:])
    return out, len(lines)

def atelier_disk():
    return os.path.join(P["atelier"], "c64", "atelier.d64")

def c1541(*args):
    t = vice_tool("c1541.exe")
    if not t:
        raise RuntimeError("VICE n'est pas installé (il fournit c1541).")
    return subprocess.run([t] + list(args), capture_output=True, text=True, creationflags=NOWIN, timeout=60)

def bwbasic_dir():
    d = os.path.join(P["atelier"], "outils", "BWBASIC")
    return d if os.path.isfile(os.path.join(d, "BWBASIC.EXE")) else None

def install_atelier(progress=None):
    """Crée la disquette d'atelier C64, le dossier DOS, le BASIC DOS libre, les exemples et la collection de listings."""
    for d in ("c64", "dos", "outils"):
        ensure_dir(os.path.join(P["atelier"], d))
    ensure_dir(P["etats"])
    disk = atelier_disk(); made = []
    if not os.path.isfile(disk):
        c1541("-format", "atelier marc,01", "d64", disk); made.append("disquette atelier.d64")
        for n, code in C64_EXEMPLES.items():
            prg, _ = petcat_prg(code, os.path.join(P["atelier"], "c64", n + ".prg"))
            c1541("-attach", disk, "-write", prg, n)
    dd = os.path.join(P["atelier"], "dos")
    for n, code in DOS_EXEMPLES.items():
        f = os.path.join(dd, n)
        if not os.path.isfile(f):
            open(f, "w", encoding="ascii", newline="\r\n").write(code)
    if not bwbasic_dir():
        if not internet_ok():
            raise RuntimeError("Pas d'Internet pour télécharger le BASIC DOS.")
        zp = os.path.join(P["dl"], "bwbasic_dos.zip"); download(BWBASIC_URL, zp)
        with zipfile.ZipFile(zp) as z:
            z.extractall(os.path.join(P["atelier"], "outils"))
        open(os.path.join(P["atelier"], "outils", "BWBASIC", "SOURCE.txt"), "w", encoding="utf-8").write(
            "Bywater BASIC (bwBASIC) pour DOS\nLicence : GNU GPL v2 (voir COPYING)\nSource : https://archive.org/details/bwbasic_202408\n"
            "Projet : https://sourceforge.net/projects/bwbasic/\nDOS4GW.EXE : extenseur DOS redistribuable fourni avec le programme.\n")
        made.append("bwBASIC")
    items = []
    for n, (title, path) in enumerate(LISTINGS):
        base = ascii_name(title).replace(" ", "_")
        cd = os.path.join(P["listings"], "c64"); dsd = os.path.join(P["listings"], "dos"); ensure_dir(cd); ensure_dir(dsd)
        bas = os.path.join(dsd, base[:8].upper() + ".BAS")
        try:
            if not os.path.isfile(bas):
                tmp = os.path.join(P["dl"], "lst_" + base + ".bas"); download(LISTINGS_REPO + path, tmp)
                txt = open(tmp, encoding="latin-1").read().replace("\r", "")
                open(bas, "w", encoding="ascii", errors="replace", newline="\r\n").write(up_inputs(bw_fix(txt)))
            txt = open(bas, encoding="ascii", errors="replace").read()
            prg = os.path.join(cd, base + ".prg")
            if not os.path.isfile(prg):
                petcat_prg(txt, prg)
            src = f"{title}\nTiré de « BASIC Computer Games » (David H. Ahl, Creative Computing).\nTexte vérifié : dépôt coding-horror/basic-computer-games, " \
                  f"licence The Unlicense.\n{LISTINGS_REPO}{path}\n"
            open(os.path.join(P["listings"], base + "_SOURCE.txt"), "w", encoding="utf-8").write(src)
            items.append(dict(title=title + " (C64)", sys="c64", path=prg, lic="Unlicense (coding-horror)", src=LISTINGS_REPO + path))
            items.append(dict(title=title + " (DOS)", sys="dos", path=bas, lic="Unlicense (coding-horror)", src=LISTINGS_REPO + path))
        except Exception as ex:
            log(f"✗ Listing {title} : {ex}")
        if progress:
            progress((n + 1) / len(LISTINGS))
    return items

# ------------------------------------------------------------ Boîte à outils DOS « comme dans le temps » (v1.4)
# Uniquement du logiciel libre / domaine public, tiré des dépôts FreeDOS (licence vérifiée dans chaque fichier APPINFO\*.LSM).
FD_REPOS = ("https://fd.lod.bz/repos/latest", "https://www.ibiblio.org/pub/micro/pc-stuff/freedos/files/repositories/1.4")
DOS_OUTILS = [  # (paquet, groupe FreeDOS, nom affiché, licence vérifiée)
    ("volkov", "util", "Volkov Commander 4.99 (clone Norton Commander)", "BSD 2 clauses"),
    ("dn2", "apps", "Dos Navigator 2 (gestionnaire de fichiers)", "Open source, type BSD"),
    ("fdshell", "apps", "DOS Shell FreeDOS (comme DOSSHELL)", "GPL v2"),
    ("doszip", "apps", "Doszip Commander (gestionnaire + zip intégré)", "GPL v2"),
    ("edit", "base", "FreeDOS EDIT", "GPL v2"),
    ("tde", "edit", "TDE, éditeur texte/binaire", "Domaine public"),
    ("nansi", "base", "NANSI.SYS (pilote ANSI)", "GPL v2"),
    ("ansimat", "util", "ANSiMat (visionneuse d'art ANSI)", "GPL v3"),
    ("foxtype", "util", "FoxType (lecteur de textes)", "GPL v2"),
    ("zip", "archiver", "Info-ZIP ZIP 3.0 (comme PKZIP)", "Licence Info-ZIP (libre)"),
    ("unzip", "archiver", "Info-ZIP UNZIP 6.0 (comme PKUNZIP)", "Licence Info-ZIP (libre)"),
    ("7zip", "archiver", "7-Zip pour DOS (7ZA)", "Domaine public / LGPL"),
    ("arj", "archiver", "ARJ open source", "GPL v2"),
    ("deltree", "base", "DELTREE", "GPL v2"), ("xcopy", "base", "XCOPY", "GPL v2"), ("tree", "base", "TREE", "GPL"),
    ("more", "base", "MORE", "GPL v2"), ("choice", "base", "CHOICE", "GPL v2"), ("mem", "base", "MEM", "GPL v2"),
    ("mysysinf", "util", "MYSYSINF (infos système)", "GPL"),
    ("v8power", "tools", "V8Power Tools (menus en couleur pour .BAT)", "GPL v2+"),
    ("bwbasic", "devel", "Bywater BASIC 3.30 (interpréteur BASIC)", "GPL v2"),
    ("fbc", "devel", "FreeBASIC 1.10 DOS (compilateur compatible QuickBASIC : -lang qb)", "GPL v2"),
    ("cwsdpmi", "tools", "CWSDPMI (extenseur DOS pour FreeBASIC)", "GPL v2"),
    ("nethack", "games", "NetHack (jeu)", "NetHack GPL"),
    ("gnuchess", "games", "GNU Chess (échecs)", "GPL v2"),
    ("flpybird", "games", "Flappy Bird DOS (jeu)", "MIT"),
]

def dos_root():
    return os.path.join(P["atelier"], "dos")

DOS_DEV = [  # (paquet, groupe, nom, licence, fichiers ignorés pour la taille : sources dispo sur les dépôts FreeDOS)
    ("fpc", "devel", "Free Pascal 3.2.2 go32v2 + IDE fp (façon Turbo Pascal)", "GPL v2 (bibliothèques : LGPL modifiée)", r"/GDB\.EXE|^SOURCE/"),
    ("djgpp", "devel", "DJGPP 2.05 (environnement C 32 bits pour DOS)", "GPL v2 / LGPL", r"^SOURCE/"),
    ("dj_bin", "devel", "GNU binutils 2.35 (DJGPP)", "GPL", r"^SOURCE/|/SHARE/INFO/"),
    ("dj_gcc", "devel", "GCC 12.2 (DJGPP)", "GPL v3", r"LTO|/SHARE/LOCALE/|/SHARE/INFO/|^SOURCE/"),
    ("dj_rhide", "devel", "RHIDE 1.5 (IDE façon Turbo C)", "GPL", r"^SOURCE/|/RHGDB\.EXE"),
    ("dj_alego", "devel", "Allegro 4.2 pour DJGPP (graphisme, son, clavier)", "Giftware (FreeDOS : GPL v2)", r"^SOURCE/"),
]
GW_URLS = ("https://codeberg.org/tkchia/GW-BASIC/releases/download/20261005/GWB26A05.ZIP",
           "https://gitlab.com/tkchia/GW-BASIC/-/releases/20261005/downloads/GWB26A05.ZIP")
GW_SHA = {"GWBASIC.EXE": "ceb0c57c1c31981844a2e41b375cd14f77630e3e200419fe746b501d21dcf333",
          "GWBASICA.EXE": "1a7b92b1aaf893e7f040190b8fa728e3c5b4dd82caaded8fefd0a471f669f7f7"}
GW_MIT = """MIT License

Copyright (c) Microsoft Corporation.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

def bas_tokenized(p):
    """GW-BASIC enregistrait en binaire (SAVE sans ,A) : premier octet FF (ou FE = protégé)."""
    try:
        return open(p, "rb").read(1) in (b"\xff", b"\xfe")
    except Exception:
        return False

def gw_ok():
    return os.path.isfile(os.path.join(dos_root(), "GWBASIC", "GWBASIC.EXE"))

def install_gwbasic(progress=None):
    """GW-BASIC de Microsoft, assemblé depuis le code source MIT (projet tkchia/GW-BASIC). Empreintes SHA-256 vérifiées."""
    import hashlib as _h
    d = os.path.join(dos_root(), "GWBASIC"); ensure_dir(d); zp = os.path.join(P["dl"], "GWB26A05.ZIP"); err = None
    for u in GW_URLS:
        try:
            download(u, zp); err = None; break
        except Exception as ex:
            err = ex
    if err:
        raise RuntimeError(f"GW-BASIC : téléchargement impossible ({err})")
    with zipfile.ZipFile(zp) as z:
        for m in z.namelist():
            b = os.path.basename(m).upper()
            if b in GW_SHA:
                data = z.read(m)
                if _h.sha256(data).hexdigest() != GW_SHA[b]:
                    raise RuntimeError(f"GW-BASIC : empreinte SHA-256 incorrecte pour {b} - fichier refusé.")
                open(os.path.join(d, b), "wb").write(data)
    open(os.path.join(d, "LICENSE.TXT"), "wb").write(_cp(GW_MIT))
    open(os.path.join(d, "SOURCE.TXT"), "wb").write(_cp(
        "GW-BASIC 1983 de Microsoft, publie sous licence MIT (github.com/microsoft/GW-BASIC, 2020).\n"
        "Assemble par le projet communautaire tkchia/GW-BASIC (codeberg.org/tkchia/GW-BASIC), version 20261005\n"
        "(commit 1432e385), avec JWasm/JWlink. Retro a reconstruit ce depot lui-meme : les .EXE sont\n"
        "IDENTIQUES octet pour octet a la release (build reproductible). SHA-256 :\n"
        + "".join(f"  {k}  {v}\n" for k, v in GW_SHA.items())
        + "GWBASICA.EXE = experimental (TIMER, MKDIR/CHDIR/RMDIR). Ports serie absents.\n"))
    return ["GW-BASIC"]

def gw_listing_dir():
    """Copies des listings pour GW-BASIC (sans UCASE$, qui n'existe pas en GW-BASIC : on tape en MAJUSCULES)."""
    src = os.path.join(P["listings"], "dos"); dst = os.path.join(P["listings"], "gw"); ensure_dir(dst)
    if os.path.isdir(src):
        for f in os.listdir(src):
            if f.upper().endswith(".BAS"):
                t = open(os.path.join(src, f), encoding="ascii", errors="replace").read().replace("\r", "")
                t = re.sub(r":([A-Z][A-Z0-9]?\$)=UCASE\$\(\1\)", "", t)
                open(os.path.join(dst, f), "w", encoding="ascii", errors="replace", newline="\r\n").write(t)
    return dst

def fpc_lfn_fix():
    """Free Pascal range ses unités à noms longs (rtl-console = Crt…) dans LFNFILES.ZIP : on n'en garde que l'utile (≈8 Mo sur 69)."""
    fpcd = os.path.join(dos_root(), "FDOS", "DEVEL", "FPC"); lz = os.path.join(fpcd, "LFNFILES.ZIP")
    if not os.path.isfile(lz):
        return
    with zipfile.ZipFile(lz) as z:
        for m in z.infolist():
            n = m.filename.replace("\\", "/")
            if m.is_dir() or ".." in n.split("/") or not re.match(r"units/go32v2/(rtl[^/]*|fcl-base|regexpr|ptc|graph|fv)/", n, re.I):
                continue
            t = os.path.join(fpcd, *n.upper().split("/")); ensure_dir(os.path.dirname(t))
            with z.open(m) as a, open(t, "wb") as b:
                shutil.copyfileobj(a, b)
    os.remove(lz)

def dev_ok():
    return os.path.isfile(os.path.join(dos_root(), "FDOS", "DEVEL", "FPC", "BIN", "GO32V2", "FP.EXE"))

def toolbox_ok():
    return os.path.isfile(os.path.join(dos_root(), "FDOS", "BIN", "VC.COM")) and os.path.isfile(os.path.join(dos_root(), "ATELIER.BAT"))

def _cp(s):
    return s.replace("\n", "\r\n").encode("cp437", "replace")

def write_dos_files():
    """Écrit les .BAT, le menu ANSI et les textes de l'Atelier DOS (régénérés à chaque version, tes .BAS ne sont jamais touchés)."""
    d = dos_root(); E = "\x1b["
    for sub in ("BATCH", "MESPROGS", "CAPTURES"):
        ensure_dir(os.path.join(d, sub))
    def w(rel, txt):
        open(os.path.join(d, rel), "wb").write(_cp(txt))
    bar = "═" * 62
    ans = (f"{E}0;1;37;44m{E}2J{E}1;1H"
           f"{E}1;33m╔{bar}╗\n║{E}1;37m   ATELIER DOS  ·  Projet Padawan · Rétro {VERSION}{' ' * (62 - 42 - len(VERSION))}{E}1;33m║\n"
           f"║{E}0;36;44m   Comme dans le temps : 100 % logiciel libre et légal           {E}1;33m║\n╚{bar}╝{E}0;37;44m\n\n"
           f"  {E}1;33m1{E}0;37;44m  Volkov Commander     {E}0;36;44m(style Norton Commander){E}0;37;44m\n"
           f"  {E}1;33m2{E}0;37;44m  Dos Navigator        {E}0;36;44m(gestionnaire de fichiers){E}0;37;44m\n"
           f"  {E}1;33m3{E}0;37;44m  DOS Shell            {E}0;36;44m(comme le DOSSHELL de MS-DOS 5){E}0;37;44m\n"
           f"  {E}1;33m4{E}0;37;44m  EDIT                 {E}0;36;44m(éditeur de texte){E}0;37;44m\n"
           f"  {E}1;33m5{E}0;37;44m  BASIC interactif     {E}0;36;44m(bwBASIC : tape RUN, LIST, SAVE...){E}0;37;44m\n"
           f"  {E}1;33m6{E}0;37;44m  Listings des magazines {E}0;36;44m(Star Trek, Hammurabi... sur D:){E}0;37;44m\n"
           f"  {E}1;33m7{E}0;37;44m  Compiler en .EXE     {E}0;36;44m(FreeBASIC, compatible QuickBASIC){E}0;37;44m\n"
           f"  {E}1;33m8{E}0;37;44m  Jeux libres          {E}0;36;44m(NetHack, échecs, Flappy Bird){E}0;37;44m\n"
           f"  {E}1;33m9{E}0;37;44m  Art ANSI             {E}0;36;44m(voir le menu dans ANSiMat){E}0;37;44m\n"
           f"  {E}1;33m0{E}0;37;44m  Aide-mémoire des commandes {E}0;36;44m(PKZIP -> ZIP, etc.){E}0;37;44m\n"
           f"  {E}1;33mG{E}0;37;44m  GW-BASIC de Microsoft {E}0;36;44m(le vrai, code source MIT){E}0;37;44m\n"
           f"  {E}1;33mP{E}0;37;44m  Pascal               {E}0;36;44m(Free Pascal, IDE façon Turbo Pascal){E}0;37;44m\n"
           f"  {E}1;33mC{E}0;37;44m  Langage C            {E}0;36;44m(DJGPP + RHIDE, façon Turbo C){E}0;37;44m\n"
           f"  {E}1;33mL{E}0;37;44m  Librairies (LIBS)    {E}0;36;44m(Allegro, graph, routines BASIC){E}0;37;44m\n"
           f"  {E}1;33mB{E}0;37;44m  BBS Padawan          {E}0;36;44m(souvenir des babillards 2400 bauds){E}0;37;44m\n"
           f"  {E}1;33mQ{E}0;37;44m  Invite C:\\>  {E}0;36;44m(tape MENU pour revenir ici){E}0;37;44m\n"
           f"  {E}1;32mTon choix : {E}0;37;44m")
    w("MENU.ANS", ans)
    w("BATCH\\MENU.BAT", r"""@echo off
:debut
cd \
type C:\MENU.ANS
choice /c:1234567890gpclbq /n
if errorlevel 16 goto fin
if errorlevel 15 goto bbs
if errorlevel 14 goto libs
if errorlevel 13 goto lc
if errorlevel 12 goto pas
if errorlevel 11 goto gw
if errorlevel 10 goto aide
if errorlevel 9 goto ansi
if errorlevel 8 goto jeux
if errorlevel 7 goto qb
if errorlevel 6 goto listings
if errorlevel 5 goto basic
if errorlevel 4 goto edit
if errorlevel 3 goto shell
if errorlevel 2 goto dn
cls
vc
goto debut
:dn
C:\FDOS\APPS\DN2\DN.COM
goto debut
:shell
dosshell
goto debut
:edit
cls
cd \MESPROGS
edit
goto debut
:basic
cls
cd \MESPROGS
echo  BASIC interactif (Bywater BASIC). Exemple :  LOAD "BONJOUR.BAS"  puis  RUN
echo  Pour revenir au menu : tape SYSTEM
echo.
bwbasic
goto debut
:listings
call C:\BATCH\LISTINGS.BAT
goto debut
:qb
cls
echo  Compiler un programme BASIC en vrai .EXE (FreeBASIC, mode QuickBASIC) :
echo     QB NOMFICH.BAS      (dans C:\MESPROGS ou D:)
echo  Le compilateur prend quelques secondes : c'est normal, comme en 1990 !
echo.
cd \MESPROGS
dir /w *.bas
goto fin
:jeux
call C:\BATCH\JEUX.BAT
goto debut
:ansi
ansimat C:\MENU.ANS
goto debut
:aide
cls
more < C:\AIDE.TXT
pause
goto debut
:gw
cls
cd \MESPROGS
echo  GW-BASIC (Microsoft, 1983, code source MIT). LOAD "BONJOUR"  RUN  LIST  SYSTEM = quitter
echo  Astuce : les vieux jeux attendent des MAJUSCULES (Verr. Maj).
C:\GWBASIC\GWBASIC.EXE
goto debut
:pas
call C:\BATCH\TP.BAT BONJOUR.PAS
goto debut
:lc
call C:\BATCH\TC.BAT bonjour.c
goto debut
:libs
cls
type C:\LIBS\LISEZMOI.TXT
pause
goto debut
:bbs
type C:\BBS.ANS
pause > nul
goto debut
:fin
echo.
echo  Tape MENU pour revenir au menu de l'atelier.
""".replace("\n", "\n"))
    w("BATCH\\LISTINGS.BAT", r"""@echo off
:l
cls
echo  LISTINGS DE MAGAZINES (BASIC Computer Games, David H. Ahl) - lecteur D:
echo  ---------------------------------------------------------------------
D:
dir /w *.bas
echo.
echo  Tape le nom (ex. SUPER_ST pour Super Star Trek) puis Entree.
echo  Tape LIRE NOM pour lire le listing page par page.  Entree seule = retour.
set PRG=
set /p PRG=Programme : 
if "%PRG%"=="" goto fin
call C:\BATCH\RUNBAS.BAT %PRG%
pause
goto l
:fin
C:
""")
    w("BATCH\\RUNBAS.BAT", r"""@echo off
rem RUNBAS : lance un listing .BAS avec Bywater BASIC (libre, GPL v2)
if "%1"=="" goto aide
set F=%1
if exist %1.BAS set F=%1.BAS
if not exist %F% goto absent
cls
echo  Chargement de %F% ... (pour quitter un programme : Ctrl+C, puis SYSTEM)
C:\FDOS\DEVEL\BWBASIC\BWBASIC.EXE %F%
echo.
echo  Fin du programme %F%.  Tape MENU pour le menu de l'atelier.
goto fin
:absent
echo  Fichier introuvable : %1   (exemple : RUNBAS SUPER_ST)
goto fin
:aide
echo  RUNBAS NOM  : lance NOM.BAS en BASIC.  Ex. :  RUNBAS SUPER_ST
:fin
""")
    w("BATCH\\LIRE.BAT", r"""@echo off
if exist %1.BAS foxtype %1.BAS
if not exist %1.BAS foxtype %1
""")
    w("BATCH\\QB.BAT", r"""@echo off
rem QB : compile un .BAS en .EXE avec FreeBASIC (dialecte QuickBASIC, -lang qb)
if "%1"=="" goto aide
set F=%1
if exist %1.BAS set F=%1.BAS
echo  Compilation de %F% (FreeBASIC -lang qb)...
C:\FDOS\DEVEL\FBC\FBC.EXE -lang qb %F%
if errorlevel 1 goto erreur
echo  Compilation reussie ! Lance ton programme en tapant son nom.
goto fin
:erreur
echo  Erreur de compilation : lis les messages ci-dessus.
goto fin
:aide
echo  QB NOM   : compile NOM.BAS en NOM.EXE (FreeBASIC, compatible QuickBASIC 4.5)
:fin
""")
    w("BATCH\\JEUX.BAT", r"""@echo off
cls
echo  JEUX LIBRES
echo  1  NetHack (aventure, le classique des donjons)
echo  2  GNU Chess (echecs, en mode texte)
echo  3  Flappy Bird DOS (barre d'espacement)
echo  4  Retour
choice /c:1234 /n
if errorlevel 4 goto fin
if errorlevel 3 goto flap
if errorlevel 2 goto chess
cd \FDOS\GAMES\NETHACK
nethack
goto fin
:chess
cd \FDOS\GAMES\GNUCHESS
gnuchess
goto fin
:flap
cd \FDOS\GAMES\FLPYBIRD
flpybird
:fin
cd \
""")
    w("ATELIER.BAT", r"""@echo off
rem Atelier DOS - Projet Padawan (equivalent de l'AUTOEXEC.BAT)
set PATH=C:\BATCH;C:\FDOS\BIN;C:\GWBASIC;C:\FDOS\DEVEL\BWBASIC;%PATH%;C:\PERSO
set DOSDIR=C:\FDOS
set DJGPP=C:\FDOS\DEVEL\DJGPP\DJGPP.ENV
set TEMP=C:\FDOS\TEMP
set DIRCMD=/O:GN
prompt $p$g
C:
cd \
call C:\BATCH\MENU.BAT
""")
    write_dos_extras(d, w); perso_dir()
    ensure_dir(os.path.join(d, "FDOS", "TEMP"))
    lic = "\n".join(f"  {n:<9} {lb:<58} {l}" for n, g, lb, l in DOS_OUTILS) + "\n" + "\n".join(f"  {n:<9} {lb:<58} {l}" for n, g, lb, l, _ in DOS_DEV)
    w("AIDE.TXT", f"""AIDE-MEMOIRE DE L'ATELIER DOS (Retro {VERSION})
==============================================
MENU            revient au menu en couleur
VC              Volkov Commander (F3 voir, F4 editer, F5 copier, F10 quitter)
DN              Dos Navigator          DOSSHELL   le Shell FreeDOS
EDIT FICH.TXT   editeur                TDE        editeur texte/binaire
RUNBAS NOM      lance NOM.BAS (bwBASIC)  BWBASIC  BASIC interactif (SYSTEM = quitter)
RUNGW NOM       lance NOM.BAS dans le VRAI GW-BASIC   GWBASIC  GW-BASIC interactif
TP NOM.PAS      IDE Free Pascal (comme Turbo Pascal 7) ; PASC NOM = compile en ligne
TC NOM.C        IDE RHIDE + GCC (comme Turbo C)        ; CC NOM   = compile en ligne
C:\\LIBS        librairies libres + exemples (Allegro, graph/crt, routines BASIC)
QB NOM          compile NOM.BAS en .EXE (FreeBASIC -lang qb, comme QuickBASIC 4.5)
LIRE NOM        lit un listing page par page (FoxType)
ZIP / UNZIP     comme PKZIP / PKUNZIP : ZIP -r SAUVE.ZIP *.*   UNZIP SAUVE.ZIP
7ZA / ARJ       autres archiveurs      ANSIMAT F.ANS   voir un dessin ANSI
TREE, DELTREE, XCOPY, MEM, MYSYSINF   les outils de tous les jours
Alt+Entree      plein ecran / fenetre  F11+F5  capture d'ecran (Images\\Retro captures sur le PC)

Tes programmes : C:\\MESPROGS (enregistre sur ton PC, rien ne se perd)
Listings de magazines : lecteur D:

POURQUOI PAS QBASIC, QB45, TURBO PASCAL NI TURBO C ?
QBasic et QB45 (Microsoft), Turbo Pascal et Turbo C (Borland) ne sont PAS
libres de redistribution (les telechargements « gratuits » d'Embarcadero
etaient pour un usage personnel, pas pour redonner). Ici tout est libre :
bwBASIC, FreeBASIC (compatible QB45), Free Pascal (compatible Turbo
Pascal 7, unites CRT/GRAPH/DOS), DJGPP GCC + RHIDE (fait comme Turbo C).
GW-BASIC, lui, est LEGAL : Microsoft a publie son code source sous
licence MIT en 2020 ; C:\\GWBASIC est assemble depuis ce code. Si tu possedes TON QBASIC.EXE, Retro
peut l'utiliser (menu Atelier > Utiliser mon propre QBASIC.EXE).

LICENCES (verifiees, fichiers APPINFO\\*.LSM et SOURCE dans C:\\FDOS) :
{lic}
Sources : depots FreeDOS (ibiblio.org / fd.lod.bz).
""")

def write_dos_extras(d, w):
    """1.4 : GW-BASIC, Pascal, C, librairies LIBS, exemples, écran BBS."""
    E = "\x1b["
    open(os.path.join(d, "BATCH", "MAJ.COM"), "wb").write(bytes([0xB8, 0x40, 0x00, 0x8E, 0xD8, 0x80, 0x0E, 0x17, 0x00, 0x40, 0xB8, 0x00, 0x4C, 0xCD, 0x21]))
    w("BATCH\\RUNGW.BAT", r"""@echo off
rem RUNGW : lance un .BAS dans GW-BASIC (Microsoft, code source MIT)
if "%1"=="" goto aide
set F=%1
if exist %1.BAS set F=%1.BAS
if not exist %F% goto absent
cls
C:\BATCH\MAJ.COM
echo  GW-BASIC : %F%   (a la fin du programme : tape SYSTEM pour revenir a DOS)
C:\GWBASIC\GWBASIC.EXE %F%
echo.
echo  Tape MENU pour le menu de l'atelier.
goto fin
:absent
echo  Fichier introuvable : %1   (exemple : RUNGW SUPER_ST)
goto fin
:aide
echo  RUNGW NOM : lance NOM.BAS dans GW-BASIC.  Ex. : RUNGW SUPER_ST
:fin
""")
    fpc = r"""if "%PASOK%"=="" set PATH=C:\FDOS\DEVEL\FPC\BIN\GO32V2;%PATH%
set PASOK=1
if not exist C:\FDOS\DEVEL\FPC\BIN\GO32V2\FP.EXE goto absent
"""
    djg = r"""set DJGPP=C:\FDOS\DEVEL\DJGPP\DJGPP.ENV
if "%CCOK%"=="" set PATH=C:\FDOS\DEVEL\DJGPP\BIN;%PATH%
set CCOK=1
if not exist C:\FDOS\DEVEL\DJGPP\BIN\GCC.EXE goto absent
"""
    absent = """goto fin
:absent
echo  Pascal et C ne sont pas encore installes : dans Retro, menu Atelier >
echo  « Installer Pascal et C (environ 140 Mo) ».
:fin
"""
    w("BATCH\\TP.BAT", "@echo off\nrem TP : IDE Free Pascal plein ecran (comme Turbo Pascal)\n" + fpc + "cd \\MESPROGS\\PASCAL\nfp %1\n" + absent)
    w("BATCH\\PASC.BAT", "@echo off\nrem PASC NOM : compile NOM.PAS en NOM.EXE (Free Pascal, mode Turbo Pascal)\n" + fpc
      + "set F=%1\nif exist %1.PAS set F=%1.PAS\nfpc -Mtp %F%\n" + absent)
    w("BATCH\\TC.BAT", "@echo off\nrem TC : IDE RHIDE + GCC (comme Turbo C)\n" + djg + "cd \\MESPROGS\\C\nrhide %1\n" + absent)
    w("BATCH\\CC.BAT", "@echo off\nrem CC NOM [ALLEGRO] : compile NOM.C en NOM.EXE avec GCC (DJGPP)\n" + djg
      + "if \"%2\"==\"ALLEGRO\" goto al\nif \"%2\"==\"allegro\" goto al\ngcc -x c -O2 %1.c -o %1.exe\ngoto ok\n:al\ngcc -x c -O2 %1.c -o %1.exe -lalleg\n:ok\nif exist %1.EXE echo  Compilation reussie : tape %1 pour lancer.\n" + absent)
    mp = os.path.join(d, "MESPROGS")
    ex = {"BONJOUR.PAS": """program Bonjour;
{ Free Pascal, compatible Turbo Pascal 7 : F9 = compiler, Ctrl+F9 = executer, Alt+X = quitter }
uses Crt;
var i: Integer;
begin
  ClrScr;
  TextColor(Yellow);
  WriteLn('Bonjour Marc ! Pascal comme dans le temps (Free Pascal).');
  for i := 1 to 5 do
  begin
    TextColor(i + 9);
    WriteLn('':i * 2, 'Retro Padawan');
  end;
  Sound(440); Delay(150); Sound(660); Delay(150); NoSound;
  TextColor(LightGray);
  WriteLn; Write('Appuie sur une touche...'); ReadKey;
end.
""", "bonjour.c": """/* GCC (DJGPP) : dans RHIDE, F9 = compiler, Ctrl+F9 = executer, Alt+X = quitter */
#include <stdio.h>
#include <conio.h>

int main(void)
{
    int i;
    clrscr();
    textcolor(YELLOW);
    cprintf("Bonjour Marc ! Le C comme dans le temps (DJGPP + GCC).\\r\\n");
    for (i = 1; i <= 5; i++) {
        textcolor(9 + i);
        cprintf("%*sRetro Padawan\\r\\n", i * 2, "");
    }
    textcolor(LIGHTGRAY);
    cprintf("\\r\\nAppuie sur une touche...");
    getch();
    return 0;
}
"""}
    for n, t in ex.items():
        sub = "PASCAL" if n.endswith(".PAS") else "C"; ensure_dir(os.path.join(mp, sub))
        if not os.path.isfile(os.path.join(mp, sub, n)):
            w("MESPROGS\\" + sub + "\\" + n, t)
    for sub in ("LIBS", "LIBS\\BASIC", "LIBS\\PASCAL", "LIBS\\C"):
        ensure_dir(os.path.join(d, sub))
    w("LIBS\\LISEZMOI.TXT", """ LIBRAIRIES LIBRES DE L'ATELIER (C:\\LIBS) - comme dans le temps
 ----------------------------------------------------------------
 BASIC  C:\\LIBS\\BASIC\\ROUTINES.BAS  routines a partir de la ligne 9000
        (centrer, cadre, pause, hasard, majuscules). Domaine public.
        En GW-BASIC : LOAD "MONPROG" puis MERGE "C:\\LIBS\\BASIC\\ROUTINES.BAS"
        Exemple pret : RUNGW DEMOLIB  (dans C:\\LIBS\\BASIC)
 PASCAL unites CRT, GRAPH, DOS de Free Pascal (incluses, licence LGPL modifiee)
        GRAPHDEM.PAS (graphisme VGA), MUSIQUE.PAS (haut-parleur PC)
        Compiler : cd \\LIBS\\PASCAL  puis  PASC GRAPHDEM
 C      VGA13H.H : mini librairie VGA 320x200 256 couleurs + souris (MIT, Retro)
           exemple VGADEMO.C : cd \\LIBS\\C  puis  CC VGADEMO
        ALLEGRO 4 (DJGPP) : graphisme, sprites, son, clavier (giftware)
           exemple ALLEGDEM.C : CC ALLEGDEM ALLEGRO
 Pascal et C : menu Atelier de Retro > « Installer Pascal et C ».
 Touche pour revenir au menu...
""")
    rout = """9000 REM === ROUTINES RETRO PADAWAN (domaine public) - MERGE dans ton programme ===
9010 REM GOSUB 9100 : centre T$ | GOSUB 9200 : cadre de largeur W | GOSUB 9300 : pause
9020 REM GOSUB 9400 : R = hasard entre 1 et N | GOSUB 9500 : U$ = S$ en MAJUSCULES
9030 RETURN
9100 PRINT TAB(INT((80-LEN(T$))/2)+1);T$
9110 RETURN
9200 PRINT "+";STRING$(W-2,"-");"+"
9210 RETURN
9300 PRINT "  (appuie sur une touche)"
9310 K$=INKEY$:IF K$="" THEN 9310
9320 RETURN
9400 R=INT(RND(1)*N)+1
9410 RETURN
9500 U$="":FOR I9=1 TO LEN(S$):C9=ASC(MID$(S$,I9,1))
9510 IF C9>96 AND C9<123 THEN C9=C9-32
9520 U$=U$+CHR$(C9):NEXT I9
9530 RETURN
"""
    w("LIBS\\BASIC\\ROUTINES.BAS", rout)
    w("LIBS\\BASIC\\DEMOLIB.BAS", """10 REM DEMO DES ROUTINES (ROUTINES.BAS fusionne a partir de 9000)
20 CLS:W=60:GOSUB 9200
30 T$="RETRO PADAWAN - LIBRAIRIE BASIC":GOSUB 9100
40 GOSUB 9200
50 N=6:GOSUB 9400:PRINT "UN DE A 6 :";R
60 S$="bonjour marc":GOSUB 9500:PRINT "EN MAJUSCULES : ";U$
70 PRINT "FIN DE LA DEMO."
80 END
""" + rout)
    w("LIBS\\PASCAL\\GRAPHDEM.PAS", """program GraphDem;
{ Unite GRAPH de Free Pascal (comme le BGI de Turbo Pascal) }
uses Graph, Crt;
var gd, gm, i: SmallInt;
begin
  gd := D8bit; gm := m320x200;
  InitGraph(gd, gm, '');
  if GraphResult <> grOk then begin WriteLn('Mode graphique impossible'); Halt(1); end;
  for i := 1 to 60 do
  begin
    SetColor(32 + i mod 72);
    Circle(160, 100, i * 2);
  end;
  SetColor(15);
  OutTextXY(60, 185, 'Free Pascal GRAPH - une touche');
  ReadKey;
  CloseGraph;
end.
""")
    w("LIBS\\PASCAL\\MUSIQUE.PAS", """program Musique;
{ Unite CRT : Sound/Delay/NoSound sur le haut-parleur du PC - Au clair de la lune }
uses Crt;
const N: array[1..11] of Word = (262,262,262,294,330,294,262,330,294,294,262);
      D: array[1..11] of Word = (300,300,300,300,600,600,300,300,300,300,900);
var i: Integer;
begin
  WriteLn('Au clair de la lune... (haut-parleur PC)');
  for i := 1 to 11 do begin Sound(N[i]); Delay(D[i]); NoSound; Delay(40); end;
end.
""")
    w("LIBS\\C\\vga13h.h", """/* VGA13H.H - mini librairie VGA 320x200x256 + souris pour DJGPP
   (c) 2026 Retro / Projet Padawan - licence MIT : utilise-la comme tu veux. */
#ifndef VGA13H_H
#define VGA13H_H
#include <dpmi.h>
#include <go32.h>
#include <pc.h>
#include <string.h>
#include <sys/farptr.h>

static void vga_mode(int m) { __dpmi_regs r; memset(&r, 0, sizeof r); r.x.ax = m; __dpmi_int(0x10, &r); }
static void vga_pixel(int x, int y, int c)
{ if (x >= 0 && x < 320 && y >= 0 && y < 200) _farpokeb(_dos_ds, 0xA0000 + y * 320 + x, (unsigned char)c); }
static void vga_rect(int x, int y, int w, int h, int c)
{ int i, j; for (j = 0; j < h; j++) for (i = 0; i < w; i++) vga_pixel(x + i, y + j, c); }
static void vga_palette(int i, int r, int g, int b) { outportb(0x3C8, i); outportb(0x3C9, r); outportb(0x3C9, g); outportb(0x3C9, b); }
static int souris_init(void) { __dpmi_regs r; memset(&r, 0, sizeof r); r.x.ax = 0; __dpmi_int(0x33, &r); return r.x.ax == 0xFFFF; }
static void souris_voir(int on) { __dpmi_regs r; memset(&r, 0, sizeof r); r.x.ax = on ? 1 : 2; __dpmi_int(0x33, &r); }
static int souris_lire(int *x, int *y)
{ __dpmi_regs r; memset(&r, 0, sizeof r); r.x.ax = 3; __dpmi_int(0x33, &r); *x = r.x.cx / 2; *y = r.x.dx; return r.x.bx; }
#endif
""")
    w("LIBS\\C\\vgademo.c", """/* Demo de VGA13H.H : arc-en-ciel + dessin a la souris. Echap = quitter. */
#include <conio.h>
#include "vga13h.h"

int main(void)
{
    int i, x, y, b, c = 15;
    vga_mode(0x13);
    for (i = 0; i < 64; i++) vga_palette(64 + i, i, 0, 63 - i);
    for (i = 0; i < 64; i++) vga_rect(i * 5, 0, 5, 12, 64 + i);
    for (i = 0; i < 16; i++) vga_rect(i * 20, 188, 20, 12, i);
    if (souris_init()) souris_voir(1);
    for (;;) {
        if (kbhit() && getch() == 27) break;
        b = souris_lire(&x, &y);
        if (b & 1) {
            if (y >= 188) c = x / 20;
            else { souris_voir(0); vga_rect(x, y, 2, 2, c); souris_voir(1); }
        }
    }
    vga_mode(0x03);
    return 0;
}
""")
    w("LIBS\\C\\allegdem.c", """/* Allegro 4 (DJGPP) : CC ALLEGDEM ALLEGRO */
#include <allegro.h>

int main(void)
{
    int i;
    allegro_init();
    install_keyboard();
    if (set_gfx_mode(GFX_AUTODETECT, 320, 200, 0, 0) != 0) {
        allegro_message("Mode graphique impossible : %s\\n", allegro_error);
        return 1;
    }
    for (i = 0; i < 90; i++)
        circle(screen, 160, 100, i, 32 + i % 72);
    textout_centre_ex(screen, font, "ALLEGRO 4 - RETRO PADAWAN", 160, 4, 15, -1);
    textout_centre_ex(screen, font, "une touche pour quitter", 160, 190, 14, -1);
    readkey();
    return 0;
}
END_OF_MAIN()
""")
    bbs = (f"{E}0m{E}2J{E}1;1H{E}1;30m  ATDT 1-514-555-1983\n{E}0;37m  CONNECT 2400\n\n"
           f"{E}1;36m  ▄▄▄▄  ▄▄▄  ▄▄▄▄   ▄▄▄  ▄   ▄  ▄▄▄  ▄   ▄   {E}1;35m▄▄▄▄  ▄▄▄▄   ▄▄▄▄\n"
           f"{E}1;36m  █▄▄█ █▄▄█ █   █ █▄▄█ █ ▄ █ █▄▄█ █▀▄ █   {E}1;35m█▄▄▀  █▄▄▀  ▀▄▄▄\n"
           f"{E}0;36m  █    █  █ █▄▄▄▀ █  █ ▀▄▀▄▀ █  █ █  ▀█   {E}0;35m█▄▄█  █▄▄█  ▄▄▄▀\n\n"
           f"{E}1;33m  Noeud 1 · 2400 bauds · 8N1 · Sysop : Forge · ouvert 24 h sur 24 (sauf quand maman appelle)\n"
           f"{E}0;37m  ─────────────────────────────────────────────────────────────────────\n"
           f"  {E}1;32m[M]{E}0;37m Messages ......... {E}1;37m1 983 nouveaux     {E}1;32m[F]{E}0;37m Fichiers ...... {E}1;37mshareware\n"
           f"  {E}1;32m[J]{E}0;37m Portes de jeux ... {E}1;37mLORD, TradeWars    {E}1;32m[A]{E}0;37m Art ANSI ...... {E}1;37mcollection\n"
           f"  {E}1;32m[C]{E}0;37m Parler au sysop .. {E}1;37m(il dort)          {E}1;32m[G]{E}0;37m Au revoir ..... {E}1;37m(raccroche)\n\n"
           f"{E}0;36m  Souvenir : on y attendait 10 minutes pour 100 Ko, et c'était magique.\n"
           f"{E}1;30m  (Ceci est un clin d'oeil : pas de vrai modem ici.)\n\n{E}1;37m  Appuie sur une touche...{E}0m")
    w("BBS.ANS", bbs)

def install_dos_toolbox(progress=None, dev=False):
    """Télécharge les outils libres FreeDOS dans C:\\web_private\\retro\\atelier\\dos\\FDOS (une fois) et écrit le menu."""
    d = dos_root(); fd = os.path.join(d, "FDOS"); ensure_dir(fd); got = []
    have = set()
    lf = os.path.join(fd, "INSTALLE.TXT")
    if os.path.isfile(lf):
        have = set(open(lf, encoding="utf-8").read().split())
    todo = [x + ("",) for x in DOS_OUTILS if x[0] not in have] + ([x for x in DOS_DEV if x[0] not in have] if dev else [])
    if todo and not internet_ok():
        raise RuntimeError("Pas d'Internet pour télécharger la boîte à outils DOS.")
    for n, (pk, grp, lbl, lic, skip) in enumerate(todo):
        zp = os.path.join(P["dl"], f"fd_{pk}.zip"); err = None
        for base in FD_REPOS:
            try:
                download(f"{base}/{grp}/{pk}.zip", zp); err = None; break
            except Exception as ex:
                err = ex
        if err:
            log(f"? {lbl} : {err}"); continue
        with zipfile.ZipFile(zp) as z:
            for m in z.infolist():
                parts = m.filename.replace("\\", "/").split("/")
                if ".." in parts or (skip and re.search(skip, "/".join(parts).upper())):
                    continue
                parts = [p.upper() for p in parts[:-1]] + [parts[-1].upper()]
                tgt = os.path.join(fd, *parts)
                if m.is_dir():
                    ensure_dir(tgt); continue
                ensure_dir(os.path.dirname(tgt))
                with z.open(m) as src, open(tgt, "wb") as dst:
                    shutil.copyfileobj(src, dst)
        have.add(pk); got.append(lbl)
        open(lf, "w", encoding="utf-8").write("\n".join(sorted(have)))
        if progress:
            progress((n + 1) / max(1, len(todo)))
    fpc_lfn_fix()
    cfgp = os.path.join(fd, "DEVEL", "FPC", "BIN", "GO32V2", "FPC.CFG")
    if os.path.isfile(cfgp):
        t = open(cfgp, encoding="latin-1").read()
        if "C:\\devel\\fpc" in t:
            open(cfgp, "w", encoding="latin-1").write(t.replace("C:\\devel\\fpc", "C:\\FDOS\\DEVEL\\FPC"))
    if not gw_ok():
        try:
            got += install_gwbasic()
        except Exception as ex:
            log(f"? GW-BASIC : {ex}")
    write_dos_files()
    for name, target in (("DN.BAT", r"C:\FDOS\APPS\DN2\DN.COM %1 %2"), ("FBC.BAT", r"C:\FDOS\DEVEL\FBC\FBC.EXE %1 %2 %3 %4 %5 %6"),
                         ("ANSIMAT.BAT", r"C:\FDOS\UTIL\ANSIMAT\ANSIMAT.EXE %1 %2")):
        open(os.path.join(d, "BATCH", name), "wb").write(_cp("@echo off\n" + target + "\n"))
    # exemples dans MESPROGS
    mp = os.path.join(d, "MESPROGS")
    for f in os.listdir(d):
        if f.upper().endswith(".BAS") and not os.path.exists(os.path.join(mp, f.upper())):
            shutil.copy2(os.path.join(d, f), os.path.join(mp, f.upper()))
    return got

# ------------------------------------------------------------ 1.4 : 📥 Importer mes vieux trucs / 📤 Exporter
IMPORT_EXT = (".bas", ".prg", ".d64", ".t64", ".com", ".exe", ".txt", ".zip")

def _dec(b):
    for enc in ("utf-8", "cp437"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            pass
    return b.decode("latin-1")

def looks_basic(txt):
    ls = [l for l in txt.split("\n") if l.strip()]
    return bool(ls) and sum(1 for l in ls if re.match(r"\s*\d+\s*\S", l)) >= 0.6 * len(ls)

def guess_basic_sys(txt):
    """C64 ou DOS ? Indices typiques de chaque machine."""
    u = txt.upper()
    c64 = len(re.findall(r"\{(CLR|HOME|DOWN|UP|RVS|WHT|BLK|RED|CYN)", u)) * 3 + len(re.findall(r"POKE\s*5328[01]|POKE\s*5\d{4}|SYS\s*\d|CHR\$\(147\)|PEEK\s*\(\s*197|POKE\s*646", u)) * 3
    dos = len(re.findall(r"\b(CLS|SCREEN|COLOR|LOCATE|INKEY\$|KEY\s+OFF|WIDTH|BEEP|SOUND|PLAY|LINE\s*\(|CIRCLE|PSET|DEF\s+SEG)\b", u)) * 2
    letters = [c for c in txt if c.isalpha()]
    if letters and sum(1 for c in letters if c.islower()) > 0.7 * len(letters):
        c64 += 2  # les listings C64 tapés sur PC sont souvent en minuscules
    return "c64" if c64 > dos else "dos"

def _uniq(path):
    d, f = os.path.split(path); b, e = os.path.splitext(f); n = 1
    while os.path.exists(path):
        path = os.path.join(d, (b[:8 - len(str(n))] + str(n) if e.upper() == ".BAS" else f"{b}_{n}") + e); n += 1
    return path

PERSO_MARK = "_PRIVE_NE_PAS_DISTRIBUER.TXT"

def perso_dir():
    """atelier\\dos\\PERSO : TES logiciels d'époque (QB45 de tes disquettes…). Dans le PATH, exclu de toute distribution."""
    d = os.path.join(dos_root(), "PERSO"); ensure_dir(d)
    mk = os.path.join(d, PERSO_MARK)
    if not os.path.isfile(mk):
        open(mk, "wb").write(_cp("DOSSIER PRIVE - NE PAS DISTRIBUER\n"
            "Logiciels personnels importes par Marc (ex. QB45 de ses disquettes) : PAS redistribuables.\n"
            "Ce dossier doit etre EXCLU du zip, de l'exe d'installation et de toute copie pour les collegues.\n"))
    return d

def import_sources(paths):
    """Copie (jamais de déplacement) dans atelier\\mes_programmes\\c64|dos, convertit encodage/fins de ligne. Renvoie les fiches."""
    base = os.path.join(P["atelier"], "mes_programmes"); out = []; files = []
    def walk(p, orig, root=None):
        if os.path.isdir(p):
            for r, _, fs in os.walk(p):
                for f in fs:
                    walk(os.path.join(r, f), orig, root or p)
        elif p.lower().endswith(".zip"):
            tmp = os.path.join(P["dl"], "import_" + time.strftime("%Y%m%d%H%M%S") + "_" + str(len(files))); ensure_dir(tmp)
            with zipfile.ZipFile(p) as z:
                for m in z.infolist():
                    if ".." in m.filename.replace("\\", "/").split("/") or m.is_dir():
                        continue
                    t = os.path.join(tmp, *m.filename.replace("\\", "/").split("/")); ensure_dir(os.path.dirname(t))
                    with z.open(m) as a, open(t, "wb") as b:
                        shutil.copyfileobj(a, b)
            ents = os.listdir(tmp)
            walk(os.path.join(tmp, ents[0]) if len(ents) == 1 and os.path.isdir(os.path.join(tmp, ents[0])) else tmp, os.path.basename(p) + " (zip)")
        elif os.path.splitext(p)[1].lower() in IMPORT_EXT:
            files.append((p, orig or p, root))
    for p in paths:
        walk(p.strip().strip("{}").strip('"'), None)
    done_roots = {}
    for p, orig, root in files:
        ext = os.path.splitext(p)[1].lower(); stem = os.path.splitext(os.path.basename(p))[0]
        title = re.sub(r"[_\-]+", " ", stem).strip().title(); note = f"Importé de {orig} le {time.strftime('%Y-%m-%d')}."
        try:
            if ext in (".prg", ".d64", ".t64"):
                d = os.path.join(base, "c64"); ensure_dir(d); t = _uniq(os.path.join(d, os.path.basename(p))); shutil.copy2(p, t)
                out.append(dict(path=t, sys="c64", title=title, notes=note)); continue
            if ext in (".com", ".exe"):
                # logiciels d'époque à TOI (ex. QB45 de tes disquettes) : C:\PERSO, dans le PATH, JAMAIS distribué
                perso = perso_dir(); src_dir = root or os.path.dirname(p); key = os.path.normcase(src_dir)
                if key not in done_roots:
                    base_nm = os.path.basename(src_dir.rstrip("\\/"))
                    if src_dir.startswith(P["dl"]):
                        base_nm = os.path.splitext(os.path.basename(orig.replace(" (zip)", "")))[0]
                    nm = ascii_name(base_nm).replace(" ", "")[:8].upper() or "PROG"
                    dd = _uniq(os.path.join(perso, nm))
                    if root:
                        shutil.copytree(src_dir, dd)
                    else:
                        ensure_dir(dd); shutil.copy2(p, dd)
                    done_roots[key] = dd
                dd = done_roots[key]
                t = os.path.join(dd, os.path.relpath(p, src_dir)) if root else os.path.join(dd, os.path.basename(p))
                bat = os.path.join(perso, ascii_name(stem).replace(" ", "")[:8].upper() + ".BAT")
                if not os.path.exists(bat):
                    rel = os.path.relpath(os.path.dirname(t), dos_root()).replace("/", "\\")
                    open(bat, "wb").write(_cp(f"@echo off\nrem lanceur cree par Retro (dossier PERSO, prive)\ncd \\{rel}\n{os.path.basename(t)} %1 %2 %3 %4\n"))
                out.append(dict(path=t, sys="dos", title=title, notes=note + " Rangé dans C:\\PERSO (privé, jamais distribué).")); continue
            raw = open(p, "rb").read()
            if raw[:1] in (b"\xff", b"\xfe") and ext == ".bas":
                d = os.path.join(base, "dos"); ensure_dir(d); t = _uniq(os.path.join(d, ascii_name(stem)[:8].upper().replace(" ", "_") + ".BAS"))
                open(t, "wb").write(raw)
                out.append(dict(path=t, sys="dos", title=title, notes=note + " Format GW-BASIC binaire (lancé dans GW-BASIC).", basic="gw")); continue
            txt = _dec(raw).replace("\r\n", "\n").replace("\r", "\n").replace("\x1a", "")
            if not looks_basic(txt):
                log(f"Ignoré (pas un listing BASIC) : {p}"); continue
            k = guess_basic_sys(txt)
            if k == "c64":
                d = os.path.join(base, "c64"); ensure_dir(d)
                src = _uniq(os.path.join(d, ascii_name(stem).replace(" ", "_") + ".bas"))
                open(src, "w", encoding="utf-8", newline="\n").write(txt)
                prg, n = petcat_prg(txt, os.path.splitext(src)[0] + ".prg")
                out.append(dict(path=prg, sys="c64", title=title, notes=note + f" Listing C64 converti en .prg ({n} lignes).", src_txt=src))
            else:
                d = os.path.join(base, "dos"); ensure_dir(d)
                t = _uniq(os.path.join(d, (ascii_name(stem)[:8].upper().replace(" ", "_") or "PROG") + ".BAS"))
                open(t, "wb").write(txt.replace("\n", "\r\n").encode("cp437", "replace"))
                out.append(dict(path=t, sys="dos", title=title, notes=note + " Listing DOS (texte, CR/LF, page de codes 437)."))
        except Exception as ex:
            log(f"? Import {p} : {ex}")
    return out

def export_item(it, fmt, dest):
    """📤 Exporte une fiche : zip, bas (texte), prg ou d64."""
    p = it["path"]; ext = os.path.splitext(p)[1].lower(); k = it["sys"]
    if fmt == "zip":
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
            if os.path.isdir(p):
                for r, _, fs in os.walk(p):
                    for f in fs:
                        z.write(os.path.join(r, f), os.path.relpath(os.path.join(r, f), os.path.dirname(p)))
            else:
                z.write(p, os.path.basename(p))
                if it.get("src_txt") and os.path.isfile(it["src_txt"]):
                    z.write(it["src_txt"], os.path.basename(it["src_txt"]))
            z.writestr("FICHE.TXT", f"{it.get('title','')}\r\nSysteme : {k}\r\n{it.get('notes','')}\r\nExporte par Retro {VERSION}\r\n")
        return dest
    if fmt == "bas":
        if k == "dos" and ext == ".bas":
            if bas_tokenized(p):
                raise RuntimeError("Ce .BAS est au format binaire de GW-BASIC.\nDans GW-BASIC : LOAD \"NOM\" puis SAVE \"NOM\",A pour le mettre en texte.")
            shutil.copy2(p, dest); return dest
        if ext == ".prg":
            pc = vice_tool("petcat.exe")
            if not pc:
                raise RuntimeError("VICE (petcat) est nécessaire.")
            r = subprocess.run([pc, "-2", "-o", dest, "--", p], capture_output=True, text=True, creationflags=NOWIN, timeout=30)
            if not os.path.isfile(dest):
                raise RuntimeError("Conversion impossible : " + (r.stderr or r.stdout)[-300:])
            return dest
        raise RuntimeError("Seuls les listings BASIC (.BAS DOS ou .prg C64) s'exportent en texte.")
    if fmt in ("prg", "d64"):
        if ext == ".prg":
            prg = p
        elif ext == ".bas":
            if bas_tokenized(p):
                raise RuntimeError("Format GW-BASIC binaire : enregistre-le d'abord en texte (SAVE \"NOM\",A).")
            prg, _ = petcat_prg(open(p, encoding="cp437", errors="replace").read(), os.path.join(P["dl"], "export.prg"))
        else:
            raise RuntimeError("Seuls les programmes BASIC ou .prg s'exportent pour le C64.")
        if fmt == "prg":
            shutil.copy2(prg, dest); return dest
        nm = re.sub(r"[^a-z0-9 ]", "", (it.get("title") or "programme").lower())[:16] or "programme"
        if os.path.exists(dest):
            os.remove(dest)
        c1541("-format", f"retro padawan,01", "d64", dest)
        c1541("-attach", dest, "-write", prg, nm)
        return dest
    raise RuntimeError("Format inconnu")

def atelier_files():
    out = []
    r = c1541("-attach", atelier_disk(), "-list") if os.path.isfile(atelier_disk()) else None
    if r:
        for ln in r.stdout.splitlines():
            m = re.match(r'\s*(\d+)\s+"([^"]+)"\s+(\w+)', ln)
            if m:
                out.append(("c64", m.group(2), m.group(3), int(m.group(1))))
    dd = os.path.join(P["atelier"], "dos")
    if os.path.isdir(dd):
        for f in sorted(os.listdir(dd)):
            if os.path.isfile(os.path.join(dd, f)):
                out.append(("dos", f, os.path.splitext(f)[1][1:].upper(), os.path.getsize(os.path.join(dd, f))))
    return out

EXIT_KEYS = {
    "c64": "VICE : Alt+Q = quitter · F12 ou Alt+D = plein écran on/off · ou bouton ⏹ Fermer le jeu / Ctrl+Alt+Q",
    "dos": "DOSBox-X : Alt+Entrée = quitter le plein écran · puis la croix, ou bouton ⏹ Fermer le jeu / Ctrl+Alt+Q",
    "win98": "86Box : Ctrl+Alt+PgDn = quitter le plein écran · Ctrl+Fin = libérer la souris · ⏹ Fermer le jeu / Ctrl+Alt+Q",
}

def scan_dir(root):
    """Trouve les jeux dans « Mes jeux » : fichiers C64/DOS, et pour un sous-dossier DOS, son .exe/.com/.bat principal."""
    found = []
    if not os.path.isdir(root):
        return found
    for dp, dn, fn in os.walk(root):
        if os.path.normcase(dp).startswith(os.path.normcase(P["pack"])):
            continue
        progs = [f for f in fn if f.lower().endswith((".exe", ".com", ".bat"))]
        for f in fn:
            if os.path.splitext(f)[1].lower() in EMUS["c64"]["ext"] + (".img", ".ima", ".iso", ".cue", ".vhd"):
                found.append(os.path.join(dp, f))
        if progs and dp != root:
            name = os.path.basename(dp).lower()
            best = sorted(progs, key=lambda f: (f.lower().startswith(("install", "setup", "uninst", "readme", "printdoc")),
                                                name[:4] not in f.lower(), not f.lower().endswith(".exe"), len(f)))[0]
            found.append(os.path.join(dp, best))
        elif progs:
            found += [os.path.join(dp, f) for f in progs]
    return found

WIN98_GUIDE = """WINDOWS 98 AVEC 86BOX - guide pas à pas
(Rétro ne fournit PAS Windows 98 : il te faut TON CD ou ISO et ta clé de produit.)

1. Clique « Installer » à côté de Windows 98 (86Box, source officielle github.com/86Box).
2. Clique « ROMs 86Box » : Rétro télécharge les ROMs de BIOS depuis le dépôt officiel 86Box/roms
   (dossier roms à côté de 86Box.exe).
3. « + Machine Win98 » : donne un nom. 86Box ouvre ses réglages :
   - Machine : Slot 1 / Intel 440BX (ex. ASUS P2B-LS), CPU Pentium II 300 MHz, 64 à 128 Mo de RAM ;
   - Vidéo : 3dfx Voodoo3 ou S3 Trio64 ; Son : Sound Blaster 16 ;
   - Stockage : disque IDE de 2 Go (Nouveau...), lecteur CD-ROM ATAPI.
4. Démarre la machine. Menu Média → CD-ROM → Image... → choisis TON ISO de Windows 98.
   Insère aussi la disquette de démarrage Windows 98 (Média → Disquette), puis :
   FDISK (oui au grand disque), redémarre, FORMAT C:, puis D:\\SETUP.
5. Après l'installation, retire la disquette. Ta machine apparaît dans la bibliothèque : double-clic pour la relancer.

Astuces : Ctrl+Alt+PgDn = plein écran ; Ctrl+Fin = libérer la souris.
Où acheter légalement des jeux Win9x/DOS : gog.com.
"""

def install_roms_86box(progress=None):
    exe = emu_exe("win98")
    if not exe:
        raise RuntimeError("Installe d'abord 86Box.")
    if not internet_ok():
        raise RuntimeError("Pas d'Internet.")
    rel = http_json("https://api.github.com/repos/86Box/roms/releases/latest")
    zp = os.path.join(P["dl"], f"86box-roms-{rel['tag_name']}.zip"); download(rel["zipball_url"], zp, progress)
    dst = os.path.join(os.path.dirname(exe), "roms"); ensure_dir(dst)
    with zipfile.ZipFile(zp) as z:
        pre = z.namelist()[0].split("/")[0] + "/"
        for m in z.namelist():
            rel_m = m[len(pre):]
            if rel_m and not m.endswith("/"):
                t = os.path.join(dst, *rel_m.split("/")); ensure_dir(os.path.dirname(t))
                with z.open(m) as a, open(t, "wb") as b:
                    shutil.copyfileobj(a, b)
    log(f"✓ ROMs 86Box installées dans {dst}")

def backup_lib():
    ensure_dir(P["saves"]); out = os.path.join(P["saves"], time.strftime("retro-bibliotheque-%Y%m%d-%H%M%S.zip"))
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in (P["lib"], os.path.join(P["data"], "retro_config.json")):
            if os.path.isfile(f):
                z.write(f, os.path.basename(f))
        if os.path.isdir(P["covers"]):
            for f in os.listdir(P["covers"]):
                z.write(os.path.join(P["covers"], f), "pochettes/" + f)
    return out

def restore_lib(zp):
    with zipfile.ZipFile(zp) as z:
        names = z.namelist()
        if "bibliotheque.json" not in names:
            raise RuntimeError("Ce fichier n'est pas une sauvegarde Rétro.")
        if os.path.isfile(P["lib"]):
            shutil.copy2(P["lib"], P["lib"] + time.strftime(".avant-restauration-%Y%m%d-%H%M%S"))
        for m in names:
            if m.startswith("pochettes/") or m in ("bibliotheque.json", "retro_config.json"):
                z.extract(m, P["data"])

LEGAL = [
    ("C64 — CSDb (démos et productions de la scène)", "https://csdb.dk/"),
    ("C64 — nouveaux jeux homebrew (itch.io)", "https://itch.io/games/tag-commodore-64"),
    ("DOS — Classic DOS Games (freeware / shareware)", "https://www.classicdosgames.com/"),
    ("DOS — DOS Games Archive (freeware / shareware)", "https://www.dosgamesarchive.com/"),
    ("DOS — FreeDOS (DOS libre et légal)", "https://www.freedos.org/"),
    ("DOS — homebrew DOS (itch.io)", "https://itch.io/games/tag-dos"),
    ("Achat légal de classiques DOS/Win9x — GOG", "https://www.gog.com/"),
    ("86Box — ROMs : documentation officielle", "https://86box.readthedocs.io/en/latest/usage/roms.html"),
    ("Archive.org — collection de logiciels shareware (CD shareware)", "https://archive.org/details/cdbbsarchive"),
]

def make_icons():
    from PIL import Image, ImageDraw
    def draw(sz):
        im = Image.new("RGBA", (sz, sz), (0, 0, 0, 0)); d = ImageDraw.Draw(im); s = sz / 64
        d.rounded_rectangle([2*s, 6*s, 62*s, 58*s], radius=8*s, fill=(120, 105, 196, 255))
        d.rectangle([8*s, 12*s, 56*s, 46*s], fill=(64, 49, 141, 255))
        for i, c in enumerate([(255, 85, 85), (255, 170, 0), (255, 255, 85), (85, 255, 85)]):
            d.rectangle([40*s + i*4*s, 48*s, 43*s + i*4*s, 55*s], fill=c + (255,))
        d.rectangle([12*s, 18*s, 34*s, 22*s], fill=(160, 150, 255, 255)); d.rectangle([12*s, 30*s, 18*s, 36*s], fill=(160, 150, 255, 255))
        return im
    big = draw(256); big.save(os.path.join(HERE, "retro1_256.png")); draw(64).save(os.path.join(HERE, "retro1.png"))
    big.save(os.path.join(HERE, "retro1.ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

def floppy_sound(on):
    if not (on and IS_WIN):
        return
    def go():
        try:
            import winsound
            for f, ms in ((180, 40), (140, 30), (220, 25), (160, 40), (120, 60), (200, 30)):
                winsound.Beep(f, ms)
        except Exception:
            pass
    threading.Thread(target=go, daemon=True).start()

THEMES = {
    "c64": dict(bg="#7869c4", panel="#40318d", fg="#a59bff", acc="#ffffff", font=("Consolas", 11, "bold"), sel="#352879"),
    "dos": dict(bg="#000000", panel="#000000", fg="#c0c0c0", acc="#ffff55", font=("Consolas", 11), sel="#0000aa"),
    "norton": dict(bg="#0000aa", panel="#0000aa", fg="#55ffff", acc="#ffff55", font=("Consolas", 11), sel="#000000"),
}

def single_instance():
    if not IS_WIN:
        return True
    try:
        import ctypes
        globals()["_MUTEX"] = ctypes.windll.kernel32.CreateMutexW(None, False, "Padawan_Retro1_Mutex")
        return ctypes.windll.kernel32.GetLastError() != 183
    except Exception:
        return True

class Tip:
    def __init__(self, w, text):
        self.w, self.text, self.tw = w, text, None
        w.bind("<Enter>", self.show, add="+"); w.bind("<Leave>", self.hide, add="+"); w.bind("<ButtonPress>", self.hide, add="+")
    def show(self, e=None):
        import tkinter as tk
        if self.tw or not self.text:
            return
        self.tw = tk.Toplevel(self.w); self.tw.overrideredirect(True); self.tw.attributes("-topmost", True)
        tk.Label(self.tw, text=self.text, bg="#ffffe0", fg="#000000", font=("Segoe UI", 10), relief="solid", bd=1, padx=6, pady=3,
                 wraplength=360, justify="left").pack()
        self.tw.geometry(f"+{self.w.winfo_rootx() + 10}+{self.w.winfo_rooty() + self.w.winfo_height() + 4}")
    def hide(self, e=None):
        if self.tw:
            self.tw.destroy(); self.tw = None

def run_gui(test_ms=0):
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox, simpledialog
    dnd_root = None
    try:
        from tkinterdnd2 import TkinterDnD, DND_FILES
        root = TkinterDnD.Tk(); dnd_root = True
    except Exception:
        root = tk.Tk()
    root.title(f"Rétro {VERSION} — C64 · DOS · Win98 (Projet Padawan)")
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    W, H = min(1100, sw - 20), min(760, sh - 70)
    root.geometry(f"{W}x{H}+{max(0,(sw-W)//2)}+0"); root.minsize(min(700, sw - 40), min(420, sh - 80))
    try:
        root.iconbitmap(os.path.join(HERE, "retro1.ico"))
    except Exception:
        pass
    ensure_dir(P["data"])
    cfgf = os.path.join(P["data"], "retro_config.json")
    try:
        cfg = json.load(open(cfgf, encoding="utf-8"))
    except Exception:
        cfg = {}
    for k_, v_ in {"theme": "c64", "sound": True, "intro": True, "big": True, "fullscreen": True, "crt": False, "pad": True, "maximized": True}.items():
        cfg.setdefault(k_, v_)
    cfg.setdefault("joyport", 2)
    OPTS.update({k_: cfg[k_] for k_ in ("fullscreen", "crt", "pad", "joyport")}); CUSTOM_EXE.update(cfg.get("exe", {})); OPTS["clavier"] = cfg.get("clavier", "cf"); OPTS["basic"] = cfg.get("basic", "gw")
    def save_cfg():
        try:
            json.dump(cfg, open(cfgf, "w", encoding="utf-8"))
        except Exception:
            pass
    T = dict(THEMES[cfg.get("theme", "c64")])
    lib = load_lib(); imgs = {}; auto_sig = {}; cover_jobs = set(); _rs = [None]
    def render_soon(ms=60):
        if _rs[0]:
            root.after_cancel(_rs[0])
        _rs[0] = root.after(ms, lambda: (_rs.__setitem__(0, None), render()))
    filt = tk.StringVar(value="tout"); search = tk.StringVar(); sel = [None]

    # ---------- écran READY.
    intro = tk.Canvas(root, highlightthickness=0, bg="#7869c4")
    def play_intro(done):
        intro.place(x=0, y=0, relwidth=1, relheight=1); tk.Misc.lift(intro); t0 = time.time()
        lines = ["", "    **** COMMODORE 64 BASIC V2 ****", "", " 64K RAM SYSTEM  38911 BASIC BYTES FREE", "", "READY.",
                 'LOAD"PADAWAN RETRO",8,1', "", "SEARCHING FOR PADAWAN RETRO", "LOADING", "READY.", "RUN"]
        state = {"end": False}
        def frame():
            if state["end"]:
                return
            el = time.time() - t0; w = intro.winfo_width() or W; h = intro.winfo_height() or H
            intro.delete("all"); bw = 46
            if 2.0 < el < 3.0:  # bandes de chargement de cassette/disquette
                cols = ["#7869c4", "#40318d", "#a59bff", "#ffffff", "#9ad284", "#c46c71"]
                for y in range(0, h, 7):
                    intro.create_rectangle(0, y, w, y + 7, fill=cols[(y // 7 + int(el * 40)) % len(cols)], outline="")
            else:
                intro.create_rectangle(0, 0, w, h, fill="#7869c4", outline="")
            intro.create_rectangle(bw, bw, w - bw, h - bw, fill="#40318d", outline="")
            shown = int(min(len(lines), 1 + el * 4.2)); typed = lines[:shown]
            if len(typed) >= 7:  # tape LOAD lettre par lettre
                n = int((el - 6 / 4.2) * 18); typed[6] = lines[6][:max(0, n)]
            fs = max(11, min(18, (w - 2 * bw) // 44))
            for i, ln in enumerate(typed):
                intro.create_text(bw + 14, bw + 14 + i * (fs + 8), anchor="nw", text=ln, fill="#a59bff", font=("Consolas", fs, "bold"))
            if int(el * 2.5) % 2 == 0:
                y = bw + 14 + len(typed) * (fs + 8)
                intro.create_rectangle(bw + 14, y, bw + 14 + fs * 0.7, y + fs + 4, fill="#a59bff", outline="")
            intro.create_text(w - bw, h - bw / 2, anchor="e", text="clic ou Échap pour passer", fill="#c0b8ff", font=("Consolas", 9))
            if el > 3.4:
                finish()
            else:
                root.after(40, frame)
        def finish(*_):
            if state["end"]:
                return
            state["end"] = True; intro.place_forget(); root.unbind("<Escape>"); done()
        intro.bind("<Button-1>", finish); root.bind("<Escape>", finish); floppy_sound(cfg.get("sound"))
        frame()

    # ---------- haut
    top = tk.Frame(root); top.pack(fill="x", padx=10, pady=(8, 4))
    title = tk.Label(top, text="◤ RÉTRO ◢  le coin du vieux nostalgique", anchor="w"); title.pack(side="left")
    emubar = tk.Frame(root); emubar.pack(fill="x", padx=10)
    emu_lbl = {}
    small = sw < 1400
    for n_, (k, e) in enumerate(EMUS.items()):
        f = tk.Frame(emubar, bd=0, padx=6, pady=3); f.grid(row=n_ // 2 if small else 0, column=n_ % 2 if small else n_, padx=(0, 8), pady=1, sticky="w")
        l = tk.Label(f, text="", anchor="w"); l.pack(side="left")
        o = tk.Button(f, text="▶ Ouvrir", relief="flat", command=lambda k=k: open_emu(k)); o.pack(side="left", padx=(6, 0))
        b = tk.Button(f, text="Installer", relief="flat", command=lambda k=k: install(k)); b.pack(side="left", padx=4)
        s = tk.Button(f, text="Site", relief="flat", command=lambda u=e["site"]: webbrowser.open(u)); s.pack(side="left")
        emu_lbl[k] = (f, l, b, s, o)
    pbar = ttk.Progressbar(emubar, mode="determinate", maximum=1.0, length=140); pbar.grid(row=1 if small else 0, column=1 if small else 3, sticky="e")

    bar = tk.Frame(root); bar.pack(fill="x", padx=10, pady=6)
    rbs = []
    for v, lbl in (("tout", "Tout"), ("c64", "C64"), ("dos", "DOS"), ("win98", "Win98"), ("fav", "★ Favoris"), ("recent", "⏱ Récents")):
        r = tk.Radiobutton(bar, text=lbl, value=v, variable=filt, indicatoron=0, padx=10, pady=2, command=lambda: render()); r.pack(side="left", padx=2); rbs.append(r)
    se = tk.Entry(bar, textvariable=search, width=16); se.pack(side="left", padx=10); search.trace_add("write", lambda *_: render_soon(150))
    catv = tk.StringVar(value="Toutes catégories")
    catcb = ttk.Combobox(bar, textvariable=catv, width=18, state="readonly"); catcb.pack(side="left")
    catcb.bind("<<ComboboxSelected>>", lambda e: render())
    def all_tags():
        return sorted({t for i in lib for t in i.get("tags", [])}, key=str.lower)
    undo = []
    def snap():
        undo.append(json.dumps(lib)); del undo[:-30]
    def do_undo(*_):
        if undo:
            lib[:] = json.loads(undo.pop()); save_lib(lib); imgs.clear(); auto_sig.clear(); render(); log(f"↶ Annulé (Ctrl+Z) - {len(undo)} étape(s) restante(s)")
        else:
            log("Rien à annuler.")
    root.bind("<Control-z>", do_undo); root.bind("<Control-Z>", do_undo)
    btns = []
    bar2 = tk.Frame(root); bar2.pack(fill="x", padx=10, pady=(0, 6))
    bar2b = tk.Frame(bar2) if not small else tk.Frame(root)
    for lbl, cmd in (("🎁 Pack de démarrage", lambda: pack()), ("↻ Scanner Mes jeux", lambda: scan(True)), ("📁 Mes jeux", lambda: open_jeux()),
                     ("Guide Win98", lambda: guide98()), ("ROMs 86Box", lambda: roms86()), ("💾 Sauvegarder", lambda: do_backup()),
                     ("Restaurer", lambda: do_restore()), ("⚙ Options", lambda: options())):
        b = tk.Button(bar2 if lbl[0] not in "GR💾⚙" else bar2b, text=lbl, relief="flat", padx=6, command=cmd); b.pack(side="left", padx=2); btns.append(b)
    stopb = tk.Button(bar2, text="\u23f9  Fermer le jeu  (Ctrl+Alt+Q)", command=lambda: stop_game(), relief="flat", bg="#c0392b", fg="#ffffff",
                      activebackground="#e74c3c", activeforeground="#ffffff", font=("Segoe UI", 12, "bold"), padx=12, pady=2, cursor="hand2")
    stopb.pack(side="right", padx=4)
    def hotkey_thread():
        """Raccourci GLOBAL Ctrl+Alt+Q : marche m\u00eame quand le jeu est en plein \u00e9cran devant R\u00e9tro."""
        try:
            import ctypes
            from ctypes import wintypes
            u = ctypes.windll.user32
            if not u.RegisterHotKey(None, 0x5254, 0x0001 | 0x0002 | 0x4000, 0x51):   # Alt|Ctrl|NOREPEAT, Q
                ui(lambda: log("\u26a0 Ctrl+Alt+Q d\u00e9j\u00e0 pris par un autre programme : utilise le bouton \u23f9 Fermer le jeu.")); return
            m = wintypes.MSG()
            while u.GetMessageW(ctypes.byref(m), None, 0, 0) > 0:
                if m.message == 0x0312:
                    ui(lambda: stop_game())
        except Exception:
            pass
    threading.Thread(target=hotkey_thread, daemon=True).start()
    if small:
        bar2b.pack(fill="x", padx=10, pady=(0, 6), after=bar2)
    else:
        bar2b.pack(side="left")
    for lbl, cmd in (("+ Ajouter", lambda: add_files()), ("+ Dossier DOS", lambda: add_folder()), ("+ Machine Win98", lambda: new_vm()),
                     ("Sources légales", lambda: legal()), ("Thème", lambda: cycle_theme())):
        b = tk.Button(bar, text=lbl, relief="flat", padx=8, command=cmd); b.pack(side="right", padx=2); btns.append(b)

    fk = tk.Frame(root); fk.pack(fill="x", side="bottom")
    logw = tk.Text(root, height=3 if sh < 800 else 4, bd=0, padx=8, state="disabled"); logw.pack(fill="x", side="bottom", padx=10, pady=(4, 0))
    mid = tk.Frame(root); mid.pack(fill="both", expand=True, padx=10)
    cv = tk.Canvas(mid, highlightthickness=0); cv.pack(side="left", fill="both", expand=True)
    sb = ttk.Scrollbar(mid, orient="vertical", command=cv.yview); sb.pack(side="right", fill="y"); cv.configure(yscrollcommand=sb.set)
    FK = [("F1", "Aide"), ("F2", "Renommer"), ("F3", "Pochette"), ("F4", "Système"), ("F5", "Lancer"), ("F6", "Favori"),
          ("F7", "Ajouter"), ("F8", "Retirer"), ("F9", "Thème"), ("F10", "Quitter")]
    fkl = []
    for n, l in FK:
        a = tk.Label(fk, text=n); a.pack(side="left"); b = tk.Label(fk, text=l, anchor="w"); b.pack(side="left", fill="x", expand=True)
        fkl.append((a, b))
        for w in (a, b):
            w.bind("<Button-1>", lambda e, n=n: fkey(n))

    def paint():
        bg, pn, fg, acc, ft = T["bg"], T["panel"], T["fg"], T["acc"], T["font"]
        root.configure(bg=bg)
        for w in (top, emubar, bar, bar2, bar2b, mid, fk):
            w.configure(bg=bg)
        title.configure(bg=bg, fg=acc, font=(ft[0], 16, "bold"))
        for k, (f, l, b, s, o) in emu_lbl.items():
            f.configure(bg=pn); l.configure(bg=pn, fg=fg, font=(ft[0], 10))
            for x in (b, s, o):
                x.configure(bg=fg, fg=pn, activebackground=acc, font=(ft[0], 9, "bold"))
        for r in rbs:
            r.configure(bg=pn, fg=fg, selectcolor=T["sel"], activebackground=acc, font=(ft[0], 10))
        for b in btns:
            b.configure(bg=fg, fg=pn, activebackground=acc, font=(ft[0], 11, "bold"), pady=3)
        se.configure(bg=pn, fg=fg, insertbackground=fg, font=ft, relief="flat")
        cv.configure(bg=pn); logw.configure(bg=pn, fg=fg, font=("Consolas", 9))
        nort = cfg["theme"] == "norton"
        for a, b in fkl:
            a.configure(bg="#000000", fg="#ffffff", font=("Consolas", 9, "bold"))
            b.configure(bg="#00aaaa" if nort else pn, fg="#000000" if nort else fg, font=("Consolas", 9))
        render(); upd_emus()

    def upd_emus():
        for k, (f, l, b, s, o) in emu_lbl.items():
            ok = bool(emu_exe(k)); l.configure(text=f"{'✓' if ok else '✗'} {EMUS[k]['nom']} ({EMUS[k]['emu']})")
            b.configure(text="Réinstaller" if ok else "Installer"); o.configure(state="normal" if ok else "disabled")

    def visible():
        q = search.get().lower().strip(); out = []
        for it in lib:
            if filt.get() == "fav" and not it.get("fav"):
                continue
            if filt.get() == "recent" and not it.get("last"):
                continue
            if filt.get() in ("c64", "dos", "win98") and it["sys"] != filt.get():
                continue
            if q and q not in " ".join([it["title"], it.get("lic", ""), EMUS[it["sys"]]["nom"], it.get("year", ""), it.get("pub", ""),
                                        " ".join(it.get("tags", [])), it.get("notes", "")]).lower():
                continue
            out.append(it)
        if filt.get() == "recent":
            return sorted(out, key=lambda i: i.get("last", ""), reverse=True)
        if catv.get() not in ("", "Toutes catégories"):
            out = [i for i in out if catv.get() in i.get("tags", [])]
        return sorted(out, key=lambda i: (not i.get("fav"), i.get("order", 1e9), i["title"].lower()))

    def cover_img(it):
        from PIL import Image, ImageTk
        path = it.get("cover") if it.get("cover") and os.path.isfile(it.get("cover")) else None
        if not path:
            auto = os.path.join(P["covers"], f"auto_{it['id']}.png")
            sig = (it["title"], it["sys"])
            if os.path.isfile(auto) and auto_sig.get(it["id"]) in (None, sig):
                auto_sig[it["id"]] = sig; path = auto
            else:
                if it["id"] not in cover_jobs:
                    cover_jobs.add(it["id"]); snapshot = dict(it)
                    def job(sn=snapshot, sg=sig):
                        try:
                            make_cover(sn)
                        except Exception:
                            pass
                        def fin():
                            cover_jobs.discard(sn["id"]); auto_sig[sn["id"]] = sg; render_soon()
                        ui(fin)
                    threading.Thread(target=job, daemon=True).start()
                return None
        key = (path, os.path.getmtime(path), CW)
        if key not in imgs:
            im = Image.open(path).convert("RGB"); im = im.resize((CW, CH)); imgs[key] = ImageTk.PhotoImage(im)
        return imgs[key]

    hov = {"hl": None}
    def hover(hl, on):
        if on:
            if hov["hl"] != hl:
                if hov["hl"]:
                    cv.itemconfigure(hov["hl"], outline="")
                cv.itemconfigure(hl, outline=T["fg"]); hov["hl"] = hl
                if str(cv.cget("cursor")) != "hand2":
                    cv.configure(cursor="hand2")
        elif hov["hl"] == hl:
            cv.itemconfigure(hl, outline=""); hov["hl"] = None
            if str(cv.cget("cursor")) != "":
                cv.configure(cursor="")
    def fmt_t(sec):
        sec = int(sec or 0)
        return f"{sec // 3600} h {sec % 3600 // 60:02d}" if sec >= 3600 else f"{sec // 60} min"
    def render():
        global CW, CH
        CW, CH = (200, 254) if cfg.get("big") else (150, 190); SX, SY = CW + 22, CH + 62
        hov["hl"] = None; cv.delete("all"); w = max(cv.winfo_width(), 300); cols = max(1, (w - 10) // SX)
        catcb.configure(values=["Toutes catégories"] + all_tags())
        layout.clear()
        items = visible()
        if not items:
            msg = ("Bibliothèque vide.\n\nClique « 🎁 Pack de démarrage » pour 6 jeux gratuits et légaux (C64 + DOS),\n"
                   "ou « ▶ Ouvrir » pour lancer un émulateur vide.\n\nDépose tes jeux dans « 📁 Mes jeux » (scan automatique), ou glisse ici"
                   " tes disquettes .d64/.prg, jeux DOS .exe, images .img/.iso.\n\nou clique « + Ajouter ».\n"
                   "Aucun ROM ni système protégé n'est fourni.")
            cv.create_text(w // 2, 160, text=msg, fill=T["fg"], font=(T["font"][0], 12), justify="center"); msg = None
        if False:
            msg = ("Glisse ici tes disquettes .d64/.prg, jeux DOS .exe, images .img/.iso…\n\nou clique « + Ajouter ».\n"
                   "Aucun jeu ni ROM n'est fourni : utilise les tiens ou les sources légales.")
            cv.create_text(w // 2, 140, text=msg, fill=T["fg"], font=(T["font"][0], 12), justify="center")
        for i, it in enumerate(items):
            x = 10 + (i % cols) * SX; y = 10 + (i // cols) * SY; tag = f"it{it['id']}"; layout.append((x, y, it["id"]))
            if sel[0] == it["id"]:
                cv.create_rectangle(x - 4, y - 4, x + CW + 4, y + CH + 52, outline=T["acc"], width=3, tags=tag)
            img = None
            try:
                img = cover_img(it)
            except Exception:
                pass
            if img:
                cv.create_image(x + CW // 2, y + CH // 2, image=img, tags=tag)
            else:
                cv.create_rectangle(x, y, x + CW, y + CH, fill=EMUS[it["sys"]]["col"], tags=tag)
            cv.create_text(x + CW // 2, y + CH + 14, text=("★ " if it.get("fav") else "") + it["title"][:26], fill=T["fg"],
                           font=(T["font"][0], 10 if cfg.get("big") else 9, "bold"), tags=tag)
            sub = EMUS[it["sys"]]["nom"] + (f" · {fmt_t(it.get('time'))}" if it.get("time") else "") + (" · pack" if it.get("lic") else "")
            cv.create_text(x + CW // 2, y + CH + 30, text=sub, fill=T["acc"], font=("Consolas", 8), tags=tag)
            if it.get("last"):
                cv.create_text(x + CW // 2, y + CH + 43, text="joué " + it["last"], fill=T["fg"], font=("Consolas", 7), tags=tag)
            cv.tag_bind(tag, "<Button-1>", lambda e, i=it["id"]: (sel.__setitem__(0, i), drag.update(src=i, x=e.x, y=e.y), render()))
            tt = cv.create_text(x + CW // 2, y + CH + 14, text="", tags=(tag, f"ti{it['id']}"))
            cv.tag_bind(tag, "<Double-Button-1>", lambda e, i=it["id"]: launch(i))
            cv.tag_bind(tag, "<Button-3>", lambda e, i=it["id"]: ctx(e, i))
            hl = cv.create_rectangle(x - 2, y - 2, x + CW + 2, y + CH + 2, outline="", width=2, state="disabled")
            cv.tag_bind(tag, "<Enter>", lambda e, hl=hl: hover(hl, True))
            cv.tag_bind(tag, "<Leave>", lambda e, hl=hl: hover(hl, False))
        cv.configure(scrollregion=(0, 0, w, 20 + ((len(items) + cols - 1) // cols) * SY))
    cv.bind("<Configure>", lambda e: render_soon(120))
    cv.bind("<B1-Motion>", lambda e: drag_move(e)); cv.bind("<ButtonRelease-1>", lambda e: drag_drop(e))
    cv.bind_all("<MouseWheel>", lambda e: cv.yview_scroll(int(-e.delta / 120), "units"))

    def get(i):
        return next((x for x in lib if x["id"] == i), None)
    layout = []; drag = {}
    def drag_move(e):
        if not drag.get("src") or abs(e.x - drag["x"]) + abs(e.y - drag["y"]) < 12:
            return
        cv.delete("ghost"); cy = cv.canvasy(e.y)
        cv.create_rectangle(e.x - CW // 4, cy - CH // 4, e.x + CW // 4, cy + CH // 4, outline=T["acc"], dash=(4, 2), width=2, tags="ghost")
        drag["moved"] = True
    def drag_drop(e):
        cv.delete("ghost"); src = drag.pop("src", None)
        if not drag.pop("moved", False) or not src:
            return
        cy = cv.canvasy(e.y); tgt = None
        for x, y, i in layout:
            if x <= e.x <= x + CW + 20 and y <= cy <= y + CH + 60:
                tgt = i
        if not tgt or tgt == src:
            return
        snap(); order = [i for _, _, i in layout]; order.remove(src); order.insert(order.index(tgt), src)
        for n, i in enumerate(order):
            g = get(i)
            if g:
                g["order"] = n
        save_lib(lib); render(); log("Ordre modifié (glisser-déposer). Ctrl+Z pour annuler.")
    def rename_inline(i):
        it = get(i); bb = cv.bbox(f"ti{i}") or cv.bbox(f"it{i}")
        if not it or not bb:
            return
        en = tk.Entry(cv, font=(T["font"][0], 10, "bold"), justify="center"); en.insert(0, it["title"]); en.select_range(0, "end")
        win = cv.create_window((bb[0] + bb[2]) // 2, bb[1] + 4, window=en, width=CW)
        st = {"d": False}
        def done(save):
            if st["d"]:
                return
            st["d"] = True
            if save and en.get().strip() and en.get().strip() != it["title"]:
                snap(); it["title"] = en.get().strip(); save_lib(lib)
            cv.delete(win); en.destroy(); render()
        en.bind("<Return>", lambda e: done(True)); en.bind("<Escape>", lambda e: done(False)); en.bind("<FocusOut>", lambda e: done(True)); en.focus_set()
    def edit(i):
        it = get(i)
        if not it:
            return
        t2 = tk.Toplevel(root); t2.title(f"Modifier - {it['title']}"); t2.configure(bg=T["panel"]); t2.transient(root)
        fr = tk.Frame(t2, bg=T["panel"]); fr.pack(side="left", fill="both", padx=12, pady=10)
        vals = {}
        def row(r, lbl, key, w=None):
            tk.Label(fr, text=lbl, bg=T["panel"], fg=T["fg"], font=("Consolas", 10), anchor="e").grid(row=r, column=0, sticky="e", pady=3)
            if w is None:
                w = tk.Entry(fr, width=46); w.insert(0, str(it.get(key, "")))
            w.grid(row=r, column=1, sticky="w", pady=3, padx=6); vals[key] = w
        row(0, "Titre", "title"); row(1, "Année", "year"); row(2, "Éditeur", "pub")
        sv = tk.StringVar(value=it["sys"]); cb = ttk.Combobox(fr, textvariable=sv, values=list(EMUS), state="readonly", width=10); row(3, "Système", "sys", cb)
        tg = tk.Entry(fr, width=46); tg.insert(0, ", ".join(it.get("tags", []))); row(4, "Catégories / collections", "tags", tg)
        tk.Label(fr, text="(séparées par des virgules, ex. : Action, Mes classiques)", bg=T["panel"], fg=T["acc"], font=("Consolas", 8)).grid(row=5, column=1, sticky="w")
        row(6, "Fichier / dossier", "path"); row(7, "Arguments en plus", "args")
        nt = tk.Text(fr, width=46, height=6); nt.insert("1.0", it.get("notes", "")); row(8, "Notes", "notes", nt)
        right = tk.Frame(t2, bg=T["panel"]); right.pack(side="right", fill="y", padx=12, pady=10)
        cov = {"path": it.get("cover")}
        pl = tk.Label(right, bg=T["panel"], text="Pochette", fg=T["fg"]); pl.pack()
        def show_cov():
            try:
                from PIL import Image, ImageTk
                p = cov["path"] if cov["path"] and os.path.isfile(cov["path"]) else make_cover(it)
                im = Image.open(p).convert("RGB").resize((150, 190)); pl.img = ImageTk.PhotoImage(im); pl.configure(image=pl.img)
            except Exception as ex:
                pl.configure(text=f"(pochette : {ex})")
        def set_cov_file(f):
            f = f.strip().strip("{}").strip('"')
            if f and os.path.isfile(f):
                ensure_dir(P["covers"]); dst = os.path.join(P["covers"], it["id"] + "_" + str(int(time.time())) + os.path.splitext(f)[1].lower())
                shutil.copy2(f, dst); cov["path"] = dst; show_cov()
        def paste_cov():
            try:
                from PIL import ImageGrab
                g = ImageGrab.grabclipboard()
                if isinstance(g, list) and g:
                    return set_cov_file(g[0])
                if g is None:
                    return messagebox.showinfo(APP, "Le presse-papiers ne contient pas d'image.", parent=t2)
                ensure_dir(P["covers"]); dst = os.path.join(P["covers"], f"{it['id']}_{int(time.time())}.png"); g.save(dst); cov["path"] = dst; show_cov()
            except Exception as ex:
                messagebox.showwarning(APP, f"Coller impossible : {ex}", parent=t2)
        show_cov()
        for lbl, cmd in (("Choisir une image…", lambda: set_cov_file(filedialog.askopenfilename(parent=t2, filetypes=[("Images", "*.png *.jpg *.jpeg *.gif *.bmp *.webp")]) or "")),
                         ("Coller (Ctrl+V)", paste_cov), ("Pochette auto", lambda: (cov.update(path=None), show_cov()))):
            tk.Button(right, text=lbl, command=cmd, relief="flat", bg=T["fg"], fg=T["panel"]).pack(fill="x", pady=2)
        tk.Label(right, text="ou glisse une image\nsur la pochette", bg=T["panel"], fg=T["acc"], font=("Consolas", 8)).pack()
        t2.bind("<Control-v>", lambda e: paste_cov())
        if dnd_root:
            try:
                pl.drop_target_register(DND_FILES); pl.dnd_bind("<<Drop>>", lambda e: set_cov_file(root.tk.splitlist(e.data)[0]))
            except Exception:
                pass
        def save():
            if not vals["title"].get().strip():
                return messagebox.showwarning(APP, "Le titre ne peut pas être vide.", parent=t2)
            if not os.path.exists(vals["path"].get().strip()):
                if not messagebox.askyesno(APP, "Ce fichier/dossier n'existe pas. Enregistrer quand même ?", parent=t2):
                    return
            snap()
            for key in ("title", "year", "pub", "path", "args"):
                it[key] = vals[key].get().strip()
            it["sys"] = sv.get(); it["notes"] = nt.get("1.0", "end").strip()
            it["tags"] = [x.strip() for x in tg.get().split(",") if x.strip()]
            if cov["path"]:
                it["cover"] = cov["path"]
            else:
                it.pop("cover", None)
            save_lib(lib); imgs.clear(); render(); t2.destroy(); log(f"✎ {it['title']} modifié (Ctrl+Z pour annuler)")
        tk.Button(right, text="Enregistrer", command=save, relief="flat", bg=T["acc"], fg="#000000", padx=16).pack(side="bottom", fill="x", pady=(20, 2))
        tk.Button(right, text="Annuler", command=t2.destroy, relief="flat").pack(side="bottom", fill="x")
        t2.bind("<Escape>", lambda e: t2.destroy())
    def open_folder(i):
        it = get(i); d = it and (os.path.dirname(it["path"]) if os.path.isfile(it["path"]) else it["path"])
        if d and os.path.isdir(d):
            os.startfile(d)
        else:
            messagebox.showwarning(APP, f"Dossier introuvable :\n{d}", parent=root)
    def duplicate(i):
        it = get(i)
        if it:
            snap(); c = json.loads(json.dumps(it)); c["id"] = hashlib.md5((it["id"] + str(time.time())).encode()).hexdigest()[:10]
            c["title"] += " (copie)"; c.pop("time", None); c.pop("last", None); lib.append(c); save_lib(lib); render()

    def add_paths(paths, quiet=False, meta=None):
        n = 0; meta = meta or {}
        for p in paths:
            p = p.strip().strip("{}").strip('"')
            if not p or not os.path.exists(p):
                continue
            k = guess_system(p)
            if not k:
                log(f"Format non reconnu : {os.path.basename(p)}"); continue
            if any(os.path.normcase(x["path"]) == os.path.normcase(p) for x in lib):
                continue
            it = {"id": hashlib.md5((p + str(time.time())).encode()).hexdigest()[:10], "path": p, "sys": k,
                  "title": re.sub(r"[_\-]+", " ", os.path.splitext(os.path.basename(p.rstrip("\\/")))[0]).strip().title(),
                  "added": time.strftime("%Y-%m-%d")}
            mt = meta.get(p)
            if mt:
                it.update(title=mt["title"], sys=mt["sys"], lic=mt["lic"], src=mt["src"])
            elif os.path.basename(os.path.dirname(p)).lower() not in ("jeux", "mes jeux") and os.path.splitext(p)[1].lower() in (".exe", ".com", ".bat"):
                it["title"] = os.path.basename(os.path.dirname(p)).replace("_", " ").strip().title()
            if n == 0:
                snap()
            lib.append(it); n += 1
        save_lib(lib); render()
        if n or not quiet:
            log(f"{n} élément(s) ajouté(s) à la bibliothèque.")
        return n

    def add_files():
        fs = filedialog.askopenfilenames(parent=root, title="Ajouter des jeux / disquettes / images",
                                         filetypes=[("Rétro", " ".join("*" + e for k in EMUS for e in EMUS[k]["ext"])), ("Tous", "*.*")])
        add_paths(list(fs))
    def add_folder():
        d = filedialog.askdirectory(parent=root, title="Dossier d'un jeu DOS (sera monté en C:)")
        if d:
            add_paths([d])
    def new_vm():
        name = simpledialog.askstring(APP, "Nom de la machine Windows 98 :", parent=root, initialvalue="Win98")
        if not name:
            return
        vm = os.path.join(P["vms"], re.sub(r"[^\w\- ]", "_", name)); ensure_dir(vm)
        open(os.path.join(vm, "86box.cfg"), "a").close()
        it = {"id": hashlib.md5(vm.encode()).hexdigest()[:10], "path": vm, "sys": "win98", "title": name, "added": time.strftime("%Y-%m-%d")}
        if not any(x["path"] == vm for x in lib):
            lib.append(it); save_lib(lib)
        render()
        log("Machine créée. Au premier lancement, 86Box ouvre ses réglages : choisis la carte mère, puis insère TON CD/ISO "
            "Windows 98 (menu Média). Les ROMs BIOS se placent dans le dossier roms d'86Box.")
        exe = emu_exe("win98")
        if exe:
            subprocess.Popen([exe, "-P", vm, "-S"], cwd=vm)

    def one_at_a_time(go):
        """Une seule instance : propose de fermer proprement le jeu en cours avant d'en lancer un autre."""
        r = running()
        if not r:
            return go()
        t = r[0][2]
        if not messagebox.askyesno(APP, f"« {t} » est encore ouvert.\n\nLe fermer proprement (tes SAVE sont gardés) et lancer le nouveau ?", parent=root):
            return
        log(f"⏹ Fermeture de {t}…")
        def w():
            left = close_emus()
            ui(lambda: go() if not left else messagebox.showwarning(APP, f"« {left[0]} » ne se ferme pas.\nFerme-le avec Alt+Q (C64) ou la croix, puis réessaie.", parent=root))
        threading.Thread(target=w, daemon=True).start()

    def stop_game():
        if not running():
            log("⏹ Aucun jeu ouvert."); return
        log("⏹ Fermeture du jeu…")
        def w():
            left = close_emus()
            ui(lambda: log("⏹ Jeu fermé." if not left else f"⚠ {left[0]} ne répond pas : Alt+Q (C64) ou la croix."))
        threading.Thread(target=w, daemon=True).start()

    def quit_app():
        if running():
            log("⏹ Fermeture des jeux ouverts…"); root.update_idletasks()
            left = close_emus(8)
            if left and messagebox.askyesno(APP, f"« {left[0]} » ne se ferme pas tout seul.\nLe forcer à quitter ? (ce qui n'est pas enregistré sera perdu)", parent=root):
                kill_emus()
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", quit_app)

    def launch(i):
        it = get(i)
        if not it:
            return
        if running():
            return one_at_a_time(lambda: launch(i))
        try:
            floppy_sound(cfg.get("sound")); pulse(it["id"]); log(f"▶ Lancement de {it['title']}…"); toast(it["sys"], it["title"])
            def work():
                try:
                    cmd, cwd = launch_cmd(it); start_proc(cmd, cwd, it["sys"], it)
                    def ok():
                        it["plays"] = it.get("plays", 0) + 1; it["last"] = time.strftime("%Y-%m-%d %H:%M"); save_lib(lib); render_soon()
                        log(f"▶ {it['title']} ({EMUS[it['sys']]['emu']})")
                    ui(ok)
                except Exception as e:
                    ui(lambda e=e: (log(f"✗ {e}"), messagebox.showwarning(APP, str(e), parent=root)))
            root.after(2200, lambda: threading.Thread(target=work, daemon=True).start())
        except Exception as e:
            log(f"✗ {e}"); messagebox.showwarning(APP, str(e), parent=root)

    def pulse(i, n=0):
        cv.delete("pulse")
        if n < 8:
            bb = cv.bbox(f"it{i}")
            if bb and n % 2 == 0:
                cv.create_rectangle(bb[0] - 3, bb[1] - 3, bb[2] + 3, bb[3] + 3, outline=T["acc"], width=4, tags="pulse")
            root.after(120, lambda: pulse(i, n + 1))

    def start_proc(cmd, cwd, k, it=None):
        ensure_dir(P["logs"]); lf = os.path.join(P["logs"], f"emu_{k}.log")
        fo = open(lf, "w", encoding="utf-8", errors="replace"); fo.write(" ".join(cmd) + "\n\n"); fo.flush()
        try:
            pr = subprocess.Popen(cmd, cwd=cwd if cwd and os.path.isdir(cwd) else None, stdout=fo, stderr=subprocess.STDOUT)
        except OSError as ex:
            fo.close(); raise RuntimeError(f"{EMUS[k]['emu']} n'a pas pu démarrer : {ex}\nEssaie « Réinstaller ».")
        RUNNING.append((pr, k, (it or {}).get("title") or EMUS[k]["emu"]))
        def unpin_loop(n=0):
            if pr.poll() is None and n < 20:
                threading.Thread(target=unpin, args=(pr.pid,), daemon=True).start(); root.after(3000, lambda: unpin_loop(n + 1))
        ui(lambda: root.after(2000, unpin_loop))
        t0 = time.time()
        def wait():
            rc = pr.wait(); dur = time.time() - t0; fo.close()
            if it is not None and dur > 5:
                ui(lambda: (it.__setitem__("time", it.get("time", 0) + int(dur)), save_lib(lib), render_soon()))
            if rc not in (0, None) and dur < 3:
                tail = ""
                try:
                    tail = "".join(open(lf, encoding="utf-8", errors="replace").readlines()[-6:])[-600:]
                except Exception:
                    pass
                msg = (f"{EMUS[k]['emu']} s'est fermé tout de suite (code {rc}).\n\n"
                       + ("86Box : il manque probablement les ROMs de BIOS → bouton « ROMs 86Box ».\n\n" if k == "win98" else "")
                       + "Essaie : désactiver Plein écran / Filtre CRT dans ⚙ Options, puis « Réinstaller ».\n\n"
                       + f"Journal : {lf}\n{tail}")
                log(f"✗ {EMUS[k]['emu']} a planté (code {rc}) - voir {lf}")
                ui(lambda: messagebox.showerror(APP, msg, parent=root))
        threading.Thread(target=wait, daemon=True).start()
        return pr

    def open_emu(k):
        if running():
            return one_at_a_time(lambda: open_emu(k))
        floppy_sound(cfg.get("sound")); log(f"▶ Ouverture de {EMUS[k]['emu']}…"); toast(k, EMUS[k]["nom"])
        def work():
            try:
                cmd, cwd = open_cmd(k); start_proc(cmd, cwd, k); ui(lambda: log(f"▶ {EMUS[k]['emu']} ouvert"))
            except Exception as e:
                ui(lambda e=e: (log(f"✗ {e}"), messagebox.showwarning(APP, str(e), parent=root)))
        root.after(2200, lambda: threading.Thread(target=work, daemon=True).start())

    def toast(k, title):
        """Bandeau bien visible : comment sortir de l'émulateur (affiché avant le plein écran)."""
        try:
            tw = tk.Toplevel(root); tw.overrideredirect(True); tw.attributes("-topmost", True); tw.configure(bg="#000000")
            tk.Label(tw, text=f"▶  {title}", bg="#000000", fg="#ffff55", font=("Consolas", 16, "bold")).pack(padx=24, pady=(14, 2))
            tk.Label(tw, text="Pour sortir : " + EXIT_KEYS[k], bg="#000000", fg="#ffffff", font=("Consolas", 12), wraplength=root.winfo_screenwidth() - 120).pack(padx=24, pady=(0, 14))
            tw.update_idletasks(); x = (tw.winfo_screenwidth() - tw.winfo_reqwidth()) // 2; tw.geometry(f"+{max(0, x)}+40")
            root.after(4500, tw.destroy)
        except Exception:
            pass

    def busy(work, done_msg, after=None):
        def run():
            try:
                r = work(lambda v: ui(lambda: pbar.configure(value=v)))
                ui(lambda: (after(r) if after else None, log(done_msg)))
            except Exception as ex:
                ui(lambda ex=ex: log(f"⚠ {ex}")); ui(lambda ex=ex: messagebox.showwarning(APP, str(ex), parent=root))
            finally:
                ui(lambda: (pbar.configure(value=1.0), upd_emus()))
        pbar.configure(value=0); threading.Thread(target=run, daemon=True).start()

    def pack(ask=True, cats=None, after_cb=None):
        def go(sel_cats):
            def after(items):
                n = add_paths([g["path"] for g in items], meta={g["path"]: g for g in items}); filt.set("tout"); render()
                if ask:
                    messagebox.showinfo(APP, f"C'est prêt : {len(items)} jeu(x) téléchargé(s), {n} nouveau(x) dans ta bibliothèque.\n\n"
                                        "Pour jouer : double-clic sur une pochette.", parent=root)
                if after_cb:
                    after_cb()
            busy(lambda pr: install_pack(pr, sel_cats), "✓ Jeux gratuits téléchargés.", after)
        if not ask:
            return go(cats)
        t2 = tk.Toplevel(root); t2.title("Jeux gratuits et légaux"); t2.configure(bg=T["panel"]); t2.transient(root)
        tk.Label(t2, text="Coche ce que tu veux, puis clique « Télécharger ».", bg=T["panel"], fg=T["acc"], font=(T["font"][0], 13, "bold")).pack(anchor="w", padx=14, pady=(10, 4))
        vs = {}
        for c, lbl in PACK_CATS:
            vs[c] = tk.BooleanVar(value=True)
            tk.Checkbutton(t2, text=lbl, variable=vs[c], bg=T["panel"], fg=T["fg"], selectcolor=T["sel"], activebackground=T["panel"],
                           font=(T["font"][0], 12, "bold"), anchor="w").pack(fill="x", padx=14, pady=(6, 0))
            for g in PACK:
                if g["cat"] == c:
                    tk.Label(t2, text=f"      • {g['title']}  ({EMUS[g['sys']]['nom']}) - {g['lic']}", bg=T["panel"], fg=T["fg"],
                             font=("Consolas", 9), anchor="w").pack(fill="x", padx=14)
        tk.Label(t2, text="Tout vient de sources officielles (archive.org, scene.org). Aucun piratage, aucune ROM commerciale.\n"
                 "La licence et la source de chaque jeu sont dans le fichier SOURCE.txt de son dossier.", bg=T["panel"], fg=T["acc"],
                 font=("Consolas", 9), justify="left").pack(anchor="w", padx=14, pady=8)
        def ok():
            c = [k for k, v in vs.items() if v.get()]
            t2.destroy()
            if c:
                go(c)
        fb = tk.Frame(t2, bg=T["panel"]); fb.pack(pady=(0, 12))
        tk.Button(fb, text="⬇  Télécharger", command=ok, bg=T["acc"], fg="#000000", font=(T["font"][0], 12, "bold"), relief="flat", padx=18, pady=6).pack(side="left", padx=6)
        tk.Button(fb, text="Annuler", command=t2.destroy, font=(T["font"][0], 11), relief="flat", padx=12, pady=6).pack(side="left", padx=6)

    def scan(manual=False):
        def work():
            ensure_dir(P["jeux"]); found = scan_dir(P["jeux"])
            ui(lambda: done(found))
        def done(found):
            n = add_paths(found, quiet=not manual)
            if manual:
                messagebox.showinfo(APP, f"Scan de {P['jeux']} : {n} nouveau(x) jeu(x).\n\nDépose tes .d64/.prg/.t64 ou un dossier par jeu DOS dans ce dossier.", parent=root)
        threading.Thread(target=work, daemon=True).start()
    def _old_scan(manual=False):
        if manual:
            messagebox.showinfo(APP, f"Scan de {P['jeux']} : {n} nouveau(x) jeu(x).\n\nDépose tes .d64/.prg/.t64 ou un dossier par jeu DOS dans ce dossier.", parent=root)
    def open_jeux():
        ensure_dir(P["jeux"])
        if IS_WIN:
            os.startfile(P["jeux"])
    def roms86():
        if messagebox.askyesno(APP, "Télécharger les ROMs de BIOS depuis le dépôt OFFICIEL 86Box (github.com/86Box/roms) ?", parent=root):
            busy(install_roms_86box, "✓ ROMs 86Box prêtes.")
    def guide98():
        t2 = tk.Toplevel(root); t2.title("Guide Windows 98 (86Box)"); t2.configure(bg="#008080")
        tx = tk.Text(t2, width=96, height=30, bg="#c0c0c0", fg="#000000", font=("Consolas", 10), padx=12, pady=10, wrap="word")
        tx.insert("1.0", WIN98_GUIDE); tx.configure(state="disabled"); tx.pack(padx=10, pady=10, fill="both", expand=True)
    def do_backup():
        try:
            f = backup_lib(); log(f"💾 Sauvegarde : {f}"); messagebox.showinfo(APP, f"Bibliothèque sauvegardée :\n{f}", parent=root)
        except Exception as e:
            messagebox.showwarning(APP, f"Sauvegarde impossible : {e}", parent=root)
    def do_restore():
        f = filedialog.askopenfilename(parent=root, title="Restaurer une sauvegarde Rétro", initialdir=P["saves"], filetypes=[("Sauvegarde Rétro", "*.zip")])
        if not f:
            return
        try:
            snap(); restore_lib(f); lib[:] = load_lib(); imgs.clear(); auto_sig.clear(); render()
            log(f"Restauré : {f} ({len(lib)} titres). Ctrl+Z pour revenir en arrière.")
            messagebox.showinfo(APP, f"Bibliothèque restaurée : {len(lib)} titre(s).", parent=root)
        except Exception as e:
            messagebox.showwarning(APP, f"Restauration impossible : {e}", parent=root)
    def options():
        t2 = tk.Toplevel(root); t2.title("Options Rétro"); t2.configure(bg=T["panel"]); t2.transient(root); t2.grab_set()
        vs = {}
        for key, lbl in (("fullscreen", "Émulateurs en plein écran (VICE, DOSBox-X, machines 86Box)"), ("maximized", "Fenêtre Rétro maximisée"), ("crt", "Filtre CRT / écran télé (VICE, DOSBox-X)"),
                         ("pad", "Manette USB (C64 : port 2 ; DOS : joystick auto)"), ("big", "Grandes pochettes"),
                         ("sound", "Sons de disquette"), ("intro", "Écran READY. au démarrage")):
            vs[key] = tk.BooleanVar(value=bool(cfg.get(key)))
            tk.Checkbutton(t2, text=lbl, variable=vs[key], bg=T["panel"], fg=T["fg"], selectcolor=T["sel"], activebackground=T["panel"],
                           font=("Consolas", 10), anchor="w").pack(fill="x", padx=14, pady=2)
        kv = tk.StringVar(value=cfg.get("clavier", "cf")); fk = tk.Frame(t2, bg=T["panel"]); fk.pack(fill="x", padx=14, pady=(6, 0))
        tk.Label(fk, text="Clavier DOS :", bg=T["panel"], fg=T["fg"], font=("Consolas", 10)).pack(side="left")
        for val, lb in (("cf", "Canadien français"), ("us", "Américain (US)"), ("fr", "France (AZERTY)")):
            tk.Radiobutton(fk, text=lb, value=val, variable=kv, bg=T["panel"], fg=T["fg"], selectcolor=T["sel"], activebackground=T["panel"], font=("Consolas", 9)).pack(side="left", padx=4)
        bv = tk.StringVar(value=cfg.get("basic", "gw")); fb2 = tk.Frame(t2, bg=T["panel"]); fb2.pack(fill="x", padx=14, pady=(4, 0))
        tk.Label(fb2, text="BASIC DOS :", bg=T["panel"], fg=T["fg"], font=("Consolas", 10)).pack(side="left")
        for val, lb in (("gw", "GW-BASIC (le vrai, Microsoft MIT)"), ("bw", "bwBASIC (minuscules acceptées)")):
            tk.Radiobutton(fb2, text=lb, value=val, variable=bv, bg=T["panel"], fg=T["fg"], selectcolor=T["sel"], activebackground=T["panel"], font=("Consolas", 9)).pack(side="left", padx=4)
        tk.Label(t2, text="Chemins des émulateurs (vide = automatique)", bg=T["panel"], fg=T["acc"], font=("Consolas", 10, "bold")).pack(anchor="w", padx=14, pady=(10, 2))
        ev = {}
        for k in EMUS:
            f2 = tk.Frame(t2, bg=T["panel"]); f2.pack(fill="x", padx=14, pady=1)
            tk.Label(f2, text=EMUS[k]["emu"], width=9, anchor="w", bg=T["panel"], fg=T["fg"], font=("Consolas", 9)).pack(side="left")
            ev[k] = tk.StringVar(value=cfg.get("exe", {}).get(k, ""))
            tk.Entry(f2, textvariable=ev[k], width=48).pack(side="left", padx=4)
            tk.Button(f2, text="…", relief="flat", command=lambda k=k: ev[k].set(filedialog.askopenfilename(parent=t2, filetypes=[("Programme", "*.exe")]) or ev[k].get())).pack(side="left")
        tk.Label(t2, text="Manettes : VICE → menu Préférences > Périphériques d'entrée > Joystick ; DOSBox-X → Ctrl+F1 (mapper).",
                 bg=T["panel"], fg=T["acc"], font=("Consolas", 9), wraplength=420, justify="left").pack(padx=14, pady=8, anchor="w")
        def ok():
            for key, v in vs.items():
                cfg[key] = v.get()
            cfg["exe"] = {k: v.get().strip() for k, v in ev.items() if v.get().strip()}
            CUSTOM_EXE.clear(); CUSTOM_EXE.update(cfg["exe"])
            for k, v in cfg["exe"].items():
                if not os.path.isfile(v):
                    return messagebox.showwarning(APP, f"Chemin invalide pour {EMUS[k]['emu']} :\n{v}", parent=t2)
            cfg["clavier"] = kv.get(); OPTS["clavier"] = cfg["clavier"]; cfg["basic"] = bv.get(); OPTS["basic"] = cfg["basic"]
            OPTS.update({k_: cfg[k_] for k_ in ("fullscreen", "crt", "pad")}); save_cfg(); emu_exe_reset(); imgs.clear(); render(); upd_emus(); t2.destroy()
            log("⚙ Options enregistrées : plein écran " + ("oui" if cfg["fullscreen"] else "non") + ", CRT " + ("oui" if cfg["crt"] else "non")
                + ", manette " + ("oui" if cfg["pad"] else "non") + ".")
        tk.Button(t2, text="OK", command=ok, relief="flat", bg=T["fg"], fg=T["panel"], padx=20).pack(pady=10)

    def rename(i):
        it = get(i); n = simpledialog.askstring(APP, "Titre :", initialvalue=it["title"], parent=root) if it else None
        if n:
            snap(); it["title"] = n; save_lib(lib); render()
    def set_cover(i):
        it = get(i)
        if not it:
            return
        f = filedialog.askopenfilename(parent=root, title="Pochette", filetypes=[("Images", "*.png *.jpg *.jpeg *.gif *.bmp *.webp")])
        if f:
            ensure_dir(P["covers"]); dst = os.path.join(P["covers"], it["id"] + os.path.splitext(f)[1].lower())
            shutil.copy2(f, dst); it["cover"] = dst; save_lib(lib); render()
    def set_sys(i):
        it = get(i)
        if not it:
            return
        snap(); o = ["c64", "dos", "win98"]; it["sys"] = o[(o.index(it["sys"]) + 1) % 3]; it.pop("cover", None) if str(it.get("cover", "")).find("auto_") >= 0 else None
        save_lib(lib); render(); log(f"{it['title']} → {EMUS[it['sys']]['nom']}")
    def fav(i):
        it = get(i)
        if it:
            snap(); it["fav"] = not it.get("fav"); save_lib(lib); render()
    def remove(i):
        it = get(i)
        if it and messagebox.askyesno(APP, f"Retirer « {it['title']} » de la bibliothèque ?\n(Le fichier n'est PAS supprimé.)", parent=root):
            snap(); lib.remove(it); save_lib(lib); render()
    def ctx(e, i):
        sel[0] = i; render(); m = tk.Menu(root, tearoff=0)
        for lbl, f in (("▶ Lancer", launch), ("✎ Modifier la fiche…", edit), ("Renommer ici", rename_inline), ("Dupliquer", duplicate), ("Renommer…", rename), ("Pochette…", set_cover), ("Changer de système", set_sys),
                       ("★ Favori", fav), ("📤 Exporter…", export_dlg), ("Ouvrir le dossier", open_folder),
                       ("Retirer", remove)):
            m.add_command(label=lbl, command=lambda f=f: f(i))
        m.tk_popup(e.x_root, e.y_root)

    def install(k):
        emu_exe_reset()
        def work():
            try:
                install_emu(k, lambda v: ui(lambda: pbar.configure(value=v)))
            except Exception as ex:
                log(f"✖ {EMUS[k]['emu']} : {ex}")
            finally:
                ui(lambda: (pbar.configure(value=1.0), upd_emus()))
        if messagebox.askyesno(APP, f"Installer {EMUS[k]['emu']} depuis sa source officielle ?\n({EMUS[k]['site']})\n\nDossier : {emu_dir(k)}", parent=root):
            threading.Thread(target=work, daemon=True).start()

    def legal():
        top2 = tk.Toplevel(root); top2.title("Sources légales"); top2.configure(bg=T["panel"])
        tk.Label(top2, text="Sources légales (freeware, domaine public, homebrew, achat)", bg=T["panel"], fg=T["acc"],
                 font=(T["font"][0], 11, "bold")).pack(padx=12, pady=8, anchor="w")
        for lbl, url in LEGAL:
            l = tk.Label(top2, text="→ " + lbl, bg=T["panel"], fg=T["fg"], cursor="hand2", font=("Consolas", 10)); l.pack(anchor="w", padx=14)
            l.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))
        tk.Label(top2, text="Les ROMs Kernal/BIOS et Windows 98 restent les TIENNES (aucun n'est fourni).", bg=T["panel"], fg=T["fg"],
                 font=("Consolas", 9)).pack(padx=12, pady=10, anchor="w")

    def cycle_theme():
        o = ["c64", "dos", "norton"]; cfg["theme"] = o[(o.index(cfg.get("theme", "c64")) + 1) % 3]
        T.clear(); T.update(THEMES[cfg["theme"]]); save_cfg(); paint()

    def help_():
        t2 = tk.Toplevel(root); t2.title(f"Aide Rétro {VERSION}"); t2.configure(bg=T["panel"])
        tx = tk.Text(t2, width=96, height=34, bg=T["panel"], fg=T["fg"], font=("Consolas", 10), padx=14, pady=10, wrap="word", bd=0)
        tx.insert("1.0", f"""RÉTRO {VERSION} - AIDE

DÉMARRER EN 30 SECONDES
  1. « Installer » à côté de chaque émulateur (sources officielles).
  2. « ▶ Ouvrir » lance l'émulateur vide : C64 READY., invite DOS Z:\\>, gestionnaire 86Box.
  3. « 🎁 Pack de démarrage » : 6 jeux gratuits et légaux (C64 + DOS) ajoutés automatiquement.
  4. Double-clic sur une pochette = jouer. Clic droit = menu. Recherche : case à côté des filtres.

TES JEUX
  Dossier « Mes jeux » : {P['jeux']}
  Dépose-y tes .d64/.prg/.t64/.crt (C64), ou un sous-dossier par jeu DOS : Rétro les trouve au démarrage
  (ou « ↻ Scanner Mes jeux »). Tu peux aussi glisser-déposer dans la fenêtre ou « + Ajouter ».

TOUCHES
  Ctrl+E Modifier la fiche   Ctrl+Z Annuler   Glisser une pochette sur une autre = réordonner
  F1 Aide   F2 Renommer ici   F3 Pochette   F4 Système   F5 Lancer   F6 Favori
  F7 Ajouter   F8 Retirer   F9 Thème   F10 Quitter   Entrée = lancer

DANS LES ÉMULATEURS
  VICE (C64)  : Alt+Entrée plein écran, Alt+W turbo, F12 menu ; LOAD"*",8,1 puis RUN.
  DOSBox-X    : Alt+Entrée plein écran, Ctrl+F1 manettes/touches, Ctrl+F10 libérer la souris,
                F11+F5 = capture d'écran (Images\\Retro captures).
ATELIER DOS (1.4) : bouton « 💾 Atelier DOS » : menu en couleur, Volkov Commander (Norton), Dos Navigator,
  DOS Shell, EDIT, RUNBAS (lancer un .BAS), QB (compiler en .EXE, FreeBASIC), ZIP/UNZIP, 7ZA, ARJ, jeux libres.
  Tes programmes : C:\\MESPROGS. Tape MENU pour revenir au menu. Clavier : ⚙ Options (canadien français par défaut).
⌨ TAPER : retape un listing de magazine, Rétro vérifie chaque ligne (somme de contrôle) puis le lance.
  86Box       : Ctrl+Alt+PgDn plein écran, Ctrl+Fin libérer la souris.

OPTIONS (⚙) : plein écran, filtre CRT, manette USB, grandes pochettes, sons, écran READY.
RÉCENTS : « ⏱ Récents » trie par dernière partie ; le temps de jeu s'affiche sous chaque pochette.
SAUVEGARDE : « 💾 Sauvegarder » crée un zip daté (bibliothèque + pochettes) dans {P['saves']}.
WINDOWS 98 : « Guide Win98 » (ton propre CD/ISO requis, aucun OS fourni).
PROBLÈME ? Journaux dans {P['logs']} (emu_c64.log, emu_dos.log, emu_win98.log).
""")
        tx.configure(state="disabled"); tx.pack(fill="both", expand=True, padx=8, pady=8)
        t2.bind("<Escape>", lambda e: t2.destroy())
    def _old_help():
        messagebox.showinfo(APP, "Glisse tes fichiers dans la fenêtre (ou + Ajouter). Double-clic = lancer.\n"
                            "F1 Aide · F2 Renommer · F3 Pochette · F4 Système · F5 Lancer · F6 Favori\nF7 Ajouter · F8 Retirer · F9 Thème · F10 Quitter\n\n"
                            "C64 : VICE (autostart .d64/.prg/.t64/.crt)\nDOS : DOSBox-X (.exe, dossier, .img disquette, .iso CD)\n"
                            "Win98 : 86Box (machine + ton propre CD Windows 98 et ROMs)\n\nVoir LISEZMOI-RETRO.txt.", parent=root)
    def fkey(n):
        i = sel[0]
        acts = {"F1": help_, "F2": lambda: i and rename_inline(i), "F3": lambda: i and set_cover(i), "F4": lambda: i and set_sys(i),
                "F5": lambda: i and launch(i), "F6": lambda: i and fav(i), "F7": add_files, "F8": lambda: i and remove(i),
                "F9": cycle_theme, "F10": quit_app}
        acts[n]()
    for n, _ in FK:
        root.bind(f"<{n}>", lambda e, n=n: (fkey(n), "break")[1])
    root.bind("<Return>", lambda e: sel[0] and launch(sel[0]) if not isinstance(root.focus_get(), (tk.Entry, tk.Text)) else None)
    root.bind("<Control-e>", lambda e: sel[0] and edit(sel[0]))

    if dnd_root:
        try:
            cv.drop_target_register(DND_FILES)
            cv.dnd_bind("<<Drop>>", lambda e: add_paths(root.tk.splitlist(e.data)))
            root.drop_target_register(DND_FILES)
            root.dnd_bind("<<Drop>>", lambda e: add_paths(root.tk.splitlist(e.data)))
        except Exception as ex:
            log(f"Glisser-déposer indisponible ({ex}) : utilise + Ajouter.")
    else:
        log("Glisser-déposer : installe tkinterdnd2 (setup Padawan) — en attendant, + Ajouter.")

    def ui_selftest():
        shots = os.path.expanduser(r"~\retro_shots")
        def shot(n):
            subprocess.run(["powershell", "-NoProfile", "-File", r"C:\web_private\retro\tests\shot.ps1", os.path.join(shots, n)], creationflags=NOWIN)
        steps = []
        it0 = visible()[0] if visible() else None
        def s1():
            shot("10_ui_principal.png")
            if it0:
                sel[0] = it0["id"]; render(); edit(it0["id"])
        def s2():
            shot("11_ui_fiche.png")
            for w in root.winfo_children():
                if isinstance(w, tk.Toplevel):
                    w.destroy()
            if it0:
                old = it0["title"]; snap(); it0["title"] = "TEST CTRLZ"; save_lib(lib); render(); do_undo()
                log("Test Ctrl+Z : " + ("OK" if get(it0["id"])["title"] == old else "ÉCHEC"))
            options()
        def s3():
            shot("12_ui_options.png")
            for w in root.winfo_children():
                if isinstance(w, tk.Toplevel):
                    w.grab_release(); w.destroy()
            f = backup_lib(); log("Test sauvegarde : " + os.path.basename(f)); n0 = len(lib)
            restore_lib(f); lib[:] = load_lib(); render(); log(f"Test restauration : {'OK' if len(lib) == n0 else 'ÉCHEC'} ({len(lib)})")
            if len(layout) >= 2:
                a, b = layout[0], layout[1]; o0 = [i for _, _, i in layout]
                drag.update(src=b[2], x=0, y=0, moved=True)
                class E: pass
                e = E(); e.x = a[0] + 10; e.y = a[1] + 10 - cv.canvasy(0); drag_drop(e)
                log("Test glisser-déposer : " + ("OK" if [i for _, _, i in layout][0] == b[2] else "ÉCHEC")); do_undo()
                log("Test annuler l'ordre : " + ("OK" if [i for _, _, i in layout] == o0 else "ÉCHEC"))
            help_()
        def s4():
            shot("13_ui_aide.png")
            for w in root.winfo_children():
                if isinstance(w, tk.Toplevel):
                    w.destroy()
            shot("14_ui_journal.png")
        for n, f in enumerate((s1, s2, s3, s4)):
            root.after(n * 2500, f)
    lag = {"t": time.time(), "max": 0.0}
    def pump():
        now = time.time(); lag["max"] = max(lag["max"], now - lag["t"] - 0.05); lag["t"] = now
        t0 = time.time()
        while time.time() - t0 < 0.03:
            try:
                fn = UIQ.get_nowait()
            except queue.Empty:
                break
            root.after_idle(fn)  # jamais imbriqué dans pump (une boîte de dialogue ne bloque plus la file)
        try:
            while True:
                if not logw.winfo_exists():
                    return
                ln = LOGQ.get_nowait(); logw.configure(state="normal"); logw.insert("end", ln + "\n"); logw.see("end"); logw.configure(state="disabled")
        except queue.Empty:
            pass
        root.after(50, pump)
    def watchdog():
        import faulthandler
        warned = 0
        while True:
            time.sleep(0.5)
            d = time.time() - lag["t"]
            if d > 2 and time.time() - warned > 30:
                warned = time.time()
                try:
                    with open(os.path.join(P["logs"], "retro_gel.log"), "a", encoding="utf-8") as f:
                        f.write(time.strftime("%Y-%m-%d %H:%M:%S") + f" interface bloquée {d:.1f} s\n"); f.flush()
                        faulthandler.dump_traceback(file=f, all_threads=True)
                except Exception:
                    pass
    threading.Thread(target=watchdog, daemon=True).start()
    def lag_report():
        if "--lag-log" in sys.argv:
            open(os.path.join(P["logs"], "retro_lag.txt"), "w").write(f"{lag['max']*1000:.0f}")
    root.bind("<Destroy>", lambda e: lag_report() if e.widget is root else None, add="+")
    paint(); pump()
    try:
        scan(False)
    except Exception as ex:
        log(f"Scan Mes jeux : {ex}")
    if emu_exe("c64") and not any("Listings de magazines" in i.get("tags", []) for i in lib):
        root.after(1500, lambda: install_at())  # crée l'atelier et la collection « Listings de magazines » (une seule fois)
    if "--test-ui" in sys.argv:
        root.after(5000, lambda: ui_selftest())
    if "--test-pack" in sys.argv:
        root.after(500, lambda: pack(False))
    _inst = [EMUS[k]["emu"] for k in EMUS if emu_exe(k)]
    log(f"Rétro {VERSION} - {len(lib)} titre(s). Émulateurs installés : " + (", ".join(_inst) if _inst else "aucun (bouton « Installer »)")
        + (f". À installer : {', '.join(EMUS[k]['emu'] for k in EMUS if not emu_exe(k))}." if len(_inst) < len(EMUS) else ". Tout est prêt !"))
    # ---- moins de boutons : les outils avancés passent dans le menu
    for w in (bar2, bar2b):
        w.pack_forget()
    for b in list(bar.winfo_children()):
        if isinstance(b, tk.Button):
            b.pack_forget()
    for k, (f, l, b, s_, o) in emu_lbl.items():
        s_.pack_forget()
    big = tk.Button(bar, text="🎁 Jeux gratuits", relief="flat", padx=12, command=lambda: pack()); big.pack(side="right", padx=4); btns.append(big)
    addb = tk.Button(bar, text="+ Ajouter un jeu", relief="flat", padx=10, command=lambda: add_files()); addb.pack(side="right", padx=4); btns.append(addb)
    atb = tk.Button(bar, text="💾 Atelier DOS", relief="flat", padx=10, command=lambda: atelier_dos()); atb.pack(side="right", padx=4); btns.append(atb)
    imb = tk.Button(bar, text="📥 Importer", relief="flat", padx=8, command=lambda: import_dlg()); imb.pack(side="right", padx=4); btns.append(imb)
    tpb = tk.Button(bar, text="⌨ Taper", relief="flat", padx=8, command=lambda: type_mode()); tpb.pack(side="right", padx=4); btns.append(tpb)
    mb = tk.Menu(root); root.configure(menu=mb)
    m1 = tk.Menu(mb, tearoff=0); mb.add_cascade(label="Fichier", menu=m1)
    for lbl, cmd in (("Ajouter des jeux…", add_files), ("Ajouter un dossier de jeu DOS…", add_folder), ("Ouvrir le dossier « Mes jeux »", open_jeux),
                     ("Chercher les nouveaux jeux dans « Mes jeux »", lambda: scan(True)), (None, None),
                     ("Sauvegarder ma bibliothèque", do_backup), ("Restaurer une sauvegarde…", do_restore), (None, None), ("Quitter (F10)", quit_app)):
        m1.add_separator() if lbl is None else m1.add_command(label=lbl, command=cmd)
    m2 = tk.Menu(mb, tearoff=0); mb.add_cascade(label="Jeux gratuits", menu=m2)
    m2.add_command(label="Choisir et télécharger des jeux gratuits…", command=lambda: pack()); m2.add_command(label="Sources légales (sites)", command=lambda: legal())
    m3 = tk.Menu(mb, tearoff=0); mb.add_cascade(label="Réglages", menu=m3)
    for lbl, cmd in (("Options (plein écran, manette, écran télé)…", options), ("Changer le thème (F9)", cycle_theme), (None, None),
                     ("Windows 98 : créer une machine…", new_vm), ("Windows 98 : télécharger les ROMs 86Box", roms86), (None, None),
                     ("Assistant de bienvenue…", lambda: welcome())):
        m3.add_separator() if lbl is None else m3.add_command(label=lbl, command=cmd)
    for k in EMUS:
        m3.add_command(label=f"Site officiel de {EMUS[k]['emu']}", command=lambda u=EMUS[k]["site"]: webbrowser.open(u))
    m5 = tk.Menu(mb, tearoff=0); mb.insert_cascade(2, label="Atelier", menu=m5)
    for lbl, cmd in (("💾 Atelier DOS (menu, Norton, BASIC, outils)", lambda: atelier_dos()), ("⌨ Taper un listing comme dans le temps…", lambda: type_mode()),
                     ("Installer / compléter la boîte à outils DOS", lambda: install_toolbox()), ("Installer Pascal et C (≈150 Mo)…", lambda: install_dev()),
                     ("📥 Importer mes vieux trucs…", lambda: import_dlg()), ("Aide-mémoire et licences de l'atelier DOS", lambda: licences_dos()),
                     ("Ouvrir mes programmes DOS (C:\\MESPROGS)", lambda: open_dir(os.path.join(dos_root(), "MESPROGS"))), (None, None),
                     ("Programmer en BASIC C64 (disquette d'atelier)", lambda: atelier_c64()),
                     ("Coller un listing et le lancer sur C64…", lambda: paste_listing()), ("Mes programmes (explorateur)…", lambda: explorer()), (None, None),
                     ("Installer l'atelier et les « Listings de magazines »", lambda: install_at()), ("Magazines d'époque (archive.org)…", lambda: magazines()),
                     (None, None), ("Utiliser mon propre QBASIC.EXE…", lambda: set_qbasic()), ("Ouvrir mes sauvegardes de parties", lambda: open_dir(P["etats"]))):
        m5.add_separator() if lbl is None else m5.add_command(label=lbl, command=cmd)
    m3.add_separator(); m3.add_command(label="Tester ma manette…", command=lambda: pad_test())
    m3.add_command(label="Manette C64 : basculer port 1 / port 2", command=lambda: joy_toggle())
    m4 = tk.Menu(mb, tearoff=0); mb.add_cascade(label="Aide", menu=m4)
    m4.add_command(label="Aide (F1)", command=help_); m4.add_command(label="Guide Windows 98", command=guide98)
    for k, (f, l, b, s_, o) in emu_lbl.items():
        Tip(o, f"Ouvre {EMUS[k]['emu']} sans jeu ({ {'c64': 'écran bleu READY.', 'dos': 'invite DOS', 'win98': 'liste des machines'}[k] }).")
        Tip(b, f"Télécharge et installe {EMUS[k]['emu']} depuis son site officiel. Gratuit, aucun réglage.")
    Tip(atb, "Ton PC DOS d'époque : menu en couleur, Volkov Commander (Norton), EDIT, BASIC, ZIP… tout libre.")
    Tip(imb, "Importe tes vieux .BAS, .prg, .d64, .exe ou un zip : copiés, convertis, prêts à lancer.")
    Tip(tpb, "Retape un listing de magazine : Rétro vérifie chaque ligne, puis le lance dans DOS.")
    Tip(big, "Télécharge des jeux et démos gratuits et légaux, rangés par catégories."); Tip(addb, "Ajoute un jeu qui est déjà sur ton ordinateur.")
    Tip(se, "Tape quelques lettres pour trouver un jeu."); Tip(catcb, "Montre seulement une catégorie / collection.")
    for r in rbs:
        Tip(r, "Filtre la bibliothèque.")

    def open_dir(d):
        ensure_dir(d); os.startfile(d)
    def install_at(after=None):
        def done(items):
            for g in items:
                g["tags"] = ["Listings de magazines"]
            n = add_paths([g["path"] for g in items], meta={g["path"]: g for g in items})
            for it in lib:
                if any(os.path.normcase(it["path"]) == os.path.normcase(g["path"]) for g in items):
                    it.setdefault("tags", []); "Listings de magazines" in it["tags"] or it["tags"].append("Listings de magazines")
            save_lib(lib); render_soon()
            log(f"✓ Atelier prêt. {n} listing(s) ajouté(s) à la collection « Listings de magazines ».")
            if after:
                after()
        busy(install_atelier, "✓ Atelier installé.", done)
    def atelier_c64():
        exe = emu_exe("c64")
        if not exe:
            return messagebox.showwarning(APP, "Installe d'abord le Commodore 64 (bouton « Installer »).", parent=root)
        if not os.path.isfile(atelier_disk()):
            return install_at(atelier_c64)
        toast("c64", "BASIC C64 - disquette d'atelier en lecteur 8")
        log('Atelier C64 : tape LOAD"$",8 puis LIST pour voir la disquette ; SAVE"NOM",8 pour enregistrer ; LOAD"NOM",8 puis RUN.')
        root.after(2200, lambda: threading.Thread(target=lambda: start_proc([exe] + emu_opts("c64") + ["-8", atelier_disk()], P["etats"], "c64"), daemon=True).start())
    # ---------------------------------------------------------------- v1.4 : Atelier DOS + Taper comme dans le temps
    def dos_cmd_base(mount_d=None):
        exe = emu_exe("dos")
        if not exe:
            raise RuntimeError("Installe d'abord MS-DOS (bouton « Installer » à côté de MS-DOS).")
        cmd = [exe, "-fastlaunch"] + emu_opts("dos") + ["-set", "dosbox memsize=64", "-c", f'mount c "{dos_path(dos_root())}"']
        if mount_d:
            cmd += ["-c", f'mount d "{dos_path(mount_d)}"']
        return cmd + ["-c", r"set PATH=C:\BATCH;C:\FDOS\BIN;C:\GWBASIC;C:\FDOS\DEVEL\BWBASIC;%PATH%;C:\PERSO", "-c", r"set DOSDIR=C:\FDOS", "-c", r"set TEMP=C:\FDOS\TEMP",
                      "-c", r"set DJGPP=C:\FDOS\DEVEL\DJGPP\DJGPP.ENV"]
    def atelier_dos():
        if not emu_exe("dos"):
            return messagebox.showwarning(APP, "Installe d'abord MS-DOS (bouton « Installer »).", parent=root)
        if not toolbox_ok():
            return install_toolbox(atelier_dos)
        try:
            write_dos_files()
        except Exception as ex:
            log(f"⚠ Menu de l'atelier : {ex}")
        cmd = dos_cmd_base(P["listings"] and os.path.join(P["listings"], "dos")) + ["-c", "C:", "-c", r"call C:\ATELIER.BAT"]
        toast("dos", "💾 Atelier DOS - menu en couleur (tape MENU pour y revenir)")
        log("💾 Atelier DOS : C: = ton atelier (programmes dans C:\\MESPROGS), D: = listings de magazines. Tape MENU pour le menu.")
        root.after(2200, lambda: threading.Thread(target=lambda: start_proc(cmd, dos_root(), "dos"), daemon=True).start())
    def run_bas_dos(path, it=None):
        """Lance un .BAS dans DOSBox-X avec l'atelier (RUNBAS)."""
        if not toolbox_ok():
            return install_toolbox(lambda: run_bas_dos(path, it))
        d = os.path.dirname(path); name = os.path.splitext(os.path.basename(dos_path(path)))[0]
        bat = "RUNGW" if gw_ok() and (bas_tokenized(path) or cfg.get("basic", "gw") == "gw") else "RUNBAS"
        cmd = dos_cmd_base(d) + ["-c", "D:", "-c", f"call C:\\BATCH\\{bat}.BAT {name}"]
        toast("dos", f"BASIC : {os.path.basename(path)}")
        root.after(2200, lambda: threading.Thread(target=lambda: start_proc(cmd, d, "dos", it), daemon=True).start())
    def install_toolbox(after=None):
        if not messagebox.askyesno(APP, "Installer la boîte à outils DOS « comme dans le temps » ?\n\n"
                                   "Volkov Commander (style Norton), Dos Navigator, DOS Shell, EDIT, ZIP/UNZIP, 7-Zip, ARJ,\n"
                                   "BASIC (bwBASIC) et compilateur compatible QuickBASIC (FreeBASIC), art ANSI, jeux libres…\n\n"
                                   "Tout est libre et légal (dépôts FreeDOS). Environ 60 Mo à télécharger, une seule fois.", parent=root):
            return
        def done(got):
            log(f"✓ Boîte à outils DOS prête ({len(got)} outil(s) ajouté(s)). Bouton « 💾 Atelier DOS ».")
            if after:
                after()
        busy(install_dos_toolbox, "✓ Atelier DOS installé.", done)
    def install_dev():
        if not messagebox.askyesno(APP, "Installer Pascal et C dans l'Atelier DOS ?\n\n"
                                   "• Free Pascal 3.2.2 + IDE plein écran fp (façon Turbo Pascal), unités CRT/GRAPH\n"
                                   "• DJGPP + GCC 12 + RHIDE (façon Turbo C) + Allegro 4\n\n"
                                   "Tout est libre (GPL). Environ 150 Mo à télécharger, ≈ 200 Mo sur le disque.", parent=root):
            return
        if not toolbox_ok():
            return messagebox.showinfo(APP, "Installe d'abord la boîte à outils DOS (bouton « 💾 Atelier DOS »).", parent=root)
        busy(lambda pr: install_dos_toolbox(pr, dev=True), "✓ Pascal et C installés : menu de l'atelier, touches P et C.",
             lambda got: log(f"✓ {len(got)} paquet(s) ajouté(s) : " + ", ".join(got)))
    def licences_dos():
        p = os.path.join(dos_root(), "AIDE.TXT")
        if not os.path.isfile(p):
            write_dos_files()
        os.startfile(p)

    def import_dlg(paths=None):
        """📥 Importer mes vieux trucs : dossier, fichiers, zip ou glisser-déposer. Copie, jamais de déplacement."""
        def go(ps):
            if not ps:
                return
            def done(items):
                meta = {g["path"]: dict(title=g["title"], sys=g["sys"], lic="À toi", src="") for g in items}
                n = add_paths([g["path"] for g in items], quiet=True, meta=meta)
                for g in items:
                    for it in lib:
                        if os.path.normcase(it["path"]) == os.path.normcase(g["path"]):
                            it["notes"] = g["notes"]; it.setdefault("tags", [])
                            "Mes vieux trucs" in it["tags"] or it["tags"].append("Mes vieux trucs")
                            for k_ in ("basic", "src_txt"):
                                if g.get(k_):
                                    it[k_] = g[k_]
                save_lib(lib); render_soon()
                messagebox.showinfo(APP, f"📥 {len(items)} fichier(s) importé(s) ({n} nouveau(x) dans la bibliothèque, collection « Mes vieux trucs »).\n\n"
                                    f"Copies rangées dans :\n{os.path.join(P['atelier'], 'mes_programmes')}\n(logiciels .EXE/.COM : C:\\PERSO de l'atelier, privé)\n\n"
                                    "Tes originaux n'ont pas bougé.\nDouble-clic = lancer · clic droit → ✎ Modifier la fiche (titre, notes) · 📤 Exporter.", parent=root)
            busy(lambda pr: import_sources(ps), "✓ Import terminé.", done)
        if paths:
            return go(paths)
        t2 = tk.Toplevel(root); t2.title("📥 Importer mes vieux trucs"); t2.configure(bg=T["panel"]); t2.transient(root)
        tk.Label(t2, text="Tes vieux programmes : .BAS (texte ou GW-BASIC binaire), .prg, .d64, .t64, .com/.exe DOS,\n"
                 ".txt de listings, ou un .zip qui en contient. Rétro les COPIE (tes originaux ne bougent pas),\n"
                 "corrige l'encodage et les fins de ligne, et devine C64 ou DOS.\n"
                 "Tes logiciels d'époque (.EXE/.COM, ex. QB45) vont dans C:\\PERSO : privé, jamais distribué.",
                 bg=T["panel"], fg=T["fg"], font=("Consolas", 10), justify="left").pack(padx=14, pady=10)
        fb = tk.Frame(t2, bg=T["panel"]); fb.pack(pady=(0, 12))
        def pick_dir():
            d = filedialog.askdirectory(parent=t2, title="Dossier de mes vieux trucs")
            if d:
                t2.destroy(); go([d])
        def pick_files():
            fs = filedialog.askopenfilenames(parent=t2, title="Fichiers ou zip", filetypes=[("Vieux trucs", " ".join("*" + e for e in IMPORT_EXT)), ("Tous", "*.*")])
            if fs:
                t2.destroy(); go(list(fs))
        tk.Button(fb, text="📁 Un dossier…", command=pick_dir, relief="flat", bg=T["acc"], fg="#000000", font=("Consolas", 11, "bold"), padx=12).pack(side="left", padx=6)
        tk.Button(fb, text="📄 Des fichiers ou un .zip…", command=pick_files, relief="flat", bg=T["acc"], fg="#000000", font=("Consolas", 11, "bold"), padx=12).pack(side="left", padx=6)
        if dnd_root:
            dz = tk.Label(t2, text="… ou glisse-les ici", bg=T["sel"], fg=T["fg"], font=("Consolas", 11), height=3)
            dz.pack(fill="x", padx=14, pady=(0, 12))
            try:
                dz.drop_target_register(DND_FILES); dz.dnd_bind("<<Drop>>", lambda e: (t2.destroy(), go(list(root.tk.splitlist(e.data)))))
            except Exception:
                pass
    def export_dlg(i):
        it = get(i)
        if not it:
            return
        t2 = tk.Toplevel(root); t2.title("📤 Exporter " + it["title"]); t2.configure(bg=T["panel"]); t2.transient(root)
        tk.Label(t2, text=f"Exporter « {it['title']} » en :", bg=T["panel"], fg=T["fg"], font=("Consolas", 11, "bold")).pack(padx=14, pady=10)
        def do(fmt):
            nm = ascii_name(it["title"]).replace(" ", "_")[:24] or "programme"
            ext = {"zip": ".zip", "bas": ".bas", "prg": ".prg", "d64": ".d64"}[fmt]
            dest = filedialog.asksaveasfilename(parent=t2, initialfile=nm + ext, defaultextension=ext, filetypes=[(fmt.upper(), "*" + ext)])
            if not dest:
                return
            try:
                export_item(it, fmt, dest); t2.destroy(); log(f"📤 Exporté : {dest}")
                messagebox.showinfo(APP, f"Exporté :\n{dest}", parent=root)
            except Exception as ex:
                messagebox.showwarning(APP, str(ex), parent=t2)
        for fmt, lb in (("zip", "📦 .zip (fichier + fiche)"), ("bas", "📝 .bas texte (listing)"), ("prg", "💾 .prg (Commodore 64)"), ("d64", "💿 .d64 (disquette C64)")):
            tk.Button(t2, text=lb, command=lambda f=fmt: do(f), relief="flat", font=("Consolas", 11), width=30).pack(padx=14, pady=3)
    def type_mode(start=None):
        """⌨ Taper comme dans le temps : le listing du magazine à gauche, tu le retapes à droite, Rétro vérifie chaque ligne."""
        srcs = []
        for dd in (os.path.join(P["listings"], "dos"), os.path.join(dos_root(), "MESPROGS")):
            if os.path.isdir(dd):
                srcs += [os.path.join(dd, f) for f in sorted(os.listdir(dd)) if f.upper().endswith(".BAS")]
        if not srcs:
            return messagebox.showinfo(APP, "Aucun listing trouvé. Menu Atelier → « Installer l'atelier et les Listings de magazines ».", parent=root)
        titles = {}
        for f in os.listdir(P["listings"]) if os.path.isdir(P["listings"]) else []:
            if f.endswith("_SOURCE.txt"):
                t = open(os.path.join(P["listings"], f), encoding="utf-8", errors="replace").readline().strip()
                titles[(ascii_name(t).replace(" ", "_")[:8].upper() + ".BAS")] = t
        names = [f"{titles.get(os.path.basename(s).upper(), os.path.basename(s))}  [{os.path.basename(s)}]" for s in srcs]
        t2 = tk.Toplevel(root); t2.title("⌨ Taper comme dans le temps - Rétro"); t2.configure(bg="#1b1b1b")
        try:
            t2.state("zoomed")
        except Exception:
            t2.geometry("1000x560")
        top = tk.Frame(t2, bg="#1b1b1b"); top.pack(fill="x", padx=8, pady=4)
        tk.Label(top, text="Listing :", bg="#1b1b1b", fg="#ffff55", font=("Consolas", 11, "bold")).pack(side="left")
        cv = tk.StringVar(); cb = ttk.Combobox(top, textvariable=cv, values=names, state="readonly", width=48); cb.pack(side="left", padx=6)
        stat = tk.Label(top, text="", bg="#1b1b1b", fg="#55ff55", font=("Consolas", 11)); stat.pack(side="right")
        pw = tk.PanedWindow(t2, orient="horizontal", bg="#1b1b1b", sashwidth=6); pw.pack(fill="both", expand=True, padx=8)
        lf = tk.Frame(pw, bg="#f3ead3"); rf = tk.Frame(pw, bg="#0000aa"); pw.add(lf, stretch="always"); pw.add(rf, stretch="always")
        tk.Label(lf, text="LE MAGAZINE", bg="#f3ead3", fg="#7a1f1f", font=("Georgia", 12, "bold")).pack(anchor="w", padx=10)
        mag = tk.Text(lf, bg="#f3ead3", fg="#202020", font=("Courier New", 11), wrap="none", bd=0, padx=10)
        mag.pack(fill="both", expand=True)
        tk.Label(rf, text="TON CLAVIER  (Entrée = ligne vérifiée ; F5 = tout vérifier)", bg="#0000aa", fg="#ffffff", font=("Consolas", 11, "bold")).pack(anchor="w", padx=8)
        ed = tk.Text(rf, bg="#0000aa", fg="#ffffff", insertbackground="#ffff55", insertwidth=3, font=("Consolas", 12), wrap="none", bd=0, padx=8, undo=True)
        ed.pack(fill="both", expand=True)
        mag.tag_configure("cur", background="#ffe08a"); mag.tag_configure("ok", foreground="#1d7a1d"); mag.tag_configure("sum", foreground="#a05a00")
        ed.tag_configure("bad", background="#aa0000"); ed.tag_configure("good", foreground="#55ff55")
        st = {"lines": [], "file": None, "t0": None}
        def norm(s):
            return re.sub(r"\s+", "", s).upper()
        def csum(s):  # somme de contrôle « à la Compute! » : 2 caractères par ligne
            return f"{sum(ord(c) for c in norm(s)) % 256:02X}"
        def load(*_):
            i = cb.current()
            if i < 0:
                return
            f = srcs[i]; st["file"] = f
            st["lines"] = [l.rstrip() for l in open(f, encoding="ascii", errors="replace").read().replace("\r", "").split("\n") if l.strip()]
            mag.configure(state="normal"); mag.delete("1.0", "end")
            title = names[i].split("  [")[0]
            mag.insert("end", f"{title.upper()}\nTiré de « BASIC Computer Games » - Creative Computing\n" + "─" * 52 + "\n")
            for l in st["lines"]:
                mag.insert("end", f"{csum(l)} ", "sum"); mag.insert("end", l + "\n")
            mag.configure(state="disabled"); ed.delete("1.0", "end"); st["t0"] = None; check(False); ed.focus_set()
        def check(full=True):
            typed = [l for l in ed.get("1.0", "end").replace("\r", "").split("\n")]
            ed.tag_remove("bad", "1.0", "end"); ed.tag_remove("good", "1.0", "end"); mag.tag_remove("cur", "1.0", "end"); mag.tag_remove("ok", "1.0", "end")
            good = bad = 0; first_bad = None; n = 0
            for k, l in enumerate(typed):
                if not l.strip():
                    continue
                if n >= len(st["lines"]):
                    break
                last = (k == len(typed) - 1 or not any(x.strip() for x in typed[k + 1:]))
                if norm(l) == norm(st["lines"][n]):
                    good += 1; ed.tag_add("good", f"{k+1}.0", f"{k+1}.end"); mag.tag_add("ok", f"{n+4}.0", f"{n+4}.end")
                elif full or not last:
                    bad += 1; ed.tag_add("bad", f"{k+1}.0", f"{k+1}.end"); first_bad = first_bad or (k + 1, st["lines"][n])
                n += 1
            if n < len(st["lines"]):
                mag.tag_add("cur", f"{n+4}.0", f"{n+4}.end"); mag.see(f"{n+4}.0")
            el = (time.time() - st["t0"]) if st["t0"] else 0
            cpm = int(sum(len(norm(x)) for x in typed) / (el / 60)) if el > 10 else 0
            stat.configure(text=f"Lignes {good}/{len(st['lines'])}  ·  erreurs {bad}  ·  {cpm} car./min", fg="#ff5555" if bad else "#55ff55")
            if full and first_bad:
                messagebox.showinfo(APP, f"Erreur à la ligne {first_bad[0]} de ton texte.\n\nLe magazine dit :\n{first_bad[1]}", parent=t2)
            elif full and good == len(st["lines"]):
                messagebox.showinfo(APP, "BRAVO ! Le listing est complet et sans faute, comme un vrai pro de 1983.\nClique « ▶ Lancer dans DOS ».", parent=t2)
        def key(e):
            if st["t0"] is None:
                st["t0"] = time.time()
            if e.keysym == "Return":
                t2.after(10, lambda: check(False))
        ed.bind("<Key>", key); t2.bind("<F5>", lambda e: check(True)); cb.bind("<<ComboboxSelected>>", load)
        def save(run=False):
            code = ed.get("1.0", "end").strip()
            if not code:
                return messagebox.showinfo(APP, "Tape d'abord quelques lignes !", parent=t2)
            base = os.path.splitext(os.path.basename(st["file"] or "TAPE.BAS"))[0][:6].upper() + "_T"
            ensure_dir(os.path.join(dos_root(), "MESPROGS")); out = os.path.join(dos_root(), "MESPROGS", base + ".BAS")
            open(out, "w", encoding="ascii", errors="replace", newline="\r\n").write(bw_fix(code.upper()) + "\n")
            log(f"⌨ Enregistré : {out}")
            if run:
                run_bas_dos(out)
            else:
                messagebox.showinfo(APP, f"Enregistré dans ton atelier :\n{out}\n\n(Dans DOS : C:\\MESPROGS\\{base}.BAS)", parent=t2)
        bb = tk.Frame(t2, bg="#1b1b1b"); bb.pack(fill="x", padx=8, pady=6)
        for lbl, cmd_, col in (("✔ Vérifier (F5)", lambda: check(True), "#ffff55"), ("💾 Enregistrer", lambda: save(False), "#55ffff"),
                               ("▶ Lancer dans DOS", lambda: save(True), "#55ff55"), ("Fermer", t2.destroy, "#cccccc")):
            tk.Button(bb, text=lbl, command=cmd_, bg=col, fg="#000000", relief="flat", font=("Consolas", 11, "bold"), padx=12).pack(side="left", padx=4)
        tk.Label(bb, text="Les petits codes orange à gauche = somme de contrôle de chaque ligne, comme dans Compute!", bg="#1b1b1b", fg="#aaaaaa",
                 font=("Consolas", 9)).pack(side="right")
        k0 = 0
        for k, s in enumerate(srcs):
            if (start and os.path.normcase(s) == os.path.normcase(start)) or (not start and "HI-LO" in s.upper()):
                k0 = k
        cb.current(k0); load()
    def set_qbasic():
        f = filedialog.askopenfilename(parent=root, title="Où est TON QBASIC.EXE ?", filetypes=[("QBASIC", "QBASIC.EXE"), ("Programme", "*.exe")])
        if f:
            cfg["qbasic"] = f; save_cfg(); log(f"QBASIC personnel : {f}")
    def joy_toggle():
        cfg["joyport"] = 1 if cfg.get("joyport", 2) == 2 else 2; OPTS["joyport"] = cfg["joyport"]; save_cfg()
        messagebox.showinfo(APP, f"La manette est maintenant branchée sur le PORT {cfg['joyport']} du Commodore 64.\n"
                            "(La plupart des jeux utilisent le port 2. Si ton personnage ne bouge pas, change de port.)", parent=root)
    def paste_listing():
        t2 = tk.Toplevel(root); t2.title("Coller un listing BASIC (C64)"); t2.configure(bg=T["panel"]); t2.transient(root)
        tk.Label(t2, text="Colle ici un listing BASIC (même d'un magazine : les sommes de contrôle et les codes {CLR}, {DOWN}… sont gérés).",
                 bg=T["panel"], fg=T["acc"], font=("Consolas", 10), wraplength=700, justify="left").pack(anchor="w", padx=12, pady=8)
        tx = tk.Text(t2, width=90, height=22, font=("Consolas", 10)); tx.pack(padx=12, fill="both", expand=True)
        try:
            tx.insert("1.0", root.clipboard_get())
        except Exception:
            pass
        nm = tk.StringVar(value="colle"); fb = tk.Frame(t2, bg=T["panel"]); fb.pack(fill="x", padx=12, pady=8)
        tk.Label(fb, text="Nom :", bg=T["panel"], fg=T["fg"]).pack(side="left"); tk.Entry(fb, textvariable=nm, width=16).pack(side="left", padx=4)
        def go():
            code = tx.get("1.0", "end"); name = re.sub(r"[^a-z0-9]", "", nm.get().lower())[:16] or "colle"
            def work():
                try:
                    out = os.path.join(P["atelier"], "c64", name + ".prg"); ensure_dir(os.path.dirname(out))
                    prg, n = petcat_prg(code, out)
                    if os.path.isfile(atelier_disk()):
                        c1541("-attach", atelier_disk(), "-delete", name); c1541("-attach", atelier_disk(), "-write", prg, name)
                    exe = emu_exe("c64"); ui(lambda: (t2.destroy(), toast("c64", f"{name} ({n} lignes)")))
                    time.sleep(2.2); start_proc([exe] + emu_opts("c64") + (["-8", atelier_disk()] if os.path.isfile(atelier_disk()) else []) + ["-autostart", prg], P["etats"], "c64")
                    ui(lambda: log(f"✓ Listing « {name} » converti ({n} lignes), enregistré sur la disquette d'atelier et lancé."))
                except Exception as ex:
                    ui(lambda ex=ex: messagebox.showwarning(APP, f"Je n'ai pas pu convertir ce listing :\n{ex}", parent=t2))
            threading.Thread(target=work, daemon=True).start()
        tk.Button(fb, text="▶ Convertir et lancer", command=go, bg=T["acc"], fg="#000000", font=(T["font"][0], 11, "bold"), relief="flat", padx=12).pack(side="right")
    def explorer():
        t2 = tk.Toplevel(root); t2.title("Mes programmes (atelier)"); t2.configure(bg=T["panel"]); t2.transient(root)
        lb = tk.Listbox(t2, width=60, height=18, font=("Consolas", 11)); lb.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        rows = []
        def refresh():
            def work():
                f = atelier_files(); ui(lambda: fill(f))
            threading.Thread(target=work, daemon=True).start()
        def fill(f):
            rows[:] = [r for r in f if r[2].lower() != "01"]; lb.delete(0, "end")
            for sy, n, ty, sz in rows:
                lb.insert("end", f"{'C64 disquette' if sy == 'c64' else 'DOS C:\\'}   {n.strip():<18} {ty}")
        def cur():
            i = lb.curselection(); return rows[i[0]] if i else None
        def ren():
            r = cur()
            if not r:
                return
            new = simpledialog.askstring(APP, "Nouveau nom :", initialvalue=r[1].strip(), parent=t2)
            if not new:
                return
            if r[0] == "c64":
                c1541("-attach", atelier_disk(), "-rename", r[1].strip(), new.lower()[:16])
            else:
                os.rename(os.path.join(P["atelier"], "dos", r[1]), os.path.join(P["atelier"], "dos", new.upper()))
            refresh()
        def export():
            r = cur()
            if not r:
                return
            dst = filedialog.askdirectory(parent=t2, title="Exporter vers…")
            if not dst:
                return
            if r[0] == "c64":
                c1541("-attach", atelier_disk(), "-read", r[1].strip(), os.path.join(dst, r[1].strip() + ".prg"))
            else:
                shutil.copy2(os.path.join(P["atelier"], "dos", r[1]), dst)
            log(f"Exporté : {r[1].strip()} → {dst}")
        def run_():
            r = cur()
            if not r:
                return
            if r[0] == "c64":
                tmp = os.path.join(P["dl"], "atelier_" + re.sub(r"\W", "_", r[1].strip()) + ".prg")
                c1541("-attach", atelier_disk(), "-read", r[1].strip(), tmp)
                it = {"sys": "c64", "path": tmp, "title": r[1].strip()}
            else:
                it = {"sys": "dos", "path": os.path.join(P["atelier"], "dos", r[1]), "title": r[1]}
            try:
                cmd, cwd = launch_cmd(it); toast(it["sys"], it["title"])
                root.after(2200, lambda: threading.Thread(target=lambda: start_proc(cmd, cwd, it["sys"]), daemon=True).start())
            except Exception as ex:
                messagebox.showwarning(APP, str(ex), parent=t2)
        side = tk.Frame(t2, bg=T["panel"]); side.pack(side="right", fill="y", padx=10, pady=10)
        for lbl, cmd in (("▶ Lancer", run_), ("Renommer", ren), ("Exporter…", export), ("Rafraîchir", refresh),
                         ("Dossier DOS", lambda: open_dir(os.path.join(P["atelier"], "dos"))), ("Dossier C64", lambda: open_dir(os.path.join(P["atelier"], "c64")))):
            tk.Button(side, text=lbl, command=cmd, relief="flat", bg=T["fg"], fg=T["panel"], font=(T["font"][0], 11, "bold"), width=14).pack(pady=3)
        lb.bind("<Double-Button-1>", lambda e: run_()); refresh()
    def magazines():
        t2 = tk.Toplevel(root); t2.title("Magazines d'époque"); t2.configure(bg=T["panel"])
        tk.Label(t2, text="Les magazines sont consultables gratuitement sur archive.org (liens, pas de copies) :", bg=T["panel"], fg=T["acc"],
                 font=("Consolas", 11, "bold")).pack(anchor="w", padx=12, pady=8)
        for n, u in MAGAZINES:
            b = tk.Button(t2, text="📖  " + n, command=lambda u=u: webbrowser.open(u), relief="flat", bg=T["fg"], fg=T["panel"], font=(T["font"][0], 11, "bold"), anchor="w")
            b.pack(fill="x", padx=12, pady=2)
        tk.Label(t2, text="Astuce : un listing trouvé dans un magazine se colle dans Atelier → « Coller un listing ».", bg=T["panel"], fg=T["fg"],
                 font=("Consolas", 9)).pack(padx=12, pady=10)
    def pad_test():
        import ctypes
        class XS(ctypes.Structure):
            _fields_ = [("pkt", ctypes.c_uint), ("btn", ctypes.c_ushort), ("lt", ctypes.c_ubyte), ("rt", ctypes.c_ubyte),
                        ("lx", ctypes.c_short), ("ly", ctypes.c_short), ("rx", ctypes.c_short), ("ry", ctypes.c_short)]
        xi = None
        for dll in ("xinput1_4", "xinput1_3", "xinput9_1_0"):
            try:
                xi = getattr(ctypes.windll, dll); break
            except Exception:
                pass
        t2 = tk.Toplevel(root); t2.title("Tester ma manette"); t2.configure(bg="#000000"); t2.transient(root)
        lab = tk.Label(t2, text="", bg="#000000", fg="#55ff55", font=("Consolas", 16, "bold"), justify="left", width=40, height=9); lab.pack(padx=20, pady=20)
        NAMES = [(0x1000, "A"), (0x2000, "B"), (0x4000, "X"), (0x8000, "Y"), (0x0100, "LB"), (0x0200, "RB"), (0x0010, "START"), (0x0020, "BACK"),
                 (0x0001, "↑"), (0x0002, "↓"), (0x0004, "←"), (0x0008, "→")]
        def poll():
            if not t2.winfo_exists():
                return
            txt = ""
            if not xi:
                txt = "Pilote XInput introuvable sur ce PC."
            else:
                found = False
                for i in range(4):
                    st = XS()
                    if xi.XInputGetState(i, ctypes.byref(st)) == 0:
                        found = True
                        pressed = [n for m, n in NAMES if st.btn & m]
                        txt += f"Manette {i + 1} détectée ✓\nBoutons : {' '.join(pressed) or '-'}\nStick : {st.lx // 3277:+d} {st.ly // 3277:+d}   Gâchettes : {st.lt} {st.rt}\n\n"
                if not found:
                    txt = "Aucune manette Xbox détectée.\n\nBranche-la (câble USB) et attends 5 secondes."
            lab.configure(text=txt + "Appuie sur les boutons : ils s'affichent ici.\nC64 : stick + A = tirer (port " + str(cfg.get("joyport", 2)) + ")\n"
                          "DOS (Doom, Keen, Wolf3D, Duke) : choisis « Joystick » dans le menu du jeu.")
            t2.after(50, poll)
        poll()

    def welcome():
        t2 = tk.Toplevel(root); t2.title("Bienvenue dans Rétro"); t2.configure(bg="#40318d"); t2.transient(root); t2.grab_set()
        tk.Label(t2, text="Bienvenue dans Rétro !", bg="#40318d", fg="#ffffff", font=("Consolas", 20, "bold")).pack(padx=30, pady=(20, 6))
        tk.Label(t2, text="Rétro fait revivre le Commodore 64, MS-DOS et Windows 98.\n\n"
                 "Un seul clic installe tout ce qu'il faut :\n  • les 3 émulateurs (gratuits, sites officiels)\n  • des jeux et démos gratuits et légaux\n\n"
                 "Ensuite : double-clic sur une pochette pour jouer.", bg="#40318d", fg="#a59bff", font=("Consolas", 12), justify="left").pack(padx=30)
        st = tk.Label(t2, text="", bg="#40318d", fg="#ffff55", font=("Consolas", 11, "bold")); st.pack(pady=8)
        def go():
            for w in fb.winfo_children():
                w.configure(state="disabled")
            def work():
                for k in EMUS:
                    if not emu_exe(k):
                        ui(lambda k=k: st.configure(text=f"Installation de {EMUS[k]['emu']}…"))
                        try:
                            install_emu(k)
                        except Exception as ex:
                            log(f"✗ {EMUS[k]['emu']} : {ex}")
                ui(lambda: (upd_emus(), st.configure(text="Téléchargement des jeux gratuits…"),
                                       pack(False, None, lambda: (st.configure(text="C'est prêt ! Double-clic sur une pochette pour jouer."),
                                                                  root.after(2500, t2.destroy)))))
            threading.Thread(target=work, daemon=True).start()
        fb = tk.Frame(t2, bg="#40318d"); fb.pack(pady=(4, 20))
        tk.Button(fb, text="✔  Tout installer", command=go, bg="#ffff55", fg="#000000", font=("Consolas", 15, "bold"), relief="flat", padx=22, pady=10).pack(side="left", padx=8)
        tk.Button(fb, text="Plus tard", command=t2.destroy, font=("Consolas", 12), relief="flat", padx=14, pady=10).pack(side="left", padx=8)
        cfg["welcomed"] = True; save_cfg()
    if not cfg.get("welcomed") and "--test-gui" not in sys.argv:
        root.after(4200, welcome)

    if cfg.get("maximized", True):
        try:
            root.state("zoomed")
        except Exception:
            pass
    if cfg.get("intro", True):
        play_intro(lambda: render())
    if test_ms:
        root.after(test_ms, root.destroy)
    root.mainloop()

def selftest():
    print("Rétro selftest", json.dumps(P, indent=1))
    for f, k in (("jeu.d64", "c64"), ("x.prg", "c64"), ("DOOM.EXE", "dos"), ("disk.img", "dos"), ("cd.iso", "dos"), ("a.txt", None)):
        assert guess_system(f) == k, f
    print("détection formats OK")
    for k in EMUS:
        print(k, "émulateur:", emu_exe(k), "ouvrir:", (open_cmd(k)[0] if emu_exe(k) else "-"))
    print("Mes jeux:", P["jeux"], "scan:", len(scan_dir(P["jeux"])))
    it = {"id": "selftest01", "title": "Test Pochette Rétro", "sys": "c64", "path": "x.d64"}
    try:
        p = make_cover(it); print("pochette:", p); os.remove(p)
    except Exception as e:
        print("pochette KO:", e)
    print("internet:", internet_ok()); print("OK")

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
            ensure_dir(P["logs"]); open(os.path.join(P["logs"], "retro_crash.log"), "a", encoding="utf-8").write(traceback.format_exc())
        except Exception:
            pass
        raise
