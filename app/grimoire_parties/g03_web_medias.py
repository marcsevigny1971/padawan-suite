# -*- coding: utf-8 -*-
# Partie de grimoire1.py (découpage v1.2.2, comportement inchangé).
# Chargée par grimoire1.py dans un espace de noms commun : ne pas lancer seule.
from __future__ import annotations



# ================================================================ web : titre, description, miniature
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/128.0 Safari/537.36 Edg/128.0")


def http_get(url: str, timeout: float = 12, maxbytes: int = 4_000_000) -> Tuple[bytes, str, str]:
    url = fix_url(url)
    hdr = {"User-Agent": UA, "Accept-Language": "fr-CA,fr;q=0.9,en;q=0.7",
           "Accept": "text/html,application/xhtml+xml,application/json,image/*;q=0.9,*/*;q=0.8"}
    try:
        import requests  # type: ignore
        r = requests.get(url, headers=hdr, timeout=timeout, stream=True, allow_redirects=True)
        chunks, n = [], 0
        for ch in r.iter_content(65536):
            chunks.append(ch)
            n += len(ch)
            if n >= maxbytes:
                break
        r.close()
        if r.status_code >= 400:
            raise IOError(f"HTTP {r.status_code}")
        return b"".join(chunks), r.url, r.headers.get("Content-Type", "")
    except ImportError:
        req = urllib.request.Request(url, headers=hdr)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read(maxbytes), resp.geturl(), resp.headers.get("Content-Type", "")


def decode_html(b: bytes, ctype: str = "") -> str:
    enc = ""
    m = re.search(r"charset=([\w-]+)", ctype or "", re.I)
    if m:
        enc = m.group(1)
    else:
        m = re.search(rb"<meta[^>]+charset=[\"']?([\w-]+)", b[:4000], re.I)
        if m:
            enc = m.group(1).decode("ascii", "ignore")
    for e in (enc, "utf-8", "cp1252", "latin-1"):
        if not e:
            continue
        try:
            return b.decode(e)
        except (LookupError, UnicodeDecodeError):
            continue
    return b.decode("utf-8", "replace")


class _MetaParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta: Dict[str, str] = {}
        self.title = ""
        self._in_title = False
        self.icon = ""

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            k = (a.get("property") or a.get("name") or a.get("itemprop") or "").lower()
            if k and a.get("content") and k not in self.meta:
                self.meta[k] = a["content"].strip()
        elif tag == "link" and "icon" in a.get("rel", "").lower() and not self.icon:
            self.icon = a.get("href", "")
        elif tag == "link" and a.get("rel", "").lower() == "canonical":
            self.meta.setdefault("canonical", a.get("href", ""))

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title and len(self.title) < 400:
            self.title += data


def _json_get(url: str, timeout: float = 10) -> Dict[str, Any]:
    b, _u, _c = http_get(url, timeout)
    return json.loads(b.decode("utf-8", "replace"))


def fetch_link_info(url: str) -> Dict[str, str]:
    """Titre, description, image, site, auteur, date de publication d'un lien (meilleur effort)."""
    url = fix_url(url)
    info: Dict[str, str] = {"title": "", "description": "", "image": "", "site": domain_of(url), "author": "",
                            "published": "", "html_text": ""}
    lu = url.lower()
    try:
        yid = youtube_id(url)
        if yid:
            try:
                j = _json_get("https://www.youtube.com/oembed?format=json&url=" + urllib.parse.quote(url, safe=""))
                info.update(title=j.get("title", ""), author=j.get("author_name", ""), site="YouTube")
            except Exception:
                pass
            info["image"] = f"https://i.ytimg.com/vi/{yid}/hqdefault.jpg"
        m = re.search(r"(?:x|twitter)\.com/([^/]+)/status/(\d+)", lu)
        if m:
            try:
                j = _json_get(f"https://api.fxtwitter.com/{m.group(1)}/status/{m.group(2)}")
                t = j.get("tweet") or {}
                au = t.get("author") or {}
                info.update(title=f"{au.get('name', '')} (@{au.get('screen_name', '')}) sur X", site="X",
                            description=t.get("text", ""), author=au.get("name", ""),
                            published=str(t.get("created_at", ""))[:40])
                media = (t.get("media") or {})
                pics = media.get("photos") or []
                vids = media.get("videos") or []
                if vids:
                    info["image"] = vids[0].get("thumbnail_url", "")
                elif pics:
                    info["image"] = pics[0].get("url", "")
            except Exception:
                try:
                    j = _json_get("https://publish.twitter.com/oembed?omit_script=1&url=" + urllib.parse.quote(url, safe=""))
                    txt = re.sub(r"<[^>]+>", " ", j.get("html", ""))
                    info.update(title=f"{j.get('author_name', '')} sur X", author=j.get("author_name", ""), site="X",
                                description=html.unescape(re.sub(r"\s+", " ", txt)).strip())
                except Exception:
                    pass
        for host, api in (("tiktok.com", "https://www.tiktok.com/oembed?url="),
                          ("vimeo.com", "https://vimeo.com/api/oembed.json?url=")):
            if host in lu and not info["title"]:
                try:
                    j = _json_get(api + urllib.parse.quote(url, safe=""))
                    info.update(title=j.get("title", ""), author=j.get("author_name", ""),
                                image=j.get("thumbnail_url", ""), site=j.get("provider_name", host))
                except Exception:
                    pass
        if not info["title"] or not info["image"] or not info["description"]:
            b, final, ctype = http_get(url, 12, 1_500_000)
            if "image/" in (ctype or ""):
                info["image"] = info["image"] or final
                info["title"] = info["title"] or os.path.basename(urllib.parse.urlparse(final).path)
                return info
            text = decode_html(b, ctype)
            p = _MetaParser()
            try:
                p.feed(text[:600_000])
            except Exception:
                pass
            mt = p.meta
            info["title"] = info["title"] or mt.get("og:title") or mt.get("twitter:title") or html.unescape(p.title.strip())
            info["description"] = info["description"] or mt.get("og:description") or mt.get("description") or \
                mt.get("twitter:description", "")
            img = info["image"] or mt.get("og:image") or mt.get("og:image:url") or mt.get("twitter:image") or \
                mt.get("twitter:image:src", "")
            if img:
                info["image"] = urllib.parse.urljoin(final, img)
            info["site"] = mt.get("og:site_name") or info["site"]
            info["author"] = info["author"] or mt.get("author") or mt.get("article:author", "")
            info["published"] = info["published"] or mt.get("article:published_time") or mt.get("date", "")
    except Exception as ex:
        info["error"] = str(ex)[:200]
    for k in ("title", "description", "author"):
        info[k] = re.sub(r"\s+", " ", html.unescape(info.get(k) or "")).strip()[:2000]
    return info


def save_thumb_bytes(data: bytes, dest: str, size: Tuple[int, int] = (480, 320)) -> bool:
    try:
        from PIL import Image  # type: ignore
        im = Image.open(io.BytesIO(data))
        im.load()
        return save_thumb_image(im, dest, size)
    except Exception as ex:
        logger.info("vignette : %s", ex)
        return False


def save_thumb_image(im: Any, dest: str, size: Tuple[int, int] = (480, 320)) -> bool:
    try:
        from PIL import Image, ImageOps  # type: ignore
        try:
            im = ImageOps.exif_transpose(im)
        except Exception:
            pass
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGBA" if "A" in im.mode or im.mode == "P" else "RGB")
        im.thumbnail(size, Image.Resampling.LANCZOS)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        im.save(dest, "PNG")
        return True
    except Exception as ex:
        logger.info("vignette : %s", ex)
        return False


def thumb_path(store: Store, sid: int, iid: int) -> str:
    d = os.path.join(store.subject_media_dir(sid), "_vignettes")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"v{iid}.png")


def thumb_from_file(path: str, dest: str) -> bool:
    ext = os.path.splitext(path)[1].lower()
    if ext in IMG_EXT:
        try:
            from PIL import Image  # type: ignore
            with Image.open(path) as im:
                im.load()
                return save_thumb_image(im.copy(), dest)
        except Exception as ex:
            logger.info("vignette image %s : %s", path, ex)
            return False
    if ext in VIDEO_EXT:
        ff = find_ffmpeg()
        if not ff:
            return False
        tmp = dest + ".tmp.png"
        for ss in ("3", "0"):
            try:
                run_hidden([ff, "-y", "-ss", ss, "-i", path, "-frames:v", "1", "-vf", "scale=480:-2", tmp], 40)
                if os.path.isfile(tmp) and os.path.getsize(tmp) > 0:
                    with open(tmp, "rb") as f:
                        ok = save_thumb_bytes(f.read(), dest)
                    os.remove(tmp)
                    return ok
            except Exception:
                pass
    return False


# ================================================================ extraction de texte
class _TextHTML(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "head", "nav", "footer", "form", "button", "iframe"}
    BLOCK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section", "article", "blockquote", "pre"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: List[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


def html_to_text(s: str) -> str:
    try:
        from bs4 import BeautifulSoup  # type: ignore
        soup = BeautifulSoup(s, "html.parser")
        for t in soup(["script", "style", "noscript", "svg", "nav", "footer", "form", "iframe", "header", "aside"]):
            t.decompose()
        root = soup.find("article") or soup.find("main") or soup.body or soup
        txt = root.get_text("\n")
    except Exception:
        p = _TextHTML()
        try:
            p.feed(s)
        except Exception:
            pass
        txt = "".join(p.out)
    lines = [re.sub(r"[ \t\xa0]+", " ", ln).strip() for ln in txt.splitlines()]
    out, blank = [], 0
    for ln in lines:
        if not ln:
            blank += 1
            if blank == 1:
                out.append("")
            continue
        blank = 0
        out.append(ln)
    return "\n".join(out).strip()


def _xml_text(data: bytes, para_tags: Tuple[str, ...] = ("</w:p>", "</text:p>", "</a:p>", "</p>", "</si>")) -> str:
    s = data.decode("utf-8", "ignore")
    for t in para_tags:
        s = s.replace(t, t + "\n")
    s = re.sub(r"<w:tab/>", "\t", s)
    s = re.sub(r"<[^>]+>", "", s)
    return html.unescape(s)


MAX_EXTRACT = 1_500_000


def extract_text(path: str) -> Tuple[str, Dict[str, Any]]:
    """Texte d'un document (pour la recherche) + infos (pages...)."""
    ext = os.path.splitext(path)[1].lower()
    info: Dict[str, Any] = {}
    txt = ""
    try:
        if ext == ".pdf":
            try:
                from pypdf import PdfReader  # type: ignore
            except ImportError:
                info["note"] = "pypdf absent : texte du PDF non extrait (pip install pypdf)"
                return "", info
            r = PdfReader(path)
            info["pages"] = len(r.pages)
            parts = []
            total = 0
            for i, pg in enumerate(r.pages):
                if i >= 400 or total > MAX_EXTRACT:
                    break
                try:
                    t = pg.extract_text() or ""
                except Exception:
                    t = ""
                parts.append(t)
                total += len(t)
            txt = "\n\n".join(parts)
            try:
                md = r.metadata
                if md and md.title:
                    info["doc_title"] = str(md.title)
                if md and md.author:
                    info["doc_author"] = str(md.author)
            except Exception:
                pass
        elif ext in (".docx", ".pptx", ".xlsx", ".odt", ".odp", ".ods", ".epub"):
            with zipfile.ZipFile(path) as z:
                names = z.namelist()
                if ext == ".docx":
                    txt = _xml_text(z.read("word/document.xml"))
                elif ext == ".pptx":
                    slides = sorted([n for n in names if re.match(r"ppt/slides/slide\d+\.xml$", n)],
                                    key=lambda n: int(re.findall(r"\d+", n)[-1]))
                    info["pages"] = len(slides)
                    txt = "\n\n".join(_xml_text(z.read(n)) for n in slides)
                elif ext == ".xlsx":
                    txt = _xml_text(z.read("xl/sharedStrings.xml")) if "xl/sharedStrings.xml" in names else ""
                elif ext in (".odt", ".odp", ".ods"):
                    txt = _xml_text(z.read("content.xml"))
                elif ext == ".epub":
                    parts = [n for n in names if n.lower().endswith((".xhtml", ".html", ".htm"))]
                    txt = "\n\n".join(html_to_text(z.read(n).decode("utf-8", "ignore")) for n in sorted(parts)[:400])
        elif ext in (".html", ".htm"):
            with open(path, "rb") as f:
                txt = html_to_text(decode_html(f.read(MAX_EXTRACT * 2)))
        elif ext == ".rtf":
            with open(path, "rb") as f:
                s = f.read(MAX_EXTRACT).decode("latin-1", "ignore")
            s = re.sub(r"\\'([0-9a-f]{2})", lambda m: bytes([int(m.group(1), 16)]).decode("cp1252", "ignore"), s)
            s = re.sub(r"\\par[d]?", "\n", s)
            s = re.sub(r"\{\\\*[^{}]*\}|\\[a-z]+-?\d* ?|[{}]", "", s)
            txt = s
        elif ext in TEXT_EXT or ext == "":
            with open(path, "rb") as f:
                b = f.read(MAX_EXTRACT)
            txt = decode_html(b)
    except Exception as ex:
        info["note"] = f"texte non extrait : {ex}"[:200]
    txt = re.sub(r"[ \t]+\n", "\n", txt or "")
    txt = re.sub(r"\n{3,}", "\n\n", txt).strip()
    return txt[:MAX_EXTRACT], info


# ================================================================ OCR (Windows integre, optionnel)
OCR_PS = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$path = $args[0]
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($WinRtTask, $ResultType) {
  $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
  $netTask = $asTask.Invoke($null, @($WinRtTask))
  $netTask.Wait(-1) | Out-Null
  $netTask.Result
}
$engine = $null
try { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new('fr')) } catch {}
if ($engine -eq $null) { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages() }
if ($engine -eq $null) { Write-Output '##NOENGINE##'; exit 3 }
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($path)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
foreach ($l in $result.Lines) { Write-Output $l.Text }
"""


def ocr_available() -> str:
    if IS_WIN:
        return "windows"
    if shutil.which("tesseract") and module_ok("pytesseract"):
        return "tesseract"
    return ""


def ocr_image(path: str) -> Tuple[str, str]:
    """(texte, erreur) - OCR Windows (Windows.Media.Ocr) sinon Tesseract si installe."""
    if not os.path.isfile(path):
        return "", "fichier introuvable"
    src = path
    tmp_png = ""
    try:
        from PIL import Image  # type: ignore
        with Image.open(path) as im:
            w, h = im.size
            if os.path.splitext(path)[1].lower() not in (".png", ".jpg", ".jpeg", ".bmp") or max(w, h) > 9000 or min(w, h) < 40:
                im2 = im.convert("RGB")
                if max(w, h) > 9000:
                    im2.thumbnail((9000, 9000))
                if min(w, h) < 40:
                    im2 = im2.resize((w * 3, h * 3))
                fd, tmp_png = tempfile.mkstemp(suffix=".png", prefix="grim_ocr_")
                os.close(fd)
                im2.save(tmp_png)
                src = tmp_png
    except Exception:
        pass
    try:
        if IS_WIN:
            fd, ps = tempfile.mkstemp(suffix=".ps1", prefix="grim_ocr_")
            with os.fdopen(fd, "w", encoding="utf-8-sig") as f:
                f.write(OCR_PS)
            try:
                r = run_hidden(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                                "-File", ps, os.path.abspath(src)], 90)
            finally:
                try:
                    os.remove(ps)
                except OSError:
                    pass
            out = r.stdout.decode("utf-8", "replace").strip()
            if "##NOENGINE##" in out:
                return "", "aucune langue OCR installée dans Windows (Paramètres → Langue → Français : reconnaissance optique)"
            if r.returncode != 0 and not out:
                return "", (r.stderr.decode("utf-8", "replace").strip().splitlines() or ["échec de l'OCR Windows"])[-1][:300]
            return out.replace("\r\n", "\n").replace("\r", "\n"), ""
        if shutil.which("tesseract") and module_ok("pytesseract"):
            import pytesseract  # type: ignore
            from PIL import Image  # type: ignore
            return pytesseract.image_to_string(Image.open(src), lang="fra+eng").strip(), ""
        return "", "OCR indisponible sur ce système"
    except Exception as ex:
        return "", str(ex)[:300]
    finally:
        if tmp_png:
            try:
                os.remove(tmp_png)
            except OSError:
                pass


# ================================================================ transcription (faster-whisper, optionnel)
WHISPER_HELP = ("La transcription des mémos vocaux se fait 100 % sur ce PC avec le module optionnel faster-whisper "
                "(environ 300 Mo + le modèle, téléchargé une seule fois).\n\nPour l'installer : menu Outils → "
                "« Installer la transcription (faster-whisper) », ou relancer setup_padawan.bat et répondre O.\n\n"
                "En attendant, tu peux écrire un résumé dans l'onglet Notes du mémo : il sera cherchable.")
_WHISPER_MODEL: Dict[str, Any] = {}


def whisper_available() -> bool:
    try:
        import importlib.util
        return importlib.util.find_spec("faster_whisper") is not None
    except Exception:
        return False


def transcribe(path: str, model_size: str = "small", progress: Optional[Callable[[str], None]] = None) -> Tuple[str, str]:
    """(texte horodate, erreur)."""
    if not whisper_available():
        return "", "faster-whisper n'est pas installé"
    try:
        from faster_whisper import WhisperModel  # type: ignore
        if model_size not in _WHISPER_MODEL:
            if progress:
                progress(f"Chargement du modèle Whisper « {model_size} » (la première fois, téléchargement)…")
            _WHISPER_MODEL[model_size] = WhisperModel(model_size, device="cpu", compute_type="int8")
        model = _WHISPER_MODEL[model_size]
        segs, info = model.transcribe(path, language="fr", vad_filter=True, beam_size=5)
        lines = []
        for s in segs:
            lines.append(f"[{fmt_dur(s.start)}] {s.text.strip()}")
            if progress and len(lines) % 5 == 0:
                progress(f"Transcription… {fmt_dur(s.end)}")
        return "\n".join(lines), ""
    except Exception as ex:
        logger.error("transcription : %s", traceback.format_exc())
        return "", str(ex)[:300]


# ================================================================ capture complete d'une page web
def capture_page(url: str, dest_dir: str, base: str, progress: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
    """HTML hors ligne (base href) + texte lisible + PDF et image pleine page (Edge/Chrome sans fenetre)."""
    url = fix_url(url)
    os.makedirs(dest_dir, exist_ok=True)
    res: Dict[str, Any] = {"files": [], "title": "", "text": "", "errors": []}
    base = safe_name(base or domain_of(url) or "page", 60)
    try:
        if progress:
            progress("Téléchargement de la page…")
        b, final, ctype = http_get(url, 25, 15_000_000)
        s = decode_html(b, ctype)
        p = _MetaParser()
        try:
            p.feed(s[:600_000])
        except Exception:
            pass
        res["title"] = (p.meta.get("og:title") or html.unescape(p.title)).strip()
        res["description"] = p.meta.get("og:description") or p.meta.get("description", "")
        res["image"] = urllib.parse.urljoin(final, p.meta.get("og:image", "")) if p.meta.get("og:image") else ""
        s2 = re.sub(r"<meta[^>]+charset[^>]*>", "", s, flags=re.I)
        tag = f'<meta charset="utf-8"><base href="{html.escape(final, quote=True)}">'
        if re.search(r"<head[^>]*>", s2, re.I):
            s2 = re.sub(r"(<head[^>]*>)", lambda m: m.group(1) + tag, s2, count=1, flags=re.I)
        else:
            s2 = tag + s2
        hp = os.path.join(dest_dir, base + ".html")
        hp = unique_path(dest_dir, os.path.basename(hp))
        with open(hp, "w", encoding="utf-8") as f:
            f.write(f"<!-- Capturé par Grimoire le {now_iso()} depuis {html.escape(final)} -->\n" + s2)
        res["html"] = hp
        res["files"].append(hp)
        res["text"] = html_to_text(s)[:MAX_EXTRACT]
        res["final_url"] = final
    except Exception as ex:
        res["errors"].append(f"page : {ex}")
    br = find_browser()
    if br:
        prof = tempfile.mkdtemp(prefix="grim_edge_")
        common = [br, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", "--hide-scrollbars",
                  "--mute-audio", f"--user-data-dir={prof}", "--virtual-time-budget=8000"]
        try:
            if progress:
                progress("PDF de la page (Edge sans fenêtre)…")
            pdf = unique_path(dest_dir, base + ".pdf")
            run_hidden(common + ["--no-pdf-header-footer", f"--print-to-pdf={pdf}", url], 90)
            if os.path.isfile(pdf) and os.path.getsize(pdf) > 1000:
                res["pdf"] = pdf
                res["files"].append(pdf)
            if progress:
                progress("Image pleine page…")
            png = unique_path(dest_dir, base + "_capture.png")
            run_hidden(common + ["--window-size=1280,3000", f"--screenshot={png}", url], 90)
            if os.path.isfile(png) and os.path.getsize(png) > 1000:
                res["png"] = png
                res["files"].append(png)
        except Exception as ex:
            res["errors"].append(f"navigateur : {ex}")
        finally:
            shutil.rmtree(prof, ignore_errors=True)
    else:
        res["errors"].append("Edge/Chrome introuvable : PDF et image non créés")
    return res


# ================================================================ lecture audio (ffplay cache)
class AudioPlayer:
    """Lecture d'un son avec ffplay sans fenetre ; pause = arret en memorisant la position."""

    def __init__(self):
        self.proc: Optional[subprocess.Popen] = None
        self.path = ""
        self.t0 = 0.0
        self.offset = 0.0
        self.paused_at = 0.0

    def play(self, path: str, start: float = 0.0) -> str:
        self.stop()
        ff = find_ff_tool("ffplay")
        if not ff:
            return "ffplay introuvable (installé avec ffmpeg par setup_padawan.bat)"
        try:
            self.proc = popen_hidden([ff, "-nodisp", "-autoexit", "-hide_banner", "-loglevel", "quiet",
                                      "-ss", f"{max(0.0, start):.2f}", path])
        except Exception as ex:
            return str(ex)
        self.path = path
        self.t0 = time.time()
        self.offset = max(0.0, start)
        self.paused_at = 0.0
        return ""

    def playing(self) -> bool:
        return bool(self.proc and self.proc.poll() is None)

    def position(self) -> float:
        if self.playing():
            return self.offset + time.time() - self.t0
        return self.paused_at

    def pause(self) -> None:
        if self.playing():
            pos = self.position()
            self.stop()
            self.paused_at = pos

    def stop(self) -> None:
        if self.proc:
            try:
                if self.proc.poll() is None:
                    self.proc.kill()
            except Exception:
                pass
        self.proc = None
        self.paused_at = 0.0


# ================================================================ enregistrement du micro
class Recorder:
    """Memo vocal : sounddevice (micro par defaut) -> FLAC via soundfile, niveau en direct."""

    def __init__(self):
        self.stream = None
        self.sf = None
        self.q: "queue.Queue[Any]" = queue.Queue()
        self.level = 0.0
        self.frames = 0
        self.sr = 44100
        self.path = ""
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.error = ""

    @staticmethod
    def devices() -> Tuple[List[Tuple[int, str]], Optional[int], str]:
        try:
            import sounddevice as sd  # type: ignore
        except Exception as ex:
            return [], None, f"module sounddevice absent ({ex.__class__.__name__}) : pip install sounddevice soundfile"
        try:
            sd._terminate()
            sd._initialize()
        except Exception:
            pass
        try:
            devs = sd.query_devices()
            apis = sd.query_hostapis()
        except Exception as ex:
            return [], None, f"audio indisponible : {ex}"
        out, seen = [], set()
        for i, d in enumerate(devs):
            if int(d.get("max_input_channels", 0)) <= 0:
                continue
            api = apis[d["hostapi"]]["name"] if d.get("hostapi") is not None else ""
            if "WDM-KS" in api:
                continue
            key = (d["name"][:28], api)
            if key in seen:
                continue
            seen.add(key)
            out.append((i, f"{d['name']}  ({api})"))
        try:
            dflt = sd.default.device[0]
            dflt = int(dflt) if dflt is not None and int(dflt) >= 0 else None
        except Exception:
            dflt = None
        if not out:
            return [], None, "Aucun micro détecté. Branche un micro (ou la webcam) puis clique « Actualiser »."
        if dflt is None or dflt not in [i for i, _ in out]:
            dflt = out[0][0]
        return out, dflt, ""

    def start(self, path: str, device: Optional[int] = None) -> str:
        try:
            import sounddevice as sd  # type: ignore
            import soundfile as sf  # type: ignore
        except Exception as ex:
            return f"modules audio absents : {ex}"
        try:
            info = sd.query_devices(device, "input")
            self.sr = int(info.get("default_samplerate") or 44100)
            fmt = "FLAC" if path.lower().endswith(".flac") else "WAV"
            self.sf = sf.SoundFile(path, "w", samplerate=self.sr, channels=1, format=fmt, subtype="PCM_16")
            self.path = path
            self.frames = 0
            self.level = 0.0

            def cb(indata, frames, _t, status):
                try:
                    self.q.put(indata.copy())
                    self.frames += frames
                    peak = float(abs(indata).max()) / 32768.0 if frames else 0.0
                    self.level = max(peak, self.level * 0.85)
                except Exception:
                    pass
            self.stream = sd.InputStream(device=device, channels=1, samplerate=self.sr, dtype="int16", callback=cb)
            self.running = True
            self.thread = threading.Thread(target=self._writer, daemon=True)
            self.thread.start()
            self.stream.start()
            return ""
        except Exception as ex:
            self.running = False
            try:
                if self.sf:
                    self.sf.close()
            except Exception:
                pass
            try:
                if path and os.path.isfile(path):
                    os.remove(path)
            except OSError:
                pass
            return f"impossible d'ouvrir le micro : {ex}"

    def _writer(self):
        while self.running or not self.q.empty():
            try:
                data = self.q.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                self.sf.write(data)
            except Exception as ex:
                self.error = str(ex)

    def duration(self) -> float:
        return self.frames / float(self.sr or 1)

    def stop(self) -> Tuple[str, float]:
        try:
            if self.stream:
                self.stream.stop()
                self.stream.close()
        except Exception:
            pass
        self.stream = None
        self.running = False
        if self.thread:
            self.thread.join(timeout=3)
        try:
            if self.sf:
                self.sf.close()
        except Exception:
            pass
        self.sf = None
        return self.path, self.duration()

    def cancel(self) -> None:
        p, _d = self.stop()
        try:
            if p and os.path.isfile(p):
                os.remove(p)
        except OSError:
            pass
