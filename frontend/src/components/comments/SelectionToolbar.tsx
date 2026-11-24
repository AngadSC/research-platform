import { Hash, MessageSquarePlus, Sparkles, Trash2, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "react-router";
import { toast } from "sonner";
import { RichComposer } from "@/components/composer/RichComposer";
import { RelativeTime } from "@/components/shared/RelativeTime";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useAssistantReady } from "@/hooks/assistant";
import { useCrumbs, useCurrentProjectId } from "@/hooks/crumbs";
import { useMentionPeople } from "@/hooks/mentions";
import { useAddPageComment, useDeletePageComment, usePageComments } from "@/hooks/pageComments";
import { useProjects } from "@/hooks/projects";
import { useLabs, useMe } from "@/hooks/workspace";
import { openAssistant } from "@/lib/assistant";
import { personName } from "@/lib/api-types";
import { formErrors } from "@/lib/forms";
import { navItems } from "@/lib/nav";
import { MessageText } from "@/lib/markdown";

/** Pages where what is on screen can be about participants: never sent to an AI from here. */
const NO_AI_PATHS = /\/(participants|subjects)(\/|$)/;
const MAX_QUOTE = 500;

interface Picked {
  text: string;
  /** Where to float the buttons: the middle of the selection's top edge, in the window. */
  x: number;
  y: number;
  summarizable: boolean;
}

/** What is selected in the page's main area, or null. Text in boxes and the document editor is
 * left alone: those have their own toolbars. */
function readSelection(path: string): Picked | null {
  const sel = window.getSelection();
  if (!sel || sel.rangeCount === 0 || sel.isCollapsed) return null;
  const text = sel.toString().replace(/\s+/g, " ").trim();
  if (text.length < 2) return null;
  const range = sel.getRangeAt(0);
  const node = range.commonAncestorContainer;
  const el = node instanceof Element ? node : node.parentElement;
  const main = document.getElementById("main");
  if (!el || !main || !main.contains(el)) return null;
  if (
    el.closest(
      "input, textarea, [contenteditable='true'], [role='dialog'], [data-no-selection-tools]",
    )
  )
    return null;
  const r = range.getBoundingClientRect();
  if (r.width === 0 && r.height === 0) return null;
  return {
    text,
    x: r.left + r.width / 2,
    y: r.top,
    summarizable: !el.closest("[data-no-ai]") && !NO_AI_PATHS.test(path),
  };
}

/** The small icon buttons that float over selected text on every page: comment on it and, when an
 * AI is connected, ask the assistant to summarize it. */
export function SelectionToolbar({ labId }: { labId: string | undefined }) {
  const { pathname } = useLocation();
  const [picked, setPicked] = useState<Picked | null>(null);
  // A panel belongs to the page it was opened on, so it is not shown after navigating away.
  const [panel, setPanel] = useState<{ quote: string; path: string } | null>(null);
  const frame = useRef(0);
  const aiReady = useAssistantReady(labId);

  useEffect(() => {
    const update = () => {
      cancelAnimationFrame(frame.current);
      frame.current = requestAnimationFrame(() => setPicked(readSelection(pathname)));
    };
    document.addEventListener("selectionchange", update);
    window.addEventListener("scroll", update, true);
    window.addEventListener("resize", update);
    return () => {
      cancelAnimationFrame(frame.current);
      document.removeEventListener("selectionchange", update);
      window.removeEventListener("scroll", update, true);
      window.removeEventListener("resize", update);
    };
  }, [pathname]);

  if (!labId) return null;
  const keepSelection = (e: React.MouseEvent) => e.preventDefault(); // a click must not clear it
  return (
    <>
      {picked && (
        <div
          role="toolbar"
          aria-label="Selected text"
          style={{
            left: Math.min(Math.max(picked.x, 48), window.innerWidth - 48),
            top: picked.y < 56 ? picked.y + 28 : picked.y - 44,
          }}
          className="fixed z-50 flex -translate-x-1/2 gap-0.5 rounded-lg border bg-popover p-1 text-popover-foreground shadow-lg print:hidden"
          onMouseDown={keepSelection}
        >
          <Button
            variant="ghost"
            size="icon"
            className="size-8"
            aria-label="Comment on this"
            title="Comment on this"
            onClick={() => {
              setPanel({ quote: picked.text.slice(0, MAX_QUOTE), path: pathname });
              window.getSelection()?.removeAllRanges();
            }}
          >
            <MessageSquarePlus aria-hidden />
          </Button>
          {aiReady && picked.summarizable && (
            <Button
              variant="ghost"
              size="icon"
              className="size-8"
              aria-label="Summarize this"
              title="Summarize this with your assistant"
              onClick={() => {
                openAssistant(`Summarize this: ${picked.text}`, { send: true });
                window.getSelection()?.removeAllRanges();
              }}
            >
              <Sparkles aria-hidden />
            </Button>
          )}
        </div>
      )}
      {panel && panel.path === pathname && (
        <CommentPanel labId={labId} quote={panel.quote} onClose={() => setPanel(null)} />
      )}
    </>
  );
}

function CommentPanel({
  labId,
  quote,
  onClose,
}: {
  labId: string;
  quote: string;
  onClose: () => void;
}) {
  const { pathname } = useLocation();
  const crumbs = useCrumbs();
  const projectId = useCurrentProjectId();
  const people = useMentionPeople(labId, projectId);
  const me = useMe().data as { id?: string } | undefined;
  const list = usePageComments(labId, pathname);
  const add = useAddPageComment(labId, pathname);
  const remove = useDeletePageComment(labId, pathname);
  const [text, setText] = useState("");
  const label = crumbs.at(-1)?.label ?? "this page";
  const labs = useLabs().data;
  const projects = useProjects(labId).data;
  const perms = labs?.find((l) => l.id === labId)?.my_permissions;
  const inventory = labs?.find((l) => l.id === labId)?.inventory_enabled;
  const pages = useMemo(
    () => [
      ...navItems(labId, perms, inventory)
        .filter((n) => n.to.startsWith(`/labs/${labId}`))
        .map((n) => ({ label: n.label, to: n.to })),
      ...(projects ?? []).map((p) => ({ label: p.name, to: `/labs/${labId}/projects/${p.id}` })),
    ],
    [labId, perms, inventory, projects],
  );

  const send = () => {
    if (!text.trim()) return;
    add.mutate(
      { body: text, quote, page_label: label },
      {
        onSuccess: () => {
          setText("");
          onClose();
          toast.success("Comment added");
        },
        onError: (e) =>
          toast.error(
            formErrors(e, ["body"]).fields.body ?? formErrors(e, []).form ?? "Could not comment.",
          ),
      },
    );
  };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <aside
      aria-label="Comment"
      className="fixed right-4 bottom-4 left-4 z-50 grid max-h-[80vh] gap-3 overflow-y-auto rounded-xl border bg-popover p-4 text-popover-foreground shadow-2xl sm:left-auto sm:w-96 print:hidden"
    >
      <div className="flex items-center justify-between gap-2">
        <h2 className="truncate text-sm font-semibold">Comment on {label}</h2>
        <Button variant="ghost" size="icon" className="size-7" aria-label="Close" onClick={onClose}>
          <X aria-hidden />
        </Button>
      </div>
      {quote && (
        <blockquote className="border-l-2 pl-2 text-xs text-muted-foreground italic">
          {quote}
        </blockquote>
      )}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
      >
        <RichComposer
          ariaLabel="Your comment"
          placeholder="Write a comment. Type @ to tag a person."
          value={text}
          onChange={setText}
          maxLength={4000}
          rows={3}
          autoFocus
          menuBelow
          people={people}
          submitLabel="Comment"
          submitting={add.isPending}
          footer={
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="sm" type="button">
                  <Hash aria-hidden /> Tag a page
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" className="max-h-64 overflow-y-auto">
                <DropdownMenuLabel>Link to a page</DropdownMenuLabel>
                {pages.map((p) => (
                  <DropdownMenuItem
                    key={p.to}
                    onSelect={() =>
                      setText(
                        (t) =>
                          `${t}${t && !t.endsWith(" ") ? " " : ""}#[${p.label}](page:${p.to}) `,
                      )
                    }
                  >
                    {p.label}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          }
        />
      </form>
      {list.data && list.data.length > 0 && (
        <ul aria-label="Comments on this page" className="grid gap-3 border-t pt-3">
          {list.data.map((c) => (
            <li key={c.id} className="grid gap-1 text-sm">
              <div className="flex items-baseline justify-between gap-2 text-xs text-muted-foreground">
                <span>
                  <strong className="font-semibold text-foreground">{personName(c.author)}</strong>{" "}
                  <RelativeTime value={c.created_at} />
                </span>
                {c.author.id === me?.id && (
                  <Button
                    variant="ghost"
                    size="icon"
                    className="size-6"
                    aria-label="Delete comment"
                    onClick={() => remove.mutate(c.id)}
                  >
                    <Trash2 aria-hidden />
                  </Button>
                )}
              </div>
              {c.quote && (
                <blockquote className="border-l-2 pl-2 text-xs text-muted-foreground italic">
                  {c.quote}
                </blockquote>
              )}
              <MessageText text={c.body} />
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}
