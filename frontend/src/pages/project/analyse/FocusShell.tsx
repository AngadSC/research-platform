import { Database, PanelLeftClose, PanelLeftOpen, Minimize2 } from "lucide-react";
import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent,
  type ReactNode,
} from "react";
import { Button } from "@/components/ui/button";
import { useViewPrefs } from "@/hooks/viewPrefs";
import type { EngineState, TestSpec } from "@/lib/stats/contract";
import { cn } from "@/lib/utils";

interface FocusPrefs {
  /** Share of the width the data pane takes, in percent. */
  dataWidth: number;
  dataOpen: boolean;
}
const DEFAULTS: FocusPrefs = { dataWidth: 40, dataOpen: true };
const MIN = 18;
const MAX = 70;

const isTyping = (t: EventTarget | null) =>
  t instanceof HTMLElement &&
  (["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName) || t.isContentEditable);

/**
 * The statistics workspace with nothing else on screen: a ribbon of analyses on top, the data on
 * the left, options and results on the right, a status line below. The parts are made by the
 * Analyse page; this only arranges them.
 */
export function FocusShell({
  tabs,
  projectId,
  title,
  engineState,
  groups,
  testId,
  onPick,
  picker,
  needsData,
  data,
  options,
  results,
  messages,
  onExit,
}: {
  /** The strip of report tabs. */
  tabs?: ReactNode;
  projectId: string;
  title: string;
  engineState: EngineState;
  groups: { g: string; tests: TestSpec[] }[];
  testId: string;
  onPick: (t: TestSpec) => void;
  picker: ReactNode;
  /** No file is open yet: show the chooser instead of the panes. */
  needsData: boolean;
  data: ReactNode;
  options: ReactNode;
  results: ReactNode;
  messages: ReactNode;
  onExit: () => void;
}) {
  const { view, update } = useViewPrefs<FocusPrefs>("stats-focus", projectId, DEFAULTS);
  const selected = groups.find((x) => x.tests.some((t) => t.id === testId))?.g;
  const [tab, setTab] = useState(selected ?? groups[0]?.g ?? "");
  const [chooser, setChooser] = useState(false);
  const body = useRef<HTMLDivElement>(null);
  const activeGroup = groups.find((x) => x.g === tab) ?? groups[0];

  // Esc leaves focus (unless a dialog or a field wants the key); D shows or hides the data.
  useEffect(() => {
    function onKey(e: globalThis.KeyboardEvent) {
      if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "Escape" && !document.querySelector('[role="dialog"]')) onExit();
      else if ((e.key === "d" || e.key === "D") && !isTyping(e.target))
        update({ dataOpen: !view.dataOpen });
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onExit, update, view.dataOpen]);

  function drag(e: PointerEvent<HTMLDivElement>) {
    const box = body.current?.getBoundingClientRect();
    if (!box || !(e.buttons & 1)) return;
    const pct = ((e.clientX - box.left) / box.width) * 100;
    update({ dataWidth: Math.round(Math.min(MAX, Math.max(MIN, pct))) });
  }
  function nudge(e: KeyboardEvent<HTMLDivElement>) {
    const step = e.key === "ArrowLeft" ? -3 : e.key === "ArrowRight" ? 3 : 0;
    if (!step) return;
    e.preventDefault();
    update({ dataWidth: Math.min(MAX, Math.max(MIN, view.dataWidth + step)) });
  }

  const working = engineState.state === "loading" || engineState.state === "running";
  const status =
    engineState.state === "loading" || engineState.state === "running"
      ? engineState.message
      : engineState.state === "error"
        ? engineState.message
        : engineState.state === "ready"
          ? "Ready"
          : "Starting";

  return (
    <div
      role="region"
      aria-label="Statistics workspace"
      className="fixed inset-0 z-[45] flex flex-col bg-background text-foreground"
    >
      <header className="flex items-center gap-2 border-b px-3 py-2">
        <Button variant="ghost" size="sm" onClick={onExit}>
          <Minimize2 aria-hidden /> Exit focus
        </Button>
        <h1 className="min-w-0 flex-1 truncate text-sm font-semibold">{title}</h1>
        <Button
          variant="ghost"
          size="sm"
          aria-pressed={chooser || needsData}
          onClick={() => setChooser((c) => !c)}
        >
          <Database aria-hidden /> Data source
        </Button>
        {!needsData && (
          <Button
            variant="ghost"
            size="sm"
            aria-pressed={view.dataOpen}
            onClick={() => update({ dataOpen: !view.dataOpen })}
          >
            {view.dataOpen ? <PanelLeftClose aria-hidden /> : <PanelLeftOpen aria-hidden />} Data
            pane
          </Button>
        )}
      </header>

      {tabs && <div className="px-3 pt-1">{tabs}</div>}

      {(chooser || needsData) && (
        <div className="max-h-[45vh] overflow-y-auto border-b bg-muted/40 px-4 py-3">{picker}</div>
      )}

      {!needsData && (
        <div className="border-b px-3 pt-2">
          <div role="tablist" aria-label="Analysis groups" className="flex gap-1 overflow-x-auto">
            {groups.map(({ g }) => (
              <button
                key={g}
                type="button"
                role="tab"
                id={`ribbon-tab-${g}`}
                aria-selected={tab === g}
                aria-controls="ribbon-panel"
                onClick={() => setTab(g)}
                className={cn(
                  "-mb-px shrink-0 rounded-t-lg border-b-2 px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
                  tab === g ? "border-primary font-medium text-foreground" : "border-transparent",
                )}
              >
                {g}
                {g === selected && (
                  <span
                    aria-hidden
                    className="ml-1.5 inline-block size-1.5 rounded-full bg-primary"
                  />
                )}
              </button>
            ))}
          </div>
          <div
            role="tabpanel"
            id="ribbon-panel"
            aria-labelledby={`ribbon-tab-${activeGroup?.g}`}
            className="flex flex-wrap gap-1.5 py-2"
          >
            {activeGroup?.tests.map((t) => (
              <button
                key={t.id}
                type="button"
                aria-pressed={testId === t.id}
                title={t.help}
                onClick={() => onPick(t)}
                className={cn(
                  "glass-field rounded-lg px-2.5 py-1 text-sm hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
                  testId === t.id && "border-primary bg-primary/10 font-medium",
                )}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {!needsData && (
        <div ref={body} className="flex min-h-0 flex-1 flex-col md:flex-row">
          {view.dataOpen && (
            <>
              <section
                aria-label="Data pane"
                style={{ flexBasis: `${view.dataWidth}%` }}
                className="max-h-[40%] min-h-0 shrink-0 grow-0 overflow-auto p-3 md:max-h-none"
              >
                {data}
              </section>
              <div
                role="separator"
                aria-orientation="vertical"
                aria-label="Resize the data pane"
                aria-valuemin={MIN}
                aria-valuemax={MAX}
                aria-valuenow={view.dataWidth}
                tabIndex={0}
                onPointerDown={(e) => e.currentTarget.setPointerCapture(e.pointerId)}
                onPointerMove={drag}
                onKeyDown={nudge}
                onDoubleClick={() => update({ dataWidth: DEFAULTS.dataWidth })}
                className="hidden w-1.5 shrink-0 cursor-col-resize bg-border hover:bg-primary/40 focus-visible:bg-primary/60 focus-visible:outline-none md:block"
              />
            </>
          )}
          <section
            aria-label="Options and results"
            className="min-h-0 min-w-0 flex-1 overflow-y-auto p-3"
          >
            <div className="mx-auto grid max-w-5xl gap-4">
              {messages}
              {options}
              {results}
              {!options && !results && (
                <p className="py-10 text-center text-sm text-muted-foreground">
                  Choose an analysis in the ribbon above. Results appear here.
                </p>
              )}
            </div>
          </section>
        </div>
      )}

      <footer className="flex items-center gap-3 border-t px-3 py-1.5 text-xs text-muted-foreground">
        <span
          aria-hidden
          className={cn(
            "size-2 rounded-full",
            engineState.state === "error"
              ? "bg-danger"
              : working
                ? "animate-pulse bg-primary"
                : "bg-success",
          )}
        />
        <span role="status">{status}</span>
        <span className="ml-auto hidden sm:inline">
          Esc leaves focus · D shows or hides the data · double-click the divider to reset it
        </span>
      </footer>
    </div>
  );
}
