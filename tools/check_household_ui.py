#!/usr/bin/env python3
"""Household screen check (AUTH_MULTIUSER_PLAN Phase 1b; redesigned 2026-09-13, HOUSEHOLD_UX_PLAN §3).

Proves what the REDESIGNED screen renders and what it POSTS, against the real components over a
stubbed api (see `frontend/harness/household-frame.tsx`). Eight scenarios:

  A  ?admin=1  the four layers — header, summary counts, profile cards (badges, chips, meta), and
               the card actions; plus the rails: NO overflow menu on your own card.
  B  ?admin=0  a non-administrator session — the refusal is stated plainly, nothing is offered
               that would fail, and NOTHING is written.
  C  ?admin=1  Library access MODAL — the same `library_ids` the inline form sent, the chips and
               the summary cards updating live afterwards, and the `[]`-means-nothing trap for
               "Every library" that the inline form had.
  D  ?admin=1  Password MODAL — a mismatch is refused BEFORE any request; a match sends only the
               new password.
  E  ?admin=1  Rename, from the ⋯ overflow — refused where the server would refuse it, and it
               carries only the name.
  F  ?admin=1  Remove, from the ⋯ overflow — the typed name arms the final button, and nothing
               else does.
  G  ?admin=1  Add member MODAL — a blank password and ONLY the ticked folders reach the API.
  H  ?admin=1  the modal contract — Escape closes, the backdrop closes, and Tab cannot leave it.

Run the dev server first (see frontend/harness/README.md):
    cd frontend && npx vite --port 5199 --strictPort
    python3 tools/check_household_ui.py            # optionally --shots /tmp/shots

⚠ Before believing a run, confirm the SERVER is serving the module on disk — this mount's vite
watcher does not fire and an orphaned dev server happily reports the pre-edit screen as passing:
    curl -s http://localhost:5199/src/features/admin/HouseholdView.tsx | grep -c 'summary-members'
"""
from __future__ import annotations

import argparse
import json
import sys

from playwright.sync_api import Page, sync_playwright

PROBLEMS: list[str] = []


def problem(message: str) -> None:
    PROBLEMS.append(message)
    print(f"  FAIL: {message}")


def check(condition: bool, message: str) -> None:
    if not condition:
        problem(message)


def open_frame(page: Page, base: str, query: str, shots: str, name: str) -> dict:
    page.goto(f"{base}/harness/household-frame.html?{query}", wait_until="networkidle")
    page.wait_for_timeout(600)
    if shots:
        page.screenshot(path=f"{shots}/{name}.png", full_page=True)
    return page.evaluate("window.__probe()")


def writes(state: dict) -> list[dict]:
    return [c for c in state["calls"] if c["method"] != "GET"]


def bodies(state: dict, suffix: str, method: str = "POST") -> list[dict]:
    return [
        json.loads(c["body"] or "{}")
        for c in state["calls"]
        if c["method"] == method and str(c["url"]).endswith(suffix)
    ]


def row(state: dict, name: str) -> dict:
    found = next((r for r in state["rows"] if r["name"] == name), None)
    return found or {"name": name, "text": "", "buttons": [], "badges": [], "chips": [],
                     "hasOverflow": False}


def scenario_a_admin(page: Page, base: str, shots: str) -> None:
    print("A — the administrator's world: four layers and the rails")
    state = open_frame(page, base, "admin=1", shots, "household-admin")

    names = [r["name"] for r in state["rows"]]
    check(names == ["admin", "Guest", "meenu"], f"A: cards should be admin, Guest, meenu, got {names}")

    # Layer 1 — the header, with his copy and the filled Add member button.
    body = state["body"]
    check("ACCOUNT · HOUSEHOLD" in body.upper(),
          "A: the header should carry the ACCOUNT · HOUSEHOLD eyebrow")
    check("keeps their own watch history and resume points" in body,
          "A: the header should carry the mockup's one-sentence description")
    check("Add member" in body, "A: the header should offer Add member")

    # Layer 2 — the summary, computed from the payload (3 members, 2 enabled, Movies + TV Shows).
    check(state["summary"] == {"members": 3, "active": 2, "libraries": 2},
          f"A: summary should be 3 members / 2 active / 2 libraries, got {state['summary']}")

    admin_card, guest_card, meenu_card = row(state, "admin"), row(state, "Guest"), row(state, "meenu")

    # Layer 3 — the cards: badges, chips, meta.
    check(admin_card["badges"] == ["YOU", "ADMINISTRATOR"],
          f"A: the admin badge set should be YOU + ADMINISTRATOR, got {admin_card['badges']}")
    check(guest_card["badges"] == ["NO PASSWORD"],
          f"A: a password-less member should be badged NO PASSWORD, got {guest_card['badges']}")
    check(meenu_card["badges"] == ["DISABLED"],
          f"A: a disabled member should be badged DISABLED, got {meenu_card['badges']}")
    check(admin_card["chips"] == ["Every library"],
          f"A: an administrator gets ONE 'Every library' chip, got {admin_card['chips']}")
    check(guest_card["chips"] == ["Movies"], f"A: the guest's grant should read Movies, got {guest_card['chips']}")
    check("unknown" not in guest_card["text"].lower(),
          "A: a resolvable grant must not be flagged unknown")
    check("Never signed in" in guest_card["text"], "A: an account that never signed in should say so")

    # Layer 4 — the card actions, and the rails that keep some of them off your own card.
    check("Library access" in guest_card["buttons"],
          f"A: every card should offer Library access, got {guest_card['buttons']}")
    check("Set password" in guest_card["buttons"],
          "A: a member with no password should be offered 'Set password' (not 'Reset password')")
    check("Change password" in admin_card["buttons"],
          "A: your own card should read 'Change password'")
    check(meenu_card["hasOverflow"] is True, "A: an ordinary member's card should carry the ⋯ menu")
    check(admin_card["hasOverflow"] is False,
          "A: YOUR OWN card must NOT offer the ⋯ menu — the server refuses rename/disable/remove "
          "of yourself, so the app must not offer them")
    check("renaming, disabling and removing it are not offered" in admin_card["text"],
          f"A: and your own card should say why, got {admin_card['text']!r}")

    if not PROBLEMS:
        print("  OK: four layers render, the counts are derived, and the rails hold")


def scenario_b_non_admin(page: Page, base: str, shots: str) -> None:
    print("B — a non-administrator")
    state = open_frame(page, base, "admin=0", shots, "household-refused")

    check("administrator" in state["refusal"].lower(),
          f"B: the refusal should name the requirement, got {state['refusal']!r}")
    check(state["rows"] == [], "B: no cards should be listed to a non-administrator")
    check(state["addModal"] is False, "B: no add modal should be offered to a non-administrator")
    check("Loading" not in state["body"], "B: the screen must not sit on 'Loading the household…'")

    posts = writes(state)
    check(posts == [], f"B: a non-administrator must trigger no write, got {posts}")

    if not PROBLEMS:
        print("  OK: the refusal is stated plainly and nothing is offered")


def scenario_c_library_access(page: Page, base: str, shots: str) -> None:
    print("C — the Library access modal: same payload, and the screen updates from the SERVER's answer")
    open_frame(page, base, "admin=1", shots, "household-library-modal")

    page.click('[data-testid="member-Guest"] button:has-text("Library access")')
    page.wait_for_selector('[data-testid="library-modal"]', timeout=5000)
    modal = page.evaluate("window.__probe()")["modalText"]
    check("Choose which libraries this profile can see." in modal,
          f"C: the modal should carry the mockup's line, got {modal!r}")
    check(page.is_checked('[data-testid="library-row-Movies"] input'),
          "C: the member's current grant should be ticked when the modal opens")

    # A subset: drop Movies, add TV Shows, save.
    page.uncheck('[data-testid="library-row-Movies"] input')
    page.check('[data-testid="library-row-TV Shows"] input')
    page.click('[data-testid="library-modal"] button:has-text("Save access")')
    page.wait_for_timeout(700)

    sent = bodies(page.evaluate("window.__probe()"), "/policy")
    check(len(sent) == 1, f"C: exactly one policy write expected, got {len(sent)}")
    check(sent and sent[0] == {"library_ids": ["f2"]},
          f"C: only the ticked library should be sent, got {sent}")

    # The screen must show what the SERVER now holds: chip changes, and the summary follows.
    state = page.evaluate("window.__probe()")
    guest = row(state, "Guest")
    check(guest["chips"] == ["TV Shows"], f"C: the chip should follow the save, got {guest['chips']}")
    check(state["summary"]["libraries"] == 1,
          f"C: 'Libraries shared' should drop to 1 once Movies is granted to nobody, got "
          f"{state['summary']}")
    check(state["libraryModal"] is False, "C: the modal should close on success")

    # ⚠ The regression guard: "Every library" must send the FULL id list. The inline form this
    # replaced sent `[]`, which the route stores as EnableAllFolders=false + EnabledFolders=[] —
    # i.e. NO libraries at all (see folderSelectionPayload in features/admin/lib.ts).
    page.click('[data-testid="member-meenu"] button:has-text("Library access")')
    page.wait_for_selector('[data-testid="library-modal"]', timeout=5000)
    page.check('[data-testid="library-every"] input')
    page.click('[data-testid="library-modal"] button:has-text("Save access")')
    page.wait_for_timeout(700)

    state = page.evaluate("window.__probe()")
    sent = bodies(state, "/policy")
    check(sent and sent[-1] == {"library_ids": ["f1", "f2"]},
          f"C: 'Every library' must send every id, never [], got {sent[-1] if sent else None}")
    # ⚠ The card then reads the libraries the SERVER now holds (both, by name) — NOT the words
    # "Every library". That is the honest rendering: the route has no way to say
    # `EnableAllFolders=true` (it always passes `enable_all=False`), so a save leaves an explicit
    # list, and the chip refuses to claim more than the server does.
    check(row(state, "meenu")["chips"] == ["Movies", "TV Shows"],
          f"C: the card should then name the granted libraries, got {row(state, 'meenu')['chips']}")
    check(state["summary"]["libraries"] == 2,
          f"C: and 'Libraries shared' should be back to 2, got {state['summary']}")
    if shots:
        page.screenshot(path=f"{shots}/household-after-access.png", full_page=True)

    if not PROBLEMS:
        print("  OK: the modal posts the ticked ids, the screen follows the server, and the "
              "empty-list trap is gone")


def scenario_d_password(page: Page, base: str, shots: str) -> None:
    print("D — the password modal: refuse a mismatch before the server is asked")
    open_frame(page, base, "admin=1", shots, "household-password-modal")

    page.click('[data-testid="member-Guest"] button:has-text("Set password")')
    page.wait_for_selector('[data-testid="password-modal"]', timeout=5000)
    state = page.evaluate("window.__probe()")
    check(state["modalTitle"] == "Set a password",
          f"D: the title should match the button that opened it, got {state['modalTitle']!r}")

    check(page.is_disabled('[data-testid="password-modal"] button:has-text("Save password")'),
          "D: Save must be disabled while the fields are empty")
    page.fill("#modal-new-password", "hunter2")
    page.fill("#modal-confirm-password", "hunter3")
    check(page.is_disabled('[data-testid="password-modal"] button:has-text("Save password")'),
          "D: a mismatch must not be submittable")
    check("do not match" in page.inner_text('[data-testid="password-modal"]'),
          "D: and the modal should say why")
    check(bodies(page.evaluate("window.__probe()"), "/password") == [],
          "D: a refused password must send NO request at all")

    page.fill("#modal-confirm-password", "hunter2")
    page.click('[data-testid="password-modal"] button:has-text("Save password")')
    page.wait_for_timeout(700)

    state = page.evaluate("window.__probe()")
    sent = bodies(state, "/password")
    check(len(sent) == 1, f"D: exactly one password write expected, got {len(sent)}")
    check(sent and sent[0] == {"new_password": "hunter2"},
          f"D: the body should be only the new password, got {sent}")
    check(state["passwordModal"] is False, "D: the modal should close on success")
    if shots:
        page.screenshot(path=f"{shots}/household-password-saved.png", full_page=True)

    if not PROBLEMS:
        print("  OK: the mismatch never leaves the browser and the payload is unchanged")


def open_overflow(page: Page, member: str, label: str) -> None:
    """Open a card's ⋯ menu and pick an item. The menu is PORTALLED to <body> (PopupMenu)."""
    page.click(f'[data-testid="member-more-{member}"]')
    page.wait_for_timeout(200)
    page.get_by_role("menuitem", name=label, exact=True).click()
    page.wait_for_timeout(200)


def scenario_e_rename(page: Page, base: str, shots: str) -> None:
    """E — renaming: the LABEL changes, the ROLE does not (Phase 2, ADMIN_CREDENTIALS_PLAN §6)."""
    print("E — Rename, from the overflow: the label changes, the role does not")
    open_frame(page, base, "admin=1", shots, "household-rename-modal")

    open_overflow(page, "Guest", "Rename")
    page.wait_for_selector('[data-testid="rename-modal"]', timeout=5000)
    check(page.input_value("#rename-member-name") == "Guest",
          "E: the modal should open prefilled with the account's current name")

    page.fill("#rename-member-name", "Guest")
    check(page.is_disabled('[data-testid="rename-modal"] button:has-text("Save name")'),
          "E: saving the unchanged name must be disabled")
    check("already this account" in page.inner_text('[data-testid="rename-modal"]'),
          "E: and the modal should say why")

    page.fill("#rename-member-name", "admin")
    check(page.is_disabled('[data-testid="rename-modal"] button:has-text("Save name")'),
          "E: a name another account already has must be disabled")
    check("another account" in page.inner_text('[data-testid="rename-modal"]').lower(),
          "E: and the modal should say why")
    check(bodies(page.evaluate("window.__probe()"), "/rename") == [],
          "E: a refused rename must send NO request at all")

    page.fill("#rename-member-name", "Geetanjali")
    page.click('[data-testid="rename-modal"] button:has-text("Save name")')
    page.wait_for_timeout(700)

    state = page.evaluate("window.__probe()")
    sent = bodies(state, "/rename")
    check(len(sent) == 1, f"E: exactly one rename request expected, got {len(sent)}")
    check(sent and sent[0] == {"name": "Geetanjali"},
          f"E: the request carries ONLY the name, got {sent}")
    check("Geetanjali" in [r["name"] for r in state["rows"]],
          f"E: the card should show the new name, got {[r['name'] for r in state['rows']]}")

    # The point of the phase: the ROLE follows the ACCOUNT, not the name.
    renamed = row(state, "Geetanjali")
    check("ADMINISTRATOR" not in renamed["text"], "E: an ordinary member must never gain the role")
    check("ADMINISTRATOR" in row(state, "admin")["text"],
          "E: and the administrator's own card must still carry it")
    if shots:
        page.screenshot(path=f"{shots}/household-renamed.png", full_page=True)

    if not PROBLEMS:
        print("  OK: refused before the server is asked, sends only the name, leaves the role alone")


def scenario_f_remove(page: Page, base: str, shots: str) -> None:
    print("F — Remove, from the overflow: the typed name arms it")
    open_frame(page, base, "admin=1", shots, "household-remove-modal")

    open_overflow(page, "Guest", "Remove")
    page.wait_for_selector('[data-testid="remove-modal"]', timeout=5000)
    check(page.evaluate("window.__probe()")["confirmEnabled"] is False,
          "F: the confirm button must be disabled before the name is typed")
    page.fill("#confirm-name", "gues")
    page.wait_for_timeout(150)
    check(page.evaluate("window.__probe()")["confirmEnabled"] is False,
          "F: a close-but-wrong name must not arm the confirm button")
    page.fill("#confirm-name", "Guest")
    page.wait_for_timeout(150)
    check(page.evaluate("window.__probe()")["confirmEnabled"] is True,
          "F: typing the exact name must arm the confirm button")
    if shots:
        page.screenshot(path=f"{shots}/household-remove-armed.png", full_page=True)

    page.click('[data-testid="remove-modal"] button:has-text("Remove member")')
    page.wait_for_timeout(700)
    state = page.evaluate("window.__probe()")
    deleted = [c for c in state["calls"] if c["method"] == "DELETE"]
    check(len(deleted) == 1, f"F: exactly one DELETE expected, got {len(deleted)}")
    check(deleted and json.loads(deleted[0]["body"] or "{}").get("confirm_name") == "Guest",
          f"F: the typed name must be what is sent, got {deleted}")

    if not PROBLEMS:
        print("  OK: the typed name gates the write")


def scenario_g_add_member(page: Page, base: str, shots: str) -> None:
    print("G — the Add member modal: a blank password and one library")
    open_frame(page, base, "admin=1", shots, "household-add-modal")
    page.click('button:has-text("Add member")')
    page.wait_for_selector('[data-testid="add-member-modal"]', timeout=5000)

    check(page.is_checked('[data-testid="library-row-Movies"] input'),
          "G: every library should be ticked by default")
    page.uncheck('[data-testid="library-row-TV Shows"] input')
    page.fill("#member-name", "Priya")
    # Password deliberately left blank — the user's decision (a member may have none).
    page.click('[data-testid="add-member-modal"] button:has-text("Create member")')
    page.wait_for_timeout(700)

    state = page.evaluate("window.__probe()")
    created = bodies(state, "/admin/users")
    check(len(created) == 1, f"G: exactly one create request expected, got {len(created)}")
    if created:
        body = created[0]
        check(body.get("name") == "Priya", f"G: name should be Priya, got {body.get('name')!r}")
        check(body.get("password") == "", f"G: the password must be blank, got {body.get('password')!r}")
        check(body.get("library_ids") == ["f1"],
              f"G: only the ticked library should be sent, got {body.get('library_ids')!r}")

    check("Priya" in [r["name"] for r in state["rows"]],
          f"G: the new member should appear after refresh, got {[r['name'] for r in state['rows']]}")
    check(state["addModal"] is False, "G: the modal should close once the member exists")
    if shots:
        page.screenshot(path=f"{shots}/household-added.png", full_page=True)

    if not PROBLEMS:
        print("  OK: a blank password and only the ticked folders reached the API")


def scenario_h_modal_contract(page: Page, base: str, shots: str) -> None:
    print("H — the modal contract: focus trapped, Escape and the backdrop close it")
    open_frame(page, base, "admin=1", shots, "household-modal-contract")

    page.click('[data-testid="member-Guest"] button:has-text("Library access")')
    page.wait_for_selector('[data-testid="library-modal"]', timeout=5000)

    # The focus trap: Tab must never leave the panel.
    trapped = True
    for _ in range(12):
        page.keyboard.press("Tab")
        if page.evaluate("window.__probe()")["focusInsideModal"] is not True:
            trapped = False
            break
    check(trapped, "H: Tab must not move focus out of the dialog")

    page.keyboard.press("Escape")
    page.wait_for_timeout(250)
    check(page.evaluate("window.__probe()")["libraryModal"] is False, "H: Escape must close the modal")

    page.click('[data-testid="member-Guest"] button:has-text("Library access")')
    page.wait_for_selector('[data-testid="library-modal"]', timeout=5000)
    page.mouse.click(6, 6)  # the backdrop, well outside the panel
    page.wait_for_timeout(250)
    state = page.evaluate("window.__probe()")
    check(state["libraryModal"] is False, "H: a backdrop click must close the modal")
    check(writes(state) == [], f"H: closing a modal must write nothing, got {writes(state)}")

    if not PROBLEMS:
        print("  OK: every modal traps focus and closes the three ways")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:5199")
    ap.add_argument("--shots", default="")
    args = ap.parse_args()

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        scenario_a_admin(page, args.base, args.shots)
        page.goto("about:blank")
        scenario_b_non_admin(page, args.base, args.shots)
        page.goto("about:blank")
        scenario_c_library_access(page, args.base, args.shots)
        page.goto("about:blank")
        scenario_d_password(page, args.base, args.shots)
        page.goto("about:blank")
        scenario_e_rename(page, args.base, args.shots)
        page.goto("about:blank")
        scenario_f_remove(page, args.base, args.shots)
        page.goto("about:blank")
        scenario_g_add_member(page, args.base, args.shots)
        page.goto("about:blank")
        scenario_h_modal_contract(page, args.base, args.shots)

        if errors:
            problem(f"page errors: {errors}")
        browser.close()

    if PROBLEMS:
        print(f"\n{len(PROBLEMS)} problem(s)")
        return 1
    print("\nOK: household screen behaves (four layers, library access, password, rename, remove, "
          "add member, modal contract)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
