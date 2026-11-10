import { Upload } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { FormError } from "@/components/shared/FormError";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { formErrors } from "@/lib/forms";

export const MAX_BYTES = 50 * 1024 * 1024;
export const NOTICE =
  "Do not upload participant identifiers. Upload only anonymized or aggregate data.";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  send: (file: File, onProgress: (f: number) => void) => Promise<unknown>;
  /** Choose several files; `send` is called once for each, in order. */
  multiple?: boolean;
}

/** Mounted fresh on every open, so the notice tick is never remembered. */
function UploadForm({
  send,
  onDone,
  multiple,
}: {
  send: Props["send"];
  onDone: () => void;
  multiple?: boolean;
}) {
  const [files, setFiles] = useState<File[]>([]);
  const [ack, setAck] = useState(false);
  const [error, setError] = useState<string>();
  const [progress, setProgress] = useState<number | null>(null);
  const input = useRef<HTMLInputElement>(null);

  function pick(list: FileList | null) {
    const picked = Array.from(list ?? []).slice(0, multiple ? undefined : 1);
    if (!picked.length) return;
    const big = picked.find((f) => f.size > MAX_BYTES);
    if (big) {
      setFiles([]);
      setError(
        `${picked.length > 1 ? big.name : "That file"} is ${(big.size / 1048576).toFixed(1)} MB. The limit is 50 MB.`,
      );
      return;
    }
    setError(undefined);
    setFiles(picked);
  }

  async function submit() {
    if (!files.length || !ack) return;
    setError(undefined);
    setProgress(0);
    try {
      for (const [i, file] of files.entries())
        await send(file, (f) => setProgress((i + f) / files.length));
      toast.success(files.length > 1 ? `${files.length} files uploaded` : "File uploaded");
      onDone();
    } catch (e) {
      const { fields, form } = formErrors(e, ["file", "acknowledged_notice"]);
      const msg = fields.file ?? fields.acknowledged_notice ?? form ?? "Upload failed.";
      setError(msg);
      toast.error(msg);
      setProgress(null);
    }
  }

  return (
    <>
      <DialogTitle className="text-base font-semibold">Upload file</DialogTitle>
      <DialogDescription className="sr-only">
        Choose a file to add to this project.
      </DialogDescription>
      <p
        role="note"
        className="rounded-md border border-primary/40 bg-primary/10 p-3 text-sm font-medium"
      >
        {NOTICE}
      </p>
      <div
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          pick(e.dataTransfer.files);
        }}
        className="grid place-items-center gap-2 rounded-lg border border-dashed p-6 text-center"
      >
        <Upload aria-hidden className="size-5 text-muted-foreground" />
        <p className="text-sm">
          {files.length > 1
            ? `${files.length} files chosen`
            : (files[0]?.name ?? (multiple ? "Drag files here, or" : "Drag a file here, or"))}
        </p>
        <input
          ref={input}
          type="file"
          multiple={multiple}
          aria-label="Choose file"
          className="sr-only"
          onChange={(e) => pick(e.target.files)}
        />
        <Button variant="outline" size="sm" onClick={() => input.current?.click()}>
          Browse files
        </Button>
        <p className="text-xs text-muted-foreground">Up to 50 MB{multiple && " each"}.</p>
      </div>
      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          checked={ack}
          onChange={(e) => setAck(e.target.checked)}
          className="mt-0.5"
        />
        I confirm this file contains no participant identifiers
      </label>
      <FormError message={error} />
      {progress !== null && (
        <progress aria-label="Upload progress" value={progress} max={1} className="w-full" />
      )}
      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={onDone} disabled={progress !== null}>
          Cancel
        </Button>
        <Button onClick={() => void submit()} disabled={!files.length || !ack || progress !== null}>
          Upload
        </Button>
      </div>
    </>
  );
}

export function UploadDialog({ open, onOpenChange, send, multiple }: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        {open && <UploadForm send={send} multiple={multiple} onDone={() => onOpenChange(false)} />}
      </DialogContent>
    </Dialog>
  );
}
