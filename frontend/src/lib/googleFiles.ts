import type { Attachment } from "@/lib/api-types";
import { openGooglePanel } from "@/lib/googlePanel";

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

/** An upload that "Edit in Google" can turn into a Google Doc, Sheet or Slides copy (VISION B3). */
export const convertible = (a: Pick<Attachment, "original_filename" | "drive_file_id">) =>
  !a.drive_file_id && /\.(docx|xlsx|pptx)$/i.test(a.original_filename);

/** Opens a linked Google Doc, Sheet or Slides file in the floating panel (D326): editing, or just
 * a preview. Returns false for any other file. */
export function openInGooglePanel(
  file: Pick<Attachment, "content_type" | "drive_file_id" | "original_filename">,
  edit = true,
) {
  const editor = googleEditor(file);
  if (!editor) return false;
  openGooglePanel({
    title: file.original_filename,
    label: editor.label,
    src: edit ? editor.edit : editor.preview,
    openUrl: editor.edit,
  });
  return true;
}

const DOC_URL =
  /^https:\/\/docs\.google\.com\/(document|spreadsheets|presentation)\/d\/([A-Za-z0-9_-]{10,})/;

/** Opens a link to a Google Doc, Sheet or Slides file in the floating panel, if it is one.
 * Rebuilt from the file id, so the panel only ever loads docs.google.com. Returns false for any
 * other link. */
export function openGoogleLinkInPanel(url: string, title: string) {
  const m = DOC_URL.exec(url);
  if (!m) return false;
  const kind = Object.values(KINDS).find((k) => k.path === m[1])!;
  const base = `https://docs.google.com/${kind.path}/d/${m[2]}`;
  openGooglePanel({ title, label: kind.label, src: `${base}/edit`, openUrl: `${base}/edit` });
  return true;
}

export const isGoogleDocLink = (url: string) => DOC_URL.test(url);
