"""Tests for cookie normalization (the fix for the Netscape-format error)."""

from __future__ import annotations

import http.cookiejar
import json

from bot.config import load_config, normalize_cookies

MAGIC = "# Netscape HTTP Cookie File"


def _loads_ok(text: str, tmp_path) -> int:
    """Write text and confirm MozillaCookieJar (what yt-dlp uses) loads it."""
    path = tmp_path / "c.txt"
    path.write_text(text)
    jar = http.cookiejar.MozillaCookieJar(str(path))
    # raises LoadError if not valid Netscape format; ignore expiry so that
    # test cookies with epoch 0 are still counted.
    jar.load(ignore_discard=True, ignore_expires=True)
    return len(jar)


def test_adds_missing_header(tmp_path):
    raw = ".youtube.com\tTRUE\t/\tTRUE\t0\tSID\tabc123"
    out = normalize_cookies(raw)
    assert out.startswith(MAGIC)
    assert _loads_ok(out, tmp_path) == 1


def test_recovers_space_separated_columns(tmp_path):
    raw = ".youtube.com TRUE / TRUE 0 SID abc123"
    out = normalize_cookies(raw)
    assert "\t" in out
    assert _loads_ok(out, tmp_path) == 1


def test_passes_through_valid_file(tmp_path):
    raw = MAGIC + "\n.youtube.com\tTRUE\t/\tTRUE\t0\tSID\tabc123\n"
    out = normalize_cookies(raw)
    assert _loads_ok(out, tmp_path) == 1


def test_handles_crlf(tmp_path):
    raw = ".youtube.com\tTRUE\t/\tTRUE\t0\tSID\tabc123\r\n"
    out = normalize_cookies(raw)
    assert "\r" not in out
    assert _loads_ok(out, tmp_path) == 1


def test_keeps_httponly_lines(tmp_path):
    raw = "#HttpOnly_.youtube.com\tTRUE\t/\tTRUE\t0\tSID\tabc123"
    out = normalize_cookies(raw)
    assert "#HttpOnly_" in out
    assert _loads_ok(out, tmp_path) == 1


def test_json_export_conversion(tmp_path):
    raw = json.dumps([
        {"domain": ".youtube.com", "name": "SID", "value": "abc",
         "path": "/", "secure": True, "expirationDate": 1999999999.5},
    ])
    out = normalize_cookies(raw)
    assert out.startswith(MAGIC)
    assert "SID" in out
    assert _loads_ok(out, tmp_path) == 1


def test_empty_returns_none():
    assert normalize_cookies("") is None
    assert normalize_cookies("   \n  ") is None
    assert normalize_cookies("# only a comment") is None


def test_config_produces_loadable_file(tmp_path):
    # Space-separated inline cookies (a common paste mistake) -> valid file.
    cfg = load_config(
        {"BOT_TOKEN": "1:t", "YOUTUBE_COOKIES_TXT": ".youtube.com TRUE / TRUE 0 SID abc"}
    )
    path = cfg.cookie_file_for("youtube")
    assert path is not None
    jar = http.cookiejar.MozillaCookieJar(path)
    jar.load(ignore_discard=True, ignore_expires=True)
    assert len(jar) == 1
