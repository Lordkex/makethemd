"""Regression tests for the code-review fixes: URL handling, file naming and converter guards."""
import io
import sys
import unittest
from pathlib import Path

sys.modules.setdefault("torch", None)  # the app must import without Whisper

import app
from markitdown._stream_info import StreamInfo
from markitdown.converters import _transcribe_audio
from markitdown.converters._facebook_converter import FacebookConverter
from markitdown.converters._tiktok_converter import TikTokConverter
from markitdown.converters._url_utils import host_matches, youtube_video_id
from markitdown.converters._youtube_converter import YouTubeConverter


def html_info(url: str) -> StreamInfo:
    return StreamInfo(url=url, mimetype="text/html", extension=".html")


class BasenameSafetyTests(unittest.TestCase):
    MALICIOUS = (
        "https://www.youtube.com/watch?v=../../../evil",
        "https://www.youtube.com/watch?v=..\\..\\evil",
        "https://youtu.be/a:b",
        "https://www.tiktok.com/@user/photo/../../../../x",
        "https://example.com/../../etc/passwd",
    )

    def test_basename_never_leaves_output_folder(self):
        out = Path("/out").resolve()
        for url in self.MALICIOUS:
            with self.subTest(url=url):
                name = app.url_to_basename(url)
                self.assertRegex(name, r"^[A-Za-z0-9._-]+$")
                self.assertNotIn("..", name)
                self.assertEqual((out / f"{name}.md").resolve().parent, out)

    def test_same_video_in_different_url_forms_gets_one_name(self):
        expected = "youtube_1CFgwfD_xYQ"
        for url in ("https://www.youtube.com/watch?v=1CFgwfD_xYQ&t=30",
                    "https://youtu.be/1CFgwfD_xYQ?si=abc",
                    "https://m.youtube.com/shorts/1CFgwfD_xYQ",
                    "https://www.youtube.com/watch?feature=share&v=1CFgwfD_xYQ"):
            with self.subTest(url=url):
                self.assertEqual(app.url_to_basename(url), expected)

    def test_other_query_parameter_ending_in_v_is_not_the_video_id(self):
        # the old split("v=") picked "lv=1" up as the ID and merged different videos
        self.assertEqual(app.url_to_basename("https://www.youtube.com/watch?lv=1&v=abcdefghijk"),
                         "youtube_abcdefghijk")


class HostMatchingTests(unittest.TestCase):
    def test_youtube_lookalike_hosts_are_rejected(self):
        for url in ("https://notyoutube.com/watch?v=abcdefghijk",
                    "https://youtube.com.example.org/watch?v=abcdefghijk"):
            with self.subTest(url=url):
                self.assertFalse(app.is_youtube_url(url))
                self.assertIsNone(youtube_video_id(url))

    def test_youtube_video_id_forms(self):
        for url in ("https://www.youtube.com/watch?v=abcdefghijk",
                    "http://youtube.com/watch?v=abcdefghijk",
                    "https://youtu.be/abcdefghijk",
                    "https://www.youtube.com/shorts/abcdefghijk",
                    "https://www.youtube.com/live/abcdefghijk"):
            with self.subTest(url=url):
                self.assertEqual(youtube_video_id(url), "abcdefghijk")
        self.assertIsNone(youtube_video_id("https://www.youtube.com/@channel"))

    def test_site_name_in_query_does_not_claim_the_page(self):
        url = "https://blog.example.com/post?utm_source=facebook.com&ref=tiktok.com"
        self.assertFalse(host_matches(url, ("facebook.com",)))
        stream = io.BytesIO(b"")
        self.assertFalse(FacebookConverter().accepts(stream, html_info(url)))
        self.assertFalse(TikTokConverter().accepts(stream, html_info(url)))
        self.assertTrue(FacebookConverter().accepts(stream, html_info("https://m.facebook.com/watch/?v=1")))

    def test_short_youtube_links_reach_the_youtube_converter(self):
        stream = io.BytesIO(b"")
        for url in ("https://youtu.be/abcdefghijk", "https://www.youtube.com/shorts/abcdefghijk"):
            with self.subTest(url=url):
                self.assertTrue(YouTubeConverter().accepts(stream, html_info(url)))


class ConverterGuardTests(unittest.TestCase):
    def test_tiktok_page_without_item_struct_does_not_crash(self):
        page = (b'<html><head><title>t</title></head><body>'
                b'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application/json">'
                b'{"__DEFAULT_SCOPE__": {}}</script></body></html>')
        result = TikTokConverter().convert(io.BytesIO(page), html_info("https://www.tiktok.com/@u/video/1"))
        self.assertIn("# TikTok", result.markdown)

    def test_video_src_is_html_escaped(self):
        page = (b'<html><head><meta property="og:video" content="x&quot;&gt;&lt;img src=x onerror=alert(1)&gt;">'
                b'</head><body></body></html>')
        result = TikTokConverter().convert(io.BytesIO(page), html_info("https://www.tiktok.com/@u/video/1"))
        self.assertNotIn("<img", result.markdown.split("<video", 1)[1])

    def test_tqdm_progress_parses_runs_over_an_hour(self):
        line = " 50%|#####     | 9434/18868 [1:02:03<1:02:03, 2.53frames/s]"
        self.assertIsNotNone(_transcribe_audio._TQDM_RE.search(line))


class RunGuardTests(unittest.TestCase):
    def test_ffmpeg_path_is_not_added_when_missing(self):
        # without LOCALAPPDATA the WinGet path would be relative; it must never reach PATH
        if not app.local_appdata:
            self.assertNotIn(app.FFMPEG_BIN, app.os.environ.get("PATH", "").split(app.os.pathsep))


if __name__ == "__main__":
    unittest.main()
