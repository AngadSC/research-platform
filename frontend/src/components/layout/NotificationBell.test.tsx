import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { NotificationBell } from "@/components/layout/NotificationBell";
import { mockFetch, SESSION, signedIn } from "@/test/utils";

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

  it("lists chats with new messages and counts them on the bell", async () => {
    mockFetch({
      "GET /api/labs/lab1/notifications/": { body: [mention] },
      "GET /api/labs/lab1/chat/unread/": {
        body: [
          { project: null, count: 2 },
          { project: "p1", count: 1 },
        ],
      },
      "GET /api/labs/lab1/projects/": { body: [{ id: "p1", name: "Pilot Study" }] },
    });
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <NotificationBell labId="lab1" />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await userEvent.click(await screen.findByRole("button", { name: "Notifications, 4 unread" }));
    const chats = await screen.findByRole("list", { name: "New chat messages" });
    const lab = within(chats).getByRole("menuitem", { name: /Lab chat/ });
    expect(lab).toHaveAttribute("href", "/labs/lab1/chat");
    expect(lab).toHaveTextContent("2 new messages");
    const project = within(chats).getByRole("menuitem", { name: /Pilot Study/ });
    expect(project).toHaveAttribute("href", "/labs/lab1/projects/p1?chat=1");
    expect(project).toHaveTextContent("1 new message");
  });
  it("marks notifications and chats read together, even when only chats are unread", async () => {
    const calls = mockFetch({
      "GET /api/labs/lab1/notifications/": { body: [] },
      "GET /api/labs/lab1/chat/unread/": {
        body: [
          { project: null, count: 2 },
          { project: "p1", count: 1 },
        ],
      },
      "GET /api/labs/lab1/projects/": { body: [{ id: "p1", name: "Pilot Study" }] },
      [SESSION]: signedIn,
      "POST /api/labs/lab1/chat/messages/read/": { body: {} },
      "POST /api/labs/lab1/projects/p1/messages/read/": { body: {} },
    });
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <NotificationBell labId="lab1" />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await userEvent.click(await screen.findByRole("button", { name: "Notifications, 3 unread" }));
    const button = await screen.findByRole("button", { name: "Mark all as read" });
    expect(button).toBeEnabled();
    await userEvent.click(button);
    await waitFor(() =>
      expect(calls.filter((c) => c.method === "POST").map((c) => c.path)).toEqual([
        "/api/labs/lab1/chat/messages/read/",
        "/api/labs/lab1/projects/p1/messages/read/",
      ]),
    );
  });
});
