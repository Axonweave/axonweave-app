import { api } from "./client";
import type { components } from "@/types/api.generated";

type S = components["schemas"];
export type Conversation = S["ConversationOut"];
export type ChatMessageRecord = S["MessageOut"];
export type AiModel = S["ModelOut"];
export type AiStatus = S["AiStatusOut"];
export type UsageSummary = S["UsageSummaryOut"];
export type UserPreferences = S["UserPreferencesOut"];

export interface Paged<T> {
  data: T[];
  total: number;
  limit: number;
  offset: number;
}

/** List endpoints return `{ success, data, total, ... }`; `api.get` hands back that whole envelope. */
type PagedEnvelope<T> = { success: true; data: T[]; total: number; limit: number; offset: number };

async function paged<T>(path: string): Promise<Paged<T>> {
  const res = (await api.get<T[]>(path)) as unknown as PagedEnvelope<T>;
  return { data: res.data, total: res.total, limit: res.limit, offset: res.offset };
}

const enc = encodeURIComponent;

export const aiApi = {
  status: () => api.get<AiStatus>("/ai/status").then((r) => r.data),
  models: () => api.get<AiModel[]>("/ai/models").then((r) => r.data),

  listConversations: (opts: { q?: string; limit?: number; offset?: number } = {}) => {
    const qs = new URLSearchParams({
      limit: String(opts.limit ?? 30),
      offset: String(opts.offset ?? 0),
    });
    if (opts.q?.trim()) qs.set("q", opts.q.trim());
    return paged<Conversation>(`/ai/conversations?${qs}`);
  },
  getConversation: (id: string) =>
    api.get<Conversation>(`/ai/conversations/${enc(id)}`).then((r) => r.data),
  createConversation: (modelId?: string | null) =>
    api
      .post<Conversation>("/ai/conversations", modelId ? { model_id: modelId } : {})
      .then((r) => r.data),
  renameConversation: (id: string, title: string) =>
    api.patch<Conversation>(`/ai/conversations/${enc(id)}`, { title }).then((r) => r.data),
  archiveConversation: (id: string) =>
    api.post<Conversation>(`/ai/conversations/${enc(id)}/archive`).then((r) => r.data),
  deleteConversation: (id: string) => api.delete<null>(`/ai/conversations/${enc(id)}`),

  /** All messages of a conversation (pages of 100 until `total` is reached). */
  async listMessages(id: string): Promise<ChatMessageRecord[]> {
    const all: ChatMessageRecord[] = [];
    for (let offset = 0; offset < 10_000; offset += 100) {
      const page = await paged<ChatMessageRecord>(
        `/ai/conversations/${enc(id)}/messages?limit=100&offset=${offset}`,
      );
      all.push(...page.data);
      if (all.length >= page.total || page.data.length === 0) break;
    }
    return all;
  },
  cancel: (conversationId: string, messageId: string) =>
    api
      .post<ChatMessageRecord>(
        `/ai/conversations/${enc(conversationId)}/messages/${enc(messageId)}/cancel`,
      )
      .then((r) => r.data),
  feedback: (messageId: string, rating: "positive" | "negative") =>
    api.post<unknown>(`/ai/messages/${enc(messageId)}/feedback`, { rating }),

  usageSummary: (days = 30) =>
    api.get<UsageSummary>(`/ai/usage/summary?days=${days}`).then((r) => r.data),

  preferences: () => api.get<UserPreferences>("/users/me/preferences").then((r) => r.data),
  acknowledgeNotice: () =>
    api.post<UserPreferences>("/users/me/ai-notice/acknowledge").then((r) => r.data),
};
