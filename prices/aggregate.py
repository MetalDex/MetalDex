#!/usr/bin/env python3
"""Turn the price history into docs/data/prices.json for the tracker's Market view.

    python3 prices/aggregate.py            # then python3 scripts/build.py to put it in docs/index.html

For every figure:
  guide    median sale price over the last 30 days (90 days when there are fewer than 5 recent sales),
           outliers removed
  chg      % change: median of the last 30 days vs. the 60 days before (needs 3+ sales in each)
  n30/n90  number of sales
  new/used medians by condition, low/high (10th/90th percentile), last sale
  weeks    weekly medians for the chart (last 52 weeks)
  asks     cheapest second-hand buy-it-now listings in the latest snapshot
  shops    shop prices (in stock or pre-order) in the latest snapshot
  sales    the sales of the last 90 days behind the guide price (date, price, condition, source, title, id, outlier)
Corrections in prices/data/corrections.csv (from "Wrong figure?" reports and audits) are applied first.
plus a gallery-wide index: each week, the median across figures of (that week's price / the figure's median
over the whole history) ×100, so 100 means "typical price" and the index rises when the market as a whole does.
"""
import csv
import json
import statistics
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA = HERE / "data"
OUT = ROOT / "docs" / "data" / "prices.json"

SOURCES = {
    "yahoo": ("Yahoo! Auctions", "https://auctions.yahoo.co.jp/jp/auction/{id}"),
    "mercari": ("Mercari", "https://jp.mercari.com/item/{id}"),
    "ebay": ("eBay", "https://www.ebay.com/itm/{id}"),
    "hobbysearch": ("Hobby Search", "https://www.1999.co.jp/{id}"),
    "estore": ("Square Enix e-STORE", "https://store.jp.square-enix.com/estore/g/g{id}/"),
    "sootang": ("Sootang", "https://www.sootang.jp/products/{id}"),
    "amiami": ("AmiAmi", "https://www.amiami.jp/top/detail/detail?gcode={id}"),
}


def read_csv(p):
    if not p.exists():
        return []
    with open(p, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def pct(xs, q):
    xs = sorted(xs)
    if not xs:
        return None
    k = (len(xs) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return round(xs[lo] + (xs[hi] - xs[lo]) * (k - lo))


def med(xs):
    return round(statistics.median(xs)) if xs else None


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def corrections():
    """(source, listing_id) -> correct figure id, or "" to leave the listing out."""
    out = {}
    for r in read_csv(DATA / "corrections.csv"):
        fid = r["figure_id"].strip()
        out[(r["source"].strip(), r["listing_id"].strip())] = "" if fid in ("", "exclude", "none") else fid
    return out


def apply_corrections(rows, corr):
    kept = []
    for r in rows:
        key = (r["source"], r["listing_id"])
        if key in corr:
            if not corr[key]:
                continue
            r = dict(r, figure_id=corr[key])
        kept.append(r)
    return kept


def audit_line():
    """The newest finished spot-check (prices/audit.py), as a sentence for the tracker."""
    import sys
    sys.path.insert(0, str(ROOT))
    from prices.audit import latest
    res = latest()
    if not res:
        return None
    d, n, right = res
    return f"Matching spot-checked by hand on {n} random sales (latest {d}): {right} right ({right / n:.1%}); the misses were fixed."


def main(today: date | None = None):
    today = today or date.today()
    corr = corrections()
    links = json.loads((DATA / "links.json").read_text(encoding="utf-8")) if (DATA / "links.json").exists() else {}
    import sys
    sys.path.insert(0, str(ROOT))
    from prices.check_links import listing_url

    def live_url(r):
        st = links.get(f"{r['source']}:{r['listing_id']}")
        return listing_url(r["source"], r["listing_id"]) if st and st[0] == "ok" else ""
    sales = apply_corrections([r for r in read_csv(DATA / "sales.csv") if r["sold_on"]], corr)
    by_fig = {}
    for r in sales:
        by_fig.setdefault(r["figure_id"], []).append(r)

    # outliers: drop sales below a third or above three times the figure's overall median
    clean = {}
    dropped = 0
    outliers = set()
    for fid, rows in by_fig.items():
        m = statistics.median(float(r["price_jpy"]) for r in rows)
        keep = [r for r in rows if m / 3 <= float(r["price_jpy"]) <= m * 3]
        outliers |= {id(r) for r in rows if not (m / 3 <= float(r["price_jpy"]) <= m * 3)}
        dropped += len(rows) - len(keep)
        clean[fid] = keep

    snap_files = sorted(p for p in (DATA / "listings").glob("*.csv") if not p.name.endswith(".counts.csv"))
    # use each source's newest snapshot only
    newest = {}
    for p in snap_files:
        for r in read_csv(p):
            newest[(r["source"], r["kind"])] = p.stem
    current = {}
    for p in snap_files:
        for r in apply_corrections(read_csv(p), corr):
            if newest[(r["source"], r["kind"])] == p.stem:
                current.setdefault(r["figure_id"], []).append(r)

    n_listed = {}
    for p in sorted((DATA / "listings").glob("*.counts.csv")):
        for r in read_csv(p):
            if newest.get((r["source"], r["kind"])) == p.name.split(".")[0]:
                n_listed[(r["figure_id"], r["kind"])] = n_listed.get((r["figure_id"], r["kind"]), 0) + int(r["n"])
    d90, d30 = today - timedelta(days=90), today - timedelta(days=30)
    start_w = week_start(today - timedelta(weeks=51))
    figures = {}
    rel_by_week = {}
    for fid in sorted(set(clean) | set(current)):
        rows = clean.get(fid, [])
        dated = [(date.fromisoformat(r["sold_on"]), float(r["price_jpy"]), r) for r in rows]
        last90 = [p for d, p, _ in dated if d >= d90]
        last30 = [p for d, p, _ in dated if d >= d30]
        prev = [p for d, p, _ in dated if d90 <= d < d30]
        # guide price: last 30 days when there are enough sales, otherwise the last 90 days
        basis = 30 if len(last30) >= 5 else 90
        guide = med(last30 if basis == 30 else last90)
        f = {"guide": guide, "basis": basis if guide else None, "n30": len(last30), "n90": len(last90)}
        if len(last30) >= 3 and len(prev) >= 3:
            f["chg"] = round((statistics.median(last30) / statistics.median(prev) - 1) * 100, 1)
        if last90:
            f["low"], f["high"] = pct(last90, 0.1), pct(last90, 0.9)
            f["new"] = med([p for d, p, r in dated if d >= d90 and r["cond"] == "new"])
            f["used"] = med([p for d, p, r in dated if d >= d90 and r["cond"] == "used"])
        if dated:
            d, p, r = max(dated, key=lambda x: (x[0], x[2]["listing_id"]))
            f["last"] = [d.isoformat(), round(p), r["source"]]
            f["n_all"] = len(dated)
        # the sales behind the price, newest first, outliers included but marked (shown greyed out)
        recent = sorted((r for r in by_fig.get(fid, []) if r["sold_on"] >= d90.isoformat()),
                        key=lambda r: (r["sold_on"], r["listing_id"]), reverse=True)
        # the newest few get a link to their listing page, but only if prices/check_links.py found it still opens
        f["sales"] = [[r["sold_on"], round(float(r["price_jpy"])), {"new": "n", "used": "u"}.get(r["cond"], "x"),
                       r["source"], (r.get("title") or "")[:70], r["listing_id"], 1 if id(r) in outliers else 0,
                       live_url(r)] for r in recent]
        weeks = {}
        for d, p, _ in dated:
            if d >= start_w:
                weeks.setdefault(week_start(d).isoformat(), []).append(p)
        f["weeks"] = [[w, med(ps), len(ps)] for w, ps in sorted(weeks.items())]
        if dated:
            overall = statistics.median(p for _, p, _ in dated)
            for w, ps in weeks.items():
                rel_by_week.setdefault(w, []).append(statistics.median(ps) / overall)
        asks, shops = [], []
        for r in current.get(fid, []):
            name, url = SOURCES.get(r["source"], (r["source"], ""))
            # auction and flea-market listings disappear when they end, so only shop listings get a link
            item = [r["source"], round(float(r["price_jpy"])), r["cond"] if r["kind"] == "ask" else r["extra"],
                    url.format(id=r["listing_id"]) if url and r["kind"] == "retail" else ""]
            if r["kind"] == "ask":
                # a "buy now" far below recent sales is usually a different item (keychain, junk, parts)
                if guide and float(r["price_jpy"]) < guide * 0.4:
                    continue
                asks.append(item)
            elif r["extra"] in ("in", "pre"):
                shops.append(item)
        f["asks"] = sorted(asks, key=lambda x: x[1])[:6]
        f["n_asks"] = n_listed.get((fid, "ask"), len(asks))
        f["shops"] = sorted(shops, key=lambda x: x[1])
        figures[fid] = f

    index = [[w, round(statistics.median(v) * 100, 1), len(v)] for w, v in sorted(rel_by_week.items()) if len(v) >= 5]
    first = min((r["sold_on"] for r in sales), default=None)
    out = {
        "generated": today.isoformat(),
        "since": first,
        "sales": len(sales),
        "outliers_dropped": dropped,
        "corrections": len(corr),
        "links_checked": max((v[1] for v in links.values() if v[0] == "ok"), default=None),
        "audit": audit_line(),
        "snapshot": max(newest.values(), default=None),
        "sources": {k: v[0] for k, v in SOURCES.items()},
        "fx": (read_csv(DATA / "fx.csv") or [{}])[-1],
        "rates": json.loads((DATA / "rates.json").read_text(encoding="utf-8")) if (DATA / "rates.json").exists() else None,
        "index": index,
        "figures": figures,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    priced = sum(1 for f in figures.values() if f["guide"])
    print(f"wrote {OUT.relative_to(ROOT)}: {len(sales)} sales since {first}, guide prices for {priced} figures, "
          f"{dropped} outliers dropped, listings snapshot {out['snapshot']}")


if __name__ == "__main__":
    main()
