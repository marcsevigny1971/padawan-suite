# -*- coding: utf-8 -*-
"""
padawan_tray — module system tray visible de Padawan.

Icône barre système (pystray + Pillow), menu sans default=True,
démarrage Windows (shell:Startup + HKCU Run), lanceur Gestionnaire de fichiers + Archiveur (archiveur5.py, repli v4/v3/v2/v1).

Assets locaux (même dossier) : padawan_tray.ico / padawan_tray.png (teal).
Alias public : systemtray.py réexporte ce module (Marc cherche systemtray.py).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
from typing import Any, Callable, Dict, Optional

try:
    import pystray
    from pystray import MenuItem as TrayMenuItem
except ImportError:
    pystray = None
    TrayMenuItem = None  # type: ignore

try:
    from PIL import Image, ImageDraw
except ImportError:
    Image = ImageDraw = None  # type: ignore

TRAY_DIR = os.path.dirname(os.path.abspath(__file__))
TRAY_AVAILABLE = pystray is not None and Image is not None

STARTUP_REG_NAME = "Padawan"
STARTUP_LNK_NAME = "Padawan.lnk"
STARTUP_BAT_NAME = "Padawan.bat"

ICO_NAME = "padawan_tray.ico"
PNG_NAME = "padawan_tray.png"


def _noop_log(msg: str) -> None:
    pass


def _python_launcher() -> str:
    """Retourne pythonw.exe en priorité pour toute GUI Windows."""
    if sys.platform == "win32":
        # Chemin demandé pour cette installation, avant les alias WindowsApps.
        roots = [
            os.environ.get("LOCALAPPDATA", ""),
            os.environ.get("USERPROFILE", ""),
        ]
        for root in roots:
            if root:
                cand = os.path.join(root, "Python", "pythoncore-3.14-64", "pythonw.exe")
                if os.path.isfile(cand):
                    return cand

        exe = sys.executable or ""
        base, name = os.path.split(exe)
        if name.lower() == "pythonw.exe" and os.path.isfile(exe):
            return exe
        if name.lower() == "python.exe":
            cand = os.path.join(base, "pythonw.exe")
            if os.path.isfile(cand):
                return cand
        found = shutil.which("pythonw.exe")
        if found:
            return found
    return sys.executable or "pythonw"


def _draw_teal_padawan(size: int):
    """Icône Padawan distincte (teal / turquoise + accent or)."""
    if Image is None or ImageDraw is None:
        return None
    img = Image.new("RGBA", (size, size), (10, 24, 28, 255))
    dr = ImageDraw.Draw(img)
    m = max(2, size // 10)
    teal = (32, 178, 170, 255)
    teal_hi = (64, 224, 208, 255)
    dark = (10, 24, 28, 255)
    gold = (228, 192, 122, 255)
    dr.ellipse([m, m, size - m - 1, size - m - 1], fill=teal)
    inner = m + max(2, size // 8)
    dr.ellipse([inner, inner, size - inner - 1, size - inner - 1], fill=dark)
    cx = size // 2
    stem_w = max(2, size // 10)
    top = m + max(2, size // 7)
    bot = size - m - max(2, size // 7)
    dr.rectangle([cx - stem_w // 2, top, cx + stem_w // 2, bot], fill=teal_hi)
    loop_l = cx - stem_w // 2
    loop_r = min(size - m - 2, cx + size // 3)
    loop_t = top
    loop_b = top + (bot - top) // 2
    dr.arc(
        [loop_l, loop_t, loop_r, loop_b],
        start=270,
        end=90,
        fill=teal_hi,
        width=max(2, size // 12),
    )
    eye = max(2, size // 14)
    ex = cx + size // 6
    ey = (loop_t + loop_b) // 2
    dr.ellipse([ex - eye, ey - eye, ex + eye, ey + eye], fill=gold)
    return img


def make_tray_image(size: int = 64):
    """Charge padawan_tray.ico/.png si présent, sinon génère l'icône teal."""
    if Image is None:
        return None
    png = os.path.join(TRAY_DIR, PNG_NAME)
    ico = os.path.join(TRAY_DIR, ICO_NAME)
    try:
        if os.path.isfile(png):
            img = Image.open(png).convert("RGBA")
            if img.size != (size, size):
                img = img.resize((size, size), Image.Resampling.LANCZOS)
            return img
        if os.path.isfile(ico):
            img = Image.open(ico).convert("RGBA")
            if img.size != (size, size):
                img = img.resize((size, size), Image.Resampling.LANCZOS)
            return img
    except Exception:
        pass
    return _draw_teal_padawan(size)



def windows_startup_dir() -> str:
    """shell:Startup — %APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Startup (legacy cleanup)."""
    appdata = os.environ.get("APPDATA") or os.path.expandvars(r"%APPDATA%")
    return os.path.join(appdata, r"Microsoft\Windows\Start Menu\Programs\Startup")


def windows_startup_paths(script: Optional[str] = None) -> Dict[str, str]:
    """Chemins documentes (reg = source de verite; bat/lnk = legacy a supprimer)."""
    start = windows_startup_dir()
    return {
        "startup_dir": start,
        "bat": os.path.join(start, STARTUP_BAT_NAME),
        "lnk": os.path.join(start, STARTUP_LNK_NAME),
        "reg": r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run\\" + STARTUP_REG_NAME,
        "script": os.path.abspath(script) if script else "",
        "python": _python_launcher(),
    }


def _startup_command(script: Optional[str] = None) -> str:
    py = _python_launcher()
    sc = os.path.abspath(script or "")
    return f'"{py}" "{sc}"'


def _remove_legacy_startup_files(log: Callable[[str], None]) -> None:
    """Supprime toujours Startup\\Padawan.bat et .lnk (doublons tray)."""
    paths = windows_startup_paths()
    for legacy in (paths["bat"], paths["lnk"]):
        try:
            if os.path.isfile(legacy):
                os.remove(legacy)
                log(f"startup legacy rm: {legacy}")
        except OSError as e:
            log(f"startup legacy rm: {e}")


def is_windows_startup_enabled() -> bool:
    """Coche = presence de la cle HKCU Run Padawan."""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_READ,
        )
        try:
            winreg.QueryValueEx(key, STARTUP_REG_NAME)
            return True
        except FileNotFoundError:
            return False
        finally:
            winreg.CloseKey(key)
    except Exception:
        return False


def ensure_windows_startup(
    enable: bool,
    script: Optional[str] = None,
    *,
    log_fn: Optional[Callable[[str], None]] = None,
) -> str:
    """
    Cree/retire l'auto-start Windows via HKCU Run UNIQUEMENT.
    Supprime toujours tout Startup\\Padawan.bat / .lnk.
    Retourne le chemin documente de l'entree (ou message).
    """
    log = log_fn or _noop_log
    if sys.platform != "win32":
        return "auto-start: non-Windows — ignore"
    if not script:
        return "auto-start: script manquant"
    paths = windows_startup_paths(script)
    script = os.path.abspath(script)
    cmd = _startup_command(script)
    _remove_legacy_startup_files(log)
    if enable:
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_SET_VALUE,
            )
            winreg.SetValueEx(key, STARTUP_REG_NAME, 0, winreg.REG_SZ, cmd)
            winreg.CloseKey(key)
            log(f"startup reg OK: {cmd}")
            return paths["reg"]
        except Exception as e:
            log(f"startup reg: {e}")
            return f"echec startup: {e}"
    else:
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_SET_VALUE,
            )
            try:
                winreg.DeleteValue(key, STARTUP_REG_NAME)
            except FileNotFoundError:
                pass
            winreg.CloseKey(key)
        except Exception as e:
            log(f"startup reg rm: {e}")
        return "(retiree)"


_MUTEX_HANDLE = None


def acquire_single_instance(mutex_name: str = r"Local\Padawan_SingleInstance") -> bool:
    """True si premiere instance; False si une autre tourne deja (ERROR_ALREADY_EXISTS=183)."""
    global _MUTEX_HANDLE
    if sys.platform != "win32":
        return True
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        ERROR_ALREADY_EXISTS = 183
        handle = kernel32.CreateMutexW(None, False, mutex_name)
        if not handle:
            return True
        _MUTEX_HANDLE = handle  # garder vivant
        if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
            return False
        return True
    except Exception:
        return True


def launch_file_manager(
    base: str,
    *,
    say: Optional[Callable[[str, str], None]] = None,
    app_name: str = "Padawan",
    parent: Any = None,
    log_fn: Optional[Callable[[str], None]] = None,
) -> None:
    """Lance gestionnaire_fichiers5.py (même dossier) via pythonw/sys.executable."""
    log = log_fn or _noop_log

    def _say(who: str, msg: str) -> None:
        if say:
            try:
                say(who, msg)
            except Exception:
                pass

    gf = os.path.join(base, "gestionnaire_fichiers5.py")
    if not os.path.isfile(gf):
        _say("sys", f"Gestionnaire introuvable: {gf}")
        try:
            from tkinter import messagebox

            messagebox.showwarning(
                app_name,
                "Gestionnaire de fichiers introuvable.\n\n"
                f"Attendu:\n{gf}\n\n"
                "Place gestionnaire_fichiers5.py à côté de Padawan.",
                parent=parent,
            )
        except Exception:
            pass
        return
    try:
        exe = _python_launcher()
        kwargs: Dict[str, Any] = {
            "cwd": base,
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "close_fds": True,
        }
        if sys.platform.startswith("win"):
            # pythonw + CREATE_NO_WINDOW + SW_HIDE prevents terminal flashes.
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            try:
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                si.wShowWindow = 0
                kwargs["startupinfo"] = si
            except Exception:
                pass
        subprocess.Popen([exe, gf], **kwargs)
        _say("sys", "Gestionnaire de fichiers lancé.")
    except Exception as e:
        log(f"launch file manager: {e}")
        _say("sys", f"Erreur lancement gestionnaire: {e}")


def launch_archiveur(
    base: str,
    *,
    say: Optional[Callable[[str, str], None]] = None,
    app_name: str = "Padawan",
    parent: Any = None,
    log_fn: Optional[Callable[[str], None]] = None,
) -> None:
    """Lance archiveur5.py (repli v4, v3, v2 puis v1) via pythonw / CREATE_NO_WINDOW."""
    log = log_fn or _noop_log

    def _say(who: str, msg: str) -> None:
        if say:
            try:
                say(who, msg)
            except Exception:
                pass

    def _resolve(root: str) -> Optional[str]:
        for name in ("archiveur5.py", "archiveur4.py", "archiveur3.py", "archiveur2.py", "archiveur1.py"):
            cand = os.path.join(root, name)
            if os.path.isfile(cand):
                return cand
        return None

    ar = _resolve(base)
    if not ar:
        ar = _resolve(TRAY_DIR)
        if ar:
            base = TRAY_DIR
    if not ar:
        expected = os.path.join(base, "archiveur5.py")
        _say("sys", f"Archiveur introuvable: {expected}")
        try:
            from tkinter import messagebox

            messagebox.showwarning(
                app_name,
                "Archiveur introuvable.\n\n"
                f"Attendu:\n{expected}\n"
                f"(ou archiveur4/3/2/1.py)\n\n"
                "Place archiveur5.py à côté de Padawan.",
                parent=parent,
            )
        except Exception:
            pass
        return
    try:
        exe = _python_launcher()
        kwargs: Dict[str, Any] = {
            "cwd": base,
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "close_fds": True,
        }
        if sys.platform.startswith("win"):
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            try:
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                si.wShowWindow = 0
                kwargs["startupinfo"] = si
            except Exception:
                pass
        subprocess.Popen([exe, ar], **kwargs)
        _say("sys", f"Archiveur lancé ({os.path.basename(ar)}).")
    except Exception as e:
        log(f"launch archiveur: {e}")
        _say("sys", f"Erreur lancement Archiveur: {e}")

def launch_arsenal(
    base: str,
    *,
    say: Optional[Callable[[str, str], None]] = None,
    app_name: str = "Padawan",
    parent: Any = None,
    log_fn: Optional[Callable[[str], None]] = None,
) -> None:
    """Lance Arsenal (arsenal1.py) via pythonw / CREATE_NO_WINDOW.
    Arsenal est a instance unique : s'il tourne deja, sa fenetre revient simplement devant."""
    log = log_fn or _noop_log

    def _say(who: str, msg: str) -> None:
        if say:
            try:
                say(who, msg)
            except Exception:
                pass

    ar = None
    for root in (base, TRAY_DIR):
        cand = os.path.join(root, "arsenal1.py")
        if os.path.isfile(cand):
            ar, base = cand, root
            break
    if not ar:
        expected = os.path.join(base, "arsenal1.py")
        _say("sys", f"Arsenal introuvable: {expected}")
        try:
            from tkinter import messagebox

            messagebox.showwarning(
                app_name,
                "Arsenal introuvable.\n\n"
                f"Attendu:\n{expected}\n\n"
                "Place arsenal1.py à côté de Padawan.",
                parent=parent,
            )
        except Exception:
            pass
        return
    try:
        exe = _python_launcher()
        kwargs: Dict[str, Any] = {
            "cwd": base,
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "close_fds": True,
        }
        if sys.platform.startswith("win"):
            # pas de STARTUPINFO SW_HIDE ici : Windows l'appliquerait au premier
            # ShowWindow d'Arsenal et sa fenetre resterait invisible.
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen([exe, ar], **kwargs)
        _say("sys", "Arsenal lancé.")
    except Exception as e:
        log(f"launch arsenal: {e}")
        _say("sys", f"Erreur lancement Arsenal: {e}")


def launch_grimoire(
    base: str,
    *,
    say: Optional[Callable[[str, str], None]] = None,
    app_name: str = "Padawan",
    parent: Any = None,
    log_fn: Optional[Callable[[str], None]] = None,
) -> None:
    """Lance le Grimoire (grimoire1.py) via pythonw / CREATE_NO_WINDOW.
    Le Grimoire est a instance unique : s'il tourne deja, sa fenetre revient devant."""
    log = log_fn or _noop_log

    def _say(who: str, msg: str) -> None:
        if say:
            try:
                say(who, msg)
            except Exception:
                pass

    gr = None
    for root in (base, TRAY_DIR):
        cand = os.path.join(root, "grimoire1.py")
        if os.path.isfile(cand):
            gr, base = cand, root
            break
    if not gr:
        expected = os.path.join(base, "grimoire1.py")
        _say("sys", f"Grimoire introuvable: {expected}")
        try:
            from tkinter import messagebox

            messagebox.showwarning(
                app_name,
                "Grimoire introuvable.\n\n"
                f"Attendu:\n{expected}\n\n"
                "Place grimoire1.py à côté de Padawan.",
                parent=parent,
            )
        except Exception:
            pass
        return
    try:
        exe = _python_launcher()
        kwargs: Dict[str, Any] = {
            "cwd": base,
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "close_fds": True,
        }
        if sys.platform.startswith("win"):
            # pas de STARTUPINFO SW_HIDE : la fenetre du Grimoire resterait invisible.
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen([exe, gr], **kwargs)
        _say("sys", "Grimoire lancé.")
    except Exception as e:
        log(f"launch grimoire: {e}")
        _say("sys", f"Erreur lancement Grimoire: {e}")



# ---------------------------------------------------------------- Facteur au demarrage (HKCU Run "Facteur")
FACTEUR_REG_NAME = "Facteur"
FACTEUR_MUTEX = "Local\\Facteur_SingleInstance"


def _facteur_off_flag() -> str:
    la = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(la, "Padawan", "Facteur", "demarrage_desactive.flag")


def is_facteur_startup_enabled() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as k:
            winreg.QueryValueEx(k, FACTEUR_REG_NAME)
            return True
    except Exception:
        return False


def set_facteur_startup(enable: bool, facteur_py: str, log_fn: Optional[Callable[[str], None]] = None) -> bool:
    """Ajoute/retire HKCU Run 'Facteur' (pythonw facteur1.py --cache). Desactivation memorisee par un drapeau."""
    log = log_fn or _noop_log
    if sys.platform != "win32":
        return False
    flag = _facteur_off_flag()
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run",
                            0, winreg.KEY_SET_VALUE) as k:
            if enable:
                cmd = f'"{_python_launcher()}" "{os.path.abspath(facteur_py)}" --cache'
                winreg.SetValueEx(k, FACTEUR_REG_NAME, 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(k, FACTEUR_REG_NAME)
                except FileNotFoundError:
                    pass
        if enable:
            if os.path.isfile(flag):
                os.remove(flag)
        else:
            os.makedirs(os.path.dirname(flag), exist_ok=True)
            open(flag, "w").write("Facteur au demarrage desactive manuellement\n")
        return True
    except Exception as e:
        log(f"facteur startup: {e}")
        return False


def ensure_facteur_startup_default(facteur_py: str, log_fn=None) -> None:
    """Defaut ON : cree la cle si absente, sauf si Marc l'a desactivee (drapeau)."""
    if os.path.isfile(facteur_py) and not os.path.isfile(_facteur_off_flag()) and not is_facteur_startup_enabled():
        set_facteur_startup(True, facteur_py, log_fn)


def is_facteur_running() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        h = ctypes.windll.kernel32.OpenMutexW(0x00100000, False, FACTEUR_MUTEX)
        if h:
            ctypes.windll.kernel32.CloseHandle(h)
            return True
    except Exception:
        pass
    return False


def stop_facteur(log_fn=None) -> None:
    """Arrete Facteur (pythonw ... facteur1.py) sans fenetre."""
    if sys.platform != "win32":
        return
    ps = ("Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
          "Where-Object { $_.CommandLine -like '*facteur1.py*' -and $_.ProcessId -ne " + str(os.getpid()) + " } | "
          "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }")
    try:
        subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps], timeout=20,
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception as e:
        (log_fn or _noop_log)(f"stop facteur: {e}")


# ---- pastille couleur dessinee dans le menu tray Win32 (pas d'emoji)
_PASTILLE_BMP: Dict[str, Any] = {}
PASTILLE_RGB = {"vert": (0, 200, 70), "jaune": (255, 210, 0)}


def _pastille_hbitmap(color: str):
    if color in _PASTILLE_BMP:
        return _PASTILLE_BMP[color]
    import ctypes
    from ctypes import wintypes
    from PIL import Image, ImageDraw
    sz, k = 16, 8
    big = Image.new("RGBA", (sz * k, sz * k), (0, 0, 0, 0))
    r, g, b = PASTILLE_RGB[color]
    ImageDraw.Draw(big).ellipse((k, k, sz * k - k - 1, sz * k - k - 1), fill=(r, g, b, 255),
                                outline=(40, 40, 40, 255), width=k)
    img = big.resize((sz, sz), Image.LANCZOS)

    class BIH(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                    ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]
    bih = BIH(ctypes.sizeof(BIH), sz, -sz, 1, 32, 0, 0, 0, 0, 0, 0)
    bits = ctypes.c_void_p()
    gdi = ctypes.windll.gdi32
    gdi.CreateDIBSection.restype = wintypes.HBITMAP
    gdi.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.c_void_p, wintypes.UINT,
                                     ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
    hbmp = gdi.CreateDIBSection(None, ctypes.byref(bih), 0, ctypes.byref(bits), None, 0)
    buf = bytearray()
    for (pr, pg, pb, pa) in img.getdata():  # BGRA premultiplie
        buf += bytes((pb * pa // 255, pg * pa // 255, pr * pa // 255, pa))
    ctypes.memmove(bits, bytes(buf), len(buf))
    _PASTILLE_BMP[color] = hbmp
    return hbmp


def _install_pastille_patch(log_fn=None) -> None:
    """Ajoute hbmpItem aux items qui ont l'attribut _pastille (callable -> 'vert'/'jaune')."""
    if sys.platform != "win32":
        return
    try:
        import pystray._win32 as pw
        if getattr(pw.Icon, "_padawan_pastille", False):
            return
        orig = pw.Icon._create_menu_item

        def _cmi(self, descriptor, callbacks):
            mi = orig(self, descriptor, callbacks)
            fn = getattr(descriptor, "_pastille", None)
            if fn:
                try:
                    mi.fMask |= 0x00000080  # MIIM_BITMAP
                    mi.hbmpItem = _pastille_hbitmap(fn())
                except Exception as e:
                    (log_fn or _noop_log)(f"pastille: {e}")
            return mi
        pw.Icon._create_menu_item = _cmi
        pw.Icon._padawan_pastille = True
    except Exception as e:
        (log_fn or _noop_log)(f"pastille patch: {e}")


def launch_facteur(
    base: str,
    *,
    say: Optional[Callable[[str, str], None]] = None,
    app_name: str = "Padawan",
    parent: Any = None,
    log_fn: Optional[Callable[[str], None]] = None,
    cache: bool = False,
) -> None:
    """Lance Facteur (facteur1.py). Instance unique ; --cache = demarrage masque (moteur actif)."""
    log = log_fn or _noop_log

    def _say(who: str, msg: str) -> None:
        if say:
            try:
                say(who, msg)
            except Exception:
                pass

    fc = None
    for root in (base, TRAY_DIR):
        cand = os.path.join(root, "facteur1.py")
        if os.path.isfile(cand):
            fc, base = cand, root
            break
    if not fc:
        expected = os.path.join(base, "facteur1.py")
        _say("sys", f"Facteur introuvable: {expected}")
        try:
            from tkinter import messagebox
            messagebox.showwarning(
                app_name,
                "Facteur introuvable.\n\n"
                f"Attendu:\n{expected}\n\n"
                "Place facteur1.py à côté de Padawan.",
                parent=parent,
            )
        except Exception:
            pass
        return
    try:
        exe = _python_launcher()
        args = [exe, fc]
        if cache:
            args.append("--cache")
        kwargs: Dict[str, Any] = {
            "cwd": base,
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "close_fds": True,
        }
        if sys.platform.startswith("win"):
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen(args, **kwargs)
        _say("sys", "Facteur lancé" + (" (cache)" if cache else "") + ".")
    except Exception as e:
        log(f"launch facteur: {e}")
        _say("sys", f"Erreur lancement Facteur: {e}")



def launch_messager(
    base: str,
    *,
    say: Optional[Callable] = None,
    app_name: str = "Padawan",
    parent: Any = None,
    log_fn: Optional[Callable[[str], None]] = None,
) -> None:
    """Lance Messager (messager2.py, sinon messager1.py) via pythonw / CREATE_NO_WINDOW. Instance unique."""
    _say = say or (lambda *a, **k: None)
    log = log_fn or _noop_log
    expected = os.path.join(base, "messager2.py")
    path = None
    for name in ("messager2.py", "messager1.py"):
        for root in (base, TRAY_DIR):
            cand = os.path.join(root, name)
            if os.path.isfile(cand):
                path = cand
                break
        if path:
            break
    if not path:
        _say("sys", f"Messager introuvable: {expected}")
        try:
            from tkinter import messagebox
            messagebox.showerror(
                app_name,
                "Messager introuvable.\n\nPlace messager2.py à côté de Padawan.",
                parent=parent,
            )
        except Exception:
            pass
        return
    try:
        exe = _python_launcher()
        kwargs = {"cwd": os.path.dirname(path)}
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen([exe, path], **kwargs)
        _say("sys", "Messager lancé.")
    except Exception as e:
        log(f"launch messager: {e}")
        _say("sys", f"Erreur lancement Messager: {e}")

def launch_padawan_app(
    base: str,
    script: str,
    label: str,
    *,
    say: Optional[Callable] = None,
    app_name: str = "Padawan",
    parent: Any = None,
    log_fn: Optional[Callable[[str], None]] = None,
) -> None:
    """Lance un programme de la suite (ex. chantier1.py, retro1.py) via pythonw / CREATE_NO_WINDOW."""
    _say = say or (lambda *a, **k: None)
    log = log_fn or _noop_log
    path = None
    for root in (base, TRAY_DIR):
        cand = os.path.join(root, script)
        if os.path.isfile(cand):
            path = cand
            break
    if not path:
        _say("sys", f"{label} introuvable: {os.path.join(base, script)}")
        try:
            from tkinter import messagebox
            messagebox.showerror(app_name, f"{label} introuvable.\n\nPlace {script} \u00e0 c\u00f4t\u00e9 de Padawan.", parent=parent)
        except Exception:
            pass
        return
    try:
        exe = _python_launcher()
        kwargs = {"cwd": os.path.dirname(path)}
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen([exe, path], **kwargs)
        _say("sys", f"{label} lanc\u00e9.")
    except Exception as e:
        log(f"launch {script}: {e}")
        _say("sys", f"Erreur lancement {label}: {e}")

def setup_tray(
    app: Any,
    *,
    app_name: str = "Padawan",
    log_fn: Optional[Callable[[str], None]] = None,
) -> bool:
    """
    Configure le menu tray pystray sur l'app Tk.
    Menu SANS default=True : clic gauche ouvre le menu.
    Attendu sur app: after0, show_from_tray, hide_to_tray, quit_padawan,
    set_start_with_windows, launch_file_manager, launch_archiveur (opt), cfg, say ; attrs _tray_icon/_tray_thread.
    """
    log = log_fn or _noop_log
    if not TRAY_AVAILABLE:
        try:
            app.say("sys", "Tray indisponible (pip install pystray pillow). X = quitter.")
        except Exception:
            pass
        return False
    try:
        img = make_tray_image(64)
        if img is None:
            return False

        def on_show(icon=None, item=None):
            app.after0(app.show_from_tray)

        def on_hide(icon=None, item=None):
            app.after0(app.hide_to_tray)

        def on_quit(icon=None, item=None):
            app.after0(app.quit_padawan)

        def on_toggle_startup(icon=None, item=None):
            cur = bool(app.cfg.get("start_with_windows", True))
            app.after0(app.set_start_with_windows, not cur)

        def startup_checked(item=None):
            return is_windows_startup_enabled()

        def on_file_manager(icon=None, item=None):
            app.after0(app.launch_file_manager)

        def on_archiveur(icon=None, item=None):
            def _go():
                if hasattr(app, "launch_archiveur"):
                    app.launch_archiveur()
                else:
                    # compat padawan38: lance depuis le dossier du tray
                    base = TRAY_DIR
                    try:
                        import __main__
                        mf = getattr(__main__, "__file__", None)
                        if mf:
                            base = os.path.dirname(os.path.abspath(mf))
                    except Exception:
                        pass
                    launch_archiveur(
                        base,
                        say=getattr(app, "say", None),
                        app_name=app_name,
                        parent=app,
                        log_fn=log,
                    )
            app.after0(_go)

        def on_arsenal(icon=None, item=None):
            def _go():
                base = TRAY_DIR
                try:
                    import __main__
                    mf = getattr(__main__, "__file__", None)
                    if mf:
                        base = os.path.dirname(os.path.abspath(mf))
                except Exception:
                    pass
                launch_arsenal(
                    base,
                    say=getattr(app, "say", None),
                    app_name=app_name,
                    parent=app,
                    log_fn=log,
                )
            app.after0(_go)


        def on_facteur(icon=None, item=None):
            def _go():
                base = TRAY_DIR
                try:
                    import __main__
                    mf = getattr(__main__, "__file__", None)
                    if mf:
                        base = os.path.dirname(os.path.abspath(mf))
                except Exception:
                    pass
                launch_facteur(
                    base,
                    say=getattr(app, "say", None),
                    app_name=app_name,
                    parent=app,
                    log_fn=log,
                    cache=False,
                )
            app.after0(_go)

        def _facteur_py():
            base = TRAY_DIR
            try:
                import __main__
                mf = getattr(__main__, "__file__", None)
                if mf:
                    base = os.path.dirname(os.path.abspath(mf))
            except Exception:
                pass
            for root in (base, TRAY_DIR):
                if os.path.isfile(os.path.join(root, "facteur1.py")):
                    return os.path.join(root, "facteur1.py")
            return os.path.join(base, "facteur1.py")

        def on_toggle_facteur_startup(icon=None, item=None):
            """Bascule actif/passif : demarre/arrete Facteur + ajoute/retire le demarrage auto."""
            def _go():
                fp = _facteur_py()
                new = not is_facteur_running()
                set_facteur_startup(new, fp, log)
                if new:
                    launch_facteur(os.path.dirname(fp), say=getattr(app, "say", None), app_name=app_name,
                                   parent=app, log_fn=log, cache=True)
                else:
                    stop_facteur(log)
                time.sleep(2.0)
                try:
                    app._tray_icon.update_menu()
                except Exception:
                    pass
                try:
                    app.say("sys", "Facteur : " + ("actif (d\u00e9marre avec Windows)" if new else "passif (arr\u00eat\u00e9, pas au d\u00e9marrage)"))
                except Exception:
                    pass
            threading.Thread(target=_go, daemon=True).start()

        def facteur_startup_checked(item=None):
            return is_facteur_startup_enabled()

        def on_messager(icon=None, item=None):
            def _go():
                base = TRAY_DIR
                try:
                    import __main__
                    mf = getattr(__main__, "__file__", None)
                    if mf:
                        base = os.path.dirname(os.path.abspath(mf))
                except Exception:
                    pass
                launch_messager(
                    base,
                    say=getattr(app, "say", None),
                    app_name=app_name,
                    parent=app,
                    log_fn=log,
                )
            app.after0(_go)
        def on_grimoire(icon=None, item=None):
            def _go():
                base = TRAY_DIR
                try:
                    import __main__
                    mf = getattr(__main__, "__file__", None)
                    if mf:
                        base = os.path.dirname(os.path.abspath(mf))
                except Exception:
                    pass
                launch_grimoire(
                    base,
                    say=getattr(app, "say", None),
                    app_name=app_name,
                    parent=app,
                    log_fn=log,
                )
            app.after0(_go)

        def _suite_app(script, label):
            def _h(icon=None, item=None):
                def _go():
                    base = TRAY_DIR
                    try:
                        import __main__
                        mf = getattr(__main__, "__file__", None)
                        if mf:
                            base = os.path.dirname(os.path.abspath(mf))
                    except Exception:
                        pass
                    launch_padawan_app(base, script, label, say=getattr(app, "say", None),
                                       app_name=app_name, parent=app, log_fn=log)
                app.after0(_go)
            return _h
        on_chantier = _suite_app("chantier1.py", "Chantier")
        on_retro = _suite_app("retro1.py", "R\u00e9tro")
        on_tableau = _suite_app("tableau_bord.py", "Tableau de bord")
        on_premiers = _suite_app("premiers_pas.py", "Premiers pas")
        on_recherche = _suite_app("recherche_padawan.py", "Recherche Padawan")
        on_coffre = _suite_app("coffre_padawan.py", "Coffre Padawan")
        on_journal = _suite_app("journal_bord.py", "Journal de bord")

        def on_journal_coller(icon=None, item=None):  # presse-papiers -> entree du jour, sans grande fenetre
            def _go():
                try:
                    p = os.path.join(TRAY_DIR, "journal_bord.py")
                    kw = {"cwd": TRAY_DIR}
                    if os.name == "nt":
                        kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                    subprocess.Popen([_python_launcher(), p, "--coller"], **kw)
                except Exception as e:
                    log(f"journal coller: {e}")
            threading.Thread(target=_go, daemon=True).start()

        def _open_web(url):
            def _h(icon=None, item=None):
                def _go():
                    try:
                        import webbrowser
                        webbrowser.open(url, new=2)
                    except Exception as e:
                        log(f"lien web: {e}")
                threading.Thread(target=_go, daemon=True).start()
            return _h
        _gh = "https://github.com/marcsevigny1971/padawan-suite"
        ressources_menu = pystray.Menu(
            TrayMenuItem("\U0001f3e0 Page du projet (GitHub)", _open_web(_gh)),
            TrayMenuItem("\u2b06 Mises \u00e0 jour (derni\u00e8re version)", _open_web(_gh + "/releases/latest")),
            TrayMenuItem("\U0001f4a1 Id\u00e9es et suggestions", _open_web(_gh + "/issues")),
            TrayMenuItem("\u2728 Pr\u00e9sentation compl\u00e8te", _open_web("https://marcsevigny1971.github.io/padawan-suite/")),
        )

        _install_pastille_patch(log)
        _fac_item = TrayMenuItem(
            lambda item: "Facteur : actif (clic = passif)" if is_facteur_running()
            else "Facteur : passif (clic = actif)",
            on_toggle_facteur_startup)
        try:
            object.__setattr__(_fac_item, "_pastille", lambda: "vert" if is_facteur_running() else "jaune")
        except Exception as e:
            log(f"pastille attr: {e}")

        menu = pystray.Menu(
            TrayMenuItem("Padawan — Ouvrir / Afficher", on_show),
            TrayMenuItem("Padawan — Masquer", on_hide),
            pystray.Menu.SEPARATOR,
            TrayMenuItem("\U0001f9ed Tableau de bord de la suite\u2026", on_tableau),
            TrayMenuItem("\U0001f680 Premiers pas (guide 5 min)\u2026", on_premiers),
            TrayMenuItem("\U0001f50e Recherche Padawan (Ctrl+Alt+R)\u2026", on_recherche),
            TrayMenuItem("\U0001f4d3 Journal de bord (Ctrl+Alt+J)\u2026", on_journal),
            TrayMenuItem("\U0001f4cb Coller dans le journal (Ctrl+Alt+K)", on_journal_coller),
            TrayMenuItem("\U0001f5c4 Coffre Padawan (sauvegarde)\u2026", on_coffre),
            TrayMenuItem("Gestionnaire de fichiers…", on_file_manager),
            TrayMenuItem("Archiveur…", on_archiveur),
            TrayMenuItem("Arsenal…", on_arsenal),
            TrayMenuItem("Grimoire…", on_grimoire),
            TrayMenuItem("Messager…", on_messager),
            TrayMenuItem("Chantier (serveurs)\u2026", on_chantier),
            TrayMenuItem("R\u00e9tro (C64 / DOS / Win98)\u2026", on_retro),
            TrayMenuItem("Facteur…", on_facteur),
            _fac_item,
            pystray.Menu.SEPARATOR,
            TrayMenuItem("\U0001f4da Ressources / GitHub", ressources_menu),
            pystray.Menu.SEPARATOR,
            TrayMenuItem("Démarrer avec Windows", on_toggle_startup, checked=startup_checked),
            pystray.Menu.SEPARATOR,
            TrayMenuItem("Quitter Padawan", on_quit),
        )
        app._tray_icon = pystray.Icon(app_name, img, app_name, menu)

        def run_tray():
            try:
                app._tray_icon.run()
            except Exception as e:
                log(f"tray run: {e}")

        app._tray_thread = threading.Thread(target=run_tray, daemon=True)
        app._tray_thread.start()

        def _refresh_pastille():  # suit l'etat reel de Facteur (vert/jaune)
            last = None
            while True:
                time.sleep(4)
                cur = is_facteur_running()
                if cur != last:
                    last = cur
                    try:
                        app._tray_icon.update_menu()
                    except Exception:
                        pass
        threading.Thread(target=_refresh_pastille, daemon=True).start()

        def _premiers_pas_auto():  # guide au 1er lancement (premiers_pas.py --auto sort tout seul si deja vu)
            try:
                time.sleep(6)
                pp = os.path.join(TRAY_DIR, "premiers_pas.py")
                if os.path.isfile(pp):
                    subprocess.Popen([_python_launcher(), pp, "--auto"], cwd=TRAY_DIR,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except Exception as e:
                log(f"premiers pas: {e}")
        threading.Thread(target=_premiers_pas_auto, daemon=True).start()

        # Démarre Facteur en arrière-plan (--cache) : une seule icône Padawan
        def _start_facteur_cache():
            try:
                base = TRAY_DIR
                try:
                    import __main__
                    mf = getattr(__main__, "__file__", None)
                    if mf:
                        base = os.path.dirname(os.path.abspath(mf))
                except Exception:
                    pass
                fp = _facteur_py()
                ensure_facteur_startup_default(fp, log)
                # pas de doublon : deja lance par la cle Run ou ailleurs ; respecte le choix OFF
                if is_facteur_running() or os.path.isfile(_facteur_off_flag()):
                    return
                launch_facteur(os.path.dirname(fp), say=getattr(app, "say", None), app_name=app_name,
                               parent=app, log_fn=log, cache=True)
            except Exception as e:
                log(f"auto Facteur: {e}")
        try:
            app.after0(_start_facteur_cache)
        except Exception:
            threading.Thread(target=_start_facteur_cache, daemon=True).start()

        try:
            app.say(
                "sys",
                "System tray prêt — clic icône = menu (Padawan / Gestionnaire / Archiveur / Arsenal / Grimoire / Facteur); X masque.",
            )
        except Exception:
            pass
        return True
    except Exception as e:
        log(f"tray setup: {e}")
        try:
            app.say("sys", f"Tray erreur: {e}")
        except Exception:
            pass
        return False


def show_from_tray(app: Any) -> None:
    """Réaffiche la fenêtre principale depuis le tray."""
    log = getattr(app, "_tray_log", _noop_log)
    try:
        app.deiconify()
        app.lift()
        if app.cfg.get("fullscreen", True):
            try:
                app.state("zoomed")
            except Exception:
                pass
        app.focus_force()
        try:
            app.ent.focus_set()
        except Exception:
            pass
    except Exception as e:
        try:
            log(f"show tray: {e}")
        except Exception:
            pass


def hide_to_tray(app: Any, *, app_name: str = "Padawan") -> None:
    """Masque la fenêtre vers le tray (notification)."""
    log = getattr(app, "_tray_log", _noop_log)
    try:
        if hasattr(app, "_persist_cfg"):
            app._persist_cfg(light=True)
        app.withdraw()
        icon = getattr(app, "_tray_icon", None)
        if icon is not None:
            try:
                icon.notify(f"{app_name} est dans la barre système.", app_name)
            except Exception:
                pass
    except Exception as e:
        try:
            log(f"hide tray: {e}")
        except Exception:
            pass


def stop_tray(app: Any) -> None:
    """Arrête l'icône tray (appelé depuis quit_padawan)."""
    icon = getattr(app, "_tray_icon", None)
    app._tray_icon = None
    if icon is not None:
        try:
            icon.stop()
        except Exception:
            pass


__all__ = [
    "TRAY_AVAILABLE",
    "TRAY_DIR",
    "STARTUP_REG_NAME",
    "STARTUP_BAT_NAME",
    "STARTUP_LNK_NAME",
    "make_tray_image",
    "_python_launcher",
    "windows_startup_dir",
    "windows_startup_paths",
    "ensure_windows_startup",
    "is_windows_startup_enabled",
    "acquire_single_instance",
    "launch_file_manager",
    "launch_archiveur",
    "launch_arsenal",
    "launch_grimoire",
    "launch_padawan_app",
    "launch_facteur",
    "is_facteur_startup_enabled",
    "set_facteur_startup",
    "is_facteur_running",
    "setup_tray",
    "show_from_tray",
    "hide_to_tray",
    "stop_tray",
]
