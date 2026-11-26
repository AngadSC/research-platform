import { CheckCircle2, CircleAlert, Upload } from "lucide-react";
import { useRef, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { serverDetail } from "@/hooks/instruments";
import { formErrors } from "@/lib/forms";
import { cn } from "@/lib/utils";
import { MAX_BYTES, ParticipantQuestion } from "@/pages/project/UploadDialog";

const NOTICE =
  "Do not upload participant identifiers unless your ethics approval covers them. If a file identifies participants, say so below and AI tools will never see it.";

type Row<T> = {
  key: number;
  name: string;
  progress: number;
  result?: T;
  error?: string;
};

/**
 * Answer the participant question once, then drop or pick files: each is sent at once, in
 * order. `renderDone` shows what happened to a sent file (the signed-in page shows the parse).
 */
export function DropZone<T>({
  send,
  renderDone,
  disabled,
  disabledHint,
}: {
  send: (file: File, participant: boolean, onProgress: (f: number) => void) => Promise<T>;
  renderDone?: (result: T) => ReactNode;
  disabled?: boolean;
  disabledHint?: string;
}) {
  const [choice, setChoice] = useState<boolean | null>(null);
  const [ethics, setEthics] = useState(false);
  const ready = !disabled && choice !== null && (!choice || ethics);
  const [rows, setRows] = useState<Row<T>[]>([]);
  const [over, setOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const queue = useRef(Promise.resolve());
  const next = useRef(0);

  const patch = (key: number, p: Partial<Row<T>>) =>
    setRows((rs) => rs.map((r) => (r.key === key ? { ...r, ...p } : r)));

  function add(list: FileList | null) {
    if (!ready) return;
    const flagged = choice === true;
    for (const file of Array.from(list ?? [])) {
      const key = next.current++;
      const big = file.size > MAX_BYTES;
      setRows((rs) => [
        {
          key,
          name: file.name,
          progress: 0,
          error: big ? `${(file.size / 1048576).toFixed(1)} MB. The limit is 50 MB.` : undefined,
        },
        ...rs,
      ]);
      if (big) continue;
      queue.current = queue.current.then(() =>
        send(file, flagged, (f) => patch(key, { progress: f })).then(
          (result) => patch(key, { progress: 1, result }),
          (e: unknown) => {
            const { fields, form } = formErrors(e, ["file", "acknowledged_notice"]);
            const reason = fields.file ?? fields.acknowledged_notice ?? serverDetail(e) ?? form;
            patch(key, { error: reason ?? "Failed." });
          },
        ),
      );
    }
  }

  const hint = disabled
    ? disabledHint
    : choice === null
      ? "First say whether these files identify participants."
      : choice && !ethics
        ? "Tick the ethics confirmation to send files."
        : undefined;

  return (
    <div className="grid gap-4">
      <p
        role="note"
        className="rounded-md border border-primary/40 bg-primary/10 p-3 text-sm font-medium"
      >
        {NOTICE}
      </p>
      <ParticipantQuestion
        choice={choice}
        onChoice={setChoice}
        ethics={ethics}
        onEthics={setEthics}
      />
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setOver(false);
          add(e.dataTransfer.files);
        }}
        aria-disabled={!ready}
        className={cn(
          "grid place-items-center gap-2 rounded-xl border-2 border-dashed p-10 text-center transition-colors",
          over && ready && "border-primary bg-primary/5",
          !ready && "opacity-60",
        )}
      >
        <Upload aria-hidden className="size-6 text-muted-foreground" />
        <p className="text-sm font-medium">Drag files from the instrument here</p>
        <input
          ref={input}
          type="file"
          multiple
          aria-label="Choose files"
          aria-hidden
          tabIndex={-1}
          className="sr-only"
          onChange={(e) => {
            add(e.target.files);
            e.target.value = "";
          }}
        />
        <Button variant="outline" disabled={!ready} onClick={() => input.current?.click()}>
          Choose files
        </Button>
        <p className="text-xs text-muted-foreground">Up to 50 MB each.</p>
        {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
      </div>
      {rows.length > 0 && (
        <ul className="grid gap-2" aria-label="Files sent" aria-live="polite">
          {rows.map((r) => (
            <li key={r.key} className="grid gap-1 rounded-lg border p-3 text-sm">
              <div className="flex items-center justify-between gap-2">
                <span className="truncate font-medium" title={r.name}>
                  {r.name}
                </span>
                {r.error ? (
                  <span className="flex shrink-0 items-center gap-1 text-destructive">
                    <CircleAlert aria-hidden className="size-4" /> Not sent
                  </span>
                ) : r.result !== undefined ? (
                  <span className="flex shrink-0 items-center gap-1 text-muted-foreground">
                    <CheckCircle2 aria-hidden className="size-4 text-success" /> Sent
                  </span>
                ) : (
                  <progress
                    aria-label={`Sending ${r.name}`}
                    value={r.progress}
                    max={1}
                    className="w-24"
                  />
                )}
              </div>
              {r.error && <p className="text-xs text-destructive">{r.error}</p>}
              {r.result !== undefined && renderDone?.(r.result)}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
