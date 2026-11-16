---
name: bili-digest
description: Turn Bilibili (B站) videos into a local library of Markdown transcripts and catch-up digests. Use when the user shares a bilibili.com / b23.tv link and wants its content, transcript, subtitles or a summary; wants to track a favorites folder (收藏夹) or an uploader (UP主); says their saved videos are gathering dust (吃灰) or asks to catch up on them; or asks "what's new from the people I follow on Bilibili". Handles syncing, transcripts, and agent-written digests. Not for downloading the videos themselves.
---

# bili-digest

The user saves Bilibili videos and rarely goes back to them. This skill keeps a local library of their transcripts in sync and turns unread ones into short digests, so the user can decide what's worth watching.

All work goes through one stdlib-only script:

```bash
python3 <this-skill-dir>/scripts/bilidigest.py <command>
```

Data lives in `$BILI_DIGEST_HOME` (default `~/BiliDigest`):
- `library/<bvid>.md`: one file per video. YAML front matter (title, uploader, published, `transcript_source`, `via`), then the description, then a `## Transcript` with `[mm:ss]` paragraph stamps.
- `digests/`: digests you write (see below).
- `state.json`: tracked sources, per-video status, digest marks. Read it only through the commands.
- `cookies.txt`: the user's login, if they set one up. **Never read, print, copy or send this file.**

## Commands

| Command | What it does |
|---|---|
| `get <url-or-BV>...` | Fetch one-off videos into the library |
| `watch fav <folder-url-or-id>` | Track a favorites folder (private folders need login) |
| `watch up <space-url-or-mid> --name X` | Track an uploader (currently needs login, see Limits) |
| `unwatch fav:<id>` / `unwatch up:<mid>` | Stop tracking |
| `sources` | List tracked sources and their last error |
| `sync [--limit N] [--retry]` | Fetch new videos from all sources. `--retry` re-tries ones without a transcript |
| `status [--undigested] [--json]` | List the library. `*` = not yet digested |
| `mark-digested <bvid>...` | Record that a digest covered these videos |
| `whoami` | Show which account is logged in, if any |
| `login` | Show a QR code for the user to scan with the Bilibili app. Run it only when the user asks, in a terminal they can see (it waits up to 3 min for their phone) |
| `logout` | Delete the saved session |

Each video has a status: `ok` (has a transcript), `needs-login` (subtitles exist behind login), or `no-subtitles` (needs speech-to-text).

## Workflow: catching up

1. `sync` (once per session is plenty; don't loop it).
2. `status --undigested --json` to get the unread videos: title, uploader, `duration_s`, `chars` (transcript length), and file path.
3. **Triage before reading.** Transcripts are expensive; a 70-minute video is about 60k characters. Decide from metadata alone: title, uploader, duration, and the description at the top of the file. Use `$BILI_DIGEST_HOME/interests.md` if it exists: the user's domains to include or exclude, and must-read uploaders.
   - Skip off-interest videos, game recordings, short clips under ~2 minutes, and music or sound-demo videos: `mark-digested --skip <bvid>...`.
   - If more than about 150k characters are left to read, ask the user to narrow it down, or pick the highest-value ones and say what you left out.
   - When the user tells you what they care about ("skip game videos", "always read uploader X"), update `interests.md` so the next triage remembers.
4. Read the picked transcripts with subagents on a cheaper model (Sonnet or Haiku), a few videos each, asking for the per-video format below. Raw transcripts stay out of the main context. AI subtitles contain homophone errors, so tell the subagents to fix obvious technical terms from context.
5. Write `digests/<YYYY-MM-DD>.md` in the user's language, grouped by uploader or theme. For each video:
   - one-line verdict: **watch** / **skim** / **skip**, and why;
   - 3–5 key points, each with the `[mm:ss]` stamp it comes from, so the user can jump in;
   - a link to the video.
   For videos without a transcript, summarize only from the title and description, and label it as such.
6. `mark-digested` the videos you covered, then show the user the digest file path and the top picks.

For a single link the user just pasted: `get` it, read the file, and answer directly. No digest file is needed.

## Limits and decisions that belong to the user

- **Without login, Bilibili returns no subtitles** (tested 2026-11: `need_login_subtitle: true` on almost every video), and uploader video lists are blocked by risk control (-352). Public favorites folders and video metadata work without login.
- Logging in uses the user's own account, which carries some risk of rate limiting. This is the user's decision. Only the user can complete `login` by scanning the QR code. Never ask for their password, and never extract cookies from their browser yourself.
- Speech-to-text for videos with no subtitles is not built yet. It would mean downloading audio and running a local model, and that's also the user's call.
- On risk-control errors (`-352`, `-412`), `sync` stops early by design. Don't retry in a loop; tell the user and try again later.
