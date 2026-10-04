import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import requests

import app
import facebook_audio


URL = "https://www.facebook.com/reel/1633195638310204"
DESCRIPTION = "# Facebook\n\n## Video title\n\n### Description\nPost description.\n"
TRANSCRIPT = "### Audio Transcript:\nThe spoken words."


class FacebookFlowTests(unittest.TestCase):
    def test_description_only_downloads_audio_and_uses_turbo(self):
        converter = MagicMock()
        converter.convert.side_effect = [SimpleNamespace(text_content=DESCRIPTION),
                                         SimpleNamespace(text_content=TRANSCRIPT)]
        progress = MagicMock()
        with patch.object(app, "fetch_media_captions", return_value=None), \
             patch.object(app, "download_media_audio", return_value=Path("audio.mp3")) as download:
            text, method = app.convert_link(converter, URL, "fr", progress_fn=progress)
        self.assertIn(DESCRIPTION.strip(), text)
        self.assertIn("### Transcript\nThe spoken words.", text)
        self.assertEqual(method, " [whisper]")
        self.assertEqual(download.call_args.args[0], URL)
        self.assertEqual(converter.convert.call_args.kwargs["whisper_model"], "turbo")
        self.assertEqual(converter.convert.call_args.kwargs["whisper_language"], "fr")
        self.assertIs(converter.convert.call_args.kwargs["whisper_progress_fn"], progress)
        self.assertFalse(Path(download.call_args.args[1]).exists())

    def test_existing_transcript_does_not_download_audio(self):
        original = DESCRIPTION + "\n### Transcript\nExisting captions.\n"
        converter = MagicMock()
        converter.convert.return_value.text_content = original
        with patch.object(app, "download_media_audio") as download:
            self.assertEqual(app.convert_link(converter, URL, None), (original, " [felirat]"))
        download.assert_not_called()

    def test_captions_are_used_without_whisper(self):
        converter = MagicMock()
        converter.convert.return_value.text_content = DESCRIPTION
        with patch.object(app, "fetch_media_captions", return_value="Actual captions."), \
             patch.object(app, "download_media_audio") as download:
            text, method = app.convert_link(converter, URL, None)
        self.assertIn("### Transcript\nActual captions.", text)
        self.assertEqual(method, " [felirat]")
        download.assert_not_called()

    def test_html_failure_still_transcribes_audio(self):
        converter = MagicMock()
        converter.convert.side_effect = [requests.HTTPError("403"), SimpleNamespace(text_content=TRANSCRIPT)]
        with patch.object(app, "fetch_media_captions", return_value=None), \
             patch.object(app, "download_media_audio", return_value=Path("audio.mp3")):
            text, _ = app.convert_link(converter, URL, None, "small")
        self.assertIn(URL, text)
        self.assertIn("The spoken words.", text)
        self.assertEqual(converter.convert.call_args.kwargs["whisper_model"], "small")

    def test_missing_audio_transcript_is_an_error(self):
        converter = MagicMock()
        converter.convert.side_effect = [SimpleNamespace(text_content=DESCRIPTION),
                                         SimpleNamespace(text_content="Title: audio metadata")]
        with patch.object(app, "fetch_media_captions", return_value=None), \
             patch.object(app, "download_media_audio", return_value=Path("audio.mp3")):
            with self.assertRaisesRegex(RuntimeError, "nem készült átirat"):
                app.convert_link(converter, URL, None)

    def test_description_and_empty_heading_are_not_completed_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "facebook.md"
            for text in (DESCRIPTION, DESCRIPTION + "\n### Transcript\n", "### Transcript\n\n### Description\nPost text"):
                path.write_text(text, encoding="utf-8")
                self.assertFalse(app.output_has_transcript(path))
            path.write_text(DESCRIPTION + "\n### Transcript\nSpoken words.", encoding="utf-8")
            self.assertTrue(app.output_has_transcript(path))

    def test_ytdlp_failure_uses_free_provider(self):
        with patch.object(app, "_download_media_with_ytdlp", side_effect=RuntimeError("Facebook blocked")), \
             patch.object(app, "download_facebook_audio", return_value=Path("fallback.mp3")) as fallback:
            path = app.download_media_audio(URL, "tmp")
        self.assertEqual(path, Path("fallback.mp3"))
        self.assertEqual(fallback.call_args.args, (URL, "tmp"))

    def test_other_sites_keep_their_download_path(self):
        with patch.object(app, "_download_media_with_ytdlp", return_value=Path("tiktok.mp4")), \
             patch.object(app, "download_facebook_audio") as fallback:
            self.assertEqual(app.download_media_audio("https://www.tiktok.com/video/123", "tmp"), Path("tiktok.mp4"))
        fallback.assert_not_called()

    def test_regular_page_keeps_markdown_conversion(self):
        converter = MagicMock()
        converter.convert.return_value.text_content = "# Article\nArticle text."
        self.assertEqual(app.convert_link(converter, "https://example.org/article", None),
                         ("# Article\nArticle text.", ""))


class FreeProviderTests(unittest.TestCase):
    def response(self, *, payload=None, content_type="audio/mp4", content=b"audio bytes"):
        response = MagicMock()
        response.__enter__.return_value = response
        response.json.return_value = payload
        response.headers = {"Content-Type": content_type}
        response.iter_content.return_value = [content]
        return response

    def test_audio_is_preferred_and_cdn_failure_retries_proxy(self):
        session = MagicMock()
        session.__enter__.return_value = session
        session.post.return_value = self.response(payload={"success": True, "data": {"formats": [
            {"url": "https://cdn.example/video.mp4", "ext": "mp4"},
            {"url": "https://cdn.example/audio.m4a", "ext": "m4a", "vcodec": "none"},
        ]}})
        session.get.side_effect = [requests.HTTPError("403"), self.response()]
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(facebook_audio.requests, "Session", return_value=session), \
             patch.object(facebook_audio, "convert_to_mp3", return_value=Path(directory) / "facebook_audio.mp3") as convert:
            path = facebook_audio.download_facebook_audio(URL, directory)
            self.assertEqual(path.suffix, ".mp3")
            self.assertEqual(session.get.call_args_list[0].args[0], "https://cdn.example/audio.m4a")
            self.assertEqual(session.get.call_args.args[0], facebook_audio.FDOWN_PROXY)
            self.assertEqual(session.get.call_args.kwargs["params"]["url"], "https://cdn.example/audio.m4a")
            self.assertEqual(convert.call_count, 1)
            self.assertFalse((Path(directory) / "facebook_source.media").exists())

    def test_provider_error_is_reported(self):
        session = MagicMock()
        session.__enter__.return_value = session
        session.post.return_value = self.response(payload={"success": False, "error": "Video unavailable"})
        with patch.object(facebook_audio.requests, "Session", return_value=session):
            with self.assertRaisesRegex(RuntimeError, "Video unavailable"):
                facebook_audio.download_facebook_audio(URL, "tmp")
        session.get.assert_not_called()

    def test_html_is_rejected_and_partial_source_cleaned(self):
        session = MagicMock()
        session.__enter__.return_value = session
        session.post.return_value = self.response(payload={"success": True, "data": {"formats": [
            {"url": "https://cdn.example/audio.m4a", "ext": "m4a"},
        ]}})
        session.get.return_value = self.response(content_type="text/html", content=b"login page")
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(facebook_audio.requests, "Session", return_value=session), \
             patch.object(facebook_audio, "convert_to_mp3") as convert:
            with self.assertRaisesRegex(RuntimeError, "szöveges választ"):
                facebook_audio.download_facebook_audio(URL, directory)
            self.assertEqual(list(Path(directory).iterdir()), [])
        convert.assert_not_called()

    def test_non_facebook_hosts_are_rejected(self):
        for url in ("https://facebook.com.example.org/reel/1", "https://example.org/facebook.com", "https://fakefb.watch/video"):
            self.assertFalse(facebook_audio.is_facebook_url(url))
            self.assertFalse(app.is_media_site(url))
        self.assertTrue(facebook_audio.is_facebook_url("https://fb.watch/abc"))
        self.assertTrue(facebook_audio.is_facebook_url("https://m.facebook.com/watch/?v=123"))


if __name__ == "__main__":
    unittest.main()
