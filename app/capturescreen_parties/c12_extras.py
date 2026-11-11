# -*- coding: utf-8 -*-
"""CaptureScreen - c12 : reperes (chapitres), fiche resume de chaque enregistrement, mode « son seulement ».
Tout est en plus : si quelque chose echoue ici, la video principale reste intacte."""
from __future__ import annotations

import glob
import json
import os
import time
from datetime import datetime

from .c01_config import find_ffmpeg, hms, logger, run_hidden

AUDIO_EXT = (".m4a", ".mp3", ".wav")
CARD_SUFFIX = ".capture.json"


# ------------------------------------------------------------------ fiche resume (a cote de la video)
def card_path(media: str) -> str:
    return os.path.splitext(media)[0] + CARD_SUFFIX


def read_card(media: str) -> dict:
    try:
        with open(card_path(media), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def write_card(media: str, card: dict) -> None:
    p = card_path(media)
    with open(p + ".tmp", "w", encoding="utf-8") as f:
        json.dump(card, f, ensure_ascii=False, indent=1)
    if os.path.exists(p):
        _hide(p, False)
    os.replace(p + ".tmp", p)
    _hide(p, True)


def _hide(p: str, on: bool) -> None:
    """Fiche resume cachee dans l'Explorateur (le dossier des videos reste propre)."""
    if os.name != "nt":
        return
    try:
        import ctypes
        ctypes.windll.kernel32.SetFileAttributesW(p, 0x2 if on else 0x80)
    except Exception:
        pass


def clean_markers(markers, duration=None):
    out = []
    for m in markers or []:
        try:
            t = float(m.get("t"))
        except Exception:
            continue
        if t < 0 or (duration and t > duration + 0.5):
            continue
        out.append({"t": round(t, 2), "label": str(m.get("label") or "").strip()[:80] or f"Repère {len(out) + 1}"})
    out.sort(key=lambda m: m["t"])
    return out


def retime_markers(man: dict, plan) -> None:
    """Recale chaque repere sur le vrai debut de son morceau (mesure a l'arret) : precis a l'image pres."""
    try:
        before, starts = 0.0, {}
        for n, t_start, dur in plan:
            starts[int(n)] = (before, float(t_start), float(dur))
            before += float(dur)
        for m in man.get("markers") or []:
            s = starts.get(int(m.get("n") or 0))
            if s and m.get("wall"):
                m["t"] = round(s[0] + min(max(0.0, float(m["wall"]) - s[1]), s[2]), 2)
    except Exception:
        logger.exception("reperes")


def _meta_escape(s: str) -> str:
    for ch in ("\\", "=", ";", "#", "\n"):
        s = s.replace(ch, "\\" + ch)
    return s


def write_chapters(media: str, markers, duration: float, ff: str = "") -> bool:
    """Chapitres MP4 (lecteurs : VLC, mpv, Films et TV…) depuis les reperes. Remux sans re-encodage."""
    ff = ff or find_ffmpeg()
    marks = clean_markers(markers, duration)
    if not ff or not marks or duration <= 0:
        return False
    if marks[0]["t"] > 0.5:
        marks.insert(0, {"t": 0.0, "label": "Début"})
    meta = os.path.splitext(media)[0] + ".chapitres.txt"
    with open(meta, "w", encoding="utf-8") as f:
        f.write(";FFMETADATA1\n")
        for i, m in enumerate(marks):
            end = marks[i + 1]["t"] if i + 1 < len(marks) else duration
            if end - m["t"] < 0.05:
                continue
            f.write(f"[CHAPTER]\nTIMEBASE=1/1000\nSTART={int(m['t'] * 1000)}\nEND={int(end * 1000)}\n"
                    f"title={_meta_escape(m['label'])}\n")
    base, ext = os.path.splitext(media)
    tmp = base + ".chap_tmp" + ext
    try:
        r = run_hidden([ff, "-hide_banner", "-loglevel", "error", "-y", "-i", media, "-f", "ffmetadata", "-i", meta,
                        "-map", "0", "-map_metadata", "0", "-map_chapters", "1", "-c", "copy", "-movflags", "+faststart",
                        tmp], timeout=3600)
        if r.returncode == 0 and os.path.isfile(tmp) and os.path.getsize(tmp) > 0.9 * os.path.getsize(media):
            os.replace(tmp, media)
            return True
        logger.error("chapitres: %s", (r.stderr or b"").decode("utf-8", "replace")[-400:])
        return False
    finally:
        for p in (tmp, meta):
            try:
                if os.path.exists(p):
                    os.remove(p)
            except OSError:
                pass


def read_chapters(media: str):
    fp = find_ffmpeg("ffprobe")
    if not fp:
        return []
    try:
        r = run_hidden([fp, "-v", "error", "-show_chapters", "-of", "json", media], timeout=20)
        ch = json.loads((r.stdout or b"{}").decode("utf-8", "replace")).get("chapters") or []
        return [{"t": round(float(c.get("start_time") or 0), 2), "label": (c.get("tags") or {}).get("title", "")}
                for c in ch]
    except Exception:
        return []


def finalize(out: str, man: dict, ff: str = "") -> None:
    """Apres l'assemblage : chapitres + fiche resume (jamais bloquant)."""
    from .c04_recorder import probe_duration
    try:
        dur = probe_duration(out)
        marks = clean_markers(man.get("markers"), dur)
        if marks and out.lower().endswith(".mp4"):
            write_chapters(out, marks, dur, ff)
        info = man.get("info") or {}
        card = {"version": 1, "titre": os.path.splitext(os.path.basename(out))[0], "cree": man.get("created"),
                "duree": round(dur, 1), "taille": os.path.getsize(out), "reperes": marks,
                "source": info.get("source"), "son_ordi": info.get("sys_audio"), "micro": info.get("mic"),
                "webcam": info.get("webcam"), "fps": man.get("fps"), "rect": man.get("rect"),
                "son_seulement": bool(man.get("audio_only")), "pauses": max(0, len(man.get("attempts") or []) - 1 - int(man.get("repairs") or 0)),
                "reparations": int(man.get("repairs") or 0),
                "archiveur": (man.get("handoff") or {}).get("dossier") or ""}
        write_card(out, card)
    except Exception:
        logger.exception("fiche resume")


def summary_text(media: str) -> str:
    c = read_card(media)
    lines = [os.path.splitext(os.path.basename(media))[0]]
    if c.get("cree"):
        lines.append("Enregistré le " + str(c["cree"])[:16].replace("T", " à "))
    if c.get("duree"):
        lines.append("Durée : " + hms(c["duree"]))
    marks = c.get("reperes") or []
    if marks:
        lines.append("")
        lines.append("Chapitres :")
        lines += [f"{hms(m['t'])} {m['label']}" for m in marks]
    return "\n".join(lines)


# ------------------------------------------------------------------ « son seulement » (cours, balado)
def assemble_audio(work: str, out_dir: str, name: str = "", ff: str = "", fmt: str = "m4a") -> str:
    from .c04_recorder import MANIFEST, probe_duration, unique
    ff = ff or find_ffmpeg()
    with open(os.path.join(work, MANIFEST), encoding="utf-8") as f:
        man = json.load(f)
    fmt = fmt if fmt in ("m4a", "mp3") else "m4a"
    inputs, chains, labs, plan = [], [], [], []
    for a in man.get("attempts") or []:
        n = int(a["n"])
        t_start = float(a.get("t_popen") or 0)
        dur = float(a.get("dur") or 0)
        per = []
        for kind, t0s in (man.get("audio") or {}).items():
            pcm = os.path.join(work, f"son_{kind}_{n:03d}.pcm")
            t0 = t0s.get(os.path.basename(pcm))
            if t0 is None or not os.path.isfile(pcm) or os.path.getsize(pcm) <= 0:
                continue
            if dur <= 0:  # panne : la duree vient de la taille du son
                dur = max(dur, os.path.getsize(pcm) / 192000.0 - max(0.0, t_start - float(t0)))
            inputs += ["-f", "s16le", "-ar", "48000", "-ac", "2", "-i", pcm]
            idx = len(inputs) // 8 - 1
            off = t_start - float(t0)
            pre = f"adelay={int(-off * 1000)}:all=1," if off < 0 else ""
            lab = f"p{idx}"
            chains.append(f"[{idx}:a]{pre}atrim=start={max(0.0, off):.3f},asetpts=PTS-STARTPTS,apad[{lab}r]")
            per.append(lab)
        if not per or dur <= 0:
            continue
        seg = f"s{len(labs)}"
        if len(per) == 1:
            chains.append(f"[{per[0]}r]atrim=duration={dur:.3f}[{seg}]")
        else:
            chains.append("".join(f"[{p}r]" for p in per) +
                          f"amix=inputs={len(per)}:duration=longest:normalize=0,atrim=duration={dur:.3f}[{seg}]")
        labs.append(seg)
        plan.append((n, t_start, dur))
    if not labs:
        raise RuntimeError("Aucun son enregistré (active « Son de l'ordi » ou « Micro »).")
    retime_markers(man, plan)
    chains.append("".join(f"[{l}]" for l in labs) + f"concat=n={len(labs)}:v=0:a=1[a]")
    os.makedirs(out_dir, exist_ok=True)
    when = man.get("created", "")[:16].replace("T", " ").replace(":", "h")
    out = unique(os.path.join(out_dir, (name or man.get("name") or f"Son {when}") + "." + fmt))
    codec = ["-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart"] if fmt == "m4a" else ["-c:a", "libmp3lame", "-b:a", "160k"]
    r = run_hidden([ff, "-hide_banner", "-loglevel", "error", "-y"] + inputs +
                   ["-filter_complex", ";".join(chains), "-map", "[a]"] + codec + [out], timeout=6 * 3600)
    if r.returncode != 0 or not os.path.isfile(out) or probe_duration(out) <= 0:
        logger.error("assemblage son: %s", (r.stderr or b"").decode("utf-8", "replace")[-800:])
        try:
            if os.path.isfile(out):
                os.remove(out)
        except OSError:
            pass
        raise RuntimeError("Le son n'a pas pu être assemblé (les morceaux sont gardés pour réessayer).")
    finalize(out, man, ff)
    import shutil
    shutil.rmtree(work, ignore_errors=True)
    logger.info("son enregistre: %s", out)
    return out


def make_audio_recorder(base_cls):
    """Classe « son seulement » construite sur Recorder (meme interface : pause, reprise, barre, recuperation)."""

    class AudioOnlyRecorder(base_cls):
        audio_only = True

        def __init__(self, cfg, rect, log=None, work=None):
            cfg = dict(cfg, webcam=False)
            super().__init__(cfg, rect, log, work)
            if not self.audio.sources:
                import shutil
                shutil.rmtree(self.work, ignore_errors=True)
                raise RuntimeError("Pour enregistrer seulement le son, active « Son de l'ordi » ou « Micro ».")
            self.man["audio_only"] = True
            self.man["audio_fmt"] = cfg.get("audio_fmt", "m4a")

        def _start_segment(self, retry=True):
            self._attempt += 1
            n = self._attempt
            self.audio.begin(n)
            t = time.time()
            self.seg_t0 = t
            with self._lock:
                self.man["attempts"].append({"n": n, "t_popen": t, "t_end": None, "dur": None})
            self._save_man()
            self.first_frame.set()

        def _stop_segment(self):
            if self.seg_t0 is None:
                return
            t_q = time.time()
            self.audio.end()
            a = self.man["attempts"][-1]
            a["t_end"], a["dur"] = t_q, max(0.0, t_q - a["t_popen"])
            self._save_man()
            self.done_before += a["dur"]
            self.seg_t0 = None

        def start(self):
            self.audio.start()
            self._start_segment()
            self.state = "rec"
            self.log("\U0001f3a4 Enregistrement du son seulement.")

        def finish(self, out_dir="", name=""):
            if self.state not in ("stopped", "idle"):
                self.stop()
            return assemble_audio(self.work, out_dir or self.cfg.get("out_dir"), name, self.ff,
                                  self.man.get("audio_fmt", "m4a"))

        def size(self):
            n = 0
            try:
                for e in os.scandir(self.work):
                    if e.name.endswith(".pcm"):
                        n += e.stat().st_size // 9
            except OSError:
                pass
            return n

    return AudioOnlyRecorder


def audio_leftover(path: str) -> bool:
    """Dossier de travail d'un enregistrement « son seulement » interrompu ?"""
    if not glob.glob(os.path.join(path, "son_*.pcm")):
        return False
    try:
        with open(os.path.join(path, "session.json"), encoding="utf-8") as f:
            return bool(json.load(f).get("audio_only"))
    except Exception:
        return False


def now_hm() -> str:
    return datetime.now().strftime("%H:%M")
