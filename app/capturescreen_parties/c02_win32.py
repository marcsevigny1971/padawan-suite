# -*- coding: utf-8 -*-
"""CaptureScreen - c02 : outils Windows (ctypes) : DPI, moniteurs, fenetres, raccourcis globaux,
fenetres « traversables », exclusion de capture (pour NOS barres d'outils seulement), corbeille, presse-papiers.
Aucun enregistrement de frappe : l'etat des touches n'est lu que pour la bulle a l'ecran, jamais ecrit."""
from __future__ import annotations

import ctypes
import os
import queue
import subprocess
import threading

IS_WIN = os.name == "nt"
if IS_WIN:
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    dwmapi = ctypes.windll.dwmapi
    kernel32 = ctypes.windll.kernel32
    user32.GetWindowLongW.restype = ctypes.c_long
    user32.SetWindowLongW.restype = ctypes.c_long


def set_dpi_aware() -> None:
    """Pixels physiques partout (Tk = ffmpeg = PIL), meme avec Windows a 125/150 %."""
    if not IS_WIN:
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


def even(v: int) -> int:
    return int(v) - (int(v) % 2)


# ------------------------------------------------------------------ moniteurs
def monitors():
    """[{x, y, w, h, primary, name}] (pixels physiques), principal en premier."""
    out = []
    if not IS_WIN:
        return [{"x": 0, "y": 0, "w": 1920, "h": 1080, "primary": True, "name": "Écran"}]

    class MONITORINFOEXW(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                    ("dwFlags", wintypes.DWORD), ("szDevice", wintypes.WCHAR * 32)]

    PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)

    def cb(hmon, hdc, rect, lp):
        mi = MONITORINFOEXW()
        mi.cbSize = ctypes.sizeof(MONITORINFOEXW)
        if user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            r = mi.rcMonitor
            out.append({"x": r.left, "y": r.top, "w": r.right - r.left, "h": r.bottom - r.top,
                        "primary": bool(mi.dwFlags & 1), "name": mi.szDevice.replace("\\\\.\\", "")})
        return True

    try:
        user32.EnumDisplayMonitors(None, None, PROC(cb), 0)
    except Exception:
        pass
    if not out:
        out = [{"x": 0, "y": 0, "w": user32.GetSystemMetrics(0), "h": user32.GetSystemMetrics(1), "primary": True, "name": "Écran"}]
    out.sort(key=lambda m: (not m["primary"], m["x"], m["y"]))
    for i, m in enumerate(out):
        m["label"] = f"Moniteur {i + 1}{' (principal)' if m['primary'] else ''} — {m['w']}×{m['h']}"
    return out


def virtual_screen():
    if not IS_WIN:
        return (0, 0, 1920, 1080)
    return (user32.GetSystemMetrics(76), user32.GetSystemMetrics(77), user32.GetSystemMetrics(78), user32.GetSystemMetrics(79))


def monitor_of_point(x, y):
    for i, m in enumerate(monitors()):
        if m["x"] <= x < m["x"] + m["w"] and m["y"] <= y < m["y"] + m["h"]:
            return i, m
    ms = monitors()
    return 0, ms[0]


# ------------------------------------------------------------------ fenetres
def window_rect(hwnd):
    """Rectangle visible (sans l'ombre) d'une fenetre : (x, y, w, h)."""
    r = wintypes.RECT()
    try:
        if dwmapi.DwmGetWindowAttribute(wintypes.HWND(hwnd), 9, ctypes.byref(r), ctypes.sizeof(r)) == 0:
            return (r.left, r.top, r.right - r.left, r.bottom - r.top)
    except Exception:
        pass
    user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(r))
    return (r.left, r.top, r.right - r.left, r.bottom - r.top)


def windows_list(skip_pid=None):
    """Fenetres visibles avec un titre : [(hwnd, titre, (x, y, w, h))]."""
    if not IS_WIN:
        return []
    res = []
    PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(hwnd, lp):
        try:
            if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
                return True
            n = user32.GetWindowTextLengthW(hwnd)
            if n <= 0:
                return True
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            title = buf.value.strip()
            cloaked = ctypes.c_int(0)
            dwmapi.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
            if cloaked.value or not title or title in ("Program Manager",):
                return True
            ex = user32.GetWindowLongW(hwnd, -20)
            if ex & 0x80:  # WS_EX_TOOLWINDOW
                return True
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if skip_pid and pid.value == skip_pid:
                return True
            x, y, w, h = window_rect(hwnd)
            if w >= 80 and h >= 60:
                res.append((int(hwnd), title, (x, y, w, h)))
        except Exception:
            pass
        return True

    user32.EnumWindows(PROC(cb), 0)
    return res


def find_window(title_part: str):
    t = (title_part or "").lower()
    for hwnd, title, rect in windows_list():
        if t and t in title.lower():
            return hwnd, title, rect
    return None


def bring_to_front(hwnd) -> None:
    try:
        user32.ShowWindow(hwnd, 9)
        user32.SetForegroundWindow(hwnd)
    except Exception:
        pass


def tk_hwnd(win) -> int:
    """HWND de la fenetre Windows d'un Toplevel Tk."""
    try:
        return int(win.wm_frame(), 16)
    except Exception:
        try:
            return user32.GetParent(win.winfo_id())
        except Exception:
            return 0


def click_through(win, on=True) -> None:
    """La souris traverse la fenetre (superpositions : halo, projecteur, encre)."""
    if not IS_WIN:
        return
    try:
        win.update_idletasks()
        h = tk_hwnd(win)
        ex = user32.GetWindowLongW(h, -20)
        flags = 0x80000 | 0x20 | 0x80 | 0x08000000  # LAYERED | TRANSPARENT | TOOLWINDOW | NOACTIVATE
        ex = (ex | flags) if on else (ex & ~0x20)
        user32.SetWindowLongW(h, -20, ex)
    except Exception:
        pass


def no_activate(win) -> None:
    """Fenetre outil qui ne vole pas le focus (barre flottante, palette)."""
    if not IS_WIN:
        return
    try:
        win.update_idletasks()
        h = tk_hwnd(win)
        user32.SetWindowLongW(h, -20, user32.GetWindowLongW(h, -20) | 0x80 | 0x08000000)
    except Exception:
        pass


def exclude_from_capture(win, on=True) -> bool:
    """Cache NOS propres barres d'outils dans la video (WDA_EXCLUDEFROMCAPTURE, Windows 10 2004+).
    Ne touche a aucune autre fenetre."""
    if not IS_WIN:
        return False
    try:
        win.update_idletasks()
        return bool(user32.SetWindowDisplayAffinity(tk_hwnd(win), 0x11 if on else 0))
    except Exception:
        return False


def cursor_pos():
    if not IS_WIN:
        return (0, 0)
    p = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(p))
    return (p.x, p.y)


# ------------------------------------------------------------------ etat clavier / souris (lecture instantanee, rien n'est ecrit)
VK_NAMES = {0x08: "Retour", 0x09: "Tab", 0x0D: "Entrée", 0x13: "Pause", 0x14: "Verr. Maj", 0x1B: "Échap", 0x20: "Espace",
            0x21: "Pg préc.", 0x22: "Pg suiv.", 0x23: "Fin", 0x24: "Début", 0x25: "\u2190", 0x26: "\u2191", 0x27: "\u2192",
            0x28: "\u2193", 0x2C: "Impr. écran", 0x2D: "Inser", 0x2E: "Suppr", 0x6A: "*", 0x6B: "+", 0x6D: "-", 0x6E: ".",
            0x6F: "/", 0xBA: ";", 0xBB: "=", 0xBC: ",", 0xBD: "-", 0xBE: ".", 0xBF: "/", 0xC0: "`", 0xDB: "[", 0xDC: "\\",
            0xDD: "]", 0xDE: "'"}
MODS = {0x11: "Ctrl", 0x12: "Alt", 0x10: "Maj", 0x5B: "Win", 0x5C: "Win"}
SPECIAL = set(VK_NAMES) - set(range(0x30, 0x5B)) - {0x6A, 0x6B, 0x6D, 0x6E, 0x6F, 0xBA, 0xBB, 0xBC, 0xBD, 0xBE, 0xBF, 0xC0,
                                                      0xDB, 0xDC, 0xDD, 0xDE, 0x20}


def vk_name(vk: int) -> str:
    if 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:
        return chr(vk)
    if 0x60 <= vk <= 0x69:
        return f"Pavé {vk - 0x60}"
    if 0x70 <= vk <= 0x87:
        return f"F{vk - 0x6F}"
    return VK_NAMES.get(vk, "")


def keys_down():
    """Ensemble des touches enfoncees en ce moment (codes VK), sans les boutons de souris."""
    if not IS_WIN:
        return set()
    gs = user32.GetAsyncKeyState
    out = set()
    for vk in list(range(0x08, 0x5D)) + list(range(0x60, 0x88)) + list(range(0xBA, 0xC1)) + list(range(0xDB, 0xDF)):
        if vk in (0x10, 0x11, 0x12) or vk in MODS or vk_name(vk):
            if gs(vk) & 0x8000:
                out.add(vk)
    out.discard(0xA0); out.discard(0xA1)
    return out


def mouse_buttons():
    """(gauche, droit, milieu) enfonces maintenant (boutons inverses de Windows respectes)."""
    if not IS_WIN:
        return (False, False, False)
    gs = user32.GetAsyncKeyState
    l, r = bool(gs(0x01) & 0x8000), bool(gs(0x02) & 0x8000)
    if user32.GetSystemMetrics(23):  # SM_SWAPBUTTON
        l, r = r, l
    return (l, r, bool(gs(0x04) & 0x8000))


# ------------------------------------------------------------------ raccourcis globaux
class GlobalHotkeys:
    """RegisterHotKey dans un fil a part ; les actions arrivent dans une file lue par Tk (after)."""

    def __init__(self):
        self.q = queue.Queue()
        self.ok, self.failed = [], []
        self._tid = None
        self._th = None

    def start(self, combos):
        """combos : [(nom, mods_texte 'ctrl+shift', touche 'R')]"""
        if not IS_WIN:
            return
        ready = threading.Event()

        def run():
            self._tid = kernel32.GetCurrentThreadId()
            for i, (name, mods, key) in enumerate(combos, 1):
                m = 0x4000  # MOD_NOREPEAT
                for part in mods.lower().split("+"):
                    m |= {"alt": 1, "ctrl": 2, "shift": 4, "win": 8}.get(part, 0)
                if user32.RegisterHotKey(None, i, m, ord(key.upper())):
                    self.ok.append(name)
                else:
                    self.failed.append(name)
            ready.set()
            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == 0x0312:  # WM_HOTKEY
                    i = int(msg.wParam)
                    if 1 <= i <= len(combos):
                        self.q.put(combos[i - 1][0])
            for i in range(1, len(combos) + 1):
                user32.UnregisterHotKey(None, i)

        self._th = threading.Thread(target=run, daemon=True)
        self._th.start()
        ready.wait(3)

    def stop(self):
        if IS_WIN and self._tid:
            user32.PostThreadMessageW(self._tid, 0x0012, 0, 0)  # WM_QUIT
            self._tid = None
            if self._th is not None:  # attendre la liberation des touches avant d'en reprendre d'autres
                self._th.join(1.5)


# ------------------------------------------------------------------ instance unique
_MUTEX = None


def single_instance(name="Local\\CaptureScreen_SingleInstance") -> bool:
    global _MUTEX
    if not IS_WIN:
        return True
    _MUTEX = kernel32.CreateMutexW(None, False, name)
    return kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


def front_existing(title="CaptureScreen") -> bool:
    if not IS_WIN:
        return False
    h = user32.FindWindowW(None, title)
    if h:
        bring_to_front(h)
        return True
    return False


# ------------------------------------------------------------------ fichiers
def recycle(path: str) -> bool:
    """Envoie a la Corbeille (recuperable), jamais de suppression definitive."""
    if not IS_WIN:
        return False

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("wFunc", ctypes.c_uint), ("pFrom", wintypes.LPCWSTR),
                    ("pTo", wintypes.LPCWSTR), ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", wintypes.BOOL),
                    ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", wintypes.LPCWSTR)]

    op = SHFILEOPSTRUCTW()
    op.wFunc = 3  # FO_DELETE
    op.pFrom = os.path.abspath(path) + "\0\0"
    op.fFlags = 0x40 | 0x10 | 0x04 | 0x400  # ALLOWUNDO | NOCONFIRMATION | SILENT | NOERRORUI
    try:
        return ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op)) == 0 and not os.path.exists(path)
    except Exception:
        return False


def copy_image_to_clipboard(img) -> bool:
    try:
        import io
        import win32clipboard  # pywin32
        bio = io.BytesIO()
        img.convert("RGB").save(bio, "BMP")
        data = bio.getvalue()[14:]
        win32clipboard.OpenClipboard()
        try:
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
        finally:
            win32clipboard.CloseClipboard()
        return True
    except Exception:
        return False


def open_path(p) -> None:
    try:
        os.startfile(p)  # type: ignore[attr-defined]
    except Exception:
        pass


def reveal(p) -> None:
    try:
        if os.path.isfile(p):
            subprocess.Popen(["explorer", "/select,", os.path.normpath(p)])
        else:
            os.startfile(p if os.path.isdir(p) else os.path.dirname(p))  # type: ignore[attr-defined]
    except Exception:
        pass
