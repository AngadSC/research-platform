import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { InstrumentFilePreview, summaryToCsv } from ".";
import type { InstrumentSummary } from ".";

const plate: InstrumentSummary = {
  status: "ok",
  kind: "plate",
  title: "Phosphate release",
  measured_at: "2026-11-24T14:41:07+00:00",
  instrument_serial: "20010101",
  fields: [{ label: "Read mode", value: "Absorbance 620 nm" }],
  plates: [
    {
      name: "Plate 1 Absorbance 620 nm",
      rows: 8,
      cols: 12,
      unit: "OD",
      wells: { A1: 0.044, A2: 0.5, B1: 1.25, H12: 0.1234567 },
    },
    { name: "Plate 1 Absorbance 450 nm", rows: 2, cols: 3, wells: { A1: 9 } },
  ],
  tables: [{ name: "Readings", columns: ["Well", "OD"], rows: [["A1", 0.044]], truncated: false }],
};

describe("InstrumentFilePreview", () => {
  it("shows plate values as text, not only colour", () => {
    render(<InstrumentFilePreview summary={plate} />);
    const grid = screen.getByRole("table", {
      name: /Plate 1 Absorbance 620 nm, 8 rows by 12 columns/,
    });
    expect(within(grid).getByText("0.044")).toBeInTheDocument();
    expect(within(grid).getByText("1.25")).toBeInTheDocument();
    expect(within(grid).getByText("0.123457")).toBeInTheDocument(); // six significant digits
    expect(within(grid).getByTitle("B1: 1.25 OD")).toBeInTheDocument();
    expect(within(grid).getAllByLabelText("no reading")).toHaveLength(96 - 4);
    expect(within(grid).getAllByRole("columnheader")).toHaveLength(12);
    expect(
      screen.getByText(/4 of 96 wells read\. Lowest 0\.044 OD, highest 1\.25 OD/),
    ).toBeInTheDocument();
  });

  it("switches between plate readings", async () => {
    render(<InstrumentFilePreview summary={plate} />);
    await userEvent.selectOptions(screen.getByLabelText("Choose a plate reading"), "1");
    const grid = screen.getByRole("table", { name: /450 nm, 2 rows by 3 columns/ });
    expect(within(grid).getByText("9")).toBeInTheDocument();
  });

  it("lists the key fields, the date and the serial number", () => {
    render(<InstrumentFilePreview summary={plate} />);
    expect(screen.getByText("Read mode").nextSibling).toHaveTextContent("Absorbance 620 nm");
    expect(screen.getByText("Serial number").nextSibling).toHaveTextContent("20010101");
    expect(screen.getByText("Measured").nextSibling).toHaveTextContent(/2026/);
  });

  it("shows a table with its header and says when it was cut short", () => {
    const summary: InstrumentSummary = {
      status: "ok",
      kind: "table",
      tables: [
        {
          name: "Samples",
          columns: ["Sample", "ng/uL"],
          rows: [
            ["S1", 52.3],
            ["S2", null],
          ],
          truncated: true,
        },
      ],
    };
    render(<InstrumentFilePreview summary={summary} />);
    const table = screen.getByRole("table", { name: "Samples" });
    expect(
      within(table)
        .getAllByRole("columnheader")
        .map((h) => h.textContent),
    ).toEqual(["Sample", "ng/uL"]);
    expect(within(table).getByText("52.3")).toBeInTheDocument();
    expect(screen.getByText(/Showing the first 2 rows/)).toBeInTheDocument();
  });

  it("draws one chart per trace with a readable summary", () => {
    const summary: InstrumentSummary = {
      status: "ok",
      kind: "trace",
      traces: [
        {
          name: "UV",
          x_label: "Volume (mL)",
          y_label: "Absorbance (mAU)",
          x: [0, 50, 100],
          y: [5, 800, 10],
        },
        { name: "Cond", x_label: "Volume (mL)", y_label: "Conductivity", x: [0, 100], y: [1, 2] },
      ],
    };
    const { container } = render(<InstrumentFilePreview summary={summary} />);
    expect(
      screen.getByRole("img", {
        name: /UV absorbance\. Volume \(mL\) from 0 to 100; Absorbance \(mAU\) from 5 to 800/,
      }),
    ).toBeInTheDocument();
    expect(container.querySelectorAll("svg")).toHaveLength(2);
    expect(container.querySelectorAll("polyline")).toHaveLength(2);
    expect(screen.getByRole("heading", { name: "Conductivity" })).toBeInTheDocument();
  });

  it("hides fields that only hold a placeholder", () => {
    render(
      <InstrumentFilePreview
        summary={{
          status: "ok",
          kind: "table",
          fields: [
            { label: "Operator", value: "Default" },
            { label: "Readings", value: "8" },
          ],
        }}
      />,
    );
    expect(screen.queryByText("Operator")).not.toBeInTheDocument();
    expect(screen.getByText("Readings")).toBeInTheDocument();
  });

  it("overlays sequencing channels with a text legend", () => {
    const channel = (name: string) => ({
      name,
      x_label: "Scan",
      y_label: "Signal",
      x: [0, 1, 2],
      y: [0, 3, 1],
    });
    const summary: InstrumentSummary = {
      status: "ok",
      kind: "sequence_trace",
      traces: ["G", "A", "T", "C"].map(channel),
    };
    const { container } = render(<InstrumentFilePreview summary={summary} />);
    expect(container.querySelectorAll("svg")).toHaveLength(1);
    expect(container.querySelectorAll("polyline")).toHaveLength(4);
    for (const base of ["G", "A", "T", "C"]) expect(screen.getByText(base)).toBeInTheDocument();
  });

  it("shows an image thumbnail with alt text and its size", () => {
    const summary: InstrumentSummary = {
      status: "ok",
      kind: "image",
      title: "SDS-PAGE",
      image: { png_base64: "AAAA", width: 1100, height: 760, bit_depth: 16 },
    };
    render(<InstrumentFilePreview summary={summary} />);
    const img = screen.getByAltText("Preview of SDS-PAGE");
    expect(img).toHaveAttribute("src", "data:image/png;base64,AAAA");
    expect(screen.getByText(/1100 × 760 pixels, 16-bit original/)).toBeInTheDocument();
  });

  it("shows warnings in plain words", () => {
    render(
      <InstrumentFilePreview
        summary={{
          status: "ok",
          kind: "table",
          warnings: ["Showing the first 12 of 24 traces."],
          tables: [],
        }}
      />,
    );
    expect(screen.getByRole("list", { name: "Notes about this file" })).toHaveTextContent(
      "first 12 of 24 traces",
    );
  });

  it("explains a failure and says the file is kept", () => {
    render(
      <InstrumentFilePreview
        summary={{ status: "failed", error: "This FCS file is cut short." }}
      />,
    );
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("We couldn't read this file.");
    expect(alert).toHaveTextContent("This FCS file is cut short.");
    expect(alert).toHaveTextContent("still saved");
  });

  it("says plainly when a kind of file has no preview", () => {
    render(<InstrumentFilePreview summary={{ status: "unsupported" }} />);
    expect(screen.getByRole("status")).toHaveTextContent("No preview for this kind of file yet.");
  });

  it("hands the first table to the caller as CSV", async () => {
    const use = vi.fn();
    render(<InstrumentFilePreview summary={plate} onUseCsv={use} />);
    await userEvent.click(screen.getByRole("button", { name: "Use in statistics" }));
    expect(use).toHaveBeenCalledWith("Well,OD\nA1,0.044");
  });

  it("has no CSV button when there is nothing to export", () => {
    render(
      <InstrumentFilePreview
        summary={{
          status: "ok",
          kind: "image",
          image: { png_base64: "A", width: 1, height: 1 },
        }}
        onUseCsv={() => {}}
      />,
    );
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});

describe("summaryToCsv", () => {
  it("quotes cells that need it and blanks missing values", () => {
    const csv = summaryToCsv({
      status: "ok",
      tables: [
        {
          name: "T",
          columns: ["Sample", "Note"],
          rows: [
            ['He said "hi", twice', null],
            ["S2", 1.5],
          ],
        },
      ],
    });
    expect(csv).toBe('Sample,Note\n"He said ""hi"", twice",\nS2,1.5');
  });

  it("defuses text that looks like a formula but leaves numbers alone", () => {
    const csv = summaryToCsv({
      status: "ok",
      tables: [
        {
          name: "T",
          columns: ["Sample", "Value"],
          rows: [
            ["=SUM(A1)", -1.5],
            ["@x", "+5"],
            ["ok-1", 2],
          ],
        },
      ],
    });
    expect(csv).toBe("Sample,Value\n'=SUM(A1),-1.5\n'@x,'+5\nok-1,2");
  });

  it("writes a plate as one row per well, in plate order", () => {
    const csv = summaryToCsv({
      status: "ok",
      plates: [{ name: "P", rows: 8, cols: 12, unit: "OD", wells: { B1: 2, A10: 3, A2: 1 } }],
    });
    expect(csv).toBe("Well,Row,Column,Value (OD)\nA2,A,2,1\nA10,A,10,3\nB1,B,1,2");
  });

  it("gives null when there is no table or plate, or the file was not read", () => {
    expect(summaryToCsv({ status: "ok", kind: "trace", traces: [] })).toBeNull();
    expect(
      summaryToCsv({ status: "failed", tables: [{ name: "T", columns: ["a"], rows: [] }] }),
    ).toBeNull();
  });
});
