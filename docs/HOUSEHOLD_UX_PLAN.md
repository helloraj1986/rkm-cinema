# Plan: Household page + account menu (from `household_UX/`)

**Status: ✅ PHASE 1 BUILT AND MERGED 2026-09-13** — implemented on branch **`feat/household-ux`**, gates
green, **merged to `main` by fast-forward** (`main` @ `3e9d343`) at his direction. ⚠ **His RKM-HP deploy
and eyeball are still outstanding:** the merge happened BEFORE he looked, so anything he flags is a
forward fix on `main`. Session record at the top of `docs/PROGRESS.md`.

**What was taken, and the two decisions this plan left open:**

* **§3.5 — counts: Option A.** His answer, verbatim: *"Skip the counts — no API change"*. The modal's
  checklist is library NAMES only; nothing new is fetched.
* **§2 — the menu delta: follow the mockup.** The account menu is now **Household · Account &
  password · Switch profile · Settings · Sign out**, with an `ADMIN` pill on Household. The password
  SCREEN still titles itself "My password" (flagged to him rather than changed unasked).
* **Two dialogs beyond the three in §3.4** — `Rename` and `Remove` moved behind `Dialog` as well,
  because deleting the inline forms without a home for those actions removes the capability.
* **⚠ A real payload bug was found and fixed while porting the inline form:** "Every library" used to
  send `library_ids: []`, which the route stores as *no libraries at all*. See
  `folderSelectionPayload` in `frontend/src/features/admin/lib.ts`.

Everything below is the original scoping, kept as written.

**Visual/UX only.** No API, route, auth or data-model change — every action keeps calling the endpoint
it calls today; only the markup, layout and entry points move. That constraint is his, verbatim:
*"All three should submit to the same existing endpoints … this is purely moving those calls behind a
modal instead of an inline row or separate view."*

## 1. The reference material

| Where | What it is |
|---|---|
| `household_UX/household-redesign-plan.md` | **His brief** — 7 sections: sidebar, account menu, the household page, visual hierarchy, what NOT to change, suggested components, QA checklist |
| `household_UX/household-redesign.html` | **The target state** — a static, fully interactive mockup. Open it in a browser; it is the acceptance reference, not decoration |
| `RKM-CINEMA_NEW_UX/RKM_Cinema_Premium_Media_Library_Design_Spec.md` | The **wider programme** (whole-app premium redesign, 87 sections, its own 9 phases) — see §6. Not this phase |
| `RKM-CINEMA_NEW_UX/RKM_Cinema_Visual_Prototype.html` | That spec's prototype |
| `rkm-ux-shots/household-redesign-full.png` (rendered 2026-09-13) | A full-page screenshot of the mockup, for a quick look without opening it |

## 2. ⚠ ALREADY DONE — do NOT redo this (§1 and §2 of his brief)

His brief was written on 2026-09-12; the account-menu consolidation landed **2026-09-13** and already
implements its first two sections. Re-doing them would be churn:

| Brief section | State | Evidence |
|---|---|---|
| §1 Remove `Household` + `My password` from the sidebar | **DONE** | `app/layout/Sidebar.tsx` (~172-184) — both items removed, with a comment saying they are account destinations, not navigation; `MobileNav.tsx` likewise |
| §2 Account menu on the avatar, top-right, consolidated | **DONE** | `features/auth/AccountMenu.tsx`; `Header.tsx` is ONE control (`variant="chip"`), the sidebar footer is the same menu (`variant="wide"`); outside-click/Escape/`role=menu`; Household gated by `mayManageHousehold` on the SERVER's own `is_admin` |

**The one remaining delta in the menu** (small, part of Phase 1): the mockup's item order and content is
**Household · Account & password · Switch profile · Settings · Sign out**, while the app ships
**Switch profile · My password · Household (admin) · Sign out** (no `Settings` entry — Settings is only
in the sidebar). Decide deliberately and say so in the commit: follow the mockup (add Settings, rename
"My password" → "Account & password", reorder) **or** keep the shipped order and only add Settings.
Recommendation: **follow the mockup** — it is the reference he handed over, and the labels are his.

## 3. Phase 1 — the household page (the actual work)

`features/admin/HouseholdView.tsx` is 599 lines and still the OLD shape: one flat list of
`MemberRow`s, each with inline `FolderTicks` / `InlinePassword` / `InlineRename` / `InlineRemove`
sub-forms and a `Tag`. Target: four visual layers, each quieter than the one above it.

### 3.1 Page header
Eyebrow `ACCOUNT · HOUSEHOLD`; title `Household`; the mockup's one-sentence description, verbatim:
*"Everyone signs in with their own account and keeps their own watch history and resume points.
Choose which libraries each person can see — it's enforced the same way across every device."*;
`+ Add member` as a **filled accent** primary button, top-right (today it is an outline/plain button).

### 3.2 Summary row — NEW
Three stat cards, values computed **client-side from the payload the page already has**:
`Household members` (total profiles) · `Active profiles` (excluding disabled) · `Libraries shared`
(distinct libraries granted across non-admin members).
⇒ New **pure** function in `features/admin/lib.ts` (e.g. `householdSummary(users, libraries)`) + cases
in `lib.test.ts`. Nothing new is fetched.

### 3.3 Profile cards (replace the rows)
Avatar (initials, coloured), name, **badge pills** (`YOU`, `ADMINISTRATOR`, `DISABLED`, `NO PASSWORD`
— the same facts today's `Tag` shows, restyled), meta line (`Last seen 13/09/2026` /
`Never signed in` — `lastLoginLabel` already exists), **library chips** (one per granted library; an
administrator gets a single `Every library` chip), then actions right-aligned:

| Action | Rule |
|---|---|
| `Library access` | every member |
| `Reset password` / `Change password` / `Set password` | label by state — **exactly today's rule**; render the no-password case as a filled button (as the mockup does) |
| `⋮` overflow: `Rename`, `Enable`/`Disable`, `Remove` | **never on the administrator's own row** — matches the current safeguard (no rename/disable/remove of yourself) |

Use the existing `components/ui/PopupMenu.tsx` for the overflow and `components/ui/Badge.tsx` for the
pills — do not invent new primitives.

### 3.4 Three modals, replacing the inline forms
`components/ui/Dialog.tsx` **already exists** (focus trap + restore, §51 chrome) — reuse it. It is what
the mockup expects, and rebuilding it is the classic way to lose the focus trap.

| Modal | Fields (from the mockup) | Buttons |
|---|---|---|
| **Library access** | checkbox per library + "Choose which libraries this profile can see." | `Cancel` · `Save access` |
| **Password** | `New password` + `Confirm password` | `Cancel` · `Save password` |
| **Add member** | `Name`, optional `Password`, library checklist | `Cancel` · `Create member` |

Same mutations, same payloads: `useHouseholdMutations()` in `features/admin/api.ts` (create / policy /
rename / password / delete) — the modal only changes WHO calls them. Delete `FolderTicks`,
`InlinePassword`, `InlineRename`, `InlineRemove`, `AddMemberForm` once their modal lands (dead inline
forms are how two behaviours drift).

### 3.5 ⚠ DECISION NEEDED — the mockup's per-library item counts
The mockup's Library-access modal shows `Movies · 412 items`, `TV Shows · 1,204 episodes`. **That data
does not exist on the endpoint the page uses**: `GET /api/admin/libraries` returns
`{id, name, collection_type, path}` only, and `GET /api/library` carries GLOBAL `counts: {movie, show}`
— not per library. So the counts are the ONE place the mockup asks for something beyond a visual change.

* **Option A (recommended, zero API change — matches his own constraint):** Phase 1 ships the chips and
  the modal **without counts** (or with `collection_type`/`path`, which the payload does have).
* **Option B:** an **additive** change to `/api/admin/libraries` to include a count per library
  (ADR-0001 allows additive; the provider already has `get_library_counts()`), which means contract
  snapshot + regenerated types + its own tests — a separate, small commit.

Ask him once, take the answer, and record which one was taken in the commit message.

## 4. What else must move with it (or the gates lie)

* **`tools/check_household_ui.py`** — drives the CURRENT UI (it calls the inline actions by label). It
  must drive the cards + modals instead, and keep its falsification habit: it was built by *opening* the
  admin gate and watching it fail. If it cannot fail, it is documentation. Run it via the vite harness
  (`frontend && npx vite --port 5199 --strictPort`, then the check with `--base`).
* **`frontend/harness/`** — the admin frame supplies stubbed payloads. ⚠ A stub **kinder than the
  server** is this repo's most expensive repeating bug (the Household-hidden-from-admin incident,
  `ADMIN_CREDENTIALS_PLAN.md` §6g): make the fixture's shape match what `GET /api/auth/profiles` and
  `GET /api/admin/*` actually send, `current.is_admin` included.
* **`features/admin/lib.test.ts`** — the new pure functions (summary counts, badge states, action
  labels) get cases there; no component-level test harness is needed.
* **Docs** — no API or architecture change, so README/ARCHITECTURE stay as they are. If a label a user
  sees changes (e.g. "My password" → "Account & password"), check whether `OPERATIONS.md` or the
  README quotes it and fix that line — a doc quoting a control that no longer exists is how the last
  truth pass got work.

## 5. Acceptance (his §7 checklist, plus what this repo requires)

- [ ] A non-admin profile sees **no Household** in the account menu.
- [ ] The administrator's own card has **no overflow menu** (no Remove/Rename/Disable on yourself).
- [ ] A disabled member's overflow shows **Enable**; a member with no password shows **Set password**.
- [ ] All three modals: focus trapped, close on `Escape` / backdrop / `Cancel`.
- [ ] Library chips and the summary counts **update live** after saving library access (the query
      invalidation the page already does).
- [ ] Keyboard reachable and closable: the account menu and every overflow menu.
- [ ] Every mutation still sends **the same payload** as before (diff the calls the check makes).
- [ ] `npx tsc --noEmit` · `npx vitest run` · `VITE_ENABLE_REACT=1 npm run build` · the household
      browser check · `python3 tools/check_md_links.py` if a doc changed.
- [ ] **Falsified**: the header's admin gate and the "no overflow on your own row" rule proved by
      breaking them (the pattern that caught the guard hole on 2026-09-13).
- [ ] Committed as `feat(household-ux): …` + a `docs(status)` record, pushed; merge only when he asks.

## 6. What comes after this phase — the wider programme (NOT this phase)

`RKM-CINEMA_NEW_UX/RKM_Cinema_Premium_Media_Library_Design_Spec.md` is a whole-app redesign: design
tokens, typography, sidebar/top bar, Home + hero + rails, Movies, TV Shows, detail pages, search,
filters, sorting, view modes, cards, modals, z-index, motion — 87 sections, **its own 9 phases**
(Foundation → Navigation → Media primitives → Movies → TV Shows → Home → Search → Library operations →
Polish), 10 implementation rules and visual acceptance criteria.

**Honest sizing: that is a multi-session programme, not one phase.** It also assumes a few things this
app does not have (a `Collections` nav group; `Movies`/`TV Shows` as top-level sidebar entries), so
before its Phase 1 starts it needs a short **delta pass** against the real routes and components —
otherwise the first phase is spent reconciling the spec with the app.

Recommended order: **Phase 1 (this plan) first** — it is small, self-contained, and it is the UX he
handed over — then a planning sitting for the premium phases, one phase per session, each its own
branch and merge.

## 7. Traps already paid for in this repo (do not pay again)

1. **A stub kinder than the server** hides a real bug for the whole life of a feature (§6g).
2. **A check that cannot fail** is worse than no check — falsify every new assertion by breaking the
   thing it guards (this is how the nginx/deployed-check guard was caught passing with its rule
   commented out).
3. Browser checks read `innerText`: CSS-uppercase headings come back UPPERCASE.
4. The household routes **refuse while somebody else's profile is selected** — the page must not offer
   what the server refuses, and `mayManageHousehold` fails closed on purpose.
5. `Dialog.tsx` already has the focus trap; `PopupMenu.tsx` already handles outside-click — reuse both.
6. Container clock is UTC, his screenshots/records are AEST; and the harness frame needs its stylesheet
   imported or the geometry is meaningless (`frontend/harness/nav-frame.tsx` cost a session on that).
