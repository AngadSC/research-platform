import type { KeyboardEvent, ReactNode } from "react";
import { SelectBox, type Selection } from "@/components/shared/bulk";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export interface Column<T> {
  key: string;
  header: string;
  cell: (row: T) => ReactNode;
  className?: string;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  rows: T[];
  getRowKey: (row: T) => string;
  loading?: boolean;
  /** Shown instead of the table when there are no rows (use <EmptyState>). */
  empty?: ReactNode;
  onRowClick?: (row: T) => void;
  /** Adds a checkbox column (and a select-all in the header). */
  selection?: Selection;
  /** What the checkboxes are called for screen readers, e.g. "item". */
  selectLabel?: (row: T) => string;
}

/** Column classes that drop a lower-value column when the content area (not the viewport) is
 * narrow, e.g. with the assistant docked. Use on columns whose data is also in the row's detail. */
export const HIDE_NARROW = "hidden @2xl:table-cell";
export const HIDE_NARROWER = "hidden @4xl:table-cell";

const SKELETON_ROWS = 5;

export function DataTable<T>({
  columns,
  rows,
  getRowKey,
  loading,
  empty,
  onRowClick,
  selection,
  selectLabel,
}: DataTableProps<T>) {
  if (!loading && rows.length === 0 && empty) return <>{empty}</>;

  const onKey = (e: KeyboardEvent, row: T) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onRowClick?.(row);
    }
  };

  return (
    <div className="rounded-lg border">
      <Table aria-busy={loading || undefined}>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            {selection && (
              <TableHead className="w-8">
                <SelectBox
                  checked={selection.all}
                  label="Select all rows"
                  onToggle={selection.toggleAll}
                />
              </TableHead>
            )}
            {columns.map((c) => (
              <TableHead key={c.key} className={c.className}>
                {c.header}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {loading
            ? Array.from({ length: SKELETON_ROWS }, (_, i) => (
                <TableRow key={i} data-testid="skeleton-row">
                  {selection && <TableCell />}
                  {columns.map((c) => (
                    <TableCell key={c.key}>
                      <Skeleton className="h-4 w-3/4" />
                    </TableCell>
                  ))}
                </TableRow>
              ))
            : rows.map((row) => (
                <TableRow
                  key={getRowKey(row)}
                  onClick={onRowClick && (() => onRowClick(row))}
                  onKeyDown={onRowClick && ((e) => onKey(e, row))}
                  tabIndex={onRowClick ? 0 : undefined}
                  className={
                    onRowClick
                      ? "cursor-pointer focus-visible:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset"
                      : undefined
                  }
                >
                  {selection && (
                    <TableCell>
                      <SelectBox
                        checked={selection.has(getRowKey(row))}
                        label={selectLabel?.(row) ?? "Select row"}
                        onToggle={(shift) => selection.toggle(getRowKey(row), shift)}
                      />
                    </TableCell>
                  )}
                  {columns.map((c) => (
                    <TableCell key={c.key} className={c.className}>
                      {c.cell(row)}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
        </TableBody>
      </Table>
    </div>
  );
}
