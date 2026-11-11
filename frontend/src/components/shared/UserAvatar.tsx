import { useState } from "react";
import { initials } from "@/lib/identity";
import { cn } from "@/lib/utils";

/** A hue from the person's id, so the same person always gets the same colour. */
function hue(seed: string) {
  let h = 0;
  for (const c of seed) h = (h * 31 + c.charCodeAt(0)) % 360;
  return h;
}

/**
 * A person's picture, or their initials on a coloured circle. Decorative: the name always sits
 * beside it, so it is hidden from screen readers.
 */
export function UserAvatar({
  user,
  className,
}: {
  user: { id?: string; email: string; display_name?: string; avatar_url?: string | null };
  className?: string;
}) {
  const [failed, setFailed] = useState<string>();
  const url = user.avatar_url;
  const base = "inline-flex size-7 shrink-0 items-center justify-center rounded-full";
  if (url && failed !== url) {
    return (
      <img
        src={url}
        alt=""
        aria-hidden
        onError={() => setFailed(url)}
        className={cn(base, "bg-muted object-cover", className)}
      />
    );
  }
  const name = user.display_name || user.email;
  return (
    <span
      aria-hidden
      // 38% lightness keeps white text above 4.5:1 for every hue, in light and dark mode
      style={{ backgroundColor: `hsl(${hue(user.id ?? user.email)} 45% 38%)` }}
      className={cn(base, "text-xs font-semibold text-white", className)}
    >
      {initials(name)}
    </span>
  );
}
