"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { api, ApiRequestError } from "@/lib/api/client";
import { LoadingSpinner } from "@/components/ui/loading";

type State = "loading" | "success" | "error" | "no_token";

function VerifyEmailContent() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token");
  const [state, setState] = useState<State>(token ? "loading" : "no_token");
  const [message, setMessage] = useState<string>("");

  useEffect(() => {
    if (!token) return;
    api
      .post("/auth/verify-email", { token })
      .then(() => setState("success"))
      .catch((err) => {
        const msg =
          err instanceof ApiRequestError ? err.message : "Verification failed. Please try again.";
        setMessage(msg);
        setState("error");
      });
  }, [token]);

  if (state === "loading") {
    return (
      <div className="flex flex-col items-center gap-4 rounded-xl border border-border bg-background p-6 shadow-sm">
        <LoadingSpinner />
        <p className="text-sm text-muted-foreground">Verifying your email…</p>
      </div>
    );
  }

  if (state === "success") {
    return (
      <div className="space-y-4 rounded-xl border border-border bg-background p-6 shadow-sm text-center">
        <h1 className="text-xl font-semibold">Email verified</h1>
        <p className="text-sm text-muted-foreground">
          Your email address has been verified. You can now use all Axonweave features.
        </p>
        <Link href="/dashboard" className="block text-sm text-primary underline underline-offset-4">
          Go to dashboard
        </Link>
      </div>
    );
  }

  if (state === "error") {
    return (
      <div className="space-y-4 rounded-xl border border-border bg-background p-6 shadow-sm text-center">
        <h1 className="text-xl font-semibold">Verification failed</h1>
        <p className="text-sm text-muted-foreground">{message}</p>
        <Link href="/login" className="block text-sm text-primary underline underline-offset-4">
          Back to sign in
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-4 rounded-xl border border-border bg-background p-6 shadow-sm text-center">
      <h1 className="text-xl font-semibold">Invalid link</h1>
      <p className="text-sm text-muted-foreground">
        This verification link is missing a token. Please use the link from your email.
      </p>
      <Link href="/login" className="block text-sm text-primary underline underline-offset-4">
        Back to sign in
      </Link>
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense>
      <VerifyEmailContent />
    </Suspense>
  );
}
