#!/usr/bin/env python3
"""Prove the library SCAN control is offered to administrators and NOT to anybody else.

Phase E (his decision, 2026-09-13) put `require_admin_session` on `GET /api/library/scan` and
`POST /api/jobs/{name}/run`. That gate is strict **even while `RKM_AUTH_REQUIRED` is false** — so on
the running stack a member clicking "Scan Library" gets a 403, and the app's own rule is that it must
never OFFER what the server will refuse (`user profile`, and the way `Household` is hidden).

`mayScanLibrary` is a pure rule and is unit-tested (`features/auth/lib.test.ts`). What THIS proves is
the wiring: that the real `LibraryHomeView` (hero AND empty state) and the real `LibraryFolderView`
pass the rule through to the DOM. The repo has twice shipped a check that could not fail — a harness
that handed the UI an answer the server was incapable of producing, and a test that passed while
inspecting zero routes — so the scenarios below are chosen so that removing the wiring fails them:

  A  administrator, library has titles   -> the hero's scan control is PRESENT
  B  administrator, library is EMPTY      -> the empty state's scan button is PRESENT (the path where
                                             the button is the only call to action)
  C  member, library has titles           -> NO scan control, and no /api/library/scan call at all
  D  member, library is EMPTY             -> NO scan button; the honest line says who can scan
  E  member, folder view                  -> NO scan control (its own copy of the control)
  F  administrator CLICKS it              -> exactly one /api/library/scan call (the control is not
                                             merely decorative: hiding it must not be the fix)
  G  signed out (no session)              -> NO scan control: the route refuses that caller too

Run against the vite dev server:

    cd frontend && npx vite --port 5199 --strictPort &
    python3 tools/check_library_scan.py [--shots DIR]
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


def _wait_for(page: Page, expr: str, seconds: int, message: str) -> bool:
    """Wait for a condition, and record a CLEAN failure when it never arrives.

    ⚠ Raising `TimeoutError` here would abort the whole run on the first scenario and bury the
    reason under a traceback. It also happened for real: the falsification that removed the wiring
    also removed the `useCurrentProfile()` call, so the profiles gate never fired and the run died
    before it could say what was wrong (2026-09-13).
    """
    try:
        page.wait_for_function(expr, timeout=seconds * 1000)
        return True
    except Exception:
        check(False, message)
        return False


def open_frame(page: Page, base: str, query: str, shots: str, name: str) -> dict:
    """Load the frame and wait until the view's own first read has been ANSWERED.

    ⚠ Waiting on a fixed timeout would let an empty frame pass every scenario below (nothing found
    is also nothing wrongly offered), so readiness is the library read landing in the probe's own
    call log — and every scenario below ALSO asserts on real rendered content.
    """
    page.goto(f"{base}/harness/library-frame.html?{query}")
    # The view's OWN first read, whichever view the frame mounted: the home view reads
    # `/api/library/items`, the folder view reads `/api/library/folders/{id}/items`. Waiting on the
    # wrong path times out on the folder scenario.
    _wait_for(
        page,
        "() => (window.__probe().calls || []).some(c => c.url === '/api/library/items' || "
        "/^\\/api\\/library\\/folders\\/.+\\/items$/.test(c.url))",
        15,
        f"{name}: the view never made its own library read — the frame did not render, so every "
        "'the control is not offered' assertion below would be vacuous",
    )
    # ⚠ This one is a REAL assertion, not just readiness: the scan rule reads the profile's
    # `is_admin`, so if this query stops being asked, an ADMINISTRATOR is never offered the control
    # either. Requiring it means the "not offered" scenarios cannot pass by never asking.
    _wait_for(
        page,
        "() => (window.__probe().calls || []).some(c => c.url === '/api/auth/profiles')",
        15,
        f"{name}: the frame never asked /api/auth/profiles — the scan rule reads that answer, so "
        "without the query nobody (administrator included) can be offered the control",
    )
    page.wait_for_timeout(700)
    if shots:
        page.screenshot(path=f"{shots}/library-scan-{name}.png", full_page=True)
    return page.evaluate("window.__probe()")


def rendered(probe: dict, needle: str, where: str) -> None:
    """The view really rendered — otherwise 'no scan control' passes for the wrong reason."""
    check(needle in probe["body"],
          f"{where}: expected {needle!r} on the page. If the frame did not render, every "
          "'not offered' assertion below is vacuous — that is the failure this check is for.")


def scenario_a_administrator_hero(page: Page, base: str, shots: str) -> None:
    print("A — an administrator with titles: the hero offers the scan")
    probe = open_frame(page, base, "admin=1", shots, "admin-hero")
    rendered(probe, "The Matrix", "A")
    check(probe["hasScanControl"],
          "A: an administrator must be OFFERED the scan control on the home view")
    if not PROBLEMS:
        print("  OK: present for an administrator")


def scenario_b_administrator_empty(page: Page, base: str, shots: str) -> None:
    print("B — an administrator with an EMPTY library: the empty state offers the scan")
    probe = open_frame(page, base, "admin=1&empty=1", shots, "admin-empty")
    rendered(probe, "library is empty", "B")
    check(probe["hasScanControl"],
          "B: with nothing in the library the scan button is the ONLY action an administrator has; "
          "it must still be there")
    if not PROBLEMS:
        print("  OK: present, and it is the empty state's call to action")


def scenario_c_member_with_titles(page: Page, base: str, shots: str) -> None:
    print("C — a member with titles: no scan control, and no scan call")
    probe = open_frame(page, base, "admin=0", shots, "member-hero")
    rendered(probe, "The Matrix", "C")
    check(not probe["hasScanControl"],
          "C: a member must NOT be offered the scan control — the route answers 403 for them")
    check(probe["scanCalls"] == [],
          f"C: a member's page must not call /api/library/scan, got {probe['scanCalls']}")
    if not PROBLEMS:
        print("  OK: not offered, and never called")


def scenario_d_member_empty(page: Page, base: str, shots: str) -> None:
    print("D — a member with an EMPTY library: told who can scan instead of given a button")
    probe = open_frame(page, base, "admin=0&empty=1", shots, "member-empty")
    rendered(probe, "library is empty", "D")
    check(not probe["hasScanControl"], "D: a member must not be offered the scan button")
    check("administrator" in probe["body"],
          "D: with no button, a member must be told that scanning is an administrator action — "
          "silence would read as a broken screen")
    if not PROBLEMS:
        print("  OK: no button, and the reason is stated")


def scenario_e_member_folder_view(page: Page, base: str, shots: str) -> None:
    print("E — a member on a library FOLDER: no scan control there either")
    probe = open_frame(page, base, "admin=0&folder=1&empty=1", shots, "member-folder")
    rendered(probe, "Movies", "E")
    check(not probe["hasScanControl"],
          "E: the folder view carries its own copy of the control; it must be gated the same way")
    if not PROBLEMS:
        print("  OK: the second surface is gated too (a rule that drifted here would be invisible)")


def scenario_f_administrator_can_still_scan(page: Page, base: str, shots: str) -> None:
    print("F — an administrator CAN still scan: the gate must not lock the operator out")
    open_frame(page, base, "admin=1", shots, "admin-click")
    button = page.query_selector('button[aria-label="Scan Library"]') or page.query_selector(
        "button:has-text('Scan Library')")
    check(button is not None, "F: no scan control to click for an administrator")
    if button is None:
        return
    button.click()
    page.wait_for_timeout(700)
    probe = page.evaluate("window.__probe()")
    check(len(probe["scanCalls"]) == 1,
          f"F: clicking the control must fire exactly one /api/library/scan call, "
          f"got {probe['scanCalls']}")
    if not PROBLEMS:
        print("  OK: one call — the control works for the person it is meant for")


def scenario_g_signed_out(page: Page, base: str, shots: str) -> None:
    """No session at all — the OTHER refusal `require_admin_session` makes (401).

    A member (C–E) is the 403 case; this is the signed-out case, and it matters because the app is
    browsable signed out today (`RKM_AUTH_REQUIRED` is false), so a visitor with no cookie sees the
    same library screens — and must be offered nothing that will answer 401.
    """
    print("G — a signed-out visitor: the library renders, and still no scan control")
    probe = open_frame(page, base, "signedout=1", shots, "signed-out")
    rendered(probe, "The Matrix", "G")
    check(not probe["hasScanControl"],
          "G: a signed-out caller is refused by the route and must not be offered its control")
    check(probe["scanCalls"] == [],
          f"G: and must make no /api/library/scan call, got {probe['scanCalls']}")
    if not PROBLEMS:
        print("  OK: same answer as a member — the route refuses both")


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

        scenario_a_administrator_hero(page, args.base, args.shots)
        page.goto("about:blank")
        scenario_b_administrator_empty(page, args.base, args.shots)
        page.goto("about:blank")
        scenario_c_member_with_titles(page, args.base, args.shots)
        page.goto("about:blank")
        scenario_d_member_empty(page, args.base, args.shots)
        page.goto("about:blank")
        scenario_e_member_folder_view(page, args.base, args.shots)
        page.goto("about:blank")
        scenario_f_administrator_can_still_scan(page, args.base, args.shots)
        page.goto("about:blank")
        scenario_g_signed_out(page, args.base, args.shots)

        if errors:
            check(False, f"page errors: {errors}")
        browser.close()

    if PROBLEMS:
        print(f"\n{len(PROBLEMS)} problem(s)")
        return 1
    print("\nOK: the scan control is offered to administrators only, on every library surface, and "
          "it still works for them")
    return 0


if __name__ == "__main__":
    sys.exit(main())
