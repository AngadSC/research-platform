import { BookOpen, FileText, Plus } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { toast } from "sonner";
import { DataTable, HIDE_NARROW, HIDE_NARROWER, type Column } from "@/components/shared/DataTable";
import { EmptyState } from "@/components/shared/EmptyState";
import { FormError } from "@/components/shared/FormError";
import { FormField } from "@/components/shared/FormField";
import { PageHeader } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { lookupDoi, usePaperMutations, usePapers } from "@/hooks/papers";
import { useProviders } from "@/hooks/integrations";
import { useLab } from "@/hooks/workspace";
import type { Paper, PaperDetail, PaperInput } from "@/lib/api-types";
import { formErrors, type FormErrors } from "@/lib/forms";
import { ZoteroImportDialog } from "@/pages/papers/ZoteroImportDialog";
import { MAX_BYTES, NOTICE } from "@/pages/project/UploadDialog";
import { DriveLogo, FromDriveButton } from "@/components/shared/FromDriveButton";
import { attachFromDrive, type PickedFile } from "@/lib/drive";

const KNOWN = ["title", "authors", "year", "venue", "doi", "url", "abstract"];

/** "Smith, Jane" lines back into text; a trailing comma marks an organisation. */
export const authorLines = (authors: string[]) => authors.join("\n");

/** For reading: drops the trailing comma that marks an organisation. */
export const authorName = (a: string) => a.replace(/,\s*$/, "");

export function authorsShort(authors: string[]) {
  if (authors.length === 0) return "-";
  const first = authorName(authors[0]!);
  return authors.length > 1 ? `${first} and ${authors.length - 1} more` : first;
}

const AUTHOR_HINT =
  'One per line, "Family, Given" (or "Given Family"). End an organisation\'s name with a comma.';

/** Add a paper, or edit one when `paper` is given. The fields start from `paper`, then autofill. */
export function PaperDialog({
  labId,
  paper,
  open,
  onClose,
  onSaved,
}: {
  labId: string;
  paper?: PaperDetail;
  open: boolean;
  onClose: () => void;
  onSaved?: (id: string) => void;
}) {
  const { create, update, uploadPdf } = usePaperMutations(labId);
  const empty = {
    title: "",
    authors: "",
    year: "",
    venue: "",
    doi: "",
    url: "",
    abstract: "",
  };
  const [form, setForm] = useState(
    paper
      ? {
          title: paper.title,
          authors: authorLines(paper.authors),
          year: paper.year != null ? String(paper.year) : "",
          venue: paper.venue,
          doi: paper.doi,
          url: paper.url,
          abstract: paper.abstract,
        }
      : empty,
  );
  const [file, setFile] = useState<File | null>(null);
  const [drivePdf, setDrivePdf] = useState<PickedFile | null>(null);
  const [ack, setAck] = useState(false);
  const [errors, setErrors] = useState<FormErrors>({ fields: {} });
  const [autofilling, setAutofilling] = useState(false);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof empty) => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  async function autofill() {
    setAutofilling(true);
    setErrors({ fields: {} });
    try {
      const got = await lookupDoi(labId, form.doi.trim());
      if (!got.found) {
        setErrors({ fields: { doi: "Crossref has no record of that DOI." } });
        return;
      }
      setForm({
        title: got.title ?? "",
        authors: authorLines(got.authors ?? []),
        year: got.year != null ? String(got.year) : "",
        venue: got.venue ?? "",
        doi: got.doi ?? form.doi.trim(),
        url: got.url ?? "",
        abstract: got.abstract ?? "",
      });
    } catch (err) {
      setErrors(formErrors(err, ["doi"]));
    } finally {
      setAutofilling(false);
    }
  }

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!form.title.trim()) return setErrors({ fields: { title: "Enter a title" } });
    if (file && file.size > MAX_BYTES)
      return setErrors({ fields: {}, form: "That PDF is larger than the 50 MB limit." });
    const body: PaperInput = {
      title: form.title.trim(),
      authors: form.authors
        .split("\n")
        .map((a) => a.trim())
        .filter(Boolean),
      year: form.year ? Number(form.year) : null,
      venue: form.venue.trim(),
      doi: form.doi.trim(),
      url: form.url.trim(),
      abstract: form.abstract,
    };
    setBusy(true);
    try {
      const saved = paper
        ? await update.mutateAsync({ id: paper.id, ...body })
        : await create.mutateAsync(body);
      if (file) await uploadPdf.mutateAsync({ id: saved.id, file });
      else if (drivePdf)
        await attachFromDrive(`/api/labs/${labId}/papers/${saved.id}/pdf/`, drivePdf.id);
      setErrors({ fields: {} });
      toast.success(paper ? "Paper saved" : "Paper added");
      onClose();
      onSaved?.(saved.id);
    } catch (err) {
      setErrors(formErrors(err, KNOWN));
    } finally {
      setBusy(false);
    }
  }

  const f = errors.fields;
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogTitle className="text-base font-semibold">
          {paper ? "Edit paper" : "Add a paper"}
        </DialogTitle>
        <DialogDescription className="sr-only">Paper details</DialogDescription>
        <form onSubmit={submit} noValidate className="grid gap-3">
          <div className="flex items-end gap-2">
            <div className="min-w-0 flex-1">
              <FormField label="DOI" error={f.doi}>
                {(p) => (
                  <Input
                    maxLength={200}
                    {...p}
                    value={form.doi}
                    onChange={set("doi")}
                    placeholder="10.1234/abcd"
                  />
                )}
              </FormField>
            </div>
            <Button
              type="button"
              variant="outline"
              disabled={!form.doi.trim() || autofilling}
              onClick={() => void autofill()}
            >
              {autofilling ? "Looking up..." : "Autofill from DOI"}
            </Button>
          </div>
          <FormField label="Title" error={f.title}>
            {(p) => <Input maxLength={500} {...p} value={form.title} onChange={set("title")} />}
          </FormField>
          <FormField label="Authors" error={f.authors} hint={AUTHOR_HINT}>
            {(p) => <Textarea {...p} rows={3} value={form.authors} onChange={set("authors")} />}
          </FormField>
          <div className="grid gap-3 sm:grid-cols-2">
            <FormField label="Year" error={f.year}>
              {(p) => <Input {...p} type="number" value={form.year} onChange={set("year")} />}
            </FormField>
            <FormField label="Journal or conference" error={f.venue}>
              {(p) => <Input maxLength={300} {...p} value={form.venue} onChange={set("venue")} />}
            </FormField>
          </div>
          <FormField label="Link" error={f.url}>
            {(p) => (
              <Input
                maxLength={500}
                {...p}
                value={form.url}
                onChange={set("url")}
                placeholder="https://"
              />
            )}
          </FormField>
          <FormField label="Abstract" error={f.abstract}>
            {(p) => (
              <Textarea
                maxLength={20000}
                {...p}
                rows={4}
                value={form.abstract}
                onChange={set("abstract")}
              />
            )}
          </FormField>
          {!paper && (
            <>
              <FormField label="PDF (optional)">
                {(p) => (
                  <input
                    {...p}
                    type="file"
                    accept="application/pdf,.pdf"
                    onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                  />
                )}
              </FormField>
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <FromDriveButton
                  labId={labId}
                  quiet
                  label={drivePdf ? "Choose another from Drive" : "PDF from Drive"}
                  onPick={async (f) => setDrivePdf(f)}
                />
                {drivePdf && (
                  <span className="flex items-center gap-1.5">
                    <DriveLogo /> {drivePdf.name}
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => setDrivePdf(null)}
                    >
                      Remove
                    </Button>
                  </span>
                )}
              </div>
              {file && (
                <>
                  <p
                    role="note"
                    className="rounded-md border border-primary/40 bg-primary/10 p-3 text-sm font-medium"
                  >
                    {NOTICE}
                  </p>
                  <label className="flex items-start gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={ack}
                      onChange={(e) => setAck(e.target.checked)}
                      className="mt-0.5"
                    />
                    I confirm this file contains no participant identifiers
                  </label>
                </>
              )}
            </>
          )}
          <FormError message={errors.form} />
          <div className="flex justify-end gap-2">
            <DialogClose asChild>
              <Button type="button" variant="outline">
                Cancel
              </Button>
            </DialogClose>
            <Button type="submit" disabled={busy || (!!file && !ack)}>
              {paper ? "Save" : "Add paper"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** The lab's paper library: every member reads; contributors add (contribute_lab). */
export function PapersPage() {
  const { labId = "" } = useParams();
  const { data: lab } = useLab(labId);
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [adding, setAdding] = useState(false);
  const [importing, setImporting] = useState(false);
  const papers = usePapers(labId, q.trim());
  const canAdd = !!lab?.my_permissions.includes("contribute_lab");
  // Your own connected Zotero account, if any: Lab settings, Integrations.
  const zotero = useProviders(labId).data?.some(
    (p) => p.name === "zotero" && p.account?.status === "active",
  );

  const columns: Column<Paper>[] = [
    {
      key: "title",
      header: "Title",
      cell: (p) => (
        <Link
          to={p.id}
          className="font-medium underline-offset-4 hover:underline"
          onClick={(e) => e.stopPropagation()}
        >
          {p.title}
        </Link>
      ),
    },
    {
      key: "authors",
      header: "Authors",
      className: HIDE_NARROW,
      cell: (p) => authorsShort(p.authors),
    },
    { key: "year", header: "Year", cell: (p) => p.year ?? "-" },
    { key: "venue", header: "Journal", className: HIDE_NARROWER, cell: (p) => p.venue || "-" },
    {
      key: "pdf",
      header: "PDF",
      cell: (p) =>
        p.has_pdf ? (
          <>
            <FileText className="size-4" aria-hidden /> <span className="sr-only">Has a PDF</span>
          </>
        ) : (
          "-"
        ),
    },
    { key: "notes", header: "Notes", className: HIDE_NARROWER, cell: (p) => p.note_count },
  ];

  return (
    <>
      <PageHeader
        title="Papers"
        description="Papers the lab has read and every member's notes on them."
        actions={
          canAdd ? (
            <div className="flex flex-wrap gap-2">
              {zotero && (
                <Button variant="outline" onClick={() => setImporting(true)}>
                  Import from Zotero
                </Button>
              )}
              <Button onClick={() => setAdding(true)}>
                <Plus aria-hidden /> Add paper
              </Button>
            </div>
          ) : undefined
        }
      />
      <div className="mb-4 max-w-sm">
        <FormField label="Search papers">
          {(p) => <Input {...p} type="search" value={q} onChange={(e) => setQ(e.target.value)} />}
        </FormField>
      </div>
      <DataTable
        columns={columns}
        rows={papers.data ?? []}
        getRowKey={(p) => p.id}
        loading={papers.isLoading}
        onRowClick={(p) => void navigate(p.id)}
        empty={
          <EmptyState
            icon={BookOpen}
            title={q ? "No papers match that search" : "No papers yet"}
            description={
              q
                ? "Try fewer or different words."
                : "Add a paper the lab has read, then share notes on it."
            }
          />
        }
      />
      {importing && <ZoteroImportDialog labId={labId} onClose={() => setImporting(false)} />}
      {adding && (
        <PaperDialog
          labId={labId}
          open
          onClose={() => setAdding(false)}
          onSaved={(id) => void navigate(id)}
        />
      )}
    </>
  );
}
