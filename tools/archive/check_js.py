#!/usr/bin/env python3
"""Extract the <script> block from the live served dashboard and syntax-check it with node.
Also verify ENTRIES/CFG were injected (no leftover __PLACEHOLDERS__)."""
import re, subprocess, sys

html = open("/tmp/live_dashboard.html").read()

# 1. placeholders
print("__CONFIG__ remaining:", html.count("__CONFIG__"))
print("__ENTRIES__ remaining:", html.count("__ENTRIES__"))
print("ENTRIES const present:", "const ENTRIES" in html)
print("CFG const present:", "const CFG" in html)

# 2. extract script
m = re.search(r"<script>(.*?)</script>", html, re.DOTALL)
if not m:
    print("NO SCRIPT BLOCK FOUND")
    sys.exit(1)
js = m.group(1)
open("/tmp/dash_check.js", "w").write(js)
print(f"script block: {len(js)} chars")

# 3. node syntax check
r = subprocess.run(["node", "--check", "/tmp/dash_check.js"], capture_output=True, text=True)
print("node --check:", r.returncode)
print(r.stdout[-500:] if r.stdout else "")
print(r.stderr[-800:] if r.stderr else "")

# 4. simulate a quick parse of ENTRIES/CFG in isolation (JSON validity)
for name in ("CFG", "ENTRIES"):
    m2 = re.search(rf"const {name} = (.*?);", js, re.DOTALL)
    if m2:
        import json as _j
        try:
            _j.loads(m2.group(1))
            print(f"{name} JSON: VALID")
        except Exception as e:
            print(f"{name} JSON: INVALID -> {e}")
    else:
        print(f"{name}: not found")
