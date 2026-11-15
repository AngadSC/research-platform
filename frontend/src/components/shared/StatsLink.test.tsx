import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { expect, it, vi } from "vitest";
import { StatsLink } from "./StatsLink";

const warmUp = vi.fn();
vi.mock("@/lib/stats/engine", () => ({ getStatsEngine: () => ({ warmUp }) }));

it("warms up the engine when the link is pointed at or focused", async () => {
  render(
    <MemoryRouter>
      <StatsLink to="/x">Stats</StatsLink>
    </MemoryRouter>,
  );
  await userEvent.hover(screen.getByRole("link", { name: "Stats" }));
  await vi.waitFor(() => expect(warmUp).toHaveBeenCalled());
});
