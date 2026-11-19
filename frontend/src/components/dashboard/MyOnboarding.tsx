import { ExternalLink } from "lucide-react";
import { Link } from "react-router";
import { toast } from "sonner";
import { ApiError } from "@/lib/api";
import { useMyOnboarding, useTickOnboarding } from "@/hooks/startHere";

/** The new-member checklist with one person's own ticks, until everything is ticked (D351).
 *  Managers keep the full view under Lab details, so they are not shown this card. */
export function MyOnboarding({ labId, enabled }: { labId: string; enabled: boolean }) {
  const { data } = useMyOnboarding(labId, enabled);
  const tick = useTickOnboarding(labId);
  if (!enabled || !data || data.length === 0 || data.every((i) => i.done)) return null;
  const done = data.filter((i) => i.done).length;
  return (
    <section aria-labelledby="my-onboarding" className="grid gap-2 rounded-lg border bg-card p-4">
      <h2 id="my-onboarding" className="text-base font-medium">
        Your onboarding
        <span className="ml-2 text-sm font-normal text-muted-foreground">
          {done} of {data.length} done
        </span>
      </h2>
      <ul className="grid gap-2 text-sm">
        {data.map((i) => (
          <li key={i.id} className="flex items-start gap-2">
            <input
              type="checkbox"
              id={`onb-${i.id}`}
              className="mt-0.5 size-4 shrink-0"
              checked={i.done}
              disabled={i.training_linked || tick.isPending}
              onChange={(e) =>
                tick.mutate(
                  { id: i.id, done: e.target.checked },
                  {
                    onError: (e) =>
                      toast.error(
                        e instanceof ApiError && e.status === 400
                          ? e.message
                          : "Could not save that. Try again.",
                      ),
                  },
                )
              }
            />
            <div className="min-w-0">
              <label htmlFor={`onb-${i.id}`} className="font-medium">
                {i.title}
              </label>
              {i.url && (
                <a
                  href={i.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="ml-2 inline-flex items-center gap-1 text-primary underline-offset-2 hover:underline"
                >
                  Open
                  <ExternalLink className="size-3" aria-hidden />
                </a>
              )}
              {i.training_linked && (
                <p className="text-xs text-muted-foreground">
                  {i.by_training ? "Done: your" : "Done when your"}{" "}
                  {i.training_requirement_name || "training"} training is recorded.{" "}
                  <Link to={`/labs/${labId}/training`} className="text-primary hover:underline">
                    Training
                  </Link>
                </p>
              )}
              {i.description && <p className="text-xs text-muted-foreground">{i.description}</p>}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
