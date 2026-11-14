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
const FLAGGED_NOTICE =
  "Keep identifying participant data here only if your ethics approval allows it. Claude and other AI tools will never see this file.";

/** One choice, two answers: shown when the caller can take the "identifies participants" mark. */
function ParticipantChoice({
  value,
  onChange,
}: {
  value: boolean | null;
  onChange: (flagged: boolean) => void;
}) {
  const opts: [boolean, string, string][] = [
    [
      true,
      "This file identifies participants",
      "Names, contact details, ID numbers, faces or voices. Keep it here only if your ethics approval allows it. Claude and other AI tools will never see this file.",
    ],
    [false, "This file has no participant identifiers", "De-identified or aggregate data."],
  ];
  return (
    <fieldset className="grid gap-2">
      <legend className="mb-1 text-sm font-medium">Participant data</legend>
      {opts.map(([v, label, hint]) => (
        <label key={label} className="flex items-start gap-2 text-sm">
          <input
            type="radio"
            name="participant-choice"
            checked={value === v}
            onChange={() => onChange(v)}
            className="mt-0.5"
          />
          <span>
            <span className="font-medium">{label}</span>
            <span className="block text-xs text-muted-foreground">{hint}</span>
          </span>
        </label>
      ))}
    </fieldset>
  );
}

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** `participant` is the "Identifies participants" tick (false when the box is not shown). */
  send: (file: File, onProgress: (f: number) => void, participant: boolean) => Promise<unknown>;
  /** Choose several files; `send` is called once for each, in order. */
  multiple?: boolean;
  /** Show "Identifies participants", starting ticked when true (a flagged folder). */
  participant?: boolean;
}

/** Mounted fresh on every open, so the notice tick is never remembered. */
function UploadForm({
  send,
  onDone,
  multiple,
  participant,
}: {
  send: Props["send"];
  onDone: () => void;
  multiple?: boolean;
  participant?: boolean;
}) {
  const [files, setFiles] = useState<File[]>([]);
  const [ack, setAck] = useState(false);
  // With the choice shown, null means "not chosen yet"; a flagged folder starts on "identifies".
  const [choice, setChoice] = useState<boolean | null>(participant ? true : null);
  const hasChoice = participant !== undefined;
  const flagged = choice === true;
  const ready = hasChoice ? choice !== null : ack;
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
    if (!files.length || !ready) return;
    setError(undefined);
    setProgress(0);
    let done = 0;
    try {
      for (const [i, file] of files.entries()) {
        await send(file, (f) => setProgress((i + f) / files.length), flagged);
        done = i + 1;
      }
      toast.success(files.length > 1 ? `${files.length} files uploaded` : "File uploaded");
      onDone();
    } catch (e) {
      const { fields, form } = formErrors(e, ["file", "acknowledged_notice"]);
      const reason = fields.file ?? fields.acknowledged_notice ?? form ?? "Upload failed.";
      const msg = done
        ? `${done} of ${files.length} files uploaded. ${files[done]!.name} failed: ${reason} Upload again to send the rest.`
        : reason;
      setFiles(files.slice(done)); // the ones that went through must not be sent twice
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
        {flagged ? FLAGGED_NOTICE : NOTICE}
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
          aria-hidden
          className="sr-only"
          tabIndex={-1} // "Browse files" is the one keyboard control for this
          onChange={(e) => pick(e.target.files)}
        />
        <Button variant="outline" size="sm" autoFocus onClick={() => input.current?.click()}>
          Browse files
        </Button>
        <p className="text-xs text-muted-foreground">Up to 50 MB{multiple && " each"}.</p>
      </div>
      {hasChoice ? (
        <ParticipantChoice value={choice} onChange={setChoice} />
      ) : (
        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            checked={ack}
            onChange={(e) => setAck(e.target.checked)}
            className="mt-0.5"
          />
          I confirm this file contains no participant identifiers
        </label>
      )}
      <FormError message={error} />
      {progress !== null && (
        <progress aria-label="Upload progress" value={progress} max={1} className="w-full" />
      )}
      {progress === null && (!files.length || !ready) && (
        <p id="upload-hint" className="text-xs text-muted-foreground">
          {files.length
            ? hasChoice
              ? "Say whether the file identifies participants to upload."
              : "Tick the confirmation to upload."
            : hasChoice
              ? "Choose a file and say whether it identifies participants."
              : "Choose a file, then tick the confirmation to upload."}
        </p>
      )}
      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={onDone} disabled={progress !== null}>
          Cancel
        </Button>
        <Button
          aria-describedby="upload-hint"
          onClick={() => void submit()}
          disabled={!files.length || !ready || progress !== null}
        >
          Upload
        </Button>
      </div>
    </>
  );
}

export function UploadDialog({ open, onOpenChange, send, multiple, participant }: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        {open && (
          <UploadForm
            send={send}
            multiple={multiple}
            participant={participant}
            onDone={() => onOpenChange(false)}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}
