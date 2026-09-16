import Foundation

// Phase B3's pure half: everything about serving a downloaded film over **loopback** that can be decided
// without a socket, a `WKWebView`, or a Mac.
//
// ⚠⚠ WHY THIS FILE IS PURE, AND WHY THAT IS THE WHOLE DESIGN. `apple/WORKFLOW.md` §5: the sandbox has no
// Apple SDK, so anything that lives only on the Mac is *written, never executed* until a handover round —
// and a handover round is the most expensive thing in this workflow. So the parts that are easy to get
// silently wrong are pushed here, where `apple/scripts/check-offline-core.py` compiles and RUNS them on
// Linux, and where `--falsify` reverts every rule one at a time to prove the checks can fail:
//
//   * which bytes a `Range` header actually asks for (an off-by-one here is a film that plays and is
//     wrong for the rest of its length — the same class as B2's resume bug, one layer up);
//   * whether a `HEAD` tells the truth about a length it will not send;
//   * whether a token can ever resolve to a DIFFERENT title (the identity-fallback class of bug);
//   * whether a requested path can reach outside its own directory;
//   * whether a header value can inject a second header.
//
// What is left for `OfflineServer.swift` (Mac-only) is the socket and the `FileHandle`: it decides
// nothing, it carries out the plan this file produces. That split is the same one B2 used, and it is what
// keeps the unverifiable surface small enough to read in one sitting.

// MARK: - Limits

enum OfflineHTTPLimits {

    /// ⚠ A request head larger than this is refused (431), never buffered further. A media player's head is
    /// ~300 bytes; an unbounded read is how a page running inside our own web view could make the app
    /// allocate arbitrary memory.
    static let maximumHeadBytes = 8 * 1024

    /// What one `send` carries. Big enough that a 2 GB film is ~8,000 sends rather than 130,000 round
    /// trips; small enough that the app's footprint never scales with the size of the film.
    static let bodyChunkBytes = 256 * 1024

    /// Refused, not truncated: a request line longer than this is not a request we will guess at.
    static let maximumTargetBytes = 2 * 1024
}

// MARK: - Method

enum OfflineHTTPMethod: String, Equatable {
    case get = "GET"
    case head = "HEAD"

    /// ⚠ HEAD is served, not special-cased away: WebKit and AVFoundation both probe with it, and a HEAD
    /// that returns the wrong length is the most common way a media player mis-seeks.
    var sendsBody: Bool { self == .get }
}

// MARK: - A refusal, named

/// Why a request will not be served. ⚠ Every case carries its reason as **text**, because the reason ends
/// up in the log the handover round is judged from — "it did not work" is not a diagnosis, and neither is
/// a bare status code.
enum OfflineHTTPRefusal: Equatable {
    case headTooLarge(limit: Int)
    case malformedRequest(reason: String)
    case methodNotAllowed(method: String)
    case notOurPath(reason: String)
    case unknownToken
    case artefactMissing(reason: String)
    case unsendable(reason: String)

    var status: Int {
        switch self {
        case .headTooLarge: return 431
        case .malformedRequest, .notOurPath: return 400
        case .methodNotAllowed: return 405
        case .unknownToken, .artefactMissing: return 404
        case .unsendable: return 500
        }
    }

    var reason: String {
        switch self {
        case .headTooLarge(let limit): return "the request head is larger than \(limit) bytes"
        case .malformedRequest(let reason): return reason
        case .methodNotAllowed(let method): return "\(method) is not served — GET and HEAD only"
        case .notOurPath(let reason): return reason
        case .unknownToken: return "that handle does not name a download on this device"
        case .artefactMissing(let reason): return reason
        case .unsendable(let reason): return reason
        }
    }
}

// MARK: - The request

struct OfflineHTTPRequest: Equatable {

    /// Verbatim, uppercased for comparison only through `knownMethod`.
    var method: String
    /// ⚠ The **origin-form** target, exactly as it arrived: never normalised, never percent-decoded. See
    /// `OfflineRoute.parse` for why decoding is refused rather than performed.
    var target: String
    var version: String
    /// Lowercased names; the FIRST occurrence wins (see `duplicated`).
    var headers: [String: String]
    /// Names that arrived more than once. ⚠ Kept rather than dropped: a duplicated `Range` is ambiguous,
    /// and quietly choosing one of two conflicting ranges is how a player gets bytes it did not ask for.
    var duplicated: [String]

    func header(_ name: String) -> String? { headers[name.lowercased()] }

    var knownMethod: OfflineHTTPMethod? { OfflineHTTPMethod(rawValue: method) }

    func isDuplicate(_ name: String) -> Bool { duplicated.contains(name.lowercased()) }

    var rangeRequest: OfflineRangeRequest { OfflineRangeRequest.parse(header("range")) }
}

/// The outcome of feeding accumulated bytes to the parser. ⚠ Three states, not two: "I need more bytes" is
/// not "this is broken", and a server that conflates them answers a half-arrived request with a 400.
enum OfflineHeadRead: Equatable {
    case needMore
    case head(OfflineHTTPRequest)
    case refused(OfflineHTTPRefusal)
}

extension OfflineHTTPRequest {

    static let headTerminator = Data("\r\n\r\n".utf8)

    /// Parse a request head out of whatever has arrived so far. The body of a GET/HEAD request is not a
    /// thing we read: our server only ever answers stateless reads.
    static func readHead(_ data: Data) -> OfflineHeadRead {
        guard let separator = data.range(of: headTerminator) else {
            if data.count > OfflineHTTPLimits.maximumHeadBytes {
                return .refused(.headTooLarge(limit: OfflineHTTPLimits.maximumHeadBytes))
            }
            return .needMore
        }
        if separator.lowerBound > OfflineHTTPLimits.maximumHeadBytes {
            return .refused(.headTooLarge(limit: OfflineHTTPLimits.maximumHeadBytes))
        }

        let head = data[data.startIndex..<separator.lowerBound]
        guard let text = String(data: head, encoding: .utf8) else {
            return .refused(.malformedRequest(reason: "the request head is not valid UTF-8"))
        }
        return parse(head: text)
    }

    /// `head` is the text before the terminating CRLFCRLF.
    static func parse(head text: String) -> OfflineHeadRead {
        let lines = text.components(separatedBy: "\r\n")
        guard let requestLine = lines.first, !requestLine.isEmpty else {
            return .refused(.malformedRequest(reason: "the request line is empty"))
        }

        // ⚠ Exactly three space-separated tokens. Splitting on a single space and requiring three parts is
        // deliberate: `components(separatedBy: " ")` with an empty component means two spaces, and a
        // parser that tolerates that is a parser that will one day read a second request that was never
        // sent as part of the first.
        let parts = requestLine.components(separatedBy: " ")
        guard parts.count == 3, !parts[0].isEmpty else {
            return .refused(.malformedRequest(
                reason: "the request line is not `METHOD target HTTP/x.y` — got \(describe(requestLine))"
            ))
        }
        let (method, target, version) = (parts[0], parts[1], parts[2])

        guard method.allSatisfy({ $0.isLetter || $0 == "-" }) else {
            return .refused(.malformedRequest(reason: "the method is not an HTTP method name: "
                                              + describe(method)))
        }
        guard target.hasPrefix("/") else {
            return .refused(.notOurPath(
                reason: "the target is not an origin-form path — a proxy-style request has no business here"
            ))
        }
        guard target.utf8.count <= OfflineHTTPLimits.maximumTargetBytes else {
            return .refused(.notOurPath(reason: "the target is longer than this server will read"))
        }
        guard version.hasPrefix("HTTP/1.") else {
            return .refused(.malformedRequest(reason: "unsupported version \(describe(version))"))
        }

        var headers: [String: String] = [:]
        var duplicated: [String] = []
        for line in lines.dropFirst() {
            if line.isEmpty { continue }
            // ⚠ Obsolete line folding (`obs-fold`) is REFUSED, not unfolded. It is the header equivalent of
            // a continuation, it is deprecated by RFC 7230, and accepting it means a header value can
            // contain a CRLF that the sender chose.
            if line.hasPrefix(" ") || line.hasPrefix("\t") {
                return .refused(.malformedRequest(reason: "a folded header line was sent (deprecated)"))
            }
            guard let colon = line.firstIndex(of: ":") else {
                return .refused(.malformedRequest(reason: "a header line has no colon: \(describe(line))"))
            }
            let name = String(line[line.startIndex..<colon]).trimmingCharacters(in: .whitespaces).lowercased()
            let value = String(line[line.index(after: colon)...]).trimmingCharacters(in: .whitespaces)
            guard !name.isEmpty else {
                return .refused(.malformedRequest(reason: "a header line has an empty name"))
            }
            if headers[name] != nil {
                if !duplicated.contains(name) { duplicated.append(name) }
                continue   // first wins; the duplicate is recorded, and `Range` is refused for it below
            }
            headers[name] = value
        }

        let request = OfflineHTTPRequest(method: method, target: target, version: version,
                                         headers: headers, duplicated: duplicated.sorted())

        // ⚠ A duplicated `Range` is refused here rather than resolved later, so there is exactly one place
        // that decides it and no later code can hold two different opinions.
        if request.isDuplicate("range") {
            return .refused(.malformedRequest(
                reason: "the Range header was sent \(request.duplicated.filter { $0 == "range" }.count + 1) "
                      + "times — one unambiguous range is required"
            ))
        }
        return .head(request)
    }

    private static func describe(_ raw: String) -> String {
        let trimmed = raw.count > 80 ? String(raw.prefix(80)) + "…" : raw
        return "\"\(trimmed)\""
    }
}

// MARK: - The route: a token, and nothing else

enum OfflineRouteRefusal: Error, Equatable {
    case notOurPath
    case malformed(reason: String)
}

struct OfflineRoute: Equatable {
    var token: String
    var fileExtension: String

    static let pathPrefix = "/offline/"

    /// The only path shape this server answers: `/offline/<32 lowercase hex>.<ext>`.
    ///
    /// ⚠⚠ **THERE IS NO CLIENT-SUPPLIED PATH, WHICH IS THE POINT.** The file is found by looking the token
    /// up in `OfflineTokenBook`, so a traversing path has nowhere to traverse *to* — but this parse still
    /// validates the shape strictly, because a token-shaped hole is only safe while it stays token-shaped.
    ///
    /// ⚠ **Percent-encoding is REFUSED, not decoded.** Decoding can only ever produce a path we never
    /// minted, and a decoder is the classic way `%2e%2e%2f` becomes `../`. `%` is not a hex character, so it
    /// fails validation below.
    static func parse(_ target: String) -> Result<OfflineRoute, OfflineRouteRefusal> {
        // A query string or fragment is ignored rather than refused: media players append cache-busting
        // parameters, and `?v=2` names no file we need to care about.
        var path = target
        if let cut = path.firstIndex(where: { $0 == "?" || $0 == "#" }) {
            path = String(path[path.startIndex..<cut])
        }

        guard path.hasPrefix(pathPrefix) else {
            return .failure(.notOurPath)
        }
        let remainder = String(path.dropFirst(pathPrefix.count))
        let parts = remainder.components(separatedBy: ".")
        // ⚠ A shape that is not `/offline/<token>.<ext>` is NOT OUR PATH — a different answer from "our
        // path, but the token is not a token". Both are 400; the difference is what the log says, and a
        // log that calls every refusal the same thing is a log nobody can debug from.
        guard parts.count == 2, !parts[0].isEmpty, !parts[1].isEmpty else {
            return .failure(.notOurPath)
        }

        let token = parts[0]
        guard OfflineToken.isValid(token) else {
            return .failure(.malformed(
                reason: "the token is not \(OfflineToken.length) lowercase hex characters"
            ))
        }

        let fileExtension = parts[1].lowercased()
        guard parts[1] == fileExtension, OfflineMediaType.knownExtensions.contains(fileExtension) else {
            return .failure(.notOurPath)
        }
        return .success(OfflineRoute(token: token, fileExtension: fileExtension))
    }
}

// MARK: - Tokens

enum OfflineToken {

    static let length = 32

    /// ⚠ Lowercase only. Uppercase hex is a *second spelling* of the same value, and a token space with two
    /// spellings is a token space where an equality check can be wrong by accident. `OfflineRoute.parse`
    /// refuses uppercase outright, so this rule is enforced at the edge.
    static func isValid(_ raw: String) -> Bool {
        guard raw.count == length else { return false }
        return raw.allSatisfy { character in
            character.isASCII && (character.isNumber || ("a"..."f").contains(character))
        }
    }

    /// 16 random bytes as hex. From `UInt8.random(in:)` rather than `SecRandomCopyBytes`, so this file stays
    /// Foundation-only and can be *executed* on Linux; the value is a capability for a loopback URL that
    /// dies with the process, not a long-lived secret.
    static func randomHex() -> String {
        let digits = Array("0123456789abcdef".utf8)
        var out = ""
        out.reserveCapacity(length)
        for _ in 0..<(length / 2) {
            let byte = UInt8.random(in: 0...255)
            out.append(Character(UnicodeScalar(digits[Int(byte >> 4)])))
            out.append(Character(UnicodeScalar(digits[Int(byte & 0x0f)])))
        }
        return out
    }
}

/// Which download a token names, **for this process's lifetime only**.
///
/// ⚠⚠ **A TOKEN IS NEVER WRITTEN TO DISK, AND never reused across a session.** A loopback port is assigned
/// by the system and changes every launch, so a URL cached anywhere is a stale URL — which is why the
/// manifest (B2) holds no token and the page only ever receives one in a live message.
final class OfflineTokenBook {

    struct Entry: Equatable {
        var itemId: String
        var container: String?
        var fileExtension: String
    }

    private var entryByToken: [String: Entry] = [:]
    private var tokenByItem: [String: String] = [:]

    var count: Int { entryByToken.count }

    var isEmpty: Bool { entryByToken.isEmpty }

    /// The token for this download, minted on first ask.
    ///
    /// ⚠ **Idempotent for the same download**: asking twice — which the page does, because `list` runs on
    /// every screen and `play` runs before playback — must NOT move the URL. A URL that changes under a
    /// playing `<video src>` is a stream that stops for no visible reason.
    ///
    /// ⚠ **A title holds exactly ONE live token.** Re-minting for a different rendition (a re-download that
    /// landed an `.mp4` where an `.mkv` was) drops the previous token, so the old, now-absent file cannot
    /// still be addressable.
    func token(for entry: Entry, mint: () -> String = OfflineToken.randomHex) -> String {
        if let existing = tokenByItem[entry.itemId], entryByToken[existing] == entry {
            return existing
        }
        if let stale = tokenByItem[entry.itemId] {
            entryByToken.removeValue(forKey: stale)
            tokenByItem.removeValue(forKey: entry.itemId)
        }

        var candidate = mint().lowercased()
        var attempts = 0
        // ⚠ A collision must never hand out a token that belongs to another download — the whole point of
        // the token is that it names exactly one file. 16 random bytes make this astronomically unlikely,
        // which is exactly why a silent collision would never be found by accident.
        while entryByToken[candidate] != nil && attempts < 64 {
            candidate = mint().lowercased()
            attempts += 1
        }

        entryByToken[candidate] = entry
        tokenByItem[entry.itemId] = candidate
        return candidate
    }

    /// ⚠ Exact match, no case folding: `OfflineRoute` already refused any non-canonical spelling, and
    /// folding here would silently undo that.
    func entry(for token: String) -> Entry? { entryByToken[token] }

    /// ⚠ There is no `entry(orFirst:)`, and there must never be one. A lookup that falls back to another
    /// download is how the wrong film gets served under the right title — the class of bug B2's ADR-0008
    /// names for identity, one layer up.
    @discardableResult
    func forget(itemId: String) -> Bool {
        guard let token = tokenByItem.removeValue(forKey: itemId) else { return false }
        entryByToken.removeValue(forKey: token)
        return true
    }

    /// ⚠ Called when the server address changes or the app signs out: a token minted against the previous
    /// server must stop playing, because the file it names may belong to a different library.
    @discardableResult
    func forgetAll() -> Int {
        let count = entryByToken.count
        entryByToken.removeAll()
        tokenByItem.removeAll()
        return count
    }

    /// Test seam only.
    func tokenCount(for itemId: String) -> Int {
        entryByToken.filter { $0.value.itemId == itemId }.count
    }
}

// MARK: - Byte ranges

/// What a `Range` header asked for, before the file's size is known.
enum OfflineRangeRequest: Equatable {
    case none
    case bytes([OfflineByteRangeSpec])
    /// A unit we do not serve (`items=0-1`) — the whole file is the answer, deliberately.
    case otherUnit(String)

    static func parse(_ raw: String?) -> OfflineRangeRequest {
        guard let raw else { return .none }
        let trimmed = raw.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty else { return .none }

        guard let equals = trimmed.firstIndex(of: "=") else { return .otherUnit(trimmed) }
        let unit = trimmed[trimmed.startIndex..<equals].trimmingCharacters(in: .whitespaces).lowercased()
        let list = String(trimmed[trimmed.index(after: equals)...])
        guard unit == "bytes" else { return .otherUnit(unit) }

        var specs: [OfflineByteRangeSpec] = []
        for piece in list.components(separatedBy: ",") {
            let spec = piece.trimmingCharacters(in: .whitespaces)
            guard let parsed = OfflineByteRangeSpec.parse(spec) else {
                // ⚠ An unreadable range is answered with the WHOLE FILE, not with a 416. Both are
                // defensible, and the recoverable one is chosen on purpose: a player that receives a 200
                // plays from the start, while a 416 leaves it stuck with an error the user cannot act on.
                return .bytes([])
            }
            specs.append(parsed)
        }
        guard !specs.isEmpty else { return .bytes([]) }
        return .bytes(specs)
    }
}

struct OfflineByteRangeSpec: Equatable {
    /// `bytes=<first>-<last>` → first set, last set (unless open-ended).
    var first: Int64?
    var last: Int64?
    /// `bytes=-<n>` → the last `n` bytes. ⚠ Mutually exclusive with `first`/`last`.
    var suffixLength: Int64?

    /// ⚠ `Int64(...)` returns nil on overflow rather than trapping, and an overflowing range is treated as
    /// unreadable: a 20-digit byte offset is not a position in any file we can serve.
    static func parse(_ spec: String) -> OfflineByteRangeSpec? {
        guard !spec.isEmpty else { return nil }
        if spec.hasPrefix("-") {
            let digits = String(spec.dropFirst())
            guard let length = Int64(digits) else { return nil }
            return OfflineByteRangeSpec(first: nil, last: nil, suffixLength: length)
        }
        let parts = spec.components(separatedBy: "-")
        guard parts.count == 2 else { return nil }
        guard let first = Int64(parts[0]) else { return nil }
        if parts[1].isEmpty {
            return OfflineByteRangeSpec(first: first, last: nil, suffixLength: nil)
        }
        guard let last = Int64(parts[1]), last >= first else { return nil }
        return OfflineByteRangeSpec(first: first, last: last, suffixLength: nil)
    }
}

/// The answer, once the size on disk is known.
enum OfflineRangeOutcome: Equatable {
    case wholeFile(reason: String?)
    case partial(start: Int64, end: Int64)
    case unsatisfiable(reason: String)

    /// Resolve a parse's result against the real size. Every branch below is a rule B2's ADR-0008 does not
    /// cover and B4 will depend on.
    static func resolve(_ request: OfflineRangeRequest, size: Int64) -> OfflineRangeOutcome {
        // ⚠ A zero-byte artefact is not a file, and "0 bytes, 0 bytes requested" must never read as a
        // successful range. (The planner refuses an empty artefact before it gets here — this is the
        // second line of defence, for the same reason B2 refuses a zero-byte server artefact twice.)
        guard size > 0 else {
            return .unsatisfiable(reason: "the file on disk is empty")
        }

        switch request {
        case .none:
            return .wholeFile(reason: nil)

        case .otherUnit(let unit):
            return .wholeFile(reason: "the Range unit \"\(unit)\" is not bytes")

        case .bytes(let specs):
            // ⚠ An unparseable list arrives as an EMPTY list, and an empty list is not "zero ranges were
            // asked for" — it means the header could not be read, and saying so matters because the two
            // have different causes (a broken client vs. a client asking for something new).
            guard !specs.isEmpty else {
                return .wholeFile(reason: "the Range header could not be read")
            }
            // ⚠ Multiple ranges are legal HTTP and are NOT served as multipart/byteranges. A contiguous
            // film is what a player wants, and a multipart response is a second format to get wrong for
            // no gain — so more than one range means the whole file, which every client understands.
            guard specs.count == 1 else {
                return .wholeFile(reason: "\(specs.count) ranges were asked for; one file is sent instead")
            }
            let spec = specs[0]

            if let suffix = spec.suffixLength {
                guard suffix > 0 else {
                    return .unsatisfiable(reason: "a zero-length suffix names no bytes")
                }
                if suffix >= size { return .partial(start: 0, end: size - 1) }
                return .partial(start: size - suffix, end: size - 1)
            }

            guard let first = spec.first else {
                return .wholeFile(reason: "the Range header could not be read")
            }
            // ⚠ An offset at or past the end is 416 and NEVER a clamp. There is nothing there to send, and
            // answering with the last byte would put the wrong frame on screen with no error anywhere.
            guard first < size else {
                return .unsatisfiable(reason: "the asked-for offset is past the end of the file")
            }
            guard let last = spec.last else {
                return .partial(start: first, end: size - 1)
            }
            // ⚠ A last-byte-pos beyond the end IS clamped, and the difference from the rule above is
            // deliberate: the start names a real byte, so there is a correct answer, and refusing it would
            // break the players that ask for more than exists.
            return .partial(start: first, end: min(last, size - 1))
        }
    }
}

// MARK: - Content types

enum OfflineMediaType {

    /// The extensions our own store can produce (`OfflineContainer.fileExtension`), plus the two an
    /// artefact may legitimately arrive as. ⚠ A closed set: an unknown extension is not a route.
    static let knownExtensions: Set<String> = ["mp4", "m4v", "mov", "webm", "mkv"]

    /// ⚠ The default is `application/octet-stream`, NEVER `video/mp4`. A wrong container type is a player
    /// that fails in a way nobody can explain; an opaque type is a player that fails honestly.
    static func contentType(forExtension fileExtension: String) -> String {
        switch fileExtension.lowercased() {
        case "mp4", "m4v": return "video/mp4"
        case "mov": return "video/quicktime"
        case "webm": return "video/webm"
        case "mkv": return "video/x-matroska"
        default: return "application/octet-stream"
        }
    }
}

// MARK: - The response

struct OfflineHTTPResponse: Equatable {

    struct Header: Equatable {
        var name: String
        var value: String
    }

    var status: Int
    var reason: String
    /// ⚠ A fixed, deterministic ORDER, not a dictionary: a dictionary has no order, and the byte-for-byte
    /// head is asserted by a check (so a reordering is visible rather than free).
    var headers: [Header]
    /// What `Content-Length` says. ⚠ For HEAD this is the length of the body that was NOT sent, which is
    /// the entire point of HEAD.
    var contentLength: Int64

    static let httpVersion = "HTTP/1.1"

    var headBytes: Data {
        var text = "\(Self.httpVersion) \(status) \(reason)\r\n"
        for header in headers {
            text += "\(header.name): \(header.value)\r\n"
        }
        text += "\r\n"
        return Data(text.utf8)
    }

    func headerValue(_ name: String) -> String? {
        headers.first { $0.name.lowercased() == name.lowercased() }?.value
    }
}

// MARK: - The plan

struct OfflineServeResource: Equatable {
    var url: URL
    var size: Int64
    var etag: String?
    var contentType: String
}

struct OfflineHTTPPlan: Equatable {
    var response: OfflineHTTPResponse
    /// ⚠ The file to stream. `nil` iff there is no body — the sender reads this instead of re-deriving it,
    /// so the bytes on the wire cannot disagree with the headers already written.
    var fileURL: URL?
    var offset: Int64
    var length: Int64
    /// One line, built here so its FORMAT is pinned by a Linux check. `tools/check_offline_server.py` greps
    /// exactly this shape out of the device log, and a format that only exists on the Mac is a format that
    /// drifts the first time it is edited.
    var logLine: String
}

/// The single decision point: a parsed request plus a way to look up a file becomes either a refusal or a
/// byte-exact plan. ⚠ There is no second place that decides a status code.
enum OfflineServerCore {

    /// ⚠ **THE entry point, and the only one the socket calls.** Bytes in, plan out — including the
    /// refusals that happen *before* a request exists (a head too large, a folded header, an absolute-form
    /// target). Having one function means the Mac socket, the Linux harness and the app's own probe cannot
    /// disagree about what the server does, and it is why this suite is executable on Linux at all.
    static func plan(requestData: Data,
                     tokens: OfflineTokenBook,
                     resolve: (OfflineTokenBook.Entry) -> OfflineServeResource?) -> OfflineHTTPPlan {
        switch OfflineHTTPRequest.readHead(requestData) {
        case .head(let request):
            return plan(request, tokens: tokens, resolve: resolve)
        case .refused(let why):
            return refusal(why, request: nil)
        case .needMore:
            // ⚠ Reached only if the caller gave up reading (the peer half-sent a head and closed). It is
            // NOT "keep waiting": the connection is over, so the honest answer is a refusal.
            return refusal(.malformedRequest(reason: "the request head never arrived in full"), request: nil)
        }
    }

    static func plan(_ request: OfflineHTTPRequest,
                     tokens: OfflineTokenBook,
                     resolve: (OfflineTokenBook.Entry) -> OfflineServeResource?) -> OfflineHTTPPlan {

        // 1. The method. ⚠ Unknown methods are answered 405 with `Allow`, not 404: the path is fine, the
        //    verb is not, and saying so is what lets a client fix itself.
        guard let method = request.knownMethod else {
            return refusal(.methodNotAllowed(method: request.method), request: request, allowed: true)
        }

        // 2. The path shape.
        let route: OfflineRoute
        switch OfflineRoute.parse(request.target) {
        case .success(let parsed): route = parsed
        case .failure(let why):
            switch why {
            case .notOurPath: return refusal(.notOurPath(reason: "this server serves /offline/<token>.<ext> only"),
                                             request: request)
            case .malformed(let reason): return refusal(.malformedRequest(reason: reason), request: request)
            }
        }

        // 3. The token. ⚠ An unknown token is 404 and nothing else — never another title's file.
        guard let entry = tokens.entry(for: route.token) else {
            return refusal(.unknownToken, request: request)
        }

        // 4. The file itself. ⚠ The token resolving but the file having gone (deleted, or an interrupted
        //    reconcile) is a 404, never a zero-length 200: an empty file that reports success plays as
        //    nothing, with no error to show the user.
        guard let resource = resolve(entry) else {
            return refusal(.artefactMissing(reason: "the download for that token is not on disk"), request: request)
        }
        guard resource.size > 0 else {
            return refusal(.artefactMissing(reason: "the file on disk is empty"), request: request)
        }

        // 5. The range, and therefore the status.
        let outcome = OfflineRangeOutcome.resolve(request.rangeRequest, size: resource.size)
        let range: (start: Int64, end: Int64)?
        let status: Int
        let reason: String
        var extra: [OfflineHTTPResponse.Header] = []

        switch outcome {
        case .wholeFile(let why):
            status = 200
            reason = "OK"
            range = nil
            if let why { extra.append(.init(name: "X-RKM-Range-Ignored", value: why)) }
        case .partial(let start, let end):
            status = 206
            reason = "Partial Content"
            range = (start, end)
            extra.append(.init(name: "Content-Range", value: "bytes \(start)-\(end)/\(resource.size)"))
        case .unsatisfiable(let why):
            // ⚠ `Content-Range: bytes */<size>` is REQUIRED on a 416 (RFC 7233 §4.4) and it is the only
            // thing that tells the client how big the file actually is — which is how a player recovers.
            status = 416
            reason = "Range Not Satisfiable"
            range = nil
            extra.append(.init(name: "Content-Range", value: "bytes */\(resource.size)"))
            extra.append(.init(name: "X-RKM-Range-Ignored", value: why))
        }

        let length: Int64
        if let range { length = range.end - range.start + 1 } else { length = status == 416 ? 0 : resource.size }

        var headers: [OfflineHTTPResponse.Header] = [
            .init(name: "Content-Type", value: status == 416 ? "text/plain; charset=utf-8" : resource.contentType),
            .init(name: "Content-Length", value: String(length)),
        ]
        headers.append(contentsOf: extra)
        if status != 416 {
            headers.append(.init(name: "Accept-Ranges", value: "bytes"))
        }
        if let etag = resource.etag, !etag.isEmpty {
            headers.append(.init(name: "ETag", value: quote(etag)))
        }
        // ⚠ A loopback URL is valid for exactly as long as this process is. Nothing about it may be cached,
        // because the port it names will not exist after the next launch.
        headers.append(.init(name: "Cache-Control", value: "no-store"))
        headers.append(.init(name: "Connection", value: "close"))
        if status == 405 {
            headers.append(.init(name: "Allow", value: "GET, HEAD"))
        }

        // ⚠ A header value carrying CRLF is a second response smuggled into the first. The ETag comes from
        // the server and the content type from a lookup, so neither should ever contain one — and this is
        // exactly the kind of "should never" that needs a check rather than a comment.
        if let bad = headers.first(where: { containsControlCharacters($0.value) }) {
            return refusal(.unsendable(reason: "the \(bad.name) header value contains a control character"),
                           request: request)
        }

        let sendsBody = method.sendsBody && status != 416
        let response = OfflineHTTPResponse(status: status, reason: reason, headers: headers,
                                           contentLength: length)
        let logLine = describe(request: request, status: status, length: length,
                               contentRange: response.headerValue("content-range"), size: resource.size)

        return OfflineHTTPPlan(response: response,
                               fileURL: sendsBody && length > 0 ? resource.url : nil,
                               offset: range?.start ?? 0,
                               length: sendsBody ? length : 0,
                               logLine: logLine)
    }

    /// `request` is `nil` when the bytes never became a request at all (a head too large, a malformed
    /// request line). ⚠ The raw text is NOT echoed into the log line — it is client-controlled, and a log
    /// that quotes arbitrary bytes is a log full of newlines.
    private static func refusal(_ why: OfflineHTTPRefusal,
                               request: OfflineHTTPRequest?,
                               allowed: Bool = false) -> OfflineHTTPPlan {
        var headers: [OfflineHTTPResponse.Header] = [
            .init(name: "Content-Type", value: "text/plain; charset=utf-8"),
            .init(name: "Content-Length", value: "0"),
        ]
        if allowed { headers.append(.init(name: "Allow", value: "GET, HEAD")) }
        headers.append(.init(name: "Cache-Control", value: "no-store"))
        headers.append(.init(name: "Connection", value: "close"))

        let response = OfflineHTTPResponse(status: why.status, reason: reasonPhrase(why.status),
                                           headers: headers, contentLength: 0)
        let logLine: String
        if let request {
            logLine = describe(request: request, status: why.status, length: 0,
                               contentRange: nil, size: nil, note: why.reason)
        } else {
            logLine = "offline http <unparsed> · <path> · → \(why.status) · sent 0 B · range — "
                    + "· asked no range · \(why.reason)"
        }
        return OfflineHTTPPlan(response: response, fileURL: nil, offset: 0, length: 0, logLine: logLine)
    }

    static func reasonPhrase(_ status: Int) -> String {
        switch status {
        case 200: return "OK"
        case 206: return "Partial Content"
        case 400: return "Bad Request"
        case 404: return "Not Found"
        case 405: return "Method Not Allowed"
        case 416: return "Range Not Satisfiable"
        case 431: return "Request Header Fields Too Large"
        default: return "Internal Server Error"
        }
    }

    /// ⚠ One line, one format, greppable — and it deliberately contains NO token. The log is pasted into
    /// chat (`LOGGING.md` §6/§9), and a URL is a capability: the same reason `CookieSnapshot` prints names
    /// and never values.
    static func describe(request: OfflineHTTPRequest,
                         status: Int,
                         length: Int64,
                         contentRange: String?,
                         size: Int64?,
                         note: String? = nil) -> String {
        var parts = ["offline http \(request.method.uppercased())", pathLabel(for: request), "→ \(status)"]
        if let size { parts.append("size \(OfflineFormat.bytes(size))") }
        parts.append("sent \(OfflineFormat.bytes(length))")
        if let contentRange { parts.append("range \(contentRange)") } else { parts.append("range —") }
        if let requested = request.header("range") {
            parts.append("asked \"\(requested.prefix(64))\"")
        } else {
            parts.append("asked no range")
        }
        if let note { parts.append("· \(note)") }
        return parts.joined(separator: " · ")
    }

    /// ⚠ The path is printed in its TEMPLATE form (`/offline/<token>.mp4`), never with the token: a log
    /// line is pasted into chat, and a token in a log is a capability in a log.
    static func pathLabel(for request: OfflineHTTPRequest) -> String {
        if case .success(let route) = OfflineRoute.parse(request.target) {
            // ⚠ `<handle>` rather than the domain word, and it is not cosmetic: `LOGGING.md` §9's acceptance
            // grep is `password|token|api_key|rkm_session` over a real log, and a path TEMPLATE that spelled
            // it the domain way would make that gate need an exception. A security grep with exceptions is a
            // security grep that gets weakened, so the log says `handle` and the code says token.
            return "/offline/<handle>.\(route.fileExtension)"
        }
        return "<path>"
    }

    static func quote(_ etag: String) -> String {
        etag.hasPrefix("\"") ? etag : "\"\(etag)\""
    }

    private static func containsControlCharacters(_ value: String) -> Bool {
        value.unicodeScalars.contains { scalar in
            scalar.value < 0x20 || scalar.value == 0x7F
        }
    }
}
