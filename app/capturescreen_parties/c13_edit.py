# -*- coding: utf-8 -*-
"""CaptureScreen - c13 : petit montage (toujours un NOUVEAU fichier, l'original n'est jamais touche).
Version « pour partager » (720p legere), extrait MP4 ou GIF, enlever un passage du milieu, joindre des videos,
ameliorer le son (bruit de fond + volume), incruster les sous-titres, garder seulement le son (MP3)."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import datetime

from .c01_config import find_ffmpeg, logger, pick_encoder, run_hidden, video_codec_args

CLEAN_AUDIO = "highpass=f=80,afftdn=nf=-25,loudnorm=I=-16:TP=-1.5:LRA=11"  # bruit de fond + volume regulier
LONG = 6 * 3600


def _unique(path: str) -> str:
    base, ext = os.path.splitext(path)
    i, p = 2, path
    while os.path.exists(p):
        p = f"{base} ({i}){ext}"
        i += 1
    return p


def _out(src: str, suffix: str, ext: str = "") -> str:
    base, e = os.path.splitext(src)
    return _unique(f"{base} ({suffix}){ext or e}")


def probe(path: str) -> dict:
    fp = find_ffmpeg("ffprobe")
    r = run_hidden([fp, "-v", "error", "-show_entries", "stream=codec_type,width,height,r_frame_rate:format=duration",
                    "-of", "json", path], timeout=30)
    d = json.loads((r.stdout or b"{}").decode("utf-8", "replace") or "{}")
    st = d.get("streams") or []
    v = next((s for s in st if s.get("codec_type") == "video"), {})
    fr = str(v.get("r_frame_rate") or "30/1").split("/")
    try:
        fps = float(fr[0]) / float(fr[1] if len(fr) > 1 else 1)
    except Exception:
        fps = 30.0
    return {"duration": float((d.get("format") or {}).get("duration") or 0), "has_video": bool(v),
            "has_audio": any(s.get("codec_type") == "audio" for s in st), "w": v.get("width") or 0,
            "h": v.get("height") or 0, "fps": max(1, min(60, round(fps)))}


def _venc(ff, quality="bonne", fps=30):
    return video_codec_args(pick_encoder(ff), quality, fps)


def _run(cmd, out, what):
    r = run_hidden(cmd, timeout=LONG)
    if r.returncode != 0 or not os.path.isfile(out) or os.path.getsize(out) == 0:
        logger.error("%s: %s", what, (r.stderr or b"").decode("utf-8", "replace")[-800:])
        try:
            if os.path.isfile(out):
                os.remove(out)
        except OSError:
            pass
        raise RuntimeError(f"{what} : échec (détails dans le journal).")
    return out


def _base(ff):
    return [ff, "-hide_banner", "-loglevel", "error", "-y"]


def share_version(src: str, height: int = 720, clean_audio: bool = False) -> str:
    """Petite version facile a envoyer (720p max, 30 i/s max, son AAC 128k)."""
    ff = find_ffmpeg()
    info = probe(src)
    fps = min(30, info["fps"])
    vf = f"scale=-2:'min({int(height)},ih)':flags=bicubic,fps={fps},format=yuv420p"
    cmd = _base(ff) + ["-i", src, "-map", "0:v:0", "-map", "0:a:0?", "-vf", vf] + _venc(ff, "legere", fps)
    if info["has_audio"]:
        cmd += (["-af", CLEAN_AUDIO] if clean_audio else []) + ["-c:a", "aac", "-b:a", "128k", "-ar", "48000"]
    out = _out(src, "à partager", ".mp4")
    return _run(cmd + ["-map_chapters", "0", "-movflags", "+faststart", out], out, "Version à partager")


def clip(src: str, start: float, end: float, gif: bool = False) -> str:
    """Extrait precis (re-encode). GIF : 12 i/s, 640 px de large, 30 s max."""
    ff = find_ffmpeg()
    start, end = max(0.0, start), max(start + 0.5, end)
    if gif:
        end = min(end, start + 30)
        out = _out(src, f"extrait {int(start)}s", ".gif")
        fc = "fps=12,scale='min(640,iw)':-1:flags=lanczos,split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer"
        return _run(_base(ff) + ["-ss", f"{start:.2f}", "-t", f"{end - start:.2f}", "-i", src, "-filter_complex", fc,
                                 "-loop", "0", out], out, "GIF")
    info = probe(src)
    out = _out(src, f"extrait {int(start)}s", ".mp4")
    cmd = _base(ff) + ["-ss", f"{start:.2f}", "-t", f"{end - start:.2f}", "-i", src, "-map", "0:v:0", "-map", "0:a:0?"]
    cmd += _venc(ff, "bonne", info["fps"]) + (["-c:a", "aac", "-b:a", "160k"] if info["has_audio"] else [])
    return _run(cmd + ["-movflags", "+faststart", out], out, "Extrait")


def cut_middle(src: str, start: float, end: float) -> str:
    """Enleve le passage [start, end] (precis a l'image) et recolle le reste."""
    ff = find_ffmpeg()
    info = probe(src)
    d = info["duration"]
    start, end = max(0.0, start), min(d, end)
    if end - start < 0.2 or (start < 0.1 and end > d - 0.1):
        raise RuntimeError("Choisis un passage plus court que la vidéo entière.")
    keep = [(0.0, start)] if start > 0.1 else []
    if end < d - 0.1:
        keep.append((end, d))
    fc, labs = [], ""
    for i, (a, b) in enumerate(keep):
        fc.append(f"[0:v]trim=start={a:.3f}:end={b:.3f},setpts=PTS-STARTPTS[v{i}]")
        labs += f"[v{i}]"
        if info["has_audio"]:
            fc.append(f"[0:a]atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS[a{i}]")
            labs += f"[a{i}]"
    fc.append(f"{labs}concat=n={len(keep)}:v=1:a={1 if info['has_audio'] else 0}[v]" + ("[a]" if info["has_audio"] else ""))
    cmd = _base(ff) + ["-i", src, "-filter_complex", ";".join(fc), "-map", "[v]"]
    if info["has_audio"]:
        cmd += ["-map", "[a]", "-c:a", "aac", "-b:a", "192k"]
    out = _out(src, "passage enlevé", ".mp4")
    return _run(cmd + _venc(ff, "bonne", info["fps"]) + ["-movflags", "+faststart", out], out, "Enlever un passage")


def join(files, out_dir: str = "") -> str:
    """Met plusieurs videos bout a bout (taille de la 1re ; son muet ajoute si une video n'en a pas)."""
    ff = find_ffmpeg()
    if len(files) < 2:
        raise RuntimeError("Choisis au moins 2 vidéos.")
    infos = [probe(f) for f in files]
    W, H = (infos[0]["w"] or 1280) // 2 * 2, (infos[0]["h"] or 720) // 2 * 2
    fps = infos[0]["fps"]
    cmd, fc, labs, n_in = _base(ff), [], "", 0
    for f, inf in zip(files, infos):
        cmd += ["-i", f]
        vi = n_in
        n_in += 1
        fc.append(f"[{vi}:v]scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,"
                  f"setsar=1,fps={fps},format=yuv420p[v{vi}]")
        if inf["has_audio"]:
            fc.append(f"[{vi}:a]aresample=48000,aformat=channel_layouts=stereo[a{vi}]")
        else:
            cmd += ["-f", "lavfi", "-t", f"{inf['duration']:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
            fc.append(f"[{n_in}:a]anull[a{vi}]")
            n_in += 1
        labs += f"[v{vi}][a{vi}]"
    fc.append(f"{labs}concat=n={len(files)}:v=1:a=1[v][a]")
    out = _unique(os.path.join(out_dir or os.path.dirname(files[0]), f"Montage {datetime.now():%Y-%m-%d %Hh%M}.mp4"))
    cmd += ["-filter_complex", ";".join(fc), "-map", "[v]", "-map", "[a]"] + _venc(ff, "bonne", fps)
    return _run(cmd + ["-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out], out, "Joindre")


def clean_audio(src: str) -> str:
    """Son ameliore : moins de bruit de fond, volume regulier. L'image est copiee telle quelle."""
    ff = find_ffmpeg()
    info = probe(src)
    if not info["has_audio"]:
        raise RuntimeError("Cette vidéo n'a pas de son.")
    if not info["has_video"]:
        out = _out(src, "son amélioré", ".m4a")
        return _run(_base(ff) + ["-i", src, "-af", CLEAN_AUDIO, "-c:a", "aac", "-b:a", "160k", out], out, "Son amélioré")
    out = _out(src, "son amélioré", ".mp4")
    return _run(_base(ff) + ["-i", src, "-map", "0:v:0", "-map", "0:a:0", "-c:v", "copy", "-af", CLEAN_AUDIO,
                             "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-map_chapters", "0", "-movflags", "+faststart",
                             out], out, "Son amélioré")


def burn_subtitles(src: str, srt: str = "") -> str:
    """Sous-titres incrustes dans l'image (visibles partout, meme sur un telephone)."""
    ff = find_ffmpeg()
    srt = srt or os.path.splitext(src)[0] + ".srt"
    if not os.path.isfile(srt):
        raise RuntimeError("Pas encore de sous-titres : fais d'abord \U0001f4ac Sous-titres.")
    info = probe(src)
    tmp = tempfile.mkdtemp(prefix="cs_srt_")
    try:
        shutil.copy2(srt, os.path.join(tmp, "s.srt"))  # chemin simple : le filtre n'aime pas C:\ ni les espaces
        out = _out(src, "sous-titré", ".mp4")
        vf = "subtitles=s.srt:force_style='FontName=Segoe UI,FontSize=22,Outline=2,Shadow=0,MarginV=28'"
        cmd = _base(ff) + ["-i", src, "-map", "0:v:0", "-map", "0:a:0?", "-vf", vf] + _venc(ff, "bonne", info["fps"])
        cmd += ["-c:a", "copy", "-movflags", "+faststart", out]
        r = run_hidden(cmd, timeout=LONG, cwd=tmp)
        if r.returncode != 0 or not os.path.isfile(out):
            logger.error("incruster: %s", (r.stderr or b"").decode("utf-8", "replace")[-800:])
            raise RuntimeError("Incruster les sous-titres : échec (détails dans le journal).")
        return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def audio_only(src: str, clean: bool = False) -> str:
    """Garder seulement le son, en MP3 (balado, cours a ecouter)."""
    ff = find_ffmpeg()
    if not probe(src)["has_audio"]:
        raise RuntimeError("Cette vidéo n'a pas de son.")
    out = _out(src, "son", ".mp3")
    return _run(_base(ff) + ["-i", src, "-vn"] + (["-af", CLEAN_AUDIO] if clean else []) +
                ["-c:a", "libmp3lame", "-b:a", "160k", out], out, "Son en MP3")


def play_at(media: str, t: float = 0.0) -> bool:
    """Lire a partir de t secondes (ffplay, fourni avec ffmpeg) ; sinon le lecteur de Windows depuis le debut."""
    import subprocess
    fp = find_ffmpeg("ffplay")
    if fp:
        try:
            subprocess.Popen([fp, "-hide_banner", "-loglevel", "error", "-autoexit", "-ss", f"{max(0.0, t):.2f}",
                              "-window_title", os.path.basename(media), media],
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return True
        except Exception:
            logger.exception("ffplay")
    try:
        os.startfile(media)  # type: ignore[attr-defined]
    except Exception:
        pass
    return False
