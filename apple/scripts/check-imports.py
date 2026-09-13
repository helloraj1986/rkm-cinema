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

(Foundation is the exception: SwiftUI *does* re-export it — proved by `Date()` compiling in a file that
imports nothing but SwiftUI.)

False positives cost nothing here (an extra import is harmless); a miss costs a build. So the rules are
deliberately broad.

Usage:
    python3 apple/scripts/check-imports.py                 # defaults to apple/ios/RKMCinema
    python3 apple/scripts/check-imports.py apple/tvos/RKMCinemaTV

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
    ],
}

DEFAULT_TARGETS = ["apple/ios/RKMCinema"]


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


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or DEFAULT_TARGETS))
