#!/usr/bin/env python3
"""The layout switch, measured in a real browser — MOBILE_FIRST_UI_PLAN §8.3.

    python3 tools/check_mobile_layout_switch.py
    python3 tools/check_mobile_layout_switch.py --selftest
    python3 tools/check_mobile_layout_switch.py --shots /tmp/shots

It drives `frontend/harness/mobile-frame.html`, which mounts the REAL `LayoutModeProvider` and the
REAL `AppShell` over a stubbed api, and answers five questions that no unit test can:

  A. desktop_unchanged   at >= 1024px the app is untouched: the mobile tokens are EMPTY, and
                         `.m-grid` is not a grid at all — i.e. the mobile CSS is inert, not merely
                         overridden. ⚠ "It looks the same" is not the claim; "the rules do not
                         apply" is.
  B. token_reflow        `--m-grid-cols` is 3 / 4 / 5 at < 600 / 600-833 / >= 834, and the REAL
                         rendered grid has exactly that many tracks. The token and the layout are
                         compared against each other, not against a number written here twice.
  C. crossing_is_free    resizing 1280 -> 390 -> 834 -> 1280 does NOT remount the shell or the
                         route, does NOT refetch a library read, and does NOT sign anybody out.
  D. never_both_shells   no width renders the sidebar AND the mobile tab bar at once.
  E. no_sideways_scroll  nothing pokes outside the viewport horizontally at 320 / 390 / 1023.

⚠ THE FRESHNESS GUARD IS PART OF THE GATE. Vite's watcher does not fire on this mount, so an
orphaned `vite` holding :5199 serves the PRE-EDIT module and the measurement quietly reports the old
layout. That has cost this repo two false PASSes (`frontend/harness/README.md`). Five markers are
fetched and checked before a single assertion runs, and a missing one is a FAIL — never a warning.

⚠ `--selftest` is not decoration either. Every assertion below is a function of a probe dict, and the
self-test feeds each one a probe it must REJECT (the desktop assertion is handed a phone, the rphone
assertion is handed a desktop, the crossing assertion is handed a probe whose mount counters moved).
A checker whose only evidence is a green run has not been tested at all.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from playwright.sync_api import sync_playwright

DEFAULT_BASE = "http://localhost:5199"
FRAME = "/harness/mobile-frame.html"

# (label, width, height) — one shell, three widths, plus the two ends of the band the boundary moved
# across, plus the two widths the brief names as the acceptance sizes.
VIEWPORTS: list[tuple[str, int, int]] = [
    ("phone 320", 320, 568),
    ("phone 390", 390, 844),
    ("tablet 600", 600, 960),
    ("tablet 834", 834, 1180),
    ("just below the line 1023", 1023, 800),
    ("the line itself 1024", 1024, 768),
    ("laptop 1280", 1280, 900),
    ("desktop 1440", 1440, 900),
]

# ⚠ Five string literals that only the CURRENT source owns. A stale module cannot produce all five.
#
# ⚠ AND A MARKER MUST BE CODE, NOT A COMMENT: esbuild strips comments, so `// some new note` is
# absent from the served module even when the server is perfectly fresh — a marker-based guard that
# greps for prose reports "stale" for a fresh server (a mistake `falsify_check_cache.py` records).
#
# ⚠ A marker must also be something the CURRENT source still contains on disk. `fresh()` checks that
# both sides, so a marker that has quietly gone obsolete is reported as a TOOL bug rather than
# silently passing: otherwise the guard rots into a check that can only say "fresh".
MARKERS: dict[str, str] = {
    "/src/layouts/LayoutMode.tsx": "MOBILE_MAX_PX",
    "/src/styles/index.css": "m-grid",
    "/harness/mobile-frame.tsx": "left: +r.left",
    "/src/app/router.tsx": "desktop.",
    "/src/main.tsx": "LayoutModeProvider",
}

REPO = Path(__file__).resolve().parent.parent
# ⚠ The served paths are relative to `frontend/` (that is the vite root), not to the repo. Resolving
# them against the repo silently turned the disk-side check into "the file does not exist" for every
# marker — a guard that fails on a perfectly fresh server is worse than no guard.
FRONTEND = REPO / "frontend"

MOBILE_MAX_PX = 1023


def expected_cols(width: int) -> int:
    """The token's reflow, stated ONCE here so the assertion cannot drift from the CSS silently.

    ⚠ If this disagrees with `styles/index.css`, the tool fails — which is the point. The alternative
    (reading the expected number out of the CSS) would make the check agree with the CSS by
    construction and prove nothing.
    """
    if width >= 834:
        return 5
    if width >= 600:
        return 4
    return 3


@dataclass
class Result:
    label: str
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def fresh(base: str) -> list[str]:
    """Every marker must be present in what the dev server is serving right now.

    ⚠ It checks BOTH sides. A marker that is no longer in the file on disk is a bug in THIS TOOL
    (the marker went obsolete, so the guard could no longer detect staleness) — reporting that
    loudly is the only thing that stops the guard decaying into a check that always says "fresh".
    """
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
        except (urllib.error.URLError, TimeoutError) as exc:  # pragma: no cover - env dependent
            problems.append(f"{path}: could not be fetched ({exc})")
            continue
        if marker not in body:
            problems.append(f"{path}: does not contain {marker!r} — the dev server is serving a STALE module")
    return problems


def probe(browser, base: str, width: int, height: int) -> dict:
    """Load the frame at a size and read `window.__probe()` — on a FRESH PAGE, always.

    ⚠ The fresh page is not tidiness. This repo's browser tools have twice failed at their eighth
    or ninth frame loaded into one Chromium page ("the frame did not load") — a previous scenario's
    `<video>`, timers or observers survive a `goto` and the next mount never completes. The cure is
    one page per scenario, which is what `ARCHITECTURE.md` §18.7 records and what this does.
    """
    page = browser.new_page(viewport={"width": width, "height": height})
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    try:
        page.goto(f"{base}{FRAME}", wait_until="load", timeout=30_000)
        # `window.__probe` is installed when the frame's module evaluates — i.e. BEFORE React has
        # rendered anything. Waiting on it first separates "the frame never loaded" from "the frame
        # loaded and the app did not render", which are different failures with different causes.
        page.wait_for_function("() => !!window.__probe", timeout=20_000)
        page.wait_for_selector('[data-testid="route-fixture"]', timeout=20_000)
        # One frame for the provider's effect to publish `data-layout` and the queries to settle.
        page.wait_for_timeout(120)
        return page.evaluate("window.__probe()")
    except Exception as exc:  # noqa: BLE001 - report the console, never a bare Playwright traceback
        detail = "; ".join(errors[:4]) if errors else "no page errors were reported"
        raise AssertionError(
            f"the frame did not render at {width}x{height}: {type(exc).__name__}: {exc} — {detail}"
        ) from exc
    finally:
        page.close()


# ---------------------------------------------------------------------------
# The assertions — each a pure function of a probe, so the self-test can feed it the wrong one.
# ---------------------------------------------------------------------------


def assert_desktop_unchanged(p: dict) -> list[str]:
    """At >= 1024px the mobile layer must not reach the page at all."""
    problems: list[str] = []
    if p["mode"] != "desktop":
        problems.append(f"mode is {p['mode']!r}, expected 'desktop'")
    if p["gridColsToken"]:
        problems.append(
            f"--m-grid-cols is {p['gridColsToken']!r} at {p['vw']}px — the mobile token block is "
            "applying to a desktop viewport"
        )
    if p["gridDisplay"] == "grid":
        problems.append(
            f"`.m-grid` computes display:{p['gridDisplay']} at {p['vw']}px — the mobile CSS is "
            "reaching the desktop tree"
        )
    if not p["sidebar"] or p["sidebar"]["w"] <= 0:
        problems.append("the sidebar is not visible at a desktop width")
    if p["mobileBar"] and p["mobileBar"]["w"] > 0:
        problems.append("the mobile tab bar is visible at a desktop width")
    return problems


def assert_mobile_mode_and_tokens(p: dict) -> list[str]:
    """Below 1024px: the mode, the token, and the REALLY RENDERED grid must agree."""
    problems: list[str] = []
    want_cols = expected_cols(p["vw"])
    if p["mode"] != "mobile":
        problems.append(f"mode is {p['mode']!r}, expected 'mobile'")
    if p["gridColsToken"] != str(want_cols):
        problems.append(
            f"--m-grid-cols is {p['gridColsToken']!r} at {p['vw']}px, expected {want_cols!r}"
        )
    if p["gridDisplay"] != "grid":
        problems.append(f"`.m-grid` computes display:{p['gridDisplay']!r}, expected 'grid'")
    if p["gridTracks"] != want_cols:
        problems.append(
            f"the rendered grid has {p['gridTracks']} track(s) at {p['vw']}px, expected {want_cols} "
            "— the token and the layout disagree"
        )
    if p["tapTokens"]["input"] != "16px":
        problems.append(
            f"--m-input is {p['tapTokens']['input']!r} — anything under 16px makes iOS zoom on focus"
        )
    return problems


def assert_crossing_is_free(before: dict, after: dict) -> list[str]:
    """A resize is a presentation change and nothing else."""
    problems: list[str] = []
    for key, label in (("shell", "the shell"), ("route", "the routed view")):
        if after["mounts"][key] != before["mounts"][key]:
            problems.append(
                f"{label} REMOUNTED across a resize "
                f"({before['mounts'][key]} -> {after['mounts'][key]} mounts)"
            )
    if len(after["calls"]) != len(before["calls"]):
        new = [c["url"] for c in after["calls"][len(before["calls"]) :]]
        problems.append(f"a resize fired {len(new)} new request(s): {', '.join(new)}")
    if after["signInForm"]:
        problems.append("a resize landed on the sign-in form — the session was thrown away")
    if after["location"] != before["location"]:
        problems.append(f"a resize navigated {before['location']} -> {after['location']}")
    return problems


def assert_never_both_shells(p: dict) -> list[str]:
    """One shell at a time, at every width. A state with both is a styling bug that looks like a
    layout bug, and it is the first thing a wrong breakpoint produces."""
    problems: list[str] = []
    sidebar = bool(p["sidebar"] and p["sidebar"]["w"] > 0)
    bar = bool(p["mobileBar"] and p["mobileBar"]["w"] > 0)
    if sidebar and bar:
        problems.append("the sidebar AND the mobile tab bar are both visible")
    if not sidebar and not bar:
        problems.append("NEITHER shell is visible — there is no navigation at all")
    return problems


def assert_no_sideways_scroll(p: dict) -> list[str]:
    problems: list[str] = []
    if p["overflowX"] > 0:
        problems.append(
            f"the document is {p['overflowX']}px wider than the viewport — the page scrolls sideways"
        )
    if p["outside"]:
        worst = p["outside"][:3]
        detail = "; ".join(f"<{o['tag']} class={o['cls']!r}> {o['left']}..{o['right']}" for o in worst)
        problems.append(f"{len(p['outside'])} element(s) poke outside the viewport: {detail}")
    return problems


# ---------------------------------------------------------------------------


def run(base: str, shots: Path | None) -> int:
    results: list[Result] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch()

        for label, width, height in VIEWPORTS:
            r = Result(f"A/B/D/E · {label} ({width}x{height})")
            p = probe(browser, base, width, height)
            if width >= 1024:
                r.problems += assert_desktop_unchanged(p)
            else:
                r.problems += assert_mobile_mode_and_tokens(p)
            r.problems += assert_never_both_shells(p)
            r.problems += assert_no_sideways_scroll(p)
            if shots is not None:
                shots.mkdir(parents=True, exist_ok=True)
                shot = browser.new_page(viewport={"width": width, "height": height})
                shot.goto(f"{base}{FRAME}", wait_until="load", timeout=30_000)
                shot.wait_for_selector('[data-testid="route-fixture"]', timeout=20_000)
                shot.screenshot(path=str(shots / f"switch-{width}x{height}.png"), full_page=False)
                shot.close()
            results.append(r)

        # C — the crossing. ⚠ This one needs ONE page, resized in place: the whole question is what
        # survives a resize, so a fresh page per width would answer a different question entirely.
        crossed = Result("C · resizing 1280 -> 390 -> 834 -> 1280 costs nothing")
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            page.goto(f"{base}{FRAME}", wait_until="load", timeout=30_000)
            page.wait_for_function("() => !!window.__probe", timeout=20_000)
            page.wait_for_selector('[data-testid="route-fixture"]', timeout=20_000)
            page.wait_for_timeout(150)
            before = page.evaluate("window.__probe()")

            path: list[tuple[str, dict]] = []
            for width, height in ((390, 844), (834, 1180), (1280, 900)):
                page.set_viewport_size({"width": width, "height": height})
                page.wait_for_timeout(250)
                path.append((f"{width}px", page.evaluate("window.__probe()")))

            for width_label, p in path:
                crossed.problems += [
                    f"at {width_label}: {m}" for m in assert_crossing_is_free(before, p)
                ]
            # …and the end state must be the desktop one again, not merely "not remounted".
            crossed.problems += assert_desktop_unchanged(path[-1][1])
        finally:
            page.close()
        results.append(crossed)

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
    """Feed every assertion a probe it must REJECT. A check that cannot fail is not a check."""
    desktop = {
        "vw": 1280,
        "mode": "desktop",
        "gridColsToken": "",
        "gridDisplay": "block",
        "gridTracks": 0,
        "sidebar": {"x": 0, "y": 0, "w": 240, "h": 900},
        "mobileBar": {"w": 0},
        "tapTokens": {"input": "16px", "nav": "56px", "tap": "44px"},
        "mounts": {"shell": 1, "route": 1, "renders": 1},
        "calls": [{"url": "/api/auth/me", "method": "GET"}],
        "signInForm": False,
        "location": "/",
        "overflowX": 0,
        "outside": [],
    }
    phone = {
        **desktop,
        "vw": 390,
        "mode": "mobile",
        "gridColsToken": "3",
        "gridDisplay": "grid",
        "gridTracks": 3,
        "sidebar": {"w": 0},
        "mobileBar": {"w": 390},
    }

    cases: list[tuple[str, callable, list[str]]] = []  # type: ignore[type-arg]

    def case(name: str, fn, expectation: bool) -> None:  # type: ignore[no-untyped-def]
        out = fn()
        got = not out
        cases.append((name, lambda: got == expectation, out))  # type: ignore[arg-type]

    # Each assertion, handed a probe it must reject, and one it must accept.
    case("desktop_unchanged rejects a phone", lambda: assert_desktop_unchanged(phone), False)
    case("desktop_unchanged accepts a desktop", lambda: assert_desktop_unchanged(desktop), True)
    case("mobile_mode rejects a desktop", lambda: assert_mobile_mode_and_tokens(desktop), False)
    case("mobile_mode accepts a phone", lambda: assert_mobile_mode_and_tokens(phone), True)

    # A token that disagrees with the rendered grid must be caught by the GRID assertion too.
    lying = {**phone, "gridColsToken": "4"}
    case("mobile_mode catches a token/grid disagreement", lambda: assert_mobile_mode_and_tokens(lying), False)
    # The 16px rule.
    small = {**phone, "tapTokens": {**phone["tapTokens"], "input": "14px"}}
    case("mobile_mode catches a sub-16px input", lambda: assert_mobile_mode_and_tokens(small), False)
    # The reflow boundaries themselves.
    for w, cols in ((320, 3), (599, 3), (600, 4), (833, 4), (834, 5), (1023, 5)):
        p = {**phone, "vw": w, "gridColsToken": str(cols), "gridTracks": cols}
        case(f"mobile_mode accepts {w}px at {cols} columns", lambda p=p: assert_mobile_mode_and_tokens(p), True)
    bad = {**phone, "vw": 834, "gridColsToken": "4", "gridTracks": 4}
    case("mobile_mode rejects 834px at 4 columns", lambda: assert_mobile_mode_and_tokens(bad), False)

    remounted = {
        **desktop,
        "mounts": {"shell": 2, "route": 1, "renders": 2},
    }
    case("crossing_is_free catches a remount", lambda: assert_crossing_is_free(desktop, remounted), False)
    refetched = {
        **desktop,
        "calls": desktop["calls"] + [{"url": "/api/library/items", "method": "GET"}],
    }
    case("crossing_is_free catches a refetch", lambda: assert_crossing_is_free(desktop, refetched), False)
    signedout = {**desktop, "signInForm": True}
    case("crossing_is_free catches a sign-out", lambda: assert_crossing_is_free(desktop, signedout), False)
    case("crossing_is_free accepts an unchanged probe", lambda: assert_crossing_is_free(desktop, desktop), True)

    both = {**desktop, "mode": "mobile", "sidebar": {"w": 76}, "mobileBar": {"w": 390}}
    case("never_both_shells catches both shells", lambda: assert_never_both_shells(both), False)
    neither = {**desktop, "sidebar": {"w": 0}, "mobileBar": {"w": 0}}
    case("never_both_shells catches no shell", lambda: assert_never_both_shells(neither), False)
    case("never_both_shells accepts the desktop shell", lambda: assert_never_both_shells(desktop), True)

    wide = {**desktop, "overflowX": 12}
    case("no_sideways_scroll catches document overflow", lambda: assert_no_sideways_scroll(wide), False)
    poking = {**desktop, "outside": [{"tag": "div", "cls": "hero", "left": 0, "right": 1400}]}
    case("no_sideways_scroll catches an element", lambda: assert_no_sideways_scroll(poking), False)

    # And the freshness guard must be able to fail, or every run could be reading a stale module.
    cases.append(
        (
            "fresh rejects a missing marker",
            lambda: fresh("http://127.0.0.1:9") != [],  # nothing listening -> the guard must speak
            [],
        )
    )

    label_width = max(len(name) for name, _, _ in cases) + 2
    failed = 0
    for name, ok_fn, extra in cases:
        ok = bool(ok_fn())
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
    parser.add_argument("--base", default=DEFAULT_BASE, help=f"dev server (default {DEFAULT_BASE})")
    parser.add_argument("--shots", type=Path, default=None, help="write a screenshot per viewport here")
    parser.add_argument("--selftest", action="store_true", help="prove the assertions can fail")
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
    except Exception as exc:  # noqa: BLE001 - a harness failure must report, not traceback
        print(f"FAIL — the harness could not run: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
