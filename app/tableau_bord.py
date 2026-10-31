# -*- coding: utf-8 -*-
"""
Tableau de bord 1.2 - Projet Padawan
Vue d'ensemble de la suite : programmes (en marche ou non), serveurs du PC (détectés par Chantier, lecture seule),
liens rapides, vérification des mises à jour (ne plante jamais hors ligne) et « Rapport de problème »
(zip des journaux, secrets masqués). Raccourcis : F1 aide · F5 rafraîchir · F10 quitter.
Options : --selftest
"""
import os, sys, re, json, time, zipfile, threading, queue, subprocess, webbrowser, traceback
import urllib.request

APP = "Tableau de bord"
VERSION = "1.2"
SUITE_VERSION = "2026.10.31"
HERE = os.path.dirname(os.path.abspath(__file__))
IS_WIN = os.name == "nt"
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0) if IS_WIN else 0
UPDATE_URL = "https://marcsevigny.ca/padawan_version.json"   # {"suite": "2026.10.30", "notes": "..."} (facultatif)

PROGS = [  # (fichier, nom, description)
    ("journal_bord.py", "Journal de bord", "Le journal du capitaine (Ctrl+Alt+J)"),
    ("archiveur5.py", "Archiveur", "Archives et copies"),
    ("grimoire1.py", "Grimoire", "Base de connaissances"),
    ("messager2.py", "Messager", "Messages"),
    ("arsenal1.py", "Arsenal", "Boîte à outils"),
    ("padawan39.py", "Padawan", "Assistant IA local (Ollama) + icône du tray"),
    ("recherche_padawan.py", "Recherche Padawan", "Une recherche pour toute la suite (Ctrl+Alt+R)"),
    ("retro1.py", "Rétro", "C64 · DOS · Win98, jeux et atelier BASIC"),
    ("facteur1.py", "Facteur", "Courrier / boîte"),
    ("coffre_padawan.py", "Coffre Padawan", "Sauvegarde / restauration de toutes tes donn\u00e9es"),
    ("gestionnaire_fichiers5.py", "Gestionnaire de fichiers", "Fichiers"),
    ("premiers_pas.py", "Premiers pas", "Guide de d\u00e9marrage en 5 minutes"),
    ("chantier1.py", "Chantier", "Serveurs Web / SQL / FTP / MQTT à la demande"),
]

def file_version(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            head = f.read(6000)
        m = re.search(r'(?<![A-Z_])VERSION\s*=\s*["\']([^"\']+)', head)
        if m:
            return m.group(1)
        m = re.search(r'APP_FILE_VER\s*=\s*["\']?([\w.]+)', head)
        return ("build " + m.group(1)) if m else "-"
    except Exception:
        return "-"

def running_scripts():
    """Noms de fichiers .py lancés par pythonw/python (lecture seule)."""
    if not IS_WIN:
        return set()
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                            "Get-CimInstance Win32_Process -Filter \"name like 'python%'\" | ForEach-Object { $_.CommandLine }"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=NOWIN, timeout=20)
        return {m.lower() for m in re.findall(r'([\w\-]+\.py)', r.stdout or "")}
    except Exception:
        return set()

def check_update():
    try:
        req = urllib.request.Request(UPDATE_URL, headers={"User-Agent": "Padawan-Tableau/1.0"})
        with urllib.request.urlopen(req, timeout=6) as r:
            d = json.loads(r.read().decode("utf-8", "replace"))
        pub = str(d.get("suite") or "")
        if not pub:
            return "Aucune version publiée en ligne pour l'instant."
        if pub > SUITE_VERSION:
            return f"⬆ Nouvelle version {pub} disponible (tu as {SUITE_VERSION}). {d.get('notes', '')}".strip()
        return f"✔ À jour (version {SUITE_VERSION})."
    except Exception:
        return f"Vérification impossible (hors ligne ou aucune version publiée). Version installée : {SUITE_VERSION}."

SECRET_RX = re.compile(r'(?i)(pass(word|wd)?|mot[ _-]?de[ _-]?passe|pwd|secret|token|api[_-]?key|cl[eé])(["\']?\s*[:=]\s*)(["\']?)[^\s"\',;]+')

def log_files():
    roots = [HERE, r"C:\web_private\chantier\logs", os.path.join(os.environ.get("LOCALAPPDATA", ""), "Padawan")]
    out = []
    for r in roots:
        if not r or not os.path.isdir(r):
            continue
        depth0 = r.count(os.sep)
        for dp, dn, fn in os.walk(r):
            if dp.count(os.sep) - depth0 >= 2:
                dn[:] = []
            for f in fn:
                low = f.lower()
                if low.endswith(".log") and "secret" not in low:
                    out.append(os.path.join(dp, f))
    return out

def make_report():
    dest_dir = os.path.join(os.path.expanduser("~"), "Documents", "Padawan", "rapports")
    os.makedirs(dest_dir, exist_ok=True)
    zp = os.path.join(dest_dir, "rapport_padawan_" + time.strftime("%Y%m%d_%H%M%S") + ".zip")
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        info = [f"Rapport de problème - suite Padawan {SUITE_VERSION}", time.strftime("%Y-%m-%d %H:%M:%S"),
                f"Python {sys.version.split()[0]} - {sys.platform}", ""]
        for f, n, _ in PROGS:
            p = os.path.join(HERE, f)
            info.append(f"{n:<26} {file_version(p) if os.path.isfile(p) else 'absent'}")
        z.writestr("infos.txt", "\n".join(info))
        for p in log_files():
            try:
                with open(p, "rb") as fh:
                    fh.seek(max(0, os.path.getsize(p) - 300_000))
                    txt = fh.read().decode("utf-8", "replace")
                txt = SECRET_RX.sub(lambda m: m.group(1) + m.group(3) + "***masqué***", txt)
                z.writestr("journaux/" + os.path.basename(os.path.dirname(p)) + "_" + os.path.basename(p), txt)
            except Exception:
                pass
    return zp

def servers():
    try:
        sys.path.insert(0, HERE)
        import chantier1
        ex = chantier1.detect_existing()
        return ex, chantier1.existing_summary(ex)
    except Exception as e:
        return {}, f"Détection des serveurs impossible : {e}"

def launch(script):
    p = os.path.join(HERE, script)
    exe = sys.executable
    if exe.lower().endswith("python.exe"):
        w = exe[:-10] + "pythonw.exe"
        exe = w if os.path.isfile(w) else exe
    subprocess.Popen([exe, p], cwd=HERE, creationflags=NOWIN)

def run_gui():
    import tkinter as tk
    from tkinter import messagebox
    BG, PANEL, FG, DIM, ACC, OK, BAD = "#0f172a", "#1e293b", "#e2e8f0", "#94a3b8", "#facc15", "#4ade80", "#f87171"
    root = tk.Tk(); root.title(f"{APP} {VERSION} - suite Padawan {SUITE_VERSION}"); root.configure(bg=BG)
    root.geometry("900x640"); root.minsize(760, 380)
    # Ouvre agrandi (maximise) comme le Gestionnaire de fichiers
    try:
        if os.name == "nt":
            root.state("zoomed")
    except Exception:
        pass
    try:
        root.iconbitmap(os.path.join(HERE, "padawan_tray.ico"))
    except Exception:
        pass
    UIQ = queue.Queue()
    tk.Label(root, text="🧭  TABLEAU DE BORD - suite Padawan", bg=BG, fg=ACC, font=("Segoe UI Black", 18)).pack(anchor="w", padx=16, pady=(12, 0))
    srv_var = tk.StringVar(value="Sur ce PC :  détection…")
    tk.Label(root, textvariable=srv_var, bg="#0b1220", fg="#a7f3d0", font=("Segoe UI", 10, "bold"), anchor="w", padx=12, pady=5).pack(fill="x", pady=(8, 4))
    upd_var = tk.StringVar(value="Mises à jour : vérification…")
    tk.Label(root, textvariable=upd_var, bg=BG, fg=DIM, font=("Segoe UI", 9), anchor="w").pack(fill="x", padx=16)
    # Liste defilante (barre verticale + molette) : toutes les lignes restent accessibles meme en petite fenetre
    wrap = tk.Frame(root, bg=BG); wrap.pack(fill="both", expand=True, padx=12, pady=8)
    cv = tk.Canvas(wrap, bg=BG, highlightthickness=0, height=200)
    sb = tk.Scrollbar(wrap, orient="vertical", command=cv.yview)
    cv.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y"); cv.pack(side="left", fill="both", expand=True)
    grid = tk.Frame(cv, bg=BG)
    gwin = cv.create_window((0, 0), window=grid, anchor="nw")
    grid.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
    cv.bind("<Configure>", lambda e: cv.itemconfigure(gwin, width=e.width))
    def _wheel(e):
        if cv.yview() == (0.0, 1.0):
            return
        d = -1 if (getattr(e, "num", 0) == 4 or getattr(e, "delta", 0) > 0) else 1
        cv.yview_scroll(d * (1 if abs(getattr(e, "delta", 120)) < 120 else abs(e.delta) // 120), "units")
    root.bind_all("<MouseWheel>", _wheel); root.bind_all("<Button-4>", _wheel); root.bind_all("<Button-5>", _wheel)
    _r = [0]
    rows = {}
    for i, (f, n, d) in enumerate(PROGS):
        if f == "chantier1.py":
            tk.Label(grid, text="\u2699  Serveurs et installation", bg=BG, fg=ACC, font=("Segoe UI", 10, "bold"), anchor="w").grid(row=_r[0], column=0, sticky="ew", pady=(10, 2)); _r[0] += 1
        fr = tk.Frame(grid, bg=PANEL, padx=10, pady=6); fr.grid(row=_r[0], column=0, sticky="ew", pady=2); _r[0] += 1
        grid.grid_columnconfigure(0, weight=1)
        led = tk.Label(fr, text="●", bg=PANEL, fg=DIM, font=("Segoe UI", 14)); led.pack(side="left")
        tk.Label(fr, text=n, bg=PANEL, fg=FG, font=("Segoe UI", 11, "bold"), width=22, anchor="w").pack(side="left", padx=6)
        ver = tk.Label(fr, text="", bg=PANEL, fg=DIM, font=("Consolas", 9), width=12, anchor="w"); ver.pack(side="left")
        tk.Label(fr, text=d, bg=PANEL, fg=DIM, font=("Segoe UI", 9), anchor="w").pack(side="left", fill="x", expand=True)
        exists = os.path.isfile(os.path.join(HERE, f))
        tk.Button(fr, text="Ouvrir" if exists else "absent", state="normal" if exists else "disabled", bg="#334155", fg=FG, relief="flat",
                  padx=10, command=lambda s=f: (launch(s), root.after(2500, refresh))).pack(side="right")
        rows[f] = (led, ver)
    bar = tk.Frame(root, bg=BG); bar.pack(fill="x", padx=12, pady=(0, 6))
    def btn(t, c):
        tk.Button(bar, text=t, command=c, bg="#334155", fg=FG, relief="flat", padx=10, pady=4).pack(side="left", padx=3)
    btn("🌐 http://localhost", lambda: webbrowser.open("http://localhost/"))
    btn("📂 Dossier de la suite", lambda: os.startfile(HERE) if IS_WIN else None)
    btn("📜 Journaux", lambda: os.startfile(r"C:\web_private\chantier\logs") if os.path.isdir(r"C:\web_private\chantier\logs") else os.startfile(HERE))
    def report():
        def work():
            try:
                zp = make_report()
                UIQ.put(lambda: (messagebox.showinfo(APP, f"Rapport créé (mots de passe masqués) :\n{zp}\n\nEnvoie ce fichier à qui t'aide.", parent=root),
                                 os.startfile(os.path.dirname(zp)) if IS_WIN else None))
            except Exception as e:
                UIQ.put(lambda: messagebox.showerror(APP, f"Rapport impossible : {e}", parent=root))
        threading.Thread(target=work, daemon=True).start()
    btn("🧰 Rapport de problème", report)
    btn("⬆ Vérifier les mises à jour", lambda: threading.Thread(target=lambda: UIQ.put(lambda v=check_update(): upd_var.set("Mises à jour : " + v)), daemon=True).start())
    fk = tk.Frame(root, bg="#000"); fk.pack(fill="x", side="bottom")
    def about():
        messagebox.showinfo(APP, f"Suite Padawan {SUITE_VERSION}\n{APP} {VERSION}\n\n" +
                            "\n".join(f"{n:<26} {file_version(os.path.join(HERE, f))}" for f, n, _ in PROGS) +
                            "\n\nF1 Aide · F5 Rafraîchir · F10 Quitter\nProjet Padawan - Marc Sévigny", parent=root)
    for k, t, c in (("F1", "Aide / À propos", about), ("F5", "Rafraîchir", lambda: refresh(True)), ("F10", "Quitter", root.destroy)):
        cell = tk.Frame(fk, bg="#000"); cell.pack(side="left", expand=True, fill="x")
        a = tk.Label(cell, text=k, bg="#000", fg="#fff", font=("Consolas", 9, "bold")); a.pack(side="left")
        b = tk.Label(cell, text=t, bg="#00aaaa", fg="#000", font=("Consolas", 9), anchor="w"); b.pack(side="left", fill="x", expand=True)
        for w in (a, b, cell):
            w.bind("<Button-1>", lambda e, c=c: c())
        root.bind(f"<{k}>", lambda e, c=c: (c(), "break")[1])
    root.bind("<Escape>", lambda e: root.destroy())
    busy = [False]
    def refresh(full=False):
        if busy[0]:
            return
        busy[0] = True
        def work():
            try:
                run = running_scripts()
                vers = {f: file_version(os.path.join(HERE, f)) for f, _, _ in PROGS}
                UIQ.put(lambda: [(rows[f][0].configure(fg=OK if f.lower() in run else DIM), rows[f][1].configure(text=(vers[f] if vers[f].startswith("build") else "v" + vers[f]) if vers[f] != "-" else ""))
                                 for f in rows])
                if full or srv_var.get().endswith("détection…"):
                    _, summ = servers()
                    UIQ.put(lambda: srv_var.set(summ))
            finally:
                busy[0] = False
        threading.Thread(target=work, daemon=True).start()
    def pump():
        try:
            while True:
                UIQ.get_nowait()()
        except queue.Empty:
            pass
        except Exception:
            pass
        root.after(150, pump)
    def auto():
        refresh(); root.after(8000, auto)
    pump(); auto()
    threading.Thread(target=lambda: UIQ.put(lambda v=check_update(): upd_var.set("Mises à jour : " + v)), daemon=True).start()
    if "--test-gui" in sys.argv:
        root.after(int(sys.argv[sys.argv.index("--test-gui") + 1]), root.destroy)
    root.mainloop()

def selftest():
    print("versions:", {n: file_version(os.path.join(HERE, f)) for f, n, _ in PROGS})
    print("en marche:", sorted(running_scripts()))
    print("maj:", check_update())
    print(servers()[1])
    assert "***" in SECRET_RX.sub(lambda m: m.group(1) + m.group(3) + "***", "password=abc123")
    print("journaux:", len(log_files())); print("OK")

if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest(); sys.exit(0)
    try:
        run_gui()
    except Exception:
        try:
            open(os.path.join(HERE, "errors.log"), "a", encoding="utf-8").write(time.ctime() + " tableau_bord\n" + traceback.format_exc())
        except Exception:
            pass
        raise
