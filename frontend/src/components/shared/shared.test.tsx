import { useState, type ReactElement } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { CommandPalette } from "@/components/layout/CommandPalette";
import { DetailPanel } from "@/components/shared/DetailPanel";
import { EmptyState } from "@/components/shared/EmptyState";
import { FormField } from "@/components/shared/FormField";
import { Input } from "@/components/ui/input";
import { registerCommands } from "@/lib/commands";
import { mockFetch } from "@/test/utils";

describe("EmptyState", () => {
  it("renders its action", () => {
    render(
      <EmptyState
        title="No datasets"
        description="Add one."
        action={<button>Add dataset</button>}
      />,
    );
    expect(screen.getByRole("button", { name: "Add dataset" })).toBeInTheDocument();
  });
});

describe("FormField", () => {
  it("links label, hint and error to the input", () => {
    render(
      <FormField label="Title" hint="Keep it short" error="Title is required">
        {(p) => <Input {...p} />}
      </FormField>,
    );
    const input = screen.getByLabelText("Title");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAccessibleDescription("Title is required Keep it short");
  });
});

function Panel() {
  const [open, setOpen] = useState(true);
  return (
    <DetailPanel open={open} onOpenChange={setOpen} title="Dataset details">
      body
    </DetailPanel>
  );
}

describe("DetailPanel", () => {
  it("closes on Escape", async () => {
    render(<Panel />);
    expect(screen.getByRole("dialog", { name: "Dataset details" })).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

const wrap = (ui: ReactElement) =>
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      {ui}
    </QueryClientProvider>,
  );

describe("CommandPalette", () => {
  it("opens on Ctrl+K and lists registered commands", () => {
    const unregister = registerCommands([{ id: "t", label: "Test action", onSelect: () => {} }]);
    wrap(<CommandPalette />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    act(() => {
      fireEvent.keyDown(document, { key: "k", ctrlKey: true });
    });
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("Test action")).toBeInTheDocument();
    unregister();
  });
});

describe("CommandPalette shortcut", () => {
  it("leaves Ctrl+F to the browser", () => {
    wrap(<CommandPalette />);
    act(() => {
      fireEvent.keyDown(document, { key: "f", ctrlKey: true });
    });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

describe("CommandPalette search (D93)", () => {
  const hit = (type: string, id: string, title: string) => ({
    type,
    id,
    title,
    snippet: "",
    project: { id: "p1", name: "Gut study" },
    url: `/labs/lab1/x/${id}`,
  });
  const open = () =>
    act(() => {
      fireEvent.keyDown(document, { key: "k", ctrlKey: true });
    });
  it("debounces, groups hits by type, navigates by keyboard and cancels stale requests", async () => {
    const signals: (AbortSignal | undefined)[] = [];
    const urls: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        urls.push(String(input));
        signals.push(init?.signal ?? undefined);
        const q = new URL(String(input), "http://x").searchParams.get("q");
        if (q === "zeb") await new Promise((r) => setTimeout(r, 1000)); // slow, will be superseded
        const results =
          q === "zebra"
            ? [
                hit("project", "a", "Zebra study"),
                hit("task", "b", "Feed zebra"),
                hit("task", "c", "Clean tank"),
              ]
            : [];
        return new Response(JSON.stringify({ results }), { status: 200 });
      }),
    );
    const go = vi.fn();
    wrap(<CommandPalette labId="lab1" onGo={go} />);
    open();
    const input = screen.getByRole("combobox");
    await userEvent.type(input, "zeb");
    await waitFor(() => expect(urls).toHaveLength(1)); // one request, after the pause only
    await userEvent.type(input, "ra");
    await screen.findByText("Zebra study");
    expect(signals[0]?.aborted).toBe(true); // the "zeb" request was cancelled
    expect(urls.every((u) => u.startsWith("/api/labs/lab1/search/?q=zeb"))).toBe(true);
    expect(screen.getByText("Projects")).toBeInTheDocument();
    expect(screen.getByText("Tasks")).toBeInTheDocument();
    await userEvent.keyboard("{ArrowDown}{Enter}"); // the first hit is already selected
    expect(go).toHaveBeenCalledWith("/labs/lab1/x/b");
  });

  it("opens the first hit on Enter without an arrow press", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        const results = [hit("project", "a", "Zebra study"), hit("task", "b", "Feed zebra")];
        return new Response(JSON.stringify({ results }), { status: 200 });
      }),
    );
    const go = vi.fn();
    wrap(<CommandPalette labId="lab1" onGo={go} />);
    open();
    await userEvent.type(screen.getByRole("combobox"), "zebra");
    await screen.findByText("Zebra study");
    await userEvent.keyboard("{Enter}");
    expect(go).toHaveBeenCalledWith("/labs/lab1/x/a");
  });

  it("does not search below two characters and keeps static commands", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const unregister = registerCommands([{ id: "s", label: "Static thing", onSelect: () => {} }]);
    wrap(<CommandPalette labId="lab1" />);
    open();
    await userEvent.type(screen.getByRole("combobox"), "s");
    await new Promise((r) => setTimeout(r, 400));
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByText("Static thing")).toBeInTheDocument();
    unregister();
  });

  it("shows a quiet message when search fails", async () => {
    mockFetch({
      "GET /api/labs/lab1/search/?q=oops": { status: 429, body: { detail: "slow down" } },
    });
    wrap(<CommandPalette labId="lab1" />);
    open();
    await userEvent.type(screen.getByRole("combobox"), "oops");
    expect(await screen.findByRole("alert")).toHaveTextContent("Search is unavailable");
  });
});
