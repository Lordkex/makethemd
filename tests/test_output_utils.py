import tempfile
import unittest
from pathlib import Path

import app
from output_utils import (
    FAILED_LINKS_NAME, read_failed_links, record_link_result, save_settings, saved_output_dir,
)


URL_A = "https://www.youtube.com/watch?v=1CFgwfD_xYQ"
URL_B = "https://www.youtube.com/watch?v=NgFhx0qGv04"


class FailedLinksTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.out_dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_failure_is_recorded_and_success_removes_it(self):
        record_link_result(self.out_dir, URL_A, "felirat-API\nblokk")
        record_link_result(self.out_dir, URL_B, "nincs felirat")
        failed = read_failed_links(self.out_dir)
        self.assertEqual(list(failed), [URL_A, URL_B])
        self.assertTrue(failed[URL_A].endswith("– felirat-API blokk"))

        record_link_result(self.out_dir, URL_A)
        self.assertEqual(list(read_failed_links(self.out_dir)), [URL_B])

        record_link_result(self.out_dir, URL_B)
        self.assertFalse((self.out_dir / FAILED_LINKS_NAME).exists())

    def test_saved_list_loads_as_plain_link_list(self):
        record_link_result(self.out_dir, URL_A, "hiba")
        text = (self.out_dir / FAILED_LINKS_NAME).read_text(encoding="utf-8")
        self.assertEqual(app.parse_link_list(text), [URL_A])

    def test_missing_file_means_no_failures(self):
        self.assertEqual(read_failed_links(self.out_dir), {})
        record_link_result(self.out_dir, URL_A)  # sikeres, listán sem volt: nem hoz létre fájlt
        self.assertFalse((self.out_dir / FAILED_LINKS_NAME).exists())

    def test_already_converted_matches_existing_output(self):
        self.assertFalse(app.already_converted(self.out_dir, URL_A))
        (self.out_dir / "youtube_1CFgwfD_xYQ.md").write_text("# YouTube\n", encoding="utf-8")
        self.assertTrue(app.already_converted(self.out_dir, URL_A + "&t=42s"))


class SettingsTests(unittest.TestCase):
    def test_output_dir_survives_restart_and_falls_back_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = Path(tmp) / "settings.json"
            default = Path(tmp) / "default"
            chosen = Path(tmp) / "sources"
            chosen.mkdir()
            self.assertEqual(saved_output_dir(default, settings), default)

            save_settings(settings, output_dir=str(chosen))
            self.assertEqual(saved_output_dir(default, settings), chosen)

            chosen.rmdir()  # a mentett mappa közben megszűnt → alapértelmezett
            self.assertEqual(saved_output_dir(default, settings), default)


if __name__ == "__main__":
    unittest.main()
