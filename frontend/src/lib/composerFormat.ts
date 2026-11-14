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

/**
 * The stored form of a mention: `@[Name](user:<id>)`. Square brackets in a name
 * would break it; round ones are fine. */
export const mentionToken = (name: string, id: string) =>
  `@[${name.replace(/[[\]\n]/g, "").trim() || "Someone"}](user:${id})`;

/** Swaps the "@query" being typed for a finished mention and a space. */
export function applyMention(
  value: string,
  at: { start: number; query: string },
  name: string,
  id: string,
): Edit {
  const end = at.start + 1 + at.query.length;
  return insertText(value, at.start, end, `${mentionToken(name, id)} `);
}
