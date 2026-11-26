import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { makeLab, mockFetch, openSection, renderRoute, SESSION, signedIn } from "@/test/utils";

const pi = { id: "u1", email: "pi@example.test", display_name: "Pat", avatar_url: null };
const now = new Date().toISOString();
const alert = {
  id: "a1",
  kind: "high",
  value: -66,
  peak: -61,
  started_at: now,
  ended_at: null,
  acknowledged_by: null,
  acknowledged_at: null,
  note: "",
};
const sensor = {
  id: "s1",
  name: "-80 Freezer B",
  item: { id: "i1", name: "-80 °C freezer B" },
  unit: "c",
  unit_symbol: "°C",
  low_limit: -90,
  high_limit: -70,
  silent_after_minutes: 30,
  recipients: [],
  active: true,
  has_token: false,
  token_created_at: null,
  last_value: -61.04,
  last_at: now,
  status: "out_of_range",
  alert,
  series: [{ t: now, min: -80, max: -61, avg: -70 }],
  created_at: now,
};

const handlers = (perms: string[], extra = {}) => ({
  [SESSION]: signedIn,
  "GET /api/labs/": { body: [makeLab(perms)] },
  "GET /api/labs/lab1/": { body: makeLab(perms) },
  "GET /api/labs/lab1/projects/": { body: [] },
  "GET /api/labs/lab1/notifications/": { body: [] },
  "GET /api/labs/lab1/chat/unread/": { body: [] },
  "GET /api/labs/lab1/sensors/": { body: [sensor] },
  "GET /api/labs/lab1/sensors/s1/": { body: { ...sensor, history: [alert] } },
  ...extra,
});

describe("monitoring", () => {
  it("shows each sensor's reading, status and open alert, and acknowledges it", async () => {
    const calls = mockFetch(
      handlers(["view_lab", "manage_inventory"], {
        "POST /api/labs/lab1/sensors/alerts/a1/acknowledge/": {
          body: { ...alert, acknowledged_by: pi, acknowledged_at: now, note: "Door ajar" },
        },
      }),
    );
    renderRoute("/labs/lab1/monitoring");
    expect(await screen.findByRole("link", { name: "-80 Freezer B" })).toBeInTheDocument();
    expect(screen.getByText("-61 °C")).toBeInTheDocument();
    expect(screen.getByText("Out of range")).toBeInTheDocument();
    expect(screen.getByText("Above -70 °C, at worst -61 °C")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Last 24 hours/ })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Acknowledge" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByRole("textbox"), "Door ajar");
    await userEvent.click(within(dialog).getByRole("button", { name: "Acknowledge" }));
    await waitFor(() =>
      expect(calls.find((c) => c.path.endsWith("/acknowledge/"))?.body).toEqual({
        note: "Door ajar",
      }),
    );
  });

  it("offers a viewer no buttons", async () => {
    mockFetch(handlers(["view_lab"]));
    renderRoute("/labs/lab1/monitoring");
    await screen.findByRole("link", { name: "-80 Freezer B" });
    expect(screen.queryByRole("button", { name: "Acknowledge" })).not.toBeInTheDocument();
    expect(screen.getByText("Nobody has acknowledged it yet.")).toBeInTheDocument();
  });

  it("has one clear button when there are no sensors", async () => {
    mockFetch(
      handlers(["view_lab", "manage_inventory"], { "GET /api/labs/lab1/sensors/": { body: [] } }),
    );
    renderRoute("/labs/lab1/monitoring");
    expect(await screen.findByText("No sensors yet")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Add a sensor" })).toHaveLength(1);
  });

  it("shows the token once with the recipes filled in", async () => {
    const calls = mockFetch(
      handlers(["view_lab", "manage_inventory"], {
        "POST /api/labs/lab1/sensors/s1/token/": {
          status: 201,
          body: { token: "lbs_secret", token_created_at: now },
        },
      }),
    );
    renderRoute("/labs/lab1/monitoring/s1");
    expect(await screen.findByRole("heading", { name: "-80 Freezer B" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Last 7 days/ })).toBeInTheDocument();
    await openSection("Set up the sensor");
    expect(screen.getByText(/token=<your token>&value=\$\{ev.tC\}/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Make a token" }));
    expect(await screen.findByDisplayValue("lbs_secret")).toBeInTheDocument();
    expect(screen.getByText(/Bearer lbs_secret/, { selector: "code" })).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST" && c.path.endsWith("/token/"))).toBe(true);
  });
});
