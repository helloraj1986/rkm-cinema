import Foundation
import RKMServerKit

// The server's offline contract, as the DEVICE sees it (`NATIVE_FEEL_AND_OFFLINE_PLAN.md` §4.3, built in
// phase B1). One client, four calls — `bundle` to plan, `prepare` to commit, `status` to wait, `HEAD` to
// size — and one download request that `OfflineDownloads` hands to a background `URLSession`.
//
// ⚠ The iOS shell has NO general API client, deliberately (`apple/README.md`: "the web UI makes its own
// /api calls"). This is not the beginning of one: it is the minimum needed for a native download, and
// the only other route it knows is `/api/library/items`, used by the DEBUG trigger so this phase is
// testable before the page affordances exist (B4).

/// `GET /api/offline/bundle/{id}` — everything the device needs to decide and to write its own manifest.
struct OfflineBundle: Decodable {
    var v: Int
    var itemId: String
    var title: String
    var year: Int?
    var type: String?
    var seriesId: String?
    var mode: String
    var needsTranscode: Bool
    var container: String?
    var videoCodec: String?
    var durationSeconds: Double?
    /// The server's ESTIMATE, from the library file — not the size `HEAD` will report.
    var estimateBytes: Int64?
    var state: String
    var bytes: Int64?
    var size: Int64?
    var borrowed: Bool
    var posterURL: String?
    var backdropURL: String?
    var fileURL: String
    var error: String?

    private enum CodingKeys: String, CodingKey {
        case v, title, year, type, mode, container, state, bytes, size, borrowed, error
        case itemId = "item_id"
        case seriesId = "series_id"
        case needsTranscode = "needs_transcode"
        case videoCodec = "video_codec"
        case durationSeconds = "duration_s"
        case estimateBytes = "estimate_bytes"
        case posterURL = "poster_url"
        case backdropURL = "backdrop_url"
        case fileURL = "file_url"
    }
}

/// The manifest body shared by `POST /api/offline/prepare` and `GET /api/offline/status/{id}`.
struct OfflineServerManifest: Decodable {
    var itemId: String
    var mode: String
    var state: String
    /// What is on the SERVER for this rendition right now (`bytes` in the JSON — the progress field).
    var size: Int64
    /// The finished artefact's size, and 0 until it exists. ⚠ Two fields on purpose, server-side: a
    /// progress bar reads `size`, and "is it ready" reads `state`.
    var readySize: Int64
    var title: String?
    var container: String?
    var borrowed: Bool
    var needsTranscode: Bool
    var error: String?
    var reused: Bool?

    private enum CodingKeys: String, CodingKey {
        case mode, title, container, borrowed, error, reused
        case itemId = "item_id"
        case state
        case size = "bytes"
        case readySize = "size"
        case needsTranscode = "needs_transcode"
    }
}

/// One row of `/api/library/items` — the debug trigger's only source of item ids.
struct OfflineCandidate: Decodable, Identifiable, Equatable {
    var itemId: String
    var title: String
    var year: Int?
    var type: String?

    var id: String { itemId }

    private enum CodingKeys: String, CodingKey {
        case title, year, type
        case itemId = "item_id"
    }
}

private struct LibraryItemsEnvelope: Decodable {
    var items: [OfflineCandidate]
}

/// What went wrong, in the vocabulary the decisions are written in.
enum OfflineAPIError: Error, LocalizedError {
    /// The server answered, and the status means something specific (`OfflineHTTPVerdict`).
    case remote(OfflineHTTPVerdict, detail: String?)
    /// The request never completed: offline, timed out, connection dropped.
    case transport(OfflineTransportFailure)
    /// A `200` whose body did not say what the contract says it says. ⚠ Its own case because it is a
    /// BUG (ours or the server's), not a condition to retry.
    case unexpectedBody(String)
    case notConfigured

    var failure: OfflineFailure {
        switch self {
        // ⚠ The detail is CARRIED, not discarded — see `OfflineFailure.http`. Dropping it here is what
        // made every 507 on his phone read "the download storage is full" whatever the server had said.
        case .remote(let verdict, let detail): return .http(verdict, detail: detail)
        case .transport(let transport): return .transport(transport)
        case .unexpectedBody(let detail): return .local("Unexpected answer from the server: \(detail)")
        case .notConfigured: return .local("No server address is set.")
        }
    }

    var errorDescription: String? { failure.sentence }
}

/// The four offline calls, plus the download request itself.
///
/// ⚠ Requests here go through ONE place (`send`) that builds the URL, attaches the mirrored cookie (or
/// reports that it could not), times the call and logs it through `RKMLog.request` — the single format
/// both halves of the app share. There is no second place where a header could carry a cookie value into
/// the log.
final class OfflineAPI {

    private let address: ServerAddress
    private let cookies: CookieMirror
    /// A plain foreground session for the small JSON calls and the `HEAD`. ⚠ The DOWNLOAD does not use
    /// it: that is `OfflineDownloads`' background session, for the reason it explains.
    private let session: URLSession

    init(address: ServerAddress, cookies: CookieMirror, session: URLSession? = nil) {
        self.address = address
        self.cookies = cookies
        if let session {
            self.session = session
        } else {
            let configuration = URLSessionConfiguration.ephemeral
            // ⚠ We attach the cookie ourselves; a session that ALSO attached its own would send two
            // Cookie headers' worth of confusion, and a background download can silently lose the ones
            // its own store holds (known WebKit/Foundation behaviour, see `CookieMirror`).
            configuration.httpShouldSetCookies = false
            configuration.httpCookieAcceptPolicy = .never
            configuration.httpCookieStorage = nil
            configuration.timeoutIntervalForRequest = 30
            self.session = URLSession(configuration: configuration)
        }
    }

    // MARK: - URLs

    func url(path: String, query: [URLQueryItem] = []) -> URL? {
        var components = URLComponents(url: address.url.appendingPathComponent(path),
                                       resolvingAgainstBaseURL: false)
        if !query.isEmpty { components?.queryItems = query }
        return components?.url
    }

    func fileURL(itemId: String, mode: String?) -> URL? {
        var query: [URLQueryItem] = []
        if let mode, !mode.isEmpty { query.append(URLQueryItem(name: "mode", value: mode)) }
        return url(path: "/api/offline/file/\(itemId)", query: query)
    }

    // MARK: - The calls

    func bundle(itemId: String, mode: String = "auto") async throws -> OfflineBundle {
        let request = try makeRequest(path: "/api/offline/bundle/\(itemId)",
                                      query: [URLQueryItem(name: "mode", value: mode)])
        let (data, response) = try await send(request, label: "bundle")
        try ensureSuccess(response, data: data)
        do {
            return try JSONDecoder().decode(OfflineBundle.self, from: data)
        } catch {
            throw OfflineAPIError.unexpectedBody("bundle: \(error)")
        }
    }

    /// ⚠ Idempotent server-side (B1's own gate proves it by counting upstream calls): a second call for a
    /// finished rendition returns it untouched.
    func prepare(itemId: String, mode: String = "auto") async throws -> OfflineServerManifest {
        var request = try makeRequest(path: "/api/offline/prepare", method: "POST")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: ["item_id": itemId, "mode": mode])
        let (data, response) = try await send(request, label: "prepare")
        try ensureSuccess(response, data: data)
        do {
            return try JSONDecoder().decode(OfflineServerManifest.self, from: data)
        } catch {
            throw OfflineAPIError.unexpectedBody("prepare: \(error)")
        }
    }

    func status(itemId: String, mode: String?) async throws -> OfflineServerManifest {
        var query: [URLQueryItem] = []
        if let mode, !mode.isEmpty { query.append(URLQueryItem(name: "mode", value: mode)) }
        let request = try makeRequest(path: "/api/offline/status/\(itemId)", query: query)
        let (data, response) = try await send(request, label: "status")
        try ensureSuccess(response, data: data)
        do {
            return try JSONDecoder().decode(OfflineServerManifest.self, from: data)
        } catch {
            throw OfflineAPIError.unexpectedBody("status: \(error)")
        }
    }

    /// The size and identity of the artefact — what a downloader asks **first**.
    ///
    /// ⚠ This is the route B1 added an EXPLICIT `@router.head` for, because a GET-only FastAPI route
    /// answers `HEAD` with **405** (measured) and a size probe would then fail silently exactly when the
    /// device had committed to a download. The strong ETag it returns is what makes a resume SAFE.
    func head(itemId: String, mode: String?) async throws -> OfflineRemoteArtefact {
        var query: [URLQueryItem] = []
        if let mode, !mode.isEmpty { query.append(URLQueryItem(name: "mode", value: mode)) }
        let request = try makeRequest(path: "/api/offline/file/\(itemId)", query: query, method: "HEAD")
        let (_, response) = try await send(request, label: "head")
        try ensureSuccess(response, data: Data())

        let http = response as? HTTPURLResponse
        let length = Self.contentLength(http)
        guard let length, length > 0 else {
            throw OfflineAPIError.unexpectedBody("HEAD reported no usable Content-Length")
        }
        return OfflineRemoteArtefact(size: Int64(length),
                                     etag: http?.value(forHTTPHeaderField: "ETag"),
                                     contentType: http?.value(forHTTPHeaderField: "Content-Type"))
    }

    /// ⚠ DEBUG-ONLY PURPOSE (phase B2 has no page affordances yet — those are B4): a source of item ids
    /// so a download can be started on the Mac without typing a GUID into a text field.
    func candidates(limit: Int = 12) async throws -> [OfflineCandidate] {
        let request = try makeRequest(path: "/api/library/items")
        let (data, response) = try await send(request, label: "library")
        try ensureSuccess(response, data: data)
        do {
            let envelope = try JSONDecoder().decode(LibraryItemsEnvelope.self, from: data)
            return Array(envelope.items.prefix(limit))
        } catch {
            throw OfflineAPIError.unexpectedBody("library items: \(error)")
        }
    }

    // MARK: - The download request

    /// The request a background download task is created from: mirror-cookie, `Range` if resuming, and
    /// the Wi-Fi-only preference applied to the *task* (see `OfflineDownloads`).
    func makeDownloadRequest(
        itemId: String,
        mode: String?,
        fromOffset: Int64,
        fileURL: URL
    ) throws -> URLRequest {
        var request = URLRequest(url: fileURL)
        request.httpMethod = "GET"
        request.cachePolicy = .reloadIgnoringLocalCacheData

        let outcome = cookies.headerOutcome(for: fileURL)
        if let header = outcome.header {
            request.setValue(header, forHTTPHeaderField: "Cookie")
        }
        if let range = OfflineRangeReport.requestHeader(fromOffset: fromOffset) {
            request.setValue(range, forHTTPHeaderField: "Range")
        }
        // ⚠ The cookie outcome is logged at START, once, not per response: it is the difference between
        // "the download 401'd" being a mystery and being a sentence.
        RKMLog.info("offline download request prepared · cookies \(outcome.summary)"
                    + (fromOffset > 0 ? " · resuming from \(OfflineFormat.bytes(fromOffset))" : " · from the start"),
                    category: .offline)
        return request
    }

    // MARK: - Plumbing

    /// ⚠ Not `URLSession.data(for:)` with a `HEAD`: that is fine, but the response for a HEAD has no body
    /// and Foundation still hands back empty `Data` — which is what `contentLength` reads instead.
    func makeRequest(path: String, query: [URLQueryItem] = [], method: String = "GET") throws -> URLRequest {
        var components = URLComponents(url: address.url.appendingPathComponent(path),
                                       resolvingAgainstBaseURL: false)
        if !query.isEmpty { components?.queryItems = query }
        guard let url = components?.url else {
            throw OfflineAPIError.unexpectedBody("could not build a URL for \(path)")
        }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.cachePolicy = .reloadIgnoringLocalCacheData
        let outcome = cookies.headerOutcome(for: url)
        if let header = outcome.header {
            request.setValue(header, forHTTPHeaderField: "Cookie")
        }
        return request
    }

    private func send(_ request: URLRequest, label: String) async throws -> (Data, URLResponse) {
        let identifier = CorrelationID.next()
        let started = Date()
        do {
            let (data, response) = try await session.data(for: request)
            let status = (response as? HTTPURLResponse)?.statusCode
            RKMLog.request(
                correlation: identifier,
                method: request.httpMethod ?? "GET",
                url: request.url?.absoluteString ?? label,
                status: status,
                milliseconds: Int(Date().timeIntervalSince(started) * 1000),
                bytes: data.count
            )
            return (data, response)
        } catch {
            let failure = Self.transportFailure(from: error)
            RKMLog.request(
                correlation: identifier,
                method: request.httpMethod ?? "GET",
                url: request.url?.absoluteString ?? label,
                status: nil,
                milliseconds: Int(Date().timeIntervalSince(started) * 1000),
                error: failure.sentence
            )
            throw OfflineAPIError.transport(failure)
        }
    }

    /// ⚠ The server's own words when it gives them (`{"detail": "…"}`) — B1's `409` says *"Still packaging
    /// (1234 B so far) — try again shortly"*, and that sentence is worth keeping.
    private func ensureSuccess(_ response: URLResponse, data: Data) throws {
        guard let http = response as? HTTPURLResponse else {
            throw OfflineAPIError.unexpectedBody("the response was not HTTP")
        }
        let verdict = OfflineHTTPVerdict.classify(http.statusCode)
        if case .success = verdict { return }
        throw OfflineAPIError.remote(verdict, detail: Self.detail(from: data))
    }

    static func detail(from data: Data) -> String? {
        guard let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let detail = object["detail"] as? String
        else { return nil }
        return detail
    }

    /// `HEAD` has no body, so `Content-Length` is a header here — and `HTTPURLResponse.expectedContentLength`
    /// is `-1` for a response Foundation did not read a body for.
    static func contentLength(_ response: HTTPURLResponse?) -> Int? {
        guard let raw = response?.value(forHTTPHeaderField: "Content-Length"),
              let value = Int(raw)
        else { return nil }
        return value
    }

    // MARK: - Failure mapping

    /// `NSError` → the transport vocabulary the rules are written against. ⚠ Mapped HERE, at the edge,
    /// so `OfflinePlan.swift` can stay Foundation-only and be tested on Linux.
    static func transportFailure(from error: Error) -> OfflineTransportFailure {
        let nsError = error as NSError
        guard nsError.domain == NSURLErrorDomain else {
            return .other("\(nsError.domain) \(nsError.code) — \(nsError.localizedDescription)")
        }
        switch nsError.code {
        case NSURLErrorCancelled:
            return .cancelled
        case NSURLErrorTimedOut:
            return .timedOut
        case NSURLErrorNetworkConnectionLost, NSURLErrorCannotConnectToHost, NSURLErrorCannotLoadFromNetwork:
            return .connectionLost
        case NSURLErrorNotConnectedToInternet, NSURLErrorCannotFindHost, NSURLErrorDNSLookupFailed,
             NSURLErrorDataNotAllowed, NSURLErrorInternationalRoamingOff, NSURLErrorCallIsActive:
            return .offline
        default:
            return .other("\(nsError.domain) \(nsError.code) — \(nsError.localizedDescription)")
        }
    }
}
