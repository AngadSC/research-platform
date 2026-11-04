import { ApiError, type FieldErrors } from "@/lib/api";

export interface FormErrors {
  fields: FieldErrors;
  form?: string;
}

/** Splits an API error into messages for known fields and one general message for everything else. */
export function formErrors(e: unknown, known: string[]): FormErrors {
  if (!(e instanceof ApiError))
    return { fields: {}, form: "Something went wrong. Please try again." };
  const fields: FieldErrors = {};
  const rest: string[] = [];
  for (const [k, v] of Object.entries(e.fieldErrors)) {
    if (known.includes(k)) fields[k] = v;
    else rest.push(v);
  }
  return { fields, form: rest[0] ?? (Object.keys(fields).length ? undefined : e.message) };
}

/** Only allow same-site paths as a post-login destination. */
export function safeNext(next: string | null | undefined): string {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/";
}
