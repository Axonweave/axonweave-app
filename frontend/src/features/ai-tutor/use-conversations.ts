"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { aiApi, type Conversation } from "@/lib/api/ai";

const PAGE = 30;
const MAX = 100;

/** Date buckets for the sidebar. Pure so it can be tested with a fixed "now". */
export function groupLabel(iso: string, now = new Date()): string {
  const day = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const diff = Math.round((day(now) - day(new Date(iso))) / 86_400_000);
  if (diff <= 0) return "Today";
  if (diff === 1) return "Yesterday";
  if (diff < 8) return "Previous 7 days";
  return "Older";
}

export function groupConversations(
  items: Conversation[],
  now = new Date(),
): { label: string; items: Conversation[] }[] {
  const groups: { label: string; items: Conversation[] }[] = [];
  for (const c of items) {
    const label = groupLabel(c.last_message_at ?? c.created_at, now);
    const last = groups[groups.length - 1];
    if (last && last.label === label) last.items.push(c);
    else groups.push({ label, items: [c] });
  }
  return groups;
}

/** The server decides order and search; this only holds what has been loaded so far. */
export function useConversations() {
  const [items, setItems] = useState<Conversation[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState(false);
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const loadedRef = useRef(PAGE);
  const seq = useRef(0);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(query), 300);
    return () => clearTimeout(t);
  }, [query]);

  const fetchFirst = useCallback(async (q: string, limit: number) => {
    const mine = (seq.current += 1);
    try {
      const page = await aiApi.listConversations({ q, limit, offset: 0 });
      if (seq.current !== mine) return;
      setItems(page.data);
      setTotal(page.total);
      setError(false);
    } catch {
      if (seq.current === mine) setError(true);
    } finally {
      if (seq.current === mine) setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadedRef.current = PAGE;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    void fetchFirst(debounced, PAGE);
  }, [debounced, fetchFirst]);

  /** Refresh without losing how far the user has scrolled. */
  const reload = useCallback(
    () => fetchFirst(debounced, Math.min(MAX, Math.max(PAGE, loadedRef.current))),
    [debounced, fetchFirst],
  );

  const loadMore = useCallback(async () => {
    if (loadingMore || items.length >= total) return;
    setLoadingMore(true);
    try {
      const page = await aiApi.listConversations({
        q: debounced,
        limit: PAGE,
        offset: items.length,
      });
      setItems((prev) => {
        const seen = new Set(prev.map((c) => c.id));
        return [...prev, ...page.data.filter((c) => !seen.has(c.id))];
      });
      setTotal(page.total);
      loadedRef.current = items.length + page.data.length;
    } catch {
      setError(true);
    } finally {
      setLoadingMore(false);
    }
  }, [debounced, items.length, loadingMore, total]);

  /** Put a freshly created conversation at the top without waiting for a round trip. */
  const prepend = useCallback((c: Conversation) => {
    setItems((prev) => (prev.some((x) => x.id === c.id) ? prev : [c, ...prev]));
    setTotal((t) => t + 1);
  }, []);

  const replace = useCallback((c: Conversation) => {
    setItems((prev) => prev.map((x) => (x.id === c.id ? c : x)));
  }, []);

  const remove = useCallback((id: string) => {
    setItems((prev) => prev.filter((x) => x.id !== id));
    setTotal((t) => Math.max(0, t - 1));
  }, []);

  return {
    items,
    total,
    loading,
    loadingMore,
    error,
    query,
    setQuery,
    searching: debounced.trim().length > 0,
    hasMore: items.length < total,
    loadMore,
    reload,
    prepend,
    replace,
    remove,
  };
}
