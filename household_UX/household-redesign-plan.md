# RKM Cinema — Account Menu & Household Page Redesign

**Reference implementation:** `household-redesign.html` (open directly in a browser — it's a static, fully interactive mockup of the target state).

**Scope:** Visual/UX only. No API, route, auth, or data-model changes. Every action in the mockup (Add member, Reset password, Library access, Rename, Enable/Disable, Remove, Sign out) should call the **exact same existing backend logic/endpoints** that the current UI already calls — only the surrounding markup, layout, and entry points change.

Affected routes (unchanged): `/settings/household`, `/library/home`, and whatever route currently backs "My password".

---

## 1. Sidebar: remove `Household` and `My password`

**Current:** Sidebar has `Settings`, `Household`, `My password` as three separate nav items.

**Change:**
- Delete the `Household` and `My password` sidebar items entirely.
- Keep `Settings` in the sidebar as-is.
- No route changes — `/settings/household` still exists, it's just no longer linked from the sidebar. It's now reachable only via the new account menu (see §2).

**Files likely affected:** the sidebar/nav component (e.g. `Sidebar.tsx` / `AppNav.tsx` or equivalent) — remove the two `<NavItem>` entries, keep everything else (Home, Libraries, Collections, Settings) untouched.

---

## 2. New: Account menu on the top-right avatar

**Current:** The "RK" avatar in the top bar is not interactive (or does nothing meaningful).

**Change:** Make it a dropdown trigger. Clicking it opens a popover anchored to the avatar, top-right aligned, containing (in this exact order):

1. **Header block** — avatar, current profile name, role label (e.g. "Administrator" or "Member")
2. **Household** — _visible only if the signed-in profile is an administrator_. Navigates to the existing `/settings/household` route.
3. **Account & password** — navigates to the existing "My password" route/logic (same destination as the old sidebar link).
4. **Switch profile** — same behavior as the existing "Switch profile" button in the top bar (that top-bar button can now be removed since it's consolidated here — see note below).
5. **Settings** — navigates to the existing Settings route.
6. Divider
7. **Sign out** — same behavior as the existing "Sign out" button in the top bar (also consolidate — see note below).

**Note on consolidation:** The current top bar has separate "Switch profile" and "Sign out" buttons next to the avatar. Since both actions now live inside the account menu, remove those two standalone buttons from the top bar and keep only the avatar + username. This is what actually makes the top bar (and the app overall) feel cleaner — don't leave duplicate controls in both places.

**Behavior details:**
- Toggle open/closed on avatar click.
- Close on: click outside, `Escape` key, or selecting any item.
- Keyboard accessible: avatar button has `aria-haspopup="true"` and `aria-expanded`; menu has `role="menu"`, items `role="menuitem"`; arrow-key navigation is a nice-to-have, not required for v1.
- The **Household** item must be conditionally rendered based on the current user's admin flag — reuse whatever check currently gates access to `/settings/household` server-side, don't invent a new permission model.

**Files likely affected:** top bar component (e.g. `TopBar.tsx`), plus a new small `AccountMenu` component. Reuse existing handlers for sign-out / switch-profile / settings-navigation — just re-wire them to the new menu items instead of writing new logic.

---

## 3. Household page redesign

**Current:** A flat list of horizontal rows, all at the same visual weight (name, badges, "Sees: ...", action buttons all in one dense row per member).

**Change:** Restructure into four visual layers, top to bottom:

### 3.1 Page header
- Small eyebrow: `ACCOUNT · HOUSEHOLD`
- Page title: `Household`
- One-sentence description (see mockup copy) explaining what the page does
- `+ Add member` as a prominent primary (filled) button, top-right of the header, same as today but visually elevated (filled accent button vs. the current outline style)

### 3.2 Summary row (new)
Three small stat cards side by side:
- **Household members** — total count of profiles
- **Active profiles** — count excluding disabled profiles
- **Libraries shared** — count of distinct libraries assigned across all non-admin members

These are derived entirely from data the page already has (the member list + their library grants). No new API calls needed — compute client-side from the existing household payload.

### 3.3 Profile cards (replaces the current rows)
Each member renders as a card with:
- Avatar (initials, same as today)
- Name
- Status/role badges inline next to the name: `YOU`, `ADMINISTRATOR`, `DISABLED`, `NO PASSWORD` — same badge data as today, just restyled as pills instead of plain text
- Meta line: last-seen text (or "Never signed in")
- Library chips: one chip per library the member can see; admins get a single "Every library" chip instead of enumerating
- Primary row actions: **Library access** and **Reset password** / **Set a password** / **Change password** (label depends on state, same logic as today's button label)
- Secondary actions (Rename, Enable/Disable, Remove) move into a **"⋯" overflow menu** rather than being separate always-visible buttons — reduces row clutter. The admin's own row has no overflow menu (can't rename/disable/remove yourself), matching current behavior where those buttons are already disabled/hidden for `rkm`.

### 3.4 Modals (new — replace inline actions)
Three modals, triggered from the cards above:

- **Library access modal** — checklist of libraries with checkboxes, "Cancel" / "Save access". Replaces whatever the current "Folders" button does inline.
- **Change/Set/Reset password modal** — "New password" + "Confirm password" fields, "Cancel" / "Save password". Replaces the current inline "Reset password"/"Set a password" action.
- **Add member modal** — "Name", optional "Password", library checklist, "Cancel" / "Create member". Replaces however "+ Add member" currently works (whether that was inline expansion or a separate page).

All three should submit to the **same existing endpoints** the current buttons call — this is purely moving those calls behind a modal instead of an inline row or separate view.

---

## 4. Visual hierarchy summary

```
Page
 └─ Header (eyebrow, title, description, Add member)
     └─ Summary cards (members / active / libraries)
         └─ Profile cards (avatar, name+badges, meta, chips)
             └─ Card actions (Library access, Password action, ⋯ overflow)
                 └─ Modals (Library access / Password / Add member)
```

Each level should read as visually quieter than the one above it — the header is the boldest text on the page, summary cards are secondary, profile cards are tertiary, and in-card actions are the quietest/smallest elements.

---

## 5. What NOT to change

- No new API endpoints.
- No change to `/settings/household` as the canonical URL for this page.
- No change to how admin-only access is determined.
- No change to what data is fetched — only how it's laid out and which controls trigger which existing actions.
- Keep the existing dark theme, accent color, and typography of the app — the mockup deliberately reuses the current app's palette rather than introducing a new brand identity.

---

## 6. Suggested component breakdown (adapt to your existing structure)

- `AccountMenu` — new. Popover component, receives current user + admin flag as props, renders the 4 nav items + sign out conditionally.
- `TopBar` — edit. Remove standalone "Switch profile"/"Sign out" buttons, mount `AccountMenu` on the avatar.
- `Sidebar` — edit. Remove `Household` and `My password` items.
- `HouseholdPage` — edit. Restructure into `HouseholdHeader`, `HouseholdSummary`, `ProfileCard` (list), each pulling from the same data source as today.
- `ProfileCard` — new/edit. Renders avatar, badges, meta, chips, actions, overflow menu.
- `LibraryAccessModal`, `PasswordModal`, `AddMemberModal` — new. Thin wrappers around existing mutation calls.

---

## 7. QA checklist before shipping

- [ ] Non-admin profile does not see "Household" in the account menu.
- [ ] Admin's own profile card has no overflow menu / no Remove option (matches current safeguard).
- [ ] Disabled member's overflow menu shows "Enable" (not "Disable").
- [ ] "No password" member shows "Set a password" (not "Reset password").
- [ ] All modals trap focus and close on Escape / backdrop click / Cancel.
- [ ] Library chip count and summary-card counts update live if data changes (e.g. after saving library access in the modal).
- [ ] Keyboard: avatar menu and profile overflow menus are reachable and closeable via keyboard.
- [ ] Existing endpoints for sign out, switch profile, reset/set password, library access, add member, rename, enable/disable, and remove are all still called with the same payloads as before — only the triggering UI moved.
