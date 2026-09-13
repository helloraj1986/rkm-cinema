import XCTest
@testable import RKMServerKit

final class CorrelationIDTests: XCTestCase {

    func testFormatIsSixLowercaseHexCharacters() {
        XCTAssertNotNil(CorrelationID(rawValue: "7f3a2c"))
        XCTAssertNotNil(CorrelationID(rawValue: "000000"))
        XCTAssertEqual(CorrelationID(rawValue: "7f3a2c")?.description, "7f3a2c")
    }

    func testAnythingElseIsRefused() {
        // A malformed id would silently stop matching the HUD, so it is refused rather than
        // trimmed into something plausible.
        XCTAssertNil(CorrelationID(rawValue: "7F3A2C"), "uppercase breaks a literal grep")
        XCTAssertNil(CorrelationID(rawValue: "7f3a2"))
        XCTAssertNil(CorrelationID(rawValue: "7f3a2c8"))
        XCTAssertNil(CorrelationID(rawValue: "7f3a2g"))
        XCTAssertNil(CorrelationID(rawValue: ""))
    }

    func testIDsAreUniqueWithinARun() {
        // ⚠ Uniqueness is what makes "grep the id from the screenshot" land on the right lines
        // and only the right lines.
        var seen = Set<String>()
        for _ in 0..<5_000 {
            let id = CorrelationID.next()
            XCTAssertEqual(id.rawValue.count, CorrelationID.length)
            seen.insert(id.rawValue)
        }
        XCTAssertEqual(seen.count, 5_000)
    }
}

final class LogEntryTests: XCTestCase {

    func testFileLineFormat() throws {
        let entry = LogEntry(
            id: 1,
            timestamp: Date(timeIntervalSince1970: 0),
            level: .verbose,
            category: .net,
            correlationID: try XCTUnwrap(CorrelationID(rawValue: "7f3a2c")),
            message: "GET /api/status -> 200"
        )
        // Category is padded to 8 so the message column starts at a fixed offset — the log is
        // meant to be read in a terminal and grepped.
        let expected = "[1970-01-01 00:00:00.000] V [7f3a2c] net"
            + String(repeating: " ", count: 6)
            + "GET /api/status -> 200"
        XCTAssertEqual(entry.text(timeZone: try XCTUnwrap(TimeZone(secondsFromGMT: 0))), expected)
    }

    func testALineWithNoCorrelationIDKeepsTheColumn() {
        let entry = LogEntry(id: 2, timestamp: Date(), level: .info, category: .app,
                             correlationID: nil, message: "launched")
        XCTAssertTrue(entry.text().contains("[\(CorrelationID.none)]"))
        XCTAssertTrue(entry.hudText.hasPrefix("[\(CorrelationID.none)] app"))
    }

    func testByteAndDurationFormattingMatchesTheSpec() {
        XCTAssertEqual(LogFormat.bytes(834), "834 B")
        XCTAssertEqual(LogFormat.bytes(1200), "1.2 KB")
        XCTAssertEqual(LogFormat.bytes(3_400_000), "3.40 MB")
        XCTAssertEqual(LogFormat.bytes(nil), "unknown size")
        XCTAssertEqual(LogFormat.duration(milliseconds: 84), "84ms")
        XCTAssertEqual(LogFormat.duration(milliseconds: 1240), "1.24s")
    }

    func testLogLevelsAreOrderedAsTheDocsDescribeThem() {
        XCTAssertTrue(LogLevel.verbose > LogLevel.info)
        XCTAssertTrue(LogLevel.info > LogLevel.error)
        XCTAssertTrue(LogLevel.error > LogLevel.off)
        XCTAssertEqual(LogLevel.named("verbose"), .verbose)
        XCTAssertEqual(LogLevel.named("OFF"), .off)
        XCTAssertNil(LogLevel.named("loud"))
    }
}

final class LogRingBufferTests: XCTestCase {

    func testHoldsTheMostRecentEntriesOnly() {
        let buffer = LogRingBuffer(capacity: 3)
        for index in 0..<5 {
            buffer.append(LogEntry(id: UInt64(index), timestamp: Date(), level: .info,
                                   category: .app, correlationID: nil, message: "line \(index)"))
        }
        XCTAssertEqual(buffer.count, 3)
        XCTAssertEqual(buffer.newestFirst.first?.message, "line 4")
        XCTAssertEqual(buffer.all.map(\.message), ["line 2", "line 3", "line 4"])
        XCTAssertEqual(buffer.recent(2).map(\.message), ["line 4", "line 3"])
    }

    func testClear() {
        let buffer = LogRingBuffer(capacity: 4)
        buffer.append(LogEntry(id: 1, timestamp: Date(), level: .info, category: .app,
                               correlationID: nil, message: "x"))
        buffer.clear()
        XCTAssertEqual(buffer.count, 0)
    }
}

final class RollingFileLogTests: XCTestCase {

    func testWritesAndReadsBack() throws {
        let directory = makeTemporaryDirectory()
        defer { try? FileManager.default.removeItem(at: directory) }

        let log = try RollingFileLog(directory: directory, policy: policy(maxFiles: 5))
        log.append("first")
        log.append(LogEntry(id: 2, timestamp: Date(timeIntervalSince1970: 0), level: .info,
                            category: .net, correlationID: nil, message: "second"))
        log.flush()

        let contents = try String(contentsOf: log.currentFileURL, encoding: .utf8)
        XCTAssertTrue(contents.contains("first"))
        XCTAssertTrue(contents.contains("second"))
        XCTAssertEqual(contents.split(separator: "\n").count, 2)
    }

    func testRotationBoundsWhatIsKeptOnDisk() throws {
        let directory = makeTemporaryDirectory()
        defer { try? FileManager.default.removeItem(at: directory) }

        let log = try RollingFileLog(directory: directory, policy: policy(maxFiles: 3))
        log.append("FIRST-LINE")
        for index in 0..<400 {
            log.append(String(repeating: "x", count: 800) + " \(index)")
        }
        log.append("LAST-MARKER")
        log.flush()

        let files = try logFiles(in: directory)
        XCTAssertLessThanOrEqual(files.count, 3, "the cap must bound disk use")
        XCTAssertGreaterThanOrEqual(files.count, 2, "it should have rotated at least once")

        let current = try String(contentsOf: log.currentFileURL, encoding: .utf8)
        XCTAssertTrue(current.contains("LAST-MARKER"))
        XCTAssertLessThanOrEqual(log.currentFileByteSize, 64 * 1024)

        let everything = files.compactMap { try? String(contentsOf: $0, encoding: .utf8) }.joined()
        XCTAssertFalse(everything.contains("FIRST-LINE"),
                       "the oldest lines must be evicted — a cap that keeps everything is not a cap")
    }

    func testRemoveAllFilesLeavesACleanDirectory() throws {
        let directory = makeTemporaryDirectory()
        defer { try? FileManager.default.removeItem(at: directory) }

        let log = try RollingFileLog(directory: directory, policy: policy(maxFiles: 3))
        for index in 0..<200 { log.append(String(repeating: "y", count: 800) + " \(index)") }
        XCTAssertGreaterThan(try logFiles(in: directory).count, 1)

        log.removeAllFiles()
        let remaining = try logFiles(in: directory)
        XCTAssertEqual(remaining.count, 1)
        XCTAssertEqual(log.currentFileByteSize, 0)
    }

    private func policy(maxFiles: Int) -> RollingFileLog.Policy {
        // The 64 KiB floor in `Policy` is what keeps a silly value from rotating per line.
        RollingFileLog.Policy(maxFileBytes: 64 * 1024, maxFiles: maxFiles, baseName: "test.log")
    }

    private func logFiles(in directory: URL) throws -> [URL] {
        try FileManager.default
            .contentsOfDirectory(at: directory, includingPropertiesForKeys: nil)
            .filter { $0.lastPathComponent.hasPrefix("test") }
    }
}

/// The end-to-end behaviour Phase 0 is judged on: a line goes in, and **nothing the §9 grep
/// looks for comes out** — plus the correlation id, status and sizes are all present.
final class RKMLogTests: XCTestCase {

    func testGateHoldsAndTheRequestLineIsUseful() throws {
        let directory = makeTemporaryDirectory()
        defer { try? FileManager.default.removeItem(at: directory) }

        let fileLog = try RollingFileLog(directory: directory, policy: .init(baseName: "gate.log"))
        let log = RKMLog(ringCapacity: 50)
        log.configure(level: .verbose, fileLog: fileLog)

        let identifier = try XCTUnwrap(CorrelationID(rawValue: "7f3a2c"))
        log.request(correlation: identifier, method: "get",
                    url: "/api/library/continue-watching?token=abc123&limit=20",
                    status: 200, milliseconds: 84, bytes: 1200)
        log.error("login refused: password=hunter2", category: .auth)
        log.info("Cookie: rkm_session=deadbeef; locale=en", category: .auth)
        log.verbose("jellyfin api_key: 0123456789abcdef", category: .library)
        log.info("home rows rendered: 2 (cw=8, recent=12)", category: .ui)
        fileLog.flush()

        let contents = try String(contentsOf: fileLog.currentFileURL, encoding: .utf8)

        // ⚠ `LOGGING.md` §9 item 3 — the acceptance command, applied to a real file.
        XCTAssertEqual(LogRedactor.leaks(contents), [],
                       "this is the credential-leak gate:\n\(contents)")

        // §9 items 1 and 2 — one file with every request, its status, duration and the id.
        XCTAssertTrue(contents.contains("[7f3a2c]"), "the correlation id must be in the file")
        XCTAssertTrue(contents.contains("-> 200"))
        XCTAssertTrue(contents.contains("84ms"))
        XCTAssertTrue(contents.contains("1.2 KB"))
        XCTAssertTrue(contents.contains("GET /api/library/continue-watching?cred=[redacted]&limit=20"))
        XCTAssertTrue(contents.contains("home rows rendered"))

        // The HUD reads the same entries, which is what joins a screenshot to the file.
        XCTAssertEqual(log.ring.count, 5)
        XCTAssertEqual(log.ring.newestFirst.first?.message.contains("home rows"), true)
    }

    func testFailedRequestsAreLoggedAsErrors() throws {
        let directory = makeTemporaryDirectory()
        defer { try? FileManager.default.removeItem(at: directory) }

        let fileLog = try RollingFileLog(directory: directory, policy: .init(baseName: "fail.log"))
        let log = RKMLog()
        log.configure(level: .verbose, fileLog: fileLog)
        log.request(correlation: CorrelationID.next(), method: "GET", url: "/api/status",
                    milliseconds: 8000,
                    error: "NSURLErrorDomain -1004 (Could not connect to the server)")
        fileLog.flush()

        let contents = try String(contentsOf: fileLog.currentFileURL, encoding: .utf8)
        XCTAssertTrue(contents.contains("-> no response"))
        XCTAssertTrue(contents.contains("-1004"))
        XCTAssertTrue(contents.contains("] E ["),
                      "a transport failure logs at error level, not information")
    }

    func testLevelFilteringQuietsEverythingIncludingTheHUD() throws {
        let directory = makeTemporaryDirectory()
        defer { try? FileManager.default.removeItem(at: directory) }

        let fileLog = try RollingFileLog(directory: directory, policy: .init(baseName: "level.log"))
        let log = RKMLog()
        log.configure(level: .error, fileLog: fileLog)
        log.verbose("noise", category: .ui)
        log.info("also noise", category: .ui)
        log.error("real problem", category: .app)
        fileLog.flush()

        let contents = try String(contentsOf: fileLog.currentFileURL, encoding: .utf8)
        XCTAssertFalse(contents.contains("noise"))
        XCTAssertTrue(contents.contains("real problem"))
        // ⚠ Both sinks are gated together — a HUD showing more than the file would break the
        // one property that makes a screenshot useful.
        XCTAssertEqual(log.ring.count, 1)
    }

    func testOffSilencesEverything() throws {
        let log = RKMLog()
        log.configure(level: .off, fileLog: nil)
        XCTAssertNil(log.error("must not be recorded", category: .app))
        XCTAssertEqual(log.ring.count, 0)
    }

    func testBothShorthandStylesCompileAndWork() {
        // Call sites use both: `RKMLog.shared.info(…)` inside reference types and the static
        // form where there is no receiver to hand.
        let log = RKMLog(ringCapacity: 10)
        log.info("via the instance", category: .app)
        RKMLog.info("via the shared instance", category: .app)
        XCTAssertEqual(log.ring.count, 1)
        XCTAssertGreaterThanOrEqual(RKMLog.shared.ring.count, 1)
        XCTAssertEqual(RKMLog.subsystem, "com.helloraj1986.rkmcinema",
                       "must match LOGGING.md §7's log stream --subsystem filter")
    }

    func testStoredLevelFallsBackToVerboseForTheDevPhase() {
        let defaults = UserDefaults(suiteName: "RKMServerKitTests.\(UUID().uuidString)")
        XCTAssertEqual(RKMLog.storedLevel(default: .verbose, defaults: defaults ?? .standard), .verbose)
        defaults?.set("info", forKey: RKMLog.levelDefaultsKey)
        XCTAssertEqual(RKMLog.storedLevel(default: .verbose, defaults: defaults ?? .standard), .info)
    }

    func testAFileSinkFailureDoesNotStopTheAppLogging() {
        // The file is best-effort: the ring (and therefore the HUD) and os_log still get the line.
        let log = RKMLog(ringCapacity: 10)
        log.configure(level: .verbose, fileLog: nil)
        XCTAssertNotNil(log.info("still recorded", category: .app))
        XCTAssertEqual(log.ring.count, 1)
        XCTAssertFalse(log.isWritingToFile)
    }
}

private func makeTemporaryDirectory() -> URL {
    let url = FileManager.default.temporaryDirectory
        .appendingPathComponent("RKMServerKitTests-\(UUID().uuidString)", isDirectory: true)
    try? FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
    return url
}
