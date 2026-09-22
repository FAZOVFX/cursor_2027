"""Unit tests for the song recognizer result parsing (no network)."""

from __future__ import annotations

from bot import recognizer


def test_parse_track_full():
    out = {"track": {"title": "Yellow", "subtitle": "Coldplay"}}
    res = recognizer._parse_track(out)
    assert res is not None
    assert res.title == "Yellow"
    assert res.artist == "Coldplay"
    assert res.query == "Coldplay Yellow"
    assert res.label == "Coldplay — Yellow"


def test_parse_track_no_artist():
    res = recognizer._parse_track({"track": {"title": "Some Song"}})
    assert res is not None
    assert res.artist is None
    assert res.query == "Some Song"
    assert res.label == "Some Song"


def test_parse_track_missing():
    assert recognizer._parse_track({}) is None
    assert recognizer._parse_track({"track": {}}) is None
    assert recognizer._parse_track(None) is None
