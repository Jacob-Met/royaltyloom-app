/* Split studio for Royalty Loom: calm palette, split wheel, corrections in words, credits intake, works home.
   Loaded after the main page script. It only reads and writes the existing #people rows, so every old id keeps working. */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const el = (tag, props = {}, ...kids) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) {
      if (k === 'class') n.className = v; else if (k === 'text') n.textContent = v;
      else if (k === 'style') n.style.cssText = v; else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
      else if (v !== false && v != null) n.setAttribute(k, v === true ? '' : v);
    }
    for (const kid of kids.flat()) if (kid != null) n.append(kid);
    return n;
  };
  const NS = 'http://www.w3.org/2000/svg';
  const sv = (tag, attrs = {}) => { const n = document.createElementNS(NS, tag); for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v); return n; };

  /* ---------- 1. One calm palette; each collaborator keeps one colour everywhere ---------- */
  const CSS = `
:root[data-theme="light"]{--bg:#f6f7f9;--panel:#ffffff;--panel2:#eef1f5;--ink:#1b2433;--muted:#566174;--line:#d3d9e2;--accent:#2a62c9;--green:#12704f;--red:#b3261e;
 --c0:#2a62c9;--c1:#b4560f;--c2:#0f766e;--c3:#a63a7c;--c4:#6a4fc2;--c5:#4d7c0f;--cink:#ffffff;
 --ok-bg:#e3f4ec;--ok-ink:#0d5a3f;--wait-bg:#fdf0d8;--wait-ink:#7a4a05;--no-bg:#fbe5e3;--no-ink:#8f1d16}
:root[data-theme="dark"]{--bg:#12151c;--panel:#1b2029;--panel2:#242b37;--ink:#eef1f6;--muted:#aab3c3;--line:#364050;--accent:#7ba7ff;--green:#6fd0a0;--red:#ff9d94;
 --c0:#7ba7ff;--c1:#f0a05a;--c2:#4fd1c1;--c3:#f08ec3;--c4:#b6a4ff;--c5:#a6d36b;--cink:#10131a;
 --ok-bg:#16382b;--ok-ink:#a5ecc8;--wait-bg:#3d3015;--wait-ink:#f7d794;--no-bg:#432120;--no-ink:#ffc3bd}
body,.surface,.workspace{background:var(--bg);color:var(--ink)}
.surface,.person,dialog,.local-ai-panel,.preflight{background:var(--panel)!important;color:var(--ink);border-color:var(--line)!important}
.app-rail{background:var(--panel)!important;color:var(--ink)!important;border-color:var(--line)!important}
.app-rail .brand,.app-rail .rail-project strong{color:var(--ink)!important}
.app-rail .rail-project span,.app-rail .environment{color:var(--muted)!important}
.workspace-nav button{color:var(--muted)!important}
.workspace-nav button[aria-current=page]{color:var(--accent)!important;background:color-mix(in srgb,var(--accent) 14%,transparent)!important}
.workspace-nav{background:var(--panel)!important;border-color:var(--line)!important}
input,textarea,select{background:var(--panel2)!important;color:var(--ink)!important;border-color:var(--line)!important}
input::file-selector-button{background:var(--panel2)!important;border:1px solid var(--line)!important;color:var(--ink)!important}
.btn{border-color:var(--line);color:var(--ink);background:var(--panel2)}
.btn.primary{background:var(--accent)!important;color:var(--cink)!important;border-color:transparent!important}
.weave-end,.weave-source{border-left-color:var(--who,var(--line))!important}
.weave-end{background:var(--panel2)!important;color:var(--ink)!important}
.weave-svg path,.weave-svg line{stroke:var(--who,var(--muted))}
.weave-payment-status.success{color:var(--ok-ink)!important}.weave-payment-status.pending{color:var(--wait-ink)!important}.weave-payment-status.failed{color:var(--no-ink)!important}
.person[style*="--who"]{border-left:5px solid var(--who)!important}
.person-header strong::before{content:"";display:inline-block;width:12px;height:12px;border-radius:50%;background:var(--who,var(--line));margin-right:8px;vertical-align:-1px}
.statement-summary,.statement-summary *{background:var(--panel2)!important;color:var(--ink)!important}.statement-summary{border:1px solid var(--line)}.hero{background:var(--panel2)!important;color:var(--ink)!important;border:1px solid var(--line)}.hero *{color:var(--ink)!important}
#workspaceTitle,.workspace h1,.allocation-heading .text-button,.text-button{color:var(--ink)!important}.text-button{color:var(--accent)!important}
.weave-source{border-left-color:var(--muted)!important}
.weave-svg path{fill-opacity:.35!important;stroke-width:1.5!important}
.who0{--who:var(--c0)}.who1{--who:var(--c1)}.who2{--who:var(--c2)}.who3{--who:var(--c3)}.who4{--who:var(--c4)}.who5{--who:var(--c5)}

#splitStudio,#splitIntake,#view-works .works-wrap{border:1px solid var(--line);background:var(--panel);border-radius:22px;padding:22px;margin:0 0 20px}
.studio-h{display:flex;flex-wrap:wrap;gap:10px 16px;align-items:end;justify-content:space-between;margin-bottom:14px}
.studio-h h2{margin:0;font-size:20px}.studio-h p{margin:2px 0 0;color:var(--muted);font-size:14px}
.studio-amt{display:flex;align-items:center;gap:8px;font-size:13px;color:var(--muted)}
.studio-amt input{width:112px;min-height:44px;border-radius:14px;border:1px solid var(--line);padding:0 12px;font-size:16px;text-align:right}
.studio-grid{display:grid;grid-template-columns:minmax(0,300px) minmax(0,1fr);gap:22px;align-items:center}
@media(max-width:760px){.studio-grid{grid-template-columns:1fr}#splitStudio,#splitIntake{padding:16px;border-radius:20px}}
.wheel-box{position:relative;max-width:320px;width:100%;margin:0 auto;touch-action:none}
.wheel-box svg{width:100%;height:auto;display:block;overflow:visible}
.wheel-seg{fill:var(--who);stroke:var(--panel);stroke-width:2}
.wheel-av circle{fill:var(--panel);stroke:var(--who);stroke-width:3}
.wheel-av text{fill:var(--ink);font:700 9px system-ui,sans-serif;text-anchor:middle;dominant-baseline:central;pointer-events:none}
.wheel-handle{fill:var(--panel);stroke:var(--ink);stroke-width:2.5;cursor:grab}
.wheel-handle:focus-visible{outline:3px solid var(--accent);outline-offset:2px}
.wheel-mid{fill:var(--ink);text-anchor:middle;font-family:system-ui,sans-serif}
.studio-bar{position:relative;display:flex;height:44px;border-radius:14px;margin:18px 0 6px;touch-action:none;user-select:none}
.studio-bar>i{display:block;background:var(--who);height:100%;min-width:0}
.studio-bar>i:first-of-type{border-radius:14px 0 0 14px}.studio-bar>i:last-of-type{border-radius:0 14px 14px 0}
.bar-handle{position:absolute;top:-6px;width:30px;height:56px;margin-left:-15px;border:0;background:transparent;cursor:ew-resize;padding:0}
.bar-handle::after{content:"";position:absolute;left:11px;top:6px;width:8px;height:44px;border-radius:5px;background:var(--panel);border:2px solid var(--ink)}
.bar-handle:focus-visible::after{outline:3px solid var(--accent)}
.cards{display:grid;gap:10px}
.card{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:2px 12px;align-items:center;border:1px solid var(--line);border-left:6px solid var(--who);border-radius:18px;padding:10px 12px;background:var(--panel2)}
.avatar{grid-row:span 2;width:44px;height:44px;border-radius:50%;background:var(--who);color:var(--cink);display:grid;place-items:center;font-weight:700;font-size:15px}
.card b{font-size:16px;overflow-wrap:anywhere}.card small{color:var(--muted)}
.card .pct{font-size:22px;font-weight:700;text-align:right;font-variant-numeric:tabular-nums}.card .amt{font-size:14px;color:var(--muted);text-align:right;font-variant-numeric:tabular-nums}
.nudge{display:flex;gap:6px;grid-column:1/-1;justify-content:flex-end}
.nudge button{min-width:44px;min-height:44px;border-radius:14px;border:1px solid var(--line);background:var(--panel);color:var(--ink);font-size:18px}
.total-pill{display:inline-flex;gap:6px;align-items:center;border-radius:999px;padding:6px 12px;font-weight:700;font-size:14px;background:var(--ok-bg);color:var(--ok-ink)}
.total-pill.bad{background:var(--no-bg);color:var(--no-ink)}
.say{display:flex;gap:8px;flex-wrap:wrap;margin-top:16px}
.say input{flex:1 1 220px;min-height:48px;border-radius:16px;border:1px solid var(--line);padding:0 14px;font-size:16px}
.say button,.big-btn{min-height:48px;border-radius:16px;border:1px solid var(--line);background:var(--panel2);color:var(--ink);padding:0 16px;font-weight:600;font-size:15px}
.say .go,.big-btn.primary{background:var(--accent);color:var(--cink);border-color:transparent}
.say .mic[aria-pressed=true]{background:var(--no-bg);color:var(--no-ink)}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px;font-size:14px}
.chip{border-radius:999px;padding:6px 12px;background:var(--ok-bg);color:var(--ok-ink)}.chip.warn{background:var(--wait-bg);color:var(--wait-ink)}
.hintline{color:var(--muted);font-size:13px;margin:8px 0 0}
#splitIntake textarea{width:100%;min-height:120px;border-radius:16px;padding:12px;font-size:16px;border:1px solid var(--line)}
.intake-row{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
.doc{white-space:pre-wrap;font:15px/1.8 ui-monospace,Menlo,monospace;background:var(--panel2);border:1px solid var(--line);border-radius:16px;padding:14px;margin:14px 0;overflow-wrap:anywhere}
.doc mark{background:color-mix(in srgb,var(--who) 30%,transparent);color:var(--ink);border-bottom:3px solid var(--who);border-radius:4px;padding:1px 2px}
.doc mark.on{background:color-mix(in srgb,var(--who) 60%,transparent)}
.prop{cursor:pointer}.prop .q{grid-column:1/-1;font-size:13px;color:var(--muted);font-style:italic;overflow-wrap:anywhere}
.thumb{max-width:100%;max-height:160px;border-radius:14px;margin-top:10px}
#view-works .works-wrap{padding:16px}
.filters{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 14px}
.filters button{min-height:44px;border-radius:999px;border:1px solid var(--line);background:var(--panel2);color:var(--ink);padding:0 16px;font-weight:600}
.filters button[aria-pressed=true]{background:var(--accent);color:var(--cink);border-color:transparent}
.work{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:6px 14px;align-items:center;width:100%;text-align:left;border:1px solid var(--line);border-radius:18px;background:var(--panel2);color:var(--ink);padding:14px;margin-bottom:10px;min-height:72px}
.work b{font-size:17px}.work small{color:var(--muted)}.work .money{font-weight:700;text-align:right;font-variant-numeric:tabular-nums}
.work .minibar{grid-column:1/-1;display:flex;height:8px;border-radius:5px;overflow:hidden}.work .minibar i{background:var(--who)}
.mark{display:inline-flex;gap:6px;align-items:center;border-radius:999px;padding:5px 12px;font-weight:700;font-size:13px;white-space:nowrap}
.mark.paid{background:var(--ok-bg);color:var(--ok-ink)}.mark.pending{background:var(--wait-bg);color:var(--wait-ink)}.mark.unagreed{background:var(--no-bg);color:var(--no-ink)}
.sr{position:absolute;left:-9999px}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}}
`;
  document.head.append(el('style', { id: 'calmStyle', text: CSS }));

  const palette = (() => {
    let map = {};
    try { map = JSON.parse(localStorage.getItem('rl-who') || '{}'); } catch (e) { /* storage may be unavailable */ }
    return key => {
      key = key.trim().toLowerCase();
      if (!(key in map)) {
        const used = new Set(Object.values(map));
        let i = 0; while (used.has(i) && i < 5) i++;
        map[key] = i < 6 && !used.has(i) ? i : Object.keys(map).length % 6;
        try { localStorage.setItem('rl-who', JSON.stringify(map)); } catch (e) { /* ignore */ }
      }
      return map[key];
    };
  })();
  const initials = n => n.trim().split(/\s+/).map(w => w[0]).slice(0, 2).join('').toUpperCase() || '?';
  const fmtPct = bps => String(+(bps / 100).toFixed(2));
  const usd = cents => '$' + (cents / 100).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  function allocate(total, bps) {
    const raw = bps.map(b => total * b / 10000), out = raw.map(Math.floor);
    raw.map((r, i) => [r - out[i], i]).sort((a, b) => b[0] - a[0]).slice(0, total - out.reduce((a, b) => a + b, 0)).forEach(([, i]) => out[i]++);
    return out;
  }

  /* ---------- 2. Read and write the existing #people rows ---------- */
  function rows() { return [...$('people').querySelectorAll('.person')]; }
  function read() {
    const rs = rows(), n = rs.length;
    const people = rs.map(row => {
      const g = r => row.querySelector('[data-role="' + r + '"]');
      const share = g('share').value.trim().toLowerCase();
      const v = share === 'equal' ? 100 / n : parseFloat(share);
      return { row, name: g('name').value.trim() || 'Unnamed', role: row.dataset.role || '', evidence: g('evidence').value, bps: Number.isFinite(v) ? Math.round(v * 100) : 0 };
    });
    const sum = people.reduce((a, p) => a + p.bps, 0);
    if (people.length && sum !== 10000 && sum > 0 && people.every(p => p.row.querySelector('[data-role=share]').value.trim().toLowerCase() === 'equal')) {
      const e = to10000(people.map(() => 1)); people.forEach((p, i) => p.bps = e[i]);
    }
    return people;
  }
  function to10000(w) {
    const t = w.reduce((a, b) => a + b, 0), raw = w.map(x => x / t * 10000), out = raw.map(Math.floor);
    raw.map((r, i) => [r - out[i], i]).sort((a, b) => b[0] - a[0]).slice(0, 10000 - out.reduce((a, b) => a + b, 0)).forEach(([, i]) => out[i]++);
    return out;
  }
  function writeShares(bps, fire) {
    rows().forEach((row, i) => {
      const input = row.querySelector('[data-role="share"]');
      input.value = fmtPct(bps[i]);
      if (fire) input.dispatchEvent(new Event('input', { bubbles: true }));
    });
  }
  const setVal = (input, v) => { input.value = v; input.dispatchEvent(new Event('input', { bubbles: true })); };

  /* Keep the agreement text in step with the agreed split, so each person's quote says what the screen says. */
  function syncAgreement(force) {
    const people = read();
    if (!people.length) return;
    const ag = $('agreement'), current = ag.value;
    const ok = people.every(p => p.evidence && current.includes(p.evidence) && new RegExp('(^|[^\\d.])' + fmtPct(p.bps).replace('.', '\\.') + '\\s*%').test(p.evidence));
    if (ok && !force) return;
    if (!ag.dataset.original) ag.dataset.original = current;
    const lines = people.map(p => p.name + ' receives ' + fmtPct(p.bps) + '% of net receipts.');
    const kept = current.split('\n').map(l => l.trim()).filter(l => l && !/%/.test(l) && !people.some(p => l.includes(p.name)));
    const head = kept.length ? kept[0] : ($('project').value.trim() || 'Royalty split') + ' royalty agreement.';
    setVal(ag, [head, '', ...lines, '', ...kept.slice(1)].join('\n').trim());
    people.forEach((p, i) => setVal(p.row.querySelector('[data-role="evidence"]'), lines[i]));
    note('Agreement text now reads the agreed split.' + (ag.dataset.original && ag.dataset.original !== current ? '' : ''));
  }

  /* ---------- 3. The studio: wheel, bar, cards, words ---------- */
  const studio = el('section', { id: 'splitStudio', 'aria-label': 'Split studio' });
  const wheelBox = el('div', { class: 'wheel-box' });
  const bar = el('div', { class: 'studio-bar', id: 'studioBar' });
  const cards = el('div', { class: 'cards', id: 'studioCards' });
  const totalPill = el('span', { class: 'total-pill', id: 'studioTotal', role: 'status' });
  const amtInput = el('input', { id: 'studioAmount', type: 'text', inputmode: 'decimal', value: '1,000.00', 'aria-label': 'Sample payout in dollars' });
  const sayInput = el('input', { id: 'studioSay', type: 'text', placeholder: 'e.g. give the producer two more points from the writer', 'aria-label': 'Describe a change in words', autocomplete: 'off' });
  const chips = el('div', { class: 'chips', id: 'studioChips', 'aria-live': 'polite' });
  const micBtn = el('button', { type: 'button', class: 'mic', id: 'studioMic', 'aria-pressed': 'false', 'aria-label': 'Speak a change' }, '🎤 Speak');
  const undoBtn = el('button', { type: 'button', id: 'studioUndo', hidden: true }, 'Undo');
  studio.append(
    el('div', { class: 'studio-h' },
      el('div', {}, el('h2', { text: 'Who gets what' }), el('p', { text: 'Drag a handle on the wheel or the bar. Everything always adds up to 100%.' })),
      el('label', { class: 'studio-amt' }, 'Sample payout $', amtInput)),
    el('div', { class: 'studio-grid' }, el('div', {}, wheelBox), el('div', {}, totalPill, bar, cards)),
    el('div', { class: 'say' }, sayInput,
      el('button', { type: 'button', class: 'go', id: 'studioApply' }, 'Apply'), micBtn,
      el('button', { type: 'button', id: 'studioEven' }, 'Split evenly'), undoBtn),
    chips,
    el('p', { class: 'hintline', text: 'Try: “give the producer two more points from the writer”, “split the rest evenly”, “set Rae to 25%”.' }));

  let hist = [];
  function snapshot() { hist.push({ bps: read().map(p => p.bps), agreement: $('agreement').value }); if (hist.length > 20) hist.shift(); undoBtn.hidden = false; }
  function note(msg, warn) { chips.append(el('span', { class: 'chip' + (warn ? ' warn' : ''), text: msg })); while (chips.children.length > 4) chips.firstChild.remove(); }

  let live = null; // bps being dragged
  function draw(bps) {
    const ppl = read(); if (!ppl.length) { studio.hidden = true; return; } studio.hidden = false;
    bps = bps || ppl.map(p => p.bps);
    const n = ppl.length, sum = bps.reduce((a, b) => a + b, 0);
    const sample = Math.round((parseFloat(amtInput.value.replace(/,/g, '')) || 0) * 100), money = allocate(sample, bps);
    totalPill.className = 'total-pill' + (sum === 10000 ? '' : ' bad');
    totalPill.textContent = sum === 10000 ? '✓ 100% allocated' : '⚠ ' + fmtPct(sum) + '% allocated (needs 100%)';
    // wheel
    const cx = 110, cy = 110, R = 98, r = 60, rm = (R + r) / 2, svg = sv('svg', { viewBox: '0 0 220 220', role: 'group', 'aria-label': 'Split wheel' });
    const pt = (rad, pct) => { const a = pct / 100 * 2 * Math.PI; return [cx + rad * Math.sin(a), cy - rad * Math.cos(a)]; };
    let c = 0; const cum = [];
    ppl.forEach((p, i) => {
      const a = c / 100, b = (c + bps[i] / 100) / 100; cum.push(c + bps[i] / 100);
      const k = 'who' + palette(p.name) % 6; p.cls = k;
      const g = sv('g', { class: k });
      if (bps[i] >= 9999) { g.append(sv('circle', { cx, cy, r: rm, fill: 'none', stroke: 'var(--who)', 'stroke-width': R - r })); }
      else if (bps[i] > 0) {
        const [x0, y0] = pt(R, a * 100), [x1, y1] = pt(R, b * 100), [x2, y2] = pt(r, b * 100), [x3, y3] = pt(r, a * 100), big = bps[i] > 5000 ? 1 : 0;
        g.append(sv('path', { class: 'wheel-seg', d: `M${x0} ${y0}A${R} ${R} 0 ${big} 1 ${x1} ${y1}L${x2} ${y2}A${r} ${r} 0 ${big} 0 ${x3} ${y3}Z` }));
        if (bps[i] >= 600) { const [mx, my] = pt(rm, (a + b) / 2 * 100), av = sv('g', { class: 'wheel-av' }); av.append(sv('circle', { cx: mx, cy: my, r: 13 })); const t = sv('text', { x: mx, y: my }); t.textContent = initials(p.name); av.append(t); g.append(av); }
      }
      svg.append(g);
    });
    const mid = sv('text', { class: 'wheel-mid', x: cx, y: cy - 2, 'font-size': 20, 'font-weight': 700 }); mid.textContent = usd(sample).replace(/\.00$/, '');
    const mid2 = sv('text', { class: 'wheel-mid', x: cx, y: cy + 16, 'font-size': 10, fill: 'var(--muted)' }); mid2.textContent = 'sample payout'; mid2.style.fill = 'var(--muted)';
    svg.append(mid, mid2);
    for (let i = 0; i < n - 1; i++) {
      const [hx, hy] = pt(rm, cum[i]), h = sv('circle', { class: 'wheel-handle', cx: hx, cy: hy, r: 9, tabindex: 0, role: 'slider', 'aria-label': 'Boundary between ' + ppl[i].name + ' and ' + ppl[i + 1].name, 'aria-valuemin': 0, 'aria-valuemax': 100, 'aria-valuenow': cum[i].toFixed(2) });
      h.dataset.i = i; svg.append(h);
    }
    wheelBox.replaceChildren(svg);
    // bar
    bar.replaceChildren(...ppl.map((p, i) => el('i', { class: p.cls, style: 'width:' + bps[i] / 100 + '%', title: p.name + ' ' + fmtPct(bps[i]) + '%' })));
    for (let i = 0; i < n - 1; i++) bar.append(el('button', { type: 'button', class: 'bar-handle', 'data-i': i, style: 'left:' + cum[i] + '%', 'aria-label': 'Boundary between ' + ppl[i].name + ' and ' + ppl[i + 1].name }));
    // cards
    cards.replaceChildren(...ppl.map((p, i) => el('div', { class: 'card ' + p.cls },
      el('div', { class: 'avatar', text: initials(p.name), 'aria-hidden': 'true' }),
      el('b', { text: p.name }), el('span', { class: 'pct', text: fmtPct(bps[i]) + '%' }),
      el('small', { text: roleOf(p) }), el('span', { class: 'amt', text: usd(money[i]) }),
      el('div', { class: 'nudge' },
        el('button', { type: 'button', 'aria-label': 'One point less for ' + p.name, 'data-n': i, 'data-d': -1, text: '−1' }),
        el('button', { type: 'button', 'aria-label': 'One point more for ' + p.name, 'data-n': i, 'data-d': 1, text: '+1' })))));
    // old rows get the same colour
    ppl.forEach(p => { p.row.classList.remove('who0', 'who1', 'who2', 'who3', 'who4', 'who5'); p.row.classList.add(p.cls); p.row.style.setProperty('--who', 'var(--c' + palette(p.name) % 6 + ')'); });
  }
  function roleOf(p) {
    const m = ((p.role || '') + ' ' + (p.evidence || '')).toLowerCase(), r = [];
    if (/wrote|writ|compos|lyric/.test(m)) r.push('writer'); if (/produc|engineer/.test(m)) r.push('producer'); if (/mix/.test(m)) r.push('mixer');
    if (/perform|vocal|sing/.test(m)) r.push('performer'); if (/cover|art|design|illustr|video/.test(m)) r.push('artwork');
    return r.join(' · ') || 'collaborator';
  }

  // dragging
  let drag = null;
  function startDrag(i, kind, e) {
    e.preventDefault(); snapshot();
    const bps = read().map(p => p.bps); const cum = []; bps.reduce((a, b, k) => (cum[k] = a + b, a + b), 0);
    drag = { i, kind, bps, cum };
    try { e.target.setPointerCapture(e.pointerId); } catch (x) { /* ok */ }
  }
  function moveDrag(e) {
    if (!drag) return;
    let f;
    if (drag.kind === 'wheel') { const r = wheelBox.querySelector('svg').getBoundingClientRect(), a = Math.atan2(e.clientX - (r.left + r.width / 2), -(e.clientY - (r.top + r.height / 2))); f = ((a / (2 * Math.PI)) + 1) % 1; }
    else { const r = bar.getBoundingClientRect(); f = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)); }
    setBoundary(drag, Math.round(f * 100) * 100);
  }
  function setBoundary(d, target) {
    const i = d.i, lo = i === 0 ? 0 : d.cum[i - 1], hi = d.cum[i + 1] ?? 10000;
    const c = Math.min(hi, Math.max(lo, target));
    const next = d.bps.slice(); next[i] = c - lo; next[i + 1] = hi - c;
    live = next; draw(next);
    if (d.kind === 'wheel') { const h = wheelBox.querySelector('[data-i="' + i + '"]'); if (h) h.focus({ preventScroll: true }); }
  }
  function endDrag() { if (!drag) return; drag = null; commit(live); live = null; }
  function commit(bps) {
    if (!bps) return;
    writeShares(bps, true); syncAgreement(true); draw();
  }
  wheelBox.addEventListener('pointerdown', e => { const h = e.target.closest('.wheel-handle'); if (h) startDrag(+h.dataset.i, 'wheel', e); });
  bar.addEventListener('pointerdown', e => { const h = e.target.closest('.bar-handle'); if (h) startDrag(+h.dataset.i, 'bar', e); });
  addEventListener('pointermove', moveDrag); addEventListener('pointerup', endDrag); addEventListener('pointercancel', endDrag);
  function keys(e) {
    const h = e.target.closest('.wheel-handle,.bar-handle'); if (!h || !/^Arrow/.test(e.key)) return;
    e.preventDefault(); const d = (e.key === 'ArrowRight' || e.key === 'ArrowUp') ? 100 : -100, i = +h.dataset.i;
    snapshot(); const bps = read().map(p => p.bps), cum = []; bps.reduce((a, b, k) => (cum[k] = a + b, a + b), 0);
    const dd = { i, kind: h.classList.contains('bar-handle') ? 'bar' : 'wheel', bps, cum }; setBoundary(dd, cum[i] + d); commit(live); live = null;
    const again = studio.querySelector((dd.kind === 'wheel' ? '.wheel-handle' : '.bar-handle') + '[data-i="' + i + '"]'); if (again) again.focus();
  }
  wheelBox.addEventListener('keydown', keys); bar.addEventListener('keydown', keys);
  cards.addEventListener('click', e => {
    const b = e.target.closest('button[data-n]'); if (!b) return;
    const i = +b.dataset.n, d = +b.dataset.d * 100, bps = read().map(p => p.bps), j = (i + 1) % bps.length;
    if (bps.length < 2 || bps[i] + d < 0 || bps[j] - d < 0) return;
    snapshot(); bps[i] += d; bps[j] -= d; commit(bps);
    note((d > 0 ? 'Moved 1 point to ' : 'Moved 1 point from ') + read()[i].name.split(' ')[0] + (d > 0 ? ' from ' : ' to ') + read()[j].name.split(' ')[0] + '.');
  });
  amtInput.addEventListener('input', () => draw(live));

  // corrections in words
  async function post(url, body, raw, type) {
    const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': type || 'application/json' }, body: raw || JSON.stringify(body) });
    const data = await r.json().catch(() => ({})); if (!r.ok) throw new Error(data.error || 'Request failed'); return data;
  }
  async function applyWords(text) {
    text = text.trim(); if (!text) return;
    chips.replaceChildren();
    try {
      const ppl = read(); if (!ppl.length) throw new Error('Add the people first.');
      const res = await post('/api/split/correct', { text, people: ppl.map(p => ({ name: p.name, bps: p.bps, role: p.role, evidence: p.evidence })) });
      if (res.changes.length) { snapshot(); commit(res.people.map(p => p.bps)); res.changes.forEach(c => note(c)); sayInput.value = ''; }
      res.unmatched.forEach(u => note('Did not understand: ' + u, true));
      if (!res.changes.length && !res.unmatched.length) note('Nothing to change.', true);
    } catch (e) { note(e.message, true); }
  }
  $('studioApply') || 0;
  studio.querySelector('#studioApply').addEventListener('click', () => applyWords(sayInput.value));
  sayInput.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); applyWords(sayInput.value); } });
  studio.querySelector('#studioEven').addEventListener('click', () => { snapshot(); commit(to10000(read().map(() => 1))); note('Split evenly.'); });
  undoBtn.addEventListener('click', () => {
    const h = hist.pop(); if (!h) return; undoBtn.hidden = !hist.length;
    writeShares(h.bps, true); if ($('agreement').value !== h.agreement) { setVal($('agreement'), h.agreement); }
    rows().forEach(r => { /* quotes follow the restored agreement */ }); draw(); note('Undone.');
  });
  // microphone -> local speech-to-text
  let rec = null, chunks = [];
  micBtn.addEventListener('click', async () => {
    if (rec) { rec.stop(); return; }
    try {
      if (!navigator.mediaDevices || !window.MediaRecorder) throw new Error('This browser cannot record. Type the change instead.');
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      rec = new MediaRecorder(stream); chunks = [];
      rec.ondataavailable = ev => chunks.push(ev.data);
      rec.onstop = async () => {
        stream.getTracks().forEach(t => t.stop()); micBtn.setAttribute('aria-pressed', 'false'); micBtn.textContent = '🎤 Speak';
        const blob = new Blob(chunks, { type: rec.mimeType || 'audio/webm' }); rec = null;
        note('Listening on this computer…');
        try { const r = await post('/api/split/listen', null, blob, blob.type); chips.replaceChildren(); sayInput.value = r.text; if (r.text) await applyWords(r.text); else note('Heard nothing. Type it instead.', true); }
        catch (e) { chips.replaceChildren(); note(e.message, true); }
      };
      rec.start(); micBtn.setAttribute('aria-pressed', 'true'); micBtn.textContent = '■ Stop';
    } catch (e) { rec = null; note(e.message || 'Microphone not available. Type the change instead.', true); }
  });

  /* ---------- 4. Bring in credits: paste or photograph, then see the words each share came from ---------- */
  const intake = el('section', { id: 'splitIntake', 'aria-label': 'Bring in credits' });
  const paste = el('textarea', { id: 'creditsText', placeholder: 'Paste the session credits or split sheet here, or take a photo of it.', 'aria-label': 'Credits or split sheet text' });
  const fileIn = el('input', { type: 'file', id: 'creditsPhoto', accept: 'image/*', capture: 'environment', class: 'sr', tabindex: -1 });
  const result = el('div', { id: 'creditsResult' });
  const sampleBtn = el('button', { type: 'button', class: 'big-btn', id: 'creditsSample', hidden: true }, 'Use the sample split sheet');
  intake.append(
    el('div', { class: 'studio-h' }, el('div', {}, el('h2', { text: 'Bring in what you have' }), el('p', { text: 'A split sheet or session credits, pasted or photographed. The people and shares are proposed; you check them against the words.' }))),
    paste,
    el('div', { class: 'intake-row' },
      el('button', { type: 'button', class: 'big-btn primary', id: 'creditsRead' }, 'Read it'),
      el('button', { type: 'button', class: 'big-btn', id: 'creditsPhotoBtn' }, '📷 Photo'), sampleBtn, fileIn),
    result);
  let proposal = null;
  async function readCredits(body) {
    result.replaceChildren(el('p', { class: 'hintline', text: 'Reading… (on this computer)' }));
    try { proposal = await post('/api/split/credits', body); showProposal(); }
    catch (e) { result.replaceChildren(el('p', { class: 'chip warn', text: e.message })); }
  }
  function showProposal() {
    const p = proposal, doc = el('div', { class: 'doc', id: 'creditsDoc' });
    const marks = [];
    p.people.forEach((x, i) => x.evidence.forEach(q => marks.push({ ...q, i })));
    marks.sort((a, b) => a.start - b.start);
    let pos = 0;
    for (const m of marks) {
      if (m.start < pos) continue;
      doc.append(p.source_text.slice(pos, m.start));
      const k = palette(p.people[m.i].name) % 6;
      doc.append(el('mark', { class: 'who' + k, 'data-i': m.i, text: p.source_text.slice(m.start, m.end) })); pos = m.end;
    }
    doc.append(p.source_text.slice(pos));
    const list = el('div', { class: 'cards' }, ...p.people.map((x, i) => el('div', { class: 'card prop who' + palette(x.name) % 6, 'data-i': i, tabindex: 0, role: 'button', 'aria-label': 'Show where ' + x.name + ' comes from' },
      el('div', { class: 'avatar', text: initials(x.name) }), el('b', { text: x.name }), el('span', { class: 'pct', text: fmtPct(x.bps) + '%' }),
      el('small', { text: x.role || 'collaborator' }), el('span', { class: 'amt', text: x.evidence[0] ? 'from the highlighted line' : 'no line found' }),
      x.evidence[0] ? el('div', { class: 'q', text: '“' + x.evidence[0].text + '”' }) : null)));
    const focusMark = i => { doc.querySelectorAll('mark').forEach(m => m.classList.toggle('on', +m.dataset.i === i)); const m = doc.querySelector('mark[data-i="' + i + '"]'); if (m) m.scrollIntoView({ block: 'nearest' }); };
    list.addEventListener('click', e => { const c = e.target.closest('.prop'); if (c) focusMark(+c.dataset.i); });
    list.addEventListener('keydown', e => { const c = e.target.closest('.prop'); if (c && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); focusMark(+c.dataset.i); } });
    result.replaceChildren(
      el('p', { class: 'hintline', text: 'Read by: ' + p.reader + (p.source === 'photo' ? ' · text read from your photo, check it' : '') }),
      doc, list, ...p.notes.map(n => el('p', { class: 'chip warn', text: n })),
      el('div', { class: 'intake-row' }, el('button', { type: 'button', class: 'big-btn primary', id: 'creditsUse' }, 'Use this split'), el('button', { type: 'button', class: 'big-btn', id: 'creditsDismiss' }, 'Not right')));
    result.querySelector('#creditsDismiss').addEventListener('click', () => result.replaceChildren());
    result.querySelector('#creditsUse').addEventListener('click', useProposal);
  }
  function useProposal() {
    const p = proposal; if (!p || !p.people.length) return;
    rows().forEach(r => r.remove());
    const lines = p.people.map(x => x.name + ' receives ' + fmtPct(x.bps) + '% of net receipts.');
    p.people.forEach((x, i) => { const it = addPerson({ name: x.name, share_bps: x.bps, evidence: lines[i] }); it.dataset.role = x.role || ''; });
    const title = (p.source_text.match(/[“"]([^”"\n]{2,60})[”"]/) || [])[1];
    if (!$('project').value.trim()) setVal($('project'), title || 'New project');
    const ag = $('agreement'); if (!ag.dataset.original) ag.dataset.original = ag.value;
    const kept = ag.value.split('\n').map(l => l.trim()).filter(l => l && !/%/.test(l) && !p.people.some(x => l.includes(x.name)));
    setVal(ag, [kept[0] || (($('project').value.trim() || 'Royalty') + ' split sheet.'), '', ...lines, '', ...kept.slice(1), 'Net receipts are sales less refunds and platform fees.'].filter((l, i, a) => l !== 'Net receipts are sales less refunds and platform fees.' || !kept.some(k => /net receipts/i.test(k))).join('\n'));
    hist = []; undoBtn.hidden = true; chips.replaceChildren();
    window.invalidate && invalidate(); draw();
    note('Split filled in from your ' + (p.source === 'photo' ? 'photo' : 'credits') + '. Drag to adjust.');
    result.replaceChildren(el('p', { class: 'chip', text: 'Added ' + p.people.length + ' people. Their colours stay the same everywhere.' }));
    studio.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
  $('creditsRead') || 0;
  intake.querySelector('#creditsRead').addEventListener('click', () => readCredits({ text: paste.value }));
  intake.querySelector('#creditsPhotoBtn').addEventListener('click', () => fileIn.click());
  fileIn.addEventListener('change', async () => {
    const f = fileIn.files[0]; if (!f) return;
    if (f.size > 8e6) { result.replaceChildren(el('p', { class: 'chip warn', text: 'Choose a picture under 8 MB.' })); return; }
    const url = URL.createObjectURL(f);
    result.replaceChildren(el('img', { class: 'thumb', src: url, alt: 'Your photo' }));
    const b64 = await new Promise(res => { const fr = new FileReader(); fr.onload = () => res(String(fr.result).split(',')[1]); fr.readAsDataURL(f); });
    await readCredits({ image_base64: b64 }); result.prepend(el('img', { class: 'thumb', src: url, alt: 'Your photo' })); fileIn.value = '';
  });
  sampleBtn.addEventListener('click', async () => { const s = await (await fetch('/api/split/sample')).json(); paste.value = s.text; readCredits({ text: s.text }); });
  fetch('/api/split/sample').then(r => r.json()).then(s => { sampleBtn.hidden = !s.text; }).catch(() => {});

  /* ---------- 5. Works home with marks ---------- */
  const worksSec = el('section', { id: 'view-works', class: 'view-panel', 'aria-label': 'Works', hidden: true });
  const filterBar = el('div', { class: 'filters', id: 'worksFilters', role: 'group', 'aria-label': 'Filter works' });
  const list = el('div', { id: 'worksList' });
  worksSec.append(el('div', { class: 'works-wrap' }, filterBar, list));
  const MARKS = { paid: ['✓', 'Paid out'], pending: ['◔', 'Pending'], unagreed: ['!', 'Split not agreed'] };
  const DEMO_BARS = { 'demo-low-tide': [['Ines Farrow', 50], ['Tomas Bell', 30], ['Rae Okonkwo', 20]], 'demo-night-bus': [['Ines Farrow', 60], ['Tomas Bell', 40]], 'demo-harbour': [['Ines Farrow', 25], ['Tomas Bell', 25], ['Rae Okonkwo', 25], ['Dev Anand', 15]] };
  let works = [], filter = 'all';
  function currentDraftWork() {
    const ppl = read(), name = $('project').value.trim();
    if (!name && !ppl.length) return null;
    const sum = ppl.reduce((a, p) => a + p.bps, 0), agreed = ppl.length > 0 && sum === 10000;
    return { id: 'draft', title: name || 'New project', period: (window.deskPeriod && deskPeriod()) || 'Current draft', net_cents: 0, people: ppl.length, mark: agreed ? 'pending' : 'unagreed', draft: true, bar: ppl.map(p => [p.name, p.bps / 100]) };
  }
  async function loadWorks() {
    let saved = []; try { saved = (await (await fetch('/api/split/works')).json()).works || []; } catch (e) { /* offline */ }
    const d = currentDraftWork(); works = (d ? [d] : []).concat(saved.filter(w => !(d && w.title === d.title && !w.sample)));
    drawWorks();
  }
  function drawWorks() {
    const count = k => works.filter(w => k === 'all' || w.mark === k).length;
    filterBar.replaceChildren(...[['all', 'All'], ['paid', 'Paid out'], ['pending', 'Pending'], ['unagreed', 'Split not agreed']].map(([k, t]) =>
      el('button', { type: 'button', 'aria-pressed': String(filter === k), 'data-filter': k, text: t + ' ' + count(k), onclick: () => { filter = k; drawWorks(); } })));
    const shown = works.filter(w => filter === 'all' || w.mark === filter);
    list.replaceChildren(...(shown.length ? shown.map(w => {
      const bar = w.bar || DEMO_BARS[w.id];
      const [ic, label] = MARKS[w.mark];
      return el('button', { type: 'button', class: 'work', 'data-mark': w.mark, 'data-id': w.id, onclick: () => openWork(w) },
        el('div', {}, el('b', { text: w.title }), el('br'), el('small', { text: w.period + ' · ' + w.people + (w.people === 1 ? ' person' : ' people') + (w.sample ? ' · sample' : '') })),
        el('div', { style: 'text-align:right' }, el('span', { class: 'mark ' + w.mark }, ic + ' ' + label), w.net_cents ? el('div', { class: 'money', text: usd(w.net_cents) }) : null),
        bar ? el('div', { class: 'minibar', 'aria-hidden': 'true' }, ...bar.map(([n, v]) => el('i', { class: 'who' + palette(n) % 6, style: 'width:' + v + '%' }))) : null);
    }) : [el('p', { class: 'hintline', text: 'Nothing here yet.' })]));
  }
  function openWork(w) {
    if (w.draft) return window.showDeskView('splits');
    if (w.sample) return;
    const h = $('openHistory'); if (h) h.click();
  }
  function showWorks() {
    window.showDeskView('statement', { scroll: false });
    document.querySelectorAll('.view-panel').forEach(p => p.hidden = p.id !== 'view-works');
    document.querySelectorAll('[data-view]').forEach(b => { if (b.dataset.view === 'works') b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current'); });
    document.body.dataset.deskView = 'works';
    $('workspaceTitle').textContent = 'Works'; $('workspaceSubtitle').textContent = 'Every release, and where its money stands';
    $('deskPrimary').hidden = true; $('preview').hidden = true; if ($('saveStatement')) $('saveStatement').hidden = true;
    loadWorks(); window.scrollTo({ top: 0 });
  }
  const navBtn = el('button', { type: 'button', 'data-view': 'works', id: 'navWorks' });
  navBtn.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5h16M4 12h16M4 19h16"/></svg><span>Works</span>';
  navBtn.addEventListener('click', e => { e.stopImmediatePropagation(); showWorks(); }, true);
  document.querySelector('.workspace-nav').prepend(navBtn);
  $('brandHome').addEventListener('click', e => { e.preventDefault(); showWorks(); });

  /* ---------- 6. Mount ---------- */
  const splits = $('view-splits');
  splits.prepend(intake);
  $('creatorSetup').insertBefore(studio, $('people'));
  $('creatorSetup').parentNode.parentNode.insertBefore(worksSec, $('view-statement'));
  const people = $('people');
  let t = null;
  const refresh = () => { clearTimeout(t); t = setTimeout(() => { if (!drag) draw(); }, 30); };
  people.addEventListener('input', refresh);
  new MutationObserver(refresh).observe(people, { childList: true });
  // stable colours on the payout and statement weave
  let raf = 0;
  function paintWeave() {
    raf = 0;
    document.querySelectorAll('.weave-canvas').forEach(cv => { const ends = [...cv.querySelectorAll('.weave-end')], paths = [...cv.querySelectorAll('.weave-svg path')];
      paths.forEach((p, i) => { const s = ends[i] && ends[i].querySelector('strong'); if (!s) return; const c = 'var(--c' + palette(s.textContent.split(' · ')[0]) % 6 + ')'; p.style.fill = c; p.style.stroke = c; }); });
    document.querySelectorAll('.weave-end').forEach(n => { const s = n.querySelector('strong'); if (!s) return; const k = palette(s.textContent.split(' · ')[0]) % 6; n.style.setProperty('--who', 'var(--c' + k + ')'); });
  }
  new MutationObserver(() => { if (!raf) raf = requestAnimationFrame(paintWeave); }).observe(document.querySelector('.workspace'), { childList: true, subtree: true });
  draw();
  window.RoyaltyStudio = { draw, read, applyWords };
})();
