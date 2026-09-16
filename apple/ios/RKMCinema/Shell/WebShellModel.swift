import Foundation
import SwiftUI
import WebKit
// ⚠ Combine carries `ObservableObject` / `@Published` — see the note in AppModel.swift. Needed on
// the iOS 26 SDK even though SwiftUI is imported.
import Combine
import RKMServerKit

/// The shell's state: is the page loading, what is it, and did the load fail.
///
/// ⚠ The failure path is the point of this type. A `WKWebView` that fails to load shows a blank
/// page and says nothing, so a typo'd address — or a server that is simply off — looks
/// indistinguishable from a broken app (`apple/ios/README.md`).
final class WebShellModel: ObservableObject {

    enum LoadState: Equatable {
        case idle
        case loading
        case loaded
        case failed(String)

        var label: String {
            switch self {
            case .idle: return "idle"
            case .loading: return "loading"
            case .loaded: return "loaded"
            case .failed(let detail): return "failed (\(detail))"
            }
        }
    }

    @Published private(set) var state: LoadState = .idle
    @Published private(set) var pageTitle: String = ""
    @Published private(set) var pagePath: String = ""
    @Published private(set) var cookieSummary: String = "unknown"
    @Published private(set) var loadAttempts = 0

    let address: ServerAddress

    /// Called on a **main-frame** navigation failure. `AppModel` turns this into the unreachable
    /// state; the shell never decides for itself to give up on a subresource.
    var onUnreachable: ((UnreachableInfo) -> Void)?

    private(set) weak var webView: WKWebView?

    /// `WebKitErrorDomain` 102 — "frame load interrupted by policy change". WebKit cancels loads
    /// for all sorts of benign reasons, and flipping to a scary screen on one of those would be
    /// worse than the blank page this is meant to fix.
    private static let webKitFrameLoadInterrupted = 102

    init(address: ServerAddress) {
        self.address = address
    }

    // MARK: - Loading

    func attach(_ webView: WKWebView) {
        self.webView = webView
        load()
    }

    func load() {
        guard let webView else { return }
        loadAttempts += 1
        let identifier = CorrelationID.next()
        state = .loading
        RKMLog.info("load #\(loadAttempts) → \(address.displayString)", category: .nav, correlation: identifier)
        webView.load(URLRequest(url: address.url))
    }

    func reload() {
        guard let webView else { return }
        RKMLog.info("reload requested", category: .nav)
        webView.reload()
    }

    // MARK: - Navigation delegate callbacks

    func didStartProvisionalNavigation(url: URL?) {
        state = .loading
        RKMLog.verbose("didStartProvisionalNavigation \(describe(url))", category: .nav)
    }

    func didFinish(url: URL?) {
        state = .loaded
        pageTitle = webView?.title ?? ""
        pagePath = describe(url)
        RKMLog.info("didFinish \(pagePath) · title \"\(pageTitle)\"", category: .nav)
        refreshCookies(verbose: false)
        // ⚠ Phase B3: a loaded page is a page that knows nothing. This is what makes the downloads it
        // already has appear on screen the moment it can draw them — and it is production behaviour, not
        // probe scaffolding.
        OfflineBridge.shared.pageDidLoad()
        #if DEBUG
        // ⚠ Phase B3's live probe hangs off this: its bridge half needs a LIVE page (it installs a listener
        // in it), and the page is only live once a navigation has finished. No-op without the launch
        // argument — see `Debug/OfflineServerProbe.swift`.
        OfflineServerProbe.startIfRequested()
        #endif
    }

    func didFail(error: Error, isMainFrame: Bool) {
        let nsError = error as NSError
        // ⚠ The domain and code are the diagnosis — "The operation couldn't be completed" is not.
        let detail = "\(nsError.domain) \(nsError.code) — \(nsError.localizedDescription)"

        if isBenignCancellation(nsError) {
            RKMLog.verbose("navigation cancelled (benign, ignored): \(detail)", category: .nav)
            return
        }

        RKMLog.error("navigation failed: \(detail) (main frame: \(isMainFrame))", category: .nav)

        guard isMainFrame else { return }
        state = .failed(detail)
        onUnreachable?(UnreachableInfo(address: address, detail: detail))
    }

    /// A crashed web-content process is its own kind of blank screen, and it is common enough
    /// under memory pressure with a video player on board. Reload rather than sit there.
    func contentProcessDidTerminate() {
        RKMLog.error("web content process terminated — reloading", category: .web)
        reload()
    }

    private func isBenignCancellation(_ error: NSError) -> Bool {
        if error.domain == NSURLErrorDomain && error.code == NSURLErrorCancelled { return true }
        if error.domain == "WebKitErrorDomain" && error.code == Self.webKitFrameLoadInterrupted { return true }
        return false
    }

    private func describe(_ url: URL?) -> String {
        guard let url else { return "?" }
        return url.path.isEmpty ? "/" : url.path
    }

    // MARK: - Cookies

    /// ⚠ **Count and names only, never values** (`LOGGING.md` §3). Inside a web view the session
    /// cookie is otherwise invisible, and "did it land?" is the first question when sign-in
    /// misbehaves.
    func refreshCookies(verbose: Bool = true) {
        guard let store = webView?.configuration.websiteDataStore else { return }
        store.httpCookieStore.getAllCookies { [weak self] cookies in
            let summary = LogRedactor.redact(cookieNames: cookies.map(\.name).sorted())
            self?.cookieSummary = summary
            if verbose {
                RKMLog.verbose("cookies: \(summary)", category: .auth)
            } else {
                RKMLog.info("cookies: \(summary)", category: .auth)
            }
        }
    }
}
