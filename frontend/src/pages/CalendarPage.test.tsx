import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { makeLab, mockFetch, renderRoute, SESSION, signedIn } from "@/test/utils";

const item = (over: Record<string, unknown>) => ({
  kind: "event",
  id: "e0",
  title: "Event",
  date: "2026-06-12",
  end_date: null,
  project_id: null,
  project_name: null,
  project_color: null,
  done: false,
  notes: "",
  starts_at: null,
  ends_at: null,
  join_url: "",
  video_provider: "",
  call_owner: null,
  attendees: [],
  ...over,
});
const LONG = "[UX test] Recruit 12 participants for the pilot";
const ITEMS = [
  item({ id: "e2", title: "Later all-day", date: "2026-06-20" }),
  item({ id: "e1", title: LONG, date: "2026-06-12", project_name: "Pilot" }),
  item({
    id: "m1",
    kind: "meeting",
    title: "Lab meeting",
    date: "2026-06-12",
    starts_at: "2026-06-12T10:00:00",
  }),
];
const handlers = (perms: string[], items = ITEMS) => ({
  [SESSION]: signedIn,
  "GET /api/labs/": { body: [makeLab(perms)] },
  "GET /api/labs/lab1/": { body: makeLab(perms) },
  "GET /api/labs/lab1/projects/": { body: [] },
  "GET /api/labs/lab1/notifications/": { body: [] },
  "GET /api/labs/lab1/google/": { body: { connected: false, show_google_events: false } },
  "GET /api/labs/lab1/calendar/?from=2026-05-31&to=2026-07-04": { body: items },
  "GET /api/labs/lab1/calendar/?from=2026-06-10&to=2026-08-09": { body: items },
});

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"], now: new Date(2026, 5, 10, 12) });
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("Calendar page", () => {
  it("shows the full title on hover in the month grid", async () => {
    mockFetch(handlers(["view_lab"]));
    renderRoute("/labs/lab1/calendar");
    expect(await screen.findByTitle(`Lab event: Pilot: ${LONG}`)).toBeTruthy();
  });

  it("switches to the agenda, keeps it in the URL, and groups by day", async () => {
    mockFetch(handlers(["view_lab"]));
    const router = renderRoute("/labs/lab1/calendar");
    await screen.findByTitle(`Lab event: Pilot: ${LONG}`);
    await userEvent.click(screen.getByRole("button", { name: "Agenda" }));
    expect(router.state.location.search).toBe("?view=agenda");
    const days = await screen.findAllByRole("heading", { level: 3 });
    expect(days.map((h) => h.textContent)).toEqual(["Friday, June 12", "Saturday, June 20"]);
    const first = within(days[0]!.closest("section")!);
    const rows = first.getAllByRole("listitem").map((r) => r.textContent);
    expect(rows[0]).toContain("All day");
    expect(rows[0]).toContain(LONG);
    expect(rows[1]).toContain("Lab meeting");
    await userEvent.click(screen.getByRole("button", { name: "Month" }));
    expect(router.state.location.search).toBe("");
  });

  it("opens straight on the agenda and offers Add event when it is empty", async () => {
    mockFetch(handlers(["view_lab", "contribute_lab"], []));
    renderRoute("/labs/lab1/calendar?view=agenda");
    expect(await screen.findByText("Nothing coming up")).toBeTruthy();
    await waitFor(() =>
      expect(screen.getAllByRole("button", { name: "Add event" })).toHaveLength(2),
    );
  });
});
