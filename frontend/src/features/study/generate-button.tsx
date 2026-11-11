"use client";

import { useState } from "react";
import { Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { GenerateDialog, type PresetSource } from "./generate-dialog";

/** Entry point on subject, chapter and document pages: opens the dialog with the source fixed. */
export function GenerateButton({ preset }: { preset: PresetSource }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button type="button" variant="outline" onClick={() => setOpen(true)}>
        <Sparkles className="mr-2 h-4 w-4" aria-hidden="true" />
        Generate study material
      </Button>
      {open ? <GenerateDialog open={open} onOpenChange={setOpen} preset={preset} /> : null}
    </>
  );
}
