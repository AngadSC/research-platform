import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/hooks/crumbs", () => ({
  useCurrentLabId: () => undefined,
  useCurrentProjectId: () => undefined,
}));
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MessageText } from "@/lib/markdown";

const wrap = (text: string, own = false) =>
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <MessageText text={text} ownLinksOnly={own} />
      </MemoryRouter>
    </QueryClientProvider>,
  );

describe("Google links in messages", () => {
  it("turns a Google Doc link on its own line into a card", () => {
    wrap("have a look\nhttps://docs.google.com/document/d/1AbCdEfGhIjKlMn/edit");
    expect(screen.getByRole("link", { name: "Google Doc" })).toHaveAttribute(
      "href",
      "https://docs.google.com/document/d/1AbCdEfGhIjKlMn/edit",
    );
    expect(screen.getByRole("link", { name: "Open Google Doc in Google" })).toBeInTheDocument();
  });
  it("leaves a link inside a sentence as a plain link, and never makes cards for the assistant", () => {
    wrap("see https://docs.google.com/document/d/1AbCdEfGhIjKlMn/edit please");
    expect(screen.queryByText("Opens in Google")).toBeNull();
    wrap("https://docs.google.com/document/d/1AbCdEfGhIjKlMn/edit", true);
    expect(screen.queryByText("Opens in Google")).toBeNull();
  });
});
