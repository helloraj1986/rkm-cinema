import Foundation
import WebKit
// ⚠ `ObservableObject`/`AnyCancellable` are Combine, and the relay below subscribes to the downloader's
// publisher. Needed explicitly on the iOS 26 SDK — see the note in `AppModel.swift`.
import Combine
import RKMServerKit

// Phase B3, the bridge: **the page ↔ native contract, both directions**.
//
// ⚠ The contract itself is not decided here. `OfflineBridgeContract.swift` (pure, Linux-executed) parses
// every command, refuses every unknown one by name, and decides what is worth telling the page and when.
// This file is the plumbing: a `WKScriptMessageHandlerWithReply`, an injected global, and the one
// subscription that turns the downloader's state into events.
//
// Three things about it are load-bearing:
//
//  1. **⚠ The global is defined, never assumed.** `window.__rkmOffline` exists only inside the iOS shell;
//     in a desktop browser it is simply absent, which is exactly how the page decides whether to draw an
//     offline affordance at all (`NATIVE_FEEL_AND_OFFLINE_PLAN.md` §4.5 — never render a control that
//     cannot work).
//  2. **⚠ A command that cannot be answered is answered anyway** — with a code and a sentence. A
//     `postMessage` a page can never settle is a button that does nothing and an error nowhere.
//  3. **⚠ The loopback URL goes to the page and nowhere else.** It is a capability for this process only
//     (the port changes every launch), so it is never written to the manifest, never returned by `list`
//     unless the server is actually listening, and never logged.

// MARK: - The injected global

enum OfflineBridgeScript {

    static let globalName = "__rkmOffline"

    static func userScript() -> WKUserScript {
        WKUserScript(source: source, injectionTime: .atDocumentStart, forMainFrameOnly: true)
    }

    /// ⚠ Wrapped in `try`/`catch` and never throwing: this must not be able to break the app it serves, the
    /// same rule `WebInstrumentation` follows.
    static let source: String = #"""
    (function () {
      // ⚠ Idempotent: a second injection (a reload, or a future second script) must not orphan the
      // listeners the page already registered.
      if (window.__rkmOffline) { return; }

      var handlerName = 'rkmOfflineCommand';
      var listeners = [];
      // ⚠ Events that arrive BEFORE the page registers a listener are queued, not dropped. The native side
      // announces every title on its own schedule, and the SPA's React tree mounts later — a dropped
      // `ready` event is a Download button that still says "Download" over a film that is already on disk.
      var queue = [];
      var MAX_QUEUE = 32;

      function handler() {
        try { return window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers[handlerName]; }
        catch (e) { return null; }
      }

      // ⚠ Reduced on purpose, and this is a privacy rule rather than tidiness: the event payload contains
      // the loopback URL, and the telemetry channel sends what the page RECEIVED straight into the log
      // file. A URL in a log is a capability in a log, so only the shape travels.
      function summary(event) {
        try {
          return {
            e: String((event && event.e) || '?'),
            itemId: (event && event.itemId) || null,
            state: (event && event.state) || null,
            percent: (event && typeof event.percent === 'number') ? event.percent : null,
            hasUrl: !!(event && event.url)
          };
        } catch (err) { return { e: 'unreadable' }; }
      }

      var api = {
        version: 1,
        available: true,

        on: function (listener) {
          if (typeof listener !== 'function') { return api; }
          listeners.push(listener);
          if (queue.length) {
            var pending = queue.slice();
            queue.length = 0;
            pending.forEach(function (event) { deliver(listener, event); });
          }
          return api;
        },

        off: function (listener) {
          listeners = listeners.filter(function (each) { return each !== listener; });
          return api;
        },

        emit: function (event) {
          if (!listeners.length) {
            queue.push(event);
            if (queue.length > MAX_QUEUE) { queue.shift(); }
            return;
          }
          listeners.slice().forEach(function (listener) { deliver(listener, event); });
        },

        // ⚠ Sends `{v, c, ...}` and returns a Promise. A command that is not answered is refused with a
        // reason: `postMessage` returns a Promise only when the native side registered a reply-capable
        // handler, and treating `undefined` as a reply would be a promise that never settles.
        request: function (command) {
          var bridge = handler();
          if (!bridge) {
            return Promise.reject(new Error('the offline bridge is not installed in this web view'));
          }
          var payload = {};
          for (var key in command) { if (Object.prototype.hasOwnProperty.call(command, key)) { payload[key] = command[key]; } }
          payload.v = 1;
          var answer;
          try {
            answer = bridge.postMessage(payload);
          } catch (err) {
            return Promise.reject(new Error('the offline bridge refused the message: ' + err));
          }
          if (!answer || typeof answer.then !== 'function') {
            return Promise.reject(new Error('this build cannot answer offline commands (no reply-capable handler)'));
          }
          return answer;
        },

        list:   function () { return api.request({ c: 'list' }); },
        ping:   function () { return api.request({ c: 'ping' }); },
        play:   function (itemId) { return api.request({ c: 'play', itemId: itemId }); },
        cancel: function (itemId) { return api.request({ c: 'cancel', itemId: itemId }); },
        remove: function (itemId) { return api.request({ c: 'delete', itemId: itemId }); },
        download: function (itemId, title, mode) {
          return api.request({ c: 'download', itemId: itemId, title: title, mode: mode || 'auto' });
        }
      };

      function deliver(listener, event) {
        try { listener(event); } catch (err) { /* a broken listener must not stop the others */ }
      }

      // The probe channel: reports what the page received, over the existing instrumentation handler (one
      // redaction call site — see `WebInstrumentation`). Only ever used by a DEBUG launch argument.
      window.__rkmOfflineReport = function (kind, detail) {
        try {
          var bridge = window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.rkm;
          if (!bridge) { return; }
          var payload = { t: 'offline', k: kind };
          for (var key in detail) { if (Object.prototype.hasOwnProperty.call(detail, key)) { payload[key] = detail[key]; } }
          bridge.postMessage(JSON.stringify(payload));
        } catch (err) { /* never break the page */ }
      };

      window.__rkmOfflineSummary = summary;
      window.__rkmOffline = api;
    })();
    """#
}

// MARK: - The bridge

final class OfflineBridge: NSObject, WKScriptMessageHandlerWithReply {

    /// ⚠ A shared instance for the same lifecycle reason `OfflineDownloads.shared` has one: the web view is
    /// rebuilt (a new server address gives `AppRootView` a different identity), and the token book and the
    /// listening socket must not be. A URL handed to the page has to stay valid while the page that holds it
    /// is on screen.
    static let shared = OfflineBridge()

    static let handlerName = "rkmOfflineCommand"

    private let tokens = OfflineTokenBook()
    private weak var downloads: OfflineDownloads?
    private weak var webView: WKWebView?

    private var server: OfflineServer?
    private var serverStartFailure: String?

    /// What the page has been told about each title. ⚠ Progress is not stored here; only what has been
    /// SENT, so the decisions in `OfflineEventPlanner` stay pure and repeatable.
    private var snapshots: [String: OfflineEventSnapshot] = [:]
    private var knownItemIds: [String] = []

    private var relay: AnyCancellable?
    private var publishScheduled = false
    private var currentAddress: String?

    private override init() {
        super.init()
    }

    // MARK: - Wiring

    /// Registered once per app run, by the web view. ⚠ `attach` is separate from `configure` because the
    /// bridge outlives both the web view and the model.
    func attach(webView: WKWebView) {
        self.webView = webView
        RKMLog.info("offline bridge attached to a web view (handler \(Self.handlerName))", category: .offline)
        // ⚠ NOT published here: a web view with no page loaded has no `window.__rkmOffline` to receive
        // anything. `pageDidLoad()` is the moment to talk.
    }

    /// ⚠ Called when a page has FINISHED loading, and it is the whole reason `snapshots` is cleared here.
    ///
    /// A navigation is a NEW page: a reload, a sign-in redirect, or a different address all throw away
    /// whatever the old page knew. `snapshots` records what we TOLD the page, so without this the events
    /// that fired while it was loading would be judged "already sent" and the page's offline UI would stay
    /// empty until something *changed* — which, for a download that finished a minute ago, is never.
    /// (This is the same rule the pure planner starts from: `previous == nil → a state event`. A new page is
    /// exactly `previous == nil`.)
    func pageDidLoad() {
        snapshots.removeAll()
        knownItemIds = []
        schedulePublish()
    }

    /// ⚠ Everything a token names belongs to ONE server. A new address (or a fresh sign-in against the same
    /// address) must not leave a URL from the previous one playable — that is a film from another library,
    /// served under this one's title.
    func configure(downloads: OfflineDownloads, address: ServerAddress) {
        self.downloads = downloads

        if currentAddress != address.displayString {
            let dropped = tokens.forgetAll()
            snapshots.removeAll()
            knownItemIds = []
            currentAddress = address.displayString
            if dropped > 0 || server != nil {
                // ⚠ `handle`, never the domain word: see the note in `OfflineServerCore.pathLabel`.
                RKMLog.info("offline bridge: the server address changed — dropped \(dropped) offline "
                            + "handle(s) and stopped the loopback server", category: .offline)
            }
            server?.stop()
            server = nil
        }

        guard relay == nil else { return }
        // ⚠ `objectWillChange` fires BEFORE the change lands, so the work is deferred to the next main-queue
        // turn — reading the rows synchronously here would publish the previous state, one event behind.
        // The flag coalesces a burst (progress ticks ~10 times a second) into one pass.
        relay = downloads.objectWillChange.sink { [weak self] in
            self?.schedulePublish()
        }
        schedulePublish()
    }

    private func schedulePublish() {
        guard !publishScheduled else { return }
        publishScheduled = true
        DispatchQueue.main.async { [weak self] in
            self?.publishScheduled = false
            self?.publish()
        }
    }

    // MARK: - Commands (page → native)

    func userContentController(_ userContentController: WKUserContentController,
                              didReceive message: WKScriptMessage,
                              replyHandler: @escaping (Any?, String?) -> Void) {
        guard message.name == Self.handlerName else {
            replyHandler(nil, "unexpected handler")
            return
        }

        switch OfflineBridgeRequest.parse(message.body) {
        case .failure(let error):
            // ⚠ Refused IN THE REPLY, not silently: this is the whole reason the reply-capable handler is
            // used. The page gets a code it can switch on and a sentence a human can act on.
            RKMLog.error("offline bridge · refused a message: \(error.code) — \(error.errorDescription ?? "")",
                         category: .offline)
            replyHandler(OfflineBridgeReply.failure(error).jsonObject, nil)
        case .success(let request):
            perform(request, replyHandler: replyHandler)
        }
    }

    private func perform(_ request: OfflineBridgeRequest,
                         replyHandler: @escaping (Any?, String?) -> Void) {
        guard let downloads else {
            replyHandler(OfflineBridgeReply.failure(.unavailable(
                reason: "The downloader is not ready yet — the app has not finished starting.")).jsonObject, nil)
            return
        }

        switch request.command {
        case .ping:
            replyHandler(OfflineBridgeReply.accepted(.ping).jsonObject, nil)

        case .list:
            replyHandler(OfflineBridgeReply.listed(items()).jsonObject, nil)

        case .play:
            guard let itemId = request.itemId else {
                replyHandler(OfflineBridgeReply.failure(.missingItemId(command: "play")).jsonObject, nil)
                return
            }
            play(itemId: itemId) { reply in
                replyHandler(reply.jsonObject, nil)
            }

        case .download:
            guard let itemId = request.itemId, let title = request.title else {
                replyHandler(OfflineBridgeReply.failure(.missingTitle).jsonObject, nil)
                return
            }
            downloads.start(itemId: itemId, title: title, mode: request.mode)
            RKMLog.info("offline bridge · download accepted · mode \(request.mode)", category: .offline)
            schedulePublish()
            replyHandler(OfflineBridgeReply.accepted(.download).jsonObject, nil)

        case .cancel:
            guard let itemId = request.itemId else {
                replyHandler(OfflineBridgeReply.failure(.missingItemId(command: "cancel")).jsonObject, nil)
                return
            }
            guard downloads.rows.contains(where: { $0.itemId == itemId }) else {
                replyHandler(OfflineBridgeReply.failure(.unknownItem(itemId: itemId)).jsonObject, nil)
                return
            }
            downloads.cancel(itemId: itemId)
            schedulePublish()
            replyHandler(OfflineBridgeReply.accepted(.cancel).jsonObject, nil)

        case .delete:
            guard let itemId = request.itemId else {
                replyHandler(OfflineBridgeReply.failure(.missingItemId(command: "delete")).jsonObject, nil)
                return
            }
            guard downloads.rows.contains(where: { $0.itemId == itemId }) else {
                replyHandler(OfflineBridgeReply.failure(.unknownItem(itemId: itemId)).jsonObject, nil)
                return
            }
            downloads.delete(itemId: itemId)
            // ⚠ The token dies with the file: an old URL that still resolves is a page that offers to play
            // something that is not there.
            tokens.forget(itemId: itemId)
            schedulePublish()
            replyHandler(OfflineBridgeReply.accepted(.delete).jsonObject, nil)
        }
    }

    /// Start the loopback server if it is not up, then hand back a URL for a title that is ready.
    func play(itemId: String, completion: @escaping (OfflineBridgeReply) -> Void) {
        guard let downloads else {
            completion(.failure(.unavailable(reason: "The downloader is not ready yet.")))
            return
        }
        guard let row = downloads.rows.first(where: { $0.itemId == itemId }) else {
            completion(.failure(.unknownItem(itemId: itemId)))
            return
        }
        guard row.state.isPlayable else {
            completion(.failure(.notReady(itemId: itemId, state: row.state.label)))
            return
        }
        guard let target = serveTarget(itemId: itemId) else {
            completion(.failure(.notReady(itemId: itemId, state: "not on this device")))
            return
        }

        ensureServer { [weak self] result in
            guard let self else { return }
            switch result {
            case .success(let port):
                let entry = OfflineTokenBook.Entry(itemId: itemId, container: target.container,
                                                   fileExtension: target.fileExtension)
                let token = self.tokens.token(for: entry)
                let url = "http://127.0.0.1:\(port)/offline/\(token).\(target.fileExtension)"
                RKMLog.info("offline bridge · play → a local URL was minted (port \(port))", category: .offline)
                // ⚠ Publishing now is what turns the URL's arrival into a `ready` event for the page, without
                // the page having to ask twice.
                self.schedulePublish()
                completion(.playable(OfflineBridgePlay(itemId: itemId, url: url,
                                                       contentType: target.resource.contentType,
                                                       size: target.resource.size)))
            case .failure(let error):
                let reason = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
                RKMLog.error("offline bridge · the loopback server would not start: \(reason)",
                             category: .offline)
                completion(.failure(.unavailable(reason: reason)))
            }
        }
    }

    /// ⚠ Idempotent, and the only place the server is started outside a probe.
    func ensureServer(completion: @escaping (Result<UInt16, Error>) -> Void) {
        if let server, let port = server.port {
            completion(.success(port))
            return
        }
        if let failure = serverStartFailure {
            completion(.failure(OfflineServerError.couldNotStart(reason: failure)))
            return
        }
        let server = self.server ?? OfflineServer(tokens: tokens) { [weak self] entry in
            self?.resource(for: entry)
        }
        self.server = server
        server.start { [weak self] result in
            DispatchQueue.main.async {
                if case .failure(let error) = result {
                    self?.serverStartFailure = (error as? LocalizedError)?.errorDescription
                        ?? error.localizedDescription
                }
                completion(result)
            }
        }
    }

    // MARK: - Reading the device's own state

    private func serveTarget(itemId: String)
        -> (resource: OfflineServeResource, container: String?, fileExtension: String)? {
        guard let store = downloads?.store,
              let record = store.record(itemId),
              record.state.isPlayable
        else { return nil }
        guard let url = try? store.layout.mediaURL(itemId, container: record.container),
              let size = store.diskState(itemId, container: record.container).finalBytes,
              size > 0
        else { return nil }
        let fileExtension = OfflineContainer.fileExtension(forServerContainer: record.container)
        let resource = OfflineServeResource(
            url: url,
            size: size,
            etag: record.etag,
            contentType: OfflineMediaType.contentType(forExtension: fileExtension)
        )
        return (resource, record.container, fileExtension)
    }

    /// ⚠ Called on the server's own queue. It reads the store (which serialises its own manifest writes),
    /// and it is the ONLY way a token becomes a file — the server never sees a path from the client.
    private func resource(for entry: OfflineTokenBook.Entry) -> OfflineServeResource? {
        guard let store = downloads?.store, let record = store.record(entry.itemId) else { return nil }
        guard let url = try? store.layout.mediaURL(entry.itemId, container: record.container),
              let size = store.diskState(entry.itemId, container: record.container).finalBytes
        else { return nil }
        return OfflineServeResource(
            url: url,
            size: size,
            etag: record.etag,
            contentType: OfflineMediaType.contentType(forExtension: entry.fileExtension)
        )
    }

    private func items() -> [OfflineBridgeItem] {
        guard let downloads else { return [] }
        let port = server?.port
        return downloads.rows.map { row in
            var url: String?
            var contentType: String?
            if row.state.isPlayable, let port, let target = serveTarget(itemId: row.itemId) {
                let entry = OfflineTokenBook.Entry(itemId: row.itemId, container: target.container,
                                                   fileExtension: target.fileExtension)
                let token = tokens.token(for: entry)
                url = "http://127.0.0.1:\(port)/offline/\(token).\(target.fileExtension)"
                contentType = target.resource.contentType
            }
            return OfflineBridgeItem(itemId: row.itemId, title: row.title, state: row.state.rawValue,
                                     bytes: row.bytes, totalBytes: row.totalBytes, mode: row.mode,
                                     error: row.lastError, url: url, contentType: contentType)
        }
    }

    /// The HUD's view of the bridge — one line, so a screenshot says whether the socket is up.
    var hudLines: [String] {
        var lines = ["bridge \(Self.handlerName) · handles \(tokens.count)"]
        if let port = server?.port {
            lines.append("loopback 127.0.0.1:\(port) (listening)")
        } else if let failure = serverStartFailure {
            lines.append("loopback FAILED — \(failure)")
        } else {
            lines.append("loopback not started (it starts when a title is ready or asked for)")
        }
        lines.append("page told about \(snapshots.count) title(s)")
        return lines
    }

    // MARK: - Events (native → page)

    /// Runs on the main thread. Reads the downloader, asks the PURE planner what is worth saying, and says it.
    func publish() {
        guard let downloads else { return }

        var served = server?.port

        // ⚠ A title that is ready but has no server yet means the `ready` event could not carry a URL. The
        // server is started here so the event that follows DOES carry one — this is the difference between
        // "downloaded" and "playable with the Wi-Fi off".
        if served == nil, serverStartFailure == nil,
           downloads.rows.contains(where: { $0.state.isPlayable && serveTarget(itemId: $0.itemId) != nil }) {
            ensureServer { [weak self] _ in
                self?.schedulePublish()
            }
            return
        }
        served = server?.port

        var current: [String] = []
        for row in downloads.rows {
            current.append(row.itemId)

            var url: String?
            if row.state.isPlayable, let port = served, let target = serveTarget(itemId: row.itemId) {
                let entry = OfflineTokenBook.Entry(itemId: row.itemId, container: target.container,
                                                   fileExtension: target.fileExtension)
                let token = tokens.token(for: entry)
                url = "http://127.0.0.1:\(port)/offline/\(token).\(target.fileExtension)"
            }

            let snapshot = OfflineEventSnapshot(
                itemId: row.itemId, title: row.title, state: row.state, bytes: row.bytes,
                totalBytes: row.totalBytes, mode: row.mode, url: url, error: row.lastError,
                emittedStep: snapshots[row.itemId]?.emittedStep ?? -1
            )

            switch OfflineEventPlanner.decide(previous: snapshots[row.itemId], current: snapshot) {
            case .nothing:
                break

            case .state:
                emit(.state(itemId: row.itemId, title: row.title, state: row.state.rawValue,
                            bytes: row.bytes, totalBytes: row.totalBytes, mode: row.mode,
                            error: row.lastError, url: url))
                // ⚠ The throttle is carried across a state change — and RESET by a rewind, so a restart does
                // not re-announce itself on every tick until it climbs back past the old percentage.
                var updated = snapshot
                updated.emittedStep = OfflineEventPlanner.stepAfterStateChange(previous: snapshots[row.itemId],
                                                                              current: snapshot)
                snapshots[row.itemId] = updated

            case .ready:
                if let url, let target = serveTarget(itemId: row.itemId) {
                    emit(.ready(itemId: row.itemId, url: url, contentType: target.resource.contentType,
                                bytes: row.bytes))
                }
                snapshots[row.itemId] = snapshot

            case .progress(let step):
                var updated = snapshot
                updated.emittedStep = step
                emit(.progress(itemId: row.itemId, bytes: row.bytes, totalBytes: row.totalBytes,
                               percent: step))
                snapshots[row.itemId] = updated
            }
        }

        // ⚠ A title the page still believes in but the downloader has forgotten (a delete) has to be said out
        // loud, or the page keeps a row that opens a film that is gone.
        for gone in OfflineEventPlanner.vanished(previous: knownItemIds, current: current) {
            tokens.forget(itemId: gone)
            snapshots.removeValue(forKey: gone)
            emit(.removed(itemId: gone))
        }
        knownItemIds = current

        #if DEBUG
        // ⚠ The launch-argument probe's second half needs a TITLE, so it cannot run at page load — a film a
        // launch argument started arrives minutes later. This is the hook that lets it fire the moment one
        // exists. No-op without the launch arguments.
        OfflineServerProbe.rowsDidChange()
        #endif
    }

    private func emit(_ payload: OfflineEventPayload) {
        guard let webView else { return }
        guard let data = try? JSONSerialization.data(withJSONObject: payload.jsonObject),
              let json = String(data: data, encoding: .utf8)
        else { return }

        // ⚠ The payload is JSON, and the only thing interpolated is that JSON — never a string we built by
        // hand, and never anything the page sent us.
        let script = "window.\(OfflineBridgeScript.globalName).emit(\(json));"
        DispatchQueue.main.async {
            webView.evaluateJavaScript(script) { _, error in
                if let error {
                    // ⚠ Loud on purpose: a page that never receives events looks exactly like a feature that
                    // was never built.
                    RKMLog.error("offline bridge · could not deliver an event to the page: "
                                 + "\(error.localizedDescription)", category: .offline)
                }
            }
        }
    }

    // ⚠ One `#if DEBUG` for this whole block, not two: a duplicated opening directive with a single `#endif`
    // is a file that does not compile AT ALL, and it is exactly what the Linux typecheck caught here.
    #if DEBUG
    /// ⚠ DEBUG only: hands the live web view to the launch-argument probe, which is the only thing that can
    /// ask the PAGE a question (the native→page direction has no other witness).
    var debugWebView: WKWebView? { webView }

    /// ⚠ DEBUG only, and used only by the launch-argument probe: it clears what the page has been told, so
    /// the next `publish()` re-announces every title through the REAL event path. Nothing is fabricated —
    /// the payloads are the ones production sends.
    func forcePublishAll() {
        snapshots.removeAll()
        knownItemIds = []
        publish()
    }
    #endif
}
