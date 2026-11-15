/**
 * In-browser statistics: the contract between the engine (Pyodide in a web worker, which runs
 * the maths on the person's own computer) and the Analyse screens. The data never leaves the
 * browser to be analysed; only what the person chooses to save goes to the project or Drive.
 */

/** What a test asks for. The screens draw one picker per param from this. */
export type ParamKind =
  | "numeric" // one numeric column
  | "numerics" // one or more numeric columns
  | "category" // one column treated as groups (any column; the engine uses its distinct values)
  | "columns" // one or more columns of any kind
  | "number" // a typed number
  | "choice"; // one of `options`

export interface ParamSpec {
  key: string;
  label: string;
  kind: ParamKind;
  optional?: boolean;
  /** For "numerics" and "columns": the fewest columns that make sense. */
  min?: number;
  /** For "choice". */
  options?: { value: string; label: string }[];
  default?: string | number;
  help?: string;
}

export type TestId =
  | "describe"
  | "frequencies"
  | "normality"
  | "t_one_sample"
  | "t_independent"
  | "t_paired"
  | "mann_whitney"
  | "wilcoxon"
  | "anova_oneway"
  | "anova_twoway"
  | "kruskal"
  | "chi_square"
  | "correlation"
  | "linear_regression"
  | "logistic_regression";

export interface TestSpec {
  id: TestId;
  label: string;
  group: "Describe" | "Compare groups" | "Relationships";
  /** One plain sentence: when to use it. */
  help: string;
  params: ParamSpec[];
}

const OUTCOME: ParamSpec = { key: "outcome", label: "Outcome (numbers)", kind: "numeric" };
const GROUP: ParamSpec = { key: "group", label: "Groups", kind: "category" };
const BEFORE: ParamSpec = { key: "before", label: "First measurement", kind: "numeric" };
const AFTER: ParamSpec = { key: "after", label: "Second measurement", kind: "numeric" };

/** Every test the engine runs, in the order the screens list them. */
export const TESTS: TestSpec[] = [
  {
    id: "describe",
    label: "Summary statistics",
    group: "Describe",
    help: "Count, mean, SD, median, range and missing values, optionally split by group.",
    params: [
      { key: "columns", label: "Columns", kind: "numerics", min: 1 },
      { ...GROUP, label: "Split by", optional: true },
    ],
  },
  {
    id: "frequencies",
    label: "Counts and percentages",
    group: "Describe",
    help: "How often each value appears. Pick two columns for a cross-table.",
    params: [{ key: "columns", label: "Columns", kind: "columns", min: 1 }],
  },
  {
    id: "normality",
    label: "Check normality",
    group: "Describe",
    help: "Shapiro-Wilk test, skew and kurtosis: whether the numbers look normally distributed.",
    params: [
      { key: "column", label: "Column", kind: "numeric" },
      { ...GROUP, label: "Split by", optional: true },
    ],
  },
  {
    id: "t_one_sample",
    label: "One-sample t-test",
    group: "Compare groups",
    help: "Is the mean different from a set value?",
    params: [
      { key: "column", label: "Column", kind: "numeric" },
      { key: "mu", label: "Compare with", kind: "number", default: 0 },
    ],
  },
  {
    id: "t_independent",
    label: "Independent t-test",
    group: "Compare groups",
    help: "Do two separate groups differ on average?",
    params: [
      OUTCOME,
      { ...GROUP, help: "Exactly two groups." },
      {
        key: "variant",
        label: "Version",
        kind: "choice",
        default: "welch",
        options: [
          { value: "welch", label: "Welch (does not assume equal variances)" },
          { value: "student", label: "Student (assumes equal variances)" },
        ],
      },
    ],
  },
  {
    id: "t_paired",
    label: "Paired t-test",
    group: "Compare groups",
    help: "Did the same people change between two measurements?",
    params: [BEFORE, AFTER],
  },
  {
    id: "mann_whitney",
    label: "Mann-Whitney U",
    group: "Compare groups",
    help: "Two separate groups, without assuming normal data.",
    params: [OUTCOME, { ...GROUP, help: "Exactly two groups." }],
  },
  {
    id: "wilcoxon",
    label: "Wilcoxon signed-rank",
    group: "Compare groups",
    help: "Two measurements of the same people, without assuming normal data.",
    params: [BEFORE, AFTER],
  },
  {
    id: "anova_oneway",
    label: "One-way ANOVA",
    group: "Compare groups",
    help: "Do three or more groups differ on average? Includes Tukey post-hoc comparisons.",
    params: [OUTCOME, GROUP],
  },
  {
    id: "anova_twoway",
    label: "Two-way ANOVA",
    group: "Compare groups",
    help: "The effect of two grouping factors and their interaction.",
    params: [
      OUTCOME,
      { key: "factor_a", label: "First factor", kind: "category" },
      { key: "factor_b", label: "Second factor", kind: "category" },
    ],
  },
  {
    id: "kruskal",
    label: "Kruskal-Wallis",
    group: "Compare groups",
    help: "Three or more groups, without assuming normal data.",
    params: [OUTCOME, GROUP],
  },
  {
    id: "chi_square",
    label: "Chi-square test",
    group: "Relationships",
    help: "Are two categories related? Uses Fisher's exact test for a 2x2 table.",
    params: [
      { key: "rows", label: "First category", kind: "category" },
      { key: "cols", label: "Second category", kind: "category" },
    ],
  },
  {
    id: "correlation",
    label: "Correlation",
    group: "Relationships",
    help: "How strongly numeric columns move together.",
    params: [
      { key: "columns", label: "Columns", kind: "numerics", min: 2 },
      {
        key: "method",
        label: "Method",
        kind: "choice",
        default: "pearson",
        options: [
          { value: "pearson", label: "Pearson" },
          { value: "spearman", label: "Spearman (ranks)" },
          { value: "kendall", label: "Kendall's tau" },
        ],
      },
    ],
  },
  {
    id: "linear_regression",
    label: "Linear regression",
    group: "Relationships",
    help: "Predict a numeric outcome from one or more columns.",
    params: [OUTCOME, { key: "predictors", label: "Predictors", kind: "columns", min: 1 }],
  },
  {
    id: "logistic_regression",
    label: "Logistic regression",
    group: "Relationships",
    help: "Predict a yes/no outcome from one or more columns.",
    params: [
      { key: "outcome", label: "Outcome (two values)", kind: "category" },
      { key: "predictors", label: "Predictors", kind: "columns", min: 1 },
    ],
  },
];

/** The file the engine reads. CSV, TSV, TXT and XLSX. */
export interface StatsFile {
  name: string;
  bytes: ArrayBuffer;
  /** For a workbook: which sheet. The first when left out. */
  sheet?: string;
}

export interface ColumnInfo {
  name: string;
  kind: "numeric" | "categorical" | "text";
  missing: number;
  distinct: number;
  /** Up to 5 example values. */
  sample: (string | number | null)[];
}

/**
 * How to read a messy file. Each `DataIssue.fix` is a complete set of these, so the screens pass
 * one back to `load` as it is. The engine checks every value against a strict list.
 */
export interface LoadOptions {
  /** The row with the column names (0 is the first); rows above it are left out. Worked out when left out. */
  header?: number;
  /** Rows right under the column names to leave out (Qualtrics' question text and import codes). Worked out when left out. */
  skip?: number;
  /** "," reads 3,5 as 3.5 (text files only). */
  decimal?: "." | ",";
  /** "." reads 1.234,5 as 1234.5, with a decimal comma. */
  thousands?: ".";
  /** Values to treat as missing, by column, such as 999. */
  missing?: Record<string, (number | string)[]>;
  /** A unit to remove from every value, by column, such as "ms" in "12 ms". */
  units?: Record<string, string>;
}

/** Something in the file that could give wrong numbers, in plain words, with a fix where there is one. */
export interface DataIssue {
  id: string;
  message: string;
  /** The button text for `fix`, e.g. "Treat 999 as missing"; "Undo" for an applied fix. */
  action?: string;
  /** Load the file again with these options to apply the fix (or, when applied, to undo it). */
  fix?: LoadOptions;
  /** The fix is in effect, chosen or applied automatically. */
  applied?: boolean;
}

/** What `load` found in the file. */
export interface DataShape {
  fileName: string;
  sheets: string[];
  sheet: string | null;
  rows: number;
  columns: ColumnInfo[];
  /** Problems found on reading, most important first; empty for a clean file. */
  issues: DataIssue[];
}

/** Param values by `ParamSpec.key`: a column name, a list of names, a number or a choice. */
export type ParamValues = Record<string, string | string[] | number | undefined>;

export interface StatsRequest {
  test: TestId;
  params: ParamValues;
}

export interface StatsTable {
  title: string;
  columns: string[];
  rows: (string | number | null)[][];
  note?: string;
}

/** Chart data, drawn by the screens. Raw values are capped by the engine (at most 5,000). */
export type StatsChart =
  | {
      kind: "histogram";
      title: string;
      xLabel: string;
      groups: { name: string; values: number[] }[];
    }
  | { kind: "box"; title: string; yLabel: string; groups: { name: string; values: number[] }[] }
  | {
      kind: "scatter";
      title: string;
      xLabel: string;
      yLabel: string;
      points: [number, number][];
      line?: { slope: number; intercept: number };
    }
  | {
      kind: "bar";
      title: string;
      yLabel: string;
      bars: { name: string; value: number; low?: number; high?: number }[];
    };

export interface StatsResult {
  test: TestId;
  title: string;
  /** Plain-English result with the APA-style numbers, e.g. "t(38.2) = 2.31, p = .026, d = 0.71". */
  summary: string;
  tables: StatsTable[];
  charts: StatsChart[];
  /** Assumption problems, dropped rows and the like, in plain words. */
  warnings: string[];
  /** Rows actually used. */
  n: number;
  /** A standalone Python script that reproduces this result from the file. */
  code: string;
  /** The result as an Excel workbook: a Summary sheet then one sheet per table. */
  xlsx: Uint8Array;
}

export type EngineState =
  | { state: "idle" }
  | { state: "loading"; message: string } // e.g. "Getting the statistics tools ready (first time only)"
  | { state: "ready" }
  | { state: "running"; message: string }
  | { state: "error"; message: string };

/** The engine. Errors reject with an Error whose message is plain English and safe to show. */
export interface StatsEngine {
  /** Start loading Python and pandas in the background; safe to call more than once. */
  warmUp(): void;
  subscribe(listener: (s: EngineState) => void): () => void;
  /** Read a file into the engine, replacing the last one (which stays loaded if this fails). */
  load(file: StatsFile, options?: LoadOptions): Promise<DataShape>;
  /** Start fetching the packages a test needs in the background, so its first run is quicker. */
  prepare(test: TestId): void;
  /** Run a test on the loaded file. */
  run(req: StatsRequest): Promise<StatsResult>;
}
