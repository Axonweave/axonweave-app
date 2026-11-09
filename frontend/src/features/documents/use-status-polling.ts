"use client";

import { useEffect, useRef } from "react";
import { isTerminal } from "@/lib/api/documents";

export const POLL_MS = 3000;

/**
 * Calls `onTick` every few seconds while at least one id is still being processed, and stops when
 * everything is terminal (or the tab is hidden). Real status only: nothing is faked in between.
 */
export function useStatusPolling(statuses: string[], onTick: () => void, intervalMs = POLL_MS) {
  const active = statuses.some((s) => !isTerminal(s));
  const tick = useRef(onTick);
  useEffect(() => {
    tick.current = onTick;
  });
  useEffect(() => {
    if (!active) return;
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") tick.current();
    }, intervalMs);
    return () => window.clearInterval(id);
  }, [active, intervalMs]);
}
