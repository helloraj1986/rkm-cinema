/**
 * The profile in effect, as the SERVER describes it (ADMIN_CREDENTIALS_PLAN Phase 3 follow-up).
 *
 * The nav needs one fact the session object does not carry: whether the profile in effect is an
 * administrator. It comes from the same `["auth","profiles"]` payload the picker and the My-password
 * screen already read, so the answer is shared rather than fetched again, and it is the server's
 * answer — never a guess made from a name.
 */
import { useQuery } from "@tanstack/react-query";

import { api, type ProfileUserShape } from "../../lib/api/client";

export function useCurrentProfile(): ProfileUserShape | undefined {
  const { data } = useQuery({
    queryKey: ["auth", "profiles"],
    queryFn: () => api.profiles(),
    staleTime: 30_000,
  });
  return data?.current;
}
