import logging
import os
import re
import subprocess
import threading
import time
import tkinter as tk
from tkinter import filedialog
from pathlib import Path

local_appdata = os.environ.get("LOCALAPPDATA", "")
FFMPEG_BIN = str(
    Path(local_appdata) / "Microsoft" / "WinGet" / "Packages" /
    "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe" / "ffmpeg-8.1.1-full_build" / "bin"
)
if FFMPEG_BIN not in os.environ["PATH"]:
    os.environ["PATH"] = FFMPEG_BIN + os.pathsep + os.environ["PATH"]

import flet as ft
from markitdown import MarkItDown
from ocr_utils import append_image_ocr, check_ocr_environment

# Importok után állítjuk be, hogy a pdfminer saját setLevel-jeit felülírjuk
logging.getLogger("pdfminer").setLevel(logging.ERROR)
logging.getLogger("pdfminer").propagate = False

OUTPUT = Path("output")
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


def main(page: ft.Page):
    page.title = "MakeThemd"
    page.window.width = 770
    page.window.height = 620
    page.bgcolor = BG
    page.padding = 24

    md = MarkItDown()
    selected_files: list[Path] = []

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
            ft.dropdown.Option("base",  "base  — gyors (ajánlott)"),
            ft.dropdown.Option("small", "small — lassabb, pontosabb"),
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
        label="OCR képekből (lokális PaddleOCR)",
        value=False,
        active_color=GREEN,
        check_color=BG_DARK,
        label_style=ft.TextStyle(color=FG),
    )

    tags_row = ft.Row(wrap=True, spacing=6, run_spacing=6)

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

    def log(msg: str, color=FG):
        status_log.controls.append(
            ft.Text(msg, color=color, size=13, font_family="monospace")
        )
        page.update()

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
        has_audio = any(f.suffix.lower() in AUDIO_EXTENSIONS for f in selected_files)
        audio_settings_row.visible = has_audio
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
        # 620 alap (nincs audio sor); +80 a settings+ETA sornak, +28 minden további fájlhoz
        page.window.height = 620 if n == 0 else min(700 + (n - 1) * 28, 850)
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

            if use_ocr:
                try:
                    check_ocr_environment()
                except Exception as ex:
                    spinner.visible = False
                    log(f"PaddleOCR nem indítható: {ex}", RED)
                    log("Lásd a SETUP.md PaddleOCR telepítési útmutatóját.", YELLOW)
                    return

            for path in selected_files:
                out_path = OUTPUT / (path.stem + ".md")
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
                        page.update()

                        def _on_progress(msg, ctrl=live_ctrl):
                            ctrl.value = msg
                            ctrl.update()  # csak ezt a sort frissíti, nem az egész lapot

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
                try:
                    result = md.convert(url_value)
                    parsed_url = url_value.replace("https://", "").replace("http://", "")
                    out_name = sanitize_filename(parsed_url)
                    out_path = OUTPUT / f"{out_name}.md"
                    out_path.write_text(result.text_content, encoding="utf-8")
                    log(f"✓  URL  →  {out_path.name}", GREEN)
                    converted += 1
                except Exception as ex:
                    log(f"✗  URL: {ex}", RED)
                    errors += 1

            spinner.visible = False
            if converted == 0 and errors == 0:
                log("Nincs kiválasztott fájl vagy URL.", YELLOW)
            else:
                log(
                    f"\nKész: {converted} sikeres, {errors} hiba  →  output/ mappa",
                    CYAN,
                )

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
        ]),
        ft.Container(
            content=tags_row,
            padding=ft.Padding(left=0, right=0, top=4, bottom=4),
        ),

        ft.Divider(height=8, color=BORDER),
        audio_settings_row,
        eta_container,
        ft.Row([url_field]),
        ocr_checkbox,

        ft.Divider(height=8, color=BORDER),
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
            ft.Text("Napló", size=14, weight=ft.FontWeight.W_600, color=FG_DIM),
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


ft.run(main)
