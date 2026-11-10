import { useState, type FormEvent } from "react";
import { Trash2 } from "lucide-react";
import { FormField } from "@/components/shared/FormField";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useMe } from "@/hooks/workspace";
import {
  MAX_CUSTOM_THEMES,
  paletteProblems,
  paletteVars,
  type CustomTheme,
  type Palette,
} from "@/lib/customTheme";
import { useSaveCustomThemes, useTheme } from "@/lib/theme";
import { Section } from "@/pages/admin/common";

const START: Palette = { background: "#ffffff", text: "#18181b", accent: "#4f46e5" };
const COLOURS = [
  ["background", "Background"],
  ["text", "Text"],
  ["accent", "Accent"],
] as const;

/** Settings > Appearance: make, list and remove your own colour themes (D224). */
export function CustomThemes() {
  const me = useMe().data as { preferences?: { custom_themes?: CustomTheme[] } } | undefined;
  const themes = me?.preferences?.custom_themes ?? [];
  const { theme } = useTheme();
  const save = useSaveCustomThemes();
  const [palette, setPalette] = useState(START);
  const [name, setName] = useState("");
  const problems = paletteProblems(palette);
  const full = themes.length >= MAX_CUSTOM_THEMES;

  function add(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const id = Date.now().toString(36);
    save.mutate(
      { custom_themes: [...themes, { ...palette, id, name: name.trim() }], theme: `custom:${id}` },
      { onSuccess: () => setName("") },
    );
  }

  function remove(t: CustomTheme) {
    save.mutate({
      custom_themes: themes.filter((x) => x.id !== t.id),
      theme: theme === `custom:${t.id}` ? "system" : theme,
    });
  }

  return (
    <Section
      title="Your colour themes"
      description="Pick your own colours. Only you see them, and text must stay easy to read."
    >
      {themes.length > 0 && (
        <ul className="grid gap-2">
          {themes.map((t) => (
            <li key={t.id} className="flex items-center justify-between gap-3 text-sm">
              <span className="flex min-w-0 items-center gap-2">
                <span
                  aria-hidden
                  className="size-5 shrink-0 rounded-full border"
                  style={{ background: t.background, boxShadow: `inset -8px 0 0 ${t.accent}` }}
                />
                <span className="truncate">{t.name}</span>
              </span>
              <Button
                variant="ghost"
                size="icon"
                aria-label={`Delete ${t.name}`}
                disabled={save.isPending}
                onClick={() => remove(t)}
              >
                <Trash2 aria-hidden />
              </Button>
            </li>
          ))}
        </ul>
      )}
      <form className="grid gap-4" onSubmit={add} aria-label="Make a colour theme">
        <FormField label="Theme name">
          {(p) => (
            <Input
              {...p}
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={40}
              className="max-w-xs"
            />
          )}
        </FormField>
        <div className="flex flex-wrap gap-4">
          {COLOURS.map(([key, label]) => (
            <FormField key={key} label={label}>
              {(p) => (
                <input
                  {...p}
                  type="color"
                  value={palette[key]}
                  onChange={(e) => setPalette({ ...palette, [key]: e.target.value })}
                  className="h-9 w-16 rounded-md border border-input bg-background p-1 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                />
              )}
            </FormField>
          ))}
        </div>
        <div
          aria-label="Preview"
          role="group"
          className="grid gap-2 rounded-md border p-4 text-sm"
          style={{ background: palette.background, color: palette.text }}
        >
          <p>This is how your text will look.</p>
          <span
            className="w-fit rounded-md px-3 py-1.5 font-medium"
            style={{
              background: palette.accent,
              color: paletteVars(palette)["--primary-foreground"],
            }}
          >
            A button
          </span>
        </div>
        {problems.map((p) => (
          <p key={p} role="alert" className="text-sm text-destructive">
            {p}
          </p>
        ))}
        {full && (
          <p className="text-sm text-muted-foreground">
            You have {MAX_CUSTOM_THEMES} themes. Delete one to add another.
          </p>
        )}
        <Button
          type="submit"
          className="w-fit"
          disabled={save.isPending || problems.length > 0 || full || !name.trim()}
        >
          Save and use
        </Button>
      </form>
    </Section>
  );
}
