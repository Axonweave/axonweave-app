"use client";

/**
 * Documents and generated study materials that belong to the current learning context.
 * Documents filter by workspace, subject, folder and chapter on the server. Study materials record
 * only a subject and chapter, so at folder scope they are narrowed to the folder's chapters here.
 */
import Link from "next/link";
import { FileText, Sparkles } from "lucide-react";
import { AsyncSection } from "@/components/ui/async-section";
import { useAsync } from "@/hooks/use-async";
import { documentsApi } from "@/lib/api/documents";
import { resourceLabel, studyApi } from "@/lib/api/study";
import { formatDate } from "@/lib/activity";
import { StatusBadge as DocStatus } from "@/features/documents/status-badge";
import { useLearningSpace } from "./space-provider";

const SHOW = 6;
const ROW =
  "hover:bg-muted/60 focus-visible:ring-ring flex items-center gap-3 rounded-lg px-2 py-2 text-sm transition-colors focus-visible:ring-2 focus-visible:outline-none";

export function useScopedDocuments(limit = SHOW) {
  const { ctx } = useLearningSpace();
  return useAsync(
    () =>
      documentsApi.list({
        workspace_id: ctx.workspaceId,
        subject_id: ctx.subjectId,
        folder_id: ctx.folderId,
        chapter_id: ctx.chapterId,
        sort_by: "updated_at",
        sort_dir: "desc",
        limit,
      }),
    [ctx.workspaceId, ctx.subjectId, ctx.folderId, ctx.chapterId, limit],
  );
}

export function useScopedMaterials(limit = SHOW) {
  const { ctx, scopedChapters } = useLearningSpace();
  const folderChapterIds = ctx.scope === "folder" ? scopedChapters.map((c) => c.id) : null;
  const key = folderChapterIds?.join(",") ?? "";
  return useAsync(async () => {
    if (folderChapterIds) {
      if (folderChapterIds.length === 0) return { data: [], total: 0 };
      const all = await studyApi.list({
        workspace_id: ctx.workspaceId,
        subject_id: ctx.subjectId,
        sort_by: "updated_at",
        sort_dir: "desc",
        limit: 100,
      });
      const ids = new Set(folderChapterIds);
      const inFolder = all.data.filter((m) => m.chapter_id && ids.has(m.chapter_id));
      return { data: inFolder.slice(0, limit), total: inFolder.length };
    }
    const page = await studyApi.list({
      workspace_id: ctx.workspaceId,
      subject_id: ctx.subjectId,
      chapter_id: ctx.chapterId,
      sort_by: "updated_at",
      sort_dir: "desc",
      limit,
    });
    return { data: page.data, total: page.total };
  }, [ctx.workspaceId, ctx.subjectId, ctx.chapterId, key, limit]);
}

export function ScopedMaterials() {
  const { ctx } = useLearningSpace();
  const docs = useScopedDocuments();
  const materials = useScopedMaterials();
  const libraryHref =
    `/library?workspace=${ctx.workspaceId}&subject=${ctx.subjectId}` +
    (ctx.chapterId ? `&chapter=${ctx.chapterId}` : "");

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className="border-border rounded-xl border p-4">
        <AsyncSection
          title={`Documents${docs.data ? ` (${docs.data.total})` : ""}`}
          loading={docs.loading}
          error={docs.error}
          onRetry={docs.reload}
          isEmpty={(docs.data?.total ?? 0) === 0}
          empty={
            <p className="text-muted-foreground py-4 text-sm">
              No documents here yet.{" "}
              <Link href={libraryHref} className="text-primary underline underline-offset-4">
                Upload one
              </Link>{" "}
              so the AI Tutor and study tools can use it.
            </p>
          }
          action={
            <Link
              href={libraryHref}
              className="text-primary text-sm underline-offset-4 hover:underline"
            >
              Library
            </Link>
          }
        >
          <ul className="-mx-2">
            {docs.data?.data.map((d) => (
              <li key={d.id}>
                <Link href={`/documents/${d.id}`} className={ROW}>
                  <FileText className="text-muted-foreground h-4 w-4 shrink-0" aria-hidden="true" />
                  <span className="min-w-0 flex-1 truncate">{d.display_name}</span>
                  <DocStatus status={d.processing_status} />
                </Link>
              </li>
            ))}
          </ul>
        </AsyncSection>
      </div>

      <div className="border-border rounded-xl border p-4">
        <AsyncSection
          title={`Study materials${materials.data ? ` (${materials.data.total})` : ""}`}
          loading={materials.loading}
          error={materials.error}
          onRetry={materials.reload}
          isEmpty={(materials.data?.total ?? 0) === 0}
          empty={
            <p className="text-muted-foreground py-4 text-sm">
              No summaries, flashcards or quizzes yet. Use “Generate study material” above.
            </p>
          }
          action={
            <Link href="/study" className="text-primary text-sm underline-offset-4 hover:underline">
              All materials
            </Link>
          }
        >
          <ul className="-mx-2">
            {materials.data?.data.map((m) => (
              <li key={m.id}>
                <Link href={`/study/${m.id}`} className={ROW}>
                  <Sparkles className="text-muted-foreground h-4 w-4 shrink-0" aria-hidden="true" />
                  <span className="min-w-0 flex-1 truncate">{m.title}</span>
                  <span className="text-muted-foreground shrink-0 text-xs">
                    {resourceLabel(m.resource_type)} · {formatDate(m.updated_at)}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </AsyncSection>
      </div>
    </div>
  );
}
