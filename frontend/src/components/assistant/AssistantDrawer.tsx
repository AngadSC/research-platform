import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useMatches } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { Ban, Check, Loader2, Plus, Sparkles, Trash2, X } from "lucide-react";
import { ApprovalDialog } from "@/components/assistant/ApprovalDialog";
import { FormError } from "@/components/shared/FormError";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import {
  conversationKey,
  useAssistantConfig,
  useConversation,
  useConversations,
  useCreateConversation,
  useDeleteConversation,
  type AssistantConfig,
  type Provider,
  type TimelineItem,
} from "@/hooks/assistant";
import { useProject } from "@/hooks/projects";
import { useLabs } from "@/hooks/workspace";
import {
  ASSISTANT_PREFILL,
  estimateCost,
  formatCost,
  streamPost,
  tokensIn,
  type ChatEvent,
} from "@/lib/assistant";
import { Markdown } from "@/lib/markdown";
import { NativeSelect } from "@/pages/admin/common";

interface Live {
  user: string;
  text: string;
  tools: { label: string; status: string }[];
  notice: ChatEvent | null;
  error: { message: string; retryable: boolean } | null;
}

const humanize = (name: string) => name.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());

function reduce(live: Live, e: ChatEvent): Live {
  switch (e.type) {
    case "text":
      return { ...live, text: live.text + String(e.delta ?? "") };
    case "retry":
      return { ...live, text: "" };
    case "tool_start":
      return {
        ...live,
        tools: [...live.tools, { label: humanize(String(e.name)), status: "running" }],
      };
    case "tool": {
      const label = String(e.title ?? humanize(String(e.name)));
      const tools = live.tools.map((t) => ({ ...t }));
      const open = tools.find((t) => t.status === "running");
      if (open) Object.assign(open, { label, status: String(e.status) });
      else tools.push({ label, status: String(e.status) });
      return { ...live, tools };
    }
    case "assistant":
      return { ...live, text: live.text ? live.text + "\n\n" : "" };
    case "notice":
      return { ...live, notice: e };
    case "error":
      return {
        ...live,
        error: { message: String(e.message), retryable: Boolean(e.retryable) },
      };
    default:
      return live;
  }
}

function ToolStatus({ status }: { status: string }) {
  if (status === "running") return <Loader2 className="size-3.5 animate-spin" aria-hidden />;
  if (status === "done") return <Check className="size-3.5 text-success" aria-hidden />;
  if (status === "declined") return <Ban className="size-3.5 text-muted-foreground" aria-hidden />;
  if (status === "pending") return <span className="text-xs">waiting for you</span>;
  return <X className="size-3.5 text-destructive" aria-hidden />;
}

const STATUS_WORD: Record<string, string> = {
  running: "working",
  done: "done",
  error: "failed",
  declined: "declined",
  pending: "waiting for approval",
};

function ToolRow({ label, status }: { label: string; status: string }) {
  return (
    <li className="flex items-center gap-2 text-xs text-muted-foreground">
      <ToolStatus status={status} />
      <span>
        {label} <span className="sr-only">({STATUS_WORD[status] ?? status})</span>
      </span>
    </li>
  );
}

function Notice({
  code,
  refusal,
  message,
}: {
  code?: string;
  refusal?: unknown;
  message?: string;
}) {
  const r = refusal as { category?: string | null; explanation?: string | null } | null;
  const text =
    code === "refusal"
      ? `The model declined to answer${r?.category ? ` (${r.category})` : ""}.${
          r?.explanation ? ` ${r.explanation}` : ""
        } Try rephrasing.`
      : (message ?? "");
  return (
    <p role="status" className="rounded-md bg-muted px-3 py-2 text-sm">
      {text}
    </p>
  );
}

function UsageLine({ item, config }: { item: TimelineItem; config?: AssistantConfig }) {
  const u = item.usage ?? {};
  const price = config?.providers.flatMap((p) => p.models).find((m) => m.id === item.model);
  const cost = estimateCost(u, price);
  return (
    <p className="mt-1 text-xs text-muted-foreground">
      {item.model} · {tokensIn(u).toLocaleString()} tokens in ·{" "}
      {(u.output_tokens ?? 0).toLocaleString()} out{cost !== null ? ` · ${formatCost(cost)}` : ""}
      {item.fallback ? " · answered by a fallback model after a refusal" : ""}
    </p>
  );
}

function Item({ item, config }: { item: TimelineItem; config?: AssistantConfig }) {
  if (item.kind === "user")
    return (
      <div className="ml-auto max-w-[85%] rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground">
        {item.text}
      </div>
    );
  if (item.kind === "tool")
    return <ToolRow label={item.title ?? item.name ?? "Tool"} status={item.status ?? "done"} />;
  if (item.kind === "usage")
    return (
      <p className="text-xs text-muted-foreground">
        {tokensIn(item.usage ?? {}).toLocaleString()} tokens in ·{" "}
        {(item.usage?.output_tokens ?? 0).toLocaleString()} out
      </p>
    );
  return (
    <div className="grid gap-1">
      {item.text && (
        <div className="max-w-[95%] text-sm [&_p]:mb-1">
          <Markdown text={item.text} ownLinksOnly />
        </div>
      )}
      {item.refusal && <Notice code="refusal" refusal={item.refusal} />}
      {item.truncated && (
        <Notice message="The answer was cut off because it hit the length limit." />
      )}
      <UsageLine item={item} config={config} />
    </div>
  );
}

export function Setup({
  config,
  onOpenSettings,
}: {
  config: AssistantConfig;
  /** The drawer closes itself so the Settings page behind it can be seen. */
  onOpenSettings?: () => void;
}) {
  if (!config.can_use)
    return (
      <p role="alert" className="rounded-md border p-3 text-sm">
        {config.ai_policy === "off"
          ? "AI assistants are turned off for this lab."
          : "This lab allows AI apps over MCP only; the in-app assistant is turned off."}{" "}
        A PI or lab admin can change this in Lab details, on the AI tab.
      </p>
    );
  return (
    <p className="rounded-md border p-3 text-sm">
      Add your own API key to use the assistant. It is billed to your account with the provider.{" "}
      <Link
        className="font-medium underline underline-offset-4"
        to="/settings#ai"
        onClick={onOpenSettings}
      >
        Add your key under Assistant API keys in Settings
      </Link>
    </p>
  );
}

function AssistantPanel({
  labId,
  projectId,
  initialText = "",
  onClose,
}: {
  labId: string;
  projectId?: string;
  initialText?: string;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const config = useAssistantConfig(labId, true);
  const convs = useConversations(labId, true);
  const lab = useLabs().data?.find((l) => l.id === labId);
  const project = useProject(labId, projectId).data;
  const [convId, setConvId] = useState<string | null>(null);
  const conv = useConversation(labId, convId);
  const create = useCreateConversation(labId);
  const remove = useDeleteConversation(labId);
  const [provider, setProvider] = useState<Provider | null>(null);
  const [model, setModel] = useState("");
  const [text, setText] = useState(initialText);
  const [live, setLive] = useState<Live | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [dismissedFor, setDismissedFor] = useState("");
  const abort = useRef<AbortController | null>(null);
  const [lastSent, setLastSent] = useState("");
  const end = useRef<HTMLDivElement>(null);

  const cfg = config.data;
  const usable = cfg?.can_use ? cfg.providers.filter((p) => p.has_key) : [];
  const chosen = usable.find((p) => p.provider === provider) ?? usable[0];
  const pending = useMemo(() => conv.data?.pending ?? [], [conv.data]);
  const pendingKey = pending.map((p) => p.id).join(",");
  const dismissed = dismissedFor === pendingKey; // a new set of waiting actions asks again

  useEffect(() => () => abort.current?.abort(), []); // closing the drawer stops the answer
  useEffect(() => {
    end.current?.scrollIntoView?.({ block: "end" });
  }, [conv.data?.items.length, live?.text, live?.tools.length]);

  async function run(path: string, body: unknown, id: string, user: string) {
    const ctrl = new AbortController();
    abort.current = ctrl;
    setLive({ user, text: "", tools: [], notice: null, error: null });
    setStreaming(true);
    try {
      await streamPost(path, body, (e) => setLive((l) => (l ? reduce(l, e) : l)), ctrl.signal);
    } catch (e) {
      const message = e instanceof Error ? e.message : "Something went wrong.";
      setLive((l) => (l ? { ...l, error: { message, retryable: false } } : l));
    } finally {
      setStreaming(false);
      await qc.invalidateQueries({ queryKey: conversationKey(labId, id) });
      void qc.invalidateQueries({ queryKey: ["assistant", labId, "conversations"] });
      // the saved conversation now shows the text and tool rows; keep only what is not saved
      setLive((l) => (l ? { ...l, user: "", text: "", tools: [] } : l));
    }
  }

  async function send(message: string) {
    const msg = message.trim();
    if (!msg || streaming || !chosen) return;
    setText("");
    setLastSent(msg);
    let id = convId;
    if (!id) {
      try {
        const c = await create.mutateAsync({
          provider: chosen.provider,
          model: model || chosen.default_model,
          ...(projectId ? { project: projectId } : {}),
        });
        id = c.id;
        setConvId(id);
      } catch (e) {
        const message = e instanceof Error ? e.message : "Could not start a chat.";
        setLive({
          user: "",
          text: "",
          tools: [],
          notice: null,
          error: { message, retryable: false },
        });
        return;
      }
    }
    await run(`/api/labs/${labId}/assistant/conversations/${id}/messages/`, { text: msg }, id, msg);
  }

  async function decide(approve: boolean) {
    if (!convId) return;
    const decisions = Object.fromEntries(pending.map((p) => [p.id, approve]));
    await run(
      `/api/labs/${labId}/assistant/conversations/${convId}/approvals/`,
      { decisions },
      convId,
      "",
    );
  }

  function newChat() {
    abort.current?.abort();
    setConvId(null);
    setLive(null);
  }

  const scope = project?.name ?? (conv.data?.project ? "this project" : null);
  const items = conv.data?.items ?? [];
  const atStart = !convId;

  return (
    <>
      <div className="flex items-start justify-between gap-2 pr-8">
        <div>
          <SheetTitle className="text-base">Assistant</SheetTitle>
          <p className="text-xs text-muted-foreground">
            {lab?.name ?? "This lab"}
            {scope ? ` · ${scope}` : ""}. It sees only what you can see.
          </p>
        </div>
        <div className="flex gap-1">
          <Button variant="ghost" size="icon" aria-label="New chat" onClick={newChat}>
            <Plus aria-hidden />
          </Button>
          {convId && (
            <Button
              variant="ghost"
              size="icon"
              aria-label="Delete this chat"
              onClick={() => {
                if (!window.confirm("Delete this chat and its saved messages?")) return;
                remove.mutate(convId, { onSuccess: newChat });
              }}
            >
              <Trash2 aria-hidden />
            </Button>
          )}
        </div>
      </div>
      <p role="note" className="rounded-md bg-muted px-3 py-2 text-xs">
        {cfg?.privacy_notice ??
          "Content from records you can see is sent to the AI provider under your own API key. Do not paste participant identifiers."}
      </p>

      {config.isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
      {cfg && usable.length === 0 && <Setup config={cfg} onOpenSettings={onClose} />}

      {cfg && usable.length > 0 && (
        <>
          {(convs.data ?? []).length > 0 && (
            <NativeSelect
              aria-label="Conversation"
              value={convId ?? ""}
              onChange={(e) => {
                setConvId(e.target.value || null);
                setLive(null);
              }}
            >
              <option value="">New chat</option>
              {(convs.data ?? []).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.title || "Untitled"} ({c.model})
                </option>
              ))}
            </NativeSelect>
          )}
          {atStart && (
            <div className="grid grid-cols-2 gap-2">
              <NativeSelect
                aria-label="Provider"
                value={chosen?.provider}
                onChange={(e) => {
                  setProvider(e.target.value as Provider);
                  setModel("");
                }}
              >
                {usable.map((p) => (
                  <option key={p.provider} value={p.provider}>
                    {p.label}
                  </option>
                ))}
              </NativeSelect>
              <NativeSelect
                aria-label="Model"
                value={model || chosen?.default_model}
                onChange={(e) => setModel(e.target.value)}
              >
                {chosen?.models.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.label}
                  </option>
                ))}
              </NativeSelect>
            </div>
          )}

          <div className="min-h-0 flex-1 overflow-y-auto" aria-live="polite" aria-label="Messages">
            <div className="grid gap-3 py-1">
              {atStart && !live && (
                <p className="text-sm text-muted-foreground">
                  Ask about your projects, tasks, documents, approvals or funding. I will cite the
                  records I use.
                </p>
              )}
              {items.map((it) => (
                <Item key={it.id} item={it} config={cfg} />
              ))}
              {live?.user && (
                <div className="ml-auto max-w-[85%] rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground">
                  {live.user}
                </div>
              )}
              {live && live.tools.length > 0 && (
                <ul className="grid gap-1" aria-label="Working">
                  {live.tools.map((t, i) => (
                    <ToolRow key={i} label={t.label} status={t.status} />
                  ))}
                </ul>
              )}
              {live?.text && (
                <div className="max-w-[95%] text-sm [&_p]:mb-1">
                  <Markdown text={live.text} ownLinksOnly />
                </div>
              )}
              {streaming && !live?.text && (
                <p className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Loader2 className="size-3.5 animate-spin" aria-hidden /> Thinking…
                </p>
              )}
              {live?.notice && !streaming && (
                <Notice
                  code={String(live.notice.code)}
                  refusal={live.notice.refusal}
                  message={String(live.notice.message ?? "")}
                />
              )}
              {live?.error && (
                <div className="grid gap-2">
                  <FormError message={live.error.message} />
                  {live.error.retryable && lastSent && !streaming && (
                    <Button
                      variant="outline"
                      size="sm"
                      className="w-fit"
                      onClick={() => void send(lastSent)}
                    >
                      Try again
                    </Button>
                  )}
                </div>
              )}
              {pending.length > 0 && !streaming && dismissed && (
                <div className="flex items-center justify-between rounded-md border p-2 text-sm">
                  <span>
                    {pending.length} action{pending.length > 1 ? "s" : ""} waiting for your
                    approval.
                  </span>
                  <Button size="sm" onClick={() => setDismissedFor("")}>
                    Review
                  </Button>
                </div>
              )}
              <div ref={end} />
            </div>
          </div>

          <form
            className="grid gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              void send(text);
            }}
          >
            <Textarea
              aria-label="Message"
              placeholder="Ask the assistant…"
              rows={2}
              value={text}
              maxLength={8000}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void send(text);
                }
              }}
            />
            <div className="flex justify-end gap-2">
              {streaming && (
                <Button type="button" variant="outline" onClick={() => abort.current?.abort()}>
                  Stop
                </Button>
              )}
              <Button type="submit" disabled={streaming || !text.trim()}>
                Send
              </Button>
            </div>
          </form>
        </>
      )}

      <ApprovalDialog
        calls={pending}
        open={!streaming && !dismissed}
        busy={streaming}
        onApprove={() => void decide(true)}
        onDecline={() => void decide(false)}
        onClose={() => setDismissedFor(pendingKey)}
      />
    </>
  );
}

/** The header button and the side drawer (D190). Scoped to the current lab, and to the current
 * project when the page is inside one; a new chat starts whenever that scope changes. */
export function AssistantDrawer({ labId }: { labId: string }) {
  const [open, setOpen] = useState(false);
  const [prefill, setPrefill] = useState("");
  const projectId = useMatches()
    .map((m) => m.params.projectId)
    .find(Boolean);
  useEffect(() => {
    const onPrefill = (e: Event) => {
      setPrefill((e as CustomEvent<string>).detail);
      setOpen(true);
    };
    window.addEventListener(ASSISTANT_PREFILL, onPrefill);
    return () => window.removeEventListener(ASSISTANT_PREFILL, onPrefill);
  }, []);
  return (
    <Sheet
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (!o) setPrefill("");
      }}
    >
      <SheetTrigger asChild>
        <Button variant="secondary" size="sm" aria-label="Assistant">
          <Sparkles aria-hidden />
          <span className="hidden sm:inline">Assistant</span>
        </Button>
      </SheetTrigger>
      <SheetContent className="max-w-xl gap-3 p-4" aria-describedby={undefined}>
        <AssistantPanel
          key={`${labId}:${projectId ?? ""}`}
          labId={labId}
          projectId={projectId}
          initialText={prefill}
          onClose={() => setOpen(false)}
        />
      </SheetContent>
    </Sheet>
  );
}
