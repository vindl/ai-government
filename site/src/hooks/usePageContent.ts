import { useQuery } from "@tanstack/react-query";
import type { PageContent } from "@/types";

export function usePageContent(page: "constitution" | "architecture" | "cabinet" | "challenges") {
  return useQuery<PageContent>({
    queryKey: ["page-content", page],
    queryFn: async () => {
      const res = await fetch(`/data/${page}.json`);
      if (!res.ok) throw new Error(`Failed to fetch ${page} content`);
      return res.json();
    },
  });
}
