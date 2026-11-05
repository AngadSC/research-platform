import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RelativeTime } from "@/components/shared/RelativeTime";
import { fullDate } from "@/lib/format";

describe("RelativeTime", () => {
  it("shows relative text and the full date on hover", () => {
    const iso = new Date(Date.now() + 25 * 86400_000).toISOString();
    render(<RelativeTime value={iso} />);
    const el = screen.getByText("in 25 days");
    expect(el.tagName).toBe("TIME");
    expect(el).toHaveAttribute("datetime", iso);
    expect(el).toHaveAttribute("title", fullDate(iso));
  });
});
