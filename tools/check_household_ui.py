#!/usr/bin/env python3
"""Household screen check (AUTH_MULTIUSER_PLAN Phase 1b) — a real browser, real screen.

Proves what the screen RENDERS and what it POSTS, against the real components over a stubbed
api (see `frontend/harness/household-frame.tsx`). Three scenarios:

  A  ?admin=1  an administrator's world — the household lists, access resolves to library
               NAMES, "No password" is visible, the rails disable Remove where the server
               would refuse, and the typed name gates the final button.
  B  ?admin=0  a non-administrator session — the refusal is stated plainly, and NOTHING is
               offered that would fail.
  C  ?admin=1  adding a member — a blank password and ONLY the ticked folders reach the API.

Run the dev server first (see frontend/harness/README.md):
    cd frontend && npx vite --port 5199 --strictPort
    python3 tools/check_household_ui.py            # optionally --shots /tmp/shots
"""
from __future__ import annotations

import argparse
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
    page.goto(f"{base}/harness/household-frame.html?{query}", wait_until="networkidle")
    page.wait_for_timeout(600)
    if shots:
        page.screenshot(path=f"{shots}/{name}.png", full_page=True)
    return page.evaluate("window.__probe()")


def scenario_a_admin(page: Page, base: str, shots: str) -> None:
    print("A — an administrator's world")
    state = open_frame(page, base, "admin=1", shots, "household-admin")

    names = [row["name"] for row in state["rows"]]
    check(names == ["admin", "Guest"], f"A: the household should list admin and Guest, got {names}")

    admin_row = next((r for r in state["rows"] if r["name"] == "admin"), {"text": ""})
    guest_row = next((r for r in state["rows"] if r["name"] == "Guest"), {"text": ""})

    check("Every library" in admin_row["text"], "A: the admin should read 'Sees: Every library'")
    check("Movies" in guest_row["text"], "A: the guest's grant should resolve to the NAME 'Movies'")
    check("unknown" not in guest_row["text"].lower(),
          "A: a resolvable grant must not be flagged unknown")
    check("No password" in guest_row["text"], "A: a password-less member should say so")
    check("Never signed in" in guest_row["text"], "A: an account that never signed in should say so")

    # The rails: your own account cannot be removed, and the reason is on screen.
    check(admin_row["removeDisabled"] is True,
          "A: Remove must be disabled for the account you are signed in as")
    check("signed in as" in admin_row["text"],
          "A: the screen must say WHY Remove is disabled for your own account")
    check(guest_row["removeDisabled"] is False,
          "A: Remove must be offered for an ordinary member")

    # Typed-name confirmation gates the final button.
    page.click('[data-testid="member-Guest"] button:has-text("Remove")')
    page.wait_for_timeout(200)
    armed = page.evaluate("window.__probe()")
    check(armed["confirmEnabled"] is False,
          "A: the confirm button must be disabled before the name is typed")
    page.fill('[data-testid="member-Guest"] #confirm-name', "gues")
    page.wait_for_timeout(150)
    check(page.evaluate("window.__probe()")["confirmEnabled"] is False,
          "A: a close-but-wrong name must not arm the confirm button")
    page.fill('[data-testid="member-Guest"] #confirm-name', "Guest")
    page.wait_for_timeout(150)
    check(page.evaluate("window.__probe()")["confirmEnabled"] is True,
          "A: typing the exact name must arm the confirm button")
    if shots:
        page.screenshot(path=f"{shots}/household-remove-armed.png", full_page=True)

    if not PROBLEMS:
        print("  OK: the household lists, access resolves to names, and the rails hold")


def scenario_b_non_admin(page: Page, base: str, shots: str) -> None:
    print("B — a non-administrator")
    state = open_frame(page, base, "admin=0", shots, "household-refused")

    check("administrator" in state["refusal"].lower(),
          f"B: the refusal should name the requirement, got {state['refusal']!r}")
    check(state["rows"] == [], "B: no accounts should be listed to a non-administrator")
    check(state["addForm"] is False, "B: no add form should be offered to a non-administrator")
    check("Loading" not in state["body"], "B: the screen must not sit on 'Loading the household…'")

    posts = [c for c in state["calls"] if c["method"] != "GET"]
    check(posts == [], f"B: a non-administrator must trigger no write, got {posts}")

    if not PROBLEMS:
        print("  OK: the refusal is stated plainly and nothing is offered")


def scenario_c_add_member(page: Page, base: str, shots: str) -> None:
    print("C — adding a member with no password and one library")
    open_frame(page, base, "admin=1", shots, "household-add")
    page.click('button:has-text("Add member")')
    page.wait_for_selector('[data-testid="add-member-form"]', timeout=5000)

    # The default is EVERYTHING (the admin's own access) — untick one to prove the choice sticks.
    check(page.is_checked('label:has-text("Movies") input[type=checkbox]'),
          "C: every library should be ticked by default")
    page.uncheck('label:has-text("TV Shows") input[type=checkbox]')
    page.fill("#member-name", "Priya")
    # Password deliberately left blank — the user's decision (a member may have none).
    page.click('button:has-text("Create member")')
    page.wait_for_timeout(700)

    state = page.evaluate("window.__probe()")
    creates = [c for c in state["calls"] if c["url"] == "/api/admin/users" and c["method"] == "POST"]
    check(len(creates) == 1, f"C: exactly one create request expected, got {len(creates)}")
    if creates:
        import json

        body = json.loads(creates[0]["body"] or "{}")
        check(body.get("name") == "Priya", f"C: name should be Priya, got {body.get('name')!r}")
        check(body.get("password") == "", f"C: the password must be blank, got {body.get('password')!r}")
        check(body.get("library_ids") == ["f1"],
              f"C: only the ticked library should be sent, got {body.get('library_ids')!r}")

    names = [row["name"] for row in state["rows"]]
    check("Priya" in names, f"C: the new member should appear after refresh, got {names}")
    check(state["addForm"] is False, "C: the form should close once the member exists")
    if shots:
        page.screenshot(path=f"{shots}/household-added.png", full_page=True)

    if not PROBLEMS:
        print("  OK: a blank password and only the ticked folders reached the API")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:5199")
    ap.add_argument("--shots", default="")
    args = ap.parse_args()

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        scenario_a_admin(page, args.base, args.shots)
        page.goto("about:blank")
        scenario_b_non_admin(page, args.base, args.shots)
        page.goto("about:blank")
        scenario_c_add_member(page, args.base, args.shots)

        if errors:
            problem(f"page errors: {errors}")
        browser.close()

    if PROBLEMS:
        print(f"\n{len(PROBLEMS)} problem(s)")
        return 1
    print("\nOK: household screen behaves (admin, non-admin, add member)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
