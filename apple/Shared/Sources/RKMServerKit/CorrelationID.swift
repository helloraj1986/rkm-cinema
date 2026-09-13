import Foundation

/// The id that joins a screenshot to a log file.
///
/// ⚠ This is the highest-value item in `apple/LOGGING.md` (§2): every request gets an id, the
/// debug HUD displays it, and the matching lines are then a `grep` away. Without it, a
/// screenshot of a TV or an iPad and a 5000-line log **cannot be joined up**.
///
/// Six lowercase hex characters, because that is what the HUD sample shows (`[7f3a2c]`) and
/// what the web-UI instrumentation mints in JavaScript. Native mints its own for requests the
/// app makes itself (the reachability probe, navigation events); the shell adopts the ids the
/// page mints for its own `fetch`/XHR calls, so the id in the HUD is the id in the log.
public struct CorrelationID: Hashable, Sendable, CustomStringConvertible, Comparable {

    /// Fixed width, so log columns line up and `grep` is predictable.
    public static let length = 6

    /// The placeholder written when a line has no correlation id — keeps the column stable.
    public static let none = "------"

    public let rawValue: String

    /// Fails unless it is exactly ``length`` lowercase hex characters. Anything else is a
    /// bug in the caller, not something to paper over — a truncated id silently stops
    /// matching the HUD.
    public init?(rawValue: String) {
        guard rawValue.count == Self.length else { return nil }
        guard rawValue.allSatisfy({ $0.isHexDigit && !$0.isUppercase }) else { return nil }
        self.rawValue = rawValue
    }

    /// Internal unchecked path for ``next()``, which formats its own hex.
    private init(unchecked value: String) {
        rawValue = value
    }

    private static let lock = NSLock()
    private static var counter: UInt32 = UInt32.random(in: 0..<0x1000)

    /// A fresh id, **unique within this run** — a counter mixed with a random start, rather
    /// than pure randomness, so two requests can never collide inside one test round and
    /// send a `grep` to the wrong lines.
    public static func next() -> CorrelationID {
        lock.lock()
        defer { lock.unlock() }
        counter = (counter &+ 1) & 0xFFFFFF
        return CorrelationID(unchecked: String(format: "%06x", counter))
    }

    public var description: String { rawValue }

    public static func < (lhs: CorrelationID, rhs: CorrelationID) -> Bool {
        lhs.rawValue < rhs.rawValue
    }
}
