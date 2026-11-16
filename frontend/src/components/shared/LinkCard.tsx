import { useQuery } from "@tanstack/react-query";
import {
  BookOpen,
  Code2,
  ExternalLink,
  Globe,
  MessagesSquare,
  PenTool,
  PlaySquare,
  ScrollText,
  Video,
  type LucideIcon,
} from "lucide-react";
import { DocLinkCard } from "@/components/shared/DocLinkCard";
import { useCurrentLabId } from "@/hooks/crumbs";
import { api } from "@/lib/api";
import type { LinkPreview as Preview } from "@/lib/api-types";
import { parseGoogleLink } from "@/lib/googleLinks";

interface Known {
  label: string;
  icon: LucideIcon;
  /** No page title worth reading: a sign-in or join page. */
  noFetch?: boolean;
}

/** Services people paste in lab chat, by host (or a parent domain). Anything else is a website. */
const KNOWN: [host: string, info: Known][] = [
  ["meet.google.com", { label: "Google Meet", icon: Video, noFetch: true }],
  ["chat.google.com", { label: "Google Chat", icon: MessagesSquare, noFetch: true }],
  ["zoom.us", { label: "Zoom meeting", icon: Video, noFetch: true }],
  ["teams.microsoft.com", { label: "Microsoft Teams", icon: Video, noFetch: true }],
  ["github.com", { label: "GitHub", icon: Code2 }],
  ["gitlab.com", { label: "GitLab", icon: Code2 }],
  ["overleaf.com", { label: "Overleaf", icon: ScrollText, noFetch: true }],
  ["youtube.com", { label: "YouTube", icon: PlaySquare }],
  ["youtu.be", { label: "YouTube", icon: PlaySquare }],
  ["figma.com", { label: "Figma", icon: PenTool, noFetch: true }],
  ["arxiv.org", { label: "arXiv", icon: BookOpen }],
  ["doi.org", { label: "DOI", icon: BookOpen }],
  ["pubmed.ncbi.nlm.nih.gov", { label: "PubMed", icon: BookOpen }],
  ["biorxiv.org", { label: "bioRxiv", icon: BookOpen }],
  ["osf.io", { label: "OSF", icon: BookOpen }],
  ["zenodo.org", { label: "Zenodo", icon: BookOpen }],
  ["protocols.io", { label: "protocols.io", icon: BookOpen }],
];

function known(host: string): Known | undefined {
  return KNOWN.find(([h]) => host === h || host.endsWith(`.${h}`))?.[1];
}

const MAX_CARDS = 3;
const MD_LINK = /\[[^\]\n]+\]\((https:\/\/[^\s)]+)\)/g;
const BARE = /(?<![(\w])https:\/\/[^\s<)\]]+/g;

/** The https links in a message, in order, without repeats; code is skipped. Trailing
 * punctuation that ends a sentence is not part of the link. */
export function messageLinks(text: string): string[] {
  const plain = text.replace(/```[\s\S]*?(```|$)/g, " ").replace(/`[^`\n]+`/g, " ");
  const found = [
    ...[...plain.matchAll(MD_LINK)].map((m) => m[1]!),
    ...[...plain.matchAll(BARE)].map((m) => m[0].replace(/[.,;:!?'"]+$/, "")),
  ];
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of found) {
    try {
      const u = new URL(raw);
      if (u.protocol !== "https:" || u.username || u.password) continue;
      const key = u.toString();
      if (!seen.has(key)) {
        seen.add(key);
        out.push(key);
      }
    } catch {
      /* not an address */
    }
  }
  return out;
}

/** D322: cards under a message for the links in it. Google files get their own card; known
 * services an icon and name; other sites the page's title and description, read by our server
 * (never by the browser, so no outside site sees who reads the chat). `skip` are links already
 * shown as cards in the text. */
export function LinkCards({ text, skip = [] }: { text: string; skip?: string[] }) {
  const links = messageLinks(text)
    .filter((l) => !skip.includes(l))
    .slice(0, MAX_CARDS);
  if (links.length === 0) return null;
  return (
    <div className="mt-1 grid gap-1">
      {links.map((url) => {
        const google = parseGoogleLink(url);
        return google ? <DocLinkCard key={url} link={google} /> : <LinkCard key={url} url={url} />;
      })}
    </div>
  );
}

export function LinkCard({ url }: { url: string }) {
  const labId = useCurrentLabId();
  const host = new URL(url).hostname.replace(/^www\./, "");
  const info = known(host);
  const preview = useQuery({
    queryKey: ["link-preview", labId, url],
    queryFn: () => api<Preview>(`/api/labs/${labId}/link-preview/?url=${encodeURIComponent(url)}`),
    enabled: !!labId && !info?.noFetch,
    staleTime: 60 * 60 * 1000,
    retry: false,
  });
  const p = preview.data;
  const Icon = info?.icon ?? Globe;
  const title = p?.title || info?.label || host;
  const detail = p?.description || [p?.site_name || info?.label, host].filter(Boolean).join(" · ");
  return (
    <span className="my-0.5 flex max-w-sm items-center gap-3 rounded-lg border bg-card p-2 text-card-foreground">
      <span className="grid size-9 shrink-0 place-items-center rounded-md bg-primary/10 text-primary">
        <Icon className="size-5" aria-hidden />
      </span>
      <span className="min-w-0 flex-1">
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer nofollow"
          className="block truncate font-medium hover:underline"
        >
          {title}
        </a>
        <span className="line-clamp-2 block text-xs text-muted-foreground">{detail}</span>
      </span>
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer nofollow"
        aria-label={`Open ${title} in a new tab`}
        className="shrink-0 rounded p-1 text-muted-foreground hover:text-foreground"
      >
        <ExternalLink className="size-4" aria-hidden />
      </a>
    </span>
  );
}
