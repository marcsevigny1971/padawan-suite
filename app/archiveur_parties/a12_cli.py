# -*- coding: utf-8 -*-
# Partie de archiveur5.py (découpage v1.2.2, comportement inchangé).
# Chargée par archiveur5.py dans un espace de noms commun : ne pas lancer seule.
from __future__ import annotations



# ================================================================= CLI
def _cli_log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    logger.info(msg)
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("ascii", "replace").decode("ascii"), flush=True)


def _cli_ensure_ytdlp() -> bool:
    if ensure_ytdlp(_cli_log, ask_install=True, parent=None):
        return True
    try:
        import yt_dlp  # noqa: F401
        return True
    except ImportError:
        _cli_log("Impossible d'importer yt_dlp")
        return False


def run_cli(urls: List[str], root: Optional[str] = None, cookies_browser: Optional[str] = None,
            quality: Optional[str] = None, subtitles: Optional[bool] = None, storyboard: bool = True,
            tags: str = "", notes: str = "", force: bool = False, page_mode: bool = False) -> int:
    cfg = load_cfg()
    archive_root = root or cfg.get("archive_root") or DEFAULT_ROOT
    os.makedirs(archive_root, exist_ok=True)
    quality = quality or cfg.get("quality") or "best"
    subtitles = cfg.get("subtitles", True) if subtitles is None else subtitles
    if not _cli_ensure_ytdlp():
        return 2
    _cli_log(f"ffmpeg: {find_ffmpeg() or 'non'}")
    entries = sync_index_with_disk(archive_root)
    rc = 0
    for url in urls:
        dups = find_duplicates(entries, url)
        if dups and not force:
            _cli_log(f"DOUBLON: déjà archivé ({len(dups)}x) -> {dups[0].get('folder')} — ajoutez --force pour re-archiver")
            print(json.dumps({"duplicate": True, "folder": dups[0].get("folder")}, ensure_ascii=False))
            continue
        try:
            info = archive_url(url, archive_root, _cli_log, cookies_browser=cookies_browser,
                               quality=quality, subtitles=bool(subtitles), storyboard=storyboard,
                               tags=parse_tags(tags), notes=notes, page_mode=page_mode,
                               web_capture=bool(cfg.get("web_capture", True)),
                               use_fx=bool(cfg.get("x_fxtwitter", True)),
                               auto_convert=bool(cfg.get("auto_convert", True)))
            entry = register_archive(archive_root, info)
            entries = load_archive_index(archive_root)
            _cli_log(f"OK folder={entry['folder']} method={entry.get('method')}")
            print(json.dumps(entry, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.exception("CLI %s", url)
            _cli_log(f"FAIL: {friendly_error(e)}")
            traceback.print_exc()
            rc = 1
    return rc


def _run_v5_cli(args, root: str) -> Optional[int]:
    """Commandes v5 en ligne de commande. None = rien à faire ici (suite normale)."""
    if args.verify:
        rep = verify_archives(root, check_media=not args.no_media_check,
                              progress=lambda i, n, f: None)
        issues = rep["issues"]
        _cli_log(f"Vérification : {rep['checked']} archive(s) vérifiée(s), {len(issues)} problème(s).")
        for it in issues:
            print(f"  [{it['kind']}] {it['folder']} — {it['label']}" + (f" : {it['detail']}" if it.get("detail") else "")
                  + f"  → {it['fix']}" + (" (auto)" if it.get("auto") else ""), flush=True)
        if args.repair and issues:
            st = repair_archives(root, [x for x in issues if x.get("auto")], _cli_log)
            _cli_log(f"Réparation : {st['ok']} corrigé(s), {st['skip']} ignoré(s), {st['fail']} échec(s).")
            rep2 = verify_archives(root, check_media=False)
            _cli_log(f"Après réparation : {len(rep2['issues'])} problème(s) restant(s) (hors médias).")
        return 0 if not issues or args.repair else 1
    if args.check_online:
        entries = sync_index_with_disk(root)
        folders = args.folders or [str(e.get("folder")) for e in entries]
        counts = check_online_many(root, folders, progress=lambda d, n, f, s: _cli_log(f"{d}/{n} {ONLINE_ICONS.get(s, '')} {s:<10} {f}"))
        _cli_log("Résultat : " + ", ".join(f"{k}={v}" for k, v in counts.items()))
        return 0
    if args.export_zip:
        entries = sync_index_with_disk(root)
        folders = args.folders or [str(e.get("folder")) for e in entries]
        n, size = export_zip(root, folders, args.export_zip, progress=lambda i, t, f: _cli_log(f"{i}/{t} {f}"))
        _cli_log(f"ZIP : {args.export_zip} — {n} fichiers, {human_size(size)}")
        return 0
    if args.export_catalog:
        entries = sync_index_with_disk(root)
        n = export_catalog(entries, args.export_catalog)
        _cli_log(f"Catalogue : {n} ligne(s) → {args.export_catalog}")
        return 0
    if args.stats:
        st = compute_stats(sync_index_with_disk(root), root)
        print(json.dumps(st, ensure_ascii=False, indent=2, default=str))
        return 0
    if args.transcript or args.whisper or args.media_test:
        target = args.transcript or args.whisper or args.media_test
        fp = target if os.path.isabs(target) else os.path.join(root, target)
        if not os.path.isdir(fp):
            _cli_log(f"Dossier introuvable : {fp}")
            return 2
        if args.transcript:
            d = build_transcript(fp, force=True)
            if not d:
                _cli_log("Aucun sous-titre exploitable dans ce dossier.")
                return 1
            refresh_entries(root, [os.path.basename(fp)])
            _cli_log(f"Transcription : {len(d['cues'])} passages ({d.get('lang')}) → {TRANSCRIPT_TXT}")
            for t, x in d["cues"][:5]:
                print(f"  [{fmt_ts(t)}] {x}", flush=True)
            return 0
        if args.whisper:
            if not whisper_available():
                _cli_log("faster-whisper n'est pas installé (setup_padawan.bat → option Whisper).")
                return 2
            d = transcribe_whisper(fp, _cli_log, model_size=str(load_cfg().get("whisper_model") or "base"))
            refresh_entries(root, [os.path.basename(fp)])
            _cli_log(f"Whisper : {len(d['cues'])} passages ({d.get('lang')})")
            return 0
        main = find_main_media(fp)
        if not main or not main.lower().endswith(VIDEO_EXTS):
            _cli_log("Pas de vidéo dans ce dossier.")
            return 2
        dur = probe_duration(main) or 10
        a, b = min(1.0, dur / 4), min(dur, 1.0 + min(4.0, dur / 2))
        ok = True
        for label, fn in (("capture", lambda: media_capture(main, a, fp)),
                          ("extrait (copie)", lambda: media_clip(main, a, b, fp)),
                          ("extrait (précis)", lambda: media_clip(main, a, b, fp, precise=True)),
                          ("audio mp3", lambda: media_audio(main, fp)),
                          ("gif", lambda: media_gif(main, a, b, fp))):
            try:
                out = fn()
                rd, det = probe_readable(out) if not out.lower().endswith(".jpg") else (os.path.getsize(out) > 1000, "")
                _cli_log(f"{'OK ' if rd else 'KO '} {label:<18} {os.path.basename(out)} ({human_size(os.path.getsize(out))}) {det}")
                ok = ok and rd
            except Exception as ex:
                ok = False
                _cli_log(f"KO  {label:<18} {friendly_error(ex)}")
        return 0 if ok else 1
    return None


def main():
    setup_logging()
    parser = argparse.ArgumentParser(description="Archiveur 5 — posts X/FB/YouTube et pages web, archivés en local")
    parser.add_argument("--url", action="append", help="Mode CLI: archiver une URL (répétable)")
    parser.add_argument("--urls-file", help="Fichier texte de liens (un par ligne)")
    parser.add_argument("--root", help="Racine des archives")
    parser.add_argument("--cookies-browser", help="chrome|edge|firefox")
    parser.add_argument("--quality", choices=[k for k, _ in QUALITY_LABELS], help="best|720|480|audio")
    parser.add_argument("--subs", dest="subs", action="store_true", default=None, help="sous-titres FR/EN")
    parser.add_argument("--no-subs", dest="subs", action="store_false")
    parser.add_argument("--no-storyboard", action="store_true")
    parser.add_argument("--tags", default="", help="tags séparés par virgules")
    parser.add_argument("--notes", default="", help="notes perso")
    parser.add_argument("--force", action="store_true", help="re-archiver même si doublon")
    parser.add_argument("--reindex", action="store_true", help="régénérer index.html global + pages")
    parser.add_argument("--search", help="chercher dans l'historique (titre/texte/auteur/tags)")
    parser.add_argument("--platform", help="filtre plateforme pour --search")
    parser.add_argument("--sort", default="date_desc", choices=[k for k, _ in SORT_CHOICES])
    parser.add_argument("--smoke", type=float, default=0.0, help="test UI: ouvre, parcourt, ferme après N s")
    parser.add_argument("--fix-codecs", action="store_true",
                        help="convertir en MP4 H.264/AAC toutes les vidéos archivées non compatibles")
    parser.add_argument("--folder", help="avec --fix-codecs : un seul dossier d'archive")
    parser.add_argument("--geometry", default="", help="test UI : taille forcée, ex. 1024x576")
    parser.add_argument("--shot", default="", help="test UI : capture PNG de la fenêtre puis ferme")
    parser.add_argument("--dpi-aware", action="store_true", help="test UI : pixels physiques, échelle 100 %%")
    # v5
    parser.add_argument("--page", action="append", help="archiver une URL comme page web (lecture + capture + PDF)")
    parser.add_argument("--verify", action="store_true", help="vérifier l'intégrité des archives")
    parser.add_argument("--repair", action="store_true", help="avec --verify : appliquer les réparations sûres")
    parser.add_argument("--no-media-check", action="store_true", help="avec --verify : ne pas analyser les médias")
    parser.add_argument("--check-online", action="store_true", help="vérifier si les originaux sont en ligne")
    parser.add_argument("--export-zip", metavar="DEST", help="exporter en ZIP (toutes, ou --folder répétable)")
    parser.add_argument("--export-catalog", metavar="DEST", help="exporter le catalogue (.csv ou .json)")
    parser.add_argument("--transcript", metavar="FOLDER", help="(re)construire la transcription depuis les sous-titres")
    parser.add_argument("--whisper", metavar="FOLDER", help="transcrire localement avec Whisper (faster-whisper)")
    parser.add_argument("--media-test", metavar="FOLDER", help="tester les outils média sur une archive vidéo")
    parser.add_argument("--stats", action="store_true", help="statistiques des archives")
    parser.add_argument("--folders", action="append", help="dossier(s) d'archive pour --check-online / --export-zip")
    parser.add_argument("--wait-lock", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--font-delta", type=int, default=None, help="test UI : taille du texte (-3 à 8)")
    parser.add_argument("--shot-action", default="", help="test UI : play|settings|help|stats|verify|media|multi|transcript[@dossier]")
    args = parser.parse_args()
    root = args.root or load_cfg().get("archive_root") or DEFAULT_ROOT
    rc = _run_v5_cli(args, root)
    if rc is not None:
        raise SystemExit(rc)
    if args.fix_codecs:
        if not find_ffmpeg():
            _cli_log("ffmpeg introuvable.")
            raise SystemExit(2)
        if args.folder:
            fp = args.folder if os.path.isabs(args.folder) else os.path.join(root, args.folder)
            try:
                r = fix_folder_codecs(fp, _cli_log)
                _cli_log(f"{os.path.basename(fp)} : {r}")
                raise SystemExit(0)
            except SystemExit:
                raise
            except Exception as ex:
                _cli_log(f"ÉCHEC : {friendly_error(ex)}")
                raise SystemExit(1)
        st = fix_codecs_all(root, _cli_log)
        _cli_log(f"Réparation codecs terminée : {st['ok']} converti(s), {st['skip']} ignoré(s), {st['fail']} échec(s).")
        for e in load_archive_index(root):
            fp = os.path.join(root, str(e.get("folder")))
            m = find_main_media(fp)
            if m and m.lower().endswith(VIDEO_EXTS):
                c = probe_codecs(m)
                print(f"  {'OK ' if is_compatible(m, c) else 'NON'} {codec_label(c):<14} {e.get('folder')}", flush=True)
        raise SystemExit(1 if st["fail"] else 0)
    if args.reindex:
        entries = sync_index_with_disk(root, _cli_log)
        for e in entries:
            fp = os.path.join(root, str(e.get("folder")))
            info = load_info(fp)
            if info:
                write_local_index(fp, info)
                fresh = entry_from_info(info, fp)
                e["size"], e["thumb"] = fresh["size"], fresh["thumb"]
        save_archive_index(root, entries)
        _cli_log(f"Index régénéré: {len(entries)} archive(s) -> {os.path.join(root, INDEX_HTML)}")
        if not args.url and not args.search:
            raise SystemExit(0)
    if args.search is not None:
        res = search_entries(sync_index_with_disk(root), args.search, args.platform, args.sort)
        for e in res:
            print(f"{fmt_iso(e.get('archived_at'))} | {e.get('platform')} | {e.get('title')} | tags={e.get('tags')} | {e.get('folder')}")
        print(f"{len(res)} résultat(s)")
        if not args.url:
            raise SystemExit(0)
    if args.page:
        raise SystemExit(run_cli(args.page, root=args.root, cookies_browser=args.cookies_browser,
                                 quality=args.quality, subtitles=args.subs, storyboard=not args.no_storyboard,
                                 tags=args.tags, notes=args.notes, force=True, page_mode=True))
    urls = list(args.url or [])
    if args.urls_file:
        with open(args.urls_file, "r", encoding="utf-8") as f:
            urls += extract_urls(f.read())
    if urls:
        raise SystemExit(run_cli(urls, root=args.root, cookies_browser=args.cookies_browser,
                                 quality=args.quality, subtitles=args.subs,
                                 storyboard=not args.no_storyboard, tags=args.tags, notes=args.notes,
                                 force=args.force))
    if tk is None:
        print("Tkinter indisponible.", file=sys.stderr)
        raise SystemExit(2)
    test_mode = bool(args.smoke or args.shot)
    global _CFG_READONLY
    if test_mode or args.root or args.font_delta is not None:
        _CFG_READONLY = True
    if not test_mode:
        # une seule fenêtre : si l'Archiveur est déjà ouvert, on le ramène au premier plan
        if not acquire_single_instance(wait=15.0 if args.wait_lock else 0.0):
            focus_existing_window()
            logger.info("Déjà ouvert : fenêtre existante ramenée au premier plan.")
            raise SystemExit(0)
    generate_icons(BASE)
    scaling = 0.0
    if args.dpi_aware and sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
            scaling = 96 / 72.0
        except Exception:
            pass
    app = ArchiveurApp(smoke=args.smoke, geometry=args.geometry, shot=args.shot, force_scaling=scaling,
                       root_override=args.root or "", font_delta=args.font_delta, shot_action=args.shot_action)
    app.mainloop()
    if args.smoke or args.shot:
        raise SystemExit(getattr(app, "_smoke_code", 1))
