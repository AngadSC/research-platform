import { FlaskConical, Plus } from "lucide-react";
import type { ReactNode } from "react";
import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { toast } from "sonner";
import { DataTable, HIDE_NARROW, HIDE_NARROWER, type Column } from "@/components/shared/DataTable";
import { DetailPanel } from "@/components/shared/DetailPanel";
import { EmptyState } from "@/components/shared/EmptyState";
import { FormError } from "@/components/shared/FormError";
import { LinkedFiles } from "@/components/shared/LinkedFiles";
import { ParticipantBadge } from "@/components/shared/ParticipantData";
import type { LinkTarget } from "@/components/shared/LinkMenu";
import { PageHeader } from "@/components/shared/PageHeader";
import { ReferenceList } from "@/components/shared/References";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { downloadUrl } from "@/hooks/projects";
import { LIVE_POLL_MS, useNewItemToasts } from "@/hooks/liveRefresh";
import { useDeleteRecord, useRecord, useRecords } from "@/hooks/research";
import { ApiError } from "@/lib/api";
import {
  personName,
  type Analysis,
  type AttachmentRef,
  type Dataset,
  type Decision,
  type Manuscript,
  type ResearchResult,
} from "@/lib/api-types";
import { shortDate } from "@/lib/format";
import { formErrors } from "@/lib/forms";
import { isKind, KINDS, recordTitle, type AnyRecord, type Kind } from "@/lib/research";
import { recordPath, SECTION_KINDS, sectionOf, type ResearchSection } from "@/lib/workflow";
import type { ProjectTabProps } from "@/pages/ProjectPage";
import { ResearchForm, ResultSetForm } from "@/pages/project/ResearchForm";
import { AnalysisOutputs, DownloadCode, RunAgain } from "@/pages/project/AnalysisExtras";

const short = (c: string) => c.slice(0, 7) || "None";
const projectBase = (p: ProjectTabProps) => `/labs/${p.labId}/projects/${p.projectId}`;

/** The records of one Workflow section (Data, Analysis, Manuscript), each kind in its own list. */
export function SectionLists({
  section,
  ...props
}: ProjectTabProps & { section: ResearchSection }) {
  const navigate = useNavigate();
  const kinds = SECTION_KINDS[section];
  return (
    <div className="grid gap-8">
      {kinds.map((kind) => (
        <section key={kind} aria-label={KINDS[kind].label} className="grid gap-3">
          {kinds.length > 1 && <h2 className="text-base font-semibold">{KINDS[kind].label}</h2>}
          <List
            {...props}
            kind={kind}
            navigate={navigate}
            canEdit={props.project.my_permissions.includes("edit_content")}
            base={projectBase(props)}
          />
        </section>
      ))}
    </div>
  );
}

function useKind(): Kind | undefined {
  const { kind } = useParams();
  return isKind(kind) ? kind : undefined;
}
const NotFound = () => <FormError message="We couldn't find that page." />;

const COLUMNS: { [K in Kind]: Column<AnyRecord>[] } = {
  datasets: [
    {
      key: "n",
      header: "Name",
      cell: (r) => (
        <span className="flex items-center gap-2">
          {(r as Dataset).name}
          {(r as Dataset).contains_participant_data && <ParticipantBadge />}
        </span>
      ),
    },
    { key: "v", header: "Version", cell: (r) => (r as Dataset).version_label },
    {
      key: "c",
      header: "Access controlled by",
      className: HIDE_NARROW,
      cell: (r) => ((r as Dataset).controlled_by ? personName((r as Dataset).controlled_by) : ""),
    },
  ],
  analyses: [
    { key: "t", header: "Title", cell: (r) => (r as Analysis).title },
    { key: "d", header: "Run on", cell: (r) => shortDate((r as Analysis).ran_at) },
    {
      key: "c",
      header: "Commit",
      className: HIDE_NARROW,
      cell: (r) => short((r as Analysis).code_commit),
    },
    {
      key: "b",
      header: "Run by",
      className: HIDE_NARROWER,
      cell: (r) => ((r as Analysis).ran_by ? personName((r as Analysis).ran_by) : ""),
    },
  ],
  results: [
    { key: "t", header: "Title", cell: (r) => (r as ResearchResult).title },
    { key: "a", header: "Analysis", cell: (r) => (r as ResearchResult).analysis?.title },
  ],
  decisions: [
    { key: "t", header: "Title", cell: (r) => (r as Decision).title },
    { key: "d", header: "Date", cell: (r) => shortDate((r as Decision).decided_on) },
  ],
  manuscripts: [
    { key: "t", header: "Title", cell: (r) => (r as Manuscript).title },
    { key: "s", header: "Status", cell: (r) => <StatusBadge status={(r as Manuscript).status} /> },
    { key: "r", header: "Results", cell: (r) => (r as Manuscript).results?.length ?? 0 },
  ],
};

/** Same name together, newest version first. */
const sortVersions = (all: Dataset[]) =>
  [...all].sort(
    (a, b) => a.name.localeCompare(b.name) || Date.parse(b.created_at) - Date.parse(a.created_at),
  );

/** The dataset columns, with a chip on versions that replace or have been replaced. */
function datasetColumns(all: Dataset[]): Column<AnyRecord>[] {
  const replaced = new Set(all.map((d) => d.previous_version?.id));
  return COLUMNS.datasets.map((c) =>
    c.key !== "v"
      ? c
      : {
          ...c,
          cell: (r) => {
            const d = r as Dataset;
            return (
              <span className="flex items-center gap-2">
                {d.version_label}
                {replaced.has(d.id) ? (
                  <Badge variant="secondary">Replaced</Badge>
                ) : (
                  d.previous_version && <Badge variant="success">Latest</Badge>
                )}
              </span>
            );
          },
        },
  );
}

function List({
  labId,
  projectId,
  kind,
  canEdit,
  base,
  navigate,
}: {
  labId: string;
  projectId: string;
  kind: Kind;
  canEdit: boolean;
  base: string;
  navigate: (to: string) => void | Promise<void>;
}) {
  const list = useRecords<AnyRecord>(
    labId,
    projectId,
    kind,
    kind === "analyses" ? LIVE_POLL_MS : undefined,
  );
  useNewItemToasts(
    `${projectId}/${kind}`,
    kind === "analyses" ? (list.data as { id: string; title: string }[] | undefined) : undefined,
    "analysis",
    (r) => r.title,
  );
  const k = KINDS[kind];
  const rows =
    kind === "analyses"
      ? [...(list.data ?? [])].sort(
          (a, b) => Date.parse((b as Analysis).ran_at) - Date.parse((a as Analysis).ran_at),
        )
      : kind === "datasets"
        ? sortVersions((list.data ?? []) as Dataset[])
        : (list.data ?? []);
  const add = canEdit ? (
    <Button asChild>
      <Link to={recordPath(base, kind, "new")}>
        <Plus aria-hidden /> New {k.one}
      </Link>
    </Button>
  ) : undefined;
  return (
    <div className="grid gap-4">
      {(list.data?.length ?? 0) > 0 && <div className="flex justify-end">{add}</div>}
      <DataTable
        columns={kind === "datasets" ? datasetColumns(rows as Dataset[]) : COLUMNS[kind]}
        rows={rows}
        getRowKey={(r) => r.id}
        loading={list.isLoading}
        onRowClick={(r) => void navigate(recordPath(base, kind, r.id))}
        empty={
          <EmptyState
            icon={FlaskConical}
            title={`No ${k.label.toLowerCase()} yet`}
            description={k.blurb}
            action={add}
          />
        }
      />
    </div>
  );
}

export function ResearchNew(props: ProjectTabProps) {
  const kind = useKind();
  const navigate = useNavigate();
  const from = useSearchParams()[0].get("from") ?? "";
  const source = useRecord<Dataset>(props.labId, "datasets", kind === "datasets" ? from : "");
  if (!kind) return <NotFound />;
  if (!props.project.my_permissions.includes("edit_content"))
    return <FormError message="You don't have permission to add records here." />;
  const base = projectBase(props);
  const back = `${base}/workflow/${sectionOf(kind)}`;
  if (from && kind === "datasets" && !source.data && !source.error)
    return <Skeleton aria-busy="true" aria-label="Loading" className="h-40 w-full" />;
  const one = (
    <ResearchForm
      key={source.data?.id}
      prefill={source.data}
      labId={props.labId}
      projectId={props.projectId}
      kind={kind}
      onSaved={(r) => void navigate(recordPath(base, kind, r.id))}
      onCancel={() => void navigate(back)}
    />
  );
  return (
    <div className="grid max-w-xl gap-4">
      <PageHeader
        title={
          kind === "results"
            ? "Add results"
            : source.data
              ? `New version of ${source.data.name}`
              : `New ${KINDS[kind].one}`
        }
      />
      {kind === "results" ? (
        <NewResults
          labId={props.labId}
          projectId={props.projectId}
          one={one}
          onDone={() => void navigate(back)}
        />
      ) : (
        one
      )}
    </div>
  );
}

/** Add one result or figure at a time, or a full set from one analysis at once. */
function NewResults({
  labId,
  projectId,
  one,
  onDone,
}: {
  labId: string;
  projectId: string;
  one: ReactNode;
  onDone: () => void;
}) {
  const [full, setFull] = useState(false);
  const choice = (value: boolean, text: string) => (
    <Button
      type="button"
      size="sm"
      variant={full === value ? "default" : "outline"}
      aria-pressed={full === value}
      onClick={() => setFull(value)}
    >
      {text}
    </Button>
  );
  return (
    <>
      <div role="group" aria-label="How to add results" className="flex flex-wrap gap-2">
        {choice(false, "One at a time")}
        {choice(true, "A full set at once")}
      </div>
      {full ? (
        <ResultSetForm labId={labId} projectId={projectId} onDone={onDone} onCancel={onDone} />
      ) : (
        one
      )}
    </>
  );
}

function Refs({
  base,
  kind,
  items,
}: {
  base: string;
  kind: Kind;
  items?: { id: string; label: string }[];
}) {
  if (!items?.length) return <span className="text-muted-foreground">None</span>;
  return (
    <ul className="grid gap-1">
      {items.map((i) => (
        <li key={i.id}>
          <Link
            className="text-primary underline-offset-2 hover:underline"
            to={recordPath(base, kind, i.id)}
          >
            {i.label}
          </Link>
        </li>
      ))}
    </ul>
  );
}

function Files({ labId, base, items }: { labId: string; base: string; items?: AttachmentRef[] }) {
  if (!items?.length) return <span className="text-muted-foreground">None</span>;
  const files = `${base}/files`;
  return (
    <ul className="grid gap-1">
      {items.map((a) => (
        <li key={a.id} className="flex items-center gap-3">
          <span>{a.original_filename}</span>
          {(a.content_type === "application/pdf" || a.original_filename.endsWith(".pdf")) && (
            <Link className="text-primary hover:underline" to={`${files}/${a.id}`}>
              Open
            </Link>
          )}
          <a className="text-primary hover:underline" href={downloadUrl(labId, a.id)} download>
            Download
          </a>
        </li>
      ))}
    </ul>
  );
}

const Ext = ({ url }: { url: string }) =>
  url ? (
    <a
      className="text-primary hover:underline"
      href={url}
      target="_blank"
      rel="noreferrer noopener"
    >
      {url}
    </a>
  ) : (
    <span className="text-muted-foreground">None</span>
  );

function fields(kind: Kind, r: AnyRecord, labId: string, base: string): [string, ReactNode][] {
  const ds = (x: { id: string; name: string; version_label: string }[]) =>
    x.map((d) => ({ id: d.id, label: `${d.name} (${d.version_label})` }));
  const t = (x: { id: string; title: string }[]) => x.map((i) => ({ id: i.id, label: i.title }));
  const who = (u?: { email: string; display_name?: string }) => (u ? personName(u) : "None");
  switch (kind) {
    case "datasets": {
      const d = r as Dataset;
      return [
        ["Version", d.version_label],
        ["Where it lives", d.location_text || "None"],
        ["Link to the data", <Ext key="u" url={d.location_url} />],
        ["Access controlled by", who(d.controlled_by)],
        ["How to get access", d.access_notes || "None"],
        ["Checksum", d.checksum || "None"],
        [
          "Identifies participants",
          d.contains_participant_data ? <ParticipantBadge key="pd" /> : "No",
        ],
        [
          "New version of",
          <Refs
            key="p"
            base={base}
            kind="datasets"
            items={d.previous_version ? ds([d.previous_version]) : []}
          />,
        ],
        ["Used by analyses", <Refs key="a" base={base} kind="analyses" items={t(d.analyses)} />],
      ];
    }
    case "analyses": {
      const a = r as Analysis;
      return [
        ["Description", a.description || "None"],
        ["Code repository", <Ext key="r" url={a.code_repo_url} />],
        [
          "Commit",
          a.code_commit && a.code_repo_url ? (
            <Ext key="c" url={`${a.code_repo_url.replace(/\/$/, "")}/commit/${a.code_commit}`} />
          ) : (
            a.code_commit || "None"
          ),
        ],
        [
          "Attached code",
          <Files
            key="f"
            labId={labId}
            base={base}
            items={a.code_attachment ? [a.code_attachment] : []}
          />,
        ],
        ["Datasets used", <Refs key="d" base={base} kind="datasets" items={ds(a.datasets)} />],
        ["Results", <Refs key="s" base={base} kind="results" items={t(a.results)} />],
        ["Run by", who(a.ran_by)],
        ["Run on", shortDate(a.ran_at)],
      ];
    }
    case "results": {
      const x = r as ResearchResult;
      return [
        ["Summary", x.summary || "None"],
        [
          "Analysis",
          <Refs key="a" base={base} kind="analyses" items={x.analysis ? t([x.analysis]) : []} />,
        ],
        ["Figures and tables", <Files key="f" labId={labId} base={base} items={x.attachments} />],
        [
          "Used in manuscripts",
          <Refs key="m" base={base} kind="manuscripts" items={t(x.manuscripts)} />,
        ],
      ];
    }
    case "decisions": {
      const d = r as Decision;
      return [
        ["Why", d.rationale || "None"],
        ["Decided on", shortDate(d.decided_on)],
        ["Decided by", who(d.decided_by)],
        [
          "Supporting documents",
          <ul key="sd">
            {d.supporting_documents.map((x) => (
              <li key={x.id}>
                <Link className="text-primary hover:underline" to={`${base}/documents/${x.id}`}>
                  {x.title}
                </Link>
              </li>
            ))}
          </ul>,
        ],
        [
          "Supporting files",
          <Files key="sf" labId={labId} base={base} items={d.supporting_attachments} />,
        ],
        ["References", <ReferenceList key="rf" items={d.references} />],
        ["Datasets", <Refs key="d" base={base} kind="datasets" items={ds(d.datasets)} />],
        ["Analyses", <Refs key="a" base={base} kind="analyses" items={t(d.analyses)} />],
        ["Results", <Refs key="r" base={base} kind="results" items={t(d.results)} />],
      ];
    }
    case "manuscripts": {
      const m = r as Manuscript;
      return [
        ["Link", <Ext key="u" url={m.url} />],
        ["Status", <StatusBadge key="s" status={m.status} />],
        ["Results used", <Refs key="r" base={base} kind="results" items={t(m.results)} />],
        ["Created by", who(m.created_by)],
      ];
    }
  }
}

const LINK_FIELD = {
  datasets: "dataset",
  analyses: "analysis",
  results: "result",
  manuscripts: "manuscript",
  decisions: "decision",
} as const satisfies Partial<Record<Kind, LinkTarget>>;

export function ResearchDetail(props: ProjectTabProps) {
  const { id = "" } = useParams();
  const kind = useKind();
  if (!kind) return <NotFound />;
  return <Detail key={id} {...props} kind={kind} id={id} />;
}

function Detail({
  labId,
  projectId,
  project,
  kind,
  id,
}: ProjectTabProps & { kind: Kind; id: string }) {
  const navigate = useNavigate();
  const rec = useRecord<AnyRecord>(labId, kind, id);
  const del = useDeleteRecord(labId, kind);
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string>();
  const canEdit = project.my_permissions.includes("edit_content");
  const base = `/labs/${labId}/projects/${projectId}`;

  if (rec.error) return <FormError message={formErrors(rec.error, []).form} />;
  if (!rec.data) return <Skeleton aria-busy="true" aria-label="Loading" className="h-40 w-full" />;
  const r = rec.data;
  const title = recordTitle(r);

  return (
    <div className="grid gap-6">
      <PageHeader
        title={title}
        actions={
          <>
            <Button variant="outline" asChild>
              <Link
                to={`/labs/${labId}/projects/${projectId}/workflow/lineage?focus=${KINDS[kind].one}:${id}`}
              >
                View in lineage
              </Link>
            </Button>
            {kind === "datasets" && canEdit && (
              <Button variant="outline" asChild>
                <Link to={`${recordPath(base, "datasets", "new")}?from=${id}`}>New version</Link>
              </Button>
            )}
            {kind === "analyses" && <DownloadCode labId={labId} analysis={r as Analysis} />}
            {kind === "analyses" && canEdit && (
              <RunAgain labId={labId} projectId={projectId} base={base} analysis={r as Analysis} />
            )}
            {canEdit && (
              <>
                <Button variant="outline" onClick={() => setEditing(true)}>
                  Edit
                </Button>
                <Button variant="outline" onClick={() => setDeleting(true)}>
                  Delete
                </Button>
              </>
            )}
          </>
        }
      />
      <dl className="grid gap-4 text-sm">
        {fields(kind, r, labId, base).map(([k, v]) => (
          <div key={k} className="grid gap-1 sm:grid-cols-[12rem_1fr]">
            <dt className="text-muted-foreground">{k}</dt>
            <dd className="whitespace-pre-wrap">{v}</dd>
          </div>
        ))}
      </dl>
      {kind === "analyses" && (
        <AnalysisOutputs labId={labId} projectId={projectId} analysisId={id} />
      )}
      {kind in LINK_FIELD && (
        <section aria-labelledby="linked-files" className="grid gap-2">
          <h2 id="linked-files" className="text-sm font-medium">
            Linked files
          </h2>
          <LinkedFiles
            labId={labId}
            projectId={projectId}
            canEdit={canEdit}
            target={{ field: LINK_FIELD[kind as keyof typeof LINK_FIELD], id }}
          />
        </section>
      )}
      <DetailPanel open={editing} onOpenChange={setEditing} title={`Edit ${KINDS[kind].one}`}>
        {editing && (
          <ResearchForm
            labId={labId}
            projectId={projectId}
            kind={kind}
            record={r}
            onSaved={() => setEditing(false)}
            onCancel={() => setEditing(false)}
          />
        )}
      </DetailPanel>
      <Dialog open={deleting} onOpenChange={setDeleting}>
        <DialogContent>
          <DialogTitle className="text-base font-semibold">Delete {title}?</DialogTitle>
          <DialogDescription className="text-sm text-muted-foreground">
            This removes the record. It does not touch any files.
          </DialogDescription>
          <FormError message={error} />
          <div className="flex justify-end gap-2">
            <DialogClose asChild>
              <Button variant="outline">Cancel</Button>
            </DialogClose>
            <Button
              variant="destructive"
              disabled={del.isPending}
              onClick={() =>
                del.mutate(id, {
                  onSuccess: () => {
                    toast.success("Deleted");
                    void navigate(`${base}/workflow/${sectionOf(kind)}`);
                  },
                  onError: (e) =>
                    setError(
                      e instanceof ApiError && e.status === 409
                        ? "Other records depend on this one, so it can't be deleted yet. Remove those links first."
                        : formErrors(e, []).form,
                    ),
                })
              }
            >
              Delete {KINDS[kind].one}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
