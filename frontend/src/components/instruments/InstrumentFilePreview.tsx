/**
 * STUB until wl-parsers merges (.night/WETLAB.md): same exports, shows only the basics. The
 * real component renders plates, tables, traces and images, and `summaryToCsv` turns the first
 * table or plate into CSV for the statistics page.
 */
export interface InstrumentSummary {
  status?: "ok" | "unsupported" | "failed";
  kind?: string;
  software?: string;
  title?: string;
  measured_at?: string | null;
  fields?: { label: string; value: string }[];
  warnings?: string[];
  error?: string;
}

export function summaryToCsv(summary: InstrumentSummary): string | null {
  void summary;
  return null;
}

export function InstrumentFilePreview({ summary }: { summary: InstrumentSummary }) {
  if (summary.status === "failed")
    return (
      <p className="text-sm text-muted-foreground">
        {summary.error ?? "Could not read this file."}
      </p>
    );
  if (summary.status !== "ok")
    return (
      <p className="text-sm text-muted-foreground">
        No preview for this kind of file yet. You can still download it.
      </p>
    );
  return (
    <div className="grid gap-2 text-sm">
      {summary.title && <p className="font-medium">{summary.title}</p>}
      {summary.fields?.map((f) => (
        <p key={f.label}>
          <span className="text-muted-foreground">{f.label}: </span>
          {f.value}
        </p>
      ))}
    </div>
  );
}
