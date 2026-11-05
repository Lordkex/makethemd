#!/usr/bin/env python3
"""Exercise the same automatic setup and OCR worker used by the app."""

import sys
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from paddleocr_tools.ocr_utils import OCR_PYTHON, run_ocr_worker


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        images = run_ocr_worker(["--self-test"], progress=print)
    except (RuntimeError, OSError) as ex:
        print(f"HIBA: {ex}")
        return 1
    text = "\n".join(image["text"] for image in images)
    print(f"OCR worker Python: {OCR_PYTHON}")
    if "123" not in text:
        print(f"HIBA: a tesztkép szövege nem ismerhető fel: {text!r}")
        return 1
    print(f"OCR lefutott. Felismert szöveg: {text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
