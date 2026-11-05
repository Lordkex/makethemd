# MakeThemd

A Windows desktop app that **turns files and links into Markdown (`.md`)**, from documents and
e-books to audio files, YouTube videos and social media clips.

The interface is available in **English and Hungarian**. Use the language switch in the top-right
corner to change it at any time.

> **Origin:** MakeThemd started as a fork of Microsoft's
> **[MarkItDown](https://github.com/microsoft/markitdown)**. A modified version of MarkItDown
> (`packages/markitdown/`) does the conversion. MakeThemd adds a desktop GUI, audio and video
> transcription, link-list batch processing and local OCR on top of it.
> See [Origin and credits](#origin-and-credits).

## Features

- **Documents:** PDF, Word (DOCX/DOC), Excel (XLSX/XLS/CSV), PowerPoint (PPTX), HTML, EPUB,
  JSON/XML, Jupyter notebooks, Outlook `.msg`, ZIP, images.
- **E-books:** AZW3, MOBI, FB2, DjVu (via Calibre's `ebook-convert`).
- **Audio → text:** MP3/WAV/M4A transcription with [Whisper](https://github.com/openai/whisper)
  on GPU or CPU.
- **YouTube:** downloads the existing captions with
  [youtube-transcript-api](https://github.com/jdepoix/youtube-transcript-api). This is fast and
  doesn't need Whisper.
- **TikTok / Facebook / Instagram / X:** tries the embedded captions first. If there are none, it
  downloads the audio with [yt-dlp](https://github.com/yt-dlp/yt-dlp) and transcribes it with
  Whisper.
- **Facebook fallback:** if the direct download fails, it fetches the audio track of the public
  video through the free [FDOWN](https://fdown.tools/) service, converts it to MP3 with ffmpeg and
  transcribes it locally. In this case the video URL is sent to FDOWN.
- **Link list:** batch processing with one URL per line. It skips links that already have an output
  file and links that appear twice in the list.
- **Retry:** failed links go into `_failed_links.txt` in the output folder, with the reason and the
  date. The **Retry failed** button loads them back into the link list.
- **Gentle YouTube requests:** waits 4 seconds between videos. If YouTube still blocks caption
  requests, the remaining YouTube links are deferred, and you can transcribe them with Whisper
  later.
- **Local image OCR (optional):** extracts text from embedded images with
  [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR). No API key is needed.

By default the results go into the **`output/`** folder.

---

## Requirements

| Tool | Needed for | Install |
|---|---|---|
| **Python 3.10–3.14** | the app itself | [python.org](https://www.python.org/downloads/) (tick “Add to PATH”) |
| **ffmpeg** | audio and video processing | `winget install Gyan.FFmpeg` |
| **Node.js** or **Deno** | YouTube downloads with yt-dlp (without one you may get `HTTP 403`) | `winget install OpenJS.NodeJS` |
| **Calibre** (`ebook-convert`) | AZW3/MOBI/FB2/DjVu conversion | `winget install calibre` |
| **exiftool** | image metadata (optional) | `winget install exiftool` |

> **ffmpeg path:** the top of `app.py` adds the WinGet `Gyan.FFmpeg` install folder
> (`ffmpeg-8.1.1-full_build`) to `PATH`. If you have a different version or location, edit the path
> there. If `ffmpeg -version` already works in your terminal, you don't need to change anything.

---

## Installation

```powershell
git clone https://github.com/Lordkex/makethemd.git
cd makethemd
```

**1. Dependencies**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

**2. PyTorch (for Whisper transcription)**

With an NVIDIA GPU (recommended, CUDA 12.8):
```powershell
python -m pip install torch --index-url https://download.pytorch.org/whl/cu128
```
Without a GPU (transcription is slower):
```powershell
python -m pip install torch
```
The app detects on its own whether a usable GPU is available.

**3. The modified MarkItDown (editable install)**
```powershell
python -m pip install -e "packages/markitdown[all]"
```

---

## Running

```powershell
start_makethemd.bat
```
or directly:
```powershell
python app.py
```

`start_makethemd.bat` uses the project's `.venv\Scripts\python.exe` when available and
updates the downloader packages (`yt-dlp[default]`, `youtube-transcript-api`)
once a week. If the app runs into an error that points to an outdated downloader (e.g.
`403 Forbidden`), the update runs on the next start, and if the new version fails to load, the
previous one is restored. `python app.py` skips this step; you can run it by hand with
`python updater.py`.

### Usage

1. **Select files**: add the files you want to convert.
2. **Links**: paste one or more video URLs (one per line), or load a `.txt` file.
3. **Local OCR for images**: optional, see [Local image OCR](#local-image-ocr-optional).
4. **Convert**: the results go into the output folder.

The log shows how each link was handled: `[captions]` (fast) or `[whisper]` (transcribed).

---

## Whisper models

You can pick the model in the app. The default is **turbo**.

| Model | Speed | Quality | Notes |
|---|---|---|---|
| tiny / base | very fast | basic | short clips or bulk jobs |
| small / medium | slower | better | mainly on GPU |
| turbo | fast | very good | **default**, GPU recommended |
| large | slowest | best | GPU only |

The model downloads on first use (about 150 MB–3 GB) and is cached after that.

---

## Local image OCR (optional)

OCR processes embedded images locally and appends the recognised text to the end of the Markdown
output. It supports images embedded in DOCX, PPTX and XLSX files, images in PDFs (via
[PyMuPDF](https://github.com/pymupdf/PyMuPDF)), and standalone PNG, JPG, TIFF, BMP and WebP files.

### Automatic setup in the project environment

OCR uses the project's existing `.venv` (including Python 3.12). A separate `.venv-ocr`
environment and `uv` are no longer needed. Checking the OCR box immediately starts a background
check of PaddleOCR, PaddlePaddle, Pillow, PyMuPDF and the document readers for PDF, DOCX, PPTX and
XLSX. Missing dependencies are installed automatically from `requirements-ocr.txt` into `.venv`,
including this repository's MarkItDown with its document extras. Progress appears in the app log.
The checkbox is temporarily disabled during setup. Conversion waits for setup to finish, and
also checks setup when an enabled OCR selection has been restored. Starting the app with OCR
disabled does not install OCR packages.

For supported files, document reading and image OCR run together in a fresh `.venv` subprocess.
This makes newly installed readers available immediately, even if the GUI previously cached
a missing-dependency error. Models download on the first actual recognition request.

PDFs are processed page by page. Readable text is extracted directly; broken character
encodings (including `(cid:...)` glyph IDs and unmapped Type3 fonts) and scanned pages use
whole-page OCR. Recognized page text replaces the faulty extraction in the original page
order. PDF page headings identify the source page. On readable pages, text in embedded
diagrams is still recognized and included with that page; duplicate images and image masks
are skipped. The table formatter runs only when actual ruled tables are detected.

Completed whole-page recognitions are cached under `.ocr-cache/pdf-pages`, keyed by the
PDF contents and OCR settings. Retrying a failed conversion reuses completed pages; changing
the PDF invalidates its cache. A page that cannot be recognized stops conversion with its
page number instead of silently producing broken text.
The live progress panel shows the current document, processing stage and elapsed time.
PDF image discovery reports pages scanned; recognition reports completed images out of the
total, with a progress bar. Model loading/downloading uses an indeterminate bar and a clock
that keeps updating while the worker is busy.
For PDFs, the panel reports the current page, total pages and whether it is reading text,
running whole-page OCR or reusing a cached page.

If `.venv` is absent, the OCR setup creates it with the Python running the app, retaining access
to system packages for older installations that installed the app globally. An existing
but broken `.venv` is reported rather than overwritten. Use a Python version supported by
PaddlePaddle (Python 3.12 or 3.13 on 64-bit Windows); an incompatible interpreter is not
automatically replaced. The system Python is never an installation target.

The first run needs internet access for packages and models and can take several minutes.
Models are cached in `.ocr-cache`; subsequent runs can work offline. Failed installations
are retried on the next OCR request. Already available dependencies are not reinstalled.

With an NVIDIA GPU (driver 560 or newer), setup replaces the CPU build of PaddlePaddle in `.venv`
with its CUDA 12.6 build, and PaddleOCR then uses the GPU on its own. This is a one-time download
that takes about 3 GB of disk space. It makes whole-page OCR about 70 times faster: roughly 1 s
instead of 60 s per dense page, measured on an RTX 3080 and a Ryzen 5 5600X. If the download fails,
OCR keeps working on the CPU and setup tries again the next time the app starts.

Test:
```powershell
.\.venv\Scripts\python.exe -m paddleocr_tools.test_ocr
```

### Troubleshooting

- **Incomplete project environment:** repair or recreate `.venv`, then reinstall the app dependencies.
- **Installation fails:** the log includes pip's error. Check the connection and retry OCR.
- **`No matching distribution found for paddlepaddle`:** use Python 3.12 or 3.13 for `.venv`
  on 64-bit Windows. The app cannot install a wheel unsupported by the current Python.
- **Manual installation / repair:** run
  `.\.venv\Scripts\python.exe -m pip install -r requirements-ocr.txt` from the project root.
- **Model download fails:** check your internet connection, proxy and firewall.
- **No text recognised:** try a larger, sharper, less compressed image.

---

## Tests

```powershell
python -m unittest discover tests
```

---

## Origin and credits

MakeThemd is a fork of **[microsoft/markitdown](https://github.com/microsoft/markitdown)**
(© Microsoft Corporation, MIT License). The `packages/markitdown/` folder contains a modified
version of it. The original license ([LICENSE](LICENSE)) and the third-party notices in
`packages/markitdown/ThirdPartyNotices.md` apply to it.

Other projects used:

- [Flet](https://github.com/flet-dev/flet): desktop GUI
- [Whisper](https://github.com/openai/whisper) and [PyTorch](https://github.com/pytorch/pytorch): speech recognition
- [yt-dlp](https://github.com/yt-dlp/yt-dlp): video and audio downloads
- [youtube-transcript-api](https://github.com/jdepoix/youtube-transcript-api): YouTube captions
- [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) and [PaddlePaddle](https://github.com/PaddlePaddle/Paddle): local OCR
- [PyMuPDF](https://github.com/pymupdf/PyMuPDF): image extraction from PDFs
- [Simple Icons](https://github.com/simple-icons/simple-icons): brand icons (CC0-1.0, see `assets/brands/`)

## Disclaimer

Only use the app on content you have the right to download and process, and follow the terms of
service of the platforms involved (YouTube, Facebook, TikTok, Instagram, X). MakeThemd is an
independent project. It is not affiliated with Microsoft or with any of the services mentioned
above.
