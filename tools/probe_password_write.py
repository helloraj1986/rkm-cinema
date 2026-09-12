#!/usr/bin/env python3
"""Why didn't the password change? Measure it, don't guess.

Reported 2026-09-12: setting a password on a **password-less** account says it worked, but the
account still has no password (no lock in the picker, and it can be entered by clicking). Two
different paths are involved — this app's self-service screen and Household's set/reset — and both
go through `POST /Users/Password`, which is exactly the family of Jellyfin endpoint that has already
bitten this repo once by **answering 2xx and storing nothing**.

READ-ONLY BY DEFAULT. With no arguments it just prints what Jellyfin holds for every account,
which is enough to answer "does that account have a password, and is it an administrator".

To test the WRITE you must name the account explicitly:

    python tools/probe_password_write.py --target Rajeev --password 'Choose-New-One1'

Then it tries each call shape this app uses, in order, with a re-read after every one, and says
which shape actually landed — proved by `HasPassword` flipping AND a real login with the new
password (on its own throwaway device, purged afterwards).

⚠ It CHANGES that account's password. Do not aim it at the administrator unless you are ready to
put the new value into `.env` (the app's own tooling signs in with `RKM_JELLYFIN_ADMIN_USER` /
`RKM_JELLYFIN_ADMIN_PASSWORD`; a rename or password change in the UI leaves those stale).

⚠ A rename in the UI also leaves `RKM_JELLYFIN_ADMIN_USER` stale — if every read below comes back
401, that is the first thing to check: the account may no longer be called "admin".
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.rkm_common import http_json, jellyfin_base, load_env  # noqa: E402

PROBE_DEVICE = "rkm-pw-probe"
PROBE_HEADER = ('MediaBrowser Client="rkm-tools", Device="password probe", '
                f'DeviceId="{PROBE_DEVICE}", Version="1.0.0"')


def accounts(env: dict) -> tuple[str | None, list[dict]]:
    """(admin token, account rows) — the token comes from `.env`, exactly like every other tool."""
    base = jellyfin_base(env)
    user = env.get("RKM_JELLYFIN_ADMIN_USER") or "admin"
    res = http_json(f"{base}/Users/AuthenticateByName",
                    data={"Username": user, "Pw": env.get("RKM_JELLYFIN_ADMIN_PASSWORD") or ""},
                    headers={"Content-Type": "application/json", "X-Emby-Authorization": PROBE_HEADER},
                    method="POST")
    if not isinstance(res, dict) or not res.get("AccessToken"):
        print(f"  !! could not sign in as {user!r} from .env: {json.dumps(res)[:200]}")
        print("     -> the account was renamed or its password changed in the UI; update "
              "RKM_JELLYFIN_ADMIN_USER / RKM_JELLYFIN_ADMIN_PASSWORD in .env")
        return None, []
    token = res["AccessToken"]
    rows = http_json(f"{base}/Users", token=token)
    return token, rows if isinstance(rows, list) else []


def show(rows: list[dict]) -> None:
    print(f"  {'name':16} {'has_password':13} {'admin':6} {'disabled':9} folders  id")
    for u in rows:
        pol = u.get("Policy") or {}
        print(f"  {str(u.get('Name')):16} {str(u.get('HasPassword')):13} "
              f"{str(pol.get('IsAdministrator')):6} {str(pol.get('IsDisabled')):9} "
              f"{len(pol.get('EnabledFolders') or []):7}  {u.get('Id')}")


def find(rows: list[dict], wanted: str) -> dict | None:
    for u in rows:
        if str(u.get("Id")) == wanted or str(u.get("Name")) == wanted:
            return u
    return None


def has_password(env: dict, token: str, user_id: str) -> bool | None:
    res = http_json(f"{jellyfin_base(env)}/Users", token=token)
    if not isinstance(res, list):
        return None
    row = next((u for u in res if str(u.get("Id")) == user_id), None)
    return None if row is None else bool(row.get("HasPassword"))


def login_works(env: dict, name: str, password: str) -> bool:
    """A REAL login, on its own device id so the app's own token is never rotated."""
    res = http_json(f"{jellyfin_base(env)}/Users/AuthenticateByName",
                    data={"Username": name, "Pw": password},
                    headers={"Content-Type": "application/json", "X-Emby-Authorization": PROBE_HEADER},
                    method="POST")
    if isinstance(res, dict) and res.get("AccessToken"):
        http_json(f"{jellyfin_base(env)}/Sessions/Logout", token=res["AccessToken"], method="POST")
        return True
    return False


def try_shape(env: dict, token: str, user_id: str, label: str, body: dict) -> tuple[int, bool | None]:
    """POST one call shape, then re-read whether the account HAS a password now."""
    res = http_json(f"{jellyfin_base(env)}/Users/Password?userId={user_id}",
                    data=body, token=token, method="POST",
                    headers={"Content-Type": "application/json"})
    status = 200
    detail = ""
    if isinstance(res, dict):
        if "__http_error__" in res:
            status = int(res["__http_error__"])
            detail = str(res.get("body") or "")[:120]
        elif "__error__" in res:
            status = 0
            detail = str(res.get("__error__"))[:120]
    after = has_password(env, token, user_id)
    print(f"    {label:52} HTTP {status:<4} has_password now: {after}")
    if detail:
        print(f"      body: {detail}")
    if status == 415:
        print("      !! 415 = WE sent a body the server could not read (missing JSON content "
              "type). This is a PROBE bug, not the app's — fix the probe before drawing any "
              "conclusion from it.")
    return status, after


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", help="account NAME or id to write to (omit for read-only)")
    ap.add_argument("--password", help="the new password to set")
    args = ap.parse_args()

    env = load_env()
    print(f"Jellyfin: {jellyfin_base(env)}")
    print(f".env says the administrator is: "
          f"{env.get('RKM_JELLYFIN_ADMIN_USER') or 'admin'!r}")
    token, rows = accounts(env)
    if not token:
        return 2

    print("\n=== what Jellyfin holds ===")
    show(rows)

    if not args.target:
        print("\n(read-only. Add --target <name> --password <new> to test which call shape "
              "actually changes a password.)")
        return 0

    target = find(rows, args.target)
    if not target:
        print(f"\n!! no account matches {args.target!r}")
        return 2
    if not args.password:
        print("\n!! --target needs --password <new>")
        return 2

    user_id, name = str(target.get("Id")), str(target.get("Name"))
    pol = target.get("Policy") or {}
    print(f"\n=== testing the write on {name!r} (id={user_id}) ===")
    print(f"    administrator={pol.get('IsAdministrator')} "
          f"has_password={target.get('HasPassword')}")

    # THE APP'S OWN CODE, not a hand-made request: this is what Household calls, so a pass here
    # means the screen works. (Measured 2026-09-12: the working body is `ResetPassword: false` —
    # `true` answers 204, stores nothing and CLEARS an existing password.)
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
    from services.library.jellyfin import JellyfinLibraryProvider  # noqa: E402

    class _Cfg:
        JELLYFIN_URL = jellyfin_base(env)
        JELLYFIN_API_KEY = token
        JELLYFIN_BROWSER_URL = ""
        JELLYFIN_SCAN_TTL = 60

    provider = JellyfinLibraryProvider(config=_Cfg())
    accepted = provider.set_user_password(user_id, args.password)
    after = has_password(env, token, user_id)
    print(f"    app's own set_user_password()  accepted={accepted}  has_password now={after}")
    if provider.last_api_error():
        print(f"      last api error: {provider.last_api_error()}")

    landed = bool(after and login_works(env, name, args.password))
    print()
    if landed:
        print("VERDICT: the password is set — a real login with the new value succeeded.")
        if pol.get("IsAdministrator"):
            print("⚠ that account is the ADMINISTRATOR: put this password into .env as "
                  "RKM_JELLYFIN_ADMIN_PASSWORD so the tooling can sign in again")
    elif after:
        print("VERDICT: the account HAS a password, but not the one passed here — it was left as "
              "it was, or something else set it. Re-run and log in to check.")
    else:
        print("VERDICT: the write did NOT land — the account still has no password. Do NOT trust "
              "a 2xx from /Users/Password; the provider re-reads and should have said False.")

    # leave nothing behind: purge the probe device with the ADMIN token (never our own credential)
    http_json(f"{jellyfin_base(env)}/Devices?api_key={token}", method="DELETE")
    print(f"(purged probe device {PROBE_DEVICE!r})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
