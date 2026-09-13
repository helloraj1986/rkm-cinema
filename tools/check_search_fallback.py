#!/usr/bin/env python3
"""Search fallback check — the external "not in your library" section must actually render.

His third report (2026-09-13): searching **"sholay"** returned the one library row that happens to
contain the string and **no external section at all**, so a famous film looked like it did not exist.

The backend half of that cause (a gate that suppressed the external search entirely) is pinned by
`backend/tests/test_global_search.py`. THIS check pins the other half, which no backend test can see:

  ⚠ the UI kept its OWN copy of the gate — `showDiscovery` required `!data.strong_match` — so even
  with the server sending rows, the frontend could hide every one of them. Two copies of one rule is
  the same drift that produced bug 2 (two hand-rolled button strings), and it is why this is a browser
  check: what must hold is what the SERVER says versus what the SCREEN does.

The frame sends the server's real shape for his query (`?strong=1`): `strong_match: true`
(an exact match of a DIFFERENT owned title) **and** discovery rows — exactly the combination the old
UI threw away.

WHAT IS ASSERTED

  A  the overlay rendered: the search call answered and all three rows are on screen (1 owned + 2
     external) — without this, "the section is missing" would pass on an empty page.
  B  the "Discover · not in your library" group IS rendered while `strong_match` is true — the
     assertion the old double gate fails.
  C  library FIRST: the owned row is the first result and keeps its owned actions (Resume).
  D  each external row is actionable and marked as not-owned ("not in your library", or the
     "In watchlist" chip when it already is), and never carries the owned Resume/Details pair.
  E  clicking an external row opens the detail modal for THAT title (the Suggest-card contract) —
     a section that renders but does nothing would be a worse trade than the missing rows.
  F  `?tmdbkey=0` (capability off): no group, no external rows, and the footer SAYS so — the honest
     reason, not a silently empty search.

Run the dev server first (see frontend/harness/README.md):

    cd frontend && npx vite --port 5199 --strictPort
    python3 tools/check_search_fallback.py [--shots DIR]
    python3 tools/check_search_fallback.py --expect-broken     # falsification direction
"""
from __future__ import annotations

import argparse
import sys

from playwright.sync_api import Page, sync_playwright

PROBLEMS: list[str] = []

DISCOVER_LABEL = "Discover"

#: The primary actions that only make sense for a row the library HAS (search/lib.ts `actionLabel`).
#: An external row offering one of these would promise playback of something he does not own.
OWNED_PRIMARY_ACTIONS = {
    "Resume", "Watch Now", "Watch Again", "Continue Watching", "Play Next Episode",
}


def problem(message: str) -> None:
    PROBLEMS.append(message)
    print(f"  FAIL: {message}")


def check(condition: bool, message: str) -> None:
    if not condition:
        problem(message)


def open_overlay(page: Page, base: str, query: str, shots: str, name: str, min_rows: int = 1) -> dict | None:
    """Load the frame, type the query, and wait for the answer to be RENDERED.

    ⚠ Readiness waits on the OWNED row (`min_rows=1`), never on the whole expected row set: waiting
    for the external rows would make the run die here — "the frame did not render" — instead of
    failing the assertion that says WHY they are missing, which is precisely the defect under test.
    """
    page.goto(f"{base}/harness/search-frame.html?{query}", wait_until="networkidle")
    page.fill('input[type="search"]', "sholay")
    try:
        page.wait_for_function(
            f"() => (window.__probe().searchCalls || []).length > 0 && window.__probe().rowCount >= {min_rows}",
            timeout=15000,
        )
    except Exception:
        problem(f"{name}: the overlay never rendered even {min_rows} row(s) — the frame did not "
                f"render, so every assertion below would be vacuous")
        return None
    page.wait_for_timeout(300)
    probe = page.evaluate("window.__probe()")
    if shots:
        try:
            page.screenshot(path=f"{shots}/search-{name}.png")
        except Exception as exc:  # noqa: BLE001 — evidence is optional, the assertion is not
            print(f"  NOTE: could not capture shots: {exc}")
    return probe


def scenario_a_owned_and_external_render(page: Page, base: str, shots: str) -> None:
    print("A–E — his query: the owned row AND the external section, on screen, together")
    probe = open_overlay(page, base, "strong=1", shots, "external")
    if probe is None:
        return

    # A — the frame really held his library's own row (not an empty page).
    check(any("Sholay — Special Ops" in r["text"] for r in probe["rows"]),
          f"A: the library's own row must be rendered; got {[r['text'][:40] for r in probe['rows']]}")

    # B — ⚠ THE assertion: strong_match is true and the external rows are still there.
    check(probe["rowCount"] == 3,
          f"B: expected 1 owned row + 2 external rows on screen, got {probe['rowCount']} — the server "
          f"sent all three; the UI (or its own copy of the server's gate) dropped "
          f"{3 - probe['rowCount']}")
    check(any(DISCOVER_LABEL in g for g in probe["groupLabels"]),
          f"B: the external group must render while `strong_match` is true — the UI showed groups "
          f"{probe['groupLabels']!r}. A second copy of the server's gate is what hid these rows before")

    # C — library first, and the owned row keeps its owned actions.
    first = probe["rows"][0]["text"] if probe["rows"] else ""
    check("Sholay — Special Ops" in first,
          f"C: the OWNED row must come first (owned content is the more actionable answer); the "
          f"first row was {first[:60]!r}")
    check(probe["rows"] and probe["rows"][0]["hasOwnedActions"],
          f"C: the owned row must keep its own actions; got {probe['rows'][0]['actionLabels']}")

    # D — every external row: actionable, marked, and never given an OWNED-only action.
    # ⚠ His report suggested "no Resume/Details buttons" on external rows. Details stays ON PURPOSE:
    # on an unowned row it opens that title's metadata modal (the same destination as clicking the
    # row), not the owned item's page — so the distinction that matters is the PRIMARY action, which
    # is what this asserts (and what tells him why the row is on the list at all).
    external = [r for r in probe["rows"] if "Sholay — Special Ops" not in r["text"]]
    check(len(external) == 2, f"D: expected 2 external rows, got {len(external)}")
    for row in external:
        labels = " ".join(row["actionLabels"])
        check(any(k in labels for k in ("Add to watchlist", "Download")),
              f"D: external row {row['text'][:40]!r} must offer Add-to-watchlist/Download, got "
              f"{row['actionLabels']}")
        owned_only = [a for a in row["actionLabels"] if a in OWNED_PRIMARY_ACTIONS]
        check(not owned_only,
              f"D: an unowned row must not offer an OWNED action ({owned_only}) — those resume or "
              f"open something he does not have; got {row['actionLabels']}")
        check(("not in your library" in row["text"]) or ("In watchlist" in row["text"]),
              f"D: external row {row['text'][:40]!r} must be marked as not owned (or already on the "
              f"watchlist) — the marker is what tells him why it is on the list")
    print(f"  A/B/C/D  {len(probe['rows'])} rows, groups {probe['groupLabels']!r}, "
          f"owned first, external rows actionable")

    # E — the external row must DO something: the Suggest-style detail modal for THAT title.
    # ⚠ Guarded: with the rows missing (the defect) a bare click would raise and abort the run,
    # losing every problem already recorded above.
    if probe["rowCount"] < 2:
        check(False, "E: there is no external row to click, so the section's own action is untested")
        return
    page.locator('[role="option"]').nth(1).click()
    page.wait_for_timeout(600)
    after = page.evaluate("window.__probe()")
    check(bool(after["detailCalls"]),
          f"E: clicking an external row must fetch its detail (the modal's own call); calls were "
          f"{[c['url'] for c in after['calls']]}")
    check(after["dialog"] is not None and "Sholay" in (after["dialog"] or {}).get("text", ""),
          f"E: the detail modal must open for the row he clicked, got {after['dialog']}")
    if after["dialog"]:
        print(f"  E  the modal opened: {after['dialog']['text'][:60]!r}")


def scenario_f_capability_off(page: Page, base: str, shots: str) -> None:
    print("F — no metadata key: no group, no rows, and the reason is stated")
    probe = open_overlay(page, base, "tmdbkey=0", shots, "no-key")
    if probe is None:
        return
    check(not any(DISCOVER_LABEL in g for g in probe["groupLabels"]),
          f"F: with no metadata key there are no external rows, so the group must not render "
          f"(groups {probe['groupLabels']!r})")
    check("TMDB discovery off" in probe["body"],
          "F: the overlay must say that discovery is off — a silently smaller answer reads as broken")
    if not PROBLEMS:
        print("  F  the group is absent and the footer explains why")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:5199")
    ap.add_argument("--shots", default="")
    ap.add_argument("--expect-broken", action="store_true",
                    help="falsification: require the checks to FAIL (run against the unfixed source)")
    args = ap.parse_args()

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900}, device_scale_factor=2)
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        scenario_a_owned_and_external_render(page, args.base, args.shots)
        page.goto("about:blank")
        scenario_f_capability_off(page, args.base, args.shots)

        if errors:
            check(False, f"page errors: {errors}")
        browser.close()

    if args.expect_broken:
        if not PROBLEMS:
            print("\nFALSIFICATION FAILED: every check passed against source that still carries the "
                  "defect — the check cannot tell the fix from the bug")
            return 1
        print(f"\nOK (falsified as expected): {len(PROBLEMS)} problem(s) with the fix absent")
        return 0

    if PROBLEMS:
        print(f"\n{len(PROBLEMS)} problem(s)")
        return 1
    print("\nOK: the external section renders beside the library row, is actionable, and is explained "
          "when the capability is off")
    return 0


if __name__ == "__main__":
    sys.exit(main())
