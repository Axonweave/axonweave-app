"use client";

import { useParams } from "next/navigation";
import { EnvironmentTabBySegment } from "@/features/learning-spaces/environment-tab";

/** content, tutor, graph, intelligence, revision, research or progress; anything else is a 404. */
export default function EnvironmentToolPage() {
  const { tab } = useParams<{ tab: string }>();
  return <EnvironmentTabBySegment segment={tab} />;
}
