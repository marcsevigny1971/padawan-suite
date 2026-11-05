# -*- coding: utf-8 -*-
# Partie de archiveur5.py (découpage v1.2.2, comportement inchangé).
# Chargée par archiveur5.py dans un espace de noms commun : ne pas lancer seule.
from __future__ import annotations




# ================================================================= codecs / lecteurs
COMPAT_VCODECS = {"h264"}
COMPAT_ACODECS = {"aac", "mp3", ""}
COMPAT_PIXFMT = {"yuv420p", "yuvj420p", ""}


def find_ffprobe() -> Optional[str]:
    ff = find_ffmpeg()
    if ff:
        cand = os.path.join(os.path.dirname(ff), "ffprobe.exe" if sys.platform.startswith("win") else "ffprobe")
        if os.path.isfile(cand):
            return cand
    w = shutil.which("ffprobe")
    return os.path.abspath(w) if w else None


def probe_codecs(video: str) -> Dict[str, Any]:
    """{'vcodec','acodec','pix_fmt','duration','width','height'} via ffprobe (repli ffmpeg -i)."""
    out: Dict[str, Any] = {"vcodec": "", "acodec": "", "pix_fmt": "", "duration": None, "width": None, "height": None}
    fp = find_ffprobe()
    try:
        if fp:
            r = subprocess.run([fp, "-v", "error", "-show_entries",
                                "stream=codec_type,codec_name,pix_fmt,width,height:format=duration",
                                "-of", "json", video], **_hidden_kwargs(), timeout=30)
            data = json.loads((r.stdout or b"{}").decode("utf-8", errors="replace") or "{}")
            for st in data.get("streams") or []:
                if st.get("codec_type") == "video" and not out["vcodec"] and st.get("codec_name") not in ("mjpeg", "png", "webp"):
                    out["vcodec"] = str(st.get("codec_name") or "")
                    out["pix_fmt"] = str(st.get("pix_fmt") or "")
                    out["width"], out["height"] = st.get("width"), st.get("height")
                elif st.get("codec_type") == "audio" and not out["acodec"]:
                    out["acodec"] = str(st.get("codec_name") or "")
            try:
                out["duration"] = float((data.get("format") or {}).get("duration") or 0) or None
            except (TypeError, ValueError):
                pass
            return out
        ff = find_ffmpeg()
        if ff:
            r = subprocess.run([ff, "-hide_banner", "-i", video], **_hidden_kwargs(), timeout=30)
            err = (r.stderr or b"").decode("utf-8", errors="replace")
            m = re.search(r"Video:\s*([a-z0-9_]+)[^,\n]*(?:,\s*([a-z0-9_]+))?", err)
            if m:
                out["vcodec"], out["pix_fmt"] = m.group(1), (m.group(2) or "")
            m = re.search(r"Audio:\s*([a-z0-9_]+)", err)
            if m:
                out["acodec"] = m.group(1)
            out["duration"] = probe_duration(video)
    except Exception:
        logger.exception("probe_codecs %s", video)
    return out


def is_compatible(video: str, c: Optional[Dict[str, Any]] = None) -> bool:
    """True si lisible par le lecteur Windows sans extension : MP4 + H.264 (yuv420p) + AAC/MP3."""
    c = c if c is not None else probe_codecs(video)
    if not c.get("vcodec"):
        return True  # inconnu / pas de vidéo : on ne touche pas
    ext = os.path.splitext(video)[1].lower()
    return (ext in (".mp4", ".m4v", ".mov") and c.get("vcodec") in COMPAT_VCODECS
            and (c.get("acodec") or "") in COMPAT_ACODECS and (c.get("pix_fmt") or "") in COMPAT_PIXFMT)


def codec_label(c: Dict[str, Any]) -> str:
    v = {"av1": "AV1", "vp9": "VP9", "vp8": "VP8", "hevc": "HEVC (H.265)", "h264": "H.264"}.get(
        str(c.get("vcodec") or ""), str(c.get("vcodec") or "?").upper())
    a = str(c.get("acodec") or "")
    return f"{v} + {a.upper()}" if a else v


# ---------------------------------------------------------------- conversion rapide (oct. 2026)
# Encodeur matériel détecté une fois (test réel de 1 s), mis en cache dans archiveur_encodeur.json.
# Ordre : NVIDIA NVENC > Intel QSV > AMD AMF > Media Foundation (matériel Windows) > libx264 veryfast.
# Réglage optionnel dans archiveur_config.json : "video_encoder": "auto" (défaut) | "x264" | "h264_nvenc"…
ENC_CACHE_FILE = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "Archiveur",
                              "encodeur.json")  # cache hors du dossier web
ENC_CACHE_TTL = 7 * 86400
HW_ENCODERS = ["h264_nvenc", "h264_qsv", "h264_amf", "h264_mf"]
ENCODER_LABELS = {"h264_nvenc": "NVIDIA NVENC", "h264_qsv": "Intel Quick Sync", "h264_amf": "AMD AMF",
                  "h264_mf": "Media Foundation (GPU)", "libx264": "libx264 (processeur)"}
_ENC_LOCK = threading.Lock()
_ENC_MEM: Dict[str, Any] = {}


def _encoder_video_args(enc: str) -> List[str]:
    """Arguments vidéo par encodeur — qualité visuelle ~ libx264 crf 23."""
    if enc == "h264_nvenc":
        return ["-c:v", "h264_nvenc", "-preset", "p4", "-tune", "hq", "-rc", "vbr", "-cq", "23", "-b:v", "0",
                "-profile:v", "high", "-pix_fmt", "yuv420p"]
    if enc == "h264_qsv":
        return ["-c:v", "h264_qsv", "-preset", "faster", "-global_quality", "23", "-look_ahead", "0",
                "-pix_fmt", "nv12"]
    if enc == "h264_amf":
        return ["-c:v", "h264_amf", "-quality", "balanced", "-rc", "cqp", "-qp_i", "21", "-qp_p", "23",
                "-pix_fmt", "yuv420p"]
    if enc == "h264_mf":
        return ["-c:v", "h264_mf", "-hw_encoding", "1", "-rate_control", "quality", "-quality", "70",
                "-scenario", "archive", "-pix_fmt", "nv12"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-threads", "0", "-pix_fmt", "yuv420p"]


def _test_encoder(ff: str, enc: str) -> bool:
    """Encode 1 s d'une mire synthétique : vrai si l'encodeur fonctionne réellement sur ce PC."""
    try:
        r = subprocess.run([ff, "-hide_banner", "-nostdin", "-loglevel", "error", "-f", "lavfi",
                            "-i", "testsrc2=size=1280x720:rate=30", "-t", "1", *_encoder_video_args(enc),
                            "-f", "null", "-"], **_hidden_kwargs(), timeout=25)
        return r.returncode == 0
    except Exception:
        return False


def _encoder_pref() -> str:
    try:
        with open(CFG_FILE, "r", encoding="utf-8") as f:
            v = str((json.load(f) or {}).get("video_encoder") or "auto").strip().lower()
    except Exception:
        v = "auto"
    if v in ("x264", "libx264", "cpu", "logiciel"):
        return "libx264"
    return v if v in HW_ENCODERS else "auto"


def pick_video_encoder(log: Optional[Callable[[str], None]] = None, force: bool = False,
                       exclude: Optional[List[str]] = None) -> str:
    """Encodeur H.264 à utiliser (cache mémoire + fichier, re-test après 7 jours ou si ffmpeg change)."""
    ff = find_ffmpeg()
    if not ff:
        return "libx264"
    pref = _encoder_pref()
    if pref == "libx264":
        return "libx264"
    try:
        st = os.stat(ff)
        key = f"{os.path.abspath(ff)}|{int(st.st_mtime)}|{st.st_size}"
    except OSError:
        key = ff
    excl = set(exclude or [])
    with _ENC_LOCK:
        if not force and not excl:
            if _ENC_MEM.get("key") == key and _ENC_MEM.get("encoder"):
                enc = _ENC_MEM["encoder"]
                return pref if pref != "auto" and pref in (_ENC_MEM.get("ok") or []) else enc
            try:
                with open(ENC_CACHE_FILE, "r", encoding="utf-8") as f:
                    d = json.load(f)
                if (isinstance(d, dict) and d.get("key") == key and d.get("encoder")
                        and time.time() - float(d.get("time") or 0) < ENC_CACHE_TTL):
                    _ENC_MEM.clear()
                    _ENC_MEM.update(d)
                    enc = str(d["encoder"])
                    return pref if pref != "auto" and pref in (d.get("ok") or []) else enc
            except Exception:
                pass
        ok: List[str] = []
        order = ([pref] if pref != "auto" else []) + [e for e in HW_ENCODERS if e != pref]
        for enc in order:
            if enc in excl:
                continue
            if _test_encoder(ff, enc):
                ok.append(enc)
                if pref == "auto" or enc == pref:
                    break
        enc = ok[0] if ok else "libx264"
        d = {"key": key, "encoder": enc, "ok": ok, "excluded": sorted(excl), "time": time.time(),
             "date": datetime.now().isoformat(timespec="seconds")}
        _ENC_MEM.clear()
        _ENC_MEM.update(d)
        try:
            os.makedirs(os.path.dirname(ENC_CACHE_FILE), exist_ok=True)
            _write_json_atomic(ENC_CACHE_FILE, d)
        except Exception:
            pass
        if log:
            log(f"⚙ Encodeur vidéo détecté : {ENCODER_LABELS.get(enc, enc)}")
        return enc


def fmt_speed(x: Optional[float]) -> str:
    if not x or x <= 0:
        return ""
    return (f"{x:.1f}" if x < 10 else f"{x:.0f}").replace(".", ",") + "×"


def convert_to_compatible(video: str, log: Callable[[str], None],
                          progress: Optional[Callable[[float], None]] = None,
                          cancel_event: Optional[threading.Event] = None,
                          stats: Optional[Callable[[Dict[str, Any]], None]] = None) -> Dict[str, Any]:
    """MP4 H.264 + AAC compatible, le plus vite possible :
    - vidéo déjà H.264 (yuv420p) → copie (remux instantané) ; audio AAC/MP3 → copie, sinon AAC seul ;
    - sinon ré-encodage avec l'encodeur matériel détecté (repli automatique sur libx264 veryfast).
    Remplace le fichier (même nom, extension .mp4). Retourne {'ok', 'path', 'vcodec', 'acodec', 'before', ...}.
    stats(dict) reçoit pct, speed (×), eta (s), mode ('remux'|'audio'|'encode'), encoder, elapsed."""
    ff = find_ffmpeg()
    if not ff:
        raise RuntimeError("ffmpeg introuvable — conversion impossible.")
    c = probe_codecs(video)
    base = os.path.splitext(video)[0]
    final = base + ".mp4"
    tmp = base + ".h264.tmp"
    v_ok = c.get("vcodec") == "h264" and (c.get("pix_fmt") or "") in COMPAT_PIXFMT
    if not c.get("acodec"):
        aargs: List[str] = []
        a_ok = True
    elif c.get("acodec") in ("aac", "mp3"):
        aargs = ["-c:a", "copy"]
        a_ok = True
    else:
        aargs = ["-c:a", "aac", "-b:a", "160k"]
        a_ok = False
    mode = ("remux" if a_ok else "audio") if v_ok else "encode"
    enc = "copy" if v_ok else pick_video_encoder(log)
    dur = c.get("duration") or probe_duration(video) or 0
    t0 = time.time()

    def _emit(pct: float, speed: Optional[float] = None, done: bool = False) -> None:
        if not stats:
            return
        el = time.time() - t0
        eta = None
        if 0.5 < pct < 100 and el > 1.5:
            eta = el * (100.0 - pct) / pct
        try:
            stats({"pct": pct, "speed": speed, "eta": eta, "mode": mode, "encoder": enc,
                   "elapsed": el, "done": done})
        except Exception:
            pass

    def _cmd(e: str) -> List[str]:
        vargs = ["-c:v", "copy"] if e == "copy" else [*_encoder_video_args(e),
                                                       "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2"]
        return [ff, "-hide_banner", "-nostdin", "-y", "-i", video, "-map", "0:v:0", "-map", "0:a:0?",
                *vargs, *aargs, "-movflags", "+faststart", "-f", "mp4",
                "-progress", "pipe:1", "-nostats", "-loglevel", "error", tmp]

    def _run(e: str) -> Tuple[int, List[str], bool]:
        kw = _hidden_kwargs()
        kw["stderr"] = subprocess.STDOUT
        proc = subprocess.Popen(_cmd(e), **kw)
        errs: List[str] = []
        last = -1.0
        last_t = 0.0
        speed: Optional[float] = None
        cancelled = False
        try:
            for raw in iter(proc.stdout.readline, b""):  # type: ignore[union-attr]
                if cancel_event is not None and cancel_event.is_set():
                    cancelled = True
                    proc.kill()
                    break
                line = raw.decode("utf-8", errors="replace").strip()
                if line.startswith("speed="):
                    m = re.search(r"([\d.]+)\s*x", line)
                    if m:
                        try:
                            speed = float(m.group(1))
                        except ValueError:
                            pass
                elif line.startswith("out_time_us=") or line.startswith("out_time_ms="):
                    try:
                        us = int(line.split("=", 1)[1])
                    except ValueError:
                        continue
                    if dur:
                        pct = max(0.0, min(99.0, us / 1e6 / dur * 100.0))
                        now = time.time()
                        if progress and pct - last >= 1.0:
                            last = pct
                            progress(pct)
                        if now - last_t >= 0.4:
                            last_t = now
                            _emit(pct, speed)
                elif "=" not in line and line:
                    errs.append(line)
            proc.wait(timeout=60)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
            raise
        return proc.returncode, errs, cancelled

    what = {"remux": "remux instantané (copie)", "audio": "vidéo copiée, audio → AAC",
            "encode": f"ré-encodage {ENCODER_LABELS.get(enc, enc)}"}[mode]
    log(f"🎬 Conversion {os.path.basename(video)} ({codec_label(c)} → H.264 + AAC) — {what}…")
    _emit(0.0)
    rc, errs, cancelled = _run(enc)
    if (not cancelled and enc in HW_ENCODERS
            and (rc != 0 or not os.path.isfile(tmp) or os.path.getsize(tmp) == 0)):
        log(f"! Encodeur {ENCODER_LABELS.get(enc, enc)} en échec — repli sur libx264.")
        try:
            os.remove(tmp)
        except OSError:
            pass
        enc = pick_video_encoder(log, exclude=[enc])
        if enc != "libx264":
            enc = "libx264"  # sécurité : on ne retente pas un 2e matériel au milieu d'une conversion
        _emit(0.0)
        rc, errs, cancelled = _run(enc)
    if cancelled:
        try:
            os.remove(tmp)
        except OSError:
            pass
        log("⛔ Conversion annulée — fichier original gardé.")
        return {"ok": False, "cancelled": True, "path": video, "before": c}
    if rc != 0 or not os.path.isfile(tmp) or os.path.getsize(tmp) == 0:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise RuntimeError("ffmpeg a échoué : " + (" | ".join(errs[-3:]) or f"code {rc}"))
    try:
        os.replace(tmp, final)
        if os.path.abspath(final) != os.path.abspath(video) and os.path.exists(video):
            os.remove(video)
    except OSError as e:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise OSError(f"Fichier verrouillé (ouvert dans un lecteur ?) — fermez-le et réessayez.\n{e}") from e
    after = probe_codecs(final)
    if progress:
        progress(100.0)
    el = time.time() - t0
    _emit(100.0, (dur / el) if dur and el > 0 else None, done=True)
    log(f"✅ MP4 compatible : {os.path.basename(final)} ({codec_label(after)}) en {el:.0f} s"
        + (f" — {fmt_speed(dur / el)}" if dur and el > 0 else "")
        + ("" if enc == "copy" else f" · {ENCODER_LABELS.get(enc, enc)}"))
    return {"ok": True, "path": final, "vcodec": after.get("vcodec"), "acodec": after.get("acodec"),
            "before": c, "mode": mode, "encoder": enc, "seconds": el}


def _refresh_index_entry(root: str, folder: str) -> None:
    fp = os.path.join(root, folder)
    info = load_info(fp)
    entries = load_archive_index(root)
    for e in entries:
        if e.get("folder") == folder:
            fresh = entry_from_info(info, fp) if info else {}
            e["size"] = fresh.get("size", folder_size(fp))
            e["thumb"] = fresh.get("thumb", e.get("thumb", ""))
    save_archive_index(root, entries)


def fix_folder_codecs(folder_path: str, log: Callable[[str], None],
                      progress: Optional[Callable[[float], None]] = None,
                      cancel_event: Optional[threading.Event] = None,
                      update_index: bool = True,
                      stats: Optional[Callable[[Dict[str, Any]], None]] = None) -> str:
    """'ok' (converti), 'skip' (déjà compatible / pas de vidéo), 'cancel'. Lève en cas d'échec."""
    main = find_main_media(folder_path)
    if not main or not main.lower().endswith(VIDEO_EXTS):
        return "skip"
    c = probe_codecs(main)
    if is_compatible(main, c):
        return "skip"
    r = convert_to_compatible(main, log, progress=progress, cancel_event=cancel_event, stats=stats)
    if not r.get("ok"):
        return "cancel"
    info = load_info(folder_path)
    if info:
        info["vcodec"], info["acodec"] = r.get("vcodec"), r.get("acodec")
        info["converted_h264"] = datetime.now().isoformat(timespec="seconds")
        info["media_files"] = [n for n in os.listdir(folder_path) if n.lower().endswith(MEDIA_EXTS)]
        _write_json_atomic(os.path.join(folder_path, "info.json"), info)
        write_local_index(folder_path, info)
    if update_index:
        root, folder = os.path.split(os.path.abspath(folder_path))
        try:
            _refresh_index_entry(root, folder)
        except Exception:
            logger.exception("index après conversion")
    return "ok"


def scan_incompatible(root: str) -> List[Tuple[str, str]]:
    """[(folder, 'AV1 + OPUS'), …] des archives dont la vidéo n'est pas MP4 H.264/AAC."""
    out = []
    for e in sync_index_with_disk(root):
        fp = os.path.join(root, str(e.get("folder") or ""))
        main = find_main_media(fp)
        if main and main.lower().endswith(VIDEO_EXTS):
            c = probe_codecs(main)
            if not is_compatible(main, c):
                out.append((str(e.get("folder")), codec_label(c)))
    return out


def fix_codecs_all(root: str, log: Callable[[str], None],
                   cancel_event: Optional[threading.Event] = None) -> Dict[str, int]:
    stats = {"ok": 0, "skip": 0, "fail": 0}
    todo = scan_incompatible(root)
    log(f"Réparation codecs : {len(todo)} vidéo(s) à convertir.")
    for folder, lab in todo:
        if cancel_event is not None and cancel_event.is_set():
            break
        try:
            r = fix_folder_codecs(os.path.join(root, folder), log, cancel_event=cancel_event, update_index=False)
            stats["ok" if r == "ok" else "skip"] += 1
        except Exception as ex:
            logger.exception("fix codecs %s", folder)
            log(f"❌ {folder} : {friendly_error(ex)}")
            stats["fail"] += 1
    entries = sync_index_with_disk(root)
    for e in entries:
        fp = os.path.join(root, str(e.get("folder")))
        if os.path.isdir(fp):
            e["size"] = folder_size(fp)
    save_archive_index(root, entries)
    return stats


PLAYER_LABELS = {"windows": "Windows (défaut)", "vlc": "VLC", "mpv": "mpv"}


def detect_players() -> Dict[str, str]:
    """{'vlc': exe, 'mpv': exe} selon les chemins usuels."""
    found: Dict[str, str] = {}
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    pfx = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    la = os.environ.get("LOCALAPPDATA", "")
    home = os.path.expanduser("~")
    cands = {
        "vlc": [os.path.join(pf, "VideoLAN", "VLC", "vlc.exe"), os.path.join(pfx, "VideoLAN", "VLC", "vlc.exe"),
                os.path.join(la, "Programs", "VideoLAN", "VLC", "vlc.exe"), shutil.which("vlc") or ""],
        "mpv": [shutil.which("mpv") or "", os.path.join(la, "Programs", "mpv", "mpv.exe"),
                os.path.join(pf, "mpv", "mpv.exe"), os.path.join(home, "scoop", "shims", "mpv.exe"),
                os.path.join(la, "Microsoft", "WinGet", "Links", "mpv.exe"), r"C:\mpv\mpv.exe"],
    }
    for name, paths in cands.items():
        for p in paths:
            if p and os.path.isfile(p):
                found[name] = os.path.abspath(p)
                break
    return found


def open_media(path: str, player: str = "windows") -> Tuple[bool, str]:
    """Ouvre un média avec le lecteur choisi (VLC/mpv si installé), sinon le lecteur Windows."""
    if player in ("vlc", "mpv") and path.lower().endswith(VIDEO_EXTS + AUDIO_EXTS):
        exe = detect_players().get(player)
        if exe:
            try:
                kw: Dict[str, Any] = {"close_fds": True, "stdin": subprocess.DEVNULL,
                                      "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
                if sys.platform.startswith("win"):
                    kw["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0) | CREATE_NO_WINDOW
                subprocess.Popen([exe, os.path.abspath(path)], **kw)
                return True, ""
            except Exception as e:
                logger.exception("lecteur %s", player)
                return open_path_explorer(path) if os.path.exists(path) else (False, str(e))
    return open_path_explorer(path)


# ================================================================= v5 : utilitaires communs
def _python_console_exe() -> str:
    """python.exe (pas pythonw) pour pip / sous-process, sans console grâce à CREATE_NO_WINDOW."""
    py = sys.executable or "python"
    if py.lower().endswith("pythonw.exe"):
        cand = py[:-len("pythonw.exe")] + "python.exe"
        if os.path.isfile(cand):
            return cand
    return py


def fmt_ts(sec: Any) -> str:
    """Horodatage court : m:ss ou h:mm:ss."""
    try:
        s = max(0, int(float(sec)))
    except Exception:
        return "0:00"
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def parse_timecode(text: Any) -> Optional[float]:
    """« 1:23 », « 01:02:03.5 », « 83 », « 83,5 », « 1m23s » → secondes (None si invalide)."""
    s = str(text or "").strip().lower().replace(",", ".")
    if not s:
        return None
    m = re.fullmatch(r"(?:(\d+)h)?\s*(?:(\d+)m(?:in)?)?\s*(?:(\d+(?:\.\d+)?)s?)?", s)
    if m and any(m.groups()) and not re.fullmatch(r"\d+(?:\.\d+)?", s):
        h, mi, se = m.groups()
        return int(h or 0) * 3600 + int(mi or 0) * 60 + float(se or 0)
    parts = s.split(":")
    try:
        nums = [float(p) for p in parts]
    except ValueError:
        return None
    if len(nums) > 3 or any(n < 0 for n in nums):
        return None
    total = 0.0
    for n in nums:
        total = total * 60 + n
    return total


def _ff_label(sec: float) -> str:
    """Horodatage pour nom de fichier : 01m05s / 1h02m03s."""
    s = max(0, int(round(sec)))
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h{m:02d}m{s:02d}s" if h else f"{m:02d}m{s:02d}s"


def _unique_path(path: str) -> str:
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    n = 2
    while os.path.exists(f"{base}_{n}{ext}"):
        n += 1
    return f"{base}_{n}{ext}"


def find_ffplay() -> Optional[str]:
    ff = find_ffmpeg()
    if ff:
        cand = os.path.join(os.path.dirname(ff), "ffplay.exe" if sys.platform.startswith("win") else "ffplay")
        if os.path.isfile(cand):
            return cand
    w = shutil.which("ffplay")
    return os.path.abspath(w) if w else None


def find_browser() -> Optional[str]:
    """Edge / Chrome / Chromium (mode headless) pour capture et PDF pleine page."""
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    pfx = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    la = os.environ.get("LOCALAPPDATA", "")
    cands = [
        os.path.join(pfx, "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(pf, "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(pf, "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(pfx, "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(la, "Google", "Chrome", "Application", "chrome.exe") if la else "",
    ]
    for name in ("msedge", "google-chrome", "chromium", "chromium-browser", "chrome"):
        w = shutil.which(name)
        if w:
            cands.append(w)
    for c in cands:
        if c and os.path.isfile(c):
            return os.path.abspath(c)
    return None


def module_available(name: str) -> bool:
    try:
        import importlib.util
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def whisper_available() -> bool:
    return module_available("faster_whisper")


def ytdlp_version() -> str:
    try:
        import yt_dlp  # type: ignore
        return str(yt_dlp.version.__version__)
    except Exception:
        return ""


def update_ytdlp(log: Callable[[str], None]) -> Tuple[bool, str, str]:
    """pip install -U yt-dlp (sans console). Retourne (ok, ancienne, nouvelle version)."""
    old = ytdlp_version()
    py = _python_console_exe()
    log(f"Mise à jour de yt-dlp (actuelle : {old or 'absente'})…")
    try:
        r = subprocess.run([py, "-m", "pip", "install", "-U", "--disable-pip-version-check", "yt-dlp"],
                           **_hidden_kwargs(), timeout=600)
        out = (r.stdout or b"").decode("utf-8", errors="replace")
        err = (r.stderr or b"").decode("utf-8", errors="replace")
        if r.returncode != 0:
            log(f"pip yt-dlp échec : {(err or out).strip()[-400:]}")
            return False, old, old
        r2 = subprocess.run([py, "-c", "import yt_dlp;print(yt_dlp.version.__version__)"],
                            **_hidden_kwargs(), timeout=60)
        new = (r2.stdout or b"").decode("utf-8", errors="replace").strip() or old
        log(f"yt-dlp : {old or '—'} → {new}")
        return True, old, new
    except Exception as e:
        log(f"Mise à jour yt-dlp impossible : {e}")
        return False, old, old


# ---------------------------------------------------------------- instance unique (Windows)
_INSTANCE_MUTEX = None
_MUTEX_NAME = "Local\\ArchiveurPadawanUnique"
