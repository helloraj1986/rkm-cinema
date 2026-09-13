import Foundation
import RKMServerKit

/// Is this server actually there, before the shell commits to it?
///
/// ⚠ The rule that makes this useful: **any HTTP response counts as reachable.** A `401`, a
/// `404`, a `500` all prove something is answering at that address. Only a transport failure —
/// DNS, refused connection, timeout, TLS — means unreachable. Treating a `401` as unreachable
/// would send him hunting for a network fault when the honest answer is "the server is fine,
/// sign in".
enum ServerProbe {

    struct Outcome {
        let reachable: Bool
        let status: Int?
        let milliseconds: Int
        /// Ready to put on screen and in the log.
        let detail: String
    }

    /// `GET /api/status` — a real route on this backend (`backend/api/routes/status.py`), so a
    /// 200 also proves the API layer is up, not merely that something is listening on the port.
    static func check(_ address: ServerAddress, correlation: CorrelationID, timeout: TimeInterval = 8) async -> Outcome {
        let url = address.url.appendingPathComponent("api/status")
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.timeoutInterval = timeout
        request.cachePolicy = .reloadIgnoringLocalCacheData
        request.setValue("application/json", forHTTPHeaderField: "Accept")

        let started = Date()
        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            let elapsed = milliseconds(since: started)
            let status = (response as? HTTPURLResponse)?.statusCode
            RKMLog.request(correlation: correlation, method: "GET", url: url.path,
                           status: status, milliseconds: elapsed, bytes: data.count)
            let code = status.map(String.init) ?? "no status"
            return Outcome(reachable: true, status: status, milliseconds: elapsed,
                           detail: "The server answered (HTTP \(code)).")
        } catch {
            let elapsed = milliseconds(since: started)
            // The full NSError domain and code, because that pair *is* the diagnosis:
            // -1003 cannot find host, -1004 cannot connect, -1009 no network, -1202 TLS.
            let nsError = error as NSError
            let detail = "\(nsError.domain) \(nsError.code) — \(nsError.localizedDescription)"
            RKMLog.request(correlation: correlation, method: "GET", url: url.path,
                           milliseconds: elapsed, error: detail)
            return Outcome(reachable: false, status: nil, milliseconds: elapsed, detail: detail)
        }
    }

    private static func milliseconds(since start: Date) -> Int {
        Int(Date().timeIntervalSince(start) * 1000)
    }
}
