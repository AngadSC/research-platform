import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LIVE_POLL_MS, markMine, useNewItemToasts } from "@/hooks/liveRefresh";
import { useAttachments } from "@/hooks/projects";
import { mockFetch } from "@/test/utils";

const toast = vi.hoisted(() => vi.fn());
vi.mock("sonner", () => ({ toast }));

const file = (id: string, extra = {}) => ({ id, original_filename: `${id}.csv`, ...extra });
const URL_ = "GET /api/labs/l1/projects/p1/attachments/";

function Probe({ poll }: { poll?: number }) {
  const { list } = useAttachments("l1", "p1", poll);
  useNewItemToasts("p1", list.data, "file", (f) => f.original_filename);
  return null;
}
const wrap = (ui: ReactNode) =>
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      {ui}
    </QueryClientProvider>,
  );
const tick = (ms: number) => act(() => vi.advanceTimersByTimeAsync(ms));

describe("live refresh", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    toast.mockClear();
  });
  afterEach(() => {
    vi.useRealTimers();
    Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true });
  });

  it("polls only while the tab is visible", async () => {
    const calls = mockFetch({ [URL_]: { body: [file("a")] } });
    wrap(<Probe poll={LIVE_POLL_MS} />);
    await tick(0);
    await tick(LIVE_POLL_MS);
    await tick(50);
    expect(calls.length).toBe(2);
    Object.defineProperty(document, "visibilityState", { value: "hidden", configurable: true });
    await tick(LIVE_POLL_MS * 3);
    expect(calls.length).toBe(2);
  });

  it("toasts a new file, and says Claude for link files", async () => {
    let rows = [file("a")];
    mockFetch({ [URL_]: () => ({ body: rows }) });
    wrap(<Probe poll={LIVE_POLL_MS} />);
    await tick(0);
    expect(toast).not.toHaveBeenCalled();
    rows = [...rows, file("b"), file("c", { source: "link" })];
    await tick(LIVE_POLL_MS);
    await tick(50);
    expect(toast).toHaveBeenCalledWith("New file: b.csv");
    expect(toast).toHaveBeenCalledWith("New from Claude: c.csv");
  });

  it("does not toast the person's own upload", async () => {
    let rows = [file("a")];
    mockFetch({ [URL_]: () => ({ body: rows }) });
    wrap(<Probe poll={LIVE_POLL_MS} />);
    await tick(0);
    markMine("b");
    rows = [...rows, file("b")];
    await tick(LIVE_POLL_MS);
    await tick(50);
    expect(toast).not.toHaveBeenCalled();
  });
});
