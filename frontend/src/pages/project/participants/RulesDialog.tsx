import { useEffect, useState } from "react";
import { toast } from "sonner";
import { FormError } from "@/components/shared/FormError";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  logFlowExport,
  useFlow,
  useRegistry,
  useRules,
  useSetDetail,
  type Rule,
  type RuleResult,
} from "@/hooks/participants";
import { download, flowRows, flowSvg, flowTableHtml, svgToPng } from "@/lib/flowExport";
import { formErrors } from "@/lib/forms";
import { RelativeTime } from "@/components/shared/RelativeTime";

type Props = {
  labId: string;
  projectId: string;
  canEdit: boolean;
  canExport: boolean;
  onClose: () => void;
};

/** Rules for who counts, locked sets, and the flow summary, in one place. */
export function RulesDialog({ labId, projectId, canEdit, canExport, onClose }: Props) {
  const { rules, save, remove, preview, sets, lock, newVersion } = useRules(labId, projectId);
  const { columns, participants } = useRegistry(labId, projectId);
  const cols = columns.data ?? [];
  const groups = [...new Set((participants.data ?? []).map((p) => p.group).filter(Boolean))];

  const [editing, setEditing] = useState<Rule | "new" | null>(null);
  const [name, setName] = useState("");
  const [requires, setRequires] = useState<string[]>([]);
  const [only, setOnly] = useState<string[]>([]);
  const [result, setResult] = useState<RuleResult>();
  const [error, setError] = useState<string>();
  const [openSet, setOpenSet] = useState<string>();
  const detail = useSetDetail(labId, projectId, openSet).data;
  const [flowSet, setFlowSet] = useState<string>();
  const flow = useFlow(labId, projectId, flowSet).data;

  function start(rule: Rule | "new") {
    setEditing(rule);
    setName(rule === "new" ? "" : rule.name);
    setRequires(rule === "new" ? [] : rule.spec.requires);
    setOnly(rule === "new" ? [] : rule.spec.groups);
    setError(undefined);
  }

  // The live answer: who counts under the rule as it is written now.
  useEffect(() => {
    if (!editing) return;
    const t = setTimeout(
      () => preview.mutate({ requires, groups: only }, { onSuccess: setResult }),
      250,
    );
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editing, requires, only]);

  async function submit() {
    setError(undefined);
    try {
      await save.mutateAsync({
        ...(editing !== "new" && editing ? { id: editing.id } : {}),
        name,
        spec: { requires, groups: only, exclude_enrolment: ["withdrawn", "ineligible"] },
      });
      toast.success("Rule saved");
      setEditing(null);
    } catch (e) {
      const f = formErrors(e, ["name", "spec"]);
      setError(f.fields.name ?? f.fields.spec ?? f.form);
    }
  }

  const toggle = (list: string[], v: string, set: (l: string[]) => void) =>
    set(list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);
  const colName = (key: string) => cols.find((c) => c.key === key)?.name ?? key;

  async function exportAs(kind: "table" | "svg" | "png") {
    if (!flow) return;
    try {
      await logFlowExport(labId, projectId, kind);
    } catch {
      toast.error("Only a project lead can export this.");
      return;
    }
    if (kind === "table") {
      const html = flowTableHtml(flow);
      try {
        await navigator.clipboard.write([
          new ClipboardItem({ "text/html": new Blob([html], { type: "text/html" }) }),
        ]);
        toast.success("Copied. Paste it into Word.");
      } catch {
        download("participant-flow.html", new Blob([html], { type: "text/html" }));
      }
    } else if (kind === "svg") {
      download("participant-flow.svg", new Blob([flowSvg(flow)], { type: "image/svg+xml" }));
    } else {
      download("participant-flow.png", await svgToPng(flowSvg(flow)));
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-3xl">
        <DialogTitle>Rules, locked sets and flow</DialogTitle>
        <DialogDescription>
          Say who counts for each paper, lock that list when you run the analysis, and report how
          many people it came to.
        </DialogDescription>

        <section aria-label="Inclusion rules" className="grid gap-2">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold">Inclusion rules</h2>
            {canEdit && !editing && (
              <Button size="sm" onClick={() => start("new")}>
                New rule
              </Button>
            )}
          </div>
          {editing ? (
            <div className="grid gap-3 rounded-lg border p-3">
              <label className="grid gap-1 text-sm">
                <span className="font-medium">Rule name</span>
                <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={120} />
              </label>
              <fieldset className="grid gap-1">
                <legend className="text-sm font-medium">These columns must be Complete</legend>
                {cols.map((c) => (
                  <label key={c.id} className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={requires.includes(c.key)}
                      onChange={() => toggle(requires, c.key, setRequires)}
                    />
                    {c.name}
                  </label>
                ))}
              </fieldset>
              {groups.length > 0 && (
                <fieldset className="grid gap-1">
                  <legend className="text-sm font-medium">
                    Only these groups (none ticked means all)
                  </legend>
                  {groups.map((g) => (
                    <label key={g} className="flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={only.includes(g)}
                        onChange={() => toggle(only, g, setOnly)}
                      />
                      {g}
                    </label>
                  ))}
                </fieldset>
              )}
              <p className="text-xs text-muted-foreground">
                Withdrawn and ineligible participants never count.
              </p>
              {result && (
                <div role="status" className="rounded-md bg-muted p-3 text-sm">
                  <strong>{result.eligible.length} eligible</strong>, {result.one_away.length} one
                  step away, {result.not_eligible} not eligible.
                  {result.one_away.length > 0 && (
                    <ul className="mt-1 list-disc pl-5">
                      {result.one_away.slice(0, 6).map((o) => (
                        <li key={o.code}>
                          {o.code} needs {o.blocking[0]?.column}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
              <FormError message={error} />
              <div className="flex justify-end gap-2">
                <Button variant="outline" onClick={() => setEditing(null)}>
                  Cancel
                </Button>
                <Button disabled={!name.trim() || save.isPending} onClick={() => void submit()}>
                  Save rule
                </Button>
              </div>
            </div>
          ) : (rules.data ?? []).length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No rules yet. A rule lists the data a participant needs before they count for a paper.
            </p>
          ) : (
            <ul className="divide-y rounded-lg border text-sm">
              {rules.data!.map((r) => (
                <li key={r.id} className="flex flex-wrap items-center gap-2 px-3 py-2">
                  <span className="min-w-40 flex-1">
                    <span className="font-medium">{r.name}</span>{" "}
                    <span className="text-xs text-muted-foreground">
                      version {r.version} · needs{" "}
                      {r.spec.requires.map(colName).join(", ") || "nothing"}
                    </span>
                  </span>
                  {canEdit && (
                    <>
                      <Button size="sm" variant="outline" onClick={() => start(r)}>
                        Edit
                      </Button>
                      <Button
                        size="sm"
                        onClick={() =>
                          lock.mutate(
                            { name: r.name, rule: r.id },
                            {
                              onSuccess: (s) => toast.success(`Locked ${s.size} participants`),
                              onError: (e) =>
                                toast.error(
                                  formErrors(e, ["rule"]).fields.rule ?? "Could not lock.",
                                ),
                            },
                          )
                        }
                      >
                        Lock a set
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        aria-label={`Remove ${r.name}`}
                        onClick={() => remove.mutate(r.id)}
                      >
                        Remove
                      </Button>
                    </>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>

        <section aria-label="Locked sets" className="grid gap-2">
          <h2 className="text-base font-semibold">Locked sets</h2>
          {(sets.data ?? []).length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Nothing locked. Locking records exactly who was included, and which version of each
              linked file.
            </p>
          ) : (
            <ul className="divide-y rounded-lg border text-sm">
              {sets.data!.map((s) => (
                <li key={s.id} className="grid gap-1 px-3 py-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      className="font-medium underline-offset-2 hover:underline"
                      aria-expanded={openSet === s.id}
                      onClick={() => setOpenSet(openSet === s.id ? undefined : s.id)}
                    >
                      {s.name}
                    </button>
                    <span className="text-muted-foreground">
                      {s.size} participants · rule v{s.rule_version} · locked{" "}
                      <RelativeTime value={s.locked_at} />
                    </span>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="ml-auto"
                      onClick={() => setFlowSet(flowSet === s.id ? undefined : s.id)}
                    >
                      {flowSet === s.id ? "Flow: this set" : "Use in flow"}
                    </Button>
                  </div>
                  {openSet === s.id && detail && (
                    <div className="grid gap-2 rounded-md bg-muted p-2">
                      {detail.changes.length > 0 ? (
                        <div role="alert" className="text-sm">
                          <strong>Data changed since this was locked.</strong> The list below has
                          not changed.
                          <ul className="list-disc pl-5">
                            {detail.changes.slice(0, 8).map((c, i) => (
                              <li key={i}>
                                {c.participant}, {c.column}: {c.kind}
                              </li>
                            ))}
                          </ul>
                          {canEdit && (
                            <Button
                              size="sm"
                              className="mt-2"
                              onClick={() =>
                                newVersion.mutate(s.id, {
                                  onSuccess: () => toast.success("New version locked"),
                                })
                              }
                            >
                              Lock a new version
                            </Button>
                          )}
                        </div>
                      ) : (
                        <p className="text-sm">Nothing has changed since it was locked.</p>
                      )}
                      <p className="text-xs text-muted-foreground">{detail.codes.join(", ")}</p>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>

        <section aria-label="Participant flow" className="grid gap-2">
          <h2 className="text-base font-semibold">Participant flow</h2>
          {flow && (
            <>
              <table className="w-full text-sm">
                <tbody>
                  {flowRows(flow).map((r) => (
                    <tr key={r.label} className="border-b">
                      <td className="py-1">{r.label}</td>
                      <td className="py-1 text-right font-medium">
                        {r.count}
                        {r.small && <span aria-label="small number"> *</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {flow.warning && (
                <p role="note" className="text-xs text-muted-foreground">
                  * {flow.warning}
                </p>
              )}
              {canExport ? (
                <div className="flex flex-wrap gap-2">
                  <Button size="sm" variant="outline" onClick={() => void exportAs("table")}>
                    Copy table for Word
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => void exportAs("svg")}>
                    Download SVG
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => void exportAs("png")}>
                    Download PNG
                  </Button>
                </div>
              ) : (
                <p className="text-xs text-muted-foreground">
                  Only a project lead can export this.
                </p>
              )}
            </>
          )}
        </section>
      </DialogContent>
    </Dialog>
  );
}
