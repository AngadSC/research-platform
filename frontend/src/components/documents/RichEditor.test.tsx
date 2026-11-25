import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import RichEditor from "@/components/documents/RichEditor";

describe("RichEditor toolbar", () => {
  it("mounts with the text toolbar and unmounts without errors", () => {
    const err = vi.spyOn(console, "error").mockImplementation(() => {});
    const { unmount } = render(
      <RichEditor initialContent={[]} editable label="Document content" />,
    );
    expect(screen.getByRole("toolbar", { name: "Text formatting" })).toBeInTheDocument();
    unmount();
    expect(err).not.toHaveBeenCalled();
  });
});
