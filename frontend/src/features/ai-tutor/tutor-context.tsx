"use client";

import { createContext, useContext } from "react";
import type { AiModel, AiStatus, Conversation } from "@/lib/api/ai";
import type { useConversations } from "./use-conversations";

export interface TutorContextValue {
  status: AiStatus;
  models: AiModel[];
  /** Explicit model choice, or null to let the server use its default. */
  modelId: string | null;
  setModelId: (id: string | null) => void;
  conversations: ReturnType<typeof useConversations>;
  /** Conversation actions; the dialogs they open live in the shell. */
  requestRename: (c: Conversation) => void;
  requestDelete: (c: Conversation) => void;
  archive: (c: Conversation) => void;
  openUsage: () => void;
  openDrawer: () => void;
}

const TutorContext = createContext<TutorContextValue | null>(null);
export const TutorProvider = TutorContext.Provider;

export function useTutor(): TutorContextValue {
  const value = useContext(TutorContext);
  if (!value) throw new Error("useTutor must be used inside the AI Tutor shell");
  return value;
}
