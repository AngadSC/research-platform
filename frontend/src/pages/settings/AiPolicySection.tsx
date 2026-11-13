import { toast } from "sonner";
import { useLabAiPolicy, useSetLabAiPolicy, type AiPolicy } from "@/hooks/assistant";
import { Section } from "@/pages/admin/common";

const CHOICES: { value: AiPolicy; label: string; help: string }[] = [
  {
    value: "full",
    label: "Connected apps (like Claude) and the in-app assistant",
    help: "Members may connect their own AI app and use the assistant built into this app.",
  },
  {
    value: "mcp",
    label: "Connected apps only",
    help: "Members may connect their own AI app. The in-app assistant is off.",
  },
  {
    value: "off",
    label: "Off",
    help: "No AI assistant of any kind can read this lab. Connected apps get an error.",
  },
];

/** The lab's "Allow AI assistants" setting (D188), shown to pi and lab_admin. */
export function AiPolicySection({ labId, labName }: { labId: string; labName: string }) {
  const policy = useLabAiPolicy(labId);
  const set = useSetLabAiPolicy(labId);
  const current = policy.data?.ai_policy;
  return (
    <Section
      title={`AI assistants in ${labName}`}
      description="Allowed by default. When an assistant is used, content from records the member can see is sent to an AI provider under that member's own account and terms. If this lab holds sensitive participant data, you may need to choose Off."
    >
      <fieldset className="grid gap-3" disabled={!current || set.isPending}>
        <legend className="sr-only">Allow AI assistants</legend>
        {CHOICES.map((c) => (
          <label key={c.value} className="flex items-start gap-2 text-sm">
            <input
              type="radio"
              name={`ai-policy-${labId}`}
              className="mt-1"
              value={c.value}
              checked={current === c.value}
              onChange={() =>
                set.mutate(c.value, {
                  onSuccess: () => toast.success("AI policy saved."),
                  onError: () => toast.error("Could not save. Try again."),
                })
              }
            />
            <span>
              <span className="font-medium">{c.label}</span>
              <span className="block text-muted-foreground">{c.help}</span>
            </span>
          </label>
        ))}
      </fieldset>
    </Section>
  );
}
