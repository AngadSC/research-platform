import { FileSearch } from "lucide-react";
import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { fillBlank, readForm, type FormKind } from "@/lib/formReader";
import { formErrors } from "@/lib/forms";

const HELP: Record<FormKind, string> = {
  ethics: "an ethics approval letter or certificate",
  funding: "a grant or award letter",
};

/** "Fill in from the form": reads a PDF (or text file) the person has, puts what it finds into
 * the empty fields of the form around it, and says what it filled. It only suggests; the person
 * checks and saves. The file is read and dropped here, not stored. */
export function FormReader({
  labId,
  kind,
  onRead,
}: {
  labId: string;
  kind: FormKind;
  /** Called with each file that was read, for a caller that also wants to keep it. */
  onRead?: (file: File) => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; ok: boolean }>();

  async function pick(file: File | undefined) {
    if (!file) return;
    setBusy(true);
    setMessage(undefined);
    try {
      const fields = await readForm(labId, kind, file);
      const form = box.current?.closest("form");
      const filled = form ? fillBlank(form, fields) : [];
      onRead?.(file);
      setMessage(
        filled.length
          ? { ok: true, text: `Filled in: ${filled.join(", ")}. Check each one before saving.` }
          : {
              ok: false,
              text: "Nothing could be read from that file, or those fields are already filled in. Fill the rest in by hand.",
            },
      );
    } catch (e) {
      setMessage({
        ok: false,
        text:
          formErrors(e, ["file"]).fields.file ??
          formErrors(e, ["file"]).form ??
          "That file could not be read.",
      });
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  }

  return (
    <div ref={box} className="grid gap-2 rounded-lg border border-dashed bg-muted/30 p-3 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span>Have {HELP[kind]}? Add it and we will fill in what we can find.</span>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={busy}
          onClick={() => input.current?.click()}
        >
          <FileSearch aria-hidden /> {busy ? "Reading…" : "Fill in from a form"}
        </Button>
      </div>
      <input
        ref={input}
        type="file"
        accept=".pdf,.txt,application/pdf,text/plain"
        aria-label="Form to read"
        className="sr-only"
        tabIndex={-1}
        onChange={(e) => void pick(e.target.files?.[0])}
      />
      <p className="text-xs text-muted-foreground">
        Only PDF or text files. It is read on our server and not kept or shared.
      </p>
      {message && (
        <p role="status" className={message.ok ? "text-xs" : "text-xs text-destructive"}>
          {message.text}
        </p>
      )}
    </div>
  );
}
