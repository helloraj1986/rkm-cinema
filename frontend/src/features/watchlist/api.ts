/**
 * TanStack Query hooks for the watchlist feature slice (LEGACY_PARITY_PLAN).
 * Entries (rich, /watchlist/entries) + resources (thin §18, /watchlist) are the
 * legacy DATA + RES split; mutations invalidate both so state moves everywhere.
 */
import { useCallback, useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type SuggestFilters, type WatchlistEntry } from "../../lib/api/client";
import {
  mediaIdOf,
  persistedToEntry,
  resourceMap,
  resolveState,
  suggestItemToEntry,
  upsertWatchlistEntries,
  type ResolvedState,
} from "./lib";

/** Rich watchlist entries (live dashboard-mapper source). */
export function useWatchlistEntries() {
  return useQuery({
    queryKey: ["watchlist", "entries"],
    queryFn: api.getWatchlistEntries,
    staleTime: 30_000,
  });
}

/** Thin §18 resources — per-title status/capabilities/watch links. The legacy
 *  app polled every 60s; TanStack refetches on window focus + after mutations,
 *  so a 60s staleTime keeps this calm while staying fresh in practice. */
export function useWatchlistResources() {
  return useQuery({
    queryKey: ["watchlist", "resources"],
    queryFn: api.getWatchlistResources,
    staleTime: 60_000,
  });
}

/** Search (watchlist + TMDB live). Enabled only when q is non-empty. */
export function useSearch(q: string) {
  return useQuery({
    queryKey: ["search", q],
    queryFn: () => api.search(q),
    enabled: q.trim().length > 0,
    staleTime: 15_000,
  });
}

/** POST /api/suggest — TMDB discover by taste filters. */
export function useSuggestRun() {
  return useMutation({ mutationFn: (filters: SuggestFilters) => api.suggest(filters) });
}

/** GET /api/suggest/detail/{id} — full TMDB + IMDb detail for the modal. */
export function useSuggestDetail(tmdbId: number | null, mediaType: string | null) {
  return useQuery({
    queryKey: ["suggest", "detail", tmdbId],
    queryFn: () => api.suggestDetail(tmdbId as number, mediaType as string),
    enabled: Boolean(tmdbId && mediaType),
    staleTime: 5 * 60_000,
  });
}

/** POST /api/suggest/add/{id} — add a title to the watchlist. On success the
 *  returned persisted entry is upserted into the rich-entries cache (full
 *  card immediately) and the resources cache is invalidated (state re-reads). */
export function useAddToWatchlist() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ tmdbId, mediaType }: { tmdbId: number; mediaType: string }) =>
      api.suggestAdd(tmdbId, mediaType),
    onSuccess: (resp, vars) => {
      if (!resp.ok) return;
      const q = qc.getQueryData<{ entries: WatchlistEntry[] }>(["watchlist", "entries"]);
      const existing = q?.entries ?? [];
      const entry =
        persistedToEntry((resp.entry ?? {}) as Record<string, unknown>) ??
        suggestItemToEntry({
          tmdb_id: vars.tmdbId,
          media_type: vars.mediaType === "tv" ? "tv" : "movie",
          title: resp.title || "",
          year: null,
          tmdb_score: 0,
          vote_count: 0,
          genres: [],
          overview: "",
          poster: "",
          backdrop: "",
          in_watchlist: true,
          in_library: false,
        });
      // Upsert by REAL ids only (legacy pushSuggestEntryToApp) — entries with
      // an empty imdbId must never dedupe against each other, or every add
      // would wipe previously-added TMDB-only titles from the local cache.
      // The optimistic list is then reconciled against the server in the
      // background so a cold cache can't show a partial watchlist.
      const next = upsertWatchlistEntries(existing, entry);
      qc.setQueryData(["watchlist", "entries"], { updated: "", entries: next });
      void qc.invalidateQueries({ queryKey: ["watchlist", "entries"] });
      void qc.invalidateQueries({ queryKey: ["watchlist", "resources"] });
    },
  });
}

/** POST /api/media/{id}/request — request the download from the *arr backend. */
export function useRequestMedia() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (mediaId: string) => api.requestMedia(mediaId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["watchlist", "resources"] });
    },
  });
}

/** POST /api/jobs/add_watchlist/run — manual recommendation refresh. */
export function useRunAddWatchlist() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (count: number) => api.runAddWatchlistJob(count),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["watchlist", "entries"] });
      void qc.invalidateQueries({ queryKey: ["watchlist", "resources"] });
    },
  });
}

/**
 * Combined watchlist view model: rich entries + thin resources resolved to a
 * per-entry `ResolvedState` (legacy DATA + RES + st()). Views consume this so
 * card actions/markers are always truthful and never reconstructed twice.
 */
export function useWatchlist() {
  const entriesQ = useWatchlistEntries();
  const resourcesQ = useWatchlistResources();
  const entries = entriesQ.data?.entries ?? [];
  const resources = useMemo(() => resourceMap(resourcesQ.data?.entries), [resourcesQ.data]);
  const stateFor = useCallback(
    (e: WatchlistEntry): ResolvedState => resolveState(e, resources[mediaIdOf(e)], true),
    [resources],
  );
  return {
    entries,
    updated: entriesQ.data?.updated ?? "",
    stateFor,
    isLoading: entriesQ.isLoading || resourcesQ.isLoading,
    isError: entriesQ.isError || resourcesQ.isError,
    indexerIssue: resourcesQ.data?.indexerIssue ?? null,
  };
}
