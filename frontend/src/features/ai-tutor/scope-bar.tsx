"use client";

import { useAsync } from "@/hooks/use-async";
import type { AnswerMode, ConversationScope } from "@/lib/api/ai";
import { documentsApi } from "@/lib/api/documents";
import { workspacesApi } from "@/lib/api/workspaces";

export const MODE_LABELS: Record<AnswerMode, string> = {
  document_only: "Only from my documents",
  document_first: "Documents first, then general knowledge",
  general: "General knowledge",
};

export const scopeKey = (s: ConversationScope | null) => (s ? `${s.kind}:${s.id}` : "");

export function parseScope(value: string): ConversationScope | null {
  const [kind, id] = value.split(":");
  return kind && id ? ({ kind, id } as ConversationScope) : null;
}

/** Pick what a NEW conversation may read. The scope is fixed once the conversation exists. */
export function ScopePicker({
  value,
  onChange,
  disabled,
}: {
  value: ConversationScope | null;
  onChange: (scope: ConversationScope | null) => void;
  disabled?: boolean;
}) {
  const workspaces = useAsync(() => workspacesApi.list().then((r) => r.data), []);
  const documents = useAsync(
    () => documentsApi.list({ status: "completed", limit: 100 }).then((r) => r.data),
    [],
  );
  return (
    <label className="flex min-w-0 flex-col gap-1 text-xs sm:flex-row sm:items-center sm:gap-2">
      <span className="text-muted-foreground shrink-0">Ask about</span>
      <select
        className="border-input bg-background h-8 min-w-0 rounded-md border px-2 text-sm"
        value={scopeKey(value)}
        disabled={disabled}
        onChange={(e) => onChange(parseScope(e.target.value))}
      >
        <option value="">General chat (no documents)</option>
        {(workspaces.data ?? []).length > 0 && (
          <optgroup label="Everything in a workspace">
            {(workspaces.data ?? []).map((w) => (
              <option key={w.id} value={`workspace:${w.id}`}>
                {w.name}
              </option>
            ))}
          </optgroup>
        )}
        {(documents.data ?? []).length > 0 && (
          <optgroup label="One document">
            {(documents.data ?? []).map((d) => (
              <option key={d.id} value={`document:${d.id}`}>
                {d.display_name}
              </option>
            ))}
          </optgroup>
        )}
      </select>
    </label>
  );
}

export function ModePicker({
  value,
  onChange,
  disabled,
}: {
  value: AnswerMode;
  onChange: (mode: AnswerMode) => void;
  disabled?: boolean;
}) {
  return (
    <label className="flex min-w-0 flex-col gap-1 text-xs sm:flex-row sm:items-center sm:gap-2">
      <span className="text-muted-foreground shrink-0">Answer</span>
      <select
        className="border-input bg-background h-8 min-w-0 rounded-md border px-2 text-sm"
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value as AnswerMode)}
      >
        {(Object.keys(MODE_LABELS) as AnswerMode[]).map((m) => (
          <option key={m} value={m}>
            {MODE_LABELS[m]}
          </option>
        ))}
      </select>
    </label>
  );
}
