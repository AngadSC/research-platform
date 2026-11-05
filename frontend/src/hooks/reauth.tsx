import { useState } from "react";
import { ReauthDialog, type Ask } from "@/components/auth/ReauthDialog";
import { ReauthCancelled, reauthFlows, type ReauthFlows } from "@/hooks/auth";

/**
 * `run(fn)` calls fn; if allauth answers 401 with a reauthentication flow it asks for the password
 * (and TOTP code), then retries fn once. `ensure(flows)` asks up front, for actions that leave the
 * SPA (connecting Google is a full-page redirect, so a 401 could not be retried).
 * Render `dialog` somewhere on the page.
 */
export function useReauth() {
  const [ask, setAsk] = useState<Ask | null>(null);

  const ensure = (flows: ReauthFlows) =>
    new Promise<void>((resolve, reject) => {
      const end = (fn: () => void) => () => {
        setAsk(null);
        fn();
      };
      setAsk({
        flows,
        done: end(resolve),
        cancel: end(() => reject(new ReauthCancelled())),
      });
    });

  async function run<T>(fn: () => Promise<T>): Promise<T> {
    try {
      return await fn();
    } catch (e) {
      const flows = reauthFlows(e);
      if (!flows) throw e;
      await ensure(flows);
      return fn();
    }
  }

  return { run, ensure, dialog: <ReauthDialog ask={ask} /> };
}
