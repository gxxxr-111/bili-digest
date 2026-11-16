# PREFLIGHT notes: bili-digest

- **Probe before assuming.** Research said subtitles were "probably public". One live curl showed they need login. Check access with real requests before writing the brief.
- **What failure looks like here:** risk-control codes -352/-412 (HTTP 412 for bare requests with no guest cookie), and empty subtitle lists with `need_login_subtitle: true`. Never treat an empty list as "this video has no subtitles" without checking that flag.
- **Check first next time:** whether the endpoint needs WBI signing, a `buvid3` guest cookie, or login. Test each one separately.
- **The real bottleneck is choosing, not transcribing.** Turning everything in the favorites into text was cheap; reading it all would have cost ~200k tokens, much of it on videos outside the user's interests. Triage on metadata (title, uploader, duration, `interests.md`) before reading any transcript, and digest with cheap-model subagents.
- **Speech-to-text matters most for the newest videos from must-read uploaders.** In testing, the newest long talk from a must-read uploader had no AI subtitles yet, more than a week after release. Try `sync --retry` a few days later before deciding on speech-to-text.
