# bili-digest

**English** | [简体中文](README.zh-CN.md)

> **Status: v0.1, experimental.** Built for personal use; Bilibili can change its endpoints at any time.

Saved Bilibili videos tend to gather dust (吃灰). This is a Claude Code skill plus a small no-dependency Python script that:

1. **Syncs** your favorites folders and chosen uploaders into a local library, with one Markdown file per video holding metadata and a timestamped transcript taken from Bilibili's subtitles.
2. **Triages** new videos from metadata alone (title, uploader, duration, your `interests.md`), so tokens aren't spent on food, game or music videos you'll never care about.
3. **Digests** the picked ones with cheap-model subagents into a dated file. Each video gets a **watch / skim / skip** verdict, key points, and the timestamps worth jumping to.

## Install

```
/plugin marketplace add gxxxr-111/bili-digest
/plugin install bili-digest@bili-digest
```

Or copy `skills/bili-digest` into `~/.claude/skills/`. Requires Python 3.10+. The optional `qrcode` package (`pip install qrcode`) or `qrencode` draws the login QR code.

## Use

Ask Claude things like *"catch me up on my Bilibili favorites"*, *"track this uploader: <space link>"*, or paste a `bilibili.com/video/...` link. The skill drives the script:

```bash
S=~/.claude/skills/bili-digest/scripts/bilidigest.py   # or the plugin's copy
python3 $S login                      # scan the QR code with the Bilibili app
python3 $S watch fav <folder link or id>
python3 $S watch up  <space link or mid> --name <label>
python3 $S sync --limit 20
python3 $S status --undigested
```

Data lives in `~/BiliDigest` (override with `BILI_DIGEST_HOME`):

```
library/<bvid>.md   transcript + YAML front matter
digests/<date>.md   digests written by the agent
interests.md        what to include / skip / always read (the agent maintains it)
state.json          sources, per-video status, digest marks
cookies.txt         your login session, mode 0600, never printed
```

## What works without login

| | No login | Logged in |
|---|---|---|
| Video metadata, public favorites | ✅ | ✅ |
| Subtitles (CC and AI) | ❌ (`need_login_subtitle`) | ✅ |
| Private favorites, uploader video lists | ❌ (risk control -352) | ✅ |

In testing, about 80% of saved videos had usable AI subtitles once logged in. Most of the rest were music or sound demos, so speech-to-text isn't built yet.

## Be aware

- Logging in uses **your own account**. Requests are slow and sequential (~1.5 s apart), and `sync` stops at the first risk-control error, but there's still some risk of rate limiting.
- Reading subtitles for personal use is a terms-of-service grey area. This tool doesn't download videos.
- AI subtitles contain homophone errors. Check quotes against the video.

## Related projects

[Agent-Reach](https://github.com/Panniantong/Agent-Reach) gives agents read access to about 15 platforms, Bilibili included. Use it if you just want an agent to read **one link** (search, trending, video info, subtitles). Use bili-digest if you want to **keep up** with favorites and uploaders over time.

| | Agent-Reach | bili-digest |
|---|---|---|
| Platforms | ~15 | Bilibili only |
| One video's subtitles | ✅ (first part, via `bili-cli`) | ✅ (all parts, no dependencies) |
| Favorites folders, uploader tracking | ❌ | ✅ |
| Incremental sync, local library | ❌ | ✅ |
| Triage + watch/skim/skip digests | ❌ | ✅ |

## How it was built

Designed with the [look-before-you-build](https://github.com/gxxxr-111/look-before-you-build) preflight skill. The design brief is in [`docs/preflight/`](docs/preflight/), and lessons learned are in [`PREFLIGHT.md`](PREFLIGHT.md).

## Tests

```bash
python3 -m unittest discover tests   # offline, no network
```

## License

[MIT](LICENSE). Not affiliated with Bilibili.
