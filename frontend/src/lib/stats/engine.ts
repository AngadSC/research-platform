import type { StatsEngine } from "@/lib/stats/contract";

/** The one statistics engine for the page (a web worker running Pyodide). Placeholder until the
 * engine lands; the screens only ever call this. */
export function getStatsEngine(): StatsEngine {
  throw new Error("The statistics engine is not built yet.");
}
