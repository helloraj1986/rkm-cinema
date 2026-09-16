import Foundation
import RKMServerKit

// The device's own copy of everything: one manifest, one directory per title, and the file surgery a
// RESUMABLE download needs. ⚠ This file touches UIKit/WebKit nowhere — it is `FileManager` — but it is
// NOT one of the Linux-tested pure files (`OfflineManifest`/`OfflinePlan`/`CookieHeader`): it decides
// nothing, it only carries out decisions the pure layer already made. That split is what keeps the
// Mac-only surface small.

/// Where a download's bytes live, and what the manifest says about them — reconciled so the FILESYSTEM
/// wins.
///
/// ⚠ **Disk is the source of truth about bytes; the manifest is only an index.** The same rule as
/// ADR-0007 D7 on the server, for the same reason: a manifest is written by a process that can be
/// killed mid-write, and a record that claims 2 GB while the file is 900 MB is exactly the state that
/// produces a "ready" row over a film that plays for four minutes.
final class OfflineStore {

    let layout: OfflineLayout
    private let fileManager: FileManager

    /// ⚠ Every mutation of the manifest happens on this queue. `URLSession`'s delegate callbacks
    /// arrive on a background queue and SwiftUI reads the rows on the main thread, so without one
    /// serialiser a progress update and a completion can interleave into a torn write.
    private let queue = DispatchQueue(label: "rkm.offline.store")
    private var manifest = OfflineManifest()

    init(layout: OfflineLayout, fileManager: FileManager = .default) {
        self.layout = layout
        self.fileManager = fileManager
    }

    // MARK: - Opening

    /// Creates the root, excludes it from backup, and loads + reconciles the manifest.
    ///
    /// ⚠ **`isExcludedFromBackup` is not optional.** A 2 GB film in an iCloud backup is a bug with a
    /// delayed, expensive symptom — the user's backup quota — and `NSTemporaryDirectory`/`Caches` are
    /// the wrong home for a file the user asked to keep (the B0 spike's own note).
    func open() throws {
        try fileManager.createDirectory(at: layout.root, withIntermediateDirectories: true)

        var values = URLResourceValues()
        values.isExcludedFromBackup = true
        var root = layout.root
        try root.setResourceValues(values)

        try queue.sync {
            if let data = try? Data(contentsOf: layout.manifestURL) {
                do {
                    manifest = try OfflineManifest.decode(data)
                } catch {
                    // ⚠ A manifest we cannot read is NOT deleted — it is moved aside and reported, so
                    // a build that changes the shape can never silently take someone's downloads with
                    // it. The downloads themselves are still on disk; the index is what is lost.
                    let aside = layout.root.appendingPathComponent("manifest-unreadable.json")
                    try? fileManager.removeItem(at: aside)
                    try? fileManager.moveItem(at: layout.manifestURL, to: aside)
                    RKMLog.error("offline manifest could not be read (\(error.localizedDescription)) — "
                                 + "kept as \(aside.lastPathComponent) and starting a fresh index",
                                 category: .offline)
                    manifest = OfflineManifest()
                }
            }
            manifest = reconcileFromDisk(manifest)
        }
        try writeManifest()
        RKMLog.info("offline store open — \(records.count) record(s), "
                    + "\(OfflineFormat.bytes(totalBytesOnDisk)) on disk", category: .offline)
    }

    // MARK: - Reading

    var records: [OfflineRecord] { queue.sync { manifest.items } }

    func record(_ itemId: String) -> OfflineRecord? { queue.sync { manifest.item(itemId) } }

    var totalBytesOnDisk: Int64 { queue.sync { manifest.totalBytesOnDisk } }

    // MARK: - Writing

    /// Insert or replace, then persist. Throws only if the manifest could not be written — in which
    /// case the in-memory value is deliberately left as it was.
    func upsert(_ record: OfflineRecord) throws {
        try queue.sync {
            manifest.upsert(record)
            try persistLocked()
        }
    }

    /// Drop the record. ⚠ Files are NOT touched here — `removeFiles` is the separate, deliberate step,
    /// so "forget this record" and "delete this download" can never be confused.
    @discardableResult
    func removeRecord(_ itemId: String) throws -> OfflineRecord? {
        try queue.sync {
            let removed = manifest.remove(itemId)
            if removed != nil { try persistLocked() }
            return removed
        }
    }

    private func writeManifest() throws {
        try queue.sync { try persistLocked() }
    }

    /// Must be called on `queue`.
    private func persistLocked() throws {
        let data = try manifest.encoded()
        // `.atomic` writes a sibling temp file and renames it — the manifest is never half-written.
        try data.write(to: layout.manifestURL, options: .atomic)
    }

    // MARK: - Files

    func makeItemDirectory(_ itemId: String) throws {
        let directory = try layout.itemDirectory(itemId)
        try fileManager.createDirectory(at: directory, withIntermediateDirectories: true)
        var values = URLResourceValues()
        values.isExcludedFromBackup = true
        var url = directory
        try? url.setResourceValues(values)
    }

    /// The bytes on disk for this title, from the two files that can hold them. Final file wins.
    func diskState(_ itemId: String, container: String?) -> OfflineDiskState {
        let final = (try? layout.mediaURL(itemId, container: container)).flatMap(size)
        let partial = (try? layout.partialURL(itemId, container: container)).flatMap(size)
        return OfflineDiskState(finalBytes: final, partialBytes: partial)
    }

    private func size(_ url: URL) -> Int64? {
        guard let attributes = try? fileManager.attributesOfItem(atPath: url.path),
              let value = attributes[.size] as? NSNumber
        else { return nil }
        return value.int64Value
    }

    func partialSize(_ itemId: String, container: String?) -> Int64 {
        diskState(itemId, container: container).partialBytes
    }

    /// Throw the partial away — used by a restart, and by a cancel that the user asked for.
    @discardableResult
    func discardPartial(_ itemId: String, container: String?) throws -> Int64 {
        guard let partial = try? layout.partialURL(itemId, container: container) else { return 0 }
        guard let existing = size(partial) else { return 0 }
        try fileManager.removeItem(at: partial)
        RKMLog.info("offline discarded \(OfflineFormat.bytes(existing)) of partial download", category: .offline)
        return existing
    }

    /// Append a finished fragment to the partial, streaming — ⚠ never via `Data(contentsOf:)`.
    ///
    /// A 2 GB film is a real possibility (the household's library has one at 1,882,377,499 bytes,
    /// measured), and loading a fragment into memory on a phone is how a background download turns
    /// into a memory kill. This is `FileHandle` to `FileHandle`, 1 MB at a time.
    @discardableResult
    func appendFragment(_ itemId: String, container: String?, fragment: URL) throws -> Int64 {
        try makeItemDirectory(itemId)
        let partial = try layout.partialURL(itemId, container: container)
        if !fileManager.fileExists(atPath: partial.path) {
            fileManager.createFile(atPath: partial.path, contents: nil)
        }
        guard let output = FileHandle(forWritingAtPath: partial.path),
              let input = FileHandle(forReadingAtPath: fragment.path)
        else {
            throw OfflineStoreError.cannotOpen("\(partial.lastPathComponent) or the fragment")
        }
        defer {
            try? output.close()
            try? input.close()
        }
        output.seekToEndOfFile()
        while true {
            let block = input.readData(ofLength: 1 << 20)
            if block.isEmpty { break }
            output.write(block)
        }
        return size(partial) ?? 0
    }

    /// The response was a WHOLE file, so it replaces whatever partial was there.
    @discardableResult
    func replacePartial(_ itemId: String, container: String?, with fragment: URL) throws -> Int64 {
        try makeItemDirectory(itemId)
        let partial = try layout.partialURL(itemId, container: container)
        if fileManager.fileExists(atPath: partial.path) {
            try fileManager.removeItem(at: partial)
        }
        try fileManager.moveItem(at: fragment, to: partial)
        return size(partial) ?? 0
    }

    /// Publish: `.part` → the real name, in one move within the same directory. ⚠ This is the moment a
    /// half-file stops being able to masquerade as a whole one, and there is exactly one call site
    /// (`OfflineDownloads.finish`), after the completion check has passed.
    @discardableResult
    func publish(_ itemId: String, container: String?) throws -> Int64 {
        let partial = try layout.partialURL(itemId, container: container)
        let final = try layout.mediaURL(itemId, container: container)
        if fileManager.fileExists(atPath: final.path) {
            try fileManager.removeItem(at: final)
        }
        try fileManager.moveItem(at: partial, to: final)
        return size(final) ?? 0
    }

    /// Delete everything this title owns on the device. ⚠ The household's file is on the server and is
    /// never touched by this — the device only ever deletes its own copy (ADR-0007 D2's rule, seen from
    /// the other side).
    func removeFiles(_ itemId: String) throws {
        guard let directory = try? layout.itemDirectory(itemId),
              fileManager.fileExists(atPath: directory.path)
        else { return }
        try fileManager.removeItem(at: directory)
        RKMLog.info("offline files removed for one title", category: .offline)
    }

    // MARK: - Reconciliation

    /// The filesystem's answer, applied to the index: every record's `bytes`/`state` is re-derived, and
    /// a record whose file disagrees with the size the server reported is **discarded and said so**.
    ///
    /// ⚠ The one destructive branch in this file, and it is deliberate: a final file whose size does not
    /// match what the server said is not a film, it is a corrupt copy that would play badly. It can
    /// always be re-downloaded, and leaving it would make `ready` a lie.
    private func reconcileFromDisk(_ input: OfflineManifest) -> OfflineManifest {
        var output = OfflineManifest(version: input.version)
        for var record in input.items {
            let state = diskState(record.itemId, container: record.container)

            if let finalBytes = state.finalBytes {
                if record.totalBytes > 0 && finalBytes != record.totalBytes {
                    RKMLog.error("offline file for one title is \(finalBytes) B but the server said "
                                 + "\(record.totalBytes) B — discarding the local copy", category: .offline)
                    if let media = try? layout.mediaURL(record.itemId, container: record.container) {
                        try? fileManager.removeItem(at: media)
                    }
                    if let partial = try? layout.partialURL(record.itemId, container: record.container) {
                        try? fileManager.removeItem(at: partial)
                    }
                    record.bytes = 0
                    record.state = .failed
                    record.verification = nil
                    record.lastError = "The stored file did not match the size the server reported, so it "
                                     + "was discarded. Download it again."
                    output.upsert(record)
                    continue
                }
                record.bytes = finalBytes
                record.state = .ready
                record.lastError = nil
                output.upsert(record)
                continue
            }

            // No published file. A partial is a paused download — never a ready one, whatever the
            // index claims, which is the whole point of deriving this here.
            let partialBytes = state.partialBytes ?? 0
            record.bytes = partialBytes
            switch record.state {
            case .ready:
                record.state = .failed
                record.lastError = "The downloaded file is missing from this device. Download it again."
            case .failed:
                break   // a real failure keeps its reason until something retries it
            default:
                record.state = .paused
            }
            output.upsert(record)
        }
        return output
    }
}

/// What is on disk for one title. `nil` means the file is not there at all (which is not 0 bytes).
struct OfflineDiskState: Equatable {
    var finalBytes: Int64?
    var partialBytes: Int64?

    var hasAnything: Bool { finalBytes != nil || partialBytes != nil }
}

enum OfflineStoreError: LocalizedError, Equatable {
    case cannotOpen(String)

    var errorDescription: String? {
        switch self {
        case .cannotOpen(let what): return "Could not open \(what) for writing."
        }
    }
}
