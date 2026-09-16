#if DEBUG
import Foundation
import Network
import WebKit
import RKMServerKit

// Phase B3's live probe — **DEBUG only, and it exists because the Mac is the only place this can run**.
//
// `docs/NATIVE_FEEL_AND_OFFLINE_PLAN.md` §6 states B3's gate as *the loopback server passes a Range test
// suite*. The suite's cases are data (`OfflineProbeCases`), executed against the PURE planner on Linux in
// `apple/scripts/check-offline-core.py`. This probe sends **the same composed heads** over a real loopback
// socket to a real `NWListener`, and adds the two things only a live run can show:
//
//   1. that the bytes on the wire are the file's bytes AT THE OFFSET ASKED FOR (a length check cannot tell
//      a correct range from a shifted one — the film would just be wrong from that point on);
//   2. that a real HTTP client (`URLSession`, the stack WebKit sits on) agrees about the same responses.
//
// ⚠ It runs against a **synthetic artefact it creates itself** (1 MiB of deterministic bytes, inside the
// offline root so it can never be backed up). That is deliberate: the suite fetches whole bodies, and
// fetching a 2 GB film to prove a Range works would be a terrible test. The one thing the synthetic file
// cannot prove — that the URL the BRIDGE mints for a real download works — is covered by a separate
// HEAD-only check against the real server (`real-film-head`), which reads the length without the body.
//
// Launch it with `-RKMOfflineServerProbe YES` (and `-RKMOfflineBridgeProbe YES` for the round-trip half).
// `tools/check_offline_server.py` reads the log this produces.

enum OfflineServerProbe {

    /// 1 MiB exactly: round in the log, and large enough that a range at 512 KiB is genuinely mid-file.
    static let artefactSize: Int64 = 1_048_576

    /// A FIXED token, so a log line from one run means the same thing in the next.
    static let artefactToken = "0123456789abcdef0123456789abcdef"

    private static var didStart = false

    static func serverProbeRequested(_ arguments: [String] = ProcessInfo.processInfo.arguments) -> Bool {
        flag("-RKMOfflineServerProbe", in: arguments)
    }

    static func bridgeProbeRequested(_ arguments: [String] = ProcessInfo.processInfo.arguments) -> Bool {
        flag("-RKMOfflineBridgeProbe", in: arguments)
    }

    private static func flag(_ name: String, in arguments: [String]) -> Bool {
        guard let index = arguments.firstIndex(of: name), arguments.count > index + 1 else { return false }
        let value = arguments[index + 1].lowercased()
        return value == "yes" || value == "1" || value == "true"
    }

    /// Called once, when the page has finished loading (the bridge half needs a live page).
    static func startIfRequested() {
        guard !didStart else { return }
        let wantServer = serverProbeRequested()
        let wantBridge = bridgeProbeRequested()
        guard wantServer || wantBridge else { return }
        didStart = true

        RKMLog.info("offline probe · starting (server=\(wantServer) bridge=\(wantBridge))", category: .offline)
        DispatchQueue.main.async {
            if wantServer { runSuite() }
            if wantBridge { installBridgeProbeListener() }
            // ⚠ The row summary is logged HERE as well as when part two fires, and the first one matters
            // most: if a title is on disk but its row says `downloading`, this is the only line that shows
            // it — and part two never fires, so a version that logged it only on success would be blind to
            // the exact bug that prompted it.
            logRowSummary()
            // ⚠ Part two needs a TITLE — see `rowsDidChange`. If one is already downloaded (a plain
            // relaunch) it runs now; otherwise it waits for the download to finish.
            rowsDidChange()
        }
    }

    private static var didAnnounce = false

    /// ⚠⚠ PART TWO, AND IT IS DELIBERATELY NOT AT PAGE LOAD.
    ///
    /// The real-film check and the announcement need a title the downloader knows about, and a film that a
    /// launch argument started arrives MINUTES after the page did. Running everything at page load is how
    /// the first Mac round reported `NOT EXERCISED` on a run that had downloaded perfectly well: 16/16 server
    /// cases green, both commands answered, and `count=0` for the events because there was nothing to
    /// announce. The bridge calls this from its own publish, so it fires the moment a title is playable.
    static func rowsDidChange() {
        // ⚠⚠ TWO GUARDS, AND THE FIRST ONE COST A ROUND (2026-09-16). A TITLE IS NOT ENOUGH: the app's rows
        // change during startup (a rebuilt container reconciles, a launch argument starts a download), which
        // happens BEFORE the page has finished loading. Firing here then means emitting into a web view that
        // has a socket and NO DOCUMENT — two `A JavaScript exception occurred` errors, a real-film check run
        // twice, and a probe that reported the failure of the page half it had not reached yet. `didStart` is
        // set by `startIfRequested`, i.e. by the page's own `didFinish`.
        guard didStart else { return }
        guard !didAnnounce else { return }
        guard serverProbeRequested() || bridgeProbeRequested() else { return }
        guard OfflineDownloads.shared.rows.contains(where: { $0.state.isPlayable }) else { return }
        didAnnounce = true

        DispatchQueue.main.async {
            logRowSummary()
            runRealFilmCheck { outcome in
                RKMLog.info("offline probe · \(outcome)", category: .offline)
            }
            if bridgeProbeRequested() {
                // ⚠ Re-announce through the PRODUCTION event path (nothing fabricated), then send the
                // `probe` event that makes the PAGE ask its own questions — one action, both directions.
                OfflineBridge.shared.forcePublishAll()
                OfflineBridge.shared.emitProbeEvent()
            }
        }
    }

    /// ⚠ What the app itself thinks each title's state is. It is the cheapest way to see the difference
    /// between "nothing downloaded" and "downloaded, and the row never changed" — the second of which is a
    /// real bug the log alone cannot show (the READY line is written by the same code that fails to refresh
    /// the row).
    private static func logRowSummary() {
        let rows = OfflineDownloads.shared.rows
        let ready = rows.filter { $0.state.isPlayable }.count
        let downloading = rows.filter { $0.state == .downloading }.count
        let failed = rows.filter { $0.state == .failed }.count
        RKMLog.info("offline probe · rows \(rows.count) total, \(ready) ready, \(downloading) downloading, "
                    + "\(failed) failed", category: .offline)
    }

    // MARK: - The artefact

    /// Writes the deterministic 1 MiB file. ⚠ It lives under the offline root (already excluded from
    /// backup) and is removed again at the end of the suite.
    private static func makeArtefact() -> (url: URL, size: Int64)? {
        guard let store = OfflineDownloads.shared.store else { return nil }
        let directory = store.layout.root.appendingPathComponent("probe", isDirectory: true)
        let url = directory.appendingPathComponent("probe.mp4")
        do {
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            try OfflineProbeBytes.data(count: artefactSize).write(to: url, options: .atomic)
            return (url, artefactSize)
        } catch {
            RKMLog.error("offline probe · could not write the probe artefact: \(error.localizedDescription)",
                         category: .offline)
            return nil
        }
    }

    // MARK: - The suite

    private static func runSuite() {
        guard let artefact = makeArtefact() else {
            RKMLog.error("offline probe case setup FAIL — the probe artefact could not be created",
                         category: .offline)
            return
        }

        let book = OfflineTokenBook()
        let entry = OfflineTokenBook.Entry(itemId: "probe", container: "mp4", fileExtension: "mp4")
        let token = book.token(for: entry) { artefactToken }
        let resource = OfflineServeResource(url: artefact.url, size: artefact.size, etag: "probe-1",
                                            contentType: "video/mp4")

        // ⚠ The resolver answers EXACTLY this one entry and nothing else, so the probe's own 404 case
        // (a well-formed token nobody minted) is honest rather than a resolver that happens to be strict.
        let server = OfflineServer(tokens: book) { asked in
            asked == entry ? resource : nil
        }

        server.start { result in
            DispatchQueue.main.async {
                switch result {
                case .failure(let error):
                    RKMLog.error("offline probe case setup FAIL — the probe server would not start: "
                                 + "\(error.localizedDescription)", category: .offline)
                    cleanUp(server: server, artefact: artefact.url)
                case .success(let port):
                    OfflineServerProbe.runCases(server: server, port: port, book: book, entry: entry,
                                                resource: resource, artefact: artefact.url)
                }
            }
        }
    }

    private static func runCases(server: OfflineServer, port: UInt16, book: OfflineTokenBook,
                                 entry: OfflineTokenBook.Entry, resource: OfflineServeResource,
                                 artefact: URL) {
        let cases = OfflineProbeCases.cases(size: resource.size)
        var index = 0
        var passed = 0
        var failures: [String] = []

        func next() {
            guard index < cases.count else {
                RKMLog.info("offline probe summary \(passed)/\(cases.count) cases passed", category: .offline)
                for failure in failures {
                    RKMLog.error("offline probe failure · \(failure)", category: .offline)
                }
                runRealFilmCheck { realOutcome in
                    RKMLog.info("offline probe · \(realOutcome)", category: .offline)
                    cleanUp(server: server, artefact: artefact)
                }
                return
            }
            let probeCase = cases[index]
            index += 1

            let head = probeCase.headBytes(token: OfflineServerProbe.artefactToken, fileExtension: "mp4",
                                           host: "127.0.0.1")
            // ⚠ The SAME pure decision path the server took, so the bytes can be checked against the offset
            // the plan says they came from.
            let plan = OfflineServerCore.plan(requestData: head, tokens: book) { asked in
                asked == entry ? resource : nil
            }

            OfflineProbeClient.fetch(port: port, head: head) { result in
                DispatchQueue.main.async {
                    finish(probeCase, result: result, plan: plan, port: port) { next() }
                }
            }
        }

        func finish(_ probeCase: OfflineProbeCase, result: Result<Data, OfflineProbeError>,
                    plan: OfflineHTTPPlan, port: UInt16, then next: @escaping () -> Void) {
            switch result {
            case .failure(let error):
                failures.append("\(probeCase.id): \(error.detail)")
                RKMLog.error("offline probe case \(probeCase.id) FAIL — \(error.detail)", category: .offline)
                next()

            case .success(let raw):
                let verdict = judge(probeCase, plan: plan, raw: raw)
                if verdict.isEmpty {
                    passed += 1
                    RKMLog.info("offline probe case \(probeCase.id) PASS", category: .offline)
                } else {
                    failures.append("\(probeCase.id): \(verdict)")
                    RKMLog.error("offline probe case \(probeCase.id) FAIL — \(verdict)", category: .offline)
                }

                guard probeCase.mirrorWithURLSession,
                      let url = URL(string: "http://127.0.0.1:\(port)"
                                    + probeCase.target.rawTarget(token: OfflineServerProbe.artefactToken,
                                                                 fileExtension: "mp4"))
                else {
                    next()
                    return
                }
                mirror(probeCase, url: url) { note in
                    if let note {
                        RKMLog.error("offline probe case \(probeCase.id)+urlsession FAIL — \(note)",
                                     category: .offline)
                    } else {
                        RKMLog.info("offline probe case \(probeCase.id)+urlsession PASS", category: .offline)
                    }
                    next()
                }
            }
        }

        next()
    }

    /// ⚠ Empty string means "it passed". Every check the case declared is enforced, INCLUDING the byte
    /// comparison — because a wrong offset returns the right NUMBER of bytes.
    private static func judge(_ probeCase: OfflineProbeCase, plan: OfflineHTTPPlan, raw: Data) -> String {
        guard case .head(let wire) = OfflineProbeWire.parseHead(raw) else {
            return "the response head could not be read"
        }
        if wire.status != probeCase.expectStatus {
            return "status \(wire.status), expected \(probeCase.expectStatus)"
        }
        if let expected = probeCase.expectContentLength, wire.contentLength != expected {
            return "Content-Length \(wire.contentLength.map(String.init) ?? "—"), expected \(expected)"
        }
        if let expected = probeCase.expectContentRange {
            if wire.header("content-range") != expected {
                return "Content-Range \(wire.header("content-range") ?? "—"), expected \(expected)"
            }
        } else if let unexpected = wire.header("content-range") {
            return "an unexpected Content-Range: \(unexpected)"
        }
        if Int64(wire.body.count) != probeCase.expectBodyBytes {
            return "\(wire.body.count) body bytes, expected \(probeCase.expectBodyBytes)"
        }

        if probeCase.expectBytesFromFile, !wire.body.isEmpty {
            let first = OfflineProbeBytes.byte(at: plan.offset)
            let last = OfflineProbeBytes.byte(at: plan.offset + Int64(wire.body.count) - 1)
            if wire.body[wire.body.startIndex] != first {
                return "the FIRST byte is not the file's byte at \(plan.offset) — a shifted range returns "
                     + "the right count and the wrong film"
            }
            if wire.body[wire.body.index(before: wire.body.endIndex)] != last {
                return "the LAST byte is not the file's byte at \(plan.offset + Int64(wire.body.count) - 1)"
            }
        }
        return ""
    }

    /// The same cases again, through a real HTTP client rather than our own hand-written request.
    private static func mirror(_ probeCase: OfflineProbeCase, url: URL,
                               completion: @escaping (String?) -> Void) {
        var request = URLRequest(url: url)
        request.httpMethod = probeCase.method
        request.setValue("close", forHTTPHeaderField: "Connection")
        if let range = probeCase.range { request.setValue(range, forHTTPHeaderField: "Range") }

        URLSession.shared.dataTask(with: request) { _, response, error in
            DispatchQueue.main.async {
                if let error {
                    completion("URLSession: \(error.localizedDescription)")
                    return
                }
                guard let http = response as? HTTPURLResponse else {
                    completion("URLSession: no HTTP response")
                    return
                }
                guard http.statusCode == probeCase.expectStatus else {
                    completion("URLSession status \(http.statusCode), expected \(probeCase.expectStatus)")
                    return
                }
                if let expected = probeCase.expectContentLength {
                    let declared = http.value(forHTTPHeaderField: "Content-Length").flatMap { Int64($0) }
                    if declared != expected {
                        completion("URLSession Content-Length \(declared.map(String.init) ?? "—"), "
                                   + "expected \(expected)")
                        return
                    }
                }
                completion(nil)
            }
        }.resume()
    }

    /// ⚠ The one check the synthetic file cannot make: does the URL the BRIDGE mints for a REAL download
    /// serve that download? HEAD only — the length and the headers, without fetching a film.
    private static func runRealFilmCheck(completion: @escaping (String) -> Void) {
        guard let row = OfflineDownloads.shared.rows.first(where: { $0.state.isPlayable }) else {
            completion("real-film-head NOT EXERCISED — no downloaded title on this device yet")
            return
        }
        OfflineBridge.shared.play(itemId: row.itemId) { reply in
            DispatchQueue.main.async {
                guard reply.ok, let target = reply.play else {
                    completion("real-film-head FAIL — \(reply.error?.errorDescription ?? "no reply")")
                    return
                }
                guard let url = URL(string: target.url) else {
                    completion("real-film-head FAIL — the bridge returned an unreadable URL")
                    return
                }
                var request = URLRequest(url: url)
                request.httpMethod = "HEAD"
                URLSession.shared.dataTask(with: request) { _, response, error in
                    DispatchQueue.main.async {
                        if let error {
                            completion("real-film-head FAIL — \(error.localizedDescription)")
                            return
                        }
                        guard let http = response as? HTTPURLResponse else {
                            completion("real-film-head FAIL — no HTTP response")
                            return
                        }
                        let declared = http.value(forHTTPHeaderField: "Content-Length").flatMap { Int64($0) }
                        if http.statusCode != 200 {
                            completion("real-film-head FAIL — status \(http.statusCode)")
                        } else if declared != target.size {
                            completion("real-film-head FAIL — the server says "
                                       + "\(declared.map(String.init) ?? "—") B, the manifest says "
                                       + "\(target.size) B")
                        } else {
                            completion("real-film-head PASS — \(target.size) B, \(target.contentType)")
                        }
                    }
                }.resume()
            }
        }
    }

    private static func cleanUp(server: OfflineServer, artefact: URL) {
        server.stop()
        try? FileManager.default.removeItem(at: artefact.deletingLastPathComponent())
        RKMLog.info("offline probe · finished (the probe artefact was removed)", category: .offline)
    }

    // MARK: - The bridge round trip

    /// ⚠ Both directions in one action, and neither half is faked: the page registers a real listener, the
    /// native side re-announces every REAL title through the production event path, and the page asks for
    /// `ping` and `list` and reports what it got back. The report rides the existing instrumentation channel
    /// (`WebBridge`), which is the only path that can prove the native→page direction at all.
    private static func installBridgeProbeListener() {
        guard let webView = OfflineBridge.shared.debugWebView else {
            RKMLog.error("offline bridge probe FAIL — no web view is attached to the bridge", category: .offline)
            return
        }

        // ⚠ The page asks ITS OWN questions when it sees `e: "probe"`, and that is deliberate: the ask must
        // travel the ONE path this phase has proved end to end (an event → the page's listener), not a
        // second `evaluateJavaScript` that ran into "A JavaScript exception occurred" on the first real round
        // while the event path worked in the same run. ⚠ A `probe` event emitted before this listener exists
        // is queued by the injected script and REPLAYED here, so "too early" cannot lose it either.
        let install = #"""
        (function () {
          var api = window.__rkmOffline;
          if (!api || !api.available) { window.__rkmOfflineReport('availability', {present: false}); return; }

          function report(command, answer) {
            window.__rkmOfflineReport('command', {cmd: command, ok: !!(answer && answer.ok),
                                                 count: (answer && answer.result && answer.result.count) || 0});
          }
          function failed(command, error) {
            window.__rkmOfflineReport('command', {cmd: command, ok: false,
                                                 detail: String((error && error.message) || error)});
          }
          function ask() {
            var ping = api.ping ? api.ping() : null;
            if (!ping) { failed('ping', new Error('this build has no ping() on __rkmOffline')); }
            else { ping.then(function (r) { report('ping', r); }, function (e) { failed('ping', e); }); }

            var list = api.list ? api.list() : null;
            if (!list) { failed('list', new Error('this build has no list() on __rkmOffline')); }
            else { list.then(function (r) { report('list', r); }, function (e) { failed('list', e); }); }
          }

          api.on(function (event) {
            window.__rkmOfflineReport('page-received', window.__rkmOfflineSummary(event));
            if (event && event.e === 'probe') { ask(); }
          });
          window.__rkmOfflineReport('availability', {present: true, version: api.version});
        })();
        """#

        webView.evaluateJavaScript(install) { _, error in
            if let error {
                RKMLog.error("offline bridge probe FAIL — the page would not install the listener: "
                             + describe(error), category: .offline)
            }
        }
    }

    /// ⚠ An `evaluateJavaScript` failure is a JavaScript EXCEPTION, and `localizedDescription` says only
    /// that one occurred. The message, the line and the source URL live in the error's `userInfo` — and
    /// without them the first real round's failure was unreadable (2026-09-16).
    static func describe(_ error: Error) -> String {
        let nsError = error as NSError
        let detail = nsError.userInfo
            .map { "\($0.key)=\($0.value)" }
            .sorted()
            .joined(separator: " · ")
        return "\(nsError.domain) \(nsError.code) — \(nsError.localizedDescription)"
             + (detail.isEmpty ? "" : " · \(detail)")
    }
}

/// ⚠ A tiny raw HTTP/1.1 client: it sends the case's composed head **verbatim**, so what the Mac sends is
/// byte-for-byte what the Linux gate planned against. `URLSession` cannot send a proxy-style target or a
/// duplicated header, and it normalises paths — which is precisely how a traversal case would be "tested"
/// into passing.
/// ⚠ Not a `String`: `Result`'s failure type must conform to `Error`, and a bare `String` does not — a real
/// error the Linux typecheck caught before the Mac did.
private struct OfflineProbeError: Error, LocalizedError {
    var detail: String
    var errorDescription: String? { detail }
}

private enum OfflineProbeClient {

    static func fetch(port: UInt16, head: Data, timeout: TimeInterval = 15,
                      completion: @escaping (Result<Data, OfflineProbeError>) -> Void) {
        let queue = DispatchQueue(label: "rkm.offline.probe.client")
        let socket = NWConnection(host: .ipv4(.loopback),
                                  port: NWEndpoint.Port(rawValue: port) ?? .any,
                                  using: .tcp)
        let deadline = Date().addingTimeInterval(timeout)
        var answered = false

        func finish(_ result: Result<Data, OfflineProbeError>) {
            guard !answered else { return }
            answered = true
            socket.cancel()
            completion(result)
        }

        /// ⚠ "Enough" is decided from the response's OWN Content-Length, so a truncated body is a finding
        /// rather than a pass — the same trap every Range check exists to avoid.
        func complete(_ buffer: Data) -> Data? {
            guard case .head(let wire) = OfflineProbeWire.parseHead(buffer) else { return nil }
            let promised = Int(wire.contentLength ?? 0)
            return wire.body.count >= promised ? buffer : nil
        }

        func receive(buffer: Data) {
            guard !answered else { return }
            if Date() > deadline {
                finish(.failure(OfflineProbeError(
                    detail: "the probe timed out after \(Int(timeout))s with \(buffer.count) B received")))
                return
            }
            socket.receive(minimumIncompleteLength: 1, maximumLength: 1 << 16) { data, _, isComplete, error in
                if let error {
                    finish(.failure(OfflineProbeError(
                        detail: "the probe could not read: \(error.localizedDescription)")))
                    return
                }
                var buffer = buffer
                if let data, !data.isEmpty { buffer.append(data) }
                if let done = complete(buffer) {
                    finish(.success(done))
                    return
                }
                if isComplete {
                    // The server closes when its body is done, so a short read is a real finding: the head
                    // arrived but not everything it promised.
                    finish(buffer.isEmpty
                           ? .failure(OfflineProbeError(detail: "the connection closed with nothing received"))
                           : .success(buffer))
                    return
                }
                receive(buffer: buffer)
            }
        }

        socket.stateUpdateHandler = { state in
            switch state {
            case .ready:
                socket.send(content: head, completion: .contentProcessed { error in
                    if let error {
                        finish(.failure(OfflineProbeError(
                            detail: "the probe could not send its head: \(error.localizedDescription)")))
                        return
                    }
                    receive(buffer: Data())
                })
            case .failed(let error):
                finish(.failure(OfflineProbeError(
                    detail: "the probe socket failed: \(error.localizedDescription)")))
            default:
                break
            }
        }

        socket.start(queue: queue)
    }
}
#endif
