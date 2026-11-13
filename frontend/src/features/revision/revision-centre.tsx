"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { AsyncSection } from "@/components/ui/async-section";
import { EmptyState } from "@/components/ui/empty-state";
import { useAsync } from "@/hooks/use-async";
import { useToast } from "@/hooks/use-toast";
import { ApiRequestError } from "@/lib/api/client";
import { recommendationsApi, revisionApi } from "@/lib/api/revision";

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="border-border rounded-lg border p-3">
      <p className="text-muted-foreground text-xs">{label}</p>
      <p className="text-foreground text-2xl font-semibold">{value}</p>
    </div>
  );
}

export function RevisionCentre() {
  const router = useRouter();
  const { toast } = useToast();
  const summary = useAsync(() => revisionApi.summary(), []);
  const recs = useAsync(() => recommendationsApi.revision(), []);
  const [starting, setStarting] = useState(false);
  const s = summary.data;

  async function start() {
    setStarting(true);
    try {
      const session = await revisionApi.startSession({});
      router.push(`/revision/session/${session.id}`);
    } catch (err) {
      const message =
        err instanceof ApiRequestError && err.status === 409
          ? "There is nothing to revise right now."
          : "Could not start a session. Please try again.";
      toast({ title: message, variant: "destructive" });
      setStarting(false);
    }
  }

  async function resolve(id: string, action: "complete" | "dismiss") {
    try {
      await (action === "complete"
        ? recommendationsApi.complete(id)
        : recommendationsApi.dismiss(id));
      recs.reload();
    } catch {
      toast({ title: "Could not update the suggestion.", variant: "destructive" });
    }
  }

  const nothing = !!s && s.total_cards === 0;
  return (
    <div className="min-w-0 space-y-8">
      <AsyncSection
        title="Today"
        loading={summary.loading}
        error={summary.error}
        onRetry={summary.reload}
        isEmpty={nothing}
        empty={
          <EmptyState
            title="No flashcards yet"
            description="Generate a flashcard set from a document in Study materials and it will appear here for spaced revision."
          />
        }
        action={
          <Button onClick={start} disabled={starting || !s || s.due_today + s.new === 0}>
            {starting ? "Starting…" : "Start revision session"}
          </Button>
        }
      >
        {s ? (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Stat label="Due today" value={s.due_today} />
              <Stat label="Overdue" value={s.overdue} />
              <Stat label="New" value={s.new} />
              <Stat label="Reviewed today" value={s.reviewed_today} />
            </div>
            <p className="text-muted-foreground text-xs">
              {s.total_cards} cards in total · {s.learning} learning · {s.review} in review ·{" "}
              {s.suspended} suspended · times shown in {s.timezone}
            </p>
          </div>
        ) : null}
      </AsyncSection>

      <AsyncSection
        title="Suggested revision"
        loading={recs.loading}
        error={recs.error}
        onRetry={recs.reload}
        isEmpty={(recs.data?.items.length ?? 0) === 0}
        empty={
          <p className="text-muted-foreground text-sm">
            Nothing to suggest yet. Suggestions appear as you take quizzes and review cards.
          </p>
        }
      >
        <ul className="space-y-2">
          {recs.data?.items.map((r) => (
            <li
              key={r.id}
              className="border-border flex flex-wrap items-center justify-between gap-2 rounded-lg border p-3"
            >
              <div className="min-w-0">
                <p className="text-foreground text-sm">{r.reason}</p>
                <p className="text-muted-foreground text-xs capitalize">{r.priority} priority</p>
              </div>
              <div className="flex gap-2">
                <Button size="sm" variant="outline" onClick={() => resolve(r.id, "complete")}>
                  Done
                </Button>
                <Button size="sm" variant="ghost" onClick={() => resolve(r.id, "dismiss")}>
                  Dismiss
                </Button>
              </div>
            </li>
          ))}
        </ul>
        {recs.data ? <p className="text-muted-foreground mt-2 text-xs">{recs.data.note}</p> : null}
      </AsyncSection>
    </div>
  );
}
