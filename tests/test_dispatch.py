"""Integration tests that feed real Telegram Update JSON through the Application.

These mirror exactly what the Render webhook does: Telegram POSTs an update, the
Application parses and dispatches it to our handlers. The Bot's HTTP transport is
mocked so outgoing API calls are captured instead of hitting Telegram.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock

import pytest

from bot import downloader
from bot.config import load_config
from bot.main import build_application
from telegram import Update


async def _make_app_with_fake_transport():
    app = build_application(load_config({"BOT_TOKEN": "123:abc"}))
    calls: list[tuple[str, dict]] = []

    async def fake_post(endpoint, data=None, *args, **kwargs):
        calls.append((endpoint, data or {}))
        if endpoint == "getMe":
            return {"id": 123, "is_bot": True, "first_name": "Bot",
                    "username": "testbot"}
        if endpoint.startswith("send"):
            chat_id = (data or {}).get("chat_id", 0)
            return {"message_id": 10, "date": 0,
                    "chat": {"id": chat_id, "type": "private"},
                    "text": (data or {}).get("text", "")}
        return True

    app.bot._post = AsyncMock(side_effect=fake_post)
    await app.initialize()
    return app, calls


async def test_message_update_shows_menu():
    app, calls = await _make_app_with_fake_transport()
    try:
        update = Update.de_json(
            {
                "update_id": 1,
                "message": {
                    "message_id": 5, "date": 0,
                    "chat": {"id": 999, "type": "private"},
                    "from": {"id": 999, "is_bot": False, "first_name": "Fazo"},
                    "text": "https://youtu.be/dQw4w9WgXcQ",
                },
            },
            app.bot,
        )
        await app.process_update(update)
    finally:
        await app.shutdown()

    endpoints = [c[0] for c in calls]
    assert "sendMessage" in endpoints
    menu = [d for e, d in calls if e == "sendMessage" and d.get("reply_markup")]
    assert menu, "expected a quality-menu message with an inline keyboard"
    assert list(app.bot_data["links"].values()) == ["https://youtu.be/dQw4w9WgXcQ"]


async def test_callback_update_triggers_audio_send(tmp_path, monkeypatch):
    app, calls = await _make_app_with_fake_transport()
    app.bot_data["links"] = {"tok1": "https://youtu.be/abc"}

    # Stub the actual download with a real temporary MP3 file.
    d = tmp_path / "dl"
    d.mkdir()
    mp3 = d / "song.mp3"
    mp3.write_bytes(b"ID3" + b"\x00" * 512)
    result = downloader.DownloadResult(path=str(mp3), title="Song", ext="mp3",
                                       is_audio=True)
    monkeypatch.setattr(downloader, "download", AsyncMock(return_value=result))

    try:
        update = Update.de_json(
            {
                "update_id": 2,
                "callback_query": {
                    "id": "cb1",
                    "from": {"id": 999, "is_bot": False, "first_name": "Fazo"},
                    "message": {
                        "message_id": 7, "date": 0,
                        "chat": {"id": 999, "type": "private"},
                        "from": {"id": 123, "is_bot": True, "first_name": "Bot"},
                        "text": "menu",
                    },
                    "chat_instance": "ci",
                    "data": "q:tok1:mp3",
                },
            },
            app.bot,
        )
        await app.process_update(update)
    finally:
        await app.shutdown()

    endpoints = [c[0] for c in calls]
    assert "sendAudio" in endpoints, f"expected sendAudio, got {endpoints}"
    # Temp download dir cleaned up.
    assert not os.path.exists(str(d))
    # Link consumed.
    assert "tok1" not in app.bot_data["links"]
