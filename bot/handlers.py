"""Telegram update handlers wiring the downloader to chat interactions."""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
import uuid

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    constants,
)
from telegram.ext import ContextTypes

from . import downloader, recognizer
from .config import Config

logger = logging.getLogger(__name__)

WELCOME = (
    "👋 Salom! Men YouTube va Instagram’dan video/musiqa yuklab beradigan botman.\n\n"
    "Mana nima qila olaman:\n"
    "📎 *Havola* yuboring (YouTube/Instagram) — yuklab beraman.\n"
    "🔎 *Artist yoki qo‘shiq nomini* yozing — variantlar chiqaraman, tanlagansiz "
    "yuklanadi.\n"
    "🎤 *Ovozli xabar* yoki *qo‘shiqdan parcha* yuboring — qaysi qo‘shiq ekanini "
    "topib, variantlarini chiqaraman.\n\n"
    "▶️ YouTube uchun sifat: MP3 (audio) yoki 360p / 480p / 720p / 1080p.\n\n"
    "⚠️ Telegram orqali maksimal fayl hajmi 50 MB. Katta 1080p oshsa, pastroq "
    "sifat yoki MP3 tanlang."
)

HELP = (
    "ℹ️ *Foydalanish*\n\n"
    "• Havola yuboring — video/audio yuklab beraman.\n"
    "• Qo‘shiq yoki artist nomini yozing — variantlardan tanlaysiz.\n"
    "• Ovozli xabar / qo‘shiq parchasini yuboring — nomini topib beraman.\n\n"
    "Buyruqlar:\n"
    "/start – boshlash\n"
    "/help – yordam"
)


def _config(context: ContextTypes.DEFAULT_TYPE) -> Config:
    return context.application.bot_data["config"]


def _links(context: ContextTypes.DEFAULT_TYPE) -> dict[str, str]:
    return context.application.bot_data.setdefault("links", {})


def _searches(context: ContextTypes.DEFAULT_TYPE) -> dict[str, list]:
    return context.application.bot_data.setdefault("searches", {})


def _attribution(context: ContextTypes.DEFAULT_TYPE) -> str:
    username = getattr(context.bot, "username", None)
    return f"@{username}" if username else "shu bot"


def _build_caption(title: str, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Caption placed under every sent file: title + 'bot orqali yuklandi'."""

    title = (title or "").strip()
    tag = _attribution(context)
    header = f"🎵 {title}\n\n" if title else ""
    return f"{header}⤵️ {tag} orqali yuklandi"


def _cookie_hint(platform: str) -> str:
    """User-facing hint (Uzbek) explaining that cookies are needed."""

    if platform == "instagram":
        name = "instagram_cookies.txt"
        site = "Instagram"
    else:
        name = "youtube_cookies.txt"
        site = "YouTube"
    return (
        f"🔒 {site} server IP’ni bloklagan (bot tekshiruvi), shuning uchun "
        f"bajarib bo‘lmadi.\n\nTuzatish: administrator Render’da «{name}» nomli "
        "cookie faylini (Secret File) qo‘shishi kerak. Batafsil — README’dagi "
        "«Cookies» bo‘limi."
    )


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


def build_search_keyboard(token: str, results: list) -> InlineKeyboardMarkup:
    """One button per search result, labelled with title + duration."""

    rows = []
    for index, result in enumerate(results):
        dur = downloader.format_duration(result.duration)
        label = f"{index + 1}. {result.title}"
        if len(label) > 55:
            label = label[:54] + "…"
        label = f"{label}  ⏱ {dur}"
        rows.append(
            [InlineKeyboardButton(label, callback_data=f"s:{token}:{index}")]
        )
    return InlineKeyboardMarkup(rows)


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
        # No link -> treat the text as a song/artist search query.
        query = text.strip()
        if len(query) < 2:
            await message.reply_text(
                "❗️ Havola yoki qo‘shiq/artist nomini yuboring."
            )
            return
        await present_search(update, context, query)
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


async def present_search(update: Update, context: ContextTypes.DEFAULT_TYPE,
                         query: str, header: str | None = None) -> None:
    """Search YouTube for ``query`` and show the results as buttons."""

    chat_id = update.effective_chat.id
    cfg = _config(context)
    status = await context.bot.send_message(chat_id, f"🔎 “{query}” qidirilmoqda…")
    try:
        results = await downloader.search(
            query, limit=5,
            cookiefile=cfg.cookie_file_for("youtube"),
            proxy=cfg.proxy,
        )
    except (downloader.AuthRequiredError, downloader.DownloadError):
        # YouTube search from a data-center IP usually fails without cookies.
        await status.edit_text(_cookie_hint("youtube"))
        return

    if not results:
        await status.edit_text("😕 Hech narsa topilmadi. Boshqacha yozib ko‘ring.")
        return

    token = uuid.uuid4().hex[:10]
    _searches(context)[token] = results
    prefix = f"{header}\n\n" if header else ""
    await status.edit_text(
        f"{prefix}🎯 Quyidagilardan birini tanlang:",
        reply_markup=build_search_keyboard(token, results),
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


async def on_search_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """User picked a search result -> offer the quality menu for its URL."""

    query = update.callback_query
    await query.answer()
    try:
        _, token, index_str = query.data.split(":", 2)
        index = int(index_str)
    except (ValueError, IndexError):
        await query.edit_message_text("❗️ Noto‘g‘ri tanlov.")
        return

    results = _searches(context).get(token)
    if not results or index >= len(results):
        await query.edit_message_text(
            "⌛️ Ro‘yxat eskirdi. Iltimos, qaytadan qidiring."
        )
        return

    result = results[index]
    link_token = uuid.uuid4().hex[:10]
    _links(context)[link_token] = result.url
    await query.edit_message_text(
        f"✅ Tanlandi: {result.title}\n\n🎯 Sifatni tanlang:",
        reply_markup=build_quality_keyboard(link_token),
    )
    _searches(context).pop(token, None)


async def on_audio_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Recognize a voice message / audio snippet, then show search variants."""

    message = update.message
    chat_id = update.effective_chat.id
    media = message.voice or message.audio
    if media is None:
        return

    status = await context.bot.send_message(chat_id, "🎧 Qo‘shiq aniqlanmoqda…")

    tmp_dir = tempfile.mkdtemp(prefix="rec_", dir=_config(context).download_dir)
    audio_path = os.path.join(tmp_dir, "clip")
    try:
        tg_file = await context.bot.get_file(media.file_id)
        await tg_file.download_to_drive(audio_path)

        result = await recognizer.recognize(audio_path)
        if result is None:
            await status.edit_text(
                "😕 Afsus, qo‘shiqni aniqlay olmadim. Aniqroq/uzunroq parcha "
                "yuboring yoki nomini yozing."
            )
            return

        await status.edit_text(f"🎵 Topildi: *{result.label}*",
                               parse_mode=constants.ParseMode.MARKDOWN)
        await present_search(update, context, result.query,
                             header=f"🎵 Topildi: {result.label}")
    except Exception:  # noqa: BLE001
        logger.exception("Audio recognition flow failed")
        await status.edit_text("❌ Xatolik yuz berdi. Keyinroq urinib ko‘ring.")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


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

        caption = _build_caption(result.title, context)
        if result.is_audio:
            await context.bot.send_chat_action(chat_id, constants.ChatAction.UPLOAD_VOICE)
            with open(result.path, "rb") as fh:
                await context.bot.send_audio(
                    chat_id, audio=fh, title=result.title, caption=caption,
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
        await _reply(update, context, chat_id, _cookie_hint(platform))
    except downloader.DownloadError as exc:
        logger.warning("Download failed for %s: %s", url, exc)
        # On cloud hosts YouTube/Instagram failures are almost always the
        # IP/bot-check, so point the user at cookies for those platforms.
        if platform in ("youtube", "instagram"):
            await _reply(update, context, chat_id, _cookie_hint(platform))
        else:
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
