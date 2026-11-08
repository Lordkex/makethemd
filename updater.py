"""A letöltő-csomagok (yt-dlp, youtube-transcript-api) frissítése indításkor.

A start_makethemd.bat futtatja az app előtt. Csak ezekhez nyúl: a YouTube gyakran
változik, és ezek attól romlanak el; a többi csomag (Flet, PyTorch, markitdown) marad.

- legfeljebb hetente egyszer ellenőriz (a PyPI-n van-e újabb verzió),
- ha az app futás közben elavult letöltőre utaló hibát látott, a következő
  indításkor azonnal frissít (settings.json "force_update"),
- ha a frissített csomag nem töltődik be, visszaállítja az előző verziót.
"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta
from importlib import metadata

from i18n import t
from output_utils import apply_saved_language, load_settings, save_settings

# pip-név → PyPI-név (a [default] hozza a yt-dlp-ejs-t a YouTube JS-kihívásához)
PACKAGES = {"yt-dlp": "yt-dlp[default]", "yt-dlp-ejs": "yt-dlp-ejs", "youtube-transcript-api": "youtube-transcript-api"}
CHECK_INTERVAL = timedelta(days=7)
SMOKE_TEST = (
    "import yt_dlp, yt_dlp_ejs, youtube_transcript_api\n"
    "yt_dlp.YoutubeDL({'quiet': True}).close()\n"
)


def installed_version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def latest_version(name: str) -> str:
    with urllib.request.urlopen(f"https://pypi.org/pypi/{name}/json", timeout=5) as resp:
        return json.load(resp)["info"]["version"]


def is_due(settings: dict, now: datetime) -> bool:
    if settings.get("force_update"):
        return True
    try:
        last = datetime.fromisoformat(settings.get("last_update_check", ""))
    except ValueError:
        return True
    return now - last >= CHECK_INTERVAL


def pip_install(*specs: str) -> bool:
    cmd = [sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check", *specs]
    return subprocess.run(cmd).returncode == 0


def works() -> bool:
    """Külön folyamatban, hogy a frissen telepített verzió töltődjön be."""
    return subprocess.run([sys.executable, "-c", SMOKE_TEST], capture_output=True).returncode == 0


def main() -> None:
    apply_saved_language()
    settings = load_settings()
    now = datetime.now()
    # hiányzó csomagnál nem várunk a heti ellenőrzésre (pl. másik Python-környezetre váltás után)
    missing = any(installed_version(name) is None for name in PACKAGES)
    if not missing and not is_due(settings, now):
        return

    try:
        outdated = [
            name for name in PACKAGES
            if name != "yt-dlp-ejs"  # a yt-dlp[default] a hozzá illő ejs-verziót húzza be
            and installed_version(name) != latest_version(name)
        ]
    except Exception:
        print(t("upd_skipped"))
        return  # nem jegyezzük fel: a következő indításkor újra próbálja

    if not installed_version("yt-dlp-ejs") and "yt-dlp" not in outdated:
        outdated.append("yt-dlp")

    if not outdated:
        save_settings(last_update_check=now.isoformat(timespec="seconds"), force_update=False)
        return

    before = {name: installed_version(name) for name in PACKAGES}
    print(t("upd_updating", names=", ".join(outdated)))
    ok = pip_install("--upgrade", "--upgrade-strategy", "only-if-needed",
                     *(PACKAGES[name] for name in outdated))

    if ok and works():
        after = ", ".join(f"{n} {installed_version(n)}" for n in PACKAGES)
        print(t("upd_done", versions=after))
    else:
        restore = [f"{name}=={ver}" for name, ver in before.items() if ver]
        print(t("upd_broken", versions=", ".join(restore)))
        if restore and pip_install(*restore) and works():
            print(t("upd_restored"))
        else:
            print(t("upd_restore_failed"))
    save_settings(last_update_check=now.isoformat(timespec="seconds"), force_update=False)


if __name__ == "__main__":
    main()
