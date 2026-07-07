from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox


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
