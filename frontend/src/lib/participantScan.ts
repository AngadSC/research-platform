/**
 * Reads a file added to a participant and suggests which of that participant's entries it fills.
 *
 * Everything here runs in the browser. The file's words are matched against the entry names (and
 * a few plain synonyms) and are never sent to an AI tool, so a file that identifies participants
 * stays as private as it was. It only suggests: the person confirms before anything is changed.
 */

export interface ScanColumn {
  id: string;
  name: string;
}

export interface ScanMatch {
  componentId: string;
  name: string;
  /** "sure": every word of the entry name was found. "maybe": some were, and the file name had one. */
  confidence: "sure" | "maybe";
  /** Where the evidence came from, for the review list. */
  found: string;
}

export interface ScanResult {
  matches: ScanMatch[];
  /** Another participant's code appears in the file, so it may belong to them. */
  otherCodes: string[];
  /** This participant's code appears in the file. */
  hasOwnCode: boolean;
  /** What was read: "text" read the file's words, "name" only had its name to go on. */
  basis: "text" | "name";
}

const STOP = new Set([
  "a",
  "an",
  "and",
  "the",
  "of",
  "for",
  "to",
  "in",
  "on",
  "or",
  "with",
  "file",
  "data",
  "form",
  "document",
  "doc",
]);

/** Words that mean the same thing for a lab's records. Each list is one idea. */
const SYNONYMS: string[][] = [
  ["transcript", "transcription", "transcribed", "verbatim"],
  ["translation", "translated", "translate"],
  ["consent", "assent", "agreement"],
  ["narrative", "story", "retell", "retelling"],
  ["questionnaire", "survey"],
  ["audio", "recording", "recorded", "mp3", "wav", "m4a"],
  ["video", "mp4", "mov"],
  ["demographic", "demographics", "background"],
  ["assessment", "test", "battery"],
  ["interview", "session"],
  ["screening", "eligibility"],
  ["debrief", "debriefing"],
];

const stem = (w: string) =>
  w.length > 4 ? w.replace(/(ing|ed|es|s|ion)$/, "") : w.replace(/s$/, "");

const words = (s: string) =>
  s
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter((w) => w && !STOP.has(w));

/** Every spelling that counts as the same word as `w`. */
function forms(w: string): Set<string> {
  const out = new Set([w, stem(w)]);
  for (const group of SYNONYMS) {
    if (group.some((g) => g === w || stem(g) === stem(w)))
      for (const g of group) {
        out.add(g);
        out.add(stem(g));
      }
  }
  return out;
}

const bag = (text: string) => {
  const set = new Set<string>();
  for (const w of words(text)) {
    set.add(w);
    set.add(stem(w));
  }
  return set;
};

const has = (haystack: Set<string>, w: string) => [...forms(w)].some((f) => haystack.has(f));

/** Codes like P-001, P012 or S_7, normalised so "P012" and "P-012" compare equal. */
const CODE = /(?<![A-Za-z])([A-Za-z]{1,3})[-_ ]?(\d{1,5})(?!\d)/g;
const normCode = (prefix: string, num: string) => `${prefix.toUpperCase()}-${Number(num)}`;
export function codesIn(text: string): Set<string> {
  const out = new Set<string>();
  for (const m of text.matchAll(CODE)) out.add(normCode(m[1]!, m[2]!));
  return out;
}

export function scanFile(opts: {
  fileName: string;
  /** The file's words, when they could be read. */
  text?: string;
  columns: ScanColumn[];
  participantCode: string;
}): ScanResult {
  const { fileName, text, columns, participantCode } = opts;
  const body = bag((text ?? "").slice(0, 200_000));
  const title = bag(fileName.replace(/\.[a-z0-9]+$/i, ""));
  const matches: ScanMatch[] = [];

  for (const c of columns) {
    const need = words(c.name);
    if (!need.length) continue;
    const inTitle = need.filter((w) => has(title, w));
    const inBody = need.filter((w) => has(body, w));
    const found = need.filter((w) => has(title, w) || has(body, w));
    if (found.length === need.length) {
      matches.push({
        componentId: c.id,
        name: c.name,
        confidence: "sure",
        found: inTitle.length === need.length ? "in the file name" : "in the file's text",
      });
    } else if (inTitle.length > 0 && found.length * 2 >= need.length) {
      matches.push({
        componentId: c.id,
        name: c.name,
        confidence: "maybe",
        found: inBody.length ? "partly in the name and text" : "partly in the file name",
      });
    }
  }
  // The most specific entry first: a "sure" match beats a "maybe", then the longer name.
  matches.sort(
    (a, b) =>
      Number(b.confidence === "sure") - Number(a.confidence === "sure") ||
      b.name.length - a.name.length,
  );

  const mine = codesIn(participantCode);
  const seen = codesIn(`${fileName} ${text ?? ""}`.slice(0, 200_000));
  const own = [...mine][0];
  return {
    matches,
    otherCodes: [...seen].filter((c) => !mine.has(c)).slice(0, 5),
    hasOwnCode: own ? seen.has(own) : false,
    basis: text ? "text" : "name",
  };
}

const PLAIN = /\.(txt|csv|tsv|md|json|html?|rtf|srt|vtt)$/i;

/** The words in a file, or undefined when this kind of file cannot be read here (Word, audio,
 * images, and anything very large). It never throws: a file that cannot be read is matched by
 * its name instead. */
export async function readFileText(file: File): Promise<string | undefined> {
  try {
    if (file.size > 30 * 1024 * 1024) return undefined;
    if (PLAIN.test(file.name) || file.type.startsWith("text/")) return await file.text();
    if (/\.pdf$/i.test(file.name) || file.type === "application/pdf") return await readPdf(file);
  } catch {
    return undefined;
  }
  return undefined;
}

async function readPdf(file: File): Promise<string | undefined> {
  const { getDocument, GlobalWorkerOptions } = await import("pdfjs-dist");
  const worker = (await import("pdfjs-dist/build/pdf.worker.min.mjs?url")).default;
  GlobalWorkerOptions.workerSrc = worker;
  const pdf = await getDocument({ data: new Uint8Array(await file.arrayBuffer()) }).promise;
  let out = "";
  for (let i = 1; i <= Math.min(pdf.numPages, 25); i++) {
    const page = await pdf.getPage(i);
    const content = await page.getTextContent();
    out += content.items.map((it) => ("str" in it ? it.str : "")).join(" ") + "\n";
    if (out.length > 200_000) break;
  }
  return out.trim() || undefined; // a scanned (image-only) PDF has no text to read
}
