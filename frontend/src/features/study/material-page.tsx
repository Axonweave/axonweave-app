"use client";

import { useCallback, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Archive,
  ArchiveRestore,
  ArrowLeft,
  History,
  Pencil,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { ErrorDisplay } from "@/components/ui/error-display";
import { LoadingSpinner } from "@/components/ui/loading";
import { useAsync } from "@/hooks/use-async";
import { useToast } from "@/hooks/use-toast";
import { formatDateTime } from "@/lib/activity";
import { ApiRequestError } from "@/lib/api/client";
import {
  materialParts,
  resourceLabel,
  studyApi,
  type MaterialVersion,
  type StudyMaterial,
} from "@/lib/api/study";
import { ExportMenu } from "./export-menu";
import { FlashcardDeck } from "./flashcards-view";
import { BankView, GlossaryView } from "./material-views";
import { renderBody } from "./render-body";
import { PayloadEditor } from "./payload-editor";
import { QuizPanel } from "./quiz-panel";
import { RegenerationReview } from "./regeneration-review";
import { Chip } from "./ui-bits";

/** Which generic actions apply (D-93, D-94: decks, quizzes and banks keep their items elsewhere). */
const EDITABLE = ["summary", "study_guide", "glossary", "formula_sheet"];
const REGENERABLE = ["summary", "study_guide", "glossary", "formula_sheet"];

export function MaterialPage({ materialId }: { materialId: string }) {
  const router = useRouter();
  const { toast } = useToast();
  const {
    data: material,
    loading,
    error,
    reload,
  } = useAsync(() => studyApi.get(materialId), [materialId]);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Record<string, unknown> | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [showVersions, setShowVersions] = useState(false);
  const [regen, setRegen] = useState<{ jobId: string; section: number | null } | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const startEdit = useCallback((m: StudyMaterial) => {
    setDraft(structuredClone(materialParts<Record<string, unknown>>(m).payload));
    setSaveError(null);
    setEditing(true);
  }, []);

  if (loading && !material) return <LoadingSpinner />;
  if (error || !material)
    return (
      <ErrorDisplay
        title="Could not load"
        message="This study material was not found."
        onRetry={reload}
      />
    );

  const { payload, sources, coverage } = materialParts<Record<string, unknown>>(material);
  const type = material.resource_type;
  const unavailable = material.unavailable_document_ids ?? [];

  async function save() {
    if (!material || !draft) return;
    setSaveError(null);
    try {
      await studyApi.edit(material.id, material.current_version, draft);
      setEditing(false);
      toast({ title: "Saved as a new version" });
      reload();
    } catch (err) {
      setSaveError(
        err instanceof ApiRequestError
          ? err.code === "MATERIAL_VERSION_CONFLICT"
            ? "This material changed elsewhere. Reload to see the latest version, then edit again."
            : err.message
          : "Could not save.",
      );
    }
  }

  async function startRegen(section: number | null) {
    if (!material) return;
    try {
      const job = await studyApi.regenerate(
        material.id,
        section === null ? {} : { section_index: section },
      );
      setRegen({ jobId: job.id, section });
    } catch (err) {
      toast({
        title: "Could not regenerate",
        description: err instanceof ApiRequestError ? err.message : undefined,
        variant: "destructive",
      });
    }
  }

  async function run(action: () => Promise<unknown>, done: string, after?: () => void) {
    try {
      await action();
      toast({ title: done });
      (after ?? reload)();
    } catch (err) {
      toast({
        title: "Action failed",
        description: err instanceof ApiRequestError ? err.message : "Something went wrong.",
        variant: "destructive",
      });
    }
  }

  return (
    <div className="min-w-0 space-y-5">
      <Link
        href="/study"
        className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1 text-sm"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        Study materials
      </Link>
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold break-words">{material.title}</h1>
        <div className="text-muted-foreground flex flex-wrap items-center gap-2 text-sm">
          <Chip>{resourceLabel(type)}</Chip>
          <span>Version {material.current_version}</span>
          <span>Updated {formatDateTime(material.updated_at)}</span>
          {material.archived_at ? <Chip>Archived</Chip> : null}
        </div>
        <p className="text-muted-foreground text-xs">
          Generated by AI from your documents. It can contain mistakes: check it against your
          source.
        </p>
        {unavailable.length > 0 ? (
          <p role="status" className="text-sm text-amber-700 dark:text-amber-400">
            {unavailable.length} source document{unavailable.length === 1 ? " was" : "s were"}{" "}
            deleted. This material is kept, but those references are unavailable.
          </p>
        ) : null}
        {coverage && coverage.complete === false ? (
          <p role="status" className="text-sm text-amber-700 dark:text-amber-400">
            Not every part of the source fit in one run. This covers only part of it.
          </p>
        ) : null}
      </header>

      <div className="flex flex-wrap items-center gap-2">
        {EDITABLE.includes(type) && !editing ? (
          <Button type="button" variant="outline" onClick={() => startEdit(material)}>
            <Pencil aria-hidden="true" />
            Edit
          </Button>
        ) : null}
        {REGENERABLE.includes(type) && !editing ? (
          <Button
            type="button"
            variant="outline"
            onClick={() => startRegen(null)}
            disabled={regen !== null}
          >
            <RefreshCw aria-hidden="true" />
            Regenerate
          </Button>
        ) : null}
        {EDITABLE.includes(type) ? (
          <Button
            type="button"
            variant="outline"
            aria-expanded={showVersions}
            onClick={() => setShowVersions((s) => !s)}
          >
            <History aria-hidden="true" />
            Versions
          </Button>
        ) : null}
        <Button
          type="button"
          variant="outline"
          onClick={() =>
            run(
              () =>
                material.archived_at
                  ? studyApi.unarchive(material.id)
                  : studyApi.archive(material.id),
              material.archived_at ? "Restored" : "Archived",
            )
          }
        >
          {material.archived_at ? (
            <ArchiveRestore aria-hidden="true" />
          ) : (
            <Archive aria-hidden="true" />
          )}
          {material.archived_at ? "Unarchive" : "Archive"}
        </Button>
        <Button type="button" variant="destructive" onClick={() => setConfirmDelete(true)}>
          <Trash2 aria-hidden="true" />
          Delete
        </Button>
      </div>
      <ExportMenu materialId={material.id} resourceType={type} />

      {regen ? (
        <RegenerationReview
          material={material}
          jobId={regen.jobId}
          section={regen.section}
          onClose={(applied) => {
            setRegen(null);
            if (applied) reload();
          }}
        />
      ) : null}

      {showVersions && EDITABLE.includes(type) ? (
        <VersionsPanel
          material={material}
          onRestored={() => {
            setShowVersions(false);
            reload();
          }}
        />
      ) : null}

      {editing && draft ? (
        <form
          className="space-y-4"
          aria-label="Edit material"
          onSubmit={(e) => {
            e.preventDefault();
            void save();
          }}
        >
          <PayloadEditor
            value={draft as never}
            onChange={(next) => setDraft(next as Record<string, unknown>)}
          />
          {saveError ? (
            <p role="alert" className="text-destructive text-sm">
              {saveError}
            </p>
          ) : null}
          <div className="flex gap-2">
            <Button type="submit">Save</Button>
            <Button type="button" variant="outline" onClick={() => setEditing(false)}>
              Cancel
            </Button>
          </div>
        </form>
      ) : type === "flashcards" ? (
        material.item_id ? (
          <FlashcardDeck deckId={material.item_id} unavailable={unavailable} />
        ) : (
          <p className="text-muted-foreground text-sm">This deck is not available.</p>
        )
      ) : type === "glossary" ? (
        <GlossaryView materialId={material.id} sources={sources} unavailable={unavailable} />
      ) : type === "question_bank" ? (
        <BankView
          materialId={material.id}
          quizId={material.item_id ?? null}
          sources={sources}
          unavailable={unavailable}
        />
      ) : type === "quiz" ? (
        <QuizPanel material={material} />
      ) : (
        renderBody(
          material,
          payload,
          sources,
          REGENERABLE.includes(type) && regen === null ? (i) => void startRegen(i) : undefined,
        )
      )}

      {type === "question_bank" && material.item_id ? (
        <Link
          className={buttonVariants({ variant: "outline" })}
          href={`/study/${material.id}/quiz`}
        >
          Practise as a quiz
        </Link>
      ) : null}

      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="Delete this study material?"
        description="It and all its versions and exports will be permanently deleted. Your documents are not affected. This cannot be undone."
        confirmLabel="Delete"
        destructive
        onConfirm={() => {
          setConfirmDelete(false);
          void run(
            () => studyApi.remove(material.id),
            "Deleted",
            () => router.push("/study"),
          );
        }}
      />
    </div>
  );
}

/* ───────── version history ───────── */

function VersionsPanel({
  material,
  onRestored,
}: {
  material: StudyMaterial;
  onRestored: () => void;
}) {
  const { toast } = useToast();
  const versions = useAsync(
    () => studyApi.versions(material.id),
    [material.id, material.current_version],
  );
  const [viewing, setViewing] = useState<MaterialVersion | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function open(n: number) {
    setError(null);
    try {
      setViewing(await studyApi.version(material.id, n));
    } catch {
      setError("Could not load that version.");
    }
  }
  async function restore(n: number) {
    try {
      await studyApi.restore(material.id, material.current_version, n);
      toast({ title: `Version ${n} restored as a new version` });
      onRestored();
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Could not restore.");
    }
  }

  const viewingContent = viewing?.content
    ? materialParts({ ...material, content: viewing.content })
    : null;
  return (
    <section aria-label="Version history" className="border-border space-y-3 rounded-lg border p-3">
      <h2 className="text-sm font-semibold">Version history</h2>
      {versions.loading ? <p className="text-muted-foreground text-sm">Loading…</p> : null}
      <ul className="space-y-1">
        {(versions.data ?? []).map((v) => (
          <li key={v.version_number} className="flex flex-wrap items-center gap-2 text-sm">
            <span className="font-medium">Version {v.version_number}</span>
            <Chip>{v.origin}</Chip>
            <span className="text-muted-foreground">{formatDateTime(v.created_at)}</span>
            {v.version_number === material.current_version ? <Chip>Current</Chip> : null}
            <Button type="button" variant="ghost" size="sm" onClick={() => open(v.version_number)}>
              View
            </Button>
            {v.version_number !== material.current_version ? (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => restore(v.version_number)}
              >
                Restore
              </Button>
            ) : null}
          </li>
        ))}
      </ul>
      {error ? (
        <p role="alert" className="text-destructive text-sm">
          {error}
        </p>
      ) : null}
      {viewing && viewingContent ? (
        <div className="border-border rounded-lg border p-3">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-sm font-semibold">Version {viewing.version_number} (read only)</h3>
            <Button type="button" variant="ghost" size="sm" onClick={() => setViewing(null)}>
              Close
            </Button>
          </div>
          {renderBody(material, viewingContent.payload, viewingContent.sources)}
        </div>
      ) : null}
    </section>
  );
}
