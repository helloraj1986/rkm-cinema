#!/usr/bin/env python3
"""Read the E1/E2 spike's log and say whether the offline plan may proceed — phase B0's gate.

`docs/NATIVE_FEEL_AND_OFFLINE_PLAN.md` §5 names E1 as *"the one that changes the design"* and §8 says
nothing in Workstream B gets written before it. The gate is therefore specific, and this turns it into
one command instead of a reading exercise:

    python3 tools/check_spike_e1_e2.py <path-to-rkm-ios.log>

What it needs is the proof of **four** things, and the last two are deliberately from DIFFERENT halves
of the system — the page's own account, and the SERVER's account of what it actually sent:

  1. the web view reached the loopback server at all      `loopback request: GET /probe.mp4`
  2. the server answered a byte range with a **206**      `loopback serving 206 Partial Content`
  3. WebKit's media stack parsed the file                 `[spike] [loopback] metadata ok WxH`
  4. a SEEK completed                                     `[spike] [loopback] seek to … -> ok`
  5. playback started                                     `[spike] [loopback] RESULT play=ok`

⚠ 1 and 2 are the reason a page-only report is not enough: *"seek -> ok"* with a `200` on the wire
would mean the whole file was re-read, not a seek — the page cannot tell those apart, the server can.
And `[scheme]` lines are recorded as INFORMATION, never as a pass/fail: the plan EXPECTS the
`WKURLSchemeHandler` to fail, so a pass there is a bonus that would simplify §4.1, not a requirement.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

LOOPBACK = "[loopback]"
SCHEME = "[scheme]"


def line_has(text: str, needle: str) -> bool:
    return needle in text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("log", help="the app's log file (rkm-ios.log)")
    args = parser.parse_args()

    path = Path(args.log)
    if not path.exists():
        print(f"no such log: {path}", file=sys.stderr)
        return 2
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    problems: list[str] = []
    notes: list[str] = []

    def evidence(pattern: str) -> str | None:
        rx = re.compile(pattern)
        for line in lines:
            if rx.search(line):
                return line.strip()
        return None

    # ------------------------------------------------------------------ E1
    print("E1 · does media play from loopback inside the WKWebView, with seeking?")

    reached = evidence(r"loopback request: GET /probe\.mp4")
    if reached:
        print(f"  ✅ the web view reached the server — {reached}")
    else:
        problems.append(
            "no `loopback request:` line at all — the web view never reached 127.0.0.1. "
            "That is NOT a codec answer: it points at ATS/origin, not at the media stack"
        )
        print("  ❌ the web view never reached the loopback server")

    partial = evidence(r"serving 206 Partial Content")
    whole = evidence(r"serving 200 OK whole file")
    if partial:
        print(f"  ✅ the server answered a BYTE RANGE with 206 — {partial}")
    elif whole:
        problems.append(
            "the server answered 200 for the whole file, not 206 for a range — so any 'seek' the page "
            "reported re-read the file instead of seeking"
        )
        print(f"  ❌ no 206; the whole file was sent — {whole}")
    else:
        problems.append("the server logged no served response for probe.mp4")
        print("  ❌ the server logged no response")

    metadata = evidence(r"\[spike\] \[loopback\] metadata ok")
    if metadata:
        print(f"  ✅ WebKit parsed the media — {metadata}")
    else:
        # ⚠ The specific error is checked BEFORE the timeout: a `loadedmetadata=TIMEOUT` that also
        # carries `mediaError=code=N` is a codec/container refusal, and calling that "timed out"
        # would send the next session looking at the transport instead of at the file.
        errored = evidence(r"\[spike\] \[loopback\] RESULT .*mediaError=code=(\d+)")
        timed_out = evidence(r"\[spike\] \[loopback\] RESULT loadedmetadata=TIMEOUT")
        if errored:
            problems.append(f"the media element errored over loopback — {errored}")
            print(f"  ❌ media error — {errored}")
        elif timed_out:
            problems.append("`loadedmetadata=TIMEOUT`: the media stack never parsed the file over loopback")
            print(f"  ❌ timed out loading metadata — {timed_out}")
        else:
            problems.append("no `metadata ok` line: the probe never got as far as loading the file")
            print("  ❌ no metadata result at all")

    seek = evidence(r"\[spike\] \[loopback\] seek to [\d.]+ -> ok")
    if seek:
        print(f"  ✅ a SEEK completed — {seek}")
    else:
        failed = evidence(r"\[spike\] \[loopback\] seek to [\d.]+ -> (?!ok)\S+")
        problems.append("the seek did not complete" + (f" — {failed}" if failed else " (no seek line)"))
        print(f"  ❌ seeking failed — {failed or 'no seek line'}")

    played = evidence(r"\[spike\] \[loopback\] RESULT play=ok")
    if played:
        print(f"  ✅ playback started — {played}")
    else:
        problems.append("`[loopback] RESULT play=` never reported ok")
        print("  ❌ playback did not report ok")

    # ---------------------------------------------------------------- the bonus
    scheme_meta = evidence(r"\[spike\] \[scheme\] metadata ok")
    scheme_failed = evidence(r"\[spike\] \[scheme\] RESULT")
    print("\n   bonus · the WKURLSchemeHandler comparison (the plan EXPECTS this to fail)")
    if scheme_meta:
        notes.append(
            "the scheme handler ALSO carried media — §4.1/§4.4 can be simplified (no port, no server)"
        )
        print(f"  ℹ️  it WORKED — {scheme_meta}")
    elif scheme_failed:
        print(f"  ℹ️  it failed as expected — {scheme_failed}")
    else:
        print("  ℹ️  no `[scheme]` result in the log")

    # ------------------------------------------------------------------ E2
    print("\nE2 · is a service worker available, and what does storage look like?")
    caps = [ln.strip() for ln in lines if "[rkm-caps]" in ln]
    if caps:
        for line in caps:
            print(f"  {line}")
        joined = " ".join(caps)
        match = re.search(r"sw=(true|false)", joined)
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
            "loaded (not just the spike sheet)"
        )
        print("  ❌ no `[rkm-caps]` line at all")

    # ------------------------------------------------------------------ verdict
    print("\n" + "=" * 78)
    if problems:
        print("FAIL — the plan may NOT proceed as written. Missing evidence:")
        for problem in problems:
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
    if notes:
        print("\nThings to decide anyway:")
        for note in notes:
            print(f"  - {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
