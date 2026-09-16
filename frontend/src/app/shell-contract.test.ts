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

  it("the page's clearance for the bottom bar is DERIVED, not a number", () => {
    // ⚠ THIS IS THE PIN FOR A REPORTED BUG, and it exists because the sandbox CANNOT reproduce it.
    // His report (2026-09-16): "bottom bar now sits on top of the pages". The mechanism: the content
    // padding was a flat `pb-24` (96px), and the bar is 64px of content PLUS the device's own
    // home-indicator inset — 98px on a notched iPhone — so the page's last row sat 2px UNDER the bar.
    // ⚠ `env(safe-area-inset-bottom)` resolves to 0px in every desktop browser, so a browser check
    // here sees a page that clears the bar perfectly while his phone does not. The only half that can
    // be pinned in this container is the DERIVATION, which is what this test does.
    //
    // ⚠ It asserts on the CLASS ATTRIBUTE, not on the file. The first version scanned the whole source
    // for `pb-24` and went red on the comment above — which NAMES the bug it is about. A rule that
    // flags its own documentation teaches people to delete the documentation.
    const shell = read("layout/AppShell.tsx");
    const nav = read("layout/MobileNav.tsx");
    const css = read("../styles/index.css");

    const contentClass = shell.match(/className="(mx-auto w-full max-w-\[1720px\][^"]*)"/)?.[1];
    expect(contentClass, "the page container's className was not found").toBeTruthy();
    // The padding must be derived from the bar's height AND the device's own inset.
    expect(contentClass).toContain("var(--m-nav-h");
    expect(contentClass).toContain("var(--rkm-safe-bottom");
    // ⚠ A flat bottom padding IS the bug: no fixed number can be right on every device.
    expect(contentClass).not.toMatch(/(?:^|\s)pb-24(?:\s|$)/);
    // …and the desktop side still hands the space back.
    expect(contentClass).toContain("lg:pb-12");

    // The bar's own row reads the token, so the token is the single source of its height.
    const barClass = nav.match(/className="(mx-auto flex h-\[var\(--m-nav-h[^"]*)"/)?.[1];
    expect(barClass, "the tab bar row no longer reads --m-nav-h").toBeTruthy();

    // The token is 64px. It was 56px, which disagreed with the bar's own `h-16` by 8px — a token that
    // lies is worse than no token, because everything deriving a clearance from it is wrong by that
    // difference and nothing says so.
    expect(css).toMatch(/--m-nav-h:\s*64px/);
    expect(css).not.toMatch(/--m-nav-h:\s*56px/);
  });

  it("full screen is the viewport itself, at every size — nothing is measured", () => {
    // ⚠ The player shell IS the screen: `fixed; inset: 0` + `100dvh` stretches it to whatever
    // display this is, and the safe-area insets come from the browser — so the same CSS is
    // correct on a phone, an iPad, a laptop and a TV-sized window. A number in here would be a
    // device the layout is right about and every other device it is wrong about.
    const css = read("../styles/index.css");
    expect(css).toContain("height: 100dvh");
    expect(css).toContain("env(safe-area-inset-top");
    expect(css).toContain("env(safe-area-inset-bottom");
    expect(css).toContain("--rkm-safe-left");
    expect(css).toContain("--rkm-safe-right");
    // A measured height (px/vh-only) would put the transport band under a browser's toolbar.
    expect(css).not.toMatch(/\.rkm-player\s*\{[^}]*height:\s*\d+px/);

    // …and the PICTURE is fitted by the browser too: one `object-fit` class, never a size.
    const player = read("../features/playback/Player.tsx");
    expect(player).toContain("videoFitClass(fit)");
    // ⚠ Neither literal may live in the component: the class comes from the choice map, which is
    // the only place that knows what "fill" costs.
    expect(player).not.toContain("object-contain");
    expect(player).not.toContain("object-cover");
    expect(read("../features/playback/lib.ts")).toContain(
      'return fit === "fill" ? "object-cover" : "object-contain"',
    );
  });
});
