import { useParams } from "react-router";
import { PageHeader } from "@/components/shared/PageHeader";
import { useLab } from "@/hooks/workspace";
import { ChatPanel } from "@/pages/project/ChatTab";

/** One group chat for the whole lab: every member reads and posts, viewers included (D206). */
export function LabChatPage() {
  const { labId = "" } = useParams();
  const { data: lab } = useLab(labId);
  return (
    <>
      <PageHeader title="Lab chat" description={lab ? `Everyone in ${lab.name}.` : undefined} />
      {lab && (
        <ChatPanel
          key={labId}
          labId={labId}
          canModerate={lab.my_permissions.includes("manage_lab")}
          label="Lab chat"
          audience="this lab"
        />
      )}
    </>
  );
}
