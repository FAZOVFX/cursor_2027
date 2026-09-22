"""Handler-level tests using mocked Telegram Update/Context objects."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot import downloader, handlers, recognizer
from bot.config import load_config
from telegram import InlineKeyboardMarkup


def make_context(cfg=None):
    cfg = cfg or load_config({"BOT_TOKEN": "1:token"})
    context = MagicMock()
    context.application.bot_data = {"config": cfg}

    status_msg = MagicMock()
    status_msg.delete = AsyncMock()
    status_msg.edit_text = AsyncMock()

    context.bot = MagicMock()
    context.bot.username = "testbot"
    context.bot.send_message = AsyncMock(return_value=status_msg)
    context.bot.send_audio = AsyncMock()
    context.bot.send_video = AsyncMock()
    context.bot.send_chat_action = AsyncMock()
    return context


def make_result(tmp_path, name="video.mp4", size=1024, is_audio=False):
    d = tmp_path / f"dl_{name}"
    d.mkdir()
    f = d / name
    f.write_bytes(b"x" * size)
    ext = name.rsplit(".", 1)[-1]
    return downloader.DownloadResult(path=str(f), title="Sample", ext=ext,
                                     is_audio=is_audio)


async def test_on_message_youtube_shows_quality_menu():
    context = make_context()
    update = MagicMock()
    update.message.text = "watch this https://youtu.be/abc123 now"
    update.message.caption = None
    update.message.reply_text = AsyncMock()

    await handlers.on_message(update, context)

    update.message.reply_text.assert_awaited_once()
    _, kwargs = update.message.reply_text.call_args
    markup = kwargs["reply_markup"]
    assert isinstance(markup, InlineKeyboardMarkup)
    # 1 audio button + 4 video buttons
    buttons = [b for row in markup.inline_keyboard for b in row]
    assert len(buttons) == 5
    # URL stored for later callback
    links = context.application.bot_data["links"]
    assert list(links.values()) == ["https://youtu.be/abc123"]


async def test_on_message_too_short_prompts():
    context = make_context()
    update = MagicMock()
    update.message.text = "a"
    update.message.caption = None
    update.message.reply_text = AsyncMock()

    await handlers.on_message(update, context)

    update.message.reply_text.assert_awaited_once()
    args, _ = update.message.reply_text.call_args
    assert "qo‘shiq" in args[0] or "Havola" in args[0]


async def test_on_message_instagram_downloads_and_sends_video(tmp_path, monkeypatch):
    context = make_context()
    update = MagicMock()
    update.message.text = "https://www.instagram.com/reel/CabcDEF/"
    update.message.caption = None
    update.effective_chat.id = 555

    result = make_result(tmp_path, "reel.mp4", size=2048, is_audio=False)
    monkeypatch.setattr(downloader, "download", AsyncMock(return_value=result))

    await handlers.on_message(update, context)

    context.bot.send_video.assert_awaited_once()
    # Temp dir cleaned up afterwards
    assert not os.path.exists(os.path.dirname(result.path))


async def test_quality_callback_mp3_sends_audio(tmp_path, monkeypatch):
    context = make_context()
    context.application.bot_data["links"] = {"tok1": "https://youtu.be/abc"}

    query = MagicMock()
    query.data = "q:tok1:mp3"
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()

    update = MagicMock()
    update.callback_query = query
    update.effective_chat.id = 777

    result = make_result(tmp_path, "song.mp3", size=4096, is_audio=True)
    monkeypatch.setattr(downloader, "download", AsyncMock(return_value=result))

    await handlers.on_quality_selected(update, context)

    context.bot.send_audio.assert_awaited_once()
    context.bot.send_video.assert_not_awaited()
    # token consumed
    assert "tok1" not in context.application.bot_data["links"]


async def test_quality_callback_expired_link():
    context = make_context()
    query = MagicMock()
    query.data = "q:missing:720"
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    update = MagicMock()
    update.callback_query = query

    await handlers.on_quality_selected(update, context)

    query.edit_message_text.assert_awaited_once()
    args, _ = query.edit_message_text.call_args
    assert "eskirdi" in args[0]


async def test_oversize_file_is_rejected(tmp_path, monkeypatch):
    cfg = load_config({"BOT_TOKEN": "1:token", "MAX_FILE_MB": "0"})
    context = make_context(cfg)
    update = MagicMock()
    update.message.text = "https://www.instagram.com/reel/x/"
    update.message.caption = None
    update.effective_chat.id = 42

    result = make_result(tmp_path, "big.mp4", size=1024, is_audio=False)
    monkeypatch.setattr(downloader, "download", AsyncMock(return_value=result))

    await handlers.on_message(update, context)

    context.bot.send_video.assert_not_awaited()
    # A warning message was sent
    warn_calls = [c.args[1] for c in context.bot.send_message.call_args_list
                  if len(c.args) > 1]
    assert any("cheklovi" in t for t in warn_calls)


async def test_text_search_shows_variants(monkeypatch):
    context = make_context()
    update = MagicMock()
    update.message.text = "Coldplay Yellow"
    update.message.caption = None
    update.effective_chat.id = 111

    results = [
        downloader.SearchResult(title="Coldplay - Yellow", url="https://youtu.be/1",
                                duration=269),
        downloader.SearchResult(title="Yellow (Lyrics)", url="https://youtu.be/2",
                                duration=270),
    ]
    monkeypatch.setattr(downloader, "search", AsyncMock(return_value=results))

    await handlers.on_message(update, context)

    # A status message was edited into the results list with an inline keyboard.
    status = context.bot.send_message.return_value
    status.edit_text.assert_awaited()
    _, kwargs = status.edit_text.call_args
    markup = kwargs["reply_markup"]
    assert isinstance(markup, InlineKeyboardMarkup)
    buttons = [b for row in markup.inline_keyboard for b in row]
    assert len(buttons) == 2
    assert all(b.callback_data.startswith("s:") for b in buttons)
    # Results stored for the selection step.
    assert len(context.application.bot_data["searches"]) == 1


async def test_search_no_results(monkeypatch):
    context = make_context()
    update = MagicMock()
    update.message.text = "asdkjhaskdjh not a real song 999"
    update.message.caption = None
    update.effective_chat.id = 111
    monkeypatch.setattr(downloader, "search", AsyncMock(return_value=[]))

    await handlers.on_message(update, context)

    status = context.bot.send_message.return_value
    status.edit_text.assert_awaited()
    args, _ = status.edit_text.call_args
    assert "topilmadi" in args[0]


async def test_search_selection_shows_quality_menu():
    context = make_context()
    results = [downloader.SearchResult(title="Song A", url="https://youtu.be/aaa")]
    context.application.bot_data["searches"] = {"stok": results}

    query = MagicMock()
    query.data = "s:stok:0"
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    update = MagicMock()
    update.callback_query = query

    await handlers.on_search_selected(update, context)

    query.edit_message_text.assert_awaited_once()
    _, kwargs = query.edit_message_text.call_args
    markup = kwargs["reply_markup"]
    buttons = [b for row in markup.inline_keyboard for b in row]
    # quality menu = 1 audio + 4 video
    assert len(buttons) == 5
    assert all(b.callback_data.startswith("q:") for b in buttons)
    # link stored, search entry consumed
    assert "https://youtu.be/aaa" in context.application.bot_data["links"].values()
    assert "stok" not in context.application.bot_data["searches"]


async def test_voice_message_recognizes_and_searches(tmp_path, monkeypatch):
    context = make_context()
    update = MagicMock()
    update.message.voice = MagicMock(file_id="fid")
    update.message.audio = None
    update.effective_chat.id = 222

    tg_file = MagicMock()
    tg_file.download_to_drive = AsyncMock()
    context.bot.get_file = AsyncMock(return_value=tg_file)

    monkeypatch.setattr(
        recognizer, "recognize",
        AsyncMock(return_value=recognizer.RecognizeResult(title="Yellow",
                                                          artist="Coldplay")),
    )
    search_mock = AsyncMock(return_value=[
        downloader.SearchResult(title="Coldplay - Yellow", url="https://youtu.be/1"),
    ])
    monkeypatch.setattr(downloader, "search", search_mock)

    await handlers.on_audio_message(update, context)

    # Recognized -> follow-up YouTube search with the recognized query.
    search_mock.assert_awaited_once()
    args, kwargs = search_mock.call_args
    assert "Coldplay" in args[0] and "Yellow" in args[0]


async def test_voice_message_no_match(tmp_path, monkeypatch):
    context = make_context()
    update = MagicMock()
    update.message.voice = MagicMock(file_id="fid")
    update.message.audio = None
    update.effective_chat.id = 222

    tg_file = MagicMock()
    tg_file.download_to_drive = AsyncMock()
    context.bot.get_file = AsyncMock(return_value=tg_file)
    monkeypatch.setattr(recognizer, "recognize", AsyncMock(return_value=None))

    await handlers.on_audio_message(update, context)

    status = context.bot.send_message.return_value
    status.edit_text.assert_awaited()
    args, _ = status.edit_text.call_args
    assert "aniqlay olmadim" in args[0]


def test_build_caption_includes_attribution():
    context = MagicMock()
    context.bot.username = "mybot"
    cap = handlers._build_caption("Coldplay - Yellow", context)
    assert "Coldplay - Yellow" in cap
    assert "@mybot" in cap
    assert "orqali yuklandi" in cap


async def test_auth_required_shows_cookie_hint(tmp_path, monkeypatch):
    context = make_context()
    update = MagicMock()
    update.message.text = "https://www.instagram.com/reel/x/"
    update.message.caption = None
    update.effective_chat.id = 99

    monkeypatch.setattr(
        downloader, "download",
        AsyncMock(side_effect=downloader.AuthRequiredError("Sign in to confirm")),
    )

    await handlers.on_message(update, context)

    context.bot.send_video.assert_not_awaited()
    msgs = [c.args[1] for c in context.bot.send_message.call_args_list
            if len(c.args) > 1]
    assert any("cookie" in t.lower() for t in msgs)
