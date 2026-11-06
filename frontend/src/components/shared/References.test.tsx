import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { ReferenceList, ReferencesEditor } from "@/components/shared/References";
import type { Reference } from "@/lib/api-types";
import { cleanReferences, doiHref, moveRow, validateReferences } from "@/lib/references";

describe("reference rules (D95)", () => {
  it("builds DOI links and refuses malformed DOIs", () => {
    expect(doiHref("10.1234/abc.5")).toBe("https://doi.org/10.1234/abc.5");
    expect(doiHref("11.1234/abc")).toBeNull();
    expect(doiHref("10.12/abc")).toBeNull();
    expect(doiHref("10.1234/a b")).toBeNull();
  });
  it("validates like the backend", () => {
    const e = validateReferences([
      { title: " ", url: "javascript:alert(1)", doi: "nope" },
      { title: "ok", url: "https://a.example", doi: "10.1234/x" },
      { title: "ok" },
    ]);
    expect(e[0]).toEqual({
      title: "Enter a title",
      url: expect.stringMatching(/http/),
      doi: expect.stringMatching(/10\.1234/),
    });
    expect(e[1]).toEqual({});
    expect(e[2]).toEqual({});
  });
  it("trims and moves rows", () => {
    expect(cleanReferences([{ title: " a ", url: " https://x.io " }])).toEqual([
      { title: "a", url: "https://x.io", doi: "" },
    ]);
    expect(moveRow([1, 2, 3], 0, 1)).toEqual([2, 1, 3]);
    expect(moveRow([1, 2, 3], 0, -1)).toEqual([1, 2, 3]);
  });
});

describe("ReferenceList", () => {
  it("links http(s) URLs and DOIs, and never a javascript: URL", () => {
    render(
      <ReferenceList
        items={[
          { title: "Good", url: "https://example.org/p", doi: "10.1234/abc" },
          { title: "Bad", url: "javascript:alert(1)", doi: "oops" },
        ]}
      />,
    );
    const a = screen.getByRole("link", { name: "Good" });
    expect(a).toHaveAttribute("href", "https://example.org/p");
    expect(a).toHaveAttribute("rel", "noopener noreferrer");
    expect(screen.getByRole("link", { name: "DOI 10.1234/abc" })).toHaveAttribute(
      "href",
      "https://doi.org/10.1234/abc",
    );
    expect(screen.getByText("Bad")).toBeInTheDocument();
    expect(screen.getAllByRole("link")).toHaveLength(2);
  });
});

function Harness({ start, onRows }: { start: Reference[]; onRows: (r: Reference[]) => void }) {
  const [rows, setRows] = useState(start);
  const change = (next: Reference[]) => {
    onRows(next);
    setRows(next);
  };
  return <ReferencesEditor rows={rows} errors={validateReferences(rows)} onChange={change} />;
}

describe("ReferencesEditor", () => {
  it("adds, edits, reorders and removes rows", async () => {
    const seen = { rows: [] as Reference[] };
    render(
      <Harness start={[{ title: "First" }, { title: "Second" }]} onRows={(r) => (seen.rows = r)} />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Add a reference" }));
    const third = screen.getByRole("group", { name: "Reference 3" });
    await userEvent.type(within(third).getByLabelText("Title"), "Third");
    await userEvent.type(within(third).getByLabelText("DOI"), "10.1234/z");
    expect(seen.rows.map((r) => r.title)).toEqual(["First", "Second", "Third"]);

    await userEvent.click(screen.getByRole("button", { name: "Move reference 3 up" }));
    expect(seen.rows.map((r) => r.title)).toEqual(["First", "Third", "Second"]);
    expect(screen.getByRole("button", { name: "Move reference 1 up" })).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: "Remove reference 1" }));
    expect(seen.rows.map((r) => r.title)).toEqual(["Third", "Second"]);
    expect(seen.rows[0]?.doi).toBe("10.1234/z");
  });

  it("shows row errors", () => {
    render(<Harness start={[{ title: "" }]} onRows={() => {}} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Enter a title");
  });
});
