import { Landmark } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { useIsPhone } from "@/hooks/media";
import { useProjects } from "@/hooks/projects";
import { DataTable, type Column } from "@/components/shared/DataTable";
import { EmptyState } from "@/components/shared/EmptyState";
import { FormError } from "@/components/shared/FormError";
import { PageHeader } from "@/components/shared/PageHeader";
import { Badge } from "@/components/ui/badge";
import { useLabFunding } from "@/hooks/workflow";
import { useLab } from "@/hooks/workspace";
import type { FundingOverview } from "@/lib/api-types";
import { formErrors } from "@/lib/forms";
import { localDateISO } from "@/lib/format";
import { FUNDING_STATUSES, label, money, WORKFLOW_TONE } from "@/lib/workflow";
import { day, NativeSelect } from "@/pages/project/workflow/parts";

const SOON_DAYS = 90;
const LIVE = ["awarded", "active"];

/** Whole days from today until an ISO date (negative once past). */
const daysUntil = (iso: string) =>
  Math.round(
    (new Date(`${iso}T00:00:00`).getTime() - new Date(`${localDateISO()}T00:00:00`).getTime()) /
      86_400_000,
  );

/** An award that is awarded or active and ends today or within the next 90 days. */
const endsSoon = (f: Pick<FundingOverview, "status" | "end_date">) =>
  LIVE.includes(f.status) &&
  !!f.end_date &&
  daysUntil(f.end_date) >= 0 &&
  daysUntil(f.end_date) <= SOON_DAYS;

const REPORT_DAYS = 30;

/** A report due today or within the next 30 days. */
const reportSoon = (f: Pick<FundingOverview, "report_due">) =>
  !!f.report_due && daysUntil(f.report_due) >= 0 && daysUntil(f.report_due) <= REPORT_DAYS;

/** Amount minus spent, only when both are recorded. */
const remaining = (f: Pick<FundingOverview, "amount" | "spent" | "currency">) =>
  f.amount !== null && f.spent !== null
    ? money(String(Number(f.amount) - Number(f.spent)), f.currency)
    : null;

const reportText = (f: Pick<FundingOverview, "report_due">) =>
  daysUntil(f.report_due!) === 0
    ? "Report due today"
    : `Report due in ${daysUntil(f.report_due!)} days`;

/** Awarded and active money, added up per currency. Applied, closed and declined are not money yet. */
function totalsByCurrency(rows: FundingOverview[]) {
  const totals = new Map<string, number>();
  for (const f of rows)
    if (LIVE.includes(f.status) && f.amount !== null)
      totals.set(f.currency, (totals.get(f.currency) ?? 0) + Number(f.amount));
  return [...totals];
}

/** Funding across every project, for PIs (D226). The server refuses anyone else. */
export function FundingPage() {
  const { labId = "" } = useParams();
  const { data: lab } = useLab(labId);
  const allowed = lab?.my_permissions.includes("access_funding") ?? false;
  const { data, isLoading, error } = useLabFunding(labId, allowed);
  const [soonOnly, setSoonOnly] = useState(false);
  const [adding, setAdding] = useState(false);
  const phone = useIsPhone();

  if (lab && !allowed)
    return (
      <>
        <PageHeader title="Funding" />
        <EmptyState
          icon={Landmark}
          title="Funding is visible to PIs only"
          description="Ask your lab's PI if you need to know how a project is funded."
        />
      </>
    );
  if (error) return <FormError message={formErrors(error, []).form} />;

  const all = data ?? [];
  const rows = soonOnly ? all.filter(endsSoon) : all;
  const totals = totalsByCurrency(rows);
  const columns: Column<FundingOverview>[] = [
    {
      key: "award",
      header: "Award",
      cell: (f) => (
        <span className="grid">
          {reportSoon(f) && (
            <Badge variant="warning" className="mb-1 w-fit">
              {reportText(f)}
            </Badge>
          )}
          <span className="font-medium">{f.funder}</span>
          <span className="text-xs text-muted-foreground">
            {[f.program, f.award_number].filter(Boolean).join(" · ")}
          </span>
        </span>
      ),
    },
    {
      key: "project",
      header: "Project",
      cell: (f) => (
        <Link
          to={`/labs/${labId}/projects/${f.project_id}/workflow/funding`}
          className="underline-offset-2 hover:underline"
        >
          {f.project_name}
        </Link>
      ),
    },
    {
      key: "amount",
      header: "Amount",
      className: "text-right",
      cell: (f) => (
        <span className="tabular-nums">
          {money(f.amount, f.currency) ?? <span className="text-muted-foreground">Not set</span>}
        </span>
      ),
    },
    {
      key: "remaining",
      header: "Remaining",
      className: "text-right",
      cell: (f) => <span className="tabular-nums">{remaining(f) ?? "-"}</span>,
    },
    {
      key: "report",
      header: "Report due",
      cell: (f) => (f.report_due ? day(f.report_due) : "-"),
    },
    { key: "start", header: "Starts", cell: (f) => day(f.start_date) },
    {
      key: "end",
      header: "Ends",
      cell: (f) => (
        <span className="flex flex-wrap items-center gap-2">
          {day(f.end_date)}
          {endsSoon(f) && (
            <Badge variant="warning">
              {daysUntil(f.end_date!) === 0
                ? "Ends today"
                : `Ends in ${daysUntil(f.end_date!)} days`}
            </Badge>
          )}
        </span>
      ),
    },
    {
      key: "status",
      header: "Status",
      cell: (f) => (
        <Badge variant={WORKFLOW_TONE[f.status] ?? "secondary"}>
          {label(FUNDING_STATUSES, f.status)}
        </Badge>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        title="Funding"
        description="Every award across your projects. Only PIs can see this page."
        actions={<Button onClick={() => setAdding(true)}>Add funding</Button>}
      />
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <label className="flex cursor-pointer items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={soonOnly}
            onChange={(e) => setSoonOnly(e.target.checked)}
            className="size-4 accent-primary"
          />
          Ends within 90 days
        </label>
        {totals.length > 0 && (
          <p className="text-sm text-muted-foreground" aria-label="Totals">
            Awarded and active: {totals.map(([cur, n]) => money(String(n), cur)).join(" · ")}
          </p>
        )}
      </div>
      {phone && !isLoading && rows.length > 0 ? (
        <ul className="grid gap-2" aria-label="Awards">
          {rows.map((f) => (
            <li key={f.id} className="grid gap-1 rounded-lg border p-3 text-sm">
              {reportSoon(f) && (
                <Badge variant="warning" className="w-fit">
                  {reportText(f)}
                </Badge>
              )}
              <div className="flex items-start justify-between gap-2">
                <span className="font-medium">{f.funder}</span>
                <Badge variant={WORKFLOW_TONE[f.status] ?? "secondary"}>
                  {label(FUNDING_STATUSES, f.status)}
                </Badge>
              </div>
              <Link
                to={`/labs/${labId}/projects/${f.project_id}/workflow/funding`}
                className="w-fit text-muted-foreground underline-offset-2 hover:underline"
              >
                {f.project_name}
              </Link>
              <p className="tabular-nums">
                {money(f.amount, f.currency) ?? "Amount not set"}
                {remaining(f) && ` · ${remaining(f)} left`}
              </p>
              <p className="text-muted-foreground">
                Ends {day(f.end_date)}
                {endsSoon(f) &&
                  ` (${daysUntil(f.end_date!) === 0 ? "today" : `in ${daysUntil(f.end_date!)} days`})`}
                {f.report_due && ` · Report due ${day(f.report_due)}`}
              </p>
            </li>
          ))}
        </ul>
      ) : (
        <DataTable
          columns={columns}
          rows={rows}
          getRowKey={(f) => f.id}
          loading={isLoading || !lab}
          empty={
            <EmptyState
              icon={Landmark}
              title={soonOnly ? "Nothing ends in the next 90 days" : "No funding recorded yet"}
              description={
                soonOnly
                  ? "Untick the filter to see every award."
                  : "Add an award to a project and it will show up here."
              }
              action={
                soonOnly ? undefined : <Button onClick={() => setAdding(true)}>Add funding</Button>
              }
            />
          }
        />
      )}
      <AddFundingDialog open={adding} onClose={() => setAdding(false)} labId={labId} />
    </>
  );
}

/** Pick a project, then land on its Funding step with the form open. Link only, no new endpoint. */
function AddFundingDialog({
  open,
  onClose,
  labId,
}: {
  open: boolean;
  onClose: () => void;
  labId: string;
}) {
  const projects = (useProjects(labId).data ?? []).filter((p) => p.status !== "archived");
  const [picked, setPicked] = useState("");
  const id = picked || projects[0]?.id;
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogTitle className="text-base font-semibold">Add funding</DialogTitle>
        <DialogDescription className="text-sm text-muted-foreground">
          Awards belong to a project. Pick the project this award pays for.
        </DialogDescription>
        {projects.length === 0 ? (
          <p className="text-sm text-muted-foreground">Create a project first.</p>
        ) : (
          <NativeSelect aria-label="Project" value={id} onChange={(e) => setPicked(e.target.value)}>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </NativeSelect>
        )}
        <div className="flex justify-end gap-2">
          <DialogClose asChild>
            <Button variant="outline">Cancel</Button>
          </DialogClose>
          {id && (
            <Button asChild>
              <Link to={`/labs/${labId}/projects/${id}/workflow/funding?new=1`}>Continue</Link>
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
