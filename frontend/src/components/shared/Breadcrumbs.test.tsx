import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { Breadcrumbs } from "@/components/shared/Breadcrumbs";

describe("Breadcrumbs", () => {
  it("shows the root once when the page is named the same", () => {
    render(
      <MemoryRouter>
        <Breadcrumbs
          items={[{ label: "Home", to: "/" }, { label: "Labs", to: "/labs" }, { label: "Home" }]}
        />
      </MemoryRouter>,
    );
    expect(screen.getAllByText("Home")).toHaveLength(1);
    expect(screen.getByText("Labs")).toHaveAttribute("aria-current", "page");
  });
});
