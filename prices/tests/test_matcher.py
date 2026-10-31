"""Run: python3 prices/tests/test_matcher.py   (also runs the JS port with node if available)"""
import json, subprocess, shutil, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from prices.matcher import Matcher

def cases():
    for line in (ROOT / "prices/tests/match_cases.tsv").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            t, e = line.rsplit("\t", 1)
            yield t, e

def got(r):
    return r["id"] if r["status"] == "ok" else r["status"]

def main():
    m = Matcher.from_json(ROOT / "docs/data/figures.json")
    cs = list(cases()); bad = 0
    for t, e in cs:
        g = got(m.match(t))
        if g != e:
            bad += 1; print(f"PY  expected {e:28} got {g:28} | {t}")
    if shutil.which("node"):
        out = subprocess.run(["node", str(ROOT / "prices/tests/run_js_matcher.js")], input=json.dumps([t for t, _ in cs]),
                             capture_output=True, text=True, encoding="utf-8")
        if out.returncode:
            print(out.stderr); bad += 1
        else:
            for (t, e), r in zip(cs, json.loads(out.stdout)):
                g = got(r)
                if g != e:
                    bad += 1; print(f"JS  expected {e:28} got {g:28} | {t}")
    print(f"{len(cs)} cases, {bad} failures")
    return 1 if bad else 0

if __name__ == "__main__":
    sys.exit(main())
