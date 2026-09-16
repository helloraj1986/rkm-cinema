import Foundation
import UIKit
import Combine
import RKMServerKit

// Phase B2: the device half of offline downloads — `NATIVE_FEEL_AND_OFFLINE_PLAN.md` §4.4, gate:
//
//   "Downloads complete with the app backgrounded, resume after a forced failure, and appear in the
//    manifest after a relaunch."
//
// The four decisions this file makes, and why each is shaped that way:
//
//  1. **A BACKGROUND `URLSession`, one task per item.** Only a background session keeps transferring
//     while the app is suspended or gone; a foreground session stops at the suspension boundary and
//     the film never arrives. `sessionSendsLaunchEvents = true` is what has the system relaunch the app
//     to hand over the result (`AppDelegate.handleEventsForBackgroundURLSession`).
//  2. **The cookie is attached EXPLICITLY** (from `CookieMirror`) and the session is told not to touch
//     cookies at all. A background session's own cookie handling is documented to lose cookies on
//     redirects, and a silent cookie loss is a mystery 401 at the worst possible moment.
//  3. **All the arithmetic is in `OfflinePlan.swift`,** which is compiled and falsified on Linux. This
//     file is the machinery that carries those decisions out — offsets, retries, files, logs.
//  4. **The manifest is an index; the filesystem is the truth.** Progress is held in memory and
//     persisted only at real state changes, because `bytes` can always be re-derived from the `.part`
//     file's size — the one thing that cannot be re-derived is a state, so only states are written often.

/// One row as the UI (and the HUD's debug panel) shows it.
struct OfflineRow: Identifiable, Equatable {
    var itemId: String
    var title: String
    var mode: String
    var state: OfflineState
    var bytes: Int64
    var totalBytes: Int64
    var bytesPerSecond: Double
    var attempt: Int
    var verification: OfflineReadyVerification?
    /// A progress sentence that is NOT an error — "the server is packaging it (1.2 GB so far)".
    var note: String?
    var lastError: String?

    var id: String { itemId }

    var fraction: Double? {
        guard totalBytes > 0 else { return nil }
        return min(1, max(0, Double(bytes) / Double(totalBytes)))
    }

    var eta: String? {
        OfflineFormat.eta(remainingBytes: max(0, totalBytes - bytes), bytesPerSecond: bytesPerSecond)
    }

    var progressLine: String {
        var parts = [state.label]
        parts.append("\(OfflineFormat.bytes(bytes))"
                     + (totalBytes > 0 ? " / \(OfflineFormat.bytes(totalBytes))" : ""))
        if let fraction { parts.append(OfflineFormat.percent(fraction)) }
        if bytesPerSecond > 0, state == .downloading { parts.append(String(format: "%.1f MB/s", bytesPerSecond / 1e6)) }
        if let eta, state == .downloading { parts.append("eta \(eta)") }
        if attempt > 1 { parts.append("attempt \(attempt)") }
        if let verification, state == .ready { parts.append("verified \(verification.label)") }
        if let note { parts.append(note) }
        if let lastError { parts.append("⚠ \(lastError)") }
        return parts.joined(separator: " · ")
    }

    init(record: OfflineRecord) {
        itemId = record.itemId
        title = record.title.isEmpty ? record.itemId : record.title
        mode = record.mode
        state = record.state
        bytes = record.bytes
        totalBytes = record.totalBytes
        bytesPerSecond = 0
        attempt = record.attempts
        note = nil
        lastError = record.lastError
    }
}

/// What is known about a running task, so a delegate callback can act without re-asking the server.
/// ⚠ `etag` and `total` are carried because a task RESTORED AFTER A RELAUNCH has no local variables —
/// only its `taskDescription` — and a resumed download without the ETag cannot be checked for a changed
/// artefact (`OfflinePlan.decide` needs both sides).
private struct OfflineTaskContext {
    var itemId: String
    var title: String
    var mode: String
    var container: String?
    var remote: OfflineRemoteArtefact
    /// The offset the request asked from: the partial size at request time.
    var offset: Int64
    var attempt: Int
    var correlation: CorrelationID
    var startedAt: Date
    var fragmentBytes: Int64
    var sampleAt: Date
    var sampleBytes: Int64
    var bytesPerSecond: Double
    var lastLoggedTenth: Int

    init(itemId: String, title: String, mode: String, container: String?,
         remote: OfflineRemoteArtefact, offset: Int64, attempt: Int, correlation: CorrelationID) {
        self.itemId = itemId
        self.title = title
        self.mode = mode
        self.container = container
        self.remote = remote
        self.offset = offset
        self.attempt = attempt
        self.correlation = correlation
        self.startedAt = Date()
        self.fragmentBytes = 0
        self.sampleAt = Date()
        self.sampleBytes = 0
        self.bytesPerSecond = 0
        self.lastLoggedTenth = -1
    }
}

final class OfflineDownloads: NSObject, ObservableObject {

    // ⚠⚠ A SHARED instance, deliberately — and it is the only justified singleton in this codebase
    // besides `RKMLog.shared`. The reason is a lifecycle fact, not convenience: iOS delivers
    // `handleEventsForBackgroundURLSession` to the **application delegate**, which may run before any
    // window or view exists (the system relaunches the app in the background just to hand over a
    // finished download). If the session and its store lived inside a view model, that event would
    // arrive with nothing to hand it to — and the relaunch would look like "the download vanished".
    static let shared = OfflineDownloads()

    /// ⚠ Must be STABLE across launches — the system matches a relaunch to the session by this string.
    /// Derived from the bundle id so it can never drift from the app that owns it.
    static var sessionIdentifier: String {
        (Bundle.main.bundleIdentifier ?? "com.helloraj1986.rkmcinema.ios") + ".offline"
    }

    private static let wifiOnlyKey = "rkm.offline.wifiOnly"
    private static let autoResumeKey = "rkm.offline.autoResume"

    // MARK: - Published state

    @Published private(set) var rows: [OfflineRow] = []
    @Published private(set) var candidates: [OfflineCandidate] = []
    @Published private(set) var libraryError: String?
    @Published private(set) var isLoadingCandidates = false
    @Published private(set) var isConfigured = false
    @Published private(set) var storeProblem: String?
    @Published var wifiOnly: Bool {
        didSet { UserDefaults.standard.set(wifiOnly, forKey: Self.wifiOnlyKey) }
    }
    @Published var autoResume: Bool {
        didSet { UserDefaults.standard.set(autoResume, forKey: Self.autoResumeKey) }
    }

    // MARK: - Machinery

    let cookies = CookieMirror()

    private(set) var store: OfflineStore?
    private var api: OfflineAPI?
    private var session: URLSession!

    private let lock = NSLock()
    private var contexts: [Int: OfflineTaskContext] = [:]
    private var taskIdentifiers: [String: Int] = [:]
    private var backgroundCompletion: (() -> Void)?
    private var cookieMirrorStarted = false
    private var restored = false

    private let retry = OfflineRetryPolicy.default
    private let preparation = OfflinePreparationPolicy()

    override init() {
        // ⚠ Read BEFORE the configuration is built: the session's `allowsCellularAccess` is a
        // per-session default, and a task's own value overrides it (`beginTask` sets both).
        let storedWiFiOnly = UserDefaults.standard.bool(forKey: Self.wifiOnlyKey)
        wifiOnly = storedWiFiOnly
        autoResume = UserDefaults.standard.object(forKey: Self.autoResumeKey) as? Bool ?? true
        super.init()

        let configuration = URLSessionConfiguration.background(withIdentifier: Self.sessionIdentifier)
        // ⚠ The three flags that decide whether a background transfer behaves:
        //  * `sessionSendsLaunchEvents` — relaunch the app to deliver the result (without it a finished
        //    download can sit unclaimed until the user opens the app).
        //  * `isDiscretionary = false` — a film the user asked for starts now, not when iOS decides the
        //    phone is idle and charging.
        //  * `allowsCellularAccess` — the Wi-Fi-only preference, default off.
        configuration.sessionSendsLaunchEvents = true
        configuration.isDiscretionary = false
        configuration.allowsCellularAccess = !storedWiFiOnly
        // ⚠ The session must NOT have its own opinion about cookies — `CookieMirror` + an explicit
        // `Cookie:` header is the single source (see the note in `CookieMirror`).
        configuration.httpShouldSetCookies = false
        configuration.httpCookieAcceptPolicy = .never
        configuration.httpCookieStorage = nil
        configuration.timeoutIntervalForRequest = 60
        // A 2 GB film over a relayed tailnet is ≈9 minutes at the measured 3.8 MB/s; six hours is the
        // "the tailnet stalled and recovered" allowance, not a target.
        configuration.timeoutIntervalForResource = 6 * 3600

        session = URLSession(configuration: configuration, delegate: self, delegateQueue: nil)

        openStore()

        RKMLog.info("offline session ready · id \(Self.sessionIdentifier) · wifiOnly=\(storedWiFiOnly) "
                    + "· autoResume=\(autoResume) · store=\(store == nil ? "UNAVAILABLE" : "open")",
                    category: .offline)
    }

    // MARK: - Opening the store

    private func openStore() {
        do {
            let layout = OfflineLayout(root: try OfflineLayout.defaultRoot())
            let store = OfflineStore(layout: layout)
            try store.open()
            self.store = store
        } catch {
            storeProblem = "The offline store could not be opened: \(error.localizedDescription)"
            RKMLog.error(storeProblem ?? "offline store error", category: .offline)
        }
    }

    // MARK: - Wiring to the shell

    /// Called when the shell knows which server it is talking to. Idempotent per address.
    func configure(address: ServerAddress) {
        api = OfflineAPI(address: address, cookies: cookies)
        if !cookieMirrorStarted {
            cookieMirrorStarted = true
            // ⚠ Starts the observer, which is how signing in inside the page reaches the native side
            // with no page change at all (`CookieMirror`).
            cookies.start()
        }
        isConfigured = true
        guard !restored else { return }
        restored = true
        restore()
        applyLaunchArguments()
    }

    /// ⚠ DEV-PHASE HOOK, and the reason the Mac round can be ONE command. B2 is the downloader and B4 has
    /// the buttons, so without this the phase's own gate would need a GUI session of tapping before
    /// anything could be measured. Two scheme arguments, both read by `UserDefaults` automatically:
    ///
    ///     -RKMOfflineItem <item-id>   start this title as soon as the shell has an address
    ///     -RKMOfflinePick YES         download the FIRST title the library returns
    ///
    /// ⚠ `-RKMOfflinePick` downloads whatever comes first, which on this household's library could be a
    /// 40 GB film. It exists for a smoke test; the HUD panel is how a *chosen* title is started.
    private func applyLaunchArguments() {
        let defaults = UserDefaults.standard
        if let itemId = defaults.string(forKey: "RKMOfflineItem"), !itemId.isEmpty {
            RKMLog.info("offline launch argument -RKMOfflineItem: starting \(itemId) now", category: .offline)
            start(itemId: itemId, title: itemId)
            return
        }
        guard defaults.bool(forKey: "RKMOfflinePick") else { return }
        Task { [weak self] in
            guard let self, let api = self.api else { return }
            do {
                let candidates = try await api.candidates(limit: 1)
                guard let first = candidates.first else {
                    RKMLog.error("offline -RKMOfflinePick found no library items to download — is the "
                                 + "library empty, or is this profile signed out?", category: .offline)
                    return
                }
                RKMLog.info("offline launch argument -RKMOfflinePick chose \"\(first.title)\"", category: .offline)
                self.start(itemId: first.itemId, title: first.title)
            } catch {
                let sentence = (error as? OfflineAPIError)?.errorDescription ?? error.localizedDescription
                RKMLog.error("offline -RKMOfflinePick could not list the library: \(sentence)", category: .offline)
            }
        }
    }

    // MARK: - Starting a download

    /// The whole pipeline, for one title: plan → package → size → decide → download.
    func start(itemId: String, title: String, mode: String = "auto", attempt: Int = 1) {
        Task { await run(itemId: itemId, title: title, mode: mode, attempt: attempt) }
    }

    @discardableResult
    func run(itemId: String, title: String, mode: String, attempt: Int) async -> Bool {
        guard let api, let store else {
            problem("The offline store is not available, so nothing can be downloaded.")
            return false
        }
        guard taskIdentifier(for: itemId) == nil else {
            RKMLog.info("offline download already running for this title — ignoring the second request",
                        category: .offline)
            return false
        }

        let correlation = CorrelationID.next()
        RKMLog.info("offline download requested · \"\(title)\" · mode \(mode) · attempt \(attempt)",
                    category: .offline, correlation: correlation)

        // ⚠ The preparation phase (bundle → prepare → poll → HEAD) runs in OUR process, so if the user
        // backgrounds the app during it, iOS would suspend us. The transfer itself does not need this
        // — a background session lives in a system process — but the wait for a packaging job does.
        let assertion = BackgroundAssertion(name: "offline-prepare")
        defer { assertion.end() }

        do {
            let record = try await plan(itemId: itemId, title: title, mode: mode, api: api, store: store,
                                        attempt: attempt, correlation: correlation)

            // The one place a download is turned into a task.
            let fileURL = try requireFileURL(api: api, itemId: itemId, mode: record.stored.mode)
            let partialBytes = store.partialSize(itemId, container: record.container)

            let decision = OfflineResume.decide(
                localBytes: partialBytes,
                localETag: record.stored.etag,
                remote: .ready(record.remoteArtefact)
            )
            switch decision {

            case .alreadyComplete(let verification):
                // The bytes were already here and still match: no transfer at all.
                var stored = record.stored
                stored.bytes = record.remoteArtefact.size
                stored.state = .ready
                stored.downloadedAt = stored.downloadedAt ?? Date()
                stored.lastError = nil
                stored.verification = verification
                try store.upsert(stored)
                RKMLog.info("offline already complete on this device — nothing fetched (\(verification.label))",
                            category: .offline, correlation: correlation)
                publish()
                return true

            case .unavailable(let reason, let kind):
                RKMLog.error("offline cannot download this title · \(kind.label) · \(reason)",
                             category: .offline, correlation: correlation)
                try fail(record: record, reason: reason, store: store, correlation: correlation)
                return false

            case .wait(let reason):
                // A transport hiccup: keep every byte, and let the retry schedule do the waiting.
                try pause(record: record, note: reason, store: store)
                scheduleRetry(itemId: itemId, title: record.stored.title, mode: record.stored.mode, attempt: attempt)
                return false

            case .restart(let reason, let total):
                RKMLog.info("offline restarting from zero — \(reason) (was \(OfflineFormat.bytes(partialBytes)))",
                            category: .offline, correlation: correlation)
                _ = try? store.discardPartial(itemId, container: record.container)
                try beginTask(record: record, remote: record.remoteArtefact, total: total, offset: 0,
                              fileURL: fileURL, attempt: attempt, correlation: correlation, store: store)
                return true

            case .fresh(let total):
                try beginTask(record: record, remote: record.remoteArtefact, total: total, offset: 0,
                              fileURL: fileURL, attempt: attempt, correlation: correlation, store: store)
                return true

            case .resume(let offset, let total):
                RKMLog.info("offline resuming from \(OfflineFormat.bytes(offset)) of \(OfflineFormat.bytes(total))",
                            category: .offline, correlation: correlation)
                try beginTask(record: record, remote: record.remoteArtefact, total: total, offset: offset,
                              fileURL: fileURL, attempt: attempt, correlation: correlation, store: store)
                return true
            }

        } catch let error as OfflineAPIError {
            handle(error.failure, itemId: itemId, title: title, mode: mode, attempt: attempt, correlation: correlation)
            return false
        } catch {
            handle(OfflineTransportFailure.other("\(error)").asFailure, itemId: itemId, title: title,
                   mode: mode, attempt: attempt, correlation: correlation)
            return false
        }
    }

    /// A working record plus everything the next step needs. Local type: it exists so `run` can stay
    /// readable and so the stored record is never half-updated.
    private struct PlannedRecord {
        var stored: OfflineRecord
        var remoteArtefact: OfflineRemoteArtefact
        var container: String?
    }

    /// Plan → package → size. The three server calls, in the order B1's contract intends.
    private func plan(itemId: String, title: String, mode: String, api: OfflineAPI, store: OfflineStore,
                      attempt: Int, correlation: CorrelationID) async throws -> PlannedRecord {
        let bundle = try await api.bundle(itemId: itemId, mode: mode)
        let container = bundle.container
        let effectiveMode = bundle.mode.isEmpty ? mode : bundle.mode

        var record = store.record(itemId) ?? OfflineRecord(itemId: itemId,
                                                          title: bundle.title.isEmpty ? title : bundle.title,
                                                          mode: effectiveMode,
                                                          container: container)
        record.title = bundle.title.isEmpty ? (record.title.isEmpty ? title : record.title) : bundle.title
        record.mode = effectiveMode
        record.container = container
        record.borrowed = bundle.borrowed
        record.attempts = attempt
        record.state = .downloading
        record.lastError = nil
        record.bytes = store.diskState(itemId, container: container).partialBytes ?? 0
        try store.upsert(record)
        publish()

        RKMLog.info("offline plan · mode \(effectiveMode)"
                    + (bundle.needsTranscode ? " (transcode required)" : " (direct-playable)")
                    + " · estimate \(OfflineFormat.bytes(bundle.estimateBytes ?? 0))"
                    + " · server state \(bundle.state)", category: .offline, correlation: correlation)

        try await ensurePackaged(itemId: itemId, mode: effectiveMode, api: api, store: store,
                                 correlation: correlation)

        let artefact = try await api.head(itemId: itemId, mode: effectiveMode)
        RKMLog.info("offline artefact · \(OfflineFormat.bytes(artefact.size)) · "
                    + "etag \(artefact.etag ?? "none") · \(artefact.contentType ?? "unknown type")",
                    category: .offline, correlation: correlation)

        record.totalBytes = artefact.size
        record.etag = artefact.etag
        record.contentType = artefact.contentType
        record.borrowed = bundle.borrowed
        try store.upsert(record)
        publish()
        return PlannedRecord(stored: record, remoteArtefact: artefact, container: container)
    }

    /// `prepare`, then wait for it if the server is still packaging.
    ///
    /// ⚠ The two answers are different and both are handled: `404`/`410` from `prepare` mean the TITLE is
    /// not packageable (a real failure), while `state: packaging` means **wait** — a remux of a large film
    /// takes minutes of server-side copying, and the device shows that as progress, not as an error.
    private func ensurePackaged(itemId: String, mode: String, api: OfflineAPI, store: OfflineStore,
                                correlation: CorrelationID) async throws {
        var manifest = try await api.prepare(itemId: itemId, mode: mode)
        if manifest.reused == true {
            RKMLog.info("offline prepare was idempotent — the server returned the existing artefact",
                        category: .offline, correlation: correlation)
        }

        var waited: TimeInterval = 0
        var round = 0
        while manifest.state == OfflineServerState.packaging {
            let delay = preparation.pollDelay(round: round)
            guard waited + delay <= preparation.maximumWait else {
                throw OfflineAPIError.remote(.packaging, detail: "still packaging after "
                                                + "\(Int(preparation.maximumWait / 60)) minutes")
            }
            note(itemId: itemId, "waiting for the server to package it "
                 + "(\(OfflineFormat.bytes(manifest.size)) so far)")
            try await Task.sleep(for: .seconds(delay))
            waited += delay
            round += 1
            manifest = try await api.status(itemId: itemId, mode: manifest.mode)
            RKMLog.verbose("offline packaging · \(manifest.state) · "
                           + "\(OfflineFormat.bytes(manifest.size)) after \(Int(waited))s",
                           category: .offline, correlation: correlation)
        }

        note(itemId: itemId, nil)

        guard manifest.state == OfflineServerState.ready else {
            // ⚠ `failed` and `missing` are the server being honest about its own disk — reported with the
            // server's own sentence, never a spinner over nothing (the B1 ADR's D7).
            throw OfflineAPIError.remote(.gone, detail: manifest.error
                                         ?? "the server reports this title as \(manifest.state)")
        }
    }

    // MARK: - The task

    private func beginTask(record: PlannedRecord, remote: OfflineRemoteArtefact, total: Int64, offset: Int64,
                           fileURL: URL, attempt: Int, correlation: CorrelationID, store: OfflineStore) throws {
        var request = try requireAPI().makeDownloadRequest(itemId: record.stored.itemId,
                                                           mode: record.stored.mode,
                                                           fromOffset: offset,
                                                           fileURL: fileURL)
        request.allowsCellularAccess = !wifiOnly

        let task = session.downloadTask(with: request)
        task.taskDescription = Self.encodeTaskDescription(record.stored.itemId, mode: record.stored.mode,
                                                          container: record.container, offset: offset,
                                                          total: total, etag: remote.etag)

        var context = OfflineTaskContext(itemId: record.stored.itemId, title: record.stored.title,
                                         mode: record.stored.mode, container: record.container,
                                         remote: remote, offset: offset, attempt: attempt,
                                         correlation: correlation)
        context.fragmentBytes = 0

        lock.lock()
        contexts[task.taskIdentifier] = context
        taskIdentifiers[record.stored.itemId] = task.taskIdentifier
        lock.unlock()

        task.resume()
        RKMLog.info("offline task started · task \(task.taskIdentifier) · "
                    + (offset > 0 ? "resuming at \(OfflineFormat.bytes(offset))" : "from byte 0")
                    + " · \(OfflineFormat.bytes(total)) total"
                    + " · wifiOnly=\(wifiOnly)",
                    category: .offline, correlation: correlation)
        publish()
    }

    // MARK: - Control

    /// Stop downloading but KEEP what arrived — a cancel is not a delete, and the partial is what makes
    /// "resume" mean something tomorrow.
    func cancel(itemId: String) {
        guard let identifier = taskIdentifier(for: itemId) else { return }
        session.getAllTasks { tasks in
            for task in tasks where task.taskIdentifier == identifier { task.cancel() }
        }
        RKMLog.info("offline download cancelled by the user — the bytes so far are kept", category: .offline)
    }

    /// Retry a stopped row, from where it stopped.
    func retry(itemId: String) {
        guard let record = store?.record(itemId) else { return }
        start(itemId: itemId, title: record.title, mode: record.mode, attempt: record.attempts + 1)
    }

    /// ⚠ Delete is the ONLY destructive action here, and it removes the DEVICE's copy only — the server's
    /// artefact and the household's media file are not this app's to delete from here (ADR-0007 D2).
    func delete(itemId: String) {
        cancel(itemId: itemId)
        do {
            try store?.removeFiles(itemId)
            try store?.removeRecord(itemId)
            RKMLog.info("offline download deleted from this device", category: .offline)
        } catch {
            RKMLog.error("offline delete failed: \(error.localizedDescription)", category: .offline)
        }
        publish()
    }

    // MARK: - The debug panel's data

    func refreshCandidates() {
        guard let api else { return }
        isLoadingCandidates = true
        Task {
            do {
                let items = try await api.candidates(limit: 12)
                await MainActor.run {
                    self.candidates = items
                    self.libraryError = items.isEmpty ? "the library returned no items" : nil
                    self.isLoadingCandidates = false
                }
            } catch {
                let sentence = (error as? OfflineAPIError)?.errorDescription ?? error.localizedDescription
                await MainActor.run {
                    self.candidates = []
                    self.libraryError = sentence
                    self.isLoadingCandidates = false
                }
            }
        }
    }

    /// For the HUD's own field — the same one-line-per-item text the file log carries.
    private(set) var hudRows: [String] {
        if let storeProblem { return ["⚠ \(storeProblem)"] }
        guard store != nil else { return ["offline store unavailable"] }
        let ordered = store?.newestFirst ?? []
        if ordered.isEmpty { return ["no downloads"] }
        return ordered.map { record in
            rows.first(where: { $0.itemId == record.itemId })?.progressLine
                ?? OfflineRow(record: record).progressLine
        }
    }

    // MARK: - Launch restore

    /// ⚠ The relaunch story, in one method, because this is what the phase's gate asks for: a download
    /// that was interrupted by the app being stopped must be FOUND and CONTINUED, not silently forgotten.
    ///
    /// 1. Ask the session for its tasks. A background session outlives the process, so a transfer that was
    ///    running when the app died is still running here — re-attached by `taskDescription`, because a
    ///    restored task carries no Swift context.
    /// 2. Any record left in `downloading` with no live task was interrupted by a force-quit (iOS stops
    ///    background tasks on force-quit by design, §4.7). It is marked paused and, if auto-resume is on,
    ///    started again — from its own partial, via `Range`.
    private func restore() {
        guard let store else { return }

        session.getAllTasks { [weak self] tasks in
            guard let self else { return }
            var live: Set<String> = []
            for case let task as URLSessionDownloadTask in tasks {
                guard let description = task.taskDescription,
                      let decoded = Self.decodeTaskDescription(description) else { continue }
                live.insert(decoded.itemId)

                var context = OfflineTaskContext(itemId: decoded.itemId, title: decoded.title ?? decoded.itemId,
                                                 mode: decoded.mode, container: decoded.container,
                                                 remote: OfflineRemoteArtefact(size: decoded.total ?? 0,
                                                                               etag: decoded.etag),
                                                 offset: decoded.offset, attempt: 1,
                                                 correlation: CorrelationID.next())
                context.fragmentBytes = task.countOfBytesReceived
                context.sampleBytes = task.countOfBytesReceived
                self.lock.lock()
                self.contexts[task.taskIdentifier] = context
                self.taskIdentifiers[decoded.itemId] = task.taskIdentifier
                self.lock.unlock()

                RKMLog.info("offline RELAUNCH: task \(task.taskIdentifier) is still running for one title · "
                            + "\(OfflineFormat.bytes(task.countOfBytesReceived)) of "
                            + "\(OfflineFormat.bytes(task.countOfBytesExpectedToReceive))",
                            category: .offline)
            }

            // Records the session knows nothing about.
            for var record in store.records where !live.contains(record.itemId) {
                switch record.state {
                case .downloading:
                    record.state = .paused
                    record.lastError = record.bytes > 0
                        ? "The app was stopped while downloading — resuming continues from here."
                        : "The download did not start."
                    try? store.upsert(record)
                    RKMLog.info("offline RELAUNCH: one interrupted download found "
                                + "(\(OfflineFormat.bytes(record.bytes)) on disk, state \(record.state.label), "
                                + "attempts \(record.attempts))", category: .offline)
                case .ready, .paused, .failed:
                    break   // reconciled from disk by the store already
                }
            }

            // Interactive rows first, then the automatic continuation.
            self.publish()

            guard self.autoResume else { return }
            for record in store.records where record.state == .paused && record.bytes > 0 {
                // ⚠ Deliberately NOT every paused row: only the ones that were interrupted mid-transfer
                // carry the "app was stopped" sentence. A row the user cancelled stays cancelled until
                // they tap it — auto-resuming that would undo a deliberate action.
                guard (record.lastError ?? "").hasPrefix("The app was stopped") else { continue }
                RKMLog.info("offline RELAUNCH: resuming an interrupted download automatically",
                            category: .offline)
                self.start(itemId: record.itemId, title: record.title, mode: record.mode,
                           attempt: record.attempts + 1)
            }

            if let stuck = store.records.first(where: { $0.state == .failed }) {
                RKMLog.verbose("offline relaunch: \(stuck.itemId) is failed and stays failed until retried",
                               category: .offline)
            }
        }
    }

    /// Called by `AppDelegate` — the system relaunched the app to hand over session events.
    func setBackgroundCompletionHandler(_ handler: @escaping () -> Void) {
        lock.lock()
        let previous = backgroundCompletion
        backgroundCompletion = handler
        lock.unlock()
        if previous != nil {
            // ⚠ Replacing a handler without calling it hangs the system's bookkeeping for this session,
            // which shows up as "background downloads stopped working" several rounds later. Loud, once.
            RKMLog.error("offline background completion handler replaced without being called — "
                         + "calling the stale one to keep the system's accounting correct", category: .offline)
            previous?()
        }
        RKMLog.info("offline background events incoming — the system relaunched the app for session "
                    + "\(Self.sessionIdentifier)", category: .offline)
    }

    // MARK: - Internals

    private func requireAPI() throws -> OfflineAPI {
        guard let api else { throw OfflineAPIError.notConfigured }
        return api
    }

    private func requireFileURL(api: OfflineAPI, itemId: String, mode: String) throws -> URL {
        guard let url = api.fileURL(itemId: itemId, mode: mode) else {
            throw OfflineAPIError.unexpectedBody("could not build the file URL")
        }
        return url
    }

    private func taskIdentifier(for itemId: String) -> Int? {
        lock.lock()
        defer { lock.unlock() }
        return taskIdentifiers[itemId]
    }

    private func context(for taskIdentifier: Int) -> OfflineTaskContext? {
        lock.lock()
        defer { lock.unlock() }
        return contexts[taskIdentifier]
    }

    private func updateContext(_ taskIdentifier: Int, _ transform: (inout OfflineTaskContext) -> Void) {
        lock.lock()
        if var context = contexts[taskIdentifier] {
            transform(&context)
            contexts[taskIdentifier] = context
        }
        lock.unlock()
    }

    private func forgetContext(_ taskIdentifier: Int) {
        lock.lock()
        let itemId = contexts[taskIdentifier]?.itemId
        contexts.removeValue(forKey: taskIdentifier)
        if let itemId, taskIdentifiers[itemId] == taskIdentifier {
            taskIdentifiers.removeValue(forKey: itemId)
        }
        lock.unlock()
    }

    private func note(itemId: String, _ text: String?) {
        DispatchQueue.main.async { [weak self] in
            guard let self, let index = self.rows.firstIndex(where: { $0.itemId == itemId }) else { return }
            self.rows[index].note = text
        }
    }

    /// The in-memory rows are rebuilt from the persisted records + the live contexts.
    private func publish() {
        guard let store else { return }
        lock.lock()
        let live = contexts
        lock.unlock()

        var built = store.records.map { OfflineRow(record: $0) }
        for index in built.indices {
            guard let context = live.values.first(where: { $0.itemId == built[index].itemId }) else { continue }
            built[index].state = .downloading
            built[index].bytes = context.offset + context.fragmentBytes
            built[index].totalBytes = context.remote.size
            built[index].bytesPerSecond = context.bytesPerSecond
            built[index].attempt = context.attempt
        }
        built.sort { ($0.state == .downloading ? 0 : 1, $0.title) < ($1.state == .downloading ? 0 : 1, $1.title) }

        DispatchQueue.main.async { [weak self] in
            self?.rows = built
            // ⚠ The store's own records are persisted; this keeps the HUD's reads consistent with them
            // for a row that just changed state.
            _ = self?.store
        }
    }

    private func pause(record: PlannedRecord, note: String, store: OfflineStore) throws {
        var stored = record.stored
        stored.state = .paused
        stored.bytes = store.diskState(stored.itemId, container: record.container).partialBytes ?? 0
        stored.lastError = note
        try store.upsert(stored)
        publish()
    }

    private func fail(record: PlannedRecord, reason: String, store: OfflineStore,
                      correlation: CorrelationID) throws {
        var stored = record.stored
        stored.state = .failed
        stored.lastError = reason
        stored.verification = nil
        try store.upsert(stored)
        RKMLog.error("offline download failed · \(reason)", category: .offline, correlation: correlation)
        publish()
    }

    private func problem(_ sentence: String) {
        RKMLog.error("offline: \(sentence)", category: .offline)
        DispatchQueue.main.async { self.libraryError = sentence }
    }

    /// One place decides whether a failure is retried, how long to wait, and what the row says.
    private func handle(_ failure: OfflineFailure, itemId: String, title: String, mode: String,
                        attempt: Int, correlation: CorrelationID) {
        guard let store else { return }
        var record = store.record(itemId) ?? OfflineRecord(itemId: itemId, title: title, mode: mode)
        record.attempts = attempt
        record.bytes = store.diskState(itemId, container: record.container).partialBytes ?? 0

        if failure.needsSignIn {
            // ⚠ Not a retry loop: the fix is a human signing in, and the sentence says so (§4.7).
            record.state = .failed
            record.lastError = failure.sentence
            try? store.upsert(record)
            RKMLog.error("offline download needs a sign-in · \(failure.sentence) · cookies "
                         + "\(cookies.summary)", category: .offline, correlation: correlation)
            publish()
            return
        }

        if failure.isRetryable, let delay = retry.delay(beforeAttempt: attempt) {
            record.state = .paused
            record.lastError = failure.sentence + " — retrying in \(Int(delay))s"
            try? store.upsert(record)
            RKMLog.info("offline download will retry in \(Int(delay))s (attempt \(attempt) of "
                        + "\(retry.maximumAttempts)) · \(failure.sentence)", category: .offline,
                        correlation: correlation)
            publish()
            if failure.restartsFromZero {
                // A 416 says our offset is stale — the retry must not send the same Range again.
                _ = try? store.discardPartial(itemId, container: record.container)
            }
            DispatchQueue.global().asyncAfter(deadline: .now() + delay) { [weak self] in
                self?.start(itemId: itemId, title: title, mode: mode, attempt: attempt + 1)
            }
            return
        }

        record.state = .failed
        record.lastError = failure.isRetryable
            ? failure.sentence + " — gave up after \(attempt) attempts"
            : failure.sentence
        try? store.upsert(record)
        RKMLog.error("offline download stopped · \(record.lastError ?? "")", category: .offline,
                     correlation: correlation)
        publish()
    }

    private func scheduleRetry(itemId: String, title: String, mode: String, attempt: Int) {
        guard let delay = retry.delay(beforeAttempt: attempt) else { return }
        DispatchQueue.global().asyncAfter(deadline: .now() + delay) { [weak self] in
            self?.start(itemId: itemId, title: title, mode: mode, attempt: attempt + 1)
        }
    }

    // MARK: - taskDescription

    private struct TaskDescription: Codable {
        var itemId: String
        var title: String?
        var mode: String
        var container: String?
        var offset: Int64
        var total: Int64?
        var etag: String?

        private enum CodingKeys: String, CodingKey {
            case itemId = "i", title = "t", mode = "m", container = "c"
            case offset = "o", total = "n", etag = "e"
        }
    }

    private static func encodeTaskDescription(_ itemId: String, mode: String, container: String?, offset: Int64,
                                             total: Int64, etag: String?) -> String {
        let payload = TaskDescription(itemId: itemId, title: nil, mode: mode, container: container,
                                      offset: offset, total: total, etag: etag)
        let encoder = JSONEncoder()
        guard let data = try? encoder.encode(payload),
              let text = String(data: data, encoding: .utf8) else { return itemId }
        return text
    }

    /// ⚠ `private` because `TaskDescription` is private — an internal function cannot return a private
    /// type (and it is only ever called from `restore()`, in this file).
    private static func decodeTaskDescription(_ text: String) -> TaskDescription? {
        guard let data = text.data(using: .utf8) else { return nil }
        return try? JSONDecoder().decode(TaskDescription.self, from: data)
    }
}

// MARK: - The download delegate

extension OfflineDownloads: URLSessionDownloadDelegate {

    func urlSession(_ session: URLSession,
                    downloadTask: URLSessionDownloadTask,
                    didWriteData bytesWritten: Int64,
                    totalBytesWritten: Int64,
                    totalBytesExpectedToWrite: Int64) {
        let identifier = downloadTask.taskIdentifier
        guard let context = context(for: identifier) else { return }
        let absoluteBytes = context.offset + totalBytesWritten

        var rate = context.bytesPerSecond
        let now = Date()
        let elapsed = now.timeIntervalSince(context.sampleAt)
        if elapsed >= 1.0 {
            let delta = Double(totalBytesWritten - context.sampleBytes)
            // A light smoothing: a single slow sample should not make the ETA jump by minutes.
            rate = delta > 0 ? (rate == 0 ? delta / elapsed : (rate * 0.6) + (delta / elapsed * 0.4)) : rate
        }

        var tenth = -1
        if context.remote.size > 0 {
            tenth = Int(Double(absoluteBytes) / Double(context.remote.size) * 10)
        }

        updateContext(identifier) { stored in
            stored.fragmentBytes = totalBytesWritten
            if elapsed >= 1.0 {
                stored.bytesPerSecond = rate
                stored.sampleAt = now
                stored.sampleBytes = totalBytesWritten
            }
            if tenth >= 0 { stored.lastLoggedTenth = tenth }
        }

        // ⚠ Progress is logged at every 10%, not per callback: at 3.8 MB/s a 2 GB film produces
        // thousands of callbacks, and a log that drowns the useful lines is a log nobody reads
        // (`LOGGING.md` §3 already made this mistake with the artwork challenges).
        if tenth >= 0, tenth != context.lastLoggedTenth {
            RKMLog.info("offline \(tenth * 10)% · \(OfflineFormat.bytes(absoluteBytes))"
                        + " of \(OfflineFormat.bytes(context.remote.size))"
                        + (rate > 0 ? String(format: " · %.1f MB/s", rate / 1e6) : "")
                        + (OfflineFormat.eta(remainingBytes: context.remote.size - absoluteBytes,
                                             bytesPerSecond: rate).map { " · eta \($0)" } ?? ""),
                        category: .offline, correlation: context.correlation)
        }

        let row = OfflineRow(record: OfflineRecord(itemId: context.itemId, title: context.title,
                                                  mode: context.mode, totalBytes: context.remote.size,
                                                  bytes: absoluteBytes, state: .downloading,
                                                  attempts: context.attempt))
        DispatchQueue.main.async { [weak self] in
            guard let self else { return }
            if let index = self.rows.firstIndex(where: { $0.itemId == context.itemId }) {
                self.rows[index].state = .downloading
                self.rows[index].bytes = absoluteBytes
                self.rows[index].totalBytes = context.remote.size
                self.rows[index].bytesPerSecond = rate
                self.rows[index].note = nil
            } else {
                self.rows.append(row)
            }
        }
    }

    /// ⚠⚠ **Everything in this method must be SYNCHRONOUS.** The file at `location` is deleted the moment
    /// it returns, so the splice, the size check and the publish all happen here — no `Task`, no
    /// `DispatchQueue.async`, no `await`. Getting that wrong produces a download that finishes and a film
    /// that is not there.
    func urlSession(_ session: URLSession, downloadTask: URLSessionDownloadTask,
                    didFinishDownloadingTo location: URL) {
        let identifier = downloadTask.taskIdentifier
        guard let context = context(for: identifier), let store else {
            RKMLog.error("offline: a finished task had no context — the bytes cannot be placed",
                         category: .offline)
            return
        }
        let stored = store.record(context.itemId) ?? OfflineRecord(itemId: context.itemId,
                                                                   title: context.title, mode: context.mode)
        let http = downloadTask.response as? HTTPURLResponse
        let status = http?.statusCode ?? 0
        let contentRange = http?.value(forHTTPHeaderField: "Content-Range")
        let fragmentBytes = Self.fileSize(location)

        let plan = OfflineAssembly.plan(status: status, contentRange: contentRange,
                                        requestedOffset: context.offset, localBytes: context.offset,
                                        remoteSize: context.remote.size)

        RKMLog.info("offline fragment · HTTP \(status) · \(OfflineFormat.bytes(fragmentBytes))"
                    + " · Content-Range \(contentRange ?? "—") · asked from "
                    + OfflineFormat.bytes(context.offset) + " · \(describe(plan))",
                    category: .offline, correlation: context.correlation)

        do {
            let newSize: Int64
            switch plan {
            case .appendFragment(let offset):
                newSize = try store.appendFragment(context.itemId, container: context.container, fragment: location)
                RKMLog.verbose("offline appended at \(OfflineFormat.bytes(offset)) — now "
                               + OfflineFormat.bytes(newSize), category: .offline)
            case .wholeFile(let discarded):
                newSize = try store.replacePartial(context.itemId, container: context.container, with: location)
                if discarded > 0 {
                    RKMLog.info("offline the server sent the whole file — discarded "
                                + "\(OfflineFormat.bytes(discarded)) of partial download", category: .offline)
                }
            case .refuse(let reason):
                finishAsIncomplete(itemId: context.itemId, stored: stored, context: context, store: store,
                                   reason: reason, keepBytes: true)
                return
            }

            // ⚠ The size check the plan predicted, then the STRONG check against the server's own identity.
            let expected = plan.finalSize(fragmentBytes: fragmentBytes)
            guard newSize == expected else {
                finishAsIncomplete(itemId: context.itemId, stored: stored, context: context, store: store,
                                   reason: "the bytes on disk (\(newSize)) do not match what the transfer "
                                         + "should have produced (\(expected))", keepBytes: true)
                return
            }

            let completion = OfflineCompletionCheck.check(localBytes: newSize, localETag: context.remote.etag,
                                                          remote: context.remote)
            switch completion {
            case .incomplete(let reason):
                // A short fragment is not corruption — it is a transfer that stopped early, and the bytes
                // are kept so the next attempt resumes from them.
                finishAsIncomplete(itemId: context.itemId, stored: stored, context: context, store: store,
                                   reason: reason, keepBytes: true)
            case .complete(let verification):
                let published = try store.publish(context.itemId, container: context.container)
                var stored = stored
                stored.state = .ready
                stored.bytes = published
                stored.totalBytes = context.remote.size
                stored.etag = context.remote.etag
                stored.contentType = context.remote.contentType
                stored.downloadedAt = Date()
                stored.lastError = nil
                stored.verification = verification
                try store.upsert(stored)
                let seconds = Date().timeIntervalSince(context.startedAt)
                RKMLog.info("offline READY · \(OfflineFormat.bytes(published)) · mode \(context.mode) · verified "
                            + "\(verification.label) · took \(Int(seconds))s"
                            + (seconds > 0 ? String(format: " (%.1f MB/s)", Double(published) / seconds / 1e6) : ""),
                            category: .offline, correlation: context.correlation)
                publish()
            }
        } catch {
            finishAsIncomplete(itemId: context.itemId, stored: stored, context: context, store: store,
                               reason: "the finished file could not be stored: \(error.localizedDescription)",
                               keepBytes: false)
        }
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        let identifier = task.taskIdentifier
        defer { forgetContext(identifier) }

        guard let error else { return }   // success was handled by didFinishDownloadingTo
        guard let context = context(for: identifier) else { return }
        let nsError = error as NSError

        if nsError.domain == NSURLErrorDomain && nsError.code == NSURLErrorCancelled {
            RKMLog.info("offline task cancelled (task \(identifier))", category: .offline,
                        correlation: context.correlation)
            return
        }
        let failure = OfflineAPI.transportFailure(from: error).asFailure
        RKMLog.error("offline task failed · \(nsError.domain) \(nsError.code) — "
                     + "\(nsError.localizedDescription)", category: .offline, correlation: context.correlation)
        handle(failure, itemId: context.itemId, title: context.title, mode: context.mode,
               attempt: context.attempt, correlation: context.correlation)
    }

    func urlSession(_ session: URLSession, didBecomeInvalidWithError error: Error?) {
        guard let error else { return }
        RKMLog.error("offline session became invalid: \(error.localizedDescription)", category: .offline)
    }

    /// ⚠⚠ The system's own completion handler, and it MUST be called — while it is pending, iOS holds the
    /// app's background budget for this session and shows the session as unfinished. Calling it when the
    /// last delegate callback has run is what makes "downloads complete with the app backgrounded" true
    /// rather than "they complete and the app is never told".
    func urlSessionDidFinishEvents(forBackgroundURLSession session: URLSession) {
        lock.lock()
        let handler = backgroundCompletion
        backgroundCompletion = nil
        lock.unlock()

        guard let handler else {
            RKMLog.verbose("offline background events finished with no handler stored", category: .offline)
            return
        }
        DispatchQueue.main.async {
            RKMLog.info("offline background events finished — releasing the system's completion handler",
                        category: .offline)
            handler()
        }
    }

    // MARK: - Internals

    /// Mark the row and let the retry policy decide whether more attempts follow.
    private func finishAsIncomplete(itemId: String, stored: OfflineRecord, context: OfflineTaskContext,
                                    store: OfflineStore, reason: String, keepBytes: Bool) {
        var record = stored
        record.state = .paused
        record.bytes = keepBytes ? (store.diskState(itemId, container: context.container).partialBytes ?? 0) : 0
        record.lastError = reason
        record.attempts = context.attempt
        try? store.upsert(record)
        RKMLog.error("offline incomplete · \(reason) · \(OfflineFormat.bytes(record.bytes)) kept",
                     category: .offline, correlation: context.correlation)
        publish()
        scheduleRetry(itemId: itemId, title: context.title, mode: context.mode, attempt: context.attempt)
    }

    private func describe(_ plan: OfflineAssemblyPlan) -> String {
        switch plan {
        case .appendFragment(let offset): return "append at \(OfflineFormat.bytes(offset))"
        case .wholeFile(let discarded): return "whole file (discards \(OfflineFormat.bytes(discarded)))"
        case .refuse(let reason): return "REFUSED — \(reason)"
        }
    }

    static func fileSize(_ url: URL) -> Int64 {
        let values = try? url.resourceValues(forKeys: [.fileSizeKey])
        return Int64(values?.fileSize ?? 0)
    }
}

// MARK: - Small pieces

private extension OfflineTransportFailure {
    var asFailure: OfflineFailure { .transport(self) }
}

/// The server's state vocabulary, as the bundle/status bodies use it.
enum OfflineServerState {
    static let ready = "ready"
    static let packaging = "packaging"
    static let failed = "failed"
    static let missing = "missing"
}

/// How long to wait for the server to finish packaging a title.
///
/// ⚠ Packaging is a `remux` (a full re-copy through Jellyfin) or a `transcode`, measured in minutes for a
/// feature film — so the poll starts eager and backs off, and the row says what is happening rather than
/// looking stuck. The ceiling is a *stop*, not a target: past it, the honest answer is "the server is
/// still working on it", and the user can retry.
struct OfflinePreparationPolicy: Equatable {
    var maximumWait: TimeInterval = 45 * 60
    var delays: [TimeInterval] = [1, 2, 3, 5, 5, 10, 10, 15, 20, 30]

    func pollDelay(round: Int) -> TimeInterval {
        guard !delays.isEmpty else { return 5 }
        return delays[min(round, delays.count - 1)]
    }
}

/// Keeps the app's preparation phase (plan → package → poll) alive if the user backgrounds the app.
///
/// ⚠ It is NOT what makes the transfer survive backgrounding — a background `URLSession` does that on its
/// own, in a system process. This covers the *other* half, and only partly: the polling for a packaging
/// job happens in OUR process, and an assertion buys the standard grace period (tens of seconds) so the
/// common case — a `direct` title, which packages instantly — survives being backgrounded straight after
/// the tap. ⚠ A packaging job that takes minutes needs the app open again, and that limit is stated in
/// the ADR rather than papered over.
///
/// ⚠ A CLASS, not a struct: the expiration handler must be able to end the assertion it belongs to, and a
/// struct captured in its own initialiser's closure would capture a *copy*.
final class BackgroundAssertion {
    private var identifier: UIBackgroundTaskIdentifier = .invalid
    private let name: String

    init(name: String) {
        self.name = name
        identifier = UIApplication.shared.beginBackgroundTask(withName: name) { [weak self] in
            guard let self else { return }
            RKMLog.error("offline the background assertion for \(self.name) expired — iOS is about to "
                         + "suspend the app; an in-flight packaging wait stops here", category: .offline)
            self.end()
        }
        if identifier == .invalid {
            RKMLog.verbose("offline could not take a background assertion for \(name)", category: .offline)
        }
    }

    func end() {
        guard identifier != .invalid else { return }
        UIApplication.shared.endBackgroundTask(identifier)
        identifier = .invalid
    }

    deinit { end() }
}
