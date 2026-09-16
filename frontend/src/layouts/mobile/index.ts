/**
 * `layouts/mobile/` — the phone-first presentation. **Layout, markup, styling, interaction and
 * local UI state — and nothing else** (MOBILE_FIRST_UI_PLAN §3.4).
 *
 * ⚠ Every file in this directory is policed by `../importRule.ts`, and `imports.test.ts` fails
 * the build on a second HTTP client, a second formatter, a second clock or a second viewport
 * source. That is not a style preference: the whole architecture rests on there being ONE
 * implementation of every business rule, and a mobile view is the easiest place in the app to
 * quietly create the second one.
 *
 * ⚠ **`MobileNav` is re-exported from where it lives, not moved (§2.4).** Two existing gates
 * name its exact path — `app/shell-contract.test.ts` asserts it contains the bottom safe-area
 * inset, and `tools/check_nav_access.py` mounts it from `nav-frame.html`. Moving the file would
 * break both, and a phase is not allowed to change an existing check's verdict (§9.1). The
 * re-export gives routes the symmetric `mobile.X` name without the churn.
 *
 * M0 ships only this index; the screens land in M1–M8, each with the phase that needs it.
 */

export { MobileNav } from "../../app/layout/MobileNav";
