import type { StatsResult } from "@/lib/stats/contract";

const size = (v: number, [s, m, l]: number[]) =>
  v >= l! ? "large" : v >= m! ? "medium" : v >= s! ? "small" : "very small";

/** A plain size label for the d or r in a summary, by the usual cut-offs (d .2/.5/.8, r .1/.3/.5). */
export function effectLabel(result: Pick<StatsResult, "summary" | "test">): string | null {
  const hit = /(?:^|[\s,(])(d|r)(?:\(\d+\))? = (-?\d*\.?\d+)/.exec(result.summary);
  if (!hit) return null;
  const v = Math.abs(Number(hit[2]));
  if (!Number.isFinite(v)) return null;
  const [sym, text] = [hit[1], hit[2]];
  const label = size(v, sym === "d" ? [0.2, 0.5, 0.8] : [0.1, 0.3, 0.5]);
  const noun =
    sym === "d" ? "difference" : /correlation/.test(result.test) ? "relationship" : "effect";
  return `${sym} = ${text}: a ${label} ${noun}`;
}
