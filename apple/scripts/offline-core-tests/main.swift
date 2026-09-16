import Foundation

// The B2 gate that runs WITHOUT a Mac.
//
// ⚠ Why this exists rather than an XCTest target: the rules in `OfflineManifest.swift`,
// `OfflinePlan.swift` and `CookieHeader.swift` are the part of a downloader that is easy to get
// silently wrong — a resume offset, a changed ETag, an item id that escapes its directory — and they
// are pure, so they can be *executed* here instead of argued about. `apple/WORKFLOW.md` §5 makes the
// distinction the whole two-machine workflow rests on: a Mac build that has not run is not verified,
// and `swiftc -parse` proves nothing about types or behaviour.
//
// Compiled and run by `apple/scripts/check-offline-core.py`, which also FALSIFIES every rule below by
// reverting it and requiring the matching check to fail. A green run here is a real green run: these
// are the same sources the iOS target compiles, not a copy.

// MARK: - Tiny assertion kit

var checks = 0
var failures: [String] = []
var currentSection = "?"

func section(_ name: String) {
    currentSection = name
    print("\n-- \(name)")
}

func check(_ condition: Bool, _ label: String, _ detail: @autoclosure () -> String = "") {
    checks += 1
    if condition {
        print("   ok   \(label)")
    } else {
        let extra = detail()
        let line = extra.isEmpty ? label : "\(label) — \(extra)"
        print("   FAIL \(line)")
        failures.append("[\(currentSection)] \(line)")
    }
}

func checkEqual<T: Equatable>(_ got: T, _ want: T, _ label: String) {
    check(got == want, label, "got \(got), want \(want)")
}

// MARK: - Fixtures

let serverContainerMP4 = "mov,mp4,m4a,3gp,3g2,mj2"   // measured: Jellyfin's own value for an MP4
let serverContainerMKV = "mkv"                        // measured: plain, for an MKV
let serverContainerWebM = "matroska,webm"             // measured: the MKV/WebM demuxer list

func artefact(_ size: Int64, etag: String? = "\"1000-1758000000000000000\"") -> OfflineRemoteArtefact {
    OfflineRemoteArtefact(size: size, etag: etag, contentType: "video/mp4")
}

// MARK: - Identity: an item id as a directory name

section("identity")

switch OfflineIdentifier.validated("f3c1a9e04b8d4e0a9b7c2d5e6f8a1b3c") {
case .success(let id): checkEqual(id, "f3c1a9e04b8d4e0a9b7c2d5e6f8a1b3c", "a 32-hex Jellyfin id is stored verbatim")
case .failure(let error): check(false, "a 32-hex Jellyfin id is stored verbatim", "\(error)")
}

for bad in ["", "..", "../../etc/passwd", "a/b", "a.b", "a b", "a\nb", String(repeating: "a", count: 65)] {
    switch OfflineIdentifier.validated(bad) {
    case .success:
        check(false, "refuses \(bad.debugDescription)")
    case .failure(let error):
        check(!(error.reason.isEmpty), "refuses \(bad.debugDescription) with a sentence")
    }
}

switch OfflineIdentifier.validated("a_b-c") {
case .success(let id): checkEqual(id, "a_b-c", "underscores and hyphens are allowed")
case .failure(let error): check(false, "underscores and hyphens are allowed", "\(error)")
}

// MARK: - Layout

section("layout")

let layout = OfflineLayout(root: URL(fileURLWithPath: "/tmp/rkm-offline"))

checkEqual(OfflineLayout.mediaName(container: serverContainerMP4), "media.mp4", "an MP4's demuxer list becomes media.mp4")
checkEqual(OfflineLayout.mediaName(container: serverContainerMKV), "media.mkv", "mkv becomes media.mkv")
checkEqual(OfflineLayout.mediaName(container: serverContainerWebM), "media.mkv", "matroska,webm becomes media.mkv")
checkEqual(OfflineLayout.mediaName(container: "weird-thing"), "media.bin",
           "an unrecognised container is NOT trusted as a filename extension")
checkEqual(OfflineLayout.mediaName(container: nil), "media.bin", "no container means no claim about the format")
checkEqual(OfflineLayout.partialName(container: serverContainerMP4), "media.mp4.part", "the partial is a sibling of the final name")

if let media = try? layout.mediaURL("abc123", container: serverContainerMP4) {
    checkEqual(media.lastPathComponent, "media.mp4", "mediaURL ends in the media name")
    checkEqual(media.deletingLastPathComponent().path, "/tmp/rkm-offline/abc123", "an item gets its own directory")
} else {
    check(false, "mediaURL for a valid id")
}

do {
    _ = try layout.mediaURL("../escape", container: nil)
    check(false, "mediaURL refuses a traversing id")
} catch {
    check(true, "mediaURL refuses a traversing id")
}

if let part = try? layout.partialURL("abc123", container: serverContainerMP4) {
    checkEqual(part.path, "/tmp/rkm-offline/abc123/media.mp4.part", "the partial sits beside its final name")
} else {
    check(false, "partialURL for a valid id")
}

// MARK: - The record and the manifest

section("manifest")

let base = Date(timeIntervalSince1970: 1_758_000_000)

var record = OfflineRecord(
    itemId: "abc123",
    title: "Heat",
    mode: "remux",
    container: serverContainerMP4,
    contentType: "video/mp4",
    totalBytes: 1000,
    bytes: 250,
    etag: "\"1000-1\"",
    state: .downloading,
    attempts: 1
)
checkEqual(record.fraction.map { Int($0 * 100) }, 25, "fraction is derived from bytes over total")
checkEqual(record.remainingBytes, 750, "remainingBytes is what is left")
checkEqual(OfflineRecord(itemId: "x", title: "t", mode: "direct").fraction, nil, "no total means no fraction, never 0%")

record.state = .ready
record.bytes = 1000
record.downloadedAt = base
checkEqual(record.fraction, 1.0, "a complete record reads 100%")
checkEqual(record.remainingBytes, 0, "nothing remains")
check(record.state.isPlayable, "ready is the playable state")
check(OfflineState.paused.isPlayable == false, "paused is not playable")
check(OfflineState.downloading.isPlayable == false, "downloading is not playable")

// ⚠ The verification strength is a PERSISTED string (it goes into manifest.json), so both spellings are
// pinned here: an implicit raw value would change silently if a case were renamed, and an old manifest's
// `ready` row would then read back as "no idea how this was checked".
checkEqual(OfflineReadyVerification.sizeAndETag.rawValue, "size_etag",
           "size+ETag keeps the spelling it stores")
checkEqual(OfflineReadyVerification.sizeOnly.rawValue, "size_only",
           "size-only keeps the spelling it stores")
checkEqual(OfflineReadyVerification(rawValue: "size_etag"), .sizeAndETag,
           "and reads back from the stored form")
check(!OfflineReadyVerification.sizeOnly.label.isEmpty, "the weaker claim can describe itself")

// An OLD manifest — no content_type, no attempts, no last_error — must still load.
let oldJSON = """
{"items":[{"item_id":"abc123","title":"Heat","mode":"direct","borrowed":false,
"bytes":10,"total_bytes":100,"state":"downloading"}],"version":1}
"""
if let data = oldJSON.data(using: .utf8), let decoded = try? OfflineManifest.decode(data) {
    checkEqual(decoded.items.count, 1, "a manifest with missing optional fields still loads")
    let item = decoded.items[0]
    checkEqual(item.state, .downloading, "its state survives")
    checkEqual(item.attempts, 0, "a missing attempts count defaults to 0")
    checkEqual(item.lastError, nil, "a missing error defaults to nothing")
    checkEqual(item.title, "Heat", "its title survives")
    checkEqual(item.verification, nil, "a manifest written before verification existed reads as unverified")
} else {
    check(false, "a manifest with missing optional fields still loads")
}

// ⚠ An unknown state must fall to `.paused`, NEVER to `.ready`.
let unknownState = """
{"items":[{"item_id":"abc123","title":"Heat","mode":"direct","bytes":10,"total_bytes":100,
"state":"somethingFromANewerBuild"}],"version":1}
"""
if let data = unknownState.data(using: .utf8), let decoded = try? OfflineManifest.decode(data) {
    checkEqual(decoded.items[0].state, .paused, "an unknown state becomes paused, not ready")
} else {
    check(false, "an unknown state is readable")
}

// ⚠ A manifest from a NEWER build is refused, not half-read.
do {
    _ = try OfflineManifest.decode(Data("{\"items\":[],\"version\":2}".utf8))
    check(false, "a newer manifest version is refused")
} catch let error as OfflineManifestError {
    if case .fromANewerBuild(let found, let supported) = error {
        checkEqual(found, 2, "the refusal names the version it found")
        checkEqual(supported, OfflineManifest.currentVersion, "and the version it supports")
    } else {
        check(false, "a newer manifest version is refused", "got \(error)")
    }
    check(!(error.errorDescription ?? "").isEmpty, "the refusal carries a sentence")
} catch {
    check(false, "a newer manifest version is refused", "got \(error)")
}

do {
    _ = try OfflineManifest.decode(Data("not json".utf8))
    check(false, "unreadable JSON is refused")
} catch let error as OfflineManifestError {
    if case .unreadable = error { check(true, "unreadable JSON is refused as unreadable") }
    else { check(false, "unreadable JSON is refused as unreadable", "got \(error)") }
} catch {
    check(false, "unreadable JSON is refused as unreadable", "got \(error)")
}

// Round trip, with a real date, through the encoder and decoder the store uses.
var manifest = OfflineManifest()
record.verification = .sizeAndETag
manifest.upsert(record)
manifest.upsert(OfflineRecord(itemId: "def456", title: "Alien", mode: "direct", totalBytes: 5, state: .paused))
if let encoded = try? manifest.encoded(), let back = try? OfflineManifest.decode(encoded) {
    checkEqual(back.items.count, 2, "both records survive a round trip")
    checkEqual(back.item("abc123")?.downloadedAt, base, "the downloaded-at date survives to the second")
    checkEqual(back.item("abc123")?.state, .ready, "the state survives")
    checkEqual(back.item("abc123")?.verification, .sizeAndETag, "the verification strength survives")
    checkEqual(back.item("def456")?.title, "Alien", "the second record survives")
} else {
    check(false, "a manifest round-trips through JSON")
}

// Upsert replaces BY IDENTITY — not by appending, and not by index.
var mutating = OfflineManifest()
mutating.upsert(record)
var changed = record
changed.bytes = 900
mutating.upsert(changed)
checkEqual(mutating.items.count, 1, "upsert replaces rather than appends")
checkEqual(mutating.item("abc123")?.bytes, 900, "upsert keeps the new value")

checkEqual(mutating.remove("nope"), nil, "removing an unknown id returns nothing")
checkEqual(mutating.remove("abc123")?.itemId, "abc123", "removing returns what was removed")
checkEqual(mutating.items.count, 0, "and the manifest is empty afterwards")

var sized = OfflineManifest()
sized.upsert(OfflineRecord(itemId: "a", title: "A", mode: "direct", bytes: 10))
sized.upsert(OfflineRecord(itemId: "b", title: "B", mode: "direct", bytes: 32))
checkEqual(sized.totalBytesOnDisk, 42, "the disk total is the sum of what the records claim")

// MARK: - Status classification

section("status codes")

checkEqual(OfflineHTTPVerdict.classify(200), .success, "200 is a success")
checkEqual(OfflineHTTPVerdict.classify(206), .success, "206 is a success")
checkEqual(OfflineHTTPVerdict.classify(401), .signInRequired, "401 means sign in again")
checkEqual(OfflineHTTPVerdict.classify(403), .refused, "403 is a refusal")
checkEqual(OfflineHTTPVerdict.classify(404), .neverPrepared, "404 means never prepared")
checkEqual(OfflineHTTPVerdict.classify(409), .packaging, "409 means still packaging — WAIT")
checkEqual(OfflineHTTPVerdict.classify(410), .gone, "410 means the server lost the file")
checkEqual(OfflineHTTPVerdict.classify(416), .rangeNotSatisfiable, "416 means the offset is stale")
checkEqual(OfflineHTTPVerdict.classify(507), .storageFull, "507 is the server's own cap")
checkEqual(OfflineHTTPVerdict.classify(503), .serverError, "5xx is a server error")
checkEqual(OfflineHTTPVerdict.classify(418), .unexpected(418), "anything else is reported as itself")

check(OfflineHTTPVerdict.classify(409).isRetryable, "409 is retryable")
check(OfflineHTTPVerdict.classify(503).isRetryable, "a 5xx is retryable")
check(OfflineHTTPVerdict.classify(416).isRetryable, "416 is retryable — because the retry restarts from zero")
check(OfflineHTTPVerdict.classify(416).restartsFromZero, "and it says so")
check(!OfflineHTTPVerdict.classify(404).isRetryable, "404 is NOT retryable")
check(!OfflineHTTPVerdict.classify(410).isRetryable, "410 is NOT retryable")
check(!OfflineHTTPVerdict.classify(401).isRetryable, "401 is NOT retryable — a human has to sign in")
check(OfflineHTTPVerdict.classify(401).needsSignIn, "401 asks for a sign-in")
check(!OfflineHTTPVerdict.classify(503).needsSignIn, "a 5xx does not")

for status in [200, 206, 401, 403, 404, 409, 410, 416, 507, 500, 418] {
    check(!OfflineHTTPVerdict.classify(status).sentence(detail: nil).isEmpty,
          "HTTP \(status) has a sentence for the user")
}

// MARK: - Is what we have the whole film?

section("completion check")

checkEqual(
    OfflineCompletionCheck.check(localBytes: 1000, localETag: "\"e\"", remote: artefact(1000, etag: "\"e\"")),
    .complete(.sizeAndETag),
    "size and ETag both matching is the strong claim"
)
checkEqual(
    OfflineCompletionCheck.check(localBytes: 1000, localETag: nil, remote: artefact(1000, etag: "\"e\"")),
    .complete(.sizeOnly),
    "size alone is the weaker claim, and is recorded as such"
)
checkEqual(
    OfflineCompletionCheck.check(localBytes: 1000, localETag: "\"old\"", remote: artefact(1000, etag: "\"new\"")),
    .incomplete(reason: "the server's copy has changed since these bytes were fetched"),
    "the same size with a different ETag is NOT complete"
)
checkEqual(
    OfflineCompletionCheck.check(localBytes: 999, localETag: "\"e\"", remote: artefact(1000, etag: "\"e\"")),
    .incomplete(reason: "999 of 1000 bytes on this device"),
    "one byte short is not complete"
)
if case .incomplete = OfflineCompletionCheck.check(localBytes: 0, localETag: nil, remote: artefact(0, etag: "\"e\"")) {
    check(true, "a zero-byte server artefact is never complete")
} else {
    check(false, "a zero-byte server artefact is never complete")
}

// MARK: - The resume decision

section("resume")

checkEqual(
    OfflineResume.decide(localBytes: 0, localETag: nil, remote: .ready(artefact(1000))),
    .fresh(total: 1000),
    "nothing local is a fresh download"
)
checkEqual(
    OfflineResume.decide(localBytes: 400, localETag: "\"e\"", remote: .ready(artefact(1000, etag: "\"e\""))),
    .resume(fromOffset: 400, total: 1000),
    "a partial with the same ETag resumes from its own size"
)
checkEqual(
    OfflineResume.decide(localBytes: 1000, localETag: "\"e\"", remote: .ready(artefact(1000, etag: "\"e\""))),
    .alreadyComplete(.sizeAndETag),
    "a complete file is recognised before anything is fetched"
)
checkEqual(
    OfflineResume.decide(localBytes: 400, localETag: "\"old\"", remote: .ready(artefact(1000, etag: "\"new\""))),
    .restart(reason: "The server's copy of this title has changed since these bytes were fetched, "
                   + "so the part-downloaded file cannot be continued.", total: 1000),
    "a changed ETag restarts instead of splicing two different films together"
)

if case .restart = OfflineResume.decide(localBytes: 400, localETag: nil, remote: .ready(artefact(1000, etag: "\"e\""))) {
    check(true, "a partial with no recorded ETag restarts — it cannot be proven to belong")
} else {
    check(false, "a partial with no recorded ETag restarts — it cannot be proven to belong")
}

checkEqual(
    OfflineResume.decide(localBytes: 1500, localETag: "\"e\"", remote: .ready(artefact(1000, etag: "\"e\""))),
    .restart(reason: "This device holds 1500 bytes but the server's file is 1000 — the partial copy is not this file.",
             total: 1000),
    "a local file bigger than the server's is a restart"
)
checkEqual(
    OfflineResume.decide(localBytes: 0, localETag: nil, remote: .ready(artefact(0))),
    .unavailable(reason: "The server reported a zero-byte download for this title.", kind: .refused),
    "a zero-byte artefact is refused before anything else can read it as complete"
)
checkEqual(
    OfflineResume.decide(localBytes: 0, localETag: nil, remote: .ready(artefact(1000, etag: nil))),
    .fresh(total: 1000),
    "a server with no ETag can still be downloaded from scratch"
)
checkEqual(
    OfflineResume.decide(localBytes: 0, localETag: nil, remote: .packaging("still packaging")),
    .wait(reason: "still packaging"),
    "409 waits rather than failing"
)
checkEqual(
    OfflineResume.decide(localBytes: 400, localETag: "\"e\"", remote: .transport("connection dropped")),
    .wait(reason: "connection dropped"),
    "a dropped connection keeps the bytes and waits"
)

checkEqual(
    OfflineResume.decide(localBytes: 0, localETag: nil, remote: .neverPrepared("nope")),
    .unavailable(reason: "nope", kind: .notPrepared), "404 is 'not prepared'"
)
checkEqual(
    OfflineResume.decide(localBytes: 0, localETag: nil, remote: .gone("gone")),
    .unavailable(reason: "gone", kind: .gone), "410 is 'gone'"
)
checkEqual(
    OfflineResume.decide(localBytes: 0, localETag: nil, remote: .signInRequired("sign in")),
    .unavailable(reason: "sign in", kind: .signInRequired), "401 is 'sign-in required'"
)
checkEqual(
    OfflineResume.decide(localBytes: 0, localETag: nil, remote: .refused("no room")),
    .unavailable(reason: "no room", kind: .refused), "507 is 'refused'"
)
checkEqual(
    OfflineResume.decide(localBytes: 0, localETag: nil, remote: .failed("boom")),
    .wait(reason: "boom"), "a 5xx waits rather than discarding anything"
)

for kind in [OfflineUnavailableKind.notPrepared, .gone, .signInRequired, .refused] {
    check(!kind.label.isEmpty, "\(kind) has a label for the HUD")
}

// MARK: - Ranges

section("content ranges")

checkEqual(OfflineRangeReport.parse("bytes 100-199/1000"), .bytes(start: 100, end: 199, total: 1000),
           "a normal range parses")
checkEqual(OfflineRangeReport.parse("bytes */1000"), .unsatisfiable(total: 1000),
           "the 416 form parses")
for bad in ["", "items 1-2/3", "bytes=100-199/1000", "bytes 5-4/10", "bytes 0-10/10", "bytes 0-9/0",
            "bytes 0-/10", "bytes -5/10", "bytes 0-1/10, 5-6/10"] {
    checkEqual(OfflineRangeReport.parse(bad), nil, "\(bad.debugDescription) is unreadable and refused")
}
checkEqual(OfflineRangeReport.parse(nil), nil, "no header is no report")

checkEqual(OfflineRangeReport.requestHeader(fromOffset: 0), nil, "a fresh download sends NO Range header")
checkEqual(OfflineRangeReport.requestHeader(fromOffset: 400), "bytes=400-", "a resume asks for everything from the offset")

// MARK: - Splicing the response into the partial

section("assembly")

checkEqual(
    OfflineAssembly.plan(status: 206, contentRange: "bytes 400-999/1000", requestedOffset: 400,
                         localBytes: 400, remoteSize: 1000),
    .appendFragment(offset: 400),
    "a 206 that matches the request is appended at the offset"
)
if case .refuse = OfflineAssembly.plan(status: 206, contentRange: "bytes 0-999/1000", requestedOffset: 400,
                                      localBytes: 400, remoteSize: 1000) {
    check(true, "a 206 from the WRONG offset is refused rather than spliced")
} else {
    check(false, "a 206 from the WRONG offset is refused rather than spliced")
}
if case .refuse = OfflineAssembly.plan(status: 206, contentRange: "bytes 400-1499/1500", requestedOffset: 400,
                                      localBytes: 400, remoteSize: 1000) {
    check(true, "a 206 whose total disagrees with HEAD is refused")
} else {
    check(false, "a 206 whose total disagrees with HEAD is refused")
}
if case .refuse = OfflineAssembly.plan(status: 206, contentRange: nil, requestedOffset: 400,
                                      localBytes: 400, remoteSize: 1000) {
    check(true, "a 206 with no readable Content-Range is refused")
} else {
    check(false, "a 206 with no readable Content-Range is refused")
}
checkEqual(
    OfflineAssembly.plan(status: 200, contentRange: nil, requestedOffset: 400, localBytes: 400, remoteSize: 1000),
    .wholeFile(discardedBytes: 400),
    "a 200 to a ranged request replaces the partial, and says how much it discarded"
)
checkEqual(
    OfflineAssembly.plan(status: 200, contentRange: nil, requestedOffset: 0, localBytes: 0, remoteSize: 1000),
    .wholeFile(discardedBytes: 0),
    "a 200 to a fresh download discards nothing"
)
if case .refuse = OfflineAssembly.plan(status: 416, contentRange: "bytes */1000", requestedOffset: 400,
                                       localBytes: 400, remoteSize: 1000) {
    check(true, "a 416 is refused, and the retry that follows restarts from zero")
} else {
    check(false, "a 416 is refused, and the retry that follows restarts from zero")
}
if case .refuse = OfflineAssembly.plan(status: 409, contentRange: nil, requestedOffset: 400,
                                       localBytes: 400, remoteSize: 1000) {
    check(true, "a 409 at file-fetch time is refused rather than written")
} else {
    check(false, "a 409 at file-fetch time is refused rather than written")
}
checkEqual(OfflineAssemblyPlan.appendFragment(offset: 400).finalSize(fragmentBytes: 600), 1000,
           "appending 600 bytes at offset 400 makes a 1000-byte file")
checkEqual(OfflineAssemblyPlan.wholeFile(discardedBytes: 400).finalSize(fragmentBytes: 1000), 1000,
           "a whole-file response ends at its own size")
checkEqual(OfflineAssemblyPlan.refuse(reason: "x").finalSize(fragmentBytes: 1000), 0,
           "a refused response produces no size at all")

// MARK: - Retry

section("retry")

let policy = OfflineRetryPolicy.default
checkEqual(policy.delay(beforeAttempt: 1), 3, "the first retry waits 3s")
checkEqual(policy.delay(beforeAttempt: 2), 15, "the second waits 15s")
checkEqual(policy.delay(beforeAttempt: 3), 60, "the third waits 60s")
checkEqual(policy.delay(beforeAttempt: 4), nil, "the fourth attempt does not exist")
checkEqual(policy.delay(beforeAttempt: 0), nil, "attempt 0 is not an attempt")
checkEqual(OfflineRetryPolicy(maximumAttempts: 2, delays: [5]).delay(beforeAttempt: 1), 5,
           "a custom policy uses its own delays")
check(policy.hasAttemptsLeft(afterAttempt: 1), "there are attempts left after the first")
check(!policy.hasAttemptsLeft(afterAttempt: 4), "the last attempt is the last")

check(OfflineFailure.http(.packaging).isRetryable, "a packaging answer is retryable")
check(!OfflineFailure.http(.neverPrepared).isRetryable, "a 404 is not retryable")
check(OfflineFailure.transport(.offline).isRetryable, "being offline is retryable")
check(!OfflineFailure.transport(.cancelled).isRetryable, "a cancellation is never retried")
check(!OfflineFailure.local("no space").isRetryable, "a local problem is never retried automatically")
check(OfflineFailure.http(.signInRequired).needsSignIn, "a 401 needs a sign-in")
check(OfflineFailure.http(.rangeNotSatisfiable).restartsFromZero, "a 416 restarts from zero")
check(!OfflineFailure.http(.serverError).restartsFromZero, "a 5xx does not restart; it retries")
for failure in [OfflineFailure.http(.gone), .transport(.timedOut), .local("disk full")] {
    check(!failure.sentence.isEmpty, "\(failure) has a sentence")
}
checkEqual(OfflineFailure.http(.neverPrepared).sentence,
           "This title has not been prepared on the server yet",
           "the 404 sentence tells the user what to do")

// MARK: - Cookies — the native session

section("cookies")

let serverURL = URL(string: "http://rkm-hp.tail8d5e8.ts.net:8124/api/offline/file/abc")!
let secureURL = URL(string: "https://rkm-hp.tail8d5e8.ts.net:8124/api/offline/file/abc")!
let otherHostURL = URL(string: "http://example.com/api/offline/file/abc")!
let now = Date(timeIntervalSince1970: 1_758_000_000)

let sessionCookie = CookieSnapshot(name: "rkm_session", value: "secret-value",
                                   domain: "rkm-hp.tail8d5e8.ts.net", path: "/")

let sent = CookieHeader.evaluate(cookies: [sessionCookie], url: serverURL, now: now)
checkEqual(sent.header, "rkm_session=secret-value", "the session cookie is attached to our own host")
checkEqual(sent.sent, ["rkm_session"], "and is reported as sent")
check(sent.skipped.isEmpty, "with nothing skipped")

let crossHost = CookieHeader.evaluate(cookies: [sessionCookie], url: otherHostURL, now: now)
checkEqual(crossHost.header, nil, "the cookie is NOT attached to a different host")
if case .some(.domainMismatch) = crossHost.skipped.first?.reason {
    check(true, "and the skip says the domain did not match")
} else {
    check(false, "and the skip says the domain did not match", "got \(String(describing: crossHost.skipped.first))")
}

let domainCookie = CookieSnapshot(name: "rkm_session", value: "v", domain: ".tail8d5e8.ts.net", path: "/")
checkEqual(CookieHeader.evaluate(cookies: [domainCookie], url: serverURL, now: now).header,
           "rkm_session=v", "a leading-dot domain cookie covers the host")

let expired = CookieSnapshot(name: "rkm_session", value: "v", domain: "rkm-hp.tail8d5e8.ts.net",
                            path: "/", expiresAt: now.addingTimeInterval(-60))
let expiredOutcome = CookieHeader.evaluate(cookies: [expired], url: serverURL, now: now)
checkEqual(expiredOutcome.header, nil, "an expired cookie is not sent")
if case .some(.expired) = expiredOutcome.skipped.first?.reason {
    check(true, "and the skip says it expired")
} else {
    check(false, "and the skip says it expired")
}

let secureCookie = CookieSnapshot(name: "rkm_session", value: "v", domain: "rkm-hp.tail8d5e8.ts.net",
                                  path: "/", isSecure: true)
let plainHTTP = CookieHeader.evaluate(cookies: [secureCookie], url: serverURL, now: now)
checkEqual(plainHTTP.header, nil, "a Secure cookie is not sent over plain http")
if case .some(.secureOnPlainHTTP) = plainHTTP.skipped.first?.reason {
    check(true, "and the skip names plain http as the reason — the mystery-401 diagnosis")
} else {
    check(false, "and the skip names plain http as the reason — the mystery-401 diagnosis")
}
checkEqual(CookieHeader.evaluate(cookies: [secureCookie], url: secureURL, now: now).header,
           "rkm_session=v", "and IS sent over https")

let apiCookie = CookieSnapshot(name: "scoped", value: "v", domain: "rkm-hp.tail8d5e8.ts.net", path: "/api")
checkEqual(CookieHeader.evaluate(cookies: [apiCookie],
                                 url: URL(string: "http://rkm-hp.tail8d5e8.ts.net:8124/api/offline/x")!,
                                 now: now).header,
           "scoped=v", "a /api cookie covers /api/offline/x")
checkEqual(CookieHeader.evaluate(cookies: [apiCookie],
                                 url: URL(string: "http://rkm-hp.tail8d5e8.ts.net:8124/apix")!,
                                 now: now).header,
           nil, "a /api cookie does NOT cover /apix — the boundary is a slash")

let injected = CookieSnapshot(name: "rkm_session", value: "v\r\nX-Evil: 1",
                              domain: "rkm-hp.tail8d5e8.ts.net", path: "/")
let injection = CookieHeader.evaluate(cookies: [injected], url: serverURL, now: now)
checkEqual(injection.header, nil, "a cookie value with CRLF is never forwarded (header injection)")
if case .some(.illegalCharacters) = injection.skipped.first?.reason {
    check(true, "and the skip says why")
} else {
    check(false, "and the skip says why")
}

let badName = CookieSnapshot(name: "a b", value: "v", domain: "rkm-hp.tail8d5e8.ts.net", path: "/")
checkEqual(CookieHeader.evaluate(cookies: [badName], url: serverURL, now: now).header, nil,
           "a malformed cookie name is not sent")

let general = CookieSnapshot(name: "rkm_session", value: "general", domain: "rkm-hp.tail8d5e8.ts.net", path: "/")
let specific = CookieSnapshot(name: "rkm_session", value: "specific", domain: "rkm-hp.tail8d5e8.ts.net", path: "/api")
let both = CookieHeader.evaluate(cookies: [general, specific], url: serverURL, now: now)
checkEqual(both.header, "rkm_session=specific", "the most specific path wins for a duplicate name")
if case .some(.shadowedByPath) = both.skipped.first?.reason {
    check(true, "and the shadowed cookie is reported")
} else {
    check(false, "and the shadowed cookie is reported")
}

let empty = CookieHeader.evaluate(cookies: [], url: serverURL, now: now)
checkEqual(empty.header, nil, "no cookies means NO header at all, not an empty one")
check(empty.isEmpty, "and the outcome says it is empty")
check(!empty.summary.isEmpty, "an empty outcome still summarises")

let twoCookies = CookieHeader.evaluate(
    cookies: [general, CookieSnapshot(name: "aaa", value: "v", domain: "rkm-hp.tail8d5e8.ts.net", path: "/")],
    url: serverURL, now: now
)
checkEqual(twoCookies.header, "aaa=v; rkm_session=general", "equal paths sort by name, so the order is stable")
checkEqual(CookieHeader.headerFields(cookies: [general], url: serverURL, now: now),
           ["Cookie": "rkm_session=general"], "the header dictionary is ready to merge into a request")
checkEqual(CookieHeader.headerFields(cookies: [], url: serverURL, now: now), [:],
           "and is empty when nothing may be sent")

// ⚠ The leak test: the type must not print its own value.
let described = String(describing: sessionCookie)
check(!described.contains("secret-value"), "a cookie never prints its value")
check(described.contains("rkm_session"), "but it does print its name")
check(!sessionCookie.logName.contains("secret"), "logName is the name only")
check(!sent.summary.contains("secret-value"), "the outcome summary carries no values")

checkEqual(CookieHeader.domainMatches(cookie: "example.com", host: "example.com"), true,
           "an exact domain matches")
checkEqual(CookieHeader.domainMatches(cookie: ".example.com", host: "a.example.com"), true,
           "a subdomain matches")
checkEqual(CookieHeader.domainMatches(cookie: "example.com", host: "notexample.com"), false,
           "a suffix that is not a domain boundary does not match")
checkEqual(CookieHeader.domainMatches(cookie: "", host: "example.com"), false,
           "an empty domain matches nothing")

// MARK: - Formatting

section("formatting")

checkEqual(OfflineFormat.bytes(0), "0 B", "zero bytes reads as 0 B")
checkEqual(OfflineFormat.bytes(1500), "1.50 KB", "kilobytes")
checkEqual(OfflineFormat.bytes(1_882_377_499), "1.88 GB", "the live gate's own file size")
checkEqual(OfflineFormat.percent(nil), "—", "an unknown total shows a dash, never 0%")
checkEqual(OfflineFormat.percent(0.41), "41%", "a percentage")
checkEqual(OfflineFormat.eta(remainingBytes: 100, bytesPerSecond: 0), nil, "no rate means no ETA")
checkEqual(OfflineFormat.eta(remainingBytes: 100, bytesPerSecond: 10), "10s", "a short ETA")
checkEqual(OfflineFormat.eta(remainingBytes: 600, bytesPerSecond: 1), "10m 0s", "a long ETA")

// MARK: - Verdict

print("")
if failures.isEmpty {
    print("PASS — \(checks) checks, 0 failures")
    exit(0)
}
print("FAIL — \(checks) checks, \(failures.count) failure(s):")
for failure in failures { print("  · \(failure)") }
exit(1)
