#!/usr/bin/env python3
"""Prove the account destinations are offered to administrators and NOT to members, on every surface.

His requests, in order:
  2026-09-12 — "household path should not be available to non admin users, and also it should be
                available on ui" (the desktop sidebar offered it to EVERYONE, and the mobile sheet
                offered neither Household nor My password);
  2026-09-13 — "you have removed the household from rkm(admin) as well … also we need tweaks in ui,
                'my password' option doesn't need to be sitting on the left side bar it can simply
                reside when user click its avatar … consolidate the ui elements".

So the check now covers BOTH halves of the consolidation:

  A  administrator -> the ACCOUNT MENU (opened from the header avatar AND from the sidebar footer)
                      offers My password and Household; the sidebar NAV no longer duplicates either
  B  member        -> both triggers offer My password but NOT Household
  C  member        -> the navigation fires no /api/admin/* call at all
  D  every surface -> the mobile sheet carries navigation only (no Household, no My password)

⚠ The regression this exists for: Household disappeared for the ADMINISTRATOR too, because
`/api/auth/profiles` sent `current` as a name-only row (is_admin always false). The harness stub now
mirrors the server's real answer, and the backend pins it
(`TestProfiles::test_the_current_profile_carries_the_SERVERS_own_answer`).

Run against the vite dev server:

    cd frontend && npx vite --port 5199 --strictPort &
    python3 tools/check_nav_access.py [--shots DIR]
"""
from __future__ import annotations

import argparse
import sys

from playwright.sync_api import Page, sync_playwright

PROBLEMS: list[str] = []

HEADER_TRIGGER = 'header [aria-haspopup="menu"]'
SIDEBAR_TRIGGER = 'aside [aria-haspopup="menu"]'


def check(condition: bool, message: str) -> None:
    if not condition:
        PROBLEMS.append(message)
        print(f"  FAIL: {message}")


def open_frame(page: Page, base: str, query: str, shots: str, name: str) -> None:
    """Load the frame and wait for the ACCOUNT surface that exists at every width.

    ⚠ Not `nav[aria-label="Primary"]` any more: that nav lives in the sidebar, which is
    `hidden md:flex`, so on the phone viewport it is legitimately invisible and the wait timed out
    the moment this frame started loading its stylesheet (2026-09-13). The header — and therefore
    the avatar — is on every breakpoint.
    """
    page.goto(f"{base}/harness/nav-frame.html?{query}")
    page.wait_for_selector("header", timeout=10000)
    page.wait_for_selector(HEADER_TRIGGER, timeout=10000)
    page.wait_for_timeout(600)  # let the profiles answer land
    if shots:
        page.screenshot(path=f"{shots}/nav-{name}.png", full_page=True)


def open_account_menu(page: Page, trigger: str) -> str:
    """Open the account menu from one trigger and return its text."""
    page.click(trigger)
    page.wait_for_selector('[role="menu"]', timeout=5000)
    page.wait_for_timeout(150)
    menu = page.evaluate("window.__probe()")["accountMenu"]
    page.keyboard.press("Escape")
    page.wait_for_timeout(150)
    return menu


def open_sheet(page: Page) -> dict:
    """The mobile destinations live behind the More button — a PHONE surface.

    ⚠ Until 2026-09-13 this frame loaded no stylesheet, so the mobile bar was 'visible' at every
    width and these clicks worked at 1280px. Styled (`md:hidden`, as on the real phone) the button
    is not visible on a desktop viewport at all, which is what the caller must use.
    """
    page.click('[aria-label="More"]')
    page.wait_for_selector('[aria-label="More destinations"]', timeout=5000)
    page.wait_for_timeout(200)
    state = page.evaluate("window.__probe()")
    page.keyboard.press("Escape")
    return state


def scenario_a_administrator(page: Page, base: str, shots: str) -> None:
    print("A — an administrator profile: the account menu offers the administration")
    open_frame(page, base, "admin=1", shots, "admin")
    triggers = page.evaluate("window.__probe()")["accountTriggers"]
    check(triggers["header"], "A: the header must offer the account menu (every breakpoint)")
    check(triggers["sidebar"], "A: the sidebar footer must offer it too (desktop convention)")

    header_menu = open_account_menu(page, HEADER_TRIGGER)
    check("My password" in header_menu,
          f"A: the account menu should offer My password, got {header_menu!r}")
    check("Household" in header_menu,
          "A: the account menu should offer Household to an administrator — THIS is the regression "
          f"he reported ('you have removed the household from rkm as well'), got {header_menu!r}")
    check("Sign out" in header_menu, "A: and Sign out belongs here, not in the header row")

    sidebar_menu = open_account_menu(page, SIDEBAR_TRIGGER)
    check("Household" in sidebar_menu and "My password" in sidebar_menu,
          f"A: both triggers must open the SAME menu, got {sidebar_menu!r}")

    nav = page.evaluate("window.__probe()")["sidebar"]
    check("My password" not in nav,
          f"A: the sidebar NAV must not duplicate My password any more, got {nav!r}")
    check("Household" not in nav,
          f"A: nor Household — they are account destinations now, got {nav!r}")
    if not PROBLEMS:
        print("  OK: one menu, offered from both triggers, and no duplicates in the sidebar")


def scenario_b_member(page: Page, base: str, shots: str) -> None:
    print("B — a member profile is not offered the account management")
    open_frame(page, base, "admin=0", shots, "member")
    for surface, trigger in (("header", HEADER_TRIGGER), ("sidebar", SIDEBAR_TRIGGER)):
        menu = open_account_menu(page, trigger)
        check("Household" not in menu,
              f"B: the {surface} account menu must NOT offer Household, got {menu!r}")
        check("My password" in menu,
              f"B: but My password is every profile's own screen, got {menu!r}")
    if not PROBLEMS:
        print("  OK: neither trigger offers Household to a member")


def scenario_c_no_admin_calls(page: Page, base: str, shots: str) -> None:
    print("C — and a member's navigation reaches no administrative route")
    open_frame(page, base, "admin=0", shots, "member-calls")
    open_sheet(page)
    calls = [c for c in page.evaluate("window.__probe()")["calls"] if "/api/admin/" in c["url"]]
    check(calls == [], f"C: the nav must not call an admin route, got {calls[:3]}")
    if not PROBLEMS:
        print("  OK: zero /api/admin/* calls from a member's navigation")


def scenario_d_sheet_is_navigation_only(page: Page, base: str, shots: str) -> None:
    print("D — the mobile sheet carries navigation only")
    open_frame(page, base, "admin=1", shots, "admin-sheet")
    sheet = open_sheet(page)["sheet"]
    check("Household" not in sheet,
          f"D: Household moved into the account menu, got {sheet!r}")
    check("My password" not in sheet,
          f"D: so did My password, got {sheet!r}")
    check(bool(sheet.strip()), "D: the sheet still has destinations")
    if not PROBLEMS:
        print("  OK: the mobile sheet is navigation only; both account screens are in the menu")


def scenario_e_phone_account_menu(page: Page, base: str, shots: str) -> None:
    """The phone's ONLY account surface is the header avatar (the sidebar is hidden below md).

    Its menu must also fit the viewport — the popup clamps to the screen, and a menu that overflows
    is a control a thumb cannot reach.
    """
    print("E — a phone reaches both account screens from the header avatar")
    open_frame(page, base, "admin=1", shots, "admin-phone")
    # Open it here rather than through the helper: that one closes the menu (Escape) before
    # returning, and this scenario needs the geometry WHILE it is open.
    page.click(HEADER_TRIGGER)
    page.wait_for_selector('[role="menu"]', timeout=5000)
    page.wait_for_timeout(200)
    menu = page.evaluate("window.__probe()")["accountMenu"]
    check("My password" in menu and "Household" in menu,
          f"E: the phone must reach both, got {menu!r}")
    box = page.evaluate(
        """() => {
          const m = [...document.querySelectorAll('[role="menu"]')]
            .find(x => !x.closest('nav[aria-label="Mobile"]'));
          if (!m) return null;
          const r = m.getBoundingClientRect();
          return { top: r.top, left: r.left, right: r.right, bottom: r.bottom,
                   w: innerWidth, h: innerHeight };
        }"""
    )
    check(box is not None, "E: no account menu was open to measure")
    if box:
        inside = (
            box["left"] >= 0
            and box["top"] >= 0
            and box["right"] <= box["w"]
            and box["bottom"] <= box["h"]
        )
        check(inside, f"E: the menu must fit the screen, got {box}")
    if not PROBLEMS:
        print("  OK: the avatar is the phone's account surface, and the menu fits")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:5199")
    ap.add_argument("--shots", default="")
    args = ap.parse_args()

    with sync_playwright() as p:
        browser = p.chromium.launch()
        # The desktop viewport for the surfaces a desktop has (sidebar + header), and a PHONE one
        # for the mobile bar: with the stylesheet loaded, each is hidden at the other's width.
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        phone = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        phone.on("pageerror", lambda e: errors.append(str(e)))

        scenario_a_administrator(page, args.base, args.shots)
        page.goto("about:blank")
        scenario_b_member(page, args.base, args.shots)
        phone.goto("about:blank")
        scenario_c_no_admin_calls(phone, args.base, args.shots)
        phone.goto("about:blank")
        scenario_d_sheet_is_navigation_only(phone, args.base, args.shots)
        phone.goto("about:blank")
        scenario_e_phone_account_menu(phone, args.base, args.shots)

        if errors:
            check(False, f"page errors: {errors}")
        browser.close()

    if PROBLEMS:
        print(f"\n{len(PROBLEMS)} problem(s)")
        return 1
    print("\nOK: the account menu offers Household to administrators only, from every trigger, and "
          "the nav no longer duplicates it")
    return 0


if __name__ == "__main__":
    sys.exit(main())
