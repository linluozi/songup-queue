"""
FairUniqueQueue —— 公平去重队列引擎（v2）

相对 v1 的修正：
1. 去重覆盖「正在播放」的那一首（v1 只查队列，播着的歌能再被点一次）
2. 配额口径统一为「占位」（在播 + 在队列），v1 在播的歌不计数，max_per_user=2 实际能占 3 个位
3. 冷却记录的是「刚结束播放的歌」，v1 记的是被切走前的上一首，语义是反的
4. clear() 一并清空冷却表与 fallback 游标
5. _user_counts 改普通 dict，v1 用 defaultdict 导致「被拒绝的用户」也在表里留一条 0 值幽灵键
6. 新增 seq（播放序号）：每次推进 +1，播放器据此强制重建，即使连续两首是同一个 id
7. 新增 kind（youtube / bilibili / local），播放器按来源渲染不同元素
8. 输入校验：id 形状、标题长度、fallback 不参与配额

本模块不依赖 Flask，可单独移植。
"""

from __future__ import annotations

import re
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Optional

# YouTube video id：11 位 [A-Za-z0-9_-]
_RE_YOUTUBE = re.compile(r"^[A-Za-z0-9_-]{11}$")
# Bilibili BV 号：BV + 10 位
_RE_BILIBILI = re.compile(r"^BV[0-9A-Za-z]{10}$")

MAX_TITLE_LEN = 200
FALLBACK_OWNER = "fallback"


def detect_kind(song_id: str, kind: Optional[str] = None) -> str:
    """推断播放源。显式传入优先，否则按 id 形状猜。"""
    if kind in ("youtube", "bilibili", "local"):
        return kind
    if _RE_BILIBILI.match(song_id):
        return "bilibili"
    if _RE_YOUTUBE.match(song_id):
        return "youtube"
    return "local"


@dataclass
class Song:
    id: str
    title: str
    added_by: str
    added_at: float = field(default_factory=time.time)
    url: str = ""
    kind: str = "youtube"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "added_by": self.added_by,
            "added_at": self.added_at,
            "url": self.url,
            "kind": self.kind,
        }


class FairUniqueQueue:
    """FIFO 去重队列 + 每人占位上限 + 可选冷却。"""

    def __init__(self, max_per_user: int = 2, cooldown_seconds: int = 0):
        if max_per_user < 1:
            raise ValueError("max_per_user 必须 >= 1")
        self.max_per_user = max_per_user
        self.cooldown_seconds = max(0, cooldown_seconds)

        self._queue: "OrderedDict[str, Song]" = OrderedDict()
        # 用户占位数：在播 + 在排队，都算
        self._user_counts: dict[str, int] = {}
        # song_id -> 结束播放的时间戳
        self._recently_played: dict[str, float] = {}

        self.current: Optional[Song] = None
        self.fallback: list[Song] = []
        self._fallback_index = 0
        self._seq = 0  # 播放序号：每次推进 +1，播放器据此判断是否需要重建
        self._current_source = "empty"  # queue / fallback / empty

    # ---------- 写入 ----------

    def add(self, song_id: str, title: str, user: str, url: str = "", kind: Optional[str] = None) -> dict:
        song_id = (song_id or "").strip()
        if not song_id:
            return {"ok": False, "error": "缺少歌曲 id"}
        if len(song_id) > 64:
            return {"ok": False, "error": "歌曲 id 过长"}

        title = (title or "").strip()[:MAX_TITLE_LEN] or "未知曲目"

        # 1. 去重：队列 + 正在播放
        if self.contains(song_id):
            return {"ok": False, "error": "这首歌已经在队列里了"}

        # 2. 冷却
        if self.cooldown_seconds > 0:
            last = self._recently_played.get(song_id)
            if last is not None:
                left = self.cooldown_seconds - (time.time() - last)
                if left > 0:
                    return {"ok": False, "error": f"这首歌刚播过，还要等 {int(left) + 1} 秒"}

        # 3. 配额（在播的歌也占位）
        if self._user_counts.get(user, 0) >= self.max_per_user:
            return {"ok": False, "error": f"你已经有 {self.max_per_user} 首在队列里了，等播完再点"}

        song = Song(id=song_id, title=title, added_by=user, url=url, kind=detect_kind(song_id, kind))
        self._queue[song_id] = song
        self._user_counts[user] = self._user_counts.get(user, 0) + 1
        return {"ok": True, "song": song.to_dict()}

    # ---------- 推进 ----------

    def next(self) -> dict:
        """结束当前曲目并推进到下一首。返回 {source, song}。"""
        self._finish_current()

        if self._queue:
            _, song = self._queue.popitem(last=False)
            self.current = song
            self._current_source = "queue"
            self._seq += 1
            return {"source": "queue", "song": song.to_dict()}

        if self.fallback:
            song = self.fallback[self._fallback_index % len(self.fallback)]
            self._fallback_index += 1
            self.current = song
            self._current_source = "fallback"
            self._seq += 1
            return {"source": "fallback", "song": song.to_dict()}

        self.current = None
        self._current_source = "empty"
        self._seq += 1
        return {"source": "empty", "song": None}

    def skip(self) -> dict:
        """跳过当前曲目（与 next 等价，语义上由主机主动触发）。"""
        return self.next()

    def remove(self, song_id: str) -> bool:
        """从队列中删除指定歌曲。正在播放的歌不在此列（用 skip）。"""
        song = self._queue.pop(song_id, None)
        if song is None:
            return False
        self._release(song.added_by)
        return True

    def clear(self) -> None:
        self._queue.clear()
        self._user_counts.clear()
        self._recently_played.clear()
        self.current = None
        self._current_source = "empty"
        self._fallback_index = 0
        self._seq += 1

    def set_fallback(self, songs: list[dict]) -> None:
        self.fallback = [
            Song(
                id=str(s["id"]),
                title=str(s.get("title", "未知曲目"))[:MAX_TITLE_LEN],
                added_by=FALLBACK_OWNER,
                url=s.get("url", ""),
                kind=detect_kind(str(s["id"]), s.get("kind")),
            )
            for s in songs
        ]
        self._fallback_index = 0

    # ---------- 查询 ----------

    def contains(self, song_id: str) -> bool:
        if song_id in self._queue:
            return True
        return self.current is not None and self.current.id == song_id

    def list_queue(self) -> list[dict]:
        return [s.to_dict() for s in self._queue.values()]

    def status(self) -> dict:
        return {
            "seq": self._seq,
            "current": self.current.to_dict() if self.current else None,
            "current_source": self._current_source,
            "queue": self.list_queue(),
            "user_counts": dict(self._user_counts),
            "queue_length": len(self._queue),
            "max_per_user": self.max_per_user,
            "cooldown_seconds": self.cooldown_seconds,
        }

    # ---------- 内部 ----------

    def _finish_current(self) -> None:
        """结束当前曲目：记冷却、释放占位。fallback 曲目不参与配额。"""
        song = self.current
        if song is None:
            return
        if song.added_by != FALLBACK_OWNER:
            self._recently_played[song.id] = time.time()
            self._release(song.added_by)
        self.current = None

    def _release(self, user: str) -> None:
        left = self._user_counts.get(user, 0) - 1
        if left > 0:
            self._user_counts[user] = left
        else:
            self._user_counts.pop(user, None)


if __name__ == "__main__":
    q = FairUniqueQueue(max_per_user=2)
    print(q.add("dQw4w9WgXcQ", "Rick Astley - Never Gonna Give You Up", "u1"))
    print(q.add("dQw4w9WgXcQ", "重复点同一首", "u2"))      # 拒绝：重复
    print(q.next())                                        # 播放第一首
    print(q.add("dQw4w9WgXcQ", "在播的歌再点一次", "u2"))   # 拒绝：去重覆盖 current
    print("status:", q.status())
