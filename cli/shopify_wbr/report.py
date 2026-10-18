"""Render a Review as a single self-contained HTML file (no external assets)."""

from __future__ import annotations

from datetime import datetime
from html import escape

from .metrics import Review, WeekMetrics

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

CSS = """
*{box-sizing:border-box}body{margin:0;background:#f5f6f8;color:#111827;font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:980px;margin:0 auto;padding:32px 24px 48px}
header{display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:20px}
h1{font-size:22px;margin:0}h2{font-size:15px;margin:0 0 12px;color:#374151}
.muted{color:#6b7280}.small{font-size:12px}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:12px}
.card{background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:16px}
.kpi .label{font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:.04em}
.kpi .value{font-size:24px;font-weight:650;margin:4px 0 2px}
.badge{display:inline-block;font-size:12px;font-weight:600;padding:1px 8px;border-radius:999px}
.up{background:#dcfce7;color:#166534}.down{background:#fee2e2;color:#991b1b}.flat{background:#f3f4f6;color:#4b5563}
.row{display:grid;grid-template-columns:3fr 2fr;gap:12px;margin-bottom:12px}
ul.summary{margin:0;padding-left:18px}ul.summary li{margin:4px 0}
table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:8px 6px;border-bottom:1px solid #f0f1f3}
th{font-size:12px;color:#6b7280;font-weight:600;text-transform:uppercase;letter-spacing:.04em}td.num,th.num{text-align:right}
.legend span{display:inline-flex;align-items:center;gap:6px;margin-right:14px;font-size:12px;color:#6b7280}
.legend i{width:10px;height:10px;border-radius:2px;display:inline-block}
footer{margin-top:24px;font-size:12px;color:#9ca3af}
@media print{body{background:#fff}.wrap{padding:0}.card{break-inside:avoid}}
"""


def _money(x: float, cur: str, decimals: int = 0) -> str:
    return f"{cur}{x:,.{decimals}f}"


def _badge(change: float | None, invert: bool = False, as_points: float | None = None) -> str:
    if as_points is not None:
        if abs(as_points) < 0.05:
            return '<span class="badge flat">±0.0 pp</span>'
        good = (as_points < 0) if invert else (as_points > 0)
        return f'<span class="badge {"up" if good else "down"}">{as_points:+.1f} pp</span>'
    if change is None:
        return '<span class="badge flat">new</span>'
    if abs(change) < 0.005:
        return '<span class="badge flat">±0%</span>'
    good = (change < 0) if invert else (change > 0)
    return f'<span class="badge {"up" if good else "down"}">{change:+.1%}</span>'


def _kpi(label: str, value: str, badge: str) -> str:
    return (
        f'<div class="card kpi"><div class="label">{label}</div>'
        f'<div class="value">{value}</div>{badge} <span class="small muted">vs last week</span></div>'
    )


def _daily_chart(cur: WeekMetrics, prev: WeekMetrics, cur_sym: str) -> str:
    w, h, pad_l, pad_b, pad_t = 540, 210, 44, 24, 10
    top = max(max(cur.daily_revenue), max(prev.daily_revenue), 1) * 1.1
    slot = (w - pad_l) / 7
    bw = slot * 0.32
    parts = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="Daily revenue">']
    for i in range(5):
        y = pad_t + (h - pad_b - pad_t) * i / 4
        val = top * (1 - i / 4)
        parts.append(f'<line x1="{pad_l}" x2="{w}" y1="{y:.1f}" y2="{y:.1f}" stroke="#f0f1f3"/>')
        parts.append(f'<text x="{pad_l-6}" y="{y+4:.1f}" font-size="10" fill="#9ca3af" text-anchor="end">{cur_sym}{val/1000:.1f}k</text>')
    for d in range(7):
        x0 = pad_l + d * slot + slot * 0.16
        for j, (vals, color) in enumerate(((prev.daily_revenue, "#cbd5e1"), (cur.daily_revenue, "#4f46e5"))):
            bh = (h - pad_b - pad_t) * vals[d] / top
            parts.append(f'<rect x="{x0 + j*bw:.1f}" y="{h-pad_b-bh:.1f}" width="{bw-2:.1f}" height="{bh:.1f}" rx="2" fill="{color}"/>')
        parts.append(f'<text x="{pad_l + d*slot + slot/2:.1f}" y="{h-6}" font-size="11" fill="#6b7280" text-anchor="middle">{DAYS[d]}</text>')
    parts.append("</svg>")
    return "".join(parts)


def _trend_chart(review: Review, cur_sym: str) -> str:
    pts = review.trend
    w, h, pad_l, pad_b, pad_t, pad_r = 360, 210, 44, 24, 10, 20
    if len(pts) < 2:
        return '<p class="muted small">Not enough history for a trend yet.</p>'
    top = max(v for _, v in pts) * 1.15 or 1
    step = (w - pad_l - pad_r - 8) / (len(pts) - 1)
    coords = [(pad_l + 8 + i * step, pad_t + (h - pad_b - pad_t) * (1 - v / top)) for i, (_, v) in enumerate(pts)]
    path = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(coords))
    area = path + f" L{coords[-1][0]:.1f},{h-pad_b} L{coords[0][0]:.1f},{h-pad_b} Z"
    parts = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="Weekly revenue trend">']
    for i in range(5):
        y = pad_t + (h - pad_b - pad_t) * i / 4
        parts.append(f'<line x1="{pad_l}" x2="{w}" y1="{y:.1f}" y2="{y:.1f}" stroke="#f0f1f3"/>')
        parts.append(f'<text x="{pad_l-6}" y="{y+4:.1f}" font-size="10" fill="#9ca3af" text-anchor="end">{cur_sym}{top*(1-i/4)/1000:.0f}k</text>')
    parts.append(f'<path d="{area}" fill="#eef2ff"/><path d="{path}" fill="none" stroke="#4f46e5" stroke-width="2"/>')
    for i, ((x, y), (ws, _)) in enumerate(zip(coords, pts)):
        last = i == len(coords) - 1
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{4 if last else 2.5}" fill="#4f46e5"/>')
        parts.append(f'<text x="{x:.1f}" y="{h-6}" font-size="10" fill="#6b7280" text-anchor="middle">{ws:%d %b}</text>')
    parts.append("</svg>")
    return "".join(parts)


def render_html(
    review: Review,
    summary: list[str],
    summary_source: str = "rules",
    currency: str = "$",
    sample: bool = False,
) -> str:
    c, p = review.current, review.previous
    kpis = [
        _kpi("Revenue", _money(c.revenue, currency), _badge(review.change("revenue"))),
        _kpi("Orders", f"{c.orders:,}", _badge(review.change("orders"))),
        _kpi("AOV", _money(c.aov, currency, 2), _badge(review.change("aov"))),
        _kpi("Refund rate", f"{c.refund_rate:.1%}", _badge(None, invert=True, as_points=(c.refund_rate - p.refund_rate) * 100)),
        _kpi("Net revenue", _money(c.net_revenue, currency), _badge(review.change("net_revenue"))),
        _kpi("Units sold", f"{c.units:,}", _badge(review.change("units"))),
        _kpi("New customers", f"{c.new_customers:,}", _badge(review.change("new_customers"))),
    ]
    if review.has_ad_data:
        roas = "n/a" if c.roas is None else f"{c.roas:.2f}x"
        kpis.append(_kpi("Blended ROAS", roas, _badge(review.change("roas"))))
    else:
        kpis.append(_kpi("Returning customers", f"{c.returning_customers:,}", _badge(review.change("returning_customers"))))

    rows = "".join(
        f"<tr><td>{i}. {escape(t.name)}</td><td class='num'>{t.units:,}</td>"
        f"<td class='num'>{_money(t.revenue, currency)}</td><td class='num'>{_badge(t.change)}</td></tr>"
        for i, t in enumerate(review.top_products, 1)
    ) or "<tr><td colspan='4' class='muted'>No line items this week.</td></tr>"

    refund_rows = "".join(
        f"<tr><td>{escape(n)}</td><td class='num'>{_money(v, currency)}</td>"
        f"<td class='num'>{(v / c.refunds if c.refunds else 0):.0%}</td></tr>"
        for n, v in review.refunds_by_product[:5]
    ) or "<tr><td colspan='3' class='muted'>No refunds this week.</td></tr>"
    refunds_html = f"""<div class="card"><h2>Refunds by product</h2>
      <table><tr><th>Product</th><th class="num">Refunded</th><th class="num">Share</th></tr>{refund_rows}</table>
      <p class="small muted" style="margin:10px 0 0">Order refunds split across line items by value (exact for single-item orders).</p></div>"""

    ads_html = ""
    if review.has_ad_data:
        ad_rows = "".join(
            f"<tr><td>{escape(ch)}</td><td class='num'>{_money(v, currency)}</td>"
            f"<td class='num'>{(v / c.ad_spend if c.ad_spend else 0):.0%}</td></tr>"
            for ch, v in c.ad_spend_by_channel.items()
        )
        cac = "n/a" if c.cac is None else _money(c.cac, currency, 2)
        ads_html = f"""
        <div class="card"><h2>Ad spend</h2>
          <table><tr><th>Channel</th><th class="num">Spend</th><th class="num">Share</th></tr>{ad_rows}
          <tr><td><b>Total</b></td><td class="num"><b>{_money(c.ad_spend, currency)}</b></td><td class="num">{_badge(review.change('ad_spend'), invert=True)}</td></tr></table>
          <p class="small muted" style="margin:10px 0 0">Cost per new customer: <b>{cac}</b></p>
        </div>"""

    source_note = "Written by an LLM from the numbers on this page." if summary_source == "llm" else "Generated from the numbers on this page (no LLM key set)."
    sample_banner = (
        '<div class="card" style="background:#fffbeb;border-color:#fde68a;margin-bottom:12px">'
        "<b>Sample report.</b> Built from synthetic data in <code>sample/</code>. Not a real store.</div>"
        if sample else ""
    )
    bullets = "".join(f"<li>{escape(b)}</li>" for b in summary)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Weekly Business Review · {escape(review.store_name)} · {c.start:%d %b %Y}</title><style>{CSS}</style></head>
<body><div class="wrap">
<header><div><div class="small muted">Weekly Business Review</div><h1>{escape(review.store_name)}</h1></div>
<div class="muted">{c.start:%a %d %b} – {c.end:%a %d %b %Y}</div></header>
{sample_banner}
<div class="card" style="margin-bottom:12px"><h2>Summary</h2><ul class="summary">{bullets}</ul>
<p class="small muted" style="margin:8px 0 0">{source_note}</p></div>
<div class="grid">{''.join(kpis)}</div>
<div class="row">
  <div class="card"><h2>Daily revenue</h2><div class="legend"><span><i style="background:#4f46e5"></i>This week</span><span><i style="background:#cbd5e1"></i>Last week</span></div>{_daily_chart(c, p, currency)}</div>
  <div class="card"><h2>Weekly revenue trend</h2>{_trend_chart(review, currency)}</div>
</div>
<div class="row">
  <div class="card"><h2>Top products</h2><table><tr><th>Product</th><th class="num">Units</th><th class="num">Revenue</th><th class="num">WoW</th></tr>{rows}</table></div>
  {ads_html or '<div class="card"><h2>Customers</h2><p>New: <b>' + f"{c.new_customers:,}" + '</b><br>Returning: <b>' + f"{c.returning_customers:,}" + '</b></p><p class="small muted">Add <code>--ads ad_spend.csv</code> to see ROAS and cost per new customer.</p></div>'}
</div>
{refunds_html}
<footer>Generated {datetime.now():%Y-%m-%d %H:%M} by shopify-wbr. Revenue = Shopify order total (after discounts, incl. shipping &amp; tax), excluding voided/cancelled orders. Refund rate = refunded value / revenue.</footer>
</div></body></html>
"""
