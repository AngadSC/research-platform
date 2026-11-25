import { useEffect, useMemo, useState } from "react";
import { Spreadsheet } from "@/components/documents/Spreadsheet";
import { addr, sheetToCsv, type Sheet } from "@/lib/sheet";
import { Button } from "@/components/ui/button";
import type { DataRows, DataShape, StatsEngine } from "@/lib/stats/contract";
import { cn } from "@/lib/utils";

const PAGE = 100;
const KIND_LABEL = { numeric: "123", categorical: "abc", text: "Aa" } as const;
const KIND_NAME = { numeric: "numbers", categorical: "category", text: "text" } as const;

/** The loaded file as a spreadsheet: the real rows, column types on the headers, a page at a time. */
export function DataGrid({
  engine,
  shape,
  tall = false,
  onSaveAsSheet,
  onUseEdits,
}: {
  engine: StatsEngine;
  shape: DataShape;
  /** Offer "Save as spreadsheet": a copy of the rows shown, to work on with formulas. */
  onSaveAsSheet?: (sheet: Sheet) => void;
  /** Offer "Analyse these edits": loads the edited sheet, formulas worked out, as the data. */
  onUseEdits?: (csv: string) => void;
  /** Fill the pane (focus mode) instead of stopping at a fixed height. */
  tall?: boolean;
}) {
  const [rows, setRows] = useState<DataRows["rows"]>([]);
  const [total, setTotal] = useState(shape.rows);
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState(false);
  const [mode, setMode] = useState<"sheet" | "types">("sheet");
  // Row 1 holds the column names, as in a spreadsheet; the rows follow. Edits here are a scratch
  // copy: they never change the file or the analysis.
  const [scratch, setScratch] = useState<{ base: Sheet; sheets: Sheet[] } | null>(null);
  const sheet = useMemo<Sheet>(() => {
    const cells: Sheet["cells"] = {};
    shape.columns.forEach((c, j) => {
      cells[addr(j, 0)] = { text: c.name, bold: true, fill: "#e5e7eb" };
    });
    rows.forEach((row, i) =>
      row.forEach((v, j) => {
        if (v !== null && v !== "") cells[addr(j, i + 1)] = { text: String(v) };
      }),
    );
    return { name: "Data", cells };
  }, [rows, shape]);
  // New rows start the scratch copy over.
  const edited = scratch && scratch.base === sheet ? scratch.sheets : null;

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
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div
          role="radiogroup"
          aria-label="Data view"
          className="flex w-fit rounded-lg bg-muted p-0.5"
        >
          {(
            [
              ["sheet", "Spreadsheet"],
              ["types", "Column types"],
            ] as const
          ).map(([v, label]) => (
            <button
              key={v}
              type="button"
              role="radio"
              aria-checked={mode === v}
              onClick={() => setMode(v)}
              className={cn(
                "rounded-md px-3 py-1 text-sm text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
                mode === v && "bg-background font-medium text-foreground shadow-sm",
              )}
            >
              {label}
            </button>
          ))}
        </div>
        {mode === "sheet" && (
          <div className="flex flex-wrap gap-2">
            {onUseEdits && edited && (
              <Button size="sm" onClick={() => onUseEdits(sheetToCsv(edited[0]!))}>
                Analyse these edits
              </Button>
            )}
            {onSaveAsSheet && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => onSaveAsSheet(edited?.[0] ?? sheet)}
              >
                Save as spreadsheet
              </Button>
            )}
          </div>
        )}
      </div>
      {mode === "sheet" ? (
        <>
          <Spreadsheet
            label="Data"
            editable
            tall={tall}
            sheets={edited ?? [sheet]}
            onChange={(sheets) => setScratch({ base: sheet, sheets })}
          />
          <p className="text-xs text-muted-foreground">
            Edits and formulas here never change your file. Choose "Analyse these edits" to run the
            tests on the edited data instead.
          </p>
        </>
      ) : (
        <div
          className={cn(
            "overflow-auto rounded-xl border bg-card",
            tall ? "max-h-[calc(100vh-17rem)]" : "max-h-80",
          )}
        >
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
      )}
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
