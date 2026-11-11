"use client";

import { useCallback, useEffect, useState } from "react";
import { ArrowDown, ArrowUp, Plus, RefreshCw, Shuffle, Star, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { useAsync } from "@/hooks/use-async";
import { useToast } from "@/hooks/use-toast";
import { ApiRequestError } from "@/lib/api/client";
import { studyApi, type Flashcard, type FlashcardSet, type MaterialSource } from "@/lib/api/study";
import { JobProgress } from "./job-progress";
import { SourceRefs } from "./sources";
import { Chip, Field, Textarea } from "./ui-bits";
import { useJob } from "./use-job";

/** Source references on a card are stored as {rank, document_id, page_number ...} objects. */
function cardRefs(card: Flashcard): { refs: number[]; sources: MaterialSource[] } {
  const sources = (card.source_references ?? []) as unknown as MaterialSource[];
  return { refs: sources.map((s) => s.rank), sources };
}

export function shuffled<T>(items: T[], random: () => number = Math.random): T[] {
  const out = [...items];
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

/* ───────── study mode ───────── */

export function StudyMode({ cards, unavailable }: { cards: Flashcard[]; unavailable: string[] }) {
  const [order, setOrder] = useState(cards);
  const [index, setIndex] = useState(0);
  const [flipped, setFlipped] = useState(false);
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setOrder(cards);
    setIndex((i) => Math.min(i, Math.max(0, cards.length - 1)));
  }, [cards]);

  const go = useCallback(
    (delta: number) => {
      setFlipped(false);
      setIndex((i) => Math.min(order.length - 1, Math.max(0, i + delta)));
    },
    [order.length],
  );

  if (order.length === 0)
    return <p className="text-muted-foreground text-sm">This deck has no cards yet.</p>;
  const card = order[index];
  const { refs, sources } = cardRefs(card);
  return (
    <div
      className="space-y-4"
      onKeyDown={(e) => {
        if (e.target instanceof HTMLElement && /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName))
          return;
        if (e.key === "ArrowRight") go(1);
        else if (e.key === "ArrowLeft") go(-1);
      }}
    >
      <div className="flex items-center justify-between gap-2">
        <p className="text-muted-foreground text-sm" aria-live="polite">
          Card {index + 1} of {order.length}
        </p>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => {
            setOrder(shuffled(cards));
            setIndex(0);
            setFlipped(false);
          }}
        >
          <Shuffle aria-hidden="true" />
          Shuffle
        </Button>
      </div>
      <div
        role="progressbar"
        aria-label="Deck progress"
        aria-valuemin={1}
        aria-valuemax={order.length}
        aria-valuenow={index + 1}
        className="bg-muted h-1.5 overflow-hidden rounded"
      >
        <div
          className="bg-primary h-full"
          style={{ width: `${((index + 1) / order.length) * 100}%` }}
        />
      </div>
      <button
        type="button"
        onClick={() => setFlipped((f) => !f)}
        aria-pressed={flipped}
        aria-label={
          flipped
            ? "Showing the answer. Press to show the question."
            : "Showing the question. Press to show the answer."
        }
        className="border-border bg-card hover:bg-muted/40 focus-visible:ring-ring/50 flex min-h-48 w-full flex-col items-center justify-center gap-2 rounded-xl border p-6 text-center focus-visible:ring-3"
        data-testid="flashcard-face"
      >
        <span className="text-muted-foreground text-xs uppercase">
          {flipped ? "Answer" : "Question"}
        </span>
        <span className="text-lg break-words whitespace-pre-wrap">
          {flipped ? card.back : card.front}
        </span>
        {flipped && card.explanation ? (
          <span className="text-muted-foreground text-sm break-words">{card.explanation}</span>
        ) : null}
      </button>
      <SourceRefs refs={refs} sources={sources} unavailable={unavailable} />
      <div className="flex justify-between gap-2">
        <Button type="button" variant="outline" onClick={() => go(-1)} disabled={index === 0}>
          Previous
        </Button>
        <Button type="button" variant="outline" onClick={() => setFlipped((f) => !f)}>
          Flip
        </Button>
        <Button
          type="button"
          variant="outline"
          onClick={() => go(1)}
          disabled={index === order.length - 1}
        >
          Next
        </Button>
      </div>
      <p className="text-muted-foreground text-xs">
        Tip: press the card to flip it, or use the left and right arrow keys to move.
      </p>
    </div>
  );
}

/* ───────── card editor row ───────── */

function CardRow({
  card,
  position,
  total,
  selected,
  onSelect,
  onSaved,
  onDelete,
  onMove,
}: {
  card: Flashcard;
  position: number;
  total: number;
  selected: boolean;
  onSelect: (on: boolean) => void;
  onSaved: () => void;
  onDelete: () => void;
  onMove: (delta: number) => void;
}) {
  const { toast } = useToast();
  const [editing, setEditing] = useState(false);
  const [front, setFront] = useState(card.front);
  const [back, setBack] = useState(card.back);
  const [explanation, setExplanation] = useState(card.explanation ?? "");
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setError(null);
    try {
      await studyApi.editCard(card.id, { front, back, explanation: explanation || null });
      setEditing(false);
      onSaved();
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Could not save.");
    }
  }
  async function favourite() {
    try {
      await studyApi.editCard(card.id, { is_favourite: !card.is_favourite });
      onSaved();
    } catch {
      toast({ title: "Could not update the card", variant: "destructive" });
    }
  }

  return (
    <li className="border-border space-y-2 rounded-lg border p-3">
      <div className="flex items-start gap-2">
        <input
          type="checkbox"
          className="mt-1.5"
          aria-label={`Select card ${position + 1}`}
          checked={selected}
          onChange={(e) => onSelect(e.target.checked)}
        />
        <div className="min-w-0 flex-1 space-y-1">
          {editing ? (
            <div className="space-y-2">
              <Field label="Front" htmlFor={`f-${card.id}`}>
                <Textarea
                  id={`f-${card.id}`}
                  rows={2}
                  value={front}
                  maxLength={400}
                  onChange={(e) => setFront(e.target.value)}
                />
              </Field>
              <Field label="Back" htmlFor={`b-${card.id}`}>
                <Textarea
                  id={`b-${card.id}`}
                  rows={3}
                  value={back}
                  maxLength={1200}
                  onChange={(e) => setBack(e.target.value)}
                />
              </Field>
              <Field label="Explanation (optional)" htmlFor={`e-${card.id}`}>
                <Textarea
                  id={`e-${card.id}`}
                  rows={2}
                  value={explanation}
                  onChange={(e) => setExplanation(e.target.value)}
                />
              </Field>
              {error ? (
                <p role="alert" className="text-destructive text-sm">
                  {error}
                </p>
              ) : null}
              <div className="flex gap-2">
                <Button type="button" size="sm" onClick={save}>
                  Save card
                </Button>
                <Button type="button" size="sm" variant="outline" onClick={() => setEditing(false)}>
                  Cancel
                </Button>
              </div>
            </div>
          ) : (
            <>
              <p className="font-medium break-words">{card.front}</p>
              <p className="text-sm break-words">{card.back}</p>
              {card.explanation ? (
                <p className="text-muted-foreground text-sm break-words">{card.explanation}</p>
              ) : null}
              <div className="flex flex-wrap gap-1.5">
                <Chip>{card.card_type.replace(/_/g, " ")}</Chip>
                <Chip>{card.difficulty}</Chip>
                {card.origin === "manual" ? <Chip>Added by you</Chip> : null}
              </div>
            </>
          )}
        </div>
        {!editing ? (
          <div className="flex shrink-0 flex-wrap justify-end gap-0.5">
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label={`Move card ${position + 1} up`}
              disabled={position === 0}
              onClick={() => onMove(-1)}
            >
              <ArrowUp aria-hidden="true" />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label={`Move card ${position + 1} down`}
              disabled={position === total - 1}
              onClick={() => onMove(1)}
            >
              <ArrowDown aria-hidden="true" />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-pressed={card.is_favourite}
              aria-label={
                card.is_favourite
                  ? `Unfavourite card ${position + 1}`
                  : `Favourite card ${position + 1}`
              }
              onClick={favourite}
            >
              <Star aria-hidden="true" className={card.is_favourite ? "fill-current" : ""} />
            </Button>
            <Button type="button" variant="outline" size="sm" onClick={() => setEditing(true)}>
              Edit
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label={`Delete card ${position + 1}`}
              onClick={onDelete}
            >
              <Trash2 aria-hidden="true" />
            </Button>
          </div>
        ) : null}
      </div>
    </li>
  );
}

/* ───────── deck ───────── */

export function FlashcardDeck({ deckId, unavailable }: { deckId: string; unavailable: string[] }) {
  const { toast } = useToast();
  const [mode, setMode] = useState<"study" | "edit">("study");
  const deck = useAsync(() => studyApi.deck(deckId), [deckId]);
  const [selected, setSelected] = useState<string[]>([]);
  const [adding, setAdding] = useState(false);
  const [newFront, setNewFront] = useState("");
  const [newBack, setNewBack] = useState("");
  const [addError, setAddError] = useState<string | null>(null);
  const [toDelete, setToDelete] = useState<Flashcard | null>(null);
  const [regenJob, setRegenJob] = useState<string | null>(null);
  const reload = deck.reload;

  const data: FlashcardSet | null = deck.data;
  const cards = data?.cards ?? [];

  async function move(index: number, delta: number) {
    const ids = cards.map((c) => c.id);
    const target = index + delta;
    if (target < 0 || target >= ids.length) return;
    [ids[index], ids[target]] = [ids[target], ids[index]];
    try {
      await studyApi.reorderCards(deckId, ids);
      reload();
    } catch {
      toast({ title: "Could not reorder", variant: "destructive" });
    }
  }

  async function add() {
    setAddError(null);
    try {
      await studyApi.addCard(deckId, { front: newFront, back: newBack });
      setNewFront("");
      setNewBack("");
      setAdding(false);
      reload();
    } catch (err) {
      setAddError(err instanceof ApiRequestError ? err.message : "Could not add the card.");
    }
  }

  async function regenerate() {
    try {
      const job = await studyApi.regenerateCards(deckId, selected);
      setRegenJob(job.id);
    } catch (err) {
      toast({
        title: "Could not regenerate",
        description: err instanceof ApiRequestError ? err.message : undefined,
        variant: "destructive",
      });
    }
  }

  if (deck.loading && !data) return <p className="text-muted-foreground text-sm">Loading cards…</p>;
  if (deck.error || !data)
    return (
      <p role="alert" className="text-destructive text-sm">
        Could not load this deck.
      </p>
    );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2" role="tablist" aria-label="Deck view">
        {(["study", "edit"] as const).map((m) => (
          <Button
            key={m}
            type="button"
            role="tab"
            aria-selected={mode === m}
            variant={mode === m ? "default" : "outline"}
            size="sm"
            onClick={() => setMode(m)}
          >
            {m === "study" ? "Study" : "Edit cards"}
          </Button>
        ))}
        <span className="text-muted-foreground text-sm">{cards.length} cards</span>
      </div>

      {mode === "study" ? (
        <StudyMode cards={cards} unavailable={unavailable} />
      ) : (
        <div className="space-y-4">
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="outline" size="sm" onClick={() => setAdding((a) => !a)}>
              <Plus aria-hidden="true" />
              Add card
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={selected.length === 0 || regenJob !== null}
              onClick={regenerate}
            >
              <RefreshCw aria-hidden="true" />
              Regenerate selected ({selected.length})
            </Button>
          </div>
          {adding ? (
            <div className="border-border space-y-2 rounded-lg border p-3">
              <Field label="Front" htmlFor="new-front">
                <Input
                  id="new-front"
                  value={newFront}
                  maxLength={400}
                  onChange={(e) => setNewFront(e.target.value)}
                />
              </Field>
              <Field label="Back" htmlFor="new-back">
                <Textarea
                  id="new-back"
                  rows={3}
                  value={newBack}
                  maxLength={1200}
                  onChange={(e) => setNewBack(e.target.value)}
                />
              </Field>
              {addError ? (
                <p role="alert" className="text-destructive text-sm">
                  {addError}
                </p>
              ) : null}
              <Button
                type="button"
                size="sm"
                onClick={add}
                disabled={newFront.trim().length < 5 || !newBack.trim()}
              >
                Save new card
              </Button>
            </div>
          ) : null}
          {regenJob ? (
            <CardRegeneration
              deckId={deckId}
              jobId={regenJob}
              onClose={(changed) => {
                setRegenJob(null);
                setSelected([]);
                if (changed) reload();
              }}
            />
          ) : null}
          <ul className="space-y-3">
            {cards.map((c, i) => (
              <CardRow
                key={c.id}
                card={c}
                position={i}
                total={cards.length}
                selected={selected.includes(c.id)}
                onSelect={(on) =>
                  setSelected((s) => (on ? [...s, c.id] : s.filter((x) => x !== c.id)))
                }
                onSaved={reload}
                onDelete={() => setToDelete(c)}
                onMove={(d) => void move(i, d)}
              />
            ))}
          </ul>
        </div>
      )}
      <ConfirmDialog
        open={toDelete !== null}
        onOpenChange={(o) => !o && setToDelete(null)}
        title="Delete this card?"
        description="The card is removed from the deck. This cannot be undone."
        confirmLabel="Delete card"
        destructive
        onConfirm={async () => {
          const id = toDelete?.id;
          setToDelete(null);
          if (!id) return;
          try {
            await studyApi.deleteCard(id);
            reload();
          } catch {
            toast({ title: "Could not delete the card", variant: "destructive" });
          }
        }}
      />
    </div>
  );
}

/** Regenerated cards are a preview: nothing changes until the user applies it. */
function CardRegeneration({
  deckId,
  jobId,
  onClose,
}: {
  deckId: string;
  jobId: string;
  onClose: (changed: boolean) => void;
}) {
  const { job, error, cancel } = useJob(jobId);
  const preview = useAsync(
    () => (job?.status === "completed" ? studyApi.preview(jobId) : Promise.resolve(null)),
    [job?.status, jobId],
  );
  const [message, setMessage] = useState<string | null>(null);
  const cards = ((
    preview.data?.content as { payload?: { cards?: { front: string; back: string }[] } } | undefined
  )?.payload?.cards ?? []) as { front: string; back: string }[];

  async function apply() {
    try {
      await studyApi.applyCardPreview(deckId, jobId);
      onClose(true);
    } catch (err) {
      setMessage(
        err instanceof ApiRequestError && err.code === "PREVIEW_STALE"
          ? "Some of these cards changed since the preview. Nothing was replaced."
          : "Could not apply the preview.",
      );
    }
  }

  return (
    <div className="border-border space-y-3 rounded-lg border p-3" data-testid="card-regeneration">
      <h3 className="text-sm font-semibold">Regenerated cards (preview)</h3>
      {job && job.status !== "completed" ? (
        <JobProgress job={job} onCancel={cancel} showLink={false} />
      ) : null}
      {error ? (
        <p role="alert" className="text-destructive text-sm">
          {error}
        </p>
      ) : null}
      {cards.length > 0 ? (
        <ul className="space-y-2 text-sm">
          {cards.map((c, i) => (
            <li key={i} className="bg-muted/40 rounded p-2">
              <p className="font-medium break-words">{c.front}</p>
              <p className="break-words">{c.back}</p>
            </li>
          ))}
        </ul>
      ) : null}
      {message ? (
        <p role="alert" className="text-destructive text-sm">
          {message}
        </p>
      ) : null}
      <div className="flex gap-2">
        {job?.status === "completed" ? (
          <Button type="button" size="sm" onClick={apply} disabled={cards.length === 0}>
            Replace selected cards
          </Button>
        ) : null}
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={async () => {
            if (job?.status === "completed")
              await studyApi.discardPreview(jobId).catch(() => undefined);
            onClose(false);
          }}
        >
          {job?.status === "completed" ? "Discard" : "Close"}
        </Button>
      </div>
    </div>
  );
}
