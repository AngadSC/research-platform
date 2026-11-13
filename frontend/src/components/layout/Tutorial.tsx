import { X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { Button } from "@/components/ui/button";
import { useCurrentLabId } from "@/hooks/crumbs";
import { APP_NAME, MOD_KEY, OPEN_TUTORIAL_EVENT } from "@/lib/constants";

const KEY = "tutorial-step";

/** Each step opens the page it describes. `path` is inside the lab unless it starts with "/". */
const STEPS = [
  {
    title: `Welcome to ${APP_NAME}`,
    body: "Home shows what needs you today. This short tour opens each main page while you read about it.",
    path: "dashboard",
  },
  {
    title: "Projects",
    body: "Each study is a project, with its own tasks, documents, files and chat. You see the projects you have been added to. Never upload anything that identifies a participant.",
    path: "projects",
  },
  {
    title: "My work",
    body: "Your tasks, deadlines and the training you still need, on one page. Check here first when you are not sure what to do next.",
    path: "my-work",
  },
  {
    title: "Lab documents",
    body: "The lab manual, protocols and SOPs. Everyone in the lab can read them, so look here when you have a question about how something is done.",
    path: "documents",
  },
  {
    title: "Ethics and training",
    body: "Ethics lists your lab's approvals and when they end. Training shows what your lab requires of you and lets you record what you have finished.",
    path: "training",
  },
  {
    title: "Calendar and chat",
    body: "The calendar shows lab events, meetings and deadlines. Lab chat is for quick questions to everyone in the lab.",
    path: "calendar",
  },
  {
    title: "The assistant",
    body: `The Assistant button opens an AI helper that sees only what you can see. It needs an API key, which you add in Settings (or your lab admin adds one for everyone). ${MOD_KEY} . opens and closes it.`,
    path: "dashboard",
  },
  {
    title: "Integrations",
    body: "Connect Google Drive and other tools, or connect Claude and other AI apps to your lab, from the Integrations page.",
    path: "settings/integrations",
  },
  {
    title: "Finding things",
    body: `Press ${MOD_KEY} K on any page to search for a project, document or page. This Help page has answers and shortcuts, and you can restart the tour from here.`,
    path: "/help",
  },
];

function readStep(): number | null {
  // A tour left midway does not come back on a phone, where the card would cover the page.
  if (window.matchMedia?.("(max-width: 639px)").matches) return null;
  try {
    const n = Number(localStorage.getItem(KEY) ?? NaN);
    return Number.isInteger(n) && STEPS[n] ? n : null;
  } catch {
    return null; // storage is blocked: the tour just does not resume
  }
}

function saveStep(step: number | null) {
  try {
    if (step === null) localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, String(step));
  } catch {
    // storage is blocked: the tour lasts until the page reloads
  }
}

/** A guided tour in a card that stays put while pages change, so people can try things (D236). */
export function Tutorial() {
  const navigate = useNavigate();
  const labId = useCurrentLabId();
  const [step, setStep] = useState(readStep);
  const heading = useRef<HTMLHeadingElement>(null);
  const opener = useRef<Element | null>(null);

  const go = useCallback(
    (next: number | null) => {
      if (step === null) opener.current = document.activeElement; // where focus goes back to
      if (next === null) {
        const el = opener.current;
        const back =
          el instanceof HTMLElement && el.isConnected && el !== document.body ? el : null;
        (back ?? document.getElementById("main"))?.focus();
      }
      setStep(next);
      saveStep(next);
      const path = next === null ? undefined : STEPS[next]?.path;
      if (path?.startsWith("/")) void navigate(path);
      else if (path && labId) void navigate(`/labs/${labId}/${path}`);
    },
    [navigate, labId, step],
  );

  useEffect(() => {
    const onOpen = () => go(0);
    window.addEventListener(OPEN_TUTORIAL_EVENT, onOpen);
    return () => window.removeEventListener(OPEN_TUTORIAL_EVENT, onOpen);
  }, [go]);

  useEffect(() => {
    if (step !== null) heading.current?.focus(); // keyboard and screen-reader users follow along
  }, [step]);

  const current = step === null ? undefined : STEPS[step];
  if (step === null || !current) return null;
  const last = step === STEPS.length - 1;
  return (
    <section
      role="dialog"
      aria-modal="false"
      aria-label="Tutorial"
      className="fixed right-4 bottom-4 left-4 z-30 rounded-lg border bg-card p-4 text-card-foreground shadow-lg sm:left-auto sm:w-96 print:hidden"
    >
      <div className="flex items-start justify-between gap-2">
        <h2 ref={heading} tabIndex={-1} className="text-base font-semibold outline-none">
          {current.title}
        </h2>
        <Button variant="ghost" size="icon" aria-label="Close tutorial" onClick={() => go(null)}>
          <X aria-hidden />
        </Button>
      </div>
      <p className="mt-1 text-sm text-muted-foreground">{current.body}</p>
      <div className="mt-3 flex items-center justify-between gap-2">
        <span className="text-xs text-muted-foreground">
          Step {step + 1} of {STEPS.length}
        </span>
        <div className="flex gap-2">
          {step > 0 && (
            <Button variant="outline" size="sm" onClick={() => go(step - 1)}>
              Back
            </Button>
          )}
          <Button size="sm" onClick={() => go(last ? null : step + 1)}>
            {last ? "Finish" : "Next"}
          </Button>
        </div>
      </div>
    </section>
  );
}
