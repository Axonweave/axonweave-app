"use client";

import { toast as baseToast } from "@/components/ui/toast";

type ToastOptions = {
  title?: string;
  description?: string;
  type?: string;
  variant?: "default" | "destructive";
};

function useToast() {
  const toast = (opts: ToastOptions) => {
    baseToast.add({
      title: opts.title,
      description: opts.description,
      type: opts.variant === "destructive" ? "error" : (opts.type ?? "default"),
    });
  };
  return { toast };
}

export { useToast };
