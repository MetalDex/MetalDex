#!/usr/bin/env python3
"""Generate an Obsidian note for every figure, plus an index note.

    python3 obsidian/generate_notes.py --vault "/path/to/My Vault"
    python3 obsidian/generate_notes.py --vault "/path/to/My Vault" --import metaldex-collection-2026-10-06.json

Safe to re-run: catalogue fields are refreshed from the data, while your own
fields (owned, wishlist, price_paid, acquired, where) and everything you write
under "## My notes" are kept. --import copies owned/wishlist/price/notes from a
web-tracker export into the notes (the export wins where both have a value).

No third-party dependencies. The index uses the Dataview community plugin.
"""
import argparse
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_DATA = HERE.parent / "docs" / "data" / "figures.json"
USER_FIELDS = ["owned", "wishlist", "price_paid", "acquired", "where"]
MY_NOTES = "## My notes"


def safe_name(s: str) -> str:
    return re.sub(r'[\\/:*?"<>|#^\[\]]', "", s).strip()


def yq(v) -> str:
    """Quote a value for YAML frontmatter."""
    if v is None or v == "":
        return '""'
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    return json.dumps(str(v), ensure_ascii=False)


def read_existing(path: Path):
    if not path.exists():
        return {}, ""
    text = path.read_text(encoding="utf-8")
    fm = {}
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if m:
        for line in m.group(1).splitlines():
            k, _, v = line.partition(":")
            v = v.strip()
            if v in ("true", "false"):
                fm[k.strip()] = v == "true"
            else:
                try:
                    fm[k.strip()] = json.loads(v) if v else ""
                except json.JSONDecodeError:
                    fm[k.strip()] = v
    mine = ""
    i = text.find(MY_NOTES)
    if i != -1:
        mine = text[i + len(MY_NOTES):].strip("\n")
    return fm, mine


def note_for(f, data, user, mine):
    tags = ["metal-gallery", f"line/{f['line']}"]
    if f.get("exclusive"):
        tags.append("exclusive")
    fm = {
        "id": f["id"],
        "name_en": f["name_en"],
        "name_ja": f["name_ja"],
        "line": data["lines"][f["line"]],
        "type": f.get("group", ""),
        "order": f.get("order", 0),
        "variant": f.get("variant") or "",
        "exclusive": data["exclusive_labels"].get(f.get("exclusive") or "", ""),
        "first_release": f.get("first_release") or "",
        "image": f.get("remote_image") or f.get("image") or "",
    }
    lines = ["---"]
    lines += [f"{k}: {yq(v)}" for k, v in fm.items()]
    lines.append(f"owned: {yq(bool(user.get('owned')))}")
    lines.append(f"wishlist: {yq(bool(user.get('wishlist')))}")
    for k in ["price_paid", "acquired", "where"]:
        lines.append(f"{k}: {yq(user.get(k, ''))}")
    lines.append("tags: [" + ", ".join(tags) + "]")
    lines.append("---")
    body = [f"# {f['name_en']}", f"**{f['name_ja']}**", ""]
    if fm["image"]:
        body += [f"![{f['name_en']}|240]({fm['image']})", ""]
    cr = f.get("image_credit") or {}
    credit = (f"[{cr['label']}]({cr['url']})" if cr.get("url") else cr.get("label", "")) if cr else ""
    facts = [("Line", fm["line"]), ("First release", fm["first_release"] or "Not yet verified"),
             ("Availability", fm["exclusive"]), ("Variant", fm["variant"]), ("Notes", f.get("notes") or ""),
             ("Photo", credit)]
    body += [f"- **{k}:** {v}" for k, v in facts if v]
    if f["releases"]:
        body += ["", "## Known releases", "", "| Barcode (JAN) | Retail | Date | Type |", "|---|---|---|---|"]
        for r in f["releases"]:
            price = f"¥{r['msrp_jpy']:,}" if r.get("msrp_jpy") else "—"
            body.append(f"| `{r['jan']}` | {price} | {r.get('date') or '—'} | {'Re-run' if r.get('kind') == 'rerun' else '—'} |")
    body += ["", "## Sources", ""] + [f"- [{s['label']}]({s['url']})" for s in f["sources"]]
    body += ["", MY_NOTES, "", mine or ""]
    return "\n".join(lines + body).rstrip() + "\n"


INDEX = """# Metal Gallery Index

Generated from the MetalDex catalogue ({count} entries, data {generated}).
Tick `owned` / `wishlist` in each figure's properties. The tables below need the **Dataview** plugin.

## Progress
```dataview
TABLE WITHOUT ID key AS "Type", length(filter(rows, (r) => r.owned)) + " / " + length(rows) AS "Owned"
FROM "{folder}"
GROUP BY type
SORT min(rows.order) ASC
```

## Wishlist
```dataview
TABLE type AS "Type", name_ja AS "Japanese", first_release AS "Released", exclusive AS "Availability"
FROM "{folder}"
WHERE wishlist = true
SORT order ASC
```

## Still missing
```dataview
TABLE type AS "Type", name_ja AS "Japanese", first_release AS "Released", exclusive AS "Availability"
FROM "{folder}"
WHERE owned != true
SORT order ASC
```

## Owned
```dataview
TABLE name_ja AS "Japanese", price_paid AS "Paid", acquired AS "Acquired", where AS "Where"
FROM "{folder}"
WHERE owned = true
SORT acquired DESC
```
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vault", required=True, help="Path to your Obsidian vault")
    ap.add_argument("--folder", default="Metal Gallery", help="Folder inside the vault (default: %(default)s)")
    ap.add_argument("--data", default=str(DEFAULT_DATA), help="figures.json to read")
    ap.add_argument("--import", dest="imp", help="Collection export (.json) from the web tracker")
    a = ap.parse_args()

    data = json.loads(Path(a.data).read_text(encoding="utf-8"))
    imported = {}
    if a.imp:
        imported = json.loads(Path(a.imp).read_text(encoding="utf-8")).get("items", {})

    root = Path(a.vault) / a.folder
    figdir = root / "Figures"
    figdir.mkdir(parents=True, exist_ok=True)

    # map existing notes by id so renamed titles don't create duplicates
    by_id = {}
    for p in figdir.glob("*.md"):
        fm, _ = read_existing(p)
        if fm.get("id"):
            by_id[fm["id"]] = p

    written = 0
    for f in data["figures"]:
        want = figdir / f"{safe_name(f['name_en'])}.md"
        path = by_id.get(f["id"]) or want
        if path != want and not want.exists():
            path.rename(want)  # figure was renamed in the catalogue
            path = want
        fm, mine = read_existing(path)
        user = {k: fm.get(k, "") for k in USER_FIELDS}
        imp = imported.get(f["id"])
        if imp:
            user["owned"] = bool(imp.get("owned", user["owned"]))
            user["wishlist"] = bool(imp.get("wish", user["wishlist"]))
            user["price_paid"] = imp.get("paid") or user["price_paid"]
            user["acquired"] = imp.get("got") or user["acquired"]
            user["where"] = imp.get("where") or user["where"]
            if imp.get("notes") and imp["notes"] not in (mine or ""):
                mine = ((mine + "\n\n") if mine else "") + imp["notes"]
        path.write_text(note_for(f, data, user, mine), encoding="utf-8")
        written += 1

    (root / "Metal Gallery Index.md").write_text(
        INDEX.format(count=data["count"], generated=data["generated"], folder=f"{a.folder}/Figures"), encoding="utf-8")
    print(f"Wrote {written} figure notes and an index to {root}")


if __name__ == "__main__":
    main()
