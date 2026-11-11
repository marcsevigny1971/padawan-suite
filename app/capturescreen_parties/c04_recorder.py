# -*- coding: utf-8 -*-
"""CaptureScreen - c04 : enregistreur ffmpeg (ddagrab, repli gdigrab) + son, pause en segments,
assemblage MP4 H.264 + AAC, captures PNG, coupe rapide, miniatures, sous-titres, envoi a l'Archiveur.
On enregistre seulement ce que Windows affiche ; rien ne contourne une protection anticopie."""
from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime

from .c01_config import (HERE, NOWIN, THUMBS, TMP_DIR, find_ffmpeg, logger, pick_encoder, run_hidden,
                         video_codec_args)
from .c02_win32 import even, monitors
from .c03_audio import AudioRecorder

VIDEO_EXT = (".mp4", ".mkv", ".webm", ".mov", ".avi")
IMAGE_EXT = (".png", ".jpg", ".jpeg")


def stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %Hh%Mm%S")


def unique(path: str) -> str:
    base, ext = os.path.splitext(path)
    i, p = 2, path
    while os.path.exists(p):
        p = f"{base} ({i}){ext}"; i += 1
    return p


def clamp_rect(rect):
    x, y, w, h = [int(v) for v in rect]
    return (x, y, max(16, even(w)), max(16, even(h)))


def list_webcams(ff=None):
    """Cameras DirectShow (noms) ; [] si aucune."""
    ff = ff or find_ffmpeg()
    if not ff:
        return []
    try:
        r = run_hidden([ff, "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"], timeout=15)
        txt = (r.stderr or b"").decode("utf-8", "replace")
        return re.findall(r'"([^"]+)"\s*\(video\)', txt)
    except Exception:
        return []


def _job_kill_on_close():
    """Objet Job Windows : si CaptureScreen plante, ffmpeg s'arrete aussi (les morceaux deja ecrits restent
    sur le disque et seront recuperes au prochain lancement). Un simple gel de l'interface ne touche pas ffmpeg."""
    try:
        import win32job  # pywin32
        job = win32job.CreateJobObject(None, "")
        info = win32job.QueryInformationJobObject(job, win32job.JobObjectExtendedLimitInformation)
        info["BasicLimitInformation"]["LimitFlags"] |= win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        win32job.SetInformationJobObject(job, win32job.JobObjectExtendedLimitInformation, info)
        return job
    except Exception:
        return None


_JOB = None


def _attach_job(proc):
    global _JOB
    try:
        import win32api
        import win32con
        import win32job
        if _JOB is None:
            _JOB = _job_kill_on_close()
        if _JOB is not None:
            h = win32api.OpenProcess(win32con.PROCESS_SET_QUOTA | win32con.PROCESS_TERMINATE, False, proc.pid)
            win32job.AssignProcessToJobObject(_JOB, h)
    except Exception:
        pass


MANIFEST = "session.json"
LATENCY = 0.1    # delai typique entre le lancement de ffmpeg et le debut de la video (corrige par la mesure)
STATS_PERIOD = "0.25"  # ffmpeg ne lit le « q » d'arret qu'a chaque rapport : 0,25 s au lieu de 1 s (duree = minuteur)
STALL_S = 25      # aucune image nouvelle pendant 25 s = capture figee


def _write_json(path, d):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def free_bytes(path: str) -> int:
    try:
        p = path
        while p and not os.path.exists(p):
            p = os.path.dirname(p)
        return shutil.disk_usage(p or "C:\\").free
    except Exception:
        return 1 << 50


class Recorder:
    """start() -> pause()/resume() -> stop() ; finish() ecrit le MP4 final (dans un fil).
    Video : ffmpeg (processus a part) en morceaux MKV de N minutes (segment muxer) : un plantage ne perd
    que les dernieres secondes. Son : PCM horodate. Tout est decrit dans session.json (recuperation)."""

    def __init__(self, cfg: dict, rect, log=None, work=None):
        self.cfg, self.log = cfg, (log or (lambda m: None))
        self.ff = find_ffmpeg()
        if not self.ff:
            raise RuntimeError("L'outil vidéo n'est pas encore installé. Ouvre l'Archiveur une fois (il s'installe tout seul) "
                               "ou lance le Setup Padawan.")
        self.rect = clamp_rect(rect)
        self.fps = int(cfg.get("fps") or 30)
        self.seg_seconds = max(5, int(float(cfg.get("segment_minutes") or 10) * 60)) if not cfg.get("_seg_s") else int(cfg["_seg_s"])
        self.enc = pick_encoder(self.ff, cfg.get("encoder", "auto"))
        self.engine = "gdigrab" if cfg.get("engine") == "gdigrab" else "ddagrab"
        self.work = work or os.path.join(TMP_DIR, datetime.now().strftime("%Y%m%d_%H%M%S"))
        os.makedirs(self.work, exist_ok=True)
        self.proc = None
        self.state = "idle"        # idle | rec | pause | stopped
        self.done_before = 0.0
        self.seg_t0 = None
        self.first_frame = threading.Event()
        self.error = ""
        self._attempt = 0
        self._lock = threading.Lock()
        self._seg_lock = threading.RLock()
        self.man = {"version": 1, "created": datetime.now().isoformat(timespec="seconds"), "rect": list(self.rect),
                    "fps": self.fps, "out_dir": cfg.get("out_dir"), "name": "", "attempts": [], "audio": {},
                    "latency": LATENCY, "finished": False, "markers": [],
                    "info": {k: cfg.get(k) for k in ("source", "sys_audio", "mic", "webcam", "quality")}}
        self.audio = AudioRecorder(self.work, cfg.get("sys_audio"), cfg.get("speaker", ""), cfg.get("mic"),
                                   cfg.get("mic_name", ""), self.log, on_t0=self._on_audio_t0)
        self.webcam = cfg.get("webcam_name") if cfg.get("webcam") else ""
        self._size_cache = (0.0, 0)

    # ---------------------------------------------------------- manifeste
    def _save_man(self):
        with self._lock:
            try:
                _write_json(os.path.join(self.work, MANIFEST), self.man)
            except Exception:
                logger.exception("manifeste")

    def _on_audio_t0(self, kind, path, t0):
        with self._lock:
            self.man["audio"].setdefault(kind, {})[os.path.basename(path)] = t0
        self._save_man()

    # ---------------------------------------------------------- commande ffmpeg
    def _dda_target(self):
        x, y, w, h = self.rect
        for i, m in enumerate(monitors()):
            if m["x"] <= x and m["y"] <= y and x + w <= m["x"] + m["w"] and y + h <= m["y"] + m["h"]:
                return i, x - m["x"], y - m["y"]
        return None

    def _cmd(self, pattern: str, progress: str):
        x, y, w, h = self.rect
        cmd = [self.ff, "-hide_banner", "-loglevel", "error", "-y", "-progress", progress, "-stats_period", STATS_PERIOD]
        mouse = "1" if self.cfg.get("cursor", True) else "0"
        tgt = self._dda_target() if self.engine == "ddagrab" else None
        if tgt is not None:
            idx, ox, oy = tgt
            src = (f"ddagrab=output_idx={idx}:framerate={self.fps}:draw_mouse={mouse}"
                   f":offset_x={ox}:offset_y={oy}:video_size={w}x{h}")
            cmd += ["-f", "lavfi", "-i", src]
            vchain = "hwdownload,format=bgra,format=yuv420p"
        else:
            self.engine = "gdigrab"
            cmd += ["-f", "gdigrab", "-thread_queue_size", "512", "-framerate", str(self.fps), "-draw_mouse", mouse,
                    "-offset_x", str(x), "-offset_y", str(y), "-video_size", f"{w}x{h}", "-i", "desktop"]
            vchain = "format=yuv420p"
        if self.webcam:
            cw = max(160, even(w // {"petite": 7, "grande": 3}.get(self.cfg.get("cam_size"), 5)))
            if self.cfg.get("_cam_test_src"):  # tests : une mire a la place de la camera
                cmd += ["-f", "lavfi", "-i", self.cfg["_cam_test_src"]]
            else:
                cmd += ["-f", "dshow", "-thread_queue_size", "512", "-i", f"video={self.webcam}"]
            pos = {"bg": "24:H-h-24", "hd": "W-w-24:24", "hg": "24:24"}.get(self.cfg.get("cam_pos"), "W-w-24:H-h-24")
            fc = (f"[0:v]{vchain}[s];[1:v]scale={cw}:-2,format=yuv420p,pad=iw+8:ih+8:4:4:color=white[c];"
                  f"[s][c]overlay={pos}:eof_action=pass,format=yuv420p[v]")
            cmd += ["-filter_complex", fc, "-map", "[v]"]
        else:
            cmd += ["-vf", vchain]
        cmd += ["-r", str(self.fps)] + video_codec_args(self.enc, self.cfg.get("quality", "bonne"), self.fps)
        cmd += ["-an", "-f", "segment", "-segment_time", str(self.seg_seconds), "-segment_format", "matroska",
                "-segment_format_options", "cluster_time_limit=1000:flush_packets=1", "-reset_timestamps", "1", pattern]
        return cmd

    # ---------------------------------------------------------- segments
    def _start_segment(self, retry=True):
        self._attempt += 1
        n = self._attempt
        pattern = os.path.join(self.work, f"seg{n:03d}_%03d.mkv")
        prog = os.path.join(self.work, f"seg{n:03d}.progress.txt")
        errp = os.path.join(self.work, f"seg{n:03d}.err.txt")
        self.audio.begin(n)
        self.first_frame.clear()
        cmd = self._cmd(pattern, prog)
        logger.info("ffmpeg: %s", " ".join(cmd))
        t_popen = time.time()
        ef = open(errp, "wb")
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=ef,
                                     creationflags=NOWIN)
        ef.close()
        _attach_job(self.proc)
        proc = self.proc
        t0 = time.time()
        while time.time() - t0 < 10:
            if proc.poll() is not None:
                break
            if glob.glob(os.path.join(self.work, f"seg{n:03d}_*.mkv")) and self._prog_frames(prog) > 0:
                break
            time.sleep(0.05)
        if proc.poll() is not None or self._prog_frames(prog) <= 0:
            self.audio.end()
            try:
                proc.kill()
            except Exception:
                pass
            err = ""
            try:
                err = open(errp, encoding="utf-8", errors="replace").read()[-600:]
            except Exception:
                pass
            for f in glob.glob(os.path.join(self.work, f"seg{n:03d}_*.mkv")):
                try:
                    os.remove(f)
                except OSError:
                    pass
            logger.info("demarrage echoue (%s/%s): %s", self.engine, self.enc, err)
            if self.webcam:
                self.log("Caméra indisponible : on continue sans elle.")
                self.webcam = ""
                return self._start_segment(retry=retry)
            if retry and self.engine == "ddagrab":
                self.log("Mode de capture compatible activé.")
                self.engine = "gdigrab"
                return self._start_segment(retry=True)
            if retry and self.enc != "libx264":
                self.log("Encodage par le processeur activé.")
                self.enc = "libx264"
                return self._start_segment(retry=False)
            raise RuntimeError("La capture n'a pas pu démarrer. Détail technique : " + (err.strip()[-200:] or "inconnu"))
        self.seg_t0 = t_popen + self.man.get("latency", LATENCY)
        with self._lock:
            self.man["attempts"].append({"n": n, "t_popen": t_popen, "t_end": None, "dur": None})
        self._save_man()
        self.first_frame.set()

    @staticmethod
    def _prog_frames(prog) -> int:
        try:
            with open(prog, "rb") as f:
                f.seek(max(0, os.path.getsize(prog) - 600))
                tail = f.read().decode("ascii", "ignore")
            m = re.findall(r"frame=(\d+)", tail)
            return int(m[-1]) if m else 0
        except Exception:
            return 0

    def _parts(self, n):
        return sorted(glob.glob(os.path.join(self.work, f"seg{n:03d}_*.mkv")))

    def _stop_segment(self, died=False):
        """'q' a ffmpeg : derniere image ~ t_q ; debut reel = t_q - duree. Le son horodate s'y cale."""
        p = self.proc
        if not p:
            return
        t_q = time.time()
        try:
            p.stdin.write(b"q"); p.stdin.flush()
        except Exception:
            pass
        try:
            p.wait(timeout=20)
        except Exception:
            p.kill()
        try:
            p.stdin.close()
        except Exception:
            pass
        self.audio.end()
        self.proc = None
        a = self.man["attempts"][-1]
        parts = self._parts(a["n"])
        if died and parts:  # le dernier morceau n'a pas ete ferme proprement : recopie (sans re-encoder) = duree exacte
            _remux_inplace(self.ff, parts[-1])
        dur = sum(probe_duration(f) for f in parts)
        a["t_end"], a["dur"] = t_q, (dur if died else (dur or max(0.0, t_q - (self.seg_t0 or t_q))))
        if died:  # ffmpeg s'est arrete tout seul : la fin reelle est le debut + la duree ecrite
            a["t_end"] = a["t_popen"] + float(self.man.get("latency", LATENCY)) + a["dur"]
        lat = (a["t_end"] - a["dur"]) - a["t_popen"]
        if not died and -0.5 < lat < 3:
            self.man["latency"] = round(max(0.0, lat), 3)
        self._save_man()
        self.done_before += a["dur"]
        self.seg_t0 = None

    # ---------------------------------------------------------- etats
    def start(self):
        self.audio.start()
        self._start_segment()
        self.state = "rec"
        self.log(f"Enregistrement : {self.rect[2]}×{self.rect[3]} à {self.fps} images/s.")
        self.repairs = 0
        threading.Thread(target=self._watchdog, daemon=True).start()

    def pause(self):
        with self._seg_lock:
            if self.state == "rec":
                self._stop_segment(); self.state = "pause"

    def resume(self):
        with self._seg_lock:
            if self.state == "pause":
                self._start_segment(); self.state = "rec"

    def stop(self):
        with self._seg_lock:
            if self.state == "rec":
                self._stop_segment()
            self.state = "stopped"
        self.audio.stop()

    # ---------------------------------------------------------- chien de garde (longues sessions)
    def _watchdog(self):
        """Si ffmpeg meurt ou se fige (pilote graphique, veille de l'ecran…), on repart tout seul sur un
        nouveau morceau : la video continue, on ne perd que la coupure (quelques secondes au pire)."""
        last, since = -1, time.time()
        while self.state not in ("stopped", "idle"):
            time.sleep(1.0)
            with self._seg_lock:
                p = self.proc
                if self.state != "rec" or p is None:
                    last, since = -1, time.time()
                    continue
                dead = p.poll() is not None
                if not dead:
                    fr = self._prog_frames(os.path.join(self.work, f"seg{self._attempt:03d}.progress.txt"))
                    if fr != last:
                        last, since = fr, time.time()
                    elif time.time() - since > STALL_S:
                        logger.warning("ffmpeg fige depuis %.0f s : on relance", time.time() - since)
                        try:
                            p.kill()
                        except Exception:
                            pass
                        dead = True
                if not dead:
                    continue
                logger.warning("ffmpeg arrete (code %s) : reprise automatique", p.poll())
                try:
                    self._stop_segment(died=True)
                    self._start_segment()
                    self.repairs = getattr(self, "repairs", 0) + 1
                    self.man["repairs"] = self.repairs
                    self._save_man()
                    self.log(f"\U0001f527 Petite coupure de la capture réparée toute seule (n° {self.repairs}).")
                except Exception as e:
                    logger.exception("reprise")
                    self.state = "pause"
                    self.error = str(e)
                    self.log("\u26a0 La capture s'est arrêtée et n'a pas pu repartir : appuie sur \u25b6 pour reprendre.")
                last, since = -1, time.time()

    def add_marker(self, label: str = "") -> float:
        """Repere (chapitre) au temps actuel de la video (les pauses ne comptent pas)."""
        t = round(self.elapsed(), 2)
        with self._lock:
            marks = self.man.setdefault("markers", [])
            marks.append({"t": t, "label": (label or "").strip()[:80] or f"Repère {len(marks) + 1}",
                          "n": self._attempt, "wall": time.time()})
        self._save_man()
        return t

    def elapsed(self) -> float:
        return self.done_before + ((time.time() - self.seg_t0) if (self.state == "rec" and self.seg_t0) else 0)

    def size(self) -> int:
        """Taille estimee du MP4 final (video ecrite + son compresse ~1/8). Mise en cache 2 s."""
        t, n = self._size_cache
        if time.time() - t < 2:
            return n
        n = 0
        try:
            for e in os.scandir(self.work):
                if e.name.endswith(".mkv"):
                    n += e.stat().st_size
                elif e.name.endswith(".pcm"):
                    n += e.stat().st_size // 8
        except OSError:
            pass
        self._size_cache = (time.time(), n)
        return n

    def per_hour(self) -> int:
        e = self.elapsed()
        return int(self.size() / e * 3600) if e > 20 else 0

    def levels(self):
        return self.audio.levels()

    # ---------------------------------------------------------- assemblage
    def finish(self, out_dir: str = "", name: str = "") -> str:
        if self.state not in ("stopped", "idle"):
            self.stop()
        return assemble(self.work, out_dir or self.cfg.get("out_dir"), name, self.ff)

    def discard(self):
        try:
            self.stop()
        except Exception:
            pass
        shutil.rmtree(self.work, ignore_errors=True)


def _remux_inplace(ff, part) -> None:
    fixed = part[:-4] + "_ok.mkv"
    try:
        run_hidden([ff, "-hide_banner", "-loglevel", "error", "-y", "-i", part, "-c", "copy", fixed], timeout=900)
        if os.path.isfile(fixed) and probe_duration(fixed) > 0:
            os.replace(fixed, part)
        elif os.path.isfile(fixed):
            os.remove(fixed)
    except Exception:
        logger.exception("recopie morceau")


def _fix_part(ff, part) -> float:
    """Duree d'un morceau ; s'il est abime (plantage), on le recopie proprement (sans re-encoder)."""
    d = probe_duration(part)
    if d > 0:
        return d
    fixed = part[:-4] + "_ok.mkv"
    run_hidden([ff, "-hide_banner", "-loglevel", "error", "-y", "-i", part, "-c", "copy", fixed], timeout=900)
    if os.path.isfile(fixed) and probe_duration(fixed) > 0:
        os.replace(fixed, part)
        return probe_duration(part)
    return 0.0


def assemble(work: str, out_dir: str, name: str = "", ff: str = "") -> str:
    """Morceaux MKV + son PCM horodate -> un seul MP4 (video copiee telle quelle, son AAC). Sert aussi a la recuperation."""
    ff = ff or find_ffmpeg()
    try:
        with open(os.path.join(work, MANIFEST), encoding="utf-8") as f:
            man = json.load(f)
    except Exception:
        man = {"attempts": [], "audio": {}, "latency": LATENCY}
    if man.get("audio_only"):  # mode « son seulement »
        from .c12_extras import assemble_audio
        return assemble_audio(work, out_dir, name, ff, man.get("audio_fmt", "m4a"))
    atts = man.get("attempts") or []
    lat = float(man.get("latency") or LATENCY)
    parts_all, plan = [], []
    for a in atts:
        parts = sorted(p for p in glob.glob(os.path.join(work, f"seg{int(a['n']):03d}_*.mkv")) if not p.endswith("_ok.mkv"))
        durs = [_fix_part(ff, p) for p in parts]
        good = [(p, d) for p, d in zip(parts, durs) if d > 0]
        if not good:
            continue
        dur = sum(d for _p, d in good)
        t_start = (a["t_end"] - dur) if a.get("t_end") else (a.get("t_popen", 0) + lat)
        parts_all += [p for p, _d in good]
        plan.append((int(a["n"]), t_start, dur))
    if not parts_all:
        raise RuntimeError("Aucune image enregistrée.")
    os.makedirs(out_dir, exist_ok=True)
    when = man.get("created", "")[:19].replace("T", " ").replace(":", "h", 1).replace(":", "m", 1)
    out = unique(os.path.join(out_dir, (name or man.get("name") or f"Capture {when or stamp()}") + ".mp4"))
    lst = os.path.join(work, "liste.txt")
    with open(lst, "w", encoding="utf-8") as f:
        for p in parts_all:
            f.write("file '" + p.replace("\\", "/").replace("'", "'\\''") + "'\n")
    cmd = [ff, "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst]
    chains, mixes, n_in = [], [], 1
    for kind, t0s in (man.get("audio") or {}).items():
        labs = []
        for n, t_start, dur in plan:
            pcm = os.path.join(work, f"son_{kind}_{n:03d}.pcm")
            lab = f"a{len(chains)}"
            t0 = t0s.get(os.path.basename(pcm))
            if t0 is not None and os.path.isfile(pcm) and os.path.getsize(pcm) > 0:
                cmd += ["-f", "s16le", "-ar", "48000", "-ac", "2", "-i", pcm]
                off = t_start - float(t0)
                pre = f"adelay={int(-off * 1000)}:all=1," if off < 0 else ""
                chains.append(f"[{n_in}:a]{pre}atrim=start={max(0.0, off):.3f},asetpts=PTS-STARTPTS,"
                              f"apad,atrim=duration={dur:.3f}[{lab}]")
                n_in += 1
            else:
                chains.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={dur:.3f}[{lab}]")
            labs.append(f"[{lab}]")
        if labs:
            m = f"m{len(mixes)}"
            chains.append(f"{''.join(labs)}concat=n={len(labs)}:v=0:a=1[{m}]")
            mixes.append(f"[{m}]")
    if not mixes:
        cmd += ["-map", "0:v", "-c", "copy"]
    else:
        chains.append(f"{mixes[0]}apad[a]" if len(mixes) == 1 else
                      f"{''.join(mixes)}amix=inputs={len(mixes)}:duration=longest:normalize=0,apad[a]")
        cmd += ["-filter_complex", ";".join(chains), "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac",
                "-b:a", "192k", "-shortest"]
    cmd += ["-movflags", "+faststart", out]
    r = run_hidden(cmd, timeout=6 * 3600)
    if r.returncode != 0 or not os.path.isfile(out) or probe_duration(out) <= 0:
        try:
            if os.path.isfile(out):
                os.remove(out)
        except OSError:
            pass
        logger.error("assemblage: %s", (r.stderr or b"").decode("utf-8", "replace")[-800:])
        raise RuntimeError("La vidéo n'a pas pu être assemblée (les morceaux sont gardés pour réessayer).")
    try:  # chapitres (reperes) + fiche resume : en plus, jamais bloquant
        from .c12_extras import finalize, retime_markers
        retime_markers(man, plan)
        finalize(out, man, ff)
    except Exception:
        logger.exception("finalisation")
    shutil.rmtree(work, ignore_errors=True)
    logger.info("enregistre: %s", out)
    return out


def leftovers():
    """Enregistrements interrompus (plantage, panne) : [(dossier, date, duree estimee, taille)]."""
    out = []
    try:
        for e in os.scandir(TMP_DIR):
            if not e.is_dir() or e.name.startswith("_"):
                continue
            if not glob.glob(os.path.join(e.path, "seg*_*.mkv")):
                from .c12_extras import audio_leftover
                if not audio_leftover(e.path):
                    continue
            size = sum(f.stat().st_size for f in os.scandir(e.path) if f.is_file())
            try:
                with open(os.path.join(e.path, MANIFEST), encoding="utf-8") as f:
                    man = json.load(f)
                created = man.get("created", e.name)
                dur = sum(a.get("dur") or 0 for a in man.get("attempts", []))
            except Exception:
                created, dur = e.name, 0
            out.append((e.path, created, dur, size))
    except OSError:
        pass
    return out


# ------------------------------------------------------------------ captures d'ecran
def screenshot(rect, out_dir: str, to_clipboard=True, name=""):
    from PIL import ImageGrab
    from .c02_win32 import copy_image_to_clipboard
    x, y, w, h = [int(v) for v in rect]
    img = ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True)
    os.makedirs(out_dir, exist_ok=True)
    p = unique(os.path.join(out_dir, (name or f"Capture {stamp()}") + ".png"))
    img.save(p, "PNG")
    ok = copy_image_to_clipboard(img) if to_clipboard else False
    return p, ok


# ------------------------------------------------------------------ outils fichiers
def probe_duration(path: str) -> float:
    fp = find_ffmpeg("ffprobe")
    if not fp:
        return 0.0
    try:
        r = run_hidden([fp, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", path], timeout=20)
        return float((r.stdout or b"0").decode().strip() or 0)
    except Exception:
        return 0.0


def thumb(path: str, width=320) -> str:
    """Miniature JPG (cache dans C:\\web_private\\CaptureScreen\\miniatures)."""
    try:
        st = os.stat(path)
    except OSError:
        return ""
    os.makedirs(THUMBS, exist_ok=True)
    key = hashlib.md5(f"{path}|{st.st_mtime}|{st.st_size}".encode("utf-8")).hexdigest()[:16]
    out = os.path.join(THUMBS, key + ".jpg")
    if os.path.isfile(out):
        return out
    try:
        if path.lower().endswith(IMAGE_EXT):
            from PIL import Image
            im = Image.open(path); im.thumbnail((width, width * 9 // 16)); im.convert("RGB").save(out, "JPEG", quality=82)
            return out
        ff = find_ffmpeg()
        d = probe_duration(path)
        t = "1" if d > 2 else "0"
        run_hidden([ff, "-hide_banner", "-loglevel", "error", "-y", "-ss", t, "-i", path, "-frames:v", "1",
                    "-vf", f"scale={width}:-2", out], timeout=30)
        return out if os.path.isfile(out) else ""
    except Exception:
        return ""


def frame_at(path: str, t: float, width=480) -> str:
    ff = find_ffmpeg()
    out = os.path.join(THUMBS, "_apercu_coupe.jpg")
    os.makedirs(THUMBS, exist_ok=True)
    run_hidden([ff, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{max(0, t):.2f}", "-i", path, "-frames:v", "1",
                "-vf", f"scale={width}:-2", out], timeout=20)
    return out if os.path.isfile(out) else ""


def trim(src: str, start: float, end: float, replace=False) -> str:
    """Coupe rapide sans re-encodage (-c copy) ; precise a ~1 s (une image cle par seconde)."""
    ff = find_ffmpeg()
    base, ext = os.path.splitext(src)
    out = unique(base + " (coupé)" + ext)
    r = run_hidden([ff, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{max(0, start):.2f}", "-to", f"{end:.2f}",
                    "-i", src, "-map", "0", "-c", "copy", "-avoid_negative_ts", "make_zero", "-movflags", "+faststart",
                    out], timeout=600)
    if r.returncode != 0 or not os.path.isfile(out):
        raise RuntimeError((r.stderr or b"").decode("utf-8", "replace")[-300:] or "coupe impossible")
    if replace:
        from .c02_win32 import recycle
        if recycle(src):
            os.replace(out, src)
            return src
    return out


def whisper_available() -> bool:
    try:
        import importlib.util
        return importlib.util.find_spec("faster_whisper") is not None
    except Exception:
        return False


def _srt_time(v: float) -> str:
    ms = int(round(v * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def make_srt(path: str, log=None, model_size="base", lang=None) -> str:
    """Sous-titres .srt a cote de la video (faster-whisper local, comme la transcription de l'Archiveur)."""
    from faster_whisper import WhisperModel  # type: ignore
    log = log or (lambda m: None)
    log("🎙 Chargement du modèle Whisper (1er usage : téléchargement)…")
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segs, info = model.transcribe(path, vad_filter=True, beam_size=1, language=lang)
    out = os.path.splitext(path)[0] + ".srt"
    n = 0
    with open(out, "w", encoding="utf-8") as f:
        for s in segs:
            t = (s.text or "").strip()
            if t:
                n += 1
                f.write(f"{n}\n{_srt_time(s.start)} --> {_srt_time(max(s.end, s.start + 0.5))}\n{t}\n\n")
    if not n:
        os.remove(out)
        raise RuntimeError("Aucune parole détectée.")
    log(f"💬 Sous-titres : {n} lignes ({getattr(info, 'language', '?')}).")
    return out


def send_to_archiveur(path: str, title: str = "", log=None) -> str:
    """Copie la video (+ .srt) dans un nouveau dossier d'archive, ecrit info.json et demande a l'Archiveur
    de mettre son index a jour (archiveur5.py --reindex). L'original reste dans CAPTURES."""
    log = log or (lambda m: None)
    sys.path.insert(0, HERE)
    try:
        import padawan_commun as pc
        root = pc.archiveur_root()
    except Exception:
        root = r"C:\web\FTP_HOME\ARCHIVEUR"
    title = title or os.path.splitext(os.path.basename(path))[0]
    slug = re.sub(r"[^a-z0-9]+", "-", re.sub(r"[^\w\s-]", "", title.lower()).strip())[:50].strip("-") or "capture"
    folder = unique(os.path.join(root, f"{datetime.now():%Y-%m-%d}_capture_{slug}"))
    os.makedirs(folder)
    files = []
    for p in (path, os.path.splitext(path)[0] + ".srt"):
        if os.path.isfile(p):
            shutil.copy2(p, os.path.join(folder, os.path.basename(p)))
            files.append(os.path.basename(p))
    info = {"title": title, "platform": "capture", "url": "", "webpage_url": "", "uploader": "Moi (CaptureScreen)",
            "description": "Enregistrement d'écran fait avec CaptureScreen.", "duration": round(probe_duration(path), 1),
            "archived_at": datetime.now().isoformat(timespec="seconds"), "folder": os.path.basename(folder),
            "media_files": [f for f in files if f.lower().endswith(VIDEO_EXT)], "method": "CaptureScreen",
            "tags": ["capture"], "notes": "", "source_file": path, "collections": ["Mes enregistrements"]}
    with open(os.path.join(folder, "info.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=1)
    arch = os.path.join(HERE, "archiveur5.py")
    if os.path.isfile(arch):
        exe = sys.executable
        if exe.lower().endswith("pythonw.exe"):
            exe = exe[:-11] + "python.exe" if os.path.isfile(exe[:-11] + "python.exe") else exe
        try:
            run_hidden([exe, arch, "--reindex", "--root", root], timeout=300, cwd=HERE)
        except Exception as e:
            log(f"Index de l'Archiveur : {e} (il se mettra à jour à sa prochaine ouverture)")
    log(f"📦 Envoyé à l'Archiveur : {os.path.basename(folder)}")
    return folder
