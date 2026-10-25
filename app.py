import logging
import os
import re
import subprocess
import shutil
import tempfile
import threading
import time
import tkinter as tk
from tkinter import filedialog
from pathlib import Path
from urllib.parse import urlparse
import importlib

local_appdata = os.environ.get("LOCALAPPDATA", "")
FFMPEG_BIN = str(
    Path(local_appdata) / "Microsoft" / "WinGet" / "Packages" /
    "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe" / "ffmpeg-8.1.1-full_build" / "bin"
)
if FFMPEG_BIN not in os.environ["PATH"]:
    os.environ["PATH"] = FFMPEG_BIN + os.pathsep + os.environ["PATH"]

import flet as ft
from markitdown import MarkItDown
from facebook_audio import convert_to_mp3, download_facebook_audio, is_facebook_url
from output_utils import (
    FAILED_LINKS_NAME, choose_output_path, read_failed_links, record_link_result,
    load_settings, save_settings, saved_output_dir,
)
from paddleocr_tools.ocr_utils import append_image_ocr, check_ocr_environment

# Importok után állítjuk be, hogy a pdfminer saját setLevel-jeit felülírjuk
logging.getLogger("pdfminer").setLevel(logging.ERROR)
logging.getLogger("pdfminer").propagate = False

# abszolút út: a felirat-lekérés átmenetileg cwd-t vált (yt-dlp write_pages), a mentés ne csússzon el
OUTPUT = Path("output").resolve()
OUTPUT.mkdir(exist_ok=True)

# Monokai Ristretto
BG       = "#2c2525"   # fő háttér
BG_DARK  = "#211c1c"   # mélyebb háttér (konténerek)
BORDER   = "#403838"   # keret, elválasztó
FG       = "#fce2be"   # szöveg, elsődleges szín
FG_DIM   = "#a89080"   # halványabb szöveg
GREEN    = "#a8c373"
RED      = "#f26d78"
YELLOW   = "#e8b057"
CYAN     = "#7fd8b4"

FILETYPES = [
    ("Minden támogatott", "*.pdf *.docx *.doc *.xlsx *.xls *.pptx *.html *.htm "
                          "*.csv *.json *.xml *.epub *.ipynb *.msg "
                          "*.azw3 *.mobi *.fb2 "
                          "*.png *.jpg *.jpeg *.gif *.bmp *.webp "
                          "*.mp3 *.wav *.m4a *.zip"),
    ("PDF", "*.pdf"),
    ("Word", "*.docx *.doc"),
    ("Excel", "*.xlsx *.xls"),
    ("PowerPoint", "*.pptx"),
    ("Ebook", "*.azw3 *.mobi *.fb2"),
]

AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a"}


def open_file_dialog() -> list[Path]:
    result: list[Path] = []

    def _pick():
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        paths = filedialog.askopenfilenames(filetypes=FILETYPES, title="Fájl kiválasztása")
        root.destroy()
        result.extend(Path(p) for p in paths)

    t = threading.Thread(target=_pick)
    t.start()
    t.join()
    return result


def open_folder_dialog() -> Path | None:
    result: list[Path] = []

    def _pick():
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askdirectory(title="Kimeneti mappa kiválasztása")
        root.destroy()
        if path:
            result.append(Path(path))

    t = threading.Thread(target=_pick)
    t.start()
    t.join()
    return result[0] if result else None


def open_txt_dialog() -> Path | None:
    result: list[Path] = []

    def _pick():
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askopenfilename(
            filetypes=[("Szövegfájl", "*.txt"), ("Minden fájl", "*.*")],
            title="Linklista kiválasztása",
        )
        root.destroy()
        if path:
            result.append(Path(path))

    t = threading.Thread(target=_pick)
    t.start()
    t.join()
    return result[0] if result else None


# Ezeknél a sima HTML-letöltés nem ad használható tartalmat (JS-oldal / 403),
# ezért yt-dlp-vel letöltjük a hangot és Whisperrel írjuk át.
YT_DLP_SITES = (
    "tiktok.com",
    "instagram.com",
    "facebook.com",
    "fb.watch",
    "twitter.com",
    "x.com",
)


def is_media_site(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == site or host.endswith("." + site) for site in YT_DLP_SITES)


def has_real_transcript(text: str) -> bool:
    """A leírás vagy egy üres átirat-fejléc nem számít kész átiratnak."""
    return any(match.group(1).strip() for match in re.finditer(
        r"^### (?:Transcript|Audio Transcript|Felirat):?[^\S\n]*\n(.*?)(?=^#{1,3} |\Z)",
        text, re.MULTILINE | re.DOTALL,
    ))


def output_has_transcript(path: Path) -> bool:
    try:
        return has_real_transcript(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError):
        return False


def is_youtube_url(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return "youtube.com" in host or "youtu.be" in host


class TranscriptMissingError(RuntimeError):
    """YouTube-videó, amihez nem készült átirat.

    A `candidate` a Whisper-átíráshoz szükséges adatokat tartalmazza
    (url, cím, hossz mp-ben), vagy None, ha a videó le sem tölthető.
    A `blocked` jelzi, hogy a YouTube letiltotta az IP-t a felirat-API-n.
    """

    def __init__(self, message: str, candidate: dict | None = None, blocked: bool = False):
        super().__init__(message)
        self.candidate = candidate
        self.blocked = blocked


# YouTube-videók között ennyi mp szünet, hogy nagy listánál se jöjjön IP-tiltás
YOUTUBE_PAUSE_S = 4.0


# Minden yt-dlp híváshoz. A YouTube a médiacímeket JS-kihívással védi: futtató nélkül 403-at
# ad a letöltésre. A yt-dlp alapból csak a Denót keresi, ezért a Node-ot is engedélyezzük
# (a nem telepített futtatót kihagyja). A színkódok ne kerüljenek a naplóba ([0;31mERROR).
YTDLP_BASE_OPTS = {"js_runtimes": {"deno": {}, "node": {}}, "color": "no_color"}

# Elavult letöltőre utaló hibák (nem IP-tiltás): ilyenkor a következő indításkor frissítünk.
_OUTDATED_HINTS = ("HTTP Error 403", "Unable to extract", "nsig extraction failed",
                   "Requested format is not available", "Signature extraction failed")


def flag_update_if_outdated(ex: Exception) -> bool:
    """Ha a hiba elavult yt-dlp-re utal, kéri a frissítést a következő indításra.

    True, ha most kérte először (ilyenkor a hívó egyszer jelez a naplóban).
    """
    if not any(hint in str(ex) for hint in _OUTDATED_HINTS) or load_settings().get("force_update"):
        return False
    save_settings(force_update=True)
    return True


def probe_media_info(url: str) -> dict | None:
    """yt-dlp metaadat-lekérés letöltés nélkül (cím, hossz, felirat-elérhetőség)."""
    try:
        import yt_dlp

        opts = {**YTDLP_BASE_OPTS, "quiet": True, "no_warnings": True, "skip_download": True}
        with yt_dlp.YoutubeDL(opts) as ydl:  # type: ignore[arg-type]
            return ydl.extract_info(url, download=False)
    except Exception:
        return None


def whisper_transcript_body(md_text: str) -> str:
    """A markitdown hang-kimenetéből kiszedi a puszta átiratot.

    A konverter a `### Audio Transcript:` elé exiftool-metaadatokat is írhat
    (Title, Artist, …); azok a letöltött fájl adatai, nem a videóé, ezért eldobjuk.
    """
    marker = "### Audio Transcript:"
    if marker in md_text:
        return md_text.split(marker, 1)[1].strip()
    return md_text.strip()


def _iso8601_duration(seconds: float) -> str:
    """Másodperc → ISO-8601 időtartam (PT21M41S), ahogy a markitdown kimenetében szerepel."""
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"PT{h}H{m}M{s}S" if h else f"PT{m}M{s}S"


def youtube_metadata_markdown(meta: dict) -> str:
    """A markitdown YouTube-kimenetével egyező fejléc (cím, metaadatok, leírás).

    Üres stringet ad, ha nincs használható metaadat – ilyenkor a hívó
    változatlanul, csak az átirattal menti a fájlt.
    """
    title = meta.get("title")
    if not title or title == meta.get("url"):
        return ""
    text = f"# YouTube\n\n## {title}\n"
    stats = ""
    if meta.get("view_count"):
        stats += f"- **Views:** {meta['view_count']}\n"
    if meta.get("tags"):
        stats += f"- **Keywords:** {','.join(meta['tags'])}\n"
    if meta.get("duration"):
        stats += f"- **Runtime:** {_iso8601_duration(meta['duration'])}\n"
    if stats:
        text += f"\n### Video Metadata\n{stats}"
    if meta.get("description"):
        text += f"\n### Description\n{meta['description']}\n"
    return text


def ensure_real_transcript(url: str, text: str) -> None:
    """YouTube-linkeknél ellenőrzi, hogy tényleg készült-e átirat.

    A markitdown, ha nem éri el a feliratot, csendben visszaesik a weboldal
    szövegére (menü/lábléc), és azt "sikeres" kimenetként adja vissza. Ilyenkor
    yt-dlp-vel kiderítjük a VALÓDI okot (nincs felirat vs. API-blokk), és
    TranscriptMissingError-t dobunk, hogy ne szülessen félrevezető, üres .md fájl.
    """
    if not is_youtube_url(url) or "### Transcript" in text:
        return
    info = probe_media_info(url)
    if info is None:
        raise TranscriptMissingError(
            "nem sikerült átiratot lekérni, és a videó adatai sem érhetők el. "
            "Lehet, hogy a videó privát, törölt vagy korhatáros, esetleg a "
            "YouTube átmenetileg blokkolja a kéréseket erről a hálózatról."
        )
    candidate = {
        "url": url,
        "title": info.get("title") or url,
        "duration": info.get("duration"),
        "view_count": info.get("view_count"),
        "tags": info.get("tags") or [],
        "description": info.get("description") or "",
    }
    if not (info.get("subtitles") or info.get("automatic_captions")):
        raise TranscriptMissingError(
            "a videónak NINCS FELIRATA a YouTube-on (se kézi, se automatikus), "
            "ezért nem készült átirat. Whisper-átírással viszont elkészíthető.",
            candidate,
        )
    raise TranscriptMissingError(
        "a videónak van felirata, de a YouTube felirat-API nem adta ki – "
        "valószínűleg túl sok kérés miatt átmenetileg blokkolta az IP-címedet. "
        "Válts hálózatot vagy várj néhány órát; a Whisper-átírás így is működik.",
        candidate,
        blocked=True,
    )


def url_to_basename(url: str) -> str:
    """Stabil, sorszám nélküli alapnevet képez egy URL-ből (kiterjesztés nélkül).

    Ugyanaz az URL mindig ugyanazt adja, így újrafuttatáskor felismerhető a kész fájl.
    """
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if "youtube.com" in host or "youtu.be" in host:
        if "v=" in url:
            return "youtube_" + url.split("v=")[-1].split("&")[0][:16]
        return "youtube_" + parsed.path.strip("/").split("/")[-1][:16]
    if "tiktok.com" in host:
        m = re.search(r"/video/(\d+)", parsed.path)
        return "tiktok_" + (m.group(1) if m else parsed.path.strip("/")[:24])
    base = (host + parsed.path).strip("/")
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("_")
    return base[:80] or "link"


def parse_link_list(text: str) -> list[str]:
    """Linklista-mező → URL-ek (üres és #-kal kezdődő sorok nélkül)."""
    return [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]


def already_converted(out_dir: Path, url: str) -> bool:
    """Van-e már kész kimenet a linkhez a mappában (Facebooknál csak valódi átirattal)."""
    name = url_to_basename(url)
    paths = [out_dir / f"{name}.md", *out_dir.glob(f"???_{name}.md")]
    return any(path.exists() and (not is_facebook_url(url) or output_has_transcript(path))
               for path in paths)


def _download_media_with_ytdlp(url: str, tmpdir: str) -> Path:
    """yt-dlp-vel letölti a videót (hanggal) a tmpdir-be, és visszaadja az útvonalat.

    A Whisper az ffmpeg-en keresztül a videófájlból is kinyeri a hangot, ezért nem
    konvertálunk külön audióvá. A formátum-string a TikTok 'download' (vízjelmentes,
    hangos) változatát preferálja; más oldalakon a bestaudio/best lép életbe.
    """
    import yt_dlp

    ydl_opts = {
        **YTDLP_BASE_OPTS,
        "format": "download/bestaudio/best",
        "outtmpl": str(Path(tmpdir) / "%(id)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "socket_timeout": 30,
    }
    if Path(FFMPEG_BIN).is_dir():
        ydl_opts["ffmpeg_location"] = FFMPEG_BIN
    # a YouTube néha átmeneti 403-at ad a médialetöltésre → egyszer újrapróbáljuk
    last_err: Exception | None = None
    for attempt in range(2):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:  # type: ignore[arg-type]
                info = ydl.extract_info(url, download=True)
                if not isinstance(info, dict):
                    raise RuntimeError("A letöltő nem adott médiafájlt.")
                filename = ydl.prepare_filename(info)
            break
        except Exception as ex:
            last_err = ex
            if attempt == 0:
                time.sleep(3)
    else:
        raise last_err  # type: ignore[misc]

    downloads = info.get("requested_downloads") or []
    if downloads and downloads[0].get("filepath"):
        path = Path(downloads[0]["filepath"])
    else:
        path = Path(info.get("filepath") or info.get("_filename") or filename)
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError("A letöltött médiafájl nem található vagy üres.")

    # A markitdown csak .mp3/.m4a/.mp4/.wav kiterjesztést fogad el; a whisper/ffmpeg a
    # tényleges tartalom alapján dekódol, így a kiterjesztés átnevezése ártalmatlan.
    if path.suffix.lower() not in {".mp3", ".m4a", ".mp4", ".wav"}:
        renamed = path.with_suffix(".mp4")
        path.rename(renamed)
        path = renamed
    return path


def download_media_audio(url: str, tmpdir: str, progress_fn=None) -> Path:
    """Facebooknál valódi MP3-at ad; yt-dlp-hiba esetén ingyenes FDOWN-t használ."""
    if not is_facebook_url(url):
        return _download_media_with_ytdlp(url, tmpdir)
    try:
        source = _download_media_with_ytdlp(url, tmpdir)
        if progress_fn:
            progress_fn("Facebook-hangsáv átalakítása MP3-má...")
        return convert_to_mp3(source, Path(tmpdir) / "facebook_audio.mp3", FFMPEG_BIN)
    except Exception as ex:
        logging.getLogger(__name__).info("Facebook yt-dlp letöltés sikertelen: %s", ex)
        if progress_fn:
            progress_fn("A közvetlen letöltés nem sikerült; ingyenes FDOWN tartalékletöltő indul...")
        return download_facebook_audio(
            url, tmpdir, ffmpeg_location=FFMPEG_BIN, progress_fn=progress_fn,
        )


def _subtitle_to_text(data: str) -> str:
    """VTT vagy SRT felirat → sima szöveg (időbélyegek, sorszámok, tagek nélkül)."""
    out: list[str] = []
    for raw in data.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line == "WEBVTT" or "-->" in line or line.isdigit():
            continue
        if line.startswith(("NOTE", "Kind:", "Language:")):
            continue
        line = re.sub(r"<[^>]+>", "", line).strip()  # <00:00:00.000>, <c> stb.
        if not line:
            continue
        if out and out[-1] == line:  # egymás utáni duplikátumok kiszűrése (auto-felirat)
            continue
        out.append(line)
    return "\n".join(out).strip()


def _tiktok_caption_text(url: str, lang: str | None) -> str | None:
    """TikTok auto-generált feliratát szedi le (Whisper nélkül), a yt-tól megszokott módon.

    A TikTok bot-védelme miatt a sima HTML-kérés csak egy üres oldalt ad vissza, ezért a
    yt-dlp extraktorával (write_pages) töltjük le a valódi oldalt, amibe a TikTok beágyazza a
    `subtitleInfos` mezőt; abból kinyerjük a webvtt felirat URL-jét, letöltjük és szöveggé alakítjuk.
    """
    import json as _json

    import yt_dlp

    # A write_pages a cwd-be írja a .dump-ot → ideiglenes mappába váltunk, utána visszaállítunk.
    dump_dir = tempfile.mkdtemp(prefix="ttsub_")
    cwd = os.getcwd()
    html = ""
    try:
        os.chdir(dump_dir)
        opts = {**YTDLP_BASE_OPTS, "quiet": True, "no_warnings": True, "skip_download": True,
                "write_pages": True}
        with yt_dlp.YoutubeDL(opts) as ydl:  # type: ignore[arg-type]
            ydl.extract_info(url, download=False)
        dumps = [f for f in os.listdir(dump_dir) if f.endswith(".dump")]
        if dumps:
            html = Path(dump_dir, dumps[0]).read_text(encoding="utf-8", errors="ignore")
    finally:
        os.chdir(cwd)
        shutil.rmtree(dump_dir, ignore_errors=True)

    m = re.search(r'"subtitleInfos":(\[[^\]]*\])', html)
    if not m:
        return None
    try:
        infos = _json.loads(m.group(1))  # a / escape-eket a json.loads feloldja
    except _json.JSONDecodeError:
        return None
    infos = [s for s in infos if s.get("Url") and s.get("Format") == "webvtt"]
    if not infos:
        return None

    # nyelvkód: a felület 2 betűs ISO-639-1-et használ, a TikTok 3 betűset (eng/hun/...)
    lang3 = {"hu": "hun", "en": "eng", "de": "deu", "fr": "fra", "es": "spa", "ru": "rus"}
    chosen = None
    if lang:
        target = lang3.get(lang, lang).lower()
        cands = [s for s in infos if s.get("LanguageCodeName", "").lower().startswith(target)]
        # kért nyelven belül az eredeti (ASR) előny a gépi fordítással (MT) szemben
        chosen = next((s for s in cands if s.get("Source") == "ASR"), None) or (cands[0] if cands else None)
    if chosen is None:
        # eredeti beszéd átirata, különben az első elérhető
        chosen = next((s for s in infos if s.get("Source") == "ASR"), None) or infos[0]

    import requests

    resp = requests.get(
        chosen["Url"],
        headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.tiktok.com/"},
        timeout=20,
    )
    resp.raise_for_status()
    return _subtitle_to_text(resp.text) or None


def _generic_captions(url: str, lang: str | None) -> str | None:
    """Általános felirat-lekérés yt-dlp subtitles/automatic_captions alapján (nem TikTok)."""
    import yt_dlp

    probe_opts = {**YTDLP_BASE_OPTS, "quiet": True, "no_warnings": True, "skip_download": True}
    with yt_dlp.YoutubeDL(probe_opts) as ydl:  # type: ignore[arg-type]
        info = ydl.extract_info(url, download=False)

    subs = info.get("subtitles") or {}
    auto = info.get("automatic_captions") or {}
    if not subs and not auto:
        return None

    def _pick(tracks: dict):
        if not tracks:
            return None
        for want in ([lang] if lang else []) + ["en"]:
            if want in tracks:
                return tracks[want]
        return next(iter(tracks.values()), None)  # bármelyik elérhető nyelv

    entries = _pick(subs) or _pick(auto)  # kézi felirat előny az auto-val szemben
    if not entries:
        return None

    chosen = None
    for ext in ("vtt", "srt"):
        chosen = next((e for e in entries if e.get("ext") == ext and e.get("url")), None)
        if chosen:
            break
    if chosen is None:
        return None  # csak ismeretlen formátum van → inkább Whisper

    import requests

    resp = requests.get(chosen["url"], timeout=20)
    resp.raise_for_status()
    return _subtitle_to_text(resp.text) or None


def fetch_media_captions(url: str, lang: str | None) -> str | None:
    """Megpróbálja leszedni a KÉSZ feliratot (Whisper nélkül, gyors).

    Sima szöveget ad vissza, vagy None-t, ha nincs felirat → a hívó Whisperre vált.
    Bármilyen hiba esetén None (a Whisper-tartalék úgyis lefut).
    """
    try:
        if "tiktok.com" in urlparse(url).netloc.lower():
            return _tiktok_caption_text(url, lang)
        return _generic_captions(url, lang)
    except Exception:
        return None


def convert_link(md, url: str, lang: str | None, model: str = "turbo", progress_fn=None) -> tuple[str, str]:
    """Az egyedi URL és a linklista közös felirat-/Whisper-útvonala."""
    if not is_media_site(url):
        text = md.convert(url).text_content
        ensure_real_transcript(url, text)
        return text, ""

    facebook = is_facebook_url(url)
    header = ""
    if progress_fn:
        progress_fn("Felirat keresése...")
    if facebook:
        try:
            header = md.convert(url).text_content
        except Exception:
            pass  # A HTML-oldal hibája mellett a hang még letölthető lehet.
        if header.startswith("# Facebook\n"):
            if has_real_transcript(header):
                return header, " [felirat]"
        else:
            header = f"# Facebook\n\n- **Source:** {url}\n"

    captions = fetch_media_captions(url, lang)
    if captions:
        text = f"{header.rstrip()}\n\n### Transcript\n{captions}\n" if facebook else "### Felirat:\n\n" + captions
        return text, " [felirat]"

    if progress_fn:
        progress_fn("Nincs felirat, hang letöltése...")
    with tempfile.TemporaryDirectory(prefix="mtd_") as tmpdir:
        audio_path = download_media_audio(url, tmpdir, progress_fn=progress_fn)
        result = md.convert(
            str(audio_path), whisper_language=lang, whisper_model=model,
            whisper_progress_fn=progress_fn,
        )
        text = result.text_content
        if not has_real_transcript(text):
            raise RuntimeError("A hangletöltés után nem készült átirat; a kimenet nem lett elmentve.")
        if facebook:
            text = f"{header.rstrip()}\n\n### Transcript\n{whisper_transcript_body(text)}\n"
        return text, " [whisper]"


def main(page: ft.Page):
    page.title = "MakeThemd"
    page.window.width = 770
    page.window.height = 860
    page.bgcolor = BG
    page.padding = 24

    md = MarkItDown()
    selected_files: list[Path] = []
    # újraindítás után is az utoljára választott mappába ment (és ott keresi a kész fájlokat)
    current_output: list[Path] = [saved_output_dir(OUTPUT)]

    border_style = ft.Border(
        left=ft.BorderSide(1, BORDER),
        right=ft.BorderSide(1, BORDER),
        top=ft.BorderSide(1, BORDER),
        bottom=ft.BorderSide(1, BORDER),
    )

    btn_style = ft.ButtonStyle(
        bgcolor=BG_DARK,
        color=FG,
        side=ft.BorderSide(1, BORDER),
        shape=ft.RoundedRectangleBorder(radius=6),
        padding=ft.Padding(left=16, right=16, top=10, bottom=10),
    )

    convert_btn_style = ft.ButtonStyle(
        bgcolor=BORDER,
        color=FG,
        shape=ft.RoundedRectangleBorder(radius=6),
        padding=ft.Padding(left=32, right=32, top=14, bottom=14),
    )

    status_log = ft.ListView(expand=True, spacing=4, auto_scroll=True)

    try:
        import torch as _torch
        _cuda = _torch.cuda.is_available()
        _device_name = _torch.cuda.get_device_name(0) if _cuda else "CPU"
    except ImportError:
        _cuda = False
        _device_name = "CPU (whisper nincs telepítve)"

    device_label = ft.Text(
        f"{'CUDA  •  ' + _device_name if _cuda else 'CPU  •  ' + _device_name}",
        size=11,
        color=GREEN if _cuda else FG_DIM,
    )

    language_dd = ft.Dropdown(
        label="Nyelv (audio)",
        value="hu",
        width=160,
        bgcolor=BG_DARK,
        border_color=BORDER,
        focused_border_color=FG,
        color=FG,
        label_style=ft.TextStyle(color=FG_DIM),
        options=[
            ft.dropdown.Option("hu", "Magyar"),
            ft.dropdown.Option("en", "English"),
            ft.dropdown.Option("de", "Deutsch"),
            ft.dropdown.Option("fr", "Français"),
            ft.dropdown.Option("es", "Español"),
            ft.dropdown.Option("ru", "Русский"),
            ft.dropdown.Option(key="auto", text="Auto detect"),
        ],
    )

    if _cuda:
        model_options = [
            ft.dropdown.Option("tiny",   "tiny   — nagyon gyors, kevésbé pontos"),
            ft.dropdown.Option("base",   "base   — gyors"),
            ft.dropdown.Option("small",  "small  — közepes"),
            ft.dropdown.Option("medium", "medium — lassabb, pontosabb"),
            ft.dropdown.Option("turbo",  "turbo  — gyors és pontos (ajánlott)"),
            ft.dropdown.Option("large",  "large  — leglassabb, legjobb minőség"),
        ]
    else:
        model_options = [
            ft.dropdown.Option("tiny",  "tiny  — nagyon gyors"),
            ft.dropdown.Option("base",  "base  — gyors"),
            ft.dropdown.Option("small", "small — lassabb, pontosabb"),
            ft.dropdown.Option("turbo", "turbo — pontosabb, CPU-n lassabb"),
        ]

    model_dd = ft.Dropdown(
        label="Whisper modell",
        value="turbo",
        width=280,
        bgcolor=BG_DARK,
        border_color=BORDER,
        focused_border_color=FG,
        color=FG,
        label_style=ft.TextStyle(color=FG_DIM),
        options=model_options,
    )

    url_field = ft.TextField(
        label="Video / Page URL",
        hint_text="https://www.youtube.com/watch?v=... or https://www.tiktok.com/... or https://www.instagram.com/...",
        expand=True,
        border_radius=6,
        bgcolor=BG_DARK,
        border_color=BORDER,
        focused_border_color=FG,
        color=FG,
        label_style=ft.TextStyle(color=FG_DIM),
        hint_style=ft.TextStyle(color=FG_DIM),
        cursor_color=FG,
        on_change=lambda _e: update_link_count(),
    )

    ocr_checkbox = ft.Checkbox(
        label="OCR képekből helyileg",
        value=False,
        active_color=GREEN,
        check_color=BG_DARK,
        label_style=ft.TextStyle(color=FG),
    )
    link_count_label = ft.Text("", size=11, color=FG_DIM)

    def update_link_count(_e=None):
        active = parse_link_list(links_field.value or "")
        link_count_label.value = f"{len(active)} link betöltve" if active else ""
        # YouTube is számít: felirat híján a batch végén Whisper-átírás ajánlható fel
        url_single = (url_field.value or "").strip()
        if url_single:
            active = active + [url_single]
        has_media_link = any(is_media_site(ln) or is_youtube_url(ln) for ln in active)
        has_audio_file = any(f.suffix.lower() in AUDIO_EXTENSIONS for f in selected_files)
        audio_settings_row.visible = has_audio_file or has_media_link
        page.update()

    links_field = ft.TextField(
        label="Linklista (soronként egy URL)",
        hint_text="https://pelda.hu/cikk\nhttps://masik.hu/oldal",
        multiline=True,
        min_lines=3,
        max_lines=6,
        expand=True,
        border_radius=6,
        bgcolor=BG_DARK,
        border_color=BORDER,
        focused_border_color=FG,
        color=FG,
        label_style=ft.TextStyle(color=FG_DIM),
        hint_style=ft.TextStyle(color=FG_DIM),
        cursor_color=FG,
        on_change=update_link_count,
    )

    def load_links(e):
        path = open_txt_dialog()
        if not path:
            return
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = path.read_text(encoding="latin-1")
        existing = (links_field.value or "").strip()
        links_field.value = (existing + "\n" + content).strip() if existing else content.strip()
        update_link_count()

    def clear_links(e):
        links_field.value = ""
        update_link_count()

    def refresh_retry_button():
        n = len(read_failed_links(current_output[0]))
        retry_btn.content = f"Újrapróbálás ({n})" if n else "Újrapróbálás"
        retry_btn.disabled = n == 0

    def load_failed_links(e):
        failed = read_failed_links(current_output[0])
        refresh_retry_button()
        if not failed:
            update_link_count()
            return
        links_field.value = "\n".join(failed)
        update_link_count()
        log(
            f"↻  {len(failed)} sikertelen link visszatöltve a linklistába "
            f"({FAILED_LINKS_NAME}) – indítsd a Konvertálást.",
            CYAN,
        )

    retry_btn = ft.Button(
        "Újrapróbálás",
        icon=ft.Icons.REPLAY,
        style=btn_style,
        tooltip=f"A kimeneti mappa korábban sikertelen linkjeinek visszatöltése ({FAILED_LINKS_NAME})",
        on_click=load_failed_links,
    )
    refresh_retry_button()

    AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".mp4"}

    tags_row = ft.Row(wrap=True, spacing=6, run_spacing=6)
    files_tags_container = ft.Container(
        content=tags_row,
        visible=False,
        padding=ft.Padding(left=0, right=0, top=6, bottom=0),
    )

    audio_settings_row = ft.Row(
        [language_dd, model_dd, device_label],
        spacing=12,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        visible=False,
    )

    eta_column = ft.Column(controls=[], spacing=2, tight=True)
    eta_container = ft.Container(
        content=eta_column,
        visible=False,
        padding=ft.Padding(left=0, right=0, top=4, bottom=0),
    )

    def safe_update():
        try:
            page.update()
        except Exception:
            pass

    def log(msg: str, color=FG):
        status_log.controls.append(
            ft.Text(msg, color=color, size=13, font_family="monospace")
        )
        safe_update()

    def make_tag(path: Path) -> ft.Container:
        def remove(e, p=path):
            selected_files.remove(p)
            refresh_file_list()

        return ft.Container(
            content=ft.Row(
                [
                    ft.Text(path.name, size=12, color="#ffffff", no_wrap=True),
                    ft.IconButton(
                        icon=ft.Icons.CLOSE,
                        icon_size=12,
                        icon_color=FG_DIM,
                        style=ft.ButtonStyle(padding=ft.Padding(0, 0, 0, 0)),
                        on_click=remove,
                    ),
                ],
                spacing=2,
                tight=True,
            ),
            bgcolor=BG_DARK,
            border=border_style,
            border_radius=20,
            padding=ft.Padding(left=10, right=4, top=4, bottom=4),
        )

    def refresh_file_list():
        tags_row.controls.clear()
        for f in selected_files:
            tags_row.controls.append(make_tag(f))
        files_tags_container.visible = bool(selected_files)
        has_audio = any(f.suffix.lower() in AUDIO_EXTENSIONS for f in selected_files)
        has_media_link = any(
            is_media_site(ln) or is_youtube_url(ln) for ln in parse_link_list(links_field.value or "")
        )
        audio_settings_row.visible = has_audio or has_media_link
        update_eta()

    def pick_files(e):
        paths = open_file_dialog()
        for p in paths:
            if p not in selected_files:
                selected_files.append(p)
        refresh_file_list()

    def clear_files(e):
        selected_files.clear()
        refresh_file_list()

    # Whisper sebességbecslés (beam_size=1, RTX 30xx mért adatok alapján)
    # large CUDA: mért 242 fr/s ≈ 2.4× realtime RTX 3080-on
    # turbo = large-v3-turbo: ~8× gyorsabb mint large, hasonló minőség
    WHISPER_SPEED = {
        "tiny":   {"cuda": 30,  "cpu": 3},
        "base":   {"cuda": 15,  "cpu": 1.5},
        "small":  {"cuda": 8,   "cpu": 0.7},
        "medium": {"cuda": 4,   "cpu": 0.3},
        "turbo":  {"cuda": 10,  "cpu": 0.8},
        "large":  {"cuda": 2.4, "cpu": 0.15},
    }

    def get_audio_info(path: Path, model: str) -> tuple[float | None, float | None]:
        """Returns (audio_duration_s, estimated_processing_s) – ffprobe-val, gyors."""
        try:
            r = subprocess.run(
                ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                capture_output=True, text=True, timeout=5,
            )
            duration = float(r.stdout.strip())
            device = "cuda" if _cuda else "cpu"
            speed = WHISPER_SPEED.get(model, {}).get(device, 5)
            return duration, duration / speed
        except Exception:
            return None, None

    def fmt_seconds(s: float) -> str:
        if s < 60:
            return f"~{int(s)+1} mp"
        if s < 3600:
            return f"~{int(s/60)+1} perc"
        h, m = divmod(int(s) // 60, 60)
        return f"~{h} óra {m} perc"

    def fmt_duration(s: float) -> str:
        m, sec = divmod(int(s), 60)
        return f"{m}:{sec:02d}"

    def fmt_hms(s: float) -> str:
        """Videóhossz emberi formában: 1:23:45 vagy 23:45."""
        h, rem = divmod(int(s), 3600)
        m, sec = divmod(rem, 60)
        return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"

    def sanitize_filename(name: str) -> str:
        safe = re.sub(r"[^a-zA-Z0-9_.-]", "_", name)
        return safe.strip("_-")[:120] or "output"

    def resize_window():
        n = sum(1 for f in selected_files if f.suffix.lower() in AUDIO_EXTENSIONS)
        # 860 alap (nincs audio sor); +80 a settings+ETA sornak, +28 minden további fájlhoz
        page.window.height = 860 if n == 0 else min(940 + (n - 1) * 28, 1050)
        page.update()

    def update_eta(_e=None):
        audio_files = [f for f in selected_files if f.suffix.lower() in AUDIO_EXTENSIONS]
        if not audio_files:
            eta_container.visible = False
            resize_window()
            return

        model = model_dd.value or "turbo"
        controls = []
        total_eta = 0.0
        for f in audio_files:
            dur_s, eta_s = get_audio_info(f, model)
            if dur_s and eta_s:
                controls.append(ft.Text(
                    f"  {f.name}   {fmt_duration(dur_s)}  →  {fmt_seconds(eta_s)}",
                    size=12, color=YELLOW, font_family="monospace",
                ))
                total_eta += eta_s
            else:
                controls.append(ft.Text(
                    f"  {f.name}   (ismeretlen hossz)",
                    size=12, color=FG_DIM, font_family="monospace",
                ))
        if len(audio_files) > 1 and total_eta:
            controls.append(ft.Text(
                f"  Összesen: {fmt_seconds(total_eta)}",
                size=12, color=YELLOW, weight=ft.FontWeight.W_600, font_family="monospace",
            ))
        eta_column.controls = controls
        eta_container.visible = True
        resize_window()

    model_dd.on_change = update_eta  # type: ignore[attr-defined]

    audio_settings_row.controls.append(ft.IconButton(
        icon=ft.Icons.REFRESH,
        icon_size=16,
        icon_color=FG_DIM,
        tooltip="ETA újraszámítása",
        on_click=update_eta,
    ))

    def notify_done(errors: int):
        """Hangjelzés + villogó tálca-ikon a futás végén."""
        try:
            import ctypes
            import winsound

            beep = winsound.MB_ICONHAND if errors else winsound.MB_ICONASTERISK
            winsound.MessageBeep(beep)
            hwnd = ctypes.windll.user32.FindWindowW(None, page.title)
            if hwnd:
                ctypes.windll.user32.FlashWindow(hwnd, True)
        except Exception:
            pass

    def note_outdated(ex: Exception):
        if flag_update_if_outdated(ex):
            log(
                "↻  A hiba elavult letöltőre utal – a következő indításkor "
                "(start_makethemd.bat) automatikusan frissítem a yt-dlp-t.",
                YELLOW,
            )

    def run_whisper_batch(items: list[dict], lang, model):
        """A kijelölt (felirat nélküli) videók hangját letölti és Whisperrel átírja."""
        spinner.visible = True
        safe_update()
        ok = 0
        errs = 0
        n = len(items)
        for i, cand in enumerate(items, 1):
            title = cand["title"] if len(cand["title"]) <= 55 else cand["title"][:54] + "…"
            live = ft.Text(
                f"⬇  [{i}/{n}]  {title}  — hang letöltése...",
                size=13, color=FG_DIM, font_family="monospace",
            )
            status_log.controls.append(live)
            safe_update()
            tmpdir = tempfile.mkdtemp(prefix="mtd_")
            try:
                audio_path = download_media_audio(cand["url"], tmpdir)

                _wp_last = [0.0]

                def _on_progress(msg, ctrl=live, idx=i, _t=_wp_last):
                    ctrl.value = f"   [{idx}/{n}]  {msg}"
                    now = time.monotonic()
                    if now - _t[0] >= 0.15:
                        _t[0] = now
                        try:
                            ctrl.update()
                        except Exception:
                            pass

                result = md.convert(
                    str(audio_path),
                    whisper_language=lang,
                    whisper_model=model,
                    whisper_progress_fn=_on_progress,
                )
                out_text = result.text_content
                # ha van metaadat, a felirat-alapú kimenettel egyező fejlécet kap
                header = youtube_metadata_markdown(cand)
                if header:
                    out_text = f"{header}\n### Transcript\n{whisper_transcript_body(out_text)}\n"
                out_path = cand["out_path"]
                out_path.write_text(out_text, encoding="utf-8")
                record_link_result(out_path.parent, cand["url"])
                status_log.controls.remove(live)
                log(f"✓  [{i}/{n}]  {title}  →  {out_path.name} [whisper]", GREEN)
                ok += 1
            except Exception as ex:
                try:
                    status_log.controls.remove(live)
                except ValueError:
                    pass
                record_link_result(cand["out_path"].parent, cand["url"], f"Whisper: {ex}")
                log(f"✗  [{i}/{n}]  {title}: {ex}", RED)
                note_outdated(ex)
                errs += 1
            finally:
                shutil.rmtree(tmpdir, ignore_errors=True)

        spinner.visible = False
        refresh_retry_button()
        log(f"\nWhisper-átírás kész: {ok} sikeres, {errs} hiba", RED if errs else CYAN)
        notify_done(errs)

    def offer_whisper_retry(candidates: list[dict], lang, model):
        """Batch végi ablak: a felirat nélkül maradt videók Whisper-átírásának felajánlása."""
        device = "cuda" if _cuda else "cpu"
        speed = WHISPER_SPEED.get(model, {}).get(device, 5)

        checkboxes: list[ft.Checkbox] = []
        has_long = False
        for cand in candidates:
            dur = cand.get("duration")
            title = cand["title"] if len(cand["title"]) <= 48 else cand["title"][:47] + "…"
            if dur:
                eta = fmt_seconds(dur / speed)
                label = f"{title}   ·   {fmt_hms(dur)}   ·   átírás kb. {eta}"
                preselect = dur < 3600  # 1 óránál hosszabbat csak kérésre
                has_long = has_long or dur >= 3600
            else:
                label = f"{title}   ·   ismeretlen hossz"
                preselect = False
            checkboxes.append(ft.Checkbox(
                label=label,
                value=preselect,
                data=cand,
                active_color=GREEN,
                check_color=BG_DARK,
                label_style=ft.TextStyle(color=FG, size=12),
            ))

        def _close():
            # A Flet saját dialógus-vermet kezel; kézi overlay-manipulációval
            # a bezárás nem jut el a klienshez, és a modális ablak beragad.
            page.pop_dialog()
            safe_update()

        def _cancel(e):
            _close()
            log("Whisper-átírás kihagyva.", FG_DIM)

        def _start(e):
            selected = [cb.data for cb in checkboxes if cb.value]
            _close()
            if not selected:
                log("Nem volt kijelölt videó, a Whisper-átírás elmaradt.", YELLOW)
                return
            threading.Thread(
                target=run_whisper_batch, args=(selected, lang, model), daemon=True
            ).start()

        content_items: list[ft.Control] = [
            ft.Text(
                f"{len(candidates)} videóhoz nem készült átirat. "
                "Jelöld ki, melyeket írja át a Whisper (hang letöltése + helyi átírás):",
                color=FG_DIM, size=12,
            ),
            *checkboxes,
        ]
        if has_long:
            content_items.append(ft.Text(
                "Az 1 óránál hosszabb videók alapból nincsenek kijelölve.",
                color=YELLOW, size=11, italic=True,
            ))

        dlg = ft.AlertDialog(
            modal=True,
            bgcolor=BG_DARK,
            title=ft.Text("Átírás Whisperrel?", color=FG, weight=ft.FontWeight.BOLD),
            content=ft.Column(
                content_items,
                tight=True,
                spacing=8,
                width=540,
                height=min(120 + 44 * len(checkboxes), 420),
                scroll=ft.ScrollMode.AUTO,
            ),
            actions=[
                ft.TextButton("Mégse", style=ft.ButtonStyle(color=FG_DIM), on_click=_cancel),
                ft.TextButton("Átírás", style=ft.ButtonStyle(color=GREEN), on_click=_start),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            shape=ft.RoundedRectangleBorder(radius=8),
        )
        page.show_dialog(dlg)
        safe_update()

    def convert(e):
        status_log.controls.clear()
        spinner.visible = True
        copy_label.value = ""
        page.update()

        lang = language_dd.value if language_dd.value != "auto" else None
        model = model_dd.value or "turbo"

        def run():
            converted = 0
            errors = 0
            use_ocr = bool(ocr_checkbox.value)
            out_dir = current_output[0]
            out_dir.mkdir(parents=True, exist_ok=True)

            if use_ocr:
                try:
                    check_ocr_environment()
                except Exception as ex:
                    spinner.visible = False
                    log(f"PaddleOCR nem indítható: {ex}", RED)
                    log("Lásd a SETUP.md PaddleOCR telepítési útmutatóját.", YELLOW)
                    return
            skipped = 0
            # felirat nélkül maradt videók – a batch végén Whisper-átírást ajánlunk fel rájuk
            whisper_candidates: list[dict] = []
            # az első IP-tiltás után a további YouTube-linkeket már le sem kérjük (elhalasztjuk)
            youtube_blocked = False
            deferred = 0
            _yt_last: list[float | None] = [None]

            def youtube_pause(url: str, progress_fn) -> None:
                """Két YouTube-lekérés között kivárja a YOUTUBE_PAUSE_S szünetet."""
                if not is_youtube_url(url) or _yt_last[0] is None:
                    return
                wait = YOUTUBE_PAUSE_S - (time.monotonic() - _yt_last[0])
                if wait > 0:
                    progress_fn(f"szünet a YouTube-kérések között ({int(wait) + 1} mp)...")
                    time.sleep(wait)

            def youtube_done(url: str) -> None:
                if is_youtube_url(url):
                    _yt_last[0] = time.monotonic()

            def note_youtube_block(ex: Exception) -> bool:
                """True, ha ez az első tiltás a futásban (ilyenkor egyszer figyelmeztetünk)."""
                if not (isinstance(ex, TranscriptMissingError) and ex.blocked) or youtube_blocked:
                    return False
                log(
                    "⏸  A YouTube letiltotta a felirat-kéréseket – a lista további YouTube-linkjeit "
                    "most nem kérem le, hogy ne hosszabbodjon a tiltás. Elhalasztva, később "
                    "az „Újrapróbálás” gombbal folytathatod.",
                    YELLOW,
                )
                return True

            for path in selected_files:
                out_path = out_dir / (path.stem + ".md")
                resolved_path = choose_output_path(out_path)
                if resolved_path is None:
                    log(f"⏭  {path.name}  (kihagyva, a kimeneti fájl már létezik)", FG_DIM)
                    skipped += 1
                    continue
                out_path = resolved_path

                is_audio = path.suffix.lower() in AUDIO_EXTENSIONS
                t0 = None
                live_ctrl = None
                progress_fn = None
                try:
                    if is_audio:
                        dur_s, eta_s = get_audio_info(path, model)
                        device_str = f"CUDA • {_device_name}" if _cuda else "CPU"
                        dur_str = f"  {fmt_duration(dur_s)} audio" if dur_s else ""
                        eta_str = f"  becsült: {fmt_seconds(eta_s)}" if eta_s else ""
                        log(f"⏳  {path.name}  [{device_str} • {model}{dur_str}{eta_str}]", FG_DIM)

                        t0 = time.monotonic()
                        live_ctrl = ft.Text("   ⟳  indul...", size=13, color=FG_DIM, font_family="monospace")
                        status_log.controls.append(live_ctrl)
                        safe_update()

                        _prog_last = [0.0]

                        def _on_progress(msg, ctrl=live_ctrl, _t=_prog_last):
                            ctrl.value = msg
                            now = time.monotonic()
                            if now - _t[0] >= 0.15:
                                _t[0] = now
                                try:
                                    ctrl.update()
                                except Exception:
                                    pass

                        progress_fn = _on_progress

                    result = md.convert(
                        str(path),
                        whisper_language=lang,
                        whisper_model=model,
                        whisper_progress_fn=progress_fn,
                    )
                    markdown = result.text_content
                    if use_ocr:
                        markdown, image_count = append_image_ocr(
                            markdown,
                            path,
                            progress=lambda message: log(message, FG_DIM),
                        )
                        if image_count:
                            log(f"  OCR: {image_count} képből került szöveg a kimenetbe.", CYAN)
                        else:
                            log("  OCR: nem található kiolvasható szöveget tartalmazó kép.", FG_DIM)
                    out_path.write_text(markdown, encoding="utf-8")

                    if live_ctrl is not None:
                        status_log.controls.remove(live_ctrl)

                    elapsed_str = f"  [{fmt_seconds(time.monotonic() - t0)}]" if t0 is not None else ""
                    log(f"✓  {path.name}  →  {out_path.name}{elapsed_str}", GREEN)
                    converted += 1
                except Exception as ex:
                    if live_ctrl is not None:
                        try:
                            status_log.controls.remove(live_ctrl)
                        except ValueError:
                            pass
                    log(f"✗  {path.name}: {ex}", RED)
                    errors += 1

            url_value = url_field.value.strip()
            if url_value:
                parsed_url = url_value.replace("https://", "").replace("http://", "")
                out_name = sanitize_filename(parsed_url)
                out_path = out_dir / f"{out_name}.md"
                resolved_path = choose_output_path(out_path)
                if resolved_path is None:
                    log("⏭  URL  (kihagyva, a kimeneti fájl már létezik)", FG_DIM)
                    skipped += 1
                else:
                    live_url = ft.Text("⏳  URL feldolgozása...", size=13, color=FG_DIM, font_family="monospace")
                    status_log.controls.append(live_url)
                    safe_update()

                    def _on_url_progress(msg):
                        live_url.value = f"   {msg}"
                        try:
                            live_url.update()
                        except Exception:
                            pass

                    try:
                        out_text, method = convert_link(md, url_value, lang, model, _on_url_progress)
                        resolved_path.write_text(out_text, encoding="utf-8")
                        record_link_result(out_dir, url_value)
                        log(f"✓  URL  →  {resolved_path.name}{method}", GREEN)
                        converted += 1
                    except Exception as ex:
                        if isinstance(ex, TranscriptMissingError) and ex.candidate:
                            whisper_candidates.append({**ex.candidate, "out_path": resolved_path})
                        record_link_result(out_dir, url_value, str(ex))
                        log(f"✗  URL: {ex}", RED)
                        note_outdated(ex)
                        errors += 1
                        youtube_blocked = note_youtube_block(ex) or youtube_blocked
                    finally:
                        youtube_done(url_value)
                        status_log.controls.remove(live_url)
                        safe_update()

            # ugyanaz a videó többször a listában (pl. &t= vagy &list= eltéréssel) → csak egyszer
            all_links = parse_link_list(links_field.value or "")
            link_list: list[str] = []
            seen: set[str] = set()
            for ln in all_links:
                if url_to_basename(ln) not in seen:
                    seen.add(url_to_basename(ln))
                    link_list.append(ln)
            duplicates = len(all_links) - len(link_list)
            if duplicates:
                log(f"⏭  {duplicates} ismétlődő link a listában – mindegyiket csak egyszer dolgozom fel.", FG_DIM)
                skipped += duplicates
            n_links = len(link_list)

            for i, url in enumerate(link_list, 1):
                short = url if len(url) <= 55 else url[:54] + "…"
                basename = url_to_basename(url)

                if already_converted(out_dir, url):
                    record_link_result(out_dir, url)
                    log(f"⏭  [{i}/{n_links}]  {short}  (már megvan, kihagyva)", FG_DIM)
                    skipped += 1
                    continue

                out_path = out_dir / f"{basename}.md"
                resolved_path = choose_output_path(out_path)
                if resolved_path is None:
                    log(f"⏭  [{i}/{n_links}]  {short}  (kihagyva, a kimeneti fájl már létezik)", FG_DIM)
                    skipped += 1
                    continue
                out_path = resolved_path

                if youtube_blocked and is_youtube_url(url):
                    # metaadat-lekérés nélkül (az is YouTube-kérés lenne): cím helyett az URL látszik
                    whisper_candidates.append({"url": url, "title": url, "duration": None, "out_path": out_path})
                    record_link_result(out_dir, url, "elhalasztva: a YouTube ebben a futásban letiltotta "
                                                     "a felirat-kéréseket")
                    log(f"⏸  [{i}/{n_links}]  {short}  (YouTube-tiltás miatt elhalasztva)", YELLOW)
                    deferred += 1
                    continue

                live = ft.Text(f"⏳  [{i}/{n_links}]  {short}", size=13, color=FG_DIM, font_family="monospace")
                status_log.controls.append(live)
                safe_update()

                method = ""
                _lp_last = [0.0]

                def _on_link_progress(msg, ctrl=live, idx=i, _t=_lp_last):
                    ctrl.value = f"   [{idx}/{n_links}]  {msg}"
                    now = time.monotonic()
                    if now - _t[0] >= 0.15:
                        _t[0] = now
                        try:
                            ctrl.update()
                        except Exception:
                            pass

                try:
                    youtube_pause(url, _on_link_progress)
                    out_text, method = convert_link(md, url, lang, model, _on_link_progress)
                    out_path.write_text(out_text, encoding="utf-8")
                    record_link_result(out_dir, url)
                    status_log.controls.remove(live)
                    log(f"✓  [{i}/{n_links}]  {short}  →  {out_path.name}{method}", GREEN)
                    converted += 1
                except Exception as ex:
                    try:
                        status_log.controls.remove(live)
                    except ValueError:
                        pass
                    if isinstance(ex, TranscriptMissingError) and ex.candidate:
                        whisper_candidates.append({**ex.candidate, "out_path": out_path})
                    record_link_result(out_dir, url, str(ex))
                    log(f"✗  [{i}/{n_links}]  {short}: {ex}", RED)
                    note_outdated(ex)
                    errors += 1
                    youtube_blocked = note_youtube_block(ex) or youtube_blocked
                finally:
                    youtube_done(url)
            spinner.visible = False
            refresh_retry_button()
            if converted == 0 and errors == 0 and skipped == 0 and deferred == 0:
                log("Nincs kiválasztott fájl vagy URL.", YELLOW)
            else:
                skip_str = f", {skipped} kihagyva" if skipped else ""
                defer_str = f", {deferred} elhalasztva" if deferred else ""
                summary_color = RED if errors else YELLOW if deferred else CYAN
                log(
                    f"\nKész: {converted} sikeres, {errors} hiba{defer_str}{skip_str}  →  {out_dir}",
                    summary_color,
                )
                if errors:
                    log(
                        f"⚠  {errors} elem nem készült el (lásd a fenti ✗ sorokat) – "
                        "ezekhez nem jött létre valós átirat.",
                        RED,
                    )
                if errors or deferred:
                    failed_count = len(read_failed_links(out_dir))
                    if failed_count:
                        log(
                            f"↻  {failed_count} sikertelen link elmentve: {out_dir / FAILED_LINKS_NAME}\n"
                            "   Később az „Újrapróbálás” gombbal visszatöltheted őket.",
                            YELLOW,
                        )
                notify_done(errors + deferred)
                if whisper_candidates:
                    offer_whisper_retry(whisper_candidates, lang, model)

        threading.Thread(target=run, daemon=True).start()

    def format_row(icon, label: str, exts: str) -> ft.Row:
        return ft.Row([
            ft.Container(
                content=ft.Icon(icon, size=18, color=CYAN),
                width=32, height=32, alignment=ft.Alignment.CENTER,
                bgcolor=ft.Colors.with_opacity(0.08, CYAN), border_radius=9,
            ),
            ft.Column([
                ft.Text(label, size=12, weight=ft.FontWeight.W_600, color=FG),
                ft.Text(exts, size=11, color=FG_DIM),
            ], spacing=0, tight=True),
        ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    formats = [
        (ft.Icons.DESCRIPTION_OUTLINED, "Dokumentumok", "PDF, DOCX, DOC, PPTX"),
        (ft.Icons.TABLE_CHART_OUTLINED, "Táblázatok", "XLSX, XLS, CSV"),
        (ft.Icons.ARTICLE_OUTLINED, "Webfájlok és szöveg", "HTML, HTM, XML, RSS"),
        (ft.Icons.MENU_BOOK_OUTLINED, "E-könyvek", "EPUB, AZW3, MOBI, FB2"),
        (ft.Icons.DATA_OBJECT, "Notebook és adatok", "IPYNB, JSON"),
        (ft.Icons.IMAGE_OUTLINED, "Képek", "PNG, JPG, JPEG, GIF, BMP, WEBP"),
        (ft.Icons.AUDIO_FILE_OUTLINED, "Hangfájlok", "MP3, WAV, M4A"),
        (ft.Icons.MAIL_OUTLINE, "Outlook-üzenetek", "MSG"),
        (ft.Icons.FOLDER_ZIP_OUTLINED, "Archívumok", "ZIP"),
    ]
    half = (len(formats) + 1) // 2
    BUBBLE_W = 540
    formats_bubble = ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Icon(ft.Icons.AUTO_AWESOME, size=16, color=CYAN),
                ft.Text("Konvertálható fájltípusok", size=14, weight=ft.FontWeight.BOLD, color=FG),
            ], spacing=8),
            ft.Divider(height=1, color=BORDER),
            ft.Row([
                ft.Column([format_row(*f) for f in formats[:half]], spacing=12, tight=True, width=240),
                ft.Column([format_row(*f) for f in formats[half:]], spacing=12, tight=True, width=240),
            ], spacing=16, vertical_alignment=ft.CrossAxisAlignment.START),
        ], spacing=12, tight=True),
        width=BUBBLE_W,
        padding=ft.Padding(left=18, right=18, top=14, bottom=16),
        bgcolor=BG_DARK,
        border=ft.Border.all(1, ft.Colors.with_opacity(0.35, CYAN)),
        border_radius=16,
        shadow=ft.BoxShadow(blur_radius=24, spread_radius=1, color=ft.Colors.with_opacity(0.5, "#000000"),
                            offset=ft.Offset(0, 8)),
        visible=False,
    )
    page.overlay.append(formats_bubble)

    info_tile = ft.Container(
        content=ft.Icon(ft.Icons.INFO_OUTLINE, size=24, color=CYAN),
        width=42, height=42, alignment=ft.Alignment.CENTER, border_radius=21,
        bgcolor=ft.Colors.with_opacity(0.10, CYAN),
        border=ft.Border.all(1.5, ft.Colors.with_opacity(0.45, CYAN)),
        animate=ft.Animation(150, ft.AnimationCurve.EASE_OUT),
    )

    def show_formats(e):
        # A csempe bal felső sarka ablak-koordinátában; a buborék alatta nyílik, ablakon belül tartva.
        x = e.global_position.x - e.local_position.x
        y = e.global_position.y - e.local_position.y
        max_left = (page.width or page.window.width or 770) - BUBBLE_W - 12
        formats_bubble.left = max(12, min(x, max_left))
        formats_bubble.top = y + 42 + 8
        formats_bubble.visible = True
        info_tile.bgcolor = ft.Colors.with_opacity(0.20, CYAN)
        page.update()

    def hide_formats(_e):
        formats_bubble.visible = False
        info_tile.bgcolor = ft.Colors.with_opacity(0.10, CYAN)
        page.update()

    info_button = ft.GestureDetector(
        content=info_tile,
        on_enter=show_formats,
        on_exit=hide_formats,
        mouse_cursor=ft.MouseCursor.HELP,
    )

    def platform_tile(name: str, slug: str | None, color: str, tooltip: str) -> ft.Container:
        logo = (ft.Image(
            src=f"brands/{slug}.svg", width=21, height=21,
            fit=ft.BoxFit.CONTAIN, semantics_label=name,
        ) if slug else ft.Icon(ft.Icons.LANGUAGE, size=22, color=color))

        def on_hover(e):
            hovered = e.data is True
            e.control.bgcolor = ft.Colors.with_opacity(0.16 if hovered else 0.07, color)
            e.control.border = ft.Border.all(1, ft.Colors.with_opacity(0.55 if hovered else 0.2, color))
            e.control.update()

        return ft.Container(
            content=logo, width=38, height=38, alignment=ft.Alignment.CENTER,
            border_radius=11, bgcolor=ft.Colors.with_opacity(0.07, color),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.2, color)),
            tooltip=tooltip, on_hover=on_hover, animate=ft.Animation(150, ft.AnimationCurve.EASE_OUT),
        )

    platforms_row = ft.Row([
        ft.Column([
            ft.Text("Konvertálható", size=13, weight=ft.FontWeight.W_600, color=FG),
            ft.Text("fájlok és linkek", size=11, color=FG_DIM),
        ], spacing=0, tight=True),
        ft.Container(width=1, height=28, bgcolor=BORDER, margin=ft.Margin(left=6, right=6, top=0, bottom=0)),
        info_button,
        platform_tile("TikTok", "tiktok", "#F4EEE8", "TikTok · videók"),
        platform_tile("YouTube", "youtube", "#FF5D5D", "YouTube · videók és feliratok"),
        platform_tile("Facebook", "facebook", "#5B9BFF", "Facebook · videók és Reels · fb.watch"),
        platform_tile("Instagram", "instagram", "#F58AB4", "Instagram · videók és Reels"),
        platform_tile("X / Twitter", "x", "#F4EEE8", "X / Twitter · videók"),
        platform_tile("Weboldalak", None, CYAN, "Weboldalak · cikkek és oldalak"),
    ], spacing=8, height=48, scroll=ft.ScrollMode.AUTO,
       vertical_alignment=ft.CrossAxisAlignment.CENTER)

    copy_label = ft.Text("", size=11, color=GREEN)

    output_path_label = ft.Text(
        str(current_output[0]),
        size=11,
        color=FG_DIM,
        expand=True,
        no_wrap=True,
        overflow=ft.TextOverflow.ELLIPSIS,
    )

    def browse_output(e):
        folder = open_folder_dialog()
        if folder:
            folder.mkdir(parents=True, exist_ok=True)
            current_output[0] = folder
            save_settings(output_dir=str(folder))
            output_path_label.value = str(folder)
            refresh_retry_button()
            update_link_count()

    spinner = ft.ProgressRing(
        width=20, height=20,
        stroke_width=2,
        color=FG,
        visible=False,
    )

    def copy_log():
        lines = [c.value for c in status_log.controls if isinstance(c, ft.Text)]  # type: ignore[union-attr]
        text = "\n".join(lines)
        subprocess.Popen(["clip"], stdin=subprocess.PIPE).communicate(
            input=("﻿" + text).encode("utf-16-le")
        )
        copy_label.value = "kimásolva vágólapra"
        page.update()

    page.add(
        platforms_row,
        ft.Row([
            ft.Button(
                "Fájl(ok) kiválasztása",
                icon=ft.Icons.UPLOAD_FILE,
                style=btn_style,
                on_click=pick_files,
            ),
            ft.Button(
                "Törlés",
                icon=ft.Icons.DELETE_OUTLINE,
                style=btn_style,
                on_click=clear_files,
            ),
            ft.Container(expand=True),
            ocr_checkbox,
        ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
        files_tags_container,
        audio_settings_row,
        eta_container,
        ft.Row([url_field]),
        ft.Row([
            ft.Button(
                "Linklista (.txt) betöltése",
                icon=ft.Icons.PLAYLIST_ADD,
                style=btn_style,
                on_click=load_links,
            ),
            ft.Button(
                "Linkek törlése",
                icon=ft.Icons.CLEAR_ALL,
                style=btn_style,
                on_click=clear_links,
            ),
            retry_btn,
            link_count_label,
        ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ft.Row([links_field]),

        ft.Divider(height=8, color=BORDER),
        ft.Row([
            ft.Icon(ft.Icons.FOLDER_OPEN, size=16, color=FG_DIM),
            output_path_label,
            ft.Button(
                "Kimenet mappa",
                icon=ft.Icons.DRIVE_FOLDER_UPLOAD,
                style=btn_style,
                on_click=browse_output,
            ),
        ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ft.Row([
            ft.Button(
                "Konvertálás",
                icon=ft.Icons.PLAY_ARROW,
                style=convert_btn_style,
                on_click=convert,
            ),
            spinner,
        ], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),

        ft.Divider(height=8, color=BORDER),
        ft.Row([
            ft.Text("console", size=14, weight=ft.FontWeight.W_600, color=FG_DIM),
            ft.IconButton(
                icon=ft.Icons.CONTENT_COPY,
                icon_size=15,
                icon_color=FG_DIM,
                tooltip="Másolás vágólapra",
                style=ft.ButtonStyle(padding=ft.Padding(4, 4, 4, 4)),
                on_click=lambda e: copy_log(),
            ),
            copy_label,
        ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ft.Container(
            content=status_log,
            bgcolor=BG_DARK,
            border=border_style,
            border_radius=6,
            padding=10,
            expand=True,
        ),
    )


if __name__ == "__main__":
    ft.run(main)
