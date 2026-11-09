"use client";

import { useRef, useState } from "react";
import { UploadCloud } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAsync } from "@/hooks/use-async";
import { useToast } from "@/hooks/use-toast";
import { ApiRequestError } from "@/lib/api/client";
import { documentsApi, type UploadPlacement } from "@/lib/api/documents";
import { subjectsApi } from "@/lib/api/subjects";
import { workspacesApi } from "@/lib/api/workspaces";

export const ACCEPT = ".pdf,.pptx,.docx,.txt,.md,.png,.jpg,.jpeg";
/** Client-side hint only. The server enforces the real limits (D-71). */
export const MAX_FILES = 5;

interface Props {
  onUploaded: () => void;
  /** Pre-selected placement (upload from a subject page). */
  defaultPlacement?: Partial<UploadPlacement>;
}

export function UploadZone({ onUploaded, defaultPlacement }: Props) {
  const { toast } = useToast();
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [workspaceId, setWorkspaceId] = useState(defaultPlacement?.workspace_id ?? "");
  const [subjectId, setSubjectId] = useState(defaultPlacement?.subject_id ?? "");

  const workspaces = useAsync(() => workspacesApi.list().then((r) => r.data), []);
  const wsList = workspaces.data ?? [];
  const effectiveWorkspace =
    workspaceId || wsList.find((w) => w.is_default)?.id || wsList[0]?.id || "";
  const subjects = useAsync(
    () =>
      effectiveWorkspace
        ? subjectsApi.list(effectiveWorkspace, { limit: 100 }).then((r) => r.data)
        : Promise.resolve([]),
    [effectiveWorkspace],
  );

  async function send(files: File[]) {
    if (files.length === 0) return;
    if (!effectiveWorkspace) {
      toast({ title: "Choose a workspace first", variant: "destructive" });
      return;
    }
    if (files.length > MAX_FILES) {
      toast({ title: `Upload up to ${MAX_FILES} files at a time`, variant: "destructive" });
      return;
    }
    setBusy(true);
    try {
      const result = await documentsApi.upload(files, {
        workspace_id: effectiveWorkspace,
        subject_id: subjectId || null,
        folder_id: defaultPlacement?.folder_id,
        chapter_id: defaultPlacement?.chapter_id,
      });
      if (result.documents.length > 0) {
        toast({
          title: `${result.documents.length} file${result.documents.length === 1 ? "" : "s"} uploaded`,
          description: "Processing has started. Status updates here automatically.",
        });
        onUploaded();
      }
      for (const rejected of result.rejected) {
        toast({
          title: `${rejected.filename} was not uploaded`,
          description: rejected.message,
          variant: "destructive",
        });
      }
    } catch (err) {
      toast({
        title: "Upload failed",
        description: err instanceof ApiRequestError ? err.message : "Something went wrong.",
        variant: "destructive",
      });
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-col gap-3 sm:flex-row">
        <label className="flex flex-1 flex-col gap-1 text-sm">
          Workspace
          <select
            className="border-input bg-background h-9 rounded-md border px-2"
            value={effectiveWorkspace}
            onChange={(e) => {
              setWorkspaceId(e.target.value);
              setSubjectId("");
            }}
          >
            {wsList.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-1 flex-col gap-1 text-sm">
          Subject (optional)
          <select
            className="border-input bg-background h-9 rounded-md border px-2"
            value={subjectId}
            onChange={(e) => setSubjectId(e.target.value)}
          >
            <option value="">No subject</option>
            {(subjects.data ?? []).map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          void send(Array.from(e.dataTransfer.files));
        }}
        className={`flex flex-col items-center gap-3 rounded-lg border-2 border-dashed px-4 py-8 text-center ${
          dragging ? "border-primary bg-muted" : "border-border"
        }`}
      >
        <UploadCloud className="text-muted-foreground h-8 w-8" aria-hidden="true" />
        <p className="text-sm">
          Drag files here, or choose them.
          <span className="text-muted-foreground block text-xs">
            PDF, PowerPoint, Word, text, Markdown, PNG or JPEG. Up to {MAX_FILES} files at a time.
          </span>
        </p>
        <input
          ref={input}
          type="file"
          multiple
          accept={ACCEPT}
          className="sr-only"
          aria-label="Choose files to upload"
          onChange={(e) => void send(Array.from(e.target.files ?? []))}
        />
        <Button type="button" disabled={busy} onClick={() => input.current?.click()}>
          {busy ? "Uploading…" : "Choose files"}
        </Button>
      </div>
    </div>
  );
}
