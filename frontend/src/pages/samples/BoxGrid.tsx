import type { BoxDetail, Tube } from "@/lib/api-types";
import { cn } from "@/lib/utils";
import { rowLetter } from "./common";

/** A freezer box as a grid: rows are letters, columns are numbers, each cell is a button. */
export function BoxGrid({
  box,
  onEmpty,
  onFilled,
  highlight,
}: {
  box: Pick<BoxDetail, "name" | "rows" | "cols" | "tubes">;
  /** Called for an empty spot; leave out when the person cannot add tubes. */
  onEmpty?: (row: number, col: number) => void;
  onFilled: (tube: Tube) => void;
  /** A tube to mark, such as the one a search found. */
  highlight?: string | null;
}) {
  const at = new Map(box.tubes.map((t) => [`${t.row}-${t.col}`, t]));
  const rows = Array.from({ length: box.rows }, (_, i) => i + 1);
  const cols = Array.from({ length: box.cols }, (_, i) => i + 1);
  return (
    <div className="overflow-x-auto" role="group" aria-label={`Box ${box.name}`}>
      <div
        className="grid w-max gap-1 text-xs"
        style={{ gridTemplateColumns: `1.5rem repeat(${box.cols}, minmax(2.75rem, 3.5rem))` }}
      >
        <span aria-hidden />
        {cols.map((c) => (
          <span key={c} aria-hidden className="text-center text-muted-foreground">
            {c}
          </span>
        ))}
        {rows.map((r) => (
          <div key={r} className="contents">
            <span aria-hidden className="flex items-center justify-center text-muted-foreground">
              {rowLetter(r)}
            </span>
            {cols.map((c) => {
              const pos = `${rowLetter(r)}${c}`;
              const t = at.get(`${r}-${c}`);
              return (
                <button
                  key={c}
                  type="button"
                  aria-label={t ? `${pos}, ${t.sample.code} ${t.sample.name}` : `${pos}, empty`}
                  title={t ? `${t.sample.code} ${t.sample.name}` : undefined}
                  disabled={!t && !onEmpty}
                  onClick={() => (t ? onFilled(t) : onEmpty?.(r, c))}
                  className={cn(
                    "flex aspect-square items-center justify-center overflow-hidden rounded-md border px-0.5 text-[10px] leading-tight font-medium focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
                    t
                      ? "border-primary/40 bg-primary/15 hover:bg-primary/25"
                      : "border-dashed bg-background hover:bg-muted disabled:cursor-default disabled:hover:bg-background",
                    t && t.id === highlight && "ring-2 ring-warning",
                  )}
                >
                  <span className="truncate">{t?.sample.code}</span>
                </button>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}
