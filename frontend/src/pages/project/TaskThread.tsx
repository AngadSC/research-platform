import { useEffect, useRef, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { RelativeTime } from "@/components/shared/RelativeTime";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useTaskPosts } from "@/hooks/projects";
import { useMe } from "@/hooks/workspace";
import { personName, type TaskPost } from "@/lib/api-types";
import { formErrors } from "@/lib/forms";
import { Markdown } from "@/lib/markdown";

const fail = (e: unknown) =>
  toast.error(formErrors(e, ["body"]).fields.body ?? "Something went wrong.");

function Post({
  post,
  mine,
  canDelete,
  onEdit,
  onDelete,
}: {
  post: TaskPost;
  mine: boolean;
  canDelete: boolean;
  onEdit: (body: string) => Promise<unknown>;
  onDelete: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(post.body);
  const [confirm, setConfirm] = useState(false);
  return (
    <li className="grid gap-1 rounded-md border bg-background p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2 text-xs text-muted-foreground">
        <span>
          <strong className="font-semibold text-foreground">{personName(post.author)}</strong>{" "}
          <RelativeTime value={post.created_at} />
          {post.edited_at && " (edited)"}
        </span>
        <span className="flex gap-1">
          {mine && !editing && (
            <Button variant="ghost" size="sm" onClick={() => setEditing(true)}>
              Edit<span className="sr-only"> post by {personName(post.author)}</span>
            </Button>
          )}
          {(mine || canDelete) && !confirm && (
            <Button variant="ghost" size="sm" onClick={() => setConfirm(true)}>
              Delete<span className="sr-only"> post by {personName(post.author)}</span>
            </Button>
          )}
        </span>
      </div>
      {editing ? (
        <form
          className="grid gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            onEdit(text).then(() => setEditing(false), fail);
          }}
        >
          <Textarea aria-label="Edit post" value={text} onChange={(e) => setText(e.target.value)} />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" size="sm" onClick={() => setEditing(false)}>
              Cancel
            </Button>
            <Button type="submit" size="sm" disabled={!text.trim()}>
              Save post
            </Button>
          </div>
        </form>
      ) : (
        <Markdown text={post.body} />
      )}
      {confirm && (
        <div
          role="alertdialog"
          aria-label="Confirm delete post"
          className="flex items-center gap-2"
        >
          <span className="text-sm">Delete this post?</span>
          <Button variant="destructive" size="sm" onClick={onDelete}>
            Confirm delete post
          </Button>
          <Button variant="outline" size="sm" onClick={() => setConfirm(false)}>
            Keep
          </Button>
        </div>
      )}
    </li>
  );
}

/** The per-task bulletin board: oldest first, composer at the bottom (D142). */
export function TaskThread({
  labId,
  taskId,
  canPost,
  isLead,
}: {
  labId: string;
  taskId: string;
  /** edit_content */
  canPost: boolean;
  /** edit_project: leads delete any post */
  isLead: boolean;
}) {
  const { list, create, edit, remove } = useTaskPosts(labId, taskId);
  const me = useMe().data;
  const [text, setText] = useState("");
  const end = useRef<HTMLDivElement>(null);
  const count = list.data?.length ?? 0;
  useEffect(() => {
    end.current?.scrollIntoView?.({ block: "nearest" });
  }, [count]);

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!text.trim()) return;
    create.mutate(text, { onSuccess: () => setText(""), onError: fail });
  }

  return (
    <section aria-label="Updates" className="grid gap-3">
      <h3 className="text-sm font-semibold">Updates</h3>
      {list.isLoading ? (
        <p aria-busy="true" className="text-sm text-muted-foreground">
          Loading updates
        </p>
      ) : count === 0 ? (
        <p className="text-sm text-muted-foreground">No updates yet.</p>
      ) : (
        <ul className="grid gap-2">
          {list.data!.map((p) => (
            <Post
              key={p.id}
              post={p}
              mine={p.author.id === me?.id && canPost}
              canDelete={isLead}
              onEdit={(body) => edit.mutateAsync({ id: p.id, body })}
              onDelete={() =>
                remove.mutate(p.id, {
                  onSuccess: () => toast.success("Post deleted"),
                  onError: fail,
                })
              }
            />
          ))}
        </ul>
      )}
      <div ref={end} />
      {canPost ? (
        <form onSubmit={submit} className="grid gap-2">
          <Textarea
            aria-label="Write an update"
            placeholder="Post an update. **bold**, *italic*, `code`, - lists and links work."
            value={text}
            maxLength={5000}
            onChange={(e) => setText(e.target.value)}
          />
          <div className="flex justify-end">
            <Button type="submit" disabled={create.isPending || !text.trim()}>
              Post update
            </Button>
          </div>
        </form>
      ) : (
        <p className="text-xs text-muted-foreground">
          You can read updates, but only editors can post.
        </p>
      )}
    </section>
  );
}
