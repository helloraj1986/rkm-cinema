#!/usr/bin/env python3
"""The tvOS MEMBERS gate — the names a SwiftUI view uses against the models nothing compiles them against.

⚠⚠ **WHY THIS EXISTS, measured 2026-09-20.** Phase U's first Mac round died on ONE line:

    Home/HomeView.swift:80:40: error: value of type 'HomeSnapshot' has no member 'navFailure'

`HomeView` asked the snapshot for a property that was never written, and **every gate on this machine was
blind to it by construction**: there is no SwiftUI on Linux, so a view is compiled by nothing here
(`check-apple-typecheck.sh` says so in its own footer), and `check-imports.py` checks imports, not members.
That is the same blind spot B2's `import RKMServerKit` failure found — and this repo's rule for it is to
**fix the GATE before the next round rather than after it**, because a round is the most expensive thing in
this workflow and he does not want to spend rounds discovering one typo at a time.

⚠⚠ **IT IS DELIBERATELY NARROW, AND THAT IS THE DESIGN.** A general "every dot-access in the app must exist"
sweep needs a type checker; a half-version would flag Swift's own members (`count`, `map`, `first`) and cry
wolf, and **a gate that cries wolf is worse than an honestly absent one**. So it checks a small TABLE of
(file, variable, type) triples that are already unambiguous in these sources — the models the redesigned
screens read — and it checks only the FIRST member after the variable, never a chain.

⚠ What it does NOT cover: types and call *shapes* (a wrong argument label still needs the compiler), anything
in a file not listed below, and any behaviour at all. It catches the one class of mistake that has actually
cost a round: a member written in a view that the model does not have.

Usage:
    python3 apple/scripts/check-tvos-members.py              # the gate
    python3 apple/scripts/check-tvos-members.py --selftest   # prove it fires on a member that does not exist

Exit codes: 0 = PASS · 1 = a view names a member the model does not define · 2 = the tool could not run.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import shutil
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[2]
TVOS = REPO / "apple" / "tvos" / "RKMCinemaTV"

#: type name -> the file that declares it. ⚠ A type declared in the VIEW file it is used in (`TopBarTab`)
#: is listed the same way: the scan reads whichever file declares it.
TYPE_SOURCES = {
    "HomeSnapshot": "Core/HomeRails.swift",
    "NavOutcome": "Core/HomeRails.swift",
    "HomeRail": "Core/HomeRails.swift",
    "HomeStore": "Core/HomeStore.swift",
    "BrowseStore": "Core/BrowseStore.swift",
    "DetailStore": "Core/DetailStore.swift",
    "SessionStore": "Auth/SessionStore.swift",
    "AppModel": "App/AppModel.swift",
    "MediaItem": "Core/Models/LibraryModels.swift",
    "ProfileUser": "Core/Models/AuthModels.swift",
    "ItemDetail": "Core/Models/DetailModels.swift",
    "DetailSnapshot": "Core/DetailRules.swift",
    "LibraryNavEntry": "Core/BrowseRules.swift",
    "TopBarTab": "Home/TopBar.swift",
}

#: (view file, variable, type). ⚠ `snapshot` appears twice with DIFFERENT types, which is exactly why the
#: table is per file: in `HomeView` it is the Home's snapshot, in `DetailView` the detail screen's.
USES = [
    ("Home/HomeView.swift", "store", "HomeStore"),
    ("Home/HomeView.swift", "snapshot", "HomeSnapshot"),
    ("Home/HomeView.swift", "hero", "MediaItem"),
    ("Home/HomeView.swift", "app", "AppModel"),
    ("Home/HeroBand.swift", "item", "MediaItem"),
    ("Home/PosterCard.swift", "item", "MediaItem"),
    ("Home/RailView.swift", "rail", "HomeRail"),
    ("Home/RailView.swift", "item", "MediaItem"),
    ("Home/TopBar.swift", "tab", "TopBarTab"),
    ("Browse/BrowseView.swift", "store", "BrowseStore"),
    ("Browse/BrowseView.swift", "entry", "LibraryNavEntry"),
    ("Browse/BrowseView.swift", "app", "AppModel"),
    ("Detail/DetailView.swift", "store", "DetailStore"),
    ("Detail/DetailView.swift", "snapshot", "DetailSnapshot"),
    ("Detail/DetailView.swift", "detail", "ItemDetail"),
    ("Detail/DetailView.swift", "app", "AppModel"),
    ("Auth/ProfilesView.swift", "session", "SessionStore"),
    ("Auth/ProfilesView.swift", "profile", "ProfileUser"),
    ("Auth/ProfilesView.swift", "app", "AppModel"),
    ("Auth/LoginView.swift", "session", "SessionStore"),
    ("App/AppRootView.swift", "app", "AppModel"),
    ("Server/ServerSetupView.swift", "app", "AppModel"),
    ("Server/UnreachableServerView.swift", "app", "AppModel"),
]

#: Members a type gets for free, which no declaration in its own file can show. Kept to the protocols the
#: app's models actually conform to, and to members this scan has SEEN used — not to guesses.
INHERITED = {
    "MediaItem": {"id"},          # Identifiable, declared as a computed property in the file anyway
    "ProfileUser": {"id"},
    "LibraryNavEntry": {"id"},
    "HomeRail": {"id"},
    "TopBarTab": {"id"},
}

DECL = re.compile(
    r"^\s*(?:@[A-Za-z]+(?:\([^)]*\))?\s+)*"          # attributes: @Published, @FocusState, @Environment…
    r"(?:public\s+|internal\s+|private\s*\(set\)\s+|private\s+|fileprivate\s+|final\s+|static\s+)*"
    r"(?:let|var|func)\s+([A-Za-z_][A-Za-z0-9_]*)"
)
NESTED = re.compile(r"^\s*(?:enum|struct|class|typealias)\s+([A-Za-z_][A-Za-z0-9_]*)")


def members_of(root: pathlib.Path, type_name: str) -> set[str]:
    """Every member DECLARED inside a type, plus its nested type names, plus what it inherits for free.

    ⚠ The scan starts at the type's own declaration and stops at the first line that closes the type at
    column 0 — a brace-depth count rather than a parser, which is enough for this file set and cheap.
    """
    rel = TYPE_SOURCES[type_name]
    path = root / rel
    if not path.exists():
        raise FileNotFoundError(f"{rel} declares {type_name} and does not exist")
    found: set[str] = set()
    inside = False
    depth = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not inside:
            if re.match(rf"^(?:public\s+|final\s+)*(?:enum|struct|class|extension)\s+{type_name}\b", stripped):
                inside = True
                depth = stripped.count("{") - stripped.count("}")
                continue
            continue
        if stripped.startswith("//"):
            continue
        # ⚠⚠ TOP LEVEL OF THE TYPE BODY ONLY (depth 1: the type's own `{` is already open), and this is not
        # tidiness — a function body's LOCALS are also declared with `let`/`var`, so a scan that counted them
        # would "find" a member that only exists inside another method and would then pass a view naming it.
        # `HomeRails.rails` has locals called `cw` and `played`, which is exactly the shape that would have
        # made this gate quietly useless.
        if depth == 1:
            match = DECL.match(line)
            if match:
                found.add(match.group(1))
            nested = NESTED.match(line)
            if nested:
                found.add(nested.group(1))
        depth += line.count("{") - line.count("}")
        if depth <= 0:
            break
    if not found:
        raise ValueError(f"no members found for {type_name} in {rel} — the scan is looking at nothing")
    found |= INHERITED.get(type_name, set())
    return found


def check(root: pathlib.Path) -> list[str]:
    problems: list[str] = []
    cache: dict[str, set[str]] = {}
    for rel_file, variable, type_name in USES:
        source = root / rel_file
        if not source.exists():
            problems.append(f"{rel_file}: listed in USES and does not exist")
            continue
        if type_name not in cache:
            cache[type_name] = members_of(root, type_name)
        known = cache[type_name]
        text = source.read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), start=1):
            if line.lstrip().startswith("//"):
                continue
            # ⚠ The FIRST member after the variable only, and `?.` counts: `item.episode?.seriesName`
            # is a check on `episode`.
            for match in re.finditer(rf"\b{re.escape(variable)}\s*[?.]\s*([A-Za-z_][A-Za-z0-9_]*)", line):
                member = match.group(1)
                if member not in known:
                    problems.append(
                        f"{rel_file}:{number}: `{variable}.{member}` — {type_name} has no member "
                        f"'{member}' (it has {len(known)}: {', '.join(sorted(known))})"
                    )
    return problems


def selftest() -> int:
    """⚠ A CHECK THAT CANNOT FAIL IS NOT A CHECK. This one is proved by breaking the thing it guards in a
    scratch copy of the tvOS tree and requiring a report — and by requiring the REAL tree to be silent, so
    a rule that fires on everything cannot pass for evidence."""
    failures: list[str] = []
    with tempfile.TemporaryDirectory(dir=str(pathlib.Path.home() / "tmp")) as tmp:
        scratch = pathlib.Path(tmp) / "RKMCinemaTV"
        shutil.copytree(TVOS, scratch)

        # The exact defect U5's round died on.
        view = scratch / "Home" / "HomeView.swift"
        view.write_text(view.read_text(encoding="utf-8")
                        + "\nlet scratchBad = store.snapshot.navFailure\n", encoding="utf-8")
        if not any("navFailure" in problem for problem in check(scratch)):
            failures.append("it did not fire on `store.snapshot.navFailure` — the defect a round was spent on")

        # …and a member that does exist must stay silent, or the rule is just noise.
        view.write_text(view.read_text(encoding="utf-8").replace("navFailure", "nav"), encoding="utf-8")
        if any("Home/HomeView.swift" in problem for problem in check(scratch)):
            failures.append("it fired on `store.snapshot.nav`, which IS a member")

        # A view file that names a member the model lost.
        card = scratch / "Home" / "PosterCard.swift"
        card.write_text(card.read_text(encoding="utf-8") + "\nlet scratchBad2 = item.progressFractions\n",
                        encoding="utf-8")
        if not any("progressFractions" in problem for problem in check(scratch)):
            failures.append("it did not fire on a member with a typo'd name")

        if check(TVOS):
            failures.append("it fires on the REAL tree, so its red above proved nothing")

    if failures:
        print("SELFTEST FAILED — the members gate does not do what its header claims:")
        for line in failures:
            print(f"  · {line}")
        return 1
    print("selftest: fires on the defect, stays silent on a real member and on the real tree.")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Check the members the tvOS SwiftUI views use.")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)

    if not TVOS.exists():
        print(f"no tvOS sources at {TVOS}", file=sys.stderr)
        return 2

    if args.selftest:
        return selftest()

    try:
        problems = check(TVOS)
    except (FileNotFoundError, ValueError) as error:
        print(f"cannot run: {error}", file=sys.stderr)
        return 2

    if problems:
        print("FAIL — the members gate:")
        for line in problems:
            print(f"  · {line}")
        return 1
    print(f"PASS — {len(USES)} view/type pair(s) checked, every member a view names exists on its model.")
    print("⚠ Not covered: types and call shapes (argument labels still need the compiler), any file not")
    print("  listed in USES, and behaviour. This gate catches ONE class of mistake — the one that has")
    print("  already cost a round: a member written in a view that the model does not have.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
