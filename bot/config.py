"""Runtime configuration for the downloader bot.

All configuration is read from environment variables so the same image can run
locally (long-polling) and on Render (webhook), driven only by which variables
are present.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Magic header that yt-dlp's Netscape cookie parser requires on the first line.
_COOKIE_MAGIC = "# Netscape HTTP Cookie File"
_COOKIE_MAGIC_RE = re.compile(r"#( Netscape)? HTTP Cookie File")

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


def _json_cookies_to_netscape(text: str) -> str | None:
    """Convert a JSON cookie export (array of objects) to Netscape format."""

    try:
        data = json.loads(text)
    except ValueError:
        return None
    if isinstance(data, dict):
        data = data.get("cookies") or data.get("Cookies") or []
    if not isinstance(data, list):
        return None

    lines = [_COOKIE_MAGIC]
    for cookie in data:
        if not isinstance(cookie, dict):
            continue
        domain = cookie.get("domain") or cookie.get("Domain")
        name = cookie.get("name") or cookie.get("Name")
        if not domain or name is None:
            continue
        value = cookie.get("value")
        if value is None:
            value = cookie.get("Value") or ""
        path = cookie.get("path") or cookie.get("Path") or "/"
        secure = "TRUE" if cookie.get("secure") or cookie.get("Secure") else "FALSE"
        host_only = cookie.get("hostOnly")
        if host_only is None:
            include_sub = "TRUE" if str(domain).startswith(".") else "FALSE"
        else:
            include_sub = "FALSE" if host_only else "TRUE"
        expiry = (cookie.get("expirationDate") or cookie.get("expiry")
                  or cookie.get("expires") or 0)
        try:
            expiry = int(float(expiry))
        except (TypeError, ValueError):
            expiry = 0
        lines.append("\t".join([
            str(domain), include_sub, str(path), secure, str(expiry),
            str(name), str(value),
        ]))
    return "\n".join(lines) + "\n" if len(lines) > 1 else None


def normalize_cookies(text: str) -> str | None:
    """Coerce ``text`` into a valid Netscape cookies.txt or return ``None``.

    Handles the common export mistakes: a missing magic header, space-separated
    columns (tabs lost on copy/paste), CRLF line endings, and JSON exports.
    """

    if not text:
        return None
    text = text.strip()
    if not text:
        return None

    # JSON export from some browser extensions.
    if text[:1] in "[{":
        converted = _json_cookies_to_netscape(text)
        if converted:
            return converted

    data_lines: list[str] = []
    for raw in text.splitlines():
        line = raw.rstrip("\r")
        stripped = line.strip()
        if not stripped:
            continue
        # Keep yt-dlp's #HttpOnly_ data lines; drop other comments/headers.
        if stripped.startswith("#") and not stripped.startswith("#HttpOnly_"):
            continue
        if "\t" in line:
            data_lines.append(line)
        else:
            # Recover tab separation from space-separated columns.
            parts = line.split()
            if len(parts) >= 7:
                data_lines.append("\t".join(parts[:6] + [" ".join(parts[6:])]))
    if not data_lines:
        return None
    return _COOKIE_MAGIC + "\n" + "\n".join(data_lines) + "\n"


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

    def _cookie_source_text(self, platform: str) -> str | None:
        """Return raw cookie text from a file or inline env value."""

        for candidate in self._cookie_file_candidates(platform):
            if os.path.isfile(candidate):
                try:
                    content = open(candidate, encoding="utf-8",
                                   errors="replace").read()
                except OSError as exc:  # pragma: no cover
                    logger.warning("Could not read cookies %s: %s", candidate, exc)
                    continue
                if content.strip():
                    return content

        if platform == "youtube":
            raw = self.cookies_youtube or self.cookies_all
        elif platform == "instagram":
            raw = self.cookies_instagram or self.cookies_all
        else:
            raw = self.cookies_all
        if raw:
            # Support values pasted with escaped newlines from dashboards.
            return raw.replace("\\n", "\n")
        return None

    def cookie_file_for(self, platform: str) -> str | None:
        """Return a path to a valid Netscape cookies.txt for ``platform``.

        Cookies can come from a Render Secret File / explicit path or an inline
        ``*_COOKIES_TXT`` value. The content is normalized (header added, tabs
        recovered, JSON converted) and written to a private temp file so yt-dlp
        always receives a well-formed file.
        """

        source = self._cookie_source_text(platform)
        if not source:
            return None

        normalized = normalize_cookies(source)
        if not normalized:
            logger.warning("Could not parse %s cookies into Netscape format",
                           platform)
            return None

        if self._cookie_dir is None:
            self._cookie_dir = tempfile.mkdtemp(prefix="dlbot_cookies_")
        path = Path(self._cookie_dir) / f"{platform}.txt"
        path.write_text(normalized, encoding="utf-8")
        path.chmod(0o600)
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
