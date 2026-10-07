---
name: performance-marketing
description: Analyze large performance-marketing datasets (Meta, Google, TikTok, Snapchat ad exports, GA4, Shopify/WooCommerce orders, CRM) to find what to scale, cut, fix, and test. Use when the user shares ad CSV/XLSX exports or asks about ROAS, CPA, CAC, CPM/CTR/CVR, creative fatigue, funnel drop-off, budget allocation, cohort/LTV, or "analyze my ads/campaigns". Handles files too big to read directly by aggregating with DuckDB.
---

# Performance Marketing Analyst

Turn big ad exports into a short ranked list of money decisions.

## Hard rules (read first, follow always)

1. NEVER open or print a big data file. Run the script, read only its printed summary.
2. NEVER do math by hand on more than a few numbers. Use the script output.
3. NEVER invent a number. If the script did not print it, say "not available".
4. Every recommendation must quote: entity name, spend, the KPI, and purchases (sample size).
5. If verdict is `INSUFFICIENT_DATA`, do not recommend scaling or cutting it. List it under caveats.
6. Do not skip steps. Do the steps in order. Finish all of them before writing the answer.
7. Never change a live ad account. Only suggest changes.

## Setup (once per machine)

```bash
bash <SKILL_DIR>/scripts/setup.sh
```
`<SKILL_DIR>` is the folder that contains this file. Use its full absolute path in every command below. The script is `<SKILL_DIR>/scripts/analyze.py`; run it with `python3`. If `python3` says a module is missing, run setup again.

## Step 1: Ask for missing inputs (one message, max 4 questions)

- File path(s) of the export(s).
- Business type (ecommerce / lead-gen / course / app).
- Breakeven ROAS (= 1 / gross margin) or target CPA. If unknown, ask for gross margin %. If still unknown, use breakeven ROAS 2.0 and say it is an assumption.
- Anything to ignore (test campaigns, date range).

## Step 1b: Pick the model tier

```bash
python3 <SKILL_DIR>/scripts/analyze.py route <FILE> --files <how many files> --task <routine|strategy|attribution|cohort|budget>
```
It prints FLASH or PRO. FLASH runs every step. If PRO: run Steps 2-3 on FLASH (cheap and mechanical), then tell the user to switch the model to PRO before Steps 4-5, and continue from `out/summary.md` only. A skill cannot switch the model itself, so say so in one line. Model names per tier: `references/model-routing.md`.

## Step 2: Profile

```bash
python3 <SKILL_DIR>/scripts/analyze.py profile <FILE>
```
Check the `mapping:` line. Each of spend, purchases, revenue, campaign, date must map to the right column. If one is wrong or missing, re-run with an override, e.g. `--map spend="Amount spent (USD)" purchases="Results"`. See `references/platform-columns.md`. Tell the user the final mapping in one line.

## Step 3: Report (run all that apply)

```bash
python3 <SKILL_DIR>/scripts/analyze.py report <FILE> --level campaign --breakeven-roas <X> --target-cpa <Y> --out out
python3 <SKILL_DIR>/scripts/analyze.py report <FILE> --level adset --breakeven-roas <X> --target-cpa <Y> --out out
python3 <SKILL_DIR>/scripts/analyze.py report <FILE> --level ad --breakeven-roas <X> --target-cpa <Y> --out out
python3 <SKILL_DIR>/scripts/analyze.py report <FILE> --by country --breakeven-roas <X> --out out   # any column name, if it exists
python3 <SKILL_DIR>/scripts/analyze.py trend <FILE> --days 7 --out out
python3 <SKILL_DIR>/scripts/analyze.py anomalies <FILE> --out out
```
Outputs are in `out/` (CSV files and `summary.md`). Read `summary.md` and the top rows of the CSVs. The `verdict` column is already computed:

| verdict | meaning |
|---|---|
| SCALE | ROAS at least 1.3x breakeven and 30+ purchases |
| WATCH | ROAS between breakeven and 1.3x breakeven |
| CUT | below breakeven with 30+ purchases, or spend with zero purchases |
| INSUFFICIENT_DATA | under 30 purchases, no decision |

If the export has several platforms, run the steps once per file, then compare totals.

## Step 4: Diagnose

Open `references/diagnostics.md`. For each CUT entity and for the `trend` output, find which term moved: CPM, CTR, or CVR (CPA = CPM / (1000 x CTR x CVR)). State it in one phrase: "CPA up 30% because CVR fell 25%".
Also check: top ad share of spend (over 40% = risk), spend with zero purchases (waste), anomaly dates (possible tracking break).
To compare two variants: `python3 <SKILL_DIR>/scripts/analyze.py significance --a-events N --a-trials N --b-events N --b-trials N`.

## Step 5: Write the answer (use exactly this template)

```
HEADLINE
Spend X | Revenue X | ROAS X (breakeven X) | CPA X | last 7d vs prior 7d: ROAS +/-X%

SCALE (max 5)
- <name>: spend X, ROAS X, purchases N -> raise budget 20%, re-check in 3 days, roll back if ROAS < breakeven

CUT / FIX (max 5)
- <name>: spend X, ROAS X, purchases N, wasted ~X -> <pause | fix landing page | refresh creative>, because <CPM/CTR/CVR reason>

TEST NEXT (3)
- Hypothesis | metric | min sample | kill rule

CAVEATS
- <insufficient-data entities, attribution overlap, mapping assumptions, recent days incomplete>
```
Keep it under 400 words. Write in the user's language. Offer to go deeper on one section only after the answer.

## Self-check before sending

- Did I run profile and confirm the mapping? 
- Does every bullet have spend, KPI and purchases?
- Did I avoid recommending anything marked INSUFFICIENT_DATA?
- Are all numbers copied from script output?
- Did I use the template?

## Files

- `scripts/analyze.py`: commands `profile`, `report`, `trend`, `anomalies`, `route`, `significance`.
- `references/model-routing.md`: which model for which step.
- `scripts/setup.sh`: installs dependencies.
- `references/diagnostics.md`: formulas and detection rules.
- `references/platform-columns.md`: export column names per platform.
- `examples/sample.csv`: small sample to test the setup.
