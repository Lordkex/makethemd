from __future__ import annotations

import argparse
import io
import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Iterable

# Always use this repository's converters, including on an older global installation.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages" / "markitdown" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageDraw
from paddleocr_tools.progress import emit_progress
from i18n import set_language

OFFICE_MEDIA_PREFIXES = {
    ".docx": ("word/media/",),
    ".pptx": ("ppt/media/",),
    ".xlsx": ("xl/media/",),
}
IMAGE_EXTENSIONS = {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}


def create_ocr_engine(language: str = "hu") -> Any:
    emit_progress("models")
    from paddleocr import PaddleOCR

    return PaddleOCR(
        lang=language,
        # CPU only: oneDNN crashes PaddlePaddle 3.3.1 (ConvertPirAttribute2RuntimeAttribute).
        enable_mkldnn=False,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )


def _office_images(path: Path) -> Iterable[tuple[str, bytes]]:
    prefixes = OFFICE_MEDIA_PREFIXES[path.suffix.lower()]
    with zipfile.ZipFile(path) as archive:
        names = sorted(
            name
            for name in archive.namelist()
            if name.lower().startswith(prefixes) and not name.endswith("/")
        )
        emit_progress("images_found", total=len(names))
        for name in names:
            yield Path(name).name, archive.read(name)


def _pdf_images(path: Path) -> Iterable[tuple[str, bytes]]:
    import fitz

    document = fitz.open(path)
    try:
        references = []
        image_number = 0
        for page_index in range(document.page_count):
            page_number = page_index + 1
            page = document.load_page(page_index)
            for image in page.get_images(full=True):
                image_number += 1
                references.append((page_number, image_number, image[0]))
            emit_progress("scan", completed=page_number, total=document.page_count)
        emit_progress("images_found", total=len(references))
        for page_number, image_number, reference in references:
            extracted = document.extract_image(reference)
            extension = extracted.get("ext", "png")
            yield f"oldal-{page_number}-kep-{image_number}.{extension}", extracted["image"]
    finally:
        document.close()


def extract_images(path: Path) -> Iterable[tuple[str, bytes]]:
    suffix = path.suffix.lower()
    if suffix in OFFICE_MEDIA_PREFIXES:
        yield from _office_images(path)
    elif suffix == ".pdf":
        yield from _pdf_images(path)
    elif suffix in IMAGE_EXTENSIONS:
        emit_progress("images_found", total=1)
        yield path.name, path.read_bytes()


def _result_texts(result: Any) -> list[str]:
    texts: list[str] = []
    for item in result or []:
        data = item
        if not isinstance(data, dict):
            data = getattr(item, "json", None) or getattr(item, "res", None)
        if callable(data):
            data = data()
        if isinstance(data, str):
            data = json.loads(data)
        if isinstance(data, dict) and isinstance(data.get("res"), dict):
            data = data["res"]
        if isinstance(data, dict):
            texts.extend(
                str(text).strip()
                for text in data.get("rec_texts", [])
                if str(text).strip()
            )
    return texts


def ocr_image_bytes(engine: Any, image_bytes: bytes) -> str:
    with Image.open(io.BytesIO(image_bytes)) as image:
        image = image.convert("RGB")
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temporary:
            temporary_path = Path(temporary.name)
            image.save(temporary, format="PNG")

    try:
        return "\n".join(_result_texts(engine.predict(str(temporary_path))))
    finally:
        temporary_path.unlink(missing_ok=True)


def process_source(source_path: Path) -> list[dict[str, str]]:
    emit_progress("finding")
    engine = None
    images: list[dict[str, str]] = []
    for index, (name, image_bytes) in enumerate(extract_images(source_path), start=1):
        if engine is None:
            engine = create_ocr_engine()
        emit_progress("image_start", name=name)
        text = ocr_image_bytes(engine, image_bytes)
        if text:
            images.append({"name": name, "text": text})
        emit_progress("image_done", name=name, completed=index)
    return images


def self_test() -> list[dict[str, str]]:
    image = Image.new("RGB", (800, 180), "white")
    ImageDraw.Draw(image).text((40, 70), "PaddleOCR local test 123", fill="black")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    emit_progress("images_found", total=1)
    engine = create_ocr_engine()
    emit_progress("image_start", name="self-test.png")
    text = ocr_image_bytes(engine, buffer.getvalue())
    emit_progress("image_done", name="self-test.png", completed=1)
    return [{"name": "self-test.png", "text": text}]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--convert", action="store_true")
    args = parser.parse_args()
    set_language(os.environ.get("MAKETHEMD_UI_LANGUAGE", "en"))

    try:
        if args.convert and args.source.suffix.lower() == ".pdf":
            from paddleocr_tools.pdf_ocr import convert_pdf

            payload = convert_pdf(
                args.source.resolve(), create_ocr_engine, ocr_image_bytes, emit_progress,
                cache_root=Path(__file__).resolve().parents[1] / ".ocr-cache" / "pdf-pages",
            )
        else:
            payload = process_conversion(args)
        exit_code = 0
    except Exception as ex:
        payload = {"images": [], "error": f"{type(ex).__name__}: {ex}"}
        exit_code = 1

    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if exit_code == 0:
        emit_progress("done")
    return exit_code


def process_conversion(args) -> dict:
    markdown = None
    if args.convert:
        emit_progress("reading")
        # Import after environment setup, never reuse the GUI's cached import failure.
        from markitdown import MarkItDown

        markdown = MarkItDown().convert(str(args.source.resolve())).text_content
    images = self_test() if args.self_test else process_source(args.source.resolve())
    payload: dict[str, Any] = {"images": images}
    if markdown is not None:
        payload["markdown"] = markdown
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
