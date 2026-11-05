import { Navigate, Outlet, useLocation, useParams } from "react-router";
import { isKind } from "@/lib/research";
import { TabNav } from "@/components/shared/TabNav";
import { SECTIONS, sectionOf } from "@/lib/workflow";
import type { ProjectTabProps } from "@/pages/ProjectPage";
import { SectionLists } from "@/pages/project/ResearchTab";

/** The Workflow tab: Funding, Ethics, Participants, Data, Analysis, Manuscript, Review (D132). */
export function WorkflowLayout(props: ProjectTabProps) {
  return (
    <div className="grid gap-6">
      <TabNav label="Workflow sections" tabs={SECTIONS} />
      <Outlet context={props} />
    </div>
  );
}

export const WorkflowIndex = () => <Navigate to="funding" replace />;

export const DataTab = (p: ProjectTabProps) => <SectionLists {...p} section="data" />;
export const AnalysisTab = (p: ProjectTabProps) => <SectionLists {...p} section="analysis" />;
export const ManuscriptTab = (p: ProjectTabProps) => <SectionLists {...p} section="manuscript" />;

/** `/research/<kind>[/new|/<id>]` from before the Workflow tab goes to its new place (D132). */
export function ResearchRedirect() {
  const { labId, projectId, "*": rest = "" } = useParams();
  const { search } = useLocation();
  const [kind, ...tail] = rest.split("/").filter(Boolean);
  const base = `/labs/${labId}/projects/${projectId}/workflow`;
  const to = isKind(kind)
    ? [base, sectionOf(kind), ...(tail.length ? [kind, ...tail] : [])].join("/")
    : `${base}/data`;
  return <Navigate to={to + search} replace />;
}
