/** What the backend's instrument_parsers package returns for one instrument file. */
export type InstrumentKind = "plate" | "table" | "trace" | "image" | "sequence_trace" | "flow";

export type InstrumentPlate = {
  name: string;
  rows: number;
  cols: number;
  unit?: string;
  /** well name ("A1") to value; wells that were not read are missing or null */
  wells: Record<string, number | null>;
};

export type InstrumentTable = {
  name: string;
  columns: string[];
  rows: (string | number | null)[][];
  truncated?: boolean;
};

export type InstrumentTrace = {
  name: string;
  x_label?: string;
  y_label?: string;
  x: number[];
  y: number[];
};

export type InstrumentSummary = {
  status: "ok" | "unsupported" | "failed";
  kind?: InstrumentKind;
  software?: string;
  title?: string;
  measured_at?: string | null;
  instrument_serial?: string | null;
  fields?: { label: string; value: string }[];
  plates?: InstrumentPlate[];
  tables?: InstrumentTable[];
  traces?: InstrumentTrace[];
  image?: { png_base64: string; width: number; height: number; bit_depth?: number };
  warnings?: string[];
  error?: string;
};
