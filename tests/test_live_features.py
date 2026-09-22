"""Opt-in live tests for search and song recognition (require network).

Run with ``RUN_LIVE=1 pytest tests/test_live_features.py``.

- Search hits YouTube's search endpoint (works from most IPs even when full
  video download needs cookies).
- Recognition uses a real 30s song preview from the public iTunes Search API
  (Shazam is Apple-owned, so these tracks are in its database).
"""

from __future__ import annotations

import os
import ssl
import urllib.parse
import urllib.request

import pytest

from bot import downloader, recognizer

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LIVE") != "1",
    reason="network test; set RUN_LIVE=1 to run",
)


async def test_live_youtube_search():
    results = await downloader.search("Coldplay Yellow", limit=3)
    assert results, "expected search results"
    assert any("yellow" in r.title.lower() for r in results)
    assert all(r.url.startswith("http") for r in results)


async def test_live_song_recognition(tmp_path):
    # Fetch a real song preview from the iTunes public API.
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    api = ("https://itunes.apple.com/search?entity=song&limit=1&term="
           + urllib.parse.quote("Coldplay Yellow"))
    import json

    data = json.load(urllib.request.urlopen(api, context=ctx))
    preview_url = data["results"][0]["previewUrl"]
    clip = tmp_path / "preview.m4a"
    clip.write_bytes(urllib.request.urlopen(preview_url, context=ctx).read())

    result = await recognizer.recognize(str(clip))
    assert result is not None
    assert "yellow" in result.title.lower()
    assert result.artist and "coldplay" in result.artist.lower()
