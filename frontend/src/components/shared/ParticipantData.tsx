import { useId } from "react";
import { Badge } from "@/components/ui/badge";

/** VISION A3: items marked this way are never given to Claude or any other AI tool. */
export const PARTICIPANT_HINT =
  "Names, contact details, ID numbers, faces or voices. Claude and other AI tools will never see this. Leave it off for de-identified data.";

export function ParticipantBadge() {
  return (
    <Badge variant="warning" title={PARTICIPANT_HINT}>
      Identifies participants
    </Badge>
  );
}

export function ParticipantCheckbox({
  checked,
  onChange,
  disabled,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
}) {
  const id = useId();
  return (
    <div className="flex items-start gap-2 text-sm">
      <input
        id={id}
        type="checkbox"
        checked={checked}
        disabled={disabled}
        aria-describedby={`${id}-hint`}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5"
      />
      <div>
        <label htmlFor={id} className="font-medium">
          Identifies participants
        </label>
        <p id={`${id}-hint`} className="text-xs text-muted-foreground">
          {PARTICIPANT_HINT}
        </p>
      </div>
    </div>
  );
}
