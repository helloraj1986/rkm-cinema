import { useQuery } from "@tanstack/react-query";
import { api } from "../../lib/api/client";

export function useEpisodes(seriesId: string | null) {
  return useQuery({
    queryKey: ["library", "episodes", seriesId],
    queryFn: () => api.getEpisodes(seriesId as string),
    enabled: Boolean(seriesId),
  });
}