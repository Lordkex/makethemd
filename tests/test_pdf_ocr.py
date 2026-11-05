import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pymupdf
from PIL import Image, ImageDraw

from paddleocr_tools.pdf_ocr import convert_pdf, page_needs_ocr, text_is_unreliable


class TextQualityTests(unittest.TestCase):
    def test_unmapped_glyphs_control_characters_and_private_use_are_rejected(self):
        for text in ["A (cid:12) broken word", "\ufffd\ufffd\ufffd", "abc\x01\x02\x03", "\ue000\ue001\ue002"]:
            self.assertTrue(text_is_unreliable(text), repr(text))

    def test_normal_languages_and_punctuation_are_accepted(self):
        for text in ["", "English prose: 123, 45% — words.", "Árvíztűrő tükörfúrógép", "Русский текст", "日本語の文章"]:
            self.assertFalse(text_is_unreliable(text), repr(text))

    def test_unmapped_type3_font_triggers_ocr_even_if_text_has_no_cid_marker(self):
        page = MagicMock()
        page.get_fonts.return_value = [(7, "n/a", "Type3", "A", "A", "")]
        page.parent.xref_get_key.return_value = ("null", "null")
        self.assertTrue(page_needs_ocr(page, "Punctuation and apparently ordinary glyph IDs"))


class PageConversionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.source = self.directory / "document.pdf"
        self.events = []
        self.engine = MagicMock(return_value=object())
        self.recognize = MagicMock(return_value="Recovered page text.")

    def create_pdf(self, texts, scanned=False):
        with pymupdf.open() as document:
            for text in texts:
                page = document.new_page()
                if text:
                    page.insert_text((50, 60), text)
                if scanned:
                    image = Image.new("RGB", (400, 100), "white")
                    ImageDraw.Draw(image).text((20, 30), "Scanned page text 123", fill="black")
                    buffer = io.BytesIO()
                    image.save(buffer, format="PNG")
                    page.insert_image(pymupdf.Rect(50, 100, 450, 200), stream=buffer.getvalue())
            document.save(self.source)

    def convert(self, cache=False):
        return convert_pdf(self.source, self.engine, self.recognize,
                           lambda stage, **details: self.events.append((stage, details)),
                           cache_root=self.directory / "cache" if cache else None)

    def test_mixed_pdf_replaces_broken_text_in_page_order_without_duplication(self):
        self.create_pdf(["Healthy first page with ordinary readable text.", "Broken (cid:12) content"])
        result = self.convert()
        markdown = result["markdown"]
        self.assertEqual([page["method"] for page in result["pdf_pages"]], ["text", "ocr"])
        self.assertLess(markdown.index("Healthy first page"), markdown.index("Recovered page text"))
        self.assertEqual(markdown.count("Recovered page text"), 1)
        self.assertNotIn("(cid:", markdown)
        self.assertEqual(result["images"], [])
        self.assertEqual(result["ocr_pages"], 1)
        self.engine.assert_called_once()
        self.recognize.assert_called_once()
        self.assertTrue(any(stage == "pdf_page" and details["page"] == 2 and details["mode"] == "ocr"
                            for stage, details in self.events))

    def test_readable_and_blank_pages_do_not_load_models(self):
        self.create_pdf(["A healthy document with enough readable text.", ""])
        result = self.convert()
        self.assertEqual(result["ocr_pages"], 0)
        self.engine.assert_not_called()
        self.assertEqual([page["method"] for page in result["pdf_pages"]], ["text", "text"])

    def test_scanned_page_uses_full_page_rendering(self):
        self.create_pdf([""], scanned=True)
        result = self.convert()
        self.assertEqual(result["ocr_pages"], 1)
        rendered = self.recognize.call_args.args[1]
        with Image.open(io.BytesIO(rendered)) as image:
            self.assertGreater(image.height, 1000)
        self.assertIn("Recovered page text", result["markdown"])

    def test_diagrams_on_readable_pages_are_still_recognized_in_the_same_page(self):
        self.create_pdf(["Ordinary document text with an embedded diagram."], scanned=True)
        result = self.convert()
        self.assertEqual(result["ocr_pages"], 0)
        self.assertIn("Recovered page text", result["markdown"])
        self.recognize.assert_called_once()

    def test_cached_pages_skip_ocr_and_source_changes_invalidate_cache(self):
        self.create_pdf(["Broken (cid:12) content"])
        self.convert(cache=True)
        self.engine.reset_mock()
        self.recognize.reset_mock()
        result = self.convert(cache=True)
        self.engine.assert_not_called()
        self.recognize.assert_not_called()
        self.assertEqual(result["pdf_pages"][0]["method"], "cached")
        self.create_pdf(["Different broken (cid:13) content"])
        self.convert(cache=True)
        self.recognize.assert_called_once()

    def test_retry_keeps_pages_completed_before_an_ocr_failure(self):
        self.create_pdf(["Broken (cid:12) content", "Broken (cid:13) content"])
        self.recognize.side_effect = ["First page recovered.", RuntimeError("recognition stopped")]
        with self.assertRaisesRegex(RuntimeError, "recognition stopped"):
            self.convert(cache=True)
        self.recognize.reset_mock()
        self.recognize.side_effect = None
        self.recognize.return_value = "Second page recovered."
        result = self.convert(cache=True)
        self.recognize.assert_called_once()
        self.assertEqual([page["method"] for page in result["pdf_pages"]], ["cached", "ocr"])

    def test_unusable_recognition_is_not_saved_as_a_successful_page(self):
        self.create_pdf(["Broken (cid:12) document with substantial text"])
        self.recognize.return_value = ""
        with self.assertRaises(RuntimeError):
            self.convert(cache=True)
        self.assertEqual(list((self.directory / "cache").rglob("*.json")), [])

    def test_damaged_cache_file_is_recognized_again(self):
        self.create_pdf(["Broken (cid:12) content"])
        self.convert(cache=True)
        cache_file = next((self.directory / "cache").rglob("*.json"))
        cache_file.write_text('{"text":', encoding="utf-8")
        self.recognize.reset_mock()
        self.convert(cache=True)
        self.recognize.assert_called_once()
        self.assertEqual(json.loads(cache_file.read_text())["text"], "Recovered page text.")


if __name__ == "__main__":
    unittest.main()
