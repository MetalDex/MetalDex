#!/usr/bin/env python3
"""Build docs/data/figures.json from the CSV source files in data/.

Usage:  python3 scripts/build.py          # build + validate
        python3 scripts/build.py --check  # validate only (CI)

No third-party dependencies.
"""
import csv
import importlib.util
import json
import os
import re
import sys
from urllib.parse import quote
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "docs" / "data" / "figures.json"
TEMPLATE = ROOT / "src" / "tracker.html"
PAGE = ROOT / "docs" / "index.html"
REPO_URL = "https://github.com/metaldex/MetalDex"

SOURCE_URLS = {
    "dqwiki": "https://dqwiki.wicurio.com/index.php?%E3%80%90%E3%83%89%E3%83%A9%E3%82%B4%E3%83%B3%E3%82%AF%E3%82%A8%E3%82%B9%E3%83%88%E3%83%A1%E3%82%BF%E3%83%AA%E3%83%83%E3%82%AF%E3%83%A2%E3%83%B3%E3%82%B9%E3%82%BF%E3%83%BC%E3%82%BA%E3%82%AE%E3%83%A3%E3%83%A9%E3%83%AA%E3%83%BC%E3%80%91",
    "amiami": "https://slist.amiami.jp/top/search/list?s_seriestitle_id=4547",
    "sootang": "https://www.sootang.jp/collections/series_metalic-monsters-garelly",
    "estore": "https://store.jp.square-enix.com/estore/e/edragonquest-figure/",
    "hobbysearch": "https://www.1999.co.jp/search?typ1_c=111&target=ItemSeries&searchkey=%E3%83%89%E3%83%A9%E3%82%B4%E3%83%B3%E3%82%AF%E3%82%A8%E3%82%B9%E3%83%88+%E3%83%A1%E3%82%BF%E3%83%AA%E3%83%83%E3%82%AF%E3%83%A2%E3%83%B3%E3%82%B9%E3%82%BF%E3%83%BC%E3%82%BA%E3%82%AE%E3%83%A3%E3%83%A9%E3%83%AA%E3%83%BC",
}
SOURCE_LABELS = {
    "dqwiki": "集まれ！ドラクエ設定wiki",
    "amiami": "AmiAmi",
    "sootang": "Sootang",
    "estore": "Square Enix e-STORE",
    "hobbysearch": "Hobby Search",
}
LINES = {"mmg": "Metallic Monsters Gallery", "battle": "MMG Battle", "dai": "MMG – Adventure of Dai", "items": "Metallic Items Gallery"}
EXCLUSIVE = {"": None, "official-shop": "Official Shop exclusive", "estore": "e-STORE only", "limited": "Limited (channel unverified)", "yahoo": "Yahoo! Shopping exclusive", "event": "Event exclusive", "loft": "LOFT exclusive / advance sale", "bundle": "Bundled with a game edition", "prize": "Prize / campaign only (never sold)"}
ID_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
DATE_RE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")
# Photos may only come from these sites (or a contributed file under docs/img/contrib/), so a bad edit can't point
# the page at an arbitrary server.
IMAGE_HOSTS = {"store.jp.square-enix.com", "www.1999.co.jp", "metalfigurecollector.com", "shop.r10s.jp",
               "static.mercdn.net"}
UNSAFE_TEXT = re.compile(r"<\s*/?\s*(script|iframe|object|embed|style|img|svg|a)\b|javascript:|on\w+\s*=", re.I)


def url_ok(u: str, hosts=None) -> bool:
    """https only, no spaces or quotes; optionally limited to some hosts."""
    m = re.match(r"^https://([^/\s\"'<>]+)(/[^\s\"'<>]*)?$", u or "")
    return bool(m) and (hosts is None or m.group(1) in hosts)


def ean13_ok(code: str) -> bool:
    if not re.fullmatch(r"\d{13}", code):
        return False
    digits = [int(c) for c in code]
    total = sum(d * (3 if i % 2 else 1) for i, d in enumerate(digits[:12]))
    return (10 - total % 10) % 10 == digits[12]


def hs_image(hs_id: str) -> str:
    n = int(hs_id)
    folder = (n - 10_000_000) // 10_000
    return f"https://www.1999.co.jp/itbig{folder:02d}/{hs_id}.jpg"


GUIDE = "https://metalfigurecollector.com/dragon-quest-metallic-monsters-gallery/"


def image_credit(url: str, fig: dict, override: str) -> dict | None:
    """Who a product photo belongs to, shown under the photo in the tracker.
    `override` (figures.csv image_credit column) is "Name" or "Name|https://link" for contributed photos."""
    if override:
        name, _, link = override.partition("|")
        return {"label": name.strip(), "url": link.strip() or None}
    if not url:
        return None
    host = re.sub(r"^https?://", "", url).split("/")[0]
    if "square-enix.com" in host:
        return {"label": "© ARMOR PROJECT/BIRD STUDIO/SQUARE ENIX (official photo, Square Enix e-STORE)", "url": "https://store.jp.square-enix.com/"}
    if "1999.co.jp" in host:
        return {"label": "© ARMOR PROJECT/BIRD STUDIO/SQUARE ENIX (official photo, via Hobby Search)", "url": f"https://www.1999.co.jp/{fig['hs_id']}" if fig.get("hs_id") else "https://www.1999.co.jp/"}
    if "metalfigurecollector.com" in host:
        return {"label": "Metal Dracky (used with permission)", "url": GUIDE}
    if "mercdn.net" in host:
        return {"label": "Mercari seller", "url": "https://jp.mercari.com/"}
    if "r10s.jp" in host or "rakuten" in host:
        return {"label": "Rakuten shop", "url": "https://www.rakuten.co.jp/"}
    return {"label": host, "url": None}


def source_entry(key: str, fig: dict) -> dict:
    if key.startswith("http"):
        host = re.sub(r"^https?://(www\.)?", "", key).split("/")[0]
        return {"label": host, "url": key}
    if key == "hobbysearch" and fig.get("hs_id"):
        return {"label": SOURCE_LABELS[key], "url": f"https://www.1999.co.jp/{fig['hs_id']}"}
    if key not in SOURCE_URLS:
        raise ValueError(f"unknown source key '{key}'")
    return {"label": SOURCE_LABELS[key], "url": SOURCE_URLS[key]}



def build_date():
    """Today, except with KEEP_DATE=1 (the GitHub check): reuse the date already in docs/data/figures.json, so a
    rebuild on another day gives identical files and the check only fails when the data really changed."""
    if os.environ.get("KEEP_DATE"):
        try:
            return json.loads(OUT.read_text(encoding="utf-8"))["generated"]
        except (OSError, ValueError, KeyError):
            pass
    return date.today().isoformat()

def main() -> int:
    errors = []
    with open(DATA / "figures.csv", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    with open(DATA / "releases.csv", encoding="utf-8", newline="") as f:
        rels = list(csv.DictReader(f))

    figures, seen = [], set()
    for i, r in enumerate(rows, start=2):
        fid = r["id"].strip()
        where = f"figures.csv line {i} ({fid})"
        if not ID_RE.match(fid):
            errors.append(f"{where}: bad id")
        if fid in seen:
            errors.append(f"{where}: duplicate id")
        seen.add(fid)
        if r["line"] not in LINES:
            errors.append(f"{where}: unknown line '{r['line']}'")
        if r["exclusive"] not in EXCLUSIVE:
            errors.append(f"{where}: unknown exclusive '{r['exclusive']}'")
        if r["first_release"] and not DATE_RE.match(r["first_release"]):
            errors.append(f"{where}: bad date '{r['first_release']}'")
        if not r["name_ja"] or not r["name_en"]:
            errors.append(f"{where}: missing name")
        for col, val in r.items():
            if val and UNSAFE_TEXT.search(val):
                errors.append(f"{where}: {col} contains HTML or script-like text")
        img = (r.get("image_url") or "").strip()
        if img and not (url_ok(img, IMAGE_HOSTS) or re.fullmatch(r"img/contrib/[a-z0-9-]+\.(jpg|png|webp)", img)):
            errors.append(f"{where}: image_url must be https on {', '.join(sorted(IMAGE_HOSTS))} or img/contrib/<id>.jpg")
        if r["hs_id"] and not r["hs_id"].isdigit():
            errors.append(f"{where}: hs_id must be digits")
        credit_link = (r.get("image_credit") or "").partition("|")[2].strip()
        if credit_link and not url_ok(credit_link):
            errors.append(f"{where}: image_credit link must be an https address")
        for k in (r["sources"] or "").split(";"):
            if k.strip().startswith("http") and not url_ok(k.strip()):
                errors.append(f"{where}: source '{k.strip()[:60]}' must be an https address")
        fig = {
            "id": fid,
            "name_ja": r["name_ja"],
            "name_en": r["name_en"],
            "line": r["line"],
            "variant": r["variant"] or None,
            "exclusive": r["exclusive"] or None,
            "first_release": r["first_release"] or None,
            "hs_id": r["hs_id"] or None,
            "image": r.get("image_url") or (hs_image(r["hs_id"]) if r["hs_id"] else None),
            "notes": r["notes"] or None,
            "aka": [a.strip() for a in (r.get("aka") or "").split(";") if a.strip()],
            "releases": [],
        }
        fig["image_credit"] = image_credit(fig["image"], fig, (r.get("image_credit") or "").strip())
        # prefer a local copy made by scripts/cache_images.py
        fig["remote_image"] = fig["image"]
        if (ROOT / "docs" / "img" / f"{fid}.jpg").exists():
            fig["image"] = f"img/{fid}.jpg"
        try:
            fig["sources"] = [source_entry(k.strip(), fig) for k in r["sources"].split(";") if k.strip()]
        except ValueError as e:
            errors.append(f"{where}: {e}")
            fig["sources"] = []
        if not fig["sources"]:
            errors.append(f"{where}: needs at least one source")
        if r.get("wiki"):
            fig["wiki"] = "https://dragon-quest.org/wiki/" + quote(r["wiki"].replace(" ", "_"), safe="'()_")
            fig["sources"].insert(0, {"label": "Dragon Quest Wiki", "url": fig["wiki"]})
        figures.append(fig)

    by_id = {f["id"]: f for f in figures}
    jans = set()
    for i, r in enumerate(rels, start=2):
        where = f"releases.csv line {i}"
        f = by_id.get(r["figure_id"])
        if not f:
            errors.append(f"{where}: unknown figure_id '{r['figure_id']}'")
            continue
        if not ean13_ok(r["jan"]):
            errors.append(f"{where}: invalid JAN/EAN-13 '{r['jan']}'")
        if r["jan"] in jans:
            errors.append(f"{where}: duplicate JAN {r['jan']}")
        jans.add(r["jan"])
        if r["date"] and not DATE_RE.match(r["date"]):
            errors.append(f"{where}: bad date '{r['date']}'")
        f["releases"].append({
            "jan": r["jan"],
            "msrp_jpy": int(r["msrp_jpy"]) if r["msrp_jpy"] else None,
            "date": r["date"] or None,
            "kind": r["kind"] or None,
            "source": r["source"],
        })

    # type groups (data/groups.py) — every figure must be in exactly one group
    spec = importlib.util.spec_from_file_location("groups", DATA / "groups.py")
    gmod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gmod)
    groups_out, order, seen_g = [], 0, set()
    for section, groups in gmod.GROUPS:
        for gname, ids in groups:
            groups_out.append({"section": section, "name": gname, "count": len(ids)})
            for fid in ids:
                if fid not in by_id:
                    errors.append(f"groups.py: unknown id '{fid}' in '{gname}'")
                    continue
                if fid in seen_g:
                    errors.append(f"groups.py: '{fid}' is in more than one group")
                seen_g.add(fid)
                order += 1
                by_id[fid].update(section=section, group=gname, order=order)
    for fid in by_id:
        if fid not in seen_g:
            errors.append(f"groups.py: '{fid}' is not in any group")

    if errors:
        print("\n".join(errors), file=sys.stderr)
        print(f"\n{len(errors)} error(s)", file=sys.stderr)
        return 1

    figures.sort(key=lambda f: f["order"])
    for f in figures:
        f["releases"].sort(key=lambda x: x["date"] or "")

    out = {
        "schema": 1,
        "generated": build_date(),
        "lines": LINES,
        "groups": groups_out,
        "exclusive_labels": {k: v for k, v in EXCLUSIVE.items() if k},
        "count": len(figures),
        "figures": figures,
    }
    if "--check" not in sys.argv:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"wrote {OUT.relative_to(ROOT)}: {len(figures)} figures, {len(rels)} releases")
        blob = json.dumps(out, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
        prices = ROOT / "docs" / "data" / "prices.json"
        pblob = prices.read_text(encoding="utf-8").replace("</", "<\\/") if prices.exists() else "null"
        html = (TEMPLATE.read_text(encoding="utf-8").replace("__FIGURE_DATA__", blob).replace("__PRICE_DATA__", pblob)
                .replace("https://github.com/", REPO_URL))
        PAGE.write_text(html, encoding="utf-8")
        print(f"wrote {PAGE.relative_to(ROOT)} ({len(html)//1024} KB, data inlined so it also works offline)")
    else:
        print(f"ok: {len(figures)} figures, {len(rels)} releases")
    return 0


if __name__ == "__main__":
    sys.exit(main())
