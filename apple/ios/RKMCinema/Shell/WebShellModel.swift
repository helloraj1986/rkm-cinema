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
///
/// ⚠⚠ AND SINCE ADR-0012 THE FAILURE PATH IS A LADDER, NOT A VERDICT: a failed load no longer means
/// "unreachable" straight away. The live app is asked first, the device's own cached copy of it is asked
/// second, and only then is the server declared unreachable. That ordering is `ShellLaunchLadder`
/// (pure, executed on Linux), and this type is the WebKit half that carries it out.
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

    /// ⚠ ADR-0012 — WHICH attempt is serving the page: the live app, or the copy this device holds.
    /// Published and logged, because the debug overlay reads the log and `LOGGING.md` §4 makes the
    /// overlay the surface a screenshot and the file log are joined on.
    @Published private(set) var bootStep: ShellBootStep = .fresh

    let address: ServerAddress

    /// Called on a **main-frame** navigation failure. `AppModel` turns this into the unreachable
    /// state; the shell never decides for itself to give up on a subresource.
    var onUnreachable: ((UnreachableInfo) -> Void)?

    private(set) weak var webView: WKWebView?

    /// ⚠ ADR-0012: the ladder the loads advance — live app → the device's own copy → the error screen.
    /// ⚠ It is a STORED property, not a local, because "have we already spent the cached attempt?" is
    /// state that has to survive between two `didFail` callbacks. Reset by every `load()`.
    private var ladder = ShellLaunchLadder()

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

    /// ⚠ THE ONE ENTRY POINT for a launch and for a reload, and it always begins at the FRESH step —
    /// which is the whole "no permanent stickiness to the cached copy" rule (ADR-0012 D4).
    func load() {
        ladder.reset()
        RKMLog.info("shell boot: step \(ladder.step.label) — the live app is asked first", category: .nav)
        performLoad()
    }

    /// ⚠ NOT `webView.reload()` any more, and the difference is load-bearing: `reload()` re-sends the
    /// LAST request, so reloading a page that was booted from the device's own copy would re-read that
    /// copy even with the network back up. This goes through `load()`, so a reload is a fresh climb of
    /// the ladder and the live app wins again.
    func reload() {
        RKMLog.info("reload requested — back to the fresh attempt", category: .nav)
        load()
    }

    /// Carry out the step the ladder is on.
    ///
    /// ⚠ The ONLY place a shell `URLRequest` is built, so the step → cache-policy mapping exists once
    /// (ADR-0012 D2) and the ladder stays pure enough to run on Linux.
    private func performLoad() {
        guard let webView else { return }
        loadAttempts += 1
        let identifier = CorrelationID.next()
        state = .loading
        bootStep = ladder.step

        var request = URLRequest(url: address.url)
        // ⚠ `returnCacheDataElseLoad` ONLY at the cached step, because it SKIPS revalidation: at `fresh`
        // it would serve a superseded document whose hashed bundle the last deploy deleted, and
        // `/assets/` answers `=404` for exactly that (by design — see `nginx/default.conf`).
        request.cachePolicy = ladder.step.asksCacheFirst ? .returnCacheDataElseLoad : .useProtocolCachePolicy

        RKMLog.info("load #\(loadAttempts) → \(address.displayString) · step \(ladder.step.label)"
                    + (ladder.step.asksCacheFirst ? " · cache-first (the device's own copy)" : " · revalidating"),
                    category: .nav, correlation: identifier)
        webView.load(request)
    }

    // MARK: - Navigation delegate callbacks

    func didStartProvisionalNavigation(url: URL?) {
        state = .loading
        RKMLog.verbose("didStartProvisionalNavigation \(describe(url))", category: .nav)
        // ⚠ Phase B3: the document that is on screen is being replaced, so the bridge must stop emitting into
        // it (an emit against a torn-down document is a JavaScript exception). `didFinish` re-opens it.
        OfflineBridge.shared.pageWillNavigate()
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
        let failure: ShellBootFailure = isBenignCancellation(nsError) ? .benignCancellation : .transport(detail)

        // ⚠ The LADDER decides, rather than this function — including the rule that a benign cancellation
        // does not move it (ADR-0012 D5). Asking it here is what keeps that rule in one place.
        //
        // ⚠ And there is no dedupe by "which load was this?" because there is nothing to dedupe: WebKit
        // reports either `didFailProvisionalNavigation` (before the response) or `didFail` (after it) for a
        // given navigation, never both. The case that WOULD matter — a navigation cancelled for WebKit's own
        // reasons advancing the ladder and spending the one cached attempt — is what D5 covers instead.
        let step = ladder.next(after: failure)

        if case .benignCancellation = failure {
            RKMLog.verbose("navigation cancelled (benign, ignored): \(detail) · step stays \(step.label)",
                           category: .nav)
            return
        }

        RKMLog.error("navigation failed: \(detail) (main frame: \(isMainFrame)) · step \(step.label)",
                     category: .nav)

        guard isMainFrame else { return }

        switch step {
        case .cached:
            // ⚠⚠ ADR-0012 — the whole point of the phase. The server did not answer, so ask the DEVICE.
            // A0 made the shell storable (`no-cache` on the document, `immutable` on the hashed bundles),
            // so this is what paints the app with the Wi-Fi off instead of "Can't reach this server".
            RKMLog.info("the server did not answer — trying the copy of the app this device holds",
                        category: .nav)
            performLoad()

        case .unreachable:
            state = .failed(detail)
            onUnreachable?(UnreachableInfo(address: address, detail: detail))

        case .fresh:
            // ⚠ Unreachable BY CONSTRUCTION: `next(after:)` never returns the step that just failed, so
            // this branch is a bug rather than a state — and reloading from here is precisely the loop
            // the ladder's shape exists to make impossible.
            RKMLog.error("the launch ladder returned the step that just failed — not reloading", category: .nav)
        }
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
