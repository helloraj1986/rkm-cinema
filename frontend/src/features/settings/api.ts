import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../lib/api/client";

export function useConfig() {
  return useQuery({
    queryKey: ["config"],
    queryFn: api.getConfig,
    staleTime: 60_000,
  });
}

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: api.getHealth,
    refetchInterval: 30_000,
  });
}

/**
 * How THIS profile wants search ranked (SEARCH_IMPROVEMENT_PLAN Phase 5).
 *
 * ⚠ Its own query key, not folded into `["config"]`: /api/config is public-safe
 * server configuration, this is a per-profile preference, and the two are
 * invalidated by different events. Sharing a key would also have one member's
 * change invalidate another's cached view after a profile switch.
 */
export function useSearchPrefs() {
  return useQuery({
    queryKey: ["search", "prefs"],
    queryFn: api.getSearchPrefs,
    staleTime: 60_000,
  });
}

export function useSetSearchPrefs() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (personalized: boolean) => api.setSearchPrefs(personalized),
    onSuccess: (data) => {
      // ⚠ Write the SERVER's answer into the cache rather than the value we sent:
      // if the two ever disagree, the screen shows what is actually stored.
      queryClient.setQueryData(["search", "prefs"], data);
      // Ranking changes, so a search result already on screen is now stale.
      void queryClient.invalidateQueries({ queryKey: ["search", "global"] });
    },
  });
}
