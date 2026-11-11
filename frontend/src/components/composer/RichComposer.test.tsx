import { useState } from "react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { RichComposer, type Person } from "@/components/composer/RichComposer";

const ADA = { id: "11111111-1111-1111-1111-111111111111", name: "Ada Lovelace" };
const GRACE = { id: "22222222-2222-2222-2222-222222222222", name: "Grace Hopper" };
const PEOPLE: Person[] = [ADA, GRACE];

function Harness({
  people = PEOPLE,
  onSend = () => {},
  initial = "",
  enterToSend = true,
}: {
  people?: Person[] | null;
  onSend?: (text: string) => void;
  initial?: string;
  enterToSend?: boolean;
}) {
  const [text, setText] = useState(initial);
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSend(text);
      }}
    >
      <RichComposer
        ariaLabel="Message"
        value={text}
        onChange={setText}
        people={people ?? undefined}
        enterToSend={enterToSend}
        submitLabel="Send"
      />
    </form>
  );
}

const box = () => screen.getByRole("textbox", { name: "Message" }) as HTMLTextAreaElement;

beforeEach(() => localStorage.clear());

describe("RichComposer", () => {
  it("formats the selection from the toolbar", async () => {
    render(<Harness initial="make this bold" />);
    box().setSelectionRange(5, 9);
    await userEvent.click(screen.getByRole("button", { name: "Bold" }));
    expect(box()).toHaveValue("make **this** bold");
    await userEvent.click(screen.getByRole("button", { name: "Bulleted list" }));
    expect(box()).toHaveValue("- make **this** bold");
  });

  it("has an accessible toolbar and keyboard shortcuts", async () => {
    render(<Harness initial="word" />);
    const bar = screen.getByRole("toolbar", { name: "Formatting" });
    const names = [
      "Bold",
      "Italic",
      "Strikethrough",
      "Link",
      "Numbered list",
      "Bulleted list",
      "Quote",
      "Inline code",
      "Code block",
    ];
    for (const name of names)
      expect(within(bar).getByRole("button", { name })).toHaveAttribute("title");
    box().focus();
    box().setSelectionRange(0, 4);
    await userEvent.keyboard("{Control>}i{/Control}");
    expect(box()).toHaveValue("_word_");
    box().setSelectionRange(1, 5);
    await userEvent.keyboard("{Control>}{Shift>}x{/Shift}{/Control}");
    expect(box()).toHaveValue("_~~word~~_");
  });

  it("adds a link through the link box and refuses a script address", async () => {
    render(<Harness initial="the docs" />);
    box().setSelectionRange(4, 8);
    await userEvent.click(screen.getByRole("button", { name: "Link" }));
    const address = screen.getByLabelText("Link address");
    await userEvent.type(address, "javascript:alert(1){Enter}");
    expect(screen.getByRole("alert")).toHaveTextContent("web address");
    expect(box()).toHaveValue("the docs");
    await userEvent.clear(address);
    await userEvent.type(address, "example.org{Enter}");
    expect(box()).toHaveValue("the [docs](https://example.org)");
    expect(screen.queryByLabelText("Link address")).toBeNull();
  });

  it("hides the toolbar with Aa and remembers that", async () => {
    const { unmount } = render(<Harness />);
    await userEvent.click(screen.getByRole("button", { name: "Formatting" }));
    expect(screen.queryByRole("toolbar")).toBeNull();
    unmount();
    render(<Harness />);
    expect(screen.queryByRole("toolbar")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Formatting" }));
    expect(screen.getByRole("toolbar")).toBeInTheDocument();
  });

  it("inserts a picked emoji at the cursor and can search by name", async () => {
    render(<Harness initial="ab" />);
    box().setSelectionRange(1, 1);
    await userEvent.click(screen.getByRole("button", { name: "Emoji" }));
    await userEvent.type(screen.getByLabelText("Search emoji"), "microscope");
    await userEvent.click(screen.getByRole("button", { name: /microscope/ }));
    expect(box()).toHaveValue("a🔬b");
    expect(screen.queryByRole("dialog", { name: "Emoji" })).toBeNull();
  });

  it("Enter sends, Shift+Enter adds a line", async () => {
    const onSend = vi.fn();
    render(<Harness onSend={onSend} />);
    await userEvent.type(box(), "hello{Shift>}{Enter}{/Shift}there");
    expect(box()).toHaveValue("hello\nthere");
    expect(onSend).not.toHaveBeenCalled();
    await userEvent.keyboard("{Enter}");
    expect(onSend).toHaveBeenCalledWith("hello\nthere");
  });

  it("without enterToSend, Enter is a line and Ctrl+Enter sends", async () => {
    const onSend = vi.fn();
    render(<Harness onSend={onSend} enterToSend={false} />);
    await userEvent.type(box(), "a{Enter}b");
    expect(box()).toHaveValue("a\nb");
    await userEvent.keyboard("{Control>}{Enter}{/Control}");
    expect(onSend).toHaveBeenCalledWith("a\nb");
  });

  it("does not send an empty message", async () => {
    const onSend = vi.fn();
    render(<Harness onSend={onSend} />);
    await userEvent.type(box(), "   {Enter}");
    expect(onSend).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
  });
});

describe("@mention picker", () => {
  it("opens on @, filters as you type, and Enter inserts the token", async () => {
    const onSend = vi.fn();
    render(<Harness onSend={onSend} />);
    await userEvent.type(box(), "hi @gra");
    const list = screen.getByRole("listbox");
    expect(within(list).getAllByRole("option")).toHaveLength(1);
    await userEvent.keyboard("{Enter}");
    expect(box()).toHaveValue(`hi @[Grace Hopper](user:${GRACE.id}) `);
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(onSend).not.toHaveBeenCalled(); // that Enter chose a person, it did not send
  });

  it("arrow keys move the choice and Escape closes the list", async () => {
    render(<Harness />);
    await userEvent.type(box(), "@");
    const options = () => screen.getAllByRole("option");
    expect(options()[0]).toHaveAttribute("aria-selected", "true");
    await userEvent.keyboard("{ArrowDown}");
    expect(options()[1]).toHaveAttribute("aria-selected", "true");
    expect(box()).toHaveAttribute("aria-activedescendant", options()[1]!.id);
    await userEvent.keyboard("{ArrowUp}{ArrowUp}");
    expect(options()[1]).toHaveAttribute("aria-selected", "true"); // wraps round
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(box()).toHaveValue("@");
  });

  it("the @ button starts a mention, and a click chooses", async () => {
    render(<Harness initial="hey" />);
    box().setSelectionRange(3, 3);
    await userEvent.click(screen.getByRole("button", { name: "Mention someone" }));
    expect(box()).toHaveValue("hey @");
    await userEvent.click(screen.getByRole("option", { name: "Ada Lovelace" }));
    expect(box()).toHaveValue(`hey @[Ada Lovelace](user:${ADA.id}) `);
  });

  it("does not offer mentions where nobody is given, or inside an email address", async () => {
    const { unmount } = render(<Harness people={null} />);
    expect(screen.queryByRole("button", { name: "Mention someone" })).toBeNull();
    await userEvent.type(box(), "@");
    expect(screen.queryByRole("listbox")).toBeNull();
    unmount();
    render(<Harness />);
    await userEvent.type(box(), "write to me@ada");
    expect(screen.queryByRole("listbox")).toBeNull();
  });
});
