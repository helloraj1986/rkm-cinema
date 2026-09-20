# Plan — the title screen's artwork as the PAGE, with a scrim built from its own colour

His ask, 2026-09-20 (his second time raising it): *"what can we do about the posters can we make it a background of
the details page with using gradients color depening on the poster so that the text on the details page can be seen
clearly"* — and, two rounds earlier: *"why cant we keep it as background of the whole page… the text part can be put
on darker gradient… the poster can take the whole page"*.

Plan committed BEFORE the build, per `references/feature-shipping-cycle.md`. **Every number below was computed from
the tokens in this repo on 2026-09-20**, not carried over from an estimate.

---

## 1. What is on the screen today, and what the ask changes

Today the title screen is **a band and a page**: a full-bleed `hero` **313.2 pt** tall (0.29 of the canvas) holding
the backdrop with the title block over its lower part, then the action row, synopsis, credits and cast **below the
band** on flat `void` — with a scrim (`Title.scrim*`) painted *inside the band only*, so everything from the action
row down has always sat on a plain dark background.

The ask is one structural sentence: **the artwork becomes the page, and the title block moves from inside the band
into the page's flow, with a scrim derived from the artwork so text stays legible over it.**

⚠ **Two things follow that are NOT cosmetic, and both are arithmetic:**

1. the page grows, because the title block now occupies its own space in the flow instead of sitting inside a band
   that was already there (§2);
2. the scrim stops being a fixed gradient and becomes a function of the artwork's own colour (§3) — which is the
   part that needs a new pure rule and a new sample of pixels.

## 2. The measurement — does the page still FIT?

⚠ The rule this rests on (W2, `references/screen-geometry-and-focus.md` §6): **a tvOS `ScrollView` scrolls only when
focus moves onto something inside it**, and every band below `Play` on this screen is information. Nothing below it
can pull focus, so **this page cannot scroll and must fit 1080 pt**. `DetailRules.titlePageHeight` is that budget
and the harness pins it at **1058.5 pt** (21.5 pt of air).

| term | today | after |
|---|---|---|
| hero band `screenHeight × 0.29` | 313.2 | — *(gone)* |
| title block in the page's flow | — *(inside the band)* | **350.8** |
| everything below the action row (`titlePageHeight − hero`) | 745.3 | 745.3 |
| **total** | **1058.5** | **1096.1** |

⚠⚠ **SO THE ASK COSTS +37.6 pt, and at 1096.1 the page is 16.1 pt OVER the screen.** ⚠ **The `Bar.clearance`
(115.2) is NOT added to the second column** — the bar floats over artwork in *both* layouts, so that 115.2 pt is
spent on art either way. Counting it twice is the easy way to talk yourself out of a feasible change.

**The two levers, and the gain each buys — both of them corrections rather than cuts:**

| lever | gain | why it is the right one |
|---|---|---|
| the title's own line height: `Metric.lineHeightRatio` **1.2** → **his file's `line-height:1.02`** | **−29.0** | ⚠ `title-view.html`: `.title-block h1 { font-size:64px; line-height:1.02 }`. The budget has been charging the h1 a `1.2` line box it does not have |
| the bottom tail `Title.bottomSpacer` (126 pt) | −126.0 *(already outside the budget)* | ⚠⚠ **it is DRAWN but not budgeted, so it is a real overflow that no gate has ever seen.** It exists to keep the last shelf off a scroller's edge — and this screen has had no scroller since round 11. ⇒ it goes |

⇒ after both: **1067.1 pt — 12.9 pt of air**, and the budget and the page finally describe the same screen.

⚠⚠ **AND THE BUILD FOUND A THIRD LEVER, WHICH THE GATE CAUGHT RATHER THAN THIS PLAN DID: 12.9 pt is UNDER the 20 pt
floor `DetailRules.minimumTitlePageSlack` keeps** (it exists so the line-height assumption can be wrong by 2 % and
the page still fits). The cheapest honest 8 pt on the page is the credits block's own line gap — a bare `6` in the
VIEW and another bare `6` in the RULE, for a block **his `title-view.html` does not have at all**. ⇒ It became one
token, `Title.creditLineGap = 2`, the two copies collapsed into one, and the built page is **1059.1 pt with
20.9 pt of air**. ⚠ That is the ONLY visible change the page-as-artwork cost: four points between 14 pt credit
lines. Recorded rather than slipped in.

## 3. The colour — where it comes from, and why half of it is a pure rule

**The scrim is built from the artwork's own colour**, so a warm poster gets a warm wash and a cold one a cold one,
and **the wash's depth is decided by how bright the artwork is** — which is exactly what makes text legible over an
arbitrary poster instead of over the one the designer happened to test.

| half | where | runs on Linux? |
|---|---|---|
| **the numbers**: which colour a set of sampled pixels means, and how deep the scrim must be for that colour's luminance | **`Core/ArtworkTint.swift`** (new, pure) | ✅ pinned in `check-tvos-core.py` |
| the PIXELS: `UIImage` → a small grid of samples | `Home/PosterCard.swift` beside `PosterImageView` — **the one place this app decodes artwork** | ❌ Mac only |
| the BRIDGE: sample → SwiftUI `Color` | `Design/DesignColours.swift` — ⚠ the only file allowed to construct a `Color(red:)` (`check-design-tokens.py` R3) | ❌ Mac only |

⚠⚠ **THE SAMPLER MUST NOT GO IN `PosterLoader`.** That file is deliberately Foundation-only so it compiles on Linux
(its header says so); one `import UIKit` there would take the whole loader out of the sandbox's reach.

⚠ **The tint is taken ONCE per artwork** — 16×16 = 256 samples off bytes already in memory, no second request — and
fed back to the screen as state. The bytes are already being decoded for the image itself.

## 4. What the treatment is, when the art is the wrong shape

⚠⚠ **NOTHING NEW IS DECIDED HERE — `PosterRules.treatment` already answers it, and it was written for this case.**
Its own comment: *"Is this band wider than it is tall — a hero band, a 16:9 card, **the whole page**?"* ⇒

* a **16:9 backdrop** in a 1920 × 1080 page fills, as it does in the band today;
* a **2:3 poster** (the fallback for a title with no keyart — the Kids films are the ones he has reported) is shown
  **whole, over a blurred dimmed copy of itself**, which is `ArtworkTreatment.ambient` and is the *existing* answer to
  *"i can only see 1/3rd of the poster"* (`KNOWN_ISSUES` #16). ⚠ So the new layout **inherits** the fix rather than
  re-deciding it, and the blurred copy is what makes a portrait poster cover a whole page without cropping it.

## 5. Falsifiers — what his round settles, and what would disprove it

| # | ✅ should | ❌ disproves |
|---|---|---|
| A1 | the artwork runs the **whole page** — behind the title, the action row, the synopsis, the cast | art still stops in a band |
| A2 | the title, meta line and every paragraph are **readable over the art**, on a dark title and on a bright one | any band where text fights the picture |
| A3 | a **poster-only** title (a Kids film) shows its poster **whole**, over a soft blurred fill — not cropped to a third | a third of it, or black bars |
| A4 | the page still **fits**: nothing below the cast row is off the bottom, and the screen does not open scrolled | anything clipped at the bottom edge |
| A5 | the scrim **changes with the title** — two different films do not share one wash | one identical gradient on every title |
| A6 | the ring still opens on **`Play`**, and `Down` from `Back to Browse` still reaches it | the round-12 fix regressed |

⚠ A5 is the one that cannot be argued on a screenshot: it needs **two titles** in the round, one dark and one bright.

## 6. What this plan does NOT do

* **It does not reintroduce a `ScrollView`.** The page fits (§2), nothing below `Play` takes focus, and the
  container was deleted in round 11 for a reason that has not changed.
* **It does not touch the Home.** The Home's hero band is a band by design — it sits above two rails that DO scroll,
  and Apple's own TV apps do the same. ⚠ Offered, not done: `HeroBand` could take the same tinted scrim, which is
  one shared change once this one is confirmed.
* **It adds no focusable control.** The bands below `Play` stay information; `ARCHITECTURE.md` §11 is unchanged.
