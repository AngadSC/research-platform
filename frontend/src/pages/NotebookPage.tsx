import { useParams } from "react-router";
import { NotebookView } from "@/components/shared/NotebookView";
import { PageHeader } from "@/components/shared/PageHeader";
import { useLab } from "@/hooks/workspace";

/** Your own notebook in this lab. Nobody else, not even a PI, can read it (D330). */
export function NotebookPage() {
  const { labId = "" } = useParams();
  const lab = useLab(labId).data;
  return (
    <>
      <PageHeader
        title="My notebook"
        description="Your own dated entries. Only you can read this. Share a result by writing it in a project's notebook."
      />
      <NotebookView labId={labId} canWrite={!!lab?.my_permissions.includes("contribute_lab")} />
    </>
  );
}
