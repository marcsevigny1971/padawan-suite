# -*- coding: utf-8 -*-
# Partie de archiveur5.py (découpage v1.2.2, comportement inchangé).
# Chargée par archiveur5.py dans un espace de noms commun : ne pas lancer seule.
from __future__ import annotations



def acquire_single_instance(wait: float = 0.0) -> bool:
    """True si cette instance est la seule (mutex nommé). Non-Windows : toujours True."""
    global _INSTANCE_MUTEX
    if not sys.platform.startswith("win"):
        return True
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        k32.CreateMutexW.restype = ctypes.c_void_p
        deadline = time.time() + max(0.0, wait)
        while True:
            h = k32.CreateMutexW(None, False, _MUTEX_NAME)
            if h and k32.GetLastError() != 183:  # ERROR_ALREADY_EXISTS
                _INSTANCE_MUTEX = h
                return True
            if h:
                k32.CloseHandle(ctypes.c_void_p(h))
            if time.time() >= deadline:
                return False
            time.sleep(0.25)
    except Exception:
        logger.exception("mutex instance")
        return True


def release_single_instance() -> None:
    global _INSTANCE_MUTEX
    if _INSTANCE_MUTEX and sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(_INSTANCE_MUTEX))
        except Exception:
            pass
    _INSTANCE_MUTEX = None


def focus_existing_window() -> bool:
    """Ramène au premier plan la fenêtre « Archiveur » déjà ouverte."""
    if not sys.platform.startswith("win"):
        return False
    try:
        import ctypes
        u32 = ctypes.windll.user32
        h = u32.FindWindowW("TkTopLevel", APP_NAME)
        if not h:
            return False
        if u32.IsIconic(h):
            u32.ShowWindow(h, 9)  # SW_RESTORE
        u32.SetForegroundWindow(h)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- sauvegarde de l'index (rotation)
BACKUP_DIR = "_sauvegardes"


def backup_index(root: str, keep: int = 15, min_interval: float = 1800.0) -> Optional[str]:
    """Copie archive_index.json dans _sauvegardes/ (au plus toutes les 30 min, garde les 15 dernières)."""
    src = os.path.join(root, INDEX_JSON)
    if not os.path.isfile(src):
        return None
    d = os.path.join(root, BACKUP_DIR)
    try:
        os.makedirs(d, exist_ok=True)
        olds = sorted(n for n in os.listdir(d) if n.startswith("archive_index_") and n.endswith(".json"))
        if olds:
            last = os.path.join(d, olds[-1])
            if time.time() - os.path.getmtime(last) < min_interval:
                return None
        dst = os.path.join(d, f"archive_index_{datetime.now().strftime('%Y%m%d-%H%M%S')}.json")
        shutil.copy2(src, dst)
        olds.append(os.path.basename(dst))
        for n in olds[:-keep]:
            try:
                os.remove(os.path.join(d, n))
            except OSError:
                pass
        return dst
    except Exception:
        logger.exception("sauvegarde index")
        return None


def list_index_backups(root: str) -> List[str]:
    d = os.path.join(root, BACKUP_DIR)
    try:
        return [os.path.join(d, n) for n in sorted(os.listdir(d), reverse=True)
                if n.startswith("archive_index_") and n.endswith(".json")]
    except OSError:
        return []


# ---------------------------------------------------------------- champs info.json → index
def update_info_fields(root: str, folder: str, save_index: bool = True, **fields: Any) -> Dict[str, Any]:
    """Met à jour des champs d'info.json (favori, collections, statut en ligne…) + page locale + index."""
    fp = os.path.join(root, folder)
    if not os.path.isdir(fp):
        raise FileNotFoundError(f"Dossier introuvable: {fp}")
    info = load_info(fp)
    info.setdefault("folder", folder)
    info.update(fields)
    _write_json_atomic(os.path.join(fp, "info.json"), info)
    try:
        write_local_index(fp, info)
    except Exception:
        logger.exception("index local %s", folder)
    if save_index:
        entries = load_archive_index(root)
        _merge_entry(entries, entry_from_info(info, fp))
        save_archive_index(root, entries)
    return info


def _merge_entry(entries: List[Dict[str, Any]], fresh: Dict[str, Any]) -> None:
    for i, e in enumerate(entries):
        if e.get("folder") == fresh.get("folder"):
            entries[i] = fresh
            return
    entries.append(fresh)


def refresh_entries(root: str, folders: List[str]) -> List[Dict[str, Any]]:
    """Reconstruit les entrées d'index des dossiers donnés depuis leur info.json (une seule écriture)."""
    entries = load_archive_index(root)
    for f in folders:
        fp = os.path.join(root, f)
        info = load_info(fp)
        if info:
            _merge_entry(entries, entry_from_info(info, fp))
    save_archive_index(root, entries)
    return entries


# ---------------------------------------------------------------- favoris / collections
COLLECTIONS_FILE = "collections.json"


def load_collections(root: str, entries: Optional[List[Dict[str, Any]]] = None) -> List[str]:
    names: List[str] = []
    try:
        p = os.path.join(root, COLLECTIONS_FILE)
        if os.path.isfile(p):
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                names = [str(x) for x in data if str(x).strip()]
    except Exception:
        logger.exception("collections.json")
    for e in entries or []:
        for c in e.get("collections") or []:
            if c not in names:
                names.append(c)
    seen = set()
    out = []
    for n in names:
        k = n.lower()
        if k not in seen:
            seen.add(k)
            out.append(n)
    return sorted(out, key=str.lower)


def save_collections(root: str, names: List[str]) -> None:
    os.makedirs(root, exist_ok=True)
    clean = sorted({re.sub(r"\s+", " ", n).strip()[:40] for n in names if n and n.strip()}, key=str.lower)
    _write_json_atomic(os.path.join(root, COLLECTIONS_FILE), clean)


def set_collections(root: str, folders: List[str], add: Optional[str] = None,
                    remove: Optional[str] = None) -> int:
    n = 0
    for f in folders:
        fp = os.path.join(root, f)
        info = load_info(fp)
        if not info:
            continue
        cols = [c for c in (info.get("collections") or []) if isinstance(c, str)]
        if add and add.lower() not in {c.lower() for c in cols}:
            cols.append(add)
        if remove:
            cols = [c for c in cols if c.lower() != remove.lower()]
        update_info_fields(root, f, save_index=False, collections=cols)
        n += 1
    refresh_entries(root, folders)
    return n


def set_favorite(root: str, folders: List[str], value: bool) -> int:
    n = 0
    for f in folders:
        if os.path.isdir(os.path.join(root, f)):
            update_info_fields(root, f, save_index=False, favorite=bool(value))
            n += 1
    refresh_entries(root, folders)
    return n


def add_tags_many(root: str, folders: List[str], tags: Any) -> int:
    new = parse_tags(tags)
    n = 0
    for f in folders:
        fp = os.path.join(root, f)
        info = load_info(fp)
        if not info:
            continue
        info_tags = parse_tags((info.get("tags") or []) + new)
        update_info_fields(root, f, save_index=False, tags=info_tags)
        try:
            write_post_txt(os.path.join(fp, "post.txt"), load_info(fp))
        except Exception:
            pass
        n += 1
    refresh_entries(root, folders)
    return n


def delete_archives(root: str, folders: List[str]) -> int:
    n = 0
    for f in folders:
        fp = os.path.join(root, f)
        if f and f == os.path.basename(f) and not f.startswith(".") and os.path.isdir(fp):
            shutil.rmtree(fp)
            n += 1
    entries = [e for e in load_archive_index(root) if e.get("folder") not in set(folders)]
    save_archive_index(root, entries)
    return n


# ---------------------------------------------------------------- classement simple (suggestions)
import unicodedata as _ud

COLL_SUGGEST_OFF = "collection_suggest_off"  # info.json : suggestion refusée (« Non merci »)

# familles de mots-clés -> collection proposée (mots sans accents, minuscules ; « * » = début de mot)
COLL_FAMILIES: List[Tuple[str, List[str]]] = [
    ("Santé & Nutrition", ["sante", "nutrition", "health", "healthy", "medecine", "medicine", "medical",
                           "medecin", "docteur", "doctor", "vaccin*", "pharma*", "vitamin*", "baking soda",
                           "bicarbonate", "cancer", "diet*", "regime", "guerir", "remede*", "remedy",
                           "immunit*", "maladie*", "disease", "jeune", "fasting", "sucre", "sugar",
                           "cholesterol", "diabet*", "nutritionniste", "naturopath*", "supplement*"]),
    ("Musique", ["music", "musique", "song", "songs", "chanson*", "official video", "clip officiel",
                 "concert", "album", "lyrics", "paroles", "remix", "guitar*", "guitare", "piano", "dj",
                 "official audio", "live session", "cover", "band", "orchestre", "orchestra"]),
    ("Films & séries", ["trailer", "bande annonce", "bande-annonce", "movie", "movies", "movieclips", "film",
                        "films", "serie", "series", "episode*", "saison", "season", "netflix", "warner",
                        "justwatch", "imdb", "anime", "cinema", "teaser", "court metrage", "short film"]),
    ("Documentaires", ["documentary", "documentaire*", "history", "histoire", "historique", "mystery",
                       "mystere*", "ancient", "chronology", "chronologie", "enquete", "civilisation*",
                       "civilization*", "archeolog*", "nobody talks about", "hidden", "secret*",
                       "the truth", "la verite", "explained", "explique"]),
    ("Tech & science", ["tech", "technologie", "technology", "ai", "ia", "intelligence artificielle",
                        "musk", "tesla", "spacex", "starlink", "grok", "chatgpt", "computer", "ordinateur",
                        "python", "logiciel", "software", "science", "scientifique", "physique", "physics",
                        "gravity", "gravite", "nasa", "robot*", "nvidia", "gpu", "quantum", "quantique",
                        "space", "espace", "astronom*", "invention"]),
    ("Nature", ["nature", "animal", "animaux", "animals", "wildlife", "forest", "foret", "ocean", "oiseau*",
                "bird*", "plante*", "plant", "jardin*", "garden*", "cat", "cats", "chat", "chats", "dog",
                "dogs", "chien*", "lion", "bear", "ours", "geolog*", "volcan*", "montagne*", "riviere",
                "lac", "canadian shield", "bouclier canadien"]),
    ("Spiritualité", ["jesus", "dieu", "god", "bible", "spiritual*", "spirituel*", "spiritualite", "priere",
                      "prayer", "meditation", "foi", "faith", "conscience", "consciousness", "ame", "soul",
                      "angel*", "ange", "anges", "eglise", "church"]),
    ("Actualités & politique", ["news", "nouvelles", "actualite*", "politique", "politics", "political",
                                "election*", "gouvernement", "government", "president", "ministre",
                                "parlement", "parliament", "tribunal", "court", "proces", "charges",
                                "senat*", "senate", "loi", "law", "guerre", "war"]),
    ("Humour", ["funny", "drole", "humour", "humor", "lol", "blague*", "meme", "memes", "comedy",
                "comedie", "parodie", "parody", "prank"]),
    ("Cuisine", ["recette*", "recipe*", "cuisine", "cooking", "chef", "patisserie", "baking", "gateau",
                 "souper", "dinner", "bbq"]),
]


def _fold(text: Any) -> str:
    """minuscules sans accents, ponctuation -> espaces."""
    t = _ud.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode("ascii").lower()
    return " " + re.sub(r"[^a-z0-9]+", " ", t).strip() + " "


_FAM_RX: List[Tuple[str, List[Tuple[str, "re.Pattern[str]"]]]] = []


def _family_patterns():
    if not _FAM_RX:
        for name, words in COLL_FAMILIES:
            pats = []
            for w in words:
                stem = w.rstrip("*")
                body = re.escape(_fold(stem).strip()).replace(r"\ ", " ")
                rx = re.compile(r" " + body + (r"[a-z0-9]*" if w.endswith("*") else "") + r" ")
                pats.append((stem, rx))
            _FAM_RX.append((name, pats))
    return _FAM_RX


_SERIES_SPLIT = re.compile(r"\s+[-–—|:]\s+|\s*[|(\[]|\s+-\s*")
_STOP_SERIES = {"", "the", "le", "la", "les", "un", "une", "a", "video", "vidéo", "live", "new", "official"}


def _title_wo_author(e: Dict[str, Any]) -> str:
    """Titre sans le « Auteur - » ajouté devant les posts X/Facebook."""
    t = str(e.get("title") or "").strip()
    up = str(e.get("uploader") or "").strip()
    if up and t.lower().startswith(up.lower()):
        rest = t[len(up):].lstrip(" -–—:|")
        if rest:
            return rest
    return t


def series_key(e: Dict[str, Any]) -> Tuple[str, str]:
    """(clé, nom joli) de la « série » d'un titre : partie avant « - », « | », « ( », « : ».
    Ex. « The Animatrix - Trailer » -> ('animatrix', 'Animatrix'). ('', '') si rien d'utile."""
    t = _title_wo_author(e)
    head = _SERIES_SPLIT.split(t, maxsplit=1)[0].strip(" -–—|:.\"'«»")
    if not head or len(head) > 48:
        return "", ""
    words = head.split()
    if len(words) > 5:
        return "", ""
    pretty_words = list(words)
    while pretty_words and _fold(pretty_words[0]).strip() in ("the", "le", "la", "les", "l"):
        pretty_words = pretty_words[1:]
    pretty = " ".join(pretty_words).strip()
    if pretty.lower().startswith("l'"):
        pretty = pretty[2:]
    key = _fold(pretty).strip()
    if not key or key in _STOP_SERIES or len(key) < 3 or key.isdigit():
        return "", ""
    up = _fold(e.get("uploader")).strip()
    if up and key == up:  # « Auteur - texte » : l'auteur n'est pas une série
        return "", ""
    return key, pretty[:40]


def _match_existing(name: str, existing: List[str]) -> str:
    k = _fold(name).strip()
    for c in existing:
        if _fold(c).strip() == k:
            return c
    return name


def suggest_collection(e: Dict[str, Any], entries: List[Dict[str, Any]],
                       existing: Optional[List[str]] = None,
                       info: Optional[Dict[str, Any]] = None) -> Optional[Tuple[str, str]]:
    """Propose UNE collection pour une archive : (nom, raison) ou None si aucune idée sûre.
    Ordre : nom d'une collection existante dans le titre > même série que d'autres archives >
    famille de mots-clés (Santé & Nutrition, Musique, Films & séries…)."""
    existing = list(existing or [])
    info = info or {}
    title = _fold(e.get("title"))
    # 1) une collection existante citée dans le titre (ou tags)
    tagtxt = _fold(" ".join(e.get("tags") or []))
    for c in sorted(existing, key=len, reverse=True):
        k = _fold(c).strip()
        if len(k) >= 3 and (f" {k} " in title or f" {k} " in tagtxt):
            return c, "le titre mentionne cette collection"
    # 2) même série (titres qui commencent pareil)
    key, pretty = series_key(e)
    if key:
        same = [x for x in entries if x is not e and x.get("folder") != e.get("folder")
                and series_key(x)[0] == key]
        if same:
            # si les autres sont déjà rangés quelque part : même endroit
            votes: Dict[str, int] = {}
            for x in same:
                for c in x.get("collections") or []:
                    votes[c] = votes.get(c, 0) + 1
            if votes:
                best = max(votes.items(), key=lambda kv: kv[1])[0]
                return best, f"comme {len(same)} autre(s) archive(s) « {pretty} »"
            return _match_existing(pretty, existing), f"même série que {len(same)} autre(s) archive(s)"
    # 3) familles de mots-clés
    parts = [
        (title, 3),
        (_fold(e.get("uploader")), 2),
        (tagtxt, 2),
        (_fold(" ".join(str(t) for t in (info.get("source_tags") or [])[:20])), 1),
        (_fold(str(e.get("text_snippet") or info.get("description") or "")[:600]), 1),
    ]
    best_name, best_score, best_words = "", 0, []
    for name, pats in _family_patterns():
        score, words = 0, []
        for txt, w in parts:
            if not txt.strip():
                continue
            for stem, rx in pats:
                if rx.search(txt):
                    score += w
                    if stem not in words:
                        words.append(stem)
        if score > best_score:
            best_name, best_score, best_words = name, score, words
    if best_score >= 3:
        shown = ", ".join(best_words[:3])
        return _match_existing(best_name, existing), f"mots repérés : {shown}"
    return None


def plan_auto_collections(entries: List[Dict[str, Any]], existing: Optional[List[str]] = None,
                          root: str = "") -> List[Tuple[str, str, str]]:
    """Plan « Ranger tout » : [(dossier, collection, raison)] pour les archives NON classées seulement."""
    plan = []
    for e in entries:
        if e.get("collections") or not e.get("folder"):
            continue
        info = load_info(os.path.join(root, str(e.get("folder")))) if root else {}
        if info.get(COLL_SUGGEST_OFF):
            continue
        sug = suggest_collection(e, entries, existing, info)
        if sug:
            plan.append((str(e.get("folder")), sug[0], sug[1]))
    return plan


def move_to_collection(root: str, folders: List[str], target: Optional[str]) -> int:
    """Déplace : l'archive n'est plus que dans « target » (None = Non classée)."""
    n = 0
    for f in folders:
        fp = os.path.join(root, f)
        if not load_info(fp):
            continue
        update_info_fields(root, f, save_index=False, collections=[target] if target else [])
        n += 1
    refresh_entries(root, folders)
    return n


# ================================================================= v5 : transcription
TRANSCRIPT_JSON = "transcript.json"
TRANSCRIPT_TXT = "transcript.txt"
SUB_EXTS = (".vtt", ".srt")
_TS_RE = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})")
