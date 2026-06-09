#!/usr/bin/env python3 -m pytest
import io

from markitdown import MarkItDown, StreamInfo


def _make_meta_html(url: str, title: str, description: str, author: str, media: str) -> bytes:
    html = f"""
    <html>
      <head>
        <title>{title}</title>
        <meta property="og:title" content="{title}" />
        <meta property="og:description" content="{description}" />
        <meta name="author" content="{author}" />
        <meta property="og:video" content="{media}" />
      </head>
      <body>Test page</body>
    </html>
    """
    return html.encode("utf-8")


def _assert_social_result(result, platform: str, title: str, author: str, media: str, description: str):
    text = result.text_content
    assert platform in text
    assert title in text
    assert author in text
    assert media in text
    assert description in text


def test_instagram_converter_accepts_html_url():
    md = MarkItDown()
    html = _make_meta_html(
        url="https://www.instagram.com/p/ABC123/",
        title="Instagram Title",
        description="Instagram Description",
        author="insta_author",
        media="https://cdn.instagram.com/video.mp4",
    )
    result = md.convert_stream(
        io.BytesIO(html),
        stream_info=StreamInfo(url="https://www.instagram.com/p/ABC123/", mimetype="text/html"),
    )
    _assert_social_result(
        result,
        platform="Instagram",
        title="Instagram Title",
        author="insta_author",
        media="https://cdn.instagram.com/video.mp4",
        description="Instagram Description",
    )


def test_tiktok_converter_accepts_html_url():
    md = MarkItDown()
    html = _make_meta_html(
        url="https://www.tiktok.com/@user/video/1234567890",
        title="TikTok Title",
        description="TikTok Description",
        author="tiktok_user",
        media="https://v16m.tiktokcdn.com/video.mp4",
    )
    result = md.convert_stream(
        io.BytesIO(html),
        stream_info=StreamInfo(url="https://www.tiktok.com/@user/video/1234567890", mimetype="text/html"),
    )
    _assert_social_result(
        result,
        platform="TikTok",
        title="TikTok Title",
        author="tiktok_user",
        media="https://v16m.tiktokcdn.com/video.mp4",
        description="TikTok Description",
    )


def test_tiktok_converter_extracts_json_metadata():
    md = MarkItDown()
    html = b'''
    <html>
      <head>
        <script>{"__DEFAULT_SCOPE__":{"webapp.video-detail":{"itemInfo":{"itemStruct":{
            "desc":"Sample TikTok description",
            "author":{"nickname":"TikToker","uniqueId":"tiktok_user"},
            "music":{"title":"original sound","authorName":"TikToker"},
            "video":{"playAddr":"https://v16m.tiktokcdn.com/video.mp4"},
            "stats":{"diggCount":123,"commentCount":45,"shareCount":6,"playCount":789,"collectCount":10}
        }}}}}</script>
      </head>
      <body>Test page</body>
    </html>
    '''
    result = md.convert_stream(
        io.BytesIO(html),
        stream_info=StreamInfo(url="https://www.tiktok.com/@user/video/1234567890", mimetype="text/html"),
    )
    assert "TikTok" in result.text_content
    assert "Sample TikTok description" in result.text_content
    assert "TikToker" in result.text_content
    assert "https://v16m.tiktokcdn.com/video.mp4" in result.text_content


def test_facebook_converter_accepts_html_url():
    md = MarkItDown()
    html = _make_meta_html(
        url="https://www.facebook.com/watch/?v=987654321",
        title="Facebook Title",
        description="Facebook Description",
        author="fb_author",
        media="https://facebook.com/video.mp4",
    )
    result = md.convert_stream(
        io.BytesIO(html),
        stream_info=StreamInfo(url="https://www.facebook.com/watch/?v=987654321", mimetype="text/html"),
    )
    _assert_social_result(
        result,
        platform="Facebook",
        title="Facebook Title",
        author="fb_author",
        media="https://facebook.com/video.mp4",
        description="Facebook Description",
    )


def test_facebook_converter_extracts_transcript(monkeypatch):
    md = MarkItDown()
    html = b'''
    <html>
      <head>
        <script>
          var foo = {"video_delivery_response":{"transcript_urls":["https://example.com/captions.vtt"]}};
        </script>
      </head>
      <body>Test page</body>
    </html>
    '''

    class FakeResponse:
        status_code = 200
        text = "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHello world\n"

    def fake_get(url, headers=None, timeout=None):
        assert url == "https://example.com/captions.vtt"
        return FakeResponse()

    monkeypatch.setattr("markitdown.converters._facebook_converter.requests.get", fake_get)

    result = md.convert_stream(
        io.BytesIO(html),
        stream_info=StreamInfo(url="https://www.facebook.com/watch/?v=987654321", mimetype="text/html"),
    )

    assert "Transcript" in result.text_content
    assert "Hello world" in result.text_content


def test_linkedin_converter_accepts_html_url():
    md = MarkItDown()
    html = _make_meta_html(
        url="https://www.linkedin.com/posts/test-post",
        title="LinkedIn Title",
        description="LinkedIn Description",
        author="linkedin_author",
        media="https://media.linkedin.com/video.mp4",
    )
    result = md.convert_stream(
        io.BytesIO(html),
        stream_info=StreamInfo(url="https://www.linkedin.com/posts/test-post", mimetype="text/html"),
    )
    _assert_social_result(
        result,
        platform="LinkedIn",
        title="LinkedIn Title",
        author="linkedin_author",
        media="https://media.linkedin.com/video.mp4",
        description="LinkedIn Description",
    )
