"use client";

import { Suspense } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { DocumentDetail } from "@/features/documents/document-detail";

function DocumentContent() {
  const { documentId } = useParams<{ documentId: string }>();
  const params = useSearchParams();
  const num = (v: string | null) => (v !== null && /^\d+$/.test(v) ? Number(v) : undefined);
  return (
    <DocumentDetail
      documentId={documentId}
      highlightChunk={num(params.get("chunk"))}
      initialPage={num(params.get("page"))}
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
