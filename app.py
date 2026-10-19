"""
SongUp Queue v2 —— 公平去重队列 + 真正的播放器

相对 v1 的改动：
- host 页有了播放器：YouTube iframe / Bilibili iframe / 本地 <video> 三种，按 kind 渲染
- 播放器由 seq 驱动重建：每次推进都销毁旧实例，即使连续两首是同一个 id 也不会卡住
- YouTube 走 IFrame API 的 ENDED 事件自动下一首；本地 <video> 用 ended 事件；B站需手动点
- 曲名一律转义后再进 DOM（v1 是存储型 XSS）
- 主机操作可选口令（SONGUP_HOST_KEY），不设则和以前一样无需口令
- debug 关闭，secret_key 不再硬编码

启动：python app.py
客人：http://<本机IP>:5000
主机：http://<本机IP>:5000/host
"""

import os
import secrets
import socket
import uuid

from flask import Flask, jsonify, render_template, request, session

import qrmini
from queue_engine import FairUniqueQueue, MAX_TITLE_LEN

app = Flask(__name__)
app.secret_key = os.environ.get("SONGUP_SECRET") or secrets.token_hex(24)
app.json.ensure_ascii = False  # 中文不要转成 \uXXXX

HOST_KEY = os.environ.get("SONGUP_HOST_KEY", "").strip()

queue = FairUniqueQueue(
    max_per_user=int(os.environ.get("SONGUP_MAX_PER_USER", "2")),
    cooldown_seconds=int(os.environ.get("SONGUP_COOLDOWN", "0")),
)

# 演示曲库。kind=local 的两首是 ffmpeg 生成的 8 秒测试片，保证离线也能点播看到效果。
DEMO_SONGS = [
    {
        "id": "demo-track-1",
        "title": "DEMO TRACK 1（本地示例 · 8 秒）",
        "kind": "local",
        "url": "/static/demo-track-1.mp4",
    },
    {
        "id": "demo-track-2",
        "title": "DEMO TRACK 2（本地示例 · 8 秒）",
        "kind": "local",
        "url": "/static/demo-track-2.mp4",
    },
    {
        "id": "BV1d4411N7zD",
        "title": "周杰伦 - 晴天（4K 修复 MV）",
        "kind": "bilibili",
        "url": "https://www.bilibili.com/video/BV1d4411N7zD",
    },
    {
        "id": "BV15S4y1R72L",
        "title": "久石让《天空之城》千人大合唱现场",
        "kind": "bilibili",
        "url": "https://www.bilibili.com/video/BV15S4y1R72L",
    },
    {
        "id": "BV1GJ411x7h7",
        "title": "Rick Astley - Never Gonna Give You Up（B站）",
        "kind": "bilibili",
        "url": "https://www.bilibili.com/video/BV1GJ411x7h7",
    },
    {
        "id": "dQw4w9WgXcQ",
        "title": "Rick Astley - Never Gonna Give You Up",
        "kind": "youtube",
        "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    },
    {
        "id": "9bZkp7q19f0",
        "title": "PSY - GANGNAM STYLE",
        "kind": "youtube",
        "url": "https://www.youtube.com/watch?v=9bZkp7q19f0",
    },
    {
        "id": "kJQP7kiw5Fk",
        "title": "Luis Fonsi - Despacito",
        "kind": "youtube",
        "url": "https://www.youtube.com/watch?v=kJQP7kiw5Fk",
    },
    {
        "id": "JGwWNGJdvx8",
        "title": "Ed Sheeran - Shape of You",
        "kind": "youtube",
        "url": "https://www.youtube.com/watch?v=JGwWNGJdvx8",
    },
    {
        "id": "OPf0YbXqDm0",
        "title": "Mark Ronson - Uptown Funk",
        "kind": "youtube",
        "url": "https://www.youtube.com/watch?v=OPf0YbXqDm0",
    },
    {
        "id": "fJ9rUzIMcZQ",
        "title": "Queen - Bohemian Rhapsody",
        "kind": "youtube",
        "url": "https://www.youtube.com/watch?v=fJ9rUzIMcZQ",
    },
    {
        "id": "hTWKbfoikeg",
        "title": "Nirvana - Smells Like Teen Spirit",
        "kind": "youtube",
        "url": "https://www.youtube.com/watch?v=hTWKbfoikeg",
    },
    {
        "id": "YQHsXMglC9A",
        "title": "Adele - Hello",
        "kind": "youtube",
        "url": "https://www.youtube.com/watch?v=YQHsXMglC9A",
    },
]

if os.environ.get("SONGUP_FALLBACK", "on").lower() not in ("off", "0", "false", "no"):
    queue.set_fallback([DEMO_SONGS[0], DEMO_SONGS[1]])


# ---------- 工具 ----------

def get_user_id() -> str:
    if "user_id" not in session:
        session["user_id"] = f"guest_{uuid.uuid4().hex[:8]}"
    return session["user_id"]


def host_authorized() -> bool:
    if not HOST_KEY:
        return True
    supplied = request.headers.get("X-Host-Key") or request.args.get("key") or ""
    return secrets.compare_digest(supplied, HOST_KEY)


def host_required():
    return jsonify({"ok": False, "error": "需要主机口令（URL 加 ?key=...）"}), 403


def fail(msg: str, code: int = 200):
    return jsonify({"ok": False, "error": msg}), code


def sanitize_local_url(url: str) -> str:
    """local 类型只允许站内 static 资源，避免客户端塞任意地址进播放器。"""
    url = (url or "").strip()
    if url.startswith("/static/") and ".." not in url:
        return url
    return ""


def _port() -> int:
    return int(os.environ.get("SONGUP_PORT", "5000"))


# ---------- 页面 ----------

@app.get("/")
def index():
    return render_template("guest.html")


@app.get("/host")
def host_page():
    join_url = "http://%s:%d" % (lan_ip(), _port())
    if HOST_KEY:
        key = request.args.get("key", "")
        if not secrets.compare_digest(key, HOST_KEY):
            return render_template("host.html", host_key="", unlocked=False,
                                   join_url=join_url, join_qr=""), 403
        return render_template("host.html", host_key=key, unlocked=True,
                               join_url=join_url, join_qr=qrmini.svg(join_url)), 200
    return render_template("host.html", host_key="", unlocked=True,
                           join_url=join_url, join_qr=qrmini.svg(join_url))


# ---------- 只读接口 ----------

@app.get("/api/status")
def api_status():
    return jsonify(queue.status())


@app.get("/api/me")
def api_me():
    return jsonify({"user_id": get_user_id(), "max_per_user": queue.max_per_user})


@app.get("/api/search")
def api_search():
    q = (request.args.get("q") or "").strip().lower()
    if not q:
        return jsonify(DEMO_SONGS)
    hits = [
        s for s in DEMO_SONGS
        if q in s["title"].lower() or q in s["id"].lower()
    ]
    return jsonify(hits)  # 无结果就返回空列表，别把全量当结果


# ---------- 客人接口 ----------

@app.post("/api/add")
def api_add():
    data = request.get_json(silent=True) or {}
    song_id = str(data.get("id") or "").strip()
    title = str(data.get("title") or "")
    url = str(data.get("url") or "")
    kind = data.get("kind")

    if not song_id:
        return fail("缺少歌曲 id", 400)
    if len(title) > MAX_TITLE_LEN * 4:
        title = title[: MAX_TITLE_LEN * 4]

    # 只接受曲库里的 local 资源，或正常外链
    if kind == "local" or (not kind and song_id.startswith("demo-")):
        url = sanitize_local_url(url)
        kind = "local"

    user = get_user_id()
    result = queue.add(song_id, title, user, url=url, kind=kind)
    return jsonify(result)


# ---------- 主机接口（都返回最新 status，前端省一次请求） ----------

@app.post("/api/next")
def api_next():
    if not host_authorized():
        return host_required()
    action = queue.next()
    return jsonify({**queue.status(), "action": action})


@app.post("/api/skip")
def api_skip():
    if not host_authorized():
        return host_required()
    action = queue.skip()
    return jsonify({**queue.status(), "action": action})


@app.post("/api/remove")
def api_remove():
    if not host_authorized():
        return host_required()
    data = request.get_json(silent=True) or {}
    song_id = str(data.get("id") or "")
    if not song_id:
        return fail("缺少 id", 400)
    removed = queue.remove(song_id)
    return jsonify({**queue.status(), "removed": removed})


@app.post("/api/clear")
def api_clear():
    if not host_authorized():
        return host_required()
    queue.clear()
    return jsonify({**queue.status(), "ok": True})


@app.get("/api/health")
def api_health():
    return jsonify({"ok": True, "queue_length": len(queue.list_queue())})


def lan_ip() -> str:
    """探测本机在局域网里的地址，方便打印给客人用的地址。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


if __name__ == "__main__":
    port = _port()
    ip = lan_ip()
    print("=" * 58)
    print(" SongStub · 曲票")
    print(f" 主机页（投屏用）    http://{ip}:{port}/host")
    print(f" 客人页（发到群里）  http://{ip}:{port}")
    if HOST_KEY:
        print(" 已启用主机口令，主机页需带 ?key=<SONGUP_HOST_KEY>")
    print(f" 每人上限 {queue.max_per_user} 首 · 冷却 {queue.cooldown_seconds}s · 兜底 {'on' if queue.fallback else 'off'}")
    print("=" * 58)
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
