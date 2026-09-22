# Secrets (token & cookies)

> 🔴 **NEVER put real tokens or cookies in this repository.** Do **not** rename
> the `*.example` templates to `*.txt` and paste real values — that publishes
> your secrets on GitHub. YouTube cookies grant full access to your Google
> account, and a leaked bot token lets anyone control your bot. If this happens,
> immediately sign out of all Google sessions + change your password, and
> `/revoke` the bot token in @BotFather.

The files here ending in `.example` are empty templates that only show the
expected format. Real values go to **Render → your service → Environment →
Secret Files** (never the repo). Real `secrets/*.txt` files are git-ignored so
they can only be created locally, not committed.

## Why Secret Files (not env vars)?

Putting a large cookies file into an environment variable (e.g. `COOKIES_TXT`)
makes Render's build fail with:

```
exec /usr/local/bin/run-buildkit.sh: argument list too long
```

because the whole environment is passed to the build process. Use **Secret
Files** for large content instead — they are mounted at `/etc/secrets/<name>`
at runtime and are not part of the build environment.

## What to add on Render

Add these as **Secret Files** (the bot auto-detects the paths):

| Secret File name        | Mounted path                       | Purpose |
| ----------------------- | ---------------------------------- | ------- |
| `bot_token.txt`         | `/etc/secrets/bot_token.txt`       | Bot token (or use the `BOT_TOKEN` env var instead) |
| `youtube_cookies.txt`   | `/etc/secrets/youtube_cookies.txt` | YouTube cookies (Netscape format) |
| `instagram_cookies.txt` | `/etc/secrets/instagram_cookies.txt` | Instagram cookies (Netscape format) |
| `cookies.txt`           | `/etc/secrets/cookies.txt`         | Cookies used for both platforms if the above are absent |

You can instead point to custom paths with env vars: `BOT_TOKEN_FILE`,
`YOUTUBE_COOKIES_FILE`, `INSTAGRAM_COOKIES_FILE`, `COOKIES_FILE`.

## How to export cookies

1. Install a "Get cookies.txt (Netscape)" browser extension.
2. Log in to YouTube / Instagram in that browser.
3. Export `cookies.txt` and paste its contents into the Render Secret File.

## Local development

For local runs you can drop real files next to these templates
(`secrets/youtube_cookies.txt`, `secrets/bot_token.txt`, …) and point the env
vars at them, e.g.:

```bash
export BOT_TOKEN_FILE="$PWD/secrets/bot_token.txt"
export YOUTUBE_COOKIES_FILE="$PWD/secrets/youtube_cookies.txt"
```

Real `*.txt` files in this folder are git-ignored (only `*.example` is tracked).
