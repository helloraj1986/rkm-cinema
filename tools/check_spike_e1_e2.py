#!/usr/bin/env python3
"""Read the E1/E2 spike's log and say whether the offline plan may proceed — phase B0's gate.

`docs/NATIVE_FEEL_AND_OFFLINE_PLAN.md` §5 names E1 as *"the one that changes the design"* and §8 says
nothing in Workstream B gets written before it. The gate is specific, so this makes it one command:

    python3 tools/check_spike_e1_e2.py              # finds the log itself (simulator)
    python3 tools/check_spike_e1_e2.py <path>       # or point it at one
    python3 tools/check_spike_e1_e2.py --selftest   # falsify the tool itself (see the bottom)

⚠ **The path argument is OPTIONAL because of a real wasted round trip.** The docs used to say
`check_spike_e1_e2.py "$LOG"` — with `$LOG` never defined on the Mac, `"$LOG"` expanded to the empty
string, `Path("")` became `.`, and the tool died with `IsADirectoryError: '.'`. A placeholder in a
command is a command that does not run. Now it finds the file, prints where it read from, and says
something useful if it cannot.

⚠⚠ **AND IT READS ONE RUN, NOT THE WHOLE FILE — because the log is APPEND-ONLY ACROSS RUNS.** The app
writes one `rkm-ios.log` that rotates to archives, so the second round's log still contains the first
round's lines. Every check here used to take the **first** match in the whole file, which produced two
faults that both only bite on a *second* run — the exact round this tool exists for:

  * a **stale pass** — once a run passed, `seek -> ok` and `RESULT play=ok` were in the file forever, so
    a later run that FAILED still reported **PASS**. A gate that cannot fail after its first success is
    not a gate.
  * a **stale failure** — the first run's `mediaError=code=4` would be printed as the *new* run's
    evidence, and `no [spike]` would be read as "[spike] says the codec failed".

So the checks run over **the newest spike run in the file**: the lines at or after the last
`offline spike: starting` marker (matched by timestamp, so rotation/archive order cannot affect it), and
the tool says which run it read and how many earlier lines it ignored. ⚠ `[rkm-caps]` is deliberately
still read from the **whole** file: it is a platform capability, not a per-run measurement — but the case
that matters for E2 (the **loopback** page's own line) can only come from the newest run anyway.

It needs the proof of **five** things, and two of them come from DIFFERENT halves of the system:

  1. the web view reached the loopback server at all      `loopback request: GET /probe.mp4`
  2. the server answered a byte range with a **206**      `serving 206 Partial Content`
  3. WebKit's media stack parsed the file                 `[spike] [loopback] metadata ok WxH`
  4. a SEEK completed                                     `[spike] [loopback] seek to … -> ok`
  5. playback started                                     `[spike] [loopback] RESULT play=ok`

⚠ 1 and 2 are why the page's own report is not enough: *"seek -> ok"* with a `200` on the wire would
mean the whole file was re-read, not seeked — the page cannot tell those apart, the server can.
`[scheme]` lines are recorded as INFORMATION, never as a pass/fail: the plan EXPECTS the
`WKURLSchemeHandler` to fail, so a pass there is a bonus that simplifies §4.1, not a requirement.
"""
from __future__ import annotations

import argparse
import io
import re
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

LOOPBACK = "[loopback]"
SCHEME = "[scheme]"

BUNDLE_ID = "com.helloraj1986.rkmcinema.ios"
#: Where `RollingFileLog.defaultDirectory(appFolder: "RKMCinema")` puts it, inside the app container.
LOG_SUFFIX = Path("Library/Application Support/RKMCinema/Logs")
LOG_NAME = "rkm-ios.log"

#: The line the app logs when the spike starts — the ONLY per-run boundary in the file.
RUN_MARKER = "offline spike: starting"
#: `[2026-09-14 21:42:05.280]` — the app's own line format.
STAMP = re.compile(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\]")


def _stamp(line: str) -> str | None:
    match = STAMP.search(line)
    return match.group(1) if match else None


def newest_run(lines: list[str]) -> tuple[list[str], str]:
    """The lines belonging to the newest spike run, and a sentence saying which run that was.

    Timestamp-matched rather than positional: the checker concatenates the current log **plus its
    archives**, and archive order is not chronological (`rkm-ios.1.log` sorts before `rkm-ios.2.log`
    and both before the live file), so counting lines from the end would pick the wrong run.

    ⚠ With no marker anywhere (a log copied out of another format, or an older build) it falls back to
    the whole file and SAYS SO, rather than silently reporting on nothing.
    """
    marks = [stamp for line in lines if RUN_MARKER in line and (stamp := _stamp(line))]
    if not marks:
        return lines, (f"no `{RUN_MARKER}` marker in the log — analysing EVERY line in the file "
                       f"(a spike from an older build, or a hand-made log)")
    latest = max(marks)
    window = [line for line in lines if (stamp := _stamp(line)) is not None and stamp >= latest]
    return window, (f"run starting {latest} — {len(lines) - len(window)} earlier line(s) from previous "
                    f"runs ignored")


def _simulator_containers() -> list[Path]:
    root = Path.home() / "Library/Developer/CoreSimulator/Devices"
    if not root.is_dir():
        return []
    found: list[Path] = []
    for candidate in root.glob("*/data/Containers/Data/Application/*"):
        directory = candidate / LOG_SUFFIX
        if (directory / LOG_NAME).exists() or directory.is_dir():
            found.append(directory)
    return found


def find_log() -> tuple[Path | None, str]:
    """The newest logging directory we can see, and a sentence about how we looked."""
    # 1. The booted simulator, the authoritative answer when the app is installed.
    try:
        result = subprocess.run(
            ["xcrun", "simctl", "get_app_container", "booted", BUNDLE_ID, "data"],
            capture_output=True, text=True, timeout=20,
        )
        if result.returncode == 0:
            container = Path(result.stdout.strip())
            if container.is_dir():
                directory = container / LOG_SUFFIX
                if (directory / LOG_NAME).exists():
                    return directory, f"booted simulator app container ({container.name[:8]}…)"
                return directory, "booted simulator app container — the app has not written a log yet"
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass  # no xcrun here: not a Mac, or Xcode's tools are not on PATH

    # 2. Any simulator on this Mac, without needing one booted.
    directories = _simulator_containers()
    if directories:
        directories.sort(key=lambda d: (d / LOG_NAME).stat().st_mtime if (d / LOG_NAME).exists() else 0,
                         reverse=True)
        return directories[0], f"a simulator container ({len(directories)} found, newest used)"

    return None, "no simulator container found"


def collect(directory: Path, primary: Path | None = None) -> tuple[str, list[Path]]:
    """Every line, current file plus archives — ⚠ rotation can move spike lines out of the current
    file, and a gate that silently reads only the newest 2 MB would report "no evidence" for a run
    that happened just before a rotate.

    ⚠ **`primary` IS NOT OPTIONAL IN SPIRIT.** This used to glob `rkm-ios*.log` unconditionally, so a
    log handed in under ANY OTHER NAME contributed **zero lines** and every check reported "no
    evidence" — a silent total misread, caught by the falsification suite (which expects a passing log
    to PASS). When a path is given, that file is read first and the archives are added around it; only
    auto-discovery globs.
    """
    if primary is not None:
        files = [primary] + sorted(p for p in directory.glob("rkm-ios*.log") if p != primary)
    else:
        files = sorted(directory.glob("rkm-ios*.log"))
    text = ""
    for path in files:
        text += path.read_text(encoding="utf-8", errors="replace") + "\n"
    return text, files


def usage_help() -> None:
    print(
        "\nHow to point it at the log yourself:\n"
        "\n  SIMULATOR (the spike's own case):\n"
        "    xcrun simctl get_app_container booted "
        f"{BUNDLE_ID} data\n"
        f"    # then: <that path>/{LOG_SUFFIX}/{LOG_NAME}\n"
        "\n  DEVICE (the file is NOT on this Mac — apple/LOGGING.md §7):\n"
        "    Xcode → Window → Devices and Simulators → your iPad → Download Container…\n"
        "    then: <downloaded>.xcappdata/AppData/Library/Application Support/RKMCinema/Logs/rkm-ios.log\n"
        "\n  OR just make the app say where it is — it logs the path at launch:\n"
        "    xcrun simctl spawn booted log stream --predicate 'subsystem CONTAINS \"rkm\"' | grep 'file log:'\n"
    )


def analyse(lines: list[str], everything: list[str], out=print) -> dict:
    """Judge ONE run: `lines` is the run's window, `everything` the whole file (for `[rkm-caps]`)."""
    problems: list[str] = []
    notes: list[str] = []
    # ⚠ "the experiment did not run" and "the experiment ran and failed" are DIFFERENT ANSWERS, and
    # conflating them is how a spike bug gets written into the plan as a fact about WebKit. Anything
    # here means: no evidence was produced, so nothing may be concluded either way.
    inconclusive: list[str] = []

    def evidence(pattern: str, source: list[str] | None = None) -> str | None:
        rx = re.compile(pattern)
        for line in (lines if source is None else source):
            if rx.search(line):
                return line.strip()
        return None

    def every(pattern: str, source: list[str] | None = None) -> list[str]:
        rx = re.compile(pattern)
        return [line.strip() for line in (lines if source is None else source) if rx.search(line)]

    # ------------------------------------------------------------------ E1
    out("\nE1 · does media play from loopback inside the WKWebView, with seeking?")

    reached = evidence(r"loopback request: GET /probe\.mp4")
    page_served = evidence(r"loopback request: GET /probe\.html")
    if reached:
        out(f"  ✅ the web view reached the server — {reached}")
    elif page_served:
        # ⚠ THE NARROW, DECISIVE DISTINCTION. The probe page came FROM the loopback origin, so that
        # origin demonstrably works — and the media element still never asked for the file. That is a
        # finding about WebKit's media stack (an E1 negative), not a spike bug.
        problems.append(
            "the probe PAGE was served from the loopback origin (so the origin works) and the media "
            "element still never requested /probe.mp4 — the media stack refused the URL without "
            "requesting it, which is a real E1 result"
        )
        out("  ❌ the page loaded from loopback, but the media element never asked for the file")
    else:
        inconclusive.append(
            "nothing was requested from the loopback server at all — not even the probe page — so the "
            "transport was never exercised. This is a spike/plumbing fault (ATS, origin, port), not a "
            "statement about the media stack"
        )
        problems.append(
            "no `loopback request:` line at all — the web view never reached 127.0.0.1. "
            "That is NOT a codec answer: it points at ATS/origin, not at the media stack"
        )
        out("  ❌ the web view never reached the loopback server (not even for the page)")

    partial = evidence(r"serving 206 Partial Content")
    whole = evidence(r"serving 200 OK whole file")
    if partial:
        out(f"  ✅ the server answered a BYTE RANGE with 206 — {partial}")
    elif whole:
        problems.append(
            "the server answered 200 for the whole file, not 206 for a range — so any 'seek' the page "
            "reported re-read the file instead of seeking"
        )
        out(f"  ❌ no 206; the whole file was sent — {whole}")
    else:
        # ⚠ ONLY when a request actually arrived: a request with no matching `serving` line means no
        # bytes were sent, and that is a spike fault, not a WebKit finding. With no request at all, the
        # `reached`/`page_served` branch above has already classified it.
        if reached:
            inconclusive.append(
                "a request for probe.mp4 arrived and the server answered NOTHING — no media bytes were "
                "sent, so the failure the page reports is not about WebKit at all. The server's own "
                "trace below says why (typically `no such file for /probe.mp4`)"
            )
            problems.append(
                "the server logged no served response for probe.mp4 — ⚠ a request WITHOUT a matching "
                "`serving` line means no media bytes were sent at all, so whatever the page reports "
                "next is not a statement about WebKit. The server's own trace is printed below"
            )
        else:
            problems.append("the server logged no served response for probe.mp4 (and no request either)")
        out("  ❌ the server logged no response")

    metadata = evidence(r"\[spike\] \[loopback\] metadata ok")
    if metadata:
        out(f"  ✅ WebKit parsed the media — {metadata}")
    else:
        # ⚠ The specific error is checked BEFORE the timeout: a `loadedmetadata=TIMEOUT` that also
        # carries `mediaError=code=N` is a codec/container refusal, and calling that "timed out"
        # would send the next session looking at the transport instead of at the file.
        errored = evidence(r"\[spike\] \[loopback\] RESULT .*mediaError=code=(\d+)")
        timed_out = evidence(r"\[spike\] \[loopback\] RESULT loadedmetadata=TIMEOUT")
        if errored:
            problems.append(f"the media element errored over loopback — {errored}")
            out(f"  ❌ media error — {errored}")
        elif timed_out:
            problems.append("`loadedmetadata=TIMEOUT`: the media stack never parsed the file over loopback")
            out(f"  ❌ timed out loading metadata — {timed_out}")
        else:
            problems.append("no `metadata ok` line: the probe never got as far as loading the file")
            out("  ❌ no metadata result at all")

    seek = evidence(r"\[spike\] \[loopback\] seek to [\d.]+ -> ok")
    if seek:
        out(f"  ✅ a SEEK completed — {seek}")
    else:
        failed = evidence(r"\[spike\] \[loopback\] seek to [\d.]+ -> (?!ok)\S+")
        problems.append("the seek did not complete" + (f" — {failed}" if failed else " (no seek line)"))
        out(f"  ❌ seeking failed — {failed or 'no seek line'}")

    played = evidence(r"\[spike\] \[loopback\] RESULT play=ok")
    if played:
        out(f"  ✅ playback started — {played}")
    else:
        problems.append("`[loopback] RESULT play=` never reported ok")
        out("  ❌ playback did not report ok")

    any_spike = evidence(r"\[spike\]")
    if not any_spike:
        inconclusive.append(
            "no `[spike]` lines in this run — the spike never ran. It needs the app launched with "
            "`-RKMOfflineSpike YES`, and a stored server address (the probe file comes from it)"
        )
        problems.append(
            "NO `[spike]` lines in this run — the spike never ran. It needs the app launched "
            "with `-RKMOfflineSpike YES`, and a stored server address (the probe file comes from it)"
        )

    # ------------------------------------------------------------------ the server's own trace
    # ⚠⚠ ADDED BECAUSE ITS ABSENCE COST A MAC ROUND. The first real run showed a request with no
    # matching response, and the reason (`no such file for /probe.mp4` — the file was stored under the
    # name it had on HIS server while the page asked for `/probe.mp4`) was sitting in the log the whole
    # time, unprinted. A gate that hides the evidence it is judging is half a gate.
    trace = [line.strip() for line in lines
             if "loopback" in line.lower() or "offline spike:" in line.lower()]
    out("\nThe server's own trace (this run's loopback / spike lines, whether or not a check matched):")
    if trace:
        for line in trace:
            out(f"  · {line}")
    else:
        out("  (none — the loopback server never logged anything in this run)")

    # ---------------------------------------------------------------- the bonus
    scheme_meta = evidence(r"\[spike\] \[scheme\] metadata ok")
    scheme_failed = evidence(r"\[spike\] \[scheme\] RESULT")
    out("\n   bonus · the WKURLSchemeHandler comparison (the plan EXPECTS this to fail)")
    if scheme_meta:
        notes.append(
            "the scheme handler ALSO carried media — §4.1/§4.4 can be simplified (no port, no server)"
        )
        out(f"  ℹ️  it WORKED — {scheme_meta}")
    elif scheme_failed:
        out(f"  ℹ️  it failed as expected — {scheme_failed}")
    else:
        out("  ℹ️  no `[scheme]` result in the log")

    # ------------------------------------------------------------------ E2
    # ⚠ From EVERYTHING, not the run window: the app page's own capability line is written when the
    # web shell loads, which can be before the spike starts. The line that decides E2 is the loopback
    # page's, and that one can only come from the newest run.
    out("\nE2 · is a service worker available, and what does storage look like?")
    caps = every(r"\[rkm-caps\]", everything)
    if caps:
        for line in caps:
            out(f"  {line}")
        match = re.search(r"sw=(true|false)", " ".join(caps))
        origins: list[str] = []
        for line in caps:
            found = re.search(r"origin=(\S+)", line)
            if found and found.group(1) not in origins:
                origins.append(found.group(1))
        origins.sort()
        if len(origins) > 1:
            # ⚠ THE DISTINCTION THAT MAKES E2 DECISIVE. `sw=false` on a plain-HTTP origin proves
            # nothing (no secure context, no service worker, in any browser); `sw=false` on a
            # POTENTIALLY TRUSTWORTHY origin (127.0.0.1) is a fact about WKWebView. `persist=` is the
            # tell that the two origins differ in kind: navigator.storage only exists in a secure one.
            out(f"  ⚠ {len(origins)} origins measured: {' · '.join(origins)} — a secure origin "
                f"(127.0.0.1/localhost) exposes `navigator.storage` where the plain-HTTP one cannot, so "
                f"read `sw=` on the SECURE origin as the platform answer.")
        if match:
            if match.group(1) == "false":
                notes.append(
                    "sw=false ⇒ a service worker is NOT available to this WKWebView: A0's cache headers "
                    "ARE the offline-shell story, and no service-worker work gets planned"
                )
            else:
                notes.append("sw=true ⇒ a service worker IS available; decide deliberately whether to use it")
    else:
        problems.append(
            "no `[rkm-caps]` line — E2 did not run. It rides the app's OWN page, so it needs the app "
            "loaded (not just the spike sheet), and the app must have completed one launch"
        )
        out("  ❌ no `[rkm-caps]` line at all")

    return {"problems": problems, "inconclusive": inconclusive, "notes": notes}


def verdict_code(result: dict) -> int:
    # ⚠ EXIT 3, NOT 1, ON PURPOSE. A caller (or the next session) must be able to tell "the experiment
    # says no" from "the experiment did not happen" — the second one is a bug in the spike, and treating
    # it as a finding about WebKit would rewrite a good plan for a bad reason.
    if result["inconclusive"]:
        return 3
    return 1 if result["problems"] else 0


def report(result: dict) -> int:
    print("\n" + "=" * 78)
    if result["inconclusive"]:
        print("INCONCLUSIVE — the experiment produced NO evidence, so the plan is neither confirmed nor")
        print("               contradicted. This is a fault in the SPIKE, not a fact about WebKit:")
        for reason in result["inconclusive"]:
            print(f"  - {reason}")
        print("\nFix that and run it again. ⚠ Do NOT read the rows below as a verdict:")
        for problem in result["problems"]:
            print(f"  (side effect) {problem}")
        return 3

    if result["problems"]:
        print("FAIL — the experiment RAN and the plan may NOT proceed as written. Missing evidence:")
        for problem in result["problems"]:
            print(f"  - {problem}")
        print(
            "\nWhat that means: E1 is the experiment the whole of Workstream B rests on "
            "(plan §5, §7 risk #1, §8). If loopback cannot play WITH SEEKING, offline playback has to "
            "be handed to a native AVPlayer screen outside the web UI — a different, larger piece of "
            "work — and §4.4–4.6 get rewritten BEFORE anything is built."
        )
        return 1

    print("PASS — E1's gate is met: a file served from 127.0.0.1 played inside the web view, was SEEKED")
    print("       (proved by a 206 on the wire as well as the page's own report), and started playing.")
    print("       ⇒ Workstream B may proceed as written (plan §6: B1 → B2 → B3 → B4 → B5).")
    if result["notes"]:
        print("\nThings to decide anyway:")
        for note in result["notes"]:
            print(f"  - {note}")
    return 0


def _run_of(text: str) -> str:
    """The part of a log that the newest run owns — for the fixtures and for a pasted log tail."""
    lines = text.splitlines()
    window, _ = newest_run(lines)
    return "\n".join(window)


# -------------------------------------------------------------------------------------------- selftest

def _fixture_pass(stamp: str) -> str:
    return (
        f"[{stamp} 21:00:00.000] I [----] app offline spike: starting (E1 loopback + E2 caps)\n"
        f"[{stamp} 21:00:00.100] I [----] net offline spike: probe file 1128375 B\n"
        f"[{stamp} 21:00:00.200] I [----] net loopback: serving files from /containers/Spike\n"
        f"[{stamp} 21:00:00.300] I [----] net loopback request: GET /probe.html\n"
        f"[{stamp} 21:00:00.400] I [----] net loopback request: GET /probe.mp4 · Range: bytes=0-1\n"
        f"[{stamp} 21:00:00.410] I [----] net loopback: serving 206 Partial Content bytes 0-1/1128375\n"
        f"[{stamp} 21:00:01.000] V [----] web console.log: [spike] [loopback] loading probe.mp4\n"
        f"[{stamp} 21:00:01.200] V [----] web console.log: [spike] [loopback] metadata ok 640x360 duration=5.05\n"
        f"[{stamp} 21:00:01.400] V [----] web console.log: [spike] [loopback] seek to 2.52 -> ok at 2.52\n"
        f"[{stamp} 21:00:01.600] V [----] web console.log: [spike] [loopback] RESULT play=ok mediaError=none\n"
        f"[{stamp} 21:00:01.700] V [----] web console.log: [rkm-caps] sw=false fullscreen=true "
        f"origin=http://127.0.0.1:57949 persist=probe\n"
    )


def _fixture_codec_error(stamp: str) -> str:
    """Bytes ARE served (206), and the element still refuses them: the transport ran and failed."""
    return (
        f"[{stamp} 22:00:00.000] I [----] app offline spike: starting (E1 loopback + E2 caps)\n"
        f"[{stamp} 22:00:00.400] I [----] net loopback request: GET /probe.mp4 · Range: bytes=0-1\n"
        f"[{stamp} 22:00:00.410] I [----] net loopback: serving 206 Partial Content bytes 0-1/1128375\n"
        f"[{stamp} 22:00:12.000] V [----] web console.log: [spike] [loopback] RESULT "
        f"loadedmetadata=TIMEOUT mediaError=code=4 message=\n"
    )


def _fixture_no_bytes(stamp: str) -> str:
    """THE FIRST REAL RUN, verbatim in shape: the request arrives and NOTHING is served."""
    return (
        f"[{stamp} 22:00:00.000] I [----] app offline spike: starting (E1 loopback + E2 caps)\n"
        f"[{stamp} 22:00:00.400] I [----] net loopback request: GET /probe.mp4 · Range: bytes=0-1\n"
        f"[{stamp} 22:00:00.430] I [----] net loopback: no such file for /probe.mp4\n"
        f"[{stamp} 22:00:12.000] V [----] web console.log: [spike] [loopback] RESULT "
        f"loadedmetadata=TIMEOUT mediaError=code=4 message=\n"
    )


def selftest() -> int:
    """⚠ FALSIFY THE TOOL, NOT THE SPIKE. Each case asserts the EXIT CODE, and two of them only exist
    because this tool once got the answer wrong."""
    cases: list[tuple[str, str, int, str]] = [
        # 1. the happy path
        ("a passing run", _fixture_pass("2026-09-14"), 0, "PASS"),
        # 2. ⚠ THE REGRESSION THAT MADE THE RUN WINDOW NECESSARY: a pass EARLIER in the same file must
        #    not carry a later failing run. Before the window, every `evidence()` took the first match,
        #    so this returned 0 (PASS) — a gate that can never fail again after its first success.
        ("a FAILING run after a passing one (stale-pass regression)",
         _fixture_pass("2026-09-14") + _fixture_codec_error("2026-09-15"), 1, "errored over loopback"),
        # 3. ⚠ THE SAME BUG'S OTHER FACE: the earlier run's codec error must not be printed as THIS
        #    run's evidence. Nothing was served here, so the honest answer is INCONCLUSIVE, and the
        #    stale `mediaError=code=4` must not be read as "WebKit refused the codec".
        ("an earlier codec error must not be inherited by a later no-bytes run",
         _fixture_codec_error("2026-09-14") + _fixture_no_bytes("2026-09-15"), 3,
         "answered NOTHING"),
        # 4. the first real run, on its own — a spike bug, not a WebKit finding
        ("no bytes served (the two-name bug's shape)", _fixture_no_bytes("2026-09-14"), 3,
         "answered NOTHING"),
        # 5. the whole file re-read instead of a range: the page may still say `seek -> ok`
        ("a whole-file 200 where the page claims a seek",
         _fixture_pass("2026-09-14").replace(
             "serving 206 Partial Content bytes 0-1/1128375",
             "serving 200 OK whole file (1128375 B)"), 1, "200 for the whole file"),
        # 6. the spike never launched
        ("the spike never launched",
         "[2026-09-14 21:00:00.000] I [----] app rkm: launched\n", 3, "never ran"),
        # 7. a log with no timestamps at all: the window falls back to the whole file and SAYS so
        ("no timestamps — the fallback must still judge the file",
         "\n".join(line.split("] ", 1)[1] if "] " in line else line
                   for line in _fixture_pass("2026-09-14").splitlines()
                   if "[" in line and "]" in line), 0, "PASS"),
        # 8. a media element that never asked for the file, while the PAGE was served — a real E1
        #    negative, not a spike fault
        ("the page loaded but the media stack never requested the file",
         (
             "[2026-09-14 21:00:00.000] I [----] app offline spike: starting (E1 loopback + E2 caps)\n"
             "[2026-09-14 21:00:00.300] I [----] net loopback request: GET /probe.html\n"
             "[2026-09-14 21:00:05.000] V [----] web console.log: [spike] [loopback] RESULT "
             "loadedmetadata=TIMEOUT mediaError=code=4 message=\n"
         ), 1, "refused the URL"),
    ]

    failures = 0
    for name, text, expected, expected_reason in cases:
        window, scope = newest_run(text.splitlines())
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            result = analyse(window, text.splitlines(), out=lambda *a, **k: None)
            code = verdict_code(result)
        shown = buffer.getvalue()
        detail = " ".join(result["inconclusive"] + result["problems"])
        ok = code == expected and (expected == 0 or expected_reason.lower() in detail.lower())
        print(f"  {'PASS' if ok else 'FAIL'}  exit={code} (want {expected})  {name}")
        if not ok:
            failures += 1
            print(f"        expected {expected_reason!r} in the reasons, got: {detail[:220]!r}")
        del shown, scope

    # 9. the arg cases that each cost a round trip: an unset `$LOG` arrives as an empty string
    for argv, want, label in (
        ([""], 2, "an EMPTY path argument (what `\"$LOG\"` expands to)"),
        (["."], 2, "a DIRECTORY-ish argument instead of a file"),
        (["/tmp/there-is-no-such-log-here.log"], 2, "a path that does not exist"),
    ):
        buffer, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(buffer), redirect_stderr(errors):
            code = main(argv)
        ok = code == want
        print(f"  {'PASS' if ok else 'FAIL'}  exit={code} (want {want})  {label}")
        failures += 0 if ok else 1

    print(f"\nSELFTEST {'PASS' if not failures else f'FAIL — {failures} case(s)'}")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("log", nargs="?", help="the log file (default: found automatically)")
    parser.add_argument("--selftest", action="store_true",
                        help="falsify this tool against synthetic logs and exit")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()

    files: list[Path] = []
    how = ""
    primary: Path | None = None
    # ⚠ `is not None`, NOT truthiness: an explicit empty string is FALSY, so `if args.log:` sent the
    # `"$LOG"`-expanded-to-nothing case down the auto-discovery path and printed a misleading message.
    # Absent and empty are different facts and get different answers.
    if args.log is not None:
        raw = args.log.strip()
        if not raw or raw in {".", ".."}:
            # ⚠ THE EXACT TRAP THAT COST A ROUND TRIP: an unset shell variable expands to nothing, and
            # `Path("")` IS the current directory — which is why the failure surfaced as
            # `IsADirectoryError: '.'` from deep inside pathlib.
            print("the path argument is EMPTY — that is what an unset shell variable looks like "
                  "(e.g. `\"$LOG\"` with no LOG). Run it with no argument and it will find the log itself.",
                  file=sys.stderr)
            usage_help()
            return 2
        path = Path(raw).expanduser()
        if path.is_dir():
            print(f"that is a DIRECTORY, not a log file: {path}", file=sys.stderr)
            candidates = sorted(path.glob("rkm-ios*.log"))
            if candidates:
                print(f"  did you mean: {'  '.join(str(c) for c in candidates)}", file=sys.stderr)
            print("  an empty $LOG expands to nothing, which is why this happens.", file=sys.stderr)
            usage_help()
            return 2
        if not path.exists():
            print(f"no such log: {path}", file=sys.stderr)
            usage_help()
            return 2
        directory = path.parent
        primary = path
        how = "the path you gave"
    else:
        directory, how = find_log()
        if directory is None or not (directory / LOG_NAME).exists():
            print(f"could not find {LOG_NAME} — {how}.")
            usage_help()
            return 2

    text, files = collect(directory, primary)
    print(f"reading {len(files)} file(s) from {directory}")
    print(f"  ({how}; {len(text.splitlines())} lines)")
    lines = text.splitlines()
    # ⚠ The log is append-only across runs: judge the newest spike run, and say which one that was.
    window, scope = newest_run(lines)
    print(f"  ⚠ {scope}")

    return report(analyse(window, lines))


if __name__ == "__main__":
    sys.exit(main())
