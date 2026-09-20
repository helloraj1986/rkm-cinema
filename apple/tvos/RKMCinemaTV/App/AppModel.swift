import Foundation
// ⚠ `ObservableObject` and `@Published` are **Combine**, not SwiftUI. SwiftUI no longer re-exports
// Combine (iOS 26 SDK), and the failure reads as "type 'AppModel' does not conform to protocol
// 'ObservableObject'" plus a wall of "missing import of defining module 'Combine'". Learned on the iOS
// target's first real build; the same import is required here.
import Combine
import RKMServerKit

/// Everything the app needs to say about a server it could not reach.
struct UnreachableInfo: Equatable {
    let address: ServerAddress
    /// An `NSError` domain/code plus its description — the thing that turns "it doesn't work" into a
    /// diagnosis (`apple/LOGGING.md` §3).
    let detail: String
}

/// Which screen the app is on, and the one decision behind it.
///
/// ⚠ **`connecting` is a screen, not a state to hide.** On iOS the shell had a WebView to show a
/// spinner over; here the launch sequence is a native request, and a TV that shows nothing for two
/// seconds reads as a broken app in a way a phone does not. So the address and a spinner are on screen,
/// with `Change server` reachable — never a dead end.
///
/// ⚠ No `@MainActor` on purpose, matching the iOS model: `URLSession`'s async results and SwiftUI's own
/// actions arrive on the main thread, and marking these types isolated would force `@preconcurrency`
/// conformances whose syntax depends on the language mode his Xcode picks — a build failure that cannot
/// be reproduced here. The main-thread discipline is real; the compiler dependency is not worth it.
final class AppModel: ObservableObject {

    enum Phase: Equatable {
        /// Screen #0 — no usable address yet. The field opens PRE-FILLED (`ServerDefaults.address`).
        case setup
        /// A stored (or just-proven) address is being checked. One request decides what comes next.
        case connecting
        /// Screen #1 — the server is up; nobody is signed in (`401` from `/api/auth/me`).
        case signIn
        /// Screen #2 — signed in, no profile chosen yet.
        case profiles
        /// Screen #3 — Home: the Continue Watching / Recently Played rails. (Named `library` since Phase A,
        /// when it was a placeholder; it IS the Home screen now.)
        case library
        /// Screen #4 — Browse: the library list, then one folder's poster wall.
        ///
        /// ⚠ **A `TabView` is the idiomatic tvOS chrome for two side-by-side content screens, and it was
        /// considered and NOT taken here.** It would restructure the root view that Phase A's round verified
        /// (each screen owns one way forward and one way out), for a navigation change no round has tested.
        /// So Browse is a peer screen reached by a button, and the tab-bar question belongs with Phase D's
        /// polish once both screens exist on hardware.
        case browse
        /// Screen #5 — Item detail, read-only (Phase B4). Reached from Home or Browse, and it knows which
        /// one it came from so `Back` returns there.
        ///
        /// ⚠ It carried no Play control until Phase C, deliberately: a Play button the api could not serve
        /// would be a promise the app cannot keep (`docs/ARCHITECTURE.md` §11: never OFFER what the server
        /// will refuse). **C3 makes the verb honest**, so `Play` / `Resume S1E4` — whose WORD was always a
        /// rule (`DetailSnapshot.primaryVerb`) — is now a control, and it lands in the same phase as the
        /// screen it opens.
        case detail
        /// Screen #6 — the player (Phase C). Reached from the detail screen, and it is where playback
        /// actually happens: `AVPlayer`, the resume position, and the progress reports that put this film
        /// back into the web app's Continue Watching.
        ///
        /// ⚠ **It is a PHASE and not a `fullScreenCover`**, for the reason every other screen here is one:
        /// the app's own rule is that each screen owns one way forward and one way out, and an overlay that
        /// hides the profile-scoped stores behind it would make "who is watching" ambiguous at exactly the
        /// moment the app is writing that person's progress.
        case player
    }

    @Published private(set) var phase: Phase = .setup
    @Published private(set) var session: SessionStore?

    /// ⚠ **The Home, owned here rather than by the view.** A profile switch changes whose library the
    /// server will answer from, so the store has to be REBUILT (not merely reloaded) whenever the app
    /// enters `.library` — a recycled store would keep rendering the previous profile's rows, which is the
    /// one mistake this app's whole identity model exists to prevent. A view-owned store could not be
    /// replaced on that transition.
    @Published private(set) var home: HomeStore?

    /// ⚠ **Browse's store, built and dropped with the Home's, for the same reason** — it reads the same
    /// profile-scoped library, so a profile switch has to rebuild it or the next viewer browses the last
    /// one's libraries.
    @Published private(set) var browse: BrowseStore?

    /// ⚠ **The detail store is ONE ITEM's, built when it is opened and dropped when it is left** —
    /// `DetailStore`'s header explains why it is not reused across items. It is also dropped on every entry
    /// to `.library` and on sign-out / `changeServer`, because it read the previous profile's library.
    @Published private(set) var detail: DetailStore?

    /// ⚠ **The player's store, built ONE FILM at a time** and dropped when the film is left — same reason
    /// `detail` is (`PlaybackStore`'s header: it holds one item's playback-info, its positions and its
    /// pending writes). It is dropped on every entry to `.library` and on sign-out / `changeServer`, because
    /// its whole life is scoped to the profile that was watching.
    @Published private(set) var playback: PlaybackStore?

    /// Where `Back` on the detail screen returns to. ⚠ Recorded rather than assumed: the screen is reachable
    /// from two places, and "back" that always goes to Home would lose a viewer three folders deep in
    /// Browse. It is a `Phase`, so it cannot drift out of sync with an enum case being added.
    private var detailReturnPhase: Phase = .browse

    /// What `Back` says — naming the screen is the difference between a viewer pressing it and a viewer
    /// wondering where it goes.
    var detailReturnLabel: String {
        detailReturnPhase == .library ? "Back to Home" : "Back to Browse"
    }
    @Published private(set) var storedValueWasInvalid = false
    @Published private(set) var setupError: String?
    @Published private(set) var isConnecting = false
    @Published var typedAddress: String = ""
    @Published var unreachable: UnreachableInfo?
    @Published var hudVisible: Bool = false

    let store: ServerStore

    init(store: ServerStore = ServerStore()) {
        self.store = store
        // ⚠ `AppLog.hudStartsVisible`, not the stored value directly: a Debug build starts hidden and
        // ignores what was stored, so a stale `true` from an earlier session cannot make the overlay
        // effectively permanent. See `AppLog` for why that rule exists.
        self.hudVisible = AppLog.hudStartsVisible

        if store.hasInvalidStoredValue {
            storedValueWasInvalid = true
            // Show him what was stored — it is usually a typo he can fix in place, and a silent re-ask is
            // the thing that looks like a bug.
            typedAddress = store.rawValue ?? ServerDefaults.address
            setupError = "The saved address could not be read, so it has been ignored. Check it and connect again."
        } else if let address = store.address {
            typedAddress = address.displayString
            phase = .connecting
        } else {
            // ⚠ PRE-FILLED. A Siri Remote is a poor text input, so the common case must be one button
            // press — and the address is still fully editable. Nothing is auto-connected: a first launch
            // should not decide for him which server to talk to.
            typedAddress = ServerDefaults.address
        }
    }

    /// Called once from the app's `body` so the launch check runs after the first frame — a stored
    /// address is checked (and, if it works, the session read) without the UI waiting on the initialiser.
    func startFromStoredAddress() async {
        guard phase == .connecting, let address = store.address else { return }
        let identifier = CorrelationID.next()
        RKMLog.info("launch: checking the stored address \(address.displayString)", category: .app,
                    correlation: identifier)
        let outcome = await ServerProbe.check(address, correlation: identifier)
        guard outcome.reachable else {
            RKMLog.error("launch: the stored address did not answer — \(outcome.detail)", category: .app,
                         correlation: identifier)
            unreachable = UnreachableInfo(address: address, detail: outcome.detail)
            // ⚠ NOT back to `.setup`: the address is still what he typed, and `UnreachableServerView`
            // offers `Try again` / `Change server` over the top of whatever is behind it. Dropping to
            // setup would lose the address he is trying to fix.
            phase = .connecting
            return
        }
        await enterSession(with: address, correlation: identifier)
    }

    // MARK: - Screen #0

    /// Parses, then **proves reachability before committing** — so a typo is answered on the spot rather
    /// than by an empty screen he cannot read from the couch.
    func connect() async {
        setupError = nil
        unreachable = nil
        let identifier = CorrelationID.next()

        let address: ServerAddress
        do {
            address = try ServerAddress(rawValue: typedAddress)
        } catch let error as ServerAddressError {
            setupError = error.errorDescription
            RKMLog.error("address rejected: \(error.errorDescription ?? "")", category: .app,
                         correlation: identifier)
            return
        } catch {
            setupError = "That address could not be read."
            return
        }

        let origin = address.hadExplicitScheme ? "scheme typed" : "scheme assumed by the app"
        let port = address.port.map { ", port \($0)" } ?? ""
        RKMLog.info("connecting to \(address.displayString) (\(origin)\(port))", category: .app,
                    correlation: identifier)

        isConnecting = true
        phase = .connecting
        defer { isConnecting = false }

        let outcome = await ServerProbe.check(address, correlation: identifier)
        guard outcome.reachable else {
            unreachable = UnreachableInfo(address: address, detail: outcome.detail)
            phase = .setup
            return
        }

        store.save(address)
        storedValueWasInvalid = false
        await enterSession(with: address, correlation: identifier)
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

    // MARK: - The session

    /// ⚠ **One request decides the first screen.** `GET /api/auth/me` separates the three states that
    /// look identical from the outside — 401 = sign in, 200 with `profile_selected` false = pick a
    /// profile, 200 with it true = carry on — and a transport failure is the only thing that means
    /// "can't reach this server".
    private func enterSession(with address: ServerAddress, correlation: CorrelationID) async {
        let session = SessionStore(address: address)
        self.session = session
        phase = .connecting
        isConnecting = true
        let outcome = await session.start(correlation: correlation)
        isConnecting = false

        switch outcome {
        case .signedIn:
            if session.profileSelected {
                enterLibrary()
            } else {
                phase = .profiles
                _ = await session.loadProfiles(correlation: correlation)
            }
        case .signedOut:
            phase = .signIn
        case .unreachable(let detail):
            unreachable = UnreachableInfo(address: address, detail: detail)
            phase = .signIn
        }
    }

    /// After a successful sign-in: the profile picker, or straight to the library if a profile is already
    /// in effect on this session.
    func didSignIn() async {
        guard let session else { return }
        if session.profileSelected {
            enterLibrary()
        } else {
            phase = .profiles
            _ = await session.loadProfiles()
        }
    }

    /// After a successful profile switch.
    func didSelectProfile() {
        enterLibrary()
    }

    /// ⚠ **Every path into `.library` goes through here, and there are three of them** (a launch that
    /// already has a profile, a sign-in, and a profile switch). The store is REBUILT rather than reloaded
    /// because the session's identity has changed and the rows belong to whoever is watching now — three
    /// call sites setting `phase = .library` directly is how one of them eventually forgets.
    private func enterLibrary() {
        home = session.map { HomeStore(client: $0.api) }
        browse = session.map { BrowseStore(client: $0.api) }
        // ⚠ Dropped with the other two: a detail screen holds one title's synopsis, cast and episode list,
        // read from the profile that was watching a moment ago.
        detail = nil
        playback = nil
        phase = .library
    }

    /// Home → Browse. ⚠ A no-op when the stores are missing rather than a phase with nothing behind it: an
    /// empty Browse screen and a Browse that could not be built must not look the same.
    func showBrowse() {
        guard browse != nil else { return }
        phase = .browse
    }

    /// Home → Browse, already open on one library. ⚠ **Phase U3's top bar is the second caller**: a tab is a
    /// library, so it must arrive at BUILDING, not at Browse's own library list.
    ///
    /// ⚠ One guard, the same as `showBrowse`'s: a no-op when there is no store, rather than a phase with
    /// nothing behind it. ⚠ And a tab with no folder (an unresolved library) is refused here as well as in the
    /// bar — the seam that matters is the one the SERVER would refuse.
    func openLibrary(folderID: String?) {
        guard let browse, let folderID, !folderID.isEmpty else { return }
        phase = .browse
        Task { await browse.openFolder(folderID) }
    }

    /// Browse → Home. The same guard, the same reason.
    func showHome() {
        guard home != nil else { return }
        phase = .library
    }

    /// Home **or** Browse → Item detail. ⚠ **ONE entry point for both screens**, so the two cannot come to
    /// differ about which store is built, which phase is entered, or where `Back` goes.
    ///
    /// ⚠ The return phase is recorded only when this is a FRESH open: re-entering detail from detail (a
    /// later phase's "more like this") must not overwrite where the viewer originally came from.
    func openDetail(itemID: String) {
        guard let session, !itemID.isEmpty else { return }
        if phase != .detail {
            detailReturnPhase = (phase == .library) ? .library : .browse
        }
        detail = DetailStore(client: session.api, itemID: itemID)
        phase = .detail
        RKMLog.info("detail: opened \(itemID.prefix(8)) — Back returns to \(detailReturnLabel)",
                    category: .app)
    }

    /// Detail → wherever it was opened from. ⚠ The store is DROPPED rather than kept: on a TV one item's
    /// synopsis, cast and episode list are worth more as memory for the next screen's posters.
    func closeDetail() {
        detail = nil
        phase = detailReturnPhase == .detail ? .browse : detailReturnPhase
    }

    // MARK: - Screen #6: the player

    /// Detail → the player. ⚠ **The `ItemDetail` is PASSED IN rather than re-fetched**: the screen behind it
    /// already has the title, the run time, the synopsis and the resume ticks, and a second read of the same
    /// item would be one more request whose only purpose is to risk disagreeing with the first.
    ///
    /// ⚠ The store is built HERE and not in the view, so a profile switch, a sign-out or a `changeServer`
    /// cannot leave a player alive that holds the previous viewer's position (see `enterLibrary`).
    func openPlayer(itemID: String, detail: ItemDetail?,
                    facts: PlaybackStore.PlaybackFacts = .unknown) {
        guard let session, !itemID.isEmpty else { return }
        playback = PlaybackStore(client: session.api, itemID: itemID, detail: detail, facts: facts)
        phase = .player
        RKMLog.info("player: opened \(itemID.prefix(8))", category: .app)
    }

    /// Player → the detail screen it came from. ⚠ **The position write is NOT done here** — `PlayerView`
    /// fires it (and awaits the server's own answer) before this runs, because a store that has been dropped
    /// cannot report anything, and the write is the whole point of the phase.
    func closePlayer() {
        playback = nil
        phase = .detail
    }

    func changeProfile() async {
        guard let session else { return }
        phase = .profiles
        _ = await session.loadProfiles()
    }

    func signOut() async {
        await session?.signOut()
        // ⚠ Dropped, not kept: the rows in it belong to the session that just ended, and a store that
        // survived a sign-out is one relaunch away from rendering the last viewer's Continue Watching.
        home = nil
        browse = nil
        detail = nil
        playback = nil
        phase = .signIn
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
            await enterSession(with: info.address, correlation: identifier)
        } else {
            unreachable = UnreachableInfo(address: info.address, detail: outcome.detail)
        }
    }

    /// ⚠ Always reachable — from the unreachable screen, from the session screens, and from the debug
    /// overlay. A stale or typo'd address must never leave the app with no way out short of reinstalling.
    func changeServer() {
        unreachable = nil
        session = nil
        // Same reason as sign-out: a different server is a different library, and the old rows must not
        // survive the switch.
        home = nil
        browse = nil
        detail = nil
        playback = nil
        phase = .setup
        setupError = nil
        typedAddress = store.address?.displayString ?? typedAddress
        RKMLog.info("changing server — back to screen #0", category: .app)
    }

    /// Forget the stored address and open on screen #0 next time. The "start over" that does not need a
    /// reinstall.
    func forgetSavedAddress() {
        RKMLog.info("forgetting the saved address", category: .app)
        store.clear()
        storedValueWasInvalid = false
        typedAddress = ServerDefaults.address
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
