"""Hermetic end-to-end test of the real yt-dlp + ffmpeg pipeline.

Generates a tiny H.264/AAC clip with ffmpeg, serves it over localhost, and runs
it through ``downloader.download`` for both a video quality and MP3 extraction.
No external network is required, so this exercises the actual download + ffmpeg
merge/convert path deterministically. Skipped only if ffmpeg is unavailable.
"""

from __future__ import annotations

import functools
import http.server
import os
import shutil
import socketserver
import subprocess
import threading

import pytest

from bot import downloader

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None, reason="ffmpeg is required for this test"
)


@pytest.fixture(scope="module")
def served_clip(tmp_path_factory):
    assets = tmp_path_factory.mktemp("assets")
    clip = assets / "clip.mp4"
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=10",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
            "-shortest", str(clip), "-y",
        ],
        check=True,
        capture_output=True,
    )

    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(assets)
    )
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}/clip.mp4"
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


async def test_pipeline_video_download(served_clip, tmp_path):
    result = await downloader.download(served_clip, "720", base_dir=str(tmp_path))
    assert os.path.isfile(result.path)
    assert result.is_audio is False
    assert result.size > 0


async def test_pipeline_mp3_extraction(served_clip, tmp_path):
    result = await downloader.download(served_clip, "mp3", base_dir=str(tmp_path))
    assert os.path.isfile(result.path)
    assert result.ext == "mp3"
    assert result.is_audio is True
    assert result.size > 0
    # Confirm ffmpeg produced a valid MP3 container.
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=format_name",
         "-of", "default=noprint_wrappers=1:nokey=1", result.path],
        capture_output=True, text=True,
    )
    assert "mp3" in probe.stdout
