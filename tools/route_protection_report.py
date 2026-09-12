#!/usr/bin/env python3
"""What does every /api route actually require? Read-only audit (first step of Phase E).

Prints one row per route with the dependency that decides access, so "the routes are not protected"
can be answered with a list instead of a feeling. Nothing is enforced here - it reports.

    cd backend && python ../tools/route_protection_report.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from api.main import app  # noqa: E402
from config.settings import get_config  # noqa: E402


def _dep_names(deps) -> set:
    """`Depends(fn)` exposes `call`, older/variant shapes expose `dependency` - read BOTH.

    Reading only `.call` reported every route as unprotected, admin routes included, which is how
    this file was caught lying about /api/admin/* on its first run (2026-09-13).
    """
    names = set()
    for d in deps or []:
        fn = getattr(d, "call", None) or getattr(d, "dependency", None)
        name = getattr(fn, "__name__", "")
        if name:
            names.add(name)
    return names


def rows():
    out = []
    for route in app.routes:
        included = getattr(route, "original_router", None)
        context = getattr(route, "include_context", None)
        if included is not None and context is not None:
            prefix = str(getattr(context, "prefix", "") or "")
            deps = _dep_names(getattr(context, "dependencies", None))
            deps |= _dep_names(getattr(included, "dependencies", None))
            for sub in getattr(included, "routes", []):
                path = prefix + str(getattr(sub, "path", ""))
                if not path.startswith("/api"):
                    continue
                verbs = tuple(sorted(getattr(sub, "methods", None) or ()))
                # per-ROUTE dependencies too: /api/admin/* gates each route, not the include
                sub_deps = deps | _dep_names(getattr(getattr(sub, "dependant", None), "dependencies", None))
                out.append((path, verbs, sub_deps))
            continue
        path = str(getattr(route, "path", "") or "")
        if not path.startswith("/api"):
            continue
        deps = _dep_names(getattr(getattr(route, "dependant", None), "dependencies", None))
        out.append((path, tuple(sorted(getattr(route, "methods", None) or ())), deps))
    return out


def level(deps: set, path: str) -> str:
    if "require_admin_session" in deps:
        return "ADMIN"
    if "require_session" in deps:
        return "session"
    if path.startswith("/api/auth/"):
        return "auth-route"
    if path == "/api/health":
        return "PUBLIC"
    return "*** NOTHING ***"


def main() -> int:
    cfg = get_config()
    armed = str(getattr(cfg, "RKM_AUTH_REQUIRED", "") or "").strip().lower() in ("1", "true", "yes", "on")
    found = rows()
    assert len(found) >= 40, f"only {len(found)} routes found - the enumeration is broken, fix it first"
    buckets: dict[str, list[str]] = {}
    for path, verbs, deps in sorted(found):
        buckets.setdefault(level(deps, path), []).append(f"{'/'.join(verbs) or '?':9} {path}")
    for name in ("PUBLIC", "auth-route", "ADMIN", "session", "*** NOTHING ***"):
        rows_ = buckets.get(name)
        if not rows_:
            continue
        print(f"\n{name}  ({len(rows_)})")
        for r in rows_:
            print("   ", r)
    print(f"\nroutes: {len(found)}")
    print(f"RKM_AUTH_REQUIRED: {armed}  <- {'ENFORCED' if armed else 'NOT enforced: a signed-out caller is served'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
