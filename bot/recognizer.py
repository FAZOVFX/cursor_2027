"""Song recognition from an audio clip using Shazam (via shazamio).

Telegram-agnostic so it can be unit tested in isolation. The input audio is
first normalized to mono 16 kHz WAV with ffmpeg (a) to keep the decoder quiet
and (b) to trim to a short window, which is all Shazam needs.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Shazam only needs a few seconds of audio to fingerprint a track.
_SAMPLE_SECONDS = 15


@dataclass
class RecognizeResult:
    title: str
    artist: str | None = None

    @property
    def query(self) -> str:
        """A search string suitable for a follow-up YouTube search."""

        if self.artist:
            return f"{self.artist} {self.title}".strip()
        return self.title

    @property
    def label(self) -> str:
        if self.artist:
            return f"{self.artist} — {self.title}"
        return self.title


async def _normalize(src: str) -> str | None:
    """Transcode ``src`` to a short mono 16 kHz WAV; return path or ``None``."""

    dst = f"{src}.rec.wav"
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", src, "-t", str(_SAMPLE_SECONDS), "-ac", "1", "-ar", "16000", dst,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.wait()
    if proc.returncode == 0 and os.path.exists(dst) and os.path.getsize(dst) > 0:
        return dst
    return None


def _parse_track(out) -> RecognizeResult | None:
    track = out.get("track") if isinstance(out, dict) else None
    if not track:
        return None
    title = track.get("title")
    if not title:
        return None
    return RecognizeResult(title=title, artist=track.get("subtitle"))


async def recognize(file_path: str) -> RecognizeResult | None:
    """Identify the song in ``file_path``.

    Returns a :class:`RecognizeResult` or ``None`` if nothing was matched.
    """

    from shazamio import Shazam

    normalized = await _normalize(file_path)
    target = normalized or file_path
    shazam = Shazam()
    try:
        try:
            out = await shazam.recognize(target)
        except AttributeError:  # older shazamio API
            out = await shazam.recognize_song(target)
    except Exception:  # noqa: BLE001 - network/parse errors -> treat as no match
        logger.exception("Shazam recognition failed")
        return None
    finally:
        if normalized and os.path.exists(normalized):
            os.remove(normalized)

    return _parse_track(out)
