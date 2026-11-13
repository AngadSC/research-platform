import { useState, type FormEvent } from "react";
import { Link } from "react-router";
import { toast } from "sonner";
import { FormError } from "@/components/shared/FormError";
import { FormField } from "@/components/shared/FormField";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useOnboarding } from "@/hooks/admin";
import { useTrainingRequirements } from "@/hooks/training";
import { useMembers } from "@/hooks/workspace";
import type { OnboardingItem } from "@/lib/api-types";
import { formErrors, type FormErrors } from "@/lib/forms";
import { formValue, NativeSelect, Section } from "./common";

const KINDS = [
  { value: "new_member", label: "New member" },
  { value: "departing", label: "Departing member" },
] as const;

export function OnboardingSection({ labId }: { labId: string }) {
  const { list, create, remove, setDone } = useOnboarding(labId);
  const members = useMembers(labId).data ?? [];
  const trainings = useTrainingRequirements(labId).data ?? [];
  const [errors, setErrors] = useState<FormErrors>({ fields: {} });
  const [who, setWho] = useState("");
  const person = who || members[0]?.user.id || "";
  const items = list.data ?? [];
  const member = members.find((m) => m.user.id === person);

  async function add(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const fd = new FormData(form);
    const title = formValue(fd, "title");
    const url = formValue(fd, "url");
    if (!title) return setErrors({ fields: { title: "Enter a title" } });
    if (url && !url.startsWith("https://"))
      return setErrors({ fields: { url: "Enter a web address starting with https://" } });
    try {
      await create.mutateAsync({
        kind: formValue(fd, "kind") as OnboardingItem["kind"],
        title,
        description: formValue(fd, "description"),
        url,
        required: fd.get("required") === "on",
        training_requirement: formValue(fd, "training_requirement") || null,
      });
      setErrors({ fields: {} });
      form.reset();
      toast.success("Item added");
    } catch (err) {
      setErrors(formErrors(err, ["kind", "title", "url", "description"]));
    }
  }

  return (
    <Section
      title="Turnover and onboarding"
      description="Checklists for people joining or leaving the lab. Tick items off per person."
    >
      {members.length > 0 && (
        <div className="max-w-xs">
          <FormField label="Track progress for">
            {(p) => (
              <NativeSelect {...p} value={person} onChange={(e) => setWho(e.target.value)}>
                {members.map((m) => (
                  <option key={m.id} value={m.user.id}>
                    {m.user.display_name || m.user.email}
                  </option>
                ))}
              </NativeSelect>
            )}
          </FormField>
        </div>
      )}
      {KINDS.map((k) => {
        const rows = items.filter((i) => i.kind === k.value);
        return (
          <div key={k.value} className="grid gap-2">
            <h3 className="text-sm font-semibold">{k.label} checklist</h3>
            {rows.length === 0 && <p className="text-sm text-muted-foreground">No items yet.</p>}
            {rows.map((i) => (
              <div key={i.id} className="flex items-start gap-3 rounded-md border p-3">
                <input
                  type="checkbox"
                  className="mt-1"
                  aria-label={`${i.title} done`}
                  checked={
                    i.completed_user_ids.includes(person) ||
                    i.training_done_user_ids.includes(person)
                  }
                  disabled={!person || i.training_done_user_ids.includes(person)}
                  onChange={(e) =>
                    setDone.mutate(
                      { itemId: i.id, user: person, done: e.target.checked },
                      { onError: () => toast.error("Could not save.") },
                    )
                  }
                />
                <div className="min-w-0 flex-1">
                  <div className="font-medium">
                    {i.url ? (
                      <a
                        href={i.url}
                        target="_blank"
                        rel="noreferrer noopener"
                        className="underline-offset-4 hover:underline"
                      >
                        {i.title}
                      </a>
                    ) : (
                      i.title
                    )}{" "}
                    <span className="text-xs font-normal text-muted-foreground">
                      {i.required ? "Required" : "Optional"} · {i.completed_user_ids.length} of{" "}
                      {members.length} done
                    </span>
                  </div>
                  {i.description && (
                    <p className="text-sm text-muted-foreground">{i.description}</p>
                  )}
                  {i.training_requirement_name && (
                    <p className="text-xs text-muted-foreground">
                      Ticks itself once {i.training_requirement_name} training is recorded and not
                      expired. {i.training_done_user_ids.length} of {members.length} done that way.
                    </p>
                  )}
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label={`Delete ${i.title}`}
                  onClick={() =>
                    remove.mutate(i.id, { onError: () => toast.error("Could not delete.") })
                  }
                >
                  Delete
                </Button>
              </div>
            ))}
            {k.value === "departing" && member && (
              <Button variant="outline" size="sm" className="justify-self-start" asChild>
                <Link to={`/labs/${labId}/members/${member.id}/handover`}>
                  Handover for {member.user.display_name || member.user.email}
                </Link>
              </Button>
            )}
          </div>
        );
      })}
      <form
        onSubmit={add}
        noValidate
        aria-label="Add a checklist item"
        className="grid max-w-2xl gap-3"
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <FormField label="Checklist">
            {(p) => (
              <NativeSelect {...p} name="kind" defaultValue="new_member">
                {KINDS.map((k) => (
                  <option key={k.value} value={k.value}>
                    {k.label}
                  </option>
                ))}
              </NativeSelect>
            )}
          </FormField>
          <FormField label="Item title" error={errors.fields.title}>
            {(p) => <Input maxLength={200} {...p} name="title" />}
          </FormField>
        </div>
        <FormField label="Description (optional)">
          {(p) => <Input maxLength={2000} {...p} name="description" />}
        </FormField>
        <FormField
          label="Link (optional)"
          error={errors.fields.url}
          hint="Must start with https://"
        >
          {(p) => <Input maxLength={500} {...p} name="url" type="url" />}
        </FormField>
        {trainings.length > 0 && (
          <FormField
            label="Linked training (optional)"
            hint="Anyone with a current record counts as done."
          >
            {(p) => (
              <NativeSelect {...p} name="training_requirement" defaultValue="">
                <option value="">None</option>
                {trainings.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </NativeSelect>
            )}
          </FormField>
        )}
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" name="required" defaultChecked /> Required
        </label>
        <FormError message={errors.form} />
        <Button type="submit" className="justify-self-start" disabled={create.isPending}>
          Add item
        </Button>
      </form>
    </Section>
  );
}
