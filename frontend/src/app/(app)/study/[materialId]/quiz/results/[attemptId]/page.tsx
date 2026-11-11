"use client";

import { useParams } from "next/navigation";
import { QuizResults } from "@/features/study/quiz-results";

export default function QuizResultsPage() {
  const { materialId, attemptId } = useParams<{ materialId: string; attemptId: string }>();
  return <QuizResults materialId={materialId} attemptId={attemptId} />;
}
