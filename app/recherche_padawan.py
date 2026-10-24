# -*- coding: utf-8 -*-
"""
Recherche Padawan 1.0 - Projet Padawan
Une seule barre de recherche pour toute la suite : Grimoire (base SQLite ouverte en LECTURE SEULE),
archives de l'Archiveur (archive_index.json + textes), Arsenal (arsenal.json) et des dossiers de fichiers
choisis (noms de fichiers). Resultats unifies ; double-clic = ouvrir au bon endroit.
Bonus : « Demander a Padawan » resume les resultats avec Ollama local s'il est present (sinon, rien ne casse).
Reglages : %APPDATA%\\Padawan\\recherche.json. Raccourci clavier : Ctrl+Alt+R (raccourci Windows cree par le setup).
Options : --q "mots" (affiche les resultats en console), --selftest, --sources (liste les sources)
"""
import os, sys, json, time, sqlite3, threading, queue, urllib.request, re
import padawan_commun as pc

APP = "Recherche Padawan"
VERSION = "1.0"
SETTINGS = "recherche.json"
MAX_PER_SOURCE = 60
FILE_SCAN_LIMIT = 40000
FILE_SCAN_SECONDS = 6.0


def default_settings():
    home = os.path.expanduser("~")
    folders = [os.path.join(home, "Documents"), os.path.join(home, "Desktop")]
    return {"dossiers": [f for f in folders if os.path.isdir(f)], "sources": {"grimoire": True, "archiveur": True,
            "arsenal": True, "fichiers": True, "journal": True}, "ollama_url": "http://127.0.0.1:11434", "modele": ""}


def terms_of(q):
    return [t for t in pc.norm(q).split() if t]


def match_all(terms, hay):
    return all(t in hay for t in terms)


def snippet(text, terms, width=160):
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    if not t:
        return ""
    n = pc.norm(t)
    pos = min([n.find(x) for x in terms if n.find(x) >= 0] or [0])
    a = max(0, pos - width // 3)
    return ("\u2026" if a else "") + t[a:a + width] + ("\u2026" if a + width < len(t) else "")


def score(terms, title, other):
    nt = pc.norm(title)
    s = sum(3 for t in terms if t in nt) + sum(1 for t in terms if t in other)
    return s


# ------------------------------------------------------------------ sources
def search_grimoire(q):
    terms = terms_of(q)
    db = pc.grimoire_db()
    out = []
    if not terms or not os.path.isfile(db):
        return out
    uri = "file:" + db.replace("\\", "/") + "?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=3)
    try:
        subj = {r[0]: r[1] for r in con.execute("SELECT id, name FROM subjects WHERE deleted IS NULL OR deleted=''")}
        rows = con.execute("SELECT id, subject_id, type, title, body_text, url, file, tags, source, author, "
                           "substr(extracted,1,20000) FROM items WHERE deleted IS NULL OR deleted=''")
        for (iid, sid, typ, title, body, url, fil, tags, src, auth, ext) in rows:
            hay = pc.norm(" ".join(str(x or "") for x in (title, body, url, fil, tags, src, auth, ext, subj.get(sid, ""))))
            if match_all(terms, hay):
                out.append({"source": "Grimoire", "icon": "\U0001f4d6", "title": title or "(sans titre)",
                            "detail": f"{subj.get(sid, '?')} \u00b7 {typ}",
                            "snippet": snippet(body or ext or url, terms), "score": score(terms, title, hay),
                            "url": url or "", "path": fil or "", "id": iid})
    finally:
        con.close()
    out.sort(key=lambda r: -r["score"])
    return out[:MAX_PER_SOURCE]


def search_archiveur(q):
    terms = terms_of(q)
    root = pc.archiveur_root()
    idx = pc.read_json(os.path.join(root, "archive_index.json"), []) or []
    if isinstance(idx, dict):
        idx = idx.get("items") or list(idx.values())
    out = []
    for e in idx:
        if not isinstance(e, dict):
            continue
        tags = e.get("tags") or []
        hay = pc.norm(" ".join(str(x or "") for x in (e.get("title"), e.get("uploader"), e.get("text_snippet"),
                                                         e.get("notes"), e.get("url"), e.get("platform"),
                                                         " ".join(tags) if isinstance(tags, list) else tags)))
        folder = os.path.join(root, e.get("folder") or "")
        if not match_all(terms, hay):
            # texte complet (post.txt / transcription) seulement si le dossier est la
            extra = ""
            for fn in ("post.txt", "transcript.txt", "transcription.txt"):
                p = os.path.join(folder, fn)
                if os.path.isfile(p):
                    try:
                        with open(p, encoding="utf-8", errors="replace") as f:
                            extra += " " + f.read(200000)
                    except OSError:
                        pass
            hay2 = hay + " " + pc.norm(extra)
            if not extra or not match_all(terms, hay2):
                continue
            hay = hay2
        out.append({"source": "Archiveur", "icon": "\U0001f3ac", "title": e.get("title") or e.get("folder") or "?",
                    "detail": f"{e.get('platform', '')} \u00b7 {e.get('uploader', '')} \u00b7 {str(e.get('archived_at', ''))[:10]}",
                    "snippet": snippet(e.get("text_snippet") or e.get("notes"), terms),
                    "score": score(terms, e.get("title"), hay), "url": e.get("url") or "", "path": folder})
    out.sort(key=lambda r: -r["score"])
    return out[:MAX_PER_SOURCE]


def search_arsenal(q):
    terms = terms_of(q)
    d = pc.read_json(pc.arsenal_json(), {}) or {}
    cats = {c.get("id"): c.get("name", "") for c in d.get("categories", []) if isinstance(c, dict)}
    out = []
    for e in d.get("entries", []):
        if not isinstance(e, dict) or e.get("hidden"):
            continue
        tags = e.get("tags") or []
        hay = pc.norm(" ".join(str(x or "") for x in (e.get("name"), e.get("desc"), e.get("group"), cats.get(e.get("category")),
                                                         " ".join(tags) if isinstance(tags, list) else tags, e.get("target"))))
        if match_all(terms, hay):
            out.append({"source": "Arsenal", "icon": "\U0001f9f0", "title": e.get("name") or "?",
                        "detail": f"{cats.get(e.get('category'), '')} \u00b7 {e.get('group', '')}",
                        "snippet": snippet(e.get("desc"), terms), "score": score(terms, e.get("name"), hay) + (1 if e.get("fav") else 0),
                        "url": e.get("target") if e.get("type") == "url" else "", "path": ""})
    out.sort(key=lambda r: -r["score"])
    return out[:MAX_PER_SOURCE]


def search_journal(q):
    """Journal de bord (lecture seule) : jamais les entrees scellees ni supprimees."""
    terms = terms_of(q)
    db = os.path.join(pc.journal_dir() if hasattr(pc, "journal_dir") else "", "journal.db")
    out = []
    if not terms or not os.path.isfile(db):
        return out
    con = sqlite3.connect("file:" + db.replace("\\", "/") + "?mode=ro", uri=True, timeout=3)
    try:
        emb = {}
        for eid, name, title, url, tr in con.execute("SELECT entry_id, name, title, url, transcript FROM embeds"):
            emb[eid] = emb.get(eid, "") + " " + " ".join(str(x or "") for x in (name, title, url, tr))
        for (eid, created, title, body, tags, lieu, mood) in con.execute(
                "SELECT id, created, title, body, tags, lieu, mood FROM entries WHERE sealed=0 AND deleted=0"):
            clean = re.sub("\u27e6e:[0-9a-f]+\u27e7", " ", str(body or ""))
            clean = re.sub(r"\\(.)", r"\1", re.sub(r"\*\*|(?<!\\)_|\]\([^)]*\)|\[", "", clean))
            hay = pc.norm(" ".join(str(x or "") for x in (title, clean, tags, lieu, emb.get(eid, ""))))
            if match_all(terms, hay):
                out.append({"source": "Journal", "icon": "\U0001f4d3", "title": title or clean.strip()[:60] or "(entr\u00e9e)",
                            "detail": f"{str(created)[:10]} \u00b7 {mood or ''} {lieu or ''}".strip(),
                            "snippet": snippet(clean, terms), "score": score(terms, title, hay), "url": "", "path": "",
                            "id": eid})
    finally:
        con.close()
    out.sort(key=lambda r: -r["score"])
    return out[:MAX_PER_SOURCE]


SKIP_DIRS = {"node_modules", "__pycache__", ".git", "$recycle.bin", "appdata", "_sauvegardes", "perso"}


def search_files(q, folders):
    terms = terms_of(q)
    out = []
    if not terms:
        return out
    t0, n = time.time(), 0
    for base in folders:
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d.lower() not in SKIP_DIRS and not d.startswith(".")]
            for fn in filenames:
                n += 1
                if match_all(terms, pc.norm(fn)):
                    p = os.path.join(dirpath, fn)
                    out.append({"source": "Fichiers", "icon": "\U0001f4c4", "title": fn, "detail": dirpath,
                                "snippet": "", "score": score(terms, fn, pc.norm(fn)), "url": "", "path": p})
                    if len(out) >= MAX_PER_SOURCE:
                        return out
            if n > FILE_SCAN_LIMIT or time.time() - t0 > FILE_SCAN_SECONDS:
                return out
    return out


def search_all(q, st=None, log=None):
    st = st or pc.load_settings(SETTINGS, default_settings())
    src = st.get("sources", {})
    res, errs = [], []
    jobs = [("grimoire", lambda: search_grimoire(q)), ("archiveur", lambda: search_archiveur(q)),
            ("arsenal", lambda: search_arsenal(q)), ("journal", lambda: search_journal(q)), ("fichiers", lambda: search_files(q, st.get("dossiers", [])))]
    for name, fn in jobs:
        if not src.get(name, True):
            continue
        try:
            res.extend(fn())
        except Exception as ex:
            errs.append(f"{name} : {ex}")
    return res, errs


# ------------------------------------------------------------------ Ollama (facultatif)
def ollama_model(st):
    if st.get("modele"):
        return st["modele"]
    cfg = pc.read_json(os.path.join(pc.HERE, "config.json"), {}) or {}
    return cfg.get("model") or ""


def ollama_available(st):
    try:
        with urllib.request.urlopen(st.get("ollama_url", "http://127.0.0.1:11434") + "/api/tags", timeout=2) as r:
            d = json.loads(r.read().decode("utf-8", "replace"))
        names = [m.get("name") for m in d.get("models", [])]
        return names
    except Exception:
        return None


def ask_ollama(st, question, results):
    names = ollama_available(st)
    if names is None:
        return "Ollama n'est pas lanc\u00e9 sur ce PC : le r\u00e9sum\u00e9 IA est d\u00e9sactiv\u00e9 (la recherche, elle, marche toujours)."
    model = ollama_model(st)
    if not model or (names and model not in names):
        model = names[0] if names else ""
    if not model:
        return "Aucun mod\u00e8le Ollama install\u00e9."
    ctx = "\n".join(f"- [{r['source']}] {r['title']} ({r['detail']}) : {r['snippet']}" for r in results[:25])
    prompt = ("Tu es Padawan, l'assistant local de l'utilisateur. R\u00e9ponds en fran\u00e7ais, court et clair. "
              "Utilise SEULEMENT les r\u00e9sultats ci-dessous (ses propres donn\u00e9es) ; dis-le si \u00e7a ne suffit pas, "
              "et indique dans quel outil regarder.\n\nQuestion : " + question + "\n\nR\u00e9sultats :\n" + ctx)
    body = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode("utf-8")
    req = urllib.request.Request(st.get("ollama_url", "http://127.0.0.1:11434") + "/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=240) as r:
        d = json.loads(r.read().decode("utf-8", "replace"))
    return f"({model})\n" + (d.get("response") or "").strip()


# ------------------------------------------------------------------ ouvrir
def open_result(r, parent=None):
    s = r["source"]
    if s == "Grimoire":
        if r.get("path") and os.path.isfile(r["path"]):
            pc.open_path(r["path"]); return
        pc.launch("grimoire", "--montrer") or pc.launch("grimoire")
        return
    if s == "Archiveur":
        if r.get("path") and os.path.isdir(r["path"]):
            html = os.path.join(r["path"], "index.html")
            pc.open_path(html if os.path.isfile(html) else r["path"]); return
        if r.get("url"):
            pc.open_path(r["url"]); return
    if s == "Arsenal":
        pc.launch("arsenal"); return
    if s == "Journal":
        pc.launch("journal", "--ouvrir", r.get("id", "")); return
    if s == "Fichiers" and r.get("path"):
        pc.open_path(r["path"]); return
    if r.get("url"):
        pc.open_path(r["url"])


# ------------------------------------------------------------------ interface
def run_gui(initial=""):
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog
    C = pc.C
    st = pc.load_settings(SETTINGS, default_settings())
    root = tk.Tk()
    root.title(APP)
    root.configure(bg=C["BG"])
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    w, h = min(1100, sw - 60), min(720, sh - 90)
    root.geometry(f"{w}x{h}+{(sw - w) // 2}+{max(0, (sh - h) // 3)}")
    try:
        root.iconbitmap(os.path.join(pc.HERE, "padawan_tray.ico"))
    except Exception:
        pass
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass
    style.configure("Treeview", background=C["ENTRY"], fieldbackground=C["ENTRY"], foreground=C["TEXT"], rowheight=26,
                    font=("Segoe UI", 10))
    style.configure("Treeview.Heading", background=C["PANEL"], foreground=C["ACC"], font=("Segoe UI", 10, "bold"))
    style.map("Treeview", background=[("selected", C["BTN"])])

    top = tk.Frame(root, bg=C["PANEL"]); top.pack(fill="x")
    tk.Label(top, text="\U0001f50e", bg=C["PANEL"], fg=C["ACC"], font=("Segoe UI", 18)).pack(side="left", padx=(14, 4), pady=10)
    qv = tk.StringVar(value=initial)
    ent = tk.Entry(top, textvariable=qv, font=("Segoe UI", 14), bg=C["ENTRY"], fg=C["TEXT"], insertbackground=C["TEXT"],
                   relief="flat")
    ent.pack(side="left", fill="x", expand=True, padx=4, pady=10, ipady=4)

    def mkbtn(parent, text, cmd, acc=False):
        return tk.Button(parent, text=text, command=cmd, bg=C["ACC"] if acc else C["BTN"], fg="#06121f" if acc else C["TEXT"],
                         activebackground=C["BTNH"], activeforeground=C["TEXT"], relief="flat",
                         font=("Segoe UI", 10, "bold"), padx=10, pady=4, cursor="hand2")

    srcbar = tk.Frame(root, bg=C["BG"]); srcbar.pack(fill="x", padx=10, pady=(6, 0))
    svars = {}
    for key, lab in (("grimoire", "\U0001f4d6 Grimoire"), ("archiveur", "\U0001f3ac Archiveur"),
                     ("arsenal", "\U0001f9f0 Arsenal"), ("journal", "\U0001f4d3 Journal"), ("fichiers", "\U0001f4c4 Fichiers")):
        v = tk.BooleanVar(value=st["sources"].get(key, True)); svars[key] = v
        tk.Checkbutton(srcbar, text=lab, variable=v, bg=C["BG"], fg=C["TEXT"], selectcolor=C["ENTRY"],
                       activebackground=C["BG"], activeforeground=C["TEXT"], font=("Segoe UI", 10)).pack(side="left", padx=4)
    status = tk.StringVar(value="Tape des mots puis Entr\u00e9e. Double-clic sur un r\u00e9sultat pour l'ouvrir.")

    mid = tk.PanedWindow(root, orient="vertical", bg=C["BG"], sashwidth=6); mid.pack(fill="both", expand=True, padx=10, pady=6)
    tf = tk.Frame(mid, bg=C["BG"])
    tree = ttk.Treeview(tf, columns=("src", "title", "detail"), show="headings")
    for c, lab, wd in (("src", "Outil", 120), ("title", "R\u00e9sultat", 480), ("detail", "O\u00f9", 380)):
        tree.heading(c, text=lab); tree.column(c, width=wd, anchor="w")
    ysb = ttk.Scrollbar(tf, orient="vertical", command=tree.yview); tree.configure(yscrollcommand=ysb.set)
    tree.pack(side="left", fill="both", expand=True); ysb.pack(side="right", fill="y")
    mid.add(tf, stretch="always")
    info = tk.Text(mid, height=7, bg=C["CARD"], fg=C["TEXT"], wrap="word", relief="flat", font=("Segoe UI", 10),
                   padx=10, pady=8)
    mid.add(info, stretch="never")

    results = []
    q_out = queue.Queue()

    def show_info(text):
        info.configure(state="normal"); info.delete("1.0", "end"); info.insert("1.0", text); info.configure(state="disabled")

    def do_search(*_):
        q = qv.get().strip()
        if not q:
            return
        for k, v in svars.items():
            st["sources"][k] = bool(v.get())
        try:
            pc.save_settings(SETTINGS, st)
        except Exception:
            pass
        status.set("Recherche\u2026")
        t0 = time.time()
        threading.Thread(target=lambda: q_out.put(("res", search_all(q, st), time.time() - t0)), daemon=True).start()

    def poll():
        try:
            while True:
                kind, *data = q_out.get_nowait()
                if kind == "res":
                    (res, errs), dt = data
                    results.clear(); results.extend(sorted(res, key=lambda r: (-r["score"])))
                    tree.delete(*tree.get_children())
                    for i, r in enumerate(results):
                        tree.insert("", "end", iid=str(i), values=(f"{r['icon']} {r['source']}", r["title"], r["detail"]))
                    counts = {}
                    for r in results:
                        counts[r["source"]] = counts.get(r["source"], 0) + 1
                    txt = " \u00b7 ".join(f"{k} {v}" for k, v in counts.items()) or "aucun r\u00e9sultat"
                    status.set(f"{len(results)} r\u00e9sultat(s) en {dt:.1f} s \u2014 {txt}" + (f"  (souci : {'; '.join(errs)})" if errs else ""))
                    show_info("")
                elif kind == "ia":
                    show_info(data[0]); status.set("R\u00e9sum\u00e9 de Padawan pr\u00eat.")
        except queue.Empty:
            pass
        root.after(150, poll)

    def sel():
        s = tree.selection()
        return results[int(s[0])] if s else None

    def on_select(_=None):
        r = sel()
        if r:
            show_info(f"{r['icon']} {r['title']}\n{r['detail']}\n\n{r['snippet']}\n\n{r.get('url') or r.get('path') or ''}")

    def on_open(_=None):
        r = sel()
        if r:
            open_result(r, root)

    def on_reveal():
        r = sel()
        if r and r.get("path"):
            pc.reveal(r["path"])
        elif r and r.get("url"):
            pc.open_path(r["url"])

    def on_ask():
        if not results:
            messagebox.showinfo(APP, "Fais d'abord une recherche : Padawan r\u00e9sume ce qui a \u00e9t\u00e9 trouv\u00e9.", parent=root)
            return
        status.set("Padawan r\u00e9fl\u00e9chit (Ollama local)\u2026")
        show_info("\U0001f916 Padawan lit les r\u00e9sultats\u2026")
        q = qv.get().strip(); snap = list(results)

        def work():
            try:
                q_out.put(("ia", ask_ollama(st, q, snap)))
            except Exception as ex:
                q_out.put(("ia", f"R\u00e9sum\u00e9 impossible : {ex}"))
        threading.Thread(target=work, daemon=True).start()

    def on_folders():
        dlg = tk.Toplevel(root); dlg.title("Dossiers cherch\u00e9s"); dlg.configure(bg=C["BG"]); dlg.transient(root)
        lb = tk.Listbox(dlg, width=80, height=10, bg=C["ENTRY"], fg=C["TEXT"], relief="flat")
        lb.pack(padx=10, pady=10, fill="both", expand=True)
        for f in st.get("dossiers", []):
            lb.insert("end", f)
        row = tk.Frame(dlg, bg=C["BG"]); row.pack(fill="x", padx=10, pady=(0, 10))

        def add():
            d = filedialog.askdirectory(parent=dlg)
            if d:
                lb.insert("end", os.path.normpath(d))

        def rem():
            for i in reversed(lb.curselection()):
                lb.delete(i)

        def ok():
            st["dossiers"] = list(lb.get(0, "end")); pc.save_settings(SETTINGS, st); dlg.destroy()
        mkbtn(row, "Ajouter\u2026", add).pack(side="left", padx=3)
        mkbtn(row, "Retirer", rem).pack(side="left", padx=3)
        mkbtn(row, "OK", ok, True).pack(side="right", padx=3)

    mkbtn(top, "Chercher", do_search, True).pack(side="left", padx=4)
    mkbtn(top, "\U0001f916 Demander \u00e0 Padawan", on_ask).pack(side="left", padx=(4, 14))
    bot = tk.Frame(root, bg=C["PANEL"]); bot.pack(fill="x")
    tk.Label(bot, textvariable=status, bg=C["PANEL"], fg=C["DIM"], font=("Segoe UI", 9)).pack(side="left", padx=12, pady=6)
    mkbtn(bot, "Dossiers cherch\u00e9s\u2026", on_folders).pack(side="right", padx=6, pady=4)
    mkbtn(bot, "Montrer dans l'Explorateur", on_reveal).pack(side="right", padx=6, pady=4)
    mkbtn(bot, "Ouvrir", on_open, True).pack(side="right", padx=6, pady=4)

    ent.bind("<Return>", do_search)
    tree.bind("<<TreeviewSelect>>", on_select)
    tree.bind("<Double-1>", on_open)
    tree.bind("<Return>", on_open)
    root.bind("<Escape>", lambda e: root.destroy())
    root.bind("<F1>", lambda e: messagebox.showinfo(APP, __doc__.strip(), parent=root))
    ent.focus_set()
    root.after(150, poll)
    if initial:
        root.after(200, do_search)
    try:  # premier plan quand lance par le raccourci clavier
        root.lift(); root.attributes("-topmost", True); root.after(400, lambda: root.attributes("-topmost", False))
        root.focus_force()
    except Exception:
        pass
    if "--selftest" in sys.argv:
        root.after(2500, root.destroy)
    root.mainloop()


def main():
    a = sys.argv[1:]
    if "--sources" in a:
        print("Grimoire :", pc.grimoire_db()); print("Archiveur :", pc.archiveur_root()); print("Arsenal :", pc.arsenal_json()); print("Journal :", pc.journal_dir())
        print("Dossiers :", pc.load_settings(SETTINGS, default_settings()).get("dossiers"))
        return 0
    if "--q" in a:
        q = a[a.index("--q") + 1] if len(a) > a.index("--q") + 1 else ""
        t0 = time.time(); res, errs = search_all(q)
        for r in sorted(res, key=lambda r: -r["score"])[:40]:
            print(f"[{r['source']}] {r['title']} | {r['detail']}")
        print(f"-- {len(res)} resultat(s) en {time.time() - t0:.2f}s ; erreurs : {errs}")
        return 0 if not errs else 1
    run_gui(a[a.index("--chercher") + 1] if "--chercher" in a and len(a) > a.index("--chercher") + 1 else "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
