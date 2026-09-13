import Foundation

/// How loud the log is — `apple/LOGGING.md` §5.
///
/// Driven by a single stored value (or a launch argument), so production can be quiet
/// without a code change; verbose stays on for the whole dev phase, which is exactly what
/// was asked for.
public enum LogLevel: Int, Comparable, CaseIterable, Sendable {
    case off = 0
    case error = 1
    case info = 2
    case verbose = 3

    public static func < (lhs: LogLevel, rhs: LogLevel) -> Bool {
        lhs.rawValue < rhs.rawValue
    }

    public var name: String {
        switch self {
        case .off: return "off"
        case .error: return "error"
        case .info: return "info"
        case .verbose: return "verbose"
        }
    }

    /// One character, so every line stays greppable and narrow.
    public var label: String {
        switch self {
        case .off: return "-"
        case .error: return "E"
        case .info: return "I"
        case .verbose: return "V"
        }
    }

    public static func named(_ text: String) -> LogLevel? {
        let wanted = text.lowercased().trimmingCharacters(in: .whitespacesAndNewlines)
        return allCases.first { $0.name == wanted }
    }
}

/// The `os.Logger` category, and the middle column of every log line.
///
/// One category per area of the app so `log stream --predicate 'category == "net"'` can be
/// pointed at exactly one thing (`LOGGING.md` §1) — and so the file log can be grepped the
/// same way.
public enum LogCategory: String, CaseIterable, Sendable {
    case app
    case nav
    case net
    case auth
    case library
    case playback
    /// What the SwiftUI layer did — row counts, state changes.
    case ui
    /// Anything from inside the web page: `console.*`, JS errors, unhandled rejections.
    case web

    /// Padded so the message column starts at the same offset on every line.
    public var label: String {
        rawValue.count >= 8 ? rawValue : rawValue + String(repeating: " ", count: 8 - rawValue.count)
    }
}

/// One finished log line. Built by ``RKMLog``, written to the file and held in the ring
/// buffer the debug HUD reads — so **the HUD shows exactly what the file got**, which is the
/// property that makes a screenshot and a log agree.
public struct LogEntry: Sendable, Identifiable, Hashable {
    public let id: UInt64
    public let timestamp: Date
    public let level: LogLevel
    public let category: LogCategory
    public let correlationID: CorrelationID?
    public let message: String

    public init(
        id: UInt64,
        timestamp: Date,
        level: LogLevel,
        category: LogCategory,
        correlationID: CorrelationID?,
        message: String
    ) {
        self.id = id
        self.timestamp = timestamp
        self.level = level
        self.category = category
        self.correlationID = correlationID
        self.message = message
    }

    /// The file-log line:
    ///
    ///     [2026-09-14 10:00:00.123] V [7f3a2c] net      GET /api/status -> 200 (84ms, 1.2 KB)
    ///
    /// ASCII only (`->`, not an arrow) so it greps cleanly from any shell on either machine.
    public func text(timeZone: TimeZone = .current) -> String {
        let stamp = LogTimestamp.string(timestamp, timeZone: timeZone)
        let identifier = correlationID?.rawValue ?? CorrelationID.none
        return "[\(stamp)] \(level.label) [\(identifier)] \(category.label) \(message)"
    }

    /// The shorter form for the on-screen HUD — same id, no timestamp.
    public var hudText: String {
        "[\(correlationID?.rawValue ?? CorrelationID.none)] \(category.label) \(message)"
    }
}

/// Formatting helpers shared by the log and the HUD, so a size or a duration reads the same
/// in both places.
public enum LogFormat {

    /// `834 B` · `1.2 KB` · `3.40 MB` — or `unknown size` when the response did not say.
    public static func bytes(_ count: Int?) -> String {
        guard let count else { return "unknown size" }
        let value = Double(count)
        if count < 1000 { return "\(count) B" }
        if count < 1_000_000 { return String(format: "%.1f KB", value / 1000) }
        return String(format: "%.2f MB", value / 1_000_000)
    }

    /// `84ms` · `1.24s`.
    public static func duration(milliseconds: Int) -> String {
        if milliseconds < 1000 { return "\(milliseconds)ms" }
        return String(format: "%.2fs", Double(milliseconds) / 1000)
    }
}

/// A lock-protected timestamp formatter. `DateFormatter` is not thread-safe and log lines
/// arrive from the main thread, the WebKit delegate queue and the URL session at once.
enum LogTimestamp {
    private static let lock = NSLock()
    private static var formatters: [String: DateFormatter] = [:]

    static func string(_ date: Date, timeZone: TimeZone) -> String {
        lock.lock()
        defer { lock.unlock() }

        let key = timeZone.identifier
        if let existing = formatters[key] {
            return existing.string(from: date)
        }
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyy-MM-dd HH:mm:ss.SSS"
        formatter.timeZone = timeZone
        formatters[key] = formatter
        return formatter.string(from: date)
    }
}
