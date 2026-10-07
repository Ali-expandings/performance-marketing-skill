#!/usr/bin/env python3
"""CRM + ads audit engine. Turns a deals export and ad exports into metrics, detector findings and a
compact facts file. Every number later used in a workbook, deck or narrative comes from here.

Usage:
  audit.py --deals deals.csv [--owners owners.csv] [--meta ads.csv ...] [--profile profile.json]
           [--periods 2025,2026] [--months 1-9] [--out out/audit]
"""
import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import classify_keywords, country_from_text, load_settings, map_channel  # noqa: E402

META_ALIASES = {
    "date": ["month", "reporting starts", "day", "date", "date_start"],
    "campaign": ["campaign name", "campaign", "campaign_name"],
    "adset": ["ad set name", "adset name", "adset_name", "ad set"],
    "ad": ["ad name", "ad_name", "ad"],
    "spend": ["amount spent (usd)", "amount spent", "spend", "cost"],
    "impressions": ["impressions"],
    "reach": ["reach"],
    "clicks": ["link clicks", "clicks"],
    "leads": ["leads", "on-facebook leads", "results (leads)", "lead"],
    "messages": ["messaging conversations started", "messaging_conversations_started", "messages",
                 "new messaging contacts"],
}
NUMERIC = ["spend", "impressions", "reach", "clicks", "leads", "messages"]


def r(x, n=4):
    if x is None or (isinstance(x, float) and (np.isnan(x) or np.isinf(x))):
        return None
    return round(float(x), n)


def div(a, b):
    return a / b if b else None


# ---------------- loading ----------------
def load_deals(path, owners_path, cfg, findings):
    c = cfg["deal_columns"]
    df = pd.read_csv(path, dtype=str, low_memory=False)
    need = [c["created"], c["amount"]]
    miss = [k for k in need if k not in df.columns]
    if miss:
        sys.exit(f"deals file is missing columns {miss}. Set deal_columns in the profile. Columns: {list(df.columns)[:40]}")
    get = lambda k: df[c[k]] if c.get(k) and c[k] in df.columns else pd.Series([None] * len(df), index=df.index)

    out = pd.DataFrame({
        "id": get("id"),
        "name": get("name"),
        "created": pd.to_datetime(get("created"), errors="coerce", utc=True).dt.tz_localize(None),
        "closed": pd.to_datetime(get("closed"), errors="coerce", utc=True).dt.tz_localize(None),
        "stage": get("stage").astype(str).str.strip(),
        "amount": pd.to_numeric(get("amount").astype(str).str.replace(r"[^0-9.\-]", "", regex=True), errors="coerce"),
        "currency": get("currency").fillna(cfg.get("default_currency") or "").astype(str).str.upper().str.strip(),
        "owner_raw": get("owner").astype(str).str.strip(),
        "channel_raw": get("channel"),
        "source": get("source"),
        "campaign": get("campaign"),
        "products": get("products"),
    })
    # status
    won_flag = get("is_won").astype(str).str.lower().isin(["true", "1", "yes"])
    stage = out["stage"].str.lower()
    won_stages = [s.lower() for s in cfg["won_stages"]]
    lost_stages = [s.lower() for s in cfg["lost_stages"]]
    out["status"] = np.where(won_flag | stage.isin(won_stages), "won",
                             np.where(stage.isin(lost_stages), "lost", "open"))
    dups = out["id"].notna() & out["id"].duplicated()
    if dups.sum():
        findings.append(dq("duplicate_deal_ids", f"{int(dups.sum())} duplicate deal ids removed"))
        out = out[~dups]

    # currency -> base
    out["month_key"] = out["closed"].fillna(out["created"]).dt.strftime("%Y-%m")
    out["rate"] = [fx_rate(cur, mk, cfg) for cur, mk in zip(out["currency"], out["month_key"])]
    out["amount_base"] = out["amount"] * out["rate"]
    won = out["status"] == "won"
    unknown_cur = won & out["rate"].isna()
    if unknown_cur.sum():
        cur_list = sorted(out.loc[unknown_cur, "currency"].unique().tolist())[:10]
        findings.append(dq("unknown_currency", f"{int(unknown_cur.sum())} won deals have a currency with no fx rate {cur_list}; excluded from base revenue"))
    no_amt = won & out["amount"].isna()
    if no_amt.sum():
        findings.append(dq("won_without_amount", f"{int(no_amt.sum())} won deals have no amount"))

    # country
    cc = c.get("country")
    if cc and cc in df.columns and df[cc].notna().mean() > 0.5:
        out["country"] = df[cc].fillna("Unknown")
    else:
        fields = [f for f in c.get("phone_fields", []) if f in df.columns]
        text = df[fields].fillna("").astype(str).agg(" ".join, axis=1) if fields else pd.Series([""] * len(df))
        out["country"] = [country_from_text(t, cfg["local_phone_patterns"], cfg["country_labels"]) or "Unknown"
                          for t in text.loc[out.index]]
    unk = (out.loc[won, "country"] == "Unknown").mean() if won.any() else 0
    if unk > 0.1:
        findings.append(dq("unknown_country", f"{unk:.0%} of won deals have no country (no phone found). Add local_phone_patterns or a country column"))

    out["channel"] = [map_channel(v, cfg["channel_map"]) for v in out["channel_raw"]]
    unk = (out.loc[won, "channel"] == "Unknown").mean() if won.any() else 0
    if unk > 0.2:
        findings.append(dq("unknown_channel", f"{unk:.0%} of won deals have no closing channel"))

    # owners + history guard
    names = dict(cfg.get("owner_names", {}))
    auto_starts = {}
    if owners_path and os.path.exists(owners_path):
        o = pd.read_csv(owners_path, dtype=str)
        names.update(dict(zip(o["id"], o["name"])))
        if "created" in o.columns:  # when the user was added to the CRM: a floor for their start date
            for name, cr in zip(o["name"], pd.to_datetime(o["created"], errors="coerce", utc=True)):
                if pd.notna(cr):
                    auto_starts[name] = cr.tz_localize(None).normalize()
    out["owner"] = out["owner_raw"].map(lambda x: names.get(x, x if x not in ("nan", "None", "") else "Unassigned"))
    starts = dict(auto_starts)
    for o in cfg.get("owners", []):
        if o.get("start_date"):
            starts[o.get("name") or o.get("id")] = pd.Timestamp(o["start_date"])
            if o.get("id"):
                starts[names.get(o["id"], o["id"])] = pd.Timestamp(o["start_date"])
    cfg["_verified_starts"] = sorted(starts)
    out["owner_reassigned"] = False
    for name, start in starts.items():
        m = (out["owner"] == name) & (out["created"] < start)
        if m.sum():
            out.loc[m, "owner_reassigned"] = True
            out.loc[m, "owner"] = cfg["pre_hire_bucket"]
            findings.append({"pattern": "owner_history_guard", "severity": "high", "period": None, "month": None,
                             "evidence": {"owner": name, "start_date": str(start.date()), "deals_moved": int(m.sum())},
                             "hint": f"{int(m.sum())} deals created before {name} started were moved to '{cfg['pre_hire_bucket']}'. Never credit them to {name}."})
    return out


def fx_rate(cur, month_key, cfg):
    base = cfg["base_currency"].upper()
    if cur == base:
        return 1.0
    table = cfg["fx_to_base"].get(cur)
    if table is None:
        return np.nan
    if isinstance(table, (int, float)):
        return float(table)
    return float(table.get(month_key, table.get("default", np.nan)))


def load_meta(paths, cfg):
    frames = []
    for p in paths or []:
        df = pd.read_csv(p, dtype=str, low_memory=False) if not p.endswith(("xlsx", "xls")) else pd.read_excel(p, dtype=str)
        low = {k.lower().strip(): k for k in df.columns}
        col = {}
        for std, names in META_ALIASES.items():
            if std in cfg.get("meta_columns", {}):
                col[std] = cfg["meta_columns"][std]
                continue
            for n in names:
                if n in low:
                    col[std] = low[n]
                    break
        if "spend" not in col or "date" not in col:
            sys.exit(f"{p}: could not find spend/date columns. Set meta_columns in the profile. Columns: {list(df.columns)[:40]}")
        f = pd.DataFrame({k: df[v] for k, v in col.items()})
        for k in NUMERIC:
            f[k] = pd.to_numeric(f[k].astype(str).str.replace(r"[^0-9.\-]", "", regex=True), errors="coerce").fillna(0) if k in f else 0.0
        f["date"] = pd.to_datetime(f["date"], errors="coerce")
        for k in ("campaign", "adset", "ad"):
            if k not in f:
                f[k] = "(all)"
        f["level"] = "ad" if "ad" in col else ("adset" if "adset" in col else ("campaign" if "campaign" in col else "account"))
        frames.append(f)
    if not frames:
        return pd.DataFrame(columns=["date", "campaign", "adset", "ad", "level"] + NUMERIC)
    m = pd.concat(frames, ignore_index=True)
    rate = cfg["fx_to_base"].get(cfg["ad_spend_currency"].upper(), 1) if cfg["ad_spend_currency"].upper() != cfg["base_currency"].upper() else 1
    if isinstance(rate, dict):
        rate = rate.get("default", 1)
    m["spend"] = m["spend"] * float(rate)
    return m.dropna(subset=["date"])


# ---------------- tables ----------------
def monthly(deals, meta, period):
    rows = []
    for mth in range(1, 13):
        cr = deals[(deals.created.dt.year == period) & (deals.created.dt.month == mth)]
        cl = deals[(deals.closed.dt.year == period) & (deals.closed.dt.month == mth)]
        w, l = cl[cl.status == "won"], cl[cl.status == "lost"]
        mm = meta[(meta.date.dt.year == period) & (meta.date.dt.month == mth)]
        if not len(cr) and not len(cl) and not len(mm):
            continue
        spend = mm.spend.sum()
        rev = w.amount_base.sum()
        row = {"period": period, "month": mth, "spend": r(spend, 2), "impressions": r(mm.impressions.sum(), 0),
               "reach": r(mm.reach.sum(), 0), "frequency": r(div(mm.impressions.sum(), mm.reach.sum()), 2),
               "leads": r(mm.leads.sum(), 0), "messages": r(mm.messages.sum(), 0),
               "inquiries": len(cr), "won": len(w), "lost": len(l),
               "cvr_inquiry": r(div(len(w), len(cr))), "close_rate": r(div(len(w), len(w) + len(l))),
               "revenue": r(rev, 2), "aov": r(div(rev, len(w)), 2), "cac": r(div(spend, len(w)), 2),
               "roas": r(div(rev, spend), 3), "cpl": r(div(spend, mm.leads.sum() + mm.messages.sum()), 2)}
        for cur, v in w.groupby("currency").amount.sum().items():
            row[f"rev_native_{cur or 'NA'}"] = r(v, 2)
        rows.append(row)
    return rows


def totals(rows):
    if not rows:
        return {}
    df = pd.DataFrame(rows)
    s = {k: float(df[k].fillna(0).sum()) for k in ["spend", "impressions", "reach", "leads", "messages", "inquiries", "won", "lost", "revenue"]}
    s.update({"cvr_inquiry": r(div(s["won"], s["inquiries"])), "close_rate": r(div(s["won"], s["won"] + s["lost"])),
              "aov": r(div(s["revenue"], s["won"]), 2), "cac": r(div(s["spend"], s["won"]), 2),
              "roas": r(div(s["revenue"], s["spend"]), 3), "cpl": r(div(s["spend"], s["leads"] + s["messages"]), 2),
              "frequency": r(div(s["impressions"], s["reach"]), 2), "months": sorted(df.month.tolist())})
    for k in [c for c in df.columns if c.startswith("rev_native_")]:
        s[k] = r(df[k].fillna(0).sum(), 2)
    keep = {"cvr_inquiry", "close_rate", "roas"}
    return {k: (r(v, 2) if isinstance(v, float) and k not in keep else v) for k, v in s.items()}


def breakdown(won, key, total_rev, total_won, min_won):
    g = won.groupby(key).agg(won=("status", "size"), revenue=("amount_base", "sum")).reset_index()
    g["aov"] = g.revenue / g.won.replace(0, np.nan)
    g["share_won"] = g.won / max(total_won, 1)
    g["share_revenue"] = g.revenue / total_rev if total_rev else np.nan
    g["enough_data"] = g.won >= min_won
    return g.sort_values("revenue", ascending=False)


def records(df, n=None):
    df = df.head(n) if n else df
    df = df.replace([np.inf, -np.inf], np.nan)
    num = df.select_dtypes("number").columns
    df[num] = df[num].round(4)
    return json.loads(df.to_json(orient="records", date_format="iso"))


# ---------------- detectors ----------------
def dq(name, text):
    return {"pattern": "data_quality", "severity": "medium", "period": None, "month": None,
            "evidence": {"check": name}, "hint": text}


def detect(month_rows, cfg, period):
    d = cfg["detectors"]
    out = []
    df = pd.DataFrame(month_rows)
    if df.empty:
        return out
    df = df.sort_values("month").reset_index(drop=True)
    t = d["lead_quality_trap"]["trailing_months"]
    for i in range(1, len(df)):
        cur, prev = df.iloc[i], df.iloc[i - 1]
        trail = df.iloc[max(0, i - t):i]
        med_inq, med_cvr = trail.inquiries.median(), trail.cvr_inquiry.median()
        if med_inq and med_cvr and cur.cvr_inquiry is not None:
            if cur.inquiries >= d["lead_quality_trap"]["spike_ratio"] * med_inq and cur.cvr_inquiry <= d["lead_quality_trap"]["cvr_drop_ratio"] * med_cvr:
                out.append({"pattern": "lead_quality_trap", "severity": "high", "period": period, "month": int(cur.month),
                            "evidence": {"inquiries": int(cur.inquiries), "trailing_median_inquiries": r(med_inq, 1),
                                         "cvr": cur.cvr_inquiry, "trailing_median_cvr": r(med_cvr),
                                         "cac": cur.cac, "won": int(cur.won)},
                            "hint": "Inquiry spike with collapsing conversion: check which offer/lead magnet ran (freebies attract non-buyers)."})
        if prev.cvr_inquiry and cur.cvr_inquiry is not None and prev.inquiries:
            if cur.cvr_inquiry <= d["infrastructure_shock"]["cvr_drop_ratio"] * prev.cvr_inquiry and cur.inquiries < d["infrastructure_shock"]["max_inquiry_ratio"] * prev.inquiries:
                out.append({"pattern": "infrastructure_shock", "severity": "high", "period": period, "month": int(cur.month),
                            "evidence": {"cvr": cur.cvr_inquiry, "prev_cvr": prev.cvr_inquiry, "inquiries": int(cur.inquiries),
                                         "prev_inquiries": int(prev.inquiries), "lost": int(cur.lost), "prev_lost": int(prev.lost)},
                            "hint": "Conversion collapsed without a lead spike: check closing infrastructure (messaging number, routing, webhooks, staffing)."})
    ok = df[df.won >= cfg["min_won_for_judgement"]].dropna(subset=["cac"])
    if len(ok) >= 3:
        q = ok.cac.quantile(d["efficiency_peak"]["quantile"])
        for _, row in ok[ok.cac <= q].iterrows():
            out.append({"pattern": "efficiency_peak", "severity": "info", "period": period, "month": int(row.month),
                        "evidence": {"cac": row.cac, "cvr": row.cvr_inquiry, "won": int(row.won), "cpl": row.cpl,
                                     "period_median_cac": r(ok.cac.median(), 2)},
                        "hint": "Lowest-CAC month: find what ran (offer, creative archetype, channel) and make it the blueprint."})
    lo, hi = d["frequency"]["sweet_spot"]
    for i in range(1, len(df)):
        cur, prev = df.iloc[i], df.iloc[i - 1]
        if cur.frequency and cur.frequency > hi and prev.cac and cur.cac and cur.cac >= prev.cac * (1 + d["frequency"]["cost_rise"]):
            out.append({"pattern": "frequency_fatigue", "severity": "medium", "period": period, "month": int(cur.month),
                        "evidence": {"frequency": cur.frequency, "cac": cur.cac, "prev_cac": prev.cac},
                        "hint": f"Frequency above {hi} with rising CAC: refresh creative or widen audience."})
    return out


def detect_breakdowns(b, cfg, period):
    d = cfg["detectors"]
    out = []
    ch = b["channels"]
    if len(ch) and ch.iloc[0]["share_won"] >= d["closing_concentration"]["max_share"] and ch.iloc[0]["channel"] != "Unknown":
        out.append({"pattern": "closing_concentration", "severity": "medium", "period": period, "month": None,
                    "evidence": {"channel": ch.iloc[0]["channel"], "share_won": r(ch.iloc[0]["share_won"])},
                    "hint": "Most deals close on one channel: it is a single point of failure. Keep a warm backup and capture leads on a stable layer first."})
    for _, row in b["countries"].iterrows():
        gap = (row["share_revenue"] or 0) - (row["share_won"] or 0)
        if row["enough_data"] and gap >= d["geo_value_gap"]["min_gap"]:
            out.append({"pattern": "geo_value_gap", "severity": "info", "period": period, "month": None,
                        "evidence": {"country": row["country"], "share_won": r(row["share_won"]), "share_revenue": r(row["share_revenue"]), "aov": r(row["aov"], 2)},
                        "hint": "This geography earns more revenue than its deal share: high-AOV market worth its own campaigns and pricing."})
    ads = b["ads"]
    if len(ads) and ads.spend.sum() and ads.iloc[0]["spend"] / ads.spend.sum() >= d["ad_concentration"]["max_share"]:
        out.append({"pattern": "ad_concentration", "severity": "medium", "period": period, "month": None,
                    "evidence": {"ad": ads.iloc[0]["ad"], "share_spend": r(ads.iloc[0]["spend"] / ads.spend.sum())},
                    "hint": "One ad carries most spend: build a creative pipeline before it fatigues."})
    return out


def volume_vs_aov(a, b, pa, pb):
    """Split revenue change into volume effect and AOV effect."""
    if not a or not b or not a.get("aov") or not b.get("aov"):
        return None
    dv = (b["won"] - a["won"]) * a["aov"]
    dp = (b["aov"] - a["aov"]) * a["won"]
    inter = (b["won"] - a["won"]) * (b["aov"] - a["aov"])
    return {"pattern": "volume_vs_aov", "severity": "info", "period": pb, "month": None,
            "evidence": {"revenue_from": a["revenue"], "revenue_to": b["revenue"], "revenue_change_pct": r(div(b["revenue"] - a["revenue"], a["revenue"])),
                         "won_from": a["won"], "won_to": b["won"], "won_change_pct": r(div(b["won"] - a["won"], a["won"])),
                         "aov_from": a["aov"], "aov_to": b["aov"], "aov_change_pct": r(div(b["aov"] - a["aov"], a["aov"])),
                         "volume_effect": r(dv, 2), "aov_effect": r(dp, 2), "interaction": r(inter, 2),
                         "driver": "AOV" if dp > dv else "volume"},
            "hint": f"Revenue {pa}->{pb} is {'AOV' if dp > dv else 'volume'}-led. Explain what changed price/mix (versions, bundles, geography)."}


# ---------------- main ----------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deals", required=True)
    ap.add_argument("--owners")
    ap.add_argument("--meta", nargs="*", default=[])
    ap.add_argument("--profile")
    ap.add_argument("--periods", help="comma list of years, default: all years in data")
    ap.add_argument("--months", help="comparable months, e.g. 1-9. Default: months present in the latest period")
    ap.add_argument("--out", default="out/audit")
    a = ap.parse_args()
    cfg = load_settings(a.profile)
    findings = []
    deals = load_deals(a.deals, a.owners, cfg, findings)
    meta = load_meta(a.meta, cfg)
    if len(meta) and (meta.level == "ad").all():
        findings.append(dq("reach_summed", "Reach is summed across ads, so monthly frequency is a lower bound. Add an account-level export for exact frequency."))
    if not cfg["fx_to_base"] or len(cfg["fx_to_base"]) <= 1 and deals.currency.nunique() > 1:
        findings.append(dq("fx_missing", "Several currencies but no fx_to_base rates in the profile."))
    if cfg.get("fx_note"):
        findings.append(dq("fx_assumption", cfg["fx_note"]))

    years = sorted(int(y) for y in (a.periods.split(",") if a.periods else deals.created.dt.year.dropna().unique()))
    os.makedirs(a.out, exist_ok=True)
    os.makedirs(f"{a.out}/tables", exist_ok=True)
    result = {"client": cfg["client"], "base_currency": cfg["base_currency"], "periods": years, "monthly": {}, "totals": {},
              "comparable": {}, "breakdowns": {}, "findings": [], "config_thresholds": cfg["detectors"],
              "min_won_for_judgement": cfg["min_won_for_judgement"], "data": {"deals": int(len(deals)), "ad_rows": int(len(meta))}}

    latest = years[-1]
    if a.months:
        lo, hi = (int(x) for x in a.months.split("-"))
        comp_months = list(range(lo, hi + 1))
    else:
        comp_months = sorted(deals[deals.created.dt.year == latest].created.dt.month.dropna().unique().astype(int).tolist())
    result["comparable_months"] = comp_months

    for y in years:
        rows = monthly(deals, meta, y)
        result["monthly"][y] = rows
        result["totals"][y] = totals(rows)
        result["comparable"][y] = totals([x for x in rows if x["month"] in comp_months])
        findings += detect(rows, cfg, y)

        won = deals[(deals.status == "won") & (deals.closed.dt.year == y)]
        lost = deals[(deals.status == "lost") & (deals.closed.dt.year == y)]
        tw, tr = len(won), won.amount_base.sum()
        mw = cfg["min_won_for_judgement"]
        owners = breakdown(won, "owner", tr, tw, mw)
        lost_by = lost.groupby("owner").size().rename("lost")
        owners = owners.merge(lost_by, left_on="owner", right_index=True, how="left").fillna({"lost": 0})
        owners["close_rate"] = owners.won / (owners.won + owners.lost)
        timeline = deals[deals.created.dt.year == y].groupby("owner").agg(first_created=("created", "min"), last_created=("created", "max"), deals=("id", "size")).reset_index()
        channels = breakdown(won, "channel", tr, tw, mw)
        countries = breakdown(won, "country", tr, tw, mw)
        cur_split = won.groupby(["country", "currency"]).size().unstack(fill_value=0)
        countries = countries.merge(cur_split, left_on="country", right_index=True, how="left")
        sep = cfg["products_separator"]
        pw = won.assign(product=won.products.fillna("Unknown").astype(str).str.split(sep)).explode("product")
        pw["product"] = pw["product"].str.strip().replace("", "Unknown")
        pw["n"] = pw.groupby(level=0)["product"].transform("size")
        pw["amount_split"] = pw.amount_base / pw.n
        pw["native_split"] = pw.amount / pw.n
        products = pw.groupby("product").agg(won=("status", "size"), revenue=("amount_split", "sum")).reset_index()
        products["avg_price"] = products.revenue / products.won
        for cur in sorted(won.currency.unique()):
            products = products.merge(pw[pw.currency == cur].groupby("product").native_split.sum().rename(f"native_{cur or 'NA'}"),
                                      left_on="product", right_index=True, how="left")
        products = products.sort_values("revenue", ascending=False)
        pm = pw.assign(month=pw.closed.dt.month).groupby(["month", "product"]).agg(won=("status", "size"), revenue=("amount_split", "sum")).reset_index()
        pm = pm.sort_values(["month", "revenue"], ascending=[True, False]).groupby("month").head(5)
        ch_month = won.assign(month=won.closed.dt.month).pivot_table(index="month", columns="channel", values="status", aggfunc="size", fill_value=0).reset_index()
        geo_month = won.assign(month=won.closed.dt.month).pivot_table(index="month", columns="country", values="status", aggfunc="size", fill_value=0).reset_index()
        own_month = won.assign(month=won.closed.dt.month).pivot_table(index="month", columns="owner", values="status", aggfunc="size", fill_value=0).reset_index()

        my = meta[meta.date.dt.year == y]
        lo_f, hi_f = cfg["detectors"]["frequency"]["sweet_spot"]
        ads = my.groupby(["campaign", "adset", "ad"]).agg(spend=("spend", "sum"), impressions=("impressions", "sum"), reach=("reach", "sum"),
                                                         leads=("leads", "sum"), messages=("messages", "sum"), clicks=("clicks", "sum")).reset_index()
        ads["frequency"] = ads.impressions / ads.reach.replace(0, np.nan)
        ads["cpl"] = ads.spend / (ads.leads + ads.messages).replace(0, np.nan)
        ads["fatigue_status"] = np.where(ads.frequency > hi_f, "Fatigue", np.where(ads.frequency >= lo_f, "Sweet spot", "Building"))
        ads["archetype"] = [classify_keywords(f"{x} {z}", cfg["content_archetypes"]) for x, z in zip(ads.ad, ads.adset)]
        ads = ads.sort_values("spend", ascending=False)
        arche = ads.groupby("archetype").agg(spend=("spend", "sum"), leads=("leads", "sum"), messages=("messages", "sum"), ads=("ad", "size")).reset_index()
        arche["cpl"] = arche.spend / (arche.leads + arche.messages).replace(0, np.nan)
        arche = arche.sort_values("spend", ascending=False)
        camps = my.groupby("campaign").agg(spend=("spend", "sum"), leads=("leads", "sum"), messages=("messages", "sum"),
                                           first=("date", "min"), last=("date", "max")).reset_index()
        camps["cpl"] = camps.spend / (camps.leads + camps.messages).replace(0, np.nan)
        dc = won.assign(key=won.campaign.fillna("").astype(str).str.lower().str.strip()).groupby("key").agg(won=("status", "size"), revenue=("amount_base", "sum"))
        camps["key"] = camps.campaign.astype(str).str.lower().str.strip()
        camps = camps.merge(dc, left_on="key", right_index=True, how="left").drop(columns="key")
        camps["roas"] = camps.revenue / camps.spend.replace(0, np.nan)
        camps = camps.sort_values("spend", ascending=False)

        b = {"owners": owners, "owner_timeline": timeline, "channels": channels, "countries": countries, "products": products,
             "product_month": pm, "channel_month": ch_month, "country_month": geo_month, "owner_month": own_month,
             "ads": ads, "archetypes": arche, "campaigns": camps}
        findings += detect_breakdowns(b, cfg, y)
        if cfg["detectors"]["owner_history"]["warn_if_no_start_date"] and y == years[0] and len(years) > 1:
            later = set(deals[deals.created.dt.year == years[-1]].owner)
            known = {o.get("name") or o.get("id") for o in cfg.get("owners", [])} | set(cfg.get("_verified_starts", []))
            suspects = [o for o in owners.owner if o in later and o not in known and o != cfg["pre_hire_bucket"]]
            if suspects:
                findings.append({"pattern": "owner_history_guard", "severity": "high", "period": y, "month": None,
                                 "evidence": {"owners_without_start_date": suspects[:10]},
                                 "hint": "These owners hold deals in the earliest period but have no start_date in the profile. Verify hire dates before writing any sales-team table; CRM owner fields are often reassigned later."})
        result["breakdowns"][y] = {k: records(v, 200) for k, v in b.items()}
        for k, v in b.items():
            v.to_csv(f"{a.out}/tables/{y}_{k}.csv", index=False)
        pd.DataFrame(rows).to_csv(f"{a.out}/tables/{y}_monthly.csv", index=False)

    if len(years) > 1:
        cmp = volume_vs_aov(result["comparable"][years[-2]], result["comparable"][years[-1]], years[-2], years[-1])
        if cmp:
            findings.append(cmp)
        a_, b_ = result["comparable"][years[-2]], result["comparable"][years[-1]]
        result["comparison"] = {k: {"from": a_.get(k), "to": b_.get(k), "change_pct": r(div((b_.get(k) or 0) - (a_.get(k) or 0), a_.get(k)))}
                                for k in ["spend", "leads", "messages", "inquiries", "won", "lost", "revenue", "aov", "cac", "roas", "cvr_inquiry", "close_rate", "cpl"]
                                if isinstance(a_.get(k), (int, float))}
        mrows = []
        pa, pb = {x["month"]: x for x in result["monthly"][years[-2]]}, {x["month"]: x for x in result["monthly"][years[-1]]}
        for mth in comp_months:
            x, z = pa.get(mth, {}), pb.get(mth, {})
            mrows.append({"month": mth, **{f"{k}_{years[-2]}": x.get(k) for k in ["revenue", "won", "cac", "cvr_inquiry"]},
                          **{f"{k}_{years[-1]}": z.get(k) for k in ["revenue", "won", "cac", "cvr_inquiry"]},
                          "revenue_change_pct": r(div((z.get("revenue") or 0) - (x.get("revenue") or 0), x.get("revenue")))})
        result["month_by_month"] = mrows

    result["findings"] = findings
    with open(f"{a.out}/metrics.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1, default=str)
    write_facts(result, a.out, cfg)
    write_template(result, a.out)
    print(open(f"{a.out}/facts.md", encoding="utf-8").read())
    print(f"\nwritten: {a.out}/metrics.json, facts.md, narrative_template.json, tables/")


def fmt(v):
    if v is None:
        return "n/a"
    if isinstance(v, float):
        return f"{v:,.4f}".rstrip("0").rstrip(".") if abs(v) < 10 else f"{v:,.2f}".rstrip("0").rstrip(".")
    return f"{v:,}" if isinstance(v, int) else str(v)


def table(rows, cols, n=10):
    rows = rows[:n]
    if not rows:
        return "_none_\n"
    s = "| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n"
    for x in rows:
        s += "| " + " | ".join(fmt(x.get(c)) for c in cols) + " |\n"
    return s


def write_facts(res, out, cfg):
    L = [f"# Audit facts: {res['client']}", f"Base currency: {res['base_currency']}. Deals: {res['data']['deals']:,}. Ad rows: {res['data']['ad_rows']:,}.",
         f"Comparable months: {res['comparable_months']}. Ratios are fractions (0.105 = 10.5%). Only numbers in this file may appear in the narrative.", ""]
    for y in res["periods"]:
        t = res["comparable"][y]
        L += [f"## {y} (comparable months)", table([t], ["spend", "inquiries", "won", "lost", "revenue", "aov", "cac", "roas", "cvr_inquiry", "close_rate", "cpl", "frequency"]), ""]
    if "comparison" in res:
        L += ["## Change latest vs previous (comparable months)",
              table([{"metric": k, **v} for k, v in res["comparison"].items()], ["metric", "from", "to", "change_pct"], 20), ""]
        L += ["## Month by month", table(res["month_by_month"], list(res["month_by_month"][0].keys()) if res["month_by_month"] else [], 12), ""]
    for y in res["periods"]:
        b = res["breakdowns"][y]
        L += [f"## {y} monthly", table(res["monthly"][y], ["month", "spend", "inquiries", "won", "lost", "cvr_inquiry", "revenue", "aov", "cac", "roas", "frequency"], 12),
              f"### {y} closing channels", table(b["channels"], ["channel", "won", "revenue", "aov", "share_won", "share_revenue"], 8),
              f"### {y} countries", table(b["countries"], ["country", "won", "revenue", "aov", "share_won", "share_revenue", "enough_data"], 8),
              f"### {y} owners (after history guard)", table(b["owners"], ["owner", "won", "lost", "close_rate", "revenue", "aov"], 10),
              f"### {y} owner timeline (verify against real start dates)", table(b["owner_timeline"], ["owner", "first_created", "last_created", "deals"], 12),
              f"### {y} top products", table(b["products"], ["product", "won", "revenue", "avg_price"], 10),
              f"### {y} creative archetypes", table(b["archetypes"], ["archetype", "spend", "leads", "messages", "cpl", "ads"], 8),
              f"### {y} top campaigns", table(b["campaigns"], ["campaign", "spend", "leads", "messages", "cpl", "won", "revenue", "roas"], 10), ""]
    L += ["## Findings (address every high one in the narrative)"]
    for f in res["findings"]:
        when = f"{f['period'] or ''}{'-%02d' % f['month'] if f.get('month') else ''}"
        L.append(f"- [{f['severity'].upper()}] {f['pattern']} {when}: {json.dumps(f['evidence'], ensure_ascii=False, default=str)}. {f['hint']}")
    with open(f"{out}/facts.md", "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")


def write_template(res, out):
    high = [f"{f['pattern']} {f.get('period') or ''}-{f.get('month') or ''}" for f in res["findings"] if f["severity"] == "high"]
    tpl = {
        "_instructions": "Fill every field. Copy numbers only from facts.md. Targets may be new numbers. Mention each high finding by month in pivots, evolution or caveats.",
        "_high_findings_to_address": high,
        "title": "", "subtitle": "", "verification_stamp": "Numbers verified against CRM and ad exports",
        "pivots": [{"title": "", "period": "", "month": "", "evidence": "", "lesson": ""} for _ in range(3)],
        "efficiency": {"headline": "", "bullets": ["", "", ""]},
        "channel_story": "",
        "geo_story": "",
        "campaign_takeaways": {},
        "content_takeaways": {},
        "evolution": [{"quarter": "", "pivot": "", "evidence": ""} for _ in range(4)],
        "pillars": [{"name": "", "actions": ["", ""], "kpi": ""} for _ in range(4)],
        "targets": [{"period": "", "revenue": "", "cac": "", "win_rate": ""} for _ in range(4)],
        "mandates": ["", "", "", "", ""],
        "caveats": [""],
    }
    with open(f"{out}/narrative_template.json", "w", encoding="utf-8") as f:
        json.dump(tpl, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
