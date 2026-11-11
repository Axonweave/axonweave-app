"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAsync } from "@/hooks/use-async";
import { useToast } from "@/hooks/use-toast";
import { ApiRequestError } from "@/lib/api/client";
import { studyApi, type StudyPreferences } from "@/lib/api/study";
import { Field, NativeSelect } from "./ui-bits";

/** Defaults for new generations. A value you set in the generate dialog always wins. */
export function PreferencesForm() {
  const { toast } = useToast();
  const prefs = useAsync(() => studyApi.preferences(), []);
  const [form, setForm] = useState<StudyPreferences | null>(null);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (prefs.data) setForm(prefs.data);
  }, [prefs.data]);

  if (prefs.loading && !form) return <p className="text-muted-foreground text-sm">Loading…</p>;
  if (!form)
    return (
      <p role="alert" className="text-destructive text-sm">
        Could not load your study preferences.
      </p>
    );
  const set = <K extends keyof StudyPreferences>(key: K, value: StudyPreferences[K]) =>
    setForm((f) => (f ? { ...f, [key]: value } : f));

  async function save() {
    if (!form) return;
    setSaving(true);
    try {
      setForm(await studyApi.savePreferences(form));
      toast({ title: "Study preferences saved" });
    } catch (err) {
      toast({
        title: "Could not save",
        description: err instanceof ApiRequestError ? err.message : undefined,
        variant: "destructive",
      });
    } finally {
      setSaving(false);
    }
  }

  return (
    <form
      className="max-w-xl space-y-4"
      aria-label="Study preferences"
      onSubmit={(e) => {
        e.preventDefault();
        void save();
      }}
    >
      <Field
        label="Language"
        htmlFor="pref-lang"
        hint="Language for generated material. Leave empty for the default."
      >
        <Input
          id="pref-lang"
          maxLength={40}
          value={form.language ?? ""}
          onChange={(e) => set("language", e.target.value || null)}
        />
      </Field>
      <Field label="Explanation level" htmlFor="pref-level">
        <NativeSelect
          id="pref-level"
          value={form.explanation_level ?? ""}
          onChange={(e) =>
            set(
              "explanation_level",
              (e.target.value || null) as StudyPreferences["explanation_level"],
            )
          }
        >
          <option value="">Default</option>
          <option value="beginner">Beginner</option>
          <option value="intermediate">Intermediate</option>
          <option value="advanced">Advanced</option>
        </NativeSelect>
      </Field>
      <Field label="Summary length" htmlFor="pref-len">
        <NativeSelect
          id="pref-len"
          value={form.summary_length ?? ""}
          onChange={(e) =>
            set("summary_length", (e.target.value || null) as StudyPreferences["summary_length"])
          }
        >
          <option value="">Default</option>
          <option value="short">Short</option>
          <option value="medium">Medium</option>
          <option value="long">Long</option>
        </NativeSelect>
      </Field>
      <Field label="Question difficulty" htmlFor="pref-diff">
        <NativeSelect
          id="pref-diff"
          value={form.question_difficulty ?? ""}
          onChange={(e) =>
            set(
              "question_difficulty",
              (e.target.value || null) as StudyPreferences["question_difficulty"],
            )
          }
        >
          <option value="">Default</option>
          <option value="easy">Easy</option>
          <option value="medium">Medium</option>
          <option value="hard">Hard</option>
          <option value="mixed">Mixed</option>
        </NativeSelect>
      </Field>
      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">Include in generated material</legend>
        {(
          [
            ["include_examples", "Examples"],
            ["include_definitions", "Definitions"],
            ["include_source_references", "Source references"],
          ] as const
        ).map(([key, label]) => (
          <label key={key} className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={form[key]}
              onChange={(e) => set(key, e.target.checked)}
            />
            {label}
          </label>
        ))}
      </fieldset>
      <Button type="submit" disabled={saving}>
        {saving ? "Saving…" : "Save preferences"}
      </Button>
    </form>
  );
}
