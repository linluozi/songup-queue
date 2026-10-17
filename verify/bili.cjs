/**
 * 单独验证 B站嵌入能否真的播起来（国内可用性关键路径）。
 * 用法：node verify/bili.cjs http://127.0.0.1:5066 [BV号]
 */

const { chromium } = require('playwright');

const BASE = process.argv[2] || 'http://127.0.0.1:5066';
const BVID = process.argv[3] || 'BV1d4411N7zD';

(async () => {
  const browser = await chromium.launch({
    channel: 'msedge',
    headless: true,
    args: ['--autoplay-policy=no-user-gesture-required', '--no-sandbox'],
  });
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 860 } });
  const host = await ctx.newPage();

  await host.goto(BASE + '/api/health', { waitUntil: 'domcontentloaded' });
  await host.evaluate(() => fetch('/api/clear', { method: 'POST' }));
  await host.evaluate((bvid) => fetch('/api/add', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id: bvid, title: 'B站测试', url: '', kind: 'bilibili' }),
  }), BVID);

  await host.goto(BASE + '/host', { waitUntil: 'networkidle', timeout: 25000 });
  await host.locator('#btnNext').click();
  await host.waitForSelector('#stage iframe', { timeout: 12000 });

  const iframeSrc = await host.evaluate(() => document.querySelector('#stage iframe').src);
  console.log('iframe src:', iframeSrc);

  // 等 B站播放器把内部 DOM 建起来
  await host.waitForTimeout(9000);

  const frame = host.frames().find((f) => f.url().includes('player.bilibili.com'));
  let probe = { found: false };
  if (frame) {
    try {
      probe = await frame.evaluate(() => {
        const vids = Array.from(document.querySelectorAll('video'));
        const v = vids.find((x) => x.readyState > 0) || vids[0];
        return {
          found: true,
          videoCount: vids.length,
          hasVideo: !!v,
          t: v ? Number(v.currentTime.toFixed(2)) : null,
          paused: v ? v.paused : null,
          ready: v ? v.readyState : null,
          duration: v && isFinite(v.duration) ? Number(v.duration.toFixed(1)) : null,
          bodyLen: document.body ? document.body.innerHTML.length : 0,
        };
      });
    } catch (e) {
      probe = { found: true, error: e.message };
    }
  }

  console.log('iframe 内部探测:', JSON.stringify(probe, null, 2));
  await host.waitForTimeout(3000);
  if (frame) {
    const again = await frame.evaluate(() => {
      const v = Array.from(document.querySelectorAll('video')).find((x) => x.readyState > 0);
      return v ? Number(v.currentTime.toFixed(2)) : null;
    }).catch(() => null);
    console.log('3 秒后 currentTime:', again, again !== null && again > (probe.t || 0) ? '（在推进 ✓）' : '（没动 ✗）');
  }

  await host.screenshot({ path: 'outputs/host-bilibili.png' });
  await browser.close();
})().catch((e) => { console.error('崩溃:', e.message); process.exit(2); });
