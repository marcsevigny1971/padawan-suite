# -*- coding: utf-8 -*-
"""padawan_ansi.py — 🖼→ANSI : convertisseur d'images en art ANSI / ASCII (Padawan v40.1, Atelier).

100 % local, en Python. Pillow sert à lire l'image ; s'il manque, la fenêtre propose « pip install pillow »
(avec confirmation, par l'Atelier). Rien d'autre n'est téléchargé.

Styles : 16 couleurs DOS (demi-blocs ▀▄, 2 pixels par caractère) · 24 bits truecolor (demi-blocs) ·
ASCII monochrome (rampe de caractères) · Pip-Boy vert · ombres ░▒▓█ en couleur.
Sorties : ANSI (codes d'échappement), texte simple, .ans (CP437 + SAUCE facultatif), .txt, page HTML rétro,
code Python prêt à print().

Pour les jeux (plus tard) :  art = image_to_ansi("image.png", width=60, style="dos16")
                             art.to_ansi(), art.to_text(), art.to_html(), render_tk(text_widget, art)
"""
from __future__ import annotations

import io
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import tkinter as tk
from tkinter import filedialog, messagebox
import tkinter.font as tkfont

VERSION = "1.1"
IS_WIN = os.name == "nt"
IMG_EXT = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp")

Image = ImageEnhance = ImageOps = ImageGrab = ImageTk = ImageDraw = ImageFont = None  # type: ignore


def load_pil() -> bool:
    """Charge Pillow si présent (peut être rappelé après un pip install)."""
    global Image, ImageEnhance, ImageOps, ImageGrab, ImageTk, ImageDraw, ImageFont
    if Image is not None:
        return True
    try:
        import importlib
        importlib.invalidate_caches()
        from PIL import Image as _I, ImageEnhance as _E, ImageOps as _O  # type: ignore
        Image, ImageEnhance, ImageOps = _I, _E, _O
        from PIL import ImageDraw as _D, ImageFont as _F  # type: ignore
        ImageDraw, ImageFont = _D, _F
        try:
            from PIL import ImageTk as _T  # type: ignore
            ImageTk = _T
        except Exception:
            ImageTk = None
        try:
            from PIL import ImageGrab as _G  # type: ignore
            ImageGrab = _G
        except Exception:
            ImageGrab = None
        return True
    except Exception:
        return False


load_pil()

try:  # accélère seulement le style ░▒▓█ (facultatif)
    import numpy as _np  # type: ignore
except Exception:  # pragma: no cover
    _np = None

RGB = Tuple[int, int, int]

# Palette VGA/DOS (ordre DOS 0-15) et correspondance vers les codes ANSI 30-37
DOS16: List[RGB] = [(0, 0, 0), (0, 0, 170), (0, 170, 0), (0, 170, 170), (170, 0, 0), (170, 0, 170), (170, 85, 0),
                    (170, 170, 170), (85, 85, 85), (85, 85, 255), (85, 255, 85), (85, 255, 255), (255, 85, 85),
                    (255, 85, 255), (255, 255, 85), (255, 255, 255)]
DOS2ANSI = [0, 4, 2, 6, 1, 5, 3, 7]
_DOS_IDX = {c: i for i, c in enumerate(DOS16)}
PIP: List[RGB] = [(0, 0, 0), (6, 40, 14), (12, 82, 30), (20, 128, 48), (30, 178, 68), (48, 222, 92), (120, 255, 150)]
# v1.1 « film noir » : 8 gris + quelques accents (néon rouge, ambre de lampe) gardés seulement là où l'image est saturée
NOIR_GRAYS: List[RGB] = [(0, 0, 0), (22, 22, 24), (48, 48, 52), (80, 80, 84), (116, 116, 120), (156, 156, 158),
                         (200, 200, 200), (245, 245, 240)]
NOIR_ACCENTS: List[RGB] = [(110, 14, 18), (200, 30, 36), (255, 70, 60), (190, 110, 30), (240, 170, 60), (255, 225, 140)]
ASCII_RAMP = " .:-=+*#%@"
SHADES = (("░", 0.25), ("▒", 0.5), ("▓", 0.75))

STYLES = [("dos16", "🟦 ANSI 16 couleurs DOS  (▀▄)"),
          ("truecolor", "🌈 Truecolor 24 bits  (▀▄)"),
          ("ascii", "🔤 ASCII monochrome"),
          ("pipboy", "📟 Pip-Boy vert"),
          ("shades", "▒ Ombres ░▒▓█ (16 couleurs)"),
          ("noir", "🕵 Film noir (gris + accents)")]
STYLE_IDS = [s for s, _ in STYLES]
PALETTE_STYLES = ("dos16", "shades")       # 16 couleurs exactes
DEFAULT_FG: RGB = (192, 192, 192)
DEFAULT_BG: RGB = (0, 0, 0)

Cell = Tuple[str, Optional[RGB], Optional[RGB]]


def _hex(c: RGB) -> str:
    return "#%02x%02x%02x" % c


def _d2(a: RGB, b: RGB) -> int:
    return 2 * (a[0] - b[0]) ** 2 + 4 * (a[1] - b[1]) ** 2 + 3 * (a[2] - b[2]) ** 2


_near_cache: Dict[Tuple[RGB, Tuple[int, ...]], int] = {}


def nearest16(c: RGB, allowed: Sequence[int] = tuple(range(16))) -> int:
    k = (c, tuple(allowed))
    r = _near_cache.get(k)
    if r is None:
        r = min(allowed, key=lambda i: _d2(c, DOS16[i]))
        if len(_near_cache) > 50000:
            _near_cache.clear()
        _near_cache[k] = r
    return r


# ───────────────────────────────────────────────────────────────── l'art ──
class Art:
    """Grille de cellules (caractère, couleur du texte, couleur du fond) ; None = couleur par défaut."""

    def __init__(self, rows: List[List[Cell]], style: str, title: str = ""):
        self.rows, self.style, self.title = rows, style, title
        self.cols = max((len(r) for r in rows), default=0)
        self.nrows = len(rows)
        self.ms = 0.0

    # texte simple (les caractères seulement)
    def to_text(self) -> str:
        return "\n".join("".join(c[0] for c in r).rstrip() for r in self.rows) + "\n"

    def _pal(self) -> bool:
        return self.style in PALETTE_STYLES

    def _allowed(self) -> Sequence[int]:
        return (0, 2, 8, 10, 15) if self.style == "pipboy" else tuple(range(16))

    def to_ansi(self, mode: str = "vt") -> str:
        """mode « vt » : console Windows / terminal (16 couleurs 30-37/90-97 ou 24 bits) ;
        mode « dos » : ANSI.SYS / fichiers .ans (16 couleurs, gras = clair, clignotant = fond clair iCE)."""
        if self.style == "ascii":
            return self.to_text()
        out: List[str] = []
        pal, allowed = self._pal() or mode == "dos", self._allowed()
        for r in self.rows:
            cur = None
            line: List[str] = []
            for ch, fg, bg in r:
                key = (fg, bg)
                if key != cur:
                    line.append(self._sgr(fg, bg, mode, pal, allowed))
                    cur = key
                line.append(ch)
            line.append("\x1b[0m")
            out.append("".join(line))
        return ("\r\n" if mode == "dos" else "\n").join(out) + ("\r\n" if mode == "dos" else "\n")

    @staticmethod
    def _sgr(fg, bg, mode, pal, allowed) -> str:
        if not pal:
            p = ["0"]
            if fg is not None:
                p.append("38;2;%d;%d;%d" % fg)
            if bg is not None:
                p.append("48;2;%d;%d;%d" % bg)
            return "\x1b[" + ";".join(p) + "m"
        f = _DOS_IDX.get(fg) if fg is not None else 7
        if f is None:
            f = nearest16(fg, allowed)
        b = _DOS_IDX.get(bg) if bg is not None else 0
        if b is None:
            b = nearest16(bg, allowed)
        if mode == "dos":
            p = ["0"]
            if f >= 8:
                p.append("1")
            if b >= 8:
                p.append("5")
            p += [str(30 + DOS2ANSI[f & 7]), str(40 + DOS2ANSI[b & 7])]
        else:
            p = ["0", str((90 if f >= 8 else 30) + DOS2ANSI[f & 7]), str((100 if b >= 8 else 40) + DOS2ANSI[b & 7])]
        return "\x1b[" + ";".join(p) + "m"

    def uses_ice(self) -> bool:
        pal = True
        for r in self.rows:
            for _, _, bg in r:
                if bg is not None:
                    i = _DOS_IDX.get(bg)
                    if (i if i is not None else nearest16(bg, self._allowed())) >= 8:
                        return True
        return False

    def to_ans_bytes(self, sauce: bool = True, title: str = "", author: str = "Padawan", group: str = "") -> bytes:
        body = ("\x1b[0m" + self.to_ansi("dos")).encode("cp437", errors="replace")
        if not sauce:
            return body
        def fld(s: str, n: int) -> bytes:
            return s.encode("cp437", errors="replace")[:n].ljust(n, b" ")
        ice = self.uses_ice()
        rec = (b"SAUCE00" + fld(title or self.title or "Padawan ANSI", 35) + fld(author, 20) + fld(group, 20)
               + datetime.now().strftime("%Y%m%d").encode() + len(body).to_bytes(4, "little")
               + bytes([1, 1]) + self.cols.to_bytes(2, "little") + self.nrows.to_bytes(2, "little")
               + b"\0\0\0\0" + bytes([0, (1 if ice else 0) | 0x02]) + b"IBM VGA".ljust(22, b"\0"))
        assert len(rec) == 128
        return body + b"\x1a" + rec

    def to_html(self, title: str = "", fragment: bool = False, font_px: int = 0) -> str:
        def esc(s: str) -> str:
            return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        lines = []
        for r in self.rows:
            cur, buf, parts = None, [], []
            def flush():
                if buf:
                    fg, bg = cur
                    st = []
                    if fg is not None:
                        st.append("color:" + _hex(fg))
                    if bg is not None:
                        st.append("background:" + _hex(bg))
                    s = esc("".join(buf))
                    parts.append(f'<span style="{";".join(st)}">{s}</span>' if st else s)
            for ch, fg, bg in r:
                if (fg, bg) != cur:
                    flush()
                    cur, buf = (fg, bg), []
                buf.append(ch)
            flush()
            lines.append("".join(parts))
        fpx = font_px or (12 if self.cols <= 80 else 9 if self.cols <= 120 else 7)
        pre = (f'<pre class="ansi" style="font-family:\'Cascadia Mono\',Consolas,\'Courier New\',monospace;'
               f'font-size:{fpx}px;line-height:1;letter-spacing:0;margin:0;background:#000;color:#c0c0c0">'
               + "\n".join(lines) + "</pre>")
        if fragment:
            return pre + "\n"
        t = esc(title or self.title or "Art ANSI")
        return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{t}</title>
<style>
  body {{ background:#050805; color:#9f9; margin:0; min-height:100vh; display:flex; flex-direction:column;
         align-items:center; justify-content:center; font-family:Consolas,'Courier New',monospace; }}
  .ecran {{ position:relative; padding:18px; background:#000; border:3px solid #2a2a2a; border-radius:14px;
           box-shadow:0 0 0 6px #111, 0 0 60px rgba(60,255,120,.18); overflow:auto; max-width:96vw; }}
  .ecran::after {{ content:""; position:absolute; inset:0; pointer-events:none; border-radius:12px;
           background:repeating-linear-gradient(0deg, rgba(0,0,0,.18) 0 1px, transparent 1px 3px); }}
  h1 {{ font-size:15px; letter-spacing:3px; color:#7f7; text-shadow:0 0 6px #3f3; margin:18px 0 10px; }}
  footer {{ font-size:11px; color:#585; margin:12px; }}
</style>
</head>
<body>
<h1>▓▒░ {t} ░▒▓</h1>
<div class="ecran">{pre}</div>
<footer>{self.cols}×{self.nrows} caractères · fait avec Padawan 🖼→ANSI</footer>
</body>
</html>
"""

    def to_python(self) -> str:
        lines = self.to_ansi("vt").split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        body = "\n".join("    " + repr(l + "\n") for l in lines)
        return (f"# Image en ANSI ({self.cols}×{self.nrows}, style {self.style}) — Padawan 🖼→ANSI\n"
                "import os\n"
                "os.system(\"\")  # active les couleurs ANSI dans la console Windows\n"
                "ART = (\n" + body + "\n)\n"
                "print(ART + \"\\x1b[0m\")\n")


# ─────────────────────────────────────────────────────────── conversion ──
def open_image(src: Any):
    """Chemin, octets ou image PIL → image RGB (transparence posée sur du noir, 1re image d'un GIF animé)."""
    if not load_pil():
        raise RuntimeError("Pillow n'est pas installé (pip install pillow)")
    if isinstance(src, (bytes, bytearray)):
        im = Image.open(io.BytesIO(src))
    elif isinstance(src, str):
        im = Image.open(src)
    else:
        im = src
    try:
        im.seek(0)
    except Exception:
        pass
    im.load()
    if im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA")
        bg = Image.new("RGBA", im.size, (0, 0, 0, 255))
        bg.alpha_composite(im)
        im = bg
    return im.convert("RGB")


def _pal_img(colors: Sequence[RGB]):
    p = Image.new("P", (1, 1))
    flat: List[int] = []
    for c in colors:
        flat += list(c)
    flat += list(colors[0]) * (256 - len(colors))
    p.putpalette(flat)
    return p


def _quant(im, colors: Sequence[RGB], dither: bool) -> List[int]:
    q = im.quantize(palette=_pal_img(colors), dither=Image.Dither.FLOYDSTEINBERG if dither else Image.Dither.NONE)
    n = len(colors)
    return [i if i < n else 0 for i in q.getdata()]


def _gray_levels(im, n: int, dither: bool) -> List[int]:
    """Niveaux de gris 0..n-1 (tramage Floyd-Steinberg facultatif)."""
    g = im.convert("L").convert("RGB")
    grays = [(round(255 * i / (n - 1)),) * 3 for i in range(n)]
    return _quant(g, grays, dither)


_SHADE_COMBOS: List[Tuple[str, int, int, RGB]] = []


def _shade_combos():
    if not _SHADE_COMBOS:
        for f in range(16):
            _SHADE_COMBOS.append(("█", f, 0, DOS16[f]))
        for f in range(16):
            for b in range(8):
                if f == b:
                    continue
                for ch, cov in SHADES:
                    c = tuple(round(DOS16[f][k] * cov + DOS16[b][k] * (1 - cov)) for k in range(3))
                    _SHADE_COMBOS.append((ch, f, b, c))  # type: ignore[arg-type]
    return _SHADE_COMBOS


def _shade_pick(pixels: List[RGB]) -> List[int]:
    combos = _shade_combos()
    if _np is not None:
        P = (_np.asarray(pixels, dtype=_np.int32).reshape(-1, 3) & 0xF8) | 4   # 32 niveaux/canal : bien moins de couleurs
        uniq, inv = _np.unique(P, axis=0, return_inverse=True)
        Cc = _np.asarray([c[3] for c in combos], dtype=_np.int32).reshape(1, -1, 3)
        w = _np.asarray([2, 4, 3], dtype=_np.int32)
        best = _np.empty(len(uniq), dtype=_np.int64)
        for s in range(0, len(uniq), 2000):
            d = (((uniq[s:s + 2000].reshape(-1, 1, 3) - Cc) ** 2) * w).sum(axis=2)
            best[s:s + 2000] = d.argmin(axis=1)
        return best[inv.reshape(-1)].tolist()
    cache: Dict[RGB, int] = {}
    res = []
    for p in pixels:
        k = (p[0] & 0xF0 | 8, p[1] & 0xF0 | 8, p[2] & 0xF0 | 8)
        i = cache.get(k)
        if i is None:
            i = min(range(len(combos)), key=lambda j: _d2(k, combos[j][3]))
            cache[k] = i
        res.append(i)
    return res


def convert(im, *, width: int = 80, style: str = "dos16", brightness: int = 0, contrast: int = 0,
            dither: bool = True, invert: bool = False, title: str = "", max_rows: int = 320) -> Art:
    """Image RGB → Art. brightness / contrast : -100..+100 (0 = inchangé)."""
    t0 = time.perf_counter()
    if style not in STYLE_IDS:
        style = "dos16"
    width = max(8, min(400, int(width)))
    w, h = im.size
    half = style in HALF_STYLES
    if half:
        hp = max(2, round(width * h / w))
        hp += hp % 2
        hp = min(hp, max_rows * 2)
    else:
        hp = max(1, min(max_rows, round(width * h / w * 0.5)))
    img = im.resize((width, hp), Image.Resampling.LANCZOS)
    if brightness:
        img = ImageEnhance.Brightness(img).enhance(max(0.0, 1 + brightness / 100))
    if contrast:
        img = ImageEnhance.Contrast(img).enhance(max(0.0, 1 + contrast / 100))
    if invert:
        img = ImageOps.invert(img)
    rows: List[List[Cell]] = []
    if half:
        if style == "dos16":
            idx = _quant(img, DOS16, dither)
            px = [DOS16[i] for i in idx]
        elif style == "pipboy":
            px = [PIP[i] for i in _gray_levels(img, len(PIP), dither)]
        elif style == "noir":
            px = _noir_pixels(img, dither)
        else:
            px = list(img.getdata())
        for y in range(0, hp, 2):
            row: List[Cell] = []
            a = px[y * width:(y + 1) * width]
            b = px[(y + 1) * width:(y + 2) * width]
            for top, bot in zip(a, b):
                row.append(_half_cell(top, bot, style))
            rows.append(row)
    elif style == "ascii":
        lv = _gray_levels(img, len(ASCII_RAMP), dither)
        for y in range(hp):
            rows.append([(ASCII_RAMP[i], None, None) for i in lv[y * width:(y + 1) * width]])
    else:  # shades
        combos = _shade_combos()
        pick = _shade_pick(list(img.getdata()))
        for y in range(hp):
            row = []
            for i in pick[y * width:(y + 1) * width]:
                ch, f, b, _ = combos[i]
                row.append((ch, DOS16[f], DOS16[b]))
            rows.append(row)
    art = Art(rows, style, title)
    art.ms = (time.perf_counter() - t0) * 1000
    return art


def _half_cell(top: RGB, bot: RGB, style: str) -> Cell:
    if top == bot:
        if style == "dos16" and _DOS_IDX.get(top, 0) >= 8:
            return ("█", top, DOS16[0])
        return (" ", DOS16[7] if style == "dos16" else None, top)
    if style == "dos16":
        ti, bi = _DOS_IDX.get(top, 0), _DOS_IDX.get(bot, 0)
        if bi >= 8 > ti:  # évite un fond clair (iCE) quand c'est possible
            return ("▄", bot, top)
    return ("▀", top, bot)


def _noir_pixels(img, dither: bool) -> List[RGB]:
    """Gris (tramés) partout, sauf les zones vraiment colorées → accent le plus proche (néon, lampe, sang)."""
    gray = [NOIR_GRAYS[i] for i in _quant(img.convert("L").convert("RGB"), NOIR_GRAYS, dither)]
    acc = [NOIR_ACCENTS[i] for i in _quant(img, NOIR_ACCENTS, False)]
    hsv = img.convert("HSV")
    out: List[RGB] = []
    for g, a, (h, s_, v) in zip(gray, acc, hsv.getdata()):
        out.append(a if (s_ > 90 and v > 35) else g)
    return out


# ─────────────────────────────────────────── banque d'images (jeux) v1.1 ──
def art_to_dict(art: Art) -> Dict[str, Any]:
    """Art → dict compact (palette + caractères + index de couleurs), pour JSON/gzip."""
    pal: List[RGB] = []
    pidx: Dict[RGB, int] = {}

    def ix(c: Optional[RGB]) -> int:
        if c is None:
            return -1
        c = tuple(c)  # type: ignore
        i = pidx.get(c)  # type: ignore
        if i is None:
            i = pidx[c] = len(pal)  # type: ignore
            pal.append(c)  # type: ignore
        return i
    chars, fgs, bgs = [], [], []
    for r in art.rows:
        chars.append("".join(c[0] for c in r))
        fgs.append([ix(c[1]) for c in r])
        bgs.append([ix(c[2]) for c in r])
    return {"style": art.style, "title": art.title, "cols": art.cols, "rows": art.nrows,
            "pal": ["%02x%02x%02x" % c for c in pal], "ch": chars, "fg": fgs, "bg": bgs}


def art_from_dict(d: Dict[str, Any]) -> Art:
    pal = [(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)) for h in d.get("pal", [])]

    def col(i: int) -> Optional[RGB]:
        return pal[i] if 0 <= i < len(pal) else None
    rows: List[List[Cell]] = []
    for chs, fr, br in zip(d.get("ch", []), d.get("fg", []), d.get("bg", [])):
        rows.append([(ch, col(f), col(b)) for ch, f, b in zip(chs, fr, br)])
    return Art(rows, d.get("style", "truecolor"), d.get("title", ""))


_BANKS: Dict[str, Dict[str, Any]] = {}


def load_bank(path: str) -> Dict[str, Any]:
    """Lit une banque .json.gz {"version", "games": {famille: {"fallback", "scenes": {clé: art_dict}}}} (en cache).
    Les Art sont décodés à la demande (bank_art)."""
    import gzip
    import json
    key = os.path.abspath(path)
    b = _BANKS.get(key)
    if b is None:
        try:
            with gzip.open(path, "rt", encoding="utf-8") as f:
                b = json.load(f)
        except Exception:
            b = {}
        b.setdefault("games", {})
        b["_arts"] = {}
        _BANKS[key] = b
    return b


def bank_art(bank: Dict[str, Any], family: str, key: str) -> Optional[Art]:
    g = (bank.get("games") or {}).get(family) or {}
    d = (g.get("scenes") or {}).get(key)
    if not d:
        return None
    cache = bank.setdefault("_arts", {})
    a = cache.get((family, key))
    if a is None:
        a = cache[(family, key)] = art_from_dict(d)
    return a


def image_to_ansi(src: Any, width: int = 80, style: str = "dos16", **kw) -> Art:
    """API pour les jeux et les scripts : chemin / octets / image PIL → Art."""
    title = os.path.splitext(os.path.basename(src))[0] if isinstance(src, str) else ""
    return convert(open_image(src), width=width, style=style, title=title, **kw)


# ───────────────────────────────────────────────────────── aperçu Tk ──
def _prev_col(c: RGB, exact: bool) -> RGB:
    if exact:
        return c
    return tuple(min(255, round(v / 51) * 51) for v in c)  # type: ignore[return-value]  # 6 niveaux : 216 couleurs


def render_tk(text: tk.Text, art: Art, cache: Optional[set] = None) -> None:
    """Dessine l'art dans un tk.Text (tags de couleur mis en cache, insertion par lots)."""
    cache = cache if cache is not None else getattr(text, "_ansi_tags", None)
    if cache is None:
        cache = set()
        text._ansi_tags = cache  # type: ignore[attr-defined]
    exact = art.style in PALETTE_STYLES or art.style in ("pipboy", "noir")
    text.configure(state="normal")
    text.delete("1.0", "end")
    for r in art.rows:
        args: List[Any] = []
        cur, buf = None, []
        for ch, fg, bg in r:
            k = (fg, bg)
            if k != cur:
                if buf:
                    args += ["".join(buf), cur_tags]
                cur, buf = k, []
                tg = []
                if fg is not None:
                    n = "f" + _hex(_prev_col(fg, exact))[1:]
                    if n not in cache:
                        text.tag_configure(n, foreground="#" + n[1:])
                        cache.add(n)
                    tg.append(n)
                if bg is not None:
                    n = "b" + _hex(_prev_col(bg, exact))[1:]
                    if n not in cache:
                        text.tag_configure(n, background="#" + n[1:])
                        cache.add(n)
                    tg.append(n)
                cur_tags = tuple(tg)
            buf.append(ch)
        if buf:
            args += ["".join(buf), cur_tags]
        args += ["\n", ()]
        text.insert("end", *args)
    text.configure(state="disabled")


HALF_STYLES = ("dos16", "truecolor", "pipboy", "noir")
_TILE_CACHE: Dict[Tuple[str, RGB, RGB, int, int], Any] = {}
_REF_FONT: List[Any] = []


def _ref_font():
    if not _REF_FONT:
        f = None
        for name in ("CascadiaMono.ttf", "consola.ttf", "lucon.ttf", "cour.ttf", "DejaVuSansMono.ttf"):
            try:
                f = ImageFont.truetype(name, 32)
                break
            except Exception:
                continue
        _REF_FONT.append(f or ImageFont.load_default())
    return _REF_FONT[0]


def _tile(ch: str, fg: RGB, bg: RGB, cw: int, chh: int):
    k = (ch, fg, bg, cw, chh)
    t = _TILE_CACHE.get(k)
    if t is None:
        f = _ref_font()
        try:
            l, tp, r, b = f.getbbox("█")
        except Exception:
            l, tp, r, b = 0, 0, 16, 32
        big = Image.new("RGB", (max(1, r - l), max(1, b - tp)), bg)
        if ch.strip():
            ImageDraw.Draw(big).text((-l, -tp), ch, font=f, fill=fg)
        t = big.resize((cw, chh), Image.Resampling.BOX)
        if len(_TILE_CACHE) > 6000:
            _TILE_CACHE.clear()
        _TILE_CACHE[k] = t
    return t


def render_image(art: Art, cw: int = 8):
    """Rendu exact de l'art en image PIL (cellule cw × 2cw, comme une console 8×16) — rapide, même à 200 colonnes."""
    cw = max(1, int(cw))
    chh = 2 * cw
    if art.style in HALF_STYLES:
        px = Image.new("RGB", (art.cols, art.nrows * 2))
        data: List[RGB] = []
        top_row: List[RGB] = []
        for r in art.rows:
            top_row, bot_row = [], []
            for ch, fg, bg in r:
                f = fg or DEFAULT_FG
                b = bg or DEFAULT_BG
                if ch == "▀":
                    top_row.append(f); bot_row.append(b)
                elif ch == "▄":
                    top_row.append(b); bot_row.append(f)
                elif ch == "█":
                    top_row.append(f); bot_row.append(f)
                else:
                    top_row.append(b); bot_row.append(b)
            pad = [DEFAULT_BG] * (art.cols - len(top_row))
            data += top_row + pad + bot_row + pad
        px.putdata(data)
        return px.resize((art.cols * cw, art.nrows * chh), Image.Resampling.NEAREST)
    out = Image.new("RGB", (art.cols * cw, art.nrows * chh), DEFAULT_BG)
    for y, r in enumerate(art.rows):
        for x, (ch, fg, bg) in enumerate(r):
            if ch == " " and bg is None:
                continue
            out.paste(_tile(ch, fg or DEFAULT_FG, bg or DEFAULT_BG, cw, chh), (x * cw, y * chh))
    return out


# ────────────────────────────────────────────────────────── glisser-déposer ──
_KEEP: List[Any] = []  # garde les procédures Win32 en vie


def enable_drop(widget: tk.Misc, on_files: Callable[[List[str]], None]) -> str:
    """tkinterdnd2 s'il est installé, sinon WM_DROPFILES (Win32) ; retourne la méthode ou ''."""
    try:
        import tkinterdnd2  # type: ignore
        from tkinterdnd2 import DND_FILES  # type: ignore
        req = getattr(tkinterdnd2.TkinterDnD, "_require", None) or getattr(tkinterdnd2.TkinterDnD, "require", None)
        req(widget.winfo_toplevel())
        def drop(e):
            try:
                items = list(widget.tk.splitlist(e.data))
            except Exception:
                items = [e.data]
            on_files([i for i in items if i])
            return getattr(e, "action", "copy")
        widget.drop_target_register(DND_FILES)  # type: ignore[attr-defined]
        widget.dnd_bind("<<Drop>>", drop)  # type: ignore[attr-defined]
        return "tkdnd"
    except Exception:
        pass
    if not IS_WIN:
        return ""
    try:
        return _win32_drop(widget, on_files)
    except Exception:
        return ""


def _win32_drop(widget: tk.Misc, on_files) -> str:
    import ctypes
    from ctypes import wintypes as wt
    u, sh = ctypes.windll.user32, ctypes.windll.shell32
    LRESULT = ctypes.c_ssize_t
    WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
    u.SetWindowLongPtrW.restype = ctypes.c_void_p
    u.SetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_void_p]
    u.CallWindowProcW.restype = LRESULT
    u.CallWindowProcW.argtypes = [ctypes.c_void_p, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
    sh.DragQueryFileW.argtypes = [ctypes.c_void_p, wt.UINT, ctypes.c_wchar_p, wt.UINT]
    sh.DragQueryFileW.restype = wt.UINT
    sh.DragFinish.argtypes = [ctypes.c_void_p]
    hwnd = widget.winfo_id()
    old = [None]

    def proc(h, msg, wp, lp):
        if msg == 0x0233:  # WM_DROPFILES
            n = sh.DragQueryFileW(wp, 0xFFFFFFFF, None, 0)
            files = []
            for i in range(n):
                ln = sh.DragQueryFileW(wp, i, None, 0) + 1
                b = ctypes.create_unicode_buffer(ln)
                sh.DragQueryFileW(wp, i, b, ln)
                files.append(b.value)
            sh.DragFinish(wp)
            pending.append(files)  # aucun appel Tk ici (on est DANS la boucle de messages de Tcl)
            return 0
        return u.CallWindowProcW(old[0], h, msg, wp, lp)

    pending: List[List[str]] = []

    def poll():
        try:
            if not widget.winfo_exists():
                return
        except Exception:
            return
        while pending:
            try:
                on_files(pending.pop(0))
            except Exception:
                pass
        widget.after(150, poll)

    cb = WNDPROC(proc)
    _KEEP.append(cb)
    old[0] = u.SetWindowLongPtrW(hwnd, -4, ctypes.cast(cb, ctypes.c_void_p).value)
    _KEEP.append(old)
    sh.DragAcceptFiles(hwnd, True)
    widget.after(150, poll)
    return "win32"


# ─────────────────────────────────────────────────────────── la fenêtre ──
_MEASURE: Dict[Tuple[str, int], Tuple[float, int]] = {}


class AnsiStudio:
    """Fenêtre 🖼→ANSI. hooks (tous facultatifs) :
       pip(mod) · new_tab(name, text) · insert(art) · default_dir() · python() · env() · log(msg) · flash(msg)."""

    def __init__(self, master: tk.Misc, C: Dict[str, str], *, cfg: Optional[Dict[str, Any]] = None,
                 save_cfg: Optional[Callable[[], None]] = None, workdir: str = "", hooks: Optional[Dict[str, Callable]] = None,
                 path: str = ""):
        self.C, self.cfg = C, (cfg if cfg is not None else {})
        self.save_cfg = save_cfg or (lambda: None)
        self.workdir = workdir or os.path.join(os.path.expanduser("~"), "Padawan_ANSI")
        self.hooks = hooks or {}
        self.src = None          # image PIL d'origine
        self.src_name = ""
        self.art: Optional[Art] = None
        self._job = None
        self._tags: set = set()
        st = self.cfg.setdefault("ansi", {})
        d = self.d = tk.Toplevel(master)
        d.title("🖼→ANSI — convertisseur d'images (Atelier)")
        d.configure(bg=C["bg"])
        sw, sh = d.winfo_screenwidth(), d.winfo_screenheight()
        W, H = min(1200, sw - 30), min(700, sh - 80)
        try:
            top = master.winfo_toplevel()
            x = max(0, min(sw - W, top.winfo_rootx() + (top.winfo_width() - W) // 2))
            y = max(0, min(sh - H - 40, top.winfo_rooty() + (top.winfo_height() - H) // 2))
        except Exception:
            x = y = 20
        d.geometry(f"{W}x{H}+{x}+{y}")
        d.minsize(900, 520)
        self.v_style = tk.StringVar(value=st.get("style", "dos16") if st.get("style") in STYLE_IDS else "dos16")
        self.v_width = tk.IntVar(value=max(40, min(200, int(st.get("width", 80) or 80))))
        self.v_bri = tk.IntVar(value=int(st.get("brightness", 0) or 0))
        self.v_con = tk.IntVar(value=int(st.get("contrast", 0) or 0))
        self.v_dither = tk.BooleanVar(value=bool(st.get("dither", True)))
        self.v_invert = tk.BooleanVar(value=bool(st.get("invert", False)))
        self.v_sauce = tk.BooleanVar(value=bool(st.get("sauce", True)))
        self.v_textprev = tk.BooleanVar(value=bool(st.get("text_preview", False)))
        self._photo = None
        self._build()
        d.bind("<Escape>", lambda e: self.close())
        d.protocol("WM_DELETE_WINDOW", self.close)
        for s in ("<Control-v>", "<Control-V>", "<Shift-Insert>"):
            d.bind(s, lambda e: (self.paste(), "break")[1])
        d.bind("<Control-o>", lambda e: (self.pick(), "break")[1])
        self.dnd = ""
        for w in (self.prev, self.drop_lbl):
            m = enable_drop(w, self._dropped)
            self.dnd = self.dnd or m
        self._hint()
        if path:
            d.after(30, lambda: self.load_path(path))

    # ── construction
    def _btn(self, p, text, cmd, tip="", kind="norm"):
        C = self.C
        bg = {"norm": C["card"], "gold": C["gold"], "cyan": "#1d4a5e", "ok": "#1f5e43"}[kind]
        b = tk.Button(p, text=text, command=cmd, bg=bg, fg="#1a1408" if kind == "gold" else C["fg"], relief="flat",
                      cursor="hand2", font=("Segoe UI", 9), padx=6, pady=3, activebackground=C["gold"],
                      activeforeground="#1a1408", disabledforeground=C["dim"])
        if tip:
            _Tip(b, tip)
        return b

    def _build(self):
        C, d = self.C, self.d
        top = tk.Frame(d, bg=C["panel"])
        top.pack(side="top", fill="x")
        tk.Label(top, text="🖼→ANSI", bg=C["panel"], fg=C["gold"], font=("Segoe UI", 13, "bold"), padx=10).pack(side="left")
        self._btn(top, "📂 Ouvrir une image…", self.pick, "png, jpg, gif, bmp, webp (Ctrl+O)", "gold").pack(side="left", padx=3, pady=5)
        self._btn(top, "📋 Coller une image", self.paste, "Image copiée (capture d'écran, navigateur…) ou fichier copié\n(Ctrl+V)").pack(side="left", padx=3)
        self.drop_lbl = tk.Label(top, text="⬇ ou glisse une image ici", bg=C["panel"], fg=C["dim"], font=("Segoe UI", 9, "italic"))
        self.drop_lbl.pack(side="left", padx=10)
        self.info = tk.Label(top, text="", bg=C["panel"], fg=C["cyan"], font=("Segoe UI", 9))
        self.info.pack(side="right", padx=10)

        bot = tk.Frame(d, bg=C["bg"])
        bot.pack(side="bottom", fill="x", padx=6, pady=6)
        self.out_btns = []
        for text, cmd, tip, kind in (
                ("📋 Copier ANSI", lambda: self.copy(True), "Texte avec les codes couleur ANSI (console, terminal, BBS)", "norm"),
                ("📋 Copier texte", lambda: self.copy(False), "Les caractères seulement, sans couleur", "norm"),
                ("💾 .ans", self.save_ans, "Fichier ANSI DOS (CP437) · SAUCE si coché à gauche", "norm"),
                ("💾 .txt", self.save_txt, "Texte simple UTF-8", "norm"),
                ("🌐 HTML", self.save_html, "Page web rétro (écran cathodique) avec les couleurs", "norm"),
                ("🌐→ onglet", self.html_tab, "La page HTML dans un nouvel onglet de l'Atelier\n(👁 Aperçu pour la voir)", "cyan"),
                ("➕ Insérer dans l'onglet", self.insert_tab, "Au curseur de l'onglet courant :\nPython = code print() avec couleurs · HTML = <pre> coloré · sinon texte", "cyan"),
                ("🖥 Console", self.console, "Affiche le vrai rendu ANSI dans une console Windows", "gold")):
            b = self._btn(bot, text, cmd, tip, kind)
            b.pack(side="left", padx=2)
            self.out_btns.append(b)

        body = tk.Frame(d, bg=C["bg"])
        body.pack(fill="both", expand=True, padx=6, pady=(6, 0))
        left = tk.Frame(body, bg=C["panel"], width=250)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        def head(t):
            tk.Label(left, text=t, bg=C["panel"], fg=C["gold"], font=("Segoe UI", 9, "bold"), anchor="w").pack(fill="x", padx=8, pady=(8, 1))
        head("Style")
        for sid, lab in STYLES:
            tk.Radiobutton(left, text=lab, value=sid, variable=self.v_style, command=self.changed, bg=C["panel"], fg=C["fg"],
                           selectcolor=C["card"], activebackground=C["panel"], activeforeground=C["gold"],
                           font=("Segoe UI", 9), anchor="w", highlightthickness=0).pack(fill="x", padx=10)
        from tkinter import ttk
        sty = ttk.Style(d)
        sty.configure("Ansi.Horizontal.TScale", background=C["gold"], troughcolor=C["card"], bordercolor=C["panel"],
                      lightcolor=C["gold"], darkcolor=C["gold"], sliderlength=16)
        sty.map("Ansi.Horizontal.TScale", background=[("active", C["fg"])])
        self._scale_lbl = {}

        def scale(label, var, lo, hi, res=1):
            row = tk.Frame(left, bg=C["panel"])
            row.pack(fill="x", padx=8, pady=(8, 1))
            tk.Label(row, text=label, bg=C["panel"], fg=C["gold"], font=("Segoe UI", 9, "bold"), anchor="w").pack(side="left")
            val = tk.Label(row, text=str(var.get()), bg=C["panel"], fg=C["fg"], font=("Consolas", 9, "bold"), anchor="e")
            val.pack(side="right")

            def moved(v, var=var, val=val):
                iv = int(round(float(v)))
                if var.get() != iv:
                    var.set(iv)
                val.configure(text=str(iv))
                self.changed()
            s = ttk.Scale(left, from_=lo, to=hi, orient="horizontal", style="Ansi.Horizontal.TScale", command=moved)
            s.set(var.get())
            s.pack(fill="x", padx=10, pady=(0, 2))
            var.trace_add("write", lambda *a, s=s, var=var, val=val: (abs(float(s.get()) - var.get()) > 0.5 and s.set(var.get()),
                                                                      val.configure(text=str(var.get()))))
            return s
        self.s_width = scale("Largeur (colonnes)", self.v_width, 40, 200)
        scale("Luminosité", self.v_bri, -100, 100)
        scale("Contraste", self.v_con, -100, 100)
        for lab, var, tip in (("Tramage (dithering)", self.v_dither, "Floyd-Steinberg : 16 couleurs, ASCII, Pip-Boy"),
                              ("Inverser", self.v_invert, "Négatif de l'image"),
                              ("SAUCE dans le .ans", self.v_sauce, "Petite fiche (titre, auteur, largeur) à la fin du .ans,\nlue par PabloDraw, Moebius, les BBS"),
                              ("Aperçu en texte Tk (sélectionnable)", self.v_textprev, "Aperçu dans une zone de texte colorée (tags en cache)\n"
                               "au lieu de l'image exacte. Plus lent au-delà de ~100 colonnes.")):
            cb = tk.Checkbutton(left, text=lab, variable=var, command=self.changed, bg=C["panel"], fg=C["fg"], selectcolor=C["card"],
                                activebackground=C["panel"], activeforeground=C["gold"], font=("Segoe UI", 9), anchor="w",
                                highlightthickness=0)
            cb.pack(fill="x", padx=10, pady=(4, 0))
            _Tip(cb, tip)
        self._btn(left, "↺ Réglages par défaut", self.reset).pack(anchor="w", padx=10, pady=(10, 4))
        self.stats = tk.Label(left, text="", bg=C["panel"], fg=C["dim"], font=("Segoe UI", 8), justify="left", anchor="w", wraplength=230)
        self.stats.pack(fill="x", padx=8, pady=4)

        right = tk.Frame(body, bg="#000000")
        right.pack(side="left", fill="both", expand=True, padx=(6, 0))
        self.font = tkfont.Font(family=_mono_family(d), size=8)
        self.prev = tk.Text(right, bg="#000000", fg=_hex(DEFAULT_FG), font=self.font, wrap="none", relief="flat", bd=0,
                            padx=6, pady=6, spacing1=0, spacing2=0, spacing3=0, highlightthickness=0, cursor="arrow",
                            insertwidth=0, state="disabled")
        ys = tk.Scrollbar(right, orient="vertical", command=self.prev.yview)
        xs = tk.Scrollbar(right, orient="horizontal", command=self.prev.xview)
        self.prev.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        ys.pack(side="right", fill="y")
        xs.pack(side="bottom", fill="x")
        self.prev.pack(fill="both", expand=True)
        self.prev.bind("<Configure>", lambda e: self._fit_later())
        self.ys, self.xs = ys, xs
        self.cv = tk.Canvas(right, bg="#000000", highlightthickness=0, bd=0)
        self.cv.bind("<Configure>", lambda e: self._fit_later())
        self.cv.bind("<MouseWheel>", lambda e: self.cv.yview_scroll(-1 if e.delta > 0 else 1, "units"))
        self.mode = "text"
        self.pil_bar = tk.Frame(right, bg="#000000")

    def _hint(self):
        if not load_pil():
            self._set_buttons(False)
            self._msg("Pillow (le module qui lit les images) n'est pas installé.\n\n"
                      "Clique « 📦 Installer Pillow » : l'Atelier lance  pip install pillow  (après confirmation).\n"
                      "Ensuite, rouvre 🖼→ANSI.")
            for w in self.pil_bar.winfo_children():
                w.destroy()
            self._btn(self.pil_bar, "📦 Installer Pillow (pip install pillow)", self.install_pil, kind="gold").pack(pady=8)
            self.pil_bar.place(relx=0.5, rely=0.62, anchor="center")
            return
        self._set_buttons(False)
        how = {"tkdnd": "glisse-dépose", "win32": "glisse-dépose"}.get(self.dnd, "")
        self._msg("🖼  Ouvre une image (📂), colle-la (Ctrl+V)" + (f" ou {how}-la ici" if how else "") + ".\n\n"
                  "png · jpg · gif · bmp · webp\n\n"
                  "Styles : 16 couleurs DOS ▀▄, truecolor 24 bits, ASCII, Pip-Boy vert, ombres ░▒▓█, film noir.\n"
                  "Tout reste sur ton PC.")

    def _show(self, mode: str):
        """« text » = zone de texte Tk · « image » = rendu exact (Canvas)."""
        if mode == self.mode:
            return
        if mode == "image":
            self.prev.pack_forget()
            self.cv.pack(fill="both", expand=True)
            self.ys.configure(command=self.cv.yview)
            self.xs.configure(command=self.cv.xview)
            self.cv.configure(yscrollcommand=self.ys.set, xscrollcommand=self.xs.set)
        else:
            self.cv.pack_forget()
            self.prev.pack(fill="both", expand=True)
            self.ys.configure(command=self.prev.yview)
            self.xs.configure(command=self.prev.xview)
        self.mode = mode

    def _msg(self, t: str):
        self._show("text")
        self.prev.configure(state="normal", font=("Segoe UI", 11))
        self.prev.delete("1.0", "end")
        self.prev.insert("1.0", "\n\n" + t)
        self.prev.configure(state="disabled")

    def _set_buttons(self, on: bool):
        for b in self.out_btns:
            b.configure(state="normal" if on else "disabled")

    def install_pil(self):
        f = self.hooks.get("pip")
        if f:
            f("pillow")
        else:
            messagebox.showinfo("🖼→ANSI", "Dans une console :  python -m pip install pillow", parent=self.d)

    # ── sources
    def pick(self):
        if not load_pil():
            return self._hint()
        p = filedialog.askopenfilename(parent=self.d, title="Image à convertir",
                                       initialdir=self.cfg.get("ansi", {}).get("last_dir") or os.path.expanduser("~"),
                                       filetypes=[("Images", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"), ("Tous", "*.*")])
        if p:
            self.load_path(p)

    def _dropped(self, files: List[str]):
        for f in files:
            if os.path.isfile(f) and f.lower().endswith(IMG_EXT):
                return self.load_path(f)
        if files:
            self._flash("Déposé : ce n'est pas une image (png, jpg, gif, bmp, webp)", bad=True)

    def paste(self):
        if not load_pil():
            return self._hint()
        im = None
        try:
            im = ImageGrab.grabclipboard() if ImageGrab else None
        except Exception as e:
            self._log(f"ansi clip: {e}")
        if isinstance(im, list):
            for f in im:
                if isinstance(f, str) and f.lower().endswith(IMG_EXT) and os.path.isfile(f):
                    return self.load_path(f)
            im = None
        if im is None:
            try:
                t = self.d.clipboard_get().strip().strip('"')
                if t.lower().endswith(IMG_EXT) and os.path.isfile(t):
                    return self.load_path(t)
            except Exception:
                pass
            return self._flash("Presse-papiers : aucune image (copie une image ou une capture, puis Ctrl+V)", bad=True)
        self.load_image(im, "image collée")

    def load_path(self, p: str) -> bool:
        try:
            im = open_image(p)
        except Exception as e:
            self._flash(f"Image illisible : {e}", bad=True)
            return False
        self.cfg.setdefault("ansi", {})["last_dir"] = os.path.dirname(p)
        self.load_image(im, os.path.basename(p))
        return True

    def load_image(self, im, name: str):
        try:
            im = open_image(im)
        except Exception as e:
            return self._flash(f"Image illisible : {e}", bad=True)
        if max(im.size) > 1600:  # plus rapide, sans perte visible à 200 colonnes
            im = im.copy()
            im.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
        self.src, self.src_name = im, name
        self.pil_bar.place_forget()
        self.render()

    # ── rendu
    def changed(self):
        if self._job:
            try:
                self.d.after_cancel(self._job)
            except Exception:
                pass
        self._job = self.d.after(120, self.render)

    def opts(self) -> Dict[str, Any]:
        return dict(width=int(self.v_width.get()), style=self.v_style.get(), brightness=int(self.v_bri.get()),
                    contrast=int(self.v_con.get()), dither=bool(self.v_dither.get()), invert=bool(self.v_invert.get()))

    def render(self):
        self._job = None
        o = self.opts()
        st = self.cfg.setdefault("ansi", {})
        st.update({k: o[k] for k in ("width", "style", "brightness", "contrast", "dither", "invert")}, sauce=bool(self.v_sauce.get()),
                  text_preview=bool(self.v_textprev.get()))
        if self.src is None:
            return
        t0 = time.perf_counter()
        title = os.path.splitext(self.src_name)[0]
        self.art = convert(self.src, title=title, **o)
        self._draw()
        ms = (time.perf_counter() - t0) * 1000
        self.render_ms = ms
        self._set_buttons(True)
        w, h = self.src.size
        self.info.configure(text=f"{self.src_name} · {w}×{h} px")
        prev = (f"aperçu texte Tk : police {self.font.cget('size')} pt, {len(self._tags)} couleurs en cache"
                if self.mode == "text" else f"aperçu image exact : cellule {self._cw}×{2 * self._cw} px")
        self.stats.configure(text=f"{self.art.cols} × {self.art.nrows} caractères\n"
                                  f"conversion {self.art.ms:.0f} ms · total {ms:.0f} ms\n{prev}")

    def _draw(self):
        if self.art is None:
            return
        if self.v_textprev.get() or ImageTk is None:
            self._show("text")
            self._fit()
            render_tk(self.prev, self.art, self._tags)
            return
        self._show("image")
        self.cv.update_idletasks()
        avail = max(200, self.cv.winfo_width() - 8)
        self._cw = cw = max(2, min(12, avail // max(1, self.art.cols)))
        img = render_image(self.art, cw)
        self._photo = ImageTk.PhotoImage(img, master=self.cv)
        self.cv.delete("all")
        x0 = max(0, (self.cv.winfo_width() - img.width) // 2)
        self.cv.create_image(x0, 4, anchor="nw", image=self._photo)
        self.cv.configure(scrollregion=(0, 0, max(img.width + x0, 1), img.height + 8))
        self.preview_img = img

    def _fit_later(self):
        if self.art is not None:
            if getattr(self, "_fitjob", None):
                self.d.after_cancel(self._fitjob)
            self._fitjob = self.d.after(200, self._refit)

    def _refit(self):
        self._fitjob = None
        if self.art is None:
            return
        if self.mode == "image":
            avail = max(200, self.cv.winfo_width() - 8)
            if max(2, min(12, avail // max(1, self.art.cols))) != getattr(self, "_cw", 0):
                self._draw()
        else:
            old = self.font.cget("size")
            self._fit()
            if self.font.cget("size") != old:
                pass  # la police nommée se met à jour toute seule

    _cw = 0

    def _fit(self):
        """Taille de police qui fait tenir la largeur dans l'aperçu (4 à 14 pt)."""
        if self.art is None:
            return
        self.prev.configure(font=self.font)
        avail = max(200, self.prev.winfo_width() - 16)
        availh = max(150, self.prev.winfo_height() - 16)
        best = 4
        fam = self.font.cget("family")
        for s in range(14, 3, -1):
            m = _MEASURE.get((fam, s))
            if m is None:
                f = tkfont.Font(family=fam, size=s)
                m = _MEASURE[(fam, s)] = (f.measure("▀" * 20) / 20, f.metrics("linespace"))
            cw, lh = m
            if cw * self.art.cols <= avail and (lh * self.art.nrows <= availh * 1.6 or s <= 6):
                best = s
                break
        if int(self.font.cget("size")) != best:
            self.font.configure(size=best)

    # ── sorties
    def _need(self) -> bool:
        if self.art is None:
            self._flash("Ouvre d'abord une image", bad=True)
            return False
        return True

    def copy(self, ansi: bool):
        if not self._need():
            return
        s = self.art.to_ansi("vt") if ansi else self.art.to_text()
        self.d.clipboard_clear()
        self.d.clipboard_append(s)
        self._flash(f"📋 Copié : {'ANSI avec couleurs' if ansi else 'texte simple'} ({self.art.nrows} lignes)")

    def _ask_save(self, ext: str, kind: str) -> str:
        base = os.path.splitext(self.src_name or "ansi")[0]
        base = re.sub(r"[^\w\-. ]+", "_", base).strip() or "ansi"
        d = self.hooks.get("default_dir", lambda: "")() or self.workdir
        return filedialog.asksaveasfilename(parent=self.d, title=f"Enregistrer {kind}", initialdir=d,
                                            initialfile=f"{base}_{self.art.style}{ext}", defaultextension=ext,
                                            filetypes=[(kind, "*" + ext), ("Tous", "*.*")])

    def _write(self, p: str, data: bytes) -> None:
        if os.path.exists(p):  # jamais d'écrasement sans copie
            try:
                import shutil
                shutil.copy2(p, p + time.strftime(".%Y%m%d_%H%M%S.bak"))
            except Exception:
                pass
        with open(p, "wb") as f:
            f.write(data)
        self._flash(f"💾 Enregistré : {p}")

    def save_ans(self, path: str = ""):
        if not self._need():
            return
        p = path or self._ask_save(".ans", "ANSI DOS")
        if p:
            self._write(p, self.art.to_ans_bytes(bool(self.v_sauce.get()), title=self.art.title))
        return p

    def save_txt(self, path: str = ""):
        if not self._need():
            return
        p = path or self._ask_save(".txt", "Texte")
        if p:
            self._write(p, self.art.to_text().encode("utf-8"))
        return p

    def save_html(self, path: str = ""):
        if not self._need():
            return
        p = path or self._ask_save(".html", "Page HTML")
        if p:
            self._write(p, self.art.to_html().encode("utf-8"))
        return p

    def html_tab(self):
        if not self._need():
            return
        f = self.hooks.get("new_tab")
        if not f:
            return self.save_html()
        base = re.sub(r"[^\w\-]+", "_", os.path.splitext(self.src_name or "ansi")[0]).strip("_")[:40] or "ansi"
        f(f"{base}_ansi.html", self.art.to_html())
        self._flash("🌐 Page HTML ouverte dans un onglet de l'Atelier (💾 puis 👁 Aperçu)")

    def insert_tab(self):
        if not self._need():
            return
        f = self.hooks.get("insert")
        if not f:
            return self.copy(False)
        what = f(self.art)
        self._flash(f"➕ Inséré dans l'onglet : {what or 'texte'}")

    def console(self):
        if not self._need():
            return
        try:
            os.makedirs(self.workdir, exist_ok=True)
            art_p = os.path.join(self.workdir, "_console_art.txt")
            with open(art_p, "w", encoding="utf-8", newline="\n") as f:
                f.write(self.art.to_ansi("vt"))
            run_p = os.path.join(self.workdir, "_console_ansi.py")
            cols, rows = max(80, self.art.cols + 2), max(30, min(9000, self.art.nrows + 6))
            with open(run_p, "w", encoding="utf-8") as f:
                f.write("import os, sys\n"
                        "if os.name == 'nt':\n"
                        f"    os.system('mode con: cols={cols} lines={rows} >nul 2>&1')\n"
                        "    os.system('title Padawan - ANSI')\n"
                        "    os.system('cls')\n"
                        f"sys.stdout.write(open({art_p!r}, encoding='utf-8').read())\n"
                        f"sys.stdout.write('\\x1b[0m\\n  {self.art.cols}x{self.art.nrows} - Entree pour fermer ')\n"
                        "sys.stdout.flush()\n"
                        "try:\n    input()\nexcept Exception:\n    pass\n")
            py = self.hooks.get("python", _console_python)()
            env = self.hooks.get("env", lambda: None)()
            self.console_proc = subprocess.Popen([py, run_p], cwd=self.workdir, env=env,
                                                 creationflags=0x00000010 if IS_WIN else 0)  # CREATE_NEW_CONSOLE
            self._flash("🖥 Console ouverte avec le vrai rendu ANSI")
            self.last_console = run_p
        except Exception as e:
            self._flash(f"Console impossible : {e}", bad=True)

    def reset(self):
        self.v_style.set("dos16"); self.v_width.set(80); self.v_bri.set(0); self.v_con.set(0)
        self.v_dither.set(True); self.v_invert.set(False); self.v_sauce.set(True)
        self.changed()

    # ── divers
    def _flash(self, msg: str, bad: bool = False):
        try:
            self.info.configure(text=msg, fg=self.C["bad"] if bad else self.C["ok"])
            self.d.after(3500, lambda: self.info.winfo_exists() and self.info.configure(
                fg=self.C["cyan"], text=(f"{self.src_name} · {self.src.size[0]}×{self.src.size[1]} px" if self.src else "")))
        except Exception:
            pass
        self.last_flash = msg
        f = self.hooks.get("flash")
        if f and not bad:
            try:
                f(msg)
            except Exception:
                pass

    def _log(self, m: str):
        try:
            self.hooks.get("log", print)(m)
        except Exception:
            pass

    def close(self):
        try:
            self.cfg.setdefault("ansi", {})["sauce"] = bool(self.v_sauce.get())
            self.save_cfg()
        except Exception as e:
            self._log(f"ansi cfg: {e}")
        try:
            self.d.destroy()
        except Exception:
            pass

    def exists(self) -> bool:
        try:
            return bool(self.d.winfo_exists())
        except Exception:
            return False


def _console_python() -> str:
    exe = sys.executable or "python"
    if exe.lower().endswith("pythonw.exe"):
        c = exe[:-11] + "python.exe"
        if os.path.isfile(c):
            return c
    return exe


def _mono_family(w: tk.Misc) -> str:
    fams = set(tkfont.families(w))
    for f in ("Cascadia Mono", "Consolas", "Lucida Console", "Courier New"):
        if f in fams:
            return f
    return "TkFixedFont"


class _Tip:
    def __init__(self, w, text):
        self.w, self.text, self.tw, self.job = w, text, None, None
        w.bind("<Enter>", lambda e: self._sched(), add="+")
        w.bind("<Leave>", lambda e: self._hide(), add="+")
        w.bind("<ButtonPress>", lambda e: self._hide(), add="+")

    def _sched(self):
        self.job = self.w.after(550, self._show)

    def _show(self):
        if self.tw:
            return
        try:
            self.tw = tk.Toplevel(self.w)
            self.tw.wm_overrideredirect(True)
            self.tw.wm_geometry(f"+{self.w.winfo_rootx() + 10}+{self.w.winfo_rooty() + self.w.winfo_height() + 4}")
            tk.Label(self.tw, text=self.text, bg="#fff8dc", fg="#222", font=("Segoe UI", 9), justify="left",
                     relief="solid", bd=1, padx=6, pady=3).pack()
        except tk.TclError:
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


if __name__ == "__main__":  # essai autonome :  python padawan_ansi.py [image]
    r = tk.Tk()
    r.withdraw()
    Cx = {"bg": "#0f131a", "panel": "#171d27", "card": "#222a37", "fg": "#f7f9fc", "dim": "#9aa4b8", "gold": "#e4c07a",
          "cyan": "#7ec8e8", "ok": "#7aefc0", "bad": "#f07178"}
    s = AnsiStudio(r, Cx, path=sys.argv[1] if len(sys.argv) > 1 else "")
    s.d.protocol("WM_DELETE_WINDOW", r.destroy)
    r.mainloop()
