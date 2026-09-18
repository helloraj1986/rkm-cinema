import Foundation

/// ⭐ **S1 — the app-owned shell's RULES, pure.** `docs/adr/ADR-0012-cold-launch-offline-shell.md` D7/D8,
/// plan `docs/OFFLINE_SHELL_PLAN.md` §0c.
///
/// The device measured why this exists: WebKit will not STORE a response larger than ~5% of its disk
/// cache, so the shell's ~1.1 MB bundle never came back with the document, and a cold launch with the
/// Wi-Fi off painted nothing. The spike then measured that the app CAN serve the shell itself — the
/// document handed over with the server as its base URL keeps the server's origin, a module script loads
/// from a `WKURLSchemeHandler`, and that document sees the app's own `localStorage` (so A1's rows and
/// everything else stay put).
///
/// This file is the part of that which decides something, so it is pure and `check-offline-core.py` RUNS
/// it on Linux; the native half (fetching the bytes, serving the scheme, choosing the step) only carries
/// these answers out.
///
/// ⚠⚠ **AND THE ASSET SET IS MEASURED, NOT ASSUMED: the built app has NO dynamic imports and
/// `frontend/dist/assets/` holds exactly two files** — `index-*.js` and `index-*.css`, the two the
/// document names. So "what must the store hold" is answerable from the document alone (plus one level of
/// insurance below, for the day a build splits the bundle).
enum ShellStoreRules {

    /// Vite's content-hashed output directory. ⚠ A path OUTSIDE this is deliberately not storable: the
    /// app's own code lives here, and everything else the document mentions (`/favicon.svg`, the Google
    /// Fonts link, anything `/api/`) is either not needed offline or must keep going to the server.
    static let assetPrefix = "/assets/"

    /// Extensions a stored asset may have. ⚠ A whitelist, so a future `<script src="/assets/x.svg">`
    /// cannot quietly enter the store as something the scheme handler would then have to guess at.
    static let storableExtensions: Set<String> = ["js", "css", "mjs"]

    /// ⚠⚠ **THE PATH RULE, and it is a security rule, not tidiness.** These strings come out of a
    /// document fetched over the network and are then used as FILE NAMES inside the app's container — the
    /// same class of risk as `OfflineIdentifier` (ADR-0008). A plain name directly under `/assets/`:
    /// no subdirectories, no `..`, no empty name, no whitespace.
    static func isStorableAssetPath(_ path: String) -> Bool {
        guard path.hasPrefix(assetPrefix) else { return false }
        let name = String(path.dropFirst(assetPrefix.count))
        guard !name.isEmpty, !name.contains("/"), !name.contains("..") else { return false }
        let allowed = CharacterSet(charactersIn: "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
        guard name.unicodeScalars.allSatisfy({ allowed.contains($0) }) else { return false }
        let ext = (name as NSString).pathExtension.lowercased()
        return storableExtensions.contains(ext)
    }

    /// Every asset path a shell needs, **in document order, de-duplicated**.
    ///
    /// ⚠ `javascriptBodies` is the one level of insurance: Vite inlines its module-preload map and any
    /// dynamic `import()` target INSIDE the bundle, so a build that ever splits the app would name assets
    /// the document does not. Today nothing splits (measured), and the rule costs ten lines.
    ///
    /// ⚠ Refused, deliberately: absolute `http(s)://` URLs, protocol-relative `//host/…`, `data:`, and any
    /// path that is not `/assets/<name>.<js|css|mjs>`. A document that mentions them keeps mentioning them
    /// — the offline shell simply does not promise them.
    static func requiredAssets(document: String, javascriptBodies: [String] = []) -> [String] {
        var seen = Set<String>()
        var ordered: [String] = []
        for text in [document] + javascriptBodies {
            for path in matches(in: text) where isStorableAssetPath(path) {
                if seen.insert(path).inserted { ordered.append(path) }
            }
        }
        return ordered
    }

    /// `/assets/index-ABC.js` → `rkm-asset://app/assets/index-ABC.js`.
    ///
    /// ⚠ The host part is fixed (`app`) so the scheme handler has exactly one authority to answer, and the
    /// path is kept verbatim so the URL still says which asset it is.
    static func storedURL(path: String, scheme: String) -> String {
        "\(scheme)://app\(path)"
    }

    /// The document, with every reference to a stored asset pointed at the app's own scheme — and
    /// **nothing else touched**.
    ///
    /// ⚠ Only the QUOTED forms are replaced (`"/assets/…"`, `'/assets/…'`), because that is where the
    /// reference always is: `src=`, `href=`, and the strings inside the bundle. A bare `/assets/` in prose
    /// is not a reference.
    /// ⚠ Idempotent by construction: a document that has already been rewritten no longer contains the
    /// quoted prefix, so a second pass changes nothing — which is what makes storing the REWRITTEN
    /// document safe (and a check asserts it).
    static func rewritten(document: String, scheme: String) -> String {
        var out = document
        for quote in ["\"", "'"] {
            for path in requiredAssets(document: document) {
                out = out.replacingOccurrences(of: "\(quote)\(path)\(quote)",
                                               with: "\(quote)\(storedURL(path: path, scheme: scheme))\(quote)")
            }
        }
        return out
    }

    /// All `…/assets/<name>.<ext>` occurrences in a blob of text, whether or not they are quoted.
    private static func matches(in text: String) -> [String] {
        let pattern = "\(assetPrefix)[A-Za-z0-9._-]+"
        guard let regex = try? NSRegularExpression(pattern: pattern) else { return [] }
        let range = NSRange(text.startIndex..<text.endIndex, in: text)
        return regex.matches(in: text, range: range).compactMap {
            Range($0.range, in: text).map { String(text[$0]) }
        }
    }
}

/// One stored asset: the path it is served at, and how many bytes it was when it was stored.
///
/// ⚠ The bytes are recorded so a half-written file is detectable *without* reading it: the store writes
/// atomically (temp + rename, the downloader's discipline), and this is the cheap second opinion.
struct ShellStoredAsset: Equatable, Codable {
    let path: String
    let bytes: Int
}

/// What the app is holding for one server: the document, the assets it named, and when it was taken.
///
/// ⚠ `serverAddress` is not decoration. The plan's own rule (§1) is that a store fetched from *another*
/// server is dropped rather than rendered — a shell is not a library, and the wrong app against the right
/// server (or the reverse) is worse than no shell at all.
struct ShellStoreManifest: Equatable, Codable {
    /// ⚠ Bumped like the downloader's manifest: a build that changes the stored shape DROPS the old one
    /// rather than decoding half of it.
    static let currentVersion = 1

    let version: Int
    let serverAddress: String
    let documentBytes: Int
    let assets: [ShellStoredAsset]
    let storedAt: Date

    init(version: Int = ShellStoreManifest.currentVersion,
         serverAddress: String,
         documentBytes: Int,
         assets: [ShellStoredAsset],
         storedAt: Date) {
        self.version = version
        self.serverAddress = serverAddress
        self.documentBytes = documentBytes
        self.assets = assets
        self.storedAt = storedAt
    }
}

/// What the offline step should do, and the ONLY two answers it may give.
enum ShellStoreChoice: Equatable {
    /// ⭐ The store holds a complete, matching shell — hand the document to the page.
    case storedShell
    /// ⚠ Degrade, never crash: no store, a stale one, or an incomplete one ⇒ the plain cache-first URL
    /// load the ladder shipped first (which on its own is not enough to paint, but is not worse either).
    case cacheFirstURL
}

extension ShellStoreRules {

    /// Is the store usable for THIS launch?
    ///
    /// ⚠ Four conditions, and each is a separate check in the gate because each is a way the offline shell
    /// paints the WRONG THING rather than nothing:
    ///   * a manifest exists at all;
    ///   * its version is the one this build understands (a newer one is refused, not decoded);
    ///   * it was fetched for the address now in use (a different server ⇒ a different app);
    ///   * **every asset the document names is present** — the pair rule (D8). A stored document whose
    ///     bundle is missing is exactly the blank screen this whole design exists to fix.
    static func choice(manifest: ShellStoreManifest?,
                       requiredAssets: [String],
                       serverAddress: String) -> ShellStoreChoice {
        guard let manifest else { return .cacheFirstURL }
        guard manifest.version == ShellStoreManifest.currentVersion else { return .cacheFirstURL }
        guard manifest.serverAddress == serverAddress else { return .cacheFirstURL }
        guard manifest.documentBytes > 0 else { return .cacheFirstURL }
        let stored = Set(manifest.assets.map(\.path))
        guard requiredAssets.allSatisfy({ stored.contains($0) }) else { return .cacheFirstURL }
        return .storedShell
    }
}
