import unittest
from unittest.mock import MagicMock, patch

import app


URL = "https://www.youtube.com/watch?v=1CFgwfD_xYQ"
PAGE_TEXT = "# YouTube\n\n## Cím\n"


class YoutubeBlockTests(unittest.TestCase):
    def test_captions_exist_but_not_served_means_blocked(self):
        info = {"title": "Cím", "duration": 60, "automatic_captions": {"hu": [{}]}}
        with patch.object(app, "probe_media_info", return_value=info), \
             patch.object(app, "IS_YOUTUBE_TRANSCRIPT_CAPABLE", True):
            with self.assertRaises(app.TranscriptMissingError) as ctx:
                app.ensure_real_transcript(URL, PAGE_TEXT)
        self.assertTrue(ctx.exception.blocked)
        self.assertEqual(ctx.exception.candidate["url"], URL)

    def test_missing_library_is_not_reported_as_a_block(self):
        info = {"title": "Cím", "duration": 60, "automatic_captions": {"hu": [{}]}}
        with patch.object(app, "probe_media_info", return_value=info), \
             patch.object(app, "IS_YOUTUBE_TRANSCRIPT_CAPABLE", False):
            with self.assertRaises(app.TranscriptMissingError) as ctx:
                app.ensure_real_transcript(URL, PAGE_TEXT)
        self.assertFalse(ctx.exception.blocked)
        self.assertEqual(str(ctx.exception), app.t("err_transcript_lib_missing"))
        self.assertEqual(ctx.exception.candidate["url"], URL)

    def test_no_captions_is_not_a_block(self):
        with patch.object(app, "probe_media_info", return_value={"title": "Cím"}):
            with self.assertRaises(app.TranscriptMissingError) as ctx:
                app.ensure_real_transcript(URL, PAGE_TEXT)
        self.assertFalse(ctx.exception.blocked)

    def test_converter_does_not_retry_when_blocked(self):
        from markitdown.converters import _youtube_converter as yc

        if not yc.IS_YOUTUBE_TRANSCRIPT_CAPABLE:
            self.skipTest("youtube-transcript-api nincs telepítve")
        operation = MagicMock(side_effect=yc.RequestBlocked("1CFgwfD_xYQ"))
        with patch.object(yc.time, "sleep") as sleep:
            with self.assertRaises(yc.RequestBlocked):
                yc.YouTubeConverter()._retry_operation(operation, retries=3, delay=2)
        operation.assert_called_once()
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
