#!/usr/bin/env python3
"""Progressive mounting, measured in a real browser — MOBILE_FIRST_UI_PLAN §11 (M3).

    python3 tools/check_library_mounting.py
    python3 tools/check_library_mounting.py --selftest
    python3 tools/check_library_mounting.py --shots /tmp/shots

**What it is for.** `LibraryFolderView` mapped every row of a folder, so the real Movies folder
(713 titles) put **22,240 nodes** into the DOM in ONE synchronous commit — CDP attributed the tap to
Script 2.4 s / `setAttribute` 814 ms, on EVERY visit, remembering nothing between them. The cure is
progressive mounting: a screenful first, the rest in idle steps.

⚠ **It is not virtualisation**, and this check is written so it cannot be mistaken for it: every row
must eventually be in the DOM, the page must keep its full height, and the LAST title must be
reachable by ordinary scrolling. What is forbidden is the ONE BIG COMMIT.

It drives the REAL `LibraryFolderView` through `harness/library-frame.html?folder=1&rows=713` (the
frame's own stub answers 713 synthetic titles shaped like the real rows) and reads a mutation trace
taken inside the page — `(ms, cards-in-DOM)` after every batch that changed the count:

  A. first_paint   the first batch must mount a SCREENFUL, not the folder
  B. chunk         no single batch may jump by more than that screenful either
  C. complete      the count must arrive at exactly the folder's size
  D. nothing_lost  the last title must be IN the DOM at the end
  E. reachable     after scrolling to the bottom, the last CARD must be in the viewport
  F. grows         a list longer than a screenful must arrive in MORE THAN ONE batch

⚠ **Every scenario gets a FRESH PAGE** (`echo "frame"`-style isolation, one browser per scenario):
this repo has already had eight tools report a false PASS because the frame stopped loading at the
eighth scenario in one Chromium (`ARCHITECTURE.md` §18.7) — `check_nav_access` still fails that way.

⚠ **The browser must be restarted after editing app source** — the vite watcher does not fire on this
mount, and an orphaned `:5199` has produced a false PASS here before. The freshness gate below reads
the served module and FAILS if it is stale, rather than trusting the port.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from playwright.sync_api import sync_playwright

DEFAULT_BASE = "http://localhost:5199"
REPO = Path(__file__).resolve().parent.parent
FRONTEND = REPO / "frontend"

#: ⚠ The two numbers this check is about, repeated ON PURPOSE as literals (reading them from the
#: app would make the check agree with any value, including a broken one — the `check_mobile_shell`
#: lesson). `FIRST_PAINT_CARDS` and `MOUNT_STEP` in `features/library/lib.ts`.
FIRST_PAINT = 48
CHUNK_LIMIT = FIRST_PAINT * 2
"""⚠ Twice the first paint, not once: React may commit the header/rails and the grid in two batches
within the same paint. The bug being caught is 713-in-one, so a bound of 96 catches it with room
for an honest first paint — while `chunk` still fails a 200-row jump."""

#: Every batch that changed the card count, read from inside the page.
PROBE = """
(() => {
  window.__trace = [];
  window.__cards = () => document.querySelectorAll('[data-testid="media-card"]').length;
  const record = () => {
    // ⚠ UNITS = grid cards + compact rows. The compact view renders `MediaListRow`, which carries
    // no `media-card` testid, so a probe counting only cards would report "nothing mounted" about a
    // list that is rendering perfectly (it did).
    const n = window.__cards() + document.querySelectorAll('[data-testid="compact-list"] > *').length;
    const last = window.__trace[window.__trace.length - 1];
    if (last && last.n === n) return;
    window.__trace.push({ t: Math.round(performance.now()), n });
  };
  new MutationObserver(record).observe(document, { childList: true, subtree: true });
  // ⚠ NOT `window.__probe` — `library-frame.tsx` already owns that name for its own (unrelated)
  // probe, and an init script is overwritten by the page. Two probes sharing one name is how this
  // check reported "no cards were ever observed" about a page that was rendering perfectly.
  window.__mountProbe = () => {
    const cards = [...document.querySelectorAll('[data-testid="media-card"]')];
    const last = cards[cards.length - 1];
    const rect = last ? last.getBoundingClientRect() : null;
    const rows = [...document.querySelectorAll('[data-testid="compact-list"] > *')];
    const lastRow = rows[rows.length - 1];
    const rowRect = lastRow ? lastRow.getBoundingClientRect() : null;
    return {
      trace: window.__trace,
      cards: cards.length,
      compactRows: rows.length,
      titles: cards.map((c) => (c.textContent || "").trim()).filter(Boolean),
      // ⚠ Falls back to the last COMPACT row: in the compact view there is no media-card at all, and
      // reading the title only from cards made the "is the last row mounted" assertion vacuous.
      lastTitle: ((last ? last.textContent : lastRow ? lastRow.textContent : "") || "").trim(),
      lastInViewport: rect ? rect.top < innerHeight && rect.bottom > 0 : false,
      lastRowInViewport: rowRect ? rowRect.top < innerHeight && rowRect.bottom > 0 : false,
      scrollHeight: document.documentElement.scrollHeight,
      innerHeight,
      errors: window.__errors || [],
    };
  };
  window.addEventListener("error", (e) => {
    (window.__errors = window.__errors || []).push(String(e.message).slice(0, 200));
  });
})();
"""


@dataclass
class Scenario:
    name: str
    query: str
    width: int
    height: int
    expect_cards: int
    expect_compact: int = 0
    #: Titles the frame's stub generates: `rows=713` → the last one is "Title 0713".
    last_title: str = "Title 0713"


PROBLEMS: list[str] = []


def problem(message: str) -> None:
    PROBLEMS.append(message)


def check(condition: bool, message: str) -> bool:
    if not condition:
        problem(message)
    return condition


# ---------------------------------------------------------------- the assertions
def assert_trace(sc: Scenario, state: dict) -> None:
    """The rules, as pure logic over a probe payload — so `--selftest` can feed it fake ones.

    ⚠ Split out from the browser code for exactly that reason: a check whose assertions only ever
    run against a page that passes cannot be falsified, and this repo has shipped that mistake.
    """
    trace = state.get("trace") or []
    raw = [int(step["n"]) for step in trace]
    # ⚠ `counts` drops the zero-count batches: React mounts the toolbar and the header before the
    # first card, so the trace legitimately opens with 0 and a "first commit" read off the raw list
    # would be the header, not the grid.
    counts = [n for n in raw if n > 0]
    cards = int(state.get("cards") or 0)

    check(bool(counts), f"{sc.name}: no cards were ever observed")
    if counts:
        check(counts[0] <= CHUNK_LIMIT,
              f"{sc.name}: the FIRST commit mounted {counts[0]} rows — a screenful is "
              f"{FIRST_PAINT}, and anything over {CHUNK_LIMIT} is the bug this phase exists to "
              f"remove (713 rows in one commit is what held the main thread for 1.7–2.0 s)")
        jumps = [counts[0]] + [counts[i] - counts[i - 1] for i in range(1, len(counts))]
        biggest = max(jumps) if jumps else 0
        check(biggest <= CHUNK_LIMIT,
              f"{sc.name}: one commit added {biggest} rows, over the {CHUNK_LIMIT} ceiling — "
              f"the list is being mounted in blocks that are too large to stay off the main thread")

    check(any(raw[i] < raw[i - 1] for i in range(1, len(raw))) is False,
          f"{sc.name}: the mounted count went DOWN mid-render ({raw}) — rows must never be "
          f"unmounted, or the page loses its height and its scroll position")

    check(cards == sc.expect_cards,
          f"{sc.name}: the DOM holds {cards} cards, expected {sc.expect_cards} — every row of the "
          f"folder must end up mounted (this is progressive mounting, NOT virtualisation)")
    if sc.expect_compact:
        rows = int(state.get("compactRows") or 0)
        check(rows == sc.expect_compact,
              f"{sc.name}: the compact list holds {rows} rows, expected {sc.expect_compact}")

    if sc.expect_cards > CHUNK_LIMIT or sc.expect_compact > CHUNK_LIMIT:
        check(len(counts) > 1,
              f"{sc.name}: the whole list arrived in ONE batch ({len(counts)}) — a list longer than "
              f"a screenful must grow in steps")

    title = str(state.get("lastTitle") or "")
    check(sc.last_title in title,
          f"{sc.name}: the LAST title of the folder is not in the DOM (found {title!r}) — the rows "
          f"past the first paint never mounted")

    check(bool(state.get("lastInViewport")) or bool(state.get("lastRowInViewport")),
          f"{sc.name}: after scrolling to the bottom the last row is NOT in the viewport — the "
          f"rows exist but the page cannot reach them")

    check(not state.get("errors"),
          f"{sc.name}: the page raised {state.get('errors')}")


# ---------------------------------------------------------------- browser driving
def served_module(url: str) -> str:
    """The module as the dev server serves it, or `__unreachable__ …`.

    ⚠ 15 s and a retry, because a vite that has just started answers the FIRST request for a module
    only after it has compiled the graph — a 10 s ceiling reported "not answering" about a server
    that was up and ready (the readiness line is in its log, not in this request).
    """
    last = ""
    for _ in range(3):
        try:
            with urllib.request.urlopen(url, timeout=15) as response:
                return response.read().decode("utf-8", "replace")
        except (urllib.error.URLError, OSError) as exc:
            last = str(exc)
            time.sleep(2)
    return f"__unreachable__ {last}"


def run_scenario(sc: Scenario, base: str, shots: str | None) -> dict:
    """One scenario, one fresh page, one fresh context — see the §18.7 note in the docstring."""
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        ctx = browser.new_context(viewport={"width": sc.width, "height": sc.height},
                                  device_scale_factor=1)
        ctx.add_init_script(PROBE)
        page = ctx.new_page()
        page.goto(f"{base}/harness/library-frame.html?{sc.query}", wait_until="domcontentloaded")
        # ⚠ Wait on UNITS (grid cards + compact rows), not on cards: the compact view renders no
        # `media-card` at all, so a card-based wait returned instantly and measured the list
        # mid-growth (it read 336 of 713 and looked like a stalled mount).
        units = max(sc.expect_cards, sc.expect_compact)
        try:
            page.wait_for_function(
                f"() => document.querySelectorAll('[data-testid=\"media-card\"]').length + "
                f"document.querySelectorAll('[data-testid=\"compact-list\"] > *').length >= {units}",
                timeout=20_000)
        except Exception:
            pass  # the assertion below reports what it actually found
        page.wait_for_timeout(400)
        page.evaluate("() => window.scrollTo(0, document.documentElement.scrollHeight)")
        page.wait_for_timeout(500)
        state = page.evaluate("() => window.__mountProbe()")
        if shots:
            Path(shots).mkdir(parents=True, exist_ok=True)
            page.screenshot(path=f"{shots}/{sc.name}.png", full_page=False)
        browser.close()
    return state


SCENARIOS = [
    Scenario("phone-390", "folder=1&rows=713", 390, 844, 713),
    Scenario("desktop-1440", "folder=1&rows=713", 1440, 900, 713),
    Scenario("phone-compact", "folder=1&rows=713&view=compact", 390, 844, 0, expect_compact=713),
    Scenario("short-30", "folder=1&rows=30", 390, 844, 30, last_title="Title 0030"),
]


# ---------------------------------------------------------------- falsification
def selftest() -> int:
    """⚠ Each assertion is fed a probe it MUST reject, plus one it must accept.

    The failure shapes are the ones the app has actually produced or plausibly could: the 713-in-one
    commit (the real bug), a stalled list, a list that stops short, rows that were unmounted, and a
    last row that exists but cannot be reached.
    """
    cases: list[tuple[str, Scenario, dict, bool]] = []
    sc = Scenario("fake-713", "folder=1&rows=713", 390, 844, 713)

    def trace(*counts: int) -> list[dict]:
        return [{"t": i * 10, "n": n} for i, n in enumerate(counts)]

    #: ⚠ The app's OWN growth pattern: `MOUNT_STEP` of 48 per idle step, then the final clamp to the
    #: list. Written out rather than derived so this fixture cannot quietly agree with a broken rule
    #: — and the first draft of this line was 48→96→144→240…, whose 144-card jump the earlier
    #: assertion correctly REJECTED, which is how the ceiling earned its keep.
    grown = [48, 96, 144, 192, 240, 288, 336, 384, 432, 480, 528, 576, 624, 672, 713]

    cases.append(("a screenful first, then steps — ACCEPT",
                  sc, {"trace": trace(*grown), "cards": 713, "lastTitle": "Title 0713",
                       "lastInViewport": True}, True))
    cases.append(("713 in ONE commit — REJECT (the real bug)",
                  sc, {"trace": trace(713), "cards": 713, "lastTitle": "Title 0713",
                       "lastInViewport": True}, False))
    cases.append(("a 200-card jump — REJECT",
                  sc, {"trace": trace(48, 248, 713), "cards": 713, "lastTitle": "Title 0713",
                       "lastInViewport": True}, False))
    cases.append(("stalled at 400 — REJECT",
                  sc, {"trace": trace(48, 96, 400), "cards": 400, "lastTitle": "Title 0400",
                       "lastInViewport": True}, False))
    cases.append(("rows UNMOUNTED mid-render — REJECT",
                  sc, {"trace": trace(48, 96, 48, 713), "cards": 713, "lastTitle": "Title 0713",
                       "lastInViewport": True}, False))
    cases.append(("last title missing though the count is right — REJECT",
                  sc, {"trace": trace(*grown), "cards": 713, "lastTitle": "Title 0400",
                       "lastInViewport": True}, False))
    cases.append(("mounted but unreachable — REJECT",
                  sc, {"trace": trace(*grown), "cards": 713, "lastTitle": "Title 0713",
                       "lastInViewport": False}, False))
    cases.append(("a page error — REJECT",
                  sc, {"trace": trace(*grown), "cards": 713, "lastTitle": "Title 0713",
                       "lastInViewport": True, "errors": ["boom"]}, False))
    compact = Scenario("fake-compact", "folder=1&rows=713&view=compact", 390, 844, 713,
                       expect_compact=713)
    cases.append(("compact list whole — ACCEPT",
                  compact, {"trace": trace(*grown), "cards": 713, "compactRows": 713,
                            "lastTitle": "Title 0713", "lastRowInViewport": True}, True))
    cases.append(("compact list short — REJECT",
                  compact, {"trace": trace(*grown), "cards": 713, "compactRows": 400,
                            "lastTitle": "Title 0713", "lastRowInViewport": True}, False))
    short = Scenario("fake-30", "folder=1&rows=30", 390, 844, 30, last_title="Title 0030")
    cases.append(("a short folder, one batch — ACCEPT",
                  short, {"trace": trace(30), "cards": 30, "lastTitle": "Title 0030",
                          "lastInViewport": True}, True))

    failures: list[str] = []
    for label, scenario, state, should_pass in cases:
        PROBLEMS.clear()
        assert_trace(scenario, state)
        passed = not PROBLEMS
        mark = "ok  " if passed == should_pass else "WRONG"
        if passed != should_pass:
            failures.append(f"{label}: expected {'PASS' if should_pass else 'FAIL'}, got "
                            f"{'PASS' if passed else 'FAIL'} ({PROBLEMS[:2]})")
        print(f"  {mark}  {label}")
    PROBLEMS.clear()
    print(f"\nselftest: {len(cases) - len(failures)}/{len(cases)} probes answered as they must")
    for line in failures:
        print(f"  !! {line}")
    return 1 if failures else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--shots", help="directory for one screenshot per scenario")
    ap.add_argument("--selftest", action="store_true", help="falsify the assertions, no browser")
    ap.add_argument("--json", metavar="PATH", help="write the raw traces here")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    # ⚠ Freshness, before any result is believed: the served module must be the one on disk.
    source = FRONTEND / "src/features/library/useProgressiveMount.ts"
    if not source.exists():
        print(f"!! {source} is missing — this check describes a build that is not here")
        return 2
    served = served_module(f"{args.base}/src/features/library/useProgressiveMount.ts")
    if "__unreachable__" in served:
        print(f"!! the dev server at {args.base} is not answering ({served.split(' ', 1)[-1][:80]})")
        print("   start it: cd frontend && npx vite --port 5199 --strictPort")
        return 2
    if "mountedCount" not in served:
        print("!! the dev server is serving a STALE useProgressiveMount — kill the vite holding "
              ":5199 and start it again (its watcher does not fire on this mount)")
        return 2

    print(f"checking progressive mounting against {args.base}\n")
    payload: dict[str, dict] = {}
    for sc in SCENARIOS:
        state = run_scenario(sc, args.base, args.shots)
        payload[sc.name] = state
        counts_raw = [int(step["n"]) for step in (state.get("trace") or [])]
        non_zero = [n for n in counts_raw if n > 0]
        print(f"  {sc.name:<15} viewport {sc.width}×{sc.height} · "
              f"first commit {non_zero[0] if non_zero else '-'} · batches {len(non_zero)} · "
              f"final {state.get('cards')} cards / {state.get('compactRows')} rows · "
              f"scrollHeight {state.get('scrollHeight')} · last \"{state.get('lastTitle')}\"")
        assert_trace(sc, state)

    if args.json:
        Path(args.json).write_text(json.dumps(payload, indent=2))
        print(f"\nraw traces: {args.json}")

    print()
    if PROBLEMS:
        for message in PROBLEMS:
            print(f"FAIL: {message}")
        return 1
    print("PASS — the folder mounts a screenful first and grows the rest, every row ends up in the "
          "DOM, and the last one is still reachable by scrolling")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
