"use client";

import { useState } from "react";
import { useAsync } from "@/hooks/use-async";
import type { AnswerMode, ConversationScope } from "@/lib/api/ai";
import { chaptersApi } from "@/lib/api/chapters";
import { documentsApi } from "@/lib/api/documents";
import { foldersApi } from "@/lib/api/folders";
import { subjectsApi } from "@/lib/api/subjects";
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

type Kind = "general" | ConversationScope["kind"];
const KIND_LABELS: Record<Kind, string> = {
  general: "General chat (no documents)",
  workspace: "Everything in a workspace",
  subject: "A subject",
  folder: "A folder",
  chapter: "A chapter",
  document: "One document",
};

const field = "border-input bg-background h-8 min-w-0 rounded-md border px-2 text-sm";

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
  const [kind, setKind] = useState<Kind>(value?.kind ?? "general");
  const [workspaceId, setWorkspaceId] = useState("");
  const [subjectId, setSubjectId] = useState("");

  const workspaces = useAsync(() => workspacesApi.list().then((r) => r.data), []);
  const wsList = workspaces.data ?? [];
  const ws = workspaceId || wsList.find((w) => w.is_default)?.id || wsList[0]?.id || "";
  const needsSubject = kind === "subject" || kind === "folder" || kind === "chapter";
  const subjects = useAsync(
    () =>
      needsSubject && ws
        ? subjectsApi.list(ws, { limit: 100 }).then((r) => r.data)
        : Promise.resolve([]),
    [needsSubject, ws],
  );
  const subList = subjects.data ?? [];
  const sub = subjectId || subList[0]?.id || "";
  const folders = useAsync(
    () => (kind === "folder" && ws && sub ? foldersApi.listAll(ws, sub) : Promise.resolve([])),
    [kind, ws, sub],
  );
  const chapters = useAsync(
    () =>
      kind === "chapter" && ws && sub
        ? chaptersApi.listAll(ws, sub).then((r) => r.data)
        : Promise.resolve([]),
    [kind, ws, sub],
  );
  const documents = useAsync(
    () =>
      kind === "document"
        ? documentsApi.list({ status: "completed", limit: 100 }).then((r) => r.data)
        : Promise.resolve([]),
    [kind],
  );

  const choose = (k: Kind, id: string) =>
    onChange(k === "general" || !id ? null : ({ kind: k, id } as ConversationScope));

  const targets: { id: string; name: string }[] =
    kind === "workspace"
      ? wsList.map((w) => ({ id: w.id, name: w.name }))
      : kind === "subject"
        ? subList.map((x) => ({ id: x.id, name: x.name }))
        : kind === "folder"
          ? (folders.data ?? []).map((f) => ({ id: f.id, name: f.name }))
          : kind === "chapter"
            ? (chapters.data ?? []).map((c) => ({ id: c.id, name: c.title }))
            : (documents.data ?? []).map((d) => ({ id: d.id, name: d.display_name }));

  return (
    <div className="flex min-w-0 flex-col gap-2 text-xs sm:flex-row sm:flex-wrap sm:items-center">
      <label className="flex min-w-0 flex-col gap-1 sm:flex-row sm:items-center sm:gap-2">
        <span className="text-muted-foreground shrink-0">Ask about</span>
        <select
          className={field}
          value={kind}
          disabled={disabled}
          onChange={(e) => {
            const k = e.target.value as Kind;
            setKind(k);
            onChange(null); // a new kind has no target until one is chosen
          }}
        >
          {(Object.keys(KIND_LABELS) as Kind[]).map((k) => (
            <option key={k} value={k}>
              {KIND_LABELS[k]}
            </option>
          ))}
        </select>
      </label>
      {needsSubject && (
        <>
          <select
            aria-label="Workspace"
            className={field}
            value={ws}
            disabled={disabled}
            onChange={(e) => {
              setWorkspaceId(e.target.value);
              setSubjectId("");
              onChange(null);
            }}
          >
            {wsList.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
          </select>
          {kind !== "subject" && (
            <select
              aria-label="Subject"
              className={field}
              value={sub}
              disabled={disabled}
              onChange={(e) => {
                setSubjectId(e.target.value);
                onChange(null);
              }}
            >
              {subList.map((x) => (
                <option key={x.id} value={x.id}>
                  {x.name}
                </option>
              ))}
            </select>
          )}
        </>
      )}
      {kind !== "general" && (
        <select
          aria-label="Choose what to ask about"
          className={field}
          value={value?.kind === kind ? value.id : ""}
          disabled={disabled}
          onChange={(e) => choose(kind, e.target.value)}
        >
          <option value="">Choose…</option>
          {targets.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
        </select>
      )}
    </div>
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
