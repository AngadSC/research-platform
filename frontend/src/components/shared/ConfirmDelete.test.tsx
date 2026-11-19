import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ConfirmDelete } from "@/components/shared/ConfirmDelete";

describe("ConfirmDelete", () => {
  it("lists the first five titles and counts the rest", () => {
    const items = ["A", "B", "C", "D", "E", "F", "G"];
    render(
      <ConfirmDelete
        open
        name="7 documents"
        noun="documents"
        description="Gone."
        items={items}
        onConfirm={() => {}}
        onClose={() => {}}
      />,
    );
    expect(screen.getByText("E")).toBeInTheDocument();
    expect(screen.queryByText("F")).toBeNull();
    expect(screen.getByText("and 2 more")).toBeInTheDocument();
  });
});
