import XCTest
@testable import RKMServerKit

/// ⚠ These are the Phase 0 gate that does **not** need his Mac: pure Swift, no UIKit, no
/// Apple SDK. The UI half of Phase 0 is unverified until Xcode builds it (`apple/WORKFLOW.md` §5).
final class ServerAddressTests: XCTestCase {

    // MARK: - The two addresses the docs actually name

    func testTailscaleNameGetsHTTPS() throws {
        let address = try ServerAddress(rawValue: "rkm-hp.tail8d5e8.ts.net")
        XCTAssertEqual(address.displayString, "https://rkm-hp.tail8d5e8.ts.net")
        XCTAssertEqual(address.scheme, "https")
        XCTAssertEqual(address.host, "rkm-hp.tail8d5e8.ts.net")
        XCTAssertNil(address.port)
        XCTAssertFalse(address.hadExplicitScheme, "the scheme was supplied, not typed")
        XCTAssertTrue(address.isLikelyTailscale)
        XCTAssertFalse(address.isLikelyOnLocalNetwork)
    }

    func testDocumentedLANAddressIsLeftAlone() throws {
        let address = try ServerAddress(rawValue: "http://192.168.1.10:8124")
        XCTAssertEqual(address.displayString, "http://192.168.1.10:8124")
        XCTAssertEqual(address.port, 8124)
        XCTAssertTrue(address.hadExplicitScheme)
        XCTAssertTrue(address.isLikelyOnLocalNetwork)
        XCTAssertTrue(address.usesPlainHTTP)
    }

    // MARK: - The refinement that keeps a LAN address from looking broken

    func testBareLANAddressWithAPortAssumesPlainHTTP() throws {
        // ⚠ nginx serves this stack as plain HTTP on a LAN; assuming https here would fail in
        // exactly the way that makes an app look broken.
        let address = try ServerAddress(rawValue: "192.168.1.10:8124")
        XCTAssertEqual(address.displayString, "http://192.168.1.10:8124")
        XCTAssertFalse(address.hadExplicitScheme)
    }

    func testBareIPLiteralAssumesPlainHTTP() throws {
        XCTAssertEqual(try ServerAddress(rawValue: "10.0.0.5").displayString, "http://10.0.0.5")
        XCTAssertEqual(try ServerAddress(rawValue: "localhost").displayString, "http://localhost")
        XCTAssertEqual(try ServerAddress(rawValue: "nas.local").displayString, "http://nas.local")
    }

    func testTLSPortsKeepHTTPS() throws {
        XCTAssertEqual(try ServerAddress(rawValue: "rkm-hp.example.com:443").displayString,
                       "https://rkm-hp.example.com:443")
        XCTAssertEqual(try ServerAddress(rawValue: "rkm-hp.example.com:8443").displayString,
                       "https://rkm-hp.example.com:8443")
    }

    // MARK: - Normalisation

    func testTrailingSlashIsStripped() throws {
        XCTAssertEqual(try ServerAddress(rawValue: "https://rkm-hp.tail8d5e8.ts.net/").displayString,
                       "https://rkm-hp.tail8d5e8.ts.net")
        XCTAssertEqual(try ServerAddress(rawValue: "http://host:8124///").displayString,
                       "http://host:8124")
    }

    func testWhitespaceAndPastedAngleBrackets() throws {
        XCTAssertEqual(try ServerAddress(rawValue: "  http://192.168.1.10:8124 \n").displayString,
                       "http://192.168.1.10:8124")
        XCTAssertEqual(try ServerAddress(rawValue: "<https://rkm-hp.tail8d5e8.ts.net>").displayString,
                       "https://rkm-hp.tail8d5e8.ts.net")
    }

    func testSchemeAndHostAreLowercased() throws {
        let address = try ServerAddress(rawValue: "HTTPS://RKM-HP.Tail8D5E8.TS.NET/")
        XCTAssertEqual(address.displayString, "https://rkm-hp.tail8d5e8.ts.net")
        XCTAssertEqual(address.scheme, "https")
    }

    func testSingleSlashSchemeTypoIsForgiven() throws {
        XCTAssertEqual(try ServerAddress(rawValue: "http:/192.168.1.10:8124").displayString,
                       "http://192.168.1.10:8124")
    }

    func testIPv6LiteralKeepsItsBrackets() throws {
        let address = try ServerAddress(rawValue: "http://[::1]:8124")
        XCTAssertEqual(address.host, "::1")
        XCTAssertTrue(address.isIPv6)
        XCTAssertEqual(address.port, 8124)
        XCTAssertEqual(address.displayString, "http://[::1]:8124")
    }

    func testNormalisationIsIdempotent() throws {
        // The address is persisted and read back on every launch, so re-normalising what we
        // wrote must be a no-op — otherwise launching twice drifts the stored value.
        let inputs = [
            "rkm-hp.tail8d5e8.ts.net",
            "https://rkm-hp.tail8d5e8.ts.net/",
            "192.168.1.10:8124",
            "http://192.168.1.10:8124",
            "HTTPS://Host.Example.COM:8443",
            "10.0.0.5",
            "http://[::1]:8124",
        ]
        for input in inputs {
            let once = try ServerAddress(rawValue: input)
            let twice = try ServerAddress(rawValue: once.displayString)
            XCTAssertEqual(once, twice, "not idempotent for \(input)")
        }
    }

    // MARK: - Rejections, each with something to show the person typing

    func testEmptyIsRejected() {
        assertThrows("", .empty)
        assertThrows("   \n", .empty)
    }

    func testUnsupportedSchemeIsRejectedByName() {
        assertThrows("ftp://rkm-hp.tail8d5e8.ts.net", .unsupportedScheme("ftp"))
        assertThrows("ws://host", .unsupportedScheme("ws"))
    }

    func testHostlessIsRejected() {
        assertThrows("http://", .missingHost)
        assertThrows("https:///", .missingHost)
    }

    func testCredentialsInTheAddressAreRejected() {
        // Both a redaction hazard and unnecessary — the web UI owns sign-in.
        assertThrows("http://rajeev:hunter2@192.168.1.10:8124", .credentialsNotAllowed)
    }

    func testPathsAndQueriesAreRejectedNotSilentlyDropped() {
        XCTAssertThrowsError(try ServerAddress(rawValue: "http://host:8124/api")) { error in
            guard case .some(.notAnOrigin) = error as? ServerAddressError else {
                return XCTFail("expected notAnOrigin, got \(error)")
            }
        }
        XCTAssertThrowsError(try ServerAddress(rawValue: "http://host?x=1"))
        XCTAssertThrowsError(try ServerAddress(rawValue: "http://host#frag"))
    }

    func testPortsAreValidated() {
        assertThrows("http://host:99999", .invalidPort("99999"))
        assertThrows("http://host:0", .invalidPort("0"))
        assertThrows("http://host:abc", .invalidPort("abc"))
    }

    func testNonsenseHostsAreRejected() {
        assertThrows("http://ho st", .malformedHost("ho st"))
        assertThrows("http://.", .malformedHost("."))
        assertThrows("http://-", .malformedHost("-"))
        // Unbracketed IPv6 — say no rather than silently mangling it.
        assertThrows("http://::1", .malformedHost("::1"))
    }

    func testEveryRejectionExplainsItself() {
        // The plan's rule: a rejected address must say why (`apple/README.md`). A nil or empty
        // message would turn a typo into a dead end.
        let raws = ["", "ftp://h", "http://", "http://u:p@h", "http://h/p", "http://h:99999", "http://.", "http://::1"]
        for raw in raws {
            do {
                _ = try ServerAddress(rawValue: raw)
                XCTFail("\(raw) should have been rejected")
            } catch let error as ServerAddressError {
                let message = error.errorDescription ?? ""
                XCTAssertFalse(message.isEmpty, "no message for \(raw)")
            } catch {
                XCTFail("unexpected error type for \(raw)")
            }
        }
    }

    // MARK: - Location hints (they drive what the setup screen tells the person to check)

    func testLocalNetworkDetection() {
        for host in ["localhost", "nas.local", "192.168.1.10", "10.0.0.5", "172.16.4.1",
                     "169.254.1.1", "127.0.0.1"] {
            XCTAssertTrue(ServerAddress.isLocalHost(host), "\(host) should read as local")
        }
        for host in ["rkm-hp.tail8d5e8.ts.net", "172.32.0.1", "8.8.8.8", "media.example.com"] {
            XCTAssertFalse(ServerAddress.isLocalHost(host), "\(host) should not read as local")
        }
    }

    func testIPLiteralDetection() {
        XCTAssertTrue(ServerAddress.isIPLiteral("192.168.1.10"))
        XCTAssertTrue(ServerAddress.isIPLiteral("::1"))
        XCTAssertFalse(ServerAddress.isIPLiteral("rkm-hp"))
        XCTAssertFalse(ServerAddress.isIPLiteral("192.168.1.999"))
    }

    // MARK: - Helper

    private func assertThrows(_ raw: String,
                              _ expected: ServerAddressError,
                              file: StaticString = #filePath,
                              line: UInt = #line) {
        XCTAssertThrowsError(try ServerAddress(rawValue: raw), file: file, line: line) { error in
            XCTAssertEqual(error as? ServerAddressError, expected, file: file, line: line)
        }
    }
}
