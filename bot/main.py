"""Application entrypoint.

Runs in webhook mode when a public URL is configured (Render sets
``RENDER_EXTERNAL_URL`` automatically) and falls back to long-polling for local
development.
"""

from __future__ import annotations

import logging

from telegram import BotCommand, Update

from .config import load_config

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("bot")


def build_application(config):
    from telegram.ext import (
        Application,
        CallbackQueryHandler,
        CommandHandler,
        MessageHandler,
        filters,
    )

    from . import handlers

    application = (
        Application.builder()
        .token(config.bot_token)
        .concurrent_updates(True)
        .build()
    )
    application.bot_data["config"] = config

    application.add_handler(CommandHandler("start", handlers.start))
    application.add_handler(CommandHandler("help", handlers.help_command))
    application.add_handler(
        CallbackQueryHandler(handlers.on_quality_selected, pattern=r"^q:")
    )
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.on_message)
    )
    return application


async def _post_init(application) -> None:
    await application.bot.set_my_commands(
        [
            BotCommand("start", "Botni ishga tushirish"),
            BotCommand("help", "Yordam"),
        ]
    )


def main() -> None:
    config = load_config()
    application = build_application(config)
    application.post_init = _post_init

    if config.use_webhook:
        url_path = config.bot_token
        webhook_url = f"{config.webhook_url}/{url_path}"
        logger.info("Starting in WEBHOOK mode on port %s -> %s",
                    config.port, config.webhook_url)
        application.run_webhook(
            listen="0.0.0.0",
            port=config.port,
            url_path=url_path,
            webhook_url=webhook_url,
            secret_token=config.webhook_secret,
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
        )
    else:
        logger.info("Starting in POLLING mode (no WEBHOOK_URL/RENDER_EXTERNAL_URL)")
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
        )


if __name__ == "__main__":
    main()
