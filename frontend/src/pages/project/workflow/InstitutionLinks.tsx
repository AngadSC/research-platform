import { ExternalLink } from "lucide-react";
import { useInstitutionLinks } from "@/hooks/workflow";

/** The institution's links for a category (University of Alberta starters and the lab's own,
 * D135). Renders nothing while loading, when the list is empty, or when the endpoint is absent. */
export function InstitutionLinks({
  labId,
  category,
  title,
}: {
  labId: string;
  category: "ethics" | "funding";
  title: string;
}) {
  const { data } = useInstitutionLinks(labId, category);
  if (!data?.length) return null;
  return (
    <section aria-label={title} className="grid gap-2">
      <h2 className="text-sm font-medium">{title}</h2>
      <ul className="grid divide-y rounded-lg border bg-background text-sm">
        {data.map((r) => (
          <li key={r.id} className="grid gap-0.5 px-3 py-2">
            <a
              href={r.url}
              target="_blank"
              rel="noreferrer noopener"
              className="inline-flex items-center gap-1.5 font-medium text-primary hover:underline"
            >
              {r.title}
              <ExternalLink className="size-3.5" aria-hidden />
              <span className="sr-only">(opens in a new tab)</span>
            </a>
            {r.description && (
              <span className="text-xs text-muted-foreground">{r.description}</span>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
