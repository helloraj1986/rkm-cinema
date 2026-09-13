#!/usr/bin/env python3
"""CTA button alignment check — the poster's "▶ Episodes" pill and the search row's action pair.

His report (2026-09-13), two defects on two high-visibility surfaces:

  Bug 1  MediaCard's poster CTA ("▶ Episodes", the "Recently Added" rail) rendered the glyph
         ABOVE the label instead of beside it.
  Bug 2  the global-search result row's **Resume** (primary) and **Details** (secondary) buttons
         rendered at different heights, with different padding, as a pair meant to read as one
         action group.

WHY A TOOL AND NOT A UNIT TEST. Both defects are GEOMETRY, and both could be described accurately
in code and still be wrong on screen:

  * Bug 1's cause is a CSS-mode mistake — the pill was `grid place-items-center` with TWO children,
    so grid laid the glyph into row 1 and the text into row 2. The pill's own height is FIXED
    (`h-9` = 36px) and the two stacked rows (13px + 16px) fit inside it, so **nothing overflowed**:
    the box was the right size and only its INSIDES were wrong. No class-string assertion can see
    that; a rect measurement can.
  * Bug 2's cause is two hand-rolled class strings that had drifted — the primary carried a fixed
    `h-8` with no vertical padding, the secondary `py-1.5` with no height — so their rendered
    heights disagree by whatever the font's line-height happens to be. Again a measurement, not a
    string.

The repo has twice shipped a check that could not fail (§6f/§6g), so these assertions are falsified
before being trusted: `--expect-broken` runs the SAME checks against the unfixed source and insists
they fail, with the numbers printed.

WHAT IS ASSERTED

  A  the pill's glyph and label share ONE LINE: their boxes overlap by at least half the shorter
     one's height (a stack overlaps by ~0px — this is the assertion Bug 1 has to lose to).
  B  the label sits AFTER the glyph horizontally, with a 3–12px gap (a centred stack puts the label
     UNDER the glyph, so the gap goes negative).
  C  both are centred on the pill's own vertical axis (1.5px — see the method note).
  D  the movie CTA (a single ▶ in a circle) is unchanged: the glyph is centred in its circle — the
     flex rewrite must not break the CTA it was never meant to touch.
  E  per search row: the primary and secondary buttons have equal heights, equal vertical padding,
     equal border-radius and equal font-size — they may differ ONLY in fill, weight and icon.
  F  per search row: the pair is centred on each other AND on the row's own axis, and neither button
     pokes outside the row.
  G  the glyph inside the primary button is inline and centred, exactly as in A–C (the "Resume"
     button is the pattern the report points at, so it is held to the same rule).
  H  the SAME size tokens reach every row: the two rows' primaries are the same height, as are their
     secondaries. This is what "consolidate so sizing cannot drift" means in measurable terms — a
     future hand-tuned class string in one place fails H.

Method note (C/F/G): a label's ink is derived analytically — `Range.getBoundingClientRect()` gives
the FONT box and therefore the baseline, and canvas `actualBoundingBoxAscent/Descent` give the ink
extent above and below it. A label with a descender ("Episodes") sits ~1px below the centre of its
own box in DejaVu Sans, so the tolerance is 1.5px rather than 0.5px; the defects it must catch are
3–8px, and the falsification run proves the band is tight enough. This is the same method (and the
same 0.3px of uncertainty) as `tools/check_brand_lockup.py`.

Run the dev server first (see frontend/harness/README.md):

    cd frontend && npx vite --port 5199 --strictPort
    python3 tools/check_cta_alignment.py [--shots DIR]
    python3 tools/check_cta_alignment.py --expect-broken     # falsification direction
"""
from __future__ import annotations

import argparse
import sys

from playwright.sync_api import Page, sync_playwright

PROBLEMS: list[str] = []

OVERLAP_FRACTION = 0.5   # A: the two boxes must share at least half of the shorter one's height
GAP_MIN, GAP_MAX = 3.0, 12.0
CENTRE_TOL = 1.5         # C/F/G: px — the analytic ink method's own uncertainty (see docstring)
HEIGHT_TOL = 0.5         # E/F: a pair must agree to this; the defect is 3–5px
EDGE_TOL = 0.1           # E: padding / radius / font-size must match exactly (they are computed px)
ROW_TOL = 1.0            # F: each button's centre vs the row's centre

#: Shared by both MEASURE scripts: a rect, and the INK box of a text node (plus the font box's own
#: left/right, which the ink box does not need but the glyph→label gap does).
INK_JS = r"""
  const rect = (el) => {
    const b = el.getBoundingClientRect();
    return { left: b.left, right: b.right, top: b.top, bottom: b.bottom,
             width: b.width, height: b.height, cx: b.left + b.width / 2, cy: b.top + b.height / 2 };
  };
  const ctx = document.createElement("canvas").getContext("2d");
  const findText = (root, needle) => {
    const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = w.nextNode())) {
      const v = (n.nodeValue || "").trim();
      if ((needle === null ? v.length > 0 : v === needle)) return n;
    }
    return null;
  };
  const ink = (node) => {
    const el = node.parentElement;
    const cs = getComputedStyle(el);
    ctx.font = cs.font;
    const m = ctx.measureText((node.nodeValue || "").trim());
    const range = document.createRange();
    range.selectNodeContents(node);
    const fontBox = range.getBoundingClientRect();
    const baseline = fontBox.bottom - m.fontBoundingBoxDescent;
    const top = baseline - m.actualBoundingBoxAscent;
    const bottom = baseline + m.actualBoundingBoxDescent;
    return { value: (node.nodeValue || "").trim(),
             family: cs.fontFamily.split(",")[0].replace(/['"]/g, ""),
             size: parseFloat(cs.fontSize),
             // the text run's own box, for the horizontal gap (the ink box has no useful left edge)
             left: fontBox.left, right: fontBox.right,
             top: top, bottom: bottom, height: bottom - top, cy: (top + bottom) / 2 };
  };
"""

MEASURE_CARD = "() => {" + INK_JS + r"""
  const out = { series: null, movie: null, error: null };

  const seriesBtn = document.querySelector('button[aria-label^="Episodes for"]');
  if (!seriesBtn) { out.error = 'no poster CTA button with an "Episodes for ..." aria-label'; return out; }
  const pill = seriesBtn.firstElementChild;
  if (!pill) { out.error = "the series poster CTA has no inner pill element"; return out; }
  const icon = pill.querySelector("svg");
  if (!icon) { out.error = "the Episodes pill carries no <svg> glyph"; return out; }
  const node = findText(pill, "Episodes");
  if (!node) { out.error = "the Episodes pill has no `Episodes` text node"; return out; }
  out.series = { pill: rect(pill), icon: rect(icon), label: ink(node) };

  const movieBtn = document.querySelector('button[aria-label^="Play "]');
  if (movieBtn && movieBtn.firstElementChild) {
    const circle = movieBtn.firstElementChild;
    const g = circle.querySelector("svg");
    out.movie = { circle: rect(circle), icon: g ? rect(g) : null };
  }
  return out;
}
"""

MEASURE_SEARCH = "() => {" + INK_JS + r"""
  const styleOf = (el) => {
    const cs = getComputedStyle(el);
    return { paddingTop: cs.paddingTop, paddingBottom: cs.paddingBottom,
             borderRadius: cs.borderTopLeftRadius, fontSize: cs.fontSize,
             fontWeight: cs.fontWeight, display: cs.display };
  };

  const rows = [...document.querySelectorAll('[role="option"]')];
  if (!rows.length) return { error: "no search result rows ([role=option]) in the DOM", rows: [] };
  const out = { rows: [], error: null };
  for (const row of rows) {
    const buttons = [...row.querySelectorAll("button")];
    const primary = row.querySelector('button[data-testid="row-action-primary"]') || buttons[0];
    const secondary = row.querySelector('button[data-testid="row-action-secondary"]') || buttons[1];
    if (!primary || !secondary) {
      out.error = "a result row carries " + buttons.length + " button(s); the pair cannot be measured";
      return out;
    }
    const icon = primary.querySelector("svg");
    const node = findText(primary, null);
    out.rows.push({
      text: (row.textContent || "").trim().slice(0, 60),
      primaryLabel: (primary.textContent || "").trim(),
      secondaryLabel: (secondary.textContent || "").trim(),
      via: row.querySelector('button[data-testid="row-action-primary"]') ? "data-testid" : "position",
      row: rect(row), primary: rect(primary), secondary: rect(secondary),
      primaryStyle: styleOf(primary), secondaryStyle: styleOf(secondary),
      icon: icon ? rect(icon) : null,
      label: node ? ink(node) : null,
    });
  }
  return out;
}
"""


def problem(message: str) -> None:
    PROBLEMS.append(message)
    print(f"  FAIL: {message}")


def check(condition: bool, message: str) -> None:
    if not condition:
        problem(message)


def inline_cta(where: str, box: dict, glyph: dict, label: dict | None) -> None:
    """A–C/G for one CTA: glyph and label on ONE line, glyph before label, both centred on the box.

    `label` is the label's ink box when the CTA has text (the pill, the Resume button), or `None`
    for a glyph-only CTA (the movie circle), where only the glyph's centring is meaningful.
    """
    if label is not None:
        # A — ONE LINE, measured glyph box vs label box (a stack overlaps by ~0px, and goes negative
        # once the two rows are pushed apart).
        overlap = min(glyph["bottom"], label["bottom"]) - max(glyph["top"], label["top"])
        check(overlap >= OVERLAP_FRACTION * min(glyph["height"], label["height"]),
              f"{where}: the glyph and the label must share ONE LINE — their boxes overlap "
              f"{overlap:.2f}px, less than {OVERLAP_FRACTION:.0%} of the shorter box (glyph "
              f"{glyph['height']:.2f}px tall, label ink {label['height']:.2f}px). A ~0px overlap is "
              f"a STACK, which is the defect")
        check(glyph["left"] <= label["left"] + 1.0,
              f"{where}: the label must sit AFTER the glyph horizontally — the glyph starts at "
              f"{glyph['left']:.2f} and the label at {label['left']:.2f}, so the label is not to the "
              f"right of the glyph (a centred stack)")
        gap = label["left"] - glyph["right"]
        check(GAP_MIN <= gap <= GAP_MAX,
              f"{where}: the glyph→label gap should be {GAP_MIN:.0f}–{GAP_MAX:.0f}px, got {gap:.2f}px")
        check(label["top"] >= box["top"] - EDGE_TOL and label["bottom"] <= box["bottom"] + EDGE_TOL,
              f"{where}: the label's ink pokes outside its box (label {label['top']:.2f}→"
              f"{label['bottom']:.2f} vs box {box['top']:.2f}→{box['bottom']:.2f})")
        dl = label["cy"] - box["cy"]
        check(abs(dl) <= CENTRE_TOL,
              f"{where}: the label's ink must be centred on the box's axis, got {dl:+.2f}px "
              f"(tolerance {CENTRE_TOL})")

    dz = glyph["cy"] - box["cy"]
    check(abs(dz) <= CENTRE_TOL,
          f"{where}: the glyph must be centred on the box's axis, got {dz:+.2f}px "
          f"(tolerance {CENTRE_TOL})")
    check(glyph["top"] >= box["top"] - EDGE_TOL and glyph["bottom"] <= box["bottom"] + EDGE_TOL,
          f"{where}: the glyph pokes outside its box (glyph {glyph['top']:.2f}→{glyph['bottom']:.2f} "
          f"vs box {box['top']:.2f}→{box['bottom']:.2f})")


def scenario_a_poster_cta(page: Page, base: str, shots: str) -> None:
    print('A–D — the poster CTA: "▶ Episodes" is ONE line, the movie circle is untouched')
    page.goto(f"{base}/harness/cta-frame.html?scene=card", wait_until="networkidle")
    page.wait_for_timeout(400)
    probe = page.evaluate("window.__probe()")
    check(probe["hasEpisodesCta"],
          "A: the series card must offer an `Episodes for …` CTA — if the frame did not render, every "
          "assertion below is vacuous")
    if not probe["hasEpisodesCta"]:
        return
    m = page.evaluate(MEASURE_CARD)
    if m.get("error"):
        problem(f"A: cannot measure the poster CTA: {m['error']}")
        return

    s = m["series"]
    print(f"  pill {s['pill']['width']:.1f}×{s['pill']['height']:.1f}px  glyph "
          f"{s['icon']['width']:.1f}×{s['icon']['height']:.1f}px  label ink "
          f"{s['label']['height']:.1f}px tall, font {s['label']['size']:.1f}px {s['label']['family']}")
    before = len(PROBLEMS)
    inline_cta("A/B/C series pill", s["pill"], s["icon"], s["label"])
    if len(PROBLEMS) == before:
        print(f"  OK: inline — glyph cy {s['icon']['cy'] - s['pill']['cy']:+.2f}px and label ink cy "
              f"{s['label']['cy'] - s['pill']['cy']:+.2f}px off the pill axis; gap "
              f"{s['label']['left'] - s['icon']['right']:.2f}px")

    if m.get("movie") and m["movie"].get("icon"):
        mv = m["movie"]
        dz = mv["icon"]["cy"] - mv["circle"]["cy"]
        check(abs(dz) <= CENTRE_TOL,
              f"D: the movie CTA's glyph must stay centred in its circle, got {dz:+.2f}px")
        print(f"  D  movie circle {mv['circle']['width']:.1f}×{mv['circle']['height']:.1f}px, glyph "
              f"{dz:+.2f}px off centre")
        if len(PROBLEMS) == before:
            print("  OK: the glyph-only CTA is unchanged")

    if shots:
        # ⚠ `page.hover()` on the pill never resolves: the card's own transparent whole-card BUTTON
        # legitimately intercepts the pointer (that is the card's design), so Playwright refuses the
        # action. Moving the raw mouse onto the card is what the `group-hover` reveal actually needs,
        # and a screenshot must never be able to lose the measurements above.
        try:
            page.screenshot(path=f"{shots}/cta-card.png")
            card = page.locator('article[data-testid="media-card"]').first.bounding_box()
            if card:
                page.mouse.move(card["x"] + card["width"] / 2, card["y"] + card["height"] / 2)
                page.wait_for_timeout(400)
            page.locator('article[data-testid="media-card"]').first.screenshot(path=f"{shots}/cta-pill.png")
        except Exception as exc:  # noqa: BLE001 — evidence is optional, the measurement is not
            print(f"  NOTE: could not capture shots: {exc}")


def scenario_e_search_pair(page: Page, base: str, shots: str) -> None:
    print("E–H — the search result row: the Resume/Details pair is ONE size, centred on the row")
    page.goto(f"{base}/harness/cta-frame.html?scene=search", wait_until="networkidle")
    page.fill('input[type="search"]', "sholay")
    try:
        # The rows exist only once the stubbed query has ANSWERED. Waiting on a timeout would let an
        # empty frame pass every assertion below: nothing measured is nothing wrong.
        page.wait_for_function(
            "() => (window.__probe().searchCalls || []).length > 0 && window.__probe().rows >= 1",
            timeout=15000,
        )
    except Exception:
        problem("E: the search dropdown never rendered a result row — the frame did not render, so "
                "every assertion below would be vacuous")
        return
    page.wait_for_timeout(300)

    m = page.evaluate(MEASURE_SEARCH)
    if m.get("error"):
        problem(f"E: cannot measure the result rows: {m['error']}")
        return
    rows = m["rows"]
    labels = [r["primaryLabel"] for r in rows]
    check("Resume" in labels,
          'E: expected the episode row\'s primary action to read "Resume" (the report\'s case), got '
          f"{labels} — the stub and the state machine have drifted apart")
    pairs = ", ".join(f"{r['primaryLabel']}/{r['secondaryLabel']}" for r in rows)
    print(f"  {len(rows)} result row(s) measured via {rows[0]['via']}: {pairs}")

    for i, r in enumerate(rows, start=1):
        where = f"row {i} ({r['primaryLabel']}/{r['secondaryLabel']})"
        p, sec = r["primary"], r["secondary"]
        ps, ss = r["primaryStyle"], r["secondaryStyle"]
        before = len(PROBLEMS)
        dh = p["height"] - sec["height"]
        check(abs(dh) <= HEIGHT_TOL,
              f"E/{where}: the primary and secondary buttons must be the same height, got "
              f"{p['height']:.2f}px vs {sec['height']:.2f}px ({dh:+.2f}px)")
        for prop, key in (("vertical padding (top)", "paddingTop"),
                          ("vertical padding (bottom)", "paddingBottom"),
                          ("border-radius", "borderRadius"),
                          ("font-size", "fontSize")):
            check(ps[key] == ss[key],
                  f"E/{where}: {prop} must match across the pair — {key} is {ps[key]} on the primary "
                  f"and {ss[key]} on the secondary")
        dcy = p["cy"] - sec["cy"]
        check(abs(dcy) <= HEIGHT_TOL,
              f"F/{where}: the pair must be centred on one axis, got {dcy:+.2f}px apart")
        for name, box in (("primary", p), ("secondary", sec)):
            d = box["cy"] - r["row"]["cy"]
            check(abs(d) <= ROW_TOL,
                  f"F/{where}: the {name} button's centre must sit on the row's axis, got {d:+.2f}px")
            check(box["top"] >= r["row"]["top"] - EDGE_TOL
                  and box["bottom"] <= r["row"]["bottom"] + EDGE_TOL,
                  f"F/{where}: the {name} button pokes outside the row "
                  f"({box['top']:.2f}→{box['bottom']:.2f} vs {r['row']['top']:.2f}→{r['row']['bottom']:.2f})")
        if r["icon"] and r["label"]:
            inline_cta(f"G/{where}", p, r["icon"], r["label"])
        print(f"  {where}: primary {p['width']:.1f}×{p['height']:.2f}px vs secondary "
              f"{sec['width']:.1f}×{sec['height']:.2f}px  pad "
              f"{ps['paddingTop']}/{ps['paddingBottom']} vs {ss['paddingTop']}/{ss['paddingBottom']}  "
              f"font {ps['fontSize']} vs {ss['fontSize']}  centres {dcy:+.2f}px apart"
              + ("  OK" if len(PROBLEMS) == before else ""))

    # H — the same tokens reach every row: a hand-tuned variant in one place must fail this.
    for kind in ("primary", "secondary"):
        heights = sorted({round(r[kind]["height"], 2) for r in rows})
        check(len(heights) == 1,
              f"H: every row's {kind} button must be one size, got {heights} across {len(rows)} rows")
        if len(rows) > 1 and len(heights) == 1:
            print(f"  H  every {kind} button is {heights[0]:.2f}px tall across {len(rows)} rows")

    if shots:
        try:
            page.screenshot(path=f"{shots}/cta-search.png")
            page.locator('[role="option"]').first.screenshot(path=f"{shots}/cta-row.png")
        except Exception as exc:  # noqa: BLE001 — evidence is optional, the measurement is not
            print(f"  NOTE: could not capture shots: {exc}")

    # Wiring — a restyle that leaves the buttons inert would be a worse bug than the misalignment
    # it fixed, and the row's own click handler must still be able to stop propagation.
    for testid, name in (("row-action-secondary", "Details"), ("row-action-primary", "the primary")):
        page.goto(f"{base}/harness/cta-frame.html?scene=search", wait_until="networkidle")
        page.fill('input[type="search"]', "sholay")
        try:
            page.wait_for_function("() => window.__probe().rows >= 1", timeout=15000)
        except Exception:
            problem(f"F: the rows never came back for the {name} click — cannot prove the wiring")
            continue
        page.click(f'[data-testid="{testid}"]')
        page.wait_for_timeout(400)
        after = page.evaluate("window.__probe()")
        check(after["rows"] == 0,
              f"F: clicking {name} must run the row's own action (the widget closes its dropdown on "
              f"activate) — {after['rows']} row(s) are still rendered, so the button is inert")
        if after["rows"] == 0:
            print(f"  F  clicking {name} still activates the row (dropdown closed)")


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

        scenario_a_poster_cta(page, args.base, args.shots)
        page.goto("about:blank")
        scenario_e_search_pair(page, args.base, args.shots)

        if errors:
            check(False, f"page errors: {errors}")
        browser.close()

    if args.expect_broken:
        if not PROBLEMS:
            print("\nFALSIFICATION FAILED: every check passed against source that still carries the "
                  "defects — the check cannot tell the fix from the bug")
            return 1
        print(f"\nOK (falsified as expected): {len(PROBLEMS)} problem(s) with the fix absent")
        return 0

    if PROBLEMS:
        print(f"\n{len(PROBLEMS)} problem(s)")
        return 1
    print("\nOK: the poster CTA is inline, and the search action pair is one size, centred on its row")
    return 0


if __name__ == "__main__":
    sys.exit(main())
