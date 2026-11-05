import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { StaleDocumentBanner } from "@/components/documents/StaleDocumentBanner";
import { mockFetch } from "@/test/utils";

const row = (version: number) => ({
  id: "d1",
  project: "p1",
  title: "Notes",
  version,
  updated_by: { id: "u2", email: "grace@uni.edu", display_name: "Grace" },
  retain_until: null,
  retention_note: "",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-02T00:00:00Z",
});

function show(serverVersion: number, dirty = false) {
  mockFetch({ "GET /api/labs/lab1/projects/p1/documents/": { body: [row(serverVersion)] } });
  const onReload = vi.fn();
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <StaleDocumentBanner
        labId="lab1"
        projectId="p1"
        documentId="d1"
        localVersion={2}
        dirty={dirty}
        onReload={onReload}
      />
    </QueryClientProvider>,
  );
  return onReload;
}

describe("StaleDocumentBanner", () => {
  it("names who saved a newer version and reloads on one click", async () => {
    const onReload = show(3, true);
    expect(await screen.findByText("Grace")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("updated this document");
    expect(screen.getByRole("status")).toHaveTextContent("discards your unsaved changes");
    await userEvent.click(screen.getByRole("button", { name: "Reload" }));
    expect(onReload).toHaveBeenCalledTimes(1);
  });

  it("stays hidden while the server version is the one open here", async () => {
    show(2);
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("does not reload by itself", async () => {
    const onReload = show(5);
    await screen.findByRole("status");
    expect(onReload).not.toHaveBeenCalled();
  });
});
