import { useEffect, useRef, useState, type FormEvent } from "react";
import { X } from "lucide-react";
import { toast } from "sonner";
import { RichComposer, type Person } from "@/components/composer/RichComposer";
import { RelativeTime } from "@/components/shared/RelativeTime";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useCommentPeople, useDocumentComments } from "@/hooks/documents";
import { useMe } from "@/hooks/workspace";
import { personName, type DocumentComment } from "@/lib/api-types";
import { formErrors } from "@/lib/forms";
import { MessageText } from "@/lib/markdown";
import { cn } from "@/lib/utils";

const fail = (e: unknown) =>
  toast.error(
    formErrors(e, ["body"]).fields.body ?? formErrors(e, []).form ?? "Something went wrong.",
  );

/** A box that posts on submit and clears itself. */
function Composer({
  label,
  submitLabel,
  people,
  onSend,
  pending,
  rows,
  autoFocus,
}: {
  label: string;
  submitLabel: string;
  people?: Person[];
  onSend: (body: string) => Promise<unknown>;
  pending: boolean;
  rows?: number;
  autoFocus?: boolean;
}) {
  const [text, setText] = useState("");
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!text.trim()) return;
    onSend(text).then(() => setText(""), fail);
  };
  return (
    <form onSubmit={submit} className="grid gap-2">
      <RichComposer
        ariaLabel={label}
        placeholder={`${label}. Type @ to mention someone.`}
        value={text}
        onChange={setText}
        maxLength={4000}
        rows={rows}
        autoFocus={autoFocus}
        menuBelow
        people={people}
        submitLabel={submitLabel}
        submitting={pending}
      />
    </form>
  );
}

function Comment({
  comment,
  canDelete,
  onDelete,
}: {
  comment: DocumentComment;
  canDelete: boolean;
  onDelete: () => void;
}) {
  const [confirm, setConfirm] = useState(false);
  const who = personName(comment.author);
  return (
    <div className="grid gap-1">
      <div className="flex items-baseline justify-between gap-2 text-xs text-muted-foreground">
        <span>
          <strong className="font-semibold text-foreground">{who}</strong>{" "}
          <RelativeTime value={comment.created_at} />
        </span>
        {canDelete && !confirm && (
          <Button
            variant="ghost"
            size="sm"
            className="h-6 px-2"
            aria-label={`Delete comment by ${who}`}
            onClick={() => setConfirm(true)}
          >
            Delete
          </Button>
        )}
      </div>
      {comment.quote && (
        <blockquote className="border-l-2 pl-2 text-xs italic text-muted-foreground">
          {comment.quote}
        </blockquote>
      )}
      <MessageText text={comment.body} />
      {confirm && (
        <div
          role="alertdialog"
          aria-label="Confirm delete comment"
          className="flex items-center gap-2"
        >
          <span className="text-sm">
            {comment.parent ? "Delete this reply?" : "Delete this comment and its replies?"}
          </span>
          <Button variant="destructive" size="sm" onClick={onDelete}>
            Delete
          </Button>
          <Button variant="outline" size="sm" onClick={() => setConfirm(false)}>
            Keep
          </Button>
        </div>
      )}
    </div>
  );
}

/** Comments beside a document: threads one reply deep, resolve and reopen, delete. Everyone who
 * can read the document may comment; editors resolve anyone's, the author their own. */
export function CommentsPanel({
  labId,
  documentId,
  canEdit,
  canModerate,
  quote,
  canQuote,
  onClearQuote,
  onClose,
  className,
}: {
  labId: string;
  documentId: string;
  /** Can edit the document: resolves anyone's comment. */
  canEdit: boolean;
  /** A project lead, or a PI or lab admin: deletes anyone's comment. */
  canModerate: boolean;
  /** Text selected in the document, quoted by the next new comment. */
  quote: string;
  /** The document is text we can select in (not an embedded Google or Office file). */
  canQuote: boolean;
  onClearQuote: () => void;
  onClose: () => void;
  className?: string;
}) {
  const { list, create, resolve, remove } = useDocumentComments(labId, documentId);
  const me = useMe().data?.id;
  const people = useCommentPeople(labId, documentId);
  const [replying, setReplying] = useState<string>();
  const [showResolved, setShowResolved] = useState(false);
  const box = useRef<HTMLElement>(null);
  // On a phone the panel sits under the document: bring it into view when it opens.
  useEffect(() => box.current?.scrollIntoView?.({ block: "nearest" }), []);
  const all = list.data ?? [];
  const threads = all.filter((c) => !c.parent);
  const open = threads.filter((c) => !c.resolved_at);
  const resolved = threads.filter((c) => c.resolved_at);
  const del = (id: string) =>
    remove.mutate(id, { onSuccess: () => toast.success("Comment deleted"), onError: fail });
  const toggle = (c: DocumentComment) =>
    resolve.mutate(
      { id: c.id, resolved: !c.resolved_at },
      {
        onSuccess: () => toast.success(c.resolved_at ? "Comment reopened" : "Comment resolved"),
        onError: fail,
      },
    );

  const thread = (c: DocumentComment) => {
    const mine = c.author.id === me;
    return (
      <li
        key={c.id}
        className={cn(
          "grid gap-2 rounded-md border bg-background p-3",
          c.resolved_at && "opacity-75",
        )}
      >
        <Comment comment={c} canDelete={mine || canModerate} onDelete={() => del(c.id)} />
        {all
          .filter((r) => r.parent === c.id)
          .map((r) => (
            <div key={r.id} className="ml-3 border-l pl-3">
              <Comment
                comment={r}
                canDelete={r.author.id === me || canModerate}
                onDelete={() => del(r.id)}
              />
            </div>
          ))}
        <div className="flex flex-wrap gap-1">
          {!c.resolved_at && replying !== c.id && (
            <Button variant="ghost" size="sm" className="h-7" onClick={() => setReplying(c.id)}>
              Reply
            </Button>
          )}
          {(mine || canEdit) && (
            <Button
              variant="ghost"
              size="sm"
              className="h-7"
              aria-label={`${c.resolved_at ? "Reopen" : "Resolve"} comment by ${personName(c.author)}`}
              onClick={() => toggle(c)}
            >
              {c.resolved_at ? "Reopen" : "Resolve"}
            </Button>
          )}
        </div>
        {replying === c.id && (
          <Composer
            label="Reply"
            submitLabel="Reply"
            rows={1}
            autoFocus
            people={people}
            pending={create.isPending}
            onSend={(body) =>
              create.mutateAsync({ body, parent: c.id }).then(() => setReplying(undefined))
            }
          />
        )}
      </li>
    );
  };

  return (
    <aside ref={box} aria-label="Comments" className={cn("flex flex-col gap-3", className)}>
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">Comments</h2>
        <Button variant="ghost" size="sm" aria-label="Close comments" onClick={onClose}>
          <X aria-hidden />
        </Button>
      </div>
      {quote && (
        <div className="flex items-start gap-2 rounded-md bg-muted p-2 text-xs">
          <blockquote className="flex-1 italic text-muted-foreground">{quote}</blockquote>
          <Button variant="ghost" size="sm" className="h-6 px-2" onClick={onClearQuote}>
            Remove quote
          </Button>
        </div>
      )}
      <Composer
        label="Add a comment"
        submitLabel="Comment"
        people={people}
        pending={create.isPending}
        onSend={(body) => create.mutateAsync({ body, quote }).then(onClearQuote)}
      />
      {list.isLoading ? (
        <Skeleton aria-label="Loading comments" className="h-24 w-full" />
      ) : open.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No open comments.{canQuote && " Select text in the document to quote it in a comment."}
        </p>
      ) : (
        <ul className="grid gap-2">{open.map(thread)}</ul>
      )}
      {resolved.length > 0 && (
        <>
          <Button
            variant="ghost"
            size="sm"
            className="justify-start"
            aria-expanded={showResolved}
            onClick={() => setShowResolved(!showResolved)}
          >
            {showResolved ? "Hide resolved" : `Show resolved (${resolved.length})`}
          </Button>
          {showResolved && <ul className="grid gap-2">{resolved.map(thread)}</ul>}
        </>
      )}
    </aside>
  );
}
