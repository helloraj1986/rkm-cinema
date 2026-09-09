import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../lib/api/client";

export function useLibraryItems() {
  return useQuery({ queryKey: ["library", "items"], queryFn: api.getLibraryItems });
}

/** Configured libraries + server folders — sidebar Libraries group. */
export function useLibraryFolders() {
  return useQuery({
    queryKey: ["library", "folders"],
    queryFn: api.getLibraryFolders,
    staleTime: 60_000,
  });
}

/** One library folder's Movie+Series rows (folder-scoped poster wall). */
export function useFolderItems(folderId: string | null) {
  return useQuery({
    queryKey: ["library", "folder-items", folderId],
    queryFn: () => api.getFolderItems(folderId as string),
    enabled: Boolean(folderId),
    staleTime: 30_000,
  });
}

/** Recently-added titles (GET /api/library) — the Home view's added row. */
export function useLibraryRecent() {
  return useQuery({ queryKey: ["library", "recent"], queryFn: api.getLibraryRecent });
}

export function useContinueWatching() {
  return useQuery({ queryKey: ["library", "continue"], queryFn: api.getContinueWatching });
}

export function useRecentlyWatched() {
  return useQuery({ queryKey: ["library", "recently-watched"], queryFn: api.getRecentlyWatched });
}

/**
 * Plex-style preplay metadata for one item. Fetched ONLY on detail open and
 * cached per item (queryKey ["library","detail",id]) so re-opening the same
 * title is instant (PLEX_UI_PLAN.md §2: detail data fetched on demand only).
 */
export function useItemDetail(itemId: string | null) {
  return useQuery({
    queryKey: ["library", "detail", itemId],
    queryFn: () => api.getItemDetail(itemId as string),
    enabled: Boolean(itemId),
    staleTime: 5 * 60_000,
  });
}

/**
 * "Because you watched" — TMDB similar titles for one item (SIMILAR_TITLES_PLAN
 * Phase 2). Rendered only for movie/tv pages; 404s (episode ids / no TMDB id)
 * must not retry — the row just stays hidden.
 */
export function useSimilar(itemId: string | null) {
  return useQuery({
    queryKey: ["library", "similar", itemId],
    queryFn: () => api.getSimilar(itemId as string),
    enabled: Boolean(itemId),
    staleTime: 5 * 60_000,
    retry: false,
  });
}

/** Trigger a backend library scan; invalidates the library queries on success. */
export function useScanLibrary() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.scanLibrary,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["library"] });
    },
  });
}

/** Mark an item watched/unwatched (roadmap item 2). Refreshes library + episodes. */
export function useMutateItemState() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ itemId, watched }: { itemId: string; watched: boolean }) =>
      api.mutateItemState(itemId, watched),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["library"] });
    },
  });
}