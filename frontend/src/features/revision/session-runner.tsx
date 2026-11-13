"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { AsyncSection } from "@/components/ui/async-section";
import { useAsync } from "@/hooks/use-async";
import { useToast } from "@/hooks/use-toast";
import {
  formatDuration,
  newIdempotencyKey,
  ratingForKey,
  revisionApi,
  type Rating,
  type SessionCard,
} from "@/lib/api/revision";

const RATINGS: { rating: Rating; label: string; key: string }[] = [
  { rating: "again", label: "Again", key: "1" },
  { rating: "hard", label: "Hard", key: "2" },
  { rating: "good", label: "Good", key: "3" },
  { rating: "easy", label: "Easy", key: "4" },
];

/** Cards in the session that have not been reviewed yet, in server order. */
export function remainingCards(cards: SessionCard[]): SessionCard[] {
  return cards.filter((c) => !c.reviewed);
}

export function SessionRunner({ sessionId }: { sessionId: string }) {
  const { toast } = useToast();
  const session = useAsync(() => revisionApi.session(sessionId), [sessionId]);
  const [done, setDone] = useState<Set<string>>(new Set());
  const [flipped, setFlipped] = useState(false);
  const [busy, setBusy] = useState(false);
  const finishing = useRef(false);
  const shownAt = useRef<number | null>(null);

  const queue = useMemo(
    () => remainingCards(session.data?.cards ?? []).filter((c) => !done.has(c.card.id)),
    [session.data, done],
  );
  const current = queue[0];

  const rate = useCallback(
    async (rating: Rating) => {
      if (!current || busy || !flipped) return;
      setBusy(true);
      try {
        await revisionApi.review(current.card.id, {
          rating,
          idempotency_key: newIdempotencyKey(),
          session_id: sessionId,
          response_time_ms:
            shownAt.current === null
              ? undefined
              : Math.min(Date.now() - shownAt.current, 3_600_000),
        });
        setDone((prev) => new Set(prev).add(current.card.id));
        setFlipped(false);
        shownAt.current = Date.now();
      } catch {
        toast({ title: "Could not save that rating. Please try again.", variant: "destructive" });
      } finally {
        setBusy(false);
      }
    },
    [current, busy, flipped, sessionId, toast],
  );

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const target = e.target as HTMLElement | null;
      if (target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
      if (e.key === " ") {
        e.preventDefault();
        setFlipped((f) => !f);
        return;
      }
      const rating = ratingForKey(e.key);
      if (rating) void rate(rating);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [rate]);

  useEffect(() => {
    if (session.data && !current && !finishing.current && session.data.status === "active") {
      finishing.current = true;
      revisionApi
        .completeSession(sessionId)
        .then(() => session.reload())
        .catch(() => undefined);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current, session.data]);

  const total = session.data?.total_cards ?? 0;
  const reviewed = total - queue.length;

  return (
    <AsyncSection
      title="Revision session"
      loading={session.loading}
      error={session.error}
      onRetry={session.reload}
      isEmpty={false}
      empty={null}
    >
      {current ? (
        <div className="mx-auto max-w-2xl space-y-4">
          <p className="text-muted-foreground text-sm" aria-live="polite">
            Card {reviewed + 1} of {total}
          </p>
          <div
            className="border-border bg-card min-h-48 rounded-xl border p-6"
            data-testid="revision-card"
          >
            <p className="text-foreground whitespace-pre-wrap">{current.card.front}</p>
            {flipped ? (
              <div className="border-border mt-4 border-t pt-4">
                <p className="text-foreground whitespace-pre-wrap">{current.card.back}</p>
                {current.card.explanation ? (
                  <p className="text-muted-foreground mt-2 text-sm">{current.card.explanation}</p>
                ) : null}
              </div>
            ) : null}
          </div>
          {flipped ? (
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {RATINGS.map((r) => (
                <Button
                  key={r.rating}
                  variant="outline"
                  disabled={busy}
                  onClick={() => void rate(r.rating)}
                >
                  {r.label} <span className="text-muted-foreground ml-1 text-xs">({r.key})</span>
                </Button>
              ))}
            </div>
          ) : (
            <Button
              onClick={() => {
                shownAt.current ??= Date.now();
                setFlipped(true);
              }}
            >
              Show answer <span className="text-muted-foreground ml-1 text-xs">(space)</span>
            </Button>
          )}
          <p className="text-muted-foreground text-xs">
            Shortcuts: space shows the answer, then 1 Again, 2 Hard, 3 Good, 4 Easy.
          </p>
        </div>
      ) : (
        <div className="mx-auto max-w-2xl space-y-3" data-testid="session-complete">
          <p className="text-foreground text-lg font-medium">Session complete</p>
          <p className="text-muted-foreground text-sm">
            You reviewed {session.data?.summary?.reviewed_cards ?? reviewed} of {total} cards
            {session.data?.summary?.duration_seconds != null
              ? ` in ${formatDuration(session.data.summary.duration_seconds)}`
              : ""}
            .
          </p>
          <Link href="/revision" className="text-primary text-sm underline">
            Back to Revision
          </Link>
        </div>
      )}
    </AsyncSection>
  );
}
