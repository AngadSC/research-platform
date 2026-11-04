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
}

/** Mounted fresh on every open, so the notice tick is never remembered. */
function UploadForm({ send, onDone }: { send: Props["send"]; onDone: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [ack, setAck] = useState(false);
  const [error, setError] = useState<string>();
  const [progress, setProgress] = useState<number | null>(null);
  const input = useRef<HTMLInputElement>(null);

  function pick(f: File | undefined) {
    if (!f) return;
    if (f.size > MAX_BYTES) {
      setFile(null);
      setError(`That file is ${(f.size / 1048576).toFixed(1)} MB. The limit is 50 MB.`);
      return;
    }
    setError(undefined);
    setFile(f);
  }

  async function submit() {
    if (!file || !ack) return;
    setError(undefined);
    setProgress(0);
    try {
      await send(file, setProgress);
      toast.success("File uploaded");
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
          pick(e.dataTransfer.files[0]);
        }}
        className="grid place-items-center gap-2 rounded-lg border border-dashed p-6 text-center"
      >
        <Upload aria-hidden className="size-5 text-muted-foreground" />
        <p className="text-sm">{file ? file.name : "Drag a file here, or"}</p>
        <input
          ref={input}
          type="file"
          aria-label="Choose file"
          className="sr-only"
          onChange={(e) => pick(e.target.files?.[0])}
        />
        <Button variant="outline" size="sm" onClick={() => input.current?.click()}>
          Browse files
        </Button>
        <p className="text-xs text-muted-foreground">Up to 50 MB.</p>
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
        <Button onClick={() => void submit()} disabled={!file || !ack || progress !== null}>
          Upload
        </Button>
      </div>
    </>
  );
}

export function UploadDialog({ open, onOpenChange, send }: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        {open && <UploadForm send={send} onDone={() => onOpenChange(false)} />}
      </DialogContent>
    </Dialog>
  );
}
