import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useSidebarOrder } from "@/hooks/preferences";

function Probe() {
  const o = useSidebarOrder();
  return (
    <>
      <p data-testid="main">{o.main.join(",")}</p>
      <button onClick={() => o.setMain(["chat", "dashboard"])}>move</button>
      <button onClick={o.reset}>reset</button>
    </>
  );
}

function serve(me: object) {
  const fetch = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) =>
    Response.json(init?.method === "PATCH" ? { ...me, ...JSON.parse(String(init.body)) } : me),
  );
  vi.stubGlobal("fetch", fetch);
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <Probe />
    </QueryClientProvider>,
  );
  return fetch;
}
const sent = (f: ReturnType<typeof serve>) =>
  f.mock.calls
    .filter(([, init]) => init?.method === "PATCH")
    .map(([, init]) => JSON.parse(String(init!.body)) as { preferences: Record<string, unknown> });

describe("useSidebarOrder", () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => vi.restoreAllMocks());

  it("reads the order from the account and saves a change to it", async () => {
    const fetch = serve({ id: "u1", preferences: { sidebar_main: ["papers", "dashboard"] } });
    expect(await screen.findByText("papers,dashboard")).toBeInTheDocument();
    await userEvent.click(screen.getByText("move"));
    await waitFor(() => expect(sent(fetch)).toHaveLength(1));
    expect(sent(fetch)[0]!.preferences).toEqual({ sidebar_main: ["chat", "dashboard"] });
    await userEvent.click(screen.getByText("reset"));
    await waitFor(() => expect(sent(fetch)).toHaveLength(2));
    expect(sent(fetch)[1]!.preferences).toEqual({ sidebar_main: [], sidebar_admin: [] });
  });

  it("carries an order made in this browser over to the account, once", async () => {
    localStorage.setItem("sidebar-order", JSON.stringify({ main: ["chat", "dashboard"] }));
    const fetch = serve({ id: "u1", preferences: {} });
    await waitFor(() => expect(sent(fetch)).toHaveLength(1));
    expect(sent(fetch)[0]!.preferences).toEqual({ sidebar_main: ["chat", "dashboard"] });
    expect(localStorage.getItem("sidebar-order")).toBeNull();
  });

  it("ignores a damaged saved order", async () => {
    localStorage.setItem("sidebar-order", "{nope");
    const fetch = serve({ id: "u1", preferences: {} });
    await waitFor(() => expect(fetch).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 30));
    expect(sent(fetch)).toHaveLength(0);
  });
});
