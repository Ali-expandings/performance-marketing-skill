# performance-marketing

A skill for analyzing large ad and order exports (Meta, Google, TikTok, GA4, Shopify). It turns raw data into a ranked list of what to scale, cut, fix and test next.

## Install

Copy this folder into your editor's skills directory and name it `performance-marketing`. Then run:

```bash
bash scripts/setup.sh
```

## Use

Ask: "analyze my ads" and give the path to an export. Or run the script directly:

```bash
python3 scripts/analyze.py profile examples/sample.csv
python3 scripts/analyze.py report examples/sample.csv --level campaign --breakeven-roas 2.8 --out out
python3 scripts/analyze.py trend examples/sample.csv --days 7
```

Commands: `profile`, `report`, `trend`, `anomalies`, `significance`. Large files are handled with DuckDB, so they are never loaded whole into memory.
