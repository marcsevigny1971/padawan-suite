# -*- coding: utf-8 -*-
# Partie de grimoire1.py (découpage v1.2.2, comportement inchangé).
# Chargée par grimoire1.py dans un espace de noms commun : ne pas lancer seule.
from __future__ import annotations



# ================================================================ contenu de depart
SEED_SUBJECTS: List[Tuple[str, str, str, str, List[Tuple[str, str, str, str]]]] = [
    ("Bienvenue", "👋", "#FFFF55", "Le mode d'emploi du Grimoire (supprimable).", []),
    (INBOX_SUBJECT, "📥", "#C0C0C0", "Ce qui arrive de l'Archiveur, de Padawan, d'Arsenal ou de la ligne de commande.", []),
    ("Géopolitique", "🌍", "#7FB2FF", "", []),
    ("Recettes", "🍲", "#FFAA33", "", []),
    ("Santé", "❤", "#FF5555", "", [
        ("Santé naturelle", "🍵", "#66E0B0", ""),
        ("Plantes médicinales", "🌿", "#55FF55", ""),
        ("Protocoles", "📋", "#FFD27F", "")]),
    ("Technologies informatiques", "💻", "#55FFFF", "", [
        ("Python", "🐍", "#FFFF55", ""),
        ("Arduino / NodeMCU", "🔌", "#40C4FF", ""),
        ("Windows", "🪟", "#7FB2FF", ""),
        ("Web", "🌐", "#B388FF", "")]),
    ("Savoir-faire", "💡", "#FFD27F", "Trucs bons à savoir.", []),
    ("Nature et jardinage", "🌱", "#A8E05F", "", []),
    ("Autonomie / Survie", "🏕", "#E0A060", "", []),
    ("Énergie libre / HHO", "⚡", "#FFFF55", "", []),
    ("Sciences", "🔬", "#40C4FF", "", []),
    ("Histoire", "📜", "#E0A060", "", []),
    ("Finances", "💰", "#66E0B0", "", []),
    ("Bricolage et maison", "🔨", "#FFAA33", "", []),
    ("Lectures et vidéos à voir", "📚", "#FF9EB5", "", []),
    ("Idées et projets", "🚀", "#FF77FF", "", []),
]

WELCOME_MD = """# Bienvenue dans ton Grimoire 📖
Ton carnet de recherche : tout ce que tu trouves, classé par **sujets**, et retrouvable en un instant.

## Ajouter quelque chose
- **Ctrl+V** n'importe où : colle un lien, du texte, une image ou des fichiers copiés, ils vont dans le sujet ouvert
- **Glisser-déposer** des fichiers ou des liens depuis l'Explorateur ou le navigateur
- Bouton **＋ Ajouter** : note, modèle de fiche (source, protocole, plante, recette…), lien, citation, image, document, son, page web complète
- **Ctrl+R** : mémo vocal au micro (transcription optionnelle)
- Depuis l'Archiveur : clic droit sur une archive → « Envoyer au Grimoire »

## Retrouver
- **Ctrl+F** : recherche dans tout (titres, notes, texte des PDF, transcriptions, étiquettes), sans te soucier des accents
- Vues **Liste**, **Cartes** et **Chronologie** (Ctrl+1, Ctrl+2, Ctrl+3) · **F11** : mode lecture
- ★ favori (Ctrl+D) · 📌 épingler (Ctrl+P) · étiquettes (Ctrl+T) · **Ctrl+G** : aller à un sujet ou une fiche

## Organiser
- Les sujets et sous-sujets sont à gauche : clic droit pour créer, renommer (F2), changer l'icône et la couleur, épingler, fusionner, supprimer
- Glisse un sujet sur un autre pour le ranger dedans ; glisse des fiches sur un sujet pour les déplacer (avec Ctrl : copier)
- Supprimer envoie à la 🗑 Corbeille (restaurable) · **Ctrl+Z** annule

## Relier tes idées
Écris [[Recettes]] ou [[le titre d'une fiche]] dans une note : la référence devient cliquable. L'onglet Fiche montre aussi les rétroliens.
Les liens web sont toujours cliquables : https://marcsevigny.ca

## Tes données
Tout est dans `C:\\web\\FTP_HOME\\GRIMOIRE` (base grimoire.db + dossier medias), donc dans tes sauvegardes, avec des copies automatiques dans _sauvegardes.

[ ] Essayer Ctrl+V avec un lien YouTube
[ ] Créer ma première fiche « Plante médicinale » (＋ Ajouter → Modèle)
[ ] Supprimer ce sujet Bienvenue quand je suis à l'aise 😉"""

TEMPLATES: Dict[str, Tuple[str, str]] = {
    "Source / référence": ("📑", """# Source
**Titre :** 
**Auteur :** 
**Date :** 
**Lien :** 

## Résumé


## Citations clés
> 

## Fiabilité
[ ] Source primaire
[ ] Vérifiée par une autre source
Remarques : 
"""),
    "Protocole": ("📋", """# Protocole : 
**Objectif :** 
**Durée :** 

## Matériel / ingrédients
- 

## Posologie / étapes
1. 

## Précautions et contre-indications
- 

## Suivi
[ ] Jour 1 : 
[ ] Semaine 1 : 

## Sources
- 
"""),
    "Plante médicinale": ("🌿", """# Plante : 
**Nom latin :** 
**Famille :** 
**Parties utilisées :** 

## Propriétés
- 

## Usages
- 

## Préparation (tisane, teinture, cataplasme…)


## Posologie


## Précautions / interactions
- 

## Où la trouver / cueillette


## Sources
- 
"""),
    "Recette": ("🍲", """# Recette : 
**Portions :**  · **Préparation :**  · **Cuisson :** 

## Ingrédients
[ ] 

## Étapes
1. 

## Notes et variantes


**Source :** 
"""),
    "Livre / vidéo / article": ("📚", """# 
**Auteur :** 
**Lien :** 
**Vu / lu le :** 

## En bref


## À retenir
- 

## Citations
> 

## Ce que j'en pense

"""),
    "Journal de recherche": ("🔎", """# Recherche : 
**Question :** 

## Ce que je sais déjà
- 

## Pistes à explorer
[ ] 

## Trouvailles
- 

## Conclusion provisoire

"""),
    "Idée / projet": ("🚀", """# Projet : 
**Pourquoi :** 

## Matériel / budget
- 

## Étapes
[ ] 

## Prochaine action


## Liens utiles
- 
"""),
    "Expérience": ("🧪", """# Expérience : 
**Hypothèse :** 
**Date :** 

## Montage / matériel
- 

## Mesures
| Essai | Valeur | Remarque |

## Résultat


## Conclusion

"""),
    "Fait / événement": ("📅", """# Événement : 
**Date :** 
**Lieu :** 
**Acteurs :** 

## Ce qui s'est passé


## Contexte


## Sources
- 
"""),
    "Personne / contact": ("👤", """# 
**Rôle / domaine :** 
**Site / contact :** 

## Pourquoi c'est intéressant


## Œuvres, vidéos, publications
- 
"""),
}


def seed_content(store: Store, demo: bool = False) -> int:
    """Cree les sujets de depart une seule fois (renommables / supprimables ensuite)."""
    if int(store.get("seed_version", 0) or 0) >= SEED_VERSION:
        return 0
    n = 0
    welcome_sid = None
    for name, icon, color, desc, kids in SEED_SUBJECTS:
        sid = store.find_subject(name) if name == INBOX_SUBJECT else None
        if not sid:
            sid = store.add_subject(name, None, icon, color, desc, pinned=(name == "Bienvenue"))
            n += 1
        if name == "Bienvenue":
            welcome_sid = sid
        for kn, ki, kc, kd in kids:
            store.add_subject(kn, sid, ki, kc, kd)
            n += 1
    if welcome_sid:
        store.add_item(welcome_sid, "note", title="Comment utiliser le Grimoire", body=runs_to_json(md_runs(WELCOME_MD)),
                       pinned=1, fav=1, tags="aide, grimoire", source="Grimoire")
        store.add_item(welcome_sid, "quote", title="La curiosité",
                       body=runs_to_json([["La curiosité est le moteur de la recherche ; le carnet en est la mémoire.", []]]),
                       author="Grimoire", source="Exemple de citation (supprimable)", tags="exemple")
    store.set("seed_version", SEED_VERSION)
    store.set("created", now_iso())
    if demo:
        seed_demo(store)
    return n


def seed_demo(store: Store) -> None:
    """Contenu d'exemple pour les captures et --smoke (dossier de donnees de test seulement)."""
    p = store.find_subject("Plantes médicinales") or store.ensure_subject("Santé/Plantes médicinales")
    store.add_item(p, "note", title="Échinacée", tags="immunité, plante",
                   body=runs_to_json(md_runs(TEMPLATES["Plante médicinale"][1].replace("# Plante : ", "# Plante : Échinacée")
                                             .replace("**Nom latin :** ", "**Nom latin :** Echinacea purpurea")
                                             .replace("**Famille :** ", "**Famille :** Astéracées"))), fav=1)
    store.add_item(p, "link", title="Échinacée — Passeport Santé", url="https://www.passeportsante.net/fr/Solutions/PlantesSupplements/Fiche.aspx?doc=echinacee_ps",
                   tags="immunité", meta={"description": "Fiche complète : usages, posologie, précautions.", "site": "passeportsante.net"})
    store.add_item(p, "quote", title="Hippocrate", body=runs_to_json([["Que ton aliment soit ta seule médecine.", []]]),
                   author="Hippocrate", source="attribué", tags="citation")
    store.add_item(p, "video", title="Exemple de vidéo (Big Buck Bunny)", url="https://www.youtube.com/watch?v=aqz-KE-bpKQ",
                   tags="vidéo", meta={"site": "YouTube"})
    store.add_item(p, "note", title="Tisane du soir", event_date="2026-09-15",
                   body=runs_to_json(md_runs("Camomille + mélisse + tilleul.\n- 1 c. à thé de chaque\n- infuser **10 minutes**")))


# ================================================================ ajout d'items (interface, CLI, inbox)
def placeholder_title(url: str) -> str:
    yid = youtube_id(url)
    if yid:
        return "Vidéo YouTube"
    return domain_of(url) or url[:80]


def add_url(store: Store, sid: int, url: str, title: str = "", note: str = "", tags: str = "", source: str = "") -> int:
    url = fix_url(url)
    typ = "video" if is_video_url(url) else "link"
    auto = not title
    body = runs_to_json(md_runs(note)) if note else ""
    return store.add_item(sid, typ, title=title or placeholder_title(url), url=url, body=body, tags=tags,
                          source=source or domain_of(url), meta={"auto_title": auto, "pending": True})


def enrich_link(store: Store, iid: int) -> Dict[str, str]:
    it = store.item(iid)
    if not it or not it.get("url"):
        return {}
    info = fetch_link_info(it["url"])
    m = store.meta(it)
    upd: Dict[str, Any] = {}
    if info.get("title") and (m.get("auto_title") or not it.get("title")):
        upd["title"] = info["title"][:300]
    if info.get("author") and not it.get("author"):
        upd["author"] = info["author"][:200]
    if info.get("description"):
        upd["extracted"] = info["description"]
    pub = info.get("published", "")
    mm = re.match(r"(\d{4}-\d{2}-\d{2})", pub or "")
    if mm and not it.get("event_date"):
        upd["event_date"] = mm.group(1)
    if info.get("image"):
        try:
            b, _u, _c = http_get(info["image"], 12, 6_000_000)
            dest = thumb_path(store, it["subject_id"], iid)
            if save_thumb_bytes(b, dest):
                upd["thumb"] = Paths.rel(dest)
        except Exception as ex:
            logger.info("miniature %s : %s", info["image"], ex)
    m.update({"description": info.get("description", ""), "site": info.get("site", ""), "image_url": info.get("image", ""),
              "pending": False, "fetched": now_iso()})
    if info.get("error") and not info.get("title"):
        m["fetch_error"] = info["error"]
    else:
        m.pop("fetch_error", None)
    upd["meta"] = m
    store.update_item(iid, touch=False, **upd)
    return info


def add_file(store: Store, sid: int, path: str, title: str = "", move: bool = False, note: str = "", tags: str = "",
             typ: str = "") -> int:
    path = os.path.abspath(path)
    typ = typ or type_for_file(path)
    rel = store.import_file(path, sid, move=move)
    size = os.path.getsize(Paths.abs(rel)) if os.path.isfile(Paths.abs(rel)) else 0
    meta = {"filename": os.path.basename(path), "size": size, "original": path, "pending": True}
    body = runs_to_json(md_runs(note)) if note else ""
    return store.add_item(sid, typ, title=title or os.path.splitext(os.path.basename(path))[0], file=rel, body=body,
                          tags=tags, meta=meta)


def enrich_file(store: Store, iid: int, ocr: bool = False) -> None:
    it = store.item(iid)
    if not it:
        return
    p = Paths.abs(it.get("file") or "")
    if not p or not os.path.isfile(p):
        return
    m = store.meta(it)
    upd: Dict[str, Any] = {}
    ext = os.path.splitext(p)[1].lower()
    if it["type"] in ("image", "video") or ext in IMG_EXT | VIDEO_EXT:
        dest = thumb_path(store, it["subject_id"], iid)
        if thumb_from_file(p, dest):
            upd["thumb"] = Paths.rel(dest)
        if ext in IMG_EXT:
            try:
                from PIL import Image  # type: ignore
                with Image.open(p) as im:
                    m["width"], m["height"] = im.size
            except Exception:
                pass
    if it["type"] == "document" or ext in DOC_EXT:
        txt, info = extract_text(p)
        if txt:
            upd["extracted"] = txt
        m.update(info)
    if it["type"] in ("audio", "voice", "video") or ext in AUDIO_EXT | VIDEO_EXT:
        d = media_duration(p)
        if d:
            m["duration"] = d
    if ocr and ext in IMG_EXT:
        txt, err = ocr_image(p)
        if txt:
            upd["extracted"] = txt
            m["ocr"] = now_iso()
        elif err:
            m["ocr_error"] = err
    m["pending"] = False
    upd["meta"] = m
    store.update_item(iid, touch=False, **upd)


def add_text(store: Store, sid: int, text: str, title: str = "", note: str = "", tags: str = "",
             source: str = "") -> List[int]:
    """Texte quelconque : chemin existant -> fichier ; liens seuls -> liens ; sinon note."""
    t = (text or "").strip().strip('"')
    if not t:
        return []
    if len(t) < 600 and "\n" not in t and os.path.exists(t):
        if os.path.isdir(t):
            return import_folder(store, sid, t)[0]
        return [add_file(store, sid, t, title, note=note, tags=tags)]
    toks = t.split()
    if toks and all(is_url(x) for x in toks):
        return [add_url(store, sid, u, title if len(toks) == 1 else "", note, tags, source) for u in toks]
    first = next((ln.strip() for ln in t.splitlines() if ln.strip()), "Note")
    ttl = title or (first[:80] + ("…" if len(first) > 80 else ""))
    body = runs_from_any(t)
    if note:
        body += [["\n\n" + note, []]]
    return [store.add_item(sid, "note", title=ttl, body=runs_to_json(body), tags=tags, source=source)]


def add_quote(store: Store, sid: int, text: str, author: str = "", source: str = "", url: str = "", page: str = "",
              tags: str = "", date: str = "") -> int:
    words = re.sub(r"\s+", " ", text).strip()
    title = author or (words[:60] + ("…" if len(words) > 60 else ""))
    return store.add_item(sid, "quote", title=title, body=runs_to_json([[text.strip(), []]]), author=author, source=source,
                          url=fix_url(url) if url else "", tags=tags, event_date=date, meta={"page": page})


def add_image_pil(store: Store, sid: int, im: Any, title: str = "") -> int:
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = unique_path(store.subject_media_dir(sid), f"image_collee_{stamp}.png")
    im.save(dest, "PNG")
    meta = {"filename": os.path.basename(dest), "size": os.path.getsize(dest), "pending": True, "origin": "presse-papiers"}
    return store.add_item(sid, "image", title=title or f"Image collée {fmt_date(now_iso())}", file=Paths.rel(dest), meta=meta)


def import_folder(store: Store, sid: int, folder: str, recursive: bool = True,
                  progress: Optional[Callable[[str], None]] = None) -> Tuple[List[int], int]:
    """Cree un sous-sujet au nom du dossier (sous-dossiers = sous-sujets) et y copie les fichiers."""
    folder = os.path.abspath(folder)
    top = store.add_subject(os.path.basename(folder.rstrip("\\/")) or "Import", sid, "📂")
    ids: List[int] = []
    nsub = 1
    mapping = {folder: top}
    for root, dirs, files in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if not d.startswith((".", "_", "$"))) if recursive else []
        cur = mapping.get(root)
        if cur is None:
            parent = mapping.get(os.path.dirname(root), top)
            cur = store.add_subject(os.path.basename(root), parent, "📂")
            mapping[root] = cur
            nsub += 1
        for f in sorted(files):
            if f.lower() in ("desktop.ini", "thumbs.db") or f.startswith("~$"):
                continue
            fp = os.path.join(root, f)
            try:
                if f.lower().endswith(".url"):
                    with open(fp, "r", encoding="utf-8", errors="ignore") as fh:
                        mm = re.search(r"^URL=(.+)$", fh.read(), re.M)
                    if mm:
                        ids.append(add_url(store, cur, mm.group(1).strip(), os.path.splitext(f)[0]))
                        continue
                ids.append(add_file(store, cur, fp))
                if progress and len(ids) % 10 == 0:
                    progress(f"Import : {len(ids)} fichier(s)…")
            except Exception as ex:
                logger.warning("import %s : %s", fp, ex)
    return ids, nsub


def process_payload(store: Store, d: Dict[str, Any]) -> List[int]:
    """Ajout venant de --ajouter (direct ou par _inbox) ; retourne les ids crees (enrichis ensuite)."""
    val = str(d.get("ajouter") or "").strip()
    if not val:
        return []
    sid = store.ensure_subject(d["sujet"]) if d.get("sujet") else store.inbox_subject()
    kind = d.get("type", "")
    if kind == "citation":
        return [add_quote(store, sid, val, d.get("auteur", ""), d.get("source", ""), d.get("url", ""), tags=d.get("etiquettes", ""))]
    ids = add_text(store, sid, val, d.get("titre", ""), d.get("note", ""), d.get("etiquettes", ""), d.get("source", ""))
    return ids


LOT_TYPES = {"note": "note", "citation": "quote", "quote": "quote", "lien": "link", "link": "link", "video": "video"}


def import_lot(store: Store, data: Any, progress: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
    """Import en lot (--importer-lot fichier.json) : sujets + fiches riches (mini-markdown, liens, etiquettes,
    favoris, modeles, citations). Idempotent : une fiche deja presente (meme titre, meme sujet) est sautee.
    Format : {"lot": "nom", "sujets": [{"chemin": "Sante/Plantes", "icone": "🌿", "couleur": "#55FF55",
    "description": ""}], "fiches": [{"sujet": "...", "type": "note|citation|lien", "titre": "...", "md": "...",
    "etiquettes": "a, b", "favori": 0, "epingle": 0, "source": "", "auteur": "", "url": "", "page": "",
    "date": "AAAA-MM-JJ", "modele": "Plante médicinale"}]}"""
    if isinstance(data, list):
        data = {"fiches": data}
    lot = str(data.get("lot") or dt.datetime.now().strftime("lot_%Y%m%d_%H%M%S"))
    rep: Dict[str, Any] = {"lot": lot, "ajoutees": [], "sautees": [], "erreurs": [], "sujets_crees": 0}
    for sj in data.get("sujets", []) or []:
        try:
            path = str(sj.get("chemin") or "").strip()
            if not path:
                continue
            existed = store.find_subject(path)
            sid = store.ensure_subject(path, sj.get("icone") or "📁")
            if not existed:
                rep["sujets_crees"] += 1
                upd = {k2: sj[k1] for k1, k2 in (("couleur", "color"), ("description", "description"), ("icone", "icon"))
                       if sj.get(k1)}
                if upd:
                    store.update_subject(sid, **upd)
        except Exception as ex:
            rep["erreurs"].append(f"sujet {sj!r} : {ex}")
    for n, f in enumerate(data.get("fiches", []) or [], start=1):
        try:
            title = str(f.get("titre") or "").strip()
            sid = store.ensure_subject(f["sujet"]) if f.get("sujet") else store.inbox_subject()
            typ = LOT_TYPES.get(str(f.get("type") or "note").lower(), "note")
            if title and any(norm(r["title"]) == norm(title) for r in store.items_in([sid])):
                rep["sautees"].append(title)
                continue
            text = str(f.get("md") or f.get("texte") or "")
            meta: Dict[str, Any] = {"lot": lot, "auto_title": False}
            if f.get("modele"):
                meta["template"] = f["modele"]
            if f.get("page"):
                meta["page"] = str(f["page"])
            if f.get("description"):
                meta["description"] = str(f["description"])
            if typ == "quote":
                body = runs_to_json([[text.strip(), []]])
            else:
                body = runs_to_json(md_runs(text)) if text else ""
            url = fix_url(f["url"]) if f.get("url") else ""
            if typ == "link" and is_video_url(url):
                typ = "video"
            iid = store.add_item(sid, typ, title=title or (runs_plain(md_runs(text))[:80] or "Fiche"), body=body, url=url,
                                 tags=f.get("etiquettes") or "", source=f.get("source") or "", author=f.get("auteur") or "",
                                 fav=1 if f.get("favori") else 0, pinned=1 if f.get("epingle") else 0,
                                 event_date=f.get("date") or "", meta=meta)
            rep["ajoutees"].append(iid)
            if progress and n % 10 == 0:
                progress(f"Import en lot : {n} fiche(s)…")
        except Exception as ex:
            rep["erreurs"].append(f"fiche {f.get('titre')!r} : {ex}")
    logger.info("import en lot « %s » : %d ajoutée(s), %d sautée(s), %d erreur(s)", lot, len(rep["ajoutees"]),
                len(rep["sautees"]), len(rep["erreurs"]))
    return rep


def remove_lot(store: Store, lot: str) -> int:
    """Envoie a la corbeille (restaurable) toutes les fiches d'un lot importe."""
    ids = [r["id"] for r in store.items_where("meta LIKE ?", (f'%"lot": "{lot}"%',)) if store.meta(r).get("lot") == lot]
    if ids:
        store.trash_items(ids)
    return len(ids)


def enrich_any(store: Store, iid: int, ocr: bool = False) -> None:
    it = store.item(iid)
    if not it:
        return
    try:
        if it["type"] in ("link", "video") and it.get("url") and not it.get("file"):
            enrich_link(store, iid)
        elif it.get("file"):
            enrich_file(store, iid, ocr=ocr)
    except Exception:
        logger.error("enrichissement %s : %s", iid, traceback.format_exc())


# ================================================================ export HTML autonome / ZIP
EXPORT_CSS = """
body{font-family:Segoe UI,Arial,sans-serif;background:#f4f6fb;color:#1b2333;margin:0}
header{background:#0000AA;color:#FFFF55;padding:18px 28px;font-family:Consolas,monospace}
header h1{margin:0;font-size:26px} header p{margin:4px 0 0;color:#55FFFF}
#q{margin:10px 0 0;padding:7px 10px;width:340px;max-width:90%;border:1px solid #55FFFF;background:#000055;color:#fff;font-family:Consolas}
main{max-width:1000px;margin:0 auto;padding:18px}
nav{background:#fff;border:1px solid #d5dbe8;border-radius:8px;padding:10px 18px;margin-bottom:18px}
nav a{color:#0b3d91;text-decoration:none} nav li{margin:2px 0}
h2.subj{border-left:8px solid var(--c,#0000AA);padding:4px 12px;background:#e8ecf7;border-radius:4px;margin-top:34px}
.item{background:#fff;border:1px solid #d5dbe8;border-radius:10px;padding:14px 18px;margin:12px 0;box-shadow:0 1px 3px #0001}
.item h3{margin:0 0 4px;font-size:19px} .meta{color:#5a6478;font-size:13px;margin-bottom:8px}
.tag{display:inline-block;background:#fff6c2;border:1px solid #e6d36a;border-radius:10px;padding:0 8px;margin-right:4px;font-size:12px}
.body{line-height:1.55;font-size:15px} .body .h1{font-size:24px;font-weight:bold;color:#0b3d91}
.body .h2{font-size:20px;font-weight:bold;color:#0b3d91} .body .h3{font-size:17px;font-weight:bold}
.body .quote,blockquote{border-left:4px solid #9fb3d9;padding-left:10px;color:#3d4a66;font-style:italic;display:inline-block}
code{background:#eef0f3;padding:0 4px;border-radius:3px} mark{background:#fff176}
.ref{color:#8B1FA9;font-weight:bold} a{color:#0645AD}
img.thumb{max-width:100%;max-height:420px;border-radius:6px;border:1px solid #ccd;display:block;margin:8px 0}
details{margin-top:8px} details pre{white-space:pre-wrap;background:#f7f8fb;padding:10px;border-radius:6px;max-height:420px;overflow:auto}
.cite{font-size:18px;font-style:italic;border-left:5px solid #FFAA33;padding:6px 14px;background:#fffaf0}
footer{color:#7a8499;font-size:12px;text-align:center;padding:24px}
"""
EXPORT_JS = """
document.getElementById('q').addEventListener('input',function(){var t=this.value.toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g,'');
document.querySelectorAll('.item').forEach(function(e){var s=e.textContent.toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g,'');e.style.display=(!t||s.indexOf(t)>=0)?'':'none';});});
"""


def _data_uri(path: str, max_bytes: int = 4_000_000) -> str:
    try:
        if os.path.getsize(path) > max_bytes:
            return ""
        mt = mimetypes.guess_type(path)[0] or "application/octet-stream"
        with open(path, "rb") as f:
            return f"data:{mt};base64," + base64.b64encode(f.read()).decode("ascii")
    except OSError:
        return ""


def export_subject(store: Store, sid: int, out_html: str, include_sub: bool = True, zip_media: bool = False,
                   item_ids: Optional[List[int]] = None) -> int:
    """HTML autonome (images integrees) ; zip_media=True : medias copies a cote (dossier medias/) pour un ZIP."""
    out_dir = os.path.dirname(os.path.abspath(out_html))
    media_out = os.path.join(out_dir, "medias")
    sids = [sid] + (store.descendants(sid) if include_sub else []) if sid else []
    root_name = store.subject_path(sid) if sid else "Sélection"
    n = 0
    toc, body = [], []

    def media_ref(rel: str, inline_ok: bool) -> str:
        p = Paths.abs(rel)
        if not p or not os.path.isfile(p):
            return ""
        if zip_media:
            os.makedirs(media_out, exist_ok=True)
            dst = unique_path(media_out, os.path.basename(p))
            shutil.copy2(p, dst)
            return "medias/" + urllib.parse.quote(os.path.basename(dst))
        if inline_ok:
            u = _data_uri(p)
            if u:
                return u
        return "file:///" + urllib.parse.quote(p.replace("\\", "/"), safe="/:")

    def render(it: Dict[str, Any]) -> str:
        m = store.meta(it)
        ic = TYPES.get(it["type"], TYPES["file"])["icon"]
        h = [f'<div class="item" id="i{it["id"]}"><h3>{ic} {html.escape(it.get("title") or "(sans titre)")}'
             f'{" ★" if it.get("fav") else ""}{" 📌" if it.get("pinned") else ""}</h3>']
        meta = [TYPES.get(it["type"], TYPES["file"])["label"], fmt_date(it.get("event_date") or it.get("created") or "", False)]
        if it.get("author"):
            meta.append("par " + html.escape(it["author"]))
        if it.get("source"):
            meta.append("source : " + _linkify_html(it["source"]))
        h.append('<div class="meta">' + " · ".join(x for x in meta if x) + "</div>")
        if it.get("tags"):
            h.append("<div>" + "".join(f'<span class="tag">#{html.escape(t)}</span>' for t in tag_list(it["tags"])) + "</div>")
        if it.get("url"):
            h.append(f'<p>🔗 <a href="{html.escape(it["url"], quote=True)}" target="_blank">{html.escape(it["url"])}</a></p>')
        img_rel = it.get("file") if it["type"] == "image" else (it.get("thumb") or "")
        if img_rel:
            src = media_ref(img_rel, True)
            if src:
                link = it.get("url") or src
                h.append(f'<a href="{html.escape(link, quote=True)}" target="_blank"><img class="thumb" src="{src}" alt=""></a>')
        if it.get("file") and it["type"] != "image":
            src = media_ref(it["file"], it["type"] in ("audio", "voice") and (m.get("size") or 0) < 8_000_000)
            if src:
                if it["type"] in ("audio", "voice"):
                    h.append(f'<audio controls src="{src}"></audio>')
                h.append(f'<p>📎 <a href="{html.escape(src, quote=True) if not src.startswith("data:") else "#"}" '
                         f'target="_blank">{html.escape(m.get("filename") or os.path.basename(it["file"]))}</a> '
                         f'({human_size(m.get("size"))})</p>')
        if m.get("description"):
            h.append(f"<p><em>{_linkify_html(m['description'])}</em></p>")
        runs = runs_from_any(it.get("body"))
        if runs:
            cls = "body cite" if it["type"] == "quote" else "body"
            h.append(f'<div class="{cls}">{runs_to_html(runs)}</div>')
        if it.get("extracted") and it["type"] not in ("link", "video"):
            lab = {"voice": "Transcription", "audio": "Transcription", "image": "Texte reconnu (OCR)"}.get(it["type"], "Texte extrait")
            h.append(f"<details><summary>{lab}</summary><pre>{html.escape(it['extracted'][:200000])}</pre></details>")
        h.append("</div>")
        return "\n".join(h)

    if item_ids:
        its = [store.item(i) for i in item_ids]
        its = [i for i in its if i]
        body.append("".join(render(i) for i in its))
        n = len(its)
    for s in sids:
        subj = store.subject(s)
        if not subj:
            continue
        its = sorted(store.items_in([s]), key=lambda i: (-int(i["pinned"] or 0), float(i["sort"] or 0)))
        depth = len(store.subject_path(s).split(" › ")) - len(root_name.split(" › "))
        toc.append(f'<li style="margin-left:{depth * 18}px"><a href="#s{s}">{html.escape(subj["icon"] or "📁")} '
                   f'{html.escape(subj["name"])}</a> ({len(its)})</li>')
        body.append(f'<h2 class="subj" id="s{s}" style="--c:{html.escape(subj["color"] or "#0000AA")}">'
                    f'{html.escape(subj["icon"] or "📁")} {html.escape(store.subject_path(s))}</h2>')
        if subj.get("description"):
            body.append(f"<p>{_linkify_html(subj['description'])}</p>")
        for it in its:
            body.append(render(it))
            n += 1
    doc = f"""<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Grimoire — {html.escape(root_name)}</title>
<style>{EXPORT_CSS}</style></head><body>
<header><h1>📖 Grimoire — {html.escape(root_name)}</h1><p>{n} fiche(s) · exporté le {fmt_date(now_iso())}</p>
<input id="q" placeholder="Filtrer…" autocomplete="off"></header><main>
{('<nav><b>Sommaire</b><ul>' + ''.join(toc) + '</ul></nav>') if len(toc) > 1 else ''}
{''.join(body)}
</main><footer>Exporté depuis le Grimoire du Projet Padawan</footer><script>{EXPORT_JS}</script></body></html>"""
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(doc)
    return n


def export_subject_zip(store: Store, sid: int, out_zip: str, include_sub: bool = True) -> int:
    tmp = tempfile.mkdtemp(prefix="grim_zip_")
    try:
        n = export_subject(store, sid, os.path.join(tmp, "index.html"), include_sub, zip_media=True)
        with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
            for root, _d, files in os.walk(tmp):
                for f in files:
                    fp = os.path.join(root, f)
                    z.write(fp, os.path.relpath(fp, tmp))
        return n
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
