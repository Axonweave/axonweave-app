"use client";

import { useState } from "react";
import { Check, Pencil, Plus, Star, Trash2, WandSparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorDisplay } from "@/components/ui/error-display";
import { LoadingSpinner } from "@/components/ui/loading";
import { useAsync } from "@/hooks/use-async";
import { useToast } from "@/hooks/use-toast";
import { ApiRequestError } from "@/lib/api/client";
import { presetsApi, type Preset, type PresetInput } from "@/lib/api/presets";
import { Chip } from "@/features/study/ui-bits";
import { BLANK_PRESET, GOALS } from "./goals";
import { PresetDialog } from "./preset-dialog";

const label = (v: string | null | undefined, map: Record<string, string>) => (v ? map[v] : null);

function summary(p: Preset): string[] {
  return [
    p.language,
    label(p.explanation_level, {
      beginner: "Beginner",
      intermediate: "Intermediate",
      advanced: "Advanced",
    }),
    label(p.summary_length, {
      short: "Short summaries",
      medium: "Medium summaries",
      long: "Long summaries",
    }),
    label(p.question_difficulty, {
      easy: "Easy questions",
      medium: "Medium questions",
      hard: "Hard questions",
      mixed: "Mixed questions",
    }),
    p.include_examples ? "Examples" : null,
    p.include_definitions ? "Definitions" : null,
    p.include_source_references ? "Sources" : null,
  ].filter((x): x is string => !!x);
}

export function StudioPage() {
  const { toast } = useToast();
  const presets = useAsync(() => presetsApi.list(), []);
  const [dialog, setDialog] = useState<{ preset: Preset | null; initial: PresetInput } | null>(
    null,
  );
  const [deleting, setDeleting] = useState<Preset | null>(null);

  const list = presets.data ?? [];
  const fail = (title: string, err: unknown) =>
    toast({
      title,
      description: err instanceof ApiRequestError ? err.message : undefined,
      variant: "destructive",
    });

  async function makeDefault(p: Preset) {
    try {
      await presetsApi.makeDefault(p.id);
      toast({ title: `“${p.name}” is now your default` });
      presets.reload();
    } catch (err) {
      fail("Could not change the default", err);
    }
  }

  async function remove(p: Preset) {
    try {
      await presetsApi.remove(p.id);
      toast({ title: `“${p.name}” deleted` });
      presets.reload();
    } catch (err) {
      fail("Could not delete the preset", err);
    }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-8">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <span className="bg-sidebar-primary/10 text-sidebar-primary flex h-11 w-11 shrink-0 items-center justify-center rounded-xl">
            <WandSparkles className="h-5 w-5" aria-hidden="true" />
          </span>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Study Studio</h1>
            <p className="text-muted-foreground mt-1 max-w-xl text-sm">
              Set up how you like to learn. Save presets for different goals and use them when you
              generate summaries, flashcards and quizzes.
            </p>
          </div>
        </div>
        <Button onClick={() => setDialog({ preset: null, initial: BLANK_PRESET })}>
          <Plus aria-hidden="true" />
          New preset
        </Button>
      </header>

      <section aria-labelledby="goals-heading" className="space-y-3">
        <div>
          <h2 id="goals-heading" className="text-base font-semibold">
            Start from a goal
          </h2>
          <p className="text-muted-foreground text-sm">
            Pick what you are working towards. You can review and change everything before saving.
          </p>
        </div>
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {GOALS.map((g) => (
            <li key={g.id}>
              <button
                type="button"
                onClick={() => setDialog({ preset: null, initial: g.preset })}
                className="bg-card hover:border-foreground/25 hover:bg-muted/30 focus-visible:ring-ring group flex h-full w-full flex-col items-start gap-1 rounded-xl border p-4 text-left transition-colors focus-visible:ring-2 focus-visible:outline-none"
              >
                <span className="text-sm font-semibold">{g.title}</span>
                <span className="text-muted-foreground text-xs">{g.blurb}</span>
                <span className="text-primary mt-2 text-xs font-medium opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100">
                  Use this goal
                </span>
              </button>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="presets-heading" className="space-y-3">
        <h2 id="presets-heading" className="text-base font-semibold">
          Your presets
          {presets.data ? (
            <span className="text-muted-foreground ml-2 text-sm font-normal">{list.length}</span>
          ) : null}
        </h2>
        {presets.loading && !presets.data ? (
          <div className="flex justify-center py-10">
            <LoadingSpinner />
          </div>
        ) : presets.error ? (
          <ErrorDisplay message={presets.error} onRetry={presets.reload} />
        ) : list.length === 0 ? (
          <EmptyState
            title="No presets yet"
            description="Choose a goal above, or create your own. A preset remembers your language, depth and difficulty."
            action={
              <Button onClick={() => setDialog({ preset: null, initial: BLANK_PRESET })}>
                Create a preset
              </Button>
            }
          />
        ) : (
          <ul className="grid gap-3 md:grid-cols-2">
            {list.map((p) => (
              <li key={p.id} className="bg-card flex flex-col gap-3 rounded-xl border p-4">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <h3 className="flex flex-wrap items-center gap-2 font-semibold">
                      <span className="truncate">{p.name}</span>
                      {p.is_default ? (
                        <span className="bg-sidebar-primary/10 text-sidebar-primary inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium">
                          <Check className="h-3 w-3" aria-hidden="true" />
                          Default
                        </span>
                      ) : null}
                    </h3>
                    {p.description ? (
                      <p className="text-muted-foreground mt-0.5 line-clamp-2 text-sm">
                        {p.description}
                      </p>
                    ) : null}
                  </div>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {summary(p).map((s) => (
                    <Chip key={s}>{s}</Chip>
                  ))}
                </div>
                <div className="mt-auto flex flex-wrap items-center gap-1 pt-1">
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => setDialog({ preset: p, initial: BLANK_PRESET })}
                  >
                    <Pencil aria-hidden="true" />
                    Edit
                  </Button>
                  {!p.is_default ? (
                    <Button size="sm" variant="ghost" onClick={() => void makeDefault(p)}>
                      <Star aria-hidden="true" />
                      Make default
                    </Button>
                  ) : null}
                  <Button
                    size="sm"
                    variant="ghost"
                    className="text-destructive ml-auto"
                    onClick={() => setDeleting(p)}
                    aria-label={`Delete ${p.name}`}
                  >
                    <Trash2 aria-hidden="true" />
                    Delete
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <PresetDialog
        open={dialog !== null}
        onOpenChange={(o) => !o && setDialog(null)}
        preset={dialog?.preset ?? null}
        initial={dialog?.initial ?? BLANK_PRESET}
        onSaved={() => {
          setDialog(null);
          toast({ title: "Preset saved" });
          presets.reload();
        }}
      />
      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(o) => {
          if (!o) setDeleting(null);
        }}
        title="Delete preset?"
        description={
          deleting
            ? `“${deleting.name}” will be removed. Material already generated is not affected.`
            : ""
        }
        confirmLabel="Delete preset"
        destructive
        onConfirm={() => {
          const p = deleting;
          setDeleting(null);
          if (p) void remove(p);
        }}
      />
    </div>
  );
}
