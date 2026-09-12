#!/usr/bin/env python3
"""Sign-in flow DOM check (AUTH_MULTIUSER_PLAN Phase 1).

`tools/measure_player_layout.py` proves geometry and `tools/check_subtitle_panel.py` proves
the subtitle picker by content; this proves the SESSION flow, in a real browser, against the
real components (`AuthProvider`, `RequireSession`, `LoginView`, `Header`) over a stubbed api:

  A. `?enforce=0` — Phase 1's world: the app renders SIGNED OUT (nothing is enforced), the
     bar offers Sign in, a WRONG password shows the generic error and does NOT sign the app
     out, a correct one lands signed in with the user's name in the chip, and Sign out flips
     it back — the app staying usable, because nothing is enforced.
  B. `?enforce=1` — the server refuses app calls: the LOGIN view is shown and app content
     NEVER appears (not even for an instant), so enabling enforcement cannot flash the shell
     before bouncing you out.
  C. `?enforce=1&signedIn=1` — a valid session is left alone by the guard.

What this does NOT prove: how the real app's pages render (unchanged by Phase 1, and the
harness stands in a fake Home), or anything about the real api — that is the user's deploy
and eyeball (see PROGRESS for the runbook).

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


def auth_calls(state: dict, url: str) -> list[dict]:
    return [c for c in state["calls"] if c["url"] == url]


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

    # --- a correct password
    page.fill("#rkm-password", GOOD_PASSWORD)
    page.click("button[type=submit]")
    page.wait_for_timeout(800)
    state = probe(page)
    print("\n  --- correct password ---")
    print(f"  login form gone      : {not state['hasLoginForm']} (want True)")
    print(f"  chip                 : {state['chipLabel']!r} (want the signed-in name)")
    print(f"  Sign out offered     : {state['signOutButton']} (want True)")
    if state["hasLoginForm"]:
        problem("A: still on the login form after the CORRECT password")
    if "Harness User" not in state["chipLabel"]:
        problem(f"A: the header chip does not name the signed-in user: {state['chipLabel']!r}")
    if not state["signOutButton"]:
        problem("A: no Sign out control beside the chip")
    if not state["hasAppContent"]:
        problem("A: a successful sign-in did not land on the app")

    # --- sign out
    page.click("button:has-text('Sign out')")
    page.wait_for_timeout(700)
    state = probe(page)
    print("\n  --- sign out ---")
    print(f"  signed-in controls   : {state['signOutButton'] or bool(state['chipLabel'])} (want False)")
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
    """Enforced, but this browser HAS a session: leave it alone."""
    state = load(page, base, "enforce=1&signedIn=1")
    print("\n=== C. enforced with a valid session (?enforce=1&signedIn=1) ===")
    print(f"  app content rendered : {state['hasAppContent']} (want True)")
    print(f"  login form shown     : {state['hasLoginForm']} (want False)")
    print(f"  chip                 : {state['chipLabel']!r}")
    if not state["hasAppContent"]:
        problem("C: a valid session was sent to the login view")
    if state["hasLoginForm"]:
        problem("C: a valid session was shown the login form")
    if "Harness User" not in state["chipLabel"]:
        problem(f"C: the chip does not name the session user: {state['chipLabel']!r}")


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
    print("\nOK: signed-out stays usable, sign-in is optional and honest, the enforced world "
          "goes straight to the login view, and a valid session is left alone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
