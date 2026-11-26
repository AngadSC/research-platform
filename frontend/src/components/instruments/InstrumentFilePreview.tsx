import { useId, useState } from "react";
import { summaryToCsv } from "./summaryToCsv";
import type { InstrumentPlate, InstrumentSummary, InstrumentTable, InstrumentTrace } from "./types";

/** Numbers to at most six significant digits; text and blanks as they are. */
function show(v: string | number | null | undefined): string {
  if (v === null || v === undefined) return "";
  if (typeof v === "number") return String(Number(v.toPrecision(6)));
  return v;
}

function when(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function Heading({ children }: { children: React.ReactNode }) {
  return <h3 className="mb-2 text-sm font-medium">{children}</h3>;
}

function Fields({ summary }: { summary: InstrumentSummary }) {
  const fields = [...(summary.fields ?? [])];
  const has = (label: string) => fields.some((f) => f.label.toLowerCase() === label.toLowerCase());
  if (summary.measured_at && !has("Measured")) {
    fields.unshift({ label: "Measured", value: when(summary.measured_at) });
  }
  if (summary.instrument_serial && !has("Serial number")) {
    fields.push({ label: "Serial number", value: summary.instrument_serial });
  }
  if (fields.length === 0) return null;
  return (
    <dl className="grid grid-cols-[max-content_1fr] gap-x-6 gap-y-1 text-sm">
      {fields.map((f) => (
        <div key={f.label} className="contents">
          <dt className="text-muted-foreground">{f.label}</dt>
          <dd className="min-w-0 break-words">{f.value}</dd>
        </div>
      ))}
    </dl>
  );
}

/** Heat colour from the app's own teal; capped so dark text stays readable in both themes. */
const heat = (t: number) =>
  `color-mix(in srgb, var(--primary) ${Math.round(t * 45)}%, var(--background))`;

function PlateGrid({ plate }: { plate: InstrumentPlate }) {
  const values = Object.values(plate.wells).filter((v): v is number => typeof v === "number");
  const lo = values.length ? Math.min(...values) : 0;
  const hi = values.length ? Math.max(...values) : 0;
  const unit = plate.unit ? ` ${plate.unit}` : "";
  const letter = (r: number) =>
    r < 26 ? String.fromCharCode(65 + r) : "A" + String.fromCharCode(65 + r - 26);
  const small = plate.cols > 12;
  return (
    <div>
      <div className="max-h-[28rem] overflow-auto rounded-md border">
        <table
          className={`border-collapse text-center tabular-nums ${small ? "text-[10px]" : "text-xs"}`}
          aria-label={`${plate.name}, ${plate.rows} rows by ${plate.cols} columns`}
        >
          <thead>
            <tr>
              <td className="sticky left-0 top-0 z-20 bg-muted/50" />
              {Array.from({ length: plate.cols }, (_, c) => (
                <th
                  key={c}
                  scope="col"
                  className="sticky top-0 z-10 bg-muted/50 px-1 py-1 font-medium text-muted-foreground"
                >
                  {c + 1}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: plate.rows }, (_, r) => (
              <tr key={r}>
                <th
                  scope="row"
                  className="sticky left-0 z-10 bg-muted/50 px-2 font-medium text-muted-foreground"
                >
                  {letter(r)}
                </th>
                {Array.from({ length: plate.cols }, (_, c) => {
                  const well = `${letter(r)}${c + 1}`;
                  const v = plate.wells[well];
                  const has = typeof v === "number";
                  return (
                    <td
                      key={c}
                      title={has ? `${well}: ${show(v)}${unit}` : `${well}: no reading`}
                      className={`border border-background px-1.5 py-1.5 ${small ? "min-w-9" : "min-w-12"}`}
                      style={{
                        background: has ? heat(hi > lo ? (v - lo) / (hi - lo) : 0) : undefined,
                      }}
                    >
                      {has ? show(v) : <span aria-label="no reading">–</span>}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span>
          {values.length} of {plate.rows * plate.cols} wells read
          {values.length ? `. Lowest ${show(lo)}${unit}, highest ${show(hi)}${unit}.` : "."}
        </span>
        <span aria-hidden className="inline-flex items-center gap-1">
          low
          <span
            className="h-2 w-16 rounded-sm border"
            style={{ background: `linear-gradient(to right, ${heat(0)}, ${heat(1)})` }}
          />
          high
        </span>
      </p>
    </div>
  );
}

function Plates({ plates }: { plates: InstrumentPlate[] }) {
  const [index, setIndex] = useState(0);
  const id = useId();
  const plate = plates[Math.min(index, plates.length - 1)] ?? plates[0];
  if (!plate) return null;
  return (
    <section>
      <div className="mb-2 flex flex-wrap items-center gap-3">
        <Heading>{plates.length > 1 ? "Plate readings" : plate.name}</Heading>
        {plates.length > 1 && (
          <>
            <label htmlFor={id} className="sr-only">
              Choose a plate reading
            </label>
            <select
              id={id}
              value={index}
              onChange={(e) => setIndex(Number(e.target.value))}
              className="mb-2 h-8 rounded-md border bg-background px-2 text-sm"
            >
              {plates.map((p, i) => (
                <option key={i} value={i}>
                  {p.name}
                </option>
              ))}
            </select>
          </>
        )}
      </div>
      <PlateGrid plate={plate} />
    </section>
  );
}

function DataTable({ table }: { table: InstrumentTable }) {
  return (
    <section>
      <Heading>{table.name}</Heading>
      <div className="max-h-96 overflow-auto rounded-md border">
        <table className="w-full border-collapse text-sm" aria-label={table.name}>
          <thead>
            <tr>
              {table.columns.map((c, i) => (
                <th
                  key={i}
                  scope="col"
                  className="sticky top-0 z-10 whitespace-nowrap border-b bg-muted px-3 py-2 text-left text-xs font-medium text-muted-foreground"
                >
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((row, r) => (
              <tr key={r} className="border-b last:border-0 hover:bg-muted/50">
                {table.columns.map((_, c) => (
                  <td
                    key={c}
                    className={`whitespace-nowrap px-3 py-1.5 ${typeof row[c] === "number" ? "text-right tabular-nums" : ""}`}
                  >
                    {show(row[c])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        {table.truncated
          ? `Showing the first ${table.rows.length} rows. The file has more rows than this preview shows.`
          : `${table.rows.length} ${table.rows.length === 1 ? "row" : "rows"}.`}
      </p>
    </section>
  );
}

const W = 640;
const H = 220;
const PAD = { l: 52, r: 12, t: 10, b: 36 };
const BASE_COLOURS: Record<string, string> = {
  A: "#2e7d32",
  C: "#1565c0",
  G: "#6b6b6b",
  T: "#c62828",
};

/** A "nice" tick step for a range, about n ticks. */
function ticks(lo: number, hi: number, n = 5): number[] {
  if (!(hi > lo)) return [lo];
  const raw = (hi - lo) / n;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw;
  const out: number[] = [];
  for (let t = Math.ceil(lo / step) * step; t <= hi + step * 1e-9; t += step)
    out.push(Number(t.toPrecision(10)));
  return out;
}

function TraceChart({ traces, title }: { traces: InstrumentTrace[]; title: string }) {
  const xs = traces.flatMap((t) => t.x);
  const ys = traces.flatMap((t) => t.y);
  if (xs.length === 0) return null;
  const x0 = Math.min(...xs);
  const x1 = Math.max(...xs);
  let y0 = Math.min(...ys);
  let y1 = Math.max(...ys);
  if (y0 > 0 && y0 < (y1 - y0) * 0.5) y0 = 0; // keep the baseline when the trace starts near zero
  if (y1 === y0) y1 = y0 + 1;
  const px = (x: number) => PAD.l + ((x - x0) / (x1 === x0 ? 1 : x1 - x0)) * (W - PAD.l - PAD.r);
  const py = (y: number) => H - PAD.b - ((y - y0) / (y1 - y0)) * (H - PAD.t - PAD.b);
  const first = traces[0];
  if (!first) return null;
  const overlay = traces.length > 1;
  return (
    <figure>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full max-w-3xl rounded-md border bg-background"
        role="img"
        aria-label={`${title}. ${first.x_label ?? "x"} from ${show(x0)} to ${show(x1)}; ${first.y_label ?? "signal"} from ${show(Math.min(...ys))} to ${show(Math.max(...ys))}.`}
      >
        {ticks(y0, y1).map((t) => (
          <g key={`y${t}`}>
            <line
              x1={PAD.l}
              x2={W - PAD.r}
              y1={py(t)}
              y2={py(t)}
              stroke="currentColor"
              opacity="0.12"
            />
            <text
              x={PAD.l - 6}
              y={py(t) + 3}
              textAnchor="end"
              fontSize="10"
              fill="currentColor"
              opacity="0.75"
            >
              {show(t)}
            </text>
          </g>
        ))}
        {ticks(x0, x1).map((t) => (
          <text
            key={`x${t}`}
            x={px(t)}
            y={H - PAD.b + 14}
            textAnchor="middle"
            fontSize="10"
            fill="currentColor"
            opacity="0.75"
          >
            {show(t)}
          </text>
        ))}
        <line
          x1={PAD.l}
          x2={W - PAD.r}
          y1={H - PAD.b}
          y2={H - PAD.b}
          stroke="currentColor"
          opacity="0.4"
        />
        <text
          x={(PAD.l + W - PAD.r) / 2}
          y={H - 4}
          textAnchor="middle"
          fontSize="11"
          fill="currentColor"
        >
          {first.x_label ?? ""}
        </text>
        <text
          transform={`translate(11 ${(PAD.t + H - PAD.b) / 2}) rotate(-90)`}
          textAnchor="middle"
          fontSize="11"
          fill="currentColor"
        >
          {first.y_label ?? ""}
        </text>
        {traces.map((t, i) => (
          <polyline
            key={i}
            fill="none"
            strokeWidth="1.3"
            strokeLinejoin="round"
            stroke={overlay ? (BASE_COLOURS[t.name] ?? "var(--primary)") : "var(--primary)"}
            points={t.x
              .map((x, j) => `${px(x).toFixed(1)},${py(t.y[j] ?? 0).toFixed(1)}`)
              .join(" ")}
          />
        ))}
      </svg>
      {overlay && (
        <figcaption className="mt-1 flex flex-wrap gap-x-4 text-xs text-muted-foreground">
          {traces.map((t, i) => (
            <span key={i} className="inline-flex items-center gap-1">
              <span
                aria-hidden
                className="inline-block h-0.5 w-4"
                style={{ background: BASE_COLOURS[t.name] ?? "var(--primary)" }}
              />
              {t.name}
            </span>
          ))}
        </figcaption>
      )}
    </figure>
  );
}

function Traces({ traces, together }: { traces: InstrumentTrace[]; together: boolean }) {
  if (together) {
    return (
      <section>
        <Heading>Signal</Heading>
        <TraceChart traces={traces} title="Signal of each channel" />
      </section>
    );
  }
  return (
    <section className="space-y-4">
      {traces.map((t, i) => (
        <div key={i}>
          <Heading>{t.name}</Heading>
          <TraceChart traces={[t]} title={t.name} />
        </div>
      ))}
    </section>
  );
}

export function InstrumentFilePreview({
  summary,
  onUseCsv,
  csvButtonLabel = "Use in statistics",
}: {
  summary: InstrumentSummary;
  /** When given, a button hands the first table or plate to the caller as CSV text. */
  onUseCsv?: (csv: string) => void;
  csvButtonLabel?: string;
}) {
  if (summary.status === "failed") {
    return (
      <div role="alert" className="rounded-md border border-danger/40 bg-danger/10 p-4 text-sm">
        <p className="font-medium">We couldn't read this file.</p>
        <p className="mt-1">{summary.error || "It may be damaged or in a format we don't know."}</p>
        <p className="mt-1 text-muted-foreground">The file is still saved. You can download it.</p>
      </div>
    );
  }
  if (summary.status === "unsupported") {
    return (
      <div role="status" className="rounded-md border bg-muted/40 p-4 text-sm">
        <p className="font-medium">No preview for this kind of file yet.</p>
        <p className="mt-1 text-muted-foreground">
          {summary.error || "The file is still saved. You can download it."}
        </p>
      </div>
    );
  }
  const csv = onUseCsv ? summaryToCsv(summary) : null;
  const image = summary.image;
  return (
    <div className="space-y-5">
      {(summary.title || csv) && (
        <div className="flex flex-wrap items-center justify-between gap-2">
          {summary.title && <h2 className="text-base font-semibold">{summary.title}</h2>}
          {csv && onUseCsv && (
            <button
              type="button"
              onClick={() => onUseCsv(csv)}
              className="inline-flex h-8 items-center rounded-md border px-3 text-sm font-medium hover:bg-muted"
            >
              {csvButtonLabel}
            </button>
          )}
        </div>
      )}
      {summary.warnings && summary.warnings.length > 0 && (
        <ul
          className="space-y-1 rounded-md border border-warning/50 bg-warning/15 p-3 text-sm"
          aria-label="Notes about this file"
        >
          {summary.warnings.map((w, i) => (
            <li key={i}>{w}</li>
          ))}
        </ul>
      )}
      <Fields summary={summary} />
      {image && (
        <figure>
          <img
            src={`data:image/png;base64,${image.png_base64}`}
            alt={`Preview of ${summary.title ?? "the image"}`}
            width={image.width}
            height={image.height}
            className="h-auto max-h-[32rem] max-w-full rounded-md border bg-black object-contain"
          />
          <figcaption className="mt-1 text-xs text-muted-foreground">
            {image.width} × {image.height} pixels
            {image.bit_depth ? `, ${image.bit_depth}-bit original` : ""}
          </figcaption>
        </figure>
      )}
      {summary.plates && summary.plates.length > 0 && <Plates plates={summary.plates} />}
      {summary.traces && summary.traces.length > 0 && (
        <Traces traces={summary.traces} together={summary.kind === "sequence_trace"} />
      )}
      {summary.tables?.map((t, i) => (
        <DataTable key={i} table={t} />
      ))}
    </div>
  );
}
