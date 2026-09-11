#!/usr/bin/env python3
"""Is the resume-progress FIX deployed, and did the last watch even reach Jellyfin?

1. The live api's own /openapi.json is the discriminator: the fix added
   `runtime_ticks` to the progress request body, so its presence proves the
   running api includes the fix.
2. Jellyfin's log shows whether a playback report ARRIVED (and under which
   client identity), which separates "never reported" from "reported but dropped".
"""
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rkm_common import Jellyfin, app_base  # noqa: E402

app = app_base()
print(f"app: {app}\n")

# --- 1. is the fix in the RUNNING api? -----------------------------------
try:
    with urllib.request.urlopen(f"{app}/openapi.json", timeout=15) as r:
        spec = json.load(r)
    body = (((spec.get("paths") or {}).get("/api/jellyfin/progress") or {})
            .get("post") or {}).get("requestBody") or {}
    ref = json.dumps(body)
    schema_name = None
    if "JellyfinProgressRequest" in ref:
        schema_name = "JellyfinProgressRequest"
    props = (((spec.get("components") or {}).get("schemas") or {})
             .get(schema_name or "", {}) or {}).get("properties") or {}
    print(f"running api has runtime_ticks on the progress payload: {'runtime_ticks' in props}")
    print(f"  (progress payload properties: {sorted(props)})")
    print(f"  => FIX {'IS' if 'runtime_ticks' in props else 'IS NOT'} DEPLOYED to the running stack")
except Exception as e:  # noqa: BLE001
    print(f"could not read the api's openapi.json: {e}")

# --- 2. what did Jellyfin see? ------------------------------------------
jf = Jellyfin()
logs = jf.get("/System/Logs") or []
name = logs[0].get("Name") if isinstance(logs, list) and logs else "log_20260911.log"
txt = jf.get(f"/System/Logs/Log?name={name}", raw=True)
lines = txt.splitlines() if isinstance(txt, str) else []
print(f"\n--- last 16 playback lines from {name} ---")
hits = [l for l in lines if ("Playback stopped reported" in l or "Playback started" in l
                             or "playback" in l.lower())]
for l in hits[-16:]:
    print("  ", l[:185])
print(f"  (total playback-ish lines in this file: {len(hits)})")
