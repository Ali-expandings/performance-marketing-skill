#!/usr/bin/env python3
"""The skill's memory. Lessons are logged after every run; ones that keep coming back get promoted
into rules the next run reads, or into detector thresholds the scripts use.

  learn.py add --kind mistake|pattern|rule|threshold --text "..." [--evidence "..."] [--profile p.json]
  learn.py list                 show lessons, most seen first
  learn.py review               lessons seen 2+ times that are not promoted yet
  learn.py promote ID           move a lesson into references/learned-rules.md
  learn.py set-threshold detectors.lead_quality_trap.spike_ratio 1.4 --reason "..."
  learn.py history              score trend from learnings/runs.jsonl

Lessons must be general (no client names, people, or money figures): the skill folder is shared.
"""
import argparse
import datetime
import difflib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import SKILL_DIR, read_json  # noqa: E402

LESSONS = os.path.join(SKILL_DIR, "learnings", "lessons.json")
RULES = os.path.join(SKILL_DIR, "references", "learned-rules.md")
CONFIG = os.path.join(SKILL_DIR, "config", "defaults.json")
CHANGES = os.path.join(SKILL_DIR, "learnings", "CHANGELOG.md")


def load():
    return read_json(LESSONS) if os.path.exists(LESSONS) else []


def save(items):
    os.makedirs(os.path.dirname(LESSONS), exist_ok=True)
    with open(LESSONS, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def changelog(text):
    with open(CHANGES, "a", encoding="utf-8") as f:
        f.write(f"- {datetime.date.today().isoformat()}: {text}\n")


def scrub(text, profile):
    """Refuse text that would leak client data into the shared skill."""
    probs = []
    if re.search(r"[$€£]\s?\d|\d[\d,]{3,}\s?(egp|usd|sar|aed|k\b)", text, re.I):
        probs.append("contains money figures")
    if profile and os.path.exists(profile):
        p = read_json(profile)
        names = [p.get("client", "")] + [o.get("name", "") for o in p.get("owners", [])] + list(p.get("owner_names", {}).values())
        hits = [x for x in names if x and len(x) > 2 and x.lower() in text.lower()]
        if hits:
            probs.append(f"names client/people {hits}")
    return probs


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("add")
    p.add_argument("--kind", required=True, choices=["mistake", "pattern", "rule", "threshold"])
    p.add_argument("--text", required=True)
    p.add_argument("--evidence", default="")
    p.add_argument("--profile")
    sp.add_parser("list")
    sp.add_parser("review")
    p = sp.add_parser("promote")
    p.add_argument("id", type=int)
    p = sp.add_parser("set-threshold")
    p.add_argument("key")
    p.add_argument("value")
    p.add_argument("--reason", required=True)
    sp.add_parser("history")
    a = ap.parse_args()
    items = load()

    if a.cmd == "add":
        probs = scrub(a.text + " " + a.evidence, a.profile)
        if probs:
            sys.exit(f"refused: lesson {', '.join(probs)}. Rewrite it as a general pattern.")
        for it in items:
            if it["kind"] == a.kind and difflib.SequenceMatcher(None, it["text"].lower(), a.text.lower()).ratio() > 0.75:
                it["seen"] += 1
                it["last"] = datetime.date.today().isoformat()
                if a.evidence:
                    it["evidence"] = (it.get("evidence", []) + [a.evidence])[-5:]
                save(items)
                print(f"lesson #{it['id']} seen {it['seen']} times" + (" -> ready to promote (run: learn.py review)" if it["seen"] >= 2 and not it["promoted"] else ""))
                return
        new = {"id": max([i["id"] for i in items], default=0) + 1, "kind": a.kind, "text": a.text, "seen": 1,
               "first": datetime.date.today().isoformat(), "last": datetime.date.today().isoformat(),
               "evidence": [a.evidence] if a.evidence else [], "promoted": False}
        items.append(new)
        save(items)
        print(f"lesson #{new['id']} added")
    elif a.cmd == "list":
        for it in sorted(items, key=lambda x: -x["seen"]):
            print(f"#{it['id']} [{it['kind']}] x{it['seen']} {'(promoted) ' if it['promoted'] else ''}{it['text']}")
    elif a.cmd == "review":
        ready = [i for i in items if i["seen"] >= 2 and not i["promoted"]]
        for it in ready:
            print(f"#{it['id']} [{it['kind']}] x{it['seen']}: {it['text']}  evidence: {it.get('evidence')}")
        print(f"{len(ready)} lesson(s) ready. Promote with: learn.py promote ID" if ready else "nothing ready")
    elif a.cmd == "promote":
        it = next((i for i in items if i["id"] == a.id), None)
        if not it:
            sys.exit("no such lesson")
        with open(RULES, "a", encoding="utf-8") as f:
            f.write(f"- [{it['kind']}] {it['text']} (seen {it['seen']}x, since {it['first']})\n")
        it["promoted"] = True
        save(items)
        changelog(f"promoted lesson #{it['id']} to learned-rules: {it['text']}")
        print(f"promoted #{it['id']} into references/learned-rules.md")
    elif a.cmd == "set-threshold":
        cfg = read_json(CONFIG)
        node, keys = cfg, a.key.split(".")
        for k in keys[:-1]:
            node = node[k]
        old = node.get(keys[-1])
        try:
            val = json.loads(a.value)
        except json.JSONDecodeError:
            val = a.value
        node[keys[-1]] = val
        with open(CONFIG, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        changelog(f"threshold {a.key}: {old} -> {val}. Reason: {a.reason}")
        print(f"{a.key}: {old} -> {val}. Now run scripts/selftest.sh to confirm nothing broke.")
    elif a.cmd == "history":
        log = os.path.join(SKILL_DIR, "learnings", "runs.jsonl")
        if not os.path.exists(log):
            print("no runs logged yet")
            return
        for line in open(log, encoding="utf-8"):
            r = json.loads(line)
            print(f"{r['date']} {r['label']:<20} {r['score']:>3}  {r['parts']}")


if __name__ == "__main__":
    main()
