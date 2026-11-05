import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from paddleocr_tools import ocr_utils as ocr
from paddleocr_tools import ocr_worker as worker
from paddleocr_tools.progress import PROGRESS_PREFIX


class StreamProgressTests(unittest.TestCase):
    def run_child(self, source, **kwargs):
        return ocr._stream_worker([sys.executable, "-u", "-c", source], **kwargs)

    def test_silent_model_stage_keeps_elapsed_time_updating(self):
        events = []
        source = ("import time; print(" + repr(PROGRESS_PREFIX + json.dumps({"stage": "models"})) +
                  ", flush=True); time.sleep(1.3)")
        process = self.run_child(source, status=events.append)
        self.assertEqual(process.returncode, 0)
        model_events = [e for e in events if e.message == ocr.t("ocr_progress_models")]
        self.assertGreaterEqual(len(model_events), 2)
        self.assertGreater(model_events[-1].elapsed, model_events[0].elapsed + 0.8)
        self.assertTrue(all(e.fraction is None for e in model_events))

    def test_counts_follow_completed_images_and_diagnostics_are_preserved(self):
        messages = [
            {"stage": "images_found", "total": 2},
            {"stage": "image_start", "name": "first.png"},
            {"stage": "image_done", "name": "first.png", "completed": 1},
            {"stage": "image_start", "name": "second.png"},
        ]
        source = "import sys\n" + "\n".join(
            "print(" + repr(PROGRESS_PREFIX + json.dumps(event)) + ", flush=True)" for event in messages
        ) + "\nprint('model failure', file=sys.stderr)\nsys.exit(1)"
        events = []
        process = self.run_child(source, status=events.append)
        self.assertEqual(process.returncode, 1)
        self.assertIn("model failure", process.stderr)
        self.assertEqual([event.fraction for event in events][-3:], [0.0, 0.5, 0.5])
        self.assertIn("second.png", events[-1].message)
        self.assertNotIn(PROGRESS_PREFIX, process.stderr)

    def test_pdf_progress_counts_completed_pages_including_cached_pages(self):
        messages = [
            {"stage": "pdf_page", "page": 1, "total": 2, "completed": 0, "mode": "ocr"},
            {"stage": "pdf_page", "page": 1, "total": 2, "completed": 1, "mode": "ocr"},
            {"stage": "pdf_page", "page": 2, "total": 2, "completed": 2, "mode": "cached"},
        ]
        source = "\n".join("print(" + repr(PROGRESS_PREFIX + json.dumps(event)) + ", flush=True)"
                           for event in messages)
        events = []
        self.run_child(source, status=events.append)
        self.assertEqual([event.fraction for event in events][-3:], [0.0, 0.5, 1.0])
        self.assertIn(ocr.t("pdf_progress_cached"), events[-1].message)


class WorkerProgressTests(unittest.TestCase):
    def test_pdf_scan_reports_pages_and_total_before_extracting_image_bytes(self):
        events = []
        document = MagicMock()
        document.page_count = 2
        document.load_page.return_value.get_images.return_value = [(7,)]
        document.extract_image.return_value = {"ext": "png", "image": b"data"}
        fitz = MagicMock()
        fitz.open.return_value = document
        with patch.dict("sys.modules", {"fitz": fitz}), \
             patch.object(worker, "emit_progress", side_effect=lambda stage, **kw: events.append((stage, kw))):
            images = worker._pdf_images(Path("test.pdf"))
            self.assertEqual(next(images), ("oldal-1-kep-1.png", b"data"))
            self.assertEqual(events, [
                ("scan", {"completed": 1, "total": 2}),
                ("scan", {"completed": 2, "total": 2}),
                ("images_found", {"total": 2}),
            ])
            document.extract_image.assert_called_once()
            self.assertEqual(len(list(images)), 1)
        document.close.assert_called_once()

    def test_images_without_recognized_text_still_advance_completed_count(self):
        events = []
        with patch.object(worker, "emit_progress", side_effect=lambda stage, **kw: events.append((stage, kw))), \
             patch.object(worker, "extract_images", return_value=iter([("one.png", b"1"), ("two.png", b"2")])), \
             patch.object(worker, "create_ocr_engine", return_value=object()), \
             patch.object(worker, "ocr_image_bytes", side_effect=["", "text"]):
            images = worker.process_source(Path("document.pdf"))
        self.assertEqual(images, [{"name": "two.png", "text": "text"}])
        self.assertEqual([data["completed"] for stage, data in events if stage == "image_done"], [1, 2])

    def test_document_with_no_images_does_not_load_models(self):
        with patch.object(worker, "emit_progress"), \
             patch.object(worker, "extract_images", return_value=iter([])), \
             patch.object(worker, "create_ocr_engine") as engine:
            self.assertEqual(worker.process_source(Path("document.pdf")), [])
        engine.assert_not_called()


if __name__ == "__main__":
    unittest.main()
