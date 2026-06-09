import bs4
import json
import requests
from typing import Any, BinaryIO, Dict, Optional
from urllib.parse import unquote

from .._base_converter import DocumentConverter, DocumentConverterResult
from .._stream_info import StreamInfo


ACCEPTED_MIME_TYPE_PREFIXES = ["text/html", "application/xhtml"]
ACCEPTED_FILE_EXTENSIONS = [".html", ".htm"]


class TikTokConverter(DocumentConverter):
    """Convert a TikTok page into Markdown containing title, author, and video link."""

    def accepts(self, file_stream: BinaryIO, stream_info: StreamInfo, **kwargs: Any) -> bool:
        url = stream_info.url or ""
        mimetype = (stream_info.mimetype or "").lower()
        extension = (stream_info.extension or "").lower()

        url = unquote(url)
        if "tiktok.com" not in url and not url.startswith("https://vm.tiktok.com"):
            return False

        if extension in ACCEPTED_FILE_EXTENSIONS:
            return True
        for prefix in ACCEPTED_MIME_TYPE_PREFIXES:
            if mimetype.startswith(prefix):
                return True
        return False

    def _extract_tiktok_json(self, soup: bs4.BeautifulSoup) -> Optional[Dict[str, Any]]:
        for script in soup.find_all("script"):
            script_text = script.string or script.get_text()
            if not script_text or "__DEFAULT_SCOPE__" not in script_text:
                continue

            start = script_text.find('{"__DEFAULT_SCOPE__"')
            if start == -1:
                continue
            json_text = script_text[start:]
            end = json_text.rfind("}")
            if end == -1:
                continue
            json_text = json_text[: end + 1]

            try:
                return json.loads(json_text)
            except json.JSONDecodeError:
                continue
        return None

    def _extract_webvtt_transcript(self, vtt_text: str) -> str:
        """Extract text content from WebVTT format, ignoring timestamps."""
        lines = vtt_text.split("\n")
        transcript_lines = []
        for line in lines:
            line = line.strip()
            # Skip empty lines, WEBVTT header, and timestamp lines
            if (
                line
                and not line.startswith("WEBVTT")
                and not line.startswith("NOTE")
                and "-->" not in line
            ):
                transcript_lines.append(line)
        return " ".join(transcript_lines).strip()

    def _fetch_transcript(
        self, subtitle_infos: list, headers: Dict[str, str]
    ) -> Optional[str]:
        """Fetch and extract transcript from TikTok's automatic captions."""
        if not subtitle_infos:
            return None

        for subtitle in subtitle_infos:
            url = subtitle.get("Url", "")
            if not url:
                continue
            try:
                resp = requests.get(url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    return self._extract_webvtt_transcript(resp.text)
            except Exception:
                # Silently fail if transcript fetch fails
                pass
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

        title = metadata.get("og:title") or metadata.get("title") or "TikTok video"
        author = metadata.get("author") or metadata.get("og:site_name") or ""
        description = metadata.get("og:description") or metadata.get("description") or ""
        video_url = metadata.get("og:video") or metadata.get("og:video:secure_url") or ""

        # Browser-like headers for transcript fetching
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.google.com/",
        }

        tiktok_json = self._extract_tiktok_json(soup)
        transcript = None
        if tiktok_json:
            item_struct = (
                tiktok_json.get("__DEFAULT_SCOPE__", {})
                .get("webapp.video-detail", {})
                .get("itemInfo", {})
                .get("itemStruct", {})
            )
            if item_struct:
                author_info = item_struct.get("author", {}) or {}
                if not author:
                    author = author_info.get("nickname") or author_info.get("uniqueId", "")
                if not description:
                    description = item_struct.get("desc", "")
                if not video_url:
                    video_url = (
                        item_struct.get("video", {})
                        .get("playAddr")
                        or item_struct.get("video", {}).get("downloadAddr", "")
                    )
                music_info = item_struct.get("music", {}) or {}
                music_title = music_info.get("title", "")
                music_author = music_info.get("authorName", "")
                stats = item_struct.get("stats", {}) or {}
                
                # Try to fetch transcript from automatic captions
                subtitle_infos = item_struct.get("video", {}).get("subtitleInfos", [])
                transcript = self._fetch_transcript(subtitle_infos, headers)
                
                if title == "TikTok video":
                    author_title = author_info.get("nickname") or author_info.get("uniqueId")
                    title = f"{author_title} on TikTok" if author_title else title
        else:
            music_title = ""
            music_author = ""
            stats = {}

        md = "# TikTok\n\n"
        if title:
            md += f"## {title}\n\n"
        if author:
            md += f"- **Author:** {author}\n"
        if video_url:
            md += f"- **Video:** {video_url}\n"
            md += f"<video controls src=\"{video_url}\"></video>\n\n"
        if music_title:
            md += f"- **Music:** {music_title}"
            if music_author:
                md += f" by {music_author}"
            md += "\n"
        if stats:
            md += "\n### Stats\n"
            if stats.get("diggCount") is not None:
                md += f"- Likes: {stats.get('diggCount')}\n"
            if stats.get("commentCount") is not None:
                md += f"- Comments: {stats.get('commentCount')}\n"
            if stats.get("shareCount") is not None:
                md += f"- Shares: {stats.get('shareCount')}\n"
            if stats.get("playCount") is not None:
                md += f"- Plays: {stats.get('playCount')}\n"
            if stats.get("collectCount") is not None:
                md += f"- Saves: {stats.get('collectCount')}\n"
            md += "\n"
        if description:
            md += f"### Description\n{description}\n"
        if transcript:
            md += f"\n### Transcript\n{transcript}\n"

        return DocumentConverterResult(markdown=md, title=title)
