# Makethemd – Beállítási útmutató

## 1. Előfeltételek

### Python
Python 3.10–3.14 szükséges.  
Letöltés: https://www.python.org/downloads/

> A fő alkalmazás használhatja a globális Python 3.14-et. A lokális PaddleOCR
> külön Python 3.13-as `.venv-ocr` worker környezetben fut.

### ffmpeg (audio/video konverzióhoz)
```bash
winget install ffmpeg
```
Vagy: https://ffmpeg.org/download.html → Windows → gyan.dev build → csomagold ki, add hozzá `C:\ffmpeg\bin` a PATH-hoz.

Ellenőrzés:
```bash
ffmpeg -version
```

### Calibre `ebook-convert` (ebook konverzióhoz)
```bash
winget install calibre
```
Vagy: https://calibre-ebook.com/download
Ellenőrzés:
```bash
ebook-convert --version
```

> Frissítésnél is győződj meg róla, hogy Calibre telepítve van és az `ebook-convert` futtatható a PATH-on, mert az ebook konverzióhoz szükséges.

### exiftool (képek metaadataihoz – opcionális)
```bash
winget install exiftool
```

---

## 2. Függőségek telepítése

### Alap csomagok
```bash
python -m pip install -r requirements.txt
```

A könyvformátumok (`.azw3`, `.mobi`, `.fb2`) konvertálásához külön Calibre telepítése szükséges, mivel az `ebook-convert` nem pip csomag.

### PyTorch – NVIDIA GPU esetén (ajánlott, CUDA 12.8)
```bash
python -m pip install torch --index-url https://download.pytorch.org/whl/cu128
```

### PyTorch – CPU esetén (lassabb audio átírás)
```bash
python -m pip install torch
```

> Az alkalmazás automatikusan detektálja, hogy van-e elérhető GPU, és annak megfelelően használja a CUDA-t vagy a CPU-t.

---

## 3. A projekt lokális (saját) library-ként való telepítése

A `-e` flag miatt a Python közvetlenül ebből a mappából tölti be a kódot —
ha módosítod a forrást, azonnal érvényes, újratelepítés nélkül.

```bash
python -m pip install -e "packages/markitdown[all]"
```

Ellenőrzés (a te mappádat kell mutassa, nem a site-packages-t):
```bash
python -c "import markitdown; print(markitdown.__file__)"
```

---

## 4. Az alkalmazás indítása

### GUI (grafikus felület)
```bash
python app.py
```

### Parancssori batch konvertálás
```bash
python convert.py
```
Fájlokat a `sources/` mappába kell másolni, az eredmény az `output/` mappában jelenik meg.

---

## 5. Támogatott formátumok

| Formátum | Megjegyzés |
|---|---|
| PDF | pdfminer + pdfplumber |
| DOCX, DOC | mammoth |
| XLSX, XLS | pandas + openpyxl/xlrd |
| PPTX | python-pptx |
| HTML, RSS, EPUB | beépített |
| AZW3, MOBI, FB2 | Calibre `ebook-convert` |
| TikTok, Facebook URL | beépített |
| CSV, JSON, XML | beépített |
| Jupyter notebook (.ipynb) | beépített |
| Outlook (.msg) | olefile |
| Képek | exiftool (metaadatok, opcionális) |
| Audio (MP3, WAV, M4A) | ffmpeg + Whisper (GPU/CPU auto) |
| YouTube URL | youtube-transcript-api |
| ZIP | beépített |

---

## 6. Audio átírás – Whisper modellek

| Modell | VRAM | CPU idő | Megjegyzés |
|---|---|---|---|
| tiny | ~1 GB | gyors | rövid fájlokhoz |
| base | ~1 GB | közepes | alapértelmezett |
| small | ~2 GB | lassú | jobb minőség |
| medium | ~5 GB | nagyon lassú | csak GPU-n ajánlott |
| large | ~10 GB | – | csak GPU-n |

Az első futáskor a modell letöltődik (~150 MB – 3 GB), ezután cache-elve van.

---

## 7. Lokális kép-OCR – PaddleOCR

Az alkalmazás a dokumentumot MarkItDown-nal alakítja Markdownná. Az opcionális
OCR-funkció a beágyazott képeket helyben, PaddleOCR-rel dolgozza fel, majd a
felismert szöveget a Markdown végéhez fűzi. Nem igényel API-kulcsot és nem
használ fizetős szolgáltatást.

### Külön OCR-környezet telepítése

A PaddlePaddle jelenleg nem ad ki Python 3.14-es Windows-csomagot. A fő app
ettől még maradhat a globális Python 3.14-en: az OCR egy külön Python 3.13-as
subprocessben fut, és JSON-fájlon keresztül adja vissza az eredményt.

A projekt gyökerében hozd létre az OCR-környezetet:

```powershell
uv venv --python 3.13 .venv-ocr
uv pip install --python .venv-ocr\Scripts\python.exe -r requirements-ocr.txt
```

Az OCR-környezetet nem kell aktiválni. Az app automatikusan a
`.venv-ocr\Scripts\python.exe` workert indítja, miközben maga továbbra is a
globális Python 3.14-en fut.

### Használat

1. Indítsd el az appot: `python app.py`.
2. Válassz ki egy dokumentumot.
3. Jelöld be az `OCR képekből (lokális PaddleOCR)` opciót.
4. Indítsd el a konvertálást.

Ha az OCR ki van kapcsolva, csak a megszokott MarkItDown-konverzió fut. Ha be
van kapcsolva, a kimenet végén ilyen szekció jelenik meg:

```markdown
## OCR-rel kinyert szöveg képekből

### Kép 1

A képről felismert szöveg...
```

A DOCX, PPTX és XLSX fájlok beágyazott képei támogatottak. PDF esetén a
beágyazott képeket a PyMuPDF nyeri ki. Önálló PNG, JPG, TIFF, BMP és WebP
képfájlok is feldolgozhatók.

### Első futtatás és teszt

Az első OCR-inicializálás letölti a szükséges modelleket, ezért ekkor
internetkapcsolat kell. A modellek ezután gyorsítótárból, offline is
használhatók. A modellek a projekt `.ocr-cache` könyvtárába kerülnek; ez és a
`.venv-ocr` nincs verziókezelés alatt.

```powershell
python test_ocr.py
```

### Hibaelhárítás

- Az OCR-környezet nem található: futtasd újra a fenti két `uv` parancsot.
- `No matching distribution found for paddlepaddle`: ellenőrizd, hogy az
  `uv venv` parancs valóban Python 3.13-as `.venv-ocr` környezetet hozott létre.
- Sikertelen modellletöltés: ellenőrizd az internetkapcsolatot, a proxyt és a
  tűzfalat, majd futtasd újra a tesztet.
- Nincs felismert szöveg: használj nagyobb, élesebb, kevésbé tömörített képet.
- Nincs OCR-szekció: a szekció csak akkor jön létre, ha legalább egy képen
  felismerhető szöveg található.

---

## 8. Saját konverter hozzáadása

Hozz létre egy új fájlt: `packages/markitdown/src/markitdown/converters/_sajat_converter.py`

```python
from markitdown._base_converter import BaseConverter, DocumentConverterResult
from markitdown._stream_info import StreamInfo

class SajatConverter(BaseConverter):
    def convert(self, stream, stream_info: StreamInfo, **kwargs) -> DocumentConverterResult:
        # ide jön a logika
        return DocumentConverterResult(text_content="...")
```

Majd regisztráld a `_markitdown.py`-ban:
```python
from markitdown.converters._sajat_converter import SajatConverter
# ...
self.register_converter(SajatConverter())
```
