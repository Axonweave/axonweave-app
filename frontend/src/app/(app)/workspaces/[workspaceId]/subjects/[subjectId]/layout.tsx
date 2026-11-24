import { LearningSpaceProvider } from "@/features/learning-spaces/space-provider";

/**
 * Loads the subject once for every page below it: the subject environment, and the folder and
 * chapter environments nested in it. Tabs and levels share that data instead of refetching it.
 */
export default function SubjectSpaceLayout({ children }: { children: React.ReactNode }) {
  return <LearningSpaceProvider>{children}</LearningSpaceProvider>;
}
