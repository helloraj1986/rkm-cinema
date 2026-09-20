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
    # ⚠⚠ Phase V. The Library screen and the detail screen read four more types, and **two of them are
    # NESTED** (`BrowseRules.LibraryTabPlan`) — the table is keyed by the name the VIEW spells, and the scan
    # finds a declaration at any depth for exactly this reason.
    "BrowseRules.LibraryTabPlan": "Core/BrowseRules.swift",
    "SeasonGroup": "Core/DetailRules.swift",
    "EpisodeProgress": "Core/DetailRules.swift",
    "EpisodeItem": "Core/Models/LibraryModels.swift",
    "DetailPerson": "Core/Models/DetailModels.swift",
    # ⚠⚠ Phase C3 — the player. ⚠ `AVPlayer` is NOT listed and must not be: the SDK type is not a file this
    # scan can read, and rule 1 is a deliberate (file, variable, type) table precisely so it never has to
    # guess. The player's OWN types are all readable, and they are the ones worth checking.
    "PlaybackStore": "Core/PlaybackStore.swift",
    # ⚠ `PlayerFocus` / `DrawerFocus` are FOCUS ENUMS: their only "members" are cases, which the
    # depth-1 declaration scan does not read, so listing them would make this gate fail on itself.
    # Their correctness is the compiler's, and the compiler is the Mac.
}

#: (view file, variable, type). ⚠ `snapshot` appears twice with DIFFERENT types, which is exactly why the
#: table is per file: in `HomeView` it is the Home's snapshot, in `DetailView` the detail screen's.
USES = [
    ("Home/HomeView.swift", "store", "HomeStore"),
    ("Home/HomeView.swift", "snapshot", "HomeSnapshot"),
    ("Home/HomeView.swift", "hero", "MediaItem"),
    ("Home/HomeView.swift", "app", "AppModel"),
    # ⚠ Phase V: the top bar's tabs became a VALUE (`BrowseRules.tabPlan`), so the Home names its members.
    ("Home/HomeView.swift", "plan", "BrowseRules.LibraryTabPlan"),
    ("Home/HeroBand.swift", "item", "MediaItem"),
    ("Home/PosterCard.swift", "item", "MediaItem"),
    ("Home/RailView.swift", "rail", "HomeRail"),
    ("Home/RailView.swift", "item", "MediaItem"),
    ("Home/TopBar.swift", "tab", "TopBarTab"),
    ("Browse/BrowseView.swift", "store", "BrowseStore"),
    ("Browse/BrowseView.swift", "entry", "LibraryNavEntry"),
    ("Browse/BrowseView.swift", "app", "AppModel"),
    ("Browse/BrowseView.swift", "plan", "BrowseRules.LibraryTabPlan"),
    ("Browse/BrowseView.swift", "item", "MediaItem"),
    ("Browse/LibraryGridCard.swift", "item", "MediaItem"),
    ("Detail/DetailView.swift", "store", "DetailStore"),
    ("Detail/DetailView.swift", "snapshot", "DetailSnapshot"),
    ("Detail/DetailView.swift", "detail", "ItemDetail"),
    ("Detail/DetailView.swift", "app", "AppModel"),
    ("Detail/DetailView.swift", "person", "DetailPerson"),
    ("Detail/DetailView.swift", "episode", "EpisodeItem"),
    ("Detail/DetailView.swift", "group", "SeasonGroup"),
    ("Detail/DetailView.swift", "progress", "EpisodeProgress"),
    # ⚠⚠ Phase C3: the player. Rule 1 is the gate that caught round 1's `navFailure` and it is the ONLY
    # thing standing between these files and a failed Mac round, so the store, the snapshot's owner and
    # the panel are all listed. ⚠ `store` is listed FOUR times against four different types (the reason
    # this table is keyed by (file, variable) and not by variable name).
    ("Player/PlayerView.swift", "store", "PlaybackStore"),
    ("Player/PlayerView.swift", "app", "AppModel"),
    ("Player/PlayerChrome.swift", "store", "PlaybackStore"),
    ("Player/PlayerSettingsPanel.swift", "store", "PlaybackStore"),
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
    "BrowseRules.LibraryTabPlan": {"id"},
    "SeasonGroup": {"id"},
    "EpisodeItem": {"id"},
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
    # ⚠ Phase V's two new views: the library grid's card and its filter chip. Both are constructed from
    # `BrowseView` with labelled arguments, so a renamed or misspelled label is a compile error this rule
    # catches before a round.
    "LibraryGridCard": "Browse/LibraryGridCard.swift",
    "FilterChip": "Browse/FilterChip.swift",
    "DetailView": "Detail/DetailView.swift",
    "ProfilesView": "Auth/ProfilesView.swift",
    "LoginView": "Auth/LoginView.swift",
    "ServerSetupView": "Server/ServerSetupView.swift",
    "UnreachableServerView": "Server/UnreachableServerView.swift",
    # ⚠ The app's own BUTTON STYLES are constructed in the views too (`CtaButtonStyle(kind:)`), so their labels
    # are checked the same way — a style that took a `kind` and was passed `style:` is the same compile error.
    "CtaButtonStyle": "Home/HeroBand.swift",
    "PillButtonStyle": "Auth/ProfilesView.swift",
    "TabButtonStyle": "Home/TopBar.swift",
    "IconButtonStyle": "Home/TopBar.swift",
    "ProfileTileStyle": "Auth/ProfilesView.swift",
    "LibraryCardStyle": "Browse/LibraryGridCard.swift",
    "ChipButtonStyle": "Browse/FilterChip.swift",
    # ⚠⚠ Phase C3's player. `PlayerView` and the drawer are constructed from `AppRootView` / each other
    # with labelled arguments, and the four new control styles are the same class of construction
    # (`PlayerControlButtonStyle(primary:label:)`). ⚠ This is the ONE gate that sees these files at all:
    # `Player/PlayerView.swift` imports SwiftUI + AVFoundation + UIKit, so nothing here can compile it.
    "PlayerView": "Player/PlayerView.swift",
    "PlayerTopBar": "Player/PlayerChrome.swift",
    "PlayerScrubber": "Player/PlayerChrome.swift",
    "PlayerControlsRow": "Player/PlayerChrome.swift",
    "PlayerInfoPanel": "Player/PlayerChrome.swift",
    "PlayerCueStrip": "Player/PlayerChrome.swift",
    "PlayerToast": "Player/PlayerChrome.swift",
    "PlayerSettingsPanel": "Player/PlayerSettingsPanel.swift",
    "PlayerControlButtonStyle": "Player/PlayerChrome.swift",
    "PlayerCircleButtonStyle": "Player/PlayerChrome.swift",
    "PlayerScrubStyle": "Player/PlayerChrome.swift",
    "DrawerNavStyle": "Player/PlayerSettingsPanel.swift",
    "DrawerSegmentStyle": "Player/PlayerSettingsPanel.swift",
    "DrawerListStyle": "Player/PlayerSettingsPanel.swift",
}

#: Where a call to one of those types may appear. ⚠ Their own declaration files are excluded: `HomeView`'s
#: body calls `TopBar(...)`, and `TopBar.swift` calling `Text(...)` is not a construction to check.
CALL_SITES = [
    "Home/HomeView.swift", "Home/TopBar.swift", "Home/HeroBand.swift", "Home/RailView.swift",
    "Home/PosterCard.swift", "Browse/BrowseView.swift", "Detail/DetailView.swift",
    "Browse/LibraryGridCard.swift", "Browse/FilterChip.swift",
    "Player/PlayerView.swift", "Player/PlayerChrome.swift", "Player/PlayerSettingsPanel.swift",
    "Auth/ProfilesView.swift", "Auth/LoginView.swift", "App/AppRootView.swift",
    "Server/ServerSetupView.swift", "Server/UnreachableServerView.swift",
]

DECL = re.compile(
    r"^\s*(?:@[A-Za-z]+(?:\([^)]*\))?\s+)*"          # attributes: @Published, @FocusState, @Environment…
    r"(?:public\s+|internal\s+|private\s*\(set\)\s+|private\s+|fileprivate\s+|final\s+|static\s+)*"
    r"(?:let|var|func)\s+([A-Za-z_][A-Za-z0-9_]*)"
)
NESTED = re.compile(r"^\s*(?:enum|struct|class|typealias)\s+([A-Za-z_][A-Za-z0-9_]*)")


def declaration_name(type_name: str) -> str:
    """⚠ The name to look for in the DECLARATION line — the last component of a dotted key.

    A type may be nested (`BrowseRules.LibraryTabPlan` is declared as `struct LibraryTabPlan` INSIDE
    `enum BrowseRules`), and the table is keyed by the name the VIEW spells. Stripping the qualifier is what
    lets one table hold both spellings.
    """
    return type_name.rsplit(".", 1)[-1]


def members_of(root: pathlib.Path, type_name: str) -> set[str]:
    """Every member DECLARED inside a type, plus its nested type names, plus what it inherits for free.

    ⚠ The scan starts at the type's own declaration and stops at the first line that closes the type at
    column 0 — a brace-depth count rather than a parser, which is enough for this file set and cheap.
    """
    rel = TYPE_SOURCES[type_name]
    path = root / rel
    if not path.exists():
        raise FileNotFoundError(f"{rel} declares {type_name} and does not exist")
    decl_name = declaration_name(type_name)
    found: set[str] = set()
    inside = False
    depth = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not inside:
            if re.match(rf"^(?:public\s+|final\s+)*(?:enum|struct|class|extension)\s+{decl_name}\b", stripped):
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
    decl_name = declaration_name(type_name)
    labels: set[str] = set()
    inside = False
    depth = 0
    in_init = False
    init_depth = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not inside:
            if re.match(rf"^(?:public\s+|final\s+)*(?:enum|struct|class|extension)\s+{decl_name}\b", stripped):
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


#: ⚠⚠ A STRING LITERAL IS NOT AN ARGUMENT LABEL, and this line exists because the rule fired on one.
#: Measured 2026-09-20, adding the Title screen: `TopBarTab(id: "detail:back", …)` — the text INSIDE the
#: quotes reads as a label to a regex, so the gate reported a label `TopBarTab` does not take and **the tree
#: was correct**. A gate that cries wolf is worse than an absent one (this file's own header), so literals are
#: stripped before the labels are read — including escaped quotes, which is why the pattern is not `[^"]*`.
STRING_LITERAL = re.compile(r'"(?:[^"\\]|\\.)*"')


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
                    tail = STRING_LITERAL.sub('""', line[match.end():])
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
              "LibraryAPI", "RequestURL",
              # ⚠ Phase V: the library grid's rules and its copy. Both are read from the two new views many
              # times over, and every one of those references is a hand-typed name.
              "LibraryRules", "LibraryCopy")


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
    cache[namespace + "::file"] = declaring
    return names


def nested_members(declaring: pathlib.Path, type_name: str) -> set[str]:
    """Every name declared INSIDE `type_name`'s braces in `declaring` — the resolver for a DOTTED path.

    ⚠⚠ **WHY THIS EXISTS (added 2026-09-20, Phase C3).** Rule 3 verified `TVTokens.Player` and stopped: the
    metric AFTER it (`TVTokens.Player.controlSize`) was checked by NOTHING, because `namespace_members`
    returns a FLAT set of every name in the file and cannot tell a nested type's members from its siblings'.
    The player phase added ~100 such three-segment references in one go, and a typo in one of them is a
    compile error on the Mac — i.e. a whole round, for a hand-typed name. That is the same trade rule 3
    already makes for two segments; this closes the third.

    ⚠ It follows BRACES rather than indentation: a `func` body's braces are not a nesting level, and an
    indentation-based scan would either miss a one-line `enum` or invent members from a function's locals.
    ⚠ It looks for ANY type declaration with that name at any depth, because `Player` is nested inside
    `TVTokens` — the same reason rule 3's scan is depth-free.
    """
    lines = declaring.read_text(encoding="utf-8").splitlines()
    start = None
    for index, line in enumerate(lines):
        if re.match(rf"^\s*(?:public\s+|internal\s+|private\s+|fileprivate\s+|final\s+|static\s+)*"
                    rf"(?:enum|struct|class|extension)\s+{re.escape(type_name)}\b", line):
            start = index
            break
    if start is None:
        return set()
    members: set[str] = set()
    depth = 0
    opened = False
    for line in lines[start:]:
        stripped = line.strip()
        if not opened:
            if "{" in line:
                opened = True
                depth = line.count("{") - line.count("}")
            continue
        if depth == 1 and not stripped.startswith("//"):
            found = re.match(r"^\s*(?:@\w+(?:\([^)]*\))?\s+)*"
                             r"(?:public\s+|internal\s+|private\s*\(set\)\s+|private\s+|fileprivate\s+"
                             r"|static\s+|final\s+)*"
                             r"(?:let|var|func|case|enum|struct|class|typealias)\s+([A-Za-z_][A-Za-z0-9_]*)",
                             line)
            if found:
                members.add(found.group(1))
        depth += line.count("{") - line.count("}")
        if depth <= 0:
            break
    return members


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
                for match in re.finditer(
                        rf"\b{namespace}\.([A-Za-z_][A-Za-z0-9_]*)(?:\.([A-Za-z_][A-Za-z0-9_]*))?", line):
                    if declared and match.start() >= declared.start():
                        continue
                    member, deep = match.group(1), match.group(2)
                    if member not in namespace_members(root, namespace, cache):
                        problems.append(
                            f"{path.relative_to(root)}:{number}: `{namespace}.{member}` — {namespace} does "
                            f"not declare '{member}'"
                        )
                    elif deep:
                        # ⚠⚠ THE THIRD SEGMENT — see `nested_members`. Checked only when the SECOND segment
                        # resolved, so one typo reports once rather than twice.
                        nested = nested_members(cache[namespace + "::file"], member)
                        if nested and deep not in nested:
                            problems.append(
                                f"{path.relative_to(root)}:{number}: `{namespace}.{member}.{deep}` — "
                                f"{member} does not declare '{deep}'"
                            )
    return problems


#: ⚠⚠ RULE 4 — `Body` IS NOT A SAFE NAME TO NEST, and this is the SECOND round U6 spent on the same blind
#: spot. Every `Style` protocol (and `View`) declares an associatedtype requirement called `Body`, so a helper
#: view nested inside a conformer and named `Body` collides with it. Measured on his Mac, 2026-09-20:
#: `type 'TabButtonStyle' does not conform to protocol 'ButtonStyle'` +
#: `struct 'Body' must be as accessible as its enclosing type because it matches a requirement in protocol
#: 'ButtonStyle'`. ⚠ Phase A's tile style is called `TileBody` for this reason — the rule was known and then
#: forgotten, which is why it is a gate now. Nothing in this sandbox compiles SwiftUI, so a text rule is the
#: only thing that stands between this mistake and his round.
#:
#: ⚠ INDENTED ONLY: a `struct Body` at file scope collides with nothing, and flagging it would be the
#: false-positive that makes a gate worth ignoring.
NESTED_BODY = re.compile(r"^\s+(?:public\s+|internal\s+|private\s+|fileprivate\s+|final\s+)*struct\s+Body\b")


def check_nested_body(root: pathlib.Path) -> list[str]:
    problems: list[str] = []
    for path in sorted(root.rglob("*.swift")):
        if ".build" in path.parts:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if line.lstrip().startswith("//"):
                continue
            if NESTED_BODY.match(line):
                problems.append(
                    f"{path.relative_to(root)}:{number}: a nested type named `Body` — a `Style` protocol owns "
                    f"that name; call it `TileBody`/`TabChrome`/whatever it IS"
                )
    return problems


#: ⚠⚠ RULE 5 — **A STYLE THAT OWNS ITS BOX MUST NOT BE GIVEN ONE BY ITS CALLER.** His report, 2026-09-20:
#: *"homescreen → scrolling to details button → the ux has bug"* — the Home's `Details` button drew its focus
#: ring around the WORD, inside its own grey box, because the ring was drawn in the style while the padding and
#: the fill were applied to the `Button` (outside the label). A `ButtonStyle` only ever receives
#: `configuration.label`, so chrome applied to the Button is chrome the style cannot see.
#:
#: ⚠ **The fix was structural — `CtaButtonStyle` and `PillButtonStyle` now draw their own padding, fill,
#: border and ring, exactly as `TabButtonStyle` already did.** This rule is what keeps a sixth style from
#: re-introducing it, because no compiler here can: the difference between "ring around the box" and "ring
#: around the word" is one that ONLY the Mac can see, and he should not be the one who finds it.
#:
#: ⚠ HOW IT READS: from `.buttonStyle(<a style we own>)` it walks back to the enclosing `Button`, DELETES every
#: brace-delimited closure from that region (the action closure, the label closure — both legitimately contain
#: padding and backgrounds) and looks at what is left: the modifier chain applied to the BUTTON. That is
#: exactly the place the box must not be.
STYLE_TYPES = ("TabButtonStyle", "IconButtonStyle", "CtaButtonStyle", "PillButtonStyle", "ProfileTileStyle",
               # ⚠ Phase V's two, added the moment they existed: a style that owns its box is only protected
               # by this rule if the rule KNOWS about it, and a new style silently outside the list is how
               # the sixth one would re-introduce the defect his screenshot bought.
               "LibraryCardStyle", "ChipButtonStyle")
BOX_CHROME = (".padding(", ".background", ".overlay", ".frame(")
CLOSURE = re.compile(r"\{[^{}]*\}")


def check_style_ownership(root: pathlib.Path) -> list[str]:
    problems: list[str] = []
    for path in sorted(root.rglob("*.swift")):
        if ".build" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"\.buttonStyle\((\w+)", text):
            style = match.group(1)
            if style not in STYLE_TYPES:
                continue
            start = text.rfind("Button", 0, match.start())
            if start == -1:
                continue
            region = text[start:match.start()]
            # ⚠ Strip the closures (repeatedly, so a closure containing a closure goes too) — the label and the
            # action are allowed to draw anything; what is left is the chain applied to the Button itself.
            for _ in range(6):
                stripped = CLOSURE.sub("", region)
                if stripped == region:
                    break
                region = stripped
            for offender in BOX_CHROME:
                if offender in region:
                    line = text.count("\n", 0, start) + 1
                    problems.append(
                        f"{path.relative_to(root)}:{line}: `{offender}…)` is applied to a `Button` that uses "
                        f"`{style}` — that style draws its own box, so the caller's chrome lands INSIDE it "
                        f"(a focus ring around the label instead of around the button)"
                    )
                    break
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

        # ⚠⚠ AND A COLON INSIDE A STRING LITERAL IS NOT A LABEL — measured on the REAL tree 2026-09-20, when
        # `TopBarTab(id: "detail:back", …)` produced a report naming a label `TopBarTab` does not take, on a
        # file that was CORRECT. Both halves are pinned: the real wrong label still fires, and the literal
        # inside the quotes stays silent.
        browse.write_text(browse.read_text(encoding="utf-8")
                          + "\nlet scratchBad3b = TopBarTab(rails: [], title: \"detail:back\")\n",
                          encoding="utf-8")
        reports = check_calls(scratch)
        if not any("'rails:'" in problem for problem in reports):
            failures.append("it did not fire on `TopBarTab(rails: …)` — a label TopBarTab does not take")
        if any("detail:" in problem for problem in reports):
            failures.append("it fired on a colon inside a string literal — the 2026-09-20 false positive")

        # Rule 3's THIRD SEGMENT (added 2026-09-20, Phase C3's player): `TVTokens.Player.<metric>` was
        # verified as far as `TVTokens.Player` and the metric name after it by nothing at all.
        chrome = scratch / "Player" / "PlayerChrome.swift"
        chrome.parent.mkdir(parents=True, exist_ok=True)
        chrome.write_text((TVOS / "Player" / "PlayerChrome.swift").read_text(encoding="utf-8")
                          + "\nlet scratchBad3c = TVTokens.Player.controlSizee\n", encoding="utf-8")
        deep = check_namespaces(scratch)
        if not any("controlSizee" in problem for problem in deep):
            failures.append("it did not fire on `TVTokens.Player.controlSizee` — a metric Player does not "
                            "declare, and the name a token table is most likely to get wrong")
        if any("TVTokens.Player." in problem for problem in check_namespaces(TVOS)):
            failures.append("the deep rule fires on the REAL tree, so its red above proved nothing")

        if check(TVOS):
            failures.append("it fires on the REAL tree, so its red above proved nothing")
        if check_calls(TVOS):
            failures.append("rule 2 fires on the REAL tree, so its red above proved nothing")
        if check_namespaces(TVOS):
            failures.append("rule 3 fires on the REAL tree, so its red above proved nothing")
        if check_nested_body(TVOS):
            failures.append("rule 4 fires on the REAL tree, so its red above proved nothing")
        if check_style_ownership(TVOS):
            failures.append("rule 5 fires on the REAL tree, so its red above proved nothing")

        # Rule 5: the defect he found — chrome on the Button rather than in the style.
        profile = scratch / "Auth" / "ProfilesView.swift"
        profile.write_text(profile.read_text(encoding="utf-8")
                           + "\nlet scratchBad5 = Button(\"x\") {}.padding(4).buttonStyle(PillButtonStyle())\n",
                           encoding="utf-8")
        if not any("PillButtonStyle" in problem for problem in check_style_ownership(scratch)):
            failures.append("it did not fire on chrome applied to a Button that uses a style we own")

        # Rule 4: the name a `Style` protocol already owns.
        rail = scratch / "Home" / "RailView.swift"
        rail.write_text(rail.read_text(encoding="utf-8")
                        + "\n    private struct Body: View {}\n", encoding="utf-8")
        if not any("named `Body`" in problem for problem in check_nested_body(scratch)):
            failures.append("it did not fire on a nested `struct Body`")

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
    print("selftest: fires on all FIVE defects (member, call label, static name, nested `Body`, chrome on a styled Button), stays silent on the real tree.")
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
        problems = (check(TVOS) + check_calls(TVOS) + check_namespaces(TVOS)
                    + check_nested_body(TVOS) + check_style_ownership(TVOS))
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
    print("⚠ Not covered: TYPES (a value of the wrong type still needs the compiler), argument ORDER, and")
    print("  behaviour. FIVE rules, every one bought by a defect that reached his Mac:")
    print("  1 a member a view names that its model lacks;  2 a call using a label its type does not take;")
    print("  3 a static-namespace name (HomeRules.*, TVTokens.* …) declared nowhere;  4 a nested `struct Body`")
    print("  (a `Style` protocol owns that name);  5 chrome applied to a `Button` whose style already draws it.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
