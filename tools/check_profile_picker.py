#!/usr/bin/env python3
"""Profile picker DOM check — "Who's watching?" (PLEX_PROFILE_AUTH_PLAN Phase B).

`tools/check_login_flow.py` proves the SESSION flow; this proves the PICKER by content, in a real
browser, against the real `ProfilesView` (plus the real `AuthProvider`, `RequireSession` and
`Header`) over a stubbed api. Five scenarios, each about a rule rather than a happy path:

  A. signed in, NOBODY CHOSEN — the picker is shown and app content NEVER appears (asserted with a
     MutationObserver, so the app cannot flash before the question is asked); the rows carry the
     server's own facts (a lock where a password is required, a disabled row that is not
     selectable WITH the reason); no row claims "Watching now" while nobody has been chosen; and
     the picker makes NO `/api/admin/libraries` call — that route is refused the moment somebody
     else's profile is selected, so offering it here would be an app telling the server to say no.
  B. a PASSWORD-LESS profile — clicking it posts an EMPTY password (that is how members are made)
     and lands in the app with that profile in the header.
  C. a PROTECTED profile — the picker asks FIRST (zero requests until the prompt is submitted, so a
     blank post cannot be sent by accident), a blank attempt is refused with the generic message,
     a wrong password likewise, and the right one lands in the app.
  D. an ADMINISTRATOR's profile with no password of its own — still asks (the server refuses a
     blank attempt on it regardless), then accepts a non-empty value.
  E. already chosen — the app renders straight away and the picker is NOT shown; the header's
     "Switch profile" brings the picker back with that profile marked "Watching now" (without that,
     the switcher would bounce straight off the picker's own "nothing to pick" rule).
  F. a DISABLED profile is not selectable and clicking it does nothing at all.

Run (sandbox):
    cd frontend && npx vite --port 5199 --strictPort &
    python3 tools/check_profile_picker.py [--base http://localhost:5199] [--shots DIR]
"""
from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright

FRAME = "/harness/profile-frame.html"
ADMIN_PW = "admin-pw"
LOCKED_PW = "locked-pw"

PROBLEMS: list[str] = []


def problem(message: str) -> None:
    PROBLEMS.append(message)


def load(page, base: str, query: str) -> dict:
    page.goto(f"{base}{FRAME}?{query}", wait_until="networkidle")
    page.wait_for_function("() => !!window.__probe", timeout=15_000)
    page.wait_for_timeout(600)
    return probe(page)


def probe(page) -> dict:
    return page.evaluate("() => window.__probe()")


def rows_by_name(state: dict) -> dict[str, dict]:
    return {row["name"]: row for row in state["rows"]}


def select_calls(state: dict) -> list[dict]:
    return [c for c in state["calls"] if c["url"] == "/api/auth/profile"]


def click_row(page, profile_id: str) -> None:
    page.click(f'[data-testid="profile-{profile_id}"]')


def scenario_a(page, base: str, shots: str) -> None:
    """Nobody chosen: the question is asked, and the app is not on screen to be watched."""
    state = load(page, base, "signedIn=1&profileSelected=0")
    print("\n=== A. signed in, no profile chosen ===")
    print(f"  picker shown         : {state['hasPicker']} (want True)")
    print(f"  app content shown    : {state['hasAppContent']} (want False)")
    print(f"  app content EVER seen: {state['sawAppContent']} (want False)")
    print(f"  rows                 : {[r['name'] for r in state['rows']]}")

    if not state["hasPicker"]:
        problem("A: a signed-in session with no profile was not asked who is watching")
    if state["hasAppContent"] or state["sawAppContent"]:
        problem("A: app content appeared before a profile was chosen")
    if len(state["rows"]) != 5:
        problem(f"A: expected the 5 server profiles, got {len(state['rows'])}")

    rows = rows_by_name(state)
    if not rows.get("admin", {}).get("locked"):
        problem("A: the administrator's profile shows no lock — it always asks for a password")
    if not rows.get("Locked", {}).get("locked"):
        problem("A: a password-protected profile shows no lock")
    if rows.get("Guest", {}).get("locked"):
        problem("A: a password-LESS profile shows a lock — clicking it needs nothing typed")
    if rows.get("Owner", {}).get("locked") is not True:
        problem("A: an administrator with NO password of its own shows no lock, but the server "
                "still refuses a blank attempt on that profile")
    if not rows.get("Off", {}).get("disabled"):
        problem("A: a disabled profile was offered as selectable")
    elif "switched off" not in rows["Off"]["text"]:
        problem(f"A: the disabled row does not say why: {rows['Off']['text']!r}")
    if any("Watching now" in row["text"] for row in state["rows"]):
        problem("A: a row claims 'Watching now' before anybody has been chosen")
    if not state["signOutButton"]:
        problem("A: the picker offers no way out (Sign out)")

    admin_calls = [c for c in state["calls"] if c["url"].startswith("/api/admin/")]
    if admin_calls:
        problem(f"A: the picker called an ADMIN route: {sorted({c['url'] for c in admin_calls})} "
                "— those are refused while somebody else's profile is selected")

    if shots:
        Path(shots).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(shots) / "picker.png"))


def scenario_b(page, base: str) -> None:
    """A password-less profile must open with NOTHING typed."""
    load(page, base, "signedIn=1&profileSelected=0")
    print("\n=== B. choosing a password-less profile (Guest) ===")
    click_row(page, "uid-guest")
    page.wait_for_timeout(800)
    state = probe(page)
    sent = select_calls(state)
    print(f"  prompt shown         : {state['passwordForm']} (want False - nothing to type)")
    print(f"  posted body          : {sent[-1]['body'] if sent else '(no call!)'}")
    print(f"  app content rendered : {state['hasAppContent']} (want True)")
    print(f"  chip                 : {state['chipLabel']!r}")

    if state["passwordForm"]:
        problem("B: a password-less profile was asked for a password")
    if not sent:
        problem("B: clicking the profile never reached the API")
    else:
        body = sent[-1]["body"].replace(" ", "")
        if '"user_id":"uid-guest"' not in body or '"password":""' not in body:
            problem(f"B: the request did not carry the id and an empty password: {sent[-1]['body']!r}")
    if not state["hasAppContent"]:
        problem("B: choosing a profile did not land in the app")
    if "Watching as Guest" != state["chipLabel"]:
        problem(f"B: the header does not name the chosen profile: {state['chipLabel']!r}")
    if state["hasPicker"]:
        problem("B: still on the picker after choosing a profile")


def scenario_c(page, base: str) -> None:
    """A protected profile: ask first, and report the refusals honestly."""
    load(page, base, "signedIn=1&profileSelected=0")
    print("\n=== C. choosing a protected profile (Locked) ===")
    click_row(page, "uid-locked")
    page.wait_for_selector('[data-testid="profile-password-form"]', timeout=5_000)
    state = probe(page)
    print(f"  prompt shown         : {state['passwordForm']} (want True)")
    print(f"  prompt names it      : {'Locked' in state['prompt']} (want True)")
    print(f"  requests so far      : {len(select_calls(state))} (want 0 - nothing posted yet)")

    if not state["passwordForm"]:
        problem("C: a protected profile was entered without being asked for its password")
    if select_calls(state):
        problem("C: the picker posted a selection BEFORE the password was typed")
    if "Locked" not in state["prompt"]:
        problem(f"C: the prompt does not say which profile it is for: {state['prompt']!r}")

    # a BLANK attempt: the server refuses it, and the screen must say so without inventing a reason
    page.click('[data-testid="profile-password-form"] button[type=submit]')
    page.wait_for_timeout(700)
    state = probe(page)
    print("\n  --- blank password ---")
    print(f"  error                : {state['error']!r}")
    print(f"  still on the picker  : {state['hasPicker']} (want True)")
    if "not correct" not in state["error"]:
        problem(f"C: a blank attempt produced no honest message: {state['error']!r}")
    if not state["hasPicker"]:
        problem("C: a blank attempt navigated away instead of staying on the picker")
    if not any(c["status"] == 401 for c in select_calls(state)):
        problem("C: the stub never refused the blank attempt — the check proved nothing")

    # a WRONG password: the same generic message, never echoing what was typed
    page.fill("#rkm-profile-password", "definitely-wrong")
    page.click('[data-testid="profile-password-form"] button[type=submit]')
    page.wait_for_timeout(700)
    state = probe(page)
    print("\n  --- wrong password ---")
    print(f"  error                : {state['error']!r}")
    if "not correct" not in state["error"]:
        problem(f"C: a wrong password produced no generic message: {state['error']!r}")
    if "definitely-wrong" in state["body"]:
        problem("C: the screen echoed the password back")

    # the RIGHT one
    page.fill("#rkm-profile-password", LOCKED_PW)
    page.click('[data-testid="profile-password-form"] button[type=submit]')
    page.wait_for_timeout(800)
    state = probe(page)
    print("\n  --- correct password ---")
    print(f"  app content rendered : {state['hasAppContent']} (want True)")
    print(f"  chip                 : {state['chipLabel']!r}")
    if not state["hasAppContent"]:
        problem("C: the correct password did not land in the app")
    if "Watching as Locked" != state["chipLabel"]:
        problem(f"C: the header does not name the profile: {state['chipLabel']!r}")


def scenario_d(page, base: str) -> None:
    """An administrator's profile with NO password of its own still asks (decision 3)."""
    load(page, base, "signedIn=1&profileSelected=0")
    print("\n=== D. an administrator's profile with no password set ===")
    click_row(page, "uid-owner-nopw")
    page.wait_for_selector('[data-testid="profile-password-form"]', timeout=5_000)
    state = probe(page)
    print(f"  prompt shown         : {state['passwordForm']} (want True)")
    print(f"  requests so far      : {len(select_calls(state))} (want 0)")
    if not state["passwordForm"]:
        problem("D: the administrator's profile was entered WITHOUT being asked — the server "
                "refuses a blank attempt on it whatever the account holds")
    if select_calls(state):
        problem("D: a blank selection was posted for the administrator's profile")

    page.fill("#rkm-profile-password", "anything-at-all")
    page.click('[data-testid="profile-password-form"] button[type=submit]')
    page.wait_for_timeout(800)
    state = probe(page)
    print(f"  app content rendered : {state['hasAppContent']} (want True)")
    print(f"  chip                 : {state['chipLabel']!r}")
    if not state["hasAppContent"]:
        problem("D: a non-empty attempt did not open the administrator's profile")


def scenario_e(page, base: str) -> None:
    """Already chosen: straight in — and the header's switcher still reaches the picker."""
    state = load(page, base, "signedIn=1&profileSelected=1")
    print("\n=== E. a profile is already chosen ===")
    print(f"  app content rendered : {state['hasAppContent']} (want True)")
    print(f"  picker shown         : {state['hasPicker']} (want False)")
    print(f"  chip                 : {state['chipLabel']!r}")
    print(f"  switcher offered     : {state['switchLink']!r}")
    if not state["hasAppContent"]:
        problem("E: a session with a chosen profile was sent to the picker")
    if state["hasPicker"]:
        problem("E: the picker was shown although somebody is already watching")
    if state["switchLink"] != "Switch profile":
        problem(f"E: the header offers no way to switch profile: {state['switchLink']!r}")

    page.click('a[href="/profiles?switch=1"]')
    page.wait_for_timeout(700)
    state = probe(page)
    rows = {r["name"]: r for r in state["rows"]}
    marked = [name for name, row in rows.items() if "Watching now" in row["text"]]
    print("\n  --- after clicking Switch profile ---")
    print(f"  picker shown         : {state['hasPicker']} (want True)")
    print(f"  rows marked watching : {marked} (want ['admin'])")
    if not state["hasPicker"]:
        problem("E: 'Switch profile' did not reach the picker (the picker bounced it back)")
    if marked != ["admin"]:
        problem(f"E: the current profile is not marked, or more than one is: {marked}")


def scenario_f(page, base: str) -> None:
    """A disabled profile is not selectable, and clicking it changes nothing."""
    state = load(page, base, "signedIn=1&profileSelected=0")
    print("\n=== F. a disabled profile ===")
    rows = rows_by_name(state)
    print(f"  disabled button      : {rows.get('Off', {}).get('disabled')} (want True)")
    if not rows.get("Off", {}).get("disabled"):
        problem("F: the disabled profile is clickable")

    before = len(select_calls(state))
    # A programmatic click on purpose: even bypassing the browser's own actionability rules must
    # not select a disabled profile — the button is inert, not merely hard to press.
    page.eval_on_selector('[data-testid="profile-uid-off"]', "el => el.click()")
    page.wait_for_timeout(500)
    state = probe(page)
    print(f"  selection calls      : {len(select_calls(state))} (want {before})")
    print(f"  app content rendered : {state['hasAppContent']} (want False)")
    if len(select_calls(state)) != before:
        problem("F: clicking a disabled profile attempted a selection")
    if state["hasAppContent"]:
        problem("F: a disabled profile let somebody into the app")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:5199")
    ap.add_argument("--shots", default="")
    args = ap.parse_args()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = browser.new_page(viewport={"width": 1366, "height": 768}, device_scale_factor=1)
        errors: list[str] = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)

        scenario_a(page, args.base, args.shots)
        scenario_b(page, args.base)
        scenario_c(page, args.base)
        scenario_d(page, args.base)
        scenario_e(page, args.base)
        scenario_f(page, args.base)

        if errors:
            print("\n=== browser errors ===")
            for line in dict.fromkeys(errors):
                print(f"  {line}")
            problem(f"the page raised {len(set(errors))} console/page error(s)")

        browser.close()

    if PROBLEMS:
        print("\nFAIL")
        for line in PROBLEMS:
            print(f"  - {line}")
        return 1
    print("\nOK: the picker asks who is watching before the app appears, offers a lock only where "
          "the server really needs a password (including the administrator's own profile), never "
          "claims a current profile before one is chosen, keeps a disabled profile out, reaches no "
          "administrative route, and the header switcher brings it back.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
