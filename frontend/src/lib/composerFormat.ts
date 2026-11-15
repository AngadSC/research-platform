/** Pure text edits behind the message composer (D260). Each takes the text and the selection and
 * returns the new text and where the selection should land, so they are easy to test and the
 * component only has to apply the result. */
export interface Edit {
  value: string;
  start: number;
  end: number;
}

/** Puts `before`/`after` around the selection; with nothing selected, around `placeholder`, which
 * ends up selected so typing replaces it. Selecting text that is already wrapped removes the marks. */
export function wrap(
  value: string,
  start: number,
  end: number,
  before: string,
  after = before,
  placeholder = "text",
): Edit {
  const selected = value.slice(start, end);
  const around = value.slice(Math.max(0, start - before.length), start);
  const beyond = value.slice(end, end + after.length);
  if (selected && around === before && beyond === after) {
    return {
      value: value.slice(0, start - before.length) + selected + value.slice(end + after.length),
      start: start - before.length,
      end: end - before.length,
    };
  }
  const text = selected || placeholder;
  const from = start + before.length;
  return {
    value: value.slice(0, start) + before + text + after + value.slice(end),
    start: from,
    end: from + text.length,
  };
}

const LINE_PREFIX = /^(?:[-*] |\d+\. |> )/;

/** Starts every line touched by the selection with "- ", "> " or numbered "1. ", "2. "... A
 * second press on lines that already have that prefix takes it off again. */
export function prefixLines(
  value: string,
  start: number,
  end: number,
  kind: "bullet" | "number" | "quote",
): Edit {
  const from = value.lastIndexOf("\n", start - 1) + 1;
  const nl = value.indexOf("\n", end);
  const to = nl === -1 ? value.length : nl;
  const lines = value.slice(from, to).split("\n");
  const has = (l: string) =>
    kind === "bullet" ? /^[-*] /.test(l) : kind === "quote" ? /^> /.test(l) : /^\d+\. /.test(l);
  const off = lines.every(has);
  const out = lines.map((l, i) => {
    const bare = l.replace(LINE_PREFIX, "");
    if (off) return bare;
    const mark = kind === "bullet" ? "- " : kind === "quote" ? "> " : `${i + 1}. `;
    return mark + bare;
  });
  const text = out.join("\n");
  return {
    value: value.slice(0, from) + text + value.slice(to),
    start: from,
    end: from + text.length,
  };
}

/** Wraps the selection in a fenced block on its own lines. */
export function codeBlock(value: string, start: number, end: number): Edit {
  const lead = start > 0 && value[start - 1] !== "\n" ? "\n" : "";
  const tail = end < value.length && value[end] !== "\n" ? "\n" : "";
  const body = value.slice(start, end) || "code";
  const open = `${lead}\`\`\`\n`;
  return {
    value: `${value.slice(0, start)}${open}${body}\n\`\`\`${tail}${value.slice(end)}`,
    start: start + open.length,
    end: start + open.length + body.length,
  };
}

/** Makes `[text](url)` from the selection (or the address itself when nothing is selected). */
export function insertLink(value: string, start: number, end: number, url: string): Edit {
  const text = value.slice(start, end) || url;
  const link = `[${text}](${url})`;
  return {
    value: value.slice(0, start) + link + value.slice(end),
    start: start + link.length,
    end: start + link.length,
  };
}

/** Replaces the selection with `text`, leaving the caret after it. */
export function insertText(value: string, start: number, end: number, text: string): Edit {
  return {
    value: value.slice(0, start) + text + value.slice(end),
    start: start + text.length,
    end: start + text.length,
  };
}

/** The address a link box accepts: http(s) or an email address; a bare "example.org" gets https. */
export function cleanUrl(raw: string): string | null {
  const url = raw.trim();
  if (!url || /[\s()<>]/.test(url)) return null;
  if (/^(https?:\/\/|mailto:)\S+$/i.test(url)) return url;
  if (/^[^\s@/:]+@[^\s@/:]+\.[^\s@/:]+$/.test(url)) return `mailto:${url}`;
  if (/^[\w-]+(\.[\w-]+)+(\/\S*)?$/.test(url)) return `https://${url}`;
  return null;
}

/** An "@name" being typed just before the caret: where it starts and what follows the "@". */
export function mentionAt(value: string, caret: number): { start: number; query: string } | null {
  const m = /(^|\s)@([^\s@[\]()]{0,40})$/.exec(value.slice(0, caret));
  return m ? { start: caret - m[2]!.length - 1, query: m[2]! } : null;
}

/** A name as written in a mention. Square brackets would break the stored form; round ones,
 * as in "Lee Lead (FAKE)", are kept. */
export const mentionName = (name: string) => name.replace(/[[\]\n]/g, "").trim() || "Someone";

/** The stored form of a mention: `@[Name](user:<id>)`. It is what is saved and what notifies the
 * person; the text box shows only `@Name` (D295). */
export const mentionToken = (name: string, id: string) => `@[${mentionName(name)}](user:${id})`;

const STORED_MENTION = /@\[([^\]\n]{1,100})\]\(user:([0-9a-fA-F-]{36})\)/g;

/** Stored text as the box shows it: every `@[Name](user:<id>)` becomes just `@Name`. */
export const toDisplay = (stored: string) =>
  stored.replace(STORED_MENTION, (_m, name) => `@${name}`);

/** Who an `@Name` in the box means, by the name shown. A name that two different people share
 * maps to `null`: it is left as plain text rather than notifying the wrong person. */
export type NameIndex = Map<string, string | null>;

/** The people who can be mentioned plus anyone already mentioned in `stored`. */
export function nameIndex(people: { id: string; name: string }[], stored: string): NameIndex {
  const index: NameIndex = new Map();
  const add = (name: string, id: string) => {
    const key = mentionName(name);
    const seen = index.get(key);
    index.set(key, seen === undefined || seen === id ? id : null);
  };
  for (const p of people) add(p.name, p.id);
  for (const m of stored.matchAll(STORED_MENTION)) add(m[1]!, m[2]!);
  return index;
}

/** Inline code and fenced blocks: a name written there is just text. An unclosed fence counts
 * as code to the end, since it is still being written. */
const CODE_SPANS = /(```[\s\S]*?(?:```|$)|`[^`\n]*`)/;

function convertMentions(text: string, index: NameIndex, startsWord: boolean): string {
  if (!text.includes("@")) return text;
  const names = [...index.keys()].sort((a, b) => b.length - a.length); // "Ada Lovelace" before "Ada"
  let out = "";
  let i = 0;
  while (i < text.length) {
    const wordStart = i === 0 ? startsWord : /[\s([{"'>]/.test(text[i - 1]!);
    if (text[i] === "@" && wordStart) {
      const name = names.find(
        (n) => text.startsWith(n, i + 1) && !/[\p{L}\p{N}_]/u.test(text[i + 1 + n.length] ?? ""),
      );
      const id = name === undefined ? null : index.get(name);
      if (name !== undefined && id) {
        out += mentionToken(name, id);
        i += 1 + name.length;
        continue;
      }
    }
    out += text[i];
    i += 1;
  }
  return out;
}

/** The box's text back into the stored form: each `@Name` that is still written out in full, at
 * the start of a word, not running into more letters and not inside code, becomes its mention.
 * Anything else (a half-deleted name, an email address) stays as typed, so a mention exists only
 * while its name is there. */
export function toStored(text: string, index: NameIndex): string {
  if (index.size === 0 || !text.includes("@")) return text;
  return text
    .split(CODE_SPANS)
    .map((part, i) => (i % 2 === 1 ? part : convertMentions(part, index, i === 0)))
    .join("");
}

/** Swaps the "@query" being typed for the person's name and a space. */
export function applyMention(
  value: string,
  at: { start: number; query: string },
  name: string,
): Edit {
  const end = at.start + 1 + at.query.length;
  return insertText(value, at.start, end, `@${mentionName(name)} `);
}
