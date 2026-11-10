import { ShieldAlert } from "lucide-react";
import { useParams } from "react-router";
import { EmptyState } from "@/components/shared/EmptyState";
import { PageHeader } from "@/components/shared/PageHeader";
import { HashTabs } from "@/components/shared/TabNav";
import { Skeleton } from "@/components/ui/skeleton";
import { useLab } from "@/hooks/workspace";
import { AiPolicySection } from "@/pages/settings/AiPolicySection";
import { LabDetailsSection } from "./LabDetailsSection";
import { OnboardingSection } from "./OnboardingSection";
import { ResourcesEditor } from "./ResourcesEditor";

export function AdminPage() {
  const { labId = "" } = useParams();
  const { data: lab, isLoading } = useLab(labId);
  const header = (
    <PageHeader title="Lab details" description="Lab information, onboarding, links and AI." />
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
          title="You don't have access to Lab details"
          description="Ask a PI or lab admin if you need something changed."
        />
      </>
    );

  return (
    <>
      {header}
      <HashTabs
        label="Lab details sections"
        tabs={[
          { id: "about", label: "About", content: <LabDetailsSection lab={lab} /> },
          { id: "onboarding", label: "Onboarding", content: <OnboardingSection labId={labId} /> },
          { id: "links", label: "Links", content: <ResourcesEditor labId={labId} /> },
          { id: "ai", label: "AI", content: <AiPolicySection labId={labId} labName={lab.name} /> },
        ]}
      />
    </>
  );
}
