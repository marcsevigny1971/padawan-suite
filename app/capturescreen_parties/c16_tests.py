# -*- coding: utf-8 -*-
"""CaptureScreen : tests de robustesse (minuteur = duree, longue session simulee, reprise auto de ffmpeg)."""
from __future__ import annotations

import os
import shutil
import time

from .c01_config import TMP_DIR, load_cfg, run_hidden, find_ffmpeg
from .c02_win32 import monitors


def _audio_dur(path: str) -> float:
    fp = find_ffmpeg("ffprobe")
    r = run_hidden([fp, "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=duration", "-of", "csv=p=0", path],
                   timeout=60)
    try:
        return float((r.stdout or b"0").decode().strip().splitlines()[0])
    except Exception:
        return 0.0


def test_robust(seconds: float = 75, keep: bool = False, audio: bool = True) -> int:
    """Morceaux de 10 s (au lieu de 10 min) pendant N s, ffmpeg tue 2 fois en route (reprise auto attendue),
    1 pause, puis : duree video = minuteur, son de la meme longueur, video lisible, fiche resume juste."""
    from .c04_recorder import Recorder, probe_duration
    from .c12_extras import read_card
    ok = True

    def check(label, cond, extra=""):
        nonlocal ok
        ok = ok and bool(cond)
        print(f"   {'OK ' if cond else 'ÉCHEC'} {label} {extra}", flush=True)
    cfg = load_cfg()
    cfg.update(sys_audio=audio, mic=False, webcam=False, engine="auto", fps=30, quality="bonne", _seg_s=10)
    m = monitors()[0]
    out_dir = os.path.join(TMP_DIR, "_test_robuste")
    os.makedirs(out_dir, exist_ok=True)
    logs = []
    print(f"== 1. minuteur = durée (3 essais de 4 s) ==", flush=True)
    for i in range(3):
        rec = Recorder(cfg, (m["x"], m["y"], m["w"], m["h"]), log=logs.append)
        rec.start()
        while rec.elapsed() < 4.0:
            time.sleep(0.05)
        rec.stop()
        out = rec.finish(out_dir, f"test_minuteur_{i}")
        d = probe_duration(out)
        check(f"essai {i + 1} : minuteur 4,00 s → vidéo {d:.2f} s", abs(d - 4.0) <= 0.5, f"(écart {d - 4.0:+.2f} s)")
        os.remove(out)
    print(f"== 2. session simulée {seconds:.0f} s, morceaux de 10 s, ffmpeg tué 2 fois, 1 pause ==", flush=True)
    rec = Recorder(cfg, (m["x"], m["y"], m["w"], m["h"]), log=lambda s: (logs.append(s), print("  ", s, flush=True)))
    rec.start()
    kills = [seconds * 0.3, seconds * 0.6]
    paused = False
    t_wall0 = time.time()
    while rec.elapsed() < seconds:
        e = rec.elapsed()
        if kills and e >= kills[0]:
            kills.pop(0)
            print(f"   >>> ffmpeg tué à {e:.1f} s (panne simulée)", flush=True)
            try:
                rec.proc.kill()
            except Exception:
                pass
            t_k = time.time()
            while rec.repairs < 2 - len(kills) and time.time() - t_k < 15:
                time.sleep(0.1)
            print(f"   reprise en {time.time() - t_k:.1f} s", flush=True)
        if not paused and e >= seconds * 0.8:
            paused = True
            rec.pause(); time.sleep(1.5); rec.resume()
        time.sleep(0.1)
    timer = rec.elapsed()
    rec.stop()
    nparts = sum(len(rec._parts(a["n"])) for a in rec.man["attempts"])
    check("reprises automatiques", rec.repairs == 2, f"({rec.repairs})")
    check("plusieurs morceaux de 10 s", nparts >= int(seconds // 10), f"({nparts} morceaux, {len(rec.man['attempts'])} essais)")
    out = rec.finish(out_dir, "test_robuste")
    d = probe_duration(out)
    check(f"durée vidéo {d:.2f} s ≈ minuteur {timer:.2f} s", abs(d - timer) <= 1.5 + 0.5 * 2)
    if audio:
        ad = _audio_dur(out)
        check(f"son {ad:.2f} s ≈ vidéo", abs(ad - d) <= 0.6)
    r = run_hidden([find_ffmpeg(), "-v", "error", "-i", out, "-f", "null", "-"], timeout=600)
    check("décodage complet sans erreur", r.returncode == 0 and not (r.stderr or b"").strip(),
          (r.stderr or b"").decode("utf-8", "replace")[-200:])
    card = read_card(out)
    check("fiche résumé : 2 réparations, 1 pause", card.get("reparations") == 2 and card.get("pauses") == 1,
          f"({card.get('reparations')}, {card.get('pauses')})")
    check("dossier de travail nettoyé", not os.path.isdir(rec.work))
    print(f"   (temps réel {time.time() - t_wall0:.0f} s, fichier {os.path.getsize(out) // 1024} Ko)", flush=True)
    if not keep:
        shutil.rmtree(out_dir, ignore_errors=True)
        print("   fichiers test supprimés.")
    print("RÉSULTAT :", "tout est OK" if ok else "au moins un ÉCHEC")
    return 0 if ok else 1
