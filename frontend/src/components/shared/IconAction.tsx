import type { ComponentProps, ReactNode } from "react";
import { Link } from "react-router";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

/** A button that shows only its icon and says what it does on hover or focus, for toolbars that
 * would otherwise be a row of words. The label is also its accessible name. */
export function IconAction({
  label,
  icon,
  variant = "ghost",
  to,
  ...props
}: Omit<ComponentProps<typeof Button>, "children" | "size" | "aria-label"> & {
  label: string;
  icon: ReactNode;
  /** Makes it a link to this page instead of a button. */
  to?: string;
}) {
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          {to ? (
            <Button variant={variant} size="icon" asChild>
              <Link to={to} aria-label={label}>
                {icon}
              </Link>
            </Button>
          ) : (
            <Button type="button" variant={variant} size="icon" aria-label={label} {...props}>
              {icon}
            </Button>
          )}
        </TooltipTrigger>
        <TooltipContent side="bottom">{label}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
