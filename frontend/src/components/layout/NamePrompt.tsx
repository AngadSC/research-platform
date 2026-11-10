import { useState, type FormEvent } from "react";
import { FormField } from "@/components/shared/FormField";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useMe, useUpdateMe } from "@/hooks/workspace";
import { formErrors } from "@/lib/forms";

/** Asks for a name once, for anyone who has none. It stays open until they give one. */
export function NamePrompt() {
  const me = useMe().data;
  const update = useUpdateMe();
  const [error, setError] = useState<string>();
  if (me?.display_name !== "") return null;

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const display_name = String(new FormData(e.currentTarget).get("name") ?? "").trim();
    if (!display_name) return setError("Enter your name");
    setError(undefined);
    try {
      await update.mutateAsync({ display_name });
    } catch (err) {
      const errors = formErrors(err, ["display_name"]);
      setError(errors.fields.display_name ?? errors.form);
    }
  }

  return (
    <Dialog open>
      <DialogContent
        showClose={false}
        onEscapeKeyDown={(e) => e.preventDefault()}
        onInteractOutside={(e) => e.preventDefault()}
      >
        <DialogTitle className="text-base font-semibold">What is your name?</DialogTitle>
        <DialogDescription className="text-sm text-muted-foreground">
          People in your labs see it next to your work. You can change it later in Settings.
        </DialogDescription>
        <form onSubmit={submit} noValidate className="grid gap-4">
          <FormField label="Your name" error={error}>
            {(p) => <Input {...p} name="name" autoComplete="name" maxLength={120} />}
          </FormField>
          <Button type="submit" className="justify-self-start" disabled={update.isPending}>
            Continue
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
