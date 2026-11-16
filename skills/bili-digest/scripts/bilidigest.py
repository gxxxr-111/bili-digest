#!/usr/bin/env python3
"""bili-digest: turn Bilibili favorites and followed uploaders into a local
library of Markdown transcripts that agents can read, summarize and track.

Standard library only. Data lives in $BILI_DIGEST_HOME (default ~/BiliDigest):
    library/<bvid>.md   one file per video: YAML front matter + transcript
    state.json          watched sources, per-video status, digest marks
    cookies.txt         optional Netscape cookie file (login); never printed
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import http.cookiejar
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
API = "https://api.bilibili.com"
MIXIN_TAB = [46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
             33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
             61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
             36, 20, 34, 44, 52]
RISK_CODES = {-352, -412, -799}
PASSPORT = "https://passport.bilibili.com/x/passport-login/web/qrcode"
LOGIN_COOKIES = ("SESSDATA", "bili_jct", "DedeUserID", "DedeUserID__ckMd5", "sid")


def home() -> Path:
    return Path(os.environ.get("BILI_DIGEST_HOME", Path.home() / "BiliDigest")).expanduser()


# ---------------------------------------------------------------- pure helpers

def mixin_key(img_key: str, sub_key: str) -> str:
    raw = img_key + sub_key
    return "".join(raw[i] for i in MIXIN_TAB)[:32]


def wbi_sign(params: dict, mixin: str, wts: int | None = None) -> str:
    """Return the signed query string for a WBI endpoint."""
    p = dict(params, wts=int(time.time()) if wts is None else wts)
    p = {k: re.sub(r"[!'()*]", "", str(v)) for k, v in sorted(p.items())}
    q = urllib.parse.urlencode(p)
    return q + "&w_rid=" + hashlib.md5((q + mixin).encode()).hexdigest()


def parse_video_id(s: str) -> str | None:
    """Extract a BV id (or 'av123') from a URL or bare id."""
    m = re.search(r"(BV[0-9A-Za-z]{10})", s)
    if m:
        return m.group(1)
    m = re.search(r"\bav(\d+)", s, re.I)
    return f"av{m.group(1)}" if m else None


def parse_fav_id(s: str) -> str | None:
    m = re.search(r"(?:fid|media_id|ml)=?(\d+)", s) or re.fullmatch(r"\s*(\d+)\s*", s)
    return m.group(1) if m else None


def pick_track(tracks: list[dict]) -> dict | None:
    """Prefer human-made Chinese subtitles, then AI Chinese, then anything."""
    if not tracks:
        return None
    def rank(t):
        lan = t.get("lan", "")
        if lan.startswith("ai-"):
            return 1 if "zh" in lan else 3
        return 0 if lan.startswith("zh") else 2
    return sorted(tracks, key=rank)[0]


def fmt_ts(sec: float) -> str:
    sec = int(sec)
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def subtitle_to_text(body: dict, para_seconds: int = 60) -> str:
    """Join subtitle lines into paragraphs, one timestamp per ~para_seconds."""
    paras, cur, start = [], [], None
    for line in body.get("body", []):
        text = line.get("content", "").strip()
        if not text:
            continue
        if start is None:
            start = line.get("from", 0)
        cur.append(text)
        if line.get("to", 0) - start >= para_seconds:
            paras.append(f"[{fmt_ts(start)}] " + _join(cur))
            cur, start = [], None
    if cur:
        paras.append(f"[{fmt_ts(start or 0)}] " + _join(cur))
    return "\n\n".join(paras)


def _join(lines: list[str]) -> str:
    # Chinese lines join without spaces; Latin lines need one.
    out = ""
    for t in lines:
        if out and re.match(r"[A-Za-z0-9]", t[:1]) and re.search(r"[A-Za-z0-9.,!?]$", out):
            out += " "
        elif out and not re.search(r"[，。！？、；：,.!?]$", out):
            out += "，" if re.search(r"[一-鿿]$", out) else " "
        out += t
    return out


def login_cookies_from_url(url: str) -> dict:
    """The QR poll's success URL carries the session cookies as query params."""
    q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
    return {k: q[k][0] for k in LOGIN_COOKIES if q.get(k)}


def make_cookie(name: str, value: str, expires: int | None) -> http.cookiejar.Cookie:
    return http.cookiejar.Cookie(0, name, value, None, False, ".bilibili.com", True, True,
                                 "/", True, True, expires, False, None, None, {})


def save_cookies(jar: http.cookiejar.MozillaCookieJar, path: Path):
    """Write the cookie file readable only by the current user."""
    path.parent.mkdir(parents=True, exist_ok=True)
    old = os.umask(0o077)
    try:
        jar.save(str(path), ignore_discard=True, ignore_expires=True)
    finally:
        os.umask(old)
    os.chmod(path, 0o600)


def render_qr(text: str) -> bool:
    """Draw a QR code in the terminal, using whatever is installed."""
    try:
        import qrcode  # optional: pip install qrcode
        q = qrcode.QRCode(border=1)
        q.add_data(text)
        q.make(fit=True)
        q.print_ascii(invert=True)
        return True
    except ImportError:
        pass
    exe = shutil.which("qrencode")  # optional: brew install qrencode
    if exe:
        return subprocess.run([exe, "-t", "ansiutf8", "-m", "1", text]).returncode == 0
    return False


def yaml_str(v) -> str:
    return json.dumps(v, ensure_ascii=False) if isinstance(v, str) else str(v)


def render_markdown(meta: dict, transcript: str | None) -> str:
    keys = ["bvid", "title", "url", "uploader", "uploader_mid", "published",
            "duration_s", "parts", "transcript_source", "via", "fetched_at"]
    fm = "\n".join(f"{k}: {yaml_str(meta[k])}" for k in keys if meta.get(k) is not None)
    desc = (meta.get("desc") or "").strip()
    parts = [f"---\n{fm}\n---", f"# {meta['title']}"]
    if desc:
        parts.append("> " + desc.replace("\n", "\n> "))
    parts.append("## Transcript")
    parts.append(transcript or "_No transcript yet: " + (meta.get("missing_reason") or "unknown") + "._")
    return "\n\n".join(parts) + "\n"


# ---------------------------------------------------------------- HTTP client

class BiliError(Exception):
    def __init__(self, code, msg):
        super().__init__(f"{code}: {msg}")
        self.code = code


class RiskControl(BiliError):
    pass


class Client:
    def __init__(self, cookie_file: Path | None = None, delay: float = 1.2):
        self.jar = http.cookiejar.MozillaCookieJar()
        if cookie_file and cookie_file.exists():
            self.jar.load(str(cookie_file), ignore_discard=True, ignore_expires=True)
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.delay, self._last, self._mixin = delay, 0.0, None

    @property
    def logged_in(self) -> bool:
        return any(c.name == "SESSDATA" and c.value for c in self.jar)

    def _open(self, url: str, headers: dict | None = None):
        wait = self.delay + random.uniform(0, 0.5) - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.time()
        h = {"User-Agent": UA, "Referer": "https://www.bilibili.com/"}
        h.update(headers or {})
        return self.opener.open(urllib.request.Request(url, headers=h), timeout=20)

    def _guest(self):
        if not any(c.name == "buvid3" for c in self.jar):
            self._open("https://www.bilibili.com/").read()

    def mixin(self) -> str:
        if not self._mixin:
            img = self.get("/x/web-interface/nav", check=False)["data"]["wbi_img"]
            key = lambda u: u.rsplit("/", 1)[1].split(".")[0]
            self._mixin = mixin_key(key(img["img_url"]), key(img["sub_url"]))
        return self._mixin

    def get(self, path: str, params: dict | None = None, signed=False, check=True, tries=3):
        self._guest()
        for attempt in range(tries):
            q = wbi_sign(params or {}, self.mixin()) if signed else urllib.parse.urlencode(params or {})
            url = (path if path.startswith("http") else API + path) + ("?" + q if q else "")
            try:
                data = json.loads(self._open(url).read())
            except urllib.error.HTTPError as e:
                data = {"code": -412 if e.code == 412 else -e.code, "message": f"HTTP {e.code}"}
            code = data.get("code", 0)
            if code in RISK_CODES and attempt < tries - 1:
                time.sleep(5 * (attempt + 1))
                continue
            if check and code != 0:
                raise (RiskControl if code in RISK_CODES else BiliError)(code, data.get("message"))
            return data
        raise RiskControl(-352, "risk control persisted")

    # endpoints
    def video(self, vid: str) -> dict:
        key = {"aid": vid[2:]} if vid.startswith("av") else {"bvid": vid}
        return self.get("/x/web-interface/view", key)["data"]

    def subtitle_tracks(self, aid, cid) -> tuple[list[dict], bool]:
        d = self.get("/x/player/wbi/v2", {"aid": aid, "cid": cid}, signed=True)["data"]
        return d.get("subtitle", {}).get("subtitles", []) or [], bool(d.get("need_login_subtitle"))

    def subtitle_body(self, url: str) -> dict:
        url = "https:" + url if url.startswith("//") else url
        return json.loads(self._open(url).read())

    def fav_items(self, media_id: str, limit: int | None = None):
        pn = 1
        while True:
            d = self.get("/x/v3/fav/resource/list",
                         {"media_id": media_id, "ps": 20, "pn": pn, "platform": "web"})["data"]
            for m in d.get("medias") or []:
                if m.get("type") == 2 and m.get("bvid") and m.get("title") != "已失效视频":
                    yield m["bvid"]
                    if limit is not None:
                        limit -= 1
                        if limit <= 0:
                            return
            if not d.get("has_more"):
                return
            pn += 1

    def fav_info(self, media_id: str) -> dict:
        return self.get("/x/v3/fav/folder/info", {"media_id": media_id})["data"]

    def uploader_videos(self, mid: str, limit: int = 10) -> list[str]:
        d = self.get("/x/space/wbi/arc/search",
                     {"mid": mid, "ps": min(limit, 30), "pn": 1, "order": "pubdate",
                      "dm_img_list": "[]", "dm_img_str": "V2ViR0wgMS4w",
                      "dm_cover_img_str": "QU5HTEUgKEFwcGxlKQ"}, signed=True)["data"]
        return [v["bvid"] for v in (d.get("list") or {}).get("vlist", [])][:limit]


# ---------------------------------------------------------------- store

class Store:
    def __init__(self, root: Path):
        self.root, self.lib = root, root / "library"
        self.lib.mkdir(parents=True, exist_ok=True)
        self.path = root / "state.json"
        self.state = json.loads(self.path.read_text()) if self.path.exists() else {}
        self.state.setdefault("sources", {})
        self.state.setdefault("videos", {})

    def save(self):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, ensure_ascii=False, indent=1))
        tmp.replace(self.path)

    def video_path(self, bvid: str) -> Path:
        return self.lib / f"{bvid}.md"


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def fetch_video(client: Client, store: Store, vid: str, via: str) -> dict:
    v = client.video(vid)
    bvid = v["bvid"]
    texts, sources, need_login = [], [], False
    pages = v.get("pages") or [{"cid": v["cid"], "part": v["title"]}]
    for pg in pages:
        tracks, nl = client.subtitle_tracks(v["aid"], pg["cid"])
        need_login |= nl
        t = pick_track(tracks)
        if not t:
            continue
        body = client.subtitle_body(t["subtitle_url"])
        txt = subtitle_to_text(body)
        texts.append(f"### P{pages.index(pg) + 1} {pg.get('part', '')}\n\n{txt}" if len(pages) > 1 else txt)
        sources.append("subtitle:" + t.get("lan", "?"))
    transcript = "\n\n".join(texts) or None
    if transcript:
        reason, status = None, "ok"
    elif need_login and not client.logged_in:
        reason, status = "subtitles require login (run `login`), or enable the speech-to-text fallback", "needs-login"
    else:
        reason, status = "the video has no subtitles; needs the speech-to-text fallback", "no-subtitles"
    meta = {
        "bvid": bvid, "title": v["title"], "url": f"https://www.bilibili.com/video/{bvid}",
        "uploader": v["owner"]["name"], "uploader_mid": v["owner"]["mid"],
        "published": dt.datetime.fromtimestamp(v["pubdate"]).astimezone().isoformat(timespec="seconds"),
        "duration_s": v.get("duration"), "parts": len(pages),
        "transcript_source": ",".join(sorted(set(sources))) or "none",
        "via": via, "fetched_at": now_iso(), "desc": v.get("desc"), "missing_reason": reason,
    }
    store.video_path(bvid).write_text(render_markdown(meta, transcript))
    rec = store.state["videos"].get(bvid, {})
    rec.update(status=status, title=v["title"], uploader=v["owner"]["name"], via=via,
               published=meta["published"], fetched_at=meta["fetched_at"],
               transcript_source=meta["transcript_source"], duration_s=meta["duration_s"],
               chars=len(transcript or ""))
    rec.setdefault("digested", False)
    store.state["videos"][bvid] = rec
    store.save()
    return rec


# ---------------------------------------------------------------- commands

def source_key(kind: str, ident: str) -> str:
    return f"{kind}:{ident}"


def cmd_get(a, client, store):
    for s in a.videos:
        vid = parse_video_id(s)
        if not vid:
            print(f"skip: not a video id/url: {s}", file=sys.stderr)
            continue
        rec = fetch_video(client, store, vid, "manual")
        print(f"{rec['status']:12} {vid}  {rec['title']}")


def cmd_watch(a, client, store):
    if a.kind == "fav":
        ident = parse_fav_id(a.target)
        if not ident:
            sys.exit("could not find a favorites folder id (fid / media_id) in: " + a.target)
        try:
            name = client.fav_info(ident).get("title")
        except BiliError as e:
            sys.exit(f"cannot read folder {ident} ({e}). Private folders need `login`.")
    else:
        m = re.search(r"(\d+)", a.target)
        if not m:
            sys.exit("could not find an uploader id (mid) in: " + a.target)
        ident, name = m.group(1), a.name
    store.state["sources"][source_key(a.kind, ident)] = {
        "kind": a.kind, "id": ident, "name": name, "added": now_iso(), "seen": []}
    store.save()
    print(f"watching {a.kind}:{ident} {name or ''}".rstrip())


def cmd_unwatch(a, client, store):
    removed = store.state["sources"].pop(a.key, None)
    store.save()
    print("removed" if removed else "no such source", a.key)


def cmd_sources(a, client, store):
    for k, s in store.state["sources"].items():
        err = f"  [last error: {s['error']}]" if s.get("error") else ""
        print(f"{k:28} {s.get('name') or ''}  seen={len(s.get('seen', []))}{err}")


def cmd_sync(a, client, store):
    vids = store.state["videos"]
    todo: list[tuple[str, str]] = []
    for key, s in store.state["sources"].items():
        try:
            if s["kind"] == "fav":
                found = list(client.fav_items(s["id"], limit=a.limit))
            else:
                found = client.uploader_videos(s["id"], limit=a.limit)
            s.pop("error", None)
        except BiliError as e:
            s["error"] = str(e) + ("" if client.logged_in else " (try `login`)")
            print(f"source {key}: {s['error']}", file=sys.stderr)
            continue
        for b in found:
            if b not in s["seen"]:
                s["seen"].append(b)
            if b not in vids or (a.retry and vids[b]["status"] != "ok"):
                todo.append((b, key))
    store.save()
    seen_now, new, failed = set(), 0, 0
    for b, key in todo:
        if b in seen_now:
            continue
        seen_now.add(b)
        try:
            rec = fetch_video(client, store, b, key)
            new += 1
            print(f"{rec['status']:12} {b}  {rec['title']}")
        except BiliError as e:
            failed += 1
            print(f"error        {b}  {e}", file=sys.stderr)
            if isinstance(e, RiskControl):
                print("risk control hit; stopping early, run sync again later", file=sys.stderr)
                break
    print(f"sync done: {new} fetched, {failed} failed, {len(todo) - new - failed} skipped")


def cmd_status(a, client, store):
    vids = store.state["videos"]
    rows = [(b, r) for b, r in vids.items() if not a.undigested or not r.get("digested")]
    rows.sort(key=lambda x: x[1].get("published", ""), reverse=True)
    if a.json:
        print(json.dumps([dict(r, bvid=b, path=str(store.video_path(b))) for b, r in rows],
                         ensure_ascii=False, indent=1))
        return
    counts: dict[str, int] = {}
    for _, r in vids.items():
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print(f"home: {store.root}  login: {'yes' if client.logged_in else 'no'}  " +
          "  ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    for b, r in rows:
        mark = "s" if r.get("skipped") else (" " if r.get("digested") else "*")
        mins = f"{r['duration_s'] // 60:>3}m" if r.get("duration_s") else "  ?m"
        print(f"{mark} {r['status']:11} {r.get('published', '')[:10]} {mins} {b}  "
              f"{r.get('uploader', '')} — {r['title']}")


def cmd_login(a, client, store):
    path = store.root / "cookies.txt"
    d = client.get(PASSPORT + "/generate")["data"]
    if not render_qr(d["url"]):
        sys.exit("No QR renderer found. Install one, then run `login` again:\n"
                 "  python3 -m pip install --user qrcode   or   brew install qrencode")
    print("\nScan with the Bilibili app (我的 → 扫一扫), then confirm on your phone. "
          "The code expires in about 3 minutes.")
    deadline, told = time.time() + 180, False
    while time.time() < deadline:
        time.sleep(1.5)
        p = client.get(PASSPORT + "/poll", {"qrcode_key": d["qrcode_key"]})["data"]
        code = p.get("code")
        if code == 0:
            break
        if code == 86090 and not told:
            print("Scanned. Confirm the login on your phone...")
            told = True
        elif code == 86038:
            sys.exit("QR code expired. Run `login` again.")
    else:
        sys.exit("Timed out waiting for the scan. Run `login` again.")
    if not client.logged_in:  # fall back to the cookies carried in the success URL
        exp = int(time.time()) + 180 * 86400
        for k, v in login_cookies_from_url(p.get("url", "")).items():
            client.jar.set_cookie(make_cookie(k, v, exp))
    if not client.logged_in:
        sys.exit("Login confirmed but no session cookie was returned. Please try again.")
    save_cookies(client.jar, path)
    print(f"Saved session to {path} (readable only by you).")
    cmd_whoami(a, client, store)


def cmd_whoami(a, client, store):
    d = client.get("/x/web-interface/nav", check=False).get("data") or {}
    if d.get("isLogin"):
        print(f"logged in as {d.get('uname')} (mid {d.get('mid')})")
    else:
        print("not logged in" + (" (saved session expired; run `login`)" if client.logged_in else ""))


def cmd_logout(a, client, store):
    path = store.root / "cookies.txt"
    if path.exists():
        path.unlink()
        print(f"Deleted {path}. To also end the session on Bilibili's side, "
              "remove the device under 账号安全 → 登录设备 in the app.")
    else:
        print("not logged in")


def cmd_mark(a, client, store):
    n = 0
    for b in a.bvids:
        if b in store.state["videos"]:
            rec = store.state["videos"][b]
            rec["digested"] = not a.undo
            rec["skipped"] = bool(a.skip and not a.undo)
            n += 1
    store.save()
    label = "not digested" if a.undo else ("skipped" if a.skip else "digested")
    print(f"marked {n} video(s) as {label}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="bilidigest", description=__doc__.split("\n\n")[0])
    ap.add_argument("--home", help="data folder (default $BILI_DIGEST_HOME or ~/BiliDigest)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("get", help="fetch transcripts for video URLs / BV ids")
    p.add_argument("videos", nargs="+")
    p = sub.add_parser("watch", help="track a favorites folder or an uploader")
    p.add_argument("kind", choices=["fav", "up"])
    p.add_argument("target", help="folder URL/id, or uploader space URL/mid")
    p.add_argument("--name", help="label for an uploader")
    p = sub.add_parser("unwatch", help="stop tracking a source, e.g. fav:123")
    p.add_argument("key")
    sub.add_parser("sources", help="list tracked sources")
    p = sub.add_parser("sync", help="fetch new videos from all tracked sources")
    p.add_argument("--limit", type=int, default=20, help="newest N per source (default 20)")
    p.add_argument("--retry", action="store_true", help="also retry videos without a transcript")
    p = sub.add_parser("status", help="list videos in the library")
    p.add_argument("--undigested", action="store_true", help="only videos not yet digested")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("mark-digested", help="mark videos as digested by an agent")
    p.add_argument("bvids", nargs="+")
    p.add_argument("--undo", action="store_true")
    p.add_argument("--skip", action="store_true", help="triaged out: not worth a digest")
    sub.add_parser("login", help="log in by scanning a QR code with the Bilibili app")
    sub.add_parser("whoami", help="show the logged-in account")
    sub.add_parser("logout", help="delete the saved session")
    a = ap.parse_args(argv)
    root = Path(a.home).expanduser() if a.home else home()
    store = Store(root)
    client = Client(root / "cookies.txt")
    {"get": cmd_get, "watch": cmd_watch, "unwatch": cmd_unwatch, "sources": cmd_sources,
     "sync": cmd_sync, "status": cmd_status, "mark-digested": cmd_mark,
     "login": cmd_login, "whoami": cmd_whoami, "logout": cmd_logout}[a.cmd](a, client, store)


if __name__ == "__main__":
    main()
