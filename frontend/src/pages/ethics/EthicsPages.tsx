import { Download, Eye, FileCheck2, Lock, Pencil, Trash2, Upload } from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { toast } from "sonner";
import { ApprovalBadge, ExpiryText } from "@/components/ethics/ApprovalBadge";
import { DataTable, type Column } from "@/components/shared/DataTable";
import { EmptyState } from "@/components/shared/EmptyState";
import { FormError } from "@/components/shared/FormError";
import { FormField } from "@/components/shared/FormField";
import { PageHeader } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useApproval,
  useApprovals,
  useApprovalUpload,
  useDeleteApproval,
  useSaveApproval,
} from "@/hooks/ethics";
import { downloadUrl, useProjects } from "@/hooks/projects";
import { useLab } from "@/hooks/workspace";
import type { Attachment, EthicsApproval } from "@/lib/api-types";
import { APPROVAL_STATUSES, dayText, validateApproval, type ApprovalValues } from "@/lib/ethics";
import { formErrors } from "@/lib/forms";
import { UploadDialog } from "@/pages/project/UploadDialog";

const selectCls =
  "flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none";
const isPdf = (a: Attachment) =>
  a.content_type === "application/pdf" || a.original_filename.toLowerCase().endsWith(".pdf");

function useCan(labId: string, perm: string) {
  const { data: lab } = useLab(labId);
  return lab?.my_permissions.includes(perm) ?? false;
}

export function EthicsListPage() {
  const { labId = "" } = useParams();
  const navigate = useNavigate();
  const canEdit = useCan(labId, "edit_ethics");
  const { data, isLoading } = useApprovals(labId);
  const add = canEdit ? (
    <Button asChild>
      <Link to="new">New approval</Link>
    </Button>
  ) : undefined;
  const cols: Column<EthicsApproval>[] = [
    {
      key: "n",
      header: "Number",
      cell: (a) => (
        <span className="font-medium">
          {a.approval_number}
          {a.restricted && <RestrictedBadge />}
        </span>
      ),
    },
    { key: "t", header: "Title", cell: (a) => a.title },
    { key: "b", header: "Board", cell: (a) => a.board },
    {
      key: "e",
      header: "Expires",
      cell: (a) => (
        <div className="grid">
          <span>{dayText(a.expiry_date)}</span>
          <ExpiryText expiry={a.expiry_date} />
        </div>
      ),
    },
    {
      key: "s",
      header: "Status",
      cell: (a) => <ApprovalBadge status={a.status} expiry={a.expiry_date} />,
    },
  ];
  return (
    <div>
      <PageHeader
        title="Ethics approvals"
        description="Approvals from your ethics board, with their expiry dates and linked projects."
        actions={add}
      />
      <DataTable
        columns={cols}
        rows={data ?? []}
        getRowKey={(a) => a.id}
        loading={isLoading}
        onRowClick={(a) => void navigate(a.id)}
        empty={
          <EmptyState
            icon={FileCheck2}
            title="No ethics approvals yet"
            description="Add an approval to track when it expires and which projects it covers. You will get a reminder before it runs out."
            action={add}
          />
        }
      />
    </div>
  );
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-sm">{children}</dd>
    </div>
  );
}

export function EthicsDetailPage() {
  const { labId = "", approvalId = "" } = useParams();
  const navigate = useNavigate();
  const canEdit = useCan(labId, "edit_ethics");
  const { data: a, error } = useApproval(labId, approvalId);
  const send = useApprovalUpload(labId, approvalId);
  const del = useDeleteApproval(labId, approvalId);
  const [uploading, setUploading] = useState(false);
  const [deleting, setDeleting] = useState(false);
  if (error) return <FormError message={formErrors(error, []).form} />;
  if (!a) return <Skeleton aria-label="Loading" className="h-40 w-full" />;
  return (
    // PageHeader already has mb-8, so drop it here to avoid a 64px gap under the title.
    <div className="grid gap-8 [&>header]:mb-0">
      <PageHeader
        title={a.title}
        description={`${a.board}, ${a.approval_number}${a.restricted ? " (restricted)" : ""}`}
        actions={
          canEdit && (
            <>
              <Button variant="outline" asChild>
                <Link to="edit">
                  <Pencil aria-hidden /> Edit
                </Link>
              </Button>
              <Button variant="outline" onClick={() => setDeleting(true)}>
                <Trash2 aria-hidden /> Delete
              </Button>
            </>
          )
        }
      />
      <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Fact label="Status">
          <ApprovalBadge status={a.status} expiry={a.expiry_date} />
        </Fact>
        <Fact label="Approved on">{dayText(a.approval_date)}</Fact>
        <Fact label="Expires on">{dayText(a.expiry_date)}</Fact>
        <Fact label="Time left">
          <ExpiryText expiry={a.expiry_date} />
        </Fact>
      </dl>
      <section className="grid gap-2">
        <h2 className="text-base font-semibold">Projects covered</h2>
        {a.projects.length === 0 ? (
          <p className="text-sm text-muted-foreground">No projects you can see are linked.</p>
        ) : (
          <ul className="grid gap-1 text-sm">
            {a.projects.map((p) => (
              <li key={p.id}>
                <Link
                  className="text-primary hover:underline"
                  to={`/labs/${labId}/projects/${p.id}`}
                >
                  {p.name}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
      <section className="grid gap-3">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold">Documents</h2>
          {canEdit && a.can_view_files && (
            <Button variant="outline" size="sm" onClick={() => setUploading(true)}>
              <Upload aria-hidden /> Upload file
            </Button>
          )}
        </div>
        {!a.can_view_files ? (
          <p className="text-sm text-muted-foreground">
            You can&apos;t open files for this approval. Ask the PI or a lab admin.
          </p>
        ) : a.attachments.length === 0 ? (
          <p className="text-sm text-muted-foreground">No documents attached yet.</p>
        ) : (
          <ul className="grid divide-y rounded-lg border">
            {a.attachments.map((f) => (
              <li key={f.id} className="flex items-center justify-between px-3 py-2 text-sm">
                <span className="font-medium">{f.original_filename}</span>
                <span className="flex gap-1">
                  {isPdf(f) && (
                    <Button variant="ghost" size="sm" asChild>
                      <Link to={`files/${f.id}`} aria-label={`Open ${f.original_filename}`}>
                        <Eye aria-hidden />
                      </Link>
                    </Button>
                  )}
                  <Button variant="ghost" size="sm" asChild>
                    <a
                      href={downloadUrl(labId, f.id)}
                      download
                      aria-label={`Download ${f.original_filename}`}
                    >
                      <Download aria-hidden />
                    </a>
                  </Button>
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
      <UploadDialog
        open={uploading}
        onOpenChange={setUploading}
        send={(file, onProgress) => send.mutateAsync({ file, onProgress })}
      />
      <Dialog open={deleting} onOpenChange={setDeleting}>
        <DialogContent>
          <DialogTitle className="text-base font-semibold">Delete {a.approval_number}?</DialogTitle>
          <DialogDescription className="text-sm text-muted-foreground">
            The approval and its documents will be removed.
          </DialogDescription>
          <div className="flex justify-end gap-2">
            <DialogClose asChild>
              <Button variant="outline">Cancel</Button>
            </DialogClose>
            <Button
              variant="destructive"
              disabled={del.isPending}
              onClick={() =>
                del.mutate(undefined, {
                  onSuccess: () => {
                    toast.success("Approval deleted");
                    void navigate(`/labs/${labId}/ethics`);
                  },
                  onError: (e) => toast.error(formErrors(e, []).form ?? "Something went wrong."),
                })
              }
            >
              Delete approval
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function RestrictedBadge() {
  return (
    <span
      className="ml-2 inline-flex items-center gap-1 text-xs font-normal text-muted-foreground"
      title="Restricted: only people on linked projects can see this"
    >
      <Lock className="size-3" aria-hidden="true" />
      Restricted
    </span>
  );
}

const FIELDS = ["approval_number", "board", "title", "approval_date", "expiry_date", "status"];

/** Create (no approvalId in the route) or edit. */
export function EthicsFormPage() {
  const { labId = "", approvalId } = useParams();
  const { data: lab } = useLab(labId);
  const { data: existing, error } = useApproval(labId, approvalId);
  if (!lab) return <Skeleton aria-label="Loading" className="h-40 w-full" />;
  // A pasted link must not show a form the server will refuse (viewers lack edit_ethics).
  if (!lab.my_permissions.includes("edit_ethics"))
    return (
      <EmptyState
        icon={Lock}
        title="You can't add or edit ethics approvals"
        description="Ask a PI or lab admin if something here needs changing."
      />
    );
  if (approvalId && error) return <FormError message={formErrors(error, []).form} />;
  if (approvalId && !existing) return <Skeleton aria-label="Loading" className="h-40 w-full" />;
  return <ApprovalForm key={existing?.id} labId={labId} approval={existing} />;
}

export function ApprovalForm({ labId, approval }: { labId: string; approval?: EthicsApproval }) {
  const navigate = useNavigate();
  const save = useSaveApproval(labId, approval?.id);
  const { data: projects = [] } = useProjects(labId);
  const [linked, setLinked] = useState<string[]>(approval?.projects.map((p) => p.id) ?? []);
  const [status, setStatus] = useState<string>(approval?.status ?? "active");
  const [restricted, setRestricted] = useState(approval?.restricted ?? false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string>();

  function submit(ev: FormEvent<HTMLFormElement>) {
    ev.preventDefault();
    const f = new FormData(ev.currentTarget);
    const get = (n: string) => String(f.get(n) ?? "").trim();
    const v: ApprovalValues = {
      approval_number: get("approval_number"),
      board: get("board"),
      title: get("title"),
      approval_date: get("approval_date"),
      expiry_date: get("expiry_date"),
    };
    const errs = validateApproval(v);
    setErrors(errs);
    setFormError(undefined);
    if (Object.keys(errs).length) return;
    save.mutate(
      { ...v, status: status as EthicsApproval["status"], projects: linked, restricted },
      {
        onSuccess: (r) => {
          toast.success("Saved");
          void navigate(`/labs/${labId}/ethics/${r.id}`);
        },
        onError: (e) => {
          const { fields, form } = formErrors(e, [...FIELDS, "projects"]);
          setErrors(fields);
          setFormError(form);
        },
      },
    );
  }

  return (
    <div className="max-w-xl">
      <PageHeader title={approval ? "Edit ethics approval" : "New ethics approval"} />
      <form onSubmit={submit} noValidate className="grid gap-4">
        <FormError message={formError} />
        <FormField label="Approval number" error={errors.approval_number}>
          {(p) => (
            <Input
              maxLength={100}
              {...p}
              name="approval_number"
              defaultValue={approval?.approval_number}
            />
          )}
        </FormField>
        <FormField label="Ethics board" error={errors.board}>
          {(p) => <Input maxLength={200} {...p} name="board" defaultValue={approval?.board} />}
        </FormField>
        <FormField label="Title" error={errors.title}>
          {(p) => <Input maxLength={300} {...p} name="title" defaultValue={approval?.title} />}
        </FormField>
        <div className="grid grid-cols-2 gap-3">
          <FormField label="Approval date" error={errors.approval_date}>
            {(p) => (
              <Input
                {...p}
                type="date"
                name="approval_date"
                defaultValue={approval?.approval_date}
              />
            )}
          </FormField>
          <FormField label="Expiry date" error={errors.expiry_date}>
            {(p) => (
              <Input {...p} type="date" name="expiry_date" defaultValue={approval?.expiry_date} />
            )}
          </FormField>
        </div>
        <FormField label="Status" error={errors.status}>
          {(p) => (
            <select
              {...p}
              className={selectCls}
              value={status}
              onChange={(e) => setStatus(e.target.value)}
            >
              {APPROVAL_STATUSES.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          )}
        </FormField>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={restricted}
            onChange={(e) => setRestricted(e.target.checked)}
          />
          Restricted: only people on linked projects can see this
        </label>
        <FormField
          label="Projects covered"
          hint="You can only link projects where you can edit content."
          error={errors.projects}
        >
          {(p) => (
            <div
              id={p.id}
              role="group"
              aria-label="Projects covered"
              className="grid gap-1 rounded-md border p-2"
            >
              {projects.length === 0 && (
                <p className="text-xs text-muted-foreground">Nothing to pick yet.</p>
              )}
              {projects.map((pr) => (
                <label key={pr.id} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={linked.includes(pr.id)}
                    disabled={!pr.my_permissions.includes("edit_content")}
                    onChange={(e) =>
                      setLinked((l) =>
                        e.target.checked ? [...l, pr.id] : l.filter((x) => x !== pr.id),
                      )
                    }
                  />
                  {pr.name}
                </label>
              ))}
            </div>
          )}
        </FormField>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={() => void navigate(-1)}>
            Cancel
          </Button>
          <Button type="submit" disabled={save.isPending}>
            Save
          </Button>
        </div>
      </form>
    </div>
  );
}
