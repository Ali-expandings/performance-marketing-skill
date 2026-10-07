#!/usr/bin/env bash
# Regression test: builds synthetic data with planted patterns, runs the full pipeline,
# and fails if a detector misses a planted pattern or the outputs break.
# Run after ANY change to scripts/ or config/.
set -e
DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-python3}"
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
"$PY" "$DIR/examples/make_audit_sample.py" "$T/d" >/dev/null
"$PY" "$DIR/scripts/audit.py" --deals "$T/d/deals.csv" --owners "$T/d/owners.csv" --meta "$T/d/meta_ads.csv" \
      --profile "$T/d/profile.json" --out "$T/o" >/dev/null
"$PY" - "$T/o/metrics.json" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
found = {(f["pattern"], f.get("period"), f.get("month")) for f in m["findings"]}
want = [("infrastructure_shock", 2026, 4), ("lead_quality_trap", 2026, 9), ("efficiency_peak", 2026, 8),
        ("frequency_fatigue", 2026, 9), ("seasonality_peak", 2026, 11), ("product_mix_shift", 2026, None),
        ("roas_decay", 2026, 10), ("wasted_ad_spend", 2026, 5), ("cac_spike", 2026, 7),
        ("underperforming_owner", 2026, None)]
miss = [w for w in want if w not in found]
pats = {f["pattern"] for f in m["findings"]}
for p in ["owner_history_guard", "volume_vs_aov", "closing_concentration"]:
    if p not in pats: miss.append(p)
vf = next(f for f in m["findings"] if f["pattern"] == "volume_vs_aov")
if vf["evidence"]["driver"] not in ("AOV", "volume"): miss.append("volume_vs_aov driver should be AOV or volume")
eg = [c for c in m["breakdowns"]["2026"]["countries"] if c["country"].startswith("Egypt")]
if not eg or eg[0]["share_won"] < 0.6: miss.append("phone parser: Egypt share too low")
rep1 = [o for o in m["breakdowns"]["2025"]["owners"] if o["owner"] == "Rep One"]
if rep1: miss.append("owner guard: Rep One still credited with first-year deals")
print("detectors: " + ("OK" if not miss else f"MISSED {miss}"))
sys.exit(1 if miss else 0)
PY
"$PY" "$DIR/scripts/build_workbook.py" --metrics "$T/o/metrics.json" --narrative "$DIR/examples/sample_narrative.json" --profile "$T/d/profile.json" >/dev/null
"$PY" "$DIR/scripts/build_deck.py" --metrics "$T/o/metrics.json" --narrative "$DIR/examples/sample_narrative.json" --profile "$T/d/profile.json" >/dev/null
"$PY" "$DIR/scripts/selfcheck.py" --metrics "$T/o/metrics.json" --narrative "$DIR/examples/sample_narrative.json" \
      --workbook "$T/o/Sample_Insights_2025.xlsx" "$T/o/Sample_Insights_2026.xlsx" --deck "$T/o/Sample_Insights_Deck_2025_2026.pptx" \
      --profile "$T/d/profile.json" --no-log | head -8
echo "selftest passed"
