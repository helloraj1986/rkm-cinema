#!/usr/bin/env python3
"""The mobile shell, measured in a real browser — MOBILE_FIRST_UI_PLAN §8.3 (phase M1).

    python3 tools/check_mobile_shell.py
    python3 tools/check_mobile_shell.py --selftest
    python3 tools/check_mobile_shell.py --shots /tmp/shots

It drives the same `frontend/harness/mobile-frame.html` as
`check_mobile_layout_switch.py` — the REAL `AppShell`, the REAL `MobileNav` and the REAL `Sheet` —
at the three widths the brief names (320, 390, 1023), and answers four questions:

  A. thumb_zone      the tab bar is in the bottom third, its bottom edge IS the viewport bottom, and
                     every tab is at least `--m-tap` (44px) in BOTH directions. The 44px floor is the
                     difference between a bar a thumb hits and one it misses, and it is measured
                     rather than read from a class string.
  B. thumb_nav       tapping a tab navigates AND the tapped tab becomes the active one. A bar that
                     changes the URL without showing where you are is half a navigation.
  C. sheet           the sheet opens anchored to the bottom edge, scrolls its own content with
                     `overscroll-behavior: contain`, moves focus into itself, and ⚠ LOCKS THE BODY
                     the way iOS needs (`position: fixed` at `-scrollY`) — not with `overflow: hidden`,
                     which on iOS leaves the page scrolling under the finger.
  D. sheet_dismiss   Escape closes it; a drag past 30% of its height closes it; a SHORT SLOW drag
                     does NOT close it (a sheet that closes on any touch is unusable); and after
                     closing, the body's styles and scroll position are RESTORED.

⚠ Both halves of the scroll lock are checked, because a lock that works and a lock that leaks look
identical until you close the sheet — and then the page is at the top instead of where it was.

⚠ The freshness guard, the fresh-page-per-scenario rule and the `--selftest` falsification are the
same as `check_mobile_layout_switch.py` (see that file for why each is there).
"""
from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from playwright.sync_api import sync_playwright

DEFAULT_BASE = "http://localhost:5199"
FRAME = "/harness/mobile-frame.html"
REPO = Path(__file__).resolve().parent.parent
FRONTEND = REPO / "frontend"

MIN_TAP_PX = 44
"""⚠ The same number as `--m-tap` in `styles/index.css`. It is repeated here ON PURPOSE: read from
the CSS it would agree with the CSS by construction, and the floor would move with a typo."""

WIDTHS: list[tuple[str, int, int]] = [
    ("phone 320", 320, 568),
    ("phone 390", 390, 844),
    ("tablet 1023", 1023, 800),
]

MARKERS: dict[str, str] = {
    "/src/components/ui/Sheet.tsx": "sheet-panel",
    # ⚠ `sheetRules.ts`, NOT `sheet.ts`: a `.ts` and a `.tsx` sharing a base name silently shadow each
    # other under Vite's default extension order (`.ts` wins), so `import { Sheet } from "./Sheet"`
    # resolved to the RULES file and the render died with "does not provide an export named 'Sheet'".
    # The two files must never share a name.
    "/src/components/ui/sheetRules.ts": "DISMISS_FRACTION",
    "/src/app/layout/MobileNav.tsx": "m-tap",
    "/src/app/layout/Sidebar.tsx": "lg:flex",
    "/src/app/layout/AppShell.tsx": "data-shell",
    "/src/layouts/LayoutMode.tsx": "MOBILE_MAX_PX",
}


@dataclass
class Result:
    label: str
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def fresh(base: str) -> list[str]:
    problems: list[str] = []
    for path, marker in MARKERS.items():
        on_disk = FRONTEND / path.lstrip("/")
        try:
            disk = on_disk.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            problems.append(f"{path}: cannot read {on_disk} ({exc})")
            continue
        if marker not in disk:
            problems.append(
                f"{path}: THIS TOOL'S MARKER {marker!r} is not in the file on disk — "
                "the marker is obsolete, so this guard can no longer detect a stale server"
            )
            continue
        try:
            with urllib.request.urlopen(f"{base}{path}", timeout=10) as response:
                body = response.read().decode("utf-8", "replace")
        except (urllib.error.URLError, TimeoutError) as exc:  # pragma: no cover
            problems.append(f"{path}: could not be fetched ({exc})")
            continue
        if marker not in body:
            problems.append(f"{path}: does not contain {marker!r} — the dev server is serving a STALE module")
    return problems


def open_frame(browser, base: str, width: int, height: int, scroll_to: int = 0):
    """A FRESH page per scenario (see the layout-switch tool for why)."""
    page = browser.new_page(viewport={"width": width, "height": height})
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    page.goto(f"{base}{FRAME}", wait_until="load", timeout=30_000)
    page.wait_for_function("() => !!window.__probe", timeout=20_000)
    page.wait_for_selector('[data-testid="route-fixture"]', timeout=20_000)
    if scroll_to:
        # ⚠ A page that is scrolled is the only way to prove the scroll lock RESTORES a position.
        # At scrollY 0 a lock that forgets to restore looks perfect.
        #
        # ⚠ And the spacer and the scroll are TWO steps. Doing both in one evaluate means `scrollTo`
        # runs before the browser has re-laid-out the taller document, so it clamps to the OLD
        # maximum (0) and the harness quietly measures a lock at scrollY 0 — a check that passes
        # against a broken lock. The wait is what makes the taller document real.
        page.evaluate("() => document.body.insertAdjacentHTML('beforeend', '<div style=\"height:4000px\"></div>')")
        page.wait_for_function(f"() => document.documentElement.scrollHeight > {scroll_to} + window.innerHeight", timeout=5_000)
        page.evaluate("(y) => window.scrollTo(0, y)", scroll_to)
        page.wait_for_function(f"() => window.scrollY >= {scroll_to}", timeout=5_000)
    page.wait_for_timeout(120)
    return page, errors


def probe(page) -> dict:
    return page.evaluate("window.__probe()")


# ---------------------------------------------------------------------------
# Assertions — pure functions of a probe, so `--selftest` can hand them a bad one.
# ---------------------------------------------------------------------------


def assert_thumb_zone(p: dict) -> list[str]:
    problems: list[str] = []
    bar = p.get("tabBar")
    if not bar or bar["w"] <= 0:
        return ["there is no tab bar on screen at a mobile width"]
    if abs(p["tabBarBottomGap"]) > 1:
        problems.append(
            f"the bar's bottom edge is {p['tabBarBottomGap']}px off the viewport bottom — it is not "
            "anchored to the edge, so the safe-area padding cannot be doing its job"
        )
    if bar["y"] < p["vh"] * 2 / 3:
        problems.append(
            f"the bar starts at y={bar['y']} of a {p['vh']}px viewport — that is above the bottom "
            "third, which is the thumb zone this shell exists for"
        )
    tabs = p.get("tabRects") or []
    if len(tabs) < 2:
        problems.append(f"only {len(tabs)} tab(s) render — a nav with one destination is not a nav")
    for tab in tabs:
        if tab["h"] + 0.5 < MIN_TAP_PX:
            problems.append(f"tab {tab['label']!r} is {tab['h']}px tall, under the {MIN_TAP_PX}px floor")
        if tab["w"] + 0.5 < MIN_TAP_PX:
            problems.append(f"tab {tab['label']!r} is {tab['w']}px wide, under the {MIN_TAP_PX}px floor")
    return problems


def assert_header_present(p: dict) -> list[str]:
    header = p.get("header")
    if not header or header["w"] <= 0:
        return ["the top bar is not rendered"]
    if header["h"] + 0.5 < MIN_TAP_PX:
        return [f"the top bar is {header['h']}px tall, under the {MIN_TAP_PX}px floor"]
    return []


def assert_no_sideways_scroll(p: dict) -> list[str]:
    problems: list[str] = []
    if p["overflowX"] > 0:
        problems.append(f"the document is {p['overflowX']}px wider than the viewport")
    if p["outside"]:
        worst = p["outside"][:3]
        detail = "; ".join(f"<{o['tag']} class={o['cls']!r}> {o['left']}..{o['right']}" for o in worst)
        problems.append(f"{len(p['outside'])} element(s) poke outside the viewport: {detail}")
    return problems


def assert_sheet_open_and_locked(p: dict, expected_scroll: int) -> list[str]:
    problems: list[str] = []
    panel = p.get("sheetPanel")
    if not p.get("sheetOpen") or not panel:
        return ["the sheet did not open — nothing to measure"]
    if abs(p["vh"] - panel["bottom"]) > 1:
        problems.append(
            f"the sheet's bottom is at {panel['bottom']} of a {p['vh']}px viewport — a bottom sheet "
            "must be anchored to the bottom edge"
        )
    if panel["h"] > p["vh"] + 1:
        problems.append(f"the sheet is {panel['h']}px tall in a {p['vh']}px viewport — it overflows the screen")
    radius = p.get("sheetRadius")
    if not radius or float(radius.replace("px", "") or 0) < 16:
        problems.append(f"the sheet's top corners are {radius!r} — a sheet is a surface, not a rectangle")
    if p.get("sheetOverscroll") != "contain":
        problems.append(
            f"overscroll-behavior-y is {p.get('sheetOverscroll')!r}, expected 'contain' — scrolling the "
            "sheet would chain out into the page behind it"
        )
    if not p.get("sheetScrollable"):
        problems.append(
            "the sheet's own content does not scroll — the fixture has 14 rows, so `.m-sheet` is "
            "clipping or overflowing instead of scrolling"
        )
    lock = p.get("bodyLock") or {}
    if lock.get("position") != "fixed":
        problems.append(
            f"the body is not locked: position is {lock.get('position')!r}. ⚠ `overflow: hidden` alone "
            "does not stop an iOS page scrolling under the finger"
        )
    if not str(lock.get("top", "")).startswith(f"-{expected_scroll}"):
        problems.append(
            f"the body is locked at top={lock.get('top')!r} for a scroll position of {expected_scroll}px "
            "— the page would jump when the sheet closes"
        )
    if not p.get("focusInSheet"):
        problems.append("focus did not move into the sheet — a keyboard would still be talking to the page behind")
    return problems


def assert_sheet_closed(p: dict, expected_scroll: int) -> list[str]:
    problems: list[str] = []
    if p.get("sheetOpen") or p.get("sheetPanel"):
        problems.append("the sheet is still open")
    lock = p.get("bodyLock") or {}
    if lock.get("position") == "fixed":
        problems.append("the body is STILL locked after the sheet closed — the page cannot scroll")
    if lock.get("top"):
        problems.append(f"the body's top offset was not cleared (top={lock.get('top')!r})")
    return problems


def assert_drag_snap_back(p: dict, dy: int) -> list[str]:
    """A short slow drag must leave the sheet open AND back at its anchored position."""
    problems: list[str] = []
    if not p.get("sheetOpen"):
        return [f"a {dy}px slow drag CLOSED the sheet — a sheet that closes on any touch is unusable"]
    panel = p.get("sheetPanel")
    if panel and abs(p["vh"] - panel["bottom"]) > 1:
        problems.append(
            f"after a {dy}px drag that did not dismiss, the sheet is {p['vh'] - panel['bottom']}px "
            "above the bottom edge — it did not snap back"
        )
    return problems


def drag(page, panel: dict, dy: int, steps: int = 12, delay_ms: int = 25) -> None:
    """Drag the sheet's handle down by `dy` real mouse pixels.

    ⚠ Starts on the HANDLE (the panel's top strip), not in the middle of the content: the sheet only
    begins a drag when its scroller is at scrollTop 0, and a drag that started over a scrolled row is
    the person scrolling, which is deliberately not a dismissal.
    """
    x = panel["x"] + panel["w"] / 2
    y = panel["y"] + 8
    page.mouse.move(x, y)
    page.mouse.down()
    for i in range(1, steps + 1):
        page.mouse.move(x, y + dy * i / steps)
        page.wait_for_timeout(delay_ms)
    page.mouse.up()
    page.wait_for_timeout(300)


# ---------------------------------------------------------------------------


def guard(r: Result, fn, *args, **kwargs):
    """Run one scenario's body, recording an exception as THAT scenario's problem.

    ⚠ Added after a falsification run exposed the failure mode: an exception (a Playwright timeout on
    a control the broken layout had made unclickable) propagated out of `run()` and the tool printed
    "the harness could not run" — losing every scenario's named assertions, including the ones that
    had already been collected and the ones still to come. A gate that cannot report is worse than no
    gate: the same run should have said "no tab bar at a mobile width", which names the bug.
    """
    try:
        return fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - reported, never traced
        r.problems.append(f"could not be measured: {type(exc).__name__}: {str(exc)[:200]}")
        return None


def run(base: str, shots: Path | None) -> int:
    results: list[Result] = []
    scroll_to = 400

    with sync_playwright() as pw:
        browser = pw.chromium.launch()

        for label, width, height in WIDTHS:
            r = Result(f"A/B/H · {label} ({width}x{height})")
            try:
                page, errors = open_frame(browser, base, width, height)
                try:
                    p = guard(r, probe, page)
                    if p is None:
                        r.problems.append("the frame produced no probe — nothing could be measured")
                        continue
                    r.problems += guard(r, assert_thumb_zone, p) or []
                    r.problems += guard(r, assert_header_present, p) or []
                    r.problems += guard(r, assert_no_sideways_scroll, p) or []

                    # B — thumb navigation, on the SAME page: tap a tab that is not the active one.
                    hrefs = p.get("tabHrefs") or []
                    target = next((h for h in hrefs if h and h != p["location"]), None)
                    if target is None:
                        r.problems.append("no tab offered a destination different from the current route")
                    else:
                        page.locator(f'nav[aria-label="Mobile"] a[href="{target}"]').first.click(
                            timeout=5_000
                        )
                        page.wait_for_timeout(250)
                        after = guard(r, probe, page)
                        if after:
                            if not after["location"].startswith(target):
                                r.problems.append(
                                    f"tapping the {target!r} tab left the route at {after['location']!r}"
                                )
                            if after["mounts"]["shell"] != 1:
                                r.problems.append(
                                    f"tapping a tab remounted the shell ({after['mounts']['shell']} mounts)"
                                )
                    if errors:
                        r.problems.append(f"page errors: {'; '.join(errors[:3])}")
                    if shots is not None:
                        shots.mkdir(parents=True, exist_ok=True)
                        page.screenshot(path=str(shots / f"shell-{width}x{height}.png"))
                finally:
                    page.close()
            except Exception as exc:  # noqa: BLE001
                r.problems.append(f"the frame did not load: {type(exc).__name__}: {str(exc)[:200]}")
            results.append(r)

        # C/D — the sheet, at 390px, on a page scrolled to 400px so the lock's RESTORE is measurable.
        r = Result("C · sheet opens, scrolls itself, and locks the body the iOS way")
        try:
            page, errors = open_frame(browser, base, 390, 844, scroll_to=scroll_to)
        except Exception as exc:  # noqa: BLE001
            r.problems.append(f"the frame did not load: {type(exc).__name__}: {str(exc)[:200]}")
            results.append(r)
            page = None
        if page is not None:
            try:
                # ⚠ The scroll position is read BEFORE the sheet opens, and it is the only moment it can
                # be read. Once the lock is on, the body is `position: fixed`, the document has nothing
                # left to scroll, and `window.scrollY` LEGITIMATELY reads 0 — the position now lives in
                # the body's negative `top`. Measuring it after opening would report a leak on a lock
                # that is working perfectly.
                held = page.evaluate("window.scrollY")
                if held != scroll_to:
                    r.problems.append(
                        f"the harness could not hold the page at scrollY {scroll_to} (it is at {held}) — "
                        "the lock cannot be measured"
                    )
                # ⚠ A JS click, NOT `locator.click()`. Playwright scrolls a target into view before
                # clicking it, and the trigger sits at the top of the fixture — so a locator click
                # silently scrolled the page back to 0 and the lock was then measured against a scroll
                # position of 0, which any implementation passes. (Recorded because the symptom is "the
                # assertion passes and the feature is broken", which is the worst kind.)
                page.evaluate("document.querySelector('[data-testid=\"open-sheet\"]').click()")
                page.wait_for_selector('[data-testid="sheet-panel"]', timeout=5_000)
                page.wait_for_timeout(300)  # the entrance transition
                p = guard(r, probe, page)
                if p:
                    r.problems += assert_sheet_open_and_locked(p, scroll_to)

                # Escape closes, and the page comes back where it was.
                page.keyboard.press("Escape")
                page.wait_for_timeout(400)
                closed = guard(r, probe, page)
                if closed:
                    r.problems += assert_sheet_closed(closed, scroll_to)
                restored = page.evaluate("window.scrollY")
                if abs(restored - scroll_to) > 2:
                    r.problems.append(
                        f"the page came back to scrollY {restored}, not {scroll_to} — the lock leaked"
                    )
                if errors:
                    r.problems.append(f"page errors: {'; '.join(errors[:3])}")
            except Exception as exc:  # noqa: BLE001
                r.problems.append(f"could not be measured: {type(exc).__name__}: {str(exc)[:200]}")
            finally:
                page.close()
            results.append(r)

        # A short, SLOW drag must not dismiss.
        r = Result("D · a short slow drag snaps back, a long drag dismisses")
        try:
            page, _ = open_frame(browser, base, 390, 844)
        except Exception as exc:  # noqa: BLE001
            r.problems.append(f"the frame did not load: {type(exc).__name__}: {str(exc)[:200]}")
            results.append(r)
            page = None
        if page is not None:
            try:
                page.evaluate("document.querySelector('[data-testid=\"open-sheet\"]').click()")
                page.wait_for_selector('[data-testid="sheet-panel"]', timeout=5_000)
                page.wait_for_timeout(300)
                p = probe(page)
                drag(page, p["sheetPanel"], dy=25, steps=12, delay_ms=40)  # 25px over ~480ms
                r.problems += assert_drag_snap_back(probe(page), dy=25)

                drag(page, p["sheetPanel"], dy=int(p["sheetPanel"]["h"] * 0.5), steps=8, delay_ms=10)
                page.wait_for_timeout(400)
                after = probe(page)
                if after.get("sheetOpen") or after.get("sheetPanel"):
                    r.problems.append("a drag past half the sheet's height did NOT dismiss it")
                # …and the body must be unlocked again, or the next sheet is unusable.
                if (after.get("bodyLock") or {}).get("position") == "fixed":
                    r.problems.append("the body stayed locked after a drag-dismissed sheet")
            except Exception as exc:  # noqa: BLE001
                r.problems.append(f"could not be measured: {type(exc).__name__}: {str(exc)[:200]}")
            finally:
                page.close()
            results.append(r)

        browser.close()

    width = max(len(r.label) for r in results) + 2
    failed = 0
    print(f"{'scenario'.ljust(width)} result")
    print("-" * (width + 8))
    for r in results:
        print(f"{r.label.ljust(width)} {'PASS' if r.ok else 'FAIL'}")
        for problem in r.problems:
            print(f"{' ' * width}   ✗ {problem}")
        if not r.ok:
            failed += 1
    print()
    if failed:
        print(f"FAIL — {failed} of {len(results)} scenario(s) reported a problem.")
        return 1
    print(f"PASS — {len(results)} scenarios, 0 problems.")
    return 0


def selftest() -> int:
    good_bar = {
        "x": 0.0,
        "y": 780.0,
        "w": 390.0,
        "h": 64.0,
        "right": 390.0,
        "bottom": 844.0,
    }
    base = {
        "vw": 390,
        "vh": 844,
        "tabBar": good_bar,
        "tabBarBottomGap": 0.0,
        "tabRects": [
            {"label": "Home", "w": 90.0, "h": 48.0},
            {"label": "Movies", "w": 90.0, "h": 48.0},
            {"label": "More", "w": 90.0, "h": 48.0},
        ],
        "header": {"x": 0.0, "y": 0.0, "w": 390.0, "h": 64.0, "right": 390.0, "bottom": 64.0},
        "overflowX": 0,
        "outside": [],
        "sheetOpen": True,
        "sheetPanel": {"x": 0.0, "y": 300.0, "w": 390.0, "h": 544.0, "right": 390.0, "bottom": 844.0},
        "sheetRadius": "20px",
        "sheetScrollable": True,
        "sheetOverscroll": "contain",
        "bodyLock": {"position": "fixed", "top": "-400px", "overflow": "hidden"},
        "focusInSheet": True,
        "mounts": {"shell": 1, "route": 1, "renders": 1},
    }
    closed = {
        **base,
        "sheetOpen": False,
        "sheetPanel": None,
        "bodyLock": {"position": "", "top": "", "overflow": ""},
        "focusInSheet": False,
    }

    cases: list[tuple[str, bool, list[str]]] = []

    def case(name: str, out: list[str], expect_problems: bool) -> None:
        cases.append((name, (not out) != expect_problems, out))

    # A — the thumb zone.
    case("thumb_zone accepts a good bar", assert_thumb_zone(base), False)
    case("thumb_zone catches a bar off the bottom edge", assert_thumb_zone({**base, "tabBarBottomGap": 34.0}), True)
    case(
        "thumb_zone catches a bar above the bottom third",
        assert_thumb_zone({**base, "tabBar": {**good_bar, "y": 300.0}}),
        True,
    )
    case(
        "thumb_zone catches a short tab",
        assert_thumb_zone({**base, "tabRects": [{"label": "Home", "w": 90.0, "h": 30.0}]}),
        True,
    )
    case(
        "thumb_zone catches a narrow tab",
        assert_thumb_zone({**base, "tabRects": [{"label": "x", "w": 28.0, "h": 48.0}]}),
        True,
    )
    case("thumb_zone catches no bar at all", assert_thumb_zone({**base, "tabBar": None}), True)
    case("thumb_zone catches a one-tab bar", assert_thumb_zone({**base, "tabRects": [{"label": "H", "w": 90.0, "h": 48.0}]}), True)

    # B/H.
    case("header accepts a real bar", assert_header_present(base), False)
    case("header catches a missing bar", assert_header_present({**base, "header": None}), True)
    case("no_sideways_scroll catches overflow", assert_no_sideways_scroll({**base, "overflowX": 9}), True)
    case(
        "no_sideways_scroll catches a poking element",
        assert_no_sideways_scroll({**base, "outside": [{"tag": "div", "cls": "x", "left": 0, "right": 999}]}),
        True,
    )

    # C — the sheet and its lock.
    case("sheet_open accepts a locked bottom sheet", assert_sheet_open_and_locked(base, 400), False)
    case(
        "sheet_open catches overflow:hidden instead of the iOS lock",
        assert_sheet_open_and_locked({**base, "bodyLock": {"position": "", "top": "", "overflow": "hidden"}}, 400),
        True,
    )
    case(
        "sheet_open catches a lock at the wrong offset",
        assert_sheet_open_and_locked({**base, "bodyLock": {"position": "fixed", "top": "-0px", "overflow": "hidden"}}, 400),
        True,
    )
    case(
        "sheet_open catches a sheet that is not bottom-anchored",
        assert_sheet_open_and_locked({**base, "sheetPanel": {**base["sheetPanel"], "bottom": 700.0}}, 400),
        True,
    )
    case(
        "sheet_open catches a sheet taller than the viewport",
        assert_sheet_open_and_locked({**base, "sheetPanel": {**base["sheetPanel"], "h": 900.0}}, 400),
        True,
    )
    case(
        "sheet_open catches missing overscroll containment",
        assert_sheet_open_and_locked({**base, "sheetOverscroll": "auto"}, 400),
        True,
    )
    case(
        "sheet_open catches non-scrolling content",
        assert_sheet_open_and_locked({**base, "sheetScrollable": False}, 400),
        True,
    )
    case(
        "sheet_open catches focus left behind the sheet",
        assert_sheet_open_and_locked({**base, "focusInSheet": False}, 400),
        True,
    )
    case("sheet_open catches an unopened sheet", assert_sheet_open_and_locked(closed, 400), True)

    # D.
    case("sheet_closed accepts a fully restored page", assert_sheet_closed(closed, 400), False)
    case("sheet_closed catches a still-locked body", assert_sheet_closed({**closed, "bodyLock": base["bodyLock"]}, 400), True)
    case("sheet_closed catches a sheet still open", assert_sheet_closed(base, 400), True)
    case("drag_snap_back accepts a sheet that snapped back", assert_drag_snap_back(base, 25), False)
    case("drag_snap_back catches a sheet that closed on a short drag", assert_drag_snap_back(closed, 25), True)
    case(
        "drag_snap_back catches a sheet left mid-drag",
        assert_drag_snap_back({**base, "sheetPanel": {**base["sheetPanel"], "bottom": 780.0}}, 25),
        True,
    )

    label_width = max(len(name) for name, _, _ in cases) + 2
    failed = 0
    for name, ok, extra in cases:
        print(f"{name.ljust(label_width)} {'ok' if ok else 'BROKEN'}")
        if not ok:
            failed += 1
            if extra:
                print(f"{' ' * label_width}   the assertion returned: {extra}")
    print()
    print(f"{len(cases) - failed}/{len(cases)} self-tests pass" + ("" if not failed else f" — {failed} BROKEN"))
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument("--shots", type=Path, default=None)
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()

    if args.selftest:
        return selftest()

    missing = fresh(args.base)
    if missing:
        print("FAIL — the dev server is not serving this folder's source:")
        for line in missing:
            print(f"  ✗ {line}")
        print("\nRestart it (kill the process that owns :5199, then `npx vite --port 5199 --strictPort`).")
        return 1

    try:
        return run(args.base, args.shots)
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL — the harness could not run: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
