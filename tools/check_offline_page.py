#!/usr/bin/env python3
"""Prove the offline PAGE half works — against the real components, in a real browser (B4, ADR-0010).

Run it with a dev server on 5199:

    cd frontend && npx vite --port 5199 --strictPort &
    python3 tools/check_offline_page.py [--shots DIR]

What this tool is for, in one sentence: **`src/features/offline/*.test.ts` falsifies the RULES, and this
falsifies the WIRING** — that the shipped `DownloadButton`, `DownloadsView` and `Player` read the app's
own rows, that the bridge is not spoken to at all when there is none, that a downloaded film is played
from the device without asking the server, and that a position reached with no server comes back.

⚠ Every assertion below is about something a pure test cannot see:

  * **?bridge=0 reproduces a desktop browser exactly.** `window.__rkmOffline` is injected by
    `OfflineBridge.swift` and exists nowhere else, so "the feature is invisible without the app" is a
    claim about the real DOM — the nav must not offer Downloads, and no row may render a Download
    button, because a control with nowhere to put a film is a control that cannot work (§4.5).
  * **The player must ASK THE DEVICE FIRST and then NOT ASK THE SERVER.** The evidence is negative
    (zero `/api/jellyfin/playback-info` calls) plus positive (`<video src>` was set to the loopback
    URL). ⚠ A check that only saw the URL would pass for a player that also made the call, and the call
    is the thing that cannot happen offline.
  * **The spool's replay is proved with a real `<video>` ticking**, not by calling the queue directly:
    the film is left playing, the network is taken away, and it is given back — the reported position
    must arrive at `POST /api/jellyfin/progress` exactly once, and the queue must empty.

⚠ NO PLACEHOLDER ARGUMENTS and no arguments at all if avoidable: it finds the dev server itself and
says so. The only optional one is `--shots`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.request

from playwright.sync_api import Page, sync_playwright

BASE = "http://localhost:5199"
FRAME = "/harness/offline-frame.html"

PROBLEMS: list[str] = []
SCENARIOS = 0

# ⚠ String literals that exist ONLY in the current source of these modules. Vite's watcher does not
# fire on this mount (WSL2/Docker), so an orphaned dev server keeps serving the PRE-EDIT module — and a
# stale module is indistinguishable from a pass. If one of these is missing, the server is not running
# the code on disk and the whole run means nothing.
FRESHNESS = {
    "/src/features/offline/bridge.ts": "noReplyCapableHandler",
    "/src/features/offline/lib.ts": "unsupportedVersion",
    "/src/features/offline/spool.ts": "rkm.offline-spool.v1",
    "/src/features/offline/session.ts": "reportProgressQueued",
    "/src/features/offline/DownloadsView.tsx": "downloads-summary",
}


def check(condition: bool, message: str) -> None:
    if not condition:
        PROBLEMS.append(message)
        print(f"  FAIL: {message}")
    else:
        print(f"  ok:   {message}")


def _wait_for(page: Page, expression: str, timeout: int = 10_000) -> bool:
    """⚠ Never let a bare `wait_for_function` guard a scenario: it RAISES on timeout and aborts the
    whole run, burying the reason. This records a clean FAIL and lets the rest run."""
    try:
        page.wait_for_function(expression, timeout=timeout)
        return True
    except Exception:
        check(False, f"timed out waiting for: {expression}")
        return False


def served_module_is_fresh() -> bool:
    ok = True
    for path, needle in FRESHNESS.items():
        try:
            with urllib.request.urlopen(f"{BASE}{path}", timeout=10) as response:
                body = response.read().decode("utf-8", "replace")
        except Exception as exc:  # noqa: BLE001
            check(False, f"could not fetch {path} from the dev server ({exc})")
            return False
        digest = hashlib.sha256(body.encode()).hexdigest()[:12]
        # ⚠ A wrong path answers index.html with a 200 on a dev server (SPA fallback), which would
        # make the staleness check compare two identical HTML documents. Refuse it loudly.
        if "<!doctype html" in body[:200].lower():
            check(False, f"{path} answered HTML — the dev server or the path is wrong")
            return False
        if needle not in body:
            check(False, f"{path} on the dev server does not contain {needle!r} — STALE module (hash {digest})")
            ok = False
        else:
            print(f"  fresh: {path} (sha {digest})")
    return ok


def open_frame(page: Page, query: str, shots: str | None, name: str) -> dict:
    global SCENARIOS
    SCENARIOS += 1
    page.goto(f"{BASE}{FRAME}?{query}", wait_until="domcontentloaded")
    _wait_for(page, "typeof window.__probe === 'function'")
    # The session check has to answer before the shell renders, so wait for a real render rather than
    # a fixed sleep. Every scenario below asserts content, never just "no error".
    _wait_for(page, "window.__probe().okBoard === true")
    _wait_for(page, "window.__probe().loginForm === false")
    time.sleep(0.6)  # the bridge's own first `list` + the two React ticks that follow it
    data = page.evaluate("window.__probe()")
    if shots:
        page.screenshot(path=f"{shots}/{SCENARIOS:02d}-{name}.png", full_page=True)
    return data


def scenario_desktop_browser(page: Page, shots: str | None) -> None:
    print("\n1. a DESKTOP browser — no bridge, so the feature must not exist")
    data = open_frame(page, "bridge=0", shots, "desktop")
    check(data["offlineAvailable"] is False, "the page reports no offline bridge")
    check(data["nav"] == [], f"the navigation offers NO Downloads entry (got {data['nav']})")
    check("Download" not in " ".join(data["detail"]["buttons"]), "the detail page renders no Download button")
    check("Sholay" in data["body"], "…while the detail page itself really rendered (it is not an empty shell)")
    check(data["bundleCalls"] == 0, "the page does not even ask the server what a download would cost")


def scenario_affordance(page: Page, shots: str | None) -> dict:
    print("\n2. the iOS shell, nothing downloaded — the button states the size BEFORE the tap")
    data = open_frame(page, "bridge=1", shots, "shell-idle")
    check(data["offlineAvailable"] is True, "the page found the bridge")
    check(data["nav"] == ["/downloads"], f"the navigation offers Downloads (got {data['nav']})")
    buttons = data["detail"]["buttons"]
    check(any("Download" in b for b in buttons), f"the detail page offers Download (buttons: {buttons})")
    summary = " ".join(data["detail"]["summary"])
    check("Remux" in summary, f"the rendition is named (remux) — {summary[:120]!r}")
    check("about 2.10 GB" in summary, f"the size is quoted as the server's ESTIMATE — {summary[:120]!r}")
    check("1080p" not in summary, "no resolution is claimed that the server never sent")
    check(
        [c for c in data["commands"] if c.get("c") == "download"] == [],
        "nothing was downloaded by merely looking at the page",
    )
    return data


def scenario_download(page: Page, shots: str | None) -> None:
    print("\n3. pressing it: the command, the progress, and the finished row")
    open_frame(page, "bridge=1", shots, "download-start")
    page.get_by_role("button", name="Download").first.click()
    _wait_for(page, "window.__bridge.commands.some(c => c.c === 'download')", timeout=5_000)
    commands = page.evaluate("window.__bridge.commands")
    sent = [c for c in commands if c.get("c") == "download"]
    check(len(sent) == 1, f"exactly one download command was sent (got {len(sent)})")
    if sent:
        check(sent[0]["itemId"] == "m-sholay", f"…for the title on screen ({sent[0]!r})")
        check(sent[0]["mode"] == "auto", f"…with the default rendition ({sent[0]!r})")

    # The app now reports the row it created, then moves it — through the REAL event path.
    page.evaluate(
        """window.__bridge.items = [{ itemId: 'm-sholay', title: 'Sholay', state: 'downloading',
             bytes: 500_000_000, totalBytes: 2_100_000_000, mode: 'remux', error: null, url: null,
             contentType: 'video/mp4' }]"""
    )
    page.evaluate(
        """window.__bridge.emit({ v: 1, e: 'state', itemId: 'm-sholay', title: 'Sholay',
             state: 'downloading', bytes: 500_000_000, totalBytes: 2_100_000_000, mode: 'remux' })"""
    )
    page.evaluate(
        """window.__bridge.emit({ v: 1, e: 'progress', itemId: 'm-sholay',
             bytes: 1_575_000_000, totalBytes: 2_100_000_000, percent: 75 })"""
    )
    _wait_for(page, "window.__probe().rows.length === 1")
    data = page.evaluate("window.__probe()")
    row = data["rows"][0]
    check(row["state"] == "downloading" and row["bytes"] == 1_575_000_000, f"the row follows the events ({row})")
    body = data["body"]
    check("75%" in body, "the ring reports 75% — the percentage the app actually sent")
    # ⚠ DECIMAL units, and this is the check that pins it: the app's own log line for the same file
    # reads `offline READY · 1.54 GB`, so a page using binary units (1.44) would disagree with the HUD
    # about one film. 1_575_000_000 bytes is 1.57 GB — the value the app SENT, rendered.
    check("1.57 GB / 2.10 GB · 75%" in body, f"and the bytes as decimal units, matching the app's own HUD — {body[-260:]!r}")
    check("Cancel" in " ".join(data["detail"]["buttons"]), "Cancel is offered while it runs")
    check("Play offline" not in " ".join(data["detail"]["buttons"]), "…and play is NOT, because it is not ready")

    page.evaluate(
        """window.__bridge.items = [{ itemId: 'm-sholay', title: 'Sholay', state: 'ready',
             bytes: 1_543_383_346, totalBytes: 1_543_383_346, mode: 'remux', error: null,
             url: 'http://127.0.0.1:51234/offline/0123456789abcdef0123456789abcdef.mp4',
             contentType: 'video/mp4' }]"""
    )
    page.evaluate(
        """window.__bridge.emit({ v: 1, e: 'ready', itemId: 'm-sholay',
             url: 'http://127.0.0.1:51234/offline/0123456789abcdef0123456789abcdef.mp4',
             contentType: 'video/mp4', bytes: 1_543_383_346 })"""
    )
    _wait_for(page, "window.__probe().rows[0] && window.__probe().rows[0].state === 'ready'")
    if shots:
        page.screenshot(path=f"{shots}/{SCENARIOS:02d}-download-ready.png", full_page=True)
    data = page.evaluate("window.__probe()")
    buttons = " ".join(data["detail"]["buttons"])
    check("Download" not in buttons, f"a finished film offers no Download button ({buttons!r})")
    check("Delete" in buttons, "…it offers Delete, the only way to free the bytes")
    check("On this device · 1.54 GB" in data["body"], f"and says what it holds — {data['body'][-220:]!r}")


def scenario_downloads_screen(page: Page, shots: str | None) -> None:
    print("\n4. the Downloads screen, and playing a film with the server out of the picture")
    open_frame(page, "bridge=1&route=/downloads", shots, "downloads-empty")
    check(
        "Nothing is downloaded yet" in page.evaluate("window.__probe()")["body"],
        "an empty device says so in words (not an empty screen)",
    )

    # ⚠ `__announce` is the app's OWN page-load behaviour reproduced: the rows AND one `state` event
    # each. Setting `bridge.items` alone would say nothing — `list` is asked once, at session start.
    page.evaluate(
        """window.__announce([
             { itemId: 'm-sholay', title: 'Sholay', state: 'ready', bytes: 1_543_383_346,
               totalBytes: 1_543_383_346, mode: 'remux', error: null,
               url: 'http://127.0.0.1:51234/offline/0123456789abcdef0123456789abcdef.mp4',
               contentType: 'video/mp4' },
             { itemId: 'm-other', title: 'Andaz Apna Apna', state: 'paused', bytes: 300_000_000,
               totalBytes: 900_000_000, mode: 'direct', error: null, url: null, contentType: null } ])"""
    )
    _wait_for(page, "window.__probe().downloads.rows.length === 2")
    data = page.evaluate("window.__probe()")
    check("1 title · 1.54 GB on this device" in data["downloads"]["summary"], f"the disk line — {data['downloads']['summary']!r}")
    ready = next((r for r in data["downloads"]["rows"] if "Sholay" in r["text"]), None)
    paused = next((r for r in data["downloads"]["rows"] if "Andaz" in r["text"]), None)
    check(ready is not None and ready["state"] == "ready", f"the finished film has a row ({ready})")
    check(ready is not None and "Play offline" in " ".join(ready["buttons"]), f"…with Play ({ready})")
    check(paused is not None and paused["state"] == "paused", f"the partial download says it is paused ({paused})")
    check(paused is not None and "Resume" in " ".join(paused["buttons"]), f"…and offers Resume ({paused})")
    check(
        paused is not None and "300 MB of 900 MB — resumable" in paused["text"],
        f"…with the bytes it actually holds ({paused['text'] if paused else None!r})",
    )

    # ---- playing it
    page.get_by_role("button", name="Play offline").first.click()
    _wait_for(page, "document.querySelector('video') !== null", timeout=8_000)
    _wait_for(page, "window.__probe().mediaSwaps.length > 0", timeout=8_000)
    data = page.evaluate("window.__probe()")
    swapped = data["mediaSwaps"][0]["from"] if data["mediaSwaps"] else ""
    check(
        swapped.startswith("http://127.0.0.1:51234/offline/"),
        f"the player set the video source to the app's LOOPBACK url — {swapped!r}",
    )
    check(
        "0123456789abcdef0123456789abcdef" in swapped,
        "…the exact handle the bridge minted, not a URL the page built for itself",
    )
    check(data["playbackInfoCalls"] == 0, f"⚠ the server was NOT asked for playback info (calls: {data['playbackInfoCalls']})")
    check(
        "On this device" in data["body"],
        f"the player says where the film is coming from — {data['body'][-200:]!r}",
    )
    commands = [c.get("c") for c in data["commands"]]
    check("play" in commands, f"the page asked the app to play it ({commands})")
    if shots:
        page.screenshot(path=f"{shots}/{SCENARIOS:02d}-playing-offline.png", full_page=True)


def scenario_progress_spool(page: Page, shots: str | None) -> None:
    print("\n5. a position reached with NO server, and what happens when it comes back")
    open_frame(page, "bridge=1&route=/downloads", shots, "spool")
    page.evaluate(
        """window.__announce([{ itemId: 'm-sholay', title: 'Sholay', state: 'ready',
             bytes: 1_543_383_346, totalBytes: 1_543_383_346, mode: 'remux', error: null,
             url: 'http://127.0.0.1:51234/offline/0123456789abcdef0123456789abcdef.mp4',
             contentType: 'video/mp4' }])"""
    )
    _wait_for(page, "window.__probe().downloads.rows.length === 1")

    # ⚠ The network goes away BEFORE the film starts, so every report is a report made with no server —
    # which is the state the whole spool exists for.
    page.evaluate("window.__setApiDown(true)")
    page.get_by_role("button", name="Play offline").first.click()
    _wait_for(page, "window.__probe().mediaSwaps.length > 0", timeout=8_000)
    # The sample file is what actually delivers bytes (a fake loopback URL cannot); the player's own
    # decision to use the loopback URL has already been recorded above.
    page.evaluate("const v = document.querySelector('video'); v.muted = true; v.play();")
    _wait_for(page, "window.__probe().mediaCurrentTime > 0.8", timeout=12_000)
    page.evaluate("document.querySelector('video').pause()")
    _wait_for(page, "window.__probe().queued > 0", timeout=8_000)

    data = page.evaluate("window.__probe()")
    check(data["queued"] >= 1, f"a position reached with no server is QUEUED on the device (queued: {data['queued']})")
    check(data["progressPosts"] == [], f"…and nothing was posted at a server that is down ({data['progressPosts']})")
    check(len(data["mediaSwaps"]) == 1, "the film played from the local file for the whole of it")
    check(
        "waiting to sync" in data["body"],
        f"the screen says what is waiting rather than being silently behind — {data['body'][-240:]!r}",
    )

    # ---- the network comes back
    attempts_before = len(data["progressPosts"])
    page.evaluate("window.__setApiDown(false)")
    page.evaluate("window.dispatchEvent(new Event('online'))")
    _wait_for(page, "window.__probe().queued === 0", timeout=12_000)
    data = page.evaluate("window.__probe()")
    # ⚠ Judged on what arrived AFTER the reconnect, not on the whole log: the point of the check is the
    # REPLAY, and a page that also tried (and failed) while the network was down would otherwise hide
    # inside the count. (Falsified: reporting through the server while playing locally produced three
    # attempts and a replayed `start` at position 0 — the rewind this whole queue exists to prevent.)
    replayed = data["progressPosts"][attempts_before:]
    check(len(replayed) == 1, f"exactly ONE report was replayed on reconnect (got {len(replayed)}: {replayed})")
    if replayed:
        payload = json.loads(replayed[0])
        check(payload["item_id"] == "m-sholay", f"…about the film that was watched ({payload})")
        check(payload["position_ticks"] > 0, f"…carrying a real position ({payload['position_ticks']})")
        check(
            payload.get("runtime_ticks", 0) > 0,
            f"…and the runtime, so the api can tell 'finished' from 'resume point' ({payload})",
        )
    check(data["queued"] == 0, "the queue is drained, not left to be replayed again")
    if shots:
        page.screenshot(path=f"{shots}/{SCENARIOS:02d}-spool-synced.png", full_page=True)


def scenario_unreachable_server(page: Page, shots: str | None) -> None:
    global SCENARIOS
    SCENARIOS += 1
    print("\n6. the server cannot be reached at all — the shell, NOT a sign-in form")
    # ⚠ This is B4's one change OUTSIDE the offline feature, and it is what makes the rest reachable:
    # `api.me()` failing used to mean "signed out", so a phone with the Wi-Fi off showed a login form
    # it could not submit — and the downloads behind it were unreachable.
    page.goto(f"{BASE}{FRAME}?bridge=1&api=down", wait_until="domcontentloaded")
    _wait_for(page, "typeof window.__probe === 'function'")
    _wait_for(page, "window.__probe().okBoard === true", timeout=10_000)
    time.sleep(0.4)
    data = page.evaluate("window.__probe()")
    if shots:
        page.screenshot(path=f"{shots}/{SCENARIOS:02d}-unreachable.png", full_page=True)
    check(data["loginForm"] is False, "no sign-in form is shown to somebody who never signed out")
    check(data["offlineAvailable"] is True, "the app still knows it can hold downloads")
    check(str(data["nav"]) == "['/downloads']", f"and the navigation still reaches them ({data['nav']})")


def scenario_cancel(page: Page, shots: str | None) -> None:
    """⚠ KNOWN_ISSUES §7a — "Cancel has no effect".

    He reported the SYMPTOM on his phone; the cause was in the SWIFT half (a cancel during the
    packaging window had nothing to cancel, and a real cancel never wrote `.paused`, so no event was
    ever planned). ⚠ Be honest about what this scenario can and cannot prove:

    * it PROVES the page half of the contract — one tap sends exactly one `cancel` command, and when
      the shell answers with a `paused` state the row really moves (Cancel -> Resume, bytes kept);
    * it REPRODUCES his report headlessly against a shell that answers nothing, which is the evidence
      that the page could not have fixed this on its own;
    * it CANNOT prove the Swift writes `.paused` on a real cancel. That is `?cancel=fixed` — a stub of
      the FIXED shell, not the shell. No Mac, no simulator, nothing here taps a real Cancel.
    """
    print("\n7. cancelling a download: the command, the row after the shell answers — and when it says nothing")

    # ---- (a) the FIXED shell: cancel -> the record is written paused -> the row moves
    open_frame(page, "bridge=1&cancel=fixed", shots, "cancel-fixed")
    page.get_by_role("button", name="Download").first.click()
    _wait_for(page, "window.__bridge.commands.some(c => c.c === 'download')", timeout=5_000)
    page.evaluate(
        """window.__announce([{ itemId: 'm-sholay', title: 'Sholay', state: 'downloading',
             bytes: 500_000_000, totalBytes: 2_100_000_000, mode: 'remux', error: null, url: null,
             contentType: null }])"""
    )
    _wait_for(page, "window.__probe().rows[0] && window.__probe().rows[0].state === 'downloading'")
    running = page.evaluate("window.__probe()")
    check("Cancel" in " ".join(running["detail"]["buttons"]),
          f"a running download offers Cancel (buttons: {running['detail']['buttons']})")

    page.get_by_role("button", name="Cancel").first.click()
    _wait_for(page, "window.__bridge.commands.some(c => c.c === 'cancel')", timeout=5_000)
    cancels = [c for c in page.evaluate("window.__bridge.commands") if c.get("c") == "cancel"]
    check(len(cancels) == 1, f"exactly ONE cancel command reaches the shell (got {len(cancels)}: {cancels})")
    check(bool(cancels) and cancels[0].get("itemId") == "m-sholay",
          f"…for the title being cancelled ({cancels})")

    _wait_for(page, "window.__probe().rows[0] && window.__probe().rows[0].state === 'paused'", timeout=5_000)
    paused = page.evaluate("window.__probe()")
    row = paused["rows"][0]
    check(row["state"] == "paused", f"the row follows the shell's state event ({row})")
    check(row["bytes"] == 500_000_000,
          f"the bytes it already held are KEPT — a cancel is not a delete ({row['bytes']})")
    buttons = " ".join(paused["detail"]["buttons"])
    check("Cancel" not in buttons, f"the Cancel tile is gone once the row is paused ({buttons!r})")
    check("Resume" in buttons, f"…and Resume has replaced it ({buttons!r})")
    check("500 MB of 2.10 GB — resumable" in paused["body"],
          f"and the row says what it holds: {paused['body'][-220:]!r}")

    # ---- (b) the PRE-FIX shell: accepted, and silent — his report, reproduced
    print("   …then the same tap against a shell that answers NOTHING (the pre-fix behaviour)")
    open_frame(page, "bridge=1&cancel=silent", shots, "cancel-silent")
    page.get_by_role("button", name="Download").first.click()
    _wait_for(page, "window.__bridge.commands.some(c => c.c === 'download')", timeout=5_000)
    page.evaluate(
        """window.__announce([{ itemId: 'm-sholay', title: 'Sholay', state: 'downloading',
             bytes: 500_000_000, totalBytes: 2_100_000_000, mode: 'remux', error: null, url: null,
             contentType: null }])"""
    )
    _wait_for(page, "window.__probe().rows[0] && window.__probe().rows[0].state === 'downloading'")
    page.get_by_role("button", name="Cancel").first.click()
    _wait_for(page, "window.__bridge.commands.some(c => c.c === 'cancel')", timeout=5_000)
    page.wait_for_timeout(900)          # long enough for any event the shell might have sent
    stuck = page.evaluate("window.__probe()")
    stuck_row = stuck["rows"][0] if stuck["rows"] else {}
    # ⚠ This is a CONTRACT assertion, not an endorsement: the page's whole knowledge of the download
    # comes FROM the shell. With no second arrival it cannot move, and must not pretend to. It pins
    # where §7a lives — the fix belongs in Swift, and this is the app's shape until the shell speaks.
    check(stuck_row.get("state") == "downloading",
          f"⚠ with a SILENT shell the row cannot move — his report reproduced: {stuck_row}")
    check("Cancel" in " ".join(stuck["detail"]["buttons"]),
          f"…the Cancel tile stays, which is the frozen ring he described ({stuck['detail']['buttons']})")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shots", help="directory to write screenshots into")
    args = parser.parse_args()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        errors: list[str] = []

        print("0. is the dev server serving the code on disk?")
        if not served_module_is_fresh():
            print("\nSTALE — restart the dev server and run again (see the header).")
            browser.close()
            return 1

        # ⚠ A FRESH PAGE PER SCENARIO, and that is not tidiness: scenario 4 leaves a `<video>` PLAYING,
        # and a scenario that inherits it loads a document whose modules may never run (measured — the
        # frame's own script silently did not execute, and every assertion after it failed for a reason
        # that had nothing to do with the app). Each page also starts with no bridge state, no queue and
        # no route history, which is what a scenario should assume anyway.
        for run in (
            scenario_desktop_browser,
            scenario_affordance,
            scenario_download,
            scenario_downloads_screen,
            scenario_progress_spool,
            scenario_unreachable_server,
            scenario_cancel,
        ):
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.on("pageerror", lambda exc: errors.append(str(exc)))
            try:
                run(page, args.shots)
            except Exception as exc:  # noqa: BLE001
                check(False, f"{run.__name__} aborted: {type(exc).__name__}: {exc}")
            finally:
                page.close()

        if errors:
            check(False, f"the page threw {len(errors)} uncaught error(s): {errors[:3]}")
        browser.close()

    print(f"\n{SCENARIOS} scenarios, {len(PROBLEMS)} problem(s)")
    if PROBLEMS:
        print("FAIL")
        for problem in PROBLEMS:
            print(f"  - {problem}")
        return 1
    print("PASS — the offline page does what the plan says, on the real components")
    return 0


if __name__ == "__main__":
    sys.exit(main())
