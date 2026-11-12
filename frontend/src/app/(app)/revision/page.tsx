import { RevisionCentre } from "@/features/revision/revision-centre";

export default function RevisionPage() {
  return (
    <div className="min-w-0 space-y-6">
      <div>
        <h1 className="text-foreground text-2xl font-semibold">Revision</h1>
        <p className="text-muted-foreground mt-1 text-sm">
          Review your flashcards on a spaced schedule. Cards come back when you are about to forget
          them. Only you can see this.
        </p>
      </div>
      <RevisionCentre />
    </div>
  );
}
