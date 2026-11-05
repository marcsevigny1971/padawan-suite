# -*- coding: utf-8 -*-
# Partie de grimoire1.py (découpage v1.2.2, comportement inchangé).
# Chargée par grimoire1.py dans un espace de noms commun : ne pas lancer seule.
from __future__ import annotations



# ================================================================ editeur de texte riche
EDITOR_APP_KEYS = set("dgnlmoprstfe")


def configure_rich_tags(t: tk.Text, reading: bool = False) -> None:
    pre = "R" if reading else "E"
    norm_f = fnt(pre + "Norm")
    t.configure(font=norm_f)
    t.tag_configure("b", font=fnt(pre + "B"))
    t.tag_configure("i", font=fnt(pre + "I"))
    t.tag_configure("bi", font=fnt(pre + "BI"))
    t.tag_configure("u", underline=True)
    t.tag_configure("s", overstrike=True)
    t.tag_configure("h1", font=fnt(pre + "H1"), foreground=C["HI"], spacing1=8, spacing3=4)
    t.tag_configure("h2", font=fnt(pre + "H2"), foreground=C["HI"], spacing1=6, spacing3=3)
    t.tag_configure("h3", font=fnt(pre + "H3"), foreground=C["FG"], spacing1=4, spacing3=2)
    t.tag_configure("quote", font=fnt(pre + "I"), foreground=C["QUOTE"], lmargin1=22, lmargin2=22, rmargin=10)
    t.tag_configure("code", font=fnt(pre + "Code" if not reading else "RCode"), background=C["CODE_BG"], foreground=C["OK"])
    t.tag_configure("mark", background=C["MARK"])
    t.tag_configure("url", foreground=C["LINK"], underline=True)
    t.tag_configure("ref", foreground=C["REF"], underline=True)
    t.tag_configure("href", foreground=C["LINK"], underline=True)
    t.tag_configure("chk", foreground=C["HI"])
    t.tag_configure("search", background=C["SEL"], foreground=C["ON_SEL"])
    for tg in ("h3", "h2", "h1", "url", "ref", "href", "search"):
        t.tag_raise(tg)
    try:
        t.tag_raise("sel")
    except tk.TclError:
        pass


def insert_runs(t: tk.Text, runs: List[List[Any]], hrefs: Dict[str, str]) -> None:
    """Insere des runs ; les liens « a=url » deviennent des etiquettes href_N (dict hrefs : etiquette -> url)."""
    rev = {v: k for k, v in hrefs.items()}
    for text, tags in runs:
        tk_tags = []
        for tg in tags:
            if tg.startswith("a="):
                url = tg[2:]
                name = rev.get(url)
                if not name:
                    name = f"href_{len(hrefs) + 1}"
                    hrefs[name] = url
                    rev[url] = name
                tk_tags += [name, "href"]
            elif tg in RICH_TAGS:
                tk_tags.append(tg)
        t.insert("end", text, tuple(tk_tags))


def refresh_combo(t: tk.Text) -> None:
    """Gras + italique ensemble : etiquette derivee « bi »."""
    t.tag_remove("bi", "1.0", "end")
    br = t.tag_ranges("b")
    ir = t.tag_ranges("i")
    if not br or not ir:
        return
    ib = [(ir[k], ir[k + 1]) for k in range(0, len(ir), 2)]
    for k in range(0, len(br), 2):
        a, b = br[k], br[k + 1]
        for c, d in ib:
            s = a if t.compare(a, ">", c) else c
            e = b if t.compare(b, "<", d) else d
            if t.compare(s, "<", e):
                t.tag_add("bi", s, e)


def relink(t: tk.Text, terms: Optional[List[str]] = None) -> None:
    """Liens web, references [[...]], cases a cocher et surlignage de recherche."""
    for tg in ("url", "ref", "chk", "search"):
        t.tag_remove(tg, "1.0", "end")
    content = t.get("1.0", "end-1c")
    nterms = [norm(x) for x in (terms or []) if len(norm(x)) >= 2]
    for ln, line in enumerate(content.split("\n"), start=1):
        if not line:
            continue
        for m in URL_RE.finditer(line):
            t.tag_add("url", f"{ln}.{tk_col(line, m.start(1))}", f"{ln}.{tk_col(line, m.end(1))}")
        for m in REF_RE.finditer(line):
            t.tag_add("ref", f"{ln}.{tk_col(line, m.start())}", f"{ln}.{tk_col(line, m.end())}")
        for m in re.finditer("[☐☑]", line):
            t.tag_add("chk", f"{ln}.{tk_col(line, m.start())}", f"{ln}.{tk_col(line, m.end())}")
        if nterms:
            nl = norm(line)
            if len(nl) == len(line):
                for term in nterms:
                    for m in re.finditer(re.escape(term), nl):
                        t.tag_add("search", f"{ln}.{tk_col(line, m.start())}", f"{ln}.{tk_col(line, m.end())}")


class RichEditor(tk.Frame):
    """Editeur de notes : gras, italique, souligne, barre, titres, listes, cases, citation, code, surligneur,
    liens (auto et sur selection), references [[...]] ; sauvegarde automatique via on_change."""

    def __init__(self, parent, app, on_change: Optional[Callable[[], None]] = None, bg: str = ""):
        super().__init__(parent, bg=bg or C["PANEL"])
        self.app = app
        self.on_change = on_change
        self.hrefs: Dict[str, str] = {}
        self.loading = False
        self.pending: set = set()
        self.terms: List[str] = []
        self.job = None
        tb = tk.Frame(self, bg=C["PANEL"])
        tb.pack(fill="x", pady=(2, 2))
        self.tb = tb
        specs = [("G", lambda: self.toggle("b"), "Gras (Ctrl+B)", "GUIB"),
                 ("I", lambda: self.toggle("i"), "Italique (Ctrl+I)", "EI"),
                 ("S̲", lambda: self.toggle("u"), "Souligné (Ctrl+U)", "GUI"),
                 ("B̶", lambda: self.toggle("s"), "Barré (Ctrl+Maj+X)", "GUI"),
                 ("|", None, "", ""),
                 ("T1", lambda: self.heading("h1"), "Grand titre (Ctrl+1)", "GSMB"),
                 ("T2", lambda: self.heading("h2"), "Titre (Ctrl+2)", "GSMB"),
                 ("T3", lambda: self.heading("h3"), "Sous-titre (Ctrl+3)", "GSMB"),
                 ("¶", lambda: self.heading(None), "Texte normal (Ctrl+0)", "GUI"),
                 ("|", None, "", ""),
                 ("•", lambda: self.list_prefix("• "), "Liste à puces (Ctrl+Maj+8)", "GUIB"),
                 ("1.", lambda: self.list_prefix("1. "), "Liste numérotée", "GSMB"),
                 ("☐", lambda: self.list_prefix("☐ "), "Case à cocher (clic sur ☐ pour cocher)", "GUI"),
                 ("❝", lambda: self.heading("quote"), "Citation (bloc)", "GUI"),
                 ("</>", lambda: self.toggle("code"), "Code / commande", "GSM"),
                 ("🖍", lambda: self.toggle("mark"), "Surligner", "EmojiSM"),
                 ("|", None, "", ""),
                 ("🔗", self.make_link, "Lien sur la sélection, ou insérer un lien (Ctrl+K)", "EmojiSM"),
                 ("[[ ]]", self.insert_ref, "Référence vers un sujet ou une fiche ([[titre]])", "GSM"),
                 ("📅", self.insert_date, "Insérer la date du jour", "EmojiSM"),
                 ("🧹", self.clear_format, "Effacer la mise en forme de la sélection", "EmojiSM")]
        self.tb_buttons = []
        for text, cmd, tip, f in specs:
            if cmd is None:
                sep = tk.Frame(tb, bg=C["LINE"], width=1, height=18)
                sep._flow_pad = 4  # type: ignore[attr-defined]
                continue
            b = tk.Button(tb, text=text, command=cmd, bg=C["BTN"], fg=C["TEXT"], relief="flat", bd=0, padx=5, pady=0,
                          activebackground=C["HI"], activeforeground=C["ON_HI"], font=fnt(f), cursor="hand2",
                          highlightthickness=0, takefocus=0)
            b._flow_pad = 1  # type: ignore[attr-defined]
            Tooltip(b, tip)
            self.tb_buttons.append(b)
        tb.bind("<Configure>", lambda _e: self._flow())
        self.after_idle(self._flow)
        fr = tk.Frame(self, bg=C["PANEL"])
        fr.pack(fill="both", expand=True)
        self.t = tk.Text(fr, bg=C["ENTRY_BG"], fg=C["ENTRY_FG"], insertbackground=C["HI"], relief="flat", wrap="word",
                         undo=True, autoseparators=True, maxundo=-1, padx=10, pady=8, spacing1=1, spacing3=1,
                         highlightthickness=1, highlightbackground=C["LINE"], highlightcolor=C["HI"],
                         selectbackground=C["SEL"], selectforeground=C["ON_SEL"], height=8, width=30)
        vsb = ttk.Scrollbar(fr, orient="vertical", command=self.t.yview)
        self.t.configure(yscrollcommand=vsb.set)
        self.t.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        configure_rich_tags(self.t)
        t = self.t
        for tg in ("url", "ref", "href", "chk"):
            t.tag_bind(tg, "<Enter>", lambda _e: t.configure(cursor="hand2"))
            t.tag_bind(tg, "<Leave>", lambda _e: t.configure(cursor="xterm"))
        t.tag_bind("url", "<Button-1>", lambda e: self._click(e, "url"))
        t.tag_bind("ref", "<Button-1>", lambda e: self._click(e, "ref"))
        t.tag_bind("href", "<Button-1>", lambda e: self._click(e, "href"))
        t.tag_bind("chk", "<Button-1>", lambda e: self._click(e, "chk"))
        t.bind("<<Modified>>", self._modified)
        t.bind("<Control-KeyPress>", self._ctrl)
        t.bind("<Return>", self._return)
        t.bind("<KeyPress>", self._key, add="+")
        t.bind("<ButtonPress-1>", lambda _e: self.pending.clear(), add="+")
        t.bind("<Button-3>", self._menu)
        t.bind("<FocusOut>", lambda _e: self.flush(), add="+")
        t.bind("<MouseWheel>", lambda e: (t.yview_scroll(wheel_steps(e) * 3, "units"), "break")[1])

    def _flow(self):
        """Barre d'outils sur plusieurs lignes si le panneau est etroit (aucun bouton cache)."""
        tb = self.tb
        try:
            W = tb.winfo_width()
        except tk.TclError:
            return
        if W < 50:
            W = 400
        x, y, rowh = 2, 2, 0
        for w in tb.winfo_children():
            pad = getattr(w, "_flow_pad", 1)
            ww, hh = w.winfo_reqwidth(), w.winfo_reqheight()
            if x + ww + pad > W and x > 2:
                x, y = 2, y + rowh + 2
                rowh = 0
            w.place(x=x + pad, y=y + (0 if pad == 1 else 3))
            x += ww + 2 * pad
            rowh = max(rowh, hh if pad == 1 else 0)
        h = y + rowh + 2
        if int(tb.cget("height") or 0) != h:
            tb.configure(height=h)

    # ------------------------------------------------------------ contenu
    def load(self, body: Any, terms: Optional[List[str]] = None, readonly: bool = False) -> None:
        self.loading = True
        self.terms = list(terms or [])
        t = self.t
        t.configure(state="normal")
        t.delete("1.0", "end")
        for name in list(self.hrefs):
            try:
                t.tag_delete(name)
            except tk.TclError:
                pass
        self.hrefs = {}
        insert_runs(t, runs_from_any(body), self.hrefs)
        refresh_combo(t)
        relink(t, self.terms)
        t.edit_reset()
        t.edit_modified(False)
        t.mark_set("insert", "1.0")
        t.see("1.0")
        if readonly:
            t.configure(state="disabled")
        self.loading = False
        if self.terms:
            r = t.tag_nextrange("search", "1.0")
            if r:
                t.see(r[0])

    def runs(self) -> List[List[Any]]:
        out: List[List[Any]] = []
        active: List[str] = []
        for key, val, _idx in self.t.dump("1.0", "end-1c", tag=True, text=True):
            if key == "tagon":
                active.append(val)
            elif key == "tagoff":
                if val in active:
                    active.remove(val)
            elif key == "text":
                tags = []
                for tg in active:
                    if tg in RICH_TAGS:
                        tags.append(tg)
                    elif tg.startswith("href_") and tg in self.hrefs:
                        tags.append("a=" + self.hrefs[tg])
                out.append([val, tags])
        return merge_runs(out)

    def body(self) -> str:
        return runs_to_json(self.runs())

    def plain(self) -> str:
        return self.t.get("1.0", "end-1c")

    def is_empty(self) -> bool:
        return not self.plain().strip()

    # ------------------------------------------------------------ evenements
    def _modified(self, _e=None):
        if not self.t.edit_modified():
            return
        self.t.edit_modified(False)
        if self.loading:
            return
        if self.job:
            self.after_cancel(self.job)
        self.job = self.after(700, self._changed)

    def _changed(self):
        self.job = None
        try:
            refresh_combo(self.t)
            relink(self.t, self.terms)
        except tk.TclError:
            return
        if self.on_change:
            self.on_change()

    def flush(self):
        try:
            dirty = (not self.loading) and bool(self.t.edit_modified())
        except tk.TclError:
            dirty = False
        if self.job or dirty:
            if self.job:
                try:
                    self.after_cancel(self.job)
                except Exception:
                    pass
            try:
                self.t.edit_modified(False)
            except tk.TclError:
                pass
            self._changed()

    def _ctrl(self, e):
        k = (e.keysym or "").lower()
        shift = bool(e.state & 0x1)
        acts = {"b": lambda: self.toggle("b"), "i": lambda: self.toggle("i"), "u": lambda: self.toggle("u"),
                "1": lambda: self.heading("h1"), "2": lambda: self.heading("h2"), "3": lambda: self.heading("h3"),
                "0": lambda: self.heading(None), "k": self.make_link}
        if k == "x" and shift:
            self.toggle("s")
            return "break"
        if k in ("8", "asterisk") and shift:
            self.list_prefix("• ")
            return "break"
        if k in acts and not (shift and k in "123"):
            acts[k]()
            return "break"
        if k in ("plus", "equal", "minus", "kp_add", "kp_subtract") or (k == "0" and shift):
            return None
        if k in EDITOR_APP_KEYS or (shift and k in ("q", "i", "v", "n")):
            self.flush()
            return self.app.ctrl_key(e)
        return None

    def _key(self, e):
        if self.pending and e.char and e.char.isprintable() and not (e.state & 0x4):
            ctx = [tg for tg in self.t.tag_names("insert-1c") if tg in RICH_TAGS]
            tags = (set(ctx) | {p for p in self.pending if not p.startswith("-")}) - {p[1:] for p in self.pending if p.startswith("-")}
            if self.t.tag_ranges("sel"):
                self.t.delete("sel.first", "sel.last")
            self.t.insert("insert", e.char, tuple(tags))
            self.t.see("insert")
            return "break"
        if e.keysym in ("Left", "Right", "Up", "Down", "Home", "End", "Prior", "Next"):
            self.pending.clear()
        return None

    def _return(self, _e=None):
        line = self.t.get("insert linestart", "insert")
        m = re.match(r"^(\s*)(• |(\d+)\. |☐ |☑ )(.*)$", line)
        if not m:
            return None
        ind, pre, num, rest = m.group(1), m.group(2), m.group(3), m.group(4)
        if not rest.strip() and self.t.compare("insert", "==", "insert lineend"):
            self.t.delete("insert linestart", "insert")
            return "break"
        nxt = f"{int(num) + 1}. " if num else ("☐ " if pre in ("☐ ", "☑ ") else pre)
        self.t.insert("insert", "\n" + ind + nxt)
        self.t.see("insert")
        return "break"

    def _click(self, e, kind):
        idx = self.t.index(f"@{e.x},{e.y}")
        if kind == "href":
            name = next((tg for tg in self.t.tag_names(idx) if tg.startswith("href_")), "")
            if name in self.hrefs:
                open_url(self.hrefs[name])
            return "break"
        r = self.t.tag_prevrange(kind, idx + "+1c")
        if not r:
            return None
        txt = self.t.get(*r)
        if kind == "url":
            open_url(txt)
        elif kind == "ref":
            self.app.follow_ref(txt.strip("[]"))
        elif kind == "chk":
            st = self.t.cget("state")
            self.t.configure(state="normal")
            self.t.delete(r[0], r[1])
            self.t.insert(r[0], "☑" if txt == "☐" else "☐", tuple(tg for tg in self.t.tag_names(r[0]) if tg in RICH_TAGS))
            self.t.configure(state=st)
            relink(self.t, self.terms)
            self._modified_force()
        return "break"

    def _modified_force(self):
        if self.on_change and not self.loading:
            if self.job:
                self.after_cancel(self.job)
            self.job = self.after(300, self._changed)

    # ------------------------------------------------------------ mise en forme
    def _sel(self) -> Optional[Tuple[str, str]]:
        try:
            return self.t.index("sel.first"), self.t.index("sel.last")
        except tk.TclError:
            return None

    def _covered(self, tag: str, a: str, b: str) -> bool:
        r = self.t.tag_ranges(tag)
        for k in range(0, len(r), 2):
            if self.t.compare(r[k], "<=", a) and self.t.compare(r[k + 1], ">=", b):
                return True
        return False

    def toggle(self, tag: str):
        if str(self.t.cget("state")) == "disabled":
            return
        s = self._sel()
        if not s:
            # sans selection : style en attente pour les prochains caracteres tapes
            if tag in self.t.tag_names("insert-1c") and "-" + tag not in self.pending:
                self.pending.discard(tag)
                self.pending.add("-" + tag)
            elif tag in self.pending or "-" + tag in self.pending:
                self.pending.discard(tag)
                self.pending.discard("-" + tag)
            else:
                self.pending.add(tag)
            self.app.set_status(f"Style « {tag} » : " + ("activé pour la suite de la frappe" if tag in self.pending else "désactivé"))
            self.t.focus_set()
            return
        a, b = s
        self.t.edit_separator()
        if self._covered(tag, a, b):
            self.t.tag_remove(tag, a, b)
        else:
            self.t.tag_add(tag, a, b)
        refresh_combo(self.t)
        self._modified_force()
        self.t.focus_set()

    def heading(self, tag: Optional[str]):
        if str(self.t.cget("state")) == "disabled":
            return
        s = self._sel()
        a, b = (s if s else (self.t.index("insert"), self.t.index("insert")))
        a, b = self.t.index(f"{a} linestart"), self.t.index(f"{b} lineend")
        had = tag and self._covered(tag, a, b) if tag else False
        for tg in LINE_TAGS:
            self.t.tag_remove(tg, a, b + "+1c")
        if tag and not had:
            self.t.tag_add(tag, a, b + "+1c")
        self._modified_force()
        self.t.focus_set()

    def list_prefix(self, pre: str):
        if str(self.t.cget("state")) == "disabled":
            return
        s = self._sel()
        a, b = (s if s else (self.t.index("insert"), self.t.index("insert")))
        first, last = int(a.split(".")[0]), int(b.split(".")[0])
        if s and b.endswith(".0") and last > first:
            last -= 1
        self.t.edit_separator()
        n = 1
        for ln in range(first, last + 1):
            line = self.t.get(f"{ln}.0", f"{ln}.end")
            m = re.match(r"^(\s*)(• |\d+\. |☐ |☑ )", line)
            if m:
                self.t.delete(f"{ln}.{len(m.group(1))}", f"{ln}.{len(m.group(0))}")
                if (pre == "1. " and m.group(2)[0].isdigit()) or m.group(2) == pre or (pre == "☐ " and m.group(2) in ("☐ ", "☑ ")):
                    continue
            ind = len(line) - len(line.lstrip(" "))
            self.t.insert(f"{ln}.{ind}", f"{n}. " if pre == "1. " else pre)
            n += 1
        relink(self.t, self.terms)
        self._modified_force()
        self.t.focus_set()

    def make_link(self):
        if str(self.t.cget("state")) == "disabled":
            return
        s = self._sel()
        clip = ""
        try:
            clip = self.clipboard_get().strip()
        except tk.TclError:
            pass
        url = ask_string(self, "Lien", "Adresse du lien (https://…) :" if s else "Lien à insérer (https://…) :",
                         clip if is_url(clip) else "https://")
        if not url or url.strip() in ("https://", "http://"):
            return
        url = fix_url(url.strip())
        if s:
            name = f"href_{len(self.hrefs) + 1}"
            while name in self.hrefs:
                name += "x"
            self.hrefs[name] = url
            self.t.tag_configure(name)
            self.t.tag_add(name, *s)
            self.t.tag_add("href", *s)
        else:
            self.t.insert("insert", url + " ")
        self._modified_force()
        self.t.focus_set()

    def insert_ref(self):
        if str(self.t.cget("state")) == "disabled":
            return
        title = self.app.choose_reference()
        if title:
            self.t.insert("insert", f"[[{title}]]")
            relink(self.t, self.terms)
            self._modified_force()
        self.t.focus_set()

    def insert_date(self):
        if str(self.t.cget("state")) != "disabled":
            self.t.insert("insert", today())
            self.t.focus_set()

    def clear_format(self):
        s = self._sel()
        a, b = s if s else (self.t.index("insert linestart"), self.t.index("insert lineend"))
        for tg in RICH_TAGS + ("bi", "href") + tuple(self.hrefs):
            self.t.tag_remove(tg, a, b)
        self._modified_force()

    def insert_text(self, txt: str):
        self.t.insert("insert", txt)
        relink(self.t, self.terms)
        self._modified_force()

    def _menu(self, e):
        m = new_menu(self)
        st = "normal" if str(self.t.cget("state")) != "disabled" else "disabled"
        m.add_command(label="Couper", accelerator="Ctrl+X", command=lambda: self.t.event_generate("<<Cut>>"), state=st)
        m.add_command(label="Copier", accelerator="Ctrl+C", command=lambda: self.t.event_generate("<<Copy>>"))
        m.add_command(label="Coller", accelerator="Ctrl+V", command=lambda: self.t.event_generate("<<Paste>>"), state=st)
        m.add_command(label="Tout sélectionner", command=lambda: self.t.tag_add("sel", "1.0", "end-1c"))
        m.add_separator()
        f = new_menu(m)
        for lab, cmd in (("Gras", lambda: self.toggle("b")), ("Italique", lambda: self.toggle("i")),
                         ("Souligné", lambda: self.toggle("u")), ("Barré", lambda: self.toggle("s")),
                         ("Surligner", lambda: self.toggle("mark")), ("Code", lambda: self.toggle("code")),
                         ("Grand titre", lambda: self.heading("h1")), ("Titre", lambda: self.heading("h2")),
                         ("Sous-titre", lambda: self.heading("h3")), ("Citation", lambda: self.heading("quote")),
                         ("Texte normal", lambda: self.heading(None)), ("Effacer la mise en forme", self.clear_format)):
            f.add_command(label=lab, command=cmd, state=st)
        m.add_cascade(label="Mise en forme", menu=f)
        m.add_command(label="🔗 Lien…", accelerator="Ctrl+K", command=self.make_link, state=st)
        m.add_command(label="[[ ]] Référence vers une fiche…", command=self.insert_ref, state=st)
        idx = self.t.index(f"@{e.x},{e.y}")
        r = self.t.tag_prevrange("url", idx + "+1c")
        if r and self.t.compare(r[1], ">=", idx):
            u = self.t.get(*r)
            m.add_separator()
            m.add_command(label="🌐 Ouvrir le lien", command=lambda: open_url(u))
            m.add_command(label="📋 Copier le lien", command=lambda: copy_to_clipboard(self, fix_url(u)))
            m.add_command(label="＋ Ajouter ce lien comme fiche", command=lambda: self.app.add_urls([u]))
        sel = self._sel()
        if sel:
            txt = self.t.get(*sel)
            m.add_separator()
            m.add_command(label="❝ Faire une citation de la sélection", command=lambda: self.app.add_quote_dialog(txt))
            m.add_command(label="📝 Nouvelle note avec la sélection", command=lambda: self.app.new_note(text=txt))
            m.add_command(label="🔍 Chercher la sélection", command=lambda: self.app.search_for(txt[:80]))
        popup(m, e)
        return "break"


# ================================================================ visionneuse d'images
class ImageViewer(tk.Toplevel):
    """Zoom molette, glisser pour deplacer, F ajuster, 1 = 100 %, R rotation, ←/→ image precedente/suivante."""

    def __init__(self, app, paths: List[Tuple[str, str]], index: int = 0):
        super().__init__(app)
        self.app = app
        self.paths = paths
        self.index = index
        self.configure(bg=C["IMG_BG"])
        self.title("Grimoire — image")
        try:
            ico = os.path.join(BASE, "grimoire1.ico")
            if os.path.isfile(ico):
                self.iconbitmap(ico)
        except tk.TclError:
            pass
        x, y, w, h = work_area(self)
        self.geometry(f"{max(600, w - 80)}x{max(400, h - 80)}+{x + 40}+{y + 30}")
        bar = tk.Frame(self, bg=C["PANEL"])
        bar.pack(fill="x")
        self.l_title = tk.Label(bar, text="", bg=C["PANEL"], fg=C["HI"], font=fnt("GUIB"), anchor="w")
        self.l_title.pack(side="left", fill="x", expand=True, padx=8)
        for text, cmd, tip in (("✕", self.destroy, "Fermer (Échap)"), ("📂", self.open_ext, "Ouvrir avec l'application par défaut"),
                               ("⟳", lambda: self.rotate(-90), "Tourner (R)"), ("1:1", lambda: self.set_zoom(1.0), "Taille réelle (1)"),
                               ("⤢", self.fit, "Ajuster à la fenêtre (F)"), ("＋", lambda: self.zoom_by(1.25), "Zoom avant (+ ou molette)"),
                               ("－", lambda: self.zoom_by(0.8), "Zoom arrière (-)"), ("▶", lambda: self.go(1), "Image suivante (→)"),
                               ("◀", lambda: self.go(-1), "Image précédente (←)")):
            mk_button(bar, text, cmd, tip=tip).pack(side="right", padx=2, pady=3)
        self.l_info = tk.Label(bar, text="", bg=C["PANEL"], fg=C["DIM"], font=fnt("GSM"))
        self.l_info.pack(side="right", padx=8)
        self.cv = tk.Canvas(self, bg=C["IMG_BG"], highlightthickness=0, cursor="fleur")
        self.cv.pack(fill="both", expand=True)
        self.im = None
        self.tkimg = None
        self.zoom = 1.0
        self.rot = 0
        self.ox = self.oy = 0.0
        self.drag = None
        self.cv.bind("<Configure>", lambda _e: self.redraw())
        self.cv.bind("<MouseWheel>", lambda e: self.zoom_by(1.2 if wheel_steps(e) < 0 else 1 / 1.2, e.x, e.y))
        self.cv.bind("<Button-4>", lambda e: self.zoom_by(1.2, e.x, e.y))
        self.cv.bind("<Button-5>", lambda e: self.zoom_by(1 / 1.2, e.x, e.y))
        self.cv.bind("<ButtonPress-1>", lambda e: setattr(self, "drag", (e.x, e.y, self.ox, self.oy)))
        self.cv.bind("<B1-Motion>", self._move)
        self.cv.bind("<Double-Button-1>", lambda _e: self.fit())
        for k, f in (("<Escape>", lambda _e: self.destroy()), ("<Left>", lambda _e: self.go(-1)), ("<Right>", lambda _e: self.go(1)),
                     ("f", lambda _e: self.fit()), ("1", lambda _e: self.set_zoom(1.0)), ("r", lambda _e: self.rotate(-90)),
                     ("<plus>", lambda _e: self.zoom_by(1.25)), ("<minus>", lambda _e: self.zoom_by(0.8)),
                     ("<KP_Add>", lambda _e: self.zoom_by(1.25)), ("<KP_Subtract>", lambda _e: self.zoom_by(0.8))):
            self.bind(k, f)
        self.load()
        self.focus_force()

    def load(self):
        p, title = self.paths[self.index]
        self.l_title.configure(text=f"🖼 {title}   ({self.index + 1}/{len(self.paths)})")
        try:
            from PIL import Image, ImageOps  # type: ignore
            im = Image.open(p)
            try:
                im = ImageOps.exif_transpose(im)
            except Exception:
                pass
            if im.mode not in ("RGB", "RGBA"):
                im = im.convert("RGBA")
            self.im = im
            self.l_info.configure(text=f"{im.width}×{im.height} · {human_size(os.path.getsize(p))}")
        except Exception as ex:
            self.im = None
            self.l_info.configure(text=f"illisible : {ex}")
        self.rot = 0
        self.after(30, self.fit)

    def _src(self):
        if self.im is None:
            return None
        return self.im.rotate(self.rot, expand=True) if self.rot else self.im

    def fit(self):
        src = self._src()
        if src is None:
            return
        cw, ch = max(50, self.cv.winfo_width()), max(50, self.cv.winfo_height())
        self.zoom = min(cw / src.width, ch / src.height, 1.0 if max(src.width, src.height) < 200 else 99)
        self.ox = self.oy = 0
        self.redraw()

    def set_zoom(self, z: float):
        self.zoom = z
        self.redraw()

    def zoom_by(self, f: float, x: Optional[int] = None, y: Optional[int] = None):
        old = self.zoom
        self.zoom = max(0.02, min(20.0, self.zoom * f))
        if x is not None:
            cw, ch = self.cv.winfo_width(), self.cv.winfo_height()
            k = self.zoom / old
            self.ox = (self.ox - (x - cw / 2)) * k + (x - cw / 2)
            self.oy = (self.oy - (y - ch / 2)) * k + (y - ch / 2)
        self.redraw()

    def rotate(self, d: int):
        self.rot = (self.rot + d) % 360
        self.fit()

    def _move(self, e):
        if self.drag:
            x0, y0, ox, oy = self.drag
            self.ox, self.oy = ox + e.x - x0, oy + e.y - y0
            self.redraw()

    def redraw(self):
        self.cv.delete("all")
        src = self._src()
        if src is None:
            self.cv.create_text(self.cv.winfo_width() // 2, self.cv.winfo_height() // 2, text="Image illisible",
                                fill=C["ERR"], font=fnt("GTitle"))
            return
        try:
            from PIL import Image, ImageTk  # type: ignore
            w, h = max(1, int(src.width * self.zoom)), max(1, int(src.height * self.zoom))
            cw, ch = self.cv.winfo_width(), self.cv.winfo_height()
            # on ne redimensionne que la partie visible quand le zoom est fort
            if w * h > 25_000_000:
                x0 = max(0, int((w / 2 - cw / 2 - self.ox) / self.zoom))
                y0 = max(0, int((h / 2 - ch / 2 - self.oy) / self.zoom))
                x1 = min(src.width, int(x0 + cw / self.zoom) + 2)
                y1 = min(src.height, int(y0 + ch / self.zoom) + 2)
                crop = src.crop((x0, y0, x1, y1)).resize((max(1, int((x1 - x0) * self.zoom)), max(1, int((y1 - y0) * self.zoom))))
                self.tkimg = ImageTk.PhotoImage(crop, master=self)
                self.cv.create_image(cw / 2 + self.ox - w / 2 + x0 * self.zoom, ch / 2 + self.oy - h / 2 + y0 * self.zoom,
                                     image=self.tkimg, anchor="nw")
            else:
                rs = Image.Resampling.LANCZOS if self.zoom < 1 else Image.Resampling.NEAREST if self.zoom > 3 else Image.Resampling.BILINEAR
                self.tkimg = ImageTk.PhotoImage(src.resize((w, h), rs), master=self)
                self.cv.create_image(cw / 2 + self.ox, ch / 2 + self.oy, image=self.tkimg)
            self.cv.create_text(10, ch - 10, anchor="sw", text=f"{self.zoom * 100:.0f} %", fill=C["DIM"], font=fnt("GSM"))
        except Exception as ex:
            logger.warning("visionneuse : %s", ex)

    def go(self, d: int):
        if len(self.paths) > 1:
            self.index = (self.index + d) % len(self.paths)
            self.load()

    def open_ext(self):
        open_path(self.paths[self.index][0])


# ================================================================ mode lecture
class ReaderWindow(tk.Toplevel):
    """Lecture confortable plein ecran, une fiche a la fois (←/→), A-/A+, Echap pour fermer."""

    def __init__(self, app, ids: List[int], index: int = 0, terms: Optional[List[str]] = None):
        super().__init__(app)
        self.app = app
        self.ids = ids
        self.index = max(0, min(index, len(ids) - 1))
        self.terms = terms or []
        self.imgs: List[Any] = []
        self.hrefs: Dict[str, str] = {}
        self.title("Grimoire — lecture")
        self.configure(bg=C["CARD"])
        try:
            ico = os.path.join(BASE, "grimoire1.ico")
            if os.path.isfile(ico):
                self.iconbitmap(ico)
        except tk.TclError:
            pass
        x, y, w, h = work_area(self)
        self.geometry(f"{w}x{h - 30}+{x}+{y}")
        try:
            self.state("zoomed")
        except tk.TclError:
            pass
        bar = tk.Frame(self, bg=C["PANEL"])
        bar.pack(fill="x")
        mk_label(bar, "📖 Mode lecture", "HI", "GUIB").pack(side="left", padx=10, pady=4)
        self.l_pos = mk_label(bar, "", "DIM", "GSM")
        self.l_pos.pack(side="left", padx=10)
        for text, cmd, tip in (("✕ Fermer", self.destroy, "Échap"), ("A+", lambda: self.font(1), "Texte plus grand (Ctrl++)"),
                               ("A−", lambda: self.font(-1), "Texte plus petit (Ctrl+-)"), ("✏ Modifier", self.edit, "Revenir à la fiche pour la modifier"),
                               ("Suivante ▶", lambda: self.go(1), "→ ou Page suivante"), ("◀ Précédente", lambda: self.go(-1), "← ou Page précédente")):
            mk_button(bar, text, cmd, tip=tip).pack(side="right", padx=3, pady=3)
        fr = tk.Frame(self, bg=C["CARD"])
        fr.pack(fill="both", expand=True)
        self.t = tk.Text(fr, bg=C["CARD"], fg=C["TEXT"], relief="flat", wrap="word", highlightthickness=0, spacing1=3,
                         spacing2=2, spacing3=3, selectbackground=C["SEL"], selectforeground=C["ON_SEL"], cursor="arrow")
        sb = ttk.Scrollbar(fr, orient="vertical", command=self.t.yview)
        self.t.configure(yscrollcommand=sb.set)
        self.t.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        configure_rich_tags(self.t, reading=True)
        self.t.tag_configure("meta", font=fnt("GUI"), foreground=C["DIM"], spacing3=10)
        self.t.tag_configure("rtitle", font=fnt("RH1"), foreground=C["HI"], spacing1=10, spacing3=6)
        self.t.tag_configure("sect", font=fnt("RH3"), foreground=C["FG"], spacing1=16, spacing3=4)
        self.t.tag_configure("cite", font=fnt("RI"), foreground=C["TEXT"], lmargin1=30, lmargin2=30)
        self.t.tag_configure("center", justify="center")
        for tg in ("url", "ref", "href"):
            self.t.tag_bind(tg, "<Enter>", lambda _e: self.t.configure(cursor="hand2"))
            self.t.tag_bind(tg, "<Leave>", lambda _e: self.t.configure(cursor="arrow"))
        self.t.tag_bind("url", "<Button-1>", self._click_url)
        self.t.tag_bind("href", "<Button-1>", self._click_href)
        self.t.tag_bind("ref", "<Button-1>", self._click_ref)
        self.t.bind("<Configure>", lambda _e: self._margins())
        self.t.bind("<Key>", lambda e: None if (e.state & 0x4 and e.keysym.lower() in ("c", "a")) else "break")
        for k, f in (("<Escape>", lambda _e: self.destroy()), ("<Left>", lambda _e: self.go(-1)), ("<Right>", lambda _e: self.go(1)),
                     ("<Prior>", lambda _e: self.go(-1)), ("<Next>", lambda _e: self.go(1)),
                     ("<Control-plus>", lambda _e: self.font(1)), ("<Control-equal>", lambda _e: self.font(1)),
                     ("<Control-minus>", lambda _e: self.font(-1)), ("<Up>", lambda _e: self.t.yview_scroll(-3, "units")),
                     ("<Down>", lambda _e: self.t.yview_scroll(3, "units")), ("<space>", lambda _e: self.t.yview_scroll(1, "pages"))):
            self.bind(k, f)
        self.t.bind("<MouseWheel>", lambda e: (self.t.yview_scroll(wheel_steps(e) * 3, "units"), "break")[1])
        self.render()
        self.focus_force()

    def _margins(self):
        w = self.t.winfo_width()
        m = max(20, (w - 900) // 2)
        self.t.configure(padx=m)

    def font(self, d: int):
        self.app.zoom(d)
        configure_rich_tags(self.t, reading=True)
        self.render()

    def go(self, d: int):
        n = self.index + d
        if 0 <= n < len(self.ids):
            self.index = n
            self.render()

    def edit(self):
        iid = self.ids[self.index]
        self.destroy()
        self.app.goto_item(iid)

    def render(self):
        st = self.app.store
        t = self.t
        t.configure(state="normal")
        t.delete("1.0", "end")
        self.imgs.clear()
        for name in list(self.hrefs):
            try:
                t.tag_delete(name)
            except tk.TclError:
                pass
        self.hrefs = {}
        it = st.item(self.ids[self.index]) if self.ids else None
        self.l_pos.configure(text=f"{self.index + 1} / {len(self.ids)}")
        if not it:
            t.insert("end", "Rien à lire.", "rtitle")
            t.configure(state="disabled")
            return
        m = st.meta(it)
        ic = TYPES.get(it["type"], TYPES["file"])["icon"]
        t.insert("end", f"{ic} {it.get('title') or '(sans titre)'}\n", "rtitle")
        bits = [st.subject_label(it["subject_id"]), TYPES.get(it["type"], TYPES["file"])["label"],
                fmt_date(it.get("event_date") or it.get("created") or "", False)]
        if it.get("author"):
            bits.append("par " + it["author"])
        if it.get("tags"):
            bits.append(" ".join("#" + x for x in tag_list(it["tags"])))
        t.insert("end", "   ·   ".join(b for b in bits if b) + "\n", "meta")
        img_rel = it.get("file") if it["type"] == "image" else it.get("thumb")
        if img_rel and os.path.isfile(Paths.abs(img_rel)):
            try:
                from PIL import Image, ImageTk  # type: ignore
                with Image.open(Paths.abs(img_rel)) as im:
                    im = im.convert("RGBA") if im.mode not in ("RGB", "RGBA") else im.copy()
                maxw = min(860, max(300, self.t.winfo_width() - 120))
                im.thumbnail((maxw, 640))
                ph = ImageTk.PhotoImage(im, master=self)
                self.imgs.append(ph)
                t.image_create("end", image=ph, padx=4, pady=6)
                t.insert("end", "\n")
            except Exception:
                pass
        if it.get("url"):
            t.insert("end", "🔗 ")
            t.insert("end", it["url"], "url")
            t.insert("end", "\n")
        if m.get("description"):
            t.insert("end", m["description"] + "\n", "i")
        runs = runs_from_any(it.get("body"))
        if runs:
            if it["type"] == "quote":
                t.insert("end", "\n« ", "cite")
                insert_runs(t, [[r[0], r[1] + ["i"]] for r in runs], self.hrefs)
                t.insert("end", " »\n", "cite")
                src = " — " + ", ".join(x for x in (it.get("author"), it.get("source"), m.get("page")) if x)
                t.insert("end", src + "\n", "meta")
            else:
                if it["type"] not in ("note",):
                    t.insert("end", "\nNotes\n", "sect")
                insert_runs(t, runs, self.hrefs)
                t.insert("end", "\n")
        if it.get("extracted") and it["type"] not in ("link", "video"):
            lab = {"voice": "Transcription", "audio": "Transcription", "image": "Texte reconnu (OCR)"}.get(it["type"], "Texte du document")
            t.insert("end", f"\n{lab}\n", "sect")
            t.insert("end", it["extracted"][:60000] + ("\n…" if len(it["extracted"]) > 60000 else "") + "\n")
        for tg in self.hrefs:
            t.tag_configure(tg)
        refresh_combo(t)
        relink(t, self.terms)
        t.configure(state="disabled")
        t.yview_moveto(0)
        self._margins()

    def _click_url(self, e):
        idx = self.t.index(f"@{e.x},{e.y}")
        r = self.t.tag_prevrange("url", idx + "+1c")
        if r:
            open_url(self.t.get(*r))

    def _click_href(self, e):
        idx = self.t.index(f"@{e.x},{e.y}")
        name = next((tg for tg in self.t.tag_names(idx) if tg.startswith("href_")), "")
        if name in self.hrefs:
            open_url(self.hrefs[name])

    def _click_ref(self, e):
        idx = self.t.index(f"@{e.x},{e.y}")
        r = self.t.tag_prevrange("ref", idx + "+1c")
        if r:
            title = self.t.get(*r).strip("[]")
            it = self.app.store.find_by_title(title)
            if it:
                if it["id"] in self.ids:
                    self.index = self.ids.index(it["id"])
                else:
                    self.ids.insert(self.index + 1, it["id"])
                    self.index += 1
                self.render()
            else:
                self.destroy()
                self.app.follow_ref(title)


# ================================================================ palette « Aller a » (Ctrl+G)
class Palette(tk.Toplevel):
    """Aller a un sujet ou une fiche au clavier ; en mode reference, retourne un titre pour [[...]]."""

    def __init__(self, app, mode: str = "goto", on_pick: Optional[Callable[[Tuple[str, int, str]], None]] = None):
        super().__init__(app)
        self.app = app
        self.mode = mode
        self.on_pick = on_pick
        self.overrideredirect(True)
        self.configure(bg=C["HI"])
        try:
            self.attributes("-topmost", True)
        except tk.TclError:
            pass
        top = app.winfo_toplevel()
        W = min(780, max(420, top.winfo_width() - 60))
        H = min(470, max(260, top.winfo_height() - 80))
        x = top.winfo_rootx() + (top.winfo_width() - W) // 2
        y = top.winfo_rooty() + max(20, top.winfo_height() // 8)
        self.geometry(f"{W}x{H}+{x}+{y}")
        inner = tk.Frame(self, bg=C["PANEL"])
        inner.pack(fill="both", expand=True, padx=2, pady=2)
        hd = tk.Frame(inner, bg=C["PANEL"])
        hd.pack(fill="x", padx=10, pady=(8, 4))
        tk.Label(hd, text="🧭" if mode == "goto" else "[[", bg=C["PANEL"], fg=C["HI"], font=fnt("GTitle")).pack(side="left")
        self.v = tk.StringVar()
        self.entry = tk.Entry(hd, textvariable=self.v, bg=C["ENTRY_BG"], fg=C["ENTRY_FG"], insertbackground=C["HI"],
                              relief="flat", font=fnt("GBig"), highlightthickness=1, highlightbackground=C["LINE"],
                              highlightcolor=C["HI"])
        self.entry.pack(side="left", fill="x", expand=True, padx=8, ipady=3)
        lf = tk.Frame(inner, bg=C["CARD"])
        lf.pack(fill="both", expand=True, padx=10, pady=4)
        self.lb = tk.Listbox(lf, bg=C["CARD"], fg=C["TEXT"], selectbackground=C["SEL"], selectforeground=C["ON_SEL"],
                             font=fnt("GUI"), activestyle="none", relief="flat", highlightthickness=0, bd=0)
        sb = ttk.Scrollbar(lf, orient="vertical", command=self.lb.yview)
        self.lb.configure(yscrollcommand=sb.set)
        self.lb.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        hint = ("Entrée : aller · ↑↓ : choisir · Échap : fermer" if mode == "goto"
                else "Entrée : insérer la référence · si rien ne correspond, le texte tapé est utilisé")
        tk.Label(inner, text=hint, bg=C["PANEL"], fg=C["DIM"], font=fnt("GSM")).pack(anchor="w", padx=10, pady=(0, 6))
        self.items: List[Tuple[str, int, str]] = []
        self.v.trace_add("write", lambda *_a: self.fill())
        for w in (self.entry, self.lb):
            w.bind("<Return>", lambda _e: self.go())
            w.bind("<Escape>", lambda _e: self.close())
        self.entry.bind("<Down>", lambda _e: self.move(1))
        self.entry.bind("<Up>", lambda _e: self.move(-1))
        self.lb.bind("<Double-Button-1>", lambda _e: self.go())
        self.bind("<FocusOut>", lambda _e: self.after(200, lambda: self.close() if self.winfo_exists() and self.focus_get() is None else None))
        self.fill()
        self.after(30, self.entry.focus_force)

    def fill(self):
        st = self.app.store
        q = self.v.get().strip()
        res: List[Tuple[str, int, str]] = []
        nq = norm(q)
        for sid in self.app.subject_order():
            path = st.subject_path(sid)
            if not nq or all(t in norm(path) for t in nq.split()):
                s = st.subject(sid)
                res.append(("s", sid, f"{s['icon'] or '📁'}  {path}"))
        if q:
            for it in st.search(q, limit=60):
                res.append(("i", it["id"], f"{TYPES.get(it['type'], TYPES['file'])['icon']}  {it['title'] or '(sans titre)'}"
                                          f"    — {st.subject_path(it['subject_id'])}"))
        else:
            for it in st.items_where("1=1 ORDER BY COALESCE(opened, updated) DESC", limit=15):
                res.append(("i", it["id"], f"{TYPES.get(it['type'], TYPES['file'])['icon']}  {it['title'] or '(sans titre)'}"
                                          f"    — {st.subject_path(it['subject_id'])}"))
        if not q:
            res = res[:40] + [r for r in res[40:] if r[0] == "i"]
        self.items = res[:120]
        self.lb.delete(0, "end")
        for _k, _i, lab in self.items:
            self.lb.insert("end", " " + lab)
        if self.items:
            self.lb.selection_set(0)

    def move(self, d):
        if not self.items:
            return "break"
        cur = self.lb.curselection()
        i = max(0, min(len(self.items) - 1, (cur[0] if cur else -1) + d))
        self.lb.selection_clear(0, "end")
        self.lb.selection_set(i)
        self.lb.see(i)
        return "break"

    def go(self):
        cur = self.lb.curselection()
        pick: Optional[Tuple[str, int, str]] = self.items[cur[0]] if cur and self.items else None
        if pick is None and self.mode == "ref" and self.v.get().strip():
            pick = ("t", 0, self.v.get().strip())
        self.close()
        if pick and self.on_pick:
            self.app.after(20, lambda: self.on_pick(pick))
        return "break"

    def close(self):
        try:
            self.destroy()
        except tk.TclError:
            pass


# ================================================================ enregistreur de memo vocal
class RecorderDialog(Dialog):
    def __init__(self, app, sid: int):
        super().__init__(app, "Mémo vocal", 620, 430, resizable=False)
        self.app = app
        self.sid = sid
        self.rec = Recorder()
        self.path = ""
        self.state_ = "idle"
        self.job = None
        self.button_bar([("Annuler", self.cancel, ""), ("✔ Enregistrer le mémo", self.save, "accent")])
        self.b_save = self.winfo_children()[-1].winfo_children()[0]
        f = tk.Frame(self, bg=C["BG"])
        f.pack(fill="both", expand=True, padx=14, pady=10)
        mk_label(f, f"🎙 Nouveau mémo dans : {app.store.subject_label(sid)}", "HI", "GUIB", wraplength=560,
                 justify="left").pack(anchor="w")
        df = tk.Frame(f, bg=C["BG"])
        df.pack(fill="x", pady=(10, 4))
        mk_label(df, "Micro :", "FG", "GUI").pack(side="left")
        self.cb = ttk.Combobox(df, state="readonly", font=fnt("GUI"), width=40)
        self.cb.pack(side="left", padx=6, fill="x", expand=True)
        mk_button(df, "↻ Actualiser", self.load_devices, font_name="GSM", tip="Relire la liste des micros").pack(side="left")
        mid = tk.Frame(f, bg=C["BG"])
        mid.pack(fill="x", pady=12)
        self.b_rec = mk_button(mid, "●  Enregistrer", self.toggle, "rec", font_name="GTitle")
        self.b_rec.pack(side="left", padx=(0, 16), ipady=6)
        self.l_time = mk_label(mid, "0:00", "HI", "GBig")
        self.l_time.pack(side="left")
        self.vu = tk.Canvas(f, height=18, bg=C["ENTRY_BG"], highlightthickness=1, highlightbackground=C["LINE"])
        self.vu.pack(fill="x", pady=4)
        self.v_title = tk.StringVar(value=f"Mémo du {fmt_date(now_iso())}")
        tf = tk.Frame(f, bg=C["BG"])
        tf.pack(fill="x", pady=(8, 2))
        mk_label(tf, "Titre :", "FG", "GUI").pack(side="left")
        mk_entry(tf, self.v_title, 40).pack(side="left", fill="x", expand=True, padx=6, ipady=2)
        self.v_tr = tk.BooleanVar(value=whisper_available() and bool(app.store.get("auto_transcribe", True)))
        self.chk = mk_check(f, "📝 Transcrire en texte ensuite (faster-whisper, local)", self.v_tr)
        self.chk.pack(anchor="w", pady=(6, 0))
        if not whisper_available():
            self.chk.configure(state="disabled")
            mk_label(f, "Transcription : module faster-whisper non installé (optionnel, menu Outils). "
                        "Le son est quand même gardé et tu peux écrire un résumé dans les notes.",
                     "DIM", "GSM", wraplength=570, justify="left").pack(anchor="w")
        self.l_msg = mk_label(f, "", "WARN", "GSM", wraplength=570, justify="left")
        self.l_msg.pack(anchor="w", pady=(6, 0))
        self.bind("<space>", lambda _e: (self.toggle(), "break")[1])
        self.load_devices()
        self.show(self.b_rec)

    def load_devices(self):
        devs, dflt, err = Recorder.devices()
        self.devs = devs
        self.cb.configure(values=[lab for _i, lab in devs])
        if devs:
            idx = next((k for k, (i, _l) in enumerate(devs) if i == dflt), 0)
            self.cb.current(idx)
            self.b_rec.configure(state="normal")
            self.l_msg.configure(text="Espace ou ● pour commencer, puis ■ pour arrêter.", fg=C["DIM"])
        else:
            self.cb.set("(aucun micro)")
            self.b_rec.configure(state="disabled")
            self.l_msg.configure(text="⚠ " + (err or "Aucun micro détecté."), fg=C["WARN"])
        self._update_save()

    def _update_save(self):
        try:
            self.b_save.configure(state="normal" if self.state_ == "done" else "disabled")
        except Exception:
            pass

    def toggle(self):
        if self.state_ == "rec":
            self.stop()
        elif self.devs:
            self.start()

    def start(self):
        if self.path and os.path.isfile(self.path):
            try:
                os.remove(self.path)
            except OSError:
                pass
        dev = self.devs[self.cb.current()][0] if self.cb.current() >= 0 else None
        d = os.path.join(Paths.data, "_temp")
        os.makedirs(d, exist_ok=True)
        self.path = os.path.join(d, f"memo_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.flac")
        err = self.rec.start(self.path, dev)
        if err:
            self.l_msg.configure(text="⚠ " + err, fg=C["ERR"])
            return
        self.state_ = "rec"
        self.b_rec.configure(text="■  Arrêter")
        self.l_msg.configure(text="Enregistrement… (Espace pour arrêter)", fg=C["OK"])
        self._update_save()
        self._tick()

    def _tick(self):
        if self.state_ != "rec":
            return
        self.l_time.configure(text=fmt_dur(self.rec.duration()))
        w = self.vu.winfo_width()
        lv = min(1.0, self.rec.level * 1.6)
        self.vu.delete("all")
        col = C["OK"] if lv < 0.7 else (C["WARN"] if lv < 0.92 else C["ERR"])
        self.vu.create_rectangle(0, 0, int(w * lv), 20, fill=col, width=0)
        self.job = self.after(80, self._tick)

    def stop(self):
        p, d = self.rec.stop()
        self.state_ = "done" if d > 0.3 else "idle"
        self.b_rec.configure(text="●  Recommencer")
        self.l_time.configure(text=fmt_dur(d))
        self.vu.delete("all")
        self.l_msg.configure(text=(f"Mémo de {fmt_dur(d)} prêt : « Enregistrer le mémo » pour le garder." if d > 0.3
                                   else "Trop court, recommence."), fg=C["OK"] if d > 0.3 else C["WARN"])
        self._update_save()

    def save(self):
        if self.state_ == "rec":
            self.stop()
        if self.state_ != "done" or not os.path.isfile(self.path):
            return
        self.result = {"path": self.path, "title": self.v_title.get().strip() or "Mémo vocal",
                       "duration": self.rec.duration(), "transcribe": bool(self.v_tr.get())}
        self.destroy()

    def cancel(self):
        if self.job:
            try:
                self.after_cancel(self.job)
            except Exception:
                pass
        if self.state_ == "rec":
            self.rec.cancel()
        elif self.path and os.path.isfile(self.path):
            try:
                os.remove(self.path)
            except OSError:
                pass
        self.result = None
        self.destroy()
