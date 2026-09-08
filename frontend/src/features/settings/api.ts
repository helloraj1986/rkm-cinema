import { useQuery } from "@tanstack/react-query";
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