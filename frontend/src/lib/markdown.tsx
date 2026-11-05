import type { ReactNode } from "react";

/** Safe "simple markdown" for thread posts (D142): **bold**, *italic*, `code`, [text](https://...),
 * bare https links, "- " lists and line breaks. It builds React elements only, never HTML, so
 * nothing in a post can inject markup; only http(s) links are made clickable. */
const INLINE =
  /(\*\*[^*\n]+\*\*|\*[^*\n]+\*|`[^`\n]+`|\[[^\]\n]+\]\(https?:\/\/[^\s)]+\)|https?:\/\/[^\s<]+)/g;

const link = (href: string, text: string, key: string) => (
  <a
    key={key}
    href={href}
    target="_blank"
    rel="noopener noreferrer nofollow"
    className="text-primary underline underline-offset-2"
  >
    {text}
  </a>
);

/** Links in the assistant's answers (D198): only addresses on this app's own origin become
 * links. Anything else is plain text with the address written out, so no link text can hide where
 * it goes (record text can steer the model into writing links). */
const ownOrigin = (href: string) => {
  try {
    return new URL(href, window.location.origin).origin === window.location.origin;
  } catch {
    return false;
  }
};

function inline(text: string, prefix: string, ownOnly: boolean): ReactNode[] {
  const make = (href: string, label: string, key: string) =>
    !ownOnly || ownOrigin(href) ? (
      link(href, label, key)
    ) : (
      <span key={key}>{label === href ? href : `${label} (${href})`}</span>
    );
  return text.split(INLINE).map((part, i) => {
    const key = `${prefix}-${i}`;
    if (i % 2 === 0) return part;
    if (part.startsWith("**")) return <strong key={key}>{part.slice(2, -2)}</strong>;
    if (part.startsWith("*")) return <em key={key}>{part.slice(1, -1)}</em>;
    if (part.startsWith("`"))
      return (
        <code key={key} className="rounded bg-muted px-1 font-mono text-[0.85em]">
          {part.slice(1, -1)}
        </code>
      );
    if (part.startsWith("[")) {
      const m = /^\[([^\]]+)\]\((.+)\)$/.exec(part);
      return m ? make(m[2]!, m[1]!, key) : part;
    }
    return make(part, part, key);
  });
}

export function Markdown({ text, ownLinksOnly = false }: { text: string; ownLinksOnly?: boolean }) {
  const blocks: ReactNode[] = [];
  let items: string[] = [];
  const flush = (at: number) => {
    if (!items.length) return;
    blocks.push(
      <ul key={`ul${at}`} className="list-disc pl-5">
        {items.map((it, i) => (
          <li key={i}>{inline(it, `l${at}-${i}`, ownLinksOnly)}</li>
        ))}
      </ul>,
    );
    items = [];
  };
  text.split("\n").forEach((line, i) => {
    const li = /^\s*[-*] (.*)$/.exec(line);
    if (li) return void items.push(li[1] ?? "");
    flush(i);
    blocks.push(
      line.trim() ? (
        <p key={i}>{inline(line, `p${i}`, ownLinksOnly)}</p>
      ) : (
        <div key={i} className="h-2" />
      ),
    );
  });
  flush(text.length);
  return <div className="grid gap-0.5 text-sm break-words">{blocks}</div>;
}
