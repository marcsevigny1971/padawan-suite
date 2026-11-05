# -*- coding: utf-8 -*-
# Partie de archiveur5.py (découpage v1.2.2, comportement inchangé).
# Chargée par archiveur5.py dans un espace de noms commun : ne pas lancer seule.
from __future__ import annotations



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
