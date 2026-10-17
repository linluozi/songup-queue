"""从 B站公开搜索接口挑几首可用的演示曲目（BV 号 + 标题 + 时长）。"""
import json
import re
import urllib.parse
import urllib.request

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Referer": "https://www.bilibili.com"}


def search(keyword, limit=5):
    url = "https://api.bilibili.com/x/web-interface/search/all/v2?" + urllib.parse.urlencode({"keyword": keyword})
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.load(r)
    if data.get("code") != 0:
        print(f"  [搜索失败] {keyword}: code={data.get('code')}")
        return []
    out = []
    for block in (data.get("data") or {}).get("result") or []:
        if block.get("result_type") != "video":
            continue
        for v in block.get("data") or []:
            title = re.sub(r"<[^>]+>", "", v.get("title", ""))
            out.append({
                "bvid": v.get("bvid"),
                "title": title,
                "duration": v.get("duration"),
                "play": v.get("play"),
                "author": v.get("author"),
            })
            if len(out) >= limit:
                return out
    return out


for kw in ["周杰伦 晴天 官方", "久石让 天空之城 音乐会", "lofi 学习 背景音乐"]:
    print(f"\n=== {kw} ===")
    for item in search(kw):
        print(f"  {item['bvid']}  {item['duration']:>7}  {item['play']:>10}  {item['title'][:44]}")
