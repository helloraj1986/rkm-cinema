import Foundation
import RKMServerKit

/// The **app-owned shell on disk** — `docs/adr/ADR-0012-cold-launch-offline-shell.md` D7/D8, plan §0c
/// phase S2.
///
/// ⚠⚠ **Why the app keeps its own copy at all, when the WebView has a cache: MEASURED, on his iPhone.**
/// WebKit refuses to STORE a response larger than roughly 5% of its disk cache, so with the Wi-Fi off the
/// shell's ~1.1 MB bundle never came back — the document did, the app did not, and the screen stayed
/// blank. The spike then measured that the app CAN do better: a document handed to WebKit with the
/// server as its base URL keeps the **server's origin** (so the session cookie, same-origin `/api/*` and
/// A1's persisted `localStorage` all keep working), and a `WKURLSchemeHandler` CAN carry the app's own
/// **module scripts**. This directory is where those bytes live.
///
/// ## The layout
///
/// ```
/// Application Support/ShellCache/
///   ├── shell.html                     ⚠ the document, ALREADY REWRITTEN to the app's scheme
///   ├── manifest.json                  ⚠ the commit point — written LAST
///   └── assets/index-<hash>.{js,css}   content-hashed, so a refresh never overwrites a live one
/// ```
///
/// ⚠ **Subdirectories are NOT preserved.** `ShellStoreRules.isStorableAssetPath` allows a plain name
/// directly under `/assets/` and nothing else, so the file name is the whole path. That is a security
/// rule (these strings arrive over the network and become file names) and it is what makes `assetURL`
/// safe to write in one line.
///
/// ## Why `Application Support` and not `Caches`
///
/// The same reason the offline downloads live there: **iOS may purge `Caches/` under storage pressure**,
/// and a shell that vanishes is the bug this exists to fix. ⚠ Backup-excluded, because it is
/// re-fetchable in one online launch and there is no reason for it to ride into iCloud.
enum ShellStore {

    /// ⚠ `ShellStoreRules.choice` compares these strings for equality, so the ONE place that builds the
    /// key is here — a second spelling anywhere else would silently disable the store on every launch.
    static func addressKey(for address: ServerAddress) -> String {
        address.url.absoluteString
    }

    /// ⚠ A file name, not a user path: everything here is generated, never typed or typed by a human.
    static let documentName = "shell.html"
    static let manifestName = "manifest.json"
    static let assetsDirectoryName = "assets"

    // MARK: - Locations

    static func directory() throws -> URL {
        let base = try FileManager.default.url(for: .applicationSupportDirectory,
                                               in: .userDomainMask,
                                               appropriateFor: nil,
                                               create: true)
        var directory = base.appendingPathComponent("ShellCache", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        // ⚠ `var`, because `setResourceValues` is mutating on the URL itself. The shell is re-fetchable,
        // so keeping it out of iCloud backups is the same call the downloader makes (ADR-0008).
        var values = URLResourceValues()
        values.isExcludedFromBackup = true
        try directory.setResourceValues(values)
        return directory
    }

    static func documentURL() throws -> URL {
        try directory().appendingPathComponent(documentName)
    }

    /// ⚠ Refuses anything `ShellStoreRules` refuses, and that is the whole safety argument: the caller
    /// passes a path that came out of a fetched document.
    static func assetURL(path: String) throws -> URL {
        guard ShellStoreRules.isStorableAssetPath(path) else {
            throw ShellStoreError.unsafeAssetPath(path)
        }
        let name = String(path.dropFirst(ShellStoreRules.assetPrefix.count))
        return try directory()
            .appendingPathComponent(assetsDirectoryName, isDirectory: true)
            .appendingPathComponent(name)
    }

    // MARK: - Reading

    /// The stored document, or `nil` when there is none — the offline step's fallback is the ladder's
    /// older behaviour, so "no store" is a normal state rather than an error.
    static func readDocument() -> String? {
        guard let url = try? documentURL() else { return nil }
        return try? String(contentsOf: url, encoding: .utf8)
    }

    static func readAsset(path: String) -> Data? {
        guard let url = try? assetURL(path: path) else { return nil }
        return try? Data(contentsOf: url)
    }

    static func manifest() -> ShellStoreManifest? {
        guard let url = try? directory().appendingPathComponent(manifestName),
              let data = try? Data(contentsOf: url) else { return nil }
        return try? JSONDecoder().decode(ShellStoreManifest.self, from: data)
    }

    // MARK: - Writing

    /// Replace the stored shell.
    ///
    /// ⚠⚠ **The manifest is written LAST, and that is the commit point.** A launch reads the manifest to
    /// decide whether the store is usable, so a crash halfway through a refresh leaves the PREVIOUS
    /// manifest naming the PREVIOUS files — which are still on disk, because every asset name is
    /// content-hashed and a refresh therefore never overwrites one that is in use. So a half-finished
    /// refresh is not a half-finished shell: it is the old shell, which is a working app.
    ///
    /// ⚠ Each file is written to a sibling `.part` and renamed, which is the downloader's discipline
    /// (ADR-0008 D4) — a truncated document would otherwise be a shell that paints nothing, which is the
    /// failure this whole design exists to remove.
    @discardableResult
    static func write(document: String, assets: [(path: String, data: Data)], serverAddress: String) throws -> ShellStoreManifest {
        let root = try directory()
        let assetsRoot = root.appendingPathComponent(assetsDirectoryName, isDirectory: true)
        try FileManager.default.createDirectory(at: assetsRoot, withIntermediateDirectories: true)

        var stored: [ShellStoredAsset] = []
        for asset in assets {
            let url = try assetURL(path: asset.path)
            try writeAtomically(asset.data, to: url)
            stored.append(ShellStoredAsset(path: asset.path, bytes: asset.data.count))
        }

        let documentData = Data(document.utf8)
        try writeAtomically(documentData, to: root.appendingPathComponent(documentName))

        let manifest = ShellStoreManifest(serverAddress: serverAddress,
                                          documentBytes: documentData.count,
                                          assets: stored,
                                          storedAt: Date())
        try writeAtomically(try JSONEncoder().encode(manifest),
                            to: root.appendingPathComponent(manifestName))

        // ⚠ LAST, and only files nothing names: an older generation's assets are pruned once the manifest
        // no longer mentions them. The stored document is rewritten in place (it keeps its name), so the
        // pruning must never touch `shell.html`.
        prune(keeping: Set(stored.map(\.path)), in: assetsRoot)

        RKMLog.info("shell store: kept \(stored.count) asset(s), \(documentData.count) B document",
                    category: .web)
        return manifest
    }

    /// Everything the app is holding, removed. The offline step then falls back to the older behaviour.
    static func clear() {
        guard let root = try? directory() else { return }
        try? FileManager.default.removeItem(at: root)
        RKMLog.info("shell store: cleared", category: .web)
    }

    private static func writeAtomically(_ data: Data, to url: URL) throws {
        let part = url.appendingPathExtension("part")
        try data.write(to: part, options: .atomic)
        // ⚠ `replaceItemAt` is the same-class operation as the downloader's `os.replace`, and it is what
        // makes the file appear whole or not at all.
        if FileManager.default.fileExists(atPath: url.path) {
            _ = try FileManager.default.replaceItemAt(url, withItemAt: part)
        } else {
            try FileManager.default.moveItem(at: part, to: url)
        }
    }

    private static func prune(keeping paths: Set<String>, in assetsRoot: URL) {
        guard let names = try? FileManager.default.contentsOfDirectory(atPath: assetsRoot.path) else { return }
        for name in names {
            let path = ShellStoreRules.assetPrefix + name
            guard !paths.contains(path) else { continue }
            try? FileManager.default.removeItem(at: assetsRoot.appendingPathComponent(name))
        }
    }
}

enum ShellStoreError: Error, LocalizedError {
    /// ⚠ The one refusal an asset path can hit. It names the path, because a document that asked for
    /// something strange is worth seeing in the log.
    case unsafeAssetPath(String)

    var errorDescription: String? {
        switch self {
        case .unsafeAssetPath(let path): return "the shell asked to store an unsafe asset path: \(path)"
        }
    }
}
