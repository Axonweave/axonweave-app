import { LearningSpaceProvider } from "@/features/learning-spaces/space-provider";

/**
 * A study room fills the whole content area and manages its own scrolling (chat, chat list and
 * tool panel each scroll on their own), so it cancels the app shell's padding.
 */
export default function StudyRoomLayout({ children }: { children: React.ReactNode }) {
  return (
    <LearningSpaceProvider>
      <div className="-m-6 h-[calc(100%+3rem)] overflow-hidden">{children}</div>
    </LearningSpaceProvider>
  );
}
