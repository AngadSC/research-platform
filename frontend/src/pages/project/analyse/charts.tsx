import type { ReactNode } from "react";
import type { StatsChart } from "@/lib/stats/contract";

// Hand-drawn SVG charts. Colours come from the `.viz` variables in index.css (light and dark).
const W = 480;
const H = 300;
const M = { l: 56, r: 16, t: 16, b: 48 };
const GROUP_COLOURS = ["var(--viz-s1)", "var(--viz-s2)", "var(--viz-s3)"];
const MAX_GROUPS = GROUP_COLOURS.length; // more than this would need hues that clash

export const fmt = (n: number) =>
  Math.abs(n) >= 1e6 || (n !== 0 && Math.abs(n) < 0.001)
    ? n.toExponential(1)
    : String(Number(n.toPrecision(4)));

/** About `count` round tick values covering lo..hi. */
export function niceTicks(lo: number, hi: number, count = 5): number[] {
  if (!(hi > lo)) return [lo];
  const raw = (hi - lo) / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = ([1, 2, 5, 10].find((m) => m * mag >= raw) ?? 10) * mag;
  const out: number[] = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step)
    out.push(Number(v.toPrecision(12)));
  return out;
}

const scale = (d0: number, d1: number, r0: number, r1: number) => (v: number) =>
  d1 === d0 ? (r0 + r1) / 2 : r0 + ((v - d0) / (d1 - d0)) * (r1 - r0);

function quantile(sorted: number[], q: number) {
  const i = (sorted.length - 1) * q;
  const lo = Math.floor(i);
  return sorted[lo]! + (sorted[Math.ceil(i)]! - sorted[lo]!) * (i - lo);
}

const range = (vals: number[], pad = 0.05): [number, number] => {
  const lo = Math.min(...vals);
  const hi = Math.max(...vals);
  const p = (hi - lo || Math.abs(hi) || 1) * pad;
  return [lo - p, hi + p];
};

const short = (s: string, n: number) => (s.length > n ? `${s.slice(0, n - 1)}...` : s);

function Frame({
  title,
  desc,
  xLabel,
  yLabel,
  yTicks,
  y,
  children,
  top = M.t,
}: {
  title: string;
  desc: string;
  xLabel?: string;
  yLabel: string;
  yTicks: number[];
  y: (v: number) => number;
  children: ReactNode;
  top?: number;
}) {
  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label={title}
      className="viz h-auto w-full max-w-xl"
      fontFamily="sans-serif"
      fontSize={13}
    >
      <title>{title}</title>
      <desc>{desc}</desc>
      {yTicks.map((t) => (
        <g key={t}>
          <line x1={M.l} x2={W - M.r} y1={y(t)} y2={y(t)} stroke="var(--viz-grid)" />
          <text x={M.l - 6} y={y(t) + 4} textAnchor="end" fill="var(--viz-muted)">
            {fmt(t)}
          </text>
        </g>
      ))}
      <text
        transform={`translate(12 ${(top + H - M.b) / 2}) rotate(-90)`}
        textAnchor="middle"
        fill="var(--viz-text)"
      >
        {short(yLabel, 30)}
      </text>
      {xLabel && (
        <text x={(M.l + W - M.r) / 2} y={H - 6} textAnchor="middle" fill="var(--viz-text)">
          {short(xLabel, 60)}
        </text>
      )}
      {children}
    </svg>
  );
}

function Legend({ names }: { names: string[] }) {
  return (
    <g>
      {names.map((n, i) => (
        <g key={n} transform={`translate(${M.l + i * 120} 12)`}>
          <rect width={10} height={10} rx={2} fill={GROUP_COLOURS[i]} />
          <text x={14} y={9} fill="var(--viz-text)">
            {short(n, 14)}
          </text>
        </g>
      ))}
    </g>
  );
}

function Histogram({ c }: { c: Extract<StatsChart, { kind: "histogram" }> }) {
  const groups = c.groups.filter((g) => g.values.length).slice(0, MAX_GROUPS);
  if (!groups.length) return null;
  const all = groups.flatMap((g) => g.values);
  const lo = Math.min(...all);
  const hi = Math.max(...all);
  const bins = Math.min(30, Math.max(5, Math.ceil(Math.log2(all.length)) + 1));
  const w = (hi - lo || 1) / bins;
  const counts = groups.map((g) => {
    const k = new Array<number>(bins).fill(0);
    for (const v of g.values) k[Math.min(bins - 1, Math.floor((v - lo) / w))]!++;
    return k;
  });
  const multi = groups.length > 1;
  const top = multi ? 34 : M.t;
  const maxC = Math.max(...counts.flat(), 1);
  const y = scale(0, maxC, H - M.b, top);
  const x = scale(lo, lo + w * bins, M.l, W - M.r);
  return (
    <Frame
      title={c.title}
      desc={`Histogram of ${c.xLabel}, ${all.length} values from ${fmt(lo)} to ${fmt(hi)}.`}
      xLabel={c.xLabel}
      yLabel="Count"
      yTicks={niceTicks(0, maxC, 4).filter(Number.isInteger)}
      y={y}
      top={top}
    >
      {multi && <Legend names={groups.map((g) => g.name)} />}
      {counts.map((k, gi) =>
        k.map((n, i) => (
          <rect
            key={`${gi}-${i}`}
            x={x(lo + i * w) + 1}
            y={y(n)}
            width={Math.max(1, x(lo + (i + 1) * w) - x(lo + i * w) - 2)}
            height={H - M.b - y(n)}
            rx={2}
            fill={GROUP_COLOURS[gi]}
            fillOpacity={multi ? 0.55 : 1}
          >
            <title>{`${groups[gi]!.name}: ${n} from ${fmt(lo + i * w)} to ${fmt(lo + (i + 1) * w)}`}</title>
          </rect>
        )),
      )}
      {niceTicks(lo, hi, 5).map((t) => (
        <text key={t} x={x(t)} y={H - M.b + 14} textAnchor="middle" fill="var(--viz-muted)">
          {fmt(t)}
        </text>
      ))}
      <line x1={M.l} x2={W - M.r} y1={H - M.b} y2={H - M.b} stroke="var(--viz-muted)" />
    </Frame>
  );
}

function Box({ c }: { c: Extract<StatsChart, { kind: "box" }> }) {
  const groups = c.groups.filter((g) => g.values.length);
  if (!groups.length) return null;
  const stats = groups.map((g) => {
    const s = [...g.values].sort((a, b) => a - b);
    const q1 = quantile(s, 0.25);
    const q3 = quantile(s, 0.75);
    const fence = 1.5 * (q3 - q1);
    const inside = s.filter((v) => v >= q1 - fence && v <= q3 + fence);
    return {
      name: g.name,
      q1,
      q3,
      med: quantile(s, 0.5),
      lo: inside[0]!,
      hi: inside[inside.length - 1]!,
      out: s.filter((v) => v < q1 - fence || v > q3 + fence),
    };
  });
  const [lo, hi] = range(groups.flatMap((g) => g.values));
  const y = scale(lo, hi, H - M.b, M.t);
  const band = (W - M.l - M.r) / stats.length;
  const bw = Math.min(56, band * 0.6);
  return (
    <Frame
      title={c.title}
      desc={`Box plot of ${c.yLabel} for ${stats.map((s) => `${s.name} (median ${fmt(s.med)})`).join(", ")}.`}
      yLabel={c.yLabel}
      yTicks={niceTicks(lo, hi, 5)}
      y={y}
    >
      {stats.map((s, i) => {
        const cx = M.l + band * (i + 0.5);
        return (
          <g key={s.name}>
            <title>{`${s.name}: median ${fmt(s.med)}, middle half ${fmt(s.q1)} to ${fmt(s.q3)}`}</title>
            {/* whiskers run from the box edges to the ends, never through the box */}
            <line
              x1={cx}
              x2={cx}
              y1={y(s.q3)}
              y2={y(s.hi)}
              stroke="var(--viz-s1)"
              strokeWidth={2}
            />
            <line
              x1={cx}
              x2={cx}
              y1={y(s.q1)}
              y2={y(s.lo)}
              stroke="var(--viz-s1)"
              strokeWidth={2}
            />
            <rect
              x={cx - bw / 2}
              y={y(s.q3)}
              width={bw}
              height={Math.max(1, y(s.q1) - y(s.q3))}
              rx={4}
              fill="var(--viz-s1)"
              fillOpacity={0.35}
              stroke="var(--viz-s1)"
              strokeWidth={2}
            />
            <line
              x1={cx - bw / 2}
              x2={cx + bw / 2}
              y1={y(s.med)}
              y2={y(s.med)}
              stroke="var(--viz-text)"
              strokeWidth={2}
            />
            {s.out.map((v, k) => (
              <circle
                key={k}
                cx={cx}
                cy={y(v)}
                r={3}
                fill="none"
                stroke="var(--viz-s1)"
                strokeWidth={1.5}
              />
            ))}
            <text x={cx} y={H - M.b + 16} textAnchor="middle" fill="var(--viz-muted)">
              {short(s.name, Math.max(4, Math.min(30, Math.floor(band / 8))))}
            </text>
          </g>
        );
      })}
      <line x1={M.l} x2={W - M.r} y1={H - M.b} y2={H - M.b} stroke="var(--viz-muted)" />
    </Frame>
  );
}

function Scatter({ c }: { c: Extract<StatsChart, { kind: "scatter" }> }) {
  if (!c.points.length) return null;
  const [xl, xh] = range(c.points.map((p) => p[0]));
  const [yl, yh] = range(c.points.map((p) => p[1]));
  const x = scale(xl, xh, M.l, W - M.r);
  const y = scale(yl, yh, H - M.b, M.t);
  const line = c.line;
  return (
    <Frame
      title={c.title}
      desc={`Scatter plot of ${c.yLabel} against ${c.xLabel}, ${c.points.length} points${line ? ", with a fitted line" : ""}.`}
      xLabel={c.xLabel}
      yLabel={c.yLabel}
      yTicks={niceTicks(yl, yh, 5)}
      y={y}
    >
      {niceTicks(xl, xh, 5).map((t) => (
        <text key={t} x={x(t)} y={H - M.b + 14} textAnchor="middle" fill="var(--viz-muted)">
          {fmt(t)}
        </text>
      ))}
      <line x1={M.l} x2={W - M.r} y1={H - M.b} y2={H - M.b} stroke="var(--viz-muted)" />
      {c.points.map(([px, py], i) => (
        <circle key={i} cx={x(px)} cy={y(py)} r={3.5} fill="var(--viz-s1)" fillOpacity={0.6} />
      ))}
      {line && (
        <line
          x1={x(xl)}
          x2={x(xh)}
          y1={y(line.intercept + line.slope * xl)}
          y2={y(line.intercept + line.slope * xh)}
          stroke="var(--viz-s2)"
          strokeWidth={2}
        />
      )}
    </Frame>
  );
}

function Bar({ c }: { c: Extract<StatsChart, { kind: "bar" }> }) {
  if (!c.bars.length) return null;
  const vals = c.bars.flatMap((b) => [b.value, b.low ?? b.value, b.high ?? b.value, 0]);
  const lo = Math.min(...vals);
  const hi = Math.max(...vals) * 1.05 || 1;
  const y = scale(lo, hi, H - M.b, M.t);
  const band = (W - M.l - M.r) / c.bars.length;
  const bw = Math.min(64, band * 0.6);
  return (
    <Frame
      title={c.title}
      desc={`Bar chart of ${c.yLabel}: ${c.bars.map((b) => `${b.name} ${fmt(b.value)}`).join(", ")}.`}
      yLabel={c.yLabel}
      yTicks={niceTicks(lo, hi, 5)}
      y={y}
    >
      {c.bars.map((b, i) => {
        const cx = M.l + band * (i + 0.5);
        const hasCi = b.low !== undefined && b.high !== undefined;
        return (
          <g key={b.name}>
            <title>
              {`${b.name}: ${fmt(b.value)}${hasCi ? ` (${fmt(b.low!)} to ${fmt(b.high!)})` : ""}`}
            </title>
            <rect
              x={cx - bw / 2}
              y={Math.min(y(b.value), y(0))}
              width={bw}
              height={Math.max(1, Math.abs(y(b.value) - y(0)))}
              rx={4}
              fill="var(--viz-s1)"
            />
            {hasCi && (
              <g stroke="var(--viz-text)" strokeWidth={1.5}>
                <line x1={cx} x2={cx} y1={y(b.low!)} y2={y(b.high!)} />
                <line x1={cx - 5} x2={cx + 5} y1={y(b.low!)} y2={y(b.low!)} />
                <line x1={cx - 5} x2={cx + 5} y1={y(b.high!)} y2={y(b.high!)} />
              </g>
            )}
            <text x={cx} y={H - M.b + 16} textAnchor="middle" fill="var(--viz-muted)">
              {short(b.name, Math.max(4, Math.min(30, Math.floor(band / 8))))}
            </text>
          </g>
        );
      })}
      <line x1={M.l} x2={W - M.r} y1={y(0)} y2={y(0)} stroke="var(--viz-muted)" />
    </Frame>
  );
}

export function Chart({ chart }: { chart: StatsChart }) {
  switch (chart.kind) {
    case "histogram":
      return <Histogram c={chart} />;
    case "box":
      return <Box c={chart} />;
    case "scatter":
      return <Scatter c={chart} />;
    case "bar":
      return <Bar c={chart} />;
  }
}
