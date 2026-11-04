import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Handover } from "@/lib/api-types";

/** Each visit generates (and audits) a fresh report, so it is never cached or refetched on focus. */
export function useHandover(path: string) {
  return useQuery({
    queryKey: ["handover", path],
    queryFn: () => api<Handover>(path),
    gcTime: 0,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });
}
