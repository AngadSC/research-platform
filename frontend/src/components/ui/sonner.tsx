import type { CSSProperties } from "react";
import { Toaster as Sonner, type ToasterProps } from "sonner";

export function Toaster(props: ToasterProps) {
  return (
    <Sonner
      style={
        {
          "--normal-bg": "var(--glass-bg-strong)",
          "--normal-text": "var(--popover-foreground)",
          "--normal-border": "var(--glass-border)",
          "--border-radius": "var(--radius-lg)",
        } as CSSProperties
      }
      toastOptions={{
        classNames: { toast: "glass--strong backdrop-blur-xl !shadow-[var(--shadow-glass-2)]" },
      }}
      {...props}
    />
  );
}
