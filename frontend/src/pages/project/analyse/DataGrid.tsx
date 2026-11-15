import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import type { DataRows, DataShape, StatsEngine } from "@/lib/stats/contract";
import { cn } from "@/lib/utils";

const PAGE = 100;
const KIND_LABEL = { numeric: "123", categorical: "abc", text: "Aa" } as const;
const KIND_NAME = { numeric: "numbers", categorical: "category", text: "text" } as const;

/** The loaded file as a spreadsheet: the real rows, column types on the headers, a page at a time. */
export function DataGrid({ engine, shape }: { engine: StatsEngine; shape: DataShape }) {
  const [rows, setRows] = useState<DataRows["rows"]>([]);
  const [total, setTotal] = useState(shape.rows);
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState(false);

  async function more(from: number) {
    setBusy(true);
    try {
      const part = await engine.rows(from, PAGE);
      setTotal(part.total);
      setRows((cur) => (from === 0 ? part.rows : [...cur, ...part.rows]));
      setError(false);
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  }

  // A new file or sheet starts again from the top.
  useEffect(() => {
    let live = true;
    engine
      .rows(0, PAGE)
      .then((part) => {
        if (!live) return;
        setTotal(part.total);
        setRows(part.rows);
        setError(false);
      })
      .catch(() => live && setError(true));
    return () => {
      live = false;
    };
  }, [engine, shape]);

  return (
    <div className="grid gap-2">
      <div className="max-h-80 overflow-auto rounded-xl border bg-card">
        <table className="w-full border-separate border-spacing-0 text-sm" aria-label="Data">
          <thead>
            <tr>
              <th
                scope="col"
                className="sticky top-0 left-0 z-20 border-b border-r bg-muted px-2 py-1.5 text-right font-normal text-muted-foreground"
              >
                <span className="sr-only">Row</span>
              </th>
              {shape.columns.map((c) => (
                <th
                  key={c.name}
                  scope="col"
                  className="sticky top-0 z-10 min-w-28 border-b bg-muted px-3 py-1.5 text-left font-medium"
                >
                  <span
                    title={KIND_NAME[c.kind]}
                    className={cn(
                      "mr-1.5 rounded px-1 text-[10px] font-semibold",
                      c.kind === "numeric"
                        ? "bg-primary/15 text-primary"
                        : "bg-foreground/10 text-muted-foreground",
                    )}
                  >
                    {KIND_LABEL[c.kind]}
                    <span className="sr-only"> {KIND_NAME[c.kind]}</span>
                  </span>
                  {c.name}
                  {c.missing > 0 && (
                    <span className="ml-1 text-xs font-normal text-muted-foreground">
                      ({c.missing} blank)
                    </span>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i}>
                <th
                  scope="row"
                  className="sticky left-0 border-b border-r bg-muted px-2 py-1 text-right font-normal text-muted-foreground tabular-nums"
                >
                  {i + 1}
                </th>
                {row.map((v, j) => (
                  <td
                    key={j}
                    className={cn(
                      "border-b px-3 py-1",
                      shape.columns[j]?.kind === "numeric" && "text-right tabular-nums",
                    )}
                  >
                    {v === null ? <span className="text-muted-foreground">·</span> : String(v)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>
          {error
            ? "Could not show the rows."
            : `Showing ${rows.length.toLocaleString()} of ${total.toLocaleString()} rows`}
        </span>
        {rows.length < total && !error && (
          <Button variant="ghost" size="sm" disabled={busy} onClick={() => void more(rows.length)}>
            Show more rows
          </Button>
        )}
      </div>
    </div>
  );
}
