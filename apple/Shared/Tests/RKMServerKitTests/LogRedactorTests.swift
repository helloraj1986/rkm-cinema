import XCTest
@testable import RKMServerKit

/// ⚠ The redactor's own tests are not optional: a redaction bug is a credential leak, and the
/// logs from this app get pasted into chat. `apple/LOGGING.md` §6 and §9.
final class LogRedactorTests: XCTestCase {

    // MARK: - Queries

    func testOrdinaryQueryParametersSurvive() {
        XCTAssertEqual(LogRedactor.redact(query: "mode=remux&t=12"), "mode=remux&t=12")
        XCTAssertEqual(LogRedactor.redact(query: "verbose=1"), "verbose=1")
        XCTAssertEqual(LogRedactor.redact(query: ""), "")
    }

    func testSensitiveParametersLoseBothNameAndValue() {
        // ⚠ The *name* has to go too: §9's grep is case-insensitive and would match `token`
        // even with the value hidden.
        XCTAssertEqual(LogRedactor.redact(query: "mode=remux&token=abc123&t=12"),
                       "mode=remux&cred=[redacted]&t=12")
        XCTAssertEqual(LogRedactor.redact(query: "api_key=XYZ"), "cred=[redacted]")
        XCTAssertEqual(LogRedactor.redact(query: "apikey=XYZ"), "cred=[redacted]")
        XCTAssertEqual(LogRedactor.redact(query: "password=hunter2"), "cred=[redacted]")
        XCTAssertEqual(LogRedactor.redact(query: "client_secret=shhh"), "cred=[redacted]")
        XCTAssertEqual(LogRedactor.redact(query: "limit=20&sessionId=9"), "limit=20&session=[redacted]")
        XCTAssertEqual(LogRedactor.redact(query: "flag&token=abc"), "flag&cred=[redacted]")
    }

    func testTheSessionParameterIsLabelledRatherThanDropped() {
        // It survives as a word — just not as the word the gate greps for — because "did the
        // session cookie land?" is the question the log needs to answer (`LOGGING.md` §3).
        XCTAssertEqual(LogRedactor.redact(query: "rkm_session=deadbeef"), "session=[redacted]")
    }

    // MARK: - URLs

    func testOrdinaryURLsSurviveIntact() {
        XCTAssertEqual(LogRedactor.redact(urlString: "/api/status"), "/api/status")
        XCTAssertEqual(LogRedactor.redact(urlString: "/api/library/continue-watching?limit=20"),
                       "/api/library/continue-watching?limit=20")
        XCTAssertEqual(LogRedactor.redact(urlString: "/api/jellyfin/hls/abc/master.m3u8?mode=remux&max_bitrate=4200000"),
                       "/api/jellyfin/hls/abc/master.m3u8?mode=remux&max_bitrate=4200000")
    }

    func testSensitiveURLParametersAreRedacted() {
        XCTAssertEqual(LogRedactor.redact(urlString: "https://host/api/x?mode=remux&token=abc"),
                       "https://host/api/x?mode=remux&cred=[redacted]")
    }

    func testFragmentsAreDropped() {
        // A SPA can carry state — including a token — in the fragment, and it never reaches
        // the server, so it has no diagnostic value worth the risk.
        XCTAssertEqual(LogRedactor.redact(urlString: "https://host/api/x#token=abc"),
                       "https://host/api/x")
    }

    func testPasswordInURLUserInfoIsRemovedEvenThoughTheGateWouldMissIt() {
        let redacted = LogRedactor.redact(urlString: "http://rajeev:hunter2@192.168.1.10:8124/api")
        XCTAssertFalse(redacted.contains("hunter2"))
        XCTAssertFalse(redacted.contains("rajeev"))
        XCTAssertTrue(redacted.hasSuffix("/api"))
    }

    // MARK: - Headers and cookies

    func testAuthorisationHeaderBecomesPresenceOnly() {
        let redacted = LogRedactor.redact(headers: [
            "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
        ])
        XCTAssertEqual(redacted["Authorization"], "[redacted]")
    }

    func testCookieHeaderKeepsNamesAndCountOnly() {
        // ⚠ Names, never values (`LOGGING.md` §3) — and the session cookie's own name is on the
        // gate's word list, so it is relabelled without losing the fact that it landed.
        XCTAssertEqual(LogRedactor.redact(cookieHeader: "rkm_session=deadbeef"), "1 cookie (session)")
        XCTAssertEqual(LogRedactor.redact(cookieHeader: "rkm_session=deadbeef; locale=en"),
                       "2 cookies (session, locale)")
        XCTAssertEqual(LogRedactor.redact(cookieHeader: "a=1; b=2; c=3"), "3 cookies (a, b, c)")
        XCTAssertEqual(LogRedactor.redact(cookieHeader: ""), "no cookies")
    }

    func testCookieHeaderIsNeverGivenAValue() {
        let redacted = LogRedactor.redact(headers: ["Cookie": "rkm_session=deadbeefsecret"])
        XCTAssertEqual(redacted["Cookie"], "1 cookie (session)")
        XCTAssertFalse(redacted.values.joined().contains("deadbeefsecret"))
    }

    func testHarmlessHeadersPassThrough() {
        let redacted = LogRedactor.redact(headers: ["Accept": "application/json"])
        XCTAssertEqual(redacted["Accept"], "application/json")
    }

    func testHeaderDescriptionIsOneLoggableLine() {
        let line = LogRedactor.describe(headers: [
            "Cookie": "rkm_session=deadbeef; locale=en",
            "Authorization": "Bearer abcdefghijklmnopqrst",
            "Accept": "application/json",
        ])
        XCTAssertTrue(line.contains("Accept: application/json"))
        XCTAssertTrue(line.contains("1 cookie") || line.contains("2 cookies"))
        XCTAssertEqual(LogRedactor.leaks(line), [])
    }

    // MARK: - Free text

    func testFreeTextIsSwept() {
        XCTAssertEqual(LogRedactor.leaks(
            LogRedactor.redact(text: "fetch failed for /api/x?token=abc (NSError -1004)")
        ), [])
        XCTAssertEqual(LogRedactor.leaks(
            LogRedactor.redact(text: "jellyfin api_key: 0123456789abcdef")
        ), [])
        XCTAssertEqual(LogRedactor.leaks(
            LogRedactor.redact(text: "{\"password\":\"hunter2\",\"name\":\"rajeev\"}")
        ), [])
    }

    func testJSONKeepsItsShapeAndItsHarmlessFields() {
        let redacted = LogRedactor.redact(text: "{\"password\":\"hunter2\",\"name\":\"rajeev\"}")
        XCTAssertTrue(redacted.contains("rajeev"), "a harmless field must survive")
        XCTAssertFalse(redacted.contains("hunter2"))
    }

    func testBearerTokensInFreeTextAreRemoved() {
        let redacted = LogRedactor.redact(text: "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9")
        XCTAssertTrue(redacted.contains("Bearer"))
        XCTAssertFalse(redacted.contains("eyJhbGciOiJIUzI1NiJ9"))
    }

    func testOrdinaryProseIsNotMangledIntoNonsense() {
        // ⚠ The counterweight to over-redaction: a rule that eats ordinary words makes the log
        // unreadable, which is its own kind of failure.
        let sentence = "the basic settings are correct and playback resumed"
        XCTAssertEqual(LogRedactor.redact(text: sentence), sentence)
    }

    // MARK: - Correlation ids must survive (they are the whole point)

    func testCorrelationIDsAreNotMistakenForCredentials() {
        // ⚠ A hex sweep would have destroyed these, which is exactly why there is no generic
        // hex rule in the redactor.
        let line = "[7f3a2c] net      GET /api/status -> 200 in 84ms (1.2 KB)"
        XCTAssertEqual(LogRedactor.redact(text: line), line)
    }

    // MARK: - The gate itself

    func testGrepWordsAreDetectedWhenPresent() {
        XCTAssertEqual(LogRedactor.leaks("password=1"), ["password"])
        XCTAssertEqual(LogRedactor.leaks("aToKeN"), ["token"])
        XCTAssertEqual(LogRedactor.leaks("rkm_session"), ["rkm_session"])
        XCTAssertEqual(LogRedactor.leaks("api_key"), ["api_key"])
        XCTAssertEqual(LogRedactor.leaks("nothing to see"), [])
    }

    /// ⚠ The property that makes the §9 gate hold: **no** input, through **any** entry point,
    /// comes out still containing a word the acceptance `grep` looks for.
    func testEveryEntryPointIsLeakFreeOverANastyCorpus() {
        let corpus = [
            "password=hunter2",
            "password: hunter2",
            "\"password\": \"hunter2\"",
            "?token=eyJhbGciOiJIUzI1NiJ9",
            "&access_token=abc",
            "api_key=0123456789abcdef",
            "apikey=0123456789abcdef",
            "api-key=0123456789abcdef",
            "rkm_session=deadbeef",
            "sessionId=12345",
            "Cookie: rkm_session=deadbeef",
            "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9",
            "Authorization: Basic cmFqZWV2Omh1bnRlcjI=",
            "https://host/api/x?token=abc&limit=5",
            "http://rajeev:hunter2@host/api",
            "client_secret=shhh",
            "X-Emby-Token: abcdef0123456789",
            "PASSWORD = HUNTER2",
            "{\"password\":\"hunter2\",\"api_key\":\"k\"}",
            "Failed to refresh the aToKeN",
            "the api_key is missing",
            "mode=remux&TOKEN=abc",
            "/api/x?RKM_SESSION=1",
        ]
        for input in corpus {
            XCTAssertEqual(LogRedactor.leaks(LogRedactor.redact(text: input)), [],
                           "redact(text:) leaked for: \(input)")
            XCTAssertEqual(LogRedactor.leaks(LogRedactor.redact(urlString: input)), [],
                           "redact(urlString:) leaked for: \(input)")
            XCTAssertEqual(LogRedactor.leaks(LogRedactor.redact(query: input)), [],
                           "redact(query:) leaked for: \(input)")
            XCTAssertEqual(LogRedactor.leaks(LogRedactor.redact(cookieHeader: input)), [],
                           "redact(cookieHeader:) leaked for: \(input)")
        }
    }

    func testRedactionIsIdempotent() {
        // A line can pass through the sweep more than once (a URL inside a message that is then
        // swept again), so running it twice must not keep changing the text.
        for input in ["token=abc", "\"password\": \"x\"", "Cookie: rkm_session=1", "/api/x?mode=remux"] {
            let once = LogRedactor.redact(text: input)
            XCTAssertEqual(LogRedactor.redact(text: once), once, "not idempotent for \(input)")
        }
    }

    func testSensitiveKeyRecognition() {
        for key in ["password", "passwd", "pwd", "passphrase", "token", "access_token",
                    "api_key", "apiKey", "api-key", "apikey", "secret", "client_secret",
                    "session", "sessionId", "rkm_session", "auth", "authorization",
                    "credential", "signature", "key", "sid", "sig"] {
            XCTAssertTrue(LogRedactor.isSensitive(key: key), "\(key) should be sensitive")
        }
        for key in ["mode", "limit", "id", "t", "verbose", "quality", "start"] {
            XCTAssertFalse(LogRedactor.isSensitive(key: key), "\(key) should not be sensitive")
        }
    }
}
