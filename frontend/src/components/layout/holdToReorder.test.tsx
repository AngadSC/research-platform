import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import {
  applyOrder,
  moveId,
  ReorderRow,
  useHoldToReorder,
} from "@/components/layout/holdToReorder";

describe("order helpers", () => {
  it("moves one id to a place", () => {
    expect(moveId(["a", "b", "c"], "a", 2)).toEqual(["b", "c", "a"]);
    expect(moveId(["a", "b", "c"], "c", 0)).toEqual(["c", "a", "b"]);
  });
  it("applies a saved order and puts what it has never seen last", () => {
    const items = ["home", "projects", "chat", "papers"];
    expect(applyOrder(items, (x) => x, ["chat", "home"])).toEqual([
      "chat",
      "home",
      "projects",
      "papers",
    ]);
    expect(applyOrder(items, (x) => x, ["gone", "papers"])).toEqual([
      "papers",
      "home",
      "projects",
      "chat",
    ]);
  });
});

function List({ onChange }: { onChange?: (o: string[]) => void }) {
  const [order, setOrder] = useState(["home", "tasks", "chat"]);
  const reorder = useHoldToReorder(order, (o) => {
    setOrder(o);
    onChange?.(o);
  });
  return (
    <nav>
      {order.map((id) => (
        <ReorderRow key={id} id={id} reorder={reorder}>
          <a href={`#${id}`}>{id}</a>
        </ReorderRow>
      ))}
    </nav>
  );
}

describe("useHoldToReorder", () => {
  it("moves the focused row with Alt and the arrow keys", async () => {
    let last: string[] = [];
    render(<List onChange={(o) => (last = o)} />);
    screen.getByRole("link", { name: "tasks" }).focus();
    await userEvent.keyboard("{Alt>}{ArrowUp}{/Alt}");
    expect(last).toEqual(["tasks", "home", "chat"]);
    expect(screen.getAllByRole("link").map((l) => l.textContent)).toEqual([
      "tasks",
      "home",
      "chat",
    ]);
    await userEvent.keyboard("{Alt>}{ArrowDown}{ArrowDown}{/Alt}");
    expect(last).toEqual(["home", "chat", "tasks"]);
  });

  it("leaves a plain arrow key and the ends alone", async () => {
    let calls = 0;
    render(<List onChange={() => calls++} />);
    screen.getByRole("link", { name: "home" }).focus();
    await userEvent.keyboard("{ArrowUp}{Alt>}{ArrowUp}{/Alt}");
    expect(calls).toBe(0);
  });
});
