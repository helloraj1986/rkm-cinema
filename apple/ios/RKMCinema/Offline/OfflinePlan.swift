import Foundation

// ⚠ FOUNDATION ONLY — see the header of `OfflineManifest.swift`. Everything in this file is a pure
// decision over numbers and strings, so it is compiled and exercised on Linux by
// `apple/scripts/check-offline-core.py`, and every rule below is falsified there by reverting it.

// MARK: - What the server told us

/// One response's meaning, from its status code alone.
///
/// ⚠ These six "not now" answers are the reason B1 pins them apart, and a downloader must react to
/// each differently (`backend/api/routes/offline.py::_raise_not_ready`):
///
/// * `404` — nothing was ever asked for: the device must `prepare` first, and retrying is pointless.
/// * `409` — **WAIT, it is still being built**: retry, and expect it to become `ready` shortly.
/// * `410` — the rendition's file is gone from the server: waiting cannot fix it.
/// * `416` — our byte offset is past the end (the artefact was replaced by a smaller one): start over.
/// * `401` — the session expired: the fix is a sign-in, not a retry.
/// * `507` — the server's own staging cap refused it: retrying changes nothing.
enum OfflineHTTPVerdict: Equatable {
    /// `200` or `206` — read the headers; this one is the caller's to interpret (`OfflineAssembly`).
    case success
    /// `409` — packaging in progress. Retryable, and the only status where "later" is the answer.
    case packaging
    /// `404` — never prepared.
    case neverPrepared
    /// `410` — the staged file is gone.
    case gone
    /// `416` — the range could not be satisfied; our offset is stale.
    case rangeNotSatisfiable
    /// `401` — the session is no longer valid.
    case signInRequired
    /// `403` — the server refuses this caller (profile, permission).
    case refused
    /// `507` — the server's storage cap, with the knob named in the detail.
    case storageFull
    /// `5xx` — the server is unwell; retry later, do not corrupt anything.
    case serverError
    case unexpected(Int)

    static func classify(_ status: Int) -> OfflineHTTPVerdict {
        switch status {
        case 200, 206: return .success
        case 401: return .signInRequired
        case 403: return .refused
        case 404: return .neverPrepared
        case 409: return .packaging
        case 410: return .gone
        case 416: return .rangeNotSatisfiable
        case 507: return .storageFull
        case 500...599: return .serverError
        default: return .unexpected(status)
        }
    }

    /// ⚠ Only three statuses are worth another attempt **on their own**, and this list is deliberately
    /// short: retrying a `404` or a `410` is a loop that never ends, and retrying a `401` fills the log
    /// with attempts while the actual fix (sign in again) sits waiting for a human.
    var isRetryable: Bool {
        switch self {
        case .packaging, .serverError: return true
        // A 416 is retryable ONLY because the retry restarts from zero — see `restartsFromZero`.
        case .rangeNotSatisfiable: return true
        default: return false
        }
    }

    /// ⚠ `416` and a whole-file answer both mean "throw the partial away". Stated as a property so the
    /// downloader cannot restart by accident anywhere else.
    var restartsFromZero: Bool {
        switch self {
        case .rangeNotSatisfiable: return true
        default: return false
        }
    }

    var needsSignIn: Bool { self == .signInRequired || self == .refused }

    /// What the Downloads screen (B4) and the HUD say. ⚠ A failure with no sentence is a failure the
    /// user cannot act on, and the reason the *status* is always spelled out here.
    func sentence(detail: String?) -> String {
        let suffix = (detail?.isEmpty == false) ? " (\(detail!))" : ""
        switch self {
        case .success: return "ok"
        case .packaging: return "The server is still packaging this title" + suffix
        case .neverPrepared: return "This title has not been prepared on the server yet"
        case .gone: return "The server no longer has the file for this title"
        case .rangeNotSatisfiable:
            return "The server rejected the resume point — the download will start again from the beginning"
        case .signInRequired: return "Sign in again to continue downloading"
        case .refused: return "The server refused this download" + suffix
        case .storageFull: return "The server's download storage is full" + suffix
        case .serverError: return "The server had an error" + suffix
        case .unexpected(let code): return "Unexpected answer from the server (HTTP \(code))" + suffix
        }
    }
}

/// What the device decided the server is offering — the shape `OfflineHTTPVerdict` + a `detail` takes.
enum OfflineRemoteReply: Equatable {
    case ready(OfflineRemoteArtefact)
    case packaging(String)
    case neverPrepared(String)
    case gone(String)
    case signInRequired(String)
    case refused(String)
    case failed(String)
    /// A retry may help, but nothing about the server changed: a dropped connection, a timeout.
    case transport(String)

    static func from(_ verdict: OfflineHTTPVerdict, detail: String?) -> OfflineRemoteReply {
        let sentence = verdict.sentence(detail: detail)
        switch verdict {
        case .success:
            // A caller that got here has no artefact to offer; it is a programming error, and it is
            // reported rather than assumed away.
            return .failed("Internal: a successful status with no artefact to describe")
        case .packaging: return .packaging(sentence)
        case .neverPrepared: return .neverPrepared(sentence)
        case .gone: return .gone(sentence)
        case .signInRequired: return .signInRequired(sentence)
        case .refused, .storageFull: return .refused(sentence)
        case .rangeNotSatisfiable: return .failed(sentence)
        case .serverError: return .failed(sentence)
        case .unexpected: return .failed(sentence)
        }
    }
}

/// A transport-level failure, mapped from an `NSError` by the iOS layer.
///
/// ⚠ Mapped, not passed through, so this file stays Foundation-only and (more usefully) so the
/// *decision* about what to do with a dropped connection is testable without a network.
enum OfflineTransportFailure: Equatable {
    case offline
    case timedOut
    case connectionLost
    /// The user cancelled, or we did. Never a retry.
    case cancelled
    case other(String)

    var isRetryable: Bool {
        switch self {
        case .cancelled: return false
        case .offline, .timedOut, .connectionLost, .other: return true
        }
    }

    var sentence: String {
        switch self {
        case .offline: return "No connection — the download will continue when the network is back"
        case .timedOut: return "The server did not answer in time"
        case .connectionLost: return "The connection dropped partway through"
        case .cancelled: return "Cancelled"
        case .other(let detail): return detail
        }
    }
}

/// The size and identity of the server's file, from a `HEAD` (or the headers of the first `GET`).
struct OfflineRemoteArtefact: Equatable {
    var size: Int64
    var etag: String?
    var contentType: String?

    init(size: Int64, etag: String? = nil, contentType: String? = nil) {
        self.size = size
        self.etag = etag
        self.contentType = contentType
    }
}

// MARK: - Is what we have the whole film?

/// How the "same bytes" claim was established. ⚠ It is recorded rather than assumed: "the size
/// matches" and "the size and the ETag match" are different strengths of proof, and a future bug
/// report that starts "it played a different edit" needs to know which one was in force.
enum OfflineReadyVerification: String, Codable, Equatable {
    /// Size equal AND the ETag equal — the strong claim, and what our own server always allows
    /// (`_file_headers` sends a strong `"size-mtime"` ETag; ADR-0007 D4: the artefact only ever
    /// changes by being replaced whole).
    ///
    /// ⚠ The raw values are EXPLICIT because they are a persisted file format (they land in
    /// `manifest.json`): an implicit raw value would change silently if a case were ever renamed, and a
    /// manifest written by the old build would then read back as `nil` — a `ready` row with no record of
    /// how it was verified.
    case sizeAndETag = "size_etag"
    /// The server sent no ETag. The size matched, so the file is very likely whole — but that is a
    /// weaker claim, it is logged as such, and it never upgrades an incomplete file.
    case sizeOnly = "size_only"

    var label: String {
        switch self {
        case .sizeAndETag: return "size+ETag"
        case .sizeOnly: return "size only (the server sent no ETag)"
        }
    }
}

enum OfflineCompletionCheck: Equatable {
    case complete(OfflineReadyVerification)
    case incomplete(reason: String)

    /// ⚠ The gate B1's own §4.7 wrote down: "never a half-file played as if complete (a size/ETag
    /// check gates `ready`)". Both halves must pass; a zero-byte file is never complete, however
    /// well the sizes agree.
    static func check(
        localBytes: Int64,
        localETag: String?,
        remote: OfflineRemoteArtefact
    ) -> OfflineCompletionCheck {
        guard remote.size > 0 else {
            return .incomplete(reason: "the server reports a zero-byte file")
        }
        guard localBytes == remote.size else {
            return .incomplete(reason: "\(localBytes) of \(remote.size) bytes on this device")
        }
        switch (localETag, remote.etag) {
        case let (local?, remote?):
            guard local == remote else {
                return .incomplete(reason: "the server's copy has changed since these bytes were fetched")
            }
            return .complete(.sizeAndETag)
        default:
            return .complete(.sizeOnly)
        }
    }
}

// MARK: - Resume

/// The one decision the downloader asks for before it fetches a byte.
enum OfflineResumeDecision: Equatable {
    /// Nothing local: get the whole thing.
    case fresh(total: Int64)
    /// Bytes on disk that belong to the server's current file: ask for the rest, from `fromOffset`.
    case resume(fromOffset: Int64, total: Int64)
    /// We already have all of it.
    case alreadyComplete(OfflineReadyVerification)
    /// A partial that cannot be continued (the server's copy changed, or it is bigger than the whole).
    /// The partial is discarded, and that is stated rather than done quietly.
    case restart(reason: String, total: Int64)
    /// `409` — the server is still packaging it. Wait, do not fail.
    case wait(reason: String)
    /// Nothing a retry can fix on its own.
    case unavailable(reason: String, kind: OfflineUnavailableKind)
}

enum OfflineUnavailableKind: Equatable {
    /// `404` — `POST /api/offline/prepare` has not been called for this title.
    case notPrepared
    /// `410` — the server's staged file is gone.
    case gone
    /// `401`/`403` — sign in again.
    case signInRequired
    /// `507`, a sanity failure such as a zero-byte artefact, and anything else terminal.
    case refused

    var label: String {
        switch self {
        case .notPrepared: return "not prepared"
        case .gone: return "gone"
        case .signInRequired: return "sign-in required"
        case .refused: return "refused"
        }
    }
}

enum OfflineResume {

    /// Pure: given what is on this device and what the server just said, what happens next.
    ///
    /// ⚠ The order of the checks below IS the rule, and each one exists because of a specific way a
    /// downloader corrupts a file:
    ///
    /// 1. **A zero-byte or negative server artefact is refused before anything else.** It would
    ///    otherwise make "0 bytes local, 0 bytes remote" read as *complete* — an empty file that
    ///    plays as nothing, which is worse than a failure.
    /// 2. **Completion is judged by ETag first, then size** — never by size alone when both sides
    ///    have an ETag, because a re-packaged rendition can land on exactly the same size.
    /// 3. **A changed ETag restarts rather than resumes.** Appending the tail of a *new* file to the
    ///    head of an *old* one produces a video that plays and is wrong for the rest of its length —
    ///    the single nastiest failure available here.
    /// 4. **A local file bigger than the server's is a restart**, not a trimmed resume.
    static func decide(
        localBytes: Int64,
        localETag: String?,
        remote: OfflineRemoteReply
    ) -> OfflineResumeDecision {
        switch remote {

        case .ready(let artefact):
            guard artefact.size > 0 else {
                return .unavailable(
                    reason: "The server reported a zero-byte download for this title.",
                    kind: .refused
                )
            }
            if case .complete(let verification) =
                OfflineCompletionCheck.check(localBytes: localBytes, localETag: localETag, remote: artefact) {
                return .alreadyComplete(verification)
            }
            guard localBytes > 0 else { return .fresh(total: artefact.size) }

            // ⚠ A partial whose ETag was never recorded cannot be proven to belong to the server's
            // current file, and the failure it would cause is a film that plays with a wrong seam for
            // the rest of its length. Losing nine minutes of transfer is the cheaper mistake, so the
            // safe direction is taken even though it costs real time.
            if localETag == nil {
                return .restart(
                    reason: "There are \(localBytes) bytes here with no record of which server file they came "
                          + "from, so the partial copy cannot be continued.",
                    total: artefact.size
                )
            }
            if let localETag, let remoteETag = artefact.etag, localETag != remoteETag {
                return .restart(
                    reason: "The server's copy of this title has changed since these bytes were fetched, "
                          + "so the part-downloaded file cannot be continued.",
                    total: artefact.size
                )
            }
            if localBytes > artefact.size {
                return .restart(
                    reason: "This device holds \(localBytes) bytes but the server's file is \(artefact.size) — "
                          + "the partial copy is not this file.",
                    total: artefact.size
                )
            }
            return .resume(fromOffset: localBytes, total: artefact.size)

        case .packaging(let reason):
            return .wait(reason: reason)

        case .neverPrepared(let reason):
            return .unavailable(reason: reason, kind: .notPrepared)
        case .gone(let reason):
            return .unavailable(reason: reason, kind: .gone)
        case .signInRequired(let reason):
            return .unavailable(reason: reason, kind: .signInRequired)
        case .refused(let reason):
            return .unavailable(reason: reason, kind: .refused)
        case .failed(let reason), .transport(let reason):
            // A transport failure says nothing about the server's file, so the LOCAL state stands:
            // the caller keeps its bytes and asks again later (`wait`), rather than restarting.
            return .wait(reason: reason)
        }
    }
}

// MARK: - Ranges

/// A parsed `Content-Range`. `bytes 100-199/1000` · `bytes */1000` (the `416` form).
enum OfflineRangeReport: Equatable {
    case bytes(start: Int64, end: Int64, total: Int64)
    case unsatisfiable(total: Int64)

    var total: Int64 {
        switch self {
        case .bytes(_, _, let total), .unsatisfiable(let total): return total
        }
    }

    /// ⚠ Strict on purpose, exactly like the server's own `parse_range`: a malformed or multi-range
    /// header returns `nil`, and the caller treats `nil` as "I cannot verify this response", never as
    /// "close enough". A `Content-Range` this device cannot read is a response it must not splice into
    /// a film.
    static func parse(_ value: String?) -> OfflineRangeReport? {
        guard let value else { return nil }
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard trimmed.hasPrefix("bytes") else { return nil }
        let rest = trimmed.dropFirst("bytes".count).trimmingCharacters(in: .whitespaces)
        let parts = rest.split(separator: "/", maxSplits: 1, omittingEmptySubsequences: false)
        guard parts.count == 2 else { return nil }
        guard let total = Int64(parts[1].trimmingCharacters(in: .whitespaces)) else { return nil }
        let span = parts[0].trimmingCharacters(in: .whitespaces)
        if span == "*" { return .unsatisfiable(total: total) }
        let bounds = span.split(separator: "-", maxSplits: 1, omittingEmptySubsequences: false)
        guard bounds.count == 2,
              let start = Int64(bounds[0].trimmingCharacters(in: .whitespaces)),
              let end = Int64(bounds[1].trimmingCharacters(in: .whitespaces)),
              start >= 0, end >= start, total > 0, end < total
        else { return nil }
        return .bytes(start: start, end: end, total: total)
    }

    /// The header this device sends for a resume. ⚠ Always open-ended (`bytes=N-`): the code asks for
    /// "everything from N", so the answer cannot disagree with the request about where it ends.
    static func requestHeader(fromOffset offset: Int64) -> String? {
        guard offset > 0 else { return nil }
        return "bytes=\(offset)-"
    }
}

// MARK: - Splicing what came back

/// What to do with the bytes a download task just produced.
enum OfflineAssemblyPlan: Equatable {
    /// Append the fragment at `offset` — the response really was the range that was asked for.
    case appendFragment(offset: Int64)
    /// The response is a whole file: it REPLACES the partial, whatever is in it. `discardedBytes` is
    /// how much was thrown away, so the log can say so instead of the size appearing to drop.
    case wholeFile(discardedBytes: Int64)
    /// The response cannot be trusted against the partial. Nothing is written; the caller decides
    /// whether to retry from zero (`416`) or give up.
    case refuse(reason: String)

    /// The size the finished file must have if this plan is carried out with a fragment of this size.
    func finalSize(fragmentBytes: Int64) -> Int64 {
        switch self {
        case .appendFragment(let offset): return offset + fragmentBytes
        case .wholeFile: return fragmentBytes
        case .refuse: return 0
        }
    }
}

enum OfflineAssembly {

    /// ⚠⚠ This is where a resume silently corrupts a film if it is wrong, so every branch is a check
    /// rather than a hope. The three failures it catches, all of which produce a file that *plays*:
    ///
    /// * a `206` whose `Content-Range` starts somewhere **other than the offset we asked for** — the
    ///   splice would put the wrong bytes at the seam;
    /// * a `206` whose `Content-Range` total **disagrees with the size `HEAD` reported** — the server's
    ///   file changed between the two calls, so the local partial belongs to a different file;
    /// * a `200` to a ranged request — the server ignored the `Range`, so the body is a whole file
    ///   from byte 0 and appending it would produce a file of exactly the wrong length.
    static func plan(
        status: Int,
        contentRange: String?,
        requestedOffset: Int64,
        localBytes: Int64,
        remoteSize: Int64
    ) -> OfflineAssemblyPlan {
        let verdict = OfflineHTTPVerdict.classify(status)
        guard verdict == .success else {
            return .refuse(reason: verdict.sentence(detail: nil))
        }

        if status == 200 {
            // Either we asked for the whole file (offset 0 — a fresh download, nothing to discard) or
            // the server ignored the range. Both mean: the fragment is the whole file.
            return .wholeFile(discardedBytes: requestedOffset > 0 ? localBytes : 0)
        }

        // 206. The range must agree with the request AND with the size HEAD reported.
        switch OfflineRangeReport.parse(contentRange) {
        case .bytes(let start, _, let total):
            guard start == requestedOffset else {
                return .refuse(
                    reason: "The server answered from byte \(start) after being asked from byte "
                          + "\(requestedOffset) — these bytes cannot be appended to what is already here."
                )
            }
            guard total == remoteSize else {
                return .refuse(
                    reason: "The server's file is now \(total) bytes but this download was planned against "
                          + "\(remoteSize) — the artefact changed underneath it."
                )
            }
            return .appendFragment(offset: requestedOffset)
        case .unsatisfiable:
            return .refuse(reason: "The server answered 206 with an unsatisfiable range.")
        case nil:
            return .refuse(
                reason: "The 206 response carried no readable Content-Range, so the bytes cannot be placed."
            )
        }
    }
}

// MARK: - Retry

/// How many times, and how long to wait.
///
/// ⚠ The delays are **deterministic** — no jitter. Jitter exists to protect a shared server from a
/// thundering herd; this is one device talking to one household server, and an untestable schedule is
/// a worse trade than a herd that does not exist. The schedule is generous because the *network* is a
/// tailnet: a relayed path (DERP) can stall for tens of seconds and recover, and the measured rate is
/// ≈3.8 MB/s, so a 2 GB film is a ~9-minute transfer that must survive one hiccup.
struct OfflineRetryPolicy: Equatable {

    /// Total attempts per download, including the first. 4 → at most 3 retries.
    var maximumAttempts: Int
    /// Delay before attempt 2, 3, 4 …; the last value repeats if `maximumAttempts` is raised.
    var delays: [TimeInterval]

    init(maximumAttempts: Int = 4, delays: [TimeInterval] = [3, 15, 60, 180]) {
        self.maximumAttempts = maximumAttempts
        self.delays = delays
    }

    static let `default` = OfflineRetryPolicy()

    /// Seconds to wait before `attempt` (1-based = the attempt about to be made), or `nil` when the
    /// download has had its last attempt. ⚠ `nil` is the ONLY way a download ends quietly, so every
    /// caller has to make that decision explicitly.
    func delay(beforeAttempt attempt: Int) -> TimeInterval? {
        guard attempt >= 1, attempt < maximumAttempts else { return nil }
        let index = min(attempt - 1, delays.count - 1)
        guard index >= 0, !delays.isEmpty else { return nil }
        return delays[index]
    }

    func hasAttemptsLeft(afterAttempt attempt: Int) -> Bool { delay(beforeAttempt: attempt + 1) != nil }
}

/// A download's failure, as the downloader sees it: a status verdict, a transport failure, or a
/// local problem (no space, an unreadable part file). One type, so the retry question has one answer.
enum OfflineFailure: Equatable {
    case http(OfflineHTTPVerdict)
    case transport(OfflineTransportFailure)
    /// ⚠ Never retried automatically: the device needs attention (no space, a refused id), and a
    /// retry loop over a full disk is how a home screen fills with spinners.
    case local(String)

    var isRetryable: Bool {
        switch self {
        case .http(let verdict): return verdict.isRetryable
        case .transport(let failure): return failure.isRetryable
        case .local: return false
        }
    }

    var needsSignIn: Bool {
        switch self {
        case .http(let verdict): return verdict.needsSignIn
        case .transport, .local: return false
        }
    }

    /// ⚠ A retry that restarts from zero has to be *stated*, because it throws away bytes that may
    /// have taken ten minutes to arrive.
    var restartsFromZero: Bool {
        switch self {
        case .http(let verdict): return verdict.restartsFromZero
        case .transport, .local: return false
        }
    }

    var sentence: String {
        switch self {
        case .http(let verdict): return verdict.sentence(detail: nil)
        case .transport(let failure): return failure.sentence
        case .local(let reason): return reason
        }
    }
}

// MARK: - Dungarees for the logged output

/// Formatting for the log lines this feature writes. ⚠ Kept next to the rules so a size or a
/// percentage reads identically in the HUD and in the file — `LOGGING.md` §2 is a promise that a
/// screenshot and the log agree.
enum OfflineFormat {

    /// `1.88 GB` · `834 MB` · `12.4 MB` · `0 B`.
    static func bytes(_ value: Int64) -> String {
        let units: [(String, Double)] = [("TB", 1e12), ("GB", 1e9), ("MB", 1e6), ("KB", 1e3)]
        for (name, scale) in units where Double(value) >= scale {
            return String(format: "%.2f %@", Double(value) / scale, name)
        }
        return "\(value) B"
    }

    /// `41%` · `—` when the total is not known (never a fake 0%).
    static func percent(_ fraction: Double?) -> String {
        guard let fraction else { return "—" }
        return String(format: "%.0f%%", fraction * 100)
    }

    /// `9m 30s` · `45s` — an ETA, from a byte rate in bytes/second.
    static func eta(remainingBytes: Int64, bytesPerSecond: Double) -> String? {
        guard bytesPerSecond > 0, remainingBytes > 0 else { return nil }
        let seconds = Double(remainingBytes) / bytesPerSecond
        if seconds < 60 { return String(format: "%.0fs", seconds) }
        let minutes = Int(seconds) / 60
        return "\(minutes)m \(Int(seconds) % 60)s"
    }
}
