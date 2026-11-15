import { useState } from "react";
import { Link } from "react-router";
import { toast } from "sonner";
import { FormError } from "@/components/shared/FormError";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAttachments } from "@/hooks/projects";
import { useSaveRecord } from "@/hooks/research";
import type { Analysis, ResearchResult } from "@/lib/api-types";
import type { StatsResult } from "@/lib/stats/contract";
import { svgToPng } from "@/pages/project/analyse/png";
import { errorText, saveRun, type SaveOutcome } from "@/pages/project/analyse/save";
import { ParticipantChoice } from "@/pages/project/UploadDialog";

interface Props {
  labId: string;
  projectId: string;
  result: StatsResult;
  inputName: string;
  datasetId?: string;
  /** true or false when the source file says; null for a file from this computer (ask). */
  flagged: boolean | null;
  getSvgs: () => SVGSVGElement[];
  onClose: () => void;
  onSaved: (o: SaveOutcome) => void;
}

function SaveForm({
  labId,
  projectId,
  result,
  inputName,
  datasetId,
  flagged,
  getSvgs,
  onClose,
  onSaved,
}: Props) {
  const { uploadFile, editInGoogle } = useAttachments(labId, projectId);
  const analyses = useSaveRecord<Analysis>(labId, projectId, "analyses");
  const results = useSaveRecord<ResearchResult>(labId, projectId, "results");
  const [title, setTitle] = useState(result.title);
  const [choice, setChoice] = useState<boolean | null>(flagged);
  const [ethics, setEthics] = useState(false);
  const [toDrive, setToDrive] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const marked = choice === true;
  const ready = !!title.trim() && choice !== null && (!marked || ethics);

  async function save() {
    setBusy(true);
    setError(undefined);
    try {
      const out = await saveRun(
        {
          result,
          title: title.trim(),
          inputName,
          datasetId,
          participant: marked,
          svgs: getSvgs(),
          chartTitles: result.charts.map((c) => c.title),
          toDrive,
        },
        {
          upload: (file, participant) => uploadFile.mutateAsync({ file, participant }),
          createAnalysis: (b) => analyses.mutateAsync(b),
          createResult: (b) => results.mutateAsync(b),
          editInGoogle: (id) => editInGoogle.mutateAsync(id),
          toPng: svgToPng,
        },
      );
      toast.success("Saved to the project", {
        description: out.driveError
          ? undefined
          : out.copy
            ? "A Google Sheet copy is in your Drive."
            : undefined,
      });
      onSaved(out);
      onClose();
    } catch (e) {
      setError(errorText(e));
      setBusy(false);
    }
  }

  return (
    <>
      <DialogTitle className="text-base font-semibold">Save to project</DialogTitle>
      <DialogDescription className="text-sm text-muted-foreground">
        {marked
          ? "Adds the results workbook, the Python code and the charts as project files. AI tools can read analysis and result records, so none is made for data that identifies participants."
          : "Adds the results workbook, the Python code and the charts as project files, and records an analysis and a result."}
      </DialogDescription>
      <div className="grid gap-1.5">
        <Label htmlFor="save-title">Title</Label>
        <Input id="save-title" value={title} onChange={(e) => setTitle(e.target.value)} />
      </div>
      {flagged === null ? (
        <ParticipantChoice value={choice} onChange={setChoice} />
      ) : (
        marked && (
          <p role="note" className="rounded-md border bg-muted p-3 text-sm">
            The data file identifies participants, so the saved files will carry the same mark.
            Claude and other AI tools will never see them.
          </p>
        )
      )}
      {marked && (
        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            checked={ethics}
            onChange={(e) => setEthics(e.target.checked)}
            className="mt-0.5"
          />
          I confirm my ethics approval allows keeping this identifying participant data here
        </label>
      )}
      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          checked={toDrive}
          onChange={(e) => setToDrive(e.target.checked)}
          className="mt-0.5"
        />
        Also make a Google Sheet copy of the results in my Google Drive
      </label>
      <FormError message={error} />
      {error && /google/i.test(error) && (
        <Link
          className="text-sm text-primary hover:underline"
          to={`/labs/${labId}/settings/integrations`}
        >
          Open Integrations
        </Link>
      )}
      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={onClose} disabled={busy}>
          Cancel
        </Button>
        <Button onClick={() => void save()} disabled={!ready || busy}>
          {busy ? "Saving" : "Save"}
        </Button>
      </div>
    </>
  );
}

export function SaveDialog(props: Props & { open: boolean }) {
  return (
    <Dialog open={props.open} onOpenChange={(o) => !o && props.onClose()}>
      <DialogContent>{props.open && <SaveForm {...props} />}</DialogContent>
    </Dialog>
  );
}
