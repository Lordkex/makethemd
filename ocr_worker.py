from __future__ import annotations

import argparse
import io
import json
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageDraw
from paddleocr import PaddleOCR

OFFICE_MEDIA_PREFIXES = {
    ".docx": ("word/media/",),
    ".pptx": ("ppt/media/",),
    ".xlsx": ("xl/media/",),
}
IMAGE_EXTENSIONS = {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}


def create_ocr_engine(language: str = "hu") -> PaddleOCR:
    return PaddleOCR(
        lang=language,
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
        for name in names:
            yield Path(name).name, archive.read(name)


def _pdf_images(path: Path) -> Iterable[tuple[str, bytes]]:
    import fitz

    document = fitz.open(path)
    try:
        image_number = 0
        for page_index in range(document.page_count):
            page_number = page_index + 1
            page = document.load_page(page_index)
            for image in page.get_images(full=True):
                image_number += 1
                extracted = document.extract_image(image[0])
                extension = extracted.get("ext", "png")
                yield (
                    f"oldal-{page_number}-kep-{image_number}.{extension}",
                    extracted["image"],
                )
    finally:
        document.close()


def extract_images(path: Path) -> Iterable[tuple[str, bytes]]:
    suffix = path.suffix.lower()
    if suffix in OFFICE_MEDIA_PREFIXES:
        yield from _office_images(path)
    elif suffix == ".pdf":
        yield from _pdf_images(path)
    elif suffix in IMAGE_EXTENSIONS:
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


def ocr_image_bytes(engine: PaddleOCR, image_bytes: bytes) -> str:
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
    engine = create_ocr_engine()
    images: list[dict[str, str]] = []
    for name, image_bytes in extract_images(source_path):
        text = ocr_image_bytes(engine, image_bytes)
        if text:
            images.append({"name": name, "text": text})
    return images


def self_test() -> list[dict[str, str]]:
    image = Image.new("RGB", (800, 180), "white")
    ImageDraw.Draw(image).text((40, 70), "PaddleOCR local test 123", fill="black")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    text = ocr_image_bytes(create_ocr_engine(), buffer.getvalue())
    return [{"name": "self-test.png", "text": text}]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    try:
        images = self_test() if args.self_test else process_source(args.source.resolve())
        payload: dict[str, Any] = {"images": images}
        exit_code = 0
    except Exception as ex:
        payload = {"images": [], "error": f"{type(ex).__name__}: {ex}"}
        exit_code = 1

    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
