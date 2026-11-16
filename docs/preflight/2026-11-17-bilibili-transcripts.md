# Design brief: Bilibili favorites → transcripts → agent digests

> Date: 2026-11-17 · Tier: 2 · Status: built and in use; speech-to-text deferred

## In one sentence

A small tool plus an agent skill: it keeps a local folder of text transcripts for the Bilibili videos you saved or the uploaders you follow, and an agent turns the unread ones into a short "worth watching?" digest.

## The problem

- **The real need** (solution stripped out): saved videos never get revisited (吃灰). You want to keep up with chosen uploaders and favorites without watching everything, by letting agents read the content for you.
- **How we'll know it works** (runnable checks):
  - `python3 -m unittest discover tests`: 10 offline tests (signing, parsing, transcript formatting, sync idempotency, risk-control handling, digest marks). **Passing.**
  - Live run: `get`, `watch fav`, `sync`, `status` against real Bilibili. **Passing without login** (metadata and public favorites work; transcripts are correctly reported as missing, with the reason).
  - After login: at least 80% of a 20-video sample from your favorites should end up `ok`. On 8 popular videos: 6/8 got AI subtitles; uploader lists now work. On a 20-video favorites sample: 16/20 `ok` (80%); 3 of the 4 misses were music or sound demos.
- **Out of scope**: downloading videos, comments and danmaku, a web UI, posting anything to Bilibili.

## What research found

- **Problem type**: incremental sync of a watch list (the same pattern as an RSS reader: sources, then new items, then idempotent fetch, then local store), plus content ingestion (media to text) and a read-later queue. The standard parts are: remember what you've seen, make every step safe to re-run, and keep the raw text separate from the summaries.
- **Existing options**:
  - bilibili-api-python covers everything but is GPL and heavy.
  - yt-dlp is reportedly blocked by Bilibili since June 2026 (single source).
  - [Agent-Reach](https://github.com/Panniantong/Agent-Reach) (MIT, ~112k stars) is a read-only multi-platform reader for agents. Its Bilibili channel offers search, trending, video info and first-part subtitles through `bili-cli`, with login by reusing browser cookies. It has no favorites, no uploader tracking, no sync state and no digests. *Added after publishing: research cited it only as a source and missed it as an option.*
  - The existing Bilibili skills and MCP servers don't do continuous favorites and uploader tracking. One stores cookies in plain text, and several are flagged as suspicious.
  - **Decision**: borrow the endpoint knowledge and write a thin client (~300 lines, standard library only).
- **Target environment** (tested live, 2026-11-17, from outside mainland China):

  | Resource | Without login |
  |---|---|
  | Video metadata | Works, once a guest cookie is set (a bare request gets HTTP 412) |
  | Subtitles (CC and AI) | **Blocked**: empty list, `need_login_subtitle: true` on 7 of 8 popular videos |
  | Audio stream | Works (206 range response), so speech-to-text is possible without login |
  | Uploader video list | **Blocked** by risk control (-352), even with WBI signing and dm_img params |
  | Public favorites folder | Works |

- **Unverified**: the yt-dlp block, the absence of account-ban reports, SenseVoice vs Whisper speed figures (vendor source).

## Recommended approach

A command-line script syncs tracked sources into `~/BiliDigest/library/<bvid>.md`: one Markdown file per video, with a front-matter header (title, uploader, date, where the transcript came from). It prefers human-made Chinese subtitles, then AI subtitles, and records a clear reason when neither is available. The `bili-digest` skill teaches any agent to run `sync`, read the unread files, write a dated digest with watch / skim / skip verdicts and timestamped key points, and mark the videos as digested.

## Key decisions

| Decision | Choice | Why | Rejected | Cost to change later |
|---|---|---|---|---|
| HTTP client | Own thin stdlib client | No dependencies, MIT-compatible, only 6 endpoints | bilibili-api-python (GPL, heavy), yt-dlp (reportedly blocked) | Low |
| Storage | One Markdown file per video + `state.json` | Agents and people can both read it; works with grep and Obsidian | SQLite (opaque to agents) | Medium: the file format is what agents depend on |
| File name | `<bvid>.md` | Stable when titles change, so re-runs never duplicate | Title-based names | Low |
| Digests | Written by the agent, not the script | Summarizing is the model's job; the script stays deterministic | Calling an LLM API from the script | Low |
| Request pacing | ~1.2–1.7 s between calls, stop at first risk-control error | Behaves like one person browsing | Parallel fetching | Low |
| Data folder | `~/BiliDigest`, override with `BILI_DIGEST_HOME` | Visible and easy to browse | A hidden folder | Low |

## Risks

- **Bilibili changes or tightens endpoints**: medium likelihood. The `sources` errors and `needs-login` statuses make breakage visible right away. The fix is local to one client class.
- **Account rate limiting after login**: low at personal volume, but it's your account. **You need to accept this knowingly.**
- **Terms of service**: reading subtitles for personal use is a grey area, and downloading audio for speech-to-text is a bit greyer. **That's your call.**

## Tooling plan

- Research ran one subagent on a cheaper model (prior art); I did the live probes myself to keep token use down.
- Later: a scheduled daily `sync` (launchd or cron), and `/code-review` before publishing the skill.

## Decisions for you

1. **Log in with your Bilibili account?** Without it there are no subtitles and no uploader tracking. Recommendation: **yes, via a QR-code `login` command** that I'd add. You scan the code with the Bilibili app, the session is saved only to `~/BiliDigest/cookies.txt` (readable only by you), and I never see a password. The alternative is to export a `cookies.txt` from your browser yourself.
2. **Add local speech-to-text for videos without subtitles?** It downloads audio temporarily and runs a model of a few hundred MB on your Mac. Recommendation: **decide after logging in.** First measure how many of your favorites are still `no-subtitles` once AI subtitles are available. If that's more than about 20%, add SenseVoice (best for Mandarin), with mlx-whisper as the backup.
3. **Which folders and uploaders to start with?** Give me one favorites folder link and two or three uploader links.

## Change log

- 2026-11-17: initial version. Live probes overturned the assumption that subtitles are public, so login moved from optional to an ask-first decision.
- 2026-11-17: added QR login. Verified that, once logged in, AI subtitles come through on 6 of 8 videos and the uploader-list block (-352) is gone.
- 2026-11-17: added Agent-Reach to the existing options after the user pointed it out. Verdict unchanged: it covers single-video reading, not the favorites/uploader → digest workflow.
