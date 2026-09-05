import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../lib/api/client";

export function useLibraryItems() {
  return useQuery({ queryKey: ["library", "items"], queryFn: api.getLibraryItems });
}

export function useContinueWatching() {
  return useQuery({ queryKey: ["library", "continue"], queryFn: api.getContinueWatching });
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