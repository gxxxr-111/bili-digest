# bili-digest

[English](README.md) | **简体中文**

> **状态：v0.1，实验性。** 为个人使用而写；B 站随时可能调整接口。

B 站收藏的视频往往会"吃灰"。这是一个 Claude Code skill，外加一个无依赖的 Python 小脚本，它会：

1. **同步**：把你的收藏夹和关注的 UP 主同步成本地文字库，每个视频一个 Markdown 文件，包含元数据和带时间戳的文字稿（来自 B 站字幕）。
2. **筛选**：只看元数据（标题、UP 主、时长，以及你的 `interests.md`）就决定哪些值得读，不把 token 花在美食、游戏、音乐这类你不关心的视频上。
3. **摘要**：用便宜的模型子智能体把选中的视频写成按日期归档的摘要，每条给出 **值得看 / 略读 / 跳过** 的结论、要点，以及值得直接跳到的时间点。

## 安装

```
/plugin marketplace add gxxxr-111/bili-digest
/plugin install bili-digest@bili-digest
```

或者把 `skills/bili-digest` 复制到 `~/.claude/skills/`。需要 Python 3.10+；登录二维码需要可选的 `qrcode` 包（`pip install qrcode`）或 `qrencode`。

## 使用

直接对 Claude 说"帮我补一下 B 站收藏夹""关注这个 UP 主：<空间链接>"，或者贴一个 `bilibili.com/video/...` 链接即可。skill 会调用脚本：

```bash
S=~/.claude/skills/bili-digest/scripts/bilidigest.py   # 或插件里的同名脚本
python3 $S login                      # 用 B 站 App 扫码登录
python3 $S watch fav <收藏夹链接或 id>
python3 $S watch up  <空间链接或 mid> --name <备注>
python3 $S sync --limit 20
python3 $S status --undigested
```

数据默认存放在 `~/BiliDigest`（可以用 `BILI_DIGEST_HOME` 修改）：

```
library/<bvid>.md   文字稿 + YAML 头信息
digests/<日期>.md   智能体写的摘要
interests.md        要看 / 跳过 / 必读的内容（由智能体维护）
state.json          订阅源、每个视频的状态、摘要标记
cookies.txt         你的登录会话，权限 0600，从不打印
```

## 不登录能做什么

| | 不登录 | 登录后 |
|---|---|---|
| 视频元数据、公开收藏夹 | ✅ | ✅ |
| 字幕（人工与 AI） | ❌（`need_login_subtitle`） | ✅ |
| 私密收藏夹、UP 主视频列表 | ❌（风控 -352） | ✅ |

测试中，登录后约 80% 的收藏视频有可用的 AI 字幕；剩下的大多是音乐或声音演示，所以暂时没有做语音转文字。

## 注意

- 登录使用的是**你自己的账号**。请求是串行、慢速的（间隔约 1.5 秒），`sync` 一遇到风控就停，但仍有一定被限流的风险。
- 为个人用途读取字幕属于服务条款的灰色地带。本工具不下载视频。
- AI 字幕有同音字错误，引用原话前请对照视频。

## 相关项目

[Agent-Reach](https://github.com/Panniantong/Agent-Reach) 让智能体能读取约 15 个平台的内容，包括 B 站。如果只是想让智能体读**一个链接**（搜索、热门、视频信息、字幕），用它就行；如果想长期**跟进**收藏夹和 UP 主，用 bili-digest。

| | Agent-Reach | bili-digest |
|---|---|---|
| 平台 | 约 15 个 | 仅 B 站 |
| 单个视频字幕 | ✅（仅第一 P，依赖 `bili-cli`） | ✅（所有分 P，无依赖） |
| 收藏夹、跟踪 UP 主 | ❌ | ✅ |
| 增量同步、本地文字库 | ❌ | ✅ |
| 筛选 + 值得看/略读/跳过摘要 | ❌ | ✅ |

## 怎么做出来的

用 [look-before-you-build](https://github.com/gxxxr-111/look-before-you-build) 的 preflight skill 设计。设计简报在 [`docs/preflight/`](docs/preflight/)，经验总结在 [`PREFLIGHT.md`](PREFLIGHT.md)。

## 测试

```bash
python3 -m unittest discover tests   # 离线，不联网
```

## 许可证

[MIT](LICENSE)。与哔哩哔哩无关联。
