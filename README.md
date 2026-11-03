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

`start_makethemd.bat` updates the downloader packages (`yt-dlp[default]`, `youtube-transcript-api`)
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

### Separate OCR environment

PaddlePaddle has no Python 3.14 package for Windows, so OCR runs as a subprocess in a separate
Python 3.13 environment. From the project root ([uv](https://github.com/astral-sh/uv) required):

```powershell
uv venv --python 3.13 .venv-ocr
uv pip install --python .venv-ocr\Scripts\python.exe -r requirements.txt
```

You don't need to activate it. The app starts `.venv-ocr\Scripts\python.exe` automatically.
The first run downloads the OCR models into `.ocr-cache`, and after that OCR also works offline.

Test:
```powershell
python paddleocr_tools\test_ocr.py
```

### Troubleshooting

- **OCR environment not found:** run the two `uv` commands above again.
- **`No matching distribution found for paddlepaddle`:** check that `.venv-ocr` really uses
  Python 3.13.
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
