/**
 * 生成 README 用的截图：正在播本地自制 demo 片，队列里混着 B站/本地曲目。
 * 刻意不让第三方 MV 画面入镜 —— 公开仓库不放有版权的截图。
 *
 * 用法：node verify/docs-shot.cjs http://127.0.0.1:5066
 */

const { chromium } = require('playwright');

const BASE = process.argv[2] || 'http://127.0.0.1:5066';

// 顺序很重要：demo-track-1 必须排第一，这样 next() 播的是自制片
const QUEUE = [
  { id: 'demo-track-1', title: 'DEMO TRACK 1（本地示例 · 8 秒）', kind: 'local', url: '/static/demo-track-1.mp4' },
  { id: 'BV1d4411N7zD', title: '周杰伦 - 晴天（4K 修复 MV）', kind: 'bilibili', url: '' },
  { id: 'BV15S4y1R72L', title: '久石让《天空之城》千人大合唱现场', kind: 'bilibili', url: '' },
  { id: 'demo-track-2', title: 'DEMO TRACK 2（本地示例 · 8 秒）', kind: 'local', url: '/static/demo-track-2.mp4' },
];

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

  // 每人上限 2 首，所以每个 context 只点 1~2 首，模拟 3 个客人
  const batches = [[QUEUE[0]], [QUEUE[1], QUEUE[2]], [QUEUE[3]]];
  for (const songs of batches) {
    const ctx = await browser.newContext();
    const p = await ctx.newPage();
    await p.goto(BASE + '/api/health', { waitUntil: 'domcontentloaded' });
    for (const s of songs) {
      await p.evaluate((song) => fetch('/api/add', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(song),
      }), s);
    }
    await ctx.close();
  }

  await host.goto(BASE + '/host', { waitUntil: 'networkidle', timeout: 25000 });
  await host.locator('#btnNext').click();      // 播 demo-track-1，队列剩 3 首
  await host.waitForTimeout(3600);             // 等画面出来（8 秒片的第 3 秒）
  await host.screenshot({ path: 'docs/screenshot-host.png' });

  const guestCtx = await browser.newContext({ viewport: { width: 400, height: 860 }, deviceScaleFactor: 2 });
  const guest = await guestCtx.newPage();
  await guest.goto(BASE + '/', { waitUntil: 'networkidle', timeout: 25000 });
  await guest.waitForTimeout(1500);
  await guest.screenshot({ path: 'docs/screenshot-guest.png', fullPage: true });

  console.log('docs 截图完成');
  await browser.close();
})().catch((e) => { console.error('崩溃:', e.message); process.exit(2); });
