# -*- coding: utf-8 -*-
# Partie de archiveur5.py (découpage v1.2.2, comportement inchangé).
# Chargée par archiveur5.py dans un espace de noms commun : ne pas lancer seule.
from __future__ import annotations



def _ts_to_sec(s: str) -> Optional[float]:
    m = _TS_RE.search(s or "")
    if not m:
        return None
    h, mi, se, ms = m.groups()
    return int(h or 0) * 3600 + int(mi) * 60 + int(se) + int(ms.ljust(3, "0")) / 1000.0


def parse_subtitles(path: str) -> List[Tuple[float, str]]:
    """Lit un .vtt/.srt → [(début_s, texte)] ; enlève les doublons des sous-titres auto YouTube."""
    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
            raw = f.read()
    except OSError:
        return []
    blocks = re.split(r"\r?\n\s*\r?\n", raw.replace("\r\n", "\n"))
    cues: List[Tuple[float, float, List[str]]] = []
    for b in blocks:
        lines = [ln for ln in b.split("\n")]
        idx = next((i for i, ln in enumerate(lines) if "-->" in ln), -1)
        if idx < 0:
            continue
        left, _, right = lines[idx].partition("-->")
        st, en = _ts_to_sec(left), _ts_to_sec(right)
        if st is None:
            continue
        texts = []
        for ln in lines[idx + 1:]:
            t = re.sub(r"<[^>]+>", "", ln)
            t = html.unescape(t).replace("\u200b", "").strip()
            if t:
                texts.append(t)
        if texts:
            cues.append((st, en if en is not None else st, texts))
    out: List[Tuple[float, str]] = []
    last_lines: List[str] = []
    for st, en, texts in cues:
        if en - st < 0.05 and len(cues) > 3:  # transitions YouTube de 10 ms
            continue
        new = [t for t in texts if t not in last_lines]
        last_lines = texts
        line = " ".join(new).strip()
        if not line or (out and out[-1][1] == line):
            continue
        out.append((round(st, 2), line))
    # fusionne les fragments (sous-titres auto découpés au milieu des phrases)
    merged: List[Tuple[float, str]] = []
    for st, line in out:
        if merged:
            pst, pl = merged[-1]
            if (st - pst < 6 and len(pl) + len(line) < 110
                    and (st - pst < 1.0 or not re.search(r"[.!?…»\"')\]]$", pl))):
                merged[-1] = (pst, pl + " " + line)
                continue
        merged.append((st, line))
    return merged


def _sub_lang(name: str) -> str:
    m = re.search(r"\.([a-zA-Z]{2,3}(?:[-_][A-Za-z0-9]+)*)\.(?:vtt|srt)$", name)
    return m.group(1) if m else ""


def pick_subtitle_file(folder: str) -> Optional[str]:
    """Meilleur fichier de sous-titres : FR, puis EN, puis autre."""
    try:
        names = [n for n in os.listdir(folder) if n.lower().endswith(SUB_EXTS)]
    except OSError:
        return None
    if not names:
        return None

    def rank(n: str) -> Tuple[int, int, str]:
        lang = _sub_lang(n).lower()
        if lang.startswith("fr"):
            r = 0
        elif lang.startswith("en"):
            r = 1
        else:
            r = 2
        return (r, 1 if "orig" in lang or "-" in lang else 0, n)
    names.sort(key=rank)
    return os.path.join(folder, names[0])


def save_transcript(folder: str, cues: List[Tuple[float, str]], lang: str, source: str) -> Dict[str, Any]:
    data = {"lang": lang, "source": source, "created": datetime.now().isoformat(timespec="seconds"),
            "cues": [[float(t), str(x)] for t, x in cues]}
    _write_json_atomic(os.path.join(folder, TRANSCRIPT_JSON), data)
    with open(os.path.join(folder, TRANSCRIPT_TXT), "w", encoding="utf-8") as f:
        f.write(f"Transcription ({source}, langue : {lang or '?'})\n\n")
        for t, x in cues:
            f.write(f"[{fmt_ts(t)}] {x}\n")
    return data


def load_transcript(folder: str) -> Dict[str, Any]:
    """{'lang','source','cues':[(t, texte)]} ; construit depuis les sous-titres si besoin."""
    p = os.path.join(folder, TRANSCRIPT_JSON)
    try:
        if os.path.isfile(p):
            with open(p, "r", encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict) and isinstance(d.get("cues"), list):
                d["cues"] = [(float(c[0]), str(c[1])) for c in d["cues"] if isinstance(c, (list, tuple)) and len(c) >= 2]
                return d
    except Exception:
        logger.exception("lecture transcript %s", p)
    return build_transcript(folder) or {}


def build_transcript(folder: str, force: bool = False) -> Optional[Dict[str, Any]]:
    """Transcription horodatée à partir des sous-titres yt-dlp (.vtt/.srt)."""
    if not force and os.path.isfile(os.path.join(folder, TRANSCRIPT_JSON)):
        return None
    sub = pick_subtitle_file(folder)
    if not sub:
        return None
    cues = parse_subtitles(sub)
    if not cues:
        return None
    try:
        d = save_transcript(folder, cues, _sub_lang(os.path.basename(sub)), "sous-titres")
        d["cues"] = [(float(t), x) for t, x in d["cues"]]
        return d
    except OSError:
        logger.exception("écriture transcript")
        return None


def transcript_text(folder: str, limit: int = 60000) -> str:
    d = load_transcript(folder) if os.path.isdir(folder) else {}
    txt = " ".join(x for _t, x in d.get("cues") or [])
    return txt[:limit]


def transcribe_whisper(folder: str, log: Callable[[str], None], model_size: str = "base",
                       progress: Optional[Callable[[float], None]] = None,
                       cancel_event: Optional[threading.Event] = None) -> Dict[str, Any]:
    """Transcription locale (faster-whisper, CPU int8). Le modèle est téléchargé au 1er usage."""
    from faster_whisper import WhisperModel  # type: ignore
    media = find_main_media(folder)
    if not media:
        raise RuntimeError("Aucun média audio/vidéo dans cette archive.")
    log(f"🎙 Chargement du modèle Whisper « {model_size} » (1er usage : téléchargement)…")
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, tinfo = model.transcribe(media, vad_filter=True, beam_size=1)
    dur = float(getattr(tinfo, "duration", 0) or 0) or (probe_duration(media) or 0)
    lang = str(getattr(tinfo, "language", "") or "")
    log(f"🎙 Langue détectée : {lang or '?'} — transcription…")
    cues: List[Tuple[float, str]] = []
    for seg in segments:
        if cancel_event is not None and cancel_event.is_set():
            raise ArchiveCancelled("Transcription annulée.")
        t = (seg.text or "").strip()
        if t:
            cues.append((round(float(seg.start), 2), t))
        if progress and dur:
            progress(min(99.0, float(seg.end) / dur * 100.0))
    if not cues:
        raise RuntimeError("Aucune parole détectée.")
    d = save_transcript(folder, cues, lang, f"whisper-{model_size}")
    with open(os.path.join(folder, f"transcript_whisper.{lang or 'xx'}.srt"), "w", encoding="utf-8") as f:
        for i, (t, x) in enumerate(cues, 1):
            nxt = cues[i][0] if i < len(cues) else t + 4

            def srt(v: float) -> str:
                ms = int(round(v * 1000))
                h, ms = divmod(ms, 3600000)
                m, ms = divmod(ms, 60000)
                s, ms = divmod(ms, 1000)
                return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
            f.write(f"{i}\n{srt(t)} --> {srt(max(t + 0.5, nxt))}\n{x}\n\n")
    info = load_info(folder)
    if info:
        info["transcript_lang"] = lang
        info["transcript_source"] = d["source"]
        _write_json_atomic(os.path.join(folder, "info.json"), info)
    return d


# ================================================================= v5 : outils média (ffmpeg)
EXTRACTS_DIR = "extraits"


def _run_ff(args: List[str], timeout: int = 600) -> Tuple[bool, str]:
    ff = find_ffmpeg()
    if not ff:
        return False, "ffmpeg introuvable"
    try:
        r = subprocess.run([ff, "-hide_banner", "-nostdin", "-loglevel", "error", "-y", *args],
                           **_hidden_kwargs(), timeout=timeout)
        err = (r.stderr or b"").decode("utf-8", errors="replace").strip()
        return r.returncode == 0, err
    except subprocess.TimeoutExpired:
        return False, "délai dépassé"
    except Exception as e:
        return False, str(e)


def _extract_dir(folder: str) -> str:
    d = os.path.join(folder, EXTRACTS_DIR)
    os.makedirs(d, exist_ok=True)
    return d


def _check_range(start: float, end: Optional[float], duration: Optional[float]) -> Tuple[float, float]:
    start = max(0.0, float(start or 0))
    if duration and start >= duration:
        raise ValueError(f"Le début ({fmt_ts(start)}) dépasse la durée ({fmt_ts(duration)}).")
    if end is None or end <= 0:
        end = duration or (start + 10)
    if duration:
        end = min(end, duration)
    if end <= start:
        raise ValueError("La fin doit être après le début.")
    return start, end


def media_capture(video: str, t: float, folder: str) -> str:
    dur = probe_duration(video)
    t = max(0.0, min(float(t or 0), max(0.0, (dur or t + 1) - 0.05)))
    out = _unique_path(os.path.join(_extract_dir(folder), f"capture_{_ff_label(t)}.jpg"))
    ok, err = _run_ff(["-ss", f"{t:.3f}", "-i", video, "-frames:v", "1", "-q:v", "2", out], 120)
    if not ok or not os.path.isfile(out):
        raise RuntimeError(f"Capture impossible : {err or 'ffmpeg'}")
    return out


def media_clip(video: str, start: float, end: Optional[float], folder: str, precise: bool = False) -> str:
    dur = probe_duration(video)
    start, end = _check_range(start, end, dur)
    is_audio = video.lower().endswith(AUDIO_EXTS)
    ext = os.path.splitext(video)[1].lower() if is_audio else ".mp4"
    name = f"extrait_{_ff_label(start)}_a_{_ff_label(end)}{ext}"
    out = _unique_path(os.path.join(_extract_dir(folder), name))
    length = end - start
    if is_audio:
        args = ["-ss", f"{start:.3f}", "-i", video, "-t", f"{length:.3f}", "-c", "copy", out]
    elif precise:
        args = ["-ss", f"{start:.3f}", "-i", video, "-t", f"{length:.3f}", "-map", "0:v:0", "-map", "0:a:0?",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out]
    else:
        args = ["-ss", f"{start:.3f}", "-i", video, "-t", f"{length:.3f}", "-map", "0:v:0", "-map", "0:a:0?",
                "-c", "copy", "-avoid_negative_ts", "make_zero", "-movflags", "+faststart", out]
    ok, err = _run_ff(args, 1800)
    if not ok or not os.path.isfile(out) or os.path.getsize(out) == 0:
        try:
            os.remove(out)
        except OSError:
            pass
        raise RuntimeError(f"Extrait impossible : {err or 'ffmpeg'}")
    return out


def media_audio(video: str, folder: str, start: Optional[float] = None, end: Optional[float] = None) -> str:
    dur = probe_duration(video)
    args: List[str] = []
    if start is not None or end is not None:
        s, e = _check_range(start or 0, end, dur)
        name = f"audio_{_ff_label(s)}_a_{_ff_label(e)}.mp3"
        args += ["-ss", f"{s:.3f}", "-i", video, "-t", f"{e - s:.3f}"]
    else:
        name = "audio_complet.mp3"
        args += ["-i", video]
    out = _unique_path(os.path.join(_extract_dir(folder), name))
    ok, err = _run_ff(args + ["-vn", "-c:a", "libmp3lame", "-q:a", "2", out], 1800)
    if not ok or not os.path.isfile(out) or os.path.getsize(out) == 0:
        try:
            os.remove(out)
        except OSError:
            pass
        raise RuntimeError(f"Extraction audio impossible : {err or 'ffmpeg (piste audio absente ?)'}")
    return out


GIF_MAX_SECONDS = 20


def media_gif(video: str, start: float, end: Optional[float], folder: str, width: int = 480, fps: int = 12) -> str:
    dur = probe_duration(video)
    start, end = _check_range(start, end if end else (start or 0) + 5, dur)
    if end - start > GIF_MAX_SECONDS:
        end = start + GIF_MAX_SECONDS
    out = _unique_path(os.path.join(_extract_dir(folder), f"gif_{_ff_label(start)}_a_{_ff_label(end)}.gif"))
    vf = (f"fps={int(fps)},scale='min({int(width)},iw)':-2:flags=lanczos,split[s0][s1];"
          f"[s0]palettegen=max_colors=128:stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle")
    ok, err = _run_ff(["-ss", f"{start:.3f}", "-t", f"{end - start:.3f}", "-i", video, "-vf", vf,
                       "-loop", "0", out], 900)
    if not ok or not os.path.isfile(out) or os.path.getsize(out) == 0:
        try:
            os.remove(out)
        except OSError:
            pass
        raise RuntimeError(f"GIF impossible : {err or 'ffmpeg'}")
    return out


def list_extracts(folder: str) -> List[str]:
    d = os.path.join(folder, EXTRACTS_DIR)
    try:
        return [os.path.join(d, n) for n in sorted(os.listdir(d)) if os.path.isfile(os.path.join(d, n))]
    except OSError:
        return []


# ================================================================= v5 : pages web complètes
WEB_ASSETS_DIR = "page_files"
WEB_MAX_IMAGES = 80
WEB_MAX_IMAGE_BYTES = 8 * 1024 * 1024
WEB_MAX_TOTAL_BYTES = 80 * 1024 * 1024
WEB_MAX_CSS = 15


def http_fetch(url: str, timeout: int = 30, max_bytes: int = 40 * 1024 * 1024) -> Tuple[bytes, str, str]:
    """GET robuste → (contenu, url finale, content-type). Repli curl_cffi (empreinte Chrome) si 403/429/503."""
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "fr-CA,fr;q=0.9,en;q=0.8",
               "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/*,*/*;q=0.8"}
    try:
        req = Request(url, headers=headers)
        with urlopen(req, timeout=timeout) as resp:
            data = resp.read(max_bytes + 1)
            if len(data) > max_bytes:
                raise RuntimeError("fichier trop volumineux")
            return data, resp.geturl(), str(resp.headers.get("Content-Type") or "")
    except Exception as e:
        code = getattr(e, "code", None)
        if code in (403, 429, 503) and module_available("curl_cffi"):
            from curl_cffi import requests as creq  # type: ignore
            r = creq.get(url, impersonate="chrome", timeout=timeout, headers={"Accept-Language": headers["Accept-Language"]})
            if r.status_code >= 400:
                raise RuntimeError(f"HTTP Error {r.status_code}") from e
            return r.content[:max_bytes], str(r.url), str(r.headers.get("content-type") or "")
        raise


def _decode_html(raw: bytes, ctype: str) -> str:
    m = re.search(r"charset=([\w-]+)", ctype or "", re.I)
    cands = [m.group(1)] if m else []
    m2 = re.search(rb"<meta[^>]+charset=[\"']?([\w-]+)", raw[:4096], re.I)
    if m2:
        cands.append(m2.group(1).decode("ascii", "ignore"))
    cands += ["utf-8", "cp1252"]
    for c in cands:
        try:
            return raw.decode(c)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", errors="replace")


def _soup(text: str):
    from bs4 import BeautifulSoup  # type: ignore
    for parser in ("lxml", "html.parser"):
        try:
            return BeautifulSoup(text, parser)
        except Exception:
            continue
    return BeautifulSoup(text, "html.parser")


def _meta(soup, *names: str) -> str:
    for n in names:
        tag = soup.find("meta", attrs={"property": n}) or soup.find("meta", attrs={"name": n})
        if tag and tag.get("content"):
            return html.unescape(str(tag.get("content"))).strip()
    return ""


def _best_src(img, base: str) -> str:
    from urllib.parse import urljoin
    cands = []
    for attr in ("srcset", "data-srcset"):
        ss = img.get(attr)
        if ss:
            for part in str(ss).split(","):
                bits = part.strip().split()
                if not bits:
                    continue
                w = 0
                if len(bits) > 1:
                    m = re.match(r"(\d+(?:\.\d+)?)([wx])", bits[1])
                    if m:
                        w = float(m.group(1)) * (1000 if m.group(2) == "x" else 1)
                cands.append((w, bits[0]))
    if cands:
        cands.sort(key=lambda x: x[0])
        # éviter les très grandes images (4K) : la plus grande ≤ 1600 px, sinon la plus petite
        ok = [c for c in cands if c[0] <= 1600] or cands[:1]
        src = ok[-1][1]
    else:
        src = img.get("data-src") or img.get("data-lazy-src") or img.get("data-original") or img.get("src") or ""
    src = str(src).strip()
    if not src or src.startswith("data:"):
        return ""
    return urljoin(base, src)


_READABLE_SELECTORS = ("article", "main", "[role=main]", "#mw-content-text", "#content", "#main",
                       ".post-content", ".entry-content", ".article-body", ".article-content", ".post", ".story")
_JUNK_TAGS = ("script", "style", "noscript", "iframe", "form", "nav", "footer", "aside", "svg", "button",
              "input", "select", "textarea", "template", "dialog")


def _readable_root(soup):
    best, best_len = None, 0
    for sel in _READABLE_SELECTORS:
        try:
            for node in soup.select(sel):
                ln = sum(len(p.get_text(" ", strip=True)) for p in node.find_all("p"))
                if ln > best_len:
                    best, best_len = node, ln
        except Exception:
            continue
    if best is None or best_len < 200:
        body = soup.body or soup
        cands = [body] + body.find_all(["div", "section"], limit=400)
        for node in cands:
            ln = sum(len(p.get_text(" ", strip=True)) for p in node.find_all("p", recursive=False))
            if ln > best_len:
                best, best_len = node, ln
    node = best or soup.body or soup

    def plen(n) -> int:
        return sum(len(p.get_text(" ", strip=True)) for p in n.find_all("p"))
    cur = plen(node)
    for _ in range(12):  # descendre vers le bloc le plus serré qui garde l'essentiel du texte
        kids = node.find_all(["div", "section", "article", "main"], recursive=False)
        if not kids or cur <= 0:
            break
        best_kid = max(kids, key=plen)
        if plen(best_kid) >= 0.85 * cur:
            node = best_kid
        else:
            break
    return node


def readable_text(node) -> str:
    """Texte lisible (titres, paragraphes, listes, citations) depuis un nœud bs4."""
    out: List[str] = []
    for el in node.find_all(["h1", "h2", "h3", "h4", "p", "li", "blockquote", "pre", "figcaption", "dd", "dt"]):
        if el.find_parent(["li", "blockquote"]) and el.name in ("p",):
            continue
        t = re.sub(r"\s+", " ", el.get_text()).strip()
        t = re.sub(r"\s+([,.;:!?)»])", r"\1", t) if el.name != "pre" else t
        if not t or len(t) < 2:
            continue
        if el.name in ("h1", "h2", "h3", "h4"):
            t = ("#" * int(el.name[1])) + " " + t
        elif el.name == "li":
            t = "• " + t
        elif el.name == "blockquote":
            t = "« " + t + " »"
        if out and out[-1] == t:
            continue
        out.append(t)
    return "\n\n".join(out)


def _download_assets(urls: List[str], dest_dir: str, log: Callable[[str], None],
                     cancel_event: Optional[threading.Event]) -> Dict[str, str]:
    """Télécharge les images (limites de taille/nombre) → {url: nom_local}."""
    os.makedirs(dest_dir, exist_ok=True)
    out: Dict[str, str] = {}
    total = 0
    for i, u in enumerate(urls[:WEB_MAX_IMAGES]):
        _check_cancel(cancel_event)
        if u in out:
            continue
        try:
            data, final, ctype = http_fetch(u, timeout=20, max_bytes=WEB_MAX_IMAGE_BYTES)
        except Exception:
            continue
        if not data or (ctype and not ctype.lower().startswith("image/")):
            continue
        ext = os.path.splitext(urlparse(final).path)[1].lower()
        if ext not in IMAGE_EXTS + (".svg", ".avif", ".bmp"):
            ext = {"image/png": ".png", "image/gif": ".gif", "image/webp": ".webp", "image/svg+xml": ".svg",
                   "image/avif": ".avif"}.get(ctype.split(";")[0].lower(), ".jpg")
        name = f"img_{i + 1:03d}{ext}"
        with open(os.path.join(dest_dir, name), "wb") as f:
            f.write(data)
        out[u] = name
        total += len(data)
        if total > WEB_MAX_TOTAL_BYTES:
            log("Limite de 80 Mo d'images atteinte — reste de la page non téléchargé.")
            break
    return out


def browser_capture(url: str, folder: str, log: Callable[[str], None], timeout: int = 75) -> Dict[str, str]:
    """Capture PNG (haut de page) + PDF pleine page via Edge/Chrome headless (sans fenêtre)."""
    exe = find_browser()
    if not exe:
        log("Capture : Edge/Chrome introuvable — page HTML autonome seulement.")
        return {}
    import tempfile
    res: Dict[str, str] = {}
    prof = tempfile.mkdtemp(prefix="archiveur_nav_")
    common = [exe, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--mute-audio", "--no-first-run",
              "--no-default-browser-check", "--disable-extensions", "--disable-notifications",
              f"--user-data-dir={prof}", "--virtual-time-budget=9000", "--lang=fr-CA"]
    if not sys.platform.startswith("win"):
        common.insert(2, "--no-sandbox")
    jobs = [("capture_page.png", ["--window-size=1280,2400", "--screenshot={out}"]),
            ("page_complete.pdf", ["--no-pdf-header-footer", "--print-to-pdf={out}"])]
    try:
        for name, extra in jobs:
            out = os.path.join(folder, name)
            args = common + [a.replace("{out}", out) for a in extra] + [url]
            try:
                kw = _hidden_kwargs()
                p = subprocess.Popen(args, **kw)
                try:
                    p.communicate(timeout=timeout)
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.communicate(timeout=10)
                    log(f"Capture {name} : délai dépassé.")
            except Exception as e:
                log(f"Capture {name} impossible : {e}")
            if os.path.isfile(out) and os.path.getsize(out) > 1000:
                res[name] = out
                log(f"📸 {name} ({human_size(os.path.getsize(out))})")
        if "capture_page.png" in res and HAS_PIL_BACKEND:
            try:
                from PIL import Image as _Im
                im = _Im.open(res["capture_page.png"])
                im.load()
                # rogner le bas uni (page plus courte que 2400 px)
                gray = im.convert("L")
                w, h = gray.size
                px = gray.load()
                bottom = h
                ref = px[w // 2, h - 1]
                while bottom > 400:
                    row = [px[x, bottom - 1] for x in range(0, w, 16)]
                    if max(abs(v - ref) for v in row) > 8:
                        break
                    bottom -= 8
                if bottom < h - 40:
                    im.crop((0, 0, w, min(h, bottom + 24))).save(res["capture_page.png"])
            except Exception:
                logger.exception("rognage capture")
    finally:
        for _ in range(5):
            shutil.rmtree(prof, ignore_errors=True)
            if not os.path.isdir(prof):
                break
            time.sleep(0.6)
    return res


try:
    import PIL  # noqa: F401
    HAS_PIL_BACKEND = True
except Exception:
    HAS_PIL_BACKEND = False

_LECTURE_CSS = """
body{font-family:Georgia,'Segoe UI',serif;background:#f6f3ea;color:#222;margin:0;padding:0}
.wrap{max-width:780px;margin:auto;padding:1.5rem 1.2rem 4rem;line-height:1.65;font-size:1.08rem}
.top{font-family:Consolas,monospace;font-size:.85rem;background:#0000aa;color:#55ffff;padding:.6rem 1rem}
.top a{color:#ffff55} h1{line-height:1.25} img{max-width:100%;height:auto} figure{margin:1rem 0}
figcaption{font-size:.85rem;color:#555} pre{white-space:pre-wrap;background:#eee;padding:.6rem}
table{border-collapse:collapse;max-width:100%;display:block;overflow:auto} td,th{border:1px solid #ccc;padding:.2rem .4rem}
blockquote{border-left:4px solid #bbb;margin-left:0;padding-left:1rem;color:#444} a{color:#0b5cad}
"""


def archive_webpage(url: str, root: str, log: Callable[[str], None],
                    cancel_event: Optional[threading.Event] = None, capture: bool = True) -> Dict[str, Any]:
    """Page web complète : HTML autonome (images locales, CSS intégrée, sans scripts), version lecture,
    texte lisible (article.txt), liens, + capture PNG / PDF pleine page (Edge/Chrome headless si présent)."""
    from urllib.parse import urljoin
    if not module_available("bs4"):
        raise RuntimeError("Module beautifulsoup4 absent — archivage page complète indisponible.")
    _check_cancel(cancel_event)
    log(f"🌐 Archivage page web complète : {url}")
    raw, final_url, ctype = http_fetch(url)
    platform = detect_platform(final_url or url)
    stamp = datetime.now().strftime("%Y-%m-%d")
    host = (urlparse(final_url or url).hostname or "site").lower()
    if host.startswith("www."):
        host = host[4:]
    low_ct = ctype.lower()
    if low_ct and "html" not in low_ct and "xml" not in low_ct:
        # document direct (PDF, image…) : on garde le fichier tel quel
        name = os.path.basename(urlparse(final_url).path) or "document"
        title = pick_archive_title({"title": os.path.splitext(name)[0]})
        final_dir = _new_archive_dir(root, f"{stamp}_{platform}_{slugify(title)}_{slugify(host.replace('.', '-'), 24)}")
        with open(os.path.join(final_dir, slugify(os.path.splitext(name)[0], 60) + (os.path.splitext(name)[1] or ".bin")), "wb") as f:
            f.write(raw)
        info_out = {"title": title, "id": host, "uploader": host, "upload_date": "", "description": "",
                    "webpage_url": final_url or url, "url": url, "platform": platform, "tags": [], "notes": "",
                    "archived_at": datetime.now().isoformat(timespec="seconds"), "folder": os.path.basename(final_dir),
                    "media_files": [], "method": "web-document", "content_type": ctype}
        _write_json_atomic(os.path.join(final_dir, "info.json"), info_out)
        write_post_txt(os.path.join(final_dir, "post.txt"), info_out)
        write_local_index(final_dir, info_out)
        return info_out
    text = _decode_html(raw, ctype)
    soup = _soup(text)
    base = final_url or url
    btag = soup.find("base", href=True)
    if btag:
        base = urljoin(base, str(btag.get("href")))
    raw_title = (_meta(soup, "og:title", "twitter:title") or
                 (soup.title.get_text(" ", strip=True) if soup.title else "") or host)
    desc_meta = _meta(soup, "og:description", "description", "twitter:description")
    author = _meta(soup, "author", "article:author", "twitter:creator", "parsely-author")
    site = _meta(soup, "og:site_name", "application-name") or host
    published = _meta(soup, "article:published_time", "datePublished", "date", "dc.date", "pubdate")
    if not published:
        art = soup.find("article")
        t = art.find("time", attrs={"datetime": True}) if art else None
        if t and re.match(r"\d{4}-\d{2}-\d{2}", str(t.get("datetime"))):
            published = str(t.get("datetime"))
    og_image = _meta(soup, "og:image", "twitter:image")

    node = _readable_root(soup)
    article = readable_text(node)
    title = pick_archive_title({"title": raw_title, "description": article or desc_meta})
    final_dir = _new_archive_dir(root, f"{stamp}_{platform}_{slugify(title)}_{slugify(host.replace('.', '-'), 24)}")
    try:
        with open(os.path.join(final_dir, "page_original.html"), "wb") as f:
            f.write(raw)
        # liens de l'article
        links: List[List[str]] = []
        seen_links = set()
        for a in node.find_all("a", href=True):
            href = urljoin(base, str(a.get("href")))
            if not href.startswith(("http://", "https://")) or href in seen_links:
                continue
            seen_links.add(href)
            links.append([re.sub(r"\s+", " ", a.get_text(" ", strip=True))[:120], href])
            if len(links) >= 400:
                break
        # images : celles de l'article d'abord, puis le reste de la page
        img_urls: List[str] = []
        if og_image:
            img_urls.append(urljoin(base, og_image))
        for scope in (node, soup):
            for img in scope.find_all("img"):
                u = _best_src(img, base)
                if u and u not in img_urls:
                    img_urls.append(u)
        _check_cancel(cancel_event)
        log(f"Images détectées : {len(img_urls)} (max {WEB_MAX_IMAGES})")
        assets = _download_assets(img_urls, os.path.join(final_dir, WEB_ASSETS_DIR), log, cancel_event)
        if og_image and urljoin(base, og_image) in assets:
            src = os.path.join(final_dir, WEB_ASSETS_DIR, assets[urljoin(base, og_image)])
            ext = os.path.splitext(src)[1]
            if ext in IMAGE_EXTS:
                shutil.copy2(src, os.path.join(final_dir, "image" + ext))

        def rewrite(scope, prefix: str, junk: Tuple[str, ...] = ("script",)) -> None:
            for tag in scope.find_all(list(junk)):
                tag.decompose()
            for mt in scope.find_all("meta", attrs={"http-equiv": True}):
                mt.decompose()
            for tag in scope.find_all(True):
                for attr in list(tag.attrs):
                    if attr.lower().startswith("on"):
                        del tag[attr]
            for img in scope.find_all("img"):
                u = _best_src(img, base)
                if u in assets:
                    img["src"] = prefix + assets[u]
                elif u:
                    img["src"] = u
                for attr in ("srcset", "data-srcset", "data-src", "loading", "sizes", "data-lazy-src"):
                    if attr in img.attrs:
                        del img[attr]
            for src in scope.find_all("source"):
                src.decompose()
            for a in scope.find_all("a", href=True):
                href = str(a.get("href"))
                if not href.startswith("#"):
                    a["href"] = urljoin(base, href)
                    a["target"] = "_blank"
                    a["rel"] = "noopener"

        # --- page complète autonome (CSS intégrée, scripts retirés)
        full = _soup(text)
        css_parts: List[str] = []
        for i, link in enumerate(full.find_all("link", href=True)):
            rel = " ".join(link.get("rel") or []).lower()
            if "stylesheet" not in rel:
                if "preload" in rel or "modulepreload" in rel:
                    link.decompose()
                continue
            if i >= 60 or len(css_parts) >= WEB_MAX_CSS:
                link.decompose()
                continue
            href = urljoin(base, str(link.get("href")))
            try:
                css_raw, css_final, _ct = http_fetch(href, timeout=20, max_bytes=3 * 1024 * 1024)
                css = css_raw.decode("utf-8", errors="replace")
                css = re.sub(r"url\(\s*(['\"]?)(?!data:)([^)'\"]+)\1\s*\)",
                             lambda m: f"url('{urljoin(css_final, m.group(2).strip())}')", css)
                css_parts.append(f"/* {href} */\n{css}")
            except Exception:
                pass
            link.decompose()
        for b in full.find_all("base"):
            b.decompose()
        for ns in full.find_all("noscript"):
            ns.unwrap()
        rewrite(full, WEB_ASSETS_DIR + "/")
        head = full.head or full
        if css_parts:
            st = full.new_tag("style")
            st.string = "\n".join(css_parts)
            head.append(st)
        banner = _soup(
            f'<div style="font:13px Consolas,monospace;background:#0000aa;color:#55ffff;padding:6px 10px;'
            f'position:relative;z-index:99999">📦 Archivé par Archiveur le {html.escape(datetime.now().strftime("%Y-%m-%d %H:%M"))} — '
            f'<a style="color:#ffff55" href="{html.escape(final_url or url, quote=True)}" target="_blank">'
            f'{html.escape(final_url or url)}</a> · <a style="color:#ffff55" href="lecture.html">version lecture</a></div>'
        )
        if full.body and banner.div:
            full.body.insert(0, banner.div)
        with open(os.path.join(final_dir, "page.html"), "w", encoding="utf-8") as f:
            f.write(str(full))

        # --- version lecture (article seul, propre)
        node_copy = _soup(str(node))
        rewrite(node_copy, WEB_ASSETS_DIR + "/", _JUNK_TAGS)
        inner = node_copy.body.decode_contents() if node_copy.body else str(node_copy)
        e = html.escape
        lecture = (f'<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">'
                   f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(title)}</title>'
                   f'<style>{_LECTURE_CSS}</style></head><body>'
                   f'<div class="top">📦 Archiveur — {e(site)} · archivé le {e(datetime.now().strftime("%Y-%m-%d %H:%M"))} · '
                   f'<a href="{e(final_url or url, quote=True)}" target="_blank">original</a> · '
                   f'<a href="page.html">page complète</a> · <a href="index.html">fiche</a></div>'
                   f'<div class="wrap"><h1>{e(raw_title)}</h1>'
                   f'<p><em>{e(author or site)}{" · " + e(published[:10]) if published else ""}</em></p>{inner}</div></body></html>')
        with open(os.path.join(final_dir, "lecture.html"), "w", encoding="utf-8") as f:
            f.write(lecture)
        with open(os.path.join(final_dir, "article.txt"), "w", encoding="utf-8") as f:
            f.write(f"{raw_title}\n{final_url or url}\n\n{article}\n")

        shots: Dict[str, str] = {}
        if capture:
            _check_cancel(cancel_event)
            shots = browser_capture(final_url or url, final_dir, log)
    except ArchiveCancelled:
        shutil.rmtree(final_dir, ignore_errors=True)
        raise
    except Exception:
        shutil.rmtree(final_dir, ignore_errors=True)
        raise
    upload = ""
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", published or "")
    if m:
        upload = "".join(m.groups())
    info_out = {
        "title": title,
        "id": host,
        "uploader": author or site,
        "uploader_url": f"https://{host}/",
        "site_name": site,
        "upload_date": upload,
        "description": article[:300000] or desc_meta,
        "summary": desc_meta,
        "webpage_url": final_url or url,
        "url": url,
        "platform": platform,
        "tags": [],
        "notes": "",
        "archived_at": datetime.now().isoformat(timespec="seconds"),
        "folder": os.path.basename(final_dir),
        "media_files": [n for n in os.listdir(final_dir) if n.lower().endswith(MEDIA_EXTS)],
        "method": "web-page",
        "links": links,
        "page_images": len(assets),
        "page_capture": "capture_page.png" if "capture_page.png" in shots else "",
        "page_pdf": "page_complete.pdf" if "page_complete.pdf" in shots else "",
        "words": len(article.split()),
    }
    _write_json_atomic(os.path.join(final_dir, "info.json"), info_out)
    write_post_txt(os.path.join(final_dir, "post.txt"), info_out)
    write_local_index(final_dir, info_out)
    log(f"✅ Page archivée : {len(article.split())} mots, {len(assets)} image(s), "
        f"{'capture + PDF' if shots else 'sans capture'}")
    return info_out


def _new_archive_dir(root: str, folder_name: str) -> str:
    final_dir = os.path.join(root, folder_name)
    n = 2
    while os.path.exists(final_dir):
        final_dir = os.path.join(root, f"{folder_name}_{n}")
        n += 1
    os.makedirs(final_dir, exist_ok=True)
    return final_dir
