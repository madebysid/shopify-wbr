# shopify-wbr CLI

A command-line version of the [Shopify Weekly Business Review](https://madebysid.github.io/shopify-wbr/) web app. It uses the same metrics and is handy for scheduled reports. Python 3.10+ with no third-party dependencies. PDF export uses a local Chrome or Chromium.

```bash
pip install -e .
wbr orders_export.csv --ads ad_spend.csv --store "Your Store" -o reports/wbr.html --pdf
```

| Flag | Default | |
|---|---|---|
| `--ads FILE` | | ad spend CSV (`date,channel,spend`) |
| `-o, --out FILE` | `wbr.html` | output path |
| `--pdf` | off | also write a PDF next to the HTML (set `WBR_CHROME` if Chrome isn't found) |
| `--week-ending DATE` | last complete week | Sunday that ends the reported week |
| `--store NAME` | `My Store` | store name in the header |
| `--currency SYM` | `$` | currency symbol |
| `--top N` | `5` | number of top products |
| `--no-llm` | off | skip the LLM even if a key is set |

Optional LLM summary: set `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` (and optionally `WBR_MODEL`). Only aggregated numbers are sent. Without a key, a rule-based summary is used.

Tests: `pip install -r requirements-dev.txt && pytest`
