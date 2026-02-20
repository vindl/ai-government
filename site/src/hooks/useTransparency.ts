import { useQuery } from "@tanstack/react-query";
import type { TransparencyData } from "@/types";

export function useTransparency() {
  return useQuery<TransparencyData>({
    queryKey: ["transparency"],
    queryFn: async () => {
      const res = await fetch(`${import.meta.env.BASE_URL}data/transparency.json`);
      if (!res.ok) throw new Error("Failed to fetch transparency data");
      return res.json();
    },
  });
}
