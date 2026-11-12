import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import type { PendingCall } from "@/hooks/assistant";

/** Shows a value the way a person reads it: text as is, anything else as compact JSON. */
const show = (v: unknown) => (typeof v === "string" ? v : JSON.stringify(v));

/** Argument ids the server resolves to names (D198): [key in `resolved`, label]. */
const IDS: Record<string, [string, string]> = {
  lab_id: ["lab", "Lab"],
  project_id: ["project", "Project"],
  task_id: ["task", "Task"],
  assignee_id: ["person", "Assign to"],
  folder_id: ["folder", "Folder"],
  analysis_id: ["analysis", "Analysis"],
  file_id: ["file", "File"],
};

/** The rows of one action: names instead of ids, then every other argument not already shown in
 * the text preview. A name the server could not resolve is flagged, never hidden. */
function rows(c: PendingCall): { label: string; value: string; unknown?: boolean }[] {
  const resolved = c.resolved ?? {};
  const previewed = new Set((c.preview ?? []).map((p) => p.text));
  const out: { label: string; value: string; unknown?: boolean }[] = [];
  for (const [k, v] of Object.entries(c.arguments)) {
    const id = IDS[k];
    if (id) {
      const name = resolved[id[0]];
      out.push({
        label: id[1],
        value: name ?? show(v),
        unknown: name?.startsWith("(not found"),
      });
    } else if (!previewed.has(show(v))) out.push({ label: k, value: show(v) });
  }
  if (resolved.project && !("project_id" in c.arguments))
    out.unshift({ label: "Project", value: resolved.project });
  return out;
}

/**
 * Write actions never run on their own (D190). The assistant stops, this dialog names each
 * action and its exact arguments, and nothing happens until "Approve" is clicked. "Decline" (or
 * closing the dialog and typing something else) tells the assistant the person said no.
 */
export function ApprovalDialog({
  calls,
  open,
  busy,
  onApprove,
  onDecline,
  onClose,
}: {
  calls: PendingCall[];
  open: boolean;
  busy: boolean;
  onApprove: () => void;
  onDecline: () => void;
  onClose: () => void;
}) {
  return (
    <Dialog open={open && calls.length > 0} onOpenChange={(o) => !o && onClose()}>
      <DialogContent aria-describedby="approval-help">
        <DialogTitle>
          {calls.length === 1 ? "Approve this action?" : `Approve these ${calls.length} actions?`}
        </DialogTitle>
        <DialogDescription id="approval-help">
          The assistant wants to change your lab&apos;s records. It runs as you, with your
          permissions, and is recorded in the audit log. Nothing happens until you approve. Read the
          text below: it may be based on something the assistant read in your records.
        </DialogDescription>
        <ul className="grid gap-3" aria-label="Actions waiting for approval">
          {calls.map((c) => (
            <li key={c.id} className="rounded-md border p-3">
              <p className="text-sm font-medium">{c.title}</p>
              <p className="text-xs text-muted-foreground">
                Tool: <code>{c.name}</code>
              </p>
              <dl className="mt-2 grid gap-1 text-sm">
                {rows(c).map((r) => (
                  <div key={r.label} className="grid grid-cols-[8rem_1fr] gap-2">
                    <dt className="truncate text-muted-foreground">{r.label}</dt>
                    <dd
                      className={
                        r.unknown ? "break-words font-medium text-danger-text" : "break-words"
                      }
                    >
                      {r.value}
                    </dd>
                  </div>
                ))}
              </dl>
              {(c.preview ?? []).map((p) => (
                <figure key={p.label} className="mt-2">
                  <figcaption className="text-xs font-medium text-muted-foreground">
                    {p.label}
                  </figcaption>
                  <blockquote className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap break-words rounded border bg-muted/40 p-2 text-sm">
                    {p.text}
                  </blockquote>
                </figure>
              ))}
            </li>
          ))}
        </ul>
        <div className="flex justify-end gap-2">
          <Button variant="outline" disabled={busy} onClick={onDecline}>
            Decline
          </Button>
          <Button disabled={busy} onClick={onApprove}>
            Approve
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
