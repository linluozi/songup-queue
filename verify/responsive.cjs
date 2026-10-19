/**
 * Responsive + accessibility gate for the two SongStub surfaces.
 *
 *   node verify/responsive.cjs http://127.0.0.1:5066
 *
 * What it actually measures (not "it looks fine"):
 *   1. Horizontal overflow at six widths — documentElement.scrollWidth vs clientWidth.
 *   2. Every interactive control is inside the viewport and at least 24x24 CSS px
 *      (WCAG 2.5.8 target size, minimum level).
 *   3. Contrast ratios computed from the *rendered* computed styles, not from the
 *      palette file — a token can be right while the rule that uses it is wrong.
 *   4. The host page has no external requests except the YouTube API.
 *   5. The guest page has none at all.
 *   6. prefers-reduced-motion is honoured (animation-duration collapses).
 *   7. Screenshots are written for every width so a human can look at them.
 */

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE = process.argv[2] || 'http://127.0.0.1:5066';
const OUT = path.join('docs', 'design', 'shots');
const WIDTHS = [320, 390, 768, 1024, 1366, 1920];

const results = [];
function check(name, pass, detail) {
  results.push({ name, pass, detail });
  console.log(`${pass ? 'PASS' : 'FAIL'}  ${name}${detail ? '  — ' + detail : ''}`);
}

/* --- colour helpers ------------------------------------------------------ */

function parseRgb(str) {
  const m = String(str).match(/rgba?\(([^)]+)\)/);
  if (!m) return null;
  const parts = m[1].split(/[,/\s]+/).filter(Boolean).map(Number);
  if (parts.length >= 4 && parts[3] === 0) return null; // fully transparent
  return { r: parts[0], g: parts[1], b: parts[2], a: parts.length > 3 ? parts[3] : 1 };
}

function lum({ r, g, b }) {
  const f = (v) => {
    const s = v / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
}

function contrast(fg, bg) {
  const a = lum(fg);
  const b = lum(bg);
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}

/* --- page-side probe ----------------------------------------------------- */

/* Runs inside the browser: resolves the effective background by walking up the
   ancestor chain until a non-transparent colour is found. Reading only
   `background-color` on the element itself would report white for every card
   whose parent paints the page. */
const PROBE = () => {
  function bgOf(el) {
    let node = el;
    while (node && node !== document.documentElement) {
      const cs = getComputedStyle(node);
      const c = cs.backgroundColor;
      if (c && !/rgba\(0, 0, 0, 0\)/.test(c) && c !== 'transparent') {
        const m = c.match(/rgba?\(([^)]+)\)/);
        if (m) {
          const p = m[1].split(/[,/\s]+/).filter(Boolean).map(Number);
          if (p.length < 4 || p[3] > 0.5) return c;
        }
      }
      node = node.parentElement;
    }
    return getComputedStyle(document.body).backgroundColor || 'rgb(255,255,255)';
  }

  const out = {
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
    docHeight: document.documentElement.scrollHeight,
    samples: [],
    targets: [],
    overflow: [],
    fonts: {},
    reduced: matchMedia('(prefers-reduced-motion: reduce)').matches,
  };

  // Text samples across every text-bearing surface.
  const selectors = [
    'body', 'h1', 'h2', '.brand .name', '.brand .sub', '.room',
    '.holder .label', '.holder .note', '.uid', '.card-head h2', '.card-head .count',
    '.row .name', '.row .src', '.add', '.none', '.msg', '.playing .t', '.playing .m',
    'ol.q .no', 'ol.q .t', 'ol.q .b', '.foot', '.stub .title', '.stub .by',
    '.stub .serial b', '.panel h2', '.panel h2 .count', 'ol.queue .no', 'ol.queue .qt',
    'ol.queue .qb', 'ol.queue .del', '.stats span', '.join .label', '.join .addr',
    '.join .tip', '.copy', '.hint', 'button', 'kbd', '.host-tag', '.meta .clock',
  ];
  selectors.forEach((sel) => {
    document.querySelectorAll(sel).forEach((el) => {
      const text = (el.textContent || '').trim();
      if (!text) return;
      const cs = getComputedStyle(el);
      if (cs.visibility === 'hidden' || cs.display === 'none') return;
      const rect = el.getBoundingClientRect();
      if (rect.width < 2 || rect.height < 2) return;
      const size = parseFloat(cs.fontSize);
      out.samples.push({
        sel,
        text: text.slice(0, 28),
        fg: cs.color,
        bg: bgOf(el),
        size,
        weight: cs.fontWeight,
        bold: parseInt(cs.fontWeight, 10) >= 700 || size >= 24 || (size >= 18.66 && parseInt(cs.fontWeight, 10) >= 700),
      });
    });
  });

  // Interactive targets.
  document.querySelectorAll('button, a, input, [role="button"]').forEach((el) => {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') return;
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) return;
    out.targets.push({
      tag: el.tagName.toLowerCase(),
      cls: el.className || '',
      id: el.id || '',
      text: (el.textContent || el.getAttribute('aria-label') || '').trim().slice(0, 20),
      w: Math.round(r.width * 10) / 10,
      h: Math.round(r.height * 10) / 10,
      left: Math.round(r.left),
      right: Math.round(r.right),
      top: Math.round(r.top),
    });
  });

  // Any element wider than the viewport.
  const limit = document.documentElement.clientWidth;
  document.querySelectorAll('body *').forEach((el) => {
    const r = el.getBoundingClientRect();
    if (r.width === 0) return;
    if (r.right > limit + 1 || r.left < -1) {
      const cs = getComputedStyle(el);
      if (cs.position === 'fixed' || cs.visibility === 'hidden') return;
      out.overflow.push({
        tag: el.tagName.toLowerCase(),
        cls: String(el.className || '').slice(0, 40),
        left: Math.round(r.left),
        right: Math.round(r.right),
        width: Math.round(r.width),
      });
    }
  });

  const titleEl = document.querySelector('.brand .name');
  out.fonts.title = titleEl ? getComputedStyle(titleEl).fontFamily : '';
  return out;
};

/* --- main ---------------------------------------------------------------- */

(async () => {
  fs.mkdirSync(OUT, { recursive: true });

  const browser = await chromium.launch({
    channel: 'msedge',
    headless: true,
    args: ['--autoplay-policy=no-user-gesture-required', '--no-sandbox'],
  });

  // Seed a queue so both pages render their populated state, not an empty shell.
  const seedCtx = await browser.newContext();
  const seed = await seedCtx.newPage();
  await seed.goto(BASE + '/api/health', { waitUntil: 'domcontentloaded' });
  await seed.evaluate(() => fetch('/api/clear', { method: 'POST' }));
  const picks = [
    [{ id: 'demo-track-1', title: 'DEMO TRACK 1（本地示例 · 8 秒）', kind: 'local', url: '/static/demo-track-1.mp4' },
     { id: 'BV1d4411N7zD', title: '周杰伦 - 晴天（4K 修复 MV）', kind: 'bilibili', url: '' }],
    [{ id: 'BV15S4y1R72L', title: '久石让《天空之城》千人大合唱现场', kind: 'bilibili', url: '' }],
    [{ id: 'demo-track-2', title: 'DEMO TRACK 2（本地示例 · 8 秒）', kind: 'local', url: '/static/demo-track-2.mp4' }],
  ];
  for (const songs of picks) {
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
  await seed.close();
  await seedCtx.close();

  const external = { host: [], guest: [] };
  let contrastFail = 0;
  let contrastTotal = 0;
  let worst = { ratio: 99, where: '' };

  for (const width of WIDTHS) {
    for (const page of ['guest', 'host']) {
      const url = page === 'guest' ? BASE + '/' : BASE + '/host';
      const ctx = await browser.newContext({
        viewport: { width, height: width < 500 ? 780 : 900 },
        deviceScaleFactor: width <= 390 ? 2 : 1,
      });
      const p = await ctx.newPage();

      p.on('request', (req) => {
        const u = req.url();
        if (u.startsWith(BASE) || u.startsWith('data:') || u.startsWith('blob:')) return;
        external[page].push(u);
      });
      const errors = [];
      p.on('pageerror', (e) => errors.push(e.message));

      await p.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
      await p.waitForTimeout(page === 'host' ? 1800 : 900);

      const probe = await p.evaluate(PROBE);

      // 1. no horizontal overflow
      check(`${width}px ${page}: 无横向溢出`, probe.scrollWidth <= probe.clientWidth + 1,
        `scrollWidth=${probe.scrollWidth} clientWidth=${probe.clientWidth}`);
      if (probe.overflow.length) {
        const worstEl = probe.overflow.sort((a, b) => b.right - a.right)[0];
        check(`${width}px ${page}: 无元素越出视口`, false,
          `${probe.overflow.length} 个元素越界，最远 ${worstEl.tag}.${worstEl.cls} right=${worstEl.right}`);
      } else {
        check(`${width}px ${page}: 无元素越出视口`, true);
      }

      // 2. target size + in-viewport
      const small = probe.targets.filter((t) => t.w < 24 || t.h < 24);
      check(`${width}px ${page}: 交互目标 ≥24px`, small.length === 0,
        small.length ? small.map((t) => `${t.tag}.${t.cls}[${t.w}x${t.h}]`).slice(0, 3).join(' ') : `${probe.targets.length} 个目标`);

      const outside = probe.targets.filter((t) => t.left < -1 || t.right > width + 1);
      check(`${width}px ${page}: 交互目标在视口内`, outside.length === 0,
        outside.length ? outside.map((t) => `${t.tag}.${t.cls} L${t.left} R${t.right}`).slice(0, 3).join(' ') : '');

      // 3. contrast from computed styles
      probe.samples.forEach((s) => {
        const fg = parseRgb(s.fg);
        const bg = parseRgb(s.bg);
        if (!fg || !bg) return;
        contrastTotal += 1;
        const ratio = contrast(fg, bg);
        const need = s.bold ? 3.0 : 4.5;
        if (ratio < worst.ratio) worst = { ratio, where: `${width}px ${page} ${s.sel} "${s.text}"` };
        if (ratio < need) {
          contrastFail += 1;
          console.log(`      contrast ${ratio.toFixed(2)} < ${need}  ${page} ${s.sel} "${s.text}" fg=${s.fg} bg=${s.bg} ${s.size}px`);
        }
      });

      // 4. no JS errors
      check(`${width}px ${page}: 无 JS 异常`, errors.length === 0, errors.slice(0, 2).join(' | '));

      await p.screenshot({
        path: path.join(OUT, `${page}-${width}.png`),
        fullPage: page === 'guest',
      });

      await ctx.close();
    }
  }

  check('对比度（全部文本样本）', contrastFail === 0,
    `${contrastTotal} 个样本，最差 ${worst.ratio.toFixed(2)}:1 @ ${worst.where}`);

  // 5. external requests
  const guestExternal = [...new Set(external.guest)];
  check('客人页零外部请求', guestExternal.length === 0,
    guestExternal.slice(0, 3).join(' ') || `${external.guest.length} 次请求，全部同源`);

  const hostExternal = [...new Set(external.host)].filter((u) => !/youtube\.com|ytimg\.com|googleapis/.test(u));
  check('主机页除 YouTube API 外无外部请求', hostExternal.length === 0,
    hostExternal.slice(0, 3).join(' ') || '仅同源 + youtube');

  // 6. reduced motion
  {
    const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 }, reducedMotion: 'reduce' });
    const p = await ctx.newPage();
    await p.goto(BASE + '/host', { waitUntil: 'networkidle' });
    const motion = await p.evaluate(() => {
      const el = document.querySelector('.stub');
      if (!el) return { reduced: false, transform: 'missing', anim: 'missing' };
      const cs = getComputedStyle(el);
      return {
        reduced: matchMedia('(prefers-reduced-motion: reduce)').matches,
        transform: cs.transform,
        anim: cs.animationDuration,
      };
    });
    check('prefers-reduced-motion 生效（票根不再旋转）',
      motion.reduced && (motion.transform === 'none' || motion.transform === 'matrix(1, 0, 0, 1, 0, 0)'),
      `transform=${motion.transform}`);
    await ctx.close();
  }

  // 7. host page: QR must be present and scannable-sized
  {
    const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
    const p = await ctx.newPage();
    await p.goto(BASE + '/host', { waitUntil: 'networkidle' });
    const qr = await p.evaluate(() => {
      const box = document.getElementById('qrBox');
      const svg = box && box.querySelector('svg');
      const rect = svg ? svg.getBoundingClientRect() : null;
      return {
        has: !!svg,
        modules: svg ? svg.querySelectorAll('rect').length : 0,
        w: rect ? Math.round(rect.width) : 0,
        addr: (document.getElementById('joinAddr') || {}).textContent || '',
      };
    });
    check('主机页渲染了二维码', qr.has && qr.modules > 100, `${qr.modules} 个模块，显示 ${qr.w}px`);
    check('二维码尺寸可扫（≥88px）', qr.w >= 88, `${qr.w}px`);
    check('入场地址是完整 URL', /^http:\/\/\d+\.\d+\.\d+\.\d+:\d+$/.test(qr.addr.trim()), qr.addr.trim());
    await ctx.close();
  }

  await browser.close();

  const failed = results.filter((r) => !r.pass);
  console.log('\n' + '='.repeat(56));
  console.log(`${results.length - failed.length}/${results.length} 项通过`);
  if (failed.length) {
    console.log('失败项：');
    failed.forEach((f) => console.log('  - ' + f.name + (f.detail ? '  — ' + f.detail : '')));
  }
  process.exit(failed.length ? 1 : 0);
})().catch((e) => {
  console.error('适配测试崩溃:', e.stack || e.message);
  process.exit(2);
});
