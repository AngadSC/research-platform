import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
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
}));
vi.mock("@/lib/drive", () => ({
  pickDriveFile: async () => picked,
  pickDriveFiles: async () => [picked],
}));
vi.mock("@/lib/integrations", () => ({ pickerReady: () => true }));

function setup(participant?: boolean) {
  const onPick = vi.fn<(f: PickedFile, participant: boolean) => Promise<unknown>>();
  onPick.mockResolvedValue({});
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <FromDriveButton labId="lab1" onPick={onPick} participant={participant} />
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

describe("linkStateLabel", () => {
  it("says a Drive file the app cannot see should be picked, not that it is gone", () => {
    expect(linkStateLabel("not_found")).toBe(
      "Pick this file with From Drive so labbenchos can check it",
    );
    expect(linkStateLabel("no_access")).toBe("no access");
  });
});
