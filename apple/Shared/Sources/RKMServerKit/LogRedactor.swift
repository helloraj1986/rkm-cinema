import Foundation

/// The **one** place a URL, a query, a header set, a cookie line or a body is made safe to
/// write down — `apple/LOGGING.md` §6.
///
/// ⚠ Why it is central rather than a helper each call site remembers to use: a redaction bug
/// is a credential leak. These apps hold a session cookie, the server holds
/// Jellyfin/OpenSubtitles/TMDB keys, and log files get pasted into chat. `LOGGING.md` §9
/// makes it an acceptance gate — `grep -iE "password|token|api_key|rkm_session"` over a real
/// run's log must return **nothing**.
///
/// The design that makes that gate hold **by construction** rather than by care:
///
/// 1. A value known to be sensitive is never emitted — a cookie **value** is dropped before
///    the string is built, not filtered afterwards.
/// 2. Every public entry point ends in ``hardSweep(_:)``, which runs on the finished string
///    and removes any surviving sensitive **key name together with the value bound to it**.
///    A caller cannot forget to redact, because there is nothing to remember.
/// 3. ``RKMLog`` re-checks the finished line with ``leaks(_:)`` and withholds it rather than
///    writing it. A redaction bug therefore cannot produce a leak — it produces a missing
///    log line.
///
/// Two label words are substituted for sensitive key **names** so that the §9 `grep`
/// (which is case-insensitive and would match the name alone) still passes while the log
/// keeps its diagnostic shape: `cred` for anything credential-shaped, and `session` for a
/// session-shaped key or cookie name. Values become ``placeholder``.
public enum LogRedactor {

    /// What a sensitive value is replaced with. ⚠ Contains none of ``forbiddenSubstrings``.
    public static let placeholder = "[redacted]"
    /// Label used where a credential-shaped **name** has to stay readable.
    public static let sensitiveKeyLabel = "cred"
    /// Label used where a session-shaped name has to stay readable — including the session
    /// cookie's, because `rkm_session` is itself on the §9 grep list, and
    /// `LOGGING.md` §3 still wants to see *that a session cookie landed*.
    public static let sessionLabel = "session"

    /// The literal list `LOGGING.md` §9 greps for. Exported so the tests can assert the gate
    /// against the same words the acceptance command uses, and so ``RKMLog`` can enforce it.
    public static let forbiddenSubstrings = ["password", "token", "api_key", "rkm_session"]

    /// ⚠ A **wider** list than the gate — this is what the safety sweep hunts for. Every entry
    /// is safe to over-apply (losing a word from a log line costs nothing; leaving a
    /// credential in one costs the account), and none of them appears in the labels above or
    /// in ``placeholder``, which is what guarantees the sweep terminates and never
    /// re-redacts its own output.
    private static let sweepNeedles = [
        "password", "passwd", "passphrase", "token", "apikey", "api_key", "api-key",
        "secret", "credential", "rkm_session", "session_id", "sessionid",
    ]

    /// Key names that are sensitive on their own rather than by containing a fragment.
    private static let exactSensitiveKeys: Set<String> = [
        "pwd", "sid", "sig", "key", "auth", "authorization",
    ]

    private static let sensitiveFragments = [
        "password", "passwd", "passphrase", "token", "secret", "apikey", "api_key",
        "api-key", "session", "credential", "signature",
    ]

    private static let sensitiveHeaderNames: Set<String> = [
        "authorization", "proxy-authorization", "cookie", "set-cookie",
        "x-api-key", "api-key", "x-emby-token", "x-mediabrowser-token", "x-auth-token",
    ]

    // MARK: - Asking questions

    /// True when this key/parameter/header name should never have its value written down.
    public static func isSensitive(key: String) -> Bool {
        let lowered = key.lowercased().trimmingCharacters(in: .whitespaces)
        if exactSensitiveKeys.contains(lowered) { return true }
        return sensitiveFragments.contains { lowered.contains($0) }
    }

    public static func isSensitive(header name: String) -> Bool {
        let lowered = name.lowercased().trimmingCharacters(in: .whitespaces)
        if sensitiveHeaderNames.contains(lowered) { return true }
        return sensitiveFragments.contains { lowered.contains($0) }
    }

    /// Which of the §9 grep words survive in a finished string. Empty means safe.
    ///
    /// Used by the tests as a property assertion over a corpus of nasty inputs, and by
    /// ``RKMLog`` as its last line of defence.
    public static func leaks(_ text: String) -> [String] {
        forbiddenSubstrings.filter { text.range(of: $0, options: .caseInsensitive) != nil }
    }

    /// Convenience inverse of ``leaks(_:)``.
    public static func isSafe(_ text: String) -> Bool {
        leaks(text).isEmpty
    }

    // MARK: - Entry points

    /// The general safety net. Use for anything that is not specifically a URL or a header:
    /// `NSError` text, a JS exception, a response's `detail` field.
    public static func redact(text input: String) -> String {
        var output = redactUserInfo(in: input)
        output = redactEmbeddedURLs(in: output)
        output = redactCredentialSchemes(in: output)
        return hardSweep(output)
    }

    public static func redact(url: URL) -> String {
        redact(urlString: url.absoluteString)
    }

    /// Redacts a URL **or a bare path+query** (the iOS shell logs what the web UI fetched, so
    /// `/api/jellyfin/hls/abc/master.m3u8?mode=remux&token=…` has to work without a scheme).
    public static func redact(urlString input: String) -> String {
        guard !input.isEmpty else { return input }
        var text = redactUserInfo(in: input)
        // Fragment state never reaches the server and can carry a token in a SPA.
        if let hash = text.firstIndex(of: "#") {
            text = String(text[text.startIndex..<hash])
        }
        if let mark = text.firstIndex(of: "?") {
            let path = String(text[text.startIndex..<mark])
            let query = String(text[text.index(after: mark)...])
            return hardSweep(path + "?" + redact(query: query))
        }
        return hardSweep(text)
    }

    /// Redacts an `a=1&b=2` query, keeping the non-sensitive pairs intact and in order so the
    /// request is still recognisable, and dropping the sensitive **name** as well as its
    /// value (`LOGGING.md` §9 greps for the name).
    public static func redact(query: String) -> String {
        guard !query.isEmpty else { return query }
        let pairs = query.split(separator: "&", omittingEmptySubsequences: false)
        let redacted = pairs.map { pair -> String in
            let text = String(pair)
            guard let equals = text.firstIndex(of: "=") else {
                return isSensitive(key: text) ? label(for: text) : text
            }
            let name = String(text[text.startIndex..<equals])
            guard isSensitive(key: name) else { return text }
            return "\(label(for: name))=\(placeholder)"
        }
        // ⚠ Swept as well: a *value* can be sensitive-shaped (`mode=tokenizer`) even when its
        // key is not, and this entry point can be called on its own.
        return hardSweep(redacted.joined(separator: "&"))
    }

    public static func redact(headers: [String: String]) -> [String: String] {
        var output: [String: String] = [:]
        for (name, value) in headers {
            let lowered = name.lowercased()
            if lowered == "cookie" || lowered == "set-cookie" {
                output[name] = redact(cookieHeader: value)
            } else if isSensitive(header: name) {
                // Presence only — `LOGGING.md` §6: never a full Authorization header.
                output[name] = placeholder
            } else {
                output[name] = redact(text: value)
            }
        }
        return output
    }

    /// One loggable line for a request's or response's headers.
    public static func describe(headers: [String: String], limit: Int = 8) -> String {
        let safe = redact(headers: headers)
        let names = safe.keys.sorted()
        var parts = names.prefix(limit).map { "\($0): \(safe[$0] ?? placeholder)" }
        if names.count > limit { parts.append("(+\(names.count - limit) more)") }
        return parts.joined(separator: " · ")
    }

    /// ⚠ **Names and a count — never a value** (`LOGGING.md` §3). A sensitive cookie name is
    /// relabelled rather than printed, because the point of logging the names is to answer
    /// "did the session cookie land?", and the answer survives the relabelling.
    ///
    /// This is the entry point a native client should call: it takes names, so a cookie
    /// **value** never becomes a string in the first place and cannot leak by accident.
    public static func redact(cookieNames: [String]) -> String {
        guard !cookieNames.isEmpty else { return "no cookies" }
        let safe = cookieNames.map { name -> String in
            let trimmed = name.trimmingCharacters(in: .whitespaces)
            return isSensitive(key: trimmed) ? sessionLabel : trimmed
        }
        let noun = cookieNames.count == 1 ? "cookie" : "cookies"
        return "\(cookieNames.count) \(noun) (\(safe.joined(separator: ", ")))"
    }

    /// Same thing from a raw `Cookie:` header value — the names are extracted and the values
    /// are dropped on the way through.
    public static func redact(cookieHeader: String) -> String {
        let pairs = cookieHeader
            .split(separator: ";")
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
        let names = pairs.map { pair -> String in
            pair.split(separator: "=", maxSplits: 1, omittingEmptySubsequences: false)
                .first
                .map(String.init) ?? pair
        }
        return redact(cookieNames: names)
    }

    // MARK: - The machinery

    private static func label(for name: String) -> String {
        name.lowercased().contains("session") ? sessionLabel : sensitiveKeyLabel
    }

    private static let embeddedURLRegex = try? NSRegularExpression(
        pattern: #"(?i)https?://[^\s"'<>]+"#, options: []
    )

    private static let credentialSchemeRegex = try? NSRegularExpression(
        // ⚠ `{16,}` rather than a short minimum: a scheme word followed by eight letters is
        // ordinary prose ("the basic settings are wrong"), and over-redacting prose costs more
        // than it buys. Real bearer/basic credentials are far longer than 16 characters.
        pattern: #"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=\-]{16,}"#, options: []
    )

    /// `http://user:hunter2@host/…` — a password in a URL.
    ///
    /// ⚠ The §9 grep would **not** catch this: `hunter2` is shaped like nothing on the word
    /// list. It is still a password in a file that gets pasted into chat, so it is removed on
    /// its own merits. (These apps refuse to *store* an address containing credentials —
    /// `ServerAddressError.credentialsNotAllowed` — so this is the free-text path.)
    private static let urlUserInfoRegex = try? NSRegularExpression(
        pattern: #"(?i)(://)[^/\s:@]+:[^/\s@]+@"#, options: []
    )

    private static func redactUserInfo(in text: String) -> String {
        guard let regex = urlUserInfoRegex else { return text }
        let range = NSRange(text.startIndex..<text.endIndex, in: text)
        return regex.stringByReplacingMatches(
            in: text, options: [], range: range,
            withTemplate: "$1\(sensitiveKeyLabel)=\(placeholder)@"
        )
    }

    /// Any `http(s)://…` sitting inside a longer message (an `NSError` description, a JS
    /// exception) gets the URL treatment rather than surviving as free text.
    private static func redactEmbeddedURLs(in text: String) -> String {
        guard let regex = embeddedURLRegex else { return text }
        let range = NSRange(text.startIndex..<text.endIndex, in: text)
        let matches = regex.matches(in: text, options: [], range: range)
        guard !matches.isEmpty else { return text }

        var output = text
        for match in matches.reversed() {
            guard let matchRange = Range(match.range, in: output) else { continue }
            output.replaceSubrange(matchRange, with: redact(urlString: String(output[matchRange])))
        }
        return output
    }

    /// `Authorization: Bearer eyJ…` in free text. The scheme word is harmless; the credential
    /// after it is not.
    private static func redactCredentialSchemes(in text: String) -> String {
        guard let regex = credentialSchemeRegex else { return text }
        let range = NSRange(text.startIndex..<text.endIndex, in: text)
        return regex.stringByReplacingMatches(
            in: text, options: [], range: range, withTemplate: "$1 \(placeholder)"
        )
    }

    /// The last thing that touches a string before it is written or displayed.
    ///
    /// For each needle: widen to the whole key token, absorb a following `: value` / `= value`
    /// binding, and replace the lot with a safe label. Progress is guaranteed because neither
    /// the labels nor ``placeholder`` contain any needle.
    private static func hardSweep(_ input: String) -> String {
        var text = input
        for needle in sweepNeedles {
            var searchFrom = text.startIndex
            while let found = text.range(of: needle, options: .caseInsensitive, range: searchFrom..<text.endIndex) {
                let start = expandBackward(text, from: found.lowerBound)
                let keyEnd = expandForward(text, from: found.upperBound)
                let label = needle.lowercased().contains("session") ? sessionLabel : sensitiveKeyLabel

                var end = keyEnd
                var suffix = ""
                if let valueEnd = valueRangeEnd(text, after: keyEnd) {
                    end = valueEnd
                    suffix = "=\(placeholder)"
                }
                let replacement = label + suffix
                text.replaceSubrange(start..<end, with: replacement)
                searchFrom = text.index(start, offsetBy: replacement.count)
            }
        }
        return text
    }

    private static func isKeyCharacter(_ character: Character) -> Bool {
        character.isLetter || character.isNumber
            || character == "_" || character == "-" || character == "." || character == "%"
    }

    private static func expandBackward(_ text: String, from index: String.Index) -> String.Index {
        var start = index
        while start > text.startIndex {
            let previous = text.index(before: start)
            guard isKeyCharacter(text[previous]) else { break }
            start = previous
        }
        return start
    }

    private static func expandForward(_ text: String, from index: String.Index) -> String.Index {
        var end = index
        while end < text.endIndex, isKeyCharacter(text[end]) {
            end = text.index(after: end)
        }
        return end
    }

    /// The end of a `: value` / `= value` binding that follows `index`, or `nil` when there
    /// isn't one (a bare word in prose). Tolerates the closing quote of a JSON key.
    private static func valueRangeEnd(_ text: String, after index: String.Index) -> String.Index? {
        var cursor = index
        while cursor < text.endIndex, isQuoteOrSpace(text[cursor]) { cursor = text.index(after: cursor) }
        guard cursor < text.endIndex, text[cursor] == ":" || text[cursor] == "=" else { return nil }
        cursor = text.index(after: cursor)
        while cursor < text.endIndex, isQuoteOrSpace(text[cursor]) { cursor = text.index(after: cursor) }
        while cursor < text.endIndex, !isValueDelimiter(text[cursor]) { cursor = text.index(after: cursor) }
        return cursor
    }

    private static func isQuoteOrSpace(_ character: Character) -> Bool {
        character == "\"" || character == "'" || character == " " || character == "\t"
    }

    private static func isValueDelimiter(_ character: Character) -> Bool {
        isQuoteOrSpace(character)
            || character == "\n" || character == "\r"
            || character == "&" || character == "," || character == ";"
            || character == "}" || character == ")" || character == "]" || character == ">"
    }
}
