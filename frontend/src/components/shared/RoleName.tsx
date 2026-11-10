import { useState } from "react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

/** A role with a short explanation on hover, keyboard focus or tap. */
export function RoleName({
  role,
  roles,
}: {
  role: string;
  roles: readonly { value: string; label: string; help: string }[];
}) {
  const [open, setOpen] = useState(false);
  const found = roles.find((r) => r.value === role);
  if (!found) return <>{role}</>;
  return (
    <Tooltip open={open} onOpenChange={setOpen}>
      {/* preventDefault stops Radix closing it again, so a tap on a phone opens it */}
      <TooltipTrigger
        type="button"
        className="cursor-help underline decoration-dotted underline-offset-4 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
        onPointerDown={(e) => e.preventDefault()}
        onClick={(e) => {
          e.preventDefault();
          setOpen((v) => !v);
        }}
      >
        {found.label}
      </TooltipTrigger>
      <TooltipContent className="max-w-64">{found.help}</TooltipContent>
    </Tooltip>
  );
}
