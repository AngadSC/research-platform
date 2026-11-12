import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { FormError } from "@/components/shared/FormError";
import { FormField } from "@/components/shared/FormField";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useCurrentLabId } from "@/hooks/crumbs";
import {
  useAssistantConfig,
  useLabAiKey,
  useRemoveLabAiKey,
  useSaveLabAiKey,
  useSetLabAiCap,
  type Provider,
} from "@/hooks/assistant";
import { useLabs } from "@/hooks/workspace";
import { ApiError } from "@/lib/api";
import { NativeSelect, Section } from "@/pages/admin/common";

const usd = (v: string | number | null | undefined) => `$${Number(v ?? 0).toFixed(2)}`;

/** Admin > AI: the lab's one shared key, its monthly limit and this month's use (VISION A5). */
export function LabAiKeySection({ labId }: { labId: string }) {
  const status = useLabAiKey(labId);
  const save = useSaveLabAiKey(labId);
  const setCap = useSetLabAiCap(labId);
  const remove = useRemoveLabAiKey(labId);
  const [provider, setProvider] = useState<Provider>("anthropic");
  const [apiKey, setApiKey] = useState("");
  const [cap, setCapValue] = useState("");
  const [newCap, setNewCap] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const s = status.data;

  function submitKey(e: FormEvent) {
    e.preventDefault();
    setErrors({});
    save.mutate(
      { provider, api_key: apiKey.trim(), monthly_cap_usd: cap },
      {
        onSuccess: () => {
          setApiKey(""); // the key is never kept in the page after it is sent
          setCapValue("");
          toast.success("Lab key checked and saved.");
        },
        onError: (err) => {
          const f = err instanceof ApiError ? err.fieldErrors : {};
          setErrors(
            f.api_key || f.monthly_cap_usd
              ? f
              : { form: err instanceof ApiError ? err.message : "Try again." },
          );
        },
      },
    );
  }

  function submitCap(e: FormEvent) {
    e.preventDefault();
    setErrors({});
    setCap.mutate(
      { monthly_cap_usd: newCap },
      {
        onSuccess: () => {
          setNewCap("");
          toast.success("Monthly limit saved.");
        },
        onError: (err) =>
          setErrors({
            new_cap:
              err instanceof ApiError
                ? (err.fieldErrors.monthly_cap_usd ?? err.message)
                : "Try again.",
          }),
      },
    );
  }

  return (
    <Section
      title="Lab AI key"
      description="Set one key the whole lab can use for the in-app assistant, with a monthly spending limit. A person's own key is always used first. Nothing is charged to the lab until you add a key."
    >
      {status.isError && <FormError message="Could not load the lab key. Try again." />}
      {status.isLoading && <Skeleton className="h-24 w-full" />}
      {s && (
        <>
          {s.saved ? (
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm">
                {s.label} <Badge variant="success">Saved: ending {s.last4}</Badge>
              </p>
              <Button
                variant="outline"
                size="sm"
                disabled={remove.isPending}
                onClick={() =>
                  remove.mutate(undefined, {
                    onSuccess: () => toast.success("Lab key removed."),
                    onError: () => toast.error("Could not remove the key. Try again."),
                  })
                }
              >
                Remove lab key
              </Button>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              No lab key yet. Members use the assistant with their own keys.
            </p>
          )}

          <form className="grid gap-3" onSubmit={submitKey} aria-label="Set the lab key">
            <FormField label="Provider">
              {(p) => (
                <NativeSelect
                  {...p}
                  value={provider}
                  onChange={(e) => setProvider(e.target.value as Provider)}
                >
                  <option value="anthropic">Anthropic (Claude)</option>
                  <option value="openai">OpenAI</option>
                </NativeSelect>
              )}
            </FormField>
            <FormField label="API key" error={errors.api_key}>
              {(p) => (
                <Input
                  {...p}
                  type="password"
                  autoComplete="off"
                  spellCheck={false}
                  placeholder={s.saved ? "Paste a new key to replace it" : "Paste the lab's key"}
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                />
              )}
            </FormField>
            <FormField
              label="Monthly limit (USD)"
              hint="When the lab's use this month reaches the limit, the lab key stops until next month."
              error={errors.monthly_cap_usd}
            >
              {(p) => (
                <Input
                  {...p}
                  type="number"
                  inputMode="decimal"
                  min={1}
                  step="0.01"
                  value={cap}
                  onChange={(e) => setCapValue(e.target.value)}
                />
              )}
            </FormField>
            <FormError message={errors.form} />
            <div>
              <Button type="submit" disabled={!apiKey.trim() || !cap || save.isPending}>
                {save.isPending ? "Checking…" : s.saved ? "Replace key" : "Check and save"}
              </Button>
            </div>
          </form>

          {s.saved && (
            <form className="flex flex-wrap items-end gap-2" onSubmit={submitCap}>
              <div className="min-w-48 flex-1">
                <FormField
                  label="Change the monthly limit (USD)"
                  hint={`Now ${usd(s.monthly_cap_usd)} a month.`}
                  error={errors.new_cap}
                >
                  {(p) => (
                    <Input
                      {...p}
                      type="number"
                      inputMode="decimal"
                      min={1}
                      step="0.01"
                      value={newCap}
                      onChange={(e) => setNewCap(e.target.value)}
                    />
                  )}
                </FormField>
              </div>
              <Button type="submit" variant="outline" disabled={!newCap || setCap.isPending}>
                Save limit
              </Button>
            </form>
          )}

          <div className="grid gap-2">
            <h3 className="text-sm font-medium">
              This month: {usd(s.spent_usd)}
              {s.saved && ` of ${usd(s.monthly_cap_usd)}`}
            </h3>
            {s.usage.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                Nobody has used the lab key this month.
              </p>
            ) : (
              <Table aria-label="Use of the lab key this month">
                <TableHeader>
                  <TableRow>
                    <TableHead>Person</TableHead>
                    <TableHead className="text-right">Cost</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {s.usage.map((u) => (
                    <TableRow key={u.user}>
                      <TableCell>{u.name}</TableCell>
                      <TableCell className="text-right">{usd(u.cost_usd)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
            <p className="text-xs text-muted-foreground">
              Estimated from list prices. Your provider's bill is the final word.
            </p>
          </div>
        </>
      )}
    </Section>
  );
}

/** Settings > AI: whether the current lab's key is there for this person (VISION A5). */
export function LabKeyNotice() {
  const labId = useCurrentLabId();
  const lab = useLabs().data?.find((l) => l.id === labId);
  const cfg = useAssistantConfig(labId ?? "", !!labId).data;
  if (!lab || !cfg?.can_use) return null;
  const k = cfg.lab_key;
  const text = !k
    ? `${lab.name} has no lab AI key. To use the assistant, add your own key below.`
    : k.own_key_wins
      ? `${lab.name} has a lab key for ${k.label}, but your own ${k.label} key is used first.`
      : k.limit_reached
        ? `${lab.name}'s AI key has reached this month's limit. Add your own key below to keep using the assistant.`
        : `${lab.name} has a lab key for ${k.label}. You can use the assistant without your own key.`;
  return (
    <p role="status" className="rounded-md border p-3 text-sm">
      {text}
    </p>
  );
}
