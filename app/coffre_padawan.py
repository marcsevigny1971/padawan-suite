# -*- coding: utf-8 -*-
"""
Coffre Padawan 1.0 - Projet Padawan
Sauvegarde globale de TES donnees de la suite dans un seul .zip date, et restauration (meme PC ou autre PC).
Contenu : Grimoire (base + medias), Journal de bord (entrees, pieces, liens permanents, scellees chiffrees), Archiveur (index, fiches, images, textes ; videos/audio en option car lourds),
Arsenal, reglages Padawan (config, memoire, taches), Facteur (regles et dossiers, SANS la partie a distance ni
les boites SQL), Retro (bibliotheque, reglages, mes_programmes), reglages Premiers pas / Recherche.
Jamais : cles, mots de passe, .dpapi, config Messager, atelier\\dos\\PERSO, journaux, sauvegardes internes.
Restauration : n'efface rien ; chaque fichier remplace est d'abord copie dans
%APPDATA%\\Padawan\\coffre_securite\\<date>\\.
Options : --exporter DOSSIER [--videos] | --restaurer FICHIER.zip --oui | --contenu FICHIER.zip
Tests : PADAWAN_DATA, PADAWAN_COFFRE_HERE, RETRO_DIR, APPDATA redirigent tous les chemins.
"""
import os, sys, json, time, shutil, sqlite3, zipfile, tempfile, re, threading, queue, fnmatch
import padawan_commun as pc

APP = "Coffre Padawan"
VERSION = "1.0"
FORMAT = 1
MEDIA_EXT = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4a", ".mp3", ".opus", ".wav", ".flac", ".ogg", ".aac", ".m4v", ".ts"}
SECRET_RX = re.compile(r"(?i)(^facteur_cle|^messager_cle|\.dpapi$|^messager_config|^cookies.*\.txt$|password|mot_?de_?passe|\.pem$|\.key$|^id_rsa|^id_ed25519)")
SKIP_DIRS = {"_sauvegardes", "__pycache__", "perso", "_corbeille_tmp"}
REMOTE_KEYS = ("remote", "boites_sql")   # Facteur : partie privee, jamais exportee


def here():
    return os.environ.get("PADAWAN_COFFRE_HERE") or pc.HERE


def arch_root():
    if os.environ.get("ARCHIVEUR_DATA") or os.environ.get("PADAWAN_DATA"):
        return pc.data_dir("Archiveur", "ARCHIVEUR")
    cfg = pc.read_json(os.path.join(here(), "archiveur_config.json"), {}) or {}
    return cfg.get("archive_root") or pc.data_dir("Archiveur", "ARCHIVEUR")


def retro():
    """donnees Retro (bibliotheque, reglages, pochettes) : Documents\\Padawan\\Retro"""
    return os.environ.get("RETRO_DIR") or os.path.join(os.path.expanduser("~"), "Documents", "Padawan", "Retro")


def retro_priv():
    """atelier et sauvegardes de parties : C:\\web_private\\retro (PC de Marc) ou %LOCALAPPDATA%\\Padawan\\Retro"""
    if os.environ.get("RETRO_PRIV"):
        return os.environ["RETRO_PRIV"]
    if os.path.isdir(r"C:\web"):
        return r"C:\web_private\retro"
    return os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "Padawan", "Retro")


def journal():
    """Journal de bord (meme logique que journal_bord.py)."""
    if hasattr(pc, "journal_dir"):
        return pc.journal_dir()
    return os.path.join(os.path.expanduser("~"), "Documents", "Padawan", "Journal")


def sources(videos=False):
    """[(logique, chemin, type)] type: file | tree | db | facteur | archiveur"""
    h = here()
    g = os.path.dirname(pc.grimoire_db())
    return [
        ("grimoire/grimoire.db", pc.grimoire_db(), "db"),
        ("grimoire/medias", os.path.join(g, "medias"), "tree"),
        ("grimoire/_inbox", os.path.join(g, "_inbox"), "tree"),
        ("archiveur", arch_root(), "archiveur" if not videos else "archiveur+"),
        ("reglages_modules/archiveur_config.json", os.path.join(h, "archiveur_config.json"), "file"),
        ("arsenal/arsenal.json", os.path.join(h, "arsenal.json"), "file"),
        ("padawan/config.json", os.path.join(h, "config.json"), "file"),
        ("padawan/memory.json", os.path.join(h, "memory.json"), "file"),
        ("padawan/tasks.json", os.path.join(h, "tasks.json"), "file"),
        ("facteur/facteur_config.json", os.path.join(pc.facteur_dir(), "facteur_config.json"), "facteur"),
        ("retro/retro_config.json", os.path.join(retro(), "retro_config.json"), "file"),
        ("retro/bibliotheque.json", os.path.join(retro(), "bibliotheque.json"), "file"),
        ("retro/pochettes", os.path.join(retro(), "pochettes"), "tree"),
        ("retro/sauvegardes", os.path.join(retro(), "sauvegardes"), "tree"),
        ("retro_atelier/mes_programmes", os.path.join(retro_priv(), "atelier", "mes_programmes"), "tree"),
        ("retro_atelier/sauvegardes_parties", os.path.join(retro_priv(), "sauvegardes_parties"), "tree"),
        ("journal/journal.db", os.path.join(journal(), "journal.db"), "db"),
        ("journal/medias", os.path.join(journal(), "medias"), "tree"),
        ("journal/liens", os.path.join(journal(), "liens"), "tree"),
        ("journal/scelles", os.path.join(journal(), "scelles"), "tree"),
        ("reglages/journal.json", os.path.join(pc.settings_dir(), "journal.json"), "file"),
        ("reglages/premiers_pas.json", os.path.join(pc.settings_dir(), "premiers_pas.json"), "file"),
        ("reglages/recherche.json", os.path.join(pc.settings_dir(), "recherche.json"), "file"),
    ]


def dest_of(logical):
    for lg, path, typ in sources(True):
        if logical == lg:
            return path
        if typ in ("tree", "archiveur", "archiveur+") and logical.startswith(lg + "/"):
            return os.path.join(path, *logical[len(lg) + 1:].split("/"))
    return None


def is_secret(name):
    return bool(SECRET_RX.search(name))


def walk_tree(base, skip_media):
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d.lower() not in SKIP_DIRS]
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if fn.endswith((".log", ".tmp")) or ".bak" in fn.lower() or is_secret(fn):
                continue
            if skip_media and (ext in MEDIA_EXT or (fn.endswith(".info.json") and fn != "info.json") or ext == ".part"):
                continue
            p = os.path.join(dirpath, fn)
            yield p, os.path.relpath(p, base).replace("\\", "/")


def sanitize_facteur(path):
    d = pc.read_json(path, None)
    if not isinstance(d, dict):
        return None
    for k in REMOTE_KEYS:
        d.pop(k, None)
    return json.dumps(d, ensure_ascii=False, indent=1)


def plan_export(videos=False):
    """Liste (logique, chemin_source, mode) + taille totale ; aucune ecriture."""
    items, total = [], 0
    for lg, path, typ in sources(videos):
        if typ in ("file", "db", "facteur"):
            if os.path.isfile(path):
                items.append((lg, path, typ)); total += os.path.getsize(path)
        elif os.path.isdir(path):
            for p, rel in walk_tree(path, skip_media=(typ == "archiveur")):
                items.append((lg + "/" + rel, p, "file")); total += os.path.getsize(p)
    return items, total


def export(dest_dir, videos=False, progress=None):
    os.makedirs(dest_dir, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d_%H-%M")
    out = os.path.join(dest_dir, f"Coffre-Padawan_{os.environ.get('COMPUTERNAME', 'PC')}_{stamp}.zip")
    items, total = plan_export(videos)
    manifest = {"app": APP, "format": FORMAT, "version": VERSION, "cree": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "pc": os.environ.get("COMPUTERNAME", ""), "videos": bool(videos), "fichiers": {}}
    tmpd = tempfile.mkdtemp(prefix="coffre_")
    done = 0
    try:
        with zipfile.ZipFile(out + ".part", "w", zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as z:
            for i, (lg, path, mode) in enumerate(items):
                if mode == "db":   # copie coherente meme si le Grimoire est ouvert
                    snap = os.path.join(tmpd, os.path.basename(path))
                    src = sqlite3.connect("file:" + path.replace("\\", "/") + "?mode=ro", uri=True)
                    dst = sqlite3.connect(snap)
                    src.backup(dst); dst.close(); src.close()
                    z.write(snap, lg)
                elif mode == "facteur":
                    txt = sanitize_facteur(path)
                    if txt is None:
                        continue
                    z.writestr(lg, txt)
                else:
                    ext = os.path.splitext(path)[1].lower()
                    z.write(path, lg, compress_type=zipfile.ZIP_STORED if ext in MEDIA_EXT | {".jpg", ".png", ".webp", ".zip"} else zipfile.ZIP_DEFLATED)
                try:
                    sz = os.path.getsize(path)
                except OSError:
                    sz = 0
                manifest["fichiers"][lg] = sz
                done += sz
                if progress:
                    progress(i + 1, len(items), done, total, lg)
            z.writestr("coffre_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=1))
            z.writestr("LISEZMOI-COFFRE.txt", "Coffre Padawan : sauvegarde de tes donnees de la suite.\r\n"
                       "Pour restaurer : Coffre Padawan > Restaurer, puis choisis ce fichier.\r\n"
                       "Aucun mot de passe ni cle n'est dans ce zip.\r\n")
        os.replace(out + ".part", out)
    finally:
        shutil.rmtree(tmpd, ignore_errors=True)
        if os.path.exists(out + ".part"):
            try:
                os.remove(out + ".part")
            except OSError:
                pass
    return out, len(manifest["fichiers"]), total


def read_manifest(zpath):
    with zipfile.ZipFile(zpath) as z:
        m = json.loads(z.read("coffre_manifest.json").decode("utf-8"))
    if m.get("app") != APP:
        raise ValueError("Ce zip n'est pas un Coffre Padawan.")
    return m


def _safe_member(name):
    n = name.replace("\\", "/")
    return not (n.startswith("/") or ".." in n.split("/") or ":" in n)


def restore(zpath, progress=None):
    m = read_manifest(zpath)
    stamp = time.strftime("%Y-%m-%d_%H-%M-%S")
    safety = os.path.join(pc.settings_dir(), "coffre_securite", stamp)
    restored, skipped = 0, []
    with zipfile.ZipFile(zpath) as z:
        names = [n for n in z.namelist() if n not in ("coffre_manifest.json", "LISEZMOI-COFFRE.txt") and not n.endswith("/")]
        for i, name in enumerate(names):
            if not _safe_member(name) or is_secret(os.path.basename(name)) or "/perso/" in name.lower():
                skipped.append(name); continue
            dst = dest_of(name)
            if not dst:
                skipped.append(name); continue
            data = z.read(name)
            if name == "facteur/facteur_config.json":   # garde la partie privee du PC actuel
                cur = pc.read_json(dst, {}) or {}
                new = json.loads(data.decode("utf-8"))
                for k in REMOTE_KEYS:
                    if k in cur:
                        new[k] = cur[k]
                    else:
                        new.pop(k, None)
                data = json.dumps(new, ensure_ascii=False, indent=1).encode("utf-8")
            if name == "reglages_modules/archiveur_config.json":   # garde le dossier d'archives du PC actuel
                cur = pc.read_json(dst, {}) or {}
                new = json.loads(data.decode("utf-8"))
                if cur.get("archive_root"):
                    new["archive_root"] = cur["archive_root"]
                else:
                    new.pop("archive_root", None)
                data = json.dumps(new, ensure_ascii=False, indent=2).encode("utf-8")
            extra = [dst + "-wal", dst + "-shm"] if name in ("grimoire/grimoire.db", "journal/journal.db") else []
            for p in [dst] + extra:
                if os.path.isfile(p):
                    bk = os.path.join(safety, *(name.split("/")[:-1] + [os.path.basename(p)]))
                    os.makedirs(os.path.dirname(bk), exist_ok=True)
                    shutil.copy2(p, bk)
                    if p in extra:
                        os.remove(p)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            tmp = dst + ".coffre_tmp"
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, dst)
            restored += 1
            if progress:
                progress(i + 1, len(names), 0, 0, name)
    return restored, skipped, (safety if os.path.isdir(safety) else "")


def human(n):
    for u in ("o", "Ko", "Mo", "Go"):
        if n < 1024:
            return f"{n:.0f} {u}" if u == "o" else f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} To"


# ------------------------------------------------------------------ interface
def run_gui():
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog
    C = pc.C
    root = tk.Tk(); root.title(APP); root.configure(bg=C["BG"])
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    w, h = min(760, sw - 60), min(560, sh - 90)
    root.geometry(f"{w}x{h}+{(sw - w) // 2}+{max(0, (sh - h) // 3)}")
    try:
        root.iconbitmap(os.path.join(pc.HERE, "padawan_tray.ico"))
    except Exception:
        pass
    tk.Label(root, text="\U0001f5c4 Coffre Padawan", bg=C["BG"], fg=C["ACC"], font=("Segoe UI", 18, "bold")).pack(anchor="w", padx=18, pady=(14, 0))
    tk.Label(root, text="Toutes tes donn\u00e9es de la suite dans un seul .zip dat\u00e9 \u2014 et retour en un clic.",
             bg=C["BG"], fg=C["DIM"], font=("Segoe UI", 11)).pack(anchor="w", padx=18)
    q = queue.Queue()
    vid = tk.BooleanVar(value=False)
    status = tk.StringVar(value="Calcul de la taille\u2026")
    s = pc.load_settings("coffre.json", {"dossier": os.path.join(os.path.expanduser("~"), "Documents", "Coffre Padawan")})
    dv = tk.StringVar(value=s["dossier"])

    card = tk.Frame(root, bg=C["CARD"], padx=14, pady=12); card.pack(fill="x", padx=18, pady=12)
    tk.Label(card, text="Exporter", bg=C["CARD"], fg=C["ACC2"], font=("Segoe UI", 13, "bold")).pack(anchor="w")
    tk.Label(card, text="Grimoire (base + m\u00e9dias) \u00b7 Journal de bord \u00b7 Archiveur (fiches, images, textes) \u00b7 Arsenal \u00b7 r\u00e9glages Padawan, "
             "Facteur (r\u00e8gles), R\u00e9tro. Jamais de mot de passe ni de cl\u00e9.", bg=C["CARD"], fg=C["TEXT"],
             wraplength=680, justify="left", font=("Segoe UI", 10)).pack(anchor="w", pady=(2, 6))
    row = tk.Frame(card, bg=C["CARD"]); row.pack(fill="x")
    tk.Entry(row, textvariable=dv, bg=C["ENTRY"], fg=C["TEXT"], insertbackground=C["TEXT"], relief="flat",
             font=("Segoe UI", 10)).pack(side="left", fill="x", expand=True, ipady=3)

    def mk(parent, text, cmd, acc=False):
        return tk.Button(parent, text=text, command=cmd, bg=C["ACC"] if acc else C["BTN"], fg="#06121f" if acc else C["TEXT"],
                         activebackground=C["BTNH"], activeforeground=C["TEXT"], relief="flat",
                         font=("Segoe UI", 10, "bold"), padx=10, pady=4, cursor="hand2")

    def pick():
        d = filedialog.askdirectory(parent=root, initialdir=dv.get())
        if d:
            if d.upper().startswith("F:"):
                messagebox.showwarning(APP, "Choisis un autre disque que F: (cl\u00e9 d'installation).", parent=root); return
            dv.set(os.path.normpath(d))
    mk(row, "Choisir\u2026", pick).pack(side="left", padx=6)
    tk.Checkbutton(card, text="Inclure les vid\u00e9os et l'audio de l'Archiveur (beaucoup plus gros)", variable=vid,
                   command=lambda: size_async(), bg=C["CARD"], fg=C["TEXT"], selectcolor=C["ENTRY"],
                   activebackground=C["CARD"], activeforeground=C["TEXT"]).pack(anchor="w", pady=4)
    bexp = mk(card, "Exporter maintenant", lambda: do_export(), True); bexp.pack(anchor="e")

    card2 = tk.Frame(root, bg=C["CARD"], padx=14, pady=12); card2.pack(fill="x", padx=18)
    tk.Label(card2, text="Restaurer", bg=C["CARD"], fg=C["ACC2"], font=("Segoe UI", 13, "bold")).pack(anchor="w")
    tk.Label(card2, text="Remet les fichiers du coffre \u00e0 leur place. Rien n'est effac\u00e9 : ce qui est remplac\u00e9 est "
             "d'abord copi\u00e9 en s\u00e9curit\u00e9. Ferme Grimoire, Journal et Arsenal avant.", bg=C["CARD"], fg=C["TEXT"],
             wraplength=680, justify="left", font=("Segoe UI", 10)).pack(anchor="w", pady=(2, 6))
    mk(card2, "Restaurer un coffre\u2026", lambda: do_restore(), True).pack(anchor="e")

    pb = ttk.Progressbar(root, mode="determinate"); pb.pack(fill="x", padx=18, pady=(12, 4))
    tk.Label(root, textvariable=status, bg=C["BG"], fg=C["DIM"], wraplength=720, justify="left").pack(anchor="w", padx=18)

    def prog(i, n, done, total, name):
        q.put(("p", i, n, name))

    def size_async():
        v = vid.get()
        threading.Thread(target=lambda: q.put(("size",) + plan_export(v)[1:] + (len(plan_export(v)[0]),)), daemon=True).start()

    def do_export():
        d = dv.get().strip()
        if not d or d.upper().startswith("F:"):
            messagebox.showwarning(APP, "Choisis un dossier (pas F:).", parent=root); return
        s["dossier"] = d; pc.save_settings("coffre.json", s)
        bexp.configure(state="disabled"); status.set("Export en cours\u2026")
        v = vid.get()

        def work():
            try:
                q.put(("exp_ok",) + export(d, v, prog))
            except Exception as ex:
                q.put(("err", str(ex)))
        threading.Thread(target=work, daemon=True).start()

    def do_restore():
        z = filedialog.askopenfilename(parent=root, filetypes=[("Coffre Padawan", "*.zip")], initialdir=dv.get())
        if not z:
            return
        try:
            m = read_manifest(z)
        except Exception as ex:
            messagebox.showerror(APP, f"Coffre illisible : {ex}", parent=root); return
        if not messagebox.askyesno(APP, f"Restaurer le coffre du {m.get('cree', '?')} (PC {m.get('pc', '?')}) ?\n"
                                   f"{len(m.get('fichiers', {}))} fichier(s).\n\nFerme Grimoire, Arsenal et Archiveur avant de continuer.",
                                   parent=root):
            return
        status.set("Restauration\u2026")

        def work():
            try:
                q.put(("res_ok",) + restore(z, prog))
            except Exception as ex:
                q.put(("err", str(ex)))
        threading.Thread(target=work, daemon=True).start()

    def poll():
        try:
            while True:
                m = q.get_nowait()
                if m[0] == "size":
                    status.set(f"Pr\u00eat : environ {human(m[1])} \u00e0 sauvegarder ({m[2]} fichiers).")
                elif m[0] == "p":
                    pb.configure(maximum=m[2], value=m[1]); status.set(f"{m[1]}/{m[2]} \u2014 {m[3]}")
                elif m[0] == "exp_ok":
                    bexp.configure(state="normal")
                    status.set(f"\u2705 Coffre cr\u00e9\u00e9 : {m[1]} ({m[2]} fichiers, {human(os.path.getsize(m[1]))})")
                    pc.reveal(m[1])
                elif m[0] == "res_ok":
                    msg = f"\u2705 {m[1]} fichier(s) restaur\u00e9(s)." + (f"\nCopie de s\u00e9curit\u00e9 : {m[3]}" if m[3] else "")
                    status.set(msg.replace("\n", "  ")); messagebox.showinfo(APP, msg, parent=root)
                elif m[0] == "err":
                    bexp.configure(state="normal"); status.set("Erreur : " + m[1]); messagebox.showerror(APP, m[1], parent=root)
        except queue.Empty:
            pass
        root.after(150, poll)
    root.after(150, poll); size_async()
    if "--selftest" in sys.argv:
        root.after(2500, root.destroy)
    root.mainloop()


def main():
    a = sys.argv[1:]
    if "--exporter" in a:
        out, n, total = export(a[a.index("--exporter") + 1], "--videos" in a)
        print(f"OK {out} ({n} fichiers, {human(total)} source, zip {human(os.path.getsize(out))})"); return 0
    if "--contenu" in a:
        m = read_manifest(a[a.index("--contenu") + 1])
        for k, v in m["fichiers"].items():
            print(v, k)
        return 0
    if "--restaurer" in a:
        if "--oui" not in a:
            print("Ajoute --oui pour confirmer."); return 2
        n, sk, safety = restore(a[a.index("--restaurer") + 1])
        print(f"OK {n} restaure(s), {len(sk)} ignore(s) {sk[:5]}, securite : {safety}"); return 0
    run_gui(); return 0


if __name__ == "__main__":
    sys.exit(main())
