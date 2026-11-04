import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { App } from "@/App";
import { mockFetch, SESSION, signedOut } from "@/test/utils";

describe("App", () => {
  it("sends signed-out visitors to the sign-in page", async () => {
    mockFetch({ [SESSION]: signedOut });
    render(<App />);
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });
});
