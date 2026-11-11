import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MessageText as Markdown } from "@/lib/markdown";

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

  it("with ownLinksOnly, other origins become plain text with the address shown (D198)", () => {
    const own = `${window.location.origin}/labs/1/projects/2`;
    const { container } = render(
      <Markdown
        ownLinksOnly
        text={`[the plan](${own}) and [click here](https://evil.example/steal?x=1) and https://evil.example/b`}
      />,
    );
    const links = container.querySelectorAll("a");
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAttribute("href", own);
    // nothing hides behind link text: the real address is written out
    expect(container).toHaveTextContent("click here (https://evil.example/steal?x=1)");
    expect(container).toHaveTextContent("https://evil.example/b");
  });

  it("renders strike, underscore italic, quotes, numbered lists and code blocks (D255)", () => {
    const { container } = render(
      <Markdown
        text={
          "~~old~~ and _new_ but snake_case_name stays\n> quoted\n1. one\n2. two\n```\nlet a = **1**;\n```"
        }
      />,
    );
    expect(container.querySelector("del")).toHaveTextContent("old");
    expect(container.querySelector("em")).toHaveTextContent("new");
    expect(container).toHaveTextContent("snake_case_name stays");
    expect(container.querySelector("blockquote")).toHaveTextContent("quoted");
    expect(container.querySelectorAll("ol li")).toHaveLength(2);
    // inside a code block nothing is formatted
    expect(container.querySelector("pre code")).toHaveTextContent("let a = **1**;");
    expect(container.querySelector("pre strong")).toBeNull();
  });

  it("keeps plain text, spacing and line breaks as written", () => {
    const { container } = render(<Markdown text={"hello there\n  indented line\n\nlast"} />);
    expect(container.querySelectorAll("p")).toHaveLength(3);
    expect(container).toHaveTextContent("hello there");
    expect(container.querySelectorAll("a, strong, em, ul, ol")).toHaveLength(0);
  });

  it("links open safely and allow only web and email addresses", () => {
    const { container } = render(
      <Markdown text={"[site](https://example.org/a) [mail](mailto:a@example.test)"} />,
    );
    const [web, mail] = Array.from(container.querySelectorAll("a"));
    expect(web).toHaveAttribute("target", "_blank");
    expect(web).toHaveAttribute("rel", "noopener noreferrer nofollow");
    expect(mail).toHaveAttribute("href", "mailto:a@example.test");
  });

  it.each([
    "[x](javascript:alert(1))",
    "[x](JaVaScRiPt:alert(1))",
    "[x](data:text/html;base64,PHNjcmlwdD4=)",
    "[x](vbscript:msgbox(1))",
    "[x](//evil.example/a)",
    "[x]( javascript:alert(1))",
  ])("never makes a link of %s", (text) => {
    const { container } = render(<Markdown text={text} />);
    expect(container.querySelector("a")).toBeNull();
  });

  it("treats raw html, handlers and breakouts as text", () => {
    const { container } = render(
      <Markdown
        text={[
          "<script>alert(1)</script>",
          "<img src=x onerror=alert(1)>",
          '<a href="javascript:alert(1)">x</a>',
          '[x](https://a.example/"onmouseover="alert(1))',
          "**<b onclick=alert(1)>x</b>**",
        ].join("\n")}
      />,
    );
    expect(
      container.querySelector("script, img, b, [onerror], [onclick], [onmouseover]"),
    ).toBeNull();
    for (const a of Array.from(container.querySelectorAll("a")))
      expect(a.getAttribute("href")).toMatch(/^https:\/\//);
    expect(container).toHaveTextContent("<script>alert(1)</script>");
  });

  it("shows a mention as a chip with only the name, and ignores a forged one", () => {
    const id = "123e4567-e89b-12d3-a456-426614174000";
    const { container } = render(
      <Markdown text={`hi @[Ada <b>L</b>](user:${id}) and @[Bob](user:nope)`} />,
    );
    expect(container).toHaveTextContent("hi @Ada <b>L</b> and @[Bob](user:nope)");
    expect(container.querySelector("b")).toBeNull();
    expect(container.querySelectorAll("a")).toHaveLength(0);
  });
});
