#!/usr/bin/env python3
"""Break-glass: set a new password for the stack's ADMINISTRATOR without knowing the old one.

Run it through the wrapper, which is the only thing to remember:

    .\\rkm-cinema.ps1 reset-admin-password            # shows what it will do, then prompts
    .\\rkm-cinema.ps1 reset-admin-password -DryRun    # read-only: names the administrator and stops

WHY this exists (ADMIN_CREDENTIALS_PLAN.md Phase 4): a forgotten administrator password used to be a
manual recovery. The stack already holds a credential nobody types -- the API key the provisioner
wrote to ``/shared/runtime.json`` in the ``rkm_shared`` volume -- and an administrator's privilege is
what authorises a reset, so this tool needs no remembered secret at all.

The three rules it is built around, each measured rather than assumed:

1. ``ResetPassword`` is sent **False, always** (plan §6c). The plan's own Phase 4 row said ``true``,
   written before it was measured: on Jellyfin 10.11.11 ``true`` answers **204, sets nothing, and
   CLEARS a password that existed**. The caller's privilege is what authorises a reset -- not the
   flag. ``true`` appears nowhere in this file, and a test says so.
2. The target is chosen **by policy** (an enabled ``IsAdministrator``), never by the literal name
   ``admin`` -- the account may have been renamed (plan §5), and a MEMBER can perfectly well be
   called "admin".
3. A 2xx is not evidence (plan §6d): after the write this tool SIGNS IN with the new password and
   reports what it observed. "Could not check" is reported as exactly that, never as success.

The password is never an argument, never printed, never logged: it is typed at a prompt and sent
straight to the media server. (An argument would land in shell history and in the process list.)
"""
from __future__ import annotations

import argparse
import getpass
import json
import subprocess
import sys
import urllib.parse
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import rkm_common as rc  # noqa: E402  (the shared .env/URL plumbing the other tools use)

DEFAULT_PROJECT = "rkm-bundled"
DOCKER_TIMEOUT = 60.0

#: The volume the provisioner writes, and the file inside it. Both are compose-named, so the
#: volume is project-prefixed exactly the way Docker does it.
RUNTIME_FILE = "runtime.json"
RUNTIME_INNER_PATH = f"/shared/{RUNTIME_FILE}"


# --------------------------------------------------------------------------- pure rules

def volume_name(project: str) -> str:
    """The compose volume that holds runtime.json (``rkm-bundled`` -> ``rkm-bundled_rkm_shared``)."""
    return f"{project}_rkm_shared"


def stored_key(runtime_text: str) -> str:
    """The API key out of runtime.json, or ``""``.

    Unreadable or absent is NOT an error here: it is a missing key, and the caller decides what to
    say about it. The one thing this must never do is invent a credential.
    """
    try:
        data = json.loads(runtime_text or "{}")
    except Exception:
        return ""
    if not isinstance(data, dict):
        return ""
    return str(data.get("JELLYFIN_API_KEY") or "")


def password_reset_body(new_password: str) -> dict:
    """The body for ``POST /Users/Password?userId=...``.

    ⚠ ``ResetPassword`` is **False** and this function has no parameter to change it (plan §6c):
    ``true`` is a silent no-op that CLEARS the password it claims to set. An administrator resetting
    a password it does NOT know works with ``false`` -- the caller's privilege authorises it.
    """
    return {"CurrentPw": "", "NewPw": str(new_password), "ResetPassword": False}


def administrators(users) -> list[dict]:
    """The ENABLED policy administrators among ``/Users`` rows, in the server's order.

    By policy, never by name: the administrator may have been renamed (plan §5), and a member may be
    called anything at all.
    """
    found = []
    for row in users or []:
        if not isinstance(row, dict):
            continue
        policy = row.get("Policy") or {}
        if policy.get("IsAdministrator") and not policy.get("IsDisabled"):
            found.append(row)
    return found


def pick_administrator(users, wanted: str = "") -> tuple[Optional[dict], str]:
    """``(row, "")`` for the account to reset, or ``(None, reason)``.

    ``wanted`` (from ``-Name``) must NAME AN ADMINISTRATOR: the break-glass is the lockout recovery,
    not a way to set somebody else's password -- a member's password is changed from Household (or
    by the member, from My password), and quietly resetting one here would be a surprise nobody
    asked for. The reason string is written for the person reading the console, and names what to do
    next.
    """
    admins = administrators(users)
    if wanted:
        target = next((row for row in admins
                       if str(row.get("Name") or "").lower() == str(wanted).lower()), None)
        if target is not None:
            return target, ""
        if next((row for row in (users or [])
                 if isinstance(row, dict)
                 and str(row.get("Name") or "").lower() == str(wanted).lower()), None) is not None:
            return None, (f"'{wanted}' is not an enabled administrator. A member's password is "
                          "changed from Household in the app (or by that person, from My password).")
        return None, f"no account named '{wanted}' on the server."
    if len(admins) == 1:
        return admins[0], ""
    if not admins:
        return None, ("the server reports NO enabled administrator account -- check the stack "
                      "(.\"rkm-cinema.ps1\" status) before resetting anything.")
    names = ", ".join(str(row.get("Name") or "?") for row in admins)
    return None, (f"{len(admins)} enabled administrators on this server ({names}) -- name the one to "
                  "reset with -Name.")


def verify_verdict(auth_result) -> str:
    """``"verified"`` / ``"refused"`` / ``"unavailable"`` from an AuthenticateByName answer.

    The ONLY proof a password change landed is that the new password signs in (plan §6d). A missing
    token is "refused" -- the server answered and did not let us in. A transport error or an
    unexpected shape is "unavailable": we could not ask, so we know nothing either way, and saying
    otherwise would be a false accusation.
    """
    if not isinstance(auth_result, dict):
        return "unavailable"
    status = auth_result.get("__http_error__")
    if status in (401, 403):
        return "refused"
    if status is not None or "__error__" in auth_result:
        return "unavailable"
    return "verified" if str(auth_result.get("AccessToken") or "") else "refused"


# --------------------------------------------------------------------------- docker + http

def _run(cmd: list[str]) -> tuple[int, str, str]:
    """Run a command, returning ``(exit_code, stdout, stderr)`` — never raising.

    stdout and stderr are kept APART on purpose: a ``docker pull`` progress line or a compose
    warning shares stderr with the command's own messages, and parsing JSON out of a mixed stream is
    how a working read turns into "the file is corrupt".
    """
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=DOCKER_TIMEOUT)
    except FileNotFoundError:
        return 127, "", "docker is not on PATH"
    except subprocess.TimeoutExpired:
        return 124, "", f"timed out after {DOCKER_TIMEOUT:.0f}s"
    except Exception as exc:  # noqa: BLE001 - a failed read must report, not crash
        return 1, "", f"{type(exc).__name__}"
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def read_stored_api_key(project: str, *, runner=None) -> tuple[str, str]:
    """``(key, how)`` from the ``rkm_shared`` volume — or ``("", why)``.

    Two ways in, because the break-glass must work in the state the user is actually in:

    * ``docker compose exec`` the RUNNING api container — instant, and the normal case (the stack is
      up and he cannot sign in);
    * ``docker run`` with the volume mounted read-only — the SAME pattern ``backup-rkm-state.ps1``
      uses, so it works when the api container is not running at all.

    ⚠ Never ``.env`` and never a remembered password: a stale ``.env`` must not be the thing that
    fails him (plan §1), and the key in the volume is the credential the stack itself uses.
    """
    run = runner or _run

    # The api image already has python and the volume; re-dumping through json keeps the answer on
    # ONE line whatever the file's formatting.
    inner = ("import json;"
             f"print(json.dumps(json.load(open('{RUNTIME_INNER_PATH}'))))")
    code, out, err = run(["docker", "compose", "-p", project, "exec", "-T", "api", "python", "-c", inner])
    key = stored_key(out.strip().splitlines()[-1] if out.strip() else "")
    if code == 0 and key:
        return key, "the running api container"
    first_problem = err.strip().splitlines()[-1] if err.strip() else f"exit {code}"

    code, out, err = run(["docker", "run", "--rm", "-v", f"{volume_name(project)}:/shared:ro",
                          "alpine:3", "cat", RUNTIME_INNER_PATH])
    key = stored_key(out)
    if code == 0 and key:
        return key, "the rkm_shared volume"

    second_problem = err.strip().splitlines()[-1] if err.strip() else f"exit {code}"
    return "", (f"could not read {RUNTIME_INNER_PATH} from the api container ({first_problem}) or "
                f"from the {volume_name(project)} volume ({second_problem}). Is the stack installed? "
                f"(docker compose -p {project} ps). If the volume itself is gone, a deploy "
                "re-provisions the key -- see docs/OPERATIONS.md.")


def _api(base: str, path: str, key: str, *, data=None, method=None):
    """Call Jellyfin with the stored key. Errors come back as dicts (rkm_common.http_json)."""
    sep = "&" if "?" in path else "?"
    return rc.http_json(f"{base}{path}{sep}api_key={urllib.parse.quote(key)}",
                        data=data, method=method,
                        headers={"Content-Type": "application/json"} if data is not None else None)


def _sign_in(base: str, name: str, password: str):
    """Authenticate as ``name`` with ``password`` — the verification, and nothing else."""
    header = ('MediaBrowser Client="rkm-recovery", Device="recovery", '
              'DeviceId="rkm-recovery-1", Version="1.0.0"')
    return rc.http_json(f"{base}/Users/AuthenticateByName",
                        data={"Username": name, "Pw": password},
                        headers={"Content-Type": "application/json",
                                 "X-Emby-Authorization": header},
                        method="POST")


# --------------------------------------------------------------------------- the tool itself

def _ask_twice() -> str:
    """Prompt for the new password twice. Never an argument: history and the process list leak."""
    while True:
        first = getpass.getpass("New password for the administrator: ")
        if not first:
            print("  ... an empty password is not a reset. An account is created without one, not "
                  "emptied afterwards -- pick something and type it twice.")
            continue
        second = getpass.getpass("Type it again to confirm: ")
        if first != second:
            print("  ... those did not match. Nothing was changed; try again.")
            continue
        return first


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Reset the stack administrator's password (break-glass).")
    ap.add_argument("--project", default=DEFAULT_PROJECT, help="compose project name")
    ap.add_argument("--name", default="", help="the administrator's account name (only needed "
                                               "when the server has more than one)")
    ap.add_argument("--dry-run", action="store_true",
                    help="read-only: name the administrator it WOULD reset and stop")
    ap.add_argument("--base", default="", help="Jellyfin base URL (default: discovered)")
    args = ap.parse_args(argv)

    env = rc.load_env()
    base = rc.jellyfin_base(env, args.base or None)
    print(f"Media server : {base}")

    key, how = read_stored_api_key(args.project)
    if not key:
        print(f"FAIL: {how}")
        return 2
    print(f"API key      : read from {how} (never from .env, never a remembered password)")

    users = _api(base, "/Users", key)
    if isinstance(users, dict):
        status = users.get("__http_error__")
        print("FAIL: the stored API key was refused" +
              (f" (HTTP {status})" if status else f" ({users.get('__error__') or 'no answer'})"))
        print("      An API key can be regenerated by a deploy: .\\rkm-cinema.ps1 deploy")
        return 3
    if not isinstance(users, list):
        print("FAIL: the server did not return a list of accounts.")
        return 3

    target, reason = pick_administrator(users, args.name)
    if target is None:
        print(f"FAIL: {reason}")
        return 4
    target_id = str(target.get("Id") or "")
    target_name = str(target.get("Name") or "")
    print(f"Administrator: {target_name} ({target_id[:8]}...)")

    if args.dry_run:
        print("")
        print("Dry run: nothing was changed. Without -DryRun this would set a new password for")
        print(f"'{target_name}' (ResetPassword=false) and then prove it by signing in.")
        return 0

    print("")
    print("This sets a NEW password for the administrator above, using the stack's own API key.")
    print("It does not need, and will not ask for, the old one.")
    new_password = _ask_twice()

    result = _api(base, f"/Users/Password?userId={urllib.parse.quote(target_id)}", key,
                  data=password_reset_body(new_password), method="POST")
    status = result.get("__http_error__") if isinstance(result, dict) else None
    if isinstance(result, dict) and ("__http_error__" in result or "__error__" in result):
        print(f"FAIL: the media server did not accept the reset (HTTP {status or 'no answer'}).")
        print("      Nothing is known about the change; try .\\rkm-cinema.ps1 status.")
        return 5

    # PROOF, not a status code: sign in with the value we just set (plan §6d).
    verdict = verify_verdict(_sign_in(base, target_name, new_password))
    print("")
    if verdict == "verified":
        print(f"OK: the administrator password was changed. Sign in as '{target_name}' with the new")
        print("    password (the api container needs no restart; passwords are not cached).")
        return 0
    if verdict == "refused":
        print("FAIL: the media server accepted the reset but would NOT sign in with the new")
        print("      password, so the change did NOT take. Nothing else was altered.")
        return 6
    print("DONE, UNPROVEN: the reset was accepted, but the check could not be completed, so")
    print("                nothing is known either way. Try signing in; if the new password does")
    print("                not work, run this again (or .\\rkm-cinema.ps1 status).")
    return 7


if __name__ == "__main__":
    sys.exit(main())
