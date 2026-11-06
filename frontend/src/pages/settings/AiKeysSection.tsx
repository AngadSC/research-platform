import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { FormError } from "@/components/shared/FormError";
import { RelativeTime } from "@/components/shared/RelativeTime";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  useAiKeys,
  useRemoveAiKey,
  useSaveAiKey,
  useSetRefusalFallback,
  type KeyStatus,
} from "@/hooks/assistant";
import { ApiError } from "@/lib/api";
import { Section } from "@/pages/admin/common";

const HELP: Record<string, string> = {
  anthropic: "Starts with sk-ant-. Create one in the Anthropic Console.",
  openai: "Starts with sk-. Create one in the OpenAI dashboard.",
};

function KeyRow({ k }: { k: KeyStatus }) {
  const save = useSaveAiKey();
  const remove = useRemoveAiKey();
  const fallback = useSetRefusalFallback();
  const [value, setValue] = useState("");
  const [error, setError] = useState("");

  function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    save.mutate(
      { provider: k.provider, apiKey: value.trim() },
      {
        onSuccess: () => {
          setValue(""); // the key is never kept in the page after it is sent
          toast.success(`${k.label} key checked and saved.`);
        },
        onError: (err) =>
          setError(
            err instanceof ApiError ? (err.fieldErrors.api_key ?? err.message) : "Try again.",
          ),
      },
    );
  }

  return (
    <div className="grid gap-3 rounded-md border p-4" role="group" aria-label={`${k.label} key`}>
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-medium">
          {k.label}{" "}
          {k.saved ? (
            <Badge variant="success">Saved: ending {k.last4}</Badge>
          ) : (
            <Badge variant="outline">Not saved</Badge>
          )}
        </p>
        {k.saved && (
          <Button
            variant="outline"
            size="sm"
            aria-label={`Remove ${k.label} key`}
            disabled={remove.isPending}
            onClick={() =>
              remove.mutate(k.provider, {
                onSuccess: () => toast.success(`${k.label} key removed.`),
                onError: () => toast.error("Could not remove the key. Try again."),
              })
            }
          >
            Remove
          </Button>
        )}
      </div>
      {k.saved && k.updated_at && (
        <p className="text-xs text-muted-foreground">
          Updated <RelativeTime value={k.updated_at} />. The key itself is never shown again.
        </p>
      )}
      <form className="flex flex-wrap items-start gap-2" onSubmit={submit}>
        <div className="grid min-w-60 flex-1 gap-1">
          <Input
            type="password"
            autoComplete="off"
            spellCheck={false}
            aria-label={`${k.label} API key`}
            aria-invalid={error ? true : undefined}
            placeholder={k.saved ? "Paste a new key to replace it" : "Paste your API key"}
            value={value}
            onChange={(e) => setValue(e.target.value)}
          />
          <p className="text-xs text-muted-foreground">{HELP[k.provider]}</p>
          <FormError message={error} />
        </div>
        <Button type="submit" disabled={!value.trim() || save.isPending}>
          {save.isPending ? "Checking…" : k.saved ? "Replace key" : "Check and save"}
        </Button>
      </form>
      {k.provider === "anthropic" && k.saved && (
        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            className="mt-1"
            checked={k.refusal_fallback}
            disabled={fallback.isPending}
            onChange={(e) =>
              fallback.mutate(e.target.checked, {
                onError: () => toast.error("Could not change the setting."),
              })
            }
          />
          <span>
            If Claude declines a request, retry it automatically on another model chosen by
            Anthropic (recommended). Turn this off to keep every answer on the model you picked.
          </span>
        </label>
      )}
    </div>
  );
}

/** Settings > AI: the person's own provider keys for the in-app assistant (D187). */
export function AiKeysSection() {
  const keys = useAiKeys();
  return (
    <Section
      title="Assistant API keys"
      description="Use the in-app assistant with your own Anthropic or OpenAI key. Usage is billed to your account with the provider, not to the lab. Keys are stored encrypted, belong to you alone (not to a lab), and are never shown again after you save them."
    >
      <p className="text-sm text-muted-foreground">
        When you chat, content from records you can see is sent to the provider under your key and
        your account terms with them. Do not paste participant identifiers. If your lab holds
        sensitive participant data, check with your PI first: they can turn assistants off.
      </p>
      {keys.isError && <FormError message="Could not load your keys. Try again." />}
      {(keys.data ?? []).map((k) => (
        <KeyRow key={k.provider} k={k} />
      ))}
    </Section>
  );
}
