#!/usr/bin/env python3
"""Read the E1/E2 spike's log and say whether the offline plan may proceed — phase B0's gate.

`docs/NATIVE_FEEL_AND_OFFLINE_PLAN.md` §5 names E1 as *"the one that changes the design"* and §8 says
nothing in Workstream B gets written before it. The gate is specific, so this makes it one command:

    python3 tools/check_spike_e1_e2.py            # finds the log itself (simulator)
    python3 tools/check_spike_e1_e2.py <path>     # or point it at one

⚠ **The path argument is OPTIONAL because of a real wasted round trip.** The docs used to say
`check_spike_e1_e2.py "$LOG"` — with `$LOG` never defined on the Mac, `"$LOG"` expanded to the empty
string, `Path("")` became `.`, and the tool died with `IsADirectoryError: '.'`. A placeholder in a
command is a command that does not run. Now it finds the file, prints where it read from, and says
something useful if it cannot.

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
import subprocess
import sys
from pathlib import Path

LOOPBACK = "[loopback]"
SCHEME = "[scheme]"

BUNDLE_ID = "com.helloraj1986.rkmcinema.ios"
#: Where `RollingFileLog.defaultDirectory(appFolder: "RKMCinema")` puts it, inside the app container.
LOG_SUFFIX = Path("Library/Application Support/RKMCinema/Logs")
LOG_NAME = "rkm-ios.log"


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("log", nargs="?", help=f"the log file (default: found automatically)")
    args = parser.parse_args()

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

    problems: list[str] = []
    notes: list[str] = []

    def evidence(pattern: str) -> str | None:
        import re
        rx = re.compile(pattern)
        for line in lines:
            if rx.search(line):
                return line.strip()
        return None

    # ------------------------------------------------------------------ E1
    print("\nE1 · does media play from loopback inside the WKWebView, with seeking?")

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

    any_spike = evidence(r"\[spike\]")
    if not any_spike:
        problems.append(
            "NO `[spike]` lines anywhere in the log — the spike never ran. It needs the app launched "
            "with `-RKMOfflineSpike YES`, and a stored server address (the probe file comes from it)"
        )

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
        import re
        match = re.search(r"sw=(true|false)", " ".join(caps))
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
