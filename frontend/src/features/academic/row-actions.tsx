"use client";

import type { ReactNode } from "react";
import { MoreHorizontal } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

export interface RowAction {
  label: string;
  icon?: ReactNode;
  onSelect: () => void;
  destructive?: boolean;
  /** Draws a separator above this item. */
  separated?: boolean;
}

/** Keyboard-accessible "..." menu for a list row. `name` says which row it belongs to. */
export function RowActions({ name, actions }: { name: string; actions: RowAction[] }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 shrink-0"
            aria-label={`Actions for ${name}`}
          />
        }
      >
        <MoreHorizontal className="h-4 w-4" aria-hidden="true" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-44">
        {actions.map((a) => (
          <div key={a.label}>
            {a.separated && <DropdownMenuSeparator />}
            <DropdownMenuItem
              variant={a.destructive ? "destructive" : "default"}
              onClick={a.onSelect}
            >
              {a.icon}
              {a.label}
            </DropdownMenuItem>
          </div>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
