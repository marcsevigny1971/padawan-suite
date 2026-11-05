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
    MAX_PIX = 960 * 540

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
        mp = self.MAX_PIX
        if w * h > mp:  # limite CPU : ~qHD (plus grand dans la grande fenêtre)
            f = (mp / float(w * h)) ** 0.5
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


class BigPlayerWindow(tk.Toplevel if tk is not None else object):  # type: ignore[misc]
    """« Grande fenêtre » avec ses propres contrôles (lecture/pause, ±10 s, barre de
    position, volume, plein écran, fermer). Souris ET clavier ; la barre reste toujours visible
    (en plein écran elle se replie et réapparaît dès que la souris bouge)."""

    def __init__(self, app, path: str, info: Dict[str, Any], at: float, title: str):
        super().__init__(app)
        self.app = app
        self.title(title)
        self.configure(bg="#000000")
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w = min(1280, int(sw * 0.7))
        h = int(w * 9 / 16) + 90
        self.geometry(f"{w}x{h}+{max(0, (sw - w) // 2)}+{max(0, (sh - h) // 3)}")
        self.minsize(480, 320)
        self._full = False
        self._drag = False
        self._hide_job = None
        self._resize_job = None
        self._last_size = (0, 0)
        self.video = tk.Label(self, bg="#000000", fg=NC_DIM, text="Chargement…", font=FONT_UI, cursor="hand2")
        self.video.pack(fill="both", expand=True)
        self.bar = tk.Frame(self, bg=NC_PANEL, bd=0)
        self.bar.pack(fill="x", side="bottom")
        self.pos_var = tk.DoubleVar(value=float(at or 0))
        self.pos_scale = ttk.Scale(self.bar, from_=0, to=1, variable=self.pos_var, orient="horizontal",
                                   style="Arch.Horizontal.TScale", command=lambda v: self._on_drag(), takefocus=0)
        self.pos_scale.pack(fill="x", padx=10, pady=(6, 2))
        self.pos_scale.bind("<ButtonPress-1>", self._seek_press)
        self.pos_scale.bind("<ButtonRelease-1>", self._seek_release)
        Tooltip(self.pos_scale, "Clique ou glisse pour te déplacer dans la vidéo (← / → = ±5 s)")
        row = tk.Frame(self.bar, bg=NC_PANEL)
        row.pack(fill="x", padx=8, pady=(0, 6))
        B = lambda t, c, tip, hi=False, side="left": self._b(row, t, c, tip, hi, side)
        self.b_play = B("▶ Lecture", self.toggle, "Lecture / pause (Espace ou K, ou clic sur l'image)", True)
        B("⏪ 10 s", lambda: self.skip(-10), "Reculer de 10 secondes (J, ou Maj+←)")
        B("10 s ⏩", lambda: self.skip(10), "Avancer de 10 secondes (L, ou Maj+→)")
        self.lbl_time = tk.Label(row, text="0:00 / 0:00", bg=NC_PANEL, fg=NC_HI, font=FONT_MONO, padx=8)
        self.lbl_time.pack(side="left")
        B("✖ Fermer", self.close, "Fermer la grande fenêtre (Échap ; en plein écran, Échap sort d'abord du plein écran)",
          side="right")
        self.b_full = B("⛶ Plein écran", self.toggle_full, "Plein écran (F ou F11, ou double-clic sur l'image)",
                        side="right")
        self.lbl_vol = tk.Label(row, text="", bg=NC_PANEL, fg=NC_FG, font=FONT_SM, width=4, anchor="w")
        self.lbl_vol.pack(side="right")
        self.vol_var = tk.DoubleVar(value=float(app.vol_var.get() or 0))
        self.vol_scale = ttk.Scale(row, from_=0, to=100, variable=self.vol_var, orient="horizontal", length=120,
                                   style="Arch.Horizontal.TScale", command=lambda v: self._vol_label(), takefocus=0)
        self.vol_scale.pack(side="right", padx=4)
        self.vol_scale.bind("<ButtonRelease-1>", lambda e: self._apply_volume())
        Tooltip(self.vol_scale, "Volume (↑ / ↓)")
        self.b_mute = B("🔊", self.mute, "Couper / remettre le son (M)", side="right")
        self.player = LightPlayer(self, self.video, self._on_update)
        self.player.MAX_PIX = 1600 * 900   # grande fenêtre : plus d'images, plus nettes
        self.player.muted = bool(getattr(app, "_muted", False))
        self.player.volume = int(self.vol_var.get())
        self.player.load(path, info)
        if self.player.duration:
            self.pos_scale.configure(to=max(1.0, self.player.duration))
        self._vol_label()
        for seq, fn in (("<space>", self.toggle), ("k", self.toggle), ("K", self.toggle),
                        ("f", self.toggle_full), ("F", self.toggle_full), ("<F11>", self.toggle_full),
                        ("<Escape>", self._escape), ("m", self.mute), ("M", self.mute),
                        ("<Left>", lambda: self.skip(-5)), ("<Right>", lambda: self.skip(5)),
                        ("<Shift-Left>", lambda: self.skip(-10)), ("<Shift-Right>", lambda: self.skip(10)),
                        ("j", lambda: self.skip(-10)), ("l", lambda: self.skip(10)),
                        ("<Up>", lambda: self.nudge_vol(5)), ("<Down>", lambda: self.nudge_vol(-5)),
                        ("<Home>", lambda: self.seek(0))):
            self.bind(seq, lambda e, f=fn: (f(), "break")[1])
        self.video.bind("<Button-1>", lambda e: self.toggle())
        self.video.bind("<Double-Button-1>", lambda e: self.toggle_full())
        self.bind("<MouseWheel>", lambda e: self.nudge_vol(5 if e.delta > 0 else -5))
        self.bind("<Motion>", self._show_bar)
        self.bind("<Configure>", self._on_resize)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(120, lambda: (self.focus_force(), self.play(at)))

    def _b(self, row, text, cmd, tip, hi, side):
        b = self.app._btn(row, text, cmd, hi=hi, font=FONT_UI)
        b.configure(takefocus=0)  # Espace / flèches vont toujours à la fenêtre (pas de double action)
        b.pack(side=side, padx=3)
        Tooltip(b, tip)
        return b

    def _box(self) -> Tuple[int, int]:
        self.update_idletasks()
        return max(160, self.video.winfo_width()), max(90, self.video.winfo_height())

    # ------------------------------------------------------------ commandes
    def play(self, at: Optional[float] = None):
        w, h = self._box()
        self._last_size = (w, h)
        if self.player.state == "end":
            at = 0.0
        self.player.play(w, h, at=at)

    def toggle(self):
        if self.player.state == "play":
            self.player.pause()
        else:
            self.play(float(self.pos_var.get() or 0))

    def skip(self, d: float):
        cur = self.player.current() if self.player.state == "play" else float(self.pos_var.get() or 0)
        self.seek(cur + d)

    def seek(self, t: float):
        t = max(0.0, min(float(t), self.player.duration or float(t)))
        self.pos_var.set(t)
        w, h = self._box()
        self.player.seek(t, w, h)
        self._show_time(t)

    def mute(self):
        self.player.set_volume(int(float(self.vol_var.get())), not self.player.muted)
        self._vol_label()

    def nudge_vol(self, d: int):
        self.vol_var.set(max(0, min(100, int(float(self.vol_var.get())) + d)))
        self._apply_volume()

    def _apply_volume(self):
        v = int(float(self.vol_var.get()))
        self.player.set_volume(v, False if v > 0 else self.player.muted)
        self._vol_label()

    def _vol_label(self):
        v = int(float(self.vol_var.get()))
        self.lbl_vol.configure(text=f"{v}%")
        self.b_mute.configure(text="🔇" if (self.player.muted or v == 0) else "🔊")

    def toggle_full(self):
        self._full = not self._full
        self.attributes("-fullscreen", self._full)
        self.b_full.configure(text="🗗 Quitter plein écran" if self._full else "⛶ Plein écran")
        self._show_bar()

    def _escape(self):
        if self._full:
            self.toggle_full()
        else:
            self.close()

    # ------------------------------------------------------------ barre / position
    def _show_bar(self, e=None):
        if not self.bar.winfo_ismapped():
            self.bar.pack(fill="x", side="bottom", before=self.video)
        if self._hide_job:
            self.after_cancel(self._hide_job)
            self._hide_job = None
        if self._full:  # en plein écran : se replie après 3 s sans bouger la souris
            self._hide_job = self.after(3000, self._auto_hide)

    def _auto_hide(self):
        self._hide_job = None
        if self._full and self.player.state == "play" and not self._drag:
            self.bar.pack_forget()

    def _on_resize(self, e):
        if e.widget is not self:
            return
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(350, self._refit)

    def _refit(self):
        self._resize_job = None
        w, h = self._box()
        if abs(w - self._last_size[0]) < 24 and abs(h - self._last_size[1]) < 24:
            return
        self._last_size = (w, h)
        if self.player.state == "play":
            self.player.play(w, h, at=self.player.current())
        elif self.player.path:
            self.player.show_still(w, h, float(self.pos_var.get() or 0))

    def _on_drag(self):
        if self._drag:
            self._show_time(float(self.pos_var.get()))

    def _seek_press(self, e):
        self._drag = True
        try:  # clic direct = aller à cet endroit
            wd = max(1, self.pos_scale.winfo_width())
            self.pos_var.set(max(0.0, min(1.0, e.x / wd)) * float(self.pos_scale.cget("to")))
        except Exception:
            pass

    def _seek_release(self, e):
        self._drag = False
        self.seek(float(self.pos_var.get()))

    def _show_time(self, pos: float):
        dur = self.player.duration
        self.lbl_time.configure(text=f"{fmt_ts(pos)} / {fmt_ts(dur) if dur else '—'}")

    def _on_update(self, pos: float, dur: float, state: str):
        if not self._drag:
            self.pos_var.set(pos)
            self._show_time(pos)
        self.b_play.configure(text="⏸ Pause" if state == "play" else "▶ Lecture")
        if state != "play":
            self._show_bar()

    def close(self):
        pos = self.player.current() if self.player.state == "play" else float(self.pos_var.get() or 0)
        try:
            self.player.stop()
        except Exception:
            pass
        try:
            self.app._bigwin_closed(pos)
        except Exception:
            logger.exception("retour grande fenêtre")
        self.destroy()


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
