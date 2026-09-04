import { chromium } from '@playwright/test';
const ws = '6e40c172-9977-5186-a015-1aa84d55129f';
const b = await chromium.launch();
const pg = await b.newPage({ viewport: { width: 1440, height: 900 } });
const dump = async (path, label) => {
  await pg.goto('http://localhost:5173' + path, { waitUntil: 'networkidle' });
  await pg.waitForTimeout(1600);
  const info = await pg.evaluate(() => {
    const els = [...document.querySelectorAll('button, a, textarea, input, h1, h2, p')];
    const rows = els.filter(el => {
      const r = el.getBoundingClientRect();
      return r.width > 0 && r.height > 0 && r.top < 100000;
    }).map(el => {
      const r = el.getBoundingClientRect();
      const cls = el.className && typeof el.className === 'string' ? el.className.split(' ').join('.') : '';
      const txt = (el.innerText || el.getAttribute('placeholder') || '').replace(/\s+/g, ' ').trim().slice(0, 70);
      return { y: Math.round(r.top + window.scrollY), h: Math.round(r.height), tag: el.tagName, cls, txt };
    });
    return { vw: innerWidth, vh: innerHeight, bodyH: document.body.scrollHeight, rows };
  });
  console.log(`\n===== ${label} ===== viewport ${info.vw}x${info.vh} body ${info.bodyH}`);
  const sorted = info.rows.filter(r => r.txt || r.tag === 'input').sort((a, b) => a.y - b.y);
  let lastY = -100;
  for (const r of sorted) {
    if (r.y - lastY > 90) console.log('--- y=' + r.y);
    else if (r.y - lastY < 0) console.log('   (above)');
    console.log(`  ${r.tag} ${r.cls} ${r.h}px: ${r.txt}`);
    lastY = r.y;
  }
};
await dump(`/workspaces/${ws}`, 'WORKSPACE');
await dump(`/workspaces/${ws}/dialogue`, 'DIALOGUE');
const colors = await (async () => {
  const pg2 = await b.newPage({ viewport: { width: 1440, height: 900 } });
  await pg2.goto('http://localhost:5173/workspaces/' + ws + '/dialogue', { waitUntil: 'networkidle' });
  return pg2.evaluate(() => {
    const s = getComputedStyle(document.documentElement);
    const out = {};
    for (const k of ['--ink','--paper','--edge','--line','--muted','--teal','--paper-dim','--bg']) out[k] = s.getPropertyValue(k).trim();
    return out;
  });
})();
console.log('\nCSS vars', JSON.stringify(colors));
await b.close();
