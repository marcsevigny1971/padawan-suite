# -*- coding: utf-8 -*-
# Partie de archiveur5.py (découpage v1.2.2, comportement inchangé).
# Chargée par archiveur5.py dans un espace de noms commun : ne pas lancer seule.
from __future__ import annotations


_TkBase = tk.Tk if tk is not None else object


class ScrollFrame(tk.Frame if tk is not None else object):  # type: ignore[misc]
    """Canvas + Frame intérieur + barre verticale ; la largeur suit la fenêtre."""

    def __init__(self, master, bg=NC_BG, **kw):
        super().__init__(master, bg=bg, **kw)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0, yscrollincrement=24)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", self._on_inner)
        self.canvas.bind("<Configure>", self._on_canvas)

    def _on_inner(self, _e=None):
        bbox = self.canvas.bbox(self._win)
        if bbox:
            h = max(bbox[3], self.canvas.winfo_height())
            self.canvas.configure(scrollregion=(0, 0, bbox[2], h))

    def _on_canvas(self, e):
        self.canvas.itemconfigure(self._win, width=e.width)
        self._on_inner()

    def scroll_units(self, n: int) -> None:
        first, last = self.canvas.yview()
        if n < 0 and first <= 0.0:
            return
        if n > 0 and last >= 1.0:
            return
        self.canvas.yview_scroll(n, "units")

    def to_top(self) -> None:
        self.canvas.yview_moveto(0.0)

    def contains(self, widget) -> bool:
        try:
            return str(widget).startswith(str(self.inner)) or str(widget) == str(self.canvas)
        except Exception:
            return False


CONV_CHEERS = [
    (5, ["🚀 Ça décolle !", "🔧 Moteurs allumés…"]),
    (25, ["🛰 En orbite, tout roule", "💪 Ça avance bien"]),
    (45, ["🌠 Belle vitesse de croisière", "🎞 Les images défilent…"]),
    (60, ["🌗 À mi-chemin, capitaine", "☕ Le temps d'un café…"]),
    (80, ["🔥 Plus que la ligne droite", "🧭 Cap maintenu, ça file !"]),
    (100, ["🏁 Presque arrivé…", "✨ Les dernières images…"]),
]


def conv_cheer(pct: float, mode: str = "encode", done: bool = False) -> str:
    if done:
        return "Mission accomplie ✨"
    if mode == "remux":
        return "⚡ Déjà au bon format : rangement éclair"
    if mode == "audio":
        return "⚡ Vidéo déjà bonne : seul le son est converti"
    flip = int(time.time() // 6) % 2
    for lim, msgs in CONV_CHEERS:
        if pct < lim:
            return msgs[flip % len(msgs)]
    return CONV_CHEERS[-1][1][0]


def conv_detail(s: Dict[str, Any]) -> str:
    """Texte vivant : message encourageant · % · vitesse · temps restant."""
    pct = float(s.get("pct") or 0)
    parts = [conv_cheer(pct, str(s.get("mode") or "encode"), bool(s.get("done")))]
    parts.append(f"{pct:.0f} %")
    sp = fmt_speed(s.get("speed")) if (s.get("mode") == "encode" or s.get("done")) else ""
    if sp:
        parts.append(sp)
    if s.get("eta") and not s.get("done"):
        parts.append(f"reste ≈ {human_duration(s['eta']) if s['eta'] >= 1 else '0:01'}")
    enc = str(s.get("encoder") or "")
    if s.get("mode") == "encode" and enc in HW_ENCODERS:
        parts.append("GPU")
    return " · ".join(parts)


class FunBar(tk.Canvas if tk is not None else object):  # type: ignore[misc]
    """Barre de progression animée (rayures jaune/cyan qui défilent sur fond bleu foncé).
    Compatible avec l'API utilisée de ttk.Progressbar : configure(value=…)."""

    def __init__(self, master, width: int = 170, height: int = 16, **kw):
        super().__init__(master, width=width, height=height, highlightthickness=0, bd=0,
                         bg=NC_ENTRY_BG, **kw)
        self._value = 0.0
        self._mood = "normal"
        self._off = 0
        self._anim = None
        self._flash = 0
        self.bind("<Configure>", lambda e: self._draw())

    def set_mood(self, mood: str) -> None:
        if mood != self._mood:
            self._mood = mood
            self._draw()

    def configure(self, cnf=None, **kw):  # type: ignore[override]
        if isinstance(cnf, dict):
            kw = {**cnf, **kw}
            cnf = None
        val = kw.pop("value", None)
        for k in ("mode", "maximum", "orient", "length", "style"):
            kw.pop(k, None)
        r = super().configure(**kw) if kw else None
        if val is not None:
            try:
                v = max(0.0, min(100.0, float(val)))
            except (TypeError, ValueError):
                v = 0.0
            if v >= 100.0 and self._value < 100.0:
                self._flash = 12
            if v <= 0.0:
                self._mood = "normal"
            self._value = v
            self._draw()
            self._ensure_anim()
        return r

    config = configure  # type: ignore[assignment]

    def _ensure_anim(self):
        active = 0.0 < self._value < 100.0 or self._flash > 0
        if active and self._anim is None:
            self._anim = self.after(70, self._tick)

    def _tick(self):
        self._anim = None
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return
        self._off = (self._off + 2) % 14
        if self._flash > 0:
            self._flash -= 1
        self._draw()
        self._ensure_anim()

    def _draw(self):
        try:
            w = max(10, int(self.winfo_width()))
            h = max(6, int(self.winfo_height()))
        except Exception:
            return
        if w <= 10:
            w = int(self.cget("width") or 170)
            h = int(self.cget("height") or 16)
        self.delete("all")
        if str(tk.Canvas.cget(self, "bg")) != NC_ENTRY_BG:
            tk.Canvas.configure(self, bg=NC_ENTRY_BG)
        fw = int(w * self._value / 100.0)
        remux = self._mood == "remux"
        base, stripe = (NC_FG, NC_HI) if remux else (NC_HI, NC_FG)
        if self._flash > 0 and self._flash % 4 < 2:
            base, stripe = NC_OK, NC_HI
        if fw > 0:
            self.create_rectangle(0, 0, fw, h, fill=base, width=0)
            if 0 < self._value < 100:
                x = -h - 14 + self._off
                while x < fw:
                    pts = [max(0, min(fw, x)), h, max(0, min(fw, x + 6)), h,
                           max(0, min(fw, x + 6 + h)), 0, max(0, min(fw, x + h)), 0]
                    self.create_polygon(*pts, fill=stripe, width=0)
                    x += 14
                # petit éclat lumineux au bout de la barre
                self.create_rectangle(max(0, fw - 3), 0, fw, h, fill="#FFFFFF", width=0)
        self.create_rectangle(0, 0, w - 1, h - 1, outline=NC_FG, width=1)
        if self._value > 0:
            txt = f"{self._value:.0f} %"
            self.create_text(w // 2 + 1, h // 2 + 1, text=txt, fill="#000000", font=("Consolas", 8, "bold"))
            self.create_text(w // 2, h // 2, text=txt, fill="#FFFFFF", font=("Consolas", 8, "bold"))


class Tooltip:
    """Infobulle simple (survol 450 ms)."""

    def __init__(self, widget, text: str):
        self.widget, self.text = widget, text
        self._job = None
        self._tip = None
        widget.bind("<Enter>", self._enter, add="+")
        widget.bind("<Leave>", self._leave, add="+")
        widget.bind("<ButtonPress>", self._leave, add="+")

    def _enter(self, _e=None):
        self._cancel()
        self._job = self.widget.after(450, self._show)

    def _cancel(self):
        if self._job:
            try:
                self.widget.after_cancel(self._job)
            except Exception:
                pass
            self._job = None

    def _show(self):
        self._job = None
        if self._tip or not self.text:
            return
        try:
            x = self.widget.winfo_rootx() + 8
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
            tw = tk.Toplevel(self.widget)
            tw.wm_overrideredirect(True)
            try:
                tw.attributes("-topmost", True)
            except Exception:
                pass
            tk.Label(tw, text=self.text, bg=NC_TIP_BG, fg=NC_TIP_FG, font=FONT_SM, justify="left",
                     relief="solid", bd=1, padx=6, pady=3, wraplength=420).pack()
            tw.update_idletasks()
            sw = self.widget.winfo_screenwidth()
            if x + tw.winfo_reqwidth() > sw:
                x = max(0, sw - tw.winfo_reqwidth() - 4)
            tw.wm_geometry(f"+{x}+{y}")
            self._tip = tw
        except Exception:
            self._tip = None

    def _leave(self, _e=None):
        self._cancel()
        if self._tip:
            try:
                self._tip.destroy()
            except Exception:
                pass
            self._tip = None


class FlowFrame(tk.Frame if tk is not None else object):  # type: ignore[misc]
    """Cadre « à la ligne » : les enfants (ajoutés via add) passent à la ligne suivante
    quand la largeur manque — aucun libellé tronqué sur petit écran."""

    def __init__(self, master, bg=NC_BG, padx=4, pady=3, **kw):
        super().__init__(master, bg=bg, height=1, **kw)
        self._items: List[Any] = []
        self._padx, self._pady = padx, pady
        self._lastw = None
        self.bind("<Configure>", self._on_conf)

    def add(self, w, tip: str = ""):
        self._items.append(w)
        if tip:
            Tooltip(w, tip)
        self.after_idle(self.relayout)
        return w

    def set_visible(self, w, visible: bool):
        w._flow_hidden = not visible  # type: ignore[attr-defined]
        if not visible:
            w.place_forget()
        self.relayout()

    def _on_conf(self, e):
        if e.width != self._lastw:
            self._lastw = e.width
            self.relayout()

    def relayout(self):
        W = self.winfo_width()
        if W <= 1:
            W = max(400, self.winfo_toplevel().winfo_width() - 40)
        x = y = rowh = 0
        for w in self._items:
            if getattr(w, "_flow_hidden", False):
                continue
            rw, rh = w.winfo_reqwidth(), w.winfo_reqheight()
            if x > 0 and x + rw > W:
                x = 0
                y += rowh + self._pady
                rowh = 0
            w.place(x=x, y=y)
            x += rw + self._padx
            rowh = max(rowh, rh)
        h = max(1, y + rowh)
        try:
            if int(float(self.cget("height"))) != h:
                self.configure(height=h)
        except Exception:
            pass


class LightPlayer:
    """Lecteur intégré léger, sans installation : ffmpeg décode les images (rgb24 → Tk) et
    ffplay (fourni avec ffmpeg, sans fenêtre : -nodisp) joue le son. La vidéo se cale sur
    l'horloge audio lue dans la ligne d'état de ffplay → synchro stable. Pause / reprise /
    déplacement = relance des deux processus à la position voulue (seek précis via atrim)."""

    FPS_MAX = 25.0

    def __init__(self, app, surface, on_update: Callable[[float, float, str], None]):
        self.app = app
        self.surface = surface          # tk.Label qui affiche les images
        self.on_update = on_update      # (position, durée, état)
        self.path = ""
        self.duration = 0.0
        self.has_video = False
        self.src_w, self.src_h, self.src_fps = 0, 0, 25.0
        self.pos = 0.0
        self.state = "stop"             # stop | play | pause | end
        self.volume = 80
        self.muted = False
        self._pv = None
        self._pa = None
        self._q: "queue.Queue[Optional[bytes]]" = queue.Queue(maxsize=6)
        self._stop_evt = threading.Event()
        self._gen = 0
        self._t0 = 0.0
        self._aclock: Optional[Tuple[float, float]] = None
        self._size = (0, 0)
        self._frame_idx = 0
        self._photo = None
        self._tick_job = None
        self._reader_done = False
        self.last_error = ""

    # ---------------------------------------------------------------- chargement
    def load(self, path: str, info: Optional[Dict[str, Any]] = None) -> bool:
        self.stop()
        self.path = path
        self.pos = 0.0
        self.state = "stop"
        self.last_error = ""
        c = probe_codecs(path)
        self.duration = float(c.get("duration") or (info or {}).get("duration") or 0)
        self.has_video = bool(c.get("vcodec")) and path.lower().endswith(VIDEO_EXTS)
        self.src_w, self.src_h = int(c.get("width") or 0), int(c.get("height") or 0)
        self.src_fps = self._probe_fps(path) or 25.0
        return bool(self.duration)

    @staticmethod
    def _probe_fps(path: str) -> float:
        fp = find_ffprobe()
        if not fp:
            return 0.0
        try:
            r = subprocess.run([fp, "-v", "error", "-select_streams", "v:0", "-show_entries",
                                "stream=avg_frame_rate", "-of", "default=nw=1:nk=1", path],
                               **_hidden_kwargs(), timeout=20)
            txt = (r.stdout or b"").decode("ascii", "ignore").strip()
            if "/" in txt:
                a, b = txt.split("/", 1)
                return float(a) / float(b) if float(b) else 0.0
            return float(txt or 0)
        except Exception:
            return 0.0

    # ---------------------------------------------------------------- géométrie
    def _target_size(self, max_w: int, max_h: int) -> Tuple[int, int]:
        sw, sh = self.src_w or 640, self.src_h or 360
        scale = min(max_w / sw, max_h / sh, 2.0)
        w = max(160, int(sw * scale)) // 2 * 2
        h = max(90, int(sh * scale)) // 2 * 2
        if w * h > 960 * 540:  # limite CPU : ~qHD
            f = (960 * 540 / float(w * h)) ** 0.5
            w, h = int(w * f) // 2 * 2, int(h * f) // 2 * 2
        return w, h

    # ---------------------------------------------------------------- contrôle
    def current(self) -> float:
        if self.state != "play":
            return self.pos
        now = time.monotonic()
        if self._aclock and now - self._aclock[1] < 0.6:
            return min(self.duration or 1e9, self._aclock[0] + (now - self._aclock[1]))
        return min(self.duration or 1e9, self.pos + (now - self._t0))

    def play(self, max_w: int, max_h: int, at: Optional[float] = None) -> None:
        if not self.path:
            return
        if at is not None:
            self.pos = max(0.0, min(float(at), max(0.0, self.duration - 0.2) if self.duration else float(at)))
        elif self.state == "end":
            self.pos = 0.0
        self._kill()
        self._gen += 1
        gen = self._gen
        self._stop_evt = threading.Event()
        self._q = queue.Queue(maxsize=6)
        self._aclock = None
        self._frame_idx = 0
        self._reader_done = not self.has_video
        ff = find_ffmpeg()
        fps = min(self.FPS_MAX, self.src_fps or 25.0)
        self._fps = fps
        if self.has_video and ff:
            w, h = self._target_size(max_w, max_h)
            self._size = (w, h)
            cmd = [ff, "-hide_banner", "-nostdin", "-loglevel", "error", "-ss", f"{self.pos:.3f}", "-i", self.path,
                   "-an", "-sn", "-vf", f"fps={fps:.3f},scale={w}:{h}:flags=bilinear",
                   "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"]
            kw = _hidden_kwargs()
            kw["stderr"] = subprocess.DEVNULL
            kw["bufsize"] = w * h * 3 * 2
            try:
                self._pv = subprocess.Popen(cmd, **kw)
                threading.Thread(target=self._reader, args=(self._pv, w * h * 3, self._q, self._stop_evt),
                                 daemon=True).start()
            except Exception as e:
                self.last_error = f"vidéo : {e}"
                self._reader_done = True
        self._start_audio(gen)
        self._t0 = time.monotonic()
        self.state = "play"
        self._schedule()

    def _start_audio(self, gen: int) -> None:
        fpl = find_ffplay()
        if not fpl or self.muted or self.volume <= 0:
            self._pa = None
            return
        cmd = [fpl, "-hide_banner", "-nodisp", "-vn", "-sn", "-autoexit", "-loglevel", "error", "-stats",
               "-volume", str(int(self.volume))]
        if self.pos > 0.05:
            cmd += ["-ss", f"{self.pos:.3f}", "-af", f"atrim=start={self.pos:.3f}"]
        cmd.append(self.path)
        kw = _hidden_kwargs()
        kw["stdout"] = subprocess.DEVNULL
        try:
            self._pa = subprocess.Popen(cmd, **kw)
            threading.Thread(target=self._audio_clock, args=(self._pa, gen), daemon=True).start()
        except Exception as e:
            self._pa = None
            self.last_error = f"son : {e}"

    def _audio_clock(self, proc, gen: int) -> None:
        buf = b""
        rx = re.compile(rb"^\s*(-?\d+\.\d+)\s+M-A")
        try:
            while True:
                ch = proc.stderr.read(64)
                if not ch:
                    break
                buf += ch
                parts = re.split(rb"[\r\n]", buf)
                buf = parts[-1]
                for ln in parts[:-1]:
                    m = rx.match(ln)
                    if m and gen == self._gen:
                        v = float(m.group(1))
                        if v >= 0:
                            self._aclock = (v, time.monotonic())
        except Exception:
            pass

    @staticmethod
    def _reader(proc, nbytes: int, q, stop_evt) -> None:
        try:
            while not stop_evt.is_set():
                data = proc.stdout.read(nbytes)
                if not data or len(data) < nbytes:
                    break
                while not stop_evt.is_set():
                    try:
                        q.put(data, timeout=0.2)
                        break
                    except queue.Full:
                        continue
        except Exception:
            pass
        finally:
            try:
                q.put(None, timeout=1)
            except Exception:
                pass

    def _schedule(self) -> None:
        if self._tick_job is None:
            self._tick_job = self.app.after(15, self._tick)

    def _tick(self) -> None:
        self._tick_job = None
        if self.state != "play":
            return
        cur = self.current()
        if self.has_video and not self._reader_done:
            target = int((cur - self.pos) * self._fps)
            frame = None
            while self._frame_idx <= target:
                try:
                    item = self._q.get_nowait()
                except queue.Empty:
                    break
                if item is None:
                    self._reader_done = True
                    break
                frame = item
                self._frame_idx += 1
            if frame is not None:
                self._show_frame(frame)
        ended = self.duration and cur >= self.duration - 0.05
        audio_dead = self._pa is None or self._pa.poll() is not None
        if ended or (self._reader_done and audio_dead and (not self.has_video or cur >= self.duration - 0.5)):
            self.pos = self.duration if self.duration else cur
            self._kill()
            self.state = "end"
            self.on_update(self.pos, self.duration, self.state)
            return
        self.on_update(cur, self.duration, self.state)
        self._tick_job = self.app.after(15, self._tick)

    def _show_frame(self, data: bytes) -> None:
        if not HAS_PIL:
            return
        w, h = self._size
        try:
            im = Image.frombuffer("RGB", (w, h), data, "raw", "RGB", 0, 1)
            if self._photo is None or (self._photo.width(), self._photo.height()) != (w, h):
                self._photo = ImageTk.PhotoImage(im)
                self.surface.configure(image=self._photo, text="", height=h)
            else:
                self._photo.paste(im)
        except Exception:
            logger.exception("image lecteur")

    def show_still(self, max_w: int, max_h: int, at: float) -> None:
        """Affiche l'image à la position donnée (pause / déplacement)."""
        ff = find_ffmpeg()
        if not (self.has_video and ff and HAS_PIL):
            return
        w, h = self._target_size(max_w, max_h)
        try:
            r = subprocess.run([ff, "-hide_banner", "-nostdin", "-loglevel", "error", "-ss", f"{max(0.0, at):.3f}",
                                "-i", self.path, "-frames:v", "1", "-an", "-sn", "-vf", f"scale={w}:{h}",
                                "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"], **_hidden_kwargs(), timeout=20)
            data = r.stdout or b""
            if len(data) >= w * h * 3:
                self._size = (w, h)
                self._show_frame(data[:w * h * 3])
        except Exception:
            logger.exception("image fixe")

    def pause(self) -> None:
        if self.state == "play":
            self.pos = self.current()
            self._kill()
            self.state = "pause"
            self.on_update(self.pos, self.duration, self.state)

    def seek(self, t: float, max_w: int, max_h: int) -> None:
        t = max(0.0, min(float(t), self.duration or float(t)))
        if self.state == "play":
            self.play(max_w, max_h, at=t)
        else:
            self.pos = t
            if self.state == "end":
                self.state = "pause"
            if self.state == "stop":
                self.state = "pause"
            self.show_still(max_w, max_h, t)
            self.on_update(self.pos, self.duration, self.state)

    def set_volume(self, vol: int, muted: Optional[bool] = None) -> None:
        self.volume = max(0, min(100, int(vol)))
        if muted is not None:
            self.muted = bool(muted)
        if self.state == "play":
            cur = self.current()
            if self._pa is not None:
                try:
                    self._pa.kill()
                except Exception:
                    pass
            self._pa = None
            self._aclock = None
            # recaler l'horloge locale sur la position actuelle avant de relancer le son
            self._frame_idx = int((cur - self.pos) * self._fps)
            self._t0 = time.monotonic() - (cur - self.pos)
            saved = self.pos
            self.pos = cur
            self._gen += 0
            self._start_audio(self._gen)
            self.pos = saved

    def stop(self) -> None:
        self._kill()
        self.state = "stop"
        self.pos = 0.0
        self._photo = None

    def _kill(self) -> None:
        if self._tick_job is not None:
            try:
                self.app.after_cancel(self._tick_job)
            except Exception:
                pass
            self._tick_job = None
        self._stop_evt.set()
        for p in (self._pv, self._pa):
            if p is not None:
                try:
                    p.kill()
                except Exception:
                    pass
                try:
                    p.wait(timeout=2)
                except Exception:
                    pass
        self._pv = self._pa = None
        self._aclock = None


COLL_ALL_LABEL = "Toutes collections"
PLAT_ALL_LABEL = "Toutes plateformes"
GUI_ONLINE = {"online": ("●", "en ligne"), "offline": ("✖", "supprimé / introuvable"),
              "restricted": ("⚠", "accès restreint (privé, connexion…)"), "unknown": ("?", "inconnu (non vérifiable)")}


def online_color(st: str) -> str:
    return {"online": NC_OK, "offline": NC_ERR, "restricted": NC_WARN}.get(st, NC_DIM)


def wrap_name(name: str, width: int = 22, lines: int = 2) -> str:
    """Nom de fichier sur 2 lignes max (coupure après _ - . ou espace), sans rien cacher d'important."""
    if len(name) <= width:
        return name
    out, rest = [], name
    while rest and len(out) < lines:
        if len(rest) <= width or len(out) == lines - 1:
            if len(rest) > width:
                base, ext = os.path.splitext(rest)
                keep = width - len(ext) - 1
                rest = base[:max(4, keep)] + "…" + ext
            out.append(rest)
            break
        cut = max(rest.rfind(c, 0, width) for c in "_- .")
        cut = cut + 1 if cut >= width // 2 else width
        out.append(rest[:cut])
        rest = rest[cut:]
    return "\n".join(out)


HELP_TEXT: List[Tuple[str, str]] = [
    ("h", "📋 Archiver"),
    ("p", "Copie un lien (X, Facebook, YouTube, TikTok, Instagram, article de presse, n'importe quelle page web) "
          "puis clique « 📋 Coller et archiver » ou fais Ctrl+V n'importe où dans la fenêtre. Tu peux aussi "
          "glisser-déposer un lien (ou un fichier .txt de liens) sur la fenêtre."),
    ("p", "Les vidéos sont enregistrées en MP4 lisible partout, avec texte du post, miniature, sous-titres, "
          "transcription et storyboard. Les pages web sont archivées en « lecture » (texte propre), copie "
          "complète hors ligne, capture d'écran et PDF. Pour X, le fil (messages précédents) est aussi gardé."),
    ("h", "▶ Lecteur intégré"),
    ("p", "▶ Lire (ou clic sur l'image) lit la vidéo directement dans l'aperçu : barre de position, ±10 s, volume. "
          "« ⛶ Grande fenêtre » (ou double-clic sur l'image) l'ouvre dans une fenêtre séparée. "
          "« ↗ Externe » utilise le lecteur Windows / VLC / mpv."),
    ("h", "🗣 Transcription"),
    ("p", "Les sous-titres (YouTube…) deviennent une transcription horodatée : clic sur [m:ss] = lecture à cet "
          "endroit, champ 🔎 pour chercher, et la recherche de l'historique fouille aussi dedans. "
          "Sans sous-titres : « 🎙 Transcrire (local) » si Whisper est installé (rien n'est envoyé en ligne)."),
    ("h", "✂ Outils média"),
    ("p", "Capture d'image, extrait vidéo, MP3, GIF animé à partir de n'importe quelle archive vidéo. "
          "Mets la vidéo en pause au bon endroit puis « = position du lecteur ». Résultat dans extraits/."),
    ("h", "🗂 Comment ranger ?"),
    ("p", "À gauche, la barre « 📚 Collections » : clic sur une collection = tu ne vois qu'elle ; « 🗂 Toutes » = tout. "
          "« 📥 Non classées » montre ce qui reste à ranger."),
    ("p", "Pour ranger une archive : clique « ✔ Oui » sur le bandeau jaune « Ranger dans … ? » au-dessus de l'aperçu "
          "(ou « Autre… » pour choisir), ou clic droit → 📂 Déplacer vers la collection… (marche aussi sur plusieurs "
          "archives choisies avec Ctrl+clic). « ✨ Ranger tout automatiquement » range d'un coup les non classées : "
          "tu vois la liste avant, et « ↩ Annuler le rangement » remet tout comme avant."),
    ("h", "🎞 Storyboard"),
    ("p", "Une rangée de petites images tirées de la vidéo (une à intervalles réguliers). Il se prépare tout seul en "
          "quelques secondes. Clique sur une image : la vidéo part à ce moment-là."),
    ("h", "★ Favoris et 📚 collections"),
    ("p", "Ctrl+D ou « ☆ Favori ». Clic droit sur une ou plusieurs archives → 📚 Collections pour les classer "
          "(Recettes, Politique…). Le menu « Collection » au-dessus de l'historique filtre la liste. "
          "Ctrl+clic / Maj+clic = sélection multiple ; Ctrl+A = tout sélectionner."),
    ("h", "🧰 Outils"),
    ("p", "Vérifier les archives (fichiers manquants ou corrompus, réparation en un clic) · vérifier si les "
          "originaux sont encore en ligne (✖ supprimé : ton archive est alors la seule copie) · statistiques · "
          "export ZIP à partager (avec une page index.html) · catalogue CSV pour Excel · mise à jour de yt-dlp."),
    ("h", "⌨ Raccourcis clavier"),
    ("k", "Ctrl+V|coller et archiver (hors champs texte)"),
    ("k", "Entrée|archiver le(s) lien(s) du champ"),
    ("k", "Ctrl+Espace|lecture / pause du lecteur intégré"),
    ("k", "Ctrl+← / Ctrl+→|reculer / avancer de 10 s"),
    ("k", "Ctrl+F|chercher dans l'historique"),
    ("k", "Ctrl+D|favori oui / non"),
    ("k", "Ctrl+E|exporter la sélection en ZIP"),
    ("k", "Ctrl+A|tout sélectionner (historique)"),
    ("k", "Ctrl+S|enregistrer tags et notes"),
    ("k", "F2|renommer l'archive"),
    ("k", "F5|relire le dossier des archives"),
    ("k", "Suppr|supprimer (confirmation)"),
    ("k", "Ctrl+molette, Ctrl +/−/0|taille du texte"),
    ("k", "Échap|replier la file d'attente / fermer une fenêtre"),
    ("k", "F1|cette aide"),
    ("h", "🔒 Confidentialité"),
    ("p", "Tout est stocké sur ce PC. Seuls les sites d'origine sont contactés (et api.fxtwitter.com pour X si "
          "l'option est active). La vérification « en ligne » interroge uniquement l'adresse d'origine."),
]
