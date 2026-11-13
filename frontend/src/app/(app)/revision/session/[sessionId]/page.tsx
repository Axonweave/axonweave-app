import { SessionRunner } from "@/features/revision/session-runner";

export default async function RevisionSessionPage({
  params,
}: {
  params: Promise<{ sessionId: string }>;
}) {
  const { sessionId } = await params;
  return <SessionRunner sessionId={sessionId} />;
}
