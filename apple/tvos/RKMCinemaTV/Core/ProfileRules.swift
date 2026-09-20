import Foundation

// The Profile Switcher's RULES — pure, so they are RUN on Linux (`apple/scripts/check-tvos-core.py`) before a
// Mac round is spent on them, and so a rule no view can reach stops being a rule (the `subtitle` and avatar
// text below lived inside `ProfilesView`'s `body` until Phase U2, where no test could see them).
//
// ⚠⚠ **THE WORDS ARE THE APP'S OWN, AND THAT IS HIS DECISION (2026-09-19).** The tvOS buildspec introduces a
// second vocabulary for one idea — `"Profile · password"` / `"Administrator · password"` / `"Profile"` —
// where this app already says `"Password protected"` / `"Administrator — asks for a password"` /
// `"No password"` / `"Disabled — cannot be selected"` (`ProfilesView`, accepted on his simulator in Phase A).
// Two vocabularies for one idea is the fault this repo keeps re-learning, and the buildspec's set **cannot
// express the disabled case at all**, which the app's can. So the app's words win, they are pinned HERE by
// tests, and `docs/TVOS_UX_PLAN.md` §1a records the decision.
//
// ⚠ **NOTHING HERE DECIDES ANYTHING THE SERVER ALREADY DECIDED.** Every fact a tile shows comes off the wire
// (`profile.has_password`, `profile.is_admin`, `profile.disabled`). The buildspec's §3 example data
// (`meenu`/`raj`/`rkm` locked, `sharanya` not, `rkm` the administrator) is ILLUSTRATIVE and hardcoding it
// would ship a screen that lies the first time somebody changes a password — falsifier **F2** is exactly that.

enum ProfileRules {

    // ---------------------------------------------------------------- the tile's words

    /// The line under a profile's name. ⚠ **The accepted screen's wording, verbatim** — see the header.
    ///
    /// ⚠ The ORDER is the rule, not an accident: disabled outranks administrator, and administrator outranks
    /// a mere password, because the administrator's profile *always* asks for a password (the server requires
    /// it even when `has_password` reads false). A tile that said "Password protected" for the administrator
    /// would be technically true and useless.
    static func subtitle(_ profile: ProfileUser) -> String {
        if profile.disabled { return "Disabled — cannot be selected" }
        if profile.isAdmin { return "Administrator — asks for a password" }
        if profile.hasPassword { return "Password protected" }
        return "No password"
    }

    /// What VoiceOver reads for a tile — the buildspec §6 asks for this, and with a lock shown as a GLYPH a
    /// screen reader would otherwise hear a name and nothing else.
    ///
    /// ⚠ Same facts as ``subtitle``, different grammar: a screen reader hears "Meenu, profile, password
    /// protected", where the tile shows "Password protected" under the name. One source, two renderings.
    static func accessibilityLabel(_ profile: ProfileUser) -> String {
        var parts = [profile.name, profile.isAdmin ? "administrator" : "profile"]
        if profile.disabled {
            parts.append("disabled")
        } else if profile.hasPassword || profile.isAdmin {
            parts.append("password protected")
        } else {
            parts.append("no password")
        }
        return parts.joined(separator: ", ")
    }

    /// The circular avatar's initials — the buildspec's gold-on-dark tile.
    ///
    /// ⚠ **The multi-word branch is NOT from the buildspec** (all four of its examples are single names), so
    /// it is a new tvOS decision and it is stated rather than implied: **one word → its first two letters**
    /// (`meenu` → `ME`, `sharanya` → `SH`, which is what the buildspec shows), **several words → the first
    /// letter of each of the first two** (`Raj Kumar` → `RK`). ⚠ Case-folded here rather than in the view:
    /// a name is whatever the server says it is, and Swift's `uppercased()` is locale-independent for this
    /// purpose while `capitalized` is not.
    static func initials(_ name: String) -> String {
        let words = name
            .split(whereSeparator: { $0.isWhitespace })
            .map { $0.filter { $0.isLetter || $0.isNumber } }
            .filter { !$0.isEmpty }
        guard let first = words.first else { return "?" }
        let letters: String
        if words.count == 1 {
            letters = String(first.prefix(2))
        } else {
            letters = String(first.prefix(1)) + String(words[1].prefix(1))
        }
        return letters.uppercased()
    }

    // ---------------------------------------------------------------- the eyebrow

    /// The line ABOVE the title: `"4 profiles on this server · Signed in as rkm"` (buildspec §3).
    ///
    /// ⚠ Two deltas from the accepted screen, both the buildspec's and both kept: the profile COUNT (which
    /// the screen never said, and which is the difference between "no profiles loaded yet" and "these four"),
    /// and the line moving above the title. ⚠ The singular is handled because a household of one is a real
    /// household; `"1 profiles"` is the kind of thing a viewer notices before anything else.
    ///
    /// ⚠ `signedInAs` empty or nil drops its own segment rather than leaving a dangling `"· "` — the same
    /// rule `HomeRules.cardFacts` applies to its absent fields.
    static func eyebrow(profileCount: Int, signedInAs: String?) -> String {
        let count = max(0, profileCount)
        let head = "\(count) profile\(count == 1 ? "" : "s") on this server"
        let name = (signedInAs ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        return name.isEmpty ? head : "\(head) · Signed in as \(name)"
    }

    // ---------------------------------------------------------------- who may administer

    /// Whether the signed-in account is the household's administrator — the gate for `Add profile` /
    /// `Manage profiles`.
    ///
    /// ⚠⚠ **A SERVER FACT, NOT A UI GUESS.** `GET /api/auth/me` carries no `is_admin` (`MeResponse` is
    /// `user` + `profile`, both `SessionUser`s), but `GET /api/auth/profiles` marks **every** profile with
    /// `is_admin` — so the answer is already on the device and is matched **by ID, never by name**
    /// (the same identity rule as `entryForHit`: the name is what a rename changes, and the buildspec's own
    /// example data makes `rkm` look like "the administrator" by name).
    ///
    /// ⚠ The server is still the enforcement point (§11): a non-administrator reaching the admin routes gets
    /// a 403 whatever this returns. This function exists so the app does not OFFER a control the server would
    /// refuse — which is why it returns false when either list is empty or the ids do not match.
    static func isAdministrator(signedInUserID: String?, profiles: [ProfileUser]) -> Bool {
        guard let signedInUserID, !signedInUserID.isEmpty else { return false }
        return profiles.first { $0.id == signedInUserID }?.isAdmin ?? false
    }
}
