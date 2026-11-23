/**
 * One hue per learning tool, used everywhere that tool appears (tab, launcher card, sidebar), so a
 * learner recognises "the green one is Revision" without reading. Full class strings on purpose:
 * Tailwind only generates classes it can find literally in the source.
 */
import type { EnvironmentTab } from "@/lib/learning-context";

export interface Tone {
  /** Icon colour. */
  icon: string;
  /** Soft background for icon chips. */
  chip: string;
  /** Active tab / selected state. */
  active: string;
  /** Gradient wash for cards. */
  wash: string;
}

export const TONES: Record<EnvironmentTab, Tone> = {
  overview: {
    icon: "text-indigo-600 dark:text-indigo-300",
    chip: "bg-indigo-500/12 dark:bg-indigo-400/15",
    active: "bg-indigo-500/12 text-indigo-700 dark:bg-indigo-400/15 dark:text-indigo-200",
    wash: "from-indigo-500/10",
  },
  content: {
    icon: "text-blue-600 dark:text-blue-300",
    chip: "bg-blue-500/12 dark:bg-blue-400/15",
    active: "bg-blue-500/12 text-blue-700 dark:bg-blue-400/15 dark:text-blue-200",
    wash: "from-blue-500/10",
  },
  tutor: {
    icon: "text-violet-600 dark:text-violet-300",
    chip: "bg-violet-500/12 dark:bg-violet-400/15",
    active: "bg-violet-500/12 text-violet-700 dark:bg-violet-400/15 dark:text-violet-200",
    wash: "from-violet-500/10",
  },
  graph: {
    icon: "text-sky-600 dark:text-sky-300",
    chip: "bg-sky-500/12 dark:bg-sky-400/15",
    active: "bg-sky-500/12 text-sky-700 dark:bg-sky-400/15 dark:text-sky-200",
    wash: "from-sky-500/10",
  },
  intelligence: {
    icon: "text-amber-600 dark:text-amber-300",
    chip: "bg-amber-500/15 dark:bg-amber-400/15",
    active: "bg-amber-500/15 text-amber-800 dark:bg-amber-400/15 dark:text-amber-200",
    wash: "from-amber-500/10",
  },
  revision: {
    icon: "text-emerald-600 dark:text-emerald-300",
    chip: "bg-emerald-500/12 dark:bg-emerald-400/15",
    active: "bg-emerald-500/12 text-emerald-700 dark:bg-emerald-400/15 dark:text-emerald-200",
    wash: "from-emerald-500/10",
  },
  research: {
    icon: "text-rose-600 dark:text-rose-300",
    chip: "bg-rose-500/12 dark:bg-rose-400/15",
    active: "bg-rose-500/12 text-rose-700 dark:bg-rose-400/15 dark:text-rose-200",
    wash: "from-rose-500/10",
  },
  progress: {
    icon: "text-teal-600 dark:text-teal-300",
    chip: "bg-teal-500/12 dark:bg-teal-400/15",
    active: "bg-teal-500/12 text-teal-700 dark:bg-teal-400/15 dark:text-teal-200",
    wash: "from-teal-500/10",
  },
};

/** Sidebar destinations that are learning tools, mapped to their tone. */
export const TONE_BY_HREF: Record<string, Tone> = {
  "/ai-tutor": TONES.tutor,
  "/knowledge": TONES.graph,
  "/insights": TONES.intelligence,
  "/research": TONES.research,
  "/revision": TONES.revision,
  "/progress": TONES.progress,
  "/library": TONES.content,
  "/study": {
    icon: "text-fuchsia-600 dark:text-fuchsia-300",
    chip: "bg-fuchsia-500/12",
    active: "bg-fuchsia-500/12 text-fuchsia-700 dark:text-fuchsia-200",
    wash: "from-fuchsia-500/10",
  },
};
