# MakeThemd

Asztali (Windows) alkalmazás, amely **bármilyen fájlt vagy linket Markdown (`.md`) szöveggé alakít**.
A Microsoft [MarkItDown](https://github.com/microsoft/markitdown) könyvtárra épül, egy egyszerű
grafikus felülettel ([Flet](https://github.com/flet-dev/flet)) kiegészítve. Az audioátírást
[Whisper](https://github.com/openai/whisper) és [PyTorch](https://github.com/pytorch/pytorch),
a helyi kép-OCR-t [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) és
[PaddlePaddle](https://github.com/PaddlePaddle/Paddle), a videó/link feldolgozást pedig
[yt-dlp](https://github.com/yt-dlp/yt-dlp) és
[youtube-transcript-api](https://github.com/jdepoix/youtube-transcript-api) segíti.

## Mit tud

- **Fájlok → Markdown:** PDF, Word (DOCX/DOC), Excel (XLSX/XLS/CSV), PowerPoint (PPTX), HTML, EPUB,
  JSON/XML, Jupyter notebook, Outlook `.msg`, ZIP, képek.
- **Ebook → Markdown:** AZW3, MOBI, FB2, DjVu (Calibre `ebook-convert` szükséges).
- **Audio → szöveg:** MP3/WAV/M4A átírása **[Whisper](https://github.com/openai/whisper)**rel
  (GPU-n vagy CPU-n).
- **YouTube → szöveg:** a kész felirat/átirat letöltése
  ([youtube-transcript-api](https://github.com/jdepoix/youtube-transcript-api), gyors, nem Whisper).
- **Linklista:** egy `.txt`-ben soronként megadott linkek **kötegelt** feldolgozása. Ami már megvan
  az `output/` mappában, azt kihagyja.
- **TikTok / Facebook / Instagram / X / Vimeo:** elsőként a videó **beágyazott feliratát** próbálja leszedni
  (gyors); ha nincs, [yt-dlp](https://github.com/yt-dlp/yt-dlp)-vel letölti a hangot és
  Whisperrel írja át.
- **Facebook tartalékletöltő:** ha a közvetlen letöltés nem sikerül, az ingyenes
  [FDOWN](https://fdown.tools/) szolgáltatással kéri le a nyilvános videó hangsávját,
  ffmpeg-gel valódi MP3-má alakítja, majd a kiválasztott Whisper-modellel
  (alapból **turbo**) átírja. API-kulcs és regisztráció nem szükséges.
  Az egyedi URL és a linklista is ezt az útvonalat használja; a Facebook-leírás önmagában
  nem számít kész átiratnak. A videó URL-je a tartalékletöltéskor eljut a FDOWN-hoz,
  az átírás helyben fut. A szolgáltatás elérhetősége és a Facebook-videó nyilvános hozzáférése szükséges.
- **Kép-OCR (opcionális):** a beágyazott képekből helyben,
  **[PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR)**-rel nyer ki szöveget
  (PDF-képekhez [PyMuPDF](https://github.com/pymupdf/PyMuPDF), lásd 5. pont).

Az eredmény mindig az **`output/`** mappába kerül.

---

## 1. Előfeltételek

### Python 3.10 – 3.14
Letöltés: https://www.python.org/downloads/ (telepítésnél pipáld be az „Add to PATH"-t).

> A fő alkalmazás futhat a globális Python 3.14-en. Az **opcionális PaddleOCR** külön Python 3.13-as
> `.venv-ocr` környezetben fut (lásd 5. pont) — csak akkor kell, ha OCR-t használsz.

### ffmpeg (audio/videó és TikTok-hang feldolgozásához)
```powershell
winget install Gyan.FFmpeg
```
Ellenőrzés:
```powershell
ffmpeg -version
```

> **Megjegyzés:** az `app.py` teteje (15–19. sor) az `FFMPEG_BIN`-t a WinGet Gyan.FFmpeg
> telepítési útjából építi fel (jelenleg a `ffmpeg-8.1.1-full_build` verzióval). Ha más verziód/
> helyed van, írd át ott az utat — vagy ha az ffmpeg már a rendszer PATH-ján van, ez a blokk elhagyható.

### Calibre `ebook-convert` (csak ebook formátumokhoz)
```powershell
winget install calibre
```
Ellenőrzés:
```powershell
ebook-convert --version
```
> Az `ebook-convert` nem pip csomag (a Calibre-vel jön). Az AZW3/MOBI/FB2/DjVu konverzióhoz kell.

### exiftool (képek metaadataihoz – opcionális)
```powershell
winget install exiftool
```

---

## 2. Telepítés lépésről lépésre

A projekt mappájában (`makethemd`) nyiss egy terminált, majd:

**1. Csomagok telepítése**
```powershell
python -m pip install -r requirements.txt
```

**2. PyTorch (a Whisper-átíráshoz)**

NVIDIA GPU esetén (ajánlott, gyors – CUDA 12.8):
```powershell
python -m pip install torch --index-url https://download.pytorch.org/whl/cu128
```
GPU nélkül (CPU, lassabb átírás):
```powershell
python -m pip install torch
```
> Az app automatikusan felismeri, van-e GPU, és aszerint használ CUDA-t vagy CPU-t.

**3. A helyi MarkItDown telepítése (szerkeszthető módban)**

A projekt a saját, módosított MarkItDown-ját használja a `packages/` mappából:
```powershell
python -m pip install -e "packages/markitdown[all]"
```

---

## 3. Indítás
```powershell
python app.py
```

### Használat
1. **Fájl(ok) kiválasztása** – tallózással hozzáadod a konvertálandó fájlokat.
2. **Video / Page URL** – egyetlen videó átirata vagy weboldal konvertálása; Facebook/Reels is megadható.
3. **Linklista** – beilleszted a linkeket (soronként egy), vagy a **Linklista (.txt) betöltése**
   gombbal beolvasol egy szövegfájlt.
4. **OCR képekből (lokális PaddleOCR)** – opcionális; ha bepipálod, a beágyazott képekből is
   kinyeri a szöveget (előbb telepítsd az 5. pont szerint).
5. **Konvertálás** – minden eredmény az `output/` mappába kerül.

A linkeknél a napló jelzi a használt módszert: `[felirat]` (gyors) vagy `[whisper]` (átírás).

---

## 4. Whisper modellek (audio / TikTok átíráshoz)

A felületen választható; az alapértelmezett a **turbo**.

| Modell | Sebesség | Minőség | Megjegyzés |
|---|---|---|---|
| tiny / base | nagyon gyors | alap | rövid vagy tömeges feladathoz |
| small / medium | lassabb | jobb | főleg GPU-n |
| turbo | gyors | nagyon jó | **alapértelmezett**, GPU ajánlott |
| large | leglassabb | legjobb | csak GPU-n |

Az első használatkor a kiválasztott modell letöltődik (~150 MB – 3 GB), utána gyorsítótárazva van.

---

## 5. Lokális kép-OCR – PaddleOCR (opcionális)

Az OCR a beágyazott képeket helyben, PaddleOCR-rel dolgozza fel, és a felismert szöveget a Markdown
végéhez fűzi. Nem igényel API-kulcsot és nem használ fizetős szolgáltatást.

### Külön OCR-környezet telepítése

A PaddlePaddle jelenleg nem ad ki Python 3.14-es Windows-csomagot, ezért az OCR egy külön Python
3.13-as subprocessben fut, és JSON-on át adja vissza az eredményt. A projekt gyökerében:

```powershell
uv venv --python 3.13 .venv-ocr
uv pip install --python .venv-ocr\Scripts\python.exe -r requirements.txt
```

Az OCR-környezetet nem kell aktiválni — az app automatikusan a `.venv-ocr\Scripts\python.exe`
workert indítja, miközben maga a globális Python 3.14-en fut.

### Mit támogat

DOCX, PPTX, XLSX beágyazott képei; PDF-ben a beágyazott képeket a PyMuPDF nyeri ki; valamint önálló
PNG, JPG, TIFF, BMP, WebP képfájlok. Ha be van kapcsolva, a kimenet végén ilyen szekció jelenik meg:

```markdown
## OCR-rel kinyert szöveg képekből

### Kép 1

A képről felismert szöveg...
```

### Első futtatás és teszt

Az első OCR-inicializálás letölti a szükséges modelleket (ehhez internet kell); utána offline is
működik. A modellek a projekt `.ocr-cache` könyvtárába kerülnek (`.ocr-cache` és `.venv-ocr` nincs
verziókezelés alatt). Teszt:

```powershell
python paddleocr_tools\test_ocr.py
```

### Hibaelhárítás

- **Az OCR-környezet nem található:** futtasd újra a fenti két `uv` parancsot.
- **`No matching distribution found for paddlepaddle`:** ellenőrizd, hogy az `uv venv` valóban
  Python 3.13-as `.venv-ocr` környezetet hozott létre.
- **Sikertelen modellletöltés:** ellenőrizd az internetkapcsolatot/proxyt/tűzfalat, majd próbáld újra.
- **Nincs felismert szöveg:** használj nagyobb, élesebb, kevésbé tömörített képet.
