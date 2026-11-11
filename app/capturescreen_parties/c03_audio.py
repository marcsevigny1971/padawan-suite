# -*- coding: utf-8 -*-
"""CaptureScreen - c03 : son (WASAPI via le module soundcard) : son de l'ordinateur (bouclage) + micro.
Chaque source ecrit du PCM brut 48 kHz stereo 16 bits (s16le) directement sur disque, vide chaque seconde :
rien en memoire, et un plantage ne perd presque rien (la longueur se deduit de la taille du fichier)."""
from __future__ import annotations

import ctypes
import os
import threading
import time

try:
    import numpy as np
except Exception:  # pragma: no cover
    np = None

SR = 48000
BLOCK = 960  # 20 ms


def _sc():
    try:
        import soundcard  # type: ignore
        return soundcard
    except Exception:
        return None


def available() -> bool:
    return _sc() is not None and np is not None


def speakers():
    sc = _sc()
    try:
        return [s.name for s in sc.all_speakers()] if sc else []
    except Exception:
        return []


def microphones():
    sc = _sc()
    try:
        return [m.name for m in sc.all_microphones(include_loopback=False)] if sc else []
    except Exception:
        return []


def _com_init():
    try:
        ctypes.windll.ole32.CoInitializeEx(None, 0)
    except Exception:
        pass


def _open(kind: str, name: str):
    sc = _sc()
    if kind == "systeme":
        spk = None
        if name:
            try:
                spk = sc.get_speaker(name)
            except Exception:
                spk = None
        spk = spk or sc.default_speaker()
        return sc.get_microphone(id=str(spk.name), include_loopback=True)
    if name:
        try:
            return sc.get_microphone(name)
        except Exception:
            pass
    return sc.default_microphone()


class Source:
    """Lit la carte son en continu (niveaux) ; ecrit un WAV seulement entre begin() et end().
    Chaque WAV connait l'heure (horloge du PC) de son 1er echantillon : la video s'y cale au montage."""

    def __init__(self, kind: str, name: str, log=None, on_t0=None):
        self.kind, self.name, self.on_t0 = kind, name, on_t0
        self.log = log or (lambda m: None)
        self.level = 0.0
        self.stop_ev = threading.Event()
        self.ready = threading.Event()
        self.error = ""
        self._lock = threading.Lock()
        self._want = None        # chemin demande (begin) ; "" = fermer
        self._wf = None
        self._cur = None         # [chemin, t0, nb_echantillons]
        self.done = []           # [(chemin, t0, nb)]
        self.th = threading.Thread(target=self._run, daemon=True)

    def begin(self, path: str):
        with self._lock:
            self._want = path

    def end(self):
        with self._lock:
            self._want = ""

    def _apply(self):
        with self._lock:
            want, self._want = self._want, None
        if want is None:
            return
        if self._wf:
            self._wf.flush(); self._wf.close(); self._wf = None
            if self._cur and self._cur[2] > 0:
                self.done.append(tuple(self._cur))
            self._cur = None
        if want:
            self._wf = open(want, "wb")
            self._cur = [want, None, 0]
            self._flush_t = time.time()

    def _run(self):
        _com_init()
        try:
            dev = _open(self.kind, self.name)
            with dev.recorder(samplerate=SR, channels=2, blocksize=BLOCK) as rec:
                self.ready.set()
                while not self.stop_ev.is_set():
                    data = rec.record(numframes=BLOCK)
                    now = time.time()
                    self._apply()
                    if data is None or not len(data):
                        continue
                    if data.ndim == 1:
                        data = np.column_stack([data, data])
                    elif data.shape[1] == 1:
                        data = np.repeat(data, 2, axis=1)
                    elif data.shape[1] > 2:
                        data = data[:, :2]
                    self.level = float(min(1.0, np.sqrt(np.mean(np.square(data))) * 4))
                    if self._wf:
                        if self._cur[1] is None:
                            self._cur[1] = now - len(data) / SR
                            if self.on_t0:
                                try:
                                    self.on_t0(self.kind, self._cur[0], self._cur[1])
                                except Exception:
                                    pass
                        self._wf.write((np.clip(data, -1.0, 1.0) * 32767).astype("<i2").tobytes())
                        self._cur[2] += len(data)
                        if now - self._flush_t > 1.0:
                            self._wf.flush(); self._flush_t = now
                self._want = ""
                self._apply()
        except Exception as e:
            self.error = f"{self.kind} : {e}"
            self.log(f"Son {self.kind} indisponible : {e}")
        finally:
            self.ready.set()
            try:
                if self._wf:
                    self._wf.close()
            except Exception:
                pass


class AudioRecorder:
    """Une ou deux sources ; un WAV par source et par segment video."""

    def __init__(self, folder: str, sys_audio: bool, speaker: str, mic: bool, mic_name: str, log=None, on_t0=None):
        self.folder = folder
        self.sources = []
        if not available():
            return
        if sys_audio:
            self.sources.append(Source("systeme", speaker, log, on_t0))
        if mic:
            self.sources.append(Source("micro", mic_name, log, on_t0))

    def start(self):
        for s in self.sources:
            s.th.start()
        for s in self.sources:
            s.ready.wait(5)

    def begin(self, seg: int):
        for s in self.sources:
            s.begin(os.path.join(self.folder, f"son_{s.kind}_{seg:03d}.pcm"))

    def end(self):
        for s in self.sources:
            s.end()

    def stop(self):
        for s in self.sources:
            s.end(); s.stop_ev.set()
        for s in self.sources:
            s.th.join(timeout=3)

    def tracks(self):
        """{source: {chemin: (t0, duree)}} des WAV termines."""
        out = {}
        for s in self.sources:
            if s.error and not s.done:
                continue
            out[s.kind] = {p: (t0, n / SR) for p, t0, n in s.done if t0 is not None and os.path.isfile(p)}
        return out

    @property
    def frames(self):
        return sum(sum(n for _p, _t, n in s.done) + (s._cur[2] if s._cur else 0) for s in self.sources)

    def levels(self):
        return {s.kind: s.level for s in self.sources}

    def errors(self):
        return [s.error for s in self.sources if s.error]


def test_levels(seconds=2.0, sys_audio=True, speaker="", mic=False, mic_name=""):
    """Petit test des niveaux (sans fichier) : retourne {source: niveau max}."""
    import tempfile
    d = tempfile.mkdtemp(prefix="cs_son_")
    a = AudioRecorder(d, sys_audio, speaker, mic, mic_name)
    a.start()
    best = {}
    t0 = time.time()
    while time.time() - t0 < seconds:
        for k, v in a.levels().items():
            best[k] = max(best.get(k, 0), v)
        time.sleep(0.05)
    a.stop()
    import shutil
    shutil.rmtree(d, ignore_errors=True)
    return best, a.errors()
