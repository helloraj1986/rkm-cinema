#!/usr/bin/env python3
"""Diagnose the household/admin path against a REAL Jellyfin — read-only.

Written 2026-09-12 after a live 403 that said *"Only a Jellyfin administrator can manage
household accounts"* to the actual administrator. Two independent causes produced that same
sentence, and neither was a permission problem:

1. the household methods existed on ``LibraryProvider`` but NOT on the ``LibraryService``
   FACADE the routes are handed, so every call raised ``AttributeError``;
2. a media server the api cannot reach or is not configured for, which also cannot answer.

Both were swallowed by the admin gate and reported as "you are not an administrator". This
tool prints what is ACTUALLY true, in order:

    python3 tools/diag_household_gate.py                 # against the bundled stack (host)
    python3 tools/diag_household_gate.py --base http://jellyfin:8096

It mints one login (so it creates a device session in Jellyfin, as any sign-in does) and makes
only GET requests. It never creates, alters or deletes an account. The password is read from the
repo ``.env`` and never printed.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from config.env_file import parse_env_file  # noqa: E402
from config.settings import get_config  # noqa: E402
from services.auth import authenticate_jellyfin  # noqa: E402
from services.library.factory import build_library_service  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://host.docker.internal:8098",
                    help="how THIS machine reaches Jellyfin (default: the bundled stack's host port)")
    ap.add_argument("--env", default=str(ROOT / ".env"))
    args = ap.parse_args()

    env = parse_env_file(args.env)
    user = env.get("RKM_JELLYFIN_ADMIN_USER", "admin")
    password = env.get("RKM_JELLYFIN_ADMIN_PASSWORD", "")

    print("== the api's own configuration ==")
    cfg = get_config()
    print(f"   JELLYFIN_URL     : {cfg.JELLYFIN_URL}")
    print(f"   JELLYFIN_API_KEY : {'set (len %d)' % len(cfg.JELLYFIN_API_KEY) if cfg.JELLYFIN_API_KEY else 'EMPTY'}")
    print(f"   admin user       : {user!r}   password present: {bool(password)}")
    service = build_library_service(cfg)
    print(f"   factory returns  : {type(service).__name__ if service else 'None'}")
    if service is None:
        print("   ^ None means no URL or no key, so the admin gate cannot ask the server at all.")
        print("     On the bundled stack the key arrives through /shared/runtime.json, written by")
        print("     the provisioner — check the api container has it, not the repo .env.")
        print("     The gate now answers 503 (not 403) in this state.")

    print("\n== the app's OWN login path, against the real server ==")
    cfg.JELLYFIN_URL = args.base
    try:
        identity = authenticate_jellyfin(user, password, config=cfg)
    except Exception as exc:  # noqa: BLE001
        print(f"   login FAILED: {type(exc).__name__}: {exc}")
        return 1
    print(f"   login ok: id {identity.user_id[:8]}…  name {identity.user_name!r}")

    print("\n== the provider path the routes use, with that token ==")
    cfg.JELLYFIN_API_KEY = identity.token
    service = build_library_service(cfg)
    if service is None:
        print("   factory returned None even with a token — cannot continue")
        return 1
    rows = service.list_users()
    print(f"   list_users()     : {len(rows)} accounts {[(r['name'], r['is_admin']) for r in rows]}")
    print(f"   last_api_error() : {service.last_api_error()}")
    policy = service.get_user_policy(identity.user_id)
    print(f"   get_user_policy(): IsAdministrator={(policy or {}).get('IsAdministrator')!r} "
          f"IsDisabled={(policy or {}).get('IsDisabled')!r}")
    print(f"   last_api_error() : {service.last_api_error()}")
    allowed = bool(policy and policy.get("IsAdministrator")) and not bool((policy or {}).get("IsDisabled"))
    print(f"\n   => the gate answers: {'ALLOW (200)' if allowed else 'REFUSE (403)'}")
    print("   The token came from a fresh login, so a REFUSE here means the app's own GET /Users")
    print("   calls are wrong against this server — not a stale credential.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
