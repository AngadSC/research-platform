import { ShieldAlert } from "lucide-react";
import { Link, useParams } from "react-router";
import { EmptyState } from "@/components/shared/EmptyState";
import { PageHeader } from "@/components/shared/PageHeader";
import { Skeleton } from "@/components/ui/skeleton";
import { useLab } from "@/hooks/workspace";
import { InventorySection } from "./InventorySection";
import { LabDetailsSection } from "./LabDetailsSection";
import { OnboardingSection } from "./OnboardingSection";
import { ResourcesEditor } from "./ResourcesEditor";
import { TrainingSection } from "./TrainingSection";
import { Section } from "./common";

const LINKS = [
  { path: "ethics", label: "Ethics approvals", hint: "Every approval in the lab" },
  { path: "audit-log", label: "Audit log", hint: "Who did what, and when" },
  { path: "retention", label: "Retention review", hint: "Projects and documents past their date" },
  { path: "members", label: "Members", hint: "Invite people and change roles" },
  {
    path: "settings/integrations",
    label: "Integrations",
    hint: "Connected accounts and providers",
  },
];

export function AdminPage() {
  const { labId = "" } = useParams();
  const { data: lab, isLoading } = useLab(labId);
  const header = (
    <PageHeader title="Admin" description="Lab details, turnover, inventory and tools." />
  );

  if (isLoading || !lab)
    return (
      <>
        {header}
        <Skeleton className="h-40 w-full" />
      </>
    );
  // The server decides: manage_lab is held by pi and lab_admin only.
  if (!lab.my_permissions.includes("manage_lab"))
    return (
      <>
        {header}
        <EmptyState
          icon={ShieldAlert}
          title="You don't have access to Admin"
          description="Ask a PI or lab admin if you need something changed."
        />
      </>
    );

  return (
    <>
      {header}
      <div className="grid gap-8">
        <Section title="Admin tools" description="Everything that manages the lab, in one place.">
          <ul className="grid gap-2 sm:grid-cols-2">
            {LINKS.map((l) => (
              <li key={l.path}>
                <Link
                  to={`/labs/${labId}/${l.path}`}
                  className="block rounded-md border p-3 hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                >
                  <span className="font-medium">{l.label}</span>
                  <span className="block text-xs text-muted-foreground">{l.hint}</span>
                </Link>
              </li>
            ))}
          </ul>
        </Section>
        <LabDetailsSection lab={lab} />
        <OnboardingSection labId={labId} />
        <TrainingSection labId={labId} />
        <InventorySection labId={labId} canEdit={lab.my_permissions.includes("manage_inventory")} />
        <ResourcesEditor labId={labId} />
      </div>
    </>
  );
}
