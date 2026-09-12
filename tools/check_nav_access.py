#!/usr/bin/env python3
"""Prove the account-management entry is offered to administrators and NOT to members.

His request (2026-09-12): "household path should not be available to non admin users, and also it
should be available on ui". Two surfaces render navigation — the desktop sidebar and the mobile
sheet — so they are separate code paths and both are checked here.

  A  administrator profile  -> Household in the sidebar AND in the mobile sheet, plus My password
  B  member profile         -> My password present, Household ABSENT from both surfaces
  C  member profile         -> the navigation fires no /api/admin/* call at all

The server refuses the household routes regardless (`require_admin_session`); this is about what the
app OFFERS, so the check is on rendered text and on the calls actually made.

Run against the vite dev server:

    cd frontend && npx vite --port 5199 --strictPort &
    python3 tools/check_nav_access.py
"""
from __future__ import annotations

import argparse
import sys

from playwright.sync_api import Page, sync_playwright

PROBLEMS: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        PROBLEMS.append(message)
        print(f"  FAIL: {message}")


def open_frame(page: Page, base: str, query: str, shots: str, name: str) -> dict:
    page.goto(f"{base}/harness/nav-frame.html?{query}")
    page.wait_for_selector('nav[aria-label="Primary"]', timeout=10000)
    page.wait_for_timeout(500)  # let the profiles answer land
    state = page.evaluate("window.__probe()")
    if shots:
        page.screenshot(path=f"{shots}/nav-{name}.png", full_page=True)
    return state


def open_sheet(page: Page) -> dict:
    """The mobile destinations live behind the More button."""
    page.click('[aria-label="More"]')
    page.wait_for_selector('[aria-label="More destinations"]', timeout=5000)
    page.wait_for_timeout(200)
    return page.evaluate("window.__probe()")


def scenario_a_administrator(page: Page, base: str, shots: str) -> None:
    print("A — an administrator profile sees the account management")
    state = open_frame(page, base, "admin=1", shots, "admin")
    check("Household" in state["sidebar"], f"A: sidebar should offer Household, got {state['sidebar']!r}")
    check("My password" in state["sidebar"], "A: sidebar should offer My password")
    state = open_sheet(page)
    check("Household" in state["sheet"],
          f"A: the MOBILE sheet must offer it too, got {state['sheet']!r}")
    check("My password" in state["sheet"], "A: the mobile sheet should offer My password")
    if not PROBLEMS:
        print("  OK: both surfaces offer Household and My password")


def scenario_b_member(page: Page, base: str, shots: str) -> None:
    print("B — a member profile is not offered the account management")
    state = open_frame(page, base, "admin=0", shots, "member")
    check("Household" not in state["sidebar"],
          f"B: sidebar must NOT offer Household, got {state['sidebar']!r}")
    check("My password" in state["sidebar"], "B: but My password is every profile's own screen")
    state = open_sheet(page)
    check("Household" not in state["sheet"],
          f"B: the mobile sheet must not offer it either, got {state['sheet']!r}")
    check("My password" in state["sheet"], "B: the mobile sheet should offer My password")
    if not PROBLEMS:
        print("  OK: neither surface offers Household to a member")


def scenario_c_no_admin_calls(page: Page, base: str, shots: str) -> None:
    print("C — and a member's navigation reaches no administrative route")
    open_frame(page, base, "admin=0", shots, "member-calls")
    open_sheet(page)
    calls = [c for c in page.evaluate("window.__probe()")["calls"] if "/api/admin/" in c["url"]]
    check(calls == [], f"C: the nav must not call an admin route, got {calls[:3]}")
    if not PROBLEMS:
        print("  OK: zero /api/admin/* calls from a member's navigation")


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

        scenario_a_administrator(page, args.base, args.shots)
        page.goto("about:blank")
        scenario_b_member(page, args.base, args.shots)
        page.goto("about:blank")
        scenario_c_no_admin_calls(page, args.base, args.shots)

        if errors:
            check(False, f"page errors: {errors}")
        browser.close()

    if PROBLEMS:
        print(f"\n{len(PROBLEMS)} problem(s)")
        return 1
    print("\nOK: Household is offered to administrators only, on both surfaces, and the mobile "
          "menu reaches it")
    return 0


if __name__ == "__main__":
    sys.exit(main())
