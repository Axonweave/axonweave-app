import { Suspense } from "react";
import { LoadingPage } from "@/components/ui/loading";
import { TutorShell } from "@/features/ai-tutor/tutor-shell";

/**
 * The shell lives in the layout so it survives navigation between conversations: a chat that is
 * streaming keeps streaming while the URL changes from /ai-tutor to /ai-tutor/<id>.
 *
 * The app shell's <main> has p-6 padding and scrolls. The tutor manages its own scrolling, so it
 * cancels that padding (-m-6) and fills exactly the padded area (+3rem = top and bottom padding).
 * Suspense is required because the shell reads the URL on the client.
 */
// The shell is a client component driven by the URL, and the route pages intentionally render
// nothing, so Next's instant-navigation validation can't inspect this segment. Opt out of it.
export const instant = false;

export default function AiTutorLayout() {
  return (
    <div className="-m-6 h-[calc(100%+3rem)] overflow-hidden">
      <Suspense fallback={<LoadingPage />}>
        <TutorShell />
      </Suspense>
    </div>
  );
}
