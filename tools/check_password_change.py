#!/usr/bin/env python3
"""Prove the "Settings → My password" screen by CONTENT, in a real browser (Phase 3).

The screen this checks is the one place a NON-administrator can change a credential, and the
cheapest way to get it wrong is to make it impossible for the accounts it matters most for: a
Jellyfin account with NO password is a legitimate account (the household's own model), and a rule
that demanded a current password from it would lock it out of its own screen — the same class of
bug that once made those accounts unable to sign in.

So the checks are about BEHAVIOUR and about which request is sent, not about pixels:

  A  ?has_password=1  — the current password is required; a mismatch is refused; the two new values
                        and the current one reach the api as ONE post, with only those fields.
  B  ?has_password=0  — a password-less account CAN change its password with the field blank, and
                        the screen says why that is allowed.
  C  ?refuse=wrong    — a 401 is shown as "that current password is not correct", and the notice
                        says the OLD password still works (nobody should be left guessing).
  D  ?refuse=server   — a 502 (refused for another reason) must NOT be reported as a wrong
                        password: that would send the user hunting a password that was fine.

Run it against the vite dev server (which serves the harness):

    cd frontend && npx vite --port 5199 --strictPort &
    python3 tools/check_password_change.py
"""
from __future__ import annotations

import argparse
import json
import sys

from playwright.sync_api import Page, sync_playwright

PROBLEMS: list[str] = []


def problem(message: str) -> None:
    PROBLEMS.append(message)
    print(f"  FAIL: {message}")


def check(condition: bool, message: str) -> None:
    if not condition:
        problem(message)


def open_frame(page: Page, base: str, query: str, shots: str, name: str) -> dict:
    page.goto(f"{base}/harness/password-frame.html?{query}")
    page.wait_for_selector('[data-testid="password-view"]', timeout=10000)
    page.wait_for_timeout(400)  # the profiles read must land before the rails are judged
    state = page.evaluate("window.__probe()")
    if shots:
        page.screenshot(path=f"{shots}/password-{name}.png", full_page=True)
    return state


def posts(state: dict) -> list[dict]:
    return [c for c in state["calls"]
            if c["method"] == "POST" and c["url"] == "/api/auth/profile/password"]


def fill(page: Page, current: str, new: str, confirm: str) -> None:
    page.fill("#current-password", current)
    page.fill("#new-password", new)
    page.fill("#confirm-password", confirm)
    page.wait_for_timeout(120)


def scenario_a_current_required(page: Page, base: str, shots: str) -> None:
    print("A — an account WITH a password: the current one is required")
    state = open_frame(page, base, "has_password=1", shots, "with-password")
    check(state["submitDisabled"] is False or state["submitDisabled"] is not None,
          "A: the submit button should exist")

    # Blank everything: refused, with the reason, and NO request.
    fill(page, "", "new-pw", "new-pw")
    state = page.evaluate("window.__probe()")
    check(state["submitDisabled"] is True, "A: a blank current password must be refused")
    check("current password" in state["notice"].lower(), f"A: reason, got {state['notice']!r}")
    check(not posts(state), "A: nothing may be sent while the form is refused")

    # A mismatch: refused on the confirm field.
    fill(page, "old-pw", "new-pw", "new-pw-typo")
    state = page.evaluate("window.__probe()")
    check(state["submitDisabled"] is True, "A: a mismatch must be refused")
    check("match" in state["notice"].lower(), f"A: reason, got {state['notice']!r}")
    check(not posts(state), "A: a mismatch must send no request")

    # The good case: ONE post carrying exactly the three values the api expects.
    fill(page, "old-pw", "new-pw", "new-pw")
    state = page.evaluate("window.__probe()")
    check(state["submitDisabled"] is False, "A: a complete form must be submittable")
    page.click('button:has-text("Change password")')
    page.wait_for_timeout(600)
    state = page.evaluate("window.__probe()")
    sent = posts(state)
    check(len(sent) == 1, f"A: exactly one change request expected, got {len(sent)}")
    if sent:
        body = json.loads(sent[0]["body"] or "{}")
        check(body.get("current_password") == "old-pw",
              f"A: the current password should be sent, got {body.get('current_password')!r}")
        check(body.get("new_password") == "new-pw",
              f"A: the new password should be sent, got {body.get('new_password')!r}")
        check(sorted(body.keys()) == ["current_password", "new_password"],
              f"A: only those two fields, got {sorted(body.keys())}")
    check("changed" in state["done"].lower(), f"A: the screen should confirm, got {state['done']!r}")
    check(state["error"] == "", f"A: no error expected, got {state['error']!r}")

    if not PROBLEMS:
        print("  OK: required while the account has one, refused before sending, one clean post")


def scenario_b_passwordless(page: Page, base: str, shots: str) -> None:
    print("B — an account with NO password can still set one")
    state = open_frame(page, base, "has_password=0", shots, "no-password")
    check("no password" in state["body"].lower(),
          "B: the screen should say the account has none yet")

    fill(page, "", "first-pw", "first-pw")
    state = page.evaluate("window.__probe()")
    check(state["submitDisabled"] is False,
          "B: a blank current password must be allowed for a password-less account")

    page.click('button:has-text("Change password")')
    page.wait_for_timeout(600)
    state = page.evaluate("window.__probe()")
    sent = posts(state)
    check(len(sent) == 1, f"B: exactly one request expected, got {len(sent)}")
    if sent:
        body = json.loads(sent[0]["body"] or "{}")
        check(body.get("current_password") == "",
              f"B: the current password goes as an empty string, got {body.get('current_password')!r}")
    check("changed" in state["done"].lower(), f"B: should confirm, got {state['done']!r}")

    if not PROBLEMS:
        print("  OK: a password-less account is not blocked from its own screen")


def scenario_c_wrong_current(page: Page, base: str, shots: str) -> None:
    print("C — a wrong current password")
    open_frame(page, base, "has_password=1&refuse=wrong", shots, "wrong")
    fill(page, "typo", "new-pw", "new-pw")
    page.click('button:has-text("Change password")')
    page.wait_for_timeout(600)
    state = page.evaluate("window.__probe()")
    check("current password" in state["error"].lower(), f"C: got {state['error']!r}")
    check("typo" not in state["error"] and "new-pw" not in state["error"],
          "C: the message must never echo either password")
    check(state["done"] == "", "C: and it must not claim success")
    if not PROBLEMS:
        print("  OK: a 401 is reported as the current password being wrong, and says nothing else")


def scenario_d_server_refusal(page: Page, base: str, shots: str) -> None:
    print("D — the server refuses for another reason")
    open_frame(page, base, "has_password=1&refuse=server", shots, "refused")
    fill(page, "old-pw", "new-pw", "new-pw")
    page.click('button:has-text("Change password")')
    page.wait_for_timeout(600)
    state = page.evaluate("window.__probe()")
    check(state["error"] != "", "D: the refusal must be shown")
    check("not correct" not in state["error"],
          f"D: a 502 must NOT be reported as a wrong password, got {state['error']!r}")
    check("refused" in state["error"].lower(),
          f"D: when the server explains itself, show ITS words, got {state['error']!r}")

    # And when the server says nothing at all, the screen must still not leave the user guessing:
    # a refusal means nothing changed, and the one thing they need to know is that they are not
    # locked out. (The unit tests pin this wording; this proves it end to end.)
    page.goto("about:blank")
    open_frame(page, base, "has_password=1&refuse=silent", shots, "refused-silent")
    fill(page, "old-pw", "new-pw", "new-pw")
    page.click('button:has-text("Change password")')
    page.wait_for_timeout(600)
    state = page.evaluate("window.__probe()")
    check("old password still works" in state["error"].lower(),
          f"D: a silent refusal needs our own words, got {state['error']!r}")
    if not PROBLEMS:
        print("  OK: a refusal that is not a typo is not blamed on the user")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:5199")
    ap.add_argument("--shots", default="")
    args = ap.parse_args()

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        scenario_a_current_required(page, args.base, args.shots)
        page.goto("about:blank")
        scenario_b_passwordless(page, args.base, args.shots)
        page.goto("about:blank")
        scenario_c_wrong_current(page, args.base, args.shots)
        page.goto("about:blank")
        scenario_d_server_refusal(page, args.base, args.shots)

        if errors:
            problem(f"page errors: {errors}")
        browser.close()

    if PROBLEMS:
        print(f"\n{len(PROBLEMS)} problem(s)")
        return 1
    print("\nOK: my-password screen behaves (required when it exists, never blocked when it "
          "does not, and refusals are told apart)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
