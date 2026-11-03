import { cn } from "@/lib/utils";

interface LoadingSpinnerProps {
  className?: string;
  size?: "sm" | "md" | "lg";
}

const sizes = { sm: "h-4 w-4", md: "h-6 w-6", lg: "h-10 w-10" };

export function LoadingSpinner({ className, size = "md" }: LoadingSpinnerProps) {
  return (
    <div
      role="status"
      aria-label="Loading"
      className={cn(
        "animate-spin rounded-full border-2 border-muted border-t-primary",
        sizes[size],
        className,
      )}
    />
  );
}

export function LoadingPage() {
  return (
    <div className="flex h-full min-h-[200px] items-center justify-center">
      <LoadingSpinner size="lg" />
    </div>
  );
}
