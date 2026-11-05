"""Small, dependency-free progress protocol shared by the GUI and OCR worker."""
from __future__ import annotations

import json
from dataclasses import dataclass

PROGRESS_PREFIX = "MAKETHEMD_OCR_PROGRESS "


@dataclass(frozen=True)
class OCRProgress:
    message: str
    elapsed: float
    fraction: float | None = None


def emit_progress(stage: str, **details) -> None:
    print(PROGRESS_PREFIX + json.dumps({"stage": stage, **details}, ensure_ascii=False), flush=True)
