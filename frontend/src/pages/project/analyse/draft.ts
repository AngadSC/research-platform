import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useAttachments } from "@/hooks/projects";
import { useMe } from "@/hooks/workspace";
import { root } from "@/hooks/research";
import { api } from "@/lib/api";
import type { Analysis } from "@/lib/api-types";
import {
  cleanName,
  errorText,
  IN_PROGRESS_MARK,
  isInProgress,
  SAVED_MARK,
} from "@/pages/project/analyse/save";

export type DraftState = "idle" | "saving" | "saved" | "error";

interface Args {
  labId: string;
  projectId: string;
  /** Off for data that identifies (or may identify) participants, and when the user can't save. */
  enabled: boolean;
  title: string;
  testLabel: string;
  inputName: string;
  datasetId?: string;
  options: Record<string, unknown>;
  /** An option was changed since the test was picked. Until then nothing new is made. */
  changed: boolean;
}

const DELAY = 1500;

const summary = (testLabel: string, inputName: string) =>
  `In progress: ${testLabel} on ${inputName}\n`;

/** An in-progress report from an earlier visit on the same input and test, to carry on with. */
async function findDraft(c: Args, me?: string): Promise<Analysis | undefined> {
  if (!me) return undefined;
  const list = await api<Analysis[]>(`/api/labs/${c.labId}/projects/${c.projectId}/analyses/`);
  return list.find(
    (a) =>
      a.ran_by?.id === me &&
      isInProgress(a.description) &&
      a.description.startsWith(summary(c.testLabel, c.inputName)) &&
      a.datasets[0]?.id === c.datasetId,
  );
}

/**
 * Keeps one "in progress" report for a statistics tab in the project's Analysis list while the
 * user works. When a test is chosen, an in-progress report from an earlier visit on the same input
 * and test is picked up again; otherwise one is made only once an option is changed, then updated
 * as the options change. The first result's save finishes it in place (ResultCard passes `draftId`
 * on); a result run before any report exists is saved as a new one.
 */
export function useDraftReport(a: Args) {
  const { uploadFile } = useAttachments(a.labId, a.projectId);
  const me = useMe().data?.id;
  const meId = useRef(me);
  useEffect(() => {
    meId.current = me;
  });
  const qc = useQueryClient();
  const [draftId, setDraftId] = useState<string>();
  const [state, setState] = useState<DraftState>("idle");
  const [error, setError] = useState<string>();
  const codeId = useRef<string>();
  const draftRef = useRef<string>();
  const chain = useRef<Promise<unknown>>(Promise.resolve());
  const lookedFor = useRef<string>();
  const key = JSON.stringify([a.title, a.testLabel, a.inputName, a.datasetId, a.options]);
  const latest = useRef(a);
  useEffect(() => {
    latest.current = a;
  });
  const upload = uploadFile.mutateAsync;

  useEffect(() => {
    if (!a.enabled || !a.testLabel) return;
    const timer = setTimeout(() => {
      // one request at a time, so the first save has an id before the next one goes out
      chain.current = chain.current.then(async () => {
        const c = latest.current;
        if (!c.enabled) return; // the report was finished while this save waited
        const which = JSON.stringify([c.testLabel, c.inputName, c.datasetId]);
        if (!draftRef.current && lookedFor.current !== which) {
          lookedFor.current = which;
          // best effort: if the list can't be read, a new report is made as before
          const found = await findDraft(c, meId.current).catch(() => undefined);
          if (found) {
            draftRef.current = found.id;
            codeId.current = found.code_attachment?.id;
            setDraftId(found.id);
            setState("saved");
          }
        }
        if (!c.changed) return; // nothing new to keep
        const base = `/api/labs/${c.labId}/projects/${c.projectId}/analyses/`;
        setState("saving");
        try {
          if (!codeId.current) {
            const text = [
              `# In progress: ${c.title}`,
              `# Test: ${c.testLabel}`,
              `# Input file: ${c.inputName}`,
              `# Options: ${JSON.stringify(c.options)}`,
              "# The full Python code is added when the analysis is run and saved.",
              "",
            ].join("\n");
            const att = await upload({
              file: new File([text], `${cleanName(c.title)} (in progress).py`, {
                type: "text/x-python",
              }),
              participant: false,
            });
            codeId.current = att.id;
          }
          const body = {
            title: `${c.title} (in progress)`,
            description: `${summary(c.testLabel, c.inputName)}\nInput file: ${c.inputName}\n\n${SAVED_MARK}\n\n${IN_PROGRESS_MARK}`,
            code_attachment: codeId.current,
            datasets: c.datasetId ? [c.datasetId] : [],
            ran_at: new Date().toISOString(),
          };
          const id = draftRef.current;
          const out = id
            ? await api<Analysis>(`/api/labs/${c.labId}/analyses/${id}/`, {
                method: "PATCH",
                body,
              })
            : await api<Analysis>(base, { method: "POST", body });
          draftRef.current = out.id;
          setDraftId(out.id);
          setError(undefined);
          setState("saved");
          await qc.invalidateQueries({ queryKey: root(c.labId) });
        } catch (e) {
          setError(errorText(e));
          setState("error");
        }
      });
    }, DELAY);
    return () => clearTimeout(timer);
    // `key` covers the text inputs; the rest only switch it on or off
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, a.enabled, qc, upload]);

  return { draftId, state, error };
}
