import Foundation

#if canImport(os)
import os
#endif

/// The log facade both apps write through — the **one** place a line becomes three things at
/// once (`apple/LOGGING.md` §1):
///
/// | sink | who it is for | why |
/// |---|---|---|
/// | structured `os.Logger` (subsystem + category) | him, live, via `log stream` | filter to one area while testing |
/// | capped rolling **file** | me, afterwards | ⚠ `os_log` alone loses an un-streamed run (`.debug` is not persisted) |
/// | in-memory ring → debug HUD | screenshots | the correlation id rides in the picture |
///
/// ⚠ Redaction happens **here**, once, on the way in — never at a call site. A line that
/// somehow still contains a sensitive key name is *withheld* rather than written, so a
/// redaction bug costs a log line instead of an account.
public final class RKMLog: @unchecked Sendable {

    public static let shared = RKMLog()

    /// ⚠ Must match `LOGGING.md` §7's `log stream --subsystem …`, which is the command he runs
    /// from the Mac. Kept identical for the tvOS app on purpose: one filter for both.
    public static let subsystem = "com.helloraj1986.rkmcinema"

    /// Read at launch. Also settable from a scheme launch argument (`-RKMLogLevel info`),
    /// which is how the level gets changed with no code change and no rebuild.
    public static let levelDefaultsKey = "RKMLogLevel"

    /// The HUD reads this. Same entries as the file got.
    public let ring: LogRingBuffer

    private let lock = NSLock()
    private var currentLevel: LogLevel = .verbose
    private var fileSink: RollingFileLog?
    private var sequence: UInt64 = 0

    #if canImport(os)
    private var systemLoggers: [String: Logger] = [:]
    #endif

    public init(ringCapacity: Int = 250) {
        ring = LogRingBuffer(capacity: ringCapacity)
    }

    // MARK: - Configuration

    public var level: LogLevel {
        lock.lock()
        defer { lock.unlock() }
        return currentLevel
    }

    /// Where the file log is, for the launch banner and for telling him which file to paste.
    public var fileURL: URL? {
        lock.lock()
        defer { lock.unlock() }
        return fileSink?.currentFileURL
    }

    public var isWritingToFile: Bool {
        lock.lock()
        defer { lock.unlock() }
        return fileSink != nil
    }

    public func configure(level: LogLevel, fileLog: RollingFileLog?) {
        lock.lock()
        currentLevel = level
        fileSink = fileLog
        lock.unlock()
    }

    /// The level to start at: the stored/launch-argument value, else the dev default.
    ///
    /// ⚠ The fallback is `verbose`, not `info`, for the whole dev phase — that is the
    /// requirement this logging exists to satisfy. Production gets quiet by setting one value.
    public static func storedLevel(default fallback: LogLevel = .verbose,
                                   defaults: UserDefaults = .standard) -> LogLevel {
        if let raw = defaults.string(forKey: levelDefaultsKey), let parsed = LogLevel.named(raw) {
            return parsed
        }
        if let object = defaults.object(forKey: levelDefaultsKey),
           let parsed = LogLevel.named("\(object)") {
            return parsed
        }
        return fallback
    }

    /// Flush the file to disk. Called when the app backgrounds, not per line.
    public func flush() {
        lock.lock()
        let sink = fileSink
        lock.unlock()
        sink?.flush()
    }

    // MARK: - Writing

    @discardableResult
    public func log(_ level: LogLevel,
                    _ message: String,
                    category: LogCategory,
                    correlation: CorrelationID? = nil,
                    file: String = #fileID,
                    line: Int = #line) -> LogEntry? {
        guard level != .off else { return nil }

        lock.lock()
        let threshold = currentLevel
        let sink = fileSink
        lock.unlock()

        guard level <= threshold else { return nil }

        var text = message
        // Where an error came from, so a failure in the log is as locatable as a crash.
        if level == .error {
            text += " (\(Self.shortLocation(file)):\(line))"
        }

        let safe = LogRedactor.redact(text: text)
        guard LogRedactor.isSafe(safe) else {
            // ⚠ Fail closed. The sweep should make this unreachable; if it ever is reached, a
            // missing line is the correct outcome and a leaked credential is not.
            return nil
        }

        lock.lock()
        sequence += 1
        let entry = LogEntry(
            id: sequence,
            timestamp: Date(),
            level: level,
            category: category,
            correlationID: correlation,
            message: safe
        )
        lock.unlock()

        sink?.append(entry.text())
        ring.append(entry)
        writeSystemLog(entry)
        return entry
    }

    @discardableResult
    public func verbose(_ message: String, category: LogCategory, correlation: CorrelationID? = nil,
                        file: String = #fileID, line: Int = #line) -> LogEntry? {
        log(.verbose, message, category: category, correlation: correlation, file: file, line: line)
    }

    @discardableResult
    public func info(_ message: String, category: LogCategory, correlation: CorrelationID? = nil,
                     file: String = #fileID, line: Int = #line) -> LogEntry? {
        log(.info, message, category: category, correlation: correlation, file: file, line: line)
    }

    @discardableResult
    public func error(_ message: String, category: LogCategory, correlation: CorrelationID? = nil,
                      file: String = #fileID, line: Int = #line) -> LogEntry? {
        log(.error, message, category: category, correlation: correlation, file: file, line: line)
    }

    // MARK: - The request line

    /// `GET /api/status -> 200 in 84ms (1.2 KB)`, one correlation id, redacted URL.
    ///
    /// ⚠ This is the **only** place that format is built. Both the native requests and the
    /// ones the iOS shell reports out of the page come through here, which is what keeps the
    /// HUD line and the file line identical — and keeps redaction in one place.
    @discardableResult
    public func request(correlation: CorrelationID,
                        method: String,
                        url: String,
                        status: Int? = nil,
                        milliseconds: Int? = nil,
                        bytes: Int? = nil,
                        error: String? = nil,
                        category: LogCategory = .net) -> LogEntry? {
        var parts: [String] = ["\(method.uppercased()) \(LogRedactor.redact(urlString: url))"]
        if let status {
            parts.append("-> \(status)")
        } else {
            parts.append("-> no response")
        }
        if let milliseconds {
            parts.append("in \(LogFormat.duration(milliseconds: milliseconds))")
        }
        if let bytes {
            parts.append("(\(LogFormat.bytes(bytes)))")
        }
        if let error {
            parts.append("error: \(error)")
        }
        let level: LogLevel = error == nil ? .info : .error
        return log(level, parts.joined(separator: " "), category: category, correlation: correlation)
    }

    // MARK: - Global shorthands

    @discardableResult
    public static func verbose(_ message: String, category: LogCategory, correlation: CorrelationID? = nil,
                               file: String = #fileID, line: Int = #line) -> LogEntry? {
        shared.verbose(message, category: category, correlation: correlation, file: file, line: line)
    }

    @discardableResult
    public static func info(_ message: String, category: LogCategory, correlation: CorrelationID? = nil,
                            file: String = #fileID, line: Int = #line) -> LogEntry? {
        shared.info(message, category: category, correlation: correlation, file: file, line: line)
    }

    @discardableResult
    public static func error(_ message: String, category: LogCategory, correlation: CorrelationID? = nil,
                             file: String = #fileID, line: Int = #line) -> LogEntry? {
        shared.error(message, category: category, correlation: correlation, file: file, line: line)
    }

    @discardableResult
    public static func request(correlation: CorrelationID, method: String, url: String,
                               status: Int? = nil, milliseconds: Int? = nil, bytes: Int? = nil,
                               error: String? = nil, category: LogCategory = .net) -> LogEntry? {
        shared.request(correlation: correlation, method: method, url: url, status: status,
                       milliseconds: milliseconds, bytes: bytes, error: error, category: category)
    }

    // MARK: - Internals

    /// `#fileID` is "Module/File.swift"; the file alone is what fits on a log line.
    private static func shortLocation(_ fileID: String) -> String {
        String(fileID.split(separator: "/").last ?? Substring(fileID))
    }

    #if canImport(os)
    private func writeSystemLog(_ entry: LogEntry) {
        let logger = systemLogger(entry.category)
        let identifier = entry.correlationID?.rawValue ?? CorrelationID.none
        // ⚠ `privacy: .public` is deliberate, and it is only safe because `entry.message` has
        // already been through `LogRedactor`. Without it, `log stream` on the Mac prints
        // "<private>" instead of the message — which would quietly make the live half of
        // `LOGGING.md` §7 useless.
        //
        // ⚠ `verbose` maps to `debug`, which `os_log` does **not** persist. That is not a
        // mistake: it is exactly why layer 2 (the file) exists. Live streaming shows
        // everything; the file has everything after the fact.
        switch entry.level {
        case .error:
            logger.error("[\(identifier, privacy: .public)] \(entry.message, privacy: .public)")
        case .info:
            logger.info("[\(identifier, privacy: .public)] \(entry.message, privacy: .public)")
        default:
            logger.debug("[\(identifier, privacy: .public)] \(entry.message, privacy: .public)")
        }
    }

    private func systemLogger(_ category: LogCategory) -> Logger {
        lock.lock()
        defer { lock.unlock() }
        if let existing = systemLoggers[category.rawValue] { return existing }
        let logger = Logger(subsystem: Self.subsystem, category: category.rawValue)
        systemLoggers[category.rawValue] = logger
        return logger
    }
    #else
    /// Linux (the sandbox's `swift test`) has no `os_log`; the file + ring sinks are the whole
    /// log, which is enough to test the behaviour that matters.
    private func writeSystemLog(_ entry: LogEntry) {}
    #endif
}
