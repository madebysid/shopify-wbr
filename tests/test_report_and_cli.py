from shopify_wbr import summary as summary_mod
from shopify_wbr.cli import main
from shopify_wbr.loader import load_orders
from shopify_wbr.metrics import build_review
from shopify_wbr.report import render_html


def test_rule_based_summary_mentions_key_numbers(orders_csv):
    r = build_review(load_orders(orders_csv))
    text = " ".join(summary_mod.rule_based_summary(r))
    assert "$300" in text and "3 orders" in text and "Blanket" in text


def test_summarize_without_keys_uses_rules(orders_csv, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _, source = summary_mod.summarize(build_review(load_orders(orders_csv)))
    assert source == "rules"


def test_summarize_with_llm(orders_csv, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    calls = {}

    def fake_post(url, headers, body, timeout=30):
        calls["url"] = url
        calls["prompt"] = body["messages"][0]["content"]
        return {"choices": [{"message": {"content": "- Revenue up.\n- Fix refunds on Mug."}}]}

    monkeypatch.setattr(summary_mod, "_post", fake_post)
    bullets, source = summary_mod.summarize(build_review(load_orders(orders_csv)))
    assert source == "llm" and bullets == ["Revenue up.", "Fix refunds on Mug."]
    assert "openai.com" in calls["url"] and '"orders": 3' in calls["prompt"]


def test_llm_failure_falls_back(orders_csv, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")

    def boom(*a, **k):
        raise OSError("no network")

    monkeypatch.setattr(summary_mod, "_post", boom)
    _, source = summary_mod.summarize(build_review(load_orders(orders_csv)))
    assert source == "rules"


def test_html_escapes_product_names(orders_csv):
    r = build_review(load_orders(orders_csv))
    r.top_products[0].name = "<script>x</script>"
    html = render_html(r, ["ok"])
    assert "<script>x</script>" not in html and "&lt;script&gt;" in html


def test_cli_end_to_end(orders_csv, ads_csv, tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out = tmp_path / "out" / "wbr.html"
    assert main([str(orders_csv), "--ads", str(ads_csv), "-o", str(out), "--store", "Test Store"]) == 0
    html = out.read_text()
    assert "Test Store" in html and "Blended ROAS" in html and "$300" in html


def test_cli_bad_file(tmp_path, capsys):
    bad = tmp_path / "bad.csv"
    bad.write_text("a,b\n1,2\n")
    assert main([str(bad), "-o", str(tmp_path / "x.html")]) == 2
    assert "error" in capsys.readouterr().err
