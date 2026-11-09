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
      </div>
      <Library />
    </div>
  );
}
