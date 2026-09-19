#!/usr/bin/env python3
"""Phase B's gate that does NOT need the Mac — and, on request, its falsification.

⚠ Why this exists is in `apple/WORKFLOW.md` §5: everything SwiftUI is Mac-only, and a Mac round is the
most expensive thing in this workflow. Phase B is built on exactly two pure things — **the URL every
poster card is loaded from** and **the wire models** the item routes decode into — and both fail
SILENTLY: a poster URL that 404s and a poster wall that cannot decode both look like an empty library.
So they are compiled AND RUN here, against fixtures shaped like the real payloads, before any Mac round.

It is the same trade `check-offline-core.py` makes for the iOS offline stack, and the same source files
the tvOS target compiles — not a copy.

What it does:

  1. compiles `Core/PosterURL.swift` and `Core/Models/LibraryModels.swift` together with the harness in
     `apple/scripts/tvos-core-tests/main.swift`, using `swiftc`;
  2. runs it and reports PASS/FAIL;
  3. with `--falsify`, reverts each rule in a scratch copy of those sources and requires the harness to go
     RED on the specific check that rule protects. A rule whose mutation still passes is a rule that
     proves nothing, and this script fails in that case.

⚠ What this gate does NOT cover, and will not claim to: the SwiftUI views (B2-B4), artwork actually
loading over the session cookie, or the player. Those are Mac rounds.

⚠ Build output goes to `~/tmp` (or `$RKM_CHECK_TMP`), never `/tmp`: `/tmp` is mounted `noexec` in this
sandbox, so a binary there cannot be run at all — and the failure reads as a compile error.

Usage:
    python3 apple/scripts/check-tvos-core.py              # compile + run
    python3 apple/scripts/check-tvos-core.py --falsify    # + revert every rule, require each to fail

Exit codes: 0 = PASS · 1 = a check FAILED (or a mutation did not) · 2 = the tool itself could not run
(stale mutation source, missing file) · 3 = no `swiftc` here.
"""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[2]
TVOS = REPO / "apple" / "tvos" / "RKMCinemaTV"

#: The sources under test. ⚠ Both are `Foundation`-only by design — the moment one of them imports
#: SwiftUI it stops being checkable here, and that is the trade this file exists to avoid.
PURE_SOURCES = [
    TVOS / "Core" / "Models" / "LibraryModels.swift",
    TVOS / "Core" / "PosterURL.swift",
]

HARNESS = REPO / "apple" / "scripts" / "tvos-core-tests" / "main.swift"

#: Every rule the harness pins, as `(label, file, old, new, check-it-protects)`. ⚠ The last element must
#: be text that appears in the FAILING line the harness prints, or a mutation that goes red for an
#: unrelated reason would count as a pass.
MUTATIONS = [
    # ---- the poster URL
    ("the width clamp", "PosterURL.swift",
     "min(max(width, widthRange.lowerBound), widthRange.upperBound)",
     "width",
     "an out-of-range width is clamped"),
    ("the empty-id refusal", "PosterURL.swift",
     "guard !itemID.isEmpty else { return nil }",
     "guard true else { return nil }",
     "an empty id builds no URL at all"),
    ("the query staying out of the path", "PosterURL.swift",
     "        let root = components.path.hasSuffix(\"/\") ? String(components.path.dropLast()) "
     ": components.path\n"
     "        components.path = root + \"/api/jellyfin/poster\"",
     "        components.path = components.path + \"/api/jellyfin/poster\"",
     "one slash between the base and the path"),
    # ---- the item shape
    ("the identity key", "LibraryModels.swift",
     'case itemID = "item_id"', 'case itemID = "id"',
     "item_id is the identity key, not id"),
    ("the optional thumb", "LibraryModels.swift",
     "let thumb: String?", "let thumb: String",
     "a missing thumb does not fail the decode"),
    # ⚠ `playbackPosition` is deliberately NOT the target here: this file uses it with `??` and
    # `guard let`, so making it non-optional is not valid Swift and the mutation cannot compile — a
    # mutation that cannot compile proves nothing, so it must not be listed as if it did.
    # `year` is read but never unwrapped, so removing ITS optionality is a clean test of the rule that
    # an optional key must tolerate absence.
    ("an optional key made required", "LibraryModels.swift",
     "let year: Int?", "let year: Int",
     "a row with nothing but title and id still reads"),
    ("the progress claim", "LibraryModels.swift",
     "guard let runtime, runtime > 0, let position = playbackPosition, position > 0 else { return nil }",
     "guard let runtime, runtime >= 0, let position = playbackPosition, position >= 0 else { return nil }",
     "no runtime means no progress claim"),
    ("the resumable rule", "LibraryModels.swift",
     "return (playbackPosition ?? 0) > 0 || (played ?? false)",
     "return true",
     "a never-played item is not resumable"),
    ("the absent-items coalescing", "LibraryModels.swift",
     "var rows: [MediaItem] { items ?? [] }",
     "var rows: [MediaItem] { [] }",
     "an absent items coalesces to an empty wall"),
    ("the folder-id requirement", "LibraryModels.swift",
     "let folderID: String\n", "let folderID: String?\n",
     "a folder payload without a folder id is refused"),
]


def find_swiftc() -> str | None:
    candidates = [shutil.which("swiftc"), "/opt/swift/usr/bin/swiftc", "/usr/bin/swiftc"]
    for candidate in candidates:
        if candidate and pathlib.Path(candidate).exists():
            return candidate
    return None


def exec_dir() -> pathlib.Path:
    """⚠ A directory that allows execution. `/tmp` is `noexec` in this sandbox."""
    override = os.environ.get("RKM_CHECK_TMP")
    base = pathlib.Path(override) if override else pathlib.Path.home() / "tmp"
    base.mkdir(parents=True, exist_ok=True)
    return base


def stage(workdir: pathlib.Path) -> None:
    workdir.mkdir(parents=True, exist_ok=True)
    for path in PURE_SOURCES:
        shutil.copy(path, workdir / path.name)
    shutil.copy(HARNESS, workdir / HARNESS.name)


def sources_in(workdir: pathlib.Path) -> list[pathlib.Path]:
    return [workdir / path.name for path in PURE_SOURCES] + [workdir / HARNESS.name]


def compile_and_run(swiftc: str, workdir: pathlib.Path, *, quiet: bool = False,
                    attempts: int = 2) -> tuple[int, str]:
    """Compile into `workdir` and run. ⚠ Retries a failed COMPILE once: this sandbox kills a `swiftc`
    under memory pressure now and then, and a gate that reports a rule as unpinned because the compiler
    was killed is a gate that cries wolf."""
    binary = workdir / "tvos-core-tests"
    failure = ""
    for _ in range(attempts):
        build = subprocess.run(
            [swiftc, "-o", str(binary)] + [str(path) for path in sources_in(workdir)],
            capture_output=True,
            text=True,
        )
        if build.returncode == 0:
            break
        detail = build.stderr.strip()[:2000] or "(no compiler output — the process was killed, likely memory pressure)"
        failure = f"compile failed (rc {build.returncode}):\n{detail}"
    else:
        return 2, failure

    run = subprocess.run([str(binary)], capture_output=True, text=True)
    output = run.stdout + run.stderr
    if not quiet:
        print(output.rstrip())
    return run.returncode, output


def main(argv: list[str]) -> int:
    falsify = "--falsify" in argv
    swiftc = find_swiftc()
    if swiftc is None:
        print("no swiftc found — cannot run the Phase B core gate on this machine.", file=sys.stderr)
        print("  looked for: swiftc on PATH, /opt/swift/usr/bin/swiftc, /usr/bin/swiftc", file=sys.stderr)
        return 3

    base = exec_dir()
    print(f"swiftc: {swiftc}")
    print(f"temp:   {base}")

    with tempfile.TemporaryDirectory(dir=base) as tmp:
        workdir = pathlib.Path(tmp) / "pass"
        stage(workdir)
        print(f"\n=== PASS RUN ({len(PURE_SOURCES)} pure sources + harness) ===")
        code, output = compile_and_run(swiftc, workdir)
        if code == 2:
            print(output)
            return 2
        if code != 0:
            print("\nThe Phase B core gate FAILED. Fix the rules, not the harness.")
            return 1

    if not falsify:
        print("\n(no --falsify: the rules were not reverted. Use --falsify for the full gate.)")
        return 0

    print(f"\n=== FALSIFICATION ({len(MUTATIONS)} rules reverted one at a time) ===")
    survivors: list[str] = []
    stale: list[str] = []
    with tempfile.TemporaryDirectory(dir=base) as tmp:
        root = pathlib.Path(tmp)
        for index, (label, filename, old, new, expected) in enumerate(MUTATIONS, start=1):
            workdir = root / f"m{index:02d}"
            stage(workdir)
            target = workdir / filename
            text = target.read_text(encoding="utf-8")
            if old not in text:
                stale.append(f"{label} ({filename})")
                print(f"[{index:02d}] STALE  {label} — the text to revert is no longer in {filename}")
                continue
            target.write_text(text.replace(old, new, 1), encoding="utf-8")
            code, output = compile_and_run(swiftc, workdir, quiet=True)
            if code == 2:
                print(f"[{index:02d}] ERROR  {label} — mutation did not compile")
                print("       " + (output.splitlines()[0] if output else ""))
                survivors.append(f"{label} (did not compile)")
                continue
            hit = expected in output
            if code != 0 and hit:
                print(f"[{index:02d}] red    {label} -> {expected}")
            elif code != 0 and not hit:
                survivors.append(label)
                print(f"[{index:02d}] WRONG  {label} — went red, but not on {expected!r}")
                for line in output.splitlines():
                    if line.strip().startswith("FAIL"):
                        print(f"       {line.strip()}")
            else:
                survivors.append(label)
                print(f"[{index:02d}] GREEN  {label} — reverted and the harness STILL PASSED")

    print("")
    if stale:
        print(f"⚠ {len(stale)} mutation(s) no longer match the source — the tool needs updating, "
              f"and until then it proves nothing about them:")
        for label in stale:
            print(f"  · {label}")
    if survivors:
        print(f"FAIL — {len(survivors)} rule(s) are not actually pinned:")
        for label in survivors:
            print(f"  · {label}")
        return 1
    if stale:
        return 2
    print(f"PASS — {len(MUTATIONS)}/{len(MUTATIONS)} rules reverted, every one went red on the check it protects.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
