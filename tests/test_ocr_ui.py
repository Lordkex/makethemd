import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import app
from paddleocr_tools.progress import OCRProgress


def walk(controls):
    for control in controls:
        yield control
        yield from walk(getattr(control, "controls", None) or [])
        content = getattr(control, "content", None)
        if isinstance(content, app.ft.Control):
            yield from walk([content])


class OCRInterfaceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.output = Path(temporary.name)
        self.page = MagicMock()
        self.page.controls = []
        self.page.overlay = []
        self.page.add.side_effect = lambda *controls: self.page.controls.extend(controls)
        self.md = MagicMock()
        self.jobs = []
        for patcher in (
            patch.dict("sys.modules", {"torch": None}),
            patch.object(app, "saved_output_dir", return_value=self.output),
            patch.object(app, "read_failed_links", return_value=[]),
            patch.object(app.threading, "Thread", side_effect=lambda target, **kw:
                         SimpleNamespace(start=lambda: self.jobs.append(target))),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        app.main(self.page, {
            "md": self.md, "files": [Path("document.pdf")], "links": "", "ocr": False,
            "audio_lang": "hu", "model": "turbo", "log": [],
        })
        controls = list(walk(self.page.controls))
        self.checkbox = next(c for c in controls if isinstance(c, app.ft.Checkbox))
        self.convert = next(c for c in controls if isinstance(c, app.ft.Button)
                            and c.content == app.t("btn_convert"))

    def test_checkbox_starts_setup_without_conversion_and_can_retry_failure(self):
        with patch.object(app, "ensure_ocr_environment", side_effect=[RuntimeError("offline"), None]) as setup:
            self.checkbox.value = True
            self.checkbox.on_change(None)
            self.assertTrue(self.checkbox.disabled)
            self.assertEqual(len(self.jobs), 1)
            self.checkbox.on_change(None)
            self.assertEqual(len(self.jobs), 1)
            self.jobs.pop(0)()
            self.assertFalse(self.checkbox.disabled)
            self.checkbox.on_change(None)
            self.jobs.pop(0)()
        self.assertEqual(setup.call_count, 2)
        self.md.convert.assert_not_called()

    def test_checked_conversion_prepares_readers_before_using_worker(self):
        events = []
        self.checkbox.value = True
        with patch.object(app, "ensure_ocr_environment", side_effect=lambda **kw: events.append("setup")), \
             patch.object(app, "convert_file_with_ocr", side_effect=lambda *a, **kw: (events.append("worker") or ("PDF plus OCR", 1))):
            self.convert.on_click(None)
            self.jobs.pop(0)()
        self.assertEqual(events, ["setup", "worker"])
        self.md.convert.assert_not_called()
        self.assertEqual((self.output / "document.md").read_text(), "PDF plus OCR")

    def test_setup_failure_prevents_output_and_document_conversion(self):
        self.checkbox.value = True
        with patch.object(app, "ensure_ocr_environment", side_effect=RuntimeError("offline")), \
             patch.object(app, "convert_file_with_ocr") as worker:
            self.convert.on_click(None)
            self.jobs.pop(0)()
        worker.assert_not_called()
        self.md.convert.assert_not_called()
        self.assertFalse((self.output / "document.md").exists())

    def test_unchecked_conversion_does_not_prepare_ocr(self):
        self.md.convert.return_value.text_content = "PDF text"
        with patch.object(app, "ensure_ocr_environment") as setup:
            self.convert.on_click(None)
            self.jobs.pop(0)()
        setup.assert_not_called()
        self.md.convert.assert_called_once()

    def test_live_progress_shows_count_elapsed_time_and_completion(self):
        self.checkbox.value = True
        controls = list(walk(self.page.controls))
        bar = next(c for c in controls if isinstance(c, app.ft.ProgressBar))

        def convert(*args, status, **kwargs):
            status(OCRProgress("OCR: 1/2", 12, 0.5))
            self.assertEqual(bar.value, 0.5)
            self.assertTrue(any(isinstance(c, app.ft.Text) and "OCR: 1/2" in str(c.value)
                                and "12" in str(c.value) for c in controls))
            return "PDF plus OCR", 1

        with patch.object(app, "ensure_ocr_environment"), patch.object(app, "convert_file_with_ocr", side_effect=convert):
            self.convert.on_click(None)
            self.jobs.pop(0)()
        self.assertEqual(bar.value, 1)
        self.assertEqual(bar.color, app.GREEN)


if __name__ == "__main__":
    unittest.main()
