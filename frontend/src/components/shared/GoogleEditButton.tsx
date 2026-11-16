import { Pencil } from "lucide-react";
import { Button } from "@/components/ui/button";
import { googleEditor, openInGooglePanel } from "@/lib/googleFiles";

type GoogleFile = { content_type: string; drive_file_id?: string; original_filename: string };

/** "Edit" for a file linked from Google Drive that is a Doc, Sheet or Slides: opens it in the
 * floating panel, which stays open while you move around the app. Nothing for any other file. */
export function GoogleEditButton({ file, label = "Edit" }: { file: GoogleFile; label?: string }) {
  const f = { ...file, drive_file_id: file.drive_file_id ?? "" };
  const editor = googleEditor(f);
  if (!editor) return null;
  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      aria-label={`${label} ${file.original_filename} in ${editor.label}`}
      onClick={() => openInGooglePanel(f)}
    >
      <Pencil aria-hidden /> {label}
    </Button>
  );
}
