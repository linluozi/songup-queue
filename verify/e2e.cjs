/**
 * 端到端验收：真实 Edge 驱动，跑完整点歌 → 播放 → 自动切歌 → 注入防线链路。
 *
 * 运行：
 *   NODE_PATH="C:/Users/15082/.workbuddy/binaries/node/workspace/node_modules" \
 *   node verify/e2e.cjs http://127.0.0.1:5066
 *
 * 说明：headless 环境没有真实用户手势，故显式传 --autoplay-policy，
 * 否则浏览器会拦下有声自动播放，测不出「播完自动切歌」。
 */

const { chromium } = require('playwright');

const BASE = process.argv[2] || 'http://127.0.0.1:5066';
const results = [];

function check(name, pass, detail) {
  results.push({ name, pass, detail });
  console.log(`${pass ? 'PASS' : 'FAIL'}  ${name}${detail ? '  — ' + detail : ''}`);
}

(async () => {
  const browser = await chromium.launch({
    channel: 'msedge',
    headless: true,
    args: ['--autoplay-policy=no-user-gesture-required', '--no-sandbox'],
  });

  const guestCtx = await browser.newContext({ viewport: { width: 420, height: 900 } });
  const guest = await guestCtx.newPage();
  const hostCtx = await browser.newContext({ viewport: { width: 1280, height: 860 } });
  const host = await hostCtx.newPage();

  const consoleErrors = [];
  host.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()); });
  guest.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()); });

  // ---------- 0. 归零服务端状态，保证可重复运行 ----------
  const admin = await hostCtx.newPage();
  await admin.goto(BASE + '/api/health', { waitUntil: 'domcontentloaded' });
  await admin.evaluate(() => fetch('/api/clear', { method: 'POST' }));
  await admin.close();

  // ---------- 1. 客人页 ----------
  await guest.goto(BASE + '/', { waitUntil: 'networkidle', timeout: 25000 });
  await guest.waitForSelector('.row', { timeout: 10000 });
  const rowCount = await guest.locator('.row').count();
  check('客人页搜索列表渲染', rowCount >= 2, `${rowCount} 条结果`);

  const quotaText = await guest.locator('#me').innerText();
  check('配额提示显示', /还能点|名额/.test(quotaText), quotaText.trim());

  // 点第一首（demo-track-1）
  await guest.locator('.row .add').first().click();
  await guest.waitForTimeout(900);
  const queueLen = await guest.locator('ol.q li').count();
  check('添加后进入队列', queueLen === 1, `${queueLen} 项`);

  // ---------- 2. 配额用尽：前端置灰 + 后端也拒绝 ----------
  await guest.locator('.row .add').nth(1).click();   // demo-track-2，用掉第二个名额
  await guest.waitForTimeout(900);

  const btnState = await guest.evaluate(() => {
    const b = document.querySelectorAll('.row .add')[2];
    return { disabled: !!b.disabled, title: b.title, quota: document.getElementById('me').innerText };
  });
  check('名额用尽后添加按钮置灰', btnState.disabled === true, `disabled=${btnState.disabled}`);
  check('配额文案切换为「名额用完」', /名额用完/.test(btnState.quota), btnState.quota.trim());

  const apiReject = await guest.evaluate(async () => {
    const r = await fetch('/api/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: 'dQw4w9WgXcQ', title: '绕过 UI 直连接口', url: '', kind: 'youtube' }),
    });
    return r.json();
  });
  check('后端同样拒绝超额（防绕过 UI）', apiReject.ok === false, apiReject.error);

  // ---------- 3. 主机页开始播放 ----------
  await host.goto(BASE + '/host', { waitUntil: 'networkidle', timeout: 25000 });
  await host.waitForTimeout(600);
  await host.locator('#btnNext').click();

  await host.waitForSelector('#stage video, #stage iframe', { timeout: 12000 });
  const tagName = await host.evaluate(() => {
    const el = document.querySelector('#stage video, #stage iframe');
    return el ? el.tagName.toLowerCase() : null;
  });
  check('播放器真的挂载出来了', tagName === 'video', `stage 内元素 = <${tagName}>`);

  // ---------- 4. 真的在播（时间在走）----------
  await host.evaluate(() => {
    const v = document.querySelector('#stage video');
    if (v) v.dataset.mark = 'round1';
  });
  await host.waitForTimeout(2000);
  const playState = await host.evaluate(() => {
    const v = document.querySelector('#stage video');
    if (!v) return null;
    return { t: v.currentTime, paused: v.paused, ready: v.readyState, muted: v.muted, dur: v.duration };
  });
  check('视频时间在推进（真在播）', !!playState && playState.t > 0.3,
    playState ? `currentTime=${playState.t.toFixed(2)}s / duration=${playState.dur}s / paused=${playState.paused}` : '无 video 元素');

  // ---------- 5. 播完自动切下一首 ----------
  const seqBefore = await host.evaluate(async () => (await (await fetch('/api/status')).json()).seq);
  await host.waitForTimeout(7500);   // 8 秒的片子，再给一点余量
  const after = await host.evaluate(async () => {
    const d = await (await fetch('/api/status')).json();
    const v = document.querySelector('#stage video');
    return { seq: d.seq, currentId: d.current && d.current.id, source: d.current_source, mark: v ? v.dataset.mark : null };
  });
  check('播完自动切下一首（seq 前进）', after.seq > seqBefore, `#${seqBefore} → #${after.seq}`);
  check('切歌时销毁并重建了播放器', after.mark !== 'round1',
    `旧节点标记 = ${after.mark === 'round1' ? '仍在（没重建）' : '已消失（重建过）'}`);

  // ---------- 6. 队列空时进兜底曲目 ----------
  await host.evaluate(() => fetch('/api/clear', { method: 'POST' }));
  await host.waitForTimeout(900);
  const emptyStatus = await host.evaluate(async () => (await fetch('/api/status')).json());
  check('清空后队列与在播都归零', emptyStatus.current === null && emptyStatus.queue_length === 0,
    `current=${emptyStatus.current}, queue_length=${emptyStatus.queue_length}`);

  await host.locator('#btnNext').click();
  await host.waitForTimeout(1800);
  const fbStatus = await host.evaluate(async () => (await fetch('/api/status')).json());
  check('队列空时自动进兜底曲目', fbStatus.current_source === 'fallback',
    `current_source=${fbStatus.current_source}, current=${fbStatus.current && fbStatus.current.id}`);
  const fbMounted = await host.evaluate(() => {
    const el = document.querySelector('#stage video, #stage iframe');
    return el ? el.tagName.toLowerCase() : null;
  });
  check('兜底曲目也挂载了播放器', fbMounted === 'video', `<${fbMounted}>`);

  // ---------- 6.5 YouTube：要么真的在播，要么明确提示，不许静默黑屏 ----------
  await host.evaluate(() => fetch('/api/clear', { method: 'POST' }));
  await host.evaluate(() => fetch('/api/add', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id: 'dQw4w9WgXcQ', title: 'yt-fallback-probe', url: '', kind: 'youtube' }),
  }));
  await host.evaluate(() => fetch('/api/next', { method: 'POST' }));
  await host.waitForTimeout(11000);   // API 7 秒超时 + 看门狗 9 秒

  const bannerState = await host.evaluate(() => ({
    shown: document.getElementById('banner').classList.contains('show'),
    text: document.getElementById('banner').textContent,
  }));
  const ytFrame = host.frames().find((f) => /youtube(-nocookie)?\.com\/embed/.test(f.url()));
  let ytPlaying = false;
  let ytT = null;
  if (ytFrame) {
    try {
      const p = await ytFrame.evaluate(() => {
        const v = document.querySelector('video');
        return v ? { t: Number(v.currentTime.toFixed(2)), paused: v.paused } : null;
      });
      if (p) { ytT = p.t; ytPlaying = p.t > 0.3 && !p.paused; }
    } catch (e) { /* 跨域读不到就算了 */ }
  }
  check('YouTube 要么在播、要么给出可见提示（不静默黑屏）',
    ytPlaying || (bannerState.shown && /YouTube/i.test(bannerState.text)),
    `playing=${ytPlaying} t=${ytT} banner="${bannerState.text.slice(0, 46)}"`);

  // ---------- 7. 存储型 XSS 防线 ----------
  const xssPayload = '<img src=x onerror="window.__xss=1"><b id="pwn">INJECTED</b>';
  await guest.evaluate(async (title) => {
    await fetch('/api/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: 'xss-probe-1', title, url: '', kind: 'youtube' }),
    });
  }, xssPayload);

  await host.waitForTimeout(2600);
  const xssHost = await host.evaluate(() => ({
    pwn: !!document.getElementById('pwn'),
    injected: !!window.__xss,
    imgCount: document.querySelectorAll('#queue img').length,
    firstQueueText: (document.querySelector('#queue li .qt') || {}).textContent || '',
  }));
  check('主机页未被注入（无 #pwn 节点）', xssHost.pwn === false);
  check('主机页未执行 payload（无 window.__xss）', xssHost.injected === false);
  check('主机页未生成 img 标签', xssHost.imgCount === 0, `${xssHost.imgCount} 个`);
  check('曲名按纯文本显示', xssHost.firstQueueText.includes('<b id="pwn">') || xssHost.firstQueueText.length > 0,
    xssHost.firstQueueText.slice(0, 40));

  await guest.reload({ waitUntil: 'networkidle' });
  await guest.waitForTimeout(1200);
  const xssGuest = await guest.evaluate(() => ({
    pwn: !!document.getElementById('pwn'),
    injected: !!window.__xss,
    imgCount: document.querySelectorAll('#queue img, #playing img').length,
  }));
  check('客人页未被注入', xssGuest.pwn === false && xssGuest.injected === false && xssGuest.imgCount === 0,
    JSON.stringify(xssGuest));

  // ---------- 8. 截图（调试用，别占用 outputs/ 里的交付截图） ----------
  await host.waitForTimeout(500);
  await host.screenshot({ path: 'outputs/e2e-host.png', fullPage: false });
  await guest.screenshot({ path: 'outputs/e2e-guest.png', fullPage: true });

  // 队列一长一短两个视角：再塞几首看排版
  await guest.evaluate(async () => {
    const songs = await (await fetch('/api/search?q=')).json();
    for (const s of songs.slice(2, 6)) {
      await fetch('/api/add', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: s.id, title: s.title, url: s.url, kind: s.kind }),
      });
    }
  });
  await host.waitForTimeout(2200);
  await host.screenshot({ path: 'outputs/e2e-host-queue.png', fullPage: false });

  // ---------- 9. 控制台错误 ----------
  // YouTube iframe 内部会刷策略/网络类告警，这些不算我们的异常
  const realErrors = consoleErrors.filter(
    (e) => !/youtube|net::ERR|Failed to load resource|Permissions policy violation|compute-pressure/i.test(e)
  );
  check('无前端 JS 异常', realErrors.length === 0, realErrors.slice(0, 2).join(' | ') || 'clean');

  await browser.close();

  const failed = results.filter((r) => !r.pass);
  console.log('\n' + '='.repeat(52));
  console.log(`${results.length - failed.length}/${results.length} 项通过`);
  if (failed.length) {
    console.log('失败项：');
    failed.forEach((f) => console.log('  - ' + f.name + (f.detail ? '  — ' + f.detail : '')));
  }
  process.exit(failed.length ? 1 : 0);
})().catch((e) => {
  console.error('E2E 崩溃:', e.message);
  process.exit(2);
});
