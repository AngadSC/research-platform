import { Search } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { toast } from "sonner";
import { DataTable, HIDE_NARROW, HIDE_NARROWER, type Column } from "@/components/shared/DataTable";
import { ConfirmDelete } from "@/components/shared/ConfirmDelete";
import { EmptyState } from "@/components/shared/EmptyState";
import { FormField } from "@/components/shared/FormField";
import { MoreMenu } from "@/components/shared/MoreMenu";
import { PageHeader } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { sampleExportUrl, useSampleActions, useSamples } from "@/hooks/samples";
import { useDebounced } from "@/hooks/useDebounced";
import { useLab, useMembers } from "@/hooks/workspace";
import type { Sample } from "@/lib/api-types";
import { personName } from "@/lib/api-types";
import { formErrors } from "@/lib/forms";
import { NativeSelect } from "@/pages/admin/common";
import { KINDS, labelOf, STATUSES } from "./common";
import { ImportSamples } from "./ImportSamples";
import { SampleDialog } from "./SampleDialog";

/** Where a sample is: how many tubes, and the first spot. One left gets a pill. */
function Where({ sample: s }: { sample: Sample }) {
  const first = s.tubes[0];
  if (!first) return <span className="text-muted-foreground">Not in storage</span>;
  const spot = `${first.unit_name} / ${first.box_name} ${first.position}`;
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <span>
        {s.tubes.length > 1 ? `${s.tubes.length} tubes, first in ${spot}` : `1 tube in ${spot}`}
      </span>
      {s.tubes.length === 1 && (
        <span
          title={`${personName(first.owner)} holds it`}
          className="rounded-full bg-warning/25 px-2 py-0.5 text-xs font-semibold text-warning-text"
        >
          Last tube
        </span>
      )}
    </span>
  );
}

export function SamplesPage() {
  const { labId = "" } = useParams();
  const { data: lab } = useLab(labId);
  const on = !!lab?.inventory_enabled;
  const canEdit = !!lab?.my_permissions.includes("manage_samples");
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [kind, setKind] = useState("");
  const [status, setStatus] = useState("");
  const [owner, setOwner] = useState("");
  const query = { q: useDebounced(q.trim()), kind, status, owner };
  const list = useSamples(labId, query, on);
  const { remove } = useSampleActions(labId);
  const members = useMembers(labId).data ?? [];
  const [params, setParams] = useSearchParams();
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<Sample | null>(null);
  const [deleting, setDeleting] = useState<Sample | null>(null);
  // the command palette's "Add sample" lands here with ?add=1
  const addFromLink = canEdit && params.get("add") === "1";
  const clearAdd = () =>
    setParams(
      (p) => {
        p.delete("add");
        return p;
      },
      { replace: true },
    );
  const rows = list.data ?? [];
  const filtered = !!(query.q || kind || status || owner);
  const open = (s: Sample) => navigate(s.id);

  const cols: Column<Sample>[] = [
    {
      key: "code",
      header: "Code",
      cell: (s) => (
        <Link
          to={s.id}
          onClick={(e) => e.stopPropagation()}
          className="font-medium underline-offset-2 hover:underline"
        >
          {s.code}
        </Link>
      ),
    },
    {
      key: "name",
      header: "Name",
      cell: (s) => (
        <span>
          {s.name}
          {s.kind === "primer" && s.tm != null && (
            <span className="ml-2 text-xs text-muted-foreground" title="Rough melting temperature">
              Tm {s.tm.toFixed(0)} °C
            </span>
          )}
        </span>
      ),
    },
    { key: "kind", header: "Kind", className: HIDE_NARROW, cell: (s) => labelOf(KINDS, s.kind) },
    { key: "owner", header: "Owner", className: HIDE_NARROWER, cell: (s) => personName(s.owner) },
    { key: "status", header: "Status", cell: (s) => labelOf(STATUSES, s.status) },
    { key: "where", header: "Where", cell: (s) => <Where sample={s} /> },
    ...(canEdit
      ? [
          {
            key: "actions",
            header: "Actions",
            className: "text-right whitespace-nowrap",
            cell: (s: Sample) => (
              <div className="flex justify-end" onClick={(e) => e.stopPropagation()}>
                <MoreMenu
                  label={`More for ${s.code}`}
                  items={[
                    { label: "Edit", onSelect: () => setEditing(s) },
                    { label: "Delete", onSelect: () => setDeleting(s) },
                  ]}
                />
              </div>
            ),
          },
        ]
      : []),
  ];

  return (
    <>
      <PageHeader
        title="Samples"
        description={
          lab
            ? `Plasmids, strains, primers and more that ${lab.name} keeps, and where they are.`
            : undefined
        }
        actions={
          on ? (
            <>
              <Button variant="outline" asChild>
                <Link to="storage">Storage</Link>
              </Button>
              {canEdit && <Button onClick={() => setAdding(true)}>Add sample</Button>}
            </>
          ) : undefined
        }
      />
      {lab && !on && (
        <EmptyState
          title="Samples are turned off"
          description="This lab is set up as a dry lab. A PI or lab admin can turn inventory and samples on in Lab details."
        />
      )}
      {on && (
        <div className="grid gap-4">
          <div className="grid gap-3 sm:flex sm:flex-wrap sm:items-end">
            <div className="sm:w-56">
              <FormField label="Search">
                {(p) => (
                  <div className="relative">
                    <Search
                      aria-hidden
                      className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
                    />
                    <Input
                      {...p}
                      type="search"
                      placeholder="Code or name"
                      className="pl-9"
                      value={q}
                      onChange={(e) => setQ(e.target.value)}
                    />
                  </div>
                )}
              </FormField>
            </div>
            <div className="sm:w-44">
              <FormField label="Kind">
                {(p) => (
                  <NativeSelect {...p} value={kind} onChange={(e) => setKind(e.target.value)}>
                    <option value="">All kinds</option>
                    {KINDS.map((k) => (
                      <option key={k.value} value={k.value}>
                        {k.label}
                      </option>
                    ))}
                  </NativeSelect>
                )}
              </FormField>
            </div>
            <div className="sm:w-44">
              <FormField label="Owner">
                {(p) => (
                  <NativeSelect {...p} value={owner} onChange={(e) => setOwner(e.target.value)}>
                    <option value="">Everyone</option>
                    {members.map((m) => (
                      <option key={m.id} value={m.user.id}>
                        {personName(m.user)}
                      </option>
                    ))}
                  </NativeSelect>
                )}
              </FormField>
            </div>
            <div className="sm:w-40">
              <FormField label="Status">
                {(p) => (
                  <NativeSelect {...p} value={status} onChange={(e) => setStatus(e.target.value)}>
                    <option value="">Any status</option>
                    {STATUSES.map((s) => (
                      <option key={s.value} value={s.value}>
                        {s.label}
                      </option>
                    ))}
                  </NativeSelect>
                )}
              </FormField>
            </div>
            <div className="flex flex-wrap gap-2 sm:ml-auto">
              <Button variant="outline" asChild>
                <a href={sampleExportUrl(labId, query)} download="samples.csv">
                  Export CSV
                </a>
              </Button>
              {canEdit && <ImportSamples labId={labId} />}
            </div>
          </div>
          <DataTable
            columns={cols}
            rows={rows}
            getRowKey={(s) => s.id}
            loading={list.isLoading}
            onRowClick={open}
            empty={
              <EmptyState
                compact
                title={filtered ? "No samples match" : "No samples yet"}
                description={
                  filtered
                    ? "Try a different search or clear a filter."
                    : canEdit
                      ? "Add your plasmids, strains and primers, then put them in a box."
                      : "Only people who manage samples can add them. Ask a PI or lab admin."
                }
                action={
                  canEdit && !filtered ? (
                    <Button onClick={() => setAdding(true)}>Add sample</Button>
                  ) : undefined
                }
              />
            }
          />
        </div>
      )}
      <ConfirmDelete
        open={!!deleting}
        name={deleting?.code ?? ""}
        noun="sample"
        description="A sample that still has tubes in storage can't be deleted. Take the tubes out first, or mark it archived."
        pending={remove.isPending}
        onClose={() => setDeleting(null)}
        onConfirm={() =>
          deleting &&
          remove.mutate(deleting.id, {
            onSuccess: () => toast.success("Sample deleted"),
            onError: (e) => toast.error(formErrors(e, []).form ?? "Could not delete the sample."),
            onSettled: () => setDeleting(null),
          })
        }
      />
      {(adding || addFromLink || editing) && (
        <SampleDialog
          labId={labId}
          sample={editing}
          open
          onClose={() => {
            setAdding(false);
            setEditing(null);
            if (addFromLink) clearAdd();
          }}
        />
      )}
    </>
  );
}
