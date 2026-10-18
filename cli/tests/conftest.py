import textwrap
from pathlib import Path

import pytest

ORDERS = textwrap.dedent("""\
    Name,Email,Financial Status,Subtotal,Shipping,Taxes,Total,Discount Amount,Created at,Lineitem quantity,Lineitem name,Lineitem price,Lineitem sku,Refunded Amount
    #1001,a@example.com,paid,100.00,0.00,0.00,100.00,0.00,2026-10-05 10:00:00 +0400,2,Mug,50.00,MUG,0.00
    #1002,b@example.com,paid,40.00,0.00,0.00,40.00,0.00,2026-10-06 10:00:00 +0400,1,Towel,40.00,TWL,0.00
    #1003,a@example.com,partially_refunded,150.00,0.00,0.00,150.00,0.00,2026-10-12 09:00:00 +0400,1,Mug,50.00,MUG,50.00
    #1003,,,,,,,,2026-10-12 09:00:00 +0400,1,Blanket,100.00,BLK,
    #1004,c@example.com,paid,60.00,0.00,0.00,60.00,0.00,2026-10-14 12:00:00 +0400,3,Towel,20.00,TWL,0.00
    #1005,d@example.com,voided,999.00,0.00,0.00,999.00,0.00,2026-10-15 12:00:00 +0400,1,Blanket,999.00,BLK,0.00
    #1006,d@example.com,paid,90.00,0.00,0.00,90.00,0.00,2026-10-18 20:00:00 +0400,1,Blanket,90.00,BLK,0.00
""")

ADS = textwrap.dedent("""\
    date,channel,spend
    2026-10-06,Meta,20
    2026-10-13,Meta,60
    2026-10-14,Google,40
""")


@pytest.fixture
def orders_csv(tmp_path: Path) -> Path:
    p = tmp_path / "orders.csv"
    p.write_text(ORDERS)
    return p


@pytest.fixture
def ads_csv(tmp_path: Path) -> Path:
    p = tmp_path / "ads.csv"
    p.write_text(ADS)
    return p
