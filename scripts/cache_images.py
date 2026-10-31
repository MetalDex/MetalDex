#!/usr/bin/env python3
"""Download every figure photo into docs/img/ so the tracker keeps working
even if a shop removes or moves its product images.

    python scripts/cache_images.py      # downloads missing photos only
    python scripts/build.py             # rebuild; local copies are used automatically

Run it on your own computer (plain Python 3, no extra packages).
Photos are for personal use: docs/img/ is git-ignored so they stay out of the public repo.
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "docs" / "data" / "figures.json"
OUT = ROOT / "docs" / "img"


def main() -> int:
    figs = json.loads(DATA.read_text(encoding="utf-8"))["figures"]
    OUT.mkdir(parents=True, exist_ok=True)
    got = skipped = failed = 0
    for f in figs:
        url = f.get("remote_image") or f.get("image")
        if not url or not url.startswith("http"):
            continue
        dest = OUT / f"{f['id']}.jpg"
        if dest.exists() and dest.stat().st_size > 0:
            skipped += 1
            continue
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (metaldex)"})
            with urllib.request.urlopen(req, timeout=30) as r:
                dest.write_bytes(r.read())
            got += 1
            print(f"ok   {f['id']}")
            time.sleep(0.5)  # be polite to the shops
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {f['id']}: {e}", file=sys.stderr)
    print(f"\n{got} downloaded, {skipped} already cached, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
