#!/usr/bin/env python3
"""Pulls every deal created OR closed in a date range from HubSpot, plus the owner list.

Token: export HUBSPOT_TOKEN=... (a private-app token with crm.objects.deals.read and crm.objects.owners.read).
Never paste the token into a file or chat.

Usage: hubspot_pull.py --start 2025-01-01 --end 2026-09-30 [--extra prop1,prop2] [--out data]
Writes data/deals.csv and data/owners.csv.
The search API returns at most 10,000 results per query, so the range is split by month and halved again when needed.
"""
import argparse
import csv
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

API = "https://api.hubapi.com"
BASE_PROPS = ["dealname", "amount", "deal_currency_code", "closedate", "createdate", "dealstage", "pipeline",
              "hs_is_closed_won", "hs_is_closed", "hubspot_owner_id", "channel", "lead_source", "source_campaign",
              "hs_analytics_source", "products", "desired_products"]
CTX = ssl.create_default_context()


def call(method, path, token, body=None, tries=6):
    data = json.dumps(body).encode() if body is not None else None
    for i in range(tries):
        req = urllib.request.Request(API + path, data=data, method=method,
                                     headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, context=CTX, timeout=60) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and i < tries - 1:
                time.sleep(2 ** i)
                continue
            sys.exit(f"HubSpot {e.code}: {e.read().decode()[:500]}")
        except urllib.error.URLError:
            if i < tries - 1:
                time.sleep(2 ** i)
                continue
            raise


def ms(d):
    return str(int(d.timestamp() * 1000))


def search(token, start, end, props):
    """All deals with createdate or closedate in [start, end). Splits the window if it holds 10k+."""
    groups = [{"filters": [{"propertyName": p, "operator": "GTE", "value": ms(start)},
                           {"propertyName": p, "operator": "LT", "value": ms(end)}]} for p in ("createdate", "closedate")]
    body = {"filterGroups": groups, "properties": props, "limit": 200, "sorts": [{"propertyName": "createdate", "direction": "ASCENDING"}]}
    first = call("POST", "/crm/v3/objects/deals/search", token, body)
    if first.get("total", 0) >= 10000 and end - start > timedelta(hours=2):
        mid = start + (end - start) / 2
        return search(token, start, mid, props) + search(token, mid, end, props)
    out, page = [], first
    while True:
        out += page.get("results", [])
        after = page.get("paging", {}).get("next", {}).get("after")
        if not after:
            return out
        time.sleep(0.25)  # search API allows a few requests per second
        page = call("POST", "/crm/v3/objects/deals/search", token, dict(body, after=after))


def valid_props(token, props):
    have = {p["name"] for p in call("GET", "/crm/v3/properties/deals", token)["results"]}
    missing = [p for p in props if p not in have]
    if missing:
        print(f"skipping properties this portal does not have: {missing}")
    return [p for p in props if p in have]


def owners(token):
    rows = []
    for archived in ("false", "true"):
        after = None
        while True:
            q = f"/crm/v3/owners?limit=500&archived={archived}" + (f"&after={after}" if after else "")
            r = call("GET", q, token)
            for o in r.get("results", []):
                name = f"{o.get('firstName') or ''} {o.get('lastName') or ''}".strip() or o.get("email") or o["id"]
                rows.append({"id": o["id"], "name": name, "email": o.get("email", ""), "archived": archived,
                             "created": o.get("createdAt", "")})
            after = r.get("paging", {}).get("next", {}).get("after")
            if not after:
                break
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True, help="inclusive date")
    ap.add_argument("--extra", default="", help="more deal properties, comma separated")
    ap.add_argument("--out", default="data")
    a = ap.parse_args()
    token = os.environ.get("HUBSPOT_TOKEN")
    if not token:
        sys.exit("Set HUBSPOT_TOKEN in the environment first.")
    props = valid_props(token, BASE_PROPS + [p for p in a.extra.split(",") if p])
    start = datetime.fromisoformat(a.start).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(a.end).replace(tzinfo=timezone.utc) + timedelta(days=1)
    deals, cur = {}, start
    while cur < end:
        nxt = min((cur.replace(day=1) + timedelta(days=32)).replace(day=1), end)
        for d in search(token, cur, nxt, props):
            deals[d["id"]] = d
        print(f"{cur:%Y-%m}: {len(deals):,} deals so far")
        cur = nxt
    os.makedirs(a.out, exist_ok=True)
    with open(f"{a.out}/deals.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["hs_object_id"] + props, extrasaction="ignore")
        w.writeheader()
        for d in deals.values():
            w.writerow({"hs_object_id": d["id"], **{p: d["properties"].get(p) for p in props}})
    ow = owners(token)
    with open(f"{a.out}/owners.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["id", "name", "email", "archived", "created"])
        w.writeheader()
        w.writerows(ow)
    print(f"wrote {len(deals):,} deals to {a.out}/deals.csv and {len(ow)} owners to {a.out}/owners.csv")
    print("Owner 'created' is when the user was added to HubSpot: compare it with each owner's first deal before trusting owner tables.")


if __name__ == "__main__":
    main()
