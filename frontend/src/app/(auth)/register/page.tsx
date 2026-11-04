"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { api, ApiRequestError } from "@/lib/api/client";
import { registerSchema, type RegisterFormData } from "@/lib/validation/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function RegisterPage() {
  const [registeredEmail, setRegisteredEmail] = useState<string | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<RegisterFormData>({ resolver: zodResolver(registerSchema) });

  const onSubmit = async (data: RegisterFormData) => {
    setServerError(null);
    try {
      await api.post("/auth/register", data);
      setRegisteredEmail(data.email);
    } catch (err) {
      if (err instanceof ApiRequestError) {
        setServerError(err.message);
      } else {
        setServerError("An unexpected error occurred. Please try again.");
      }
    }
  };

  if (registeredEmail) {
    return (
      <div className="border-border bg-background space-y-4 rounded-xl border p-6 text-center shadow-sm">
        <h1 className="text-xl font-semibold">Check your email</h1>
        <p className="text-muted-foreground text-sm">
          We sent a link to {registeredEmail}. Please verify your email address, then sign in.
        </p>
        <Link href="/login" className="text-primary block text-sm underline underline-offset-4">
          Go to sign in
        </Link>
      </div>
    );
  }

  return (
    <div className="border-border bg-background space-y-6 rounded-xl border p-6 shadow-sm">
      <div className="space-y-1">
        <h1 className="text-xl font-semibold">Create your account</h1>
        <p className="text-muted-foreground text-sm">
          Already have an account?{" "}
          <Link href="/login" className="text-primary underline underline-offset-4">
            Sign in
          </Link>
        </p>
      </div>

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
        {serverError && (
          <div className="bg-destructive/10 text-destructive rounded-md px-3 py-2 text-sm">
            {serverError}
          </div>
        )}

        <div className="space-y-1.5">
          <Label htmlFor="full_name">Full name</Label>
          <Input
            id="full_name"
            type="text"
            autoComplete="name"
            placeholder="Ada Lovelace"
            {...register("full_name")}
            aria-invalid={!!errors.full_name}
          />
          {errors.full_name && (
            <p className="text-destructive text-xs">{errors.full_name.message}</p>
          )}
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="email">Email</Label>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            placeholder="you@example.com"
            {...register("email")}
            aria-invalid={!!errors.email}
          />
          {errors.email && <p className="text-destructive text-xs">{errors.email.message}</p>}
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="password">Password</Label>
          <Input
            id="password"
            type="password"
            autoComplete="new-password"
            {...register("password")}
            aria-invalid={!!errors.password}
          />
          {errors.password && <p className="text-destructive text-xs">{errors.password.message}</p>}
          <p className="text-muted-foreground text-xs">Minimum 12 characters</p>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="confirm_password">Confirm password</Label>
          <Input
            id="confirm_password"
            type="password"
            autoComplete="new-password"
            {...register("confirm_password")}
            aria-invalid={!!errors.confirm_password}
          />
          {errors.confirm_password && (
            <p className="text-destructive text-xs">{errors.confirm_password.message}</p>
          )}
        </div>

        <div className="space-y-1.5">
          <div className="flex items-start gap-2">
            <input
              id="terms_accepted"
              type="checkbox"
              className="border-border mt-0.5 h-4 w-4 rounded"
              {...register("terms_accepted")}
            />
            <Label htmlFor="terms_accepted" className="text-sm leading-relaxed font-normal">
              I agree to the{" "}
              <a href="/terms" className="text-primary underline underline-offset-4">
                Terms of Service
              </a>{" "}
              and{" "}
              <a href="/privacy" className="text-primary underline underline-offset-4">
                Privacy Policy
              </a>
            </Label>
          </div>
          {errors.terms_accepted && (
            <p className="text-destructive text-xs">{errors.terms_accepted.message}</p>
          )}
        </div>

        <Button type="submit" className="w-full" disabled={isSubmitting}>
          {isSubmitting ? "Creating account…" : "Create account"}
        </Button>
      </form>
    </div>
  );
}
