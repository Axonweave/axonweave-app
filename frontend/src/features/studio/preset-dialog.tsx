"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { ApiRequestError } from "@/lib/api/client";
import { presetsApi, type Preset, type PresetInput } from "@/lib/api/presets";
import { Field, NativeSelect, Textarea } from "@/features/study/ui-bits";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Present = edit this preset; absent = create from `initial`. */
  preset?: Preset | null;
  initial: PresetInput;
  onSaved: () => void;
}

function Form({ preset, initial, onOpenChange, onSaved }: Omit<Props, "open">) {
  const editing = !!preset;
  const [form, setForm] = useState<PresetInput>(
    preset
      ? {
          name: preset.name,
          description: preset.description ?? null,
          is_default: preset.is_default,
          language: preset.language ?? null,
          explanation_level: preset.explanation_level ?? null,
          summary_length: preset.summary_length ?? null,
          question_difficulty: preset.question_difficulty ?? null,
          include_examples: preset.include_examples,
          include_definitions: preset.include_definitions,
          include_source_references: preset.include_source_references,
        }
      : initial,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = <K extends keyof PresetInput>(key: K, value: PresetInput[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim()) {
      setError("Give the preset a name.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (preset) await presetsApi.replace(preset.id, form);
      else await presetsApi.create(form);
      onSaved();
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Could not save the preset.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-4">
      <DialogHeader>
        <DialogTitle>{editing ? "Edit preset" : "New preset"}</DialogTitle>
        <DialogDescription>
          Defaults for study material you generate. Anything you set while generating still wins.
        </DialogDescription>
      </DialogHeader>

      <Field label="Name" htmlFor="preset-name">
        <Input
          id="preset-name"
          value={form.name}
          maxLength={60}
          autoFocus
          onChange={(e) => set("name", e.target.value)}
        />
      </Field>
      <Field label="What is it for? (optional)" htmlFor="preset-desc">
        <Textarea
          id="preset-desc"
          rows={2}
          maxLength={200}
          value={form.description ?? ""}
          onChange={(e) => set("description", e.target.value || null)}
        />
      </Field>

      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Language" htmlFor="preset-lang" hint="Empty uses the default.">
          <Input
            id="preset-lang"
            maxLength={32}
            value={form.language ?? ""}
            onChange={(e) => set("language", e.target.value || null)}
          />
        </Field>
        <Field label="Explanation level" htmlFor="preset-level">
          <NativeSelect
            id="preset-level"
            value={form.explanation_level ?? ""}
            onChange={(e) =>
              set("explanation_level", (e.target.value || null) as PresetInput["explanation_level"])
            }
          >
            <option value="">Default</option>
            <option value="beginner">Beginner</option>
            <option value="intermediate">Intermediate</option>
            <option value="advanced">Advanced</option>
          </NativeSelect>
        </Field>
        <Field label="Summary length" htmlFor="preset-length">
          <NativeSelect
            id="preset-length"
            value={form.summary_length ?? ""}
            onChange={(e) =>
              set("summary_length", (e.target.value || null) as PresetInput["summary_length"])
            }
          >
            <option value="">Default</option>
            <option value="short">Short</option>
            <option value="medium">Medium</option>
            <option value="long">Long</option>
          </NativeSelect>
        </Field>
        <Field label="Question difficulty" htmlFor="preset-diff">
          <NativeSelect
            id="preset-diff"
            value={form.question_difficulty ?? ""}
            onChange={(e) =>
              set(
                "question_difficulty",
                (e.target.value || null) as PresetInput["question_difficulty"],
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
      </div>

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
              checked={form[key] ?? true}
              onChange={(e) => set(key, e.target.checked)}
            />
            {label}
          </label>
        ))}
      </fieldset>

      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={form.is_default ?? false}
          onChange={(e) => set("is_default", e.target.checked)}
        />
        Use this preset by default
      </label>

      {error ? (
        <p role="alert" className="text-destructive text-sm">
          {error}
        </p>
      ) : null}
      <DialogFooter>
        <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
          Cancel
        </Button>
        <Button type="submit" disabled={busy}>
          {busy ? "Saving…" : editing ? "Save changes" : "Create preset"}
        </Button>
      </DialogFooter>
    </form>
  );
}

export function PresetDialog({ open, onOpenChange, ...rest }: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        {/* remounts per open so the form always starts from the right values */}
        {open ? <Form {...rest} onOpenChange={onOpenChange} /> : null}
      </DialogContent>
    </Dialog>
  );
}
