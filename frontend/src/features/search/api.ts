/**
 * TanStack Query hook for the global search (GLOBAL_SEARCH_PLAN Phase 3;
 * cancellation + perceived speed are SEARCH_IMPROVEMENT_PLAN Phase 4).
 *
 * ⚠ ONE hook for both surfaces — the desktop palette (`GlobalSearch.tsx`) and the
 * phone's screen (`layouts/mobile/SearchScreen.tsx`). Cancellation policy is part
 * of the search's behaviour, so it lives here rather than in either screen; a
 * second copy is how the two would end up hammering the server differently.
 *
 * Debounce stays in the SURFACES (they own the field), but it is the same shared
 * `SEARCH_DEBOUNCE_MS`.
 */
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { api } from "../../lib/api/client";

export function useGlobalSearch(q: string) {
  const queryClient = useQueryClient();
  const previous = useRef<string | null>(null);

  useEffect(() => {
    const superseded = previous.current;
    previous.current = q;
    // ⚠ React Query does NOT cancel a query just because its key changed: the old
    // fetch runs to completion. On a slow link that request is still in flight when
    // the next three keystrokes have already been asked, so each one pays for a
    // TMDB round-trip nobody will read. Cancelling aborts it through the signal the
    // queryFn was handed, so nothing is left running.
    if (superseded && superseded !== q) {
      void queryClient.cancelQueries({ queryKey: ["search", "global", superseded] });
    }
  }, [q, queryClient]);

  return useQuery({
    queryKey: ["search", "global", q],
    queryFn: ({ signal }) => api.searchGlobal(q, signal),
    enabled: q.trim().length > 0,
    staleTime: 15_000,
    // ⚠ `keepPreviousData` is the perceived-speed win the plan asks for: while the
    // new query is in flight the previous rows stay on screen instead of the list
    // collapsing to a skeleton and back on every keystroke. The rows are keyed and
    // the highlight spans travel with them, so what is shown is never a mix.
    placeholderData: keepPreviousData,
  });
}
