import { useState, type ChangeEvent } from "react";
import { toast } from "sonner";
import { FormError } from "@/components/shared/FormError";
import { RelativeTime } from "@/components/shared/RelativeTime";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import {
  useImports,
  useLinkHealth,
  type FileMatch,
  type ImportMapping,
  type ImportPreview,
  type ImportResult,
} from "@/hooks/participants";
import { useRegistry } from "@/hooks/participants";
import { formErrors } from "@/lib/forms";
import { CODES_ONLY } from "@/lib/participants";
import { cn } from "@/lib/utils";
import { NativeSelect } from "@/pages/project/workflow/parts";

type Props = { labId: string; projectId: string; onClose: () => void };

const guess = (headers: string[], rx: RegExp) => headers.find((h) => rx.test(h)) ?? "";

/** Sheet or CSV in, three steps: choose, map, check. Nothing is saved until the check passes. */
export function ImportWizard({ labId, projectId, onClose }: Props) {
  const imports = useImports(labId, projectId);
  const [step, setStep] = useState<"source" | "map" | "check" | "done">("source");
  const [csv, setCsv] = useState("");
  const [preview, setPreview] = useState<ImportPreview>();
  const [map, setMap] = useState({ code: "", group: "", cohort: "", status: "" });
  const [picked, setPicked] = useState<string[]>([]);
  const [result, setResult] = useState<ImportResult>();
  const [error, setError] = useState<string>();

  async function readFile(e: ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (f) setCsv(await f.text());
  }

  async function next() {
    setError(undefined);
    try {
      const p = await imports.preview.mutateAsync(csv);
      const free = p.headers.filter((h) => !p.blocked_headers.includes(h));
      const code = guess(free, /code|id|participant/i);
      const group = guess(free, /group|language|lang/i);
      setPreview(p);
      setMap({
        code,
        group,
        cohort: guess(free, /cohort|site/i),
        status: guess(free, /enrol|status/i),
      });
      setPicked(
        free.filter((h) => ![code, group].includes(h) && !/cohort|site|enrol|status/i.test(h)),
      );
      setStep("map");
    } catch (e) {
      setError(formErrors(e, ["csv"]).fields.csv ?? formErrors(e, []).form);
    }
  }

  const mapping = (): ImportMapping => ({
    code: map.code,
    ...(map.group && { group: map.group }),
    ...(map.cohort && { cohort: map.cohort }),
    ...(map.status && { enrolment_status: map.status }),
    components: picked.map((column) => ({ column })),
  });

  async function check(dry: boolean) {
    setError(undefined);
    try {
      const r = await imports.run.mutateAsync({ csv, mapping: mapping(), dry_run: dry });
      setResult(r);
      setStep(dry ? "check" : "done");
    } catch (e) {
      const f = formErrors(e, ["mapping", "csv"]);
      setError(f.fields.mapping ?? f.fields.csv ?? f.form);
    }
  }

  const free = preview?.headers.filter((h) => !preview.blocked_headers.includes(h)) ?? [];
  const select = (label: string, key: keyof typeof map, optional = true) => (
    <label className="grid gap-1 text-sm">
      <span className="font-medium">
        {label}
        {!optional && " *"}
      </span>
      <NativeSelect value={map[key]} onChange={(e) => setMap({ ...map, [key]: e.target.value })}>
        <option value="">{optional ? "Not in the sheet" : "Choose a column…"}</option>
        {free.map((h) => (
          <option key={h}>{h}</option>
        ))}
      </NativeSelect>
    </label>
  );

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogTitle>Import participants</DialogTitle>
        <DialogDescription>
          Bring in the sheet you already use. Only codes, groups, statuses and links are read.{" "}
          {CODES_ONLY}
        </DialogDescription>

        {step === "source" && (
          <div className="grid gap-3">
            <p className="text-sm text-muted-foreground">
              In Google Sheets, select your table, copy it, and paste it here. Or upload a CSV file.
              One row per participant.
            </p>
            <Textarea
              aria-label="Sheet contents"
              rows={8}
              value={csv}
              onChange={(e) => setCsv(e.target.value)}
              placeholder={"Code\tGroup\tTranscript\nP-001\tPunjabi\thttps://docs.google.com/…"}
            />
            <input
              type="file"
              accept=".csv,text/csv,.tsv,text/plain"
              onChange={(e) => void readFile(e)}
              aria-label="Upload a CSV file"
            />
            <FormError message={error} />
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={onClose}>
                Cancel
              </Button>
              <Button
                disabled={!csv.trim() || imports.preview.isPending}
                onClick={() => void next()}
              >
                Next: match columns
              </Button>
            </div>
          </div>
        )}

        {step === "map" && preview && (
          <div className="grid gap-3">
            {preview.blocked_headers.length > 0 && (
              <p
                role="alert"
                className="rounded-md border border-warning bg-warning/15 p-3 text-sm"
              >
                {preview.blocked_headers.length === 1 ? "A column looks" : "Some columns look"} like
                a name or contact detail ({preview.blocked_headers.join(", ")}). They cannot be
                imported and are left out.
              </p>
            )}
            <div className="grid gap-3 sm:grid-cols-2">
              {select("Participant code", "code", false)}
              {select("Group (for example home language)", "group")}
              {select("Cohort or site", "cohort")}
              {select("Enrolment status", "status")}
            </div>
            <fieldset className="grid gap-1">
              <legend className="text-sm font-medium">Data columns</legend>
              {free
                .filter((h) => ![map.code, map.group, map.cohort, map.status].includes(h))
                .map((h) => (
                  <label key={h} className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={picked.includes(h)}
                      onChange={(e) =>
                        setPicked(e.target.checked ? [...picked, h] : picked.filter((x) => x !== h))
                      }
                    />
                    {h}
                    {preview.link_columns.includes(h) && (
                      <span className="text-xs text-muted-foreground">(links found)</span>
                    )}
                  </label>
                ))}
            </fieldset>
            <div className="overflow-x-auto rounded-md border text-xs">
              <table className="w-full">
                <thead>
                  <tr>
                    {preview.headers.map((h) => (
                      <th key={h} className="px-2 py-1 text-left font-medium">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {preview.rows.slice(0, 5).map((r, i) => (
                    <tr key={i}>
                      {preview.headers.map((_, j) => (
                        <td key={j} className="max-w-40 truncate px-2 py-1">
                          {r[j]}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <FormError message={error} />
            <div className="flex justify-between gap-2">
              <Button variant="outline" onClick={() => setStep("source")}>
                Back
              </Button>
              <Button
                disabled={!map.code || imports.run.isPending}
                onClick={() => void check(true)}
              >
                Check before saving
              </Button>
            </div>
          </div>
        )}

        {(step === "check" || step === "done") && result && (
          <div className="grid gap-3">
            <p role="status" className="text-sm font-medium">
              {step === "check" ? "Nothing is saved yet. If you confirm:" : "Imported."}
            </p>
            <ul className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {(
                [
                  ["Created", result.created],
                  ["Updated", result.updated],
                  ["Skipped", result.skipped],
                  ["Links found", result.links],
                ] as const
              ).map(([l, n]) => (
                <li key={l} className="rounded-lg border px-3 py-2">
                  <span className="block text-xl font-semibold">{n}</span>
                  <span className="text-xs text-muted-foreground">{l}</span>
                </li>
              ))}
            </ul>
            {result.attention.length > 0 && (
              <div>
                <h3 className="text-sm font-medium">Needs attention ({result.attention_total})</h3>
                <ul className="mt-1 max-h-40 overflow-y-auto text-sm">
                  {result.attention.map((a, i) => (
                    <li key={i}>
                      Row {a.row}: {a.message}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <FormError message={error} />
            <div className="flex justify-between gap-2">
              {step === "check" ? (
                <>
                  <Button variant="outline" onClick={() => setStep("map")}>
                    Back
                  </Button>
                  <Button disabled={imports.run.isPending} onClick={() => void check(false)}>
                    Confirm import
                  </Button>
                </>
              ) : (
                <Button className="ml-auto" onClick={onClose}>
                  Done
                </Button>
              )}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

export function ImportHistory({ labId, projectId, onClose }: Props) {
  const { history, undo } = useImports(labId, projectId);
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogTitle>Import history</DialogTitle>
        <DialogDescription>
          Undo removes what the most recent import added. Older imports cannot be undone.
        </DialogDescription>
        {(history.data ?? []).length === 0 && (
          <p className="text-sm text-muted-foreground">No imports yet.</p>
        )}
        <ul className="grid gap-2">
          {(history.data ?? []).map((r) => (
            <li key={r.id} className="flex items-center justify-between gap-2 text-sm">
              <span className={cn(r.undone_at && "text-muted-foreground line-through")}>
                {r.summary.created ?? 0} created, {r.summary.updated ?? 0} updated ·{" "}
                <RelativeTime value={r.created_at} />
                {r.undone_at && " (undone)"}
              </span>
              {r.can_undo && (
                <Button
                  size="sm"
                  variant="outline"
                  disabled={undo.isPending}
                  onClick={() =>
                    undo.mutate(r.id, {
                      onSuccess: () => toast.success("Import undone"),
                      onError: () => toast.error("Could not undo that import."),
                    })
                  }
                >
                  Undo
                </Button>
              )}
            </li>
          ))}
        </ul>
      </DialogContent>
    </Dialog>
  );
}

/** Match Drive files to cells by their name. Paste "name, link" lines; review, then attach. */
export function MatchFilesDialog({ labId, projectId, onClose }: Props) {
  const imports = useImports(labId, projectId, false);
  const [text, setText] = useState("");
  const [pattern, setPattern] = useState("P-{number}_{component}");
  const [matches, setMatches] = useState<FileMatch[]>();
  const [accepted, setAccepted] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string>();

  const parse = () =>
    text
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean)
      .map((line) => {
        const m = line.match(/^(.*?)[\s,;\t]+(https?:\/\/\S+)$/);
        return m ? { name: m[1]!.trim(), url: m[2]! } : null;
      })
      .filter((x): x is { name: string; url: string } => !!x);

  async function find() {
    setError(undefined);
    try {
      const r = await imports.match.mutateAsync({ files: parse(), pattern });
      setMatches(r.matches);
      setAccepted(new Set(r.matches.filter((m) => m.confidence === "high").map((m) => m.url)));
    } catch (e) {
      setError(formErrors(e, ["pattern", "files"]).fields.pattern ?? formErrors(e, []).form);
    }
  }
  async function attach() {
    const items = (matches ?? [])
      .filter((m) => accepted.has(m.url) && m.participant && m.component)
      .map((m) => ({ participant: m.participant!, component: m.component!, url: m.url }));
    try {
      const r = await imports.attach.mutateAsync(items);
      toast.success(`Attached ${r.attached} link${r.attached === 1 ? "" : "s"}`);
      onClose();
    } catch (e) {
      setError(formErrors(e, []).form);
    }
  }
  const tone = { high: "High", medium: "Medium", low: "Low", none: "No match" } as const;

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogTitle>Match files to participants</DialogTitle>
        <DialogDescription>
          Paste one file per line as the file name, then its link. Files are matched by their name
          to a participant and a data column. Unmatched files stay here so none are lost.
        </DialogDescription>
        {!matches ? (
          <div className="grid gap-3">
            <label className="grid gap-1 text-sm">
              <span className="font-medium">Naming pattern</span>
              <input
                className="h-9 rounded-md border border-input bg-background px-3 text-sm"
                value={pattern}
                onChange={(e) => setPattern(e.target.value)}
              />
              <span className="text-xs text-muted-foreground">
                Use {"{number}"} for the participant number and {"{component}"} for the column.
              </span>
            </label>
            <Textarea
              aria-label="Files and links"
              rows={8}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={"P-017_Transcript.docx  https://docs.google.com/…"}
            />
            <FormError message={error} />
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={onClose}>
                Cancel
              </Button>
              <Button
                disabled={!parse().length || imports.match.isPending}
                onClick={() => void find()}
              >
                Find matches
              </Button>
            </div>
          </div>
        ) : (
          <div className="grid gap-3">
            <ul className="grid gap-1 text-sm">
              {matches.map((m) => (
                <li key={m.url} className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    aria-label={`Attach ${m.name}`}
                    disabled={!m.participant || !m.component}
                    checked={accepted.has(m.url)}
                    onChange={(e) => {
                      const next = new Set(accepted);
                      if (e.target.checked) next.add(m.url);
                      else next.delete(m.url);
                      setAccepted(next);
                    }}
                  />
                  <span className="min-w-0 flex-1 truncate">{m.name}</span>
                  <span className="text-xs text-muted-foreground">
                    {m.participant_code ?? "?"} · {m.component_name ?? "?"}
                  </span>
                  <span className="w-16 text-right text-xs">{tone[m.confidence]}</span>
                </li>
              ))}
            </ul>
            <FormError message={error} />
            <div className="flex justify-between gap-2">
              <Button variant="outline" onClick={() => setMatches(undefined)}>
                Back
              </Button>
              <Button
                disabled={!accepted.size || imports.attach.isPending}
                onClick={() => void attach()}
              >
                Attach {accepted.size} selected
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

export function LinkHealthDialog({ labId, projectId, onClose }: Props) {
  const { health, check } = useLinkHealth(labId, projectId);
  const registry = useRegistry(labId, projectId);
  const h = health.data;
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogTitle>Link health</DialogTitle>
        <DialogDescription>
          Checks the title, last edit and reachability of each linked Google file. It never changes
          a status or any sharing.
        </DialogDescription>
        {h && (
          <p className="text-sm">
            {h.counts.ok} fine, {h.counts.unchecked} not checked yet, {h.counts.problems} with
            problems, {h.counts.changed_since_verified} edited since you confirmed them.
          </p>
        )}
        <Button
          variant="outline"
          disabled={check.isPending}
          onClick={() =>
            check.mutate(undefined, {
              onSuccess: (r) =>
                toast.success(`Checked ${r.checked} file${r.checked === 1 ? "" : "s"}`),
              onError: () => toast.error("Connect Google Drive in Integrations first."),
            })
          }
        >
          {check.isPending ? "Checking…" : "Check links now"}
        </Button>
        {(h?.problems ?? []).length > 0 && (
          <section aria-label="Problem links">
            <h3 className="text-sm font-medium">Problem links</h3>
            <ul className="mt-1 grid gap-1 text-sm">
              {h!.problems.map((p) => (
                <li key={p.file} className="flex items-center gap-2">
                  <span className="flex-1">
                    {p.participant} · {p.component} · {p.state.replace("_", " ")}
                  </span>
                  <Button asChild size="sm" variant="ghost">
                    <a href={p.url} target="_blank" rel="noopener noreferrer">
                      Open
                    </a>
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    aria-label={`Remove link for ${p.participant} ${p.component}`}
                    onClick={() => registry.removeFile.mutate(p.file)}
                  >
                    Remove
                  </Button>
                </li>
              ))}
            </ul>
          </section>
        )}
        {(h?.changed ?? []).length > 0 && (
          <section aria-label="Edited since confirmed">
            <h3 className="text-sm font-medium">Edited since you confirmed them complete</h3>
            <ul className="mt-1 text-sm">
              {h!.changed.map((c) => (
                <li key={c.cell}>
                  {c.participant} · {c.component}
                </li>
              ))}
            </ul>
          </section>
        )}
        {h && h.counts.problems === 0 && h.counts.changed_since_verified === 0 && (
          <p className="text-sm text-muted-foreground">No problem links.</p>
        )}
      </DialogContent>
    </Dialog>
  );
}
