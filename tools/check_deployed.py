#!/usr/bin/env python3
"""Is the api you are RUNNING the code in this folder?

This is the question that keeps arriving in a new outfit: *"did my change take effect?"*, *"is Phase E
actually deployed?"*, *"why does the app still behave like the old one?"*. Reading `.env`, the compose
file or the container logs cannot answer it. Comparing the running api's own contract with the
snapshot of THIS folder can.

    python tools/check_deployed.py            # exit 0 = running api matches this folder
                                              # exit 1 = it does not (run .\\rkm-cinema.ps1 apply)
                                              # exit 2 = the api did not answer

**How it works.** FastAPI serves its own `/openapi.json`, and `docs/api/openapi.v1.json` is a snapshot
of the SAME thing generated from this folder's code (`backend/scripts/snapshot_openapi.py`). The two
are deep-equal when the running api is this code — verified, with one exception: the snapshot script
decorates `info.description` with the ADR-0001 "FROZEN contract" note, so `info` is ignored. Everything
else (paths, methods, schemas, every field, every description) is compared exactly, which is why a
docstring-only change also shows up.

⚠ **What this canNOT see.** The contract, not the implementation. A change that leaves the API shape
identical — a fixed bug inside a handler, a faster query, a different default that is not in the schema
— is invisible here. A green result means "the contract matches", never "the code is byte-identical".
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from rkm_common import app_base  # noqa: E402

DEFAULT_SNAPSHOT = ROOT / "docs" / "api" / "openapi.v1.json"
MAX_DIFFS = 12


def _without_info(spec: dict) -> dict:
    """Drop `info` — the only part the snapshot script is allowed to decorate."""
    return {k: v for k, v in spec.items() if k != "info"}


def differences(snapshot: dict, live: dict, limit: int = MAX_DIFFS) -> list[str]:
    """Human-readable contract differences, oldest-first, capped."""
    out: list[str] = []

    def add(line: str) -> None:
        if len(out) < limit:
            out.append(line)

    sp = snapshot.get("paths") or {}
    lp = live.get("paths") or {}
    for path in sorted(set(lp) - set(sp)):
        add(f"NEW endpoint, only in the running api : {path}")
    for path in sorted(set(sp) - set(lp)):
        add(f"MISSING, this folder has it but the running api does NOT : {path}")
    for path in sorted(set(sp) & set(lp)):
        for verb in sorted(set(sp[path]) - set(lp[path])):
            add(f"MISSING method on {path} : {verb.upper()}")
        for verb in sorted(set(lp[path]) - set(sp[path])):
            add(f"NEW method on {path} : {verb.upper()}")
        for verb in sorted(set(sp[path]) & set(lp[path])):
            if sp[path][verb] != lp[path][verb]:
                add(f"CHANGED : {verb.upper()} {path}")

    ss = (snapshot.get("components") or {}).get("schemas") or {}
    ls = (live.get("components") or {}).get("schemas") or {}
    for name in sorted(set(ls) - set(ss)):
        add(f"NEW schema, only in the running api : {name}")
    for name in sorted(set(ss) - set(ls)):
        add(f"MISSING schema, the running api does NOT have : {name}")
    for name in sorted(set(ss) & set(ls)):
        if ss[name] == ls[name]:
            continue
        mine = set((ss[name].get("properties") or {}))
        theirs = set((ls[name].get("properties") or {}))
        if theirs - mine:
            add(f"{name} : the running api has extra field(s) {sorted(theirs - mine)}")
        if mine - theirs:
            add(f"{name} : the running api is MISSING field(s) {sorted(mine - theirs)}")
        if not (mine - theirs) and not (theirs - mine):
            add(f"{name} : field list matches but the content differs")
    return out


def fetch_live(base: str, timeout: float = 15.0) -> dict:
    with urllib.request.urlopen(f"{base.rstrip('/')}/openapi.json", timeout=timeout) as response:
        return json.load(response)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Is the running api the code in this folder?")
    ap.add_argument("--app", default=None, help="override the app URL (default: auto)")
    ap.add_argument("--snapshot", default=str(DEFAULT_SNAPSHOT),
                    help="the contract snapshot for THIS folder")
    args = ap.parse_args(argv)

    snapshot_path = Path(args.snapshot)
    if not snapshot_path.is_file():
        print(f"could not read {snapshot_path}", file=sys.stderr)
        return 2

    base = args.app or app_base()
    try:
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except Exception as exc:                                        # noqa: BLE001
        print(f"could not parse {snapshot_path}: {exc}", file=sys.stderr)
        return 2
    try:
        live = fetch_live(base)
    except urllib.error.HTTPError as exc:
        print(f"the api at {base} answered HTTP {exc.code} for /openapi.json", file=sys.stderr)
        return 2
    except Exception as exc:                                        # noqa: BLE001
        print(f"the api at {base} did not answer: {exc}", file=sys.stderr)
        return 2

    diffs = differences(_without_info(snapshot), _without_info(live))
    print(f"app        : {base}")
    print(f"this folder: {snapshot_path.name} "
          f"({len((snapshot.get('paths') or {}))} paths)")
    print(f"running api: {len((live.get('paths') or {}))} paths")
    print()
    if not diffs:
        print("MATCH: the running api IS this folder's code (contract identical).")
        print("  (contract only - a change that does not alter the API shape cannot be seen here.)")
        return 0
    print(f"DIFFERENT: the running api is NOT this folder's code ({len(diffs)}"
          f"{'+' if len(diffs) == MAX_DIFFS else ''} difference(s)):")
    for line in diffs:
        print(f"  - {line}")
    print()
    print("Deploy the current code:   .\\rkm-cinema.ps1 apply")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
