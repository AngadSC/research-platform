import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { parseLine, useInstrumentFile } from "@/hooks/instruments";
import { downloadUrl } from "@/hooks/projects";
import { InstrumentFilePreview, type InstrumentSummary } from "./InstrumentFilePreview";

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
          <InstrumentFilePreview summary={f.summary as InstrumentSummary} />
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
