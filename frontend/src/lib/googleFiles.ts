import type { Attachment } from "@/lib/api-types";

// What a Drive-linked file's type says it is. Drive gives these types to Docs, Sheets and Slides.
const KINDS: Record<string, { path: string; label: string }> = {
  "application/vnd.google-apps.document": { path: "document", label: "Google Docs" },
  "application/vnd.google-apps.spreadsheet": { path: "spreadsheets", label: "Google Sheets" },
  "application/vnd.google-apps.presentation": { path: "presentation", label: "Google Slides" },
};

/** Where a linked Google Doc, Sheet or Slides file opens in Google's own editor, or null for any
 * other file. Built from the file id the server checked when it was linked (never from the stored
 * link), so the address can only ever be docs.google.com. */
export function googleEditor(a: Pick<Attachment, "content_type" | "drive_file_id">) {
  const kind = a.drive_file_id ? KINDS[a.content_type] : undefined;
  if (!kind) return null;
  const base = `https://docs.google.com/${kind.path}/d/${encodeURIComponent(a.drive_file_id)}`;
  return { label: kind.label, edit: `${base}/edit`, preview: `${base}/preview` };
}

export const isImage = (a: Pick<Attachment, "content_type" | "drive_file_id">) =>
  !a.drive_file_id && /^image\/(png|jpe?g|gif|webp|svg\+xml)$/.test(a.content_type);
