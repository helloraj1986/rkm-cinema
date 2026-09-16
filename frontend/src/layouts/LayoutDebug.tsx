/**
 * `?layout=debug` — the readout M0's done-when asks for, and nothing else.
 *
 * ⚠ It renders NOTHING unless the query parameter is present. That is deliberate: a permanent
 * badge would be chrome the design did not ask for, and worse, it would be a second place that
 * renders the current mode — so a disagreement between the badge and the layout would be one
 * more thing to debug instead of the thing that tells you what is wrong.
 *
 * It reports four facts, because "which mode is it" alone does not distinguish the three ways
 * a layout switch can be wrong:
 *
 *   mode   — what `useLayoutMode()` says, i.e. what the app is BUILDING.
 *   match  — what `matchMedia` says right now, read directly, i.e. what the viewport IS.
 *   vw×vh  — the real inner size, so a device-scale/viewport mistake is visible.
 *   attr   — `document.documentElement.dataset.layout`, i.e. what the CSS is keyed off.
 *
 * ⚠ `mode` and `match` disagreeing is the interesting failure; `attr` disagreeing with `mode`
 * means the effect has not run or the provider is missing; `vw` disagreeing with what the
 * emulator claims means the viewport was never set.
 */

import { useLayoutMode, MOBILE_MAX_PX } from "./LayoutMode";

function readMatch(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return false;
  return window.matchMedia(`(max-width: ${MOBILE_MAX_PX}px)`).matches;
}

export function LayoutDebugReadout() {
  const mode = useLayoutMode();

  const on =
    typeof window !== "undefined" &&
    new URLSearchParams(window.location.search).get("layout") === "debug";
  if (!on) return null;

  const match = readMatch();
  const agree = (match ? "mobile" : "desktop") === mode;

  return (
    <div
      data-testid="layout-debug"
      data-mode={mode}
      data-matches={String(match)}
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        zIndex: 9999,
        padding: "2px 6px",
        font: "600 11px/1.4 ui-monospace, monospace",
        color: agree ? "#08090B" : "#08090B",
        background: agree ? "#FFC400" : "#FF5B5B",
        pointerEvents: "none",
      }}
    >
      {mode} · match={String(match)} · {window.innerWidth}×{window.innerHeight} · attr=
      {document.documentElement.dataset.layout ?? "unset"}
    </div>
  );
}
