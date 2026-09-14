import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * The iOS shell's safe-area contract — the two halves that must move TOGETHER, pinned because
 * neither a browser in the sandbox nor a unit test can see the result.
 *
 * His report (2026-09-14, iPad): *"the ui needs a bit of work"* — a **white band behind the status
 * bar**, because the shell's web view was inset to the safe area and the window's own (white)
 * background showed through in the gap. Fixing it takes four edits in two languages:
 *
 *   frontend/index.html        `viewport-fit=cover` — without it every `env(safe-area-inset-*)` is 0px
 *   AppRootView.swift          the web view `.ignoresSafeArea()` — the page fills the display
 *   Header.tsx                 the bar pads by `env(safe-area-inset-top)` — content clears the clock
 *   Info.plist                 `UIUserInterfaceStyle = Dark` — the status bar glyphs stay legible
 *                              over the page's #08090b
 *
 * ⚠ Any ONE of these can be dropped in isolation and the app still builds, still runs, and looks
 * fine in a desktop browser: the failure appears only on a device, and only visually. That is
 * exactly the class of change that silently rots, so it is asserted here — a plain read of the
 * files, which is all a node test can do about a trait that has no DOM.
 */
const here = fileURLToPath(new URL(".", import.meta.url));

const read = (relative: string) => readFileSync(`${here}${relative}`, "utf8");

describe("the iOS shell's safe-area contract", () => {
  it("the page asks for the whole display, so the insets are real", () => {
    const html = read("../../index.html");
    expect(html).toMatch(/name="viewport"[^>]*viewport-fit=cover/);
    // …and it must keep telling the browser it is a dark app, or the shell's band and the page
    // disagree about what colour "the background" is.
    expect(html).toContain('name="color-scheme" content="dark"');
  });

  it("the shell lets the page fill the display", () => {
    const root = read("../../../apple/ios/RKMCinema/App/AppRootView.swift");
    expect(root).toContain(".ignoresSafeArea()");
    // ⚠ The keyboard-only form was the old line: it insets the web view to the safe area, which is
    // what put a band of window background behind the status bar in the first place.
    expect(root).not.toContain(".ignoresSafeArea(.keyboard)");
  });

  it("the app forces dark, so the status bar is legible over the page", () => {
    const plist = read("../../../apple/ios/Config/Info.plist");
    expect(plist).toMatch(/<key>UIUserInterfaceStyle<\/key>\s*<string>Dark<\/string>/);
  });

  it("the top bar and the bottom nav make room for the insets those unlock", () => {
    expect(read("layout/Header.tsx")).toContain("env(safe-area-inset-top)");
    expect(read("layout/MobileNav.tsx")).toContain("env(safe-area-inset-bottom)");
    // ⚠ A FIXED height would let the padding eat the row instead of adding to it — on a notched
    // phone that leaves ~5px for the search field.
    expect(read("layout/Header.tsx")).toContain("min-h-16");
  });
});
