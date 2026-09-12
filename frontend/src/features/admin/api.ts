/**
 * Household API hooks (AUTH_MULTIUSER_PLAN Phase 1b).
 *
 * Thin react-query wrappers over the typed client; every mutation refreshes the household so
 * the screen shows what the SERVER now holds rather than what was requested.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../lib/api/client";

const HOUSEHOLD_KEY = ["household"] as const;

export function useHousehold() {
  return useQuery({ queryKey: HOUSEHOLD_KEY, queryFn: () => api.getHousehold() });
}

export function useGrantableLibraries() {
  return useQuery({
    queryKey: ["household", "libraries"] as const,
    queryFn: () => api.getGrantableLibraries(),
  });
}

export function useHouseholdMutations() {
  const queryClient = useQueryClient();
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: HOUSEHOLD_KEY });
  };

  const create = useMutation({ mutationFn: api.createHouseholdUser, onSuccess: refresh });
  const policy = useMutation({
    mutationFn: (vars: { userId: string; library_ids?: string[]; disabled?: boolean }) =>
      api.updateHouseholdPolicy(vars.userId, {
        ...(vars.library_ids !== undefined ? { library_ids: vars.library_ids } : {}),
        ...(vars.disabled !== undefined ? { disabled: vars.disabled } : {}),
      }),
    onSuccess: refresh,
  });
  const rename = useMutation({
    mutationFn: (vars: { userId: string; name: string }) =>
      api.renameHouseholdUser(vars.userId, vars.name),
    onSuccess: refresh,
  });
  const setPassword = useMutation({
    mutationFn: (vars: { userId: string; newPassword: string }) =>
      api.setHouseholdPassword(vars.userId, vars.newPassword),
  });
  const remove = useMutation({
    mutationFn: (vars: { userId: string; confirmName: string }) =>
      api.deleteHouseholdUser(vars.userId, vars.confirmName),
    onSuccess: refresh,
  });

  return { create, policy, rename, setPassword, remove };
}
