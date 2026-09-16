#!/usr/bin/env python3
"""Syntax-check every piece of JavaScript this repo INJECTS into a web view or evaluates inside one.

⚠ Why this exists, in one sentence: **the shell's JavaScript is the only code in this repo that nothing
checks.** Swift is parsed, typechecked and (for the offline phases) executed on Linux; the Python is tested;
but the two scripts that decide whether the app can see anything at all — `WebInstrumentation.swift`'s
console/fetch/XHR capture and `OfflineBridge.swift`'s `window.__rkmOffline` — are Swift string literals until
the moment a WKWebView runs them. A syntax error there is invisible here and lands on the Mac as:

  * `WebInstrumentation`: the whole injected script throws at document-start, so **the page loads and the HUD's
    request log stays empty** — the failure looks like a bridge problem, not a typo;
  * `OfflineBridge`: `window.__rkmOffline` never exists, so every offline affordance (B4) is hidden and the
    phase looks unbuilt;
  * a probe script: the probe reports nothing and the gate says `NOT EXERCISED`, which is a *correct* answer
    that tells you the wrong thing.

⚠ It checks the SCRIPT, not its behaviour: `node --check` parses and stops. That is the whole point — it is
the class of error a parser catches and nothing else does.

⚠ It only looks at multi-line string literals that look like JavaScript (`window.`, `webkit.messageHandlers`,
`document.`, `(function`). A Swift file full of other multi-line strings is not this tool's business.

Usage:
    python3 tools/check_injected_js.py                # the app sources
    python3 tools/check_injected_js.py --selftest     # prove the tool can fail (fixtures, no node needed)

Exit codes: 0 every block parses · 1 a block does NOT parse · 3 no `node` here to ask.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

#: Where injected JS can live. Both platforms, because the TV shell wraps the same page.
SEARCH_ROOTS = [REPO / "apple" / "ios" / "RKMCinema", REPO / "apple" / "tvos"]

#: A raw Swift string literal: `#"""…"""#` (with any number of `#`) or a plain `"""…"""`.
BLOCK = re.compile(r'(?P<hashes>#+)?"""\n(?P<body>.*?)\n\s*"""(?P=hashes)', re.S)

#: Cheap "this is JavaScript" test. Deliberately generous: a false positive costs one `node --check`.
JS_MARKERS = ("window.", "document.", "webkit.messageHandlers", "(function", "=>", "console.", "navigator.")


def js_blocks(path: Path) -> list[tuple[int, str]]:
    """Every JS-looking block in one Swift file, with the line it starts on."""
    text = path.read_text(encoding="utf-8", errors="replace")
    found: list[tuple[int, str]] = []
    for match in BLOCK.finditer(text):
        body = match.group("body")
        if not any(marker in body for marker in JS_MARKERS):
            continue
        line = text[:match.start()].count("\n") + 1
        found.append((line, body))
    return found


def check_with_node(node: str, blocks: list[tuple[Path, int, str]]) -> int:
    """Parse each block with `node --check`. ⚠ `--check` never runs the code."""
    failures = 0
    # ⚠ `$HOME/tmp`, never `/tmp`: `/tmp` is `noexec` in this sandbox, and a tool that quietly cannot run its
    # own helper is worse than no tool (the lesson `check-offline-core.py` already records).
    scratch = Path(tempfile.mkdtemp(dir=Path.home() / "tmp"))
    try:
        for index, (path, line, body) in enumerate(blocks, start=1):
            target = scratch / f"block{index:02d}.js"
            target.write_text(body, encoding="utf-8")
            result = subprocess.run([node, "--check", str(target)], capture_output=True, text=True)
            # ⚠ `relative_to` raises for a synthetic path (the selftest's fixtures), and a checker that
            # crashes on its own fixture reports a traceback where a verdict belongs.
            try:
                relative = path.relative_to(REPO)
            except ValueError:
                relative = path
            if result.returncode == 0:
                print(f"✓ {relative}:{line} — parses")
            else:
                failures += 1
                print(f"✗ {relative}:{line} — DOES NOT PARSE")
                for detail in (result.stderr or result.stdout).strip().splitlines()[:12]:
                    print(f"    {detail}")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return failures


def selftest() -> int:
    """⚠ The tool must be able to FAIL — proved with a block that cannot parse."""
    good = '(function () { window.__x = 1; })();'
    bad = '(function () { window.__x = ; })();'
    scratch = Path(tempfile.mkdtemp(dir=Path.home() / "tmp"))
    node = shutil.which("node") or shutil.which("nodejs")
    cases = [("a valid IIFE", good), ("a missing operand", bad)]
    failures = 0
    try:
        for index, (label, body) in enumerate(cases, start=1):
            source = scratch / f"case{index}.swift"
            source.write_text(f'let source: String = #"""\n{body}\n"""#\n', encoding="utf-8")
            blocks = js_blocks(source)
            if not blocks or blocks[0][1] != body:
                print(f"{index:02d}. FAIL {label} — the extractor did not find the block")
                failures += 1
                continue
            print(f"{index:02d}. ok   {label} — extracted ({len(body)} chars)")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    if failures:
        print(f"\nFAIL — {failures} extraction case(s) wrong; the tool cannot be trusted.")
        return 1

    # ⚠ And the PARSE verdict itself, not just the extractor: the broken fixture must be REJECTED. A checker
    # whose only evidence is "it said fine" has not been falsified at all.
    if node is None:
        print("\n(no node on PATH — extraction verified, the parse verdict was NOT falsified here)")
        return 3
    verdicts = check_with_node(node, [(Path("selftest-valid.js"), 1, good), (Path("selftest-broken.js"), 1, bad)])
    if verdicts != 1:
        print(f"\nFAIL — the checker reported {verdicts} failure(s) for one valid and one BROKEN block; "
              f"expected exactly 1. It cannot be trusted to fail.")
        return 1
    print("\nPASS — the extractor finds both blocks and the parse verdict is falsified: the valid one parses, "
          "the broken one is REJECTED.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()

    node = shutil.which("node") or shutil.which("nodejs")
    if node is None:
        print("no `node` on PATH — cannot parse the injected JavaScript here.", file=sys.stderr)
        print("  (the blocks are still extracted and listed below, so a Mac round can check them ", file=sys.stderr)
        print("   with the same command)", file=sys.stderr)
        for root in SEARCH_ROOTS:
            if not root.is_dir():
                continue
            for path in sorted(root.rglob("*.swift")):
                for line, _ in js_blocks(path):
                    print(f"  {path.relative_to(REPO)}:{line}")
        return 3

    blocks: list[tuple[Path, int, str]] = []
    files = 0
    for root in SEARCH_ROOTS:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.swift")):
            files += 1
            for line, body in js_blocks(path):
                blocks.append((path, line, body))

    print(f"checked {files} Swift file(s) for injected JavaScript in: "
          + ", ".join(str(root.relative_to(REPO)) for root in SEARCH_ROOTS if root.is_dir()))
    if not blocks:
        print("no injected JavaScript found — ⚠ that is either a huge refactor or a broken extractor; "
              "check the patterns above before believing it")
        return 3

    failures = check_with_node(node, blocks)
    print("")
    if failures:
        print(f"FAIL — {failures} of {len(blocks)} injected script(s) do not parse. This is a Mac-round bug "
              f"caught here: the page would load and the feature would silently not exist.")
        return 1
    print(f"PASS — {len(blocks)} injected script(s) parse. ⚠ This is a PARSE, not a behaviour: it proves no "
          f"typo, not that the script does its job.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
