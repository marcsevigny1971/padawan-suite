# -*- coding: utf-8 -*-
"""
Premiers pas 1.0 - Projet Padawan
Guide « Premiers pas en 5 minutes » : la suite en 7 etapes et 6 scenarios concrets, chacun avec
un bouton qui ouvre le bon outil. S'affiche au premier lancement (case « Ne plus afficher au demarrage »),
toujours accessible depuis l'icone Padawan > Premiers pas.
Options : --auto (ne s'ouvre que si la case n'est pas cochee), --selftest
"""
import os, sys
import padawan_commun as pc

APP = "Premiers pas - Padawan"
VERSION = "1.0"
SETTINGS = "premiers_pas.json"

ETAPES = [
    ("1", "L'ic\u00f4ne Padawan", "Tout part de la petite ic\u00f4ne turquoise pr\u00e8s de l'horloge. "
     "Clic droit : chaque outil de la suite est l\u00e0. Une seule ic\u00f4ne, rien d'autre ne s'ajoute.", "tableau"),
    ("2", "Le Tableau de bord", "La vue d'ensemble : quels programmes tournent, tes serveurs, "
     "les mises \u00e0 jour et le bouton \u00ab Rapport de probl\u00e8me \u00bb.", "tableau"),
    ("3", "Trouver n'importe quoi", "Recherche Padawan (Ctrl+Alt+R) cherche en m\u00eame temps dans le Grimoire, "
     "tes archives vid\u00e9o, l'Arsenal et tes dossiers.", "recherche"),
    ("4", "Garder ce qui compte", "Archiveur garde une copie des vid\u00e9os et pages web. "
     "Grimoire range tes notes, liens et m\u00e9dias par sujets.", "archiveur"),
    ("5", "Tes outils en un clic", "Arsenal : des centaines d'outils Windows et tes favoris, "
     "class\u00e9s, cherchables, lan\u00e7ables en un clic.", "arsenal"),
    ("6", "Ton journal de bord", "Le journal du capitaine : tes pens\u00e9es, m\u00e9mos vocaux, photos et liens "
     "rendus permanents. Priv\u00e9 par d\u00e9faut, facile \u00e0 partager quand tu veux. Ctrl+Alt+J pour \u00e9crire, "
     "Ctrl+Alt+K pour y coller ce que tu viens de copier.", "journal"),
    ("7", "Dormir tranquille", "Coffre Padawan met toutes tes donn\u00e9es dans un seul .zip dat\u00e9, "
     "et sait les remettre en place sur un autre PC.", "coffre"),
]

SCENARIOS = [
    ("\U0001f3ac Archiver une vid\u00e9o YouTube et la retrouver dans le Grimoire",
     ["Copie le lien de la vid\u00e9o (Ctrl+C dans la barre d'adresse).",
      "Ouvre Archiveur et clique \u00ab Coller et archiver \u00bb (ou Ctrl+V) : vid\u00e9o, image, description et texte sont gard\u00e9s.",
      "Clic droit sur l'archive > \u00ab Envoyer au Grimoire \u00bb : une fiche est cr\u00e9\u00e9e dans le sujet \u00ab \u00c0 classer \u00bb.",
      "Plus tard : Ctrl+Alt+R, tape un mot du titre, et Recherche Padawan te montre l'archive et la fiche."],
     [("Ouvrir Archiveur", "archiveur"), ("Ouvrir Grimoire", "grimoire"), ("Recherche Padawan", "recherche")]),
    ("\U0001f4da Monter un dossier de recherche sur un sujet",
     ["Dans Grimoire, cr\u00e9e un sujet (ex. \u00ab Sant\u00e9 / Sommeil \u00bb).",
      "Glisse-y des liens, PDF, images, notes ou un m\u00e9mo vocal : tout est cherchable, m\u00eame le texte des PDF.",
      "Ajoute des \u00e9tiquettes pour relier les fiches entre sujets."],
     [("Ouvrir Grimoire", "grimoire")]),
    ("\U0001f4ec Ranger T\u00e9l\u00e9chargements tout seul",
     ["Ouvre Facteur : le bouton \u00ab Ma premi\u00e8re r\u00e8gle \u00bb te guide en 3 \u00e9tapes (quel dossier, quels fichiers, quoi en faire).",
      "Un aper\u00e7u te montre ce qui serait fait, sans rien toucher.",
      "Clique \u00ab Cr\u00e9er et activer \u00bb : Facteur range les nouveaux fichiers tout seul.",
      "Envie d'id\u00e9es ? R\u00e8gles > Biblioth\u00e8que de mod\u00e8les."],
     [("Ouvrir Facteur", "facteur")]),
    ("\U0001f9f0 Installer ta bo\u00eete \u00e0 outils",
     ["Ouvre Arsenal et tape ce que tu cherches (\u00ab r\u00e9seau \u00bb, \u00ab disque \u00bb, \u00ab capture \u00bb\u2026).",
      "\u00c9toile tes favoris, ils restent en haut.",
      "Menu Importer > Paquet d'exemple : ajoute un lot d'outils pr\u00eat (rien n'est lanc\u00e9 \u00e0 l'import)."],
     [("Ouvrir Arsenal", "arsenal")]),
    ("\U0001f916 Poser une question \u00e0 l'IA, sans internet",
     ["Ouvre Padawan IA (Ollama local) : tes questions restent sur ton PC.",
      "Dans Recherche Padawan, le bouton \u00ab Demander \u00e0 Padawan \u00bb r\u00e9sume ce que tu as trouv\u00e9 dans tes donn\u00e9es."],
     [("Ouvrir Padawan IA", "padawan"), ("Recherche Padawan", "recherche")]),
    ("\U0001f4d3 Tenir ton journal de bord (et partager un passage)",
     ["Ctrl+Alt+J (ou ic\u00f4ne Padawan > Journal de bord) : une nouvelle entr\u00e9e s'ouvre, avec la date stellaire.",
      "Colle n'importe quoi (Ctrl+V) : texte, capture d'\u00e9cran, image, fichier ou lien. Un lien devient une carte : "
      "\u00ab Rendre ce lien permanent \u00bb en garde une copie sur ton PC.",
      "\U0001f399 Vocal pour un m\u00e9mo parl\u00e9 ; humeur, m\u00e9t\u00e9o, lieu et \u00e9tiquettes en un clic. Tout s'enregistre tout seul.",
      "Pour partager : s\u00e9lectionne un passage > \u00ab Copier ce passage \u00bb, ou Partager > Page web / PDF. "
      "Seul ce que tu choisis part, jamais le reste du journal."],
     [("Ouvrir le Journal", "journal")]),
    ("\U0001f5c4 Changer de PC sans rien perdre",
     ["Ouvre Coffre Padawan > \u00ab Exporter \u00bb : un seul .zip dat\u00e9 (Grimoire, archives, Arsenal, r\u00e9glages).",
      "Sur l'autre PC : installe Padawan, ouvre Coffre > \u00ab Restaurer \u00bb et choisis le .zip.",
      "Avant d'\u00e9craser quoi que ce soit, Coffre garde une copie de s\u00e9curit\u00e9 de ce qui \u00e9tait l\u00e0."],
     [("Ouvrir Coffre", "coffre")]),
]


def should_show_auto():
    return not pc.load_settings(SETTINGS, {"ne_plus_afficher": False}).get("ne_plus_afficher")


def run_splash(seconds=4.5):
    """Petite animation de bienvenue (Tk pur, quelques secondes, cliquer pour passer)."""
    import tkinter as tk, math, time as _t
    C = pc.C
    r = tk.Tk(); r.overrideredirect(True); r.configure(bg=C["BG"])
    w, h = 520, 300
    sw, sh = r.winfo_screenwidth(), r.winfo_screenheight()
    r.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")
    try:
        r.attributes("-topmost", True); r.attributes("-alpha", 0.0)
    except Exception:
        pass
    cv = tk.Canvas(r, width=w, height=h, bg=C["BG"], highlightthickness=1, highlightbackground=C["ACC"])
    cv.pack()
    cx, cy = w // 2, 120
    rings = [cv.create_oval(0, 0, 0, 0, outline=C["ACC"], width=1) for _ in range(4)]
    disc = cv.create_oval(cx - 34, cy - 34, cx + 34, cy + 34, fill=C["ACC"], outline="")
    cv.create_oval(cx - 19, cy - 19, cx + 19, cy + 19, fill=C["BG"], outline="")
    core = cv.create_oval(cx - 8, cy - 8, cx + 8, cy + 8, fill=C["ACC2"], outline="")
    cv.create_text(cx, 196, text="Bienvenue dans la Padawan Suite", fill=C["TEXT"], font=("Segoe UI", 16, "bold"))
    sub = cv.create_text(cx, 228, text="", fill=C["DIM"], font=("Segoe UI", 10))
    cv.create_text(cx, 280, text="clic pour passer", fill="#4a5b7a", font=("Segoe UI", 8))
    msgs = ["Padawan \u00b7 ton assistant IA local", "Grimoire \u00b7 tes notes et recherches", "Archiveur \u00b7 tes vid\u00e9os et pages web",
            "Facteur \u00b7 range tes fichiers tout seul", "Journal de bord \u00b7 ton r\u00e9cit de capitaine", "Arsenal \u00b7 ta bo\u00eete \u00e0 outils", "Recherche \u00b7 Ctrl+Alt+R partout",
            "Tout reste sur ton PC. On y va !"]
    t0 = _t.time()
    done = [False]

    def stop(_e=None):
        if not done[0]:
            done[0] = True
            try:
                r.destroy()
            except Exception:
                pass
    r.bind("<Button-1>", stop); r.bind("<Escape>", stop)

    def tick():
        if done[0]:
            return
        t = _t.time() - t0
        if t > seconds:
            stop(); return
        a = min(1.0, t / 0.5, max(0.0, (seconds - t) / 0.5))
        try:
            r.attributes("-alpha", a)
        except Exception:
            pass
        for i, it in enumerate(rings):
            ph = (t * 0.8 + i / 4) % 1.0
            rr = 36 + ph * 70
            cv.coords(it, cx - rr, cy - rr, cx + rr, cy + rr)
            v = int(58 + (1 - ph) * 0)
            cv.itemconfigure(it, outline=C["ACC"] if ph < 0.6 else "#1f5f66")
        k = 8 + 2 * math.sin(t * 6)
        cv.coords(core, cx - k, cy - k, cx + k, cy + k)
        cv.itemconfigure(sub, text=msgs[min(len(msgs) - 1, int(t / seconds * len(msgs)))])
        r.after(33, tick)
    r.after(10, tick)
    r.mainloop()


def run_gui():
    import tkinter as tk
    from tkinter import messagebox
    C = pc.C
    root = tk.Tk()
    root.title(APP)
    root.configure(bg=C["BG"])
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    w, h = min(980, sw - 60), min(760, sh - 90)
    root.geometry(f"{w}x{h}+{(sw - w) // 2}+{max(0, (sh - h) // 2 - 20)}")
    try:
        root.iconbitmap(os.path.join(pc.HERE, "padawan_tray.ico"))
    except Exception:
        pass

    def go(key):
        if not pc.launch(key):
            messagebox.showwarning(APP, f"Programme introuvable : {pc.PROGRAMMES.get(key, (key,))[0]}", parent=root)

    top = tk.Frame(root, bg=C["PANEL"]); top.pack(fill="x")
    tk.Label(top, text="\u2728 Bienvenue dans la Padawan Suite", bg=C["PANEL"], fg=C["ACC"],
             font=("Segoe UI", 18, "bold")).pack(anchor="w", padx=18, pady=(12, 0))
    tk.Label(top, text="Premiers pas en 5 minutes \u2014 clique les boutons, tout s'ouvre au bon endroit.",
             bg=C["PANEL"], fg=C["DIM"], font=("Segoe UI", 11)).pack(anchor="w", padx=18, pady=(0, 12))

    outer = tk.Frame(root, bg=C["BG"]); outer.pack(fill="both", expand=True)
    cv = tk.Canvas(outer, bg=C["BG"], highlightthickness=0)
    sb = tk.Scrollbar(outer, orient="vertical", command=cv.yview)
    body = tk.Frame(cv, bg=C["BG"])
    body.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
    win = cv.create_window((0, 0), window=body, anchor="nw")
    cv.bind("<Configure>", lambda e: cv.itemconfigure(win, width=e.width))
    cv.configure(yscrollcommand=sb.set)
    cv.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")
    root.bind_all("<MouseWheel>", lambda e: cv.yview_scroll(int(-e.delta / 120), "units"))

    def btn(parent, text, cmd, accent=False):
        b = tk.Button(parent, text=text, command=cmd, bg=C["ACC"] if accent else C["BTN"],
                      fg="#06121f" if accent else C["TEXT"], activebackground=C["BTNH"], activeforeground=C["TEXT"],
                      relief="flat", font=("Segoe UI", 10, "bold"), padx=10, pady=4, cursor="hand2")
        return b

    tk.Label(body, text="Les 7 \u00e9tapes", bg=C["BG"], fg=C["ACC2"], font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=18, pady=(14, 4))
    grid = tk.Frame(body, bg=C["BG"]); grid.pack(fill="x", padx=12)
    for i, (num, titre, texte, key) in enumerate(ETAPES):
        card = tk.Frame(grid, bg=C["CARD"], padx=12, pady=10)
        last_alone = i == len(ETAPES) - 1 and len(ETAPES) % 2 == 1
        card.grid(row=i // 2, column=i % 2, columnspan=2 if last_alone else 1, sticky="nsew", padx=6, pady=6)
        grid.columnconfigure(i % 2, weight=1)
        tk.Label(card, text=f"{num}. {titre}", bg=C["CARD"], fg=C["ACC"], font=("Segoe UI", 12, "bold")).pack(anchor="w")
        tk.Label(card, text=texte, bg=C["CARD"], fg=C["TEXT"], font=("Segoe UI", 10), wraplength=400,
                 justify="left").pack(anchor="w", pady=(2, 6))
        btn(card, "Ouvrir \u2192", lambda k=key: go(k)).pack(anchor="e")

    tk.Label(body, text="Des sc\u00e9narios concrets", bg=C["BG"], fg=C["ACC2"],
             font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=18, pady=(16, 4))
    for titre, pas, boutons in SCENARIOS:
        card = tk.Frame(body, bg=C["CARD"], padx=14, pady=10)
        card.pack(fill="x", padx=18, pady=6)
        tk.Label(card, text=titre, bg=C["CARD"], fg=C["TEXT"], font=("Segoe UI", 12, "bold")).pack(anchor="w")
        for j, p in enumerate(pas, 1):
            tk.Label(card, text=f"  {j}. {p}", bg=C["CARD"], fg=C["DIM"], font=("Segoe UI", 10),
                     wraplength=840, justify="left").pack(anchor="w")
        row = tk.Frame(card, bg=C["CARD"]); row.pack(anchor="e", pady=(6, 0))
        for lab, key in boutons:
            btn(row, lab, lambda k=key: go(k), accent=True).pack(side="left", padx=4)

    tk.Label(body, text="\U0001f4da Ressources et mises \u00e0 jour", bg=C["BG"], fg=C["ACC2"],
             font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=18, pady=(16, 4))
    rcard = tk.Frame(body, bg=C["CARD"], padx=14, pady=10)
    rcard.pack(fill="x", padx=18, pady=6)
    tk.Label(rcard, text="La Padawan Suite a sa page publique sur GitHub : les nouvelles versions, le guide complet "
             "et une bo\u00eete \u00e0 suggestions. Ces liens sont aussi dans l'ic\u00f4ne Padawan > "
             "\u00ab Ressources / GitHub \u00bb.", bg=C["CARD"], fg=C["TEXT"], font=("Segoe UI", 10),
             wraplength=840, justify="left").pack(anchor="w")
    rrow = tk.Frame(rcard, bg=C["CARD"]); rrow.pack(anchor="e", pady=(6, 0))
    for lab, url, _d in getattr(pc, "RESSOURCES", []):
        btn(rrow, lab, lambda u=url: pc.open_url(u), accent=lab.startswith("\U0001f3e0")).pack(side="left", padx=4)

    tk.Label(body, text="Astuce : le fichier LISEZMOI-PREMIERS-PAS.txt contient ce guide en texte, \u00e0 imprimer ou \u00e0 partager.",
             bg=C["BG"], fg=C["DIM"], font=("Segoe UI", 9, "italic")).pack(anchor="w", padx=18, pady=(10, 16))

    bot = tk.Frame(root, bg=C["PANEL"]); bot.pack(fill="x")
    st = pc.load_settings(SETTINGS, {"ne_plus_afficher": False})
    var = tk.BooleanVar(value=bool(st.get("ne_plus_afficher")))

    def save_flag():
        st["ne_plus_afficher"] = bool(var.get())
        try:
            pc.save_settings(SETTINGS, st)
        except Exception:
            pass
    tk.Checkbutton(bot, text="Ne plus afficher au d\u00e9marrage", variable=var, command=save_flag,
                   bg=C["PANEL"], fg=C["TEXT"], selectcolor=C["ENTRY"], activebackground=C["PANEL"],
                   activeforeground=C["TEXT"], font=("Segoe UI", 10)).pack(side="left", padx=14, pady=8)
    var_anim = tk.BooleanVar(value=bool(st.get("animation", True)))

    def save_anim():
        st["animation"] = bool(var_anim.get())
        try:
            pc.save_settings(SETTINGS, st)
        except Exception:
            pass
    tk.Checkbutton(bot, text="Animation de bienvenue", variable=var_anim, command=save_anim,
                   bg=C["PANEL"], fg=C["TEXT"], selectcolor=C["ENTRY"], activebackground=C["PANEL"],
                   activeforeground=C["TEXT"], font=("Segoe UI", 10)).pack(side="left", padx=6, pady=8)
    btn(bot, "Lire le guide texte", lambda: pc.open_path(os.path.join(pc.HERE, "LISEZMOI-PREMIERS-PAS.txt"))).pack(side="right", padx=6, pady=8)
    btn(bot, "Fermer", lambda: (save_flag(), root.destroy()), accent=True).pack(side="right", padx=6, pady=8)
    root.protocol("WM_DELETE_WINDOW", lambda: (save_flag(), root.destroy()))
    root.bind("<Escape>", lambda e: (save_flag(), root.destroy()))
    if "--selftest" in sys.argv:
        root.after(1500, root.destroy)
    root.mainloop()


def main():
    if "--auto" in sys.argv and not should_show_auto():
        return 0
    st = pc.load_settings(SETTINGS, {"ne_plus_afficher": False, "animation": True})
    if ("--auto" in sys.argv and st.get("animation", True)) or "--splash" in sys.argv or "--bienvenue" in sys.argv:
        try:
            run_splash(1.5 if "--selftest" in sys.argv else 4.5)
        except Exception:
            pass
        if "--splash" in sys.argv:
            return 0
    if "--selftest" in sys.argv and "--nogui" in sys.argv:
        for k in {k for *_, k in ETAPES} | {k for _, _, bs in SCENARIOS for _, k in bs}:
            f = pc.PROGRAMMES[k][0]
            print(("OK  " if os.path.isfile(os.path.join(pc.HERE, f)) else "MANQUE ") + f)
        return 0
    run_gui()
    return 0


if __name__ == "__main__":
    sys.exit(main())
