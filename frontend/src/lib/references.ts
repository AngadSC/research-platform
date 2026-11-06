import type { Reference } from "@/lib/api-types";
import { safeHttpUrl } from "@/lib/lineage";
import { isHttpUrl } from "@/lib/research";

/** Same rules as the backend (D95). */
export const DOI_RE = /^10\.\d{4,9}\/\S+$/;
export const MAX_REFERENCES = 50;

/** A DOI link, or null when the stored value is not a well-formed DOI. */
export const doiHref = (doi: string): string | null =>
  DOI_RE.test(doi) ? `https://doi.org/${encodeURI(doi)}` : null;

/** Link target for a reference's URL: only http(s), never anything else. */
export const urlHref = (url: string): string | null => safeHttpUrl(url);

export interface RefErrors {
  title?: string;
  url?: string;
  doi?: string;
}

/** One entry per row; an empty object means the row is fine. */
export function validateReferences(rows: Reference[]): RefErrors[] {
  return rows.map((r) => {
    const e: RefErrors = {};
    if (!r.title.trim()) e.title = "Enter a title";
    const url = (r.url ?? "").trim();
    if (url && !isHttpUrl(url)) e.url = "Enter a link starting with http:// or https://";
    const doi = (r.doi ?? "").trim();
    if (doi && !DOI_RE.test(doi)) e.doi = "Enter a DOI like 10.1234/abcd";
    return e;
  });
}

export function cleanReferences(rows: Reference[]): Reference[] {
  return rows.map((r) => ({
    title: r.title.trim(),
    url: (r.url ?? "").trim(),
    doi: (r.doi ?? "").trim(),
  }));
}

export const moveRow = <T>(rows: T[], from: number, to: number): T[] => {
  if (to < 0 || to >= rows.length) return rows;
  const next = [...rows];
  next.splice(to, 0, ...next.splice(from, 1));
  return next;
};
