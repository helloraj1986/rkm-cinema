/**
 * TanStack Query hook for the global search (GLOBAL_SEARCH_PLAN Phase 3).
 * Debounce lives in the overlay; this only fires for non-empty queries.
 */
import { useQuery } from "@tanstack/react-query";
import { api } from "../../lib/api/client";

export function useGlobalSearch(q: string) {
  return useQuery({
    queryKey: ["search", "global", q],
    queryFn: () => api.searchGlobal(q),
    enabled: q.trim().length > 0,
    staleTime: 15_000,
  });
}
