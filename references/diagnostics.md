# Diagnostics

## Core formulas (always sum first, divide last)
CTR = clicks/impressions · CPM = spend/impr×1000 · CPC = spend/clicks · CVR = purchases/clicks
CPA = spend/purchases · ROAS = revenue/spend · AOV = revenue/purchases
Breakeven ROAS = 1/gross margin · Target CPA ≤ AOV × margin
CAC payback = CAC / (monthly gross profit per customer) · LTV:CAC healthy ≥ 3

## Funnel decomposition
CPA = CPM / (1000 × CTR × CVR). When CPA moves, find which term moved:
- CPM up → audience saturation, auction pressure, seasonality.
- CTR down → creative fatigue or message mismatch.
- CVR down → landing page, offer, price, tracking, or traffic quality.
Report the term with the largest relative change.

## Creative fatigue
Flag an ad when, over its last 7 days vs its first 7 days: CTR down ≥25% AND frequency ≥ 3 (prospecting), or CPA up ≥30% at stable spend. Check hook rate (3s views/impressions) and hold rate for video.

## Waste detection
- Spend on entities with zero conversions after ≥ 2× target CPA of spend.
- Entities below breakeven ROAS with ≥ 30 conversions (real losers, not noise).
- Placements/countries/devices with CPA > 1.5× account average and ≥ 5% of spend.
- Overlapping audiences bidding against each other (same geo + interest, high frequency).

## Concentration risk
Top 1 ad > 40% of spend or top 3 campaigns > 80%: flag dependency, recommend a creative pipeline.

## Significance
Two-proportion z-test for CVR/CTR differences (`analyze.py significance`). Require p < 0.05 and a minimum of 100 events per arm before declaring a winner. For many comparisons, say results are exploratory.

## Budget moves
Scale winners +15-25% every 3-4 days. Cut losers only after the sample rule is met. Shift budget toward marginal ROAS, not average ROAS: look at the last 20% of spend of each campaign.

## Trend and anomaly
Compare last 7d to prior 7d. Flag day-level spend/KPI outside ±3 MAD from rolling median. Check for tracking breaks: spend steady while conversions drop to ~0.

## Cohort / LTV (when order or CRM data exists)
Group customers by first-order week and acquisition channel. Show repeat rate at 30/60/90 days and cumulative revenue per customer. Judge channels on LTV:CAC, not first-purchase ROAS.
