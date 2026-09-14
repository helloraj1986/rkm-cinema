import Foundation
import WebKit
import RKMServerKit

/// ⚠ **SPIKE ONLY — the other half of E1.** Not to be merged.
///
/// The elegant answer to "how does the page play a file in the app's container" is a custom scheme
/// handler: register `rkm-offline:`, serve the bytes, no port, no server. `NATIVE_FEEL_AND_OFFLINE_PLAN`
/// §4.1 rejects it *in advance* — WebKit's media stack runs out of process and does not route media
/// through an app's scheme handler — but the plan's own rule is that an assumption this load-bearing
/// gets measured before anything is designed on it, so the spike registers one and asks the same
/// `<video>` to play from it.
///
/// Expected outcome: the media element errors (and the error is the answer). If it *does* play, the
/// offline design gets simpler and cheaper and the plan should be rewritten accordingly.
final class SpikeSchemeHandler: NSObject, WKURLSchemeHandler {

    static let scheme = "rkm-offline"

    private let root: URL

    init(root: URL) {
        self.root = root
    }

    /// The URL the probe page asks for, built from the same file the loopback server serves.
    static func probeURL() -> URL? {
        URL(string: "\(scheme)://probe.mp4")
    }

    func webView(_ webView: WKWebView, start urlSchemeTask: WKURLSchemeTask) {
        let name = urlSchemeTask.request.url?.lastPathComponent ?? "probe.mp4"
        let file = root.appendingPathComponent(name)
        RKMLog.info("scheme handler: requested \(name)", category: .net)

        guard let data = try? Data(contentsOf: file) else {
            RKMLog.error("scheme handler: \(name) is not in the container", category: .net)
            urlSchemeTask.didFailWithError(
                NSError(domain: "rkm.spike.offline", code: 404,
                        userInfo: [NSLocalizedDescriptionKey: "no such offline file"])
            )
            return
        }

        // ⚠ No `Range` support here on purpose. A scheme handler that lies about byte ranges would
        // turn a seeking failure into a *silent* whole-file re-read, and the whole question is
        // whether seeking works. The log says what was served.
        guard let response = HTTPURLResponse(
            url: urlSchemeTask.request.url ?? URL(string: "\(Self.scheme)://probe.mp4")!,
            statusCode: 200,
            httpVersion: "HTTP/1.1",
            headerFields: ["Content-Type": "video/mp4", "Content-Length": "\(data.count)"]
        ) else {
            urlSchemeTask.didFailWithError(
                NSError(domain: "rkm.spike.offline", code: 500,
                        userInfo: [NSLocalizedDescriptionKey: "could not build a response"])
            )
            return
        }
        RKMLog.info("scheme handler: serving \(data.count) B as 200 (no Range support)", category: .net)
        urlSchemeTask.didReceive(response)
        urlSchemeTask.didReceive(data)
        urlSchemeTask.didFinish()
    }

    func webView(_ webView: WKWebView, stop urlSchemeTask: WKURLSchemeTask) {
        RKMLog.verbose("scheme handler: task stopped", category: .net)
    }
}
