---
name: performance-marketing
description: Analyze large performance-marketing and sales data and produce decisions, workbooks and executive decks. Two modes. Quick mode reads ad exports (Meta, Google, TikTok, Snapchat, GA4, Shopify) and returns what to scale, cut, fix and test. Audit mode joins CRM deals (HubSpot or any CRM export) with ad spend across periods, detects growth patterns and funnel leaks (volume vs AOV, lead-quality traps, closing outages, owner attribution errors, geo value gaps, fatigue), and builds a 12-tab Excel workbook plus a 10-slide 16:9 deck. Use for "analyze my ads", ROAS/CPA/CAC/win-rate questions, year-over-year audits, CRM pipeline audits, budget allocation, or executive performance reports. Learns from every run.
---

# Performance Marketing Analyst

Turns big ad and CRM data into decisions. Scripts do all the math; you read their small summaries, write the story, and check yourself before anything reaches the user. Every run makes the skill better (see Step L).

## Hard rules (follow always)

1. NEVER open or print a big data file. Run a script; read only its summary (`summary.md`, `facts.md`).
2. NEVER calculate by hand. Every number you write must come from script output. The self-check fails the run if one does not.
3. NEVER invent a number, a cause, a person or a date. Unknown = "not available" + ask.
4. Never judge an entity below the sample minimum (30 won deals/purchases by default). Put it under caveats.
5. Never credit deals to a person before their verified start date (owner history guard).
6. Do the steps in order. Do not skip the self-check or the learning step.
7. Never change a live ad account or CRM. Only suggest changes.
8. Never paste tokens, passwords or API keys anywhere. Tokens go in environment variables only.

`<SKILL_DIR>` below = the folder containing this file. Use its absolute path. First time on a machine: `bash <SKILL_DIR>/scripts/setup.sh`.

## Step 0: Load what the skill has learned (every run)

Read `references/learned-rules.md`. These are rules promoted from earlier runs. They override defaults in this file when they conflict.

## Step 1: Pick the mode

| The user has / wants | Mode |
|---|---|
| Ad exports only, "what should I scale/cut", one period | QUICK |
| CRM deals (+ usually ad spend), several months or years, "audit", "compare years", workbook or deck | AUDIT |

Then pick the model tier: `python3 <SKILL_DIR>/scripts/analyze.py route <FILE> --files <N> --task <routine|strategy|attribution|cohort|budget>`. AUDIT is always `--task strategy`. Tier names: `references/model-routing.md`. A skill cannot switch models itself: when a step is marked [PRO] and you are on a fast model, tell the user in one line to switch, then continue from the files named in that step.

---

## QUICK mode

Q1. Ask in one message only what is missing: export file paths, business type, breakeven ROAS (= 1 / gross margin) or target CPA. Unknown margin → breakeven ROAS 2.0, labelled as an assumption.

Q2. `python3 <SKILL_DIR>/scripts/analyze.py profile <FILE>`. Check the `mapping:` line: spend, purchases, revenue, campaign, date must map correctly. Fix with `--map spend="Amount spent (USD)" purchases="Results"` (see `references/platform-columns.md`).

Q3. Run:
```bash
python3 <SKILL_DIR>/scripts/analyze.py report <FILE> --level campaign --breakeven-roas <X> --target-cpa <Y> --out out
python3 <SKILL_DIR>/scripts/analyze.py report <FILE> --level ad --breakeven-roas <X> --target-cpa <Y> --out out
python3 <SKILL_DIR>/scripts/analyze.py trend <FILE> --days 7 --out out
python3 <SKILL_DIR>/scripts/analyze.py anomalies <FILE> --out out
```
The `verdict` column is computed: SCALE (ROAS ≥ 1.3× breakeven, 30+ purchases), WATCH, CUT (below breakeven with 30+, or spend with zero purchases), INSUFFICIENT_DATA.

Q4. [PRO if route said PRO] Diagnose with `references/diagnostics.md`: for each CUT and for the trend, name the term that moved (CPA = CPM / (1000 × CTR × CVR)).

Q5. Answer with this template, under 400 words, in the user's language:
```
HEADLINE   Spend | Revenue | ROAS (breakeven) | CPA | last 7d vs prior 7d
SCALE      - <name>: spend, ROAS, purchases -> +20% budget, re-check in 3 days, roll back if ROAS < breakeven
CUT / FIX  - <name>: spend, ROAS, purchases, wasted -> action, because <CPM/CTR/CVR reason>
TEST NEXT  - hypothesis | metric | min sample | kill rule   (3 of these)
CAVEATS    - insufficient data, attribution overlap, assumptions
```
Then go to Step L.

---

## AUDIT mode

A1. Gather inputs (ask once, only what is missing):
- CRM deals: either a CSV export, or HubSpot via `export HUBSPOT_TOKEN=...` then
  `python3 <SKILL_DIR>/scripts/hubspot_pull.py --start 2025-01-01 --end 2026-09-30 --out data`
- Ad exports (monthly or daily; campaign, ad set or ad level; spend, impressions, reach, leads, messaging conversations).
- A client profile: copy `profiles/example.json` to the user's workspace (never into the skill folder) and fill in: currency rates to the base currency and where they came from, won/lost stage names, local phone formats, sales owners with real start dates, creative archetype keywords. Ask the user for owner start dates and FX rates; never guess them.

A2. Run the engine:
```bash
python3 <SKILL_DIR>/scripts/audit.py --deals data/deals.csv --owners data/owners.csv --meta ads.csv --profile profile.json --out out/audit
```
Optional: `--periods 2025,2026` and `--months 1-9` (comparable window; default = months present in the latest period).
It prints `facts.md`. Read it fully. If it exits with a column error, fix `deal_columns` / `meta_columns` in the profile and rerun.

A3. Data-quality gate. In `facts.md` → Findings:
- `owner_history_guard`: confirm start dates with the user before writing anything about the sales team.
- `unknown_currency`, `fx_missing`, `unknown_country` above 20%, `won_without_amount`: fix the profile and rerun A2, or carry them into caveats.
Do not continue to A4 while a HIGH data issue is unresolved unless the user says to.

A4. [PRO] Write `narrative.json`. Start from `out/audit/narrative_template.json` and follow `references/patterns.md`:
- Every HIGH finding is addressed by month (pivots, evolution or caveats).
- `pivots`: the 3 biggest moments (usually the shock, the peak, the trap), each with evidence numbers copied from facts.md and a one-line lesson.
- `efficiency`: what the lowest-CAC months had in common.
- `channel_story`, `geo_story`, `campaign_takeaways`, `content_takeaways` (keys must match names in facts.md).
- `evolution`: one row per quarter: the strategic pivot and its evidence.
- `pillars` (4) with actions and one KPI each; `targets` (new numbers allowed here only); `mandates` (5 directives); `caveats` (one per data-quality finding).
- Numbers: copy exactly as shown in facts.md (or as %, e.g. 0.1347 → 13.47%). Do not round differently or derive new ratios.

A5. Build:
```bash
python3 <SKILL_DIR>/scripts/build_workbook.py --metrics out/audit/metrics.json --narrative narrative.json --profile profile.json
python3 <SKILL_DIR>/scripts/build_deck.py --metrics out/audit/metrics.json --narrative narrative.json --profile profile.json
```
One 12-tab workbook per period (Arial 11 bold, 3-colour scales: green-high for wins, red-high for costs) and one 10-slide deck comparing the last two periods.

A6. Self-check (mandatory):
```bash
python3 <SKILL_DIR>/scripts/selfcheck.py --metrics out/audit/metrics.json --narrative narrative.json --workbook out/audit/*.xlsx --deck out/audit/*.pptx --profile profile.json --label "<short run name>"
```
Score below the pass mark (85), or any UNVERIFIED NUMBER → fix `narrative.json` and repeat A5–A6. At most 3 rounds; then report the remaining issues honestly.

A7. Reply with: file paths, the headline (revenue change and its driver), the 3 pivots in one line each, the self-check score, and the caveats. Then Step L.

---

## Step L: Learn (every run, both modes, takes one minute)

1. For each mistake the self-check caught, each data problem that needed a profile fix, and each pattern you saw that `patterns.md` does not describe, log one general lesson:
   `python3 <SKILL_DIR>/scripts/learn.py add --kind mistake|pattern|rule|threshold --text "<general lesson>" --evidence "<which metric, which direction>" --profile profile.json`
   Lessons must be general: no client names, people or money figures (the script refuses them).
2. `python3 <SKILL_DIR>/scripts/learn.py review`. Lessons seen 2+ times are ready:
   - a rule or mistake → `learn.py promote <ID>` (it lands in `learned-rules.md`, read at Step 0 next time);
   - a detector that fired wrongly or missed → `learn.py set-threshold <key> <value> --reason "..."` and then `bash <SKILL_DIR>/scripts/selftest.sh`; if the selftest fails, set it back;
   - a new pattern → add it to `references/patterns.md` (and, [PRO] only, a detector in `audit.py` plus a planted case in `examples/make_audit_sample.py` and `selftest.sh`).
   Tell the user in one line what was promoted or changed. Ask before promoting if the user is present.
3. `python3 <SKILL_DIR>/scripts/learn.py history` shows whether scores are improving.

## Files

- `scripts/analyze.py`: quick mode (`profile`, `report`, `trend`, `anomalies`, `route`, `significance`).
- `scripts/hubspot_pull.py`: deals + owners from HubSpot, handles paging and the 10k search cap.
- `scripts/audit.py`: audit engine → `metrics.json`, `facts.md`, `narrative_template.json`, `tables/`.
- `scripts/build_workbook.py`, `scripts/build_deck.py`: outputs.
- `scripts/selfcheck.py`: grades a run; `scripts/learn.py`: lessons, promotion, thresholds, history.
- `scripts/selftest.sh`: regression test on synthetic data with planted patterns. Run after any change.
- `config/defaults.json`: thresholds, styles, colours. `profiles/example.json`: per-client settings.
- `references/patterns.md`, `learned-rules.md`, `diagnostics.md`, `platform-columns.md`, `model-routing.md`.
- `learnings/`: lessons and changelog (shared), `runs.jsonl` (local score history).
