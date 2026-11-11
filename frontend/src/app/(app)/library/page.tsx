import { Suspense } from "react";
import Link from "next/link";
import { Library } from "@/features/documents/library";

export default function LibraryPage() {
  return (
    <div className="min-w-0 space-y-6">
      <div>
        <h1 className="text-foreground text-2xl font-semibold">Library</h1>
        <p className="text-muted-foreground mt-1 text-sm">
          Upload your study documents. Their text is sent to the AI provider to be indexed so the AI
          Tutor can answer from them. Only you can see them.
        </p>
        <nav aria-label="Library sections" className="mt-3 flex gap-2 text-sm">
          <span
            aria-current="page"
            className="bg-accent text-accent-foreground rounded-md px-3 py-1.5 font-medium"
          >
            Documents
          </span>
          <Link
            href="/study"
            className="text-muted-foreground hover:text-foreground rounded-md px-3 py-1.5 font-medium"
          >
            Study materials
          </Link>
        </nav>
      </div>
      <Suspense fallback={null}>
        <Library />
      </Suspense>
    </div>
  );
}
