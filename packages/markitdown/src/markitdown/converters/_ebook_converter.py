import os
import shutil
import subprocess
import tempfile
from typing import Any, BinaryIO
from pathlib import Path

from .._base_converter import DocumentConverter, DocumentConverterResult
from .._exceptions import MissingDependencyException
from .._stream_info import StreamInfo
from ._epub_converter import EpubConverter

ACCEPTED_MIME_TYPE_PREFIXES = [
    "application/x-mobipocket-ebook",
    "application/x-fictionbook+xml",
    "application/fb2",
]

ACCEPTED_FILE_EXTENSIONS = [".azw3", ".mobi", ".fb2"]

# Common Calibre installation paths on Windows
CALIBRE_PATHS = [
    Path("C:\\Program Files\\Calibre2"),
    Path("C:\\Program Files (x86)\\Calibre2"),
    Path("C:\\Program Files\\Calibre"),
    Path("C:\\Program Files (x86)\\Calibre"),
]


def _find_ebook_convert() -> str | None:
    """Find ebook-convert executable, checking PATH and common Calibre paths."""
    # First, try shutil.which
    result = shutil.which("ebook-convert")
    if result:
        return result

    # Try common Windows Calibre paths
    for calibre_path in CALIBRE_PATHS:
        ebook_convert = calibre_path / "ebook-convert.exe"
        if ebook_convert.exists():
            return str(ebook_convert)

    return None


class EbookConverter(DocumentConverter):
    """Convert Calibre-supported ebook formats to Markdown via ebook-convert."""

    def accepts(
        self,
        file_stream: BinaryIO,
        stream_info: StreamInfo,
        **kwargs: Any,
    ) -> bool:
        mimetype = (stream_info.mimetype or "").lower()
        extension = (stream_info.extension or "").lower()

        if extension in ACCEPTED_FILE_EXTENSIONS:
            return True

        for prefix in ACCEPTED_MIME_TYPE_PREFIXES:
            if mimetype.startswith(prefix):
                return True

        return False

    def convert(
        self,
        file_stream: BinaryIO,
        stream_info: StreamInfo,
        **kwargs: Any,
    ) -> DocumentConverterResult:
        ebook_convert_path = kwargs.get("ebook_convert_path")
        if ebook_convert_path is None:
            ebook_convert_path = _find_ebook_convert()

        if ebook_convert_path is None:
            raise MissingDependencyException(
                "Ebook conversion requires Calibre's `ebook-convert` executable. "
                "Install Calibre from https://calibre-ebook.com and ensure it is installed "
                "or pass `ebook_convert_path` to MarkItDown. "
                "Checked PATH and common Windows paths: " + ", ".join(str(p) for p in CALIBRE_PATHS)
            )

        extension = (stream_info.extension or "").lower()
        if not extension:
            extension = ".ebook"

        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = os.path.join(temp_dir, f"input{extension}")
            output_path = os.path.join(temp_dir, "output.epub")

            file_stream.seek(0)
            with open(source_path, "wb") as source_file:
                source_file.write(file_stream.read())

            try:
                completed = subprocess.run(
                    [ebook_convert_path, source_path, output_path],
                    capture_output=True,
                    text=True,
                )
            except FileNotFoundError as exc:
                raise MissingDependencyException(
                    "Ebook conversion requires Calibre's `ebook-convert` executable. "
                    "Install Calibre and ensure `ebook-convert` is available on PATH, "
                    "or pass `ebook_convert_path` to MarkItDown."
                ) from exc

            if completed.returncode != 0:
                raise RuntimeError(
                    "ebook-convert failed to convert the ebook. "
                    f"stderr={completed.stderr.strip()}"
                )

            with open(output_path, "rb") as output_file:
                result = EpubConverter().convert(
                    output_file,
                    StreamInfo(
                        mimetype="application/epub+zip",
                        extension=".epub",
                        filename=os.path.basename(output_path),
                    ),
                )

        return DocumentConverterResult(markdown=result.markdown, title=result.title)
