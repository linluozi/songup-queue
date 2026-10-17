/**
 * 生成交付用截图：模拟 3 个客人点歌 + 主机正在播 B站，各拍一张。
 * 用法：node verify/shots.cjs http://127.0.0.1:5066
 */

const { chromium } = require('playwright');

const BASE = process.argv[2] || 'http://127.0.0.1:5066';

(async () => {
  const browser = await chromium.launch({
    channel: 'msedge',
    headless: true,
    args: ['--autoplay-policy=no-user-gesture-required', '--no-sandbox'],
  });

  const hostCtx = await browser.newContext({ viewport: { width: 1366, height: 768 } });
  const host = await hostCtx.newPage();

  await host.goto(BASE + '/api/health', { waitUntil: 'domcontentloaded' });
  await host.evaluate(() => fetch('/api/clear', { method: 'POST' }));

  // 三个客人，各自一个 context（独立 session）
  const guestCtxs = [];
  const picks = [
    [{ id: 'BV1d4411N7zD', title: '周杰伦 - 晴天（4K 修复 MV）', kind: 'bilibili', url: '' },
     { id: 'demo-track-1', title: 'DEMO TRACK 1（本地示例 · 8 秒）', kind: 'local', url: '/static/demo-track-1.mp4' }],
    [{ id: 'BV15S4y1R72L', title: '久石让《天空之城》千人大合唱现场', kind: 'bilibili', url: '' },
     { id: 'demo-track-2', title: 'DEMO TRACK 2（本地示例 · 8 秒）', kind: 'local', url: '/static/demo-track-2.mp4' }],
    [{ id: 'BV1GJ411x7h7', title: 'Rick Astley - Never Gonna Give You Up（B站）', kind: 'bilibili', url: '' }],
  ];

  for (const songs of picks) {
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } });
    guestCtxs.push(ctx);
    const p = await ctx.newPage();
    await p.goto(BASE + '/api/health', { waitUntil: 'domcontentloaded' });
    for (const s of songs) {
      await p.evaluate((song) => fetch('/api/add', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(song),
      }), s);
    }
  }

  // 主机开播
  await host.goto(BASE + '/host', { waitUntil: 'networkidle', timeout: 25000 });
  await host.locator('#btnNext').click();
  await host.waitForTimeout(9000);   // 等 B站播放器出画面
  await host.screenshot({ path: 'outputs/host.png' });

  // 客人页：用第三个客人（只点了一首）的视角更好看，重新开一个
  const gctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 });
  const guest = await gctx.newPage();
  await guest.goto(BASE + '/', { waitUntil: 'networkidle', timeout: 25000 });
  await guest.waitForTimeout(1600);
  await guest.screenshot({ path: 'outputs/guest.png', fullPage: true });

  // 客人点歌后的状态（挑一首还没人点的）
  await guest.evaluate(() => fetch('/api/add', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      id: '9bZkp7q19f0', title: 'PSY - GANGNAM STYLE', kind: 'youtube',
      url: 'https://www.youtube.com/watch?v=9bZkp7q19f0',
    }),
  }));
  await guest.reload({ waitUntil: 'networkidle' });
  await guest.waitForTimeout(1400);
  await guest.screenshot({ path: 'outputs/guest-queued.png', fullPage: true });

  // 队列空 + 兜底曲目状态
  await host.evaluate(() => fetch('/api/clear', { method: 'POST' }));
  await host.evaluate(() => fetch('/api/next', { method: 'POST' }));
  await host.waitForTimeout(2600);
  await host.screenshot({ path: 'outputs/host-empty.png' });

  console.log('截图完成: outputs/host.png, guest.png, guest-queued.png, host-empty.png');
  await browser.close();
})().catch((e) => { console.error('崩溃:', e.message); process.exit(2); });
