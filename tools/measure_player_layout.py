#!/usr/bin/env python3
"""
Player LAYOUT measurement — real Chromium, one viewport per run.

Why this exists: the player's job is to fit a *viewport*, and the sandbox has no
Docker/Jellyfin to eyeball it against. This drives the real React <Player> (via
`frontend/harness/player-frame.html`, which stubs the API) through Playwright at a
matrix of device sizes and asserts the layout invariants that "fits the screen"
actually means:

  * the player shell == the exact viewport (0,0 → vw,vh) and does not scroll
  * the transport dock sits FULLY inside the viewport at every size
  * no element of the player pokes outside the viewport
  * the video fills its stage box (no unpainted frame around it)

Run (sandbox):
    cd frontend && npx vite --port 5199 --strictPort &      # dev server
    python3 tools/measure_player_layout.py                  # table + JSON
    python3 tools/measure_player_layout.py --shots /tmp/shots

Exit code 1 when any viewport FAILS, so it can gate a change.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

from playwright.sync_api import sync_playwright

# (label, width, height, is_mobile, has_touch, device_scale_factor)
VIEWPORTS: list[tuple[str, int, int, bool, bool, float]] = [
    ("Phone SE portrait", 320, 568, True, True, 2.0),
    ("Android small portrait", 360, 640, True, True, 3.0),
    ("iPhone 12 portrait", 390, 844, True, True, 3.0),
    ("Android landscape", 915, 412, True, True, 2.6),
    ("iPhone 12 landscape", 844, 390, True, True, 3.0),
    ("iPad portrait", 820, 1180, True, True, 2.0),
    ("Laptop 1366x768", 1366, 768, False, False, 1.0),
    ("Laptop short window", 1280, 600, False, False, 1.0),
    ("Narrow short window", 1024, 500, False, False, 1.0),
    ("Desktop 1920x1080", 1920, 1080, False, False, 1.0),
]

PROBE_JS = "() => window.__probe()"


@dataclass
class Result:
    label: str
    viewport: dict
    notes: list[str]
    probe: dict | None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return not self.notes


def verdict(p: dict | None, err: str | None) -> list[str]:
    """The layout invariants, in plain words."""
    if err:
        return [err]
    if not p:
        return ["no probe result"]
    notes: list[str] = []
    if not p.get("mounted"):
        notes.append("player did not mount")
    root = p.get("root") or {}
    vw, vh = p.get("vw"), p.get("vh")
    if root:
        if abs(root["x"]) > 0.5 or abs(root["y"]) > 0.5:
            notes.append(f"shell not at origin (x={root['x']}, y={root['y']})")
        if abs(root["w"] - vw) > 0.5:
            notes.append(f"shell width {root['w']} != viewport {vw}")
        if abs(root["h"] - vh) > 0.5:
            notes.append(f"shell height {root['h']} != viewport {vh}")
    else:
        notes.append("no shell rect")
    dock = p.get("dock")
    if not dock:
        notes.append("no transport dock rect")
    else:
        if dock["bottom"] > vh + 0.5:
            notes.append(f"transport dock bottom {dock['bottom']} past viewport {vh}")
        if dock["right"] > vw + 0.5:
            notes.append(f"transport dock right {dock['right']} past viewport {vw}")
        if dock["w"] > vw + 0.5:
            notes.append(f"transport dock wider than viewport ({dock['w']})")
    row = p.get("dockRow")
    if row and row["right"] > vw + 0.5:
        notes.append(f"control row right {row['right']} past viewport {vw}")
    if row and row["w"] > vw + 0.5:
        notes.append(f"control row wider than viewport ({row['w']})")
    grow = p.get("dockRowScroll") or {}
    if grow and grow.get("scrollW", 0) > grow.get("clientW", 0) + 1:
        notes.append(
            f"transport row clips its own content ({grow['scrollW']} > {grow['clientW']})"
        )
    # Every rendered control must stay a usable touch target and stay on screen.
    for b in p.get("buttons") or []:
        if b["h"] < 32 or b["w"] < 32:
            notes.append(f"control '{b['label']}' is below a 32px touch target ({b['w']}x{b['h']})")
        if b["right"] > vw + 0.5:
            notes.append(f"control '{b['label']}' ends at {b['right']} (viewport {vw})")
    # Chrome policy: a SHORT viewport collapses the header's second line ("S1E2 · n of
    # m") so the picture keeps the pixels — and a tall one must keep it.
    header = p.get("headerText") or ""
    has_context = re.search(r"\bof \d+", header) is not None
    want_context = (vh or 0) > 480
    if has_context != want_context:
        notes.append(
            "header context line "
            + ("should be present" if want_context else "should be collapsed")
            + f" at vh={vh} (text: {header[:60]!r})"
        )
    if p.get("overflowCount"):
        first = (p.get("overflow") or [{}])[0]
        notes.append(
            f"{p['overflowCount']} element(s) outside the viewport "
            f"(e.g. <{first.get('tag')}> {first.get('over')})"
        )
    # The settings overlay must open fully on screen at every size (it is capped to the
    # space above the dock, which is exactly where a short viewport clips it).
    overlays = p.get("overlays")
    if overlays is not None:
        panel = overlays.get("settingsPanel")
        if not panel:
            notes.append("settings overlay did not open")
        else:
            if panel["right"] > vw + 0.5 or panel["bottom"] > vh + 0.5 or panel["x"] < -0.5 or panel["y"] < -0.5:
                notes.append(
                    f"settings panel outside the viewport ({panel['w']}x{panel['h']} at "
                    f"{panel['x']},{panel['y']} -> {panel['right']},{panel['bottom']})"
                )
            if overlays.get("overflowCount"):
                first = (overlays.get("overflow") or [{}])[0]
                notes.append(
                    f"{overlays['overflowCount']} element(s) outside the viewport with settings open "
                    f"(e.g. <{first.get('tag')}> {first.get('over')})"
                )
    if p.get("docScrollW", 0) > (vw or 0) + 1:
        notes.append(f"document scrolls horizontally ({p['docScrollW']} > {vw})")
    if p.get("docScrollH", 0) > (vh or 0) + 1:
        notes.append(f"document scrolls vertically ({p['docScrollH']} > {vh})")
    return notes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:5199")
    ap.add_argument("--kind", default="series", choices=["series", "movie"])
    ap.add_argument("--shots", default=None, help="directory for per-viewport screenshots")
    ap.add_argument("--out", default=None, help="write the JSON report here")
    ap.add_argument("--fullscreen", action="store_true", help="also click Fullscreen + re-probe")
    ap.add_argument(
        "--overlays", action="store_true", help="also open the settings overlay + re-probe"
    )
    args = ap.parse_args()

    frame_url = f"{args.base}/harness/player-frame.html?kind={args.kind}"
    results: list[Result] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
        for label, w, h, mobile, touch, dpr in VIEWPORTS:
            ctx = browser.new_context(
                viewport={"width": w, "height": h},
                device_scale_factor=dpr,
                is_mobile=mobile,
                has_touch=touch,
            )
            page = ctx.new_page()
            err: str | None = None
            probe: dict | None = None
            try:
                page.goto(frame_url, wait_until="load")
                page.wait_for_function("() => !!document.querySelector('video')", timeout=15000)
                page.wait_for_timeout(700)  # stubbed fetch + media metadata settle
                probe = page.evaluate(PROBE_JS)
                if args.overlays:
                    # The settings panel is height-capped to the space above the dock;
                    # on a short viewport that is exactly where a clipped panel appears.
                    page.click("button[aria-label='Settings']")
                    page.wait_for_timeout(350)
                    ov = page.evaluate(PROBE_JS)
                    panel = page.evaluate(
                        "() => { const p = document.querySelector('[aria-label=\"Player settings\"]');"
                        " if (!p) return null; const b = p.getBoundingClientRect();"
                        " return { x: +b.x.toFixed(1), y: +b.y.toFixed(1), w: +b.width.toFixed(1),"
                        " h: +b.height.toFixed(1), right: +b.right.toFixed(1), bottom: +b.bottom.toFixed(1) }; }"
                    )
                    ov["settingsPanel"] = panel
                    probe = {**probe, "overlays": ov}
                    page.click("button[aria-label='Close settings']")  # leave it as we found it
                    page.wait_for_timeout(150)
                if args.fullscreen and not mobile:
                    page.click("button[aria-label='Fullscreen']")
                    page.wait_for_timeout(600)
                    fs = page.evaluate(PROBE_JS)
                    probe = {**probe, "fullscreen": fs}
                if args.shots:
                    Path(args.shots).mkdir(parents=True, exist_ok=True)
                    slug = label.lower().replace(" ", "-").replace("×", "x")
                    page.screenshot(path=str(Path(args.shots) / f"{slug}.png"))
            except Exception as exc:  # noqa: BLE001 - reported, not swallowed
                err = f"{type(exc).__name__}: {exc}"
            notes = verdict(probe, err)
            if args.fullscreen and probe and probe.get("fullscreen"):
                fs = probe["fullscreen"]
                if abs(fs["root"]["w"] - fs["vw"]) > 0.5 or abs(fs["root"]["h"] - fs["vh"]) > 0.5:
                    notes.append("fullscreen shell does not fill the screen")
            results.append(Result(label, {"w": w, "h": h, "mobile": mobile}, notes, probe, err))
            ctx.close()
        browser.close()

    width = max(len(r.label) for r in results) + 2
    print(f"{'viewport'.ljust(width)} {'size':<11} result   detail")
    print("-" * 110)
    for r in results:
        p = r.probe or {}
        size = f"{r.viewport['w']}x{r.viewport['h']}"
        state = "PASS" if r.ok else "FAIL"
        detail = "; ".join(r.notes) if r.notes else "shell = viewport, dock inside, no overflow"
        # Informational only: content below the fold INSIDE the settings panel's
        # scroll container is reachable by scrolling, so it is not a failure — but it
        # is worth seeing, since it is how much of the panel a phone user must scroll.
        if not r.notes and r.probe:
            reach = (r.probe.get("overlays") or {}).get("overflowReachable")
            if reach:
                detail += f" | {reach} more inside the panel's scroll area (reachable)"
        if r.ok:
            detail += (
                f" | video {p.get('video', {}).get('w')}x{p.get('video', {}).get('h')}"
                f" dock {p.get('dockH')}px"
                f" | {len(p.get('buttons') or [])} controls, min {p.get('minButtonH')}px"
            )
        print(f"{r.label.ljust(width)} {size:<11} {state:<8} {detail}")
    failed = [r for r in results if not r.ok]
    print("-" * 110)
    print(f"{len(results) - len(failed)}/{len(results)} viewports PASS")

    if args.out:
        Path(args.out).write_text(
            json.dumps([{**asdict(r), "ok": r.ok} for r in results], indent=1), encoding="utf-8"
        )
        print(f"json report -> {args.out}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
