import { Dialog } from "../../components/ui/Dialog";
import { Icon } from "../../components/ui/Icon";
import { ItemDetailContent } from "./ItemDetail";
import { useLibraryOutlet } from "./LibraryLayout";

/**
 * The item detail as a MODAL — the app's one presentation for "show me this title" (his Bug 5,
 * 2026-09-13).
 *
 * What was wrong: clicking a search result (or a poster card) NAVIGATED to `/library/item/:id`, a
 * full page. Every symptom he reported followed from that — no scrim (a page has none), the content
 * block sitting in the right ~67% of a wide screen with the sidebar and its gutter exposed, the
 * hero's edges reading as a hard-cut panel, no close button, and the page behind still live. He asked
 * for a modal, and the app already HAS one: `components/ui/Dialog` supplies the scrim
 * (`bg-black/65` + blur), the centred rounded panel with `shadow-modal`, the Esc key, backdrop-click
 * close, body scroll LOCK and a focus trap. Item details were the only surface not using it.
 *
 * Why here and not new modal CSS: his own note was right — "the fix is routing, not new modal CSS".
 * The ROUTE now renders this modal, so every entry point (search results, poster cards, the hero's
 * Details, a deep link) gets the same treatment with no call-site changes, and the URL stays the
 * source of truth: Back and refresh still work, Esc/backdrop/X call `onClose`, which the route maps
 * back to history.
 *
 * ⚠ Layering with the player: the player is closed by its OWN Esc handler, so this dialog must not
 * treat Esc as its own while a player is open — otherwise one keypress would close both. The page
 * this replaced carried the same guard (`!playerRef.current`).
 */
export function ItemDetailModal({ itemId, onClose }: { itemId: string; onClose: () => void }) {
  const { player, startMovie, startEpisode, toggleWatched } = useLibraryOutlet();

  // Ignore Esc/backdrop while the player owns the screen (it has its own Esc).
  const close = () => {
    if (!player) onClose();
  };

  return (
    <Dialog
      labelledBy="item-detail-title"
      onClose={close}
      panelClassName="max-w-5xl"
      // The player owns Escape while it is open — without this the dialog would swallow the key in
      // the capture phase and NEITHER layer would close (measured, 2026-09-13).
      canEscapeClose={() => !player}
    >
      <button
        type="button"
        aria-label="Close"
        title="Close"
        data-testid="item-detail-close"
        onClick={onClose}
        className="absolute right-3.5 top-3.5 z-10 grid h-9 w-9 place-items-center rounded-full border border-white/10 bg-black/55 text-zinc-200 backdrop-blur-md transition hover:bg-black/80 hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      >
        <Icon name="close" size={16} />
      </button>

      {/* Content padding on all sides: the panel is the shell, so nothing may touch its edges
          (his report). The hero keeps its own rounded card INSIDE that padding. */}
      <div className="px-5 pb-5 pt-5 sm:px-7 sm:pb-7 sm:pt-7">
        <ItemDetailContent
          itemId={itemId}
          inModal
          onBack={onClose}
          onPlayMovie={startMovie}
          onPlayEpisode={startEpisode}
          onToggleWatched={toggleWatched}
        />
      </div>
    </Dialog>
  );
}
