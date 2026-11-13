"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { ApiRequestError } from "@/lib/api/client";
import {
  knowledgeApi,
  type ClearGraphResult,
  type ExtractionJob,
  type SubjectExtractionRun,
} from "@/lib/api/knowledge";
import { SubjectDocumentsPanel } from "./subject-documents-panel";

const POLL_MS = 4000;
const BUSY = new Set(["pending", "retrieving_sources", "extracting", "validating", "saving"]);

function errorText(e: unknown): string {
  if (e instanceof ApiRequestError) {
    if (e.code === "LLM_NOT_CONFIGURED") return "No AI provider is configured on this server.";
    if (e.code === "AI_QUOTA_EXCEEDED")
      return "Your daily AI usage limit has been reached, so nothing was started. It resets at midnight UTC.";
    if (e.code === "LLM_WEB_SEARCH_UNAVAILABLE")
      return "Web search is not available for the configured AI model or account.";
    if (e.status === 503) return "Extraction is not available right now. Try again later.";
    return e.message;
  }
  return "Could not start the knowledge graph. Try again.";
}

/**
 * Starts AI extraction for every processed document of one subject (documents that were already
 * extracted are skipped by the backend) and shows real progress from the job list.
 */
export function GenerateSubjectGraph({
  subjectId,
  subjectName,
  onProgress,
}: {
  subjectId: string;
  subjectName: string;
  /** Called when the graph changed (jobs completed, graph cleared), so it can reload. */
  onProgress: () => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const [starting, setStarting] = useState(false);
  const [run, setRun] = useState<SubjectExtractionRun | null>(null);
  const [jobs, setJobs] = useState<ExtractionJob[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [showDocs, setShowDocs] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [clearBusy, setClearBusy] = useState(false);
  const [cleared, setCleared] = useState<ClearGraphResult | null>(null);
  const [confirmingWeb, setConfirmingWeb] = useState(false);
  const [webJobId, setWebJobId] = useState<string | null>(null);
  const completedSeen = useRef(0);
  const webSeen = useRef(false);

  const webJob = webJobId ? jobs.find((j) => j.id === webJobId) : undefined;
  const webActive = webJobId !== null && (webJob === undefined || BUSY.has(webJob.status));

  const mine = run ? jobs.filter((j) => run.job_ids.includes(j.id)) : [];
  const done = mine.filter((j) => j.status === "completed").length;
  const failed = mine.filter((j) => j.status === "failed" || j.status === "cancelled").length;
  const active = (run ? run.job_ids.length - done - failed : 0) + (webActive ? 1 : 0);

  const poll = useCallback(async () => {
    try {
      const page = await knowledgeApi.extractionJobs(subjectId);
      setJobs(page.data);
    } catch {
      /* a failed poll is retried on the next tick */
    }
  }, [subjectId]);

  // keep polling while this run has unfinished jobs, or while the document list is open and any
  // job (for example one started before a page reload) is still working
  const anyBusy = jobs.some((j) => BUSY.has(j.status));
  const polling =
    (run !== null && run.job_ids.length > 0 && active > 0) || webActive || (showDocs && anyBusy);
  useEffect(() => {
    if (!polling) return;
    const t = setInterval(poll, POLL_MS);
    return () => clearInterval(t);
  }, [polling, poll]);

  function toggleDocs() {
    if (!showDocs) void poll(); // fresh job status the moment the list opens
    setShowDocs((v) => !v);
  }

  useEffect(() => {
    if (done > completedSeen.current) {
      completedSeen.current = done;
      onProgress();
    }
  }, [done, onProgress]);

  useEffect(() => {
    if (webJob?.status === "completed" && !webSeen.current) {
      webSeen.current = true;
      onProgress();
    }
  }, [webJob?.status, onProgress]);

  async function startWeb() {
    setStarting(true);
    setError(null);
    setCleared(null);
    try {
      const job = await knowledgeApi.extractWeb(subjectId);
      webSeen.current = false;
      setWebJobId(job.id);
      setConfirmingWeb(false);
      await poll();
    } catch (e) {
      setError(errorText(e));
      setConfirmingWeb(false);
    } finally {
      setStarting(false);
    }
  }

  async function start() {
    setStarting(true);
    setError(null);
    setCleared(null);
    try {
      const result = await knowledgeApi.extractSubject(subjectId);
      setRun(result);
      completedSeen.current = 0;
      setConfirming(false);
      if (result.job_ids.length) await poll();
    } catch (e) {
      setError(errorText(e));
      setConfirming(false);
    } finally {
      setStarting(false);
    }
  }

  async function clearGraph() {
    setClearBusy(true);
    setError(null);
    try {
      const result = await knowledgeApi.clearSubjectGraph(subjectId);
      setCleared(result);
      setRun(null);
      setWebJobId(null);
      setJobs([]);
      completedSeen.current = 0;
      setClearing(false);
      onProgress();
    } catch (e) {
      setError(
        e instanceof ApiRequestError && e.status === 409
          ? "An extraction is still running for this subject. Wait for it to finish first."
          : e instanceof ApiRequestError
            ? e.message
            : "Could not clear the graph. Try again.",
      );
      setClearing(false);
    } finally {
      setClearBusy(false);
    }
  }

  const finished = run !== null && run.job_ids.length > 0 && active === 0;

  return (
    <section
      aria-label="Generate knowledge graph"
      className="bg-card flex flex-wrap items-center gap-3 rounded-lg border p-3 text-sm"
    >
      <div className="min-w-0 flex-1">
        <p className="font-medium">AI knowledge graph for {subjectName}</p>
        <p className="text-muted-foreground text-xs">
          Reads every processed document in this subject and extracts concepts and how they relate.
          Documents that were already extracted are skipped. With no documents, build it from a web
          search on the subject name instead.
        </p>
        {run ? (
          <p role="status" className="mt-1 text-xs">
            {run.ready === 0
              ? "This subject has no processed documents yet."
              : run.job_ids.length === 0
                ? `Nothing to do: ${run.skipped} of ${run.ready} documents already have concepts.`
                : active > 0
                  ? `Extracting: ${done} of ${run.job_ids.length} documents done${
                      failed ? `, ${failed} failed` : ""
                    }.`
                  : `Finished: ${done} of ${run.job_ids.length} documents done${
                      failed ? `, ${failed} failed` : ""
                    }.`}
            {run.skipped > 0 && run.job_ids.length > 0 ? ` ${run.skipped} skipped.` : ""}
            {run.over_cap > 0
              ? ` ${run.over_cap} more documents are left; run it again after these finish.`
              : ""}
            {run.not_ready > 0 ? ` ${run.not_ready} not ready.` : ""}
            {finished && failed > 0 ? " Run it again to retry the failed ones." : ""}
          </p>
        ) : null}
        {webJobId ? (
          <p role="status" className="mt-1 text-xs" data-testid="web-status">
            {webJob?.status === "completed"
              ? "Web research finished. The concepts link to the websites they came from."
              : webJob?.status === "failed" || webJob?.status === "cancelled"
                ? `Web research did not finish${webJob.error_message ? `: ${webJob.error_message}` : "."}`
                : "Searching the web and building the graph..."}
          </p>
        ) : null}
        <button
          type="button"
          className="text-primary mt-1 text-xs underline"
          aria-expanded={showDocs}
          onClick={toggleDocs}
        >
          {showDocs ? "Hide documents" : "View documents"}
        </button>
        {clearing ? (
          <p role="alert" className="text-destructive mt-1 text-xs">
            Delete every concept of {subjectName}? This also removes their relationships, evidence
            links, mastery scores and misconception records for these concepts. This cannot be
            undone. Your documents, flashcards and quizzes are not deleted.
          </p>
        ) : null}
        {cleared ? (
          <p role="status" className="mt-1 text-xs">
            Cleared {cleared.concepts} concepts and {cleared.relationships} relationships. You can
            generate the graph again.
          </p>
        ) : null}
        {error ? (
          <p role="alert" className="text-destructive mt-1 text-xs">
            {error}
          </p>
        ) : null}
      </div>
      {confirmingWeb ? (
        <div className="flex w-full flex-wrap items-center gap-2">
          <span className="text-muted-foreground min-w-0 flex-1 text-xs">
            This uses your AI quota and sends the subject name “{subjectName}” to a web search.
            Concepts come from public websites, which can be wrong or biased, so review them. Each
            one links to its source.
          </span>
          <Button type="button" size="sm" onClick={startWeb} disabled={starting}>
            {starting ? "Starting..." : "Search the web"}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => setConfirmingWeb(false)}
            disabled={starting}
          >
            Cancel
          </Button>
        </div>
      ) : confirming ? (
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground text-xs">This uses your AI quota.</span>
          <Button type="button" size="sm" onClick={start} disabled={starting}>
            {starting ? "Starting..." : "Start"}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => setConfirming(false)}
            disabled={starting}
          >
            Cancel
          </Button>
        </div>
      ) : clearing ? (
        <div className="flex items-center gap-2">
          <Button
            type="button"
            size="sm"
            variant="destructive"
            onClick={clearGraph}
            disabled={clearBusy}
          >
            {clearBusy ? "Deleting..." : "Delete all concepts"}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => setClearing(false)}
            disabled={clearBusy}
          >
            Keep them
          </Button>
        </div>
      ) : (
        <div className="flex items-center gap-2">
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => setClearing(true)}
            disabled={starting || active > 0}
          >
            Clear graph
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => setConfirmingWeb(true)}
            disabled={starting || active > 0}
          >
            Build from the web
          </Button>
          <Button
            type="button"
            size="sm"
            onClick={() => setConfirming(true)}
            disabled={starting || active > 0}
          >
            {active > 0 ? "Generating..." : "Generate knowledge graph"}
          </Button>
        </div>
      )}
      {showDocs ? <SubjectDocumentsPanel subjectId={subjectId} jobs={jobs} /> : null}
    </section>
  );
}
