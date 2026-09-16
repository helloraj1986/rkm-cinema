import { Outlet, ScrollRestoration } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { Header } from "./Header";
import { MobileNav } from "./MobileNav";
import { Toaster } from "../../features/watchlist/Toaster";
import { OfflineWiring } from "../../features/offline/OfflineWiring";
import { useLayoutMode } from "../../layouts/LayoutMode";

/**
 * App shell (design spec §4/§38/§76): the sidebar is sticky with its own fixed
 * height (content scrolls past it), the 64px top bar is sticky/blurred, and a
 * mobile bottom navigation bar takes over under lg. The full-screen player and
 * toasts layer above via the z-index system (spec §75).
 *
 * ⚠ TWO ARRANGEMENTS, ONE COMPONENT (MOBILE_FIRST_UI_PLAN M1). The shell used to be one layout with
 * breakpoints doing the hiding; it is now one layout whose two pieces of chrome are chosen by
 * `useLayoutMode()`. What did NOT change is that the page in the middle is the SAME element at every
 * size — see the note in the body about why that matters for anything you touch here.
 *
 * ScrollRestoration (spec §60): the data router saves scroll per history
 * entry, so Back from an item page returns to the folder grid at the same
 * scroll position (filters themselves live in the URL — see folder views).
 */
export function AppShell() {
  // ⚠ The shell SWAPS ARRANGEMENT without remounting anything. That is why this is one component
  // rather than `{mode === "mobile" ? <MobileShell/> : <DesktopShell/>}`: swapping the two trees
  // would move `<Outlet/>` to a new position and React would unmount the routed view on every
  // rotation, throwing away its state and refetching what it needs. Here the conditionals are
  // SIBLINGS of the Outlet's ancestors, so crossing the boundary changes the chrome around the page
  // and leaves the page itself alone. ⚠ `tools/check_mobile_layout_switch.py` scenario C measures
  // exactly this: 1280 -> 390 -> 834 -> 1280 remounts neither the shell nor the routed view.
  const mode = useLayoutMode();
  const mobile = mode === "mobile";
  return (
    <div
      className={`min-h-dvh bg-canvas text-zinc-100${mobile ? " m-root" : ""}`}
      // ⚠ The mobile shell's own handle. The scoped CSS in `styles/index.css` keys off
      // `[data-layout="mobile"]`, which covers everything inside `html`; `.m-root` is the narrower
      // handle for the handful of rules that belong to the shell's OWN subtree. `data-shell` is here
      // for the browser tools and for reading a screenshot's provenance — nothing styles it.
      data-shell={mode}
    >
      <ScrollRestoration />
      <div className="flex min-h-dvh">
        {!mobile && <Sidebar />}
        <div className="flex min-w-0 flex-1 flex-col">
          <Header />
          <main className="min-w-0 flex-1">
            {/* ⚠ THE CLEARANCE IS DERIVED, NOT A NUMBER. `lg:pb-12`, not `md:pb-12`, because the bar
                now exists below 1024px rather than below 768px. And below lg the padding is
                `--m-nav-h + --rkm-safe-bottom + 32px`: bar height, plus the device's own bottom
                inset, plus a gap.

                ⚠ It used to be a flat `pb-24` (96px), and that is what put the bar ON TOP OF the
                page on his phone: the bar is 64px of content PLUS a 34px home-indicator inset = 98px
                on a notched iPhone, so 96px of padding left the page 2px underneath it. ⚠ A hardcoded
                number cannot be right on every device, and this sandbox cannot measure a non-zero
                inset at all (`env(safe-area-inset-bottom)` is 0px in every desktop browser) — so the
                only fix that works is one where the inset is part of the expression by construction.
                On an inset-free device this resolves to 96px, which is what it has always looked like. */}
            <div className="mx-auto w-full max-w-[1720px] px-4 pb-[calc(var(--m-nav-h,64px)_+_var(--rkm-safe-bottom,0px)_+_2rem)] pt-4 sm:px-6 lg:pb-12 lg:px-8 xl:px-10">
              <Outlet />
            </div>
          </main>
        </div>
      </div>
      {mobile && <MobileNav />}
      {/* ⚠ Renders nothing. It starts the offline session (the bridge subscription and the progress
          spool's replay loop), which has to be running when no offline screen is on screen: a film
          watched with the Wi-Fi off must reach Continue Watching without anyone opening Downloads
          first. Mounted HERE, once, so it is bound to the session rather than to a route — and ⚠ it
          is deliberately OUTSIDE the mode conditional: a rotation must not restart the spool's
          replay loop, and a phone that becomes a desktop (a maximised window) must not lose the
          positions it is holding. */}
      <OfflineWiring />
      <Toaster />
    </div>
  );
}
