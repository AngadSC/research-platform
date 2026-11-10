import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { UploadDialog } from "./UploadDialog";

const file = (name: string) => new File(["x"], name, { type: "text/plain" });

describe("UploadDialog", () => {
  it("does not send a file twice when a retry follows a failure partway through", async () => {
    const send = vi
      .fn<(f: File) => Promise<unknown>>()
      .mockResolvedValueOnce({})
      .mockRejectedValueOnce(new Error("drop"))
      .mockResolvedValue({});
    const u = userEvent.setup();
    render(<UploadDialog open onOpenChange={() => {}} send={send} multiple />);
    await u.upload(screen.getByLabelText("Choose file"), [file("a"), file("b"), file("c")]);
    await u.click(screen.getByRole("checkbox"));
    await u.click(screen.getByRole("button", { name: "Upload" }));
    expect(await screen.findByText(/1 of 3 files uploaded/)).toBeInTheDocument();
    await u.click(screen.getByRole("button", { name: "Upload" }));
    await waitFor(() => expect(send).toHaveBeenCalledTimes(4));
    expect(send.mock.calls.map(([f]) => f.name)).toEqual(["a", "b", "b", "c"]);
  });
});
