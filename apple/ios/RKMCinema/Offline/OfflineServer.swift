import Foundation
import Network
import RKMServerKit

// Phase B3, the Mac-only half: the **loopback HTTP server** a downloaded film is played from.
//
// ⚠⚠ THIS FILE DECIDES NOTHING. Every status code, every byte range, every refusal, the whole response
// head and even the log line come from `OfflineServerCore` in `OfflineHTTP.swift` — pure Foundation, run
// and falsified on Linux. What is left here is the part that cannot exist without the SDK: an `NWListener`
// bound to loopback, a byte accumulator, and a `FileHandle` streamed out in chunks.
//
// The reason for the split is in `apple/WORKFLOW.md` §5 and it is not stylistic: nothing in this file can
// be *executed* until a handover round on the Mac, so the less it decides, the less there is to get wrong
// in the one place a mistake costs a round trip.
//
// ⚠ **Loopback only, and that is enforced by the listener's own endpoint** (`requiredLocalEndpoint`), not
// by a check inside a handler: a server that reads films off the user's device must not be reachable from
// the tailnet, and "we check the peer address" is a second thing that can be wrong.
//
// ⚠ The routes are tokens minted for this process (`OfflineTokenBook`), and a token resolves to a file
// only through the closure this server is given — so there is no client-supplied path anywhere in the
// chain, by construction.

enum OfflineServerError: LocalizedError, Equatable {
    case alreadyRunning(port: UInt16)
    case couldNotStart(reason: String)
    case noPort

    var errorDescription: String? {
        switch self {
        case .alreadyRunning(let port): return "The offline server is already listening on port \(port)."
        case .couldNotStart(let reason): return "The offline server could not start: \(reason)"
        case .noPort: return "The offline server started but did not report a port."
        }
    }
}

final class OfflineServer {

    // MARK: - Wiring

    /// ⚠ One connection's whole life: the socket, the bytes read so far, and whether we have already
    /// answered. The buffer is capped (`OfflineHTTPLimits.maximumHeadBytes`) — a local page that sends an
    /// endless head must not be able to grow the app's memory.
    private final class Connection {
        let socket: NWConnection
        var buffer = Data()
        var answered = false
        let identifier = UUID()

        init(socket: NWConnection) { self.socket = socket }
    }

    private let tokens: OfflineTokenBook
    private let resolve: (OfflineTokenBook.Entry) -> OfflineServeResource?
    private let queue = DispatchQueue(label: "rkm.offline.loopback")

    private var listener: NWListener?
    private var connections: [UUID: Connection] = [:]
    private var pendingStart: [(Result<UInt16, Error>) -> Void] = []

    /// ⚠ The port lives on the server's own queue; this accessor is the synchronized way to ask for it
    /// from the main thread (the HUD, the bridge, the probe). Never read it from inside a queue callback —
    /// `queue.sync` from the queue itself would deadlock, which is why the callbacks below all use
    /// `storedPort` directly.
    var port: UInt16? { queue.sync { storedPort } }

    private var storedPort: UInt16?

    var isListening: Bool { listener != nil && port != nil }

    init(tokens: OfflineTokenBook,
         resolve: @escaping (OfflineTokenBook.Entry) -> OfflineServeResource?) {
        self.tokens = tokens
        self.resolve = resolve
    }

    // MARK: - Lifecycle

    /// Starts the listener and reports the port the system assigned.
    ///
    /// ⚠ The port is **ephemeral on purpose** (`NWEndpoint.Port.any`): a fixed port can be occupied by
    /// something else on the device, and the page is told the real one over the bridge — which is also why
    /// no URL is ever written to disk (a URL cached across launches is a stale port).
    func start(completion: @escaping (Result<UInt16, Error>) -> Void) {
        if let port {
            completion(.failure(OfflineServerError.alreadyRunning(port: port)))
            return
        }
        pendingStart.append(completion)
        // ⚠ A SECOND `start()` WHILE THE FIRST IS STILL COMING UP IS NOT A SECOND LISTENER. `ensureServer`
        // is called from a publish that can fire several times before the port exists, and without this
        // guard each call would build another `NWListener` on another port — the page would be handed a URL
        // pointing at a socket nobody is reading.
        guard listener == nil else { return }

        let parameters = NWParameters.tcp
        parameters.allowLocalEndpointReuse = true
        // ⚠ The one line that keeps this off the network the phone is on.
        parameters.requiredLocalEndpoint = .hostPort(host: .ipv4(.loopback), port: .any)

        let listener: NWListener
        do {
            listener = try NWListener(using: parameters)
        } catch {
            RKMLog.error("offline server could not be created: \(error.localizedDescription)",
                         category: .offline)
            completion(.failure(OfflineServerError.couldNotStart(reason: error.localizedDescription)))
            return
        }

        self.listener = listener

        listener.stateUpdateHandler = { [weak self] state in
            guard let self else { return }
            switch state {
            case .ready:
                let raw = listener.port?.rawValue ?? 0
                guard raw > 0 else {
                    self.failStart(OfflineServerError.noPort)
                    return
                }
                self.storedPort = raw
                RKMLog.info("offline server listening on 127.0.0.1:\(raw) (loopback only)",
                            category: .offline)
                self.drainStart(.success(raw))
            case .failed(let error):
                RKMLog.error("offline server failed: \(error.localizedDescription)", category: .offline)
                self.failStart(OfflineServerError.couldNotStart(reason: error.localizedDescription))
            case .cancelled:
                RKMLog.info("offline server stopped", category: .offline)
                self.storedPort = nil
            default:
                break
            }
        }

        listener.newConnectionHandler = { [weak self] socket in
            self?.accept(socket)
        }

        listener.start(queue: queue)
    }

    private func drainStart(_ result: Result<UInt16, Error>) {
        let waiting = pendingStart
        pendingStart.removeAll()
        for completion in waiting { completion(result) }
    }

    private func failStart(_ error: Error) {
        listener?.cancel()
        listener = nil
        storedPort = nil
        drainStart(.failure(error))
    }

    func stop() {
        queue.async { [weak self] in
            guard let self else { return }
            for connection in self.connections.values {
                connection.socket.cancel()
            }
            self.connections.removeAll()
            self.listener?.cancel()
            self.listener = nil
            self.storedPort = nil
        }
    }

    // MARK: - Accepting

    private func accept(_ socket: NWConnection) {
        let connection = Connection(socket: socket)
        connections[connection.identifier] = connection

        socket.stateUpdateHandler = { [weak self] state in
            switch state {
            case .failed(let error):
                RKMLog.verbose("offline connection failed: \(error.localizedDescription)", category: .offline)
                self?.close(connection)
            case .cancelled:
                self?.close(connection)
            default:
                break
            }
        }
        socket.start(queue: queue)
        receive(connection)
    }

    /// Read until the head is complete. ⚠ `isComplete`/`error` mean the peer is done — a half-sent head is
    /// a refusal with a reason, not an invitation to keep waiting (which would leak the connection).
    private func receive(_ connection: Connection) {
        connection.socket.receive(minimumIncompleteLength: 1, maximumLength: 4096) {
            [weak self] data, _, isComplete, error in
            guard let self else { return }
            guard !connection.answered else { return }

            if let data, !data.isEmpty {
                connection.buffer.append(data)
            }

            if connection.buffer.count > OfflineHTTPLimits.maximumHeadBytes {
                // ⚠ The buffer is capped as we read, so it can never grow past the limit — and the answer
                // (431, and the sentence explaining it) still comes from the pure layer, which is why this
                // goes through `plan` rather than deciding a status here.
                self.respond(OfflineServerCore.plan(requestData: connection.buffer,
                                                    tokens: self.tokens,
                                                    resolve: self.resolve),
                             on: connection)
                return
            }

            switch OfflineHTTPRequest.readHead(connection.buffer) {
            case .needMore:
                if isComplete || error != nil {
                    self.respond(OfflineServerCore.plan(requestData: connection.buffer,
                                                        tokens: self.tokens,
                                                        resolve: self.resolve),
                                 on: connection)
                } else {
                    self.receive(connection)
                }
            case .head, .refused:
                self.respond(OfflineServerCore.plan(requestData: connection.buffer,
                                                    tokens: self.tokens,
                                                    resolve: self.resolve),
                             on: connection)
            }
        }
    }

    // MARK: - Answering

    private func respond(_ plan: OfflineHTTPPlan, on connection: Connection) {
        guard !connection.answered else { return }
        connection.answered = true

        // ⚠ The log line is built by the pure layer, so the format `tools/check_offline_server.py` greps is
        // pinned by a Linux check rather than by a comment.
        RKMLog.info(plan.logLine, category: .offline)

        connection.socket.send(content: plan.response.headBytes, completion: .contentProcessed {
            [weak self] error in
            guard let self else { return }
            if let error {
                RKMLog.verbose("offline send (head) failed: \(error.localizedDescription)", category: .offline)
                self.close(connection)
                return
            }
            self.sendBody(plan, on: connection)
        })
    }

    private func sendBody(_ plan: OfflineHTTPPlan, on connection: Connection) {
        guard let fileURL = plan.fileURL, plan.length > 0 else {
            close(connection)
            return
        }
        guard let handle = FileHandle(forReadingAtPath: fileURL.path) else {
            // ⚠ The plan was made from a resource the resolver said was there. If it has gone since, the
            // client gets a short body and the log says exactly why — never a silent stall.
            RKMLog.error("offline server could not open the artefact for reading", category: .offline)
            close(connection)
            return
        }
        do {
            try handle.seek(toOffset: UInt64(plan.offset))
        } catch {
            RKMLog.error("offline server could not seek to \(plan.offset): \(error.localizedDescription)",
                         category: .offline)
            close(connection)
            return
        }
        sendChunk(handle, remaining: plan.length, on: connection)
    }

    /// ⚠ One chunk at a time, each one waiting for the previous `send` to complete. This is what keeps the
    /// app's memory flat while a 2 GB film goes out: at most `bodyChunkBytes` is in flight, however large
    /// the file is. `Data(contentsOf:)` here would be a memory kill on a phone.
    private func sendChunk(_ handle: FileHandle, remaining: Int64, on connection: Connection) {
        guard remaining > 0 else {
            close(handle)
            close(connection)
            return
        }
        let wanted = Int(min(Int64(OfflineHTTPLimits.bodyChunkBytes), remaining))
        let block = handle.readData(ofLength: wanted)
        guard !block.isEmpty else {
            // ⚠ The file shrank underneath us (a delete, or a reconcile that discarded a mismatched copy).
            // Sending nothing more is honest: the client sees a short body rather than a stall.
            RKMLog.error("offline server: the artefact ended early with \(remaining) B still promised",
                         category: .offline)
            close(handle)
            close(connection)
            return
        }

        let isLast = Int64(block.count) >= remaining
        connection.socket.send(content: block, contentContext: .defaultMessage,
                               isComplete: isLast, completion: .contentProcessed { [weak self] error in
            guard let self else { return }
            if let error {
                RKMLog.verbose("offline send (body) failed: \(error.localizedDescription)", category: .offline)
                self.close(handle)
                self.close(connection)
                return
            }
            if isLast {
                self.close(handle)
                self.close(connection)
            } else {
                self.sendChunk(handle, remaining: remaining - Int64(block.count), on: connection)
            }
        })
    }

    private func close(_ handle: FileHandle) {
        try? handle.close()
    }

    /// ⚠ Cancels the socket and forgets it. Every path above ends here, so a connection can never be
    /// answered twice or linger in the map.
    private func close(_ connection: Connection) {
        connections.removeValue(forKey: connection.identifier)
        connection.socket.cancel()
    }
}
