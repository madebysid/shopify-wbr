"""Generate SYNTHETIC sample data in Shopify's orders-export format.

Everything here is made up: a fictional store, fake products and
example.com customer emails. Deterministic (seeded) so the sample report is
reproducible.

    python cli/scripts/generate_sample_data.py
"""

from __future__ import annotations

import csv
import random
from datetime import date, datetime, timedelta
from pathlib import Path

OUT = Path(__file__).resolve().parents[2] / "site" / "sample"
START = date(2026, 8, 24)  # Monday
WEEKS = 8

# name, sku, price, popularity weight, base refund probability
PRODUCTS = [
    ("Linen Throw Blanket", "HOME-LTB-01", 64.00, 9, 0.03),
    ("Ceramic Pour-Over Set", "KIT-CPS-02", 48.00, 8, 0.04),
    ("Stoneware Mug (Set of 4)", "KIT-SM4-03", 36.00, 10, 0.05),
    ("Cotton Waffle Bath Towel", "BATH-CWT-04", 29.00, 9, 0.02),
    ("Glass Storage Jars (6 pc)", "KIT-GSJ-05", 42.00, 6, 0.06),
    ("Beeswax Candle Trio", "HOME-BCT-06", 32.00, 7, 0.02),
    ("Walnut Serving Board", "KIT-WSB-07", 58.00, 5, 0.03),
    ("Merino Lounge Socks", "APP-MLS-08", 18.00, 8, 0.02),
    ("Rattan Storage Basket", "HOME-RSB-09", 54.00, 4, 0.04),
    ("Cast Iron Skillet 10in", "KIT-CIS-10", 72.00, 4, 0.03),
]

FIELDS = [
    "Name", "Email", "Financial Status", "Paid at", "Fulfillment Status", "Accepts Marketing", "Currency",
    "Subtotal", "Shipping", "Taxes", "Total", "Discount Code", "Discount Amount", "Created at",
    "Lineitem quantity", "Lineitem name", "Lineitem price", "Lineitem sku", "Refunded Amount", "Source",
]

DAY_FACTOR = [0.95, 0.9, 0.92, 1.0, 1.05, 1.2, 1.15]  # Mon..Sun


def main() -> None:
    rng = random.Random(42)
    OUT.mkdir(exist_ok=True)
    customers: list[str] = []
    order_no = 1001
    rows: list[dict] = []
    ad_rows: list[dict] = []

    for day_i in range(WEEKS * 7):
        d = START + timedelta(days=day_i)
        week = day_i // 7
        growth = 1 + 0.03 * week + (0.12 if week == WEEKS - 1 else 0)  # promo push in the last week
        n_orders = max(5, int(rng.gauss(48, 5) * growth * DAY_FACTOR[d.weekday()]))

        meta = 780 * growth * DAY_FACTOR[d.weekday()] * rng.uniform(0.9, 1.1)
        google = 400 * (1.05 if week == WEEKS - 1 else 1) * rng.uniform(0.9, 1.1)
        tiktok = (150 + 20 * week) * rng.uniform(0.8, 1.2)
        for ch, s in (("Meta", meta), ("Google", google), ("TikTok", tiktok)):
            ad_rows.append({"date": d.isoformat(), "channel": ch, "spend": f"{s:.2f}"})

        for _ in range(n_orders):
            if customers and rng.random() < 0.32:
                email = rng.choice(customers)
            else:
                email = f"customer{len(customers) + 1:05d}@example.com"
                customers.append(email)
            ts = datetime.combine(d, datetime.min.time()) + timedelta(seconds=rng.randint(7 * 3600, 23 * 3600))
            k = 1 if rng.random() < 0.62 else rng.choice([2, 2, 3])
            picks = rng.choices(PRODUCTS, weights=[p[3] for p in PRODUCTS], k=k)
            items = {}
            for p in picks:
                items.setdefault(p, 0)
                items[p] += 1
            subtotal = sum(p[2] * q for p, q in items.items())
            code, disc = "", 0.0
            if rng.random() < (0.35 if week == WEEKS - 1 else 0.15):
                code, disc = "WELCOME10", round(subtotal * 0.10, 2)
            shipping = 0.0 if subtotal >= 75 else 6.95
            taxes = round((subtotal - disc) * 0.05, 2)
            total = round(subtotal - disc + shipping + taxes, 2)

            refunded = 0.0
            for p, q in items.items():
                prob = p[4]
                if p[1] == "KIT-GSJ-05" and week == WEEKS - 1:
                    prob = 0.22  # sample "issue": breakage on glass jars in the last week
                if rng.random() < prob:
                    refunded += p[2] * q
            refunded = round(min(refunded, total), 2)
            status = "paid" if refunded == 0 else ("refunded" if refunded >= total - 0.01 else "partially_refunded")
            if rng.random() < 0.004:
                status, refunded = "voided", 0.0

            for i, (p, q) in enumerate(items.items()):
                first = i == 0
                rows.append({
                    "Name": f"#{order_no}",
                    "Email": email if first else "",
                    "Financial Status": status if first else "",
                    "Paid at": ts.strftime("%Y-%m-%d %H:%M:%S +0400") if first and status != "voided" else "",
                    "Fulfillment Status": "fulfilled" if first else "",
                    "Accepts Marketing": rng.choice(["yes", "no"]) if first else "",
                    "Currency": "USD" if first else "",
                    "Subtotal": f"{subtotal:.2f}" if first else "",
                    "Shipping": f"{shipping:.2f}" if first else "",
                    "Taxes": f"{taxes:.2f}" if first else "",
                    "Total": f"{total:.2f}" if first else "",
                    "Discount Code": code if first else "",
                    "Discount Amount": f"{disc:.2f}" if first else "",
                    "Created at": ts.strftime("%Y-%m-%d %H:%M:%S +0400"),
                    "Lineitem quantity": q,
                    "Lineitem name": p[0],
                    "Lineitem price": f"{p[2]:.2f}",
                    "Lineitem sku": p[1],
                    "Refunded Amount": f"{refunded:.2f}" if first else "",
                    "Source": "web" if first else "",
                })
            order_no += 1

    # Shopify exports newest first
    rows.sort(key=lambda r: (r["Created at"], r["Name"]), reverse=True)
    with open(OUT / "orders_sample.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    with open(OUT / "ad_spend_sample.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date", "channel", "spend"])
        w.writeheader()
        w.writerows(ad_rows)
    print(f"wrote {order_no - 1001} orders, {len(rows)} rows, {len(ad_rows)} ad rows to {OUT}")


if __name__ == "__main__":
    main()
