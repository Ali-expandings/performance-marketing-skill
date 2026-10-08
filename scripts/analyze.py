#!/usr/bin/env python3
"""Performance-marketing data analysis CLI.
Usage:
  analyze.py profile FILE
  analyze.py report FILE [--level campaign|adset|ad|platform|day] [--by col,col] [--out DIR] [--map std=Column ...]
  analyze.py anomalies FILE [--out DIR]
  analyze.py trend FILE [--days 7]
  analyze.py route FILE [--files N] [--task routine|strategy|attribution|cohort|budget]
  report also takes --breakeven-roas X --target-cpa Y to add a SCALE/CUT/WATCH/INSUFFICIENT_DATA verdict column
  analyze.py significance --a-events N --a-trials N --b-events N --b-trials N
Needs: pip install duckdb pandas openpyxl
"""
import argparse, math, os, re, sys
import duckdb
import pandas as pd

ALIASES = {
    "date": ["day", "date", "reporting starts", "stat_time_day", "created at", "order date"],
    "platform": ["platform", "source", "publisher platform", "source / medium"],
    "campaign": ["campaign name", "campaign", "campaign_name"],
    "adset": ["ad set name", "ad group", "ad group name", "adset", "adset_name", "ad_group_name"],
    "ad": ["ad name", "ad", "ad_name", "creative"],
    "spend": ["amount spent", "amount spent (usd)", "cost", "spend", "total spend"],
    "impressions": ["impressions", "impr.", "impr"],
    "clicks": ["link clicks", "clicks", "clicks (all)", "sessions"],
    "purchases": ["purchases", "results", "conversions", "transactions", "orders", "website purchases"],
    "revenue": ["purchase conversion value", "conv. value", "conversion value", "revenue",
                "total purchase value", "total sales", "purchase roas value"],
}
NUM = ["spend", "impressions", "clicks", "purchases", "revenue"]


def load(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xlsm", ".xls"):
        df = pd.read_excel(path)
        con = duckdb.connect()
        con.register("raw", df)
        return con, "raw"
    con = duckdb.connect()
    con.execute(f"CREATE VIEW raw AS SELECT * FROM read_csv_auto('{path}', all_varchar=true, sample_size=-1, ignore_errors=true)")
    return con, "raw"


def automap(cols, overrides):
    m = {}
    low = {c.lower().strip(): c for c in cols}
    for std, names in ALIASES.items():
        for n in names:
            if n in low:
                m[std] = low[n]
                break
    for o in overrides or []:
        k, v = o.split("=", 1)
        m[k] = v
    return m


def clean_expr(col):
    return f"TRY_CAST(REGEXP_REPLACE(CAST(\"{col}\" AS VARCHAR), '[^0-9.\\-]', '', 'g') AS DOUBLE)"


def build_clean(con, src, m):
    sel = []
    for std in ALIASES:
        if std in m:
            if std in NUM:
                sel.append(f"COALESCE({clean_expr(m[std])},0) AS {std}")
            elif std == "date":
                sel.append(f"TRY_CAST(\"{m[std]}\" AS DATE) AS date")
            else:
                sel.append(f"CAST(\"{m[std]}\" AS VARCHAR) AS {std}")
    con.execute(f"CREATE OR REPLACE TABLE clean AS SELECT DISTINCT {', '.join(sel)} FROM {src}")
    # drop total rows
    for dim in ("campaign", "adset", "ad"):
        if dim in m:
            con.execute(f"DELETE FROM clean WHERE lower({dim}) IN ('total','totals','grand total','--') OR {dim} IS NULL")
            break


def rollup_sql(dims, m):
    s = lambda c: f"SUM({c})" if c in m else "NULL"
    d = ", ".join(dims) + ", " if dims else ""
    g = f"GROUP BY {', '.join(dims)}" if dims else ""
    return f"""SELECT {d}
      {s('spend')} AS spend, {s('impressions')} AS impressions, {s('clicks')} AS clicks,
      {s('purchases')} AS purchases, {s('revenue')} AS revenue,
      {s('spend')}/NULLIF({s('impressions')},0)*1000 AS cpm,
      {s('clicks')}/NULLIF({s('impressions')},0) AS ctr,
      {s('purchases')}/NULLIF({s('clicks')},0) AS cvr,
      {s('spend')}/NULLIF({s('purchases')},0) AS cpa,
      {s('revenue')}/NULLIF({s('spend')},0) AS roas,
      {s('revenue')}/NULLIF({s('purchases')},0) AS aov
      FROM clean {g} ORDER BY spend DESC NULLS LAST"""


def cmd_profile(a):
    con, src = load(a.file)
    cols = [r[0] for r in con.execute(f"DESCRIBE {src}").fetchall()]
    n = con.execute(f"SELECT COUNT(*) FROM {src}").fetchone()[0]
    print(f"rows: {n:,}  columns: {len(cols)}")
    m = automap(cols, a.map)
    print("mapping:", m or "NONE (use --map std=Column)")
    print("unmapped standard fields:", [k for k in ALIASES if k not in m])
    for c in cols[:60]:
        nn = con.execute(f'SELECT COUNT(*) FROM {src} WHERE "{c}" IS NULL OR CAST("{c}" AS VARCHAR)=\'\'').fetchone()[0]
        print(f"  {c}: {nn/max(n,1):.0%} empty")
    if m:
        build_clean(con, src, m)
        nc = con.execute("SELECT COUNT(*) FROM clean").fetchone()[0]
        print(f"after dedupe/total-row removal: {nc:,} rows (dropped {n-nc:,})")
        if "date" in m:
            print("date range:", con.execute("SELECT MIN(date), MAX(date) FROM clean").fetchone())
        print(con.execute(rollup_sql([], m)).df().T.to_string())


def md_table(df, n=10):
    return df.head(n).round(3).to_markdown(index=False) if hasattr(df, "to_markdown") else df.head(n).round(3).to_string(index=False)


def cmd_report(a):
    con, src = load(a.file)
    cols = [r[0] for r in con.execute(f"DESCRIBE {src}").fetchall()]
    m = automap(cols, a.map)
    build_clean(con, src, m)
    os.makedirs(a.out, exist_ok=True)
    dims = a.by.split(",") if a.by else [a.level]
    dims = [d for d in dims if d in m or d == "date"]
    if not dims:
        sys.exit(f"dimension not found in mapping: {m}")
    df = con.execute(rollup_sql(dims, m)).df()
    if "roas" in df and "purchases" in df:
        be = a.breakeven_roas
        def verdict(r):
            if (r.purchases or 0) < 30 and not ((r.purchases or 0) == 0 and r.spend and be and r.spend > 2 * (a.target_cpa or 1e18)):
                return "INSUFFICIENT_DATA"
            if (r.purchases or 0) == 0:
                return "CUT"
            if be and r.roas is not None:
                if r.roas >= be * 1.3: return "SCALE"
                if r.roas < be: return "CUT"
                return "WATCH"
            return "WATCH"
        df["verdict"] = df.apply(verdict, axis=1)
    df.to_csv(f"{a.out}/rollup_{'_'.join(dims)}.csv", index=False)
    tot = con.execute(rollup_sql([], m)).df()
    tot.to_csv(f"{a.out}/totals.csv", index=False)
    lines = ["# Summary", "", "## Totals", md_table(tot, 1), "", f"## By {', '.join(dims)} (top 15 by spend)", md_table(df, 15)]
    t = tot.iloc[0]
    if t.get("roas") and "spend" in df:
        mins = df[(df.purchases >= 30)] if "purchases" in df else df
        if len(mins):
            lines += ["", "## Best / worst ROAS (>=30 purchases)", md_table(mins.sort_values("roas", ascending=False), 5), "...", md_table(mins.sort_values("roas"), 5)]
        waste = df[(df.purchases == 0) & (df.spend > 0)]
        lines += ["", f"## Spend with zero purchases: {waste.spend.sum():,.0f} across {len(waste)} entities"]
        top = df.spend.head(1).sum() / max(df.spend.sum(), 1)
        lines += [f"Top entity share of spend: {top:.0%}"]
    open(f"{a.out}/summary.md", "w").write("\n".join(lines))
    print("\n".join(lines))
    print(f"\nwritten to {a.out}/")


def cmd_route(a):
    """Recommend a model tier from simple signals about the data and the task."""
    con, src = load(a.file)
    cols = [r[0] for r in con.execute(f"DESCRIBE {src}").fetchall()]
    n = con.execute(f"SELECT COUNT(*) FROM {src}").fetchone()[0]
    m = automap(cols, a.map)
    core = ["spend", "purchases", "revenue", "campaign", "date"]
    missing = [k for k in core if k not in m]
    pro, flash = [], []
    if missing: pro.append(f"core columns not mapped: {missing}")
    if a.files > 1: pro.append(f"{a.files} files / platforms to reconcile")
    if a.task in ("strategy", "attribution", "cohort", "budget"): pro.append(f"task needs judgement: {a.task}")
    if n > 5_000_000: pro.append(f"very large file ({n:,} rows)")
    if not pro:
        flash.append("one file, columns mapped, routine task")
    tier = "PRO" if pro else "FLASH"
    print(f"rows: {n:,}")
    print(f"recommended tier: {tier}")
    for r in (pro or flash): print(" -", r)
    print("Steps 2-3 (profile, report, trend) are mechanical: FLASH is enough." if tier == "PRO" else "Run every step on FLASH.")
    if tier == "PRO": print("Switch to PRO for steps 4-5 (diagnose + write the answer). Read out/summary.md only.")
    print("Model names for each tier: references/model-routing.md")


def cmd_trend(a):
    con, src = load(a.file)
    cols = [r[0] for r in con.execute(f"DESCRIBE {src}").fetchall()]
    m = automap(cols, a.map)
    build_clean(con, src, m)
    mx = con.execute("SELECT MAX(date) FROM clean").fetchone()[0]
    d = a.days
    cur = f"date > DATE '{mx}' - {d}"
    prv = f"date <= DATE '{mx}' - {d} AND date > DATE '{mx}' - {2*d}"
    rows = []
    for name, cond in (("current", cur), ("previous", prv)):
        con.execute(f"CREATE OR REPLACE TABLE w AS SELECT * FROM clean WHERE {cond}")
        sql = rollup_sql([], m).replace("FROM clean", "FROM w")
        r = con.execute(sql).df().iloc[0]
        r["window"] = name
        rows.append(r)
    df = pd.DataFrame(rows).set_index("window").T
    df["change_%"] = ((df["current"].astype(float) / df["previous"].astype(float) - 1) * 100).round(1)
    print(f"last {d} days ending {mx} vs the {d} days before")
    print(df.to_string())
    os.makedirs(a.out, exist_ok=True)
    df.to_csv(f"{a.out}/trend.csv")


def cmd_anomalies(a):
    con, src = load(a.file)
    cols = [r[0] for r in con.execute(f"DESCRIBE {src}").fetchall()]
    m = automap(cols, a.map)
    build_clean(con, src, m)
    df = con.execute(rollup_sql(["date"], m)).df().sort_values("date")
    out = []
    for k in ("spend", "purchases", "cpa", "roas"):
        s = df[k].astype(float)
        med = s.rolling(14, min_periods=5).median()
        mad = (s - med).abs().rolling(14, min_periods=5).median() * 1.4826
        z = (s - med) / mad.replace(0, float("nan"))
        for i in df.index[z.abs() > 3]:
            out.append((df.loc[i, "date"], k, round(s[i], 2), round(z[i], 1)))
    res = pd.DataFrame(out, columns=["date", "metric", "value", "robust_z"])
    os.makedirs(a.out, exist_ok=True)
    res.to_csv(f"{a.out}/anomalies.csv", index=False)
    print(res.to_string(index=False) if len(res) else "no anomalies")
    low = df[(df.spend > df.spend.median()) & (df.purchases == 0)]
    if len(low):
        print("\nPossible tracking break (spend normal, zero purchases):", list(low.date.astype(str)))


def cmd_blend(a):
    if not a.true_revenue:
        sys.exit("Requires --true-revenue to calculate blend factor.")

    con, src = load(a.file)
    cols = [r[0] for r in con.execute(f"DESCRIBE {src}").fetchall()]
    m = automap(cols, a.map)
    build_clean(con, src, m)

    # Calculate overall multiplier
    overall = con.execute(rollup_sql([], m)).df().iloc[0]
    reported_revenue = overall["revenue"]
    if not reported_revenue or reported_revenue == 0:
        sys.exit("Reported revenue is zero, cannot calculate blend factor.")

    blend_factor = a.true_revenue / reported_revenue
    print(f"Reported Revenue: {reported_revenue:,.2f}")
    print(f"True Revenue:     {a.true_revenue:,.2f}")
    print(f"Blend Multiplier: {blend_factor:.4f}")
    print("-" * 50)

    dims = a.by.split(",") if a.by else [a.level]
    dims = [d for d in dims if d in m or d == "date"]

    df = con.execute(rollup_sql(dims, m)).df()
    df["blended_revenue"] = df["revenue"] * blend_factor
    df["blended_roas"] = df["blended_revenue"] / df["spend"].replace(0, float("nan"))

    res = df[dims + ["spend", "revenue", "roas", "blended_revenue", "blended_roas"]].head(20)
    print(res.to_string(index=False))

    if a.out:
        os.makedirs(a.out, exist_ok=True)
        df.to_csv(f"{a.out}/blended_roas.csv", index=False)
        print(f"\nWritten to {a.out}/blended_roas.csv")

def cmd_forecast(a):
    import numpy as np
    con, src = load(a.file)
    cols = [r[0] for r in con.execute(f"DESCRIBE {src}").fetchall()]
    m = automap(cols, a.map)
    build_clean(con, src, m)

    # We need date, ad/campaign, spend, roas, frequency.
    # Group by date and ad level to see trend.
    dims = [a.level, "date"]
    df = con.execute(rollup_sql(dims, m)).df().sort_values(["date"])

    if "roas" not in df or "spend" not in df:
        sys.exit("Forecast requires spend and revenue to calculate ROAS.")

    be = a.breakeven_roas
    if not be:
        sys.exit("Requires --breakeven-roas X to forecast fatigue.")

    print(f"Fatigue Forecasting for {a.level} (Breakeven ROAS: {be})")
    print("-" * 50)

    out = []
    for name, group in df.groupby(a.level):
        group = group.dropna(subset=["roas", "spend"])
        if len(group) < 7:
            continue

        # Fit a simple linear regression over time for ROAS
        x = np.arange(len(group))
        y = group["roas"].values
        slope, intercept = np.polyfit(x, y, 1)

        current_roas = y[-1]

        if slope >= -0.01:
            continue # Not decaying significantly

        # Predict when ROAS hits breakeven
        # be = slope * x + intercept => x = (be - intercept) / slope
        days_to_be = (be - intercept) / slope
        days_left = int(days_to_be - x[-1])

        if days_left > 0 and days_left < 30:
            out.append((name, current_roas, days_left, group["spend"].sum()))

    res = pd.DataFrame(out, columns=["Entity", "Current ROAS", "Days to Fatigue", "Total Spend"])
    res = res.sort_values("Days to Fatigue")
    print(res.to_string(index=False) if not res.empty else "No entities are in immediate danger of fatiguing (<30 days).")


def cmd_sig(a):
    # Frequentist Z-test
    p1, p2 = a.a_events / a.a_trials, a.b_events / a.b_trials
    p = (a.a_events + a.b_events) / (a.a_trials + a.b_trials)
    se = math.sqrt(p * (1 - p) * (1 / a.a_trials + 1 / a.b_trials))
    z = (p2 - p1) / se if se else 0
    pv = math.erfc(abs(z) / math.sqrt(2))

    # Bayesian Probability to Be Best (Win Probability)
    # Using Monte Carlo simulation with Beta distributions
    import numpy as np
    try:
        from scipy.stats import beta
        draws = 100000
        a_samples = beta.rvs(1 + a.a_events, 1 + a.a_trials - a.a_events, size=draws)
        b_samples = beta.rvs(1 + a.b_events, 1 + a.b_trials - a.b_events, size=draws)
        prob_b_beats_a = np.mean(b_samples > a_samples)
        bayes_str = f" | Win Probability (B > A): {prob_b_beats_a:.2%}"
        if prob_b_beats_a >= 0.95:
            bayes_str += " [B is clear winner]"
        elif prob_b_beats_a <= 0.05:
            bayes_str += " [A is clear winner]"
    except ImportError:
        bayes_str = " | (Install scipy for Bayesian win probability)"

    print(f"A={p1:.4%} B={p2:.4%} lift={(p2/p1-1) if p1 else float('nan'):+.1%} z={z:.2f} p={pv:.4f}{bayes_str}")
    print("Frequentist significant (p<0.05, >=100 events/arm)" if pv < 0.05 and min(a.a_events, a.b_events) >= 100 else "NOT conclusive (Frequentist)")


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    for name in ("profile", "report", "anomalies", "trend", "route", "forecast", "blend"):
        p = sp.add_parser(name)
        p.add_argument("file")
        p.add_argument("--map", nargs="*")
        p.add_argument("--out", default="out")
        p.add_argument("--level", default="campaign")
        p.add_argument("--by")
        p.add_argument("--breakeven-roas", type=float, default=None, help="Target breakeven ROAS. Required for report verdicts and forecasting.")
        p.add_argument("--target-cpa", type=float, default=None)
        p.add_argument("--days", type=int, default=7)
        p.add_argument("--files", type=int, default=1)
        p.add_argument("--task", default="routine", help="routine|strategy|attribution|cohort|budget")
        p.add_argument("--true-revenue", type=float, default=None, help="For blend command: actual CRM or Shopify revenue to calibrate ad-reported revenue.")
    p = sp.add_parser("significance")
    for k in ("a_events", "a_trials", "b_events", "b_trials"):
        p.add_argument("--" + k.replace("_", "-"), dest=k, type=float, required=True)
    a = ap.parse_args()
    {"profile": cmd_profile, "report": cmd_report, "anomalies": cmd_anomalies, "trend": cmd_trend, "route": cmd_route, "forecast": cmd_forecast, "blend": cmd_blend, "significance": cmd_sig}[a.cmd](a)


if __name__ == "__main__":
    main()
