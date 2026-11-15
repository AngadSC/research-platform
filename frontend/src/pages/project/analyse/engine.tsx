import { createContext, useContext, type ReactNode } from "react";
import type { StatsEngine } from "@/lib/stats/contract";
import { getStatsEngine } from "@/lib/stats/engine";

/** Tests hand the page a fake engine here; the app uses the real one. */
const Ctx = createContext<(() => StatsEngine) | null>(null);

export function StatsEngineProvider({
  get,
  children,
}: {
  get: () => StatsEngine;
  children: ReactNode;
}) {
  return <Ctx.Provider value={get}>{children}</Ctx.Provider>;
}

export const useGetEngine = () => useContext(Ctx) ?? getStatsEngine;
