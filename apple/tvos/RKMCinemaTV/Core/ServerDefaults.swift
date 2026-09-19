import Foundation

/// The address screen #0 opens with.
///
/// ⚠ **THIS IS THE ONE LINE TO CHANGE** if the house address moves. It is a *default*, not a
/// requirement: the field on screen #0 is editable, and whatever he types is stored by `ServerStore`
/// and wins from the next launch on. It exists for exactly one reason — **a Siri Remote is a poor text
/// input** (`docs/APPLE_CLIENTS_PLAN.md` §4.2), so the common case has to be one button press. The
/// nearby-iPhone keyboard (Continuity) and a paired Bluetooth keyboard both still work when the
/// address is different; this is just what the field already says when the app opens.
///
/// The Tailscale name is the default rather than a LAN IP because it is the address that works BOTH at
/// home and away — a LAN address only works on the home network, and there is no way to know from here
/// which one is wanted. Plain `http://` is fine: `Config/Info.plist` declares the ATS exception, and
/// the launch banner logs whether that declaration actually landed.
enum ServerDefaults {

    static let address = "http://rkm-hp.tail8d5e8.ts.net:8124"
}
