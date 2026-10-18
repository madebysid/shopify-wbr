from datetime import date

import pytest

from shopify_wbr.loader import load_ad_spend, load_orders
from shopify_wbr.metrics import build_review, latest_complete_week_end, pct_change


def test_latest_complete_week_end(orders_csv):
    # data ends on Sunday 2026-10-18, so that week counts as complete
    assert latest_complete_week_end(load_orders(orders_csv)) == date(2026, 10, 18)


def test_week_metrics(orders_csv, ads_csv):
    r = build_review(load_orders(orders_csv), load_ad_spend(ads_csv))
    c, p = r.current, r.previous
    assert (c.start, c.end) == (date(2026, 10, 12), date(2026, 10, 18))
    # voided #1005 excluded
    assert c.orders == 3 and c.revenue == pytest.approx(300.0)
    assert c.aov == pytest.approx(100.0)
    assert c.refunds == 50.0 and c.refund_rate == pytest.approx(50 / 300)
    assert c.units == 2 + 3 + 1
    assert p.orders == 2 and p.revenue == 140.0
    assert r.change("revenue") == pytest.approx(300 / 140 - 1)
    # a@ ordered last week -> returning; c@ and d@ are new (d@'s voided order doesn't count)
    assert c.new_customers == 2 and c.returning_customers == 1
    assert c.ad_spend == 100.0 and c.roas == pytest.approx(3.0)
    assert c.cac == pytest.approx(50.0)
    assert c.ad_spend_by_channel == {"Meta": 60.0, "Google": 40.0}


def test_top_products_and_refund_attribution(orders_csv):
    r = build_review(load_orders(orders_csv))
    names = [t.name for t in r.top_products]
    assert names[0] == "Blanket"  # 100 + 90, voided 999 excluded
    blanket = r.top_products[0]
    assert blanket.revenue == 190.0 and blanket.change is None  # not sold last week
    refunds = dict(r.refunds_by_product)
    assert refunds["Mug"] == pytest.approx(50 * 50 / 150)
    assert refunds["Blanket"] == pytest.approx(50 * 100 / 150)
    assert not r.has_ad_data and r.current.roas is None


def test_explicit_week(orders_csv):
    r = build_review(load_orders(orders_csv), week_ending=date(2026, 10, 11))
    assert r.current.orders == 2 and r.previous.orders == 0
    assert r.change("revenue") is None


def test_pct_change():
    assert pct_change(110, 100) == pytest.approx(0.1)
    assert pct_change(5, 0) is None
