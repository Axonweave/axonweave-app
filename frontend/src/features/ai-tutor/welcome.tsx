"use client";

import { Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";

/** Each prompt starts a real conversation when chosen (spec 7.2). */
export const SUGGESTED_PROMPTS: { label: string; prompt: string }[] = [
  {
    label: "Explain a difficult concept",
    prompt: "Explain a difficult concept to me in simple terms, using an everyday analogy.",
  },
  {
    label: "Teach me a topic step by step",
    prompt:
      "Teach me a topic step by step. Start with the basics and check my understanding as we go.",
  },
  {
    label: "Compare two technical concepts",
    prompt:
      "Compare two technical concepts that students often confuse, in a short table with an example for each.",
  },
  {
    label: "Give me an example-based explanation",
    prompt: "Explain a concept using three worked examples that get harder each time.",
  },
  {
    label: "Help me understand a programming problem",
    prompt:
      "Help me understand a programming problem. Walk through how to think about it before showing any code.",
  },
];

export function Welcome({
  onPick,
  disabled,
}: {
  onPick: (prompt: string) => void;
  disabled: boolean;
}) {
  return (
    <div className="mx-auto flex max-w-2xl flex-col items-center gap-6 px-4 py-10 text-center">
      <span
        className="bg-primary/10 text-primary flex size-12 items-center justify-center rounded-full"
        aria-hidden="true"
      >
        <Sparkles className="size-6" />
      </span>
      <div className="space-y-1">
        <h2 className="text-2xl font-semibold">Welcome to Axonweave AI</h2>
        <p className="text-muted-foreground">Your personal academic learning companion.</p>
      </div>
      <ul className="flex w-full flex-col gap-2" aria-label="Suggested prompts">
        {SUGGESTED_PROMPTS.map((p) => (
          <li key={p.label}>
            <Button
              variant="outline"
              className="h-auto w-full justify-start px-4 py-3 text-left whitespace-normal"
              disabled={disabled}
              onClick={() => onPick(p.prompt)}
            >
              {p.label}
            </Button>
          </li>
        ))}
      </ul>
    </div>
  );
}
