import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif
import RKMServerKit

/// Keep the app-owned shell current — `docs/adr/ADR-0012-cold-launch-offline-shell.md` **D8**, plan §0c
/// phase S2.
///
/// ⚠ **Called after a successful LIVE load, and only there.** That is the one moment the app knows both
/// that the server is answering and which shell it is serving, so a refresh is a diff against a shell the
/// page is already running — not a guessed download. It never runs on the offline step (there is nothing
/// to fetch) and never on a failure (there is nothing to trust).
///
/// ⚠⚠ **A refresh is ALL-OR-NOTHING, because a half-updated store is worse than an old one.** If the
/// document is fetched but one asset is not — a deploy in flight, a 404, a dropped connection — the store
/// is left exactly as it was. `ShellStore.write` commits with the manifest, and this returns without
/// writing, so the previous shell stays valid and the next online launch tries again.
///
/// ⚠ **No credentials are used, and that is not an oversight.** The shell comes from nginx, not from the
/// api: the document and `/assets/*` are served to anyone who can reach the port (measured — the app
/// loads its UI before anybody signs in). Nothing here should change if that ever changes.
enum ShellFetcher {

    enum Outcome: Equatable {
        /// ⭐ The store was replaced: the new document and its assets are on disk.
        case stored(assets: Int)
        /// The store already IS this shell — the document is byte-identical and every asset is present.
        case unchanged
        /// ⚠ Nothing was written. The store (if any) is untouched.
        case failed(String)
    }

    /// The whole refresh, `async` because the caller is a `Task` hung off `didFinish`.
    ///
    /// ⚠ Sequential on purpose: the document must name the assets BEFORE they are fetched (that is what
    /// makes the pair a pair), and two of them is not a concurrency problem.
    static func refresh(address: ServerAddress) async -> Outcome {
        do {
            let (documentData, documentResponse) = try await URLSession.shared.data(from: address.url)
            guard let http = documentResponse as? HTTPURLResponse, http.statusCode == 200 else {
                return .failed("the document answered \(describe(documentResponse))")
            }
            guard let document = String(data: documentData, encoding: .utf8), !document.isEmpty else {
                return .failed("the document came back empty or unreadable")
            }

            let required = ShellStoreRules.requiredAssets(document: document)
            guard !required.isEmpty else {
                return .failed("the document names no assets — refusing to store a shell without its code")
            }

            let rewritten = ShellStoreRules.rewritten(document: document, scheme: ShellAssetSchemeHandler.scheme)

            // ⭐ Is there anything to do? Byte-identical document AND every asset already on disk is the
            // common case on a normal launch, and it costs one document fetch (1.6 KB) instead of pulling
            // the bundle again.
            if let stored = ShellStore.readDocument(), stored == rewritten,
               required.allSatisfy({ ShellStore.readAsset(path: $0) != nil }) {
                return .unchanged
            }

            var assets: [(path: String, data: Data)] = []
            for path in required {
                guard let url = URL(string: path, relativeTo: address.url) else {
                    return .failed("the document named an asset that is not a URL: \(path)")
                }
                let (data, response) = try await URLSession.shared.data(from: url)
                guard let assetHTTP = response as? HTTPURLResponse, assetHTTP.statusCode == 200, !data.isEmpty else {
                    // ⚠ No partial store. This is the deploy-in-flight case, and it is the one that would
                    // otherwise leave a document naming an asset the app does not hold.
                    return .failed("asset \(path) answered \(describe(response)) — store left untouched")
                }
                assets.append((path: path, data: data))
            }

            let manifest = try ShellStore.write(document: rewritten,
                                                assets: assets,
                                                serverAddress: ShellStore.addressKey(for: address))
            return .stored(assets: manifest.assets.count)
        } catch {
            return .failed(error.localizedDescription)
        }
    }

    /// ⚠ A status when there is one, and the honest words when there is not — "did not work" is not a
    /// diagnosis.
    private static func describe(_ response: URLResponse?) -> String {
        guard let http = response as? HTTPURLResponse else { return "no http response" }
        return "HTTP \(http.statusCode)"
    }
}
