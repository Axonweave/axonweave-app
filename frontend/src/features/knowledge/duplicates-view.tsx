"use client";

import { useState } from "react";
import { AsyncSection } from "@/components/ui/async-section";
import { Button } from "@/components/ui/button";
import { useAsync } from "@/hooks/use-async";
import { useToast } from "@/hooks/use-toast";
import { knowledgeApi, type CandidateAction, type DuplicateCandidate } from "@/lib/api/knowledge";

/** Review queue for possible duplicate concepts. Nothing merges unless the user chooses to. */
export function DuplicatesView({
  workspaceId,
  onChanged,
}: {
  workspaceId?: string;
  onChanged: () => void;
}) {
  const { toast } = useToast();
  const list = useAsync(() => knowledgeApi.duplicates(workspaceId, 20, 0), [workspaceId]);
  const [busy, setBusy] = useState<string | null>(null);

  async function resolve(c: DuplicateCandidate, action: CandidateAction, survivorId?: string) {
    setBusy(c.id);
    try {
      await knowledgeApi.resolveDuplicate(c.id, action, survivorId);
      toast({ title: action === "merge" ? "Concepts merged" : "Saved" });
      list.reload();
      onChanged();
    } catch {
      toast({ title: "Could not resolve this pair.", variant: "destructive" });
    } finally {
      setBusy(null);
    }
  }

  return (
    <AsyncSection
      title="Possible duplicates"
      loading={list.loading}
      error={list.error}
      onRetry={list.reload}
      isEmpty={!list.data?.data.length}
      empty={<p className="text-muted-foreground text-sm">No duplicates to review.</p>}
    >
      <ul className="space-y-3">
        {list.data?.data.map((c) => (
          <li key={c.id} className="bg-card space-y-2 rounded-lg border p-3">
            <div className="grid gap-3 sm:grid-cols-2">
              {[c.node_a, c.node_b].map((n) => (
                <div key={n.id} className="min-w-0 text-sm">
                  <p className="font-medium break-words">{n.name}</p>
                  <p className="text-muted-foreground text-xs">{n.node_type}</p>
                  {n.definition ? <p className="mt-1 line-clamp-3">{n.definition}</p> : null}
                </div>
              ))}
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                disabled={busy === c.id}
                onClick={() => resolve(c, "merge", c.node_a.id)}
              >
                Keep “{c.node_a.name}” and merge
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={busy === c.id}
                onClick={() => resolve(c, "merge", c.node_b.id)}
              >
                Keep “{c.node_b.name}” and merge
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={busy === c.id}
                onClick={() => resolve(c, "keep_separate")}
              >
                Keep separate
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={busy === c.id}
                onClick={() => resolve(c, "related")}
              >
                Mark related
              </Button>
              <Button
                size="sm"
                variant="ghost"
                disabled={busy === c.id}
                onClick={() => resolve(c, "ignore")}
              >
                Ignore
              </Button>
            </div>
          </li>
        ))}
      </ul>
    </AsyncSection>
  );
}
