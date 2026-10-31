#!/usr/bin/env python3
"""Collect prices with plain Python, no browser needed (the "script" half of the price tracker).

    python3 prices/collect.py                 # all script-friendly sources, sales since the last run
    python3 prices/collect.py yahoo-sold estore --since 2026-10-01
    python3 prices/ingest.py prices/data/raw/*-$(date +%F).json && python3 prices/aggregate.py && python3 scripts/build.py

Sources: yahoo-sold, yahoo-ask (Yahoo! Auctions), estore (Square Enix e-STORE), sootang; hobbysearch only when
named, because Hobby Search answers scripts with a Cloudflare bot check (we don't try to get around it).
Mercari and eBay build their pages in the browser or block scripts, so they are collected with
prices/collectors/browser.js instead (see prices/README.md).

Writes prices/data/raw/<source>-<date>.json with listing titles; prices/ingest.py matches them to figures.
Standard library only. Be polite: one request every couple of seconds.
"""
import argparse
import csv
import gzip
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "data" / "raw"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
DELAY = 2.0
START = time.time()


def progress(msg):
    """One live progress line (prices/update.py shows these as they happen but keeps them out of the log)."""
    t = int(time.time() - START)
    print(f"  · {t // 60}:{t % 60:02d}  {msg}", flush=True)


# Some shops turn away requests that don't look like a browser, so send the headers a browser sends.
HEADERS = {
    "basic": {"User-Agent": UA, "Accept-Language": "ja,en;q=0.8"},
    "browser": {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",
        "Sec-Ch-Ua": '"Chromium";v="126", "Google Chrome";v="126", "Not-A.Brand";v="99"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    },
}
PROFILE = "basic"  # Yahoo and the e-STORE answer this; shops that turn it away use "browser"


def fetch(url, profile=None, timeout=30):
    """One request; returns (status, headers, body text). HTTP errors come back as a status, not an exception."""
    req = urllib.request.Request(url, headers=HEADERS[profile or PROFILE])
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        status, hdrs, raw = r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        status, hdrs, raw = e.code, e.headers, e.read()
    enc = (hdrs.get("Content-Encoding") or "").lower()
    if enc == "gzip":
        raw = gzip.decompress(raw)
    elif enc == "deflate":
        raw = zlib.decompress(raw, -zlib.MAX_WBITS)
    return status, hdrs, raw.decode("utf-8", errors="replace")


def get(url, tries=3, profile=None):
    for t in range(tries):
        status, hdrs, body = fetch(url, profile)
        if status < 400:
            break
        # 429 "too many requests" / 403 or 503 "too much traffic": wait and try again, then give up
        if status not in (403, 429, 503) or t == tries - 1:
            raise urllib.error.HTTPError(url, status, f"HTTP Error {status}", hdrs, None)
        wait = 20 * (t + 1)
        try:
            wait = max(wait, min(int(hdrs.get("Retry-After") or 0), 120))
        except ValueError:
            pass
        progress(f"site said {status}; waiting {wait} s and trying again")
        time.sleep(wait)
    time.sleep(DELAY)
    return body


def text(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def last_sale_date():
    p = HERE / "data" / "sales.csv"
    if not p.exists():
        return "2000-01-01"
    with open(p, encoding="utf-8", newline="") as f:
        ds = [r["sold_on"] for r in csv.DictReader(f) if r["source"] == "yahoo" and r["sold_on"]]
    return max(ds, default="2000-01-01")


# ---- Yahoo! Auctions: the page embeds its results as JSON (__NEXT_DATA__) ----
def yahoo_items(url):
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', get(url), re.S)
    if not m:
        raise RuntimeError("Yahoo page without __NEXT_DATA__ (bot check or layout change)")
    return json.loads(m.group(1))["props"]["pageProps"]["initialState"]["search"]["items"]["listing"].get("items") or []


def ycond(c):
    return "new" if "NEW" in (c or "") else ("used" if c else "")


def yahoo_sold(since):
    rows, seen = [], set()
    for q in ["メタリックモンスターズ", "メタリックアイテムズ"]:
        for b in range(1, 15001, 100):
            items = yahoo_items("https://auctions.yahoo.co.jp/closedsearch/closedsearch?p=%s&n=100&b=%d" % (urllib.parse.quote(q), b))
            if not items:
                break
            progress(f"Yahoo sold, {q}: page {b // 100 + 1}, {len(rows)} new sales so far (back to {items[-1]['endTime'][:10]}, stops at {since})")
            older = 0
            for it in items:
                d = it["endTime"][:10]
                if d < since:
                    older += 1
                    continue
                if it["auctionId"] in seen:
                    continue
                seen.add(it["auctionId"])
                rows.append(["sold", it["auctionId"], it["title"], it["price"], "JPY", d, ycond(it.get("itemCondition")), it.get("bidCount", ""), ""])
            if older == len(items):
                break
    return rows


def yahoo_ask(_since):
    rows, seen = [], set()
    for q in ["メタリックモンスターズ", "メタリックアイテムズ"]:
        for b in range(1, 3001, 100):
            items = yahoo_items("https://auctions.yahoo.co.jp/search/search?p=%s&n=100&b=%d" % (urllib.parse.quote(q), b))
            if not items:
                break
            progress(f"Yahoo listings, {q}: page {b // 100 + 1}, {len(rows)} buy-now listings so far")
            for it in items:
                p = it.get("buyNowPrice") or (it["price"] if it.get("isFixedPrice") else None)
                if p and it["auctionId"] not in seen:
                    seen.add(it["auctionId"])
                    rows.append(["ask", it["auctionId"], it["title"], p, "JPY", "", ycond(it.get("itemCondition")),
                                 "flea" if it.get("isFleamarketItem") else "auction", ""])
    return rows


# ---- Hobby Search ----
def hobbysearch(_since):
    base = "https://www.1999.co.jp/search?typ1_c=111&target=ItemSeries&searchkey=" + urllib.parse.quote("ドラゴンクエスト メタリックモンスターズギャラリー")
    rows = []
    for p in range(1, 11):
        cards = re.split(r'<div class="c-card">', get(base + "&spage=%d" % p, profile="browser"))[1:]
        if not cards:
            break
        progress(f"Hobby Search: page {p}, {len(rows) + len(cards)} items")
        for c in cards:
            code = re.search(r'itemcode="(\d+)"', c, re.I)  # the page writes ItemCode=
            price = re.search(r'c-card__price-element">\s*¥?\s*(?:<span[^>]*>)?\s*([\d,]+)', c)
            if not code or not price:
                continue
            t = text(c)
            title = re.sub(r"^.*?(ドラゴンクエスト)", r"\1", t)
            stock = "out" if re.search("在庫なし|品切|販売終了", t) else ("pre" if "予約" in t else "in")
            rows.append(["retail", code.group(1), title, int(price.group(1).replace(",", "")), "JPY", "", "new", stock, ""])
    return rows


# ---- Square Enix e-STORE ----
def estore(_since):
    rows, seen = [], set()
    for p in range(1, 21):
        page = get("https://store.jp.square-enix.com/estore/e/edragonquest-figure%s/" % ("_p%d" % p if p > 1 else ""))
        cards = re.split(r'<dl class="block-thumbnail-t--goods', page)[1:]
        first = re.search(r'href="(/estore/g/g[^"]+)"', cards[0]).group(1) if cards else None
        if not cards or first in seen:
            break
        seen.add(first)
        progress(f"e-STORE: page {p} ({len(cards)} products)")
        for k, c in enumerate(cards, 1):
            a = re.search(r'href="/estore/g/g([^"/]+)/?"[^>]*title="([^"]+)"', c)
            pr = re.search(r'class="price"><span>([\d,]+)', c)
            if not a or not pr or "メタリック" not in a.group(2):
                continue
            t = text(c)
            stock = "out" if re.search("在庫切れ|品切|売り切れ|SOLD|受付終了|販売終了", t) else ("pre" if "予約商品" in t else "in")
            if stock != "pre":  # the list page doesn't show sold-out items; the product page's stock box does
                progress(f"e-STORE: page {p}, checking stock of product {k}/{len(cards)}")
                try:
                    time.sleep(1)  # the store answers "too much traffic" (403) when asked too fast
                    page_ = get("https://store.jp.square-enix.com/estore/g/g%s/" % a.group(1))
                except Exception:
                    page_ = ""
                i = page_.find('class="block-goods-stock"')
                # the status comes first ("在庫 在庫あり" / "在庫 予約受付中"); the notes after ※ can mention 予約 too
                box = text(page_[i:i + 400]).split("※")[0] if i >= 0 else ""
                stock = "out" if re.search("品切|在庫切|販売終了|受付終了", box) else ("pre" if "予約" in box else ("in" if "在庫あり" in box else "unknown"))
            rows.append(["retail", a.group(1), html.unescape(a.group(2)), int(pr.group(1).replace(",", "")), "JPY", "", "new", stock, ""])
    return rows


# ---- Sootang (Shopify JSON) ----
def sootang(_since):
    rows = []
    for p in range(1, 6):
        prods = json.loads(get("https://www.sootang.jp/collections/series_metalic-monsters-garelly/products.json?limit=250&page=%d" % p, profile="browser"))["products"]
        if not prods:
            break
        progress(f"Sootang: page {p}, {len(prods)} products")
        for pr in prods:
            for v in pr["variants"]:
                jan = v.get("sku") if re.fullmatch(r"\d{13}", v.get("sku") or "") else ""
                rows.append(["retail", pr["handle"], pr["title"], round(float(v["price"])), "JPY", "", "new",
                             "in" if v.get("available") else "out", jan])
    return rows


# ---- --diagnose: which sites answer a script, and with which headers ----
CHECKS = [
    ("Yahoo! Auctions", "https://auctions.yahoo.co.jp/closedsearch/closedsearch?p=%E3%83%A1%E3%82%BF%E3%83%AA%E3%83%83%E3%82%AF%E3%83%A2%E3%83%B3%E3%82%B9%E3%82%BF%E3%83%BC%E3%82%BA&n=100"),
    ("e-STORE list", "https://store.jp.square-enix.com/estore/e/edragonquest-figure/"),
    ("Hobby Search search", "https://www.1999.co.jp/search?typ1_c=111&target=ItemSeries&searchkey=" + urllib.parse.quote("ドラゴンクエスト メタリックモンスターズギャラリー")),
    ("Hobby Search home", "https://www.1999.co.jp/"),
    ("Sootang collection json", "https://www.sootang.jp/collections/series_metalic-monsters-garelly/products.json?limit=250&page=1"),
    ("Sootang products.json", "https://www.sootang.jp/products.json?limit=1"),
    ("Sootang collection page", "https://www.sootang.jp/collections/series_metalic-monsters-garelly"),
    ("Sootang home", "https://www.sootang.jp/"),
]


def diagnose():
    lines = [f"Site check {date.today().isoformat()}, Python {sys.version.split()[0]}, {sys.platform}", ""]
    for name, url in CHECKS:
        for prof in ("basic", "browser"):
            try:
                st, h, body = fetch(url, prof, timeout=20)
                hint = []
                for k in ("Server", "Retry-After", "CF-RAY", "X-Shopify-Stage", "X-Amz-Cf-Id", "Set-Cookie"):
                    if h.get(k):
                        hint.append(f"{k}={h.get(k)[:40]}")
                low = body[:3000].lower()
                for w in ("just a moment", "captcha", "access denied", "cloudflare", "akamai", "request blocked", "too many"):
                    if w in low:
                        hint.append(f'page says "{w}"')
                res = f"{st} {len(body):>7} chars  " + "; ".join(hint)
            except Exception as e:  # network problems
                res = f"ERR {type(e).__name__}: {e}"
            lines.append(f"{name:24} {prof:8} {res}")
            print(lines[-1], flush=True)
            time.sleep(3)
    out = HERE / "data" / "logs" / f"site-check-{date.today().isoformat()}.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nSaved to {out.relative_to(HERE.parent)}")


SOURCES = {"yahoo-sold": yahoo_sold, "yahoo-ask": yahoo_ask, "hobbysearch": hobbysearch, "estore": estore, "sootang": sootang}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sources", nargs="*", default=[s for s in SOURCES if s != "hobbysearch"], help="default: all but hobbysearch")
    ap.add_argument("--diagnose", action="store_true", help="check which sites answer a script (no data is changed)")
    ap.add_argument("--since", help="earliest sale date for yahoo-sold (default: the day of the newest Yahoo sale already stored)")
    a = ap.parse_args()
    if a.diagnose:
        diagnose()
        return 0
    run = date.today().isoformat()
    since = a.since or last_sale_date()
    RAW.mkdir(parents=True, exist_ok=True)
    for i, src in enumerate(a.sources, 1):
        progress(f"--- {src} ({i} of {len(a.sources)}) ---")
        try:
            rows = SOURCES[src](since)
            err = None
        except Exception as e:  # keep going with the other sources
            rows, err = [], f"{type(e).__name__}: {e}"
        # a failed run never overwrites good data from earlier the same day
        out = RAW / (f"{src}-{run}.json" if not err else f"{src}-{run}.failed.json")
        out.write_text(json.dumps({"src": src, "run": run, "error": err, "raw": rows}, ensure_ascii=False), encoding="utf-8")
        print(f"{src}: {len(rows)} listings -> {out.relative_to(HERE.parent)}" + (f"  ERROR {err}" if err else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
