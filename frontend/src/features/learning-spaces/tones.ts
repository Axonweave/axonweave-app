/**
 * How a learning tool is drawn wherever it appears (tab, launcher card, sidebar, room panel).
 *
 * Deliberately neutral: professional tools are told apart by icon and label, not by a rainbow.
 * Colour is kept for meaning only (status, the learner's own subject colours) and the one
 * accent for actions and focus. The per-tool map stays so a tool can be given emphasis later
 * from one place.
 */
import type { EnvironmentTab } from "@/lib/learning-context";

export interface Tone {
  /** Icon colour. */
  icon: string;
  /** Background for icon chips. */
  chip: string;
  /** Active tab / selected state. */
  active: string;
}

const NEUTRAL: Tone = {
  icon: "text-muted-foreground",
  chip: "bg-muted",
  active: "bg-background text-foreground shadow-xs ring-1 ring-border",
};

export const TONES: Record<EnvironmentTab, Tone> = {
  overview: NEUTRAL,
  content: NEUTRAL,
  tutor: NEUTRAL,
  graph: NEUTRAL,
  intelligence: NEUTRAL,
  revision: NEUTRAL,
  research: NEUTRAL,
  progress: NEUTRAL,
};

/** Sidebar destinations that are learning tools. */
export const TONE_BY_HREF: Record<string, Tone> = {};
