import XCTest
@testable import RKMServerKit

final class ServerStoreTests: XCTestCase {

    func testSavesTheNormalisedFormAndReadsItBack() throws {
        let storage = InMemoryServerAddressStorage()
        let store = ServerStore(storage: storage)
        XCTAssertNil(store.address)
        XCTAssertNil(store.rawValue)
        XCTAssertFalse(store.hasInvalidStoredValue)

        let saved = try store.save("RKM-HP.Tail8D5E8.ts.net/")
        XCTAssertEqual(saved.displayString, "https://rkm-hp.tail8d5e8.ts.net")
        // What is on disk is the normalised string, so the next launch needs no decisions.
        XCTAssertEqual(storage.string(forKey: ServerStore.addressKey), "https://rkm-hp.tail8d5e8.ts.net")
        XCTAssertEqual(store.address?.displayString, "https://rkm-hp.tail8d5e8.ts.net")
    }

    func testSavingGarbageIsRejectedAndPersistsNothing() throws {
        let storage = InMemoryServerAddressStorage()
        let store = ServerStore(storage: storage)
        XCTAssertThrowsError(try store.save("ftp://nope"))
        XCTAssertNil(storage.string(forKey: ServerStore.addressKey))
        XCTAssertNil(store.address)
    }

    func testAStoredValueThatNoLongerParsesIsReported() {
        // ⚠ Without this the setup screen would silently ask again, and "why is it asking me
        // for the address I already set?" is an unfixable-looking bug.
        let storage = InMemoryServerAddressStorage(seed: [ServerStore.addressKey: "not a host"])
        let store = ServerStore(storage: storage)
        XCTAssertNil(store.address)
        XCTAssertEqual(store.rawValue, "not a host")
        XCTAssertTrue(store.hasInvalidStoredValue)
    }

    func testClearReturnsTheAppToScreenZero() throws {
        let storage = InMemoryServerAddressStorage()
        let store = ServerStore(storage: storage)
        try store.save("192.168.1.10:8124")
        XCTAssertNotNil(store.address)
        store.clear()
        XCTAssertNil(store.address)
        XCTAssertNil(store.rawValue)
        XCTAssertFalse(store.hasInvalidStoredValue)
    }

    func testUserDefaultsRoundTripThroughASecondStore() throws {
        // The real storage adapter, exercised in the sandbox. A fresh `ServerStore` over the
        // same defaults is the closest we get to "relaunch the app" without a simulator.
        let suite = "RKMServerKitTests.\(UUID().uuidString)"
        let scoped = UserDefaults(suiteName: suite)
        defer { scoped?.removePersistentDomain(forName: suite) }

        let store = ServerStore(storage: UserDefaultsServerAddressStorage(suiteName: suite))
        try store.save("192.168.1.10:8124")

        let relaunched = ServerStore(storage: UserDefaultsServerAddressStorage(suiteName: suite))
        XCTAssertEqual(relaunched.address?.displayString, "http://192.168.1.10:8124")
        XCTAssertFalse(relaunched.hasInvalidStoredValue)
    }
}
