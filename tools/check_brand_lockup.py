#!/usr/bin/env python3
"""Brand lockup alignment check — the sidebar mark vs the "RKM / CINEMA" text (2026-09-13).

His report, verbatim: *"RKM Cinema text on top left is not perfectly aligned with the icon"*.

WHY THIS IS A TOOL AND NOT A NUDGE. The offset is real, but it is not a constant: a line box carries
its font's ASCENT and DESCENT, uppercase type has no descenders, and so a box-centred two-line stack
leans by roughly `(ascent − capHeight − descent) / 2` — a number that belongs to the FONT:

    DejaVu Sans  (what this headless sandbox falls back to)          ->  the stack reads ~0.3px HIGH
    Segoe UI     (Windows' default; the app ships NO webfont, and
                  "Segoe UI" is the first entry of its stack that
                  exists on Windows)                                 ->  ~1.2px LOW   <- what he saw

A hand-tuned pixel nudge would be right on one machine and wrong on the next, so the fix is
`text-box-trim: trim-both` + `text-box-edge: cap alphabetic`, which trims the BLOCK's box to the CAP
ink and lets `items-center` centre the letters themselves — in any font.

WHAT THIS ASSERTS
  D  the trim is really applied (computed `text-box-trim`/`text-box-edge`, and the block's rendered
     height matches its cap ink). Without D, B can pass in a favourable font while the fix is absent.
  A  the play glyph is centred inside its rounded square.
  B  the text's cap ink is centred on the mark, within tolerance.
  C  ⚠ THE GUARD THAT CAN ACTUALLY FAIL — the same measurement with the trim forced OFF. Turning it
     off must CHANGE the geometry by a measurable amount; if the CSS is removed from the component,
     ON == OFF and C fails. This is the assertion that keeps the fix from silently regressing, and it
     is font-independent by construction (both sides use the same method).
     C also tries three installed font stacks and reports their metrics, so it is visible when the
     font-independence claim was (or was not) genuinely exercised on this machine.

Method note: ink is derived analytically — the text run's own client rect (`Range.getBoundingClientRect`,
which is the FONT box and therefore unaffected by the trim) locates the baseline, and canvas
`actualBoundingBoxAscent` gives the ink extent above it. That carries ~0.3px of method uncertainty, which
is why C (a difference, not an absolute) is the assertion that bites.

Run the dev server first (see frontend/harness/README.md):
    cd frontend && npx vite --port 5199 --strictPort
    python3 tools/check_brand_lockup.py [--shots DIR]
"""
from __future__ import annotations

import argparse
import sys

from playwright.sync_api import Page, sync_playwright

PROBLEMS: list[str] = []

INK_TOLERANCE = 1.0  # px — the analytic method's own uncertainty (see the docstring)
GLYPH_TOLERANCE = 0.75
# The trim must MOVE the geometry by at least this much; below it the fix is doing nothing.
TRIM_EFFECT = 0.2

# Font stacks that exist on a bare Linux image and have DIFFERENT vertical metrics, so the
# font-independence of the fix is actually exercised. `None` = leave the app's own stack alone.
FONT_STACKS: dict[str, str | None] = {
    "app stack": None,
    "Liberation Serif": "'Liberation Serif', 'DejaVu Serif', serif",
    "DejaVu Sans Mono": "'DejaVu Sans Mono', monospace",
    "Liberation Sans": "'Liberation Sans', Arial, sans-serif",
}


def problem(message: str) -> None:
    PROBLEMS.append(message)
    print(f"  FAIL: {message}")


def check(condition: bool, message: str) -> None:
    if not condition:
        problem(message)


MEASURE = r"""
({fontStack, trim}) => {
  const lock = document.querySelector('div[title="RKM Cinema"]');
  if (!lock) return { error: "no brand lockup in the DOM" };
  const mark = lock.children[0];
  const text = lock.children[1];
  if (!text) return { error: "the brand lockup has no text block (viewport below xl hides it)" };
  const lines = [...text.children];
  if (fontStack) for (const el of [lock, text, ...lines]) el.style.fontFamily = fontStack;
  if (trim) text.style.setProperty("text-box-trim", trim);
  else text.style.removeProperty("text-box-trim");

  const rect = (el) => { const b = el.getBoundingClientRect();
    return { top: b.top, bottom: b.bottom, height: b.height, cy: b.top + b.height / 2 }; };
  const ctx = document.createElement("canvas").getContext("2d");

  const lineInk = (el) => {
    const cs = getComputedStyle(el);
    ctx.font = cs.font;
    const value = (el.textContent || "").trim();
    const m = ctx.measureText(value);
    const node = el.firstChild;
    if (!node || node.nodeType !== 3) return null;
    const range = document.createRange();
    range.selectNodeContents(node);
    const fontBox = range.getBoundingClientRect();   // the FONT box: trim does not move it
    // The baseline sits `fontBoundingBoxDescent` above the bottom of the font box.
    const baseline = fontBox.bottom - m.fontBoundingBoxDescent;
    const ink = {
      value,
      family: cs.fontFamily.split(",")[0].replace(/["']/g, ""),
      size: parseFloat(cs.fontSize),
      ascent: m.fontBoundingBoxAscent,
      descent: m.fontBoundingBoxDescent,
      capInk: m.actualBoundingBoxAscent,
      top: baseline - m.actualBoundingBoxAscent,
      bottom: baseline + m.actualBoundingBoxDescent,
    };
    ink.ratio = (ink.ascent + ink.descent) / ink.size;
    ink.capRatio = ink.capInk / ink.size;
    return ink;
  };

  const svg = mark.querySelector("svg");
  const styles = getComputedStyle(text);
  return {
    mark: rect(mark),
    icon: svg ? rect(svg) : null,
    block: rect(text),
    lines: lines.map(lineInk).filter(Boolean),
    trim: { trim: styles.textBoxTrim, edge: styles.textBoxEdge },
    supportsTrim: CSS.supports("text-box-trim", "trim-both"),
  };
}
"""


def ink_centre(m: dict) -> float:
    top = min(line["top"] for line in m["lines"])
    bottom = max(line["bottom"] for line in m["lines"])
    return (top + bottom) / 2


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:5199")
    ap.add_argument("--shots", default="")
    args = ap.parse_args()

    with sync_playwright() as p:
        browser = p.chromium.launch()
        # 1440 wide: the xl breakpoint, where the brand TEXT is visible (below xl it is hidden).
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"{args.base}/harness/nav-frame.html?admin=1", wait_until="networkidle")
        page.wait_for_timeout(500)

        base = page.evaluate(MEASURE, {"fontStack": None, "trim": None})
        if "error" in base:
            problem(f"cannot measure the lockup: {base['error']}")
            browser.close()
            print("\n1 problem(s)")
            return 1

        # ── D: the mechanism is present, or the rest means nothing ────────────────────────────────
        print("D — the trim is really applied")
        check(base["supportsTrim"],
              "D: this browser does not support `text-box-trim` (Chromium < 133), so this check CANNOT "
              "prove the alignment — it must not report success")
        check(base["trim"]["trim"] == "trim-both" and base["trim"]["edge"] == "cap alphabetic",
              f"D: the text block should carry text-box-trim/edge, got {base['trim']!r}")
        # The trim removes the leading from the block, so the block MUST be shorter with it on. Both
        # sides of this comparison are the same measurement, which is what makes it dependable.
        untrimmed = page.evaluate(MEASURE, {"fontStack": None, "trim": "none"})
        on_h, off_h = base["block"]["height"], untrimmed["block"]["height"]
        check(on_h <= off_h - 1.0,
              f"D: the trimmed block must be shorter than the untrimmed one — got {on_h:.2f}px vs "
              f"{off_h:.2f}px, i.e. the trim is not taking effect")
        if not PROBLEMS:
            print(f"  OK: trim-both / cap alphabetic applied; the block is {on_h:.2f}px trimmed vs "
                  f"{off_h:.2f}px untrimmed")

        # ── A: the glyph inside the mark ──────────────────────────────────────────────────────────
        print("A — the play glyph is centred in its rounded square")
        if base.get("icon"):
            delta = base["icon"]["cy"] - base["mark"]["cy"]
            check(abs(delta) <= GLYPH_TOLERANCE,
                  f"A: the glyph should be centred in the mark, got {delta:+.2f}px")
            if not PROBLEMS:
                print(f"  OK: {delta:+.2f}px (tolerance {GLYPH_TOLERANCE})")

        # ── B + C: ink centring, and the trim must be doing the work ──────────────────────────────
        print("B/C — the text's cap ink is centred on the mark, in ANY font")
        seen_metrics: set[tuple[float, float]] = set()
        for name, stack in FONT_STACKS.items():
            on = page.evaluate(MEASURE, {"fontStack": stack, "trim": None})
            off = page.evaluate(MEASURE, {"fontStack": stack, "trim": "none"})
            if "error" in on or "error" in off:
                problem(f"{name}: {on.get('error') or off.get('error')}")
                continue
            on_delta = ink_centre(on) - on["mark"]["cy"]
            off_delta = ink_centre(off) - off["mark"]["cy"]
            line = on["lines"][0]
            seen_metrics.add((round(line["ratio"], 3), round(line["capRatio"], 3)))
            print(f"  {name:18s} declared={line['family']:<18s} ascent+descent={line['ratio']:.3f}em "
                  f"cap={line['capRatio']:.3f}em")
            print(f"    ink vs mark: trim ON {on_delta:+.2f}px   trim OFF {off_delta:+.2f}px   "
                  f"(the trim moves it {abs(on_delta - off_delta):.2f}px)")
            check(abs(on_delta) <= INK_TOLERANCE,
                  f"{name}: with the trim applied the ink should be centred within {INK_TOLERANCE}px, "
                  f"got {on_delta:+.2f}px")
            check(abs(on_delta - off_delta) >= TRIM_EFFECT,
                  f"{name}: the trim must actually move the text (>= {TRIM_EFFECT}px) — measured "
                  f"{abs(on_delta - off_delta):.2f}px, i.e. the CSS is missing or has no effect")
            if args.shots:
                page.locator('div[title="RKM Cinema"]').screenshot(
                    path=f"{args.shots}/brand-{name.replace(' ', '-').lower()}.png")

        if len(seen_metrics) < 2:
            print(f"  NOTE: the font stacks available here share one metric profile {seen_metrics}, so "
                  f"the font-independence claim was not exercised on this machine "
                  f"(on his Windows box it is Segoe UI, ~1.2px low before the fix).")

        if errors:
            problem(f"page errors: {errors}")
        browser.close()

    if PROBLEMS:
        print(f"\n{len(PROBLEMS)} problem(s)")
        return 1
    print("\nOK: the brand lockup is aligned by ink, and the cap trim is what does it")
    return 0


if __name__ == "__main__":
    sys.exit(main())
