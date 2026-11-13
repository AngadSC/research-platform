import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useSyncTimeZone } from "@/hooks/preferences";

function Probe() {
  useSyncTimeZone();
  return null;
}

/** Answers GET /api/me/ with `me` and echoes a PATCH; returns the fetch mock. */
function serve(me: object) {
  const fetch = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) =>
    Response.json(init?.method === "PATCH" ? { ...me, ...JSON.parse(String(init.body)) } : me),
  );
  vi.stubGlobal("fetch", fetch);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <Probe />
    </QueryClientProvider>,
  );
  return fetch;
}
const patches = (fetch: ReturnType<typeof serve>) =>
  fetch.mock.calls.filter(([, init]) => init?.method === "PATCH");

describe("useSyncTimeZone", () => {
  afterEach(() => vi.restoreAllMocks());
  const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;

  it("saves the browser's zone when the account has another", async () => {
    const fetch = serve({ id: "u1", preferences: { time_zone: "Pacific/Chatham" } });
    await waitFor(() => expect(patches(fetch)).toHaveLength(1));
    expect(JSON.parse(String(patches(fetch)[0]![1]!.body))).toEqual({
      preferences: { time_zone: zone },
    });
  });

  it("does nothing when the zones match", async () => {
    const fetch = serve({ id: "u1", preferences: { time_zone: zone } });
    await waitFor(() => expect(fetch).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 50));
    expect(patches(fetch)).toHaveLength(0);
  });
});
