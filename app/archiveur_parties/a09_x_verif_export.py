# -*- coding: utf-8 -*-
# Partie de archiveur5.py (découpage v1.2.2, comportement inchangé).
# Chargée par archiveur5.py dans un espace de noms commun : ne pas lancer seule.
from __future__ import annotations



# ================================================================= v5 : X / Twitter (texte, médias, fil parent)
def _x_status_id(url: str) -> str:
    k = normalize_url(url)
    return k[2:] if k.startswith("x:") else ""


def fetch_fxtwitter(url_or_id: str, user: str = "i", timeout: int = 20) -> Optional[Dict[str, Any]]:
    """API publique fxtwitter (sans connexion) → dict « tweet » ou None."""
    sid = url_or_id if re.fullmatch(r"\d+", url_or_id or "") else _x_status_id(url_or_id)
    if not sid:
        return None
    if user == "i":
        m = re.search(r"(?:x|twitter)\.com/([A-Za-z0-9_]{1,15})/status", url_or_id or "")
        if m:
            user = m.group(1)
    try:
        data, _f, _c = http_fetch(f"https://api.fxtwitter.com/{user}/status/{sid}", timeout=timeout, max_bytes=4_000_000)
        d = json.loads(data.decode("utf-8", errors="replace"))
        tw = d.get("tweet") if isinstance(d, dict) else None
        return tw if isinstance(tw, dict) else None
    except Exception as e:
        logger.info("fxtwitter %s : %s", sid, e)
        return None


def _fx_line(tw: Dict[str, Any]) -> str:
    a = tw.get("author") or {}
    when = ""
    try:
        when = datetime.fromtimestamp(int(tw.get("created_timestamp"))).strftime("%Y-%m-%d %H:%M")
    except Exception:
        when = str(tw.get("created_at") or "")
    head = f"{a.get('name') or ''} (@{a.get('screen_name') or '?'}) — {when}"
    txt = str(tw.get("text") or "")
    q = tw.get("quote")
    if isinstance(q, dict):
        qa = q.get("author") or {}
        txt += f"\n\n↪ Citation de @{qa.get('screen_name') or '?'} : {q.get('text') or ''}\n{q.get('url') or ''}"
    stats = []
    for k, lab in (("replies", "réponses"), ("retweets", "reposts"), ("likes", "j'aime"), ("views", "vues")):
        if tw.get(k) is not None:
            stats.append(f"{tw.get(k)} {lab}")
    return f"{head}\n{txt}\n{tw.get('url') or ''}" + (f"\n[{', '.join(stats)}]" if stats else "")


def fetch_x_thread(url: str, max_parents: int = 8) -> List[Dict[str, Any]]:
    """Post + messages parents (remontée du fil). Les réponses sous le post exigent une connexion."""
    tw = fetch_fxtwitter(url)
    if not tw:
        return []
    chain = [tw]
    cur = tw
    for _ in range(max_parents):
        pid = cur.get("replying_to_status")
        if not pid:
            break
        parent = fetch_fxtwitter(str(pid), str(cur.get("replying_to") or "i"))
        if not parent:
            break
        chain.insert(0, parent)
        cur = parent
    return chain


def x_thread_text(chain: List[Dict[str, Any]], main_id: str = "") -> str:
    parts = []
    for i, tw in enumerate(chain, 1):
        mark = "▶ " if str(tw.get("id")) == main_id else ""
        parts.append(f"{mark}[{i}/{len(chain)}] {_fx_line(tw)}")
    return "\n\n────────\n\n".join(parts)


def archive_x_fx(url: str, root: str, log: Callable[[str], None],
                 cancel_event: Optional[threading.Event] = None) -> Dict[str, Any]:
    """Post X sans vidéo (ou yt-dlp en échec) : texte complet, photos, vidéo directe, fil parent, liens."""
    chain = fetch_x_thread(url)
    if not chain:
        raise RuntimeError("fxtwitter : post introuvable (supprimé, privé ou service indisponible).")
    main = chain[-1]
    sid = str(main.get("id") or _x_status_id(url))
    a = main.get("author") or {}
    text_main = str(main.get("text") or "")
    title = pick_archive_title({"title": "status", "description": text_main,
                                "uploader": a.get("name") or a.get("screen_name"), "id": sid})
    stamp = datetime.now().strftime("%Y-%m-%d")
    final_dir = _new_archive_dir(root, f"{stamp}_x_{slugify(title)}_{slugify(sid, 20)}")
    media_files: List[str] = []
    try:
        n = 0
        for ti, tw in enumerate(chain):
            med = tw.get("media") or {}
            for ph in (med.get("photos") or [])[:8]:
                _check_cancel(cancel_event)
                u = str(ph.get("url") or "")
                if not u:
                    continue
                try:
                    data, final, _ct = http_fetch(u + ("?name=orig" if "pbs.twimg.com" in u and "?" not in u else ""),
                                                  timeout=30, max_bytes=20 * 1024 * 1024)
                    n += 1
                    ext = os.path.splitext(urlparse(final).path)[1] or ".jpg"
                    fname = f"photo_{n:02d}{'' if tw is main else '_fil'}{ext}"
                    with open(os.path.join(final_dir, fname), "wb") as f:
                        f.write(data)
                    media_files.append(fname)
                except ArchiveCancelled:
                    raise
                except Exception as e:
                    log(f"Photo non téléchargée : {e}")
            if tw is main:
                for vi, vd in enumerate((med.get("videos") or [])[:4]):
                    _check_cancel(cancel_event)
                    u = str(vd.get("url") or "")
                    if not u:
                        continue
                    try:
                        data, _f, _ct = http_fetch(u, timeout=120, max_bytes=500 * 1024 * 1024)
                        fname = f"video_{vi + 1:02d}.mp4"
                        with open(os.path.join(final_dir, fname), "wb") as f:
                            f.write(data)
                        media_files.append(fname)
                        log(f"Vidéo sauvée : {fname} ({human_size(len(data))})")
                    except Exception as e:
                        log(f"Vidéo non téléchargée : {e}")
                    th = str(vd.get("thumbnail_url") or "")
                    if th and not os.path.exists(os.path.join(final_dir, "thumbnail.jpg")):
                        try:
                            data, _f, _ct = http_fetch(th, timeout=30, max_bytes=10 * 1024 * 1024)
                            with open(os.path.join(final_dir, "thumbnail.jpg"), "wb") as f:
                                f.write(data)
                        except Exception:
                            pass
        av = str(a.get("avatar_url") or "")
        if av:
            try:
                data, _f, _ct = http_fetch(av, timeout=20, max_bytes=2 * 1024 * 1024)
                os.makedirs(os.path.join(final_dir, "auteur"), exist_ok=True)
                with open(os.path.join(final_dir, "auteur", "avatar.jpg"), "wb") as f:
                    f.write(data)
            except Exception:
                pass
    except ArchiveCancelled:
        shutil.rmtree(final_dir, ignore_errors=True)
        raise
    desc = x_thread_text(chain, sid) if len(chain) > 1 else _fx_line(main)
    up = ""
    try:
        up = datetime.fromtimestamp(int(main.get("created_timestamp"))).strftime("%Y%m%d")
    except Exception:
        pass
    links = [[u, u] for u in extract_urls(desc)]
    info_out = {
        "title": title, "id": sid,
        "uploader": f"{a.get('name') or ''} (@{a.get('screen_name') or ''})".strip(),
        "uploader_url": f"https://x.com/{a.get('screen_name')}" if a.get("screen_name") else "",
        "upload_date": up, "description": desc, "text": text_main,
        "webpage_url": str(main.get("url") or url), "url": url, "platform": "x",
        "like_count": main.get("likes"), "repost_count": main.get("retweets"), "view_count": main.get("views"),
        "tags": [], "notes": "", "archived_at": datetime.now().isoformat(timespec="seconds"),
        "folder": os.path.basename(final_dir),
        "media_files": [m for m in os.listdir(final_dir) if m.lower().endswith(MEDIA_EXTS)],
        "method": "x-fxtwitter", "thread_count": len(chain), "links": links,
        "note": "Texte + médias via fxtwitter (public). Fil : messages parents seulement ; "
                "les réponses sous le post exigent une connexion à X.",
    }
    if any(m.lower().endswith(VIDEO_EXTS) for m in info_out["media_files"]):
        try:
            generate_storyboard(final_dir, SB_FRAMES)
        except Exception:
            logger.exception("storyboard x")
    _write_json_atomic(os.path.join(final_dir, "info.json"), info_out)
    write_post_txt(os.path.join(final_dir, "post.txt"), info_out)
    write_local_index(final_dir, info_out)
    log(f"✖ Post X archivé (fxtwitter) : {len(chain)} message(s) du fil, {len(media_files)} média(s).")
    return info_out


def enrich_x_thread(folder: str, url: str, log: Callable[[str], None]) -> None:
    """Après yt-dlp sur X : ajoute le fil parent et les liens (non bloquant)."""
    try:
        chain = fetch_x_thread(url)
        if len(chain) < 2:
            return
        info = load_info(folder)
        if not info:
            return
        info["thread_text"] = x_thread_text(chain, _x_status_id(url))
        info["thread_count"] = len(chain)
        info["description"] = (info.get("description") or "") + "\n\n──── Fil (messages parents) ────\n\n" + info["thread_text"]
        _write_json_atomic(os.path.join(folder, "info.json"), info)
        write_post_txt(os.path.join(folder, "post.txt"), info)
        write_local_index(folder, info)
        log(f"Fil X : {len(chain)} message(s) ajoutés au texte.")
    except Exception:
        logger.exception("enrich x")


# ================================================================= v5 : lien original encore en ligne ?
ONLINE_LABELS = {"online": "🟢 en ligne", "offline": "🔴 supprimé / introuvable",
                 "restricted": "🟠 privé / restreint", "unknown": "⚪ non vérifiable"}
ONLINE_ICONS = {"online": "🟢", "offline": "🔴", "restricted": "🟠", "unknown": "⚪"}


def _http_status(url: str, timeout: int = 15) -> Tuple[int, str]:
    try:
        req = Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "fr,en;q=0.8"})
        with urlopen(req, timeout=timeout) as r:
            r.read(2048)
            return int(r.status), r.geturl()
    except Exception as e:
        code = getattr(e, "code", None)
        if code:
            return int(code), url
        return 0, str(e)


def check_online(url: str, timeout: int = 15) -> Tuple[str, str]:
    """('online'|'offline'|'restricted'|'unknown', détail) — oEmbed officiels quand possible."""
    url = (url or "").strip()
    if not url:
        return "unknown", "pas d'URL"
    key = normalize_url(url)
    oembed = None
    if key.startswith("youtube:"):
        vid = key.split(":", 1)[1]
        oembed = "https://www.youtube.com/oembed?format=json&url=" + quote(f"https://www.youtube.com/watch?v={vid}", safe="")
    elif key.startswith("x:"):
        oembed = "https://publish.twitter.com/oembed?omit_script=1&url=" + quote(f"https://twitter.com/i/status/{key[2:]}", safe="")
    elif "vimeo.com" in key:
        oembed = "https://vimeo.com/api/oembed.json?url=" + quote(url, safe="")
    elif key.startswith("tiktok:"):
        oembed = "https://www.tiktok.com/oembed?url=" + quote(url, safe="")
    if oembed:
        code, _ = _http_status(oembed, timeout)
        if code == 200:
            return "online", "oEmbed 200"
        if code in (404, 400, 410):
            return "offline", f"oEmbed {code}"
        if code in (401, 403):
            return "restricted", f"oEmbed {code} (privé, restreint ou intégration interdite)"
        if code == 0:
            return "unknown", "réseau"
    plat = detect_platform(url)
    code, final = _http_status(url, timeout)
    if plat in ("facebook", "instagram") and code in (200, 302, 400, 403):
        return "unknown", f"HTTP {code} — vérification impossible sans connexion"
    if 200 <= code < 400:
        return "online", f"HTTP {code}"
    if code in (404, 410, 451):
        return "offline", f"HTTP {code}"
    if code in (401, 403):
        return "restricted", f"HTTP {code}"
    return "unknown", f"HTTP {code}" if code else "réseau"


def check_online_many(root: str, folders: List[str], progress: Optional[Callable[[int, int, str, str], None]] = None,
                      cancel_event: Optional[threading.Event] = None, workers: int = 4) -> Dict[str, int]:
    from concurrent.futures import ThreadPoolExecutor
    entries = {e.get("folder"): e for e in load_archive_index(root)}
    todo = [f for f in folders if f in entries]
    counts = {"online": 0, "offline": 0, "restricted": 0, "unknown": 0}
    results: Dict[str, Tuple[str, str]] = {}

    def one(f):
        if cancel_event is not None and cancel_event.is_set():
            return f, ("", "")
        e = entries[f]
        return f, check_online(str(e.get("url") or e.get("source_url") or ""))
    done = 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        for f, (st, det) in ex.map(one, todo):
            done += 1
            if not st:
                continue
            results[f] = (st, det)
            counts[st] = counts.get(st, 0) + 1
            if progress:
                progress(done, len(todo), f, st)
    now = datetime.now().isoformat(timespec="seconds")
    for f, (st, det) in results.items():
        try:
            update_info_fields(root, f, save_index=False, online_status=st, online_detail=det, online_checked=now)
        except Exception:
            logger.exception("online %s", f)
    if results:
        refresh_entries(root, list(results))
    return counts


# ================================================================= v5 : vérification d'intégrité
VERIFY_KINDS = {
    "orphan_entry": ("Entrée orpheline (dossier absent)", "Retirer de l'index"),
    "unindexed": ("Dossier non indexé", "Réindexer"),
    "no_info": ("Dossier sans info.json", "Créer une fiche minimale et indexer"),
    "tmp_left": ("Dossier temporaire abandonné", "Supprimer"),
    "missing_files": ("Fichiers listés mais absents", "Mettre la fiche à jour"),
    "no_local_index": ("Page index.html manquante", "Régénérer la page"),
    "thumb_missing": ("Miniature introuvable", "Mettre l'index à jour"),
    "media_unreadable": ("Média illisible / corrompu", "Re-archiver depuis l'original"),
    "no_media": ("Aucun média alors qu'une vidéo était attendue", "Re-archiver depuis l'original"),
    "incompatible": ("Vidéo non lisible par le lecteur Windows", "Convertir en MP4 H.264"),
    "bad_json": ("info.json illisible", "Restaurer depuis l'index"),
}
AUTO_FIX_KINDS = {"orphan_entry", "unindexed", "no_info", "tmp_left", "missing_files", "no_local_index",
                  "thumb_missing", "bad_json"}


def probe_readable(path: str) -> Tuple[bool, str]:
    """Média lisible ? (ffprobe : erreurs de flux, durée nulle) ; images via Pillow."""
    low = path.lower()
    if low.endswith(IMAGE_EXTS):
        try:
            from PIL import Image as _Im
            with _Im.open(path) as im:
                im.verify()
            return True, ""
        except Exception as e:
            return False, f"image illisible ({e.__class__.__name__})"
    fp = find_ffprobe()
    if not fp:
        return True, "ffprobe absent"
    try:
        r = subprocess.run([fp, "-v", "error", "-show_entries", "format=duration:stream=codec_type",
                            "-of", "json", path], **_hidden_kwargs(), timeout=60)
        err = (r.stderr or b"").decode("utf-8", errors="replace").strip()
        data = json.loads((r.stdout or b"{}").decode("utf-8", errors="replace") or "{}")
        streams = data.get("streams") or []
        dur = float((data.get("format") or {}).get("duration") or 0)
        if r.returncode != 0 or not streams:
            return False, (err.splitlines()[0][:160] if err else "aucun flux lisible")
        if dur <= 0 and not low.endswith(".gif"):
            return False, "durée nulle"
        return True, ""
    except Exception as e:
        return False, str(e)[:160]


def verify_archives(root: str, check_media: bool = True,
                    progress: Optional[Callable[[int, int, str], None]] = None,
                    cancel_event: Optional[threading.Event] = None) -> Dict[str, Any]:
    """Rapport : [{folder, title, kind, detail, fix, auto}] + compteurs. Ne modifie rien."""
    issues: List[Dict[str, Any]] = []
    entries = load_archive_index(root)
    by_folder = {str(e.get("folder")): e for e in entries if e.get("folder")}

    def add(folder: str, kind: str, detail: str = "", title: str = ""):
        lab, fix = VERIFY_KINDS[kind]
        issues.append({"folder": folder, "title": title or str((by_folder.get(folder) or {}).get("title") or folder),
                       "kind": kind, "label": lab, "detail": detail, "fix": fix, "auto": kind in AUTO_FIX_KINDS})
    try:
        names = sorted(os.listdir(root)) if os.path.isdir(root) else []
    except OSError:
        names = []
    dirs = [n for n in names if os.path.isdir(os.path.join(root, n))]
    for f in by_folder:
        if f not in dirs:
            add(f, "orphan_entry")
    checked = 0
    total = len(dirs)
    for i, name in enumerate(dirs):
        if cancel_event is not None and cancel_event.is_set():
            break
        if progress:
            progress(i + 1, total, name)
        fp = os.path.join(root, name)
        if name.startswith("_tmp_"):
            add(name, "tmp_left", human_size(folder_size(fp)), name)
            continue
        if name.startswith("_") or name.startswith("."):
            continue
        info_p = os.path.join(fp, "info.json")
        if not os.path.isfile(info_p):
            add(name, "no_info", f"{len(list_folder_files(fp))} fichier(s)", name)
            continue
        try:
            with open(info_p, "r", encoding="utf-8") as fh:
                info = json.load(fh)
            if not isinstance(info, dict):
                raise ValueError("pas un objet")
        except Exception as e:
            add(name, "bad_json", str(e)[:120])
            continue
        checked += 1
        if name not in by_folder:
            add(name, "unindexed", "", str(info.get("title") or name))
        missing = [m for m in (info.get("media_files") or []) if isinstance(m, str)
                   and not os.path.exists(os.path.join(fp, m))]
        if missing:
            add(name, "missing_files", ", ".join(missing[:4]) + (" …" if len(missing) > 4 else ""))
        if not os.path.isfile(os.path.join(fp, "index.html")):
            add(name, "no_local_index")
        e = by_folder.get(name)
        if e and e.get("thumb") and not os.path.isfile(os.path.join(fp, str(e.get("thumb")))):
            add(name, "thumb_missing", str(e.get("thumb")))
        main = find_main_media(fp)
        if info.get("method") == "yt-dlp" and not main and not list_images(fp):
            add(name, "no_media")
        if check_media:
            for n in list_folder_files(fp):
                if n.lower().endswith(VIDEO_EXTS + AUDIO_EXTS):
                    ok, det = probe_readable(os.path.join(fp, n))
                    if not ok:
                        add(name, "media_unreadable", f"{n} : {det}")
            if main and main.lower().endswith(VIDEO_EXTS):
                try:
                    c = probe_codecs(main)
                    if c.get("vcodec") and not is_compatible(main, c):
                        add(name, "incompatible", codec_label(c))
                except Exception:
                    pass
    bad = {x["folder"] for x in issues}
    return {"issues": issues, "checked": checked, "folders": total, "entries": len(entries),
            "ok": max(0, checked - len(bad & set(dirs))), "date": datetime.now().isoformat(timespec="seconds")}


def repair_archives(root: str, issues: List[Dict[str, Any]], log: Callable[[str], None]) -> Dict[str, int]:
    """Applique les réparations automatiques sûres (pas de re-archivage ni conversion ici)."""
    st = {"ok": 0, "skip": 0, "fail": 0}
    entries = load_archive_index(root)
    by_folder = {str(e.get("folder")): e for e in entries}
    touched: List[str] = []
    drop: set = set()
    for it in issues:
        kind, f = it.get("kind"), str(it.get("folder") or "")
        fp = os.path.join(root, f)
        try:
            if kind == "orphan_entry":
                drop.add(f)
            elif kind == "tmp_left":
                if f.startswith("_tmp_") and os.path.isdir(fp):
                    shutil.rmtree(fp)
            elif kind == "no_info":
                files = list_folder_files(fp)
                m = re.match(r"^(\d{4}-\d{2}-\d{2})_([a-z0-9]+)_(.+)$", f)
                info = {"title": (m.group(3) if m else f).replace("-", " "), "platform": m.group(2) if m else "web",
                        "url": "", "webpage_url": "", "description": "",
                        "archived_at": (m.group(1) + "T00:00:00") if m else datetime.now().isoformat(timespec="seconds"),
                        "folder": f, "media_files": [n for n in files if n.lower().endswith(MEDIA_EXTS)],
                        "method": "réindexé", "tags": [], "notes": ""}
                _write_json_atomic(os.path.join(fp, "info.json"), info)
                write_local_index(fp, info)
                touched.append(f)
            elif kind == "bad_json":
                e = by_folder.get(f)
                if not e:
                    st["skip"] += 1
                    continue
                os.replace(os.path.join(fp, "info.json"), os.path.join(fp, "info.json.corrompu"))
                info = {"title": e.get("title"), "platform": e.get("platform"), "url": e.get("source_url") or e.get("url"),
                        "webpage_url": e.get("url"), "uploader": e.get("uploader"), "description": e.get("text_snippet") or "",
                        "archived_at": e.get("archived_at"), "folder": f, "tags": e.get("tags") or [],
                        "notes": e.get("notes") or "", "method": e.get("method") or "restauré",
                        "media_files": [n for n in list_folder_files(fp) if n.lower().endswith(MEDIA_EXTS)]}
                _write_json_atomic(os.path.join(fp, "info.json"), info)
                write_local_index(fp, info)
                touched.append(f)
            elif kind == "missing_files":
                info = load_info(fp)
                info["media_files"] = [n for n in list_folder_files(fp) if n.lower().endswith(MEDIA_EXTS)]
                _write_json_atomic(os.path.join(fp, "info.json"), info)
                write_local_index(fp, info)
                touched.append(f)
            elif kind == "no_local_index":
                write_local_index(fp, load_info(fp))
            elif kind in ("unindexed", "thumb_missing"):
                touched.append(f)
            else:
                st["skip"] += 1
                continue
            st["ok"] += 1
            log(f"🔧 {f} : {VERIFY_KINDS.get(kind, (kind, ''))[1]}")
        except Exception as ex:
            logger.exception("réparation %s %s", kind, f)
            log(f"❌ {f} : {friendly_error(ex)}")
            st["fail"] += 1
    entries = [e for e in entries if str(e.get("folder")) not in drop]
    for f in touched:
        fp = os.path.join(root, f)
        info = load_info(fp)
        if info:
            _merge_entry(entries, entry_from_info(info, fp))
    save_archive_index(root, entries)
    return st


# ================================================================= v5 : export / partage / statistiques
_STORED_EXTS = VIDEO_EXTS + AUDIO_EXTS + IMAGE_EXTS + (".zip", ".pdf", ".avif")


def build_catalog_rows(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = []
    for e in entries:
        rows.append({
            "titre": e.get("title") or "", "plateforme": e.get("platform") or "", "url": e.get("url") or "",
            "auteur": e.get("uploader") or "", "publie": fmt_upload_date(e.get("upload_date")),
            "archive_le": fmt_iso(e.get("archived_at")), "duree": human_duration(e.get("duration")),
            "taille_octets": int(e.get("size") or 0), "tags": ", ".join(e.get("tags") or []),
            "collections": ", ".join(e.get("collections") or []), "favori": "oui" if e.get("favorite") else "",
            "en_ligne": ONLINE_LABELS.get(str(e.get("online_status") or ""), ""), "notes": e.get("notes") or "",
            "dossier": e.get("folder") or "",
        })
    return rows


def export_catalog(entries: List[Dict[str, Any]], dest: str) -> int:
    """CSV (séparateur ; UTF-8 BOM pour Excel FR) ou JSON selon l'extension."""
    rows = build_catalog_rows(entries)
    if dest.lower().endswith(".json"):
        _write_json_atomic(dest, rows)
    else:
        import csv
        with open(dest, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["titre"], delimiter=";")
            w.writeheader()
            for r in rows:
                w.writerow(r)
    return len(rows)


def export_zip(root: str, folders: List[str], dest: str,
               progress: Optional[Callable[[int, int, str], None]] = None,
               cancel_event: Optional[threading.Event] = None) -> Tuple[int, int]:
    """ZIP des archives choisies + index.html (cartes) + catalogue.csv. Retourne (fichiers, octets)."""
    import zipfile
    entries = [e for e in load_archive_index(root) if e.get("folder") in set(folders)]
    files: List[Tuple[str, str]] = []
    for f in folders:
        fp = os.path.join(root, f)
        for dp, _dn, fn in os.walk(fp):
            for n in fn:
                if n.endswith(".tmp"):
                    continue
                full = os.path.join(dp, n)
                files.append((full, os.path.relpath(full, root).replace("\\", "/")))
    tmp = dest + ".partiel"
    total = 0
    try:
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as z:
            for i, (full, arc) in enumerate(files):
                if cancel_event is not None and cancel_event.is_set():
                    raise ArchiveCancelled("Export annulé.")
                ct = zipfile.ZIP_STORED if arc.lower().endswith(_STORED_EXTS) else zipfile.ZIP_DEFLATED
                z.write(full, arc, compress_type=ct)
                total += os.path.getsize(full)
                if progress and (i % 5 == 0 or i == len(files) - 1):
                    progress(i + 1, len(files), arc)
            z.writestr("index.html", build_global_index_html(entries, root))
            import csv
            import io
            buf = io.StringIO()
            rows = build_catalog_rows(entries)
            if rows:
                w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()), delimiter=";")
                w.writeheader()
                for r in rows:
                    w.writerow(r)
            z.writestr("catalogue.csv", "\ufeff" + buf.getvalue())
        os.replace(tmp, dest)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    return len(files), total


def entry_summary(e: Dict[str, Any]) -> str:
    lines = [str(e.get("title") or e.get("folder") or ""), str(e.get("url") or e.get("webpage_url") or "")]
    meta = [platform_label(e.get("platform"))]
    if e.get("uploader"):
        meta.append(str(e.get("uploader")))
    if e.get("upload_date"):
        meta.append(fmt_upload_date(e.get("upload_date")))
    lines.append(" · ".join(meta))
    if e.get("tags"):
        lines.append("Tags : " + ", ".join("#" + t for t in e.get("tags") or []))
    if e.get("notes"):
        lines.append("Notes : " + str(e.get("notes")))
    return "\n".join(x for x in lines if x.strip())


def compute_stats(entries: List[Dict[str, Any]], root: str) -> Dict[str, Any]:
    from collections import Counter
    by_plat: Dict[str, List[int]] = {}
    tags: Counter = Counter()
    months: Counter = Counter()
    cols: Counter = Counter()
    online: Counter = Counter()
    dur = 0.0
    for e in entries:
        p = str(e.get("platform") or "web")
        by_plat.setdefault(p, [0, 0])
        by_plat[p][0] += 1
        by_plat[p][1] += int(e.get("size") or 0)
        for t in e.get("tags") or []:
            tags[t.lower()] += 1
        for c in e.get("collections") or []:
            cols[c] += 1
        months[str(e.get("archived_at") or "")[:7] or "?"] += 1
        online[str(e.get("online_status") or "jamais vérifié")] += 1
        try:
            dur += float(e.get("duration") or 0)
        except (TypeError, ValueError):
            pass
    free = None
    try:
        free = shutil.disk_usage(root).free
    except Exception:
        pass
    return {"count": len(entries), "size": sum(v[1] for v in by_plat.values()), "by_platform": by_plat,
            "favorites": sum(1 for e in entries if e.get("favorite")), "tags": tags.most_common(15),
            "months": sorted(months.items())[-12:], "collections": cols.most_common(), "online": dict(online),
            "duration": dur, "free": free,
            "with_transcript": sum(1 for e in entries if e.get("has_transcript"))}


# ================================================================= GUI
try:
    from PIL import Image, ImageDraw, ImageTk  # type: ignore
    HAS_PIL = True
except Exception:  # pragma: no cover
    HAS_PIL = False

JOB_LABELS = {
    "attente": "⏳ En attente",
    "cours": "⬇ En cours",
    "ok": "✅ Terminé",
    "echec": "❌ Échec",
    "annule": "⛔ Annulé",
}
