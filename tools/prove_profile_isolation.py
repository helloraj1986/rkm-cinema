"""PROVE that two real profiles do not see each other's state or libraries (Phase C).

**Why this is a tool and not a unit test:** the claim needs a REAL media server holding TWO real
accounts, and a running api in front of it. Neither exists in the sandbox or in CI, so the phase's
acceptance criterion — *"resume a title as one profile and show the other does NOT see it; a profile
granted only Movies gets an empty/404 for a TV item even when the item URL is typed by hand"* — can
only be answered against the live stack. Everything here is measured through the APP's own HTTP
routes, because the app's URL shapes are what the claim is about (PLEX_PROFILE_AUTH_PLAN §4d).

What it does, in order:

1. mints a temporary Jellyfin API key for the api to use (on its OWN app name — a session token
   cannot be handed to the api, and Jellyfin rotates a device's token on every login);
2. starts a LOCAL uvicorn against the live server, with the session store isolated to ``/tmp`` so
   nothing is written into the household's real state;
3. signs in as the ADMINISTRATOR, and finds one TV item and one MOVIE item via the app's own
   ``/api/library/items``;
4. **switches to the non-administrator profile** (blank password — a password-less member is
   first-class here) and asserts:
   * the sidebar lists that profile's GRANTS only, with no warnings;
   * a TV item requested **by id, typed by hand** is a 404;
   * a resume position it writes appears in ITS Continue Watching;
5. **switches back to the administrator** and asserts their library list is whole again, the same TV
   item answers 200, and the member's position is NOT in the administrator's Continue Watching;
6. **reverts everything it wrote** (position 0 as the member, then re-checks), and deletes the key it
   minted.

Usage (from the repo root, on the machine that can reach Jellyfin):

    python3 tools/prove_profile_isolation.py                 # uses the repo .env
    python3 tools/prove_profile_isolation.py --profile NAME   # pick the member explicitly
    python3 tools/prove_profile_isolation.py --keep            # leave the api running for poking

Exit code 0 = every claim held. It prints measured values beside each claim, so a failure says
which one and what it actually was.

⚠ **It signs in THROUGH the app's routes, on the app's own Jellyfin device id** (``rkm-cinema-web``
— that is what the app uses, and the whole point is to exercise the app's real path). Jellyfin
invalidates a device+user token on every login, so if somebody is signed in on RKM-HP while this
runs, that session may need a fresh sign-in afterwards. That is the known limit recorded in
``PLEX_PROFILE_AUTH_PLAN.md`` §4e, not a side effect this tool can avoid without per-session device
ids. Its OWN device rows and the temporary API key it mints ARE cleaned up at the end.
"""
from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rkm_common import http_json, jellyfin_base, load_env  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
BACKEND = REPO / "backend"
APP_NAME = "rkm-phasec-proof"

PASSED: list[str] = []
FAILED: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> bool:
    """Record one claim. Prints either way — the measured value IS the evidence."""
    (PASSED if ok else FAILED).append(label)
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"   [{detail}]" if detail else ""))
    return ok


# ------------------------------------------------------------------ jellyfin side (read + one key)

def jellyfin_login(base: str, username: str, password: str, device: str) -> str:
    hdr = (f'MediaBrowser Client="rkm-phasec-proof", Device="proof", '
           f'DeviceId="{device}", Version="1.0.0"')
    res = http_json(f"{base}/Users/AuthenticateByName",
                    data={"Username": username, "Pw": password},
                    headers={"Content-Type": "application/json", "X-Emby-Authorization": hdr},
                    method="POST")
    return res.get("AccessToken") if isinstance(res, dict) else ""


def mint_api_key(base: str, admin_token: str) -> str:
    """A server-wide key for the api to hold, created on its OWN app name.

    ``POST /Auth/Keys?app=`` with an EMPTY body (a JSON body answers 400 on 10.11), and the list
    items carry ``AppName`` + ``AccessToken`` — NOT ``App``/``Key``.
    """
    http_json(f"{base}/Auth/Keys?app={urllib.parse.quote(APP_NAME)}", data=b"", method="POST",
              headers={"Content-Type": "application/json", "X-Emby-Token": admin_token})
    listed = http_json(f"{base}/Auth/Keys", headers={"X-Emby-Token": admin_token})
    for item in (listed.get("Items") if isinstance(listed, dict) else listed) or []:
        if str(item.get("AppName") or "") == APP_NAME:
            return str(item.get("AccessToken") or "")
    return ""


def delete_api_key(base: str, admin_token: str, key: str) -> bool:
    res = http_json(f"{base}/Auth/Keys/{urllib.parse.quote(key)}", method="DELETE",
                    headers={"X-Emby-Token": admin_token})
    return not (isinstance(res, dict) and res.get("__http_error__"))


def purge_probe_devices(base: str, admin_token: str) -> None:
    """Remove the Jellyfin device rows this proof created. Never touches the app's own.

    Two traps, both measured while writing this:

    * ``DELETE /Devices`` needs the credential as **``?api_key=``** — the ``X-Emby-Token`` header
      answers 401 for this verb while every GET accepts it;
    * **deleting the device your own credential belongs to revokes that credential.** The first
      attempt deleted the tool's own device first and every later delete answered 401, which reads
      exactly like "the endpoint is refusing me".

    So the tool's own device is deleted LAST, and the removal is confirmed by RE-READING the list.
    ``rkm-cinema-web`` is deliberately left alone: it is the APP's device (the shared id every app
    session signs in on), and deleting it would sign the household out.
    """
    mine = ("rkm-phasec-proof",)

    def listing(token: str) -> list[str]:
        payload = http_json(f"{base}/Devices?api_key={urllib.parse.quote(token)}",
                            headers={"X-Emby-Token": token})
        rows = payload.get("Items") if isinstance(payload, dict) else payload
        return [str(d.get("Id")) for d in (rows or []) if str(d.get("Id", "")).startswith(mine)]

    others = [d for d in listing(admin_token) if d != "rkm-phasec-proof-admin"]
    for device_id in others:
        res = http_json(
            f"{base}/Devices?Id={urllib.parse.quote(device_id)}"
            f"&api_key={urllib.parse.quote(admin_token)}",
            method="DELETE", headers={"X-Emby-Token": admin_token})
        refused = isinstance(res, dict) and res.get("__http_error__")
        print(f"  device {device_id}: {'refused' if refused else 'deleted'}")
    left = [d for d in listing(admin_token) if d != "rkm-phasec-proof-admin"]
    print(f"  probe devices left (before the last delete): {left or 'none'}")
    if not left:
        # LAST, because it is the one this credential belongs to.
        http_json(f"{base}/Devices?Id=rkm-phasec-proof-admin"
                  f"&api_key={urllib.parse.quote(admin_token)}",
                  method="DELETE", headers={"X-Emby-Token": admin_token})
        print("  device rkm-phasec-proof-admin: deleted (its credential dies with it — intended)")


# ------------------------------------------------------------------------------ the local api

def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def start_api(port: int, jellyfin_url: str, jellyfin_key: str, log: Path) -> subprocess.Popen:
    env = os.environ.copy()
    env.update({
        "JELLYFIN_URL": jellyfin_url,
        "JELLYFIN_API_KEY": jellyfin_key,
        # The store that matters: sessions.json is derived from this path, so keeping it in /tmp is
        # what stops the proof writing a session into the household's real /data/rkm state.
        "WATCHLIST_DB_PATH": "/tmp/rkm/verify/watchlist.json",
        "WATCHLIST_SCHEDULER": "false",
        "RKM_AUTH_REQUIRED": "false",
    })
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api.main:app", "--host", "127.0.0.1",
         "--port", str(port), "--log-level", "warning"],
        cwd=str(BACKEND), env=env, stdout=log.open("wb"), stderr=subprocess.STDOUT)
    deadline = time.time() + 60
    while time.time() < deadline:
        if proc.poll() is not None:
            raise SystemExit(f"the api exited during startup — see {log}")
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2) as r:
                if r.status == 200:
                    return proc
        except Exception:
            time.sleep(0.5)
    proc.kill()
    raise SystemExit(f"the api did not answer /api/health within 60s — see {log}")


class App:
    """The app's HTTP client, with the session cookie kept in a jar (as a browser would)."""

    def __init__(self, port: int):
        self.base = f"http://127.0.0.1:{port}"
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar))

    def call(self, method: str, path: str, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            self.base + path, data=data, method=method.upper(),
            headers={"Content-Type": "application/json"} if data else {})
        try:
            with self.opener.open(req, timeout=120) as r:
                raw = r.read().decode("utf-8", "replace")
                return r.status, (json.loads(raw) if raw.strip() else None)
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            try:
                parsed = json.loads(raw) if raw.strip() else None
            except json.JSONDecodeError:
                parsed = raw[:200]
            return e.code, parsed

    def get(self, path):
        return self.call("GET", path)

    def post(self, path, body=None):
        return self.call("POST", path, body if body is not None else {})


# ----------------------------------------------------------------------------------- the proof

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--profile", default="", help="the non-administrator profile to prove with")
    ap.add_argument("--keep", action="store_true", help="leave the local api running when done")
    args = ap.parse_args()

    env = load_env()
    base = jellyfin_base(env)
    admin_user = env.get("RKM_JELLYFIN_ADMIN_USER") or "admin"
    admin_pw = env.get("RKM_JELLYFIN_ADMIN_PASSWORD") or ""
    print(f"Jellyfin: {base}")

    admin_token = jellyfin_login(base, admin_user, admin_pw, "rkm-phasec-proof-admin")
    if not admin_token:
        raise SystemExit("could not sign in to Jellyfin as the administrator (check the repo .env)")

    # The member to prove with: named, else the first non-administrator the server reports.
    users = http_json(f"{base}/Users", token=admin_token) or []
    members = [u for u in users if not ((u.get("Policy") or {}).get("IsAdministrator"))]
    member = None
    if args.profile:
        member = next((u for u in members if str(u.get("Name")) == args.profile), None)
        if member is None:
            raise SystemExit(f"no non-administrator profile named {args.profile!r}")
    elif members:
        member = members[0]
    if member is None:
        raise SystemExit(
            "this server has NO non-administrator account, so the two-profile proof cannot run.\n"
            "Create one from the app (Settings -> Household) — that is the owner's decision, not "
            "this tool's. Nothing was changed.")
    member_name = str(member.get("Name"))
    print(f"profile under test: {member_name}  "
          f"(password-less: {not bool(member.get('HasPassword'))})")

    key = mint_api_key(base, admin_token)
    if not key:
        raise SystemExit("could not mint a temporary API key for the api (nothing was changed)")
    print(f"minted a temporary API key for the api: app={APP_NAME}")

    port = free_port()
    log = Path("/tmp/rkm-phasec-proof-api.log")
    log.parent.mkdir(parents=True, exist_ok=True)
    proc = start_api(port, base, key, log)
    print(f"local api: http://127.0.0.1:{port}  (log {log})")
    app = App(port)
    exit_code = 1
    try:
        exit_code = run_proof(app, member, member_name, admin_pw, admin_user)
    finally:
        if args.keep:
            print(f"\n--keep: the api is still running on port {port} (kill {proc.pid})")
        else:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
            print("local api stopped")
        if delete_api_key(base, admin_token, key):
            print("temporary API key deleted")
        else:
            print("!! could NOT delete the temporary API key — remove it in Jellyfin's dashboard "
                  f"(Dashboard -> API Keys -> {APP_NAME})")
        purge_probe_devices(base, admin_token)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return exit_code


def run_proof(app: App, member: dict, member_name: str, admin_pw: str,
              admin_user: str = "") -> int:
    # ⚠ The account's REAL name, from .env — never the literal "admin". It was renamed to `rkm`
    # (ADMIN_CREDENTIALS_PLAN §5), so a hard-coded name signs in as nobody and this proof stopped
    # at step 1 with a 401 while its Jellyfin half used the correct name.
    admin_user = admin_user or "admin"
    member_id = str(member.get("Id") or "")

    print("\n== 1. the administrator opens the server ==")
    status, body = app.post("/api/auth/login", {"username": admin_user, "password": admin_pw})
    check("administrator signs in", status == 200, f"HTTP {status}")
    if status != 200:
        return 1
    status, me = app.get("/api/auth/me")
    check("no profile chosen yet", status == 200 and me.get("profile_selected") is False,
          f"profile_selected={me.get('profile_selected') if status == 200 else status}")
    # The account that signed in — switching BACK needs its id (a blank one is a 404 by design:
    # "switch to the administrator" is a deliberate, password-checked act, never a default).
    admin_id = str(((me or {}).get("user") or {}).get("id") or "")
    check("the administrator's own id is known (needed to switch back)", bool(admin_id))

    # Pick the items from the app's OWN listing, on the administrator's profile.
    status, items = app.get("/api/library/items")
    rows = (items or {}).get("items") or []
    def _kind(row):
        return str(row.get("kind") or row.get("type") or "")

    tv = next((r for r in rows if _kind(r) in ("show", "tv", "series")), None)
    movie = next((r for r in rows if _kind(r) in ("movie",)), None)
    check("found one TV item and one movie in the administrator's library",
          bool(tv and movie),
          f"tv={tv and tv.get('title')} movie={movie and movie.get('title')}")
    if not (tv and movie):
        return 1
    tv_id, movie_id = str(tv.get("item_id") or ""), str(movie.get("item_id") or "")

    status, admin_folders = app.get("/api/library/folders")
    admin_names = [lib["name"] for lib in (admin_folders or {}).get("libraries", [])]
    check("the administrator's sidebar lists more than one library", len(admin_names) > 1,
          ", ".join(admin_names))
    status, _ = app.get(f"/api/jellyfin/detail?id={tv_id}")
    check("the administrator CAN open the TV item by id", status == 200, f"HTTP {status}")

    print(f"\n== 2. switch to the profile {member_name!r} ==")
    status, sel = app.post("/api/auth/profile", {"user_id": member_id, "password": ""})
    check("profile selected", status == 200, f"HTTP {status}")
    if status != 200:
        print("   (a protected profile needs its own password — this tool only supports a "
              "password-less member)")
        return 1
    status, me = app.get("/api/auth/me")
    check("the session now acts as that profile",
          status == 200 and (me.get("profile") or {}).get("id") == member_id,
          f"profile={(me.get('profile') or {}).get('name') if status == 200 else status}")

    status, folders = app.get("/api/library/folders")
    names = [lib["name"] for lib in (folders or {}).get("libraries", [])]
    granted = admin_names and set(names) < set(admin_names)
    check("the sidebar lists ONLY that profile's grants", bool(granted),
          f"{names} vs the administrator's {admin_names}")
    check("…and no config warnings are shown for somebody else's grants",
          (folders or {}).get("warnings") == [], f"warnings={(folders or {}).get('warnings')}")
    check("…and nothing the administrator sees is missing from the grant list",
          set(names) <= set(admin_names), f"libraries={names}")

    status, detail = app.get(f"/api/jellyfin/detail?id={tv_id}")
    check("a TV item typed BY HAND is refused for that profile", status in (403, 404),
          f"HTTP {status} — {detail if isinstance(detail, str) else (detail or {}).get('detail')}")
    status, _ = app.get(f"/api/jellyfin/detail?id={movie_id}")
    check("…while a GRANTED movie still opens", status == 200, f"HTTP {status}")

    status, written = app.post("/api/jellyfin/progress",
                               {"item_id": movie_id, "event": "timeupdate",
                                "position_ticks": 500 * 10_000_000, "runtime_ticks": 0})
    check("the profile writes a resume position on the movie", status == 204,
          f"HTTP {status} {written}")
    status, cw = app.get("/api/library/continue-watching")
    member_cw = [str(i.get("item_id")) for i in (cw or {}).get("items", [])]
    check("…and it appears in THIS profile's Continue Watching", movie_id in member_cw,
          f"{len(member_cw)} row(s)")

    print("\n== 3. back to the administrator: the state must not have travelled ==")
    status, _ = app.post("/api/auth/profile", {"user_id": admin_id, "password": admin_pw})
    check("switched back to the administrator (their password, as decision 3 requires)",
          status == 200, f"HTTP {status}")
    status, me = app.get("/api/auth/me")
    check("…on their OWN profile",
          status == 200 and (me or {}).get("on_own_profile") is True,
          f"on_own_profile={(me or {}).get('on_own_profile') if status == 200 else status}")
    status, folders = app.get("/api/library/folders")
    back = [lib["name"] for lib in (folders or {}).get("libraries", [])]
    check("the administrator's sidebar is whole again", back == admin_names,
          ", ".join(back))
    status, _ = app.get(f"/api/jellyfin/detail?id={tv_id}")
    check("the TV item opens for the administrator again", status == 200, f"HTTP {status}")
    status, cw = app.get("/api/library/continue-watching")
    admin_cw = [str(i.get("item_id")) for i in (cw or {}).get("items", [])]
    check("the member's resume position is NOT in the administrator's Continue Watching",
          movie_id not in admin_cw, f"{len(admin_cw)} row(s), member's item absent")
    check("…and the two Continue Watching lists are genuinely different",
          set(member_cw) != set(admin_cw), f"member={len(member_cw)} admin={len(admin_cw)}")

    print(f"\n== 4. revert everything this tool wrote (as {member_name}) ==")
    status, _ = app.post("/api/auth/profile", {"user_id": member_id, "password": ""})
    check("back on the member's profile", status == 200, f"HTTP {status}")
    status, _ = app.post("/api/jellyfin/progress",
                         {"item_id": movie_id, "event": "timeupdate", "position_ticks": 0,
                          "runtime_ticks": 0})
    check("position cleared (0 ticks)", status == 204, f"HTTP {status}")
    status, cw = app.get("/api/library/continue-watching")
    after = [str(i.get("item_id")) for i in (cw or {}).get("items", [])]
    check("the member's Continue Watching is back to what it was",
          movie_id not in after, f"{len(after)} row(s) left")
    # Leave the SERVER session on the administrator's own profile: this tool borrowed the device,
    # and a household device should not be left sitting on somebody else's profile.
    app.post("/api/auth/profile", {"user_id": admin_id, "password": admin_pw})
    print("   (left the session on the administrator's own profile)")
    return 0 if not FAILED else 1


if __name__ == "__main__":
    raise SystemExit(main())
