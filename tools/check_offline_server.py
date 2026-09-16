#!/usr/bin/env python3
"""Judge phase B3's gate from the DEVICE's own evidence — one command, no arguments.

`docs/NATIVE_FEEL_AND_OFFLINE_PLAN.md` §6 states B3's gate as:

    the loopback server passes a Range test suite; the page round-trips a command and a progress event.

Both halves happen inside an `NWListener` and a `WKWebView`, on the Mac — nothing about them is visible from
here except the app's own file log. So this reads that log and answers the gate's questions one at a time:

  1. **did the server pass the Range suite?** The suite's cases are data (`OfflineProbeCases`), executed by
     `apple/scripts/check-offline-core.py` on Linux against the pure planner AND here, over a real loopback
     socket, by the app's own DEBUG probe. ⚠ Both are counted: a `FAIL` line is a finding however many
     cases passed before it, and a suite that stopped halfway is not a pass either — "10 of 16" is evidence
     that something went wrong, not a score.
  2. **did a command round-trip?** The page asks (`ping`, `list`) and reports what it got back through the
     existing instrumentation channel. That report is the only witness for the direction that matters:
     native answering a page is the half that cannot be faked by the page alone.
  3. **did a native event reach the page?** The page reports every event it receives. ⚠ A `state` event and
     a `progress` event travel the identical path (`window.__rkmOffline.emit` → the page's listener), so a
     `state` event proves the channel that carries progress works; the note says which kinds arrived.

⚠ **No argument is required, and that is deliberate.** B0's checker learned it the hard way: a documented
`"$LOG"` was never defined on the Mac, expanded to nothing, and the tool died with `IsADirectoryError: '.'`.
A placeholder in a command is a command that does not run.

⚠ **This reads ONE app run by default** (a probe is a single launch; the bridge half needs the page, so it is
the same launch). Unlike the B2 gate, whose story spans three launches, a window here would only let an OLD
pass answer for a NEW run — see the stale fixture in `--selftest`.

⚠ **Exit codes:** 0 both questions answered YES · 1 a check FAILED · 3 NOT EXERCISED (the probe never ran, or
nothing was downloaded to judge) — "we did not test it" and "it did not work" are different answers, and a
gate that conflates them is worse than no gate.

Usage:
    python3 tools/check_offline_server.py              # finds the simulator's container itself
    python3 tools/check_offline_server.py --log PATH
    python3 tools/check_offline_server.py --selftest    # falsify the TOOL (fixtures, no Mac)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# ⚠ The log-finding is NOT copied here. `check_offline_download.py` already learned the hard lessons — the
# manifest path, the container that moves on every reinstall, the per-run boundary — and two copies would
# drift apart. Same Mac, same app, same file.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_offline_download import (  # noqa: E402
    _booted_container,
    collect_log,
    find_log,
    find_manifest,
    window,
)

DEFAULT_RUNS = 1

# ------------------------------------------------------------------ the evidence patterns
P_STARTED = re.compile(r"offline probe · starting \(server=(\w+) bridge=(\w+)\)")
P_LISTENING = re.compile(r"offline server listening on (127\.0\.0\.1:\d+) \(loopback only\)")
P_CASE_PASS = re.compile(r"offline probe case (\S+?) PASS")
# ⚠ NO `$`, and that is a real bug this selftest caught: the log is joined into ONE string, so `$` anchors at
# the end of the whole log rather than the end of the line — and a failing case with anything after it was
# silently read as "no failures".
P_CASE_FAIL = re.compile(r"offline probe case (\S+?) FAIL(?: —|-)?[ \t]*(.*)")
P_SUMMARY = re.compile(r"offline probe summary (\d+)/(\d+) cases passed")
P_FAILURE_LINE = re.compile(r"offline probe failure · (\S+?):")
P_REAL_FILM = re.compile(r"offline probe · (real-film-head (PASS|FAIL|NOT EXERCISED)[^\n]*)")
P_REQUEST = re.compile(r"offline http (\w+) · (\S+) · → (\d{3}) ·")
P_PAGE_SEES = re.compile(r"offline bridge · the page sees the bridge: (true|false)(?: v(\d+))?")
P_COMMAND = re.compile(r"offline bridge · command (\S+) ok=(true|false)(?: count=(\d+))?(?:\s+—\s+(.*))?")
P_PAGE_RECEIVED = re.compile(r"offline bridge · page received event=(\S+?) item=(\S+?)(?: percent=(\d+))? "
                             r"carriesUrl=(true|false)")
P_BRIDGE_FAIL = re.compile(r"offline bridge probe FAIL — ([^\n]*)")
#: ⚠ The app's OWN view of each title. It exists because "nothing downloaded" and "downloaded, and the row
#: never changed" look identical from the log otherwise — the READY line is written by the same code path
#: that failed to refresh the row (found on the Mac 2026-09-16, from a screenshot).
P_ROWS = re.compile(r"offline probe · rows (\d+) total, (\d+) ready, (\d+) downloading, (\d+) failed")

#: The suite is `OfflineProbeCases.cases(size:)`. ⚠ A floor rather than an exact number on purpose: adding a
#: case must not fail this gate, while LOSING cases (a suite that stopped early) must.
MINIMUM_CASES = 16


def analyse(lines: list[str], manifest: dict | None = None) -> dict:
    """Pure: given one run's lines (and the manifest, for one question), answer the gate's questions."""
    text = "\n".join(lines)
    result: dict = {"questions": {}, "evidence": [], "notes": [], "fatal": None}

    def question(name: str, state: str, why: str, evidence: list[str]) -> None:
        result["questions"][name] = {"state": state, "why": why}
        result["evidence"].extend(evidence)

    started = P_STARTED.search(text)
    listening = P_LISTENING.search(text)
    passes = P_CASE_PASS.findall(text)
    failures = [match for match in P_CASE_FAIL.finditer(text)]
    summary = P_SUMMARY.search(text)
    failure_lines = P_FAILURE_LINE.findall(text)
    real_film = P_REAL_FILM.search(text)
    requests = P_REQUEST.findall(text)
    page_sees = P_PAGE_SEES.search(text)
    commands = P_COMMAND.findall(text)
    received = P_PAGE_RECEIVED.findall(text)
    bridge_failures = P_BRIDGE_FAIL.findall(text)

    # ---- the probe has to have run at all
    if not started and not passes and not summary:
        question("the Range suite passed", "NOT EXERCISED",
                 "the B3 probe never ran in this run — build and launch with "
                 "`-RKMOfflineServerProbe YES -RKMOfflineBridgeProbe YES` (see docs/PROGRESS.md)", [])
        question("a command round-tripped with the page", "NOT EXERCISED",
                 "the bridge probe never ran in this run", [])
        question("a native event reached the page", "NOT EXERCISED",
                 "the bridge probe never ran in this run", [])
        return result

    if started:
        result["evidence"].append(f"probe started (server={started.group(1)}, bridge={started.group(2)})")
    if listening:
        result["evidence"].append(f"the loopback listener came up on {listening.group(1)}")
    if requests:
        # ⚠ The SERVER's own line per request, not the client's: this is the half a page cannot fabricate.
        codes = sorted({status for _, _, status in requests})
        result["evidence"].append(f"the server answered {len(requests)} request(s): "
                                  f"status(es) {', '.join(codes)}")

    # ---- 1. the Range suite
    if failures:
        detail = failures[0].group(2).strip()
        question("the Range suite passed", "FAIL",
                 f"{len(failures)} case(s) FAILED — first: {failures[0].group(1)} ({detail})",
                 [line for line in lines if P_CASE_FAIL.search(line)][:6])
        result["fatal"] = f"the loopback server failed {len(failures)} range case(s)"
    elif bridge_failures:
        question("the Range suite passed", "FAIL",
                 f"the probe itself reported a failure: {bridge_failures[0]}",
                 [line for line in lines if P_BRIDGE_FAIL.search(line)])
        result["fatal"] = "the probe reported a failure"
    elif summary:
        passed, total = int(summary.group(1)), int(summary.group(2))
        if passed != total:
            question("the Range suite passed", "FAIL",
                     f"the suite stopped at {passed}/{total} cases — an incomplete run is not a pass",
                     [summary.group(0)])
            result["fatal"] = "the suite did not finish"
        elif total < MINIMUM_CASES:
            question("the Range suite passed", "FAIL",
                     f"only {total} case(s) ran and the suite has at least {MINIMUM_CASES} — the suite "
                     f"itself is wrong (check `OfflineProbeCases.cases(size:)`)",
                     [summary.group(0)])
            result["fatal"] = "the suite is missing cases"
        else:
            question("the Range suite passed", "PASS",
                     f"all {passed}/{total} cases passed, over a real loopback socket, including a byte "
                     f"comparison at the asked-for offset",
                     [summary.group(0)] + [line for line in lines if P_CASE_PASS.search(line)][:4])
    elif passes:
        question("the Range suite passed", "NOT EXERCISED",
                 f"{len(passes)} case(s) passed but no summary line was written — the suite did not finish",
                 [line for line in lines if P_CASE_PASS.search(line)][:3])
    else:
        question("the Range suite passed", "NOT EXERCISED",
                 "the probe started but no case ran — the artefact or the probe server did not come up",
                 [])

    if real_film:
        result["evidence"].append(real_film.group(1))
        if "NOT EXERCISED" in real_film.group(1):
            result["notes"].append(
                "no downloaded title exists on this device, so the one check that uses a REAL film "
                "(its length, over the bridge's own URL) could not run — download one and repeat")
        elif "FAIL" in real_film.group(1):
            result["notes"].append("⚠ the real-film check failed — the synthetic suite passing does not "
                                   "cover the bridge's own URL path")
        elif "urlsession" in text:
            result["notes"].append("the cases marked for it also passed through URLSession, the HTTP stack "
                                   "WebKit itself uses")

    # ---- 2. a command round-tripped
    ok_commands = {name: detail for name, ok, _count, detail in commands if ok == "true"}
    bad_commands = [(name, detail) for name, ok, _count, detail in commands if ok == "false"]

    if bad_commands:
        question("a command round-tripped with the page", "FAIL",
                 f"the page asked and got a refusal: {bad_commands[0][0]} — {bad_commands[0][1] or 'no detail'}",
                 [line for line in lines if P_COMMAND.search(line)])
    elif page_sees and page_sees.group(1) == "false":
        question("a command round-tripped with the page", "FAIL",
                 "the page cannot see the offline bridge at all — the injected global is missing or the "
                 "handler was registered without the reply form (`addScriptMessageHandler`)",
                 [line for line in lines if P_PAGE_SEES.search(line)])
    elif "ping" in ok_commands and "list" in ok_commands:
        question("a command round-tripped with the page", "PASS",
                 "the page asked `ping` and `list` and got answers back — the reply-capable handler is "
                 "wired in both directions",
                 [line for line in lines if P_COMMAND.search(line)])
    elif commands:
        question("a command round-tripped with the page", "NOT EXERCISED",
                 f"only {', '.join(sorted({name for name, *_ in commands}))} was answered — expected "
                 f"`ping` and `list`",
                 [line for line in lines if P_COMMAND.search(line)])
    else:
        question("a command round-tripped with the page", "NOT EXERCISED",
                 "no command was reported — either the bridge probe did not run, or its script did not "
                 "execute in the page", [])

    # ---- 3. a native event reached the page
    kinds = sorted({name for name, *_ in received})
    if received:
        question("a native event reached the page", "PASS",
                 f"the page received {len(received)} event(s): {', '.join(kinds)}"
                 + (" — a `state` event and a `progress` event use the SAME path "
                    "(`window.__rkmOffline.emit` → the page's listener), so the progress channel is proved"
                    if "progress" not in kinds else ""),
                 [line for line in lines if P_PAGE_RECEIVED.search(line)][:6])
    else:
        question("a native event reached the page", "NOT EXERCISED",
                 "the page received nothing. ⚠ This needs at least one title the downloader knows about "
                 "(every title is announced once); with none, `list` still round-trips but there is nothing "
                 "to emit — see the note below", [])

    # ---- 4. do the app's own rows agree with what is on disk?
    # ⚠ THE **LAST** ROW SUMMARY, NOT THE FIRST — and this is a real trap, not tidiness: the probe logs one
    # at page load (usually `0 ready`, because a fresh install has nothing) and another the moment a title
    # becomes playable. Reading the first would call a perfectly good round a STALE ROW.
    rows_found = P_ROWS.findall(text)
    rows = rows_found[-1] if rows_found else None
    if rows:
        total, ready, downloading, failed = (int(value) for value in rows)
        result["evidence"].append(f"the app's rows: {total} total, {ready} ready, {downloading} downloading, "
                                  f"{failed} failed")
        if ready > 0:
            question("the app's own rows agree with the manifest", "PASS",
                     f"{ready} of {total} row(s) are ready, which is what a published file looks like",
                     [line for line in lines if P_ROWS.search(line)])
        else:
            # ⚠ THE SIGNATURE OF A STALE ROW: the file is on disk (the manifest says ready) and the app's own
            # row says something else. It is a FAIL, not a "not exercised", because the UI is lying about a
            # file the user can play — and the log's `offline READY` line cannot show it.
            ready_records = [record for record in (manifest or {}).get("items", [])
                             if record.get("state") == "ready"]
            if ready_records:
                question("the app's own rows agree with the manifest", "FAIL",
                         f"the manifest holds {len(ready_records)} ready record(s) but the app's rows show "
                         f"{ready} ready — the row is STALE. The download finished and the UI still says "
                         f"`downloading`, which is a bug in the completion path, not a test setup problem",
                         [line for line in lines if P_ROWS.search(line)])
                result["fatal"] = "a ready file whose row never changed"
            else:
                question("the app's own rows agree with the manifest", "NOT EXERCISED",
                         "no title is ready yet — nothing to agree or disagree about",
                         [line for line in lines if P_ROWS.search(line)])
    else:
        question("the app's own rows agree with the manifest", "NOT EXERCISED",
                 "the probe did not report the app's rows (an older build?)", [])

    if not received:
        result["notes"].append(
            "the event direction is proved by ANY event. To exercise it: download a title, then relaunch "
            "WITHOUT reinstalling (⚠ `mac-round.sh --sim` REINSTALLS, and a reinstall gives the app a NEW "
            "container — the film you just downloaded would be stranded in the old one, which is exactly "
            "how this state was reached):\n"
            "         xcrun simctl terminate booted com.helloraj1986.rkmcinema.ios\n"
            "         xcrun simctl launch booted com.helloraj1986.rkmcinema.ios "
            "-RKMOfflineServerProbe YES -RKMOfflineBridgeProbe YES")

    return result


def verdict_code(result: dict) -> int:
    states = [entry["state"] for entry in result["questions"].values()]
    if result.get("fatal"):
        return 1
    if "FAIL" in states:
        return 1
    if states and all(state == "PASS" for state in states):
        return 0
    return 3


def report(result: dict, where: str) -> int:
    print(f"evidence: {where}")
    print("")
    for name, entry in result["questions"].items():
        mark = {"PASS": "YES ", "FAIL": "NO  ", "NOT EXERCISED": "????"}[entry["state"]]
        print(f"{mark} {name}")
        print(f"       {entry['why']}")
    if result["evidence"]:
        print("\nevidence lines:")
        for line in result["evidence"][:14]:
            print(f"   {line.strip()[:170]}")
    if result["notes"]:
        print("\nnotes:")
        for note in result["notes"]:
            print(f"   · {note}")

    code = verdict_code(result)
    print("")
    if code == 0:
        print("PASS — the loopback server passed the suite and the bridge worked in both directions.")
    elif code == 1:
        print("FAIL — see the NO above. (A failed check is a real finding, not a test setup problem.)")
    else:
        print("NOT EXERCISED — nothing was measured. Run the checklist in docs/PROGRESS.md: rebuild, then "
              "launch with `-RKMOfflineServerProbe YES -RKMOfflineBridgeProbe YES`.")
    return code


# -------------------------------------------------------------------------------------------- selftest

STAMP = "2026-09-16 20:00:00.000"
RUN_MARKER = "offline session ready"


def _run(*lines: str, stamp: str = STAMP) -> list[str]:
    out = [f"[{stamp}] I [-------] offline  {RUN_MARKER} · id x.offline · wifiOnly=false · "
           f"autoResume=true · store=open"]
    out.extend(f"[{stamp}] I [-------] offline  {line}" for line in lines)
    return out


def _case_lines(total: int = 16, passing: int = 16) -> list[str]:
    ids = [f"case-{index:02d}" for index in range(1, total + 1)]
    lines = [f"offline probe case {name} PASS" for name in ids[:passing]]
    lines.extend(f"offline probe case {name} FAIL — status 200, expected 206" for name in ids[passing:])
    lines.append(f"offline probe summary {passing}/{total} cases passed")
    return lines


FIXTURE_FULL = _run(
    "offline probe · starting (server=true bridge=true)",
    "offline server listening on 127.0.0.1:51234 (loopback only)",
    *_case_lines(),
    "offline probe case head-no-range+urlsession PASS",
    "offline http GET · /offline/<token>.mp4 · → 206 · size 1.00 MB · sent 512.00 KB · "
    "range bytes 524288-1048575/1048576 · asked \"bytes=524288-\"",
    "offline http HEAD · /offline/<token>.mp4 · → 200 · size 1.00 MB · sent 0 B · range — · asked no range",
    "offline probe · rows 1 total, 1 ready, 0 downloading, 0 failed",
    "offline probe · real-film-head PASS — 1.88 GB, video/mp4",
    "offline probe · finished (the probe artefact was removed)",
    "offline bridge · the page sees the bridge: true v1",
    "offline bridge · page received event=state item=abc123 carriesUrl=true",
    "offline bridge · page received event=progress item=abc123 percent=42 carriesUrl=false",
    "offline bridge · command ping ok=true count=0",
    "offline bridge · command list ok=true count=1",
)

FIXTURE_SHIFTED = _run(
    "offline probe · starting (server=true bridge=true)",
    "offline server listening on 127.0.0.1:51234 (loopback only)",
    "offline probe case get-mid-open FAIL — the FIRST byte is not the file's byte at 524288 — a shifted "
    "range returns the right count and the wrong film",
    "offline probe case get-open-range PASS",
    "offline probe summary 15/16 cases passed",
    "offline bridge · the page sees the bridge: true v1",
    "offline bridge · command ping ok=true count=0",
    "offline bridge · command list ok=true count=1",
    "offline bridge · page received event=state item=abc123 carriesUrl=true",
)

FIXTURE_HALF_SUITE = _run(
    "offline probe · starting (server=true bridge=true)",
    "offline probe case head-no-range PASS",
    "offline probe case get-whole PASS",
    "offline probe summary 10/16 cases passed",
    "offline bridge · the page sees the bridge: true v1",
    "offline bridge · command ping ok=true count=0",
    "offline bridge · command list ok=true count=1",
    "offline bridge · page received event=state item=abc123 carriesUrl=true",
)

FIXTURE_NO_ROWS = _run(
    "offline probe · starting (server=true bridge=true)",
    "offline server listening on 127.0.0.1:51234 (loopback only)",
    *_case_lines(),
    "offline probe · real-film-head NOT EXERCISED — no downloaded title on this device yet",
    "offline bridge · the page sees the bridge: true v1",
    "offline bridge · command ping ok=true count=0",
    "offline bridge · command list ok=true count=0",
)

FIXTURE_COMMAND_REFUSED = _run(
    "offline probe · starting (server=true bridge=true)",
    *_case_lines(),
    "offline bridge · the page sees the bridge: true v1",
    "offline bridge · command ping ok=false — the handler did not answer",
    "offline bridge · page received event=state item=abc123 carriesUrl=true",
)

FIXTURE_NO_BRIDGE = _run(
    "offline probe · starting (server=true bridge=true)",
    *_case_lines(),
    "offline bridge · the page sees the bridge: false",
    "offline bridge · page received event=state item=abc123 carriesUrl=true",
)

FIXTURE_NOT_RUN = _run(
    "offline session ready · id x.offline",
)

#: ⚠ A finished download whose row never changed: the server suite is green, the commands answer, and the
#: app's OWN rows say `downloading` — while the file sits on disk.
#: ⚠ A real round logs TWO row summaries: one at page load (`0 ready` — a fresh install after the rebuild put
#: the film in a new container) and one when the download lands. The checker must read the LAST one.
FIXTURE_TWO_SUMMARIES = _run(
    "offline probe · starting (server=true bridge=true)",
    "offline server listening on 127.0.0.1:51234 (loopback only)",
    "offline probe · rows 0 total, 0 ready, 0 downloading, 0 failed",
    *_case_lines(),
    "offline bridge · the page sees the bridge: true v1",
    "offline READY · 1.54 GB · mode remux · verified size+ETag · took 190s (8.1 MB/s)",
    "offline probe · rows 1 total, 1 ready, 0 downloading, 0 failed",
    "offline probe · real-film-head PASS — 1.54 GB, video/mp4",
    "offline bridge · page received event=state item=abc123 carriesUrl=true",
    "offline bridge · command ping ok=true count=0",
    "offline bridge · command list ok=true count=1",
)

FIXTURE_STALE_ROW = _run(
    "offline probe · starting (server=true bridge=true)",
    "offline server listening on 127.0.0.1:51234 (loopback only)",
    *_case_lines(),
    "offline probe · rows 1 total, 0 ready, 1 downloading, 0 failed",
    "offline READY · 1.54 GB · mode remux · verified size+ETag · took 190s (8.1 MB/s)",
    "offline bridge · the page sees the bridge: true v1",
    "offline bridge · command ping ok=true count=0",
    "offline bridge · command list ok=true count=1",
    "offline bridge · page received event=progress item=abc123 percent=41 carriesUrl=false",
)


#: A manifest that says a film is on disk — the other half of the stale-row case.
MANIFEST_READY = {"version": 1, "items": [{"item_id": "abc123", "title": "The Book of Life",
                                           "state": "ready", "bytes": 1540000000,
                                           "total_bytes": 1540000000, "verification": "size_etag"}]}


def selftest() -> int:
    cases = [
        ("the real round: suite green, both directions proved", FIXTURE_FULL, None, 0,
         "all 16/16 cases passed"),
        ("⚠ a SHIFTED range: the right byte count from the wrong offset", FIXTURE_SHIFTED, None, 1,
         "get-mid-open"),
        ("a suite that stopped halfway", FIXTURE_HALF_SUITE, None, 1, "stopped at 10/16"),
        ("no downloaded title, so the event direction is unproven", FIXTURE_NO_ROWS, None, 3,
         "received nothing"),
        ("a command the page could not get an answer to", FIXTURE_COMMAND_REFUSED, None, 1, "got a refusal"),
        ("the page cannot see the bridge at all", FIXTURE_NO_BRIDGE, None, 1, "cannot see the offline bridge"),
        ("the probe never ran", FIXTURE_NOT_RUN, None, 3, "probe never ran"),
        ("a STALE pass: an older run passed, this one did not (1-run window)",
         FIXTURE_FULL + FIXTURE_NOT_RUN, None, 3, "probe never ran"),
        # ⚠⚠ The bug the first real B3 round found from a screenshot: the film is on disk (the manifest says
        # so) and the app's own row still says `downloading`. It must NOT be reported as "not exercised".
        ("⚠ a STALE ROW: the manifest says ready and the app's rows say downloading",
         FIXTURE_STALE_ROW, MANIFEST_READY, 1, "the row is STALE"),
        ("⚠ the real order: nothing downloaded at page load, then a film lands", FIXTURE_TWO_SUMMARIES,
         MANIFEST_READY, 0, "all 16/16 cases passed"),
        ("the same suite with no manifest to compare against",
         FIXTURE_STALE_ROW, None, 3, "nothing to agree or disagree about"),
    ]

    failures = 0
    for index, (label, lines, manifest, expected_code, expected_text) in enumerate(cases, start=1):
        run, _where = window(lines, DEFAULT_RUNS)
        result = analyse(run, manifest)
        code = verdict_code(result)
        body = json.dumps(result)
        ok = code == expected_code and expected_text in body
        if not ok:
            failures += 1
        print(f"{index:02d}. {'ok  ' if ok else 'FAIL'} {label} — expected exit {expected_code} and "
              f"`{expected_text}`, got exit {code}")
        if not ok:
            print(f"    {body[:500]}")

    print("")
    if failures:
        print(f"FAIL — {failures} of {len(cases)} selftest case(s) wrong. The TOOL is wrong: fix it before "
              f"trusting any verdict it gives.")
        return 1
    print(f"PASS — {len(cases)}/{len(cases)} selftest cases behave: the tool can fail, it can say "
          f"'not exercised' instead of guessing, and an OLD pass cannot answer for a NEW run.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--selftest", action="store_true",
                        help="run the fixture cases that falsify the tool itself (no Mac needed)")
    parser.add_argument("--log", type=Path, default=None, help="the log file to read (default: find it)")
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS,
                        help=f"how many of the newest app runs to judge (default {DEFAULT_RUNS})")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()

    container = None
    if args.log is not None:
        if not args.log.exists():
            print(f"no such log file: {args.log}", file=sys.stderr)
            return 3
        lines = collect_log(args.log)
        where = f"{args.log} ({len(lines)} lines)"
        container = _booted_container()
    else:
        path, why, container = find_log(container)
        if path is None:
            print(f"cannot read the app's log: {why}", file=sys.stderr)
            return 3
        lines = collect_log(path)
        where = f"{why} ({len(lines)} lines)"

    manifest_path, manifest_note, _container = find_manifest(container)
    manifest: dict | None = None
    if manifest_path is not None:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            print(f"manifest could not be parsed: {error}", file=sys.stderr)
            manifest_note = f"{manifest_note} — UNREADABLE ({error})"

    run, run_note = window(lines, max(1, args.runs))
    print(f"offline loopback gate — {run_note}")
    print(f"manifest: {manifest_note}")
    return report(analyse(run, manifest), where)


if __name__ == "__main__":
    sys.exit(main())
