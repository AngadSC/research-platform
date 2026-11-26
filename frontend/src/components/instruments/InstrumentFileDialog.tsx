import { useState } from "react";
import { useNavigate } from "react-router";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { parseLine, useInstrumentFile } from "@/hooks/instruments";
import { downloadUrl } from "@/hooks/projects";
import { upload } from "@/lib/api";
import type { Attachment, InstrumentFileDetail } from "@/lib/api-types";
import { InstrumentFilePreview, type InstrumentSummary } from "./index";

/**
 * Saves the preview's table as a CSV next to the instrument file (same project, same participant
 * mark) and opens the project's Analyse page on it, which reads project files by id (D305).
 */
async function analyseCsv(labId: string, f: InstrumentFileDetail, csv: string) {
  const name = `${f.filename.replace(/\.[^.]*$/, "") || "instrument data"} (table).csv`;
  const form = new FormData();
  form.append("file", new File([csv], name, { type: "text/csv" }));
  form.append("acknowledged_notice", "true");
  if (f.contains_participant_data) form.append("contains_participant_data", "true");
  return upload<Attachment>(`/api/labs/${labId}/projects/${f.project.id}/attachments/`, form);
}

/** A small "Instrument data" badge, for the project's file list. */
export function InstrumentBadge({ name }: { name: string }) {
  return (
    <Badge variant="secondary" title={`Sent from ${name}`}>
      Instrument data · {name}
    </Badge>
  );
}

/** The file's parsed preview, with a download. Polls while it is still being read. */
export function InstrumentFileDialog({
  labId,
  fileId,
  onClose,
}: {
  labId: string;
  fileId: string | null;
  onClose: () => void;
}) {
  const { data: f } = useInstrumentFile(labId, fileId);
  const navigate = useNavigate();
  const [saving, setSaving] = useState(false);
  const useCsv = (csv: string) => {
    if (!f || saving) return;
    setSaving(true);
    analyseCsv(labId, f, csv).then(
      (a) => void navigate(`/labs/${labId}/projects/${f.project.id}/analyse?file=${a.id}`),
      () => {
        setSaving(false);
        toast.error(
          "Could not save the table to the project. You may not be able to add files there.",
        );
      },
    );
  };
  return (
    <Dialog open={!!fileId} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-3xl">
        <DialogTitle className="truncate text-base font-semibold">
          {f?.filename ?? "Instrument file"}
        </DialogTitle>
        <DialogDescription className="text-sm text-muted-foreground">
          {f ? `${f.instrument.name} · ${f.project.name}` : "Loading"}
        </DialogDescription>
        {!f ? (
          <div className="grid gap-2" aria-busy="true">
            <Skeleton className="h-4 w-1/2" />
            <Skeleton className="h-32 w-full" />
          </div>
        ) : f.status === "pending" ? (
          <p className="text-sm text-muted-foreground">{parseLine(f)}</p>
        ) : (
          <InstrumentFilePreview summary={f.summary as InstrumentSummary} onUseCsv={useCsv} />
        )}
        {f && (
          <div className="flex justify-end">
            <Button variant="outline" asChild>
              <a href={downloadUrl(labId, f.attachment)} download>
                Download
              </a>
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
