import {
  loadOrders, loadAdSpend, buildReview, ruleSummary, llmSummary, latestCompleteWeekEnd,
  fmtDay, money,
} from './wbr.js';

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const SYMBOLS = { USD: '$', CAD: 'CA$', AUD: 'A$', EUR: '€', GBP: '£', INR: '₹', JPY: '¥', AED: 'AED ', SAR: 'SAR ' };

const state = { orders: null, ads: null, sample: false, store: 'My Store', currency: '$', weekEnd: null, ai: null, apiKey: '' };

// ---------- file loading ----------
const readFile = (file) => new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(r.result); r.onerror = () => rej(r.error); r.readAsText(file); });

function showError(msg) { const e = $('error'); e.textContent = msg; e.hidden = !msg; }

function detectCurrency(text) {
  const m = /(?:^|,)(USD|CAD|AUD|EUR|GBP|INR|JPY|AED|SAR|[A-Z]{3})(?:,|$)/m.exec(text.split('\n').slice(1, 6).join('\n'));
  if (!m) return '$';
  return SYMBOLS[m[1]] || `${m[1]} `;
}

async function useOrders(text, { sample = false } = {}) {
  showError('');
  try {
    const orders = loadOrders(text);
    if (!orders.length) throw new Error('No orders found in this file.');
    state.orders = orders;
    state.sample = sample;
    state.currency = detectCurrency(text);
    state.store = sample ? 'Sample Home Goods Co.' : $('store-name').value === 'Sample Home Goods Co.' ? 'My Store' : $('store-name').value || 'My Store';
    $('store-name').value = state.store;
    state.weekEnd = latestCompleteWeekEnd(orders);
    state.ai = null;
    fillWeeks();
    render();
    $('landing').hidden = true;
    $('report-view').hidden = false;
    window.scrollTo(0, 0);
  } catch (err) {
    showError(err.message);
  }
}

async function useAds(text) {
  try {
    state.ads = loadAdSpend(text);
    $('ads-status').textContent = `✓ Ad spend loaded (${state.ads.length} rows)`;
    state.ai = null;
    if (state.orders) render();
  } catch (err) {
    showError(err.message);
    if (state.orders) alert(err.message);
  }
}

function fillWeeks() {
  const first = Math.min(...state.orders.map((o) => o.day));
  const opts = [];
  for (let end = latestCompleteWeekEnd(state.orders); end - 6 >= first - 6 && opts.length < 26; end -= 7) {
    opts.push(`<option value="${end}">${fmtDay(end - 6)} – ${fmtDay(end, { year: true })}</option>`);
  }
  $('week-select').innerHTML = opts.join('');
  $('week-select').value = String(state.weekEnd);
}

// ---------- charts ----------
function dailyChart(cur, prev, sym) {
  const w = 540, h = 210, pl = 46, pb = 24, pt = 10;
  const top = Math.max(...cur.dailyRevenue, ...prev.dailyRevenue, 1) * 1.1;
  const slot = (w - pl) / 7, bw = slot * 0.32;
  let s = `<svg viewBox="0 0 ${w} ${h}" width="100%" role="img" aria-label="Daily revenue, this week vs last week">`;
  for (let i = 0; i < 5; i++) {
    const y = pt + ((h - pb - pt) * i) / 4;
    s += `<line x1="${pl}" x2="${w}" y1="${y}" y2="${y}" stroke="#f0f1f3"/><text x="${pl - 6}" y="${y + 4}" font-size="10" fill="#9ca3af" text-anchor="end">${esc(sym)}${((top * (1 - i / 4)) / 1000).toFixed(1)}k</text>`;
  }
  for (let d = 0; d < 7; d++) {
    const x0 = pl + d * slot + slot * 0.16;
    [[prev.dailyRevenue, '#cbd5e1'], [cur.dailyRevenue, '#4f46e5']].forEach(([vals, color], j) => {
      const bh = ((h - pb - pt) * vals[d]) / top;
      s += `<rect x="${(x0 + j * bw).toFixed(1)}" y="${(h - pb - bh).toFixed(1)}" width="${(bw - 2).toFixed(1)}" height="${bh.toFixed(1)}" rx="2" fill="${color}"><title>${DAYS[d]} ${j ? 'this' : 'last'} week: ${esc(money(vals[d], sym))}</title></rect>`;
    });
    s += `<text x="${(pl + d * slot + slot / 2).toFixed(1)}" y="${h - 6}" font-size="11" fill="#6b7280" text-anchor="middle">${DAYS[d]}</text>`;
  }
  return s + '</svg>';
}

function trendChart(trend, sym) {
  if (trend.length < 2) return '<p class="muted small">Export more weeks of orders to see a trend.</p>';
  const w = 360, h = 210, pl = 46, pb = 24, pt = 10, pr = 20;
  const top = Math.max(...trend.map((t) => t[1])) * 1.15 || 1;
  const step = (w - pl - pr - 8) / (trend.length - 1);
  const pts = trend.map(([, v], i) => [pl + 8 + i * step, pt + (h - pb - pt) * (1 - v / top)]);
  const path = pts.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  let s = `<svg viewBox="0 0 ${w} ${h}" width="100%" role="img" aria-label="Weekly revenue trend">`;
  for (let i = 0; i < 5; i++) {
    const y = pt + ((h - pb - pt) * i) / 4;
    s += `<line x1="${pl}" x2="${w}" y1="${y}" y2="${y}" stroke="#f0f1f3"/><text x="${pl - 6}" y="${y + 4}" font-size="10" fill="#9ca3af" text-anchor="end">${esc(sym)}${((top * (1 - i / 4)) / 1000).toFixed(0)}k</text>`;
  }
  s += `<path d="${path} L${pts.at(-1)[0]},${h - pb} L${pts[0][0]},${h - pb} Z" fill="#eef2ff"/><path d="${path}" fill="none" stroke="#4f46e5" stroke-width="2"/>`;
  const labelEvery = trend.length > 8 ? 2 : 1;
  pts.forEach(([x, y], i) => {
    s += `<circle cx="${x}" cy="${y}" r="${i === pts.length - 1 ? 4 : 2.5}" fill="#4f46e5"><title>Week of ${fmtDay(trend[i][0])}: ${esc(money(trend[i][1], sym))}</title></circle>`;
    if (i % labelEvery === 0 || i === pts.length - 1) s += `<text x="${x}" y="${h - 6}" font-size="10" fill="#6b7280" text-anchor="middle">${fmtDay(trend[i][0])}</text>`;
  });
  return s + '</svg>';
}

// ---------- report ----------
function badge(change, { invert = false, points = null } = {}) {
  if (points != null) {
    if (Math.abs(points) < 0.05) return '<span class="badge flat">±0.0 pp</span>';
    const good = invert ? points < 0 : points > 0;
    return `<span class="badge ${good ? 'up' : 'down'}">${points > 0 ? '+' : ''}${points.toFixed(1)} pp</span>`;
  }
  if (change == null) return '<span class="badge flat">new</span>';
  if (Math.abs(change) < 0.005) return '<span class="badge flat">±0%</span>';
  const good = invert ? change < 0 : change > 0;
  return `<span class="badge ${good ? 'up' : 'down'}">${change > 0 ? '+' : ''}${(change * 100).toFixed(1)}%</span>`;
}
const kpi = (label, value, b) => `<div class="card kpi"><div class="label">${label}</div><div class="value">${value}</div>${b} <span class="small muted">vs last week</span></div>`;

function render() {
  const r = buildReview(state.orders, state.ads || [], { weekEnding: state.weekEnd });
  const c = r.current, p = r.previous, cur = state.currency;
  const pctOf = (v, t) => (t ? Math.round((v / t) * 100) : 0) + '%';

  const kpis = [
    kpi('Revenue', money(c.revenue, cur), badge(r.change('revenue'))),
    kpi('Orders', c.orders.toLocaleString('en-US'), badge(r.change('orders'))),
    kpi('AOV', money(c.aov, cur, 2), badge(r.change('aov'))),
    kpi('Refund rate', `${(c.refundRate * 100).toFixed(1)}%`, badge(null, { invert: true, points: (c.refundRate - p.refundRate) * 100 })),
    kpi('Net revenue', money(c.netRevenue, cur), badge(r.change('netRevenue'))),
    kpi('Units sold', c.units.toLocaleString('en-US'), badge(r.change('units'))),
    kpi('New customers', c.newCustomers.toLocaleString('en-US'), badge(r.change('newCustomers'))),
    r.hasAdData
      ? kpi('Blended ROAS', c.roas == null ? 'n/a' : `${c.roas.toFixed(2)}x`, badge(r.change('roas')))
      : kpi('Returning customers', c.returningCustomers.toLocaleString('en-US'), badge(r.change('returningCustomers'))),
  ];

  const topRows = r.topProducts.map((t, i) => `<tr><td>${i + 1}. ${esc(t.name)}</td><td class="num">${t.units.toLocaleString('en-US')}</td><td class="num">${money(t.revenue, cur)}</td><td class="num">${badge(t.change)}</td></tr>`).join('')
    || '<tr><td colspan="4" class="muted">No line items this week.</td></tr>';
  const refundRows = r.refundsByProduct.slice(0, 5).map(([n, v]) => `<tr><td>${esc(n)}</td><td class="num">${money(v, cur)}</td><td class="num">${pctOf(v, c.refunds)}</td></tr>`).join('')
    || '<tr><td colspan="3" class="muted">No refunds this week.</td></tr>';

  const side = r.hasAdData
    ? `<div class="card"><h2>Ad spend</h2><table><tr><th>Channel</th><th class="num">Spend</th><th class="num">Share</th></tr>
        ${c.adSpendByChannel.map(([ch, v]) => `<tr><td>${esc(ch)}</td><td class="num">${money(v, cur)}</td><td class="num">${pctOf(v, c.adSpend)}</td></tr>`).join('')}
        <tr><td><b>Total</b></td><td class="num"><b>${money(c.adSpend, cur)}</b></td><td class="num">${badge(r.change('adSpend'), { invert: true })}</td></tr></table>
        <p class="small muted" style="margin:10px 0 0">Cost per new customer: <b>${c.cac == null ? 'n/a' : money(c.cac, cur, 2)}</b></p></div>`
    : `<div class="card"><h2>Customers</h2><p style="margin:0 0 8px">New: <b>${c.newCustomers}</b> · Returning: <b>${c.returningCustomers}</b></p>
        <p class="small muted no-print" style="margin:0">Add an ad spend CSV (<code>date,channel,spend</code>) to see ROAS and cost per new customer.</p></div>`;

  const bullets = state.ai || ruleSummary(r, cur);
  const source = state.ai ? 'Written by AI from the numbers on this page.' : 'Generated from the numbers on this page.';

  $('report').innerHTML = `
    <div class="r-head"><div><div class="small muted">Weekly Business Review</div><h1>${esc(state.store)}</h1></div>
      <div class="muted">${fmtDay(c.start, { weekday: true })} – ${fmtDay(c.end, { weekday: true, year: true })}</div></div>
    ${state.sample ? '<div class="card banner"><b>Sample report.</b> Built from synthetic data for a fictional store. Upload your own export to see yours.</div>' : ''}
    <div class="card"><h2>Summary</h2><ul class="summary">${bullets.map((b) => `<li>${esc(b)}</li>`).join('')}</ul>
      <p class="small muted" style="margin:8px 0 0">${source}</p></div>
    <div class="grid">${kpis.join('')}</div>
    <div class="row">
      <div class="card"><h2>Daily revenue</h2><div class="legend"><span><i style="background:#4f46e5"></i>This week</span><span><i style="background:#cbd5e1"></i>Last week</span></div>${dailyChart(c, p, cur)}</div>
      <div class="card"><h2>Weekly revenue trend</h2>${trendChart(r.trend, cur)}</div>
    </div>
    <div class="row">
      <div class="card"><h2>Top products</h2><table><tr><th>Product</th><th class="num">Units</th><th class="num">Revenue</th><th class="num">WoW</th></tr>${topRows}</table></div>
      ${side}
    </div>
    <div class="card"><h2>Refunds by product</h2><table><tr><th>Product</th><th class="num">Refunded</th><th class="num">Share</th></tr>${refundRows}</table>
      <p class="small muted" style="margin:10px 0 0">Shopify exports refunds per order, so each refund is split across that order's items by value (exact for single-item orders).</p></div>
    <p class="defs">Revenue = Shopify order total (after discounts, incl. shipping &amp; tax), excluding voided/cancelled orders. Refund rate = refunded value ÷ revenue. New customer = first order in this file falls in this week.</p>`;
  document.title = `WBR · ${state.store} · ${fmtDay(c.start)}`;
}

// ---------- events ----------
const dz = $('dropzone');
dz.addEventListener('click', () => $('orders-file').click());
dz.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); $('orders-file').click(); } });
['dragenter', 'dragover'].forEach((t) => dz.addEventListener(t, (e) => { e.preventDefault(); dz.classList.add('drag'); }));
['dragleave', 'drop'].forEach((t) => dz.addEventListener(t, (e) => { e.preventDefault(); dz.classList.remove('drag'); }));
dz.addEventListener('drop', async (e) => {
  const files = [...(e.dataTransfer?.files || [])];
  if (!files.length) return;
  // Two files dropped at once: the one with a spend column (and no line items) is the ad spend CSV.
  const texts = await Promise.all(files.map(readFile));
  const isAds = (t) => { const h = t.slice(0, 300).toLowerCase(); return h.includes('spend') && !h.includes('lineitem'); };
  if (files.length > 1) for (const t of texts.filter(isAds)) await useAds(t);
  const orders = files.length > 1 ? texts.find((t) => !isAds(t)) : texts[0];
  if (orders) await useOrders(orders);
});
$('orders-file').addEventListener('change', async (e) => { const f = e.target.files[0]; if (f) await useOrders(await readFile(f)); e.target.value = ''; });
for (const id of ['ads-file-landing', 'ads-file-report']) {
  $(id).addEventListener('change', async (e) => { const f = e.target.files[0]; if (f) await useAds(await readFile(f)); e.target.value = ''; });
}

$('try-sample').addEventListener('click', async () => {
  const btn = $('try-sample');
  btn.disabled = true; btn.textContent = 'Loading sample…';
  try {
    const [o, a] = await Promise.all([fetch('sample/orders_sample.csv').then((r) => r.text()), fetch('sample/ad_spend_sample.csv').then((r) => r.text())]);
    await useAds(a);
    await useOrders(o, { sample: true });
  } catch (err) {
    showError(`Couldn't load the sample data: ${err.message}`);
  } finally {
    btn.disabled = false; btn.textContent = 'Try with sample data';
  }
});

$('back').addEventListener('click', () => {
  $('report-view').hidden = true; $('landing').hidden = false;
  state.orders = null; state.ads = null; state.ai = null; $('ads-status').textContent = '';
  window.scrollTo(0, 0);
});
$('store-name').addEventListener('input', (e) => { state.store = e.target.value || 'My Store'; render(); });
$('week-select').addEventListener('change', (e) => { state.weekEnd = Number(e.target.value); state.ai = null; render(); });
$('print').addEventListener('click', () => window.print());

$('ai-key').addEventListener('input', (e) => { state.apiKey = e.target.value.trim(); });
$('ai-run').addEventListener('click', async () => {
  const status = $('ai-status');
  if (!state.apiKey) { status.textContent = 'Paste an API key first. (Not needed for the regular report.)'; return; }
  const btn = $('ai-run'); btn.disabled = true; status.textContent = 'Writing summary…';
  try {
    const r = buildReview(state.orders, state.ads || [], { weekEnding: state.weekEnd });
    state.ai = await llmSummary(r, { provider: $('ai-provider').value, apiKey: state.apiKey, currency: state.currency });
    render();
    status.textContent = '✓ Summary updated above. Your key was used for this one request and is not saved.';
  } catch (err) {
    status.textContent = `AI summary failed: ${err.message}. The rule-based summary is still shown.`;
  } finally { btn.disabled = false; }
});

// Handy for demos: ?sample opens the sample report directly.
if (new URLSearchParams(location.search).has('sample')) $('try-sample').click();
