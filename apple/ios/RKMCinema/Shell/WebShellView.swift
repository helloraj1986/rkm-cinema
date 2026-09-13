import SwiftUI
import UIKit
import WebKit
import RKMServerKit

/// The `WKWebView` itself — ~nothing but configuration and delegation.
///
/// ⚠ Not Capacitor, and not a bundled copy of the web app: the frame loads the **live** UI from the
/// address the person typed, which is why every future change to `frontend/` appears on the iPad
/// with no rebuild and no store release (`apple/README.md`).
struct WebShellView: UIViewRepresentable {

    @ObservedObject var model: WebShellModel

    func makeCoordinator() -> Coordinator {
        Coordinator(model: model, address: model.address)
    }

    func makeUIView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()

        // ⚠ NON-NEGOTIABLE (`apple/ios/README.md`): the player is a custom `<video>` with
        // `playsInline` + `requestFullscreen`. Without this, iOS hijacks it into its native
        // fullscreen player and the custom transport — seek bar, quality, and the audio/subtitle
        // pickers — never renders at all.
        configuration.allowsInlineMediaPlayback = true

        // The other half of the same requirement: it lets the *page's own* fullscreen request work,
        // so the page keeps its own UI instead of iOS taking the screen over.
        configuration.preferences.isElementFullscreenEnabled = true

        // Persistent, like Safari — the session cookie has to survive a relaunch, or he signs in
        // every single time.
        configuration.websiteDataStore = .default()

        let controller = configuration.userContentController
        let bridge = WebBridge()
        bridge.model = model
        // ⚠ Registered DIRECTLY — and this is the fix for a real bug found on the first run, not a
        // style choice. This was previously registered through a weak proxy, to avoid a retain cycle
        // that does not exist (`WebBridge` holds its model weakly, and the model holds the web view
        // weakly). With a weak proxy **nothing retained the bridge**, so it was deallocated the
        // instant `makeUIView` returned and every JavaScript event was dropped in silence: no
        // console capture, no `net` lines, no `page ready`. It presented as a film playing with an
        // empty request log in the debug HUD — which is exactly what the HUD exists to reveal.
        controller.add(bridge, name: WebInstrumentation.handlerName)
        controller.addUserScript(WebInstrumentation.userScript())

        let webView = WKWebView(frame: .zero, configuration: configuration)
        webView.navigationDelegate = context.coordinator
        webView.uiDelegate = context.coordinator
        webView.allowsBackForwardNavigationGestures = true

        // ⚠ The single best debugging lever on the whole iOS app (`LOGGING.md` §3): with this on he
        // attaches Safari → Develop → [his iPad] from the Mac and gets the real DOM, console,
        // network tab and JS errors — which no screenshot can compete with. iOS 16.4+.
        if #available(iOS 16.4, *) {
            webView.isInspectable = true
        }

        logConfiguration(configuration, webView: webView)

        // Attaches and starts the first load, so the model's state and the view's lifetime are the
        // same story rather than two.
        model.attach(webView)
        return webView
    }

    func updateUIView(_ uiView: WKWebView, context: Context) {
        // Nothing to push. The address only changes by leaving the shell, and `AppRootView` gives
        // that a different identity so the web view is rebuilt rather than reused.
    }

    /// ⚠ Dumps the flags that decide whether the player behaves like it does in a desktop browser.
    /// `mediaTypesRequiringUserAction` in particular is **left at its default** — deliberately,
    /// because it is not in the spec's non-negotiables. If a *programmatic* `play()` is refused on
    /// the iPad, this is the value to change, and the log already carries it.
    private func logConfiguration(_ configuration: WKWebViewConfiguration, webView: WKWebView) {
        var flags = [
            "allowsInlineMediaPlayback=\(configuration.allowsInlineMediaPlayback)",
            "mediaTypesRequiringUserAction=\(configuration.mediaTypesRequiringUserActionForPlayback.rawValue)",
            "elementFullscreen=\(configuration.preferences.isElementFullscreenEnabled)",
            "websiteDataStore=\(configuration.websiteDataStore.isPersistent ? "persistent" : "ephemeral")",
            "backForwardGestures=\(webView.allowsBackForwardNavigationGestures)",
        ]
        if #available(iOS 16.4, *) {
            flags.append("isInspectable=\(webView.isInspectable)")
        }
        RKMLog.info("web config: " + flags.joined(separator: " "), category: .web)
    }

    // MARK: - Delegation

    final class Coordinator: NSObject, WKNavigationDelegate, WKUIDelegate {

        private weak var model: WebShellModel?
        /// The only host the shell treats as "ours".
        private let host: String

        init(model: WebShellModel, address: ServerAddress) {
            self.model = model
            host = address.host.lowercased()
        }

        // MARK: Navigation policy

        func webView(_ webView: WKWebView,
                     decidePolicyFor navigationAction: WKNavigationAction,
                     decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            guard let url = navigationAction.request.url else {
                decisionHandler(.allow)
                return
            }

            let scheme = url.scheme?.lowercased() ?? ""
            if scheme != "http" && scheme != "https" {
                // `blob:`, `data:`, `about:` — the page's own business, and the player uses them.
                decisionHandler(.allow)
                return
            }

            let isMainFrame = navigationAction.targetFrame?.isMainFrame ?? false
            if isMainFrame, url.host?.lowercased() != host {
                // ⚠ An off-site link must not turn the shell into a blank page with no way back.
                // Note this is the *opposite* of the behaviour that got Capacitor rejected: the
                // address the user typed is always allowed — only a genuinely foreign host leaves
                // for Safari.
                RKMLog.info("off-site link → Safari: \(url.absoluteString)", category: .nav)
                UIApplication.shared.open(url)
                decisionHandler(.cancel)
                return
            }

            decisionHandler(.allow)
        }

        func webView(_ webView: WKWebView, didStartProvisionalNavigation navigation: WKNavigation!) {
            model?.didStartProvisionalNavigation(url: webView.url)
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            model?.didFinish(url: webView.url)
        }

        // ⚠ Both failure callbacks matter, and both describe the **main** navigation: a typo'd
        // address fails provisionally, a dropped connection mid-flight fails later.
        func webView(_ webView: WKWebView,
                     didFailProvisionalNavigation navigation: WKNavigation!,
                     withError error: Error) {
            model?.didFail(error: error, isMainFrame: true)
        }

        func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
            model?.didFail(error: error, isMainFrame: true)
        }

        func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
            model?.contentProcessDidTerminate()
        }

        func webView(_ webView: WKWebView,
                     didReceive challenge: URLAuthenticationChallenge,
                     completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void) {
            // Logged, never overridden. A certificate problem has to surface as a failure we can
            // read in the log — silently trusting a bad certificate is not an option.
            RKMLog.info("auth challenge: \(challenge.protectionSpace.authenticationMethod) host=\(challenge.protectionSpace.host)",
                        category: .net)
            completionHandler(.performDefaultHandling, nil)
        }

        // MARK: UI delegate

        /// ⚠ `target="_blank"` appears in the web app (`DiscoverView`, `WatchlistDetail`). Without
        /// this delegate method WKWebView does **nothing at all** with those links — they are
        /// simply dead, with no error anywhere.
        func webView(_ webView: WKWebView,
                     createWebViewWith configuration: WKWebViewConfiguration,
                     for navigationAction: WKNavigationAction,
                     windowFeatures: WKWindowFeatures) -> WKWebView? {
            guard let url = navigationAction.request.url else { return nil }

            let path = url.path.isEmpty ? (url.host ?? "") : url.path
            RKMLog.info("new-window navigation intercepted → \(path)", category: .nav)

            if url.host?.lowercased() == host {
                // Our own links stay in the shell.
                webView.load(URLRequest(url: url))
            } else {
                UIApplication.shared.open(url)
            }
            return nil
        }
    }
}
