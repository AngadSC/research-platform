import { ExternalLink } from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
import { useGettingStarted, useSetGettingStartedDismissed } from "@/hooks/dashboard";
import { useCurrentLabId } from "@/hooks/crumbs";
import { FEEDBACK_URL, MOD_KEY, OPEN_TUTORIAL_EVENT } from "@/lib/constants";

const QUESTIONS = [
  [
    "Who can see my project?",
    "The people added to the project, plus your lab's PI and lab admins. Other lab members do not see it until someone adds them.",
  ],
  [
    "What should I never upload?",
    "Anything that identifies a participant, such as names, emails or ID numbers. Upload only anonymized or combined data.",
  ],
  [
    "Do I need to save documents?",
    "No. A document saves itself a few seconds after you stop typing. Open its menu and choose History to see or bring back an older version.",
  ],
  [
    "Someone else changed the document I am editing. What now?",
    "You will see a message asking what to do. Your work is never overwritten without asking, and you can copy your changes before reloading.",
  ],
  [
    "Why can I not change something?",
    "What you can do depends on your role in the lab and on the project. Ask your PI or lab admin, who can change your role on the Members page.",
  ],
  [
    "Where do I see what I have to do?",
    "My work lists your tasks, deadlines and required training on one page.",
  ],
] as const;

const SHORTCUTS = [
  [`${MOD_KEY} K`, "Search, or jump to any page"],
  [`${MOD_KEY} S`, "Save the document you are editing"],
  ["/", "In a document, open the list of things to add"],
  ["Up, Down, Enter", "Move through the search results and open one"],
  ["Esc", "Close a dialog, menu or the side menu"],
] as const;

function ShowChecklistAgain({ labId }: { labId: string }) {
  const { data } = useGettingStarted(labId);
  const show = useSetGettingStartedDismissed(labId);
  if (!data?.dismissed) return null;
  return (
    <Button
      variant="outline"
      disabled={show.isPending}
      onClick={() =>
        show.mutate(false, {
          onSuccess: () => toast.success("The checklist is back on your lab's Home page."),
        })
      }
    >
      Show the getting-started checklist
    </Button>
  );
}

export function HelpPage() {
  const labId = useCurrentLabId();
  return (
    <>
      <PageHeader title="Help" description="Answers, shortcuts and a way to tell us what to fix." />
      <div className="grid max-w-2xl gap-8">
        <section aria-labelledby="help-start" className="grid gap-3">
          <h2 id="help-start" className="text-base font-semibold">
            New here?
          </h2>
          <p className="text-sm text-muted-foreground">
            The tour takes about two minutes. It opens each main page and says what it is for.
          </p>
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => window.dispatchEvent(new Event(OPEN_TUTORIAL_EVENT))}>
              Take the tour
            </Button>
            {labId && <ShowChecklistAgain labId={labId} />}
          </div>
        </section>

        <section aria-labelledby="help-questions" className="grid gap-2">
          <h2 id="help-questions" className="text-base font-semibold">
            Common questions
          </h2>
          {QUESTIONS.map(([question, answer]) => (
            <details key={question} className="rounded-md border p-3 text-sm">
              <summary className="cursor-pointer font-medium">{question}</summary>
              <p className="mt-2 text-muted-foreground">{answer}</p>
            </details>
          ))}
        </section>

        <section aria-labelledby="help-keys" className="grid gap-2">
          <h2 id="help-keys" className="text-base font-semibold">
            Keyboard shortcuts
          </h2>
          <dl className="grid grid-cols-[auto_minmax(0,1fr)] items-baseline gap-x-4 gap-y-2 text-sm">
            {SHORTCUTS.map(([keys, what]) => (
              <div key={keys} className="contents">
                <dt>
                  <kbd className="rounded border bg-muted px-1.5 py-0.5 text-xs font-medium">
                    {keys}
                  </kbd>
                </dt>
                <dd className="text-muted-foreground">{what}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section aria-labelledby="help-feedback" className="grid gap-3">
          <h2 id="help-feedback" className="text-base font-semibold">
            Send feedback
          </h2>
          <p className="text-sm text-muted-foreground">
            Found a problem or have an idea? Tell us on GitHub. You need a free GitHub account, and
            what you write there is public, so do not include names, participant details or anything
            private.
          </p>
          <div>
            <Button variant="outline" asChild>
              <a href={FEEDBACK_URL} target="_blank" rel="noopener noreferrer">
                Send feedback
                <ExternalLink aria-hidden />
                <span className="sr-only">(opens in a new tab)</span>
              </a>
            </Button>
          </div>
        </section>
      </div>
    </>
  );
}
