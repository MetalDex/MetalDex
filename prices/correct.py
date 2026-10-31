#!/usr/bin/env python3
"""Fix a wrong match: add a line to prices/data/corrections.csv (applied by every update).

    python3 prices/correct.py <listing id> <right figure id | exclude> "why" [--source yahoo] [--by "issue #12"]
    python3 prices/correct.py --list

Use the listing id from a "Wrong match" report (or the sale list in the tracker). "exclude" leaves the sale
out entirely (a set, another toy line, a stand...). Then rebuild: python3 prices/aggregate.py && python3 scripts/build.py
"""
import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORR = ROOT / "prices" / "data" / "corrections.csv"
COLS = ["source", "listing_id", "figure_id", "reason", "reported_by", "date"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("listing", nargs="?")
    ap.add_argument("figure", nargs="?", help='right figure id, or "exclude"')
    ap.add_argument("reason", nargs="?", default="")
    ap.add_argument("--source", default="yahoo")
    ap.add_argument("--by", default="", help="who reported it, e.g. an issue number")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    rows = list(csv.DictReader(open(CORR, encoding="utf-8"))) if CORR.exists() else []
    if a.list or not a.listing:
        for r in rows:
            print(f"{r['date']}  {r['source']}:{r['listing_id']:14} -> {r['figure_id'] or 'exclude':28} {r['reason']}")
        print(f"{len(rows)} corrections")
        return 0
    if not a.figure:
        sys.exit("give the right figure id, or exclude")
    ids = {f["id"] for f in json.loads((ROOT / "docs" / "data" / "figures.json").read_text(encoding="utf-8"))["figures"]}
    if a.figure != "exclude" and a.figure not in ids:
        sys.exit(f"unknown figure id {a.figure!r} (ids are in data/figures.csv)")
    sales = {(r["source"], r["listing_id"]): r for r in csv.DictReader(open(ROOT / "prices" / "data" / "sales.csv", encoding="utf-8"))}
    s = sales.get((a.source, a.listing))
    if s:
        print(f"sale: {s['sold_on']} ¥{float(s['price_jpy']):,.0f} counted for {s['figure_id']}  {s.get('title', '')[:80]}")
    else:
        print("(not in sales.csv; it may be a current listing, the correction applies to it too)")
    rows = [r for r in rows if (r["source"], r["listing_id"]) != (a.source, a.listing)]
    rows.append({"source": a.source, "listing_id": a.listing, "figure_id": a.figure, "reason": a.reason,
                 "reported_by": a.by, "date": date.today().isoformat()})
    with open(CORR, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print(f"saved: {a.source}:{a.listing} -> {a.figure}. Rebuild with: python3 prices/aggregate.py && python3 scripts/build.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
