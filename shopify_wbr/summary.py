"""Executive summary: rule-based by default, LLM-written if an API key is set.

Set ``OPENAI_API_KEY`` or ``ANTHROPIC_API_KEY`` to get an LLM-written summary.
Override the model with ``WBR_MODEL``. Without a key (or if the call fails)
the tool falls back to a deterministic summary, so reports always build.
"""

from __future__ import annotations

import json
import os
import urllib.request

from .metrics import Review

OPENAI_DEFAULT_MODEL = "gpt-4o-mini"
ANTHROPIC_DEFAULT_MODEL = "claude-sonnet-4-5"


def _fmt_pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x:+.1%}"


def facts(review: Review, currency: str = "$") -> dict:
    c, p = review.current, review.previous
    d = {
        "store": review.store_name,
        "week": f"{c.start:%Y-%m-%d} to {c.end:%Y-%m-%d}",
        "revenue": round(c.revenue, 2),
        "revenue_wow": _fmt_pct(review.change("revenue")),
        "orders": c.orders,
        "orders_wow": _fmt_pct(review.change("orders")),
        "aov": round(c.aov, 2),
        "aov_wow": _fmt_pct(review.change("aov")),
        "refund_rate": f"{c.refund_rate:.1%}",
        "refund_rate_prev": f"{p.refund_rate:.1%}",
        "new_customers": c.new_customers,
        "returning_customers": c.returning_customers,
        "top_products": [
            {"name": t.name, "revenue": round(t.revenue, 2), "wow": _fmt_pct(t.change)}
            for t in review.top_products
        ],
        "top_refunded_products": [
            {"name": n, "refunded": round(v, 2)} for n, v in review.refunds_by_product[:3]
        ],
        "currency": currency,
    }
    if review.has_ad_data:
        d.update(
            ad_spend=round(c.ad_spend, 2),
            ad_spend_wow=_fmt_pct(review.change("ad_spend")),
            roas=None if c.roas is None else round(c.roas, 2),
            roas_prev=None if p.roas is None else round(p.roas, 2),
            cac=None if c.cac is None else round(c.cac, 2),
        )
    return d


def rule_based_summary(review: Review, currency: str = "$") -> list[str]:
    c, p = review.current, review.previous
    out: list[str] = []
    rc = review.change("revenue")
    direction = "up" if (rc or 0) >= 0 else "down"
    if rc is None:
        out.append(f"Revenue was {currency}{c.revenue:,.0f} from {c.orders} orders (no prior week to compare).")
    else:
        out.append(
            f"Revenue was {currency}{c.revenue:,.0f}, {direction} {abs(rc):.1%} week over week, "
            f"on {c.orders} orders ({_fmt_pct(review.change('orders'))}) at an AOV of {currency}{c.aov:,.2f} "
            f"({_fmt_pct(review.change('aov'))})."
        )
    delta_pp = (c.refund_rate - p.refund_rate) * 100
    if abs(delta_pp) >= 1:
        word = "rose" if delta_pp > 0 else "fell"
        out.append(
            f"Refund rate {word} to {c.refund_rate:.1%} from {p.refund_rate:.1%} "
            f"({c.refunded_orders} orders with refunds)."
        )
        if delta_pp > 0 and review.refunds_by_product and c.refunds:
            name, amt = review.refunds_by_product[0]
            out.append(
                f"{name} drove the most refunds ({currency}{amt:,.0f}, {amt / c.refunds:.0%} of refunded value); "
                "check reviews and return reasons for that SKU."
            )
    else:
        out.append(f"Refund rate held at {c.refund_rate:.1%} of revenue.")
    if review.top_products:
        t = review.top_products[0]
        share = t.revenue / c.revenue if c.revenue else 0
        out.append(f"Top product: {t.name} with {currency}{t.revenue:,.0f} ({share:.0%} of revenue, {_fmt_pct(t.change)} WoW).")
        movers = [x for x in review.top_products if x.change is not None]
        if movers:
            worst = min(movers, key=lambda x: x.change)
            if worst.change < -0.15:
                out.append(f"Watch {worst.name}: revenue {_fmt_pct(worst.change)} vs last week.")
    if review.has_ad_data and c.roas is not None:
        roas_line = f"Blended ROAS was {c.roas:.2f}x on {currency}{c.ad_spend:,.0f} of ad spend"
        if p.roas is not None:
            roas_line += f" (last week {p.roas:.2f}x)"
        if c.cac is not None:
            roas_line += f"; cost per new customer {currency}{c.cac:,.2f}"
        out.append(roas_line + ".")
    out.append(f"{c.new_customers} new and {c.returning_customers} returning customers ordered this week.")
    return out


PROMPT = """You are an ecommerce operator writing the executive summary of a weekly business review.
Write 4-6 short bullet points for the founder. Lead with what changed and why it matters, then one or two
concrete actions for next week. Use only the numbers below; do not invent data. No preamble, bullets only,
each starting with "- ".

DATA:
{data}
"""


def _post(url: str, headers: dict, body: dict, timeout: int = 30) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _parse_bullets(text: str) -> list[str]:
    lines = [ln.strip().lstrip("-*• ").strip() for ln in text.splitlines()]
    return [ln for ln in lines if ln]


def llm_summary(review: Review, currency: str = "$") -> list[str] | None:
    """Return LLM bullets, or None if no key is configured or the call fails."""
    prompt = PROMPT.format(data=json.dumps(facts(review, currency), indent=2))
    model = os.environ.get("WBR_MODEL")
    try:
        if os.environ.get("ANTHROPIC_API_KEY"):
            data = _post(
                "https://api.anthropic.com/v1/messages",
                {
                    "x-api-key": os.environ["ANTHROPIC_API_KEY"],
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                {
                    "model": model or ANTHROPIC_DEFAULT_MODEL,
                    "max_tokens": 600,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            text = "".join(b.get("text", "") for b in data.get("content", []))
        elif os.environ.get("OPENAI_API_KEY"):
            data = _post(
                "https://api.openai.com/v1/chat/completions",
                {
                    "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
                    "Content-Type": "application/json",
                },
                {
                    "model": model or OPENAI_DEFAULT_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
                },
            )
            text = data["choices"][0]["message"]["content"]
        else:
            return None
    except Exception as exc:  # network errors, bad keys, rate limits...
        print(f"[shopify-wbr] LLM summary failed ({exc.__class__.__name__}); using rule-based summary.")
        return None
    bullets = _parse_bullets(text)
    return bullets or None


def summarize(review: Review, currency: str = "$", use_llm: bool = True) -> tuple[list[str], str]:
    """Return (bullets, source) where source is 'llm' or 'rules'."""
    if use_llm:
        bullets = llm_summary(review, currency)
        if bullets:
            return bullets, "llm"
    return rule_based_summary(review, currency), "rules"
