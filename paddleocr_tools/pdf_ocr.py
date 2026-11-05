"""Page-by-page PDF reading with OCR for unreliable or absent text layers."""
from __future__ import annotations

import hashlib
import io
import json
import re
import tempfile
import unicodedata
from pathlib import Path
from typing import Callable, Any

from i18n import t

_CACHE_VERSION = b"pdf-page-ocr-v1;paddleocr=3.7.0;lang=hu;dpi=200;max-side=2800"


def text_is_unreliable(text: str) -> bool:
    if re.search(r"\(cid:\d+\)", text):
        return True
    characters = [character for character in text if not character.isspace()]
    if not characters:
        return False
    invalid = sum(character == "\ufffd" or unicodedata.category(character) in {"Cc", "Co"}
                  for character in characters)
    return invalid >= 3 or invalid / len(characters) > 0.02


def page_needs_ocr(page: Any, text: str) -> bool:
    if text_is_unreliable(text):
        return True
    for font in page.get_fonts():
        if font[2] == "Type3" and page.parent.xref_get_key(font[0], "ToUnicode")[0] == "null":
            return True
    # A small page number or caption is not proof that a scanned page has a usable text layer.
    return len(re.sub(r"\s", "", text)) < 20 and bool(page.get_images() or page.get_drawings())


def _cache_directory(source: Path, cache_root: Path | None) -> Path | None:
    if cache_root is None:
        return None
    digest = hashlib.sha256(_CACHE_VERSION)
    with source.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    directory = cache_root / digest.hexdigest()
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _cached_text(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        text = payload["text"]
        return text if isinstance(text, str) and not text_is_unreliable(text) else None
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _save_text(path: Path | None, text: str) -> None:
    if path is None:
        return
    # A killed worker must not leave a partial page cached as a completed recognition.
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     suffix=".json", delete=False) as stream:
        temporary = Path(stream.name)
        json.dump({"text": text}, stream, ensure_ascii=False)
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _read_page(pdf_page: Any) -> str:
    text = pdf_page.extract_text() or ""
    if text_is_unreliable(text):
        return text
    # Only try the table formatter when actual ruled tables exist. Prose must not
    # become a table just because its words happen to share horizontal positions.
    if pdf_page.find_tables():
        from markitdown.converters._pdf_converter import _extract_form_content_from_words

        table_text = _extract_form_content_from_words(pdf_page)
        if table_text and not text_is_unreliable(table_text):
            return table_text
    return text


def _page_image_texts(page, native_text, get_engine, recognize, seen, emit, number, total, completed):
    """Retain diagram/image OCR on otherwise readable pages without reading masks or logos twice."""
    from PIL import Image

    texts = []
    native_words = set(re.findall(r"\w+", native_text.casefold()))
    for reference in page.get_images(full=True):
        xref = reference[0]
        if reference[2] < 80 or reference[3] < 40:
            continue
        if page.parent.xref_get_key(xref, "ImageMask") == ("bool", "true"):
            continue
        data = page.parent.extract_image(xref)["image"]
        digest = hashlib.sha256(data).digest()
        if digest in seen:
            continue
        seen.add(digest)
        with Image.open(io.BytesIO(data)) as image:
            histogram = image.convert("L").histogram()
            if max(histogram) == image.width * image.height:
                continue
        engine = get_engine()
        emit("pdf_page", page=number, total=total, completed=completed, mode="images")
        recognized = recognize(engine, data).strip()
        words = re.findall(r"\w+", recognized.casefold())
        if sum(map(len, words)) < 10 or text_is_unreliable(recognized):
            continue
        if words and sum(word in native_words for word in words) / len(words) >= 0.9:
            continue
        texts.append(recognized)
    return texts


def convert_pdf(
    source: Path, create_engine: Callable[[], Any], recognize: Callable[[Any, bytes], str],
    emit: Callable[..., None], cache_root: Path | None = None,
) -> dict:
    import pdfplumber
    import pymupdf

    cache = _cache_directory(source, cache_root)
    engine = None
    def get_engine():
        nonlocal engine
        if engine is None:
            engine = create_engine()
        return engine

    pages = []
    ocr_pages = 0
    seen_images = set()
    with pymupdf.open(source) as document, pdfplumber.open(source) as text_document:
        total = len(document)
        for index, page in enumerate(document):
            number = index + 1
            emit("pdf_page", page=number, total=total, completed=index, mode="reading")
            text_page = text_document.pages[index]
            try:
                try:
                    text = text_page.extract_text() or ""
                except Exception:
                    text = page.get_text(sort=True)
                method = "text"
                if page_needs_ocr(page, text):
                    ocr_pages += 1
                    cache_path = cache / f"{number}.json" if cache else None
                    recognized = _cached_text(cache_path)
                    if recognized is None:
                        engine = get_engine()
                        emit("pdf_page", page=number, total=total, completed=index, mode="ocr")
                        scale = min(200 / 72, 2800 / max(page.rect.width, page.rect.height))
                        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
                        recognized = recognize(engine, pixmap.tobytes("png"))
                        if text_is_unreliable(recognized) or (not recognized.strip() and len(text.strip()) >= 20):
                            raise RuntimeError(t("err_pdf_page_ocr", page=number))
                        _save_text(cache_path, recognized)
                        method = "ocr"
                    else:
                        method = "cached"
                    text = recognized
                else:
                    try:
                        text = _read_page(text_page)
                    except Exception:
                        # Preserve the already validated plain text if table analysis fails.
                        pass
                    image_texts = _page_image_texts(page, text, get_engine, recognize, seen_images,
                                                   emit, number, total, index)
                    for image_index, image_text in enumerate(image_texts, start=1):
                        text += f"\n\n### {t('ocr_image', n=image_index)}\n\n{image_text}"
                pages.append({"page": number, "method": method, "text": text.strip()})
                emit("pdf_page", page=number, total=total, completed=number, mode=method)
            except Exception as ex:
                raise RuntimeError(t("err_pdf_page_failed", page=number, error=str(ex))) from ex
            finally:
                text_page.close()
    markdown = "\n\n---\n\n".join(
        f"## {t('pdf_page_heading', page=page['page'])}\n\n{page['text']}" for page in pages
    ) + "\n"
    return {"markdown": markdown, "images": [], "ocr_pages": ocr_pages,
            "pdf_pages": [{"page": page["page"], "method": page["method"]} for page in pages]}
