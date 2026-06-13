from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parent
OCR_PYTHON = PROJECT_ROOT / ".venv-ocr" / "Scripts" / "python.exe"
OCR_WORKER = PROJECT_ROOT / "ocr_worker.py"
OCR_CACHE = PROJECT_ROOT / ".ocr-cache"


def check_ocr_environment() -> None:
    if not OCR_PYTHON.is_file():
        raise RuntimeError(
            "Az OCR-környezet nem található. Futtasd a SETUP.md-ben szereplő "
            "uv venv és uv pip parancsokat a .venv-ocr létrehozásához."
        )
    if not OCR_WORKER.is_file():
        raise RuntimeError(f"Az OCR worker nem található: {OCR_WORKER}")


def extract_image_texts(source_path: Path) -> list[dict[str, str]]:
    check_ocr_environment()
    source_path = source_path.resolve()

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as temporary:
        result_path = Path(temporary.name)

    command = [
        str(OCR_PYTHON),
        str(OCR_WORKER),
        "--source",
        str(source_path),
        "--output",
        str(result_path),
    ]
    environment = os.environ.copy()
    environment.update(
        {
            "HOME": str(OCR_CACHE),
            "USERPROFILE": str(OCR_CACHE),
            "HF_HOME": str(OCR_CACHE / "huggingface"),
            "PADDLE_PDX_CACHE_HOME": str(OCR_CACHE / "paddlex"),
        }
    )
    OCR_CACHE.mkdir(exist_ok=True)
    try:
        process = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            env=environment,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        payload = json.loads(result_path.read_text(encoding="utf-8-sig"))
        if error := payload.get("error"):
            raise RuntimeError(str(error))
        if process.returncode != 0:
            details = process.stderr.strip() or process.stdout.strip()
            raise RuntimeError(details or "Az OCR worker hibával leállt.")
        return [
            {"name": str(item["name"]), "text": str(item["text"])}
            for item in payload.get("images", [])
            if item.get("text")
        ]
    finally:
        result_path.unlink(missing_ok=True)


def append_image_ocr(
    markdown: str,
    source_path: Path,
    progress: Callable[[str], None] | None = None,
) -> tuple[str, int]:
    if progress:
        progress(f"OCR worker: {source_path.name}")

    images = extract_image_texts(source_path)
    if not images:
        return markdown, 0

    sections = [
        f"### Kép {index}\n\n{image['text']}"
        for index, image in enumerate(images, start=1)
    ]
    ocr_markdown = "## OCR-rel kinyert szöveg képekből\n\n" + "\n\n".join(sections)
    return markdown.rstrip() + "\n\n" + ocr_markdown + "\n", len(sections)
