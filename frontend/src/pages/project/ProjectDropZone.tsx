import { FileUp } from "lucide-react";
import { useRef, useState, type DragEvent, type ReactNode } from "react";
import { useAttachments } from "@/hooks/projects";
import { UploadDialog } from "@/pages/project/UploadDialog";

const hasFiles = (e: DragEvent) => Array.from(e.dataTransfer.types).includes("Files");

/** Drop a PDF (or any file) anywhere on a project to upload it. It opens the usual upload box
 * with the files already chosen, so the participant-identifier confirmation is still asked. The
 * file goes to the project's top-level files; use Documents to put one in a folder. */
export function ProjectDropZone({
  labId,
  projectId,
  enabled,
  name,
  children,
}: {
  labId: string;
  projectId: string;
  enabled: boolean;
  name: string;
  children: ReactNode;
}) {
  const { uploadFile } = useAttachments(labId, projectId);
  const [over, setOver] = useState(false);
  const [dropped, setDropped] = useState<File[]>([]);
  const depth = useRef(0); // dragenter/leave fire for every child element

  if (!enabled) return <>{children}</>;
  return (
    <div
      className="relative"
      onDragEnter={(e) => {
        if (!hasFiles(e)) return;
        depth.current += 1;
        setOver(true);
      }}
      onDragOver={(e) => hasFiles(e) && e.preventDefault()}
      onDragLeave={(e) => {
        if (!hasFiles(e)) return;
        depth.current = Math.max(0, depth.current - 1);
        if (depth.current === 0) setOver(false);
      }}
      onDrop={(e) => {
        if (!hasFiles(e)) return;
        e.preventDefault();
        depth.current = 0;
        setOver(false);
        const files = Array.from(e.dataTransfer.files);
        if (files.length) setDropped(files);
      }}
    >
      {children}
      {over && (
        <div
          aria-hidden
          className="pointer-events-none fixed inset-4 z-40 grid place-items-center rounded-xl border-2 border-dashed border-primary bg-primary/10 backdrop-blur-[1px]"
        >
          <p className="flex items-center gap-2 rounded-lg bg-background px-4 py-3 text-sm font-medium shadow">
            <FileUp className="size-5 text-primary" /> Drop to upload to {name}
          </p>
        </div>
      )}
      <UploadDialog
        open={dropped.length > 0}
        onOpenChange={(o) => !o && setDropped([])}
        multiple
        initialFiles={dropped}
        send={(file, onProgress) => uploadFile.mutateAsync({ file, onProgress })}
      />
    </div>
  );
}
