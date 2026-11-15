import { ExternalLink, X } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { FormField } from "@/components/shared/FormField";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useParticipantEvents, useReasons, type useRegistry } from "@/hooks/participants";
import { useMembers } from "@/hooks/workspace";
import type {
  CellStatus,
  RegistryCell,
  RegistryColumn,
  RegistryParticipant,
} from "@/lib/api-types";
import { personName } from "@/lib/api-types";
import { formErrors } from "@/lib/forms";
import { REASON_KIND, STATUS, STATUSES } from "@/lib/participants";
import { NativeSelect } from "@/pages/project/workflow/parts";
import { StatusChip } from "@/pages/project/participants/StatusChip";
import { RelativeTime } from "@/components/shared/RelativeTime";

type Registry = ReturnType<typeof useRegistry>;

function StatusPill({ done }: { done: boolean }) {
  return (
    <span className="rounded-full border px-1.5 text-xs text-muted-foreground">
      {done ? "Done" : "Open"}
    </span>
  );
}

/**
 * The cell's side panel. It sits beside the grid instead of over it (not a modal), so the page
 * stays in view; Escape closes it.
 */
export function CellPanel({
  labId,
  projectId,
  participant,
  column,
  cell,
  registry,
  canEdit,
  initialStatus,
  onClose,
}: {
  labId: string;
  projectId: string;
  participant: RegistryParticipant;
  column: RegistryColumn;
  cell?: RegistryCell;
  registry: Registry;
  canEdit: boolean;
  /** A status chosen by shortcut that still needs its reason. */
  initialStatus?: CellStatus;
  onClose: () => void;
}) {
  const reasons = useReasons(labId).data ?? [];
  const members = useMembers(labId).data ?? [];
  const history = useParticipantEvents(labId, projectId, participant.id).data ?? [];
  const [status, setStatus] = useState<CellStatus>(initialStatus ?? cell?.status ?? "not_started");
  const [reason, setReason] = useState(cell?.reason ?? "");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState(false);
  const [link, setLink] = useState({ url: "", title: "" });
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => heading.current?.focus(), [participant.id, column.id]);

  const kind = REASON_KIND[status];
  const choices = reasons.filter((r) => r.active && r.kind === kind);

  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setErrors({});
    try {
      await registry.setCell.mutateAsync({
        participant: participant.id,
        component: column.id,
        patch: {
          status,
          reason: kind ? reason || null : null,
          owner: String(f.get("owner") ?? "") || null,
          due_date: String(f.get("due_date") ?? "") || null,
          note: String(f.get("note") ?? ""),
        },
      });
      setSaved(true);
    } catch (err) {
      setSaved(false);
      setErrors(formErrors(err, ["status", "reason", "owner", "due_date", "note"]).fields);
      toast.error("Not saved. Check the highlighted fields.");
    }
  }

  async function addLink(e: FormEvent) {
    e.preventDefault();
    try {
      let target = cell;
      if (!target || target.id.startsWith("pending")) {
        target = await registry.setCell.mutateAsync({
          participant: participant.id,
          component: column.id,
          patch: { status: cell?.status ?? "not_started" },
        });
      }
      await registry.addFile.mutateAsync({ cell: target.id, ...link });
      setLink({ url: "", title: "" });
    } catch (err) {
      toast.error(formErrors(err, []).form ?? "Could not add that link.");
    }
  }

  const mine = history.filter((h) => h.component === column.id).slice(0, 8);
  const suggestion = cell?.suggested_status;
  return (
    <aside
      aria-label={`${participant.code}, ${column.name}`}
      onKeyDown={(e) => e.key === "Escape" && onClose()}
      className="flex w-full shrink-0 flex-col gap-4 overflow-y-auto rounded-lg border bg-card p-4 lg:sticky lg:top-4 lg:max-h-[calc(100vh-6rem)] lg:w-80"
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <h2 ref={heading} tabIndex={-1} className="text-base font-semibold outline-none">
            {participant.code}
          </h2>
          <p className="text-sm text-muted-foreground">
            {column.name}
            {participant.group && ` · ${participant.group}`}
          </p>
        </div>
        <Button variant="ghost" size="icon" aria-label="Close panel" onClick={onClose}>
          <X aria-hidden />
        </Button>
      </div>

      {suggestion && cell?.status === "not_started" && canEdit && (
        <div className="rounded-md border border-info bg-info/10 p-3 text-sm">
          There is a link here but nobody has started this.
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="mt-2 w-full"
            onClick={() => setStatus("in_progress")}
          >
            Mark as In progress
          </Button>
        </div>
      )}

      {(cell?.tasks ?? []).length > 0 && (
        <section aria-label="Tasks" className="grid gap-1">
          <h3 className="text-sm font-medium">Tasks</h3>
          <ul className="text-sm">
            {cell!.tasks.map((t) => (
              <li key={t.id} className="flex items-center gap-2">
                <StatusPill done={t.status === "done"} />
                <span className="min-w-0 flex-1 truncate">{t.title}</span>
              </li>
            ))}
          </ul>
          {cell!.tasks.some((t) => t.status === "done") &&
            cell!.status !== "complete" &&
            canEdit && (
              <div className="rounded-md border border-info bg-info/10 p-3 text-sm">
                A task for this is finished. Is the data now complete?
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  className="mt-2 w-full"
                  onClick={() => setStatus("complete")}
                >
                  Set to Complete (then Save)
                </Button>
              </div>
            )}
        </section>
      )}

      {cell?.changed_since_verified && (
        <div role="alert" className="rounded-md border border-warning bg-warning/15 p-3 text-sm">
          A linked document was edited after this was marked complete.
          {canEdit && (
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="mt-2 w-full"
              onClick={() =>
                registry.setCell.mutate({
                  participant: participant.id,
                  component: column.id,
                  patch: { verified: true },
                })
              }
            >
              I checked it again
            </Button>
          )}
        </div>
      )}

      <form onSubmit={(e) => void save(e)} className="grid gap-3" key={cell?.updated_at}>
        <FormField label="Status" error={errors.status} hint={STATUS[status].hint}>
          {(p) => (
            <NativeSelect
              {...p}
              value={status}
              disabled={!canEdit}
              onChange={(e) => {
                setStatus(e.target.value as CellStatus);
                setReason("");
                setSaved(false);
              }}
            >
              {STATUSES.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.key}. {s.label}
                </option>
              ))}
            </NativeSelect>
          )}
        </FormField>
        {kind && (
          <FormField label="Reason" required error={errors.reason}>
            {(p) => (
              <NativeSelect
                {...p}
                value={reason}
                disabled={!canEdit}
                onChange={(e) => setReason(e.target.value)}
              >
                <option value="">Choose a reason…</option>
                {choices.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.label}
                  </option>
                ))}
              </NativeSelect>
            )}
          </FormField>
        )}
        <FormField label="Owner" error={errors.owner}>
          {(p) => (
            <NativeSelect {...p} name="owner" defaultValue={cell?.owner ?? ""} disabled={!canEdit}>
              <option value="">Unassigned</option>
              {members.map((m) => (
                <option key={m.id} value={m.user.id}>
                  {personName(m.user)}
                </option>
              ))}
            </NativeSelect>
          )}
        </FormField>
        <FormField label="Due date" error={errors.due_date}>
          {(p) => (
            <Input
              {...p}
              type="date"
              name="due_date"
              defaultValue={cell?.due_date ?? ""}
              disabled={!canEdit}
            />
          )}
        </FormField>
        <FormField
          label="Note"
          error={errors.note}
          hint="Coded IDs only. Do not enter names or contact details."
        >
          {(p) => (
            <Textarea
              {...p}
              name="note"
              rows={3}
              maxLength={1000}
              defaultValue={cell?.note}
              disabled={!canEdit}
            />
          )}
        </FormField>
        {canEdit && (
          <div className="flex items-center gap-3">
            <Button type="submit" disabled={registry.setCell.isPending}>
              Save
            </Button>
            <span role="status" className="text-sm text-muted-foreground">
              {registry.setCell.isPending ? "Saving…" : saved ? "Saved" : ""}
            </span>
          </div>
        )}
      </form>

      <section aria-label="Linked files" className="grid gap-2">
        <h3 className="text-sm font-medium">Links</h3>
        {(cell?.files ?? []).length === 0 && (
          <p className="text-sm text-muted-foreground">
            No links yet. Paste the Google Doc or Drive address below.
          </p>
        )}
        <ul className="grid gap-1">
          {(cell?.files ?? []).map((f) => (
            <li key={f.id} className="flex items-center gap-2 text-sm">
              <a
                href={f.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex min-w-0 flex-1 items-center gap-1 underline"
              >
                <ExternalLink aria-hidden className="size-3.5 shrink-0" />
                <span className="truncate">{f.title || f.url}</span>
              </a>
              {f.link_state !== "ok" && f.link_state !== "unchecked" && (
                <span className="text-xs text-danger-text">{f.link_state.replace("_", " ")}</span>
              )}
              {canEdit && (
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label={`Remove link ${f.title || f.url}`}
                  onClick={() => registry.removeFile.mutate(f.id)}
                >
                  Remove
                </Button>
              )}
            </li>
          ))}
        </ul>
        {canEdit && (
          <form onSubmit={(e) => void addLink(e)} className="grid gap-2">
            <FormField label="Link address">
              {(p) => (
                <Input
                  {...p}
                  type="url"
                  required
                  placeholder="https://docs.google.com/…"
                  value={link.url}
                  onChange={(e) => setLink({ ...link, url: e.target.value })}
                />
              )}
            </FormField>
            <FormField label="Link title (optional)">
              {(p) => (
                <Input
                  {...p}
                  maxLength={300}
                  value={link.title}
                  onChange={(e) => setLink({ ...link, title: e.target.value })}
                />
              )}
            </FormField>
            <Button type="submit" variant="outline" size="sm">
              Add link
            </Button>
          </form>
        )}
      </section>

      <section aria-label="History" className="grid gap-1">
        <h3 className="text-sm font-medium">History</h3>
        {mine.length === 0 && <p className="text-sm text-muted-foreground">No changes yet.</p>}
        <ul className="grid gap-1 text-sm">
          {mine.map((h) => (
            <li key={h.id} className="flex flex-wrap items-center gap-1">
              {h.from_value && <StatusChip status={h.from_value as CellStatus} compact />}
              {h.from_value && <span aria-hidden>→</span>}
              {h.to_value && <StatusChip status={h.to_value as CellStatus} compact />}
              <RelativeTime value={h.created_at} className="text-xs text-muted-foreground" />
            </li>
          ))}
        </ul>
      </section>
    </aside>
  );
}
