import { NotebookView } from "@/components/shared/NotebookView";
import type { ProjectTabProps } from "@/pages/ProjectPage";

/** The project's shared notebook: everyone on the project reads it, and whoever can edit adds. */
export default function NotebookTab({ labId, projectId, project }: ProjectTabProps) {
  return (
    <NotebookView
      labId={labId}
      projectId={projectId}
      canWrite={project.my_permissions.includes("edit_content") && project.status !== "archived"}
    />
  );
}
