import { useCallback, useEffect, useRef } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { ItemDetailContent } from "./ItemDetail";
import { useLibraryOutlet } from "./LibraryLayout";

/**
 * /library/item/:itemId — the item's OWN dedicated page (PLEX_VIEWS_PLAN Phase 1):
 * the URL is the source of truth (deep-linkable, Back works, refresh keeps you
 * here). Chrome:
 * - Back button + Esc leave the page (Esc closes the full-screen player FIRST —
 *   the player overlay owns Esc while it is open, this page only fires when the
 *   player is closed; exactly as Plex layers the player over the item page).
 * - Scrolling resets on item change so each title opens at its hero.
 */
export function ItemDetailPage() {
  const { itemId = "" } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const { player, startMovie, startEpisode, toggleWatched } = useLibraryOutlet();

  // Refs so the keydown listener stays stable while reading LIVE player state.
  const playerRef = useRef(player);
  playerRef.current = player;

  const goBack = useCallback(() => {
    // Deep link (location.key === "default"): no in-app history to unwind.
    if (location.key !== "default") {
      navigate(-1);
    } else {
      navigate("/library/home", { replace: true });
    }
  }, [location.key, navigate]);

  const goBackRef = useRef(goBack);
  goBackRef.current = goBack;

  // Esc: player closes itself first; only when no player is open does Esc leave
  // the page. (Player's own window listener closes it; this one is inert then.)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !playerRef.current) goBackRef.current();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // A new title (or a direct refresh of a deep link) opens at the hero.
  useEffect(() => {
    window.scrollTo({ top: 0 });
  }, [itemId]);

  return (
    <div className="flex flex-col gap-4">
      <ItemDetailContent
        key={itemId}
        itemId={itemId}
        onBack={goBack}
        onPlayMovie={startMovie}
        onPlayEpisode={startEpisode}
        onToggleWatched={toggleWatched}
      />
    </div>
  );
}
