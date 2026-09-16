#!/usr/bin/env python3
"""Judge phase B2's gate from the DEVICE's own evidence — one command, no arguments.

`docs/NATIVE_FEEL_AND_OFFLINE_PLAN.md` §6 states B2's gate as behaviour:

    downloads complete with the app backgrounded, resume after a forced failure,
    and appear in the manifest after a relaunch.

None of that is visible from here: it happens inside a WKWebView shell on a phone or a simulator, and the
only two things that come back are the app's **file log** and its **manifest.json** — both inside the app
container. So this reads those two, scopes itself to the newest app run, and answers the gate's three
questions one at a time.

    python3 tools/check_offline_download.py              # finds the simulator's container itself
    python3 tools/check_offline_download.py --sim        # explicitly the booted simulator
    python3 tools/check_offline_download.py --log PATH --manifest PATH
    python3 tools/check_offline_download.py --selftest   # falsify the TOOL (fixture logs, no Mac)

⚠ **No argument is required, and that is deliberate.** B0's checker (`check_spike_e1_e2.py`) learned it the
hard way: the docs once said `check_spike_e1_e2.py "$LOG"`, `$LOG` was never defined, the empty string
became `.`, and the tool died with `IsADirectoryError`. A placeholder in a command is a command that does
not run.

⚠⚠ **IT READS ONE RUN, NOT THE WHOLE FILE.** `rkm-ios.log` is append-only across launches, so a run that
passed yesterday is still in the file today — a gate that cannot fail after its first success is not a
gate. The per-run boundary is the app's own launch line (`offline session ready`), matched by timestamp so
that archive order cannot matter.

⚠ **Exit codes:** 0 all three questions answered YES · 1 a check FAILED, or two pieces of evidence
contradict each other · 3 NOT EXERCISED (nothing to judge: the download never started, or the log is not
there) — the third state exists because "we did not test it" and "it did not work" are different answers
and a gate that conflates them is worse than no gate.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

BUNDLE_ID = "com.helloraj1986.rkmcinema.ios"
#: Where `RollingFileLog.defaultDirectory(appFolder: "RKMCinema")` puts it, inside the app container.
LOG_SUFFIX = Path("Library/Application Support/RKMCinema/Logs")
LOG_NAME = "rkm-ios.log"
#: The offline store's root. ⚠ `OfflineLayout.defaultRoot()` appends `Offline` DIRECTLY to Application
#: Support — it is NOT under the `RKMCinema/` folder the LOG lives in (`RollingFileLog.defaultDirectory`
#: adds that one). The first version of this tool looked inside `RKMCinema/Offline/`, found nothing, and
#: reported "no manifest was read" while the app was holding a finished film — a wrong path is a gate that
#: silently judges nothing. Both are tried now, and the one that was NOT found is printed.
MANIFEST_CANDIDATES = [
    Path("Library/Application Support/Offline/manifest.json"),
    Path("Library/Application Support/RKMCinema/Offline/manifest.json"),
]
#: How many of the newest app runs the three questions may draw on. ⚠ The gate is a STORY — start, a
#: dropped connection, a force-quit, a relaunch — and one run cannot contain it: the resume happens in the
#: run AFTER the one that started the download. Three covers start → interrupted → resumed.
DEFAULT_RUNS = 3

#: The app's own launch line — the ONLY per-run boundary in the file.
RUN_MARKER = "offline session ready"
STAMP = re.compile(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\]")
SIZE = r"([\d.]+ [A-Z]+)"

# ------------------------------------------------------------------ the evidence patterns
P_REQUESTED = re.compile(r"offline download requested")
P_PLAN = re.compile(r"offline plan · mode (\S+)")
P_ARTEFACT = re.compile(rf"offline artefact · {SIZE} · etag (\S+) ·")
P_TASK = re.compile(r"offline task started · task (\d+) · (.*) · ([\d.]+ [A-Z]+) total")
P_FRAGMENT = re.compile(rf"offline fragment · HTTP (\d{{3}}) · {SIZE} · Content-Range (.*?) · asked from {SIZE}")
P_READY = re.compile(rf"offline READY · {SIZE} · mode (\S+) · verified (.+?) · took")
P_PERCENT = re.compile(r"offline (\d+)% ·")
P_RESUMING = re.compile(rf"offline resuming from {SIZE} of {SIZE}")
P_RESTART = re.compile(r"offline restarting from zero")
P_RETRY = re.compile(r"offline download will retry in (\d+)s")
P_INCOMPLETE = re.compile(r"offline incomplete ·")
P_SIGNIN = re.compile(r"offline download needs a sign-in")
P_BACKGROUNDED = re.compile(r"scene background — flushing the file log")
P_BG_INCOMING = re.compile(r"offline background events incoming")
P_BG_FINISHED = re.compile(r"offline background events finished")
P_RELAUNCH = re.compile(r"offline RELAUNCH")
P_RESTORED = re.compile(r"offline RELAUNCH: task \d+ is still running")


def _stamp(line: str) -> str | None:
    match = STAMP.search(line)
    return match.group(1) if match else None


def runs(lines: list[str]) -> list[tuple[str, int]]:
    """Every app run in the file, oldest first: `(timestamp, index of its first line)`."""
    found: list[tuple[str, int]] = []
    for index, line in enumerate(lines):
        if RUN_MARKER in line and (stamp := _stamp(line)):
            found.append((stamp, index))
    return found


def window(lines: list[str], count: int) -> tuple[list[str], str]:
    """The lines of the newest `count` runs, plus a sentence naming the window.

    ⚠⚠ WHY A WINDOW OF RUNS AND NOT ONE RUN. Every question this tool asks is behavioural and the behaviour
    takes MORE THAN ONE LAUNCH: a download starts in one run, the network drops, the retry resumes, the app
    is force-quit and the next launch continues the transfer. Judging only the newest run reported
    "no download was started" on a round where the film had downloaded, dropped, resumed and survived a
    relaunch — while two old runs sat right there in the file with the evidence in them.

    ⚠ The stale-pass protection is the WINDOW, not "one run": an old success outside the last `count`
    launches is still ignored, and that is the case the selftest pins.
    """
    marks = runs(lines)
    if not marks:
        return lines, (f"no `{RUN_MARKER}` line — analysing EVERY line (an older build, or a log copied "
                       f"out of something else)")
    kept = marks[-count:]
    start = kept[0][1]
    ignored = sum(1 for line in lines[:start] if _stamp(line))
    if len(kept) == 1:
        return lines[start:], (f"run starting at {kept[0][0]} — {ignored} earlier line(s) ignored "
                               f"(the 1st of {len(marks)} launches in the file)")
    return lines[start:], (f"the last {len(kept)} runs, {kept[0][0]} → {kept[-1][0]} — {ignored} earlier "
                           f"line(s) ignored (of {len(marks)} launches in the file)")


# ------------------------------------------------------------------ finding the evidence

def _booted_container() -> Path | None:
    try:
        out = subprocess.run(
            ["xcrun", "simctl", "get_app_container", "booted", BUNDLE_ID, "data"],
            capture_output=True, text=True, timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    path = Path(out.stdout.strip())
    return path if path.exists() else None


def _all_containers() -> list[Path]:
    """Every RKMCinema data container on this Mac, newest first.

    ⚠⚠ **A REINSTALL MOVES THE CONTAINER, AND THE OLD ONE STAYS ON DISK.** iOS gives an app a new Data
    container when it is installed again — which every `mac-round.sh --sim` run does — so a manifest
    written before a rebuild is still readable here while it is *not* the app's current state, and a
    downloaded film is stranded in it. That is why this returns the container itself and why the caller
    compares it against the one the LOG came from: a record from a different container is evidence of what
    happened, never of what the app has now.
    """
    root = Path.home() / "Library/Developer/CoreSimulator/Devices"
    if not root.is_dir():
        return []
    found: list[Path] = []
    for candidate in root.glob("*/data/Containers/Data/Application/*"):
        if (candidate / "Library/Application Support").is_dir():
            found.append(candidate)
    found.sort(key=lambda path: (path / "Library/Application Support").stat().st_mtime, reverse=True)
    return found


def find_log(container: Path | None = None) -> tuple[Path | None, str, Path | None]:
    """The newest log directory, which container it came from, and how we looked."""
    # 1. The booted simulator — authoritative, because that IS the app that is running.
    if container is None:
        container = _booted_container()
    if container is not None:
        directory = container / LOG_SUFFIX
        if (directory / LOG_NAME).exists():
            return directory, f"booted simulator app container ({container.name[:8]}…)", container
        # Fall through: the container exists but has never logged.
    # 2. Any simulator on this Mac, without needing one booted (or after a reinstall).
    for candidate in _all_containers():
        directory = candidate / LOG_SUFFIX
        if (directory / LOG_NAME).exists():
            return (directory,
                    f"an app container on this Mac ({candidate.name[:8]}… — NOT the booted one; a rebuild "
                    f"moves the container)", candidate)
    if container is not None:
        return container / LOG_SUFFIX, "the booted container — the app has not written a log yet", container
    return None, "no simulator container found — is a simulator installed and the app run at least once?", None


def find_manifest(container: Path | None) -> tuple[Path | None, str, Path | None]:
    """The manifest for the container the log came from — and only that one.

    ⚠⚠ **IT IS DELIBERATELY NOT "the newest manifest anywhere".** An older install's manifest can look
    like a pass while the app the user is actually running has nothing — so a record from another container
    is printed as EVIDENCE and never counted as an answer. (The first version of this tool got the path
    wrong as well: `OfflineLayout.defaultRoot()` appends `Offline` straight to Application Support, not
    under the `RKMCinema/` folder the log lives in.)
    """
    if container is None:
        return None, "no app container to look in", None
    tried = [container / candidate for candidate in MANIFEST_CANDIDATES]
    for path in tried:
        if path.exists():
            return path, f"read from {path}", container
    stranded = []
    for other in _all_containers():
        if other == container:
            continue
        for candidate in MANIFEST_CANDIDATES:
            path = other / candidate
            if path.exists():
                stranded.append(path)
    note = ""
    if stranded:
        note = (" · ⚠ an OLDER install's container holds a manifest ("
                + ", ".join(str(path.parent.parent.parent.name)[:8] + "…" for path in stranded[:2])
                + ") — stranded data, not the running app's")
    return None, ("no manifest at " + " nor ".join(str(path) for path in tried) + note), None


def collect_log(directory: Path) -> list[str]:
    """Every line from the log directory — the live file plus any rotated archives.

    ⚠ Rotation can move a run out of the live file, and a gate that reads only the newest 2 MB would
    report "nothing happened" for a round that happened just before a rotate.
    """
    if directory.is_file():
        directory = directory.parent
    files = sorted(directory.glob(f"{LOG_NAME}*"), key=lambda item: item.name)
    lines: list[str] = []
    for file in files:
        try:
            lines.extend(file.read_text(encoding="utf-8", errors="replace").splitlines())
        except OSError:
            continue
    return lines


# ------------------------------------------------------------------ the judgement

def analyse(lines: list[str], manifest: dict | None) -> dict:
    """Pure: given the newest run's lines and the manifest, answer the three questions."""
    text = "\n".join(lines)
    result: dict = {"questions": {}, "evidence": [], "notes": [], "fatal": None}

    def question(name: str, state: str, why: str, evidence: list[str]) -> None:
        result["questions"][name] = {"state": state, "why": why}
        result["evidence"].extend(evidence)

    # ---- 1. did a film actually land?
    requested = bool(P_REQUESTED.search(text))
    plan = P_PLAN.search(text)
    artefact = P_ARTEFACT.search(text)
    task = P_TASK.search(text)
    ready = P_READY.search(text)
    percents = P_PERCENT.findall(text)
    sign_in = bool(P_SIGNIN.search(text))
    incomplete = P_INCOMPLETE.findall(text)
    resuming = P_RESUMING.search(text)
    retries = P_RETRY.findall(text)
    restarts = P_RESTART.findall(text)

    if not requested:
        question("download completed",
                 "NOT EXERCISED",
                 "no download was started in this run — open the debug HUD's offline panel, "
                 "tap Load titles, then Download",
                 [])
    elif sign_in:
        question("download completed", "FAIL",
                 "the server refused the download and asked for a sign-in — the native request carried no "
                 "usable session cookie (sign in inside the app first, then retry)",
                 [line for line in lines if P_SIGNIN.search(line)])
    elif ready:
        weaker = "size only" in ready.group(2)
        contradiction = None
        if task and ready.group(1) != task.group(3):
            contradiction = (f"the task reported {task.group(3)} total but READY reported {ready.group(1)}")
        if contradiction:
            question("download completed", "FAIL", contradiction,
                     [line for line in lines if P_READY.search(line) or P_TASK.search(line)])
            result["fatal"] = contradiction
        else:
            question("download completed", "PASS",
                     f"{ready.group(1)} landed, mode {ready.group(2)}, verified {ready.group(3)}",
                     [line for line in lines if P_READY.search(line)])
            if weaker:
                result["notes"].append(
                    "the verification was SIZE-ONLY — the server sent no ETag, so identity was not proved "
                    "(our own server always sends one; treat this as a finding)")
    elif incomplete:
        # ⚠ A stop that is RETRYING is not a failure yet — the retry policy is carrying it. A stop with no
        # retry left is a FAIL, and the difference matters: one is a test in progress, the other is a bug
        # report.
        if retries:
            question("download completed", "NOT EXERCISED",
                     f"the transfer stopped and is retrying (waiting {retries[0]}s) — let the run finish",
                     [line for line in lines if P_INCOMPLETE.search(line) or P_RETRY.search(line)])
        else:
            question("download completed", "FAIL",
                     "the transfer stopped before the file was whole and nothing is retrying it",
                     [line for line in lines if P_INCOMPLETE.search(line)])
    elif task:
        question("download completed", "NOT EXERCISED",
                 "a task started but no READY line yet — it is either still running or was interrupted; "
                 "nothing here says which",
                 [line for line in lines if P_TASK.search(line)])
    else:
        question("download completed", "FAIL",
                 "the plan ran but no download task was ever created",
                 [line for line in lines if P_PLAN.search(line) or P_ARTEFACT.search(line)])

    if plan:
        result["evidence"].append(f"plan: mode {plan.group(1)}")
    if artefact:
        result["evidence"].append(f"artefact: {artefact.group(1)}, etag {artefact.group(2)}")
    if percents:
        result["evidence"].append(f"progress reported at {len(percents)} checkpoint(s), up to {max(percents)}%")
    if task and task.group(2).strip().startswith("resuming at"):
        result["notes"].append("the transfer resumed from a byte offset rather than starting at zero")

    # ---- 2. was a failure survived?
    assisted_fragments = [line for line in lines if P_FRAGMENT.search(line) and "asked from 0 B" not in line]

    if resuming or assisted_fragments:
        question("resume after a forced failure", "PASS",
                 "a resume happened" + (f" (from {resuming.group(1)})" if resuming else " (a fragment was "
                 "fetched from a non-zero offset)"),
                 [line for line in lines if P_RESUMING.search(line) or P_FRAGMENT.search(line)])
    elif retries:
        question("resume after a forced failure", "PASS",
                 f"a failure was survived and retried after {retries[0]}s, continuing from the bytes on disk",
                 [line for line in lines if P_RETRY.search(line)])
    elif restarts:
        question("resume after a forced failure", "PASS",
                 "a restart-from-zero was taken deliberately (a 416/unusable partial) — the mechanism ran, "
                 "though no partial was carried forward",
                 [line for line in lines if P_RESTART.search(line)])
    else:
        question("resume after a forced failure", "NOT EXERCISED",
                 "nothing interrupted the download. To exercise it: start a download, then turn the "
                 "Mac's Wi-Fi OFF for a few seconds and back on — the retry policy resumes with a Range",
                 [])

    # ---- 3. background, and the manifest after a relaunch
    backgrounded = [line for line in lines if P_BACKGROUNDED.search(line)]
    bg_events = [line for line in lines if P_BG_INCOMING.search(line) or P_BG_FINISHED.search(line)]
    relaunch = [line for line in lines if P_RELAUNCH.search(line)]
    restored = [line for line in lines if P_RESTORED.search(line)]

    manifest_records = []
    if manifest:
        manifest_records = manifest.get("items", [])
    ready_records = [record for record in manifest_records if record.get("state") == "ready"]
    size_bad = [record for record in ready_records
                if record.get("total_bytes") and record.get("bytes") != record.get("total_bytes")]

    if size_bad:
        question("manifest after a relaunch", "FAIL",
                 f"{len(size_bad)} record(s) say ready with bytes != total_bytes — the index is claiming a "
                 "file that is not whole",
                 [json.dumps(record) for record in size_bad])
        result["fatal"] = result["fatal"] or "a ready record whose bytes do not match its total"
    elif ready_records and (relaunch or restored or backgrounded or resuming):
        # ⚠ A resume is evidence TOO, and it is the strongest kind available in one run: the app came back
        # to a download it had not finished, read the partial from disk and continued it. That is the
        # relaunch machinery working, whether the restart was a force-quit, a suspension or a failure.
        detail = "the manifest holds " + ", ".join(
            f"{record.get('title') or record.get('item_id')}: {record.get('bytes')} B "
            f"({record.get('verification') or 'unverified'})" for record in ready_records[:3])
        why = "a ready record survived a relaunch"
        if restored:
            why += " and a live task was re-attached by taskDescription"
        elif resuming:
            why += " and the app continued a partially downloaded file from disk"
        question("manifest after a relaunch", "PASS", why,
                 relaunch + restored + [detail])
    elif ready_records:
        question("manifest after a relaunch", "NOT EXERCISED",
                 "a record is ready, but nothing in this run shows a relaunch — force-quit the app and "
                 "open it again, and the `offline RELAUNCH` lines and the manifest should both appear",
                 ready_records and [json.dumps(record) for record in ready_records[:3]])
    else:
        question("manifest after a relaunch", "NOT EXERCISED",
                 "no ready record in the manifest yet — a finished download is the prerequisite",
                 [])

    if bg_events:
        result["evidence"].append("the system delivered background-session events to the app "
                                  f"({len(bg_events)} line(s)) — the AppDelegate hook fired")
    elif backgrounded:
        result["notes"].append("the app was backgrounded during this run, but no background-session event "
                               "was logged: the transfer completed inside the app's own process, which "
                               "does not prove the background path")
    else:
        result["notes"].append("the app was never backgrounded in this run — the background half of the "
                               "gate is unproven until it is")

    if manifest_record := None:
        pass
    result["manifest"] = {"records": len(manifest_records), "ready": len(ready_records)}
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
        for line in result["evidence"][:12]:
            print(f"   {line.strip()[:160]}")
    if result.get("manifest"):
        print(f"\nmanifest: {result['manifest']['records']} record(s), "
              f"{result['manifest']['ready']} ready")
    if result["notes"]:
        print("\nnotes:")
        for note in result["notes"]:
            print(f"   · {note}")

    code = verdict_code(result)
    print("")
    if code == 0:
        print("PASS — all three questions answered yes.")
    elif code == 1:
        print("FAIL — see the NO above. (A failed check is a real finding, not a test setup problem.)")
    else:
        print("NOT EXERCISED — nothing was measured. Judge nothing from this run; run the checklist in "
              "docs/PROGRESS.md and try again.")
    return code


# -------------------------------------------------------------------------------------------- selftest

def _run(*lines: str, stamp: str = "2026-09-16 12:00:00.000") -> list[str]:
    out = [f"[{stamp}] I [-------] offline  {RUN_MARKER} · id x.offline · wifiOnly=false · autoResume=true "
           f"· store=open"]
    out.extend(f"[{stamp}] I [-------] offline  {line}" for line in lines)
    return out


FIXTURE_PASS_FULL = _run(
    'offline download requested · "Heat" · mode direct · attempt 1',
    "offline plan · mode direct (direct-playable) · estimate 1.88 GB · server state ready",
    "offline prepare was idempotent — the server returned the existing artefact",
    'offline artefact · 1.88 GB · etag "1882377499-1758000000000000000" · video/mp4',
    "offline task started · task 7 · from byte 0 · 1.88 GB total · wifiOnly=false",
    "offline 10% · 188.24 MB of 1.88 GB · 3.8 MB/s · eta 8m 0s",
    "offline 100% · 1.88 GB of 1.88 GB · 3.7 MB/s",
    'offline fragment · HTTP 200 · 1.88 GB · Content-Range — · asked from 0 B · whole file (discards 0 B)',
    "offline READY · 1.88 GB · mode direct · verified size+ETag · took 540s (3.5 MB/s)",
)
FIXTURE_BACKGROUNDED = FIXTURE_PASS_FULL + _run(
    "scene background — flushing the file log",
    "offline background events incoming — the system relaunched the app for session x.offline",
    "offline background events finished — releasing the system's completion handler",
)
FIXTURE_RESUME = _run(
    'offline download requested · "Heat" · mode direct · attempt 2',
    "offline plan · mode direct (direct-playable) · estimate 1.88 GB · server state ready",
    'offline artefact · 1.88 GB · etag "1882377499-1" · video/mp4',
    "offline resuming from 512.00 MB of 1.88 GB",
    "offline task started · task 9 · resuming at 512.00 MB · 1.88 GB total · wifiOnly=false",
    "offline fragment · HTTP 206 · 1.37 GB · Content-Range bytes 536870912-1882377498/1882377499 · "
    "asked from 512.00 MB · append at 512.00 MB",
    "offline READY · 1.88 GB · mode direct · verified size+ETag · took 360s (3.9 MB/s)",
)
FIXTURE_RETRY = _run(
    'offline download requested · "Heat" · mode direct · attempt 1',
    "offline task started · task 4 · from byte 0 · 1.88 GB total · wifiOnly=false",
    "offline task failed · NSURLErrorDomain -1005 — The network connection was lost.",
    "offline download will retry in 3s (attempt 1 of 4) · The connection dropped partway through",
)
FIXTURE_RELAUNCH = _run(
    "offline RELAUNCH: one interrupted download found (512.00 MB on disk, state paused, attempts 1)",
    "offline RELAUNCH: resuming an interrupted download automatically",
    "offline resuming from 512.00 MB of 1.88 GB",
    "offline task started · task 11 · resuming at 512.00 MB · 1.88 GB total · wifiOnly=false",
)
FIXTURE_SIGNIN = _run(
    'offline download requested · "Heat" · mode direct · attempt 1',
    "offline plan · mode direct (direct-playable) · estimate 1.88 GB · server state ready",
    "offline download needs a sign-in · Sign in again to continue downloading (ok) · cookies sent 0 []",
)
FIXTURE_STALE = _run(
    'offline download requested · "Alien" · mode direct · attempt 1',
    "offline plan · mode direct (direct-playable) · estimate 1.2 GB · server state ready",
)
FIXTURE_INCOMPLETE = _run(
    'offline download requested · "Heat" · mode direct · attempt 1',
    "offline plan · mode direct (direct-playable) · estimate 1.88 GB · server state ready",
    "offline task started · task 5 · from byte 0 · 1.88 GB total · wifiOnly=false",
    "offline incomplete · 900.00 MB of 1.88 GB bytes on this device · 900.00 MB kept",
)

# ⚠ THE REAL ROUND, as it actually happened on the Mac (2026-09-16): the gate is a STORY across launches,
# and the first version of this tool judged only the NEWEST run — so it reported "no download was started"
# on a round where the film downloaded, the network dropped, the retry resumed it, and a force-quit
# resumed it again. These three fixtures are that story.
STORY_RUN_1 = _run(
    'offline download requested · "Aladdin" · mode direct · attempt 1',
    "offline plan · mode direct (direct-playable) · estimate 1.20 GB · server state ready",
    'offline artefact · 1.20 GB · etag "1200000000-1" · video/mp4',
    "offline task started · task 3 · from byte 0 · 1.20 GB total · wifiOnly=false",
    "offline 10% · 120.00 MB of 1.20 GB · 3.8 MB/s · eta 5m 0s",
    stamp="2026-09-16 17:32:00.000",
)
STORY_RUN_2 = _run(
    "scene background — flushing the file log",
    "offline task failed · NSURLErrorDomain -1005 — The network connection was lost.",
    "offline download will retry in 3s (attempt 1 of 4) · The connection dropped partway through",
    "offline resuming from 400.00 MB of 1.20 GB",
    "offline task started · task 5 · resuming at 400.00 MB · 1.20 GB total · wifiOnly=false",
    "offline fragment · HTTP 206 · 800.00 MB · Content-Range bytes 419430400-1258291199/1258291200 · "
    "asked from 400.00 MB · append at 400.00 MB",
    stamp="2026-09-16 17:40:00.000",
)
STORY_RUN_3 = _run(
    "offline RELAUNCH: one interrupted download found (900.00 MB on disk, state paused, attempts 2)",
    "offline resuming from 900.00 MB of 1.20 GB",
    "offline task started · task 9 · resuming at 900.00 MB · 1.20 GB total · wifiOnly=false",
    "offline READY · 1.20 GB · mode direct · verified size+ETag · took 420s (3.6 MB/s)",
    stamp="2026-09-16 17:44:00.000",
)
STORY_MANIFEST = {"items": [{"item_id": "aladdin", "title": "Aladdin", "state": "ready", "bytes": 1200000000,
                             "total_bytes": 1200000000, "verification": "size_etag"}]}


def selftest() -> int:
    cases: list[tuple[str, list[str], dict | None, int, str]] = [
        ("a complete download, foreground only",
         FIXTURE_PASS_FULL, None, 3, "download completed"),
        ("a complete download with a relaunch and background events",
         FIXTURE_RELAUNCH + FIXTURE_BACKGROUNDED,
         {"items": [{"item_id": "abc", "title": "Heat", "state": "ready", "bytes": 10, "total_bytes": 10,
                    "verification": "size_etag"}]},
         0, "PASS"),
        ("a resume from a byte offset, in one run",
         FIXTURE_RESUME,
         {"items": [{"item_id": "abc", "title": "Heat", "state": "ready", "bytes": 10, "total_bytes": 10,
                    "verification": "size_etag"}]},
         0, "PASS"),
        ("⭐ the REAL round: start → a dropped connection → a force-quit, across THREE runs",
         STORY_RUN_1 + STORY_RUN_2 + STORY_RUN_3, STORY_MANIFEST, 0, "PASS"),
        ("a FOUR-launch-old success must NOT carry the newest window",
         FIXTURE_PASS_FULL + _run(stamp="2026-09-16 18:00:00.000") + _run(stamp="2026-09-16 18:10:00.000")
         + _run(stamp="2026-09-16 18:20:00.000"), None, 3, "NOT EXERCISED"),
        ("a dropped connection, retried from the bytes on disk",
         FIXTURE_RETRY, None, 3, "resume"),
        ("a 401 — the session cookie never reached the request",
         FIXTURE_SIGNIN, None, 1, "sign-in"),
        ("a STALE pass: the newest run started nothing, but an older run succeeded",
         FIXTURE_STALE + FIXTURE_PASS_FULL, None, 3, "NOT EXERCISED"),
        ("a transfer that stopped short",
         FIXTURE_INCOMPLETE, None, 1, "stopped"),
        ("a manifest that claims ready with the wrong size",
         FIXTURE_PASS_FULL + FIXTURE_RELAUNCH,
         {"items": [{"item_id": "abc", "title": "Heat", "state": "ready", "bytes": 900, "total_bytes": 1000,
                    "verification": "size_etag"}]},
         1, "bytes != total_bytes"),
        ("no log at all",
         [], None, 3, "no download was started"),
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
            print(f"    {body[:400]}")

    print("")
    if failures:
        print(f"FAIL — {failures} of {len(cases)} selftest case(s) wrong. The TOOL is wrong: fix it "
              f"before trusting any verdict it gives.")
        return 1
    print(f"PASS — {len(cases)}/{len(cases)} selftest cases behave: the tool can fail, and it can say "
          f"'not exercised' instead of guessing.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--selftest", action="store_true",
                        help="run the fixture cases that falsify the tool itself (no Mac needed)")
    parser.add_argument("--log", type=Path, default=None, help="the log file to read (default: find it)")
    parser.add_argument("--manifest", type=Path, default=None, help="manifest.json (default: find it)")
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS,
                        help=f"how many of the newest app runs to judge (default {DEFAULT_RUNS}) — the gate "
                             f"is a story that spans launches")
    parser.add_argument("--sim", action="store_true", help="use the booted simulator (the default)")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()

    manifest: dict | None = None
    container: Path | None = None
    if args.log is not None:
        if not args.log.exists():
            print(f"no such log file: {args.log}", file=sys.stderr)
            return 3
        container = _booted_container()
        lines = collect_log(args.log)
        where = f"{args.log} ({len(lines)} lines)"
    else:
        container = _booted_container()
        path, why, container = find_log(container)
        if path is None:
            print(f"cannot read the app's log: {why}", file=sys.stderr)
            return 3
        lines = collect_log(path)
        where = f"{why} ({len(lines)} lines)"

    if args.manifest is not None:
        if args.manifest.exists():
            try:
                manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                print(f"manifest could not be parsed: {error}", file=sys.stderr)
        manifest_note = f"read from {args.manifest}"
    else:
        path, manifest_note, _ = find_manifest(container)
        if path is not None:
            try:
                manifest = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                print(f"manifest could not be parsed: {error}", file=sys.stderr)
    run, run_note = window(lines, max(1, args.runs))
    print(f"offline download gate — {run_note}")
    print(f"manifest: {manifest_note}")
    if manifest is None:
        print("⚠ without a manifest the relaunch question can only be judged from the log")
    return report(analyse(run, manifest), where)


if __name__ == "__main__":
    sys.exit(main())
