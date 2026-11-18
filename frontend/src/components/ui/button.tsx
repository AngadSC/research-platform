import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import {
  Check,
  Link2,
  Play,
  Plug,
  Send,
  Download,
  Pencil,
  Plus,
  RotateCcw,
  Save,
  Trash2,
  Upload,
  X,
  type LucideIcon,
} from "lucide-react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

/** A familiar icon for the common verbs, so buttons read at a glance. Only plain-text buttons get
 * one, and never when the caller put their own icon in. */
const VERB_ICONS: [RegExp, LucideIcon][] = [
  [/^(remove|delete|discard)\b/i, Trash2],
  [/^(edit|rename)\b/i, Pencil],
  [/^(add|new|create|invite)\b/i, Plus],
  [/^(save|update)\b/i, Save],
  [/^(mark|done|complete|approve|confirm|accept)\b/i, Check],
  [/^(cancel|close|dismiss)\b/i, X],
  [/^(reopen|undo|retry|reset)\b/i, RotateCcw],
  [/^(download|export)\b/i, Download],
  [/^(import|upload)\b/i, Upload],
  [/^(link|attach)\b/i, Link2],
  [/^run\b/i, Play],
  [/^connect\b/i, Plug],
  [/^(send|share|post)\b/i, Send],
];
const iconFor = (children: React.ReactNode): LucideIcon | null =>
  typeof children === "string"
    ? (VERB_ICONS.find(([re]) => re.test(children.trim()))?.[1] ?? null)
    : null;

const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-2 rounded-md text-sm font-medium whitespace-nowrap focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50 [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default: "btn-primary-glass bg-primary text-primary-foreground",
        secondary: "btn-tint",
        outline: "btn-glass text-foreground",
        ghost: "glass-ghost text-foreground/80 hover:text-foreground",
        success: "bg-success text-success-foreground hover:bg-success/90",
        warning: "bg-warning text-warning-foreground hover:bg-warning/90",
        destructive: "bg-danger text-danger-foreground hover:bg-danger/90",
      },
      size: {
        default: "h-9 px-4 py-2 max-md:h-10",
        sm: "h-8 px-3 max-md:h-10",
        lg: "h-11 px-6 text-base",
        icon: "size-9 max-md:size-10",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

interface ButtonProps extends React.ComponentProps<"button">, VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    // An icon-only button has no words, so its name is the hover tip.
    const Auto = !asChild && size !== "icon" ? iconFor(props.children) : null;
    const dangerous = Auto === Trash2 && variant !== "destructive";
    const tip = size === "icon" && !props.title ? props["aria-label"] : undefined;
    return (
      <Comp
        ref={ref}
        className={cn(
          buttonVariants({ variant, size }),
          dangerous && "text-danger-text hover:bg-danger/10 hover:text-danger-text",
          className,
        )}
        {...(tip ? { title: tip } : {})}
        {...props}
      >
        {Auto ? (
          <>
            <Auto aria-hidden />
            {props.children}
          </>
        ) : (
          props.children
        )}
      </Comp>
    );
  },
);
Button.displayName = "Button";

// eslint-disable-next-line react-refresh/only-export-components
export { Button, buttonVariants };
