import { api } from "./client";
import { query } from "./paged";
import type { components } from "@/types/api.generated";

type S = components["schemas"];
export type RevisionSummary = S["SummaryOut"];
export type RevisionSession = S["app__modules__revision__schemas__SessionOut"];
export type RevisionSessionDetail = S["SessionDetailOut"];
export type SessionCard = S["SessionCardOut"];
export type ReviewResult = S["ReviewOut"];
export type Rating = "again" | "hard" | "good" | "easy";

export type AnalyticsOverview = S["OverviewOut"];
export type TopicPerformance = S["TopicPerformanceOut"];
export type TopicRow = S["TopicOut"];
export type SubjectPerformance = S["SubjectPerformanceOut"];
export type RevisionActivity = S["RevisionActivityOut"];
export type StudyCalendar = S["CalendarOut"];
export type DayDetail = S["DayDetailOut"];
export type QuizPerformance = S["QuizPerformanceOut"];
export type Streak = S["StreakOut"];
export type Recommendation = S["RecommendationOut"];

const enc = encodeURIComponent;

export interface AnalyticsFilters {
  subject_id?: string;
  chapter_id?: string;
  start_date?: string;
  end_date?: string;
}

/** A fresh key per rating press; resending the same key is safe (the server ignores the repeat). */
export function newIdempotencyKey(): string {
  return `r-${crypto.randomUUID().replace(/-/g, "")}`;
}

export const revisionApi = {
  summary: () => api.get<RevisionSummary>("/revision/summary").then((r) => r.data),
  startSession: (body: { subject_id?: string; limit?: number; include_new?: boolean } = {}) =>
    api.post<RevisionSession>("/revision/sessions", body).then((r) => r.data),
  session: (id: string) =>
    api.get<RevisionSessionDetail>(`/revision/sessions/${enc(id)}`).then((r) => r.data),
  completeSession: (id: string) =>
    api.post<RevisionSession>(`/revision/sessions/${enc(id)}/complete`).then((r) => r.data),
  abandonSession: (id: string) =>
    api.post<RevisionSession>(`/revision/sessions/${enc(id)}/abandon`).then((r) => r.data),
  review: (
    cardId: string,
    body: {
      rating: Rating;
      idempotency_key: string;
      session_id?: string;
      response_time_ms?: number;
    },
  ) =>
    api
      .post<ReviewResult>(`/study/flashcards/cards/${enc(cardId)}/review`, body)
      .then((r) => r.data),
  suspend: (cardId: string) => api.patch(`/study/flashcards/cards/${enc(cardId)}/suspend`),
};

export const analyticsApi = {
  overview: (f: AnalyticsFilters = {}) =>
    api.get<AnalyticsOverview>(`/analytics/overview${query({ ...f })}`).then((r) => r.data),
  topics: (f: AnalyticsFilters = {}) =>
    api.get<TopicPerformance>(`/analytics/topic-performance${query({ ...f })}`).then((r) => r.data),
  subjects: (f: AnalyticsFilters = {}) =>
    api
      .get<SubjectPerformance>(`/analytics/subject-performance${query({ ...f })}`)
      .then((r) => r.data),
  quizzes: (f: AnalyticsFilters = {}) =>
    api.get<QuizPerformance>(`/analytics/quiz-performance${query({ ...f })}`).then((r) => r.data),
  activity: (f: AnalyticsFilters = {}) =>
    api.get<RevisionActivity>(`/analytics/revision-activity${query({ ...f })}`).then((r) => r.data),
  calendar: (f: AnalyticsFilters = {}) =>
    api.get<StudyCalendar>(`/analytics/study-calendar${query({ ...f })}`).then((r) => r.data),
  day: (day: string) =>
    api.get<DayDetail>(`/analytics/study-calendar/${enc(day)}`).then((r) => r.data),
};

export const recommendationsApi = {
  revision: () =>
    api
      .get<{ items: Recommendation[]; note: string }>("/recommendations/revision")
      .then((r) => r.data),
  complete: (id: string) =>
    api.post<Recommendation>(`/recommendations/${enc(id)}/complete`).then((r) => r.data),
  dismiss: (id: string) =>
    api.post<Recommendation>(`/recommendations/${enc(id)}/dismiss`).then((r) => r.data),
};

/** Keyboard shortcut for a rating, or null for any other key. */
export function ratingForKey(key: string): Rating | null {
  return (
    ({ "1": "again", "2": "hard", "3": "good", "4": "easy" } as Record<string, Rating>)[key] ?? null
  );
}

/** "75%" for a 0-100 figure, or "No data yet" when there is nothing to average. */
export function formatPercent(value: number | null | undefined): string {
  return value === null || value === undefined ? "No data yet" : `${Math.round(value)}%`;
}

export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min`;
  return `${Math.floor(minutes / 60)} h ${minutes % 60} min`;
}
