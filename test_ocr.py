#!/usr/bin/env python3
"""Run the PaddleOCR worker smoke test from the main Python environment."""

import json
import os
import subprocess
import tempfile
from pathlib import Path

from ocr_utils import OCR_CACHE, OCR_PYTHON, OCR_WORKER, check_ocr_environment


def main() -> int:
    try:
        check_ocr_environment()
    except RuntimeError as ex:
        print(f"HIBA: {ex}")
        return 1

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as temporary:
        result_path = Path(temporary.name)

    try:
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
        process = subprocess.run(
            [
                str(OCR_PYTHON),
                str(OCR_WORKER),
                "--self-test",
                "--output",
                str(result_path),
            ],
            env=environment,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        payload = json.loads(result_path.read_text(encoding="utf-8-sig"))
    finally:
        result_path.unlink(missing_ok=True)

    if process.returncode != 0 or payload.get("error"):
        print(f"HIBA: {payload.get('error') or process.stderr.strip()}")
        return 1

    text = payload.get("images", [{}])[0].get("text", "")
    print(f"OCR worker Python: {OCR_PYTHON}")
    print(f"OCR lefutott. Felismert szöveg: {text or '(nem talált szöveget)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
