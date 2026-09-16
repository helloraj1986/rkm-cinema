import Foundation

// Phase B3's third pure piece: **the Range test suite itself**, shared by both worlds.
//
// `docs/NATIVE_FEEL_AND_OFFLINE_PLAN.md` §6 states B3's gate as: *the loopback server passes a Range test
// suite; the page round-trips a command and a progress event*. A "test suite" that exists only on the Mac
// is one that can only be judged by a handover round, and a suite written twice (once for Linux, once for
// the app) is two suites that will disagree the first time either changes. So the cases live HERE, as data:
//
//   * `apple/scripts/check-offline-core.py` drives them through the PURE planner on Linux — every status,
//     every `Content-Range`, every byte count, and a round-trip of the response head back through the
//     parser the client side uses;
//   * the app's own DEBUG probe (`Debug/OfflineServerProbe.swift`) sends **the same composed heads** over
//     a real loopback socket, and additionally checks that the bytes returned really are the file's bytes
//     at the offset it asked for.
//
// ⚠ The head is composed in ONE place (`OfflineProbeCase.headBytes`) for the same reason: if the Mac sent a
// request the Linux gate never saw, the two would be testing different servers.

// MARK: - Where a case points

enum OfflineProbeTarget: Equatable {
    /// `/offline/<token>.<ext>` — the real thing.
    case valid
    /// A well-formed handle that was never minted. ⚠ Must be 404, and must never fall back to another title.
    case otherToken
    /// The real handle, upper-cased. ⚠ Refused: one canonical spelling, so equality can never be accidental.
    case uppercaseToken
    /// `../../etc/passwd`, sent raw so no client library can normalise it away first.
    case traversal
    /// A proxy-style absolute-form target: `GET http://host/path HTTP/1.1`.
    case absoluteForm

    static let unknownToken = "deadbeefdeadbeefdeadbeefdeadbeef"

    func rawTarget(token: String, fileExtension: String) -> String {
        switch self {
        case .valid: return "/offline/\(token).\(fileExtension)"
        case .otherToken: return "/offline/\(Self.unknownToken).\(fileExtension)"
        case .uppercaseToken: return "/offline/\(token.uppercased()).\(fileExtension)"
        case .traversal: return "/offline/../../etc/passwd"
        case .absoluteForm: return "http://127.0.0.1/offline/\(token).\(fileExtension)"
        }
    }
}

// MARK: - A case

struct OfflineProbeCase: Equatable {
    var id: String
    var method: String
    var target: OfflineProbeTarget
    /// Sent as the `Range` header. `nil` means the header is absent entirely (not empty — absent).
    var range: String?
    /// Raw header lines appended verbatim — the only way to send a DUPLICATED `Range`, which no client
    /// library will do for us and which the server must refuse rather than resolve.
    var extraHeaderLines: [String]
    var expectStatus: Int
    /// `nil` = the header must be ABSENT.
    var expectContentLength: Int64?
    /// `nil` = the header must be ABSENT.
    var expectContentRange: String?
    var expectBodyBytes: Int64
    /// ⚠ The one a length check cannot catch: are these the RIGHT bytes for that offset?
    var expectBytesFromFile: Bool
    /// Also run this case through `URLSession`, the real HTTP stack WebKit sits on top of.
    var mirrorWithURLSession: Bool
    var note: String

    /// The exact request head, as it goes on the wire. ⚠ One composition, both worlds.
    func headBytes(token: String, fileExtension: String, host: String) -> Data {
        var lines = ["\(method) \(target.rawTarget(token: token, fileExtension: fileExtension)) HTTP/1.1"]
        lines.append("Host: \(host)")
        if let range { lines.append("Range: \(range)") }
        lines.append(contentsOf: extraHeaderLines)
        lines.append("Connection: close")
        return Data((lines.joined(separator: "\r\n") + "\r\n\r\n").utf8)
    }
}

enum OfflineProbeCases {

    /// The suffix case asks for this many trailing bytes.
    static let suffixBytes: Int64 = 4096
    /// The head-chunk case asks for this many bytes from zero.
    static let chunkBytes: Int64 = 65536

    /// ⚠ Derived from the size, so the SAME cases run against the probe's 1 MiB synthetic artefact on the
    /// Mac and against whatever size the Linux harness chooses. A suite with a baked-in size would pass on
    /// one file and be meaningless on another.
    static func cases(size: Int64) -> [OfflineProbeCase] {
        let last = size - 1
        let half = size / 2
        let chunk = min(chunkBytes, size)
        let suffix = min(suffixBytes, size)

        return [
            OfflineProbeCase(
                id: "head-no-range", method: "HEAD", target: .valid, range: nil, extraHeaderLines: [],
                expectStatus: 200, expectContentLength: size, expectContentRange: nil,
                expectBodyBytes: 0, expectBytesFromFile: false, mirrorWithURLSession: true,
                note: "a HEAD must tell the truth about a body it will not send"),

            OfflineProbeCase(
                id: "get-whole", method: "GET", target: .valid, range: nil, extraHeaderLines: [],
                expectStatus: 200, expectContentLength: size, expectContentRange: nil,
                expectBodyBytes: size, expectBytesFromFile: true, mirrorWithURLSession: false,
                note: "no Range at all → the whole file, 200, and every byte in order"),

            OfflineProbeCase(
                id: "get-open-range", method: "GET", target: .valid, range: "bytes=0-", extraHeaderLines: [],
                expectStatus: 206, expectContentLength: size, expectContentRange: "bytes 0-\(last)/\(size)",
                expectBodyBytes: size, expectBytesFromFile: true, mirrorWithURLSession: true,
                note: "'bytes=0-' is what a player sends first: open-ended, so end = size-1"),

            OfflineProbeCase(
                id: "get-head-chunk", method: "GET", target: .valid, range: "bytes=0-\(chunk - 1)",
                extraHeaderLines: [],
                expectStatus: 206, expectContentLength: chunk,
                expectContentRange: "bytes 0-\(chunk - 1)/\(size)",
                expectBodyBytes: chunk, expectBytesFromFile: true, mirrorWithURLSession: false,
                note: "the header-probe a player does before it has any metadata"),

            OfflineProbeCase(
                id: "get-mid-open", method: "GET", target: .valid, range: "bytes=\(half)-",
                extraHeaderLines: [],
                expectStatus: 206, expectContentLength: size - half,
                expectContentRange: "bytes \(half)-\(last)/\(size)",
                expectBodyBytes: size - half, expectBytesFromFile: true, mirrorWithURLSession: true,
                note: "⚠ THE SEEK: a non-zero offset with no end — an off-by-one here is a film that plays "
                    + "and is wrong from that point on"),

            OfflineProbeCase(
                id: "get-last-byte", method: "GET", target: .valid, range: "bytes=\(last)-",
                extraHeaderLines: [],
                expectStatus: 206, expectContentLength: 1, expectContentRange: "bytes \(last)-\(last)/\(size)",
                expectBodyBytes: 1, expectBytesFromFile: true, mirrorWithURLSession: false,
                note: "the boundary itself — the last valid offset, one byte"),

            OfflineProbeCase(
                id: "get-clamped-end", method: "GET", target: .valid,
                range: "bytes=\(size - 10)-\(size + 4096)", extraHeaderLines: [],
                expectStatus: 206, expectContentLength: 10,
                expectContentRange: "bytes \(size - 10)-\(last)/\(size)",
                expectBodyBytes: 10, expectBytesFromFile: true, mirrorWithURLSession: false,
                note: "⚠ a last-byte-pos past the end is CLAMPED, because the start names a real byte"),

            OfflineProbeCase(
                id: "get-past-end", method: "GET", target: .valid, range: "bytes=\(size)-",
                extraHeaderLines: [],
                expectStatus: 416, expectContentLength: 0, expectContentRange: "bytes */\(size)",
                expectBodyBytes: 0, expectBytesFromFile: false, mirrorWithURLSession: true,
                note: "⚠ an offset at the end is 416 and never a clamp: there is nothing there to send"),

            OfflineProbeCase(
                id: "head-with-range", method: "HEAD", target: .valid, range: "bytes=0-\(chunk - 1)",
                extraHeaderLines: [],
                expectStatus: 206, expectContentLength: chunk,
                expectContentRange: "bytes 0-\(chunk - 1)/\(size)",
                expectBodyBytes: 0, expectBytesFromFile: false, mirrorWithURLSession: false,
                note: "⚠ the case a lying HEAD fails: 206 with Content-Length \(chunk) and NO body"),

            OfflineProbeCase(
                id: "get-suffix", method: "GET", target: .valid, range: "bytes=-\(suffix)",
                extraHeaderLines: [],
                expectStatus: 206, expectContentLength: suffix,
                expectContentRange: "bytes \(size - suffix)-\(last)/\(size)",
                expectBodyBytes: suffix, expectBytesFromFile: true, mirrorWithURLSession: false,
                note: "'bytes=-N' means the LAST N bytes, not the first"),

            OfflineProbeCase(
                // ⚠⚠ THE ID MUST NOT CONTAIN THE WORD `token`. `LogRedactor`'s safety sweep is the last line
                // of defence for `LOGGING.md` §9's `token` grep, so it rewrites that word inside ANY log
                // message — which turned this case and the next one into two lines both reading
                // `offline probe case cred PASS`, i.e. the gate could not say WHICH case had failed. ⚠ The
                // wording gave way, not the sweep (an over-applied sweep costs a word; a missed one costs the
                // account). Found on the Mac 2026-09-16, from `--grep`.
                id: "get-unknown-handle", method: "GET", target: .otherToken, range: nil, extraHeaderLines: [],
                expectStatus: 404, expectContentLength: 0, expectContentRange: nil,
                expectBodyBytes: 0, expectBytesFromFile: false, mirrorWithURLSession: false,
                note: "a well-formed token nobody minted must NOT fall back to another title"),

            OfflineProbeCase(
                id: "post-method", method: "POST", target: .valid, range: nil, extraHeaderLines: [],
                expectStatus: 405, expectContentLength: 0, expectContentRange: nil,
                expectBodyBytes: 0, expectBytesFromFile: false, mirrorWithURLSession: false,
                note: "405 with Allow — the path is fine, the verb is not"),

            OfflineProbeCase(
                id: "get-uppercase-handle", method: "GET", target: .uppercaseToken, range: nil,
                extraHeaderLines: [],
                expectStatus: 400, expectContentLength: 0, expectContentRange: nil,
                expectBodyBytes: 0, expectBytesFromFile: false, mirrorWithURLSession: false,
                note: "one canonical spelling per token, or equality can be wrong by accident"),

            OfflineProbeCase(
                id: "get-traversal", method: "GET", target: .traversal, range: nil, extraHeaderLines: [],
                expectStatus: 400, expectContentLength: 0, expectContentRange: nil,
                expectBodyBytes: 0, expectBytesFromFile: false, mirrorWithURLSession: false,
                note: "sent RAW so no client library can normalise it away first"),

            OfflineProbeCase(
                id: "get-absolute-form", method: "GET", target: .absoluteForm, range: nil, extraHeaderLines: [],
                expectStatus: 400, expectContentLength: 0, expectContentRange: nil,
                expectBodyBytes: 0, expectBytesFromFile: false, mirrorWithURLSession: false,
                note: "a proxy-style request has no business on a loopback server"),

            OfflineProbeCase(
                id: "get-duplicate-range", method: "GET", target: .valid, range: "bytes=0-16",
                extraHeaderLines: ["Range: bytes=32-48"],
                expectStatus: 400, expectContentLength: 0, expectContentRange: nil,
                expectBodyBytes: 0, expectBytesFromFile: false, mirrorWithURLSession: false,
                note: "two Range headers are ambiguous — refused rather than resolved"),
        ]
    }
}

// MARK: - Reading a response head (the client side of the same contract)

enum OfflineWireHeadRead: Equatable {
    case needMore
    case head(OfflineWireHead)
}

struct OfflineWireHead: Equatable {
    var status: Int
    var reason: String
    var headers: [String: String]
    /// The bytes after the terminating CRLFCRLF — the start of the body, if any.
    var body: Data

    func header(_ name: String) -> String? { headers[name.lowercased()] }

    var contentLength: Int64? { header("content-length").flatMap { Int64($0) } }
}

/// ⚠ The SAME parse runs on both sides of the wire: on the Mac over the socket, and on Linux against the
/// head bytes the pure planner produced. That round-trip is a real check — it is the one that proves the
/// sender's bytes and the reader's expectations are the same document.
enum OfflineProbeWire {

    static let headTerminator = Data("\r\n\r\n".utf8)

    static func parseHead(_ data: Data) -> OfflineWireHeadRead {
        guard let separator = data.range(of: headTerminator) else { return .needMore }
        let head = data[data.startIndex..<separator.lowerBound]
        guard let text = String(data: head, encoding: .utf8) else { return .needMore }

        let lines = text.components(separatedBy: "\r\n")
        guard let statusLine = lines.first else { return .needMore }
        let parts = statusLine.components(separatedBy: " ")
        guard parts.count >= 2, parts[0].hasPrefix("HTTP/1."), let status = Int(parts[1]) else {
            return .needMore
        }

        var headers: [String: String] = [:]
        for line in lines.dropFirst() {
            guard let colon = line.firstIndex(of: ":") else { continue }
            let name = String(line[line.startIndex..<colon]).trimmingCharacters(in: .whitespaces).lowercased()
            let value = String(line[line.index(after: colon)...]).trimmingCharacters(in: .whitespaces)
            if headers[name] == nil { headers[name] = value }
        }

        let body = Data(data[separator.upperBound...])
        return .head(OfflineWireHead(status: status,
                                     reason: parts.dropFirst().joined(separator: " "),
                                     headers: headers,
                                     body: body))
    }
}

// MARK: - A deterministic file, so a byte comparison means something

enum OfflineProbeBytes {

    /// ⚠ Deterministic and easily distinguished from zero: byte *i* is `(i * 31 + 7) mod 251`. A file of
    /// zeroes would let "the wrong offset" pass every check, and 251 is prime so the pattern does not
    /// repeat in a way that makes two offsets look alike.
    static func byte(at offset: Int64) -> UInt8 {
        UInt8((Int(offset) * 31 + 7) % 251)
    }

    static func data(count: Int64, startingAt offset: Int64 = 0) -> Data {
        var bytes = [UInt8](repeating: 0, count: Int(max(0, count)))
        for index in 0..<bytes.count {
            bytes[index] = byte(at: offset + Int64(index))
        }
        return Data(bytes)
    }
}
