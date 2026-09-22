"""Telegram update handlers wiring the downloader to chat interactions."""

from __future__ import annotations

import logging
import os
import shutil
import uuid

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    constants,
)
from telegram.ext import ContextTypes

from . import downloader
from .config import Config

logger = logging.getLogger(__name__)

WELCOME = (
    "👋 Salom! Men YouTube va Instagram’dan video yuklab beradigan botman.\n\n"
    "📎 Menga YouTube yoki Instagram havolasini yuboring.\n"
    "▶️ YouTube uchun sifatni tanlaysiz: MP3 (audio) yoki 360p / 480p / 720p / 1080p.\n"
    "📸 Instagram uchun videoni to‘g‘ridan-to‘g‘ri yuboraman.\n\n"
    "⚠️ Telegram bot orqali maksimal fayl hajmi 50 MB. Katta 1080p videolar "
    "chegaradan oshsa, pastroq sifat yoki MP3 tanlang."
)

HELP = (
    "ℹ️ *Foydalanish*\n\n"
    "1. YouTube yoki Instagram havolasini yuboring.\n"
    "2. YouTube bo‘lsa, tugmalardan sifatni tanlang.\n"
    "3. Men faylni yuklab, shu yerga jo‘nataman.\n\n"
    "Buyruqlar:\n"
    "/start – boshlash\n"
    "/help – yordam"
)


def _config(context: ContextTypes.DEFAULT_TYPE) -> Config:
    return context.application.bot_data["config"]


def _links(context: ContextTypes.DEFAULT_TYPE) -> dict[str, str]:
    return context.application.bot_data.setdefault("links", {})


def build_quality_keyboard(token: str) -> InlineKeyboardMarkup:
    """Inline keyboard offering MP3 + the supported video heights."""

    audio_row = [
        InlineKeyboardButton(
            downloader.quality_label(downloader.AUDIO_QUALITY),
            callback_data=f"q:{token}:{downloader.AUDIO_QUALITY}",
        )
    ]
    video_row = [
        InlineKeyboardButton(
            downloader.quality_label(q), callback_data=f"q:{token}:{q}"
        )
        for q in downloader.VIDEO_QUALITIES
    ]
    return InlineKeyboardMarkup([audio_row, video_row])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(WELCOME)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP, parse_mode=constants.ParseMode.MARKDOWN)


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if message is None:
        return
    text = message.text or message.caption or ""
    url = downloader.find_url(text)
    if not url:
        await message.reply_text(
            "❗️ Havola topilmadi. Iltimos, YouTube yoki Instagram havolasini yuboring."
        )
        return

    platform = downloader.detect_platform(url)

    if platform == "instagram":
        # Instagram posts are effectively single-quality; download directly.
        await _process_download(update, context, url, "1080", platform)
        return

    # YouTube (and any other supported site): offer a quality menu.
    token = uuid.uuid4().hex[:10]
    _links(context)[token] = url
    await message.reply_text(
        "🎯 Sifatni tanlang:",
        reply_markup=build_quality_keyboard(token),
    )


async def on_quality_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    try:
        _, token, quality = query.data.split(":", 2)
    except ValueError:
        await query.edit_message_text("❗️ Noto‘g‘ri tanlov.")
        return

    url = _links(context).get(token)
    if not url:
        await query.edit_message_text(
            "⌛️ Havola eskirdi. Iltimos, havolani qayta yuboring."
        )
        return

    platform = downloader.detect_platform(url)
    await query.edit_message_text(
        f"⏳ {downloader.quality_label(quality)} yuklab olinmoqda…"
    )
    await _process_download(update, context, url, quality, platform,
                            status_via_callback=True)
    _links(context).pop(token, None)


async def _process_download(update: Update, context: ContextTypes.DEFAULT_TYPE,
                            url: str, quality: str, platform: str,
                            status_via_callback: bool = False) -> None:
    chat_id = update.effective_chat.id
    cfg = _config(context)
    cookiefile = cfg.cookie_file_for(platform)

    status = None
    if not status_via_callback:
        status = await context.bot.send_message(
            chat_id, f"⏳ {downloader.quality_label(quality)} yuklab olinmoqda…"
        )

    result = None
    try:
        result = await downloader.download(
            url, quality,
            cookiefile=cookiefile,
            proxy=cfg.proxy,
            base_dir=cfg.download_dir,
        )

        size = result.size
        if size > cfg.max_file_bytes:
            await _reply(update, context, chat_id,
                         f"⚠️ Fayl hajmi {downloader.human_size(size)} — "
                         f"Telegram cheklovi {cfg.max_file_mb} MB dan katta.\n"
                         "Iltimos, pastroq sifat yoki MP3 tanlang.")
            return

        caption = result.title[:1000]
        if result.is_audio:
            await context.bot.send_chat_action(chat_id, constants.ChatAction.UPLOAD_VOICE)
            with open(result.path, "rb") as fh:
                await context.bot.send_audio(
                    chat_id, audio=fh, title=result.title,
                    filename=os.path.basename(result.path),
                    read_timeout=180, write_timeout=180, connect_timeout=60,
                )
        else:
            await context.bot.send_chat_action(chat_id, constants.ChatAction.UPLOAD_VIDEO)
            with open(result.path, "rb") as fh:
                await context.bot.send_video(
                    chat_id, video=fh, caption=caption, supports_streaming=True,
                    filename=os.path.basename(result.path),
                    read_timeout=180, write_timeout=180, connect_timeout=60,
                )
    except downloader.AuthRequiredError:
        await _reply(update, context, chat_id,
                     "🔒 Bu media login talab qiladi (YouTube/Instagram bot "
                     "tekshiruvi). Administrator cookie sozlamasini qo‘shishi kerak "
                     "(COOKIES_TXT). README’dagi ko‘rsatmaga qarang.")
    except downloader.DownloadError as exc:
        logger.warning("Download failed for %s: %s", url, exc)
        await _reply(update, context, chat_id,
                     "❌ Yuklab bo‘lmadi. Havola noto‘g‘ri yoki media mavjud emas.")
    except Exception:  # noqa: BLE001 - surface a friendly message, log the rest
        logger.exception("Unexpected error while handling %s", url)
        await _reply(update, context, chat_id,
                     "❌ Kutilmagan xatolik yuz berdi. Keyinroq urinib ko‘ring.")
    finally:
        if result is not None:
            shutil.rmtree(os.path.dirname(result.path), ignore_errors=True)
        if status is not None:
            try:
                await status.delete()
            except Exception:  # noqa: BLE001
                pass


async def _reply(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int,
                 text: str) -> None:
    await context.bot.send_message(chat_id, text)
