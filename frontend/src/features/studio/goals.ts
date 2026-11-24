import type { PresetInput } from "@/lib/api/presets";

/**
 * Starting points for a new preset. They only prefill the editor with values the backend accepts;
 * the learner reviews and changes everything before saving, so nothing here is applied silently.
 */
export interface Goal {
  id: string;
  title: string;
  blurb: string;
  preset: PresetInput;
}

const BASE: PresetInput = {
  name: "",
  description: null,
  is_default: false,
  language: null,
  explanation_level: null,
  summary_length: null,
  question_difficulty: null,
  include_examples: true,
  include_definitions: true,
  include_source_references: true,
};

export const GOALS: Goal[] = [
  {
    id: "exam",
    title: "Exam preparation",
    blurb: "Tight summaries and hard practice questions.",
    preset: {
      ...BASE,
      name: "Exam preparation",
      description: "Short summaries and hard questions for a coming exam.",
      summary_length: "short",
      question_difficulty: "hard",
      include_examples: false,
    },
  },
  {
    id: "understand",
    title: "Understand deeply",
    blurb: "Beginner-friendly, detailed, with examples.",
    preset: {
      ...BASE,
      name: "Understand deeply",
      description: "Detailed explanations with examples and definitions.",
      explanation_level: "beginner",
      summary_length: "long",
      question_difficulty: "medium",
    },
  },
  {
    id: "revise",
    title: "Quick revision",
    blurb: "Fast, short and mixed difficulty.",
    preset: {
      ...BASE,
      name: "Quick revision",
      description: "Short refreshers across mixed difficulty.",
      summary_length: "short",
      question_difficulty: "mixed",
    },
  },
  {
    id: "advanced",
    title: "Advanced reading",
    blurb: "Concise, advanced level, with sources.",
    preset: {
      ...BASE,
      name: "Advanced reading",
      description: "Advanced explanations that cite their sources.",
      explanation_level: "advanced",
      summary_length: "medium",
      question_difficulty: "hard",
      include_examples: false,
    },
  },
];

export const BLANK_PRESET: PresetInput = BASE;
