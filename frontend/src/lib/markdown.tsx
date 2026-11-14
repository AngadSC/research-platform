import type { ReactNode } from "react";
import { DocLinkCard } from "@/components/shared/DocLinkCard";
import { parseGoogleLink } from "@/lib/googleLinks";
import { cn } from "@/lib/utils";

/** Safe "simple markdown" for messages, thread posts and notes (D142, D260): **bold**, *italic* or
 * _italic_, ~~strike~~, `code`, fenced code blocks, [text](https://... or mailto:...), bare https
 * links, "- " and "1. " lists, "> " quotes, @mentions and line breaks. It builds React elements
 * only, never HTML, so nothing in a message can inject markup; only http(s) and mailto links are
 * made clickable. */
const INLINE = new RegExp(
  `(${[
    String.raw`@\[[^\]\n]+\]\(user:[0-9a-fA-F-]{36}\)`,
    String.raw`\*\*[^*\n]+\*\*`,
    String.raw`~~[^~\n]+~~`,
    String.raw`\*[^*\n]+\*`,
    String.raw`(?<![\w])_[^_\n]+_(?![\w])`,
    "`[^`\\n]+`",
    String.raw`\[[^\]\n]+\]\((?:https?:\/\/|mailto:)[^\s)]+\)`,
    String.raw`https?:\/\/[^\s<]+`,
  ].join("|")})`,
  "g",
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

interface Style {
  ownOnly: boolean;
  /** On the coloured chat bubble, where the usual link and code colours would not show. */
  onPrimary: boolean;
}

function inline(text: string, prefix: string, st: Style): ReactNode[] {
  const make = (href: string, label: string, key: string) =>
    !st.ownOnly || ownOrigin(href) ? (
      <a
        key={key}
        href={href}
        target="_blank"
        rel="noopener noreferrer nofollow"
        className={cn("underline underline-offset-2", !st.onPrimary && "text-primary")}
      >
        {label}
      </a>
    ) : (
      <span key={key}>{label === href ? href : `${label} (${href})`}</span>
    );
  const nest = (s: string, key: string) => inline(s, key, st);
  return text.split(INLINE).map((part, i) => {
    const key = `${prefix}-${i}`;
    if (i % 2 === 0) return part;
    if (part.startsWith("@[")) {
      const m = /^@\[([^\]]+)\]/.exec(part);
      return (
        <span
          key={key}
          className={cn(
            "rounded px-1 font-medium",
            st.onPrimary ? "bg-primary-foreground/20" : "bg-primary/10 text-primary",
          )}
        >
          @{m?.[1]}
        </span>
      );
    }
    if (part.startsWith("**")) return <strong key={key}>{nest(part.slice(2, -2), key)}</strong>;
    if (part.startsWith("~~")) return <del key={key}>{nest(part.slice(2, -2), key)}</del>;
    if (part.startsWith("*") || part.startsWith("_"))
      return <em key={key}>{nest(part.slice(1, -1), key)}</em>;
    if (part.startsWith("`"))
      return (
        <code
          key={key}
          className={cn(
            "rounded px-1 font-mono text-[0.85em]",
            st.onPrimary ? "bg-primary-foreground/20" : "bg-muted",
          )}
        >
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

const BULLET = /^\s*[-*] (.*)$/;
const NUMBER = /^\s*(\d+)\. (.*)$/;
const QUOTE = /^\s*> ?(.*)$/;
const FENCE = /^\s*```/;

export function MessageText({
  text,
  ownLinksOnly = false,
  onPrimary = false,
}: {
  text: string;
  ownLinksOnly?: boolean;
  onPrimary?: boolean;
}) {
  const st: Style = { ownOnly: ownLinksOnly, onPrimary };
  const blocks: ReactNode[] = [];
  const lines = text.split("\n");
  for (let i = 0; i < lines.length;) {
    const line = lines[i]!;
    const at = `b${i}`;
    if (FENCE.test(line)) {
      const code: string[] = [];
      i++;
      while (i < lines.length && !FENCE.test(lines[i]!)) code.push(lines[i++]!);
      i++; // the closing fence; an unclosed block runs to the end
      blocks.push(
        <pre
          key={at}
          className={cn(
            "overflow-x-auto rounded-md p-2 font-mono text-xs",
            onPrimary ? "bg-primary-foreground/20" : "bg-muted",
          )}
        >
          <code>{code.join("\n")}</code>
        </pre>,
      );
      continue;
    }
    const list = (re: RegExp, ordered: boolean) => {
      const items: [number, string][] = [];
      while (i < lines.length && re.test(lines[i]!)) {
        const m = re.exec(lines[i++]!)!;
        items.push(ordered ? [Number(m[1]), m[2]!] : [0, m[1]!]);
      }
      const Tag = ordered ? "ol" : "ul";
      blocks.push(
        <Tag
          key={at}
          start={ordered ? items[0]![0] : undefined}
          className={cn("pl-5", ordered ? "list-decimal" : "list-disc")}
        >
          {items.map(([, it], n) => (
            <li key={n}>{inline(it, `${at}-${n}`, st)}</li>
          ))}
        </Tag>,
      );
    };
    if (BULLET.test(line)) list(BULLET, false);
    else if (NUMBER.test(line)) list(NUMBER, true);
    else if (QUOTE.test(line)) {
      const rows: string[] = [];
      while (i < lines.length && QUOTE.test(lines[i]!)) rows.push(QUOTE.exec(lines[i++]!)![1]!);
      blocks.push(
        <blockquote
          key={at}
          className={cn(
            "border-l-2 pl-2",
            onPrimary ? "border-primary-foreground/50" : "border-border text-muted-foreground",
          )}
        >
          {rows.map((r, n) => (
            <p key={n} className="whitespace-pre-wrap">
              {inline(r, `${at}-${n}`, st)}
            </p>
          ))}
        </blockquote>,
      );
    } else if (!st.ownOnly && parseGoogleLink(line)) {
      // A Google link on a line of its own becomes a card (not in the assistant's answers).
      blocks.push(<DocLinkCard key={at} link={parseGoogleLink(line)!} />);
      i++;
    } else {
      blocks.push(
        line.trim() ? (
          <p key={at} className="whitespace-pre-wrap">
            {inline(line, at, st)}
          </p>
        ) : (
          <div key={at} className="h-2" />
        ),
      );
      i++;
    }
  }
  return <div className="grid gap-0.5 text-sm break-words">{blocks}</div>;
}
