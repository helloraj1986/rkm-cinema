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

#: ⚠⚠ RULE 2 — the CALL SITES. A view that names a real type with the WRONG LABEL is a compile error of the
#: same family as a missing member, and the same round would be spent discovering it. Only these types are
#: checked, only in these files, and every label must be a declared property OR an `init` parameter.
VIEW_TYPES = {
    "TopBar": "Home/TopBar.swift",
    "TopBarTab": "Home/TopBar.swift",
    "HeroBand": "Home/HeroBand.swift",
    "RailView": "Home/RailView.swift",
    "PosterCard": "Home/PosterCard.swift",
    "PosterImageView": "Home/PosterCard.swift",
    "HomeView": "Home/HomeView.swift",
    "BrowseView": "Browse/BrowseView.swift",
    "DetailView": "Detail/DetailView.swift",
    "ProfilesView": "Auth/ProfilesView.swift",
    "LoginView": "Auth/LoginView.swift",
    "ServerSetupView": "Server/ServerSetupView.swift",
    "UnreachableServerView": "Server/UnreachableServerView.swift",
}

#: Where a call to one of those types may appear. ⚠ Their own declaration files are excluded: `HomeView`'s
#: body calls `TopBar(...)`, and `TopBar.swift` calling `Text(...)` is not a construction to check.
CALL_SITES = [
    "Home/HomeView.swift", "Home/TopBar.swift", "Home/HeroBand.swift", "Home/RailView.swift",
    "Home/PosterCard.swift", "Browse/BrowseView.swift", "Detail/DetailView.swift",
    "Auth/ProfilesView.swift", "Auth/LoginView.swift", "App/AppRootView.swift",
    "Server/ServerSetupView.swift", "Server/UnreachableServerView.swift",
]

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


def call_labels(root: pathlib.Path, type_name: str) -> set[str]:
    """The labels a call to this type MAY use: its top-level properties plus any `init` parameters.

    ⚠ Both, because a type may take a parameter it does not store (`PosterLoader(width:)` is passed straight
    to the URL builder). Allowing an unknown label is the failure this rule is FOR; allowing a known one that
    is not stored is what keeps it from crying wolf.
    """
    rel = VIEW_TYPES.get(type_name) or TYPE_SOURCES.get(type_name)
    path = root / rel
    if not path.exists():
        raise FileNotFoundError(f"{rel} declares {type_name} and does not exist")
    labels: set[str] = set()
    inside = False
    depth = 0
    in_init = False
    init_depth = 0
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
        if in_init:
            # Every `name:` inside the parameter list, until the list closes.
            for match in re.finditer(r"([A-Za-z_][A-Za-z0-9_]*)\s*:", line):
                labels.add(match.group(1))
            if ")" in line:
                in_init = False
            depth += line.count("{") - line.count("}")
            if depth <= 0:
                break
            continue
        if depth == 1:
            if re.match(r"^\s*(?:public\s+|internal\s+|private\s+|fileprivate\s+)*init\s*\(", line):
                in_init = True
                init_depth = depth
                labels.add("init")   # sentinel, never used as a label
                for match in re.finditer(r"([A-Za-z_][A-Za-z0-9_]*)\s*:", line):
                    labels.add(match.group(1))
                if ")" in line:
                    in_init = False
                continue
            match = DECL.match(line)
            if match:
                labels.add(match.group(1))
        depth += line.count("{") - line.count("}")
        if depth <= 0:
            break
    labels.discard("init")
    if not labels:
        raise ValueError(f"no labels found for {type_name} in {rel} — the scan is looking at nothing")
    return labels


def check_calls(root: pathlib.Path) -> list[str]:
    """⚠ Every label used when this app constructs one of its OWN views/types must exist on that type."""
    problems: list[str] = []
    cache: dict[str, set[str]] = {}
    for rel_file in CALL_SITES:
        source = root / rel_file
        if not source.exists():
            problems.append(f"{rel_file}: listed in CALL_SITES and does not exist")
            continue
        text = source.read_text(encoding="utf-8")
        lines = text.splitlines()
        for number, line in enumerate(lines, start=1):
            if line.lstrip().startswith("//"):
                continue
            for name in VIEW_TYPES:
                for match in re.finditer(rf"\b{name}\s*\(", line):
                    # ⚠ Skip `Type(` inside a declaration (`struct Type(`) and skip the type's own file.
                    if rel_file == VIEW_TYPES[name]:
                        continue
                    if re.search(rf"(?:struct|class|enum|extension)\s+{name}\s*$", line[:match.start()]):
                        continue
                    if name not in cache:
                        cache[name] = call_labels(root, name)
                    known = cache[name]
                    tail = line[match.end():]
                    for label in re.finditer(r"([A-Za-z_][A-Za-z0-9_]*)\s*:(?!\s*//)", tail):
                        if label.group(1) not in known:
                            problems.append(
                                f"{rel_file}:{number}: `{name}(…)` is called with '{label.group(1)}:', which "
                                f"{name} does not take (it takes {', '.join(sorted(known))})"
                            )
    return problems


#: ⚠⚠ RULE 3 — the STATIC NAMESPACES. `HomeRules.badgeText`, `TVTokens.Shelf.cardWidth`, `RKMColour.accent`.
#: A typo in one of these is the same family of compile error as a missing member, and after U6 the token
#: tables are the most hand-typed names in the app (≈150 new references in one phase).
NAMESPACES = ("HomeRules", "ProfileRules", "BrowseRules", "DetailRules", "PosterURL", "DesignTokens", "TVTokens",
              "RKMColour", "LibraryIcon", "DetailCopy", "HomeSnapshot", "HomeRowFailure", "HomeStore",
              "BrowseStore", "DetailStore", "SessionStore", "AppModel", "AppLog", "ServerDefaults",
              "LibraryAPI", "RequestURL")


def namespace_members(root: pathlib.Path, namespace: str, cache: dict) -> set[str]:
    """Every name declared in the file that declares `namespace` — nested types, statics, computed properties.

    ⚠ ANY depth, unlike rule 1: `TVTokens.Shelf.cardWidth` is a static inside a NESTED enum, and a
    depth-1-only scan would report every one of those as missing.
    """
    if namespace in cache:
        return cache[namespace]
    declaring = None
    for path in sorted(root.rglob("*.swift")):
        if ".build" in path.parts:
            continue
        if re.search(rf"^(?:public\s+|final\s+)*(?:enum|struct|class|extension)\s+{namespace}\b",
                     path.read_text(encoding="utf-8"), re.M):
            declaring = path
            break
    if declaring is None:
        raise ValueError(f"no file declares {namespace} — the table is stale")
    names: set[str] = set()
    for line in declaring.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("//"):
            continue
        for pattern in (r"^\s*(?:@\w+(?:\([^)]*\))?\s+)*(?:public\s+|internal\s+|private\s*\(set\)\s+|private\s+|fileprivate\s+|static\s+|final\s+)*(?:let|var|func|enum|struct|class|typealias|case)\s+([A-Za-z_][A-Za-z0-9_]*)",
                        r"^\s*(?:public\s+|internal\s+|private\s+|fileprivate\s+)*enum\s+([A-Za-z_][A-Za-z0-9_]*)"):
            found = re.match(pattern, line)
            if found and not line.strip().startswith("//"):
                names.add(found.group(1))
    cache[namespace] = names
    return names


def check_namespaces(root: pathlib.Path) -> list[str]:
    """⚠ Every `<Namespace>.<member>` a tvOS source names must be declared by that namespace's file."""
    problems: list[str] = []
    cache: dict = {}
    for path in sorted(root.rglob("*.swift")):
        if ".build" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), start=1):
            if line.lstrip().startswith("//"):
                continue
            for namespace in NAMESPACES:
                # ⚠ Skip `extension Foo` / `enum Foo` declarations, which are not member uses.
                declared = re.search(rf"(?:enum|struct|class|extension)\s+{namespace}\b", line)
                for match in re.finditer(rf"\b{namespace}\.([A-Za-z_][A-Za-z0-9_]*)", line):
                    if declared and match.start() >= declared.start():
                        continue
                    member = match.group(1)
                    if member not in namespace_members(root, namespace, cache):
                        problems.append(
                            f"{path.relative_to(root)}:{number}: `{namespace}.{member}` — {namespace} does "
                            f"not declare '{member}'"
                        )
    return problems


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

        # Rule 2: one of the app's own views constructed with a label it does not take.
        browse = scratch / "Browse" / "BrowseView.swift"
        browse.write_text(browse.read_text(encoding="utf-8")
                          + "\nlet scratchBad3 = RailView(rails: [], base: URL(string: \"http://x\")!,"
                            " onSelect: { _ in })\n", encoding="utf-8")
        reports = check_calls(scratch)
        if not any("rails:" in problem for problem in reports):
            failures.append("it did not fire on `RailView(rails: …)` — a label RailView does not take")
        # ⚠ …and it must NOT fire on the three labels that view DOES take, or the rule is noise.
        if any("base:" in problem or "onSelect:" in problem for problem in reports):
            failures.append("it fired on a label RailView does take")

        if check(TVOS):
            failures.append("it fires on the REAL tree, so its red above proved nothing")
        if check_calls(TVOS):
            failures.append("rule 2 fires on the REAL tree, so its red above proved nothing")
        if check_namespaces(TVOS):
            failures.append("rule 3 fires on the REAL tree, so its red above proved nothing")

        # Rule 3: a static-namespace member that does not exist.
        hero = scratch / "Home" / "HeroBand.swift"
        hero.write_text(hero.read_text(encoding="utf-8")
                        + "\nlet scratchBad4 = HomeRules.heroEyebrows\n", encoding="utf-8")
        if not any("heroEyebrows" in problem for problem in check_namespaces(scratch)):
            failures.append("it did not fire on `HomeRules.heroEyebrows` — a member that does not exist")

    if failures:
        print("SELFTEST FAILED — the members gate does not do what its header claims:")
        for line in failures:
            print(f"  · {line}")
        return 1
    print("selftest: fires on all three defects (member, call label, static name), stays silent on the real tree.")
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
        problems = check(TVOS) + check_calls(TVOS) + check_namespaces(TVOS)
    except (FileNotFoundError, ValueError) as error:
        print(f"cannot run: {error}", file=sys.stderr)
        return 2

    if problems:
        print("FAIL — the members gate:")
        for line in problems:
            print(f"  · {line}")
        return 1
    print(f"PASS — {len(USES)} view/type pair(s) checked: every member a view names exists on its model, "
          f"and every call to one of the {len(VIEW_TYPES)} app view/type names uses a label it takes.")
    print(f"⚠ Not covered: TYPES (a value of the wrong type still needs the compiler), argument ORDER, and")
    print("  behaviour. THREE rules, all aimed at the class of mistake that has already cost a round:")
    print("  a member a view names that its model lacks; a call using a label its own type does not take;")
    print("  and a static-namespace name (HomeRules.*, TVTokens.* …) that is not declared anywhere.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
