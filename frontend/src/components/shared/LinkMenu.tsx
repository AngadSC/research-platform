import { ChevronDown, Link2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { ProviderIcon } from "@/components/shared/ExternalLinkItem";
import { FormError } from "@/components/shared/FormError";
import { FormField } from "@/components/shared/FormField";
import { RelativeTime } from "@/components/shared/RelativeTime";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import {
  fetchPickerToken,
  useCreateExternalLink,
  useItemSearch,
  useProviders,
} from "@/hooks/integrations";
import { useDebounced } from "@/hooks/useDebounced";
import { ApiError } from "@/lib/api";
import type { ExternalLinkInput, IntegrationProvider } from "@/lib/api-types";
import { pickDriveFile } from "@/lib/drive";
import { formErrors } from "@/lib/forms";
import {
  checkPastedUrl,
  isUsable,
  linkMethods,
  offering,
  sharingNote,
  type LinkKind,
} from "@/lib/integrations";

export type LinkTarget = Exclude<LinkKind, "project">;
export interface LinkTargetRef {
  field: LinkTarget;
  id: string;
}
type LinkInput = Partial<ExternalLinkInput>;

const NOTES: Record<string, string> = {
  copied: "The file's checksum was added to this record.",
  kept: "This record already has a different version, so it was left as it is. Add a new version to record this one.",
};

const message = (e: unknown) => formErrors(e, []).form ?? "Something went wrong.";
// A failed Picker load is a plain Error with its own text; API errors go through formErrors.
const failure = (e: unknown) => (e instanceof ApiError ? message(e) : (e as Error).message);

/** Creates the link and reports the outcome; throws the API error for the caller to show. */
function useLinker(labId: string, projectId: string, target?: LinkTargetRef) {
  const create = useCreateExternalLink(labId, projectId);
  return async (p: IntegrationProvider, input: LinkInput) => {
    const made = await create.mutateAsync({
      provider: p.name,
      ...input,
      ...(target ? { [target.field]: target.id } : {}),
    });
    const note = NOTES[made.version_note ?? ""];
    toast.success(`Linked ${made.title}`, note ? { description: note } : undefined);
  };
}

/** "Link from...": every usable provider that can link to this kind of record. With no
 * `target` the link hangs on the project (the Files tab). Hidden when no provider offers the
 * kind at all. */
export function LinkMenu({
  labId,
  projectId,
  target,
  only,
}: {
  labId: string;
  projectId: string;
  target?: LinkTargetRef;
  /** Offer only these providers (by name), for tabs about one kind of service. */
  only?: string[];
}) {
  const kind: LinkKind = target?.field ?? "project";
  const providers = useProviders(labId).data;
  const [active, setActive] = useState<IntegrationProvider | null>(null);
  const [busy, setBusy] = useState(false);
  const link = useLinker(labId, projectId, target);

  const offered = offering(providers, kind).filter((p) => !only || only.includes(p.name));
  if (!offered.length) return null;
  const usable = offered.filter(isUsable);

  // The Picker is Google's own window, so it needs no dialog of ours.
  const pick = async (p: IntegrationProvider) => {
    setBusy(true);
    try {
      const { access_token: token } = await fetchPickerToken(labId);
      const file = await pickDriveFile({
        apiKey: p.public_config.api_key!,
        appId: p.public_config.app_id!,
        token,
      });
      if (file) await link(p, { external_id: file.id });
    } catch (e) {
      toast.error(failure(e));
    } finally {
      setBusy(false);
    }
  };

  const choose = (p: IntegrationProvider) => {
    const methods = linkMethods(p);
    if (methods.length === 1 && methods[0] === "picker") void pick(p);
    else setActive(p);
  };

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" disabled={busy}>
            <Link2 aria-hidden /> Link from&hellip; <ChevronDown aria-hidden />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          {usable.length ? (
            usable.map((p) => (
              <DropdownMenuItem key={p.name} onSelect={() => choose(p)}>
                <ProviderIcon name={p.icon} /> {p.label}
              </DropdownMenuItem>
            ))
          ) : (
            <DropdownMenuLabel className="max-w-56 font-normal text-muted-foreground">
              Connect a service under Settings &gt; Integrations first.
            </DropdownMenuLabel>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
      <Dialog open={!!active} onOpenChange={(o) => !o && setActive(null)}>
        <DialogContent>
          {active && (
            <LinkBody
              labId={labId}
              projectId={projectId}
              target={target}
              p={active}
              onPick={(p) => {
                setActive(null);
                void pick(p);
              }}
              onClose={() => setActive(null)}
            />
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}

function LinkBody({
  labId,
  projectId,
  target,
  p,
  onPick,
  onClose,
}: {
  labId: string;
  projectId: string;
  target?: LinkTargetRef;
  p: IntegrationProvider;
  onPick: (p: IntegrationProvider) => void;
  onClose: () => void;
}) {
  const methods = linkMethods(p);
  const link = useLinker(labId, projectId, target);
  const [error, setError] = useState<string>();
  const go = async (input: LinkInput) => {
    setError(undefined);
    try {
      await link(p, input);
      onClose();
    } catch (e) {
      setError(message(e));
    }
  };
  return (
    <div className="grid gap-4">
      <DialogTitle className="text-base font-semibold">Link from {p.label}</DialogTitle>
      <DialogDescription className="text-sm text-muted-foreground">
        {sharingNote(p.name, p.label)}
      </DialogDescription>
      <FormError message={error} />
      {methods.includes("picker") && (
        <Button variant="outline" onClick={() => onPick(p)}>
          Choose in {p.label}
        </Button>
      )}
      {methods.includes("search") && (
        <SearchLinker
          labId={labId}
          projectId={projectId}
          kind={target?.field ?? "project"}
          p={p}
          go={go}
        />
      )}
      {methods.includes("paste_url") && <PasteLinker p={p} go={go} />}
    </div>
  );
}

function SearchLinker({
  labId,
  projectId,
  kind,
  p,
  go,
}: {
  labId: string;
  projectId: string;
  kind: LinkKind;
  p: IntegrationProvider;
  go: (input: LinkInput) => Promise<void>;
}) {
  const [text, setText] = useState("");
  const q = useDebounced(text.trim());
  const search = useItemSearch(labId, projectId, p.name, kind, q, true);
  const waiting = search.isFetching || q !== text.trim();
  const results = search.data ?? [];
  return (
    <section aria-label={`Search ${p.label}`} className="grid gap-2">
      <FormField label={`Search ${p.label}`} hint="Leave empty to see recent items.">
        {(props) => (
          <Input {...props} type="search" value={text} onChange={(e) => setText(e.target.value)} />
        )}
      </FormField>
      {search.isError && <FormError message={message(search.error)} />}
      {waiting && (
        <p className="text-xs text-muted-foreground" aria-live="polite">
          Searching...
        </p>
      )}
      {!waiting && !search.isError && results.length === 0 && (
        <p className="text-xs text-muted-foreground">No matches.</p>
      )}
      <ul className="grid max-h-60 divide-y overflow-y-auto rounded-lg border empty:hidden">
        {results.map((r) => (
          <li key={r.id}>
            <button
              type="button"
              className="grid w-full gap-0.5 px-3 py-2 text-left text-sm hover:bg-accent focus-visible:bg-accent focus-visible:outline-none"
              onClick={() => void go({ external_id: r.id })}
            >
              <span className="truncate font-medium">{r.title}</span>
              <span className="truncate text-xs text-muted-foreground">
                {r.subtitle}
                {r.modified && (
                  <>
                    {r.subtitle && " | "}Modified <RelativeTime value={r.modified} />
                  </>
                )}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function PasteLinker({
  p,
  go,
}: {
  p: IntegrationProvider;
  go: (input: LinkInput) => Promise<void>;
}) {
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [errors, setErrors] = useState<{ url?: string; title?: string }>({});
  const needsTitle = p.auth_type === "link_only";
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const next = {
      url: checkPastedUrl(url, p) || undefined,
      title: needsTitle && !title.trim() ? "Enter a title for this link." : undefined,
    };
    setErrors(next);
    if (next.url || next.title) return;
    void go({ url: url.trim(), ...(needsTitle ? { title: title.trim() } : {}) });
  };
  return (
    <form onSubmit={submit} noValidate className="grid gap-3">
      <FormField label={`${p.label} link`} error={errors.url}>
        {(props) => (
          <Input
            {...props}
            type="url"
            placeholder="https://"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
        )}
      </FormField>
      {needsTitle && (
        <FormField label="Title" error={errors.title}>
          {(props) => (
            <Input
              {...props}
              maxLength={500}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          )}
        </FormField>
      )}
      <div className="flex justify-end">
        <Button type="submit">Link</Button>
      </div>
    </form>
  );
}
