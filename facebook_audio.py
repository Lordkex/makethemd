"""Ingyenes Facebook-hangletöltés a FDOWN szolgáltatással, valódi MP3-kimenettel."""

import shutil
import subprocess
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

import requests

from i18n import t


FDOWN_API = "https://fdown.tools/api/api/video-info"
FDOWN_PROXY = "https://fdown.tools/api/api/proxy-download"


def is_facebook_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == domain or host.endswith("." + domain)
               for domain in ("facebook.com", "fb.watch"))


def convert_to_mp3(source: Path, target: Path, ffmpeg_location: str | None = None) -> Path:
    """Kinyeri a hangsávot; az üres, hibás vagy néma videófájlokat visszautasítja."""
    executable = None
    if ffmpeg_location:
        location = Path(ffmpeg_location)
        if location.is_file():
            executable = str(location)
        else:
            executable = next((str(location / name) for name in ("ffmpeg.exe", "ffmpeg")
                               if (location / name).is_file()), None)
    executable = executable or shutil.which("ffmpeg")
    if not executable:
        raise RuntimeError(t("err_ffmpeg_missing"))

    temporary = target.with_name(target.stem + ".part.mp3")
    try:
        result = subprocess.run(
            [executable, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
             "-i", str(source), "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "16000",
             "-codec:a", "libmp3lame", "-b:a", "64k", str(temporary)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=300, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode or not temporary.is_file() or temporary.stat().st_size == 0:
            raise RuntimeError(t("err_mp3_failed", details=result.stderr.strip()[-500:]))
        temporary.replace(target)
        return target
    finally:
        temporary.unlink(missing_ok=True)


def download_facebook_audio(
    url: str,
    tmpdir: str,
    *,
    ffmpeg_location: str | None = None,
    progress_fn: Callable[[str], None] | None = None,
) -> Path:
    """FDOWN: külön hangsáv előnyben; CDN-hiba esetén szolgáltatói proxy, majd MP3."""
    if not is_facebook_url(url):
        raise ValueError(t("err_fdown_facebook_only"))

    if progress_fn:
        progress_fn(t("fdown_searching"))
    with requests.Session() as session:
        session.headers.update({"User-Agent": "Mozilla/5.0", "Referer": "https://fdown.tools/"})
        with session.post(FDOWN_API, json={"url": url}, timeout=(10, 45)) as response:
            response.raise_for_status()
            try:
                payload = response.json()
            except ValueError as ex:
                raise RuntimeError(t("err_fdown_bad_response")) from ex
        if not isinstance(payload, dict) or not payload.get("success"):
            message = (payload.get("error") or payload.get("details")) if isinstance(payload, dict) else None
            raise RuntimeError(t("err_fdown_failed", message=message or t("err_fdown_no_content")))

        data = payload.get("data") or {}
        if not isinstance(data, dict) or not isinstance(data.get("formats", []), list):
            raise RuntimeError(t("err_fdown_no_formats"))
        formats = data.get("formats") or []
        formats = [item for item in formats if isinstance(item, dict) and isinstance(item.get("url"), str)
                   and urlparse(item["url"]).scheme == "https"
                   and item.get("acodec") != "none"]

        def audio_priority(item):
            audio_only = (item.get("vcodec") == "none" or item.get("video_ext") == "none"
                          or item.get("ext") in {"mp3", "m4a", "aac", "opus"})
            return (not audio_only, item.get("format_id") != "sd")

        formats.sort(key=audio_priority)
        if not formats:
            raise RuntimeError(t("err_fdown_no_audio"))

        source = Path(tmpdir) / "facebook_source.media"
        target = Path(tmpdir) / "facebook_audio.mp3"
        last_error = None
        for item in formats[:3]:
            # A CDN a szolgáltató IP-címére is korlátozhatja a linket.
            for via_proxy in (False, True):
                try:
                    if progress_fn:
                        progress_fn(t("fdown_downloading_proxy" if via_proxy else "fdown_downloading"))
                    endpoint = FDOWN_PROXY if via_proxy else item["url"]
                    params = {"url": item["url"]} if via_proxy else None
                    headers = None if via_proxy else {
                        "User-Agent": "facebookexternalhit/1.1", "Referer": "https://www.facebook.com/",
                    }
                    with session.get(endpoint, params=params, headers=headers,
                                     stream=True, timeout=(10, 60)) as response:
                        response.raise_for_status()
                        content_type = response.headers.get("Content-Type", "").lower()
                        if any(value in content_type for value in ("text/", "json", "xml")):
                            raise RuntimeError(t("err_fdown_text"))
                        with source.open("wb") as stream:
                            for chunk in response.iter_content(chunk_size=256 * 1024):
                                stream.write(chunk)
                    if progress_fn:
                        progress_fn(t("fdown_converting"))
                    return convert_to_mp3(source, target, ffmpeg_location)
                except (requests.RequestException, RuntimeError, subprocess.TimeoutExpired) as ex:
                    last_error = ex
                finally:
                    source.unlink(missing_ok=True)

    raise RuntimeError(t("err_fdown_all_failed", error=last_error)) from last_error
