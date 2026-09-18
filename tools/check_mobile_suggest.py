#!/usr/bin/env python3
"""The phone's SUGGEST SHEET, and the one acquisition failure with structure behind it — 2026-09-18.

    python3 tools/check_mobile_suggest.py
    python3 tools/check_mobile_suggest.py --selftest
    python3 tools/check_mobile_suggest.py --shots /tmp/shots

`POST /api/media/{id}/request` answers **409** when the title it was asked for matches several
titles: `detail: {message, candidates}` (`api/routes/media.py`). Until 2026-09-18 the candidate list
never reached the browser at all (`ApiError` kept only the sentence), so the failure arrived as a
toast that named nothing — and a screen could not have rendered the list even if it wanted to.

It drives `frontend/harness/search-mobile-frame.html` — the REAL `SearchScreen` over a stubbed API —
and asserts the three things a unit test cannot:

  A. ambiguous   with `?ambiguous=1`, pressing Download on a discovered title opens THAT title's
                 sheet with the server's sentence and the candidate titles in it.
  B. no-panel    WITHOUT the 409 the same press renders no panel at all, and sends exactly one
                 request — the negative case, or A would be evidence that the panel always renders.
  C. in-sheet    the same 409 arriving while the sheet is ALREADY open puts the list in that sheet
                 (the flow this feature exists for: download from the details, not from the row).
  D. narrow      the whole thing fits 320px with nothing poking outside the viewport.

⚠ The assertion that matters most is `no-pick-controls`: the server's candidates carry a title and a
year and **no id**, so "pick one" has nothing to re-request with. A button, link or `role="button"`
among them would be a control that cannot act — the defect M3-part-4 removed from the details page,
and the reason this list is read-only until the backend carries an id (`KNOWN_ISSUES` §7).

⚠ FRESHNESS. Vite's watcher does not fire on this mount (WSL2/Docker) and an orphaned `vite` keeps
serving the PRE-EDIT module, so every marker is checked against BOTH the file on disk and what the
server is serving right now. Restart before trusting any number:
    pgrep -f "[b]in/vite" | xargs -r kill -9 && (cd frontend && npx vite --port 5199 --strictPort &)
"""
from __future__ import annotations

import argparse
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from playwright.sync_api import sync_playwright

DEFAULT_BASE = "http://localhost:5199"
FRAME = "/harness/search-mobile-frame.html"
REPO = Path(__file__).resolve().parent.parent
FRONTEND = REPO / "frontend"

SENTENCE = "Two titles matched — pick one"
"""The server's own sentence, from the route. ⚠ Asserted BY VALUE: the point of this feature is that
the person reads the SERVER's words, not the client's paraphrase of them."""

EXPECTED_CANDIDATES = ("Sholay", "The Sholay Girl")
"""Both candidates the 409 carries. Asserting one would pass on a list that dropped the other."""

MARKERS: dict[str, str] = {
    # The frame (its 409 stub and its probe) — ⚠ the newest thing it carries, not merely something
    # recent, or a stale serve of the frame would go unnoticed.
    "/harness/search-mobile-frame.tsx": "ambiguous-matches",
    # The shared action that turns a caught error into structure, and the panel that renders it.
    "/src/features/watchlist/actions.ts": "ambiguousMatch",
    "/src/features/suggest/AmbiguousMatches.tsx": "ambiguous-candidate",
    # The screen under test: it owns the sheet and the copy of the 409 it renders.
    "/src/layouts/mobile/SearchScreen.tsx": "downloadDisc",
}


@dataclass
class Result:
    label: str
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def _fetch(url: str, attempts: int = 3, timeout: float = 20.0) -> str | None:
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
    """Every marker present on disk AND in what the server serves right now — both sides, because a
    marker that has vanished from disk means THIS TOOL can no longer detect a stale server."""
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
            problems.append(f"{path}: does not contain {marker!r} — the dev server is serving a STALE module")
    return problems


# ---------------------------------------------------------------------------
# Assertions — pure functions of a probe + a request count, so `--selftest` can falsify them.
# ---------------------------------------------------------------------------


def assert_sheet_open(p: dict, before: int) -> list[str]:
    if not p.get("sheet"):
        return ["no sheet opened — the press must land somewhere the person can read"]
    return []


def assert_candidates(p: dict, before: int) -> list[str]:
    """The server's sentence AND both candidates, inside the open sheet."""
    problems: list[str] = []
    amb = p.get("ambiguous")
    if not amb:
        return ["no ambiguous panel — the 409's candidates did not reach the screen"]
    if SENTENCE not in (amb.get("text") or ""):
        problems.append(f"the panel does not carry the server's sentence ({amb.get('text')!r})")
    titles = [t.strip(" ·") for t in (amb.get("candidates") or [])]
    missing = [t for t in EXPECTED_CANDIDATES if not any(t in got for got in titles)]
    if missing:
        problems.append(f"the panel is missing {missing} (rendered: {titles})")
    if not (p.get("sheet") or "").strip():
        problems.append("the panel rendered OUTSIDE a sheet — the answer belongs where the press happened")
    return problems


def assert_drag_dismisses(p: dict, before: int) -> list[str]:
    """⚠ The other half of the arm-threshold fix: the gesture must still WORK.

    A pointer is armed and captured only after 8px of travel, so this is the measurement that the
    drag still follows the finger and still dismisses the sheet — without it, "taps reach buttons now"
    could just as easily mean "the sheet stopped being draggable", which the source cannot tell you.
    """
    problems: list[str] = []
    if p.get("sheet"):
        problems.append("a drag down the sheet did not dismiss it — the gesture no longer works")
    if (p.get("mediaCalls") or 0) != before:
        problems.append(
            f"the drag fired {p.get('mediaCalls')} request(s) — a drag over a control must never "
            "activate it (that is what the capture is for)"
        )
    return problems


def assert_no_pick_controls(p: dict, before: int) -> list[str]:
    """⚠ No button, link or role=button among the candidates: the server sends no id to re-request."""
    amb = p.get("ambiguous")
    if not amb:
        return ["no ambiguous panel to inspect"]
    controls = amb.get("controls")
    if controls:
        return [
            f"{controls} interactive control(s) rendered among the candidates — they carry no id, so a "
            "pick-one control cannot act (KNOWN_ISSUES §7 says read-only until the backend carries one)"
        ]
    return []


def assert_no_panel(p: dict, before: int) -> list[str]:
    """The negative case: a plain successful download renders NO panel and sends one request."""
    problems: list[str] = []
    if p.get("ambiguous"):
        problems.append("an ambiguous panel rendered for a request the server answered normally")
    if (p.get("mediaCalls") or 0) != 1:
        problems.append(f"{p.get('mediaCalls')} request(s) sent for one press — expected exactly 1")
    return problems


def assert_candidate_tap_is_inert(p: dict, before: int) -> list[str]:
    """Clicking a candidate must not fire another request nor pretend to be a choice."""
    if (p.get("mediaCalls") or 0) != before:
        return [
            f"clicking a candidate sent another request ({before} → {p.get('mediaCalls')}) — the list is "
            "read-only because there is nothing to re-request with"
        ]
    return []


def assert_narrow(p: dict, before: int) -> list[str]:
    problems: list[str] = []
    if p["scrollWidth"] > p["innerWidth"] + 1:
        problems.append(
            f"the document scrolls {p['scrollWidth'] - p['innerWidth']}px horizontally "
            f"({p['scrollWidth']} > {p['innerWidth']})"
        )
    if p.get("overflow"):
        problems.append(f"{p['overflow']} element(s) poke outside the viewport: {p.get('overflowEls')}")
    if not p.get("ambiguous"):
        problems.append("no ambiguous panel at 320px — the narrow case measured nothing")
    return problems


ASSERTIONS = {
    "sheet-open": assert_sheet_open,
    "candidates": assert_candidates,
    "no-pick-controls": assert_no_pick_controls,
    "no-panel": assert_no_panel,
    "inert": assert_candidate_tap_is_inert,
    "narrow": assert_narrow,
    "drag-dismiss": assert_drag_dismisses,
}

POSITIVE = ("sheet-open", "candidates", "no-pick-controls", "inert", "narrow", "drag-dismiss")
"""⚠ `no-panel` is NOT here: it asserts the ABSENCE of the panel, so it fails the same good probe the
positives pass. It is falsified by its own mutations instead — checking it against a good probe would
report the assertions as broken when they are simply describing the other scenario."""


# ---------------------------------------------------------------------------
# Driving the real screen.
# ---------------------------------------------------------------------------


def _ready(page, expect: str = "") -> None:
    """⚠ Readiness waits on the FIELD, not on the results: the results only exist after a query, so
    waiting for them here would turn "the screen did not render" into "the search never ran" — and
    a scenario that dies at the gate reports nothing about the thing under test."""
    page.wait_for_function("() => !!window.__probe", timeout=20_000)
    page.wait_for_selector("input[aria-label='Search movies, shows and people']", timeout=20_000)
    if expect:
        page.wait_for_selector(f'text={expect}', timeout=20_000)


def _open_search(page, text: str = "sholay") -> None:
    """Type into the screen's own field and wait for the discovery rows."""
    page.fill("input[aria-label='Search movies, shows and people']", text)
    page.wait_for_selector('[data-testid="discovery-action"]', timeout=20_000)


def _press_row_download(page, expect_sheet: bool = True) -> None:
    """The row pill that says Download (the second discovery row is already on the watchlist).

    ⚠ `expect_sheet=False` is the NEGATIVE scenario: a normal answer opens no sheet, so waiting for
    one there would report a timeout as "the scenario could not be driven" instead of asserting the
    thing under test.
    """
    page.get_by_role("button", name="Download", exact=True).first.click()
    if expect_sheet:
        page.wait_for_selector('[data-testid="sheet-panel"]', timeout=10_000)


def scenario_ambiguous(page) -> dict:
    _open_search(page)
    _press_row_download(page)
    page.wait_for_selector('[data-testid="ambiguous-matches"]', timeout=10_000)
    return page.evaluate("window.__probe()")


def scenario_no_panel(page) -> dict:
    _open_search(page)
    _press_row_download(page, expect_sheet=False)
    page.wait_for_timeout(400)
    return page.evaluate("window.__probe()")


def scenario_in_sheet(page) -> dict:
    """Open the title's sheet from the ROW BODY, then press Download inside it."""
    _open_search(page)
    page.locator('[data-testid="discovery-open"]').nth(1).click()
    page.wait_for_selector('[data-testid="sheet-panel"]', timeout=10_000)
    panel = page.locator('[data-testid="sheet-panel"]')
    panel.get_by_role("button", name="Download", exact=True).click()
    page.wait_for_selector('[data-testid="ambiguous-matches"]', timeout=10_000)
    return page.evaluate("window.__probe()")


def scenario_narrow(page) -> dict:
    _open_search(page)
    _press_row_download(page)
    page.wait_for_selector('[data-testid="ambiguous-matches"]', timeout=10_000)
    return page.evaluate("window.__probe()")


def scenario_drag(page) -> dict:
    """⚠ A drag down the sheet must STILL dismiss it, and must not press anything on the way.

    The arm threshold means the pointer is captured 8px into the gesture rather than on
    `pointerdown`; this is the measurement that the gesture it protects still works. The drag starts
    ON THE HANDLE and travels well past `DISMISS_FRACTION` of the sheet's height.
    """
    _open_search(page)
    page.locator('[data-testid="discovery-open"]').nth(1).click()
    page.wait_for_selector('[data-testid="sheet-panel"]', timeout=10_000)
    box = page.locator('[data-testid="sheet-panel"]').bounding_box()
    if not box:
        raise RuntimeError("the sheet has no box to drag")
    x = box["x"] + box["width"] / 2
    start_y = box["y"] + 14
    page.mouse.move(x, start_y)
    page.mouse.down()
    # Several steps, like a finger: one jump would test nothing about following the pointer.
    for step in range(1, 7):
        page.mouse.move(x, start_y + step * (box["height"] * 0.15))
        page.wait_for_timeout(16)
    page.mouse.up()
    page.wait_for_timeout(500)  # DISMISS_MS (180) + unmount
    return page.evaluate("window.__probe()")


def selftest() -> int:
    """Falsification: hand each assertion a probe that should fail it, and require it to go RED."""
    good = {
        "sheet": "Two titles matched — pick oneSholay1975The Sholay Girl2019This app cannot tell…",
        "ambiguous": {
            "text": f"{SENTENCE} · Sholay · The Sholay Girl",
            "candidates": ["Sholay1975", "The Sholay Girl2019"],
            "controls": 0,
            "h": 120,
        },
        "mediaCalls": 1,
        "scrollWidth": 390,
        "innerWidth": 390,
        "overflow": 0,
        "overflowEls": [],
    }
    if any(fn(good, 1) for name, fn in ASSERTIONS.items() if name in POSITIVE):
        print("❌ SELFTEST: the GOOD probe fails an assertion — the assertions are wrong, not the screen")
        for name, fn in ASSERTIONS.items():
            print(f"   {name}: {fn(good, 1)}")
        return 1

    # (assertion, label, probe, requests-sent-before-the-last-action). ⚠ Label and assertion are
    # separate on purpose: three mutations falsify `candidates` three different ways (absent, partial,
    # wrong sentence), and deriving the assertion from the label was how one of them silently ran the
    # wrong check in an earlier draft.
    mutations = [
        ("sheet-open", "sheet-open: no sheet", {**good, "sheet": None}, 1),
        ("candidates", "candidates: no panel", {**good, "ambiguous": None}, 1),
        (
            "candidates",
            "candidates: only one title",
            {**good, "ambiguous": {**good["ambiguous"], "candidates": ["Sholay1975"]}},
            1,
        ),
        (
            "candidates",
            "candidates: client's own sentence",
            {**good, "ambiguous": {**good["ambiguous"], "text": "Something failed"}},
            1,
        ),
        (
            "candidates",
            "candidates: panel outside a sheet",
            {**good, "ambiguous": {**good["ambiguous"]}, "sheet": None},
            1,
        ),
        (
            "no-pick-controls",
            "no-pick-controls: a button among the candidates",
            {**good, "ambiguous": {**good["ambiguous"], "controls": 2}},
            1,
        ),
        ("no-panel", "no-panel: a panel for a normal answer", {**good}, 1),
        ("no-panel", "no-panel: two requests for one press", {**good, "ambiguous": None, "mediaCalls": 2}, 1),
        ("inert", "inert: the candidate tap sent a request", {**good, "mediaCalls": 2}, 1),
        (
            "narrow",
            "narrow: 30px of horizontal scroll",
            {**good, "overflow": 1, "overflowEls": ["DIV.x"], "scrollWidth": 420},
            1,
        ),
    ]
    failures: list[str] = []
    for assertion, label, bad, before in mutations:
        problems = ASSERTIONS[assertion](bad, before)
        if not problems:
            failures.append(f"{label}: mutation NOT caught — this assertion cannot fail")
        else:
            print(f"✅ {label}: RED as required — {problems[0]}")
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
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--shots", default=None, help="directory to write one screenshot per scenario")
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

    scenarios = [
        ("A ambiguous", "?ambiguous=1", 390, 844, scenario_ambiguous,
         ("sheet-open", "candidates", "no-pick-controls")),
        ("B no panel", "?x=1", 390, 844, scenario_no_panel, ("no-panel",)),
        ("C in-sheet", "?ambiguous=1", 390, 844, scenario_in_sheet,
         ("sheet-open", "candidates", "no-pick-controls")),
        ("D narrow", "?ambiguous=1", 320, 568, scenario_narrow, ("narrow",)),
        ("E drag", "?ambiguous=1", 390, 844, scenario_drag, ("drag-dismiss",)),
    ]

    results: list[Result] = []
    print(f"phone suggest sheet · {args.base}{FRAME}")
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            for label, query, w, h, drive, names in scenarios:
                page = browser.new_page(viewport={"width": w, "height": h})
                errors: list[str] = []
                page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
                result = Result(label)
                try:
                    page.goto(f"{args.base}{FRAME}{query}", wait_until="load", timeout=30_000)
                    _ready(page)
                    p = drive(page)
                    for name in names:
                        for problem in ASSERTIONS[name](p, p.get("mediaCalls") or 0):
                            result.problems.append(f"[{name}] {problem}")
                    # ⚠ The last thing scenario A–D prove: a candidate is not a choice.
                    if "candidates" in names and p.get("ambiguous"):
                        before = p.get("mediaCalls") or 0
                        page.locator('[data-testid="ambiguous-candidate"]').first.click()
                        page.wait_for_timeout(250)
                        after = page.evaluate("window.__probe()")
                        for problem in ASSERTIONS["inert"](after, before):
                            result.problems.append(f"[inert] {problem}")
                    print(
                        f"{label:<12} sheet={bool(p.get('sheet'))!s:<5} "
                        f"candidates={(p.get('ambiguous') or {}).get('candidates')} "
                        f"controls={(p.get('ambiguous') or {}).get('controls')} "
                        f"mediaCalls={p.get('mediaCalls')}"
                    )
                    if shots:
                        page.screenshot(path=str(shots / f"suggest-{label.split()[0]}.png"), full_page=True)
                except Exception as exc:  # noqa: BLE001
                    result.problems.append(f"the scenario could not be driven: {exc!r}")
                finally:
                    page.close()
                if errors:
                    result.problems.extend(errors)
                results.append(result)
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
    print(f"\n{len(results) - failed}/{len(results)} scenarios passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
