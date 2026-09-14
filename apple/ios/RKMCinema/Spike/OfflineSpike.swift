import Foundation
// ⚠ Dispatch, explicitly — see the same note in `Spike/LoopbackServer.swift`.
import Dispatch
import SwiftUI
// ⚠ `ObservableObject`/`@Published` are Combine, not SwiftUI — see `AppModel.swift`. SwiftUI no
// longer re-exports it on the iOS 26 SDK, and the failure reads as a protocol conformance error.
import Combine
import WebKit
import RKMServerKit

/// ⚠⚠ **SPIKE ONLY — B0 of `docs/NATIVE_FEEL_AND_OFFLINE_PLAN.md` §5. NOT TO BE MERGED.**
///
/// It answers the two experiments that decide whether the offline-downloads design is the one in the
/// plan, and it answers them **on a device, by measurement**, because both are questions about
/// WebKit's behaviour that no amount of reading settles:
///
/// * **E1 — does media play from a loopback HTTP server inside this WKWebView, with seeking?** One
///   downloaded file, served by `LoopbackServer` on 127.0.0.1, loaded into a `<video>` **inside a
///   WKWebView** (page and media on the same loopback origin, which is the architecture the plan
///   proposes). The same file is then asked for through `rkm-offline://`, a `WKURLSchemeHandler`,
///   which the plan *expects* to fail. Whichever works, plus whether a seek produced a `206`, is the
///   answer — and it is the difference between a three-day job and a different design entirely.
/// * **E2 — is a service worker available at all?** (`WebInstrumentation` logs `[rkm-caps]` on the
///   app's own page.) If not, A0's cache headers ARE the offline-shell story and no service-worker
///   work is planned.
///
/// **How to run it (Mac, simulator or device)** — full instructions in `apple/SPIKE_E1_E2.md`:
/// `./apple/scripts/mac-round.sh ios --sim` and launch with `-RKMOfflineSpike YES`.
///
/// ⚠ It needs the app to have a **stored server address**, because the probe file is downloaded from
/// his own server: the spike deliberately commits no binary, and `harness-sample.mp4` is already
/// served there (measured 2026-09-14: `200`, 1,128,375 B).
enum OfflineSpike {

    /// The key a `UserDefaults` argument sets to open the spike at launch. Nothing else in the app
    /// changes behaviour without it — the spike is opt-in and cannot leak into normal use.
    static let launchKey = "RKMOfflineSpike"

    /// The file the server serves, fetched from his own stack once.
    static let assetName = "harness-sample.mp4"

    static var startsAtLaunch: Bool {
        UserDefaults.standard.bool(forKey: launchKey)
    }

    /// `Application Support/Spike/` — ⚠ **not** `Caches/`. iOS may purge `Caches/` under storage
    /// pressure, and the whole point of this directory (and of the real feature) is that a file the
    /// user asked for does not vanish. Backup-excluded so a multi-GB film never rides into iCloud.
    static func directory() throws -> URL {
        let base = try FileManager.default.url(for: .applicationSupportDirectory,
                                              in: .userDomainMask,
                                              appropriateFor: nil,
                                              create: true)
        var directory = base.appendingPathComponent("Spike", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        var values = URLResourceValues()
        values.isExcludedFromBackup = true
        try directory.setResourceValues(values)
        return directory
    }

    /// The probe page. Served BY the loopback server, so the page and the media share one origin —
    /// which is exactly how the real offline player would work, and is why a `file://` page was
    /// rejected in the plan (§4.1): a `file://` page's subresources are cross-origin and blocked.
    static let probePage: String = #"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
<title>RKM — E1 loopback probe</title>
<style>
  body { background:#08090b; color:#e5e7eb; font:14px/1.45 -apple-system, system-ui; margin:0; padding:16px; }
  video { width:100%; max-height:45vh; background:#000; border-radius:8px; }
  pre { white-space:pre-wrap; font-size:12px; color:#9ca3af; }
</style>
</head>
<body>
<h1 style="font-size:15px">E1 — loopback media probe</h1>
<video id="v" playsinline muted controls></video>
<pre id="out"></pre>
<script>
(function () {
  'use strict';
  var out = document.getElementById('out');
  var video = document.getElementById('v');

  // ⚠ Everything is logged through `console.log`, which the shell's own instrumentation already
  // forwards into `rkm-ios.log` at verbose level. No second bridge path was added for the spike:
  // one event route means the log file is the single place the answer lives.
  function log(message) {
    var line = '[spike] ' + message;
    try { console.log(line); } catch (e) {}
    out.textContent += message + '\n';
  }

  function caps() {
    var probe = document.createElement('video');
    var facts = ['origin=' + location.origin,
                 'canPlayType(mp4)=' + JSON.stringify(probe.canPlayType('video/mp4')),
                 'h264+aac=' + JSON.stringify(probe.canPlayType('video/mp4; codecs="avc1.42E01E, mp4a.40.2"'))];
    log('caps ' + facts.join(' '));
  }

  function mediaError() {
    var error = video.error;
    if (!error) { return 'none'; }
    return 'code=' + error.code + ' message=' + (error.message || '');
  }

  function waitFor(event, ms) {
    return new Promise(function (resolve) {
      var done = false;
      var timer = setTimeout(function () { if (!done) { done = true; cleanup(); resolve('TIMEOUT'); } }, ms);
      function cleanup() { clearTimeout(timer); video.removeEventListener(event, onEvent); }
      function onEvent() { if (done) { return; } done = true; cleanup(); resolve('ok'); }
      video.addEventListener(event, onEvent);
    });
  }

  async function attempt(label, src) {
    log(label + ' loading ' + src);
    try { video.pause(); } catch (e) {}
    video.removeAttribute('src');
    video.load();
    video.src = src;
    video.load();

    var loaded = await waitFor('loadedmetadata', 12000);
    if (loaded !== 'ok') {
      log(label + ' RESULT loadedmetadata=' + loaded + ' mediaError=' + mediaError());
      return;
    }
    var duration = video.duration;
    log(label + ' metadata ok ' + video.videoWidth + 'x' + video.videoHeight
        + ' duration=' + (duration && isFinite(duration) ? duration.toFixed(2) : 'n/a'));

    // ⚠ THE SEEK IS THE REAL QUESTION. A file can "play" from a bad transport and still be unable
    // to seek — and seeking is what the whole offline player depends on (`Range` → 206).
    if (duration && isFinite(duration) && duration > 1) {
      var target = duration / 2;
      video.currentTime = target;
      var seeked = await waitFor('seeked', 8000);
      log(label + ' seek to ' + target.toFixed(2) + ' -> ' + seeked
          + (seeked === 'ok' ? ' at ' + video.currentTime.toFixed(2) : ''));
    }

    var playing = 'not attempted';
    try {
      var promise = video.play();
      if (promise && promise.catch) { promise.catch(function (e) { log(label + ' play() rejected: ' + e); }); }
      playing = await waitFor('playing', 8000);
    } catch (e) {
      playing = 'threw ' + e;
    }
    log(label + ' RESULT play=' + playing + ' mediaError=' + mediaError());
    try { video.pause(); } catch (e) {}
  }

  async function run() {
    log('probe start ua=' + navigator.userAgent);
    caps();
    // 1. loopback HTTP (relative URL → the SAME origin that served this page)
    await attempt('[loopback]', 'probe.mp4');
    // 2. the scheme handler the plan expects to fail — measured, not assumed
    await attempt('[scheme]', 'rkm-offline://probe.mp4');
    log('probe done — compare the two RESULT lines above');
  }

  run();
})();
</script>
</body>
</html>
"""#
}

/// Owns the probe: the file, the server, the web view, and the state the screen shows.
final class OfflineSpikeModel: ObservableObject {

    @Published private(set) var status = "starting…"
    @Published private(set) var detail = ""
    @Published private(set) var port: UInt16 = 0
    @Published private(set) var assetBytes = 0

    /// ⚠ One web view, created up front: `setURLSchemeHandler` must be configured **before** the
    /// view exists, and the probe loads into this one.
    let webView: WKWebView

    private let address: ServerAddress?
    private var server: LoopbackServer?

    init(address: ServerAddress?) {
        self.address = address

        let configuration = WKWebViewConfiguration()
        // The same two non-negotiables as the real shell (`WebShellView`), or the probe would be
        // measuring a different web view than the app runs.
        configuration.allowsInlineMediaPlayback = true
        configuration.preferences.isElementFullscreenEnabled = true
        configuration.websiteDataStore = .default()

        let controller = configuration.userContentController
        // ⚠ The real bridge + the real instrumentation: that is what puts `[spike]` lines in
        // `rkm-ios.log` with no second logging path.
        controller.add(WebBridge(), name: WebInstrumentation.handlerName)
        controller.addUserScript(WebInstrumentation.userScript())

        let handler = SpikeSchemeHandler(root: (try? OfflineSpike.directory()) ?? URL(fileURLWithPath: NSTemporaryDirectory()))
        configuration.setURLSchemeHandler(handler, forURLScheme: SpikeSchemeHandler.scheme)

        let webView = WKWebView(frame: .zero, configuration: configuration)
        if #available(iOS 16.4, *) {
            webView.isInspectable = true
        }
        self.webView = webView
    }

    func start() {
        guard server == nil else { return }
        RKMLog.info("offline spike: starting (E1 loopback + E2 caps)", category: .app)
        ensureAsset { [weak self] result in
            guard let self else { return }
            switch result {
            case .failure(let message):
                // ⚠ Loud and specific, because this is the failure that would otherwise read as
                // "the spike is broken": the asset comes from his own server.
                self.status = "probe file unavailable"
                self.detail = message
                RKMLog.error("offline spike: \(message)", category: .app)
            case .success(let url):
                self.startServer(root: url.deletingLastPathComponent())
            }
        }
    }

    /// Download `harness-sample.mp4` from the app's own server once. No binary is committed: the
    /// plan's own file is already served there, and a spike should not add weight to the repo.
    private func ensureAsset(completion: @escaping (Result<URL, String>) -> Void) {
        let file: URL
        do {
            file = try OfflineSpike.directory().appendingPathComponent(OfflineSpike.assetName)
        } catch {
            completion(.failure("could not create the spike directory: \(error.localizedDescription)"))
            return
        }
        if let size = (try? FileManager.default.attributesOfItem(atPath: file.path))?[.size] as? NSNumber,
           size.intValue > 0 {
            assetBytes = size.intValue
            status = "probe file ready"
            detail = "\(OfflineSpike.assetName) — \(size.intValue) B (already downloaded)"
            completion(.success(file))
            return
        }
        guard let address else {
            completion(.failure("no stored server address — connect to the server once, then relaunch with "
                                + "-\(OfflineSpike.launchKey) YES"))
            return
        }
        let remote = address.url.appendingPathComponent(OfflineSpike.assetName)
        status = "downloading probe file…"
        detail = remote.absoluteString
        RKMLog.info("offline spike: downloading \(remote.absoluteString)", category: .net)

        URLSession.shared.dataTask(with: remote) { [weak self] data, response, error in
            // ⚠ Named `httpStatus`, not `status`: the obvious name shadows the @Published property
            // above, and a shadowed assignment in this closure would silently update the wrong thing.
            let httpStatus = (response as? HTTPURLResponse)?.statusCode ?? 0
            guard let data, error == nil, httpStatus == 200 else {
                let reason = error?.localizedDescription ?? "HTTP \(httpStatus)"
                DispatchQueue.main.async {
                    completion(.failure("GET \(remote.absoluteString) failed — \(reason). "
                                        + "Put any small .mp4 at that path on the server and relaunch."))
                }
                return
            }
            do {
                try data.write(to: file, options: .atomic)
            } catch {
                DispatchQueue.main.async { completion(.failure("could not write the probe file: \(error.localizedDescription)")) }
                return
            }
            DispatchQueue.main.async {
                self?.assetBytes = data.count
                self?.status = "probe file ready"
                self?.detail = "\(OfflineSpike.assetName) — \(data.count) B (downloaded)"
                RKMLog.info("offline spike: probe file \(data.count) B", category: .net)
                completion(.success(file))
            }
        }.resume()
    }

    private func startServer(root: URL) {
        let server = LoopbackServer(root: root)
        self.server = server
        server.start { [weak self] result in
            guard let self else { return }
            switch result {
            case .failure(let error):
                self.status = "loopback server failed"
                self.detail = error.localizedDescription
                RKMLog.error("offline spike: loopback server failed — \(error)", category: .net)
            case .success(let port):
                self.port = port
                self.status = "serving on 127.0.0.1:\(port)"
                self.detail = "loading the probe page…"
                RKMLog.info("offline spike: loopback server ready on 127.0.0.1:\(port)", category: .net)
                let url = URL(string: "http://127.0.0.1:\(port)/probe.html")
                if let url {
                    self.webView.load(URLRequest(url: url))
                } else {
                    self.detail = "could not build the probe URL"
                }
            }
        }
    }
}

/// The screen: what the probe is doing, and the web view doing it (so it can be photographed too).
struct OfflineSpikeView: View {

    @StateObject private var model: OfflineSpikeModel

    init(address: ServerAddress?) {
        _model = StateObject(wrappedValue: OfflineSpikeModel(address: address))
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("E1/E2 offline spike").font(.headline)
                Spacer()
                Text(model.port > 0 ? "127.0.0.1:\(model.port)" : "—")
                    .font(.caption.monospaced())
                    .foregroundStyle(.secondary)
            }
            Text(model.status).font(.subheadline)
            if !model.detail.isEmpty {
                Text(model.detail).font(.caption).foregroundStyle(.secondary)
            }
            OfflineSpikeWebView(webView: model.webView)
                .clipShape(RoundedRectangle(cornerRadius: 10))
        }
        .padding()
        .onAppear { model.start() }
    }
}

/// Hands SwiftUI the model's own web view — the probe owns it from configuration time.
struct OfflineSpikeWebView: UIViewRepresentable {

    let webView: WKWebView

    func makeUIView(context: Context) -> WKWebView { webView }
    func updateUIView(_ uiView: WKWebView, context: Context) {}
}
