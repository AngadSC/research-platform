import { useState } from "react";
import { Link, useParams } from "react-router";
import { DropZone } from "@/components/instruments/DropZone";
import { InstrumentFileDialog } from "@/components/instruments/InstrumentFileDialog";
import { EmptyState } from "@/components/shared/EmptyState";
import { FormField } from "@/components/shared/FormField";
import { PageHeader } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useInventory } from "@/hooks/admin";
import {
  dropFile,
  parseLine,
  useContributableProjects,
  useInstrumentFile,
} from "@/hooks/instruments";
import type { InstrumentFile } from "@/lib/api-types";
import { NativeSelect } from "@/pages/admin/common";

/** How reading one sent file went; polls until it is done. */
function Parsed({ labId, file }: { labId: string; file: InstrumentFile }) {
  const { data } = useInstrumentFile(labId, file.id);
  const [open, setOpen] = useState(false);
  const f = data ?? file;
  return (
    <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
      <span>{parseLine(f)}</span>
      {f.status !== "pending" && (
        <Button variant="ghost" size="sm" onClick={() => setOpen(true)}>
          Preview
        </Button>
      )}
      <InstrumentFileDialog
        labId={labId}
        fileId={open ? f.id : null}
        onClose={() => setOpen(false)}
      />
    </div>
  );
}

/** What the QR sticker opens: pick a project, drop files, see them read. */
export function DropPage() {
  const { labId = "", itemId = "" } = useParams();
  const inv = useInventory(labId, { category: "equipment" });
  const item = inv.list.data?.find((i) => i.id === itemId);
  const { projects, isLoading } = useContributableProjects(labId);
  const [project, setProject] = useState("");
  const chosen = project || (projects.length === 1 ? projects[0]!.id : "");

  if (inv.list.isLoading || isLoading)
    return (
      <div className="grid gap-3" aria-busy="true" aria-label="Loading">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-40 w-full max-w-2xl" />
      </div>
    );
  if (!item)
    return (
      <EmptyState
        title="Instrument not found"
        description="It may have been removed, or it is not equipment."
        action={
          <Button asChild variant="outline">
            <Link to={`/labs/${labId}/inventory`}>Back to Inventory</Link>
          </Button>
        }
      />
    );
  if (!projects.length)
    return (
      <EmptyState
        title="No project to send files to"
        description="You need to be able to add files to a project. Ask a project lead to add you, or start a project."
        action={
          <Button asChild variant="outline">
            <Link to={`/labs/${labId}/projects`}>Go to projects</Link>
          </Button>
        }
      />
    );
  return (
    <div className="grid max-w-2xl gap-4">
      <PageHeader
        title={`Send files from ${item.name}`}
        description="They go into the project's Instrument data folder and are read for a preview."
      />
      <FormField label="Project">
        {(p) => (
          <NativeSelect {...p} value={chosen} onChange={(e) => setProject(e.target.value)}>
            <option value="">Choose a project</option>
            {projects.map((pr) => (
              <option key={pr.id} value={pr.id}>
                {pr.name}
              </option>
            ))}
          </NativeSelect>
        )}
      </FormField>
      <DropZone<InstrumentFile>
        disabled={!chosen}
        disabledHint="Choose a project first."
        send={(file, participant, onProgress) =>
          dropFile(labId, chosen, item.id, file, participant, onProgress)
        }
        renderDone={(f) => <Parsed labId={labId} file={f} />}
      />
      <Link
        to={`/labs/${labId}/instruments/${item.id}`}
        className="text-sm text-muted-foreground underline-offset-2 hover:underline"
      >
        All files from {item.name}
      </Link>
    </div>
  );
}
