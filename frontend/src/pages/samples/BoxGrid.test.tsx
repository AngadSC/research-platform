import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Tube } from "@/lib/api-types";
import { BoxGrid } from "./BoxGrid";

const tube = {
  id: "t1",
  box: "b1",
  row: 1,
  col: 2,
  position: "A2",
  sample: { id: "s1", code: "P0012", name: "pCW-MalE-CST06", kind: "plasmid" },
  label: "",
  amount: "",
  stored_on: null,
  owner: { id: "u1", email: "a@example.test", avatar_url: null },
} as Tube;
const box = { name: "Box 1", rows: 9, cols: 9, tubes: [tube] };

describe("BoxGrid", () => {
  it("shows every spot of a 9 by 9 box, with the code in a filled one", () => {
    render(<BoxGrid box={box} onFilled={() => {}} onEmpty={() => {}} />);
    expect(screen.getAllByRole("button")).toHaveLength(81);
    expect(screen.getByRole("button", { name: "A1, empty" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "I9, empty" })).toBeInTheDocument();
    const filled = screen.getByRole("button", { name: "A2, P0012 pCW-MalE-CST06" });
    expect(filled).toHaveTextContent("P0012");
  });

  it("asks to place a tube in an empty spot and to open a filled one", async () => {
    const onEmpty = vi.fn();
    const onFilled = vi.fn();
    render(<BoxGrid box={box} onFilled={onFilled} onEmpty={onEmpty} />);
    await userEvent.click(screen.getByRole("button", { name: "B3, empty" }));
    expect(onEmpty).toHaveBeenCalledWith(2, 3);
    await userEvent.click(screen.getByRole("button", { name: /^A2, P0012/ }));
    expect(onFilled).toHaveBeenCalledWith(tube);
  });

  it("leaves empty spots off limits when nobody may place tubes", () => {
    render(<BoxGrid box={box} onFilled={() => {}} />);
    expect(screen.getByRole("button", { name: "A1, empty" })).toBeDisabled();
  });
});
