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
            {/* ⚠ `lg:pb-12`, not `md:pb-12`: the 96px bottom padding is what clears the fixed tab
                bar, and the bar now exists below 1024px rather than below 768px. If these two ever
                disagree the last row of every grid hides under the bar — on a tablet, silently. */}
            <div className="mx-auto w-full max-w-[1720px] px-4 pb-24 pt-4 sm:px-6 lg:pb-12 lg:px-8 xl:px-10">
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
