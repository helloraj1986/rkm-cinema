import Foundation
import WebKit
import RKMServerKit

/// Serves the app's own shell bytes to the page — `docs/adr/ADR-0012-cold-launch-offline-shell.md` **D7**,
/// plan §0c phase S2.
///
/// ⚠ **Why a scheme handler, when the document itself keeps the server's origin.** The document is handed
/// to WebKit with the SERVER as its base URL (so the session cookie, same-origin `/api/*` and A1's
/// persisted `localStorage` all go on working — measured, `apple/SPIKE_SHELL_ORIGIN.md`). What sits at a
/// custom scheme is only the parts of the document the app keeps itself, which are its two content-hashed
/// assets. So the page's origin never moves and this handler is the only thing that knows the app has a
/// copy at all.
///
/// ⚠⚠ **E1 IS NOT CONTRADICTED HERE.** That spike measured a `WKURLSchemeHandler` OUT for **media**
/// (`mediaError=code=4` *with* the bytes served) — WebKit's media stack runs out of process and does not
/// route media through an app handler. A module script is a different path through the same framework,
/// and it was measured **separately, on the device, and it works** (`serving /probe.js as
/// text/javascript, 106 B` → `moduleNow: ok @ …`).
final class ShellAssetSchemeHandler: NSObject, WKURLSchemeHandler {

    static let scheme = "rkm-asset"

    /// ⚠⚠ **A STRONGLY-HELD SINGLETON, AND THAT IS LOAD-BEARING.** `WKWebViewConfiguration` does not
    /// promise to keep a scheme handler alive, and a deallocated one is **not an error**: every request
    /// simply never arrives, which presents as a page whose script silently never loads
    /// (`apple/WORKFLOW.md` §8b — the second time this project has been bitten by retention).
    static let shared = ShellAssetSchemeHandler()

    /// The one authority this handler answers for. ⚠ Fixed, so a URL cannot point the app at a second
    /// host, and so `ShellStoreRules.storedURL` and this file cannot drift apart unnoticed.
    static let host = "app"

    private override init() { super.init() }

    func webView(_ webView: WKWebView, start urlSchemeTask: WKURLSchemeTask) {
        guard let url = urlSchemeTask.request.url else {
            urlSchemeTask.didFailWithError(failure("no url"))
            return
        }
        // ⚠ The store's own layout decides what is servable, so the handler cannot be talked into reading
        // a path the store refused to write (`isStorableAssetPath`).
        let path = url.path

        guard let data = ShellStore.readAsset(path: path), !data.isEmpty else {
            RKMLog.error("shell assets: \(path) is not in the store", category: .web)
            urlSchemeTask.didFailWithError(failure("the shell asset \(path) is not stored"))
            return
        }

        let headers = [
            "Content-Type": contentType(for: path),
            "Content-Length": "\(data.count)",
            // ⚠ A module script is fetched in CORS mode, so without this header WebKit refuses it — and
            // the refusal looks exactly like "custom schemes do not carry scripts".
            "Access-Control-Allow-Origin": "*",
            // ⚠ Insurance for a future page with COEP on: harmless otherwise.
            "Cross-Origin-Resource-Policy": "cross-origin",
            // ⚠ THE STORE is the cache. A WebView cache for these bytes is precisely what the device
            // showed cannot be relied on (it refuses a ~1.1 MB response), and a second staleness rule
            // would be a second way for the document and its script to disagree.
            "Cache-Control": "no-store",
            // ⚠ No `Content-Encoding`: the stored bytes are what URLSession DECODED, so claiming gzip
            // here would be a lie the browser would act on.
        ]

        guard let response = HTTPURLResponse(url: url, statusCode: 200, httpVersion: "HTTP/1.1",
                                             headerFields: headers) else {
            urlSchemeTask.didFailWithError(failure("could not build a response"))
            return
        }
        RKMLog.verbose("shell assets: serving \(path) as \(contentType(for: path)), \(data.count) B", category: .web)
        urlSchemeTask.didReceive(response)
        urlSchemeTask.didReceive(data)
        urlSchemeTask.didFinish()
    }

    func webView(_ webView: WKWebView, stop urlSchemeTask: WKURLSchemeTask) {
        RKMLog.verbose("shell assets: task stopped", category: .web)
    }

    /// ⚠ A whitelist, matching `ShellStoreRules.storableExtensions`: the store can only hold these, so
    /// anything else reaching here is a bug rather than a media type to guess at.
    private func contentType(for path: String) -> String {
        switch (path as NSString).pathExtension.lowercased() {
        case "js", "mjs": return "text/javascript"
        case "css": return "text/css"
        default: return "application/octet-stream"
        }
    }

    private func failure(_ reason: String) -> NSError {
        NSError(domain: "rkm.shell.assets", code: 404,
                userInfo: [NSLocalizedDescriptionKey: reason])
    }
}
