from __future__ import annotations

import json
import logging
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox

# A kimeneti mappában tartott lista a sikertelen linkekről, későbbi újrapróbáláshoz.
# Sima .txt, így a „Linklista (.txt) betöltése” gombbal is visszatölthető.
FAILED_LINKS_NAME = "_sikertelen_linkek.txt"
_FAILED_HEADER = (
    "# MakeThemd – sikertelen linkek\n"
    "# Az app „Újrapróbálás” gombja innen tölti vissza őket a linklistába;\n"
    "# ami később elkészül, automatikusan lekerül innen.\n"
)


# Felhasználói beállítások (pl. utoljára választott kimeneti mappa) újraindítások között.
SETTINGS_PATH = Path(__file__).resolve().parent / "settings.json"


def load_settings(path: Path = SETTINGS_PATH) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_settings(path: Path = SETTINGS_PATH, **changes) -> None:
    data = {**load_settings(path), **changes}
    try:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as ex:
        logging.getLogger(__name__).warning("A beállítások nem menthetők: %s", ex)


def saved_output_dir(default: Path, path: Path = SETTINGS_PATH) -> Path:
    """Az utoljára választott kimeneti mappa, ha még létezik; különben az alapértelmezett."""
    saved = load_settings(path).get("output_dir")
    if isinstance(saved, str) and saved and Path(saved).is_dir():
        return Path(saved)
    return default


def read_failed_links(out_dir: Path) -> dict[str, str]:
    """A kimeneti mappa sikertelen-listája: URL → az utolsó hiba (dátummal)."""
    try:
        lines = (out_dir / FAILED_LINKS_NAME).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return {}
    failed: dict[str, str] = {}
    reason = ""
    for raw in lines:
        line = raw.strip()
        if not line:
            reason = ""  # üres sor után a fejléc-megjegyzés nem tapad a következő linkhez
        elif line.startswith("#"):
            reason = line.lstrip("#").strip()
        else:
            failed[line] = reason
            reason = ""
    return failed


def record_link_result(out_dir: Path, url: str, error: str | None = None) -> None:
    """Sikertelen linket felvesz a listára (hibaokkal), elkészültet levesz róla."""
    failed = read_failed_links(out_dir)
    if error is None:
        if url not in failed:
            return
        del failed[url]
    else:
        reason = " ".join(error.split())
        if len(reason) > 200:
            reason = reason[:199] + "…"
        failed[url] = f"{datetime.now():%Y-%m-%d %H:%M} – {reason}"

    path = out_dir / FAILED_LINKS_NAME
    try:
        if not failed:
            path.unlink(missing_ok=True)
            return
        body = "\n\n".join(f"# {r}\n{u}" if r else u for u, r in failed.items())
        path.write_text(_FAILED_HEADER + "\n" + body + "\n", encoding="utf-8")
    except OSError as ex:
        logging.getLogger(__name__).warning("A sikertelen-lista nem írható: %s", ex)


def make_unique_path(path: Path) -> Path:
    """Visszaad egy még nem létező útvonalat az adott alapútnál."""
    candidate = path
    counter = 2
    while candidate.exists():
        candidate = path.with_name(f"{path.stem}_{counter}{path.suffix}")
        counter += 1
    return candidate


def choose_output_path(path: Path) -> Path | None:
    """Ha a célfájl már létezik, a felhasználótól kér döntést."""
    if not path.exists():
        return path

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        answer = messagebox.askyesnocancel(
            "Kimeneti fájl már létezik",
            f"A(z) {path.name} fájl már létezik.\nFelülírja, átnevezi, vagy kihagyja ezt az elemet?",
            icon=messagebox.WARNING,
        )
    finally:
        root.destroy()

    if answer is True:
        return path
    if answer is False:
        return make_unique_path(path)
    return None
