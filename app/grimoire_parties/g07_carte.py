# -*- coding: utf-8 -*-
# Partie de grimoire1.py (découpage v1.2.2, comportement inchangé).
# Chargée par grimoire1.py dans un espace de noms commun : ne pas lancer seule.
from __future__ import annotations



# ================================================================ application
# ======================================================================== 1.5 : cartes, carte des sujets, liens permanents
GX_ARCHIVES_SQL = """
CREATE TABLE IF NOT EXISTS archives(
  url TEXT PRIMARY KEY,
  item_id INTEGER,
  status TEXT DEFAULT '',
  root TEXT DEFAULT '',
  folder TEXT DEFAULT '',
  info TEXT DEFAULT '{}',
  created TEXT, updated TEXT
);
"""
GX_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
GX_MEDIA_EXT = (".mp4", ".webm", ".mkv", ".mov", ".m4v", ".mp3", ".m4a", ".opus")


def gx_mix(c1: str, c2: str, t: float) -> str:
    """melange de deux couleurs #RRGGBB (t=0 -> c1, t=1 -> c2)."""
    try:
        a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
        b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
        return "#%02X%02X%02X" % tuple(int(x + (y - x) * t) for x, y in zip(a, b))
    except Exception:
        return c2


def gx_http(url: str, timeout: float = 12, limit: int = 3_000_000, headers: Optional[Dict[str, str]] = None):
    h = {"User-Agent": GX_UA, "Accept-Language": "fr-CA,fr;q=0.9,en;q=0.8"}
    h.update(headers or {})
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(limit), r.headers.get("Content-Type", ""), r.geturl()


def gx_http_json(url: str, timeout: float = 12) -> Dict[str, Any]:
    raw, _c, _u = gx_http(url, timeout, headers={"Accept": "application/json"})
    return json.loads(raw.decode("utf-8", "replace"))


def gx_og(raw_html: str, *names: str) -> str:
    for n in names:
        mo = re.search(r'(?is)<meta[^>]+(?:property|name)=["\']' + re.escape(n) + r'["\'][^>]*content=["\']([^"\']*)', raw_html) or \
            re.search(r'(?is)<meta[^>]+content=["\']([^"\']*)["\'][^>]*(?:property|name)=["\']' + re.escape(n) + r'["\']', raw_html)
        if mo and mo.group(1).strip():
            return html.unescape(re.sub(r"\s+", " ", mo.group(1))).strip()
    return ""


def gx_preview_dir() -> str:
    d = os.path.join(Paths.data, "apercus")
    os.makedirs(d, exist_ok=True)
    return d


def gx_key(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


def gx_preview_cached(url: str) -> Optional[Dict[str, Any]]:
    p = os.path.join(gx_preview_dir(), gx_key(url) + ".json")
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def gx_preview_image(url: str) -> str:
    """chemin de la miniature d'apercu en cache (ou '')."""
    d = gx_preview_cached(url)
    if d and d.get("image"):
        p = os.path.join(gx_preview_dir(), d["image"])
        if os.path.isfile(p):
            return p
    return ""


def gx_fetch_preview(url: str) -> Dict[str, Any]:
    """apercu d'un lien (titre, site, description, miniature : OpenGraph / oEmbed) ; garde une copie dans apercus\\
    pour que ca marche hors ligne. Meme logique que le Journal de bord 1.4."""
    key = gx_key(url)
    d = gx_preview_dir()
    jp = os.path.join(d, key + ".json")
    old = gx_preview_cached(url)
    if old and (old.get("ok") or time.time() - float(old.get("t") or 0) < 3600):
        return old
    host = (urllib.parse.urlparse(url).hostname or "").lower().replace("www.", "")
    res: Dict[str, Any] = {"url": url, "title": "", "site": host, "desc": "", "image": "", "author": "", "ok": False,
                           "t": time.time()}
    img_url = ""
    q = urllib.parse.quote(url, safe="")
    try:
        if host in ("youtube.com", "m.youtube.com", "youtu.be", "music.youtube.com"):
            o = gx_http_json("https://www.youtube.com/oembed?format=json&url=" + q)
            res.update(title=o.get("title", ""), author=o.get("author_name", ""), site="YouTube", video=True)
            img_url = o.get("thumbnail_url", "")
        elif host.endswith("vimeo.com"):
            o = gx_http_json("https://vimeo.com/api/oembed.json?url=" + q)
            res.update(title=o.get("title", ""), author=o.get("author_name", ""), site="Vimeo",
                       desc=str(o.get("description") or "")[:300], video=True)
            img_url = o.get("thumbnail_url", "")
        elif host.endswith("tiktok.com"):
            o = gx_http_json("https://www.tiktok.com/oembed?url=" + q)
            res.update(title=o.get("title", ""), author=o.get("author_name", ""), site="TikTok", video=True)
            img_url = o.get("thumbnail_url", "")
        elif host in ("x.com", "twitter.com", "mobile.twitter.com", "fxtwitter.com", "vxtwitter.com") and "/status/" in url:
            mo = re.search(r"/([A-Za-z0-9_]{1,15})/status(?:es)?/(\d+)", url)
            o = gx_http_json(f"https://api.fxtwitter.com/{mo.group(1)}/status/{mo.group(2)}")["tweet"]
            a = o.get("author") or {}
            res.update(title=(a.get("name") or "") + (f" (@{a.get('screen_name')})" if a.get("screen_name") else ""),
                       author=a.get("name") or "", site="X", desc=str(o.get("text") or "")[:400])
            med = o.get("media") or {}
            if med.get("photos"):
                img_url = med["photos"][0].get("url", "")
            elif med.get("videos"):
                img_url = med["videos"][0].get("thumbnail_url", "")
                res["video"] = True
            else:
                img_url = a.get("avatar_url", "")
        if not res["title"]:
            raw, ctype, final = gx_http(url, 12, 1_500_000)
            if "html" in ctype.lower() or not ctype:
                t = raw.decode("utf-8", "replace")
                res["title"] = gx_og(t, "og:title", "twitter:title") or html.unescape(
                    re.sub(r"\s+", " ", (re.search(r"(?is)<title[^>]*>(.*?)</title>", t) or [None, ""])[1])).strip()
                res["desc"] = res["desc"] or gx_og(t, "og:description", "twitter:description", "description")[:400]
                res["site"] = gx_og(t, "og:site_name") or res["site"]
                img_url = img_url or gx_og(t, "og:image", "og:image:url", "twitter:image", "twitter:image:src")
                if img_url:
                    img_url = urllib.parse.urljoin(final, img_url)
            else:
                res["title"] = os.path.basename(urllib.parse.urlparse(url).path) or url
                res["desc"] = ctype
        res["title"] = str(res["title"])[:200]
        res["ok"] = bool(res["title"] or res["desc"])
        if img_url:
            try:
                raw, _c, _u = gx_http(img_url, 15, 8_000_000)
                from PIL import Image  # type: ignore
                im = Image.open(io.BytesIO(raw)).convert("RGB")
                im.thumbnail((480, 300))
                im.save(os.path.join(d, key + ".jpg"), "JPEG", quality=85)
                res["image"] = key + ".jpg"
            except Exception:
                pass
    except Exception as ex:
        res["erreur"] = str(ex)[:200]
    try:
        tmp = jp + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False)
        os.replace(tmp, jp)
    except OSError:
        pass
    return res


GX_ARCH_SCRIPT = r"""
import sys, os, json
sys.path.insert(0, sys.argv[1]); url = sys.argv[2]
import archiveur5 as a
a.setup_logging()
def hook(d):
    try:
        if d.get("status") == "downloading":
            t = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            if t:
                print("@@P@@%.1f" % (100.0 * (d.get("downloaded_bytes") or 0) / t), flush=True)
        elif d.get("status") == "finished":
            print("@@P@@100", flush=True)
    except Exception:
        pass
cfg = a.load_cfg()
root = cfg.get("archive_root") or a.DEFAULT_ROOT
os.makedirs(root, exist_ok=True)
if not a._cli_ensure_ytdlp():
    print("@@E@@yt-dlp introuvable", flush=True); sys.exit(2)
entries = a.sync_index_with_disk(root)
d = a.find_duplicates(entries, url)
if d:
    folder, dup = d[0].get("folder"), True
else:
    info = a.archive_url(url, root, a._cli_log, progress_hook=hook, quality=cfg.get("quality") or "best",
                         subtitles=bool(cfg.get("subtitles", True)), storyboard=True, tags=["Grimoire"],
                         notes="Depuis le Grimoire", web_capture=bool(cfg.get("web_capture", True)),
                         use_fx=bool(cfg.get("x_fxtwitter", True)), auto_convert=bool(cfg.get("auto_convert", True)))
    folder, dup = a.register_archive(root, info)["folder"], False
try:
    a.set_collections(root, [folder], add="Grimoire")
except Exception:
    pass
print("@@R@@" + json.dumps({"root": root, "folder": folder, "dup": dup}), flush=True)
"""


def gx_archiveur_dir() -> str:
    for d in (padawan_dir(), BASE):
        if d and os.path.isfile(os.path.join(d, "archiveur5.py")):
            return d
    return ""


def gx_console_python() -> str:
    exe = sys.executable or "python"
    if os.path.basename(exe).lower() == "pythonw.exe":
        c = os.path.join(os.path.dirname(exe), "python.exe")
        if os.path.isfile(c):
            return c
    return exe


def gx_archive_via_archiveur(url: str, on_event: Callable[[str, Any], None] = lambda k, v: None,
                             timeout: float = 3600) -> Dict[str, Any]:
    here = gx_archiveur_dir()
    if not here:
        raise RuntimeError("archiveur5.py introuvable")
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    kw: Dict[str, Any] = {}
    if IS_WIN:
        kw["creationflags"] = CREATE_NO_WINDOW
    p = subprocess.Popen([gx_console_python(), "-c", GX_ARCH_SCRIPT, here, url], cwd=here, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, text=True, encoding="utf-8",
                         errors="replace", env=env, **kw)
    res, tail, t0 = None, [], time.time()
    assert p.stdout is not None
    for line in p.stdout:
        line = line.rstrip()
        if line.startswith("@@P@@"):
            try:
                on_event("pct", float(line[5:]))
            except ValueError:
                pass
        elif line.startswith("@@R@@"):
            res = json.loads(line[5:])
        elif line.startswith("@@E@@"):
            tail.append(line[5:])
        elif line.strip():
            tail = (tail + [line])[-8:]
            on_event("log", line)
        if time.time() - t0 > timeout:
            p.kill()
            break
    p.wait()
    if not res:
        fails = [x for x in tail if "FAIL" in x or "rror" in x]
        raise RuntimeError((fails or tail or ["l'Archiveur n'a rien gardé"])[-1][-240:])
    return res


def gx_folder_info(folder: str) -> Dict[str, Any]:
    """fichiers utiles d'un dossier d'archive (video principale, page, capture...)."""
    files = os.listdir(folder) if os.path.isdir(folder) else []
    vids = sorted([f for f in files if f.lower().endswith(GX_MEDIA_EXT)], key=lambda f: -os.path.getsize(os.path.join(folder, f)))
    imgs = [f for f in files if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp")) and not f.startswith("sb_")]
    imgs.sort(key=lambda f: (0 if ("thumb" in f.lower() or "capture" in f.lower()) else 1, f))
    info: Dict[str, Any] = {}
    try:
        with open(os.path.join(folder, "info.json"), "r", encoding="utf-8") as f:
            info = json.load(f) or {}
    except (OSError, ValueError):
        info = {}
    return {"main": vids[0] if vids else ("lecture.html" if "lecture.html" in files else
                                          ("page.html" if "page.html" in files else ("index.html" if "index.html" in files else ""))),
            "video": bool(vids and not vids[0].lower().endswith((".mp3", ".m4a", ".opus"))),
            "index": "index.html" if "index.html" in files else "",
            "capture": imgs[0] if imgs else "",
            "title": str(info.get("title") or "")[:300],
            "texte": str(info.get("description") or info.get("text") or "")[:20000],
            "nfiles": len(files)}


def gx_archive_get(store: "Store", url: str) -> Optional[Dict[str, Any]]:
    try:
        r = store.q("SELECT * FROM archives WHERE url=?", (url,))
    except sqlite3.Error:
        return None
    if not r:
        return None
    d = dict(r[0])
    try:
        d["info"] = json.loads(d.get("info") or "{}")
    except ValueError:
        d["info"] = {}
    return d


def gx_archive_set(store: "Store", url: str, item_id: Optional[int], status: str, root: str = "", folder: str = "",
                   info: Optional[Dict[str, Any]] = None) -> None:
    now = now_iso()
    old = gx_archive_get(store, url)
    if old:
        store.x("UPDATE archives SET item_id=COALESCE(?,item_id), status=?, root=?, folder=?, info=?, updated=? WHERE url=?",
                (item_id, status, root or old.get("root") or "", folder or old.get("folder") or "",
                 json.dumps(info if info is not None else old.get("info") or {}, ensure_ascii=False), now, url))
    else:
        store.x("INSERT INTO archives(url,item_id,status,root,folder,info,created,updated) VALUES(?,?,?,?,?,?,?,?)",
                (url, item_id, status, root, folder, json.dumps(info or {}, ensure_ascii=False), now, now))


def gx_archive_folder(a: Optional[Dict[str, Any]]) -> str:
    if not a or a.get("status") != "permanent":
        return ""
    p = os.path.join(a.get("root") or "", a.get("folder") or "")
    return p if a.get("folder") and os.path.isdir(p) else ""


def gx_cheer(pct: Optional[float], log: str = "") -> str:
    if pct is None:
        if re.search(r"(?i)ffmpeg|convert|encod|remux|storyboard", log or ""):
            return "🎞 L'Archiveur peaufine la copie… presque fini !"
        return "🛰 L'Archiveur met ce lien à l'abri… tu peux continuer à lire."
    p = int(pct)
    if p < 5:
        return "🚀 C'est parti, on va chercher ça…"
    if p < 40:
        return f"📥 {p} % — ça avance bien !"
    if p < 80:
        return f"✨ {p} % — plus de la moitié !"
    if p < 100:
        return f"🏁 {p} % — dernière ligne droite !"
    return "🎞 Téléchargé ! L'Archiveur range la copie…"


def gx_item_urls(it: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    for u in [it.get("url") or ""] + find_urls(it.get("body_text") or "") + find_urls(it.get("extracted") or "")[:5]:
        u = (u or "").strip().rstrip(".,;:)»\"'")
        if u.startswith(("http://", "https://")) and u not in out:
            out.append(u)
    return out[:12]


class MindMap(tk.Toplevel):
    """« Carte des sujets » : graphe anime et interactif (Canvas Tk pur) : sujets, sous-sujets, fiches, liens."""

    def __init__(self, app: "GrimoireApp"):
        super().__init__(app)
        self.app = app
        st = app.store
        self.title("🗺 Carte des sujets — Grimoire")
        self.configure(bg=C["BG"])
        try:
            self.state("zoomed")
        except tk.TclError:
            self.geometry(f"{self.winfo_screenwidth()}x{self.winfo_screenheight() - 60}+0+0")
        self.anim = bool(app.store.get("animations", True))
        self.show_items = tk.BooleanVar(value=bool(st.get("map_items", True)))
        self.show_links = tk.BooleanVar(value=bool(st.get("map_links", False)))
        bar = tk.Frame(self, bg=C["PANEL"])
        bar.pack(fill="x")
        tk.Label(bar, text="🗺 CARTE DES SUJETS", bg=C["PANEL"], fg=C["HI"], font=fnt("GTitle")).pack(side="left", padx=10, pady=6)
        for txt, cmd, tip in (("➕ Zoom", lambda: self.zoom_at(1.2), "Agrandir (molette vers le haut, ou +)"),
                              ("➖ Zoom", lambda: self.zoom_at(1 / 1.2), "Réduire (molette vers le bas, ou -)"),
                              ("🎯 Recentrer", self.fit, "Tout voir d'un coup d'œil (touche 0)"),
                              ("✨ Réorganiser", self.shake, "Relancer l'animation de placement (touche R)")):
            mk_button(bar, txt, cmd, tip=tip).pack(side="left", padx=3, pady=6)
        c1 = mk_check(bar, "Montrer les fiches", self.show_items, bg=C["PANEL"], cmd=self.rebuild)
        c1.pack(side="left", padx=8)
        Tooltip(c1, "Petits points autour de chaque sujet : un point = une fiche")
        c2 = mk_check(bar, "Liens entre fiches", self.show_links, bg=C["PANEL"], cmd=lambda: (self.app.store.set("map_links", bool(self.show_links.get())), self.redraw()))
        c2.pack(side="left", padx=4)
        Tooltip(c2, "Traits pointillés : fiches qui se citent ([[…]]) ou partagent une étiquette")
        mk_button(bar, "✖ Fermer", self.destroy, tip="Fermer la carte (Échap)").pack(side="right", padx=6, pady=6)
        self.l_info = tk.Label(self, text="Molette : zoom · glisser : déplacer · clic sur un sujet : l'ouvrir · double-clic sur une "
                                          "fiche : l'ouvrir · survol : nom et nombre de fiches", bg=C["BG"], fg=C["DIM"],
                               font=fnt("GSM"), anchor="w")
        self.l_info.pack(fill="x", padx=10)
        self.cv = tk.Canvas(self, bg=C["CARD"], highlightthickness=0, bd=0, takefocus=1)
        self.cv.pack(fill="both", expand=True)
        self.scale, self.ox, self.oy = 1.0, 0.0, 0.0
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.edges: List[Tuple[str, str, str]] = []
        self.hover: Optional[str] = None
        self.drag: Optional[Tuple[int, int, float, float, bool]] = None
        self.ticks = 0
        self.job = None
        cv = self.cv
        cv.bind("<MouseWheel>", lambda e: self.zoom_at(1.15 if wheel_steps(e) < 0 else 1 / 1.15, e.x, e.y))
        cv.bind("<Button-4>", lambda e: self.zoom_at(1.15, e.x, e.y))
        cv.bind("<Button-5>", lambda e: self.zoom_at(1 / 1.15, e.x, e.y))
        cv.bind("<ButtonPress-1>", self._press)
        cv.bind("<B1-Motion>", self._motion_drag)
        cv.bind("<ButtonRelease-1>", self._release)
        cv.bind("<Double-Button-1>", self._double)
        cv.bind("<Motion>", self._motion)
        cv.bind("<Button-3>", self._menu)
        cv.bind("<Configure>", lambda _e: self.redraw())
        self.bind("<Escape>", lambda _e: self.destroy())
        for k, f in (("plus", 1.2), ("equal", 1.2), ("KP_Add", 1.2), ("minus", 1 / 1.2), ("KP_Subtract", 1 / 1.2)):
            self.bind(f"<{k}>", lambda _e, ff=f: self.zoom_at(ff))
        self.bind("0", lambda _e: self.fit())
        self.bind("r", lambda _e: self.shake())
        self.bind("R", lambda _e: self.shake())
        self.rebuild(first=True)
        self.after(50, lambda: (cv.focus_set(), self.fit(), self.start()))

    # ------------------------------------------------------------ modele
    def rebuild(self, first: bool = False):
        st = self.app.store
        st.set("map_items", bool(self.show_items.get()))
        subs = st.subjects()
        tc = st.total_counts()
        cnt = st.counts()
        old = self.nodes
        self.nodes, self.edges = {}, []
        roots = [s for s in st.children(None)]
        n = max(1, len(roots))
        R0 = 340.0
        for k, s in enumerate(roots):
            a = 2 * math.pi * k / n
            self._add_subject(s, math.cos(a) * R0, math.sin(a) * R0, subs, tc, 0, old)
        for sid, s in subs.items():
            if s.get("parent_id") and f"s{s['parent_id']}" in self.nodes and f"s{sid}" in self.nodes:
                self.edges.append((f"s{s['parent_id']}", f"s{sid}", "tree"))
        if self.show_items.get():
            items = st.items_where("1=1", limit=3000)
            by_title: Dict[str, str] = {}
            tags: Dict[str, List[str]] = {}
            for r in items:
                p = self.nodes.get(f"s{r['subject_id']}")
                if not p:
                    continue
                key = f"i{r['id']}"
                ang = random.random() * 2 * math.pi
                o = old.get(key)
                self.nodes[key] = {"kind": "item", "id": r["id"], "label": r.get("title") or "(sans titre)",
                                   "x": o["x"] if o else p["x"] + math.cos(ang) * 60, "y": o["y"] if o else p["y"] + math.sin(ang) * 60,
                                   "vx": 0.0, "vy": 0.0, "r": 4.5, "color": p["color"], "type": r["type"], "fav": r.get("fav")}
                self.edges.append((p["key"], key, "item"))
                by_title[norm(r.get("title") or "")] = key
                for tg in tag_list(r.get("tags") or ""):
                    tags.setdefault(tg.lower(), []).append(key)
            seen = set()
            for r in items:
                a = f"i{r['id']}"
                if a not in self.nodes:
                    continue
                for ref in re.findall(r"\[\[([^\]]+)\]\]", r.get("body_text") or ""):
                    b = by_title.get(norm(ref))
                    if b and b != a and (a, b) not in seen:
                        seen.add((a, b))
                        self.edges.append((a, b, "ref"))
            for tg, keys in tags.items():
                if 2 <= len(keys) <= 12:
                    for i in range(len(keys) - 1):
                        pair = (keys[i], keys[i + 1])
                        if pair not in seen:
                            seen.add(pair)
                            self.edges.append((keys[i], keys[i + 1], "tag"))
        _ = cnt
        if not first:
            self.start()

    def _add_subject(self, s, x, y, subs, tc, depth, old):
        key = f"s{s['id']}"
        o = old.get(key)
        n = tc.get(s["id"], 0)
        r = (26 if depth == 0 else 16) + 5 * math.sqrt(n)
        col = s.get("color") or (self.nodes.get(f"s{s.get('parent_id')}", {}).get("color")) or C["HI"]
        self.nodes[key] = {"kind": "subject", "id": s["id"], "key": key, "label": s["name"], "icon": s.get("icon") or "📁",
                           "count": n, "x": o["x"] if o else x, "y": o["y"] if o else y, "vx": 0.0, "vy": 0.0,
                           "r": min(r, 70), "color": col, "depth": depth}
        kids = self.app.store.children(s["id"])
        for k, c in enumerate(kids):
            a = math.atan2(y, x) + (k - (len(kids) - 1) / 2) * 0.55
            self._add_subject(c, x + math.cos(a) * 170, y + math.sin(a) * 170, subs, tc, depth + 1, old)

    # ------------------------------------------------------------ animation (forces douces)
    def start(self):
        self.ticks = 160 if self.anim else 0
        if not self.anim:
            for _ in range(140):
                self.step(fast=True)
            self.redraw()
            return
        if self.job is None:
            self.job = self.after(16, self._tick)

    def shake(self):
        for n in self.nodes.values():
            n["vx"] += random.uniform(-8, 8)
            n["vy"] += random.uniform(-8, 8)
        self.start()

    def _tick(self):
        self.job = None
        if not self.winfo_exists():
            return
        self.step()
        self.redraw()
        self.ticks -= 1
        if self.ticks > 0:
            self.job = self.after(20, self._tick)

    def step(self, fast: bool = False):
        ns = list(self.nodes.values())
        subj = [n for n in ns if n["kind"] == "subject"]
        for i, a in enumerate(subj):           # repulsion entre sujets
            for b in subj[i + 1:]:
                dx, dy = a["x"] - b["x"], a["y"] - b["y"]
                d2 = dx * dx + dy * dy + 0.01
                d = math.sqrt(d2)
                mind = a["r"] + b["r"] + 60
                f = 9000.0 / d2 + (max(0.0, mind - d) * 0.5)
                fx, fy = dx / d * f, dy / d * f
                a["vx"] += fx; a["vy"] += fy
                b["vx"] -= fx; b["vy"] -= fy
        for a_k, b_k, kind in self.edges:       # ressorts
            a, b = self.nodes.get(a_k), self.nodes.get(b_k)
            if not a or not b:
                continue
            dx, dy = b["x"] - a["x"], b["y"] - a["y"]
            d = math.sqrt(dx * dx + dy * dy) + 0.01
            rest = {"tree": a["r"] + b["r"] + 90, "item": a["r"] + 22 + (abs(hash(b_k)) % 30), "ref": 120, "tag": 140}[kind]
            k = {"tree": 0.02, "item": 0.08, "ref": 0.004, "tag": 0.002}[kind]
            f = (d - rest) * k
            fx, fy = dx / d * f, dy / d * f
            if a["kind"] == "item" or kind != "item":
                a["vx"] += fx; a["vy"] += fy
            b["vx"] -= fx; b["vy"] -= fy
        for n in ns:                              # gravite vers le centre + amortissement
            g = 0.004 if n["kind"] == "subject" else 0.0
            n["vx"] = (n["vx"] - n["x"] * g) * 0.78
            n["vy"] = (n["vy"] - n["y"] * g) * 0.78
            if self.drag and self.drag[4] and self.drag_key == n.get("key", f"i{n['id']}"):
                continue
            n["x"] += max(-30, min(30, n["vx"]))
            n["y"] += max(-30, min(30, n["vy"]))

    # ------------------------------------------------------------ dessin
    def sx(self, x: float) -> float:
        return self.cv.winfo_width() / 2 + (x + self.ox) * self.scale

    def sy(self, y: float) -> float:
        return self.cv.winfo_height() / 2 + (y + self.oy) * self.scale

    def redraw(self):
        cv = self.cv
        if not cv.winfo_exists():
            return
        cv.delete("all")
        s = self.scale
        links = self.show_links.get()
        for a_k, b_k, kind in self.edges:
            if kind in ("ref", "tag") and not links:
                continue
            a, b = self.nodes.get(a_k), self.nodes.get(b_k)
            if not a or not b:
                continue
            hot = self.hover in (a_k, b_k)
            if kind == "tree":
                cv.create_line(self.sx(a["x"]), self.sy(a["y"]), self.sx(b["x"]), self.sy(b["y"]), fill=gx_mix(C["CARD"], b["color"], 0.8),
                               width=max(1, 3 * s))
            elif kind == "item":
                cv.create_line(self.sx(a["x"]), self.sy(a["y"]), self.sx(b["x"]), self.sy(b["y"]),
                               fill=gx_mix(C["CARD"], a["color"], 0.6 if hot else 0.28), width=1)
            else:
                cv.create_line(self.sx(a["x"]), self.sy(a["y"]), self.sx(b["x"]), self.sy(b["y"]),
                               fill=C["HI"] if hot else gx_mix(C["CARD"], C["FG"] if kind == "ref" else C["DIM"], 0.55),
                               dash=(4, 3), width=2 if hot else 1)
        for key, n in self.nodes.items():
            if n["kind"] != "item":
                continue
            r = max(2.0, n["r"] * min(1.6, s))
            x, y = self.sx(n["x"]), self.sy(n["y"])
            hot = key == self.hover
            cv.create_oval(x - r, y - r, x + r, y + r, fill=C["HI"] if (hot or n.get("fav")) else gx_mix(C["CARD"], n["color"], 0.75),
                           outline=C["HI"] if hot else "", tags=("node", key))
        subs = sorted([kv for kv in self.nodes.items() if kv[1]["kind"] == "subject"], key=lambda kv: -kv[1]["depth"])
        for key, n in subs:
            r = n["r"] * s
            x, y = self.sx(n["x"]), self.sy(n["y"])
            hot = key == self.hover
            if hot:
                cv.create_oval(x - r - 6, y - r - 6, x + r + 6, y + r + 6, outline=n["color"], width=2, tags=("node", key))
            cv.create_oval(x - r, y - r, x + r, y + r, fill=gx_mix(C["CARD"], n["color"], 0.30 if not hot else 0.45),
                           outline=n["color"], width=3 if n["depth"] == 0 else 2, tags=("node", key))
            if r > 9:
                cv.create_text(x, y - (r * 0.12), text=n["icon"], font=("Segoe UI Emoji", max(8, int(min(28, r * 0.55)))),
                               fill=C["TEXT"], tags=("node", key))
            if s > 0.35 or n["depth"] == 0:
                fz = max(7, int((11 if n["depth"] == 0 else 9) * min(1.5, max(0.8, s))))
                cv.create_text(x, y + r + 4, text=f"{n['label']}  ({n['count']})", anchor="n", fill=C["TEXT"] if not hot else C["HI"],
                               font=(fnt("GUIB").actual("family") if hasattr(fnt("GUIB"), "actual") else "Segoe UI", fz, "bold"),
                               tags=("node", key))
        if self.hover and self.hover in self.nodes:
            n = self.nodes[self.hover]
            txt = (f"{n['icon']} {self.app.store.subject_path(n['id'])} — {n['count']} fiche(s) · clic : ouvrir ce sujet"
                   if n["kind"] == "subject" else f"{TYPES.get(n['type'], TYPES['file'])['icon']} {n['label']} · double-clic : ouvrir la fiche")
            x, y = self.sx(n["x"]), self.sy(n["y"]) - n["r"] * s - 16
            t = cv.create_text(x, y, text=txt, anchor="s", fill=C["ON_HI"], font=fnt("GUI"))
            bb = cv.bbox(t)
            if bb:
                rr = cv.create_rectangle(bb[0] - 6, bb[1] - 3, bb[2] + 6, bb[3] + 3, fill=C["HI"], outline="")
                cv.tag_lower(rr, t)

    def fit(self):
        if not self.nodes:
            return
        xs = [n["x"] for n in self.nodes.values()]
        ys = [n["y"] for n in self.nodes.values()]
        w, h = max(200, self.cv.winfo_width()), max(200, self.cv.winfo_height())
        bw, bh = max(xs) - min(xs) + 200, max(ys) - min(ys) + 200
        self.scale = max(0.15, min(2.0, min(w / bw, h / bh)))
        self.ox, self.oy = -(max(xs) + min(xs)) / 2, -(max(ys) + min(ys)) / 2
        self.redraw()

    def zoom_at(self, f: float, x: Optional[int] = None, y: Optional[int] = None):
        w, h = self.cv.winfo_width(), self.cv.winfo_height()
        x = w / 2 if x is None else x
        y = h / 2 if y is None else y
        wx = (x - w / 2) / self.scale - self.ox
        wy = (y - h / 2) / self.scale - self.oy
        self.scale = max(0.1, min(5.0, self.scale * f))
        self.ox = (x - w / 2) / self.scale - wx
        self.oy = (y - h / 2) / self.scale - wy
        self.redraw()

    # ------------------------------------------------------------ souris
    def node_at(self, x: int, y: int) -> Optional[str]:
        best, bd = None, 1e9
        for key, n in self.nodes.items():
            d = math.hypot(self.sx(n["x"]) - x, self.sy(n["y"]) - y)
            r = max(6, n["r"] * self.scale) + 3
            if d <= r and (n["kind"] == "item" or d < bd):
                if n["kind"] == "item" or best is None or self.nodes[best]["kind"] != "item":
                    best, bd = key, d
        return best

    def _motion(self, e):
        k = self.node_at(e.x, e.y)
        if k != self.hover:
            self.hover = k
            self.cv.configure(cursor="hand2" if k else "fleur")
            self.redraw()

    def _press(self, e):
        self.cv.focus_set()
        k = self.node_at(e.x, e.y)
        self.drag_key = k
        self.drag = (e.x, e.y, self.ox, self.oy, bool(k))
        self.moved = False

    def _motion_drag(self, e):
        if not self.drag:
            return
        x0, y0, ox, oy, on_node = self.drag
        if abs(e.x - x0) + abs(e.y - y0) > 4:
            self.moved = True
        if on_node and self.drag_key in self.nodes:
            n = self.nodes[self.drag_key]
            n["x"] = (e.x - self.cv.winfo_width() / 2) / self.scale - self.ox
            n["y"] = (e.y - self.cv.winfo_height() / 2) / self.scale - self.oy
            n["vx"] = n["vy"] = 0.0
            if self.anim and self.job is None:
                self.ticks = 40
                self.job = self.after(16, self._tick)
        else:
            self.ox = ox + (e.x - x0) / self.scale
            self.oy = oy + (e.y - y0) / self.scale
        self.redraw()

    def _release(self, e):
        k = self.drag_key if self.drag else None
        moved = getattr(self, "moved", False)
        self.drag = None
        if k and not moved and self.nodes.get(k, {}).get("kind") == "subject":
            self.open_node(k)

    def _double(self, e):
        k = self.node_at(e.x, e.y)
        if k:
            self.open_node(k)

    def open_node(self, k: str):
        n = self.nodes.get(k)
        if not n:
            return
        if n["kind"] == "subject":
            self.app.open_view(f"s:{n['id']}")
            self.app.reveal_subject(n["id"])
            self.app.set_status(f"🗺 Sujet ouvert : {n['label']} ({n['count']} fiche(s)).", "OK")
        else:
            self.app.goto_item(n["id"])
        self.app.lift()

    def _menu(self, e):
        k = self.node_at(e.x, e.y)
        m = new_menu(self)
        if k:
            n = self.nodes[k]
            m.add_command(label=("📂 Ouvrir ce sujet" if n["kind"] == "subject" else "📄 Ouvrir cette fiche"),
                          command=lambda: self.open_node(k))
            m.add_separator()
        m.add_command(label="🎯 Recentrer", command=self.fit)
        m.add_command(label="✨ Réorganiser", command=self.shake)
        m.add_command(label="✖ Fermer la carte", command=self.destroy)
        popup(m, e)

    def destroy(self):
        if self.job:
            try:
                self.after_cancel(self.job)
            except tk.TclError:
                pass
            self.job = None
        try:
            self.app._mindmap = None
        except Exception:
            pass
        super().destroy()


SPECIAL_VIEWS = [("v:all", "🗂", "Tout"), ("v:fav", "★", "Favoris"), ("v:pin", "📌", "Épinglés"),
                 ("v:recent", "🕘", "Récents"), ("v:tags", "🏷", "Étiquettes"), ("v:trash", "🗑", "Corbeille")]
SORTS = [("manual", "Ordre manuel"), ("recent", "Plus récents"), ("old", "Plus anciens"), ("title", "Titre A→Z"),
         ("type", "Par type"), ("event", "Date de l'info")]
PERIODS = [("", "Toutes les dates"), ("7", "7 derniers jours"), ("30", "30 derniers jours"), ("365", "Cette année")]
PANES_V = 1
TYPE_FILTERS = [("", "Tous les types")] + [(k, f"{TYPES[k]['icon']} {TYPES[k]['plural']}") for k in TYPE_ORDER]
