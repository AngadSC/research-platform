import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { TeamTable } from "@/components/dashboard/TeamTable";
import type { DashPerson } from "@/hooks/dashboard";
import type { TrainingCompliance } from "@/lib/api-types";

const person = (over: Partial<DashPerson>): DashPerson => ({
  user_id: "u1",
  name: "Ada",
  role: "member",
  open_tasks: 3,
  overdue_tasks: 2,
  in_progress_tasks: 1,
  done_last_30_days: 4,
  last_active_at: null,
  ...over,
});
const cell = (status: string) => ({ status, record: null, completed_on: null, expires_on: null });
const compliance = {
  requirements: [{ id: "r1", name: "Safety" }],
  members: [
    { user: { id: "u1" }, role: "member", cells: { r1: cell("expired") } },
    { user: { id: "u2" }, role: "member", cells: { r1: cell("current") } },
  ],
  summary: {},
};

function show(people: DashPerson[]) {
  render(
    <MemoryRouter>
      <TeamTable
        labId="lab1"
        people={people}
        training={compliance as unknown as TrainingCompliance}
      />
    </MemoryRouter>,
  );
}

describe("Team table", () => {
  it("links each count to that person's tasks and flags training", () => {
    show([
      person({}),
      person({ user_id: "u2", name: "Ben", overdue_tasks: 0, in_progress_tasks: 0 }),
    ]);
    const ada = screen.getByText("Ada").closest("tr")!;
    expect(within(ada).getByRole("link", { name: "Ada" })).toHaveAttribute(
      "href",
      "/labs/lab1/team-tasks?assignee=u1&show=open",
    );
    expect(within(ada).getByRole("link", { name: "2 overdue tasks for Ada" })).toHaveAttribute(
      "href",
      "/labs/lab1/team-tasks?assignee=u1&show=overdue",
    );
    expect(within(ada).getByRole("link", { name: "1 in progress tasks for Ada" })).toHaveAttribute(
      "href",
      "/labs/lab1/team-tasks?assignee=u1&show=in_progress",
    );
    expect(within(ada).getByRole("link", { name: "Needs attention" })).toHaveAttribute(
      "href",
      "/labs/lab1/training",
    );
    const ben = screen.getByText("Ben").closest("tr")!;
    expect(within(ben).getByText("OK")).toBeInTheDocument();
    expect(within(ben).queryByRole("link", { name: /overdue/ })).toBeNull(); // 0 is not a link
    expect(within(ben).getByText("No activity yet")).toBeInTheDocument(); // nothing is invented
  });
});
