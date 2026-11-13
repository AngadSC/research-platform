import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CommandPalette } from "@/components/layout/CommandPalette";
import { registerCommands } from "@/lib/commands";
import { OPEN_SEARCH_EVENT } from "@/lib/constants";

const wrap = (ui: ReactElement) =>
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      {ui}
    </QueryClientProvider>,
  );

const hit = (type: string, id: string, title: string) => ({
  type,
  id,
  title,
  snippet: "",
  project: { id: "p1", name: "Gut study" },
  url: `/labs/lab1/x/${id}`,
});

function serve(results: ReturnType<typeof hit>[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) =>
      String(input).includes("/assistant/config/")
        ? new Response("{}", { status: 403 })
        : new Response(JSON.stringify({ results }), { status: 200 }),
    ),
  );
}

let unregister = () => {};
afterEach(() => unregister());

describe("CommandPalette", () => {
  it("shows an item once, as the search hit, and groups jumps under Go to", async () => {
    serve([
      hit("project", "p1", "Gut study"),
      hit("file", "f1", "Tester doc.docx"),
      hit("chat", "c1", "gut samples are ready"),
    ]);
    unregister = registerCommands([
      { id: "project:p1", label: "Go to project Gut study", group: "Projects", onSelect: () => {} },
      { id: "project:p2", label: "Go to project Gut flora", group: "Projects", onSelect: () => {} },
      { id: "nav:/home", label: "Go to Home", group: "Navigate", onSelect: () => {} },
    ]);
    wrap(<CommandPalette labId="lab1" />);
    act(() => {
      fireEvent.keyDown(document, { key: "k", ctrlKey: true });
    });
    await userEvent.type(screen.getByRole("combobox"), "gut");
    await screen.findByText("Tester doc.docx");
    expect(screen.getByText("Files")).toBeInTheDocument();
    expect(screen.getByText("Chat")).toBeInTheDocument();
    expect(screen.getAllByText("Projects")).toHaveLength(1); // the search group only
    expect(screen.queryByText("Go to project Gut study")).not.toBeInTheDocument();
    const goTo = screen.getByText("Go to").closest("[cmdk-group]") as HTMLElement;
    expect(within(goTo).getByText("Go to project Gut flora")).toBeInTheDocument();
  });

  it("gives focus back to what opened it", async () => {
    serve([]);
    const button = document.createElement("button");
    button.textContent = "Search";
    button.onclick = () => window.dispatchEvent(new Event(OPEN_SEARCH_EVENT));
    document.body.appendChild(button);
    wrap(<CommandPalette labId="lab1" />);
    await userEvent.click(button);
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("combobox")).toHaveFocus());
    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(button).toHaveFocus();
    button.remove();
  });
});
