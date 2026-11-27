import type { SensorPoint } from "@/lib/api-types";
import { niceTicks } from "@/pages/project/analyse/charts";

/** "-79.4 °C", "45%", "5% CO2". */
export const showValue = (v: number | null | undefined, symbol: string) =>
  v == null ? "-" : `${Number(v.toFixed(1))}${symbol.startsWith("°") ? ` ${symbol}` : symbol}`;

const HOUR = 3_600_000;

/** Each local midnight inside the window (ms), newest first: the tick for that day sits where it starts. */
export function dayTicks(start: number, end: number): number[] {
  const out: number[] = [];
  for (const d = new Date(end); ; d.setDate(d.getDate() - 1)) {
    d.setHours(0, 0, 0, 0);
    if (d.getTime() <= start) return out;
    out.push(d.getTime());
  }
}

/**
 * Readings over a window ending now, hand-drawn in SVG: the average as a line, the low and high
 * of each step as a faint band, and the limits as dashed lines. A gap in the readings stays a gap.
 * `compact` is the card's sparkline: no axes or labels.
 */
export function SensorChart({
  points,
  low,
  high,
  symbol,
  hours,
  end,
  compact,
}: {
  points: SensorPoint[];
  low?: number | null;
  high?: number | null;
  symbol: string;
  hours: number;
  /** When the window ends: when the readings were fetched (ms). */
  end: number;
  compact?: boolean;
}) {
  const W = compact ? 240 : 640;
  const H = compact ? 56 : 240;
  const M = compact ? { l: 2, r: 2, t: 4, b: 4 } : { l: 52, r: 12, t: 12, b: 28 };
  const start = end - hours * HOUR;
  const step = (hours * HOUR) / (compact ? 72 : 168); // the server's step: 20 minutes, 1 hour
  const vals = points.flatMap((p) => [p.min, p.max]);
  const limits = [low, high].filter((v): v is number => v != null);
  const all = [...vals, ...limits];
  const lo0 = all.length ? Math.min(...all) : 0;
  const hi0 = all.length ? Math.max(...all) : 1;
  const pad = (hi0 - lo0 || 1) * 0.1;
  const [lo, hi] = [lo0 - pad, hi0 + pad];
  const x = (t: string) => M.l + ((Date.parse(t) - start) / (end - start)) * (W - M.l - M.r);
  const y = (v: number) => M.t + ((hi - v) / (hi - lo)) * (H - M.t - M.b);

  // one path per unbroken run of readings
  const runs: SensorPoint[][] = [];
  points.forEach((p, i) => {
    const prev = points[i - 1];
    if (!prev || Date.parse(p.t) - Date.parse(prev.t) > step * 2.5) runs.push([p]);
    else runs[runs.length - 1]!.push(p);
  });
  const line = (run: SensorPoint[]) =>
    run.map((p, i) => `${i ? "L" : "M"}${x(p.t).toFixed(1)} ${y(p.avg).toFixed(1)}`).join("");
  const band = (run: SensorPoint[]) =>
    `${run.map((p, i) => `${i ? "L" : "M"}${x(p.t).toFixed(1)} ${y(p.max).toFixed(1)}`).join("")}` +
    `${[...run]
      .reverse()
      .map((p) => `L${x(p.t).toFixed(1)} ${y(p.min).toFixed(1)}`)
      .join("")}Z`;

  const label = points.length
    ? `Last ${hours === 24 ? "24 hours" : `${hours / 24} days`}: from ${showValue(
        Math.min(...vals),
        symbol,
      )} to ${showValue(Math.max(...vals), symbol)}`
    : "No readings in this time";
  const days = compact ? [] : dayTicks(start, end);

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label={label}
      className={compact ? "viz h-14 w-full" : "viz h-auto w-full"}
      preserveAspectRatio={compact ? "none" : undefined}
      fontFamily="sans-serif"
      fontSize={12}
    >
      <title>{label}</title>
      {!compact &&
        niceTicks(lo, hi, 5).map((t) => (
          <g key={t}>
            <line x1={M.l} x2={W - M.r} y1={y(t)} y2={y(t)} stroke="var(--viz-grid)" />
            <text x={M.l - 6} y={y(t) + 4} textAnchor="end" fill="var(--viz-muted)">
              {showValue(t, symbol)}
            </text>
          </g>
        ))}
      {days.map((t) => {
        const iso = new Date(t).toISOString();
        return (
          <text key={t} x={x(iso)} y={H - 8} textAnchor="middle" fill="var(--viz-muted)">
            {new Date(t).toLocaleDateString(undefined, { weekday: "short" })}
          </text>
        );
      })}
      {limits.map((v) => (
        <line
          key={v}
          x1={M.l}
          x2={W - M.r}
          y1={y(v)}
          y2={y(v)}
          stroke="var(--viz-s2)"
          strokeDasharray="4 4"
          vectorEffect="non-scaling-stroke"
        />
      ))}
      {runs.map((run) => (
        <g key={run[0]!.t}>
          <path d={band(run)} fill="var(--viz-s1)" opacity={0.15} />
          <path
            d={line(run)}
            fill="none"
            stroke="var(--viz-s1)"
            strokeWidth={compact ? 1.5 : 2}
            vectorEffect="non-scaling-stroke"
          />
          {run.length === 1 && (
            <circle cx={x(run[0]!.t)} cy={y(run[0]!.avg)} r={2.5} fill="var(--viz-s1)" />
          )}
        </g>
      ))}
    </svg>
  );
}
