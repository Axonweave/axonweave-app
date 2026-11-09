"use client";

import { Suspense } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { DocumentDetail } from "@/features/documents/document-detail";

function DocumentContent() {
  const { documentId } = useParams<{ documentId: string }>();
  const params = useSearchParams();
  const num = (v: string | null) => (v !== null && /^\d+$/.test(v) ? Number(v) : undefined);
  const uuid = (v: string | null) =>
    v !== null && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v)
      ? v
      : undefined;
  return (
    <DocumentDetail
      documentId={documentId}
      highlightChunk={num(params.get("chunk"))}
      initialPage={num(params.get("page"))}
      sourceId={uuid(params.get("source"))}
    />
  );
}

export default function DocumentPage() {
  return (
    <Suspense fallback={null}>
      <DocumentContent />
    </Suspense>
  );
}
