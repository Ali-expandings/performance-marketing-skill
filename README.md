# performance-marketing

A skill for analyzing large marketing and sales datasets. It works in two modes:

- **Quick:** ad exports (Meta, Google, TikTok, GA4, Shopify) in, a ranked list of what to scale, cut, fix and test out.
- **Audit:** CRM deals (HubSpot or any CSV export) joined with ad spend across periods. It detects growth patterns and funnel leaks, then builds a 12-tab Excel workbook and a 10-slide executive deck.

All math runs in scripts (DuckDB/pandas), so large files never need to be read whole, and every number in the final report is checked against the data.

## It improves itself

Each run is graded by `scripts/selfcheck.py` (numbers traced to data, findings addressed, completeness, caveats, valid outputs). Lessons are logged with `scripts/learn.py`; lessons that recur are promoted into rules the next run reads, or into detector thresholds. `scripts/selftest.sh` reruns the pipeline on synthetic data with planted patterns so a change can't silently break detection.

## Install

Copy this folder into your editor's skills directory as `performance-marketing`, then:

```bash
bash scripts/setup.sh
bash scripts/selftest.sh
```

## Try it

```bash
python3 examples/make_audit_sample.py demo
python3 scripts/audit.py --deals demo/deals.csv --owners demo/owners.csv --meta demo/meta_ads.csv --profile demo/profile.json --out demo/out
python3 scripts/build_workbook.py --metrics demo/out/metrics.json --narrative examples/sample_narrative.json --profile demo/profile.json
python3 scripts/build_deck.py --metrics demo/out/metrics.json --narrative examples/sample_narrative.json --profile demo/profile.json
```

Per-client settings (currency rates, stage names, phone formats, sales owners and start dates, creative keywords) go in a profile: see `profiles/example.json`.
