import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { NotificationBell } from "@/components/layout/NotificationBell";
import { mockFetch } from "@/test/utils";

const mention = {
  id: "n1",
  kind: "mention",
  title: "Ann mentioned you in the lab chat",
  body: "bold gone cc @Ben",
  target_type: "",
  target_id: null,
  url: "/labs/lab1/chat",
  read_at: null,
  created_at: "2026-11-12T10:00:00Z",
};

describe("NotificationBell", () => {
  it("links every notification to what it is about and shows its text", async () => {
    mockFetch({ "GET /api/labs/lab1/notifications/": { body: [mention] } });
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <NotificationBell labId="lab1" />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await userEvent.click(await screen.findByRole("button", { name: "Notifications, 1 unread" }));
    const menu = await screen.findByRole("menu");
    const link = within(menu).getByRole("menuitem", { name: /Ann mentioned you/ });
    expect(link).toHaveAttribute("href", "/labs/lab1/chat");
    expect(within(link).getByText("bold gone cc @Ben")).toBeInTheDocument();
  });
});
