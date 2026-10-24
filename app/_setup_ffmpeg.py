# -*- coding: utf-8 -*-
"""Setup : installe ffmpeg + ffprobe (+ ffplay pour le lecteur integre) si absents (winget Gyan.FFmpeg puis zip gyan.dev)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
mod = None
for name in ("archiveur5", "archiveur4", "archiveur3", "archiveur2", "archiveur1"):
    try:
        mod = __import__(name)
        break
    except Exception:
        continue
if mod is None:
    print("Archiveur introuvable - ffmpeg non verifie.")
    raise SystemExit(1)
ok = mod.ensure_ffmpeg(print, ask_install=False)
ff = mod.find_ffmpeg()


def _sibling(fn_name, exe):
    fn = getattr(mod, fn_name, None)
    try:
        p = fn() if fn else None
    except Exception:
        p = None
    if not p and ff:
        cand = os.path.join(os.path.dirname(ff), exe)
        p = cand if os.path.isfile(cand) else None
    return p


fp = _sibling("find_ffprobe", "ffprobe.exe")
fy = _sibling("find_ffplay", "ffplay.exe")
print("ffmpeg :", ff or "MANQUANT")
print("ffprobe:", fp or "MANQUANT")
print("ffplay :", fy or "absent (lecteur integre sans son)")
raise SystemExit(0 if (ok and ff and fp) else 1)
