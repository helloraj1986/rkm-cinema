import Foundation

// ⚠ FOUNDATION ONLY — see the header of `OfflineManifest.swift`. What is tested here is the *rule*
// about which cookies may be attached to which request; reading them out of WebKit is `CookieMirror`'s
// job and building the request is `OfflineAPI`'s, and neither decision lives in this file.

/// One cookie, as a value this file may reason about.
///
/// ⚠ The split exists so that the **value** is carried but never *usable by accident*: `CookieHeader`
/// has exactly one output that contains values (the header itself), its summary function takes names,
/// and nothing here has a `description` that prints a value. `LOGGING.md` §6 makes
/// `grep -iE "password|token|api_key|rkm_session"` over a real run's log an acceptance gate, and the
/// session cookie is `rkm_session` — a struct that prints its own value would break that gate the first
/// time someone logged a cookie.
struct CookieSnapshot: Equatable {
    var name: String
    var value: String
    /// As WebKit reports it: the host, or `.example.com` for a domain cookie.
    var domain: String
    var path: String
    /// `nil` = a session cookie (no `Expires`/`Max-Age`), which is what our server sets.
    var expiresAt: Date?
    var isSecure: Bool
    var isHTTPOnly: Bool

    init(
        name: String,
        value: String,
        domain: String,
        path: String = "/",
        expiresAt: Date? = nil,
        isSecure: Bool = false,
        isHTTPOnly: Bool = false
    ) {
        self.name = name
        self.value = value
        self.domain = domain
        self.path = path
        self.expiresAt = expiresAt
        self.isSecure = isSecure
        self.isHTTPOnly = isHTTPOnly
    }

    /// ⚠ Names only. This is the only string form of a cookie that may reach the log.
    var logName: String { name }
}

// ⚠⚠ NOT DECORATION. A Swift struct's default `String(describing:)` prints **every stored property**,
// so the first `RKMLog.verbose("cookies: \(cookies)")` anywhere in this feature would write the
// `rkm_session` value into a file that gets pasted into chat — and `LOGGING.md` §9's acceptance gate
// (`grep -iE "password|token|api_key|rkm_session"`) would fail on a real run. Conforming here means the
// *type itself* cannot leak, rather than every call site remembering not to. The harness asserts both
// halves: the description must contain the name and must NOT contain the value.
extension CookieSnapshot: CustomStringConvertible {
    var description: String {
        "CookieSnapshot(\(name) @ \(domain.isEmpty ? "?" : domain)\(path.isEmpty ? "/" : path)"
            + "\(isSecure ? " secure" : "")\(isHTTPOnly ? " httpOnly" : "")\(expiresAt == nil ? " session" : ""))"
    }
}

/// Why a cookie was NOT attached. ⚠ Every one of these is a plausible explanation for a `401`, which
/// is otherwise the least diagnosable failure in the app: the server says "sign in", the user *is*
/// signed in, and nothing anywhere says the cookie never left the device.
enum CookieSkipReason: Equatable {
    case expired(Date)
    case secureOnPlainHTTP
    case domainMismatch(host: String)
    case pathMismatch(path: String)
    case malformedName
    /// A CR or LF in a value is header injection, never a cookie to forward.
    case illegalCharacters
    /// A more specific cookie of the same name won (RFC 6265 §5.4 step 2).
    case shadowedByPath(String)

    var sentence: String {
        switch self {
        case .expired(let date): return "expired \(date)"
        case .secureOnPlainHTTP: return "Secure cookie, but this address is not https"
        case .domainMismatch(let host): return "domain does not cover \(host)"
        case .pathMismatch(let path): return "path does not cover \(path)"
        case .malformedName: return "malformed name"
        case .illegalCharacters: return "value contains a control character"
        case .shadowedByPath(let path): return "shadowed by the cookie for \(path)"
        }
    }
}

struct CookieSkip: Equatable {
    var name: String
    var reason: CookieSkipReason
}

/// The outcome of asking "which cookies go with this request?".
struct CookieHeaderOutcome: Equatable {
    /// `nil` when nothing may be sent. Emphatically NOT an empty string: an empty `Cookie:` header is
    /// a header the server can reject, whereas no header at all is the honest "signed out".
    var header: String?
    /// Names, in the order they appear in the header.
    var sent: [String]
    var skipped: [CookieSkip]

    var isEmpty: Bool { header == nil }

    /// `sent 1 [rkm_session] · skipped 1 [rkm_session: expired …]` — names and reasons only.
    var summary: String {
        var parts = ["sent \(sent.count) [\(sent.joined(separator: " "))]"]
        if !skipped.isEmpty {
            let described = skipped.map { "\($0.name): \($0.reason.sentence)" }.joined(separator: "; ")
            parts.append("skipped \(skipped.count) [\(described)]")
        }
        return parts.joined(separator: " · ")
    }
}

/// Which cookies belong on a request to a URL — the native side of the session, because a native
/// `URLSession` has **no cookie jar of its own** (`NATIVE_FEEL_AND_OFFLINE_PLAN.md` §4.4 option 1, now
/// a hard prerequisite: `RKM_AUTH_REQUIRED=true`, and all six `/api/offline/*` routes are
/// session-scoped).
enum CookieHeader {

    /// The rules, in order, all from RFC 6265 §5.4:
    ///
    /// 1. **Not expired** — a stored `Expires` in the past is dropped, not sent.
    /// 2. **Domain match** — the host equals the cookie's domain, or is a subdomain of it. A leading
    ///    dot in the stored domain is stripped before comparing, because `HTTPCookie` reports `Domain`
    ///    inconsistently and `.host` vs `host` must not decide whether someone stays signed in.
    /// 3. **Path match** — `/api/x` is covered by `/`, `/api`, and `/api/`; it is NOT covered by `/ap`.
    /// 4. **Secure** — only over `https`. ⚠ This one matters here: the app runs on **plain http** over
    ///    the LAN and over the tailnet (the server sets `secure=False` deliberately, `apple/README.md`),
    ///    so a `Secure` cookie would be dropped silently on the address the app actually uses.
    ///    The skip is reported, which is the difference between a mystery 401 and a sentence.
    /// 5. **Name legality** and **control characters** — a name with `=` `;` or a space, or a value
    ///    containing CR/LF, is dropped. A cookie whose value contains a line break is HTTP header
    ///    injection, and forwarding it is how a "cookie problem" becomes a security problem.
    /// 6. **Duplicates by name**: the most specific path wins, the rest are reported as shadowed.
    ///    Our server has exactly one `rkm_session`; two would be ambiguous, and sending both is not
    ///    more correct, it is just harder to debug.
    ///
    /// Ordering within the header: longer paths first, then names alphabetically. ⚠ RFC 6265 sorts
    /// equal-length paths by creation time, which WebKit does not give us; alphabetical is the
    /// deterministic stand-in, and determinism is what makes this testable.
    static func evaluate(cookies: [CookieSnapshot], url: URL, now: Date = Date()) -> CookieHeaderOutcome {
        guard let host = url.host?.lowercased(), !host.isEmpty else {
            return CookieHeaderOutcome(header: nil, sent: [], skipped: [])
        }
        let path = url.path.isEmpty ? "/" : url.path
        let isHTTPS = url.scheme?.lowercased() == "https"

        var skipped: [CookieSkip] = []
        var eligible: [CookieSnapshot] = []

        for cookie in cookies {
            guard isLegalName(cookie.name) else {
                skipped.append(.init(name: cookie.name, reason: .malformedName))
                continue
            }
            guard !containsControlCharacters(cookie.value), !containsControlCharacters(cookie.name) else {
                skipped.append(.init(name: cookie.name, reason: .illegalCharacters))
                continue
            }
            if let expires = cookie.expiresAt, expires <= now {
                skipped.append(.init(name: cookie.name, reason: .expired(expires)))
                continue
            }
            guard domainMatches(cookie: cookie.domain, host: host) else {
                skipped.append(.init(name: cookie.name, reason: .domainMismatch(host: host)))
                continue
            }
            guard pathMatches(cookie: cookie.path, request: path) else {
                skipped.append(.init(name: cookie.name, reason: .pathMismatch(path: path)))
                continue
            }
            if cookie.isSecure && !isHTTPS {
                skipped.append(.init(name: cookie.name, reason: .secureOnPlainHTTP))
                continue
            }
            eligible.append(cookie)
        }

        // Most specific path first; alphabetical for the tie, so the output is stable.
        let ordered = eligible.sorted { left, right in
            if left.path.count != right.path.count { return left.path.count > right.path.count }
            return left.name < right.name
        }

        var chosen: [CookieSnapshot] = []
        for cookie in ordered {
            if let existing = chosen.first(where: { $0.name == cookie.name }) {
                skipped.append(.init(name: cookie.name, reason: .shadowedByPath(existing.path)))
                continue
            }
            chosen.append(cookie)
        }

        guard !chosen.isEmpty else {
            return CookieHeaderOutcome(header: nil, sent: [], skipped: skipped)
        }
        let header = chosen.map { "\($0.name)=\($0.value)" }.joined(separator: "; ")
        return CookieHeaderOutcome(header: header, sent: chosen.map(\.name), skipped: skipped)
    }

    /// The header dictionary to merge into a request. Empty when nothing may be sent.
    static func headerFields(cookies: [CookieSnapshot], url: URL, now: Date = Date()) -> [String: String] {
        let outcome = evaluate(cookies: cookies, url: url, now: now)
        guard let header = outcome.header else { return [:] }
        return ["Cookie": header]
    }

    // MARK: - Pieces

    /// `host` matches `example.com` and `.example.com`, and `a.example.com` matches both too.
    static func domainMatches(cookie domain: String, host: String) -> Bool {
        let normalised = domain.hasPrefix(".") ? String(domain.dropFirst()) : domain
        let candidate = normalised.lowercased()
        guard !candidate.isEmpty else { return false }
        return host == candidate || host.hasSuffix("." + candidate)
    }

    /// RFC 6265 §5.1.4: the cookie path is a prefix of the request path, and either it is the whole
    /// path or the boundary is a `/`.
    static func pathMatches(cookie path: String, request: String) -> Bool {
        let cookiePath = path.isEmpty ? "/" : path
        guard request.hasPrefix(cookiePath) else { return false }
        if request.count == cookiePath.count { return true }
        if cookiePath.hasSuffix("/") { return true }
        let index = request.index(request.startIndex, offsetBy: cookiePath.count)
        return request[index] == "/"
    }

    static func isLegalName(_ name: String) -> Bool {
        guard !name.isEmpty else { return false }
        let illegal = CharacterSet(charactersIn: "=; \t\r\n")
        return name.rangeOfCharacter(from: illegal) == nil
    }

    static func containsControlCharacters(_ value: String) -> Bool {
        value.unicodeScalars.contains { scalar in
            scalar.value < 0x20 || scalar.value == 0x7F
        }
    }
}
