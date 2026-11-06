import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { App } from "@/App";
import { mockFetch, SESSION, signedOut } from "@/test/utils";

describe("App", () => {
  it("shows signed-out visitors the landing page with Sign in and Register", async () => {
    mockFetch({ [SESSION]: signedOut });
    render(<App />);
    expect(await screen.findByRole("banner")).toBeInTheDocument();
    expect(
      within(screen.getByRole("banner")).getByRole("link", { name: "Register" }),
    ).toBeInTheDocument();
    expect(
      within(screen.getByRole("banner")).getByRole("link", { name: "Sign in" }),
    ).toBeInTheDocument();
  });
});
