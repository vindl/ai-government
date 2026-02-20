import { useQuery } from "@tanstack/react-query";
import type { Announcement } from "@/types";

export function useAnnouncements() {
  return useQuery<Announcement[]>({
    queryKey: ["announcements"],
    queryFn: async () => {
      const res = await fetch("/data/announcements.json");
      if (!res.ok) throw new Error("Failed to fetch announcements");
      return res.json();
    },
  });
}
