import { ExternalLink } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { startersMessage, useLoadStarters } from "@/hooks/admin";
import { useInstitutionLinks } from "@/hooks/workflow";
import { useLab } from "@/hooks/workspace";

/** The institution's links for a category (D135, D149). Empty, it renders nothing for most
 * people; someone who can manage the lab gets the "Get my university's forms" action. */
export function InstitutionLinks({
  labId,
  category,
  title,
}: {
  labId: string;
  category: "ethics" | "funding" | "data_management";
  title: string;
}) {
  const { data } = useInstitutionLinks(labId, category);
  const canManage = !!useLab(labId).data?.my_permissions.includes("manage_lab");
  const load = useLoadStarters(labId);
  if (!data) return null;
  if (!data.length) {
    if (!canManage) return null;
    return (
      <p className="text-sm text-muted-foreground">
        No university links yet.{" "}
        <Button
          variant="ghost"
          size="sm"
          className="h-auto p-0 font-medium text-primary underline-offset-4 hover:underline"
          disabled={load.isPending}
          onClick={() =>
            load.mutate(undefined, {
              onSuccess: (r) => toast.success(startersMessage(r)),
              onError: () => toast.error("Could not load your university's forms."),
            })
          }
        >
          Get my university's forms
        </Button>
      </p>
    );
  }
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
