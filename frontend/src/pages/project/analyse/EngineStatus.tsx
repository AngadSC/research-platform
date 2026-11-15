import { useEffect, useState } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import type { EngineState } from "@/lib/stats/contract";

const HEAVY = ["anova_twoway", "linear_regression", "logistic_regression"];

/** Plain words for what the engine is doing. There are no byte-level progress events, so no percentage. */
function engineText(s: EngineState, testId: string): { title: string; detail?: string } {
  if (s.state === "loading" && s.message.startsWith("Getting more")) {
    return {
      title: "Downloading more statistics tools",
      detail: HEAVY.includes(testId)
        ? "This test needs about 14 MB (scipy) plus 8.4 MB (statsmodels) the first time. It happens only once. Later visits are instant."
        : "This test needs about 14 MB (scipy) the first time. It happens only once. Later visits are instant.",
    };
  }
  if (s.state === "loading") {
    return {
      title: "Downloading the statistics tools",
      detail:
        "About 14.5 MB (Python and pandas) the first time. It happens only once. Later visits are instant.",
    };
  }
  return { title: "message" in s ? s.message : "" };
}

function Elapsed() {
  const [secs, setSecs] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setSecs((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, []);
  return <span>{secs} s</span>;
}

export function EngineStatus({ state, testId }: { state: EngineState; testId: string }) {
  if (state.state !== "loading" && state.state !== "running") return null;
  const { title, detail } = engineText(state, testId);
  return (
    <div role="status" className="grid gap-2">
      <Skeleton className="h-2 w-64" />
      <p className="text-sm font-medium">
        {title} · <Elapsed key={title} />
      </p>
      {detail && <p className="text-sm text-muted-foreground">{detail}</p>}
    </div>
  );
}
