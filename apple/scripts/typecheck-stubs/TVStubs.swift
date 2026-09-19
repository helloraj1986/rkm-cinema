// ⚠ NOT SHIPPED AND NOT COMPILED INTO THE APP — like its sibling `Stubs.swift`, this file only ever
// exists inside the scratch copy `apple/scripts/check-apple-typecheck.sh` builds.
//
// ⚠⚠ **WHY THERE ARE TWO STUB FILES RATHER THAN ONE.** `Stubs.swift` stubs WebKit and UIKit for the iOS
// target, and its WebKit slice deliberately references iOS types (`CookieMirror` returns
// `CookieHeaderOutcome` from `CookieHeader`). Adding it to the tvOS compile would therefore fail on
// symbols the tvOS app does not have — the stubs would be the reason a gate went red, which is the one
// thing a stub must never do. tvOS needs only the Combine half, so it gets only the Combine half.
//
// ⚠ What is NOT here, and cannot be: SwiftUI, UIKit and AVFoundation. That is why
// `check-apple-typecheck.sh` lists the tvOS files ONE AT A TIME — the six in the list import none of
// those (they are `Foundation` + `RKMServerKit`, plus `Combine` for the session), and every SwiftUI view
// is left to the Mac round rather than pretended at here.
import Foundation

#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

// MARK: - Combine stand-ins (the slice `SessionStore` touches)

/// ⚠ These exist so the session model can be typechecked on Linux. What matters here is the SHAPE:
/// a class declaring `ObservableObject` must still conform without writing `objectWillChange` itself
/// (the real protocol supplies one through an extension, so the stub must too — otherwise every type
/// that declares conformance fails, and the gate reports errors that do not exist on the Mac).
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
