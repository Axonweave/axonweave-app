"use client";

import { useParams } from "next/navigation";
import { QuizTaker } from "@/features/study/quiz-taker";

export default function TakeQuizPage() {
  const { materialId } = useParams<{ materialId: string }>();
  return <QuizTaker materialId={materialId} />;
}
