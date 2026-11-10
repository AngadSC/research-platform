import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { InstitutionInput } from "@/components/shared/InstitutionInput";
import type { Lab } from "@/lib/api-types";
import { LabDetailsSection } from "@/pages/admin/LabDetailsSection";
import { makeLab, mockFetch } from "@/test/utils";

const alberta = {
  id: "https://ror.org/0160cpw27",
  name: "University of Alberta",
  address: "Edmonton, Alberta, Canada",
  website: "https://www.ualberta.ca/",
};

function wrap(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

it("suggests institutions, and offers only labelled web searches after a pick", async () => {
  mockFetch({
    "GET /api/institutions/search/?q=university%20of%20a": { body: { results: [alberta] } },
  });
  const onPick = vi.fn();
  wrap(<InstitutionInput id="i" name="institution_name" onPick={onPick} />);

  const box = screen.getByRole("textbox");
  await userEvent.type(box, "university of a");
  await userEvent.click(await screen.findByRole("button", { name: /University of Alberta/ }));

  expect(onPick).toHaveBeenCalledWith(alberta);
  expect(box).toHaveValue("University of Alberta");
  expect(screen.queryByRole("list", { name: "Suggested institutions" })).toBeNull();
  const ethics = screen.getByRole("link", { name: /web search for its ethics pages/ });
  expect(ethics.getAttribute("href")).toContain("google.com/search?q=University%20of%20Alberta");
  expect(screen.getByText(/check that what you find is really theirs/)).toBeInTheDocument();

  await userEvent.type(box, "x");
  expect(screen.queryByRole("link", { name: /web search/ })).toBeNull();
});

it("fills only the empty address and website fields on the lab details form", async () => {
  mockFetch({
    "GET /api/institutions/search/?q=alberta": { body: { results: [alberta] } },
  });
  const lab = {
    ...makeLab(["manage_lab"]),
    department: "",
    description: "",
    address: "",
    contact_email: "",
    website: "https://our-lab.example",
    inventory_enabled: true,
  } as unknown as Lab;
  wrap(<LabDetailsSection lab={lab} />);

  const box = screen.getByLabelText("Institution");
  await userEvent.clear(box);
  await userEvent.type(box, "alberta");
  await userEvent.click(await screen.findByRole("button", { name: /University of Alberta/ }));

  expect(screen.getByLabelText("Address")).toHaveValue("Edmonton, Alberta, Canada");
  expect(screen.getByLabelText("Website")).toHaveValue("https://our-lab.example");
});
