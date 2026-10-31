#!/usr/bin/env python3
"""Add collector results to the price history.

    python3 prices/ingest.py --usdjpy 152.3 results/yahoo-sold.json results/mercari-sold.json ...
    python3 prices/ingest.py --matcher-data        # rewrite prices/data/matcher.json after catalogue changes

Each input is the JSON a collector produced (prices/collectors/browser.js or prices/collect.py).
Writes, under prices/data/:
  sales.csv                 every completed sale ever seen (one row per listing; re-runs never duplicate)
  listings/YYYY-MM-DD.csv   what was for sale on that day (second-hand buy-it-now asks and shop prices)
  fx.csv                    USD→JPY rate used for each run (Mercari shows US$ prices outside Japan)

Mercari doesn't show when an item sold. The first Mercari run is stored as a baseline (no date, not used
for prices); after that, a newly seen sold item is dated to the run that first saw it.
"""
import argparse
import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA = HERE / "data"
SALES = DATA / "sales.csv"
FX = DATA / "fx.csv"
# title: the listing's title as the seller wrote it, so anyone can check why it was matched to that figure
SALES_COLS = ["source", "listing_id", "figure_id", "sold_on", "price", "currency", "price_jpy", "cond", "extra", "first_seen", "title"]
LIST_COLS = ["source", "kind", "listing_id", "figure_id", "price", "currency", "price_jpy", "cond", "extra", "title"]


def read_csv(p):
    if not p.exists():
        return []
    with open(p, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(p, cols, rows):
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n", restval="")
        w.writeheader()
        w.writerows(rows)


COND = {"n": "new", "": "used", "x": "unknown", "u": "used", "new": "new", "used": "used", "unknown": "unknown"}


def read_pack(text):
    """Read the compact text written by __mmgPack() in prices/collectors/browser.js.

    #mmgpack2 <src> <run>          header
    #stats {...}                   collector counts
    #counts fig:n ...              listings per figure, when only the cheapest few are included
    #u <status> <price> <title>    unmatched samples
    O <figure> day:price[c] ...    older sales without listing ids (day = days before the run; c: n new, x unknown, else used)
    R kind,id,figure,price,currency,date,cond,extra   (or the 6-field sold form: id,figure,price,date,cond,extra)
                                   optionally followed by a tab and the listing title
    """
    from datetime import date, timedelta
    lines = text.splitlines()
    _, src, run = lines[0].split()
    res = {"src": src, "run": run, "stats": {}, "records": [], "unmatched": [], "error": None}
    run_d = date.fromisoformat(run)
    for ln in lines[1:]:
        if ln.startswith("#stats "):
            res["stats"] = json.loads(ln[7:])
        elif ln.startswith("#counts "):
            res["counts"] = {k: int(v) for k, v in (x.rsplit(":", 1) for x in ln[8:].split())}
        elif ln.startswith("#error "):
            res["error"] = ln[7:]
        elif ln.startswith("#u "):
            st, price, title = (ln[3:].split(" ", 2) + ["", ""])[:3]
            res["unmatched"].append([st, "", title, price])
        elif ln.startswith("O "):
            _, fid, *items = ln.split()
            # the same sale can appear twice when two search queries both found it; the second query's
            # results start a new run of ascending days, so drop exact repeats found after the first run
            seen, runs, prev = {}, 0, -1
            for n, it in enumerate(items):
                d, rest = it.split(":")
                c = rest[-1] if rest[-1].isalpha() else ""
                price = rest[:-1] if c else rest
                key = (d, price, c)
                if int(d) < prev:
                    runs += 1
                prev = int(d)
                if runs and seen.get(key, 0) > 0:
                    seen[key] -= 1
                    continue
                if not runs:
                    seen[key] = seen.get(key, 0) + 1
                sold = (run_d - timedelta(days=int(d))).isoformat()
                res["records"].append(["sold", f"old:{fid}:{sold}:{price}:{n}", fid, int(price), "JPY", sold, COND[c], ""])
        elif ln.startswith("R "):
            body, _, title = ln[2:].partition("\t")
            f = body.split(",")
            if len(f) == 6:
                lid, fid, price, d, c, extra = f
                res["records"].append(["sold", lid, fid, float(price), "JPY", d, COND[c], extra, title])
            else:
                kind, lid, fid, price, cur, d, c, extra = f[:8]
                res["records"].append([kind, lid, fid, float(price), cur or "JPY", d, COND[c], extra, title])
    return res


def load(path):
    text = Path(path).read_text(encoding="utf-8")
    return read_pack(text) if text.startswith("#mmgpack2") else json.loads(text)


def match_raw(res):
    """Match collector output that carries titles instead of figure ids (small retail lists, prices/collect.py).
    raw rows: [kind, id, title, price, currency, date, cond_hint, extra, jan]"""
    sys.path.insert(0, str(ROOT))
    from prices.matcher import Matcher
    m = Matcher.from_json(ROOT / "docs" / "data" / "figures.json")
    jan = {r["jan"]: f["id"] for f in m.figs.values() for r in f.get("releases", [])}
    st = {"seen": 0, "ok": 0, "lot": 0, "excluded": 0, "uncertain": 0, "none": 0}
    res.setdefault("records", [])
    res.setdefault("unmatched", [])
    for kind, lid, title, price, cur, d, hint, extra, j in res["raw"]:
        st["seen"] += 1
        r = {"status": "ok", "id": jan[j], "cond": "new"} if j in jan else m.match(title, hint, require_series=kind != "retail")
        st[r["status"]] += 1
        if r["status"] == "ok":
            res["records"].append([kind, str(lid), r["id"], price, cur, d, r["cond"], extra, title])
        elif r["status"] in ("none", "uncertain"):
            res["unmatched"].append([r["status"], str(lid), title[:90], price])
    res["stats"] = st


def write_matcher_data():
    sys.path.insert(0, str(ROOT))
    from prices.matcher import Matcher, export
    m = Matcher.from_json(ROOT / "docs" / "data" / "figures.json")
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "matcher.json").write_text(json.dumps(export(m), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote prices/data/matcher.json ({len(m.jp)} Japanese and {len(m.en)} English names)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*")
    ap.add_argument("--usdjpy", type=float, help="USD→JPY rate for this run (needed for Mercari/eBay US$ prices)")
    ap.add_argument("--matcher-data", action="store_true", help="rewrite prices/data/matcher.json and exit")
    a = ap.parse_args()
    if a.matcher_data:
        write_matcher_data()
        return 0

    sales = read_csv(SALES)
    keys = {(r["source"], r["listing_id"]) for r in sales}
    has_source = {r["source"] for r in sales}
    fx = read_csv(FX)
    listings = {}
    counts = {}
    summary = []
    for path in a.files:
        res = load(path)
        if res.get("raw"):
            match_raw(res)
        src_full, run = res["src"], res["run"]
        source = src_full.split("-")[0]
        if res.get("error"):
            summary.append(f"{src_full}: collector error: {res['error']}")
        needs_fx = any(r[4] != "JPY" for r in res["records"])
        if needs_fx and not a.usdjpy:
            sys.exit(f"{path}: has US$ prices; pass --usdjpy")
        if a.usdjpy and not any(r["date"] == run for r in fx):
            fx.append({"date": run, "usdjpy": a.usdjpy})
        baseline = source == "mercari" and src_full.endswith("sold") and "mercari" not in has_source
        added = 0
        for rec in res["records"]:
            kind, lid, fid, price, cur, date, cond, extra = rec[:8]
            title = " ".join(str(rec[8]).split())[:120] if len(rec) > 8 else ""
            if price in (None, "", 0):
                continue
            jpy = round(float(price) * (a.usdjpy if cur == "USD" else 1))
            if kind == "sold":
                if (source, lid) in keys:
                    continue
                keys.add((source, lid))
                sold_on = date or ("" if baseline else run)
                sales.append({"source": source, "listing_id": lid, "figure_id": fid, "sold_on": sold_on, "price": price,
                              "currency": cur, "price_jpy": jpy, "cond": cond, "extra": extra, "first_seen": run,
                              "title": title})
                added += 1
            else:
                listings.setdefault(run, {}).setdefault((source, kind), {})[lid] = {
                    "source": source, "kind": kind, "listing_id": lid, "figure_id": fid, "price": price, "currency": cur,
                    "price_jpy": jpy, "cond": cond, "extra": extra, "title": title}
                added += 1
        if res.get("counts"):
            kind = "ask" if src_full.endswith("ask") else "retail"
            counts.setdefault(run, {})[(source, kind)] = res["counts"]
        st = res.get("stats", {})
        summary.append(f"{src_full} ({run}): {st.get('seen', '?')} listings seen, {st.get('ok', '?')} matched, "
                       f"{st.get('lot', 0)} lots, {st.get('excluded', 0)} excluded, {st.get('uncertain', 0)} uncertain, "
                       f"{st.get('none', 0)} unmatched; {added} rows added" + (" (Mercari baseline: undated)" if baseline else ""))
        if res.get("unmatched"):
            summary.append("  unmatched samples: " + " | ".join(f"{u[0]}:{u[2]}" for u in res["unmatched"][:15]))

    sales.sort(key=lambda r: (r["sold_on"] or "0000", r["source"], r["listing_id"]))
    write_csv(SALES, SALES_COLS, sales)
    fx.sort(key=lambda r: r["date"])
    write_csv(FX, ["date", "usdjpy"], fx)
    for run, groups in listings.items():
        p = DATA / "listings" / f"{run}.csv"
        old = [r for r in read_csv(p) if (r["source"], r["kind"]) not in groups]  # replace re-collected sources
        rows = old + [r for g in groups.values() for r in g.values()]
        rows.sort(key=lambda r: (r["figure_id"], r["source"], int(float(r["price_jpy"]))))
        write_csv(p, LIST_COLS, rows)
    for run, groups in counts.items():
        p = DATA / "listings" / f"{run}.counts.csv"
        old = [r for r in read_csv(p) if (r["source"], r["kind"]) not in groups]
        rows = old + [{"source": s_, "kind": k_, "figure_id": f, "n": n} for (s_, k_), c in groups.items() for f, n in c.items()]
        write_csv(p, ["source", "kind", "figure_id", "n"], sorted(rows, key=lambda r: (r["figure_id"], r["source"])))
    print("\n".join(summary))
    print(f"sales.csv: {len(sales)} sales in total")
    return 0


if __name__ == "__main__":
    sys.exit(main())
