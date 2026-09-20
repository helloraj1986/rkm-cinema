#!/usr/bin/env python3
"""Generate the tvOS colour/radius/spacing tokens FROM the web app's own CSS.

⚠ WHY THIS FILE EXISTS. `tvos_ux/1. UserProfileSelection_HomePage/rkm-cinema-tvos-buildspec.md` §1 says
it is *"extracted from the current web UI so both platforms stay visually identical"* and then hand-copies
a table that is **wrong in 8 of 10 values — including the brand accent** (`#F2B93A` where the app is
`#ffc400`). Measured 2026-09-19, `docs/TVOS_UX_PLAN.md` §0.1. A spec's table is a source, not a
measurement; `frontend/src/styles/index.css` is the measurement, and this generator makes it the ONLY
source. The tvOS app therefore cannot hold a colour the web app does not.

⚠ The trade is the one `docs/api/openapi.v1.json` already makes for the wire format: **one source,
generated consumers, and a gate that fails the moment they drift**. Regenerate with this script; verify
with `apple/scripts/check-design-tokens.py`, which requires regeneration to be a NO-OP.

⚠ WHAT IS **NOT** GENERATED, and why (so nobody adds it later by accident):
  · the tvOS-only layer — the adjusted de-emphasised grey from `Design/TVTokens.swift`, and the
    spacing/safe-margin/type-scale values that were never in the CSS. **A generator for a hand-written
    number is worse than no generator** (`TVOS_UX_PLAN.md` §2);
  · the z-index ladder — `--z-*` is a DOM STACKING order. tvOS has no `z-index`, so carrying it would be
    inventing a use for a number that has none. It is in `IGNORED` below, by name, on purpose.

⚠ EVERY new CSS custom property must be either MAPPED or EXPLICITLY IGNORED — an unknown one is a hard
error rather than a silent omission. A generator that quietly skips what it does not recognise is how the
brand accent gets left behind.

Usage:
    python3 apple/scripts/generate-design-tokens.py                       # write the file
    python3 apple/scripts/generate-design-tokens.py --check               # drift check (writes nothing)
    python3 apple/scripts/generate-design-tokens.py --selftest            # prove the parser on fixtures
    python3 apple/scripts/generate-design-tokens.py --css X --out Y       # point it at fixtures

Exit codes: 0 = fine · 1 = drift / a parse failure / a selftest failure · 2 = the tool could not run.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_CSS = REPO / "frontend" / "src" / "styles" / "index.css"
DEFAULT_OUT = REPO / "apple" / "tvos" / "RKMCinemaTV" / "Design" / "DesignTokens.swift"

#: `--name: value;` inside a rule block. The value runs to the semicolon, so `rgba(255, 255, 255, 0.08)`
#: and `env(safe-area-inset-top, 0px)` both survive the match intact.
DECLARATION = re.compile(r"--([a-z0-9-]+)\s*:\s*([^;]+);")

#: The block whose tokens are the DESIGN SYSTEM. ⚠ Only the FIRST `:root` block: the second one
#: (`index.css`, the mobile shell) holds `env(safe-area-inset-*)` fallbacks, which are not design tokens
#: and are resolved by the browser — there is no number here to generate.
ROOT_BLOCK = re.compile(r":root\s*\{(?P<body>[^}]*)\}", re.DOTALL)

#: CSS name → Swift name. ⚠ EXPLICIT, never derived: `--surface-1` → `surface1` is guessable, `--accent`
#: → `accent` and `--bg` → `background` are not, and an auto-name is how two files come to call one token
#: two things. A CSS name missing from both this map and `IGNORED` is an ERROR.
COLOURS = {
    "bg": "background",
    "surface-1": "surface1",
    "surface-2": "surface2",
    "surface-3": "surface3",
    "card": "card",
    "border": "border",
    "text-primary": "textPrimary",
    "text-secondary": "textSecondary",
    "text-muted": "textMuted",
    "accent": "accent",
    "accent-hover": "accentHover",
    "success": "success",
    "warning": "warning",
    "danger": "danger",
}

RADII = {"radius-sm": "sm", "radius-md": "md", "radius-lg": "lg", "radius-xl": "xl"}
SPACES = {
    "space-1": "s1",
    "space-2": "s2",
    "space-3": "s3",
    "space-4": "s4",
    "space-5": "s5",
    "space-6": "s6",
    "space-7": "s7",
    "space-8": "s8",
}

#: Named on purpose, with the reason, so this list is a decision rather than a dumping ground.
IGNORED = {
    # The DOM stacking order. tvOS has no z-index; a token carried with no consumer is worse than absent.
    "z-sticky": "DOM stacking order — tvOS has no z-index",
    "z-header": "DOM stacking order — tvOS has no z-index",
    "z-dropdown": "DOM stacking order — tvOS has no z-index",
    "z-popover": "DOM stacking order — tvOS has no z-index",
    "z-drawer": "DOM stacking order — tvOS has no z-index",
    "z-modal": "DOM stacking order — tvOS has no z-index",
    "z-toast": "DOM stacking order — tvOS has no z-index",
    "z-player": "DOM stacking order — tvOS has no z-index",
}

HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
RGB_FUNCTION = re.compile(
    r"^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([0-9.]+)\s*)?\)$"
)
LENGTH = re.compile(r"^(\d+(?:\.\d+)?)px$")


class ParseError(Exception):
    """A value (or a property) this generator does not understand. ⚠ Never a warning — see the header."""


def parse_colour(value: str) -> tuple[float, float, float, float]:
    """`#rrggbb`, `#rgb`, `#rrggbbaa` or `rgba(r, g, b, a)` → four 0…1 components."""
    text = value.strip()
    if HEX.match(text):
        digits = text[1:]
        if len(digits) == 3:
            digits = "".join(character * 2 for character in digits)
        if len(digits) == 6:
            digits += "ff"
        return tuple(int(digits[i:i + 2], 16) / 255.0 for i in (0, 2, 4, 6))  # type: ignore[return-value]
    match = RGB_FUNCTION.match(text)
    if match:
        red, green, blue, alpha = match.groups()
        return (int(red) / 255.0, int(green) / 255.0, int(blue) / 255.0,
                float(alpha) if alpha is not None else 1.0)
    raise ParseError(f"not a colour this generator understands: {value!r}")


def parse_length(value: str) -> float:
    """`12px` → 12.0. ⚠ A bare number is refused: `--radius-sm: 6` and `--radius-sm: 6px` differ by a
    unit, and silently assuming pixels is how a value ships that is six times too large."""
    match = LENGTH.match(value.strip())
    if not match:
        raise ParseError(f"not a px length this generator understands: {value!r}")
    return float(match.group(1))


def read_tokens(css_text: str) -> dict[str, str]:
    """Every declaration in the FIRST `:root` block, in file order."""
    block = ROOT_BLOCK.search(css_text)
    if not block:
        raise ParseError("no `:root { … }` block in the CSS — nothing to read")
    tokens: dict[str, str] = {}
    for name, value in DECLARATION.findall(block.group("body")):
        # ⚠ First wins, and duplicates are an ERROR rather than a silent overwrite: two `--accent`
        # declarations in one block is exactly the drift this file exists to make impossible.
        if name in tokens:
            raise ParseError(f"--{name} is declared twice in :root")
        tokens[name] = value.strip()
    if not tokens:
        raise ParseError("the `:root` block declared no custom properties")
    return tokens


def swift_number(value: float) -> str:
    """A Double literal that is exactly the CSS number — a fraction where one is honest.

    ⚠ `8/255` is not `0.0314`: the generator emits the ARITHMETIC so the component is the same value
    the browser computes rather than a rounded copy of it. A colour six decimal places off is invisible,
    but a habit of rounding is not — the next token it rounds might be a spacing.
    """
    if value == int(value):
        return f"{int(value)}.0"
    return repr(value)


def swift_colour(name: str, value: str) -> str:
    red, green, blue, alpha = parse_colour(value)
    return ((f"        static let {name} = RGBAColor(red: {swift_number(red * 255)} / 255.0,\n"
             f"                                       green: {swift_number(green * 255)} / 255.0,\n"
             f"                                       blue: {swift_number(blue * 255)} / 255.0,\n"
             f"                                       alpha: {swift_number(alpha)})"))


def render(tokens: dict[str, str], source: str) -> str:
    """The whole generated file, as text."""
    unknown = sorted(
        name for name in tokens
        if name not in COLOURS and name not in RADII and name not in SPACES and name not in IGNORED
    )
    if unknown:
        raise ParseError(
            "these CSS custom properties are neither mapped nor explicitly ignored: "
            + ", ".join(f"--{name}" for name in unknown)
            + " — add each to COLOURS/RADII/SPACES, or to IGNORED with its reason"
        )

    missing = sorted(
        name for name in list(COLOURS) + list(RADII) + list(SPACES) if name not in tokens
    )
    if missing:
        raise ParseError(
            "the CSS no longer declares: " + ", ".join(f"--{name}" for name in missing)
            + " — the mapping is stale, and a token that vanished is a brand change, not a typo"
        )

    colours = "\n".join(swift_colour(COLOURS[name], tokens[name]) for name in COLOURS)
    radii = "\n".join(f"        static let {RADII[name]}: CGFloat = {swift_number(parse_length(tokens[name]))}"
                      for name in RADII)
    spaces = "\n".join(f"        static let {SPACES[name]}: CGFloat = {swift_number(parse_length(tokens[name]))}"
                       for name in SPACES)
    ignored = "\n".join(f"//   · --{name} — {reason}" for name, reason in IGNORED.items())

    return f'''// ⚠⚠ GENERATED FILE — DO NOT EDIT BY HAND, and do not hand-copy a hex in beside it.
//
// Source of truth: {source}
// Regenerate:      python3 apple/scripts/generate-design-tokens.py
// Drift gate:      python3 apple/scripts/check-design-tokens.py   (requires this file to be a no-op diff)
//
// ⚠⚠ WHY THIS IS GENERATED RATHER THAN TRANSCRIBED. The tvOS buildspec's §1 colour table claims to be
// extracted from this app's web UI. It is not: measured 2026-09-19, **8 of its 10 values were wrong,
// including the brand accent** — it specified gold `#F2B93A` where the app is `#ffc400`
// (`docs/TVOS_UX_PLAN.md` §0.1). A hand-copied table also has no way to notice the web app changing. So
// the CSS custom properties are the source, this file is generated from them, and a gate fails the round
// the moment the two drift — the same trade `docs/api/openapi.v1.json` makes for the wire format.
//
// ⚠ This file is `Foundation`-only ON PURPOSE, so `apple/scripts/check-apple-typecheck.sh` compiles it on
// Linux. It carries NUMBERS, not `SwiftUI.Color` — the bridge to SwiftUI lives in `Design/DesignColours.swift`,
// which is a mechanical conversion with no rule in it to run.
//
// ⚠ A tvOS-only difference does NOT belong here — it belongs in `Design/TVTokens.swift`, and it carries
// its reason. A value migrating from there into this file stops being a tvOS decision and becomes a brand
// change that affects the phone and the web.
//
// ⚠ NOT generated, deliberately:
{ignored}

import Foundation

/// A colour as four 0…1 components.
///
/// ⚠ The PARSING happened in Python, at generation time: this type holds numbers, so there is no hex
/// parser in the app to be wrong about a three-digit hex or an alpha channel. `Equatable` for tests,
/// `Sendable` because a token table is a constant.
struct RGBAColor: Equatable, Sendable {{
    let red: Double
    let green: Double
    let blue: Double
    let alpha: Double
}}

/// The web app's palette, radii and spacing — generated, never transcribed.
enum DesignTokens {{

    /// `index.css`'s colour foundation (§2.3). ⚠ These are the WEB app's values. Where tvOS deliberately
    /// differs, the difference is in `TVTokens` with its reason attached.
    enum Colour {{
{colours}
    }}

    /// `index.css`'s radii (§41).
    enum Radius {{
{radii}
    }}

    /// `index.css`'s spacing scale (§41).
    enum Space {{
{spaces}
    }}
}}
'''


def find_css_path(path: pathlib.Path) -> str:
    """The path as it should read in the generated header — repo-relative when we can tell.

    ⚠ A generated header naming an absolute path from somebody's machine would make the drift check
    pass here and fail on his Mac for a reason that has nothing to do with the tokens.
    """
    try:
        return path.resolve().relative_to(REPO).as_posix()
    except ValueError:
        return str(path)


def selftest() -> int:
    """⚠ A generator that has only ever been run on the happy path is a draft. These are the fixtures the
    parser's two branches (hex and `rgba()`) and its two refusals are proved on."""
    failures: list[str] = []

    def expect(label: str, got, want) -> None:
        if got != want:
            failures.append(f"{label}: got {got!r}, want {want!r}")

    expect("a 6-digit hex", parse_colour("#ffc400"), (1.0, 196 / 255.0, 0.0, 1.0))
    expect("a 3-digit hex", parse_colour("#fff"), (1.0, 1.0, 1.0, 1.0))
    expect("an 8-digit hex carries alpha", parse_colour("#00000080"), (0.0, 0.0, 0.0, 128 / 255.0))
    expect("rgba() carries alpha", parse_colour("rgba(255, 255, 255, 0.08)"), (1.0, 1.0, 1.0, 0.08))
    expect("rgb() without alpha is opaque", parse_colour("rgb(8, 9, 11)"), (8 / 255.0, 9 / 255.0, 11 / 255.0, 1.0))
    expect("a px length", parse_length("12px"), 12.0)

    for label, call in [
        ("a bare number is refused, not assumed to be px", lambda: parse_length("12")),
        ("a non-colour is refused", lambda: parse_colour("var(--accent)")),
        ("an env() fallback is refused as a colour", lambda: parse_colour("env(safe-area-inset-top, 0px)")),
        ("duplicate declarations are refused",
         lambda: read_tokens(":root { --accent: #fff; --accent: #000; }")),
        ("an unmapped token is refused",
         lambda: render({"brand-new-thing": "#fff"}, "fixture")),
        ("a vanished token is refused",
         lambda: render({name: "#fff" for name in list(COLOURS) + list(RADII) + list(SPACES)
                         if name != "accent"}, "fixture")),
    ]:
        try:
            call()
        except ParseError:
            continue
        failures.append(f"{label}: it was accepted")

    if failures:
        print("SELFTEST FAILED — the parser does not do what its header claims:")
        for line in failures:
            print(f"  · {line}")
        return 1
    print("selftest: 6 parses and 6 refusals, all as claimed.")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Generate the tvOS design tokens from the web app's CSS.")
    parser.add_argument("--css", type=pathlib.Path, default=DEFAULT_CSS)
    parser.add_argument("--out", type=pathlib.Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true",
                        help="write nothing; fail if the file on disk differs from a fresh generation")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()

    if not args.css.exists():
        print(f"no CSS at {args.css} — the token source is gone.", file=sys.stderr)
        return 2

    try:
        generated = render(read_tokens(args.css.read_text(encoding="utf-8")), find_css_path(args.css))
    except ParseError as error:
        print(f"cannot generate design tokens: {error}", file=sys.stderr)
        return 1

    if args.check:
        if not args.out.exists():
            print(f"DRIFT — {args.out} does not exist; run the generator.", file=sys.stderr)
            return 1
        current = args.out.read_text(encoding="utf-8")
        if current == generated:
            print(f"no drift — {args.out} is exactly what {args.css} generates.")
            return 0
        print(f"DRIFT — {args.out} is not what {args.css} generates.", file=sys.stderr)
        import difflib
        for line in list(difflib.unified_diff(current.splitlines(), generated.splitlines(),
                                              "on disk", "regenerated", lineterm=""))[:40]:
            print(line, file=sys.stderr)
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(generated, encoding="utf-8")
    print(f"wrote {args.out} from {args.css}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
