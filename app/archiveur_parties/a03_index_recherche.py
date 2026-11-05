# -*- coding: utf-8 -*-
# Partie de archiveur5.py (découpage v1.2.2, comportement inchangé).
# Chargée par archiveur5.py dans un espace de noms commun : ne pas lancer seule.
from __future__ import annotations


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
