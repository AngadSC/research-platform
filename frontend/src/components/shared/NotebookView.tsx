import { Download, FileText, Lock, Pencil, Plus, Trash2 } from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";
import { toast } from "sonner";
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
import { Textarea } from "@/components/ui/textarea";
import { useNotebook, type ExportFormat } from "@/hooks/notebook";
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

function EntryDialog({
  entry,
  onClose,
  onSave,
}: {
  entry: NotebookEntry | null;
  onClose: () => void;
  onSave: (v: { title: string; entry_date: string; body: string }) => Promise<unknown>;
}) {
  const [errors, setErrors] = useState<FormErrors>({ fields: {} });
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
      <DialogContent className="max-h-[92vh] max-w-2xl overflow-y-auto">
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
                  placeholder="Western blot, day 2"
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
                name="body"
                rows={14}
                className="font-mono text-sm"
                placeholder={"Aim\n\nMethod\n\nResult\n\nNext steps"}
                defaultValue={entry?.body}
              />
            )}
          </FormField>
          <FormError message={errors.form} />
          <div className="flex justify-end gap-2">
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
  const [adding, setAdding] = useState(false);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [q, setQ] = useState("");
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
                      onClick={() => {
                        if (window.confirm("Delete this entry?"))
                          nb.remove.mutate(e.id, {
                            onSuccess: () => toast.success("Deleted"),
                            onError: fail,
                          });
                      }}
                    >
                      <Trash2 aria-hidden /> Delete
                    </Button>
                  </div>
                )}
              </div>
              {e.body && <p className="mt-3 text-sm break-words whitespace-pre-wrap">{e.body}</p>}
            </li>
          ))}
        </ol>
      )}

      {(adding || editing) && (
        <EntryDialog
          key={editing?.id ?? "new"}
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
    </div>
  );
}
