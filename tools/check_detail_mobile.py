#!/usr/bin/env python3
"""The MOBILE DETAIL screen, measured in a real browser — MOBILE_FIRST_UI_PLAN §11 (M4).

    python3 tools/check_detail_mobile.py
    python3 tools/check_detail_mobile.py --kind series
    python3 tools/check_detail_mobile.py --selftest
    python3 tools/check_detail_mobile.py --shots /tmp/shots

It drives `frontend/harness/detail-mobile-frame.html` — the REAL `ItemDetail` mounted on the REAL
`LibraryOutletContext` seam with a stubbed API — at the widths the brief names (320, 390, 430) and
answers the questions the 2026-09-18 handoff left open:

  A. primary      the pinned action bar renders ONE primary action with a live label (`Resume` for a
                  mid-play movie, `Play` for an unplayed one, `Play S#E#` for a series) and it is on
                  screen and at least `--m-tap` tall.
  B. watched      the watched control is labelled by STATE — `Unwatched`/`Watched` — and there is
                  exactly ONE of it. ⚠ This is the tile the pre-2026-09-18 probe silently dropped:
                  its label filter listed only `Watched`, so the control it exists to measure read as
                  absent and the run was green anyway.
  C. tiles        the action tiles (`More` + the watched control) are on screen, ≥32px in both
                  directions, and never poke outside the viewport.
  D. layout       nothing overflows: `documentElement.scrollWidth == innerWidth` and no element's
                  box crosses a horizontal edge.

⚠ WHY A TOOL AND NOT A ONE-OFF PROBE. The handoff recorded this screen with a manual playwright run
whose assertion (`tiles == ["Watched", "More"]`) went stale the moment the control became
state-labelled — an assertion nobody re-ran, so the screen was described as "measured" while the
measurement no longer matched the code. A tool re-runs in one command, keeps a freshness guard, and
can be FALSIFIED (`--selftest`), which is the only thing that proves its assertions can fail.

⚠ FRESHNESS. Vite's watcher does not fire on this mount (WSL2/Docker) and an orphaned `vite` keeps
serving the PRE-EDIT module, so every marker is checked against BOTH the file on disk and what the
server is serving right now — see `fresh()`. Kill the server with `pgrep -f "[b]in/vite" | xargs -r
kill -9` before trusting any number.
"""
from __future__ import annotations

import argparse
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from playwright.sync_api import sync_playwright

_PCT = re.compile(r"\s*\(\d+%\)\s*$")
"""The progress suffix the pinned bar appends while a position exists — `Resume (28%)`."""
_CODE = re.compile(r"\s*S\d+E\d+\s*$")
"""The episode code the bar appends when the action targets an episode — `Play S1E1`."""

DEFAULT_BASE = "http://localhost:5199"
FRAME = "/harness/detail-mobile-frame.html"
REPO = Path(__file__).resolve().parent.parent
FRONTEND = REPO / "frontend"

MIN_TAP_PX = 44
"""⚠ The same number as `--m-tap` in `styles/index.css`, repeated on purpose — read from the CSS it
would agree with the CSS by construction, and the floor would move with a typo."""

MIN_TILE_PX = 32
"""The floor for the secondary action tiles. They are not the thumb's primary target, but a tile
below this is a mis-tap on a phone."""

WIDTHS: list[tuple[str, int, int]] = [
    ("phone 320", 320, 568),
    ("phone 390", 390, 844),
    ("phone 430", 430, 932),
]

WATCHED_LABELS = ("Watched", "Unwatched")

MARKERS: dict[str, str] = {
    # The frame itself. ⚠ The marker is the NEWEST thing it measures — the label set that went stale
    # — not merely something recent.
    "/harness/detail-mobile-frame.tsx": "TILE_LABELS",
    # The screen under test (the MOBILE detail screen — `layouts/mobile/DetailScreen.tsx`, not the
    # desktop `features/library/ItemDetail.tsx`) and the two facts the assertions depend on: the
    # primary action's test id and the state-labelled watched control.
    # ⚠ The marker is `detail-primary`, NOT the JSX attribute text: Vite/esbuild rewrites JSX
    # attributes into object properties (`"data-testid": "detail-primary"`), so the source spelling
    # is absent from the served module and the guard would report a false stale.
    "/src/layouts/mobile/DetailScreen.tsx": "detail-primary",
    "/src/features/library/WatchedAction.tsx": "Unwatched",
}


@dataclass
class Result:
    label: str
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def _fetch(url: str, attempts: int = 3, timeout: float = 20.0) -> str | None:
    """Fetch a module, retrying a TIMEOUT — right after a `vite` restart the first requests transform
    a lot of the module graph, and a guard that fires on warm-up is a guard people ignore."""
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                return response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError:
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = exc
            time.sleep(0.75 * (attempt + 1))
    raise last if last else RuntimeError("unreachable")


def fresh(base: str) -> list[str]:
    """Every marker must be present on disk AND in what the server is serving right now.

    ⚠ It checks BOTH sides: a marker no longer on disk is a bug in THIS TOOL (the guard could no
    longer detect staleness), and reporting that loudly is the only thing that stops it decaying
    into a check that always says "fresh".
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
                f"{path}: THIS TOOL'S MARKER {marker!r} is not in the file on disk — the marker is "
                "obsolete, so this guard can no longer detect a stale server"
            )
            continue
        try:
            body = _fetch(f"{base}{path}")
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{path}: could not be fetched after 3 attempts ({exc})")
            continue
        if body is None or marker not in body:
            problems.append(
                f"{path}: does not contain {marker!r} — the dev server is serving a STALE module"
            )
    return problems


def open_frame(browser, base: str, width: int, height: int, kind: str):
    """A FRESH page per scenario — a reused page carries the previous width's layout."""
    page = browser.new_page(viewport={"width": width, "height": height})
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    url = f"{base}{FRAME}?kind={kind}"
    page.goto(url, wait_until="load", timeout=30_000)
    page.wait_for_function("() => !!window.__probe", timeout=20_000)
    page.wait_for_selector('[data-testid="detail-primary"]', timeout=20_000)
    page.wait_for_timeout(150)
    return page, errors


def probe(page) -> dict:
    return page.evaluate("window.__probe()")


# ---------------------------------------------------------------------------
# Assertions — pure functions of a probe, so `--selftest` can hand them a bad one.
# ---------------------------------------------------------------------------


def assert_primary(p: dict, kind: str) -> list[str]:
    problems: list[str] = []
    primary = p.get("primary")
    if not primary:
        return ["primary action bar not rendered (no [data-testid='detail-primary'])"]
    text = (primary.get("text") or "").strip()
    if not text:
        problems.append("primary action has no label")
    # ⚠ The label is progress- and context-aware: the screen appends the percentage while a position
    # exists (`Resume (28%)`) and the episode code when the action targets one (`Play S1E1`). Asserting
    # the bare verb would fail on the real, correct screen — measured 2026-09-18.
    stem = _PCT.sub("", text)
    stem = _CODE.sub("", stem).strip()
    if stem not in ("Play", "Resume", "Replay"):
        problems.append(f"primary reads {text!r} — expected Play/Resume/Replay (optionally with a % or S#E# suffix)")
    if kind == "series" and stem in ("Play", "Resume") and not (_CODE.search(text) or _PCT.search(text)):
        problems.append(f"series primary reads {text!r} with no episode code or progress — it must say which episode it will play")
    if primary["h"] < MIN_TAP_PX:
        problems.append(f"primary is {primary['h']}px tall — under the {MIN_TAP_PX}px tap floor")
    if primary["bottom"] > p["viewportH"] + 1:
        problems.append(f"primary bottom {primary['bottom']} is below the {p['viewportH']}px viewport")
    if primary.get("opacity") not in (None, "1"):
        problems.append(f"primary opacity is {primary['opacity']} — it renders faded")
    return problems


def assert_watched_tile(p: dict) -> list[str]:
    """Exactly ONE state-labelled watched control, and it says which state it is in."""
    problems: list[str] = []
    tiles = p.get("tiles") or []
    labels = [t["text"] for t in tiles]
    watched = [t for t in tiles if t["text"] in WATCHED_LABELS]
    if len(watched) == 0:
        problems.append(
            f"no watched control found — the tile labels present are {labels}; the detail view OWNS "
            "this control, so it must render (⚠ the pre-2026-09-18 probe could not see it, which is "
            "how this screen was called measured while the label had changed)"
        )
    elif len(watched) > 1:
        problems.append(f"{len(watched)} watched controls rendered ({[t['text'] for t in watched]}) — one state, one control")
    return problems


def assert_tiles(p: dict) -> list[str]:
    problems: list[str] = []
    tiles = p.get("tiles") or []
    labels = [t["text"] for t in tiles]
    if "More" not in labels:
        problems.append(f"no More tile — labels present: {labels}")
    for t in tiles:
        if t["w"] < MIN_TILE_PX or t["h"] < MIN_TILE_PX:
            problems.append(f"tile {t['text']!r} is {t['w']}×{t['h']}px — under {MIN_TILE_PX}px")
        if t["bottom"] > p["viewportH"] + 1 or t["top"] < -1:
            problems.append(f"tile {t['text']!r} is off screen (top {t['top']}, bottom {t['bottom']})")
    return problems


def assert_layout(p: dict) -> list[str]:
    problems: list[str] = []
    if p["scrollWidth"] > p["innerWidth"] + 1:
        problems.append(
            f"the document scrolls {p['scrollWidth'] - p['innerWidth']}px horizontally "
            f"({p['scrollWidth']} > {p['innerWidth']})"
        )
    if p.get("overflow"):
        problems.append(f"{p['overflow']} element(s) poke outside the viewport: {p.get('overflowEls')}")
    return problems


ASSERTIONS = {
    "primary": lambda p, kind: assert_primary(p, kind),
    "watched": lambda p, kind: assert_watched_tile(p),
    "tiles": lambda p, kind: assert_tiles(p),
    "layout": lambda p, kind: assert_layout(p),
}


def check_width(browser, base: str, label: str, w: int, h: int, kind: str) -> tuple[Result, dict | None, list[str]]:
    page, errors = open_frame(browser, base, w, h, kind)
    try:
        p = probe(page)
    finally:
        page.close()
    result = Result(label)
    if errors:
        result.problems.extend(errors)
    for name, fn in ASSERTIONS.items():
        for problem in fn(p, kind):
            result.problems.append(f"[{name}] {problem}")
    return result, p, errors


def selftest() -> int:
    """Falsification: hand each assertion a deliberately broken probe and require it to go RED."""
    good = {
        "primary": {"text": "Resume", "w": 200, "h": 52, "top": 700, "bottom": 752, "opacity": "1"},
        "tiles": [
            {"text": "Unwatched", "w": 44, "h": 44, "top": 640, "bottom": 684},
            {"text": "More", "w": 44, "h": 44, "top": 640, "bottom": 684},
        ],
        "overflow": 0,
        "overflowEls": [],
        "scrollWidth": 390,
        "innerWidth": 390,
        "viewportH": 844,
    }
    baseline = [f"{n}: {fn(good, 'movie')}" for n, fn in ASSERTIONS.items()]
    if any(problems for _, problems in ((n, fn(good, "movie")) for n, fn in ASSERTIONS.items())):
        print("❌ SELFTEST: the GOOD probe fails an assertion — the assertions are wrong, not the screen")
        for line in baseline:
            print(f"   {line}")
        return 1

    mutations = {
        "primary": {**good, "primary": None},
        "watched": {**good, "tiles": [{"text": "More", "w": 44, "h": 44, "top": 1, "bottom": 45}]},
        "tiles": {**good, "tiles": [{"text": "Unwatched", "w": 20, "h": 20, "top": 1, "bottom": 21}]},
        "layout": {**good, "overflow": 1, "overflowEls": ["DIV.x"], "scrollWidth": 420},
    }
    failures: list[str] = []
    for name, bad in mutations.items():
        problems = ASSERTIONS[name](bad, "movie")
        if not problems:
            failures.append(f"{name}: mutation NOT caught — this assertion cannot fail")
        else:
            print(f"✅ {name}: RED as required — {problems[0]}")
    if failures:
        print("❌ SELFTEST FAILED:")
        for f in failures:
            print(f"   {f}")
        return 1
    print("✅ SELFTEST: every assertion went RED on its mutation and green on the good probe.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--kind", choices=["movie", "series"], default="movie")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--shots", default=None, help="directory to write one screenshot per width")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    problems = fresh(args.base)
    if problems:
        print("❌ the dev server is not serving the code under test:")
        for p in problems:
            print(f"   {p}")
        print("\n   Restart it:  pgrep -f \"[b]in/vite\" | xargs -r kill -9 && (cd frontend && npx vite --port 5199 --strictPort &)")
        return 1

    shots = Path(args.shots) if args.shots else None
    if shots:
        shots.mkdir(parents=True, exist_ok=True)

    results: list[Result] = []
    print(f"detail screen · kind={args.kind} · {args.base}{FRAME}")
    print(f"{'scenario':<12} {'primary':<14} {'tiles':<28} {'scroll':>10}  overflow")
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            for label, w, h in WIDTHS:
                result, p, _ = check_width(browser, args.base, label, w, h, args.kind)
                results.append(result)
                if p:
                    tile_text = ",".join(t["text"] for t in (p.get("tiles") or [])) or "—"
                    prim = ((p.get("primary") or {}).get("text") or "—")
                    print(
                        f"{label:<12} {prim:<14} {tile_text:<28} "
                        f"{p['scrollWidth']:>4}/{p['innerWidth']:<5} {p.get('overflow')}"
                    )
                    if shots:
                        page, _ = open_frame(browser, args.base, w, h, args.kind)
                        page.screenshot(path=str(shots / f"detail-{w}.png"), full_page=True)
                        page.close()
        finally:
            browser.close()

    print()
    failed = 0
    for r in results:
        if r.ok:
            print(f"✅ {r.label}")
        else:
            failed += 1
            print(f"❌ {r.label}")
            for problem in r.problems:
                print(f"   {problem}")
    print(f"\n{len(results) - failed}/{len(results)} widths passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
