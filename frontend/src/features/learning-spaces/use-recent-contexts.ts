"use client";

import { useEffect, useState } from "react";
import { readRecentContexts, subscribeRecentContexts, type RecentContext } from "./recent-contexts";

/** Recently opened learning contexts (this browser only); empty during SSR and when storage is blocked. */
export function useRecentContexts(): RecentContext[] {
  const [list, setList] = useState<RecentContext[]>([]);
  useEffect(() => {
    const sync = () => setList(readRecentContexts());
    sync();
    return subscribeRecentContexts(sync);
  }, []);
  return list;
}
