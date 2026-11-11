"use client";

import type { ComponentProps, ReactNode } from "react";
import { cn } from "@/lib/utils";

export const selectClass =
  "border-input bg-background h-8 w-full min-w-0 rounded-lg border px-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50";
export const textareaClass =
  "border-input bg-background w-full min-w-0 rounded-lg border px-2.5 py-1.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50";

export function Field({
  label,
  htmlFor,
  hint,
  children,
}: {
  label: string;
  htmlFor: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <div className="space-y-1">
      <label htmlFor={htmlFor} className="text-sm font-medium">
        {label}
      </label>
      {children}
      {hint ? <p className="text-muted-foreground text-xs">{hint}</p> : null}
    </div>
  );
}

export function NativeSelect({ className, ...props }: ComponentProps<"select">) {
  return <select className={cn(selectClass, className)} {...props} />;
}

export function Textarea({ className, ...props }: ComponentProps<"textarea">) {
  return <textarea className={cn(textareaClass, className)} {...props} />;
}

export function Chip({ children }: { children: ReactNode }) {
  return (
    <span className="bg-muted text-muted-foreground inline-flex items-center rounded px-1.5 py-0.5 text-xs">
      {children}
    </span>
  );
}
