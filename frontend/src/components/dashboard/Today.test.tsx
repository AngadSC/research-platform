import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { localDateISO } from "@/lib/format";
import { addDays } from "@/lib/snooze";
import { makeLab, mockFetch, renderRoute, SESSION, signedIn } from "@/test/utils";

const today = localDateISO();
const t = (id: string, title: string, due: string | null, snoozed: string | null = null) => ({
  id,
  project: "p1",
  project_name: "Paper 2",
  project_color: "teal",
  title,
  due_date: due,
  snoozed_until: snoozed,
  status: "todo",
});
const recents = [
  {
    url: "/labs/lab1/projects/p1/documents/d1",
    label: "Methods draft",
    kind: "document",
    at: "2026-01-01T00:00:00Z",
  },
];
const handlers = (tasks: unknown[], extra: Record<string, unknown> = {}) => ({
  [SESSION]: signedIn,
  "GET /api/me/": {
    body: { id: "u1", email: "ada@uni.edu", display_name: "Ada Lee", preferences: { recents } },
  },
  "GET /api/labs/": { body: [makeLab(["view_lab"])] },
  "GET /api/labs/lab1/": { body: makeLab(["view_lab"]) },
  "GET /api/labs/lab1/projects/": { body: [] },
  "GET /api/labs/lab1/getting-started/": { status: 404, body: {} },
  "GET /api/labs/lab1/my-tasks/": { body: tasks },
  ...extra,
});

describe("Today", () => {
  it("shows overdue and due today, hides snoozed, and offers where you left off", async () => {
    mockFetch(
      handlers([
        t("a", "Late thing", addDays(today, -2)),
        t("b", "Due thing", today),
        t("c", "Snoozed thing", today, addDays(today, 3)),
        t("d", "Later thing", addDays(today, 5)),
      ]),
    );
    renderRoute("/labs/lab1/dashboard");
    expect(await screen.findByRole("region", { name: "Overdue" })).toHaveTextContent("Late thing");
    expect(screen.getByRole("region", { name: "Due today" })).toHaveTextContent("Due thing");
    expect(screen.queryByRole("region", { name: "Due today" })).not.toHaveTextContent(
      "Snoozed thing",
    );
    expect(screen.getByRole("link", { name: /Continue where you left off/ })).toHaveAttribute(
      "href",
      "/labs/lab1/projects/p1/documents/d1",
    );
  });

  it("does not continue into an archived project", async () => {
    mockFetch(
      handlers([], {
        "GET /api/labs/lab1/projects/": {
          body: [{ id: "p1", name: "Old", status: "archived", updated_at: "2026-01-01T00:00:00Z" }],
        },
      }),
    );
    renderRoute("/labs/lab1/dashboard");
    await screen.findByText("You are all caught up.");
    expect(screen.queryByRole("link", { name: /Continue where you left off/ })).toBeNull();
  });

  it("says all caught up when nothing is due", async () => {
    mockFetch(handlers([t("d", "Later thing", addDays(today, 5))]));
    renderRoute("/labs/lab1/dashboard");
    expect(await screen.findByText("You are all caught up.")).toBeInTheDocument();
  });

  it("checks a task off and snoozes one until Monday", async () => {
    const calls = mockFetch(
      handlers([t("a", "Late thing", addDays(today, -1)), t("b", "Due thing", today)], {
        "PATCH /api/labs/lab1/tasks/a/": { body: {} },
        "PATCH /api/labs/lab1/tasks/b/": { body: {} },
      }),
    );
    renderRoute("/labs/lab1/dashboard");
    await userEvent.click(await screen.findByRole("button", { name: 'Mark "Late thing" done' }));
    await waitFor(() => expect(calls.some((c) => c.path.endsWith("/tasks/a/"))).toBe(true));
    expect(calls.find((c) => c.path.endsWith("/tasks/a/"))!.body).toEqual({ status: "done" });
    await userEvent.click(screen.getByRole("button", { name: 'Snooze "Due thing"' }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Until Monday" }));
    await waitFor(() => expect(calls.some((c) => c.path.endsWith("/tasks/b/"))).toBe(true));
    expect(calls.find((c) => c.path.endsWith("/tasks/b/"))!.body).toMatchObject({
      snoozed_until: expect.stringMatching(/^\d{4}-\d{2}-\d{2}T/),
    });
  });

  it("snoozes for three hours with Later today, and lets you unsnooze from the list", async () => {
    const calls = mockFetch(
      handlers([t("a", "Due thing", today), t("s", "Resting thing", today, addDays(today, 3))], {
        "PATCH /api/labs/lab1/tasks/a/": { body: {} },
        "PATCH /api/labs/lab1/tasks/s/": { body: {} },
      }),
    );
    renderRoute("/labs/lab1/dashboard");
    await userEvent.click(await screen.findByRole("button", { name: 'Snooze "Due thing"' }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Later today" }));
    await waitFor(() => expect(calls.some((c) => c.path.endsWith("/tasks/a/"))).toBe(true));
    const sent = (
      calls.find((c) => c.path.endsWith("/tasks/a/"))!.body as { snoozed_until: string }
    ).snoozed_until;
    expect(new Date(sent).getTime() - Date.now()).toBeGreaterThan(2.9 * 3600_000);
    // the list shows it as snoozed and not overdue, with a way back
    await userEvent.click(await screen.findByRole("button", { name: 'Unsnooze "Resting thing"' }));
    await waitFor(() => expect(calls.some((c) => c.path.endsWith("/tasks/s/"))).toBe(true));
    expect(calls.find((c) => c.path.endsWith("/tasks/s/"))!.body).toEqual({ snoozed_until: null });
  });

  it("opens the morning digest in the app, with what is due and what is coming", async () => {
    mockFetch(
      handlers([
        t("a", "Late thing", addDays(today, -2)),
        t("b", "Due thing", today),
        t("c", "Next week thing", addDays(today, 4)),
        t("d", "Snoozed thing", today, addDays(today, 3)),
      ]),
    );
    renderRoute("/labs/lab1/dashboard");
    const card = await screen.findByRole("button", { name: /Morning digest/ });
    await waitFor(() => expect(card).toHaveTextContent("1 due today · 1 overdue"));
    await userEvent.click(card);
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("region", { name: "Overdue" })).toHaveTextContent("Late thing");
    expect(within(dialog).getByRole("region", { name: "Due today" })).toHaveTextContent(
      "Due thing",
    );
    expect(within(dialog).getByRole("region", { name: "Coming up this week" })).toHaveTextContent(
      "Next week thing",
    );
    expect(dialog).not.toHaveTextContent("Snoozed thing");
    expect(dialog).toHaveTextContent("1 snoozed task resting");
  });
  it("offers Undo after a task is marked done", async () => {
    const calls = mockFetch(
      handlers([t("a", "Late thing", addDays(today, -1))], {
        "PATCH /api/labs/lab1/tasks/a/": { body: {} },
      }),
    );
    renderRoute("/labs/lab1/dashboard");
    await userEvent.click(await screen.findByRole("button", { name: 'Mark "Late thing" done' }));
    await userEvent.click(await screen.findByRole("button", { name: "Undo" }));
    await waitFor(() =>
      expect(calls.filter((c) => c.path.endsWith("/tasks/a/")).map((c) => c.body)).toEqual([
        { status: "done" },
        { status: "todo" },
      ]),
    );
  });
});
