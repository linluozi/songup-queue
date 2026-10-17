# SongUp Queue v2

聚会点歌队列 —— 公平去重 + 真能播出来的播放器。

思路来自 [motz0815/songup](https://github.com/motz0815/songup)：客人扫码点歌，主机的屏幕负责放。
这个版本重写了原 `optimized-songup-queue` 的引擎与前端，**把上一版宣称但没做的那件事补上了：播放器**。

```
python app.py
客人 → http://<你的局域网IP>:5000
主机 → http://<你的局域网IP>:5000/host
```

<p align="center">
  <img src="docs/screenshot-host.png" alt="主机页：正在播放 + 右侧实时队列" width="88%">
</p>

<p align="center">
  <img src="docs/screenshot-guest.png" alt="客人页：搜索曲库、看排队、看配额" width="300">
</p>

> 截图里的播放画面是仓库自带的 8 秒测试片（ffmpeg 生成的纯色帧），不含任何第三方素材。

---

## 上一版的问题，逐条处置

| 上一版的问题 | 怎么发现的 | v2 怎么改 |
|---|---|---|
| **「强制刷新播放」零实现**：README 说会销毁重建播放实例，但两个模板里没有任何 iframe/video | 全仓 grep `iframe\|video\|Player` 零命中；zip 里还留着一个空的 `static/` 目录 | 主机页真挂播放器：YouTube IFrame / B站 iframe / 本地 `<video>` 三种，按 `kind` 渲染 |
| 相同 id 连播时播放器不重载 | 引擎没有「播放序号」概念 | 引擎维护 `seq`，每次推进 +1；前端只比 `seq`，变了就 `replaceChildren()` 重建整个舞台 |
| **存储型 XSS**：客人提交的曲名进 `innerHTML`，任何人扫码都能往所有页面注入脚本 | 真实 Edge 里塞 `<b id=pwn>INJECTED</b>`，`document.getElementById('pwn')` 返回 true | 前端全部改用 `createElement` + `textContent`，一处 `innerHTML` 拼用户数据都没有 |
| **去重漏掉正在播放的歌**：播着 A 时能再点一次 A | `add()` 只查 `_queue` | `contains()` 同时查队列与 `current` |
| **配额口径错**：`max_per_user=2` 实际能占 3 个位（在播那首不计数） | 加满 2 首 → `next()` → 计数变 1 → 又能加 | 计数改为「占位」语义：在播 + 排队都算；歌真正播完才释放 |
| 曲名含单引号会截断 `onclick='...'`，按钮点不动 | `Don't Stop Me Now` 直接把属性断成两半 | 去掉内联 onclick，全部 `addEventListener` |
| `skip` 记的是切走前那首，被跳过的歌反而不进冷却 | 读 `next()` 的冷却逻辑 | `_finish_current()` 统一处理：谁结束就记谁 |
| `clear()` 不清冷却表 | 清空队列后仍被 cooldown 挡住 | `clear()` 一并清 `_recently_played` 与 fallback 游标 |
| `defaultdict` 读访问给被拒用户留 0 值幽灵键，永不回收 | `status()['user_counts']` 里出现 `{'ghost_user': 0}` | 换普通 dict，`.get(user, 0)` 读，归零即删键 |
| 队列空了直接进 fallback，主机不知道「没歌了」 | `next()` 永远返回非 None | `status.current_source` 明确区分 `queue / fallback / empty`，主机页据此提示 |
| `debug=True` + `0.0.0.0` + 硬编码 secret_key | 代码里写死 | `debug` 关闭，secret 走环境变量或随机生成 |

回归测试 `tests/test_queue.py` 里每条用例都对着上面一行写的。

---

## 三种曲源

| kind | id 长什么样 | 播放方式 | 播完能自动下一首吗 |
|---|---|---|---|
| `local` | 任意（如 `demo-track-1`） | `<video>` 放 `/static/xxx.mp4` | ✅ `ended` 事件 |
| `bilibili` | `BV` + 10 位 | `player.bilibili.com` iframe | ❌ 官方嵌入没有结束回调，手动点 |
| `youtube` | 11 位 | IFrame API | ✅ `ENDED` 事件（需要能访问 youtube.com） |

`kind` 不传时会按 id 形状自动猜。

**国内建议以 B站 + 本地为主**：仓库自带的曲库里前三首是 B站（周杰伦晴天 4K / 天空之城千人大合唱 / Never Gonna Give You Up），实测能正常出画面出声；YouTube 那 8 首需要代理，连不上时主机会给出明确提示而不是黑屏。

---

## 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `SONGUP_PORT` | `5000` | 监听端口 |
| `SONGUP_MAX_PER_USER` | `2` | 每人同时最多占几首（含正在播的） |
| `SONGUP_COOLDOWN` | `0` | 一首歌播完后多少秒内不能再点 |
| `SONGUP_HOST_KEY` | 空 | 设了就要求主机页带 `?key=...`，防止客人清空全场队列 |
| `SONGUP_SECRET` | 随机 | Flask session 签名密钥，不设则每次重启重置 |
| `SONGUP_FALLBACK` | `on` | 设成 `off` 可关闭「队列空了播兜底曲目」 |

---

## 验证

```bash
# 引擎回归（27 条，不需要起服务）
python -m unittest discover -s tests -v

# 端到端（真实 Edge 驱动，需要先 python app.py）
NODE_PATH=<全局 node_modules> node verify/e2e.cjs http://127.0.0.1:5000
```

`verify/e2e.cjs` 覆盖 20 项：从搜索点歌、配额置灰、播放器挂载、`currentTime` 真的在走、播完自动切、切歌时 DOM 节点确实被换掉、空队列进兜底、YouTube 不静默失败、到 XSS payload 在主机页与客人页都只当纯文本。

`verify/bili.cjs` 单独验 B站嵌入能不能真播（进 iframe 读 `video.currentTime` 看有没有在推进）。

---

## 已知限制

- **单房间**：全局一个队列，多人多房间要按房间 id 分桶（引擎本身无状态依赖，加个 dict 就行）
- **无持久化**：重启即清空
- **B站嵌入带官方浮层**（「进入哔哩哔哩观看更高清」），这是 B站 播放器自带的，去不掉
- **主机接口无鉴权**：默认任何人都能调 `/api/clear`，需要的话设 `SONGUP_HOST_KEY`
- 演示曲库里的 YouTube 视频只是占位，国内直连放不出来

## License

MIT。算法核心 `queue_engine.py` 不依赖 Flask，可单独移植。
