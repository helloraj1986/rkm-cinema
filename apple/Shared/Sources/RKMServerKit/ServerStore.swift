import Foundation

/// The persistence seam behind `ServerStore`.
///
/// `UserDefaults` is the real implementation; the in-memory one exists so the rules can be
/// exercised by `swift test` in the Linux sandbox — no simulator, no defaults plist, and no
/// chance of a test quietly reading the machine's real stored address.
public protocol ServerAddressStorage {
    func string(forKey key: String) -> String?
    func setString(_ value: String?, forKey key: String)
}

/// The real one. `UserDefaults` rather than the Keychain: the address is not a secret
/// (`apple/Shared/README.md` — "Keychain only if it ever holds a secret"), and a
/// non-secret in the Keychain is a non-secret that survives an app delete, which is worse
/// than useless when someone is trying to reset the app.
public final class UserDefaultsServerAddressStorage: ServerAddressStorage {
    private let defaults: UserDefaults

    public init(suiteName: String? = nil) {
        if let suiteName, let scoped = UserDefaults(suiteName: suiteName) {
            defaults = scoped
        } else {
            defaults = .standard
        }
    }

    public func string(forKey key: String) -> String? {
        defaults.string(forKey: key)
    }

    public func setString(_ value: String?, forKey key: String) {
        if let value {
            defaults.set(value, forKey: key)
        } else {
            defaults.removeObject(forKey: key)
        }
    }
}

public final class InMemoryServerAddressStorage: ServerAddressStorage {
    private var values: [String: String]

    public init(seed: [String: String] = [:]) {
        values = seed
    }

    public func string(forKey key: String) -> String? { values[key] }

    public func setString(_ value: String?, forKey key: String) {
        if let value {
            values[key] = value
        } else {
            values.removeValue(forKey: key)
        }
    }
}

/// Remembers the one server address, for both apps.
///
/// Deliberately dumb: it stores the **normalised** string and hands back a parsed
/// `ServerAddress`, so every launch reads the same rules the setup screen applied.
public final class ServerStore {
    public static let addressKey = "rkm.serverAddress"

    private let storage: ServerAddressStorage
    private let key: String

    public init(storage: ServerAddressStorage = UserDefaultsServerAddressStorage(),
                key: String = ServerStore.addressKey) {
        self.storage = storage
        self.key = key
    }

    /// The address to load from, or `nil` when there isn't one.
    public var address: ServerAddress? {
        guard let raw = rawValue else { return nil }
        return try? ServerAddress(rawValue: raw)
    }

    /// Exactly what is on disk, unparsed.
    public var rawValue: String? {
        storage.string(forKey: key)
    }

    /// ⚠ Something IS stored but no longer parses — a stricter rule since it was written, a
    /// hand-edited value, or a build that persisted a different shape. The setup screen says
    /// so instead of silently asking again, because "why am I being asked for the address
    /// when I already set it?" is otherwise an unfixable-looking bug.
    public var hasInvalidStoredValue: Bool {
        rawValue != nil && address == nil
    }

    /// Normalises and persists. Returns `false` only if the value could not be written back.
    @discardableResult
    public func save(_ raw: String) throws -> ServerAddress {
        let address = try ServerAddress(rawValue: raw)
        save(address)
        return address
    }

    public func save(_ address: ServerAddress) {
        storage.setString(address.displayString, forKey: key)
    }

    /// The "Change server" path. Clears the stored value so the app launches on screen #0.
    public func clear() {
        storage.setString(nil, forKey: key)
    }
}
