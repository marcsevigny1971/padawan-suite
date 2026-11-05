# -*- coding: utf-8 -*-
# Partie de grimoire1.py (découpage v1.2.2, comportement inchangé).
# Chargée par grimoire1.py dans un espace de noms commun : ne pas lancer seule.
from __future__ import annotations



# ================================================================ interface : utilitaires
TK9 = False


def tk_col(line: str, i: int) -> int:
    """Index Python -> colonne Tk (Tk 8.6 compte les emoji hors BMP comme 2 caracteres)."""
    if TK9:
        return i
    return len(line[:i].encode("utf-16-le")) // 2


def apply_styles(root) -> None:
    st = ttk.Style(root)
    try:
        st.theme_use("clam")
    except tk.TclError:
        pass
    lh = tkfont.Font(font=fnt("GUI")).metrics("linespace")
    st.configure(".", background=C["BG"], foreground=C["FG"], fieldbackground=C["ENTRY_BG"], font=fnt("GUI"),
                 bordercolor=C["LINE"], lightcolor=C["PANEL"], darkcolor=C["PANEL"], troughcolor=C["PANEL"],
                 selectbackground=C["SEL"], selectforeground=C["ON_SEL"], insertcolor=C["ENTRY_FG"])
    st.configure("TFrame", background=C["BG"])
    st.configure("TLabel", background=C["BG"], foreground=C["FG"])
    st.configure("Treeview", background=C["CARD"], fieldbackground=C["CARD"], foreground=C["TEXT"],
                 rowheight=lh + 8, font=fnt("GUI"), borderwidth=0)
    st.map("Treeview", background=[("selected", C["SEL"])], foreground=[("selected", C["ON_SEL"])])
    st.configure("Treeview.Heading", background=C["PANEL"], foreground=C["HI"], font=fnt("GHead"), relief="flat")
    st.map("Treeview.Heading", background=[("active", C["HOVER"])])
    st.configure("Subj.Treeview", background=C["PANEL"], fieldbackground=C["PANEL"], foreground=C["TEXT"], rowheight=lh + 9)
    st.configure("TCombobox", fieldbackground=C["ENTRY_BG"], background=C["BTN"], foreground=C["ENTRY_FG"],
                 arrowcolor=C["FG"], selectbackground=C["ENTRY_BG"], selectforeground=C["ENTRY_FG"], padding=2)
    st.map("TCombobox", fieldbackground=[("readonly", C["ENTRY_BG"])], foreground=[("readonly", C["ENTRY_FG"])],
           selectbackground=[("readonly", C["ENTRY_BG"])], selectforeground=[("readonly", C["ENTRY_FG"])])
    root.option_add("*TCombobox*Listbox.background", C["ENTRY_BG"])
    root.option_add("*TCombobox*Listbox.foreground", C["ENTRY_FG"])
    root.option_add("*TCombobox*Listbox.selectBackground", C["SEL"])
    root.option_add("*TCombobox*Listbox.selectForeground", C["ON_SEL"])
    root.option_add("*TCombobox*Listbox.font", fnt("GUI"))
    for orient in ("Vertical", "Horizontal"):
        st.configure(f"{orient}.TScrollbar", background=C["BTN"], troughcolor=C["PANEL"], arrowcolor=C["FG"],
                     bordercolor=C["LINE"], gripcount=0, arrowsize=16)
        st.map(f"{orient}.TScrollbar", background=[("active", C["HOVER"])])
    st.configure("TNotebook", background=C["PANEL"], borderwidth=0, tabmargins=(4, 4, 4, 0))
    st.configure("TNotebook.Tab", background=C["BTN"], foreground=C["TEXT"], padding=(10, 3), font=fnt("GUI"),
                 bordercolor=C["LINE"], lightcolor=C["PANEL"])
    st.map("TNotebook.Tab", background=[("selected", C["HI"]), ("active", C["HOVER"])],
           foreground=[("selected", C["ON_HI"])])
    st.configure("TCheckbutton", background=C["BG"], foreground=C["TEXT"], indicatorbackground=C["ENTRY_BG"])
    st.configure("Horizontal.TProgressbar", background=C["OK"], troughcolor=C["ENTRY_BG"], bordercolor=C["LINE"])


def mk_button(parent, text: str, cmd: Callable, kind: str = "", width: int = 0, tip: str = "", font_name: str = "GUI"):
    """Bouton plat aux couleurs du theme. kind : '' | 'accent' | 'danger' | 'ghost'."""
    bg, fg, abg, afg = C["BTN"], C["BTN_FG"], C["HI"], C["ON_HI"]
    if kind == "accent":
        bg, fg, abg, afg = C["HI"], C["ON_HI"], C["HI_ACT"], C["ON_HI"]
    elif kind == "danger":
        bg, fg = C["BTN"], C["ERR"]
    elif kind == "ghost":
        bg = parent.cget("bg") if "bg" in parent.keys() else C["BG"]
    elif kind == "rec":
        bg, fg, abg, afg = "#AA0000", "#FFFFFF", "#FF3333", "#FFFFFF"
    b = tk.Button(parent, text=text, command=cmd, bg=bg, fg=fg, activebackground=abg, activeforeground=afg,
                  relief="flat", bd=0, highlightthickness=1, highlightbackground=C["LINE"], padx=9, pady=3,
                  font=fnt(font_name if kind != "accent" else "GUIB"), cursor="hand2", disabledforeground=C["DISABLED"])
    if width:
        b.configure(width=width)
    b._colors = (bg, fg, abg, afg)  # type: ignore[attr-defined]
    b.bind("<Enter>", lambda _e: b.configure(bg=b._colors[2], fg=b._colors[3]) if str(b["state"]) != "disabled" else None)
    b.bind("<Leave>", lambda _e: b.configure(bg=b._colors[0], fg=b._colors[1]))
    if tip:
        Tooltip(b, tip)
    return b


def mk_entry(parent, var=None, width: int = 30, font_name: str = "GUI"):
    return tk.Entry(parent, textvariable=var, width=width, bg=C["ENTRY_BG"], fg=C["ENTRY_FG"], insertbackground=C["HI"],
                    relief="flat", highlightthickness=1, highlightbackground=C["LINE"], highlightcolor=C["HI"],
                    font=fnt(font_name), selectbackground=C["SEL"], selectforeground=C["ON_SEL"],
                    disabledbackground=C["PANEL"], readonlybackground=C["ENTRY_BG"])


def mk_text(parent, height: int = 4, width: int = 40, font_name: str = "GMono", wrap: str = "word"):
    return tk.Text(parent, height=height, width=width, bg=C["ENTRY_BG"], fg=C["ENTRY_FG"], insertbackground=C["HI"],
                   relief="flat", highlightthickness=1, highlightbackground=C["LINE"], highlightcolor=C["HI"],
                   font=fnt(font_name), wrap=wrap, selectbackground=C["SEL"], selectforeground=C["ON_SEL"], undo=True,
                   padx=6, pady=4)


def mk_label(parent, text: str = "", key: str = "FG", font_name: str = "GUI", bg: str = "", **kw):
    return tk.Label(parent, text=text, fg=C[key], bg=bg or parent.cget("bg"), font=fnt(font_name), **kw)


def mk_link(parent, text: str, target: str, bg: str = "", font_name: str = "GUI", wrap: int = 0, cmd: Optional[Callable] = None):
    """Libelle cliquable (souligne, curseur main) : ouvre un lien, un fichier ou appelle cmd."""
    f = fnt(font_name)
    try:
        uf = tkfont.Font(font=f)
        uf.configure(underline=True)
    except Exception:
        uf = f
    lab = tk.Label(parent, text=text, fg=C["LINK"], bg=bg or parent.cget("bg"), font=uf, cursor="hand2",
                   justify="left", anchor="w", wraplength=wrap or 0)
    lab._ufont = uf  # type: ignore[attr-defined]
    lab.bind("<Button-1>", lambda _e: cmd() if cmd else (open_url(target) if re.match(r"(?i)^(https?://|www\.)", target)
                                                          else open_path(target)))
    Tooltip(lab, target if not cmd else "")
    return lab


def mk_check(parent, text: str, var, bg: str = "", cmd: Optional[Callable] = None):
    b = bg or parent.cget("bg")
    return tk.Checkbutton(parent, text=text, variable=var, bg=b, fg=C["TEXT"], selectcolor=C["ENTRY_BG"],
                          activebackground=b, activeforeground=C["HI"], font=fnt("GUI"), anchor="w",
                          highlightthickness=0, bd=0, command=cmd)


def style_menu(m) -> None:
    m.configure(bg=C["PANEL"], fg=C["TEXT"], activebackground=C["SEL"], activeforeground=C["ON_SEL"],
                font=fnt("GUI"), tearoff=0, relief="flat", bd=1, selectcolor=C["HI"], disabledforeground=C["DISABLED"])


def new_menu(parent):
    m = tk.Menu(parent, tearoff=0)
    style_menu(m)
    return m


def popup(m, e) -> None:
    try:
        m.tk_popup(e.x_root, e.y_root)
    finally:
        try:
            m.grab_release()
        except Exception:
            pass


class Tooltip:
    """Infobulle simple (delai 500 ms)."""

    def __init__(self, widget, text: Any, delay: int = 500):
        self.w = widget
        self.text = text
        self.delay = delay
        self.tip = None
        self.job = None
        widget.bind("<Enter>", self._sched, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _sched(self, _e=None):
        self._cancel()
        self.job = self.w.after(self.delay, self._show)

    def _cancel(self):
        if self.job:
            try:
                self.w.after_cancel(self.job)
            except Exception:
                pass
            self.job = None

    def _show(self):
        txt = self.text() if callable(self.text) else self.text
        if not txt:
            return
        try:
            self.tip = show_tip(self.w, txt, self.w.winfo_pointerx() + 14, self.w.winfo_pointery() + 18)
        except tk.TclError:
            self.tip = None

    def _hide(self, _e=None):
        self._cancel()
        if self.tip is not None:
            try:
                self.tip.destroy()
            except Exception:
                pass
            self.tip = None


def show_tip(widget, txt: str, x: int, y: int):
    tw = tk.Toplevel(widget)
    tw.wm_overrideredirect(True)
    try:
        tw.attributes("-topmost", True)
    except tk.TclError:
        pass
    tk.Label(tw, text=txt, bg=C["TIP_BG"], fg=C["TIP_FG"], font=fnt("GSM"), justify="left", relief="solid", bd=1,
             padx=6, pady=3, wraplength=520).pack()
    tw.update_idletasks()
    sw, sh = widget.winfo_screenwidth(), widget.winfo_screenheight()
    w, h = tw.winfo_reqwidth(), tw.winfo_reqheight()
    x = min(x, sw - w - 4)
    if y + h > sh - 4:
        y = y - h - 30
    tw.wm_geometry(f"+{max(0, x)}+{max(0, y)}")
    return tw


def wheel_steps(e) -> int:
    if getattr(e, "num", None) == 4:
        return -1
    if getattr(e, "num", None) == 5:
        return 1
    d = int(getattr(e, "delta", 0) or 0)
    if d == 0:
        return 0
    return -max(1, abs(d) // 120) if d > 0 else max(1, abs(d) // 120)


class ScrollFrame(tk.Frame):
    """Cadre defilant vertical ; la molette fait defiler le Text survole s'il y en a un."""

    def __init__(self, parent, bg: str = "", **kw):
        bg = bg or C["BG"]
        super().__init__(parent, bg=bg, **kw)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self.win = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.vsb.pack(side="right", fill="y")
        self.inner.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.win, width=e.width))
        self.bind("<Enter>", self._on, add="+")
        self.bind("<Leave>", self._off, add="+")

    def _on(self, _e=None):
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.bind_all(seq, self._wheel)

    def _off(self, _e=None):
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.unbind_all(seq)

    def _wheel(self, e):
        n = wheel_steps(e)
        w = e.widget
        try:
            if isinstance(w, tk.Text):
                w.yview_scroll(n * 3, "units")
                return "break"
            if isinstance(w, (tk.Listbox, ttk.Treeview)):
                w.yview_scroll(n * 3, "units")
                return "break"
        except Exception:
            pass
        if self.inner.winfo_reqheight() > self.canvas.winfo_height():
            self.canvas.yview_scroll(n * 3, "units")
        return "break"

    def clear(self):
        for w in self.inner.winfo_children():
            w.destroy()
        self.canvas.yview_moveto(0)


class FlowFrame(tk.Frame):
    """Rangee de widgets qui passe a la ligne quand la place manque (rien n'est coupe a 1024 px)."""

    def __init__(self, parent, bg: str = "", gap: int = 2, **kw):
        super().__init__(parent, bg=bg or C["BG"], height=30, **kw)
        self.items: List[Tuple[Any, int]] = []
        self.hidden: set = set()
        self.gap = gap
        self.bind("<Configure>", lambda _e: self.reflow())

    def add(self, w, pad: int = 2) -> None:
        self.items.append((w, pad))

    def show(self, w, on: bool) -> None:
        if on:
            self.hidden.discard(str(w))
        else:
            self.hidden.add(str(w))

    def reflow(self) -> None:
        try:
            W = self.winfo_width()
        except tk.TclError:
            return
        if W < 50:
            W = max(300, self.master.winfo_width() - 16)
        x, y, rowh = 0, 0, 0
        for w, pad in self.items:
            if str(w) in self.hidden:
                w.place_forget()
                continue
            ww, hh = w.winfo_reqwidth(), w.winfo_reqheight()
            if x and x + pad + ww > W:
                x, y = 0, y + rowh + self.gap + 1
                rowh = 0
            px = x + (pad if x else 0)
            w.place(x=px, y=y)
            x = px + ww
            rowh = max(rowh, hh)
        h = y + rowh
        if int(self.cget("height") or 0) != h:
            self.configure(height=h)


def work_area(widget) -> Tuple[int, int, int, int]:
    if IS_WIN:
        try:
            r = wintypes.RECT()
            if ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(r), 0):
                return r.left, r.top, r.right - r.left, r.bottom - r.top
        except Exception:
            pass
    return 0, 0, widget.winfo_screenwidth(), widget.winfo_screenheight()


def copy_to_clipboard(root, text: str) -> None:
    try:
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update_idletasks()
    except tk.TclError:
        pass


def color_swatch(root, color: str, size: int = 12):
    img = tk.PhotoImage(master=root, width=size, height=size)
    try:
        img.put(C["LINE"], to=(0, 0, size, size))
        img.put(color or C["DIM"], to=(1, 1, size - 1, size - 1))
    except tk.TclError:
        pass
    return img


class Dialog(tk.Toplevel):
    """Fenetre modale centree, aux couleurs du theme, bornee a l'ecran."""

    def __init__(self, parent, title: str, w: int = 640, h: int = 420, resizable: bool = True, modal: bool = True):
        super().__init__(parent)
        self.parent = parent
        self.result = None
        self.withdraw()
        self.title(title)
        self.configure(bg=C["BG"])
        try:
            ico = os.path.join(BASE, "grimoire1.ico")
            if os.path.isfile(ico):
                self.iconbitmap(ico)
        except tk.TclError:
            pass
        top = parent.winfo_toplevel()
        pw, ph = top.winfo_width(), top.winfo_height()
        if pw < 200:
            pw, ph = top.winfo_screenwidth(), top.winfo_screenheight()
        wx, wy, ww, wh = work_area(self)
        w = min(w, max(300, pw - 30), ww - 30)
        h = min(h, max(240, ph - 40), wh - 50)
        x = top.winfo_rootx() + (pw - w) // 2
        y = top.winfo_rooty() + max(0, (ph - h) // 2 - 10)
        x = max(wx, min(x, wx + ww - w - 10))
        y = max(wy, min(y, wy + wh - h - 40))
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.resizable(resizable, resizable)
        self.transient(top)
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.bind("<Escape>", lambda _e: self.cancel())
        self._modal = modal

    def show(self, focus=None):
        self.deiconify()
        self.lift()
        if self._modal:
            try:
                self.grab_set()
            except tk.TclError:
                pass
        try:
            (focus or self).focus_set()
        except tk.TclError:
            pass
        return self

    def wait(self):
        self.wait_window(self)
        return self.result

    def cancel(self):
        self.result = None
        self.destroy()

    def button_bar(self, buttons: List[Tuple[str, Callable, str]]):
        bar = tk.Frame(self, bg=C["PANEL"])
        bar.pack(side="bottom", fill="x")
        for text, cmd, kind in reversed(buttons):
            mk_button(bar, text, cmd, kind).pack(side="right", padx=6, pady=8)
        return bar

    def row(self, parent, label: str, r: int, widget, hint: str = ""):
        mk_label(parent, label, "HI", "GUIB").grid(row=r, column=0, sticky="nw", padx=(10, 8), pady=4)
        widget.grid(row=r, column=1, sticky="we", padx=(0, 10), pady=4)
        if hint:
            mk_label(parent, hint, "DIM", "GSM", wraplength=420, justify="left").grid(row=r + 1, column=1, sticky="w", padx=(0, 10))


class TextDialog(Dialog):
    """Texte long en lecture (aide, statistiques, rapport) ; # titre, ## sous-titre, liens cliquables."""

    def __init__(self, parent, title: str, content: str, w: int = 900, h: int = 640):
        super().__init__(parent, title, w, h, modal=False)
        self.button_bar([("Copier", lambda: copy_to_clipboard(self, content), ""), ("Fermer", self.cancel, "accent")])
        fr = tk.Frame(self, bg=C["BG"])
        fr.pack(fill="both", expand=True, padx=8, pady=8)
        self.t = tk.Text(fr, bg=C["CARD"], fg=C["TEXT"], font=fnt("GUI"), wrap="word", relief="flat", padx=12, pady=8,
                         highlightthickness=0, selectbackground=C["SEL"], selectforeground=C["ON_SEL"], spacing1=1, spacing3=2)
        sb = ttk.Scrollbar(fr, orient="vertical", command=self.t.yview)
        self.t.configure(yscrollcommand=sb.set)
        self.t.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.t.tag_configure("h1", foreground=C["HI"], font=fnt("GTitle"), spacing1=8, spacing3=4)
        self.t.tag_configure("h2", foreground=C["HI"], font=fnt("GUIB"), spacing1=10, spacing3=2)
        self.t.tag_configure("k", foreground=C["FG"], font=fnt("GUIB"))
        self.t.tag_configure("bar", foreground=C["OK"])
        self.t.tag_configure("url", foreground=C["LINK"], underline=True)
        self.t.tag_bind("url", "<Enter>", lambda _e: self.t.configure(cursor="hand2"))
        self.t.tag_bind("url", "<Leave>", lambda _e: self.t.configure(cursor=""))
        self.t.tag_bind("url", "<Button-1>", self._click)
        for line in content.split("\n"):
            if line.startswith("# "):
                self.t.insert("end", line[2:] + "\n", "h1")
            elif line.startswith("## "):
                self.t.insert("end", line[3:] + "\n", "h2")
            elif line.startswith("  ") and " : " in line:
                k, v = line.split(" : ", 1)
                self.t.insert("end", k + " : ", "k")
                self._ins(v + "\n")
            else:
                self._ins(line + "\n")
        self.t.configure(state="disabled")
        self.show(self.t)

    def _ins(self, s: str):
        pos = 0
        for m in URL_RE.finditer(s):
            self.t.insert("end", s[pos:m.start()], "bar" if "█" in s[pos:m.start()] else ())
            self.t.insert("end", m.group(1), "url")
            pos = m.end()
        rest = s[pos:]
        if "█" in rest:
            i = rest.index("█")
            j = len(rest) - len(rest.lstrip("█")) if rest.startswith("█") else rest.rindex("█") + 1
            self.t.insert("end", rest[:i])
            self.t.insert("end", rest[i:j], "bar")
            self.t.insert("end", rest[j:])
        else:
            self.t.insert("end", rest)

    def _click(self, e):
        idx = self.t.index(f"@{e.x},{e.y}")
        r = self.t.tag_prevrange("url", idx + "+1c")
        if r:
            open_url(self.t.get(*r))


class AskDialog(Dialog):
    """Question simple : une ligne (ou plusieurs avec multiline)."""

    def __init__(self, parent, title: str, prompt: str, value: str = "", multiline: bool = False, w: int = 560):
        super().__init__(parent, title, w, 300 if multiline else 190, resizable=multiline)
        self.multiline = multiline
        self.button_bar([("Annuler", self.cancel, ""), ("OK", self._ok, "accent")])
        mk_label(self, prompt, "HI", "GUIB", wraplength=w - 40, justify="left").pack(anchor="w", padx=12, pady=(12, 6))
        if multiline:
            self.e = mk_text(self, 6, 40, "GUI")
            self.e.insert("1.0", value)
            self.e.pack(fill="both", expand=True, padx=12, pady=4)
        else:
            self.v = tk.StringVar(value=value)
            self.e = mk_entry(self, self.v, 50)
            self.e.pack(fill="x", padx=12, pady=4, ipady=3)
            self.e.select_range(0, "end")
            self.e.bind("<Return>", lambda _e: self._ok())
        self.show(self.e)

    def _ok(self):
        self.result = self.e.get("1.0", "end-1c") if self.multiline else self.v.get()
        self.destroy()


def ask_string(parent, title: str, prompt: str, value: str = "", multiline: bool = False) -> Optional[str]:
    return AskDialog(parent, title, prompt, value, multiline).wait()


class EmojiPicker(Dialog):
    def __init__(self, parent, current: str = ""):
        super().__init__(parent, "Choisir une icône", 640, 520)
        self.button_bar([("Aucune", self._none, ""), ("Annuler", self.cancel, ""), ("OK", self._ok, "accent")])
        top = tk.Frame(self, bg=C["BG"])
        top.pack(fill="x", padx=10, pady=(10, 4))
        mk_label(top, "Icône (emoji ou caractère) :", "HI", "GUIB").pack(side="left")
        self.v = tk.StringVar(value=current)
        e = mk_entry(top, self.v, 6, "EmojiSM")
        e.pack(side="left", padx=8)
        sf = ScrollFrame(self, bg=C["BG"])
        sf.pack(fill="both", expand=True, padx=8, pady=4)
        for name, chars in EMOJI_SETS:
            mk_label(sf.inner, name, "FG", "GHead").pack(anchor="w", padx=4, pady=(6, 0))
            g = tk.Frame(sf.inner, bg=C["BG"])
            g.pack(anchor="w")
            for i, ch in enumerate(self._split(chars)):
                b = tk.Button(g, text=ch, command=lambda c=ch: self._pick(c), bg=C["BG"], fg=C["TEXT"], relief="flat", bd=0,
                              activebackground=C["SEL"], font=fnt("EmojiSM"), cursor="hand2", width=2)
                b.grid(row=i // 13, column=i % 13, padx=1, pady=1)
        self.show(e)

    @staticmethod
    def _split(s: str) -> List[str]:
        out: List[str] = []
        for ch in s:
            if out and (ch in "\ufe0f\u200d" or unicodedata.category(ch) == "Mn" or (out[-1].endswith("\u200d"))):
                out[-1] += ch
            else:
                out.append(ch)
        return out

    def _pick(self, ch):
        self.v.set(ch)
        self._ok()

    def _none(self):
        self.result = ""
        self.destroy()

    def _ok(self):
        self.result = self.v.get().strip()
        self.destroy()

    def cancel(self):
        self.result = None
        self.destroy()


class SubjectDialog(Dialog):
    """Creer / modifier un sujet : nom, icone, couleur, parent, description, epingle."""

    def __init__(self, parent, app, title: str, subj: Optional[Dict[str, Any]] = None, parent_id: Optional[int] = None):
        super().__init__(parent, title, 680, 520)
        self.app = app
        st = app.store
        s = subj or {}
        self.sid = s.get("id")
        self.button_bar([("Annuler", self.cancel, ""), ("Enregistrer", self._ok, "accent")])
        f = tk.Frame(self, bg=C["BG"])
        f.pack(fill="both", expand=True, padx=6, pady=8)
        f.columnconfigure(1, weight=1)
        self.v_name = tk.StringVar(value=s.get("name", ""))
        e = mk_entry(f, self.v_name, 40, "GUIB")
        self.row(f, "Nom", 0, e)
        e.bind("<Return>", lambda _e: self._ok())
        ic = tk.Frame(f, bg=C["BG"])
        self.v_icon = tk.StringVar(value=s.get("icon") or "📁")
        mk_entry(ic, self.v_icon, 4, "EmojiSM").pack(side="left")
        mk_button(ic, "Choisir…", self._pick).pack(side="left", padx=6)
        self.row(f, "Icône", 1, ic)
        cf = tk.Frame(f, bg=C["BG"])
        self.v_color = tk.StringVar(value=s.get("color") or random.choice(SUBJECT_COLORS))
        self.color_btns = []
        for i, col in enumerate(SUBJECT_COLORS):
            b = tk.Button(cf, bg=col, activebackground=col, width=2, relief="flat", bd=0, highlightthickness=2,
                          cursor="hand2", command=lambda c=col: self._set_color(c))
            b.grid(row=i // 8, column=i % 8, padx=2, pady=2)
            self.color_btns.append((col, b))
        mk_button(cf, "Autre…", self._other_color, font_name="GSM").grid(row=0, column=8, rowspan=2, padx=6)
        self.row(f, "Couleur", 2, cf)
        self._set_color(self.v_color.get())
        self.parents = [(None, "(racine : sujet principal)")]
        excl = {self.sid} | set(st.descendants(self.sid)) if self.sid else set()
        for sid in app.subject_order():
            if sid not in excl:
                self.parents.append((sid, "   " * (len(st.subject_path(sid).split(" › ")) - 1) + st.subject_label(sid).split(" ", 1)[0]
                                     + " " + st.subject(sid)["name"]))
        self.cb_parent = ttk.Combobox(f, values=[p[1] for p in self.parents], state="readonly", font=fnt("GUI"))
        cur = s.get("parent_id") if subj else parent_id
        idx = next((i for i, p in enumerate(self.parents) if p[0] == cur), 0)
        self.cb_parent.current(idx)
        self.row(f, "Dans", 3, self.cb_parent)
        self.t_desc = mk_text(f, 4, 40, "GUI")
        self.t_desc.insert("1.0", s.get("description", ""))
        self.row(f, "Description", 4, self.t_desc)
        self.v_pin = tk.BooleanVar(value=bool(s.get("pinned")))
        self.row(f, "", 5, mk_check(f, "📌 Épinglé (toujours en haut)", self.v_pin))
        self.show(e)
        e.select_range(0, "end")

    def _pick(self):
        r = EmojiPicker(self, self.v_icon.get()).wait()
        if r is not None:
            self.v_icon.set(r or "📁")

    def _set_color(self, c):
        self.v_color.set(c)
        for col, b in self.color_btns:
            b.configure(highlightbackground=C["HI"] if col.lower() == c.lower() else C["BG"],
                        relief="solid" if col.lower() == c.lower() else "flat")

    def _other_color(self):
        from tkinter import colorchooser
        r = colorchooser.askcolor(self.v_color.get(), parent=self, title="Couleur du sujet")
        if r and r[1]:
            self._set_color(r[1])

    def _ok(self):
        name = self.v_name.get().strip()
        if not name:
            messagebox.showwarning(APP_NAME, "Donne un nom au sujet.", parent=self)
            return
        self.result = {"name": name, "icon": self.v_icon.get().strip() or "📁", "color": self.v_color.get(),
                       "parent_id": self.parents[self.cb_parent.current()][0],
                       "description": self.t_desc.get("1.0", "end-1c").strip(), "pinned": int(self.v_pin.get())}
        self.destroy()


class SubjectChooser(Dialog):
    """Choisir un sujet (deplacer, copier, fusionner) avec filtre."""

    def __init__(self, parent, app, title: str, prompt: str, allow_root: bool = False, exclude: Iterable[int] = ()):
        super().__init__(parent, title, 560, 560)
        self.app = app
        self.allow_root = allow_root
        self.exclude = set(exclude)
        self.button_bar([("Annuler", self.cancel, ""), ("＋ Nouveau sujet…", lambda: self._new(False), ""),
                         ("＋ Sous-sujet du sujet choisi…", lambda: self._new(True), ""), ("OK", self._ok, "accent")])
        mk_label(self, prompt, "HI", "GUIB", wraplength=520, justify="left").pack(anchor="w", padx=12, pady=(10, 4))
        self.v = tk.StringVar()
        e = mk_entry(self, self.v, 40)
        e.pack(fill="x", padx=12, pady=4, ipady=2)
        fr = tk.Frame(self, bg=C["BG"])
        fr.pack(fill="both", expand=True, padx=12, pady=4)
        self.tv = ttk.Treeview(fr, show="tree", selectmode="browse", style="Subj.Treeview")
        sb = ttk.Scrollbar(fr, orient="vertical", command=self.tv.yview)
        self.tv.configure(yscrollcommand=sb.set)
        self.tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.v.trace_add("write", lambda *_a: self.fill())
        e.bind("<Down>", lambda _e: (self.tv.focus_set(), self._first()))
        e.bind("<Return>", lambda _e: self._ok())
        self.tv.bind("<Double-Button-1>", lambda _e: self._ok())
        self.tv.bind("<Return>", lambda _e: self._ok())
        self.fill()
        self.show(e)

    def _first(self):
        ch = self.tv.get_children("")
        if ch:
            self.tv.selection_set(ch[0])
            self.tv.focus(ch[0])

    def fill(self):
        st = self.app.store
        self.tv.delete(*self.tv.get_children(""))
        q = norm(self.v.get())
        if self.allow_root and not q:
            self.tv.insert("", "end", iid="root", text="⬆ (racine : sujet principal)")
        if q:
            for sid in self.app.subject_order():
                if sid in self.exclude:
                    continue
                if all(t in norm(st.subject_path(sid)) for t in q.split()):
                    self.tv.insert("", "end", iid=f"s{sid}", text=st.subject_label(sid))
        else:
            def add(parent_iid, pid):
                for s in st.children(pid):
                    if s["id"] in self.exclude:
                        continue
                    self.tv.insert(parent_iid, "end", iid=f"s{s['id']}", text=f"{s['icon'] or '📁'} {s['name']}", open=True)
                    add(f"s{s['id']}", s["id"])
            add("", None)
        self._first()

    def _new(self, sub: bool = False):
        par = None
        if sub:
            sel = self.tv.selection()
            if not sel or sel[0] == "root":
                messagebox.showinfo(APP_NAME, "Choisis d'abord dans la liste le sujet qui recevra le sous-sujet.", parent=self)
                return
            par = int(sel[0][1:])
        r = SubjectDialog(self, self.app, "Nouveau sous-sujet" if par else "Nouveau sujet", None, par).wait()
        if r:
            sid = self.app.store.add_subject(r["name"], r["parent_id"], r["icon"], r["color"], r["description"], bool(r["pinned"]))
            if r["parent_id"]:
                self.app.store.update_subject(r["parent_id"], expanded=1)
            self.app.refresh_tree()
            self.app.reveal_subject(sid)
            self.result = sid
            self.destroy()

    def _ok(self):
        sel = self.tv.selection()
        if not sel:
            return
        self.result = 0 if sel[0] == "root" else int(sel[0][1:])
        self.destroy()


class SubjectManager(Dialog):
    """Fenetre « Gerer les sujets » : tous les sujets, sur tous les niveaux, avec leurs actions."""

    def __init__(self, parent, app):
        super().__init__(parent, "Gérer les sujets", 820, 620, modal=False)
        self.app = app
        mk_label(self, "Tous les sujets. Choisis-en un puis une action, ou glisse-le dans l'arbre principal. "
                       "Double-clic = modifier.", "HI", "GUIB", wraplength=780, justify="left").pack(anchor="w", padx=12, pady=(10, 4))
        body = tk.Frame(self, bg=C["BG"])
        body.pack(fill="both", expand=True, padx=12, pady=4)
        fr = tk.Frame(body, bg=C["BG"])
        fr.pack(side="left", fill="both", expand=True)
        self.tv = ttk.Treeview(fr, show="tree", columns=("n",), selectmode="browse", style="Subj.Treeview")
        self.tv.column("n", width=50, anchor="e", stretch=False)
        sb = ttk.Scrollbar(fr, orient="vertical", command=self.tv.yview)
        self.tv.configure(yscrollcommand=sb.set)
        self.tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        bx = tk.Frame(body, bg=C["BG"])
        bx.pack(side="right", fill="y", padx=(10, 0))
        acts = [("📁 Nouveau sujet principal", lambda s: self._do(lambda: app.new_subject(None)), False),
                ("📂 Nouveau sous-sujet", lambda s: self._do(lambda: app.new_subject(s)), True),
                ("✏ Renommer (F2)", lambda s: self._do(lambda: app.rename_subject_id(s)), True),
                ("⚙ Modifier…", lambda s: self._do(lambda: app.edit_subject(s)), True),
                ("😀 Icône…", lambda s: self._do(lambda: app.set_subject_icon(s)), True),
                ("🎨 Couleur…", lambda s: self._do(lambda: app.set_subject_color(s)), True),
                ("⬆ Monter", lambda s: self._do(lambda: app.store.reorder_subject(s, -1)), True),
                ("⬇ Descendre", lambda s: self._do(lambda: app.store.reorder_subject(s, 1)), True),
                ("📁 Ranger dans…", lambda s: self._do(lambda: app._subject_into(s)), True),
                ("⤴ Rendre principal", lambda s: self._do(lambda: app.promote_subject(s)), True),
                ("🔀 Fusionner dans…", lambda s: self._do(lambda: app.merge_subject(s)), True),
                ("🗑 Supprimer (corbeille)", lambda s: self._do(lambda: app.delete_subject(s)), True)]
        for lab, fn, need in acts:
            mk_button(bx, lab, lambda fn=fn, need=need: self._run(fn, need), font_name="GSM").pack(fill="x", pady=2)
        self.button_bar([("Fermer", self.cancel, "accent")])
        self.tv.bind("<Double-Button-1>", lambda _e: self._run(lambda s: self._do(lambda: app.edit_subject(s)), True))
        self.tv.bind("<F2>", lambda _e: self._run(lambda s: self._do(lambda: app.rename_subject_id(s)), True))
        self.fill()
        self.show(self.tv)

    def _sid(self) -> Optional[int]:
        sel = self.tv.selection()
        return int(sel[0][1:]) if sel else None

    def _run(self, fn, need: bool):
        sid = self._sid()
        if need and not sid:
            messagebox.showinfo(APP_NAME, "Choisis d'abord un sujet dans la liste.", parent=self)
            return
        fn(sid)

    def _do(self, fn):
        sid = self._sid()
        fn()
        self.app.refresh_tree()
        self.fill(sid)
        if sid and self.app.store.subject(sid):
            self.app.reveal_subject(sid, flash=False)

    def fill(self, keep: Optional[int] = None):
        st = self.app.store
        tot = st.total_counts()
        self.tv.delete(*self.tv.get_children(""))

        def add(piid, pid):
            for s in st.children(pid):
                iid = f"s{s['id']}"
                self.tv.insert(piid, "end", iid=iid, text=f"{s['icon'] or '📁'} {s['name']}",
                               values=(tot.get(s["id"], 0) or "",), image=self.app.swatch(s["color"]), open=True)
                add(iid, s["id"])
        add("", None)
        if keep and self.tv.exists(f"s{keep}"):
            self.tv.selection_set(f"s{keep}")
            self.tv.see(f"s{keep}")


class LinkDialog(Dialog):
    def __init__(self, parent, app, url: str = ""):
        super().__init__(parent, "Ajouter un lien web", 700, 480)
        self.button_bar([("Annuler", self.cancel, ""), ("Ajouter", self._ok, "accent")])
        f = tk.Frame(self, bg=C["BG"])
        f.pack(fill="both", expand=True, padx=6, pady=8)
        f.columnconfigure(1, weight=1)
        self.v_url = tk.StringVar(value=url)
        e = mk_entry(f, self.v_url, 50)
        self.row(f, "Lien", 0, e, "Le titre, la description et la miniature sont récupérés automatiquement.")
        self.v_title = tk.StringVar()
        self.row(f, "Titre", 2, mk_entry(f, self.v_title, 50), "Laisser vide : titre de la page.")
        self.v_tags = tk.StringVar()
        self.row(f, "Étiquettes", 4, mk_entry(f, self.v_tags, 50), "Séparées par des virgules.")
        self.t_note = mk_text(f, 4, 40, "GUI")
        self.row(f, "Note", 6, self.t_note)
        f.rowconfigure(6, weight=1)
        self.v_cap = tk.BooleanVar(value=False)
        self.row(f, "", 7, mk_check(f, "🌐 Capturer aussi la page complète (HTML hors ligne + PDF + image)", self.v_cap))
        e.bind("<Return>", lambda _e: self._ok())
        self.show(e)
        e.select_range(0, "end")

    def _ok(self):
        u = self.v_url.get().strip()
        if not u:
            return
        if not re.match(r"(?i)^[a-z][a-z0-9+.-]*:", u) and not u.lower().startswith("www."):
            u = "https://" + u
        self.result = {"url": u, "title": self.v_title.get().strip(), "tags": self.v_tags.get(),
                       "note": self.t_note.get("1.0", "end-1c").strip(), "capture": self.v_cap.get()}
        self.destroy()


class QuoteDialog(Dialog):
    def __init__(self, parent, text: str = ""):
        super().__init__(parent, "Ajouter une citation", 720, 540)
        self.button_bar([("Annuler", self.cancel, ""), ("Ajouter", self._ok, "accent")])
        f = tk.Frame(self, bg=C["BG"])
        f.pack(fill="both", expand=True, padx=6, pady=8)
        f.columnconfigure(1, weight=1)
        self.t = mk_text(f, 6, 40, "GUI")
        self.t.insert("1.0", text)
        self.row(f, "Citation", 0, self.t)
        f.rowconfigure(0, weight=1)
        self.vs = {k: tk.StringVar() for k in ("author", "source", "url", "page", "tags", "date")}
        for i, (k, lab, hint) in enumerate((("author", "Auteur", ""), ("source", "Source", "Livre, article, vidéo, site…"),
                                            ("url", "Lien", ""), ("page", "Page / minute", ""),
                                            ("date", "Date", "AAAA-MM-JJ (facultatif)"), ("tags", "Étiquettes", ""))):
            self.row(f, lab, 1 + i, mk_entry(f, self.vs[k], 40))
        self.show(self.t)

    def _ok(self):
        txt = self.t.get("1.0", "end-1c").strip()
        if not txt:
            return
        self.result = {"text": txt, **{k: v.get().strip() for k, v in self.vs.items()}}
        self.destroy()
