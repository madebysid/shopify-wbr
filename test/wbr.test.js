import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  parseCSV, loadOrders, loadAdSpend, buildReview, ruleSummary, llmSummary, summaryFacts,
  latestCompleteWeekEnd, dayNum, isoDay, weekday, pctChange,
} from '../site/wbr.js';

const ORDERS = `Name,Email,Financial Status,Subtotal,Shipping,Taxes,Total,Discount Amount,Created at,Lineitem quantity,Lineitem name,Lineitem price,Lineitem sku,Refunded Amount
#1001,a@example.com,paid,100.00,0.00,0.00,100.00,0.00,2026-10-05 10:00:00 +0400,2,Mug,50.00,MUG,0.00
#1002,b@example.com,paid,40.00,0.00,0.00,40.00,0.00,2026-10-06 10:00:00 +0400,1,Towel,40.00,TWL,0.00
#1003,a@example.com,partially_refunded,150.00,0.00,0.00,150.00,0.00,2026-10-12 09:00:00 +0400,1,Mug,50.00,MUG,50.00
#1003,,,,,,,,2026-10-12 09:00:00 +0400,1,Blanket,100.00,BLK,
#1004,c@example.com,paid,60.00,0.00,0.00,60.00,0.00,2026-10-14 12:00:00 +0400,3,Towel,20.00,TWL,0.00
#1005,d@example.com,voided,999.00,0.00,0.00,999.00,0.00,2026-10-15 12:00:00 +0400,1,Blanket,999.00,BLK,0.00
#1006,d@example.com,paid,90.00,0.00,0.00,90.00,0.00,2026-10-18 20:00:00 +0400,1,Blanket,90.00,BLK,0.00
`;
const ADS = `date,channel,spend
2026-10-06,Meta,20
2026-10-13,Meta,60
2026-10-14,Google,40
`;
const close = (a, b) => assert.ok(Math.abs(a - b) < 1e-9, `${a} != ${b}`);

test('CSV parser handles quotes, commas, CRLF and BOM', () => {
  const { header, records } = parseCSV('\ufeffa,b\r\n"x, y","he said ""hi"""\r\n');
  assert.deepEqual(header, ['a', 'b']);
  assert.deepEqual(records, [{ a: 'x, y', b: 'he said "hi"' }]);
});

test('dates are timezone-free day numbers, weeks start Monday', () => {
  const d = dayNum('2026-10-18 22:39:40 +0400');
  assert.equal(isoDay(d), '2026-10-18');
  assert.equal(weekday(d), 6); // Sunday
});

test('groups line items by order', () => {
  const o = loadOrders(ORDERS);
  assert.deepEqual(o.map((x) => x.name), ['#1001', '#1002', '#1003', '#1004', '#1005', '#1006']);
  assert.equal(o[2].total, 150);
  assert.equal(o[2].refunded, 50);
  assert.deepEqual(o[2].lineItems.map((l) => l.name), ['Mug', 'Blanket']);
});

test('rejects files that are not Shopify order exports', () => {
  assert.throws(() => loadOrders('foo,bar\n1,2\n'), /Shopify orders export/);
  assert.throws(() => loadAdSpend('foo,bar\n1,2\n'), /date/);
});

test('weekly metrics match the Python CLI', () => {
  const r = buildReview(loadOrders(ORDERS), loadAdSpend(ADS));
  const c = r.current, p = r.previous;
  assert.equal(isoDay(c.start), '2026-10-12');
  assert.equal(isoDay(c.end), '2026-10-18');
  assert.equal(c.orders, 3); // voided excluded
  close(c.revenue, 300);
  close(c.aov, 100);
  close(c.refunds, 50);
  close(c.refundRate, 50 / 300);
  assert.equal(c.units, 6);
  assert.equal(p.orders, 2);
  close(p.revenue, 140);
  close(r.change('revenue'), 300 / 140 - 1);
  assert.equal(c.newCustomers, 2);
  assert.equal(c.returningCustomers, 1);
  close(c.adSpend, 100);
  close(c.roas, 3);
  close(c.cac, 50);
  assert.deepEqual(c.adSpendByChannel, [['Meta', 60], ['Google', 40]]);
});

test('top products and refund attribution', () => {
  const r = buildReview(loadOrders(ORDERS));
  assert.equal(r.topProducts[0].name, 'Blanket');
  close(r.topProducts[0].revenue, 190);
  assert.equal(r.topProducts[0].change, null);
  const refunds = Object.fromEntries(r.refundsByProduct);
  close(refunds.Mug, (50 * 50) / 150);
  close(refunds.Blanket, (50 * 100) / 150);
  assert.equal(r.hasAdData, false);
  assert.equal(r.current.roas, null);
});

test('explicit week and latest complete week', () => {
  const orders = loadOrders(ORDERS);
  assert.equal(isoDay(latestCompleteWeekEnd(orders)), '2026-10-18');
  const r = buildReview(orders, [], { weekEnding: dayNum('2026-10-11') });
  assert.equal(r.current.orders, 2);
  assert.equal(r.previous.orders, 0);
  assert.equal(r.change('revenue'), null);
  assert.equal(pctChange(5, 0), null);
});

test('rule-based summary mentions the key numbers', () => {
  const text = ruleSummary(buildReview(loadOrders(ORDERS))).join(' ');
  assert.match(text, /\$300/);
  assert.match(text, /3 orders/);
  assert.match(text, /Blanket/);
});

test('LLM summary sends only aggregates and parses bullets', async () => {
  const r = buildReview(loadOrders(ORDERS));
  let sent;
  const fetchImpl = async (url, init) => {
    sent = { url, body: JSON.parse(init.body), headers: init.headers };
    return { ok: true, json: async () => ({ content: [{ text: '- Revenue up.\n- Fix Mug refunds.' }] }) };
  };
  const bullets = await llmSummary(r, { provider: 'anthropic', apiKey: 'k', fetchImpl });
  assert.deepEqual(bullets, ['Revenue up.', 'Fix Mug refunds.']);
  assert.match(sent.url, /anthropic\.com/);
  assert.equal(sent.headers['anthropic-dangerous-direct-browser-access'], 'true');
  const prompt = sent.body.messages[0].content;
  assert.ok(!prompt.includes('@example.com'), 'no customer emails in prompt');
  assert.equal(summaryFacts(r).orders, 3);
});

test('sample data: JS matches Python reference numbers', () => {
  const orders = loadOrders(readFileSync(new URL('../site/sample/orders_sample.csv', import.meta.url), 'utf8'));
  const ads = loadAdSpend(readFileSync(new URL('../site/sample/ad_spend_sample.csv', import.meta.url), 'utf8'));
  const r = buildReview(orders, ads);
  assert.equal(r.current.orders, 462);
  assert.equal(Math.round(r.current.revenue), 32798);
});
