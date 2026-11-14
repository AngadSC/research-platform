import { describe, expect, it } from "vitest";
import { fillBlank } from "@/lib/formReader";

function form(html: string) {
  const f = document.createElement("form");
  f.innerHTML = html;
  return f;
}

describe("fillBlank", () => {
  it("fills empty fields and leaves what the person wrote", () => {
    const f = form(
      '<input name="approval_number" value=""><input name="board" value="My REB"><input name="title">',
    );
    const filled = fillBlank(f, { approval_number: "Pro1", board: "Other", title: "T" });
    expect(filled).toEqual(["approval number", "title"]);
    expect((f.elements.namedItem("board") as HTMLInputElement).value).toBe("My REB");
    expect((f.elements.namedItem("approval_number") as HTMLInputElement).value).toBe("Pro1");
  });

  it("replaces the starting currency only along with a filled amount", () => {
    const f = form('<input name="amount"><input name="currency" value="CAD">');
    fillBlank(f, { amount: "10.00", currency: "USD" });
    expect((f.elements.namedItem("currency") as HTMLInputElement).value).toBe("USD");
    const g = form('<input name="amount" value="5"><input name="currency" value="CAD">');
    fillBlank(g, { amount: "10.00", currency: "USD" });
    expect((g.elements.namedItem("currency") as HTMLInputElement).value).toBe("CAD");
  });

  it("skips fields the form does not have", () => {
    expect(fillBlank(form('<input name="x">'), { funder: "A" })).toEqual([]);
  });
});
