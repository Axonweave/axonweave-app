"use client";

import { useParams, useSearchParams } from "next/navigation";
import { DocumentDetail } from "@/features/documents/document-detail";

export default function DocumentPage() {
  const { documentId } = useParams<{ documentId: string }>();
  const chunk = useSearchParams().get("chunk");
  const parsed = chunk !== null && /^\d+$/.test(chunk) ? Number(chunk) : undefined;
  return <DocumentDetail documentId={documentId} highlightChunk={parsed} />;
}
