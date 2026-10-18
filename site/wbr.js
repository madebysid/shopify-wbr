// shopify-wbr core: CSV parsing, weekly metrics and the rule-based summary.
// Pure functions, no DOM, so the same code runs in the browser and in Node tests.
// Dates are handled as "YYYY-MM-DD" day numbers in the store's local time
// (Shopify exports timestamps in the store's timezone).

// ---------- CSV ----------
export function parseCSV(text) {
  if (text.charCodeAt(0) === 0xfeff) text = text.slice(1);
  const rows = [];
  let row = [], field = '', i = 0, inQuotes = false;
  while (i < text.length) {
    const ch = text[i];
    if (inQuotes) {
      if (ch === '"') {
        if (text[i + 1] === '"') { field += '"'; i += 2; continue; }
        inQuotes = false; i++; continue;
      }
      field += ch; i++; continue;
    }
    if (ch === '"') { inQuotes = true; i++; continue; }
    if (ch === ',') { row.push(field); field = ''; i++; continue; }
    if (ch === '\r') { i++; continue; }
    if (ch === '\n') { row.push(field); rows.push(row); row = []; field = ''; i++; continue; }
    field += ch; i++;
  }
  if (field !== '' || row.length) { row.push(field); rows.push(row); }
  const header = (rows.shift() || []).map((h) => h.trim());
  return {
    header,
    records: rows
      .filter((r) => r.some((v) => v.trim() !== ''))
      .map((r) => Object.fromEntries(header.map((h, j) => [h, r[j] ?? '']))),
  };
}

const num = (v) => {
  if (v == null) return 0;
  const s = String(v).trim().replace(/[,$]/g, '');
  if (!s) return 0;
  const n = Number(s);
  return Number.isFinite(n) ? n : 0;
};

// ---------- dates (integer day numbers, UTC-based, timezone-free) ----------
const DAY = 86400000;
export function dayNum(str) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(str).trim());
  if (m) return Math.floor(Date.UTC(+m[1], +m[2] - 1, +m[3]) / DAY);
  const d = new Date(str);
  if (isNaN(d)) throw new Error(`Unrecognised date: "${str}"`);
  return Math.floor(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()) / DAY);
}
export const isoDay = (n) => new Date(n * DAY).toISOString().slice(0, 10);
export const weekday = (n) => (new Date(n * DAY).getUTCDay() + 6) % 7; // Mon=0..Sun=6
export const weekStart = (n) => n - weekday(n);

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
// e.g. "12 Oct", with options { weekday: true, year: true } -> "Mon 12 Oct 2026"
export function fmtDay(n, { weekday: wd = false, year = false } = {}) {
  const d = new Date(n * DAY);
  return `${wd ? WEEKDAYS[(d.getUTCDay() + 6) % 7] + ' ' : ''}${String(d.getUTCDate()).padStart(2, '0')} ${MONTHS[d.getUTCMonth()]}${year ? ' ' + d.getUTCFullYear() : ''}`;
}

// ---------- loaders ----------
export function loadOrders(text) {
  const { header, records } = parseCSV(text);
  const missing = ['Name', 'Created at', 'Total'].filter((c) => !header.includes(c));
  if (missing.length) {
    throw new Error(
      `This doesn't look like a Shopify orders export (missing column${missing.length > 1 ? 's' : ''}: ${missing.join(', ')}). ` +
        'In Shopify admin go to Orders → Export and choose "CSV for Excel, Numbers, or other spreadsheet programs".'
    );
  }
  const byName = new Map();
  for (const r of records) {
    const name = (r['Name'] || '').trim();
    if (!name) continue;
    let o = byName.get(name);
    if (!o) {
      o = {
        name,
        day: dayNum(r['Created at']),
        createdAt: r['Created at'],
        email: (r['Email'] || '').trim().toLowerCase(),
        financialStatus: (r['Financial Status'] || '').trim(),
        subtotal: num(r['Subtotal']),
        discount: num(r['Discount Amount']),
        total: num(r['Total']),
        refunded: num(r['Refunded Amount']),
        lineItems: [],
      };
      byName.set(name, o);
    }
    const itemName = (r['Lineitem name'] || '').trim();
    if (itemName) {
      o.lineItems.push({
        name: itemName,
        sku: (r['Lineitem sku'] || '').trim(),
        quantity: Math.trunc(num(r['Lineitem quantity'])),
        price: num(r['Lineitem price']),
      });
    }
  }
  return [...byName.values()].sort((a, b) => a.day - b.day || String(a.createdAt).localeCompare(String(b.createdAt)));
}

export const isVoided = (o) => ['voided', 'cancelled'].includes(o.financialStatus.toLowerCase());

export function loadAdSpend(text) {
  const { header, records } = parseCSV(text);
  const cols = Object.fromEntries(header.map((h) => [h.toLowerCase(), h]));
  if (!cols.date || !cols.spend) throw new Error('The ad spend CSV needs at least "date" and "spend" columns (and optionally "channel").');
  return records.map((r) => ({
    day: dayNum(r[cols.date]),
    channel: (cols.channel && r[cols.channel].trim()) || 'Ads',
    spend: num(r[cols.spend]),
  }));
}

// ---------- metrics ----------
export const pctChange = (cur, prev) => (prev == null || cur == null || prev === 0 ? null : (cur - prev) / prev);

export function latestCompleteWeekEnd(orders) {
  if (!orders.length) throw new Error('No orders found in this file.');
  const last = Math.max(...orders.map((o) => o.day));
  return weekday(last) === 6 ? last : last - weekday(last) - 1;
}

function weekMetrics(orders, ads, start, firstSeen) {
  const end = start + 6;
  const m = {
    start, end, revenue: 0, refunds: 0, orders: 0, refundedOrders: 0, units: 0, discounts: 0,
    newCustomers: 0, returningCustomers: 0, adSpend: 0, adSpendByChannel: [], dailyRevenue: [0, 0, 0, 0, 0, 0, 0],
  };
  const newSet = new Set(), retSet = new Set();
  for (const o of orders) {
    if (o.day < start || o.day > end || isVoided(o)) continue;
    m.orders++;
    m.revenue += o.total;
    m.refunds += o.refunded;
    m.discounts += o.discount;
    m.units += o.lineItems.reduce((s, li) => s + li.quantity, 0);
    m.dailyRevenue[o.day - start] += o.total;
    if (o.refunded > 0) m.refundedOrders++;
    if (o.email) (firstSeen.get(o.email) >= start ? newSet : retSet).add(o.email);
  }
  m.newCustomers = newSet.size;
  m.returningCustomers = [...retSet].filter((e) => !newSet.has(e)).length;
  const ch = new Map();
  for (const a of ads) {
    if (a.day < start || a.day > end) continue;
    m.adSpend += a.spend;
    ch.set(a.channel, (ch.get(a.channel) || 0) + a.spend);
  }
  m.adSpendByChannel = [...ch.entries()].sort((a, b) => b[1] - a[1]);
  m.netRevenue = m.revenue - m.refunds;
  m.aov = m.orders ? m.revenue / m.orders : 0;
  m.refundRate = m.revenue ? m.refunds / m.revenue : 0;
  m.roas = m.adSpend ? m.revenue / m.adSpend : null;
  m.cac = m.adSpend && m.newCustomers ? m.adSpend / m.newCustomers : null;
  return m;
}

function productRevenue(orders, start) {
  const out = new Map();
  for (const o of orders) {
    if (o.day < start || o.day > start + 6 || isVoided(o)) continue;
    for (const li of o.lineItems) {
      const p = out.get(li.name) || { units: 0, revenue: 0 };
      p.units += li.quantity;
      p.revenue += li.quantity * li.price;
      out.set(li.name, p);
    }
  }
  return out;
}

// Shopify's export only has the refund per order, so split it across line items by value.
function refundsByProduct(orders, start) {
  const out = new Map();
  for (const o of orders) {
    if (o.day < start || o.day > start + 6 || o.refunded <= 0 || isVoided(o)) continue;
    const gross = o.lineItems.reduce((s, li) => s + li.quantity * li.price, 0);
    if (gross <= 0) continue;
    for (const li of o.lineItems) out.set(li.name, (out.get(li.name) || 0) + (o.refunded * li.quantity * li.price) / gross);
  }
  return [...out.entries()].sort((a, b) => b[1] - a[1]);
}

export function buildReview(orders, ads = [], { weekEnding = null, topN = 5, trendWeeks = 8 } = {}) {
  ads = ads || [];
  const end = weekEnding ?? latestCompleteWeekEnd(orders);
  const start = weekStart(end);
  const prevStart = start - 7;
  const firstSeen = new Map();
  for (const o of orders) {
    if (!o.email || isVoided(o)) continue;
    firstSeen.set(o.email, Math.min(firstSeen.get(o.email) ?? Infinity, o.day));
  }
  const current = weekMetrics(orders, ads, start, firstSeen);
  const previous = weekMetrics(orders, ads, prevStart, firstSeen);
  const curP = productRevenue(orders, start), prevP = productRevenue(orders, prevStart);
  const topProducts = [...curP.entries()]
    .sort((a, b) => b[1].revenue - a[1].revenue)
    .slice(0, topN)
    .map(([name, p]) => {
      const prevRevenue = prevP.get(name)?.revenue ?? 0;
      return { name, units: p.units, revenue: p.revenue, prevRevenue, change: pctChange(p.revenue, prevRevenue) };
    });
  let trend = [];
  for (let i = trendWeeks - 1; i >= 0; i--) {
    const ws = start - 7 * i;
    const rev = orders.filter((o) => o.day >= ws && o.day <= ws + 6 && !isVoided(o)).reduce((s, o) => s + o.total, 0);
    trend.push([ws, rev]);
  }
  while (trend.length && trend[0][1] === 0) trend.shift();
  const change = (k) => pctChange(current[k], previous[k]);
  return { current, previous, topProducts, trend, hasAdData: ads.length > 0, refundsByProduct: refundsByProduct(orders, start), change };
}

// ---------- summary ----------
export const fmtPct = (x) => (x == null ? 'n/a' : `${x >= 0 ? '+' : ''}${(x * 100).toFixed(1)}%`);
const money = (x, cur, d = 0) => `${x < 0 ? '-' : ''}${cur}${Math.abs(x).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d })}`;
export { money };

export function ruleSummary(r, cur = '$') {
  const c = r.current, p = r.previous, out = [];
  const rc = r.change('revenue');
  if (rc == null) out.push(`Revenue was ${money(c.revenue, cur)} from ${c.orders} orders (no prior week to compare).`);
  else
    out.push(
      `Revenue was ${money(c.revenue, cur)}, ${rc >= 0 ? 'up' : 'down'} ${(Math.abs(rc) * 100).toFixed(1)}% week over week, ` +
        `on ${c.orders} orders (${fmtPct(r.change('orders'))}) at an AOV of ${money(c.aov, cur, 2)} (${fmtPct(r.change('aov'))}).`
    );
  const dpp = (c.refundRate - p.refundRate) * 100;
  if (Math.abs(dpp) >= 1) {
    out.push(`Refund rate ${dpp > 0 ? 'rose' : 'fell'} to ${(c.refundRate * 100).toFixed(1)}% from ${(p.refundRate * 100).toFixed(1)}% (${c.refundedOrders} orders with refunds).`);
    if (dpp > 0 && r.refundsByProduct.length && c.refunds) {
      const [name, amt] = r.refundsByProduct[0];
      out.push(`${name} drove the most refunds (${money(amt, cur)}, ${Math.round((amt / c.refunds) * 100)}% of refunded value); check reviews and return reasons for that SKU.`);
    }
  } else out.push(`Refund rate held at ${(c.refundRate * 100).toFixed(1)}% of revenue.`);
  if (r.topProducts.length) {
    const t = r.topProducts[0];
    const share = c.revenue ? t.revenue / c.revenue : 0;
    out.push(`Top product: ${t.name} with ${money(t.revenue, cur)} (${Math.round(share * 100)}% of revenue, ${fmtPct(t.change)} WoW).`);
    const movers = r.topProducts.filter((x) => x.change != null);
    if (movers.length) {
      const worst = movers.reduce((a, b) => (b.change < a.change ? b : a));
      if (worst.change < -0.15) out.push(`Watch ${worst.name}: revenue ${fmtPct(worst.change)} vs last week.`);
    }
  }
  if (r.hasAdData && c.roas != null) {
    let s = `Blended ROAS was ${c.roas.toFixed(2)}x on ${money(c.adSpend, cur)} of ad spend`;
    if (p.roas != null) s += ` (last week ${p.roas.toFixed(2)}x)`;
    if (c.cac != null) s += `; cost per new customer ${money(c.cac, cur, 2)}`;
    out.push(s + '.');
  }
  out.push(`${c.newCustomers} new and ${c.returningCustomers} returning customers ordered this week.`);
  return out;
}

// Aggregated numbers only: no customer emails or order rows.
export function summaryFacts(r, cur = '$') {
  const c = r.current, p = r.previous;
  const f = {
    week: `${isoDay(c.start)} to ${isoDay(c.end)}`,
    currency: cur,
    revenue: +c.revenue.toFixed(2), revenue_wow: fmtPct(r.change('revenue')),
    orders: c.orders, orders_wow: fmtPct(r.change('orders')),
    aov: +c.aov.toFixed(2), aov_wow: fmtPct(r.change('aov')),
    refund_rate: `${(c.refundRate * 100).toFixed(1)}%`, refund_rate_prev: `${(p.refundRate * 100).toFixed(1)}%`,
    new_customers: c.newCustomers, returning_customers: c.returningCustomers,
    top_products: r.topProducts.map((t) => ({ name: t.name, revenue: +t.revenue.toFixed(2), wow: fmtPct(t.change) })),
    top_refunded_products: r.refundsByProduct.slice(0, 3).map(([name, v]) => ({ name, refunded: +v.toFixed(2) })),
  };
  if (r.hasAdData) Object.assign(f, { ad_spend: +c.adSpend.toFixed(2), ad_spend_wow: fmtPct(r.change('adSpend')), roas: c.roas && +c.roas.toFixed(2), roas_prev: p.roas && +p.roas.toFixed(2), cac: c.cac && +c.cac.toFixed(2) });
  return f;
}

export const LLM_PROMPT = (facts) => `You are an ecommerce operator writing the executive summary of a weekly business review.
Write 4-6 short bullet points for the founder. Lead with what changed and why it matters, then one or two
concrete actions for next week. Use only the numbers below; do not invent data. No preamble, bullets only,
each starting with "- ".

DATA:
${JSON.stringify(facts, null, 2)}`;

export const parseBullets = (text) =>
  text.split('\n').map((l) => l.trim().replace(/^[-*•]\s*/, '').trim()).filter(Boolean);

// Calls the provider directly from the browser with the user's own key. The key is never stored.
export async function llmSummary(review, { provider, apiKey, model, currency = '$', fetchImpl = fetch }) {
  const prompt = LLM_PROMPT(summaryFacts(review, currency));
  let text;
  if (provider === 'anthropic') {
    const res = await fetchImpl('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'x-api-key': apiKey,
        'anthropic-version': '2023-06-01',
        'anthropic-dangerous-direct-browser-access': 'true',
        'content-type': 'application/json',
      },
      body: JSON.stringify({ model: model || 'claude-sonnet-4-5', max_tokens: 600, messages: [{ role: 'user', content: prompt }] }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data?.error?.message || `Anthropic API error ${res.status}`);
    text = (data.content || []).map((b) => b.text || '').join('');
  } else {
    const res = await fetchImpl('https://api.openai.com/v1/chat/completions', {
      method: 'POST',
      headers: { Authorization: `Bearer ${apiKey}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: model || 'gpt-4o-mini', temperature: 0.2, messages: [{ role: 'user', content: prompt }] }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data?.error?.message || `OpenAI API error ${res.status}`);
    text = data.choices?.[0]?.message?.content || '';
  }
  const bullets = parseBullets(text);
  if (!bullets.length) throw new Error('The model returned an empty summary.');
  return bullets;
}
