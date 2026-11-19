import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { expect, it } from "vitest";
import { useDeleteDocument } from "@/hooks/documents";
import { mockFetch, SESSION, signedIn } from "@/test/utils";

it("deleting a document drops it from the cached recents", async () => {
  const d1 = { url: "/labs/l1/documents/d1", label: "Manual", kind: "document", at: "x" };
  const d2 = { url: "/labs/l1/documents/d2", label: "Other", kind: "document", at: "x" };
  mockFetch({
    [SESSION]: signedIn,
    "DELETE /api/labs/l1/documents/d1/": { status: 204 },
    "GET /api/me/": { body: { preferences: { recents: [d2] } } },
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const recents = [d1, d2];
  qc.setQueryData(["me"], { id: "u", preferences: { recents } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  const { result } = renderHook(() => useDeleteDocument("l1", ""), { wrapper });
  result.current.mutate("d1");
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  const me = qc.getQueryData<{ preferences: { recents: { url: string }[] } }>(["me"]);
  expect(me?.preferences.recents.map((r) => r.url)).toEqual(["/labs/l1/documents/d2"]);
});
