"""Offline tests: no network. Run with `python3 -m unittest discover tests`."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/bili-digest/scripts"))
import bilidigest as bd  # noqa: E402


class PureHelpers(unittest.TestCase):
    def test_wbi_known_vector(self):
        # Example from the community-maintained bilibili-API-collect docs.
        mixin = bd.mixin_key("7cd084941338484aae1ad9425b84077c", "4932caff0ff746eab6f01bf08b70ac45")
        self.assertEqual(mixin, "ea1db124af3c7062474693fa704f4ff8")
        q = bd.wbi_sign({"foo": "114", "bar": "514", "zab": 1919810}, mixin, wts=1702204169)
        self.assertTrue(q.endswith("w_rid=8f6f2b5b3d485fe1886cec6a0be8c5d4"), q)

    def test_parse_ids(self):
        self.assertEqual(bd.parse_video_id("https://www.bilibili.com/video/BV1GJ411x7h7/?p=2"), "BV1GJ411x7h7")
        self.assertEqual(bd.parse_video_id("av170001"), "av170001")
        self.assertIsNone(bd.parse_video_id("hello"))
        self.assertEqual(bd.parse_fav_id("https://space.bilibili.com/1/favlist?fid=123456&ftype=create"), "123456")
        self.assertEqual(bd.parse_fav_id("98765"), "98765")

    def test_pick_track_prefers_human_chinese(self):
        tracks = [{"lan": "en-US"}, {"lan": "ai-zh"}, {"lan": "zh-CN"}]
        self.assertEqual(bd.pick_track(tracks)["lan"], "zh-CN")
        self.assertEqual(bd.pick_track([{"lan": "en-US"}, {"lan": "ai-zh"}])["lan"], "ai-zh")
        self.assertIsNone(bd.pick_track([]))

    def test_subtitle_to_text_paragraphs(self):
        body = {"body": [{"from": 0, "to": 2, "content": "大家好"},
                         {"from": 2, "to": 61, "content": "今天聊聊搜索"},
                         {"from": 61, "to": 63, "content": "Monte Carlo"},
                         {"from": 63, "to": 65, "content": "tree search"}]}
        out = bd.subtitle_to_text(body)
        self.assertEqual(out, "[00:00] 大家好，今天聊聊搜索\n\n[01:01] Monte Carlo tree search")

    def test_render_markdown_front_matter(self):
        md = bd.render_markdown({"bvid": "BV1", "title": "标题 \"x\"", "url": "u", "transcript_source": "none",
                                 "missing_reason": "needs login"}, None)
        self.assertTrue(md.startswith('---\nbvid: "BV1"\ntitle: "标题 \\"x\\""'))
        self.assertIn("_No transcript yet: needs login._", md)


class LoginHelpers(unittest.TestCase):
    def test_cookies_from_success_url(self):
        url = ("https://passport.biligame.com/x/passport-login/web/crossDomain?"
               "DedeUserID=7&DedeUserID__ckMd5=ab&Expires=1&SESSDATA=s%2C1%2Cx&bili_jct=j&gourl=x")
        self.assertEqual(bd.login_cookies_from_url(url),
                         {"SESSDATA": "s,1,x", "bili_jct": "j", "DedeUserID": "7", "DedeUserID__ckMd5": "ab"})

    def test_saved_cookie_file_is_private_and_reloads(self):
        import http.cookiejar, os, stat
        with tempfile.TemporaryDirectory() as t:
            path = Path(t) / "sub" / "cookies.txt"
            jar = http.cookiejar.MozillaCookieJar()
            jar.set_cookie(bd.make_cookie("SESSDATA", "v", 4102444800))
            bd.save_cookies(jar, path)
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
            self.assertTrue(bd.Client(path).logged_in)
            self.assertFalse(bd.Client(Path(t) / "missing.txt").logged_in)


class FakeClient:
    logged_in = False

    def __init__(self, with_subs=True):
        self.with_subs, self.calls = with_subs, []

    def video(self, vid):
        self.calls.append(("video", vid))
        return {"bvid": vid, "aid": 1, "cid": 10, "title": f"T-{vid}", "desc": "d",
                "owner": {"name": "UP", "mid": 7}, "pubdate": 1700000000, "duration": 90,
                "pages": [{"cid": 10, "part": "p1"}]}

    def subtitle_tracks(self, aid, cid):
        return ([{"lan": "ai-zh", "subtitle_url": "//x/sub.json"}], False) if self.with_subs else ([], True)

    def subtitle_body(self, url):
        return {"body": [{"from": 0, "to": 3, "content": "你好"}]}

    def fav_items(self, media_id, limit=None):
        yield from ["BVaaaaaaaaaa", "BVbbbbbbbbbb"][:limit]

    def uploader_videos(self, mid, limit=10):
        raise bd.RiskControl(-352, "风控校验失败")


class Pipeline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = bd.Store(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_fetch_with_subtitles(self):
        rec = bd.fetch_video(FakeClient(), self.store, "BVaaaaaaaaaa", "manual")
        self.assertEqual(rec["status"], "ok")
        md = self.store.video_path("BVaaaaaaaaaa").read_text()
        self.assertIn('transcript_source: "subtitle:ai-zh"', md)
        self.assertIn("[00:00] 你好", md)

    def test_fetch_without_login_records_reason(self):
        rec = bd.fetch_video(FakeClient(with_subs=False), self.store, "BVaaaaaaaaaa", "manual")
        self.assertEqual(rec["status"], "needs-login")
        self.assertIn("require login", self.store.video_path("BVaaaaaaaaaa").read_text())

    def run_sync(self, client, retry=False):
        args = type("A", (), {"limit": 20, "retry": retry})()
        bd.cmd_sync(args, client, self.store)

    def test_sync_is_idempotent_and_survives_risk_control(self):
        self.store.state["sources"] = {
            "fav:1": {"kind": "fav", "id": "1", "seen": []},
            "up:7": {"kind": "up", "id": "7", "seen": []}}
        c = FakeClient()
        self.run_sync(c)
        self.assertEqual(sorted(self.store.state["videos"]), ["BVaaaaaaaaaa", "BVbbbbbbbbbb"])
        self.assertIn("-352", self.store.state["sources"]["up:7"]["error"])
        c.calls.clear()
        self.run_sync(c)
        self.assertEqual(c.calls, [], "second sync must not refetch known videos")
        # state survives a reload
        again = bd.Store(Path(self.tmp.name))
        self.assertEqual(len(again.state["videos"]), 2)

    def test_retry_refetches_missing_only(self):
        self.store.state["sources"] = {"fav:1": {"kind": "fav", "id": "1", "seen": []}}
        self.run_sync(FakeClient(with_subs=False))
        self.assertTrue(all(v["status"] == "needs-login" for v in self.store.state["videos"].values()))
        self.run_sync(FakeClient(), retry=True)
        self.assertTrue(all(v["status"] == "ok" for v in self.store.state["videos"].values()))

    def test_digest_marks(self):
        bd.fetch_video(FakeClient(), self.store, "BVaaaaaaaaaa", "manual")
        mark = lambda **kw: bd.cmd_mark(type("A", (), dict({"bvids": ["BVaaaaaaaaaa"], "undo": False, "skip": False}, **kw))(), None, self.store)
        mark()
        rec = self.store.state["videos"]["BVaaaaaaaaaa"]
        self.assertTrue(rec["digested"] and not rec["skipped"])
        self.assertEqual(rec["duration_s"], 90)
        self.assertEqual(rec["chars"], len("[00:00] 你好"))
        mark(skip=True)
        self.assertTrue(rec["digested"] and rec["skipped"])
        mark(undo=True)
        self.assertFalse(rec["digested"] or rec["skipped"])


if __name__ == "__main__":
    unittest.main()
