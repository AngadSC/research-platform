import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";
import { ExternalLinkItem } from "@/components/shared/ExternalLinkItem";
import type { ExternalLink } from "@/lib/api-types";

const EDITOR = "https://docs.google.com/spreadsheets/d/abc/edit";
const link = (editor_url: string) =>
  ({
    id: "l1",
    provider: "google_drive",
    provider_label: "Google Drive",
    title: "Budget sheet",
    url: "https://docs.google.com/spreadsheets/d/abc/edit?usp=drivesdk",
    status: "ok",
    linked_by: { id: "u1", email: "ada@uni.edu", display_name: "Ada" },
    editor_url,
  }) as unknown as ExternalLink;

it("opens a linked Sheet in Google's editor, with the way out always shown", async () => {
  render(<ExternalLinkItem link={link(EDITOR)} />);
  await userEvent.click(screen.getByRole("button", { name: "Edit Budget sheet here" }));

  expect(screen.getByTitle("Budget sheet")).toHaveAttribute("src", EDITOR);
  expect(screen.getByRole("link", { name: /Open in Google Sheets/ })).toHaveAttribute(
    "href",
    EDITOR,
  );
});

it("offers no editor for a file Google cannot edit here", () => {
  render(<ExternalLinkItem link={link("")} />);
  expect(screen.queryByRole("button", { name: /here/ })).toBeNull();
});
