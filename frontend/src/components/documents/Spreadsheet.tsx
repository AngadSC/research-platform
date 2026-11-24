import {
  AlignCenter,
  AlignLeft,
  AlignRight,
  Bold,
  ChevronDown,
  Italic,
  Plus,
  Redo2,
  Undo2,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  addr,
  colName,
  DEFAULT_WIDTH,
  display,
  emptySheet,
  Evaluator,
  extent,
  FILLS,
  parseAddr,
  parseTsv,
  shiftCells,
  toTsv,
  type Cell,
  type Sheet,
} from "@/lib/sheet";
import { cn } from "@/lib/utils";

interface Pos {
  r: number;
  c: number;
}
const same = (a: Pos, b: Pos) => a.r === b.r && a.c === b.c;
const HISTORY = 100;
const ARROWS: Record<string, [number, number]> = {
  ArrowDown: [1, 0],
  ArrowUp: [-1, 0],
  ArrowRight: [0, 1],
  ArrowLeft: [0, -1],
};

/** An Excel-style spreadsheet: formula bar, column letters and row numbers, ranges, formulas,
 * formatting, insert and delete, sorting, copy and paste, and several sheets. `editable` off
 * gives the same layout to read. */
export function Spreadsheet({
  sheets,
  onChange,
  editable,
  label,
  tall = false,
}: {
  sheets: Sheet[];
  onChange?: (next: Sheet[]) => void;
  editable: boolean;
  label: string;
  /** Fill more of the window (a spreadsheet page) instead of a compact panel. */
  tall?: boolean;
}) {
  const [active, setActive] = useState(0);
  const [cur, setCur] = useState<Pos>({ r: 0, c: 0 });
  const [end, setEnd] = useState<Pos>({ r: 0, c: 0 }); // the other corner of a selected range
  const [draft, setDraft] = useState<string | null>(null); // text being typed, or null
  const undo = useRef<Sheet[][]>([]);
  const redo = useRef<Sheet[][]>([]);
  const box = useRef<HTMLDivElement>(null);
  const [history, setHistory] = useState({ undo: 0, redo: 0 });
  const bump = () => setHistory({ undo: undo.current.length, redo: redo.current.length });

  const idx = Math.min(active, sheets.length - 1);
  const sheet = sheets[idx]!;
  const ev = useMemo(() => new Evaluator(sheet.cells), [sheet.cells]);
  const { cols, rows } = useMemo(() => extent(sheet.cells), [sheet.cells]);

  const r1 = Math.min(cur.r, end.r);
  const r2 = Math.max(cur.r, end.r);
  const c1 = Math.min(cur.c, end.c);
  const c2 = Math.max(cur.c, end.c);
  const inRange = (r: number, c: number) => r >= r1 && r <= r2 && c >= c1 && c <= c2;
  const curRef = addr(cur.c, cur.r);

  const commit = useCallback(
    (next: Sheet[]) => {
      if (!editable) return;
      undo.current = [...undo.current.slice(-HISTORY + 1), sheets];
      redo.current = [];
      onChange?.(next);
      bump();
    },
    [editable, sheets, onChange],
  );
  const withSheet = (fn: (s: Sheet) => Sheet) =>
    commit(sheets.map((s, i) => (i === idx ? fn(s) : s)));

  const step = (back: boolean) => {
    const from = back ? undo : redo;
    const to = back ? redo : undo;
    const prev = from.current.pop();
    if (!prev) return;
    to.current.push(sheets);
    onChange?.(prev);
    bump();
  };

  /** Each selected cell through `fn`; a cell that ends up empty and plain is removed. */
  const patchRange = (fn: (c: Cell) => Cell) =>
    withSheet((s) => {
      const cells = { ...s.cells };
      for (let r = r1; r <= r2; r++)
        for (let c = c1; c <= c2; c++) {
          const k = addr(c, r);
          const next = fn(cells[k] ?? { text: "" });
          const plain = !next.text && !next.bold && !next.italic && !next.align && !next.fill;
          if (plain && (!next.format || next.format === "general")) delete cells[k];
          else cells[k] = next;
        }
      return { ...s, cells };
    });

  const setText = (ref: string, text: string) =>
    withSheet((s) => {
      const cells = { ...s.cells };
      const old = cells[ref];
      if (!text && !(old && (old.bold || old.italic || old.align || old.fill || old.format)))
        delete cells[ref];
      else cells[ref] = { ...old, text };
      return { ...s, cells };
    });

  const startEdit = (text?: string) => {
    if (!editable) return;
    setDraft(text ?? sheet.cells[curRef]?.text ?? "");
  };
  const finishEdit = (save: boolean) => {
    if (draft !== null && save && draft !== (sheet.cells[curRef]?.text ?? ""))
      setText(curRef, draft);
    setDraft(null);
    box.current?.focus();
  };
  const go = (dr: number, dc: number, extend = false) => {
    const next = {
      r: Math.max(0, Math.min(rows - 1, (extend ? end.r : cur.r) + dr)),
      c: Math.max(0, Math.min(cols - 1, (extend ? end.c : cur.c) + dc)),
    };
    if (extend) setEnd(next);
    else {
      setCur(next);
      setEnd(next);
    }
  };

  const clearRange = () => {
    withSheet((s) => {
      const cells = { ...s.cells };
      for (let r = r1; r <= r2; r++)
        for (let c = c1; c <= c2; c++) {
          const k = addr(c, r);
          if (cells[k]) cells[k] = { ...cells[k], text: "" };
          if (
            cells[k] &&
            !cells[k]!.bold &&
            !cells[k]!.italic &&
            !cells[k]!.align &&
            !cells[k]!.fill &&
            !cells[k]!.format
          )
            delete cells[k];
        }
      return { ...s, cells };
    });
  };

  const rangeText = (raw: boolean) => {
    const out: string[][] = [];
    for (let r = r1; r <= r2; r++) {
      const line: string[] = [];
      for (let c = c1; c <= c2; c++) {
        const k = addr(c, r);
        line.push(
          raw ? (sheet.cells[k]?.text ?? "") : display(ev.value(k), sheet.cells[k]?.format),
        );
      }
      out.push(line);
    }
    return toTsv(out);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (draft !== null) return; // the cell's own box handles keys while typing
    const mod = e.ctrlKey || e.metaKey;
    if (mod && e.key.toLowerCase() === "z") {
      e.preventDefault();
      step(!e.shiftKey);
    } else if (mod && e.key.toLowerCase() === "y") {
      e.preventDefault();
      step(false);
    } else if (mod && e.key.toLowerCase() === "b" && editable) {
      e.preventDefault();
      patchRange((c) => ({ ...c, bold: !sheet.cells[curRef]?.bold }));
    } else if (mod && e.key.toLowerCase() === "i" && editable) {
      e.preventDefault();
      patchRange((c) => ({ ...c, italic: !sheet.cells[curRef]?.italic }));
    } else if (mod && e.key.toLowerCase() === "a") {
      e.preventDefault();
      setCur({ r: 0, c: 0 });
      setEnd({ r: rows - 1, c: cols - 1 });
    } else if (mod) {
      return; // copy, cut and paste arrive as clipboard events
    } else if (ARROWS[e.key]) {
      e.preventDefault();
      const [dr, dc] = ARROWS[e.key]!;
      go(dr, dc, e.shiftKey);
    } else if (e.key === "Tab") {
      e.preventDefault();
      go(0, e.shiftKey ? -1 : 1);
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (editable) startEdit();
      else go(1, 0);
    } else if (e.key === "F2") {
      e.preventDefault();
      startEdit();
    } else if (e.key === "Home") {
      e.preventDefault();
      go(0, -cur.c);
    } else if (e.key === "Delete" || e.key === "Backspace") {
      e.preventDefault();
      if (editable) clearRange();
    } else if (e.key.length === 1 && editable) {
      e.preventDefault();
      startEdit(e.key); // typing over a cell replaces what it held
    }
  };

  const onCopy = (e: React.ClipboardEvent) => {
    if (draft !== null) return;
    e.preventDefault();
    e.clipboardData.setData("text/plain", rangeText(true));
  };
  const onCut = (e: React.ClipboardEvent) => {
    if (draft !== null) return;
    onCopy(e);
    if (editable) clearRange();
  };
  const onPaste = (e: React.ClipboardEvent) => {
    if (draft !== null || !editable) return;
    e.preventDefault();
    const grid = parseTsv(e.clipboardData.getData("text/plain"));
    withSheet((s) => {
      const cells = { ...s.cells };
      grid.forEach((line, dr) =>
        line.forEach((text, dc) => {
          const k = addr(cur.c + dc, cur.r + dr);
          if (text || cells[k]) cells[k] = { ...cells[k], text };
          if (!text && cells[k] && Object.keys(cells[k]!).length === 1) delete cells[k];
        }),
      );
      return { ...s, cells };
    });
    setEnd({ r: cur.r + grid.length - 1, c: cur.c + (grid[0]?.length ?? 1) - 1 });
  };

  const insert = (axis: "row" | "col", after: boolean) => {
    const at = (axis === "row" ? cur.r : cur.c) + (after ? 1 : 0);
    withSheet((s) => ({ ...s, cells: shiftCells(s.cells, axis, at, 1) }));
  };
  const remove = (axis: "row" | "col") =>
    withSheet((s) => {
      let cells = s.cells;
      const lo = axis === "row" ? r1 : c1;
      const hi = axis === "row" ? r2 : c2;
      for (let n = hi; n >= lo; n--) cells = shiftCells(cells, axis, n, -1);
      return { ...s, cells };
    });

  /** Sorts the selected rows by the active column. Formulas keep their text, so sort values. */
  const sortBy = (dir: 1 | -1) =>
    withSheet((s) => {
      const lines = [];
      for (let r = r1; r <= r2; r++) {
        const row: (Cell | undefined)[] = [];
        for (let c = c1; c <= c2; c++) row.push(s.cells[addr(c, r)]);
        lines.push({ row, key: ev.value(addr(cur.c, r)) });
      }
      lines.sort((a, b) => {
        const x = a.key;
        const y = b.key;
        if (x === "" || y === "") return x === y ? 0 : x === "" ? 1 : -1; // blanks last
        const both = typeof x === "number" && typeof y === "number";
        const d = both ? x - y : String(x).localeCompare(String(y), undefined, { numeric: true });
        return d * dir;
      });
      const cells = { ...s.cells };
      lines.forEach((line, i) =>
        line.row.forEach((cell, j) => {
          const k = addr(c1 + j, r1 + i);
          if (cell) cells[k] = cell;
          else delete cells[k];
        }),
      );
      return { ...s, cells };
    });

  const resize = (c: number, startX: number) => {
    const start = sheet.widths?.[c] ?? DEFAULT_WIDTH;
    const move = (e: MouseEvent) =>
      withSheetLive(c, Math.max(40, Math.min(480, start + e.clientX - startX)));
    const up = () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
  };
  const withSheetLive = (c: number, w: number) =>
    onChange?.(sheets.map((s, i) => (i === idx ? { ...s, widths: { ...s.widths, [c]: w } } : s)));

  // Keep the active cell in view.
  useEffect(() => {
    box.current
      ?.querySelector(`[data-cell="${curRef}"]`)
      ?.scrollIntoView?.({ block: "nearest", inline: "nearest" });
  }, [curRef]);

  const stats = useMemo(() => {
    let n = 0;
    let sum = 0;
    let cells = 0;
    for (let r = r1; r <= r2; r++)
      for (let c = c1; c <= c2; c++) {
        const k = addr(c, r);
        if (sheet.cells[k]?.text) cells++;
        const v = ev.value(k);
        if (typeof v === "number") {
          n++;
          sum += v;
        }
      }
    return { n, sum, cells, single: r1 === r2 && c1 === c2 };
  }, [ev, sheet.cells, r1, r2, c1, c2]);

  const here = sheet.cells[curRef];
  const addSheet = () => {
    let n = sheets.length + 1;
    while (sheets.some((s) => s.name === `Sheet${n}`)) n++;
    commit([...sheets, emptySheet(`Sheet${n}`)]);
    setActive(sheets.length);
  };
  const [renaming, setRenaming] = useState<number | null>(null);

  const btn = "size-8";
  return (
    <div
      role="group"
      aria-label={label}
      className="grid min-w-0 gap-0 overflow-hidden rounded-lg border bg-background"
    >
      {editable && (
        <div
          role="toolbar"
          aria-label="Spreadsheet tools"
          className="flex flex-wrap items-center gap-0.5 border-b bg-muted/40 p-1"
        >
          <Button
            variant="ghost"
            size="icon"
            className={btn}
            aria-label="Undo edit"
            disabled={!history.undo}
            onClick={() => step(true)}
          >
            <Undo2 aria-hidden />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className={btn}
            aria-label="Redo edit"
            disabled={!history.redo}
            onClick={() => step(false)}
          >
            <Redo2 aria-hidden />
          </Button>
          <span className="mx-1 h-5 w-px bg-border" aria-hidden />
          <Button
            variant="ghost"
            size="icon"
            className={cn(btn, here?.bold && "bg-accent")}
            aria-label="Bold"
            aria-pressed={!!here?.bold}
            onClick={() => patchRange((c) => ({ ...c, bold: !here?.bold }))}
          >
            <Bold aria-hidden />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className={cn(btn, here?.italic && "bg-accent")}
            aria-label="Italic"
            aria-pressed={!!here?.italic}
            onClick={() => patchRange((c) => ({ ...c, italic: !here?.italic }))}
          >
            <Italic aria-hidden />
          </Button>
          {(["left", "center", "right"] as const).map((a) => {
            const Icon = a === "left" ? AlignLeft : a === "center" ? AlignCenter : AlignRight;
            return (
              <Button
                key={a}
                variant="ghost"
                size="icon"
                className={cn(btn, here?.align === a && "bg-accent")}
                aria-label={`Align ${a}`}
                aria-pressed={here?.align === a}
                onClick={() => patchRange((c) => ({ ...c, align: c.align === a ? undefined : a }))}
              >
                <Icon aria-hidden />
              </Button>
            );
          })}
          <span className="mx-1 h-5 w-px bg-border" aria-hidden />
          <select
            aria-label="Number format"
            value={here?.format ?? "general"}
            onChange={(e) =>
              patchRange((c) => ({ ...c, format: e.target.value as Cell["format"] }))
            }
            className="h-8 rounded-md border bg-background px-2 text-sm"
          >
            <option value="general">Automatic</option>
            <option value="number">Number (1,234.00)</option>
            <option value="percent">Percent</option>
            <option value="currency">Currency</option>
          </select>
          <div role="group" aria-label="Fill colour" className="ml-1 flex items-center gap-1">
            {FILLS.map((f) => (
              <button
                key={f || "none"}
                type="button"
                aria-label={f ? `Fill ${f}` : "No fill"}
                title={f ? "Fill colour" : "No fill"}
                onClick={() => patchRange((c) => ({ ...c, fill: f || undefined }))}
                className={cn(
                  "size-5 rounded border",
                  here?.fill === f || (!f && !here?.fill) ? "ring-2 ring-ring" : "",
                )}
                style={f ? { background: f } : undefined}
              />
            ))}
          </div>
          <span className="mx-1 h-5 w-px bg-border" aria-hidden />
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="sm">
                Edit <ChevronDown aria-hidden />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start">
              <DropdownMenuItem onSelect={() => insert("row", false)}>
                Insert row above
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => insert("row", true)}>
                Insert row below
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => insert("col", false)}>
                Insert column left
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => insert("col", true)}>
                Insert column right
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => remove("row")}>Delete row</DropdownMenuItem>
              <DropdownMenuItem onSelect={() => remove("col")}>Delete column</DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => sortBy(1)}>Sort selection A to Z</DropdownMenuItem>
              <DropdownMenuItem onSelect={() => sortBy(-1)}>Sort selection Z to A</DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={clearRange}>Clear contents</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      )}

      <div className="flex items-center border-b text-sm">
        <span
          aria-label="Selected cell"
          className="w-20 shrink-0 border-r px-2 py-1.5 text-center font-medium"
        >
          {r1 === r2 && c1 === c2 ? curRef : `${addr(c1, r1)}:${addr(c2, r2)}`}
        </span>
        <span aria-hidden className="px-2 text-muted-foreground italic">
          fx
        </span>
        <input
          aria-label="Formula bar"
          className="min-w-0 flex-1 bg-transparent px-1 py-1.5 outline-none"
          readOnly={!editable}
          value={draft ?? here?.text ?? ""}
          onFocus={() => editable && draft === null && setDraft(here?.text ?? "")}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              finishEdit(true);
              go(1, 0);
            } else if (e.key === "Escape") finishEdit(false);
          }}
          onBlur={() => draft !== null && finishEdit(true)}
        />
      </div>

      <div
        ref={box}
        tabIndex={0}
        role="grid"
        aria-label={`${label}, ${sheet.name}`}
        aria-rowcount={rows}
        aria-colcount={cols}
        onKeyDown={onKeyDown}
        onCopy={onCopy}
        onCut={onCut}
        onPaste={onPaste}
        className={cn(
          "relative overflow-auto outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset",
          tall ? "max-h-[calc(100vh-18rem)] min-h-80" : "max-h-96",
        )}
      >
        <table
          className="border-separate border-spacing-0 text-sm select-none"
          style={{ tableLayout: "fixed" }}
        >
          <colgroup>
            <col style={{ width: 48 }} />
            {Array.from({ length: cols }, (_, c) => (
              <col key={c} style={{ width: sheet.widths?.[c] ?? DEFAULT_WIDTH }} />
            ))}
          </colgroup>
          <thead>
            <tr>
              <th className="sticky top-0 left-0 z-30 border-r border-b bg-muted" />
              {Array.from({ length: cols }, (_, c) => (
                <th
                  key={c}
                  scope="col"
                  onClick={() => (setCur({ r: 0, c }), setEnd({ r: rows - 1, c }))}
                  className={cn(
                    "relative sticky top-0 z-20 border-r border-b bg-muted py-1 text-center text-xs font-medium text-muted-foreground",
                    c >= c1 && c <= c2 && "bg-accent text-foreground",
                  )}
                >
                  {colName(c)}
                  {editable && (
                    <span
                      aria-hidden
                      onMouseDown={(e) => (e.stopPropagation(), resize(c, e.clientX))}
                      className="absolute top-0 right-0 h-full w-1.5 cursor-col-resize hover:bg-primary/40"
                    />
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: rows }, (_, r) => (
              <tr key={r}>
                <th
                  scope="row"
                  onClick={() => (setCur({ r, c: 0 }), setEnd({ r, c: cols - 1 }))}
                  className={cn(
                    "sticky left-0 z-10 border-r border-b bg-muted px-1 text-center text-xs font-normal text-muted-foreground tabular-nums",
                    r >= r1 && r <= r2 && "bg-accent text-foreground",
                  )}
                >
                  {r + 1}
                </th>
                {Array.from({ length: cols }, (_, c) => {
                  const k = addr(c, r);
                  const cell = sheet.cells[k];
                  const isCur = cur.r === r && cur.c === c;
                  const val = cell ? ev.value(k) : "";
                  const text = display(val, cell?.format);
                  const numeric = typeof val === "number";
                  return (
                    <td
                      key={c}
                      data-cell={k}
                      role="gridcell"
                      aria-selected={inRange(r, c)}
                      onMouseDown={(e) => {
                        if (draft !== null) finishEdit(true);
                        if (e.shiftKey) setEnd({ r, c });
                        else {
                          setCur({ r, c });
                          setEnd({ r, c });
                        }
                        const drag = (m: MouseEvent) => {
                          const el = (m.target as HTMLElement).closest(
                            "[data-cell]",
                          ) as HTMLElement | null;
                          const p = el ? parseAddr(el.dataset.cell!) : null;
                          if (p && !same(p, { r, c })) setEnd(p);
                        };
                        const up = () => {
                          window.removeEventListener("mouseover", drag);
                          window.removeEventListener("mouseup", up);
                        };
                        window.addEventListener("mouseover", drag);
                        window.addEventListener("mouseup", up);
                      }}
                      onDoubleClick={() => (setCur({ r, c }), startEdit(cell?.text ?? ""))}
                      style={{
                        textAlign: cell?.align ?? (numeric ? "right" : "left"),
                        background: cell?.fill && !inRange(r, c) ? cell.fill : undefined,
                      }}
                      className={cn(
                        "overflow-hidden border-r border-b px-1.5 py-0.5 whitespace-nowrap",
                        cell?.bold && "font-bold",
                        cell?.italic && "italic",
                        inRange(r, c) && !isCur && "bg-primary/10",
                        isCur && "outline-2 -outline-offset-1 outline-primary",
                        typeof val === "object" && "text-destructive",
                        cell?.fill && "text-neutral-900",
                      )}
                    >
                      {isCur && draft !== null ? (
                        <input
                          autoFocus
                          aria-label={`Edit ${k}`}
                          value={draft}
                          onChange={(e) => setDraft(e.target.value)}
                          onKeyDown={(e) => {
                            e.stopPropagation();
                            if (e.key === "Enter") {
                              e.preventDefault();
                              finishEdit(true);
                              go(e.shiftKey ? -1 : 1, 0);
                            } else if (e.key === "Tab") {
                              e.preventDefault();
                              finishEdit(true);
                              go(0, e.shiftKey ? -1 : 1);
                            } else if (e.key === "Escape") finishEdit(false);
                          }}
                          onBlur={() => draft !== null && finishEdit(true)}
                          className="w-full bg-background outline-none"
                        />
                      ) : (
                        text
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between gap-3 border-t bg-muted/40 text-xs">
        <div
          role="tablist"
          aria-label="Sheets"
          className="flex min-w-0 items-center overflow-x-auto"
        >
          {sheets.map((s, i) => (
            <div
              key={i}
              className={cn(
                "flex shrink-0 items-center border-r",
                i === idx ? "bg-background font-medium" : "hover:bg-accent",
              )}
            >
              {renaming === i && editable ? (
                <input
                  autoFocus
                  aria-label="Sheet name"
                  defaultValue={s.name}
                  maxLength={40}
                  className="w-24 bg-background px-2 py-1.5 outline-none"
                  onBlur={(e) => {
                    const name = e.target.value.trim();
                    if (name && !sheets.some((o, j) => j !== i && o.name === name))
                      commit(sheets.map((o, j) => (j === i ? { ...o, name } : o)));
                    setRenaming(null);
                  }}
                  onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
                />
              ) : (
                <button
                  type="button"
                  role="tab"
                  aria-selected={i === idx}
                  onClick={() => (
                    setActive(i),
                    setCur({ r: 0, c: 0 }),
                    setEnd({ r: 0, c: 0 }),
                    setDraft(null)
                  )}
                  onDoubleClick={() => editable && setRenaming(i)}
                  className="px-3 py-1.5"
                >
                  {s.name}
                </button>
              )}
              {editable && sheets.length > 1 && i === idx && (
                <button
                  type="button"
                  aria-label={`Delete ${s.name}`}
                  className="mr-1 rounded p-0.5 text-muted-foreground hover:bg-muted"
                  onClick={() => {
                    commit(sheets.filter((_, j) => j !== i));
                    setActive(0);
                  }}
                >
                  <X className="size-3" aria-hidden />
                </button>
              )}
            </div>
          ))}
          {editable && (
            <Button
              variant="ghost"
              size="icon"
              className="size-7"
              aria-label="Add a sheet"
              onClick={addSheet}
            >
              <Plus aria-hidden />
            </Button>
          )}
        </div>
        <span className="shrink-0 px-3 tabular-nums text-muted-foreground" aria-live="polite">
          {stats.single || stats.n === 0
            ? stats.single
              ? ""
              : `Count: ${stats.cells}`
            : `Sum: ${display(stats.sum)} · Average: ${display(stats.sum / stats.n)} · Count: ${stats.n}`}
        </span>
      </div>
    </div>
  );
}
