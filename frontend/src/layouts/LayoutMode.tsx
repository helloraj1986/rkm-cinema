/**
 * The layout switch — the ONE place that decides whether a phone-shaped layout or the
 * existing desktop layout is presented (MOBILE_FIRST_UI_PLAN §3/§4).
 *
 * ⚠ **This is a PRESENTATION switch. It is not a capability switch.** `bridgeAvailable()`
 * gates what the app OFFERS (downloads, play-offline); this gates only which arrangement of
 * chrome is on screen. A phone browser on the tailnet gets the mobile layout and no offline
 * affordances; the iOS shell at 1200px gets the desktop layout. The two facts never mix.
 *
 * ⚠ **Two modes, not three** (brief §2a/§4). A tablet is NOT a mode. Inside the mobile layout
 * the phone/tablet difference is CSS only — `--m-grid-cols`, the type step, the sheet's
 * max-width. There is deliberately no `isTablet` anywhere in the app, and adding one is the
 * one change that would take this from "one shell" to "three things to keep in sync".
 *
 * ⚠ **No user-agent sniffing.** The viewport decides. A UA string would make the layout a
 * property of the DEVICE instead of the window, which is wrong on a desktop browser resized
 * narrow, wrong in an iPad split view, and wrong the day Apple ships a new one.
 */

import {
  createContext,
  useContext,
  useLayoutEffect,
  useSyncExternalStore,
  type ReactNode,
} from "react";

export type LayoutMode = "mobile" | "desktop";

/**
 * ⚠ **The ONE number.** Below 1024px is `mobile` — the phone AND the tablet.
 *
 * It is 1023 rather than 1024 so the query is `max-width` and the two sides partition the
 * integer pixel line exactly: 1023 is mobile, 1024 is desktop, and no width is in both or
 * neither.
 *
 * ⚠ Tailwind's `lg` is 1024px, so the CSS boundary and this constant agree **by
 * construction**. The constant exists so a later edit cannot move one and leave the other:
 * the mobile shell's `lg:hidden`/`lg:flex` and this number are the same line, and
 * `LayoutMode.test.tsx` reads both and fails if they ever disagree.
 */
export const MOBILE_MAX_PX = 1023;

/** The exact media query. Built from the constant, never typed out twice. */
export const MOBILE_MEDIA_QUERY = `(max-width: ${MOBILE_MAX_PX}px)`;

/** The Tailwind breakpoint half of the pair — `lg` in `tailwind.config.js` is 1024px. */
export const DESKTOP_MIN_PX = MOBILE_MAX_PX + 1;

/**
 * The rule, PURE — no React, no `matchMedia`, testable in node.
 *
 * There is exactly ONE input because there is exactly ONE question: did the viewport match?
 * Anything that would need a second input (orientation, platform, device class) is either a
 * media query inside the mobile shell or a fact this component tree must not have.
 */
export function layoutModeFor(matchesMobile: boolean): LayoutMode {
  return matchesMobile ? "mobile" : "desktop";
}

/* ---------------------------------------------------------------------------
 * One MediaQueryList per query, shared by every subscriber.
 *
 * ⚠ This is not premature optimisation. The provider and every consumer call the hook (hooks
 * cannot be called conditionally, and several legitimate consumers read the mode without being
 * inside the provider — the harness frames mount `Header`/`Sidebar`/`MobileNav` bare). Without
 * a hub that is one `MediaQueryList` and one listener per consumer; with it, one of each per
 * query, however many components ask. `matchMedia` listeners are cheap but not free, and a
 * resize fires every one of them.
 * --------------------------------------------------------------------------- */
interface QueryHub {
  mql: MediaQueryList;
  listeners: Set<() => void>;
}

const HUBS = new Map<string, QueryHub>();

function hubFor(query: string): QueryHub | null {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return null;
  const existing = HUBS.get(query);
  if (existing) return existing;
  const hub: QueryHub = { mql: window.matchMedia(query), listeners: new Set() };
  HUBS.set(query, hub);
  return hub;
}

/** The listener that fans a hub's one native event out to its subscribers. */
function notify(hub: QueryHub) {
  return () => {
    // Copy first: a listener may unsubscribe during its own notification.
    for (const listener of Array.from(hub.listeners)) listener();
  };
}

function subscribeToQuery(query: string, onChange: () => void): () => void {
  const hub = hubFor(query);
  if (!hub) return () => {};
  if (hub.listeners.size === 0) {
    // `addEventListener` is the modern form; older WebKit only has the deprecated
    // `addListener`. Both are attached lazily so a hub with no subscribers holds no event.
    if (typeof hub.mql.addEventListener === "function") {
      hub.mql.addEventListener("change", notify(hub));
    } else if (typeof hub.mql.addListener === "function") {
      hub.mql.addListener(notify(hub));
    }
  }
  hub.listeners.add(onChange);
  return () => {
    hub.listeners.delete(onChange);
  };
}

function snapshotForQuery(query: string): boolean {
  const hub = hubFor(query);
  // No `matchMedia` (a node test, an ancient engine): desktop. Failing to the layout the app
  // has always had is the only safe direction — a phone that reads "desktop" is a worse app,
  // a desktop that reads "mobile" is a broken one.
  return hub ? hub.mql.matches : false;
}

/**
 * Subscribe to the viewport. Reactive to a resize, a rotation and an iPad split-view resize —
 * all three arrive as the same `change` event, which is why there is no `resize` listener and
 * no `window.innerWidth` arithmetic anywhere.
 */
function useMediaLayoutMode(): LayoutMode {
  const matches = useSyncExternalStore(
    (onChange) => subscribeToQuery(MOBILE_MEDIA_QUERY, onChange),
    () => snapshotForQuery(MOBILE_MEDIA_QUERY),
    // SPA only — but `useSyncExternalStore` demands the third argument whenever it might
    // hydrate, and the desktop layout is the honest server answer.
    () => false,
  );
  return layoutModeFor(matches);
}

const LayoutModeContext = createContext<LayoutMode | null>(null);

/**
 * Mounted ONCE, in `main.tsx`, above the router and below the query/auth providers.
 *
 * ⚠ **That position is load-bearing.** Above the router, so crossing 1024px re-renders the
 * routed element without remounting anything; below `QueryClientProvider` and `AuthProvider`,
 * so the React Query cache and the session survive the swap. That is what makes "no refetch
 * storm and no sign-out on rotation" true rather than hoped for — and
 * `tools/check_mobile_layout_switch.py` measures it.
 *
 * It also publishes `document.documentElement.dataset.layout`, which is how the scoped CSS in
 * `styles/index.css` reaches things OUTSIDE the mobile shell's own element — the `html`/`body`
 * rules that stop a rubber-band scroll revealing a white page behind a dark UI.
 */
export function LayoutModeProvider({ children }: { children: ReactNode }) {
  const mode = useMediaLayoutMode();

  useLayoutEffect(() => {
    document.documentElement.dataset.layout = mode;
    return () => {
      // Leaving the attribute behind after unmount would keep the mobile CSS applied to a tree
      // that no longer has a provider. (In practice this only runs in a test or a harness frame.)
      delete document.documentElement.dataset.layout;
    };
  }, [mode]);

  return <LayoutModeContext.Provider value={mode}>{children}</LayoutModeContext.Provider>;
}

/**
 * The ONE consumer hook. Components never call `matchMedia` themselves.
 *
 * ⚠ It falls back to the media query when there is no provider rather than throwing. That is
 * not a convenience: `frontend/harness/*.html` mount real components (`Header`, `Sidebar`,
 * `MobileNav`, `Player`) bare, and a hook that required a provider would break every existing
 * browser gate at once. Inside a provider the context wins, so the value is the provider's —
 * one source of truth where one exists, an honest reading where one does not.
 */
export function useLayoutMode(): LayoutMode {
  const fromContext = useContext(LayoutModeContext);
  const fromMedia = useMediaLayoutMode();
  return fromContext ?? fromMedia;
}

/** Sugar for the small number of legitimate boolean reads (the shell, the player frame). */
export function useIsMobile(): boolean {
  return useLayoutMode() === "mobile";
}
