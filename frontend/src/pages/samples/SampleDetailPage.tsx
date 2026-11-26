import { useRef, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { toast } from "sonner";
import { ConfirmDelete } from "@/components/shared/ConfirmDelete";
import { EmptyState } from "@/components/shared/EmptyState";
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
import { downloadUrl, useProjects } from "@/hooks/projects";
import {
  sampleFileUrl,
  useProjectFiles,
  useSample,
  useSampleActions,
  useSamples,
} from "@/hooks/samples";
import { useLab } from "@/hooks/workspace";
import type { SampleDetail, SampleFile } from "@/lib/api-types";
import { personName } from "@/lib/api-types";
import { ApiError } from "@/lib/api";
import { shortDate } from "@/lib/format";
import { formErrors } from "@/lib/forms";
import { NativeSelect, Section } from "@/pages/admin/common";
import { KIND_FIELDS, KINDS, labelOf, STATUSES } from "./common";
import { SampleDialog } from "./SampleDialog";

const sizeText = (n: number) =>
  n < 1024 * 1024 ? `${Math.ceil(n / 1024)} KB` : `${(n / 1048576).toFixed(1)} MB`;

/** A checkbox list in a dialog, with a search box, for choosing several things at once. */
function MultiPick({
  title,
  options,
  initial,
  onSave,
  onClose,
}: {
  title: string;
  options: { id: string; label: string }[];
  initial: string[];
  onSave: (ids: string[]) => Promise<unknown>;
  onClose: () => void;
}) {
  const [picked, setPicked] = useState(new Set(initial));
  const [find, setFind] = useState("");
  const [busy, setBusy] = useState(false);
  const shown = options.filter((o) => o.label.toLowerCase().includes(find.trim().toLowerCase()));
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogTitle className="text-base font-semibold">{title}</DialogTitle>
        <DialogDescription className="sr-only">Pick from the list</DialogDescription>
        <FormField label="Search">
          {(p) => (
            <Input {...p} type="search" value={find} onChange={(e) => setFind(e.target.value)} />
          )}
        </FormField>
        <ul className="grid max-h-64 gap-1 overflow-y-auto" aria-label={title}>
          {shown.map((o) => (
            <li key={o.id}>
              <label className="flex items-center gap-2 rounded px-1 py-1 text-sm hover:bg-muted">
                <input
                  type="checkbox"
                  className="size-4 accent-primary"
                  checked={picked.has(o.id)}
                  onChange={(e) => {
                    const next = new Set(picked);
                    if (e.target.checked) next.add(o.id);
                    else next.delete(o.id);
                    setPicked(next);
                  }}
                />
                {o.label}
              </label>
            </li>
          ))}
          {shown.length === 0 && <li className="text-sm text-muted-foreground">Nothing found.</li>}
        </ul>
        <div className="flex justify-end gap-2">
          <DialogClose asChild>
            <Button type="button" variant="outline">
              Cancel
            </Button>
          </DialogClose>
          <Button
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                await onSave([...picked]);
                onClose();
              } catch (e) {
                toast.error(formErrors(e, []).form ?? "Could not save.");
              } finally {
                setBusy(false);
              }
            }}
          >
            Save
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

/** Pick a project, then one of its files, to show on this sample. */
function LinkFileDialog({
  labId,
  sample,
  onLink,
  onClose,
}: {
  labId: string;
  sample: SampleDetail;
  onLink: (fileId: string) => Promise<unknown>;
  onClose: () => void;
}) {
  const projects = useProjects(labId).data ?? [];
  const [project, setProject] = useState("");
  const files = useProjectFiles(labId, project);
  const linked = new Set(sample.files.map((f) => f.id));
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogTitle className="text-base font-semibold">Link a project file</DialogTitle>
        <DialogDescription className="text-sm text-muted-foreground">
          Show a file from a project on this sample. The file stays in the project.
        </DialogDescription>
        <FormField label="Project">
          {(p) => (
            <NativeSelect {...p} value={project} onChange={(e) => setProject(e.target.value)}>
              <option value="">Choose a project</option>
              {projects.map((pr) => (
                <option key={pr.id} value={pr.id}>
                  {pr.name}
                </option>
              ))}
            </NativeSelect>
          )}
        </FormField>
        {project && files.isLoading && <Skeleton className="h-20 w-full" />}
        {project && files.data && (
          <ul className="grid max-h-64 gap-1 overflow-y-auto" aria-label="Project files">
            {files.data.map((f) => (
              <li key={f.id} className="flex items-center justify-between gap-2 text-sm">
                <span className="truncate">{f.original_filename}</span>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={linked.has(f.id)}
                  onClick={async () => {
                    try {
                      await onLink(f.id);
                      toast.success("File linked");
                      onClose();
                    } catch (e) {
                      toast.error(formErrors(e, []).form ?? "Could not link the file.");
                    }
                  }}
                >
                  {linked.has(f.id) ? "Linked" : "Link"}
                </Button>
              </li>
            ))}
            {files.data.length === 0 && (
              <li className="text-sm text-muted-foreground">This project has no files yet.</li>
            )}
          </ul>
        )}
        <div className="flex justify-end">
          <DialogClose asChild>
            <Button variant="outline">Close</Button>
          </DialogClose>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function Pill({ children }: { children: ReactNode }) {
  return <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium">{children}</span>;
}

function Detail({
  sample: s,
  labId,
  canEdit,
}: {
  sample: SampleDetail;
  labId: string;
  canEdit: boolean;
}) {
  const navigate = useNavigate();
  const { update, remove, uploadFile, removeFile } = useSampleActions(labId);
  const allSamples = useSamples(labId, {}).data ?? [];
  const allProjects = useProjects(labId).data ?? [];
  const [dialog, setDialog] = useState<"edit" | "delete" | "parents" | "projects" | "link" | null>(
    null,
  );
  const fileInput = useRef<HTMLInputElement>(null);
  const save = (v: Parameters<typeof update.mutateAsync>[0]) => update.mutateAsync(v);
  const linkedIds = s.files.filter((f) => !f.on_sample).map((f) => f.id);
  const fields = KIND_FIELDS[s.kind].filter((f) => s[f.key]);
  const last = s.tubes.length === 1 ? s.tubes[0] : undefined;

  const fileHref = (f: SampleFile) =>
    f.on_sample ? sampleFileUrl(labId, s.id, f.id) : downloadUrl(labId, f.id);
  const dropFile = (f: SampleFile) =>
    (f.on_sample
      ? removeFile.mutateAsync({ id: s.id, fileId: f.id })
      : save({ id: s.id, linked_files: linkedIds.filter((i) => i !== f.id) })
    ).then(
      () => toast.success(f.on_sample ? "File removed" : "File unlinked"),
      (e) => toast.error(formErrors(e, []).form ?? "Could not remove the file."),
    );
  async function onPick(file: File | undefined) {
    if (!file) return;
    try {
      await uploadFile.mutateAsync({ id: s.id, file });
      toast.success("File added");
    } catch (e) {
      toast.error(formErrors(e, []).form ?? "Could not upload the file.");
    }
  }

  return (
    <div className="grid gap-6">
      <PageHeader
        title={`${s.code} ${s.name}`}
        description={`${labelOf(KINDS, s.kind)}, ${labelOf(STATUSES, s.status).toLowerCase()}, owned by ${personName(s.owner)}.`}
        actions={
          <>
            <Button variant="outline" asChild>
              <Link to="..">All samples</Link>
            </Button>
            {canEdit && (
              <>
                <Button variant="outline" onClick={() => setDialog("edit")}>
                  Edit
                </Button>
                <Button variant="outline" onClick={() => setDialog("delete")}>
                  Delete
                </Button>
              </>
            )}
          </>
        }
      />
      <Section title="Details" defaultOpen>
        <dl className="grid gap-3 text-sm sm:grid-cols-2">
          {fields.map((f) => (
            <div key={f.key}>
              <dt className="text-xs text-muted-foreground">{f.label}</dt>
              <dd className={f.type === "long" ? "font-mono break-all" : undefined}>{s[f.key]}</dd>
            </div>
          ))}
          {s.kind === "primer" && s.tm != null && (
            <div>
              <dt className="text-xs text-muted-foreground">Melting temperature (rough)</dt>
              <dd>{s.tm.toFixed(1)} °C</dd>
            </div>
          )}
        </dl>
        {fields.length === 0 && !s.description && (
          <p className="text-sm text-muted-foreground">No details yet.</p>
        )}
        {s.description && <p className="text-sm whitespace-pre-wrap">{s.description}</p>}
      </Section>

      <Section title="Lineage" description="What it came from and what came from it." defaultOpen>
        <div className="grid gap-2 text-sm">
          <RefList label="Made from" items={s.parents} empty="No parents recorded." />
          <p className="rounded-md border bg-muted/40 px-3 py-2 font-medium">
            {s.code} {s.name}
          </p>
          <RefList label="Made into" items={s.children} empty="Nothing made from it yet." />
        </div>
        {canEdit && (
          <Button
            variant="outline"
            className="justify-self-start"
            onClick={() => setDialog("parents")}
          >
            Edit parents
          </Button>
        )}
      </Section>

      <Section title="Where it is" description="Every tube of it in the freezers." defaultOpen>
        {last && (
          <p className="rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-sm">
            <Pill>Last tube</Pill> {personName(last.owner)} holds the last tube of {s.code}.
          </p>
        )}
        {s.tubes.length === 0 ? (
          <EmptyState
            compact
            title="Not in storage"
            description="Put a tube of it in a box to find it later."
            action={
              <Button asChild>
                <Link to="../storage">Open storage</Link>
              </Button>
            }
          />
        ) : (
          <ul className="grid divide-y rounded-lg border">
            {s.tubes.map((t) => (
              <li
                key={t.id}
                className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-sm"
              >
                <span>
                  <Link
                    to={`../storage?box=${t.box}&tube=${t.id}`}
                    className="font-medium underline-offset-2 hover:underline"
                  >
                    {t.unit_name} / {t.box_name} / {t.position}
                  </Link>
                  <span className="ml-2 text-xs text-muted-foreground">
                    {[t.amount, t.label, t.stored_on && shortDate(t.stored_on)]
                      .filter(Boolean)
                      .join(" · ")}
                  </span>
                </span>
                <span className="text-xs text-muted-foreground">{personName(t.owner)}</span>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Projects" description="Where this sample is used." defaultOpen>
        {s.projects.length === 0 ? (
          <p className="text-sm text-muted-foreground">Not linked to a project.</p>
        ) : (
          <ul className="flex flex-wrap gap-2">
            {s.projects.map((p) => (
              <li key={p.id}>
                <Link
                  to={`/labs/${labId}/projects/${p.id}`}
                  className="rounded-full border px-3 py-1 text-sm hover:bg-muted"
                >
                  {p.name}
                </Link>
              </li>
            ))}
          </ul>
        )}
        {canEdit && (
          <Button
            variant="outline"
            className="justify-self-start"
            onClick={() => setDialog("projects")}
          >
            Edit projects
          </Button>
        )}
      </Section>

      <Section title="Files" description="Gels, maps and sequencing files." defaultOpen>
        {s.files.length === 0 ? (
          <p className="text-sm text-muted-foreground">No files yet.</p>
        ) : (
          <ul className="grid divide-y rounded-lg border">
            {s.files.map((f) => (
              <li
                key={f.id}
                className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-sm"
              >
                <span className="min-w-0">
                  <a
                    href={fileHref(f)}
                    download={f.name}
                    className="font-medium underline-offset-2 hover:underline"
                  >
                    {f.name}
                  </a>
                  <span className="ml-2 text-xs text-muted-foreground">
                    {[
                      sizeText(f.size_bytes),
                      f.on_sample ? null : f.project ? `From ${f.project.name}` : "Linked",
                      shortDate(f.created_at),
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </span>
                </span>
                {canEdit && (
                  <Button
                    size="sm"
                    variant="outline"
                    aria-label={`${f.on_sample ? "Remove" : "Unlink"} ${f.name}`}
                    onClick={() => void dropFile(f)}
                  >
                    {f.on_sample ? "Remove" : "Unlink"}
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
        {canEdit && (
          <div className="flex flex-wrap gap-2">
            <input
              ref={fileInput}
              type="file"
              className="sr-only"
              aria-label="Choose a file to upload"
              onChange={(e) => {
                void onPick(e.target.files?.[0]);
                e.target.value = "";
              }}
            />
            <Button
              variant="outline"
              disabled={uploadFile.isPending}
              onClick={() => fileInput.current?.click()}
            >
              {uploadFile.isPending ? "Uploading…" : "Upload a file"}
            </Button>
            <Button variant="outline" onClick={() => setDialog("link")}>
              Link a project file
            </Button>
          </div>
        )}
      </Section>

      {dialog === "edit" && (
        <SampleDialog labId={labId} sample={s} open onClose={() => setDialog(null)} />
      )}
      {dialog === "parents" && (
        <MultiPick
          title="Edit parents"
          options={allSamples
            .filter((o) => o.id !== s.id)
            .map((o) => ({ id: o.id, label: `${o.code} ${o.name}` }))}
          initial={s.parents.map((p) => p.id)}
          onSave={(ids) => save({ id: s.id, parents: ids })}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog === "projects" && (
        <MultiPick
          title="Edit projects"
          options={allProjects.map((p) => ({ id: p.id, label: p.name }))}
          initial={s.projects.map((p) => p.id)}
          onSave={(ids) => save({ id: s.id, projects: ids })}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog === "link" && (
        <LinkFileDialog
          labId={labId}
          sample={s}
          onLink={(fileId) => save({ id: s.id, linked_files: [...linkedIds, fileId] })}
          onClose={() => setDialog(null)}
        />
      )}
      <ConfirmDelete
        open={dialog === "delete"}
        name={s.code}
        noun="sample"
        description="A sample that still has tubes in storage can't be deleted. Take the tubes out first, or mark it archived."
        pending={remove.isPending}
        onClose={() => setDialog(null)}
        onConfirm={() =>
          remove.mutate(s.id, {
            onSuccess: () => {
              toast.success("Sample deleted");
              navigate("..", { relative: "path" });
            },
            onError: (e) => toast.error(formErrors(e, []).form ?? "Could not delete the sample."),
            onSettled: () => setDialog(null),
          })
        }
      />
    </div>
  );
}

function RefList({
  label,
  items,
  empty,
}: {
  label: string;
  items: SampleDetail["parents"];
  empty: string;
}) {
  return (
    <div className="grid gap-1">
      <span className="text-xs text-muted-foreground">{label}</span>
      {items.length === 0 ? (
        <span className="text-muted-foreground">{empty}</span>
      ) : (
        <ul className="flex flex-wrap gap-2">
          {items.map((r) => (
            <li key={r.id}>
              <Link to={`../${r.id}`} className="underline-offset-2 hover:underline">
                {r.code} {r.name}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function SampleDetailPage() {
  const { labId = "", sampleId = "" } = useParams();
  const { data: lab } = useLab(labId);
  const { data, isLoading, error } = useSample(labId, sampleId);
  const canEdit = !!lab?.my_permissions.includes("manage_samples");
  if (isLoading) return <Skeleton className="h-64 w-full" aria-label="Loading" />;
  if (error || !data) {
    const gone = error instanceof ApiError && (error.status === 404 || error.status === 403);
    return (
      <EmptyState
        title={gone ? "This sample is not available" : "We could not load this sample"}
        description={gone ? "It may have been deleted, or samples are turned off." : "Try again."}
        action={
          <Button asChild>
            <Link to="..">All samples</Link>
          </Button>
        }
      />
    );
  }
  return <Detail sample={data} labId={labId} canEdit={canEdit} />;
}
