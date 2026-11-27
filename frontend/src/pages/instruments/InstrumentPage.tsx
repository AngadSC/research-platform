import QRCode from "qrcode";
import { Copy, Printer, Upload } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router";
import { toast } from "sonner";
import { InstrumentFileDialog } from "@/components/instruments/InstrumentFileDialog";
import { ConfirmDelete } from "@/components/shared/ConfirmDelete";
import { EmptyState } from "@/components/shared/EmptyState";
import { FormError } from "@/components/shared/FormError";
import { FormField } from "@/components/shared/FormField";
import { PageHeader } from "@/components/shared/PageHeader";
import { RelativeTime } from "@/components/shared/RelativeTime";
import { HashTabs } from "@/components/shared/TabNav";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useInventory } from "@/hooks/admin";
import {
  dropPath,
  parseLine,
  useContributableProjects,
  useDropLinks,
  useInstrumentFiles,
  useSoftwareChoices,
} from "@/hooks/instruments";
import { useReauth } from "@/hooks/reauth";
import { useLab } from "@/hooks/workspace";
import { personName, type DropLinkCreated, type InventoryItem } from "@/lib/api-types";
import { formErrors, type FormErrors } from "@/lib/forms";
import { shortDate } from "@/lib/format";
import { CATEGORIES, ItemDialog, STATUSES } from "@/pages/admin/InventorySection";
import { NativeSelect, formValue } from "@/pages/admin/common";

const label = (list: readonly { value: string; label: string }[], v: string) =>
  list.find((x) => x.value === v)?.label ?? v;

function Details({ item }: { item: InventoryItem }) {
  const software = useSoftwareChoices().data ?? [];
  const rows: [string, string | null | undefined][] = [
    [
      "Software it exports from",
      item.instrument_software && label(software, item.instrument_software),
    ],
    ["Category", label(CATEGORIES, item.category)],
    ["Status", label(STATUSES, item.status)],
    ["Location", item.location],
    ["Owner", item.owner && personName(item.owner)],
    ["Serial or asset number", item.serial_number],
    ["Purchase date", item.purchase_date],
    ["Calibration or maintenance due", item.due_date],
    ["Notes", item.notes],
  ];
  return (
    <dl className="grid max-w-2xl gap-x-6 gap-y-3 rounded-xl border bg-card p-4 text-sm sm:grid-cols-[14rem_1fr]">
      {rows.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-muted-foreground">{k}</dt>
          <dd className="whitespace-pre-wrap">{v || "-"}</dd>
        </div>
      ))}
    </dl>
  );
}

function Data({ labId, item }: { labId: string; item: InventoryItem }) {
  const files = useInstrumentFiles(labId, { instrument: item.id });
  const [open, setOpen] = useState<string | null>(null);
  if (files.isLoading)
    return (
      <div className="grid gap-2" aria-busy="true" aria-label="Loading files">
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-12 w-full" />
      </div>
    );
  if (!files.data?.length)
    return (
      <EmptyState
        icon={Upload}
        title="No files from this instrument yet"
        description="Drop exported files here and they land in a project's Instrument data folder, read and previewed."
        action={
          <Button asChild>
            <Link to={dropPath(labId, item.id)}>Drop files</Link>
          </Button>
        }
      />
    );
  return (
    <>
      <ul className="grid gap-2" aria-label="Files from this instrument">
        {files.data.map((f) => (
          <li key={f.id}>
            <button
              type="button"
              onClick={() => setOpen(f.id)}
              className="grid w-full gap-0.5 rounded-lg border bg-card p-3 text-left text-sm hover:bg-muted/50 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
            >
              <span className="flex items-center justify-between gap-2">
                <span className="truncate font-medium">{f.filename}</span>
                <RelativeTime
                  value={f.created_at}
                  className="shrink-0 text-xs text-muted-foreground"
                />
              </span>
              <span className="text-xs text-muted-foreground">
                {[
                  f.project.name,
                  f.dropped_by ? personName(f.dropped_by) : "Drop link",
                  parseLine(f),
                ].join(" · ")}
              </span>
            </button>
          </li>
        ))}
      </ul>
      <InstrumentFileDialog labId={labId} fileId={open} onClose={() => setOpen(null)} />
    </>
  );
}

const EXPIRY = [
  { value: "1", label: "1 day" },
  { value: "7", label: "1 week" },
  { value: "30", label: "30 days" },
  { value: "90", label: "3 months" },
  { value: "365", label: "1 year" },
];

function Links({ labId, item }: { labId: string; item: InventoryItem }) {
  const { list, create, revoke } = useDropLinks(labId, item.id);
  const { projects } = useContributableProjects(labId);
  const reauth = useReauth(); // D194: a link that needs no sign-in asks for a recent one
  const [errors, setErrors] = useState<FormErrors>({ fields: {} });
  const [made, setMade] = useState<DropLinkCreated | null>(null);
  const [stopping, setStopping] = useState<string | null>(null);
  // One choice: take it. Otherwise the project of the newest link, if the person can still use it.
  const recent = list.data?.[0]?.project.id;
  const preset =
    projects.length === 1 ? projects[0]!.id : projects.some((p) => p.id === recent) ? recent : "";

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const fd = new FormData(form);
    const project = formValue(fd, "project");
    if (!project) return setErrors({ fields: { project: "Choose a project" } });
    try {
      const link = await reauth.run(() =>
        create.mutateAsync({
          project,
          label: formValue(fd, "label"),
          expires_in_days: Number(formValue(fd, "expires")),
        }),
      );
      setErrors({ fields: {} });
      setMade(link);
      form.reset();
    } catch (err) {
      setErrors(formErrors(err, ["project", "label", "expires_in_days"]));
    }
  }

  const copy = (url: string) =>
    navigator.clipboard.writeText(url).then(
      () => toast.success("Link copied"),
      () => toast.error("Could not copy. Select the link and copy it."),
    );

  return (
    <div className="grid max-w-3xl gap-6">
      <p className="text-sm text-muted-foreground">
        A drop link lets a shared instrument PC or a core facility send files into one project
        without signing in. It can only add files: it cannot see or open anything. Anyone with the
        link can use it, so treat it like a key.
      </p>
      <form
        onSubmit={(e) => void submit(e)}
        noValidate
        className="grid gap-3 rounded-xl border bg-card p-4 sm:grid-cols-2"
      >
        <FormField label="Project" error={errors.fields.project}>
          {(p) => (
            <NativeSelect {...p} key={preset} name="project" defaultValue={preset}>
              <option value="">Choose a project</option>
              {projects.map((pr) => (
                <option key={pr.id} value={pr.id}>
                  {pr.name}
                </option>
              ))}
            </NativeSelect>
          )}
        </FormField>
        <FormField label="Name" hint="Where it will be used" error={errors.fields.label}>
          {(p) => <Input {...p} name="label" maxLength={100} placeholder="Core facility PC" />}
        </FormField>
        <FormField label="Stops working" error={errors.fields.expires_in_days}>
          {(p) => (
            <NativeSelect {...p} name="expires" defaultValue="90">
              {EXPIRY.map((x) => (
                <option key={x.value} value={x.value}>
                  {x.label}
                </option>
              ))}
            </NativeSelect>
          )}
        </FormField>
        <div className="flex items-end">
          <Button type="submit" disabled={create.isPending}>
            Make a drop link
          </Button>
        </div>
        <div className="sm:col-span-2">
          <FormError message={errors.form} />
        </div>
      </form>
      {made && (
        <div
          role="status"
          className="grid gap-2 rounded-xl border border-primary/40 bg-primary/5 p-4"
        >
          <p className="text-sm font-medium">
            Copy this link now. For safety it is shown only once.
          </p>
          <div className="flex gap-2">
            <Input
              readOnly
              value={made.url}
              aria-label="Drop link"
              onFocus={(e) => e.target.select()}
            />
            <Button variant="outline" onClick={() => void copy(made.url)}>
              <Copy aria-hidden /> Copy
            </Button>
          </div>
        </div>
      )}
      {list.isLoading ? (
        <Skeleton className="h-12 w-full" />
      ) : !list.data?.length ? (
        <EmptyState
          compact
          title="No drop links"
          description="Make one above for a shared instrument PC or a core facility."
        />
      ) : (
        <ul className="grid gap-2" aria-label="Drop links">
          {list.data.map((l) => (
            <li
              key={l.id}
              className="flex items-center justify-between gap-3 rounded-lg border bg-card p-3 text-sm"
            >
              <span className="grid min-w-0 gap-0.5">
                <span className="truncate font-medium">
                  {l.label || "Drop link"} → {l.project.name}
                </span>
                <span className="text-xs text-muted-foreground">
                  {[
                    `Made by ${personName(l.created_by)}`,
                    l.expired
                      ? "Expired"
                      : l.expires_at
                        ? `Stops ${shortDate(l.expires_at)}`
                        : "No end date",
                    l.last_used_at
                      ? `Last used ${new Date(l.last_used_at).toLocaleString()}`
                      : "Not used yet",
                  ].join(" · ")}
                </span>
              </span>
              <Button variant="outline" size="sm" onClick={() => setStopping(l.id)}>
                Turn off
              </Button>
            </li>
          ))}
        </ul>
      )}
      <ConfirmDelete
        open={!!stopping}
        name="this drop link"
        noun="link"
        verb="Turn off"
        description="It stops working at once. Files already sent stay in the project."
        pending={revoke.isPending}
        onClose={() => setStopping(null)}
        onConfirm={() =>
          stopping &&
          revoke.mutate(stopping, {
            onSuccess: () => toast.success("Link turned off"),
            onError: () => toast.error("Could not turn the link off. Try again."),
            onSettled: () => setStopping(null),
          })
        }
      />
      {reauth.dialog}
    </div>
  );
}

function Sticker({ labId, item }: { labId: string; item: InventoryItem }) {
  const url = `${window.location.origin}${dropPath(labId, item.id)}`;
  const [src, setSrc] = useState<string>();
  useEffect(() => {
    let live = true;
    QRCode.toDataURL(url, { margin: 1, width: 320 }).then(
      (s) => live && setSrc(s),
      () => undefined,
    );
    return () => {
      live = false;
    };
  }, [url]);
  return (
    <div className="grid justify-items-start gap-4">
      <p className="text-sm text-muted-foreground print:hidden">
        Stick this on the instrument. Scanning it opens the drop page on a phone, after signing in.
      </p>
      <figure className="grid w-72 justify-items-center gap-2 rounded-xl border-2 border-foreground bg-white p-4 text-center text-black">
        {src ? (
          <img src={src} alt={`QR code to send files from ${item.name}`} className="size-56" />
        ) : (
          <Skeleton className="size-56" />
        )}
        <figcaption className="grid gap-1">
          <span className="text-lg font-semibold">{item.name}</span>
          <span className="text-xs">Scan to send this instrument's files</span>
        </figcaption>
      </figure>
      <Button className="print:hidden" onClick={() => window.print()}>
        <Printer aria-hidden /> Print sticker
      </Button>
    </div>
  );
}

/** An equipment item as a place that collects data (opened from Inventory). */
export function InstrumentPage() {
  const { labId = "", itemId = "" } = useParams();
  const { data: lab } = useLab(labId);
  const canEdit = !!lab?.my_permissions.includes("manage_inventory");
  const inv = useInventory(labId, { category: "equipment" });
  const item = inv.list.data?.find((i) => i.id === itemId);
  const [editing, setEditing] = useState(false);

  if (inv.list.isLoading)
    return (
      <div className="grid gap-3" aria-busy="true" aria-label="Loading">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-4 w-80" />
      </div>
    );
  if (!item)
    return (
      <EmptyState
        title="Instrument not found"
        description="It may have been removed, or it is not equipment."
        action={
          <Button asChild variant="outline">
            <Link to={`/labs/${labId}/inventory`}>Back to Inventory</Link>
          </Button>
        }
      />
    );
  return (
    <div className="[&>nav]:print:hidden">
      <div className="print:hidden">
        <PageHeader
          title={item.name}
          description={item.location || undefined}
          actions={
            <>
              {canEdit && (
                <Button variant="outline" onClick={() => setEditing(true)}>
                  Edit
                </Button>
              )}
              <Button asChild>
                <Link to={dropPath(labId, item.id)}>
                  <Upload aria-hidden /> Drop files
                </Link>
              </Button>
            </>
          }
        />
      </div>
      <HashTabs
        label="Instrument"
        tabs={[
          { id: "data", label: "Data", content: <Data labId={labId} item={item} /> },
          { id: "details", label: "Details", content: <Details item={item} /> },
          { id: "links", label: "Drop links", content: <Links labId={labId} item={item} /> },
          { id: "sticker", label: "QR sticker", content: <Sticker labId={labId} item={item} /> },
        ]}
      />
      {canEdit && (
        <ItemDialog
          labId={labId}
          item={item}
          open={editing}
          onClose={() => setEditing(false)}
          create={inv.create}
          update={inv.update}
        />
      )}
    </div>
  );
}
