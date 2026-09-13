import Foundation

/// Why an address was rejected.
///
/// Every case carries a message fit to put on the setup screen, because the plan's rule
/// (`apple/README.md`) is that **a rejected address must say why** — "invalid address" is
/// a dead end for the person typing, and the whole point of screen #0 is that a human can
/// recover from a typo without reinstalling the app.
public enum ServerAddressError: Error, Equatable, LocalizedError {
    case empty
    case unsupportedScheme(String)
    case missingHost
    case credentialsNotAllowed
    case notAnOrigin(String)
    case invalidPort(String)
    case malformedHost(String)

    public var errorDescription: String? {
        switch self {
        case .empty:
            return "Enter the server address."
        case .unsupportedScheme(let scheme):
            return "“\(scheme)” isn’t supported — use http:// or https://."
        case .missingHost:
            return "That address has no host in it."
        case .credentialsNotAllowed:
            return "Leave the username and password out — the app asks for those on the sign-in screen."
        case .notAnOrigin(let detail):
            return "Enter just the server address, with nothing after it (found “\(detail)”)."
        case .invalidPort(let port):
            return "“\(port)” isn’t a valid port — use 1–65535."
        case .malformedHost(let host):
            return "“\(host)” doesn’t look like a host name or IP address."
        }
    }
}

/// A server address a human typed, parsed and normalised into the **origin** the Apple
/// clients load from.
///
/// Both apps open on a server-address screen (`docs/APPLE_CLIENTS_PLAN.md` §2 — the
/// Jellyfin/Infuse/Plex model), so the rules for turning what someone typed into a usable
/// base URL must exist exactly once. This is that one place, and the tvOS app will use the
/// same type.
///
/// What "normalise" means here:
/// - **A bare host is accepted.** No scheme → one is supplied: `https` for a name (the
///   Tailscale case, `rkm-hp.tail8d5e8.ts.net`), `http` for an IP literal, `localhost`,
///   a `.local` name, or any explicit port that isn't 443/8443 (the LAN case,
///   `192.168.1.10:8124`). ⚠ That last rule is a deliberate refinement of
///   `apple/README.md`'s "add https:// when no scheme is given": `nginx` serves this stack
///   as **plain HTTP** on a LAN, so assuming TLS there would fail in a way that looks like
///   a broken app. The setup screen shows the normalised result before it connects, so the
///   choice is never silent.
/// - Trailing slashes go, the scheme and host are lowercased, and a `http:/host` typo is
///   forgiven.
/// - **Normalisation is idempotent** — `ServerAddress(ServerAddress(x).displayString)`
///   equals `ServerAddress(x)`. It is unit-tested, because the address is persisted and
///   read back on every launch.
public struct ServerAddress: Hashable, Sendable, CustomStringConvertible {

    /// The normalised origin — scheme + host (+ port). Never a trailing slash, never a path.
    public let url: URL
    /// `"http"` or `"https"`, lowercased.
    public let scheme: String
    /// The host as it will be used, lowercased and **without** IPv6 brackets.
    public let host: String
    /// The explicit port, or `nil` when the scheme's default applies.
    public let port: Int?
    /// Whether the human typed a scheme or we supplied one. Worth recording: when a
    /// connection fails, "did I type https:// or did the app assume it?" is the first
    /// question, and the HUD/log answer it without a second round trip.
    public let hadExplicitScheme: Bool
    /// True when `host` is an IPv6 literal (so the authority needs brackets when rebuilt).
    public let isIPv6: Bool

    // MARK: - Parsing

    public init(rawValue raw: String) throws {
        let cleaned = Self.cleaned(raw)
        guard !cleaned.isEmpty else { throw ServerAddressError.empty }

        let split = Self.splitScheme(cleaned)
        let hadExplicitScheme = split.scheme != nil
        var scheme = split.scheme?.lowercased() ?? ""

        if let given = split.scheme, scheme != "http" && scheme != "https" {
            throw ServerAddressError.unsupportedScheme(given.lowercased())
        }

        // "http:/host" and "http://host" both leave slashes in front of the authority.
        var remainder = split.remainder
        while remainder.hasPrefix("/") { remainder.removeFirst() }
        guard !remainder.isEmpty else { throw ServerAddressError.missingHost }

        let authority = String(remainder.prefix { $0 != "/" && $0 != "?" && $0 != "#" })
        let tail = String(remainder.dropFirst(authority.count))
        if !tail.isEmpty {
            // A trailing slash (any number of them) is normalisation, not an error — the
            // documented `https://rkm-hp.tail8d5e8.ts.net/` form has to be accepted.
            let isJustSlashes = tail.allSatisfy { $0 == "/" }
            if !isJustSlashes {
                throw ServerAddressError.notAnOrigin(String(tail.prefix(24)))
            }
        }

        // Credentials in the address are both a redaction hazard and unnecessary — the
        // web UI owns sign-in.
        if authority.contains("@") { throw ServerAddressError.credentialsNotAllowed }

        let parts = try Self.splitAuthority(authority)
        // ⚠ Lowercased here rather than left to `URL`: `absoluteString`'s case behaviour is not
        // the same in CoreFoundation and corelibs, and a persisted address that reads back in a
        // different case per platform is a bug waiting to happen. Host names are case-insensitive.
        let host = parts.host.lowercased()
        guard Self.isPlausibleHost(host, isIPv6: parts.isIPv6) else {
            throw ServerAddressError.malformedHost(parts.host.isEmpty ? authority : parts.host)
        }
        let port = try parts.portText.map { try Self.parsePort($0) }

        if !hadExplicitScheme {
            scheme = Self.defaultScheme(forHost: host, port: port)
        }

        let authorityOut = parts.isIPv6 ? "[\(host)]" : host
        let urlString = port.map { "\(scheme)://\(authorityOut):\($0)" } ?? "\(scheme)://\(authorityOut)"
        guard let url = URL(string: urlString), url.host != nil else {
            throw ServerAddressError.malformedHost(parts.host)
        }

        self.url = url
        self.scheme = scheme
        self.host = host
        self.port = port
        self.hadExplicitScheme = hadExplicitScheme
        self.isIPv6 = parts.isIPv6
    }

    // MARK: - Reading it back

    /// The normalised form — also the string that gets persisted, so a launch after a
    /// successful connect needs no re-parsing decisions.
    public var displayString: String { url.absoluteString }

    /// The host alone, for the setup screen and the log line ("redacted host only is fine,
    /// keep it" — `LOGGING.md` §3; the host is not a secret, the credentials are).
    public var displayHost: String {
        port.map { "\(host):\($0)" } ?? host
    }

    public var isSecure: Bool { scheme == "https" }

    /// A plain-HTTP address is expected on the LAN and works because the app declares an
    /// App Transport Security exception — the setup screen says so rather than leaving the
    /// person wondering why it is allowed.
    public var usesPlainHTTP: Bool { scheme == "http" }

    /// True for `localhost`, `*.local`, and private/loopback/link-local IP literals.
    /// Drives the "is Tailscale running on this device?" hint — the one prerequisite the
    /// app cannot satisfy itself (`docs/APPLE_CLIENTS_PLAN.md` §2.3).
    public var isLikelyOnLocalNetwork: Bool { Self.isLocalHost(host) }

    /// True for a `*.ts.net` Tailscale name, where the hint is the opposite one: it works
    /// away from home **only** if the Tailscale app is running on the device.
    public var isLikelyTailscale: Bool { host.lowercased().hasSuffix(".ts.net") }

    public var description: String { displayString }

    /// "The same server", not "typed the same way".
    ///
    /// ⚠ `hadExplicitScheme` is deliberately **excluded**: it records how the address was
    /// entered, and once the normalised form has been written out and read back the scheme is
    /// always explicit. Including it would make `ServerAddress("host")` unequal to
    /// `ServerAddress("https://host")` — the same server, said two ways — and would break the
    /// idempotence the persistence depends on.
    public static func == (lhs: ServerAddress, rhs: ServerAddress) -> Bool {
        lhs.url == rhs.url
            && lhs.scheme == rhs.scheme
            && lhs.host == rhs.host
            && lhs.port == rhs.port
            && lhs.isIPv6 == rhs.isIPv6
    }

    public func hash(into hasher: inout Hasher) {
        hasher.combine(url)
        hasher.combine(scheme)
        hasher.combine(host)
        hasher.combine(port)
        hasher.combine(isIPv6)
    }

    // MARK: - Rules

    private static func cleaned(_ raw: String) -> String {
        var text = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        // People paste `<http://host>` out of documentation or chat.
        if text.hasPrefix("<"), text.hasSuffix(">"), text.count > 2 {
            text = String(text.dropFirst().dropLast()).trimmingCharacters(in: .whitespaces)
        }
        return text
    }

    /// Splits `scheme://rest`, `scheme:/rest` (typo) and `scheme:rest`, or reports no scheme.
    private static func splitScheme(_ text: String) -> (scheme: String?, remainder: String) {
        guard let colon = text.firstIndex(of: ":") else { return (nil, text) }
        let candidate = String(text[text.startIndex..<colon])
        guard !candidate.isEmpty,
              candidate.allSatisfy({ $0.isLetter || $0.isNumber || $0 == "+" || $0 == "-" || $0 == "." }),
              candidate.first?.isLetter == true
        else { return (nil, text) }

        var rest = String(text[text.index(after: colon)...])
        // ⚠ Only a *known* scheme counts. Otherwise `rkm-hp.tail8d5e8.ts.net:8124` — a real
        // address form — would be read as scheme "rkm-hp.tail8d5e8.ts.net".
        guard rest.hasPrefix("//") || isKnownScheme(candidate) else { return (nil, text) }
        while rest.hasPrefix("/") { rest.removeFirst() }
        return (candidate, rest)
    }

    private static func isKnownScheme(_ candidate: String) -> Bool {
        let lower = candidate.lowercased()
        return lower == "http" || lower == "https"
    }

    private struct Authority {
        let host: String
        let portText: String?
        let isIPv6: Bool
    }

    private static func splitAuthority(_ authority: String) throws -> Authority {
        if authority.hasPrefix("[") {
            guard let close = authority.firstIndex(of: "]") else {
                throw ServerAddressError.malformedHost(authority)
            }
            let inner = String(authority[authority.index(after: authority.startIndex)..<close])
            let rest = String(authority[authority.index(after: close)...])
            if rest.isEmpty { return Authority(host: inner, portText: nil, isIPv6: true) }
            guard rest.hasPrefix(":") else { throw ServerAddressError.malformedHost(authority) }
            return Authority(host: inner, portText: String(rest.dropFirst()), isIPv6: true)
        }
        let colons = authority.filter { $0 == ":" }.count
        if colons == 0 { return Authority(host: authority, portText: nil, isIPv6: false) }
        guard colons == 1 else {
            // More than one colon and no brackets is an unbracketed IPv6 literal — say so
            // rather than silently mangling it.
            throw ServerAddressError.malformedHost(authority)
        }
        let pieces = authority.split(separator: ":", maxSplits: 1, omittingEmptySubsequences: false)
        return Authority(host: String(pieces[0]), portText: String(pieces[1]), isIPv6: false)
    }

    private static func parsePort(_ text: String) throws -> Int {
        let digits = text.trimmingCharacters(in: .whitespaces)
        guard !digits.isEmpty, digits.allSatisfy({ $0.isNumber }), let value = Int(digits),
              (1...65535).contains(value)
        else { throw ServerAddressError.invalidPort(text) }
        return value
    }

    private static func isPlausibleHost(_ host: String, isIPv6: Bool) -> Bool {
        guard !host.isEmpty else { return false }
        if isIPv6 {
            return host.contains(":")
                && host.allSatisfy { $0.isHexDigit || $0 == ":" || $0 == "." }
        }
        let allowed = CharacterSet(charactersIn: "abcdefghijklmnopqrstuvwxyz0123456789-._")
        guard host.lowercased().unicodeScalars.allSatisfy({ allowed.contains($0) }) else { return false }
        guard host.contains(where: { $0.isLetter || $0.isNumber }) else { return false }
        guard !host.hasPrefix("."), !host.hasSuffix("."), !host.hasPrefix("-"), !host.hasSuffix("-") else {
            return false
        }
        return true
    }

    /// ⚠ The one judgement call in this file, and it is deliberate — see the type comment.
    /// A name gets `https`; anything that is really a "reach this box directly" address gets
    /// `http`, because that is how this stack is actually served on a LAN.
    private static func defaultScheme(forHost host: String, port: Int?) -> String {
        if isIPLiteral(host) { return "http" }
        if isLocalHost(host) { return "http" }
        if let port, port != 443, port != 8443 { return "http" }
        return "https"
    }

    static func isIPLiteral(_ host: String) -> Bool {
        if host.contains(":") { return true }          // an IPv6 literal, brackets already stripped
        return ipv4Components(host) != nil
    }

    /// Exactly four dotted numeric components, each 0–255.
    static func ipv4Components(_ host: String) -> [Int]? {
        let parts = host.split(separator: ".", omittingEmptySubsequences: false)
        guard parts.count == 4 else { return nil }
        var values: [Int] = []
        for part in parts {
            guard !part.isEmpty, part.allSatisfy({ $0.isNumber }),
                  let value = Int(part), (0...255).contains(value)
            else { return nil }
            values.append(value)
        }
        return values
    }

    /// `localhost`, a `.local` name, or a private / loopback / link-local IP literal.
    static func isLocalHost(_ host: String) -> Bool {
        let lower = host.lowercased()
        if lower == "localhost" || lower.hasSuffix(".localhost") { return true }
        if lower.hasSuffix(".local") { return true }
        if lower == "::1" || lower.hasPrefix("fe80:") { return true }
        guard let octets = ipv4Components(lower) else { return false }
        switch (octets[0], octets[1]) {
        case (10, _): return true
        case (127, _): return true
        case (169, 254): return true
        case (172, 16...31): return true
        case (192, 168): return true
        default: return false
        }
    }
}
