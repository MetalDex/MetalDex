#!/usr/bin/env python3
"""Update the price data in one go, without a browser.

    Windows:      double-click update-prices.bat (in the repo's top folder)
    Mac / Linux:  double-click update-prices.command, or run  python3 prices/update.py

What it does, in order:
  1. exchange rates for the currency menu      (prices/update_rates.py)
  2. collect listings from the script sources   (prices/collect.py: Yahoo! Auctions sold + buy-now,
                                                 Square Enix e-STORE, Sootang)
  3. safety checks: a source that failed or came back much smaller than last time is left out, so a
     blocked or half-loaded site can never wipe out good data
  4. add the results to the history              (prices/ingest.py), and check the newest sales' listing pages
                                                 still open (prices/check_links.py)
  5. guide prices, trends, the tracker page      (prices/aggregate.py, scripts/build.py)
  6. the Obsidian notes, if the repo sits inside the vault
  7. a git commit of the new data (not pushed unless you add --push)

A log of every run is written to prices/data/logs/update-<date>.txt.
Not collected here: Mercari (its pages are built in the browser) and Hobby Search (it answers scripts with a
Cloudflare bot check, which we don't try to get around). The weekly browser run covers both; see prices/README.md.

Options:
  --sources yahoo-sold estore ...   only these sources (default: all script sources)
  --no-commit                       leave the changes uncommitted
  --push                            git push after committing (the published site updates from that)
  --force                           ingest even sources that failed the size check
  --auto                            no "press Enter" at the end (for Task Scheduler / cron)
Standard library only (Python 3.9 or newer).
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RAW = HERE / "data" / "raw"
LOGS = HERE / "data" / "logs"
SCRIPT_SOURCES = ["yahoo-sold", "yahoo-ask", "estore", "sootang"]
ALL_SOURCES = SCRIPT_SOURCES + ["hobbysearch"]  # hobbysearch only if asked: Cloudflare turns the script away
# a listing source whose count drops below this share of the previous run is treated as a failed load
MIN_SHARE = 0.5

log_lines = []
NAMES = {"yahoo-sold": "Yahoo! Auctions sold", "yahoo-ask": "Yahoo! Auctions listings", "estore": "Square Enix e-STORE",
         "hobbysearch": "Hobby Search", "sootang": "Sootang"}
# what happened, for the summary at the end
state = {"start": time.time(), "rates": None, "sources": {}, "sales_before": None, "sales_after": None,
         "guides": None, "saved": None, "stopped": None, "log": None}


def plain(err):
    """A collector error in plain words."""
    e = str(err)
    if "URLError" in e or "timed out" in e or "Connection" in e:
        return "couldn't connect (internet down or site unreachable)"
    if "403" in e:
        return "the site refused the script (403, blocked)"
    if "429" in e:
        return "the site said too many requests (429); try again later"
    if "503" in e:
        return "the site was busy (503)"
    if "NEXT_DATA" in e:
        return "the page looked different than expected (bot check or site redesign)"
    return e


def count_sales():
    try:
        with open(HERE / "data" / "sales.csv", encoding="utf-8") as f:
            return max(sum(1 for _ in f) - 1, 0)
    except OSError:
        return None


def summary():
    st = state
    t = int(time.time() - st["start"])
    skipped = [k for k, v in st["sources"].items() if not v[0]]
    if st["stopped"]:
        head = "STOPPED: " + st["stopped"]
    elif skipped:
        head = f"FINISHED, with {len(skipped)} source(s) skipped"
    else:
        head = "FINISHED, everything updated"
    out = ["", "=" * 64, f"  {head}", f"  Time taken: {t // 60} min {t % 60} s", "-" * 64]
    for src, (ok, info) in st["sources"].items():
        out.append(f"  {'OK  ' if ok else 'SKIP'}  {NAMES.get(src, src):26} {info}")
    if st["sources"]:
        out.append("-" * 64)
    if st["sales_before"] is not None and st["sales_after"] is not None:
        out.append(f"  New sales added:   {st['sales_after'] - st['sales_before']}  (history now {st['sales_after']:,})")
    if st["guides"] is not None:
        out.append(f"  Guide prices:      {st['guides']} figures")
    if st["rates"] is not None:
        out.append(f"  Exchange rates:    {'updated' if st['rates'] else 'kept the previous ones (offline?)'}")
    if st["saved"]:
        out.append(f"  Saved:             {st['saved']}")
    if st["log"]:
        out.append(f"  Full log:          {st['log']}")
    out.append("  Not in the script: Mercari, Hobby Search (the weekly browser run collects them)")
    if skipped and not st["stopped"]:
        out.append("  Skipped sources keep their previous prices; run again later to retry them.")
    out.append("=" * 64)
    for ln in out:
        say(ln)


def say(msg=""):
    msg = msg.replace(str(Path.home()), "~")  # keep the user folder name out of the committed log
    print(msg, flush=True)
    log_lines.append(msg)


STEPS = 6
step_no = 0


def step(title):
    global step_no
    step_no += 1
    bar = "#" * step_no + "-" * (STEPS - step_no)
    say(f"\n[{bar}] Step {step_no} of {STEPS}: {title}")


def run(args, check=True):
    """Run a step of the pipeline with the same Python and show its output as it happens.
    Progress lines (starting with "  · ") are shown but kept out of the log."""
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    p = subprocess.Popen([sys.executable, "-u", *args], cwd=ROOT, env=env, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    for ln in p.stdout:
        ln = ln.rstrip("\n")
        if ln.startswith("  · "):
            print("  " + ln, flush=True)
        else:
            say("    " + ln)
    p.wait()
    if check and p.returncode != 0:
        state["stopped"] = f"{args[0]} failed; nothing was committed"
        raise SystemExit(f"\nStopped: {' '.join(args)} failed (exit {p.returncode}). Nothing was committed.")
    return p.returncode == 0


def rows_in(path):
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, "unreadable"
    return len(d.get("raw") or []), d.get("error")


def previous(src, today):
    """Row count of the newest earlier script run of this source, if any."""
    olds = sorted(p for p in RAW.glob(f"{src}-*.json") if p.stem[len(src) + 1:] < today and p.stem[len(src) + 1:][:1].isdigit() and ".failed" not in p.name)
    for p in reversed(olds):
        n, err = rows_in(p)
        if n and not err:
            return n, p.name
    return None, None


def git(*args):
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    except FileNotFoundError:  # git isn't installed
        return subprocess.CompletedProcess(args, 1, "", "git not found")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sources", nargs="+", choices=ALL_SOURCES, default=SCRIPT_SOURCES)
    ap.add_argument("--no-commit", action="store_true")
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--auto", action="store_true")
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    today = date.today().isoformat()
    say(f"MetalDex price update, {today}")

    step("exchange rates")
    state["rates"] = run(["prices/update_rates.py"], check=False)
    if not state["rates"]:
        say("    (kept the previous rates)")

    step("collecting listings")
    say("    Usually 5–15 minutes: the script waits a few seconds between pages so the sites don't block it,")
    say("    and checks the e-STORE stock of each product. A new line appears every few seconds; if nothing")
    say("    changes for 2 minutes, it's stuck (close the window and run it again).")
    run(["prices/collect.py", *a.sources])

    step("safety checks")
    use, skipped = [], []
    for src in a.sources:
        f, failed = RAW / f"{src}-{today}.json", RAW / f"{src}-{today}.failed.json"
        if failed.exists() and (not f.exists() or failed.stat().st_mtime > f.stat().st_mtime):
            n, err = rows_in(failed)  # this run failed (an older good file from today may still be there)
        else:
            n, err = rows_in(f)
        prev_n, prev_f = previous(src, today)
        if err or not n:
            # no sold listings since the last run is possible but unlikely in a week; everything else is a failure
            reason = err or "no listings"
            skipped.append(f"{src}: {reason}")
            state["sources"][src] = (False, plain(reason) if err else "found no listings")
            say(f"    SKIP  {src}: {reason}")
            continue
        if src != "yahoo-sold" and prev_n and n < prev_n * MIN_SHARE and not a.force:
            skipped.append(f"{src}: only {n} listings vs {prev_n} last time")
            state["sources"][src] = (False, f"only {n} listings vs {prev_n} last time (half loaded?)")
            say(f"    SKIP  {src}: only {n} listings vs {prev_n} in {prev_f} (site blocked or half loaded? rerun, or use --force)")
            continue
        say(f"    ok    {src}: {n} listings" + (f" (last time {prev_n})" if prev_n else ""))
        state["sources"][src] = (True, f"{n} listings")
        use.append(str(f.relative_to(ROOT)))
    if not use:
        state["stopped"] = "no site returned usable data, nothing was changed"
        raise SystemExit("\nStopped: no source returned usable data, so nothing was changed. "
                         "Check your internet connection, or open the sites in a browser to see if they work.")

    step("adding to the price history")
    state["sales_before"] = count_sales()
    run(["prices/ingest.py", *use])
    state["sales_after"] = count_sales()

    say("    Checking that the newest sales' listing pages still open (only working ones get a link):")
    run(["prices/check_links.py"], check=False)

    step("guide prices and the tracker page")
    run(["prices/aggregate.py"])
    run(["scripts/build.py"])
    try:
        pj = json.loads((ROOT / "docs" / "data" / "prices.json").read_text(encoding="utf-8"))
        state["guides"] = sum(1 for f in pj["figures"].values() if f.get("guide"))
    except (OSError, ValueError, KeyError):
        pass

    vault = ROOT.parent
    if (vault / "Metal Gallery").is_dir() and (ROOT / "obsidian" / "generate_notes.py").exists():
        say("    Obsidian notes:")
        run(["obsidian/generate_notes.py", "--vault", str(vault)], check=False)
    step("saving (log and git commit)")

    LOGS.mkdir(parents=True, exist_ok=True)
    logf = LOGS / f"update-{today}.txt"
    state["log"] = str(logf.relative_to(ROOT))
    say(f"    Log: {state['log']}")

    if a.no_commit or git("rev-parse", "--is-inside-work-tree").returncode != 0:
        state["saved"] = "files updated, not committed (--no-commit, or not a git repo)"
    else:
        msg = f"Price update {today}\n\nSources: {', '.join(Path(u).stem for u in use)}"
        if skipped:
            msg += "\nSkipped: " + "; ".join(skipped)
        # the summary goes into the log before committing, so the committed log is complete
        state["saved"] = "committed to git" + (" and pushed" if a.push else "")
        summary()
        logf.write_text("\n".join(log_lines) + "\n", encoding="utf-8")
        git("add", "prices/data", "docs/data", "docs/index.html")
        if git("diff", "--cached", "--quiet").returncode == 0:
            print("  (nothing had changed, so there was nothing to commit)")
            return 0
        c = git("commit", "-m", msg)
        if c.returncode != 0:
            print("  COMMIT FAILED: " + (c.stderr or c.stdout).strip() + "\n  The data files are updated; commit them yourself.")
            return 1
        if a.push:
            p = git("push")
            if p.returncode != 0:
                print("  PUSH FAILED: " + (p.stderr or p.stdout).strip() + "\n  It's committed; push it yourself.")
                return 1
        return 0
    summary()
    logf.write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    a_auto = "--auto" in sys.argv
    try:
        code = main()
    except SystemExit as e:
        if e.code not in (None, 0):
            print(e.code if isinstance(e.code, str) else f"exit {e.code}")
            if not state["stopped"]:
                state["stopped"] = "a step failed (see above); nothing was committed"
            if state["start"] and step_no:
                summary()
        code = 1 if e.code not in (None, 0) else 0
    if not a_auto and sys.stdin and sys.stdin.isatty():
        input("\nPress Enter to close.")
    sys.exit(code)
