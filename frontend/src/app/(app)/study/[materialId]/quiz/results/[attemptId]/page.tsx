"use client";

import { Suspense } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { QuizResults } from "@/features/study/quiz-results";

function Results() {
  const { materialId, attemptId } = useParams<{ materialId: string; attemptId: string }>();
  const timeUp = useSearchParams().get("timeup") === "1";
  return <QuizResults materialId={materialId} attemptId={attemptId} timeUp={timeUp} />;
}

export default function QuizResultsPage() {
  return (
    <Suspense fallback={null}>
      <Results />
    </Suspense>
  );
}
