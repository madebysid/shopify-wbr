"""Command line entry point: ``wbr orders.csv [--ads ad_spend.csv] [-o report.html] [--pdf]``."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from . import __version__
from .loader import load_ad_spend, load_orders
from .metrics import build_review
from .pdf import html_to_pdf
from .report import render_html
from .summary import summarize


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="wbr", description="Generate a weekly business review from a Shopify orders CSV export."
    )
    ap.add_argument("orders", help="Shopify orders export (Orders > Export > CSV)")
    ap.add_argument("--ads", help="optional ad spend CSV with columns date,channel,spend")
    ap.add_argument("-o", "--out", default="wbr.html", help="output HTML path (default: wbr.html)")
    ap.add_argument("--pdf", action="store_true", help="also write a PDF next to the HTML (needs Chrome)")
    ap.add_argument("--week-ending", type=date.fromisoformat, help="Sunday that ends the week (default: last complete week)")
    ap.add_argument("--store", default="My Store", help="store name shown in the report")
    ap.add_argument("--currency", default="$", help="currency symbol (default: $)")
    ap.add_argument("--top", type=int, default=5, help="number of top products (default: 5)")
    ap.add_argument("--no-llm", action="store_true", help="never call an LLM, even if a key is set")
    ap.add_argument("--sample", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--version", action="version", version=f"shopify-wbr {__version__}")
    args = ap.parse_args(argv)

    try:
        orders = load_orders(args.orders)
        ads = load_ad_spend(args.ads) if args.ads else None
        review = build_review(orders, ads, week_ending=args.week_ending, store_name=args.store, top_n=args.top)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    bullets, source = summarize(review, args.currency, use_llm=not args.no_llm)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_html(review, bullets, source, args.currency, sample=args.sample), encoding="utf-8")
    c = review.current
    print(f"Week {c.start} to {c.end}: revenue {args.currency}{c.revenue:,.0f}, {c.orders} orders, AOV {args.currency}{c.aov:,.2f}")
    print(f"Wrote {out}")
    if args.pdf:
        pdf = out.with_suffix(".pdf")
        if html_to_pdf(out, pdf):
            print(f"Wrote {pdf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
