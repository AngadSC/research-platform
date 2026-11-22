import { useParams } from "react-router";
import { PageHeader } from "@/components/shared/PageHeader";
import { useGoogleChat } from "@/hooks/googleChat";
import { useLab } from "@/hooks/workspace";
import { GoogleChatSync } from "@/pages/GoogleChatSync";
import { ChatPanel } from "@/pages/project/ChatTab";

/** One group chat for the whole lab: every member reads and posts, viewers included (D206). */
export function LabChatPage() {
  const { labId = "" } = useParams();
  const { data: lab } = useLab(labId);
  const google = useGoogleChat(labId).status.data?.bridge;
  return (
    <>
      <PageHeader title="Lab chat" description={lab ? `Everyone in ${lab.name}.` : undefined} />
      {lab && <GoogleChatSync labId={labId} />}
      {lab && (
        <div className="h-[calc(100dvh-23rem)] min-h-80 md:h-[calc(100dvh-19rem)]">
          <ChatPanel
            inPanel
            key={labId}
            labId={labId}
            canModerate={lab.my_permissions.includes("manage_lab")}
            label="Lab chat"
            audience="this lab"
            alsoSentTo={
              google ? `the Google Chat ${google.space_name || "conversation"}` : undefined
            }
          />
        </div>
      )}
    </>
  );
}
