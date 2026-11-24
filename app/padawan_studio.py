# -*- coding: utf-8 -*-
"""padawan_studio.py — 🎨 Studio d'images de Padawan (v41.0).

Idée en français → (option) prompt anglais via le modèle Ollama courant → image générée en local par
ComfyUI (127.0.0.1 seulement, démarré à la demande) → conversion immédiate en art ANSI (padawan_ansi).

Le moteur (ComfyUI portable + modèle) n'est JAMAIS téléchargé sans confirmation explicite ; il n'est pas
fourni avec Padawan (trop gros) et le script de distribution refuse de l'embarquer.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import random
import re
import shutil
import subprocess
import threading
import time
import unicodedata
import urllib.error
import urllib.request
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
except Exception:  # tests sans Tk
    tk = None  # type: ignore

try:
    import padawan_ansi as _ANSI
except Exception:
    _ANSI = None

VERSION = "1.4"  # v41.6 : style La Légende s'écrit (peinture fantasy années 80, couverture de livre-jeu, enluminure dorée) ; v41.5 : style Galaxie 42 (SF rétro années 70-80) ; v41.4 : image à chaque action (gros plan sur un examen), annulation des images périmées ; v41.3 : scènes de jeu résumées par le modèle de jeu (JSON), images couleur, VRAM

# ───────────────────────────────────────────────────────────── réglages ──
DEFAULTS: Dict[str, Any] = {
    "engine_dir": r"C:\IA\ComfyUI",   # dossier ComfyUI portable (python_embeded + ComfyUI\main.py)
    "port": 8188,
    "extra_args": "--disable-pinned-memory --offline",  # PC à 8 Go de RAM : pas de RAM épinglée ; pas d'internet
    "idle_min": 10,                   # arrêt auto du moteur après N minutes sans image (0 = jamais)
    "model": "sd_turbo",
    "style": "postapo",
    "size": "paysage",
    "steps": 2,
    "seed": -1,
    "lock_seed": False,
    "enhance": True,                  # ✨ idée FR → prompt EN par le modèle Ollama courant
    "ansi_style": "auto",
    "ansi_cols": 80,
    "vram": "auto",                   # auto | toujours | jamais (libérer Ollama avant de générer)
    "game_timeout": 90,               # s — au-delà, le jeu garde l'image de la banque
    "game_enhance": True,
    "history_max": 400,
}

MODELS: Dict[str, Dict[str, Any]] = {
    "sd_turbo": {
        "label": "SD-Turbo (Stability AI, fp16, 2,6 Go)",
        "unet": "sd_turbo_unet.fp16.safetensors",
        "clip": "sd_turbo_te.fp16.safetensors",
        "vae": "sd_turbo_vae.fp16.safetensors",
        "steps": (1, 4), "cfg": 1.0, "sampler": "euler_ancestral",
        # sources officielles (Hugging Face stabilityai/sd-turbo) + SHA-256 publiés par le dépôt
        "files": [
            ("diffusion_models", "sd_turbo_unet.fp16.safetensors",
             "https://huggingface.co/stabilityai/sd-turbo/resolve/main/unet/diffusion_pytorch_model.fp16.safetensors",
             1731904736, "40ec400881e27d1376c7c95c5bd495f407b33756e80eb6365e301c33a07af6e5"),
            ("text_encoders", "sd_turbo_te.fp16.safetensors",
             "https://huggingface.co/stabilityai/sd-turbo/resolve/main/text_encoder/model.fp16.safetensors",
             680820392, "bc1827c465450322616f06dea41596eac7d493f4e95904dcb51f0fc745c4e13f"),
            ("vae", "sd_turbo_vae.fp16.safetensors",
             "https://huggingface.co/stabilityai/sd-turbo/resolve/main/vae/diffusion_pytorch_model.fp16.safetensors",
             167335342, "3e4c08995484ee61270175e9e7a072b66a6e4eeb5f0c266667fe1f45b90daf9a"),
        ],
    },
}

# moteur : ComfyUI portable officiel (GitHub Comfy-Org/ComfyUI) + 7zr officiel (GitHub ip7z/7zip) pour l'extraire
ENGINE_PKG = ("https://github.com/Comfy-Org/ComfyUI/releases/download/v0.45.0/ComfyUI_windows_portable_nvidia.7z",
              2071479423, "60c12e8c7af778047ad0413722dd3dc0f6ca773a41cbf5cb229ee9bc92c44a6f")
SEVENZR = ("https://github.com/ip7z/7zip/releases/download/26.06/7zr.exe", 600064,
           "e80db2dad715a6c5adabe292d31ed54e11f4e9b99ca349827b50573b175891bc")

SIZES: List[Tuple[str, str, int, int]] = [  # (id, libellé, largeur, hauteur) — tout tient dans 8 Go
    ("carre", "◻ Carré 512×512", 512, 512),
    ("paysage", "▭ Paysage 640×384", 640, 384),
    ("portrait", "▯ Portrait 384×640", 384, 640),
    ("large", "▬ Large 768×448", 768, 448),
    ("petit", "· Rapide 384×384", 384, 384),
]

# styles « un clic » : (id, libellé, suffixe anglais du prompt, style ANSI conseillé)
STYLES: List[Tuple[str, str, str, str]] = [
    ("postapo", "☢ Post-apo rétro",
     "retro-futuristic post-apocalyptic wasteland, 1950s atomic age design, rusted metal, desaturated green tint, "
     "dramatic light, detailed concept art", "pipboy"),
    ("pixel", "👾 Pixel art DOS",
     "pixel art, 16-color EGA palette, 1990 DOS adventure game screenshot, crisp large pixels, dithering", "dos16"),
    ("aquarelle", "🎨 Aquarelle",
     "watercolor painting, soft washes, visible paper texture, delicate ink outlines, pastel colors", "truecolor"),
    ("photo", "📷 Photo",
     "photograph, 35mm film, natural light, sharp focus, realistic, detailed", "truecolor"),
    ("affiche", "🖼 Affiche rétro",
     "vintage 1930s travel poster, flat bold colors, simple shapes, screen print, art deco lettering-free", "dos16"),
    ("noir", "🕵 Film noir",
     "film noir, black and white photograph, high contrast, hard shadows, rain, 1940s, single red neon accent", "noir"),
    ("libre", "∅ Sans style", "", "truecolor"),
]
STYLE_IDS = [s[0] for s in STYLES]

# jeux → style d'image + palette ANSI de la banque
GAME_STYLE = {"fallout": ("postapo", "pipboy"), "donjon": ("pixel", "dos16"), "polar": ("noir", "noir"),
              "galaxie": ("libre", "truecolor"), "legende": ("libre", "truecolor")}

# v41.3 : scènes générées en COULEUR — une touche d'ambiance légère (le sujet passe d'abord : CLIP coupe à 77 jetons)
GAME_GEN_LOOK = {
    "fallout": "retro-futuristic 1950s atomic age wasteland, vibrant colors, detailed",
    "donjon": "dark fantasy dungeon adventure, torchlight, rich colors, detailed illustration",
    "galaxie": "planets, spaceships, starbases and aliens, deep space, vibrant colors, detailed",
    "legende": "medieval fantasy kingdom, knights, castles, dragons and magic, rich warm vibrant colors, detailed",
    "polar": "1940s noir city, moody cinematic color, rain, neon reflections, detailed illustration",
}
GAME_GEN_ANSI = "truecolor"   # ANSI couleur (▀▄ 24 bits) : bien différent des 31 illustrations de la banque
GAME_GEN_COLS = 84


# v41.4 : style BD léger à la Fallout, placé en tête (CLIP coupe à 77 jetons, la fin du sujet saute en premier)
GAME_GEN_PRE = {"fallout": "comic book illustration, retro-futuristic, inked lines, vibrant colors",
                "galaxie": "retro 1970s 1980s science fiction paperback cover art, inked outlines, vibrant colors",
                "legende": "1980s fantasy oil painting, gamebook cover art, gilded illuminated border, rich colors"}


def game_full_prompt(subject: str, fam: str, closeup: bool = False) -> str:
    look = GAME_GEN_LOOK.get(fam, "cinematic color, detailed illustration")
    pre = GAME_GEN_PRE.get(fam, "")
    if closeup:  # v41.4 : un examen = gros plan de l'objet (en tête : c'est ce que SD-Turbo respecte le mieux)
        pre = "extreme close-up of a single object filling the frame, " + pre
    return sanitize_prompt((f"{pre}, " if pre else "") + f"{subject.strip(' ,.')}, {look}")


def _json_obj(txt: str) -> Dict[str, Any]:
    t = (txt or "").strip()
    try:
        d = json.loads(t)
        return d if isinstance(d, dict) else {}
    except Exception:
        pass
    m = re.search(r"\{.*\}", t, re.S)
    if m:
        try:
            d = json.loads(m.group(0))
            return d if isinstance(d, dict) else {}
        except Exception:
            return {}
    return {}


BRIEF_KINDS = ("lieu", "combat", "personnage", "evenement", "aucun")

# pas de marques ni de personnages protégés dans les prompts envoyés au moteur
_TM = [(r"\bfallout\b", "post-apocalyptic"), (r"\bvault[- ]?tec\b", "retro corporation"),
       (r"\bvault[- ]?boy\b", "cartoon mascot"), (r"\bpip[- ]?boy\b", "retro wrist computer"),
       (r"\bnuka[- ]?cola\b", "retro soda"), (r"\bbrotherhood of steel\b", "armored knights"),
       (r"\b(disney|marvel|nintendo|pokemon|mickey|mario|batman|star wars)\b", "")]


def sanitize_prompt(p: str) -> str:
    s = p or ""
    for rx, rep in _TM:
        s = re.sub(rx, rep, s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip(" ,.")
    return s[:600]


def fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn").lower()


def style_info(sid: str) -> Tuple[str, str, str, str]:
    for s in STYLES:
        if s[0] == sid:
            return s
    return STYLES[0]


def size_info(zid: str) -> Tuple[str, str, int, int]:
    for z in SIZES:
        if z[0] == zid:
            return z
    return SIZES[1]


def full_prompt(subject: str, sid: str) -> str:
    suf = style_info(sid)[2]
    return sanitize_prompt(", ".join(x for x in (subject.strip(" ,."), suf) if x))


def clean_env() -> Dict[str, str]:
    """Environnement propre pour le moteur : pas de PYTHON*/PADAWAN* hérités (pas de fuite de réglages de test)."""
    env = {k: v for k, v in os.environ.items()
           if not k.upper().startswith(("PYTHON", "PADAWAN", "TCL_", "TK_", "PIP_", "VIRTUAL_ENV", "CONDA"))}
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def load_cfg(path: str) -> Dict[str, Any]:
    cfg = dict(DEFAULTS)
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict):
            cfg.update({k: v for k, v in d.items() if k in DEFAULTS})
    except Exception:
        pass
    return cfg


def save_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


# ──────────────────────────────────────────────────────────── moteur ──
class EngineError(Exception):
    pass


class Engine:
    """ComfyUI portable piloté en arrière-plan : 127.0.0.1 seulement, démarré à la demande, arrêté au repos."""

    def __init__(self, cfg: Dict[str, Any], workdir: str, log: Callable[[str], None] = lambda m: None):
        self.cfg, self.workdir, self.log = cfg, workdir, log
        self.proc: Optional[subprocess.Popen] = None
        self.ours = False
        self.last_use = time.time()
        self.lock = threading.RLock()
        self.client_id = uuid.uuid4().hex
        self.started_s = 0.0

    # chemins
    @property
    def root(self) -> str:
        return os.path.normpath(self.cfg.get("engine_dir") or DEFAULTS["engine_dir"])

    @property
    def python(self) -> str:
        return os.path.join(self.root, "python_embeded", "python.exe")

    @property
    def main_py(self) -> str:
        return os.path.join(self.root, "ComfyUI", "main.py")

    def models_dir(self, sub: str = "") -> str:
        return os.path.join(self.root, "ComfyUI", "models", sub)

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{int(self.cfg.get('port') or 8188)}"

    def installed(self) -> bool:
        return os.path.isfile(self.python) and os.path.isfile(self.main_py)

    def missing_models(self, model: str = "") -> List[str]:
        m = MODELS.get(model or self.cfg.get("model") or "sd_turbo", MODELS["sd_turbo"])
        return [n for sub, n, *_ in m["files"] if not os.path.isfile(os.path.join(self.models_dir(sub), n))]

    def ready_to_run(self) -> bool:
        return self.installed() and not self.missing_models()

    def size_gb(self) -> float:
        tot = 0
        for dp, _, fs in os.walk(self.root):
            for f in fs:
                try:
                    tot += os.path.getsize(os.path.join(dp, f))
                except OSError:
                    pass
        return tot / 1e9

    # HTTP
    def _req(self, path: str, data: Any = None, timeout: float = 10.0, raw: bool = False):
        body = None if data is None else json.dumps(data).encode("utf-8")
        rq = urllib.request.Request(self.base + path, data=body,
                                    headers={"Content-Type": "application/json"} if body else {})
        with urllib.request.urlopen(rq, timeout=timeout) as r:
            b = r.read()
        if raw:
            return b
        return json.loads(b.decode("utf-8") or "null") if b else None

    def alive(self, timeout: float = 1.5) -> Optional[Dict[str, Any]]:
        try:
            d = self._req("/system_stats", timeout=timeout)
            return d if isinstance(d, dict) and "system" in d else None
        except Exception:
            return None

    def running(self) -> bool:
        if self.proc is not None and self.proc.poll() is not None:
            self.proc, self.ours = None, False
        return self.alive() is not None

    def vram_free(self) -> int:
        d = self.alive()
        try:
            return int(d["devices"][0]["vram_free"])
        except Exception:
            return -1

    def status_text(self) -> str:
        if not self.installed():
            return "non installé"
        if self.missing_models():
            return "modèle manquant"
        if self.running():
            return "démarré" + ("" if self.ours else " (lancé hors de Padawan)")
        return "arrêté"

    def start(self, timeout: float = 180.0, cancel: Optional[threading.Event] = None) -> bool:
        with self.lock:
            if self.alive():
                return True
            if not self.installed():
                raise EngineError("moteur d'images non installé (🎨 Studio → Moteur)")
            os.makedirs(self.workdir, exist_ok=True)
            lp = os.path.join(self.workdir, "comfyui.log")
            try:
                if os.path.isfile(lp) and os.path.getsize(lp) > 4_000_000:
                    os.replace(lp, lp + ".old")
            except OSError:
                pass
            args = [self.python, "-s", self.main_py, "--windows-standalone-build", "--listen", "127.0.0.1",
                    "--port", str(int(self.cfg.get("port") or 8188)), "--disable-auto-launch",
                    "--output-directory", os.path.join(self.workdir, "_comfy_out"),
                    "--temp-directory", os.path.join(self.workdir, "_comfy_tmp")]
            args += [a for a in str(self.cfg.get("extra_args") or "").split() if a.startswith("--")
                     and not a.startswith(("--listen", "--port", "--enable-cors"))]
            flags = 0
            if os.name == "nt":
                flags = 0x08000000 | 0x00000200  # CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
            self.log("studio: démarrage ComfyUI " + " ".join(args[2:]))
            t0 = time.time()
            self._logf = open(lp, "a", encoding="utf-8", errors="replace")
            self._logf.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} Padawan démarre ComfyUI =====\n")
            self._logf.flush()
            self.proc = subprocess.Popen(args, cwd=self.root, env=clean_env(), stdin=subprocess.DEVNULL,
                                         stdout=self._logf, stderr=subprocess.STDOUT, creationflags=flags)
            self.ours = True
        while time.time() - t0 < timeout:
            if cancel is not None and cancel.is_set():
                self.stop()
                raise EngineError("démarrage annulé")
            if self.proc is not None and self.proc.poll() is not None:
                raise EngineError(f"ComfyUI s'est arrêté au démarrage (code {self.proc.returncode}) — "
                                  f"voir {os.path.join(self.workdir, 'comfyui.log')}")
            if self.alive(timeout=1.0):
                self.started_s = time.time() - t0
                self.last_use = time.time()
                self.log(f"studio: ComfyUI prêt en {self.started_s:.1f} s")
                return True
            time.sleep(0.5)
        raise EngineError("ComfyUI ne répond pas (délai dépassé)")

    def free(self) -> bool:
        """Vide la carte graphique côté ComfyUI (avant que le modèle de texte recharge)."""
        try:
            self._req("/free", {"unload_models": True, "free_memory": True}, timeout=5)
            return True
        except Exception:
            return False

    def interrupt(self) -> None:
        try:
            self._req("/interrupt", {}, timeout=3)
        except Exception:
            pass

    def stop(self) -> bool:
        """Arrête le moteur s'il a été lancé par Padawan (jamais un ComfyUI ouvert par l'utilisateur)."""
        with self.lock:
            p = self.proc
            if p is None or not self.ours:
                return False
            self.free()
            try:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True,
                                   creationflags=0x08000000, timeout=15)
                else:
                    p.terminate()
                p.wait(timeout=10)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass
            self.proc, self.ours = None, False
            try:
                self._logf.close()
            except Exception:
                pass
            self.log("studio: ComfyUI arrêté")
            return True

    def idle_check(self) -> bool:
        m = float(self.cfg.get("idle_min") or 0)
        if m > 0 and self.ours and self.proc is not None and time.time() - self.last_use > m * 60:
            return self.stop()
        return False

    # génération
    def workflow(self, prompt: str, seed: int, w: int, h: int, steps: int, batch: int = 1,
                 model: str = "") -> Dict[str, Any]:
        m = MODELS.get(model or self.cfg.get("model") or "sd_turbo", MODELS["sd_turbo"])
        lo, hi = m["steps"]
        steps = max(lo, min(hi, int(steps)))
        return {
            "1": {"class_type": "UNETLoader", "inputs": {"unet_name": m["unet"], "weight_dtype": "default"}},
            "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": m["clip"], "type": "stable_diffusion"}},
            "3": {"class_type": "VAELoader", "inputs": {"vae_name": m["vae"]}},
            "4": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}},
            "5": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["2", 0]}},
            "6": {"class_type": "EmptyLatentImage", "inputs": {"width": int(w), "height": int(h), "batch_size": int(batch)}},
            "7": {"class_type": "SDTurboScheduler", "inputs": {"model": ["1", 0], "steps": steps, "denoise": 1.0}},
            "8": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": m["sampler"]}},
            "9": {"class_type": "SamplerCustom", "inputs": {
                "model": ["1", 0], "add_noise": True, "noise_seed": int(seed) & 0xFFFFFFFFFFFF, "cfg": m["cfg"],
                "positive": ["4", 0], "negative": ["5", 0], "sampler": ["8", 0], "sigmas": ["7", 0],
                "latent_image": ["6", 0]}},
            # v41.4 : décodage par tuiles — pic de VRAM bien plus bas (8 Go partagés avec le modèle de jeu)
            "10": ({"class_type": "VAEDecodeTiled", "inputs": {"samples": ["9", 0], "vae": ["3", 0], "tile_size": 320,
                                                                "overlap": 64, "temporal_size": 64, "temporal_overlap": 8}}
                   if self.cfg.get("vae_tiled", True) else
                   {"class_type": "VAEDecode", "inputs": {"samples": ["9", 0], "vae": ["3", 0]}}),
            "11": {"class_type": "PreviewImage", "inputs": {"images": ["10", 0]}},
        }

    def run(self, wf: Dict[str, Any], cancel: Optional[threading.Event] = None,
            on_status: Callable[[str], None] = lambda s: None, timeout: float = 300.0) -> Tuple[List[bytes], Dict[str, Any]]:
        self.last_use = time.time()
        r = self._req("/prompt", {"prompt": wf, "client_id": self.client_id}, timeout=15)
        pid = (r or {}).get("prompt_id")
        if not pid:
            raise EngineError(f"ComfyUI a refusé le travail : {str(r)[:300]}")
        t0 = time.time()
        said = ""
        while True:
            if cancel is not None and cancel.is_set():
                self.interrupt()
                try:
                    self._req("/queue", {"delete": [pid]}, timeout=3)
                except Exception:
                    pass
                raise EngineError("annulé")
            if time.time() - t0 > timeout:
                self.interrupt()
                raise EngineError("délai dépassé")
            try:
                h = self._req(f"/history/{pid}", timeout=5) or {}
            except Exception:
                h = {}
            item = h.get(pid)
            if item:
                stt = item.get("status") or {}
                if stt.get("status_str") == "error":
                    msg = ""
                    for ev, d in stt.get("messages", []):
                        if ev == "execution_error":
                            msg = f"{d.get('node_type')}: {d.get('exception_message', '')}".strip()
                    raise EngineError("erreur ComfyUI — " + (msg or "voir comfyui.log")[:400])
                if stt.get("completed") or item.get("outputs"):
                    break
            else:
                try:
                    q = self._req("/queue", timeout=3) or {}
                    s = "🎨 génération…" if any(x[1] == pid for x in q.get("queue_running", [])) else "⏳ en file…"
                    if s == "🎨 génération…" and not said:
                        said = s  # déjà annoncé par l'appelant
                except Exception:
                    s = "🎨 génération…"
                if s != said:
                    on_status(s)
                    said = s
            time.sleep(0.15)
        imgs: List[bytes] = []
        for node in (item.get("outputs") or {}).values():
            for im in node.get("images", []) or []:
                q = urllib.parse.urlencode({"filename": im.get("filename", ""), "subfolder": im.get("subfolder", ""),
                                            "type": im.get("type", "temp")})
                imgs.append(self._req("/view?" + q, timeout=20, raw=True))
        ts = {ev: d.get("timestamp") for ev, d in (item.get("status") or {}).get("messages", []) if isinstance(d, dict)}
        info = {"prompt_id": pid, "wall_s": time.time() - t0}
        try:
            info["exec_s"] = (ts["execution_success"] - ts["execution_start"]) / 1000.0
        except Exception:
            pass
        self.last_use = time.time()
        if not imgs:
            raise EngineError("aucune image renvoyée")
        return imgs, info


import urllib.parse  # noqa: E402  (après la classe pour garder l'import groupé lisible)


# ─────────────────────────────────────────────────────── Ollama (VRAM) ──
class Ollama:
    def __init__(self, base: str = "http://127.0.0.1:11434", log: Callable[[str], None] = lambda m: None):
        self.base, self.log = base.rstrip("/"), log

    def _req(self, path: str, data: Any = None, timeout: float = 10.0):
        body = None if data is None else json.dumps(data).encode("utf-8")
        rq = urllib.request.Request(self.base + path, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(rq, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8") or "{}")

    def loaded(self) -> List[Tuple[str, int]]:
        try:
            return [(m.get("name") or m.get("model"), int(m.get("size_vram") or 0))
                    for m in self._req("/api/ps", timeout=3).get("models", [])]
        except Exception:
            return []

    def unload_all(self) -> List[str]:
        out = []
        for name, vram in self.loaded():
            if vram > 0:
                try:
                    self._req("/api/generate", {"model": name, "keep_alive": 0}, timeout=20)
                    out.append(name)
                except Exception as e:
                    self.log(f"studio: déchargement {name}: {e}")
        if out:  # attendre que la mémoire soit vraiment rendue
            t0 = time.time()
            while time.time() - t0 < 10 and any(v > 0 for _, v in self.loaded()):
                time.sleep(0.25)
        return out

    def enhance(self, model: str, idea: str, style_hint: str = "", timeout: float = 60.0,
                keep_alive: Any = None, num_ctx: int = 0) -> str:
        """Idée en français → courte description visuelle en anglais pour le moteur d'images."""
        sys_p = ("You write prompts for an image generator. Translate the user's idea (often in French) into ONE "
                 "English description of what is visible: subject, setting, lighting, mood, composition. "
                 "Comma-separated phrases, 15 to 45 words, no sentences about the image itself, no quotes, "
                 "no brand names, no names of real people, no text or letters in the image. Do NOT name an art style, "
                 "medium or camera (it is added separately). Output only the prompt.")
        user = f"Idea: {idea.strip()}" + (f"\nMood hint: {style_hint}" if style_hint else "")
        data = {"model": model, "system": sys_p, "prompt": user, "stream": False,
                "options": {"temperature": 0.4, "num_predict": 110}}
        if num_ctx:  # même contexte que Padawan : sinon Ollama recharge le modèle (≈ 25 s mesurées)
            data["options"]["num_ctx"] = int(num_ctx)
        if keep_alive is not None:
            data["keep_alive"] = keep_alive
        r = self._req("/api/generate", data, timeout=timeout)
        out = (r.get("response") or "").strip()
        out = re.sub(r"(?is)^.*?prompt\s*:\s*", "", out) if re.match(r"(?is)^.{0,40}prompt\s*:", out) else out
        out = out.strip().strip("\"'`").split("\n\n")[0].replace("\n", ", ")
        return sanitize_prompt(out)


    def scene_brief(self, model: str, scene: str, prev: str = "", hero: str = "", lieu: str = "",
                    timeout: float = 45.0, num_ctx: int = 0, keep_alive: Any = "30m", action: str = "") -> Dict[str, Any]:
        """v41.3 : le modèle de JEU lit la scène (FR) et répond en JSON : la scène a-t-elle vraiment changé ?
        + prompt visuel anglais (lieu, personnages, action, heure, ambiance, éléments clés) + fiche du héros."""
        sys_p = (
            "You are the art director of a French text adventure game. You read the NEW SCENE and answer ONLY a JSON "
            "object with these keys:\n"
            '"change": true if the picture must change compared with PREVIOUS PICTURE: a new location, a fight starts, '
            "an important new character appears, or a major event happens; false for talk, small actions or the "
            "same place.\n"
            '"kind": one of "lieu", "combat", "personnage", "evenement", "aucun".\n'
            '"place": the location in 2 to 6 English words.\n'
            '"time": time of day and light in 1 to 4 English words.\n'
            '"prompt": ONE English image description of what is visible now, 20 to 40 words, comma-separated phrases, '
            "most important first: location, characters (describe the player character with HERO when visible), "
            "action, time of day, lighting, mood, key objects. No names, no brands, no text or letters, "
            "no art style words, never game statistics (HP, caps, SPECIAL, hunger, thirst, levels, hull, fuel, oxygen, "
            "energy, credits, skill, stamina, luck, gold, provisions).\n"
            '"hero": the player character appearance in 8 to 20 English words (sex, age, hair, clothes, gear). '
            "Keep HERO unchanged unless the scene clearly changes it; if HERO is unknown, deduce it from the story.\n"
            '"closeup": true when the picture should be a close-up of an object.')
        if action:  # v41.4 : une image par action — fidèle à ce qui vient d'arriver
            sys_p += ("\nPLAYER ACTION is what the player just did (French). The prompt must show the RESULT of that "
                      "action right now, in this scene. If the player examines, reads, opens, searches, hacks or uses an "
                      "object (terminal, console, chest, safe, locker, door, note, map, weapon, body, machine...), describe "
                      "a CLOSE-UP of that object filling the frame, with its visible details, and set closeup to true. "
                      "Describe ONLY what the NEW SCENE text shows now: never reuse objects or places "
                      "from earlier pictures that the NEW SCENE does not mention.")
        user = ((f"PLAYER ACTION: {action.strip()[:300]}\n" if action else "")
                + ("" if action else f"PREVIOUS PICTURE: {prev or 'none, this is the first picture'}\n")
                + f"HERO: {hero or 'unknown'}\n"
                + (f"LOCATION FIELD: {lieu}\n" if lieu else "")
                + f"NEW SCENE:\n{scene.strip()[:1500]}")
        data: Dict[str, Any] = {"model": model, "system": sys_p, "prompt": user, "stream": False, "format": "json",
                                "options": {"temperature": 0.2, "num_predict": 260}}
        if num_ctx:  # même contexte que le jeu : pas de rechargement du modèle
            data["options"]["num_ctx"] = int(num_ctx)
        if keep_alive is not None:  # même durée que Padawan (sinon Ollama la ramène à 5 min)
            data["keep_alive"] = keep_alive
        t0 = time.time()
        r = self._req("/api/generate", data, timeout=timeout)
        d = _json_obj(r.get("response") or "")
        ch = d.get("change")
        if isinstance(ch, str):
            ch = ch.strip().lower() in ("true", "yes", "oui", "1")
        kind = fold(str(d.get("kind") or "")).strip()
        kind = kind if kind in BRIEF_KINDS else ("aucun" if not ch else "evenement")
        cu = d.get("closeup")
        if isinstance(cu, str):
            cu = cu.strip().lower() in ("true", "yes", "oui", "1")
        out = {"change": bool(ch), "kind": kind, "closeup": bool(cu),
               "place": sanitize_prompt(str(d.get("place") or ""))[:80],
               "time": sanitize_prompt(str(d.get("time") or ""))[:40],
               "prompt": sanitize_prompt(str(d.get("prompt") or "").replace("\n", ", "))[:420],
               "hero": sanitize_prompt(str(d.get("hero") or ""))[:160],
               "secs": round(time.time() - t0, 1)}
        if not out["prompt"]:
            raise ValueError("résumé de scène vide")
        return out


# ─────────────────────────────────────────────── image → ANSI (jeux) ──
def prep_for_ansi(im, ansi_style: str):
    """Même préparation que la banque des jeux : contraste auto, couleurs franches, médian sans tramage."""
    from PIL import ImageOps, ImageEnhance, ImageFilter
    if ansi_style == "pipboy":  # vert monochrome : égaliser + accentuer, sinon tout se fond en 40 lignes
        g = ImageOps.equalize(ImageOps.autocontrast(im.convert("L"), cutoff=2))
        return g.filter(ImageFilter.UnsharpMask(4, 120, 2)).convert("RGB")
    im = ImageOps.autocontrast(im.convert("RGB"), cutoff=1)
    if ansi_style == "dos16":
        im = ImageEnhance.Color(im).enhance(1.4)
    if ansi_style == "noir":
        im = ImageEnhance.Brightness(im).enhance(1.15)
    im = ImageEnhance.Contrast(im).enhance(1.12)
    return im.filter(ImageFilter.MedianFilter(5))


def crop_to(im, ratio: float):
    w, h = im.size
    if w / h > ratio:
        nw = int(h * ratio)
        return im.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
    nh = int(w / ratio)
    return im.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))


def to_ansi(im, style: str, cols: int, rows: int = 0, title: str = "", game: bool = False):
    if _ANSI is None:
        return None
    if game:  # SD-Turbo griffonne parfois un faux texte en bas de l'image : on le coupe
        im = im.crop((0, 0, im.width, int(im.height * 0.93)))
    if rows:  # format exact (jeux : 72×20 comme la banque)
        im = crop_to(im, cols / (rows * 2.0) if style in _ANSI.HALF_STYLES else cols / float(rows))
    src = prep_for_ansi(im, style) if game else im
    return _ANSI.convert(src, width=cols, style=style, dither=not game and style not in ("noir",), title=title)


# ──────────────────────────────────────────────────────── galerie ──
class Gallery:
    def __init__(self, folder: str, max_items: int = 400):
        self.folder = folder
        self.path = os.path.join(folder, "historique.json")
        self.max_items = max_items
        self.items: List[Dict[str, Any]] = []
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                d = json.load(f)
            self.items = [x for x in d if isinstance(x, dict) and x.get("file")]
        except Exception:
            self.items = []

    def add(self, png: bytes, meta: Dict[str, Any]) -> Dict[str, Any]:
        os.makedirs(self.folder, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        base = f"{stamp}_{meta.get('style', '')}_{int(meta.get('seed', 0)) % 1000000:06d}"
        fn = base + ".png"
        n = 1
        while os.path.exists(os.path.join(self.folder, fn)):
            n += 1
            fn = f"{base}_{n}.png"
        with open(os.path.join(self.folder, fn), "wb") as f:
            f.write(png)
        it = dict(meta, file=fn, made=time.strftime("%Y-%m-%d %H:%M:%S"))
        self.items.append(it)
        self.items = self.items[-self.max_items:]
        self.save()
        return it

    def save(self) -> None:
        save_json(self.path, self.items)

    def file(self, it: Dict[str, Any]) -> str:
        return os.path.join(self.folder, it["file"])

    def remove(self, it: Dict[str, Any]) -> None:
        try:
            os.remove(self.file(it))
        except OSError:
            pass
        self.items = [x for x in self.items if x is not it and x.get("file") != it.get("file")]
        self.save()


# ─────────────────────────────────────────────────────────── service ──
class Studio:
    """Le cœur sans interface : réglages, moteur, Ollama, galerie, cache des jeux. Utilisable depuis un thread."""

    def __init__(self, private_dir: str, ollama_base: str = "http://127.0.0.1:11434",
                 log: Callable[[str], None] = lambda m: None):
        self.private_dir = private_dir
        self.folder = os.path.join(private_dir, "studio")
        self.cfg_path = os.path.join(private_dir, "studio.json")
        self.cache_dir = os.path.join(self.folder, "cache")
        self.log = log
        self.cfg = load_cfg(self.cfg_path)
        self.engine = Engine(self.cfg, self.folder, log)
        self.ollama = Ollama(ollama_base, log)
        self.gallery = Gallery(self.folder, int(self.cfg.get("history_max") or 400))
        self.gen_lock = threading.Lock()
        self.timings: List[Dict[str, Any]] = []
        self.num_ctx: Callable[[], int] = lambda: 0  # l'hôte branche son num_ctx (évite un rechargement Ollama)

    def save_cfg(self) -> None:
        try:
            save_json(self.cfg_path, {k: self.cfg.get(k, v) for k, v in DEFAULTS.items()})
        except Exception as e:
            self.log(f"studio cfg: {e}")

    def need_unload(self, mode: str = "") -> bool:
        mode = mode or self.cfg.get("vram") or "auto"
        if mode == "jamais":
            return False
        loaded = [n for n, v in self.ollama.loaded() if v > 0]
        if not loaded:
            return False
        if mode == "toujours":
            return True
        need = 3_400_000_000  # SD-Turbo fp16 ≈ 2,6 Go + calculs à 512-768 px
        d = self.engine.alive() or {}
        try:
            dev = d["devices"][0]
            total, free = int(dev.get("vram_total") or 0), int(dev.get("vram_free") or 0)
        except Exception:
            total, free = 0, -1
        held = sum(v for _, v in self.ollama.loaded())
        est = (total or 8_589_934_592) - held - 700_000_000  # bureau Windows ≈ 0,7 Go
        self.log(f"studio: VRAM libre {free / 1e9:.2f} Go (ComfyUI), estimée {est / 1e9:.2f} Go, Ollama {held / 1e9:.2f} Go")
        return free < 0 or min(free, est) < need

    def generate(self, prompt: str, *, seed: int = -1, size: str = "", steps: int = 0, batch: int = 1,
                 cancel: Optional[threading.Event] = None, status: Callable[[str], None] = lambda s: None,
                 timeout: float = 300.0, free_after: bool = False, vram: str = "",
                 start_cancel: bool = True) -> Tuple[List[Any], Dict[str, Any]]:
        """→ ([images PIL], infos). Libère Ollama si besoin, démarre le moteur si besoin. Bloquant."""
        from PIL import Image
        with self.gen_lock:
            t0 = time.time()
            info: Dict[str, Any] = {}
            if not self.engine.ready_to_run():
                raise EngineError("moteur d'images " + ("non installé" if not self.engine.installed()
                                                         else "sans modèle : " + ", ".join(self.engine.missing_models())))
            if not self.engine.alive():
                status("🚀 démarrage du moteur d'images…")
                self.engine.start(cancel=cancel if start_cancel else None)  # v41.4 : une image périmée n'arrête pas le démarrage
                info["start_s"] = round(self.engine.started_s, 1)
            if self.need_unload(vram):
                status("⏳ libère la carte graphique…")
                t1 = time.time()
                info["unloaded"] = self.ollama.unload_all()
                info["unload_s"] = round(time.time() - t1, 2)
            _, _, w, h = size_info(size or self.cfg.get("size"))
            if seed is None or int(seed) < 0:
                seed = random.randint(0, 2 ** 31 - 1)
            wf = self.engine.workflow(prompt, int(seed), w, h, steps or int(self.cfg.get("steps") or 2), batch)
            status("🎨 génération…")
            raw, ri = self.engine.run(wf, cancel=cancel, on_status=status, timeout=timeout)
            info.update(ri)
            if free_after:
                t2 = time.time()
                self.engine.free()
                info["free_s"] = round(time.time() - t2, 2)
            imgs = [Image.open(io.BytesIO(b)).convert("RGB") for b in raw]
            info.update(seed=int(seed), w=w, h=h, total_s=round(time.time() - t0, 2), png=raw)
            self.timings.append({k: v for k, v in info.items() if k != "png"})
            self.timings = self.timings[-50:]
            return imgs, info

    # cache des jeux
    def cache_key(self, fam: str, key: str, lieu: str, extra: str = "") -> str:
        base = "|".join([fam, key, re.sub(r"[^a-z0-9]+", " ", fold(lieu)).strip()[:60], extra, MODELS_KEY])
        return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]

    def cache_get(self, h: str):
        p = os.path.join(self.cache_dir, h + ".json")
        if _ANSI is None or not os.path.isfile(p):
            return None
        try:
            with open(p, "r", encoding="utf-8") as f:
                d = json.load(f).get("art")
            return _ANSI.art_from_dict(d) if d else None
        except Exception:
            return None

    def cache_put(self, h: str, art, png: bytes, meta: Dict[str, Any]) -> None:
        os.makedirs(self.cache_dir, exist_ok=True)
        with open(os.path.join(self.cache_dir, h + ".png"), "wb") as f:
            f.write(png)
        save_json(os.path.join(self.cache_dir, h + ".json"),
                  {"art": _ANSI.art_to_dict(art) if art is not None else None, "meta": meta})

    def cache_png(self, h: str) -> str:
        p = os.path.join(self.cache_dir, h + ".png")
        return p if h and os.path.isfile(p) else ""

    def game_brief(self, model: str, scene: str, prev: str = "", hero: str = "", lieu: str = "",
                   action: str = "") -> Dict[str, Any]:
        """v41.3 : résumé visuel de la scène par le modèle de jeu (lève une exception si indisponible)."""
        if not self.cfg.get("game_enhance", True):
            raise ValueError("résumé désactivé (game_enhance)")
        return self.ollama.scene_brief(model, scene, prev, hero, lieu, timeout=45, num_ctx=self.num_ctx(),
                                       action=action)

    def vram_report(self) -> Dict[str, Any]:
        """v41.3 : mémoire vidéo (nvidia-smi) + part tenue par Ollama, en Mo — pour la surveiller pendant les jeux."""
        rep: Dict[str, Any] = {}
        try:
            exe = shutil.which("nvidia-smi")
            if exe:
                out = subprocess.run([exe, "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
                                     capture_output=True, text=True, timeout=5,
                                     creationflags=0x08000000 if os.name == "nt" else 0).stdout
                u, t = [int(float(x)) for x in out.strip().splitlines()[0].split(",")[:2]]
                rep.update(used_mb=u, total_mb=t, free_mb=t - u)
        except Exception:
            pass
        rep["ollama_mb"] = int(sum(v for _, v in self.ollama.loaded()) / 1048576)
        return rep

    def game_prompt(self, fam: str, scene_text: str, key: str, lieu: str, model: str = "") -> Tuple[str, str]:
        """Prompt anglais pour une scène de jeu : le modèle de texte résume la scène (s'il répond), sinon modèle-type."""
        sid = GAME_STYLE.get(fam, ("libre", "truecolor"))[0]
        subj = ""
        how = "modèle"
        if model and self.cfg.get("game_enhance", True) and scene_text.strip():
            try:
                subj = self.ollama.enhance(model, scene_text[:900], "", timeout=40,
                                           num_ctx=self.num_ctx(), keep_alive="30m")
                how = "résumé par " + model
            except Exception as e:
                self.log(f"studio jeu prompt: {e}")
        if not subj:
            subj = GAME_SUBJECT.get(fam, {}).get(key) or GAME_SUBJECT.get(fam, {}).get("_") or "mysterious scene"
            if lieu:
                subj += ", " + fold(lieu)[:60]
        return full_prompt(subj, sid), how


MODELS_KEY = "sdturbo1"

GAME_SUBJECT: Dict[str, Dict[str, str]] = {
    "fallout": {"titre": "ruined city skyline at dawn, giant radio tower, lone wanderer silhouette",
                "abri": "huge round steel bunker door in a rock cave, flickering lights",
                "ruines": "ruined downtown street, collapsed buildings, abandoned cars", "foret": "irradiated forest, dead trees, giant moose",
                "lac": "hydroelectric dam over a glowing lake", "route": "empty cracked highway through wasteland",
                "mutant": "hulking green mutant brute with a club", "goule": "rotting ghoul creature in a dark tunnel",
                "marche": "wasteland bazaar, merchants stalls, scrap metal", "robot": "rusty 1950s style robot",
                "campement": "survivors camp with campfire at night", "metro": "flooded subway station, emergency lights",
                "combat": "wasteland firefight, laser beams, explosions", "cabane": "abandoned sugar shack in snowy woods",
                "_": "post-apocalyptic wasteland scene"},
    "galaxie": {"espace": "small battered retro spaceship near a colorful ringed planet, starfield",
                "vaisseau": "cramped retro spaceship cockpit with blinking consoles", "planete": "alien planet surface, two moons",
                "starbase": "huge rotating space station with docking bays", "alien": "friendly bizarre alien merchant",
                "combat": "space battle, laser beams between small spaceships", "hyperespace": "spaceship jumping to hyperspace, light streaks",
                "asteroides": "spaceship flying through an asteroid belt", "_": "retro spaceship in deep space near a planet"},
    "legende": {"titre": "fantasy kingdom at golden sunrise, castle on a hill, dragon in the sky",
                "auberge": "cozy medieval inn interior, roaring fireplace, adventurers at wooden tables",
                "village": "medieval village square, half-timbered houses, market stalls",
                "chateau": "majestic medieval castle with banners, drawbridge", "foret": "enchanted elven forest, giant oaks, glowing fireflies",
                "montagne": "dwarven mountain fortress carved in rock, snowy peaks", "caverne": "torchlit underground cavern, glittering crystals",
                "desert": "amber desert dunes, camel caravan, ancient ruins", "mer": "wooden sailing ship on a stormy sea, giant sea serpent",
                "ile": "misty tropical island with pirate cove", "temple": "ancient greek marble temple, oracle, golden light",
                "lac": "misty lake at dawn, hand holding a sword from the water", "nord": "frozen viking fjord, longships, northern lights",
                "neige": "flying canoe over snowy quebec forest at night, full moon",
                "combat": "knight fighting a fierce monster, sword clash, sparks", "dragon": "huge red dragon breathing fire over a castle",
                "monstre": "fearsome troll under a stone bridge", "magie": "wizard casting a glowing spell, magic runes",
                "route": "medieval road through green hills, rider on horseback", "_": "medieval fantasy adventure scene"},
    "donjon": {"titre": "fantasy castle on a hill at night, full moon", "porte": "massive dungeon gate with torches",
               "couloir": "stone dungeon corridor lit by torches", "coffre": "treasure chest in a dark crypt",
               "monstre": "red dragon in a cavern", "squelette": "skeleton warrior with sword",
               "taverne": "medieval tavern interior, warm fire", "escalier": "spiral stone staircase going down",
               "tresor": "pile of gold coins and gems", "_": "fantasy dungeon scene"},
    "polar": {"titre": "1940s city street at night in the rain, neon sign", "ruelle": "dark alley in the rain, fire escape",
              "bureau": "private detective office, venetian blinds, desk lamp", "cadavre": "crime scene, body outline, police lights",
              "jazz": "smoky jazz club, saxophone player on stage", "voiture": "1940s car in the rain at night, headlights",
              "police": "police interrogation room, single lamp", "port": "foggy harbour docks at night, ship",
              "_": "film noir city scene"},
}


# ───────────────────────────────────────────── installation (sur demande) ──
def sha256_file(path: str, chunk: int = 4 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def download(url: str, dest: str, size: int, sha: str, progress: Callable[[str, float], None],
             cancel: Optional[threading.Event] = None, label: str = "") -> None:
    """Téléchargement reprenable + vérification taille et SHA-256 (fichier refusé s'il ne correspond pas)."""
    if os.path.isfile(dest) and os.path.getsize(dest) == size and sha256_file(dest) == sha:
        progress(f"✔ {label} déjà là (vérifié)", 1.0)
        return
    part = dest + ".part"
    have = os.path.getsize(part) if os.path.isfile(part) else 0
    rq = urllib.request.Request(url, headers={"User-Agent": "Padawan-Studio/" + VERSION,
                                              **({"Range": f"bytes={have}-"} if have else {})})
    with urllib.request.urlopen(rq, timeout=60) as r, open(part, "ab" if have and r.status == 206 else "wb") as f:
        done = have if r.status == 206 else 0
        t0, last = time.time(), 0.0
        while True:
            if cancel is not None and cancel.is_set():
                raise EngineError("installation annulée")
            b = r.read(1 << 20)
            if not b:
                break
            f.write(b)
            done += len(b)
            if time.time() - last > 0.4:
                last = time.time()
                mbps = (done - have) / max(0.1, time.time() - t0) / 1e6
                progress(f"⬇ {label} {done / 1e9:.2f} / {size / 1e9:.2f} Go · {mbps:.0f} Mo/s", done / size)
    if os.path.getsize(part) != size:
        raise EngineError(f"{label} : taille inattendue ({os.path.getsize(part)} au lieu de {size})")
    progress(f"🔎 vérification SHA-256 de {label}…", 1.0)
    if sha256_file(part) != sha:
        os.remove(part)
        raise EngineError(f"{label} : empreinte SHA-256 incorrecte — fichier supprimé")
    os.replace(part, dest)


PAD_TE = r'''
import sys, os
from safetensors.torch import load_file, save_file
src = sys.argv[1]
sd = load_file(src)
n = sum(1 for k in sd if k.endswith(".mlp.fc1.weight") and "encoder.layers." in k)
if n == 23:
    for k in [k for k in sd if k.startswith("text_model.encoder.layers.22.")]:
        sd[k.replace("layers.22.", "layers.23.")] = sd[k].clone()
    save_file(sd, src + ".tmp", metadata={"padawan": "SD2 text encoder: layer 23 = copy of 22 (unused, penultimate)"})
    del sd
    os.replace(src + ".tmp", src)
    print("padded")
else:
    print("ok", n)
'''


def pad_text_encoder(engine: Engine, name: str) -> str:
    """Le text encoder SD2 « diffusers » n'a que 23 couches ; ComfyUI en attend 24 (la 24e n'est pas utilisée :
    SD2 lit l'avant-dernière). On recopie la 23e pour que le chargeur l'accepte."""
    path = os.path.join(engine.models_dir("text_encoders"), name)
    r = subprocess.run([engine.python, "-s", "-c", PAD_TE, path], capture_output=True, text=True, env=clean_env(),
                       creationflags=0x08000000 if os.name == "nt" else 0, timeout=600)
    if r.returncode:
        raise EngineError("préparation du text encoder : " + (r.stderr or r.stdout)[-300:])
    return r.stdout.strip()


def install_engine(engine: Engine, progress: Callable[[str, float], None],
                   cancel: Optional[threading.Event] = None, model: str = "sd_turbo") -> None:
    """Installe ComfyUI portable (officiel) + le modèle choisi (Hugging Face officiel). Appelé SEULEMENT après
    confirmation de l'utilisateur. Ne touche ni au Python du système ni au démarrage de Windows."""
    root = engine.root
    parent = os.path.dirname(root)
    dl = os.path.join(parent, "_downloads")
    os.makedirs(dl, exist_ok=True)
    free = shutil.disk_usage(parent).free
    if free < 12e9:
        raise EngineError(f"pas assez d'espace sur {parent} ({free / 1e9:.1f} Go libres, il en faut ≈ 12)")
    if not engine.installed():
        z = os.path.join(parent, "_tools", "7zr.exe")
        os.makedirs(os.path.dirname(z), exist_ok=True)
        download(SEVENZR[0], z, SEVENZR[1], SEVENZR[2], progress, cancel, "7zr.exe (7-Zip officiel)")
        pkg = os.path.join(dl, os.path.basename(ENGINE_PKG[0]))
        download(ENGINE_PKG[0], pkg, ENGINE_PKG[1], ENGINE_PKG[2], progress, cancel, "ComfyUI portable NVIDIA")
        progress("📦 extraction de ComfyUI (≈ 3-4 min)…", 0.0)
        r = subprocess.run([z, "x", pkg, "-o" + parent, "-y", "-bso0", "-bsp0"], capture_output=True, text=True,
                           creationflags=0x08000000 if os.name == "nt" else 0)
        if r.returncode:
            raise EngineError("extraction : " + (r.stderr or r.stdout)[-300:])
        ex = os.path.join(parent, "ComfyUI_windows_portable")
        if os.path.isdir(ex) and not os.path.exists(root):
            os.replace(ex, root)
        if not engine.installed():
            raise EngineError("ComfyUI introuvable après extraction")
    m = MODELS[model]
    for sub, name, url, size, sha in m["files"]:
        dest = os.path.join(engine.models_dir(sub), name)
        if os.path.isfile(dest):
            continue
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        tmp = os.path.join(dl, name)
        download(url, tmp, size, sha, progress, cancel, name)
        os.replace(tmp, dest)
    progress("🔧 préparation du modèle…", 1.0)
    pad_text_encoder(engine, m["clip"])
    progress("✔ moteur d'images installé", 1.0)


# ───────────────────────────────────────────────────────────── interface ──
if tk is not None:
    import queue as _queue

    class _Tip:
        def __init__(self, w, text: str, C: Dict[str, str]):
            self.w, self.text, self.C, self.tw, self.job = w, text, C, None, None
            w.bind("<Enter>", lambda e: self._sched(), add="+")
            w.bind("<Leave>", lambda e: self._hide(), add="+")
            w.bind("<ButtonPress>", lambda e: self._hide(), add="+")

        def _sched(self):
            self._hide()
            self.job = self.w.after(550, self._show)

        def _show(self):
            if self.tw or not self.text:
                return
            try:
                x, y = self.w.winfo_rootx() + 10, self.w.winfo_rooty() + self.w.winfo_height() + 4
                self.tw = tk.Toplevel(self.w)
                self.tw.wm_overrideredirect(True)
                self.tw.geometry(f"+{x}+{y}")
                tk.Label(self.tw, text=self.text, bg=self.C["card2"], fg=self.C["fg"], justify="left",
                         font=("Segoe UI", 9), padx=8, pady=5).pack()
            except Exception:
                self.tw = None

        def _hide(self):
            if self.job:
                try:
                    self.w.after_cancel(self.job)
                except Exception:
                    pass
                self.job = None
            if self.tw:
                try:
                    self.tw.destroy()
                except Exception:
                    pass
                self.tw = None

    class StudioView(tk.Frame):
        """🎨 Studio : écran plein qui se pose par-dessus Padawan (comme l'Atelier)."""

        def __init__(self, master, C: Dict[str, str], core: Studio, hooks: Optional[Dict[str, Any]] = None):
            super().__init__(master, bg=C["bg"])
            self.C, self.core, self.cfg = C, core, core.cfg
            self.hooks = hooks or {}
            self.q: "_queue.Queue[Callable[[], None]]" = _queue.Queue()
            self.cancel_ev: Optional[threading.Event] = None
            self.busy = False
            self.cur_img = None          # PIL
            self.cur_item: Optional[Dict[str, Any]] = None
            self.cur_art = None
            self._ph: List[Any] = []
            self._thumbs: List[Any] = []
            self.timings: List[Dict[str, Any]] = []
            self._build()
            self._poll()
            self.after(800, self._tick)

        # outils
        def _b(self, p, text, cmd, tip="", kind="norm", **kw):
            C = self.C
            bg, fg = {"gold": (C["gold"], "#1a1408"), "ok": (C["ok"], "#06231a"), "bad": (C["card2"], C["bad"]),
                      "norm": (C["card"], C["fg"])}[kind]
            b = tk.Button(p, text=text, command=cmd, bg=bg, fg=fg, activebackground=C["card2"], activeforeground=C["fg"],
                          relief="flat", cursor="hand2", font=("Segoe UI", kw.pop("size", 9), "bold"),
                          padx=kw.pop("padx", 8), pady=kw.pop("pady", 3), bd=0, **kw)
            if tip:
                _Tip(b, tip, C)
            return b

        def _l(self, p, text, fg=None, size=9, bold=False, **kw):
            return tk.Label(p, text=text, bg=kw.pop("bg", p.cget("bg")), fg=fg or self.C["fg"],
                            font=("Segoe UI", size, "bold" if bold else "normal"), **kw)

        def ui(self, fn: Callable[[], None]) -> None:  # depuis un thread
            self.q.put(fn)

        def _poll(self):
            try:
                while True:
                    fn = self.q.get_nowait()
                    try:
                        fn()
                    except Exception as e:
                        self.core.log(f"studio ui: {e}")
            except _queue.Empty:
                pass
            try:
                self.after(60, self._poll)
            except Exception:
                pass

        def _tick(self):
            try:
                if self.winfo_ismapped():
                    self._paint_engine()
            except Exception:
                pass
            self.after(4000, self._tick)

        # construction
        def _build(self):
            C = self.C
            hdr = tk.Frame(self, bg=C["panel"])
            hdr.pack(side="top", fill="x")
            self._l(hdr, "🎨 STUDIO D'IMAGES", C["gold"], 13, True).pack(side="left", padx=(12, 10), pady=6)
            self.b_close = self._b(hdr, "✕ Fermer  Échap", self.leave, "Retour à Padawan (le moteur s'arrête seul au repos)")
            self.b_close.pack(side="right", padx=(4, 10), pady=5)
            self.b_set = self._b(hdr, "⚙ Moteur", self.settings, "Dossier, port, arrêt auto, carte graphique, modèle")
            self.b_set.pack(side="right", padx=4)
            self.b_dir = self._b(hdr, "📁 ComfyUI", self.open_engine_dir, "Ouvrir le dossier du moteur ComfyUI")
            self.b_dir.pack(side="right", padx=4)
            self.b_stop = self._b(hdr, "■ Arrêter", self.stop_engine, "Arrêter le moteur (libère la carte graphique et la RAM)", "bad")
            self.b_stop.pack(side="right", padx=4)
            self.b_start = self._b(hdr, "▶ Démarrer", self.start_engine, "Démarrer le moteur maintenant (≈ 20-30 s)", "ok")
            self.b_start.pack(side="right", padx=4)
            # l'état du moteur prend la place qui reste (coupé avant les boutons sur un petit écran)
            self.eng_lbl = self._l(hdr, "moteur : …", C["dim"], 9, anchor="w", width=1)
            self.eng_lbl.pack(side="left", padx=4, fill="x", expand=True)

            body = tk.Frame(self, bg=C["bg"])
            body.pack(fill="both", expand=True)
            left = tk.Frame(body, bg=C["panel"], width=330)
            left.pack(side="left", fill="y", padx=(8, 4), pady=8)
            left.pack_propagate(False)
            self.left = left
            self._l(left, "Ton idée (en français, ou en anglais)", C["dim"], 9, True).pack(anchor="w", padx=10, pady=(10, 2))
            self.idea = tk.Text(left, height=4, wrap="word", bg=C["input"], fg=C["fg"], insertbackground=C["cursor"],
                                relief="flat", font=("Segoe UI", 10), padx=6, pady=4)
            self.idea.pack(fill="x", padx=10)
            self.idea.insert("1.0", "une cabane à sucre abandonnée dans la neige, au crépuscule")
            self.idea.bind("<Control-Return>", lambda e: (self.generate(), "break")[1])
            self.enh_var = tk.BooleanVar(value=bool(self.cfg.get("enhance", True)))
            self.enh_cb = tk.Checkbutton(left, variable=self.enh_var, text="✨ Améliorer en anglais (modèle courant)",
                                         command=self._save_opts, bg=C["panel"], fg=C["fg"], selectcolor=C["card"],
                                         activebackground=C["panel"], activeforeground=C["fg"], font=("Segoe UI", 9))
            self.enh_cb.pack(anchor="w", padx=6, pady=(4, 2))
            _Tip(self.enh_cb, "Le modèle Ollama courant traduit ton idée en une description visuelle anglaise\n"
                              "(le moteur comprend mal le français). Décoché : ton texte part tel quel.", C)

            self._l(left, "Style (un clic)", C["dim"], 9, True).pack(anchor="w", padx=10, pady=(6, 2))
            sg = tk.Frame(left, bg=C["panel"])
            sg.pack(fill="x", padx=10)
            self.style_btns: Dict[str, tk.Button] = {}
            for i, (sid, lab, suf, ast) in enumerate(STYLES):
                b = tk.Button(sg, text=lab, relief="flat", cursor="hand2", font=("Segoe UI", 9, "bold"), bd=0, pady=3,
                              command=lambda s_=sid: self.pick_style(s_))
                b.grid(row=i // 2, column=i % 2, sticky="ew", padx=2, pady=2)
                _Tip(b, (suf or "aucun ajout au prompt") + f"\nANSI conseillé : {ast}", C)
                self.style_btns[sid] = b
            sg.columnconfigure(0, weight=1)
            sg.columnconfigure(1, weight=1)

            row = tk.Frame(left, bg=C["panel"])
            row.pack(fill="x", padx=10, pady=(8, 2))
            self._l(row, "Taille", C["dim"]).pack(side="left")
            self.size_var = tk.StringVar(value=size_info(self.cfg.get("size"))[1])
            self.size_cb = ttk.Combobox(row, textvariable=self.size_var, values=[z[1] for z in SIZES], state="readonly", width=18)
            self.size_cb.pack(side="left", padx=4)
            self.size_cb.bind("<<ComboboxSelected>>", lambda e: self._save_opts())
            self._l(row, "Pas", C["dim"]).pack(side="left", padx=(6, 0))
            self.steps_var = tk.IntVar(value=int(self.cfg.get("steps") or 2))
            sp = tk.Spinbox(row, from_=1, to=4, textvariable=self.steps_var, width=2, command=self._save_opts,
                            bg=C["input"], fg=C["fg"], buttonbackground=C["card"], relief="flat")
            sp.pack(side="left", padx=4)
            _Tip(sp, "SD-Turbo : 1 pas = le plus rapide, 2-4 = un peu plus net", C)

            row = tk.Frame(left, bg=C["panel"])
            row.pack(fill="x", padx=10, pady=(4, 2))
            self._l(row, "Graine", C["dim"]).pack(side="left")
            self.seed_var = tk.StringVar(value="" if int(self.cfg.get("seed", -1)) < 0 else str(self.cfg.get("seed")))
            se = tk.Entry(row, textvariable=self.seed_var, width=11, bg=C["input"], fg=C["fg"], relief="flat",
                          insertbackground=C["cursor"])
            se.pack(side="left", padx=4)
            _Tip(se, "Vide = au hasard. Même graine + même prompt = même image.", C)
            self._b(row, "🎲", lambda: self.seed_var.set(str(random.randint(0, 2 ** 31 - 1))), "Nouvelle graine au hasard",
                    padx=4).pack(side="left")
            self.lock_var = tk.BooleanVar(value=bool(self.cfg.get("lock_seed")))
            tk.Checkbutton(row, variable=self.lock_var, text="🔒 garder", command=self._save_opts, bg=C["panel"],
                           fg=C["fg"], selectcolor=C["card"], activebackground=C["panel"], font=("Segoe UI", 9)).pack(side="left")

            self.b_gen = self._b(left, "🎨 Générer   Ctrl+Entrée", self.generate,
                                 "Génère l'image (la première prend ≈ 20-40 s : démarrage + chargement)", "gold", size=11, pady=6)
            self.b_gen.pack(fill="x", padx=10, pady=(10, 3))
            row = tk.Frame(left, bg=C["panel"])
            row.pack(fill="x", padx=10)
            self.b_var = self._b(row, "🔀 Variation", lambda: self.generate(variation=True),
                                 "Même prompt, autre graine")
            self.b_var.pack(side="left", fill="x", expand=True, padx=(0, 2))
            self.b_x4 = self._b(row, "×4", lambda: self.generate(batch=4), "4 variations d'un coup (galerie)")
            self.b_x4.pack(side="left", fill="x", expand=True, padx=2)
            self.b_cancel = self._b(row, "⏹ Annuler", self.cancel, "Arrêter la génération en cours", "bad")
            self.b_cancel.pack(side="left", fill="x", expand=True, padx=(2, 0))

            self._l(left, "Prompt envoyé au moteur", C["dim"], 8, True).pack(anchor="w", padx=10, pady=(8, 0))
            self.prompt_txt = tk.Text(left, height=4, wrap="word", bg=C["card"], fg=C["dim"], relief="flat",
                                      font=("Segoe UI", 8), padx=5, pady=3)
            self.prompt_txt.pack(fill="x", padx=10)
            self.status = self._l(left, "", C["ok"], 9, True, wraplength=300, justify="left", anchor="w")
            self.status.pack(fill="x", padx=10, pady=(6, 2))
            self.pb = ttk.Progressbar(left, mode="indeterminate")
            self.pb.pack(fill="x", padx=10)
            self.tlbl = self._l(left, "", C["dim"], 8, wraplength=300, justify="left", anchor="w")
            self.tlbl.pack(fill="x", padx=10, pady=(3, 6))

            right = tk.Frame(body, bg=C["bg"])
            right.pack(side="left", fill="both", expand=True, padx=(4, 8), pady=8)
            self.right = right
            # galerie en bas
            gal = tk.Frame(right, bg=C["panel"])
            gal.pack(side="bottom", fill="x", pady=(6, 0))
            gh = tk.Frame(gal, bg=C["panel"])
            gh.pack(fill="x")
            self.gal_lbl = self._l(gh, "🖼 Galerie", C["dim"], 9, True)
            self.gal_lbl.pack(side="left", padx=8, pady=(3, 0))
            self._b(gh, "📂 Ouvrir le dossier", self.open_gallery_dir, "C:\\web_private\\Padawan\\studio", size=8).pack(side="right", padx=6, pady=2)
            self.gal_c = tk.Canvas(gal, height=92, bg=C["panel"], highlightthickness=0)
            self.gal_c.pack(fill="x", padx=4)
            self.gal_sb = ttk.Scrollbar(gal, orient="horizontal", command=self.gal_c.xview)
            self.gal_sb.pack(fill="x", padx=4, pady=(0, 3))
            self.gal_c.configure(xscrollcommand=self.gal_sb.set)
            self.gal_c.bind("<MouseWheel>", lambda e: self.gal_c.xview_scroll(-1 if e.delta > 0 else 1, "units"))
            # actions
            act = tk.Frame(right, bg=C["bg"])
            act.pack(side="bottom", fill="x", pady=(6, 0))
            self.acts = []
            for t, fn, tip in (("💾 PNG", self.save_png, "Enregistrer l'image (PNG)"),
                               ("💾 .ans", self.save_ans, "Art ANSI pour terminal / BBS (SAUCE)"),
                               ("💾 .html", self.save_html, "Page HTML avec l'art ANSI en couleurs"),
                               ("📋 ANSI", lambda: self.copy(True), "Copier l'art avec les codes couleur (terminal)"),
                               ("📋 Texte", lambda: self.copy(False), "Copier l'art en texte simple"),
                               ("💻 Atelier", self.to_atelier, "Ouvrir l'image dans 🖼→ANSI de l'Atelier (réglages fins)")):
                b = self._b(act, t, fn, tip)
                b.pack(side="left", padx=(0, 4))
                self.acts.append(b)
            self._l(act, "ANSI", C["dim"]).pack(side="left", padx=(10, 2))
            sty = [("auto", "auto (selon le style)")] + ([(a, b) for a, b in _ANSI.STYLES] if _ANSI else [])
            self._ansi_ids = [a for a, _ in sty]
            self.ansi_var = tk.StringVar(value=dict(sty).get(self.cfg.get("ansi_style") or "auto", sty[0][1]))
            self.ansi_cb = ttk.Combobox(act, textvariable=self.ansi_var, values=[b for _, b in sty], state="readonly", width=24)
            self.ansi_cb.pack(side="left")
            self.ansi_cb.bind("<<ComboboxSelected>>", lambda e: (self._save_opts(), self.render_ansi()))
            self.cols_var = tk.IntVar(value=int(self.cfg.get("ansi_cols") or 80))
            sc = tk.Scale(act, from_=40, to=160, orient="horizontal", variable=self.cols_var, showvalue=True, length=120,
                          bg=C["bg"], fg=C["dim"], troughcolor=C["card"], highlightthickness=0, bd=0,
                          command=lambda v: self._cols_later())
            sc.pack(side="left", padx=6)
            _Tip(sc, "Largeur de l'art ANSI (colonnes)", C)
            # 2 vues côte à côte
            views = tk.Frame(right, bg=C["bg"])
            views.pack(side="top", fill="both", expand=True)
            self.views = views
            self.v_img = tk.Label(views, bg="#000000", bd=0, cursor="hand2")
            self.v_ansi = tk.Label(views, bg="#000000", bd=0, cursor="hand2")
            self.v_img.place(relx=0, rely=0, relwidth=0.5, relheight=1, width=-3)
            self.v_ansi.place(relx=0.5, rely=0, relwidth=0.5, relheight=1, x=3, width=-3)
            self.v_img.bind("<Button-1>", lambda e: self.popup(False))
            self.v_ansi.bind("<Button-1>", lambda e: self.popup(True))
            views.bind("<Configure>", lambda e: self._fit_later())
            # écran « moteur non installé »
            self.inst = tk.Frame(right, bg=C["panel"])
            self._build_install(self.inst)
            self.bind_all_keys()
            self.pick_style(self.cfg.get("style") or "postapo", save=False)
            self.refresh_gallery()
            self._paint_engine()
            self._set_busy(False)

        def _build_install(self, f):
            C = self.C
            self._l(f, "🎨 Le moteur d'images n'est pas installé", C["gold"], 14, True).pack(anchor="w", padx=20, pady=(20, 6))
            m = MODELS["sd_turbo"]
            txt = ("Le Studio dessine en local, sans internet, avec ComfyUI (moteur libre, officiel) et le modèle\n"
                   f"{m['label']}. Rien n'est téléchargé sans ton accord.\n\n"
                   "• À télécharger : ≈ 4,7 Go (ComfyUI portable NVIDIA 2,1 Go + modèle 2,6 Go)\n"
                   "• Sur le disque : ≈ 7 Go dans le dossier ci-dessous (Python intégré : ton Python n'est pas touché)\n"
                   "• Sources : github.com/Comfy-Org/ComfyUI · huggingface.co/stabilityai/sd-turbo · 7-Zip (github.com/ip7z)\n"
                   "  — chaque fichier est vérifié (taille + SHA-256)\n"
                   "• Carte NVIDIA conseillée (≈ 3,5 Go de mémoire graphique libre) ; démarré seulement quand tu génères,\n"
                   "  jamais au démarrage de Windows, écoute sur 127.0.0.1 seulement.\n"
                   "• Modèle SD-Turbo : licence Stability AI Community (usage perso / non commercial).")
            self._l(f, txt, C["fg"], 10, justify="left").pack(anchor="w", padx=20)
            row = tk.Frame(f, bg=C["panel"])
            row.pack(anchor="w", padx=20, pady=12)
            self._l(row, "Dossier :", C["dim"]).pack(side="left")
            self.inst_dir = tk.StringVar(value=self.core.engine.root)
            tk.Entry(row, textvariable=self.inst_dir, width=44, bg=C["input"], fg=C["fg"], relief="flat").pack(side="left", padx=6)
            self.inst_btn = self._b(f, "📥 Installer le moteur…", self.install, "", "gold", size=11, pady=6)
            self.inst_btn.pack(anchor="w", padx=20)
            self.inst_msg = self._l(f, "", C["ok"], 9, True)
            self.inst_msg.pack(anchor="w", padx=20, pady=6)
            self.inst_pb = ttk.Progressbar(f, mode="determinate", maximum=1.0, length=420)
            self.inst_pb.pack(anchor="w", padx=20)

        def bind_all_keys(self):
            self.bind("<Escape>", lambda e: self.leave())
            for w in (self, self.views, self.v_img, self.v_ansi, self.left):
                w.bind("<Escape>", lambda e: self.leave(), add="+")

        # entrée / sortie
        def enter(self, idea: str = ""):
            self.place(x=0, y=0, relwidth=1, relheight=1)
            self.lift()
            if idea:
                self.idea.delete("1.0", "end")
                self.idea.insert("1.0", idea)
            m = (self.hooks.get("current") or (lambda: ""))()
            self.enh_cb.configure(text=f"✨ Améliorer en anglais ({m or 'modèle courant'})")
            self._paint_engine()
            self.idea.focus_set()
            self._fit_later()

        def leave(self):
            if self.busy:
                self.cancel()
            self.place_forget()
            cb = self.hooks.get("leave")
            if cb:
                cb()  # l'hôte rend la carte graphique au modèle de texte
            elif self.core.engine.alive(timeout=0.5) and self.cfg.get("vram") != "jamais":
                threading.Thread(target=self.core.engine.free, daemon=True).start()

        # moteur
        def _paint_engine(self):
            e = self.core.engine
            st = e.status_text()
            col = {"démarré": self.C["ok"], "arrêté": self.C["dim"]}.get(st.split(" ")[0], self.C["gold"])
            extra = ""
            if st.startswith("démarré") and e.ours and float(self.cfg.get("idle_min") or 0) > 0:
                left = float(self.cfg["idle_min"]) * 60 - (time.time() - e.last_use)
                extra = f" · arrêt auto dans {max(0, int(left // 60))} min"
            self.eng_lbl.configure(text=f"moteur ComfyUI : {st} · {MODELS[self.cfg.get('model') or 'sd_turbo']['label']}{extra}",
                                   fg=col)
            ok = e.ready_to_run()
            if ok:
                self.inst.place_forget()
            else:
                self.inst.place(in_=self.right, x=0, y=0, relwidth=1, relheight=1)
                self.inst.lift()
            run = st.startswith("démarré")
            C = self.C
            on1 = not (run or not ok or self.busy)
            on2 = bool(run and e.ours and not self.busy)
            self.b_start.configure(state="normal" if on1 else "disabled", bg=C["ok"] if on1 else C["card"],
                                   disabledforeground=C["skel"] if "skel" in C else C["dim"])
            self.b_stop.configure(state="normal" if on2 else "disabled", bg=C["card2"] if on2 else C["card"],
                                  disabledforeground=C["skel"] if "skel" in C else C["dim"])
            self.b_dir.configure(state="normal" if e.installed() else "disabled")

        def start_engine(self):
            def work():
                try:
                    self.ui(lambda: self._say("🚀 démarrage du moteur…", True))
                    self.core.engine.start()
                    s = self.core.engine.started_s
                    self.ui(lambda: self._say(f"✔ moteur prêt ({s:.0f} s)"))
                except Exception as ex:
                    msg = str(ex)
                    self.ui(lambda: self._say("⚠ " + msg, bad=True))
                finally:
                    self.ui(lambda: (self._set_busy(False), self._paint_engine()))
            self._set_busy(True)
            threading.Thread(target=work, daemon=True).start()

        def stop_engine(self):
            threading.Thread(target=lambda: (self.core.engine.stop(), self.ui(self._paint_engine),
                                             self.ui(lambda: self._say("■ moteur arrêté (carte graphique libérée)"))),
                             daemon=True).start()

        def open_engine_dir(self):
            d = self.core.engine.root
            if os.path.isdir(d):
                os.startfile(d) if os.name == "nt" else None

        def open_gallery_dir(self):
            os.makedirs(self.core.folder, exist_ok=True)
            os.startfile(self.core.folder) if os.name == "nt" else None

        def settings(self):
            C, cfg = self.C, self.cfg
            d = tk.Toplevel(self)
            d.title("⚙ Moteur d'images")
            d.configure(bg=C["bg"])
            d.transient(self.winfo_toplevel())
            e = self.core.engine
            vals: Dict[str, Any] = {}

            def row(lab, key, w=40, tip=""):
                r = tk.Frame(d, bg=C["bg"])
                r.pack(fill="x", padx=14, pady=3)
                tk.Label(r, text=lab, bg=C["bg"], fg=C["dim"], width=22, anchor="w").pack(side="left")
                v = tk.StringVar(value=str(cfg.get(key, "")))
                tk.Entry(r, textvariable=v, width=w, bg=C["input"], fg=C["fg"], relief="flat").pack(side="left")
                if tip:
                    tk.Label(r, text=tip, bg=C["bg"], fg=C["dim"], font=("Segoe UI", 8)).pack(side="left", padx=6)
                vals[key] = v
            tk.Label(d, text="⚙ Moteur d'images (ComfyUI)", bg=C["bg"], fg=C["gold"], font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=14, pady=(12, 6))
            row("Dossier ComfyUI", "engine_dir", 40)
            row("Port (127.0.0.1)", "port", 8)
            row("Arrêt auto (minutes)", "idle_min", 8, "0 = jamais")
            row("Options ComfyUI", "extra_args", 40)
            row("Délai jeu (s)", "game_timeout", 8, "au-delà : image de la banque")
            r = tk.Frame(d, bg=C["bg"])
            r.pack(fill="x", padx=14, pady=3)
            tk.Label(r, text="Carte graphique", bg=C["bg"], fg=C["dim"], width=22, anchor="w").pack(side="left")
            vv = tk.StringVar(value=cfg.get("vram") or "auto")
            for k, lab in (("auto", "libérer Ollama si besoin"), ("toujours", "toujours libérer"), ("jamais", "partager")):
                tk.Radiobutton(r, text=lab, value=k, variable=vv, bg=C["bg"], fg=C["fg"], selectcolor=C["card"],
                               activebackground=C["bg"]).pack(side="left")
            info = (f"Installé : {'oui' if e.installed() else 'non'} · modèle : "
                    f"{'OK' if not e.missing_models() else 'manquant ' + ', '.join(e.missing_models())}\n"
                    f"Journal : {os.path.join(self.core.folder, 'comfyui.log')}\n"
                    f"Réglages : {self.core.cfg_path}\n"
                    "« partager » garde le modèle de texte en mémoire graphique (images ≈ 16 s au lieu de ≈ 3 s,\n"
                    "mais pas de rechargement ≈ 27 s du modèle de texte ensuite). Les jeux partagent toujours.")
            tk.Label(d, text=info, bg=C["bg"], fg=C["dim"], justify="left", font=("Segoe UI", 8)).pack(anchor="w", padx=14, pady=6)

            def ok():
                for k, v in vals.items():
                    x = v.get().strip()
                    if isinstance(DEFAULTS[k], int):
                        try:
                            x = int(float(x))
                        except ValueError:
                            x = DEFAULTS[k]
                    cfg[k] = x
                cfg["vram"] = vv.get()
                self.core.save_cfg()
                d.destroy()
                self._paint_engine()
            bb = tk.Frame(d, bg=C["bg"])
            bb.pack(fill="x", padx=14, pady=(4, 12))
            self._b(bb, "✔ Enregistrer", ok, kind="gold").pack(side="right")
            self._b(bb, "Annuler", d.destroy).pack(side="right", padx=6)
            d.bind("<Escape>", lambda e_: d.destroy())

        def install(self):
            e = self.core.engine
            dest = os.path.normpath(self.inst_dir.get().strip() or DEFAULTS["engine_dir"])
            if not messagebox.askyesno(
                    "📥 Installer le moteur d'images",
                    f"Télécharger ≈ 4,7 Go et installer dans\n{dest}\n\n"
                    "ComfyUI portable (GitHub Comfy-Org) + SD-Turbo fp16 (Hugging Face stabilityai)\n"
                    "+ 7zr.exe (7-Zip, GitHub ip7z) pour décompresser.\nChaque fichier est vérifié (SHA-256).\n\nOn y va ?",
                    parent=self):
                return
            self.cfg["engine_dir"] = dest
            self.core.save_cfg()
            ev = threading.Event()
            self.cancel_ev = ev

            def prog(msg, frac):
                self.ui(lambda: (self.inst_msg.configure(text=msg), self.inst_pb.configure(value=max(0.0, min(1.0, frac)))))

            def work():
                try:
                    install_engine(e, prog, ev)
                    self.ui(lambda: self._say("✔ moteur installé — prêt à générer"))
                except Exception as ex:
                    m = str(ex)
                    self.ui(lambda: self.inst_msg.configure(text="⚠ " + m, fg=self.C["bad"]))
                finally:
                    self.ui(lambda: (self.inst_btn.configure(state="normal"), self._paint_engine()))
            self.inst_btn.configure(state="disabled")
            threading.Thread(target=work, daemon=True).start()

        # options
        def pick_style(self, sid: str, save: bool = True):
            if sid not in STYLE_IDS:
                sid = "postapo"
            self.style = sid
            for k, b in self.style_btns.items():
                on = k == sid
                b.configure(bg=self.C["gold"] if on else self.C["card"], fg="#1a1408" if on else self.C["fg"])
            if save:
                self._save_opts()
                if self.cur_img is not None and (self.cfg.get("ansi_style") or "auto") == "auto":
                    self.render_ansi()

        def _size_id(self) -> str:
            lab = self.size_var.get()
            return next((z[0] for z in SIZES if z[1] == lab), "paysage")

        def _ansi_id(self) -> str:
            lab = self.ansi_var.get()
            sty = [("auto", "auto (selon le style)")] + ([(a, b) for a, b in _ANSI.STYLES] if _ANSI else [])
            return next((a for a, b in sty if b == lab), "auto")

        def _save_opts(self):
            c = self.cfg
            c["enhance"] = bool(self.enh_var.get())
            c["style"] = getattr(self, "style", "postapo")
            c["size"] = self._size_id()
            try:
                c["steps"] = max(1, min(4, int(self.steps_var.get())))
            except Exception:
                c["steps"] = 2
            c["lock_seed"] = bool(self.lock_var.get())
            c["ansi_style"] = self._ansi_id()
            c["ansi_cols"] = int(self.cols_var.get())
            self.core.save_cfg()

        # génération
        def _say(self, msg: str, busy: bool = False, bad: bool = False):
            self.status.configure(text=msg, fg=self.C["bad"] if bad else (self.C["gold"] if busy else self.C["ok"]))

        def _set_busy(self, on: bool):
            self.busy = on
            for b in (self.b_gen, self.b_var, self.b_x4):
                b.configure(state="disabled" if on else "normal")
            self.b_cancel.configure(state="normal" if on else "disabled")
            if on:
                self.pb.start(12)
            else:
                self.pb.stop()
            try:
                self._paint_engine()
            except Exception:
                pass

        def cancel(self):
            if self.cancel_ev is not None:
                self.cancel_ev.set()
            self._say("⏹ annulation…", True)

        def generate(self, variation: bool = False, batch: int = 1, done: Optional[Callable[[bool], None]] = None):
            if self.busy:
                return
            if not self.core.engine.ready_to_run():
                self._paint_engine()
                return
            self._save_opts()
            idea = self.idea.get("1.0", "end").strip()
            last = self.cur_item or {}
            if variation and last.get("prompt"):
                idea = last.get("idea", idea)
            if not idea:
                self._say("Écris d'abord une idée 🙂", bad=True)
                return
            seed = -1
            raw = self.seed_var.get().strip()
            if raw.isdigit() and not variation:
                seed = int(raw)
            if variation:
                seed = random.randint(0, 2 ** 31 - 1)
            sid, size, steps = self.style, self._size_id(), int(self.cfg.get("steps") or 2)
            enhance = bool(self.enh_var.get())
            model = (self.hooks.get("current") or (lambda: ""))()
            ready = (self.hooks.get("ready") or (lambda: True))()
            ev = threading.Event()
            self.cancel_ev = ev
            self._set_busy(True)
            reuse = last.get("prompt") if variation and last.get("idea") == idea and last.get("style") == sid else ""
            t_all = time.time()

            def work():
                ok = False
                tim: Dict[str, Any] = {}
                try:
                    prompt, how = "", "tel quel"
                    if reuse:
                        prompt, how = reuse, "réutilisé"
                    elif enhance and model and ready:
                        self.ui(lambda: self._say(f"✨ {model} traduit ton idée…", True))
                        t = time.time()
                        try:
                            subj = self.core.ollama.enhance(model, idea, "",
                                                            num_ctx=self.core.num_ctx())
                            prompt, how = full_prompt(subj, sid), "amélioré par " + model
                        except Exception as ex:
                            self.core.log(f"studio enhance: {ex}")
                        tim["enhance_s"] = round(time.time() - t, 1)
                    if not prompt:
                        prompt = full_prompt(idea, sid)
                    self.ui(lambda: (self.prompt_txt.delete("1.0", "end"), self.prompt_txt.insert("1.0", prompt)))
                    if ev.is_set():
                        raise EngineError("annulé")
                    imgs, info = self.core.generate(prompt, seed=seed, size=size, steps=steps, batch=batch, cancel=ev,
                                                    status=lambda s: self.ui(lambda: self._say(s, True)))
                    tim.update({k: v for k, v in info.items() if k in ("start_s", "unload_s", "exec_s", "total_s", "unloaded")})
                    tim["all_s"] = round(time.time() - t_all, 1)
                    items = []
                    for i, (im, png) in enumerate(zip(imgs, info["png"])):
                        meta = {"idea": idea, "prompt": prompt, "how": how, "style": sid, "seed": info["seed"],
                                "batch_i": i, "size": size, "w": info["w"], "h": info["h"], "steps": steps,
                                "model": self.cfg.get("model"), "time_s": tim.get("all_s")}
                        items.append(self.core.gallery.add(png, meta))
                    self.timings.append(tim)
                    ok = True

                    def show():
                        self.show_item(items[0], imgs[0])
                        if not self.lock_var.get():
                            self.seed_var.set("")
                        self.refresh_gallery()
                        self._say(f"✔ {len(items)} image{'s' if len(items) > 1 else ''} · graine {info['seed']} · {how}")
                        bits = [f"⏱ total {tim['all_s']:.1f} s"]
                        if "enhance_s" in tim:
                            bits.append(f"traduction {tim['enhance_s']:.1f} s")
                        if "start_s" in tim:
                            bits.append(f"démarrage moteur {tim['start_s']:.0f} s")
                        if tim.get("unloaded"):
                            bits.append(f"carte libérée ({', '.join(tim['unloaded'])}) {tim.get('unload_s', 0):.1f} s")
                        if "exec_s" in tim:
                            bits.append(f"dessin {tim['exec_s']:.1f} s")
                        self.tlbl.configure(text=" · ".join(bits))
                    self.ui(show)
                except Exception as ex:
                    m = str(ex)
                    self.ui(lambda: self._say(("⏹ " if "annul" in m else "⚠ ") + m, bad="annul" not in m))
                finally:
                    self.ui(lambda: self._set_busy(False))
                    if done:
                        self.ui(lambda: done(ok))
            threading.Thread(target=work, daemon=True).start()

        # affichage
        def show_item(self, it: Dict[str, Any], im=None):
            from PIL import Image
            if im is None:
                try:
                    im = Image.open(self.core.gallery.file(it)).convert("RGB")
                except Exception as e:
                    self._say(f"⚠ image introuvable ({e})", bad=True)
                    return
            self.cur_item, self.cur_img = it, im
            self.prompt_txt.delete("1.0", "end")
            self.prompt_txt.insert("1.0", it.get("prompt", ""))
            self.render_ansi()

        def _cols_later(self):
            if getattr(self, "_cj", None):
                self.after_cancel(self._cj)
            self._cj = self.after(250, lambda: (self._save_opts(), self.render_ansi()))

        def render_ansi(self):
            if self.cur_img is None or _ANSI is None:
                return
            st = self._ansi_id()
            if st == "auto":
                st = style_info((self.cur_item or {}).get("style") or self.style)[3]
            t = time.time()
            self.cur_art = to_ansi(self.cur_img, st, int(self.cols_var.get()), title=(self.cur_item or {}).get("idea", "")[:30],
                                   game=st in ("pipboy", "noir"))
            self.ansi_ms = (time.time() - t) * 1000
            self._fit()

        def _fit_later(self):
            if getattr(self, "_fj", None):
                self.after_cancel(self._fj)
            self._fj = self.after(80, self._fit)

        def _fit(self):
            if self.cur_img is None:
                self.v_img.configure(image="", text="L'image apparaîtra ici", fg=self.C["dim"], font=("Segoe UI", 11))
                self.v_ansi.configure(image="", text="… et sa version ANSI ici", fg=self.C["dim"], font=("Segoe UI", 11))
                return
            from PIL import Image, ImageTk
            W = max(100, self.v_img.winfo_width() or 400)
            H = max(100, self.v_img.winfo_height() or 300)
            im = self.cur_img.copy()
            im.thumbnail((W, H), Image.Resampling.LANCZOS)
            p1 = ImageTk.PhotoImage(im, master=self)
            self.v_img.configure(image=p1, text="")
            p2 = None
            if self.cur_art is not None:
                a = self.cur_art
                cw = max(1, min(12, W // max(1, a.cols), H // max(1, 2 * a.nrows)))
                ai = _ANSI.render_image(a, cw).convert("RGB")
                if ai.width > W or ai.height > H:
                    ai.thumbnail((W, H), Image.Resampling.NEAREST)
                p2 = ImageTk.PhotoImage(ai, master=self)
                self.v_ansi.configure(image=p2, text="")
            self._ph = [p1, p2]

        def popup(self, ansi: bool):
            if self.cur_img is None:
                return
            from PIL import Image, ImageTk
            top = tk.Toplevel(self)
            top.configure(bg="#000000")
            top.title("🎨 " + ((self.cur_item or {}).get("idea", "")[:60]))
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            if ansi and self.cur_art is not None:
                a = self.cur_art
                cw = max(2, min(16, int(sw * 0.9) // a.cols, int(sh * 0.82) // (2 * a.nrows)))
                im = _ANSI.render_image(a, cw).convert("RGB")
            else:
                im = self.cur_img.copy()
                k = min(sw * 0.9 / im.width, sh * 0.82 / im.height, 2.0)
                im = im.resize((int(im.width * k), int(im.height * k)), Image.Resampling.LANCZOS)
            ph = ImageTk.PhotoImage(im, master=top)
            top._ph = ph  # type: ignore[attr-defined]
            lb = tk.Label(top, image=ph, bg="#000000", bd=0)
            lb.pack()
            for w in (top, lb):
                w.bind("<Button-1>", lambda e: top.destroy())
            top.bind("<Escape>", lambda e: top.destroy())
            top.focus_force()

        # galerie
        def refresh_gallery(self):
            from PIL import Image, ImageTk
            c = self.gal_c
            c.delete("all")
            self._thumbs = []
            items = list(reversed(self.core.gallery.items[-60:]))
            self.gal_lbl.configure(text=f"🖼 Galerie · {len(self.core.gallery.items)} image(s) · clic = rouvrir · clic droit = menu")
            x = 4
            for it in items:
                p = self.core.gallery.file(it)
                try:
                    im = Image.open(p)
                    im.thumbnail((140, 84))
                    ph = ImageTk.PhotoImage(im, master=c)
                except Exception:
                    continue
                tg = "t" + str(len(self._thumbs))
                c.create_image(x, 4, image=ph, anchor="nw", tags=(tg,))
                c.tag_bind(tg, "<Button-1>", lambda e, i=it: self.show_item(i))
                c.tag_bind(tg, "<Button-3>", lambda e, i=it: self._gal_menu(e, i))
                self._thumbs.append(ph)
                x += ph.width() + 6
            c.configure(scrollregion=(0, 0, x, 90))

        def _gal_menu(self, e, it):
            m = tk.Menu(self, tearoff=0)
            m.add_command(label="🖼 Rouvrir", command=lambda: self.show_item(it))
            m.add_command(label="✏ Réutiliser l'idée et le style",
                          command=lambda: (self.idea.delete("1.0", "end"), self.idea.insert("1.0", it.get("idea", "")),
                                           self.pick_style(it.get("style") or self.style)))
            m.add_command(label="🔁 Même graine", command=lambda: self.seed_var.set(str(it.get("seed", ""))))
            m.add_separator()
            m.add_command(label="🗑 Supprimer de la galerie", command=lambda: (self.core.gallery.remove(it), self.refresh_gallery()))
            m.tk_popup(e.x_root, e.y_root)

        # sorties
        def _need(self) -> bool:
            if self.cur_img is None:
                self._say("Génère ou rouvre d'abord une image.", bad=True)
                return False
            return True

        def _base_name(self) -> str:
            it = self.cur_item or {}
            return os.path.splitext(it.get("file") or "image")[0]

        def _ask(self, ext: str, kinds) -> str:
            return filedialog.asksaveasfilename(parent=self, defaultextension=ext, initialfile=self._base_name() + ext,
                                                initialdir=self.core.folder, filetypes=kinds)

        def save_png(self, path: str = ""):
            if not self._need():
                return ""
            path = path or self._ask(".png", [("PNG", "*.png")])
            if path:
                self.cur_img.save(path)
                self._say(f"💾 {os.path.basename(path)}")
            return path

        def save_ans(self, path: str = ""):
            if not self._need() or self.cur_art is None:
                return ""
            path = path or self._ask(".ans", [("Art ANSI", "*.ans")])
            if path:
                with open(path, "wb") as f:
                    f.write(self.cur_art.to_ans_bytes(title=(self.cur_item or {}).get("idea", "")[:35]))
                self._say(f"💾 {os.path.basename(path)}")
            return path

        def save_html(self, path: str = ""):
            if not self._need() or self.cur_art is None:
                return ""
            path = path or self._ask(".html", [("Page HTML", "*.html")])
            if path:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(self.cur_art.to_html(title=(self.cur_item or {}).get("idea", "")[:60]))
                self._say(f"💾 {os.path.basename(path)}")
            return path

        def copy(self, ansi: bool):
            if not self._need() or self.cur_art is None:
                return
            t = self.cur_art.to_ansi("vt") if ansi else self.cur_art.to_text()
            self.clipboard_clear()
            self.clipboard_append(t)
            self._say("📋 art " + ("ANSI (codes couleur)" if ansi else "texte") + " copié")

        def to_atelier(self):
            if not self._need():
                return
            fn = self.hooks.get("atelier")
            it = self.cur_item or {}
            p = self.core.gallery.file(it) if it.get("file") else ""
            if not p or not os.path.isfile(p):
                p = os.path.join(self.core.folder, "_atelier.png")
                self.cur_img.save(p)
            if fn:
                self.place_forget()
                fn(p)

        def shutdown(self):
            try:
                if self.cancel_ev is not None:
                    self.cancel_ev.set()
            except Exception:
                pass
