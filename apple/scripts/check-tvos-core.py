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
    # Phase C1 — the credential `AVPlayer` cannot get from `URLSession`. Same split again: the SELECTION and
    # the refusal are pure and run here; the AVFoundation key it is built under is supplied by the Mac-only
    # call site (see the file), and the platform behaviour itself is the round's falsifier, not this gate's
    # claim.
    TVOS / "Core" / "PlaybackAuth.swift",
    # Phase U2 — the Profile Switcher's rules, and the wire model they read. ⚠ `AuthModels.swift` joins the
    # list WITH them: `ProfileRules` takes a `ProfileUser`, and a rule about a shape is only worth running
    # against the shape the wire actually produces. `SessionStore` and `ProfilesView` are NOT here (the first
    # imports `RKMServerKit`, the second is SwiftUI) — so `subtitle`, `initials`, the eyebrow and the
    # administrator check are the parts of that screen a machine can check.
    # ⚠ Both design tables came in together (U7): `TVTokens` NAMES `RGBAColor`, which the generated
    # `DesignTokens.swift` declares, so one cannot be compiled without the other. They are Foundation-only
    # on purpose (the SwiftUI bridge is `Design/DesignColours.swift`), which is what lets the profile row's
    # fit be a RUNNABLE check rather than a comment.
    TVOS / "Design" / "DesignTokens.swift",
    TVOS / "Design" / "TVTokens.swift",
    TVOS / "Core" / "Models" / "AuthModels.swift",
    TVOS / "Core" / "ProfileRules.swift",
    # Phase V — the LIBRARY GRID's rules: the genre chips (derived from the rows), the filter and the web
    # app's eight sorts. ⚠ It joins this list because the sorts are where a port goes SILENTLY wrong — every
    # comparator has a tie-break that falls back to `cmpRecentDesc`, two of them have a leading rule
    # (`release`'s unknown-years-last, `progress`'s played-scores-zero), and Swift's `sorted(by:)` is not
    # documented as stable where JavaScript's is. None of that is visible on a television.
    TVOS / "Core" / "LibraryRules.swift",
    # Phase C2 — THE PLAYER'S RULES. ⚠⚠ This is the phase where "runnable here" matters most: the screen
    # itself is SwiftUI + AVFoundation (Mac-only, one round), so every DECISION the player makes was pushed
    # into these files and is EXECUTED below. `PlaybackURLs.swift` exists for the trap that has no log line at
    # all — the URL `AVPlayer` fetches ITSELF, where a wrong build is a black screen and nothing else.
    # `PlaybackModels.swift` joins them because `PlaybackRules` reads real `PlaybackTrack`s, and a rule about
    # a shape is worth running against the shape the wire produces.
    TVOS / "Core" / "PlaybackRules.swift",
    TVOS / "Core" / "PlaybackURLs.swift",
    TVOS / "Core" / "Models" / "PlaybackModels.swift",
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
    # notices when that word is wrong. ⚠ It must NOT be changed to another EXISTING raw value: two enum cases
    # with the same raw value do not compile, and an uncompilable mutation proves nothing (`ERROR`, not red).
    ("the backdrop route word", "PosterURL.swift",
     '        case backdrop = "api/jellyfin/backdrop"',
     '        case backdrop = "api/jellyfin/backdropX"',
     "a backdrop URL is the backdrop route"),
    ("the backdrop's own width ceiling", "PosterURL.swift",
     "        var widthRange: ClosedRange<Int> { self == .poster ? 16...2000 : 16...4000 }",
     "        var widthRange: ClosedRange<Int> { 16...2000 }",
     "a backdrop width above its own ceiling is lowered to it"),
    ("the backdrop's default width", "PosterURL.swift",
     "        var defaultWidth: Int { self == .poster ? 500 : 1600 }",
     "        var defaultWidth: Int { 500 }",
     # ⚠ The expected string must be the FIRST check this mutation turns red, not merely A check it turns red:
     # a default width of 500 makes the backdrop's own path wrong before the clamp check is ever reached, and
     # the runner counts a red on the wrong line as a survivor.
     "a backdrop path is the backdrop route at the backdrop width"),
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
    # ⚠⚠ REPAIRED IN PHASE V (2026-09-20): this mutation had gone STALE — the line it reverted had been
    # rewritten (`return parts.joined(…)` instead of a bare `.joined(…)`), and the check it NAMED
    # ("a film reads year · runtime") belongs to `DetailRules.metaBits`, which returns an ARRAY and was never
    # reachable from this line. Both halves are now the real ones: the line as it actually reads, in
    # `HomeRules.heroMetaLine`, and the check that actually exercises it.
    ("the hero's meta separator", "HomeRails.swift",
     '        return parts.joined(separator: " · ")', '        return parts.joined(separator: ", ")',
     "the hero's meta reads year and genres"),
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
    # ---- C1: the playback credential
    ("the session cookie's name", "PlaybackAuth.swift",
     'static let sessionCookieName = "rkm_session"',
     'static let sessionCookieName = "rkm"',
     "the cookie the player looks for is the api's own session cookie"),
    ("the cookie name check", "PlaybackAuth.swift",
     '        guard cookie.name == sessionCookieName else { return false }',
     '        guard true else { return false }',
     "the session cookie is picked by NAME out of a jar full of others"),
    ("the host check inside applies", "PlaybackAuth.swift",
     '        guard domainCovers(cookie.domain, host: host) else { return false }',
     '        guard true else { return false }',
     "a correctly-named session cookie for ANOTHER host is not used"),
    ("the expiry check", "PlaybackAuth.swift",
     '        if let expires = cookie.expiresDate, expires <= Date() { return false }',
     '        if false { return false }',
     "an EXPIRED session cookie is not used"),
    ("the path scope inside applies", "PlaybackAuth.swift",
     '        return pathCovers(cookie.path, requestPath: requestPath)',
     '        return true',
     "a cookie scoped to a path this app does not use is refused"),
    ("the subdomain suffix test", "PlaybackAuth.swift",
     '        return host.hasSuffix("." + domain)',
     '        return host.hasSuffix(domain)',
     "a domain cookie does not match a host that merely ends the same way"),
    ("the path prefix test", "PlaybackAuth.swift",
     '        return requestPath.hasPrefix(base.hasSuffix("/") ? base : base + "/")',
     '        return requestPath.hasPrefix(base)',
     "…but NOT a path that merely starts the same way"),
    ("the no-substitute rule", "PlaybackAuth.swift",
     '        cookies.first { applies($0, to: origin) }',
     '        cookies.first',
     "an unrelated cookie is NEVER substituted for the session"),
    ("the empty option key", "PlaybackAuth.swift",
     '        guard !cookieKey.isEmpty else { return nil }',
     '        guard true else { return nil }',
     "an empty option key builds NO options rather than a bogus one"),
    ("the withheld cookie value", "PlaybackAuth.swift",
     '        return "session cookie for \\(cookie.domain)\\(cookie.path) (value withheld)"',
     '        return "session cookie \\(cookie.value)"',
     "the loggable description never carries the credential"),
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
     # ⚠ `{ _ in true }` and not `{ true }`: a closure body with no parameters does not satisfy
     # `(MediaItem) -> Bool`, so the mutation would not compile — and an uncompilable mutation is an ERROR,
     # never a red (the rule this repo already paid for on Phase B's `playbackPosition`).
     "        if let movie = resume.first(where: { _ in true }) { return movie }",
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
    # ⚠⚠ REPAIRED IN PHASE V (2026-09-20) — STALE, and BOTH halves of it. The line had been rewritten
    # (`position > 0, runtime > position`), so there was nothing left to revert; and the check it named
    # ("an unstarted film has no countdown") is not a label any check carries. Repointed at the clause that
    # actually changes an answer — `position > 0`, i.e. an unstarted title — and at the check that asks for it.
    ("an unstarted film's countdown", "HomeRails.swift",
     "              position > 0, runtime > position else { return \"\" }",
     "              position >= 0, runtime > position else { return \"\" }",
     "an unstarted title has nothing left to lose"),
    # ⚠⚠ REPAIRED IN PHASE V (2026-09-20) — STALE for the same reason: the guard lost its episode clause
    # (episodes DO get a countdown on the card, deliberately), so the text to revert no longer exists, and the
    # check it named ("a series measures episodes, not minutes") is not a label either. Reverting the guard
    # outright is what pins the rule now.
    ("a countdown on a series", "HomeRails.swift",
     "        guard !isSeries(item) else { return \"\" }",
     "        guard true else { return \"\" }",
     "a SERIES has no countdown"),
    ("a failed tab row going unnamed", "HomeRails.swift",
     "        if nav.failedMessage != nil { out.append(Self.tabsLabel) }",
     "        if false { out.append(Self.tabsLabel) }",
     "a failed tab row is named in the footer, beside the rail that failed"),
    ("an id-less hero claimed as Continue Watching", "HomeRails.swift",
     "        guard let hero, !hero.itemID.isEmpty else { return false }",
     "        guard let hero else { return false }",
     "…and is never claimed to have come from Continue Watching (the empty-id sentinel)"),
    # ---- the profile row's FIT (his screenshot: the `Add profile` tile hanging off the right edge)
    ("the profile row outgrowing the screen", "TVTokens.swift",
     "        static let rowWidthUnits: CGFloat = 5 * 13 + 4 * 2.6",
     "        static let rowWidthUnits: CGFloat = 5 * 15 + 4 * 3.2",
     # ⚠ REPAIRED IN PHASE V (2026-09-20): the check's own label gained its `(6u)` when U7b turned the fit
     # into arithmetic, so the old expectation stopped matching — and the gate reported a mutation that WAS
     # red as "WRONG … went red, but not on …", which reads as a survivor. The expectation is now a prefix of
     # the real label, and it is deliberately the SHORT prefix: it survives the label gaining a clause again.
     "the profile row fits the screen with a whole margin"),

    # ---- U6's premium card: the facts line, the countdown and the state chip
    ("the card losing its duration", "HomeRails.swift",
     "        if !isSeries(item) {\n            let duration = runtimeText(item.runtime)",
     "        if false {\n            let duration = runtimeText(item.runtime)",
     "a film leads with its duration, then the year and a genre"),
    ("a series printing a runtime on the card", "HomeRails.swift",
     "        if !isSeries(item) {\n            let duration = runtimeText(item.runtime)",
     "        if true {\n            let duration = runtimeText(item.runtime)",
     "a SERIES never prints a runtime"),
    ("how long is left losing its series refusal", "HomeRails.swift",
     '        guard !isSeries(item) else { return "" }',
     '        guard true else { return "" }',
     "a SERIES has no countdown"),
    ("the state chip losing its \"left\"", "HomeRails.swift",
     '        if !left.isEmpty { return "\(left) left" }',
     '        if !left.isEmpty { return left }',
     "a half-watched film says how much is left"),
    ("a watched title not saying so", "HomeRails.swift",
     '        if item.played ?? false { return "Watched" }',
     '        if item.played ?? false { return "" }',
     "a title marked watched says so"),
    ("a part-watched series claiming to be watched", "HomeRails.swift",
     '        if let fraction = item.progressFraction, fraction < 1 { return "" }',
     '        if let fraction = item.progressFraction, fraction < 0 { return "" }',
     "a part-watched SERIES Jellyfin also marks played gets no chip either"),

    # ---- U6: the card's badge
    ("the badge losing the episode code", "HomeRails.swift",
     "        if let code = episodeItemCode(item) { return code }",
     '        if let code = episodeItemCode(item) { return "EPISODE" }',
     "an episode's badge is the app's own S1E3 code"),
    ("every badge saying MOVIE", "HomeRails.swift",
     '        return isSeries(item) ? "SERIES" : "MOVIE"',
     '        return "MOVIE"',
     "a series with no episode badge says SERIES"),
    ("a series drawn with the film glyph", "HomeRails.swift",
     "        isSeries(item) ? .tv : .film", "        .film",
     "a series gets the tv glyph"),
    # ---- U4: the third rail
    ("the third rail dropped", "HomeRails.swift",
     "        let added = HomeRules.recentlyAddedItems(libraryRecent.items)\n        if !added.isEmpty {",
     "        let added = HomeRules.recentlyAddedItems(libraryRecent.items)\n        if false {",
     "Recently Added is the THIRD rail"),
    ("the Recently Added heading lowercased", "HomeRails.swift",
     '    static let recentlyAddedTitle = "Recently Added"',
     '    static let recentlyAddedTitle = "Recently added"',
     "the third rail has the web app's own heading"),
    ("a failed Recently Added row going unnamed", "HomeRails.swift",
     "        if libraryRecent.failedMessage != nil { out.append(Self.recentlyAddedTitle) }",
     "        if false { out.append(Self.recentlyAddedTitle) }",
     "a failed Recently Added fetch is named in the footer"),

    # ---- V: the library grid's rules. ⚠ Every one of these is a PORT of `frontend/src/features/library/lib.ts`,
    # which is where a silent difference would live: the same wall, sorted differently on the TV than on the
    # phone, with nothing on screen to say so.
    ("the genre list's order", "LibraryRules.swift",
     "        return seen.sorted()",
     "        return Array(seen.sorted().reversed())",
     "genres are unique and code-unit sorted"),
    ("an empty genre name kept", "LibraryRules.swift",
     "            for genre in item.genres ?? [] where !genre.isEmpty {",
     "            for genre in item.genres ?? [] {",
     "an empty genre name is dropped"),
    ("the All chip losing its meaning", "LibraryRules.swift",
     '        return chip == allChipTitle ? current.isEmpty : chip == current',
     "        return chip == current",
     "All is selected when nothing is filtered"),
    ("All filtering by the word All", "LibraryRules.swift",
     '        chip == allChipTitle ? "" : chip',
     "        chip",
     "All clears the filter rather than filtering by the word 'All'"),
    ("the count line becoming the prototype's demo sentence", "LibraryRules.swift",
     "        guard !wanted.isEmpty else { return BrowseRules.folderCountLabel(total) }",
     '        guard !wanted.isEmpty else { return "\\(shown) of \\(total) titles" }',
     "unfiltered count is the web's own line, not '140 of 140'"),
    ("a filtered count losing its plural rule", "LibraryRules.swift",
     '        return "\\(shown) title\\(shown == 1 ? "" : "s") in \\(wanted)"',
     '        return "\\(shown) titles in \\(wanted)"',
     "a filtered count of one is singular"),
    # ⚠⚠ THE U7b SHAPE, ON THE NEW SCREEN: one margin subtracted instead of two. It is the defect that put the
    # `Add profile` tile off the edge of his screenshot, and on a 6-column grid it is a card that overflows the
    # screen instead of a tile that hangs off it.
    ("the grid's second margin", "LibraryRules.swift",
     "        let usable = containerWidth - 2 * margin - CGFloat(columns - 1) * columnGap",
     "        let usable = containerWidth - margin - CGFloat(columns - 1) * columnGap",
     "six cards, five gaps and two margins are exactly the screen"),
    ("the fraction trimmed to the wrong length", "LibraryRules.swift",
     "        let keep = iso.index(iso.startIndex, offsetBy: iso.distance(from: iso.startIndex, to: dot) + 4)",
     "        let keep = iso.index(iso.startIndex, offsetBy: iso.distance(from: iso.startIndex, to: dot) + 3)",
     "seven fraction digits are trimmed to three"),
    ("the undated row sorting FIRST", "LibraryRules.swift",
     "        case (.some, nil): return -1\n        case (nil, .some): return 1",
     "        case (.some, nil): return 1\n        case (nil, .some): return -1",
     "recent is newest first and puts the undated row last"),
    ("a finished title scoring its position", "LibraryRules.swift",
     "        guard !(item.played ?? false), let runtime = item.runtime, runtime > 0 else { return 0 }",
     "        guard let runtime = item.runtime, runtime > 0 else { return 0 }",
     "a finished title scores zero, so it is not the most-watched thing in the library"),
    ("recently-played ignoring the played flag", "LibraryRules.swift",
     "        let pa = (a.played ?? false) ? parseISO(a.lastPlayed ?? \"\") : nil",
     "        let pa = parseISO(a.lastPlayed ?? \"\")",
     "recently played leads with a played row that has a date, and never-played comes last"),
    # ⚠⚠ STABILITY — the tie-break that JavaScript gives for free and Swift does not.
    ("the sort losing its stability", "LibraryRules.swift",
     "            return left.offset < right.offset",
     "            return left.element.itemID > right.element.itemID",
     "two undated rows keep the server's order"),
    ("the card caption's runtime", "LibraryRules.swift",
     '        [item.year.map(String.init) ?? "", HomeRules.runtimeText(item.runtime)]',
     '        [item.year.map(String.init) ?? "", "\\(item.runtime ?? 0)s"]',
     "the caption is year · runtime, through the app's ONE runtime formatter"),
    ("the Browse fallback not current", "BrowseRules.swift",
     "                                       isCurrent: current == .browse, isEnabled: true, warning: \"\"))",
     "                                       isCurrent: false, isEnabled: true, warning: \"\"))",
     "…and it is current on the Browse screen"),
    ("an unresolved library losing its row's state", "BrowseRules.swift",
     "                                  isCurrent: isCurrent, isEnabled: entry.isOpenable, warning: entry.warning)",
     "                                  isCurrent: isCurrent, isEnabled: true, warning: \"\")",
     "an unresolved library keeps its tab and cannot be selected"),
    ("the cast colour keyed on the wrong field", "DetailRules.swift",
     "        let key = person.id.isEmpty ? person.name : person.id",
     "        let key = person.name",
     "one person id is one colour, whatever else the row says"),    # ⚠⚠ ---- PHASE C2: THE PLAYER'S RULES. Every one of these reverts a decision the SCREEN would have made
    # invisibly: a mode chosen for the wrong client, a URL that turns a query into a path, a subtitle that
    # silently does not apply. What is NOT here: the SwiftUI itself, which no gate on this machine can compile.
    ("the clock rounding instead of flooring", "PlaybackRules.swift",
     '        let seconds = Int(max(0, raw).rounded(.down))',
     '        let seconds = Int(max(0, raw).rounded())',
     "a fractional second is floored, never rounded up"),
    ("the tick rate", "PlaybackRules.swift",
     '    static let ticksPerSecond: Double = 10_000_000',
     '    static let ticksPerSecond: Double = 1_000_000',
     "one second is 10,000,000 Jellyfin ticks"),
    ("clamping a seek to the end", "PlaybackRules.swift",
     '        if total > 0 { return min(max(0, target), total) }',
     '        if total > 0 { return max(0, target) }',
     "a seek past the end clamps to the end"),
    ("clamping a seek with no known total", "PlaybackRules.swift",
     '        return max(0, target)',
     '        return 0',
     "an unknown total steps forward instead of pinning to 0"),
    ("the bar total with no duration yet", "PlaybackRules.swift",
     '        if isFiniteDuration(streamDuration) { return streamDuration ?? 0 }',
     '        if false { return streamDuration ?? 0 }',
     "the stream's own duration wins once it is known"),
    ("dividing by an unknown total", "PlaybackRules.swift",
     '        guard total > 0 else { return 0 }\n        return min(max(0, position / total), 1)',
     '        guard total > 0 else { return 1 }\n        return min(max(0, position / total), 1)',
     "an unknown total divides by nothing and draws an empty bar"),
    ("the skip rule", "PlaybackRules.swift",
     '        clampSeek(position + delta, total: total)',
     '        clampSeek(position, total: total)',
     "Back 10s at 3s lands at 0, not at a negative time"),
    ("the quality forcing a transcode", "PlaybackRules.swift",
     '        if quality != defaultQualityLabel { return .transcode }',
     '        if false { return .transcode }',
     "asking for a quality re-encodes — Jellyfin ignores a bitrate cap on a direct play"),
    ("the video codec check", "PlaybackRules.swift",
     '        if !codecValue.isEmpty && !codecs.video.contains(codecValue) { return true }',
     '        if false { return true }',
     "…and a transcode for one that decodes neither"),
    ("the audio codec check", "PlaybackRules.swift",
     '        return !codecs.audio.contains(value)',
     '        return false',
     "EAC3 needs transcoding for a browser"),
    ("the tvOS set losing EAC3", "PlaybackRules.swift",
     '            audio: ["aac", "mp3", "opus", "flac", "alac", "eac3", "ac3", "pcm_s16le", "pcm_s24le"],',
     '            audio: ["aac", "mp3", "opus", "flac", "alac", "ac3", "pcm_s16le", "pcm_s24le"],',
     "an HEVC/EAC3 MKV is a remux for a client that decodes both"),
    ("the mode ladder order", "PlaybackRules.swift",
     '    static let hlsLadder: [StreamMode] = [.remux, .transcodeAudio, .transcode]',
     '    static let hlsLadder: [StreamMode] = [.transcodeAudio, .remux, .transcode]',
     "the escalation order is the web's, and audio-aware"),
    ("the top-bar badge", "PlaybackRules.swift",
     '        case .remux: return "Remux · HLS"',
     '        case .remux: return "Remux (HLS)"',
     "the top-bar badge is his prototype's spelling, not the web's"),
    ("the bitrate the api is asked for", "PlaybackRules.swift",
     '        quality(for: label)?.bitrate ?? 0',
     '        quality(for: label)?.bitrate ?? 1',
     "Original asks for no cap (the api's own 0 = unthrottled)"),
    ("the quality caption", "PlaybackRules.swift",
     '        return "\\(label) · capped at \\(String(format: "%.1f", mbps)) Mbps on a transcode."',
     '        return "\\(label)"',
     "the caption names the bitrate the app will actually ask for"),
    ("the speed label keeping its trailing zero", "PlaybackRules.swift",
     '        while text.hasSuffix("0") { text.removeLast() }',
     '',
     "1× has no decimals"),
    ("the finish fraction", "PlaybackRules.swift",
     '    static let finishFraction: Double = 0.95',
     '    static let finishFraction: Double = 0.5',
     "95% of a runtime counts as finished, exactly as the server decides it"),
    ("finishing with no runtime", "PlaybackRules.swift",
     '        guard runtimeTicks > 0 else { return false }',
     '        guard runtimeTicks > 0 else { return true }',
     "an unknown runtime cannot mark anything finished"),
    ("the report cadence", "PlaybackRules.swift",
     '        elapsedSinceLastReport >= progressReportInterval',
     '        return true',
     "and not more often than that"),
    ("a panel pinning the chrome", "PlaybackRules.swift",
     '        if panelOpen { return false }',
     '        if false { return false }',
     "the settings drawer and the info panel pin the chrome on"),
    ("chrome hiding on a paused film", "PlaybackRules.swift",
     '        if !playing || switching || failed || hoveringChrome { return false }',
     '        if switching || failed || hoveringChrome { return false }',
     "a PAUSED film never hides its controls"),
    ("the language exception table", "PlaybackRules.swift",
     '            return languageExceptions[text] ?? String(text.prefix(2))',
     '            return String(text.prefix(2))',
     "a 639-2/B code maps through the exception table"),
    ("the remembered subtitle TITLE", "PlaybackRules.swift",
     '                $0.name.trimmingCharacters(in: .whitespaces).lowercased() == wanted',
     '                false',
     "the remembered TITLE wins over the language"),
    ("the subtitle language fallback", "PlaybackRules.swift",
     '                return same.index',
     '                return nil',
     "a stale title falls back to the first track in that LANGUAGE"),
    ("the track summary plural", "PlaybackRules.swift",
     '        let subs = "\\(subtitleCount) sub" + (subtitleCount == 1 ? "" : "s")',
     '        let subs = "\\(subtitleCount) sub"',
     "zero subtitles is plural, and is not hidden"),
    ("the meta row for a film with no subtitles", "PlaybackRules.swift",
     '            parts.append("No subtitles")',
     '            parts.append("")',
     "a film with no subtitle tracks says so rather than trailing a dot"),
    ("the drawer's pane kinds", "PlaybackRules.swift",
     '            case .picture, .speed, .quality: return .segmented',
     '            case .picture, .speed, .quality: return .list',
     "quality is a segmented row, not a list"),
    ("the audio track's codec lookup", "PlaybackRules.swift",
     '        guard let index, index > 0 else { return tracks.first?.codec }',
     '        guard let index, index > 0 else { return nil }',
     "no chosen track means the FIRST one — the api's own default"),
    ("a chosen track forcing the mode", "PlaybackRules.swift",
     '    static func choosingATrackForcesNonDirect(audioIndex: Int?) -> Bool { (audioIndex ?? 0) > 0 }',
     '    static func choosingATrackForcesNonDirect(audioIndex: Int?) -> Bool { false }',
     "choosing a track forces a non-direct mode"),
    ("the VTT millisecond scale", "PlaybackRules.swift",
     '        return Double(hours * 3600 + minutes * 60 + seconds) + Double(millis) / 1000',
     '        return Double(hours * 3600 + minutes * 60 + seconds) + Double(millis) / 100',
     "hh:mm:ss.mmm parses to seconds"),
    ("an unparseable VTT timestamp", "PlaybackRules.swift",
     '        guard let separatorIndex else { return 0 }',
     '        guard let separatorIndex else { return -1 }',
     "an unparseable timestamp is 0, not a wild guess"),
    ("dropping an empty cue", "PlaybackRules.swift",
     '            if !clean.isEmpty {',
     '            if true {',
     "tags are stripped, settings ignored, and an EMPTY cue is dropped"),
    ("the cue's end token and its settings", "PlaybackRules.swift",
     '            let endToken = rest.trimmingCharacters(in: .whitespaces)\n                .split(separator: " ", omittingEmptySubsequences: true)\n                .first\n                .map(String.init) ?? ""',
     '            let endToken = rest.trimmingCharacters(in: .whitespaces)',
     "the end token stops at the first space, not at the cue's settings"),
    ("inline markup in a cue", "PlaybackRules.swift",
     '            if !inside { out.append(character) }',
     '            out.append(character)',
     "inline markup never reaches the screen"),
    ("the mode picking the endpoint", "PlaybackURLs.swift",
     '        let path = PlaybackRules.usesHLS(mode) ? hlsMaster(itemID: itemID) : stream(itemID: itemID)',
     '        let path = stream(itemID: itemID)',
     "a remux rides the HLS master"),
    ("a direct play sending unusable parameters", "PlaybackURLs.swift",
     '        guard mode != .direct else { return items }',
     '        guard false else { return items }',
     "⚠ AudioStreamIndex and MaxStreamingBitrate are NOT sent on a direct play — Jellyfin ignores both under Static, so sending them would make a track choice LOOK applied"),
    ("the subtitle proxy's media source", "PlaybackURLs.swift",
     '         URLQueryItem(name: "ms", value: mediaSourceID.isEmpty ? itemID : mediaSourceID),',
     '         URLQueryItem(name: "ms", value: mediaSourceID),',
     "the subtitle proxy gets the item, the media source and the stream index"),
    ("the video bit depth key", "PlaybackModels.swift",
     '        case bitDepth = "bit_depth"',
     '        case bitDepth = "bitdepth"',
     "bit_depth decodes from its snake_case key"),
    ("the progress body's item key", "PlaybackModels.swift",
     '        case itemID = "item_id"\n        case positionTicks = "position_ticks"',
     '        case itemID = "id"\n        case positionTicks = "position_ticks"',
     "the progress body carries the contract's six keys and nothing else"),
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
