# -*- coding: utf-8 -*-
"""
Journal de bord 1.0 - Projet Padawan
Le journal de bord du capitaine : entrees privees (texte enrichi, humeur, meteo, lieu, etiquettes),
memos vocaux, images, fichiers et liens rendus PERMANENTS (copie locale de la page : HTML autonome,
capture, PDF ; video via yt-dlp), chronologie, calendrier, recherche, « Ce jour-la », partage facile
(page HTML autonome, PDF, .zip, texte, passage selectionne, Grimoire, Messager), verrou et entrees scellees.
Copier-coller au coeur : Ctrl+V de n'importe quoi devient la bonne piece ; Ctrl+C d'un passage copie
texte + version enrichie (images comprises).
Donnees : JOURNAL_DATA / PADAWAN_DATA\\Journal, sinon C:\\web_private\\journal (PC de Marc, hors du web),
sinon Documents\\Padawan\\Journal. Reglages : %APPDATA%\\Padawan\\journal.json.
Options : --nouvelle | --coller (capture le presse-papiers dans l'entree du jour, sans grande fenetre)
          --ouvrir ID | --selftest-core URL | --selftest | --screenshot FICHIER.png | --make-icons
"""
import os, sys, json, time, re, sqlite3, uuid, shutil, hashlib, hmac, base64, threading, queue, html
import subprocess, zipfile, tempfile, math, random, wave, struct, importlib, importlib.util, traceback
import datetime as dt
from html.parser import HTMLParser
from urllib.parse import urlparse
import padawan_commun as pc

APP = "Journal de bord"
VERSION = "1.4"
SETTINGS = "journal.json"
HERE = pc.HERE
IS_WIN = pc.IS_WIN
NOWIN = pc.NOWIN
EMB_RX = re.compile("\u27e6e:([0-9a-f]{6,32})\u27e7")
URL_RX = re.compile(r"(?i)\bhttps?://[^\s<>\"'\u27e6\u27e7]+[^\s<>\"'.,;:!?)\]\u27e6\u27e7]")
IMG_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
AUD_EXT = {".wav", ".mp3", ".ogg", ".m4a", ".flac", ".opus"}
VIDEO_HOSTS = ("youtube.com", "youtu.be", "vimeo.com", "tiktok.com", "dailymotion.com", "twitch.tv",
               "rumble.com", "odysee.com")
MOODS = [("\U0001f604", "Joyeux"), ("\U0001f642", "Bien"), ("\U0001f610", "Neutre"), ("\U0001f914", "Curieux"),
         ("\U0001f929", "\u00c9merveill\u00e9"), ("\U0001f614", "Pensif"), ("\U0001f622", "Triste"),
         ("\U0001f620", "F\u00e2ch\u00e9"), ("\U0001f634", "Fatigu\u00e9"), ("\U0001f680", "En mission")]
WEATHER = [("\u2600", "Soleil"), ("\u26c5", "Nuageux"), ("\u2601", "Couvert"), ("\U0001f327", "Pluie"),
           ("\u26c8", "Orage"), ("\u2744", "Neige"), ("\U0001f32b", "Brouillard"), ("\U0001f319", "Nuit \u00e9toil\u00e9e"),
           ("\U0001f308", "Arc-en-ciel")]
MOIS = ["janvier", "f\u00e9vrier", "mars", "avril", "mai", "juin", "juillet", "ao\u00fbt", "septembre", "octobre",
        "novembre", "d\u00e9cembre"]
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
FLAVOR = ["Journal de bord du capitaine, date stellaire {sd}.",
          "Journal personnel du capitaine, date stellaire {sd}. Rapport compl\u00e9mentaire.",
          "Date stellaire {sd}. Le vaisseau file en silence ; je consigne ceci.",
          "Journal de bord, date stellaire {sd}. Nous explorons de nouveaux mondes.",
          "Date stellaire {sd}. Note pour moi-m\u00eame, \u00e0 garder pr\u00e8s du c\u0153ur."]
DEFAULT_SETTINGS = {"animations": True, "mode_avance": False, "liens_auto": False, "wayback": False,
                    "verrou": {"actif": False, "sel": "", "hash": ""}, "verrou_propose": False,
                    "derniere": "", "jalons": [], "geometrie": "",
                    "fenetre": "agrandie",   # agrandie (par defaut) | plein | normale
                    "theme": "cosmos", "date_stellaire": False,
                    "debut_journee": 5, "quart_heures": 8, "horodatage": True}
STAMP_RX = re.compile(r"^(\*\*)?\d{1,2} h \d{2} \u2014")
STAMP_LINE = re.compile(r"^\s*(\*\*)?\s*(\w+ \d{1,2} \w+ \d{4} \u2014 )?\d{1,2} h \d{2}( \u2014)?\s*(\*\*)?\s*$")


def body_sans_stamps(md):
    return "\n".join(ln for ln in str(md or "").split("\n") if not STAMP_LINE.match(ln))


def stamp_text(d=None):
    d = d or dt.datetime.now()
    return f"{date_fr(d, False).capitalize()} \u2014 {d.hour} h {d.minute:02d}"
OPTS = {"stellaire": False}   # date stellaire : seulement si on la demande (Apparence)
TEMPLATES = [
    ("\u2600 Ma journ\u00e9e", "Ma journ\u00e9e",
     "# Ce qui s'est pass\u00e9 aujourd'hui\n\n# Ce qui m'a fait du bien\n\n# Ce que je retiens\n"),
    ("\U0001f4a1 Une id\u00e9e", "Une id\u00e9e",
     "# L'id\u00e9e\n\n# Pourquoi c'est int\u00e9ressant\n\n# Premier petit pas\n"),
    ("\U0001f64f Gratitude", "Gratitude",
     "# Aujourd'hui, je dis merci pour\u2026\n\u2022 \n\u2022 \n\u2022 \n"),
    ("\U0001f6e0 Travail", "Travail",
     "# Fait aujourd'hui\n\u2022 \n\n# \u00c0 faire ensuite\n\u2022 \n\n# Notes / questions\n"),
    ("\U0001f319 R\u00eave", "Un r\u00eave",
     "# Ce dont je me souviens\n\n# Ce que j'ai ressenti\n"),
    ("\U0001f333 Sortie nature", "Sortie nature",
     "# O\u00f9 je suis all\u00e9\n\n# Ce que j'ai vu, entendu, senti\n\n# Un moment \u00e0 garder\n"),
]
# Th\u00e8mes : chaque cl\u00e9 doit avoir une couleur distincte (le changement en direct remplace couleur par couleur)
THEMES = {
    "cosmos": ("\U0001f30c Cosmos (classique)", {}),
    "papier": ("\U0001f4dc Papier (clair, doux pour les yeux)", {
        "BG": "#f7f1e3", "PANEL": "#efe6d2", "CARD": "#fffaf0", "TEXT": "#2b2419", "DIM": "#7a6a55",
        "ACC": "#9a5b1e", "ACC2": "#b2452e", "ENTRY": "#fffdf7", "BTN": "#e6d9bf", "BTNH": "#d8c39b",
        "LINE": "#cdbb98", "DEEP": "#3a2f22", "OK": "#2e7d32", "REC": "#c62828", "WAX": "#a3263a",
        "WAX2": "#cf4a5c", "ONACC": "#fffef9", "SEL": "#f0d9a8"}),
    "nuit": ("\U0001f319 Nuit douce (sombre, chaleureux)", {
        "BG": "#1e1b24", "PANEL": "#26222e", "CARD": "#2f2a39", "TEXT": "#ece6f2", "DIM": "#a99fb8",
        "ACC": "#c9a7ff", "ACC2": "#ffb38a", "ENTRY": "#17151c", "BTN": "#3a3347", "BTNH": "#4b4160",
        "LINE": "#3d3550", "DEEP": "#0d0b12", "OK": "#8fe3a8", "REC": "#ff6b81", "WAX": "#a8243a",
        "WAX2": "#d9475b", "ONACC": "#1a1424", "SEL": "#5a4a78"}),
    "foret": ("\U0001f332 For\u00eat (nature, apaisant)", {
        "BG": "#14201a", "PANEL": "#1a2a21", "CARD": "#22362b", "TEXT": "#e9f2e6", "DIM": "#a7bfa9",
        "ACC": "#7fd18b", "ACC2": "#f2c46d", "ENTRY": "#0f1914", "BTN": "#2b4535", "BTNH": "#3a5c46",
        "LINE": "#30503c", "DEEP": "#08110c", "OK": "#b6f5bd", "REC": "#ff7a6b", "WAX": "#8c2f2f",
        "WAX2": "#c0504d", "ONACC": "#0c1a10", "SEL": "#3f6b4f"}),
}


# ------------------------------------------------------------------ chemins
def data_root():
    if hasattr(pc, "journal_dir"):
        return pc.journal_dir()
    env = os.environ.get("JOURNAL_DATA", "").strip()
    if env:
        return env
    root = os.environ.get("PADAWAN_DATA", "").strip()
    if root:
        return os.path.join(root, "Journal")
    if IS_WIN and os.path.isdir(r"C:\web"):
        return r"C:\web_private\journal"   # PC de Marc : hors de FTP_HOME (qui est servi sur le web)
    return os.path.join(os.path.expanduser("~"), "Documents", "Padawan", "Journal")


def settings():
    s = pc.load_settings(SETTINGS, json.loads(json.dumps(DEFAULT_SETTINGS)))
    for k, v in DEFAULT_SETTINGS.items():
        s.setdefault(k, v)
    return s


def save_settings(s):
    try:
        pc.save_settings(SETTINGS, s)
    except Exception:
        pass


def partages_dir():
    d = os.path.join(os.path.expanduser("~"), "Documents", "Padawan", "Journal-partages")
    os.makedirs(d, exist_ok=True)
    return d


def now_iso():
    return dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def parse_iso(s):
    try:
        return dt.datetime.strptime(str(s)[:19], "%Y-%m-%dT%H:%M:%S")
    except Exception:
        try:
            return dt.datetime.strptime(str(s)[:16].replace(" ", "T"), "%Y-%m-%dT%H:%M")
        except Exception:
            return dt.datetime.now()


def stardate(d=None):
    d = d or dt.datetime.now()
    doy = d.timetuple().tm_yday - 1
    days = 366 if (d.year % 4 == 0 and (d.year % 100 or d.year % 400 == 0)) else 365
    frac = (doy + d.hour / 24 + d.minute / 1440) / days
    return f"{(d.year - 1946) * 1000 + frac * 1000:.1f}"


def date_fr(d, heure=True):
    s = f"{JOURS[d.weekday()]} {d.day} {MOIS[d.month - 1]} {d.year}"
    return s + (f", {d.hour} h {d.minute:02d}" if heure else "")


def slug(s, n=50):
    s = pc.norm(s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return (s[:n] or "sans-titre").strip("-")


def human(n):
    n = float(n or 0)
    for u in ("o", "Ko", "Mo", "Go"):
        if n < 1024:
            return f"{n:.0f} {u}" if u == "o" else f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} To"


def fmt_dur(sec):
    sec = int(round(sec or 0))
    return f"{sec // 60}:{sec % 60:02d}"


def wav_duration(p):
    try:
        with wave.open(p, "rb") as w:
            return w.getnframes() / float(w.getframerate() or 1)
    except Exception:
        return 0.0


def has_module(name):
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


# ------------------------------------------------------------------ scellement (stdlib : PBKDF2 + flux BLAKE2b + HMAC)
MAGIC = b"JDB1"


def _keys(phrase, salt):
    dk = hashlib.pbkdf2_hmac("sha256", phrase.encode("utf-8"), salt, 240000, dklen=64)
    return dk[:32], dk[32:]


def _stream_xor(key, nonce, data):
    n = len(data)
    if not n:
        return b""
    blocks = []
    for i in range((n + 63) // 64):
        blocks.append(hashlib.blake2b(nonce + i.to_bytes(8, "big"), key=key, digest_size=64).digest())
    ks = b"".join(blocks)[:n]
    return (int.from_bytes(data, "big") ^ int.from_bytes(ks, "big")).to_bytes(n, "big")


def seal_bytes(phrase, data):
    salt, nonce = os.urandom(16), os.urandom(16)
    ek, mk = _keys(phrase, salt)
    ct = _stream_xor(ek, nonce, data)
    tag = hmac.new(mk, MAGIC + salt + nonce + ct, hashlib.sha256).digest()
    return MAGIC + salt + nonce + tag + ct


def unseal_bytes(phrase, blob):
    if blob[:4] != MAGIC:
        raise ValueError("format inconnu")
    salt, nonce, tag, ct = blob[4:20], blob[20:36], blob[36:68], blob[68:]
    ek, mk = _keys(phrase, salt)
    if not hmac.compare_digest(tag, hmac.new(mk, MAGIC + salt + nonce + ct, hashlib.sha256).digest()):
        raise ValueError("phrase incorrecte")
    return _stream_xor(ek, nonce, ct)


def pin_hash(pin, sel_hex):
    return hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), bytes.fromhex(sel_hex), 200000).hex()


# ------------------------------------------------------------------ stockage
class Journal:
    def __init__(self, root=None):
        self.root = root or data_root()
        for sub in ("", "medias", "liens", "scelles", "_corbeille"):
            os.makedirs(os.path.join(self.root, sub), exist_ok=True)
        self.lock = threading.RLock()
        self.emb_gen = {}
        self.db = sqlite3.connect(os.path.join(self.root, "journal.db"), check_same_thread=False, timeout=10)
        self.db.row_factory = sqlite3.Row
        with self.lock:
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.executescript("""
            CREATE TABLE IF NOT EXISTS entries(id TEXT PRIMARY KEY, created TEXT, updated TEXT, title TEXT,
              body TEXT, mood TEXT, weather TEXT, tags TEXT, lieu TEXT, sealed INTEGER DEFAULT 0, hint TEXT,
              deleted INTEGER DEFAULT 0, favori INTEGER DEFAULT 0, jour INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS embeds(id TEXT PRIMARY KEY, entry_id TEXT, kind TEXT, name TEXT, path TEXT,
              url TEXT, title TEXT, archive TEXT, status TEXT, transcript TEXT, created TEXT, meta TEXT);
            CREATE INDEX IF NOT EXISTS ix_emb_entry ON embeds(entry_id);
            CREATE INDEX IF NOT EXISTS ix_ent_created ON entries(created);
            """)
            self.db.commit()
        readme = os.path.join(self.root, "LISEZMOI.txt")
        if not os.path.isfile(readme):
            with open(readme, "w", encoding="utf-8") as f:
                f.write("Journal de bord (Padawan Suite) : tes entrees privees.\n"
                        "journal.db = les textes ; medias\\ = images, memos vocaux, fichiers ;\n"
                        "liens\\ = copies permanentes des pages web ; scelles\\ = entrees scellees (chiffrees).\n"
                        "Ne pas deplacer ce dossier dans un dossier publie sur le web.\n")

    def close(self):
        try:
            self.db.close()
        except Exception:
            pass

    # chemins
    def abs(self, rel):
        if rel and (os.path.isabs(str(rel)) or re.match(r"^[A-Za-z]:[\\/]", str(rel))):
            return str(rel)                       # copie gardee par l'Archiveur (chemin complet)
        return os.path.join(self.root, *str(rel or "").split("/")) if rel else ""

    def rel(self, p):
        return os.path.relpath(p, self.root).replace("\\", "/")

    def media_dir(self, entry_id, created=None):
        d = parse_iso(created) if created else dt.datetime.now()
        p = os.path.join(self.root, "medias", d.strftime("%Y-%m"), entry_id)
        os.makedirs(p, exist_ok=True)
        return p

    # entrees
    def new_entry(self, **kw):
        e = {"id": uuid.uuid4().hex[:16], "created": now_iso(), "updated": now_iso(), "title": "", "body": "",
             "mood": "", "weather": "", "tags": "", "lieu": "", "sealed": 0, "hint": "", "deleted": 0,
             "favori": 0, "jour": 0}
        e.update(kw)
        return e

    def save_entry(self, e):
        e["updated"] = now_iso()
        cols = ["id", "created", "updated", "title", "body", "mood", "weather", "tags", "lieu", "sealed", "hint",
                "deleted", "favori", "jour"]
        with self.lock:
            self.db.execute(f"INSERT OR REPLACE INTO entries({','.join(cols)}) VALUES({','.join('?' * len(cols))})",
                            [e.get(c, "") if c not in ("sealed", "deleted", "favori", "jour") else int(e.get(c) or 0)
                             for c in cols])
            self.db.commit()
        return e

    def exists(self, eid):
        with self.lock:
            return self.db.execute("SELECT 1 FROM entries WHERE id=?", (eid,)).fetchone() is not None

    def entry(self, eid):
        with self.lock:
            r = self.db.execute("SELECT * FROM entries WHERE id=?", (eid,)).fetchone()
        return dict(r) if r else None

    def entries(self, include_deleted=False):
        with self.lock:
            rows = self.db.execute("SELECT * FROM entries " + ("" if include_deleted else "WHERE deleted=0 ") +
                                   "ORDER BY created DESC").fetchall()
        return [dict(r) for r in rows]

    def count(self):
        with self.lock:
            return self.db.execute("SELECT COUNT(*) FROM entries WHERE deleted=0").fetchone()[0]

    def delete_entry(self, eid, undo=False):
        with self.lock:
            self.db.execute("UPDATE entries SET deleted=? WHERE id=?", (0 if undo else 1, eid))
            self.db.commit()

    def today_entry(self, create=True):
        today = dt.date.today().isoformat()
        with self.lock:
            r = self.db.execute("SELECT * FROM entries WHERE jour=1 AND deleted=0 AND sealed=0 AND substr(created,1,10)=? "
                                "ORDER BY created LIMIT 1", (today,)).fetchone()
        if r:
            return dict(r)
        if not create:
            return None
        d = dt.date.today()
        e = self.new_entry(title=f"\U0001f4cb Coll\u00e9 le {d.day} {MOIS[d.month - 1]}", jour=1, tags="coll\u00e9")
        return self.save_entry(e)

    # pieces
    def embeds(self, entry_id):
        with self.lock:
            rows = self.db.execute("SELECT * FROM embeds WHERE entry_id=? ORDER BY created", (entry_id,)).fetchall()
        return [dict(r) for r in rows]

    def embed(self, emb_id):
        with self.lock:
            r = self.db.execute("SELECT * FROM embeds WHERE id=?", (emb_id,)).fetchone()
        return dict(r) if r else None

    def save_embed(self, m):
        cols = ["id", "entry_id", "kind", "name", "path", "url", "title", "archive", "status", "transcript", "created",
                "meta"]
        m.setdefault("created", now_iso())
        if isinstance(m.get("meta"), dict):
            m["meta"] = json.dumps(m["meta"], ensure_ascii=False)
        self.emb_gen[m["entry_id"]] = self.emb_gen.get(m["entry_id"], 0) + 1
        with self.lock:
            self.db.execute(f"INSERT OR REPLACE INTO embeds({','.join(cols)}) VALUES({','.join('?' * len(cols))})",
                            [m.get(c) or "" for c in cols])
            self.db.commit()
        return m

    def update_embed(self, emb_id, **kw):
        m = self.embed(emb_id)
        if m:
            m.update(kw)
            self.save_embed(m)
        return m

    def remove_embed(self, emb_id):
        m = self.embed(emb_id)
        if not m:
            return
        dst = os.path.join(self.root, "_corbeille", time.strftime("%Y%m%d_%H%M%S") + "_" + emb_id)
        for rel in (m.get("path"), m.get("archive")):
            p = self.abs(rel)
            if p and os.path.exists(p):
                os.makedirs(dst, exist_ok=True)
                try:
                    shutil.move(p, os.path.join(dst, os.path.basename(p)))
                except Exception:
                    pass
        with self.lock:
            self.db.execute("DELETE FROM embeds WHERE id=?", (emb_id,))
            self.db.commit()

    def _new_emb(self, entry, kind, **kw):
        m = {"id": uuid.uuid4().hex[:12], "entry_id": entry["id"], "kind": kind, "name": "", "path": "", "url": "",
             "title": "", "archive": "", "status": "", "transcript": "", "meta": {}}
        m.update(kw)
        return m

    def _unique(self, folder, name):
        base, ext = os.path.splitext(name)
        base = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", base).strip(" .")[:80] or "piece"
        p, i = os.path.join(folder, base + ext), 2
        while os.path.exists(p):
            p = os.path.join(folder, f"{base} ({i}){ext}"); i += 1
        return p

    def add_file(self, entry, src):
        ext = os.path.splitext(src)[1].lower()
        kind = "image" if ext in IMG_EXT else ("audio" if ext in AUD_EXT else "file")
        dst = self._unique(self.media_dir(entry["id"], entry.get("created")), os.path.basename(src))
        if os.path.isdir(src):
            shutil.copytree(src, dst)
            kind = "file"
        else:
            shutil.copy2(src, dst)
        m = self._new_emb(entry, kind, name=os.path.basename(src), path=self.rel(dst),
                          meta={"taille": os.path.getsize(dst) if os.path.isfile(dst) else 0})
        if kind == "audio" and ext == ".wav":
            m["meta"]["duree"] = wav_duration(dst)
        return self.save_embed(m)

    def add_image(self, entry, img, name=None):
        name = name or time.strftime("image_%Y-%m-%d_%H%M%S.png")
        dst = self._unique(self.media_dir(entry["id"], entry.get("created")), name)
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA")
        img.save(dst, "PNG", optimize=True)
        m = self._new_emb(entry, "image", name=os.path.basename(dst), path=self.rel(dst),
                          meta={"taille": os.path.getsize(dst), "dim": list(img.size)})
        return self.save_embed(m)

    def add_image_bytes(self, entry, data, name):
        dst = self._unique(self.media_dir(entry["id"], entry.get("created")), name)
        with open(dst, "wb") as f:
            f.write(data)
        return self.save_embed(self._new_emb(entry, "image", name=os.path.basename(dst), path=self.rel(dst),
                                             meta={"taille": len(data)}))

    def add_audio(self, entry, wav_path, name=None):
        name = name or time.strftime("memo_%Y-%m-%d_%H%M%S.wav")
        dst = self._unique(self.media_dir(entry["id"], entry.get("created")), name)
        shutil.move(wav_path, dst)
        m = self._new_emb(entry, "audio", name=os.path.basename(dst), path=self.rel(dst),
                          meta={"duree": wav_duration(dst), "taille": os.path.getsize(dst)})
        return self.save_embed(m)

    def add_link(self, entry, url, title=""):
        host = (urlparse(url).hostname or "").lower()
        if host.startswith("www."):
            host = host[4:]
        m = self._new_emb(entry, "link", url=url, title=title or host or url, name=host, status="vivant")
        return self.save_embed(m)


def link_text_blob(j, m):
    """texte d'une copie permanente (pour la recherche)."""
    meta = m.get("meta")
    if isinstance(meta, str):
        try:
            meta = json.loads(meta or "{}")
        except Exception:
            meta = {}
    return str((meta or {}).get("texte", ""))[:20000]


# ------------------------------------------------------------------ mini-markdown du journal
# **gras**  _italique_  [texte](url)  ligne « # titre »  « • puce »  pieces : ⟦e:ID⟧
INLINE_RX = re.compile(r"\\(.)|\*\*|_|\[((?:\\.|[^\]\\\n])*)\]\(([^)\s]+)\)|\u27e6e:([0-9a-f]{6,32})\u27e7")


def md_escape(s):
    return re.sub(r"([\\*_\[\]])", r"\\\1", s)


def md_unescape(s):
    return re.sub(r"\\(.)", r"\1", s)


def md_lines(md):
    """-> [(niveau_titre, [tokens])] ; token = ("t", texte, bold, italic, url) | ("e", id)"""
    out = []
    for line in str(md or "").split("\n"):
        h = 0
        if line.startswith("# "):
            h, line = 1, line[2:]
        toks, bold, ital, pos = [], False, False, 0
        for m in INLINE_RX.finditer(line):
            if m.start() > pos:
                toks.append(("t", line[pos:m.start()], bold, ital, ""))
            g = m.group(0)
            if m.group(1) is not None:
                toks.append(("t", m.group(1), bold, ital, ""))
            elif g == "**":
                bold = not bold
            elif g == "_":
                ital = not ital
            elif m.group(4):
                toks.append(("e", m.group(4)))
            else:
                toks.append(("t", md_unescape(m.group(2)) or m.group(3), bold, ital, m.group(3)))
            pos = m.end()
        if pos < len(line):
            toks.append(("t", line[pos:], bold, ital, ""))
        out.append((h, toks))
    return out


def md_strip(md, n=None):
    """texte lisible sans balises ni pieces (apercus, titres auto)."""
    s = " ".join("".join(t[1] for t in toks if t[0] == "t") for _h, toks in md_lines(md))
    s = re.sub(r"\s+", " ", s).strip()
    return s[:n] if n else s


def md_embed_ids(md):
    return EMB_RX.findall(str(md or ""))


def embed_label(m):
    k = m.get("kind")
    if k == "image":
        return f"[Image : {m.get('name')}]"
    if k == "audio":
        t = (m.get("transcript") or "").strip()
        return f"[M\u00e9mo vocal : {m.get('name')}]" + (f"\n\u00ab {t} \u00bb" if t else "")
    if k == "link":
        return f"{m.get('title') or m.get('url')} \u2014 {m.get('url')}"
    return f"[Fichier : {m.get('name')}]"


def md_to_plain(md, embeds):
    em = {m["id"]: m for m in embeds}
    lines = []
    for h, toks in md_lines(md):
        s = ""
        for t in toks:
            if t[0] == "e":
                m = em.get(t[1])
                s += embed_label(m) if m else ""
            else:
                s += t[1] + (f" ({t[4]})" if t[4] and t[4] != t[1] else "")
        lines.append(s.upper() if h and len(s) < 80 else s)
    return "\n".join(lines).strip()


def entry_plain(e, embeds, header=True):
    d = parse_iso(e["created"])
    head = []
    if header:
        head.append(e.get("title") or "Entr\u00e9e sans titre")
        bits = [date_fr(d)] + ([f"date stellaire {stardate(d)}"] if OPTS["stellaire"] else [])
        if e.get("lieu"):
            bits.append(e["lieu"])
        if e.get("mood") or e.get("weather"):
            bits.append(" ".join(x for x in (e.get("mood"), e.get("weather")) if x))
        head.append(" \u00b7 ".join(bits))
        if e.get("tags"):
            head.append("\u00c9tiquettes : " + e["tags"])
        head.append("")
    return "\n".join(head) + md_to_plain(e.get("body"), embeds)


# ------------------------------------------------------------------ HTML colle -> mini-markdown
class _HtmlToMd(HTMLParser):
    BLOCK = {"p", "div", "section", "article", "header", "footer", "blockquote", "pre", "table", "tr", "ul", "ol",
             "h4", "h5", "h6", "figure", "dl", "dd", "dt"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.bold, self.ital, self.href, self.atext = [], 0, 0, None, []
        self.images, self.skip = [], 0

    def nl(self):
        if self.out and not "".join(self.out[-2:]).endswith("\n"):
            self.out.append("\n")

    def emit(self, s):
        if self.href is not None:
            self.atext.append(s)
        else:
            self.out.append(s)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style", "head", "title", "noscript"):
            self.skip += 1
        elif tag in ("b", "strong"):
            self.bold += 1
            if self.bold == 1:
                self.emit("**")
        elif tag in ("i", "em"):
            self.ital += 1
            if self.ital == 1:
                self.emit("_")
        elif tag == "a" and a.get("href", "").startswith(("http://", "https://")):
            self.href, self.atext = a["href"], []
        elif tag in ("h1", "h2", "h3"):
            self.nl(); self.out.append("# ")
        elif tag == "li":
            self.nl(); self.out.append("\u2022 ")
        elif tag == "br":
            self.out.append("\n")
        elif tag == "img" and a.get("src"):
            self.images.append(a["src"])
            self.out.append(f"\u27e6img:{len(self.images) - 1}\u27e7")
        elif tag in self.BLOCK or tag in ("td", "th"):
            if tag in ("td", "th"):
                self.out.append(" ")
            else:
                self.nl()

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head", "title", "noscript"):
            self.skip = max(0, self.skip - 1)
        elif tag in ("b", "strong"):
            self.bold = max(0, self.bold - 1)
            if self.bold == 0:
                self.emit("**")
        elif tag in ("i", "em"):
            self.ital = max(0, self.ital - 1)
            if self.ital == 0:
                self.emit("_")
        elif tag == "a" and self.href is not None:
            t = "".join(self.atext).strip()
            url, self.href = self.href, None
            self.out.append(f"[{t}]({url})" if t and t != url else url)
        elif tag in ("h1", "h2", "h3", "li") or tag in self.BLOCK:
            self.nl()

    def handle_data(self, d):
        if self.skip:
            return
        d = re.sub(r"[ \t\r\n]+", " ", d)
        if d:
            self.emit(md_escape(d))

    def result(self):
        s = "".join(self.out)
        s = s.replace("****", "").replace("**  **", " ")
        s = re.sub(r"\n[ \t]+", "\n", s)
        s = re.sub(r"\n{3,}", "\n\n", s)
        return s.strip(), self.images


def html_to_md(fragment):
    p = _HtmlToMd()
    try:
        p.feed(fragment); p.close()
    except Exception:
        pass
    return p.result()


def html_visible_text(fragment):
    md, imgs = html_to_md(fragment)
    return re.sub("\u27e6img:\\d+\u27e7", "", md).strip(), imgs


# ------------------------------------------------------------------ presse-papiers Windows (ctypes, sans dependance)
CF_DIB, CF_UNICODETEXT, CF_HDROP = 8, 13, 15


def _cb_api():
    import ctypes
    from ctypes import wintypes as W
    u, k, sh = ctypes.windll.user32, ctypes.windll.kernel32, ctypes.windll.shell32
    u.OpenClipboard.argtypes = [W.HWND]; u.OpenClipboard.restype = W.BOOL
    u.GetClipboardData.argtypes = [W.UINT]; u.GetClipboardData.restype = W.HANDLE
    u.SetClipboardData.argtypes = [W.UINT, W.HANDLE]; u.SetClipboardData.restype = W.HANDLE
    u.IsClipboardFormatAvailable.argtypes = [W.UINT]; u.IsClipboardFormatAvailable.restype = W.BOOL
    u.RegisterClipboardFormatW.argtypes = [W.LPCWSTR]; u.RegisterClipboardFormatW.restype = W.UINT
    k.GlobalAlloc.argtypes = [W.UINT, ctypes.c_size_t]; k.GlobalAlloc.restype = W.HGLOBAL
    k.GlobalLock.argtypes = [W.HGLOBAL]; k.GlobalLock.restype = ctypes.c_void_p
    k.GlobalUnlock.argtypes = [W.HGLOBAL]
    k.GlobalSize.argtypes = [W.HGLOBAL]; k.GlobalSize.restype = ctypes.c_size_t
    sh.DragQueryFileW.argtypes = [W.HANDLE, W.UINT, W.LPWSTR, W.UINT]; sh.DragQueryFileW.restype = W.UINT
    return ctypes, u, k, sh


def _cb_open(u):
    for _ in range(10):
        if u.OpenClipboard(None):
            return True
        time.sleep(0.05)
    return False


def _cf_html_id():
    return _cb_api()[1].RegisterClipboardFormatW("HTML Format")


def _cb_get_bytes(ctypes, u, k, fmt):
    h = u.GetClipboardData(fmt)
    if not h:
        return b""
    ptr = k.GlobalLock(h)
    try:
        return ctypes.string_at(ptr, k.GlobalSize(h)) if ptr else b""
    finally:
        k.GlobalUnlock(h)


def clipboard_read():
    """-> dict {files, image, html, text} (ce qui est present)."""
    res = {"files": [], "image": None, "html": "", "text": ""}
    try:
        from PIL import ImageGrab
        g = ImageGrab.grabclipboard()
        if isinstance(g, list):
            res["files"] = [p for p in g if isinstance(p, str) and os.path.exists(p)]
        elif g is not None:
            res["image"] = g
    except Exception:
        pass
    if not IS_WIN:
        return res
    try:
        ctypes, u, k, sh = _cb_api()
        fid = u.RegisterClipboardFormatW("HTML Format")
        if not _cb_open(u):
            return res
        try:
            if u.IsClipboardFormatAvailable(fid):
                raw = _cb_get_bytes(ctypes, u, k, fid).rstrip(b"\x00")
                m1, m2 = re.search(rb"StartFragment:(\d+)", raw), re.search(rb"EndFragment:(\d+)", raw)
                frag = raw[int(m1.group(1)):int(m2.group(1))] if m1 and m2 else raw
                res["html"] = frag.decode("utf-8", "replace")
            if u.IsClipboardFormatAvailable(CF_UNICODETEXT):
                raw = _cb_get_bytes(ctypes, u, k, CF_UNICODETEXT)
                res["text"] = raw.decode("utf-16-le", "replace").split("\x00", 1)[0]
            if not res["files"] and u.IsClipboardFormatAvailable(CF_HDROP):
                h = u.GetClipboardData(CF_HDROP)
                n = sh.DragQueryFileW(h, 0xFFFFFFFF, None, 0)
                for i in range(min(n, 200)):
                    ln = sh.DragQueryFileW(h, i, None, 0)
                    buf = ctypes.create_unicode_buffer(ln + 1)
                    sh.DragQueryFileW(h, i, buf, ln + 1)
                    if os.path.exists(buf.value):
                        res["files"].append(buf.value)
        finally:
            u.CloseClipboard()
    except Exception:
        traceback.print_exc()
    return res


def make_cf_html(fragment):
    pre = "Version:0.9\r\nStartHTML:{0:010d}\r\nEndHTML:{1:010d}\r\nStartFragment:{2:010d}\r\nEndFragment:{3:010d}\r\n"
    start = "<html><body><!--StartFragment-->"
    end = "<!--EndFragment--></body></html>"
    frag = fragment.encode("utf-8")
    hl = len(pre.format(0, 0, 0, 0).encode())
    sh = hl
    sf = sh + len(start.encode())
    ef = sf + len(frag)
    eh = ef + len(end.encode())
    return pre.format(sh, eh, sf, ef).encode() + start.encode() + frag + end.encode()


def clipboard_write(text, html_fragment="", image_path=""):
    """texte simple + HTML (images en data:) + image seule (CF_DIB) si une seule image."""
    if not IS_WIN:
        return False
    ctypes, u, k, sh = _cb_api()

    def put(fmt, data):
        h = k.GlobalAlloc(0x0002, len(data))
        ptr = k.GlobalLock(h)
        ctypes.memmove(ptr, data, len(data))
        k.GlobalUnlock(h)
        u.SetClipboardData(fmt, h)
    if not _cb_open(u):
        return False
    try:
        u.EmptyClipboard()
        put(CF_UNICODETEXT, (text or "").encode("utf-16-le") + b"\x00\x00")
        if html_fragment:
            put(u.RegisterClipboardFormatW("HTML Format"), make_cf_html(html_fragment) + b"\x00")
        if image_path and os.path.isfile(image_path):
            try:
                from PIL import Image
                import io
                im = Image.open(image_path).convert("RGB")
                b = io.BytesIO(); im.save(b, "BMP")
                put(CF_DIB, b.getvalue()[14:])
            except Exception:
                pass
    finally:
        u.CloseClipboard()
    return True


# ------------------------------------------------------------------ liens permanents
def find_browser():
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    pfx = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    la = os.environ.get("LOCALAPPDATA", "")
    for c in (os.path.join(pfx, "Microsoft", "Edge", "Application", "msedge.exe"),
              os.path.join(pf, "Microsoft", "Edge", "Application", "msedge.exe"),
              os.path.join(pf, "Google", "Chrome", "Application", "chrome.exe"),
              os.path.join(pfx, "Google", "Chrome", "Application", "chrome.exe"),
              os.path.join(la, "Google", "Chrome", "Application", "chrome.exe") if la else ""):
        if c and os.path.isfile(c):
            return c
    for n in ("msedge", "google-chrome", "chromium", "chrome"):
        w = shutil.which(n)
        if w:
            return w
    return None


def headless(url_or_file, out, mode="pdf", timeout=90):
    exe = find_browser()
    if not exe:
        return False
    prof = tempfile.mkdtemp(prefix="journal_nav_")
    args = [exe, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--mute-audio", "--no-first-run",
            "--no-default-browser-check", "--disable-extensions", f"--user-data-dir={prof}",
            "--virtual-time-budget=8000"]
    args += (["--no-pdf-header-footer", f"--print-to-pdf={out}"] if mode == "pdf"
             else ["--window-size=1280,2000", f"--screenshot={out}"])
    if not IS_WIN:
        args.insert(1, "--no-sandbox")
    try:
        p = subprocess.Popen(args + [url_or_file], creationflags=NOWIN, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        try:
            p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            p.kill()
    except Exception:
        return False
    finally:
        for _ in range(4):
            shutil.rmtree(prof, ignore_errors=True)
            if not os.path.isdir(prof):
                break
            time.sleep(0.5)
    return os.path.isfile(out) and os.path.getsize(out) > 800


def _console_python():
    exe = sys.executable or "python"
    if exe.lower().endswith("pythonw.exe"):
        c = exe[:-11] + "python.exe"
        if os.path.isfile(c):
            return c
    return exe


def is_video_url(url):
    h = (urlparse(url).hostname or "").lower()
    return any(h == v or h.endswith("." + v) for v in VIDEO_HOSTS)


def _archive_simple(url, folder, log):
    """secours si l'Archiveur n'est pas la : HTML (sans scripts) + capture + PDF."""
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Padawan-Journal"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read(30 * 1024 * 1024)
        ctype = r.headers.get("Content-Type", "")
    if "html" not in ctype.lower():
        name = os.path.basename(urlparse(url).path) or "document"
        with open(os.path.join(folder, name), "wb") as f:
            f.write(raw)
        return {"title": name, "main": name, "texte": ""}
    txt = raw.decode("utf-8", "replace")
    title = re.search(r"(?is)<title[^>]*>(.*?)</title>", txt)
    title = html.unescape(title.group(1).strip()) if title else url
    clean = re.sub(r"(?is)<script.*?</script>", "", txt)
    clean = re.sub(r"(?is)<head[^>]*>", lambda m: m.group(0) + f'<base href="{html.escape(url, True)}">', clean, count=1)
    with open(os.path.join(folder, "page.html"), "w", encoding="utf-8") as f:
        f.write(clean)
    md, _ = html_to_md(re.sub(r"(?is)<(nav|footer|header|aside)\b.*?</\1>", "", clean))
    plain = md_to_plain(md, [])
    with open(os.path.join(folder, "article.txt"), "w", encoding="utf-8") as f:
        f.write(f"{title}\n{url}\n\n{plain}\n")
    return {"title": title, "main": "page.html", "texte": plain}


def make_permanent(j, m, log=lambda s: None, wayback=False):
    """Copie locale d'un lien -> met a jour la piece (archive, status, meta). Retourne la piece."""
    url = m["url"]
    meta = json.loads(m.get("meta") or "{}") if isinstance(m.get("meta"), str) else dict(m.get("meta") or {})
    liens = os.path.join(j.root, "liens")
    res = {}
    host = slug((urlparse(url).hostname or "site").replace("www.", ""), 30)
    folder = None
    if is_video_url(url):
        folder = j._unique(liens, f"{time.strftime('%Y-%m-%d')}_{host}_video")
        os.makedirs(folder)
        log("Vid\u00e9o : copie avec yt-dlp\u2026")
        cmd = [_console_python(), "-m", "yt_dlp", "--no-playlist", "--no-progress", "-f",
               "bv*[height<=720][vcodec^=avc1]+ba[ext=m4a]/b[height<=720]/b", "--merge-output-format", "mp4",
               "--write-info-json", "--write-thumbnail", "-o", os.path.join(folder, "%(title).80s.%(ext)s"), url]
        try:
            r = subprocess.run(cmd, creationflags=NOWIN, capture_output=True, timeout=1800)
            vids = [f for f in os.listdir(folder) if f.lower().endswith((".mp4", ".webm", ".mkv", ".m4a"))]
            if vids:
                info = {}
                for f in os.listdir(folder):
                    if f.endswith(".info.json"):
                        info = pc.read_json(os.path.join(folder, f), {}) or {}
                res = {"title": info.get("title") or vids[0], "main": vids[0],
                       "texte": str(info.get("description") or "")[:20000]}
                thumbs = [f for f in os.listdir(folder) if f.lower().endswith((".jpg", ".webp", ".png"))]
                if thumbs:
                    res["capture"] = thumbs[0]
            else:
                log("yt-dlp n'a rien gard\u00e9 : " + (r.stderr or b"").decode("utf-8", "replace")[-200:])
                shutil.rmtree(folder, ignore_errors=True); folder = None
        except Exception as ex:
            log(f"yt-dlp : {ex}")
            shutil.rmtree(folder, ignore_errors=True); folder = None
    if not folder:
        try:
            if HERE not in sys.path:
                sys.path.insert(0, HERE)
            ar = importlib.import_module("archiveur5")
            info = ar.archive_webpage(url, liens, log, None, True)
            folder = os.path.join(liens, info.get("folder"))
            main = "page.html" if os.path.isfile(os.path.join(folder, "page.html")) else ""
            if not main:
                files = [f for f in os.listdir(folder) if not f.endswith((".json", ".txt"))]
                main = files[0] if files else ""
            res = {"title": info.get("title") or url, "main": main,
                   "capture": info.get("page_capture") or "", "pdf": info.get("page_pdf") or "",
                   "lecture": "lecture.html" if os.path.isfile(os.path.join(folder, "lecture.html")) else "",
                   "texte": str(info.get("description") or "")[:20000]}
        except Exception as ex:
            log(f"Archiveur indisponible ({ex}) : copie simple.")
            folder = j._unique(liens, f"{time.strftime('%Y-%m-%d')}_{host}")
            os.makedirs(folder)
            try:
                res = _archive_simple(url, folder, log)
                if headless(url, os.path.join(folder, "capture_page.png"), "png"):
                    res["capture"] = "capture_page.png"
                if headless(url, os.path.join(folder, "page_complete.pdf"), "pdf"):
                    res["pdf"] = "page_complete.pdf"
            except Exception as ex2:
                shutil.rmtree(folder, ignore_errors=True)
                j.update_embed(m["id"], status="erreur", meta=json.dumps(dict(meta, erreur=str(ex2)[:300])))
                raise
    if wayback:
        try:
            import urllib.request
            req = urllib.request.Request("https://web.archive.org/save/" + url, headers={"User-Agent": "Padawan-Journal"})
            with urllib.request.urlopen(req, timeout=90) as r:
                meta["wayback"] = r.geturl()
        except Exception as ex:
            log(f"Wayback : {ex}")
    meta.update({k: res.get(k, "") for k in ("main", "capture", "pdf", "lecture")})
    meta["texte"] = res.get("texte", "")
    meta["copie_le"] = now_iso()
    title = m.get("title")
    if not title or title == m.get("name"):
        title = res.get("title") or title
    return j.update_embed(m["id"], archive=j.rel(folder), status="permanent", title=title,
                          meta=json.dumps(meta, ensure_ascii=False))


# ------------------------------------------------------------------ 1.4 : apercus de liens + Archiveur
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"


def _http(url, timeout=12, limit=3_000_000, headers=None):
    import urllib.request
    h = {"User-Agent": UA, "Accept-Language": "fr-CA,fr;q=0.9,en;q=0.8"}
    h.update(headers or {})
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(limit), r.headers.get("Content-Type", ""), r.geturl()


def _http_json(url, timeout=12):
    raw, _c, _u = _http(url, timeout, headers={"Accept": "application/json"})
    return json.loads(raw.decode("utf-8", "replace"))


def _og(raw_html, *names):
    for n in names:
        mo = re.search(r'(?is)<meta[^>]+(?:property|name)=["\']' + re.escape(n) + r'["\'][^>]*content=["\']([^"\']*)', raw_html) or \
            re.search(r'(?is)<meta[^>]+content=["\']([^"\']*)["\'][^>]*(?:property|name)=["\']' + re.escape(n) + r'["\']', raw_html)
        if mo and mo.group(1).strip():
            return html.unescape(re.sub(r"\s+", " ", mo.group(1))).strip()
    return ""


def preview_dir(j):
    d = os.path.join(j.root, "apercus")
    os.makedirs(d, exist_ok=True)
    return d


def preview_cached(j, url):
    p = os.path.join(preview_dir(j), hashlib.sha1(url.encode("utf-8")).hexdigest()[:16] + ".json")
    return pc.read_json(p, None) if os.path.isfile(p) else None


def fetch_preview(j, url):
    """apercu d'un lien (titre, site, description, miniature) ; garde une copie dans apercus\\ (marche hors ligne)."""
    key = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
    d = preview_dir(j)
    jp = os.path.join(d, key + ".json")
    old = pc.read_json(jp, None) if os.path.isfile(jp) else None
    if old and (old.get("ok") or time.time() - float(old.get("t") or 0) < 3600):
        return old
    host = (urlparse(url).hostname or "").lower().replace("www.", "")
    res = {"url": url, "title": "", "site": host, "desc": "", "image": "", "author": "", "ok": False, "t": time.time()}
    img_url = ""
    try:
        if host in ("youtube.com", "m.youtube.com", "youtu.be", "music.youtube.com"):
            o = _http_json("https://www.youtube.com/oembed?format=json&url=" + urllib_quote(url))
            res.update(title=o.get("title", ""), author=o.get("author_name", ""), site="YouTube")
            img_url = o.get("thumbnail_url", "")
        elif host.endswith("vimeo.com"):
            o = _http_json("https://vimeo.com/api/oembed.json?url=" + urllib_quote(url))
            res.update(title=o.get("title", ""), author=o.get("author_name", ""), site="Vimeo",
                       desc=str(o.get("description") or "")[:300])
            img_url = o.get("thumbnail_url", "")
        elif host.endswith("tiktok.com"):
            o = _http_json("https://www.tiktok.com/oembed?url=" + urllib_quote(url))
            res.update(title=o.get("title", ""), author=o.get("author_name", ""), site="TikTok")
            img_url = o.get("thumbnail_url", "")
        elif host in ("x.com", "twitter.com", "mobile.twitter.com", "fxtwitter.com", "vxtwitter.com") and "/status/" in url:
            mo = re.search(r"/([A-Za-z0-9_]{1,15})/status(?:es)?/(\d+)", url)
            o = _http_json(f"https://api.fxtwitter.com/{mo.group(1)}/status/{mo.group(2)}")["tweet"]
            a = o.get("author") or {}
            txt = str(o.get("text") or "")
            res.update(title=(a.get("name") or "") + (f" (@{a.get('screen_name')})" if a.get("screen_name") else ""),
                       author=a.get("name") or "", site="X", desc=txt[:400])
            med = o.get("media") or {}
            if med.get("photos"):
                img_url = med["photos"][0].get("url", "")
            elif med.get("videos"):
                img_url = med["videos"][0].get("thumbnail_url", "")
                res["video"] = True
            else:
                img_url = a.get("avatar_url", "")
        if not res["title"]:
            raw, ctype, final = _http(url, 12, 1_500_000)
            if "html" in ctype.lower() or not ctype:
                t = raw.decode("utf-8", "replace")
                res["title"] = _og(t, "og:title", "twitter:title") or html.unescape(
                    re.sub(r"\s+", " ", (re.search(r"(?is)<title[^>]*>(.*?)</title>", t) or [None, ""])[1])).strip()
                res["desc"] = res["desc"] or _og(t, "og:description", "twitter:description", "description")[:400]
                res["site"] = _og(t, "og:site_name") or res["site"]
                img_url = img_url or _og(t, "og:image", "og:image:url", "twitter:image", "twitter:image:src")
                if img_url and img_url.startswith("/"):
                    pu = urlparse(final)
                    img_url = f"{pu.scheme}://{pu.netloc}{img_url}"
            else:
                res["title"] = os.path.basename(urlparse(url).path) or url
                res["desc"] = ctype
        res["title"] = res["title"][:200]
        res["ok"] = bool(res["title"] or res["desc"])
        if img_url:
            try:
                raw, _c, _u = _http(img_url, 15, 8_000_000)
                from PIL import Image
                import io
                im = Image.open(io.BytesIO(raw)).convert("RGB")
                im.thumbnail((480, 300))
                im.save(os.path.join(d, key + ".jpg"), "JPEG", quality=85)
                res["image"] = key + ".jpg"
            except Exception:
                pass
    except Exception as ex:
        res["erreur"] = str(ex)[:200]
    try:
        with open(jp, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False)
    except Exception:
        pass
    return res


def urllib_quote(u):
    from urllib.parse import quote
    return quote(u, safe="")


ARCH_SCRIPT = r"""
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
                         subtitles=bool(cfg.get("subtitles", True)), storyboard=True, tags=["Journal de bord"],
                         notes="Depuis le Journal de bord", web_capture=bool(cfg.get("web_capture", True)),
                         use_fx=bool(cfg.get("x_fxtwitter", True)), auto_convert=bool(cfg.get("auto_convert", True)))
    folder, dup = a.register_archive(root, info)["folder"], False
try:
    a.set_collections(root, [folder], add="Journal de bord")
except Exception:
    pass
print("@@R@@" + json.dumps({"root": root, "folder": folder, "dup": dup}), flush=True)
"""


def archiveur_ok():
    return os.path.isfile(os.path.join(HERE, "archiveur5.py"))


def archive_via_archiveur(url, on_event=lambda k, v: None, timeout=3600):
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    p = subprocess.Popen([_console_python(), "-c", ARCH_SCRIPT, HERE, url], cwd=HERE, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, text=True, encoding="utf-8",
                         errors="replace", creationflags=NOWIN, env=env)
    res, tail, t0 = None, [], time.time()
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
            p.kill(); break
    p.wait()
    if not res:
        fails = [x for x in tail if "FAIL" in x or "rror" in x]
        raise RuntimeError((fails or tail or ["l'Archiveur n'a rien gard\u00e9"])[-1][-240:])
    return res


def make_permanent_archiveur(j, m, on_event=lambda k, v: None):
    r = archive_via_archiveur(m["url"], on_event)
    folder = os.path.join(r["root"], r["folder"])
    files = os.listdir(folder) if os.path.isdir(folder) else []
    if not files:
        raise RuntimeError("dossier d'archive introuvable")
    info = pc.read_json(os.path.join(folder, "info.json"), {}) or {}
    vids = sorted([f for f in files if f.lower().endswith((".mp4", ".webm", ".mkv", ".mov", ".m4v", ".mp3", ".m4a", ".opus"))],
                  key=lambda f: -os.path.getsize(os.path.join(folder, f)))
    imgs = [f for f in files if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp")) and not f.startswith("sb_")]
    imgs.sort(key=lambda f: (0 if ("thumb" in f.lower() or "capture" in f.lower()) else 1, f))
    meta = emeta(m)
    meta.update({"source": "archiveur", "archiveur_dossier": r["folder"], "copie_le": now_iso(),
                 "main": vids[0] if vids else ("lecture.html" if "lecture.html" in files else
                                                ("page.html" if "page.html" in files else "index.html")),
                 "video": bool(vids and not vids[0].lower().endswith((".mp3", ".m4a", ".opus"))),
                 "index": "index.html" if "index.html" in files else "",
                 "lecture": "lecture.html" if "lecture.html" in files else "",
                 "pdf": next((f for f in files if f.lower().endswith(".pdf")), ""),
                 "capture": imgs[0] if imgs else "",
                 "texte": str(info.get("description") or info.get("text") or "")[:20000]})
    title = m.get("title") or info.get("title") or m["url"]
    return j.update_embed(m["id"], archive=folder, status="permanent", title=title, meta=json.dumps(meta, ensure_ascii=False))


def cheer(pct, log=""):
    if pct is None:
        if re.search(r"(?i)ffmpeg|convert|encod|remux|storyboard", log or ""):
            return "\U0001f39e L'Archiveur peaufine la copie\u2026 presque fini !"
        return "\U0001f6f0 L'Archiveur met ce lien \u00e0 l'abri\u2026 tu peux continuer d'\u00e9crire."
    p = int(pct)
    if p < 5:
        return "\U0001f680 C'est parti, on va chercher \u00e7a\u2026"
    if p < 40:
        return f"\U0001f4e5 {p} % \u2014 \u00e7a avance bien !"
    if p < 80:
        return f"\u2728 {p} % \u2014 plus de la moiti\u00e9 !"
    if p < 100:
        return f"\U0001f3c1 {p} % \u2014 derni\u00e8re ligne droite !"
    return "\U0001f39e T\u00e9l\u00e9charg\u00e9 ! L'Archiveur range la copie\u2026"


def fetch_title(url):
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 Padawan-Journal"})
        with urllib.request.urlopen(req, timeout=8) as r:
            if "html" not in r.headers.get("Content-Type", "html"):
                return ""
            raw = r.read(300000).decode("utf-8", "replace")
        m = re.search(r'(?is)<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)', raw) or \
            re.search(r"(?is)<title[^>]*>(.*?)</title>", raw)
        return html.unescape(re.sub(r"\s+", " ", m.group(1))).strip()[:200] if m else ""
    except Exception:
        return ""


def emeta(m):
    x = m.get("meta")
    if isinstance(x, dict):
        return x
    try:
        return json.loads(x or "{}")
    except Exception:
        return {}


# ------------------------------------------------------------------ partage : page HTML autonome
EXPORT_CSS = """
:root{--bg:#070b16;--card:#111a2e;--txt:#e8eefc;--dim:#9fb0d0;--acc:#3ad1c2;--acc2:#ffcc55}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);font:17px/1.65 'Segoe UI',system-ui,sans-serif;
background-image:radial-gradient(1px 1px at 10% 20%,#fff8,transparent),radial-gradient(1px 1px at 80% 10%,#fff6,transparent),
radial-gradient(1.5px 1.5px at 50% 70%,#fff5,transparent),radial-gradient(1px 1px at 30% 85%,#fff7,transparent),
radial-gradient(1px 1px at 92% 60%,#fff6,transparent),radial-gradient(ellipse at top,#16234a 0,#070b16 60%);background-attachment:fixed}
.wrap{max-width:860px;margin:auto;padding:2rem 1.2rem 4rem}
header.top{text-align:center;margin-bottom:2rem}header.top .sd{font-family:Consolas,monospace;color:var(--acc);letter-spacing:.08em}
header.top h1{margin:.3rem 0;font-size:2rem}
article{background:var(--card);border:1px solid #23345c;border-radius:16px;padding:1.4rem 1.6rem;margin:1.4rem 0;
box-shadow:0 10px 40px #0008}
article h2{margin:.1rem 0 .2rem;color:var(--acc2)}.meta{color:var(--dim);font-size:.9rem;margin-bottom:1rem}
.chip{display:inline-block;background:#1d2b4d;border-radius:99px;padding:.05rem .6rem;margin:.1rem .2rem .1rem 0;font-size:.85rem}
.body p{margin:.35rem 0}.body h3{color:var(--acc);margin:1rem 0 .3rem}.body li{margin:.15rem 0}
figure{margin:1rem 0;text-align:center}figure img{max-width:100%;border-radius:10px;box-shadow:0 4px 20px #0009}
figcaption{color:var(--dim);font-size:.85rem}audio{width:100%;margin:.4rem 0}
.piece{background:#0b1324;border:1px solid #23345c;border-radius:12px;padding:.8rem 1rem;margin:.8rem 0}
.piece .t{font-weight:600}.piece small{color:var(--dim)}a{color:var(--acc)}
.piece img.cap{max-width:100%;border-radius:8px;margin-top:.5rem;max-height:420px;object-fit:cover;object-position:top}
details{margin-top:.5rem}summary{cursor:pointer;color:var(--acc2)}details pre{white-space:pre-wrap;font:14px/1.5 Georgia,serif;
max-height:420px;overflow:auto;background:#070d1a;padding:.8rem;border-radius:8px}
.badge{color:#55ff99;font-size:.85rem}.tr{font-style:italic;color:var(--dim)}
footer{text-align:center;color:var(--dim);font-size:.85rem;margin-top:3rem}
@media print{body{background:#fff;color:#111}article,.piece{background:#fff;border-color:#ccc;box-shadow:none}
.meta,.piece small,figcaption,footer{color:#555}article h2{color:#8a5a00}a{color:#0b5cad}}
"""


def _b64(path, mime):
    with open(path, "rb") as f:
        return f"data:{mime};base64," + base64.b64encode(f.read()).decode()


def _img_data(path, maxw=1600):
    try:
        from PIL import Image
        import io
        im = Image.open(path)
        if im.width > maxw or os.path.getsize(path) > 2_500_000:
            im = im.convert("RGB")
            im.thumbnail((maxw, maxw * 4))
            b = io.BytesIO(); im.save(b, "JPEG", quality=85)
            return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()
    except Exception:
        pass
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    return _b64(path, "image/" + ("jpeg" if ext in ("jpg", "jpeg") else ext or "png"))


MIME_AUD = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".ogg": "audio/ogg", ".m4a": "audio/mp4", ".flac": "audio/flac",
            ".opus": "audio/ogg"}


def embed_html(j, m, rel_files=None, compact=False):
    """rel_files : dict id->chemin relatif (export .zip) ; sinon tout est integre."""
    e = html.escape
    p = j.abs(m.get("path"))
    k = m.get("kind")
    if k == "image" and os.path.isfile(p):
        src = rel_files.get(m["id"]) if rel_files else _img_data(p)
        return f'<figure><img src="{src}" alt="{e(m.get("name", ""))}"><figcaption>{e(m.get("name", ""))}</figcaption></figure>'
    if k == "audio" and compact:
        tr = (m.get("transcript") or "").strip()
        return f'<p>\U0001f399 <em>M\u00e9mo vocal ({e(m.get("name", ""))})</em>' + (f" : \u00ab {e(tr)} \u00bb" if tr else "") + "</p>"
    if k == "file" and compact:
        return f'<p>\U0001f4ce <em>{e(m.get("name", ""))}</em></p>'
    if k == "audio" and os.path.isfile(p):
        src = rel_files.get(m["id"]) if rel_files else _b64(p, MIME_AUD.get(os.path.splitext(p)[1].lower(), "audio/wav"))
        tr = (m.get("transcript") or "").strip()
        return (f'<div class="piece"><div class="t">\U0001f399 M\u00e9mo vocal</div><audio controls src="{src}"></audio>'
                + (f'<div class="tr">\u00ab {e(tr)} \u00bb</div>' if tr else "") + "</div>")
    if k == "link":
        meta = emeta(m)
        url = m.get("url", "")
        s = (f'<div class="piece"><div class="t">\U0001f517 <a href="{e(url, True)}" target="_blank" rel="noopener">'
             f'{e(m.get("title") or url)}</a></div><small>{e(url)}</small>')
        if m.get("status") == "permanent":
            s += f'<div class="badge">\U0001f6e1 Copie permanente du {e(str(meta.get("copie_le", ""))[:10])}</div>'
            folder = j.abs(m.get("archive"))
            cap = os.path.join(folder, meta.get("capture") or "") if meta.get("capture") else ""
            if not compact and cap and os.path.isfile(cap):
                src = rel_files.get(m["id"] + ":cap") if rel_files else _img_data(cap, 1100)
                if src:
                    s += f'<img class="cap" src="{src}" alt="capture">'
            if rel_files and rel_files.get(m["id"] + ":main"):
                s += f'<div><a href="{e(rel_files[m["id"] + ":main"], True)}">Ouvrir la copie locale</a></div>'
            if not compact and meta.get("texte"):
                s += f'<details><summary>Texte de la page (copie)</summary><pre>{e(meta["texte"][:30000])}</pre></details>'
            if meta.get("wayback"):
                s += f'<div><small>Wayback : <a href="{e(meta["wayback"], True)}">{e(meta["wayback"])}</a></small></div>'
        return s + "</div>"
    if k == "file" and (os.path.isfile(p) or rel_files):
        size = os.path.getsize(p) if os.path.isfile(p) else 0
        if rel_files and rel_files.get(m["id"]):
            link = f'<a href="{e(rel_files[m["id"]], True)}">t\u00e9l\u00e9charger</a>'
        elif size <= 12 * 1024 * 1024:
            link = f'<a download="{e(m.get("name", "fichier"), True)}" href="{_b64(p, "application/octet-stream")}">t\u00e9l\u00e9charger</a>'
        else:
            link = "<small>(trop gros pour la page : utilise l'export .zip)</small>"
        return f'<div class="piece"><div class="t">\U0001f4ce {e(m.get("name", ""))}</div><small>{human(size)}</small> \u00b7 {link}</div>'
    return ""


def md_to_html(j, md, embeds, rel_files=None, compact=False):
    em = {m["id"]: m for m in embeds}
    out, in_list = [], False
    for h, toks in md_lines(md):
        parts, blocks = [], []
        for t in toks:
            if t[0] == "e":
                if em.get(t[1]):
                    blocks.append(embed_html(j, em[t[1]], rel_files, compact))
                continue
            s = html.escape(t[1])
            if t[2]:
                s = f"<strong>{s}</strong>"
            if t[3]:
                s = f"<em>{s}</em>"
            if t[4]:
                s = f'<a href="{html.escape(t[4], True)}" target="_blank" rel="noopener">{s}</a>'
            parts.append(s)
        line = "".join(parts)
        plain = re.sub(r"<[^>]+>", "", line)
        is_li = plain.startswith("\u2022 ")
        if is_li and not in_list:
            out.append("<ul>"); in_list = True
        if not is_li and in_list:
            out.append("</ul>"); in_list = False
        if h and line.strip():
            out.append(f"<h3>{line}</h3>")
        elif is_li:
            out.append("<li>" + line.replace("\u2022 ", "", 1) + "</li>")
        elif line.strip():
            out.append(f"<p>{line}</p>")
        out.extend(blocks)
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def entry_html(j, e, embeds, rel_files=None, compact=False):
    d = parse_iso(e["created"])
    chips = []
    if e.get("mood"):
        chips.append(e["mood"])
    if e.get("weather"):
        chips.append(e["weather"])
    if e.get("lieu"):
        chips.append("\U0001f4cd " + e["lieu"])
    chips += ["#" + t.strip() for t in str(e.get("tags") or "").split(",") if t.strip()]
    x = html.escape
    ttl = e.get("title") or "Entr\u00e9e sans titre"
    return (f'<article><h2>{x(ttl)}</h2>'
            f'<div class="meta">{x(date_fr(d))}' + (f' \u00b7 date stellaire {stardate(d)}' if OPTS["stellaire"] else '') + '<br>'
            + "".join(f'<span class="chip">{x(c)}</span>' for c in chips) + "</div>"
            f'<div class="body">{md_to_html(j, e.get("body"), embeds, rel_files, compact)}</div></article>')


def page_html(title, articles_html, sub=""):
    x = html.escape
    sd = stardate()
    return (f'<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" '
            f'content="width=device-width,initial-scale=1"><title>{x(title)}</title><style>{EXPORT_CSS}</style></head>'
            f'<body><div class="wrap"><header class="top"><div class="sd">\u2726 JOURNAL DE BORD \u00b7 DATE STELLAIRE {sd} \u2726</div>'
            f'<h1>{x(title)}</h1><div style="color:#9fb0d0">{x(sub)}</div></header>{articles_html}'
            f'<footer>Partag\u00e9 depuis le Journal de bord \u00b7 Padawan Suite \u00b7 {x(date_fr(dt.datetime.now()))}</footer>'
            f'</div></body></html>')


def export_html(j, entry_ids, out_path, title=None):
    arts, n = [], 0
    for eid in entry_ids:
        e = j.entry(eid)
        if not e or e.get("sealed") or e.get("deleted"):
            continue   # jamais d'entree scellee ou supprimee dans un partage
        arts.append(entry_html(j, e, j.embeds(eid))); n += 1
    if not n:
        raise ValueError("Rien \u00e0 partager (les entr\u00e9es scell\u00e9es ne sont jamais partag\u00e9es).")
    if not title:
        title = (j.entry(entry_ids[0]).get("title") or "Journal de bord") if n == 1 else f"Journal de bord \u2014 {n} entr\u00e9es"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(page_html(title, "\n".join(arts)))
    return out_path


def export_segment_html(j, e, md, out_path):
    ids = set(md_embed_ids(md))
    embeds = [m for m in j.embeds(e["id"]) if m["id"] in ids]
    pseudo = dict(e, body=md, title=(e.get("title") or "Entr\u00e9e") + " \u2014 extrait")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(page_html(pseudo["title"], entry_html(j, pseudo, embeds), "Un passage partag\u00e9 de mon journal"))
    return out_path


def export_pdf(j, entry_ids, out_pdf):
    tmp = os.path.join(tempfile.mkdtemp(prefix="journal_pdf_"), "page.html")
    try:
        export_html(j, entry_ids, tmp)
        ok = headless("file:///" + tmp.replace("\\", "/"), out_pdf, "pdf")
        if not ok:
            raise RuntimeError("Edge ou Chrome est n\u00e9cessaire pour le PDF (la page HTML, elle, marche toujours).")
        return out_pdf
    finally:
        shutil.rmtree(os.path.dirname(tmp), ignore_errors=True)


def export_zip(j, entry_ids, out_zip):
    arts, n = [], 0
    with zipfile.ZipFile(out_zip + ".part", "w", zipfile.ZIP_DEFLATED) as z:
        for eid in entry_ids:
            e = j.entry(eid)
            if not e or e.get("sealed") or e.get("deleted"):
                continue
            embeds = j.embeds(eid)
            rel = {}
            base = f"pieces/{parse_iso(e['created']).strftime('%Y-%m-%d')}_{slug(e.get('title'), 30)}_{eid[:6]}"
            for m in embeds:
                p = j.abs(m.get("path"))
                if p and os.path.isfile(p):
                    rel[m["id"]] = f"{base}/{os.path.basename(p)}"
                    z.write(p, rel[m["id"]])
                if m.get("kind") == "link" and m.get("archive"):
                    folder = j.abs(m["archive"])
                    meta = emeta(m)
                    if os.path.isdir(folder):
                        lb = f"{base}/lien_{m['id'][:6]}"
                        for dp, _dn, fns in os.walk(folder):
                            for fn in fns:
                                fp = os.path.join(dp, fn)
                                z.write(fp, lb + "/" + os.path.relpath(fp, folder).replace("\\", "/"))
                        if meta.get("main"):
                            rel[m["id"] + ":main"] = f"{lb}/{meta['main']}"
                        if meta.get("capture"):
                            rel[m["id"] + ":cap"] = f"{lb}/{meta['capture']}"
            arts.append(entry_html(j, e, embeds, rel)); n += 1
        if not n:
            raise ValueError("Rien \u00e0 partager.")
        title = "Journal de bord" + (f" \u2014 {n} entr\u00e9es" if n > 1 else "")
        z.writestr("index.html", page_html(title, "\n".join(arts), "Ouvre index.html : tout est dans ce dossier."))
        z.writestr("LISEZMOI.txt", "Ouvre index.html dans ton navigateur. Les pieces et les copies de pages sont dans pieces\\.\r\n")
    os.replace(out_zip + ".part", out_zip)
    return out_zip


def send_to_grimoire(j, e, embeds):
    script = os.path.join(HERE, "grimoire1.py")
    if not os.path.isfile(script):
        raise RuntimeError("Grimoire introuvable.")
    txt = entry_plain(e, embeds)
    args = [pc.pythonw(), script, "--ajouter", txt, "--titre", (e.get("title") or "Entr\u00e9e du journal")[:300],
            "--sujet", "Journal de bord", "--source", "Journal de bord"]
    if e.get("tags"):
        args += ["--etiquettes", e["tags"]]
    r = subprocess.run(args, cwd=HERE, creationflags=NOWIN, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.PIPE, timeout=180)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or b"").decode("utf-8", "replace")[-300:] or "erreur Grimoire")
    return True


# ------------------------------------------------------------------ IA locale (Ollama, facultatif)
def ollama_model():
    cfg = pc.read_json(os.path.join(HERE, "config.json"), {}) or {}
    return cfg.get("model") or cfg.get("modele") or "dolphin3:8b"


def ollama_ask(prompt, timeout=300):
    import urllib.request
    base = os.environ.get("JOURNAL_OLLAMA_URL", "").strip() or "http://127.0.0.1:11434"
    try:
        with urllib.request.urlopen(base + "/api/tags", timeout=3) as r:
            names = [m.get("name") for m in json.loads(r.read().decode()).get("models", [])]
    except Exception:
        raise RuntimeError("L'IA locale (Ollama) n'est pas lanc\u00e9e sur ce PC. Le reste du journal marche sans elle.")
    model = ollama_model()
    if names and model not in names:
        model = "dolphin3:8b" if "dolphin3:8b" in names else names[0]
    body = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode()
    req = urllib.request.Request(base + "/api/generate", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return model, (json.loads(r.read().decode("utf-8", "replace")).get("response") or "").strip()


def journal_context(j, entries, limit=40, chars=1200):
    out = []
    for e in entries[:limit]:
        if e.get("sealed"):
            continue
        d = parse_iso(e["created"])
        out.append(f"--- {date_fr(d)} | {e.get('title') or ''} | {e.get('mood') or ''} {e.get('lieu') or ''}\n"
                   + md_to_plain(e.get("body"), j.embeds(e["id"]))[:chars])
    return "\n".join(out)


def weekly_summary(j):
    since = (dt.datetime.now() - dt.timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S")
    es = [e for e in j.entries() if e["created"] >= since and not e.get("sealed")]
    if not es:
        return "", "Aucune entr\u00e9e cette semaine \u2014 le vaisseau attend ton prochain rapport, capitaine !"
    prompt = ("Tu es l'officier des communications du vaisseau. Voici les entr\u00e9es de journal de bord du capitaine "
              "des 7 derniers jours. Tutoie-le. Fais en fran\u00e7ais un r\u00e9sum\u00e9 chaleureux et vivant (5 \u00e0 10 phrases) : "
              "les moments forts, l'humeur g\u00e9n\u00e9rale, les fils \u00e0 suivre. Termine par une phrase inspirante "
              "fa\u00e7on \u00ab Fin du rapport \u00bb. N'invente rien.\n\n" + journal_context(j, es))
    return ollama_ask(prompt)


def ask_journal(j, question):
    terms = [t for t in pc.norm(question).split() if len(t) > 3]
    es = [e for e in j.entries() if not e.get("sealed")]
    if not es:
        return "", "Ton journal est encore vierge, capitaine : \u00e9cris quelques entr\u00e9es et je pourrai te r\u00e9pondre !"
    if not question.strip():
        return "", "Pose-moi une question, par exemple : \u00ab Qu'est-ce que j'ai fait au chalet cet \u00e9t\u00e9 ? \u00bb"
    scored = []
    for e in es:
        hay = pc.norm(" ".join([e.get("title") or "", e.get("body") or "", e.get("tags") or "", e.get("lieu") or ""]))
        scored.append((sum(hay.count(t) for t in terms), e))
    scored.sort(key=lambda x: -x[0])
    pick = [e for s, e in scored if s > 0][:25] or es[:15]
    prompt = ("Tu es Padawan, l'assistant local du capitaine. Tutoie-le. R\u00e9ponds en fran\u00e7ais, de fa\u00e7on vivante et "
              "d\u00e9velopp\u00e9e, en t'appuyant SEULEMENT sur ces extraits de son journal (cite les dates). "
              "Si \u00e7a ne suffit pas, dis-le gentiment.\n\nQuestion : " + question + "\n\nExtraits :\n" + journal_context(j, pick))
    return ollama_ask(prompt)


# ------------------------------------------------------------------ entrees scellees
def seal_entry(j, eid, phrase, hint=""):
    e = j.entry(eid)
    if not e or e.get("sealed"):
        raise ValueError("Entr\u00e9e introuvable ou d\u00e9j\u00e0 scell\u00e9e.")
    embeds = j.embeds(eid)
    import io
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("entree.json", json.dumps({"entry": e, "embeds": embeds}, ensure_ascii=False))
        for m in embeds:
            for key in ("path", "archive"):
                p = j.abs(m.get(key))
                if p and os.path.isfile(p):
                    z.write(p, "f/" + m[key])
                elif p and os.path.isdir(p):
                    for dp, _d, fns in os.walk(p):
                        for fn in fns:
                            fp = os.path.join(dp, fn)
                            z.write(fp, "f/" + j.rel(fp))
    blob = seal_bytes(phrase, buf.getvalue())
    out = os.path.join(j.root, "scelles", eid + ".scelle")
    with open(out + ".tmp", "wb") as f:
        f.write(blob)
    os.replace(out + ".tmp", out)
    unseal_bytes(phrase, open(out, "rb").read())  # verification avant d'effacer quoi que ce soit
    for m in embeds:
        for key in ("path", "archive"):
            p = j.abs(m.get(key))
            if p and os.path.isfile(p):
                os.remove(p)
            elif p and os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
        with j.lock:
            j.db.execute("DELETE FROM embeds WHERE id=?", (m["id"],))
    j.db.commit()
    md = os.path.join(j.root, "medias", parse_iso(e["created"]).strftime("%Y-%m"), eid)
    if os.path.isdir(md) and not os.listdir(md):
        os.rmdir(md)
    sealed = dict(e, title="\U0001f512 Entr\u00e9e scell\u00e9e", body="", tags="", lieu="", mood="", weather="",
                  sealed=1, hint=hint)
    j.save_entry(sealed)
    return out


def open_sealed(j, eid, phrase):
    """-> (entree, pieces, dossier_temporaire) ; rien n'est remis en clair dans le journal."""
    blob = open(os.path.join(j.root, "scelles", eid + ".scelle"), "rb").read()
    data = unseal_bytes(phrase, blob)
    import io
    tmp = tempfile.mkdtemp(prefix="journal_scelle_")
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        d = json.loads(z.read("entree.json").decode("utf-8"))
        for n in z.namelist():
            if n.startswith("f/") and ".." not in n:
                dst = os.path.join(tmp, *n[2:].split("/"))
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with open(dst, "wb") as f:
                    f.write(z.read(n))
    return d["entry"], d["embeds"], tmp


def unseal_entry(j, eid, phrase):
    e, embeds, tmp = open_sealed(j, eid, phrase)
    try:
        for dp, _d, fns in os.walk(tmp):
            for fn in fns:
                fp = os.path.join(dp, fn)
                dst = os.path.join(j.root, os.path.relpath(fp, tmp))
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.move(fp, dst)
        for m in embeds:
            j.save_embed(m)
        e["sealed"] = 0
        j.save_entry(e)
        os.remove(os.path.join(j.root, "scelles", eid + ".scelle"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return e


# ------------------------------------------------------------------ recherche
_HAY = {}


def entry_haystack(j, e):
    key = (e.get("updated"), getattr(j, "emb_gen", {}).get(e["id"], 0))
    c = _HAY.get(e["id"])
    if c and c[0] == key:
        return c[1]
    parts = [e.get("title"), e.get("body"), e.get("tags"), e.get("lieu"), e.get("mood"), e.get("weather")]
    for m in j.embeds(e["id"]):
        parts += [m.get("name"), m.get("title"), m.get("url"), m.get("transcript"), link_text_blob(j, m)]
    hay = pc.norm(" ".join(str(p or "") for p in parts))
    _HAY[e["id"]] = (key, hay)
    return hay


def search(j, q, entries=None):
    terms = [t for t in pc.norm(q).split() if t]
    entries = entries if entries is not None else j.entries()
    if not terms:
        return entries
    return [e for e in entries if not e.get("sealed") and all(t in entry_haystack(j, e) for t in terms)]


# ------------------------------------------------------------------ coller (sans interface)
def _fetch_img(src, base=""):
    try:
        if src.startswith("data:image/"):
            head, b = src.split(",", 1)
            ext = head.split("/")[1].split(";")[0]
            return base64.b64decode(b), "." + ("jpg" if ext == "jpeg" else ext)
        if src.startswith("file:///"):
            from urllib.request import url2pathname
            p = url2pathname(src[8:])
            return open(p, "rb").read(), os.path.splitext(p)[1] or ".png"
        if src.startswith(("http://", "https://")):
            import urllib.request
            req = urllib.request.Request(src, headers={"User-Agent": "Mozilla/5.0 Padawan-Journal"})
            with urllib.request.urlopen(req, timeout=15) as r:
                data = r.read(15 * 1024 * 1024)
                ct = r.headers.get("Content-Type", "image/png")
            ext = "." + (ct.split("/")[-1].split(";")[0].replace("jpeg", "jpg") if "/" in ct else "png")
            return data, ext if len(ext) <= 5 else ".img"
    except Exception:
        return None, None
    return None, None


def clip_to_md(j, entry, clip=None, log=lambda s: None):
    """Transforme le presse-papiers en morceau de journal. -> (md, [pieces creees], resume)"""
    clip = dict({"text": "", "html": "", "files": [], "image": None}, **(clip or clipboard_read()))
    new, md = [], ""
    if clip["files"]:
        for p in clip["files"][:40]:
            m = j.add_file(entry, p); new.append(m)
        md = "\n".join(f"\u27e6e:{m['id']}\u27e7" for m in new)
        return md, new, f"{len(new)} fichier(s)"
    html_md, imgs = ("", [])
    if clip["html"]:
        vis, imgs = html_visible_text(clip["html"])
        if vis:
            html_md, imgs = html_to_md(clip["html"])
    if html_md:
        def rep(mo):
            i = int(mo.group(1))
            data, ext = _fetch_img(imgs[i]) if i < len(imgs) and i < 12 else (None, None)
            if not data:
                return ""
            m = j.add_image_bytes(entry, data, f"image_collee_{i + 1}{ext}"); new.append(m)
            return f"\n\u27e6e:{m['id']}\u27e7\n"
        md = re.sub("\u27e6img:(\\d+)\u27e7", rep, html_md)
        return md.strip(), new, "texte enrichi" + (f" + {len(new)} image(s)" if new else "")
    if clip["image"] is not None:
        m = j.add_image(entry, clip["image"], time.strftime("capture_%Y-%m-%d_%H%M%S.png")); new.append(m)
        return f"\u27e6e:{m['id']}\u27e7", new, "une image"
    if clip["html"] and imgs:   # HTML sans texte : une image de page web
        for i, src in enumerate(imgs[:6]):
            data, ext = _fetch_img(src)
            if data:
                new.append(j.add_image_bytes(entry, data, f"image_collee_{i + 1}{ext}"))
        if new:
            return "\n".join(f"\u27e6e:{m['id']}\u27e7" for m in new), new, f"{len(new)} image(s)"
    t = (clip["text"] or "").strip()
    if not t:
        return "", [], ""
    if URL_RX.fullmatch(t):
        m = j.add_link(entry, t, fetch_title(t)); new.append(m)
        return f"\u27e6e:{m['id']}\u27e7", new, "un lien"
    return autolink_md(md_escape(t)), [], "du texte"


def autolink_md(md):
    return URL_RX.sub(lambda mo: f"[{mo.group(0)}]({mo.group(0)})", md)


def append_to_entry(j, e, md):
    e = j.entry(e["id"]) or e
    stamp = time.strftime("%H:%M")
    e["body"] = (e.get("body") or "").rstrip() + ("\n\n" if e.get("body") else "") + f"_{stamp}_ \u00b7 " + md
    return j.save_entry(e)


# ================================================================== interface
C = dict(pc.C)
C.update({"DEEP": "#070b16", "REC": "#ff4d6d", "OK": "#55ff99", "WAX": "#b3263a", "WAX2": "#e0485c", "LINE": "#2a3b63",
          "ONACC": "#06121f", "SEL": "#2f5597"})
C_COSMOS = dict(C)
THEMES["cosmos"] = (THEMES["cosmos"][0], dict(C_COSMOS))


def theme_colors(key):
    pal = dict(C_COSMOS)
    pal.update(THEMES.get(key, THEMES["cosmos"])[1])
    return pal
EMOJI_FONT = ("Segoe UI Emoji", 13)


def _mix(c1, c2, t):
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{int(a[k] + (b[k] - a[k]) * max(0, min(1, t))):02x}" for k in range(3))


class Anim:
    """Animations legeres (Tk pur, ~30 i/s, courtes, toutes desactivables)."""

    def __init__(self, app):
        self.app = app

    @property
    def k(self):
        return getattr(self.app, "ui_scale", 1.0)

    @property
    def on(self):
        return bool(self.app.st.get("animations", True))

    # ---- ouverture : saut en distorsion dans un champ d'etoiles
    def warp(self, root, done, seconds=2.1, full=False):
        import tkinter as tk
        if not self.on:
            done(); return
        top = tk.Toplevel(root); top.overrideredirect(True); top.configure(bg=C["DEEP"])
        sw, sh = top.winfo_screenwidth(), top.winfo_screenheight()
        q = self.k
        w, h = (sw, sh) if full else (int(640 * q), int(360 * q))
        top.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")
        try:
            top.attributes("-topmost", True)
        except Exception:
            pass
        cv = tk.Canvas(top, width=w, height=h, bg=C["DEEP"], highlightthickness=0 if full else 1,
                       highlightbackground=C["ACC"])
        cv.pack(fill="both", expand=True)
        z = max(1.0, min(3.0, w / (640.0 * q)))           # plein ecran : etoiles plus loin, plus nombreuses
        zf, z = z, z * q                                    # zf : polices (deja en points) ; z : distances en pixels
        cx, cy = w / 2, h / 2 - 20 * z
        rmax = math.hypot(w, h) / 2 + 20
        stars = []
        for _ in range(int(90 * min(2.4, zf))):
            a = random.uniform(0, 2 * math.pi)
            stars.append([a, random.uniform(2, 40 * z), random.uniform(0.6, 1.6), cv.create_line(0, 0, 0, 0, fill="#ffffff"),
                          None])
        shades = [_mix(C["DEEP"], "#ffffff", i / 12.0) for i in range(13)]   # 13 teintes pre-calculees (leger pour le CPU)
        f1, f2 = int(20 * min(zf, 1.9)), int(11 * min(zf, 1.6))
        now = dt.datetime.now()
        hr = now.hour
        greet = ("Bonne nuit" if hr < 5 else "Bon matin" if hr < 12 else "Bon apr\u00e8s-midi" if hr < 18 else "Bonne soir\u00e9e")
        fd = int(f1 * 1.7)
        hello = cv.create_text(cx, cy - fd * 1.5 * q, text=f"{greet} !", fill=C["DEEP"], font=("Segoe UI", f2 + 2))
        bigd = cv.create_text(cx, cy, text=date_fr(now, False).capitalize(), fill=C["DEEP"], font=("Segoe UI", fd, "bold"))
        bigh = cv.create_text(cx, cy + fd * 1.25 * q, text=f"{now.hour} h {now.minute:02d}", fill=C["DEEP"], font=("Segoe UI", f2 + 4))
        title = cv.create_text(cx, h * 0.80, text="", fill=C["TEXT"], font=("Segoe UI", f1, "bold"))
        sub = cv.create_text(cx, h * 0.80 + f1 * 1.9 * q, text="", fill=C["ACC"], font=("Consolas", f2))
        cv.create_text(cx, h - 18 * z, text="clic ou \u00c9chap pour passer", fill="#3d4d6e", font=("Segoe UI", 8 + int(zf > 1.5)))
        t0 = time.time()
        state = {"done": False, "shown": False}
        full_t = "\U0001f4d3 Journal de bord"
        full_s = (f"date stellaire {stardate()} \u00b7 tout reste \u00e0 bord" if OPTS["stellaire"]
                  else "tout reste sur ce PC")
        fade = 0.45

        def reveal():
            if not state["shown"]:
                state["shown"] = True
                done()                                     # la fenetre se prepare SOUS le champ d'etoiles
                try:
                    top.lift(); top.attributes("-topmost", True)
                except Exception:
                    pass

        def stop(_e=None):
            if state["done"]:
                return
            state["done"] = True
            reveal()
            try:
                top.destroy()
            except Exception:
                pass
            try:
                root.lift(); root.focus_force()
            except Exception:
                pass
        for wdg in (top, cv):
            wdg.bind("<Button-1>", stop)
        top.bind("<Escape>", stop); top.bind("<Key>", stop)
        top.focus_force()

        def tick():
            if state["done"]:
                return
            t = time.time() - t0
            if t > seconds:
                stop(); return
            if t > seconds - fade:
                reveal()
                try:
                    top.attributes("-alpha", max(0.0, (seconds - t) / fade))
                except Exception:
                    pass
            # 0-0.7 s : la date apparait (etoiles calmes) ; ensuite : le saut, la date s'envole
            kd = min(1.0, t / 0.35) if t < 0.9 else max(0.0, 1 - (t - 0.9) / 0.45)
            cv.itemconfigure(bigd, fill=_mix(C["DEEP"], "#ffffff", kd))
            cv.itemconfigure(hello, fill=_mix(C["DEEP"], C["ACC2"], kd))
            cv.itemconfigure(bigh, fill=_mix(C["DEEP"], C["ACC"], kd))
            tt = max(0.0, t - 0.7)
            speed = 0.4 + 14 * min(1.0, tt / 0.6) * (1 - max(0, tt - 0.8) / 0.6 * 0.85)
            for s in stars:
                s[1] += s[2] * speed * 2.2 * z
                if s[1] > rmax:
                    s[1] = random.uniform(2, 20 * z)
                r1, r2 = s[1], s[1] + s[2] * speed * 3.2 * z
                x1, y1 = cx + math.cos(s[0]) * r1, cy + math.sin(s[0]) * r1
                x2, y2 = cx + math.cos(s[0]) * r2, cy + math.sin(s[0]) * r2
                cv.coords(s[3], x1, y1, x2, y2)
                look = (int(12 * min(1, s[1] / (120 * z))), (1 + (speed > 8)) * (2 if z > 2 else 1))
                if look != s[4]:
                    s[4] = look
                    cv.itemconfigure(s[3], fill=shades[look[0]], width=look[1])
            if t > 1.0:
                k = min(1.0, (t - 1.0) / 0.4)
                cv.itemconfigure(title, text=full_t[:max(1, int(len(full_t) * k))])
            if t > 1.3:
                k = min(1.0, (t - 1.3) / 0.4)
                cv.itemconfigure(sub, text=full_s[:int(len(full_s) * k)])
            top.after(33, tick)
        top.after(10, tick)

    # ---- sceau de cire « Journal enregistre »
    def seal(self, parent, text="JOURNAL ENREGISTR\u00c9"):
        import tkinter as tk
        if not self.on:
            return
        size = int(150 * self.k)
        cv = tk.Canvas(parent, width=size, height=size, bg=C["BG"], highlightthickness=0)
        cv.place(relx=1.0, x=-size - 24, y=6)
        t0 = time.time()
        c = size / 2

        def tick():
            t = time.time() - t0
            try:
                cv.delete("all")
            except Exception:
                return
            if t > 1.5:
                cv.destroy(); return
            if t < 0.25:
                k = 1.6 - 0.6 * (t / 0.25)          # le sceau tombe (grand -> normal)
            else:
                k = 1.0 + 0.04 * math.sin((t - 0.25) * 18) * max(0, 0.6 - t)
            fade = 0 if t < 1.0 else (t - 1.0) / 0.5
            r = 46 * k * self.k
            wax, wax2 = _mix(C["WAX"], C["BG"], fade), _mix(C["WAX2"], C["BG"], fade)
            pts = []
            for i in range(28):
                a = i / 28 * 2 * math.pi
                rr = r * (1 + 0.07 * math.sin(i * 2.7))
                pts += [c + math.cos(a) * rr, c + math.sin(a) * rr]
            cv.create_polygon(pts, fill=wax, outline="", smooth=True)
            cv.create_oval(c - r * 0.72, c - r * 0.72, c + r * 0.72, c + r * 0.72, outline=wax2, width=2)
            star = []
            for i in range(10):
                a = -math.pi / 2 + i * math.pi / 5
                rr = r * (0.42 if i % 2 == 0 else 0.18)
                star += [c + math.cos(a) * rr, c + math.sin(a) * rr]
            cv.create_polygon(star, fill=_mix("#ffd9a0", C["BG"], fade), outline="")
            if t > 0.2:
                cv.create_text(c, c + r + 12, text=text, fill=_mix(C["ACC2"], C["BG"], fade), font=("Segoe UI", 8, "bold"))
            cv.after(30, tick)
        tick()

    # ---- confettis d'etoiles (jalons)
    def confetti(self, parent, message):
        import tkinter as tk
        w, h = parent.winfo_width() or 900, parent.winfo_height() or 600
        cv = tk.Canvas(parent, width=w, height=h, bg=C["BG"], highlightthickness=0)
        cv.place(x=0, y=0, relwidth=1, relheight=1)
        cols = [C["ACC"], C["ACC2"], "#ff7eb6", "#9b8cff", "#ffffff", C["OK"]]
        v = max(1.0, min(2.6, w / 900.0))                 # grand ecran : les etoiles vont plus loin
        parts = [[w / 2, h / 2, random.uniform(-9, 9) * v, random.uniform(-14, -4) * v ** 0.5, random.choice(cols),
                  random.uniform(4, 9) * self.k] for _ in range(int(120 * min(1.8, v)) if self.on else 0)]
        t0 = time.time()

        def star(x, y, r, col):
            pts = []
            for i in range(10):
                a = -math.pi / 2 + i * math.pi / 5
                rr = r if i % 2 == 0 else r * 0.45
                pts += [x + math.cos(a) * rr, y + math.sin(a) * rr]
            cv.create_polygon(pts, fill=col, outline="")

        def tick():
            t = time.time() - t0
            try:
                cv.delete("all")
            except Exception:
                return
            if t > (3.0 if self.on else 2.2):
                cv.destroy(); return
            for p in parts:
                p[0] += p[2]; p[1] += p[3]; p[3] += 0.35 * v ** 0.5; p[2] *= 0.99
                star(p[0], p[1], p[5], p[4])
            cv.create_text(w / 2, h / 2 - 40, text=message, fill=C["ACC2"], font=("Segoe UI", int(22 + 8 * (v - 1) / 1.6), "bold"))
            cv.after(33, tick)
        cv.bind("<Button-1>", lambda e: cv.destroy())
        tick()

    # ---- machine a ecrire
    def typewrite(self, label, text, speed=22):
        if not self.on:
            label.configure(text=text); return
        label._tw = getattr(label, "_tw", 0) + 1
        tok = label._tw

        def step(i=0):
            if getattr(label, "_tw", 0) != tok:
                return
            try:
                label.configure(text=text[:i] + ("\u258c" if i < len(text) else ""))
            except Exception:
                return
            if i < len(text):
                label.after(speed, step, i + 1)
        step()

    # ---- apparition douce (couleur fg : fond -> normal)
    def fade_in(self, widgets, delay=0):
        if not self.on:
            return
        items = []
        for wdg in widgets:
            try:
                items.append((wdg, wdg.cget("fg"), wdg.cget("bg")))
                wdg.configure(fg=wdg.cget("bg"))
            except Exception:
                pass
        t0 = time.time() + delay

        def tick():
            t = (time.time() - t0) / 0.28
            for wdg, fg, bg in items:
                try:
                    if fg.startswith("#") and bg.startswith("#"):
                        wdg.configure(fg=_mix(bg, fg, t))
                except Exception:
                    pass
            if t < 1 and items:
                items[0][0].after(30, tick)
        if items:
            items[0][0].after(int(max(0, delay) * 1000) + 10, tick)

    # ---- capsule qui se verrouille (scellement) / se deverrouille
    def capsule(self, root, text, work, done, unlock=False):
        """affiche l'animation pendant que work() tourne dans un fil ; done(resultat|Exception) ensuite."""
        import tkinter as tk
        top = tk.Toplevel(root); top.overrideredirect(True); top.configure(bg=C["PANEL"])
        q = self.k
        lw, lh = 360, 230                                   # dessin en unites logiques, mis a l'echelle de l'ecran
        w, h = int(lw * q), int(lh * q)
        x = root.winfo_rootx() + (root.winfo_width() - w) // 2
        y = root.winfo_rooty() + (root.winfo_height() - h) // 3
        top.geometry(f"{w}x{h}+{max(0, x)}+{max(0, y)}")
        try:
            top.attributes("-topmost", True)
        except Exception:
            pass
        cv = tk.Canvas(top, width=w, height=h, bg=C["PANEL"], highlightthickness=1, highlightbackground=C["ACC"])
        cv.pack()
        res = {}
        th = threading.Thread(target=lambda: res.setdefault("r", _try(work)), daemon=True)
        th.start()
        t0 = time.time()
        cx, cy = lw / 2, 96

        def tick():
            t = time.time() - t0
            cv.delete("all")
            h = lh
            ang = t * (5 if self.on else 0)
            for i in range(12):
                a = ang + i * math.pi / 6
                r1, r2 = 62, 70
                cv.create_line(cx + math.cos(a) * r1, cy + math.sin(a) * r1, cx + math.cos(a) * r2, cy + math.sin(a) * r2,
                               fill=_mix(C["PANEL"], C["ACC"], (i + 1) / 12), width=3)
            cv.create_oval(cx - 34, cy - 50, cx + 34, cy + 50, fill="#22325a", outline=C["ACC"], width=2)
            cv.create_line(cx - 34, cy, cx + 34, cy, fill=C["ACC"], width=2)
            closed = (min(1.0, t / 0.9) if not unlock else 1 - min(1.0, t / 0.9))
            sh = -14 + 10 * closed
            cv.create_arc(cx - 13, cy - 22 + sh - 13, cx + 13, cy - 22 + sh + 13, start=0, extent=180, style="arc",
                          outline=C["ACC2"], width=4)
            cv.create_rectangle(cx - 17, cy - 24, cx + 17, cy + 2, fill=C["ACC2"], outline="")
            cv.create_text(cx, h - 46, text=text, fill=C["TEXT"], font=("Segoe UI", 11, "bold"))
            cv.create_text(cx, h - 24, text="un instant\u2026", fill=C["DIM"], font=("Segoe UI", 9))
            if q != 1.0:
                cv.scale("all", 0, 0, q, q)
            if not th.is_alive() and t > (1.0 if self.on else 0):
                top.destroy(); done(res.get("r")); return
            top.after(33, tick)
        tick()


def _try(fn):
    try:
        return fn()
    except Exception as ex:
        traceback.print_exc()
        return ex


class JournalApp:
    def __init__(self, args):
        import tkinter as tk
        from tkinter import ttk
        self.tk, self.ttk = tk, ttk
        self.args = args
        self.st = settings()
        OPTS["stellaire"] = bool(self.st.get("date_stellaire"))
        if self.st.get("theme") not in THEMES:
            self.st["theme"] = "cosmos"
        C.update(theme_colors(self.st.get("theme")))
        self.anim = Anim(self)
        self.j = Journal()
        self.dnd = None
        try:
            import tkinterdnd2
            self.root = tkinterdnd2.TkinterDnD.Tk()
            self.dnd = tkinterdnd2
        except Exception:
            self.root = tk.Tk()
        r = self.root
        self._update_title()
        r.configure(bg=C["BG"])
        try:
            r.iconbitmap(os.path.join(HERE, "journal_bord.ico") if os.path.isfile(os.path.join(HERE, "journal_bord.ico"))
                         else os.path.join(HERE, "padawan_tray.ico"))
        except Exception:
            pass
        sw, sh = r.winfo_screenwidth(), r.winfo_screenheight()
        try:
            self.ui_scale = max(1.0, r.winfo_fpixels("1i") / 96.0)   # 1.5 sur un ecran Windows a 150 %
        except Exception:
            self.ui_scale = 1.0
        if os.environ.get("JOURNAL_ECHELLE"):                    # tests : simuler un autre ecran (ex. 1.0 = 100 %)
            self.ui_scale = float(os.environ["JOURNAL_ECHELLE"])
            r.tk.call("tk", "scaling", self.ui_scale * 96 / 72.0)
        q = self.ui_scale
        w, h = min(int(1280 * q), sw - 40), min(int(820 * q), sh - 80)
        geo = self.st.get("geometrie") or f"{w}x{h}+{(sw - w) // 2}+{max(0, (sh - h) // 2 - 20)}"
        if "--taille" in args:
            geo = args[args.index("--taille") + 1] + "+0+0"
        elif "--selftest" in args or "--screenshot" in args:
            geo = f"{w}x{h}+{(sw - w) // 2}+{max(0, (sh - h) // 2 - 20)}"
        m = re.match(r"(\d+)x(\d+)\+(-?\d+)\+(-?\d+)$", geo or "")
        if m and (int(m.group(3)) > sw - 80 or int(m.group(4)) > sh - 80 or int(m.group(3)) < -200):
            geo = f"{w}x{h}+{(sw - w) // 2}+{max(0, (sh - h) // 2 - 20)}"   # ecran change : on recentre
        r.geometry(geo)
        r.minsize(self.px(900), self.px(560))
        self.full = False
        lsw = sw / q                                         # largeur « logique » de l'ecran
        self.fs = 12 + (1 if lsw >= 1900 else 0) + (1 if lsw >= 2500 else 0)   # grands ecrans : texte un peu plus grand
        self.q = queue.Queue()
        self.cur = None             # entree courante (dict)
        self.dirty = False
        self.save_job = None
        self.cards = {}             # chemin widget -> id piece
        self.card_frames = {}       # id piece -> frame
        self.imgs = []              # references PhotoImage
        self.link_urls = {}
        self.link_n = 0
        self.view = "chrono"
        self.day_filter = None
        self.cal_month = dt.date.today().replace(day=1)
        self.playing = None
        self.playing_btn = None
        self.copying = set()
        self.loading = False
        r.protocol("WM_DELETE_WINDOW", self.on_close)
        self._single_instance_server()          # des le depart (meme verrouille) : Ctrl+Alt+J/K arrivent ici
        r.after(120, self._poll_queue)
        self._style()
        if self.st["verrou"].get("actif") and self.st["verrou"].get("hash"):
            r.withdraw()
            r.after(50, self._lock_screen)
        elif "--selftest" in args or "--screenshot" in args or "--sans-anim" in args:
            self._show_window()
            self._build()
        else:
            r.withdraw()
            r.after(30, lambda: self.anim.warp(r, self._after_intro, full=self._window_mode() != "normale"))

    def px(self, n):
        return int(round(n * getattr(self, "ui_scale", 1.0)))

    def _after_intro(self):
        self._show_window()
        self._build()

    # ------------------------------------------------------------ fenetre : agrandie par defaut, F11 plein ecran
    def _window_mode(self):
        a = self.args
        if "--fenetre" in a and a.index("--fenetre") + 1 < len(a):
            return a[a.index("--fenetre") + 1]
        if "--taille" in a or "--selftest" in a or "--screenshot" in a:
            return "normale"
        mode = self.st.get("fenetre") or "agrandie"
        return mode if mode in ("agrandie", "plein", "normale") else "agrandie"

    def _show_window(self):
        r = self.root
        mode = self._window_mode()
        try:
            r.deiconify()
        except Exception:
            pass
        if mode in ("agrandie", "plein"):
            try:
                r.state("zoomed")
            except Exception:
                try:
                    r.attributes("-zoomed", True)
                except Exception:
                    pass
        if mode == "plein":
            self.set_fullscreen(True, quiet=True)
        try:
            r.update_idletasks()
        except Exception:
            pass

    def set_fullscreen(self, on=None, quiet=False):
        on = (not self.full) if on is None else bool(on)
        try:
            self.root.attributes("-fullscreen", on)
        except Exception:
            return
        self.full = on
        if on and not quiet and hasattr(self, "st_lbl"):
            self.toast("\u26f6 Plein \u00e9cran \u2014 F11 ou \u00c9chap pour revenir.", seconds=3)

    def _esc(self, _e=None):
        if self.full:
            self.set_fullscreen(False)
            return "break"

    def _style(self):
        s = self.ttk.Style(self.root)
        try:
            s.theme_use("clam")
        except Exception:
            pass
        s.configure("J.TCombobox", fieldbackground=C["ENTRY"], background=C["BTN"], foreground=C["TEXT"],
                    arrowcolor=C["TEXT"], bordercolor=C["LINE"])
        s.map("J.TCombobox", fieldbackground=[("readonly", C["ENTRY"])], foreground=[("readonly", C["TEXT"])])
        s.configure("J.Vertical.TScrollbar", background=C["BTN"], troughcolor=C["BG"], bordercolor=C["BG"],
                    arrowcolor=C["TEXT"])
        self.root.option_add("*TCombobox*Listbox.background", C["ENTRY"])
        self.root.option_add("*TCombobox*Listbox.foreground", C["TEXT"])

    # ------------------------------------------------------------ petits outils
    def btn(self, parent, text, cmd, acc=False, small=False, bg=None, tip=None):
        b = self.tk.Button(parent, text=text, command=cmd, bg=bg or (C["ACC"] if acc else C["BTN"]),
                           fg=C["ONACC"] if acc else C["TEXT"], activebackground=C["BTNH"], activeforeground=C["TEXT"],
                           relief="flat", bd=0, font=("Segoe UI", 9 if small else 10, "bold"),
                           padx=8 if small else 12, pady=3 if small else 5, cursor="hand2")
        if tip:
            self._tip(b, tip)
        return b

    def _tip(self, w, text):
        tk = self.tk
        st = {"t": None}

        def show(_e):
            if st["t"]:
                return
            t = tk.Toplevel(w); t.overrideredirect(True)
            t.geometry(f"+{w.winfo_rootx() + 10}+{w.winfo_rooty() + w.winfo_height() + 4}")
            tk.Label(t, text=text, bg="#fff8d0", fg="#222", font=("Segoe UI", 9), padx=6, pady=3).pack()
            st["t"] = t

        def hide(_e):
            if st["t"]:
                st["t"].destroy(); st["t"] = None
        w.bind("<Enter>", show, add="+"); w.bind("<Leave>", hide, add="+")

    def toast(self, text, actions=(), seconds=4.5):
        tk = self.tk
        f = tk.Frame(self.root, bg=C["CARD"], highlightthickness=1, highlightbackground=C["ACC"], padx=12, pady=8)
        tk.Label(f, text=text, bg=C["CARD"], fg=C["TEXT"], font=("Segoe UI", 10), wraplength=self.px(420),
                 justify="left").pack(side="left")
        for lab, fn in actions:
            self.btn(f, lab, lambda fn=fn: (fn(), f.destroy()), acc=True, small=True).pack(side="left", padx=4)
        for wdg in [f] + list(f.winfo_children()):
            if isinstance(wdg, tk.Label):
                wdg.bind("<Button-1>", lambda e: f.winfo_exists() and f.destroy())
        if self.anim.on:                                   # glisse doucement depuis la droite
            t0 = time.time()

            def slide():
                if not f.winfo_exists():
                    return
                k = min(1.0, (time.time() - t0) / 0.22)
                k = 1 - (1 - k) ** 3
                f.place(relx=1.0, rely=1.0, x=int(-18 + (1 - k) * self.px(460)), y=-40, anchor="se")
                if k < 1:
                    f.after(15, slide)
            slide()
        else:
            f.place(relx=1.0, rely=1.0, x=-18, y=-40, anchor="se")
        f.after(int(seconds * 1000), lambda: f.winfo_exists() and f.destroy())

    def status(self, text, ok=False):
        try:
            self.st_lbl.configure(text=text, fg=C["OK"] if ok else C["DIM"])
        except Exception:
            pass

    def _poll_queue(self):
        try:
            while True:
                fn = self.q.get_nowait()
                try:
                    fn()
                except Exception:
                    traceback.print_exc()
        except queue.Empty:
            pass
        self._poll_cmds()
        self.root.after(150, self._poll_queue)

    def ui(self, fn):
        self.q.put(fn)

    def bg(self, work, done=None, err=None):
        def run():
            try:
                r = work()
                if done:
                    self.ui(lambda: done(r))
            except Exception as ex:
                traceback.print_exc()
                msg = str(ex)
                self.ui(lambda: (err or (lambda m: self.toast("\u26a0 " + m)))(msg))
        threading.Thread(target=run, daemon=True).start()

    # ------------------------------------------------------------ verrou
    def _lock_screen(self):
        tk = self.tk
        top = tk.Toplevel(self.root); top.title(APP); top.configure(bg=C["BG"])
        self._lock_top = top
        lw, lh = self.px(420), self.px(260)
        top.geometry(f"{lw}x{lh}+{top.winfo_screenwidth() // 2 - lw // 2}+{top.winfo_screenheight() // 2 - lh // 2 - 20}")
        tk.Label(top, text="\U0001f512", bg=C["BG"], fg=C["ACC2"], font=("Segoe UI Emoji", 34)).pack(pady=(18, 0))
        tk.Label(top, text="Ton journal t'attend, capitaine.", bg=C["BG"], fg=C["TEXT"],
                 font=("Segoe UI", 13, "bold")).pack()
        v = tk.StringVar()
        en = tk.Entry(top, textvariable=v, show="\u2022", justify="center", bg=C["ENTRY"], fg=C["TEXT"],
                      insertbackground=C["TEXT"], relief="flat", font=("Segoe UI", 14), width=14)
        en.pack(pady=10, ipady=4); en.focus_set()
        msg = tk.Label(top, text="Tape ton code", bg=C["BG"], fg=C["DIM"], font=("Segoe UI", 9))
        msg.pack()

        def ok(_e=None):
            vr = self.st["verrou"]
            if pin_hash(v.get(), vr["sel"]) == vr["hash"]:
                top.destroy()
                self._show_window(); self._build()
            else:
                msg.configure(text="Pas tout \u00e0 fait\u2026 r\u00e9essaie tranquillement.", fg=C["ACC2"]); v.set("")

        def oubli():
            from tkinter import messagebox
            messagebox.showinfo(APP, "Pas de panique : le verrou est une porte, pas un coffre-fort.\n\n"
                                "Pour l'enlever, ouvre le dossier %APPDATA%\\Padawan et efface le fichier journal.json "
                                "(tes entr\u00e9es ne bougent pas). Les entr\u00e9es scell\u00e9es, elles, gardent leur "
                                "propre phrase secr\u00e8te.", parent=top)
        row = tk.Frame(top, bg=C["BG"]); row.pack(pady=8)
        self.btn(row, "Ouvrir le journal", ok, acc=True).pack(side="left", padx=4)
        self.btn(row, "J'ai oubli\u00e9", oubli, small=True).pack(side="left", padx=4)
        en.bind("<Return>", ok)
        top.protocol("WM_DELETE_WINDOW", lambda: (top.destroy(), self.root.destroy()))

    # ------------------------------------------------------------ construction
    def _build(self):
        tk = self.tk
        r = self.root
        self._menus()
        main = tk.PanedWindow(r, orient="horizontal", bg=C["BG"], sashwidth=5, bd=0, sashrelief="flat")
        left = tk.Frame(main, bg=C["PANEL"], width=350)
        right = tk.Frame(main, bg=C["BG"])
        main.add(left, minsize=self.px(290), width=int(max(self.px(360), min(self.px(520), r.winfo_screenwidth() * 0.22))))
        main.add(right, minsize=self.px(520))
        self.left, self.right = left, right
        self._build_left(left)
        self._build_editor(right)
        bar = tk.Frame(r, bg=C["PANEL"]); bar.pack(fill="x", side="bottom")
        main.pack(fill="both", expand=True)      # apres la barre du bas : elle reste toujours visible
        self.st_lbl = tk.Label(bar, text="Pr\u00eat. Tout reste sur ce PC.", bg=C["PANEL"], fg=C["DIM"], font=("Segoe UI", 9))
        self.st_lbl.pack(side="left", padx=10, pady=4)
        self.wc_lbl = tk.Label(bar, text="", bg=C["PANEL"], fg=C["DIM"], font=("Segoe UI", 9))
        self.wc_lbl.pack(side="left", padx=10)
        self.v_anim = tk.BooleanVar(value=self.st.get("animations", True))
        self.v_adv = tk.BooleanVar(value=self.st.get("mode_avance", False))
        for txt, var, fn in (("\u2728 Animations", self.v_anim, self._toggle_anim), ("\u2699 Mode avanc\u00e9", self.v_adv, self._toggle_adv)):
            tk.Checkbutton(bar, text=txt, variable=var, command=fn, bg=C["PANEL"], fg=C["DIM"], selectcolor=C["ENTRY"],
                           activebackground=C["PANEL"], activeforeground=C["TEXT"], font=("Segoe UI", 9)).pack(side="right", padx=6)
        self.btn(bar, "\u2754 Guide", self.help, small=True, tip="Guide du journal (F1)").pack(side="right", padx=3, pady=2)
        self.btn(bar, "\u26f6 Plein \u00e9cran", lambda: self.set_fullscreen(), small=True,
                 tip="Plein \u00e9cran (F11) \u00b7 \u00c9chap ou F11 pour revenir").pack(side="right", padx=3, pady=2)
        self.mb_theme = tk.Menubutton(bar, text="\U0001f3a8 Th\u00e8me \u25be", bg=C["BTN"], fg=C["TEXT"], relief="flat",
                                      activebackground=C["BTNH"], activeforeground=C["TEXT"], font=("Segoe UI", 9, "bold"),
                                      padx=8, pady=3, cursor="hand2")
        self.mb_theme.configure(menu=self._theme_menu(self.mb_theme))
        self.mb_theme.pack(side="right", padx=3, pady=2)
        self._tip(self.mb_theme, "Changer les couleurs du journal (aussi : menu Apparence)")
        self.offer = tk.Frame(bar, bg=C["PANEL"])
        self.offer.pack(side="right", padx=10)
        self._apply_adv()
        try:
            r.update_idletasks()
        except Exception:
            pass
        self.refresh_list()
        eid = None
        if "--ouvrir" in self.args:
            i = self.args.index("--ouvrir")
            eid = self.args[i + 1] if i + 1 < len(self.args) else None
        if eid and self.j.entry(eid):
            self.open_entry(eid)
        elif "--nouvelle" in self.args or not self.j.count():
            self.new_entry()
        else:
            self._smart_start()
        self._maybe_offer_lock()
        mem = self._ce_jour_la()
        if mem and "--selftest" not in self.args:
            self.toast(f"\u2728 Ce jour-l\u00e0 : {len(mem)} souvenir(s) d'une autre ann\u00e9e t'attendent.",
                       [("Voir", lambda: self.set_view("jour"))], 7)
        r.bind_all("<Control-n>", lambda e: self.new_entry())
        r.bind_all("<Control-s>", lambda e: (self.consign(), "break")[1])
        r.bind_all("<Control-f>", lambda e: (self.search_en.focus_set(), "break")[1])
        r.bind_all("<F1>", lambda e: self.help())
        r.bind_all("<Control-p>", lambda e: (self.print_entry(), "break")[1])
        r.bind_all("<F11>", lambda e: (self.set_fullscreen(), "break")[1])
        r.bind("<Escape>", self._esc, add="+")
        self._update_wc()
        self._caret_start()
        r.after(150, self._focus_editor); r.after(900, self._focus_editor)

    def _first_open_id(self):
        for e in self.j.entries():
            if not e.get("sealed"):
                return e["id"]
        return None

    def _menus(self):
        tk = self.tk
        mb = tk.Menu(self.root)
        m = tk.Menu(mb, tearoff=0)
        m.add_command(label="\u2795 Nouvelle entr\u00e9e  (Ctrl+N)", command=self.new_entry)
        m.add_command(label="\U0001f4cb Coller dans l'entr\u00e9e du jour", command=self.paste_today)
        m.add_command(label="\u2726 Consigner l'entr\u00e9e  (Ctrl+S)", command=self.consign)
        m.add_cascade(label="\U0001f4dd Commencer avec un mod\u00e8le", menu=self._template_menu(m))
        m.add_command(label="\u2b50 Favori : ajouter / enlever", command=lambda: self.toggle_fav())
        m.add_command(label="\U0001f50e Chercher  (Ctrl+F)", command=lambda: self.search_en.focus_set())
        m.add_separator()
        m.add_command(label="\U0001f5a8 Imprimer l'entr\u00e9e  (Ctrl+P)", command=lambda: self.print_entry())
        m.add_command(label="\U0001f9fe Enregistrer en fichier texte (.txt)\u2026", command=lambda: self.share("txt", self._current_saved_id()))
        m.add_separator()
        m.add_command(label="\U0001f4c2 Ouvrir le dossier du journal", command=lambda: pc.open_path(self.j.root))
        m.add_command(label="\U0001f4e4 Dossier des partages", command=lambda: pc.open_path(partages_dir()))
        m.add_separator()
        m.add_command(label="\U0001f5d1 Supprimer l'entr\u00e9e (va \u00e0 la corbeille)", command=self.delete_current)
        m.add_command(label="\u267b Corbeille : retrouver une entr\u00e9e\u2026", command=self.open_trash)
        m.add_separator()
        m.add_command(label="\u26f6 Plein \u00e9cran  (F11 \u00b7 \u00c9chap pour revenir)", command=self.set_fullscreen)
        m.add_command(label="Quitter", command=self.on_close)
        mb.add_cascade(label="Journal", menu=m)
        self.share_menu = tk.Menu(mb, tearoff=0)
        self._fill_share_menu(self.share_menu)
        mb.add_cascade(label="Partager", menu=self.share_menu)
        mb.add_cascade(label="Apparence", menu=self._theme_menu(mb))
        lm = tk.Menu(mb, tearoff=0)
        self.v_auto = tk.BooleanVar(value=self.st.get("liens_auto", False))
        lm.add_command(label="\U0001f517 Tous mes liens (et leur copie)\u2026", command=self.open_links)
        lm.add_separator()
        lm.add_checkbutton(label="Rendre les liens permanents automatiquement (envoi \u00e0 l'Archiveur)", variable=self.v_auto,
                           command=lambda: self._set("liens_auto", self.v_auto.get()))
        mb.add_cascade(label="Liens", menu=lm)
        ia = tk.Menu(mb, tearoff=0)
        ia.add_command(label="\U0001f9e0 R\u00e9sum\u00e9 de ma semaine (IA locale)", command=self.ai_week)
        ia.add_command(label="\U0001f4ac Pose une question \u00e0 ton journal\u2026", command=self.ai_ask)
        mb.add_cascade(label="IA", menu=ia)
        self.adv_menu = tk.Menu(mb, tearoff=0)
        self.adv_menu.add_command(label="\U0001f511 Verrou du journal (code)\u2026", command=self.lock_settings)
        self.adv_menu.add_command(label="\U0001f512 Sceller l'entr\u00e9e (chiffr\u00e9e)\u2026", command=self.seal_current)
        self.v_way = tk.BooleanVar(value=self.st.get("wayback", False))
        self.adv_menu.add_checkbutton(label="Rendre les liens permanents automatiquement", variable=self.v_auto,
                                      command=lambda: self._set("liens_auto", self.v_auto.get()))
        self.adv_menu.add_checkbutton(label="Aussi sauver les liens sur la Wayback Machine (internet)", variable=self.v_way,
                                      command=lambda: self._set("wayback", self.v_way.get()))
        mb.add_cascade(label="Avanc\u00e9", menu=self.adv_menu)
        h = tk.Menu(mb, tearoff=0)
        h.add_command(label="Guide du journal (F1)", command=self.help)
        h.add_command(label="Revoir l'animation d'ouverture", command=lambda: self.anim.warp(self.root, lambda: None) if self.anim.on else None)
        mb.add_cascade(label="Aide", menu=h)
        self.menubar = mb
        self.root.configure(menu=mb)

    def _fill_share_menu(self, m, eid_fn=None):
        eid_fn = eid_fn or (lambda: self._current_saved_id())
        m.add_command(label="\U0001f310 Page web \u00e0 partager (.html, tout inclus)\u2026", command=lambda: self.share("html", eid_fn()))
        m.add_command(label="\U0001f4c4 PDF\u2026", command=lambda: self.share("pdf", eid_fn()))
        m.add_command(label="\U0001f5dc Paquet complet (.zip)\u2026", command=lambda: self.share("zip", eid_fn()))
        m.add_command(label="\U0001f4cb Copier pour partager (texte)", command=lambda: self.share("texte", eid_fn()))
        m.add_command(label="\U0001f9fe Fichier texte (.txt)\u2026", command=lambda: self.share("txt", eid_fn()))
        m.add_command(label="\U0001f5a8 Imprimer\u2026", command=lambda: self.print_entry(eid_fn()))
        m.add_separator()
        m.add_command(label="\U0001f4d6 Envoyer au Grimoire", command=lambda: self.share("grimoire", eid_fn()))
        m.add_command(label="\U0001f4e8 Pr\u00e9parer pour le Messager", command=lambda: self.share("messager", eid_fn()))
        m.add_separator()
        m.add_command(label="\U0001f4da Partager plusieurs entr\u00e9es\u2026", command=self.share_many)

    def _set(self, k, v):
        self.st[k] = v; save_settings(self.st)

    def _toggle_anim(self):
        self._set("animations", bool(self.v_anim.get()))
        self.status("Animations " + ("activ\u00e9es \u2728" if self.v_anim.get() else "d\u00e9sactiv\u00e9es"), True)

    def _toggle_adv(self):
        self._set("mode_avance", bool(self.v_adv.get()))
        self._apply_adv()

    def _apply_adv(self):
        adv = bool(self.st.get("mode_avance"))
        try:
            idx = self.menubar.index("Avanc\u00e9")
            self.menubar.entryconfigure(idx, state="normal" if adv else "disabled")
        except Exception:
            pass
        try:
            if adv:
                self.b_seal.pack(side="right", padx=3)
            else:
                self.b_seal.pack_forget()
        except Exception:
            pass

    # ------------------------------------------------------------ colonne de gauche
    def _build_left(self, f):
        tk, ttk = self.tk, self.ttk
        top = tk.Frame(f, bg=C["PANEL"]); top.pack(fill="x", padx=10, pady=(10, 4))
        self.btn(top, "\u2795  Nouvelle entr\u00e9e", self.new_entry, acc=True,
                 tip="Ctrl+N \u00b7 ou Ctrl+Alt+J depuis n'importe o\u00f9").pack(fill="x")
        self.btn(top, "\U0001f4cb  Coller dans le journal", self.paste_today,
                 tip="Ce que tu as copi\u00e9 va dans l'entr\u00e9e du jour (aussi : Ctrl+Alt+K partout)").pack(fill="x", pady=(5, 0))
        self.streak_lbl = tk.Label(top, text="", bg=C["PANEL"], fg=C["ACC2"], font=("Segoe UI", 10, "bold"), anchor="w")
        self.streak_lbl.pack(fill="x", pady=(6, 0))
        sf = tk.Frame(f, bg=C["PANEL"]); sf.pack(fill="x", padx=10, pady=6)
        self.v_search = tk.StringVar()
        self.search_en = tk.Entry(sf, textvariable=self.v_search, bg=C["ENTRY"], fg=C["TEXT"], insertbackground=C["TEXT"],
                                  relief="flat", font=("Segoe UI", 11))
        self.btn(sf, "\u2715", self._clear_search, small=True,
                 tip="Effacer la recherche (\u00c9chap)").pack(side="right", padx=(4, 0))
        self.search_en.pack(side="left", fill="x", expand=True, ipady=4)
        self._tip(self.search_en, "Chercher partout (Ctrl+F)")
        self.search_en.bind("<Escape>", lambda e: (self._clear_search(), "break")[1])
        self._placeholder(self.search_en, self.v_search, "\U0001f50e Chercher partout (textes, liens, vocaux\u2026)")
        self.v_search.trace_add("write", lambda *a: self._debounce_list())
        fr = tk.Frame(f, bg=C["PANEL"]); fr.pack(fill="x", padx=10)
        self.v_tag = tk.StringVar(value="Toutes les \u00e9tiquettes")
        self.cb_tag = ttk.Combobox(fr, textvariable=self.v_tag, state="readonly", style="J.TCombobox", width=18)
        self.cb_tag.pack(side="left", fill="x", expand=True)
        self.cb_tag.bind("<<ComboboxSelected>>", lambda e: self.refresh_list())
        self.v_mood = tk.StringVar(value="")
        self.mb_mood = tk.Menubutton(fr, text="Humeur \u25be", bg=C["BTN"], fg=C["TEXT"], relief="flat",
                                     activebackground=C["BTNH"], font=("Segoe UI", 9, "bold"))
        mm = tk.Menu(self.mb_mood, tearoff=0)
        mm.add_command(label="Toutes", command=lambda: self._set_mood_filter(""))
        for ic, nm in MOODS:
            mm.add_command(label=f"{ic}  {nm}", command=lambda ic=ic: self._set_mood_filter(ic))
        self.mb_mood.configure(menu=mm)
        self.mb_mood.pack(side="left", padx=(6, 0))
        self._tip(self.mb_mood, "Montrer seulement les entr\u00e9es d'une humeur")
        tabs = tk.Frame(f, bg=C["PANEL"]); tabs.pack(fill="x", padx=10, pady=(8, 2))
        self.tab_btns = {}
        tips = {"chrono": "Toutes tes entr\u00e9es, de la plus r\u00e9cente \u00e0 la plus ancienne",
                "cal": "Un calendrier : les jours avec une entr\u00e9e sont color\u00e9s",
                "jour": "Tes souvenirs des autres ann\u00e9es, \u00e0 la m\u00eame date",
                "fav": "Les entr\u00e9es marqu\u00e9es d'une \u00e9toile (bouton \u2606 Favori)"}
        for n, (key, lab) in enumerate((("chrono", "\U0001f30c Chronologie"), ("cal", "\U0001f4c5 Calendrier"),
                                         ("jour", "\u2728 Ce jour-l\u00e0"), ("fav", "\u2b50 Favoris"))):
            b = tk.Button(tabs, text=lab, relief="flat", bd=0, font=("Segoe UI", 9, "bold"), cursor="hand2",
                          command=lambda k=key: self.set_view(k), padx=6, pady=5)
            b.grid(row=n // 2, column=n % 2, sticky="nsew", padx=1, pady=1)
            tabs.columnconfigure(n % 2, weight=1)
            self._tip(b, tips[key])
            self.tab_btns[key] = b
        lb_ = tk.Button(tabs, text="\U0001f517 Mes liens", relief="flat", bd=0, font=("Segoe UI", 9, "bold"), cursor="hand2",
                        command=self.open_links, padx=6, pady=5, bg=C["CARD"], fg=C["TEXT"], activebackground=C["BTNH"])
        lb_.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=1, pady=1)
        self._tip(lb_, "Tous les liens de ton journal, avec leur copie permanente")
        self.cal_frame = tk.Frame(f, bg=C["PANEL"])
        self.list_head = tk.Label(f, text="", bg=C["PANEL"], fg=C["ACC2"], font=("Segoe UI", 9, "italic"),
                                  anchor="w", justify="left", wraplength=self.px(320))
        self.list_head.pack(fill="x", padx=12)
        outer = tk.Frame(f, bg=C["PANEL"]); outer.pack(fill="both", expand=True, padx=(8, 0), pady=(2, 8))
        self.lcv = tk.Canvas(outer, bg=C["PANEL"], highlightthickness=0)
        sb = ttk.Scrollbar(outer, orient="vertical", command=self.lcv.yview, style="J.Vertical.TScrollbar")
        self.lbody = tk.Frame(self.lcv, bg=C["PANEL"])
        self.lbody.bind("<Configure>", lambda e: self.lcv.configure(scrollregion=self.lcv.bbox("all")))
        self._lwin = self.lcv.create_window((0, 0), window=self.lbody, anchor="nw")
        self.lcv.bind("<Configure>", lambda e: self.lcv.itemconfigure(self._lwin, width=e.width))
        self.lcv.configure(yscrollcommand=sb.set)
        self.lcv.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")
        for wdg in (self.lcv, self.lbody):
            wdg.bind("<MouseWheel>", lambda e: self.lcv.yview_scroll(int(-e.delta / 120), "units"))
        self._paint_tabs()

    def _placeholder(self, en, var, text):
        en._phtext = text

        def show(_e=None):
            if not var.get():
                en.configure(fg=C["DIM"]); en.insert(0, text); en._ph = True

        def hide(_e=None):
            if getattr(en, "_ph", False):
                if var.get() == text:
                    en.delete(0, "end")
                en.configure(fg=C["TEXT"]); en._ph = False
        en._ph = False
        en._show_ph = show
        en.bind("<FocusIn>", hide, add="+"); en.bind("<FocusOut>", show, add="+")
        show()

    def _val(self, en, var):
        v = var.get()
        return "" if getattr(en, "_ph", False) and v == getattr(en, "_phtext", None) else v

    def _set_mood_filter(self, ic):
        self.v_mood.set(ic)
        self.mb_mood.configure(text=(ic + " \u25be") if ic else "Humeur \u25be")
        self.refresh_list()

    def set_view(self, key):
        self.view = key
        if key != "cal":
            self.day_filter = None
        self._paint_tabs()
        self.refresh_list()

    def _paint_tabs(self):
        for k, b in self.tab_btns.items():
            on = k == self.view
            b.configure(bg=C["ACC"] if on else C["CARD"], fg=C["ONACC"] if on else C["TEXT"],
                        activebackground=C["BTNH"])
        if self.view == "cal":
            self.cal_frame.pack(fill="x", padx=10, pady=4, before=self.list_head)
            self._draw_calendar()
        else:
            self.cal_frame.pack_forget()

    def _debounce_list(self):
        if getattr(self, "_deb", None):
            self.root.after_cancel(self._deb)
        self._deb = self.root.after(260, self.refresh_list)

    def _ce_jour_la(self):
        t = dt.date.today()
        md = t.strftime("-%m-%d")
        return [e for e in self.j.entries() if e["created"][4:10] == md and int(e["created"][:4]) < t.year]

    def _draw_calendar(self):
        tk = self.tk
        for wdg in self.cal_frame.winfo_children():
            wdg.destroy()
        m0 = self.cal_month
        head = tk.Frame(self.cal_frame, bg=C["PANEL"]); head.pack(fill="x")

        def shift(k):
            y, mth = m0.year, m0.month + k
            if mth < 1:
                y, mth = y - 1, 12
            if mth > 12:
                y, mth = y + 1, 1
            self.cal_month = dt.date(y, mth, 1); self._draw_calendar()
        self.btn(head, "\u25c0", lambda: shift(-1), small=True, tip="Mois pr\u00e9c\u00e9dent").pack(side="left")
        tk.Label(head, text=f"{MOIS[m0.month - 1].capitalize()} {m0.year}", bg=C["PANEL"], fg=C["TEXT"],
                 font=("Segoe UI", 11, "bold")).pack(side="left", expand=True)
        self.btn(head, "\u25b6", lambda: shift(1), small=True, tip="Mois suivant").pack(side="right")
        g = tk.Frame(self.cal_frame, bg=C["PANEL"]); g.pack(fill="x", pady=4)
        for i, d in enumerate("LMMJVSD"):
            tk.Label(g, text=d, bg=C["PANEL"], fg=C["DIM"], font=("Segoe UI", 8)).grid(row=0, column=i, sticky="nsew")
            g.columnconfigure(i, weight=1)
        counts, moods = {}, {}
        prefix = m0.strftime("%Y-%m")
        for e in self.j.entries():
            if e["created"].startswith(prefix):
                d = int(e["created"][8:10])
                counts[d] = counts.get(d, 0) + 1
                if e.get("mood") and d not in moods:
                    moods[d] = e["mood"]
        first = m0.weekday()
        nd = ((m0.replace(month=m0.month % 12 + 1, year=m0.year + (m0.month == 12))) - m0).days
        today = dt.date.today()
        for d in range(1, nd + 1):
            pos = first + d - 1
            has = counts.get(d)
            sel = self.day_filter == dt.date(m0.year, m0.month, d)
            dot = moods.get(d, "\u2022" if has else " ")
            txt = f"{d}\n{dot}"
            b = tk.Button(g, text=txt, relief="flat", bd=0, font=("Segoe UI", 8), cursor="hand2",
                          bg=C["ACC2"] if sel else (C["ACC"] if has else C["CARD"]),
                          fg=C["ONACC"] if (has or sel) else (C["TEXT"] if dt.date(m0.year, m0.month, d) != today else C["ACC2"]),
                          command=lambda d=d: self._pick_day(dt.date(m0.year, m0.month, d)))
            b.grid(row=1 + pos // 7, column=pos % 7, sticky="nsew", padx=1, pady=1)

    def _pick_day(self, d):
        self.day_filter = None if self.day_filter == d else d
        self._draw_calendar(); self.refresh_list()

    def _filtered(self):
        es = self.j.entries()
        tags = sorted({t.strip() for e in es for t in str(e.get("tags") or "").split(",") if t.strip()}, key=pc.norm)
        self.cb_tag.configure(values=["Toutes les \u00e9tiquettes"] + tags)
        head = ""
        if self.view == "jour":
            es = self._ce_jour_la()
            t = dt.date.today()
            head = (f"\u2728 Le {t.day} {MOIS[t.month - 1]}, les autres ann\u00e9es :" if es else
                    "\u2728 Rien encore pour ce jour-l\u00e0\u2026 dans un an, tes souvenirs reviendront ici.")
        elif self.view == "cal" and self.day_filter:
            ds = self.day_filter.isoformat()
            es = [e for e in es if e["created"][:10] == ds]
            head = f"\U0001f4c5 {date_fr(dt.datetime.combine(self.day_filter, dt.time()), False)}"
        elif self.view == "fav":
            es = [e for e in es if e.get("favori")]
            head = ("\u2b50 Tes entr\u00e9es favorites" if es else
                    "\u2b50 Aucun favori encore : clique \u00ab \u2606 Favori \u00bb au-dessus d'une entr\u00e9e pour la garder ici.")
        elif self.view == "cal":
            pre = self.cal_month.strftime("%Y-%m")
            es = [e for e in es if e["created"].startswith(pre)]
        tag = self.v_tag.get()
        if tag and not tag.startswith("Toutes"):
            es = [e for e in es if tag in [t.strip() for t in str(e.get("tags") or "").split(",")]]
        if self.v_mood.get():
            es = [e for e in es if e.get("mood") == self.v_mood.get()]
        q = self._val(self.search_en, self.v_search).strip()
        if q:
            es = search(self.j, q, es)
            head = f"\U0001f50e {len(es)} r\u00e9sultat(s) pour \u00ab {q} \u00bb (hors entr\u00e9es scell\u00e9es)"
        return es, head

    def refresh_list(self):
        tk = self.tk
        try:
            es, head = self._filtered()
        except Exception:
            traceback.print_exc(); es, head = [], ""
        self.list_head.configure(text=head)
        for wdg in self.lbody.winfo_children():
            wdg.destroy()
        self.list_cards = {}
        fades = []
        if not es:
            tk.Label(self.lbody, text="Aucune entr\u00e9e ici pour l'instant.\nClique \u00ab Nouvelle entr\u00e9e \u00bb pour commencer ton r\u00e9cit.",
                     bg=C["PANEL"], fg=C["DIM"], font=("Segoe UI", 10), justify="center").pack(pady=30)
        try:
            with self.j.lock:
                rows = self.j.db.execute("SELECT entry_id, url, status FROM embeds WHERE kind='link'").fetchall()
            self._emb_links = {}
            for r_ in rows:
                self._emb_links.setdefault(r_[0], {})[r_[1]] = r_[2]
        except Exception:
            self._emb_links = {}
        self._list_state = {"last_month": None, "es": es, "shown": 0, "more": None}
        self._list_more(fades)
        for n, ws in fades:
            self.anim.fade_in(ws, delay=n * 0.035)
        self.lcv.yview_moveto(0)
        if self.view == "cal":
            self._draw_calendar()
        self._paint_streak()

    def _list_more(self, fades=None):
        """affiche les cartes par paquets de 60 (rapide meme avec des milliers d'entrees)."""
        tk = self.tk
        st = self._list_state
        if st.get("more") is not None:
            try:
                st["more"].destroy()
            except Exception:
                pass
            st["more"] = None
        es, a = st["es"], st["shown"]
        b = min(len(es), a + 60)
        fades = [] if fades is None else fades
        for n in range(a, b):
            e = es[n]
            d = parse_iso(e["created"])
            mk = d.strftime("%Y-%m")
            if mk != st["last_month"] and self.view == "chrono":
                st["last_month"] = mk
                tk.Label(self.lbody, text=f"{MOIS[d.month - 1].capitalize()} {d.year}", bg=C["PANEL"], fg=C["ACC"],
                         font=("Segoe UI", 9, "bold"), anchor="w").pack(fill="x", padx=6, pady=(8, 0))
            cur = self.cur and self.cur.get("id") == e["id"]
            card = tk.Frame(self.lbody, bg=C["BTNH"] if cur else C["CARD"], padx=8, pady=6, cursor="hand2")
            card.pack(fill="x", padx=(2, 8), pady=3)
            cb = card.cget("bg")
            icon = e.get("mood") or ("\U0001f512" if e.get("sealed") else "\U0001f4dd")
            l1 = tk.Label(card, text=icon, bg=cb, fg=C["TEXT"], font=("Segoe UI Emoji", 16))
            l1.pack(side="left", padx=(0, 8))
            col = tk.Frame(card, bg=cb); col.pack(side="left", fill="x", expand=True)
            title = ("\u2605 " if e.get("favori") else "") + (e.get("title") or self._auto_title(e))
            l2 = tk.Label(col, text=title[:60], bg=cb, fg=C["TEXT"], font=("Segoe UI", 10, "bold"), anchor="w", justify="left")
            l2.pack(fill="x")
            yr = f" {d.year}" if d.year != dt.date.today().year else ""
            sub = f"{JOURS[d.weekday()][:3]}. {d.day} {MOIS[d.month - 1][:4]}.{yr} \u00b7 {d.hour} h {d.minute:02d}"
            if e.get("lieu"):
                sub += f" \u00b7 \U0001f4cd {e['lieu'][:24]}"
            nl = self._link_count(e)
            if nl:
                sub += f" \u00b7 \U0001f517 {nl}"
            l3 = tk.Label(col, text=sub, bg=cb, fg=C["DIM"], font=("Segoe UI", 8), anchor="w")
            l3.pack(fill="x")
            if e.get("sealed"):
                snip = "Scell\u00e9e \u2014 phrase secr\u00e8te demand\u00e9e" + (f" (indice : {e['hint']})" if e.get("hint") else "")
            else:
                snip = md_strip(e.get("body"), 90)
            l4 = tk.Label(col, text=snip, bg=cb, fg=C["DIM"], font=("Segoe UI", 8, "italic"), anchor="w",
                          justify="left", wraplength=self.px(250))
            l4.pack(fill="x")
            for wdg in (card, l1, col, l2, l3, l4):
                wdg.bind("<Button-1>", lambda ev, i=e["id"]: self.open_entry(i))
                wdg.bind("<Double-Button-1>", lambda ev, i=e["id"]: self.open_entry(i))
                wdg.bind("<Button-3>", lambda ev, i=e["id"]: self._list_menu(ev, i))
                wdg.bind("<MouseWheel>", lambda ev: self.lcv.yview_scroll(int(-ev.delta / 120), "units"))
            self.list_cards[e["id"]] = card
            if n < 14:
                fades.append((n, [l2, l3, l4]))
        st["shown"] = b
        if b < len(es):
            st["more"] = tk.Button(self.lbody, text=f"\u2193 Voir plus ({len(es) - b} autres entr\u00e9es)", relief="flat",
                                   bg=C["BTN"], fg=C["TEXT"], activebackground=C["BTNH"], activeforeground=C["TEXT"],
                                   font=("Segoe UI", 9, "bold"), cursor="hand2", command=self._list_more)
            st["more"].pack(fill="x", padx=(2, 8), pady=(6, 12))
            st["more"].bind("<MouseWheel>", lambda ev: self.lcv.yview_scroll(int(-ev.delta / 120), "units"))

    def _auto_title(self, e):
        txt = md_strip(e.get("body"))
        if txt:
            return txt[:48] + ("\u2026" if len(txt) > 48 else "")
        d = parse_iso(e["created"])
        return f"Entr\u00e9e du {d.day} {MOIS[d.month - 1]}"

    def _list_menu(self, ev, eid):
        tk = self.tk
        m = tk.Menu(self.root, tearoff=0)
        e = self.j.entry(eid)
        m.add_command(label="Ouvrir", command=lambda: self.open_entry(eid))
        m.add_command(label="\u2606 Enlever des favoris" if e.get("favori") else "\u2b50 Ajouter aux favoris",
                      command=lambda: self.toggle_fav(eid))
        if not e.get("sealed"):
            m.add_separator()
            self._fill_share_menu(m, lambda: eid)
            if self.st.get("mode_avance"):
                m.add_command(label="\U0001f512 Sceller\u2026", command=lambda: self.seal_dialog(eid))
        m.add_separator()
        m.add_command(label="\U0001f5d1 Supprimer (va \u00e0 la corbeille)", command=lambda: self.delete_entry(eid))
        m.tk_popup(ev.x_root, ev.y_root)

    # ------------------------------------------------------------ editeur
    def _build_editor(self, f):
        tk = self.tk
        self.ed_wrap = f
        head = tk.Frame(f, bg=C["BG"]); head.pack(fill="x", padx=18, pady=(10, 0))
        self.flavor = tk.Label(head, text="", bg=C["BG"], fg=C["ACC"], font=("Consolas", 10), anchor="w")
        self.flavor.pack(fill="x")
        self.v_title = tk.StringVar()
        self.title_en = tk.Entry(head, textvariable=self.v_title, bg=C["BG"], fg=C["TEXT"], insertbackground=C["ACC"],
                                 relief="flat", font=("Segoe UI", 18, "bold"))
        self.title_en.pack(fill="x", pady=(2, 2))
        self._placeholder(self.title_en, self.v_title, "Titre de l'entr\u00e9e (facultatif)")
        meta = tk.Frame(head, bg=C["BG"]); meta.pack(fill="x", pady=(0, 4))
        self.v_date, self.v_lieu, self.v_tags = tk.StringVar(), tk.StringVar(), tk.StringVar()

        def field(lab, var, w, ph):
            tk.Label(meta, text=lab, bg=C["BG"], fg=C["DIM"], font=("Segoe UI", 9)).pack(side="left", padx=(0, 3))
            en = tk.Entry(meta, textvariable=var, width=w, bg=C["ENTRY"], fg=C["TEXT"], insertbackground=C["TEXT"],
                          relief="flat", font=("Segoe UI", 9))
            en.pack(side="left", padx=(0, 10), ipady=2)
            if ph:
                self._placeholder(en, var, ph)
            return en
        self.date_en = field("\U0001f552", self.v_date, 16, "")
        self.lieu_en = field("\U0001f4cd", self.v_lieu, 18, "Lieu")
        self.tags_en = field("#", self.v_tags, 22, "\u00e9tiquettes, s\u00e9par\u00e9es, par virgules")
        moods = tk.Frame(head, bg=C["BG"]); moods.pack(fill="x")
        self.mood_btns, self.weather_btns = {}, {}
        self.v_moodsel, self.v_weathersel = "", ""
        for ic, nm in MOODS:
            b = tk.Label(moods, text=ic, bg=C["BG"], font=EMOJI_FONT, cursor="hand2", padx=3, pady=1,
                         highlightthickness=2, highlightbackground=C["BG"])
            b.pack(side="left", padx=1); b.bind("<Button-1>", lambda e, ic=ic: self._pick_mood(ic))
            self._tip(b, f"Humeur : {nm} (clic pour choisir, re-clic pour enlever)")
            self.mood_btns[ic] = b
        tk.Label(moods, text="  \u2502  ", bg=C["BG"], fg=C["LINE"]).pack(side="left")
        for ic, nm in WEATHER:
            b = tk.Label(moods, text=ic, bg=C["BG"], fg=C["TEXT"], font=EMOJI_FONT, cursor="hand2", padx=3, pady=1,
                         highlightthickness=2, highlightbackground=C["BG"])
            b.pack(side="left", padx=1); b.bind("<Button-1>", lambda e, ic=ic: self._pick_weather(ic))
            self._tip(b, f"M\u00e9t\u00e9o : {nm} (clic pour choisir, re-clic pour enlever)")
            self.weather_btns[ic] = b
        self.mood_lbl = tk.Label(head, text="", bg=C["BG"], fg=C["DIM"], font=("Segoe UI", 9, "italic"), anchor="w")
        self.mood_lbl.pack(fill="x")
        tb = tk.Frame(f, bg=C["PANEL"]); tb.pack(fill="x", padx=18, pady=(6, 0))
        self.toolbar = tb
        for txt, fn, tip in (("B", lambda: self._toggle_tag("b"), "Gras (Ctrl+B)"), ("I", lambda: self._toggle_tag("i"), "Italique (Ctrl+I)"),
                             ("T", self._toggle_h1, "Sous-titre (la ligne o\u00f9 est le curseur)"),
                             ("\u2022", self._bullet, "Puce (d\u00e9but de ligne)")):
            self.btn(tb, txt, fn, small=True, tip=tip).pack(side="left", padx=1, pady=3)
        tk.Label(tb, text=" ", bg=C["PANEL"]).pack(side="left")
        for txt, fn, tip in (("\U0001f399 Vocal", self.record, "Enregistrer un m\u00e9mo vocal"),
                             ("\U0001f5bc Image", self.pick_image, "Ajouter une image (ou colle-la : Ctrl+V)"),
                             ("\U0001f4ce Fichier", self.pick_file, "Joindre un fichier (ou glisse-le ici)"),
                             ("\U0001f517 Lien", self.ask_link, "Ajouter un lien \u2014 on peut le rendre permanent"),
                             ("\U0001f4cb Coller", self.smart_paste, "Coller n'importe quoi (Ctrl+V)")):
            self.btn(tb, txt, fn, small=True, tip=tip).pack(side="left", padx=2, pady=3)
        self.mb_tpl = tk.Menubutton(tb, text="\U0001f4dd Mod\u00e8le \u25be", bg=C["BTN"], fg=C["TEXT"], relief="flat",
                                    activebackground=C["BTNH"], activeforeground=C["TEXT"], font=("Segoe UI", 9, "bold"),
                                    padx=8, pady=3, cursor="hand2")
        self.mb_tpl.configure(menu=self._template_menu(self.mb_tpl)); self.mb_tpl.pack(side="left", padx=2, pady=3)
        self._tip(self.mb_tpl, "Commencer avec un mod\u00e8le : Journ\u00e9e, Id\u00e9e, Gratitude, Travail\u2026")
        self.btn(tb, "\u2726 Consigner", self.consign, acc=True, small=True,
                 tip="Enregistre avec le sceau (Ctrl+S) \u2014 tout est aussi enregistr\u00e9 automatiquement").pack(side="right", padx=3)
        self.b_share = tk.Menubutton(tb, text="\U0001f4e4 Partager \u25be", bg=C["BTN"], fg=C["TEXT"], relief="flat",
                                     activebackground=C["BTNH"], font=("Segoe UI", 9, "bold"), padx=6)
        sm = tk.Menu(self.b_share, tearoff=0); self._fill_share_menu(sm); self.b_share.configure(menu=sm)
        self.b_share.pack(side="right", padx=3)
        self._tip(self.b_share, "Partager cette entr\u00e9e : page web, PDF, texte, impression (Ctrl+P)\u2026")
        self.b_fav = self.btn(tb, "\u2606 Favori", lambda: self.toggle_fav(), small=True,
                              tip="Garder cette entr\u00e9e dans l'onglet \u2b50 Favoris")
        self.b_fav.pack(side="right", padx=3)
        self.b_seal = self.btn(tb, "\U0001f512 Sceller", self.seal_current, small=True, tip="Chiffrer cette entr\u00e9e (mode avanc\u00e9)")
        holder = tk.Frame(f, bg=C["BG"]); holder.pack(fill="both", expand=True, padx=18, pady=(6, 8))
        self.holder = holder
        self.txt = tk.Text(holder, wrap="word", undo=True, bg=C["ENTRY"], fg=C["TEXT"], insertbackground=C["ACC"],
                           relief="flat", font=("Segoe UI", self.fs), padx=self.px(16), pady=self.px(12), spacing1=2, spacing3=4,
                           selectbackground=C["SEL"], selectforeground=C["TEXT"], highlightthickness=0)
        sb = self.ttk.Scrollbar(holder, orient="vertical", command=self.txt.yview, style="J.Vertical.TScrollbar")
        self.txt.configure(yscrollcommand=sb.set)
        self.txt.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")
        t = self.txt
        t.tag_configure("b", font=("Segoe UI", self.fs, "bold"))
        t.tag_configure("i", font=("Segoe UI", self.fs, "italic"))
        t.tag_configure("bi", font=("Segoe UI", self.fs, "bold italic"))
        t.tag_configure("h1", font=("Segoe UI", self.fs + 3, "bold"), foreground=C["ACC2"], spacing1=10)
        t.tag_configure("lnk", foreground=C["ACC"], underline=True)
        t.bind("<Configure>", self._reflow, add="+")
        t.tag_raise("bi"); t.tag_raise("sel")
        t.tag_bind("lnk", "<Enter>", lambda e: t.configure(cursor="hand2"))
        t.tag_bind("lnk", "<Leave>", lambda e: t.configure(cursor="xterm"))
        t.tag_bind("lnk", "<Control-Button-1>", self._click_link)
        t.tag_bind("lnk", "<Double-Button-1>", self._click_link)
        t.bind("<<Modified>>", self._on_modified)
        t.bind("<Control-v>", lambda e: (self.smart_paste(), "break")[1])
        t.bind("<Control-V>", lambda e: (self.smart_paste(), "break")[1])
        t.bind("<Shift-Insert>", lambda e: (self.smart_paste(), "break")[1])
        t.bind("<<Paste>>", lambda e: "break")
        t.bind("<Control-c>", lambda e: (self.copy_passage("riche"), "break")[1] if t.tag_ranges("sel") else None)
        t.bind("<Control-x>", lambda e: (self.copy_passage("riche"), self._delete_sel(), "break")[2] if t.tag_ranges("sel") else None)
        t.bind("<Control-b>", lambda e: (self._toggle_tag("b"), "break")[1])
        t.bind("<Control-i>", lambda e: (self._toggle_tag("i"), "break")[1])
        t.bind("<ButtonRelease-1>", lambda e: self.root.after(30, self._sel_bar), add="+")
        t.bind("<KeyRelease>", lambda e: self.root.after(30, self._sel_bar), add="+")
        t.bind("<Button-3>", self._text_menu)
        t.bind("<MouseWheel>", lambda e: self.root.after(20, self._sel_bar), add="+")
        for var in (self.v_title, self.v_date, self.v_lieu, self.v_tags):
            var.trace_add("write", lambda *a: self._mark_dirty())
        if self.dnd:
            try:
                t.drop_target_register(self.dnd.DND_FILES, self.dnd.DND_TEXT)
                t.dnd_bind("<<Drop>>", self._on_drop)
            except Exception:
                pass
        self.selbar = tk.Frame(holder, bg=C["CARD"], highlightthickness=1, highlightbackground=C["ACC"])
        for txt, fn in (("\U0001f4cb Copier ce passage", lambda: self.copy_passage("riche")),
                        ("\U0001f9f9 Texte seul", lambda: self.copy_passage("texte")),
                        ("\U0001f4c4 Mini-page", lambda: self.copy_passage("page"))):
            self.btn(self.selbar, txt, fn, small=True,
                     tip="Ctrl+C" if "Copier" in txt else None).pack(side="left", padx=2, pady=2)

    def _pick_mood(self, ic):
        self.v_moodsel = "" if self.v_moodsel == ic else ic
        self._paint_moods(); self._mark_dirty()

    def _pick_weather(self, ic):
        self.v_weathersel = "" if self.v_weathersel == ic else ic
        self._paint_moods(); self._mark_dirty()

    def _paint_moods(self):
        for btns, cur in ((self.mood_btns, self.v_moodsel), (self.weather_btns, self.v_weathersel)):
            for ic, b in btns.items():
                on = ic == cur
                b.configure(bg=C["SEL"] if on else C["BG"], highlightbackground=C["ACC"] if on else C["BG"])
        names = dict(MOODS); wn = dict(WEATHER)
        bits = []
        if self.v_moodsel:
            bits.append("Humeur : " + names.get(self.v_moodsel, ""))
        if self.v_weathersel:
            bits.append("M\u00e9t\u00e9o : " + wn.get(self.v_weathersel, ""))
        try:
            self.mood_lbl.configure(text=" \u00b7 ".join(bits) if bits else "\u2190 ton humeur et la m\u00e9t\u00e9o du jour (facultatif)",
                                    fg=C["ACC"] if bits else C["DIM"])
        except Exception:
            pass

    # ---- mise en forme
    def _toggle_tag(self, tag):
        t = self.txt
        if not t.tag_ranges("sel"):
            return
        a, b = t.index("sel.first"), t.index("sel.last")
        if tag in t.tag_names(a):
            t.tag_remove(tag, a, b)
        else:
            t.tag_add(tag, a, b)
        self._refresh_bi(); self._mark_dirty()

    def _refresh_bi(self):
        t = self.txt
        t.tag_remove("bi", "1.0", "end")
        br = t.tag_ranges("b")
        for k in range(0, len(br), 2):
            a, b = br[k], br[k + 1]
            pos = t.index(a)
            while t.compare(pos, "<", b):
                rng = t.tag_nextrange("i", pos, b)
                if not rng:
                    break
                s = rng[0]
                e = rng[1] if t.compare(rng[1], "<", b) else t.index(b)
                t.tag_add("bi", s, e)
                pos = e

    def _toggle_h1(self):
        t = self.txt
        ln = t.index("insert").split(".")[0]
        if "h1" in t.tag_names(f"{ln}.0"):
            t.tag_remove("h1", f"{ln}.0", f"{ln}.end+1c")
        else:
            t.tag_add("h1", f"{ln}.0", f"{ln}.end+1c")
        self._mark_dirty()

    def _bullet(self):
        t = self.txt
        ln = t.index("insert").split(".")[0]
        if t.get(f"{ln}.0", f"{ln}.2") == "\u2022 ":
            t.delete(f"{ln}.0", f"{ln}.2")
        else:
            t.insert(f"{ln}.0", "\u2022 ")
        self._mark_dirty()

    def _click_link(self, ev):
        idx = self.txt.index(f"@{ev.x},{ev.y}")
        for tg in self.txt.tag_names(idx):
            if tg in self.link_urls:
                pc.open_url(self.link_urls[tg]); return "break"

    # ---- rendu mini-markdown -> Text
    def _link_tag(self, url):
        self.link_n += 1
        tg = f"L{self.link_n}"
        self.link_urls[tg] = url
        return tg

    def insert_md(self, index, md, embeds_by_id=None):
        t = self.txt
        embeds_by_id = embeds_by_id or {}
        t.mark_set("ins", index); t.mark_gravity("ins", "right")
        lines = md_lines(md)
        for n, (h, toks) in enumerate(lines):
            line_start = t.index("ins")
            for tk_ in toks:
                if tk_[0] == "e":
                    m = embeds_by_id.get(tk_[1]) or self.j.embed(tk_[1])
                    if m:
                        self._insert_card(m, "ins")
                    continue
                _, s, b, i, url = tk_
                tags = []
                if b:
                    tags.append("b")
                if i:
                    tags.append("i")
                if url:
                    tags += ["lnk", self._link_tag(url)]
                t.insert("ins", s, tuple(tags))
            if n < len(lines) - 1:
                t.insert("ins", "\n")
            if h:
                t.tag_add("h1", line_start, t.index("ins"))
        self._refresh_bi()

    # ---- Text -> mini-markdown (tout ou un passage)
    def serialize(self, start="1.0", end="end-1c"):
        t = self.txt
        start, end = t.index(start), t.index(end)
        l0, l1 = int(start.split(".")[0]), int(end.split(".")[0])
        out = []
        for ln in range(l0, l1 + 1):
            a = start if ln == l0 else f"{ln}.0"
            b = end if ln == l1 else t.index(f"{ln}.end")
            active = {x for x in t.tag_names(a) if x in ("b", "i") or x in self.link_urls}
            parts, link_buf, link_url = [], [], None
            for key, val, idx in t.dump(a, b, text=True, tag=True, window=True):
                if key == "tagon":
                    if val in ("b", "i") or val in self.link_urls:
                        active.add(val)
                elif key == "tagoff":
                    active.discard(val)
                elif key == "text":
                    s = md_escape(val.replace("\n", ""))
                    if not s:
                        continue
                    if "i" in active:
                        s = f"_{s}_"
                    if "b" in active:
                        s = f"**{s}**"
                    lt = next((x for x in active if x in self.link_urls), None)
                    url = self.link_urls.get(lt) if lt else None
                    if url != link_url and link_url is not None:
                        parts.append("[" + "".join(link_buf) + f"]({link_url})"); link_buf = []
                    link_url = url
                    (link_buf if url else parts).append(s)
                elif key == "window":
                    eid = self.cards.get(str(val))
                    if link_url is not None:
                        parts.append("[" + "".join(link_buf) + f"]({link_url})"); link_buf, link_url = [], None
                    if eid:
                        parts.append(f"\u27e6e:{eid}\u27e7")
            if link_url is not None:
                parts.append("[" + "".join(link_buf) + f"]({link_url})")
            line = re.sub(r"(?<!\\)__", "", re.sub(r"(?<!\\)\*\*\*\*", "", "".join(parts)))
            if "h1" in t.tag_names(f"{ln}.0") and (ln != l0 or start.endswith(".0")):
                line = "# " + line
            out.append(line)
        return "\n".join(out)

    # ---- cartes (pieces integrees dans le texte)
    def _insert_card(self, m, index):
        tk = self.tk
        fr = tk.Frame(self.txt, bg=C["CARD"], highlightthickness=1, highlightbackground=C["LINE"], padx=8, pady=6,
                      cursor="arrow")
        self.cards[str(fr)] = m["id"]
        self.card_frames[m["id"]] = fr
        self._fill_card(fr, m)
        self.txt.window_create(index, window=fr, padx=4, pady=6, align="baseline")
        return fr

    def _card_width(self):
        try:
            pad = int(float(str(self.txt.cget("padx"))))
            return max(self.px(320), min(self.px(680), self.txt.winfo_width() - 2 * pad - 40))
        except Exception:
            return 520

    def _reflow(self, e=None):
        """grand ecran : le texte reste une belle colonne de lecture centree (comme une page)."""
        try:
            colmax = int(1000 * self.ui_scale)
            pad = max(self.px(16), (self.txt.winfo_width() - colmax) // 2)
            if abs(pad - int(float(str(self.txt.cget("padx"))))) > 6:
                self.txt.configure(padx=pad)
        except Exception:
            pass

    def _fill_card(self, fr, m, root_dir=None, readonly=False):
        tk = self.tk
        for wdg in fr.winfo_children():
            wdg.destroy()
        absp = (lambda rel: os.path.join(root_dir, *rel.split("/")) if rel else "") if root_dir else self.j.abs
        k = m.get("kind")
        p = absp(m.get("path"))
        W = self._card_width()
        menu_items = []
        bgc = C["CARD"]
        if k == "image":
            try:
                from PIL import Image, ImageTk
                im = Image.open(p); im.thumbnail((W, self.px(440)))
                ph = ImageTk.PhotoImage(im); self.imgs.append(ph)
                lab = tk.Label(fr, image=ph, bg=bgc, cursor="hand2")
            except Exception:
                lab = tk.Label(fr, text="\U0001f5bc " + (m.get("name") or "image"), bg=bgc, fg=C["TEXT"])
            lab.pack()
            lab.bind("<Button-1>", lambda e: pc.open_path(p))
            row = tk.Frame(fr, bg=bgc); row.pack(fill="x", pady=(4, 0))
            tk.Label(row, text=m.get("name", ""), bg=bgc, fg=C["DIM"], font=("Segoe UI", 8)).pack(side="left")
            self.btn(row, "Copier l'image", lambda: (clipboard_write(m.get("name", ""), "", p), self.toast("\U0001f4cb Image copi\u00e9e : colle-la o\u00f9 tu veux.")), small=True).pack(side="right", padx=2)
            self.btn(row, "Ouvrir", lambda: pc.open_path(p), small=True).pack(side="right", padx=2)
        elif k == "audio":
            meta = emeta(m)
            dur = meta.get("duree") or wav_duration(p)
            row = tk.Frame(fr, bg=bgc); row.pack(fill="x")
            b = self.btn(row, "\u25b6", None, acc=True, small=True)
            b.pack(side="left")
            tk.Label(row, text=f"\U0001f399 M\u00e9mo vocal \u00b7 {fmt_dur(dur)}", bg=bgc, fg=C["TEXT"],
                     font=("Segoe UI", 10, "bold")).pack(side="left", padx=8)
            bar = tk.Canvas(fr, width=W - 20, height=self.px(8), bg=C["ENTRY"], highlightthickness=0)
            bar.pack(fill="x", pady=(6, 2))
            b.configure(command=lambda: self._play(p, dur, b, bar))
            if not readonly and has_module("faster_whisper") and not m.get("transcript"):
                self.btn(row, "\U0001f4dd Transcrire", lambda: self._transcribe(m), small=True).pack(side="right")
            if m.get("transcript"):
                tk.Label(fr, text="\u00ab " + m["transcript"] + " \u00bb", bg=bgc, fg=C["DIM"], wraplength=W - 20,
                         justify="left", font=("Segoe UI", 9, "italic")).pack(anchor="w")
        elif k == "link":
            meta = emeta(m)
            url = m.get("url", "")
            self._preview_block(fr, url, W, bgc, lambda mid=m["id"]: self.refresh_card(mid) if mid not in self.copying else None,
                                archive_dir=absp(m.get("archive")) if m.get("status") == "permanent" else "", meta=meta)
            tl = tk.Label(fr, text="\U0001f517 " + (m.get("title") or url)[:90], bg=bgc, fg=C["ACC"], cursor="hand2",
                          font=("Segoe UI", 10, "bold"), wraplength=W - 20, justify="left")
            tl.pack(anchor="w")
            tl.bind("<Button-1>", lambda e: pc.open_url(url))
            tk.Label(fr, text=url[:110], bg=bgc, fg=C["DIM"], font=("Segoe UI", 8)).pack(anchor="w")
            row = tk.Frame(fr, bg=bgc); row.pack(fill="x", pady=(5, 0))
            folder = absp(m.get("archive"))
            if m.get("status") == "permanent" and folder and os.path.isdir(folder) and meta.get("source") == "archiveur":
                tk.Label(row, text=f"\u2714 Permanent \u00b7 dans l'Archiveur \u00b7 {str(meta.get('copie_le', ''))[:10]}", bg=bgc,
                         fg=C["OK"], font=("Segoe UI", 9, "bold")).pack(side="left")
                self.btn(row, "\U0001f4c2 Dossier", lambda: pc.open_path(folder), small=True,
                         tip="Le dossier de la copie (dans l'Archiveur, collection \u00ab Journal de bord \u00bb)").pack(side="right", padx=2)
                if meta.get("index") and os.path.isfile(os.path.join(folder, meta["index"])):
                    self.btn(row, "\U0001f4f0 Copie locale", lambda: pc.open_path(os.path.join(folder, meta["index"])), small=True,
                             tip="La page de l'archive : marche m\u00eame si le lien original dispara\u00eet").pack(side="right", padx=2)
                mp = os.path.join(folder, meta.get("main") or "")
                if meta.get("main") and os.path.isfile(mp) and mp.lower().endswith((".mp4", ".webm", ".mkv", ".mov", ".m4v", ".mp3", ".m4a", ".opus")):
                    self.btn(row, "\u25b6 Regarder" if meta.get("video") else "\u25b6 \u00c9couter", lambda: pc.open_path(mp),
                             small=True, acc=True, tip="Lire la copie gard\u00e9e sur ton PC").pack(side="right", padx=2)
            elif m.get("status") == "permanent" and folder and os.path.isdir(folder):
                tk.Label(row, text=f"\U0001f6e1 Permanent \u00b7 copie du {str(meta.get('copie_le', ''))[:10]}", bg=bgc,
                         fg=C["OK"], font=("Segoe UI", 9, "bold")).pack(side="left")
                for lab, key in (("PDF", "pdf"), ("Capture", "capture")):
                    if meta.get(key) and os.path.isfile(os.path.join(folder, meta[key])):
                        self.btn(row, lab, lambda f_=os.path.join(folder, meta[key]): pc.open_path(f_), small=True).pack(side="right", padx=2)
                main = meta.get("lecture") or meta.get("main")
                if main and os.path.exists(os.path.join(folder, main)):
                    self.btn(row, "Copie locale", lambda f_=os.path.join(folder, main): pc.open_path(f_), small=True, acc=True).pack(side="right", padx=2)
                else:
                    self.btn(row, "Copie locale", lambda: pc.open_path(folder), small=True, acc=True).pack(side="right", padx=2)
            elif m.get("status") == "copie" and m["id"] in self.copying:
                self._scan_beam(fr, W, m["id"])
            else:
                msg = "\U0001f517 Lien vivant" if m.get("status") != "erreur" else "\u26a0 Copie impossible pour l'instant (hors ligne ?)"
                tk.Label(row, text=msg, bg=bgc, fg=C["DIM"] if m.get("status") != "erreur" else C["ACC2"],
                         font=("Segoe UI", 9)).pack(side="left")
                if not readonly:
                    self.btn(row, "\U0001f4e6 Rendre permanent" if m.get("status") != "erreur" else "\u21bb R\u00e9essayer",
                             lambda: self.make_link_permanent(m["id"]), small=True, acc=True,
                             tip="Envoie le lien \u00e0 l'Archiveur : une copie reste sur ton PC, m\u00eame si le lien dispara\u00eet").pack(side="right")
            self.btn(row, "Ouvrir l'original", lambda: pc.open_url(url), small=True).pack(side="right", padx=2)
        else:
            row = tk.Frame(fr, bg=bgc); row.pack(fill="x")
            size = os.path.getsize(p) if p and os.path.isfile(p) else 0
            tk.Label(row, text=f"\U0001f4ce {m.get('name', '')}", bg=bgc, fg=C["TEXT"],
                     font=("Segoe UI", 10, "bold")).pack(side="left")
            tk.Label(row, text=human(size), bg=bgc, fg=C["DIM"], font=("Segoe UI", 8)).pack(side="left", padx=6)
            self.btn(row, "Dossier", lambda: pc.reveal(p), small=True).pack(side="right", padx=2)
            self.btn(row, "Ouvrir", lambda: pc.open_path(p), small=True).pack(side="right", padx=2)
        if not readonly:
            def menu(ev):
                mm = tk.Menu(self.root, tearoff=0)
                if k == "link" and m.get("status") != "permanent":
                    mm.add_command(label="\U0001f6e1 Rendre permanent", command=lambda: self.make_link_permanent(m["id"]))
                if p:
                    mm.add_command(label="Montrer dans le dossier", command=lambda: pc.reveal(p))
                mm.add_separator()
                mm.add_command(label="Retirer de l'entr\u00e9e", command=lambda: self.remove_card(m["id"]))
                mm.tk_popup(ev.x_root, ev.y_root)
            for wdg in [fr] + list(fr.winfo_children()):
                wdg.bind("<Button-3>", menu, add="+")

    def _scan_beam(self, fr, W, key=None):
        """barre vivante pendant la copie (pourcentage + encouragements), puis coche."""
        tk = self.tk
        lab = tk.Label(fr, text="\U0001f6f0 Copie de la page en cours\u2026 tu peux continuer d'\u00e9crire.", bg=C["CARD"],
                       fg=C["ACC2"], font=("Segoe UI", 9))
        prog = getattr(self, "copy_progress", {})
        lab.pack(anchor="w", pady=(4, 0))
        cv = tk.Canvas(fr, width=W - 20, height=self.px(10), bg=C["ENTRY"], highlightthickness=0)
        cv.pack(fill="x", pady=(3, 0))
        t0 = time.time()

        def tick():
            if not cv.winfo_exists():
                return
            cv.delete("all")
            w = cv.winfo_width() or W
            pg = prog.get(key) if key else None
            if pg:
                try:
                    lab.configure(text=cheer(pg.get("pct"), pg.get("log", "")))
                except Exception:
                    return
                if pg.get("pct") is not None:
                    cv.create_rectangle(0, 0, w * min(1.0, pg["pct"] / 100.0), 10, outline="", fill=_mix(C["ENTRY"], C["OK"], 0.55))
            x = ((time.time() - t0) * 0.6 % 1.0) * (w + 120) - 60
            for k in range(12):
                cv.create_rectangle(x - 60 + k * 10, 0, x - 50 + k * 10, 10, outline="",
                                    fill=_mix(C["ENTRY"], C["ACC"], 1 - abs(k - 6) / 6))
            cv.after(40 if self.anim.on else 400, tick)
        tick()

    def _check_flash(self, fr):
        tk = self.tk
        if not self.anim.on or not fr.winfo_exists():
            return
        lab = tk.Label(fr, text="\u2714", bg=C["CARD"], fg=C["OK"], font=("Segoe UI", 8, "bold"))
        lab.place(relx=1.0, x=-30, y=2)
        sizes = [8, 12, 16, 20, 22, 20, 18, 18, 18, 18, 18, 18, 16, 12]

        def step(i=0):
            if not lab.winfo_exists():
                return
            if i >= len(sizes):
                lab.destroy(); return
            lab.configure(font=("Segoe UI", sizes[i], "bold"))
            lab.after(45, step, i + 1)
        step()

    def remove_card(self, eid):
        fr = self.card_frames.pop(eid, None)
        if fr:
            try:
                idx = self.txt.index(fr)
                self.txt.delete(idx)
            except Exception:
                pass
            self.cards.pop(str(fr), None)
            try:
                fr.destroy()
            except Exception:
                pass
        self.j.remove_embed(eid)
        self._mark_dirty(); self.save_now()
        self.toast("Pi\u00e8ce retir\u00e9e. (Elle est gard\u00e9e dans _corbeille du journal, au cas o\u00f9.)")

    def refresh_card(self, eid):
        fr = self.card_frames.get(eid)
        m = self.j.embed(eid)
        if fr and m and fr.winfo_exists():
            self._fill_card(fr, m)
            return fr

    # ---- son
    def _play(self, p, dur, b, bar):
        if self.playing:
            self._stop_play()
            if self.playing_btn is b:
                return
        self.playing_btn = b
        try:
            if IS_WIN and p.lower().endswith(".wav"):
                import winsound
                winsound.PlaySound(p, winsound.SND_FILENAME | winsound.SND_ASYNC)
            elif has_module("sounddevice") and has_module("soundfile"):
                import sounddevice as sd, soundfile as sf
                data, sr = sf.read(p); sd.play(data, sr)
            else:
                pc.open_path(p); return
        except Exception as ex:
            self.toast(f"Lecture impossible : {ex}"); return
        self.playing = (time.time(), dur or 1, bar, b)
        b.configure(text="\u25a0")

        def tick():
            if not self.playing or self.playing[2] is not bar:
                return
            t = time.time() - self.playing[0]
            try:
                bar.delete("all")
                w = bar.winfo_width()
                bar.create_rectangle(0, 0, w * min(1, t / self.playing[1]), 8, fill=C["ACC"], outline="")
            except Exception:
                return
            if t >= self.playing[1] + 0.2:
                self._stop_play(); return
            bar.after(80, tick)
        tick()

    def _stop_play(self):
        try:
            if IS_WIN:
                import winsound
                winsound.PlaySound(None, 0)
            if has_module("sounddevice"):
                import sounddevice as sd
                sd.stop()
        except Exception:
            pass
        if self.playing:
            try:
                self.playing[3].configure(text="\u25b6")
                self.playing[2].delete("all")
            except Exception:
                pass
        self.playing = None

    def _transcribe(self, m):
        self.toast("\U0001f4dd Transcription locale en cours (la premi\u00e8re fois, le mod\u00e8le se pr\u00e9pare)\u2026", seconds=6)

        def work():
            from faster_whisper import WhisperModel
            model = WhisperModel("small", device="cpu", compute_type="int8")
            segs, _info = model.transcribe(self.j.abs(m["path"]), language="fr")
            return " ".join(s.text.strip() for s in segs).strip()

        def done(txt):
            self.j.update_embed(m["id"], transcript=txt or "(rien entendu)")
            self.refresh_card(m["id"]); self.status("\U0001f4dd Transcription ajout\u00e9e.", True)
        self.bg(work, done)

    # ------------------------------------------------------------ entrees : ouvrir / nouvelle / enregistrer
    def _load_into_editor(self, e):
        self.loading = True
        t = self.txt
        self._stop_play()
        t.delete("1.0", "end")
        for fr in list(self.card_frames.values()):
            try:
                fr.destroy()
            except Exception:
                pass
        self.cards.clear(); self.card_frames.clear(); self.imgs.clear(); self.link_urls.clear()
        embeds = {m["id"]: m for m in self.j.embeds(e["id"])} if self.j.exists(e["id"]) else {}
        body = e.get("body") or ""
        missing = [i for i in embeds if i not in set(md_embed_ids(body))]
        if missing:   # une piece n'est jamais perdue : on la remet a la fin
            body = body.rstrip() + "\n" + "\n".join(f"\u27e6e:{i}\u27e7" for i in missing)
        self.insert_md("1.0", body, embeds)
        self._tag_stamps()
        for fr in list(getattr(self, "tprev", {}).values()):
            try:
                fr.destroy()
            except Exception:
                pass
        self.tprev = {}
        d = parse_iso(e["created"])
        try:
            foc = self.root.focus_get()
        except Exception:
            foc = None
        for en, var, val in ((self.title_en, self.v_title, e.get("title") or ""), (self.date_en, self.v_date, d.strftime("%Y-%m-%d %H:%M")),
                             (self.lieu_en, self.v_lieu, e.get("lieu") or ""), (self.tags_en, self.v_tags, e.get("tags") or "")):
            en._ph = False; en.configure(fg=C["TEXT"]); var.set(val)
            if not val:
                if en is not foc and hasattr(en, "_show_ph"):
                    en._show_ph()
        self.v_moodsel, self.v_weathersel = e.get("mood") or "", e.get("weather") or ""
        self._paint_moods()
        t.edit_reset(); t.edit_modified(False)
        self.dirty = False
        self.loading = False
        if OPTS["stellaire"]:
            fl = random.Random(e["id"]).choice(FLAVOR).format(sd=stardate(d))
        else:
            fl = "\u270e " + date_fr(d).capitalize()
        self.anim.typewrite(self.flavor, fl)
        self._paint_fav(); self._update_wc()
        self.root.after(30, lambda: self._scan_text_links(False))

    def open_entry(self, eid):
        if not eid:
            return
        e = self.j.entry(eid)
        if not e:
            return
        if e.get("sealed"):
            self.open_sealed_dialog(eid); return
        self.save_now()
        self.cur = e
        self._load_into_editor(e)
        self.st["derniere"] = eid; save_settings(self.st)
        self._highlight_list()
        self.txt.mark_set("insert", "end-1c")
        self._continue_here(e, parse_iso(e.get("updated") or e["created"]))
        self._highlight_hits()

    def _highlight_list(self):
        for i, card in getattr(self, "list_cards", {}).items():
            on = self.cur and self.cur.get("id") == i
            col = C["BTNH"] if on else C["CARD"]
            try:
                card.configure(bg=col)
                for wdg in card.winfo_children():
                    wdg.configure(bg=col)
                    for w2 in wdg.winfo_children():
                        w2.configure(bg=col)
            except Exception:
                pass

    def new_entry(self):
        self.save_now()
        self.cur = self.j.new_entry()
        self._load_into_editor(self.cur)
        if self.st.get("horodatage", True):
            self._insert_stamp()
        self._highlight_list()
        self.txt.focus_set()
        self.status("\u2795 Nouvelle entr\u00e9e : \u00e9cris, colle, parle\u2026 tout s'enregistre tout seul.")

    def _ensure_saved(self):
        """une piece arrive : l'entree doit exister en base."""
        if self.cur and not self.j.exists(self.cur["id"]):
            self.collect(); self.j.save_entry(self.cur)
            self.root.after(10, self.refresh_list)

    def _current_saved_id(self):
        self.save_now(force=True)
        return self.cur["id"] if self.cur and self.j.exists(self.cur["id"]) else None

    def collect(self):
        e = self.cur
        body = self.serialize()
        ls = body.rstrip().split("\n")
        while ls and STAMP_LINE.match(ls[-1]) and ls[-1].strip():   # une heure seule a la fin (rien ecrit dessous) n'est pas gardee
            ls.pop()
            while ls and not ls[-1].strip():
                ls.pop()
        e["body"] = "\n".join(ls) if ls != body.rstrip().split("\n") else body
        e["title"] = self._val(self.title_en, self.v_title).strip()
        e["lieu"] = self._val(self.lieu_en, self.v_lieu).strip()
        e["tags"] = ", ".join(t.strip() for t in self._val(self.tags_en, self.v_tags).split(",") if t.strip())
        e["mood"], e["weather"] = self.v_moodsel, self.v_weathersel
        ds = self.v_date.get().strip()
        try:
            e["created"] = dt.datetime.strptime(ds, "%Y-%m-%d %H:%M").strftime("%Y-%m-%dT%H:%M:00")
        except Exception:
            pass
        return e

    def _on_modified(self, _e=None):
        if self.txt.edit_modified():
            self.txt.edit_modified(False)
            self._mark_dirty()
            if getattr(self, "_wc_job", None):
                self.root.after_cancel(self._wc_job)
            self._wc_job = self.root.after(400, self._update_wc)

    def _mark_dirty(self):
        if self.loading or not self.cur:
            return
        self.dirty = True
        if self.save_job:
            self.root.after_cancel(self.save_job)
        self.save_job = self.root.after(1500, self.save_now)
        self.status("\u270d \u00c9criture\u2026 (enregistrement automatique)")

    def save_now(self, force=False):
        if self.save_job:
            try:
                self.root.after_cancel(self.save_job)
            except Exception:
                pass
            self.save_job = None
        if not self.cur or (not self.dirty and not force):
            return False
        try:
            e = self.collect()
            new = not self.j.exists(e["id"])
            empty = not EMB_RX.sub("", body_sans_stamps(e["body"])).strip() and not e["title"] and not md_embed_ids(e["body"]) \
                and not e["lieu"] and not e["tags"] and not e["mood"]
            if new and empty:
                return False
            self.j.save_entry(e)
            self.dirty = False
            self.status(f"\u2714 Enregistr\u00e9 \u00e0 {time.strftime('%H:%M:%S')}", True)
            if new:
                self.refresh_list(); self._milestone()
                self._pulse(getattr(self, "list_cards", {}).get(e["id"]))
            else:
                self._update_list_card(e)
            return True
        except Exception as ex:
            traceback.print_exc()
            self._emergency_copy()
            self.status(f"\u26a0 Enregistrement retard\u00e9 ({ex}) \u2014 une copie de secours est gard\u00e9e.")
            return False

    def _emergency_copy(self):
        try:
            d = os.path.join(pc.settings_dir(), "journal_secours")
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, f"{self.cur['id']}.json"), "w", encoding="utf-8") as f:
                json.dump(self.cur, f, ensure_ascii=False)
        except Exception:
            pass

    def _update_list_card(self, e):
        card = getattr(self, "list_cards", {}).get(e["id"])
        if not card or not card.winfo_exists():
            return
        try:
            kids = card.winfo_children()
            kids[0].configure(text=e.get("mood") or "\U0001f4dd")
            col = kids[1].winfo_children()
            col[0].configure(text=(e.get("title") or self._auto_title(e))[:60])
            snip = md_strip(e.get("body"), 90)
            col[2].configure(text=snip)
        except Exception:
            pass

    def consign(self):
        if not self.cur:
            return
        self.dirty = True
        ok = self.save_now(force=True)
        if ok or self.j.exists(self.cur["id"]):
            self.anim.seal(self.holder)
            self.status(f"\u2726 Consign\u00e9 au journal \u00b7 {time.strftime('%H:%M')}"
                        + (f" \u00b7 date stellaire {stardate()}" if OPTS["stellaire"] else ""), True)
            self.toast("\u2714 Consign\u00e9 ! Ton entr\u00e9e est bien gard\u00e9e sur ce PC.", seconds=2.6)
            self._paint_streak()
        else:
            self.status("Rien \u00e0 consigner pour l'instant : \u00e9cris quelques mots d'abord.")

    def _milestone(self):
        n = self.j.count()
        for k in (1, 10, 50, 100, 250, 500, 1000):
            if n == k and k not in self.st.get("jalons", []):
                self.st.setdefault("jalons", []).append(k); save_settings(self.st)
                msg = {1: "Premi\u00e8re entr\u00e9e au journal, capitaine ! \u2728",
                       100: "100e entr\u00e9e, capitaine ! \U0001f389"}.get(k, f"{k} entr\u00e9es au journal ! \u2728")
                if self.anim.on:
                    self.anim.confetti(self.right, msg)
                else:
                    self.toast(msg)
        self._maybe_offer_lock()

    def delete_current(self):
        if self.cur and self.j.exists(self.cur["id"]):
            self.delete_entry(self.cur["id"])

    def delete_entry(self, eid):
        self.save_now()
        self.j.delete_entry(eid)
        if self.cur and self.cur["id"] == eid:
            self.cur = None
            nxt = self._first_open_id()
            self.open_entry(nxt) if nxt else self.new_entry()
        self.refresh_list()
        self.toast("\U0001f5d1 Entr\u00e9e mise \u00e0 la corbeille (Journal \u25b8 Corbeille pour la retrouver).", [("Annuler", lambda: (self.j.delete_entry(eid, undo=True), self.refresh_list(), self.open_entry(eid)))], 8)

    # ------------------------------------------------------------ coller : tout devient la bonne piece
    def smart_paste(self):
        if not self.cur:
            self.new_entry()
        t = self.txt
        if t.tag_ranges("sel"):
            self._delete_sel()
        t.mark_set("paste", "insert"); t.mark_gravity("paste", "right")
        clip = clipboard_read()
        if not clip["files"] and clip["image"] is None and not clip["html"]:
            try:
                clip["text"] = clip["text"] or self.root.clipboard_get()
            except Exception:
                pass
        text = (clip["text"] or "").strip()
        if not clip["files"] and clip["image"] is None and not clip["html"] and not text:
            self.status("Le presse-papiers est vide : copie quelque chose d'abord (Ctrl+C).")
            return
        if not clip["files"] and clip["image"] is None and (not clip["html"] or not html_visible_text(clip["html"])[0]) \
                and not (clip["html"] and html_visible_text(clip["html"])[1]):
            if URL_RX.fullmatch(text):
                self.add_link_card(text, index="paste"); return
            raw = clip["text"] or text
            if len(raw) > 400000:
                raw = raw[:400000]
                self.toast("Texte tr\u00e8s long : j'ai coll\u00e9 les 400 000 premiers caract\u00e8res.")
            self.insert_md("paste", autolink_md(md_escape(raw)))
            self._mark_dirty(); t.see("insert"); return
        self._ensure_saved()
        e = dict(self.cur)
        self.status("\U0001f4cb Je colle\u2026")

        def done(res):
            md, new, what = res
            if not md:
                self.status("Rien d'utilisable dans le presse-papiers."); return
            self.insert_md("paste", md, {m["id"]: m for m in new})
            self._mark_dirty(); self.save_now()
            t.see("paste")
            self.status(f"\U0001f4cb Coll\u00e9 : {what}.", True)
            for m in new:
                if m.get("kind") == "link" and self.st.get("liens_auto"):
                    self.make_link_permanent(m["id"])
        self.bg(lambda: clip_to_md(self.j, e, clip), done)

    def _delete_sel(self):
        t = self.txt
        if not t.tag_ranges("sel"):
            return
        a, b = t.index("sel.first"), t.index("sel.last")
        gone = [self.cards.pop(str(v), None) for k, v, i in t.dump(a, b, window=True) if k == "window"]
        t.delete(a, b)
        for eid in gone:
            self.card_frames.pop(eid, None)
        for eid in gone:
            if eid:
                self.toast("Une pi\u00e8ce a \u00e9t\u00e9 effac\u00e9e du texte : elle sera remise \u00e0 la fin de l'entr\u00e9e. "
                           "(Pour la retirer pour de bon : clic droit > Retirer.)", seconds=6)
                break
        self._mark_dirty()

    def paste_today(self):
        """capture le presse-papiers dans l'entree du jour."""
        self.save_now()
        e = self.j.today_entry()
        if not self.cur or self.cur["id"] != e["id"]:
            self.open_entry(e["id"])
        self.txt.mark_set("insert", "end-1c")
        if self.txt.get("1.0", "end-1c").strip():
            self.txt.insert("end-1c", "\n\n")
            self.txt.insert("end-1c", time.strftime("%H:%M") + " \u00b7 ", ("i",))
        self.smart_paste()

    def _on_drop(self, ev):
        data = ev.data or ""
        try:
            items = list(self.root.tk.splitlist(data))
        except Exception:
            items = [data]
        files = [p for p in items if os.path.exists(p)]
        if not self.cur:
            self.new_entry()
        if files:
            self._ensure_saved()
            for p in files[:40]:
                try:
                    m = self.j.add_file(self.cur, p)
                    self._insert_card(m, "insert")
                    self.txt.insert("insert", "\n")
                except Exception as ex:
                    self.toast(f"Impossible d'ajouter {os.path.basename(p)} : {ex}")
            self._mark_dirty(); self.save_now()
        elif URL_RX.fullmatch(data.strip()):
            self.add_link_card(data.strip())
        elif data.strip():
            self.insert_md("insert", autolink_md(md_escape(data)))
            self._mark_dirty()
        return ev.action if hasattr(ev, "action") else None

    # ------------------------------------------------------------ copier un passage
    def copy_passage(self, mode="riche"):
        t = self.txt
        if not t.tag_ranges("sel") or not self.cur:
            self.status("S\u00e9lectionne d'abord un passage (glisse la souris sur le texte)."); return
        md = self.serialize("sel.first", "sel.last")
        ids = set(md_embed_ids(md))
        embeds = [m for m in self.j.embeds(self.cur["id"])] if self.j.exists(self.cur["id"]) else []
        embeds = [m for m in embeds if m["id"] in ids]       # seulement ce passage, rien d'autre
        plain = md_to_plain(md, embeds)
        if mode == "page":
            self.save_now()
            e = self.collect()
            name = f"extrait_{time.strftime('%Y-%m-%d_%H%M%S')}_{slug(e.get('title') or 'journal', 30)}.html"
            out = os.path.join(partages_dir(), name)
            try:
                export_segment_html(self.j, e, md, out)
            except Exception as ex:
                self.toast(f"\u26a0 {ex}"); return
            self.toast("\U0001f4c4 Mini-page du passage pr\u00eate (images et vocaux inclus).",
                       [("Ouvrir", lambda: pc.open_path(out)), ("Montrer", lambda: pc.reveal(out))], 8)
            return
        if mode == "texte":
            ok = clipboard_write(plain)
            if not ok:
                self.root.clipboard_clear(); self.root.clipboard_append(plain)
            self.status("\U0001f9f9 Passage copi\u00e9 en texte simple.", True); return
        frag = md_to_html(self.j, md, embeds, compact=True)
        single = [m for m in embeds if m["kind"] == "image"]
        img = self.j.abs(single[0]["path"]) if len(single) == 1 and len(embeds) == 1 else ""
        ok = False
        try:
            ok = clipboard_write(plain, frag, img)
        except Exception:
            traceback.print_exc()
        if not ok:
            self.root.clipboard_clear(); self.root.clipboard_append(plain)
        self.status("\U0001f4cb Passage copi\u00e9 : colle-le dans un courriel, Word ou un message (texte + images).", True)

    def _sel_bar(self):
        t = self.txt
        try:
            if not t.tag_ranges("sel"):
                self.selbar.place_forget(); return
            bb = t.bbox("sel.last") or t.bbox("sel.first")
            if not bb:
                self.selbar.place_forget(); return
            x = min(max(10, bb[0] - 120), max(10, t.winfo_width() - 380))
            y = bb[1] + bb[3] + 6
            if y > t.winfo_height() - 40:
                y = max(4, bb[1] - 38)
            self.selbar.place(in_=t, x=x, y=y)
            self.selbar.lift()
        except Exception:
            self.selbar.place_forget()

    def _text_menu(self, ev):
        tk = self.tk
        m = tk.Menu(self.root, tearoff=0)
        has = bool(self.txt.tag_ranges("sel"))
        m.add_command(label="\U0001f4cb Coller (n'importe quoi)", command=self.smart_paste)
        if has:
            m.add_separator()
            m.add_command(label="\U0001f4cb Copier ce passage (texte + images)", command=lambda: self.copy_passage("riche"))
            m.add_command(label="\U0001f9f9 Copier en texte seul", command=lambda: self.copy_passage("texte"))
            m.add_command(label="\U0001f4c4 Mini-page \u00e0 partager (.html)", command=lambda: self.copy_passage("page"))
            m.add_separator()
            m.add_command(label="Gras", command=lambda: self._toggle_tag("b"))
            m.add_command(label="Italique", command=lambda: self._toggle_tag("i"))
            m.add_command(label="\U0001f517 Faire un lien\u2026", command=self._sel_to_link)
        m.tk_popup(ev.x_root, ev.y_root)

    def _sel_to_link(self):
        from tkinter import simpledialog
        t = self.txt
        if not t.tag_ranges("sel"):
            return
        url = simpledialog.askstring(APP, "Adresse du lien (https://\u2026) :", parent=self.root)
        if url and url.startswith(("http://", "https://")):
            t.tag_add("lnk", "sel.first", "sel.last")
            t.tag_add(self._link_tag(url), "sel.first", "sel.last")
            self._mark_dirty()

    # ------------------------------------------------------------ liens
    def ask_link(self):
        tk = self.tk
        if not self.cur:
            self.new_entry()
        top = tk.Toplevel(self.root); top.title("Ajouter un lien"); top.configure(bg=C["BG"]); top.transient(self.root)
        top.geometry(f"+{self.root.winfo_rootx() + self.px(200)}+{self.root.winfo_rooty() + self.px(160)}")
        tk.Label(top, text="\U0001f517 Colle l'adresse du lien", bg=C["BG"], fg=C["TEXT"], font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=16, pady=(14, 4))
        v = tk.StringVar()
        try:
            c = self.root.clipboard_get().strip()
            if URL_RX.fullmatch(c):
                v.set(c)
        except Exception:
            pass
        en = tk.Entry(top, textvariable=v, width=60, bg=C["ENTRY"], fg=C["TEXT"], insertbackground=C["TEXT"], relief="flat",
                      font=("Segoe UI", 10))
        en.pack(padx=16, ipady=4, fill="x"); en.focus_set()
        vp = tk.BooleanVar(value=True)
        tk.Checkbutton(top, text="\U0001f6e1 Rendre ce lien permanent (une copie de la page est gard\u00e9e sur ton PC)",
                       variable=vp, bg=C["BG"], fg=C["TEXT"], selectcolor=C["ENTRY"], activebackground=C["BG"],
                       activeforeground=C["TEXT"]).pack(anchor="w", padx=12, pady=8)

        def ok(_e=None):
            url = v.get().strip()
            if not url.startswith(("http://", "https://")):
                url = "https://" + url if "." in url and " " not in url else ""
            if not url:
                return
            top.destroy()
            m = self.add_link_card(url, offer=False)
            if m and vp.get():
                self.make_link_permanent(m["id"])
        row = tk.Frame(top, bg=C["BG"]); row.pack(fill="x", padx=16, pady=(0, 14))
        self.btn(row, "Ajouter", ok, acc=True).pack(side="right")
        self.btn(row, "Annuler", top.destroy).pack(side="right", padx=6)
        en.bind("<Return>", ok); top.bind("<Escape>", lambda e: top.destroy())

    def add_link_card(self, url, offer=True, index="insert"):
        self._ensure_saved()
        m = self.j.add_link(self.cur, url)
        self._insert_card(m, index)
        self.txt.insert(index, "\n")
        self._mark_dirty(); self.save_now()
        self.status("\U0001f517 Lien ajout\u00e9" + (" \u2014 clique \u00ab Rendre ce lien permanent \u00bb pour en garder une copie." if offer else "."), True)

        def work():
            return fetch_title(url)

        def done(title):
            if title:
                self.j.update_embed(m["id"], title=title)
                if self.j.embed(m["id"]).get("status") != "copie":
                    self.refresh_card(m["id"])
        self.bg(work, done, lambda msg: None)
        if offer and self.st.get("liens_auto"):
            self.make_link_permanent(m["id"])
        return m

    def make_link_permanent(self, emb_id):
        m = self.j.embed(emb_id)
        if not m or emb_id in self.copying:
            return
        self.copying.add(emb_id)
        self.j.update_embed(emb_id, status="copie")
        self.refresh_card(emb_id)
        way = bool(self.st.get("wayback")) and bool(self.st.get("mode_avance"))
        logs = []

        def done(m2):
            self.copying.discard(emb_id)
            fr = self.refresh_card(emb_id)
            if fr:
                self._check_flash(fr)
            m3 = self.j.embed(emb_id) or {}
            self.status("\u2714 Lien rendu permanent : la copie est sur ton PC" +
                        (" (Archiveur, collection \u00ab Journal de bord \u00bb)." if emeta(m3).get("source") == "archiveur" else "."), True)
            self.toast("\u2714 Permanent ! M\u00eame si le lien dispara\u00eet, ta copie reste dans ton journal.", seconds=4)

        def err(msg):
            self.copying.discard(emb_id)
            self.j.update_embed(emb_id, status="erreur")
            self.refresh_card(emb_id)
            self.status("\u26a0 Copie impossible pour l'instant (connexion ?). Le lien reste dans l'entr\u00e9e ; tu pourras r\u00e9essayer.")
        if not hasattr(self, "copy_progress"):
            self.copy_progress = {}
        prog = self.copy_progress[emb_id] = {"pct": None, "log": ""}

        def ev(k, v):
            prog[k] = v

        def work():
            m0 = self.j.embed(emb_id)
            if archiveur_ok():
                try:
                    return make_permanent_archiveur(self.j, m0, ev)
                except Exception as ex:
                    logs.append(f"Archiveur : {ex}")
                    traceback.print_exc()
            return make_permanent(self.j, m0, logs.append, way)
        self.bg(work, done, err)

    # ------------------------------------------------------------ images / fichiers
    def pick_image(self):
        from tkinter import filedialog
        ps = filedialog.askopenfilenames(parent=self.root, title="Choisir des images",
                                         filetypes=[("Images", "*.png *.jpg *.jpeg *.gif *.webp *.bmp"), ("Tous", "*.*")])
        self._add_files(ps)

    def pick_file(self):
        from tkinter import filedialog
        self._add_files(filedialog.askopenfilenames(parent=self.root, title="Joindre des fichiers"))

    def _add_files(self, ps):
        if not ps:
            return
        if not self.cur:
            self.new_entry()
        self._ensure_saved()
        for p in ps:
            try:
                m = self.j.add_file(self.cur, p)
                self._insert_card(m, "insert"); self.txt.insert("insert", "\n")
            except Exception as ex:
                self.toast(f"Impossible d'ajouter {os.path.basename(p)} : {ex}")
        self._mark_dirty(); self.save_now()

    # ------------------------------------------------------------ memo vocal
    def record(self):
        tk = self.tk
        if not (has_module("sounddevice") and has_module("numpy")):
            self.toast("Le module audio n'est pas install\u00e9 : lance \u00ab R\u00e9parer l'installation Padawan \u00bb (menu D\u00e9marrer)."); return
        import sounddevice as sd
        import numpy as np
        if not self.cur:
            self.new_entry()
        self.txt.mark_set("recpoint", "insert"); self.txt.mark_gravity("recpoint", "left")
        SR = 22050
        chunks, levels = [], [0.0] * 48
        stt = {"on": True, "t0": time.time(), "err": None}

        def cb(indata, frames, tinfo, status):
            chunks.append(indata.copy())
            levels.append(float(np.abs(indata).mean()) / 3000.0)
            del levels[:-48]
        try:
            stream = sd.InputStream(samplerate=SR, channels=1, dtype="int16", callback=cb)
            stream.start()
        except Exception as ex:
            self.toast("\U0001f3a4 Je n'entends pas de micro sur ce PC. Branche-en un (ou active-le dans Windows) et r\u00e9essaie.\n"
                       f"({str(ex)[:80]})", seconds=7)
            return
        top = tk.Toplevel(self.root); top.overrideredirect(True); top.configure(bg=C["PANEL"])
        q = self.ui_scale
        w, h = 420, 190                                     # unites logiques (cv.scale ensuite)
        W_, H_ = self.px(w), self.px(h)
        top.geometry(f"{W_}x{H_}+{self.root.winfo_rootx() + self.root.winfo_width() // 2 - W_ // 2}+{self.root.winfo_rooty() + self.px(120)}")
        try:
            top.attributes("-topmost", True)
        except Exception:
            pass
        cv = tk.Canvas(top, width=W_, height=self.px(120), bg=C["PANEL"], highlightthickness=1, highlightbackground=C["REC"])
        cv.pack(fill="x")
        row = tk.Frame(top, bg=C["PANEL"]); row.pack(fill="x", pady=10)

        def finish(keep):
            if not stt["on"]:
                return
            stt["on"] = False
            try:
                stream.stop(); stream.close()
            except Exception:
                pass
            top.destroy()
            if not keep or not chunks:
                self.status("Enregistrement annul\u00e9."); return
            data = np.concatenate(chunks)
            if len(data) < SR * 0.4:
                self.status("Enregistrement trop court : r\u00e9essaie en parlant un peu plus longtemps."); return
            tmp = os.path.join(tempfile.gettempdir(), f"journal_memo_{uuid.uuid4().hex[:8]}.wav")
            with wave.open(tmp, "wb") as wf:
                wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(SR); wf.writeframes(data.tobytes())
            self._ensure_saved()
            m = self.j.add_audio(self.cur, tmp)
            self._insert_card(m, "recpoint"); self.txt.insert("recpoint", "\n")
            self._mark_dirty(); self.save_now()
            self.status(f"\U0001f399 M\u00e9mo vocal ajout\u00e9 ({fmt_dur(len(data) / SR)}).", True)
        self.btn(row, "\u25a0  Terminer et ajouter", lambda: finish(True), acc=True).pack(side="left", padx=14)
        self.btn(row, "Annuler", lambda: finish(False)).pack(side="right", padx=14)
        top.bind("<Escape>", lambda e: finish(False)); top.bind("<Return>", lambda e: finish(True))
        top.focus_force()

        def tick():
            if not stt["on"]:
                return
            t = time.time() - stt["t0"]
            cv.delete("all")
            pulse = 7 + 3 * math.sin(t * 6) if self.anim.on else 8
            cv.create_oval(24 - pulse, 30 - pulse, 24 + pulse, 30 + pulse, fill=C["REC"], outline="")
            if self.anim.on:
                rr = 10 + (t * 30) % 22
                cv.create_oval(24 - rr, 30 - rr, 24 + rr, 30 + rr, outline=_mix(C["REC"], C["PANEL"], (rr - 10) / 22))
            cv.create_text(48, 30, anchor="w", text=f"Enregistrement\u2026  {fmt_dur(t)}", fill=C["TEXT"], font=("Segoe UI", 12, "bold"))
            bw = (w - 40) / len(levels)
            for i, lv in enumerate(levels):
                hh = max(2, min(40, lv * 120 * (1 + (0.15 * math.sin(t * 9 + i) if self.anim.on else 0))))
                x = 20 + i * bw
                cv.create_rectangle(x, 85 - hh, x + bw - 2, 85 + hh, fill=_mix(C["ACC"], C["REC"], min(1, lv * 3)), outline="")
            if q != 1.0:
                cv.scale("all", 0, 0, q, q)
            if t > 1800:
                finish(True); return
            top.after(40, tick)
        tick()

    # ------------------------------------------------------------ partager
    def share(self, how, eid):
        from tkinter import filedialog
        if not eid:
            self.toast("\u00c9cris d'abord quelques mots : une entr\u00e9e vide ne se partage pas."); return
        e = self.j.entry(eid)
        if not e or e.get("sealed"):
            self.toast("Les entr\u00e9es scell\u00e9es ne se partagent jamais."); return
        base = f"{parse_iso(e['created']).strftime('%Y-%m-%d')}_{slug(e.get('title') or self._auto_title(e), 40)}"
        if how in ("html", "pdf", "zip"):
            ext = {"html": ".html", "pdf": ".pdf", "zip": ".zip"}[how]
            out = filedialog.asksaveasfilename(parent=self.root, initialdir=partages_dir(), initialfile=base + ext,
                                               defaultextension=ext, filetypes=[(ext.upper()[1:], "*" + ext)])
            if not out:
                return
            if out.upper().startswith("F:"):
                self.toast("Choisis un autre disque que F: (cl\u00e9 d'installation)."); return
            fn = {"html": export_html, "pdf": export_pdf, "zip": export_zip}[how]
            self.status("\U0001f4e4 Pr\u00e9paration du partage\u2026")
            self.bg(lambda: fn(self.j, [eid], out),
                    lambda p: self.toast("\u2728 C'est pr\u00eat ! Seule cette entr\u00e9e est dedans.",
                                         [("Ouvrir", lambda: pc.open_path(p)), ("Montrer", lambda: pc.reveal(p))], 9))
        elif how == "imprimer":
            self.print_entry(eid)
        elif how == "txt":
            out = filedialog.asksaveasfilename(parent=self.root, initialdir=partages_dir(), initialfile=base + ".txt",
                                               defaultextension=".txt", filetypes=[("Texte", "*.txt")])
            if not out:
                return
            with open(out, "w", encoding="utf-8-sig") as f:
                f.write(entry_plain(e, self.j.embeds(eid)))
            self.toast("\U0001f9fe Fichier texte pr\u00eat.", [("Ouvrir", lambda: pc.open_path(out)), ("Montrer", lambda: pc.reveal(out))], 8)
        elif how == "texte":
            txt = entry_plain(e, self.j.embeds(eid))
            if not clipboard_write(txt):
                self.root.clipboard_clear(); self.root.clipboard_append(txt)
            self.status("\U0001f4cb Entr\u00e9e copi\u00e9e en texte : colle-la o\u00f9 tu veux.", True)
        elif how == "grimoire":
            self.bg(lambda: send_to_grimoire(self.j, e, self.j.embeds(eid)),
                    lambda r: self.toast("\U0001f4d6 Envoy\u00e9 au Grimoire (sujet \u00ab Journal de bord \u00bb)."))
        elif how == "messager":
            out = os.path.join(partages_dir(), base + ".html")

            def done(p):
                pc.reveal(p)
                pc.launch("messager")
                self.toast("\U0001f4e8 Page pr\u00eate : glisse-la dans le Messager (le dossier est ouvert).", seconds=9)
            self.bg(lambda: export_html(self.j, [eid], out), done)

    def share_many(self):
        tk = self.tk
        from tkinter import filedialog
        self.save_now()
        es = [e for e in self._filtered()[0] if not e.get("sealed")][:300]
        top = tk.Toplevel(self.root); top.title("Partager plusieurs entr\u00e9es"); top.configure(bg=C["BG"]); top.transient(self.root)
        top.geometry(f"{self.px(560)}x{self.px(560)}+{self.root.winfo_rootx() + self.px(160)}+{self.root.winfo_rooty() + self.px(60)}")
        tk.Label(top, text="\U0001f4da Coche les entr\u00e9es \u00e0 partager", bg=C["BG"], fg=C["TEXT"],
                 font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=14, pady=(12, 0))
        tk.Label(top, text="Seules les entr\u00e9es coch\u00e9es seront dans le partage. Les scell\u00e9es n'y sont jamais.",
                 bg=C["BG"], fg=C["DIM"], font=("Segoe UI", 9)).pack(anchor="w", padx=14)
        lb = tk.Listbox(top, selectmode="multiple", bg=C["ENTRY"], fg=C["TEXT"], selectbackground=C["ACC"],
                        selectforeground=C["ONACC"], relief="flat", font=("Segoe UI", 10), activestyle="none")
        lb.pack(fill="both", expand=True, padx=14, pady=8)
        for e in es:
            d = parse_iso(e["created"])
            lb.insert("end", f"{d.strftime('%Y-%m-%d')}  {e.get('mood') or ''}  {e.get('title') or self._auto_title(e)}")
        row = tk.Frame(top, bg=C["BG"]); row.pack(fill="x", padx=14, pady=(0, 12))

        def go(kind):
            ids = [es[i]["id"] for i in lb.curselection()]
            if not ids:
                return
            ext = {"html": ".html", "pdf": ".pdf", "zip": ".zip", "txt": ".txt"}[kind]
            out = filedialog.asksaveasfilename(parent=top, initialdir=partages_dir(), defaultextension=ext,
                                               initialfile=f"journal_{len(ids)}_entrees_{time.strftime('%Y-%m-%d')}{ext}")
            if not out:
                return
            top.destroy()
            if kind == "txt":
                with open(out, "w", encoding="utf-8-sig") as f:
                    f.write(("\n\n" + "\u2500" * 40 + "\n\n").join(entry_plain(self.j.entry(i), self.j.embeds(i)) for i in ids))
                self.toast(f"\U0001f9fe {len(ids)} entr\u00e9e(s) en texte.", [("Ouvrir", lambda: pc.open_path(out))], 8)
                return
            fn = {"html": export_html, "pdf": export_pdf, "zip": export_zip}[kind]
            self.bg(lambda: fn(self.j, ids, out),
                    lambda p: self.toast(f"\u2728 {len(ids)} entr\u00e9e(s) pr\u00eate(s) \u00e0 partager.",
                                         [("Ouvrir", lambda: pc.open_path(p)), ("Montrer", lambda: pc.reveal(p))], 9))
        self.btn(row, "Tout cocher", lambda: lb.select_set(0, "end"), small=True).pack(side="left")
        lb.bind("<MouseWheel>", lambda ev: lb.yview_scroll(int(-ev.delta / 120), "units"))
        for k, lab in (("txt", "\U0001f9fe Texte"), ("zip", "\U0001f5dc .zip"), ("pdf", "\U0001f4c4 PDF"), ("html", "\U0001f310 Page web")):
            self.btn(row, lab, lambda k=k: go(k), acc=(k == "html")).pack(side="right", padx=3)

    # ------------------------------------------------------------ verrou (doux, facultatif)
    def _maybe_offer_lock(self):
        if self.st.get("verrou_propose") or self.st["verrou"].get("actif") or self.j.count() < 3:
            return
        tk = self.tk
        for wdg in self.offer.winfo_children():
            wdg.destroy()
        tk.Label(self.offer, text="\U0001f511 Envie d'un petit code pour ton journal ? (facultatif)", bg=C["PANEL"],
                 fg=C["ACC2"], font=("Segoe UI", 9)).pack(side="left")

        def later():
            self._set("verrou_propose", True)
            for wdg in self.offer.winfo_children():
                wdg.destroy()
        self.btn(self.offer, "Mettre un code", lambda: (later(), self.lock_settings()), small=True, acc=True).pack(side="left", padx=4)
        self.btn(self.offer, "Non merci", later, small=True).pack(side="left")

    def lock_settings(self):
        tk = self.tk
        top = tk.Toplevel(self.root); top.title("Verrou du journal"); top.configure(bg=C["BG"]); top.transient(self.root)
        top.geometry(f"+{self.root.winfo_rootx() + self.px(220)}+{self.root.winfo_rooty() + self.px(140)}")
        vr = self.st["verrou"]
        tk.Label(top, text="\U0001f511 Un code pour ouvrir le journal", bg=C["BG"], fg=C["TEXT"],
                 font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=16, pady=(14, 2))
        tk.Label(top, text="Pratique si d'autres utilisent ce PC. C'est une porte, pas un coffre : pour un vrai coffre-fort,\n"
                 "utilise \u00ab Sceller \u00bb sur les entr\u00e9es tr\u00e8s priv\u00e9es.", bg=C["BG"], fg=C["DIM"],
                 justify="left", font=("Segoe UI", 9)).pack(anchor="w", padx=16)
        v1, v2 = tk.StringVar(), tk.StringVar()
        for lab, v in (("Nouveau code", v1), ("Encore une fois", v2)):
            tk.Label(top, text=lab, bg=C["BG"], fg=C["TEXT"]).pack(anchor="w", padx=16, pady=(8, 0))
            tk.Entry(top, textvariable=v, show="\u2022", bg=C["ENTRY"], fg=C["TEXT"], insertbackground=C["TEXT"],
                     relief="flat", font=("Segoe UI", 12)).pack(fill="x", padx=16, ipady=3)
        msg = tk.Label(top, text="", bg=C["BG"], fg=C["ACC2"]); msg.pack(anchor="w", padx=16)

        def ok():
            if len(v1.get()) < 4:
                msg.configure(text="Au moins 4 caract\u00e8res, s'il te pla\u00eet."); return
            if v1.get() != v2.get():
                msg.configure(text="Les deux codes ne sont pas pareils."); return
            sel = os.urandom(16).hex()
            self.st["verrou"] = {"actif": True, "sel": sel, "hash": pin_hash(v1.get(), sel)}
            save_settings(self.st); top.destroy()
            self.toast("\U0001f511 Code activ\u00e9 : il sera demand\u00e9 \u00e0 la prochaine ouverture.")

        def off():
            self.st["verrou"] = {"actif": False, "sel": "", "hash": ""}; save_settings(self.st); top.destroy()
            self.toast("Verrou retir\u00e9.")
        row = tk.Frame(top, bg=C["BG"]); row.pack(fill="x", padx=16, pady=12)
        self.btn(row, "Activer le code", ok, acc=True).pack(side="right")
        if vr.get("actif"):
            self.btn(row, "Retirer le verrou", off).pack(side="right", padx=6)
        self.btn(row, "Fermer", top.destroy).pack(side="left")

    # ------------------------------------------------------------ entrees scellees
    def seal_current(self):
        eid = self._current_saved_id()
        if eid:
            self.seal_dialog(eid)
        else:
            self.toast("\u00c9cris d'abord l'entr\u00e9e, ensuite tu pourras la sceller.")

    def seal_dialog(self, eid):
        tk = self.tk
        top = tk.Toplevel(self.root); top.title("Sceller l'entr\u00e9e"); top.configure(bg=C["BG"]); top.transient(self.root)
        top.geometry(f"+{self.root.winfo_rootx() + self.px(220)}+{self.root.winfo_rooty() + self.px(120)}")
        tk.Label(top, text="\U0001f512 Sceller cette entr\u00e9e", bg=C["BG"], fg=C["TEXT"], font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=16, pady=(14, 2))
        tk.Label(top, text="Le texte et les pi\u00e8ces sont chiffr\u00e9s avec ta phrase secr\u00e8te. Elle n'est gard\u00e9e nulle part :\n"
                 "note-la dans un endroit s\u00fbr. Une entr\u00e9e scell\u00e9e n'appara\u00eet ni dans la recherche ni dans les partages.",
                 bg=C["BG"], fg=C["DIM"], justify="left", font=("Segoe UI", 9)).pack(anchor="w", padx=16)
        v1, v2, vh = tk.StringVar(), tk.StringVar(), tk.StringVar()
        for lab, v, show in (("Phrase secr\u00e8te", v1, "\u2022"), ("Encore une fois", v2, "\u2022"), ("Indice (facultatif, visible)", vh, "")):
            tk.Label(top, text=lab, bg=C["BG"], fg=C["TEXT"]).pack(anchor="w", padx=16, pady=(8, 0))
            tk.Entry(top, textvariable=v, show=show, bg=C["ENTRY"], fg=C["TEXT"], insertbackground=C["TEXT"], relief="flat",
                     font=("Segoe UI", 11)).pack(fill="x", padx=16, ipady=3)
        msg = tk.Label(top, text="", bg=C["BG"], fg=C["ACC2"]); msg.pack(anchor="w", padx=16)

        def ok():
            if len(v1.get()) < 6:
                msg.configure(text="Au moins 6 caract\u00e8res (une petite phrase, c'est encore mieux)."); return
            if v1.get() != v2.get():
                msg.configure(text="Les deux phrases ne sont pas pareilles."); return
            phrase, hint = v1.get(), vh.get().strip()
            top.destroy()
            self.save_now()
            if self.cur and self.cur["id"] == eid:
                self._load_into_editor(self.j.new_entry()); self.cur = None

            def done(r):
                if isinstance(r, Exception):
                    self.toast(f"\u26a0 Scellement impossible : {r}. Rien n'a \u00e9t\u00e9 effac\u00e9."); return
                self.refresh_list(); self.new_entry()
                self.toast("\U0001f512 Entr\u00e9e scell\u00e9e. Seule ta phrase secr\u00e8te peut la rouvrir.")
            self.anim.capsule(self.root, "Scellement de la capsule\u2026", lambda: seal_entry(self.j, eid, phrase, hint), done)
        row = tk.Frame(top, bg=C["BG"]); row.pack(fill="x", padx=16, pady=12)
        self.btn(row, "\U0001f512 Sceller", ok, acc=True).pack(side="right")
        self.btn(row, "Annuler", top.destroy).pack(side="right", padx=6)

    def open_sealed_dialog(self, eid):
        from tkinter import simpledialog
        e = self.j.entry(eid)
        ph = simpledialog.askstring(APP, "\U0001f512 Phrase secr\u00e8te de cette entr\u00e9e :" +
                                    (f"\n(indice : {e['hint']})" if e.get("hint") else ""), show="\u2022", parent=self.root)
        if not ph:
            return

        def done(r):
            if isinstance(r, Exception):
                self.toast("Ce n'est pas la bonne phrase\u2026 prends ton temps et r\u00e9essaie." if "phrase" in str(r)
                           else f"\u26a0 {r}"); return
            self._sealed_viewer(eid, ph, *r)
        self.anim.capsule(self.root, "Ouverture de la capsule\u2026", lambda: open_sealed(self.j, eid, ph), done, unlock=True)

    def _sealed_viewer(self, eid, phrase, e, embeds, tmp):
        tk = self.tk
        top = tk.Toplevel(self.root); top.title("\U0001f512 Entr\u00e9e scell\u00e9e (lecture)"); top.configure(bg=C["BG"]); top.transient(self.root)
        top.geometry(f"{self.px(760)}x{self.px(620)}+{self.root.winfo_rootx() + self.px(120)}+{self.root.winfo_rooty() + self.px(40)}")
        d = parse_iso(e["created"])
        tk.Label(top, text=(f"Date stellaire {stardate(d)} \u00b7 " if OPTS["stellaire"] else "") + date_fr(d), bg=C["BG"], fg=C["ACC"], font=("Consolas", 10)).pack(anchor="w", padx=16, pady=(10, 0))
        tk.Label(top, text=(e.get("mood") or "") + " " + (e.get("title") or "Entr\u00e9e"), bg=C["BG"], fg=C["TEXT"],
                 font=("Segoe UI", 16, "bold")).pack(anchor="w", padx=16)
        txt = tk.Text(top, wrap="word", bg=C["ENTRY"], fg=C["TEXT"], relief="flat", font=("Segoe UI", 12), padx=14, pady=10)
        txt.pack(fill="both", expand=True, padx=16, pady=8)
        em = {m["id"]: m for m in embeds}
        for h, toks in md_lines(e.get("body")):
            for tk_ in toks:
                if tk_[0] == "e" and tk_[1] in em:
                    fr = tk.Frame(txt, bg=C["CARD"], padx=8, pady=6)
                    self._fill_card(fr, em[tk_[1]], root_dir=tmp, readonly=True)
                    txt.window_create("end", window=fr, padx=4, pady=6)
                elif tk_[0] == "t":
                    txt.insert("end", tk_[1])
            txt.insert("end", "\n")
        txt.configure(state="disabled")

        def close():
            self._stop_play()
            shutil.rmtree(tmp, ignore_errors=True); top.destroy()

        def unseal():
            close()

            def done(r):
                if isinstance(r, Exception):
                    self.toast(f"\u26a0 {r}"); return
                self.refresh_list(); self.open_entry(eid)
                self.toast("\U0001f513 Entr\u00e9e remise en clair dans ton journal.")
            self.anim.capsule(self.root, "Descellement\u2026", lambda: unseal_entry(self.j, eid, phrase), done, unlock=True)
        row = tk.Frame(top, bg=C["BG"]); row.pack(fill="x", padx=16, pady=(0, 12))
        self.btn(row, "Fermer", close, acc=True).pack(side="right")
        self.btn(row, "\U0001f513 Desceller (remettre en clair)", unseal).pack(side="left")
        top.protocol("WM_DELETE_WINDOW", close)

    # ------------------------------------------------------------ IA locale
    def _ai_window(self, title, question=False):
        tk = self.tk
        top = tk.Toplevel(self.root); top.title(title); top.configure(bg=C["BG"]); top.transient(self.root)
        top.geometry(f"{self.px(700)}x{self.px(540)}+{self.root.winfo_rootx() + self.px(160)}+{self.root.winfo_rooty() + self.px(60)}")
        tk.Label(top, text=title, bg=C["BG"], fg=C["TEXT"], font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=16, pady=(12, 0))
        tk.Label(top, text=f"IA locale ({ollama_model()}) : rien ne quitte ton PC. Les entr\u00e9es scell\u00e9es ne sont jamais lues.",
                 bg=C["BG"], fg=C["DIM"], font=("Segoe UI", 9)).pack(anchor="w", padx=16)
        out = tk.Text(top, wrap="word", bg=C["ENTRY"], fg=C["TEXT"], relief="flat", font=("Segoe UI", 11), padx=12, pady=10)
        out.pack(fill="both", expand=True, padx=16, pady=8)
        return top, out

    def _ai_run(self, out, fn):
        out.delete("1.0", "end"); out.insert("end", "\U0001f9e0 L'officier des communications r\u00e9fl\u00e9chit\u2026 (souvent 20 \u00e0 60 s)")
        self.save_now()

        def done(r):
            model, txt = r
            out.delete("1.0", "end"); out.insert("end", txt or "(pas de r\u00e9ponse)")
        self.bg(fn, done, lambda m: (out.delete("1.0", "end"), out.insert("end", m)))

    def ai_week(self):
        top, out = self._ai_window("\U0001f9e0 R\u00e9sum\u00e9 de ma semaine")
        self._ai_run(out, lambda: weekly_summary(self.j))

    def ai_ask(self):
        tk = self.tk
        top, out = self._ai_window("\U0001f4ac Pose une question \u00e0 ton journal")
        row = tk.Frame(top, bg=C["BG"]); row.pack(fill="x", padx=16, pady=(0, 12))
        v = tk.StringVar()
        en = tk.Entry(row, textvariable=v, bg=C["ENTRY"], fg=C["TEXT"], insertbackground=C["TEXT"], relief="flat", font=("Segoe UI", 11))
        en.pack(side="left", fill="x", expand=True, ipady=4); en.focus_set()
        out.insert("end", "Exemples : \u00ab Quand suis-je all\u00e9 au chalet ? \u00bb \u00b7 \u00ab Qu'est-ce qui m'a rendu heureux ce mois-ci ? \u00bb")

        def go(_e=None):
            q = v.get().strip()
            if q:
                self._ai_run(out, lambda: ask_journal(self.j, q))
        self.btn(row, "Demander", go, acc=True).pack(side="right", padx=(6, 0))
        en.bind("<Return>", go)

    # ------------------------------------------------------------ aide

    # ------------------------------------------------------------ 1.1 : date, themes, modeles, favoris, corbeille...
    def _update_title(self):
        now = dt.datetime.now()
        try:
            self.root.title(f"\U0001f4d3 {APP} \u2014 {date_fr(now, False)} \u2014 Padawan Suite")
        except Exception:
            return
        day = now.date()
        if getattr(self, "_title_day", None) not in (None, day) and hasattr(self, "lbody"):
            self.refresh_list()                     # minuit : serie et « Ce jour-la » a jour
        self._title_day = day
        self.root.after(30000, self._update_title)

    def _theme_menu(self, parent):
        tk = self.tk
        m = tk.Menu(parent, tearoff=0)
        if not hasattr(self, "v_theme"):
            self.v_theme = tk.StringVar(value=self.st.get("theme", "cosmos"))
            self.v_stel = tk.BooleanVar(value=bool(self.st.get("date_stellaire")))
        for key, (lab, _p) in THEMES.items():
            m.add_radiobutton(label=lab, variable=self.v_theme, value=key, command=lambda k=key: self.set_theme(k))
        m.add_separator()
        m.add_checkbutton(label="Afficher la date stellaire (pour les fans de Star Trek)", variable=self.v_stel,
                          command=self._toggle_stellaire)
        m.add_cascade(label="\U0001f552 Journ\u00e9e et quart de travail", menu=self._shift_menu(m))
        return m

    def set_theme(self, key):
        if key not in THEMES:
            return
        old = dict(C)
        new = theme_colors(key)
        C.update(new)
        try:
            self._recolor(old, new)
            self._style()
            self.txt.configure(selectbackground=C["SEL"], insertbackground=C["ACC"])
            self._paint_tabs(); self._paint_moods(); self._paint_fav()
            self.refresh_list()
            self._highlight_hits()
        except Exception:
            traceback.print_exc()
        self.v_theme.set(key)
        self._set("theme", key)
        self.status(f"\U0001f3a8 Th\u00e8me : {THEMES[key][0]}", True)

    def _recolor(self, old, new):
        mp = {}
        for k, v in old.items():
            if isinstance(v, str) and v.startswith("#"):
                mp.setdefault(v.lower(), new.get(k, v))
        opts = ("bg", "fg", "activebackground", "activeforeground", "highlightbackground", "highlightcolor",
                "insertbackground", "selectbackground", "selectforeground", "selectcolor", "troughcolor")

        def walk(w):
            for o in opts:
                try:
                    v = str(w.cget(o)).lower()
                except Exception:
                    continue
                if v in mp:
                    try:
                        w.configure(**{o: mp[v]})
                    except Exception:
                        pass
            try:
                if w.winfo_class() == "Text":
                    for tg in w.tag_names():
                        for o in ("foreground", "background"):
                            v = str(w.tag_cget(tg, o) or "").lower()
                            if v in mp:
                                w.tag_configure(tg, **{o: mp[v]})
            except Exception:
                pass
            for c in w.winfo_children():
                walk(c)
        walk(self.root)

    def _toggle_stellaire(self):
        OPTS["stellaire"] = bool(self.v_stel.get())
        self._set("date_stellaire", OPTS["stellaire"])
        if self.cur:
            d = parse_iso(self.cur["created"])
            self.flavor.configure(text=random.Random(self.cur["id"]).choice(FLAVOR).format(sd=stardate(d))
                                  if OPTS["stellaire"] else "\u270e " + date_fr(d).capitalize())

    def _template_menu(self, parent):
        m = self.tk.Menu(parent, tearoff=0)
        for lab, ttl, body in TEMPLATES:
            m.add_command(label=lab, command=lambda t=ttl, b=body: self.apply_template(t, b))
        return m

    def apply_template(self, title, body):
        if not self.cur:
            self.new_entry()
        t = self.txt
        empty = not body_sans_stamps(t.get("1.0", "end-1c")).strip() and not self.card_frames
        if empty:
            if not self._val(self.title_en, self.v_title).strip():
                self.title_en._ph = False; self.title_en.configure(fg=C["TEXT"]); self.v_title.set(title)
            start = t.index("end-1c")
            self.insert_md("end-1c", body)
            t.mark_set("insert", f"{start} +1 lines linestart")
        else:
            t.mark_set("insert", "end-1c")
            self.insert_md("insert", "\n" + body)
        self._mark_dirty(); t.focus_set(); t.see("insert")
        self.status(f"\U0001f4dd Mod\u00e8le \u00ab {title} \u00bb : remplis les sections, ou efface ce qui ne sert pas.")

    def toggle_fav(self, eid=None):
        if eid is None or (self.cur and eid == self.cur.get("id")):
            if not self.cur:
                return
            self.cur["favori"] = 0 if self.cur.get("favori") else 1
            on = self.cur["favori"]
            self.dirty = True
            self.save_now(force=True)
            if not self.j.exists(self.cur["id"]):
                self.toast("\u2b50 \u00c9toile not\u00e9e : elle sera gard\u00e9e d\u00e8s que tu \u00e9cris quelques mots.")
        else:
            e = self.j.entry(eid)
            if not e:
                return
            e["favori"] = 0 if e.get("favori") else 1
            on = e["favori"]
            self.j.save_entry(e)
        self._paint_fav(); self.refresh_list()
        self.status("\u2b50 Ajout\u00e9e aux favoris" if on else "\u2606 Retir\u00e9e des favoris", True)

    def _paint_fav(self):
        try:
            on = bool(self.cur and self.cur.get("favori"))
            self.b_fav.configure(text="\u2605 Favori" if on else "\u2606 Favori", fg=C["ACC2"] if on else C["TEXT"])
        except Exception:
            pass

    def _clear_search(self):
        self.v_search.set("")
        if self.root.focus_get() is not self.search_en and hasattr(self.search_en, "_show_ph"):
            self.search_en._show_ph()
        self.txt.tag_remove("hit", "1.0", "end")

    def _highlight_hits(self):
        t = self.txt
        t.tag_remove("hit", "1.0", "end")
        q = self._val(self.search_en, self.v_search).strip()
        if not q:
            return
        words = [w for w in re.split(r"\s+", q) if len(w) > 1][:6]
        first = None
        for w in words:
            idx, n = "1.0", 0
            while n < 300:
                cnt = self.tk.IntVar()
                pos = t.search(w, idx, "end", nocase=True, count=cnt)
                if not pos or not cnt.get():
                    break
                end = f"{pos}+{cnt.get()}c"
                t.tag_add("hit", pos, end)
                if first is None or t.compare(pos, "<", first):
                    first = pos
                idx, n = end, n + 1
        if first is None:
            return
        t.tag_raise("sel")
        t.see(first)
        final = _mix(C["ENTRY"], C["ACC2"], 0.38)
        if not self.anim.on:
            t.tag_configure("hit", background=final); return
        t0 = time.time()

        def tick():
            k = min(1.0, (time.time() - t0) / 1.2)
            try:
                t.tag_configure("hit", background=_mix(C["ACC2"], final, k))
            except Exception:
                return
            if k < 1:
                t.after(40, tick)
        tick()

    def _update_wc(self):
        self._wc_job = None
        if not self.loading:
            try:
                self._scan_text_links(True)
            except Exception:
                traceback.print_exc()
        try:
            n = len(re.findall(r"\w+", self.txt.get("1.0", "end-1c")))
            mins = max(1, round(n / 200))
            self.wc_lbl.configure(text=f"\U0001f4dd {n} mot{'s' if n > 1 else ''}" + (f" \u00b7 environ {mins} min de lecture" if n >= 150 else ""))
        except Exception:
            pass

    def _streak(self):
        days = {e["created"][:10] for e in self.j.entries()}
        d = dt.date.today()
        today = d.isoformat() in days
        if not today:
            d -= dt.timedelta(days=1)
        n = 0
        while d.isoformat() in days:
            n += 1; d -= dt.timedelta(days=1)
        return n, today

    def _paint_streak(self):
        try:
            n, today = self._streak()
            if n >= 2:
                txt = f"\U0001f525 {n} jours de suite" + (" \u2014 bravo !" if today else " \u2014 \u00e9cris aujourd'hui pour continuer !")
            elif today:
                txt = "\u270d \u00c9crit aujourd'hui \u2014 reviens demain pour une s\u00e9rie !"
            else:
                txt = "\u270d Une petite entr\u00e9e aujourd'hui ?"
            self.streak_lbl.configure(text=txt)
        except Exception:
            pass

    def _pulse(self, card):
        """une nouvelle entree arrive dans la chronologie : petite lueur douce."""
        if not card or not self.anim.on:
            return
        ws = [card]
        for w in card.winfo_children():
            ws.append(w); ws += list(w.winfo_children())
        t0 = time.time()

        def tick():
            k = min(1.0, (time.time() - t0) / 0.9)
            col = _mix(C["ACC"], C["BTNH"], k)
            for w in ws:
                try:
                    w.configure(bg=col)
                except Exception:
                    pass
            if k < 1 and card.winfo_exists():
                card.after(30, tick)
        tick()

    def print_entry(self, eid=None):
        eid = eid or self._current_saved_id()
        if not eid:
            self.toast("\u00c9cris d'abord quelques mots : il n'y a rien \u00e0 imprimer."); return
        e = self.j.entry(eid)
        if not e or e.get("sealed"):
            self.toast("Les entr\u00e9es scell\u00e9es ne s'impriment pas."); return
        d = os.path.join(tempfile.gettempdir(), "padawan_journal_impression")
        os.makedirs(d, exist_ok=True)
        out = os.path.join(d, "impression.html")

        def work():
            p = export_html(self.j, [eid], out)
            with open(p, encoding="utf-8") as f:
                h = f.read()
            js = "<script>window.addEventListener('load',function(){setTimeout(function(){window.print()},500)});</script>"
            h = h.replace("</body>", js + "</body>") if "</body>" in h else h + js
            with open(p, "w", encoding="utf-8") as f:
                f.write(h)
            return p
        self.status("\U0001f5a8 Pr\u00e9paration de l'impression\u2026")
        self.bg(work, lambda p: (pc.open_path(p), self.toast("\U0001f5a8 La page s'ouvre dans ton navigateur : la fen\u00eatre d'impression appara\u00eet toute seule.", seconds=7)))

    def open_trash(self):
        tk = self.tk
        es = [e for e in self.j.entries(include_deleted=True) if e.get("deleted")]
        top = tk.Toplevel(self.root); top.title("Corbeille du journal"); top.configure(bg=C["BG"]); top.transient(self.root)
        top.geometry(f"{self.px(560)}x{self.px(460)}+{self.root.winfo_rootx() + self.px(160)}+{self.root.winfo_rooty() + self.px(80)}")
        tk.Label(top, text="\u267b Corbeille", bg=C["BG"], fg=C["TEXT"], font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=14, pady=(12, 0))
        tk.Label(top, text="Les entr\u00e9es supprim\u00e9es attendent ici : rien n'est effac\u00e9 pour de bon.\n"
                           "Choisis-en une et clique \u00ab Restaurer \u00bb (ou double-clic).",
                 bg=C["BG"], fg=C["DIM"], font=("Segoe UI", 9), justify="left").pack(anchor="w", padx=14)
        lb = tk.Listbox(top, bg=C["ENTRY"], fg=C["TEXT"], selectbackground=C["ACC"], selectforeground=C["ONACC"],
                        relief="flat", font=("Segoe UI", 11), activestyle="none")
        lb.pack(fill="both", expand=True, padx=14, pady=8)
        lb.bind("<MouseWheel>", lambda ev: lb.yview_scroll(int(-ev.delta / 120), "units"))
        for e in es:
            dd = parse_iso(e["created"])
            lb.insert("end", f"{dd.strftime('%Y-%m-%d')}  {e.get('mood') or ''}  {e.get('title') or self._auto_title(e)}")
        if not es:
            lb.insert("end", "  (La corbeille est vide.)")
        row = tk.Frame(top, bg=C["BG"]); row.pack(fill="x", padx=14, pady=(0, 12))

        def restore(_e=None):
            sel = lb.curselection()
            if not sel or not es:
                return
            e = es.pop(sel[0]); lb.delete(sel[0])
            self.j.delete_entry(e["id"], undo=True)
            self.refresh_list()
            if not e.get("sealed"):
                self.open_entry(e["id"])
            self.status("\u267b Entr\u00e9e restaur\u00e9e dans le journal.", True)
        lb.bind("<Double-Button-1>", restore)
        self.btn(row, "Fermer", top.destroy, small=True).pack(side="right", padx=3)
        self.btn(row, "\u267b Restaurer", restore, acc=True, tip="Remettre l'entr\u00e9e choisie dans le journal").pack(side="right", padx=3)


    # ------------------------------------------------------------ 1.2 : demarrage intelligent, quart, curseur vivant
    def _shift_menu(self, parent):
        tk = self.tk
        m = tk.Menu(parent, tearoff=0)
        if not hasattr(self, "v_debut"):
            self.v_debut = tk.IntVar(value=int(self.st.get("debut_journee", 5)))
            self.v_quart = tk.IntVar(value=int(self.st.get("quart_heures", 8)))
            self.v_horo = tk.BooleanVar(value=bool(self.st.get("horodatage", True)))
        m.add_command(label="\u2753 Comment \u00e7a marche ?", command=self._shift_help)
        m.add_separator()
        d = tk.Menu(m, tearoff=0)
        for hh in (0, 3, 4, 5, 6, 7, 8):
            d.add_radiobutton(label=f"\u00e0 {hh} h" + (" (minuit)" if hh == 0 else "") + (" (conseill\u00e9)" if hh == 5 else ""),
                              variable=self.v_debut, value=hh, command=lambda: self._set("debut_journee", self.v_debut.get()))
        m.add_cascade(label="Une nouvelle journ\u00e9e commence\u2026", menu=d)
        qm = tk.Menu(m, tearoff=0)
        for hh in (2, 4, 6, 8, 10, 12):
            qm.add_radiobutton(label=f"moins de {hh} heures" + (" (conseill\u00e9)" if hh == 8 else ""), variable=self.v_quart,
                               value=hh, command=lambda: self._set("quart_heures", self.v_quart.get()))
        m.add_cascade(label="Continuer mon quart si j'ai \u00e9crit il y a\u2026", menu=qm)
        m.add_checkbutton(label="Mettre l'heure au d\u00e9but de chaque nouvelle note (comme les notes au dossier)",
                          variable=self.v_horo, command=lambda: self._set("horodatage", bool(self.v_horo.get())))
        return m

    def _shift_help(self):
        from tkinter import messagebox
        messagebox.showinfo(APP, "\u00c0 l'ouverture, le journal regarde l'heure :\n\n"
                            "\u2022 Si ta derni\u00e8re entr\u00e9e est d'aujourd'hui, il la rouvre et met le curseur \u00e0 la fin, "
                            "pr\u00eat \u00e0 continuer.\n"
                            "\u2022 Si elle date d'un autre jour, il pr\u00e9pare une nouvelle entr\u00e9e (rien n'est enregistr\u00e9 "
                            "tant que tu n'\u00e9cris pas).\n\n"
                            "Travail de nuit : la journ\u00e9e commence \u00e0 5 h (r\u00e9glable). Et si tu as \u00e9crit il y a "
                            "moins de 8 heures (r\u00e9glable), on continue le m\u00eame quart, m\u00eame apr\u00e8s minuit.\n\n"
                            "Chaque fois que tu reviens, l'heure est mise au d\u00e9but de la nouvelle note "
                            "(ex. \u00ab 15 h 24 \u2014 \u00bb), comme des notes au dossier. Tu peux l'enlever dans ce menu.",
                            parent=self.root)

    def _logical_day(self, d):
        return (d - dt.timedelta(hours=int(self.st.get("debut_journee", 5)))).date()

    def _smart_start(self):
        now = dt.datetime.now()
        cands = [e for e in self.j.entries() if not e.get("sealed") and not e.get("jour")]
        last = max(cands, key=lambda e: e.get("updated") or e["created"]) if cands else None
        if last:
            upd = parse_iso(last.get("updated") or last["created"])
            created = parse_iso(last["created"])
            same_day = self._logical_day(created) == self._logical_day(now) or self._logical_day(upd) == self._logical_day(now)
            in_shift = (now - upd) < dt.timedelta(hours=int(self.st.get("quart_heures", 8)))
            if same_day or in_shift:
                self.open_entry(last["id"])
                if created.date() != now.date():
                    when = "hier" if created.date() == now.date() - dt.timedelta(days=1) else f"le {created.day} {MOIS[created.month - 1]}"
                    self._banner(f"\U0001f319 On continue ton quart commenc\u00e9 {when} \u00e0 {created.hour} h {created.minute:02d}.")
                else:
                    self._banner(f"\u270d On continue ta journ\u00e9e \u2014 derni\u00e8re \u00e9criture \u00e0 {upd.hour} h {upd.minute:02d}.")
                return
        self.new_entry()
        if last:
            ld = parse_iso(last.get("updated") or last["created"])
            self._banner(f"\u2600 Nouvelle journ\u00e9e \u2014 bonne \u00e9criture ! (derni\u00e8re entr\u00e9e : {date_fr(ld, False)})",
                         [("\u21a9 Reprendre la derni\u00e8re entr\u00e9e", lambda: self.open_entry(last["id"]))])
        else:
            self._banner("\u2600 Bienvenue ! \u00c9cris ta premi\u00e8re entr\u00e9e \u2014 tout reste sur ce PC.")

    def _continue_here(self, e, upd):
        """curseur a la fin, ligne vide + heure (notes au dossier) ; rien n'est enregistre tant qu'on n'ecrit pas."""
        t = self.txt
        body = e.get("body") or ""
        lines = [ln for ln in body.rstrip().split("\n") if ln.strip()]
        if self.st.get("horodatage", True) and not (lines and STAMP_LINE.match(lines[-1])):
            self._insert_stamp()
        else:
            self.loading = True
            try:
                if t.get("1.0", "end-1c").strip() or md_embed_ids(body):
                    tail = t.get("end-3c", "end-1c")
                    if not tail.endswith("\n\n"):
                        t.insert("end-1c", "\n" if tail.endswith("\n") else "\n\n")
                t.mark_set("insert", "end-1c")
                t.edit_reset(); t.edit_modified(False)
            finally:
                self.loading = False
                self.dirty = False
        t.see("insert")
        self._focus_editor()

    def _insert_stamp(self):
        """a l'endroit ou on ecrit : ligne vide, puis la date et l'heure, puis le curseur dessous (rien n'est enregistre
        tant qu'on n'ecrit pas ; une entree avec seulement l'heure compte comme vide)."""
        t = self.txt
        self.loading = True
        try:
            has = bool(t.get("1.0", "end-1c").strip()) or bool(self.card_frames)
            if has:
                tail = t.get("end-3c", "end-1c")
                if not tail.endswith("\n\n"):
                    t.insert("end-1c", "\n" if tail.endswith("\n") else "\n\n")
            else:
                t.delete("1.0", "end-1c")
            a = t.index("end-1c")
            t.insert("end-1c", stamp_text(), ("b",))
            t.tag_add("stamp", a, "end-1c")
            t.insert("end-1c", "\n")
            t.mark_set("insert", "end-1c")
            t.edit_reset(); t.edit_modified(False)
        finally:
            self.loading = False
            self.dirty = False
        t.see("insert")

    def _tag_stamps(self):
        t = self.txt
        t.tag_configure("stamp", foreground=C["ACC"])
        n = int(t.index("end-1c").split(".")[0])
        for ln in range(1, n + 1):
            s_ = t.get(f"{ln}.0", f"{ln}.12")
            full = t.get(f"{ln}.0", f"{ln}.end")
            if STAMP_LINE.match(full) and full.strip():
                t.tag_add("stamp", f"{ln}.0", f"{ln}.end")
                continue
            mo = re.match(r"\d{1,2} h \d{2} \u2014", s_)
            if mo:
                t.tag_add("stamp", f"{ln}.0", f"{ln}.{mo.end()}")

    def _banner(self, text, actions=(), seconds=9):
        tk = self.tk
        try:
            if getattr(self, "_bn", None) is not None and self._bn.winfo_exists():
                self._bn.destroy()
        except Exception:
            pass
        f = tk.Frame(self.right, bg=C["CARD"], highlightthickness=1, highlightbackground=C["ACC"], padx=12, pady=6)
        lab = tk.Label(f, text=text, bg=C["CARD"], fg=C["TEXT"], font=("Segoe UI", 10))
        lab.pack(side="left")
        for txt, fn in actions:
            self.btn(f, txt, lambda fn=fn: (fn(), f.destroy()), acc=True, small=True).pack(side="left", padx=(10, 0))
        x = self.btn(f, "\u2715", f.destroy, small=True, tip="Fermer")
        x.pack(side="left", padx=(8, 0))
        lab.bind("<Button-1>", lambda e: f.destroy())
        self._bn = f
        if self.anim.on:
            t0 = time.time()

            def drop():
                if not f.winfo_exists():
                    return
                k = min(1.0, (time.time() - t0) / 0.3); k = 1 - (1 - k) ** 3
                f.place(relx=0.5, y=int(-40 + 46 * k), anchor="n")
                if k < 1:
                    f.after(15, drop)
            drop()
        else:
            f.place(relx=0.5, y=6, anchor="n")
        f.after(int(seconds * 1000), lambda: f.winfo_exists() and f.destroy())

    def _focus_editor(self):
        try:
            f = self.root.focus_get()
            if f is None or f.winfo_class() not in ("Entry", "TCombobox", "Listbox"):
                self.txt.focus_force()
                self.txt.see("insert")
        except Exception:
            pass

    # ---- curseur vivant : un bloc qui respire dans la couleur du theme, et la ligne courante qui luit doucement
    def _caret_start(self):
        self._caret = {"t0": time.time(), "line": None, "key": 0.0, "on": None}
        t = self.txt
        t.tag_configure("curline", background=C["ENTRY"])
        t.tag_lower("curline")
        t.bind("<Key>", lambda e: self._caret.__setitem__("key", time.time()), add="+")
        self.root.after(60, self._caret_tick)

    def _caret_tick(self):
        t = self.txt
        st = self._caret
        try:
            on = self.anim.on
            if on != st["on"]:
                st["on"] = on
                if on:
                    t.configure(insertofftime=0, insertontime=600)
                else:
                    t.configure(insertwidth=2, insertofftime=300, insertontime=600, insertbackground=C["ACC"])
                    t.tag_remove("curline", "1.0", "end")
                    st["line"] = None
            if on:
                now = time.time()
                age = now - st["t0"]
                base = self.px(4)
                land = max(0.0, 1 - age / 0.7)                       # a l'ouverture : un gros cube qui se pose
                w = int(base + self.px(10) * land * land)
                typing = now - st["key"] < 0.6
                k = 1.0 if typing else 0.5 + 0.5 * math.sin(age * 2 * math.pi / 2.2)
                col = _mix(_mix(C["ENTRY"], C["ACC"], 0.35), C["ACC"], k)
                t.configure(insertwidth=w, insertbackground=col)
                ln = t.index("insert").split(".")[0]
                if ln != st["line"] or not t.tag_ranges("curline"):
                    t.tag_remove("curline", "1.0", "end")
                    t.tag_add("curline", f"{ln}.0", f"{ln}.0 lineend +1c")
                    st["line"] = ln
                t.tag_configure("curline", background=_mix(C["ENTRY"], C["ACC"], 0.05 + 0.04 * k))
        except Exception:
            pass
        self.root.after(70, self._caret_tick)


    # ------------------------------------------------------------ 1.4 : apercus de liens, Archiveur, « Mes liens »
    def _link_count(self, e):
        urls = set(URL_RX.findall(EMB_RX.sub(" ", e.get("body") or ""))) if not e.get("sealed") else set()
        urls |= set(getattr(self, "_emb_links", {}).get(e["id"], {}).keys())
        return len(urls)

    def _preview_block(self, fr, url, W, bgc, on_ready, archive_dir="", meta=None):
        """miniature + titre + site + description (cache local ; sinon chargement en arriere-plan)."""
        tk = self.tk
        pv = preview_cached(self.j, url)
        if pv is None or (not pv.get("ok") and time.time() - float(pv.get("t") or 0) > 3600):
            if url not in self._pv_pending():
                self._pv_pending().add(url)

                def done(_r):
                    self._pv_pending().discard(url)
                    try:
                        on_ready()
                    except Exception:
                        pass
                self.bg(lambda: fetch_preview(self.j, url), done, lambda msg: self._pv_pending().discard(url))
            tk.Label(fr, text="\u23f3 Aper\u00e7u du lien\u2026", bg=bgc, fg=C["DIM"], font=("Segoe UI", 8, "italic")).pack(anchor="w")
            return
        if not pv.get("ok") and not pv.get("image"):
            tk.Label(fr, text="Aper\u00e7u indisponible pour ce site (le lien marche quand m\u00eame).", bg=bgc, fg=C["DIM"],
                     font=("Segoe UI", 8, "italic")).pack(anchor="w")
            return
        box = tk.Frame(fr, bg=bgc, cursor="hand2"); box.pack(fill="x", pady=(0, 4))
        img = os.path.join(preview_dir(self.j), pv["image"]) if pv.get("image") else ""
        if archive_dir and meta and meta.get("capture") and os.path.isfile(os.path.join(archive_dir, meta["capture"])) and not img:
            img = os.path.join(archive_dir, meta["capture"])
        if img and os.path.isfile(img):
            try:
                from PIL import Image, ImageTk
                im = Image.open(img); im.thumbnail((self.px(200), self.px(130)))
                ph = ImageTk.PhotoImage(im); self.imgs.append(ph)
                il = tk.Label(box, image=ph, bg=bgc, cursor="hand2")
                if pv.get("video"):
                    il.configure(text=" \u25b6 ", compound="center", fg="#ffffff", font=("Segoe UI", 18, "bold"))
                il.pack(side="left", padx=(0, 10))
                il.bind("<Button-1>", lambda e: pc.open_url(url))
            except Exception:
                pass
        col = tk.Frame(box, bg=bgc); col.pack(side="left", fill="x", expand=True)
        site = pv.get("site") or ""
        tk.Label(col, text=site.upper()[:40], bg=bgc, fg=C["ACC2"], font=("Segoe UI", 8, "bold")).pack(anchor="w")
        tl = tk.Label(col, text=(pv.get("title") or url)[:140], bg=bgc, fg=C["TEXT"], font=("Segoe UI", 10, "bold"),
                      wraplength=max(200, W - self.px(240)), justify="left", cursor="hand2")
        tl.pack(anchor="w")
        tl.bind("<Button-1>", lambda e: pc.open_url(url))
        if pv.get("desc"):
            tk.Label(col, text=pv["desc"][:260] + ("\u2026" if len(pv["desc"]) > 260 else ""), bg=bgc, fg=C["DIM"],
                     font=("Segoe UI", 9), wraplength=max(200, W - self.px(240)), justify="left").pack(anchor="w")
        self._tip(tl, "Ouvrir dans le navigateur")

    def _pv_pending(self):
        if not hasattr(self, "_pvp"):
            self._pvp = set()
        return self._pvp

    def _scan_text_links(self, typing=True):
        """les liens ecrits dans le texte recoivent un apercu (non enregistre : il ne change pas l'entree)."""
        if not self.cur or not hasattr(self, "txt"):
            return
        t = self.txt
        if not hasattr(self, "tprev"):
            self.tprev = {}
        carded = {m.get("url") for m in (self.j.embeds(self.cur["id"]) if self.j.exists(self.cur["id"]) else [])}
        found = {}
        n = int(t.index("end-1c").split(".")[0])
        cur_ln, cur_col = (int(x) for x in t.index("insert").split("."))
        for ln in range(1, n + 1):
            line = t.get(f"{ln}.0", f"{ln}.end")
            if "http" not in line:
                continue
            for mo in URL_RX.finditer(line):
                u = mo.group(0)
                if u in carded or u in found:
                    continue
                if typing and ln == cur_ln and mo.start() <= cur_col <= mo.end():
                    continue                           # on est en train de l'ecrire
                found[u] = ln
        for u, fr in list(self.tprev.items()):          # lien efface : son apercu s'en va
            if u not in found:
                self._drop_preview(u)
        for u, ln in list(found.items())[:12]:
            if u in self.tprev:
                continue
            fr = self.tk.Frame(t, bg=C["CARD"], highlightthickness=1, highlightbackground=C["LINE"], padx=8, pady=6, cursor="arrow")
            self.tprev[u] = fr
            self._fill_tprev(fr, u)
            mod = t.edit_modified()
            t.window_create(f"{ln}.end", window=fr, padx=4, pady=6, align="baseline")
            if not mod:
                t.edit_modified(False)          # un apercu ne compte pas comme une modification
            if typing and self.st.get("liens_auto"):
                self.root.after(200, lambda u=u: self._promote_preview(u))

    def _fill_tprev(self, fr, u):
        tk = self.tk
        for w in fr.winfo_children():
            w.destroy()
        W = self._card_width()
        self._preview_block(fr, u, W, C["CARD"], lambda: fr.winfo_exists() and self._fill_tprev(fr, u))
        row = tk.Frame(fr, bg=C["CARD"]); row.pack(fill="x", pady=(4, 0))
        tk.Label(row, text="\U0001f517 " + u[:80], bg=C["CARD"], fg=C["DIM"], font=("Segoe UI", 8)).pack(side="left")
        self.btn(row, "\U0001f4e6 Rendre permanent", lambda: self._promote_preview(u), small=True, acc=True,
                 tip="Envoie le lien \u00e0 l'Archiveur : une copie reste sur ton PC, m\u00eame si le lien dispara\u00eet").pack(side="right")
        self.btn(row, "Ouvrir", lambda: pc.open_url(u), small=True, tip="Ouvrir dans le navigateur").pack(side="right", padx=2)

        def menu(ev):
            mm = tk.Menu(self.root, tearoff=0)
            mm.add_command(label="\U0001f4e6 Rendre permanent (Archiveur)", command=lambda: self._promote_preview(u))
            mm.add_command(label="Ouvrir dans le navigateur", command=lambda: pc.open_url(u))
            mm.add_command(label="Copier l'adresse", command=lambda: (self.root.clipboard_clear(), self.root.clipboard_append(u)))
            mm.tk_popup(ev.x_root, ev.y_root)
        for w in [fr] + list(fr.winfo_children()):
            w.bind("<Button-3>", menu, add="+")

    def _drop_preview(self, u):
        fr = self.tprev.pop(u, None)
        if fr is None:
            return None
        idx = None
        try:
            idx = self.txt.index(fr)
            self.loading = True
            mod = self.txt.edit_modified()
            self.txt.delete(idx)
            if not mod:
                self.txt.edit_modified(False)
        except Exception:
            pass
        finally:
            self.loading = False
        try:
            fr.destroy()
        except Exception:
            pass
        return idx

    def _promote_preview(self, u):
        """l'apercu devient une vraie carte lien (enregistree) et part a l'Archiveur."""
        if u not in getattr(self, "tprev", {}):
            return
        title = (preview_cached(self.j, u) or {}).get("title", "")
        was_loading, dirty0 = self.loading, self.dirty
        idx = self._drop_preview(u)
        self.dirty = True
        self._ensure_saved()
        m = self.j.add_link(self.cur, u, title)
        self._insert_card(m, idx or "end-1c")
        self._mark_dirty(); self.save_now(force=True)
        self.make_link_permanent(m["id"])

    def open_links(self):
        tk = self.tk
        self.save_now()
        rows = []
        for e in self.j.entries():
            if e.get("sealed"):
                continue
            seen = set()
            for m in self.j.embeds(e["id"]):
                if m.get("kind") == "link":
                    seen.add(m.get("url"))
                    rows.append((e, m.get("url"), m))
            for u in URL_RX.findall(EMB_RX.sub(" ", e.get("body") or "")):
                if u not in seen:
                    seen.add(u); rows.append((e, u, None))
        top = tk.Toplevel(self.root); top.title("Mes liens"); top.configure(bg=C["BG"]); top.transient(self.root)
        top.geometry(f"{self.px(760)}x{self.px(520)}+{self.root.winfo_rootx() + self.px(120)}+{self.root.winfo_rooty() + self.px(60)}")
        tk.Label(top, text="\U0001f517 Mes liens", bg=C["BG"], fg=C["TEXT"], font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=14, pady=(12, 0))
        nperm = sum(1 for r_ in rows if r_[2] and r_[2].get("status") == "permanent")
        tk.Label(top, text=f"{len(rows)} lien(s) dans ton journal \u00b7 {nperm} gard\u00e9(s) en copie permanente. "
                           "Double-clic : aller \u00e0 l'entr\u00e9e.", bg=C["BG"], fg=C["DIM"], font=("Segoe UI", 9)).pack(anchor="w", padx=14)
        lb = tk.Listbox(top, bg=C["ENTRY"], fg=C["TEXT"], selectbackground=C["ACC"], selectforeground=C["ONACC"],
                        relief="flat", font=("Segoe UI", 10), activestyle="none")
        lb.pack(fill="both", expand=True, padx=14, pady=8)
        lb.bind("<MouseWheel>", lambda ev: lb.yview_scroll(int(-ev.delta / 120), "units"))
        lab = {"permanent": "\u2714 Permanent", "copie": "\u23f3 Copie\u2026", "erreur": "\u26a0 \u00c0 r\u00e9essayer"}
        for e, u, m in rows:
            st_ = lab.get((m or {}).get("status"), "\U0001f517 Lien")
            ttl = (m or {}).get("title") or (preview_cached(self.j, u) or {}).get("title") or u
            lb.insert("end", f"{st_:<16}  {e['created'][:10]}  {ttl[:70]}")
        if not rows:
            lb.insert("end", "  Aucun lien pour l'instant : colle une adresse web dans une entr\u00e9e.")
        row = tk.Frame(top, bg=C["BG"]); row.pack(fill="x", padx=14, pady=(0, 12))

        def sel():
            s_ = lb.curselection()
            return rows[s_[0]] if s_ and rows else None

        def goto(_e=None):
            r_ = sel()
            if r_:
                self.open_entry(r_[0]["id"])

        def orig():
            r_ = sel()
            if r_:
                pc.open_url(r_[1])

        def copie():
            r_ = sel()
            if not r_ or not r_[2] or r_[2].get("status") != "permanent":
                self.toast("Ce lien n'a pas encore de copie : clique \u00ab \U0001f4e6 Rendre permanent \u00bb."); return
            mt = emeta(r_[2]); folder = self.j.abs(r_[2].get("archive"))
            for k in ("index", "main", "lecture"):
                if mt.get(k) and os.path.isfile(os.path.join(folder, mt[k])):
                    pc.open_path(os.path.join(folder, mt[k])); return
            pc.open_path(folder)

        def perm():
            r_ = sel()
            if not r_:
                return
            e, u, m = r_
            if m and m.get("status") == "permanent":
                self.toast("\u2714 Ce lien est d\u00e9j\u00e0 permanent."); return
            self.open_entry(e["id"])
            if m:
                self.make_link_permanent(m["id"])
            else:
                self.root.after(150, lambda: self._promote_preview(u))
            top.destroy()
        lb.bind("<Double-Button-1>", goto)
        self.btn(row, "Fermer", top.destroy, small=True).pack(side="right", padx=3)
        self.btn(row, "\U0001f4e6 Rendre permanent", perm, acc=True, tip="Envoyer \u00e0 l'Archiveur").pack(side="right", padx=3)
        self.btn(row, "\U0001f4f0 Ouvrir la copie", copie, tip="La copie gard\u00e9e sur ton PC").pack(side="right", padx=3)
        self.btn(row, "\U0001f310 Ouvrir l'original", orig, tip="Dans le navigateur").pack(side="right", padx=3)
        self.btn(row, "\u2197 Aller \u00e0 l'entr\u00e9e", goto, tip="Ouvrir l'entr\u00e9e (ou double-clic)").pack(side="left", padx=3)

    def help(self):
        p = os.path.join(HERE, "LISEZMOI-JOURNAL.txt")
        if os.path.isfile(p):
            pc.open_path(p)

    # ------------------------------------------------------------ instance unique (Ctrl+Alt+J / Ctrl+Alt+K)
    def _single_instance_server(self):
        self.cmd_dir = cmd_dir()

    def _poll_cmds(self):
        d = getattr(self, "cmd_dir", None)
        if not d or not os.path.isdir(d):
            return
        built = hasattr(self, "txt")
        if built and getattr(self, "_pending", None):
            pend, self._pending = self._pending, []
            for cmd in pend:
                self._run_cmd(cmd)
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".json"):
                continue
            p = os.path.join(d, fn)
            try:
                old = time.time() - os.path.getmtime(p) > 60
                cmd = pc.read_json(p, {}) or {}
                os.remove(p)
            except Exception:
                continue
            if old:
                continue
            if not built:                      # verrou ou ouverture en cours : on garde la demande pour apres
                self._pending = getattr(self, "_pending", []) + [cmd]
                lt = getattr(self, "_lock_top", None)
                try:
                    if lt is not None and lt.winfo_exists():
                        lt.deiconify(); lt.lift(); lt.focus_force()
                except Exception:
                    pass
                continue
            self._run_cmd(cmd)

    def _run_cmd(self, cmd):
        try:
            self.root.deiconify(); self.root.lift(); self.root.focus_force()
            self.root.attributes("-topmost", True); self.root.after(300, lambda: self.root.attributes("-topmost", False))
        except Exception:
            pass
        a = cmd.get("args") or []
        if "--coller" in a:
            self.paste_today()
        elif "--ouvrir" in a and a.index("--ouvrir") + 1 < len(a):
            self.open_entry(a[a.index("--ouvrir") + 1])
        elif "--nouvelle" in a:
            self.new_entry()

    def on_close(self):
        try:
            self.save_now()
        except Exception:
            pass
        self._stop_play()
        try:
            if self.full:
                self.st["fenetre"] = "plein"
            elif self.root.state() == "zoomed":
                self.st["fenetre"] = "agrandie"
            elif self.root.state() == "normal":
                self.st["fenetre"] = "normale"
                self.st["geometrie"] = self.root.geometry()
            save_settings(self.st)
        except Exception:
            pass
        self.j.close()
        release_instance()
        self.root.destroy()


# ------------------------------------------------------------------ instance unique
_MUTEX = None


def mutex_name():
    return "Local\\PadawanJournal_" + hashlib.sha1(data_root().lower().encode()).hexdigest()[:10]


def cmd_dir():
    d = os.path.join(pc.settings_dir(), "journal_cmd")
    os.makedirs(d, exist_ok=True)
    return d


def acquire_instance():
    global _MUTEX
    if not IS_WIN:
        return True
    import ctypes
    k32 = ctypes.windll.kernel32
    k32.CreateMutexW.restype = ctypes.c_void_p
    _MUTEX = k32.CreateMutexW(None, False, mutex_name())
    return k32.GetLastError() != 183


def instance_running():
    if not IS_WIN:
        return False
    import ctypes
    k32 = ctypes.windll.kernel32
    k32.OpenMutexW.restype = ctypes.c_void_p
    h = k32.OpenMutexW(0x00100000, False, mutex_name())
    if h:
        k32.CloseHandle(ctypes.c_void_p(h))
        return True
    return False


def send_to_running(args):
    p = os.path.join(cmd_dir(), f"{time.time():.6f}_{uuid.uuid4().hex[:4]}.json")
    with open(p + ".tmp", "w", encoding="utf-8") as f:
        json.dump({"args": args}, f)
    os.replace(p + ".tmp", p)
    return p


def wait_taken(p, seconds=3.0):
    """vrai si la fenetre deja ouverte a pris la commande ; sinon on la retire (rien ne trainera)."""
    t = time.time()
    while time.time() - t < seconds:
        if not os.path.exists(p):
            return True
        time.sleep(0.1)
    try:
        os.remove(p)
        return False
    except Exception:
        return True


def release_instance():
    global _MUTEX
    if IS_WIN and _MUTEX:
        import ctypes
        try:
            ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(_MUTEX))
        except Exception:
            pass
        _MUTEX = None


# ------------------------------------------------------------------ « Coller dans le journal » sans grande fenetre
def quick_paste():
    j = Journal()
    try:
        clip = clipboard_read()
        e = j.today_entry()
        md, new, what = clip_to_md(j, e, clip)
        if md:
            append_to_entry(j, e, md)
            msg = f"Coll\u00e9 dans le journal du jour : {what}"
        else:
            msg = "Le presse-papiers est vide : copie quelque chose d'abord."
    except Exception as ex:
        traceback.print_exc()
        msg = f"Collage impossible : {ex}"
    finally:
        j.close()
    if "--sans-fenetre" in sys.argv:
        print(msg); return 0
    mini_toast(msg)
    return 0


def mini_toast(msg, seconds=2.8):
    import tkinter as tk
    st = settings()
    r = tk.Tk(); r.overrideredirect(True); r.configure(bg=C["PANEL"])
    try:
        q = max(1.0, r.winfo_fpixels("1i") / 96.0)
    except Exception:
        q = 1.0
    w, h = 380, 92
    W_, H_ = int(w * q), int(h * q)
    sw, sh = r.winfo_screenwidth(), r.winfo_screenheight()
    r.geometry(f"{W_}x{H_}+{sw - W_ - int(24 * q)}+{sh - H_ - int(70 * q)}")
    try:
        r.attributes("-topmost", True); r.attributes("-alpha", 0.0)
    except Exception:
        pass
    cv = tk.Canvas(r, width=W_, height=H_, bg=C["PANEL"], highlightthickness=1, highlightbackground=C["ACC"])
    cv.pack()
    cv.create_text(84, 34, anchor="w", text="\U0001f4d3 Journal de bord", fill=C["ACC"], font=("Segoe UI", 11, "bold"))
    cv.create_text(84, 58, anchor="w", text=msg, fill=C["TEXT"], font=("Segoe UI", 9), width=int((w - 96) * q))
    cv.scale("all", 0, 0, q, q)
    t0 = time.time()
    anim = st.get("animations", True)
    r.bind("<Button-1>", lambda e: r.destroy())

    def tick():
        t = time.time() - t0
        if t > seconds:
            r.destroy(); return
        a = min(1.0, t / 0.25, max(0.0, (seconds - t) / 0.4)) if anim else 1.0
        try:
            r.attributes("-alpha", 0.96 * a)
        except Exception:
            pass
        cv.delete("chk")
        k = min(1.0, t / 0.5) if anim else 1.0
        cv.create_oval(40 - 22 * k, 46 - 22 * k, 40 + 22 * k, 46 + 22 * k, fill=C["ACC"], outline="", tags="chk")
        if k >= 1:
            cv.create_line(29, 47, 37, 55, 52, 37, fill="#06121f", width=4, capstyle="round", tags="chk")
        cv.scale("chk", 0, 0, q, q)
        r.after(30, tick)
    tick()
    r.mainloop()


# ------------------------------------------------------------------ icone
def make_icons():
    from PIL import Image, ImageDraw
    def draw(s):
        im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        k = s / 64
        d.rounded_rectangle([6 * k, 6 * k, 58 * k, 58 * k], radius=10 * k, fill=(15, 23, 36, 255), outline=(58, 209, 194, 255), width=max(1, int(3 * k)))
        d.rectangle([16 * k, 13 * k, 48 * k, 51 * k], fill=(28, 42, 72, 255))
        d.rectangle([16 * k, 13 * k, 21 * k, 51 * k], fill=(58, 209, 194, 255))
        cx, cy, r1, r2 = 35 * k, 31 * k, 10 * k, 4 * k
        pts = [(cx + math.cos(-math.pi / 2 + i * math.pi / 5) * (r1 if i % 2 == 0 else r2),
                cy + math.sin(-math.pi / 2 + i * math.pi / 5) * (r1 if i % 2 == 0 else r2)) for i in range(10)]
        d.polygon(pts, fill=(255, 204, 85, 255))
        d.line([25 * k, 45 * k, 44 * k, 45 * k], fill=(159, 176, 208, 255), width=max(1, int(2 * k)))
        return im
    big = draw(256)
    big.save(os.path.join(HERE, "journal_bord_256.png"))
    draw(64).save(os.path.join(HERE, "journal_bord.png"))
    big.save(os.path.join(HERE, "journal_bord.ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("icones OK")
    return 0


# ------------------------------------------------------------------ test sans interface
def selftest_core(url):
    """utiliser avec JOURNAL_DATA=<dossier temporaire> ; cree texte, lien permanent, image, vocal, export."""
    from PIL import Image, ImageDraw
    rep = {"ok": [], "erreurs": []}
    j = Journal()

    def ok(x):
        rep["ok"].append(x); print("OK ", x)
    try:
        e = j.save_entry(j.new_entry(title="Essai du capitaine", mood="\U0001f680", weather="\u2600", lieu="Sherbrooke",
                                     tags="essai, absinthe",
                                     body="# Rapport\nVisite **tr\u00e8s** _belle_ sur [Wikip\u00e9dia](https://fr.wikipedia.org).\n\u2022 point un\n\u2022 point\\_deux \\* \u00e9toile"))
        ok("entr\u00e9e cr\u00e9\u00e9e")
        lm = j.add_link(e, url, fetch_title(url))
        lm = make_permanent(j, lm, lambda s: print("   ", s))
        meta = emeta(lm)
        folder = j.abs(lm["archive"])
        assert lm["status"] == "permanent" and os.path.isdir(folder), "lien non permanent"
        ok(f"lien permanent : {lm['title']} -> {lm['archive']} (main={meta.get('main')}, capture={meta.get('capture')}, pdf={meta.get('pdf')}, mots={len(meta.get('texte', '').split())})")
        im = Image.new("RGB", (640, 360), (7, 11, 22)); d = ImageDraw.Draw(im)
        for _ in range(200):
            x, y = random.randint(0, 639), random.randint(0, 359); d.point((x, y), fill=(255, 255, 255))
        d.text((20, 20), "Test image journal", fill=(255, 204, 85))
        mi = j.add_image(e, im, "nebuleuse.png"); ok("image ajout\u00e9e " + mi["path"])
        tmp = os.path.join(tempfile.gettempdir(), "journal_test_memo.wav")
        with wave.open(tmp, "wb") as wf:
            wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(22050)
            wf.writeframes(b"".join(struct.pack("<h", int(9000 * math.sin(2 * math.pi * 440 * i / 22050) * (1 - i / 44100)))
                                    for i in range(44100)))
        ma = j.add_audio(e, tmp); ok(f"m\u00e9mo vocal {ma['path']} ({emeta(ma).get('duree'):.1f} s)")
        mf = j.add_file(e, os.path.abspath(__file__)); ok("fichier joint " + mf["name"])
        e["body"] += f"\n\u27e6e:{lm['id']}\u27e7\nUne image :\n\u27e6e:{mi['id']}\u27e7\nMa voix :\n\u27e6e:{ma['id']}\u27e7\n\u27e6e:{mf['id']}\u27e7"
        j.save_entry(e)
        secret = j.save_entry(j.new_entry(title="SECRET-NE-PAS-FUIR", body="mot-de-code-xyzzy"))
        other = j.save_entry(j.new_entry(title="AUTRE-ENTREE-PRIVEE", body="ne doit pas apparaitre"))
        out = os.path.join(j.root, "_test_export.html")
        export_html(j, [e["id"]], out)
        h = open(out, encoding="utf-8").read()
        assert "data:image/" in h and "data:audio/wav" in h and "Essai du capitaine" in h
        assert "AUTRE-ENTREE-PRIVEE" not in h and "SECRET-NE-PAS-FUIR" not in h
        assert not re.search(r'(src|href)="(?!data:|https?:|#)', h), "r\u00e9f\u00e9rence externe locale"
        ok(f"export HTML autonome {human(os.path.getsize(out))} (images+audio int\u00e9gr\u00e9s, aucune autre entr\u00e9e)")
        rep["export"] = out
        seg = f"Une image :\n\u27e6e:{mi['id']}\u27e7"
        so = os.path.join(j.root, "_test_extrait.html")
        export_segment_html(j, e, seg, so)
        hs = open(so, encoding="utf-8").read()
        assert "data:image/" in hs and "data:audio" not in hs and "Rapport" not in hs and "wikipedia" not in hs.lower()
        ok("extrait (passage) : seulement l'image choisie")
        rep["extrait"] = so
        zo = os.path.join(j.root, "_test_export.zip")
        export_zip(j, [e["id"]], zo)
        names = zipfile.ZipFile(zo).namelist()
        assert "index.html" in names and any(n.endswith(".wav") for n in names)
        ok(f"export .zip ({len(names)} fichiers)")
        pdf = os.path.join(j.root, "_test_export.pdf")
        try:
            export_pdf(j, [e["id"]], pdf); ok(f"export PDF {human(os.path.getsize(pdf))}")
        except Exception as ex:
            rep["erreurs"].append(f"PDF : {ex}")
        pl = entry_plain(e, j.embeds(e["id"]))
        assert "Essai du capitaine" in pl and "[Image : nebuleuse.png]" in pl and "point_deux * \u00e9toile" in pl, pl
        ok("texte \u00e0 partager")
        assert search(j, "absinthe") and search(j, "nebuleuse") and not search(j, "xyzzy-introuvable")
        ok("recherche (titre, \u00e9tiquettes, pi\u00e8ces)")
        seal_entry(j, secret["id"], "phrase-test-123", "test")
        assert not search(j, "xyzzy") and j.entry(secret["id"])["sealed"] == 1
        raw = open(os.path.join(j.root, "journal.db"), "rb").read()
        try:
            unseal_bytes("mauvaise", open(os.path.join(j.root, "scelles", secret["id"] + ".scelle"), "rb").read())
            rep["erreurs"].append("mauvaise phrase accept\u00e9e !")
        except ValueError:
            pass
        e2, _em, tmpd = open_sealed(j, secret["id"], "phrase-test-123"); shutil.rmtree(tmpd, ignore_errors=True)
        assert e2["body"] == "mot-de-code-xyzzy"
        try:
            export_html(j, [secret["id"]], os.path.join(j.root, "_x.html")); rep["erreurs"].append("scell\u00e9e export\u00e9e !")
        except ValueError:
            pass
        unseal_entry(j, secret["id"], "phrase-test-123")
        assert j.entry(secret["id"])["body"] == "mot-de-code-xyzzy"
        ok("entr\u00e9e scell\u00e9e : chiffr\u00e9e, absente de la recherche et des partages, rouverte et descell\u00e9e")
        md, imgs = html_to_md('<p>Salut <b>gras</b> et <i>ital</i> <a href="https://ex.com">lien</a></p><ul><li>un</li></ul><img src="data:image/png;base64,iVBORw0KGgo=">')
        assert "**gras**" in md and "_ital_" in md and "[lien](https://ex.com)" in md and "\u2022 un" in md and imgs, md
        ok("collage HTML -> texte enrichi")
        rt = md_lines("**a** _b_ [c](https://x.y) \\_d\\*")
        assert [t[1] for t in rt[0][1] if t[0] == "t"] == ["a", " ", "b", " ", "c", " ", "_", "d", "*"], rt
        ok("mini-markdown (aller-retour)")
    except Exception:
        rep["erreurs"].append(traceback.format_exc())
    finally:
        j.close()
    print("SELFTEST", "OK" if not rep["erreurs"] else "ERREURS")
    for x in rep["erreurs"]:
        print("ERREUR:", x)
    return 0 if not rep["erreurs"] else 1


def bulk_test(n=1000):
    """perf : n entrees de test (dossier temporaire !) puis recherche chronometree."""
    j = Journal()
    words = "nebuleuse vaisseau chalet lac montagne absinthe recette jardin velo etoile soleil pluie ami famille".split()
    t0 = time.time()
    base = dt.datetime.now() - dt.timedelta(days=n)
    with j.lock:
        for i in range(n):
            d = base + dt.timedelta(days=i, hours=random.randint(0, 20))
            e = j.new_entry(created=d.strftime("%Y-%m-%dT%H:%M:%S"), title=f"Entr\u00e9e {i} " + random.choice(words),
                            body=" ".join(random.choice(words) for _ in range(150)), tags=random.choice(words),
                            mood=random.choice(MOODS)[0])
            cols = list(e.keys())
            j.db.execute(f"INSERT INTO entries({','.join(cols)}) VALUES({','.join('?' * len(cols))})", [e[c] for c in cols])
        j.db.commit()
    t1 = time.time()
    r = search(j, "chalet absinthe")
    t2 = time.time()
    r2 = search(j, "vaisseau")
    t3 = time.time()
    t4 = time.time(); es = j.entries(); t5 = time.time()
    print(f"{n} entr\u00e9es cr\u00e9\u00e9es en {t1 - t0:.2f} s ; recherche (1re fois) : {len(r)} r\u00e9sultats en {(t2 - t1) * 1000:.0f} ms ;"
          f" recherche suivante : {len(r2)} en {(t3 - t2) * 1000:.0f} ms ; liste : {len(es)} en {(t5 - t4) * 1000:.0f} ms")
    j.close()
    return 0


def gui_selftest(app):
    """exerce l'editeur : texte, gras, lien, collage, copie de passage, sauvegarde, vues, recherche."""
    errs = []
    saved_clip = clipboard_read().get("text", "")

    def chk(cond, what):
        print(("OK  " if cond else "ECHEC ") + what)
        if not cond:
            errs.append(what)
    try:
        app.new_entry()
        t = app.txt
        line = "Bonjour capitaine. Texte gras ici et italique la."
        t.insert("1.0", line + "\nDeuxieme ligne")
        g, it = line.index("gras"), line.index("italique")
        t.tag_add("b", f"1.{g}", f"1.{g + 4}"); t.tag_add("i", f"1.{it}", f"1.{it + 8}"); t.tag_add("b", f"1.{it}", f"1.{it + 3}")
        app._refresh_bi()
        t.tag_add("h1", "2.0", "2.end+1c")
        md = app.serialize()
        chk("**gras**" in md and "**_ita_**_lique_" in md and "# Deuxieme" in md, "serialisation " + md.replace(chr(10), " / "))
        chk([x[1] for x in md_lines(md)[0][1] if x[0] == "t"][3:6] == ["ita", "lique", " la."], "relecture gras+italique")
        app.v_title.set("Test interface"); app._mark_dirty(); app.save_now(force=True)
        chk(app.j.exists(app.cur["id"]), "autosave entree")
        chk(app.j.entry(app.cur["id"])["title"] == "Test interface", "titre enregistre (champ avec texte d'aide)")
        app.root.clipboard_clear(); app.root.clipboard_append("https://example.com/")
        clipboard_write("https://example.com/")
        t.mark_set("insert", "end-1c")
        app.smart_paste()
        app.root.update()
        ems = app.j.embeds(app.cur["id"])
        chk(any(m["kind"] == "link" for m in ems), "Ctrl+V d'une adresse -> carte lien")
        clipboard_write("Ligne collee avec https://padawan.example/x dedans")
        t.mark_set("insert", "end-1c"); app.smart_paste(); app.root.update()
        app.save_now(force=True)
        body = app.j.entry(app.cur["id"])["body"]
        chk("[https://padawan.example/x](https://padawan.example/x)" in body, "Ctrl+V texte -> lien cliquable")
        t.tag_add("sel", "1.0", "1.18")
        app.copy_passage("riche")
        got = clipboard_read()
        chk(got["text"].startswith("Bonjour capitaine") and "Deuxieme" not in got["text"], "Copier ce passage (texte) : " + got["text"][:40])
        chk((not IS_WIN) or "Bonjour" in got["html"], "Copier ce passage (HTML)")
        app._sel_bar(); app.root.update()
        chk(bool(app.selbar.winfo_ismapped()), "barre de passage visible")
        t.tag_remove("sel", "1.0", "end")
        md2 = app.serialize()
        app._load_into_editor(app.j.entry(app.cur["id"])); app.root.update()
        chk(app.serialize().count("\u27e6e:") == md2.count("\u27e6e:"), "rechargement : pieces conservees")
        app.consign(); app.root.update()
        for v in ("cal", "jour", "chrono"):
            app.set_view(v); app.root.update()
        chk(True, "vues chronologie / calendrier / ce jour-la")
        app.search_en.event_generate("<FocusIn>"); app.v_search.set("capitaine"); app.refresh_list(); app.root.update()
        chk(len(app.list_cards) >= 1, f"recherche ({len(app.list_cards)} resultat(s))")
        app.v_search.set(""); app.search_en.event_generate("<FocusOut>")
        app.set_fullscreen(True); app.root.update(); time.sleep(0.3); app.root.update()
        fs_on = bool(int(app.root.attributes("-fullscreen")))
        app.root.update(); pad = int(float(str(app.txt.cget("padx"))))
        print(f"    plein ecran : {app.root.winfo_width()}x{app.root.winfo_height()}, marge de colonne {pad}px, carte {app._card_width()}px")
        app._esc(); app.root.update()
        chk(fs_on and not bool(int(app.root.attributes("-fullscreen"))), "F11 plein ecran puis Echap")
    except Exception:
        errs.append(traceback.format_exc()); print(traceback.format_exc())
    try:
        clipboard_write(saved_clip or "")
    except Exception:
        pass
    print("GUI SELFTEST", "OK" if not errs else f"ERREURS ({len(errs)})")


def dpi_aware():
    """texte net sur les ecrans Windows a 125/150 % (sinon Windows etire la fenetre et c'est flou)."""
    if not IS_WIN or os.environ.get("JOURNAL_SANS_DPI"):
        return
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def main():
    a = sys.argv[1:]
    dpi_aware()
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if "--make-icons" in a:
        return make_icons()
    if "--selftest-core" in a:
        i = a.index("--selftest-core")
        return selftest_core(a[i + 1] if i + 1 < len(a) else "https://fr.wikipedia.org/wiki/Absinthe")
    if "--bulk" in a:
        return bulk_test(int(a[a.index("--bulk") + 1]) if a.index("--bulk") + 1 < len(a) else 1000)
    test = "--selftest" in a or "--screenshot" in a or "--capture-intro" in a
    if "--coller" in a:
        if instance_running() and wait_taken(send_to_running(a)):
            return 0
        return quick_paste()
    if not acquire_instance() and not test:
        if wait_taken(send_to_running(a or ["--nouvelle"]), 5.0):
            return 0
        release_instance()        # l'autre fenetre ne repond pas (fermeture en cours ?) : on ouvre quand meme
    app = JournalApp(a)
    if "--capture-intro" in a:            # test : capture du saut en distorsion + mesure du processeur
        out = a[a.index("--capture-intro") + 1]
        c0, w0 = time.process_time(), time.time()
        mes = {}

        def grab():
            from PIL import ImageGrab
            ImageGrab.grab().save(out); print("capture", out)

        def cpu(tag, c, w):
            print(f"processeur {tag} : {100 * (time.process_time() - c) / max(0.01, time.time() - w):.1f} % d'un coeur")

        def idle_start():
            mes["c"], mes["w"] = time.process_time(), time.time()
        if out != "-":
            app.root.after(1700, grab)
        app.root.after(2600, lambda: cpu("pendant l'ouverture animee (avec la capture)", c0, w0))
        app.root.after(6000, idle_start)
        app.root.after(16000, lambda: (cpu("au repos (10 s)", mes["c"], mes["w"]), app.on_close()))
    if test and "--capture-intro" not in a:
        def shot():
            try:
                app.root.update()
                if "--screenshot" in a:
                    out = a[a.index("--screenshot") + 1]
                    from PIL import ImageGrab
                    r = app.root
                    r.attributes("-topmost", True); r.update(); time.sleep(0.4); r.update()
                    x, y = r.winfo_rootx(), r.winfo_rooty()
                    full = ImageGrab.grab()
                    k = full.width / float(r.winfo_screenwidth() or full.width)
                    x2, y2 = x + r.winfo_width(), y + r.winfo_height()
                    full.crop((int(x * k), int((y - 30) * k), int(x2 * k), int(y2 * k))).save(out)
                    print("capture", out)
            finally:
                app.on_close()
        if "--vue" in a:
            app.root.after(1500, lambda: app.set_view(a[a.index("--vue") + 1]))
        if "--cherche" in a:
            app.root.after(1600, lambda: (app.search_en.event_generate("<FocusIn>"), app.v_search.set(a[a.index("--cherche") + 1])))
        if "--selftest" in a:
            app.root.after(1200, lambda: gui_selftest(app))
        delay = 4000
        if "--attente" in a:
            delay = int(a[a.index("--attente") + 1])
        app.root.after(delay, shot)
    app.root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
