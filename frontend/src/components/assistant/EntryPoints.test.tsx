import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it } from "vitest";
import { CommandPalette } from "@/components/layout/CommandPalette";
import { LineageDetail } from "@/components/lineage/LineageDetail";
import { ASSISTANT_PREFILL } from "@/lib/assistant";
import { indexLineage } from "@/lib/lineage";
import { sample } from "@/lib/lineage.fixture";
import OverviewTab from "@/pages/project/OverviewTab";
import { mockFetch } from "@/test/utils";

const config = (can_use: boolean, has_key: boolean) => ({
  "GET /api/labs/lab1/assistant/config/": {
    body: {
      can_use,
      ai_policy: "assistant",
      providers: [{ provider: "anthropic", has_key, models: [] }],
    },
  },
});
const OK = config(true, true);
const NO_USE = config(false, true);
const NO_KEY = config(true, false);

const prefills: string[] = [];
const listen = (e: Event) => prefills.push((e as CustomEvent<string>).detail);
window.addEventListener(ASSISTANT_PREFILL, listen);
afterEach(() => {
  prefills.length = 0;
});

const wrap = (ui: React.ReactNode) =>
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );

const ix = indexLineage(sample);
const detail = (id: string) => (
  <LineageDetail
    ix={ix}
    node={ix.byId.get(id)!}
    labId="lab1"
    projectId="p1"
    onSelect={() => {}}
    onClose={() => {}}
  />
);
const project = {
  id: "p1",
  name: "Gut study",
  description: "",
  status: "active",
  my_permissions: [],
} as never;
const overview = <OverviewTab labId="lab1" projectId="p1" project={project} />;
const overviewMocks = {
  "GET /api/labs/lab1/projects/p1/deadlines/": { body: [] },
  "GET /api/labs/lab1/projects/p1/members/": { body: [] },
  "GET /api/labs/lab1/projects/p1/ethics-approvals/": { body: [] },
};

describe.each([
  ["no policy", NO_USE],
  ["no key", NO_KEY],
])("entry points are hidden with %s", (_n, cfg) => {
  it("lineage", async () => {
    mockFetch(cfg);
    wrap(detail("result:r1"));
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByRole("button", { name: /Explain how this was made/ })).toBeNull();
  });
  it("overview", async () => {
    mockFetch({ ...cfg, ...overviewMocks });
    wrap(overview);
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByRole("button", { name: "Catch me up" })).toBeNull();
  });
  it("palette", async () => {
    mockFetch({ ...cfg, "GET /api/labs/lab1/search/?q=zz": { body: { results: [] } } });
    wrap(<CommandPalette labId="lab1" />);
    act(() => void fireEvent.keyDown(document, { key: "k", ctrlKey: true }));
    await userEvent.type(screen.getByRole("combobox"), "zz");
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByText(/Ask the assistant/)).toBeNull();
  });
});

describe("entry points when the assistant is ready", () => {
  it("lineage explains a result and an analysis, not a dataset", async () => {
    mockFetch(OK);
    wrap(detail("result:r1"));
    await userEvent.click(await screen.findByRole("button", { name: /Explain how this was made/ }));
    expect(prefills[0]).toContain('item_type "result" and item_id "r1" in lab lab1');
  });
  it("lineage uses the analysis id for analyses", async () => {
    mockFetch(OK);
    wrap(detail("analysis:a1"));
    await userEvent.click(await screen.findByRole("button", { name: /Explain how this was made/ }));
    expect(prefills[0]).toContain('item_type "analysis" and item_id "a1"');
  });
  it("lineage hides it for a dataset", async () => {
    mockFetch(OK);
    wrap(detail("dataset:d1"));
    await screen.findByText("Open full record");
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByRole("button", { name: /Explain how this was made/ })).toBeNull();
  });
  it("overview catches the person up", async () => {
    mockFetch({ ...OK, ...overviewMocks });
    wrap(overview);
    await userEvent.click(await screen.findByRole("button", { name: "Catch me up" }));
    expect(prefills[0]).toContain("project_id p1 in lab lab1");
  });
  it("palette asks with Enter and closes", async () => {
    mockFetch({ ...OK, "GET /api/labs/lab1/search/?q=why%20low": { body: { results: [] } } });
    wrap(<CommandPalette labId="lab1" />);
    act(() => void fireEvent.keyDown(document, { key: "k", ctrlKey: true }));
    await userEvent.type(screen.getByRole("combobox"), "why low");
    const item = await screen.findByText(/Ask the assistant/);
    expect(item.textContent).toContain("why low");
    await userEvent.keyboard("{Enter}");
    expect(prefills).toEqual(["why low"]);
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
