import { act, render, screen } from "@testing-library/react";
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

  it("can be widened to nearly the whole window", () => {
    window.innerWidth = 1280;
    panel();
    const handle = screen.getByRole("separator", { name: "Resize panel" });
    expect(handle).toHaveAttribute("aria-valuemax", "1200");
  });

  it("floats instead of closing when the assistant opens", () => {
    const onClose = vi.fn();
    panel(onClose);
    act(() => announcePanel("assistant"));
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByRole("separator", { name: "Resize window" })).toBeInTheDocument();
    expect(document.documentElement.style.getPropertyValue("--google-w")).toBe("");
  });

  it("floats as a window that resizes from its corner, and docks again", async () => {
    panel();
    await userEvent.click(screen.getByRole("button", { name: "Float as a window" }));
    const grip = screen.getByRole("separator", { name: "Resize window" });
    grip.focus();
    await userEvent.keyboard("{ArrowRight}{ArrowDown}");
    expect(grip.getAttribute("aria-valuetext")).toMatch(/^664 by /);
    await userEvent.click(screen.getByRole("button", { name: "Dock to the right" }));
    expect(screen.getByRole("separator", { name: "Resize panel" })).toBeInTheDocument();
  });

  it("closes only from its X, which is the first control", async () => {
    const onClose = vi.fn();
    panel(onClose);
    const buttons = screen.getAllByRole("button");
    expect(buttons[0]).toHaveAccessibleName("Close panel");
    await userEvent.click(buttons[0]!);
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
