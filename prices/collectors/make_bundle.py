#!/usr/bin/env python3
"""Bundle the matcher, its data and the browser collectors into one installer script.

    python3 prices/collectors/make_bundle.py

Writes prices/collectors/install.js. Paste it once into a tab on each shop site (browser pane or any browser
console): it saves itself in that site's localStorage, so later runs only need prices/collectors/load.js.
Re-run this script (and re-install) whenever the catalogue or the collectors change; the version changes with them.
"""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRICES = HERE.parent

code = "\n".join([
    (PRICES / "matcher.js").read_text(encoding="utf-8"),
    (HERE / "browser.js").read_text(encoding="utf-8"),
    "window.__mmgInstall(" + (PRICES / "data" / "matcher.json").read_text(encoding="utf-8") + ");",
])
ver = hashlib.sha1(code.encode("utf-8")).hexdigest()[:10]
code += f"\nwindow.__mmgVersion = {json.dumps(ver)};"
installer = (
    "(() => {\n"
    f"  const code = {json.dumps(code, ensure_ascii=False)};\n"
    "  try { localStorage.setItem('mmgBundle', code); localStorage.setItem('mmgBundleVer', "
    f"{json.dumps(ver)}); }} catch (e) {{}}\n"
    "  (0, eval)(code);\n"
    f"  return 'MetalDex price collectors {ver} installed on ' + location.host;\n"
    "})()\n"
)
(HERE / "install.js").write_text(installer, encoding="utf-8")
(HERE / "load.js").write_text(
    "// Loads the collectors saved by install.js. Returns the installed version, or 'not installed'.\n"
    "(() => { const c = localStorage.getItem('mmgBundle'); if (!c) return 'not installed';"
    " (0, eval)(c); return 'loaded ' + localStorage.getItem('mmgBundleVer'); })()\n", encoding="utf-8")
(HERE / "VERSION").write_text(ver + "\n", encoding="utf-8")
print(f"wrote prices/collectors/install.js ({len(installer)//1024} KB), version {ver}")

# Compressed copy of the installer (about a third of the size), for pasting through tools with size limits.
import base64, gzip  # noqa: E402
raw = installer.encode("utf-8")
sha = hashlib.sha1(raw).hexdigest()[:10]
b64 = base64.b64encode(gzip.compress(raw, 9, mtime=0)).decode()
(HERE / "install.min.js").write_text(
    "(async () => {\n"
    f"  const b64 = \"{b64}\";\n"
    "  const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));\n"
    "  const code = await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).text();\n"
    "  const h = [...new Uint8Array(await crypto.subtle.digest('SHA-1', new TextEncoder().encode(code)))]"
    ".map(x => x.toString(16).padStart(2, '0')).join('').slice(0, 10);\n"
    f"  if (h !== \"{sha}\") return 'checksum mismatch: the pasted text was altered (' + h + ')';\n"
    "  return (0, eval)(code);\n"
    "})()\n", encoding="utf-8")
print(f"wrote prices/collectors/install.min.js ({len(b64)//1024} KB)")
