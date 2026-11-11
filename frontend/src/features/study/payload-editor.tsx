"use client";

import { Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "./ui-bits";

type Json = string | number | boolean | null | Json[] | { [key: string]: Json };
type Obj = { [key: string]: Json };

/** Fields the backend owns or recomputes: never offered for editing. */
const LOCKED = new Set([
  "source_refs",
  "kind",
  "level",
  "needs_review",
  "review_notes",
  "verification",
  "flagged_count",
  "generated_recommendation",
  "additional_explanation",
  "question_type",
  "difficulty",
  "card_type",
]);

const label = (key: string) => key.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());

/**
 * Edits the text of a generated payload in place. Strings become text areas, lists of strings
 * become one line per item, lists of objects get per-item fieldsets with a remove button. The
 * backend validates the result again on save (D-92) and recomputes any flags.
 */
export function PayloadEditor({
  value,
  onChange,
  path = "",
}: {
  value: Obj;
  onChange: (next: Obj) => void;
  path?: string;
}) {
  return (
    <div className="space-y-3">
      {Object.entries(value).map(([key, v]) => {
        if (LOCKED.has(key)) return null;
        const id = `edit-${path}${key}`;
        const set = (next: Json) => onChange({ ...value, [key]: next });
        if (typeof v === "string") {
          const long = v.length > 80 || v.includes("\n") || key === "body" || key === "overview";
          return (
            <div key={key} className="space-y-1">
              <label htmlFor={id} className="text-sm font-medium">
                {label(key)}
              </label>
              <Textarea
                id={id}
                rows={long ? 5 : 1}
                value={v}
                onChange={(e) => set(e.target.value)}
              />
            </div>
          );
        }
        if (Array.isArray(v) && v.every((x) => typeof x === "string")) {
          return (
            <div key={key} className="space-y-1">
              <label htmlFor={id} className="text-sm font-medium">
                {label(key)}{" "}
                <span className="text-muted-foreground font-normal">(one per line)</span>
              </label>
              <Textarea
                id={id}
                rows={Math.min(10, Math.max(3, v.length + 1))}
                value={(v as string[]).join("\n")}
                onChange={(e) => set(e.target.value.split("\n").filter((l) => l.trim() !== ""))}
              />
            </div>
          );
        }
        if (Array.isArray(v) && v.every((x) => x && typeof x === "object" && !Array.isArray(x))) {
          const items = v as Obj[];
          return (
            <fieldset key={key} className="space-y-3">
              <legend className="text-sm font-semibold">{label(key)}</legend>
              {items.map((item, i) => (
                <div key={i} className="border-border space-y-3 rounded-lg border p-3">
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground text-xs">
                      {label(key.replace(/s$/, ""))} {i + 1}
                    </span>
                    {items.length > 1 ? (
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon-sm"
                        aria-label={`Remove ${label(key.replace(/s$/, ""))} ${i + 1}`}
                        onClick={() => set(items.filter((_, j) => j !== i))}
                      >
                        <Trash2 aria-hidden="true" />
                      </Button>
                    ) : null}
                  </div>
                  <PayloadEditor
                    path={`${path}${key}-${i}-`}
                    value={item}
                    onChange={(next) => set(items.map((x, j) => (j === i ? next : x)))}
                  />
                </div>
              ))}
            </fieldset>
          );
        }
        return null;
      })}
    </div>
  );
}
