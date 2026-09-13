import Foundation
import WebKit
import RKMServerKit

/// Receives the structured events the injected script sends (`WebInstrumentation`), and turns each
/// into one log line — through the **native** redactor.
///
/// ⚠ The events arrive with the path the page actually requested, redaction happens here, and the
/// correlation id the page minted is carried through unchanged. That is what lets a HUD id in a
/// screenshot be grepped out of the file: both halves use the same six hex characters.
final class WebBridge: NSObject, WKScriptMessageHandler {

    weak var model: WebShellModel?

    func userContentController(_ userContentController: WKUserContentController,
                              didReceive message: WKScriptMessage) {
        guard message.name == WebInstrumentation.handlerName else { return }
        guard let json = message.body as? String,
              let data = json.data(using: .utf8),
              let payload = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
        else {
            RKMLog.verbose("bridge message could not be read", category: .web)
            return
        }
        handle(payload)
    }

    private func handle(_ payload: [String: Any]) {
        guard let kind = payload["t"] as? String else { return }
        let identifier = correlation(from: payload["id"] as? String)

        switch kind {

        case "net":
            // ⚠ The request line is built by `RKMLog.request` — the single place that format
            // exists, and the single place redaction happens.
            RKMLog.request(
                correlation: identifier ?? CorrelationID.next(),
                method: payload["m"] as? String ?? "GET",
                url: payload["u"] as? String ?? "",
                status: payload["s"] as? Int,
                milliseconds: payload["ms"] as? Int,
                bytes: payload["b"] as? Int,
                error: payload["err"] as? String
            )

        case "console":
            let level = payload["lv"] as? String ?? "log"
            let text = payload["m"] as? String ?? ""
            if level == "error" {
                RKMLog.error("console.error: \(text)", category: .web, correlation: identifier)
            } else {
                RKMLog.verbose("console.\(level): \(text)", category: .web, correlation: identifier)
            }

        case "jserror":
            let message = payload["m"] as? String ?? ""
            let source = payload["s"] as? String ?? "?"
            let line = payload["ln"] as? Int ?? 0
            RKMLog.error("JS error: \(message) (\(source):\(line))", category: .web, correlation: identifier)

        case "rejection":
            RKMLog.error("unhandled promise rejection: \(payload["m"] as? String ?? "")",
                         category: .web, correlation: identifier)

        case "dialog":
            // Loud on purpose: the page is asking for something the shell cannot give it, and a
            // silent `confirm()` is a hang with no explanation.
            RKMLog.error("page called window.\(payload["k"] as? String ?? "?")() — WKWebView does not present these without a WKUIDelegate",
                         category: .web, correlation: identifier)

        case "ready":
            let width = payload["w"] as? Int ?? 0
            let height = payload["h"] as? Int ?? 0
            RKMLog.info("page ready \(payload["hr"] as? String ?? "") · viewport \(width)x\(height) · \(payload["ua"] as? String ?? "")",
                        category: .web)
            model?.refreshCookies()

        default:
            RKMLog.verbose("unhandled bridge event: \(kind)", category: .web, correlation: identifier)
        }
    }

    private func correlation(from raw: String?) -> CorrelationID? {
        guard let raw else { return nil }
        return CorrelationID(rawValue: raw.lowercased())
    }
}

/// ⚠ `WKUserContentController` retains its message handlers **strongly**, the controller is owned
/// by the configuration, and the configuration is owned by the web view — so registering the
/// bridge directly would form a cycle that keeps the entire web view (and the page in it) alive
/// for the life of the app. This forwards weakly instead.
final class WeakScriptMessageHandler: NSObject, WKScriptMessageHandler {

    weak var target: WKScriptMessageHandler?

    init(_ target: WKScriptMessageHandler) {
        self.target = target
    }

    func userContentController(_ userContentController: WKUserContentController,
                              didReceive message: WKScriptMessage) {
        target?.userContentController(userContentController, didReceive: message)
    }
}
