import * as React from "react";
import * as S from "@radix-ui/react-select";
import { Check, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

export const Select = S.Root;
export const SelectValue = S.Value;
export const SelectGroup = S.Group;

export function SelectLabel({ className, ...props }: React.ComponentProps<typeof S.Label>) {
  return (
    <S.Label
      className={cn("px-2 pt-2 pb-1 text-xs font-medium text-muted-foreground", className)}
      {...props}
    />
  );
}

export function SelectTrigger({
  className,
  children,
  ...props
}: React.ComponentProps<typeof S.Trigger>) {
  return (
    <S.Trigger
      className={cn(
        "glass-field flex h-9 w-full items-center justify-between gap-2 rounded-md px-3 text-sm focus-visible:outline-none max-md:h-10 disabled:opacity-50 aria-[invalid=true]:border-destructive data-[placeholder]:text-muted-foreground",
        className,
      )}
      {...props}
    >
      {children}
      <S.Icon>
        <ChevronDown className="size-4 opacity-60" />
      </S.Icon>
    </S.Trigger>
  );
}

export function SelectContent({
  className,
  children,
  ...props
}: React.ComponentProps<typeof S.Content>) {
  return (
    <S.Portal>
      <S.Content
        position="popper"
        sideOffset={4}
        className={cn(
          "glass glass--strong glass--solid glass-in z-50 min-w-[var(--radix-select-trigger-width)] max-h-[min(var(--radix-select-content-available-height),24rem)] overflow-hidden rounded-lg p-1.5 text-popover-foreground",
          className,
        )}
        {...props}
      >
        <S.Viewport className="max-h-[inherit] overflow-y-auto overscroll-contain">
          {children}
        </S.Viewport>
      </S.Content>
    </S.Portal>
  );
}

export function SelectItem({
  className,
  children,
  hint,
  ...props
}: React.ComponentProps<typeof S.Item> & { hint?: string }) {
  return (
    <S.Item
      className={cn(
        "relative flex cursor-default items-center rounded-sm py-1.5 pr-2 pl-8 text-sm outline-none select-none data-[disabled]:opacity-50 data-[highlighted]:bg-accent",
        className,
      )}
      {...props}
    >
      <span className="absolute left-2 flex size-4 items-center justify-center">
        <S.ItemIndicator>
          <Check className="size-4" />
        </S.ItemIndicator>
      </span>
      <span className="grid">
        <S.ItemText>{children}</S.ItemText>
        {hint && <span className="max-w-56 text-xs text-muted-foreground">{hint}</span>}
      </span>
    </S.Item>
  );
}
