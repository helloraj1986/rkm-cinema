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

        case "offline":
            // ⚠ PHASE B3'S ONLY WITNESS FOR THE NATIVE→PAGE DIRECTION. The offline bridge can be *told* to
            // send an event and it can fail silently (a global that was never installed, a page that
            // reloaded) — so the page reports what it actually received, back through this same redacting
            // channel. One redaction call site (`LOGGING.md` §6), and the report carries the SHAPE of the
            // event, never the loopback URL the event contains.
            switch payload["k"] as? String ?? "?" {
            case "page-received":
                let name = payload["e"] as? String ?? "?"
                let itemId = payload["itemId"] as? String ?? "-"
                let percent = payload["percent"] as? Int
                let hasUrl = payload["hasUrl"] as? Bool ?? false
                RKMLog.info("offline bridge · page received event=\(name) item=\(itemId)"
                            + (percent.map { " percent=\($0)" } ?? "")
                            + " carriesUrl=\(hasUrl)", category: .offline)
            case "command":
                let command = payload["cmd"] as? String ?? "?"
                let ok = payload["ok"] as? Bool ?? false
                let count = payload["count"] as? Int
                let detail = payload["detail"] as? String
                RKMLog.info("offline bridge · command \(command) ok=\(ok)"
                            + (count.map { " count=\($0)" } ?? "")
                            + (detail.map { " — \($0)" } ?? ""), category: .offline)
            case "availability":
                let present = payload["present"] as? Bool ?? false
                let version = payload["version"] as? Int
                RKMLog.info("offline bridge · the page sees the bridge: \(present)"
                            + (version.map { " v\($0)" } ?? ""), category: .offline)
            default:
                RKMLog.verbose("offline bridge · unhandled page report", category: .offline)
            }

        default:
            RKMLog.verbose("unhandled bridge event: \(kind)", category: .web, correlation: identifier)
        }
    }

    private func correlation(from raw: String?) -> CorrelationID? {
        guard let raw else { return nil }
        return CorrelationID(rawValue: raw.lowercased())
    }
}

// ⚠ There used to be a `WeakScriptMessageHandler` here, forwarding to the bridge through a weak
// reference. It was removed because it caused a silent, total failure: with a weak proxy **nothing
// retained the bridge**, so it deallocated as soon as `makeUIView` returned and every JavaScript
// event was dropped — a film played while the debug HUD's request log stayed empty.
//
// ⚠ And the retain cycle it was guarding against does not exist: `WKUserContentController` does
// retain its handler, but `WebBridge` holds its model **weakly** and the model holds the web view
// **weakly**, so the chain terminates and the bridge simply dies with the web view that owns it.
// Register the bridge directly — see `WebShellView.makeUIView`.
