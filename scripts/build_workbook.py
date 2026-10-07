#!/usr/bin/env python3
"""Builds the 12-tab insights workbook for one period from audit metrics (+ optional narrative).

Usage: build_workbook.py --metrics out/audit/metrics.json [--narrative narrative.json] [--period 2026]
                         [--profile profile.json] [--out out/audit]
"""
import argparse
import json
import os
import sys

from openpyxl import Workbook
from openpyxl.formatting.rule import ColorScaleRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_settings, read_json  # noqa: E402

MONTHS = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
GOOD = {"won", "revenue", "roas", "cvr_inquiry", "close_rate", "aov", "share_won", "share_revenue", "leads", "messages", "avg_price"}
BAD = {"cac", "cpl", "lost", "frequency"}
MONEY = {"spend", "revenue", "aov", "cac", "cpl", "avg_price", "volume_effect", "aov_effect"}
PCT = {"cvr_inquiry", "close_rate", "share_won", "share_revenue", "change_pct", "revenue_change_pct"}
RATIO = {"roas", "frequency"}
LABELS = {"cvr_inquiry": "Inquiry→Won %", "close_rate": "Close Rate %", "share_won": "Share of Deals", "share_revenue": "Share of Revenue",
          "aov": "AOV", "cac": "CAC", "cpl": "CPL", "roas": "ROAS", "won": "Won", "lost": "Lost", "avg_price": "Avg Price"}


def label(c):
    if c.startswith("rev_native_"):
        return f"Revenue ({c[11:]})"
    if c.startswith("native_"):
        return f"Revenue ({c[7:]})"
    if c.isupper():
        return f"Deals in {c}"
    return LABELS.get(c, c.replace("_", " ").title())


class Sheet:
    def __init__(self, wb, title, st):
        self.ws = wb.create_sheet(title[:31])
        self.st = st
        self.row = 1
        self.f_data = Font(name=st["font"], size=st["size"], bold=st["bold"], color="000000")
        self.f_title = Font(name=st["font"], size=st["title_size"], bold=True, color=st["title_color"])
        self.fill = PatternFill("solid", fgColor=st["header_fill"])
        self.sub = PatternFill("solid", fgColor="E2E8F0")
        thin = Side(style="thin", color="CBD5E1")
        self.border = Border(left=thin, right=thin, top=thin, bottom=thin)

    def title(self, text, width=8):
        c = self.ws.cell(self.row, 1, text)
        c.font, c.fill = self.f_title, self.fill
        for j in range(2, width + 1):
            self.ws.cell(self.row, j).fill = self.fill
        self.row += 2

    def note(self, text):
        c = self.ws.cell(self.row, 1, text)
        c.font = Font(name=self.st["font"], size=self.st["size"], bold=False, italic=True, color="475569")
        self.row += 1

    def table(self, rows, cols, labels=None, n=None, scales=True):
        rows = rows[:n] if n else rows
        if not rows:
            self.note("No data for this table.")
            self.row += 1
            return
        labels = labels or [label(c) for c in cols]
        top = self.row
        for j, lab in enumerate(labels, 1):
            c = self.ws.cell(self.row, j, lab)
            c.font, c.fill, c.border = self.f_data, self.sub, self.border
            c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        self.row += 1
        for x in rows:
            for j, col in enumerate(cols, 1):
                v = x.get(col)
                if col == "month" and isinstance(v, (int, float)) and 1 <= v <= 12:
                    v = MONTHS[int(v)]
                c = self.ws.cell(self.row, j, v)
                c.font, c.border = self.f_data, self.border
                base = col.split("_20")[0] if "_20" in col else col
                fm = self.st["formats"]
                if base in MONEY or col.startswith("rev_native") or col.startswith("native_"):
                    c.number_format = fm["money"] if not (col.startswith("rev_native") or col.startswith("native_")) else "#,##0"
                elif base in PCT or col.endswith("change_pct"):
                    c.number_format = fm["pct"]
                elif base in RATIO:
                    c.number_format = fm["ratio"]
                elif isinstance(v, (int, float)):
                    c.number_format = fm["count"]
            self.row += 1
        if scales and len(rows) >= 3:
            for j, col in enumerate(cols, 1):
                base = col.split("_20")[0] if "_20" in col else col
                rng = f"{get_column_letter(j)}{top + 1}:{get_column_letter(j)}{self.row - 1}"
                if base in GOOD or base in BAD:
                    s = self.st["good_scale"] if base in GOOD else self.st["bad_scale"]
                    self.ws.conditional_formatting.add(rng, ColorScaleRule(start_type="min", start_color=s[0], mid_type="percentile",
                                                                           mid_value=50, mid_color=s[1], end_type="max", end_color=s[2]))
        self.row += 1

    def kv(self, pairs):
        for k, v, kind in pairs:
            a = self.ws.cell(self.row, 1, k)
            b = self.ws.cell(self.row, 2, v)
            a.font = b.font = self.f_data
            a.fill = self.sub
            a.border = b.border = self.border
            b.number_format = {"money": self.st["formats"]["money"], "pct": self.st["formats"]["pct"], "ratio": "0.00"}.get(kind, "#,##0")
            self.row += 1
        self.row += 1

    def finish(self):
        for col in self.ws.columns:
            letter = get_column_letter(col[0].column)
            width = max((len(str(c.value)) for c in col if c.value is not None and c.row > 1 or (c.value and c.row == 1 and len(str(c.value)) < 30)), default=8)
            self.ws.column_dimensions[letter].width = min(max(10, width * 1.15 + 2), 60)
        self.ws.sheet_view.showGridLines = False


def pivot_rows(rows):
    return rows, [k for k in (rows[0].keys() if rows else [])]


def build(metrics, narrative, period, cfg, out):
    st = cfg["workbook"]
    b = metrics["breakdowns"][str(period)] if str(period) in metrics["breakdowns"] else metrics["breakdowns"][period]
    monthly = metrics["monthly"].get(str(period)) or metrics["monthly"].get(period)
    tot = metrics["totals"].get(str(period)) or metrics["totals"].get(period)
    findings = [f for f in metrics["findings"] if str(f.get("period")) in (str(period), "None")]
    n = narrative or {}
    wb = Workbook()
    wb.remove(wb.active)

    s = Sheet(wb, "Executive Dashboard", st)
    s.title(f"{metrics['client']} · {period} Executive Dashboard ({metrics['base_currency']})", 14)
    s.kv([("Ad spend", tot["spend"], "money"), ("Inquiries", tot["inquiries"], "count"), ("Won deals", tot["won"], "count"),
          ("Revenue", tot["revenue"], "money"), ("AOV", tot["aov"], "money"), ("CAC", tot["cac"], "money"),
          ("ROAS", tot["roas"], "ratio"), ("Inquiry→won", tot["cvr_inquiry"], "pct"), ("Close rate", tot["close_rate"], "pct")])
    cols = ["month", "spend", "leads", "messages", "inquiries", "won", "lost", "cvr_inquiry"] + \
           sorted(k for k in monthly[0] if k.startswith("rev_native")) + ["revenue", "cac", "roas"] if monthly else []
    s.table(monthly, cols)
    s.finish()

    s = Sheet(wb, "Sales Team Performance", st)
    s.title("Sales team performance (owners verified against start dates)", 8)
    s.table(b["owners"], ["owner", "won", "lost", "close_rate", "revenue", "aov"])
    s.note("Owner timeline: first and last deal each owner holds in this period. Check against real hire dates.")
    s.table(b["owner_timeline"], ["owner", "first_created", "last_created", "deals"], scales=False)
    r, c = pivot_rows(b["owner_month"])
    s.note("Won deals per month by owner")
    s.table(r, c)
    s.finish()

    s = Sheet(wb, "Sales Channel Attribution", st)
    s.title("Where deals close", 8)
    s.table(b["channels"], ["channel", "won", "share_won", "revenue", "share_revenue", "aov"])
    if n.get("channel_story"):
        s.note(n["channel_story"])
    r, c = pivot_rows(b["channel_month"])
    s.note("Won deals per month by closing channel")
    s.table(r, c)
    s.finish()

    s = Sheet(wb, "Country Performance", st)
    s.title("Country performance and economics", 10)
    cc = ["country", "won", "share_won", "revenue", "share_revenue", "aov"] + [k for k in (b["countries"][0] if b["countries"] else {}) if k.isupper()]
    s.table(b["countries"], cc, n=25)
    if n.get("geo_story"):
        s.note(n["geo_story"])
    r, c = pivot_rows(b["country_month"])
    s.note("Won deals per month by country")
    s.table(r, c[:12])
    s.finish()

    s = Sheet(wb, "Frequency & Ad Fatigue", st)
    lo, hi = cfg["detectors"]["frequency"]["sweet_spot"]
    s.title(f"Frequency and fatigue (sweet spot {lo}–{hi})", 9)
    fr = [dict(x, status="Fatigue" if (x.get("frequency") or 0) > hi else ("Sweet spot" if (x.get("frequency") or 0) >= lo else "Building")) for x in monthly]
    s.table(fr, ["month", "spend", "reach", "impressions", "frequency", "cvr_inquiry", "cac", "status"])
    s.finish()

    s = Sheet(wb, "Frequency by Ad Copy", st)
    s.title("Ad-level telemetry (top 100 by spend)", 11)
    s.table(b["ads"], ["campaign", "adset", "ad", "archetype", "spend", "impressions", "reach", "frequency", "leads", "messages", "cpl", "fatigue_status"], n=100)
    s.finish()

    s = Sheet(wb, "Top Winning Courses", st)
    s.title("Top products by revenue", 8)
    pc = ["product", "won", "revenue", "avg_price"] + [k for k in (b["products"][0] if b["products"] else {}) if k.startswith("native_")]
    s.table(b["products"], pc, n=40)
    s.note("Deals with several products split their amount equally across them.")
    s.finish()

    s = Sheet(wb, "Top Winning Content Style", st)
    s.title("Creative archetypes (classified from ad names)", 7)
    rows = [dict(x, takeaway=(n.get("content_takeaways") or {}).get(x["archetype"], "")) for x in b["archetypes"]]
    s.table(rows, ["archetype", "ads", "spend", "leads", "messages", "cpl", "takeaway"])
    s.finish()

    s = Sheet(wb, "Product Performance Matrix", st)
    s.title("Top 5 products each month", 5)
    s.table(b["product_month"], ["month", "product", "won", "revenue"])
    s.finish()

    s = Sheet(wb, "Campaign-Level Ad Insights", st)
    s.title("Campaigns", 10)
    rows = [dict(x, takeaway=(n.get("campaign_takeaways") or {}).get(x["campaign"], "")) for x in b["campaigns"]]
    s.table(rows, ["campaign", "first", "last", "spend", "leads", "messages", "cpl", "won", "revenue", "roas", "takeaway"], n=60)
    s.note("Won/revenue appear only where the CRM campaign field matches the ad campaign name.")
    s.finish()

    s = Sheet(wb, "Campaign Evolution", st)
    s.title("Strategic pivots over time", 4)
    s.table(n.get("evolution") or [{"quarter": "Pending narrative"}], ["quarter", "pivot", "evidence"], scales=False)
    s.table(n.get("pivots") or [], ["title", "period", "month", "evidence", "lesson"], scales=False)
    s.finish()

    s = Sheet(wb, "Strategic Recommendations", st)
    s.title("Growth pillars and mandates", 4)
    pil = [{"pillar": p.get("name"), "actions": " · ".join(p.get("actions", [])), "kpi": p.get("kpi")} for p in n.get("pillars", [])]
    s.table(pil or [{"pillar": "Pending narrative"}], ["pillar", "actions", "kpi"], scales=False)
    s.table([{"mandate": m} for m in n.get("mandates", [])], ["mandate"], scales=False)
    s.note("Evidence flags from the audit engine")
    s.table([{"severity": f["severity"], "pattern": f["pattern"], "month": f.get("month"), "hint": f["hint"]} for f in findings],
            ["severity", "pattern", "month", "hint"], scales=False)
    s.finish()

    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str) and len(c.value) > 60:
                    c.alignment = Alignment(wrap_text=True, vertical="top")
    path = os.path.join(out, f"{cfg['file_prefix']}_{period}.xlsx")
    wb.save(path)
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--metrics", required=True)
    ap.add_argument("--narrative")
    ap.add_argument("--period", help="default: every period in metrics")
    ap.add_argument("--profile")
    ap.add_argument("--out")
    a = ap.parse_args()
    cfg = load_settings(a.profile)
    m = read_json(a.metrics)
    n = read_json(a.narrative) if a.narrative and os.path.exists(a.narrative) else None
    if not n:
        print("note: no narrative given, tabs 10-12 will say 'Pending narrative'")
    out = a.out or os.path.dirname(a.metrics)
    for p in ([a.period] if a.period else m["periods"]):
        print("wrote", build(m, n, p, cfg, out))


if __name__ == "__main__":
    main()
