// swift-tools-version: 5.9
import PackageDescription

// The ONLY package both Apple clients share — and it stays this small on purpose
// (`apple/Shared/README.md`): nothing belongs here unless BOTH apps need it.
//
//   ServerAddress / ServerStore  the server address a human typed — parse, normalise, persist
//   LogRedactor                  the ONE place a URL/header/cookie/body is made safe to log
//   RKMLog + RollingFileLog      structured `os.Logger` + the capped rolling file (`apple/LOGGING.md`)
//
// ⚠ One library product, deliberately. He links this in Xcode by hand, once, via
// File → Add Package Dependencies → Add Local… — a second product would mean a second
// checkbox to forget, and a missing one is a compile error he cannot fix from the Mac.
//
// The address rules and the redactor are pure Swift/Foundation, so they compile and
// unit-test on Linux: `swift test` in this directory is the Phase 0 gate that does not
// need his Mac. The `os.Logger` sink is guarded by `#if canImport(os)`, which is why
// that works.
let package = Package(
    name: "RKMServerKit",
    platforms: [
        .iOS(.v16),
        .tvOS(.v16),
        .macOS(.v13),
    ],
    products: [
        .library(name: "RKMServerKit", targets: ["RKMServerKit"])
    ],
    targets: [
        .target(name: "RKMServerKit"),
        .testTarget(name: "RKMServerKitTests", dependencies: ["RKMServerKit"]),
    ]
)
