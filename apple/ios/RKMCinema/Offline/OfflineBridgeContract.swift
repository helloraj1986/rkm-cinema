import Foundation

// Phase B3's second pure half: the **page ↔ native contract**.
//
// `docs/NATIVE_FEEL_AND_OFFLINE_PLAN.md` §4.5 describes it in a dozen lines. This file is those dozen
// lines made checkable, because the two things that go wrong with a bridge are both silent:
//
//   * **a message the native side does not understand is dropped** — `postMessage` with no reply is a
//     promise that never settles, i.e. a button that does nothing and an error nowhere. Every unknown
//     command is REFUSED BY NAME here, never ignored;
//   * **the page gets an event and nobody notices the payload is wrong** — the event payloads carry the
//     numbers the UI draws, so their shape is pinned by checks rather than by hope.
//
// ⚠ Versioned and additive, the same discipline as the HTTP contract (ADR-0001): every message carries
// `v`, and a version this build does not speak is **refused with a sentence a human can act on** — the app
// being older than the page is a fact to report, not something to paper over by guessing at the shape.

// MARK: - Commands: page → native

enum OfflineBridgeCommand: String, Equatable, CaseIterable {
    /// Every downloaded title, and whether it is playable. ⚠ The page asks FIRST, so its buttons are right
    /// on every screen and after any relaunch — native is the only side that knows.
    case list
    case download
    case cancel
    case delete
    case play
    /// A liveness check with no side effects: does this build speak the bridge at all.
    case ping

    var needsItemId: Bool {
        switch self {
        case .list, .ping: return false
        case .download, .cancel, .delete, .play: return true
        }
    }
}

/// The modes the server's `prepare` accepts (`backend/api/routes/offline.py`, the `mode` query's own
/// description) — ⚠ spelled out rather than passed through, so a typo in the page is refused instead of
/// quietly becoming `auto` and downloading something other than what was asked for.
enum OfflineBridgeMode {
    static let allowed = ["auto", "direct", "remux", "transcode_audio", "transcode"]
    static let `default` = "auto"
}

struct OfflineBridgeRequest: Equatable {
    var version: Int
    var command: OfflineBridgeCommand
    var itemId: String?
    var title: String?
    var mode: String

    static let supportedVersion = 1

    /// Parse what `WKScriptMessage` handed over. ⚠ **Both shapes are accepted on purpose**: a JS
    /// `postMessage({...})` arrives as a dictionary, and `postMessage(JSON.stringify({...}))` arrives as a
    /// `String`. Supporting only one of them produces the worst kind of bug — a bridge that works in the
    /// probe and not in the app.
    static func parse(_ body: Any) -> Result<OfflineBridgeRequest, OfflineBridgeError> {
        let dictionary: [String: Any]
        if let text = body as? String {
            guard let data = text.data(using: .utf8),
                  let object = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
            else {
                return .failure(.notReadable(reason: "a String body was not a JSON object"))
            }
            dictionary = object
        } else if let object = body as? [String: Any] {
            dictionary = object
        } else {
            return .failure(.notReadable(reason: "the message is neither a dictionary nor a JSON string"))
        }

        // ⚠ The version is REQUIRED. A message that does not say which contract it speaks cannot be
        // answered correctly, and defaulting it would make every future shape change a coin flip.
        guard let version = dictionary["v"] as? Int else {
            return .failure(.unsupportedVersion(found: 0, supported: supportedVersion))
        }
        guard version == supportedVersion else {
            return .failure(.unsupportedVersion(found: version, supported: supportedVersion))
        }

        guard let rawCommand = dictionary["c"] as? String else {
            return .failure(.notReadable(reason: "the message has no `c` (command) field"))
        }
        guard let command = OfflineBridgeCommand(rawValue: rawCommand) else {
            return .failure(.unknownCommand(rawCommand))
        }

        var itemId: String?
        if let raw = dictionary["itemId"] as? String {
            // ⚠ Refused, never repaired — B2's ADR-0008 D6. A rewrite is an alias, and an alias is the one
            // thing that can put two different titles in one directory.
            switch OfflineIdentifier.validated(raw) {
            case .success(let clean): itemId = clean
            case .failure(let error): return .failure(.invalidItemId(itemId: raw, reason: error.reason))
            }
        }
        if command.needsItemId && itemId == nil {
            return .failure(.missingItemId(command: command.rawValue))
        }

        var title: String?
        if let raw = dictionary["title"] as? String {
            let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
            if !trimmed.isEmpty { title = trimmed }
        }
        if command == .download && title == nil {
            return .failure(.missingTitle)
        }

        var mode = OfflineBridgeMode.default
        if let raw = dictionary["mode"] as? String {
            let cleaned = raw.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            guard OfflineBridgeMode.allowed.contains(cleaned) else {
                return .failure(.badMode(raw, allowed: OfflineBridgeMode.allowed))
            }
            mode = cleaned
        }

        return .success(OfflineBridgeRequest(version: version, command: command,
                                             itemId: itemId, title: title, mode: mode))
    }
}

// MARK: - Errors

/// Every failure a bridge call can produce, each with a **stable code** (what the page switches on) and a
/// sentence for the human. ⚠ Two audiences, two fields: a code the page can `switch` on, and prose that
/// says what to do — a bare code is a button with no explanation.
enum OfflineBridgeError: Error, Equatable, LocalizedError {
    case notReadable(reason: String)
    case unsupportedVersion(found: Int, supported: Int)
    case unknownCommand(String)
    case missingItemId(command: String)
    case invalidItemId(itemId: String, reason: String)
    case missingTitle
    case badMode(String, allowed: [String])
    case unknownItem(itemId: String)
    case notReady(itemId: String, state: String)
    case unavailable(reason: String)

    var code: String {
        switch self {
        case .notReadable: return "notReadable"
        case .unsupportedVersion: return "unsupportedVersion"
        case .unknownCommand: return "unknownCommand"
        case .missingItemId: return "missingItemId"
        case .invalidItemId: return "invalidItemId"
        case .missingTitle: return "missingTitle"
        case .badMode: return "badMode"
        case .unknownItem: return "unknownItem"
        case .notReady: return "notReady"
        case .unavailable: return "unavailable"
        }
    }

    var errorDescription: String? {
        switch self {
        case .notReadable(let reason):
            return "The message could not be read: \(reason)."
        case .unsupportedVersion(let found, let supported):
            return found == 0
                ? "The page did not say which version of the offline bridge it speaks (this app speaks v\(supported))."
                : "The page speaks offline bridge v\(found) and this app speaks v\(supported) — update the app."
        case .unknownCommand(let raw):
            return "The page asked for \"\(raw)\", which this build does not know. It was refused rather than ignored, because ignoring it would leave the page waiting forever."
        case .missingItemId(let command):
            return "\(command) needs an itemId."
        case .invalidItemId(let itemId, let reason):
            return "That is not a usable item id (\(reason)): \(itemId.prefix(64))."
        case .missingTitle:
            return "A download needs a title, so the Downloads screen can name it."
        case .badMode(let raw, let allowed):
            return "\"\(raw)\" is not a rendition — use one of \(allowed.joined(separator: ", "))."
        case .unknownItem(let itemId):
            return "That title is not on this device: \(itemId.prefix(64))."
        case .notReady(let itemId, let state):
            return "That title is \(state) on this device, not ready to play: \(itemId.prefix(64))."
        case .unavailable(let reason):
            return reason
        }
    }

    var jsonObject: [String: Any] {
        ["code": code, "message": errorDescription ?? code]
    }
}

// MARK: - Replies: native → page

struct OfflineBridgeItem: Equatable {
    var itemId: String
    var title: String
    var state: String
    var bytes: Int64
    var totalBytes: Int64
    var mode: String
    var error: String?
    /// ⚠ Present ONLY when the server is listening and the title is ready. The page must never construct
    /// this itself: it is the one value that must not be cached.
    var url: String?
    var contentType: String?

    var jsonObject: [String: Any] {
        var object: [String: Any] = [
            "itemId": itemId, "title": title, "state": state,
            "bytes": bytes, "totalBytes": totalBytes, "mode": mode,
        ]
        object["error"] = error ?? NSNull()
        object["url"] = url ?? NSNull()
        object["contentType"] = contentType ?? NSNull()
        return object
    }
}

struct OfflineBridgePlay: Equatable {
    var itemId: String
    var url: String
    var contentType: String
    var size: Int64

    var jsonObject: [String: Any] {
        ["itemId": itemId, "url": url, "contentType": contentType, "size": size]
    }
}

struct OfflineBridgeReply: Equatable {
    var ok: Bool
    var error: OfflineBridgeError?
    var items: [OfflineBridgeItem]
    var bytes: Int64
    var play: OfflineBridgePlay?
    var accepted: String?

    static let version = OfflineBridgeRequest.supportedVersion

    static func failure(_ error: OfflineBridgeError) -> OfflineBridgeReply {
        OfflineBridgeReply(ok: false, error: error, items: [], bytes: 0, play: nil, accepted: nil)
    }

    static func listed(_ items: [OfflineBridgeItem]) -> OfflineBridgeReply {
        OfflineBridgeReply(ok: true, error: nil, items: items,
                           bytes: items.reduce(0) { $0 + $1.bytes }, play: nil, accepted: nil)
    }

    static func playable(_ target: OfflineBridgePlay) -> OfflineBridgeReply {
        OfflineBridgeReply(ok: true, error: nil, items: [], bytes: 0, play: target, accepted: nil)
    }

    /// Acknowledges a command that starts work — ⚠ it means "accepted", never "done". The result arrives as
    /// an EVENT, because a 2 GB download cannot be a return value.
    static func accepted(_ command: OfflineBridgeCommand) -> OfflineBridgeReply {
        OfflineBridgeReply(ok: true, error: nil, items: [], bytes: 0, play: nil, accepted: command.rawValue)
    }

    var jsonObject: [String: Any] {
        var result: [String: Any] = [
            "items": items.map { $0.jsonObject },
            "bytes": bytes,
            "count": items.count,
        ]
        if let play { result["play"] = play.jsonObject }
        if let accepted { result["accepted"] = accepted }

        var object: [String: Any] = ["v": Self.version, "ok": ok]
        object["result"] = result
        object["error"] = error?.jsonObject ?? NSNull()
        return object
    }
}

// MARK: - Events: native → page

enum OfflineEventPayload: Equatable {
    case state(itemId: String, title: String, state: String, bytes: Int64, totalBytes: Int64,
               mode: String, error: String?, url: String?)
    case progress(itemId: String, bytes: Int64, totalBytes: Int64, percent: Int)
    case ready(itemId: String, url: String, contentType: String, bytes: Int64)
    case removed(itemId: String)

    var name: String {
        switch self {
        case .state: return "state"
        case .progress: return "progress"
        case .ready: return "ready"
        case .removed: return "removed"
        }
    }

    var itemId: String? {
        switch self {
        case .state(let itemId, _, _, _, _, _, _, _): return itemId
        case .progress(let itemId, _, _, _): return itemId
        case .ready(let itemId, _, _, _): return itemId
        case .removed(let itemId): return itemId
        }
    }

    var jsonObject: [String: Any] {
        var object: [String: Any] = ["v": OfflineBridgeRequest.supportedVersion, "e": name]
        switch self {
        case .state(let itemId, let title, let state, let bytes, let totalBytes, let mode, let error,
                    let url):
            object["itemId"] = itemId
            object["title"] = title
            object["state"] = state
            object["bytes"] = bytes
            object["totalBytes"] = totalBytes
            object["mode"] = mode
            object["error"] = error ?? NSNull()
            object["url"] = url ?? NSNull()
        case .progress(let itemId, let bytes, let totalBytes, let percent):
            object["itemId"] = itemId
            object["bytes"] = bytes
            object["totalBytes"] = totalBytes
            object["percent"] = percent
        case .ready(let itemId, let url, let contentType, let bytes):
            object["itemId"] = itemId
            object["url"] = url
            object["contentType"] = contentType
            object["bytes"] = bytes
        case .removed(let itemId):
            object["itemId"] = itemId
        }
        return object
    }
}

/// What the native side last told the page about one title. ⚠ `emittedStep` is part of the snapshot because
/// it is the only way to throttle progress without losing the fact that it was already sent.
struct OfflineEventSnapshot: Equatable {
    var itemId: String
    var title: String
    var state: OfflineState
    var bytes: Int64
    var totalBytes: Int64
    var mode: String
    var url: String?
    var error: String?
    var emittedStep: Int

    init(itemId: String, title: String, state: OfflineState, bytes: Int64, totalBytes: Int64,
         mode: String, url: String?, error: String?, emittedStep: Int = -1) {
        self.itemId = itemId
        self.title = title
        self.state = state
        self.bytes = bytes
        self.totalBytes = totalBytes
        self.mode = mode
        self.url = url
        self.error = error
        self.emittedStep = emittedStep
    }

    var percent: Int? {
        guard totalBytes > 0 else { return nil }
        let fraction = Double(bytes) / Double(totalBytes)
        return max(0, min(100, Int((fraction * 100).rounded(.down))))
    }
}

enum OfflineEventDecision: Equatable {
    case nothing
    case state
    case ready
    case progress(step: Int)
}

/// Decides whether a change is worth waking the page for, and with what. Pure so it can be *executed*.
enum OfflineEventPlanner {

    /// ⚠ **State changes are never throttled; progress is always throttled.** They are different promises:
    /// a missed state change is a UI that lies about a download, and an unthrottled progress stream is
    /// ~10 `evaluateJavaScript` calls a second for a number that moves by a tenth of a percent.
    static func decide(previous: OfflineEventSnapshot?, current: OfflineEventSnapshot) -> OfflineEventDecision {
        // ⚠ The page is never assumed to know anything. Every title is announced at least once per process,
        // which is also what makes the page's first paint correct instead of "wait for something to change".
        guard let previous else { return .state }

        if previous.state != current.state { return .state }
        if previous.title != current.title { return .state }
        if previous.mode != current.mode { return .state }
        if previous.totalBytes != current.totalBytes { return .state }
        if previous.error != current.error { return .state }

        // The URL appearing is the ONE change with its own event, because it is the moment a film becomes
        // playable with the network off.
        if previous.url == nil, let url = current.url, !url.isEmpty { return .ready }
        if previous.url != current.url { return .state }

        // ⚠ Progress only while a download is actually moving.
        guard current.state == .downloading else { return .nothing }
        // ⚠ One guard, in ONE place: `percent` is nil exactly when the total is unknown, and an unknown
        // total must never become a number the UI can draw a bar from ("0%" over a file whose size we do
        // not know is a lie — B2 already shows a dash in this case).
        guard let step = current.percent else { return .nothing }

        // ⚠ A step that went BACKWARDS is a restart, not progress — it must come through as a state change,
        // because a bar that silently rewinds is worse than one that jumps.
        if step < previous.emittedStep { return .state }

        guard step > previous.emittedStep else { return .nothing }
        return .progress(step: step)
    }

    /// ⚠ What to remember as already-sent after a STATE change.
    ///
    /// A state change and a progress step are different promises, and this is the seam between them: state
    /// must never be throttled, but the throttle itself must survive — otherwise a download that reports its
    /// state every tick would be re-announced forever. And when the step went BACKWARDS (a restart), the
    /// throttle is reset, because a restart at 3% with 60% remembered would otherwise emit a state event on
    /// every single tick until it climbed past the old number.
    static func stepAfterStateChange(previous: OfflineEventSnapshot?, current: OfflineEventSnapshot) -> Int {
        let remembered = previous?.emittedStep ?? -1
        guard let step = current.percent else { return -1 }   // an unknown total has no step to remember
        return step < remembered ? step : remembered
    }

    /// The titles the page still believes in but native has forgotten. ⚠ Sorted, so the payload order is
    /// deterministic rather than whatever the dictionary iterated as.
    static func vanished(previous: [String], current: [String]) -> [String] {
        let live = Set(current)
        return previous.filter { !live.contains($0) }.sorted()
    }
}
