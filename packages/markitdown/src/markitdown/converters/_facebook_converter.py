import bs4
import json
import re
import requests
from typing import Any, BinaryIO, Dict, List, Optional
from urllib.parse import unquote

from .._base_converter import DocumentConverter, DocumentConverterResult
from .._stream_info import StreamInfo


ACCEPTED_MIME_TYPE_PREFIXES = ["text/html", "application/xhtml"]
ACCEPTED_FILE_EXTENSIONS = [".html", ".htm"]


class FacebookConverter(DocumentConverter):
    """Convert a Facebook video/post page into Markdown."""

    def accepts(self, file_stream: BinaryIO, stream_info: StreamInfo, **kwargs: Any) -> bool:
        url = stream_info.url or ""
        mimetype = (stream_info.mimetype or "").lower()
        extension = (stream_info.extension or "").lower()

        url = unquote(url)
        if "facebook.com" not in url and "fb.watch" not in url:
            return False

        if extension in ACCEPTED_FILE_EXTENSIONS:
            return True
        for prefix in ACCEPTED_MIME_TYPE_PREFIXES:
            if mimetype.startswith(prefix):
                return True
        return False

    def _extract_webvtt_transcript(self, vtt_text: str) -> str:
        lines = vtt_text.splitlines()
        transcript_lines: List[str] = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("WEBVTT") or stripped.startswith("NOTE"):
                continue
            if "-->" in stripped:
                continue
            transcript_lines.append(stripped)
        return " ".join(transcript_lines).strip()

    def _find_facebook_transcript_urls(self, html: str) -> List[str]:
        transcript_urls: List[str] = []
        for match in re.finditer(r'"transcript_urls"\s*:\s*(\[[^\]]*\])', html):
            array_text = match.group(1)
            try:
                urls = json.loads(array_text)
            except json.JSONDecodeError:
                continue
            for item in urls:
                if isinstance(item, str):
                    transcript_urls.append(item)
                elif isinstance(item, dict):
                    for key in ["uri", "url", "Url", "URL", "src", "Src"]:
                        value = item.get(key)
                        if isinstance(value, str) and value:
                            transcript_urls.append(value)
                            break
        return transcript_urls

    def _fetch_facebook_transcript(self, transcript_urls: List[str], headers: Dict[str, str]) -> Optional[str]:
        for url in transcript_urls:
            try:
                response = requests.get(url, headers=headers, timeout=15)
                if response.status_code != 200:
                    continue
                text = response.text
                if "WEBVTT" in text:
                    transcript = self._extract_webvtt_transcript(text)
                    if transcript:
                        return transcript
                try:
                    data = json.loads(text)
                except json.JSONDecodeError:
                    data = None
                if data is not None:
                    collected: List[str] = []
                    def collect(o: Any) -> None:
                        if isinstance(o, dict):
                            for k, v in o.items():
                                if k.lower() in {"text", "caption", "content", "subtitle"} and isinstance(v, str) and v.strip():
                                    collected.append(v.strip())
                                else:
                                    collect(v)
                        elif isinstance(o, list):
                            for item in o:
                                collect(item)
                    collect(data)
                    if collected:
                        return " ".join(collected).strip()
            except Exception:
                continue
        return None

    def convert(self, file_stream: BinaryIO, stream_info: StreamInfo, **kwargs: Any) -> DocumentConverterResult:
        encoding = "utf-8" if stream_info.charset is None else stream_info.charset
        raw = file_stream.read()
        html = raw.decode(encoding, errors="replace") if isinstance(raw, (bytes, bytearray)) else raw
        soup = bs4.BeautifulSoup(html, "html.parser")

        metadata: Dict[str, str] = {}
        if soup.title and soup.title.string:
            metadata["title"] = soup.title.string
        for meta in soup(["meta"]):
            if not isinstance(meta, bs4.Tag):
                continue
            for a in meta.attrs:
                if a in ["property", "name", "itemprop"]:
                    key = str(meta.get(a, ""))
                    content = str(meta.get("content", ""))
                    if key and content:
                        metadata[key] = content
                    break

        title = metadata.get("og:title") or metadata.get("title") or "Facebook post"
        author = metadata.get("author") or metadata.get("og:site_name") or ""
        description = metadata.get("og:description") or metadata.get("description") or ""
        video_url = metadata.get("og:video") or metadata.get("og:video:secure_url") or ""

        transcript = None
        transcript_urls = self._find_facebook_transcript_urls(html)
        if transcript_urls:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.facebook.com/",
            }
            transcript = self._fetch_facebook_transcript(transcript_urls, headers)

        md = "# Facebook\n\n"
        if title:
            md += f"## {title}\n\n"
        if author:
            md += f"- **Author:** {author}\n"
        if video_url:
            md += f"- **Video:** {video_url}\n\n"
            md += f"<video controls src=\"{video_url}\"></video>\n\n"
        if description:
            md += f"### Description\n{description}\n"
        if transcript:
            md += f"\n### Transcript\n{transcript}\n"

        return DocumentConverterResult(markdown=md, title=title)
