"""FairUniqueQueue 回归测试。

每条用例对应 v1 的一个已实测缺陷，防止回退。
运行：python -m unittest discover -s tests -v
"""

import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from queue_engine import FairUniqueQueue, detect_kind  # noqa: E402


class DedupTest(unittest.TestCase):
    def test_duplicate_in_queue_rejected(self):
        q = FairUniqueQueue(max_per_user=5)
        self.assertTrue(q.add("aaa111", "A", "u1")["ok"])
        r = q.add("aaa111", "A again", "u2")
        self.assertFalse(r["ok"])
        self.assertIn("已经在队列里", r["error"])

    def test_duplicate_against_current_rejected(self):
        """v1 缺陷：去重只查队列，正在播放的歌能被再点一次。"""
        q = FairUniqueQueue(max_per_user=5)
        q.add("aaa111", "A", "u1")
        q.next()
        self.assertEqual(q.current.id, "aaa111")

        r = q.add("aaa111", "A again", "u2")
        self.assertFalse(r["ok"], "在播的歌必须被去重挡住")
        self.assertEqual(q.list_queue(), [], "队列里不应出现第二份 A")

    def test_contains_reports_current(self):
        q = FairUniqueQueue()
        q.add("aaa111", "A", "u1")
        q.next()
        self.assertTrue(q.contains("aaa111"))
        self.assertTrue(q.contains("never-added") is False)


class QuotaTest(unittest.TestCase):
    def test_per_user_limit(self):
        q = FairUniqueQueue(max_per_user=2)
        self.assertTrue(q.add("s1", "S1", "u1")["ok"])
        self.assertTrue(q.add("s2", "S2", "u1")["ok"])
        self.assertFalse(q.add("s3", "S3", "u1")["ok"])

    def test_quota_counts_now_playing(self):
        """v1 缺陷：在播的歌不占配额，max_per_user=2 实际能占 3 个位。"""
        q = FairUniqueQueue(max_per_user=2)
        q.add("s1", "S1", "u1")
        q.add("s2", "S2", "u1")
        q.next()  # s1 开始播放，仍占 u1 的位

        r = q.add("s3", "S3", "u1")
        self.assertFalse(r["ok"], "在播+排队合计已达上限，第 3 首必须被拒")

    def test_quota_released_after_finish(self):
        q = FairUniqueQueue(max_per_user=2)
        q.add("s1", "S1", "u1")
        q.add("s2", "S2", "u1")
        q.next()  # 播 s1
        q.next()  # s1 结束(释放)，s2 开始播
        r = q.add("s3", "S3", "u1")
        self.assertTrue(r["ok"], "s1 已播完，应空出 1 个位")

    def test_users_are_independent(self):
        q = FairUniqueQueue(max_per_user=1)
        self.assertTrue(q.add("s1", "S1", "u1")["ok"])
        self.assertFalse(q.add("s2", "S2", "u1")["ok"])
        self.assertTrue(q.add("s2", "S2", "u2")["ok"])

    def test_remove_releases_quota(self):
        q = FairUniqueQueue(max_per_user=1)
        q.add("s1", "S1", "u1")
        self.assertFalse(q.add("s2", "S2", "u1")["ok"])
        self.assertTrue(q.remove("s1"))
        self.assertTrue(q.add("s2", "S2", "u1")["ok"])

    def test_remove_missing_returns_false(self):
        q = FairUniqueQueue()
        self.assertFalse(q.remove("nope"))

    def test_rejected_add_leaves_no_ghost_key(self):
        """v1 缺陷：defaultdict 读访问给被拒用户留 0 值键。"""
        q = FairUniqueQueue(max_per_user=1)
        q.add("dup", "Dup", "u1")
        for i in range(5):
            q.add("dup", "Dup", f"tryer{i}")  # 全部被去重拒绝
        self.assertNotIn("tryer0", q.status()["user_counts"])
        self.assertEqual(q.status()["user_counts"], {"u1": 1})

    def test_user_counts_cleared_when_zero(self):
        q = FairUniqueQueue(max_per_user=1)
        q.add("s1", "S1", "u1")
        q.next()  # 播 s1
        q.next()  # s1 结束
        self.assertEqual(q.status()["user_counts"], {})


class OrderTest(unittest.TestCase):
    def test_fifo(self):
        q = FairUniqueQueue(max_per_user=99)
        for i in range(4):
            q.add(f"s{i}", f"S{i}", f"u{i}")
        self.assertEqual([s["id"] for s in q.list_queue()], ["s0", "s1", "s2", "s3"])
        self.assertEqual(q.next()["song"]["id"], "s0")
        self.assertEqual(q.next()["song"]["id"], "s1")


class FallbackTest(unittest.TestCase):
    def test_fallback_used_when_queue_empty(self):
        q = FairUniqueQueue()
        q.set_fallback([{"id": "f1", "title": "F1"}, {"id": "f2", "title": "F2"}])
        r = q.next()
        self.assertEqual(r["source"], "fallback")
        self.assertEqual(r["song"]["id"], "f1")
        self.assertEqual(q.next()["song"]["id"], "f2")
        self.assertEqual(q.next()["song"]["id"], "f1", "fallback 应循环")

    def test_source_tells_empty_apart(self):
        """v1 缺陷：队列空时静默进 fallback，主机无法区分“没歌了”。"""
        q = FairUniqueQueue()
        r = q.next()
        self.assertEqual(r["source"], "empty")
        self.assertIsNone(r["song"])
        self.assertEqual(q.status()["queue_length"], 0)

    def test_fallback_does_not_consume_quota(self):
        q = FairUniqueQueue(max_per_user=1)
        q.set_fallback([{"id": "f1", "title": "F1"}])
        q.next()  # 播 fallback
        self.assertEqual(q.status()["user_counts"], {})
        self.assertTrue(q.add("s1", "S1", "u1")["ok"], "fallback 不应占用户配额")

    def test_fallback_not_in_queue(self):
        q = FairUniqueQueue()
        q.set_fallback([{"id": "f1", "title": "F1"}])
        self.assertFalse(q.contains("f1"), "没在播的 fallback 曲目不算队列成员")
        q.next()
        self.assertEqual(q.list_queue(), [])
        self.assertTrue(q.contains("f1"), "正在播的 fallback 仍应被去重挡住")


class CooldownTest(unittest.TestCase):
    def test_cooldown_after_play(self):
        q = FairUniqueQueue(max_per_user=5, cooldown_seconds=60)
        q.add("s1", "S1", "u1")
        q.next()   # 播 s1
        q.next()   # s1 结束，进冷却
        r = q.add("s1", "S1", "u2")
        self.assertFalse(r["ok"])
        self.assertIn("刚播过", r["error"])

    def test_cooldown_expires(self):
        q = FairUniqueQueue(max_per_user=5, cooldown_seconds=0.05)
        q.add("s1", "S1", "u1")
        q.next()
        q.next()
        self.assertFalse(q.add("s1", "S1", "u2")["ok"])
        time.sleep(0.08)
        self.assertTrue(q.add("s1", "S1", "u2")["ok"])

    def test_skipped_song_enters_cooldown(self):
        """v1 缺陷：skip 时记录的是切走前的那首，被跳过的歌反而不进冷却。"""
        q = FairUniqueQueue(max_per_user=5, cooldown_seconds=60)
        q.add("s1", "S1", "u1")
        q.add("s2", "S2", "u1")
        q.next()      # 播 s1
        q.skip()      # s1 被跳过，s2 开始
        self.assertIn("s1", q._recently_played)

    def test_clear_wipes_cooldown(self):
        """v1 缺陷：clear() 后冷却表仍有残留，清空队列依旧被挡。"""
        q = FairUniqueQueue(max_per_user=5, cooldown_seconds=60)
        q.add("s1", "S1", "u1")
        q.next()
        q.next()
        self.assertTrue(q._recently_played)
        q.clear()
        self.assertEqual(q._recently_played, {})
        self.assertTrue(q.add("s1", "S1", "u2")["ok"])


class SeqTest(unittest.TestCase):
    def test_seq_bumps_every_advance(self):
        q = FairUniqueQueue(max_per_user=5)
        q.add("s1", "S1", "u1")
        s0 = q.status()["seq"]
        q.next()
        s1 = q.status()["seq"]
        q.next()
        s2 = q.status()["seq"]
        self.assertEqual((s1, s2), (s0 + 1, s0 + 2))

    def test_same_song_replayed_gets_new_seq(self):
        """相同 id 连播两次时，seq 必须不同 —— 播放器据此强制重建实例。"""
        q = FairUniqueQueue(max_per_user=5)
        q.add("s1", "S1", "u1")
        first = q.next()
        first_seq = q.status()["seq"]

        q.next()  # 播完，队列空
        q.add("s1", "S1", "u2")
        again = q.next()
        again_seq = q.status()["seq"]

        self.assertEqual(first["song"]["id"], again["song"]["id"])
        self.assertNotEqual(first_seq, again_seq)


class ValidationTest(unittest.TestCase):
    def test_empty_id_rejected(self):
        q = FairUniqueQueue()
        self.assertFalse(q.add("", "x", "u1")["ok"])
        self.assertFalse(q.add("   ", "x", "u1")["ok"])

    def test_long_title_truncated(self):
        q = FairUniqueQueue()
        q.add("s1", "あ" * 500, "u1")
        self.assertEqual(len(q.list_queue()[0]["title"]), 200)

    def test_blank_title_defaults(self):
        q = FairUniqueQueue()
        q.add("s1", "   ", "u1")
        self.assertEqual(q.list_queue()[0]["title"], "未知曲目")

    def test_kind_detection(self):
        self.assertEqual(detect_kind("dQw4w9WgXcQ"), "youtube")
        self.assertEqual(detect_kind("BV1GJ411x7h7"), "bilibili")
        self.assertEqual(detect_kind("demo-loop"), "local")
        self.assertEqual(detect_kind("anything", "bilibili"), "bilibili")

    def test_max_per_user_validated(self):
        with self.assertRaises(ValueError):
            FairUniqueQueue(max_per_user=0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
