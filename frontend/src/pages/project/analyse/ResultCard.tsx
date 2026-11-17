import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { toast } from "sonner";
import { Copy, Download, FileSpreadsheet, Save, Sheet, X } from "lucide-react";
import { IconAction } from "@/components/shared/IconAction";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useDriveExport } from "@/hooks/driveExport";
import { useAttachments } from "@/hooks/projects";
import { useSaveRecord } from "@/hooks/research";
import type { Analysis, ResearchResult } from "@/lib/api-types";
import { formErrors } from "@/lib/forms";
import { fileSafe, saveBlob, svgFile, tableCsv, tableTsv, XLSX_TYPE } from "@/lib/exportFiles";
import { recordPath } from "@/lib/workflow";
import { googleEditor } from "@/lib/googleFiles";
import type { StatsResult, StatsTable } from "@/lib/stats/contract";
import { Chart } from "@/pages/project/analyse/charts";
import { useGetEngine } from "@/pages/project/analyse/engine";
import { ExportMenu } from "@/pages/project/analyse/ExportMenu";
import { cn } from "@/lib/utils";
import { svgToPng } from "@/pages/project/analyse/png";
import { SaveDialog } from "@/pages/project/analyse/SaveDialog";
import { cleanName, errorText, saveRun, type SaveOutcome } from "@/pages/project/analyse/save";

export interface Run {
  id: number;
  result: StatsResult;
  inputName: string;
  datasetId?: string;
  /** Does the data file identify participants? null for a file from this computer. */
  flagged: boolean | null;
  saved?: SaveOutcome;
}

const download = saveBlob;

async function copy(text: string, what: string) {
  try {
    await navigator.clipboard.writeText(text);
    toast.success(`${what} copied`);
  } catch {
    toast.error("Could not copy. Select the text and copy it yourself.");
  }
}

const fileStem = (r: StatsResult) => cleanName(r.title);
// Only long text may break anywhere: on every cell it would split short numbers too.
const wrapLong = (v: unknown) =>
  typeof v === "string" && v.length > 30 && "min-w-48 [overflow-wrap:anywhere]";

export function ResultCard({
  run,
  labId,
  projectId,
  canSave,
  onSaved,
  onRemove,
  canExport = false,
  autoSave,
}: {
  run: Run;
  labId: string;
  projectId: string;
  canSave: boolean;
  onSaved: (o: SaveOutcome) => void;
  /** Drop this result from the list (it is not saved anywhere). */
  onRemove?: () => void;
  /** May send results to Google Drive (the project's export right). */
  canExport?: boolean;
  /**
   * Save this result to the project as soon as it is shown (only when the data file is known not
   * to identify participants). `draftId` is the in-progress report to finish instead of a new one.
   */
  autoSave?: { draftId?: string };
}) {
  const { result, saved } = run;
  const { uploadFile } = useAttachments(labId, projectId);
  const analyses = useSaveRecord<Analysis>(labId, projectId, "analyses", autoSave?.draftId);
  const results = useSaveRecord<ResearchResult>(labId, projectId, "results");
  const [autoError, setAutoError] = useState<string>();
  const [autoBusy, setAutoBusy] = useState(false);
  const autoTried = useRef(false);
  const savedNow = useRef(saved);
  useEffect(() => {
    savedNow.current = saved;
  });
  const root = useRef<HTMLElement>(null);
  const [saving, setSaving] = useState(false);
  const svgs = () => Array.from(root.current?.querySelectorAll<SVGSVGElement>("svg.viz") ?? []);
  const base = `/labs/${labId}/projects/${projectId}`;
  useEffect(() => {
    if (!autoSave || !canSave || saved || run.flagged !== false) return;
    // a moment for the charts to draw, because they are saved as pictures
    const timer = setTimeout(() => {
      if (autoTried.current || savedNow.current) return;
      autoTried.current = true;
      setAutoBusy(true);
      saveRun(
        {
          result,
          title: result.title,
          inputName: run.inputName,
          datasetId: run.datasetId,
          participant: false,
          svgs: svgs(),
          chartTitles: result.charts.map((c) => c.title),
          toDrive: false,
        },
        {
          upload: (file, participant) => uploadFile.mutateAsync({ file, participant }),
          createAnalysis: (b) => analyses.mutateAsync(b),
          createResult: (b) => results.mutateAsync(b),
          editInGoogle: () => Promise.reject(new Error("not used")),
          toPng: svgToPng,
        },
      )
        .then(
          (out) => {
            toast.success("Saved to the project", { description: "It is in the Analysis tab." });
            onSaved(out);
          },
          (e) => setAutoError(errorText(e)),
        )
        .finally(() => setAutoBusy(false));
    }, 400);
    return () => clearTimeout(timer);
    // once per result: the mutations and callbacks are rebuilt on every render
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoSave !== undefined, canSave, saved, run.flagged]);
  const sheet = saved?.copy && googleEditor(saved.copy);
  const getEngine = useGetEngine();
  const drive = useDriveExport(labId, projectId);
  // Unknown (a file from this computer) counts as marked, for the audit record only.
  const participantData = run.flagged !== false;

  async function toDrive(blob: Blob, filename: string, name: string, what: string) {
    try {
      const out = await drive.mutateAsync({
        file: new File([blob], filename, { type: blob.type }),
        name,
        participantData,
      });
      toast.success(`${what} sent to your Google Drive`, {
        action: { label: "Open", onClick: () => window.open(out.url, "_blank", "noopener") },
      });
    } catch (e) {
      toast.error(formErrors(e, ["file"]).fields.file ?? "Could not send that to Google Drive.");
    }
  }

  async function tableWorkbook(t: StatsTable) {
    const bytes = await getEngine().tableXlsx(t, {
      title: result.title,
      summary: result.summary,
      n: result.n,
      file: run.inputName,
    });
    return new Blob([bytes as BlobPart], { type: XLSX_TYPE });
  }
  const failed = (what: string) => () => toast.error(`Could not make ${what}. Try again.`);

  function tableItems(t: StatsTable) {
    const stem = `${fileStem(result)}-${fileSafe(t.title)}`;
    return {
      here: [
        { label: "Copy to paste", run: () => copy(tableTsv(t), "Table") },
        {
          label: "Download CSV",
          run: () => download(new Blob([tableCsv(t)], { type: "text/csv" }), `${stem}.csv`),
        },
        {
          label: "Download Excel (.xlsx)",
          run: () =>
            tableWorkbook(t).then((b) => download(b, `${stem}.xlsx`), failed("the workbook")),
        },
      ],
      google: canExport
        ? [
            {
              label: "Send to Google Sheets",
              run: () =>
                tableWorkbook(t).then(
                  (b) => toDrive(b, `${stem}.xlsx`, `${result.title}: ${t.title}`, "Table"),
                  failed("the workbook"),
                ),
            },
          ]
        : [],
    };
  }

  function chartItems(i: number, title: string) {
    const stem = `${fileStem(result)} - ${cleanName(title)}`;
    const png = async () => {
      const svg = svgs()[i];
      if (!svg) throw new Error("no chart");
      return svgToPng(svg);
    };
    return {
      here: [
        {
          label: "Download PNG",
          run: () =>
            png().then(
              (b) => download(b, `${stem}.png`),
              () => toast.error("The chart could not be turned into a picture."),
            ),
        },
        {
          label: "Download SVG (editable)",
          run: () => {
            const svg = svgs()[i];
            if (svg) download(svgFile(svg), `${stem}.svg`);
          },
        },
        {
          label: "Copy picture",
          run: () =>
            png()
              .then((b) => navigator.clipboard.write([new ClipboardItem({ "image/png": b })]))
              .then(
                () => toast.success("Picture copied"),
                () => toast.error("This browser could not copy the picture. Download it instead."),
              ),
        },
      ],
      google: canExport
        ? [
            {
              label: "Send picture to Google Drive",
              run: () =>
                png().then(
                  (b) => toDrive(b, `${stem}.png`, `${result.title}: ${title}`, "Chart"),
                  () => toast.error("The chart could not be turned into a picture."),
                ),
            },
          ]
        : [],
    };
  }

  return (
    <article
      ref={root}
      aria-label={result.title}
      className="grid min-w-0 gap-4 rounded-lg border p-4 [overflow-wrap:anywhere]"
    >
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-base font-semibold">{result.title}</h2>
          <p className="text-xs text-muted-foreground">
            {run.inputName} · {result.n} rows used
          </p>
        </div>
        <div className="flex gap-2">
          {onRemove && !saved && (
            <IconAction
              label={`Remove ${result.title}`}
              icon={<X aria-hidden />}
              onClick={onRemove}
            />
          )}
          {canSave && !saved && !autoBusy && (
            <IconAction
              label="Save to project"
              icon={<Save aria-hidden />}
              variant="default"
              onClick={() => {
                autoTried.current = true; // saving by hand replaces the automatic save
                setSaving(true);
              }}
            />
          )}
        </div>
      </header>

      <div className="flex items-start gap-2">
        <p className="text-sm">{result.summary}</p>
        <IconAction
          label="Copy"
          icon={<Copy aria-hidden />}
          onClick={() => void copy(result.summary, "Summary")}
        />
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
          <Table className="[overflow-wrap:normal]">
            <caption className="caption-top pb-1 text-left text-sm font-medium">{t.title}</caption>
            <TableHeader>
              <TableRow>
                {t.columns.map((c) => (
                  <TableHead key={c} scope="col" className={cn("whitespace-normal", wrapLong(c))}>
                    {c}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {t.rows.map((r, i) => (
                <TableRow key={i}>
                  {r.map((v, j) => (
                    <TableCell key={j} className={cn("whitespace-normal", wrapLong(v))}>
                      {v ?? ""}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <div className="flex items-start justify-between gap-2">
            <p className="text-xs text-muted-foreground">{t.note}</p>
            <ExportMenu label={`Export table ${t.title}`} {...tableItems(t)} />
          </div>
        </div>
      ))}

      {result.charts.map((c, i) => (
        <figure key={`${c.kind}-${i}`} className="grid gap-1">
          <figcaption className="flex items-center gap-2 text-sm font-medium">
            {c.title}
            <ExportMenu label={`Export chart ${c.title}`} {...chartItems(i, c.title)} />
          </figcaption>
          <Chart chart={c} />
        </figure>
      ))}

      <details className="rounded-md border p-3">
        <summary className="cursor-pointer text-sm font-medium">Python code</summary>
        <div className="mt-2 grid gap-2">
          <pre className="max-h-80 overflow-auto rounded bg-muted p-3 text-xs">
            <code>{result.code}</code>
          </pre>
          <div className="flex gap-2">
            <IconAction
              label="Copy code"
              icon={<Copy aria-hidden />}
              variant="outline"
              onClick={() => void copy(result.code, "Code")}
            />
            <IconAction
              label="Download .py"
              icon={<Download aria-hidden />}
              variant="outline"
              onClick={() =>
                download(
                  new Blob([result.code], { type: "text/x-python" }),
                  `${fileStem(result)}.py`,
                )
              }
            />
          </div>
        </div>
      </details>

      <div className="flex flex-wrap gap-2">
        <IconAction
          label="Download results (.xlsx)"
          icon={<FileSpreadsheet aria-hidden />}
          variant="outline"
          onClick={() =>
            download(
              new Blob([result.xlsx as BlobPart], {
                type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
              }),
              `${fileStem(result)}.xlsx`,
            )
          }
        />
        {canExport && (
          <IconAction
            label="Send results to Google Sheets"
            icon={<Sheet aria-hidden />}
            variant="outline"
            onClick={() =>
              void toDrive(
                new Blob([result.xlsx as BlobPart], { type: XLSX_TYPE }),
                `${fileStem(result)}.xlsx`,
                result.title,
                "Results workbook",
              )
            }
          />
        )}
      </div>

      {autoError && !saved && (
        <p role="alert" className="text-sm font-medium text-destructive">
          Could not save this result automatically. {autoError} Use Save to project to try again.
        </p>
      )}

      {saved && (
        <div role="status" className="grid gap-1 rounded-md border bg-muted p-3 text-sm">
          {saved.analysis ? (
            <p>
              Saved to the project.{" "}
              <Link
                className="text-primary hover:underline"
                to={recordPath(base, "analyses", saved.analysis.id)}
              >
                Open the analysis
              </Link>
            </p>
          ) : (
            <p>
              Saved as files only, marked as identifying participants: {saved.files.join(", ")}. No
              analysis or result was made, so AI tools cannot see any of it. They are in the
              project&apos;s files.{" "}
              <Link className="text-primary hover:underline" to={`${base}/documents`}>
                Open the files
              </Link>
            </p>
          )}
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
