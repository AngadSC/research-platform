import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { App } from "@/App";
import { APP_NAME } from "@/lib/constants";

describe("App", () => {
  it("renders the app name", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: APP_NAME })).toBeInTheDocument();
  });
});
