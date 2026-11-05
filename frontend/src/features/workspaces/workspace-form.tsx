"use client";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { WorkspaceType } from "@/types/api";

const WS_TYPES: Array<{ value: WorkspaceType; label: string }> = [
  { value: "personal_learning", label: "Personal learning" },
  { value: "university", label: "University" },
  { value: "research", label: "Research" },
  { value: "professional_development", label: "Professional development" },
  { value: "custom", label: "Custom" },
];

export const PRESET_COLOURS = [
  "#3b82f6",
  "#8b5cf6",
  "#ec4899",
  "#f59e0b",
  "#10b981",
  "#ef4444",
  "#6366f1",
  "#14b8a6",
];

export function ColourPicker({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <div className="flex flex-wrap gap-2">
      {PRESET_COLOURS.map((c) => (
        <button
          key={c}
          type="button"
          onClick={() => onChange(c)}
          className={`h-7 w-7 rounded-full border-2 transition-transform ${
            value === c ? "border-foreground scale-110" : "border-transparent"
          }`}
          style={{ backgroundColor: c }}
          aria-label={c}
          aria-pressed={value === c}
        />
      ))}
    </div>
  );
}

export interface WorkspaceFormData {
  name: string;
  description: string;
  workspace_type: WorkspaceType;
  colour: string;
}

export function WorkspaceFormFields({
  data,
  onChange,
}: {
  data: WorkspaceFormData;
  onChange: (d: WorkspaceFormData) => void;
}) {
  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="ws-name">Name *</Label>
        <Input
          id="ws-name"
          value={data.name}
          onChange={(e) => onChange({ ...data, name: e.target.value })}
          maxLength={255}
          required
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="ws-desc">Description</Label>
        <Input
          id="ws-desc"
          value={data.description}
          onChange={(e) => onChange({ ...data, description: e.target.value })}
          maxLength={2000}
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="ws-type">Type</Label>
        <select
          id="ws-type"
          value={data.workspace_type}
          onChange={(e) => onChange({ ...data, workspace_type: e.target.value as WorkspaceType })}
          className="border-input bg-background focus:ring-ring w-full rounded-md border px-3 py-2 text-sm focus:ring-2 focus:outline-none"
        >
          {WS_TYPES.map((t) => (
            <option key={t.value} value={t.value}>
              {t.label}
            </option>
          ))}
        </select>
      </div>
      <div className="space-y-2">
        <Label>Colour</Label>
        <ColourPicker value={data.colour} onChange={(c) => onChange({ ...data, colour: c })} />
      </div>
    </div>
  );
}

export const DEFAULT_FORM: WorkspaceFormData = {
  name: "",
  description: "",
  workspace_type: "personal_learning",
  colour: PRESET_COLOURS[0],
};
