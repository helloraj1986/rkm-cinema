import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../lib/api/client";

export function useLibraryItems() {
  return useQuery({ queryKey: ["library", "items"], queryFn: api.getLibraryItems });
}

export function useContinueWatching() {
  return useQuery({ queryKey: ["library", "continue"], queryFn: api.getContinueWatching });
}

export function useRecentlyWatched() {
  return useQuery({ queryKey: ["library", "recently-watched"], queryFn: api.getRecentlyWatched });
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