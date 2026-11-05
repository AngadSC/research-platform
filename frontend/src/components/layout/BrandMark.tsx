import { APP_NAME } from "@/lib/constants";

/** The product name with its lime mark. Use inside `.sidebar-scope`, where primary is lime. */
export function BrandMark() {
  return (
    <p className="flex items-center gap-2 text-sm font-bold tracking-tight">
      <span aria-hidden className="size-3 rotate-45 rounded-[3px] bg-primary" />
      {APP_NAME}
    </p>
  );
}
