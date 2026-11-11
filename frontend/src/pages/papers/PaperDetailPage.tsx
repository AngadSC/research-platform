import { Copy, Download, Eye, Pencil, Sparkles, Trash2, Upload } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { toast } from "sonner";
import { Setup } from "@/components/assistant/AssistantDrawer";
import { FormError } from "@/components/shared/FormError";
import { PageHeader } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useAssistantConfig } from "@/hooks/assistant";
import { useAuth } from "@/hooks/auth";
import { paperPdfUrl, useCitations, usePaper, usePaperMutations } from "@/hooks/papers";
import { useLab } from "@/hooks/workspace";
import type { PaperCitations, PaperDetail, PaperNote } from "@/lib/api-types";
import { openAssistant } from "@/lib/assistant";
import { when } from "@/lib/format";
import { formErrors } from "@/lib/forms";
import { Markdown } from "@/lib/markdown";
import { doiHref, urlHref } from "@/lib/references";
import { NativeSelect, Section } from "@/pages/admin/common";
import { UploadDialog } from "@/pages/project/UploadDialog";
import { authorName, PaperDialog } from "./PapersPage";
import { DriveLogo, FromDriveButton } from "@/components/shared/FromDriveButton";
import { attachFromDrive } from "@/lib/drive";

const STYLES: { value: keyof PaperCitations; label: string }[] = [
  { value: "apa", label: "APA" },
  { value: "mla", label: "MLA" },
  { value: "chicago", label: "Chicago" },
  { value: "bibtex", label: "BibTeX" },
];

const byline = (u: { display_name?: string; email: string }) => u.display_name || u.email;

function CopyCitation({ labId, paperId }: { labId: string; paperId: string }) {
  const { data } = useCitations(labId, paperId);
  const [style, setStyle] = useState<keyof PaperCitations>("apa");
  const text = data?.[style] ?? "";

  function copy() {
    navigator.clipboard?.writeText(text).then(
      () => toast.success("Citation copied"),
      () => toast.error("Could not copy to the clipboard."),
    );
  }

  return (
    <Section title="Cite this paper">
      <div className="flex flex-wrap items-center gap-2">
        <NativeSelect
          aria-label="Citation style"
          className="w-36"
          value={style}
          onChange={(e) => setStyle(e.target.value as keyof PaperCitations)}
        >
          {STYLES.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </NativeSelect>
        <Button variant="outline" size="sm" disabled={!text} onClick={copy}>
          <Copy aria-hidden /> Copy citation
        </Button>
      </div>
      <pre className="overflow-x-auto rounded-md bg-muted p-3 text-sm whitespace-pre-wrap">
        {text || "Loading..."}
      </pre>
    </Section>
  );
}

/** The two AI shortcuts open the app's assistant with a prompt ready to send (no second LLM path). */
function AiShortcuts({ labId, paper }: { labId: string; paper: PaperDetail }) {
  const { data: cfg } = useAssistantConfig(labId, true);
  if (!cfg) return null;
  if (!cfg.can_use || !cfg.providers.some((p) => p.has_key)) return <Setup config={cfg} />;
  const named = `the paper "${paper.title}" (paper_id ${paper.id})`;
  const source = paper.has_pdf
    ? `Read its PDF with read_paper (all pages)`
    : `It has no PDF, so use its abstract and the lab's notes from get_paper`;
  return (
    <div className="flex flex-wrap gap-2">
      <Button
        variant="secondary"
        onClick={() =>
          openAssistant(
            `Draft structured notes on ${named}. ${source}. Cover the research question, the method, the main findings with numbers, and the limitations, then save them with add_paper_note so the lab can read them.`,
          )
        }
      >
        <Sparkles aria-hidden /> Generate notes with AI
      </Button>
      <Button
        variant="secondary"
        onClick={() =>
          openAssistant(
            `Give me citations for ${named} in APA, MLA, Chicago and BibTeX. Use cite_paper for each style and show them exactly as returned.`,
          )
        }
      >
        <Sparkles aria-hidden /> Generate citation with AI
      </Button>
    </div>
  );
}

function NoteItem({
  labId,
  note,
  mine,
  canRemove,
}: {
  labId: string;
  note: PaperNote;
  mine: boolean;
  canRemove: boolean;
}) {
  const { editNote, removeNote } = usePaperMutations(labId);
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(note.body);
  const [error, setError] = useState<string>();

  async function save() {
    try {
      await editNote.mutateAsync({ id: note.id, body: text });
      setEditing(false);
      setError(undefined);
    } catch (err) {
      const { fields, form } = formErrors(err, ["body"]);
      setError(fields.body ?? form);
    }
  }

  return (
    <li className="grid gap-2 rounded-md border p-3">
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs text-muted-foreground">
          <span className="font-medium text-foreground">{byline(note.author)}</span> ·{" "}
          {when(note.created_at)}
          {note.edited_at && " · edited"}
        </p>
        <span className="flex shrink-0 gap-1">
          {mine && !editing && (
            <Button
              variant="ghost"
              size="sm"
              aria-label="Edit note"
              onClick={() => setEditing(true)}
            >
              <Pencil aria-hidden />
            </Button>
          )}
          {canRemove && (
            <Button
              variant="ghost"
              size="sm"
              aria-label="Delete note"
              onClick={() => {
                if (window.confirm("Delete this note?"))
                  removeNote.mutate(note.id, {
                    onError: () => toast.error("Could not delete the note."),
                  });
              }}
            >
              <Trash2 aria-hidden />
            </Button>
          )}
        </span>
      </div>
      {editing ? (
        <div className="grid gap-2">
          <Textarea
            aria-label="Edit note"
            rows={4}
            value={text}
            maxLength={20000}
            onChange={(e) => setText(e.target.value)}
          />
          <FormError message={error} />
          <div className="flex justify-end gap-2">
            <Button variant="outline" size="sm" onClick={() => setEditing(false)}>
              Cancel
            </Button>
            <Button size="sm" disabled={!text.trim()} onClick={() => void save()}>
              Save
            </Button>
          </div>
        </div>
      ) : (
        <div className="text-sm [&_p]:mb-1">
          <Markdown text={note.body} ownLinksOnly />
        </div>
      )}
    </li>
  );
}

export function PaperDetailPage() {
  const { labId = "", paperId = "" } = useParams();
  const navigate = useNavigate();
  const { email } = useAuth();
  const { data: lab } = useLab(labId);
  const { data: paper, isLoading, isError } = usePaper(labId, paperId);
  const { addNote, remove, uploadPdf } = usePaperMutations(labId);
  const [text, setText] = useState("");
  const [error, setError] = useState<string>();
  const [editing, setEditing] = useState(false);
  const [uploading, setUploading] = useState(false);

  if (isLoading) return <Skeleton className="h-64 w-full" />;
  if (isError || !paper)
    return (
      <p role="alert" className="text-sm">
        This paper could not be found.
      </p>
    );

  const perms = lab?.my_permissions ?? [];
  const canContribute = perms.includes("contribute_lab");
  const isManager = perms.includes("manage_lab");
  const authors = paper.authors;
  const doiLink = paper.doi ? doiHref(paper.doi) : null;
  const webLink = paper.url ? urlHref(paper.url) : null;

  async function submitNote(e: FormEvent) {
    e.preventDefault();
    if (!text.trim()) return;
    try {
      await addNote.mutateAsync({ paperId, body: text });
      setText("");
      setError(undefined);
    } catch (err) {
      const { fields, form } = formErrors(err, ["body"]);
      setError(fields.body ?? form);
    }
  }

  return (
    <>
      <PageHeader
        title={paper.title}
        description={[authors.map(authorName).join("; "), paper.year, paper.venue]
          .filter(Boolean)
          .join(" · ")}
        actions={
          <>
            {canContribute && (
              <Button variant="outline" onClick={() => setEditing(true)}>
                Edit
              </Button>
            )}
            {(canContribute && paper.added_by.email === email) || isManager ? (
              <Button
                variant="outline"
                onClick={() => {
                  if (window.confirm(`Delete "${paper.title}" and its notes?`))
                    remove.mutate(paper.id, {
                      onSuccess: () => void navigate(`/labs/${labId}/papers`),
                      onError: () => toast.error("Could not delete the paper."),
                    });
                }}
              >
                Delete
              </Button>
            ) : null}
          </>
        }
      />
      <div className="grid max-w-3xl gap-6">
        <Section title="Details">
          <dl className="grid gap-2 text-sm">
            {doiLink && (
              <div>
                <dt className="sr-only">DOI</dt>
                <dd>
                  <a
                    className="underline underline-offset-4"
                    href={doiLink}
                    target="_blank"
                    rel="noreferrer noopener"
                  >
                    doi:{paper.doi}
                  </a>
                </dd>
              </div>
            )}
            {webLink && (
              <div>
                <dt className="sr-only">Link</dt>
                <dd>
                  <a
                    className="underline underline-offset-4"
                    href={webLink}
                    target="_blank"
                    rel="noreferrer noopener"
                  >
                    {paper.url}
                  </a>
                </dd>
              </div>
            )}
            <div>
              <dt className="sr-only">Added by</dt>
              <dd className="text-muted-foreground">
                Added by {byline(paper.added_by)} on {when(paper.created_at)}
              </dd>
            </div>
          </dl>
          {paper.abstract && (
            <div>
              <h3 className="text-sm font-medium">Abstract</h3>
              <p className="text-sm whitespace-pre-wrap text-muted-foreground">{paper.abstract}</p>
            </div>
          )}
          <div className="flex flex-wrap gap-2">
            {paper.pdf && (
              <>
                {paper.pdf.external_url ? (
                  <Button variant="outline" size="sm" asChild>
                    <a href={paper.pdf.external_url} target="_blank" rel="noopener noreferrer">
                      <DriveLogo /> Open in Drive
                    </a>
                  </Button>
                ) : (
                  <>
                    <Button variant="outline" size="sm" asChild>
                      <Link to="pdf">
                        <Eye aria-hidden /> View PDF
                      </Link>
                    </Button>
                    <Button variant="outline" size="sm" asChild>
                      <a href={paperPdfUrl(labId, paper.id)} download>
                        <Download aria-hidden /> Download PDF
                      </a>
                    </Button>
                  </>
                )}
              </>
            )}
            {canContribute && (
              <Button variant="outline" size="sm" onClick={() => setUploading(true)}>
                <Upload aria-hidden /> {paper.pdf ? "Replace PDF" : "Upload PDF"}
              </Button>
            )}
            {canContribute && (
              <FromDriveButton
                labId={labId}
                label={paper.pdf ? "Replace from Drive" : "PDF from Drive"}
                onPick={(f) => attachFromDrive(`/api/labs/${labId}/papers/${paper.id}/pdf/`, f.id)}
              />
            )}
          </div>
        </Section>

        <CopyCitation labId={labId} paperId={paper.id} />

        <Section title="Use the AI assistant">
          <AiShortcuts labId={labId} paper={paper} />
        </Section>

        <Section title={`Notes (${paper.notes.length})`} description="Every member can read these.">
          {canContribute && (
            <form onSubmit={submitNote} className="grid gap-2">
              <Textarea
                aria-label="Add a note"
                placeholder="What did you take from this paper?"
                rows={3}
                value={text}
                maxLength={20000}
                onChange={(e) => setText(e.target.value)}
              />
              <FormError message={error} />
              <Button
                type="submit"
                size="sm"
                className="justify-self-end"
                disabled={addNote.isPending || !text.trim()}
              >
                Add note
              </Button>
            </form>
          )}
          {paper.notes.length === 0 ? (
            <p className="text-sm text-muted-foreground">No notes yet.</p>
          ) : (
            <ul className="grid gap-2" aria-label="Notes">
              {paper.notes.map((n) => (
                <NoteItem
                  key={n.id}
                  labId={labId}
                  note={n}
                  mine={n.author.email === email}
                  canRemove={n.author.email === email || isManager}
                />
              ))}
            </ul>
          )}
        </Section>
      </div>

      {editing && (
        <PaperDialog labId={labId} paper={paper} open onClose={() => setEditing(false)} />
      )}
      <UploadDialog
        open={uploading}
        onOpenChange={setUploading}
        send={(file, onProgress) => uploadPdf.mutateAsync({ id: paper.id, file, onProgress })}
      />
    </>
  );
}
