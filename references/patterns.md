# Pattern library

Each pattern: what it looks like in the data, which detector finds it, what evidence to quote, what to recommend.
Detectors live in `scripts/audit.py`; thresholds in `config/defaults.json`. New patterns found in real runs are added at the bottom (see "Adding a pattern").

## 1. Volume vs AOV (detector: `volume_vs_aov`)
Revenue = won deals × AOV. Never judge growth by deal or lead count alone.
- Evidence: revenue, won and AOV change %, volume effect vs AOV effect, `driver`.
- If AOV-led: name what lifted price or mix (new product versions, bundles, higher-value geography). If volume-led: check that CAC held.

## 2. Lead-quality trap (detector: `lead_quality_trap`)
Inquiries spike far above the trailing median while inquiry→won collapses. Usually a giveaway (free files, free software, generic templates) pulling non-buyers. It floods sales, hides real buyers, and inflates true CAC even if CPL looks cheap.
- Evidence: inquiries vs trailing median, win rate vs trailing median, CAC that month, the archetype/campaign that ran.
- Recommend: gate lead magnets on buying intent (professional tools for practitioners), score leads before routing, judge offers on CAC not CPL.

## 3. Closing infrastructure shock (detector: `infrastructure_shock`)
Win rate halves or worse with no lead spike, and lost deals jump. Demand was there; the closing layer broke (messaging number banned or unlinked, routing or webhook failure, staffing gap).
- Evidence: win rate before/after, inquiries flat, lost deals before/after.
- Recommend: warm backup line or account, leads captured on a stable layer (native forms) and dispatched within a minute, alerting when replies stop.

## 4. Efficiency blueprint (detector: `efficiency_peak`)
Lowest-CAC months with enough deals. Find what was different (offer, creative archetype, audience, channel) and make it the default.
- Evidence: CAC vs period median, win rate, won count, CPL.

## 5. Acquisition ≠ closing (detector: `closing_concentration`)
Ads generate leads on one layer (forms, messages); deals close on another (often one chat channel). When one closing channel carries 80%+ of deals it is a single point of failure.
- Evidence: share of won deals by closing channel, form leads vs messaging starts.

## 6. Volume market vs value market (detector: `geo_value_gap`)
A geography whose share of revenue clearly exceeds its share of deals (high AOV, often a stronger currency). Deserves its own campaigns, pricing and payment options.
- Evidence: share of deals, share of revenue, AOV per country. Country comes from phone codes when the CRM has no country field.

## 7. Frequency fatigue (detector: `frequency_fatigue`)
Frequency above the sweet spot with CAC rising month over month. Refresh creative or widen the audience.
- Note: if reach is summed across ads, frequency is a lower bound (flagged as data quality).

## 8. Creative concentration (detector: `ad_concentration`)
One ad carries 40%+ of spend. Build a creative pipeline before it fatigues.

## 9. Owner history guard (detector: `owner_history_guard`)
CRM owner fields get reassigned. People hired later often appear as owners of deals created before they joined.
- Never write a sales-team table until owner start dates are verified (profile `owners[].start_date`, or the CRM user creation date in owners.csv).
- Deals created before an owner's start move to the profile's `pre_hire_bucket`.

## 10. Data quality (detector: `data_quality`)
Unknown currency, won deals without amount, unknown country or channel, duplicate ids, assumed FX. Each one goes into the narrative caveats.

## Adding a pattern
When a run reveals something the detectors missed:
1. `learn.py add --kind pattern --text "<general description>" --evidence "<which metric moved how>"`.
2. After it is seen twice, write it here (same format) and, if it can be detected from the tables, add a detector function in `audit.py` with thresholds in `config/defaults.json`, plant it in `examples/make_audit_sample.py`, and add it to the `want` list in `scripts/selftest.sh`.
3. Only the PRO tier edits scripts. `selftest.sh` must pass before the change is kept.
