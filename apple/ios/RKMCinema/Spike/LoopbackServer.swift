import Foundation
// ⚠ `DispatchQueue` comes from **Dispatch**, not Foundation. On Darwin `import Foundation` happens to
// re-export it, so this compiles without the line — and that is exactly the kind of "happens to work"
// this project has already paid for twice (Combine and UIKit re-exports, both lost on the iOS 26 SDK).
// Spelled out so it cannot become the third.
import Dispatch
import Network
import RKMServerKit

/// ⚠ **SPIKE ONLY — experiment E1** (`docs/NATIVE_FEEL_AND_OFFLINE_PLAN.md` §5). Not to be merged.
///
/// A minimal HTTP/1.1 file server on **127.0.0.1**, on an OS-assigned port, serving one directory
/// with real `Range` support. It exists to answer the single question every offline design choice
/// hangs off: **does WebKit's media stack play from loopback, with seeking, inside this WKWebView?**
///
/// ⚠ `WKURLSchemeHandler` is NOT the safe answer and this build measures both: WebKit's media stack
/// runs in a separate process and does not route media through an app's scheme handler, so
/// `rkm-offline://` is expected to fail — but "expected to" is why the spike exists.
///
/// Not production: no auth, no manifest, no token, no staging TTL. `B1`–`B3` replace it.
final class LoopbackServer {

    private let root: URL
    private let queue = DispatchQueue(label: "rkm.spike.loopback")
    private var listener: NWListener?

    /// Every request line (with its `Range`, when it had one) — the evidence that a seek produced a
    /// **206** rather than a whole-file read. Kept here as well as logged, so the probe page can be
    /// cross-checked against what the server actually saw.
    private(set) var requests: [String] = []

    private(set) var port: UInt16 = 0

    init(root: URL) {
        self.root = root
    }

    func start(completion: @escaping (Result<UInt16, Error>) -> Void) {
        do {
            let parameters = NWParameters.tcp
            // ⚠ LOOPBACK ONLY. A spike has no business listening on the LAN, and the page always
            // asks 127.0.0.1, so restricting the interface costs nothing and removes the question.
            parameters.requiredInterfaceType = .loopback
            let listener = try NWListener(using: parameters, on: .any)
            listener.stateUpdateHandler = { [weak self] state in
                switch state {
                case .ready:
                    let assigned = listener.port?.rawValue ?? 0
                    self?.port = assigned
                    // ⚠ The ROOT is logged at start-up: when a request 404s, the first question is
                    // "which directory is it even looking in?", and last round it cost a whole Mac
                    // round to answer because the log never said.
                    if let root = self?.root.path {
                        RKMLog.info("loopback: serving files from \(root)", category: .net)
                    }
                    completion(.success(assigned))
                case .failed(let error):
                    completion(.failure(error))
                default:
                    break
                }
            }
            listener.newConnectionHandler = { [weak self] connection in
                self?.accept(connection)
            }
            self.listener = listener
            listener.start(queue: queue)
        } catch {
            completion(.failure(error))
        }
    }

    func stop() {
        listener?.cancel()
        listener = nil
    }

    // MARK: - One connection at a time (a probe asks one question at a time)

    private func accept(_ connection: NWConnection) {
        connection.start(queue: queue)
        receiveHeaders(on: connection, buffer: Data())
    }

    private func receiveHeaders(on connection: NWConnection, buffer: Data) {
        connection.receive(minimumIncompleteLength: 1, maximumLength: 64 * 1024) { [weak self] data, _, isComplete, error in
            guard let self else {
                connection.cancel()
                return
            }
            var buffer = buffer
            if let data { buffer.append(data) }
            if let error {
                RKMLog.verbose("loopback: receive failed — \(error)", category: .net)
                connection.cancel()
                return
            }
            if let separator = buffer.range(of: Data("\r\n\r\n".utf8)) {
                let head = String(decoding: buffer[..<separator.lowerBound], as: UTF8.self)
                self.respond(to: head, on: connection)
                return
            }
            if isComplete {
                connection.cancel()
                return
            }
            self.receiveHeaders(on: connection, buffer: buffer)
        }
    }

    private func respond(to head: String, on connection: NWConnection) {
        let lines = head.split(separator: "\r\n", omittingEmptySubsequences: false).map(String.init)
        let parts = (lines.first ?? "").split(separator: " ").map(String.init)
        let method = parts.count > 0 ? parts[0].uppercased() : "GET"
        let target = parts.count > 1 ? parts[1] : "/"
        let rangeHeader = lines.first { $0.lowercased().hasPrefix("range:") }

        let described = "\(method) \(target)\(rangeHeader.map { " · \($0)" } ?? "")"
        requests.append(described)
        // ⚠ Logged at INFO through the app's own logger, so the file carries the requests the page
        // made as well as the page's own report of what happened.
        RKMLog.info("loopback request: \(described)", category: .net)

        if target == "/" || target.hasPrefix("/probe.html") {
            send(status: "200 OK",
                 headers: ["Content-Type": "text/html; charset=utf-8"],
                 body: Data(OfflineSpike.probePage.utf8),
                 on: connection)
            return
        }

        guard let file = fileURL(for: target) else {
            RKMLog.info("loopback: no such file for \(target)", category: .net)
            send(status: "404 Not Found",
                 headers: ["Content-Type": "text/plain; charset=utf-8"],
                 body: Data("not found".utf8),
                 on: connection)
            return
        }
        serve(file: file, method: method, rangeHeader: rangeHeader, on: connection)
    }

    /// ⚠ Basename only: a spike still must not be talked into serving `/etc/hosts` by a request
    /// line. (The real server in `B3` gets a manifest and a token instead of this.)
    private func fileURL(for target: String) -> URL? {
        let path = target.split(separator: "?").first.map(String.init) ?? target
        let name = (path as NSString).lastPathComponent
        guard !name.isEmpty, name != "/", name != ".", name != ".." else { return nil }
        let url = root.appendingPathComponent(name)
        guard FileManager.default.fileExists(atPath: url.path) else { return nil }
        return url
    }

    private func serve(file url: URL, method: String, rangeHeader: String?, on connection: NWConnection) {
        guard let attributes = try? FileManager.default.attributesOfItem(atPath: url.path),
              let size = (attributes[.size] as? NSNumber)?.intValue, size > 0
        else {
            // ⚠ LOUD, because this is the failure that looks exactly like "WebKit refused the media":
            // the page reports `mediaError=code=4` either way, and only this line distinguishes
            // "no bytes were ever sent" from "bytes were sent and the codec was refused".
            RKMLog.error("loopback: cannot read \(url.path) — sending 404 (no media bytes sent at all)",
                         category: .net)
            send(status: "404 Not Found", headers: [:], body: Data(), on: connection)
            return
        }

        var start = 0
        var end = size - 1
        var status = "200 OK"
        if let requested = Self.parseRange(rangeHeader, size: size) {
            start = requested.start
            end = requested.end
            // ⚠ 206 is the whole point: it is what seeking needs. A 200 for a range request would
            // make the probe pass while proving nothing about `Range`.
            status = "206 Partial Content"
            RKMLog.info("loopback: serving \(status) bytes \(start)-\(end)/\(size)", category: .net)
        } else {
            RKMLog.info("loopback: serving \(status) whole file (\(size) B)", category: .net)
        }

        var headers = [
            "Content-Type": "video/mp4",
            "Content-Length": "\(end - start + 1)",
            "Accept-Ranges": "bytes",
        ]
        if status.hasPrefix("206") {
            headers["Content-Range"] = "bytes \(start)-\(end)/\(size)"
        }

        var text = "HTTP/1.1 \(status)\r\n"
        for (key, value) in headers.sorted(by: { $0.key < $1.key }) {
            text += "\(key): \(value)\r\n"
        }
        text += "Connection: close\r\n\r\n"

        connection.send(content: Data(text.utf8), completion: .contentProcessed { [weak self] error in
            guard error == nil, let self else {
                connection.cancel()
                return
            }
            // A HEAD asks for the size, not the bytes — the plan's own note: a size probe must not
            // pull the file down.
            guard method != "HEAD" else {
                connection.send(content: nil, isComplete: true, completion: .contentProcessed { _ in connection.cancel() })
                return
            }
            self.sendBody(url: url, offset: start, remaining: end - start + 1, on: connection)
        })
    }

    /// ⚠ RECURSIVE, NOT A LOOP WITH A SEMAPHORE — and that is not a style choice. `connection.send`'s
    /// completion handler is delivered on the connection's OWN serial queue, which is the queue this
    /// code runs on: blocking it waiting for its own completion is a deadlock, and it would look like
    /// "the probe hangs" rather than "the server deadlocked".
    private func sendBody(url: URL, offset: Int, remaining: Int, on connection: NWConnection) {
        guard remaining > 0 else {
            connection.send(content: nil, isComplete: true, completion: .contentProcessed { _ in connection.cancel() })
            return
        }
        let want = min(256 * 1024, remaining)
        let handle: FileHandle
        do {
            handle = try FileHandle(forReadingFrom: url)
        } catch {
            connection.cancel()
            return
        }
        defer { try? handle.close() }
        do {
            try handle.seek(toOffset: UInt64(offset))
        } catch {
            connection.cancel()
            return
        }
        let chunk: Data?
        do {
            chunk = try handle.read(upToCount: want)
        } catch {
            connection.cancel()
            return
        }
        guard let chunk, !chunk.isEmpty else {
            connection.send(content: nil, isComplete: true, completion: .contentProcessed { _ in connection.cancel() })
            return
        }
        connection.send(content: chunk, isComplete: false, completion: .contentProcessed { [weak self] error in
            guard error == nil else {
                connection.cancel()
                return
            }
            self?.sendBody(url: url, offset: offset + chunk.count, remaining: remaining - chunk.count, on: connection)
        })
    }

    private func send(status: String, headers: [String: String], body: Data, on connection: NWConnection) {
        var text = "HTTP/1.1 \(status)\r\n"
        var headers = headers
        headers["Content-Length"] = "\(body.count)"
        for (key, value) in headers.sorted(by: { $0.key < $1.key }) {
            text += "\(key): \(value)\r\n"
        }
        text += "Connection: close\r\n\r\n"
        var payload = Data(text.utf8)
        payload.append(body)
        connection.send(content: payload, completion: .contentProcessed { _ in connection.cancel() })
    }

    // MARK: - Range

    /// `bytes=start-end` / `bytes=start-` / `bytes=-suffix`. Anything else is served whole, which is
    /// what a server is allowed to do — and the log says which happened.
    static func parseRange(_ header: String?, size: Int) -> (start: Int, end: Int)? {
        guard let header, let equals = header.firstIndex(of: "=") else { return nil }
        let value = header[header.index(after: equals)...].trimmingCharacters(in: .whitespaces)
        guard let dash = value.firstIndex(of: "-") else { return nil }
        let startText = String(value[value.startIndex..<dash])
        let endText = String(value[value.index(after: dash)...])

        if startText.isEmpty {
            // A suffix range: the LAST n bytes.
            guard let suffix = Int(endText), suffix > 0 else { return nil }
            return (max(0, size - suffix), size - 1)
        }
        guard let start = Int(startText), start < size else { return nil }
        let end = Int(endText).map { min($0, size - 1) } ?? (size - 1)
        guard end >= start else { return nil }
        return (start, end)
    }
}
