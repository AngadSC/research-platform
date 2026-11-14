import { api } from "@/lib/api";

export type FormKind = "ethics" | "funding";

/** What the server could read from a form, by field name. Dates are YYYY-MM-DD. */
export type Suggestions = Record<string, string>;

const NAMES: Record<string, string> = {
  approval_number: "approval number",
  board: "board",
  title: "title",
  approval_date: "approval date",
  expiry_date: "expiry date",
  funder: "funder",
  program: "program",
  award_number: "award number",
  amount: "amount",
  currency: "currency",
  start_date: "start date",
  end_date: "end date",
};

export async function readForm(labId: string, kind: FormKind, file: File): Promise<Suggestions> {
  const body = new FormData();
  body.append("file", file);
  const out = await api<{ fields: Suggestions }>(`/api/labs/${labId}/form-reader/${kind}/`, {
    method: "POST",
    body,
  });
  return out.fields;
}

/** Puts suggestions into the form's fields, only where the person has not written anything.
 * Returns the names of what was filled, for a message. The currency comes with an amount that was
 * filled, since "CAD" is only a starting value. */
export function fillBlank(form: HTMLFormElement, fields: Suggestions): string[] {
  const filled: string[] = [];
  for (const [name, value] of Object.entries(fields)) {
    const input = form.elements.namedItem(name);
    if (!(input instanceof HTMLInputElement || input instanceof HTMLTextAreaElement)) continue;
    const blank = input.value.trim() === "";
    const startingCurrency = name === "currency" && filled.includes(NAMES.amount!);
    if (!blank && !startingCurrency) continue;
    input.value = value;
    filled.push(NAMES[name] ?? name);
  }
  return filled;
}
