import Foundation
import WebKit
import RKMServerKit

/// Clearing everything the page has stored on the device.
///
/// ⚠ This is the other half of "a wrong address must never brick the app": when the server is
/// reachable but the shell still will not load — a stale session cookie, a cached bundle that no
/// longer matches the server — the way out is to forget the page's local state. That includes the
/// session cookie, which is why the UI puts it behind a confirmation.
enum WebsiteData {

    static func clear(completion: @escaping (String) -> Void) {
        let store = WKWebsiteDataStore.default()
        let types = WKWebsiteDataStore.allWebsiteDataTypes()
        let cookieStore = store.httpCookieStore

        cookieStore.getAllCookies { cookies in
            // ⚠ Names only, through the redactor — a value never becomes a string here at all.
            let summary = LogRedactor.redact(cookieNames: cookies.map(\.name))
            for cookie in cookies {
                cookieStore.delete(cookie)
            }
            store.removeData(ofTypes: types, modifiedSince: .distantPast) {
                completion("Cleared \(summary) and all cached page data.")
            }
        }
    }
}
