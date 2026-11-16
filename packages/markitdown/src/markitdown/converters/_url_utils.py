"""URL helpers shared by the site-specific converters (MakeThemd addition)."""
import re
from typing import Iterable, Optional
from urllib.parse import parse_qs, urlparse

YOUTUBE_DOMAINS = ("youtube.com", "youtube-nocookie.com", "youtu.be")
_YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,}$")
_YOUTUBE_PATH_PREFIXES = ("shorts", "live", "embed", "v")


def url_host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""


def host_matches(url: str, domains: Iterable[str]) -> bool:
    """True if the URL's host is one of ``domains`` or a subdomain of one.

    A plain substring check would also match ``?utm_source=facebook.com`` or
    ``facebook.com.example.org``, so every site check goes through the parsed host.
    """
    host = url_host(url)
    return bool(host) and any(host == d or host.endswith("." + d) for d in domains)


def youtube_video_id(url: str) -> Optional[str]:
    """The video ID of a YouTube watch/short/live/embed or youtu.be link, else None."""
    if not host_matches(url, YOUTUBE_DOMAINS):
        return None
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    parts = [p for p in parsed.path.split("/") if p]
    candidate = None
    if url_host(url).endswith("youtu.be"):
        candidate = parts[0] if parts else None
    elif parts[:1] == ["watch"]:
        candidate = (parse_qs(parsed.query).get("v") or [None])[0]
    elif len(parts) >= 2 and parts[0] in _YOUTUBE_PATH_PREFIXES:
        candidate = parts[1]
    if candidate and _YOUTUBE_ID_RE.match(candidate):
        return candidate
    return None
