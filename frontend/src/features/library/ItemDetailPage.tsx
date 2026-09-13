import { useCallback, useEffect } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { ItemDetailModal } from "./ItemDetailModal";
import { LibraryHomeView } from "./LibraryHomeView";

/**
 * `/library/item/:itemId` — the item's detail as a MODAL over the library (his Bug 5, 2026-09-13).
 *
 * The URL is still the source of truth: every in-app entry point (search results, poster cards, the
 * hero's Details) navigates here, a deep link works on a cold load, Back and refresh behave, and
 * closing the panel walks history back to where he came from. What changed is PRESENTATION — this
 * route used to render a full page whose content block read as an un-scrimmed panel occupying the
 * right ~67% of a wide screen. It now renders the app's `Dialog` (see `ItemDetailModal`).
 *
 * ⚠ The library view he came from is not re-rendered underneath: the router replaced it with this
 * route, and this route has no memory of the caller (the callers navigate by URL, deliberately — no
 * overlay state anywhere). Home stands in as the dimmed, INERT backdrop, which is the view a search
 * or a card click is almost always made from. It is marked `pointer-events-none` as well as
 * `aria-hidden`, so "the page behind looks fully interactive" cannot happen again even if the scrim's
 * geometry ever changed.
 */
export function ItemDetailPage() {
  const { itemId = "" } = useParams();
  const navigate = useNavigate();
  const location = useLocation();

  /** Close → the page he came from; a cold deep link has no in-app history to unwind. */
  const goBack = useCallback(() => {
    if (location.key !== "default") {
      navigate(-1);
    } else {
      navigate("/library/home", { replace: true });
    }
  }, [location.key, navigate]);

  // A new title (or a refresh of a deep link) starts at the top — the panel scrolls itself.
  useEffect(() => {
    window.scrollTo({ top: 0 });
  }, [itemId]);

  return (
    <>
      {/* aria-hidden + pointer-events-none (React 18's typings predate the `inert` attribute). */}
      <div aria-hidden="true" className="pointer-events-none select-none">
        <LibraryHomeView />
      </div>
      <ItemDetailModal itemId={itemId} onClose={goBack} />
    </>
  );
}
