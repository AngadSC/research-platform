import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { announcePanel } from "@/components/shared/DockHandle";
import { GoogleEditorPanel } from "@/components/shared/GoogleEditorPanel";

beforeEach(() => {
  window.innerWidth = 1920;
});
afterEach(() => localStorage.clear());

const panel = (onClose = vi.fn()) =>
  render(
    <GoogleEditorPanel
      title="Plan"
      label="Google Docs"
      src="about:blank"
      openUrl="#"
      onClose={onClose}
    />,
  );

describe("Google editor panel", () => {
  it("has a keyboard resize handle that reports its width and makes room", async () => {
    panel();
    const handle = screen.getByRole("separator", { name: "Resize panel" });
    expect(handle).toHaveAttribute("aria-valuenow", "560");
    expect(document.documentElement.style.getPropertyValue("--google-w")).toBe("560px");
    handle.focus();
    await userEvent.keyboard("{ArrowLeft}");
    expect(handle).toHaveAttribute("aria-valuenow", "584");
  });

  it("never leaves the page less than 640px beside the sidebar", () => {
    window.innerWidth = 1280;
    panel();
    const handle = screen.getByRole("separator", { name: "Resize panel" });
    expect(handle).toHaveAttribute("aria-valuemax", "384");
  });

  it("closes when the assistant opens", () => {
    const onClose = vi.fn();
    panel(onClose);
    announcePanel("google");
    expect(onClose).not.toHaveBeenCalled();
    announcePanel("assistant");
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
