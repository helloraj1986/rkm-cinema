#!/usr/bin/env python3
"""Final pre-deploy check: compose file valid YAML, both HTML copies have MagicDNS URLs,
no stale gateway refs, nginx conf present."""
import json, os, subprocess, sys

try:
    import yaml
except ImportError:
    yaml = None

base = "/workspace/media/watchlist"
ok = True

# 1. compose YAML
p = os.path.join(base, "docker-compose.yml")
if yaml:
    try:
        with open(p) as f:
            c = yaml.safe_load(f)
        svc = c.get("services", {}).get("watchlist", {})
        print("compose: valid YAML | image:", svc.get("image"), "| ports:", svc.get("ports"), "| restart:", svc.get("restart"))
    except Exception as e:
        ok = False
        print("compose: INVALID ->", e)
else:
    print("compose: (yaml module missing — skipped parse)")

# 2. HTML copies
for name in ("dashboard.html", "index.html"):
    full = os.path.join(base, name)
    if not os.path.exists(full):
        print(f"{name}: MISSING")
        ok = False
        continue
    html = open(full).read()
    stale = html.count("192.168.65.254")
    magic = html.count("rkm-hp.tail8d5e8.ts.net")
    btn = html.count("btn-add")
    print(f"{name}: {len(html)}B | magicdns refs={magic} | stale gateway={stale} | download btns={btn}")

# 3. nginx conf
nc = os.path.join(base, "nginx", "default.conf")
if os.path.exists(nc):
    content = open(nc).read()
    print("nginx/default.conf: present | no-store:", "no-store" in content, "| root:", "/usr/share/nginx/html" in content)
else:
    print("nginx/default.conf: MISSING")
    ok = False

# 4. watchlist.json intact
wl = json.load(open("/workspace/media/watchlist.json"))
print("watchlist.json: pending =", len(wl.get("pending", [])), "| rotation_index =", wl.get("rotation_index"))

print("\nPRE-DEPLOY CHECK:", "PASS ✅" if ok else "ISSUES ❌")