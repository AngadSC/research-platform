export type GoogleLinkKind = "doc" | "sheet" | "slides" | "form" | "file";

export interface GoogleLink {
  kind: GoogleLinkKind;
  id: string;
  url: string;
}

const KINDS: Record<string, GoogleLinkKind> = {
  document: "doc",
  spreadsheets: "sheet",
  presentation: "slides",
  forms: "form",
};
export const KIND_LABEL: Record<GoogleLinkKind, string> = {
  doc: "Google Doc",
  sheet: "Google Sheet",
  slides: "Google Slides",
  form: "Google Form",
  file: "Drive file",
};

/** A Google Docs, Sheets, Slides, Forms or Drive file link, or null for anything else. Only
 * https on Google's own two hosts counts, so a look-alike address never gets a card. */
export function parseGoogleLink(text: string): GoogleLink | null {
  let u: URL;
  try {
    u = new URL(text.trim());
  } catch {
    return null;
  }
  if (u.protocol !== "https:" || u.username || u.password) return null;
  if (u.hostname === "docs.google.com") {
    const m =
      /^\/(document|spreadsheets|presentation|forms)\/(?:u\/\d+\/)?d\/(?:e\/)?([\w-]{10,})/.exec(
        u.pathname,
      );
    return m ? { kind: KINDS[m[1]!]!, id: m[2]!, url: u.toString() } : null;
  }
  if (u.hostname === "drive.google.com") {
    const m = /^\/file\/d\/([\w-]{10,})/.exec(u.pathname);
    const id = m?.[1] ?? (u.pathname === "/open" ? u.searchParams.get("id") : null);
    return id && /^[\w-]{10,}$/.test(id) ? { kind: "file", id, url: u.toString() } : null;
  }
  return null;
}
