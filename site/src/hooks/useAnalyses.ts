import { useQuery } from "@tanstack/react-query";
import type { AnalysisSummary } from "@/types";

export function useAnalyses() {
  return useQuery<AnalysisSummary[]>({
    queryKey: ["analyses-index"],
    queryFn: async () => {
      const res = await fetch("/data/analyses-index.json");
      if (!res.ok) throw new Error("Failed to fetch analyses index");
      return res.json();
    },
  });
}
