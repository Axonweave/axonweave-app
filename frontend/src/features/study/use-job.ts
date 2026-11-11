"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { isJobDone, studyApi, type GenerationJob } from "@/lib/api/study";

export const JOB_POLL_MS = 2000;

/**
 * Polls one generation job until it reaches a terminal state. Real server status only; the
 * progress bar shows the server's own number. Polling pauses while the tab is hidden.
 */
export function useJob(jobId: string | null, onDone?: (job: GenerationJob) => void) {
  const [job, setJob] = useState<GenerationJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const done = useRef(onDone);
  useEffect(() => {
    done.current = onDone;
  });

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setJob(null);
    setError(null);
    if (!jobId) return;
    let stopped = false;
    let timer: number | undefined;
    const tick = async () => {
      if (stopped) return;
      if (document.visibilityState !== "visible") {
        timer = window.setTimeout(tick, JOB_POLL_MS);
        return;
      }
      try {
        const next = await studyApi.job(jobId);
        if (stopped) return;
        setJob(next);
        if (isJobDone(next.status)) {
          done.current?.(next);
          return;
        }
      } catch {
        if (!stopped) setError("Could not read the job status.");
        return;
      }
      timer = window.setTimeout(tick, JOB_POLL_MS);
    };
    void tick();
    return () => {
      stopped = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [jobId]);

  const cancel = useCallback(async () => {
    if (!jobId) return;
    try {
      setJob(await studyApi.cancel(jobId));
    } catch {
      setError("Could not cancel this job.");
    }
  }, [jobId]);

  return { job, error, cancel };
}
