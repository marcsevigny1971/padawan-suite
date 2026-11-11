# -*- coding: utf-8 -*-
"""CaptureScreen - c10 : point d'entree + tests en ligne de commande.
  --test-record N [--keep] [--no-audio] [--gdigrab]   enregistre N s de l'ecran principal + son (sans fenetre)
  --test-shot                                         capture PNG de l'ecran principal (puis supprimee)
  --smoke N  /  --shot fichier.png                    ouvre l'interface, (capture), ferme apres N s
  --selftest                                          verifie modules, ffmpeg, son, moniteurs
  --test-robustesse [N]                               minuteur = duree + session de N s en morceaux de 10 s, pannes simulees
  --enregistrer --mode ecran|fenetre|zone --titre T --root R --dossier D [--url U --ouvrir-site]
      [--son 1 --micro 0 --webcam 0 --touches 1 --clics 1]   demande venue de l'Archiveur (video → fiche)
      tests : --auto-stop N (arrete apres N s)  --sans-compte (pas de 3-2-1)  --test-handoff (ne sauve pas les reglages)"""
from __future__ import annotations

import argparse
import os
import sys
import time
import traceback

from .c01_config import APP, VERSION, find_ffmpeg, load_cfg, logger, setup_logging, pick_encoder, human_size, TMP_DIR
from .c02_win32 import monitors, set_dpi_aware


def _probe_report(out, seconds):
    from .c04_recorder import probe_duration
    from .c01_config import run_hidden
    fp = find_ffmpeg("ffprobe")
    r = run_hidden([fp, "-v", "error", "-show_entries", "stream=codec_type,codec_name,width,height,r_frame_rate,sample_rate",
                    "-of", "compact", out], timeout=30)
    print("   fichier :", out, human_size(os.path.getsize(out)), f"durée {probe_duration(out):.2f} s (visé ~{seconds:.1f} s)")
    print("  ", (r.stdout or b"").decode().strip().replace("\n", "\n   "))
    d = run_hidden([find_ffmpeg(), "-v", "error", "-i", out, "-f", "null", "-"], timeout=300)
    ok = d.returncode == 0 and not d.stderr.strip()
    print("   décodage complet :", "OK" if ok else (d.stderr or b"").decode()[-300:])
    return ok


def _test_record(seconds: float, keep: bool, audio: bool, engine: str, seg_s: int = 0, crash: bool = False) -> int:
    from .c04_recorder import Recorder, assemble, leftovers
    cfg = load_cfg()
    cfg.update(sys_audio=audio, mic=False, webcam=False, engine=engine, fps=30, quality="bonne")
    if seg_s:
        cfg["_seg_s"] = seg_s
    m = monitors()[0]
    out_dir = os.path.join(TMP_DIR, "_test")
    rec = Recorder(cfg, (m["x"], m["y"], m["w"], m["h"]), log=lambda s: print("  ", s, flush=True))
    rec.start()
    t0 = time.time()
    while time.time() - t0 < seconds / 2:
        time.sleep(0.25)
    rec.pause(); print("   pause 1 s", flush=True); time.sleep(1.0); rec.resume()
    while rec.elapsed() < seconds:
        time.sleep(0.1)
    print(f"   niveaux son : {rec.levels()}  erreurs son : {rec.audio.errors()}", flush=True)
    if crash:
        print("   >>> plantage simulé : ffmpeg tué, rien de finalisé", flush=True)
        rec.state = "plante"  # tout le programme « plante » : pas de reprise automatique
        rec.proc.kill(); rec.proc.wait()
        for s in rec.audio.sources:
            s.stop_ev.set()
        time.sleep(0.5)
        left = [l for l in leftovers() if l[0] == rec.work]
        print("   récupération proposée :", bool(left), "| morceaux :",
              len([f for f in os.listdir(rec.work) if f.endswith('.mkv')]), flush=True)
        out = assemble(rec.work, out_dir, "test_recup")
    else:
        rec.stop()
        print("   morceaux :", sorted(f for f in os.listdir(rec.work) if f.endswith(".mkv")), flush=True)
        print("   segments :", [round(a["dur"] or 0, 2) for a in rec.man["attempts"]], "| latence mesurée :",
              rec.man.get("latency"), flush=True)
        out = rec.finish(out_dir, "test_capturescreen")
    ok = _probe_report(out, seconds)
    print("   dossier de travail nettoyé :", not os.path.isdir(rec.work))
    if not keep:
        os.remove(out)
        try:
            os.rmdir(out_dir)
        except OSError:
            pass
        print("   fichier test supprimé.")
    return 0 if ok else 1


def _test_upgrades(keep: bool = False) -> int:
    """Reperes/chapitres, fiche resume, son seulement (+ panne), webcam (mire), outils de montage."""
    import glob
    import shutil
    from .c04_recorder import Recorder, assemble, leftovers, probe_duration
    from .c12_extras import make_audio_recorder, read_card, read_chapters
    from . import c13_edit as E
    ok = True
    cfg = load_cfg()
    cfg.update(sys_audio=True, mic=False, webcam=False, engine="auto", fps=30, quality="bonne")
    m = monitors()[0]
    rect = (m["x"], m["y"], m["w"], m["h"])
    out_dir = os.path.join(TMP_DIR, "_test_up")
    os.makedirs(out_dir, exist_ok=True)

    def check(label, cond, extra=""):
        nonlocal ok
        ok = ok and bool(cond)
        print(f"   {'OK ' if cond else 'ÉCHEC'} {label} {extra}", flush=True)
    print("== 1. vidéo 6 s + 2 repères + pause ==", flush=True)
    rec = Recorder(cfg, rect, log=lambda s: None)
    rec.start(); time.sleep(2.0); rec.add_marker("Introduction"); time.sleep(1.0)
    rec.pause(); time.sleep(1.0); rec.resume(); time.sleep(1.5); rec.add_marker(""); time.sleep(1.5)
    rec.stop()
    v = rec.finish(out_dir, "test_reperes")
    ch = read_chapters(v); card = read_card(v)
    check("chapitres dans le MP4", len(ch) == 3, str([(c["t"], c["label"]) for c in ch]))
    check("fiche résumé", len(card.get("reperes") or []) == 2 and card.get("pauses") == 1,
          f"durée {card.get('duree')} s, repères {card.get('reperes')}")
    check("décodage", _probe_report(v, 6.0))
    print("== 2. son seulement 4 s (+ pause), M4A et MP3 ==", flush=True)
    A = make_audio_recorder(Recorder)
    for fmt in ("m4a", "mp3"):
        r = A(dict(cfg, source="son", audio_fmt=fmt), rect, log=lambda s: None)
        r.start(); time.sleep(2.0); r.add_marker("milieu"); r.pause(); time.sleep(0.8); r.resume(); time.sleep(2.0); r.stop()
        a = r.finish(out_dir, f"test_son_{fmt}")
        info = E.probe(a)
        check(f"son {fmt}", a.endswith("." + fmt) and not info["has_video"] and info["has_audio"] and 3.4 < info["duration"] < 5.2,
              f"{os.path.basename(a)} {info['duration']:.2f} s")
    print("== 3. son seulement : panne puis récupération ==", flush=True)
    r = A(dict(cfg, source="son"), rect, log=lambda s: None)
    r.start(); time.sleep(3.0)
    for s in r.audio.sources:
        s.stop_ev.set()
    time.sleep(0.6)
    left = [l for l in leftovers() if l[0] == r.work]
    check("récupération proposée", bool(left))
    a = assemble(r.work, out_dir, "test_son_recup")
    check("son récupéré", 2.0 < probe_duration(a) < 4.5, f"{probe_duration(a):.2f} s")
    print("== 4. webcam (mire de test) en haut à gauche, petite ==", flush=True)
    wc = Recorder(dict(cfg, webcam=True, webcam_name="mire", cam_pos="hg", cam_size="petite",
                       _cam_test_src="testsrc2=size=640x360:rate=30"), rect, log=lambda s: None)
    wc.start(); time.sleep(3.0); wc.stop()
    w = wc.finish(out_dir, "test_webcam")
    from .c04_recorder import frame_at
    fr = frame_at(w, 1.5, width=1920)
    from PIL import Image
    im = Image.open(fr).convert("RGB")
    px = im.getpixel((26, 26))
    check("bulle webcam (cadre blanc en haut à gauche)", min(px) > 200, f"pixel {px}")
    print("== 5. outils de montage (nouveaux fichiers) ==", flush=True)
    srt = os.path.splitext(v)[0] + ".srt"
    with open(srt, "w", encoding="utf-8") as f:
        f.write("1\n00:00:00,500 --> 00:00:03,000\nBonjour la classe\n\n")
    for label, fn, args, cond in (
            ("version à partager", E.share_version, (v, 720, True), lambda p, i: i["h"] <= 720 and i["has_audio"]),
            ("extrait MP4", E.clip, (v, 1.0, 3.0), lambda p, i: 1.6 < i["duration"] < 2.5),
            ("GIF", E.clip, (v, 1.0, 3.0, True), lambda p, i: p.endswith(".gif") and os.path.getsize(p) > 1000),
            ("enlever un passage", E.cut_middle, (v, 1.0, 3.0), lambda p, i: abs(i["duration"] - (probe_duration(v) - 2)) < 0.6),
            ("joindre", E.join, ([v, w],), lambda p, i: abs(i["duration"] - probe_duration(v) - probe_duration(w)) < 0.8),
            ("son amélioré", E.clean_audio, (v,), lambda p, i: i["has_audio"] and i["has_video"]),
            ("son en MP3", E.audio_only, (v, True), lambda p, i: p.endswith(".mp3") and i["has_audio"]),
            ("sous-titres incrustés", E.burn_subtitles, (v,), lambda p, i: i["has_video"])):
        try:
            t0 = time.time()
            p = fn(*args)
            i = E.probe(p)
            check(label, cond(p, i), f"{os.path.basename(p)} {i['duration']:.2f} s {i['w']}x{i['h']} ({time.time() - t0:.1f} s)")
        except Exception as e:
            check(label, False, str(e))
    if not keep:
        shutil.rmtree(out_dir, ignore_errors=True)
        print("   fichiers de test supprimés.", flush=True)
    return 0 if ok else 1


def _selftest() -> int:
    from . import c03_audio
    ff = find_ffmpeg()
    print(APP, VERSION)
    print("ffmpeg :", ff)
    print("encodeur :", pick_encoder(ff) if ff else "-")
    print("moniteurs :", [m["label"] for m in monitors()])
    print("son : soundcard", c03_audio.available(), "| haut-parleurs", c03_audio.speakers(), "| micros", c03_audio.microphones())
    from .c04_recorder import list_webcams, whisper_available
    print("webcams :", list_webcams(ff), "| faster-whisper :", whisper_available())
    return 0


def main(argv=None) -> int:
    setup_logging()
    set_dpi_aware()
    ap = argparse.ArgumentParser(prog="capturescreen1.py")
    ap.add_argument("--test-record", type=float, default=0)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--no-audio", action="store_true")
    ap.add_argument("--gdigrab", action="store_true")
    ap.add_argument("--seg-seconds", type=int, default=0)
    ap.add_argument("--crash", action="store_true")
    ap.add_argument("--test-shot", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--smoke", type=float, default=0)
    ap.add_argument("--shot", default="")
    ap.add_argument("--shot-view", default="")
    ap.add_argument("--enregistrer", action="store_true")
    ap.add_argument("--mode", default="ecran", choices=["ecran", "fenetre", "zone", "son"])
    ap.add_argument("--titre", default="")
    ap.add_argument("--root", default="")
    ap.add_argument("--dossier", default="")
    ap.add_argument("--url", default="")
    ap.add_argument("--ouvrir-site", action="store_true")
    for k in ("son", "micro", "webcam", "touches", "clics"):
        ap.add_argument("--" + k, type=int, choices=[0, 1], default=None)
    ap.add_argument("--auto-stop", type=float, default=0)
    ap.add_argument("--sans-compte", action="store_true")
    ap.add_argument("--test-handoff", action="store_true")
    ap.add_argument("--test-upgrades", action="store_true")
    ap.add_argument("--test-robustesse", type=float, nargs="?", const=75, default=0)
    a = ap.parse_args(argv)
    try:
        if a.selftest:
            return _selftest()
        if a.test_upgrades:
            return _test_upgrades(a.keep)
        if a.test_robustesse:
            from .c16_tests import test_robust
            return test_robust(a.test_robustesse, a.keep, not a.no_audio)
        if a.test_record:
            return _test_record(a.test_record, a.keep, not a.no_audio, "gdigrab" if a.gdigrab else "auto",
                                a.seg_seconds, a.crash)
        if a.test_shot:
            from .c04_recorder import screenshot
            m = monitors()[0]
            p, ok = screenshot((m["x"], m["y"], m["w"], m["h"]), os.path.join(TMP_DIR, "_test"), to_clipboard=False)
            from PIL import Image
            print("capture :", p, Image.open(p).size, human_size(os.path.getsize(p)))
            os.remove(p)
            return 0
    except Exception:
        traceback.print_exc()
        return 1
    from .c02_win32 import single_instance, front_existing
    req = None
    if a.enregistrer:
        from .c11_archiveur import request_from_args, write_request
        req = request_from_args(a)
        logger.info("demande de l'Archiveur : %s", {k: v for k, v in req.items() if k != "url"})
    if not (a.smoke or a.shot) and not single_instance():
        if req:  # CaptureScreen deja ouvert : il prend la demande (fichier lu toutes les 0,7 s)
            write_request(req)
        else:
            front_existing(APP)
        return 0
    from .c09_app import run_app
    return run_app(smoke=a.smoke, shot=a.shot, shot_view=a.shot_view, request=req)
