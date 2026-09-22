"""Unit tests for the pure downloader logic (no network)."""

from __future__ import annotations

import pytest

from bot import downloader
from bot.config import load_config


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.youtube.com/watch?v=abc123", "youtube"),
        ("https://youtu.be/abc123", "youtube"),
        ("https://m.youtube.com/watch?v=x", "youtube"),
        ("https://www.instagram.com/reel/CabcDEF/", "instagram"),
        ("https://instagr.am/p/xyz/", "instagram"),
        ("https://vimeo.com/12345", "other"),
        ("https://example.com/video.mp4", "other"),
    ],
)
def test_detect_platform(url, expected):
    assert downloader.detect_platform(url) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("look https://youtu.be/x cool", "https://youtu.be/x"),
        ("no link here", None),
        ("http://a.b/c and http://d.e/f", "http://a.b/c"),
    ],
)
def test_find_url(text, expected):
    assert downloader.find_url(text) == expected


def test_build_ydl_opts_mp3():
    opts = downloader.build_ydl_opts("mp3", "/tmp/out")
    assert opts["format"] == "bestaudio/best"
    pps = opts["postprocessors"]
    assert pps[0]["key"] == "FFmpegExtractAudio"
    assert pps[0]["preferredcodec"] == "mp3"
    assert "merge_output_format" not in opts


def test_build_ydl_opts_1080_video():
    opts = downloader.build_ydl_opts("1080", "/tmp/out", cookiefile="/tmp/c.txt",
                                     proxy="http://p:1")
    assert "height<=1080" in opts["format"]
    assert opts["merge_output_format"] == "mp4"
    assert opts["cookiefile"] == "/tmp/c.txt"
    assert opts["proxy"] == "http://p:1"
    assert "postprocessors" not in opts


def test_quality_label():
    assert "MP3" in downloader.quality_label("mp3")
    assert downloader.quality_label("720") == "🎬 720p"


@pytest.mark.parametrize(
    "n,expected",
    [(0, "0 B"), (512, "512 B"), (1536, "1.5 KB"), (5 * 1024 * 1024, "5.0 MB")],
)
def test_human_size(n, expected):
    assert downloader.human_size(n) == expected


@pytest.mark.parametrize(
    "seconds,expected",
    [(None, "?"), (0, "?"), (5, "0:05"), (75, "1:15"), (3661, "1:01:01")],
)
def test_format_duration(seconds, expected):
    assert downloader.format_duration(seconds) == expected


def test_run_search_parses_entries(monkeypatch):
    class FakeYDL:
        def __init__(self, opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, target, download=False):
            assert target.startswith("ytsearch")
            return {
                "entries": [
                    {"title": "A", "url": "https://youtu.be/a", "duration": 100,
                     "channel": "Chan"},
                    {"title": "B", "id": "bbb", "duration": 200},
                    None,
                ]
            }

    monkeypatch.setattr(downloader.yt_dlp, "YoutubeDL", FakeYDL)
    results = downloader._run_search("query", 5, None, None)
    assert len(results) == 2
    assert results[0].url == "https://youtu.be/a"
    assert results[0].uploader == "Chan"
    # Entry with only an id gets a canonical watch URL.
    assert results[1].url == "https://www.youtube.com/watch?v=bbb"


def test_download_rejects_unknown_quality():
    import asyncio

    with pytest.raises(ValueError):
        asyncio.run(downloader.download("https://x", "4k"))


def test_classify_error_auth():
    err = downloader._classify_error("ERROR: Sign in to confirm you're not a bot")
    assert isinstance(err, downloader.AuthRequiredError)

    err2 = downloader._classify_error("Instagram sent an empty media response")
    assert isinstance(err2, downloader.AuthRequiredError)

    err3 = downloader._classify_error("HTTP Error 404: Not Found")
    assert isinstance(err3, downloader.DownloadError)
    assert not isinstance(err3, downloader.AuthRequiredError)


def test_config_cookie_materialization(tmp_path):
    cfg = load_config(
        {
            "BOT_TOKEN": "1:token",
            "COOKIES_TXT": "# Netscape HTTP Cookie File\\nline",
            "YOUTUBE_COOKIES_TXT": "# youtube-specific",
        }
    )
    yt = cfg.cookie_file_for("youtube")
    ig = cfg.cookie_file_for("instagram")
    assert yt is not None and ig is not None
    with open(yt) as fh:
        assert "youtube-specific" in fh.read()
    with open(ig) as fh:
        # instagram falls back to COOKIES_TXT, with escaped newline expanded
        content = fh.read()
        assert "Netscape" in content and "\n" in content


def test_config_no_cookies():
    cfg = load_config({"BOT_TOKEN": "1:token"})
    assert cfg.cookie_file_for("youtube") is None


def test_config_requires_token():
    with pytest.raises(RuntimeError):
        load_config({})


def test_config_webhook_from_render_url():
    cfg = load_config({"BOT_TOKEN": "1:t", "RENDER_EXTERNAL_URL": "https://x.onrender.com/"})
    assert cfg.use_webhook is True
    assert cfg.webhook_url == "https://x.onrender.com"
