#!/usr/bin/env python3
"""Sign-in flow DOM check (AUTH_MULTIUSER_PLAN Phase 1; PLEX_PROFILE_AUTH_PLAN Phase B).

`tools/measure_player_layout.py` proves geometry and `tools/check_subtitle_panel.py` proves
the subtitle picker by content; this proves the SESSION flow, in a real browser, against the
real components (`AuthProvider`, `RequireSession`, `LoginView`, `Header`) over a stubbed api:

  A. `?enforce=0` — Phase 1's world: the app renders SIGNED OUT (nothing is enforced), the
     bar offers Sign in, a WRONG password shows the generic error and does NOT sign the app
     out, a correct one lands SIGNED IN — and (Phase B) on "Who's watching?" rather than in the
     app, so the picker is answered before anything can be watched. Sign out flips it back,
     the app staying usable, because nothing is enforced.
  B. `?enforce=1` — the server refuses app calls: the LOGIN view is shown and app content
     NEVER appears (not even for an instant), so enabling enforcement cannot flash the shell
     before bouncing you out.
  C. `?enforce=1&signedIn=1` — a valid session that has chosen a profile is left alone.
  D. a BLANK password — a Jellyfin account with no password must be able to sign in (the form
     must not block the empty submit), and it then picks its profile like anybody else.

What this does NOT prove: the picker's own rules (a lock badge, a password-less member, a
disabled profile, what each refusal says, where a selection lands) — those are
`tools/check_profile_picker.py`'s job, over the same real `ProfilesView`. Nor anything about the
real api: that is the user's deploy and eyeball (see PROGRESS for the runbook).

Run (sandbox):
    cd frontend && npx vite --port 5199 --strictPort &
    python3 tools/check_login_flow.py [--base http://localhost:5199] [--shots DIR]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

FRAME = "/harness/login-frame.html"
GOOD_PASSWORD = "correct-horse"

PROBLEMS: list[str] = []


def problem(message: str) -> None:
    PROBLEMS.append(message)


def load(page, base: str, query: str) -> dict:
    """Open a scenario and return the first settled probe."""
    page.goto(f"{base}{FRAME}?{query}", wait_until="networkidle")
    page.wait_for_function("() => !!window.__probe", timeout=15_000)
    page.wait_for_timeout(700)  # let me() + the enforcement probe settle
    return probe(page)


def probe(page) -> dict:
    return page.evaluate("() => window.__probe()")


def open_account_menu(page) -> dict:
    """Open the account menu from the header avatar and return the probe.

    Since 2026-09-13 the header is a single control (the avatar) and every account destination —
    including Sign out — is an item in this menu. A check that looked for a standalone button finds
    nothing, which is why this helper exists rather than a bare click.
    """
    page.click('[data-testid="account-menu-trigger"]')
    page.wait_for_selector('[role="menu"]', timeout=5000)
    page.wait_for_timeout(150)
    return probe(page)


def auth_calls(state: dict, url: str) -> list[dict]:
    return [c for c in state["calls"] if c["url"] == url]


def pick_profile(page, *, password: str) -> dict:
    """Answer "Who's watching?" — click the row, then the password the picker asks for.

    The prompt is NOT optional here: the only profile this stub offers is the account that just
    signed in, and an administrator's profile always asks (a blank attempt never lands on it).
    Clicking twice (once for the row, once to submit) is the point — a picker that posted
    straight away would be refused by the server and look broken.
    """
    # `[data-profile-name]` picks a ROW: the container's own `profile-picker` testid also starts
    # with "profile-", and clicking that would prove nothing at all.
    row = page.query_selector('[data-testid^="profile-"][data-profile-name]')
    if row is None:
        problem("the picker offered no profile rows at all")
        return probe(page)
    row.click()
    page.wait_for_selector('[data-testid="profile-password-form"]', timeout=5_000)
    page.fill("#rkm-profile-password", password)
    page.click('[data-testid="profile-password-form"] button[type=submit]')
    page.wait_for_timeout(800)
    return probe(page)


def scenario_a(page, base: str, shots: str) -> None:
    """Nothing enforced: the app must work signed out, and sign-in must be optional."""
    state = load(page, base, "enforce=0&signedIn=0")
    print("\n=== A. nothing enforced (?enforce=0, signed out) ===")
    print(f"  app content rendered : {state['hasAppContent']} (want True)")
    print(f"  login form shown     : {state['hasLoginForm']} (want False)")
    print(f"  bar offers Sign in   : {state['signInLink']} (want True)")
    print(f"  the app's own call   : {state['appValue']!r} (want 'app data loaded')")

    if not state["hasAppContent"]:
        problem("A: the app did not render while signed out, but nothing is enforced")
    if state["hasLoginForm"]:
        problem("A: a signed-out visitor was shown a login form with nothing enforced")
    if not state["signInLink"]:
        problem("A: the bar offers no way to sign in at all")
    if state["appValue"] != "app data loaded":
        problem(f"A: the app's own API call did not succeed: {state['appValue']!r}")
    me_calls = auth_calls(state, "/api/auth/me")
    if len(me_calls) != 1:
        problem(f"A: expected exactly ONE /api/auth/me call at startup, got {len(me_calls)}")

    # --- a wrong password: the form keeps the message, and the app is NOT signed out
    page.click('a[href="/login"]')
    page.wait_for_selector("#rkm-username", timeout=5_000)
    page.fill("#rkm-username", "harness")
    page.fill("#rkm-password", "definitely-wrong")
    page.click("button[type=submit]")
    page.wait_for_timeout(600)
    state = probe(page)
    print("\n  --- wrong password ---")
    print(f"  still on the form    : {state['hasLoginForm']} (want True)")
    print(f"  error message        : {state['error']!r} (want the generic one)")
    if not state["hasLoginForm"]:
        problem("A: a wrong password navigated away from the login form")
    if "Incorrect username or password" not in state["error"]:
        problem(f"A: a wrong password produced no generic error: {state['error']!r}")
    if state["signOutButton"] or state["chipLabel"]:
        problem("A: a wrong password somehow signed the app IN/OUT (the form's 401 must be inert)")
    if not any(c["status"] == 401 for c in auth_calls(state, "/api/auth/login")):
        problem("A: the stub never rejected the wrong password — the check proved nothing")

    # --- a correct password: signed in, and asked WHO IS WATCHING (Phase B)
    page.fill("#rkm-password", GOOD_PASSWORD)
    page.click("button[type=submit]")
    page.wait_for_timeout(800)
    state = probe(page)
    print("\n  --- correct password ---")
    print(f"  login form gone      : {not state['hasLoginForm']} (want True)")
    print(f"  picker shown         : {state['hasPicker']} (want True - nobody has been chosen)")
    print(f"  app content shown    : {state['hasAppContent']} (want False)")
    if state["hasLoginForm"]:
        problem("A: still on the login form after the CORRECT password")
    if not state["hasPicker"]:
        problem("A: a successful sign-in did not ask who is watching")
    if state["hasAppContent"]:
        problem("A: the app rendered before a profile was chosen")

    # …then answer it, and land in the app as that profile.
    state = pick_profile(page, password=GOOD_PASSWORD)
    print("\n  --- after choosing the profile ---")
    print(f"  picker gone          : {not state['hasPicker']} (want True)")
    print(f"  app content rendered : {state['hasAppContent']} (want True)")
    print(f"  avatar               : {state['chipLabel']!r} (want the profile name)")
    print(f"  Sign out offered     : {state['signOutButton']} (want True)")
    if state["hasPicker"]:
        problem("A: still on the picker after choosing a profile")
    if not state["hasAppContent"]:
        problem("A: choosing a profile did not land on the app")
    if "Harness User" not in state["chipLabel"]:
        problem(f"A: the account menu does not name the profile: {state['chipLabel']!r}")
    # ⚠ Since 2026-09-13 the header is ONE control: Sign out lives inside the account menu, so the
    # check opens it. `signOutButton` alone would read False even though it is offered.
    state = open_account_menu(page)
    if "Sign out" not in state["accountMenuItems"]:
        problem(f"A: no Sign out in the account menu: {state['accountMenuItems']}")
    sent = auth_calls(state, "/api/auth/profile")
    if not sent:
        problem("A: choosing a profile never reached the API")
    elif '"user_id":"harness-uid"' not in sent[-1]["body"].replace(" ", ""):
        problem(f"A: the selection did not carry the profile id: {sent[-1]['body']!r}")

    # --- sign out
    page.click("[role=\"menuitem\"]:has-text('Sign out')")
    page.wait_for_timeout(700)
    state = probe(page)
    print("\n  --- sign out ---")
    print(f"  signed-in controls   : {bool(state['chipLabel'])} (want False)")
    print(f"  bar offers Sign in   : {state['signInLink']} (want True)")
    print(f"  app still usable     : {state['hasAppContent']} (want True - nothing enforces)")
    if state["signOutButton"] or state["chipLabel"]:
        problem("A: still signed in after Sign out")
    if not state["signInLink"]:
        problem("A: no Sign in offer after signing out")
    if not state["hasAppContent"]:
        problem("A: signing out removed the app even though nothing is enforced")

    if shots:
        Path(shots).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(shots) / "login-signed-out.png"))


def scenario_b(page, base: str, shots: str) -> None:
    """Enforced: go straight to the login view, and never flash app content."""
    state = load(page, base, "enforce=1&signedIn=0")
    print("\n=== B. enforced (?enforce=1, signed out) ===")
    print(f"  login form shown     : {state['hasLoginForm']} (want True)")
    print(f"  app on screen now    : {state['hasAppContent']} (want False)")
    print(f"  app content EVER seen: {state['sawAppContent']} (want False)")
    if not state["hasLoginForm"]:
        problem("B: the guard did not show the login view when the server refused app calls")
    if state["hasAppContent"]:
        problem("B: app content is on screen alongside the login view")
    if state["sawAppContent"]:
        problem("B: the app rendered before the bounce — enforcement must not flash the shell")
    if not any(c["status"] == 401 for c in state["calls"] if c["url"].startswith("/api/")):
        problem("B: no app call was ever refused — the stub did not enforce anything")

    if shots:
        Path(shots).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(shots) / "login-enforced.png"))


def scenario_c(page, base: str) -> None:
    """Enforced, but this browser HAS a session that has chosen a profile: leave it alone."""
    state = load(page, base, "enforce=1&signedIn=1")
    print("\n=== C. enforced with a valid session (?enforce=1&signedIn=1) ===")
    print(f"  app content rendered : {state['hasAppContent']} (want True)")
    print(f"  login form shown     : {state['hasLoginForm']} (want False)")
    print(f"  picker shown         : {state['hasPicker']} (want False - a profile is chosen)")
    print(f"  chip                 : {state['chipLabel']!r}")
    if not state["hasAppContent"]:
        problem("C: a valid session was sent to the login view")
    if state["hasLoginForm"]:
        problem("C: a valid session was shown the login form")
    if state["hasPicker"]:
        problem("C: a session that already chose a profile was sent back to the picker")
    if "Harness User" not in state["chipLabel"]:
        problem(f"C: the chip does not name the session's profile: {state['chipLabel']!r}")


def scenario_d(page, base: str) -> None:
    """A password-LESS household account must be able to sign in through the form.

    The browser's own form validation is the risk here: a `required` password field blocks an
    empty submit, which would make an account with no password impossible to use — and that is
    exactly the account the household flow is being built to create.
    """
    load(page, base, "enforce=0&signedIn=0")
    page.click('a[href="/login"]')
    page.wait_for_selector("#rkm-username", timeout=5_000)
    page.fill("#rkm-username", "guest")
    page.fill("#rkm-password", "")  # blank ON PURPOSE
    page.click("button[type=submit]")
    page.wait_for_timeout(700)
    state = probe(page)
    sent = [c for c in state["calls"] if c["url"] == "/api/auth/login"]
    print("\n=== D. a Jellyfin account with NO password ===")
    print(f"  form still shown     : {state['hasLoginForm']} (want False)")
    print(f"  picker shown         : {state['hasPicker']} (want True)")
    print(f"  posted body          : {sent[-1]['body'] if sent else '(no login call!)'}")

    if not sent:
        problem("D: the blank-password submit never reached the API — browser validation blocked it")
    elif '"password":""' not in sent[-1]["body"].replace(" ", ""):
        problem(f"D: the request did not carry an empty password: {sent[-1]['body']!r}")
    if state["hasLoginForm"]:
        problem("D: a blank password was rejected by the form instead of the API")
    if not state["hasPicker"]:
        problem("D: a blank-password sign-in did not reach the picker")

    # The profile that signed in has no password of its own, so any value the picker asks for is
    # accepted — Jellyfin has nothing to compare against (measured 2026-09-12).
    state = pick_profile(page, password="anything-at-all")
    print(f"  chip after choosing  : {state['chipLabel']!r} (want the password-less user)")
    if not state["hasAppContent"]:
        problem("D: choosing a profile did not land on the app")
    if "No-Password User" not in state["chipLabel"]:
        problem(f"D: the chip does not name the password-less profile: {state['chipLabel']!r}")


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
        scenario_b(page, args.base, args.shots)
        scenario_c(page, args.base)
        scenario_d(page, args.base)

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
    print("\nOK: signed-out stays usable, sign-in is optional and honest and now asks WHO IS "
          "WATCHING, a password-LESS account can sign in and pick its profile, the enforced world "
          "goes straight to the login view, and a valid session with a profile is left alone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
