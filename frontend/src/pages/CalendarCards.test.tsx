import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { makeLab, mockFetch, renderRoute, SESSION, signedIn } from "@/test/utils";

const L = "/api/labs/lab1";
const person = (id: string, name: string) => ({ id, display_name: name, email: `${id}@uni.edu` });
const me = person("u1", "Pat Example");
const lee = person("u2", "Lee Lead");
const meeting = {
  kind: "meeting",
  id: "m1",
  title: "Lab meeting",
  date: "2026-06-12",
  end_date: null,
  project_id: null,
  project_name: null,
  project_color: null,
  done: false,
  notes: "Bring the data",
  starts_at: "2026-06-12T10:00:00",
  ends_at: "2026-06-12T11:00:00",
  join_url: "https://meet.google.com/abc-defg-hij",
  video_provider: "google_meet",
  call_owner: "u2",
  attendees: ["u1", "u2"],
  guests: ["friend@gmail.com"],
  responses: { u2: "accepted" },
};
const google = {
  id: "g1",
  title: "Scheduling Team",
  date: "2026-06-12",
  end_date: null,
  starts_at: "2026-06-12T15:00:00",
  ends_at: "2026-06-12T16:00:00",
  join_url: "",
  url: "https://www.google.com/calendar/event?eid=g1",
  location: "Room 4",
  description: "",
  organizer: "boss@uni.edu",
  repeats: true,
  my_status: "needsAction",
  attendees: [
    { email: "boss@uni.edu", name: "The Boss", status: "accepted", organizer: true, self: false },
    { email: "pat@uni.edu", name: "", status: "needsAction", organizer: false, self: true },
    { email: "gone@gmail.com", name: "", status: "declined", organizer: false, self: false },
  ],
};
const RANGE = "from=2026-05-31&to=2026-07-04";
const world = (perms = ["view_lab"], extra: Record<string, unknown> = {}) => ({
  [SESSION]: signedIn,
  "GET /api/labs/": { body: [makeLab(perms)] },
  [`GET ${L}/`]: { body: makeLab(perms) },
  [`GET ${L}/projects/`]: { body: [] },
  [`GET ${L}/notifications/`]: { body: [] },
  "GET /api/me/": { body: me },
  [`GET ${L}/members/`]: {
    body: [
      { id: "a", user: me, role: "pi" },
      { id: "b", user: lee, role: "member" },
    ],
  },
  [`GET ${L}/calendar/google/`]: { body: { connected: true, show_google_events: true } },
  [`GET ${L}/calendar/?${RANGE}`]: { body: [meeting] },
  [`GET ${L}/calendar/google/events/?${RANGE}`]: { body: [google] },
  [`GET ${L}/calendar/video-options/`]: {
    body: { google_meet: true, zoom: false, google_meet_available: true, zoom_available: false },
  },
  ...extra,
});

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"], now: new Date(2026, 5, 10, 12) });
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("calendar hover cards", () => {
  it("shows a meeting's details, who is on it and how they answered, and takes your answer", async () => {
    const calls = mockFetch(
      world(["view_lab"], {
        [`PUT ${L}/calendar/meetings/m1/answer/`]: {
          body: { ...meeting, responses: { u1: "maybe", u2: "accepted" } },
        },
      }),
    );
    renderRoute("/labs/lab1/calendar");
    const entry = await screen.findByRole("button", { name: /Lab meeting/ });
    await userEvent.hover(entry);
    await waitFor(() => expect(screen.getAllByText("Bring the data").length).toBeGreaterThan(0), {
      timeout: 3000,
    });
    expect((await screen.findAllByText("Lee Lead")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("friend@gmail.com").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/invited by email/).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: /Join the call/ })[0]).toHaveAttribute(
      "href",
      "https://meet.google.com/abc-defg-hij",
    );
    await userEvent.click(screen.getAllByRole("button", { name: "Maybe" })[0]!);
    await waitFor(() =>
      expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ status: "maybe" }),
    );
  });

  it("shows a Google event's guests and answers an invitation", async () => {
    const calls = mockFetch(
      world(["view_lab"], {
        [`POST ${L}/calendar/google/events/g1/answer/`]: {
          body: { id: "g1", my_status: "accepted" },
        },
      }),
    );
    renderRoute("/labs/lab1/calendar");
    const entry = await screen.findByRole("link", { name: /Scheduling Team/ });
    await userEvent.hover(entry);
    await waitFor(() => expect(screen.getAllByText("The Boss").length).toBeGreaterThan(0), {
      timeout: 3000,
    });
    expect(screen.getAllByText("gone@gmail.com").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Room 4/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/repeats/).length).toBeGreaterThan(0);
    await userEvent.click(screen.getAllByRole("button", { name: "Accept" })[0]!);
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST")?.body).toEqual({ status: "accepted" }),
    );
  });
});

describe("inviting people by email", () => {
  it("asks for a Google Meet call's guests, checks the addresses, and sends them", async () => {
    const calls = mockFetch(
      world(["view_lab", "contribute_lab"], {
        [`POST ${L}/calendar/meetings/`]: { status: 201, body: { ...meeting, id: "m2" } },
      }),
    );
    renderRoute("/labs/lab1/calendar");
    await userEvent.click(await screen.findByRole("button", { name: "Add meeting" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).queryByLabelText(/Invite anyone with a Google account/)).toBeNull();
    await userEvent.type(within(dialog).getByLabelText("Title"), "Sync");
    await userEvent.click(within(dialog).getByLabelText("Make a Google Meet call"));
    const box = await within(dialog).findByLabelText(/Invite anyone with a Google account/);
    await userEvent.type(box, "friend@gmail.com, not-an-email");
    await userEvent.click(within(dialog).getByRole("button", { name: /Save/ }));
    expect(await within(dialog).findByText(/not-an-email/)).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST")).toBe(false);
    await userEvent.clear(box);
    await userEvent.type(box, "Friend@Gmail.com colleague@uni.edu");
    await userEvent.click(within(dialog).getByRole("button", { name: /Save/ }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    const body = calls.find((c) => c.method === "POST")!.body as Record<string, unknown>;
    expect(body.video).toBe("google_meet");
    expect(body.guests).toEqual(["Friend@Gmail.com", "colleague@uni.edu"]);
  });

  it("shows your own answer buttons inside a meeting you are on", async () => {
    mockFetch(world(["view_lab", "contribute_lab"]));
    renderRoute("/labs/lab1/calendar");
    await userEvent.click(await screen.findByRole("button", { name: /Lab meeting/ }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("button", { name: "Accept" })).toBeInTheDocument();
    expect(within(dialog).getByText(/1 accepted, 0 maybe, 0 declined of 3 invited/)).toBeVisible();
  });
});
