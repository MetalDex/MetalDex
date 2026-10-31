#!/usr/bin/env python3
"""Check a proposed change (pull request) against the main branch and summarise it in plain English.

    python3 scripts/review_changes.py origin/main            # what the GitHub check runs on pull requests
    python3 scripts/review_changes.py origin/main --owner    # the maintainer's own change: price files allowed

The project doesn't take pull requests from others (people report changes with the issue forms and the maintainer
makes them), so any change that isn't the maintainer's own (or a Dependabot update) fails.
Also fails (exit 1) when a change removes a figure, or changes a figure's id (ids never change; links and
collections depend on them). Warns when a change edits many figures at once.
Writes the summary to the GitHub job summary when run there.
"""
import csv
import io
import os
import subprocess
import sys

BIG = 15  # more changed figures than this gets a warning
FIELDS = ["name_ja", "name_en", "wiki", "aka", "line", "variant", "exclusive", "first_release", "hs_id", "image_url",
          "notes", "sources", "image_credit"]


def git(*a):
    return subprocess.run(["git", *a], capture_output=True, text=True, encoding="utf-8").stdout


def table(text):
    return {r["id"]: r for r in csv.DictReader(io.StringIO(text))} if text else {}


def main():
    base = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "origin/main"
    owner = "--owner" in sys.argv
    files = [f for f in git("diff", "--name-only", f"{base}...HEAD").splitlines() if f]
    errors, warnings, lines = [], [], []

    base_csv = git("show", f"{base}:data/figures.csv")
    if not base_csv:
        print(f"::error::Can't read data/figures.csv on {base}; fetch the main branch first (checkout fetch-depth: 0).")
        return 2
    old, new = table(base_csv), table(open("data/figures.csv", encoding="utf-8").read())
    added = [i for i in new if i not in old]
    removed = [i for i in old if i not in new]
    changed = {i: [k for k in FIELDS if (old[i].get(k) or "") != (new[i].get(k) or "")] for i in new if i in old}
    changed = {i: ks for i, ks in changed.items() if ks}
    if removed:
        errors.append(f"Removes figure(s): {', '.join(removed)}. Figures are never removed (mark them in notes instead), "
                      "and ids never change.")
    if len(changed) + len(added) > BIG:
        warnings.append(f"Large change: {len(added)} figures added and {len(changed)} edited. Review carefully.")

    if not owner and files:
        errors.append("This project doesn't take pull requests: please open an issue with the details instead "
                      "(Issues -> New issue), and the change will be made there.")

    lines.append("## What this change does\n")
    if added:
        lines.append(f"**Adds {len(added)} figure(s):** " + ", ".join(f"{new[i]['name_en']} (`{i}`)" for i in added))
    for i, ks in list(changed.items())[:40]:
        parts = []
        for k in ks:
            a, b = (old[i].get(k) or "—"), (new[i].get(k) or "—")
            parts.append(f"{k}: {a[:60]!r} → {b[:60]!r}")
        lines.append(f"- **{new[i]['name_en']}** (`{i}`): " + "; ".join(parts))
    if len(changed) > 40:
        lines.append(f"- … and {len(changed) - 40} more figures")
    other = [f for f in files if f != "data/figures.csv"]
    if other:
        lines.append("\n**Other files:** " + ", ".join(f"`{f}`" for f in other[:30]) + (" …" if len(other) > 30 else ""))
    if not (added or changed or other):
        lines.append("No catalogue changes.")
    if warnings:
        lines.append("\n" + "\n".join(f"⚠️ {w}" for w in warnings))
    if errors:
        lines.append("\n" + "\n".join(f"❌ {e}" for e in errors))

    text = "\n".join(lines)
    print(text)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(text + "\n")
    for w in warnings:
        print(f"::warning::{w}")
    for e in errors:
        print(f"::error::{e}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
