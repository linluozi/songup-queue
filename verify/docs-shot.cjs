/**
 * The screenshots that ship in the README.
 *
 *   node verify/docs-shot.cjs http://127.0.0.1:5066
 *
 * Rules this script follows, because a screenshot is a claim:
 *   - Only the repo's own ffmpeg-generated demo clip is ever on the stage.
 *     No third-party MV frame goes into a public repo.
 *   - The queue is seeded through the real API, so what you see is what the
 *     engine actually produced, not a hand-written fixture.
 *   - Guest shots run on a freshly cleared queue, so "2 of 2 tickets used" is
 *     really 2 of 2 and not a leftover from a previous section.
 *   - Every shot is taken twice; the second frame is kept. Video paints and
 *     CSS transitions land late, and the first frame is routinely the old screen.
 */

const { chromium } = require('playwright');

const BASE = process.argv[2] || 'http://127.0.0.1:5066';
const OUT = 'docs';

const S1 = { id: 'demo-track-1', title: 'DEMO TRACK 1（本地示例 · 8 秒）', kind: 'local', url: '/static/demo-track-1.mp4' };
const S2 = { id: 'demo-track-2', title: 'DEMO TRACK 2（本地示例 · 8 秒）', kind: 'local', url: '/static/demo-track-2.mp4' };
const B1 = { id: 'BV1d4411N7zD', title: '周杰伦 - 晴天（4K 修复 MV）', kind: 'bilibili', url: '' };
const B2 = { id: 'BV15S4y1R72L', title: '久石让《天空之城》千人大合唱现场', kind: 'bilibili', url: '' };

async function shoot(page, path, opts) {
  await page.screenshot(Object.assign({ path }, opts || {}));
  await page.waitForTimeout(160);
  await page.screenshot(Object.assign({ path }, opts || {}));
}

async function reset(ctx) {
  const p = await ctx.newPage();
  await p.goto(BASE + '/api/health', { waitUntil: 'domcontentloaded' });
  await p.evaluate(() => fetch('/api/clear', { method: 'POST' }));
  await p.close();
}

/** Add songs as a distinct guest (its own session cookie). */
async function addAsGuest(browser, songs) {
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

(async () => {
  const browser = await chromium.launch({
    channel: 'msedge',
    headless: true,
    args: ['--autoplay-policy=no-user-gesture-required', '--no-sandbox'],
  });

  /* ============ guest ============ */
  const guestCtx = await browser.newContext({ viewport: { width: 400, height: 880 }, deviceScaleFactor: 2 });
  await reset(guestCtx);

  // Someone else is already queued, so "正在播放" and "排队中" are populated.
  await addAsGuest(browser, [B1, B2]);

  const guest = await guestCtx.newPage();
  await guest.goto(BASE + '/', { waitUntil: 'networkidle', timeout: 30000 });
  await guest.waitForSelector('.row', { timeout: 10000 });

  // One ticket spent: 1 solid slot, 1 dashed.
  await guest.locator('.row .add').first().click();
  await guest.waitForTimeout(1600);
  await shoot(guest, OUT + '/screenshot-guest.png', { fullPage: true });

  // Second ticket spent: quota exhausted, buttons greyed.
  await guest.locator('.row .add').nth(1).click();
  await guest.waitForTimeout(1800);
  const quota = await guest.evaluate(() => ({
    note: document.getElementById('me').innerText,
    used: document.querySelectorAll('.slot.used').length,
    disabled: [...document.querySelectorAll('.add')].every((b) => b.disabled),
  }));
  if (!/名额用完/.test(quota.note) || quota.used !== 2 || !quota.disabled) {
    throw new Error('配额状态不对，拒绝出图: ' + JSON.stringify(quota));
  }
  await shoot(guest, OUT + '/screenshot-guest-quota.png', { fullPage: true });

  /* ============ host ============ */
  const hostCtx = await browser.newContext({ viewport: { width: 1440, height: 810 } });
  await reset(hostCtx);

  const host = await hostCtx.newPage();
  // Four songs across two guests, so the queue shows a real mix of sources.
  await addAsGuest(browser, [S1, B1]);
  await addAsGuest(browser, [B2, S2]);

  await host.goto(BASE + '/host', { waitUntil: 'networkidle', timeout: 30000 });
  await host.locator('#btnNext').click();
  await host.waitForSelector('#stage video', { timeout: 12000 });
  await host.waitForTimeout(3600);          // ~3s into the 8s clip
  await shoot(host, OUT + '/screenshot-host.png');

  // Second angle: replay the local clip with three songs still waiting.
  // (Auto-advancing into a B站 iframe gives a black stage in a headless
  // browser, which would ship as a broken screenshot.)
  await reset(hostCtx);
  await addAsGuest(browser, [S2, B1]);
  await addAsGuest(browser, [B2, S1]);
  await host.locator('#btnNext').click();
  await host.waitForTimeout(2600);
  await shoot(host, OUT + '/screenshot-host-queue.png');

  /* ============ narrow phone ============ */
  const narrowCtx = await browser.newContext({ viewport: { width: 320, height: 720 }, deviceScaleFactor: 2 });
  const narrow = await narrowCtx.newPage();
  await narrow.goto(BASE + '/', { waitUntil: 'networkidle', timeout: 30000 });
  await narrow.waitForSelector('.row', { timeout: 10000 });
  await narrow.waitForTimeout(1000);
  await shoot(narrow, OUT + '/screenshot-guest-320.png', { fullPage: true });

  console.log('截图完成：host / host-queue / guest / guest-quota / guest-320');
  await browser.close();
})().catch((e) => { console.error('截图崩溃:', e.stack || e.message); process.exit(2); });
