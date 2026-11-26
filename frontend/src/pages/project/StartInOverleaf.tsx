import { useState } from "react";
import { ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useProjectMembers } from "@/hooks/projects";
import { manuscriptTemplate, openOverleafWindow } from "@/lib/overleaf";

/** Starts a new Overleaf project from a small template (title and the project's people). The
 * person then pastes the new project's address into this record's link. */
export function StartInOverleaf({
  labId,
  projectId,
  title,
}: {
  labId: string;
  projectId: string;
  title: string;
}) {
  const members = useProjectMembers(labId, projectId).list;
  const [started, setStarted] = useState(false);
  const start = () => {
    const names = (members.data ?? []).flatMap((m) => m.user.display_name || []); // never fall back to an email
    openOverleafWindow().post([
      ["encoded_snip", encodeURIComponent(manuscriptTemplate(title, names))],
      ["snip_name", "main.tex"],
    ]);
    setStarted(true);
  };
  return (
    <span className="grid gap-1">
      <Button type="button" variant="outline" size="sm" className="w-fit" onClick={start}>
        <ExternalLink aria-hidden /> Start in Overleaf
      </Button>
      {started && (
        <span role="status" className="text-xs text-muted-foreground">
          Overleaf opened in a new tab. When your project is ready, copy its address from the
          browser bar, then choose Edit and paste it into the manuscript link.
        </span>
      )}
    </span>
  );
}
