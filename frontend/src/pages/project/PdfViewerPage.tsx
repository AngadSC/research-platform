import { Download } from "lucide-react";
import { Link, useParams } from "react-router";
import { PageHeader } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
import { paperPdfUrl, usePaper } from "@/hooks/papers";
import { downloadUrl, useAttachment } from "@/hooks/projects";
import PdfView from "@/pages/project/PdfView";

export default function PdfViewerPage() {
  const {
    labId = "",
    projectId = "",
    approvalId = "",
    attachmentId = "",
    paperId = "",
  } = useParams();
  const back = paperId
    ? { to: `/labs/${labId}/papers/${paperId}`, label: "Back to paper" }
    : approvalId
      ? { to: `/labs/${labId}/ethics/${approvalId}`, label: "Back to approval" }
      : { to: `/labs/${labId}/projects/${projectId}/documents`, label: "Back to files" };
  const url = paperId ? paperPdfUrl(labId, paperId) : downloadUrl(labId, attachmentId);
  const { data: att } = useAttachment(labId, attachmentId);
  const { data: paper } = usePaper(labId, paperId);
  return (
    <div className="grid gap-4">
      <PageHeader
        title={att?.original_filename ?? paper?.title ?? "File"}
        actions={
          <>
            <Button variant="outline" asChild>
              <Link to={back.to}>{back.label}</Link>
            </Button>
            <Button variant="outline" asChild>
              <a href={url} download>
                <Download aria-hidden /> Download
              </a>
            </Button>
          </>
        }
      />
      <PdfView url={url} />
    </div>
  );
}
