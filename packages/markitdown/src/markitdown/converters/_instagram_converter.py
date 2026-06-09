import bs4
from typing import Any, BinaryIO, Dict, Union
from urllib.parse import unquote

from .._base_converter import DocumentConverter, DocumentConverterResult
from .._stream_info import StreamInfo


ACCEPTED_MIME_TYPE_PREFIXES = ["text/html", "application/xhtml"]
ACCEPTED_FILE_EXTENSIONS = [".html", ".htm"]


class InstagramConverter(DocumentConverter):
    """Convert an Instagram post or reel page into Markdown."""

    def accepts(self, file_stream: BinaryIO, stream_info: StreamInfo, **kwargs: Any) -> bool:
        url = stream_info.url or ""
        mimetype = (stream_info.mimetype or "").lower()
        extension = (stream_info.extension or "").lower()

        url = unquote(url)

        if "instagram.com" not in url and "instagr.am" not in url:
            return False

        if extension in ACCEPTED_FILE_EXTENSIONS:
            return True
        for prefix in ACCEPTED_MIME_TYPE_PREFIXES:
            if mimetype.startswith(prefix):
                return True
        return False

    def convert(self, file_stream: BinaryIO, stream_info: StreamInfo, **kwargs: Any) -> DocumentConverterResult:
        encoding = "utf-8" if stream_info.charset is None else stream_info.charset
        soup = bs4.BeautifulSoup(file_stream, "html.parser", from_encoding=encoding)

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

        title = metadata.get("og:title") or metadata.get("title") or "Instagram post"
        author = metadata.get("author") or metadata.get("og:site_name") or ""
        description = metadata.get("og:description") or metadata.get("description") or ""
        media = metadata.get("og:video") or metadata.get("og:video:secure_url") or metadata.get("og:image") or ""

        md = "# Instagram\n\n"
        if title:
            md += f"## {title}\n\n"
        if author:
            md += f"- **Author:** {author}\n"
        if media:
            md += f"- **Media:** {media}\n\n"
            if media.endswith(('.mp4', '.mov')):
                md += f"<video controls src=\"{media}\"></video>\n\n"
            else:
                md += f"![instagram media]({media})\n\n"
        if description:
            md += f"### Description\n{description}\n"

        return DocumentConverterResult(markdown=md, title=title)
