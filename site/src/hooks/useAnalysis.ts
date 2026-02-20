import { useQuery } from "@tanstack/react-query";
import type { SessionResult } from "@/types";

export function useAnalysis(id: string | undefined) {
  return useQuery<SessionResult>({
    queryKey: ["analysis", id],
    queryFn: async () => {
      const res = await fetch(`/data/analyses/${id}.json`);
      if (!res.ok) throw new Error(`Failed to fetch analysis ${id}`);
      return res.json();
    },
    enabled: !!id,
  });
}
