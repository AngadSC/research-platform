import {
  Beaker,
  Download,
  FileText,
  FlaskConical,
  Lock,
  Pencil,
  Plus,
  Trash2,
  TriangleAlert,
} from "lucide-react";
import { useMemo, useRef, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { ConfirmDelete } from "@/components/shared/ConfirmDelete";
import { EmptyState } from "@/components/shared/EmptyState";
import { FormError } from "@/components/shared/FormError";
import { FormField } from "@/components/shared/FormField";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useEntryHints, useNotebook, type ExportFormat } from "@/hooks/notebook";
import { useProtocols } from "@/hooks/admin";
import { useProjects } from "@/hooks/projects";
import { trimNumber } from "@/lib/units";
import { NativeSelect } from "@/pages/admin/common";
import type { NotebookEntry } from "@/lib/api-types";
import { shortDate } from "@/lib/dashboard";
import { localDateISO } from "@/lib/format";
import { formErrors, type FormErrors } from "@/lib/forms";
import { formValue } from "@/pages/admin/common";

const EXPORTS: { fmt: ExportFormat; label: string; hint: string }[] = [
  { fmt: "md", label: "Markdown (.md)", hint: "Plain text that opens anywhere" },
  { fmt: "html", label: "Web page (.html)", hint: "Open it, then Print and Save as PDF" },
  { fmt: "json", label: "Data (.json)", hint: "For other software" },
];

/** Pick a protocol and paste it into the entry as text: its name and each reagent with its
 * amount, so the entry records what was actually planned. */
function InsertProtocol({
  labId,
  projectId,
  onInsert,
}: {
  labId: string;
  projectId?: string;
  onInsert: (text: string) => void;
}) {
  const projects = useProjects(labId).data ?? [];
  const [pick, setPick] = useState(projectId ?? "");
  const { list } = useProtocols(labId, pick);
  const [protocol, setProtocol] = useState("");
  const chosen = (list.data ?? []).find((p) => p.id === protocol);
  return (
    <fieldset className="grid gap-2 rounded-lg border p-3">
      <legend className="px-1 text-sm font-medium">Insert a protocol</legend>
      <div className="flex flex-wrap items-end gap-2">
        {!projectId && (
          <label className="grid gap-0.5 text-xs text-muted-foreground">
            Project
            <NativeSelect
              aria-label="Project to take a protocol from"
              value={pick}
              onChange={(e) => {
                setPick(e.target.value);
                setProtocol("");
              }}
            >
              <option value="">Choose a project</option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </NativeSelect>
          </label>
        )}
        <label className="grid gap-0.5 text-xs text-muted-foreground">
          Protocol
          <NativeSelect
            aria-label="Protocol to insert"
            value={protocol}
            disabled={!pick}
            onChange={(e) => setProtocol(e.target.value)}
          >
            <option value="">{pick ? "Choose a protocol" : "Pick a project first"}</option>
            {(list.data ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </NativeSelect>
        </label>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={!chosen}
          onClick={() =>
            chosen &&
            onInsert(
              `Protocol: ${chosen.name}\n${chosen.reagents
                .map((r) => `- ${trimNumber(r.amount)} ${r.unit} ${r.item_name}`.replace("  ", " "))
                .join("\n")}\n`,
            )
          }
        >
          <FlaskConical aria-hidden /> Insert
        </Button>
      </div>
    </fieldset>
  );
}

/** What an entry says about inventory: amounts of known items you can log with a click, uses that
 * may already be logged, and amounts that differ from the protocol the entry names (D332). */
function EntryHints({
  labId,
  projectId,
  entry,
}: {
  labId: string;
  projectId?: string;
  entry: NotebookEntry;
}) {
  const { hints, take } = useEntryHints(labId, projectId, entry.id, true);
  const data = hints.data;
  if (hints.isLoading) return <Skeleton aria-label="Reading the entry" className="h-12 w-full" />;
  if (!data || (data.uses.length === 0 && data.protocol_changes.length === 0))
    return (
      <p className="text-sm text-muted-foreground">
        Nothing to log. Amounts like "10 mL ethanol", written with an item from the inventory, show
        up here.
      </p>
    );
  return (
    <div className="grid gap-2">
      {data.uses.length > 0 && (
        <ul aria-label="Inventory in this entry" className="grid gap-1.5">
          {data.uses.map((h) => (
            <li
              key={h.request_id}
              className="flex flex-wrap items-center gap-2 rounded-md border bg-muted/40 px-3 py-2 text-sm"
            >
              <Beaker aria-hidden className="size-4 text-primary" />
              <span className="font-medium">
                {trimNumber(h.amount)} {h.unit} {h.item_name}
              </span>
              <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground">
                “{h.snippet}”
              </span>
              {h.status === "logged" && (
                <span className="text-xs font-medium text-success-text">Logged</span>
              )}
              {h.status === "reversed" && (
                <span className="text-xs text-muted-foreground">Logged, then undone</span>
              )}
              {h.status === "not_enough" && (
                <span className="text-xs font-medium text-danger-text">
                  Only {trimNumber(h.stock)} {h.item_unit} in stock
                </span>
              )}
              {h.status === "possible_duplicate" && (
                <span className="inline-flex items-center gap-1 text-xs font-medium text-warning-text">
                  <TriangleAlert aria-hidden className="size-3" /> May already be logged
                </span>
              )}
              {(h.status === "new" || h.status === "possible_duplicate") && (
                <Button
                  size="sm"
                  variant={h.status === "new" ? "secondary" : "outline"}
                  aria-label={`Log ${h.amount} ${h.unit} ${h.item_name} from this entry`}
                  disabled={take.isPending}
                  onClick={() =>
                    take.mutate(
                      { hint: h, title: entry.title },
                      {
                        onSuccess: () =>
                          toast.success(`Took ${h.amount} ${h.unit} of ${h.item_name}`),
                        onError: (e) =>
                          toast.error(formErrors(e, []).form ?? "Could not take that from stock."),
                      },
                    )
                  }
                >
                  {h.status === "new" ? "Take from stock" : "Take anyway"}
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
      {data.protocol_changes.length > 0 && (
        <ul aria-label="Differences from the protocol" className="grid gap-1.5">
          {data.protocol_changes.map((c, i) => (
            <li
              key={i}
              className="flex items-center gap-2 rounded-md border border-warning/50 bg-warning/10 px-3 py-2 text-sm"
            >
              <TriangleAlert aria-hidden className="size-4 text-warning-text" />
              <span>
                {c.item_name}: the entry says <strong>{c.noted_amount}</strong>, the protocol “
                {c.protocol}” says <strong>{c.protocol_amount}</strong>. Update the protocol if this
                is the new way.
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function EntryDialog({
  labId,
  projectId,
  entry,
  onClose,
  onSave,
}: {
  labId: string;
  projectId?: string;
  entry: NotebookEntry | null;
  onClose: () => void;
  onSave: (v: { title: string; entry_date: string; body: string }) => Promise<unknown>;
}) {
  const [errors, setErrors] = useState<FormErrors>({ fields: {} });
  const bodyRef = useRef<HTMLTextAreaElement>(null);
  const insert = (text: string) => {
    const box = bodyRef.current;
    if (!box) return;
    const at = box.selectionStart ?? box.value.length;
    box.value = `${box.value.slice(0, at)}${at > 0 && !box.value.slice(0, at).endsWith("\n") ? "\n" : ""}${text}${box.value.slice(at)}`;
    box.focus();
  };
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const v = (k: string) => formValue(fd, k);
    if (!v("title")) return setErrors({ fields: { title: "Give the entry a title" } });
    try {
      await onSave({
        title: v("title"),
        entry_date: v("entry_date") || localDateISO(),
        body: String(fd.get("body") ?? ""),
      });
      onClose();
    } catch (err) {
      setErrors(formErrors(err, ["title", "entry_date", "body"]));
    }
  }
  const f = errors.fields;
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[92dvh] max-w-2xl overflow-y-auto">
        <DialogTitle className="text-base font-semibold">
          {entry ? "Edit entry" : "New entry"}
        </DialogTitle>
        <DialogDescription className="text-sm text-muted-foreground">
          Write what you did, what you saw and what comes next. Keep names of participants out.
        </DialogDescription>
        <form onSubmit={submit} noValidate className="grid gap-3">
          <div className="grid gap-3 sm:grid-cols-[1fr_11rem]">
            <FormField label="Title" error={f.title}>
              {(p) => (
                <Input
                  {...p}
                  name="title"
                  maxLength={200}
                  autoFocus
                  placeholder="Pilot session 3 notes"
                  defaultValue={entry?.title}
                />
              )}
            </FormField>
            <FormField label="Date" error={f.entry_date}>
              {(p) => (
                <Input
                  {...p}
                  name="entry_date"
                  type="date"
                  defaultValue={entry?.entry_date ?? localDateISO()}
                />
              )}
            </FormField>
          </div>
          <FormField label="Entry" error={f.body}>
            {(p) => (
              <Textarea
                {...p}
                ref={bodyRef}
                name="body"
                rows={14}
                className="font-mono text-sm"
                defaultValue={entry ? entry.body : "Aim\n\n\nMethod\n\n\nResult\n\n\nNext steps\n"}
              />
            )}
          </FormField>
          <InsertProtocol labId={labId} projectId={projectId} onInsert={insert} />
          <FormError message={errors.form} />
          <div className="sticky -bottom-6 z-10 -mx-1 flex justify-end gap-2 bg-background px-1 py-3">
            <DialogClose asChild>
              <Button type="button" variant="outline">
                Cancel
              </Button>
            </DialogClose>
            <Button type="submit">Save</Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** A notebook: dated entries you can write, lock as a signed record, and export (D330). The same
 * view serves a person's own notebook and a project's shared one. */
export function NotebookView({
  labId,
  projectId,
  canWrite,
}: {
  labId: string;
  projectId?: string;
  canWrite: boolean;
}) {
  const nb = useNotebook(labId, projectId);
  const [editing, setEditing] = useState<NotebookEntry | null>(null);
  const [deleting, setDeleting] = useState<NotebookEntry | null>(null);
  const [adding, setAdding] = useState(false);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [q, setQ] = useState("");
  const [checking, setChecking] = useState<string | null>(null);
  const rows = useMemo(() => {
    const t = q.trim().toLowerCase();
    return (nb.list.data ?? []).filter(
      (e) => !t || e.title.toLowerCase().includes(t) || e.body.toLowerCase().includes(t),
    );
  }, [nb.list.data, q]);

  const fail = (e: unknown) => toast.error(formErrors(e, []).form ?? "Something went wrong.");

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="w-full sm:w-64">
          <Input
            type="search"
            aria-label="Search this notebook"
            placeholder="Search entries"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline">
                <Download aria-hidden /> Export
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-72">
              <DropdownMenuLabel>Export the whole notebook, or a range</DropdownMenuLabel>
              <div className="grid grid-cols-2 gap-2 px-2 pb-2">
                <label className="grid gap-0.5 text-xs text-muted-foreground">
                  From
                  <Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
                </label>
                <label className="grid gap-0.5 text-xs text-muted-foreground">
                  To
                  <Input type="date" value={to} onChange={(e) => setTo(e.target.value)} />
                </label>
              </div>
              {EXPORTS.map((x) => (
                <DropdownMenuItem key={x.fmt} asChild>
                  <a
                    href={nb.exportUrl(x.fmt, from, to)}
                    target={x.fmt === "html" ? "_blank" : undefined}
                    rel="noopener"
                    download={x.fmt === "html" ? undefined : ""}
                    className="grid gap-0"
                  >
                    <span className="flex items-center gap-2 font-medium">
                      <FileText aria-hidden className="size-4" /> {x.label}
                    </span>
                    <span className="pl-6 text-xs text-muted-foreground">{x.hint}</span>
                  </a>
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
          {canWrite && (
            <Button onClick={() => setAdding(true)}>
              <Plus aria-hidden /> New entry
            </Button>
          )}
        </div>
      </div>

      {rows.length === 0 ? (
        <EmptyState
          icon={FileText}
          title={nb.list.data?.length ? "No entries match that search" : "No entries yet"}
          description={
            projectId
              ? "The project's shared notebook: everyone on the project can read it, and anyone who can edit can add to it."
              : "Your own notebook. Only you can read it. Write up experiments as you go, then export it when you need a copy."
          }
          why="Dated entries you can lock make a clear record of what was done, and when."
          action={
            canWrite && !nb.list.data?.length ? (
              <Button onClick={() => setAdding(true)}>
                <Plus aria-hidden /> New entry
              </Button>
            ) : undefined
          }
        />
      ) : (
        <ol className="grid gap-3" aria-label="Entries">
          {rows.map((e) => (
            <li key={e.id} className="rounded-2xl border bg-card p-5 shadow-sm">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <h2 className="flex items-center gap-2 text-base font-semibold">
                    {e.title}
                    {e.locked_at && (
                      <span
                        title={`Locked ${shortDate(e.locked_at.slice(0, 10))}`}
                        className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground"
                      >
                        <Lock aria-hidden className="size-3" /> Locked
                      </span>
                    )}
                  </h2>
                  <p className="text-xs text-muted-foreground">
                    {shortDate(e.entry_date)}
                    {projectId && ` · ${e.author.display_name || e.author.email}`}
                    {e.locked_by && ` · locked by ${e.locked_by.display_name || e.locked_by.email}`}
                  </p>
                </div>
                {canWrite && e.can_edit && (
                  <div className="flex gap-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      aria-label={`Edit ${e.title}`}
                      onClick={() => setEditing(e)}
                    >
                      <Pencil aria-hidden /> Edit
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      aria-label={`Lock ${e.title}`}
                      title="Lock it as a signed record. It can no longer be changed or deleted."
                      onClick={() => {
                        if (
                          window.confirm(
                            "Lock this entry? It becomes a signed record that nobody can change or delete.",
                          )
                        )
                          nb.lock.mutate(e.id, {
                            onSuccess: () => toast.success("Locked"),
                            onError: fail,
                          });
                      }}
                    >
                      <Lock aria-hidden /> Lock
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      aria-label={`Delete ${e.title}`}
                      className="text-danger-text hover:bg-danger/10 hover:text-danger-text"
                      onClick={() => setDeleting(e)}
                    >
                      <Trash2 aria-hidden /> Delete
                    </Button>
                  </div>
                )}
              </div>
              {e.body && <p className="mt-3 text-sm break-words whitespace-pre-wrap">{e.body}</p>}
              {e.body && (
                <div className="mt-3 grid gap-2 border-t pt-3">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="w-fit"
                    aria-expanded={checking === e.id}
                    title="Finds amounts of inventory items you wrote down, so you can take them from stock"
                    onClick={() => setChecking(checking === e.id ? null : e.id)}
                  >
                    <Beaker aria-hidden />{" "}
                    {checking === e.id ? "Hide inventory" : "Check inventory"}
                  </Button>
                  {checking === e.id && (
                    <EntryHints labId={labId} projectId={projectId} entry={e} />
                  )}
                </div>
              )}
            </li>
          ))}
        </ol>
      )}

      {(adding || editing) && (
        <EntryDialog
          key={editing?.id ?? "new"}
          labId={labId}
          projectId={projectId}
          entry={editing}
          onClose={() => {
            setAdding(false);
            setEditing(null);
          }}
          onSave={async (v) => {
            if (editing) await nb.update.mutateAsync({ id: editing.id, patch: v });
            else await nb.create.mutateAsync(v);
            toast.success(editing ? "Saved" : "Added");
          }}
        />
      )}
      <ConfirmDelete
        open={!!deleting}
        name={deleting?.title ?? ""}
        noun="entry"
        description="The entry is removed from the notebook."
        pending={nb.remove.isPending}
        onClose={() => setDeleting(null)}
        onConfirm={() =>
          deleting &&
          nb.remove.mutate(deleting.id, {
            onSuccess: () => {
              toast.success("Deleted");
              setDeleting(null);
            },
            onError: fail,
          })
        }
      />
    </div>
  );
}
