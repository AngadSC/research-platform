import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { localDateISO } from "@/lib/format";
import { monthGrid } from "@/lib/calendar";
import { makeLab, mockFetch, renderRoute, SESSION, signedIn } from "@/test/utils";

const L = "/api/labs/lab1";
const base = (perms: string[], extra: Record<string, unknown> = {}) => ({
  [SESSION]: signedIn,
  "GET /api/labs/": { body: [makeLab(perms)] },
  [`GET ${L}/`]: { body: makeLab(perms) },
  [`GET ${L}/projects/`]: { body: [] },
  [`GET ${L}/chat/unread/`]: { body: [] },
  [`GET ${L}/notifications/`]: { body: [] },
  ...extra,
});
const message = {
  id: "m1",
  author: { id: "u2", email: "bob@uni.edu", display_name: "Bob" },
  body: "Lab meeting moved",
  created_at: "2026-11-09T10:00:00Z",
};

describe("lab chat", () => {
  it("shows messages from the lab chat endpoint and a badge in the sidebar", async () => {
    mockFetch(
      base(["view_lab"], {
        [`GET ${L}/chat/messages/`]: { body: [message] },
        [`POST ${L}/chat/messages/read/`]: { status: 204 },
        [`GET ${L}/chat/unread/`]: { body: [{ project: null, count: 3 }] },
      }),
    );
    renderRoute("/labs/lab1/chat");
    expect(await screen.findByText("Lab meeting moved")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Lab chat" })).toBeInTheDocument();
    const nav = screen.getAllByRole("navigation", { name: "Main" })[0]!;
    expect(await within(nav).findByRole("link", { name: /Lab chat/ })).toHaveTextContent("3");
  });
});

describe("calendar", () => {
  const now = new Date();
  const days = monthGrid(now.getFullYear(), now.getMonth());
  const range = `from=${localDateISO(days[0]!)}&to=${localDateISO(days[days.length - 1]!)}`;
  const today = localDateISO(now);
  const items = [
    {
      kind: "task",
      id: "t1",
      title: "Submit protocol",
      date: today,
      end_date: null,
      project_id: "p1",
      project_name: "Sleep",
      project_color: "teal",
      done: false,
      notes: "",
    },
    {
      kind: "event",
      id: "e1",
      title: "Retreat",
      date: today,
      end_date: null,
      project_id: null,
      project_name: null,
      project_color: null,
      done: false,
      notes: "Bring boots",
    },
  ];

  it("links a project's item to its source and opens a lab event read-only for viewers", async () => {
    mockFetch(base(["view_lab"], { [`GET ${L}/calendar/?${range}`]: { body: items } }));
    renderRoute("/labs/lab1/calendar");
    expect(await screen.findByRole("link", { name: /Submit protocol/ })).toHaveAttribute(
      "href",
      "/labs/lab1/projects/p1/tasks?task=t1",
    );
    expect(screen.queryByRole("button", { name: "Add event" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Retreat/ }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByLabelText("Notes")).toHaveValue("Bring boots");
    expect(within(dialog).getByLabelText("Notes")).toBeDisabled();
    expect(within(dialog).queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
  });

  it("asks for the next month when paging forward", async () => {
    const next = monthGrid(now.getFullYear(), now.getMonth() + 1);
    const nextRange = `from=${localDateISO(next[0]!)}&to=${localDateISO(next[next.length - 1]!)}`;
    const calls = mockFetch(
      base(["view_lab", "contribute_lab"], {
        [`GET ${L}/calendar/?${range}`]: { body: items },
        [`GET ${L}/calendar/?${nextRange}`]: { body: [] },
      }),
    );
    renderRoute("/labs/lab1/calendar");
    expect(await screen.findByRole("button", { name: "Add event" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Next month" }));
    await expect.poll(() => calls.some((c) => c.path === `${L}/calendar/?${nextRange}`)).toBe(true);
  });
});

describe("meetings and my work", () => {
  const now = new Date();
  const days = monthGrid(now.getFullYear(), now.getMonth());
  const range = `from=${localDateISO(days[0]!)}&to=${localDateISO(days[days.length - 1]!)}`;
  const meeting = {
    kind: "meeting",
    id: "m1",
    title: "Thesis check-in",
    date: localDateISO(now),
    end_date: null,
    project_id: null,
    project_name: null,
    project_color: null,
    done: false,
    notes: "",
    starts_at: now.toISOString(),
    ends_at: new Date(now.getTime() + 3600000).toISOString(),
    join_url: "https://zoom.us/j/99",
    attendees: ["u1"],
  };

  it("shows a Join link on a meeting, and My calendar asks for your own items", async () => {
    const calls = mockFetch(
      base(["view_lab"], {
        [`GET ${L}/calendar/?${range}`]: { body: [meeting] },
        [`GET ${L}/calendar/?${range}&mine=true`]: { body: [] },
        [`GET ${L}/members/`]: { body: [] },
      }),
    );
    renderRoute("/labs/lab1/calendar");
    await userEvent.click(await screen.findByRole("button", { name: /Thesis check-in/ }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("link", { name: "Join meeting" })).toHaveAttribute(
      "href",
      "https://zoom.us/j/99",
    );
    expect(within(dialog).queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    await userEvent.click(screen.getByRole("button", { name: "My calendar" }));
    await expect
      .poll(() => calls.some((c) => c.path === `${L}/calendar/?${range}&mine=true`))
      .toBe(true);
  });

  it("makes a secret link once and shows both calendar addresses", async () => {
    let active = false;
    mockFetch(
      base(["view_lab"], {
        [`GET ${L}/calendar/?${range}`]: { body: [] },
        [`GET ${L}/calendar/feed/`]: () => ({
          body: { active, updated_at: active ? "2026-11-09T10:00:00Z" : null },
        }),
        [`POST ${L}/calendar/feed/`]: () => {
          active = true;
          return {
            status: 201,
            body: { active, updated_at: "2026-11-09T10:00:00Z", token: "s3cret" },
          };
        },
      }),
    );
    renderRoute("/labs/lab1/calendar");
    await userEvent.click(await screen.findByRole("button", { name: "Subscribe" }));
    await userEvent.click(await screen.findByRole("button", { name: "Make a link" }));
    expect(await screen.findByLabelText("My calendar link")).toHaveValue(
      `${window.location.origin}/api/calendar.ics?token=s3cret&mine=1`,
    );
    expect(screen.getByLabelText("Lab calendar link")).toHaveValue(
      `${window.location.origin}/api/calendar.ics?token=s3cret`,
    );
    expect(await screen.findByRole("button", { name: "Turn off link" })).toBeInTheDocument();
  });

  it("My work lists my tasks, the deadlines of my projects and my trainings", async () => {
    const from = new Date();
    from.setDate(from.getDate() - 30);
    const to = new Date();
    to.setDate(to.getDate() + 61);
    mockFetch({
      ...base(["view_lab"]),
      [`GET ${L}/my-tasks/`]: {
        body: [
          {
            id: "t1",
            project: "p1",
            project_name: "Sleep",
            title: "Write ethics draft",
            due_date: null,
            status: "todo",
          },
        ],
      },
      [`GET ${L}/training/my/`]: {
        body: {
          requirements: [{ id: "r1", name: "Biosafety" }],
          members: [
            { user: { id: "u1" }, cells: { r1: { status: "expired", expires_on: "2026-01-01" } } },
          ],
          summary: {},
        },
      },
      [`GET ${L}/calendar/?from=${localDateISO(from)}&to=${localDateISO(to)}&mine=true`]: {
        body: [
          {
            ...meeting,
            kind: "deadline",
            id: "d1",
            title: "Submit report",
            project_id: "p1",
            project_name: "Sleep",
            starts_at: null,
            ends_at: null,
            join_url: "",
          },
          {
            ...meeting,
            kind: "deadline",
            id: "d2",
            title: "Finished one",
            done: true,
            starts_at: null,
            ends_at: null,
          },
          meeting,
        ],
      },
    });
    renderRoute("/labs/lab1/my-work");
    expect(await screen.findByRole("link", { name: "Write ethics draft" })).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "Submit report" })).toHaveAttribute(
      "href",
      "/labs/lab1/projects/p1/overview",
    );
    expect(screen.queryByText("Finished one")).not.toBeInTheDocument();
    expect(screen.queryByText("Thesis check-in")).not.toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "Biosafety" })).toBeInTheDocument();
    expect(screen.getByText("Expired", { selector: ".inline-flex, span" })).toBeInTheDocument();
  });
});

describe("orders", () => {
  const item = {
    id: "i1",
    name: "Tips",
    category: "consumable",
    location: "",
    quantity: "2.00",
    unit: "box",
    owner: null,
    serial_number: "",
    purchase_date: null,
    due_date: null,
    status: "active",
    notes: "",
  };
  const order = {
    id: "o1",
    item: "i1",
    item_name: "Tips",
    name: "Tips",
    vendor: "VWR",
    catalog_number: "CAT-9",
    url: "https://vendor.example/o1",
    quantity: "3.00",
    unit: "box",
    status: "ordered",
    notes: "",
    requested_by: { id: "u2", email: "bob@uni.edu", display_name: "Bob" },
    created_at: "2026-11-09T10:00:00Z",
    updated_at: "2026-11-09T10:00:00Z",
  };
  const inventory = (perms: string[], extra: Record<string, unknown> = {}) =>
    base(perms, {
      [`GET ${L}/members/`]: { body: [] },
      [`GET ${L}/inventory/?ordering=name`]: { body: [item] },
      [`GET ${L}/inventory/orders/`]: { body: [order] },
      ...extra,
    });

  it("opens the order link safely in a new tab and hides editing from viewers", async () => {
    mockFetch(inventory(["view_lab"]));
    renderRoute("/labs/lab1/inventory");
    const place = await screen.findByRole("link", { name: /Place order/ });
    expect(place).toHaveAttribute("href", "https://vendor.example/o1");
    expect(place).toHaveAttribute("target", "_blank");
    expect(place).toHaveAttribute("rel", "noopener noreferrer");
    expect(screen.queryByRole("button", { name: "New order" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reorder Tips" })).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "Status of Tips" })).not.toBeInTheDocument();
  });

  it("prefills Reorder from the item's last order and links it", async () => {
    const calls = mockFetch(
      inventory(["view_lab", "manage_inventory"], {
        [`POST ${L}/inventory/orders/`]: { body: order },
      }),
    );
    renderRoute("/labs/lab1/inventory");
    await userEvent.click(await screen.findByRole("button", { name: "Reorder Tips" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByLabelText("Name")).toHaveValue("Tips");
    expect(within(dialog).getByLabelText("Catalog number")).toHaveValue("CAT-9");
    const vwr = within(dialog).getByRole("link", { name: "VWR" });
    expect(vwr).toHaveAttribute("href", "https://www.vwr.com/ca/en/search/CAT-9");
    expect(vwr).toHaveAttribute("rel", "noopener noreferrer");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await expect
      .poll(() => calls.find((c) => c.method === "POST")?.body)
      .toMatchObject({ item: "i1", name: "Tips", catalog_number: "CAT-9", quantity: "3" });
  });

  it("confirms before marking received", async () => {
    const calls = mockFetch(
      inventory(["view_lab", "manage_inventory"], {
        [`PATCH ${L}/inventory/orders/o1/`]: { body: { ...order, status: "received" } },
      }),
    );
    renderRoute("/labs/lab1/inventory");
    const select = await screen.findByRole("combobox", { name: "Status of Tips" });
    await userEvent.selectOptions(select, "received");
    expect(calls.some((c) => c.method === "PATCH")).toBe(false);
    await userEvent.click(await screen.findByRole("button", { name: "Mark received" }));
    await expect
      .poll(() => calls.find((c) => c.method === "PATCH")?.body)
      .toEqual({ status: "received" });
  });
});
