// ⚠ NOT SHIPPED AND NOT COMPILED INTO THE APP — this file only ever exists inside the scratch copy
// `apple/scripts/check-apple-typecheck.sh` builds. It is the "mimic the overloads" technique from
// `apple/WORKFLOW.md` §5 scaled up: the smallest stand-ins whose SHAPES match the Apple APIs the iOS
// sources call, so `swiftc` can check the parts that are ours — types, argument labels, optionality,
// protocol conformance — without a Mac.
//
// ⚠⚠ WHAT IT CANNOT DO, and the reason the script reports per file: it has no UIKit, no WebKit, no
// Combine, and two `URLSessionConfiguration` members are Darwin-only. Those show up as errors and are
// filtered by name. Everything else is a real error in the real source.
import Foundation

#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

// MARK: - Combine stand-ins

/// ⚠ These exist so a file that pipes a downloader's changes into the page can be *typechecked* here. The
/// real `AnyCancellable`/`ObservableObjectPublisher` are Combine's; what matters for a Linux typecheck is
/// that `objectWillChange.sink { … }` has a `sink` and returns something storable, and that a class
/// declaring `ObservableObject` still conforms without writing the property itself (the real protocol
/// supplies one through an extension, so the stub must too — otherwise every existing type fails).
final class AnyCancellable {
    init() {}
}

final class ObservableObjectPublisher {
    @discardableResult
    func sink(receiveValue: @escaping () -> Void) -> AnyCancellable {
        _ = receiveValue
        return AnyCancellable()
    }
}

protocol ObservableObject: AnyObject {
    var objectWillChange: ObservableObjectPublisher { get }
}

extension ObservableObject {
    var objectWillChange: ObservableObjectPublisher { ObservableObjectPublisher() }
}

@propertyWrapper
struct Published<Value> {
    var wrappedValue: Value
    init(wrappedValue: Value) { self.wrappedValue = wrappedValue }
    var projectedValue: Published<Value> { self }
}

// MARK: - UIKit stand-ins

typealias UIBackgroundTaskIdentifier = Int

extension Int {
    static var invalid: Int { -1 }
}

final class UIApplication {
    static let shared = UIApplication()
    func beginBackgroundTask(withName: String?, expirationHandler: (() -> Void)?) -> UIBackgroundTaskIdentifier {
        _ = expirationHandler
        _ = withName
        return 0
    }
    func endBackgroundTask(_ identifier: UIBackgroundTaskIdentifier) { _ = identifier }
}

// MARK: - WebKit stand-in (only the slice `OfflineAPI` and the B3 bridge touch)

final class CookieMirror {
    var summary: String { "stub" }
    func start() {}
    func stop() {}
    func headerOutcome(for url: URL, now: Date = Date()) -> CookieHeaderOutcome {
        CookieHeader.evaluate(cookies: [], url: url, now: now)
    }
}

// MARK: - WebKit stand-ins (the bridge's slice)

final class WKWebView {
    @discardableResult
    func evaluateJavaScript(_ javaScriptString: String,
                            completionHandler: ((Any?, Error?) -> Void)? = nil) -> Void {
        _ = javaScriptString
        _ = completionHandler
        return ()
    }

    // ⚠ S2 (ADR-0012 D7): the stored shell is handed to the web view as a STRING with the server as its
    // base URL. Mimicked as WebKit declares it — a stub kinder than the real API is a gate that cannot
    // fail (`ARCHITECTURE.md` §17.6).
    func loadHTMLString(_ string: String, baseURL: URL?) -> WKNavigation? { nil }
    func load(_ request: URLRequest) -> WKNavigation? { nil }
}

/// ⚠ S2: the real WebKit protocol, member for member, so `ShellAssetSchemeHandler` is typechecked here
/// instead of on the Mac.
protocol WKURLSchemeTask: AnyObject {
    var request: URLRequest { get }
    func didReceive(_ response: URLResponse)
    func didReceive(_ data: Data)
    func didFinish()
    func didFailWithError(_ error: Error)
}

protocol WKURLSchemeHandler: AnyObject {
    func webView(_ webView: WKWebView, start urlSchemeTask: WKURLSchemeTask)
    func webView(_ webView: WKWebView, stop urlSchemeTask: WKURLSchemeTask)
}

final class WKScriptMessage {
    var name: String = ""
    var body: Any = ""
}

/// ⚠ The whole reason the offline bridge uses the reply-capable registration: only this protocol lets a
/// command be ANSWERED, so a page can never be left with a promise that never settles.
protocol WKScriptMessageHandlerWithReply: AnyObject {
    func userContentController(_ userContentController: WKUserContentController,
                              didReceive message: WKScriptMessage,
                              replyHandler: @escaping (Any?, String?) -> Void)
}

final class WKContentWorld {
    static let page = WKContentWorld()
}

final class WKUserContentController {
    func addScriptMessageHandler(_ scriptMessageHandler: WKScriptMessageHandlerWithReply,
                                 contentWorld: WKContentWorld,
                                 name: String) {
        _ = scriptMessageHandler
        _ = contentWorld
        _ = name
    }
}

final class WKUserScript {
    enum InjectionTime {
        case atDocumentStart
        case atDocumentEnd
    }

    init(source: String, injectionTime: InjectionTime, forMainFrameOnly: Bool) {
        _ = source
        _ = injectionTime
        _ = forMainFrameOnly
    }
}

// MARK: - Network.framework stand-ins (loopback listener + client)

/// ⚠ `Network` does not exist on Linux at all, so without these the whole B3 socket layer would be
/// unchecked — the exact gap that let B2's `Int64?` reach the Mac. Only the SHAPES matter: the compiler
/// checks argument labels, optionality and protocol conformance, which is where the real errors live.
struct NWError: Error, LocalizedError {
    var detail: String
    var errorDescription: String? { detail }
}

struct IPv4Address {
    static let loopback = IPv4Address()
}

enum NWEndpoint {

    enum Host {
        case ipv4(IPv4Address)
        case name(String, interface: NWInterface?)
    }

    /// The real `NWEndpoint.Port` is failable for a reason — not every `UInt16` is a usable port.
    struct Port: Equatable {
        var rawValue: UInt16

        init?(rawValue: UInt16) {
            guard rawValue != 0 else { return nil }
            self.rawValue = rawValue
        }

        static let any: NWEndpoint.Port = NWEndpoint.Port(rawValue: 1)!
    }

    static func hostPort(host: Host, port: Port) -> NWEndpoint { NWEndpoint() }
}

final class NWInterface {}

final class NWParameters {
    static var tcp: NWParameters { NWParameters() }
    var allowLocalEndpointReuse: Bool = false
    var requiredLocalEndpoint: NWEndpoint?
}

final class NWListener {

    enum State {
        case setup
        case waiting(NWError?)
        case ready
        case failed(NWError)
        case cancelled
    }

    var stateUpdateHandler: ((State) -> Void)?
    var newConnectionHandler: ((NWConnection) -> Void)?
    var port: NWEndpoint.Port?

    init(using parameters: NWParameters) throws {
        _ = parameters
    }

    func start(queue: DispatchQueue) { _ = queue }
    func cancel() {}
}

final class NWConnection {

    enum State {
        case setup
        case preparing
        case ready
        case waiting(NWError)
        case failed(NWError)
        case cancelled
    }

    final class ContentContext {
        static let defaultMessage = ContentContext()
    }

    enum SendCompletion {
        case contentProcessed((NWError?) -> Void)
    }

    var stateUpdateHandler: ((State) -> Void)?

    init(host: NWEndpoint.Host, port: NWEndpoint.Port, using: NWParameters) {
        _ = host
        _ = port
        _ = using
    }

    func start(queue: DispatchQueue) { _ = queue }
    func cancel() {}

    func send(content: Data?, contentContext: ContentContext, isComplete: Bool, completion: SendCompletion) {
        _ = content
        _ = contentContext
        _ = isComplete
        _ = completion
    }

    func send(content: Data?, completion: SendCompletion) {
        _ = content
        _ = completion
    }

    func receive(minimumIncompleteLength: Int,
                 maximumLength: Int,
                 completion: @escaping (Data?, ContentContext?, Bool, NWError?) -> Void) {
        _ = minimumIncompleteLength
        _ = maximumLength
        _ = completion
    }
}
