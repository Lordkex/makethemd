import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import app
from test_ocr_ui import walk


URL = "https://www.youtube.com/watch?v=1CFgwfD_xYQ"
OTHER = "https://www.youtube.com/watch?v=JC4nR45J0Ds"


class LinkOverwriteTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.output = Path(temporary.name)
        self.done = self.output / "youtube_1CFgwfD_xYQ.md"
        self.jobs = []
        for patcher in (
            patch.dict("sys.modules", {"torch": None}),
            patch.object(app, "saved_output_dir", return_value=self.output),
            patch.object(app, "read_failed_links", return_value=[]),
            patch.object(app, "choose_output_path", side_effect=lambda path: path),
            patch.object(app.threading, "Thread", side_effect=lambda target, **kw:
                         SimpleNamespace(start=lambda: self.jobs.append(target))),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def convert(self, links, answer, result=("new text", "")):
        page = MagicMock()
        page.controls = []
        page.overlay = []
        page.add.side_effect = lambda *controls: page.controls.extend(controls)
        app.main(page, {"md": MagicMock(), "files": [], "links": "\n".join(links), "ocr": False,
                        "audio_lang": "hu", "model": "turbo", "log": []})
        button = next(c for c in walk(page.controls) if isinstance(c, app.ft.Button)
                      and c.content == app.t("btn_convert"))
        options = {"side_effect": result} if isinstance(result, Exception) else {"return_value": result}
        with patch.object(app, "confirm_overwrite_links", return_value=answer) as ask, \
             patch.object(app, "convert_link", **options) as worker:
            button.on_click(None)
            self.jobs.pop(0)()
        return ask, worker

    def test_yes_converts_again_and_overwrites_without_a_second_question(self):
        self.done.write_text("old text", encoding="utf-8")
        ask, worker = self.convert([URL], True)
        ask.assert_called_once_with(1)
        worker.assert_called_once()
        app.choose_output_path.assert_not_called()
        self.assertEqual(self.done.read_text(encoding="utf-8"), "new text")

    def test_no_keeps_the_file_and_makes_no_request(self):
        self.done.write_text("old text", encoding="utf-8")
        ask, worker = self.convert([URL], False)
        ask.assert_called_once_with(1)
        worker.assert_not_called()
        self.assertEqual(self.done.read_text(encoding="utf-8"), "old text")

    def test_nothing_finished_means_no_question(self):
        ask, worker = self.convert([URL], False)
        ask.assert_not_called()
        worker.assert_called_once()
        self.assertEqual(self.done.read_text(encoding="utf-8"), "new text")

    def test_the_question_is_asked_once_and_no_still_converts_new_links(self):
        self.done.write_text("old text", encoding="utf-8")
        ask, worker = self.convert([URL, OTHER], False)
        ask.assert_called_once_with(1)
        self.assertEqual(worker.call_count, 1)
        self.assertEqual(worker.call_args.args[1], OTHER)

    def test_failed_reconversion_keeps_the_old_file(self):
        self.done.write_text("old text", encoding="utf-8")
        self.convert([URL], True, result=RuntimeError("offline"))
        self.assertEqual(self.done.read_text(encoding="utf-8"), "old text")


if __name__ == "__main__":
    unittest.main()
