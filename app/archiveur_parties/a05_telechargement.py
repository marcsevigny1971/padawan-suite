# -*- coding: utf-8 -*-
# Partie de archiveur5.py (découpage v1.2.2, comportement inchangé).
# Chargée par archiveur5.py dans un espace de noms commun : ne pas lancer seule.
from __future__ import annotations

_YTDLP_NOISE = re.compile(
    r"(Video Thumbnail \d+ does not exist|Downloading video thumbnail \d+|^\[download\]\s+\d+(\.\d+)?%)", re.I)


class YTDLPLogger:
    def __init__(self, log: Callable[[str], None]):
        self._log = log

    def debug(self, msg):
        if msg and not str(msg).startswith("[debug]") and not _YTDLP_NOISE.search(str(msg)):
            self._log(str(msg))

    def info(self, msg):
        if msg and not _YTDLP_NOISE.search(str(msg)):
            self._log(str(msg))

    def warning(self, msg):
        if msg:
            self._log(f"! {msg}")

    def error(self, msg):
        if msg:
            self._log(f"X {msg}")



# Tri yt-dlp : H.264 (avc1) + AAC (m4a) en MP4 d'abord → lisible par le lecteur Windows
# sans codec AV1/VP9 ; ensuite la meilleure résolution parmi ceux-là.
FORMAT_SORT_COMPAT = ["vcodec:h264", "acodec:aac", "res", "ext:mp4:m4a"]


def build_format_candidates(quality: str, has_ff: bool) -> List[str]:
    h = {"720": 720, "480": 480}.get(str(quality))
    if quality == "audio":
        return ["ba/b"] if has_ff else ["ba[ext=m4a]/ba/b"]
    if has_ff:
        if h:
            return [f"bv*[height<={h}]+ba/b[height<={h}]/bv*+ba/b"]
        return ["bv*+ba/b"]
    if h:
        return [
            f"b[height<={h}][acodec!=none][vcodec!=none][ext=mp4]/b[height<={h}][acodec!=none][vcodec!=none]/b[acodec!=none][vcodec!=none]",
            "18/best",
        ]
    return [
        "b*[acodec!=none][vcodec!=none][ext=mp4]/b[acodec!=none][vcodec!=none]/best[acodec!=none][vcodec!=none]",
        "18/22/best[height<=720][ext=mp4]/worst[ext=mp4]/best",
    ]


def _check_cancel(cancel_event: Optional[threading.Event]) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise ArchiveCancelled("Archivage annulé par l'utilisateur.")


def archive_with_ytdlp(
    url: str,
    root: str,
    log: Callable[[str], None],
    *,
    cookies_browser: Optional[str] = None,
    progress_hook: Optional[Callable[[Dict[str, Any]], None]] = None,
    quality: str = "best",
    subtitles: bool = True,
    storyboard: bool = True,
    cancel_event: Optional[threading.Event] = None,
    auto_convert: bool = True,
) -> Dict[str, Any]:
    import yt_dlp

    platform = detect_platform(url)
    ff_exe = find_ffmpeg()
    has_ff = ff_exe is not None
    ff_dir = os.path.dirname(ff_exe) if ff_exe else ffmpeg_location()
    if ff_dir:
        _prepend_path(ff_dir)
    if not has_ff:
        log("Sans ffmpeg: formats déjà combinés uniquement (pas de fusion).")
    format_candidates = build_format_candidates(quality, has_ff)

    def _hook(d: Dict[str, Any]) -> None:
        _check_cancel(cancel_event)
        if progress_hook:
            progress_hook(d)

    stamp = datetime.now().strftime("%Y-%m-%d")
    tmp_name = f"_tmp_{stamp}_{os.getpid()}_{threading.get_ident()}"
    out_tmp = os.path.join(root, tmp_name)
    os.makedirs(out_tmp, exist_ok=True)
    outtmpl = os.path.join(out_tmp, "%(title).80B [%(id)s].%(ext)s")

    info: Dict[str, Any] = {}
    last_err: Optional[BaseException] = None
    attempts = list(format_candidates)
    subs_on = bool(subtitles)
    ai = 0
    while ai < len(attempts):
        fmt = attempts[ai]
        ai += 1
        opts: Dict[str, Any] = {
            "outtmpl": outtmpl,
            "format": fmt,
            "writesubtitles": subs_on,
            "writeautomaticsub": subs_on,
            "subtitleslangs": ["fr", "fr-FR", "fr-CA", "en", "en-US"],
            "subtitlesformat": "vtt/srt/best",
            "writethumbnail": True,
            "writeinfojson": True,
            "writedescription": True,
            "noplaylist": True,
            "ignoreerrors": False,
            "quiet": True,
            "no_warnings": False,
            "noprogress": True,
            "logger": YTDLPLogger(log),
            "progress_hooks": [_hook],
            "http_headers": {"User-Agent": USER_AGENT},
        }
        if quality != "audio":
            opts["format_sort"] = list(FORMAT_SORT_COMPAT)
        if has_ff:
            if quality == "audio":
                opts["postprocessors"] = [{
                    "key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192",
                }]
            else:
                opts["merge_output_format"] = "mp4"
            if ff_dir:
                opts["ffmpeg_location"] = ff_dir
        if cookies_browser:
            opts["cookiesfrombrowser"] = (cookies_browser,)
        try:
            _check_cancel(cancel_event)
            log(f"yt-dlp format: {fmt}  (qualité: {LABEL_BY_QUALITY.get(quality, quality)})")
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True) or {}
                if "entries" in info and info["entries"]:
                    info = info["entries"][0] or info
            last_err = None
            break
        except BaseException as e:  # noqa: B902 — inclut ArchiveCancelled levé dans le hook
            if isinstance(e, (KeyboardInterrupt, SystemExit)):
                raise
            if isinstance(e, ArchiveCancelled) or (cancel_event is not None and cancel_event.is_set()):
                shutil.rmtree(out_tmp, ignore_errors=True)
                raise ArchiveCancelled("Archivage annulé par l'utilisateur.") from None
            last_err = e
            if subs_on and "subtitle" in str(e).lower():
                log("! Sous-titres refusés par le site (souvent 429) — nouvel essai sans sous-titres.")
                subs_on = False
                ai -= 1
            else:
                log(f"yt-dlp essai format échoué: {e}")
            try:
                for name in list(os.listdir(out_tmp)):
                    try:
                        os.remove(os.path.join(out_tmp, name))
                    except OSError:
                        pass
            except OSError:
                pass
    if last_err is not None or not info:
        err = str(last_err or "aucune info")
        log(f"yt-dlp: {err}")
        shutil.rmtree(out_tmp, ignore_errors=True)
        raise last_err if last_err else RuntimeError(err)

    raw_title = info.get("title") or info.get("id") or "sans-titre"
    title = pick_archive_title({
        "title": raw_title,
        "description": info.get("description") or "",
        "text": info.get("description") or "",
        "uploader": info.get("uploader") or info.get("creator") or info.get("channel"),
        "id": info.get("id") or "id",
    })
    vid = info.get("id") or "id"
    folder_name = f"{stamp}_{platform}_{slugify(title)}_{slugify(str(vid), 20)}"
    final_dir = os.path.join(root, folder_name)
    n = 2
    while os.path.exists(final_dir):
        final_dir = os.path.join(root, f"{folder_name}_{n}")
        n += 1
    os.rename(out_tmp, final_dir)

    vcodec_out, acodec_out = info.get("vcodec"), info.get("acodec")
    converted_at = ""
    if quality != "audio" and has_ff:
        main_v = find_main_media(final_dir)
        if main_v and main_v.lower().endswith(VIDEO_EXTS):
            try:
                c = probe_codecs(main_v)
                if c.get("vcodec"):
                    vcodec_out, acodec_out = c.get("vcodec"), c.get("acodec") or acodec_out
                if auto_convert and c.get("vcodec") and not is_compatible(main_v, c):
                    log(f"🎬 Vidéo {codec_label(c)} → conversion MP4 compatible (H.264/AAC)…")

                    def _cstats(s):
                        if progress_hook:
                            try:
                                progress_hook({"status": "converting", **s})
                            except Exception:
                                pass
                    r = convert_to_compatible(main_v, log, cancel_event=cancel_event, stats=_cstats)
                    if r.get("ok"):
                        vcodec_out, acodec_out = r.get("vcodec"), r.get("acodec")
                        converted_at = datetime.now().isoformat(timespec="seconds")
            except Exception as ce:
                logger.exception("conversion")
                log(f"! Conversion MP4 impossible ({ce}) — fichier original gardé.")

    media_files = [n for n in os.listdir(final_dir) if n.lower().endswith(MEDIA_EXTS)]
    w, h = info.get("width"), info.get("height")
    resolution = f"{w}x{h}" if w and h else (info.get("resolution") or "")
    if quality == "audio":
        resolution = "audio"
    info_out = {
        "title": title,
        "id": vid,
        "uploader": info.get("uploader") or info.get("creator") or info.get("channel"),
        "uploader_url": info.get("uploader_url") or info.get("channel_url") or "",
        "channel": info.get("channel") or "",
        "channel_url": info.get("channel_url") or "",
        "upload_date": info.get("upload_date") or "",
        "description": info.get("description") or "",
        "webpage_url": info.get("webpage_url") or url,
        "url": url,
        "platform": platform,
        "extractor": info.get("extractor"),
        "duration": info.get("duration"),
        "resolution": resolution,
        "fps": info.get("fps"),
        "vcodec": vcodec_out,
        "acodec": acodec_out,
        "converted_h264": converted_at,
        "view_count": info.get("view_count"),
        "like_count": info.get("like_count"),
        "source_tags": (info.get("tags") or [])[:30],
        "tags": [],
        "notes": "",
        "quality": quality,
        "archived_at": datetime.now().isoformat(timespec="seconds"),
        "folder": os.path.basename(final_dir),
        "media_files": media_files,
        "method": "yt-dlp",
    }
    if storyboard and quality != "audio":
        try:
            frames = generate_storyboard(final_dir, SB_FRAMES, duration=info.get("duration"))
            if frames:
                log(f"Storyboard: {len(frames)} images")
        except Exception:
            logger.exception("storyboard")
    try:
        tr = build_transcript(final_dir, force=True)
        if tr and tr.get("cues"):
            info_out["transcript_lang"] = tr.get("lang") or ""
            info_out["transcript_source"] = "sous-titres"
            log(f"🗣 Transcription : {len(tr['cues'])} lignes ({tr.get('lang') or '?'})")
    except Exception:
        logger.exception("transcription sous-titres")
    _write_json_atomic(os.path.join(final_dir, "info.json"), info_out)
    write_post_txt(os.path.join(final_dir, "post.txt"), info_out)
    write_local_index(final_dir, info_out)
    return info_out


def archive_fallback_html(
    url: str,
    root: str,
    log: Callable[[str], None],
    cancel_event: Optional[threading.Event] = None,
) -> Dict[str, Any]:
    platform = detect_platform(url)
    log(f"Fallback HTML pour {platform}: {url}")
    _check_cancel(cancel_event)
    raw = http_get(url)
    try:
        text = raw.decode("utf-8")
    except Exception:
        text = raw.decode("latin-1", errors="replace")
    og = extract_og(text)
    raw_title = og.get("og:title") or og.get("twitter:title") or "sans-titre"
    desc = og.get("og:description") or og.get("twitter:description") or ""
    title = pick_archive_title({"title": raw_title, "description": desc, "text": desc})
    stamp = datetime.now().strftime("%Y-%m-%d")
    folder_name = f"{stamp}_{platform}_{slugify(title)}_html"
    final_dir = os.path.join(root, folder_name)
    n = 2
    while os.path.exists(final_dir):
        final_dir = os.path.join(root, f"{folder_name}_{n}")
        n += 1
    os.makedirs(final_dir, exist_ok=True)
    with open(os.path.join(final_dir, "page.html"), "w", encoding="utf-8") as f:
        f.write(text)
    media_files: List[str] = []
    seen_urls = set()
    for key, prefix in (("og:image", "image"), ("twitter:image", "twimage"), ("og:video", "video"), ("og:video:url", "video2")):
        media_url = og.get(key)
        if not media_url or media_url in seen_urls:
            continue
        seen_urls.add(media_url)
        try:
            _check_cancel(cancel_event)
            data = http_get(media_url)
            ext = os.path.splitext(urlparse(media_url).path)[1] or (".mp4" if "video" in key else ".jpg")
            if len(ext) > 5:
                ext = ".bin"
            fname = f"{prefix}{ext}"
            with open(os.path.join(final_dir, fname), "wb") as f:
                f.write(data)
            media_files.append(fname)
            log(f"Média sauvé: {fname}")
        except ArchiveCancelled:
            shutil.rmtree(final_dir, ignore_errors=True)
            raise
        except Exception as e:
            log(f"Échec média {key}: {e}")
    info_out = {
        "title": title,
        "id": "",
        "uploader": "",
        "upload_date": "",
        "description": desc,
        "text": desc,
        "webpage_url": og.get("og:url") or url,
        "url": url,
        "platform": platform,
        "tags": [],
        "notes": "",
        "archived_at": datetime.now().isoformat(timespec="seconds"),
        "folder": os.path.basename(final_dir),
        "media_files": media_files,
        "method": "html-fallback",
        "links": [[u, u] for u in extract_urls(desc)],
        "note": "Archivage best-effort (métadonnées Open Graph). Login/DRM peuvent bloquer le média.",
    }
    _write_json_atomic(os.path.join(final_dir, "info.json"), info_out)
    write_post_txt(os.path.join(final_dir, "post.txt"), info_out)
    write_local_index(final_dir, info_out)
    return info_out


def _embed_attach_safe(root: str, info: Dict[str, Any], url: str, log: Callable[[str], None]) -> Dict[str, Any]:
    """Aperçu oEmbed/OpenGraph + lecteur officiel (padawan_embeds) ; n'empêche jamais l'archivage."""
    try:
        return embed_attach(root, info, url, log)
    except Exception:
        logger.exception("embed_attach")
        return info


def archive_url(
    url: str,
    root: str,
    log: Callable[[str], None],
    *,
    cookies_browser: Optional[str] = None,
    progress_hook: Optional[Callable[[Dict[str, Any]], None]] = None,
    quality: str = "best",
    subtitles: bool = True,
    storyboard: bool = True,
    cancel_event: Optional[threading.Event] = None,
    tags: Any = None,
    notes: str = "",
    auto_convert: bool = True,
    web_capture: bool = True,
    use_fx: bool = True,
    page_mode: bool = False,
) -> Dict[str, Any]:
    url = (url or "").strip()
    if not url:
        raise ValueError("URL vide")
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    os.makedirs(root, exist_ok=True)
    platform = detect_platform(url)
    log(f"> Archivage ({platform}): {url}")
    emb = embed_detect(url)
    if page_mode:
        info = archive_webpage(url, root, log, cancel_event=cancel_event, capture=web_capture)
        info = _embed_attach_safe(root, info, url, log)
        if tags or notes:
            info = update_tags_notes(root, str(info["folder"]), tags or [], notes or "")
        return info
    if emb.get("protected"):
        # site protégé (DRM) : aucun téléchargement de la vidéo, on garde la page, l'aperçu et le lien
        log(f"🔒 {emb.get('label') or 'Site protégé'} : contenu protégé (DRM). "
            "L'Archiveur garde l'aperçu + le lien ; regarde-le sur le site officiel.")
        try:
            info = archive_webpage(url, root, log, cancel_event=cancel_event, capture=web_capture)
        except ArchiveCancelled:
            raise
        except Exception as ex:
            log(f"Page web complète impossible ({friendly_error(ex)}) — repli métadonnées.")
            info = archive_fallback_html(url, root, log, cancel_event=cancel_event)
        info = _embed_attach_safe(root, info, url, log)
        if tags or notes:
            info = update_tags_notes(root, str(info["folder"]), tags or [], notes or "")
        return info
    try:
        info = archive_with_ytdlp(
            url, root, log, cookies_browser=cookies_browser, progress_hook=progress_hook,
            quality=quality, subtitles=subtitles, storyboard=storyboard, cancel_event=cancel_event,
            auto_convert=auto_convert,
        )
    except ArchiveCancelled:
        raise
    except Exception as e1:
        log(f"yt-dlp a échoué ({e1})")
        info = None
        if platform == "x" and use_fx:
            log("Post X sans vidéo (ou bloqué) → texte, photos et fil via fxtwitter…")
            try:
                info = archive_x_fx(url, root, log, cancel_event=cancel_event)
            except ArchiveCancelled:
                raise
            except Exception as ex:
                log(f"fxtwitter : {ex}")
        if info is None and platform == "web":
            try:
                info = archive_webpage(url, root, log, cancel_event=cancel_event, capture=web_capture)
            except ArchiveCancelled:
                raise
            except Exception as ex:
                logger.exception("page web")
                log(f"Page web complète impossible ({friendly_error(ex)}) — repli métadonnées.")
        if info is None and platform in ("x", "facebook", "instagram", "web"):
            log("Tentative fallback HTML (limites login/DRM possibles)…")
            try:
                info = archive_fallback_html(url, root, log, cancel_event=cancel_event)
            except ArchiveCancelled:
                raise
            except Exception as e2:
                raise RuntimeError(
                    f"Échec yt-dlp et fallback HTML.\n"
                    f"yt-dlp: {e1}\nfallback: {e2}\n"
                    "Pour X/Facebook privés: cochez cookies navigateur, ou la page exige un login/DRM."
                ) from e2
        elif info is None:
            raise
    else:
        if platform == "x" and use_fx:
            enrich_x_thread(os.path.join(root, str(info.get("folder"))), url, log)
            info = load_info(os.path.join(root, str(info.get("folder")))) or info
    info = _embed_attach_safe(root, info, url, log)
    if tags or notes:
        info = update_tags_notes(root, str(info["folder"]), tags or [], notes or "")
    return info
