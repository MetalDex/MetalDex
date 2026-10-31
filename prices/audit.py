#!/usr/bin/env python3
"""Spot-check the matching: draw random sales, check each title by hand, publish the accuracy.

    python3 prices/audit.py sample [--n 200] [--seed 2026]   # writes prices/data/audits/<date>.csv to fill in
    python3 prices/audit.py summary [file]                    # accuracy of a filled-in audit

Fill in the "verdict" column for every row: ok (right figure), wrong (a different figure: put the right id in
"correct_figure"), or not (not a single figure of this series: set, other line, stand, damaged...).
Wrong and not rows should also go into prices/data/corrections.csv (prices/correct.py). Once every row has a
verdict, prices/aggregate.py shows the result in the tracker ("Matching checked on 200 random sales ...").
"""
import argparse
import csv
import random
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIR = ROOT / "prices" / "data" / "audits"
COLS = ["source", "listing_id", "figure_id", "sold_on", "price_jpy", "title", "verdict", "correct_figure", "note"]


def read(p):
    with open(p, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def result(rows):
    """(checked, right, sentence) for a fully filled-in audit, else None."""
    if not rows or any(not r["verdict"].strip() for r in rows):
        return None
    right = sum(r["verdict"].strip() == "ok" for r in rows)
    return len(rows), right


def latest():
    """All finished audits together: (newest date, checked, right) or None."""
    n = right = 0
    newest = None
    for p in sorted(DIR.glob("*.csv")):
        res = result(read(p))
        if res:
            n, right, newest = n + res[0], right + res[1], p.stem[:10]
    return (newest, n, right) if n else None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["sample", "summary"])
    ap.add_argument("file", nargs="?")
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--seed", type=int, default=None)
    a = ap.parse_args()
    if a.cmd == "sample":
        sales = [r for r in read(ROOT / "prices" / "data" / "sales.csv") if r["sold_on"] and r.get("title")]
        rnd = random.Random(a.seed)
        pick = rnd.sample(sales, min(a.n, len(sales)))
        DIR.mkdir(parents=True, exist_ok=True)
        out = DIR / f"{date.today().isoformat()}.csv"
        with open(out, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLS, lineterminator="\n", extrasaction="ignore")
            w.writeheader()
            for r in sorted(pick, key=lambda r: (r["figure_id"], r["sold_on"])):
                w.writerow({**r, "verdict": "", "correct_figure": "", "note": ""})
        print(f"wrote {out.relative_to(ROOT)}: {len(pick)} sales drawn from {len(sales)} with titles")
        return 0
    p = Path(a.file) if a.file else max(DIR.glob("*.csv"))
    rows = read(p)
    res = result(rows)
    if not res:
        print(f"{p.name}: {sum(1 for r in rows if not r['verdict'].strip())} of {len(rows)} rows still need a verdict")
        return 1
    n, right = res
    print(f"{p.name}: {right} of {n} right ({right / n:.1%})")
    for r in rows:
        if r["verdict"].strip() != "ok":
            print(f"  {r['verdict']:6} {r['figure_id']:28} -> {r['correct_figure'] or '-':24} {r['title'][:60]}  {r['note']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
