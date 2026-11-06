import { BookOpen, Database, FlaskConical, Gavel, ChartLine } from "lucide-react";
import type { ComponentType } from "react";
import type { LineageKind } from "@/lib/api-types";

/** Icon and tint per kind. Tints use theme tokens only, so both themes keep AA contrast. */
export const KIND_STYLE: Record<
  LineageKind,
  { icon: ComponentType<{ className?: string }>; chip: string }
> = {
  dataset: { icon: Database, chip: "bg-primary/10 text-primary" },
  analysis: { icon: FlaskConical, chip: "bg-success/10 text-success-text" },
  result: { icon: ChartLine, chip: "bg-warning/10 text-warning-text" },
  manuscript: { icon: BookOpen, chip: "bg-secondary text-foreground" },
  decision: { icon: Gavel, chip: "bg-muted text-muted-foreground" },
};
