/** A small spreadsheet engine: cells hold text; text starting with "=" is a formula. Written for
 * this app (no spreadsheet library), covering what a lab uses day to day: + - * / ^ & comparisons,
 * cell references and ranges, and the common functions below. */

export interface Cell {
  /** What was typed: a number, text or a formula such as "=SUM(A1:A5)". */
  text: string;
  bold?: boolean;
  italic?: boolean;
  align?: "left" | "center" | "right";
  format?: "general" | "number" | "percent" | "currency";
  /** Background, one of FILLS. */
  fill?: string;
}

export interface Sheet {
  name: string;
  cells: Record<string, Cell>;
  /** Column widths in pixels, by column index. */
  widths?: Record<number, number>;
}

/** What a spreadsheet document stores: one block holding its sheets. */
export interface SheetBlock {
  type: "sheet";
  sheets: Sheet[];
}

export const DEFAULT_COLS = 26;
export const DEFAULT_ROWS = 100;
export const DEFAULT_WIDTH = 96;
export const FILLS = ["", "#fef08a", "#bbf7d0", "#bfdbfe", "#fbcfe8", "#fed7aa", "#e5e7eb"];

export const emptySheet = (name = "Sheet1"): Sheet => ({ name, cells: {} });
export const emptyBlock = (): SheetBlock => ({ type: "sheet", sheets: [emptySheet()] });

/** The sheets stored in a document's content, or one blank sheet. */
export function sheetsOf(content: unknown[]): Sheet[] {
  const block = content.find((b) => (b as { type?: string })?.type === "sheet") as
    SheetBlock | undefined;
  return block?.sheets?.length ? block.sheets : [emptySheet()];
}

export const colName = (i: number): string => {
  let n = i + 1;
  let s = "";
  while (n > 0) {
    const r = (n - 1) % 26;
    s = String.fromCharCode(65 + r) + s;
    n = Math.floor((n - 1) / 26);
  }
  return s;
};

const colIndex = (name: string): number =>
  [...name].reduce((n, ch) => n * 26 + ch.charCodeAt(0) - 64, 0) - 1;

export const addr = (c: number, r: number) => `${colName(c)}${r + 1}`;

export function parseAddr(ref: string): { c: number; r: number } | null {
  const m = /^\$?([A-Z]{1,3})\$?(\d{1,6})$/.exec(ref.toUpperCase());
  return m ? { c: colIndex(m[1]!), r: Number(m[2]) - 1 } : null;
}

export type Value = number | string | boolean | SheetError;
export class SheetError {
  constructor(public code: string) {}
  toString() {
    return this.code;
  }
}
const err = (code: string) => new SheetError(code);

// ------------------------------------------------------------------ parsing

type Node =
  | { t: "num"; v: number }
  | { t: "str"; v: string }
  | { t: "bool"; v: boolean }
  | { t: "ref"; c: number; r: number }
  | { t: "range"; a: { c: number; r: number }; b: { c: number; r: number } }
  | { t: "un"; op: string; x: Node }
  | { t: "bin"; op: string; l: Node; r: Node }
  | { t: "call"; name: string; args: Node[] };

const TOKEN =
  /\s*(?:(\d+\.?\d*(?:[eE][+-]?\d+)?|\.\d+)|"((?:[^"]|"")*)"|(\$?[A-Za-z]{1,3}\$?\d+(?::\$?[A-Za-z]{1,3}\$?\d+)?)(?![A-Za-z0-9_(])|([A-Za-z_][A-Za-z0-9_.]*)|(<>|<=|>=|[-+*/^&=<>(),%]))/y;

function tokenize(src: string) {
  const out: { k: string; v: string }[] = [];
  TOKEN.lastIndex = 0;
  while (TOKEN.lastIndex < src.length) {
    if (/^\s*$/.test(src.slice(TOKEN.lastIndex))) break;
    const m = TOKEN.exec(src);
    if (!m) throw err("#NAME?");
    if (m[1] !== undefined) out.push({ k: "num", v: m[1] });
    else if (m[2] !== undefined) out.push({ k: "str", v: m[2].replace(/""/g, '"') });
    else if (m[3] !== undefined) out.push({ k: "ref", v: m[3] });
    else if (m[4] !== undefined) out.push({ k: "word", v: m[4] });
    else out.push({ k: "op", v: m[5]! });
  }
  return out;
}

export function parse(src: string): Node {
  const toks = tokenize(src);
  let i = 0;
  const peek = () => toks[i];
  const take = () => toks[i++];
  const isOp = (...ops: string[]) => peek()?.k === "op" && ops.includes(peek()!.v);

  function primary(): Node {
    const t = take();
    if (!t) throw err("#ERROR!");
    if (t.k === "num") return { t: "num", v: Number(t.v) };
    if (t.k === "str") return { t: "str", v: t.v };
    if (t.k === "ref") {
      const [a, b] = t.v.split(":");
      const pa = parseAddr(a!);
      if (!pa) throw err("#REF!");
      if (!b) return { t: "ref", ...pa };
      const pb = parseAddr(b);
      if (!pb) throw err("#REF!");
      return { t: "range", a: pa, b: pb };
    }
    if (t.k === "word") {
      const up = t.v.toUpperCase();
      if (isOp("(")) {
        take();
        const args: Node[] = [];
        if (!isOp(")")) {
          do args.push(compare());
          while (isOp(",") && take());
        }
        if (!isOp(")")) throw err("#ERROR!");
        take();
        return { t: "call", name: up, args };
      }
      if (up === "TRUE") return { t: "bool", v: true };
      if (up === "FALSE") return { t: "bool", v: false };
      throw err("#NAME?");
    }
    if (t.v === "(") {
      const x = compare();
      if (!isOp(")")) throw err("#ERROR!");
      take();
      return x;
    }
    throw err("#ERROR!");
  }
  function postfix(): Node {
    let x = primary();
    while (isOp("%")) {
      take();
      x = { t: "bin", op: "/", l: x, r: { t: "num", v: 100 } };
    }
    return x;
  }
  // As in Excel: a minus sign binds tighter than ^, and ^ chains left to right.
  function unary(): Node {
    if (isOp("-", "+")) {
      const op = take()!.v;
      return { t: "un", op, x: unary() };
    }
    return postfix();
  }
  function power(): Node {
    let l = unary();
    while (isOp("^")) l = { t: "bin", op: take()!.v, l, r: unary() };
    return l;
  }
  function term(): Node {
    let l = power();
    while (isOp("*", "/")) l = { t: "bin", op: take()!.v, l, r: power() };
    return l;
  }
  function sum(): Node {
    let l = term();
    while (isOp("+", "-")) l = { t: "bin", op: take()!.v, l, r: term() };
    return l;
  }
  function concat(): Node {
    let l = sum();
    while (isOp("&")) l = { t: "bin", op: take()!.v, l, r: sum() };
    return l;
  }
  function compare(): Node {
    let l = concat();
    while (isOp("=", "<>", "<", ">", "<=", ">=")) l = { t: "bin", op: take()!.v, l, r: concat() };
    return l;
  }
  const tree = compare();
  if (i < toks.length) throw err("#ERROR!");
  return tree;
}

// --------------------------------------------------------------- evaluation

const isErr = (v: unknown): v is SheetError => v instanceof SheetError;

/** What a cell's text means as a value: a number when it reads as one, else text. */
export function literal(text: string): Value {
  const t = text.trim();
  if (t === "") return "";
  if (/^[-+]?(\d+\.?\d*|\.\d+)(e[-+]?\d+)?$/i.test(t)) return Number(t);
  if (/^[-+]?(\d+\.?\d*|\.\d+)%$/.test(t)) return Number(t.slice(0, -1)) / 100;
  if (/^true$/i.test(t)) return true;
  if (/^false$/i.test(t)) return false;
  return text;
}

const num = (v: Value): number => {
  if (isErr(v)) throw v;
  if (typeof v === "number") return v;
  if (typeof v === "boolean") return v ? 1 : 0;
  if (v === "") return 0;
  const n = Number(v);
  if (Number.isNaN(n)) throw err("#VALUE!");
  return n;
};
const str = (v: Value): string => {
  if (isErr(v)) throw v;
  return typeof v === "boolean" ? (v ? "TRUE" : "FALSE") : String(v);
};

/** Evaluates every cell of one sheet on demand, remembering results and catching loops. */
export class Evaluator {
  private memo = new Map<string, Value>();
  private busy = new Set<string>();
  constructor(private cells: Record<string, Cell>) {}

  value(ref: string): Value {
    const hit = this.memo.get(ref);
    if (hit !== undefined) return hit;
    const text = this.cells[ref]?.text ?? "";
    let out: Value;
    if (!text.startsWith("=")) out = literal(text);
    else if (this.busy.has(ref)) return err("#CIRC!");
    else {
      this.busy.add(ref);
      try {
        out = this.run(parse(text.slice(1)));
      } catch (e) {
        out = isErr(e) ? e : err("#ERROR!");
      } finally {
        this.busy.delete(ref);
      }
    }
    this.memo.set(ref, out);
    return out;
  }

  private cell(c: number, r: number): Value {
    if (c < 0 || r < 0) throw err("#REF!");
    const v = this.value(addr(c, r));
    if (isErr(v)) throw v;
    return v;
  }

  private flat(args: Node[], numbersOnly = true): Value[] {
    const out: Value[] = [];
    for (const a of args) {
      if (a.t === "range") {
        for (let r = Math.min(a.a.r, a.b.r); r <= Math.max(a.a.r, a.b.r); r++)
          for (let c = Math.min(a.a.c, a.b.c); c <= Math.max(a.a.c, a.b.c); c++) {
            const v = this.cell(c, r);
            // In a range, text and blanks are skipped (as in Excel); typed-in arguments are not.
            if (!numbersOnly || typeof v === "number") out.push(v);
          }
      } else {
        const v = this.run(a);
        if (isErr(v)) throw v;
        out.push(numbersOnly ? num(v) : v);
      }
    }
    return out;
  }

  private run(n: Node): Value {
    switch (n.t) {
      case "num":
      case "str":
      case "bool":
        return n.v;
      case "ref":
        return this.cell(n.c, n.r);
      case "range":
        throw err("#VALUE!");
      case "un":
        return n.op === "-" ? -num(this.run(n.x)) : num(this.run(n.x));
      case "bin": {
        const l = this.run(n.l);
        const r = this.run(n.r);
        switch (n.op) {
          case "+":
            return num(l) + num(r);
          case "-":
            return num(l) - num(r);
          case "*":
            return num(l) * num(r);
          case "/": {
            const d = num(r);
            if (d === 0) throw err("#DIV/0!");
            return num(l) / d;
          }
          case "^":
            return num(l) ** num(r);
          case "&":
            return str(l) + str(r);
          default: {
            const both = typeof l === "number" && typeof r === "number";
            const a = both ? l : str(l).toLowerCase();
            const b = both ? r : str(r).toLowerCase();
            return n.op === "="
              ? a === b
              : n.op === "<>"
                ? a !== b
                : n.op === "<"
                  ? a < b
                  : n.op === ">"
                    ? a > b
                    : n.op === "<="
                      ? a <= b
                      : a >= b;
          }
        }
      }
      case "call":
        return this.call(n.name, n.args);
    }
  }

  private call(name: string, args: Node[]): Value {
    const nums = () => this.flat(args) as number[];
    switch (name) {
      case "SUM":
        return nums().reduce((a, b) => a + b, 0);
      case "PRODUCT":
        return nums().reduce((a, b) => a * b, 1);
      case "AVERAGE":
      case "MEAN": {
        const v = nums();
        if (!v.length) throw err("#DIV/0!");
        return v.reduce((a, b) => a + b, 0) / v.length;
      }
      case "MIN": {
        const v = nums();
        return v.length ? Math.min(...v) : 0;
      }
      case "MAX": {
        const v = nums();
        return v.length ? Math.max(...v) : 0;
      }
      case "COUNT":
        return this.flat(args).length;
      case "COUNTA": {
        let n = 0;
        for (const v of this.flat(args, false)) if (v !== "") n++;
        return n;
      }
      case "MEDIAN": {
        const v = nums().sort((a, b) => a - b);
        if (!v.length) throw err("#NUM!");
        const m = Math.floor(v.length / 2);
        return v.length % 2 ? v[m]! : (v[m - 1]! + v[m]!) / 2;
      }
      case "VAR":
      case "STDEV": {
        const v = nums();
        if (v.length < 2) throw err("#DIV/0!");
        const mean = v.reduce((a, b) => a + b, 0) / v.length;
        const variance = v.reduce((a, b) => a + (b - mean) ** 2, 0) / (v.length - 1);
        return name === "VAR" ? variance : Math.sqrt(variance);
      }
      case "ABS":
        return Math.abs(num(this.run(args[0]!)));
      case "SQRT": {
        const x = num(this.run(args[0]!));
        if (x < 0) throw err("#NUM!");
        return Math.sqrt(x);
      }
      case "POWER":
        return num(this.run(args[0]!)) ** num(this.run(args[1]!));
      case "ROUND": {
        const f = 10 ** (args[1] ? num(this.run(args[1])) : 0);
        return Math.round(num(this.run(args[0]!)) * f) / f;
      }
      case "IF": {
        const c = this.run(args[0]!);
        const truthy = typeof c === "string" ? c !== "" : !!num(c);
        const branch = truthy ? args[1] : args[2];
        return branch ? this.run(branch) : false;
      }
      case "AND":
        return args.every((a) => !!num(this.run(a)));
      case "OR":
        return args.some((a) => !!num(this.run(a)));
      case "NOT":
        return !num(this.run(args[0]!));
      case "CONCAT":
      case "CONCATENATE":
        return this.flat(args, false).map(str).join("");
      case "LEN":
        return str(this.run(args[0]!)).length;
      case "UPPER":
        return str(this.run(args[0]!)).toUpperCase();
      case "LOWER":
        return str(this.run(args[0]!)).toLowerCase();
      default:
        throw err("#NAME?");
    }
  }
}

// --------------------------------------------------------------- display

export function display(v: Value, format: Cell["format"] = "general"): string {
  if (isErr(v)) return v.code;
  if (typeof v === "boolean") return v ? "TRUE" : "FALSE";
  if (typeof v === "string") return v;
  if (!Number.isFinite(v)) return "#NUM!";
  switch (format) {
    case "number":
      return v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    case "percent":
      return `${(v * 100).toLocaleString(undefined, { maximumFractionDigits: 2 })}%`;
    case "currency":
      return v.toLocaleString(undefined, { style: "currency", currency: "USD" });
    default:
      return String(Math.round(v * 1e10) / 1e10);
  }
}

// ------------------------------------------------------------ editing aids

/** The sheet's used area, so a column or row to the right still shows. */
export function extent(cells: Record<string, Cell>) {
  let cols = DEFAULT_COLS;
  let rows = DEFAULT_ROWS;
  for (const k of Object.keys(cells)) {
    const p = parseAddr(k);
    if (p) {
      cols = Math.max(cols, p.c + 2);
      rows = Math.max(rows, p.r + 20);
    }
  }
  return { cols, rows };
}

/** Moves cells down/right (insert, delta 1) or up/left (remove, delta -1) from `at` on one axis.
 * Formulas keep pointing at the same cells, which move with them. */
export function shiftCells(
  cells: Record<string, Cell>,
  axis: "row" | "col",
  at: number,
  delta: 1 | -1,
): Record<string, Cell> {
  const move = (n: number) => (n >= at ? n + delta : n);
  const fix = (text: string) =>
    text.startsWith("=")
      ? text.replace(/(\$?)([A-Z]{1,3})(\$?)(\d+)/g, (_m, d1, col, d2, row) => {
          const p = parseAddr(`${col}${row}`)!;
          if (axis === "row" ? p.r === at && delta === -1 : p.c === at && delta === -1)
            return "#REF!";
          const c = axis === "col" ? move(p.c) : p.c;
          const r = axis === "row" ? move(p.r) : p.r;
          return `${d1}${colName(c)}${d2}${r + 1}`;
        })
      : text;
  const out: Record<string, Cell> = {};
  for (const [k, cell] of Object.entries(cells)) {
    const p = parseAddr(k)!;
    const here = axis === "row" ? p.r : p.c;
    if (delta === -1 && here === at) continue;
    const c = axis === "col" ? move(p.c) : p.c;
    const r = axis === "row" ? move(p.r) : p.r;
    out[addr(c, r)] = { ...cell, text: fix(cell.text) };
  }
  return out;
}

/** Tab- and line-separated text, as copied from a spreadsheet, to a grid of strings. */
export const parseTsv = (text: string): string[][] =>
  text
    .replace(/\r\n?/g, "\n")
    .replace(/\n$/, "")
    .split("\n")
    .map((line) => line.split("\t"));

export const toTsv = (rows: string[][]) => rows.map((r) => r.join("\t")).join("\n");
