#!/usr/bin/env python3
"""Subtitle-panel DOM check: what the picker actually RENDERS (Phase 4).

`tools/measure_player_layout.py` proves geometry; this proves CONTENT. It opens the
real <Player> in the layout harness, opens the settings panel, asks for the
OpenSubtitles rows, and prints the subtitles section's text — so a label, an active
marker or a usage count that fails to render is visible as text rather than assumed.

Run (sandbox):  cd frontend && npx vite --port 5199 --strictPort &
                python3 tools/check_subtitle_panel.py [--shots DIR]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

GEAR = 'button[aria-label="Settings"]'
PANEL = "section:has-text('Subtitles')"
SEARCH = "button:has-text('Search OpenSubtitles')"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:5199")
    ap.add_argument("--shots", default="")
    ap.add_argument("--fail-search", action="store_true",
                    help="make the ONLINE search fail and assert the panel still works")
    args = ap.parse_args()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = browser.new_page(viewport={"width": 1366, "height": 768}, device_scale_factor=1)
        query = "kind=series" + ("&failSearch=1" if args.fail_search else "")
        page.goto(f"{args.base}/harness/player-frame.html?{query}", wait_until="networkidle")
        page.wait_for_timeout(700)

        # open the settings overlay (the picker lives there)
        page.click(GEAR)
        page.wait_for_timeout(400)
        before = page.locator(PANEL).first.inner_text().strip()
        print("=== subtitles section, before searching ===")
        print(before)

        # the search is on demand — nothing may have been fetched yet
        asked = page.evaluate(
            "() => (window.__subtitleSearchCalls ?? 0)")
        print(f"\nsubtitle-search calls before asking: {asked}")

        page.click(SEARCH)
        page.wait_for_timeout(700)
        after = page.locator(PANEL).first.inner_text().strip()
        print("\n=== subtitles section, after searching ===")
        print(after)

        state = page.evaluate(
            """() => {
              const rows = [...document.querySelectorAll('button[aria-pressed]')].map((b) => ({
                label: b.innerText.trim().replace(/\\s+/g, ' '),
                pressed: b.getAttribute('aria-pressed'),
              }));
              return {
                rows,
                searchCalls: window.__subtitleSearchCalls ?? null,
                notice: (document.querySelector('[role="status"]') || {}).innerText || "",
              };
            }"""
        )
        print("\n=== rendered rows (aria-pressed = active) ===")
        print(json.dumps(state, indent=2))

        # ---- the reported bug (live 2026-09-12): the row the user CLICKED must be the
        # ---- one that shows the round box, and only that row.
        chosen = [r for r in state["rows"] if r["pressed"] == "true"
                  and "OpenSubtitles" in r["label"]]
        problems = []

        if args.fail_search:
            # Criterion 10 end to end: a dead vendor must not cost the user their OWN
            # subtitles. The item's tracks are still listed, the notice explains the
            # failure, and nothing crashed.
            labels = [r["label"] for r in state["rows"]]
            if not any("English" in l for l in labels):
                problems.append("the item's own subtitle tracks vanished when search failed")
            if "Off" not in labels:
                problems.append("the Off row vanished when search failed")
            if any("OpenSubtitles" in l for l in labels):
                problems.append("remote rows were listed even though the search failed")
            print(f"\nnotice after the failed search: {state['notice']!r}")
            if problems:
                print("FAIL: " + "; ".join(problems))
                return 1
            print("OK: the search failed; the item's own subtitles are still listable, "
                  "the Off row survives, and the failure is explained in the notice.")
            return 0
        if len(chosen) != 1:
            problems.append(f"expected exactly ONE ticked OpenSubtitles row, got "
                            f"{len(chosen)}: {[r['label'] for r in chosen]}")
        elif "Harness.Release.1080p" not in chosen[0]["label"]:
            problems.append(f"the ticked row is not the chosen result: {chosen[0]['label']}")
        if any("SUBRIP - External" in r["label"] and r["pressed"] == "true"
               for r in state["rows"]):
            problems.append("the delivered local track is ticked as well — two selections")
        print(f"\nticked result rows: {len(chosen)}")
        if problems:
            print("FAIL: " + "; ".join(problems))
            return 1
        print("OK: exactly one row is ticked, and it is the OpenSubtitles result chosen.")

        if args.shots:
            Path(args.shots).mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(Path(args.shots) / "subtitle-panel-laptop.png"))
            phone = browser.new_page(viewport={"width": 390, "height": 844},
                                     device_scale_factor=3, is_mobile=True, has_touch=True)
            phone.goto(f"{args.base}/harness/player-frame.html?kind=movie",
                       wait_until="networkidle")
            phone.wait_for_timeout(700)
            phone.click(GEAR)
            phone.wait_for_timeout(400)
            phone.screenshot(path=str(Path(args.shots) / "subtitle-panel-phone.png"))
            print(f"\nshots written to {args.shots}")

        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
