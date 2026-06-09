import io
import shutil

import pytest

from markitdown import StreamInfo
from markitdown.converters import EbookConverter
from markitdown._exceptions import MissingDependencyException


def test_ebook_converter_accepts_supported_extensions() -> None:
    converter = EbookConverter()

    assert converter.accepts(io.BytesIO(b""), StreamInfo(extension=".azw3"))
    assert converter.accepts(io.BytesIO(b""), StreamInfo(extension=".mobi"))
    assert converter.accepts(io.BytesIO(b""), StreamInfo(extension=".fb2"))


def test_ebook_converter_rejects_unsupported_extension() -> None:
    converter = EbookConverter()

    assert not converter.accepts(io.BytesIO(b""), StreamInfo(extension=".pdf"))
    assert not converter.accepts(io.BytesIO(b""), StreamInfo(extension=".txt"))


def test_ebook_converter_missing_dependency_raises() -> None:
    converter = EbookConverter()
    if shutil.which("ebook-convert") is not None:
        pytest.skip("ebook-convert is installed; skipping missing-dependency test")

    with pytest.raises(MissingDependencyException):
        converter.convert(
            io.BytesIO(b"fake ebook content"),
            StreamInfo(extension=".mobi"),
            ebook_convert_path="/nonexistent/ebook-convert",
        )
