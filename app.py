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
from output_utils import choose_output_path
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
    "vimeo.com",
    "dailymotion.com",
    "twitch.tv",
)


def is_media_site(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return any(site in host for site in YT_DLP_SITES)


def is_youtube_url(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return "youtube.com" in host or "youtu.be" in host


def ensure_real_transcript(url: str, text: str) -> None:
    """YouTube-linkeknél ellenőrzi, hogy tényleg készült-e átirat.

    A markitdown, ha nem éri el a feliratot (pl. a YouTube blokkolja az IP-t,
    vagy a videónak nincs felirata), csendben visszaesik a weboldal szövegére
    (menü/lábléc), és azt "sikeres" kimenetként adja vissza. Ilyenkor inkább
    hibát dobunk, hogy ne szülessen félrevezető, üres .md fájl.
    """
    if is_youtube_url(url) and "### Transcript" not in text:
        raise RuntimeError(
            "nem sikerült feliratot/átiratot lekérni. "
            "Legvalószínűbb ok: TÚL SOK KÉRÉS a YouTube felirat-API felé, "
            "ezért a YouTube átmenetileg blokkolta az IP-címedet (IpBlocked). "
            "Megoldás: válts hálózatot (pl. mobilnetről Wi-Fi-re vagy fordítva), "
            "vagy várj néhány órát, és ne futtass egyszerre sok linket. "
            "(Ritkább ok: a videónak egyáltalán nincs felirata.)"
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


def download_media_audio(url: str, tmpdir: str) -> Path:
    """yt-dlp-vel letölti a videót (hanggal) a tmpdir-be, és visszaadja az útvonalat.

    A Whisper az ffmpeg-en keresztül a videófájlból is kinyeri a hangot, ezért nem
    konvertálunk külön audióvá. A formátum-string a TikTok 'download' (vízjelmentes,
    hangos) változatát preferálja; más oldalakon a bestaudio/best lép életbe.
    """
    import yt_dlp

    ydl_opts = {
        "format": "download/bestaudio/best",
        "outtmpl": str(Path(tmpdir) / "%(id)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "ffmpeg_location": FFMPEG_BIN,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:  # type: ignore[arg-type]
        info = ydl.extract_info(url, download=True)
        downloads = info.get("requested_downloads") or []
        if downloads and downloads[0].get("filepath"):
            path = Path(downloads[0]["filepath"])
        else:
            path = next(Path(tmpdir).iterdir())

    # A markitdown csak .mp3/.m4a/.mp4/.wav kiterjesztést fogad el; a whisper/ffmpeg a
    # tényleges tartalom alapján dekódol, így a kiterjesztés átnevezése ártalmatlan.
    if path.suffix.lower() not in {".mp3", ".m4a", ".mp4", ".wav"}:
        renamed = path.with_suffix(".mp4")
        path.rename(renamed)
        path = renamed
    return path


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
        opts = {"quiet": True, "no_warnings": True, "skip_download": True, "write_pages": True}
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

    probe_opts = {"quiet": True, "no_warnings": True, "skip_download": True}
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


def main(page: ft.Page):
    page.title = "MakeThemd"
    page.window.width = 770
    page.window.height = 820
    page.bgcolor = BG
    page.padding = 24

    md = MarkItDown()
    selected_files: list[Path] = []
    current_output: list[Path] = [OUTPUT]

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
        active = [
            ln.strip() for ln in (links_field.value or "").splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
        link_count_label.value = f"{len(active)} link betöltve" if active else ""
        has_media_link = any(is_media_site(ln) for ln in active)
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
            is_media_site(ln.strip())
            for ln in (links_field.value or "").splitlines()
            if ln.strip() and not ln.strip().startswith("#")
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
        return f"~{int(s/60)+1} perc"

    def fmt_duration(s: float) -> str:
        m, sec = divmod(int(s), 60)
        return f"{m}:{sec:02d}"

    def sanitize_filename(name: str) -> str:
        safe = re.sub(r"[^a-zA-Z0-9_.-]", "_", name)
        return safe.strip("_-")[:120] or "output"

    def resize_window():
        n = sum(1 for f in selected_files if f.suffix.lower() in AUDIO_EXTENSIONS)
        # 820 alap (nincs audio sor); +80 a settings+ETA sornak, +28 minden további fájlhoz
        page.window.height = 820 if n == 0 else min(900 + (n - 1) * 28, 1050)
        page.update()

    def update_eta(_e=None):
        audio_files = [f for f in selected_files if f.suffix.lower() in AUDIO_EXTENSIONS]
        if not audio_files:
            eta_container.visible = False
            resize_window()
            return

        model = model_dd.value or "base"
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

    def convert(e):
        status_log.controls.clear()
        spinner.visible = True
        copy_label.value = ""
        page.update()

        lang = language_dd.value if language_dd.value != "auto" else None
        model = model_dd.value or "base"

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
                    try:
                        result = md.convert(url_value)
                        ensure_real_transcript(url_value, result.text_content)
                        resolved_path.write_text(result.text_content, encoding="utf-8")
                        log(f"✓  URL  →  {resolved_path.name}", GREEN)
                        converted += 1
                    except Exception as ex:
                        log(f"✗  URL: {ex}", RED)
                        errors += 1

            link_list = [ln.strip() for ln in (links_field.value or "").splitlines()]
            link_list = [ln for ln in link_list if ln and not ln.startswith("#")]
            n_links = len(link_list)

            def _already_converted(name: str) -> bool:
                if (out_dir / f"{name}.md").exists():
                    return True
                return any(out_dir.glob(f"???_{name}.md"))

            for i, url in enumerate(link_list, 1):
                short = url if len(url) <= 55 else url[:54] + "…"
                basename = url_to_basename(url)

                if _already_converted(basename):
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

                live = ft.Text(f"⏳  [{i}/{n_links}]  {short}", size=13, color=FG_DIM, font_family="monospace")
                status_log.controls.append(live)
                safe_update()

                tmpdir = None
                method = ""
                try:
                    if is_media_site(url):
                        # 1) gyors út: kész felirat (Whisper nélkül)
                        live.value = f"💬  [{i}/{n_links}]  {short}  — felirat keresése..."
                        try:
                            live.update()
                        except Exception:
                            pass
                        out_text = fetch_media_captions(url, lang)

                        if out_text:
                            out_text = "### Felirat:\n\n" + out_text
                            method = " [felirat]"
                        else:
                            # 2) tartalék: hang letöltése + Whisper-átírás
                            live.value = f"⬇  [{i}/{n_links}]  {short}  — nincs felirat, hang letöltése..."
                            try:
                                live.update()
                            except Exception:
                                pass
                            tmpdir = tempfile.mkdtemp(prefix="mtd_")
                            audio_path = download_media_audio(url, tmpdir)

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

                            result = md.convert(
                                str(audio_path),
                                whisper_language=lang,
                                whisper_model=model,
                                whisper_progress_fn=_on_link_progress,
                            )
                            out_text = result.text_content
                            method = " [whisper]"
                    else:
                        out_text = md.convert(url).text_content
                        ensure_real_transcript(url, out_text)

                    out_path.write_text(out_text, encoding="utf-8")
                    status_log.controls.remove(live)
                    log(f"✓  [{i}/{n_links}]  {short}  →  {out_path.name}{method}", GREEN)
                    converted += 1
                except Exception as ex:
                    try:
                        status_log.controls.remove(live)
                    except ValueError:
                        pass
                    log(f"✗  [{i}/{n_links}]  {short}: {ex}", RED)
                    errors += 1
                finally:
                    if tmpdir:
                        shutil.rmtree(tmpdir, ignore_errors=True)

            spinner.visible = False
            if converted == 0 and errors == 0 and skipped == 0:
                log("Nincs kiválasztott fájl vagy URL.", YELLOW)
            else:
                skip_str = f", {skipped} kihagyva" if skipped else ""
                summary_color = RED if errors else CYAN
                log(
                    f"\nKész: {converted} sikeres, {errors} hiba{skip_str}  →  {out_dir}",
                    summary_color,
                )
                if errors:
                    log(
                        f"⚠  {errors} elem nem készült el (lásd a fenti ✗ sorokat) – "
                        "ezekhez nem jött létre valós átirat.",
                        RED,
                    )
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

        threading.Thread(target=run, daemon=True).start()

    def format_row(icon: str, label: str, exts: str) -> ft.Row:
        return ft.Row([
            ft.Text(icon, size=14),
            ft.Column([
                ft.Text(label, size=12, weight=ft.FontWeight.W_600, color=FG),
                ft.Text(exts, size=11, color=FG_DIM),
            ], spacing=1, tight=True),
        ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.START)

    info_dialog = ft.AlertDialog(
        bgcolor=BG_DARK,
        title=ft.Text("Támogatott formátumok", color=FG, weight=ft.FontWeight.BOLD),
        content=ft.Column([
            format_row("📄", "Dokumentumok", "PDF, DOCX, DOC, PPTX"),
            format_row("📊", "Táblázatok",   "XLSX, XLS, CSV"),
            format_row("🌐", "Web / szöveg", "HTML, HTM, XML, RSS, EPUB"),
            format_row("📓", "Notebook",     "IPYNB, JSON"),
            format_row("🖼️", "Kép",          "PNG, JPG, JPEG, GIF, BMP, WEBP"),
            format_row("🎵", "Audio",        "MP3, WAV, M4A  (ffmpeg szükséges)"),
            format_row("📬", "Outlook",      "MSG"),
            format_row("🗜️", "Archívum",     "ZIP"),
            format_row("▶️", "URL",          "YouTube link"),
            format_row("🎬", "Videó-linkek", "TikTok, Instagram, X, Vimeo (hang → átírás)"),
            format_row("📋", "Linklista",    "TXT, soronként egy URL"),
        ], spacing=10, tight=True, width=320),
        actions=[
            ft.TextButton("Bezárás", style=ft.ButtonStyle(color=FG),
                          on_click=lambda e: close_info(e)),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
        shape=ft.RoundedRectangleBorder(radius=8),
        inset_padding=ft.Padding(left=60, right=60, top=40, bottom=40),
    )
    page.overlay.append(info_dialog)

    def show_info(e):
        info_dialog.open = True
        page.update()

    def close_info(e):
        info_dialog.open = False
        page.update()

    copy_label = ft.Text("", size=11, color=GREEN)

    output_path_label = ft.Text(
        str(OUTPUT),
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
            output_path_label.value = str(folder)
            page.update()

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
        ft.Row([
            ft.Text("Konvertálható fájlok", size=14, weight=ft.FontWeight.W_600, color=FG_DIM),
            ft.IconButton(
                icon=ft.Icons.INFO_OUTLINE,
                icon_size=16,
                icon_color=FG_DIM,
                style=ft.ButtonStyle(padding=ft.Padding(4, 4, 4, 4)),
                on_click=lambda e: show_info(e),
            ),
        ], spacing=2, vertical_alignment=ft.CrossAxisAlignment.CENTER),
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
