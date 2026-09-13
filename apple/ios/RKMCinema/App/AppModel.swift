import Foundation
import SwiftUI
import RKMServerKit

/// Everything the app needs to say about a server it could not reach.
struct UnreachableInfo: Equatable {
    let address: ServerAddress
    /// An `NSError` domain/code plus its description — the thing that turns "it doesn't work"
    /// into a diagnosis (`LOGGING.md` §3).
    let detail: String
}

/// Which screen the app is on, and the one decision behind it.
///
/// ⚠ No `@MainActor` on purpose. WebKit's delegate callbacks, `URLSession`'s async results and
/// SwiftUI's own actions all arrive on the main thread, and marking these types isolated would
/// force `@preconcurrency` conformances whose exact syntax depends on the Swift language mode
/// his Xcode picks — which is a build failure I cannot reproduce here. The main-thread
/// discipline is real; it just isn't worth a compiler-version dependency.
final class AppModel: ObservableObject {

    enum Phase: Equatable {
        /// Screen #0: no usable address.
        case setup
        /// The address is known and stored; the web shell is showing it.
        case shell
    }

    @Published private(set) var phase: Phase = .setup
    @Published private(set) var shell: WebShellModel?
    @Published private(set) var storedValueWasInvalid = false
    @Published private(set) var setupError: String?
    @Published private(set) var isConnecting = false
    @Published private(set) var websiteDataSummary: String?
    @Published var typedAddress: String = ""
    @Published var unreachable: UnreachableInfo?
    @Published var hudVisible: Bool = false

    let store: ServerStore

    init(store: ServerStore = ServerStore()) {
        self.store = store
        hudVisible = UserDefaults.standard.bool(forKey: AppLog.hudDefaultsKey)
        restoreFromStore()
    }

    // MARK: - Launch and routing

    private func restoreFromStore() {
        storedValueWasInvalid = store.hasInvalidStoredValue

        guard let address = store.address else {
            if storedValueWasInvalid {
                // Show him what was stored — it is usually a typo he can fix in place, and a
                // silent re-ask is the thing that looks like a bug.
                typedAddress = store.rawValue ?? ""
                setupError = "The saved address could not be read, so it has been ignored. Check it and connect again."
            }
            return
        }
        enterShell(with: address)
    }

    private func enterShell(with address: ServerAddress) {
        let model = WebShellModel(address: address)
        // The web view cannot show anything by itself; this is how a dead server becomes the
        // recoverable state instead of a white screen (plan §3.2).
        model.onUnreachable = { [weak self] info in
            guard let self else { return }
            self.unreachable = info
        }
        shell = model
        typedAddress = address.displayString
        unreachable = nil
        phase = .shell
    }

    // MARK: - Screen #0

    /// Parses, then **proves reachability before committing** — so a typo is answered on the
    /// spot rather than by a blank web view.
    func connect() async {
        setupError = nil
        let identifier = CorrelationID.next()

        let address: ServerAddress
        do {
            address = try ServerAddress(rawValue: typedAddress)
        } catch let error as ServerAddressError {
            setupError = error.errorDescription
            RKMLog.error("address rejected: \(error.errorDescription ?? "")", category: .app, correlation: identifier)
            return
        } catch {
            setupError = "That address could not be read."
            return
        }

        let origin = address.hadExplicitScheme ? "scheme typed" : "scheme assumed by the app"
        let port = address.port.map { ", port \($0)" } ?? ""
        RKMLog.info("connecting to \(address.displayString) (\(origin)\(port))", category: .app, correlation: identifier)

        isConnecting = true
        defer { isConnecting = false }

        let outcome = await ServerProbe.check(address, correlation: identifier)
        guard outcome.reachable else {
            unreachable = UnreachableInfo(address: address, detail: outcome.detail)
            return
        }

        store.save(address)
        storedValueWasInvalid = false
        enterShell(with: address)
    }

    /// Live feedback for the field: the normalised address, or **why** it was refused.
    var typedAddressResult: Result<ServerAddress, ServerAddressError>? {
        let trimmed = typedAddress.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        do {
            return .success(try ServerAddress(rawValue: trimmed))
        } catch let error as ServerAddressError {
            return .failure(error)
        } catch {
            return .failure(.empty)
        }
    }

    // MARK: - Recovery

    func retry() async {
        guard let info = unreachable else { return }
        let identifier = CorrelationID.next()
        unreachable = nil
        isConnecting = true
        defer { isConnecting = false }

        let outcome = await ServerProbe.check(info.address, correlation: identifier)
        if outcome.reachable {
            store.save(info.address)
            enterShell(with: info.address)
        } else {
            unreachable = UnreachableInfo(address: info.address, detail: outcome.detail)
        }
    }

    /// ⚠ Always reachable, from the unreachable screen and from the debug overlay. A stale or
    /// typo'd address must never leave the app with no way out short of reinstalling
    /// (`apple/ios/README.md`).
    func changeServer() {
        unreachable = nil
        shell = nil
        phase = .setup
        setupError = nil
        RKMLog.info("changing server — back to the setup screen", category: .app)
    }

    func clearWebsiteData() {
        WebsiteData.clear { [weak self] summary in
            guard let self else { return }
            self.websiteDataSummary = summary
            RKMLog.info("website data: \(summary)", category: .app)
        }
    }

    /// Forget the stored address and open on screen #0 next time. The "start over" that does not
    /// need a reinstall.
    func forgetSavedAddress() {
        RKMLog.info("forgetting the saved address", category: .app)
        store.clear()
        storedValueWasInvalid = false
        typedAddress = ""
        changeServer()
    }

    // MARK: - Debug overlay

    func toggleHUD() {
        setHUD(!hudVisible)
    }

    func setHUD(_ visible: Bool) {
        hudVisible = visible
        UserDefaults.standard.set(visible, forKey: AppLog.hudDefaultsKey)
        RKMLog.info("debug overlay \(visible ? "on" : "off")", category: .app)
    }
}
