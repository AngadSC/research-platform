import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DocsGrid, PreviewTile } from "@/components/documents/DocsGrid";

describe("document previews in the grid", () => {
  it("draws text, a spreadsheet corner and a slide", () => {
    const { container } = render(
      <>
        <PreviewTile preview={{ kind: "doc", text: "Hello lab" }} />
        <PreviewTile
          preview={{
            kind: "sheet",
            rows: [
              ["a", "b"],
              ["1", "2"],
            ],
          }}
        />
        <PreviewTile preview={{ kind: "slides", title: "Intro", text: "" }} />
      </>,
    );
    expect(screen.getByText("Hello lab")).toBeInTheDocument();
    expect(container.querySelectorAll("td")).toHaveLength(4);
    expect(screen.getByText("Intro")).toBeInTheDocument();
  });

  it("shows nothing for an empty document, so the icon is used", () => {
    const { container } = render(<PreviewTile preview={{ kind: "doc", text: "" }} />);
    expect(container).toBeEmptyDOMElement();
    render(
      <DocsGrid
        items={[{ id: "1", name: "Blank", icon: <svg data-testid="icon" />, onOpen: () => {} }]}
      />,
    );
    expect(screen.getByTestId("icon")).toBeInTheDocument();
  });
});
