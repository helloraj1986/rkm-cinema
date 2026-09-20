#!/usr/bin/env python3
"""The tvOS design-token gate — three rules, all of them possible to FAIL, and all three proved to fail.

⚠ WHY A GATE RATHER THAN A CONVENTION. `docs/TVOS_UX_PLAN.md` §2: the tvOS buildspec's colour table was
wrong in **8 of 10 values including the brand accent** (`#F2B93A` vs the real `#ffc400`), so this phase
generates the tokens from the web app's CSS instead of transcribing them. A generated file with no gate is
just a hand-copied file that happens to be right today.

The rules:

  R1  **DRIFT.** `DesignTokens.swift` must be exactly what `generate-design-tokens.py` produces from
      `frontend/src/styles/index.css` — regenerate and require a no-op. A CSS change that is not
      regenerated fails the round HERE, not on a TV.
  R2  **THE ONE tvOS DIFFERENCE IS NOT REACHED PAST.** `TVTokens.Colour.textMuted` is deliberately the
      television's own grey (`#81858f`), while every other colour comes from the generated table. A tvOS
      source naming the web app's `DesignTokens.Colour.textMuted` would silently undo that — so it is a
      failure, and `RKMColour.muted` is the name it should use.
  R3  **NO HEX LITERALS OUTSIDE THE TOKEN FILES.** The CSS's own header says it: *"never scatter arbitrary
      colours in components"*. A view that builds its own `Color(red:…)` or spells `#ffc400` is a second
      copy of the palette, and it is the copy that does not move when the brand does. (There is no hex
      parser in the app at all — the Python generator does the parsing — so a literal here would also be
      unverified.)

⚠ What this gate does NOT cover: whether the colours LOOK right, and anything SwiftUI
(`DesignColours.swift` is deliberately gate-invisible — see its header). Those are his round.

Usage:
    python3 apple/scripts/check-design-tokens.py              # the gate
    python3 apple/scripts/check-design-tokens.py --falsify    # + prove each rule can go RED

Exit codes: 0 = PASS · 1 = a rule failed (or a falsification did not) · 2 = the tool could not run.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[2]
TVOS = REPO / "apple" / "tvos"
GENERATOR = REPO / "apple" / "scripts" / "generate-design-tokens.py"
GENERATED = TVOS / "RKMCinemaTV" / "Design" / "DesignTokens.swift"

#: ⚠ The WEB app's de-emphasised grey. It must be read through `TVTokens` on tvOS (R2).
WEB_MUTED = "DesignTokens.Colour.textMuted"

#: R3's two shapes. `.white.opacity(…)` and the system styles (`Color.black`) are untouched: they are not
#: brand colours and banning them would be a rule nobody could keep.
HEX_LITERAL = re.compile(r"#[0-9a-fA-F]{6}\b")
COLOUR_CONSTRUCTION = re.compile(r"Color\(\s*(\.sRGB|red:)")

#: ⚠ `Design/` is exempt — it is where tokens are DEFINED. The generated file holds the numbers and
#: `DesignColours.swift` is the one conversion to `Color`.
TOKEN_DIR = TVOS / "RKMCinemaTV" / "Design"


def swift_sources(root: pathlib.Path) -> list[pathlib.Path]:
    """Every `.swift` file the tvOS app compiles, excluding the token files themselves."""
    out: list[pathlib.Path] = []
    for path in sorted(root.rglob("*.swift")):
        if ".build" in path.parts:
            continue
        try:
            path.relative_to(root / "RKMCinemaTV" / "Design")
            continue
        except ValueError:
            pass
        out.append(path)
    return out


def check_drift(css: pathlib.Path | None = None) -> list[str]:
    """R1 — regenerate and require no diff."""
    command = [sys.executable, str(GENERATOR), "--check"]
    if css is not None:
        command += ["--css", str(css)]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode == 0:
        return []
    detail = (result.stdout + result.stderr).strip().splitlines()
    return ["R1 drift: " + (detail[0] if detail else "the generator reported drift")]


def check_web_muted(root: pathlib.Path) -> list[str]:
    """R2 — the tvOS tree must not reach for the web app's muted grey."""
    problems: list[str] = []
    for path in swift_sources(root):
        text = path.read_text(encoding="utf-8")
        if WEB_MUTED in text:
            problems.append(f"R2 {path.relative_to(REPO) if REPO in path.parents else path}: "
                            f"names {WEB_MUTED} — tvOS reads TVTokens.Colour.textMuted (RKMColour.muted)")
    return problems


def check_no_literals(root: pathlib.Path) -> list[str]:
    """R3 — no hex literals and no hand-built colours outside the token files."""
    problems: list[str] = []
    for path in swift_sources(root):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if line.lstrip().startswith("//"):
                continue
            if HEX_LITERAL.search(line) or COLOUR_CONSTRUCTION.search(line):
                problems.append(f"R3 {path.relative_to(REPO) if REPO in path.parents else path}:{number}: "
                                f"{line.strip()} — read it from DesignTokens/TVTokens instead")
    return problems


def run(root: pathlib.Path) -> list[str]:
    return check_drift() + check_web_muted(root) + check_no_literals(root)


def falsify() -> int:
    """⚠⚠ A CHECK THAT CANNOT FAIL IS NOT A CHECK. Each rule is proved by breaking the thing it guards in a
    SCRATCH copy (or against a scratch CSS) and requiring it to go red — the repo's rule, and the reason
    three earlier gates in this project were found to prove nothing (`apple/WORKSPACE.md` §5's habit)."""
    failures: list[str] = []

    with tempfile.TemporaryDirectory(dir=str(pathlib.Path.home() / "tmp")) as tmp:
        scratch_root = pathlib.Path(tmp) / "tvos"
        shutil.copytree(TVOS, scratch_root, ignore=shutil.ignore_patterns(".build"))

        # R1 — a CSS value the generated file does not carry.
        scratch_css = pathlib.Path(tmp) / "index.css"
        scratch_css.write_text(
            (REPO / "frontend" / "src" / "styles" / "index.css")
            .read_text(encoding="utf-8")
            .replace("--accent: #ffc400;", "--accent: #f2b93a;"),
            encoding="utf-8",
        )
        if "R1 drift" not in " ".join(check_drift(scratch_css)):
            failures.append("R1 did not go red when the CSS changed without a regeneration")

        # R2 — a view naming the web app's muted grey.
        muted_target = scratch_root / "RKMCinemaTV" / "Home" / "PosterCard.swift"
        muted_target.write_text(muted_target.read_text(encoding="utf-8")
                                + f"\n// scratch\nlet scratchMuted = {WEB_MUTED}\n", encoding="utf-8")
        if not any(line.startswith("R2") for line in check_web_muted(scratch_root)):
            failures.append("R2 did not go red on a source naming the web app's textMuted")
        muted_target.write_text(muted_target.read_text(encoding="utf-8").split("\n// scratch")[0],
                               encoding="utf-8")

        # R3 — a hex literal, and a hand-built colour.
        card = scratch_root / "RKMCinemaTV" / "Home" / "PosterCard.swift"
        card.write_text(card.read_text(encoding="utf-8")
                        + '\nlet scratchHex = "#ffc400"\nlet scratchColour = Color(red: 1, green: 0.77, blue: 0)\n',
                        encoding="utf-8")
        r3 = [line for line in check_no_literals(scratch_root) if line.startswith("R3")]
        if len(r3) < 2:
            failures.append("R3 did not go red on both a hex literal and a Color(red:) construction")

        # …and the falsifiers must not have been proved by a rule that fires on everything.
        if check_web_muted(TVOS):
            failures.append("R2 fires on the REAL tree, so its red above proved nothing")
        if check_no_literals(TVOS):
            failures.append("R3 fires on the REAL tree, so its red above proved nothing")

    if failures:
        print("FALSIFICATION FAILED — these rules prove nothing:")
        for line in failures:
            print(f"  · {line}")
        return 1
    print("falsify: R1, R2 and R3 each went red when the thing they guard was broken.")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="The tvOS design-token gate (R1 drift, R2 muted, R3 literals).")
    parser.add_argument("--falsify", action="store_true")
    args = parser.parse_args(argv)

    if not GENERATOR.exists():
        print(f"no generator at {GENERATOR}", file=sys.stderr)
        return 2
    if not GENERATED.exists():
        print(f"no generated tokens at {GENERATED} — run apple/scripts/generate-design-tokens.py", file=sys.stderr)
        return 2

    if args.falsify:
        return falsify()

    problems = run(TVOS)
    if problems:
        print("FAIL — the design-token gate:")
        for line in problems:
            print(f"  · {line}")
        return 1
    print("PASS — R1 no drift, R2 the tvOS muted grey is the one reached for, R3 no scatter.")
    print("⚠ Not covered here: whether the colours LOOK right on a TV, and any SwiftUI file.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
