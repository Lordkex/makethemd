# Makethemd – Beállítási útmutató

## 1. Előfeltételek

### Python
Python 3.10–3.14 szükséges.  
Letöltés: https://www.python.org/downloads/

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

## 7. Saját konverter hozzáadása

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
