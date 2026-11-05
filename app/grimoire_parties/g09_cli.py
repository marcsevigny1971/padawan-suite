# -*- coding: utf-8 -*-
# Partie de grimoire1.py (découpage v1.2.2, comportement inchangé).
# Chargée par grimoire1.py dans un espace de noms commun : ne pas lancer seule.
from __future__ import annotations



# ================================================================ aide
HELP_TEXT = """# 📖 Grimoire : ton carnet de recherche

Le Grimoire garde TOUT ce que tu trouves, classé par sujets : notes, liens, vidéos, citations, pages web, images, documents, sons, mémos vocaux et fichiers. Tout est enregistré automatiquement, rien à sauvegarder à la main.

## Les trois colonnes
  Gauche : les sujets (et sous-sujets) + les vues spéciales : Tout, Favoris, Épinglés, Récents, Étiquettes, Corbeille.
  Centre : les fiches du sujet choisi, en Liste ☰, en Cartes ▦ (vignettes) ou en Chronologie 🕘 (par mois).
  Droite : la fiche choisie : Aperçu (miniature, lien, lecteur, texte extrait), Notes (texte riche), Fiche (source, dates, références).

## Ajouter quelque chose
  ＋ Ajouter : note, fiche à partir d'un modèle, lien, citation, image, document, son, vidéo, fichier, mémo vocal, page web.
  Ctrl+V (hors zone de texte) : colle intelligemment un lien (titre et miniature récupérés), du texte (note),
     une image copiée (capture d'écran) ou des fichiers copiés dans l'Explorateur.
  Glisser-déposer : des fichiers, des liens ou du texte depuis l'Explorateur ou le navigateur, sur la liste ou sur un sujet.
  Ce qui est ajouté va dans le sujet ouvert (sinon dans « À classer »).

## Les sujets
  Clic droit sur un sujet : sous-sujet, renommer (F2), icône, couleur, épingler, monter/descendre, ranger dans, fusionner,
     exporter, importer un dossier, supprimer (corbeille).
  Glisse un sujet sur un autre pour le ranger dedans ; Maj en lâchant = le placer avant ; dans le vide = niveau principal.
  Glisse des fiches sur un sujet pour les déplacer (Ctrl en lâchant = copier), sur ★ Favoris, 📌 Épinglés ou 🗑 Corbeille.
  Tous les sujets de départ sont renommables et supprimables.

## Les notes
  Barre d'outils : G gras, I italique, S̲ souligné, B̶ barré, T1/T2/T3 titres, ¶ normal, • puces, 1. numéros, ☐ cases à cocher
     (clic pour cocher), ❝ bloc citation, </> code, 🖍 surligner, 🔗 lien, [[ ]] référence, 📅 date du jour, 🧹 effacer le style.
  Les liens tapés deviennent cliquables tout seuls. [[Titre d'une fiche]] ou [[Nom d'un sujet]] crée un lien interne cliquable.
  L'onglet Fiche montre les références sortantes et les fiches qui citent celle-ci (rétroliens).
  Modèles : Source, Protocole, Plante médicinale, Recette, Livre/vidéo/article, Journal de recherche, Idée/projet,
     Expérience, Fait/événement, Personne. Tu peux enregistrer tes propres modèles (clic droit → Outils).

## Rechercher
  Ctrl+F : recherche instantanée dans tout : titres, notes, étiquettes, sources, liens, texte des PDF et documents,
     texte des pages capturées, texte lu dans les images (OCR) et mémos transcrits. Accents et majuscules ignorés.
  Plusieurs mots = fiches qui contiennent tous les mots ; « plant » trouve aussi « plantes ».
  Filtres : type, étiquette, période, « Partout » ou « Dans ce sujet ». Les mots trouvés sont surlignés.
  Ctrl+G : aller directement à un sujet ou une fiche en tapant quelques lettres.

## Outils de chercheur
  Citation ❝ : texte + auteur + source + page + lien + date ; « Copier avec la source » la met en forme.
  Capturer une page 🌐 : copie hors ligne complète (HTML + PDF + image pleine page) : la page reste même si le site disparaît.
  OCR 🔤 : lit le texte des images (moteur de Windows) pour le rendre cherchable (automatique au choix, menu Outils).
  Mémo vocal 🎙 : enregistre au micro ; transcription locale avec faster-whisper si installé (menu Outils).
  Date de l'info (onglet Fiche) : la date de l'événement ou de la publication, utilisée par la Chronologie.
  Mode lecture 📖 (F11) : grand texte confortable, fiche après fiche (◀ ▶).
  Statistiques 📊 : nombre de fiches par type, par sujet, par mois, étiquettes.
  Exporter : un sujet en page HTML autonome (images intégrées, filtre) ou en ZIP avec tous les fichiers.
  Envoyer à l'Archiveur 📦 : pour les vidéos, copie le lien et ouvre l'Archiveur 5 pour la télécharger.

## Raccourcis clavier
  Ctrl+N : nouvelle note            Ctrl+Maj+N : nouveau sujet          Ctrl+L : lien web
  Ctrl+Maj+Q : citation             Ctrl+R : mémo vocal                 Ctrl+O : fichier(s)
  Ctrl+Maj+I : image(s)             Ctrl+V : coller intelligent         Ctrl+Maj+V : coller comme note
  Ctrl+F : rechercher               Ctrl+G : aller à…                   Échap : quitter la recherche
  Ctrl+1 / 2 / 3 : liste / cartes / chronologie                         F11 : mode lecture
  Ctrl+D : favori ★                 Ctrl+P : épingler 📌                Ctrl+T : étiquettes
  Ctrl+M : déplacer vers…           Alt+Haut / Alt+Bas : monter / descendre (fiche ou sujet)
  F2 : renommer                     Suppr : corbeille                   Ctrl+Z : annuler suppression / déplacement
  Ctrl+A : tout sélectionner        Ctrl+clic / Maj+clic : sélection multiple
  Ctrl+Maj+E : exporter le sujet    Ctrl+S : copie de sauvegarde datée  F5 : rafraîchir
  Ctrl++ / Ctrl+- / Ctrl+0 : taille du texte (aussi Ctrl+molette)       F1 : cette aide
  Dans une note : Ctrl+B gras, Ctrl+I italique, Ctrl+U souligné, Ctrl+1/2/3 titres, Ctrl+0 normal, Ctrl+K lien,
     Ctrl+Maj+X barré, Ctrl+Maj+8 puces, Entrée continue la liste, Échap revient à la liste.
  Dans la liste : tape une lettre pour lancer la recherche, Entrée pour ouvrir.

## Données et sécurité
  Tout est dans C:\\web\\FTP_HOME\\GRIMOIRE\\ : grimoire.db (la base), medias\\ (les fichiers copiés, un dossier par sujet),
     _sauvegardes\\ (copies automatiques de la base : au démarrage, toutes les 6 h et à la fermeture, 30 gardées),
     exports\\ et grimoire.log (journal).
  Les fichiers ajoutés sont COPIÉS dans le Grimoire : l'original peut être déplacé ou effacé sans rien perdre.
  Corbeille : rien n'est effacé tant que tu ne vides pas la corbeille. Fichier → Restaurer une sauvegarde au besoin.

## Ligne de commande (pour les autres programmes Padawan)
  grimoire1.py --ajouter "https://..." --sujet "Santé/Protocoles" --titre "..." --note "..." --etiquettes "a, b"
  grimoire1.py --ajouter "C:\\chemin\\fichier.pdf"      grimoire1.py --ajouter "Une idée" --type citation --auteur "X"
  Si le Grimoire est ouvert, l'ajout arrive tout de suite dedans ; sinon il est enregistré directement.
  --check : vérification complète    --smoke : test automatique    --montrer : ramener la fenêtre
  --importer-lot fichier.json : import de fiches riches en lot    --retirer-lot NOM : retire un lot (corbeille)
"""


# ================================================================ verification
def check_report(store: Store) -> str:
    L = ["# 🔎 Vérification du Grimoire", ""]
    L.append(f"  Dossier : {Paths.data}")
    L.append(f"  Intégrité SQLite : {store.integrity()}")
    st = store.stats()
    L.append(f"  Fiches : {st['items']}  ·  sujets : {st['subjects']}  ·  corbeille : {st['trash']}")
    if store.fts_ok:
        nf = store.q("SELECT COUNT(*) n FROM fts")[0]["n"]
        L.append(f"  Index de recherche : {nf} entrée(s) pour {st['items']} fiche(s)"
                 + ("" if nf == st["items"] else "  ⚠ écart (menu Outils → Reconstruire l'index)"))
    else:
        L.append("  Index de recherche : FTS5 indisponible (recherche simple)")
    missing = []
    for r in store.q("SELECT id,title,file,thumb FROM items WHERE deleted IS NULL AND (file<>'' OR thumb<>'')"):
        for k in ("file", "thumb"):
            if r[k] and not os.path.isfile(Paths.abs(r[k])):
                missing.append(f"    #{r['id']} {r['title'][:50]} : {k} {r[k]}")
    L.append(f"  Fichiers manquants : {len(missing)}")
    L += missing[:30]
    orphans = store.q("SELECT COUNT(*) n FROM items WHERE deleted IS NULL AND subject_id NOT IN "
                      "(SELECT id FROM subjects WHERE deleted IS NULL)")[0]["n"]
    L.append(f"  Fiches sans sujet : {orphans}" + ("  ⚠ (Ctrl+Z / restaurer, ou elles apparaissent dans Tout)" if orphans else ""))
    bk = sorted(glob.glob(os.path.join(Paths.backups(), "grimoire_*.db")))
    L.append(f"  Sauvegardes : {len(bk)}" + (f"  (dernière : {os.path.basename(bk[-1])})" if bk else ""))
    L += ["", "## Modules et outils"]
    for mod, why in (("PIL", "images, vignettes, Ctrl+V d'images"), ("requests", "liens web"), ("pypdf", "texte des PDF"),
                     ("tkinterdnd2", "glisser-déposer depuis l'Explorateur"), ("sounddevice", "micro (mémos vocaux)"),
                     ("soundfile", "enregistrement FLAC"), ("bs4", "texte des pages web (facultatif)"),
                     ("faster_whisper", "transcription des mémos (facultatif)")):
        L.append(f"  {mod:<15} {'OK' if module_ok(mod) else 'absent'}   ({why})")
    try:
        devs, _d, err = Recorder.devices()
        L.append(f"  Micro            {len(devs)} entrée(s) audio" + (f"  ({err})" if err and not devs else ""))
    except Exception as ex:
        L.append(f"  Micro            erreur : {ex}")
    L.append(f"  ffplay           {find_ff_tool('ffplay') or 'introuvable (lecture audio par Windows)'}")
    L.append(f"  ffmpeg           {find_ffmpeg() or 'introuvable (pas de vignettes de vidéos locales)'}")
    L.append(f"  Navigateur       {find_browser() or 'introuvable (pas de PDF/image des pages capturées)'}")
    try:
        o = ocr_available()
        L.append(f"  OCR Windows      {o or 'indisponible'}")
    except Exception as ex:
        L.append(f"  OCR Windows      erreur : {ex}")
    L.append(f"  Python           {sys.version.split()[0]}  ({sys.executable})")
    return "\n".join(L)


# ================================================================ instance unique, captures, tests
def _focus_existing() -> bool:
    if not IS_WIN:
        return False
    try:
        u32 = ctypes.windll.user32
        hwnd = u32.FindWindowW("TkTopLevel", APP_TITLE)
        if hwnd:
            cmd = 9 if u32.IsIconic(hwnd) else (3 if u32.IsZoomed(hwnd) else 5)
            u32.ShowWindow(hwnd, cmd)
            u32.ShowWindow(hwnd, cmd)
            u32.mouse_event(0x0001, 0, 0, 0, 0)
            u32.BringWindowToTop(hwnd)
            u32.SetForegroundWindow(hwnd)
            return True
    except Exception:
        pass
    return False


def _mutex_exists() -> bool:
    if not IS_WIN:
        return False
    k32 = ctypes.windll.kernel32
    k32.OpenMutexW.restype = wintypes.HANDLE
    h = k32.OpenMutexW(0x00100000, False, _MUTEX_NAME)   # SYNCHRONIZE
    if h:
        k32.CloseHandle(h)
        return True
    return False


def _single_instance():
    if not IS_WIN:
        return True, None
    k32 = ctypes.windll.kernel32
    k32.CreateMutexW.restype = wintypes.HANDLE
    h = k32.CreateMutexW(None, False, _MUTEX_NAME)
    if ctypes.GetLastError() == 183:
        return False, h
    return True, h


def take_shot(app: "GrimoireApp", path: str) -> bool:
    try:
        from PIL import ImageGrab  # type: ignore
    except ImportError:
        logger.error("capture : Pillow absent")
        return False
    wins = [app] + [w for w in app.winfo_children() if isinstance(w, tk.Toplevel) and w.winfo_viewable()]
    for w in wins:
        try:
            w.attributes("-topmost", True)
            w.lift()
        except tk.TclError:
            pass
    app.update()
    time.sleep(0.4)
    app.update()
    try:
        full = ImageGrab.grab()
    except Exception as ex:
        logger.error("capture : %s", ex)
        return False
    for w in wins:
        try:
            w.attributes("-topmost", False)
        except tk.TclError:
            pass
    f = full.width / max(1, app.winfo_screenwidth())
    x, y = app.winfo_rootx(), app.winfo_rooty()
    w, h = app.winfo_width(), app.winfo_height()
    img = full.crop((int(x * f), int(y * f), int((x + w) * f), int((y + h) * f)))
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    img.save(path)
    logger.info("capture %s (%dx%d, facteur %.2f)", path, img.width, img.height, f)
    return True


def _first_item(app: "GrimoireApp", name: str, typ: str = "") -> Optional[int]:
    for r in app.store.items_where("1=1"):
        if (not name or norm(r["title"]) == norm(name)) and (not typ or r["type"] == typ):
            return r["id"]
    return None


def run_shot(app: "GrimoireApp", path: str, view: str) -> None:
    st = app.store

    def subj(name):
        return st.find_subject(name)

    def step1():
        try:
            pm = subj("Plantes médicinales")
            if view in ("cartes", "lien"):
                for r in st.items_where("type IN ('link','video')"):
                    if st.meta(r).get("pending", True) and not st.meta(r).get("fetched"):
                        enrich_any(st, r["id"])
            if view in ("main", "cartes", "chrono", "lien", "image", "citation"):
                app.open_view(f"s:{pm}" if pm else "v:all")
                app.set_view_mode({"cartes": "cards", "chrono": "chrono"}.get(view, "list"))
                target = {"main": _first_item(app, "Échinacée", "note"), "lien": _first_item(app, "", "link"),
                          "citation": _first_item(app, "", "quote"), "cartes": _first_item(app, "", "video"),
                          "chrono": _first_item(app, "Tisane du soir"), "image": _first_item(app, "", "image")}.get(view)
                if target:
                    app.select_ids([target], see=True)
            elif view == "accueil":
                app.set_view_mode("list")
                b = subj("Bienvenue")
                app.open_view(f"s:{b}")
                it = _first_item(app, "Comment utiliser le Grimoire")
                if it:
                    app.select_ids([it])
            elif view == "sujet":
                app.set_view_mode("list")
                app.open_view(f"s:{subj('Santé')}")
            elif view == "recherche":
                app.set_view_mode("list")
                app.v_search.set("echinacee")
                app.do_search()
                if app.results:
                    app.select_ids([app.results[0]["id"]])
            elif view == "lecture":
                app.open_view(f"s:{pm}")
                it = _first_item(app, "Échinacée", "note")
                if it:
                    app.select_ids([it])
                app.open_reader()
            elif view == "memo":
                app.open_view(f"s:{pm}")
                RecorderDialog(app, pm)
            elif view == "aide":
                app.show_help()
            elif view == "stats":
                app.show_stats()
            elif view == "corbeille":
                app.open_view("v:trash")
            elif view == "palette":
                Palette(app, "goto")
            elif view == "sujetdlg":
                SubjectDialog(app, app, "Nouveau sujet", None, subj("Santé"))
            elif view == "citationdlg":
                QuoteDialog(app, "")
            elif view == "liendlg":
                LinkDialog(app, app, "https://www.youtube.com/watch?v=aqz-KE-bpKQ")
            elif view == "verif":
                app.check_dialog()
            elif view == "carte":
                app.open_mindmap()
            elif view == "cartes2":
                app.open_view("v:all")
                app.set_view_mode("cards")
            elif view == "liens":
                app.open_view("v:all")
                app.set_view_mode("cards")
                tgt = os.environ.get("GX_SHOT_ITEM")
                if tgt:
                    app.select_ids([int(tgt)], see=True)
        except Exception:
            logger.error("capture %s : %s", view, traceback.format_exc())
        app.after(1800 if view != "verif" else 4000, step2)

    def step2():
        take_shot(app, path)
        app.after(150, app.destroy)
    app.after(1600, step1)


def run_smoke(app: "GrimoireApp") -> int:
    errors: List[str] = []
    st = app.store
    try:
        app.update()
        for key, _i, _l in SPECIAL_VIEWS:
            app.open_view(key)
            app.update()
        for sid in app.subject_order():
            app.open_view(f"s:{sid}")
            app.update()
            if app.visible:
                app.select_ids([app.visible[0]["id"]])
                app.update()
        for mode in ("cards", "chrono", "list"):
            app.set_view_mode(mode)
            app.update()
        pm = st.find_subject("Plantes médicinales")
        app.open_view(f"s:{pm}")
        app.update()
        # note
        app.new_note(template="Recette")
        app.update()
        iid = app.cur_item
        app.editor.t.insert("end", "\nzorglub magique [[Échinacée]] https://exemple.org")
        app.editor.flush()
        app.update()
        it = st.item(iid)
        if not it or "zorglub" not in (it.get("body_text") or ""):
            errors.append("note : texte non enregistré")
        app.v_tags.set("test, smoke")
        app._tags_commit()
        if "smoke" not in (st.item(iid) or {}).get("tags", ""):
            errors.append("étiquettes non enregistrées")
        # recherche
        app.v_search.set("zorglub")
        app.do_search()
        app.update()
        if not any(r["id"] == iid for r in app.results):
            errors.append("recherche : note zorglub introuvable")
        app.v_search.set("echinacee")
        app.do_search()
        app.update()
        if not app.results:
            errors.append("recherche sans accent : échinacée introuvable")
        app.clear_search()
        app.update()
        # citation, lien hors ligne
        q = add_quote(st, pm, "Le savoir est une arme.", "Anonyme", "Test")
        app._after_add([q], pm, enrich=False)
        app.update()
        app.copy_citation(q)
        # corbeille + annuler
        n0 = st.stats()["items"]
        app.select_ids([iid, q])
        app.delete_selected()
        app.update()
        if st.stats()["items"] != n0 - 2:
            errors.append("corbeille : suppression incorrecte")
        app.do_undo()
        app.update()
        if st.stats()["items"] != n0:
            errors.append("annuler : restauration incorrecte")
        # deplacer + annuler
        other = st.find_subject("Recettes")
        app.select_ids([iid])
        app.move_selected(False, other)
        if (st.item(iid) or {}).get("subject_id") != other:
            errors.append("déplacement incorrect")
        app.do_undo()
        if (st.item(iid) or {}).get("subject_id") != pm:
            errors.append("annuler le déplacement incorrect")
        # sujets
        sid = st.add_subject("Sujet smoke", pm, "🧪", "#55FF55")
        app.refresh_tree()
        app.open_view(f"s:{sid}")
        app.update()
        b = st.trash_subject(sid)
        st.restore_batch(b)
        st.trash_subject(sid)
        app.refresh_all()
        app.open_view("v:trash")
        app.update()
        # dialogues
        for maker in (lambda: TextDialog(app, "Aide", HELP_TEXT), lambda: SubjectDialog(app, app, "Test"),
                      lambda: LinkDialog(app, app, "https://exemple.org"), lambda: QuoteDialog(app, "x"),
                      lambda: EmojiPicker(app, "📖"), lambda: SubjectChooser(app, app, "Test", "Choisir"),
                      lambda: RecorderDialog(app, pm), lambda: Palette(app, "goto")):
            d = maker()
            app.update()
            d.destroy()
        app.show_stats()
        app.update()
        ReaderWindow(app, [iid, q], 0).destroy()
        # export
        out = os.path.join(Paths.exports(), "smoke_export.html")
        os.makedirs(Paths.exports(), exist_ok=True)
        n = export_subject(st, pm, out)
        if n < 1 or not os.path.isfile(out):
            errors.append("export HTML vide")
        app.zoom(1)
        app.update()
        app.zoom(0)
        app.update()
        app.v_theme.set("clair")
        app.change_theme()
        app.update()
        app.v_theme.set("norton")
        app.change_theme()
        app.update()
        app.open_view(f"s:{pm}")
        app.set_view_mode("cards")
        app.update()
        app.set_view_mode("list")
        if st.integrity() != "ok":
            errors.append("intégrité : " + st.integrity())
    except Exception:
        errors.append(traceback.format_exc())
    s = st.stats()
    print(f"SMOKE {'OK' if not errors else 'ERREURS'} : {s['items']} fiches, {s['subjects']} sujets, données {Paths.data}")
    for er in errors:
        print("ERREUR:", er)
    logger.info("smoke : %s", "OK" if not errors else f"{len(errors)} erreur(s)")
    return 0 if not errors else 1


# ================================================================ ligne de commande
def cli_add(args) -> int:
    payload = {"ajouter": args.ajouter, "sujet": args.sujet, "titre": args.titre, "note": args.note,
               "etiquettes": args.etiquettes, "source": args.source, "type": args.type, "auteur": args.auteur,
               "url": args.url}
    payload = {k: v for k, v in payload.items() if v}
    val = payload["ajouter"].strip().strip('"')
    if len(val) < 600 and os.path.exists(val):
        payload["ajouter"] = os.path.abspath(val)
    if _mutex_exists():
        os.makedirs(Paths.inbox(), exist_ok=True)
        fp = os.path.join(Paths.inbox(), f"{dt.datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{uuid.uuid4().hex[:6]}.json")
        tmp = fp + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        os.replace(tmp, fp)
        print(f"Envoyé au Grimoire ouvert : {fp}")
        logger.info("--ajouter → inbox %s", fp)
        return 0
    st = Store().open()
    try:
        seed_content(st)
        ids = process_payload(st, payload)
        for iid in ids:
            enrich_any(st, iid)
        for iid in ids:
            it = st.item(iid)
            print(f"Ajouté #{iid} [{it['type']}] « {it['title']} » dans {st.subject_path(it['subject_id'])}")
        logger.info("--ajouter direct : %d fiche(s)", len(ids))
        return 0 if ids else 2
    finally:
        st.close()


def cli_lot(args) -> int:
    fp = os.path.abspath(args.importer_lot)
    with open(fp, "r", encoding="utf-8") as f:
        data = json.load(f)
    if _mutex_exists():
        os.makedirs(Paths.inbox(), exist_ok=True)
        dst = os.path.join(Paths.inbox(), f"lot_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}.json")
        with open(dst + ".tmp", "w", encoding="utf-8") as f:
            json.dump({"action": "lot", "fichier": fp}, f, ensure_ascii=False)
        os.replace(dst + ".tmp", dst)
        print(f"Grimoire ouvert : lot envoyé par la boîte de réception ({dst})")
        return 0
    st = Store().open()
    try:
        seed_content(st)
        st.backup(force=True, tag="avant_lot")
        rep = import_lot(st, data, progress=print)
        print(f"Lot « {rep['lot']} » : {len(rep['ajoutees'])} fiche(s) ajoutée(s), {len(rep['sautees'])} déjà présente(s), "
              f"{rep['sujets_crees']} sujet(s) créé(s), {len(rep['erreurs'])} erreur(s)")
        for e in rep["erreurs"]:
            print("ERREUR:", e)
        return 0 if not rep["erreurs"] else 1
    finally:
        st.close()


def cli_remove_lot(args) -> int:
    if _mutex_exists():
        print("Ferme d'abord le Grimoire (ou utilise la corbeille dans l'interface).")
        return 2
    st = Store().open()
    try:
        st.backup(force=True, tag="avant_retrait_lot")
        n = remove_lot(st, args.retirer_lot)
        print(f"{n} fiche(s) du lot « {args.retirer_lot} » envoyée(s) à la corbeille (restaurables).")
        return 0
    finally:
        st.close()


def cli_check(_args) -> int:
    st = Store().open()
    try:
        print(check_report(st))
        return 0 if st.integrity() == "ok" else 1
    finally:
        st.close()


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Grimoire - carnet de recherche par sujets (Projet Padawan)")
    ap.add_argument("--smoke", action="store_true", help="test automatique de l'interface puis sortie")
    ap.add_argument("--check", action="store_true", help="vérification de la base, des fichiers et des modules")
    ap.add_argument("--shot", default="", help="capture PNG de la fenêtre puis sortie")
    ap.add_argument("--shot-view", default="main", help="main|cartes|chrono|recherche|lecture|memo|sujet|aide|stats|accueil|"
                                                         "lien|citation|corbeille|palette|sujetdlg|citationdlg|liendlg|verif")
    ap.add_argument("--geometry", default="", help="ex. 1280x720+0+0 (sinon plein écran)")
    ap.add_argument("--data", default="", help="autre dossier de données (tests)")
    ap.add_argument("--demo", action="store_true", help="ajoute des fiches d'exemple (dossier de test seulement)")
    ap.add_argument("--ajouter", default="", help="texte, lien ou fichier à ajouter")
    ap.add_argument("--sujet", default="", help="sujet de destination (« Santé/Protocoles »), sinon « À classer »")
    ap.add_argument("--titre", default="")
    ap.add_argument("--note", default="")
    ap.add_argument("--etiquettes", default="")
    ap.add_argument("--source", default="")
    ap.add_argument("--auteur", default="")
    ap.add_argument("--url", default="", help="lien de la source (citation)")
    ap.add_argument("--type", default="", help="citation : ajoute le texte comme citation")
    ap.add_argument("--montrer", action="store_true", help="ramène la fenêtre du Grimoire")
    ap.add_argument("--make-icons", action="store_true", help="génère grimoire1.ico/.png puis sortie")
    ap.add_argument("--importer-lot", default="", help="importe un lot de fiches (JSON : sujets, fiches riches, étiquettes)")
    ap.add_argument("--retirer-lot", default="", help="envoie à la corbeille les fiches d'un lot importé (par son nom)")
    args = ap.parse_args(argv)
    if args.data:
        Paths.set(args.data)
    setup_logging()
    if IS_WIN:
        for s in (sys.stdout, sys.stderr):
            try:
                s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
            except Exception:
                pass
    if args.make_icons:
        print(generate_app_icons(BASE, force=True))
        return 0
    if args.check:
        return cli_check(args)
    if args.importer_lot:
        try:
            return cli_lot(args)
        except Exception:
            logger.error("--importer-lot : %s", traceback.format_exc())
            print(traceback.format_exc())
            return 1
    if args.retirer_lot:
        return cli_remove_lot(args)
    if args.ajouter:
        try:
            return cli_add(args)
        except Exception:
            logger.error("--ajouter : %s", traceback.format_exc())
            print(traceback.format_exc())
            return 1
    if tk is None:
        print("tkinter est requis")
        return 1
    special = args.smoke or bool(args.shot)
    mutex = None
    if not special:
        ok, mutex = _single_instance()
        if not ok:
            if not _focus_existing():
                try:
                    os.makedirs(Paths.inbox(), exist_ok=True)
                    with open(os.path.join(Paths.inbox(), f"montrer_{uuid.uuid4().hex[:6]}.json"), "w", encoding="utf-8") as f:
                        json.dump({"action": "montrer"}, f)
                except OSError:
                    pass
            return 0
    elif args.montrer:
        return 0
    try:
        generate_app_icons(BASE)
    except Exception:
        logger.info("icônes : %s", traceback.format_exc())
    try:
        app = GrimoireApp(args)
    except Exception:
        logger.error("démarrage : %s", traceback.format_exc())
        if not special and tk is not None:
            try:
                r = tk.Tk()
                r.withdraw()
                messagebox.showerror(APP_NAME, "Le Grimoire n'a pas pu démarrer :\n\n" + traceback.format_exc()[-1500:]
                                     + f"\n\nJournal : {Paths.log()}")
                r.destroy()
            except Exception:
                pass
        raise

    def report(*a):
        logger.error("erreur Tk : %s", "".join(traceback.format_exception(*a)))
        try:
            app.set_status("⚠ Une erreur s'est produite (détails dans grimoire.log) : " + str(a[1])[:120], "ERR")
        except Exception:
            pass
    app.report_callback_exception = report
    if args.smoke:
        app.update()
        code = run_smoke(app)
        try:
            app.store.close()
        except Exception:
            pass
        app.destroy()
        return code
    if args.shot:
        run_shot(app, args.shot, args.shot_view)
    try:  # v1.2.3 : themes communs de la suite (menu/bouton « 🎨 Thème », Ctrl+Maj+T)
        import padawan_themes as _pt
        _pt.install(app, "grimoire", C)
    except Exception:
        pass
    app.mainloop()
    _ = mutex
    return 0
