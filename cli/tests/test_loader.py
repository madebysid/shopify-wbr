import pytest

from shopify_wbr.loader import load_ad_spend, load_orders


def test_groups_line_items_by_order(orders_csv):
    orders = load_orders(orders_csv)
    assert [o.name for o in orders] == ["#1001", "#1002", "#1003", "#1004", "#1005", "#1006"]
    o3 = orders[2]
    assert o3.total == 150.0 and o3.refunded == 50.0
    assert [li.name for li in o3.line_items] == ["Mug", "Blanket"]
    assert o3.email == "a@example.com"


def test_voided_flag(orders_csv):
    assert load_orders(orders_csv)[4].is_cancelled_or_voided


def test_rejects_non_shopify_csv(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("foo,bar\n1,2\n")
    with pytest.raises(ValueError, match="Shopify orders export"):
        load_orders(p)


def test_ad_spend(ads_csv):
    ads = load_ad_spend(ads_csv)
    assert len(ads) == 3 and ads[1].channel == "Meta" and ads[1].spend == 60.0
