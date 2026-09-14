#!/usr/bin/env python3
"""Prove the home screen paints from DISK on a cold launch — phase A1 of NATIVE_FEEL_AND_OFFLINE_PLAN.

The plan's gate for A1: a cold launch paints rows with the network (for data) blocked. The unit tests
in `frontend/src/lib/query/` prove the persister's rules; they cannot prove the WIRING — that
`main.tsx` starts the writer, that `AuthProvider` adopts at the right moment, and that the real
`LibraryHomeView` therefore renders last session's rows without asking the server for them. That is
what this does, in a real browser, across a real reload of the same origin.

Scenarios (each one a fresh storage, each one asserting RENDERED CONTENT — "the row is missing" is
true of a blank page and is not evidence):

  A  prime then replay, library routes DEAD      -> the title is on screen and 0 library calls SUCCEEDED
  B  prime with the WRITER DISABLED, then replay -> the title is ABSENT  (the false direction: without
                                                    the disk there is nothing to paint, so A's green
                                                    cannot be an artefact of the stub or the browser)
  C  prime as one profile, replay as ANOTHER     -> the title is ABSENT and the snapshot is DELETED
                                                    (the shared-iPad rule, in a browser rather than in
                                                    a unit test)

Run against the vite dev server:

    cd frontend && npx vite --port 5199 --strictPort &
    python3 tools/check_query_cache.py [--shots DIR]
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

from playwright.sync_api import Page, sync_playwright

BASE = "http://localhost:5199"
PRIME_TITLE = "PRIME-ONLY-FILM"
PROBLEMS: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        PROBLEMS.append(message)
        print(f"  FAIL: {message}")


def _wait_for(page: Page, expr: str, seconds: int, message: str) -> bool:
    """Wait for a condition, recording a CLEAN failure rather than raising (see check_library_scan.py:
    a bare `wait_for_function` aborts the run and buries the reason under a traceback)."""
    try:
        page.wait_for_function(expr, timeout=seconds * 1000)
        return True
    except Exception:
        check(False, message)
        return False


def probe(page: Page) -> dict:
    return page.evaluate("() => window.__probe ? window.__probe() : null") or {}


def served_module(path: str) -> str:
    """⚠ The dev server's watcher does NOT fire on this mount, so an orphaned vite can serve PRE-EDIT
    modules and make a deliberate change look untouched. Every run proves the served module is the one
    on disk before it measures anything (this exact trap produced a false green in this repo twice)."""
    try:
        with urllib.request.urlopen(f"{BASE}{path}", timeout=20) as response:
            return response.read().decode("utf-8", "replace")
    except urllib.error.URLError as exc:  # pragma: no cover - only on a missing server
        check(False, f"the dev server did not serve {path} ({exc}) — is vite running on :5199?")
        return ""


def open_app(page: Page, query: str, expect_ready: bool = True) -> None:
    page.goto(f"{BASE}/harness/cache-frame.html?{query}")
    if expect_ready:
        # The app's OWN text while the guard waits for the session; once it is gone, `me()` has
        # answered and whatever the cache holds has already been restored or refused.
        _wait_for(
            page,
            "() => Boolean(window.__probe) && !window.__probe().body.includes('Checking your session')",
            15,
            f"the shell never left the session skeleton for {query}",
        )
    page.wait_for_timeout(600)  # let a (stale) refetch land, so 'no calls' means no calls


def clear_storage(page: Page) -> None:
    page.evaluate("() => { try { localStorage.clear(); } catch (e) {} }")


def scenario_a(page: Page, shots: str | None) -> None:
    print("A · prime, then a cold reload with the library routes DEAD")
    open_app(page, "phase=prime&owner=uid-raj")
    check(PRIME_TITLE in probe(page).get("body", ""), "the prime load did not render the home rows at all")
    primed = _wait_for(
        page,
        f"() => Boolean(window.__probe().stored) && window.__probe().stored.includes('{PRIME_TITLE}')",
        8,
        "the writer never stored a snapshot (startQueryCachePersistence is not wired?)",
    )
    if primed:
        print("    primed: a snapshot is on disk")

    open_app(page, "phase=replay&owner=uid-raj&dead=1")
    seen = probe(page)
    if shots:
        page.screenshot(path=f"{shots}/query-cache-replay.png")
    check(seen.get("hasPrimeTitle") is True, "the cold reload did NOT paint the rows from disk")
    # ⚠ The decisive half: the rows are on screen AND nothing fetched them. A refetch that failed
    # would leave the restored data on screen too, so the painted rows alone would prove less.
    check(seen.get("libraryCalls") == [], f"the restored launch still called the library: {seen.get('libraryCalls')}")
    check(seen.get("libraryFailures") == 0, f"{seen.get('libraryFailures')} library calls were attempted and refused")


def scenario_b(page: Page, shots: str | None) -> None:
    print("B · FALSIFICATION — the same two loads with the WRITER DISABLED")
    open_app(page, "phase=prime&owner=uid-raj&nopersist=1")
    clear_storage(page)
    open_app(page, "phase=replay&owner=uid-raj&dead=1")
    seen = probe(page)
    if shots:
        page.screenshot(path=f"{shots}/query-cache-falsified.png")
    # If this ever fails, scenario A proves nothing: the title would have to be coming from somewhere
    # other than the disk.
    check(seen.get("hasPrimeTitle") is False, "WITH NO SNAPSHOT the rows still painted — A is not measuring the disk")
    check(bool(seen.get("body")), "the falsified replay rendered nothing at all — that is not a fair comparison")


def scenario_c(page: Page, shots: str | None) -> None:
    print("C · prime as one profile, cold reload as ANOTHER")
    open_app(page, "phase=prime&owner=uid-raj")
    _wait_for(
        page,
        f"() => Boolean(window.__probe().stored) && window.__probe().stored.includes('{PRIME_TITLE}')",
        8,
        "the writer never stored a snapshot for the first profile",
    )

    open_app(page, "phase=replay&owner=uid-kid&dead=1")
    seen = probe(page)
    if shots:
        page.screenshot(path=f"{shots}/query-cache-foreign.png")
    check(seen.get("hasPrimeTitle") is False, "ANOTHER profile's rows were painted from disk")
    check(seen.get("stored") is None, "the other profile's snapshot SURVIVED — one person's rows left on the device")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shots", help="directory for evidence screenshots")
    args = parser.parse_args()

    persist_source = served_module("/src/lib/query/persist.ts")
    frame_source = served_module("/harness/cache-frame.tsx")
    if persist_source and "persistedQueriesOnly" not in persist_source:
        check(False, "the dev server is serving a STALE persist.ts — kill the vite holding :5199 and restart")
    if frame_source and PRIME_TITLE not in frame_source:
        check(False, "the dev server is serving a STALE cache-frame — kill the vite holding :5199 and restart")
    if PROBLEMS:
        print("\nSTALE MODULE — no measurement is meaningful until that is fixed.")
        return 1

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        # ONE context per scenario: localStorage is per-origin and must not leak between scenarios.
        for name, scenario in (("A", scenario_a), ("B", scenario_b), ("C", scenario_c)):
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            page = context.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda err: errors.append(str(err)))
            try:
                scenario(page, args.shots)
            finally:
                # A page error means a React crash or a rejected promise that nothing caught — the
                # rows could be on screen while the app is broken.
                check(not errors, f"{name}: the page threw: {errors[:2]}")
                context.close()
        browser.close()

    print()
    if PROBLEMS:
        print(f"FAIL — {len(PROBLEMS)} problem(s)")
        return 1
    print("PASS — a cold launch paints from disk with no library call, and neither the disk-less nor the "
          "other-profile case paints anything")
    return 0


if __name__ == "__main__":
    sys.exit(main())
