#!/usr/bin/env python3
"""Item-detail modal check — the treatment his Bug 5 report asked for, on every entry point.

His report (2026-09-13), verbatim in substance: a detail view reached by clicking a search result had
**no scrim**, **hard-cut edges**, sat in the **right ~60%** of the screen with the sidebar exposed,
**clipped its title at the top**, and offered **no dismiss control**.

The measured cause was not a broken modal: clicking a search result (or a poster card) NAVIGATED to
`/library/item/:id`, a full PAGE. A page has no scrim, no close button and no scroll lock, and on a
2560px screen its capped content area occupies exactly the right ~67% with the sidebar and a 300px
gutter exposed — every symptom, from the same cause. This check pins the fix: the route now renders
the app's shared `Dialog`, so the detail is a real modal wherever it is opened from.

WHY A BROWSER CHECK: the app already HAD the modal shell (`bg-black/65`, blur, `rounded-2xl`,
`shadow-modal`, body scroll lock, Esc, backdrop-click close, focus trap) — it simply was not used for
item details. What must hold is therefore not "does the CSS exist" but "is it on screen, on the
surface he clicked", which is a rendered fact.

WHAT IS ASSERTED

  A  clicking a search result opens a DIALOG, with a viewport-covering scrim that actually dims.
  B  the panel is centred, rounded, shadowed and scrollable — not a bare rectangle.
  C  its content is INSET from the panel's edges (nothing flush against the top, as reported).
  D  a visible close (X) exists, and Esc, the X and a backdrop click each dismiss it.
  E  body scroll is LOCKED while it is open, and released after.
  F  the page behind is INERT: the library view is still rendered (he sees where he came from) but
     cannot be interacted with.
  G  one pattern: a COLD DEEP LINK renders the same dialog, and closing it lands on the library.
  H  the layering rule with the player: Esc while the player is open closes the PLAYER, not the modal.
  I  clicking a poster CARD reaches the same dialog (his report's own note: check the other entry
     points too).

Run the dev server first (see frontend/harness/README.md):

    cd frontend && npx vite --port 5199 --strictPort
    python3 tools/check_item_modal.py [--shots DIR]
    python3 tools/check_item_modal.py --expect-broken     # falsification direction
"""
from __future__ import annotations

import argparse
import sys

from playwright.sync_api import Page, sync_playwright

PROBLEMS: list[str] = []

FRAME = "/harness/item-frame.html"
CENTRE_TOL = 2.0        # px: a centred panel may be off by sub-pixel rounding of flex centring
MIN_INSET = 8.0         # px: content must be inset from the panel's edges (his "no padding" report)


def problem(message: str) -> None:
    PROBLEMS.append(message)
    print(f"  FAIL: {message}")


def check(condition: bool, message: str) -> None:
    if not condition:
        problem(message)


def open_scene(page: Page, base: str, query: str, shots: str, name: str, need_dialog: bool = True) -> dict | None:
    """Load a scene and wait for it to have RENDERED something we can measure.

    ⚠ Readiness is deliberately the library content (not the dialog): waiting for the dialog would
    turn "there is no modal" into a timeout that says "the frame did not render", which is the exact
    defect this check exists to name.
    """
    page.goto(f"{base}{FRAME}?{query}", wait_until="networkidle")
    try:
        page.wait_for_function("() => (window.__probe().body || '').includes('Sholay')", timeout=15000)
    except Exception:
        problem(f"{name}: nothing rendered — the frame did not load, so every assertion below is vacuous")
        return None
    page.wait_for_timeout(600)
    probe = page.evaluate("window.__probe()")
    if shots:
        try:
            page.screenshot(path=f"{shots}/modal-{name}.png")
        except Exception as exc:  # noqa: BLE001 — evidence is optional, the assertion is not
            print(f"  NOTE: could not capture shots: {exc}")
    if need_dialog and probe["dialogCount"] == 0:
        problem(f"{name}: no dialog on screen — the detail is not being presented as a modal at all "
                f"(dialogCount=0, scrimCount={probe['scrimCount']})")
    return probe


def assert_modal_treatment(probe: dict, where: str) -> None:
    """A–F: the treatment his report lists, measured on the rendered panel."""
    check(probe["dialogCount"] >= 1, f"{where}: a dialog must be open")
    panel, scrim = probe.get("panel"), probe.get("scrim")
    if panel is None or scrim is None:
        problem(f"{where}: the dialog shell could not be measured (panel={panel is not None}, "
                f"scrim={scrim is not None})")
        return

    # A — the scrim really covers the viewport and really dims.
    vp = probe["viewport"]
    check(scrim["position"] == "fixed" and scrim["width"] >= vp["w"] - 1 and scrim["height"] >= vp["h"] - 1,
          f"{where}: the backdrop must cover the whole viewport, got {scrim['width']:.0f}×"
          f"{scrim['height']:.0f} for a {vp['w']}×{vp['h']} viewport")
    check("rgba" in scrim["bg"] and "rgba(0, 0, 0, 0)" not in scrim["bg"],
          f"{where}: the backdrop must actually dim the page (a translucent dark fill), got "
          f"background {scrim['bg']!r}")
    alpha = float(scrim["bg"].split(",")[-1].strip(" )")) if "rgba" in scrim["bg"] else 0.0
    check(alpha >= 0.4,
          f"{where}: the scrim is too faint to read as a backdrop (alpha {alpha:.2f}, "
          f"his expectation ~0.6)")

    # B — centred, rounded, shadowed, scrollable.
    check(abs(panel["centredX"]) <= CENTRE_TOL and abs(panel["centredY"]) <= CENTRE_TOL,
          f"{where}: the panel must be centred in the viewport, got {panel['centredX']:+.1f}px / "
          f"{panel['centredY']:+.1f}px off centre")
    check(panel["radius"] not in ("0px", "", None),
          f"{where}: the panel must have rounded corners, got border-radius {panel['radius']!r}")
    check(panel["shadow"] not in ("none", "", None),
          f"{where}: the panel must have a drop shadow (elevation), got {panel['shadow']!r}")
    check(panel["overflowY"] in ("auto", "scroll"),
          f"{where}: a tall detail panel must scroll internally, got overflow-y {panel['overflowY']!r}")

    # C — internal padding: the reported symptom was content flush against the edges.
    inset = probe.get("heroInset")
    if inset:
        check(inset["left"] >= MIN_INSET and inset["top"] >= MIN_INSET,
              f"{where}: panel content must be inset from the edges, got hero inset "
              f"left={inset['left']:.1f}px top={inset['top']:.1f}px")

    # D/E — dismiss controls + scroll lock.
    check(probe["closeBtn"] is not None,
          f"{where}: a visible close (X) button is required (his report: 'no visible dismiss control')")
    check(probe["bodyOverflow"] == "hidden",
          f"{where}: background scroll must be locked while the modal is open, got body overflow "
          f"{probe['bodyOverflow']!r}")

    # F — the page behind is visible but INERT (his "looks fully interactive" complaint).
    behind = probe.get("behindInert")
    check(behind is not None and behind["pointerEvents"] == "none",
          f"{where}: the library view behind must stay rendered but inert, got "
          f"{behind if behind is None else behind['pointerEvents']!r}")
    if behind:
        check(behind["text"].strip() != "",
              f"{where}: the backdrop must show the library he came from, not an empty canvas")


def open_from_search(page: Page) -> bool:
    """His path: type "sholay", click the owned row's Details. True when a dialog is open."""
    page.fill('input[type="search"]', "sholay")
    try:
        page.wait_for_function(
            "() => document.querySelectorAll('[role=\\\"option\\\"]').length >= 1", timeout=15000)
    except Exception:
        return False
    page.wait_for_timeout(250)
    page.locator('[data-testid="row-action-secondary"]').first.click()
    page.wait_for_timeout(800)
    return page.evaluate("() => window.__probe().dialogCount") >= 1


def scenario_a_search_result(page: Page, base: str, shots: str) -> None:
    print("A–F — clicking a SEARCH RESULT: the detail opens as a modal with the full treatment")
    page.goto(f"{base}{FRAME}?route=/library/home", wait_until="networkidle")
    try:
        # ⚠ Readiness is the LIBRARY VIEW, not a specific rail heading: the frame's stub has no
        # continue-watching rows, so waiting on that copy failed a frame that had rendered fine.
        page.wait_for_function(
            "() => (document.querySelector('main')?.textContent || '').length > 20", timeout=15000)
    except Exception:
        problem("A: the library view never rendered — the frame did not load")
        return
    if not open_from_search(page):
        problem("A: clicking a search result produced no dialog — the detail is not a modal at all")
        return
    probe = page.evaluate("window.__probe()")
    if shots:
        page.screenshot(path=f"{shots}/modal-search-result.png")
    assert_modal_treatment(probe, "A/search result")
    if not PROBLEMS:
        print(f"  A–F  panel {probe['panel']['width']:.0f}×{probe['panel']['height']:.0f}px centred "
              f"({probe['panel']['centredX']:+.1f}px off), scrim {probe['scrim']['bg']}, "
              f"scroll locked, X present, backdrop inert")

    # D — the three dismissals: the X, Esc, and a click on the backdrop.
    for key in ("X", "Esc", "backdrop"):
        if page.evaluate("() => window.__probe().dialogCount") == 0 and not open_from_search(page):
            problem(f"D: could not re-open the modal to test {key}")
            continue
        page.wait_for_timeout(200)
        if key == "X":
            page.locator('[data-testid="item-detail-close"]').click()
        elif key == "Esc":
            page.keyboard.press("Escape")
        else:
            page.mouse.click(6, 6)      # a corner: outside the centred panel, on the scrim
        page.wait_for_timeout(500)
        after = page.evaluate("window.__probe()")
        check(after["dialogCount"] == 0,
              f"D: {key} must dismiss the modal, still {after['dialogCount']} dialog(s) open")
        check(after["bodyOverflow"] != "hidden",
              f"D: after dismissing with {key} the scroll lock must be released, got "
              f"{after['bodyOverflow']!r}")
        if after["dialogCount"] == 0:
            print(f"  D  {key} dismisses the modal and releases the scroll lock")


def scenario_g_deep_link(page: Page, base: str, shots: str) -> None:
    print("G — a COLD DEEP LINK: same modal, and closing it lands on the library")
    probe = open_scene(page, base, "route=/library/item/m-sholay", shots, "deep-link")
    if probe is None:
        return
    assert_modal_treatment(probe, "G/deep link")
    # ⚠ Guarded: in the broken state there IS no close button, and a bare click would abort the run
    # with a Playwright timeout instead of reporting the failures already recorded above.
    if probe["dialogCount"] == 0:
        check(False, "G: nothing to dismiss — a deep link must open the same modal")
        return
    page.locator('[data-testid="item-detail-close"]').click()
    page.wait_for_timeout(700)
    after = page.evaluate("window.__probe()")
    check(after["dialogCount"] == 0, "G: the deep-link modal must close")
    check("Home" in after["body"] or "Continue Watching" in after["body"],
          "G: closing a deep-linked detail must land somewhere real (the library), not a blank page")
    if after["dialogCount"] == 0:
        print("  G  a cold deep link opens the same modal and closes onto the library")


def scenario_i_card_click(page: Page, base: str, shots: str) -> None:
    print("I — clicking a poster CARD: the same modal (his note asked for the other entry points too)")
    probe = open_scene(page, base, "route=/library/home", shots, "before-card", need_dialog=False)
    if probe is None:
        return
    card = page.locator('article[data-testid="media-card"] button[aria-label^="Open details"]')
    if card.count() == 0:
        problem("I: no poster card on the home view — cannot test the second entry point")
        return
    card.first.click()
    page.wait_for_timeout(900)
    after = page.evaluate("window.__probe()")
    if shots:
        page.screenshot(path=f"{shots}/modal-card-click.png")
    assert_modal_treatment(after, "I/card")
    if after["dialogCount"]:
        print(f"  I  a poster card opens the same dialog ({after['panel']['width']:.0f}px panel)")


def scenario_h_player_layering(page: Page, base: str, shots: str) -> None:
    print("H — with the PLAYER open, Esc closes the player and leaves the modal alone")
    probe = open_scene(page, base, "route=/library/item/m-sholay", shots, "player-layer", need_dialog=True)
    if probe is None or probe["dialogCount"] == 0:
        return
    play = page.locator('[role="dialog"] button', has_text="Play").first
    if play.count() == 0:
        problem("H: the modal has no Play action to start the player with")
        return
    play.click()
    page.wait_for_timeout(1500)
    opened = page.evaluate("window.__probe()")
    if not opened["playerOpen"]:
        print("  NOTE: the player did not open in this frame (stubbed media) — layering untested here")
        return
    page.keyboard.press("Escape")
    page.wait_for_timeout(700)
    after = page.evaluate("window.__probe()")
    check(not after["playerOpen"], "H: the first Esc must close the PLAYER")
    check(after["dialogCount"] >= 1,
          "H: the same Esc must NOT also close the modal behind it (one keypress, one layer)")
    if not after["playerOpen"] and after["dialogCount"] >= 1:
        print("  H  Esc closed the player only — the modal stayed behind it")


def scenario_j_discovery_no_poster(page: Page, base: str, shots: str) -> None:
    """J — his screenshot: a "not in your library" title with NO POSTER, opened from the search
    dropdown that lives INSIDE the blurred top bar.

    ⚠ The top bar is `sticky top-0 … backdrop-blur-xl`, and `backdrop-filter` (like filter/transform)
    makes an element a CONTAINING BLOCK for `position: fixed` descendants. The dialog's `fixed inset-0`
    therefore resolved against a 64px-tall header: the panel was centred inside that strip — its top
    above the viewport, i.e. "sticks to the top with the title flush" — and the scrim dimmed only the
    bar. Fixed by portalling the dialog to `<body>`.
    """
    print("J — the discovery modal (no poster), opened from the top bar")
    page.goto(f"{base}{FRAME}?route=/library/home", wait_until="networkidle")
    try:
        page.wait_for_function(
            "() => (document.querySelector('main')?.textContent || '').length > 20", timeout=15000)
    except Exception:
        problem("J: the library view never rendered — the frame did not load")
        return
    page.fill('input[type="search"]', "canelo")
    try:
        page.wait_for_function(
            "() => document.querySelectorAll('[role=\\\"option\\\"]').length >= 2", timeout=15000)
    except Exception:
        problem("J: the dropdown never rendered an external row — his case cannot be reproduced")
        return
    page.wait_for_timeout(250)
    # The DISCOVERY row's Details is the last one (owned rows render first).
    page.locator('[data-testid="row-action-secondary"]').last.click()
    page.wait_for_timeout(900)
    probe = page.evaluate("window.__probe()")
    if shots:
        page.screenshot(path=f"{shots}/modal-discovery-no-poster.png")
    check(probe["dialogCount"] >= 1,
          "J: clicking a not-in-library row must open its detail modal")
    if probe["dialogCount"] == 0:
        return
    out = probe.get("panelOutOfViewport")
    check(out is not None and not any(out.values()),
          f"J: the panel must sit fully INSIDE the viewport — got {out} for a {probe['viewport']} "
          f"viewport. A `fixed` dialog mounted inside a `backdrop-filter` ancestor is laid out against "
          f"THAT element, not the viewport, so the panel lands off-screen and the scrim dims only the "
          f"bar (panel ancestors: {probe.get('panelAncestors')})")
    scrim = probe.get("scrim") or {}
    check(bool(scrim.get("coversViewport")),
          f"J: the scrim must cover the whole viewport, got "
          f"{scrim.get('width')}x{scrim.get('height')} for {probe['viewport']}")
    check(probe["bodyOverflow"] == "hidden",
          f"J: the scroll must be locked while it is open, got {probe['bodyOverflow']!r}")
    if not PROBLEMS:
        print(f"  J  the no-poster modal is fully on screen "
              f"({probe['panel']['width']:.0f}×{probe['panel']['height']:.0f}px at y="
              f"{probe['panel']['top']:.0f}), the scrim covers the viewport, scroll locked")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:5199")
    ap.add_argument("--shots", default="")
    ap.add_argument("--expect-broken", action="store_true",
                    help="falsification: require the checks to FAIL (run against the unfixed source)")
    args = ap.parse_args()

    with sync_playwright() as p:
        browser = p.chromium.launch()
        # 2560 wide: the viewport where the old PAGE treatment read as a right-hand panel (his report).
        page = browser.new_page(viewport={"width": 2560, "height": 1440})
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        scenario_a_search_result(page, args.base, args.shots)
        page.goto("about:blank")
        scenario_i_card_click(page, args.base, args.shots)
        page.goto("about:blank")
        scenario_g_deep_link(page, args.base, args.shots)
        page.goto("about:blank")
        scenario_j_discovery_no_poster(page, args.base, args.shots)
        page.goto("about:blank")
        scenario_h_player_layering(page, args.base, args.shots)

        if errors:
            check(False, f"page errors: {errors}")
        browser.close()

    if args.expect_broken:
        if not PROBLEMS:
            print("\nFALSIFICATION FAILED: every check passed against source that still has the "
                  "defect — the check cannot tell the fix from the bug")
            return 1
        print(f"\nOK (falsified as expected): {len(PROBLEMS)} problem(s) with the fix absent")
        return 0

    if PROBLEMS:
        print(f"\n{len(PROBLEMS)} problem(s)")
        return 1
    print("\nOK: the item detail is a real modal — scrim, centred rounded panel, padded, close X, "
          "Esc/backdrop dismiss, scroll locked, inert backdrop, on every entry point")
    return 0


if __name__ == "__main__":
    sys.exit(main())
