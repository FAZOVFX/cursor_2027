# cursor_2027 — Telegram video downloader bot

A Telegram bot (Uzbek UI) that downloads videos/music from **YouTube** and
**Instagram**, searches by name, and recognizes songs from an audio clip.

- 📥 Send a YouTube or Instagram **link** → download it.
- 🔎 Send an **artist / song name** → the bot searches YouTube and shows options;
  pick one and choose the quality.
- 🎤 Send a **voice message or a snippet of a song** → the bot recognizes it
  (Shazam) and shows matching options to download.
- 🎬 For YouTube, pick the quality: **MP3 (audio)** or **360p / 480p / 720p / 1080p**.
- 🏷️ Every sent file is captioned with *"… orqali yuklandi"* (downloaded via the bot).
- ☁️ Designed to run on the **Render.com free tier** using Docker + webhooks.

Built with [python-telegram-bot](https://docs.python-telegram-bot.org),
[yt-dlp](https://github.com/yt-dlp/yt-dlp) and
[shazamio](https://github.com/shazamio/ShazamIO) (with `ffmpeg` for merging
1080p, extracting MP3, and normalizing audio for recognition).

---

## 1. Create the bot

1. Open [@BotFather](https://t.me/BotFather) in Telegram and send `/newbot`.
2. Choose a name and username; BotFather gives you a **token** like
   `123456789:AA...`. Keep it secret.

## 2. Run locally (long-polling)

```bash
python3 -m pip install -r requirements.txt      # needs ffmpeg installed on the system
export BOT_TOKEN="123456789:AA..."               # your token
python3 -m bot.main
```

With no `WEBHOOK_URL`/`RENDER_EXTERNAL_URL` set, the bot uses long-polling —
perfect for local testing. Send it a link in Telegram.

> `ffmpeg` must be installed locally (`apt install ffmpeg` / `brew install ffmpeg`).
> The Docker image installs it for you.

## 3. Deploy to Render (free)

This repo is Docker-based, which lets Render install `ffmpeg`.

**Option A — Blueprint (recommended):**

1. Push this repo to GitHub.
2. In Render, click **New + → Blueprint** and select the repo. Render reads
   [`render.yaml`](./render.yaml) and creates a free web service.
3. Set the **`BOT_TOKEN`** environment variable (and optionally `COOKIES_TXT`).
4. Deploy. Render injects `RENDER_EXTERNAL_URL`, so the bot automatically
   registers a Telegram **webhook** and starts receiving messages.

**Option B — Manual web service:**

1. **New + → Web Service**, connect the repo, choose **Docker** runtime, **Free** plan.
2. Add env var `BOT_TOKEN` (and optionally `COOKIES_TXT`).
3. Create the service.

The app binds to Render's `$PORT` and serves the Telegram webhook at
`https://<your-app>.onrender.com/<BOT_TOKEN>`.

> **Free tier note:** free web services sleep after ~15 minutes of inactivity.
> Telegram wakes the service on the next message via the webhook (first reply
> after sleep may take a few extra seconds while the container cold-starts).

## 4. Cookies (important for YouTube & Instagram)

YouTube and Instagram increasingly block **anonymous requests from data-center
IPs** (Render, most clouds) with messages like *"Sign in to confirm you're not
a bot"* or *"empty media response"*. The reliable fix is to provide **cookies**
from a logged-in account.

> ⚠️ **Do NOT paste cookies into an environment variable on Render.** A large
> cookies value makes the build fail with
> `exec /usr/local/bin/run-buildkit.sh: argument list too long`. Use a **Secret
> File** instead (see below).

### Recommended: Render Secret Files

1. In your browser, install a "Get cookies.txt (Netscape)" extension.
2. Log in to YouTube / Instagram, export `cookies.txt`.
3. In Render: **your service → Environment → Secret Files → Add Secret File**.
   Create a file named `youtube_cookies.txt` (and/or `instagram_cookies.txt`,
   or a single `cookies.txt` for both) and paste the exported contents.

The bot auto-detects these mounted paths — no extra env var needed:

```
/etc/secrets/youtube_cookies.txt
/etc/secrets/instagram_cookies.txt
/etc/secrets/cookies.txt            # used for both if the above are absent
```

You can also point to custom paths with `YOUTUBE_COOKIES_FILE`,
`INSTAGRAM_COOKIES_FILE` or `COOKIES_FILE`. Templates live in
[`secrets/`](./secrets). Without cookies, gated content returns a
"login required" message (search still works).

> The bot token can likewise be provided as a Secret File
> `/etc/secrets/bot_token.txt` instead of the `BOT_TOKEN` env var.

## 5. Configuration

| Variable | Required | Description |
| --- | --- | --- |
| `BOT_TOKEN` | ✅* | Telegram bot token from @BotFather. |
| `BOT_TOKEN_FILE` | ✅* | Path to a token file (default `/etc/secrets/bot_token.txt`). *One of `BOT_TOKEN`/file is required.* |
| `RENDER_EXTERNAL_URL` / `WEBHOOK_URL` | auto on Render | Public URL → enables webhook mode. Unset → polling. |
| `PORT` | auto on Render | Port to bind in webhook mode (default `10000`). |
| `MAX_FILE_MB` | ❌ | Upload size cap in MB (Telegram hard limit is 50; default `49`). |
| `YOUTUBE_COOKIES_FILE` | ❌ | Path to a YouTube cookies.txt file (Secret File). Preferred. |
| `INSTAGRAM_COOKIES_FILE` | ❌ | Path to an Instagram cookies.txt file. |
| `COOKIES_FILE` | ❌ | Path to a cookies.txt file used for both platforms. |
| `COOKIES_TXT` / `YOUTUBE_COOKIES_TXT` / `INSTAGRAM_COOKIES_TXT` | ❌ | Inline cookies (small only — large values break Render's build). |
| `WEBHOOK_SECRET` | ❌ | Optional Telegram webhook secret token. |
| `YTDLP_PROXY` | ❌ | Outbound proxy for yt-dlp. |

## 6. File-size limit

Telegram's Bot API allows sending files up to **50 MB**. Long 1080p videos can
exceed this; the bot detects it and asks you to choose a lower quality or MP3.

## 7. Development

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m pytest -q                 # unit + handler tests (no network)
RUN_LIVE=1 python3 -m pytest -q      # also runs a real download over the network
```

## Legal

Only download content you have the right to use. Respect YouTube's and
Instagram's Terms of Service and the rights of content owners.
