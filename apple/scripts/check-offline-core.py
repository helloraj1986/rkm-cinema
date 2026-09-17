#!/usr/bin/env python3
"""Phase B2's gate that does NOT need the Mac — and, on request, its falsification.

⚠ Why this exists is in `apple/WORKFLOW.md` §5: development happens on Windows, testing happens on the
Mac, and *everything UI* is Mac-only. So the part of an offline downloader that is easy to get silently
wrong — where a resume starts, whether a partial belongs to the file the server is now offering, what a
`206` with a mismatched `Content-Range` means, which failures are worth retrying, whether an item id can
escape its directory, whether a cookie value can reach the log — is written as pure Foundation and
*executed here*.

What it does:

  1. compiles the three pure sources under `apple/ios/RKMCinema/Offline/`
     (`OfflineManifest.swift`, `OfflinePlan.swift`, `CookieHeader.swift`) together with the harness in
     `apple/scripts/offline-core-tests/main.swift`, using `swiftc`;
  2. runs it and reports PASS/FAIL — these are the SAME sources the iOS target compiles, not a copy;
  3. with `--falsify`, reverts each rule in a scratch copy of those sources and requires the harness to
     go RED on the specific check that rule protects. A rule whose mutation still passes is a rule that
     proves nothing, and this script fails in that case.

⚠ Build output goes to `~/tmp` (or `$RKM_CHECK_TMP`), never `/tmp`: `/tmp` is mounted `noexec` in this
sandbox, so a binary there cannot be run at all — the failure reads as a compile error and costs an hour.

Usage:
    python3 apple/scripts/check-offline-core.py              # compile + run
    python3 apple/scripts/check-offline-core.py --falsify    # + revert every rule, require each to fail

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
OFFLINE = REPO / "apple" / "ios" / "RKMCinema" / "Offline"
PURE_SOURCES = [
    OFFLINE / "OfflineManifest.swift",
    OFFLINE / "OfflinePlan.swift",
    OFFLINE / "CookieHeader.swift",
    # Phase B3 — the loopback server's decisions (request parsing, Range arithmetic, response planning,
    # tokens) and the page↔native contract. Same rule as B2: if it can be decided without a socket, it is
    # decided here, where it can be RUN.
    OFFLINE / "OfflineHTTP.swift",
    OFFLINE / "OfflineBridgeContract.swift",
    # ⚠ The Range suite itself, shared with the app's own DEBUG probe, so the Mac round tests exactly the
    # cases that were executed here.
    OFFLINE / "OfflineProbeCases.swift",
]
HARNESS = REPO / "apple" / "scripts" / "offline-core-tests" / "main.swift"

# ---------------------------------------------------------------------------- what gets reverted
#
# Each entry: (what it protects, file, exact text, replacement, a substring of the check that must fail).
# ⚠ The replacement is a REVERT (the rule removed or inverted), never a refinement — a mutation that
# "improves" the code proves nothing about the check.
MUTATIONS: list[tuple[str, str, str, str, str]] = [
    # --- identity / layout
    ("the item-id character rule", "OfflineManifest.swift",
     "if let bad = raw.first(where: { !allowed.contains($0) }) {",
     "if let bad = raw.first(where: { _ in false }) {",
     'refuses "../../etc/passwd"'),
    ("the item-id path check in routing", "OfflineManifest.swift",
     "root.appendingPathComponent(try OfflineIdentifier.checked(itemId), isDirectory: true)",
     "root.appendingPathComponent(itemId, isDirectory: true)",
     "mediaURL refuses a traversing id"),
    ("the MP4 family mapping", "OfflineManifest.swift",
     '        case "mp4": return "mp4"',
     '        case "mp4": return "mkv"',
     "an MP4's demuxer list becomes media.mp4"),
    ("the .part suffix", "OfflineManifest.swift",
     'static let partialSuffix = ".part"',
     'static let partialSuffix = ".tmp"',
     "the partial is a sibling of the final name"),
    # --- the record and the manifest
    ("the safe default for an unknown state", "OfflineManifest.swift",
     "state = rawState.flatMap(OfflineState.init(rawValue:)) ?? .paused",
     "state = rawState.flatMap(OfflineState.init(rawValue:)) ?? .ready",
     "an unknown state becomes paused, not ready"),
    ("the persisted verification spelling", "OfflinePlan.swift",
     'case sizeAndETag = "size_etag"',
     'case sizeAndETag = "sizeETag"',
     "size+ETag keeps the spelling it stores"),
    ("tolerant decoding of an older record", "OfflineManifest.swift",
     "attempts = try container.decodeIfPresent(Int.self, forKey: .attempts) ?? 0",
     "attempts = try container.decode(Int.self, forKey: .attempts)",
     "a manifest with missing optional fields still loads"),
    ("the newer-manifest refusal", "OfflineManifest.swift",
     "guard manifest.version <= currentVersion else {",
     "guard true else {",
     "a newer manifest version is refused"),
    ("upsert by identity", "OfflineManifest.swift",
     "if let index = items.firstIndex(where: { $0.itemId == record.itemId }) {\n            items[index] = record",
     "if false, let index = items.firstIndex(where: { $0.itemId == record.itemId }) {\n            items[index] = record",
     "upsert replaces rather than appends"),
    # --- completion
    ("the size equality gate", "OfflinePlan.swift",
     "guard localBytes == remote.size else {",
     "guard localBytes >= remote.size else {",
     "one byte short is not complete"),
    ("the ETag comparison", "OfflinePlan.swift",
     "            guard local == remote else {\n"
     "                return .incomplete(reason: \"the server's copy has changed since these bytes were fetched\")\n"
     "            }\n"
     "            return .complete(.sizeAndETag)",
     "            return .complete(.sizeAndETag)",
     "the same size with a different ETag is NOT complete"),
    ("the zero-byte artefact refusal", "OfflinePlan.swift",
     "guard artefact.size > 0 else {",
     "guard artefact.size >= 0 else {",
     "a zero-byte artefact is refused before anything else can read it as complete"),
    # --- resume
    ("the changed-ETag restart", "OfflinePlan.swift",
     "if let localETag, let remoteETag = artefact.etag, localETag != remoteETag {",
     "if false, let localETag, let remoteETag = artefact.etag, localETag != remoteETag {",
     "a changed ETag restarts instead of splicing two different films together"),
    ("the unprovable-partial restart", "OfflinePlan.swift",
     "if localETag == nil {",
     "if false {",
     "a partial with no recorded ETag restarts"),
    ("the bigger-than-remote restart", "OfflinePlan.swift",
     "if localBytes > artefact.size {",
     "if false {",
     "a local file bigger than the server's is a restart"),
    # --- ranges
    ("the Content-Range strictness", "OfflinePlan.swift",
     "start >= 0, end >= start, total > 0, end < total",
     "start >= 0, end >= start, total > 0, end <= total",
     'is unreadable and refused'),
    ("not sending a Range for a fresh download", "OfflinePlan.swift",
     "guard offset > 0 else { return nil }",
     "guard offset >= 0 else { return nil }",
     "a fresh download sends NO Range header"),
    # --- assembly
    ("the offset agreement check", "OfflinePlan.swift",
     "guard start == requestedOffset else {",
     "guard start >= 0 else {",
     "a 206 from the WRONG offset is refused rather than spliced"),
    ("the total agreement check", "OfflinePlan.swift",
     "guard total == remoteSize else {",
     "guard total > 0 else {",
     "a 206 whose total disagrees with HEAD is refused"),
    ("what a 200-to-a-range discards", "OfflinePlan.swift",
     "return .wholeFile(discardedBytes: requestedOffset > 0 ? localBytes : 0)",
     "return .wholeFile(discardedBytes: 0)",
     "a 200 to a ranged request replaces the partial, and says how much it discarded"),
    # --- retry
    ("the attempt ceiling", "OfflinePlan.swift",
     "guard attempt >= 1, attempt < maximumAttempts else { return nil }",
     "guard attempt >= 1, attempt <= maximumAttempts else { return nil }",
     "the fourth attempt does not exist"),
    ("what is worth retrying", "OfflinePlan.swift",
     "case .packaging, .serverError: return true",
     "case .packaging, .serverError, .neverPrepared: return true",
     "404 is NOT retryable"),
    ("a cancellation is never retried", "OfflinePlan.swift",
     "case .cancelled: return false\n        case .offline, .timedOut, .connectionLost, .other: return true",
     "case .cancelled: return true\n        case .offline, .timedOut, .connectionLost, .other: return true",
     "a cancellation is never retried"),
    # --- the sentence a failure shows
    # ⚠ His report 2026-09-18: the detail was discarded on the way to the row, so a `507` read "the
    # download storage is full" even when the server had said the budget was smaller than the film.
    ("the server's own sentence beating the canned one", "OfflinePlan.swift",
     "            if let detail, !detail.isEmpty { return detail }",
     "            if let detail, detail.isEmpty { return detail }",
     "the server's own sentence is what the row says"),
    # --- cookies
    ("the cookie domain rule", "CookieHeader.swift",
     "return host == candidate || host.hasSuffix(\".\" + candidate)",
     "return true",
     "the cookie is NOT attached to a different host"),
    ("the cookie path boundary", "CookieHeader.swift",
     "        return request[index] == \"/\"",
     "        return true",
     "a /api cookie does NOT cover /apix"),
    ("Secure cookies on plain http", "CookieHeader.swift",
     "if cookie.isSecure && !isHTTPS {",
     "if false {",
     "a Secure cookie is not sent over plain http"),
    ("the control-character guard", "CookieHeader.swift",
     "        value.unicodeScalars.contains { scalar in\n            scalar.value < 0x20 || scalar.value == 0x7F\n        }",
     "        _ = value\n        return false",
     "a cookie value with CRLF is never forwarded"),
    ("the duplicate-name shadowing", "CookieHeader.swift",
     "            if let existing = chosen.first(where: { $0.name == cookie.name }) {",
     "            if false, let existing = chosen.first(where: { $0.name == cookie.name }) {",
     "the most specific path wins for a duplicate name"),
    ("no cookies means no header", "CookieHeader.swift",
     "        guard !chosen.isEmpty else {\n"
     "            return CookieHeaderOutcome(header: nil, sent: [], skipped: skipped)\n"
     "        }",
     "        guard !chosen.isEmpty else {\n"
     "            return CookieHeaderOutcome(header: \"\", sent: [], skipped: skipped)\n"
     "        }",
     "no cookies means NO header at all"),
    ("the value-free description", "CookieHeader.swift",
     '"CookieSnapshot(\\(name) @ \\(domain.isEmpty ? "?" : domain)\\(path.isEmpty ? "/" : path)"',
     '"CookieSnapshot(\\(name)=\\(value) @ \\(domain.isEmpty ? "?" : domain)\\(path.isEmpty ? "/" : path)"',
     "a cookie never prints its value"),
    # --- formatting
    ("the unknown-total dash", "OfflinePlan.swift",
     'guard let fraction else { return "—" }',
     'guard let fraction else { return "0%" }',
     "an unknown total shows a dash"),
    # ==============================================================================================
    # Phase B3 — the loopback server and the page↔native contract. Same discipline: each mutation is a
    # REVERT of one rule, and the check it protects must go red.
    # ==============================================================================================
    # --- the Range arithmetic (an off-by-one here is a film that plays and is wrong from that point on)
    ("the end of an open-ended range", "OfflineHTTP.swift",
     "                return .partial(start: first, end: size - 1)",
     "                return .partial(start: first, end: size)",
     "[get-open-range] Content-Range"),
    ("an offset at the end is 416, not a clamp", "OfflineHTTP.swift",
     '                return .unsatisfiable(reason: "the asked-for offset is past the end of the file")',
     "                return .partial(start: first, end: size - 1)",
     "an offset AT the end is 416, never a clamp"),
    ("the clamp of a last-byte-pos past the end", "OfflineHTTP.swift",
     "            return .partial(start: first, end: min(last, size - 1))",
     "            return .partial(start: first, end: last)",
     "[get-clamped-end] Content-Range"),
    ("a suffix range means the LAST n bytes", "OfflineHTTP.swift",
     "                if suffix >= size { return .partial(start: 0, end: size - 1) }\n"
     "                return .partial(start: size - suffix, end: size - 1)",
     "                return .partial(start: 0, end: min(suffix, size) - 1)",
     "a suffix range is the LAST n bytes, not the first"),
    ("the zero-length suffix refusal", "OfflineHTTP.swift",
     "                guard suffix > 0 else {",
     "                guard suffix >= 0 else {",
     "a zero-length suffix names no bytes"),
    ("zero bytes can never satisfy a range", "OfflineHTTP.swift",
     "        guard size > 0 else {",
     "        guard size >= 0 else {",
     "⚠ zero bytes can never satisfy a range"),
    ("an unreadable range is the whole file", "OfflineHTTP.swift",
     '                return .wholeFile(reason: "the Range header could not be read")',
     '                return .unsatisfiable(reason: "the Range header could not be read")',
     "an unreadable range sends the whole file — the recoverable answer"),
    # --- the response
    ("a HEAD sends no body", "OfflineHTTP.swift",
     "        let sendsBody = method.sendsBody && status != 416",
     "        let sendsBody = status != 416",
     "⚠ a HEAD sends no body — and the plan is where that is decided"),
    ("a 416 states the real size", "OfflineHTTP.swift",
     '            extra.append(.init(name: "Content-Range", value: "bytes */\\(resource.size)"))',
     '            extra.append(.init(name: "Content-Range", value: "bytes */0"))',
     "⚠ a 416 states the real size, which is how a player recovers"),
    ("the response head's terminating blank line", "OfflineHTTP.swift",
     '        text += "\\r\\n"\n        return Data(text.utf8)',
     '        text += ""\n        return Data(text.utf8)',
     "the response head the planner produced was not readable"),
    ("a header value carrying CRLF is refused", "OfflineHTTP.swift",
     "        if let bad = headers.first(where: { containsControlCharacters($0.value) }) {",
     "        if false, let bad = headers.first(where: { containsControlCharacters($0.value) }) {",
     "⚠ a header value carrying CRLF is refused, never written"),
    ("the empty-artefact refusal", "OfflineHTTP.swift",
     "        guard resource.size > 0 else {",
     "        guard resource.size >= 0 else {",
     "⚠ a zero-byte file is 404, never an empty 200 that plays as nothing"),
    # --- the route and the request head
    ("an unknown token resolves to NOTHING", "OfflineHTTP.swift",
     "    func entry(for token: String) -> Entry? { entryByToken[token] }",
     "    func entry(for token: String) -> Entry? { entryByToken[token] ?? entryByToken.values.first }",
     "an unknown token resolves to nothing — there is no fallback to another title"),
    ("a token lookup does not case-fold", "OfflineHTTP.swift",
     "    func entry(for token: String) -> Entry? { entryByToken[token] }",
     "    func entry(for token: String) -> Entry? { entryByToken[token.lowercased()] }",
     "⚠ a token lookup does not case-fold: there is exactly one spelling"),
    ("an id the log's safety sweep would rewrite", "OfflineProbeCases.swift",
     'id: "get-uppercase-handle", method: "GET", target: .uppercaseToken, range: nil,',
     'id: "get-uppercase-token", method: "GET", target: .uppercaseToken, range: nil,',
     "the id does not contain `token`"),
    ("the canonical (lowercase-only) token spelling", "OfflineHTTP.swift",
     '            character.isASCII && (character.isNumber || ("a"..."f").contains(character))',
     '            character.isASCII && (character.isNumber || ("a"..."f").contains(character)\n'
     '                                  || ("A"..."F").contains(character))',
     "uppercase hex is NOT a token"),
    ("the extension set the route serves", "OfflineHTTP.swift",
     "        guard parts[1] == fileExtension, OfflineMediaType.knownExtensions.contains(fileExtension) else {",
     "        guard true else {",
     "an unknown extension is not a route"),
    ("a duplicated Range is refused", "OfflineHTTP.swift",
     '        if request.isDuplicate("range") {',
     "        if false {",
     "[get-duplicate-range] status"),
    ("a folded header line is refused", "OfflineHTTP.swift",
     '            if line.hasPrefix(" ") || line.hasPrefix("\\t") {',
     "            if false {",
     "a folded header line is refused, never unfolded"),
    ("the head size limit", "OfflineHTTP.swift",
     "            if data.count > OfflineHTTPLimits.maximumHeadBytes {",
     "            if false {",
     "a head larger than the limit is refused with 431"),
    ("only GET and HEAD are served", "OfflineHTTP.swift",
     "        guard let method = request.knownMethod else {\n"
     "            return refusal(.methodNotAllowed(method: request.method), request: request, allowed: true)\n"
     "        }",
     "        let method = request.knownMethod ?? .get",
     "an unknown method is 405"),
    # --- the token book
    ("the idempotent mint", "OfflineHTTP.swift",
     "        if let existing = tokenByItem[entry.itemId], entryByToken[existing] == entry {\n"
     "            return existing\n        }",
     "        if false, let existing = tokenByItem[entry.itemId], entryByToken[existing] == entry {\n"
     "            return existing\n        }",
     "⚠ asking twice returns the SAME token"),
    ("one live token per title", "OfflineHTTP.swift",
     "        if let stale = tokenByItem[entry.itemId] {\n"
     "            entryByToken.removeValue(forKey: stale)\n"
     "            tokenByItem.removeValue(forKey: entry.itemId)\n        }",
     "        if let stale = tokenByItem[entry.itemId] {\n            _ = stale\n        }",
     "⚠ and the old token stops working entirely"),
    ("a colliding mint is not reused", "OfflineHTTP.swift",
     "        while entryByToken[candidate] != nil && attempts < 64 {",
     "        while false {",
     "⚠ a mint that collides is not handed to a second title"),
    # --- the page↔native contract
    ("the version is required and exact", "OfflineBridgeContract.swift",
     '        guard let version = dictionary["v"] as? Int else {\n'
     "            return .failure(.unsupportedVersion(found: 0, supported: supportedVersion))\n        }",
     '        let version = (dictionary["v"] as? Int) ?? 1',
     "⚠ a message with no version is refused, never assumed to be v1"),
    ("an unknown command is refused by name", "OfflineBridgeContract.swift",
     "        guard let command = OfflineBridgeCommand(rawValue: rawCommand) else {\n"
     "            return .failure(.unknownCommand(rawCommand))\n        }",
     "        let command = OfflineBridgeCommand(rawValue: rawCommand) ?? .list",
     "⚠ an unknown command is refused BY NAME"),
    ("an unknown mode is refused, not defaulted", "OfflineBridgeContract.swift",
     "            guard OfflineBridgeMode.allowed.contains(cleaned) else {\n"
     "                return .failure(.badMode(raw, allowed: OfflineBridgeMode.allowed))\n            }",
     "            if OfflineBridgeMode.allowed.contains(cleaned) { mode = cleaned }",
     "an unknown mode is refused with the list, not defaulted"),
    ("the item id is refused, never rewritten", "OfflineBridgeContract.swift",
     "            case .failure(let error): return .failure(.invalidItemId(itemId: raw, reason: error.reason))",
     "            case .failure: itemId = raw",
     "a traversing item id is refused as an invalid item id"),
    ("a download needs a title", "OfflineBridgeContract.swift",
     "        if command == .download && title == nil {\n            return .failure(.missingTitle)\n        }",
     "        if false && command == .download {\n            return .failure(.missingTitle)\n        }",
     "a download without a title is refused"),
    # --- what the page is told, and how often
    ("state changes are never throttled", "OfflineBridgeContract.swift",
     "        if previous.state != current.state { return .state }",
     "        if false { return .state }",
     "a state change is always sent"),
    ("progress is throttled by step", "OfflineBridgeContract.swift",
     "        guard step > previous.emittedStep else { return .nothing }",
     "        guard step >= previous.emittedStep else { return .nothing }",
     "⚠ a step already sent is not sent again"),
    ("a rewind is a state change, not progress", "OfflineBridgeContract.swift",
     "        if step < previous.emittedStep { return .state }",
     "        if false { return .state }",
     "⚠ progress that goes BACKWARDS is a restart, and a restart is seen"),
    ("an unknown total is never a percentage", "OfflineBridgeContract.swift",
     "        guard totalBytes > 0 else { return nil }",
     "        guard totalBytes > 0 else { return 0 }",
     "⚠ an unknown total never becomes a percentage"),
    ("the URL appearing has its own event", "OfflineBridgeContract.swift",
     "        if previous.url == nil, let url = current.url, !url.isEmpty { return .ready }",
     "        if false, let url = current.url, !url.isEmpty { return .ready }",
     "⚠ the URL APPEARING is its own event"),
    ("a vanished title is announced", "OfflineBridgeContract.swift",
     "        let live = Set(current)\n        return previous.filter { !live.contains($0) }.sorted()",
     "        return []",
     "⚠ a deleted title is announced, and in a deterministic order"),
]


# ---------------------------------------------------------------------------- plumbing

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


def sources_in(directory: pathlib.Path) -> list[pathlib.Path]:
    return [directory / path.name for path in PURE_SOURCES] + [HARNESS]


def compile_and_run(
    swiftc: str,
    workdir: pathlib.Path,
    *,
    quiet: bool = False,
    attempts: int = 2,
) -> tuple[int, str]:
    """Compile into `workdir` and run. ⚠ Retries a failed COMPILE once: this sandbox kills a `swiftc`
    under memory pressure now and then, and a gate that reports a rule as unpinned because the compiler
    was killed is a gate that cries wolf."""
    binary = workdir / "offline-core-tests"
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


def stage(swiftc: str, workdir: pathlib.Path) -> None:
    workdir.mkdir(parents=True, exist_ok=True)
    for path in PURE_SOURCES:
        shutil.copy(path, workdir / path.name)


def main(argv: list[str]) -> int:
    falsify = "--falsify" in argv
    swiftc = find_swiftc()
    if swiftc is None:
        print("no swiftc found — cannot run the B2 core gate on this machine.", file=sys.stderr)
        print("  looked for: swiftc on PATH, /opt/swift/usr/bin/swiftc, /usr/bin/swiftc", file=sys.stderr)
        return 3

    base = exec_dir()
    print(f"swiftc: {swiftc}")
    print(f"temp:   {base}")

    with tempfile.TemporaryDirectory(dir=base) as tmp:
        workdir = pathlib.Path(tmp) / "pass"
        stage(swiftc, workdir)
        print(f"\n=== PASS RUN ({len(PURE_SOURCES)} pure sources + harness) ===")
        code, output = compile_and_run(swiftc, workdir)
        if code == 2:
            print(output)
            return 2
        if code != 0:
            print("\nThe B2 core gate FAILED. Fix the rules, not the harness.")
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
            stage(swiftc, workdir)
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
