/**
 * Shared card/detail action handlers for the watchlist views
 * (LEGACY_PARITY_PLAN). One implementation of the legacy data-act behaviours:
 * download (request media), Play in RKM / Episodes (navigate to the item's
 * page — the routed player owns playback), external watch links, library-item
 * navigation + watched toggles, and the manual recommendation refresh.
 */
import { useNavigate } from "react-router-dom";
import type { AmbiguousCandidate, MediaItem, WatchlistEntry } from "../../lib/api/client";
import { ApiError, ambiguousCandidates } from "../../lib/api/client";
import { useMutateItemState } from "../library/api";
import { useRequestMedia, useRunAddWatchlist } from "./api";
import { mediaIdOf } from "./lib";
import { toast } from "./toast";

export function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

/**
 * A server "two titles matched, pick one" answer — the ONLY acquisition failure a person can act on.
 *
 * ⚠ A 409 from `POST /api/media/{id}/request` carries `detail: {message, candidates}`. `errorDetail`
 * has always lifted `message` into `ApiError.message`, so a surface could print the SENTENCE — but
 * the candidate LIST was dropped on the floor (nothing read `payload`). `ApiError.payload` and
 * `ambiguousCandidates()` now keep it (2026-09-18); this is the shape a screen renders.
 *
 * ⚠ The candidates carry **no id** — the server flattens the provider's result to title/year
 * (`KNOWN_ISSUES` §7). So the list is READ-ONLY, and it stays read-only until the backend carries an
 * id to re-request with. A control that cannot act is the defect M3-part-4 removed.
 */
export interface AmbiguousMatch {
  /** The server's own sentence; `""` when it sent structure without one. */
  message: string;
  candidates: AmbiguousCandidate[];
}

/**
 * The ambiguous-match payload of a caught error, or `null` when this was any other failure.
 *
 * ⚠ Pure, total and `unknown`-safe on purpose: it is handed whatever a mutation rejected with, and
 * a screen must never have to `try` around it or guess at the shape. A 409 with no candidates (or
 * any other error) returns `null`, which is exactly "show the toast you always showed".
 */
export function ambiguousMatch(e: unknown): AmbiguousMatch | null {
  const candidates = ambiguousCandidates(e);
  if (candidates.length === 0) return null;
  return { message: e instanceof ApiError ? e.detail ?? "" : "", candidates };
}

/** What a surface may do with a download request's outcome. */
export interface DownloadOptions {
  /**
   * Called INSTEAD of the toast when the server answers an ambiguous match.
   *
   * ⚠ "Instead", not "as well": a surface that renders the candidates shows them where the person
   * acted (the sheet), and a toast repeating the same sentence on top of it is noise. A surface
   * that passes nothing keeps today's toast exactly — which is the honest fallback, because
   * `acquisitionToast` prints the server's sentence.
   */
  onAmbiguous?: (match: AmbiguousMatch) => void;
  /** The request is in flight. Surfaces that render the in-flight state pass this. */
  onStart?: () => void;
  /** The request finished, either way. */
  onSettled?: () => void;
}

/** Friendly copy for the two "this stack can't acquire" cases so the user
 *  knows it is environmental (no Radarr/Sonarr), not a broken button. */
export function acquisitionToast(e: unknown, title: string): void {
  if (e instanceof ApiError && e.status === 503) {
    toast(title, `${e.message} — enable Radarr/Sonarr (bundled fullstack profile) or use the prod stack.`, "warn", 7000);
    return;
  }
  if (e instanceof ApiError && e.status === 502) {
    toast(title, `${e.message} — the download service is unreachable.`, "err", 7000);
    return;
  }
  toast(title, errorMessage(e), "err", 6000);
}

export function useCardActions() {
  const navigate = useNavigate();
  const requestMedia = useRequestMedia();
  const runJob = useRunAddWatchlist();
  const mutateItem = useMutateItemState();

  /** Legacy data-act="download" — request the canonical media id. */
  const download = (entry: WatchlistEntry, opts: DownloadOptions = {}) => {
    opts.onStart?.();
    requestMedia.mutate(mediaIdOf(entry), {
      onSuccess: (r) => {
        if (r.ok) toast("Download started", entry.title);
        else toast("Download failed", r.message || r.state, "err", 6000);
      },
      onError: (e) => {
        // ⚠ An ambiguous match is the one failure with STRUCTURE behind it. A surface that can
        // render it takes it (and says nothing else); every other surface — and every other
        // failure — keeps the toast, which already carries the server's own sentence.
        const match = ambiguousMatch(e);
        if (match && opts.onAmbiguous) {
          opts.onAmbiguous(match);
          return;
        }
        acquisitionToast(e, "Download failed");
      },
      onSettled: () => opts.onSettled?.(),
    });
  };

  /** Jellyfin in-app play / Episodes → the title's own routed page. */
  const playInRkm = (entry: WatchlistEntry, itemId: string) => {
    navigate(`/library/item/${encodeURIComponent(itemId)}`);
  };

  /** External watch link (the media server's own web UI). */
  const watchLink = (entry: WatchlistEntry, url: string) => {
    window.open(url, "_blank", "noopener,noreferrer");
  };

  /** Library-item whole-card click (MediaCard surfaces). */
  const openLibraryItem = (item: MediaItem) => {
    navigate(`/library/item/${encodeURIComponent(item.item_id)}`);
  };

  /** Library-item hover play: movies play on their page (Resume aware). */
  const quickPlayLibrary = (item: MediaItem) => openLibraryItem(item);

  /** Library watched toggle (MediaCard hover). */
  const toggleWatched = (item: MediaItem) => {
    mutateItem.mutate({ itemId: item.item_id, watched: !item.played });
  };

  /** Manual "update watchlist" (legacy refresh button's recommendation job). */
  const refreshRecommendations = (count = 20) => {
    runJob.mutate(count, {
      onSuccess: (job) => {
        if (job && job.status === "error") {
          toast("Watchlist update failed", String(job.error || "Could not fetch new recommendations."), "warn", 5000);
        } else {
          toast("Watchlist updated", "New recommendations have been fetched and added.");
        }
      },
      onError: (e) => toast("Watchlist update failed", errorMessage(e), "warn", 5000),
    });
  };

  return { download, playInRkm, watchLink, openLibraryItem, quickPlayLibrary, toggleWatched, refreshRecommendations };
}
