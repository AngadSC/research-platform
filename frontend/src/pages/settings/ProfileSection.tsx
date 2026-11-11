import { useEffect, useRef, useState, type DragEvent, type FormEvent } from "react";
import { toast } from "sonner";
import { FormError } from "@/components/shared/FormError";
import { FormField } from "@/components/shared/FormField";
import { UserAvatar } from "@/components/shared/UserAvatar";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useMe, useSetAvatar, useUpdateMe } from "@/hooks/workspace";
import { prepareAvatar } from "@/lib/avatarImage";
import { formErrors } from "@/lib/forms";
import { cn } from "@/lib/utils";
import { Section } from "@/pages/admin/common";

const BIO_MAX = 500;

/** Name, pronouns, bio and picture. The picture is prepared in the browser and sent on Save. */
export function ProfileSection() {
  const { data: me } = useMe();
  const update = useUpdateMe();
  const setAvatar = useSetAvatar();
  const [errors, setErrors] = useState<Record<string, string | undefined>>({});
  const [bio, setBio] = useState<string>();
  const [staged, setStaged] = useState<{ blob: Blob; url: string }>();
  const [over, setOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const stagedUrl = staged?.url;
  useEffect(() => () => (stagedUrl ? URL.revokeObjectURL(stagedUrl) : undefined), [stagedUrl]);

  async function choose(file: File | undefined) {
    if (!file) return;
    try {
      const blob = await prepareAvatar(file);
      setStaged({ blob, url: URL.createObjectURL(blob) });
      setErrors((e) => ({ ...e, file: undefined }));
    } catch (err) {
      setErrors((e) => ({ ...e, file: err instanceof Error ? err.message : "Try another file." }));
    }
  }

  function drop(e: DragEvent) {
    e.preventDefault();
    setOver(false);
    void choose(e.dataTransfer.files[0]);
  }

  function remove() {
    if (staged) return setStaged(undefined);
    setAvatar.mutate(null, {
      onSuccess: () => toast.success("Picture removed"),
      onError: () => toast.error("Could not remove your picture."),
    });
  }

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const text = (name: string) => String(form.get(name) ?? "").trim();
    if (!text("name")) return setErrors({ name: "Enter your name" });
    setErrors({});
    try {
      if (staged) await setAvatar.mutateAsync(staged.blob);
      setStaged(undefined);
      await update.mutateAsync({
        display_name: text("name"),
        pronouns: text("pronouns"),
        bio: String(form.get("bio") ?? "").trim(),
      });
      toast.success("Profile saved");
    } catch (err) {
      const f = formErrors(err, ["display_name", "pronouns", "bio", "file"]);
      setErrors({
        name: f.fields.display_name,
        pronouns: f.fields.pronouns,
        bio: f.fields.bio,
        file: f.fields.file,
        form: f.form,
      });
    }
  }

  if (!me) {
    return (
      <Section title="Your profile">
        <Skeleton className="h-9 w-64" />
      </Section>
    );
  }
  const shown = staged ? { ...me, avatar_url: staged.url } : me;
  const hasPicture = !!staged || !!me.avatar_url;
  const length = (bio ?? me.bio ?? "").length;
  return (
    <Section title="Your profile" description="Shown to other people in your labs.">
      <form onSubmit={submit} noValidate className="grid max-w-md gap-4">
        <div
          onDragOver={(e) => (e.preventDefault(), setOver(true))}
          onDragLeave={() => setOver(false)}
          onDrop={drop}
          className={cn(
            "flex items-center gap-4 rounded-lg border border-dashed p-3",
            over && "border-primary bg-primary/10",
          )}
        >
          <UserAvatar user={shown} className="size-20 text-2xl" />
          <div className="grid gap-2">
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => input.current?.click()}
              >
                {hasPicture ? "Change picture" : "Choose a picture"}
              </Button>
              {hasPicture && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  disabled={setAvatar.isPending}
                  onClick={remove}
                >
                  Remove
                </Button>
              )}
            </div>
            <p className="text-xs text-muted-foreground">
              Or drop a picture here. It is cropped to a square and shrunk on your device before it
              is saved, which also removes any location it carries.
              {staged && " Press Save to keep it."}
            </p>
            <input
              ref={input}
              type="file"
              accept="image/*"
              aria-label="Profile picture file"
              className="sr-only"
              onChange={(e) => {
                void choose(e.target.files?.[0]);
                e.target.value = ""; // choosing the same file again still counts
              }}
            />
          </div>
        </div>
        <FormError message={errors.file} />
        <FormField label="Name" error={errors.name}>
          {(p) => (
            <Input
              maxLength={120}
              {...p}
              name="name"
              defaultValue={me.display_name}
              autoComplete="name"
            />
          )}
        </FormField>
        <FormField label="Pronouns" error={errors.pronouns} hint="Optional.">
          {(p) => (
            <Input
              maxLength={40}
              {...p}
              name="pronouns"
              defaultValue={me.pronouns}
              placeholder="she/her, he/him, they/them"
            />
          )}
        </FormField>
        <FormField label="Bio" error={errors.bio}>
          {(p) => (
            <>
              <Textarea
                maxLength={BIO_MAX}
                {...p}
                name="bio"
                rows={4}
                defaultValue={me.bio}
                placeholder="A line or two about you and your work."
                onChange={(e) => setBio(e.target.value)}
              />
              <p className="text-right text-xs text-muted-foreground" aria-live="polite">
                {length} / {BIO_MAX}
              </p>
            </>
          )}
        </FormField>
        <FormError message={errors.form} />
        <Button
          type="submit"
          className="justify-self-start"
          disabled={update.isPending || setAvatar.isPending}
        >
          Save
        </Button>
      </form>
    </Section>
  );
}
