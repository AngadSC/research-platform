import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { makeLab, mockFetch, renderRoute, SESSION, signedIn, signedOut } from "@/test/utils";

class FakeXHR {
  static sent: FormData[] = [];
  static url = "";
  upload: { onprogress?: unknown } = {};
  status = 201;
  responseText = JSON.stringify({ name: "read1.csv", size_bytes: 16 });
  onload?: () => void;
  open(_method: string, url: string) {
    FakeXHR.url = url;
  }
  setRequestHeader() {}
  send(f: FormData) {
    FakeXHR.sent.push(f);
    queueMicrotask(() => this.onload?.());
  }
}

beforeEach(() => {
  FakeXHR.sent = [];
  document.cookie = "csrftoken=t";
  vi.stubGlobal("XMLHttpRequest", FakeXHR);
});
afterEach(() => vi.unstubAllGlobals());

const csv = () => new File(["Well,OD"], "read1.csv", { type: "text/csv" });
const user = { id: "u1", email: "ada@example.test", display_name: "Ada" };
const reader = {
  id: "i1",
  name: "Plate reader",
  category: "equipment",
  location: "Bench 3",
  quantity: "1",
  unit: "",
  low_stock_at: null,
  low: false,
  weeks_left: null,
  owner: null,
  serial_number: "",
  purchase_date: null,
  due_date: null,
  status: "active",
  notes: "",
  instrument_software: "agilent_gen5",
  created_at: "2026-11-01T00:00:00Z",
  updated_at: "2026-11-01T00:00:00Z",
};
const project = {
  id: "p1",
  name: "Sialyltransferase",
  status: "active",
  my_permissions: ["view_project", "edit_content"],
};
const L = "/api/labs/lab1";
const lab = (extra: Record<string, unknown> = {}) => ({
  [SESSION]: signedIn,
  "GET /api/labs/": { body: [makeLab(["view_lab", "manage_inventory"])] },
  [`GET ${L}/`]: { body: makeLab(["view_lab", "manage_inventory"]) },
  [`GET ${L}/projects/`]: { body: [project] },
  [`GET ${L}/notifications/`]: { body: [] },
  [`GET ${L}/chat/unread/`]: { body: [] },
  [`GET ${L}/inventory/?category=equipment`]: { body: [reader] },
  "GET /api/instrument-software/": {
    body: [{ value: "agilent_gen5", label: "Agilent BioTek Gen5" }],
  },
  ...extra,
});

describe("public drop link", () => {
  it("shows only the names, asks the participant question, then sends with the token", async () => {
    mockFetch({
      [SESSION]: signedOut,
      "GET /api/instrument-drop/?token=tok": {
        body: { instrument: "Plate reader", project: "Sialyltransferase", max_bytes: 52428800 },
      },
    });
    renderRoute("/drop/tok");
    expect(await screen.findByText("Send files from Plate reader")).toBeInTheDocument();
    expect(screen.getByText(/Into the project Sialyltransferase/)).toBeInTheDocument();
    const u = userEvent.setup();
    expect(screen.getByRole("button", { name: "Choose files" })).toBeDisabled();
    await u.click(screen.getByRole("radio", { name: /no participant identifiers/i }));
    await u.upload(screen.getByLabelText("Choose files"), csv());
    await waitFor(() => expect(FakeXHR.sent).toHaveLength(1));
    const sent = FakeXHR.sent[0]!;
    expect(sent.get("token")).toBe("tok");
    expect(sent.get("acknowledged_notice")).toBe("true");
    expect(sent.get("contains_participant_data")).toBeNull();
    expect(FakeXHR.url).toBe("/api/instrument-drop/"); // the token stays out of the address
    expect(await screen.findByText("Sent")).toBeInTheDocument();
  });

  it("says why a link cannot be used", async () => {
    mockFetch({
      [SESSION]: signedOut,
      "GET /api/instrument-drop/?token=old": {
        status: 410,
        body: { detail: "This link has expired. Ask the person who gave it to you for a new one." },
      },
    });
    renderRoute("/drop/old");
    expect(await screen.findByText("This link can't be used")).toBeInTheDocument();
    expect(screen.getByText(/This link has expired/)).toBeInTheDocument();
  });
});

describe("instrument page", () => {
  it("lists the instrument's files with how reading went", async () => {
    mockFetch(
      lab({
        [`GET ${L}/instrument-files/?instrument=i1`]: {
          body: [
            {
              id: "f1",
              instrument: { id: "i1", name: "Plate reader" },
              project: { id: "p1", name: "Sialyltransferase" },
              attachment: "a1",
              filename: "elisa.xlsx",
              size_bytes: 10,
              contains_participant_data: false,
              software: "agilent_gen5",
              status: "ok",
              title: "Plate 1",
              kind: "plate",
              uploaded_via: "page",
              dropped_by: user,
              created_at: "2026-11-20T10:00:00Z",
            },
          ],
        },
      }),
    );
    renderRoute("/labs/lab1/instruments/i1");
    expect(await screen.findByText("elisa.xlsx")).toBeInTheDocument();
    expect(screen.getByText(/Sialyltransferase · Ada · Read: Plate 1/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Drop files/ })).toHaveAttribute(
      "href",
      "/labs/lab1/instruments/i1/drop",
    );
  });

  it("makes a drop link and shows it once", async () => {
    const calls = mockFetch(
      lab({
        [`GET ${L}/instruments/i1/drop-links/`]: { body: [] },
        [`POST ${L}/instruments/i1/drop-links/`]: {
          status: 201,
          body: {
            id: "l1",
            label: "Core PC",
            project: { id: "p1", name: "Sialyltransferase" },
            created_by: user,
            expires_at: null,
            expired: false,
            last_used_at: null,
            created_at: "2026-11-20T10:00:00Z",
            url: "https://labbenchos.test/drop/secret-token",
          },
        },
      }),
    );
    renderRoute("/labs/lab1/instruments/i1#links");
    const u = userEvent.setup();
    await u.selectOptions(await screen.findByLabelText("Project"), "p1");
    await u.type(screen.getByLabelText(/^Name/), "Core PC");
    await u.click(screen.getByRole("button", { name: "Make a drop link" }));
    expect(
      await screen.findByDisplayValue("https://labbenchos.test/drop/secret-token"),
    ).toBeVisible();
    const post = calls.find((c) => c.method === "POST")!;
    expect(post.body).toEqual({ project: "p1", label: "Core PC", expires_in_days: 30 });
  });
});
