import { useNavigate } from "react-router";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { downloadUrl } from "@/hooks/projects";
import { useRecords, useSaveRecord } from "@/hooks/research";
import type { Analysis, Dataset, ResearchResult } from "@/lib/api-types";
import { formErrors } from "@/lib/forms";
import { recordPath } from "@/lib/workflow";

/** Follow previous_version forward from `id` to the newest version (the latest one if it forks). */
export function newestVersion(all: Dataset[], id: string): Dataset | undefined {
  const seen = new Set([id]);
  let cur = id;
  for (;;) {
    const next = all
      .filter((d) => d.previous_version?.id === cur && !seen.has(d.id))
      .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))[0];
    if (!next) return cur === id ? undefined : all.find((d) => d.id === cur);
    seen.add(next.id);
    cur = next.id;
  }
}

/** There is no code runner yet, so this makes a new record of the same code on newer data. */
export function RunAgain({
  labId,
  projectId,
  base,
  analysis: a,
}: {
  labId: string;
  projectId: string;
  base: string;
  analysis: Analysis;
}) {
  const navigate = useNavigate();
  const datasets = useRecords<Dataset>(labId, projectId, "datasets");
  const save = useSaveRecord<Analysis>(labId, projectId, "analyses");
  if (datasets.isLoading) return <Skeleton className="h-9 w-32" />;
  const all = datasets.data ?? [];
  const ids = a.datasets.map((d) => newestVersion(all, d.id)?.id ?? d.id);
  const hasNewer = a.datasets.some((d) => newestVersion(all, d.id));
  const run = () =>
    save.mutate(
      {
        title: `${a.title} (again)`,
        description: `Run again from "${a.title}".${a.description ? `\n\n${a.description}` : ""}`,
        code_repo_url: a.code_repo_url,
        code_commit: a.code_commit,
        code_attachment: a.code_attachment?.id ?? null,
        datasets: ids,
      },
      {
        onSuccess: (r) => {
          toast.success("Saved a new analysis on the newer data");
          void navigate(recordPath(base, "analyses", r.id));
        },
        onError: (e) => toast.error(formErrors(e, []).form),
      },
    );
  const why = "None of its datasets has a newer version yet.";
  return (
    <span title={hasNewer ? undefined : why} className="inline-flex">
      <Button
        variant="outline"
        disabled={!hasNewer || save.isPending}
        aria-describedby={hasNewer ? undefined : "run-again-why"}
        onClick={run}
      >
        Run again on newer data
      </Button>
      {!hasNewer && (
        <span id="run-again-why" className="sr-only">
          {why}
        </span>
      )}
    </span>
  );
}

export function DownloadCode({ labId, analysis: a }: { labId: string; analysis: Analysis }) {
  if (!a.code_attachment) return null;
  return (
    <Button variant="outline" asChild>
      <a href={downloadUrl(labId, a.code_attachment.id)} download>
        Download code
      </a>
    </Button>
  );
}

const isImage = (t: string) => t.startsWith("image/");

export function AnalysisOutputs({
  labId,
  projectId,
  analysisId,
}: {
  labId: string;
  projectId: string;
  analysisId: string;
}) {
  const results = useRecords<ResearchResult>(labId, projectId, "results");
  const mine = (results.data ?? []).filter((r) => r.analysis?.id === analysisId);
  return (
    <section aria-labelledby="outputs" className="grid gap-3">
      <h2 id="outputs" className="text-sm font-medium">
        Outputs
      </h2>
      {results.isLoading ? (
        <Skeleton className="h-24 w-full" />
      ) : mine.length === 0 ? (
        <p className="text-sm text-muted-foreground">No results have been added yet.</p>
      ) : (
        mine.map((r) => (
          <div key={r.id} className="grid gap-2 rounded-md border p-3 text-sm">
            <p className="font-medium">{r.title}</p>
            {r.summary && <p className="text-muted-foreground">{r.summary}</p>}
            <ul className="flex flex-wrap gap-3">
              {r.attachments.map((f) => (
                <li key={f.id} className="grid gap-1">
                  {isImage(f.content_type) && (
                    <img
                      src={downloadUrl(labId, f.id)}
                      alt={f.original_filename}
                      className="h-24 w-auto rounded border object-contain"
                    />
                  )}
                  <a
                    className="text-primary hover:underline"
                    href={downloadUrl(labId, f.id)}
                    download
                  >
                    {f.original_filename}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        ))
      )}
    </section>
  );
}
