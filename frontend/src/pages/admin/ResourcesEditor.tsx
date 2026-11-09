import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { FormError } from "@/components/shared/FormError";
import { FormField } from "@/components/shared/FormField";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { startersMessage, useLoadStarters, useResources } from "@/hooks/admin";
import { RESOURCE_CATEGORIES, type ResourceCategory } from "@/lib/api-types";
import { formErrors, type FormErrors } from "@/lib/forms";
import { formValue, NativeSelect, Section } from "./common";

const label = (c: string) => RESOURCE_CATEGORIES.find((x) => x.value === c)?.label ?? c;

/** Admin editor for the lab's institution links (D149). Every lab member reads them elsewhere. */
export function ResourcesEditor({ labId }: { labId: string }) {
  const { list, create, remove } = useResources(labId);
  const load = useLoadStarters(labId);
  const [errors, setErrors] = useState<FormErrors>({ fields: {} });

  async function add(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const fd = new FormData(form);
    const title = formValue(fd, "title");
    const url = formValue(fd, "url");
    if (!title) return setErrors({ fields: { title: "Enter a title" } });
    if (!url.startsWith("https://"))
      return setErrors({ fields: { url: "Enter a web address starting with https://" } });
    try {
      await create.mutateAsync({
        category: formValue(fd, "category") as ResourceCategory,
        title,
        url,
        description: formValue(fd, "description"),
      });
      setErrors({ fields: {} });
      form.reset();
      toast.success("Link added");
    } catch (err) {
      setErrors(formErrors(err, ["category", "title", "url", "description"]));
    }
  }

  return (
    <Section
      title="Institution resources"
      description="Links to your university's ethics, funding and data management pages, shown in each project's Workflow tab."
    >
      <div className="grid gap-1">
        <Button
          variant="outline"
          className="justify-self-start"
          disabled={load.isPending}
          onClick={() =>
            load.mutate(undefined, {
              onError: () => toast.error("Could not load your university's forms."),
            })
          }
        >
          Get my university's forms
        </Button>
        <p className="text-xs text-muted-foreground" role="status">
          {load.data
            ? startersMessage(load.data)
            : "Adds your institution's forms and the national funder links. Links you already have are left as they are, and a link you removed is added back."}
        </p>
      </div>
      {(list.data ?? []).length === 0 ? (
        <p className="text-sm text-muted-foreground">No links yet.</p>
      ) : (
        <ul className="grid gap-2">
          {list.data?.map((r) => (
            <li key={r.id} className="flex items-start justify-between gap-3 rounded-md border p-3">
              <div className="min-w-0">
                <a
                  href={r.url}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="font-medium underline-offset-4 hover:underline"
                >
                  {r.title}
                </a>
                <div className="text-xs text-muted-foreground">
                  {label(r.category)}
                  {r.description ? ` · ${r.description}` : ""}
                </div>
              </div>
              <Button
                variant="ghost"
                size="sm"
                aria-label={`Remove ${r.title}`}
                onClick={() =>
                  remove.mutate(r.id, {
                    onSuccess: () => toast.success("Link removed"),
                    onError: () => toast.error("Could not remove the link."),
                  })
                }
              >
                Remove
              </Button>
            </li>
          ))}
        </ul>
      )}
      <form onSubmit={add} noValidate aria-label="Add a link" className="grid max-w-2xl gap-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <FormField label="Category" error={errors.fields.category}>
            {(p) => (
              <NativeSelect {...p} name="category" defaultValue="ethics">
                {RESOURCE_CATEGORIES.map((c) => (
                  <option key={c.value} value={c.value}>
                    {c.label}
                  </option>
                ))}
              </NativeSelect>
            )}
          </FormField>
          <FormField label="Link title" error={errors.fields.title}>
            {(p) => <Input {...p} name="title" />}
          </FormField>
        </div>
        <FormField label="Link address" error={errors.fields.url} hint="Must start with https://">
          {(p) => <Input {...p} name="url" type="url" />}
        </FormField>
        <FormField label="Short description (optional)" error={errors.fields.description}>
          {(p) => <Input {...p} name="description" />}
        </FormField>
        <FormError message={errors.form} />
        <Button type="submit" className="justify-self-start" disabled={create.isPending}>
          Add link
        </Button>
      </form>
    </Section>
  );
}
