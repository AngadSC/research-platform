import { CheckCircle2, Circle } from "lucide-react";
import { Link } from "react-router";
import { Button } from "@/components/ui/button";
import { useGettingStarted, useSetGettingStartedDismissed } from "@/hooks/dashboard";
import { OPEN_TUTORIAL_EVENT } from "@/lib/constants";

const STEPS: Record<string, { title: string; hint: string; path: string; action: string }> = {
  members: {
    title: "Invite your lab members",
    hint: "Add the people who work in your lab so they can join in.",
    path: "members",
    action: "Invite people",
  },
  project: {
    title: "Create your first project",
    hint: "A project holds the tasks, documents and files for one study.",
    path: "projects?new=project",
    action: "New project",
  },
  ethics: {
    title: "Link an ethics approval to a project",
    hint: "Add your approval and choose the project it covers.",
    path: "ethics",
    action: "Open Ethics",
  },
  drive: {
    title: "Connect Google Drive",
    hint: "Link Drive files to your projects without copying them.",
    path: "settings/integrations",
    action: "Connect",
  },
  training: {
    title: "Add the trainings your lab requires",
    hint: "List what people must finish, so everyone can see what they still need.",
    path: "training",
    action: "Open Training",
  },
};

/** Shown on Home until every step is done or this person dismisses it (D234). */
export function GettingStarted({ labId }: { labId: string }) {
  const { data } = useGettingStarted(labId);
  const dismiss = useSetGettingStartedDismissed(labId);
  if (!data || data.dismissed || data.steps.every((s) => s.done)) return null;
  const done = data.steps.filter((s) => s.done).length;
  return (
    <section aria-labelledby="getting-started" className="mb-8 rounded-lg border p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1 basis-56">
          <h2 id="getting-started" className="text-base font-semibold">
            Get your lab set up
          </h2>
          <p className="text-sm text-muted-foreground">
            {done} of {data.steps.length} done. These tick themselves as you go.
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => window.dispatchEvent(new Event(OPEN_TUTORIAL_EVENT))}
          >
            Take the tour
          </Button>
          <Button
            variant="ghost"
            size="sm"
            disabled={dismiss.isPending}
            onClick={() => dismiss.mutate(true)}
          >
            Dismiss
          </Button>
        </div>
      </div>
      <ul className="mt-3 grid gap-2">
        {data.steps.map((step) => {
          const info = STEPS[step.key];
          if (!info) return null;
          const Icon = step.done ? CheckCircle2 : Circle;
          return (
            <li key={step.key} className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <Icon
                aria-hidden
                className={step.done ? "size-4 text-success-text" : "size-4 text-muted-foreground"}
              />
              <div className="min-w-0 flex-1 basis-56">
                <p className="text-sm font-medium">
                  {info.title}
                  {step.done && <span className="sr-only"> (done)</span>}
                </p>
                {!step.done && (
                  <p className="text-xs text-muted-foreground">
                    {step.can_act ? info.hint : "Your PI or lab admin can do this."}
                  </p>
                )}
              </div>
              {!step.done && step.can_act && (
                <Button variant="secondary" size="sm" asChild>
                  <Link to={`/labs/${labId}/${info.path}`}>{info.action}</Link>
                </Button>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
