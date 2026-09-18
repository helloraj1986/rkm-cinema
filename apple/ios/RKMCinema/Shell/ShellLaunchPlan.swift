import Foundation

/// The **cold-launch ladder**: what the shell does about a navigation that FAILED.
///
/// `docs/adr/ADR-0012-cold-launch-offline-shell.md`. The ask behind it is *"does it work with the Wi-Fi
/// off"*, and the answer used to be no — not because the device has nothing to show, but because the
/// app asked the network once, was refused, and went straight to *"Can't reach this server"*.
///
/// ⚠⚠ **THE DEVICE ALREADY HOLDS THE APP, and `nginx/default.conf` is what makes it storable.** A0 gave
/// the shell `Cache-Control: no-cache` on the document (revalidated, but STORED — it used to be
/// `no-store`, which forbids keeping it at all) and `immutable` for a year on Vite's content-hashed
/// `/assets/*`. So a cold launch with no network is not a missing-cache problem; it is a
/// never-asked-the-cache problem. This ladder is the asking.
///
/// Three steps, and the order is the decision (plan §1 option (a) — the live app is asked FIRST, the
/// cached copy is the fallback, never the default):
///
/// | Step | What it loads | Why |
/// |---|---|---|
/// | `fresh` | the live URL, `.useProtocolCachePolicy` | Every launch starts here. A working network must always win, which is what stops the app "sticking" to a cached copy. |
/// | `cached` | the same URL, `.returnCacheDataElseLoad` | The network just refused at `fresh`. This policy answers from the device's own copy and only touches the network if there is none — so an offline launch paints the app instead of an error. |
/// | `unreachable` | nothing | Both attempts failed. This is the SCREEN (`UnreachableServerView`), with its always-reachable way out — not an attempt. |
///
/// ⚠ **Why not the plan's `WKURLSchemeHandler` + a `ShellCache/` directory (§2, phases A and B)?** Because
/// that would be a SECOND cache of bytes the WebView already caches, with its own sync, its own eviction
/// and its own staleness rules — and E1 already measured custom schemes OUT for this app's media
/// (`mediaError=code=4` with the bytes served). The HTTP cache needs no sync step at all: `immutable`
/// hashed assets plus a revalidating document IS sync-on-load. ADR-0012 D3.
///
/// ⚠ **Pure Foundation, no WebKit, no `URLRequest`** — deliberately, and it is the same discipline as
/// `OfflinePlan.swift`/`OfflineServerCore`: the decisions live here, where `check-offline-core.py` RUNS
/// them with `swiftc` on Linux, and the WebKit half merely carries one of them out. `URLRequest.CachePolicy`
/// is spelled as a property of the step and mapped at the single call site in `WebShellModel`.
enum ShellBootStep: String, Equatable, CaseIterable {

    /// The first attempt of every launch: the live app, revalidated.
    case fresh
    /// The second, and only if `fresh` failed for a transport reason: the copy this device holds.
    case cached
    /// Both failed. The screen that says so — and nothing else.
    case unreachable

    /// ⚠ **The spelling IS the interface.** It goes into the log line, and the debug overlay reads the
    /// log, so it is what he photographs on the iPad during the Mac round. Pinned by a check that fails
    /// if any of the three is renamed (same rule as `Verification.sizeAndETag`).
    var label: String { rawValue }

    /// ⚠⚠ **`cacheFirst` FOR THE `cached` STEP ONLY, and this is the rule that keeps a stale shell from
    /// outliving a deploy.** `.returnCacheDataElseLoad` SKIPS revalidation, so using it at `fresh` would
    /// serve yesterday's `index.html` — which names yesterday's hashed bundle, and `/assets/` answers
    /// `=404` for a bundle the new deploy no longer ships (measured: a missing bundle must fail loudly
    /// rather than return the SPA and be reported as a syntax error). The cached step is only ever
    /// reached when the server has already refused to answer, so there is nothing fresher to prefer.
    var asksCacheFirst: Bool { self == .cached }

    /// ⚠ Whether this step is an ATTEMPT at all. `unreachable` is a screen, and a step that both means
    /// "give up" and could be loaded would be a step that reloads the attempt that just failed.
    var loads: Bool { self != .unreachable }
}

/// The one failure fact this ladder needs, reduced from an `NSError`.
///
/// ⚠ Two cases, not a code list: everything the ladder decides turns on *"is this worth the cached
/// attempt?"*, and the honest division is "WebKit cancelled it for its own benign reason" versus
/// "nothing answered".
enum ShellBootFailure: Equatable {

    /// `WebKitErrorDomain` 102 (frame load interrupted by policy change) or `NSURLErrorCancelled`.
    /// ⚠ WebKit cancels navigations for all sorts of benign reasons, and the rule about them is
    /// **they must not spend the one cached attempt.**
    case benignCancellation

    /// DNS, refused connection, no network, TLS — the `NSError` domain/code/description, which is the
    /// diagnosis (`-1003` cannot find host, `-1004` cannot connect, `-1009` offline, `-1202` TLS).
    case transport(String)

    /// The sentence to log. ⚠ Carries no credential-shaped word — `LogRedactor`'s sweep rewrites those
    /// inside ANY message (`LOGGING.md` §9).
    var detail: String {
        switch self {
        case .benignCancellation: return "cancelled by WebKit (benign)"
        case .transport(let detail): return detail
        }
    }
}

/// The ladder itself: three steps, advanced by failures, and reset by every `load()`.
///
/// ⚠ It is a value type with one `mutating` method rather than a stateless function because the step IS
/// state — and the state that matters is *"have we already spent the cached attempt?"*. Keeping it in the
/// model that owns the web view, and resetting it in `load()`, is what makes "the live app is always
/// asked first" true on every launch rather than only on a cold install.
struct ShellLaunchLadder {

    private(set) var step: ShellBootStep = .fresh

    /// ⚠ Called by `load()`, which is the ONE entry point for a launch and for a reload. A ladder that
    /// persisted across launches would make a cached boot sticky — the plan's own falsification test
    /// ("restore the network and confirm it goes back to loading live") is this line.
    mutating func reset() {
        step = .fresh
    }

    /// Advance on a failure and answer which step is next.
    ///
    /// ⚠ The result is what the caller LOADS (`cached`) or SHOWS (`unreachable`) — and `.fresh` is
    /// deliberately unreachable as a return value: a failure can never send the shell back to the
    /// attempt that just failed, which is the shape a reload loop would take.
    @discardableResult
    mutating func next(after failure: ShellBootFailure) -> ShellBootStep {
        if case .benignCancellation = failure {
            // ⚠ Changes NOTHING, on purpose: a benign cancellation is not evidence about the network,
            // and treating it as a failure would burn the cached attempt on a load WebKit never made.
            return step
        }
        switch step {
        case .fresh: step = .cached
        case .cached: step = .unreachable
        case .unreachable: break   // terminal, and idempotent: no loop, and no second screen.
        }
        return step
    }
}
