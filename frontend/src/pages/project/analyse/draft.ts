import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useAttachments } from "@/hooks/projects";
import { root } from "@/hooks/research";
import { api } from "@/lib/api";
import type { Analysis } from "@/lib/api-types";
import { cleanName, errorText, IN_PROGRESS_MARK, SAVED_MARK } from "@/pages/project/analyse/save";

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
}

const DELAY = 1500;

/**
 * Keeps one "in progress" report for a statistics tab in the project's Analysis list while the
 * user works: made when a test is chosen, updated as the options change. The report is later
 * finished in place by the save of the first result (ResultCard passes `draftId` on).
 */
export function useDraftReport(a: Args) {
  const { uploadFile } = useAttachments(a.labId, a.projectId);
  const qc = useQueryClient();
  const [draftId, setDraftId] = useState<string>();
  const [state, setState] = useState<DraftState>("idle");
  const [error, setError] = useState<string>();
  const codeId = useRef<string>();
  const draftRef = useRef<string>();
  const chain = useRef<Promise<unknown>>(Promise.resolve());
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
            description: `In progress: ${c.testLabel} on ${c.inputName}\n\nInput file: ${c.inputName}\n\n${SAVED_MARK}\n\n${IN_PROGRESS_MARK}`,
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
