#!/usr/bin/env python3
"""Catch a missing framework import BEFORE the Mac does.

⚠ Why this exists. The first three builds of the iOS shell failed on nothing but missing imports:

  build 2: `ObservableObject` / `@Published`                     -> Combine
  build 2: `Color(uiColor: .secondarySystemBackground)`          -> UIKit
  build 3: `webView.isInspectable`                               -> WebKit

On the **iOS 26 SDK SwiftUI no longer re-exports Combine or UIKit**, so a file that only says
`import SwiftUI` fails on any symbol those modules own. Every miss costs a full round trip through the
Mac, which is the most expensive thing in this workflow.

⚠ Two ways a miss happens, and this checker covers both:
  1. **Type names carry their module** — `WKWebView`, `UIView` — caught by `RULES`.
  2. ⚠ **Members reached through an instance do not** — `shell.webView?.isInspectable` and
     `Color(uiColor: .secondarySystemBackground)` have no prefix at all, so no name pattern finds them.
     That is exactly how `isInspectable` was missed by the first version of this script, after the same
     blind spot had already cost a build. `MEMBER_RULES` is the curated answer; extend it when a new
     one appears. ⚠ It can never be exhaustive — a member is only in it once we have been bitten.

⚠⚠ **AND A THIRD, WHICH COST PHASE B2's FIRST MAC ROUND (2026-09-19): THE APP'S OWN MODULE WAS NEVER IN
THE TABLE.** This checker was written because three iOS builds died on Apple *framework* imports, so
`RULES` listed Apple's modules and nobody asked whether `RKMServerKit` — the package this app links and
imports in sixteen files — needed the same rule. `Home/HomeView.swift` used `RKMLog` with no
`import RKMServerKit` and **no gate could see it**: the file is SwiftUI, so it is not in
`check-apple-typecheck.sh`'s list, and the module was not in `RULES` here. Two gates, both blind to it,
one failed round. `RKMServerKit` is now a rule like any other.

(Foundation is the exception: SwiftUI *does* re-export it — proved by `Date()` compiling in a file that
imports nothing but SwiftUI.)

False positives cost nothing here (an extra import is harmless); a miss costs a build. So the rules are
deliberately broad — **except** `RKMServerKit`'s, which must be name-exact: the app defines its own types
starting with `RKM` (`RKMCinemaTVApp`, `RKMCinema`), so a prefix pattern would demand the import from
files that need nothing. `--selftest` pins that distinction.

Usage:
    python3 apple/scripts/check-imports.py                 # defaults to apple/ios/RKMCinema
    python3 apple/scripts/check-imports.py apple/tvos/RKMCinemaTV
    python3 apple/scripts/check-imports.py --selftest       # the rules, against known snippets

Exit code 1 when a file uses a symbol whose module it does not import.
"""
import os
import re
import sys

# Type names that carry their framework ("WKWebView", "UIColor"). Keep the module name exactly as it
# is written in an `import`.
RULES = {
    "Combine": r"\bObservableObject\b|\b@Published\b|\bAnyCancellable\b|\bPassthroughSubject\b"
               r"|\bCurrentValueSubject\b|\bObservableObjectPublisher\b",
    "WebKit": r"\bWK[A-Z]\w*",
    # SwiftUI's own representable protocols start with "UI" but live in SwiftUI.
    "UIKit": r"\b(?!UIViewRepresentable\b|UIViewControllerRepresentable\b|UIHostingController\b)UI[A-Z]\w*",
    "AVFoundation": r"\bAV[A-Z]\w*",
    # ⚠⚠ **PHASE P (2026-09-20) — `MediaPlayer`, AND IT IS THE `RKMServerKit` LESSON A THIRD TIME.** The player
    # publishes what it is showing to the system's now-playing panel (`MPNowPlayingInfoCenter`), and **no rule
    # here named `MP`** — so a file using it without the import would have compiled right up to the Mac, which
    # is the most expensive place in this workflow to find out. ⚠ `MP` is added as a PREFIX and that is safe
    # here, unlike `RKM`: nothing in this app defines a type starting with `MP`.
    "MediaPlayer": r"\bMP[A-Z]\w*",
    # Phase B3's loopback server and the probe's client both speak Network.framework. ⚠ It is easy to miss
    # because every type it contributes is `NW`-prefixed but the file often looks Foundation-only.
    "Network": r"\bNW[A-Z]\w*",
    # ⚠⚠ NOT an Apple framework — **the app's OWN package**, and it was missing from this table until
    # Phase B2's first Mac round failed on it (`HomeView.swift` used `RKMLog` with no import). The blind
    # spot's shape: the table was written for Apple's modules, and the app's own module was never asked.
    #
    # ⚠ DELIBERATELY NAME-EXACT, not a prefix. `\bRKM[A-Z]\w*` would be the "consistent" pattern and it is
    # WRONG here: the app defines its own types starting with `RKM` (`RKMCinemaTVApp`, `RKMCinema`,
    # `RKMOfflineSpike`), so a prefix rule would demand this import from files that need nothing — and a
    # false positive that forces a wrong import is worse than a rule one symbol short (the `isHTTPOnly`
    # lesson, again).
    "RKMServerKit": r"\bRKMLog\b|\bCorrelationID\b|\bLogRedactor\b|\bRollingFileLog\b"
                    r"|\bLogRingBuffer\b|\bServerAddress\b|\bServerAddressError\b"
                    r"|\bServerAddressHost\b|\bServerStore\b",
}

# ⚠ Members with no prefix, reached through an instance — invisible to `RULES`.
MEMBER_RULES = {
    "WebKit": [
        "isInspectable",
        "allowsInlineMediaPlayback",
        "allowsBackForwardNavigationGestures",
        "mediaTypesRequiringUserActionForPlayback",
        "isElementFullscreenEnabled",
        "defaultWebpagePreferences",
        "userContentController",
        "httpCookieStore",
        "allWebsiteDataTypes",
        "loadHTMLString",
        "evaluateJavaScript",
        # Phase B2's cookie mirror: reached as `store.httpCookieStore.getAllCookies`, and
        # `cookiesDidChange(in:)` is the observer callback — no `WK` prefix anywhere in the file.
        "getAllCookies",
        "cookiesDidChange",
        "isSessionOnly",
        # ⚠ NOT `isHTTPOnly`, and it was tried: our OWN `CookieSnapshot` has a property of that name
        # (`Offline/CookieHeader.swift`), so the rule reports a missing WebKit import for a file that must
        # stay Foundation-only — it is compiled by `apple/scripts/check-offline-core.py` on Linux, where
        # WebKit does not exist. The genuine use (`HTTPCookie.isHTTPOnly`) is in `CookieMirror.swift`,
        # which imports WebKit for the `WK`-prefixed names anyway. A false positive that forces a wrong
        # import is worse than a rule that is one symbol short.
    ],
    # `uiColor` alone covers the UIColor backgrounds in this codebase (`.secondarySystemBackground`,
    # `.systemBackground`, `.separator` all appear as its argument), so the broad, noisy words
    # ("label", "separator") are deliberately left out.
    "UIKit": [
        "uiColor",
        "motionEnded",
        "canBecomeFirstResponder",
        "becomeFirstResponder",
        "dequeueReusableCell",
        # Phase B2's background assertion for the preparation phase (OfflineDownloads.swift).
        "beginBackgroundTask",
        "endBackgroundTask",
        "backgroundTimeRemaining",
    ],
    # ⚠ Only the DISTINCTIVE members: a word like `maximumLength` or `isComplete` appears in ordinary
    # parsing code too, and a false positive here forces a wrong framework import into a file that must stay
    # Foundation-only (the lesson `isHTTPOnly` already taught).
    "Network": [
        "allowLocalEndpointReuse",
        "requiredLocalEndpoint",
        "stateUpdateHandler",
        "newConnectionHandler",
        "contentProcessed",
        "minimumIncompleteLength",
    ],
}

#: ⚠⚠ **A FOURTH WAY A MISS HAPPENS — AND IT COST PHASE C'S FIRST MAC ROUND (2026-09-20).** The module can be
#: carried by a **METHOD**, not by a type: `Timer.publish(every:on:in:).autoconnect()` names `Timer`
#: (Foundation) and `autoconnect()` (**Combine**), so neither `RULES` nor `MEMBER_RULES` fires and the file
#: compiles right up until:
#:
#:     PlayerView.swift:33: error: instance method 'autoconnect()' is not available due to missing import of
#:     defining module 'Combine'
#:
#: ⚠⚠ **DELIBERATELY PATTERNS, NOT BARE MEMBER NAMES** — `sink`, `receive` and `assign` are ordinary English
#: words, and a rule that fires on a comment or a variable name forces a wrong import into a file that must
#: stay Foundation-only (the `isHTTPOnly` lesson, third time). Each pattern below requires the CALL shape.
PATTERN_RULES = {
    "Combine": [
        r"\.autoconnect\(",
        r"\bTimer\.publish\(",
        r"\.publisher\(for:",
        r"\.sink\(",
        r"\.receive\(on:",
        r"\.assign\(to:",
    ],
}

# ⚠ A third way a miss happens, caught by neither table above: a type the app defines ITSELF whose name
# collides with a module-namespaced pattern. `OfflineDownloads` starts with "Offline", so nothing here
# fires — but if a future type starts with `UI` or `WK` it will be reported as a missing import, and the
# fix is to rename the type, not to add an import.

DEFAULT_TARGETS = ["apple/ios/RKMCinema"]

#: ⚠ The rules, against snippets whose answer is KNOWN — because a rule nobody has seen fail is a rule
#: that proves nothing (`references/falsification-and-test-stubs.md`). Two of these exist purely to pin the
#: `RKMServerKit` rule's two edges: it must fire on a real use without the import, and it must NOT fire on
#: the app's own `RKM`-prefixed types or on a symbol that only appears in a comment.
SELFTEST = [
    ("an unimported RKMServerKit symbol",
     'import SwiftUI\n\nstruct V: View {\n    var body: some View { Text("x").onAppear { RKMLog.info("hi") } }\n}',
     {"RKMServerKit"}),
    ("an RKMServerKit symbol WITH its import",
     'import SwiftUI\nimport RKMServerKit\n\nstruct V: View { let log = RKMLog.self }',
     set()),
    ("an RKMServerKit symbol in a COMMENT only",
     'import SwiftUI\n\n// this file deliberately does not use RKMLog\nstruct V: View {}',
     set()),
    ("the app's OWN RKM type (must NOT demand the import)",
     'import SwiftUI\n\n@main\nstruct RKMCinemaTVApp: App {}',
     set()),
    ("an unimported Combine symbol",
     'import SwiftUI\n\nfinal class M: ObservableObject {}',
     {"Combine"}),
    # ⚠⚠ The shape THIS table was blind to until Phase C's first Mac round: a Combine METHOD on a
    # Foundation type. The file below is `PlayerView.swift`'s ticker, reduced.
    ("an unimported Combine METHOD on a Foundation type",
     'import SwiftUI\n\nlet ticker = Timer.publish(every: 0.5, on: .main, in: .common).autoconnect()',
     {"Combine"}),
    ("a Combine subscription with no import",
     'import SwiftUI\n\nlet sub = NotificationCenter.default.publisher(for: Notification.Name("x"))',
     {"Combine"}),
    # ⚠ And the OTHER edge: the same words as ordinary code must NOT demand the import.
    ("the word `sink` in prose, and `assign` as a plain function",
     'import SwiftUI\n\n// the kitchen sink\nfunc assign(_ x: Int) -> Int { x }',
     set()),
    ("an unimported UIKit type",
     'import SwiftUI\n\nlet label = UILabel()',
     {"UIKit"}),
    # ⚠⚠ Phase P's own rule, and both of its edges. The POSITIVE case is the real shape (`PlayerView`'s
    # now-playing publish); the negative case pins that the `MP` prefix does not demand an import for a word
    # that merely starts that way in prose — the false-positive class that would force a wrong import.
    ("an unimported MediaPlayer symbol",
     'import SwiftUI\n\nfunc publish(_ title: String) {\n'
     '    MPNowPlayingInfoCenter.default().nowPlayingInfo = [MPMediaItemPropertyTitle: title]\n}',
     {"MediaPlayer"}),
    ("a MediaPlayer symbol WITH its import",
     'import SwiftUI\nimport MediaPlayer\n\nlet centre = MPNowPlayingInfoCenter.default()',
     set()),
    ("the letters `MP` inside a word in prose",
     'import SwiftUI\n\n// the MP4 container is not a MediaPlayer symbol\nlet x = 1',
     set()),
]


def framework_imports(text: str) -> set:
    return set(re.findall(r"^\s*import\s+(\w+)", text, re.M))


def without_comments(text: str) -> str:
    """A doc comment must not be able to demand an import."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"//[^\n]*", "", text)
    return text


def missing_for(code: str, imported: set) -> dict:
    missing = {}
    for framework, pattern in RULES.items():
        if framework in imported:
            continue
        hits = set(re.findall(pattern, code))
        for member in MEMBER_RULES.get(framework, []):
            if re.search(rf"\b{re.escape(member)}\b", code):
                hits.add(member)
        for pattern in PATTERN_RULES.get(framework, []):
            for hit in re.findall(pattern, code):
                hits.add(hit)
        if hits:
            missing[framework] = sorted(hits)
    return missing


def main(targets) -> int:
    checked = 0
    problems = []

    for target in targets:
        if not os.path.isdir(target):
            print(f"not a directory: {target}", file=sys.stderr)
            return 2
        for dirpath, _dirnames, filenames in os.walk(target):
            for filename in sorted(filenames):
                if not filename.endswith(".swift"):
                    continue
                path = os.path.join(dirpath, filename)
                text = open(path, encoding="utf-8").read()
                checked += 1
                for framework, hits in missing_for(without_comments(text), framework_imports(text)).items():
                    shown = ", ".join(hits[:6]) + (" …" if len(hits) > 6 else "")
                    problems.append((path, framework, shown))

    print(f"checked {checked} Swift file(s) in: {', '.join(targets)}")
    if not problems:
        print("no missing framework imports ✅")
        return 0

    print()
    for path, framework, symbols in problems:
        print(f"MISSING  import {framework}   in {path}")
        print(f"         uses: {symbols}")
    print()
    print(f"{len(problems)} missing import(s). ⚠ Each one would have been a failed build on the Mac.")
    return 1


def selftest() -> int:
    print("selftest — the rules against snippets whose answer is known\n")
    failures = 0
    for label, source, expected in SELFTEST:
        got = set(missing_for(without_comments(source), framework_imports(source)))
        if got == expected:
            print(f"  ok   {label}")
        else:
            failures += 1
            print(f"  FAIL {label} — got {sorted(got) or 'nothing'}, want {sorted(expected) or 'nothing'}")
    print()
    if failures:
        print(f"FAIL — {failures} snippet(s) answered wrongly; the rule table is not proving what it "
              f"claims.")
        return 1
    print(f"PASS — {len(SELFTEST)}/{len(SELFTEST)} snippets answered as expected.")
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--selftest" in args:
        sys.exit(selftest())
    sys.exit(main(args or DEFAULT_TARGETS))
