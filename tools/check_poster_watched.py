#!/usr/bin/env python3
"""The poster's watched surface — ONE fact, ONE owner (his rule, 2026-09-18).

His report (`KNOWN_ISSUES` §2): *"on the poster when you click the right tick button (i think its for
watched) there are two green ticks and then the button inside (details page) watched button becomes
redundant"*. The card drew the same fact twice — the tick MARKER on the art and a green TOGGLE in the
bottom row, both driven by `item.played`.

His rule: **the details view OWNS the watched control; the poster only REFLECTS status.** So this
checks the rendered SHAPE, because the defect was a duplicate ON SCREEN and a props-level test would
have been satisfied by the pair:

  A  the frame really rendered — three cards, art and a ⋯ trigger on each (else every later
     assertion is vacuous: "no toggle" is trivially true of a blank page)
  B  a PLAYED card paints exactly ONE watched indicator — the report's "two green ticks"
  C  NO card paints a watched CONTROL at all (`Mark as watched` / `Mark as unplayed`)
  D  the ⋯ menu of a played card offers no watched verb, and still offers Replay + View details —
     removing the toggle must not leave the action unreachable BY ACCIDENT
  E  an UNPLAYED card shows no marker — the marker follows `item.played`, it is not always drawn
  F  the surviving marker sits INSIDE the artwork (status on the poster), not in the action row
  G  the ⋯ trigger is at the row's RIGHT edge — the row lost its left-hand child, so
     `justify-between` would silently move the menu to the left

Run the dev server first (see frontend/harness/README.md):

    cd frontend && npx vite --port 5199 --strictPort
    python3 tools/check_poster_watched.py [--shots DIR] [--base URL]
    python3 tools/check_poster_watched.py --expect-broken   # falsification direction

⚠ `--expect-broken` requires the WATCHED TOGGLE TO BE PRESENT in `MediaCard.tsx` (i.e. run it against
the code as it was before this rule landed). It is a real falsification only if the source still carries
the defect — see the README's lesson about checks that cannot fail.

Exit codes: 0 = PASS · 1 = a check FAILED (or the falsification produced none) · 2 = the frame could
not be measured at all.
"""
from __future__ import annotations

import argparse
import sys

from playwright.sync_api import Page, sync_playwright

PROBLEMS: list[str] = []

#: The ⋯ trigger's right edge must be within this many px of the art's right edge (G). The row is
#: `inset-x-2`, so 8px is the intended inset and the defect is the art's whole width (~176px).
TRIGGER_RIGHT_TOL = 12.0

#: The two verbs the removed control carried. Finding either one is a FAIL.
WATCH_VERBS = ("Mark as watched", "Mark as unplayed")


def problem(message: str) -> None:
    PROBLEMS.append(message)
    print(f"  FAIL: {message}")


def check(condition: bool, message: str) -> None:
    if not condition:
        problem(message)


def run(page: Page, base: str, shots: str) -> None:
    print("A — the frame rendered the real cards")
    page.goto(f"{base}/harness/poster-watched-frame.html", wait_until="networkidle")
    page.wait_for_timeout(400)
    probe = page.evaluate("window.__probe()")
    cards = probe["perCard"]
    check(probe["cards"] == 3,
          f"A: three cards must render — got {probe['cards']}; every assertion below is about a "
          "surface that is not on screen")
    if probe["cards"] != 3:
        return
    for i, card in enumerate(cards):
        check(card["hasArt"], f"A: card {i} ({card['title']!r}) has no poster art element")
        check(card["hasMenuTrigger"],
              f"A: card {i} ({card['title']!r}) has no ⋯ trigger — the watched control was removed, "
              "so a card with no menu would have NO actions at all")
    if shots:
        page.screenshot(path=f"{shots}/poster-watched.png", full_page=True)

    print("B/E/F — the marker: one per played card, none on an unplayed one, on the ART")
    played = [c for c in cards if c["title"] in ("A Played Film", "A Played Series")]
    unplayed = [c for c in cards if c["title"] == "An Unwatched Film"]
    check(len(played) == 2 and len(unplayed) == 1,
          f"B: the fixtures must be two played cards and one unplayed — got {len(played)} played, "
          f"{len(unplayed)} unplayed (the frame's items changed?)")
    for card in played:
        # ⚠ THE REPORT'S OWN COUNT, first: "two green ticks" is markers + controls on one card. B
        # measures the marker alone, C the control — and the falsification run showed B passing on the
        # pre-fix source (the old toggle was labelled `Mark as unplayed`, not `Watched`, so it never
        # counted as a marker). This is the assertion that fails either way round.
        check(card["markers"] + card["toggles"] == 1,
              f"B: {card['title']!r} draws the watched fact {card['markers'] + card['toggles']} "
              f"time(s) — {card['markers']} marker(s) {card['markerLabels']} + {card['toggles']} "
              f"control(s) {card['toggleLabels']}. His report is exactly this: TWO green ticks on one "
              "poster. One fact, one owner.")
        check(card["markers"] == 1,
              f"B: {card['title']!r} shows {card['markers']} watched indicator(s) — the report is "
              f"TWO green ticks; exactly one marker may remain (labels: {card['markerLabels']})")
        check(card["markerInsideArt"],
              f"F: {card['title']!r}'s marker is NOT inside the artwork — a marker outside the art is "
              "a control in the action row, which is the surface his rule took the control off")
    for card in unplayed:
        check(card["markers"] == 0,
              f"E: {card['title']!r} is UNPLAYED but shows {card['markers']} marker(s) — the marker "
              "must follow `item.played`, or it is decoration rather than status")

    print("C — no card offers the watched control any more")
    for card in cards:
        check(card["toggles"] == 0,
              f"C: {card['title']!r} still renders a watched CONTROL ({card['toggleLabels']}) — the "
              "details view owns that control; the poster only reflects it")

    print("D — the ⋯ menu: no watched verb, and the actions that remain are reachable")
    menu = page.evaluate("window.__openMenu(0)")
    check(menu.get("open"), f"D: card 0's ⋯ menu did not open ({menu}) — nothing below is measured")
    items = menu.get("items") or []
    for verb in WATCH_VERBS:
        check(verb not in items,
              f"D: the ⋯ menu still offers {verb!r} — that is the SECOND surface for one fact: {items}")
    check("View details" in items,
          f"D: the ⋯ menu lost 'View details' — it exists, so its absence here is a different bug: {items}")
    check(any(i in ("Play", "Replay", "Episodes") for i in items),
          f"D: the ⋯ menu offers no play verb at all: {items}")

    unplayed_menu = page.evaluate("window.__openMenu(1)")
    u_items = unplayed_menu.get("items") or []
    check(unplayed_menu.get("open") and u_items,
          f"D: the UNPLAYED card's ⋯ menu is empty or did not open ({unplayed_menu}) — the menu is "
          "built from the item, so an unplayed title must still offer Play + View details")
    check("Mark as watched" not in u_items,
          f"D: the unplayed card's ⋯ menu offers 'Mark as watched': {u_items}")

    print("G — the ⋯ trigger is right-aligned in its row")
    for card in cards:
        gap = card["menuTriggerRightGap"]
        check(gap is not None and 0 <= gap <= TRIGGER_RIGHT_TOL,
              f"G: {card['title']!r}'s ⋯ trigger sits {gap}px from the art's right edge (tolerance "
              f"{TRIGGER_RIGHT_TOL}px) — the row lost its left-hand child, so `justify-between` "
              "silently moves the menu to the LEFT")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:5199")
    ap.add_argument("--shots", default="")
    ap.add_argument("--expect-broken", action="store_true",
                    help="falsification: require the checks to FAIL (the watched toggle must still be "
                         "in MediaCard.tsx for this to mean anything)")
    args = ap.parse_args()

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900}, device_scale_factor=2)
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        try:
            run(page, args.base, args.shots)
        except Exception as exc:  # noqa: BLE001 — a frame that cannot be measured is exit 2
            print(f"\nthe frame could not be measured: {type(exc).__name__}: {exc}")
            return 2
        if errors:
            check(False, f"page errors: {errors}")
        browser.close()

    if args.expect_broken:
        if not PROBLEMS:
            print("\nFALSIFICATION FAILED: every check passed against the source that still carries the "
                  "duplicate watched control — the check cannot tell the fix from the bug")
            return 1
        print(f"\nOK (falsified as expected): {len(PROBLEMS)} problem(s) with the fix absent")
        return 0

    if PROBLEMS:
        print(f"\n{len(PROBLEMS)} problem(s)")
        return 1
    print("\nOK: one watched indicator per played poster, no watched control on a poster, and the ⋯ "
          "menu carries no watched verb")
    return 0


if __name__ == "__main__":
    sys.exit(main())
