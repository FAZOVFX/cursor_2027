"""Runtime configuration for the downloader bot.

All configuration is read from environment variables so the same image can run
locally (long-polling) and on Render (webhook), driven only by which variables
are present.
"""

from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


@dataclass
class Config:
    """Resolved configuration for a single bot process."""

    bot_token: str
    webhook_url: str | None = None
    webhook_secret: str | None = None
    port: int = 10000
    max_file_mb: int = 49
    download_dir: str = field(default_factory=lambda: tempfile.mkdtemp(prefix="dlbot_"))
    proxy: str | None = None
    # Raw cookies.txt contents (Netscape format), per platform.
    cookies_all: str | None = None
    cookies_youtube: str | None = None
    cookies_instagram: str | None = None
    _cookie_dir: str | None = field(default=None, repr=False)

    @property
    def use_webhook(self) -> bool:
        return bool(self.webhook_url)

    @property
    def max_file_bytes(self) -> int:
        return self.max_file_mb * 1024 * 1024

    def cookie_file_for(self, platform: str) -> str | None:
        """Return a path to a cookies.txt file for ``platform`` or ``None``.

        Platform-specific cookies take precedence over the shared ``cookies_all``
        value. Files are written lazily into a private directory.
        """

        raw = None
        if platform == "youtube":
            raw = self.cookies_youtube or self.cookies_all
        elif platform == "instagram":
            raw = self.cookies_instagram or self.cookies_all
        else:
            raw = self.cookies_all

        if not raw:
            return None

        if self._cookie_dir is None:
            self._cookie_dir = tempfile.mkdtemp(prefix="dlbot_cookies_")
        path = Path(self._cookie_dir) / f"{platform}.txt"
        if not path.exists():
            # Support values pasted with escaped newlines from dashboards.
            normalized = raw.replace("\\n", "\n")
            path.write_text(normalized, encoding="utf-8")
            path.chmod(0o600)
            logger.info("Wrote %s cookies to %s (%d bytes)", platform, path, len(normalized))
        return str(path)


def load_config(env: dict[str, str] | None = None) -> Config:
    """Build a :class:`Config` from ``env`` (defaults to ``os.environ``)."""

    env = dict(os.environ if env is None else env)

    token = _clean(env.get("BOT_TOKEN") or env.get("TELEGRAM_BOT_TOKEN"))
    if not token:
        raise RuntimeError(
            "BOT_TOKEN is not set. Create a bot with @BotFather and set BOT_TOKEN."
        )

    # Render injects RENDER_EXTERNAL_URL automatically for web services.
    webhook_base = _clean(env.get("WEBHOOK_URL") or env.get("RENDER_EXTERNAL_URL"))
    if webhook_base:
        webhook_base = webhook_base.rstrip("/")

    return Config(
        bot_token=token,
        webhook_url=webhook_base,
        webhook_secret=_clean(env.get("WEBHOOK_SECRET")),
        port=int(_clean(env.get("PORT")) or 10000),
        max_file_mb=int(_clean(env.get("MAX_FILE_MB")) or 49),
        proxy=_clean(env.get("YTDLP_PROXY") or env.get("HTTPS_PROXY")),
        cookies_all=_clean(env.get("COOKIES_TXT")),
        cookies_youtube=_clean(env.get("YOUTUBE_COOKIES_TXT")),
        cookies_instagram=_clean(env.get("INSTAGRAM_COOKIES_TXT")),
    )
