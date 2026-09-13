import { describe, expect, it } from "vitest";

import { buttonClass, type ButtonVariant } from "./Button";

/**
 * The companion guard to `tools/check_cta_alignment.py`.
 *
 * The browser check proves the pair is ONE SIZE *today*; this pins the reason it stays that way —
 * that no variant grows its own height, padding, radius or font-size. His report (2026-09-13) came
 * from exactly that: two hand-rolled strings where the primary had `h-8` and the secondary `py-1.5`,
 * so the pair rendered 32.00px next to 30.50px. A variant may change FILL, COLOUR and WEIGHT only.
 *
 * Falsified before being trusted: adding `py-1.5` (or `text-[13px]`, or `h-9`) to ONE variant makes
 * these fail loudly — see the `drift` case below, which is the assertion that bites.
 */
const VARIANTS: ButtonVariant[] = ["primary", "secondary", "ghost"];

/** Every class that decides a button's BOX — a variant adding one of these is the drift this file
 *  exists to catch. (Weight, colour, border-style and hover states are deliberately NOT here.) */
const BOX_CLASS =
  /^(?:-?(?:m|p)[trblxy]?-\S+|h-\S+|w-\S+|min-h-\S+|min-w-\S+|max-(?:h|w)-\S+|gap-\S+|rounded\S*|text-(?:xs|sm|base|lg|xl|\[[^\]]+\]))/;

/** The tokens every variant must share, named so a failure says WHICH one moved. */
const SHARED = [
  "inline-flex",
  "h-8",
  "items-center",
  "justify-center",
  "gap-1.5",
  "rounded-lg",
  "px-3",
  "text-[11px]",
  "shrink-0",
];

const boxTokens = (variant: ButtonVariant): string[] =>
  buttonClass(variant)
    .split(/\s+/)
    .filter((t) => BOX_CLASS.test(t))
    .sort();

describe("Button sizing tokens", () => {
  it("gives every variant the same box geometry", () => {
    for (const variant of VARIANTS) {
      const tokens = buttonClass(variant).split(/\s+/);
      for (const shared of SHARED) {
        expect(tokens, `${variant} is missing ${shared}`).toContain(shared);
      }
    }
  });

  it("lets a variant drift ONLY in fill, colour and weight", () => {
    // The set of box-deciding classes must be identical across variants. `h-8`/`px-3`/`rounded-lg`
    // are shared, so the sets are equal — a variant that adds `py-1.5`, `h-9`, `text-[13px]` or
    // drops `h-8` changes its own set and fails here, naming both sides.
    const reference = boxTokens("primary");
    for (const variant of VARIANTS) {
      expect(boxTokens(variant), `${variant} must not carry its own box geometry`).toEqual(reference);
    }
  });

  it("keeps the pair's fill and weight distinct, so the hierarchy survives the fix", () => {
    expect(buttonClass("primary")).toContain("bg-accent");
    expect(buttonClass("secondary")).not.toContain("bg-accent");
    expect(buttonClass("primary")).toContain("font-bold");
    expect(buttonClass("secondary")).toContain("font-semibold");
  });

  it("appends caller classes without dropping the shared geometry", () => {
    const custom = buttonClass("secondary", "w-full");
    for (const shared of SHARED) expect(custom.split(/\s+/)).toContain(shared);
    expect(custom.split(/\s+/)).toContain("w-full");
  });
});
