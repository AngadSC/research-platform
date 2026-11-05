import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Markdown } from "@/lib/markdown";

describe("Markdown", () => {
  it("renders bold, italic, code, lists and https links", () => {
    const { container } = render(
      <Markdown text={"**bold** and *it* and `code`\n- one\n- two\nsee https://example.org/x"} />,
    );
    expect(container.querySelector("strong")).toHaveTextContent("bold");
    expect(container.querySelector("em")).toHaveTextContent("it");
    expect(container.querySelector("code")).toHaveTextContent("code");
    expect(container.querySelectorAll("li")).toHaveLength(2);
    const a = screen.getByRole("link", { name: "https://example.org/x" });
    expect(a).toHaveAttribute("rel", expect.stringContaining("noopener"));
  });

  it("never produces markup or script links from the text", () => {
    const { container } = render(
      <Markdown
        text={'<img src=x onerror="alert(1)"><script>alert(1)</script> [x](javascript:alert(1))'}
      />,
    );
    expect(container.querySelector("img, script")).toBeNull();
    expect(container.querySelector("a")).toBeNull();
    expect(container).toHaveTextContent("<script>alert(1)</script>");
  });
});
