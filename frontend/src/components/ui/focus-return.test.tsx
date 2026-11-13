import { useState } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";

function Plain({ sheet = false }: { sheet?: boolean }) {
  const [open, setOpen] = useState(false);
  const Root = sheet ? Sheet : Dialog;
  const Content = sheet ? SheetContent : DialogContent;
  const Title = sheet ? SheetTitle : DialogTitle;
  const Desc = sheet ? SheetDescription : DialogDescription;
  return (
    <>
      <button onClick={() => setOpen(true)}>Open it</button>
      <Root open={open} onOpenChange={setOpen}>
        <Content>
          <Title>Thing</Title>
          <Desc>About the thing</Desc>
        </Content>
      </Root>
    </>
  );
}

describe("focus returns after a dialog or sheet closes", () => {
  it.each([false, true])("opened by plain state (sheet: %s)", async (sheet) => {
    render(<Plain sheet={sheet} />);
    const opener = screen.getByRole("button", { name: "Open it" });
    await userEvent.click(opener);
    await screen.findByRole("dialog");
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    await waitFor(() => expect(opener).toHaveFocus());
  });

  it("opened from a menu item, whose menu is gone, goes back to the menu button", async () => {
    function Menu() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <DropdownMenu>
            <DropdownMenuTrigger>Actions</DropdownMenuTrigger>
            <DropdownMenuContent>
              <DropdownMenuItem onSelect={() => setOpen(true)}>Move</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogContent>
              <DialogTitle>Move it</DialogTitle>
              <DialogDescription>Pick a folder</DialogDescription>
            </DialogContent>
          </Dialog>
        </>
      );
    }
    render(<Menu />);
    const trigger = screen.getByRole("button", { name: "Actions" });
    await userEvent.click(trigger);
    await userEvent.click(await screen.findByRole("menuitem", { name: "Move" }));
    await screen.findByRole("dialog");
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    await waitFor(() => expect(trigger).toHaveFocus());
  });
});
