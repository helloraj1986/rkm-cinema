import Foundation

/// The last few hundred finished log lines, held in memory for the debug HUD.
///
/// ⚠ Why the HUD reads **this** rather than keeping its own list: it guarantees the HUD and
/// the file log agree. `LOGGING.md` §9's second acceptance item is "given only a HUD
/// correlation id from a screenshot, the matching log lines can be found" — that only holds
/// if what is on screen is literally what was written.
public final class LogRingBuffer: @unchecked Sendable {

    private let lock = NSLock()
    private var storage: [LogEntry] = []

    public let capacity: Int

    public init(capacity: Int = 250) {
        self.capacity = max(1, capacity)
    }

    public func append(_ entry: LogEntry) {
        lock.lock()
        defer { lock.unlock() }
        storage.append(entry)
        if storage.count > capacity {
            storage.removeFirst(storage.count - capacity)
        }
    }

    /// Oldest first — file order.
    public var all: [LogEntry] {
        lock.lock()
        defer { lock.unlock() }
        return storage
    }

    /// Newest first — the order the HUD draws them in.
    public var newestFirst: [LogEntry] {
        Array(all.reversed())
    }

    public func recent(_ count: Int) -> [LogEntry] {
        Array(newestFirst.prefix(max(0, count)))
    }

    public var count: Int {
        lock.lock()
        defer { lock.unlock() }
        return storage.count
    }

    public func clear() {
        lock.lock()
        storage.removeAll()
        lock.unlock()
    }
}
