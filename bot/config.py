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

# Render mounts "Secret Files" under /etc/secrets/<filename>. These are the
# default locations checked when no explicit *_COOKIES_FILE path is provided.
DEFAULT_SECRET_DIR = "/etc/secrets"
DEFAULT_TOKEN_FILE = os.path.join(DEFAULT_SECRET_DIR, "bot_token.txt")


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _read_file(path: str | None) -> str | None:
    if not path:
        return None
    try:
        if os.path.isfile(path):
            content = open(path, encoding="utf-8").read().strip()
            return content or None
    except OSError as exc:  # pragma: no cover - unexpected FS error
        logger.warning("Could not read %s: %s", path, exc)
    return None


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
    # Raw cookies.txt contents (Netscape format), per platform. Prefer files
    # (below) for large cookies to avoid huge environment variables.
    cookies_all: str | None = None
    cookies_youtube: str | None = None
    cookies_instagram: str | None = None
    # Explicit paths to cookies.txt files (e.g. Render Secret Files).
    cookies_file: str | None = None
    cookies_youtube_file: str | None = None
    cookies_instagram_file: str | None = None
    _cookie_dir: str | None = field(default=None, repr=False)

    @property
    def use_webhook(self) -> bool:
        return bool(self.webhook_url)

    @property
    def max_file_bytes(self) -> int:
        return self.max_file_mb * 1024 * 1024

    def _cookie_file_candidates(self, platform: str) -> list[str]:
        """Ordered list of explicit + default cookie-file paths for a platform."""

        if platform == "youtube":
            explicit = [self.cookies_youtube_file, self.cookies_file]
            defaults = [
                os.path.join(DEFAULT_SECRET_DIR, "youtube_cookies.txt"),
                os.path.join(DEFAULT_SECRET_DIR, "cookies.txt"),
            ]
        elif platform == "instagram":
            explicit = [self.cookies_instagram_file, self.cookies_file]
            defaults = [
                os.path.join(DEFAULT_SECRET_DIR, "instagram_cookies.txt"),
                os.path.join(DEFAULT_SECRET_DIR, "cookies.txt"),
            ]
        else:
            explicit = [self.cookies_file]
            defaults = [os.path.join(DEFAULT_SECRET_DIR, "cookies.txt")]
        return [p for p in (*explicit, *defaults) if p]

    def cookie_file_for(self, platform: str) -> str | None:
        """Return a path to a cookies.txt file for ``platform`` or ``None``.

        Resolution order:
        1. An existing cookies file (explicit ``*_COOKIES_FILE`` path or a
           Render Secret File at a default location). Preferred — keeps large
           cookies out of environment variables.
        2. Raw ``*_COOKIES_TXT`` contents materialized to a temp file.
        """

        for candidate in self._cookie_file_candidates(platform):
            if os.path.isfile(candidate):
                return candidate

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

    # Token can come from an env var, an explicit file, or a Render Secret File
    # mounted at /etc/secrets/bot_token.txt. Env var wins when present.
    token = _clean(env.get("BOT_TOKEN") or env.get("TELEGRAM_BOT_TOKEN"))
    if not token:
        token_file = _clean(env.get("BOT_TOKEN_FILE")) or DEFAULT_TOKEN_FILE
        token = _read_file(token_file)
    if not token:
        raise RuntimeError(
            "BOT_TOKEN is not set. Create a bot with @BotFather and set BOT_TOKEN "
            "(or provide a bot_token.txt Secret File)."
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
        cookies_file=_clean(env.get("COOKIES_FILE")),
        cookies_youtube_file=_clean(env.get("YOUTUBE_COOKIES_FILE")),
        cookies_instagram_file=_clean(env.get("INSTAGRAM_COOKIES_FILE")),
    )
