/**
 * Harness: the REAL `MediaCard`, to pin WHAT A POSTER IS ALLOWED TO SAY ABOUT WATCHED STATE.
 *
 * His report (2026-09-17, `KNOWN_ISSUES` §2): *"on the poster when you click the right tick button
 * (i think its for watched) there are two green ticks and then the button inside (details page)
 * watched button becomes redundant"*. One fact was drawn twice on one card — the `WatchedTick` MARKER
 * on the art AND the bottom row's green TOGGLE, both driven by `item.played` — and offered a third
 * time on the details page.
 *
 * His rule: the DETAILS view owns the watched control; the poster only REFLECTS status. So this frame
 * mounts the same component in both states and `tools/check_poster_watched.py` asserts the resulting
 * shape: exactly ONE watched indicator on a played card, NO watched control on any card, and no
 * watched verb in the ⋯ menu.
 *
 * ⚠ Why the CONSOLE is not enough, and why this is not a unit test: the defect was a rendered
 * duplicate — two elements that both claimed to mean "watched" — and a unit test over props would have
 * been satisfied by the pair. What has to hold is a count of what the browser actually painted, plus
 * where the surviving marker sits (on the ART, not in the action row), which is geometry.
 *
 * ⚠ Both states are mounted on PURPOSE. A frame that rendered only a played card could not tell
 * "the marker follows `played`" from "the marker is always drawn".
 */
import ReactDOM from "react-dom/client";
import { MemoryRouter } from "react-router-dom";

import type { MediaItem } from "../src/lib/api/client";
import { MediaCard } from "../src/features/library/MediaCard";
// The app's REAL stylesheet (see cta-frame.tsx): without it any geometry measured here is unstyled
// and therefore not evidence of anything.
import "../src/styles/index.css";

/** A played film: the state that used to draw BOTH the marker and the toggle. */
const PLAYED_MOVIE: MediaItem = {
  item_id: "p-played",
  title: "A Played Film",
  year: 1999,
  type: "movie",
  played: true,
  playback_position: 640,
  runtime: 8160,
  play_count: 1,
};

/** An untouched film: no marker, and the ⋯ menu's first verb is "Play" rather than "Replay". */
const UNPLAYED_MOVIE: MediaItem = {
  item_id: "p-unplayed",
  title: "An Unwatched Film",
  year: 2001,
  type: "movie",
  played: false,
  playback_position: 0,
  runtime: 7200,
  play_count: 0,
};

/** A played SERIES, because the series card draws a different CTA (the "Episodes" pill). */
const PLAYED_SERIES: MediaItem = {
  item_id: "p-series",
  title: "A Played Series",
  year: 2020,
  type: "tv",
  played: true,
  playback_position: 1200,
  runtime: 3600,
  play_count: 3,
};

const ITEMS = [PLAYED_MOVIE, UNPLAYED_MOVIE, PLAYED_SERIES];

function Frame() {
  return (
    <MemoryRouter initialEntries={["/"]}>
      <div className="min-h-dvh bg-canvas p-6 text-zinc-100">
        {/* `flex` rather than the app's grid: each card keeps its fixed rail width, so a rect
            measured here is the card's own and cannot be squeezed by a grid track. */}
        <section data-section="cards" className="flex items-start gap-6">
          {ITEMS.map((item) => (
            <MediaCard
              key={item.item_id}
              item={item}
              onQuickPlay={() => {}}
              onOpenDetail={() => {}}
            />
          ))}
        </section>
      </div>
    </MemoryRouter>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<Frame />);

/**
 * The measurements `tools/check_poster_watched.py` asserts on.
 *
 * ⚠ The MARKER is found by its `aria-label="Watched"` — the label the art badge carries so a screen
 * reader hears the same fact the eye sees. The TOGGLE is found by the two verbs it used to carry
 * (`Mark as watched` / `Mark as unplayed`), which is what makes "the control is gone" checkable rather
 * than a claim about the source.
 */
(window as unknown as { __probe: () => unknown }).__probe = () => {
  const cards = [...document.querySelectorAll('[data-testid="media-card"]')];

  const rect = (el: Element | null) => {
    if (!el) return null;
    const b = el.getBoundingClientRect();
    return { left: b.left, right: b.right, top: b.top, bottom: b.bottom, width: b.width, height: b.height };
  };

  const perCard = cards.map((card) => {
    const art = card.querySelector("div.aspect-\\[2\\/3\\]");
    const markers = [...card.querySelectorAll('[aria-label="Watched"]')];
    const toggles = [...card.querySelectorAll("button")].filter((b) =>
      // ⚠ BOTH spellings, and this is not tidiness: the REMOVED control said "Mark as unplayed" for a
      // played title while the details view's own control says "Mark as unwatched". A probe that knew
      // only the second word was blind to the duplicate on exactly the PLAYED card the report is
      // about — the first falsification run missed it for that reason, and only the unplayed fixture
      // came back red. Match the verb, not one spelling of it.
      /^Mark as (un)?(watched|played)$/.test(b.getAttribute("aria-label") ?? ""),
    );
    const menuTrigger = card.querySelector('button[aria-label^="More actions for"]');
    const markerRect = rect(markers[0] ?? null);
    const artRect = rect(art);
    const triggerRect = rect(menuTrigger);
    return {
      title: card.querySelector(".line-clamp-2")?.textContent?.trim() ?? "",
      hasArt: !!art,
      markers: markers.length,
      markerLabels: markers.map((m) => m.getAttribute("aria-label")),
      toggles: toggles.length,
      toggleLabels: toggles.map((t) => t.getAttribute("aria-label")),
      hasMenuTrigger: !!menuTrigger,
      // The marker must sit INSIDE the artwork: that is what makes it status on the poster rather
      // than a control in the action row.
      markerInsideArt: !!(markerRect && artRect &&
        markerRect.top >= artRect.top - 1 && markerRect.bottom <= artRect.bottom + 1 &&
        markerRect.left >= artRect.left - 1 && markerRect.right <= artRect.right + 1),
      // The ⋯ is the ONLY thing left in the bottom row, so it must sit at the row's RIGHT edge.
      menuTriggerRightGap: triggerRect && artRect ? artRect.right - triggerRect.right : null,
    };
  });

  return { cards: cards.length, perCard };
};

/**
 * Open one card's ⋯ menu and report what it offers.
 *
 * ⚠ It resolves in a `setTimeout`, not synchronously: React renders the portalled panel on the next
 * tick, so reading the DOM in the click's own frame finds nothing and would report an empty menu for
 * a menu that is perfectly alive.
 */
(window as unknown as { __openMenu: (i: number) => Promise<unknown> }).__openMenu = (i: number) =>
  new Promise((resolve) => {
    const cards = [...document.querySelectorAll('[data-testid="media-card"]')];
    const btn = cards[i]?.querySelector('button[aria-label^="More actions for"]');
    if (!btn) {
      resolve({ error: "no ⋯ trigger on that card" });
      return;
    }
    (btn as HTMLElement).click();
    setTimeout(() => {
      const menu = document.querySelector('div[role="menu"]');
      resolve({
        open: !!menu,
        items: menu
          ? [...menu.querySelectorAll('button[role="menuitem"]')].map((b) => b.textContent?.trim() ?? "")
          : [],
      });
    }, 80);
  });
