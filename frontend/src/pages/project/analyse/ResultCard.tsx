import { useRef, useState } from "react";
import { Link } from "react-router";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { recordPath } from "@/lib/workflow";
import { googleEditor } from "@/lib/googleFiles";
import type { StatsResult } from "@/lib/stats/contract";
import { Chart } from "@/pages/project/analyse/charts";
import { svgToPng } from "@/pages/project/analyse/png";
import { SaveDialog } from "@/pages/project/analyse/SaveDialog";
import type { SaveOutcome } from "@/pages/project/analyse/save";

export interface Run {
  id: number;
  result: StatsResult;
  inputName: string;
  datasetId?: string;
  /** Does the data file identify participants? null for a file from this computer. */
  flagged: boolean | null;
  saved?: SaveOutcome;
}

function download(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

async function copy(text: string, what: string) {
  try {
    await navigator.clipboard.writeText(text);
    toast.success(`${what} copied`);
  } catch {
    toast.error("Could not copy. Select the text and copy it yourself.");
  }
}

const fileStem = (r: StatsResult) => r.test.replace(/_/g, "-");

export function ResultCard({
  run,
  labId,
  projectId,
  canSave,
  onSaved,
}: {
  run: Run;
  labId: string;
  projectId: string;
  canSave: boolean;
  onSaved: (o: SaveOutcome) => void;
}) {
  const { result, saved } = run;
  const root = useRef<HTMLElement>(null);
  const [saving, setSaving] = useState(false);
  const svgs = () => Array.from(root.current?.querySelectorAll<SVGSVGElement>("svg.viz") ?? []);
  const base = `/labs/${labId}/projects/${projectId}`;
  const sheet = saved?.copy && googleEditor(saved.copy);

  return (
    <article ref={root} aria-label={result.title} className="grid gap-4 rounded-lg border p-4">
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-base font-semibold">{result.title}</h2>
          <p className="text-xs text-muted-foreground">
            {run.inputName} · {result.n} rows used
          </p>
        </div>
        {canSave && !saved && <Button onClick={() => setSaving(true)}>Save to project</Button>}
      </header>

      <div className="flex items-start gap-2">
        <p className="text-sm">{result.summary}</p>
        <Button variant="ghost" size="sm" onClick={() => void copy(result.summary, "Summary")}>
          Copy
        </Button>
      </div>

      {result.warnings.length > 0 && (
        <ul className="grid gap-1 rounded-md border border-primary/40 bg-primary/10 p-3 text-sm">
          {result.warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}

      {result.tables.map((t) => (
        <div key={t.title} className="grid gap-1 overflow-x-auto">
          <Table>
            <caption className="pb-1 text-left text-sm font-medium">{t.title}</caption>
            <TableHeader>
              <TableRow>
                {t.columns.map((c) => (
                  <TableHead key={c} scope="col">
                    {c}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {t.rows.map((r, i) => (
                <TableRow key={i}>
                  {r.map((v, j) => (
                    <TableCell key={j}>{v ?? ""}</TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {t.note && <p className="text-xs text-muted-foreground">{t.note}</p>}
        </div>
      ))}

      {result.charts.map((c, i) => (
        <figure key={`${c.kind}-${i}`} className="grid gap-1">
          <Chart chart={c} />
          <figcaption className="flex items-center gap-2 text-xs text-muted-foreground">
            {c.title}
            <Button
              variant="ghost"
              size="sm"
              aria-label={`Download chart ${i + 1} as PNG`}
              onClick={() => {
                const svg = svgs()[i];
                if (!svg) return;
                svgToPng(svg).then(
                  (b) => download(b, `${fileStem(result)}-chart-${i + 1}.png`),
                  () => toast.error("The chart could not be turned into a picture."),
                );
              }}
            >
              PNG
            </Button>
          </figcaption>
        </figure>
      ))}

      <details className="rounded-md border p-3">
        <summary className="cursor-pointer text-sm font-medium">Python code</summary>
        <div className="mt-2 grid gap-2">
          <pre className="max-h-80 overflow-auto rounded bg-muted p-3 text-xs">
            <code>{result.code}</code>
          </pre>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => void copy(result.code, "Code")}>
              Copy code
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() =>
                download(
                  new Blob([result.code], { type: "text/x-python" }),
                  `${fileStem(result)}.py`,
                )
              }
            >
              Download .py
            </Button>
          </div>
        </div>
      </details>

      <div className="flex flex-wrap gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={() =>
            download(
              new Blob([result.xlsx as BlobPart], {
                type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
              }),
              `${fileStem(result)}.xlsx`,
            )
          }
        >
          Download results (.xlsx)
        </Button>
      </div>

      {saved && (
        <div role="status" className="grid gap-1 rounded-md border bg-muted p-3 text-sm">
          <p>
            Saved to the project.{" "}
            <Link
              className="text-primary hover:underline"
              to={recordPath(base, "analyses", saved.analysis.id)}
            >
              Open the analysis
            </Link>
          </p>
          {sheet && (
            <p>
              A Google Sheet copy is in your Drive.{" "}
              <a
                className="text-primary hover:underline"
                href={sheet.edit}
                target="_blank"
                rel="noreferrer"
              >
                Open in Google Sheets
              </a>
            </p>
          )}
          {saved.driveError && (
            <p>
              Saved to the project, but the Google copy was not made: {saved.driveError}{" "}
              <Link
                className="text-primary hover:underline"
                to={`/labs/${labId}/settings/integrations`}
              >
                Check Integrations
              </Link>
            </p>
          )}
        </div>
      )}

      <SaveDialog
        open={saving}
        labId={labId}
        projectId={projectId}
        result={result}
        inputName={run.inputName}
        datasetId={run.datasetId}
        flagged={run.flagged}
        getSvgs={svgs}
        onClose={() => setSaving(false)}
        onSaved={onSaved}
      />
    </article>
  );
}
