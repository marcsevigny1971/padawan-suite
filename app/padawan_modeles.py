# -*- coding: utf-8 -*-
"""padawan_modeles.py — 🧠 Gestionnaire de modèles Ollama pour Padawan (v39.6).

- Diagnostic machine (GPU/VRAM via nvidia-smi → registre/WMI, RAM, CPU, disque du dossier modèles)
- Mes modèles (/api/tags) : activer, effacer (/api/delete)
- Catalogue intégré (+ mise à jour facultative depuis ollama.com, tolérante aux pannes)
- Installation en un clic (/api/pull en flux, progression, vitesse, annulation, contrôle d'espace disque)
- Banc d'essai : même question à 2-3 modèles côte à côte (temps, tokens/s) → corrige la pastille
Aucune dépendance obligatoire hors requests (déjà utilisé par Padawan).
"""
from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    import requests  # type: ignore
except Exception:  # pragma: no cover
    requests = None  # type: ignore

VERSION = "1.2"  # v39.8 : estimation calibrée sur des mesures réelles (gemma2:9b déborde d'une carte 8 Go)  # v39.7 : recommandés cliquables (⬇ Installer / ⭐ Activer), bouton par ligne au catalogue
OLLAMA = "http://127.0.0.1:11434"
NOWIN = 0x08000000 if os.name == "nt" else 0
GB = 1024 ** 3

TAGS = {
    "🎮": "jeux de rôle / histoires",
    "🔍": "recherche / culture générale",
    "🇫🇷": "bon en français",
    "🐍": "code",
    "⚡": "léger et rapide",
}

# Tailles = téléchargement Q4 par défaut sur ollama.com (approximatif, mis à jour via 🔄).
CATALOGUE: List[Dict[str, Any]] = [
    {"name": "smollm2:135m", "size": 0.27, "params": 0.135, "tags": "⚡",
     "desc": "Minuscule (135 M) : tests seulement, réponses très simples, anglais surtout."},
    {"name": "qwen2.5:0.5b", "size": 0.40, "params": 0.5, "tags": "⚡",
     "desc": "Très petit Qwen : utile pour tester ou résumer court. Français basique."},
    {"name": "llama3.2:1b", "size": 1.3, "params": 1.2, "tags": "⚡",
     "desc": "Petit Llama de Meta, très rapide. Correct pour des tâches simples."},
    {"name": "gemma2:2b", "size": 1.6, "params": 2.6, "tags": "⚡🇫🇷",
     "desc": "Petit Gemma de Google, étonnamment bon en français pour sa taille."},
    {"name": "qwen2.5:3b", "size": 1.9, "params": 3.1, "tags": "⚡🇫🇷🔍",
     "desc": "Qwen 3B : rapide, multilingue, bon pour résumer et répondre vite."},
    {"name": "llama3.2:3b", "size": 2.0, "params": 3.2, "tags": "⚡🔍",
     "desc": "Llama 3.2 3B : léger et polyvalent, bon suivi des consignes."},
    {"name": "phi3.5", "size": 2.2, "params": 3.8, "tags": "⚡🐍",
     "desc": "Phi-3.5 de Microsoft : raisonnement/maths/code compact. Français moyen."},
    {"name": "gemma3:4b", "size": 3.3, "params": 4.3, "tags": "⚡🇫🇷🔍",
     "desc": "Gemma 3 4B : récent, très multilingue, bon compromis vitesse/qualité."},
    {"name": "mistral", "size": 4.1, "params": 7.2, "tags": "🇫🇷🎮",
     "desc": "Mistral 7B (français d'origine) : naturel en français, bon conteur."},
    {"name": "dolphin-mistral", "size": 4.1, "params": 7.2, "tags": "🎮🇫🇷",
     "desc": "Mistral 7B « Dolphin » non censuré : jeux de rôle et histoires sans filtre."},
    {"name": "qwen2.5:7b", "size": 4.7, "params": 7.6, "tags": "🇫🇷🔍🐍",
     "desc": "Qwen 2.5 7B : très solide en recherche/synthèse, bon français, bon en code."},
    {"name": "huihui_ai/qwen2.5-abliterate:7b", "size": 4.7, "params": 7.6, "tags": "🎮🔍",
     "desc": "Qwen 2.5 7B « abliterated » (sans refus) : polyvalent, non censuré."},
    {"name": "qwen2.5-coder:7b", "size": 4.7, "params": 7.6, "tags": "🐍",
     "desc": "Qwen 2.5 Coder 7B : spécialiste du code (Python, scripts, débogage)."},
    {"name": "dolphin3:8b", "size": 4.9, "params": 8.0, "tags": "🎮🔍",
     "desc": "Dolphin 3 (Llama 3.1 8B) non censuré : le modèle par défaut de Padawan."},
    {"name": "llama3.1:8b", "size": 4.9, "params": 8.0, "tags": "🔍",
     "desc": "Llama 3.1 8B de Meta : généraliste fiable, long contexte."},
    {"name": "qwen3:8b", "size": 5.2, "params": 8.2, "tags": "🔍🇫🇷🐍",
     "desc": "Qwen 3 8B : récent, mode « réflexion », très bon en raisonnement."},
    {"name": "deepseek-r1:8b", "size": 5.2, "params": 8.0, "tags": "🔍",
     "desc": "DeepSeek-R1 8B : raisonne à voix haute (plus lent mais plus réfléchi)."},
    {"name": "gemma2:9b", "size": 5.4, "params": 9.2, "tags": "🇫🇷🔍",
     "desc": "Gemma 2 9B : excellent français écrit, style soigné."},
    {"name": "mistral-nemo", "size": 7.1, "params": 12.2, "tags": "🇫🇷🎮🔍",
     "desc": "Mistral NeMo 12B : très bon français et récits, à la limite d'une carte 8 Go."},
    {"name": "gemma3:12b", "size": 8.1, "params": 12.2, "tags": "🇫🇷🔍",
     "desc": "Gemma 3 12B : qualité nettement supérieure, mais déborde d'une carte 8 Go."},
    {"name": "qwen2.5:14b", "size": 9.0, "params": 14.8, "tags": "🔍🇫🇷🐍",
     "desc": "Qwen 2.5 14B : plus intelligent, mais déborde en RAM sur 8 Go de VRAM (lent)."},
    {"name": "qwen2.5-coder:14b", "size": 9.0, "params": 14.8, "tags": "🐍",
     "desc": "Qwen 2.5 Coder 14B : meilleur en code, lent si la VRAM est < 12 Go."},
    {"name": "gemma2:27b", "size": 16.0, "params": 27.2, "tags": "🇫🇷🔍",
     "desc": "Gemma 2 27B : très bon, il faut ~20 Go de VRAM ou beaucoup de RAM."},
    {"name": "qwen2.5:32b", "size": 20.0, "params": 32.8, "tags": "🔍🐍",
     "desc": "Qwen 2.5 32B : haut de gamme, carte 24 Go recommandée."},
    {"name": "llama3.3:70b", "size": 43.0, "params": 70.6, "tags": "🔍",
     "desc": "Llama 3.3 70B : niveau « gros modèle », il faut 48 Go de VRAM."},
    {"name": "dolphin-llama3:70b", "size": 40.0, "params": 70.6, "tags": "🎮",
     "desc": "Dolphin Llama 3 70B non censuré : énorme, inutilisable sans grosse machine."},
]

DOT_UI = {"🟢": ("● fluide", "ok"), "🟡": ("● lent", "gold"), "🔴": ("● trop gros", "bad"), "⚪": ("● ?", "dim")}

DOT_TXT = {"🟢": "fluide (tient dans la carte graphique)",
           "🟡": "possible mais lent (déborde en RAM/CPU)",
           "🔴": "trop gros pour ce PC"}


# ───────────────────────── utilitaires ─────────────────────────
def _run(cmd: List[str], timeout: float = 8.0) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           creationflags=NOWIN, encoding="utf-8", errors="replace")
        return r.stdout or ""
    except Exception:
        return ""


def fmt_gb(x: Optional[float]) -> str:
    if x is None:
        return "?"
    if x < 1:
        return f"{x * 1024:.0f} Mo"
    return f"{x:.1f} Go"


def base_name(name: str) -> str:
    n = (name or "").strip().lower()
    if ":" not in n:
        n += ":latest"
    return n


def same_model(a: str, b: str) -> bool:
    return base_name(a) == base_name(b)


# ───────────────────────── diagnostic ─────────────────────────
def _nvidia_smi() -> Optional[str]:
    p = shutil.which("nvidia-smi")
    if p:
        return p
    for c in (r"C:\Windows\System32\nvidia-smi.exe",
              r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe"):
        if os.path.isfile(c):
            return c
    return None


_IGPU = re.compile(r"intel.*(hd|uhd|iris)|microsoft basic|radeon\(tm\) graphics|vega \d+ graphics|"
                   r"remote display|virtual|parsec|meta|citrix", re.I)


def diag_gpus() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    smi = _nvidia_smi()
    if smi:
        txt = _run([smi, "--query-gpu=name,memory.total,memory.free,driver_version",
                    "--format=csv,noheader,nounits"])
        for line in txt.splitlines():
            parts = [x.strip() for x in line.split(",")]
            if len(parts) >= 3:
                try:
                    out.append({"name": parts[0], "vram": float(parts[1]) / 1024,
                                "free": float(parts[2]) / 1024,
                                "driver": parts[3] if len(parts) > 3 else "",
                                "dedicated": True, "src": "nvidia-smi"})
                except ValueError:
                    pass
    if os.name == "nt":
        seen = {g["name"].lower() for g in out}
        for g in _gpus_registry() or _gpus_wmi():
            if g["name"].lower() in seen:
                continue
            seen.add(g["name"].lower())
            g["dedicated"] = bool(g.get("vram")) and g["vram"] >= 1.5 and not _IGPU.search(g["name"])
            out.append(g)
    return out


def _gpus_registry() -> List[Dict[str, Any]]:
    """qwMemorySize du registre = VRAM exacte (> 4 Go, contrairement à WMI AdapterRAM)."""
    res: List[Dict[str, Any]] = []
    try:
        import winreg  # type: ignore
        key = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key) as k:
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(k, i)
                except OSError:
                    break
                i += 1
                if not sub.isdigit():
                    continue
                try:
                    with winreg.OpenKey(k, sub) as s:
                        name = str(winreg.QueryValueEx(s, "DriverDesc")[0])
                        mem = None
                        for v in ("HardwareInformation.qwMemorySize", "HardwareInformation.MemorySize"):
                            try:
                                raw = winreg.QueryValueEx(s, v)[0]
                                mem = int.from_bytes(raw, "little") if isinstance(raw, bytes) else int(raw)
                                break
                            except OSError:
                                continue
                        res.append({"name": name, "vram": (mem or 0) / GB, "free": None,
                                    "driver": "", "src": "registre"})
                except OSError:
                    continue
    except Exception:
        return []
    return res


def _gpus_wmi() -> List[Dict[str, Any]]:
    txt = _run(["powershell", "-NoProfile", "-Command",
                "Get-CimInstance Win32_VideoController | Select-Object Name,AdapterRAM | ConvertTo-Json"], 15)
    try:
        data = json.loads(txt or "[]")
        if isinstance(data, dict):
            data = [data]
        return [{"name": str(d.get("Name") or "?"), "vram": (d.get("AdapterRAM") or 0) / GB,
                 "free": None, "driver": "", "src": "WMI"} for d in data]
    except Exception:
        return []


def diag_ram() -> Tuple[Optional[float], Optional[float]]:
    if os.name == "nt":
        try:
            import ctypes

            class MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            m = MS()
            m.dwLength = ctypes.sizeof(MS)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
                return m.ullTotalPhys / GB, m.ullAvailPhys / GB
        except Exception:
            pass
        return None, None
    try:
        info = {}
        with open("/proc/meminfo") as f:
            for line in f:
                k, v = line.split(":", 1)
                info[k] = int(v.split()[0]) * 1024
        return info["MemTotal"] / GB, info.get("MemAvailable", info.get("MemFree", 0)) / GB
    except Exception:
        return None, None


def diag_cpu() -> Dict[str, Any]:
    d: Dict[str, Any] = {"name": "", "threads": os.cpu_count() or 0, "cores": None, "avx2": None}
    if os.name == "nt":
        try:
            import winreg  # type: ignore
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as k:
                d["name"] = " ".join(str(winreg.QueryValueEx(k, "ProcessorNameString")[0]).split())
        except Exception:
            pass
        try:
            import ctypes
            d["avx2"] = bool(ctypes.windll.kernel32.IsProcessorFeaturePresent(40))
        except Exception:
            pass
        txt = _run(["powershell", "-NoProfile", "-Command",
                    "(Get-CimInstance Win32_Processor | Measure-Object NumberOfCores -Sum).Sum"], 15)
        try:
            d["cores"] = int(txt.strip())
        except ValueError:
            pass
    else:
        try:
            s = open("/proc/cpuinfo").read()
            m = re.search(r"model name\s*:\s*(.+)", s)
            d["name"] = m.group(1).strip() if m else ""
            d["avx2"] = " avx2" in s
        except Exception:
            pass
    return d


def models_dir() -> str:
    p = os.environ.get("OLLAMA_MODELS", "").strip()
    if not p and os.name == "nt":
        try:
            import winreg  # type: ignore
            for hive, key in ((winreg.HKEY_CURRENT_USER, r"Environment"),
                              (winreg.HKEY_LOCAL_MACHINE,
                               r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment")):
                try:
                    with winreg.OpenKey(hive, key) as k:
                        p = str(winreg.QueryValueEx(k, "OLLAMA_MODELS")[0]).strip()
                        if p:
                            break
                except OSError:
                    continue
        except Exception:
            pass
    return os.path.expandvars(p) if p else os.path.join(os.path.expanduser("~"), ".ollama", "models")


def diag_disk(path: str) -> Optional[float]:
    p = path
    while p and not os.path.exists(p):
        np_ = os.path.dirname(p)
        if np_ == p:
            break
        p = np_
    try:
        return shutil.disk_usage(p or os.path.expanduser("~")).free / GB
    except Exception:
        return None


def ollama_version(base: str = OLLAMA) -> str:
    try:
        return requests.get(f"{base}/api/version", timeout=4).json().get("version", "") if requests else ""
    except Exception:
        return ""


def diagnose(base: str = OLLAMA) -> Dict[str, Any]:
    gpus = diag_gpus()
    tot, free = diag_ram()
    mdir = models_dir()
    return {"gpus": gpus, "ram": tot, "ram_free": free, "cpu": diag_cpu(),
            "models_dir": mdir, "disk_free": diag_disk(mdir), "ollama": ollama_version(base),
            "when": datetime.now().strftime("%Y-%m-%d %H:%M")}


def main_gpu(d: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    ded = [g for g in d.get("gpus") or [] if g.get("dedicated")]
    return max(ded, key=lambda g: g.get("vram") or 0) if ded else None


# ───────────────────────── compatibilité ─────────────────────────
def _overhead(size: float) -> float:
    """Contexte 8k (KV cache) + tampons. Mesuré sur le PC de Marc (v39.8) : dolphin3:8b 4,6 Go → 5,8 Go chargé,
    gemma2:9b 5,4 Go → 6,7 Go chargé ⇒ ≈ +25 % +0,3 Go."""
    return size * 0.25 + 0.3


DESKTOP_VRAM = 1.2  # Go de VRAM déjà pris par Windows / l'écran / le navigateur (mesuré : 1,2 à 1,5 Go)


def _need(size: float) -> float:
    return size + _overhead(size)


GB_PER_B_Q4 = 0.6  # ≈ Go de fichier par milliard de paramètres en Q4_K_M


def budget(d: Dict[str, Any]) -> Dict[str, Any]:
    g = main_gpu(d)
    vram = (g or {}).get("vram") or 0.0
    ram = d.get("ram") or 0.0
    ram_use = ram * 0.7  # part de RAM raisonnablement utilisable par Ollama
    if vram:
        eff = max(0.0, vram - DESKTOP_VRAM)
        fluid = (eff - 0.3) / 1.25
        slow = (eff + ram_use - 0.3) / 1.25
    else:  # CPU seulement : petits modèles fluides, le reste lent
        fluid = min(2.5, ram * 0.35)
        slow = ram_use / 1.15
    return {"vram": vram, "ram": ram, "gpu": (g or {}).get("name", ""),
            "fluid_gb": max(0.0, fluid), "slow_gb": max(0.0, slow),
            "fluid_b": max(0.0, fluid / GB_PER_B_Q4), "slow_b": max(0.0, slow / GB_PER_B_Q4)}


def _round_b(b: float) -> str:
    for s in (70, 32, 27, 14, 12, 9, 8, 7, 4, 3, 2, 1):
        if b >= s * 0.97:
            return f"{s} B"
    return "1 B" if b >= 0.5 else "0,5 B"


def compat(size: Optional[float], d: Dict[str, Any], tps: Optional[float] = None) -> Tuple[str, str]:
    """→ (pastille, raison). tps = tokens/s mesuré au banc d'essai (prioritaire)."""
    if tps is not None and tps > 0:
        if tps >= 12:
            return "🟢", f"mesuré {tps:.0f} tok/s : fluide"
        if tps >= 3:
            return "🟡", f"mesuré {tps:.1f} tok/s : utilisable mais lent"
        return "🔴", f"mesuré {tps:.1f} tok/s : trop lent en pratique"
    if not size:
        return "⚪", "taille inconnue"
    b = budget(d)
    need = _need(size)
    if b["vram"]:
        eff = max(0.0, b["vram"] - DESKTOP_VRAM)
        if need <= eff:
            return "🟢", f"≈{need:.1f} Go nécessaires ≤ {eff:.1f} Go de VRAM utilisable"
        if need <= eff + b["ram"] * 0.7:
            return "🟡", f"≈{need:.1f} Go > {eff:.1f} Go de VRAM utilisable : déborde en RAM (lent)"
        return "🔴", f"≈{need:.1f} Go : trop pour {b['vram']:.0f} Go VRAM + {b['ram']:.0f} Go RAM"
    if need <= b["fluid_gb"] * 1.15:
        return "🟢", "petit modèle : correct même sans carte graphique"
    if need <= b["ram"] * 0.6:
        return "🟡", "pas de carte graphique dédiée : calcul CPU (lent)"
    return "🔴", "trop gros pour la RAM de ce PC"


def summary_text(d: Dict[str, Any]) -> str:
    b = budget(d)
    cpu = d.get("cpu") or {}
    parts = []
    if b["gpu"]:
        parts.append(f"{b['gpu']} {b['vram']:.0f} Go")
    else:
        parts.append("pas de carte graphique dédiée")
    if d.get("ram"):
        parts.append(f"{d['ram']:.0f} Go de RAM")
    if cpu.get("name"):
        parts.append(re.sub(r"\(R\)|\(TM\)|CPU|@.*", "", cpu["name"]).strip())
    s = "Ton PC : " + ", ".join(parts)
    s += f" → tu peux viser jusqu'à ~{_round_b(b['fluid_b'])} en Q4 (fluide)"
    if b["slow_b"] > b["fluid_b"] * 1.2:
        s += f", ~{_round_b(b['slow_b'])} en lent"
    s += "."
    return s


def advice_lines(d: Dict[str, Any]) -> List[str]:
    b = budget(d)
    cpu = d.get("cpu") or {}
    L = []
    if b["vram"]:
        L.append(f"• Carte graphique : {b['gpu']} — {b['vram']:.1f} Go de VRAM. C'est ELLE qui fait la vitesse : "
                 f"un modèle qui tient dedans (fichier ≲ {b['fluid_gb']:.1f} Go) répond vite.")
    else:
        L.append("• Pas de carte graphique dédiée détectée : tout tourne sur le processeur → vise ≤ 3-4 B.")
    if d.get("ram"):
        L.append(f"• RAM : {d['ram']:.1f} Go (libre {d.get('ram_free') or 0:.1f} Go). Un modèle qui déborde de la VRAM "
                 "utilise la RAM et le CPU : ça marche, mais 5 à 20× plus lent.")
        if d["ram"] < 12:
            L.append("  ⚠ Peu de RAM : évite les 14 B et plus, et ferme les applis lourdes pendant un gros modèle.")
    if cpu.get("avx2") is False:
        L.append("• Processeur sans AVX2 : le calcul sur CPU est lent → reste dans ce qui tient en VRAM.")
    if d.get("disk_free") is not None:
        L.append(f"• Disque des modèles ({d.get('models_dir')}) : {d['disk_free']:.0f} Go libres.")
    L.append("")
    L.append(f"→ Zone confortable : modèles de 3 à {_round_b(b['fluid_b'])} en Q4 (ex. qwen2.5:7b, dolphin3:8b, llama3.1:8b).")
    if b["vram"] and b["vram"] < 10:
        L.append("→ gemma2:9b et mistral-nemo (12 B) débordent déjà un peu (≈ 10 tok/s, chargement ~40 s) ; "
                 "14 B : lent ; 27 B et plus : non.")
    return L


# ───────────────────────── API Ollama ─────────────────────────
def list_models(base: str = OLLAMA) -> List[Dict[str, Any]]:
    r = requests.get(f"{base}/api/tags", timeout=(3, 15))
    r.raise_for_status()
    out = []
    for m in r.json().get("models", []):
        det = m.get("details") or {}
        out.append({"name": m.get("name") or m.get("model") or "?",
                    "size": (m.get("size") or 0) / GB,
                    "modified": str(m.get("modified_at") or "")[:10],
                    "family": det.get("family") or "",
                    "params": det.get("parameter_size") or "",
                    "quant": det.get("quantization_level") or ""})
    out.sort(key=lambda x: x["name"].lower())
    return out


def delete_model(name: str, base: str = OLLAMA) -> None:
    r = requests.delete(f"{base}/api/delete", json={"model": name, "name": name}, timeout=(3, 60))
    if r.status_code >= 400:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")


def pull_model(name: str, on_progress: Callable[[Dict[str, Any]], None],
               cancel: Optional[threading.Event] = None, base: str = OLLAMA) -> bool:
    """Télécharge en flux. on_progress({status, done, total, speed}). Retourne False si annulé."""
    parts: Dict[str, Tuple[int, int]] = {}
    t0 = time.time()
    last_t, last_done = t0, 0
    speed = 0.0
    with requests.post(f"{base}/api/pull", json={"model": name, "name": name, "stream": True},
                       stream=True, timeout=(5, 120)) as r:
        if r.status_code >= 400:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
        for line in r.iter_lines():
            if cancel is not None and cancel.is_set():
                r.close()
                return False
            if not line:
                continue
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if ev.get("error"):
                raise RuntimeError(str(ev["error"]))
            dg = ev.get("digest")
            if dg and ev.get("total"):
                parts[dg] = (int(ev.get("completed") or 0), int(ev["total"]))
            done = sum(c for c, _ in parts.values())
            total = sum(t for _, t in parts.values())
            now = time.time()
            if now - last_t >= 0.7:
                inst = (done - last_done) / (now - last_t)
                speed = inst if not speed else speed * 0.6 + inst * 0.4
                last_t, last_done = now, done
            on_progress({"status": ev.get("status", ""), "done": done, "total": total, "speed": speed})
            if ev.get("status") == "success":
                return True
    return True


def bench_model(name: str, question: str, options: Optional[Dict[str, Any]] = None,
                cancel: Optional[threading.Event] = None, base: str = OLLAMA) -> Dict[str, Any]:
    # 1) chargement séparé (prompt vide = charge le modèle sans générer) : sinon le 1er passage
    #    mélange chargement / pagination mémoire et donne une vitesse faussement basse.
    load = 0.0
    tl = time.time()
    try:
        rl = requests.post(f"{base}/api/generate", json={"model": name, "prompt": "", "keep_alive": "5m",
                           "options": {k: v for k, v in (options or {}).items() if k == "num_ctx"}},
                           timeout=(5, 600))
        if rl.status_code < 400:
            load = time.time() - tl
    except Exception:
        pass
    if cancel is not None and cancel.is_set():
        return {"cancelled": True, "text": ""}
    t0 = time.time()
    body = {"model": name, "prompt": question, "stream": True, "keep_alive": "5m",
            "options": dict({"num_predict": 200, "temperature": 0.3}, **(options or {}))}
    text: List[str] = []
    fin: Dict[str, Any] = {}
    first = None
    with requests.post(f"{base}/api/generate", json=body, stream=True, timeout=(5, 600)) as r:
        if r.status_code >= 400:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
        for line in r.iter_lines():
            if cancel is not None and cancel.is_set():
                r.close()
                return {"cancelled": True, "text": "".join(text)}
            if not line:
                continue
            ev = json.loads(line)
            if ev.get("error"):
                raise RuntimeError(str(ev["error"]))
            if ev.get("response"):
                if first is None:
                    first = time.time()
                text.append(ev["response"])
            if ev.get("done"):
                fin = ev
                break
    total = time.time() - t0
    ec, ed = fin.get("eval_count") or 0, fin.get("eval_duration") or 0
    return {"text": "".join(text).strip(), "secs": total,
            "first": (first - t0) if first else None,
            "load": load + (fin.get("load_duration") or 0) / 1e9,
            "tokens": ec, "tps": (ec / (ed / 1e9)) if ed else None}


# ───────────────────────── mise à jour en ligne ─────────────────────────
_SIZE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(GB|MB)\b")


def parse_tags_page(html: str, family: str) -> Dict[str, float]:
    """Page https://ollama.com/library/<famille>/tags → {nom:tag: Go}. Tolérant."""
    out: Dict[str, float] = {}
    pat = re.compile(r'href="/library/(' + re.escape(family) + r':[\w.\-]+)"')
    for m in pat.finditer(html):
        if m.group(1) in out:
            continue
        sz = _SIZE_RE.search(html[m.end(): m.end() + 1500])
        if sz:
            v = float(sz.group(1))
            out[m.group(1)] = v / 1024 if sz.group(2) == "MB" else v
    return out


def refresh_online(timeout: float = 8.0, cancel: Optional[threading.Event] = None) -> Dict[str, float]:
    """Met à jour les tailles du catalogue depuis ollama.com. Ne lève jamais."""
    found: Dict[str, float] = {}
    if not requests:
        return found
    fams = sorted({c["name"].split(":")[0] for c in CATALOGUE})
    for fam in fams:
        if cancel is not None and cancel.is_set():
            break
        try:
            r = requests.get(f"https://ollama.com/library/{fam}/tags", timeout=timeout,
                             headers={"User-Agent": "Padawan/39.6"})
            if r.status_code != 200:
                continue
            sizes = parse_tags_page(r.text, fam)
            for c in CATALOGUE:
                n = c["name"] if ":" in c["name"] else c["name"] + ":latest"
                if n in sizes and 0.05 < sizes[n] < 500:
                    found[c["name"]] = round(sizes[n], 2)
        except Exception:
            continue
    return found


# ───────────────────────── mémoire du panneau ─────────────────────────
class Store:
    def __init__(self, path: str):
        self.path = path
        self.data: Dict[str, Any] = {"bench": {}, "sizes": {}, "sizes_date": "", "only_viable": True,
                                     "question": "Explique en trois phrases pourquoi le ciel est bleu."}
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict):
                self.data.update(d)
        except Exception:
            pass

    def save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        except Exception:
            pass

    def tps(self, name: str) -> Optional[float]:
        for k, v in (self.data.get("bench") or {}).items():
            if same_model(k, name):
                return v.get("tps")
        return None

    def size(self, entry: Dict[str, Any]) -> float:
        return float((self.data.get("sizes") or {}).get(entry["name"]) or entry["size"])


# ───────────────────────── interface ─────────────────────────
try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore


if tk is not None:
    class ModelsWindow(tk.Toplevel):  # type: ignore[misc]
        """🧠 Modèles. app doit fournir : _tip, _theme_fix (optionnel), model_activate(name),
        models_refresh_selector(select=None), current_model(), gen_opts() (optionnel)."""

        TABS = ("machine", "mine", "catalog", "bench")

        def __init__(self, app, C: Dict[str, str], store_path: str, tab: str = "machine",
                     base: str = OLLAMA, log: Callable[[str], None] = lambda s: None):
            super().__init__(app)
            self.app, self.C, self.base, self.log = app, C, base, log
            self.store = Store(store_path)
            self.diag: Dict[str, Any] = {}
            self.mine: List[Dict[str, Any]] = []
            self._q: "queue.Queue[Callable[[], None]]" = queue.Queue()
            self._pull_cancel: Optional[threading.Event] = None
            self._pulling: str = ""
            self._pull_pct: int = 0
            self._bench_cancel: Optional[threading.Event] = None
            self.title("🧠 Modèles — Padawan")
            self.configure(bg=C["bg"])
            self.minsize(980, 640)
            try:
                self.geometry("1280x820")
                self.state("zoomed")
            except Exception:
                pass
            self._style()
            self._build()
            self.bind("<Escape>", lambda e: self.close())
            self.bind("<F5>", lambda e: self.refresh_all())
            self._then = None
            for i, t in enumerate(self.TABS, 1):
                self.bind(f"<Control-Key-{i}>", lambda e, t=t: self.select_tab(t))
            self.protocol("WM_DELETE_WINDOW", self.close)
            self.after(80, self._poll)
            self.select_tab(tab)
            self.refresh_all()
            try:
                app._theme_fix(self)
            except Exception:
                pass

        # ---------- style ----------
        def _style(self):
            C = self.C
            st = ttk.Style(self)
            st.configure("Modeles.TNotebook", background=C["bg"], borderwidth=0)
            st.configure("Modeles.TNotebook.Tab", font=("Segoe UI", 12, "bold"), padding=(18, 8),
                         background=C["card"], foreground=C["fg"])
            st.configure("Modeles.Treeview", background=C["card"], fieldbackground=C["card"],
                         foreground=C["fg"], rowheight=30, font=("Segoe UI", 11), borderwidth=0)
            st.configure("Modeles.Treeview.Heading", background=C["card2"], foreground=C["gold"],
                         font=("Segoe UI", 11, "bold"), relief="flat")
            st.map("Modeles.Treeview", background=[("selected", C["sel"])],
                   foreground=[("selected", C["fg"])])
            st.configure("Modeles.Horizontal.TProgressbar", troughcolor=C["card"], background=C["ok"],
                         thickness=18)
            st.configure("Modeles.TCombobox", fieldbackground=C["card"], background=C["card"],
                         foreground=C["fg"], arrowcolor=C["gold"], padding=4)
            st.map("Modeles.TCombobox", fieldbackground=[("readonly", C["card"])],
                   foreground=[("readonly", C["fg"])], selectbackground=[("readonly", C["card"])],
                   selectforeground=[("readonly", C["fg"])])
            st.map("Modeles.TNotebook.Tab", background=[("selected", C["card2"]), ("!selected", C["card"])],
                   foreground=[("selected", C["gold"]), ("!selected", C["fg"])])
            try:
                self.option_add("*TCombobox*Listbox.font", ("Segoe UI", 11))
            except Exception:
                pass

        def _tip(self, w, text):
            try:
                self.app._tip(w, text)
            except Exception:
                pass

        def _btn(self, parent, text, cmd, tip="", kind="normal", size=11):
            C = self.C
            bg = {"primary": C["gold"], "ok": C["ok"], "danger": C["bad"]}.get(kind, C["card2"])
            fg = C["bg"] if kind in ("primary", "ok", "danger") else C["fg"]
            b = tk.Button(parent, text=text, command=cmd, bg=bg, fg=fg, activebackground=C["sel"],
                          activeforeground=C["fg"], relief="flat", bd=0, cursor="hand2",
                          font=("Segoe UI", size, "bold"), padx=14, pady=7)
            if tip:
                self._tip(b, tip)
            return b

        def _lbl(self, parent, text, size=11, color=None, bold=False, **kw):
            return tk.Label(parent, text=text, bg=kw.pop("bg", self.C["bg"]), fg=color or self.C["fg"],
                            font=("Segoe UI", size, "bold" if bold else "normal"), **kw)

        def _status(self, text, color=None):
            try:
                self.status.config(text=text, fg=color or self.C["dim"])
            except Exception:
                pass

        # ---------- threads ----------
        def _poll(self):
            try:
                while True:
                    fn = self._q.get_nowait()
                    try:
                        fn()
                    except Exception as e:
                        self.log(f"modeles ui: {e}")
            except queue.Empty:
                pass
            if self.winfo_exists():
                self.after(100, self._poll)

        def _ui(self, fn):
            self._q.put(fn)

        def _bg(self, fn):
            threading.Thread(target=fn, daemon=True).start()

        # ---------- construction ----------
        def _build(self):
            C = self.C
            top = tk.Frame(self, bg=C["bg"])
            top.pack(fill="x", padx=16, pady=(12, 4))
            self._lbl(top, "🧠 Modèles", 18, C["gold"], True).pack(side="left")
            b = self._btn(top, "✖ Fermer", self.close, "Fermer (Échap)")
            b.pack(side="right")
            b = self._btn(top, "🔄 Actualiser", self.refresh_all, "Relire la machine et les modèles (F5)")
            b.pack(side="right", padx=6)
            self.summary = self._lbl(self, "Diagnostic en cours…", 12, C["cyan"], True, anchor="w", justify="left")
            self.summary.pack(fill="x", padx=18, pady=(0, 2))
            self.summary.bind("<Configure>", lambda e: self.summary.config(wraplength=max(300, e.width - 10)))
            self.status = self._lbl(self, "", 10, C["dim"], anchor="w")
            self.status.pack(side="bottom", fill="x", padx=16, pady=(0, 8))
            dl = tk.Frame(self, bg=C["panel"])
            dl.pack(side="bottom", fill="x", padx=12, pady=(0, 4))
            self.nb = ttk.Notebook(self, style="Modeles.TNotebook")
            self.nb.pack(fill="both", expand=True, padx=12, pady=6)
            self.f_machine = tk.Frame(self.nb, bg=C["bg"])
            self.f_mine = tk.Frame(self.nb, bg=C["bg"])
            self.f_cat = tk.Frame(self.nb, bg=C["bg"])
            self.f_bench = tk.Frame(self.nb, bg=C["bg"])
            self.nb.add(self.f_machine, text="🖥 Ma machine  Ctrl+1")
            self.nb.add(self.f_mine, text="📦 Mes modèles  Ctrl+2")
            self.nb.add(self.f_cat, text="🛒 Catalogue  Ctrl+3")
            self.nb.add(self.f_bench, text="🏁 Banc d'essai  Ctrl+4")
            self._build_machine()
            self._build_mine()
            self._build_cat()
            self._build_bench()
            # barre de téléchargement (commune)
            self.dl_lbl = self._lbl(dl, "", 11, C["dim"], bg=C["panel"])
            self.dl_lbl.pack(side="left", padx=10, pady=6)
            self.dl_cancel = self._btn(dl, "✖ Annuler le téléchargement", self.cancel_pull,
                                       "Arrêter le téléchargement (Ollama garde les morceaux : reprendre plus tard repart d'où il était)",
                                       "danger", 10)
            self.dl_bar = ttk.Progressbar(dl, style="Modeles.Horizontal.TProgressbar", length=420,
                                          mode="determinate", maximum=1000)
            self.dl_frame = dl
            dl.pack_forget()  # visible seulement pendant un téléchargement

        def select_tab(self, tab):
            try:
                self.nb.select(self.TABS.index(tab) if tab in self.TABS else 0)
            except Exception:
                pass

        def _tree(self, parent, cols, widths, heights=8):
            C = self.C
            fr = tk.Frame(parent, bg=C["bg"])
            tv = ttk.Treeview(fr, columns=cols, show="headings", style="Modeles.Treeview", height=heights)
            for c, (title, w) in zip(cols, widths):
                tv.heading(c, text=title)
                tv.column(c, width=w, anchor="w", stretch=(c in ("desc", "name")))
            sb = ttk.Scrollbar(fr, orient="vertical", command=tv.yview)
            tv.configure(yscrollcommand=sb.set)
            tv.pack(side="left", fill="both", expand=True)
            sb.pack(side="right", fill="y")
            for dot, (_t, col) in DOT_UI.items():
                tv.tag_configure(col, foreground=C[col])
            return fr, tv

        def _build_machine(self):
            C = self.C
            f = self.f_machine
            self.m_text = tk.Text(f, bg=C["card"], fg=C["fg"], font=("Segoe UI", 12), wrap="word",
                                  relief="flat", padx=18, pady=14, height=8)
            self._m_text_pack = lambda: self.m_text.pack(fill="both", expand=True, padx=6, pady=8)
            self.m_text.tag_configure("h", foreground=C["gold"], font=("Segoe UI", 14, "bold"))
            self.m_text.tag_configure("ok", foreground=C["ok"])
            self.m_text.tag_configure("dim", foreground=C["dim"])
            for _d, (_t, col) in DOT_UI.items():
                self.m_text.tag_configure("dot_" + col, foreground=C[col], font=("Segoe UI", 12, "bold"))
            row = tk.Frame(f, bg=C["bg"])
            row.pack(side="bottom", fill="x", padx=6, pady=(0, 6))
            # v39.7 : recommandés = lignes cliquables avec bouton au bout
            self.rec_box = tk.Frame(f, bg=C["bg"])
            self.rec_box.pack(side="top", fill="x", padx=6, pady=(8, 0))
            self.rec_rows: Dict[str, Dict[str, Any]] = {}
            self._m_text_pack()
            b = self._btn(row, "🛒 Voir les modèles viables", lambda: self.select_tab("catalog"),
                          "Catalogue filtré sur ce que ta machine fait tourner", "primary")
            b.pack(side="left")
            b = self._btn(row, "📋 Copier le diagnostic", self.copy_diag, "Copier ce texte dans le presse-papiers")
            b.pack(side="left", padx=8)

        def _build_mine(self):
            C = self.C
            f = self.f_mine
            fr, self.tv_mine = self._tree(f, ("dot", "name", "size", "params", "family", "date", "note"),
                                          [("Ton PC", 110), ("Modèle", 300), ("Taille", 90), ("Param./quant.", 160),
                                           ("Famille", 110), ("Date", 110), ("Remarque", 380)])
            self.tv_mine.bind("<Double-1>", lambda e: self.activate_sel())
            self.tv_mine.bind("<Delete>", lambda e: self.delete_sel())
            row = tk.Frame(f, bg=C["bg"])
            row.pack(side="bottom", fill="x", padx=6, pady=(0, 6))
            fr.pack(fill="both", expand=True, padx=6, pady=8)
            self._btn(row, "⭐ Activer", self.activate_sel,
                      "Mettre ce modèle dans le sélecteur de Padawan et l'utiliser (double-clic)", "primary").pack(side="left")
            self._btn(row, "🏁 Comparer", self.bench_from_mine,
                      "Envoyer les modèles sélectionnés (Ctrl+clic, 3 max) au banc d'essai").pack(side="left", padx=8)
            self._btn(row, "🗑 Effacer…", self.delete_sel,
                      "Supprimer ce modèle du disque (confirmation demandée) — touche Suppr", "danger").pack(side="left")
            self.mine_lbl = self._lbl(row, "", 11, C["dim"])
            self.mine_lbl.pack(side="right")

        def _build_cat(self):
            C = self.C
            f = self.f_cat
            row = tk.Frame(f, bg=C["bg"])
            row.pack(fill="x", padx=6, pady=(8, 2))
            self.only_viable = tk.BooleanVar(value=bool(self.store.data.get("only_viable", True)))
            cb = tk.Checkbutton(row, text="Seulement ceux qui tournent sur mon PC", variable=self.only_viable,
                                command=self.fill_cat, bg=C["bg"], fg=C["fg"], selectcolor=C["card"],
                                activebackground=C["bg"], activeforeground=C["gold"], font=("Segoe UI", 11, "bold"))
            cb.pack(side="left")
            self._tip(cb, "Cache les 🔴 (trop gros pour ta carte graphique + RAM)")
            self._lbl(row, "   Étiquette :", 11, C["dim"]).pack(side="left")
            self.tag_var = tk.StringVar(value="Toutes")
            vals = ["Toutes"] + [f"{k} {v}" for k, v in TAGS.items()]
            tc = ttk.Combobox(row, textvariable=self.tag_var, values=vals, state="readonly", width=28,
                              style="Modeles.TCombobox", font=("Segoe UI", 11))
            tc.pack(side="left", padx=6)
            tc.bind("<<ComboboxSelected>>", lambda e: self.fill_cat())
            leg = tk.Frame(f, bg=C["bg"])
            leg.pack(fill="x", padx=8)
            for dot, why in DOT_TXT.items():
                txt, col = DOT_UI[dot]
                self._lbl(leg, txt, 10, C[col], True).pack(side="left")
                self._lbl(leg, f" = {why}     ", 10, C["dim"]).pack(side="left")
            fr, self.tv_cat = self._tree(f, ("dot", "name", "size", "tags", "state", "desc"),
                                         [("Ton PC", 110), ("Modèle", 260), ("Taille", 90), ("Étiquettes", 110),
                                          ("Action (clic)", 130), ("Description", 600)])
            self.tv_cat.bind("<Double-1>", lambda e: self.install_sel())
            self.tv_cat.bind("<ButtonRelease-1>", self._cat_click, add="+")
            self.tv_cat.bind("<Motion>", self._cat_motion, add="+")
            self._tip(self.tv_cat, "Clique « ⬇ Installer » ou « ⭐ Activer » au bout d'une ligne (un seul clic)")
            self.tv_cat.bind("<<TreeviewSelect>>", lambda e: self._cat_why())
            row2 = tk.Frame(f, bg=C["bg"])
            row2.pack(side="bottom", fill="x", padx=6, pady=(0, 6))
            fr.pack(fill="both", expand=True, padx=6, pady=6)
            self._btn(row2, "⬇ Installer", self.install_sel,
                      "Télécharger ce modèle (vérifie l'espace disque d'abord) — double-clic", "ok").pack(side="left")
            self._btn(row2, "🔄 Tailles depuis ollama.com", self.refresh_online,
                      "Rafraîchir les tailles du catalogue depuis ollama.com (facultatif, sans risque)").pack(side="left", padx=8)
            self.cat_why = self._lbl(row2, "", 11, C["cyan"])
            self.cat_why.pack(side="left", padx=10)

        def _build_bench(self):
            C = self.C
            f = self.f_bench
            row = tk.Frame(f, bg=C["bg"])
            row.pack(fill="x", padx=6, pady=(8, 2))
            self._lbl(row, "Question :", 11, C["gold"], True).pack(side="left")
            self.q_var = tk.StringVar(value=self.store.data.get("question") or "")
            e = tk.Entry(row, textvariable=self.q_var, bg=C["input"], fg=C["fg"], insertbackground=C["cursor"],
                         relief="flat", font=("Segoe UI", 12))
            e.pack(side="left", fill="x", expand=True, padx=8, ipady=5)
            e.bind("<Return>", lambda ev: self.run_bench())
            qrow = row
            row2 = tk.Frame(f, bg=C["bg"])
            row2.pack(fill="x", padx=6, pady=4)
            self.bench_vars: List[tk.StringVar] = []
            for i in range(3):
                self._lbl(row2, f"Modèle {i + 1} :", 11, C["dim"]).pack(side="left", padx=(8 if i else 0, 2))
                v = tk.StringVar(value="")
                cb = ttk.Combobox(row2, textvariable=v, state="readonly", width=26, style="Modeles.TCombobox",
                                  font=("Segoe UI", 11))
                cb.pack(side="left")
                self.bench_vars.append(v)
                setattr(self, f"bench_cb{i}", cb)
            self.bench_go = self._btn(qrow, "▶ Lancer", self.run_bench,
                                      "Poser la même question à chaque modèle (un après l'autre) — Entrée", "primary")
            self.bench_go.pack(side="left", padx=10)
            self._btn(qrow, "■ Arrêter", self.cancel_bench, "Arrêter le banc d'essai", "danger").pack(side="left")
            self._lbl(f, "Astuce : chaque modèle est d'abord chargé en mémoire (temps compté à part), puis chronométré. "
                         "Le tok/s mesuré corrige la pastille du modèle (≥ 12 tok/s = fluide).", 10, C["dim"]).pack(
                side="bottom", anchor="w", padx=8)
            cols = tk.Frame(f, bg=C["bg"])
            cols.pack(fill="both", expand=True, padx=6, pady=6)
            self.bench_out: List[Tuple[tk.Label, tk.Text]] = []
            for i in range(3):
                col = tk.Frame(cols, bg=C["card"])
                col.pack(side="left", fill="both", expand=True, padx=4)
                h = tk.Label(col, text="—", bg=C["card2"], fg=C["gold"], font=("Segoe UI", 11, "bold"),
                             anchor="w", justify="left", padx=10, pady=6, width=10, wraplength=380)
                h.pack(fill="x")
                t = tk.Text(col, bg=C["card"], fg=C["fg"], font=("Segoe UI", 11), wrap="word", relief="flat",
                            padx=10, pady=8, width=20, height=6)
                t.pack(fill="both", expand=True)
                self.bench_out.append((h, t))


        # ---------- données ----------
        def refresh_all(self, then: Optional[Tuple[str, str]] = None):
            self._then = then
            self._status("Diagnostic de la machine et lecture des modèles…")

            def work():
                d = diagnose(self.base)
                try:
                    mine = list_models(self.base)
                    err = ""
                except Exception as e:
                    mine, err = [], str(e)
                self._ui(lambda: self._apply(d, mine, err))
            self._bg(work)

        def _apply(self, d, mine, err):
            self.diag, self.mine = d, mine
            self.summary.config(text=summary_text(d))
            self.fill_machine()
            self.fill_mine()
            self.fill_cat()
            self.fill_bench_choices()
            if err:
                self._status(f"⚠ Ollama ne répond pas ({err[:120]}). Lance Ollama puis F5.", self.C["bad"])
            else:
                self._status(f"{len(mine)} modèle(s) installé(s) — Ollama {d.get('ollama') or '?'} — {d.get('when')}")
            then, self._then = getattr(self, "_then", None), None
            if then:
                self._status(*then)

        def diag_text(self) -> str:
            d = self.diag
            L = [summary_text(d), ""]
            for g in d.get("gpus") or []:
                fr = f", libre {g['free']:.1f} Go" if g.get("free") is not None else ""
                if g.get("free") is not None and g.get("vram") and g["free"] < g["vram"] * 0.5:
                    fr += " (un modèle est sans doute chargé en ce moment)"
                kind = "dédiée" if g.get("dedicated") else "intégrée/secondaire"
                L.append(f"GPU : {g['name']} — {g.get('vram') or 0:.1f} Go VRAM{fr} ({kind}, via {g.get('src')})")
            if not d.get("gpus"):
                L.append("GPU : aucun détecté")
            cpu = d.get("cpu") or {}
            L.append(f"CPU : {cpu.get('name') or '?'} — {cpu.get('cores') or '?'} cœurs / {cpu.get('threads') or '?'} fils"
                     + ("" if cpu.get("avx2") is None else (", AVX2 oui" if cpu["avx2"] else ", sans AVX2")))
            L.append(f"RAM : {d.get('ram') or 0:.1f} Go (libre {d.get('ram_free') or 0:.1f} Go)")
            L.append(f"Dossier des modèles : {d.get('models_dir')} — {d.get('disk_free') or 0:.0f} Go libres")
            L.append(f"Ollama : {d.get('ollama') or 'ne répond pas'}")
            L.append("")
            L += advice_lines(d)
            return "\n".join(L)

        def fill_machine(self):
            t = self.m_text
            t.config(state="normal")
            t.delete("1.0", "end")
            lines = self.diag_text().split("\n")
            t.insert("end", lines[0] + "\n", "h")
            self.fill_recs()
            t.insert("end", "\nDétails de la machine\n", "h")
            for ln in lines[1:]:
                t.insert("end", ln + "\n", "ok" if ln.startswith("→") else ("dim" if ln.startswith("  ") else ""))
            t.config(state="disabled")

        # ---------- v39.7 : recommandés cliquables ----------
        def installed_name(self, name: str) -> str:
            """Nom exact installé (« mistral » → « mistral:latest »), "" si absent."""
            return next((m["name"] for m in self.mine if same_model(m["name"], name)), "")

        def model_state(self, name: str) -> str:
            inst = self.installed_name(name)
            if not inst:
                return "absent"
            cur = ""
            try:
                cur = self.app.current_model()
            except Exception:
                pass
            return "actif" if same_model(inst, cur) else "installe"

        ACTION_TXT = {"absent": "⬇ Installer", "installe": "⭐ Activer", "actif": "✔ actif"}

        def model_action(self, name: str):
            """Clic sur une ligne / un bouton : installer, activer, ou rien si déjà actif."""
            st = self.model_state(name)
            if st == "absent":
                self.install_sel(name)
            elif st == "installe":
                inst = self.installed_name(name)
                try:
                    self.app.model_activate(inst)
                    self._status(f"⭐ {inst} est maintenant le modèle de Padawan.", self.C["ok"])
                except Exception as e:
                    self._status(f"Activation impossible : {e}", self.C["bad"])
                self.after(150, self._refresh_states)
            else:
                self._status(f"✔ {self.installed_name(name)} est déjà le modèle actif.", self.C["ok"])

        def _refresh_states(self):
            self.fill_recs()
            self.fill_mine()
            self.fill_cat()

        def fill_recs(self):
            C = self.C
            box = self.rec_box
            for w in box.winfo_children():
                w.destroy()
            self.rec_rows = {}
            recs = self.recommend()
            if not recs:
                return
            self._lbl(box, "Recommandés pour ta machine — clique une ligne pour l'installer ou l'activer :",
                      12, C["ok"], True, anchor="w").pack(fill="x", pady=(0, 4))
            for c, dot in recs:
                self._rec_row(box, c, dot)

        def _rec_row(self, box, c, dot):
            C = self.C
            name = c["name"]
            st = self.model_state(name)
            row = tk.Frame(box, bg=C["card"], cursor="hand2", highlightthickness=1, highlightbackground=C["line"])
            row.pack(fill="x", pady=1)
            txt, col = DOT_UI.get(dot, DOT_UI["⚪"])
            w_dot = tk.Label(row, text="●", bg=C["card"], fg=C[col], font=("Segoe UI", 13, "bold"), cursor="hand2")
            w_dot.pack(side="left", padx=(10, 6), pady=1)
            w_name = tk.Label(row, text=name, bg=C["card"], fg=C["gold"], font=("Segoe UI", 11, "bold"),
                              cursor="hand2", width=30, anchor="w")
            w_name.pack(side="left")
            w_size = tk.Label(row, text=fmt_gb(self.store.size(c)), bg=C["card"], fg=C["fg"],
                              font=("Segoe UI", 11), cursor="hand2", width=8, anchor="w")
            w_size.pack(side="left")
            w_tags = tk.Label(row, text=c["tags"], bg=C["card"], fg=C["cyan"], font=("Segoe UI", 11),
                              cursor="hand2", width=7, anchor="w")
            w_tags.pack(side="left")
            kind = {"absent": "ok", "installe": "primary", "actif": "normal"}[st]
            btn = self._btn(row, self.ACTION_TXT[st], lambda n=name: self.model_action(n), "", kind, 10)
            btn.configure(width=12, pady=2)
            btn.pack(side="right", padx=8, pady=2)
            if self._pulling and same_model(self._pulling, name):
                btn.configure(text=f"⏳ {self._pull_pct} %", state="disabled")
            w_desc = tk.Label(row, text=c["desc"], bg=C["card"], fg=C["dim"], font=("Segoe UI", 10),
                              cursor="hand2", anchor="w")
            w_desc.pack(side="left", fill="x", expand=True, padx=(4, 6))
            parts = [row, w_dot, w_name, w_size, w_tags, w_desc]
            _d, why = compat(self.store.size(c), self.diag, self.store.tps(name))
            tip = {"absent": f"Clic = installer {name} (≈{fmt_gb(self.store.size(c))})",
                   "installe": f"Clic = utiliser {name} dans Padawan (déjà installé)",
                   "actif": f"{name} est le modèle actif de Padawan"}[st]
            tip += f"\n{txt} : {why}\n{c['desc']}"

            def enter(e, ps=parts):
                for w in ps:
                    try:
                        w.configure(bg=C["card2"])
                    except Exception:
                        pass
                row.configure(highlightbackground=C["gold"])

            def leave(e, ps=parts):
                for w in ps:
                    try:
                        w.configure(bg=C["card"])
                    except Exception:
                        pass
                row.configure(highlightbackground=C["line"])

            for w in parts:
                w.bind("<Enter>", enter, add="+")
                w.bind("<Leave>", leave, add="+")
                w.bind("<Button-1>", lambda e, n=name: self.model_action(n), add="+")
                self._tip(w, tip)
            self._tip(btn, tip)
            self.rec_rows[name] = {"row": row, "btn": btn}

        def recommend(self) -> List[Tuple[Dict[str, Any], str]]:
            out = []
            for c in CATALOGUE:
                dot, _ = compat(self.store.size(c), self.diag, self.store.tps(c["name"]))
                if dot == "🟢" and c["params"] >= 2.5:
                    out.append((c, dot))
            out.sort(key=lambda x: -x[0]["params"])
            return out[:7]

        def copy_diag(self):
            try:
                self.clipboard_clear()
                self.clipboard_append(self.diag_text())
                self._status("📋 Diagnostic copié.", self.C["ok"])
            except Exception:
                pass

        def is_installed(self, name: str) -> bool:
            return any(same_model(m["name"], name) for m in self.mine)

        def fill_mine(self):
            tv = self.tv_mine
            tv.delete(*tv.get_children())
            cur = ""
            try:
                cur = self.app.current_model()
            except Exception:
                pass
            tot = 0.0
            for m in self.mine:
                tot += m["size"]
                dot, why = compat(m["size"], self.diag, self.store.tps(m["name"]))
                note = ("⭐ actif — " if same_model(m["name"], cur) else "") + why
                txt, col = DOT_UI.get(dot, DOT_UI["⚪"])
                tv.insert("", "end", iid=m["name"], tags=(col,), values=(txt, m["name"], fmt_gb(m["size"]),
                          f"{m['params']} {m['quant']}".strip(), m["family"], m["modified"], note))
            self.mine_lbl.config(text=f"{len(self.mine)} modèle(s), {tot:.1f} Go sur le disque")

        def cat_rows(self) -> List[Tuple[str, Dict[str, Any], str]]:
            tag = (self.tag_var.get() or "Toutes").split(" ")[0]
            rows = []
            for c in CATALOGUE:
                if tag != "Toutes" and tag not in c["tags"]:
                    continue
                dot, why = compat(self.store.size(c), self.diag, self.store.tps(c["name"]))
                if self.only_viable.get() and dot == "🔴":
                    continue
                rows.append((dot, c, why))
            return rows

        def fill_cat(self):
            self.store.data["only_viable"] = bool(self.only_viable.get())
            self.store.save()
            tv = self.tv_cat
            tv.delete(*tv.get_children())
            self._why: Dict[str, str] = {}
            for dot, c, why in self.cat_rows():
                state = self.ACTION_TXT[self.model_state(c["name"])]
                if self._pulling and same_model(self._pulling, c["name"]):
                    state = f"⏳ {self._pull_pct} %"
                txt, col = DOT_UI.get(dot, DOT_UI["⚪"])
                tv.insert("", "end", iid=c["name"], tags=(col,), values=(txt, c["name"], fmt_gb(self.store.size(c)),
                          c["tags"], state, c["desc"]))
                self._why[c["name"]] = f"{txt} : {why}"

        def _cat_click(self, e):
            tv = self.tv_cat
            if tv.identify_region(e.x, e.y) != "cell" or tv.identify_column(e.x) != "#5":
                return
            iid = tv.identify_row(e.y)
            if iid:
                tv.selection_set(iid)
                if not (self._pulling and same_model(self._pulling, iid)):
                    self.model_action(iid)

        def _cat_motion(self, e):
            tv = self.tv_cat
            on = tv.identify_region(e.x, e.y) == "cell" and tv.identify_column(e.x) == "#5" and tv.identify_row(e.y)
            want = "hand2" if on else ""
            if str(tv.cget("cursor")) != want:
                tv.configure(cursor=want)

        def _cat_why(self):
            sel = self.tv_cat.selection()
            self.cat_why.config(text=self._why.get(sel[0], "") if sel else "")

        def fill_bench_choices(self):
            names = [m["name"] for m in self.mine]
            for i, v in enumerate(self.bench_vars):
                getattr(self, f"bench_cb{i}").config(values=["(aucun)"] + names)
                if v.get() not in names:
                    v.set("(aucun)")
            if self.bench_vars[0].get() == "(aucun)" and names:
                cur = ""
                try:
                    cur = self.app.current_model()
                except Exception:
                    pass
                pick = next((n for n in names if same_model(n, cur)), names[0])
                self.bench_vars[0].set(pick)

        # ---------- actions ----------
        def _sel(self, tv) -> List[str]:
            return list(tv.selection())

        def activate_sel(self):
            sel = self._sel(self.tv_mine)
            if not sel:
                self._status("Choisis un modèle dans la liste.", self.C["bad"])
                return
            try:
                self.app.model_activate(sel[0])
                self._status(f"⭐ {sel[0]} est maintenant le modèle de Padawan.", self.C["ok"])
                self.fill_mine()
            except Exception as e:
                self._status(f"Activation impossible : {e}", self.C["bad"])

        def delete_sel(self):
            sel = self._sel(self.tv_mine)
            if not sel:
                return
            name = sel[0]
            m = next((x for x in self.mine if x["name"] == name), {"size": 0})
            cur = ""
            try:
                cur = self.app.current_model()
            except Exception:
                pass
            extra = "\n\n⚠ C'est le modèle ACTIF de Padawan." if same_model(name, cur) else ""
            if not messagebox.askyesno("Effacer le modèle",
                                       f"Effacer « {name} » ({fmt_gb(m['size'])}) du disque ?\n"
                                       f"Il faudra le retélécharger pour l'utiliser.{extra}", parent=self):
                return
            self._status(f"🗑 Suppression de {name}…")

            def work():
                try:
                    delete_model(name, self.base)
                    self._ui(lambda: self._after_change(then=(f"🗑 {name} effacé.", self.C["ok"])))
                except Exception as e:
                    self._ui(lambda e=e: self._status(f"Suppression impossible : {e}", self.C["bad"]))
            self._bg(work)

        def _after_change(self, select: Optional[str] = None, then: Optional[Tuple[str, str]] = None):
            try:
                self.app.models_refresh_selector(select=select)
            except Exception as e:
                self.log(f"modeles selector: {e}")
            self.refresh_all(then)

        def bench_from_mine(self):
            sel = self._sel(self.tv_mine)[:3]
            if not sel:
                self._status("Sélectionne 1 à 3 modèles (Ctrl+clic).", self.C["bad"])
                return
            for i, v in enumerate(self.bench_vars):
                v.set(sel[i] if i < len(sel) else "(aucun)")
            self.select_tab("bench")

        def install_sel(self, name: Optional[str] = None):
            if name is None:
                sel = self._sel(self.tv_cat)
                if not sel:
                    self._status("Choisis un modèle du catalogue.", self.C["bad"])
                    return
                name = sel[0]
            c = next((x for x in CATALOGUE if x["name"] == name), {"name": name, "size": 0})
            if self.is_installed(name):
                if self.model_state(name) == "installe":
                    return self.model_action(name)
                self._status(f"✔ {name} est déjà installé et actif.", self.C["ok"])
                return
            if self._pull_cancel is not None:
                self._status("Un téléchargement est déjà en cours.", self.C["bad"])
                return
            size = self.store.size(c) if c.get("size") else 0
            free = self.diag.get("disk_free")
            if size and free is not None and free < size * 1.1 + 2:
                messagebox.showerror("Espace disque insuffisant",
                                     f"{name} demande ≈{fmt_gb(size)} et il reste {free:.1f} Go "
                                     f"sur le disque des modèles.\nEfface un modèle d'abord.", parent=self)
                return
            dot, why = compat(size, self.diag)
            if dot == "🔴" and not messagebox.askyesno(
                    "Trop gros pour ce PC", f"{name} ({fmt_gb(size)}) : {why}.\nIl sera très lent ou ne "
                                            "chargera pas. Télécharger quand même ?", parent=self):
                return
            if size >= 3 and not messagebox.askyesno(
                    "Télécharger", f"Télécharger {name} (≈{fmt_gb(size)}) ?\n{dot} {why}", parent=self):
                return
            ev = threading.Event()
            self._pull_cancel = ev
            self._pulling, self._pull_pct = name, 0
            self._row_progress(name)
            self.dl_frame.pack(side="bottom", fill="x", padx=12, pady=(0, 4), before=self.nb)
            self.dl_lbl.config(text=f"⬇ {name} : connexion…")
            self.dl_bar.pack(side="left", padx=10)
            self.dl_cancel.pack(side="right", padx=8, pady=4)
            self.dl_bar["value"] = 0

            def prog(p):
                def ui():
                    tot, done = p["total"], p["done"]
                    if tot:
                        self.dl_bar["value"] = int(done * 1000 / tot)
                        self._pull_pct = int(done * 100 / tot)
                        self._row_progress(name)
                        sp = p["speed"] / 1024 ** 2
                        eta = (tot - done) / p["speed"] if p["speed"] > 0 else 0
                        self.dl_lbl.config(text=f"⬇ {name} : {done / GB:.2f} / {tot / GB:.2f} Go — "
                                                f"{sp:.1f} Mo/s — reste ~{int(eta // 60)} min {int(eta % 60)} s")
                    else:
                        self.dl_lbl.config(text=f"⬇ {name} : {p['status']}")
                self._ui(ui)

            def work():
                try:
                    ok = pull_model(name, prog, ev, self.base)
                    msg = (f"✔ {name} installé — il est dans le sélecteur de Padawan.", self.C["ok"]) if ok else \
                          (f"✖ Téléchargement de {name} annulé (les morceaux restent dans le cache d'Ollama).",
                           self.C["dim"])
                    self._ui(lambda: self._pull_done(msg, name if ok else None))
                except Exception as e:
                    self._ui(lambda e=e: self._pull_done((f"Téléchargement impossible : {e}", self.C["bad"]), None))
            self._bg(work)

        def _row_progress(self, name):
            r = self.rec_rows.get(name)
            if r:
                try:
                    r["btn"].configure(text=f"⏳ {self._pull_pct} %", state="disabled")
                except Exception:
                    pass
            try:
                if self.tv_cat.exists(name):
                    self.tv_cat.set(name, "state", f"⏳ {self._pull_pct} %")
            except Exception:
                pass

        def _pull_done(self, msg, name):
            was = self._pulling
            self._pull_cancel = None
            self._pulling, self._pull_pct = "", 0
            if not name:  # annulé / échec : remettre les boutons
                self._refresh_states()
            self.dl_bar.pack_forget()
            self.dl_cancel.pack_forget()
            self.dl_lbl.config(text="")
            self.dl_frame.pack_forget()
            self._status(*msg)
            if name:
                self._after_change(select=None, then=msg)

        def cancel_pull(self):
            if self._pull_cancel is not None:
                self._pull_cancel.set()
                self.dl_lbl.config(text="Annulation…")

        def refresh_online(self):
            self._status("🔄 Lecture des tailles sur ollama.com…")

            def work():
                found = refresh_online()
                def ui():
                    if found:
                        self.store.data["sizes"] = found
                        self.store.data["sizes_date"] = datetime.now().strftime("%Y-%m-%d")
                        self.store.save()
                        self.fill_cat()
                        self.fill_machine()
                        self._status(f"🔄 {len(found)} taille(s) mise(s) à jour depuis ollama.com.", self.C["ok"])
                    else:
                        self._status("ollama.com injoignable ou format changé : catalogue intégré conservé.")
                self._ui(ui)
            self._bg(work)

        def run_bench(self):
            names = [v.get() for v in self.bench_vars if v.get() and v.get() != "(aucun)"]
            names = list(dict.fromkeys(names))
            q = self.q_var.get().strip()
            if not names or not q:
                self._status("Choisis au moins un modèle et une question.", self.C["bad"])
                return
            if self._bench_cancel is not None:
                return
            self.store.data["question"] = q
            self.store.save()
            ev = threading.Event()
            self._bench_cancel = ev
            for h, t in self.bench_out:
                h.config(text="—", fg=self.C["gold"])
                t.delete("1.0", "end")
            for i, n in enumerate(names):
                self.bench_out[i][0].config(text=f"{n}\n⏳ en attente…")
            opts = {}
            try:
                o = self.app.gen_opts()
                if o.get("num_ctx"):
                    opts["num_ctx"] = int(o["num_ctx"])
            except Exception:
                pass

            def work():
                for i, n in enumerate(names):
                    if ev.is_set():
                        break
                    self._ui(lambda i=i, n=n: self.bench_out[i][0].config(text=f"{n}\n⏳ chargement et réponse…"))
                    try:
                        r = bench_model(n, q, opts, ev, self.base)
                    except Exception as e:
                        r = {"error": str(e)}
                    self._ui(lambda i=i, n=n, r=r: self._bench_show(i, n, r))
                self._ui(self._bench_end)
            self._bg(work)

        def _bench_show(self, i, n, r):
            h, t = self.bench_out[i]
            if r.get("error"):
                h.config(text=f"{n}\n✖ {r['error'][:80]}")
                return
            if r.get("cancelled"):
                h.config(text=f"{n}\n■ arrêté")
                t.insert("end", r.get("text", ""))
                return
            tps = r.get("tps")
            m = next((x for x in self.mine if x["name"] == n), None)
            dot, why = compat(m["size"] if m else None, self.diag, tps)
            h.config(fg=self.C[DOT_UI.get(dot, DOT_UI["⚪"])[1]])
            h.config(text=f"{DOT_UI.get(dot, DOT_UI['⚪'])[0]} — {n}\nchargement {r['load']:.1f} s · réponse {r['secs']:.1f} s — "
                          f"{r['tokens']} tokens — {tps or 0:.1f} tok/s")
            t.insert("end", r.get("text", ""))
            if tps:
                self.store.data.setdefault("bench", {})[n] = {
                    "tps": round(tps, 2), "secs": round(r["secs"], 2), "load": round(r["load"], 2),
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M")}
                self.store.save()

        def _bench_end(self):
            self._bench_cancel = None
            self.fill_mine()
            self.fill_cat()
            self._status("🏁 Banc d'essai terminé — pastilles corrigées avec les vitesses mesurées.", self.C["ok"])

        def cancel_bench(self):
            if self._bench_cancel is not None:
                self._bench_cancel.set()

        def close(self):
            if self._pull_cancel is not None:
                if not messagebox.askyesno("Téléchargement en cours",
                                           "Un téléchargement est en cours. L'annuler et fermer ?", parent=self):
                    return
                self._pull_cancel.set()
            if self._bench_cancel is not None:
                self._bench_cancel.set()
            self.destroy()
