#!/usr/bin/env python3
"""Check that the listing pages of each figure's most recent sales still open, so the tracker only links to live pages.

    python3 prices/check_links.py               # check what's due (run by prices/update.py)
    python3 prices/check_links.py --report      # show what's stored, no requests

For every figure, the newest sales (3 by default) get a link in the tracker, but only once their page has been
opened and found working. Results go to prices/data/links.json: {"<source>:<listing id>": ["ok"|"dead", "<date>"]}.
A working page is checked again after RECHECK_DAYS; a dead one is never checked again (sold listings don't come back).

Yahoo listings whose id starts with "z" are Yahoo! Flea Market items (paypayfleamarket.yahoo.co.jp), the rest are
Yahoo! Auctions. Standard library only.
"""
import argparse
import csv
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from prices.collect import fetch, progress  # noqa: E402

DATA = HERE / "data"
LINKS = DATA / "links.json"
PER_FIGURE = 3
RECHECK_DAYS = 7
DELAY = 5.0        # Yahoo starts refusing (429 / 500) after a few dozen quick page loads
MAX_PER_RUN = 60   # the rest are checked on later runs; figures without any working link go first
GONE = ("このオークションは削除されました", "このオークションは存在しません", "お探しの商品は見つかりません",
        "ページが見つかりません", "この商品は削除されました")


def listing_url(source, lid):
    if source == "yahoo":
        return (f"https://paypayfleamarket.yahoo.co.jp/item/{lid}" if lid.startswith("z")
                else f"https://auctions.yahoo.co.jp/jp/auction/{lid}")
    if source == "mercari":
        return f"https://jp.mercari.com/item/{lid}"
    return None


def fig_of():
    """'<source>:<listing id>' -> figure id, for ordering the checks."""
    from prices.aggregate import read_csv
    return {f"{r['source']}:{r['listing_id']}": r["figure_id"] for r in read_csv(DATA / "sales.csv")}


def wanted(sales, corrections, links):
    """The PER_FIGURE newest linkable sales of each figure, skipping pages known to be gone: [(source, listing id)]."""
    by_fig = {}
    for r in sales:
        key = (r["source"], r["listing_id"])
        if key in corrections:
            if not corrections[key]:
                continue
            r = dict(r, figure_id=corrections[key])
        if (r["sold_on"] and not r["listing_id"].startswith("old:") and listing_url(r["source"], r["listing_id"])
                and links.get(f"{r['source']}:{r['listing_id']}", [""])[0] != "dead"):
            by_fig.setdefault(r["figure_id"], []).append(r)
    out = []
    for rows in by_fig.values():
        rows.sort(key=lambda r: (r["sold_on"], r["listing_id"]), reverse=True)
        out += [(r["source"], r["listing_id"]) for r in rows[:PER_FIGURE]]
    return out


class Throttled(Exception):
    pass


def check(url):
    status, _h, body = fetch(url, "browser", timeout=20)
    if status in (429, 500, 503, 403):
        raise Throttled(f"HTTP {status}")
    if status in (404, 410) or any(g in body for g in GONE):
        return "dead"
    if status == 200:
        return "ok"
    raise RuntimeError(f"HTTP {status}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()
    from prices.aggregate import corrections, read_csv
    links = json.loads(LINKS.read_text(encoding="utf-8")) if LINKS.exists() else {}
    want = wanted(read_csv(DATA / "sales.csv"), corrections(), links)
    today = date.today()
    due = []
    for src, lid in want:
        st = links.get(f"{src}:{lid}")
        if not st or (st[0] == "ok" and date.fromisoformat(st[1]) < today - timedelta(days=RECHECK_DAYS)):
            due.append((src, lid))
    ok = sum(1 for s, l in want if links.get(f"{s}:{l}", [""])[0] == "ok")
    # at most MAX_PER_RUN per run: first the newest sale of each figure that has no working link yet, then the rest
    fig = fig_of()
    linked = {fig.get(k) for k, v in links.items() if v[0] == "ok"}
    rank, seen = {}, {}
    for s_, l_ in due:  # due is newest-first within each figure (same order as wanted())
        f_ = fig.get(f"{s_}:{l_}")
        rank[(s_, l_)] = (f_ in linked, seen.get(f_, 0))
        seen[f_] = seen.get(f_, 0) + 1
    due.sort(key=lambda sl: rank[sl])
    backlog = len(due)
    due = due[:MAX_PER_RUN]
    print(f"{len(want)} recent sales to link, {ok} confirmed working, {backlog} to check"
          + (f" ({len(due)} this run)" if backlog > len(due) else ""))
    if a.report:
        return 0
    n_ok = n_dead = n_err = 0
    throttled = 0
    for i, (src, lid) in enumerate(due, 1):
        if i % 5 == 1:
            progress(f"checking listing pages {i}/{len(due)}")
        try:
            res = check(listing_url(src, lid))
            throttled = 0
        except Throttled as e:
            throttled += 1
            if throttled >= 2:
                print(f"stopped for now: Yahoo is refusing page loads ({e}); the rest are checked next time")
                break
            progress(f"Yahoo said {e}; waiting 90 s")
            time.sleep(90)
            continue
        except Exception:  # network trouble: leave it for the next run
            n_err += 1
            if n_err >= 5:
                print("stopped for now: the sites aren't answering")
                break
            continue
        links[f"{src}:{lid}"] = [res, today.isoformat()]
        n_ok += res == "ok"
        n_dead += res == "dead"
        time.sleep(DELAY)
    # keep the file small: forget working pages that are no longer among the newest sales (dead ones are kept so
    # they're skipped and an older sale takes their place)
    keep = {f"{s}:{l}" for s, l in want}
    links = {k: v for k, v in sorted(links.items()) if k in keep or v[0] == "dead"}
    LINKS.write_text(json.dumps(links, indent=0, ensure_ascii=False), encoding="utf-8")
    print(f"checked {n_ok + n_dead}: {n_ok} working, {n_dead} gone" + (f", {n_err} not answered (next time)" if n_err else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
