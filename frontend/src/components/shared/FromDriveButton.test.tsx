import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { openGooglePanel } from "@/lib/googlePanel";
import { linkStateLabel } from "@/lib/participants";
import type { PickedFile } from "@/lib/drive";
import { FromDriveButton } from "./FromDriveButton";

const picked = { id: "f1", name: "Interviews.xlsx", url: "https://docs.google.com/x" };

vi.mock("@/hooks/integrations", () => ({
  useProviders: () => ({
    data: [
      {
        name: "google_drive",
        configured: true,
        public_config: { api_key: "k", app_id: "1" },
        account: { status: "active" },
      },
    ],
  }),
  fetchPickerToken: async () => ({ access_token: "t" }),
  createGoogleDoc: async () => ({ id: "newDoc12345", name: "Untitled document" }),
}));
vi.mock("@/lib/googlePanel", () => ({ openGooglePanel: vi.fn() }));
vi.mock("@/lib/drive", () => ({
  pickDriveFile: async () => picked,
  pickDriveFiles: async () => [picked],
}));
vi.mock("@/lib/integrations", () => ({ pickerReady: () => true }));

function setup(participant?: boolean, newDoc = false) {
  const onPick = vi.fn<(f: PickedFile, participant: boolean) => Promise<unknown>>();
  onPick.mockResolvedValue({});
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <FromDriveButton labId="lab1" onPick={onPick} participant={participant} newDoc={newDoc} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { onPick, u: userEvent.setup() };
}

describe("FromDriveButton participant question", () => {
  it("asks, as an upload does, and passes the answer on", async () => {
    const { onPick, u } = setup(false);
    await u.click(screen.getByRole("button", { name: /From Drive/ }));
    const link = await screen.findByRole("button", { name: "Link" });
    expect(link).toBeDisabled();
    expect(onPick).not.toHaveBeenCalled();
    await u.click(screen.getByLabelText(/identifies participants/));
    expect(link).toBeDisabled(); // the ethics confirmation comes first
    await u.click(screen.getByLabelText(/ethics approval allows/));
    await u.click(link);
    await waitFor(() => expect(onPick).toHaveBeenCalledWith(picked, true));
  });

  it("links a file with no identifiers unmarked", async () => {
    const { onPick, u } = setup(false);
    await u.click(screen.getByRole("button", { name: /From Drive/ }));
    await u.click(await screen.findByLabelText(/no participant identifiers/));
    await u.click(screen.getByRole("button", { name: "Link" }));
    await waitFor(() => expect(onPick).toHaveBeenCalledWith(picked, false));
  });

  it("does not ask where the answer is not stored", async () => {
    const { onPick, u } = setup();
    await u.click(screen.getByRole("button", { name: /From Drive/ }));
    await waitFor(() => expect(onPick).toHaveBeenCalledWith(picked, false));
    expect(screen.queryByRole("button", { name: "Link" })).toBeNull();
  });
});

describe("New Google Doc", () => {
  it("is only there when asked for", () => {
    setup();
    expect(screen.queryByRole("button", { name: /New Google Doc/ })).toBeNull();
  });

  it("makes a Doc, links it like a picked file, and opens it in the panel", async () => {
    const { onPick, u } = setup(false, true);
    await u.click(screen.getByRole("button", { name: /New Google Doc/ }));
    const url = "https://docs.google.com/document/d/newDoc12345/edit";
    await waitFor(() =>
      expect(onPick).toHaveBeenCalledWith(
        { id: "newDoc12345", name: "Untitled document", url },
        false, // an empty Doc identifies no one, and there is no participant question to ask
      ),
    );
    await waitFor(() =>
      expect(openGooglePanel).toHaveBeenCalledWith(
        expect.objectContaining({ src: url, label: "Google Docs" }),
      ),
    );
  });
});

describe("linkStateLabel", () => {
  it("says a Drive file the app cannot see should be picked, not that it is gone", () => {
    expect(linkStateLabel("not_found")).toBe(
      "Pick this file with From Drive so labbenchos can check it",
    );
    expect(linkStateLabel("no_access")).toBe("no access");
  });
});
