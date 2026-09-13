import Foundation

#if canImport(Darwin)
import Darwin
#else
import Glibc
#endif

public enum RollingFileLogError: Error, Equatable {
    case cannotCreateDirectory(path: String)
    case cannotOpen(path: String, code: Int32)
}

/// The capped rolling file behind every log line — `apple/LOGGING.md` §1, layer 2.
///
/// ⚠ **This exists because `os_log` alone is not enough.** `.debug`-level messages are not
/// persisted and `.info` is only flushed to disk on collection, so if `os_log` is the only
/// sink then every log from a run he was not streaming at the time is **gone**. The file is
/// the answer, and it is the artefact that gets pasted back to me.
///
/// Shape: one current file (`rkm-ios.log`) plus numbered archives (`rkm-ios.1.log` …), capped
/// at `maxFileBytes` each, so a long play session cannot fill the device. Deliberately plain
/// POSIX `open`/`write`/`fsync` rather than `FileHandle`: `O_APPEND` writes are atomic per
/// line, the deprecation-free API keeps the Mac build clean, and a write that lands in the
/// page cache survives a process crash — which is the crash we actually care about, since
/// the interesting lines are the ones immediately before it.
public final class RollingFileLog: @unchecked Sendable {

    public struct Policy: Sendable {
        public let maxFileBytes: Int
        /// Total number of files kept, **including** the current one.
        public let maxFiles: Int
        public let baseName: String

        public init(maxFileBytes: Int = 2 * 1024 * 1024, maxFiles: Int = 5, baseName: String = "rkm.log") {
            // A floor keeps a silly value from rotating on every line; the ceiling is what
            // bounds the app's disk use.
            self.maxFileBytes = max(64 * 1024, maxFileBytes)
            self.maxFiles = max(2, maxFiles)
            self.baseName = baseName
        }

        /// The whole budget on disk — what the docs quote when they say "capped".
        public var totalByteCap: Int { maxFileBytes * maxFiles }

        public var currentFileName: String { baseName }

        public func archiveFileName(_ index: Int) -> String {
            let url = URL(fileURLWithPath: baseName)
            let stem = url.deletingPathExtension().lastPathComponent
            let ext = url.pathExtension
            return ext.isEmpty ? "\(stem).\(index)" : "\(stem).\(index).\(ext)"
        }
    }

    public let directory: URL
    public let policy: Policy

    private let queue = DispatchQueue(label: "com.helloraj1986.rkmcinema.filelog")
    private var descriptor: Int32 = -1
    private var written = 0

    public var currentFileURL: URL { directory.appendingPathComponent(policy.currentFileName) }

    public func archiveURL(_ index: Int) -> URL {
        directory.appendingPathComponent(policy.archiveFileName(index))
    }

    /// Oldest last. Empty for a `maxFiles` of 2 minus nothing — see the rotation step.
    public var archiveURLs: [URL] {
        (1..<policy.maxFiles).map(archiveURL)
    }

    public var currentFileByteSize: Int {
        queue.sync { written }
    }

    public init(directory: URL, policy: Policy = Policy()) throws {
        self.directory = directory
        self.policy = policy

        let manager = FileManager.default
        do {
            try manager.createDirectory(at: directory, withIntermediateDirectories: true)
        } catch {
            throw RollingFileLogError.cannotCreateDirectory(path: directory.path)
        }
        // Logs should not eat his iCloud backup quota.
        var resourceValues = URLResourceValues()
        resourceValues.isExcludedFromBackup = true
        var mutableDirectory = directory
        try? mutableDirectory.setResourceValues(resourceValues)

        try openCurrent()
        // A file left oversized by a previous build would else sit at the cap until the next
        // line crossed it.
        if written > policy.maxFileBytes { try rotate() }
    }

    deinit {
        closeCurrent()
    }

    // MARK: - Writing

    /// Synchronous on a private serial queue: ordering is guaranteed, and a line that has been
    /// logged has been handed to the kernel before the caller continues — which is the whole
    /// point of a log you are trying to read after a crash.
    public func append(_ line: String) {
        let payload = Data((line + "\n").utf8)
        queue.sync {
            if written + payload.count > self.policy.maxFileBytes {
                try? self.rotate()
            }
            self.writeAll(payload)
        }
    }

    public func append(_ entry: LogEntry) {
        append(entry.text())
    }

    /// Force the page cache to disk. Called when the app goes to the background, not per line —
    /// a process crash does not lose unflushed writes, a power cut does.
    public func flush() {
        queue.sync {
            guard descriptor >= 0 else { return }
            _ = fsync(descriptor)
        }
    }

    /// Close and delete everything. Tests and a "start a clean run" button.
    public func removeAllFiles() {
        queue.sync {
            closeCurrent()
            let manager = FileManager.default
            try? manager.removeItem(at: currentFileURL)
            for index in 1..<policy.maxFiles {
                try? manager.removeItem(at: archiveURL(index))
            }
            try? openCurrent()
        }
    }

    // MARK: - Plumbing

    private func openCurrent() throws {
        let path = currentFileURL.path
        let handle = open(path, O_WRONLY | O_CREAT | O_APPEND, 0o644)
        guard handle >= 0 else {
            throw RollingFileLogError.cannotOpen(path: path, code: errno)
        }
        descriptor = handle
        written = Self.fileSize(at: currentFileURL)
    }

    private func closeCurrent() {
        guard descriptor >= 0 else { return }
        _ = close(descriptor)
        descriptor = -1
    }

    private func writeAll(_ payload: Data) {
        guard descriptor >= 0 else { return }
        let total = payload.count
        var offset = 0
        while offset < total {
            let result = payload.withUnsafeBytes { buffer -> Int in
                guard let base = buffer.baseAddress else { return -1 }
                return write(descriptor, base.advanced(by: offset), total - offset)
            }
            if result > 0 {
                offset += result
                written += result
                continue
            }
            if result < 0 && errno == EINTR { continue }
            // Best-effort by design: the `os_log` sink still has the line, and a logging
            // failure must never take the app down with it.
            break
        }
    }

    /// `rkm.log` → `rkm.1.log`, `rkm.1.log` → `rkm.2.log`, … and the oldest archive is dropped.
    private func rotate() throws {
        closeCurrent()
        let manager = FileManager.default

        try? manager.removeItem(at: archiveURL(policy.maxFiles - 1))
        if policy.maxFiles > 2 {
            for index in stride(from: policy.maxFiles - 2, through: 1, by: -1) {
                let source = archiveURL(index)
                guard manager.fileExists(atPath: source.path) else { continue }
                try? manager.removeItem(at: archiveURL(index + 1))
                try? manager.moveItem(at: source, to: archiveURL(index + 1))
            }
        }
        if manager.fileExists(atPath: currentFileURL.path) {
            try? manager.removeItem(at: archiveURL(1))
            try? manager.moveItem(at: currentFileURL, to: archiveURL(1))
        }

        try openCurrent()
    }

    private static func fileSize(at url: URL) -> Int {
        guard let attributes = try? FileManager.default.attributesOfItem(atPath: url.path),
              let raw = attributes[.size]
        else { return 0 }
        if let value = raw as? Int { return value }
        if let number = raw as? NSNumber { return number.intValue }
        return 0
    }

    /// Where the log lives: `Application Support/<app>/Logs`.
    ///
    /// `Application Support` rather than `Documents`, because the file is not the user's
    /// document and must not appear in the Files app to be deleted by accident
    /// (`apple/LOGGING.md` §7 — logs travel back by **pasting**, not by browsing).
    public static func defaultDirectory(appFolder: String) throws -> URL {
        let manager = FileManager.default
        let base: URL
        #if canImport(Darwin)
        base = try manager.url(for: .applicationSupportDirectory, in: .userDomainMask,
                               appropriateFor: nil, create: true)
        #else
        base = URL(fileURLWithPath: NSTemporaryDirectory(), isDirectory: true)
        #endif

        let directory = base
            .appendingPathComponent(appFolder, isDirectory: true)
            .appendingPathComponent("Logs", isDirectory: true)
        do {
            try manager.createDirectory(at: directory, withIntermediateDirectories: true)
        } catch {
            throw RollingFileLogError.cannotCreateDirectory(path: directory.path)
        }
        return directory
    }
}
