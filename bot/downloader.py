"""Thin async wrapper around yt-dlp for the bot.

The module is intentionally free of any Telegram dependency so it can be unit
tested and reused in isolation.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import tempfile
from dataclasses import dataclass

import yt_dlp

logger = logging.getLogger(__name__)

INSTAGRAM_HOSTS = ("instagram.com", "instagr.am", " instagram.")
YOUTUBE_HOSTS = ("youtube.com", "youtu.be", "youtube-nocookie.com")

_URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)

# Quality keys the bot understands. "mp3" means audio-only extraction; the rest
# are maximum video heights in pixels.
AUDIO_QUALITY = "mp3"
VIDEO_QUALITIES = ("360", "480", "720", "1080")
ALL_QUALITIES = (AUDIO_QUALITY, *VIDEO_QUALITIES)


class DownloadError(RuntimeError):
    """Raised when a download fails for a reason worth showing to the user."""


class AuthRequiredError(DownloadError):
    """Raised when the source needs login cookies (YouTube/Instagram gating)."""


@dataclass
class DownloadResult:
    path: str
    title: str
    ext: str
    is_audio: bool

    @property
    def size(self) -> int:
        return os.path.getsize(self.path)


def find_url(text: str) -> str | None:
    """Return the first http(s) URL found in ``text``."""

    if not text:
        return None
    match = _URL_RE.search(text)
    return match.group(0) if match else None


def detect_platform(url: str) -> str:
    """Classify ``url`` into ``youtube``, ``instagram`` or ``other``."""

    lowered = url.lower()
    if any(host in lowered for host in YOUTUBE_HOSTS):
        return "youtube"
    if any(host in lowered for host in INSTAGRAM_HOSTS):
        return "instagram"
    return "other"


def quality_label(quality: str) -> str:
    """Human-friendly label for a quality key."""

    if quality == AUDIO_QUALITY:
        return "🎵 MP3 (audio)"
    return f"🎬 {quality}p"


def build_ydl_opts(quality: str, outdir: str, cookiefile: str | None = None,
                   proxy: str | None = None) -> dict:
    """Build a yt-dlp options dict for a given ``quality`` selection."""

    opts: dict = {
        "outtmpl": os.path.join(outdir, "%(title).80B.%(ext)s"),
        "restrictfilenames": True,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "nocheckcertificate": True,
        "retries": 3,
        "socket_timeout": 30,
        # Reduce chance of hanging forever on a stalled fragment.
        "concurrent_fragment_downloads": 1,
    }
    if cookiefile:
        opts["cookiefile"] = cookiefile
    if proxy:
        opts["proxy"] = proxy

    if quality == AUDIO_QUALITY:
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ]
    else:
        height = int(quality)
        # Prefer mp4/m4a so the merged file plays inline in Telegram, but fall
        # back to whatever is available at or below the requested height.
        opts["format"] = (
            f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/"
            f"bestvideo[height<={height}]+bestaudio/"
            f"best[height<={height}]/best"
        )
        opts["merge_output_format"] = "mp4"

    return opts


def _classify_error(message: str) -> DownloadError:
    lowered = message.lower()
    if (
        "sign in to confirm" in lowered
        or "use --cookies" in lowered
        or "login required" in lowered
        or "empty media response" in lowered
        or "requested content is not available" in lowered
        or "private" in lowered and "video" in lowered
    ):
        return AuthRequiredError(message)
    return DownloadError(message)


def _run_download(url: str, opts: dict, outdir: str) -> DownloadResult:
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except yt_dlp.utils.DownloadError as exc:  # pragma: no cover - message varies
        raise _classify_error(str(exc)) from exc

    if info is None:
        raise DownloadError("yt-dlp returned no information for this URL.")

    # A playlist slipped through despite noplaylist; take the first entry.
    if "entries" in info:
        entries = [e for e in info["entries"] if e]
        if not entries:
            raise DownloadError("No downloadable media found at this URL.")
        info = entries[0]

    files = [
        os.path.join(outdir, name)
        for name in os.listdir(outdir)
        if not name.endswith(".part")
    ]
    files = [f for f in files if os.path.isfile(f)]
    if not files:
        raise DownloadError("Download finished but produced no file.")

    path = max(files, key=os.path.getsize)
    ext = os.path.splitext(path)[1].lstrip(".").lower()
    is_audio = ext in {"mp3", "m4a", "opus", "aac", "wav", "ogg"}
    title = info.get("title") or os.path.splitext(os.path.basename(path))[0]
    return DownloadResult(path=path, title=title, ext=ext, is_audio=is_audio)


async def download(url: str, quality: str, *, cookiefile: str | None = None,
                   proxy: str | None = None, base_dir: str | None = None) -> DownloadResult:
    """Download ``url`` at ``quality`` and return the resulting file.

    Runs the blocking yt-dlp call in a worker thread so the event loop stays
    responsive for other users.
    """

    if quality not in ALL_QUALITIES:
        raise ValueError(f"Unsupported quality: {quality!r}")

    outdir = tempfile.mkdtemp(prefix="dl_", dir=base_dir)
    opts = build_ydl_opts(quality, outdir, cookiefile=cookiefile, proxy=proxy)
    logger.info("Downloading %s at quality=%s", url, quality)
    return await asyncio.to_thread(_run_download, url, opts, outdir)


def human_size(num_bytes: int) -> str:
    """Format a byte count as a short human-readable string."""

    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"
