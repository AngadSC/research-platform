import {
  ExternalLink,
  FileSpreadsheet,
  FileText,
  Presentation,
  ClipboardList,
  File,
} from "lucide-react";
import { Link } from "react-router";
import { RelativeTime } from "@/components/shared/RelativeTime";
import { useCurrentLabId, useCurrentProjectId } from "@/hooks/crumbs";
import { useDocuments } from "@/hooks/documents";
import { KIND_LABEL, type GoogleLink, type GoogleLinkKind } from "@/lib/googleLinks";

const ICON: Record<GoogleLinkKind, typeof FileText> = {
  doc: FileText,
  sheet: FileSpreadsheet,
  slides: Presentation,
  form: ClipboardList,
  file: File,
};

/** A pasted Google link as a card. When the link is one of this project's documents it shows that
 * document's title and when it was last edited, and opens it here; otherwise it says what kind of
 * Google file it is and opens it in Google (we cannot read a file we were not given). */
export function DocLinkCard({ link }: { link: GoogleLink }) {
  const labId = useCurrentLabId();
  const projectId = useCurrentProjectId();
  const docs = useDocuments(labId ?? "", projectId ?? "", undefined, !!labId && !!projectId);
  const known =
    labId && projectId ? (docs.data ?? []).find((d) => d.embed_url.includes(link.id)) : undefined;
  const Icon = ICON[link.kind];
  return (
    <span className="my-0.5 flex max-w-sm items-center gap-3 rounded-lg border bg-card p-2 text-card-foreground">
      <span className="grid size-9 shrink-0 place-items-center rounded-md bg-primary/10 text-primary">
        <Icon className="size-5" aria-hidden />
      </span>
      <span className="min-w-0 flex-1">
        {known ? (
          <Link
            to={`/labs/${labId}/projects/${projectId}/documents/${known.id}`}
            className="block truncate font-medium hover:underline"
          >
            {known.title}
          </Link>
        ) : (
          <a
            href={link.url}
            target="_blank"
            rel="noopener noreferrer"
            className="block truncate font-medium hover:underline"
          >
            {KIND_LABEL[link.kind]}
          </a>
        )}
        <span className="block text-xs text-muted-foreground">
          {known ? (
            <>
              {KIND_LABEL[link.kind]} · edited <RelativeTime value={known.updated_at} />
            </>
          ) : (
            <>Opens in Google</>
          )}
        </span>
      </span>
      <a
        href={link.url}
        target="_blank"
        rel="noopener noreferrer"
        aria-label={`Open ${KIND_LABEL[link.kind]} in Google`}
        className="shrink-0 rounded p-1 text-muted-foreground hover:text-foreground"
      >
        <ExternalLink className="size-4" aria-hidden />
      </a>
    </span>
  );
}
