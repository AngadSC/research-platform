import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { NotebookView } from "@/components/shared/NotebookView";
import { mockFetch, SESSION, signedIn } from "@/test/utils";

const person = { id: "u1", email: "ann@uni.edu", display_name: "Ann" };
const entry = (over: object = {}) => ({
  id: "e1",
  project: null,
  author: person,
  title: "Western blot, day 1",
  entry_date: "2026-11-10",
  body: "Ran the gel at 120 V.",
  locked_at: null,
  locked_by: null,
  can_edit: true,
  created_at: "2026-11-10T10:00:00Z",
  updated_at: "2026-11-10T10:00:00Z",
  ...over,
});

function show(canWrite = true) {
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter>
        <NotebookView labId="lab1" canWrite={canWrite} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("NotebookView", () => {
  it("lists entries, hides edit controls on a locked one, and offers three exports", async () => {
    mockFetch({
      "GET /api/labs/lab1/notebook/": {
        body: [
          entry(),
          entry({
            id: "e2",
            title: "Plate read",
            locked_at: "2026-11-11T09:00:00Z",
            can_edit: false,
            locked_by: person,
          }),
        ],
      },
    });
    show();
    const list = await screen.findByRole("list", { name: "Entries" });
    expect(within(list).getByText("Western blot, day 1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit Western blot, day 1" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit Plate read" })).toBeNull();
    expect(within(list).getByText("Locked")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Export/ }));
    const links = await screen.findAllByRole("menuitem");
    expect(links.map((l) => l.getAttribute("href"))).toEqual([
      "/api/labs/lab1/notebook/export/?fmt=md",
      "/api/labs/lab1/notebook/export/?fmt=html",
      "/api/labs/lab1/notebook/export/?fmt=json",
    ]);
  });

  it("adds an entry", async () => {
    const calls = mockFetch({
      [SESSION]: signedIn,
      "GET /api/labs/lab1/notebook/": { body: [] },
      "POST /api/labs/lab1/notebook/": { status: 201, body: entry() },
    });
    show();
    await userEvent.click((await screen.findAllByRole("button", { name: /New entry/ }))[0]!);
    await userEvent.type(await screen.findByLabelText("Title"), "Gel 3");
    await userEvent.type(screen.getByLabelText("Entry"), "Ran at 100 V");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => {
      const post = calls.find((c) => c.method === "POST");
      expect(post?.body).toMatchObject({ title: "Gel 3", body: "Ran at 100 V" });
    });
  });

  it("shows no write buttons to a reader", async () => {
    mockFetch({ "GET /api/labs/lab1/notebook/": { body: [entry()] } });
    show(false);
    await screen.findByText("Western blot, day 1");
    expect(screen.queryByRole("button", { name: /New entry/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Edit/ })).toBeNull();
  });
});
