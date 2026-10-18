"""Weekly business review metrics.

Weeks run Monday to Sunday. Everything is computed from the orders export, so
"revenue" means Shopify's order ``Total`` (after discounts, including shipping
and tax) for orders that were not voided or cancelled.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from .loader import AdSpend, Order


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def latest_complete_week_end(orders: list[Order]) -> date:
    """The last Sunday covered by the data (a week is complete if its Sunday is in range)."""
    if not orders:
        raise ValueError("no orders to report on")
    last = max(o.day for o in orders)
    if last.weekday() == 6:
        return last
    return last - timedelta(days=last.weekday() + 1)


def pct_change(current: float, previous: float) -> float | None:
    if previous == 0:
        return None
    return (current - previous) / previous


@dataclass
class ProductRow:
    name: str
    units: int
    revenue: float
    prev_revenue: float

    @property
    def change(self) -> float | None:
        return pct_change(self.revenue, self.prev_revenue)


@dataclass
class WeekMetrics:
    start: date
    end: date
    revenue: float = 0.0
    refunds: float = 0.0
    orders: int = 0
    refunded_orders: int = 0
    units: int = 0
    discounts: float = 0.0
    new_customers: int = 0
    returning_customers: int = 0
    ad_spend: float = 0.0
    ad_spend_by_channel: dict[str, float] = field(default_factory=dict)
    daily_revenue: list[float] = field(default_factory=lambda: [0.0] * 7)

    @property
    def net_revenue(self) -> float:
        return self.revenue - self.refunds

    @property
    def aov(self) -> float:
        return self.revenue / self.orders if self.orders else 0.0

    @property
    def refund_rate(self) -> float:
        """Refunded value as a share of revenue."""
        return self.refunds / self.revenue if self.revenue else 0.0

    @property
    def refunded_order_rate(self) -> float:
        return self.refunded_orders / self.orders if self.orders else 0.0

    @property
    def roas(self) -> float | None:
        """Blended ROAS (a.k.a. MER): revenue / total ad spend."""
        return self.revenue / self.ad_spend if self.ad_spend else None

    @property
    def cac(self) -> float | None:
        """Blended cost per new customer."""
        if not self.ad_spend or not self.new_customers:
            return None
        return self.ad_spend / self.new_customers


@dataclass
class Review:
    store_name: str
    current: WeekMetrics
    previous: WeekMetrics
    top_products: list[ProductRow]
    trend: list[tuple[date, float]]  # (week start, revenue) for recent weeks
    has_ad_data: bool
    refunds_by_product: list[tuple[str, float]] = field(default_factory=list)

    def change(self, attr: str) -> float | None:
        cur, prev = getattr(self.current, attr), getattr(self.previous, attr)
        if cur is None or prev is None:
            return None
        return pct_change(cur, prev)


def _week_metrics(
    orders: list[Order],
    ads: list[AdSpend],
    start: date,
    first_seen: dict[str, date],
) -> WeekMetrics:
    end = start + timedelta(days=6)
    m = WeekMetrics(start=start, end=end)
    customers_new: set[str] = set()
    customers_returning: set[str] = set()
    for o in orders:
        if not (start <= o.day <= end) or o.is_cancelled_or_voided:
            continue
        m.orders += 1
        m.revenue += o.total
        m.refunds += o.refunded
        m.discounts += o.discount
        m.units += sum(li.quantity for li in o.line_items)
        m.daily_revenue[(o.day - start).days] += o.total
        if o.refunded > 0:
            m.refunded_orders += 1
        if o.email:
            if first_seen.get(o.email, o.day) >= start:
                customers_new.add(o.email)
            else:
                customers_returning.add(o.email)
    m.new_customers = len(customers_new)
    m.returning_customers = len(customers_returning - customers_new)
    by_channel: dict[str, float] = defaultdict(float)
    for a in ads:
        if start <= a.day <= end:
            m.ad_spend += a.spend
            by_channel[a.channel] += a.spend
    m.ad_spend_by_channel = dict(sorted(by_channel.items(), key=lambda kv: -kv[1]))
    return m


def _product_revenue(orders: list[Order], start: date) -> dict[str, tuple[int, float]]:
    end = start + timedelta(days=6)
    out: dict[str, list[float]] = defaultdict(lambda: [0, 0.0])
    for o in orders:
        if start <= o.day <= end and not o.is_cancelled_or_voided:
            for li in o.line_items:
                out[li.name][0] += li.quantity
                out[li.name][1] += li.revenue
    return {k: (int(v[0]), v[1]) for k, v in out.items()}


def _refunds_by_product(orders: list[Order], start: date) -> list[tuple[str, float]]:
    """Attribute each order's refund to its line items in proportion to their value.

    Shopify's orders export only has the refunded amount per order, so this is
    an estimate; it is exact for single-item orders.
    """
    end = start + timedelta(days=6)
    out: dict[str, float] = defaultdict(float)
    for o in orders:
        if not (start <= o.day <= end) or o.refunded <= 0 or o.is_cancelled_or_voided:
            continue
        gross = sum(li.revenue for li in o.line_items)
        if gross <= 0:
            continue
        for li in o.line_items:
            out[li.name] += o.refunded * li.revenue / gross
    return sorted(out.items(), key=lambda kv: -kv[1])


def build_review(
    orders: list[Order],
    ads: list[AdSpend] | None = None,
    week_ending: date | None = None,
    store_name: str = "Store",
    top_n: int = 5,
    trend_weeks: int = 8,
) -> Review:
    ads = ads or []
    end = week_ending or latest_complete_week_end(orders)
    start = week_start(end)
    prev_start = start - timedelta(days=7)

    first_seen: dict[str, date] = {}
    for o in orders:
        if o.email and not o.is_cancelled_or_voided:
            first_seen[o.email] = min(first_seen.get(o.email, o.day), o.day)

    current = _week_metrics(orders, ads, start, first_seen)
    previous = _week_metrics(orders, ads, prev_start, first_seen)

    cur_p = _product_revenue(orders, start)
    prev_p = _product_revenue(orders, prev_start)
    top = sorted(cur_p.items(), key=lambda kv: -kv[1][1])[:top_n]
    top_products = [
        ProductRow(name=n, units=u, revenue=r, prev_revenue=prev_p.get(n, (0, 0.0))[1])
        for n, (u, r) in top
    ]

    trend = []
    for i in range(trend_weeks - 1, -1, -1):
        ws = start - timedelta(days=7 * i)
        we = ws + timedelta(days=6)
        rev = sum(o.total for o in orders if ws <= o.day <= we and not o.is_cancelled_or_voided)
        trend.append((ws, rev))
    # drop leading weeks with no data at all
    while trend and trend[0][1] == 0:
        trend.pop(0)

    return Review(
        store_name=store_name,
        current=current,
        previous=previous,
        top_products=top_products,
        trend=trend,
        has_ad_data=bool(ads),
        refunds_by_product=_refunds_by_product(orders, start),
    )
