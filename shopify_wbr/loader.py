"""Parse Shopify orders CSV exports and optional ad spend CSVs.

Shopify's "Export orders" CSV has one row per line item. Order-level fields
(totals, refunds, customer email) are only filled on the first row of each
order, so we group rows by the order ``Name`` (e.g. ``#1001``).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path


@dataclass
class LineItem:
    name: str
    sku: str
    quantity: int
    price: float

    @property
    def revenue(self) -> float:
        return self.quantity * self.price


@dataclass
class Order:
    name: str
    created_at: datetime
    email: str
    financial_status: str
    subtotal: float
    shipping: float
    taxes: float
    discount: float
    total: float
    refunded: float
    line_items: list[LineItem] = field(default_factory=list)

    @property
    def day(self) -> date:
        return self.created_at.date()

    @property
    def is_cancelled_or_voided(self) -> bool:
        return self.financial_status.lower() in {"voided", "cancelled"}


@dataclass
class AdSpend:
    day: date
    channel: str
    spend: float


def _num(value: str | None) -> float:
    if value is None:
        return 0.0
    value = value.strip().replace(",", "").replace("$", "")
    if not value:
        return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0


def _parse_dt(value: str) -> datetime:
    value = value.strip()
    # Shopify exports look like "2026-09-07 14:03:11 +0400"
    for fmt in ("%Y-%m-%d %H:%M:%S %z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(value, fmt)
            return dt.replace(tzinfo=None)  # report in the store's local time
        except ValueError:
            continue
    return datetime.fromisoformat(value).replace(tzinfo=None)


def _get(row: dict, *keys: str) -> str:
    for k in keys:
        if k in row and row[k] is not None:
            return row[k]
    return ""


def load_orders(path: str | Path) -> list[Order]:
    """Load a Shopify orders export into a list of :class:`Order`."""
    orders: dict[str, Order] = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        missing = {"Name", "Created at", "Total"} - set(reader.fieldnames or [])
        if missing:
            raise ValueError(
                f"{path} does not look like a Shopify orders export; missing columns: {sorted(missing)}"
            )
        for row in reader:
            name = row["Name"].strip()
            if not name:
                continue
            order = orders.get(name)
            if order is None:
                order = Order(
                    name=name,
                    created_at=_parse_dt(row["Created at"]),
                    email=_get(row, "Email").strip().lower(),
                    financial_status=_get(row, "Financial Status").strip(),
                    subtotal=_num(_get(row, "Subtotal")),
                    shipping=_num(_get(row, "Shipping")),
                    taxes=_num(_get(row, "Taxes")),
                    discount=_num(_get(row, "Discount Amount")),
                    total=_num(_get(row, "Total")),
                    refunded=_num(_get(row, "Refunded Amount")),
                )
                orders[name] = order
            item_name = _get(row, "Lineitem name").strip()
            if item_name:
                order.line_items.append(
                    LineItem(
                        name=item_name,
                        sku=_get(row, "Lineitem sku").strip(),
                        quantity=int(_num(_get(row, "Lineitem quantity")) or 0),
                        price=_num(_get(row, "Lineitem price")),
                    )
                )
    return sorted(orders.values(), key=lambda o: o.created_at)


def load_ad_spend(path: str | Path) -> list[AdSpend]:
    """Load ad spend. Expected columns: ``date``, ``channel``, ``spend``."""
    rows: list[AdSpend] = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        cols = {c.lower().strip(): c for c in (reader.fieldnames or [])}
        if not {"date", "spend"} <= set(cols):
            raise ValueError(f"{path} needs at least 'date' and 'spend' columns")
        for row in reader:
            rows.append(
                AdSpend(
                    day=_parse_dt(row[cols["date"]]).date(),
                    channel=(row[cols["channel"]].strip() if "channel" in cols else "Ads") or "Ads",
                    spend=_num(row[cols["spend"]]),
                )
            )
    return rows
