/**
 * Shared card/detail action handlers for the watchlist views
 * (LEGACY_PARITY_PLAN). One implementation of the legacy data-act behaviours:
 * download (request media), Play in RKM / Episodes (navigate to the item's
 * page — the routed player owns playback), external watch links, library-item
 * navigation + watched toggles, and the manual recommendation refresh.
 */
import { useNavigate } from "react-router-dom";
import type { MediaItem, WatchlistEntry } from "../../lib/api/client";
import { ApiError } from "../../lib/api/client";
import { useMutateItemState } from "../library/api";
import { useRequestMedia, useRunAddWatchlist } from "./api";
import { mediaIdOf } from "./lib";
import { toast } from "./toast";

export function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
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
  const download = (entry: WatchlistEntry) => {
    requestMedia.mutate(mediaIdOf(entry), {
      onSuccess: (r) => {
        if (r.ok) toast("Download started", entry.title);
        else toast("Download failed", r.message || r.state, "err", 6000);
      },
      onError: (e) => acquisitionToast(e, "Download failed"),
    });
  };

  /** Jellyfin in-app play / Episodes → the title's own routed page. */
  const playInRkm = (entry: WatchlistEntry, itemId: string) => {
    navigate(`/library/item/${encodeURIComponent(itemId)}`);
  };

  /** External watch links (Plex / Emby / Jellyfin web). */
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
