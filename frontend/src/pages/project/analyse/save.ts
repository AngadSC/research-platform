import type { Analysis, Attachment, ResearchResult } from "@/lib/api-types";
import type { StatsResult } from "@/lib/stats/contract";

export interface SaveDeps {
  upload: (file: File, participant: boolean) => Promise<Attachment>;
  createAnalysis: (body: Record<string, unknown>) => Promise<Analysis>;
  createResult: (body: Record<string, unknown>) => Promise<ResearchResult>;
  editInGoogle: (attachmentId: string) => Promise<Attachment>;
  toPng: (svg: SVGSVGElement) => Promise<Blob>;
}

export interface SaveArgs {
  result: StatsResult;
  title: string;
  inputName: string;
  /** Set when the data came from a dataset record. */
  datasetId?: string;
  /** The saved files get the "identifies participants" mark. */
  participant: boolean;
  svgs: SVGSVGElement[];
  toDrive: boolean;
}

export interface SaveOutcome {
  xlsx: Attachment;
  /** Not made for data that identifies participants (see saveRun). */
  analysis?: Analysis;
  result?: ResearchResult;
  /** The Google Sheet copy, when it was made. */
  copy?: Attachment;
  /** Why the copy was not made. The project save still went through. */
  driveError?: string;
}

/** Thrown when a step fails after others went through; `message` says exactly what was saved. */
export class SaveError extends Error {}

const XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
const slug = (s: string) =>
  s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 60) || "statistics";

export const errorText = (e: unknown) => (e instanceof Error ? e.message : "Something went wrong.");

/** Upload the files, then record the analysis and the result, then (optionally) the Google copy. */
export async function saveRun(a: SaveArgs, d: SaveDeps): Promise<SaveOutcome> {
  const saved: string[] = [];
  const fail = (step: string, e: unknown): never => {
    const done = saved.length ? `Saved so far: ${saved.join(", ")}. ` : "Nothing was saved. ";
    throw new SaveError(`${done}Could not ${step}: ${errorText(e)}`);
  };
  const stem = slug(a.title);
  const up = async (blob: BlobPart, name: string, type: string) => {
    try {
      const att = await d.upload(new File([blob], name, { type }), a.participant);
      saved.push(name);
      return att;
    } catch (e) {
      return fail(`upload ${name}`, e);
    }
  };

  const xlsx = await up(a.result.xlsx as BlobPart, `${stem}.xlsx`, XLSX_TYPE);
  const code = await up(a.result.code, `${stem}.py`, "text/x-python");
  const pngs: Attachment[] = [];
  for (const [i, svg] of a.svgs.entries()) {
    let blob: Blob;
    try {
      blob = await d.toPng(svg);
    } catch (e) {
      return fail(`make chart ${i + 1}`, e);
    }
    pngs.push(await up(blob, `${stem}-chart-${i + 1}.png`, "image/png"));
  }

  // An analysis must point at its code, and the server refuses marked code there because AI tools
  // may run an analysis's code. Analysis and result records can't carry the mark, so for marked
  // data none is made: the marked files are the whole save.
  if (a.participant) return withCopy({ xlsx }, a, d);

  let analysis: Analysis;
  try {
    analysis = await d.createAnalysis({
      title: a.title,
      description: `${a.result.summary}\n\nInput file: ${a.inputName}\n\nRun in the browser with labbenchos statistics.`,
      code_attachment: code.id,
      datasets: a.datasetId ? [a.datasetId] : [],
      ran_at: new Date().toISOString(),
    });
    saved.push("the analysis");
  } catch (e) {
    return fail("create the analysis", e);
  }
  let result: ResearchResult;
  try {
    result = await d.createResult({
      title: a.title,
      summary: a.result.summary,
      analysis: analysis.id,
      attachments: [xlsx.id, ...pngs.map((p) => p.id)],
    });
  } catch (e) {
    return fail("create the result", e);
  }

  return withCopy({ xlsx, analysis, result }, a, d);
}

async function withCopy(out: SaveOutcome, a: SaveArgs, d: SaveDeps): Promise<SaveOutcome> {
  if (a.toDrive) {
    try {
      out.copy = await d.editInGoogle(out.xlsx.id);
    } catch (e) {
      out.driveError = errorText(e);
    }
  }
  return out;
}
