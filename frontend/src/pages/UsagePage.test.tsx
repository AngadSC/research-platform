import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { makeLab, mockFetch, renderRoute, SESSION, signedIn } from "@/test/utils";

const L = "/api/labs/lab1";
const me = (site_staff: boolean) => ({
  id: "u1",
  email: "founder@uni.example",
  display_name: "Founder",
  preferences: {},
  site_staff,
});
const world = (staff: boolean) => ({
  [SESSION]: signedIn,
  "GET /api/me/": { body: me(staff) },
  "GET /api/labs/": { body: [makeLab(["view_lab"])] },
  [`GET ${L}/`]: { body: makeLab(["view_lab"]) },
  [`GET ${L}/projects/`]: { body: [] },
  [`GET ${L}/chat/unread/`]: { body: [] },
  [`GET ${L}/notifications/`]: { body: [] },
  [`GET ${L}/my-tasks/`]: { body: [] },
});

const usage = (days: number) => ({
  days,
  include_test: false,
  headline: {
    total_users: 34,
    new_users: 12,
    active_users: 20,
    labs_total: 9,
    labs_new: 3,
    projects_total: 15,
    dau: 4,
    wau: 11,
    mau: 20,
  },
  daily: Array.from({ length: days }, (_, i) => ({
    date: `2026-11-${String(i + 1).padStart(2, "0")}`,
    signups: i === 0 ? 2 : 0,
    sign_ins: 3,
    active_users: i % 5,
  })),
  funnel: [
    { key: "signed_up", label: "Signed up", count: 12, percent: 100 },
    { key: "in_lab", label: "Joined or created a lab", count: 9, percent: 75 },
    { key: "came_back", label: "Came back on a later day", count: 6, percent: 50 },
  ],
  features: [
    { feature: "Tasks", events: 140, users: 8 },
    { feature: "Lab chat messages", events: 0, users: 0 },
  ],
  integrations: [{ provider: "google_drive", connections: 2, users: 2 }],
  recent_signups: [
    {
      id: "p1",
      display_name: "Prof Example",
      email: "prof@uni.example",
      institution: "Example University",
      date_joined: "2026-11-20T10:00:00Z",
      labs: 1,
      last_active: null,
      events: 7,
    },
  ],
  retention: [
    { week_start: "2026-11-16", users: 5, weeks: [40] },
    { week_start: "2026-11-23", users: 7, weeks: [] },
  ],
});

describe("usage page", () => {
  it("shows staff the numbers and changes the window", async () => {
    const calls = mockFetch({
      ...world(true),
      "GET /api/usage/?days=30&include_test=0": { body: usage(30) },
      "GET /api/usage/?days=7&include_test=0": { body: usage(7) },
      "GET /api/usage/?days=7&include_test=1": { body: { ...usage(7), include_test: true } },
    });
    renderRoute("/usage");
    expect(await screen.findByRole("heading", { name: "Usage", level: 1 })).toBeInTheDocument();
    const summary = await screen.findByRole("region", { name: "Summary" });
    expect(within(summary).getByText("34")).toBeInTheDocument();
    expect(within(summary).getByText("New sign-ups (30 days)")).toBeInTheDocument();
    expect(screen.getByText("Joined or created a lab")).toBeInTheDocument();
    expect(screen.getByText("9 · 75%")).toBeInTheDocument();
    expect(screen.getByText("Tasks")).toBeInTheDocument();
    expect(screen.getByText("prof@uni.example")).toBeInTheDocument();
    expect(screen.getByText("Example University")).toBeInTheDocument();
    expect(screen.getByText("Never")).toBeInTheDocument();
    expect(screen.getByText("40%")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Active people per day" }).children).toHaveLength(30);

    await userEvent.click(screen.getByRole("button", { name: "7 days" }));
    expect(await screen.findByText("New sign-ups (7 days)")).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("checkbox", { name: "Include test and staff accounts" }),
    );
    await screen.findByText("New sign-ups (7 days)");
    expect(calls.some((c) => c.path === "/api/usage/?days=7&include_test=1")).toBe(true);

    await userEvent.click(screen.getByRole("button", { name: "Sign-ins" }));
    expect(screen.getByRole("list", { name: "Sign-ins per day" })).toBeInTheDocument();
  });

  it("puts Usage in the account menu for staff", async () => {
    mockFetch({ ...world(true), "GET /api/usage/?days=30&include_test=0": { body: usage(30) } });
    renderRoute("/settings");
    await userEvent.click(await screen.findByRole("button", { name: "Account menu" }));
    expect(await screen.findByRole("menuitem", { name: "Usage" })).toBeInTheDocument();
  });

  it("hides the link from everyone else", async () => {
    mockFetch(world(false));
    renderRoute("/settings");
    await userEvent.click(await screen.findByRole("button", { name: "Account menu" }));
    expect(await screen.findByRole("menuitem", { name: "Settings" })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "Usage" })).not.toBeInTheDocument();
  });

  it("shows everyone else Page not found, without asking the server", async () => {
    const calls = mockFetch(world(false));
    renderRoute("/usage");
    expect(await screen.findByText("Page not found")).toBeInTheDocument();
    expect(calls.some((c) => c.path.startsWith("/api/usage/"))).toBe(false);
  });
});
