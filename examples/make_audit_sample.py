#!/usr/bin/env python3
"""Builds a synthetic two-year CRM + ads dataset with known patterns planted in it.
Used by scripts/selftest.sh to prove the detectors still find them after any change.

Planted in the latest year: an outage month (4), an efficiency month (8), a lead-quality trap (9),
an owner who did not exist in the first year but holds first-year deals, higher AOV than the first year.
"""
import csv
import os
import random
import sys
from datetime import datetime, timedelta

random.seed(7)
out = sys.argv[1] if len(sys.argv) > 1 else "sample_audit"
os.makedirs(out, exist_ok=True)

Y1, Y2 = 2025, 2026
PRODUCTS_Y1 = ["Course A v3", "Course B v3", "Diploma C", "Course D"]
PRODUCTS_Y2 = ["Course A v9", "Course B v9", "Diploma C", "Bundle Pro", "Course D"]
OWNERS = {"100": "Central Desk", "201": "Rep One", "202": "Rep Two", "203": "Rep Three"}
ARCH = ["comparison vs", "walkthrough demo", "masterclass live", "authority photo", "free template download", "promo offer"]


def phone(local):
    if local:
        return "01" + random.choice("0125") + "".join(random.choices("0123456789", k=8))
    code = random.choice(["966", "966", "971", "974", "965", "962"])
    return "+" + code + "".join(random.choices("0123456789", k=9))


deals, did = [], 1
for y in (Y1, Y2):
    for m in range(1, 13):
        inquiries = random.randint(1700, 2200)
        cvr = random.uniform(0.09, 0.11)
        if y == Y2 and m == 4:
            cvr = 0.033
        if y == Y2 and m == 8:
            cvr = 0.135
        if y == Y2 and m == 9:
            inquiries, cvr = 4100, 0.044
        if m == 11:  # plant seasonal peak
            inquiries, cvr = 5000, 0.15

        aov_mult = 1.0
        if y == Y2 and m == 10: # plant ROAS decay (CAC stable, AOV drops)
            aov_mult = 0.5

        if y == Y1:
            cvr *= 0.85

        cac_spike = False
        if y == Y2 and m == 7: # Plant CAC spike
            cvr *= 0.3
            cac_spike = True
        n_won = int(inquiries * cvr)
        n_lost = int(inquiries * (0.30 if not (y == Y2 and m == 4) else 0.6))
        for i in range(inquiries):
            created = datetime(y, m, random.randint(1, 28), random.randint(8, 22))

            owner = "100" if y == Y1 else random.choice(["201", "202", "203"])
            if y == Y1 and random.random() < 0.15:
                owner = "201"  # reassigned history: Rep One did not work here in Y1

            status = "won" if i < n_won else ("lost" if i < n_won + n_lost else "open")

            # Plant underperforming owner
            if owner == "202" and y == Y2 and status == "won" and random.random() < 0.6:
                status = "lost" # Convert 60% of rep 2's won deals to lost to tank close rate

            closed = created + timedelta(days=random.randint(0, 2)) if status != "open" else None
            if closed and closed.month != m:
                closed = closed.replace(day=28, month=m, year=y)
            egypt = random.random() < 0.72
            if egypt:
                cur, amt = "EGP", random.choice([3500, 3800, 4200]) * (1.15 if y == Y2 else 1) * aov_mult
            else:
                cur, amt = "USD", random.choice([140, 180, 250]) * (1.2 if y == Y2 else 1) * aov_mult
            if y == Y1:
                prods = random.choices(PRODUCTS_Y1, weights=[0.4, 0.3, 0.2, 0.1])[0]
            else:
                prods = random.choices(PRODUCTS_Y2, weights=[0.4, 0.4, 0.05, 0.1, 0.05])[0]
            ch = random.random()
            channel = "WhatsApp" if ch < 0.87 else ("Facebook Page" if ch < 0.93 else ("Instagram" if ch < 0.97 else "Website"))
            deals.append({
                "hs_object_id": did, "dealname": f"Lead {did} - {phone(egypt)}",
                "createdate": created.isoformat() + "Z", "closedate": closed.isoformat() + "Z" if closed else "",
                "dealstage": {"won": "closedwon", "lost": "closedlost", "open": "appointmentscheduled"}[status],
                "hs_is_closed_won": "true" if status == "won" else "false",
                "amount": round(amt, 2) if status == "won" else "", "deal_currency_code": cur,
                "hubspot_owner_id": owner, "channel": channel, "lead_source": "Meta Lead Form",
                "source_campaign": f"{y}-Q{(m - 1) // 3 + 1} Leads", "products": prods,
            })
            did += 1

with open(f"{out}/deals.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(deals[0].keys()))
    w.writeheader()
    w.writerows(deals)

with open(f"{out}/owners.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["id", "name"])
    w.writerows(OWNERS.items())

rows = []
for y in (Y1, Y2):
    for m in range(1, 13):
        for a in range(12):
            arch = ARCH[a % len(ARCH)]
            spend = random.uniform(800, 1600)
            if y == Y2 and m == 7:
                spend *= 1.8 # Plant CAC spike (increase spend drastically while CVR dropped)
            impressions = int(spend * random.uniform(90, 120))
            freq = random.uniform(2.6, 3.2) if not (y == Y2 and m == 9) else random.uniform(3.6, 4.2)
            leads = int(spend / random.uniform(4, 7)) * (2 if (y == Y2 and m == 9 and "free" in arch) else 1)

            # Plant wasted ad spend
            if y == Y2 and m == 5 and a == 7:
                leads = 0

            rows.append({"Month": f"{y}-{m:02d}-01", "Campaign name": f"{y}-Q{(m - 1) // 3 + 1} Leads",
                         "Ad set name": f"Set {a % 3}", "Ad name": f"Ad {a} {arch}",
                         "Amount spent (USD)": round(spend, 2), "Impressions": impressions, "Reach": int(impressions / freq),
                         "Leads": leads, "Messaging conversations started": 0 if (y == Y2 and m == 5 and a == 7) else int(leads * 0.3)})
with open(f"{out}/meta_ads.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)

with open(f"{out}/profile.json", "w") as f:
    f.write("""{
  "client": "Sample Academy",
  "file_prefix": "Sample_Insights",
  "fx_to_base": {"USD": 1, "EGP": {"default": 0.0200}},
  "fx_note": "Sample data: EGP at a flat 50 per USD.",
  "local_phone_patterns": [{"regex": "01[0125]\\\\d{8}", "country": "Egypt (+20)"}],
  "owners": [{"name": "Rep One", "start_date": "2026-01-01"}, {"name": "Rep Two", "start_date": "2026-01-01"}, {"name": "Rep Three", "start_date": "2026-01-01"}]
}
""")
print(f"wrote {len(deals):,} deals and {len(rows):,} ad rows to {out}/")
