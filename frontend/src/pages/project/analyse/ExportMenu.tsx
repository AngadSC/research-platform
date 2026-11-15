import { ChevronDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

export interface ExportItem {
  label: string;
  run: () => unknown;
}

/** One menu for everything you can do with a table, chart or result: keep it, copy it, send it. */
export function ExportMenu({
  label,
  here,
  google,
}: {
  /** Names the menu for screen readers, for example "Export Group means". */
  label: string;
  /** Copy and download choices. */
  here: ExportItem[];
  /** Send-to-Google choices; left out for people who may not export. */
  google: ExportItem[];
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="sm" aria-label={label}>
          Export <ChevronDown aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {here.map((i) => (
          <DropdownMenuItem key={i.label} onSelect={() => void i.run()}>
            {i.label}
          </DropdownMenuItem>
        ))}
        {google.length > 0 && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuLabel>Your Google Drive</DropdownMenuLabel>
            {google.map((i) => (
              <DropdownMenuItem key={i.label} onSelect={() => void i.run()}>
                {i.label}
              </DropdownMenuItem>
            ))}
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
