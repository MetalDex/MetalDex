#!/usr/bin/env python3
"""Save today's exchange rates (yen → USD, EUR, GBP, KRW, CNY) for the tracker's currency menu.

    python3 prices/update_rates.py                          # fetch from frankfurter.dev (European Central Bank rates)
    python3 prices/update_rates.py --date 2026-10-27 USD=0.0063363 EUR=0.0056828 GBP=0.0047541 KRW=8.413 CNY=0.042248

Writes prices/data/rates.json; prices/aggregate.py copies it into the page. The page also refreshes the rates
itself when it's opened online, so these are the offline fallback.
"""
import argparse
import json
import sys
import urllib.request
from datetime import date
from pathlib import Path

OUT = Path(__file__).resolve().parent / "data" / "rates.json"
CODES = ["USD", "EUR", "GBP", "KRW", "CNY"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pairs", nargs="*", help="CODE=rate (units of CODE per 1 yen)")
    ap.add_argument("--date", default=date.today().isoformat())
    a = ap.parse_args()
    if a.pairs:
        rates = {k: float(v) for k, v in (p.split("=") for p in a.pairs)}
        d = a.date
    else:
        url = "https://api.frankfurter.dev/v1/latest?from=JPY&to=" + ",".join(CODES)
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "metaldex"}), timeout=20) as r:
                j = json.load(r)
        except (OSError, ValueError) as e:
            sys.exit(f"couldn't fetch exchange rates ({type(e).__name__}: {e}); {OUT.name} unchanged")
        rates, d = j["rates"], j["date"]
    missing = [c for c in CODES if c not in rates]
    if missing:
        sys.exit(f"missing rates: {missing}")
    OUT.write_text(json.dumps({"date": d, "base": "JPY", "source": "European Central Bank via frankfurter.dev", "rates": rates}, indent=1), encoding="utf-8")
    print(f"wrote {OUT.name}: {d} " + " ".join(f"{k}={v}" for k, v in rates.items()))


if __name__ == "__main__":
    main()
