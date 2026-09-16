import { useQuery } from "@tanstack/react-query";

import { api } from "../../lib/api/client";

/**
 * What a download would cost — `GET /api/offline/bundle/{item_id}` (§4.6: *"a Download button with
 * the ready size and the rendition it will fetch"*).
 *
 * ⚠ Asked BEFORE the button that commits to it, and that is the point. The alternative is a download
 * that starts and only then reports the real size — which is how a feature teaches someone to
 * distrust its numbers.
 *
 * ⚠ `retry: false`: a 404 is an ORDINARY answer (the server has no record of that title), and
 * retrying it four times would make a normal answer look like a network fault.
 */
export function useOfflineBundle(itemId: string, enabled: boolean) {
  return useQuery({
    queryKey: ["offline", "bundle", itemId],
    queryFn: () => api.offlineBundle(itemId),
    enabled: enabled && Boolean(itemId),
    retry: false,
    staleTime: 60_000,
  });
}
