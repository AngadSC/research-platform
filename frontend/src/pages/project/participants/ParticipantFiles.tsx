import { FileUp, Search, TriangleAlert } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { FromDriveButton } from "@/components/shared/FromDriveButton";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { useAttachments } from "@/hooks/projects";
import type { useRegistry } from "@/hooks/participants";
import type { RegistryCell, RegistryColumn, RegistryParticipant } from "@/lib/api-types";
import { formErrors } from "@/lib/forms";
import { readFileText, scanFile, type ScanResult } from "@/lib/participantScan";
import { UploadDialog } from "@/pages/project/UploadDialog";

type Registry = ReturnType<typeof useRegistry>;

interface Added {
  name: string;
  url: string;
  scan: ScanResult;
}

/**
 * Add a file to one participant, from this computer or from Drive. The file is read here in the
 * browser (text, CSV and PDF files; Word and other files go by their name) and compared with the
 * participant's entries. The person then confirms which entries it fills. Nothing about the file's
 * contents is sent to an AI tool.
 */
export function ParticipantFiles({
  labId,
  projectId,
  participant,
  columns,
  cellOf,
  registry,
}: {
  labId: string;
  projectId: string;
  participant: RegistryParticipant;
  columns: RegistryColumn[];
  cellOf: (componentId: string) => RegistryCell | undefined;
  registry: Registry;
}) {
  const { uploadFile } = useAttachments(labId, projectId);
  const input = useRef<HTMLInputElement>(null);
  const text = useRef<Promise<string | undefined>>(Promise.resolve(undefined));
  const sent = useRef<{ id: string; name: string } | null>(null);
  const [chosen, setChosen] = useState<File | null>(null);
  const [added, setAdded] = useState<Added | null>(null);
  const [reading, setReading] = useState(false);

  const scan = async (name: string, readable?: string) =>
    scanFile({
      fileName: name,
      text: readable,
      columns,
      participantCode: participant.code,
    });

  async function afterUpload() {
    const done = sent.current;
    sent.current = null;
    setChosen(null);
    if (!done) return; // cancelled
    setReading(true);
    try {
      const result = await scan(done.name, await text.current);
      setAdded({
        name: done.name,
        url: `${window.location.origin}/labs/${labId}/projects/${projectId}/files/${done.id}`,
        scan: result,
      });
    } finally {
      setReading(false);
    }
  }

  return (
    <section
      aria-label="Add a file"
      className="flex flex-wrap items-center gap-3 rounded-lg border bg-card px-4 py-3"
    >
      <div className="min-w-48 flex-1">
        <h2 className="text-sm font-semibold">Add a file for {participant.code}</h2>
        <p className="text-sm text-muted-foreground">
          We read it here and suggest which entries it fills. You confirm before anything changes.
        </p>
      </div>
      <input
        ref={input}
        type="file"
        aria-label="Choose a file for this participant"
        className="sr-only"
        tabIndex={-1}
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (!file) return;
          text.current = readFileText(file); // starts reading while the upload question is answered
          setChosen(file);
        }}
      />
      <Button variant="outline" size="sm" disabled={reading} onClick={() => input.current?.click()}>
        <FileUp aria-hidden /> Upload a file
      </Button>
      <FromDriveButton
        labId={labId}
        quiet
        onPick={async (file) => {
          const name = file.name;
          const url = file.url ?? `https://drive.google.com/file/d/${file.id}/view`;
          setAdded({ name, url, scan: await scan(name) });
        }}
      />

      <UploadDialog
        open={chosen !== null}
        onOpenChange={(open) => !open && void afterUpload()}
        participant
        initialFiles={chosen ? [chosen] : []}
        send={async (file, onProgress, flagged) => {
          const a = await uploadFile.mutateAsync({ file, onProgress, participant: flagged });
          sent.current = { id: a.id, name: file.name };
        }}
      />
      {added && (
        <ReviewDialog
          key={added.url}
          added={added}
          participant={participant}
          columns={columns}
          cellOf={cellOf}
          registry={registry}
          onClose={() => setAdded(null)}
        />
      )}
    </section>
  );
}

function ReviewDialog({
  added,
  participant,
  columns,
  cellOf,
  registry,
  onClose,
}: {
  added: Added;
  participant: RegistryParticipant;
  columns: RegistryColumn[];
  cellOf: (componentId: string) => RegistryCell | undefined;
  registry: Registry;
  onClose: () => void;
}) {
  const { scan } = added;
  const suggested = scan.matches;
  const suggestedIds = new Set(suggested.map((m) => m.componentId));
  const others = columns.filter((c) => !suggestedIds.has(c.id));
  // A file that names another participant is not ticked for anything: the person decides.
  const wrongPerson = scan.otherCodes.length > 0 && !scan.hasOwnCode;
  const [ticked, setTicked] = useState<Set<string>>(
    () =>
      new Set(
        wrongPerson
          ? []
          : suggested.filter((m) => m.confidence === "sure").map((m) => m.componentId),
      ),
  );
  const [markDone, setMarkDone] = useState(true);
  const [showOthers, setShowOthers] = useState(suggested.length === 0);
  const [busy, setBusy] = useState(false);

  const toggle = (id: string) =>
    setTicked((s) => {
      const next = new Set(s);
      if (!next.delete(id)) next.add(id);
      return next;
    });

  async function apply() {
    setBusy(true);
    let done = 0;
    try {
      for (const id of ticked) {
        const cell = cellOf(id);
        const real = cell && !cell.id.startsWith("pending") ? cell : undefined;
        const finish = markDone && real?.status !== "complete";
        const target =
          real && !finish
            ? real
            : await registry.setCell.mutateAsync({
                participant: participant.id,
                component: id,
                patch: { status: finish ? "complete" : (real?.status ?? "not_started") },
              });
        await registry.addFile.mutateAsync({ cell: target.id, url: added.url, title: added.name });
        done++;
      }
      toast.success(
        done === 1 ? `Added to 1 entry for ${participant.code}` : `Added to ${done} entries`,
      );
      onClose();
    } catch (e) {
      toast.error(
        `${done ? `Added to ${done}, then stopped. ` : ""}${formErrors(e, []).form ?? "Could not add the file."}`,
      );
    } finally {
      setBusy(false);
    }
  }

  const row = (c: { id: string; name: string }, note?: string) => (
    <li key={c.id}>
      <label className="flex cursor-pointer items-start gap-2 rounded-md px-2 py-1.5 hover:bg-muted/60">
        <input
          type="checkbox"
          className="mt-1"
          checked={ticked.has(c.id)}
          onChange={() => toggle(c.id)}
        />
        <span className="min-w-0 flex-1">
          <span className="font-medium">{c.name}</span>
          {note && <span className="block text-xs text-muted-foreground">{note}</span>}
        </span>
      </label>
    </li>
  );

  return (
    <Dialog open onOpenChange={(open) => !open && !busy && onClose()}>
      <DialogContent>
        <DialogTitle className="text-base font-semibold">Which entries does this fill?</DialogTitle>
        <DialogDescription className="text-sm text-muted-foreground">
          {scan.basis === "text"
            ? `Read "${added.name}" and compared it with ${participant.code}'s entries.`
            : `"${added.name}" could not be read here, so this goes by the file name. Check the choices.`}
        </DialogDescription>

        {wrongPerson && (
          <p
            role="alert"
            className="flex items-start gap-2 rounded-md border border-warning bg-warning/15 p-3 text-sm"
          >
            <TriangleAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
            <span>
              This file mentions {scan.otherCodes.join(", ")} and not {participant.code}. It may
              belong to someone else, so nothing is ticked.
            </span>
          </p>
        )}

        {suggested.length > 0 ? (
          <div className="grid gap-1">
            <h3 className="text-sm font-medium">Suggested</h3>
            <ul className="grid gap-0.5">
              {suggested.map((m) =>
                row(
                  { id: m.componentId, name: m.name },
                  `${m.confidence === "sure" ? "Found" : "Might fit"} ${m.found}`,
                ),
              )}
            </ul>
          </div>
        ) : (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Search aria-hidden className="size-4" /> Nothing in the file matched an entry. Choose
            where it belongs.
          </p>
        )}

        {others.length > 0 && (
          <div className="grid gap-1">
            {suggested.length > 0 && (
              <Button
                variant="ghost"
                size="sm"
                className="justify-start"
                aria-expanded={showOthers}
                onClick={() => setShowOthers((v) => !v)}
              >
                {showOthers ? "Hide other entries" : `Other entries (${others.length})`}
              </Button>
            )}
            {showOthers && (
              <ul className="grid max-h-48 gap-0.5 overflow-y-auto">{others.map((c) => row(c))}</ul>
            )}
          </div>
        )}

        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={markDone}
            onChange={(e) => setMarkDone(e.target.checked)}
          />
          Also mark these entries complete
        </label>

        <div className="flex justify-end gap-2">
          <Button variant="outline" disabled={busy} onClick={onClose}>
            Skip
          </Button>
          <Button disabled={busy || ticked.size === 0} onClick={() => void apply()}>
            {ticked.size > 1 ? `Add to ${ticked.size} entries` : "Add to entry"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
