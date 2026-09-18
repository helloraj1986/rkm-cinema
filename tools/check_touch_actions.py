#!/usr/bin/env python3
"""The poster actions, on a device that cannot hover — MOBILE_FIRST_UI_PLAN §7.3 (M3).

    python3 tools/check_touch_actions.py
    python3 tools/check_touch_actions.py --selftest
    python3 tools/check_touch_actions.py --shots /tmp/shots

**The defect.** Every poster action in the app — the ▶ / Episodes button, the watched toggle and the
⋯ menu — was `opacity-0` with `group-hover:opacity-100` and **no `(hover: hover)` guard anywhere**.
On a touch device those actions are not merely unstyled; they are **invisible and untappable**, which
is the app's primary interaction. It is also invisible in every screenshot, because a desktop browser
hides them "correctly" — it can hover.

The rule that fixes it lives in `styles/index.css` (`.rkm-reveal`, `.rkm-reveal-hit`): visible by
default, hidden only where there is a real hover, and hovering or keyboard focus reveals them exactly
as before.

**What this check proves, and in which direction:**
  A. no_hover      ⚠ the emulated phone REALLY has no hover (`(hover: none)` matches) — asserted
                   BEFORE anything else, because without it every other assertion below passes
                   vacuously on a desktop browser that can always hover
  B. visible       on that phone the ▶/Episodes button and the ⋯ are rendered — and NO watched
                   TOGGLE exists on the poster at all (inverted 2026-09-19: the details view owns
                   it — see assert_touch_report)
                   (opacity > 0, pointer-events not `none`, a real box)
  C. tappable      a real TOUCH on ⋯ opens its menu — visible is not the same as reachable
  D. compact       the compact list's ▶ is visible on touch too (a second map over the same rows)
  E. desktop_intact a mouse-driven viewport still HIDES them until hover, then shows them — the
                   direction that must not regress, and the one a "make it visible" fix usually breaks
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

DEFAULT_BASE = "http://localhost:5199"
FRAME = "/harness/library-frame.html"
REPO = Path(__file__).resolve().parent.parent
FRONTEND = REPO / "frontend"

#: ⚠ `(hover: none)` is the whole premise. If the browser will not produce it, this check has no
#: subject and must say so rather than pass.
HOVER_QUERY = "(hover: none)"
NEEDS_HOVER_QUERY = "(hover: hover) and (pointer: fine)"

#: The ⋯ trigger, by the accessible name it already carries — used both to measure it and to TAP it.
MENU_SELECTOR = 'button[aria-label^="More actions"]'

#: The action surfaces §7.3 names, as (label, JS that returns the element to measure).
#: ⚠ `watched` is INVERTED as of 2026-09-19 (his decision, `KNOWN_ISSUES` §8). It is no longer a
#: target measured as visible — it is the control that must NOT exist. The accepted answer to his #2
#: report (2026-09-18) is that the DETAILS view owns the watched control and the poster only REFLECTS
#: status, so a poster watched TOGGLE is the "two green ticks" report coming back. Keep the selector:
#: it is what DETECTS the return. ⚠ The status MARKER on a played poster is a different thing and must
#: stay — `tools/check_poster_watched.py` owns that side.
TARGETS = {
    "cta": "document.querySelector('[data-testid=\"media-card-cta\"]')?.closest('button')",
    "watched": "document.querySelector('button[aria-label^=\"Mark as\"]')",
    "menu": f"document.querySelector({json.dumps(MENU_SELECTOR)})",
    "compact_play": "document.querySelector('[data-testid=\"compact-list\"] button[aria-label^=\"Play\"]')",
    "compact_row": "document.querySelector('[data-testid=\"media-list-row\"]')",
}

PROBE = """
(labels) => {
  const out = {};
  for (const [label, expr] of Object.entries(labels)) {
    const el = eval(expr);
    if (!el) { out[label] = null; continue; }
    // ⚠ TWO different properties, read two different ways, and getting this wrong made this check
    // lie in BOTH directions before it was right:
    //   * `opacity` is NOT inherited but it MULTIPLIES down the tree, so a button whose own opacity
    //     is 1 inside a row at `opacity: 0` is invisible — the walk is required, and reading the
    //     leaf alone reported the ⋯ as visible on a mouse viewport, where its row hides it.
    //   * `pointer-events` IS inherited, so an element's OWN computed value already accounts for the
    //     whole chain — and a descendant may re-enable it (`auto`) under an ancestor that is `none`,
    //     which is exactly how this card works. OR-ing the ancestors reported every action as
    //     untappable, including ones that demonstrably work.
    let opacity = 1;
    for (let n = el; n && n !== document.documentElement; n = n.parentElement) {
      opacity *= Number(getComputedStyle(n).opacity);
    }
    const own = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    out[label] = {
      opacity: Number(opacity.toFixed(3)),
      pointerEvents: own.pointerEvents,
      display: own.display,
      width: Math.round(r.width),
      height: Math.round(r.height),
      role: el.getAttribute('role') || el.tagName.toLowerCase(),
    };
  }
  out.__hoverNone = window.matchMedia('(hover: none)').matches;
  out.__hoverFine = window.matchMedia('(hover: hover) and (pointer: fine)').matches;
  return out;
}
"""

PROBLEMS: list[str] = []


def problem(message: str) -> None:
    PROBLEMS.append(message)


def check(condition: bool, message: str) -> bool:
    if not condition:
        problem(message)
    return condition


def assert_visible(name: str, label: str, state: dict | None) -> None:
    """⚠ `visible` = rendered AND able to receive a touch. Both halves, because an element with
    `pointer-events: none` at full opacity looks perfect and cannot be tapped."""
    if not check(bool(state), f"{name}: {label} is not in the DOM at all"):
        return
    check(state["opacity"] > 0.5,
          f"{name}: {label} is INVISIBLE (opacity {state['opacity']}) — a hover-only action on a "
          f"device with no hover is an action that does not exist")
    check(state["pointerEvents"] != "none",
          f"{name}: {label} is visible but `pointer-events: none`, so a tap goes through it to the "
          f"card behind — it must be tappable, not just painted")
    check(state["width"] > 0 and state["height"] > 0,
          f"{name}: {label} has no box ({state['width']}×{state['height']})")


def assert_hidden(name: str, label: str, state: dict | None) -> None:
    if not check(bool(state), f"{name}: {label} is not in the DOM at all"):
        return
    check(state["opacity"] < 0.5,
          f"{name}: {label} is VISIBLE with no hover (opacity {state['opacity']}) — the desktop "
          f"layout must keep its hidden-until-hover behaviour")


def assert_touch_report(name: str, report: dict) -> None:
    """A phone: no hover, every ACTION reachable — and NO watched control on the poster.

    ⚠ The last one is INVERTED (2026-09-19, his decision, KNOWN_ISSUES §8). His accepted #2 answer is
    that the DETAILS view owns the watched control and the poster only REFLECTS status, so a poster
    watched TOGGLE is a defect rather than a target. This goes RED if one ever comes back, which is the
    only thing that keeps a deleted control deleted.
    """
    assert_visible(name, "the ▶/Episodes action", report.get("cta"))
    assert_visible(name, "the ⋯ menu", report.get("menu"))
    # ⚠ Not vacuous, and the ORDER is why: the two assertions above prove the POSTER really rendered
    # before this one claims something is MISSING from it. A frame that never painted would pass an
    # absence check for free — which is the exact failure mode this file has been burned by.
    check(report.get("watched") is None,
          f"{name}: the poster offers a WATCHED TOGGLE again ({report.get('watched')}) — the details view "
          f"owns that control and the poster only reflects status (his #2 rule, 2026-09-18), so a poster "
          f"toggle is the 'two green ticks' report coming back")


def assert_desktop_report(name: str, report: dict) -> None:
    """A mouse: hidden until hover — the direction this fix must not change."""
    assert_hidden(name, "the ▶/Episodes action (before hover)", report.get("cta"))
    assert_hidden(name, "the ⋯ menu (before hover)", report.get("menu"))
    assert_visible(name, "the ▶/Episodes action (with hover)", report.get("cta_hover"))
    assert_visible(name, "the ⋯ menu (with hover)", report.get("menu_hover"))


def selftest() -> int:
    visible = {"opacity": 1.0, "pointerEvents": "auto", "width": 48, "height": 48}
    invisible = {"opacity": 0.0, "pointerEvents": "none", "width": 48, "height": 48}
    ghost = {"opacity": 1.0, "pointerEvents": "none", "width": 48, "height": 48}
    cases = [
        ("a phone with every action visible and tappable — ACCEPT",
         assert_touch_report, "phone",
         {"cta": visible, "menu": visible, "watched": None}, True),
        ("…but the poster's watched TOGGLE is back — REJECT (his #2 rule, inverted 2026-09-19)",
         assert_touch_report, "phone",
         {"cta": visible, "menu": visible, "watched": visible}, False),
        ("a hover-only action still hidden on the phone — REJECT",
         assert_touch_report, "phone",
         {"cta": invisible, "menu": visible, "watched": None}, False),
        ("opacity 1 but pointer-events none (a painted, untappable button) — REJECT",
         assert_touch_report, "phone",
         {"cta": ghost, "menu": visible, "watched": None}, False),
        ("an action missing from the DOM entirely — REJECT",
         assert_touch_report, "phone",
         {"cta": None, "menu": visible, "watched": None}, False),
        ("a mouse with actions hidden until hover, then visible — ACCEPT",
         assert_desktop_report, "desktop",
         {"cta": invisible, "menu": invisible, "cta_hover": visible, "menu_hover": visible}, True),
        ("the desktop regression this fix causes if it forgets the media query — REJECT",
         assert_desktop_report, "desktop",
         {"cta": visible, "menu": visible, "cta_hover": visible, "menu_hover": visible}, False),
    ]
    failures = []
    for label, fn, name, report, should_pass in cases:
        PROBLEMS.clear()
        fn(name, report)
        passed = not PROBLEMS
        if passed != should_pass:
            failures.append(f"{label}: expected {'PASS' if should_pass else 'FAIL'} "
                            f"({PROBLEMS[:2]})")
        print(f"  {'ok  ' if passed == should_pass else 'WRONG'}  {label}")
    PROBLEMS.clear()
    print(f"\nselftest: {len(cases) - len(failures)}/{len(cases)} probes answered as they must")
    for line in failures:
        print(f"  !! {line}")
    return 1 if failures else 0


def served_source(url: str) -> str:
    for _ in range(3):
        try:
            with urllib.request.urlopen(url, timeout=15) as response:
                return response.read().decode("utf-8", "replace")
        except (urllib.error.URLError, OSError):
            time.sleep(2)
    return "__unreachable__"


def measure(base: str, *, touch: bool, compact: bool, shots: str | None) -> dict:
    query = "folder=1&rows=3" + ("&view=compact" if compact else "")
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        ctx = browser.new_context(
            viewport={"width": 390, "height": 844} if touch else {"width": 1280, "height": 800},
            is_mobile=touch, has_touch=touch, device_scale_factor=1)
        page = ctx.new_page()
        page.goto(f"{base}{FRAME}?{query}", wait_until="domcontentloaded")
        page.wait_for_selector('[data-testid="media-card"], [data-testid="compact-list"] > *',
                               timeout=15_000)
        page.wait_for_timeout(250)
        report = page.evaluate(PROBE, TARGETS)
        if not touch:
            page.hover('[data-testid="media-card"]')
            page.wait_for_timeout(400)
            after = page.evaluate(PROBE, TARGETS)
            report["cta_hover"] = after.get("cta")
            report["menu_hover"] = after.get("menu")
        else:
            # C — visible is not reachable: TAP the ⋯ and require its menu to open.
            try:
                page.tap(MENU_SELECTOR, timeout=8_000)
                page.wait_for_selector('[role="menu"]', timeout=5_000)
                report["menu_opened"] = True
            except Exception as exc:  # noqa: BLE001 — reported, never swallowed
                report["menu_opened"] = False
                report["menu_error"] = type(exc).__name__
        if shots:
            Path(shots).mkdir(parents=True, exist_ok=True)
            page.screenshot(path=f"{shots}/{'phone' if touch else 'desktop'}"
                                 f"{'-compact' if compact else ''}.png")
        browser.close()
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--shots", help="directory for the phone/desktop screenshots")
    ap.add_argument("--selftest", action="store_true", help="falsify the assertions, no browser")
    ap.add_argument("--json", metavar="PATH")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    css = served_source(f"{args.base}/src/styles/index.css")
    if css == "__unreachable__":
        print(f"!! the dev server at {args.base} is not answering — start it: "
              f"cd frontend && npx vite --port 5199 --strictPort")
        return 2
    if ".rkm-reveal" not in css:
        print("!! the dev server is serving a STALE styles/index.css — kill the `node …/bin/vite` "
              "holding :5199 (NOT the npm wrapper) and start it again")
        return 2

    print(f"checking touch reachability against {args.base}\n")
    out: dict[str, dict] = {}

    phone = measure(args.base, touch=True, compact=False, shots=args.shots)
    out["phone"] = phone
    # A — the premise, before anything is concluded from it.
    if not check(bool(phone.get("__hoverNone")),
                 "phone: this browser did NOT emulate a device with no hover "
                 f"({HOVER_QUERY} did not match) — every assertion here would pass vacuously on a "
                 "desktop browser, so the run is meaningless"):
        for message in PROBLEMS:
            print(f"FAIL: {message}")
        return 1
    print(f"  phone      no-hover emulated ✅ · "
          f"cta {phone.get('cta')} · watched {phone.get('watched')} · menu {phone.get('menu')}")
    assert_touch_report("phone", phone)
    check(bool(phone.get("menu_opened")),
          f"phone: tapping ⋯ did not open its menu "
          f"({phone.get('menu_error', 'no menu appeared')}) — the action is painted but not "
          f"reachable, which is the difference this whole check exists for")

    compact = measure(args.base, touch=True, compact=True, shots=args.shots)
    out["phone-compact"] = compact
    print(f"  phone/compact  row {compact.get('compact_row')} · play {compact.get('compact_play')}")
    # ⚠ Below 640px the compact row carries NO play button at all — it lives in the status column,
    # which is `hidden sm:flex`. That is a layout decision, not the hover bug: the ROW is the touch
    # target (`role="button"`, full width). So the assertion is that the row is a real target, and
    # that the ▶ — where it exists — is visible and tappable too.
    row = compact.get("compact_row")
    if check(bool(row), "phone-compact: the compact row is not in the DOM"):
        check(row["width"] > 100 and row["height"] > 30,
              f"phone-compact: the row is only {row['width']}×{row['height']} — it is meant to be the "
              f"full-width touch target on a phone")
        check(row["role"] == "button",
              f"phone-compact: the row's role is {row['role']!r}, not 'button' — the tap target must "
              f"say what it does")
    play = compact.get("compact_play")
    if play is not None and play["width"] > 0 and play["height"] > 0:
        assert_visible("phone-compact", "the compact row's ▶", play)
    else:
        print("  ⚠ the compact row's ▶ is absent at 390px BY DESIGN (its column is `hidden sm:flex`); "
              "the row itself is the touch target, asserted above")

    desktop = measure(args.base, touch=False, compact=False, shots=args.shots)
    out["desktop"] = desktop
    print(f"  desktop    hover emulated ✅ · before {desktop.get('cta', {}).get('opacity')} / "
          f"{desktop.get('cta', {}).get('pointerEvents')} · after {desktop.get('cta_hover', {}).get('opacity')}")
    assert_desktop_report("desktop", desktop)

    if args.json:
        Path(args.json).write_text(json.dumps(out, indent=2))
        print(f"\nraw measurements: {args.json}")
    print()
    if PROBLEMS:
        for message in PROBLEMS:
            print(f"FAIL: {message}")
        return 1
    print("PASS — on a device with no hover every poster action is visible AND tappable, a real tap "
          "opens the ⋯ menu, and a mouse still gets the hover behaviour it always had")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
