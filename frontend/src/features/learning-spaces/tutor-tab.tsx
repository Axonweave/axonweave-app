"use client";

/**
 * AI Tutor tab of a learning environment. Asking here opens the full tutor with this context already
 * selected, so the learner never picks the subject, folder or chapter again. Past conversations
 * scoped to exactly this context are listed underneath.
 */
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowUp, MessageSquare } from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { AsyncSection } from "@/components/ui/async-section";
import { useAsync } from "@/hooks/use-async";
import { aiApi } from "@/lib/api/ai";
import { formatDateTime } from "@/lib/activity";
import { SCOPE_LABELS, contextQuery, toConversationScope } from "@/lib/learning-context";
import { useLearningSpace } from "./space-provider";

const SUGGESTIONS = [
  "Summarise the key ideas",
  "Explain the hardest concept simply",
  "Quiz me with five questions",
  "What should I learn first?",
];

/** Conversations are searched in pages of this size; older ones stay reachable in the tutor itself. */
const SCAN = 100;

export function TutorTab() {
  const space = useLearningSpace();
  const { ctx } = space;
  const router = useRouter();
  const [q, setQ] = useState("");
  const name = space.chapter?.title ?? space.folder?.name ?? space.subject.name;
  const scope = toConversationScope(ctx);
  const query = contextQuery(ctx);

  const status = useAsync(() => aiApi.status().catch(() => null), []);
  const convos = useAsync(
    () =>
      aiApi
        .listConversations({ limit: SCAN })
        .then((r) => r.data.filter((c) => c.scope_type === scope.kind && c.scope_id === scope.id)),
    [scope.kind, scope.id],
  );

  const ask = (text: string) => {
    const params = new URLSearchParams(query);
    if (text.trim()) params.set("q", text.trim());
    router.push(`/ai-tutor?${params.toString()}`);
  };
  const notConfigured = status.data && !status.data.configured;

  return (
    <div className="space-y-6">
      <section aria-labelledby="ask-heading" className="bg-card rounded-xl border p-5 sm:p-6">
        <h2 id="ask-heading" className="text-xl font-semibold tracking-tight">
          Ask anything about {name}
        </h2>
        <p className="text-muted-foreground mt-1 text-sm">
          Answers come from the documents in this {SCOPE_LABELS[ctx.scope].toLowerCase()}, with the
          passages they came from. You can widen or change the scope in the tutor.
        </p>

        {notConfigured ? (
          <p
            className="border-border bg-background mt-4 rounded-lg border p-3 text-sm"
            role="status"
          >
            AI is not configured on this server yet, so the tutor cannot answer. Everything else
            here still works.
          </p>
        ) : (
          <>
            <form
              className="border-border bg-background focus-within:ring-ring/50 mt-4 flex items-end gap-2 rounded-lg border p-2 focus-within:ring-3"
              onSubmit={(e) => {
                e.preventDefault();
                ask(q);
              }}
            >
              <label htmlFor="context-ask" className="sr-only">
                Your question about {name}
              </label>
              <textarea
                id="context-ask"
                rows={2}
                value={q}
                maxLength={status.data?.max_input_chars ?? 8000}
                onChange={(e) => setQ(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    ask(q);
                  }
                }}
                placeholder={`e.g. What are the main ideas in ${name}?`}
                className="placeholder:text-muted-foreground min-h-[3rem] flex-1 resize-none bg-transparent px-2 py-1.5 text-sm outline-none"
              />
              <Button type="submit" size="icon" aria-label="Ask the AI Tutor" disabled={!q.trim()}>
                <ArrowUp aria-hidden="true" />
              </Button>
            </form>
            <ul className="mt-3 flex flex-wrap gap-2" aria-label="Suggested questions">
              {SUGGESTIONS.map((s) => (
                <li key={s}>
                  <button
                    type="button"
                    onClick={() => ask(s)}
                    className="border-border bg-background hover:bg-muted focus-visible:ring-ring inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs transition-colors focus-visible:ring-2 focus-visible:outline-none"
                  >
                    {s}
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </section>

      <AsyncSection
        title={`Conversations about ${name}`}
        loading={convos.loading}
        error={convos.error}
        onRetry={convos.reload}
        isEmpty={(convos.data?.length ?? 0) === 0}
        empty={
          <p className="text-muted-foreground text-sm">
            No conversations about this {SCOPE_LABELS[ctx.scope].toLowerCase()} yet. Ask a question
            above to start one.
          </p>
        }
        action={
          <Link
            href={`/ai-tutor?${query}`}
            className={buttonVariants({ variant: "outline", size: "sm" })}
          >
            Open the tutor
          </Link>
        }
      >
        <ul className="divide-border divide-y rounded-xl border">
          {convos.data?.map((c) => (
            <li key={c.id}>
              <Link
                href={`/ai-tutor/${c.id}?${query}`}
                className="hover:bg-muted/50 focus-visible:ring-ring flex items-center gap-3 px-4 py-3 text-sm transition-colors focus-visible:ring-2 focus-visible:outline-none"
              >
                <MessageSquare
                  className="text-muted-foreground h-4 w-4 shrink-0"
                  aria-hidden="true"
                />
                <span className="min-w-0 flex-1 truncate font-medium">
                  {c.title ?? "Untitled conversation"}
                </span>
                <span className="text-muted-foreground shrink-0 text-xs">
                  {formatDateTime(c.last_message_at ?? c.created_at)}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </AsyncSection>
    </div>
  );
}
