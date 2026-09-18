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

// ⚠⚠ THE SERVER'S OWN SENTENCE WINS (his report, 2026-09-18: *"for the offline download the ios still
// have these logs, where it says storage is full"*). The server's refusal had stopped lying the day
// before and the phone had not: the detail was parsed off the wire and then discarded, so a 507 read
// "the download storage is full" whether the disk was full or the budget was smaller than the film.
// The text below is the backend's own budget sentence (`backend/services/offline.py::_check_cap`)
// with the numbers off his log — a 4.63 GB title against `RKM_OFFLINE_MAX_BYTES=10000` (bytes).
let hisBudgetRefusal = "this title alone is about 4.3 GB, which is larger than the entire offline "
    + "budget of 0.0 GB (RKM_OFFLINE_MAX_BYTES) — it can never be staged while that budget stands. "
    + "Raise the budget, or set it to 0 for no budget at all."
checkEqual(OfflineFailure.http(.storageFull, detail: hisBudgetRefusal).sentence,
           hisBudgetRefusal,
           "the server's own sentence is what the row says — not the client's canned one")
check(!OfflineFailure.http(.storageFull).sentence.contains("RKM_OFFLINE_MAX_BYTES"),
      "without the server's words, the canned sentence names no knob — so it must not pretend to")
checkEqual(OfflineFailure.http(.packaging, detail: "Still packaging (1234 B so far) — try again shortly").sentence,
           "Still packaging (1234 B so far) — try again shortly",
           "a 409's own words reach the row too")
checkEqual(OfflineFailure.http(.storageFull).sentence, "The server's download storage is full",
           "with no words from the server, the canned sentence stands in")
checkEqual(OfflineFailure.http(.serverError, detail: "").sentence, "The server had an error",
           "an EMPTY detail is not a sentence — the canned one stands in")
checkEqual(OfflineHTTPVerdict.classify(503).sentence(detail: "the disk is on fire"),
           "the disk is on fire",
           "a 5xx defers to the server as well — no canned claim survives beside it")
checkEqual(OfflineHTTPVerdict.classify(418).sentence(detail: "short and stout"),
           "Unexpected answer from the server (HTTP 418) — short and stout",
           "an unexpected status keeps its CODE, and the detail rides along beside it")
checkEqual(OfflineFailure.http(.rangeNotSatisfiable).sentence,
           "The server rejected the resume point — the download will start again from the beginning",
           "a 416 has no body to prefer, so the canned sentence is what it still says")

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

// MARK: - B3 · the loopback route (a token, and nothing else)

section("B3 · the loopback route")

let probeToken = "0123456789abcdef0123456789abcdef"

func routeExtension(_ target: String) -> String {
    switch OfflineRoute.parse(target) {
    case .success(let route): return route.fileExtension
    case .failure(.notOurPath): return "notOurPath"
    case .failure(.malformed(let reason)): return "malformed: \(reason)"
    }
}

checkEqual(OfflineToken.isValid(probeToken), true, "32 lowercase hex characters is a token")
checkEqual(OfflineToken.isValid(probeToken.uppercased()), false, "uppercase hex is NOT a token")
checkEqual(OfflineToken.isValid(String(probeToken.dropLast())), false, "31 characters is not a token")
checkEqual(OfflineToken.isValid(probeToken.replacingOccurrences(of: "0", with: "g")), false,
           "a non-hex character is not a token")
checkEqual(OfflineToken.isValid(OfflineToken.randomHex()), true, "a minted token validates")
checkEqual(OfflineToken.randomHex().count, 32, "a minted token is 32 characters")

checkEqual(routeExtension("/offline/\(probeToken).mp4"), "mp4", "the one path shape that is served")
checkEqual(routeExtension("/offline/\(probeToken).mp4?cache=1"), "mp4",
           "a query string is ignored, not refused")
checkEqual(routeExtension("/offline/\(probeToken).MP4"), "notOurPath",
           "an uppercase extension is refused: the path has one spelling")
checkEqual(routeExtension("/offline/\(probeToken.uppercased()).mp4").hasPrefix("malformed"), true,
           "an uppercase token is refused at the route as well as at the token")
checkEqual(routeExtension("/offline/%2e%2e%2fetc/passwd"), "notOurPath",
           "a percent-encoded name is not a route: nothing is decoded")
checkEqual(routeExtension("/offline/../../etc/passwd"), "notOurPath", "a traversing path is not a route")
checkEqual(routeExtension("/offline/\(probeToken)"), "notOurPath", "a missing extension is not a route")
checkEqual(routeExtension("/offline/\(probeToken).mp4.extra"), "notOurPath",
           "a second dot is not a route")
checkEqual(routeExtension("/offline/\(probeToken).txt"), "notOurPath", "an unknown extension is not a route")
checkEqual(routeExtension("/media/\(probeToken).mp4"), "notOurPath", "another prefix is not a route")
checkEqual(routeExtension("/"), "notOurPath", "the root is not a route")

// MARK: - B3 · reading a request head

section("B3 · reading a request head")

func headRead(_ text: String) -> OfflineHeadRead { OfflineHTTPRequest.readHead(Data(text.utf8)) }

func parsedHead(_ text: String) -> OfflineHTTPRequest? {
    if case .head(let request) = headRead(text) { return request }
    return nil
}

func headRefusal(_ text: String) -> OfflineHTTPRefusal? {
    if case .refused(let why) = headRead(text) { return why }
    return nil
}

func refusalReason(_ text: String) -> String { headRefusal(text)?.reason ?? "accepted" }

checkEqual(headRead("GET /offline/x.mp4 HTTP/1.1\r\nHost: h\r\n"), .needMore,
           "a head without its terminator needs more bytes, and is NOT an error")
checkEqual(parsedHead("GET /offline/\(probeToken).mp4 HTTP/1.1\r\nHost: h\r\n\r\n")?.method, "GET",
           "the method is read verbatim")
checkEqual(parsedHead("get /offline/\(probeToken).mp4 HTTP/1.1\r\n\r\n")?.knownMethod, nil,
           "a lowercase method is NOT silently accepted as GET")
checkEqual(parsedHead("HEAD /offline/\(probeToken).mp4 HTTP/1.0\r\n\r\n")?.knownMethod, .head,
           "HTTP/1.0 is answered too")
checkEqual(parsedHead("GET /offline/\(probeToken).mp4 HTTP/1.1\r\nRANGE: bytes=0-\r\n\r\n")?.header("range"),
           "bytes=0-", "header names are case-insensitive")
checkEqual(headRefusal("GET /offline/\(probeToken).mp4 HTTP/1.1\r\nHost\r\n\r\n") != nil, true,
           "a header line with no colon is malformed")
checkEqual(headRefusal("GET /offline/\(probeToken).mp4  HTTP/1.1\r\n\r\n") != nil, true,
           "two spaces in the request line is malformed, not tolerated")
checkEqual(headRefusal("GET /offline/\(probeToken).mp4\r\n\r\n") != nil, true,
           "a missing version is malformed")
checkEqual(headRefusal("GET /offline/\(probeToken).mp4 HTTP/2\r\n\r\n") != nil, true,
           "an unsupported version is refused")
checkEqual(headRefusal("GET http://127.0.0.1/offline/\(probeToken).mp4 HTTP/1.1\r\n\r\n") != nil, true,
           "a proxy-style absolute-form target is refused")
checkEqual(headRefusal("GET /offline/\(probeToken).mp4 HTTP/1.1\r\n Host: folded\r\n\r\n") != nil, true,
           "a folded header line is refused, never unfolded")
checkEqual(refusalReason("GET /offline/\(probeToken).mp4 HTTP/1.1\r\nRange: bytes=0-1\r\nRange: bytes=5-6\r\n\r\n"),
           "the Range header was sent 2 times — one unambiguous range is required",
           "⚠ a duplicated Range is refused rather than resolved")

if let duplicate = parsedHead("GET /offline/\(probeToken).mp4 HTTP/1.1\r\nHost: one\r\nHost: two\r\n\r\n") {
    checkEqual(duplicate.header("host"), "one", "the FIRST occurrence of a duplicated header wins")
    checkEqual(duplicate.isDuplicate("host"), true, "and the duplication is recorded")
} else {
    check(false, "a duplicated non-Range header still parses")
}

let oversized = String(repeating: "X", count: OfflineHTTPLimits.maximumHeadBytes + 64)
checkEqual(headRefusal(oversized)?.status, 431, "a head larger than the limit is refused with 431")

// MARK: - B3 · what a Range asks for

section("B3 · what a Range asks for")

func resolved(_ raw: String?, size: Int64) -> OfflineRangeOutcome {
    OfflineRangeOutcome.resolve(OfflineRangeRequest.parse(raw), size: size)
}

let rangeSize: Int64 = 1000

checkEqual(resolved(nil, size: rangeSize), .wholeFile(reason: nil), "no Range at all is the whole file")
checkEqual(resolved("", size: rangeSize), .wholeFile(reason: nil), "an empty Range header is no Range")
checkEqual(resolved("bytes=0-", size: rangeSize), .partial(start: 0, end: 999),
           "an open-ended range ends at the last byte")
checkEqual(resolved("bytes=0-0", size: rangeSize), .partial(start: 0, end: 0), "one byte is one byte")
checkEqual(resolved("bytes=500-", size: rangeSize), .partial(start: 500, end: 999),
           "a mid-file open range starts where it says")
checkEqual(resolved("bytes=999-", size: rangeSize), .partial(start: 999, end: 999),
           "the last byte is satisfiable")
checkEqual(resolved("bytes=1000-", size: rangeSize), .unsatisfiable(reason: "the asked-for offset is past the end of the file"),
           "⚠ an offset AT the end is 416, never a clamp")
checkEqual(resolved("bytes=5000-", size: rangeSize), .unsatisfiable(reason: "the asked-for offset is past the end of the file"),
           "an offset past the end is 416")
checkEqual(resolved("bytes=500-2000", size: rangeSize), .partial(start: 500, end: 999),
           "⚠ a last-byte-pos past the end IS clamped — the start names a real byte")
checkEqual(resolved("bytes=-100", size: rangeSize), .partial(start: 900, end: 999),
           "a suffix range is the LAST n bytes, not the first")
checkEqual(resolved("bytes=-1000", size: rangeSize), .partial(start: 0, end: 999),
           "a suffix longer than the file is the whole file")
checkEqual(resolved("bytes=-0", size: rangeSize), .unsatisfiable(reason: "a zero-length suffix names no bytes"),
           "a zero-length suffix names no bytes")
checkEqual(resolved("bytes=0-1, 5-6", size: rangeSize),
           .wholeFile(reason: "2 ranges were asked for; one file is sent instead"),
           "multiple ranges are answered with the whole file, never multipart")
checkEqual(resolved("items=0-1", size: rangeSize),
           .wholeFile(reason: "the Range unit \"items\" is not bytes"),
           "another unit is ignored rather than refused")
checkEqual(resolved("garbage", size: rangeSize),
           .wholeFile(reason: "the Range unit \"garbage\" is not bytes"),
           "a Range header with no unit is ignored")
checkEqual(resolved("bytes=abc", size: rangeSize),
           .wholeFile(reason: "the Range header could not be read"),
           "an unreadable range sends the whole file — the recoverable answer")
checkEqual(resolved("bytes=", size: rangeSize),
           .wholeFile(reason: "the Range header could not be read"),
           "an empty range list sends the whole file")
checkEqual(resolved("bytes=5-2", size: rangeSize),
           .wholeFile(reason: "the Range header could not be read"),
           "a reversed range is unreadable, not clamped to something else")
checkEqual(resolved("bytes=99999999999999999999-", size: rangeSize),
           .wholeFile(reason: "the Range header could not be read"),
           "an offset too large for Int64 is unreadable rather than a trap")
checkEqual(resolved("bytes=0-", size: 0), .unsatisfiable(reason: "the file on disk is empty"),
           "⚠ zero bytes can never satisfy a range")

// MARK: - B3 · the plan, and the head it becomes

section("B3 · the plan")

let tokenBook = OfflineTokenBook()
let probeEntry = OfflineTokenBook.Entry(itemId: "item-1", container: "mp4", fileExtension: "mp4")
let probeTokenValue = tokenBook.token(for: probeEntry) { "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" }
let probeResource = OfflineServeResource(url: URL(fileURLWithPath: "/tmp/rkm-probe.mp4"),
                                         size: 1000, etag: "1000-1758000000000000000",
                                         contentType: "video/mp4")

func plannedPlan(_ method: String, _ target: String, range: String? = nil) -> OfflineHTTPPlan? {
    var lines = ["\(method) \(target) HTTP/1.1", "Host: 127.0.0.1"]
    if let range { lines.append("Range: \(range)") }
    let head = Data((lines.joined(separator: "\r\n") + "\r\n\r\n").utf8)
    guard case .head(let request) = OfflineHTTPRequest.readHead(head) else { return nil }
    return OfflineServerCore.plan(request, tokens: tokenBook) { _ in probeResource }
}

func planStatus(_ method: String, _ target: String, range: String? = nil) -> Int {
    plannedPlan(method, target, range: range)?.response.status ?? -1
}

func planLogLine(_ method: String, _ target: String, range: String? = nil) -> String {
    plannedPlan(method, target, range: range)?.logLine ?? "<no plan>"
}

checkEqual(planStatus("GET", "/offline/\(probeTokenValue).mp4"), 200, "a plain GET is 200")
checkEqual(planStatus("HEAD", "/offline/\(probeTokenValue).mp4"), 200, "a HEAD is 200")
checkEqual(planStatus("GET", "/offline/\(probeTokenValue).mp4", range: "bytes=0-"), 206, "a range is 206")
checkEqual(planStatus("HEAD", "/offline/\(probeTokenValue).mp4", range: "bytes=0-"), 206,
           "a HEAD with a range is 206 too — the status describes the resource, not the body")
checkEqual(planStatus("GET", "/offline/\(probeTokenValue).mp4", range: "bytes=1000-"), 416,
           "an unsatisfiable range is 416")
checkEqual(planStatus("GET", "/offline/\(OfflineProbeTarget.unknownToken).mp4"), 404,
           "a token nobody minted is 404")
checkEqual(planStatus("POST", "/offline/\(probeTokenValue).mp4"), 405, "an unknown method is 405")
checkEqual(planStatus("GET", "/offline/../../etc/passwd"), 400, "a traversing path is 400")

let wholePlan = plannedPlan("GET", "/offline/\(probeTokenValue).mp4")
checkEqual(wholePlan?.response.contentLength, 1000, "a whole-file 200 declares the file's length")
checkEqual(wholePlan?.response.headerValue("content-range"), nil, "a 200 carries NO Content-Range")
checkEqual(wholePlan?.response.headerValue("accept-ranges"), "bytes", "a 200 advertises byte ranges")
checkEqual(wholePlan?.response.headerValue("cache-control"), "no-store",
           "⚠ a loopback URL may never be cached: the port dies with the process")
checkEqual(wholePlan?.response.headerValue("connection"), "close", "one request per connection")
checkEqual(wholePlan?.response.headerValue("etag"), "\"1000-1758000000000000000\"",
           "the ETag is quoted, as the header requires")
checkEqual(wholePlan?.fileURL, probeResource.url, "a 200 GET streams the file")
checkEqual(wholePlan?.offset, 0, "a 200 starts at zero")
checkEqual(wholePlan?.length, 1000, "a 200 sends the whole file")

let headPlan = plannedPlan("HEAD", "/offline/\(probeTokenValue).mp4")
checkEqual(headPlan?.response.contentLength, 1000,
           "⚠ a HEAD declares the length it will NOT send")
checkEqual(headPlan?.fileURL, nil, "⚠ a HEAD sends no body — and the plan is where that is decided")
checkEqual(headPlan?.length, 0, "a HEAD has no body length")

let rangedPlan = plannedPlan("GET", "/offline/\(probeTokenValue).mp4", range: "bytes=500-")
checkEqual(rangedPlan?.response.headerValue("content-range"), "bytes 500-999/1000",
           "a 206 states exactly which bytes these are, out of the whole")
checkEqual(rangedPlan?.response.contentLength, 500, "a 206 declares the length of the range")
checkEqual(rangedPlan?.offset, 500, "a 206 streams from the asked-for offset")
checkEqual(rangedPlan?.length, 500, "a 206 streams the asked-for length")

let rangedHeadPlan = plannedPlan("HEAD", "/offline/\(probeTokenValue).mp4", range: "bytes=500-")
checkEqual(rangedHeadPlan?.response.contentLength, 500,
           "⚠ a ranged HEAD declares the RANGE's length")
checkEqual(rangedHeadPlan?.fileURL, nil, "and still sends nothing")

let unsatisfiablePlan = plannedPlan("GET", "/offline/\(probeTokenValue).mp4", range: "bytes=1000-")
checkEqual(unsatisfiablePlan?.response.headerValue("content-range"), "bytes */1000",
           "⚠ a 416 states the real size, which is how a player recovers")
checkEqual(unsatisfiablePlan?.response.contentLength, 0, "a 416 has an empty body")
checkEqual(unsatisfiablePlan?.fileURL, nil, "a 416 streams nothing")
checkEqual(unsatisfiablePlan?.response.headerValue("accept-ranges"), nil,
           "a 416 does not advertise a capability it just refused")

// ⚠ A token that resolves to a file of ZERO bytes: the token book cannot tell 0 bytes from a film, so the
// planner must. A 200 with Content-Length 0 is a download that reports success and plays as nothing.
if let validHead = plannedPlan("GET", "/offline/\(probeTokenValue).mp4") {
    _ = validHead
    let emptyResource = OfflineServeResource(url: URL(fileURLWithPath: "/tmp/rkm-probe.mp4"),
                                             size: 0, etag: "0-x", contentType: "video/mp4")
    let emptyPlan = OfflineServerCore.plan(requestData:
        OfflineProbeCase(id: "empty", method: "GET", target: .valid, range: nil, extraHeaderLines: [],
                         expectStatus: 200, expectContentLength: nil, expectContentRange: nil,
                         expectBodyBytes: 0, expectBytesFromFile: false, mirrorWithURLSession: false,
                         note: "an empty artefact").headBytes(token: probeTokenValue, fileExtension: "mp4",
                                                             host: "127.0.0.1"),
        tokens: tokenBook) { _ in emptyResource }
    checkEqual(emptyPlan.response.status, 404,
               "⚠ a zero-byte file is 404, never an empty 200 that plays as nothing")
    checkEqual(emptyPlan.fileURL, nil, "and nothing is streamed for it")
} else {
    check(false, "the empty-artefact case could be planned")
}

let methodPlan = plannedPlan("POST", "/offline/\(probeTokenValue).mp4")
checkEqual(methodPlan?.response.headerValue("allow"), "GET, HEAD", "a 405 says what IS allowed")

// ⚠⚠ The header-injection guard, and it needs its own case: an ETag is echoed from the server's own
// response headers, so a value carrying a CRLF would end this response and begin another one.
let evilResource = OfflineServeResource(url: URL(fileURLWithPath: "/tmp/rkm-probe.mp4"),
                                        size: 1000, etag: "1000\r\nX-Evil: yes",
                                        contentType: "video/mp4")
if let evilPlan = plannedPlan("GET", "/offline/\(probeTokenValue).mp4") {
    let evilActual = OfflineServerCore.plan(requestData:
        OfflineProbeCase(id: "evil", method: "GET", target: .valid, range: nil, extraHeaderLines: [],
                         expectStatus: 200, expectContentLength: nil, expectContentRange: nil,
                         expectBodyBytes: 0, expectBytesFromFile: false, mirrorWithURLSession: false,
                         note: "an ETag carrying CRLF").headBytes(token: probeTokenValue, fileExtension: "mp4",
                                                                 host: "127.0.0.1"),
        tokens: tokenBook) { _ in evilResource }
    checkEqual(evilActual.response.status, 500,
               "⚠ a header value carrying CRLF is refused, never written")
    checkEqual(evilActual.response.headBytes.contains(Data("X-Evil".utf8)), false,
               "⚠ and no second header can be smuggled into the response")
    _ = evilPlan
} else {
    check(false, "the header-injection case could be planned")
}

checkEqual(planLogLine("GET", "/offline/\(probeTokenValue).mp4", range: "bytes=500-").contains(probeTokenValue),
           false, "⚠ the log line never contains the token — a token is a capability")
checkEqual(planLogLine("GET", "/offline/\(probeTokenValue).mp4", range: "bytes=500-")
           .contains("/offline/<handle>.mp4"), true,
           "the log line names the path by shape — and by `handle`, which is what keeps LOGGING.md §9's "
           + "`token` grep clean")
checkEqual(planLogLine("GET", "/offline/\(probeTokenValue).mp4", range: "bytes=500-")
           .contains("range bytes 500-999/1000"), true, "⚠ the log line carries the Content-Range")

checkEqual(wholePlan?.response.headBytes.starts(with: Data("HTTP/1.1 200 OK\r\n".utf8)), true,
           "the head starts with a real status line")

if let head = wholePlan?.response.headBytes {
    switch OfflineProbeWire.parseHead(head) {
    case .head(let wire):
        checkEqual(wire.status, 200, "the response head parses back to its status")
        checkEqual(wire.contentLength, 1000, "and back to its Content-Length")
    case .needMore:
        check(false, "the response head the planner produced was not readable")
    }
} else {
    check(false, "a plan with a body has head bytes")
}

// MARK: - B3 · the Range suite itself, executed on Linux

section("B3 · the Range suite (the same cases the Mac probe sends)")

let suiteSize: Int64 = 1000
let suiteCases = OfflineProbeCases.cases(size: suiteSize)
checkEqual(Set(suiteCases.map { $0.id }).count, suiteCases.count,
           "every probe case has a unique id")
check(suiteCases.count >= 16, "the suite has \(suiteCases.count) cases")

// ⚠⚠ A CASE ID IS LOGGED, AND THE LOG HAS A SAFETY SWEEP. `LogRedactor`'s last line of defence rewrites the
// words `LOGGING.md` §9 greps for — inside ANY message — so an id containing one arrives in the log as
// `offline probe case cred PASS`, and a gate cannot say WHICH case failed. ⚠ The words are declared here
// rather than imported: the harness compiles only the pure Offline sources, so a rule that depends on a
// module it cannot see would not run at all.
let redactorForbiddenWords = ["password", "token", "api_key", "rkm_session"]
for probeCase in suiteCases {
    for word in redactorForbiddenWords {
        checkEqual(probeCase.id.lowercased().contains(word), false,
                   "[\(probeCase.id)] the id does not contain `\(word)` — the log's safety sweep rewrites it")
    }
}

for probeCase in suiteCases {
    let head = probeCase.headBytes(token: probeTokenValue, fileExtension: "mp4", host: "127.0.0.1")
    // ⚠ Through `plan(requestData:)`, the same entry point the socket uses: a case whose head is refused
    // BEFORE it becomes a request (a proxy-style target, a duplicate Range) is still a case the suite
    // answers, rather than a case the harness quietly skips.
    let plan = OfflineServerCore.plan(requestData: head, tokens: tokenBook) { _ in probeResource }
    let response = plan.response

    checkEqual(response.status, probeCase.expectStatus, "[\(probeCase.id)] status")
    if let expected = probeCase.expectContentLength {
        checkEqual(response.contentLength, expected, "[\(probeCase.id)] Content-Length")
    } else {
        checkEqual(response.headerValue("content-length"), nil, "[\(probeCase.id)] no Content-Length")
    }
    if let expected = probeCase.expectContentRange {
        checkEqual(response.headerValue("content-range"), expected, "[\(probeCase.id)] Content-Range")
    } else {
        checkEqual(response.headerValue("content-range"), nil, "[\(probeCase.id)] no Content-Range")
    }

    let plannedBody: Int64 = probeCase.expectStatus == 206 || response.status == 200
        ? plan.length : 0
    checkEqual(plannedBody, probeCase.expectBodyBytes, "[\(probeCase.id)] the body length planned")

    // ⚠ And the round trip: what the planner WOULD write must read back as the same document.
    if case .head(let wire) = OfflineProbeWire.parseHead(response.headBytes) {
        checkEqual(wire.status, probeCase.expectStatus, "[\(probeCase.id)] the head parses back")
        checkEqual(wire.contentLength, response.contentLength,
                   "[\(probeCase.id)] the head's own Content-Length agrees")
    } else {
        check(false, "[\(probeCase.id)] the response head is readable")
    }
}

// MARK: - B3 · the token book

section("B3 · the token book")

let bookA = OfflineTokenBook()
let entryOne = OfflineTokenBook.Entry(itemId: "item-1", container: "mp4", fileExtension: "mp4")
let entryOneOther = OfflineTokenBook.Entry(itemId: "item-1", container: "mkv", fileExtension: "mkv")
let entryTwo = OfflineTokenBook.Entry(itemId: "item-2", container: "mp4", fileExtension: "mp4")

let firstMint = bookA.token(for: entryOne) { "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" }
checkEqual(bookA.token(for: entryOne) { "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb" }, firstMint,
           "⚠ asking twice returns the SAME token — a playing <video> must not have its URL moved")
checkEqual(bookA.entry(for: firstMint), entryOne, "the token resolves to what it was minted for")
checkEqual(firstMint.uppercased() != firstMint, true,
           "the fixture token has letters, or a case check below would prove nothing")
checkEqual(bookA.entry(for: firstMint.uppercased()), nil,
           "⚠ a token lookup does not case-fold: there is exactly one spelling")
checkEqual(bookA.entry(for: OfflineProbeTarget.unknownToken), nil,
           "an unknown token resolves to nothing — there is no fallback to another title")
checkEqual(bookA.count, 1, "one token on the book")

let secondMint = bookA.token(for: entryOneOther) { "cccccccccccccccccccccccccccccccc" }
checkEqual(secondMint != firstMint, true, "a different rendition mints a different token")
checkEqual(bookA.entry(for: firstMint), nil, "⚠ and the old token stops working entirely")
checkEqual(bookA.tokenCount(for: "item-1"), 1, "a title holds exactly ONE live token")

let thirdMint = bookA.token(for: entryTwo) { "dddddddddddddddddddddddddddddddd" }
checkEqual(bookA.count, 2, "a second title gets its own token")
checkEqual(bookA.entry(for: thirdMint), entryTwo, "and it resolves to that title")

checkEqual(bookA.forget(itemId: "item-2"), true, "forgetting a title drops its token")
checkEqual(bookA.entry(for: thirdMint), nil, "and the token stops resolving")
checkEqual(bookA.forget(itemId: "never-seen"), false, "forgetting an unknown title is not an error")
checkEqual(bookA.forgetAll(), 1, "forgetAll reports how many it dropped")
checkEqual(bookA.isEmpty, true, "⚠ a new server address or a sign-out leaves NO usable token")

var mintCalls = 0
let bookB = OfflineTokenBook()
let collidesWith = "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
_ = bookB.token(for: entryOne) { collidesWith }
let collided = bookB.token(for: entryTwo) {
    mintCalls += 1
    return mintCalls < 3 ? collidesWith : "ffffffffffffffffffffffffffffffff"
}
checkEqual(collided == collidesWith, false, "⚠ a mint that collides is not handed to a second title")
checkEqual(bookB.entry(for: collidesWith), entryOne, "the first title keeps the token it was given")

// MARK: - B3 · the page ↔ native contract

section("B3 · the bridge contract")

func bridgeParse(_ body: Any) -> Result<OfflineBridgeRequest, OfflineBridgeError> {
    OfflineBridgeRequest.parse(body)
}

func bridgeError(_ body: Any) -> OfflineBridgeError? {
    if case .failure(let error) = OfflineBridgeRequest.parse(body) { return error }
    return nil
}

func bridgeCommand(_ body: Any) -> OfflineBridgeCommand? {
    if case .success(let request) = OfflineBridgeRequest.parse(body) { return request.command }
    return nil
}

func json(_ value: Any) -> String {
    guard JSONSerialization.isValidJSONObject(value),
          let data = try? JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]),
          let text = String(data: data, encoding: .utf8)
    else { return "<unserialisable>" }
    return text
}

checkEqual(bridgeCommand(["v": 1, "c": "list"]), .list, "a v1 list message is accepted")
checkEqual(bridgeCommand("{\"v\":1,\"c\":\"ping\"}"), .ping,
           "a JSON STRING body is accepted as well as a dictionary — both spellings arrive in practice")

if case .success(let request) = bridgeParse(["v": 1, "c": "download", "itemId": "abc123", "title": "Heat"]) {
    checkEqual(request.mode, "auto", "an absent mode defaults to auto")
    checkEqual(request.title, "Heat", "the title is carried through")
} else {
    check(false, "a download message parses")
}

if case .success(let request) = bridgeParse(["v": 1, "c": "download", "itemId": "abc123",
                                             "title": "Heat", "mode": "REMUX"]) {
    checkEqual(request.mode, "remux", "⚠ a mode is canonicalised, and a known one is accepted")
} else {
    check(false, "an uppercase known mode is accepted")
}

checkEqual(bridgeError(["c": "list"]), .unsupportedVersion(found: 0, supported: 1),
           "⚠ a message with no version is refused, never assumed to be v1")
checkEqual(bridgeError(["v": 2, "c": "list"]), .unsupportedVersion(found: 2, supported: 1),
           "⚠ a NEWER page is refused with a sentence, not guessed at")
checkEqual(bridgeError(["v": 1, "c": "explode"]), .unknownCommand("explode"),
           "⚠ an unknown command is refused BY NAME — ignoring it would leave the page waiting")
checkEqual(bridgeError(["v": 1, "c": "play"]), .missingItemId(command: "play"),
           "play without an item is refused")
checkEqual(bridgeError(["v": 1, "c": "download", "itemId": "abc123"]), .missingTitle,
           "a download without a title is refused — the Downloads screen has to name it")
if case .invalidItemId(let badId, let reason)? = bridgeError(["v": 1, "c": "download",
                                                             "itemId": "../../etc", "title": "x"]) {
    checkEqual(badId, "../../etc", "⚠ an unusable item id is refused, never rewritten")
    checkEqual(reason.isEmpty, false, "and the refusal carries the reason the server side gave")
} else {
    check(false, "a traversing item id is refused as an invalid item id")
}
checkEqual(bridgeError(["v": 1, "c": "download", "itemId": "abc123", "title": "x", "mode": "1080p"]),
           .badMode("1080p", allowed: ["auto", "direct", "remux", "transcode_audio", "transcode"]),
           "an unknown mode is refused with the list, not defaulted")
checkEqual(bridgeError("not json"), .notReadable(reason: "a String body was not a JSON object"),
           "an unreadable body is named as such")
checkEqual(bridgeError(42), .notReadable(reason: "the message is neither a dictionary nor a JSON string"),
           "a body that is neither shape is refused")

checkEqual(json(OfflineBridgeReply.failure(.unknownItem(itemId: "abc")).jsonObject).contains("\"ok\":false"),
           true, "a failed reply says so")
checkEqual(json(OfflineBridgeReply.failure(.unknownItem(itemId: "abc")).jsonObject)
           .contains("\"code\":\"unknownItem\""), true, "and names its code")
checkEqual(json(OfflineBridgeReply.listed([]).jsonObject).contains("\"count\":0"), true,
           "an empty list reply is a valid reply")
checkEqual(json(OfflineBridgeReply.accepted(.download).jsonObject).contains("\"accepted\":\"download\""),
           true, "⚠ an accepted command says ACCEPTED, never done")

let playReply = OfflineBridgeReply.playable(OfflineBridgePlay(
    itemId: "abc", url: "http://127.0.0.1:50123/offline/\(probeTokenValue).mp4",
    contentType: "video/mp4", size: 1000))
checkEqual(json(playReply.jsonObject).contains("\"contentType\""), true,
           "the play reply carries the content type as well as the URL")
checkEqual(json(playReply.jsonObject).contains("\"size\":1000"), true,
           "and the size, so the page can show it without asking again")
checkEqual(json(playReply.jsonObject).contains("\"ok\":true"), true, "a playable reply says so")

// MARK: - B3 · what the page is told, and how often

section("B3 · the event planner")

func snapshot(_ itemId: String = "i1", title: String = "Heat", state: OfflineState = .downloading,
              bytes: Int64 = 0, total: Int64 = 1000, mode: String = "auto",
              url: String? = nil, error: String? = nil, step: Int = -1) -> OfflineEventSnapshot {
    OfflineEventSnapshot(itemId: itemId, title: title, state: state, bytes: bytes, totalBytes: total,
                         mode: mode, url: url, error: error, emittedStep: step)
}

let baseSnapshot = snapshot(bytes: 100, step: 10)
checkEqual(OfflineEventPlanner.decide(previous: nil, current: baseSnapshot), .state,
           "⚠ the page is never assumed to know anything — every title is announced once")
checkEqual(OfflineEventPlanner.decide(previous: baseSnapshot, current: baseSnapshot), .nothing,
           "nothing changed means nothing is sent")
checkEqual(OfflineEventPlanner.decide(previous: snapshot(bytes: 100, step: -1),
                                      current: snapshot(bytes: 100)),
           .progress(step: 10), "a step that was never sent is sent, even at the same byte count")
checkEqual(OfflineEventPlanner.decide(previous: baseSnapshot, current: snapshot(state: .ready, bytes: 100)),
           .state, "a state change is always sent")
checkEqual(OfflineEventPlanner.decide(previous: baseSnapshot, current: snapshot(bytes: 100, total: 2000)),
           .state, "a changed total is a state change, not progress")
checkEqual(OfflineEventPlanner.decide(previous: baseSnapshot, current: snapshot(bytes: 100, error: "lost")),
           .state, "a new error is always sent")
checkEqual(OfflineEventPlanner.decide(previous: baseSnapshot, current: snapshot(bytes: 100, mode: "direct")),
           .state, "a changed rendition is a state change")
checkEqual(OfflineEventPlanner.decide(previous: baseSnapshot,
                                      current: snapshot(bytes: 100, url: "http://127.0.0.1:1/offline/x.mp4")),
           .ready, "⚠ the URL APPEARING is its own event: that is the moment it plays offline")
checkEqual(OfflineEventPlanner.decide(previous: snapshot(bytes: 100, url: "http://127.0.0.1:1/offline/x.mp4"),
                                      current: snapshot(bytes: 100)),
           .state, "⚠ a URL DISAPPEARING is a state change — the page must stop offering it")
checkEqual(OfflineEventPlanner.decide(previous: snapshot(bytes: 100, url: "http://127.0.0.1:1/offline/x.mp4"),
                                      current: snapshot(bytes: 100, url: "http://127.0.0.1:2/offline/y.mp4")),
           .state, "a changed URL is a state change")

checkEqual(OfflineEventPlanner.decide(previous: snapshot(bytes: 100, total: 0),
                                      current: snapshot(bytes: 200, total: 0)),
           .nothing, "⚠ an unknown total never becomes a percentage")
checkEqual(OfflineEventPlanner.decide(previous: snapshot(bytes: 100, step: -1),
                                      current: snapshot(bytes: 500)),
           .progress(step: 50), "progress is reported at whole percent steps")
checkEqual(OfflineEventPlanner.decide(previous: snapshot(bytes: 500, step: 50),
                                      current: snapshot(bytes: 505)),
           .nothing, "⚠ a step already sent is not sent again — progress is throttled, state is not")
checkEqual(OfflineEventPlanner.decide(previous: snapshot(bytes: 100, step: 60),
                                      current: snapshot(bytes: 300)),
           .state, "⚠ progress that goes BACKWARDS is a restart, and a restart is seen")
checkEqual(OfflineEventPlanner.decide(previous: snapshot(state: .paused, bytes: 100, step: -1),
                                      current: snapshot(state: .paused, bytes: 400, step: -1)),
           .nothing, "a paused download reports no progress")
checkEqual(OfflineEventPlanner.decide(previous: snapshot(state: .ready, bytes: 1000, total: 1000),
                                      current: snapshot(state: .ready, bytes: 1000, total: 1000)),
           .nothing, "a ready title that has not changed says nothing")
checkEqual(OfflineEventPlanner.vanished(previous: ["b", "a", "c"], current: ["a"]), ["b", "c"],
           "⚠ a deleted title is announced, and in a deterministic order")

checkEqual(json(OfflineEventPayload.progress(itemId: "i1", bytes: 500, totalBytes: 1000, percent: 50)
                .jsonObject).contains("\"percent\":50"), true, "a progress event carries its percent")
checkEqual(json(OfflineEventPayload.ready(itemId: "i1", url: "http://127.0.0.1:1/offline/x.mp4",
                                          contentType: "video/mp4", bytes: 1000).jsonObject)
           .contains("\"e\":\"ready\""), true, "a ready event names itself")
checkEqual(json(OfflineEventPayload.state(itemId: "i1", title: "Heat", state: "failed", bytes: 0,
                                          totalBytes: 1000, mode: "auto", error: "gone", url: nil)
                .jsonObject).contains("\"error\":\"gone\""), true,
           "a state event carries the reason the user needs")

// MARK: - The cold-launch ladder (ADR-0012)

// ⚠ Why this is here and not in the app: with the Wi-Fi off the app has exactly ONE shot at the copy of
// the shell the device already holds. `ShellLaunchLadder` decides when that shot is spent and what
// happens after it fails — so it is pure, and these are the checks that fail when the rule goes.

section("cold launch")

checkEqual(ShellBootStep.allCases.map(\.label), ["fresh", "cached", "unreachable"],
           "⚠ the three steps have the spelling the log and the HUD use")

var ladder = ShellLaunchLadder()
checkEqual(ladder.step, .fresh, "a launch begins with the live app, never the cached copy")
checkEqual(ladder.step.asksCacheFirst, false, "the fresh attempt revalidates — a working network must always win")
checkEqual(ladder.step.loads, true, "the fresh step is an attempt, and it is the first one")

let refused = ShellBootFailure.transport("NSURLErrorDomain -1004 — Could not connect to the server")
let offline = ShellBootFailure.transport("NSURLErrorDomain -1009 — the internet connection appears to be offline")

checkEqual(ladder.next(after: .benignCancellation), .fresh,
           "⚠ a benign cancellation does NOT spend the cached attempt")
checkEqual(ladder.step, .fresh, "…and it does not move the ladder either")

checkEqual(ladder.next(after: refused), .cached, "a transport failure tries the device's own copy")
checkEqual(ladder.step.asksCacheFirst, true,
           "…and that step is the one that asks the cache to answer without the network")
checkEqual(ladder.next(after: .benignCancellation), .cached,
           "a benign cancellation at the cached step does not move it either")

checkEqual(ladder.next(after: offline), .unreachable,
           "when the cached copy cannot boot either, the app says so")
checkEqual(ladder.step.loads, false, "the unreachable step is a SCREEN — it loads nothing")
checkEqual(ladder.next(after: offline), .unreachable,
           "⚠ and it is terminal: a failure at unreachable stays unreachable, so there is no loop")

ladder.reset()
checkEqual(ladder.step, .fresh, "⚠ a new launch starts at the fresh attempt again — there is no stickiness")

// A whole launch, driven the way the app drives it: the live app refuses, the cached copy refuses.
var launch = ShellLaunchLadder()
launch.next(after: refused)
checkEqual(launch.next(after: offline), .unreachable, "two failures is the whole ladder")
launch.reset()
checkEqual(launch.next(after: refused), .cached, "…and the next launch gets its cached attempt back")

// MARK: - The app-owned shell's rules (ADR-0012 D7/D8 · plan §0c, phase S1)

// ⚠ Why these are here: the shell is a DOCUMENT plus the assets it names, kept by the app and handed to
// the page — so "which assets", "where do their URLs point" and "is the stored copy usable" are three
// decisions that decide whether a cold launch with no network paints the app, paints an empty page, or
// paints the WRONG app. Each rule below is reverted, one at a time, by `check-offline-core.py --falsify`.

section("shell store")

let shellDocument = """
<!doctype html><html><head>
<link rel="stylesheet" crossorigin href="/assets/index-DbZL-5sd.css">
<script type="module" crossorigin src="/assets/index-UZQ_BGxK.js"></script>
<link rel="icon" href="/favicon.svg">
<link href="https://fonts.googleapis.com/css2?family=Inter" rel="stylesheet">
</head><body><div id="root"></div></body></html>
"""

checkEqual(ShellStoreRules.requiredAssets(document: shellDocument),
           ["/assets/index-DbZL-5sd.css", "/assets/index-UZQ_BGxK.js"],
           "the document's own asset references, in document order")
checkEqual(ShellStoreRules.requiredAssets(document: shellDocument + shellDocument).count, 2,
           "an asset named twice is fetched once")
checkEqual(ShellStoreRules.requiredAssets(document: shellDocument).contains("/favicon.svg"), false,
           "a path outside /assets/ is not stored")
checkEqual(ShellStoreRules.requiredAssets(document: shellDocument,
                                         javascriptBodies: ["var p=\"/assets/chunk-9.js\";"]),
           ["/assets/index-DbZL-5sd.css", "/assets/index-UZQ_BGxK.js", "/assets/chunk-9.js"],
           "an asset named INSIDE the bundle is collected too (the day a build splits)")

for unsafe in ["/assets/../secret.js", "/assets/sub/dir.js", "/assets/", "/assets/x.txt", "/assets/.js",
               "/assets/index%2F..%2Fx.js",
               // ⚠⚠ THIS ONE IS HERE BECAUSE THE FALSIFICATION RUN FOUND THE TWO ABOVE WERE PASSING FOR
               // THE WRONG REASON. `../secret.js` contains a `/` and `%2F..%2Fx.js` contains `%`, so BOTH
               // are already refused by the character whitelist — reverting the traversal guard changed
               // nothing, which is a check that proves nothing. This name needs the `..` guard ITSELF: a
               // legal extension, legal characters, no separator, and a traversal inside it.
               "/assets/..js"] {
    checkEqual(ShellStoreRules.isStorableAssetPath(unsafe), false, "refuses \(unsafe) as a file name")
}
checkEqual(ShellStoreRules.isStorableAssetPath("/assets/index-UZQ_BGxK.js"), true,
           "a plain hashed bundle is a storable name")
// ⚠ And the same lesson for the PREFIX: `/favicon.svg` is refused by the extension whitelist too, so a
// check written with it cannot fail when the prefix guard goes. A `.js` outside `/assets/` is the case
// that needs the prefix rule and nothing else — drop the guard and `dropFirst` turns it into an asset.
checkEqual(ShellStoreRules.isStorableAssetPath("/static/index-abc.js"), false,
           "⚠ a .js OUTSIDE /assets/ is refused — the prefix is the rule, not the extension")

let shellRewritten = ShellStoreRules.rewritten(document: shellDocument, scheme: "rkm-asset")
check(shellRewritten.contains("\"rkm-asset://app/assets/index-UZQ_BGxK.js\""),
      "the script reference is pointed at the app")
check(shellRewritten.contains("\"rkm-asset://app/assets/index-DbZL-5sd.css\""),
      "and so is the stylesheet")
check(shellRewritten.contains("https://fonts.googleapis.com/css2?family=Inter"),
      "an external url is left alone")
checkEqual(ShellStoreRules.rewritten(document: shellRewritten, scheme: "rkm-asset"), shellRewritten,
           "⚠ the rewrite is idempotent — storing the rewritten document is safe")

// ⚠⚠ LOAD-BEARING AND EASY TO LOSE: the STORED document is already rewritten, and the store's pair rule
// reads the asset set back OUT of it (`WebShellModel.storedShellDocument`) — so the rewritten form must
// still name the same assets. If a rewrite ever hid them, `requiredAssets` would come back empty, the
// pair rule would be satisfied by nothing, and an incomplete store would render as the blank page this
// whole phase exists to fix.
checkEqual(ShellStoreRules.requiredAssets(document: ShellStoreRules.rewritten(document: shellDocument, scheme: "rkm-asset")),
           ShellStoreRules.requiredAssets(document: shellDocument),
           "the rewritten document still names the same assets")

let mixedDocument = "<script src=\"/assets/index-UZQ_BGxK.js\"></script><p>see /assets/index-UZQ_BGxK.js</p>"
let mixedRewritten = ShellStoreRules.rewritten(document: mixedDocument, scheme: "rkm-asset")
check(mixedRewritten.contains("<p>see /assets/index-UZQ_BGxK.js</p>"),
      "⚠ a bare mention in prose is NOT a reference")
check(mixedRewritten.contains("\"rkm-asset://app/assets/index-UZQ_BGxK.js\""),
      "…while the quoted reference still is")

let shellNeeds = ["/assets/index-UZQ_BGxK.js", "/assets/index-DbZL-5sd.css"]
let shellStored = ShellStoreManifest(
    serverAddress: "http://rkm-hp:8124",
    documentBytes: 1623,
    assets: shellNeeds.map { ShellStoredAsset(path: $0, bytes: 10) },
    storedAt: Date(timeIntervalSince1970: 1_758_000_000))

checkEqual(ShellStoreRules.choice(manifest: shellStored, requiredAssets: shellNeeds,
                                  serverAddress: "http://rkm-hp:8124"), .storedShell,
           "a complete store for THIS server is used")
checkEqual(ShellStoreRules.choice(manifest: nil, requiredAssets: shellNeeds,
                                  serverAddress: "http://rkm-hp:8124"), .cacheFirstURL,
           "no store at all degrades to the older behaviour")
checkEqual(ShellStoreRules.choice(manifest: shellStored, requiredAssets: shellNeeds,
                                  serverAddress: "http://other:8124"), .cacheFirstURL,
           "⚠ a store fetched from ANOTHER server is dropped, never rendered")
checkEqual(ShellStoreRules.choice(manifest: shellStored,
                                  requiredAssets: shellNeeds + ["/assets/missing.js"],
                                  serverAddress: "http://rkm-hp:8124"), .cacheFirstURL,
           "⚠ a document whose bundle is missing is NOT usable — that is the blank screen this fixes")
checkEqual(ShellStoreRules.choice(manifest: ShellStoreManifest(version: 99,
                                                               serverAddress: "http://rkm-hp:8124",
                                                               documentBytes: 1623,
                                                               assets: shellStored.assets,
                                                               storedAt: shellStored.storedAt),
                                  requiredAssets: shellNeeds,
                                  serverAddress: "http://rkm-hp:8124"), .cacheFirstURL,
           "a manifest from a NEWER build is refused, not decoded")
checkEqual(ShellStoreRules.choice(manifest: ShellStoreManifest(serverAddress: "http://rkm-hp:8124",
                                                               documentBytes: 0,
                                                               assets: shellStored.assets,
                                                               storedAt: shellStored.storedAt),
                                  requiredAssets: shellNeeds,
                                  serverAddress: "http://rkm-hp:8124"), .cacheFirstURL,
           "an empty stored document is not a shell")

// MARK: - Verdict

print("")
if failures.isEmpty {
    print("PASS — \(checks) checks, 0 failures")
    exit(0)
}
print("FAIL — \(checks) checks, \(failures.count) failure(s):")
for failure in failures { print("  · \(failure)") }
exit(1)
