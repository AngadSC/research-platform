import { Search } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { toast } from "sonner";
import { ConfirmDelete } from "@/components/shared/ConfirmDelete";
import { EmptyState } from "@/components/shared/EmptyState";
import { FormError } from "@/components/shared/FormError";
import { FormField } from "@/components/shared/FormField";
import { MoreMenu } from "@/components/shared/MoreMenu";
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
import { Skeleton } from "@/components/ui/skeleton";
import { useInventory } from "@/hooks/admin";
import { useBox, useSamples, useStorage, useStorageActions } from "@/hooks/samples";
import { useDebounced } from "@/hooks/useDebounced";
import { useLab, useMembers } from "@/hooks/workspace";
import type { BoxDetail, StorageBox, StorageUnit, Tube } from "@/lib/api-types";
import { personName } from "@/lib/api-types";
import { localDateISO } from "@/lib/format";
import { formErrors, type FormErrors } from "@/lib/forms";
import { formValue, NativeSelect } from "@/pages/admin/common";
import { BoxGrid } from "./BoxGrid";
import { rowLetter } from "./common";

type Actions = ReturnType<typeof useStorageActions>;

const UNIT_KINDS = [
  { value: "freezer", label: "Freezer" },
  { value: "fridge", label: "Fridge" },
  { value: "ln2", label: "Liquid nitrogen" },
  { value: "room", label: "Room temperature" },
] as const;
const kindLabel = (k: string) => UNIT_KINDS.find((x) => x.value === k)?.label ?? k;

/** What a `run` returns to say a field is missing, before anything is sent. */
const missing = (fields: Record<string, string>) => ({ missing: fields });

/** Runs a save, shows a toast, and puts field errors back on the form. */
function useSubmit(
  known: string[],
  run: (fd: FormData) => Promise<unknown> | ReturnType<typeof missing>,
  done: string,
  onClose: () => void,
) {
  const [errors, setErrors] = useState<FormErrors>({ fields: {} });
  const submit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    try {
      const out = await run(new FormData(e.currentTarget));
      if (out && typeof out === "object" && "missing" in out)
        return setErrors({ fields: out.missing as Record<string, string> });
      toast.success(done);
      onClose();
    } catch (err) {
      setErrors(formErrors(err, known));
    }
  };
  return { errors, setErrors, submit };
}

function Buttons({ label = "Save" }: { label?: string }) {
  return (
    <div className="flex justify-end gap-2">
      <DialogClose asChild>
        <Button type="button" variant="outline">
          Cancel
        </Button>
      </DialogClose>
      <Button type="submit">{label}</Button>
    </div>
  );
}

function UnitDialog({
  labId,
  unit,
  actions,
  onClose,
}: {
  labId: string;
  unit: StorageUnit | null;
  actions: Actions;
  onClose: () => void;
}) {
  const equipment = useInventory(labId, { category: "equipment" }).list.data ?? [];
  const { errors, submit } = useSubmit(
    ["name", "kind", "temperature", "location", "equipment"],
    async (fd) => {
      const v = (k: string) => formValue(fd, k);
      if (!v("name")) return missing({ name: "Enter a name" });
      const body = {
        name: v("name"),
        kind: v("kind") as StorageUnit["kind"],
        temperature: v("temperature"),
        location: v("location"),
        equipment: v("equipment") || null,
      };
      return unit
        ? actions.editUnit.mutateAsync({ id: unit.id, ...body })
        : actions.addUnit.mutateAsync(body);
    },
    unit ? "Saved" : "Added",
    onClose,
  );
  const f = errors.fields;
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogTitle className="text-base font-semibold">
          {unit ? "Edit freezer or fridge" : "Add a freezer or fridge"}
        </DialogTitle>
        <DialogDescription className="sr-only">Storage details</DialogDescription>
        <form onSubmit={submit} noValidate className="grid gap-3">
          <FormField label="Name" error={f.name}>
            {(p) => <Input {...p} name="name" maxLength={200} defaultValue={unit?.name} />}
          </FormField>
          <div className="grid gap-3 sm:grid-cols-2">
            <FormField label="Type" error={f.kind}>
              {(p) => (
                <NativeSelect {...p} name="kind" defaultValue={unit?.kind ?? "freezer"}>
                  {UNIT_KINDS.map((k) => (
                    <option key={k.value} value={k.value}>
                      {k.label}
                    </option>
                  ))}
                </NativeSelect>
              )}
            </FormField>
            <FormField label="Temperature" error={f.temperature} hint="For example -80 °C">
              {(p) => (
                <Input {...p} name="temperature" maxLength={32} defaultValue={unit?.temperature} />
              )}
            </FormField>
          </div>
          <FormField label="Location" error={f.location} hint="For example Room 4-12">
            {(p) => <Input {...p} name="location" maxLength={200} defaultValue={unit?.location} />}
          </FormField>
          <FormField
            label="Equipment record"
            error={f.equipment}
            hint="Optional. Links to the item in Inventory."
          >
            {(p) => (
              <NativeSelect {...p} name="equipment" defaultValue={unit?.equipment?.id ?? ""}>
                <option value="">None</option>
                {equipment.map((i) => (
                  <option key={i.id} value={i.id}>
                    {i.name}
                  </option>
                ))}
              </NativeSelect>
            )}
          </FormField>
          <FormError message={errors.form} />
          <Buttons />
        </form>
      </DialogContent>
    </Dialog>
  );
}

function BoxDialog({
  box,
  unitId,
  units,
  actions,
  onClose,
}: {
  box: StorageBox | null;
  unitId: string;
  units: StorageUnit[];
  actions: Actions;
  onClose: () => void;
}) {
  const { errors, submit } = useSubmit(
    ["unit", "name", "rows", "cols", "shelf"],
    async (fd) => {
      const v = (k: string) => formValue(fd, k);
      if (!v("name")) return missing({ name: "Enter a name" });
      const body = {
        unit: v("unit"),
        name: v("name"),
        rows: Number(v("rows") || 9),
        cols: Number(v("cols") || 9),
        shelf: v("shelf"),
      };
      return box
        ? actions.editBox.mutateAsync({ id: box.id, ...body })
        : actions.addBox.mutateAsync(body);
    },
    box ? "Saved" : "Box added",
    onClose,
  );
  const f = errors.fields;
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogTitle className="text-base font-semibold">
          {box ? "Edit box" : "Add a box"}
        </DialogTitle>
        <DialogDescription className="sr-only">Box details</DialogDescription>
        <form onSubmit={submit} noValidate className="grid gap-3">
          <FormField label="Freezer or fridge" error={f.unit}>
            {(p) => (
              <NativeSelect {...p} name="unit" defaultValue={box?.unit ?? unitId}>
                {units.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.name}
                  </option>
                ))}
              </NativeSelect>
            )}
          </FormField>
          <FormField label="Name" error={f.name}>
            {(p) => <Input {...p} name="name" maxLength={200} defaultValue={box?.name} />}
          </FormField>
          <div className="grid grid-cols-3 gap-3">
            <FormField label="Rows" error={f.rows}>
              {(p) => (
                <Input
                  {...p}
                  name="rows"
                  type="number"
                  min={1}
                  max={26}
                  defaultValue={box?.rows ?? 9}
                />
              )}
            </FormField>
            <FormField label="Columns" error={f.cols}>
              {(p) => (
                <Input
                  {...p}
                  name="cols"
                  type="number"
                  min={1}
                  max={26}
                  defaultValue={box?.cols ?? 9}
                />
              )}
            </FormField>
            <FormField label="Shelf" error={f.shelf}>
              {(p) => <Input {...p} name="shelf" maxLength={64} defaultValue={box?.shelf} />}
            </FormField>
          </div>
          <FormError message={errors.form} />
          <Buttons />
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** Pick a registry sample: a search box over a list. */
function SamplePicker({ labId, onPick }: { labId: string; onPick: (id: string) => void }) {
  const [text, setText] = useState("");
  const q = useDebounced(text.trim());
  const { data = [], isLoading } = useSamples(labId, { q });
  return (
    <div className="grid gap-2">
      <FormField label="Sample" required>
        {(p) => (
          <Input
            {...p}
            type="search"
            placeholder="Search by code or name"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
        )}
      </FormField>
      <NativeSelect
        aria-label="Matching samples"
        size={5}
        className="h-auto"
        onChange={(e) => onPick(e.target.value)}
      >
        {data.map((s) => (
          <option key={s.id} value={s.id}>
            {s.code} {s.name}
          </option>
        ))}
      </NativeSelect>
      {!isLoading && data.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No samples found.{" "}
          <Link to=".." className="underline">
            Add it in Samples first
          </Link>
          .
        </p>
      )}
    </div>
  );
}

function PlaceDialog({
  labId,
  box,
  row,
  col,
  actions,
  onClose,
}: {
  labId: string;
  box: BoxDetail;
  row: number;
  col: number;
  actions: Actions;
  onClose: () => void;
}) {
  const members = useMembers(labId).data ?? [];
  const [sample, setSample] = useState("");
  const { errors, submit } = useSubmit(
    ["sample", "row", "col", "label", "amount", "stored_on", "owner"],
    async (fd) => {
      if (!sample) return missing({ sample: "Pick a sample" });
      const v = (k: string) => formValue(fd, k);
      return actions.placeTube.mutateAsync({
        box: box.id,
        row,
        col,
        sample,
        label: v("label"),
        amount: v("amount"),
        stored_on: v("stored_on") || null,
        owner: v("owner") || undefined,
      });
    },
    "Tube placed",
    onClose,
  );
  const f = errors.fields;
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogTitle className="text-base font-semibold">
          Place a tube in {box.name} at {rowLetter(row)}
          {col}
        </DialogTitle>
        <DialogDescription className="sr-only">Choose the sample in this tube</DialogDescription>
        <form onSubmit={submit} noValidate className="grid gap-3">
          <SamplePicker labId={labId} onPick={setSample} />
          {f.sample && (
            <p role="alert" className="text-xs font-medium text-destructive">
              {f.sample}
            </p>
          )}
          <div className="grid gap-3 sm:grid-cols-2">
            <FormField label="Label" error={f.label} hint="Optional, such as Stock or Dilution">
              {(p) => <Input {...p} name="label" maxLength={100} />}
            </FormField>
            <FormField label="Amount" error={f.amount} hint="For example 50 µL">
              {(p) => <Input {...p} name="amount" maxLength={64} />}
            </FormField>
            <FormField label="Date stored" error={f.stored_on}>
              {(p) => <Input {...p} name="stored_on" type="date" defaultValue={localDateISO()} />}
            </FormField>
            <FormField label="Held by" error={f.owner}>
              {(p) => (
                <NativeSelect {...p} name="owner" defaultValue="">
                  <option value="">Me</option>
                  {members.map((m) => (
                    <option key={m.id} value={m.user.id}>
                      {personName(m.user)}
                    </option>
                  ))}
                </NativeSelect>
              )}
            </FormField>
          </div>
          <FormError message={errors.form ?? f.row} />
          <Buttons label="Place tube" />
        </form>
      </DialogContent>
    </Dialog>
  );
}

function MoveDialog({
  tube,
  units,
  actions,
  onClose,
}: {
  tube: Tube;
  units: StorageUnit[];
  actions: Actions;
  onClose: () => void;
}) {
  const boxes = units.flatMap((u) => u.boxes.map((b) => ({ ...b, unitName: u.name })));
  const [boxId, setBoxId] = useState(tube.box);
  const target = boxes.find((b) => b.id === boxId);
  const { errors, submit } = useSubmit(
    ["box", "row", "col"],
    (fd) =>
      actions.editTube.mutateAsync({
        id: tube.id,
        box: boxId,
        row: Number(fd.get("row")),
        col: Number(fd.get("col")),
      }),
    "Tube moved",
    onClose,
  );
  const f = errors.fields;
  const range = (n: number) => Array.from({ length: n }, (_, i) => i + 1);
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogTitle className="text-base font-semibold">Move {tube.sample.code}</DialogTitle>
        <DialogDescription className="text-sm text-muted-foreground">
          Choose an empty spot. You can also move it by taking it out and placing it again.
        </DialogDescription>
        <form onSubmit={submit} noValidate className="grid gap-3">
          <FormField label="Box" error={f.box}>
            {(p) => (
              <NativeSelect {...p} value={boxId} onChange={(e) => setBoxId(e.target.value)}>
                {boxes.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.unitName} / {b.name}
                  </option>
                ))}
              </NativeSelect>
            )}
          </FormField>
          <div className="grid grid-cols-2 gap-3" key={boxId}>
            <FormField label="Row" error={f.row}>
              {(p) => (
                <NativeSelect {...p} name="row" defaultValue={boxId === tube.box ? tube.row : 1}>
                  {range(target?.rows ?? 1).map((r) => (
                    <option key={r} value={r}>
                      {rowLetter(r)}
                    </option>
                  ))}
                </NativeSelect>
              )}
            </FormField>
            <FormField label="Column" error={f.col}>
              {(p) => (
                <NativeSelect {...p} name="col" defaultValue={boxId === tube.box ? tube.col : 1}>
                  {range(target?.cols ?? 1).map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </NativeSelect>
              )}
            </FormField>
          </div>
          <FormError message={errors.form} />
          <Buttons label="Move" />
        </form>
      </DialogContent>
    </Dialog>
  );
}

function TubeDialog({
  labId,
  tube,
  canEdit,
  actions,
  onMove,
  onClose,
}: {
  labId: string;
  tube: Tube;
  canEdit: boolean;
  actions: Actions;
  onMove: () => void;
  onClose: () => void;
}) {
  const members = useMembers(labId).data ?? [];
  const [confirm, setConfirm] = useState(false);
  const { errors, submit } = useSubmit(
    ["label", "amount", "stored_on", "owner"],
    (fd) => {
      const v = (k: string) => formValue(fd, k);
      return actions.editTube.mutateAsync({
        id: tube.id,
        label: v("label"),
        amount: v("amount"),
        stored_on: v("stored_on") || null,
        owner: v("owner") !== tube.owner.id ? v("owner") : undefined,
      });
    },
    "Tube saved",
    onClose,
  );
  const f = errors.fields;
  return (
    <>
      <Dialog open={!confirm} onOpenChange={(o) => !o && onClose()}>
        <DialogContent>
          <DialogTitle className="text-base font-semibold">
            {tube.position}: {tube.sample.code} {tube.sample.name}
          </DialogTitle>
          <DialogDescription className="text-sm text-muted-foreground">
            Held by {personName(tube.owner)}.{" "}
            <Link to={`../${tube.sample.id}`} className="underline underline-offset-2">
              Open the sample
            </Link>
          </DialogDescription>
          <form onSubmit={submit} noValidate className="grid gap-3">
            <div className="grid gap-3 sm:grid-cols-2">
              <FormField label="Label" error={f.label}>
                {(p) => (
                  <Input
                    {...p}
                    name="label"
                    maxLength={100}
                    defaultValue={tube.label}
                    disabled={!canEdit}
                  />
                )}
              </FormField>
              <FormField label="Amount" error={f.amount}>
                {(p) => (
                  <Input
                    {...p}
                    name="amount"
                    maxLength={64}
                    defaultValue={tube.amount}
                    disabled={!canEdit}
                  />
                )}
              </FormField>
              <FormField label="Date stored" error={f.stored_on}>
                {(p) => (
                  <Input
                    {...p}
                    name="stored_on"
                    type="date"
                    defaultValue={tube.stored_on ?? ""}
                    disabled={!canEdit}
                  />
                )}
              </FormField>
              <FormField label="Held by" error={f.owner}>
                {(p) => (
                  <NativeSelect
                    {...p}
                    name="owner"
                    defaultValue={tube.owner.id}
                    disabled={!canEdit}
                  >
                    {members.map((m) => (
                      <option key={m.id} value={m.user.id}>
                        {personName(m.user)}
                      </option>
                    ))}
                  </NativeSelect>
                )}
              </FormField>
            </div>
            <FormError message={errors.form} />
            <div className="flex flex-wrap justify-end gap-2">
              {canEdit && (
                <>
                  <Button type="button" variant="outline" onClick={() => setConfirm(true)}>
                    Take out
                  </Button>
                  <Button type="button" variant="outline" onClick={onMove}>
                    Move
                  </Button>
                </>
              )}
              <DialogClose asChild>
                <Button type="button" variant="outline">
                  {canEdit ? "Cancel" : "Close"}
                </Button>
              </DialogClose>
              {canEdit && <Button type="submit">Save</Button>}
            </div>
          </form>
        </DialogContent>
      </Dialog>
      <ConfirmDelete
        open={confirm}
        verb="Take out"
        name={`${tube.sample.code} from ${tube.position}`}
        noun="tube"
        description="The tube leaves the box. The sample stays in the registry."
        pending={actions.removeTube.isPending}
        onClose={() => setConfirm(false)}
        onConfirm={() =>
          actions.removeTube.mutate(tube.id, {
            onSuccess: () => {
              toast.success("Tube taken out");
              onClose();
            },
            onError: (e) => toast.error(formErrors(e, []).form ?? "Could not take the tube out."),
            onSettled: () => setConfirm(false),
          })
        }
      />
    </>
  );
}

/** The grid of one box, with the dialogs for its tubes. */
function BoxPanel({
  labId,
  boxId,
  units,
  canEdit,
  actions,
  highlight,
}: {
  labId: string;
  boxId: string;
  units: StorageUnit[];
  canEdit: boolean;
  actions: Actions;
  highlight: string | null;
}) {
  const { data: box, isLoading, error } = useBox(labId, boxId);
  const [place, setPlace] = useState<{ row: number; col: number } | null>(null);
  const [tubeId, setTubeId] = useState<string | null>(null);
  const [moving, setMoving] = useState(false);
  if (isLoading) return <Skeleton className="h-64 w-full" aria-label="Loading" />;
  if (error || !box)
    return <p className="text-sm text-muted-foreground">We could not open that box.</p>;
  const tube = box.tubes.find((t) => t.id === tubeId);
  return (
    <section aria-labelledby="box-title" className="grid gap-3 rounded-lg border bg-card p-4">
      <h2 id="box-title" className="text-base font-semibold">
        {box.unit_name} / {box.name}{" "}
        <span className="text-sm font-normal text-muted-foreground">
          {box.filled} of {box.rows * box.cols} filled
        </span>
      </h2>
      <BoxGrid
        box={box}
        highlight={highlight}
        onEmpty={canEdit ? (row, col) => setPlace({ row, col }) : undefined}
        onFilled={(t) => setTubeId(t.id)}
      />
      {place && (
        <PlaceDialog
          labId={labId}
          box={box}
          {...place}
          actions={actions}
          onClose={() => setPlace(null)}
        />
      )}
      {tube && !moving && (
        <TubeDialog
          labId={labId}
          tube={tube}
          canEdit={canEdit}
          actions={actions}
          onMove={() => setMoving(true)}
          onClose={() => setTubeId(null)}
        />
      )}
      {tube && moving && (
        <MoveDialog
          tube={tube}
          units={units}
          actions={actions}
          onClose={() => {
            setMoving(false);
            setTubeId(null);
          }}
        />
      )}
    </section>
  );
}

/** "Where is P0012?": every tube of the samples that match, with a link to its box. */
function FindSample({ labId }: { labId: string }) {
  const [text, setText] = useState("");
  const q = useDebounced(text.trim());
  const { data = [], isLoading } = useSamples(labId, { q }, q.length > 0);
  return (
    <section className="grid gap-2">
      <FormField label="Find a sample" hint="Type a sample code, for example P0001.">
        {(p) => (
          <div className="relative max-w-md">
            <Search
              aria-hidden
              className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
            />
            <Input
              {...p}
              type="search"
              placeholder="Code or name"
              className="pl-9"
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
          </div>
        )}
      </FormField>
      {q && !isLoading && data.length === 0 && (
        <p className="text-sm text-muted-foreground">No sample matches {q}.</p>
      )}
      {q && data.length > 0 && (
        <ul className="grid divide-y rounded-lg border bg-card text-sm" aria-label="Search results">
          {data.map((s) => (
            <li key={s.id} className="grid gap-1 px-3 py-2">
              <Link to={`../${s.id}`} className="font-medium underline-offset-2 hover:underline">
                {s.code} {s.name}
              </Link>
              {s.tubes.length === 0 && (
                <span className="text-muted-foreground">Not in storage</span>
              )}
              {s.tubes.map((t) => (
                <Link
                  key={t.id}
                  to={`?box=${t.box}&tube=${t.id}`}
                  className="text-muted-foreground underline-offset-2 hover:underline"
                >
                  {t.unit_name} / {t.box_name} / {t.position}
                  {t.amount ? `, ${t.amount}` : ""}, held by {personName(t.owner)}
                </Link>
              ))}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function StoragePage() {
  const { labId = "" } = useParams();
  const { data: lab } = useLab(labId);
  const on = !!lab?.inventory_enabled;
  const canEdit = !!lab?.my_permissions.includes("manage_samples");
  const units = useStorage(labId, on);
  const actions = useStorageActions(labId);
  const [params, setParams] = useSearchParams();
  const boxId = params.get("box") ?? "";
  const [unitDialog, setUnitDialog] = useState<StorageUnit | "new" | null>(null);
  const [boxDialog, setBoxDialog] = useState<{ box: StorageBox | null; unit: string } | null>(null);
  const [deleting, setDeleting] = useState<
    { kind: "unit"; unit: StorageUnit } | { kind: "box"; box: StorageBox } | null
  >(null);
  const list = units.data ?? [];
  const pickBox = (id: string) =>
    setParams(
      (p) => {
        p.set("box", id);
        p.delete("tube");
        return p;
      },
      { replace: true },
    );

  function confirmDelete() {
    if (!deleting) return;
    const done = {
      onSuccess: () => {
        toast.success("Deleted");
        if (deleting.kind === "box" && deleting.box.id === boxId)
          setParams(
            (p) => {
              p.delete("box");
              p.delete("tube");
              return p;
            },
            { replace: true },
          );
      },
      onError: (e: unknown) => toast.error(formErrors(e, []).form ?? "Could not delete it."),
      onSettled: () => setDeleting(null),
    };
    if (deleting.kind === "unit") actions.removeUnit.mutate(deleting.unit.id, done);
    else actions.removeBox.mutate(deleting.box.id, done);
  }

  return (
    <>
      <PageHeader
        title="Storage"
        description="Freezers, fridges and the boxes in them. Click a box to see its tubes."
        actions={
          <>
            <Button variant="outline" asChild>
              <Link to="..">All samples</Link>
            </Button>
            {on && canEdit && (
              <Button onClick={() => setUnitDialog("new")}>Add freezer or fridge</Button>
            )}
          </>
        }
      />
      {lab && !on && (
        <EmptyState
          title="Samples are turned off"
          description="This lab is set up as a dry lab. A PI or lab admin can turn inventory and samples on in Lab details."
        />
      )}
      {on && (
        <div className="grid gap-6">
          <FindSample labId={labId} />
          {units.isLoading && <Skeleton className="h-40 w-full" aria-label="Loading" />}
          {!units.isLoading && list.length === 0 && (
            <EmptyState
              title="No freezers or fridges yet"
              description={
                canEdit
                  ? "Add one, then add boxes to it and put tubes in the boxes."
                  : "Only people who manage samples can add them. Ask a PI or lab admin."
              }
              action={
                canEdit ? (
                  <Button onClick={() => setUnitDialog("new")}>Add freezer or fridge</Button>
                ) : undefined
              }
            />
          )}
          <div className="grid gap-4 lg:grid-cols-2">
            {list.map((u) => (
              <section
                key={u.id}
                aria-labelledby={`unit-${u.id}`}
                className="grid content-start gap-3 rounded-lg border bg-card p-4"
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h2 id={`unit-${u.id}`} className="text-base font-semibold">
                      {u.name}
                    </h2>
                    <p className="text-xs text-muted-foreground">
                      {[kindLabel(u.kind), u.temperature, u.location, u.equipment?.name]
                        .filter(Boolean)
                        .join(" · ")}
                    </p>
                  </div>
                  {canEdit && (
                    <MoreMenu
                      label={`More for ${u.name}`}
                      items={[
                        {
                          label: "Add a box",
                          onSelect: () => setBoxDialog({ box: null, unit: u.id }),
                        },
                        { label: "Edit", onSelect: () => setUnitDialog(u) },
                        { label: "Delete", onSelect: () => setDeleting({ kind: "unit", unit: u }) },
                      ]}
                    />
                  )}
                </div>
                {u.boxes.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No boxes yet.</p>
                ) : (
                  <ul className="grid gap-1">
                    {u.boxes.map((b) => (
                      <li key={b.id} className="flex items-center gap-1">
                        <Button
                          variant={b.id === boxId ? "secondary" : "ghost"}
                          className="h-auto flex-1 justify-between py-2 text-left"
                          aria-pressed={b.id === boxId}
                          onClick={() => pickBox(b.id)}
                        >
                          <span>
                            {b.name}
                            {b.shelf && (
                              <span className="ml-2 text-xs text-muted-foreground">
                                {/^shelf\b/i.test(b.shelf) ? b.shelf : `Shelf ${b.shelf}`}
                              </span>
                            )}
                          </span>
                          <span className="text-xs text-muted-foreground">
                            {b.filled} of {b.rows * b.cols} filled
                          </span>
                        </Button>
                        {canEdit && (
                          <MoreMenu
                            label={`More for ${b.name}`}
                            items={[
                              {
                                label: "Edit",
                                onSelect: () => setBoxDialog({ box: b, unit: u.id }),
                              },
                              {
                                label: "Delete",
                                onSelect: () => setDeleting({ kind: "box", box: b }),
                              },
                            ]}
                          />
                        )}
                      </li>
                    ))}
                  </ul>
                )}
                {canEdit && u.boxes.length === 0 && (
                  <Button
                    variant="outline"
                    className="justify-self-start"
                    onClick={() => setBoxDialog({ box: null, unit: u.id })}
                  >
                    Add a box
                  </Button>
                )}
              </section>
            ))}
          </div>
          {boxId && (
            <BoxPanel
              key={boxId}
              labId={labId}
              boxId={boxId}
              units={list}
              canEdit={canEdit}
              actions={actions}
              highlight={params.get("tube")}
            />
          )}
        </div>
      )}
      {unitDialog && (
        <UnitDialog
          labId={labId}
          unit={unitDialog === "new" ? null : unitDialog}
          actions={actions}
          onClose={() => setUnitDialog(null)}
        />
      )}
      {boxDialog && (
        <BoxDialog
          box={boxDialog.box}
          unitId={boxDialog.unit}
          units={list}
          actions={actions}
          onClose={() => setBoxDialog(null)}
        />
      )}
      <ConfirmDelete
        open={!!deleting}
        name={deleting?.kind === "unit" ? deleting.unit.name : (deleting?.box.name ?? "")}
        noun={deleting?.kind === "unit" ? "freezer or fridge" : "box"}
        description={
          deleting?.kind === "unit"
            ? "A freezer or fridge that still has boxes can't be deleted. Delete its boxes first."
            : "A box that still has tubes can't be deleted. Take the tubes out first."
        }
        onClose={() => setDeleting(null)}
        onConfirm={confirmDelete}
      />
    </>
  );
}
