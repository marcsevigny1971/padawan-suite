# -*- coding: utf-8 -*-
"""padawan_cartes - cartes « Sources » dépliables pour Padawan (padawan39.py).

Chaque carte se déplie SUR PLACE (clic sur la carte ou « ▸ Détails ») : extrait complet,
résumé IA s'il existe, texte de la page chargé en arrière-plan, le tout dans une zone avec sa
propre barre verticale. Plus besoin d'ouvrir le Lecteur pour lire les détails.

Extras : « ⇕ Tout déplier / replier », filtre 🔎 instantané, mots de la recherche surlignés,
temps de lecture estimé, 📋 Copier (titre + lien + texte), ⤢ zone plus grande.
Rien n'est écrit sur disque ; le texte chargé est gardé dans la carte (le Lecteur en profite).
"""
from __future__ import annotations

import re
import threading
import unicodedata
import tkinter as tk
from tkinter import ttk

SMALL_LINES = 9
BIG_LINES = 22
_SEM = threading.Semaphore(3)  # au plus 3 pages chargées en même temps
STOP = {"les", "des", "une", "pour", "dans", "avec", "sur", "que", "qui", "est", "aux", "par", "pas",
        "svp", "moi", "donne", "donnes", "nouvelles", "the", "and", "for", "plus", "mais", "ces", "ses"}


class _Tip:
    """Petite bulle d'aide au survol."""

    def __init__(self, w, text, C):
        self.w, self.text, self.C, self.tw, self.job = w, text, C, None, None
        w.bind("<Enter>", self._sched, add="+")
        w.bind("<Leave>", self._hide, add="+")
        w.bind("<ButtonPress>", self._hide, add="+")

    def _sched(self, e=None):
        self._cancel()
        self.job = self.w.after(550, self._show)

    def _cancel(self):
        if self.job:
            try:
                self.w.after_cancel(self.job)
            except Exception:
                pass
            self.job = None

    def _show(self):
        self.job = None
        try:
            self.tw = tk.Toplevel(self.w)
            self.tw.wm_overrideredirect(True)
            self.tw.attributes("-topmost", True)
            tk.Label(self.tw, text=self.text, bg=self.C.get("card2", "#333"), fg=self.C.get("fg", "#eee"),
                     font=("Segoe UI", 8), relief="solid", bd=1, padx=6, pady=3, justify="left",
                     wraplength=320).pack()
            x = self.w.winfo_rootx() + 6
            y = self.w.winfo_rooty() + self.w.winfo_height() + 3
            self.tw.wm_geometry(f"+{x}+{y}")
        except Exception:
            self.tw = None

    def _hide(self, e=None):
        self._cancel()
        if self.tw is not None:
            try:
                self.tw.destroy()
            except Exception:
                pass
            self.tw = None


def _fold(t: str) -> str:
    """Minuscules sans accents, même longueur (é → e) : « geopolitique » trouve « géopolitique »."""
    out = []
    for ch in t or "":
        d = unicodedata.normalize("NFD", ch)
        b = "".join(c for c in d if not unicodedata.combining(c))
        out.append((b[:1] or ch).lower() if len(b) >= 1 else ch.lower())
    return "".join(out)


def _query_words(q: str):
    words = [w for w in re.findall(r"[\w'-]{3,}", _fold(q)) if w not in STOP and not w.isdigit()]
    return sorted(set(words), key=len, reverse=True)[:8]


def _reading_time(text: str) -> str:
    n = len((text or "").split())
    if n < 40:
        return ""
    m = max(1, round(n / 230))
    return f"{n} mots · ~{m} min de lecture"


def _st(app):
    st = getattr(app, "_cartes_state", None)
    if st is None:
        st = {"open": set(), "big": set(), "filter": None, "all_btn": None, "count": None, "loading": set()}
        app._cartes_state = st
    return st


def _install_bar(app, g):
    """Ajoute ⇕ Tout déplier, le filtre 🔎 et le compteur à la barre du haut (une seule fois)."""
    st = _st(app)
    if st["filter"] is not None:
        return
    C = g["C"]
    top = app.read3_btn.master
    st["all_btn"] = tk.Button(top, text="⇕ Tout déplier", command=lambda: toggle_all(app, g),
                              bg=C["card"], fg=C["fg"], relief="flat", font=("Segoe UI", 8, "bold"),
                              padx=8, pady=3, cursor="hand2", activebackground=C["gold"],
                              activeforeground="#1a1408")
    st["all_btn"].pack(side="left", padx=(0, 4))
    _Tip(st["all_btn"], "Déplier ou replier les détails de toutes les cartes d'un coup", C)
    var = tk.StringVar()
    st["filter"] = var
    ent = tk.Entry(top, textvariable=var, width=14, bg=C.get("input", C["card"]), fg=C["fg"],
                   insertbackground=C["fg"], relief="flat", font=("Segoe UI", 9),
                   highlightthickness=1, highlightbackground=C["line"], highlightcolor=C["gold"])
    ent.pack(side="right", padx=(2, 0), ipady=2)
    tk.Label(top, text="🔎", bg=C["bg"], fg=C["dim"], font=("Segoe UI", 9)).pack(side="right")
    _Tip(ent, "Filtrer les cartes : tape un mot (titre, site ou texte). Échap = effacer.", C)
    ent.bind("<Escape>", lambda e: var.set(""))
    var.trace_add("write", lambda *a: app.after(120, lambda: draw_sources(app, g)))
    st["count"] = tk.Label(top, text="", bg=C["bg"], fg=C["dim"], font=("Segoe UI", 8))
    st["count"].pack(side="right", padx=4)
    app._cartes_entry = ent


def toggle_all(app, g):
    st = _st(app)
    urls = [h["url"] for h in (app.hits or [])]
    if urls and all(u in st["open"] for u in urls):
        st["open"].clear()
    else:
        st["open"].update(urls)
    draw_sources(app, g)


def _ensure_body(app, g, it):
    """Charge le texte de la page en arrière-plan (une seule fois), puis rafraîchit la carte."""
    st = _st(app)
    url = it.get("url") or ""
    if it.get("body") or it.get("_cartes_fail") or url in st["loading"] or not url:
        return
    try:
        if g["is_dead"](url):
            it["_cartes_fail"] = True
            return
    except Exception:
        pass
    st["loading"].add(url)

    def job():
        body = ""
        try:
            _SEM.acquire()
            if app.router.can("read_page"):
                body = app.router.call_tool("read_page", url=url, limit=6000) or ""
            else:
                body = g["read_page"](url, 6000) or ""
        except Exception:
            body = ""
        finally:
            _SEM.release()

        def done():
            st["loading"].discard(url)
            for h in app.hits or []:
                if h.get("url") == url:
                    if body.strip():
                        h["body"] = body[:6000]
                    else:
                        h["_cartes_fail"] = True
            box = getattr(app, "_cartes_boxes", {}).get(url)
            if box is not None:
                try:
                    _fill_details(app, g, box, next((h for h in app.hits if h.get("url") == url), it))
                except Exception:
                    pass

        app.after0(done)

    threading.Thread(target=job, daemon=True).start()


def _fill_details(app, g, txt: tk.Text, it):
    C = g["C"]
    st = _st(app)
    txt.configure(state="normal")
    txt.delete("1.0", "end")
    snip = (it.get("snippet") or "").strip()
    body = (it.get("body") or "").strip()
    summ = (it.get("dig_summary") or "").strip()
    meta = _reading_time(body)
    txt.insert("end", (g["host_of"](it["url"]) + (f"  ·  {meta}" if meta else "")) + "\n", "meta")
    if summ:
        txt.insert("end", "Résumé IA\n", "h")
        txt.insert("end", summ + "\n\n")
    if snip and (not body or snip[:60] not in body):
        txt.insert("end", "Extrait\n", "h")
        txt.insert("end", snip + "\n\n")
    if body:
        txt.insert("end", "Texte de la page\n", "h")
        txt.insert("end", body + "\n\n")
    elif it.get("url") in st["loading"]:
        txt.insert("end", "⏳ Chargement du texte de la page…\n", "dim")
    elif it.get("_cartes_fail"):
        txt.insert("end", "Texte non disponible ici (paywall, JavaScript ou délai). Essaie « Site ».\n", "dim")
    txt.insert("end", it["url"], "url")
    words = _query_words(getattr(app, "last_q", "") or getattr(app, "_hunt_query", ""))
    if words:
        flat = _fold(txt.get("1.0", "end-1c"))
        rx = re.compile("|".join(re.escape(w) for w in words))
        for m in list(rx.finditer(flat))[:400]:
            txt.tag_add("hl", f"1.0+{m.start()}c", f"1.0+{m.end()}c")
    txt.tag_configure("hl", background=C.get("sel", "#554400"), foreground=C["gold"])
    txt.configure(state="disabled")


def _copy(app, g, it):
    body = (it.get("dig_summary") or it.get("body") or it.get("snippet") or "").strip()
    txt = f"{it.get('title', '')}\n{it['url']}\n\n{body[:3000]}".strip()
    try:
        app.clipboard_clear()
        app.clipboard_append(txt)
        app.status.config(text="📋 carte copiée", fg=g["C"]["ok"])
    except Exception:
        pass


def _match(it, f: str) -> bool:
    if not f:
        return True
    hay = _fold(" ".join([it.get("title", ""), it.get("url", ""), it.get("snippet", ""),
                          (it.get("body") or "")[:3000], it.get("dig_summary", "")]))
    return all(p in hay for p in _fold(f).split())


def draw_sources(app, g):
    """Remplace Padawan.draw_sources : cartes dépliables avec détails défilants."""
    C, host_of = g["C"], g["host_of"]
    _install_bar(app, g)
    st = _st(app)
    for w in app.src_in.winfo_children():
        w.destroy()
    app._cartes_boxes = {}
    hits = list(app.hits or [])
    urls = {h["url"] for h in hits}
    st["open"] &= urls
    st["big"] &= urls
    if st["all_btn"] is not None:
        st["all_btn"].configure(text="⇕ Tout replier" if hits and all(h["url"] in st["open"] for h in hits)
                                else "⇕ Tout déplier")
    if not hits:
        if st["count"] is not None:
            st["count"].configure(text="")
        tk.Label(app.src_in, text="Lance une chasse.\nClic sur une carte = détails ici · « Lire » = Lecteur.",
                 bg=C["bg"], fg=C["dim"], justify="left", font=("Segoe UI", 9)).pack(anchor="w", padx=8, pady=10)
        return
    f = (st["filter"].get() if st["filter"] is not None else "").strip()
    shown = [(i, it) for i, it in enumerate(hits, 1) if _match(it, f)]
    if st["count"] is not None:
        st["count"].configure(text=f"{len(shown)}/{len(hits)}" if f else f"{len(hits)} sources")
    if not shown:
        tk.Label(app.src_in, text=f"Aucune carte ne contient « {f} ».", bg=C["bg"], fg=C["dim"],
                 font=("Segoe UI", 9)).pack(anchor="w", padx=8, pady=10)
    wrap = max(220, int(app.src_canvas.winfo_width() or 300) - 28)
    for i, it in shown:
        _card(app, g, i, it, wrap)
    app.after(30, lambda: _refresh_scroll(app))


def _refresh_scroll(app):
    try:
        app.src_in.update_idletasks()
        app.src_canvas.configure(scrollregion=app.src_canvas.bbox("all"))
    except Exception:
        pass


def _card(app, g, i, it, wrap):
    C, host_of = g["C"], g["host_of"]
    st = _st(app)
    url = it["url"]
    sel = url == app.active_url
    is_open = url in st["open"]
    bg = C["sel"] if sel else C["card"]
    card = tk.Frame(app.src_in, bg=bg, highlightbackground=C["gold"] if (sel or is_open) else C["line"],
                    highlightthickness=1, cursor="hand2")
    card.pack(fill="x", padx=5, pady=2)
    inner = tk.Frame(card, bg=bg, cursor="hand2")
    inner.pack(fill="x", padx=7, pady=5)
    badge = " · profond" if it.get("body") else ""
    if it.get("dig_summary"):
        badge += " · résumé IA"
    head = tk.Frame(inner, bg=bg)
    head.pack(fill="x")
    tk.Label(head, text=f"{i}  {host_of(url)}{badge}", bg=bg, fg=C["gold"],
             font=("Segoe UI", 7, "bold")).pack(side="left")
    chev = tk.Label(head, text="▾" if is_open else "▸", bg=bg, fg=C["gold"], font=("Segoe UI", 10, "bold"))
    chev.pack(side="right")
    title = tk.Label(inner, text=it["title"], bg=bg, fg=C["fg"], wraplength=wrap, justify="left",
                     font=("Segoe UI", 9, "bold"))
    title.pack(anchor="w", pady=(1, 1))
    snip_lbl = None
    if it.get("snippet") and not is_open:
        s = it["snippet"]
        snip_lbl = tk.Label(inner, text=s[:110] + ("…" if len(s) > 110 else ""), bg=bg, fg=C["dim"],
                            wraplength=wrap, justify="left", font=("Segoe UI", 8))
        snip_lbl.pack(anchor="w", pady=(0, 3))
    if is_open:
        big = url in st["big"]
        box = tk.Frame(inner, bg=C["line"])
        box.pack(fill="x", pady=(3, 4))
        txt = tk.Text(box, height=BIG_LINES if big else SMALL_LINES, wrap="word", bg=C.get("panel", C["card2"]),
                      fg=C["fg"], font=("Segoe UI", 9), relief="flat", padx=8, pady=6, cursor="arrow",
                      highlightthickness=0, bd=0)
        sb = ttk.Scrollbar(box, orient="vertical", command=txt.yview)
        try:
            sb.configure(style="Gold.Vertical.TScrollbar")
        except Exception:
            pass
        txt.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        txt.pack(side="left", fill="both", expand=True, padx=(1, 0), pady=1)
        txt.tag_configure("h", foreground=C["gold"], font=("Segoe UI", 9, "bold"), spacing1=4)
        txt.tag_configure("meta", foreground=C["cyan"], font=("Segoe UI", 8))
        txt.tag_configure("dim", foreground=C["dim"], font=("Segoe UI", 9, "italic"))
        txt.tag_configure("url", foreground=C["link"], underline=True)
        txt.tag_bind("url", "<Button-1>", lambda e, u=url: app.open_browser(u))
        txt.tag_bind("url", "<Enter>", lambda e: txt.configure(cursor="hand2"))
        txt.tag_bind("url", "<Leave>", lambda e: txt.configure(cursor="arrow"))

        def _wheel(e, t=txt):
            first, last = t.yview()
            d = int(-1 * (e.delta / 120)) if getattr(e, "delta", 0) else (-1 if getattr(e, "num", 0) == 4 else 1)
            if (d < 0 and first <= 0.0) or (d > 0 and last >= 1.0):
                return None  # au bout du texte : la liste des cartes défile
            t.yview_scroll(d * 2, "units")
            return "break"

        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            txt.bind(seq, _wheel)
        app._cartes_boxes[url] = txt
        _fill_details(app, g, txt, it)
        _ensure_body(app, g, it)
    row = tk.Frame(inner, bg=bg)
    row.pack(fill="x")

    def B(text, cmd, tip, hi=False, side="left"):
        b = tk.Button(row, text=text, command=cmd, bg=C["gold"] if hi else C["card2"],
                      fg="#1a1408" if hi else C["fg"], relief="flat",
                      font=("Segoe UI", 7, "bold") if hi else ("Segoe UI", 7), padx=7, pady=2, cursor="hand2",
                      activebackground=C["gold"], activeforeground="#1a1408")
        b.pack(side=side, padx=(0, 4))
        _Tip(b, tip, C)
        return b

    B("▾ Replier" if is_open else "▸ Détails", lambda: toggle(app, g, url),
      "Afficher / cacher les détails ici même (ou clic sur la carte)", hi=not is_open)
    B("Lire", lambda: app.reader(url, it["title"]), "Ouvrir dans l'onglet Lecteur (texte complet)", hi=is_open)
    B("Site", lambda: app.open_browser(url), "Ouvrir le site dans le navigateur")
    if is_open:
        B("📋", lambda: _copy(app, g, it), "Copier titre + lien + texte")
        B("⤡" if url in st["big"] else "⤢", lambda: toggle_big(app, g, url),
          "Zone de détails plus petite" if url in st["big"] else "Zone de détails plus grande")

    def _click(e):
        toggle(app, g, url)

    def _on(e):
        card.configure(highlightbackground=C["cyan"])

    def _off(e):
        card.configure(highlightbackground=C["gold"] if (url == app.active_url or url in st["open"]) else C["line"])

    for w in [card, inner, head, title, chev] + ([snip_lbl] if snip_lbl else []) + list(head.winfo_children()):
        w.bind("<Button-1>", _click)
        w.bind("<Enter>", _on, add="+")
        w.bind("<Leave>", _off, add="+")


def toggle(app, g, url):
    st = _st(app)
    if url in st["open"]:
        st["open"].discard(url)
    else:
        st["open"].add(url)
    y = app.src_canvas.yview()[0]
    draw_sources(app, g)
    app.after(40, lambda: app.src_canvas.yview_moveto(y))


def toggle_big(app, g, url):
    st = _st(app)
    if url in st["big"]:
        st["big"].discard(url)
    else:
        st["big"].add(url)
    y = app.src_canvas.yview()[0]
    draw_sources(app, g)
    app.after(40, lambda: app.src_canvas.yview_moveto(y))
