import Foundation

// ⚠⚠ FOUNDATION ONLY, ON PURPOSE — and that is a verification decision, not tidiness.
//
// The whole of B2 is device work: `URLSession`, `WKWebsiteDataStore`, SwiftUI. None of that exists in
// the Linux sandbox, so none of it can be *run* here — and `apple/WORKFLOW.md` §5 is blunt that a
// build which has not run on the Mac is not verified.
//
// But the part of a downloader that is actually easy to get wrong is not the networking: it is the
// arithmetic and the rules — where a byte offset resumes from, whether a partial file is the same
// film the server is now offering, what a `206` whose `Content-Range` disagrees with the requested
// offset means, which failures are worth retrying, and whether an item id can escape its own
// directory. Those are pure functions over `Int64`/`String`/`URL`, so they live here with NO Apple
// framework import at all, and `apple/scripts/check-offline-core.py` compiles THIS FILE with
// `swiftc` on Linux, runs it against real cases, and falsifies every rule by reverting it.
//
// The rule that keeps that true: nothing in `OfflineManifest.swift` / `OfflinePlan.swift` /
// `CookieHeader.swift` may `import` anything but `Foundation`. If a change needs WebKit or UIKit,
// it belongs in a sibling file (`OfflineStore`, `OfflineAPI`, `CookieMirror`, `OfflineDownloads`).

// MARK: - Identity

/// Why an item id was refused — a sentence, because "the download failed" is not a diagnosis.
struct OfflineIdentifierError: LocalizedError, Equatable {
    let raw: String
    let reason: String

    var errorDescription: String? { "\(reason) (item id \(raw.prefix(64)))" }
}

/// Item ids as DIRECTORY NAMES, on the device.
///
/// ⚠ The server has the same rule (`backend/services/offline.py::safe_id`) and this is deliberately
/// **stricter than it is**. The server *rewrites*: it strips every character outside `[A-Za-z0-9_-]`,
/// truncates to 64, and — when that changed the id — appends a hash so two different ids cannot land
/// on one file. The device **refuses** instead, because a rewrite is an *alias*, and an alias is the
/// one thing that can put two different titles in the same directory. There is no hash here and no
/// attempt to reproduce the server's, so the two can never disagree: an id that arrives unchanged is
/// stored under its own name, and an id that would have been rewritten is refused **by name**.
///
/// A real Jellyfin id is 32 hex characters, so the refusal has never fired. If it ever does, the
/// sentence says which id and why, and the fix is on the server (it already rewrites for its own
/// staging path) rather than a silent local alias.
enum OfflineIdentifier {

    static let maximumLength = 64

    private static let allowed = Set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-")

    /// The id as a single path component, or the reason it may not be one.
    ///
    /// Refused: empty · longer than 64 · any character outside `[A-Za-z0-9_-]` (which covers `/`,
    /// `\`, `.`, `..`, a NUL byte and every URL-escape that could decode into one) · a leading `-`
    /// or `_` alone is allowed on purpose, it is still one harmless component.
    static func validated(_ raw: String) -> Result<String, OfflineIdentifierError> {
        guard !raw.isEmpty else {
            return .failure(.init(raw: raw, reason: "The server sent an empty item id."))
        }
        guard raw.count <= maximumLength else {
            return .failure(.init(
                raw: raw,
                reason: "The item id is longer than \(maximumLength) characters."
            ))
        }
        if let bad = raw.first(where: { !allowed.contains($0) }) {
            let shown = bad.unicodeScalars.first.map { String(format: "U+%04X", $0.value) } ?? "?"
            return .failure(.init(
                raw: raw,
                reason: "The item id contains a character this app will not put in a filename (\(shown)) — "
                        + "a server-side id needs the same rewrite the server already applies to its own staging path."
            ))
        }
        return .success(raw)
    }

    /// Convenience for callers that already know the id came from a route they built themselves.
    static func checked(_ raw: String) throws -> String {
        switch validated(raw) {
        case .success(let value): return value
        case .failure(let error): throw error
        }
    }
}

// MARK: - State

/// What the DEVICE thinks of one download.
///
/// ⚠ Deliberately NOT the server's vocabulary (`missing`/`packaging`/`ready`/`failed`). The server's
/// states describe *its* staging file; these describe *this phone's* copy, and the two disagree
/// constantly — that is the normal case, not an error: the server can have a `ready` artefact the
/// device has only half of, and the device can hold a `ready` film the server has since swept.
enum OfflineState: String, Codable, Equatable {
    /// Bytes are arriving (or were, before a relaunch — reconciled at launch, see `OfflineDownloads`).
    case downloading
    /// Bytes on disk, no task running. Resumable, and the row says so rather than looking finished.
    case paused
    /// The whole file, verified against the server's size and ETag.
    case ready
    /// Stopped for a reason a retry may not fix until something else changes. `lastError` says why.
    case failed

    var label: String {
        switch self {
        case .downloading: return "downloading"
        case .paused: return "paused"
        case .ready: return "ready"
        case .failed: return "failed"
        }
    }

    /// ⚠ Can this state be trusted to PLAY? Exactly one state can, and the size check that earns it
    /// is in `OfflineReadyCheck` — a half-file that plays as if complete is the failure this whole
    /// feature is shaped to avoid.
    var isPlayable: Bool { self == .ready }
}

// MARK: - The record

/// One downloaded (or partly downloaded) title, as the device remembers it.
///
/// ⚠ Every field decodes with `decodeIfPresent`, so a manifest written by an OLDER build still loads
/// — the A1 lesson from the query cache (`frontend/src/lib/query/persist.ts`): a snapshot that will
/// not parse is worse than no snapshot, because it turns "the feature has no data yet" into "the
/// feature is broken". Missing values fall back to the state a fresh record has.
struct OfflineRecord: Codable, Equatable {

    /// The id the SERVER uses, exactly as it was sent. Never a rewritten form.
    var itemId: String
    var title: String
    /// The rendition the server packaged: `direct` · `remux` · `transcode_audio` · `transcode`.
    var mode: String
    /// The server's own container string (ffprobe's demuxer list). Recorded rather than inferred —
    /// B3's loopback server answers `Content-Type` from this, so nothing has to guess.
    var container: String?
    /// The `Content-Type` the file response actually carried. The authoritative answer for B3.
    var contentType: String?
    /// True when the server's artefact IS the household's library file (ADR-0007 D2). Informational
    /// on the device — this copy always belongs to the device.
    var borrowed: Bool
    /// The server's `Content-Length` for this rendition: what `ready` must equal. 0 until known.
    var totalBytes: Int64
    /// What is on THIS device right now — the `.part` size while incomplete, the file size when ready.
    var bytes: Int64
    /// The server's strong ETag the local bytes belong to. `nil` only before the first byte.
    var etag: String?
    var state: OfflineState
    /// How `ready` was established. ⚠ Recorded, not inferred: a later "it played the wrong edit" report
    /// needs to know whether the ETag was checked or only the size was (`OfflineReadyVerification`).
    var verification: OfflineReadyVerification?
    /// When the download finished (`ready`), for the Downloads screen. `nil` while incomplete.
    var downloadedAt: Date?
    /// The last thing that went wrong, in a sentence. Survives a relaunch on purpose: a failure the
    /// user comes back to must still say what it was.
    var lastError: String?
    /// How many times the current download has been attempted — retry reads it, and the HUD shows it.
    var attempts: Int

    init(
        itemId: String,
        title: String,
        mode: String,
        container: String? = nil,
        contentType: String? = nil,
        borrowed: Bool = false,
        totalBytes: Int64 = 0,
        bytes: Int64 = 0,
        etag: String? = nil,
        state: OfflineState = .paused,
        verification: OfflineReadyVerification? = nil,
        downloadedAt: Date? = nil,
        lastError: String? = nil,
        attempts: Int = 0
    ) {
        self.itemId = itemId
        self.title = title
        self.mode = mode
        self.container = container
        self.contentType = contentType
        self.borrowed = borrowed
        self.totalBytes = totalBytes
        self.bytes = bytes
        self.etag = etag
        self.state = state
        self.verification = verification
        self.downloadedAt = downloadedAt
        self.lastError = lastError
        self.attempts = attempts
    }

    private enum CodingKeys: String, CodingKey {
        case itemId = "item_id"
        case title, mode, container, contentType, borrowed
        case totalBytes = "total_bytes"
        case bytes, etag, state
        case verification
        case downloadedAt = "downloaded_at"
        case lastError = "last_error"
        case attempts
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        itemId = try container.decode(String.self, forKey: .itemId)
        title = try container.decodeIfPresent(String.self, forKey: .title) ?? ""
        mode = try container.decodeIfPresent(String.self, forKey: .mode) ?? "direct"
        self.container = try container.decodeIfPresent(String.self, forKey: .container)
        contentType = try container.decodeIfPresent(String.self, forKey: .contentType)
        borrowed = try container.decodeIfPresent(Bool.self, forKey: .borrowed) ?? false
        totalBytes = try container.decodeIfPresent(Int64.self, forKey: .totalBytes) ?? 0
        bytes = try container.decodeIfPresent(Int64.self, forKey: .bytes) ?? 0
        etag = try container.decodeIfPresent(String.self, forKey: .etag)
        // ⚠ An UNKNOWN state string (a newer build wrote it) becomes `.paused`, never `.ready`:
        // the failure direction matters — the safe reading of "I do not understand this record" is
        // "there are bytes here, ask the server", not "play it".
        let rawState = try container.decodeIfPresent(String.self, forKey: .state)
        state = rawState.flatMap(OfflineState.init(rawValue:)) ?? .paused
        verification = try container.decodeIfPresent(OfflineReadyVerification.self, forKey: .verification)
        downloadedAt = try container.decodeIfPresent(Date.self, forKey: .downloadedAt)
        lastError = try container.decodeIfPresent(String.self, forKey: .lastError)
        attempts = try container.decodeIfPresent(Int.self, forKey: .attempts) ?? 0
    }

    /// 0…1, or `nil` when the total is not known yet (a bar over an unknown total is a lie).
    var fraction: Double? {
        guard totalBytes > 0 else { return nil }
        return min(1, max(0, Double(bytes) / Double(totalBytes)))
    }

    /// What is still to come, for an ETA — 0 when nothing is.
    var remainingBytes: Int64 { max(0, totalBytes - bytes) }
}

// MARK: - The manifest

/// Why a manifest could not be used. ⚠ These are distinct on purpose: "there is no manifest yet" is
/// normal on a fresh install, and "a newer build wrote it" is a bug we must not paper over by
/// truncating somebody's downloads.
enum OfflineManifestError: LocalizedError, Equatable {
    case fromANewerBuild(found: Int, supported: Int)
    case unreadable(detail: String)

    var errorDescription: String? {
        switch self {
        case .fromANewerBuild(let found, let supported):
            return "This manifest was written by a newer build (v\(found), this build reads v\(supported)). "
                 + "It has been left alone — nothing was deleted."
        case .unreadable(let detail):
            return "The offline manifest could not be read: \(detail)"
        }
    }
}

/// The whole on-disk index: one JSON file, rewritten atomically, small enough to read on every launch.
///
/// ⚠ It is an INDEX, never the source of truth about bytes. Which is why every field that describes
/// *content* (`bytes`, `totalBytes`, `state: ready`) is re-derived from the filesystem when the store
/// loads (`OfflineStore.load`). ADR-0007 D7 said this for the server — "a manifest says what something
/// is; the filesystem says whether it is there, and the filesystem wins" — and it is the same rule here.
struct OfflineManifest: Codable, Equatable {

    /// Bumped only for a shape that an older reader cannot cope with at all.
    static let currentVersion = 1

    var version: Int
    var items: [OfflineRecord]

    init(version: Int = OfflineManifest.currentVersion, items: [OfflineRecord] = []) {
        self.version = version
        self.items = items
    }

    // MARK: Reading

    /// ⚠ Refuses a NEWER version instead of reading what it can. A partially-understood manifest is
    /// how a build silently drops half a household's downloads; saying so costs one log line.
    static func decode(_ data: Data) throws -> OfflineManifest {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        do {
            let manifest = try decoder.decode(OfflineManifest.self, from: data)
            guard manifest.version <= currentVersion else {
                throw OfflineManifestError.fromANewerBuild(found: manifest.version, supported: currentVersion)
            }
            return manifest
        } catch let error as OfflineManifestError {
            throw error
        } catch {
            throw OfflineManifestError.unreadable(detail: String(describing: error))
        }
    }

    func encoded() throws -> Data {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        // Stable, readable on disk — this file is meant to be inspectable in a container download.
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        return try encoder.encode(self)
    }

    // MARK: CRUD — the only three operations, and none of them is "replace everything"

    func item(_ itemId: String) -> OfflineRecord? {
        items.first { $0.itemId == itemId }
    }

    /// Insert or replace by `itemId`. ⚠ Replace is by IDENTITY, not by index: a record rewritten while
    /// a second task completed would otherwise overwrite the wrong row.
    mutating func upsert(_ record: OfflineRecord) {
        if let index = items.firstIndex(where: { $0.itemId == record.itemId }) {
            items[index] = record
        } else {
            items.append(record)
        }
    }

    @discardableResult
    mutating func remove(_ itemId: String) -> OfflineRecord? {
        guard let index = items.firstIndex(where: { $0.itemId == itemId }) else { return nil }
        return items.remove(at: index)
    }

    /// Newest first — the shipping order the Downloads screen (B4) will want; the pure kind of rule that
    /// belongs with the data rather than in a view. Kept because the HUD reads it today and B5's eviction
    /// needs a defined order, not because a screen exists yet.
    var newestFirst: [OfflineRecord] {
        items.sorted { ($0.downloadedAt ?? .distantPast) > ($1.downloadedAt ?? .distantPast) }
    }

    var totalBytesOnDisk: Int64 {
        items.reduce(0) { $0 + $1.bytes }
    }
}

// MARK: - Layout

/// Where a download lives. ONE place decides, so no call site can invent a path.
///
///     <root>/manifest.json
///     <root>/<item-id>/media.mp4           the finished film (extension from the server's container)
///     <root>/<item-id>/media.mp4.part      the bytes so far — never served, never playable
///     <root>/<item-id>/poster.jpg          B4's artwork (captured at download time)
///     <root>/<item-id>/sub-<lang>.vtt      B4's sidecars
///
/// ⚠ The `.part` file is a SIBLING of its final name, not a temp name elsewhere, so publishing is a
/// `moveItem` within one directory — the same atomic-publish discipline as the server's
/// `.part → os.replace` (ADR-0007 D4), for the same reason: `ready` and a `Content-Length` may never
/// describe half a film.
struct OfflineLayout {

    static let folderName = "Offline"
    static let manifestName = "manifest.json"
    static let mediaBaseName = "media"
    static let partialSuffix = ".part"

    let root: URL

    init(root: URL) {
        self.root = root
    }

    /// ⚠ `Application Support`, NOT `Caches` — deliberately, and for the reason the B0 spike wrote
    /// down: iOS may purge `Caches/` under storage pressure, and a file the user explicitly asked to
    /// keep is the one thing that must not vanish. The caller sets `isExcludedFromBackup` on it too
    /// (`OfflineStore.prepare`): a 2 GB film in an iCloud backup is a bug, not a convenience.
    static func defaultRoot(fileManager: FileManager = .default) throws -> URL {
        let base = try fileManager.url(
            for: .applicationSupportDirectory,
            in: .userDomainMask,
            appropriateFor: nil,
            create: true
        )
        return base.appendingPathComponent(folderName, isDirectory: true)
    }

    var manifestURL: URL { root.appendingPathComponent(Self.manifestName) }

    /// The item's own directory. Throws rather than renaming — see `OfflineIdentifier`.
    func itemDirectory(_ itemId: String) throws -> URL {
        root.appendingPathComponent(try OfflineIdentifier.checked(itemId), isDirectory: true)
    }

    /// The filename a download uses: `media.mp4` · `media.mkv` · `media.bin`.
    static func mediaName(container: String?) -> String {
        "\(mediaBaseName).\(OfflineContainer.fileExtension(forServerContainer: container))"
    }

    static func partialName(container: String?) -> String {
        mediaName(container: container) + partialSuffix
    }

    func mediaURL(_ itemId: String, container: String?) throws -> URL {
        try itemDirectory(itemId).appendingPathComponent(Self.mediaName(container: container))
    }

    func partialURL(_ itemId: String, container: String?) throws -> URL {
        try itemDirectory(itemId).appendingPathComponent(Self.partialName(container: container))
    }

    func posterURL(_ itemId: String, width: Int = 500) throws -> URL {
        try itemDirectory(itemId).appendingPathComponent("poster-\(width).jpg")
    }

    func subtitleURL(_ itemId: String, language: String) throws -> URL {
        try itemDirectory(itemId).appendingPathComponent("sub-\(language).vtt")
    }
}

// MARK: - Containers

/// The container as a NAME, mirroring the server's own rule.
///
/// ⚠⚠ `Container` from Jellyfin is **ffprobe's `format_name`**, a comma-separated DEMUXER LIST — an
/// ordinary MP4 arrives as `"mov,mp4,m4a,3gp,3g2,mj2"`. This is the same measured fact that cost B1 a
/// live-gate failure (13 of 13 MP4s taking the remux rung), so the lists below are **copied from
/// `backend/services/offline.py`** rather than re-derived; if they ever diverge, the divergence is the
/// bug. The device only uses this for a *filename extension* — B3 answers `Content-Type` from the
/// recorded `contentType`, which is the server's own answer — so a miss here is cosmetic, not a
/// playback failure. Noted because it is exactly the kind of place a "clever" re-derivation hides.
enum OfflineContainer {

    static let mp4Family: Set<String> = ["mov", "mp4", "m4a", "m4v", "3gp", "3g2", "mj2"]
    static let matroskaFamily: Set<String> = ["matroska", "webm"]

    /// `"mov,mp4,m4a,3gp,3g2,mj2"` → `"mp4"` · `"mkv"` → `"mkv"` · `"matroska,webm"` → `"matroska"` ·
    /// absent/unknown → `""`. ⚠ Order matters: MP4 is tested first, because the family strings can
    /// share tokens and the MP4 list is the one that means "WebKit plays this as-is".
    static func family(_ serverContainer: String?) -> String {
        let tokens = (serverContainer ?? "")
            .split(separator: ",")
            .map { $0.trimmingCharacters(in: .whitespaces).lowercased() }
            .filter { !$0.isEmpty }
        guard let first = tokens.first else { return "" }
        if tokens.contains(where: { mp4Family.contains($0) }) { return "mp4" }
        if tokens.contains(where: { matroskaFamily.contains($0) }) { return "matroska" }
        return first
    }

    /// A filename extension, from the family. `bin` for anything unrecognised — an extension that
    /// claims a format we did not verify is worse than an honest one.
    static func fileExtension(forServerContainer serverContainer: String?) -> String {
        switch family(serverContainer) {
        case "mp4": return "mp4"
        case "matroska", "mkv": return "mkv"
        case "webm": return "webm"
        default: return "bin"
        }
    }
}
