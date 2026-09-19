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
    # Phase B2 — the Home's rules and its state table. Pure `Foundation` + each other, which is why they can
    # be executed here: `HomeStore` and `LibraryAPI` are NOT in this list (they import `RKMServerKit`), and
    # that is the split the phase is built on — every DECISION is runnable, only I/O is not.
    TVOS / "Core" / "HomeRails.swift",
    # Phase B3 — Browse's rules: the library list, the wall's mounting plan. Same split, same reason.
    TVOS / "Core" / "BrowseRules.swift",
    # Phase B4 — the detail screen: its payload models, its rules, and the one transport rule that fails
    # silently. ⚠ `APIClient` is deliberately NOT here (it imports `RKMServerKit`) — which is exactly why
    # `RequestURL.swift` exists as its own `Foundation`-only file: a query escaped into the PATH turns a
    # working request into a 404, and that is a rule worth executing rather than trusting.
    TVOS / "Core" / "Models" / "DetailModels.swift",
    TVOS / "Core" / "DetailRules.swift",
    TVOS / "Core" / "RequestURL.swift",
    # Phase U2 — the Profile Switcher's rules, and the wire model they read. ⚠ `AuthModels.swift` joins the
    # list WITH them: `ProfileRules` takes a `ProfileUser`, and a rule about a shape is only worth running
    # against the shape the wire actually produces. `SessionStore` and `ProfilesView` are NOT here (the first
    # imports `RKMServerKit`, the second is SwiftUI) — so `subtitle`, `initials`, the eyebrow and the
    # administrator check are the parts of that screen a machine can check.
    TVOS / "Core" / "Models" / "AuthModels.swift",
    TVOS / "Core" / "ProfileRules.swift",
]

HARNESS = REPO / "apple" / "scripts" / "tvos-core-tests" / "main.swift"

#: Every rule the harness pins, as `(label, file, old, new, check-it-protects)`. ⚠ The last element must
#: be text that appears in the FAILING line the harness prints, or a mutation that goes red for an
#: unrelated reason would count as a pass.
MUTATIONS = [
    # ---- the poster URL
    ("the width clamp", "PosterURL.swift",
     "min(max(width, route.widthRange.lowerBound), route.widthRange.upperBound)",
     "width",
     "an out-of-range width is clamped"),
    ("the empty-id refusal", "PosterURL.swift",
     "guard !itemID.isEmpty else { return nil }",
     "guard true else { return nil }",
     "an empty id builds no URL at all"),
    ("the query staying out of the path", "PosterURL.swift",
     "        components.path = root + route.path",
     "        components.path = components.path + route.path",
     "one slash between the base and the path"),
    # ---- U3: the backdrop route, which is the SAME builder with the other route word and the other limits.
    # ⚠ The route word is a CONTRACT PATH sitting in a string literal (`Route`'s raw value), so R4 in
    # `check-tvos-models.py` checks both routes character for character. This mutation proves the harness
    # notices when that word is wrong.
    ("the backdrop route word", "PosterURL.swift",
     '        case backdrop = "api/jellyfin/backdrop"',
     '        case backdrop = "api/jellyfin/poster"',
     "a backdrop URL is the backdrop route"),
    ("the backdrop's own width ceiling", "PosterURL.swift",
     "        var widthRange: ClosedRange<Int> { self == .poster ? 16...2000 : 16...4000 }",
     "        var widthRange: ClosedRange<Int> { 16...2000 }",
     "a backdrop width above its own ceiling is lowered to it"),
    ("the backdrop's default width", "PosterURL.swift",
     "        var defaultWidth: Int { self == .poster ? 500 : 1600 }",
     "        var defaultWidth: Int { 500 }",
     "a backdrop path defaults to 1600 wide"),
    # ---- the item shape
    ("the identity key", "LibraryModels.swift",
     'case itemID = "item_id"', 'case itemID = "id"',
     "item_id is the identity key, not id"),
    ("the optional thumb", "LibraryModels.swift",
     "let thumb: String?", "let thumb: String",
     "a missing thumb does not fail the decode"),
    # ⚠ `playbackPosition` and `year` are deliberately NOT the target here: this code unwraps both (`??`,
    # `map`) and makes them load-bearing, so removing their optionality is not valid Swift and the mutation
    # cannot compile. A mutation that cannot compile proves nothing, so it must not be listed as if it did.
    # `genres` is declared and never unwrapped, so it is a clean test of the rule that an optional key must
    # tolerate absence.
    ("an optional key made required", "LibraryModels.swift",
     "let genres: [String]?", "let genres: [String]",
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
    # ---- B2: the Home's rules and its state table
    ("the continue-watching rule", "HomeRails.swift",
     "item.isResumable", "true",
     "only in-progress or played rows WITH an id are Continue Watching"),
    ("the Recently Played cap", "HomeRails.swift",
     "prefix(HomeRailLimit.recentlyPlayed)", "prefix(HomeRailLimit.recentlyAdded)",
     "the Recently Played rail caps at 14"),
    ("the Recently Added id filter", "HomeRails.swift",
     "Array((items ?? []).filter { !$0.itemID.isEmpty }.prefix(HomeRailLimit.recentlyAdded))",
     "Array((items ?? []).prefix(HomeRailLimit.recentlyAdded))",
     "the Recently Added rail drops a row with no id"),
    ("the empty-vs-failed order", "HomeRails.swift",
     "        if rails.isEmpty && hasAnyFailure { return (Self.allFailedTitle, Self.allFailedSub) }",
     "        if allFailed { return (Self.allFailedTitle, Self.allFailedSub) }",
     "with nothing to show, a failed row takes the screen rather than claiming the library is empty"),
    ("the Recently Played heading", "HomeRails.swift",
     'static let recentlyPlayedTitle = "Recently Played"',
     'static let recentlyPlayedTitle = "Recently played"',
     "the Recently Played rail has the web app's own heading"),
    ("the meta line's separator", "HomeRails.swift",
     '        .joined(separator: " · ")', '        .joined(separator: ", ")',
     "a film reads year · runtime"),
    ("the runtime floor", "HomeRails.swift",
     'return "\\(max(1, minutes))m"', 'return "\\(minutes)m"',
     "a runtime under a minute still reads 1m, never 0m"),
    ("the transport sentence", "HomeRails.swift",
     'return "Couldn\'t reach the server."', 'return "Error."',
     "a transport failure says the server was not reached"),
    # ---- B3: Browse's rules
    ("an unresolved library kept", "BrowseRules.swift",
     "        (libraries ?? []).map { lib in", "        (libraries ?? []).filter { $0.ok }.map { lib in",
     "an unresolved library is NOT openable"),
    ("the openable gate", "BrowseRules.swift",
     "let folderID = resolved ? lib.folderID : nil", "let folderID = lib.folderID",
     "…and has no folder to open"),
    ("the movies icon", "BrowseRules.swift",
     'case "movies": return .film', 'case "movies": return .folder',
     "a `movies` library gets the film icon"),
    ("the count label plural", "BrowseRules.swift",
     '"\\(count) title\\(count == 1 ? "" : "s")"', '"\\(count) title"',
     "one title is singular"),
    ("the first-paint cap", "BrowseRules.swift",
     "static let firstPaint = 48", "static let firstPaint = 500",
     "a big wall mounts the first paint only"),
    ("the wall's id filter", "BrowseRules.swift",
     "(items ?? []).filter { !$0.itemID.isEmpty }", "(items ?? [])",
     "a wall drops a row with no id"),
    ("the server-folders fallback", "BrowseRules.swift",
     "if !configured.isEmpty { return configured }", "if false { return configured }",
     "configured libraries win when there are any"),
    # ---- B4: the request URL. ⚠ THE TRAP THIS RULE EXISTS FOR is a query that becomes part of the PATH,
    # which turns a working request into a 404 that wears the app's own "we couldn't find that title" copy.
    ("the query is carried as a query", "RequestURL.swift",
     "        components.queryItems = query", "        components.queryItems = []",
     "a parameterised request puts the parameter in the QUERY"),
    ("one slash after a trailing-slash address", "RequestURL.swift",
     '        let root = components.path.hasSuffix("/") ? String(components.path.dropLast()) : components.path',
     "        let root = components.path",
     "an address ending in a slash does not double the slash"),
    # ---- B4: the detail screen's rules, each mirrored from the web app.
    ("the .0 stripped from a whole rating", "DetailRules.swift",
     '        return oneDecimal.hasSuffix(".0") ? String(oneDecimal.dropLast(2)) : oneDecimal',
     "        return oneDecimal",
     "a whole rating drops the .0"),
    ("a finished title showing a resume bar", "DetailRules.swift",
     "        guard let play, !play.played else { return 0 }",
     "        guard let play else { return 0 }",
     "a finished title shows no resume bar"),
    ("in-progress ignoring the played flag", "DetailRules.swift",
     "        return !play.played && play.resume > 0",
     "        return play.resume > 0",
     "a finished title is NOT in progress, even with a position on it"),
    ("a series reading its runtime instead of its seasons", "DetailRules.swift",
     "            isSeries(detail) ? seasonsText(seasonCount) : HomeRules.runtimeText(detail.runtime),",
     "            HomeRules.runtimeText(detail.runtime),",
     "a series reads its season count, not its runtime"),
    ("the season count plural", "DetailRules.swift",
     '        count > 0 ? "\\(count) season\\(count > 1 ? "s" : "")" : ""',
     '        count > 0 ? "\\(count) seasons" : ""',
     "one season is singular"),
    ("the minute floor on time left", "DetailRules.swift",
     '            ? "\\(HomeRules.runtimeText(max(1, runtime - position))) left"',
     '            ? "\\(HomeRules.runtimeText(runtime - position)) left"',
     "…and still reads 1m left"),
    ("a countdown against an unknown runtime", "DetailRules.swift",
     "        let remainingLabel = (inProgress && runtime > 0)",
     "        let remainingLabel = (inProgress)",
     "…and no countdown"),
    ("the next episode ignoring what is in progress", "DetailRules.swift",
     "        return ordered.first { !$0.played && $0.playbackPosition > 0 }",
     "        return ordered.first { !$0.played }",
     "a series mid-episode resumes THAT episode"),
    ("the seasons left unsorted", "DetailRules.swift",
     "        return seasonOrder.sorted().map { season in",
     "        return seasonOrder.map { season in",
     "seasons are ascending however the list arrives"),
    # ⚠⚠ THE PORTING HAZARD ITSELF: a Swift dictionary has no order, so the obvious translation of the web's
    # `Map` shuffles the episodes inside every season. This mutation is what says the long way round is
    # load-bearing rather than fussy.
    ("the episodes inside a season re-ordered", "DetailRules.swift",
     "        for episode in episodes {",
     "        for episode in episodes.reversed() {",
     "…and the episodes INSIDE a season keep the server's order"),
    ("the series verb losing Resume", "DetailRules.swift",
     '            return "\\(target.playbackPosition > 0 ? "Resume" : "Play") \\(episodeCode(target))"',
     '            return "Play \\(episodeCode(target))"',
     "a half-watched series resumes that episode by name"),
    ("the fully-watched series losing its Replay", "DetailRules.swift",
     '        return first.map { "Replay \\(episodeCode($0))" } ?? "Play"',
     '        return first.map { "Play \\(episodeCode($0))" } ?? "Play"',
     "a finished series offers a replay of the first episode"),
    ("the episode code swapped", "DetailRules.swift",
     '        "S\\(season)E\\(episode)"',
     '        "E\\(episode)S\\(season)"',
     "an episode's code is S<season>E<number>"),
    ("the credits noun plural", "DetailRules.swift",
     '        return "\(noun)\(names.count > 1 ? "s" : ""): \(names.joined(separator: ", "))"',
     '        return "\(noun): \(names.joined(separator: ", "))"',
     "two directors are Directors"),
    ("the cast rail uncapped", "DetailRules.swift",
     "        Array((people?.actors ?? []).filter { !$0.name.isEmpty }.prefix(Cast.limit))",
     "        Array((people?.actors ?? []).filter { !$0.name.isEmpty })",
     "the cast rail is capped at ten"),
    ("a partial warning on a film", "DetailRules.swift",
     "    var partialWarning: String? { episodesFailed && isSeries ? DetailCopy.partialWarning : nil }",
     "    var partialWarning: String? { episodesFailed ? DetailCopy.partialWarning : nil }",
     "a film with a failed episode list still shows no episode warning"),
    ("an episode section keyed off the count", "DetailRules.swift",
     "    var showsEpisodes: Bool { isSeries }",
     "    var showsEpisodes: Bool { !episodes.isEmpty }",
     "a failed episode list still draws the section"),
    ("the placeholder losing the next verb", "DetailRules.swift",
     '    static func nextUp(_ verb: String) -> String { "Next up: \\(verb)" }',
     '    static func nextUp(_ verb: String) -> String { "\\(verb)" }',
     "the screen names the verb it WILL offer, in the phone's own words"),
    # ---- U2: the Profile Switcher's rules
    ("the avatar's second letter", "ProfileRules.swift",
     "            letters = String(first.prefix(2))", "            letters = String(first.prefix(1))",
     "meenu reads ME"),
    ("the second initial of a two-word name", "ProfileRules.swift",
     "            letters = String(first.prefix(1)) + String(words[1].prefix(1))",
     "            letters = String(first.prefix(2))",
     "a two-word name reads its two initials"),
    ("a disabled profile still offering to be selected", "ProfileRules.swift",
     '        if profile.disabled { return "Disabled — cannot be selected" }',
     '        if false { return "Disabled — cannot be selected" }',
     "a disabled administrator says it cannot be selected"),
    # ⚠⚠ THE MUTATION THAT GUARDS HIS DECISION: the buildspec's own vocabulary, which §1a records as NOT
    # adopted because it cannot express the disabled case at all.
    ("the buildspec's vocabulary for a locked profile", "ProfileRules.swift",
     '        if profile.hasPassword { return "Password protected" }',
     '        if profile.hasPassword { return "Profile · password" }',
     "a locked profile says Password protected"),
    ("the administrator no longer saying what it asks for", "ProfileRules.swift",
     '        if profile.isAdmin { return "Administrator — asks for a password" }',
     '        if profile.isAdmin { return "Administrator" }',
     "the administrator says what it will ask for"),
    ("a screen reader losing the lock", "ProfileRules.swift",
     '            parts.append("password protected")', '            parts.append("locked")',
     "a locked tile reads its lock to a screen reader"),
    ("the eyebrow's plural", "ProfileRules.swift",
     'let head = "\\(count) profile\\(count == 1 ? "" : "s") on this server"',
     'let head = "\\(count) profiles on this server"',
     "one profile is singular"),
    ("a dangling separator on the eyebrow", "ProfileRules.swift",
     "        return name.isEmpty ? head : \"\\(head) · Signed in as \\(name)\"",
     "        return \"\\(head) · Signed in as \\(name)\"",
     "with no account name there is no dangling separator"),
    # ⚠⚠ MATCHED BY ID, NOT BY NAME — the trap the fixture is shaped for.
    ("the administrator matched by name", "ProfileRules.swift",
     "        return profiles.first { $0.id == signedInUserID }?.isAdmin ?? false",
     "        return profiles.first { $0.name == signedInUserID }?.isAdmin ?? false",
     "a member is not the administrator, whatever they are called"),
    # ---- U3: the hero's pick, its copy, and the top bar's tabs
    ("a film no longer preferred for the hero", "HomeRails.swift",
     "        if let movie = resume.first(where: { !isSeries($0) && !isEpisodeItem($0) }) { return movie }",
     "        if let movie = resume.first(where: { true }) { return movie }",
     "an in-progress MOVIE takes the hero before an episode"),
    ("a finished title taking the hero", "HomeRails.swift",
     "            !$0.itemID.isEmpty && !($0.played ?? false) && ($0.playbackPosition ?? 0) > 0",
     "            !$0.itemID.isEmpty && ($0.playbackPosition ?? 0) > 0",
     "a finished title never takes the hero"),
    ("the recently-added tier losing its id filter", "HomeRails.swift",
     "        if let added = (recentlyAdded ?? []).first(where: { !$0.itemID.isEmpty }) { return added }",
     "        if let added = (recentlyAdded ?? []).first(where: { $0.itemID.isEmpty }) { return added }",
     "the most recently added title takes the hero when nothing is in progress"),
    ("the whole-library tier losing its film preference", "HomeRails.swift",
     "        return (all ?? []).first { !isSeries($0) } ?? (all ?? []).first",
     "        return (all ?? []).first",
     "the whole-library fallback prefers a film"),
    ("an id-less hero removing a row", "HomeRails.swift",
     "        guard let hero, !hero.itemID.isEmpty else { return items ?? [] }",
     "        guard let hero else { return items ?? [] }",
     "a hero with no id removes nothing — never the first row with an empty id"),
    ("the hero eyebrow always Continue Watching", "HomeRails.swift",
     '        if !continueWatching { return "Recently Added" }',
     '        if false { return "Recently Added" }',
     "a hero that is not continue watching says Recently Added"),
    ("a series offering to play", "HomeRails.swift",
     '        if isSeries { return "Explore Episodes" }', '        if isSeries { return "Play" }',
     "a series is explored, never played"),
    ("an episode's hero verb losing its code", "HomeRails.swift",
     '            return episodeCode.isEmpty ? verb : "\\(verb) \\(episodeCode)"',
     "            return verb",
     "a half-watched episode names the episode it resumes"),
    ("an episode's hero titled with the episode", "HomeRails.swift",
     "        if isEpisodeItem(item), let series = item.episode?.seriesName, !series.isEmpty { return series }",
     "        if isEpisodeItem(item), let series = item.episode?.seriesName, series.isEmpty { return series }",
     "an episode's hero is titled with its series"),
    ("the hero's meta line losing its episode space", "HomeRails.swift",
     '            parts.append("S\\(episode.season) E\\(episode.number)")',
     '            parts.append("S\\(episode.season)E\\(episode.number)")',
     "an episode's hero meta carries its code, spaced"),
    ("the hero's meta line keeping every genre", "HomeRails.swift",
     "        parts.append(contentsOf: (item.genres ?? []).prefix(2))",
     "        parts.append(contentsOf: (item.genres ?? []))",
     "the hero's meta keeps only two genres"),
    ("the hero's percentage truncated", "HomeRails.swift",
     "        return min(100, Int((Double(position) / Double(runtime) * 100).rounded()))",
     "        return min(100, Int((Double(position) / Double(runtime) * 100)))",
     "the hero's percentage is rounded (620 of 7200 is 9%)"),
    ("a countdown on a finished film", "HomeRails.swift",
     "              position > 0, runtime > position else { return \"\" }",
     "              position > 0 else { return \"\" }",
     "a finished film has no countdown"),
    ("a countdown on a series", "HomeRails.swift",
     "        guard !isSeries(item), !isEpisodeItem(item) else { return \"\" }",
     "        guard !isSeries(item) else { return \"\" }",
     "a series measures episodes, not minutes"),
    ("a failed tab row going unnamed", "HomeRails.swift",
     "        if nav.failedMessage != nil { out.append(Self.tabsLabel) }",
     "        if false { out.append(Self.tabsLabel) }",
     "a failed tab row is named in the footer, beside the rail that failed"),
    ("an id-less hero claimed as Continue Watching", "HomeRails.swift",
     "        guard let hero, !hero.itemID.isEmpty else { return false }",
     "        guard let hero else { return false }",
     "…and is never claimed to have come from Continue Watching (the empty-id sentinel)"),
    ("a series drawn with the film glyph", "HomeRails.swift",
     "        isSeries(item) ? .tv : .film", "        .film",
     "a series gets the tv glyph"),

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
