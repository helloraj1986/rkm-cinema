# CTA button alignment — plan and measurements

His report (2026-09-13), two visual polish defects on two high-visibility surfaces. Both are fixed by
one change of principle, and both are pinned by measurements rather than by class strings.

| # | Surface | Defect |
|---|---|---|
| 1 | `MediaCard` poster CTA ("▶ Episodes", the "Recently Added" rail) | the play glyph rendered ABOVE the word instead of beside it |
| 2 | global-search result row (`GlobalSearch` → `OwnedRow`) | "Resume" (primary) and "Details" (secondary) rendered at different heights and padding, as a pair that is meant to read as one action group |

## 1. What was actually wrong (measured, not inferred)

`tools/check_cta_alignment.py` over `frontend/harness/cta-frame.*`, run BEFORE the fix, in the
falsification direction (`--expect-broken`), which requires every assertion to FAIL:

```
pill 96.0×36.0px  glyph 13.0×13.0px  label ink 13.0px tall, font 12.0px Inter
FAIL A/B/C: the glyph and the label must share ONE LINE — their boxes overlap -8.50px
FAIL A/B/C: the glyph→label gap should be 3–12px, got -37.59px
FAIL A/B/C: the label's ink must be centred on the box's axis, got +10.25px (tolerance 1.5)
FAIL A/B/C: the glyph must be centred on the box's axis, got -11.25px (tolerance 1.5)
FAIL E/row 1 (Resume/Details): must be the same height, got 32.00px vs 30.50px (+1.50px)
FAIL E/row 1: vertical padding must match — paddingTop is 0px on the primary and 6px on the secondary
```

**Bug 1's cause** is a CSS-mode mistake, not a spacing value: the pill was `grid place-items-center`
with TWO children, so grid laid the glyph into row 1 and the label into row 2. ⚠ The trap that hid it:
the pill's height is FIXED (`h-9` = 36px) and the two stacked rows (13px + 16px) fit inside it, so
**nothing overflowed** — the box was the right size and only its insides were wrong. A unit test on
class strings cannot see this; a rect measurement can.

**Bug 2's cause** is two hand-rolled class strings that had drifted: the primary carried a fixed `h-8`
with NO vertical padding, the secondary `py-1.5` with no height. Their difference (1.50px here) is
whatever the font's line-height happens to be, so it is machine-dependent — another reason a string
assertion is the wrong instrument.

⚠ Neither button came from a shared component, which is the audit answer his report asked for: both
were inline. That is *why* they drifted, and it is what Decision 1 below fixes.

## 2. Decisions

1. **One `components/ui/Button.tsx`, one size token.** `SIZE` holds every box-deciding class
   (`h-8`, `px-3`, `rounded-lg`, `text-[11px]`, `gap-1.5`); the variants change FILL, COLOUR and
   WEIGHT only — hierarchy survives, geometry cannot drift. Applied to the search rows (primary +
   secondary + the discovery rows' ghost pair) and to the decorative "Browse" chip, which was the
   third copy of the same hand-tuned chip.
2. **The pill becomes a flex row**, not a grid: `flex items-center justify-center` + `leading-none`,
   so the label's line box cannot push the glyph off the axis. The movie CTA (a single glyph in a
   circle) keeps its shape and is asserted unchanged (`D`).
3. **Tolerances are stated, not tuned.** 1.5px for the ink centring, because the analytic method
   (Range box → baseline → canvas ink extent) carries ~0.3px and a label with a descender ("Episodes")
   legitimately sits ~1px below the centre of its own box in DejaVu Sans. The defects it must catch are
   4–21px, and the falsification run proves the band is tight enough. Same method as
   `tools/check_brand_lockup.py`.
4. **Both directions are asserted.** `--expect-broken` runs the SAME checks against the unfixed source
   and insists they fail — a check that passes against the bug is documentation, not a guard, and this
   repo has shipped two of those.
5. **The wiring is re-proved** (scenario F): clicking either button must still run the row's own
   action. A restyle that leaves the buttons inert would be a worse bug than the misalignment.

## 3. Result (after)

```
pill 109.2×36.0px  glyph cy +0.00px and label ink cy +0.50px off the pill axis; gap 6.00px
row 1 (Resume/Details):  90.2×32.00px vs 69.4×32.00px  pad 0px/0px vs 0px/0px  font 11px vs 11px
row 2 (Watch Now/Details): 110.5×32.00px vs 69.4×32.00px  pad 0px/0px vs 0px/0px  font 11px vs 11px
H  every primary button is 32.00px tall across 2 rows; every secondary button is 32.00px
F  clicking Details and the primary both still activate the row
```

The pill is 13px wider (96.0 → 109.2) — that is the layout becoming a row: glyph + 6px gap + label.

⚠ **`Button.test.ts` is the companion guard, not a substitute.** It pins that no variant grows its own
box class (falsified: injecting `py-1.5` into the secondary fails it, naming the token). It cannot see
what the browser does, which is why the geometry check exists.

## 4. Not done, on purpose

* The size stays 32px — these buttons sit inside a result row whose 56px poster they must not dominate.
  A redesign of the row's action sizing would be a different change with its own measurements.
* Other CTA pairs elsewhere in the app (`ItemDetail`'s primary actions) were NOT migrated to `Button`:
  they are a different size by design and out of this report's scope. They are candidates for the same
  treatment, with their own measurements.
