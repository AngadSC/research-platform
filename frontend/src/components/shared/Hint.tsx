import { Info } from "lucide-react";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

/** A small "i" that explains a word or a rule on hover, focus or tap. */
export function Hint({ text, label = "What does this mean?" }: { text: string; label?: string }) {
  return (
    <TooltipProvider delayDuration={150}>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            aria-label={`${label} ${text}`}
            className="inline-grid size-4 shrink-0 place-items-center rounded-full text-muted-foreground hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
          >
            <Info aria-hidden className="size-3.5" />
          </button>
        </TooltipTrigger>
        <TooltipContent className="max-w-64">{text}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
