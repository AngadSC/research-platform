import { Landmark } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router";
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
import { day } from "@/pages/project/workflow/parts";

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
      />
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <label className="flex cursor-pointer items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={soonOnly}
            onChange={(e) => setSoonOnly(e.target.checked)}
          />
          Ends within 90 days
        </label>
        {totals.length > 0 && (
          <p className="text-sm text-muted-foreground" aria-label="Totals">
            Awarded and active: {totals.map(([cur, n]) => money(String(n), cur)).join(" · ")}
          </p>
        )}
      </div>
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
                : "Add funding from a project's Workflow tab and it will show up here."
            }
          />
        }
      />
    </>
  );
}
