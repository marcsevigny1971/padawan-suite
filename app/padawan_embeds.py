# -*- coding: utf-8 -*-
"""padawan_embeds - aperçus et lecteurs officiels (embeds) pour la suite Padawan.

* detect(url)            -> plateforme (clé, nom, icône, type, protégé DRM ?, URL du lecteur officiel)
* fetch_preview(url)     -> titre, miniature, auteur, durée, description (oEmbed officiel, sinon
                            OpenGraph), avec cache local (%APPDATA%/Padawan/embeds_cache, 7 jours)
* open_player(url, meta) -> ouvre le lecteur OFFICIEL de la plateforme dans une petite fenêtre
                            propre (Edge/Chrome --app), via une page locale http://localhost.

Aucun contournement : rien n'est téléchargé ici, les contenus protégés (DRM) gardent seulement
l'aperçu + le lien, et se regardent sur le site officiel. Module sans Tk : utilisable par
l'Archiveur, le Journal de bord et le Grimoire.
"""
from __future__ import annotations

import hashlib
import html as _html
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, quote, urlencode, urlparse
from urllib.request import Request, urlopen

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0 Safari/537.36")
CACHE_TTL = 7 * 24 * 3600

# clé, nom affiché, morceaux d'hôte, type, protégé (DRM / lien seulement)
PLATFORMS = [
    ("youtube", "📺 YouTube", ("youtube.com", "youtu.be", "youtube-nocookie.com"), "video", False),
    ("vimeo", "🎬 Vimeo", ("vimeo.com",), "video", False),
    ("dailymotion", "🎞 Dailymotion", ("dailymotion.com", "dai.ly"), "video", False),
    ("x", "✖ X (Twitter)", ("twitter.com", "x.com", "fxtwitter.com", "vxtwitter.com"), "social", False),
    ("tiktok", "🎵 TikTok", ("tiktok.com",), "video", False),
    ("facebook", "📘 Facebook", ("facebook.com", "fb.watch", "fb.com"), "social", False),
    ("instagram", "📷 Instagram", ("instagram.com",), "social", False),
    ("reddit", "👽 Reddit", ("reddit.com", "redd.it"), "social", False),
    ("twitch", "🟣 Twitch", ("twitch.tv",), "video", False),
    ("kick", "🟢 Kick", ("kick.com",), "video", False),
    ("rumble", "🟩 Rumble", ("rumble.com",), "video", False),
    ("odysee", "🌊 Odysee", ("odysee.com",), "video", False),
    ("bitchute", "🔴 BitChute", ("bitchute.com",), "video", False),
    ("streamable", "▶ Streamable", ("streamable.com",), "video", False),
    ("loom", "🎥 Loom", ("loom.com",), "video", False),
    ("ted", "🎤 TED", ("ted.com",), "video", False),
    ("bandcamp", "💿 Bandcamp", ("bandcamp.com",), "audio", False),
    ("soundcloud", "☁ SoundCloud", ("soundcloud.com", "on.soundcloud.com"), "audio", False),
    ("spotify", "🟢 Spotify", ("open.spotify.com", "spotify.link"), "audio", False),
    ("applepodcasts", "🎙 Apple Podcasts", ("podcasts.apple.com",), "audio", False),
    ("applemusic", "🍎 Apple Music", ("music.apple.com",), "audio", False),
    ("deezer", "🎧 Deezer", ("deezer.com", "deezer.page.link"), "audio", False),
    ("mixcloud", "🎚 Mixcloud", ("mixcloud.com",), "audio", False),
    ("archiveorg", "🏛 Archive.org", ("archive.org",), "video", False),
    ("telegram", "✈ Telegram", ("t.me", "telegram.me"), "social", False),
    ("bluesky", "🦋 Bluesky", ("bsky.app",), "social", False),
    ("threads", "🧵 Threads", ("threads.net", "threads.com"), "social", False),
    ("linkedin", "💼 LinkedIn", ("linkedin.com",), "social", False),
    ("pinterest", "📌 Pinterest", ("pinterest.", "pin.it"), "image", False),
    ("imgur", "🖼 Imgur", ("imgur.com",), "image", False),
    ("giphy", "🎞 Giphy", ("giphy.com",), "image", False),
    ("flickr", "📸 Flickr", ("flickr.com", "flic.kr"), "image", False),
    ("github", "🐙 GitHub", ("github.com", "gist.github.com"), "code", False),
    ("codepen", "✒ CodePen", ("codepen.io",), "code", False),
    ("googlemaps", "🗺 Google Maps", ("maps.google.", "google.com/maps", "maps.app.goo.gl", "goo.gl/maps"), "map", False),
    ("googledrive", "📁 Google Drive", ("drive.google.com", "docs.google.com"), "doc", False),
    ("wikipedia", "📖 Wikipédia", ("wikipedia.org",), "doc", False),
    # contenus protégés : aperçu + lien seulement, on regarde sur le site officiel
    ("tubi", "📺 Tubi", ("tubitv.com", "tubi.tv"), "video", True),
    ("plutotv", "📺 Pluto TV", ("pluto.tv",), "video", True),
    ("crunchyroll", "🍥 Crunchyroll", ("crunchyroll.com",), "video", True),
    ("netflix", "🎬 Netflix", ("netflix.com",), "video", True),
    ("primevideo", "🎬 Prime Video", ("primevideo.com", "amazon.com/gp/video", "amazon.ca/gp/video"), "video", True),
    ("disneyplus", "🏰 Disney+", ("disneyplus.com",), "video", True),
    ("max", "🎬 Max", ("max.com", "hbomax.com"), "video", True),
    ("hulu", "🎬 Hulu", ("hulu.com",), "video", True),
    ("paramountplus", "⛰ Paramount+", ("paramountplus.com",), "video", True),
    ("peacock", "🦚 Peacock", ("peacocktv.com",), "video", True),
    ("appletv", "🍎 Apple TV+", ("tv.apple.com",), "video", True),
    ("crave", "🎬 Crave", ("crave.ca",), "video", True),
    ("toutv", "📺 ICI TOU.TV", ("ici.tou.tv", "tou.tv"), "video", True),
    ("noovo", "📺 Noovo", ("noovo.ca",), "video", True),
    ("youtubetv", "📺 YouTube TV", ("tv.youtube.com",), "video", True),
]
LABELS = {k: lab for k, lab, _h, _t, _d in PLATFORMS}
PROTECTED_MSG = ("🔒 Contenu protégé : l'aperçu et le lien sont gardés. "
                 "Regarde-le sur le site officiel.")

OEMBED = {
    "youtube": "https://www.youtube.com/oembed?format=json&url={u}",
    "vimeo": "https://vimeo.com/api/oembed.json?url={u}",
    "dailymotion": "https://www.dailymotion.com/services/oembed?format=json&url={u}",
    "x": "https://publish.twitter.com/oembed?omit_script=1&dnt=1&url={u}",
    "tiktok": "https://www.tiktok.com/oembed?url={u}",
    "reddit": "https://www.reddit.com/oembed?url={u}",
    "soundcloud": "https://soundcloud.com/oembed?format=json&url={u}",
    "spotify": "https://open.spotify.com/oembed?url={u}",
    "mixcloud": "https://app.mixcloud.com/oembed/?format=json&url={u}",
    "deezer": "https://api.deezer.com/oembed?format=json&url={u}",
    "rumble": "https://rumble.com/api/Media/oembed.json?url={u}",
    "bluesky": "https://embed.bsky.app/oembed?format=json&url={u}",
    "giphy": "https://giphy.com/services/oembed?url={u}",
    "flickr": "https://www.flickr.com/services/oembed/?format=json&url={u}",
    "streamable": "https://api.streamable.com/oembed.json?url={u}",
    "loom": "https://www.loom.com/v1/oembed?url={u}",
    "ted": "https://www.ted.com/services/v1/oembed.json?url={u}",
    "imgur": "https://api.imgur.com/oembed.json?url={u}",
    "codepen": "https://codepen.io/api/oembed?format=json&url={u}",
    "odysee": "https://odysee.com/$/oembed?format=json&url={u}",
}


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def detect(url: str) -> Dict[str, Any]:
    """Plateforme d'un lien : {key, label, kind, protected, embed} (embed = lecteur officiel ou "")."""
    url = (url or "").strip()
    h = _host(url)
    low = (h + (urlparse(url).path or "")).lower() if h else url.lower()
    key, label, kind, prot = "web", "🌐 Web", "web", False
    for k, lab, hosts, t, d in PLATFORMS:
        if any((frag in low) if "/" in frag or frag.endswith(".") else (h == frag or h.endswith("." + frag))
               for frag in hosts):
            key, label, kind, prot = k, lab, t, d
            break
    if key == "web" and re.search(r"/(videos/watch|w)/[0-9a-zA-Z-]{8,}", urlparse(url).path or ""):
        key, label, kind = "peertube", "🐙 PeerTube", "video"   # PeerTube : n'importe quel serveur
    if key == "web" and re.search(r"/@[\w.]+/\d{6,}", urlparse(url).path or ""):
        key, label, kind = "mastodon", "🐘 Mastodon", "social"
    emb = "" if prot else embed_url(key, url)
    return {"key": key, "label": label, "kind": kind, "protected": prot, "embed": emb}


def _yt_id(url: str) -> str:
    p = urlparse(url)
    if "youtu.be" in (p.hostname or ""):
        return p.path.strip("/").split("/")[0]
    m = re.search(r"/(?:shorts|embed|live|v)/([\w-]{6,})", p.path or "")
    if m:
        return m.group(1)
    return (parse_qs(p.query).get("v") or [""])[0]


def _yt_start(url: str) -> int:
    q = parse_qs(urlparse(url).query)
    t = (q.get("t") or q.get("start") or [""])[0]
    m = re.match(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s?)?$", t or "")
    if not t or not m:
        return 0
    return int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0)


def embed_url(key: str, url: str) -> str:
    """URL du lecteur officiel (iframe) pour la plateforme, ou "" si aucune."""
    p = urlparse(url)
    path = p.path or ""
    try:
        if key == "youtube":
            vid = _yt_id(url)
            if vid:
                s = _yt_start(url)
                return f"https://www.youtube-nocookie.com/embed/{vid}?autoplay=1&rel=0" + (f"&start={s}" if s else "")
            lst = (parse_qs(p.query).get("list") or [""])[0]
            return f"https://www.youtube-nocookie.com/embed/videoseries?list={lst}" if lst else ""
        if key == "vimeo":
            m = re.search(r"/(\d{5,})", path)
            return f"https://player.vimeo.com/video/{m.group(1)}?autoplay=1" if m else ""
        if key == "dailymotion":
            m = re.search(r"/video/([a-zA-Z0-9]+)", path) or (re.search(r"/([a-zA-Z0-9]+)$", path) if "dai.ly" in p.netloc else None)
            return f"https://www.dailymotion.com/embed/video/{m.group(1)}?autoplay=1" if m else ""
        if key == "x":
            m = re.search(r"/status(?:es)?/(\d+)", path)
            return f"https://platform.twitter.com/embed/Tweet.html?id={m.group(1)}&dnt=true" if m else ""
        if key == "tiktok":
            m = re.search(r"/video/(\d+)", path)
            return f"https://www.tiktok.com/embed/v2/{m.group(1)}" if m else ""
        if key == "instagram":
            m = re.search(r"/(p|reel|reels|tv)/([\w-]+)", path)
            return f"https://www.instagram.com/{'reel' if m.group(1).startswith('reel') else m.group(1)}/{m.group(2)}/embed/captioned/" if m else ""
        if key == "facebook":
            kind = "video" if re.search(r"/(videos|watch|reel|share/v|share/r)", path) or "fb.watch" in p.netloc else "post"
            return f"https://www.facebook.com/plugins/{kind}.php?href={quote(url, safe='')}&show_text=true"
        if key == "reddit":
            if "/comments/" in path:
                return f"https://embed.reddit.com{path.rstrip('/')}/?embed=true&theme=dark"
            return ""
        if key == "twitch":
            m = re.search(r"/videos/(\d+)", path)
            if m:
                return f"https://player.twitch.tv/?video={m.group(1)}&parent=localhost&autoplay=true"
            m = re.search(r"/clip/([\w-]+)", path)
            if m or "clips.twitch.tv" in p.netloc:
                slug = m.group(1) if m else path.strip("/").split("/")[0]
                return f"https://clips.twitch.tv/embed?clip={slug}&parent=localhost&autoplay=true"
            ch = path.strip("/").split("/")[0]
            return f"https://player.twitch.tv/?channel={ch}&parent=localhost&autoplay=true" if ch else ""
        if key == "kick":
            ch = path.strip("/").split("/")[0]
            return f"https://player.kick.com/{ch}" if ch else ""
        if key == "odysee":
            return f"https://odysee.com/$/embed{path}" if path.strip("/") else ""
        if key == "bitchute":
            m = re.search(r"/(?:video|embed)/([\w-]+)", path)
            return f"https://www.bitchute.com/embed/{m.group(1)}/" if m else ""
        if key == "streamable":
            vid = path.strip("/").split("/")[-1]
            return f"https://streamable.com/e/{vid}?autoplay=1" if vid else ""
        if key == "loom":
            m = re.search(r"/(?:share|embed)/([\w]+)", path)
            return f"https://www.loom.com/embed/{m.group(1)}" if m else ""
        if key == "ted":
            m = re.search(r"/talks/([\w-]+)", path)
            return f"https://embed.ted.com/talks/{m.group(1)}" if m else ""
        if key == "spotify":
            m = re.search(r"/(track|album|playlist|episode|show|artist)/([\w]+)", path)
            return f"https://open.spotify.com/embed/{m.group(1)}/{m.group(2)}" if m else ""
        if key == "applepodcasts":
            return "https://embed.podcasts.apple.com" + path + (("?" + p.query) if p.query else "")
        if key == "applemusic":
            return "https://embed.music.apple.com" + path + (("?" + p.query) if p.query else "")
        if key == "deezer":
            m = re.search(r"/(track|album|playlist|episode|show|artist)/(\d+)", path)
            return f"https://widget.deezer.com/widget/dark/{m.group(1)}/{m.group(2)}" if m else ""
        if key == "mixcloud":
            return "https://www.mixcloud.com/widget/iframe/?" + urlencode({"feed": path, "hide_cover": 1}) if path.strip("/") else ""
        if key == "archiveorg":
            m = re.search(r"/(?:details|embed)/([^/?#]+)", path)
            return f"https://archive.org/embed/{m.group(1)}" if m else ""
        if key == "peertube":
            m = re.search(r"/(?:videos/watch|w)/([0-9a-zA-Z-]+)", path)
            return f"{p.scheme}://{p.netloc}/videos/embed/{m.group(1)}" if m else ""
        if key == "mastodon":
            return f"{p.scheme}://{p.netloc}{path.rstrip('/')}/embed"
        if key == "telegram":
            m = re.match(r"/(?:s/)?([\w]+)/(\d+)", path)
            return f"https://t.me/{m.group(1)}/{m.group(2)}?embed=1&dark=1" if m else ""
        if key == "pinterest":
            m = re.search(r"/pin/(\d+)", path)
            return f"https://assets.pinterest.com/ext/embed.html?id={m.group(1)}" if m else ""
        if key == "imgur":
            vid = path.strip("/").split("/")[-1].split(".")[0]
            return f"https://imgur.com/{'a/' if '/a/' in path or '/gallery/' in path else ''}{vid}/embed?pub=true" if vid else ""
        if key == "giphy":
            vid = path.rstrip("/").split("/")[-1].split("-")[-1]
            return f"https://giphy.com/embed/{vid}" if vid else ""
        if key == "codepen":
            m = re.match(r"/([\w-]+)/(?:pen|full|details)/(\w+)", path)
            return f"https://codepen.io/{m.group(1)}/embed/{m.group(2)}?default-tab=result" if m else ""
        if key == "googlemaps":
            q = (parse_qs(p.query).get("q") or [""])[0]
            m = re.search(r"/place/([^/]+)", path)
            if not q and m:
                q = m.group(1).replace("+", " ")
            m2 = re.search(r"@(-?\d+\.\d+),(-?\d+\.\d+)", path)
            if not q and m2:
                q = f"{m2.group(1)},{m2.group(2)}"
            return f"https://maps.google.com/maps?q={quote(q)}&output=embed" if q else ""
        if key == "googledrive":
            m = re.search(r"/(file|document|spreadsheets|presentation)/d/([\w-]+)", path)
            if m:
                base = "https://drive.google.com/file" if m.group(1) == "file" else f"https://docs.google.com/{m.group(1)}"
                return f"{base}/d/{m.group(2)}/preview"
            return ""
    except Exception:
        return ""
    return ""


# ------------------------------------------------------------------ aperçu (oEmbed / OpenGraph)
def _cache_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "Padawan", "embeds_cache")
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        pass
    return d


def _get(url: str, timeout: float = 8.0, limit: int = 1_500_000) -> bytes:
    req = Request(url, headers={"User-Agent": UA, "Accept-Language": "fr-CA,fr;q=0.9,en;q=0.8"})
    with urlopen(req, timeout=timeout) as r:
        return r.read(limit)


def _meta_tags(page: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for tag in re.findall(r"<meta\b[^>]*>", page[:600_000], re.I):
        k = re.search(r"(?:property|name|itemprop)\s*=\s*[\"']([^\"']+)[\"']", tag, re.I)
        v = re.search(r"content\s*=\s*[\"']([^\"']*)[\"']", tag, re.I) or re.search(r"content\s*=\s*([^\s>]+)", tag, re.I)
        if k and v:
            out.setdefault(k.group(1).strip().lower(), _html.unescape(v.group(1)).strip())
    if "og:title" not in out:
        m = re.search(r"<title[^>]*>([^<]+)</title>", page, re.I)
        if m:
            out["og:title"] = _html.unescape(m.group(1)).strip()
    return out


def _iso_dur(s: str) -> float:
    m = re.match(r"P(?:T)?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?$", s or "", re.I)
    if not m:
        try:
            return float(s)
        except (TypeError, ValueError):
            return 0.0
    return int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + float(m.group(3) or 0)


def fetch_preview(url: str, use_cache: bool = True, timeout: float = 8.0) -> Dict[str, Any]:
    """Titre, miniature, auteur, durée, description + lecteur officiel. Jamais d'exception."""
    det = detect(url)
    key = hashlib.sha1(url.strip().encode("utf-8")).hexdigest()
    cpath = os.path.join(_cache_dir(), key + ".json")
    if use_cache:
        try:
            if time.time() - os.path.getmtime(cpath) < CACHE_TTL:
                with open(cpath, "r", encoding="utf-8") as fh:
                    return json.load(fh)
        except (OSError, ValueError):
            pass
    meta: Dict[str, Any] = {"url": url, "platform": det["key"], "label": det["label"], "kind": det["kind"],
                            "protected": det["protected"], "embed": det["embed"], "source": ""}
    ep = OEMBED.get(det["key"])
    if ep and not det["protected"]:
        try:
            d = json.loads(_get(ep.format(u=quote(url, safe="")), timeout).decode("utf-8", "replace"))
            meta.update({"title": d.get("title") or "", "author": d.get("author_name") or "",
                         "author_url": d.get("author_url") or "", "thumbnail": d.get("thumbnail_url") or "",
                         "provider": d.get("provider_name") or "", "oembed_html": (d.get("html") or "")[:20000],
                         "duration": float(d.get("duration") or 0), "description": d.get("description") or "",
                         "width": d.get("width"), "height": d.get("height"), "source": "oembed"})
        except Exception:
            pass
    if not meta["embed"] and meta.get("oembed_html"):
        m = re.search(r"<iframe[^>]+src=[\"']([^\"']+)", meta["oembed_html"], re.I)
        if m and m.group(1).startswith(("https://", "//")):
            meta["embed"] = ("https:" + m.group(1)) if m.group(1).startswith("//") else m.group(1)
    if not meta.get("title") or not meta.get("thumbnail") or not meta.get("description"):
        try:
            raw = _get(url, timeout)
            page = raw.decode("utf-8", "replace")
            m = _meta_tags(page)
            meta.setdefault("title", "")
            meta["title"] = meta["title"] or m.get("og:title") or m.get("twitter:title") or ""
            meta["description"] = meta.get("description") or m.get("og:description") or m.get("description") or ""
            meta["thumbnail"] = meta.get("thumbnail") or m.get("og:image") or m.get("og:image:url") or m.get("twitter:image") or ""
            meta["author"] = meta.get("author") or m.get("author") or m.get("article:author") or m.get("og:site_name") or ""
            meta["provider"] = meta.get("provider") or m.get("og:site_name") or ""
            if not meta.get("duration"):
                meta["duration"] = _iso_dur(m.get("video:duration") or m.get("duration") or m.get("og:video:duration") or "")
            if not meta["embed"] and not det["protected"]:
                ov = m.get("og:video:secure_url") or m.get("og:video:url") or m.get("og:video") or m.get("twitter:player") or ""
                if ov.startswith("https://") and not re.search(r"\.(mp4|m3u8|webm|mov)(\?|$)", ov, re.I):
                    meta["embed"] = ov  # lecteur officiel annoncé par la page elle-même
            meta["source"] = meta["source"] or "opengraph"
        except Exception:
            pass
    meta["fetched_at"] = int(time.time())
    try:
        tmp = cpath + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(meta, fh, ensure_ascii=False)
        os.replace(tmp, cpath)
    except OSError:
        pass
    return meta


def can_play(meta_or_url: Any) -> bool:
    m = meta_or_url if isinstance(meta_or_url, dict) else detect(str(meta_or_url))
    return bool(not m.get("protected") and (m.get("embed") or m.get("oembed_html")))


# ------------------------------------------------------------------ lecteur officiel (fenêtre --app)
_PAGES: Dict[str, str] = {}
_SRV: Dict[str, Any] = {}
_LOCK = threading.Lock()


def _server_port() -> int:
    with _LOCK:
        if _SRV.get("port"):
            return _SRV["port"]
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        class H(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                tok = self.path.strip("/").split("/")[-1].split("?")[0]
                body = _PAGES.get(tok)
                if body is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                data = body.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *a):
                pass

        srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        _SRV["srv"], _SRV["port"] = srv, srv.server_address[1]
        return _SRV["port"]


def player_html(meta: Dict[str, Any], colors: Optional[Dict[str, str]] = None) -> str:
    c = {"bg": "#0f172a", "panel": "#1e293b", "fg": "#e2e8f0", "dim": "#94a3b8", "acc": "#facc15"}
    c.update({k: v for k, v in (colors or {}).items() if v})
    e = _html.escape
    title = e(str(meta.get("title") or meta.get("url") or ""))
    url = e(str(meta.get("url") or ""), quote=True)
    kind = meta.get("kind") or "video"
    if meta.get("embed"):
        h = {"audio": "min(420px,100%)", "social": "100%", "map": "100%", "doc": "100%"}.get(kind, "100%")
        frame = (f'<iframe src="{e(meta["embed"], quote=True)}" style="height:{h}" allowfullscreen '
                 'allow="autoplay; encrypted-media; picture-in-picture; fullscreen; clipboard-write" '
                 'referrerpolicy="strict-origin-when-cross-origin"></iframe>')
    else:
        frame = f'<div class="oe">{meta.get("oembed_html") or ""}</div>'
        if meta.get("platform") == "x":
            frame += '<script async src="https://platform.twitter.com/widgets.js"></script>'
    who = e(" · ".join(x for x in (str(meta.get("label") or ""), str(meta.get("author") or "")) if x))
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="referrer" content="strict-origin-when-cross-origin"><title>{title}</title>
<style>html,body{{margin:0;height:100%;background:{c['bg']};color:{c['fg']};font:14px "Segoe UI",sans-serif}}
#top{{display:flex;gap:10px;align-items:center;padding:6px 10px;background:{c['panel']}}}
#top b{{flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}#top span{{color:{c['dim']}}}
button,a.b{{background:{c['acc']};color:#111;border:0;border-radius:6px;padding:7px 12px;font-weight:700;
cursor:pointer;text-decoration:none;font-size:14px}}
#wrap{{position:absolute;top:46px;bottom:0;left:0;right:0;display:flex;justify-content:center;align-items:center;overflow:auto}}
iframe{{border:0;width:100%;background:#000}}.oe{{max-width:620px;margin:auto;padding:10px}}
#hint{{position:fixed;right:10px;bottom:6px;color:{c['dim']};font-size:12px}}</style></head><body>
<div id="top"><b>{title}</b><span>{who}</span>
<button onclick="fs()" title="Plein écran (F)">⛶ Plein écran</button>
<a class="b" href="{url}" target="_blank" rel="noopener" title="Ouvrir sur le site officiel (O)">🌐 Site officiel</a></div>
<div id="wrap">{frame}</div><div id="hint">F = plein écran · O = site officiel · Alt+F4 = fermer</div>
<script>function fs(){{var w=document.getElementById('wrap');(w.requestFullscreen||w.webkitRequestFullscreen).call(w)}}
document.addEventListener('keydown',function(ev){{if(ev.key==='f'||ev.key==='F')fs();
if(ev.key==='o'||ev.key==='O')window.open("{url}","_blank")}});setTimeout(function(){{document.getElementById('hint').style.display='none'}},6000)</script>
</body></html>"""


def find_browser() -> Optional[str]:
    cands = []
    for env in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        b = os.environ.get(env)
        if b:
            cands += [os.path.join(b, "Microsoft", "Edge", "Application", "msedge.exe"),
                      os.path.join(b, "Google", "Chrome", "Application", "chrome.exe")]
    for c in cands:
        if os.path.isfile(c):
            return c
    for n in ("msedge", "google-chrome", "chromium", "chromium-browser", "chrome"):
        p = shutil.which(n)
        if p:
            return p
    return None


def open_player(url: str, meta: Optional[Dict[str, Any]] = None, colors: Optional[Dict[str, str]] = None,
                size=(1040, 680), dry_run: bool = False) -> str:
    """Ouvre le lecteur officiel dans une fenêtre propre. Retourne l'adresse locale ouverte (ou le site)."""
    meta = dict(meta or fetch_preview(url))
    meta.setdefault("url", url)
    if meta.get("protected") or not can_play(meta):
        if not dry_run:
            import webbrowser
            webbrowser.open(url)
        return url
    if meta.get("kind") == "audio":
        size = (760, 520)
    tok = hashlib.sha1(f"{url}{time.time()}".encode()).hexdigest()[:16]
    _PAGES[tok] = player_html(meta, colors)
    local = f"http://localhost:{_server_port()}/p/{tok}"
    if dry_run:
        return local
    b = find_browser()
    if b:
        kw: Dict[str, Any] = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if sys.platform.startswith("win"):
            kw["creationflags"] = 0x08000000
        try:
            subprocess.Popen([b, f"--app={local}", f"--window-size={size[0]},{size[1]}", "--new-window"], **kw)
            return local
        except Exception:
            pass
    import webbrowser
    webbrowser.open(local)
    return local


if __name__ == "__main__":  # petit test : python padawan_embeds.py <lien>
    for a in sys.argv[1:] or ["https://youtu.be/dQw4w9WgXcQ"]:
        print(json.dumps(detect(a), ensure_ascii=False))
